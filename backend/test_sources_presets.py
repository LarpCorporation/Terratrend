"""New source and geographic contracts; all observation values here are fixtures."""
import unittest
import geography
import spatial
from unittest.mock import patch


class TestFocusPresets(unittest.TestCase):
    def test_named_presets_are_real_selectable_rectangles_with_stable_ids(self):
        data = geography.collection('preset')
        self.assertGreaterEqual(len(data['features']), 20)
        savannah = next(f for f in data['features'] if f['id']=='focus:ghana_north')
        self.assertIn('Savannah', savannah['properties']['name'])
        self.assertEqual(savannah['geometry']['type'], 'Polygon')
        self.assertEqual(savannah['properties']['level'], 'preset')
        self.assertIn('box', savannah['properties']['boundary_source'].lower())
        self.assertEqual(geography.resolve('focus:ghana_north')['geometry'],savannah['geometry'])

    def test_shifted_native_grid_retains_actual_source_centres(self):
        f=geography._feature('fixture:grid','Fixture','preset',{'type':'Polygon','coordinates':[[[0,0],[.5,0],[.5,.5],[0,.5],[0,0]]]})
        from unittest.mock import patch
        with patch.dict(geography._FEATURES,{f['id']:f}):
            cells=spatial.cells(f['id'],.25,.25,-179.875,-59.875)
        self.assertEqual({(x,y) for x,y,w in cells},{(.125,.125),(.125,.375),(.375,.125),(.375,.375)})
        self.assertAlmostEqual(sum(w for x,y,w in cells),.25,places=4)
        spatial.cells.cache_clear()


class TestSourceLinking(unittest.TestCase):
    def test_station_summaries_are_not_published_as_whole_country_layer_values(self):
        import server
        with patch.object(server,'run_analysis') as analyze:
            with self.assertRaisesRegex(ValueError,'[Ss]tation'):
                server.execute_job({'operation':'overview','provider':'noaa-cdo','region':'country:gha','features':['country:gha'],
                    'variables':['STATION_TAVG'],'start':2016,'end':2024})
        analyze.assert_not_called()

    def test_giovanni_can_analyze_a_disclosed_batch_of_preset_rectangles(self):
        import server,data_sources
        with patch.object(data_sources.nasa_data,'token',return_value='fixture'),patch.object(server,'run_analysis',return_value={'series':[{'overall':{'ok':True},'summary':{},'provenance':{}}]}) as analyze:
            out=server.execute_job({'operation':'overview','provider':'nasa-giovanni','region':'focus:ghana_north',
                'features':['focus:ghana_north','focus:congo'],'variables':['T2M'],'start':2016,'end':2024})
        self.assertEqual(len(out['rows']),2);self.assertEqual(analyze.call_count,2)

    def test_linked_mode_routes_each_measurement_to_its_actual_provider(self):
        import data_sources as d
        f=geography.resolve('country:gha')
        with patch.object(d.nasa_data,'fetch_region',return_value='soil') as soil,\
             patch.object(d.appeears_data,'fetch_region',return_value='vegetation') as veg:
            token=d.PROVIDER.set('multi-source')
            try:
                self.assertEqual(d.fetch_region('GWETROOT',f,2005,2024),'soil')
                self.assertEqual(d.fetch_region('NDVI',f,2005,2024),'vegetation')
            finally:d.PROVIDER.reset(token)
        soil.assert_called_once();veg.assert_called_once()

    def test_local_interconnections_do_not_launch_remote_requests_and_keep_series_only_data(self):
        import server,data_sources
        from giovanni_data import RegionalSeries
        values={m:float(i%13) for i,m in enumerate(server.calendar_months(2005,2024))}
        region=geography.resolve('country:gha')
        with patch.object(server,'fetch_region',return_value=RegionalSeries(values,{'source':'Fixture','dataset':'Fixture','field':'fixture'})),\
             patch.object(server,'run_teleconnections') as remote,patch.object(data_sources.nasa_data,'token',return_value='fixture-key'):
            result=server.execute_job({'operation':'interconnections','provider':'multi-source','region':region['id'],
                'variables':['GWETROOT'],'relationship_variables':['GWETROOT','NDVI'],'relationship_scope':'local','start':2005,'end':2024})
        remote.assert_not_called()
        self.assertEqual(set(result['local']['provenance']),{'GWETROOT','NDVI'})
        self.assertEqual(result['scope'],'local')

    def test_missing_companion_source_is_reported_separately_from_no_relationship(self):
        import server
        def fetch(variable,*args,**kwargs):
            if variable=='NDVI':raise ValueError('AppEEARS connection required')
            return {0:{0:{m:float(i%11) for i,m in enumerate(server.calendar_months(2005,2024))}}}
        with patch.object(server,'fetch_region',side_effect=fetch):
            out=server.run_coupling_analysis('country:gha',['GWETROOT','NDVI'],2005,2024,target_variable='GWETROOT')
        self.assertIn('NDVI',out['source_errors'])
        self.assertEqual(out['analysable_variables'],['GWETROOT'])
        self.assertIn('anomaly_report',out['source_anomaly'])


if __name__=='__main__':unittest.main()
