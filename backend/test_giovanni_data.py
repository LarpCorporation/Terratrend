"""Giovanni rectangle mode: real service schema, fixture observations."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import catalog
import data_sources
import geography
import nasa_data
import server


BOX = {"id": "test-box", "geometry_version": "box-v1", "bbox": [-2, 6, 0, 8],
       "geometry": {"type": "Polygon", "coordinates": [[[-2, 6], [0, 6], [0, 8], [-2, 8], [-2, 6]]]}}
JOB = "12345678-1234-1234-1234-123456789abc"


def csv_values(variable="T2M", start=2005, end=2016):
    rows = ['User Start Date:,'+str(start)+'-01-01T00:00:00Z',
            'User End Date:,'+str(end)+'-12-31T23:59:59Z',
            'User Bounding Box:,"-2, 6, 0, 8"', 'Fill Value:,-9999.900390625', ',',
            'time,mean_M2IMNXASM_5_12_4_'+variable]
    for year in range(start, end+1):
        for month in range(1, 13): rows.append(f'{year}-{month:02}-01T00:00:00,{283.15+(year-start)*.1}')
    return ('\n'.join(rows)+'\n').encode()


class TestGiovanniData(unittest.TestCase):
    def test_rectangular_lasso_and_coordinate_bounds_are_accepted_by_geometry(self):
        from giovanni_data import rectangle
        self.assertEqual(rectangle(BOX), (-2, 6, 0, 8))

    def test_triangles_circles_holes_multipart_and_countries_are_not_changed_to_boxes(self):
        from giovanni_data import rectangle
        import copy
        for coordinates in ([[[-2, 6], [0, 6], [-1, 8], [-2, 6]]],
                            [[[-2, 6], [-.5, 6], [0, 7], [-1, 8], [-2, 6]]],
                            BOX['geometry']['coordinates']+[[[-1, 7], [-.5, 7], [-1, 7.5], [-1, 7]]]):
            feature=copy.deepcopy(BOX);feature['geometry']['coordinates']=coordinates
            with self.assertRaisesRegex(ValueError, 'rectangle|native'): rectangle(feature)
        with self.assertRaises(ValueError): rectangle(geography.resolve('country:gha'))

    def test_harmony_request_uses_area_average_full_period_and_no_point_sampling(self):
        from giovanni_data import request_url
        url=request_url('T2M', BOX, 2005, 2024);q=parse_qs(urlparse(url).query)
        self.assertIn('C1276812823-GES_DISC', url)
        self.assertEqual(q['average'], ['area']);self.assertEqual(q['format'], ['text/csv'])
        self.assertEqual(q['variable'], ['M2IMNXASM_5_12_4_T2M'])
        self.assertTrue(any('2024-12-31' in v for v in q['subset']))
        self.assertNotIn('point', q);self.assertNotIn('maxResults',q)
        with self.assertRaisesRegex(ValueError, 'not supported'): request_url('GWETROOT', BOX, 2005, 2024)

    def test_monthly_csv_scaling_fill_and_missing_months(self):
        from giovanni_data import decode_csv
        values=decode_csv(csv_values(), 'T2M', BOX['bbox'], 2005, 2016)
        self.assertAlmostEqual(values[200501], 10.)
        self.assertAlmostEqual(values[201612], 11.1)
        raw=csv_values().replace(b'2005-01-01T00:00:00,283.15', b'2005-01-01T00:00:00,-9999.900390625')
        self.assertIsNone(decode_csv(raw, 'T2M', BOX['bbox'], 2005, 2016)[200501])

    def test_csv_requires_requested_measurement_rectangle_monthly_cadence_and_unique_dates(self):
        from giovanni_data import decode_csv
        for raw in [b'<html>login</html>', csv_values('QV2M'),
                    csv_values().replace(b'"-2, 6, 0, 8"', b'"-3, 6, 0, 8"'),
                    csv_values()+b'2005-01-01T12:00:00,284\n',
                    csv_values().replace(b'2005-02-01T00:00:00', b'2005-01-02T00:00:00')]:
            with self.subTest(size=len(raw)):
                with self.assertRaises(ValueError): decode_csv(raw, 'T2M', BOX['bbox'], 2005, 2016)

    def test_cached_regional_series_keep_charts_and_comparison_statistics_without_fake_cells(self):
        import giovanni_data as gio
        with tempfile.TemporaryDirectory() as folder, patch.object(gio,'CACHE',Path(folder)), \
             patch.object(nasa_data,'token',return_value='session-token'), \
             patch.object(gio,'run_remote',return_value=(csv_values(), JOB)) as remote:
            grid=gio.fetch_region('T2M',BOX,2005,2016)
            again=gio.fetch_region('T2M',BOX,2005,2016)
        self.assertEqual(remote.call_count,1)
        self.assertTrue(again.provenance['cache_hit'])
        self.assertEqual(again.provenance['retrieved_utc'],grid.provenance['retrieved_utc'])
        months=server.calendar_months(2005,2016)
        block=server.analyze_variable(next(v for v in catalog.CATALOG if v['id']=='T2M'),grid,months,server._month_labels(months))
        self.assertTrue(block['overall']['ok']);self.assertAlmostEqual(block['overall']['per_decade'],1.)
        self.assertEqual(block['cells'],[])
        self.assertFalse(block['summary']['spatial_detail_available'])
        self.assertNotIn('available_area_fraction',block['provenance'])
        self.assertEqual(block['provenance']['dataset'],'M2IMNXASM')
        self.assertEqual(len(block['monthly_timeseries']),144)

    def test_provider_is_optional_and_advertises_only_verified_mappings(self):
        provider=next(p for p in data_sources.providers() if p['id']=='nasa-giovanni')
        self.assertEqual(provider['variables'],['T2M','QV2M','T10M','QV10M'])
        self.assertEqual(provider['geometry'],'rectangle')

    def test_additional_ten_metre_fields_preserve_source_height_and_conversion(self):
        import giovanni_data as g
        self.assertIn('T10M',g.FIELDS)
        self.assertIn('QV10M',g.FIELDS)
        q=parse_qs(urlparse(g.request_url('T10M',BOX,2005,2024)).query)
        self.assertEqual(q['variable'],['M2IMNXASM_5_12_4_T10M'])
        self.assertAlmostEqual(g.decode_csv(csv_values('T10M'),'T10M',BOX['bbox'],2005,2016)[200501],10.)
        self.assertEqual(data_sources.providers()[0]['id'],'auto')

    def test_polygon_validation_happens_before_earthdata_or_remote_processing(self):
        import giovanni_data as gio
        with patch.object(gio,'run_remote') as remote:
            with self.assertRaises(ValueError): gio.fetch_region('T2M',geography.resolve('country:gha'),2005,2016)
            remote.assert_not_called()

    def test_regional_provider_rejects_layer_and_interconnection_jobs_without_download_fallback(self):
        with patch.object(nasa_data,'token',return_value='session-token'):
            for operation in ['overview','interconnections']:
                with self.subTest(operation=operation):
                    with self.assertRaisesRegex(ValueError,'native|rectangle'):
                        server.execute_job({'operation':operation,'provider':'nasa-giovanni','variables':['T2M'],
                                            'region':'country:gha','start':2005,'end':2016})

    def test_remote_job_polling_and_output_allowlist(self):
        import giovanni_data as gio
        output='https://harmony-prod-public.s3.us-west-2.amazonaws.com/public/gesdisc/giovanni/result.csv?X-Amz-Signature=temporary'
        with patch.object(gio,'_request',side_effect=[json.dumps({'jobID':JOB,'status':'running'}).encode(),
             json.dumps({'jobID':JOB,'status':'successful','links':[{'rel':'data','type':'text/csv','href':output}]}).encode(),csv_values()]) as req:
            raw,jid=gio.run_remote('T2M',BOX,2005,2016,'session-token')
        self.assertEqual(raw,csv_values());self.assertEqual(jid,JOB)
        self.assertEqual(req.call_args_list[-1].kwargs.get('bearer',''),'')
        with patch.object(gio,'_request',side_effect=[json.dumps({'jobID':JOB,'status':'successful','links':[
            {'rel':'data','type':'text/csv','href':'https://example.com/result.csv'}]}).encode()]):
            with self.assertRaises(ValueError): gio.run_remote('T2M',BOX,2005,2016,'session-token')

    def test_live_harmony_schema_identifies_csv_by_filename_when_type_is_geotiff_csv(self):
        import giovanni_data as gio
        output=gio.BASE+'/service-results/harmony-prod-staging/public/'+JOB+'/result.csv'
        reply=json.dumps({'jobID':JOB,'status':'successful','links':[{'rel':'data','type':'GEOTIFF/CSV','href':output}]}).encode()
        with patch.object(gio,'_request',side_effect=[reply,csv_values()]) as request:
            self.assertEqual(gio.run_remote('T2M',BOX,2005,2016,'session-token')[0],csv_values())
        self.assertEqual(request.call_args.kwargs.get('bearer'),'session-token')

    def test_transport_limits_token_destinations_and_does_not_follow_login_redirects(self):
        import giovanni_data as gio
        from test_nasa_data import Session,Response
        for code in [401,302]:
            with patch.object(gio.requests,'Session',return_value=Session(Response(code))):
                with self.assertRaises(nasa_data.EarthdataRequired): gio._request(gio.BASE+'/jobs/'+JOB,bearer='private')
        with patch.object(gio.requests,'Session') as session:
            with self.assertRaises(ValueError): gio._request('https://example.com/data',bearer='private')
            session.assert_not_called()

    def test_successful_transport_omits_tokens_for_results_and_bounds_response_size(self):
        import giovanni_data as gio
        from test_nasa_data import Session,Response
        output='https://harmony-prod-public.s3.us-west-2.amazonaws.com/public/gesdisc/giovanni/result.csv'
        session=Session(Response(body=csv_values()))
        with patch.object(gio.requests,'Session',return_value=session):
            self.assertEqual(gio._request(output),csv_values())
        self.assertNotIn('Authorization',session.calls[0][1]['headers'])
        for response in [Response(500),Response(body=b'x'*2_000_001)]:
            with patch.object(gio.requests,'Session',return_value=Session(response)):
                with self.assertRaises(ValueError):gio._request(output)
        with self.assertRaises(ValueError):gio._request(output,bearer='must-stay-at-nasa')

    def test_harmony_job_redirect_is_processing_not_a_login_failure(self):
        import giovanni_data as gio
        from test_nasa_data import Session,Response
        class RedirectSession(Session):
            def __init__(self,responses): super().__init__(None);self.responses=iter(responses)
            def get(self,url,**kwargs): self.calls.append((url,kwargs));return next(self.responses)
        session=RedirectSession([Response(303,headers={'Location':'/jobs/'+JOB}),Response(body=b'{"jobID":"'+JOB.encode()+b'"}')])
        with patch.object(gio.requests,'Session',return_value=session):
            body=gio._request(gio.BASE+'/request',bearer='session-token')
        self.assertEqual(json.loads(body)['jobID'],JOB)
        self.assertEqual(len(session.calls),2)
        self.assertEqual(session.calls[1][1]['headers']['Authorization'],'Bearer session-token')
        output='https://harmony-prod-public.s3.us-west-2.amazonaws.com/public/gesdisc/giovanni/result.csv?X-Amz-Signature=temporary'
        session=RedirectSession([Response(303,headers={'Location':output}),Response(body=csv_values())])
        with patch.object(gio.requests,'Session',return_value=session):
            self.assertEqual(gio._request(gio.BASE+'/service-results/result',bearer='session-token'),csv_values())
        self.assertNotIn('Authorization',session.calls[1][1]['headers'])
        cdn='https://dqzb5lcolc8fj.cloudfront.net/s3-ed54538b88f6e9fc0ec110d0f71c8fa0/harmony-prod-staging.s3.us-west-2.amazonaws.com/public/'+JOB+'/result.csv'
        session=RedirectSession([Response(307,headers={'Location':cdn}),Response(body=csv_values())])
        with patch.object(gio.requests,'Session',return_value=session):
            self.assertEqual(gio._request(gio.BASE+'/service-results/result',bearer='session-token'),csv_values())
        self.assertNotIn('Authorization',session.calls[1][1]['headers'])

    def test_redirects_to_earthdata_login_are_not_followed_with_credentials(self):
        import giovanni_data as gio
        from test_nasa_data import Session,Response
        session=Session(Response(303,headers={'Location':'https://urs.earthdata.nasa.gov/oauth/authorize'}))
        with patch.object(gio.requests,'Session',return_value=session):
            with self.assertRaises(nasa_data.EarthdataRequired):gio._request(gio.BASE+'/jobs/'+JOB,bearer='private')
        self.assertEqual(len(session.calls),1)

    def test_failed_and_cancelled_remote_jobs_do_not_publish_or_trigger_native_downloads(self):
        import giovanni_data as gio
        failed=json.dumps({'jobID':JOB,'status':'failed'}).encode()
        with patch.object(gio,'_request',side_effect=[failed,b'{}']) as request:
            with self.assertRaises(ValueError):gio.run_remote('T2M',BOX,2005,2016,'session-token')
        self.assertTrue(request.call_args.args[0].endswith('/cancel'))
        running=json.dumps({'jobID':JOB,'status':'running'}).encode()
        with patch.object(gio,'_request',side_effect=[running,b'{}']) as request, \
             patch.object(gio.jobs,'check_cancelled',side_effect=ValueError('Cancelled')):
            with self.assertRaisesRegex(ValueError,'Cancelled'):gio.run_remote('T2M',BOX,2005,2016,'session-token')
        self.assertTrue(request.call_args.kwargs['cancel'])
        with patch.object(gio,'_request',return_value=b'{"jobID":"invalid"}'):
            with self.assertRaises(ValueError):gio.run_remote('T2M',BOX,2005,2016,'session-token')

    def test_humidity_conversion_and_incomplete_year_exclusion(self):
        import giovanni_data as gio
        raw=csv_values('QV2M').replace(b'283.15',b'0.012')
        self.assertAlmostEqual(gio.decode_csv(raw,'QV2M',BOX['bbox'],2005,2016)[200501],12.)
        values=gio.decode_csv(csv_values(),'T2M',BOX['bbox'],2005,2016);values[200501]=None
        grid=gio.RegionalSeries(values,{'provider':'nasa-giovanni','dataset':'M2IMNXASM','field':'T2M'})
        months=server.calendar_months(2005,2016)
        block=server.analyze_variable(next(v for v in catalog.CATALOG if v['id']=='T2M'),grid,months,server._month_labels(months))
        self.assertEqual(block['overall']['n'],11)
        self.assertFalse(block['yearly_timeseries'][0]['complete'])

    def test_two_rectangles_keep_independent_series_and_paired_common_years(self):
        import giovanni_data as gio
        import copy
        a=geography.register_custom({'geometry':BOX['geometry'],'properties':{'name':'Box A','selection_kind':'bounds'}},persist=False)
        shifted=copy.deepcopy(BOX['geometry'])
        for point in shifted['coordinates'][0]:point[0]+=.5
        b=geography.register_custom({'geometry':shifted,'properties':{'name':'Box B','selection_kind':'bounds'}},persist=False)
        values=gio.decode_csv(csv_values(),'T2M',BOX['bbox'],2005,2016)
        def fetch(variable,feature,start,end):
            offset=1 if feature['id']==b['id'] else 0
            return gio.RegionalSeries({m:v+offset for m,v in values.items()},
                {'provider':'nasa-giovanni','dataset':'M2IMNXASM','field':'T2M','spatial_detail_available':False})
        with patch.object(nasa_data,'token',return_value='session-token'),patch.object(data_sources,'fetch_region',side_effect=fetch):
            result=server.execute_job({'operation':'analyze','provider':'nasa-giovanni','variables':['T2M'],
                'region':a['id'],'compare_region':b['id'],'start':2005,'end':2016})
        primary=result['series'][0];comparison=result['compare']['series'][0]
        self.assertEqual(primary['overall']['n'],12)
        self.assertAlmostEqual(comparison['monthly_timeseries'][0]['value']-primary['monthly_timeseries'][0]['value'],1.)
        self.assertEqual(primary['cells'],[]);self.assertEqual(comparison['cells'],[])
        self.assertEqual(len(result['compare']['contrasts']),1)
