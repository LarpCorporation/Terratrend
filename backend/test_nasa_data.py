"""Automatic data acquisition: actual NetCDF fixtures, no external credentials."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import data_sources
import jobs
import nasa_data


def netcdf(variable="T2M", units="K", values=((283.15, -9999),), lons=(0, .625)):
    from netCDF4 import Dataset
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/"fixture.nc4"
        with Dataset(path,"w") as data:
            data.createDimension("time",1);data.createDimension("lat",len(values));data.createDimension("lon",len(lons))
            data.createVariable("lat","f8",("lat",))[:]=np.arange(len(values))*.5
            data.createVariable("lon","f8",("lon",))[:]=lons
            field=data.createVariable(nasa_data.FIELDS[variable][1],"f8",("time","lat","lon"),fill_value=-9999)
            field.units=units;field[:]=[values]
        return path.read_bytes()


class Response:
    def __init__(self,code=200,body=b"ok",headers=None):self.status_code=code;self.body=body;self.headers=headers or {}
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def iter_content(self,_):yield self.body


class Session:
    def __init__(self,response):self.response=response;self.calls=[]
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def get(self,url,**kwargs):self.calls.append((url,kwargs));return self.response


class TestNASAData(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.cache=patch.object(nasa_data,"CACHE",Path(self.temp.name));self.cache.start()
        self.env=patch.dict(os.environ,{"EARTHDATA_TOKEN":""});self.env.start()
        self.old_token=nasa_data._TOKEN;nasa_data._TOKEN=""

    def tearDown(self):
        nasa_data._TOKEN=self.old_token;self.env.stop();self.cache.stop();self.temp.cleanup()

    def test_login_is_required_before_any_observation_work(self):
        with patch.object(nasa_data,"granules") as discovery:
            with self.assertRaisesRegex(nasa_data.EarthdataRequired,"no CSV upload"):
                nasa_data.fetch_region("GWETROOT",{},2005,2024)
            discovery.assert_not_called()

    def test_temperature_units_and_provider_fill_mask(self):
        values=nasa_data.decode_subset(netcdf(),"T2M",(180,180,288,289))
        self.assertAlmostEqual(values[0,0],10.,places=8)
        self.assertTrue(np.isnan(values[0,1]))

    def test_flux_humidity_pressure_and_wetness_units(self):
        for variable,unit,raw,expected in [("EVLAND","kg m-2 s-1",1e-5,.864),("PRECTOTCORR","kg m-2 s-1",2e-5,1.728),
                                         ("QV2M","kg kg-1",.012,12.),("PS","Pa",101325,101.325),("GWETROOT","1",.5,.5)]:
            with self.subTest(variable=variable):
                result=nasa_data.decode_subset(netcdf(variable,unit,((raw,),),(0,)),variable,(180,180,288,288))
                self.assertAlmostEqual(result[0,0],expected,places=8)

    def test_wrong_units_and_shifted_grid_are_rejected(self):
        with self.assertRaisesRegex(ValueError,"units differ"):
            nasa_data.decode_subset(netcdf(units="C"),"T2M",(180,180,288,289))
        with self.assertRaisesRegex(ValueError,"native"):
            nasa_data.decode_subset(netcdf(lons=(.3125,.9375)),"T2M",(180,180,288,289))
        with self.assertRaisesRegex(ValueError,"login/error page"):
            nasa_data.decode_subset(b"<html>Login</html>","T2M",(180,180,288,288))

    def test_dateline_cells_use_two_small_windows(self):
        points=[(-180,0,1),(-179.375,0,1),(179.375,0,1)]
        windows=nasa_data.windows(points)
        self.assertEqual(windows,[(180,180,575,575),(180,180,0,1)])
        self.assertEqual(nasa_data.windows([(0,0,1)]),[(180,180,288,288)])

    def test_subset_url_is_bounded_native_resolution(self):
        row={"url":"https://opendap.earthdata.nasa.gov/collections/C123/granules/M2TMNXSLV.5.12.4%3Areal.nc4"}
        from urllib.parse import parse_qs,urlparse,unquote
        url=nasa_data.subset_url(row,"T2M",(180,181,288,290))
        self.assertEqual(parse_qs(urlparse(url).query)["dap4.ce"],["/T2M[0:1:0][180:1:181][288:1:290];/lat[180:1:181];/lon[288:1:290]"])
        self.assertIn("%253A",url)
        self.assertIn("M2TMNXSLV.5.12.4:real.nc4",unquote(unquote(url)))
        with self.assertRaises(ValueError):nasa_data.subset_url({"url":"https://evil.example/granules/file"},"T2M",(0,0,0,0))

    def test_authentication_redirect_and_401_have_actionable_errors(self):
        for response in [Response(302,headers={"Location":"/login/urs"}),Response(401),Response(403)]:
            with patch.object(nasa_data.requests,"Session",return_value=Session(response)):
                with self.assertRaisesRegex(nasa_data.EarthdataRequired,"Connect Earthdata"):
                    nasa_data._request("https://opendap.earthdata.nasa.gov/test")

    def test_token_only_goes_to_the_data_host_and_never_the_url(self):
        session=Session(Response())
        with patch.object(nasa_data.requests,"Session",return_value=session):
            nasa_data._request("https://cmr.earthdata.nasa.gov/test", "secret-value")
            self.assertNotIn("Authorization",session.calls[0][1]["headers"])
            nasa_data._request("https://opendap.earthdata.nasa.gov/test", "secret-value")
        self.assertNotIn("secret-value",session.calls[1][0])
        self.assertEqual(session.calls[1][1]["headers"]["Authorization"],"Bearer secret-value")
        with self.assertRaisesRegex(ValueError,"destination"):nasa_data._request("https://evil.example/", "secret-value")

    def test_cmr_uses_published_months_and_latest_revision_without_filling_gaps(self):
        def entry(month,revision):
            return {"id":"G"+month+revision,"title":"MERRA2 "+month,"time_start":month+"-01T00:00:00Z","updated":revision,
                    "links":[{"href":"https://opendap.earthdata.nasa.gov/collections/C/granules/"+month}]}
        body=json.dumps({"feed":{"entry":[entry("2024-01","1"),entry("2024-03","1"),entry("2024-01","2")]}}).encode()
        with patch.object(nasa_data,"_request",return_value=body) as request:
            rows=nasa_data.granules("M2TMNXSLV",2024,2024)
            self.assertEqual([r["month"] for r in rows],[202401,202403]);self.assertEqual(rows[0]["updated"],"2")
            self.assertEqual(nasa_data.granules("M2TMNXSLV",2024,2024),rows)
            self.assertEqual(request.call_count,1)

    def test_validated_subsets_are_reused_without_another_download(self):
        row={"id":"G123","updated":"2024-02-01","url":"https://opendap.earthdata.nasa.gov/collections/C/granules/test.nc4"}
        with patch.object(nasa_data,"_request",return_value=netcdf()) as request:
            first,hit=nasa_data.download_month(row,"T2M",(180,180,288,289),"private-token")
            self.assertFalse(hit)
            second,hit=nasa_data.download_month(row,"T2M",(180,180,288,289),"private-token")
            self.assertTrue(hit);self.assertEqual(request.call_count,1)
            np.testing.assert_allclose(first,second)
        for path in Path(self.temp.name).rglob("*"):
            if path.is_file():self.assertNotIn(b"private-token",path.read_bytes())

    def test_polygon_cells_missing_months_and_provenance_survive_automatic_fetch(self):
        nasa_data._TOKEN="session-test"
        rows=[{"id":"G1","month":200501,"title":"first","updated":"1"},{"id":"G2","month":200503,"title":"third","updated":"1"}]
        def download(row,variable,window,bearer):return np.array([[.5]]) if window[2]==575 else np.array([[.8,np.nan]]),False
        planned=[(-180,0,1),(-179.375,0,1),(179.375,0,1)]
        with patch.object(nasa_data.spatial,"cells",return_value=planned),patch.object(nasa_data,"granules",return_value=rows),patch.object(nasa_data,"download_month",side_effect=download):
            grid=nasa_data.fetch_region("GWETROOT",{"id":"test","geometry_version":"v1"},2005,2024)
        self.assertEqual(grid[-180][0],{200501:.8,200503:.8});self.assertNotIn(-179.375,grid)
        self.assertEqual(grid.expected_weight,3)
        self.assertAlmostEqual(grid.provenance["available_area_fraction"],2/3)
        self.assertEqual(grid.provenance["dataset"],"M2TMNXLND");self.assertEqual(grid.provenance["last_observed_month"],200503)
        self.assertEqual(grid.provenance["requested_months"],240);self.assertEqual(len(grid.provenance["granules"]),2)

    def test_connection_only_keeps_a_verified_token_in_server_memory(self):
        row={"url":"https://opendap.earthdata.nasa.gov/collections/C/granules/file.nc4"}
        with patch.object(nasa_data,"granules",return_value=[row]),patch.object(nasa_data,"_request",return_value=netcdf(values=((283.15,),),lons=(0,))):
            result=nasa_data.connect("a-private-session-token-123")
        self.assertTrue(result["verified"]);self.assertTrue(nasa_data.status()["configured"])
        self.assertNotIn("a-private-session-token-123",json.dumps(nasa_data.status()))
        self.assertEqual(list(Path(self.temp.name).iterdir()),[])
        nasa_data.disconnect();self.assertFalse(nasa_data.status()["configured"])

    def test_cancelled_job_never_downloads_a_subset(self):
        context=jobs._CURRENT.set({"status":"cancelled"})
        try:
            with patch.object(nasa_data,"_request") as request:
                with self.assertRaisesRegex(ValueError,"Cancelled"):
                    nasa_data.download_month({"id":"G1","updated":"1"},"T2M",(180,180,288,288),"token")
                request.assert_not_called()
        finally:jobs._CURRENT.reset(context)

    def test_partial_legacy_cache_preserves_real_months_and_missing_years(self):
        path=Path(self.temp.name)/"point.json";path.write_text(json.dumps({"data":{"201001":25,"201002":26,"201013":99,"201101":27}}))
        provider=data_sources.PROVIDER.set("project-cache")
        try:
            with patch.object(data_sources,"_cache_index",return_value={("T2M",0,0):[(2010,2011,path)]}),patch.object(data_sources.spatial,"cells",return_value=[(0,0,1)]):
                grid=data_sources.fetch_region("T2M",{"id":"test","geometry_version":"v1"},2005,2026)
            self.assertEqual(sorted(grid[0][0]),[201001,201002,201101]);self.assertNotIn(200501,grid[0][0])
        finally:data_sources.PROVIDER.reset(provider)

    def test_automatic_source_reaches_the_existing_trend_engine(self):
        import server
        nasa_data._TOKEN="session-test"
        feature={"id":"test","name":"Test polygon","level":"custom","bbox":[-.2,-.2,.2,.2],"geometry_version":"v1",
                 "geometry":{"type":"Polygon","coordinates":[[[-.2,-.2],[.2,-.2],[.2,.2],[-.2,.2],[-.2,-.2]]]}}
        rows=[{"id":f"G{y}{m:02}","month":y*100+m,"title":"fixture","updated":"1"} for y in range(2000,2011) for m in range(1,13)]
        def download(row,*_):
            year,month=divmod(row["month"],100)
            return np.array([[20.+.1*(year-2000)+np.sin(month*np.pi/6)]]),False
        with patch.object(server,"resolve_region",return_value=feature),patch.object(nasa_data.spatial,"cells",return_value=[(0,0,1)]),patch.object(nasa_data,"granules",return_value=rows),patch.object(nasa_data,"download_month",side_effect=download):
            result=server.execute_job({"operation":"analyze","provider":"nasa-merra2","region":"test","variables":["T2M"],"start":2000,"end":2010})
        block=result["series"][0]
        self.assertTrue(block["overall"]["ok"]);self.assertTrue(block["overall"]["significant"])
        self.assertAlmostEqual(block["overall"]["per_decade"],1.,places=5)
        self.assertEqual(block["variable"]["mission"],"MERRA-2")
        self.assertEqual(block["provenance"]["dataset"],"M2TMNXSLV")
        self.assertEqual(result["window"]["last_month"],"2010-12")
