"""Transport security, real-schema orchestration and cache/cancellation regressions."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch

import appeears_data as app
import hydrology_data as hydro
import station_data as noaa
import geography
import hashlib

JID='12345678-1234-1234-1234-123456789abc'
FID='22345678-1234-1234-1234-123456789abc'
CSV=b'File Name,Dataset,aid,Date,Count,Minimum,Maximum,Range,Mean\nMOD13A3_061_NDVI_doy2024001_aid0001,NDVI,aid0001,2024-01-01,4,0.4,0.6,0.2,0.5\n'


class Response:
    def __init__(self,status=200,body=b'{}',headers=None):self.status_code=status;self.body=body;self.headers=headers or {}
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def iter_content(self,*a):yield self.body


def session(response):
    s=MagicMock();s.__enter__.return_value=s;s.get.return_value=response;s.request.return_value=response
    return s


class TestSourceTransport(unittest.TestCase):
    def test_hydrology_auth_is_scoped_and_redirects_are_not_followed(self):
        s=session(Response(body=b'csv'))
        with patch.object(hydro.requests,'Session',return_value=s):self.assertEqual(hydro._request({'data':'fixture'},'fixture-token'),b'csv')
        call=s.get.call_args;self.assertEqual(call.args[0],hydro.BASE)
        self.assertFalse(call.kwargs['allow_redirects']);self.assertEqual(call.kwargs['headers']['Authorization'],'Bearer fixture-token')

    def test_all_transports_reject_service_errors_and_oversized_responses(self):
        for source in ('app','hydro','noaa'):
            for status,body in [(403,b'{}'),(500,b'{}'),(302,b'{}'),(200,b'x'*2_000_001)]:
                s=session(Response(status,body))
                with self.subTest(source=source,status=status,size=len(body)),patch.object(app.requests,'Session',return_value=s):
                    with self.assertRaises(ValueError):
                        {'app':lambda:app._request('task',bearer='fixture'),
                         'hydro':lambda:hydro._request({},'fixture'),
                         'noaa':lambda:noaa._request('data/v1',{})}[source]()

    def test_app_and_noaa_reject_untrusted_routes_before_a_request(self):
        with patch.object(app.requests,'Session') as request:
            with self.assertRaises(ValueError):app._request('https://example.com/steal',bearer='fixture')
            with self.assertRaises(ValueError):noaa._request('../outside',{})
        request.assert_not_called()

    def test_completed_app_status_redirect_is_followed_only_to_the_same_nasa_task(self):
        s=session(Response(303,headers={'Location':'/api/task/'+JID}))
        s.request.side_effect=[Response(303,headers={'Location':'/api/task/'+JID}),Response(200,json.dumps({'task_id':JID,'status':'done'}).encode())]
        with patch.object(app.requests,'Session',return_value=s):
            self.assertEqual(app._request('status/'+JID,bearer='fixture')['status'],'done')
        self.assertEqual(s.request.call_args_list[-1].args[1],app.BASE+'task/'+JID)
        for destination in ['https://example.com/api/task/'+JID,'/api/task/'+FID]:
            s=session(Response(303,headers={'Location':destination}))
            with patch.object(app.requests,'Session',return_value=s):
                with self.assertRaises(ValueError):app._request('status/'+JID,bearer='fixture')
            self.assertEqual(s.request.call_count,1)

    def test_app_summary_delivery_strips_credentials_and_rejects_rasters_or_other_tasks(self):
        prefix='https://d2v96idf0qj40l.cloudfront.net/s3-eab5ea0d219da2588ae2241aa105a663/appeears-output.s3.amazonaws.com/'
        url=prefix+JID+'/MOD13A3-061-Statistics.csv?fixture-signature=not-a-real-key'
        s=session(Response(302,headers={'Location':url}));s.get.return_value=Response(200,CSV)
        with patch.object(app.requests,'Session',return_value=s):
            self.assertEqual(app._request('bundle/'+JID+'/'+FID,bearer='fixture-token',raw=True),CSV)
        self.assertNotIn('Authorization',s.get.call_args.kwargs['headers'])
        self.assertFalse(s.get.call_args.kwargs['allow_redirects'])
        for location in [url.replace('d2v96idf0qj40l.cloudfront.net','example.com'),url.replace(JID,FID),url.replace('Statistics.csv','raster.tif')]:
            s=session(Response(302,headers={'Location':location}))
            with patch.object(app.requests,'Session',return_value=s):
                with self.assertRaises(ValueError):app._request('bundle/'+JID+'/'+FID,bearer='fixture',raw=True)
            s.get.assert_not_called()
        for output in [Response(403,b'{}'),Response(200,b'x'*2_000_001)]:
            s=session(Response(302,headers={'Location':url}));s.get.return_value=output
            with patch.object(app.requests,'Session',return_value=s):
                with self.assertRaises(ValueError):app._request('bundle/'+JID+'/'+FID,bearer='fixture',raw=True)

    def test_appeears_login_remembers_only_issued_token_and_disconnect_is_separate(self):
        with patch.object(app,'_TOKEN',''),patch.object(app,'_request',return_value={'token':'fixture-token-that-is-long-enough'}) as request,\
             patch.object(app.service_credentials,'remember') as remember,patch.object(app.service_credentials,'forget') as forget,\
             patch.object(app.service_credentials,'load',return_value=''):
            self.assertTrue(app.connect('fixture-user','fixture-password')['configured'])
            self.assertEqual(request.call_args.kwargs['auth'],('fixture-user','fixture-password'))
            remember.assert_called_once_with('appeears','fixture-token-that-is-long-enough')
            self.assertFalse(app.disconnect()['configured']);forget.assert_called_once_with('appeears')
        for username,password in [('',None),('x',''),(None,'fixture')]:
            with self.assertRaises(ValueError):app.connect(username,password)

    def test_appeears_polls_and_downloads_only_summary_then_reuses_cached_values(self):
        feature=geography.resolve('focus:ghana_north')
        def reply(route,**kwargs):
            if route=='task':return {'task_id':JID,'status':'queued'}
            if route in {'task/'+JID,'status/'+JID}:return {'task_id':JID,'status':'done'}
            if route=='bundle/'+JID:return {'files':[{'file_id':FID,'file_name':'MOD13A3-061-Statistics.csv'}]}
            if route=='bundle/'+JID+'/'+FID:return CSV
            self.fail(route)
        with tempfile.TemporaryDirectory() as d,patch.object(app,'CACHE',Path(d)),patch.object(app,'token',return_value='fixture'),patch.object(app,'_request',side_effect=reply) as request:
            grid=app.fetch_region('NDVI',feature,2024,2024)
            cached=app.fetch_region('NDVI',feature,2024,2024)
        self.assertEqual(request.call_count,4);self.assertEqual(grid.regional_series,{202401:.5})
        self.assertTrue(cached.provenance['cache_hit']);self.assertFalse(grid.provenance['monthly_area_coverage_known'])

    def test_appeears_cancellation_deletes_its_pending_remote_task(self):
        with tempfile.TemporaryDirectory() as d,patch.object(app,'CACHE',Path(d)),patch.object(app,'token',return_value='fixture'),\
             patch.object(app,'_request',return_value={'task_id':JID,'status':'queued'}) as request,\
             patch.object(app.jobs,'check_cancelled',side_effect=ValueError('Cancelled')):
            with self.assertRaisesRegex(ValueError,'Cancelled'):app.fetch_region('NDVI',geography.resolve('focus:ghana_north'),2024,2024)
        self.assertTrue(any(c.kwargs.get('method')=='DELETE' for c in request.call_args_list))

    def test_appeears_resumes_a_saved_remote_task_after_a_server_restart(self):
        feature=geography.resolve('focus:ghana_north')
        key=hashlib.sha256(json.dumps([app.VERSION,'NDVI',feature['geometry_version'],2024,2024]).encode()).hexdigest()
        def reply(route,**kwargs):
            self.assertNotEqual(kwargs.get('method'),'POST','A restart must not submit the extraction again')
            if route in {'task/'+JID,'status/'+JID}:return {'task_id':JID,'status':'done'}
            if route=='bundle/'+JID:return {'files':[{'file_id':FID,'file_name':'MOD13A3-061-Statistics.csv'}]}
            if route=='bundle/'+JID+'/'+FID:return CSV
            self.fail(route)
        with tempfile.TemporaryDirectory() as d,patch.object(app,'CACHE',Path(d)),patch.object(app,'token',return_value='fixture'),patch.object(app,'_request',side_effect=reply):
            Path(d,key+'.pending.json').write_text(json.dumps({'task_id':JID}))
            grid=app.fetch_region('NDVI',feature,2024,2024)
            self.assertEqual(grid.regional_series[202401],.5)
            self.assertFalse(Path(d,key+'.pending.json').exists())

    def test_lightweight_appeears_progress_preserves_task_identity_and_marks_server_work(self):
        state=app.remote_status([{'task_id':JID,'updated':'2026-11-15T07:00:00','progress':{'summary':15,'details':[
            {'step':1,'desc':'Initializing','pct_complete':100},{'step':2,'desc':'Downloading','pct_complete':31}]}}],JID)
        self.assertEqual(state['status'],'processing');self.assertEqual(state['percent'],15)
        self.assertIn('NASA',state['message'])
        self.assertEqual(app.remote_status({'task_id':JID,'status':'done'},JID)['status'],'done')
        self.assertNotIn('user_id',app.remote_status({'task_id':JID,'status':'done','user_id':'fixture-private-account'},JID))
        with self.assertRaises(ValueError):app.remote_status({'task_id':FID,'status':'done'},JID)

    def test_noaa_fetch_uses_station_membership_fixed_cohort_and_cache(self):
        feature=geography._feature('fixture:noaa','Fixture','preset',{'type':'Polygon','coordinates':[[[0,0],[1,0],[1,1],[0,1],[0,0]]]})
        discovery={'count':1,'results':[{'boundingPoints':[{'coordinates':[.5,.5]}],
            'stations':[{'id':'fixture-station','name':'Fixture','dataTypes':[{'id':'TAVG'}]}]}]}
        observations=[{'STATION':'fixture-station','DATE':f'2024-{m:02}','TAVG':'25'} for m in range(1,13)]
        with tempfile.TemporaryDirectory() as d,patch.object(noaa,'CACHE',Path(d)),patch.object(noaa,'_request',side_effect=[discovery,observations]) as request:
            grid=noaa.fetch_region('STATION_TAVG',feature,2024,2024)
            cached=noaa.fetch_region('STATION_TAVG',feature,2024,2024)
        self.assertEqual(request.call_count,2);self.assertEqual(grid.provenance['station_count'],1)
        self.assertEqual(grid.regional_series[202401],25);self.assertTrue(cached.provenance['cache_hit'])
        self.assertFalse(grid.provenance['spatial_detail_available'])

    def test_noaa_requests_remain_public_and_bounded(self):
        s=session(Response(body=b'[]'))
        with patch.object(noaa.requests,'Session',return_value=s):self.assertEqual(noaa._request('data/v1',{}),[])
        self.assertNotIn('Authorization',s.get.call_args.kwargs)
        with self.assertRaisesRegex(ValueError,'smaller'):noaa.fetch_region('STATION_WIND',geography.resolve('continent:africa'),2016,2024)


if __name__=='__main__':unittest.main()
