"""Automatic routing must preserve boundaries and paired product identity."""
import unittest
from unittest.mock import patch
import geography
import data_sources as d


class TestAutomaticRouting(unittest.TestCase):
    def test_discovery_excludes_an_incompatible_height_without_substituting_a_country_box(self):
        p=d.plan_request({'operation':'scan','provider':'auto','region':'country:gha','variables':['T2M','T10M'],'start':2016,'end':2024})
        self.assertEqual(p['variables'],['T2M']);self.assertFalse(p['issues'])
        self.assertEqual(p['excluded'][0]['variable'],'T10M')
        self.assertNotIn('T10M',p['routes']['country:gha'])

    def test_automatic_fetch_keeps_adapter_identity_and_does_not_substitute_unsupported_measurements(self):
        area=geography.resolve('country:gha');token=d.PROVIDER.set('auto')
        try:
            with patch.object(d.appeears_data,'fetch_region',return_value='NASA vegetation') as fetch:
                self.assertEqual(d.fetch_region('NDVI',area,2016,2024),'NASA vegetation');fetch.assert_called_once_with('NDVI',area,2016,2024)
            with self.assertRaisesRegex(ValueError,'no verified automatic'):
                d.fetch_region('RH2M',area,2016,2024)
        finally:d.PROVIDER.reset(token)

    def test_job_preserves_pair_context_and_rejects_invalid_scope_before_fetch(self):
        import server
        def analyzed(*args,**kwargs):
            self.assertEqual([a['id'] for a in d.AUTO_AREAS.get()],['country:gha','focus:ghana_north'])
            return {'fixture':True}
        with patch.object(server,'run_analysis',side_effect=analyzed):
            out=server.execute_job({'operation':'analyze','provider':'auto','region':'country:gha','compare_region':'focus:ghana_north','variables':['T2M'],'start':2016,'end':2024})
        self.assertTrue(out['fixture']);self.assertEqual(d.AUTO_AREAS.get(),())
        with patch.object(server,'run_analysis') as fetch:
            with self.assertRaisesRegex(ValueError,'rectangle'):
                server.execute_job({'operation':'analyze','provider':'auto','region':'country:gha','variables':['T10M'],'start':2016,'end':2024})
        fetch.assert_not_called()

    def test_two_rectangles_use_prepared_series_but_mixed_shapes_keep_paired_product(self):
        a=geography.resolve('focus:ghana_north');b=geography.resolve('focus:ghana_south')
        self.assertEqual(d.automatic_route('T2M',a,[a,b]),'nasa-giovanni')
        self.assertEqual(d.automatic_route('T2M',a,[a,geography.resolve('country:gha')]),'nasa-merra2')

    def test_country_measurements_route_to_actual_source_without_downloads(self):
        a=geography.resolve('country:gha')
        self.assertEqual(d.automatic_route('NDVI',a,[a]),'nasa-appeears')
        self.assertEqual(d.automatic_route('PRECTOTCORR',a,[a]),'nasa-merra2')
        self.assertEqual(d.automatic_route('STATION_WIND',a,[a]),'noaa-cdo')

    def test_unsupported_shape_has_specific_recovery_and_is_not_replaced_by_bbox(self):
        a=geography.resolve('country:gha')
        with self.assertRaisesRegex(ValueError,'Ghana.*10 m.*rectangle|10 m.*Ghana.*rectangle'):
            d.automatic_route('T10M',a,[a])

    def test_preflight_lists_actual_routes_and_rejects_oversized_requests_without_network(self):
        with patch.object(d.nasa_data,'fetch_region') as download:
            p=d.plan_request({'operation':'analyze','provider':'auto','region':'country:gha','variables':['PRECTOTCORR','NDVI'],'start':2016,'end':2024})
            self.assertEqual(p['routes']['country:gha']['NDVI'],'nasa-appeears')
            self.assertFalse(p['issues'])
            p=d.plan_request({'operation':'analyze','provider':'auto','region':'continent:africa','variables':['NDVI'],'start':2016,'end':2024})
            self.assertIn('smaller',p['issues'][0]['message'])
        download.assert_not_called()


if __name__=='__main__':unittest.main()
