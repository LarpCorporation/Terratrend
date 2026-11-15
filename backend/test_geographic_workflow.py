"""Regression checks for actual geography, calendar gaps and imported data."""
import csv
import io
import json
import math
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import analysis
import catalog
import data_sources
import geography
import interconnect
import jobs
import server
import spatial


def box(fid,x=0):
    return geography._feature(fid,fid,"region",{"type":"Polygon","coordinates":[[[x-.25,-.25],[x+.25,-.25],[x+.25,.25],[x-.25,.25],[x-.25,-.25]]]},"country:test")


class TestGeographicCatalog(unittest.TestCase):
    def test_bundled_ghana_is_sixteen_regions(self):
        features=geography.collection("region","country:gha")["features"]
        self.assertEqual(len(features),16)
        self.assertIn("Ashanti",[f["properties"]["name"] for f in features])
        self.assertIn("Greater Accra",[f["properties"]["name"] for f in features])

    def test_country_includes_mainland_and_disconnected_territories(self):
        au=geography.resolve("country:aus")
        self.assertEqual(au["name"],"Australia")
        self.assertLess(au["bbox"][0],114)
        self.assertGreater(au["bbox"][2],153)
        self.assertGreater(len(geography.polygons(au["geometry"])),3)

    def test_hierarchy_and_version_are_shared_with_map(self):
        gh=geography.resolve("country:gha")
        self.assertEqual(gh["parent"],"subcontinent:western_africa")
        west=geography.resolve(gh["parent"])
        self.assertEqual(west["parent"],"continent:africa")
        mapped=next(f for f in geography.collection("country","subcontinent:western_africa")["features"] if f["id"]==gh["id"])
        self.assertEqual(mapped["geometry"],gh["geometry"])
        self.assertEqual(mapped["properties"]["geometry_version"],gh["geometry_version"])

    def test_unknown_level_fails(self):
        with self.assertRaises(ValueError):geography.collection("neighborhood")

    def test_non_latin_region_names_have_distinct_stable_identifiers(self):
        self.assertNotEqual(geography.slug('中部'),geography.slug('東部'))
        self.assertEqual(geography.slug('Île de France'),'ile_de_france')


class TestSpatialWeights(unittest.TestCase):
    def test_clipping_does_not_include_the_bounding_box_corners(self):
        triangle=[(0,0),(1,0),(0,1),(0,0)]
        self.assertEqual(spatial.area(spatial.clip(triangle,(.8,.8,1,1))),0)
        self.assertGreater(spatial.area(spatial.clip(triangle,(0,0,.2,.2))),0)

    def test_holes_are_excluded_and_islands_retained(self):
        geography.initialize()
        f=box("region:test:holes")
        f["geometry"]["coordinates"].append([[-.2,-.2],[.2,-.2],[.2,.2],[-.2,.2],[-.2,-.2]])
        with patch.dict(geography._FEATURES,{f["id"]:f}):
            weights=spatial.cells(f["id"],.5,.5)
            self.assertEqual(len(weights),1)
            self.assertAlmostEqual(weights[0][2],.09,places=5)
        spatial.cells.cache_clear()

    def test_antimeridian_does_not_span_the_whole_world(self):
        f=geography._feature("region:test:dateline","Dateline","region",{"type":"Polygon","coordinates":[[[179,-1],[-179,-1],[-179,1],[179,1],[179,-1]]]})
        with patch.dict(geography._FEATURES,{f["id"]:f}):
            weights=spatial.cells(f["id"],1,1)
            self.assertTrue(all(abs(lon)>=178 for lon,lat,w in weights))
            self.assertLess(len(weights),15)
        spatial.cells.cache_clear()

    def test_weighted_mean_and_support(self):
        grid=spatial.Grid({0:{0:{200001:0}},1:{0:{200001:10}}},weights={(0,0):3,(1,0):1})
        grid.expected_weight=4
        values,support=spatial.weighted_series(grid,[200001])
        self.assertEqual(values,[2.5]);self.assertEqual(support,[4])
        grid[0][0]={}
        self.assertEqual(server.covered_region_series(grid,[200001]),[None])


class TestCalendarAndDiscovery(unittest.TestCase):
    def test_missing_month_stays_in_the_calendar(self):
        months=server.calendar_months(2000,2001)
        self.assertEqual(months[2:4],[200003,200004])
        self.assertEqual(len(months),24)

    def test_missing_year_does_not_accelerate_the_trend(self):
        months=[y*100+m for y in range(2000,2021) if y!=2010 for m in range(1,13)]
        grid={0:{0:{m:15+.1*(m//100-2000) for m in months}}}
        block=server.analyze_variable(next(v for v in catalog.CATALOG if v["id"]=="T2M"),grid,months,server._month_labels(months))
        self.assertAlmostEqual(block["overall"]["per_decade"],1.0,places=9)
        self.assertAlmostEqual(block["overall"]["t_per_decade"],1.0,places=9)

    def test_full_remote_test_family_is_used_before_discovery_filter(self):
        months=[y*100+m for y in range(2000,2020) for m in range(1,13)]
        grid={0:{0:{m:15+(i%13)*.1+i*.001 for i,m in enumerate(months)}}}
        call=[0]
        def diag(*a,**k):
            call[0]+=1
            return {"r":.7,"r_lagged":.7,"p":.009 if call[0]==1 else .5,"lag_months":2,"lead_note":"source leads by 2 months","composite":{"effect_sigma":1.0}}
        with patch.object(server,"fetch_region",return_value=grid),patch.object(interconnect,"impact_pair",side_effect=diag):
            out=server.run_teleconnections("ghana_south","T2M",start=2000,end=2019)
        self.assertGreater(out["summary"]["valid_tests"],12)
        self.assertEqual(out["teleconnections"],[])

    def test_adjusted_p_preserves_full_precision(self):
        self.assertAlmostEqual(interconnect.bh_adjusted_p(.009,[.009]+[.5]*55),.5)

    def test_joint_model_identifies_two_planted_predictors(self):
        import random
        rng=random.Random(81)
        x=[rng.gauss(0,1) for _ in range(300)];z=[rng.gauss(0,1) for _ in range(300)]
        y=[0.,0.,0.]
        for i in range(3,300):y.append(.2*y[-1]+.8*x[i-1]+.6*z[i-2]+rng.gauss(0,.1))
        out=interconnect.conditional_driver_model(y,[{"id":"x","lag":1,"values":x},{"id":"z","lag":2,"values":z}])
        self.assertTrue(out["ok"]);self.assertEqual(len(out["drivers"]),2)
        self.assertTrue(all(d["standardized_coefficient"]>0 and d["p_adjusted"]<.01 for d in out["drivers"]))

    def test_coupling_server_passes_actual_series_to_the_engine(self):
        values={m:float(i%11) for i,m in enumerate(server.calendar_months(2000,2019))}
        grid={0:{0:values}}
        with patch.object(server,"fetch_region",return_value=grid),patch.object(interconnect,"analyze_local_couplings",return_value=[]) as analyze:
            server.run_coupling_analysis("ghana_south",["T2M","PRECTOTCORR"],2000,2019)
        self.assertEqual(set(analyze.call_args.args[1]),{"T2M","PRECTOTCORR"})


class MemoryHandler(server.Handler):
    """Exercise the HTTP routing without opening a network socket."""
    def __init__(self,path,body=None):
        self.path=path
        raw=json.dumps(body).encode() if body is not None else b""
        self.headers={"Content-Length":str(len(raw))}
        self.rfile=io.BytesIO(raw)
        self.result=None

    def _json(self,status,body):
        json.dumps(body,allow_nan=False)
        self.result=(status,body)
        return self.result

    def _static(self,path):
        return self._json(404,{"error":"not found"})


class TestHttpContracts(unittest.TestCase):
    def test_other_websites_cannot_import_data_into_the_local_app(self):
        h=MemoryHandler('/api/data-sources/import',{'source':'giovanni'})
        h.headers.update({'Host':'127.0.0.1:8517','Origin':'https://example.com'})
        h.do_POST();self.assertEqual(h.result[0],403)

    def test_catalog_contains_metadata_without_serializing_all_boundaries(self):
        h=MemoryHandler('/api/catalog');h.do_GET();code,data=h.result
        self.assertEqual(code,200)
        gh=next(r for r in data['regions'] if r['id']=='country:gha')
        self.assertNotIn('geometry',gh)
        self.assertEqual(gh['level'],'country')

    def test_geography_route_returns_selectable_country_features(self):
        h=MemoryHandler('/api/geography?level=country&parent=subcontinent:western_africa');h.do_GET()
        self.assertEqual(h.result[0],200)
        self.assertTrue(any(f['id']=='country:gha' for f in h.result[1]['features']))

    def test_unknown_level_and_missing_parameters_are_errors(self):
        for path in ['/api/geography?level=invalid','/api/analyze','/api/coupling']:
            h=MemoryHandler(path);h.do_GET();self.assertEqual(h.result[0],400)

    def test_import_route_rejects_unlisted_scientific_sources(self):
        h=MemoryHandler('/api/data-sources/import',{'source':'unlisted'});h.do_POST()
        self.assertEqual(h.result[0],400)

    def test_job_route_reports_failure_without_fabricated_results(self):
        h=MemoryHandler('/api/jobs',{'operation':'analyze','region':'country:gha','variables':['T2M'],'provider':'unknown','start':2000,'end':2024});h.do_POST()
        self.assertEqual(h.result[0],202);jid=h.result[1]['id']
        deadline=time.monotonic()+2
        while jobs.get(jid)['status'] not in {'complete','failed'} and time.monotonic()<deadline:time.sleep(.01)
        status=MemoryHandler('/api/jobs/'+jid);status.do_GET()
        self.assertEqual(status.result[1]['status'],'failed');self.assertIsNone(status.result[1]['result'])


class TestCustomSelections(unittest.TestCase):
    def setUp(self):
        geography.initialize();self.temp=tempfile.TemporaryDirectory()
        self.cache=patch.object(geography,'CACHE',Path(self.temp.name));self.cache.start()
        self.features=patch.dict(geography._FEATURES,{});self.features.start()

    def tearDown(self):
        self.features.stop();self.cache.stop();self.temp.cleanup();spatial.cells.cache_clear()

    def feature(self):
        return {'type':'Feature','geometry':{'type':'Polygon','coordinates':[[[-3,4],[1,4],[1,11],[-3,11],[-3,4]]]},'properties':{'name':'Coordinate bounds','selection_kind':'bounds','center':[-1,7.5]}}

    def test_frontend_identity_and_surface_area_match_backend(self):
        body=self.feature();body['id']='custom:60fbc5bb7a895a8905ab'
        f=geography.register_custom(body)
        self.assertEqual(f['id'],body['id'])
        expected=6371.0088**2*math.radians(4)*(math.sin(math.radians(11))-math.sin(math.radians(4)))
        self.assertAlmostEqual(f['properties']['area_km2'],expected,places=3)

    def test_saved_boundary_resolves_after_an_application_restart(self):
        f=geography.register_custom(self.feature());del geography._FEATURES[f['id']]
        restored=geography.resolve(f['id'])
        self.assertEqual(restored['geometry'],f['geometry'])
        self.assertEqual(restored['level'],'custom')

    def test_self_intersection_and_spoofed_identity_are_rejected(self):
        body=self.feature();body['geometry']['coordinates']=[[[0,0],[2,2],[0,2],[2,0],[0,0]]]
        with self.assertRaisesRegex(ValueError,'crosses itself'):geography.register_custom(body)
        body=self.feature();body['id']='custom:'+'0'*20
        with self.assertRaisesRegex(ValueError,'identity'):geography.register_custom(body)

    def test_custom_geography_http_route_returns_a_real_polygon_selection(self):
        h=MemoryHandler('/api/geography/custom',self.feature());h.do_POST()
        self.assertEqual(h.result[0],201)
        self.assertIsNotNone(geography.resolve(h.result[1]['id']))
        self.assertEqual(h.result[1]['properties']['selection_kind'],'bounds')


class TestResourceImport(unittest.TestCase):
    def setUp(self):
        geography.initialize()
        self.temp=tempfile.TemporaryDirectory()
        self.store=patch.object(data_sources,"STORE",Path(self.temp.name));self.store.start()
        self.a=box("region:test:a");self.b=box("region:test:b",1)
        self.geo=patch.dict(geography._FEATURES,{self.a["id"]:self.a,self.b["id"]:self.b});self.geo.start()

    def tearDown(self):
        self.geo.stop();self.store.stop();self.temp.cleanup();spatial.cells.cache_clear()

    def payload(self,partial=False):
        out=io.StringIO();writer=csv.writer(out);writer.writerow(["lon","lat","month","value"])
        for year in range(2000,2025):
            for month in range(1,13):
                writer.writerow([0,0,f"{year}-{month:02}",10+.1*(year-2000)])
                if not partial:writer.writerow([1,0,f"{year}-{month:02}",10-.1*(year-2000)])
        return {"source":"giovanni","name":"Test-only analytic fixture","citation":"Synthetic test data; not a scientific observation","variable":"T2M","unit":"°C","dlon":.5,"dlat":.5,"csv":out.getvalue()}

    def test_imported_grid_drives_real_polygon_analysis_and_paired_comparison(self):
        imported=data_sources.import_csv(self.payload())
        token=data_sources.PROVIDER.set(imported["id"])
        try:out=server.run_analysis(["T2M"],self.a["id"],2000,2024,compare_region=self.b["id"])
        finally:data_sources.PROVIDER.reset(token)
        self.assertAlmostEqual(out["series"][0]["overall"]["per_decade"],1.,places=6)
        self.assertAlmostEqual(out["compare"]["series"][0]["overall"]["per_decade"],-1.,places=6)
        self.assertTrue(out["compare"]["contrasts"][0]["diff_significant"])
        self.assertEqual(out["series"][0]["provenance"]["source"],"Giovanni")

    def test_custom_boundary_in_job_uses_the_same_scientific_pipeline(self):
        imported=data_sources.import_csv(self.payload())
        body={'type':'Feature','geometry':self.a['geometry'],'properties':{'name':'Drawn test area','selection_kind':'lasso','center':[0,0]}}
        with patch.object(geography,'CACHE',Path(self.temp.name)/'geography'):
            feature=geography.register_custom(body,persist=False)
            h=MemoryHandler('/api/jobs',{'operation':'analyze','region':feature['id'],'custom_areas':[feature],'variables':['T2M'],'provider':imported['id'],'start':2000,'end':2024});h.do_POST()
            self.assertEqual(h.result[0],202);jid=h.result[1]['id'];deadline=time.monotonic()+3
            while jobs.get(jid)['status'] in {'running','queued'} and time.monotonic()<deadline:time.sleep(.01)
            out=jobs.get(jid);self.assertEqual(out['status'],'complete',out.get('error'))
            self.assertEqual(out['result']['region']['id'],feature['id'])
            self.assertAlmostEqual(out['result']['series'][0]['overall']['per_decade'],1.,places=6)

    def test_absent_spatial_data_cannot_be_presented_as_a_trend(self):
        imported=data_sources.import_csv(self.payload(partial=True));token=data_sources.PROVIDER.set(imported["id"])
        try:out=server.run_analysis(["T2M"],self.b["id"],2000,2024)
        finally:data_sources.PROVIDER.reset(token)
        self.assertFalse(out["series"][0]["overall"]["ok"])
        self.assertEqual(out["series"][0]["provenance"]["available_area_fraction"],0)

    def test_unlisted_source_and_wrong_units_are_rejected(self):
        for values in [{"source":"unlisted"},{"unit":"K"}]:
            body=self.payload();body.update(values)
            with self.assertRaises(ValueError):data_sources.import_csv(body)

    def test_duplicate_months_and_nonfinite_values_are_rejected(self):
        for csvtext in ["lon,lat,month,value\n0,0,2000-01,1\n0,0,2000-01,2", "lon,lat,month,value\n0,0,2000-01,nan"]:
            body=self.payload();body["csv"]=csvtext
            with self.assertRaises(ValueError):data_sources.import_csv(body)

    def test_fill_values_and_blanks_never_enter_a_trend(self):
        body=self.payload();body["csv"]="lon,lat,month,value\n0,0,2000-01,10\n0,0,2000-02,-9999\n0,0,2000-03,\n0,0,2000-04,12"
        imported=data_sources.import_csv(body)
        saved=json.loads((data_sources.STORE/(imported["id"]+".json")).read_text())
        self.assertEqual(list(saved["records"]["0.000000,0.000000"]),["200001","200004"])

    def test_irregular_points_cannot_masquerade_as_native_grid_cells(self):
        body=self.payload();body["csv"]="lon,lat,month,value\n0,0,2000-01,10\n0.1,0.1,2000-01,12"
        with self.assertRaisesRegex(ValueError,"grid spacing"):data_sources.import_csv(body)


class TestJobs(unittest.TestCase):
    def test_identical_jobs_are_deduplicated_and_results_returned(self):
        import threading
        gate=threading.Event();calls=[]
        def fn():gate.wait(1);calls.append(1);return {"ok":True}
        spec={"test":time.monotonic()}
        a=jobs.submit(spec,fn);b=jobs.submit(spec,fn);self.assertEqual(a["id"],b["id"]);gate.set()
        deadline=time.monotonic()+2
        while jobs.get(a["id"])["status"]!="complete" and time.monotonic()<deadline:time.sleep(.01)
        self.assertEqual(jobs.get(a["id"])["result"],{"ok":True});self.assertEqual(len(calls),1)

    def test_cancelled_job_does_not_publish_late_results(self):
        import threading
        gate=threading.Event();started=threading.Event();ended=threading.Event()
        def fn():started.set();gate.wait(1);ended.set();return {"late":True}
        job=jobs.submit({"cancel_test":time.monotonic()},fn);started.wait(1);jobs.cancel(job["id"]);gate.set();ended.wait(1)
        self.assertEqual(jobs.get(job["id"])["status"],"cancelled");self.assertIsNone(jobs.get(job["id"])["result"])


if __name__=="__main__":unittest.main()
