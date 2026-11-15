"""Monthly Hydrology Time Series contracts; generated observations are fixtures."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import geography


def fixture_csv(field='SoilMoi0_10cm_inst',unit='kg m-2',lon=-1.125,lat=9.125):
    return (f'prod_name,GLDAS_NOAH025_M.2.1\nparam_short_name,{field}\nunit,{unit}\nundef,-9999\n'
            f'lat,{lat}\nlon,{lon}\nlat_resolution,0.25\nlon_resolution,0.25\n\n'
            'Timestamp (UTC),Data\n2024-01-01 00:00,8.5\n2024-02-01 00:00,-9999\n').encode()


class TestHydrology(unittest.TestCase):
    def test_monthly_schema_units_coordinates_and_missing_values(self):
        import hydrology_data as h
        v=h.decode_csv(fixture_csv(),'GLDAS_SM_TOP',-1.125,9.125,2024,2024)
        self.assertEqual(v,{202401:8.5,202402:None})
        for raw in [fixture_csv(unit='mm/day'),fixture_csv(field='RootMoist_inst'),fixture_csv(lon=0),
                    fixture_csv()+b'2024-01-02 00:00,2\n']:
            with self.subTest(raw=raw[:30]):
                with self.assertRaises(ValueError):h.decode_csv(raw,'GLDAS_SM_TOP',-1.125,9.125,2024,2024)

    def test_country_aggregation_uses_each_actual_native_cell_and_reuses_point_cache(self):
        import hydrology_data as h
        f=geography._feature('fixture:hydro','Fixture','preset',{'type':'Polygon','coordinates':[
            [[-1.25,9],[-1,9],[-1,9.25],[-1.25,9.25],[-1.25,9]]]})
        with tempfile.TemporaryDirectory() as d,patch.object(h,'CACHE',Path(d)),patch.dict(geography._FEATURES,{f['id']:f}),\
             patch.object(h.nasa_data,'token',return_value='fixture-auth'),patch.object(h,'_request',return_value=fixture_csv()) as request:
            a=h.fetch_region('GLDAS_SM_TOP',f,2024,2024)
            b=h.fetch_region('GLDAS_SM_TOP',f,2024,2024)
        self.assertEqual(request.call_count,1)
        self.assertEqual(set(a),{-1.125});self.assertEqual(set(a[-1.125]),{9.125})
        self.assertEqual(b.provenance['cached_series'],1)
        self.assertIn('polygon',a.provenance['aggregation'].lower())
        self.assertEqual(a.provenance['dataset'],'GLDAS_NOAH025_M')

    def test_continental_request_is_bounded_before_any_remote_call(self):
        import hydrology_data as h
        with patch.object(h,'_request') as request,patch.object(h.nasa_data,'token',return_value='fixture-auth'):
            with self.assertRaisesRegex(ValueError,'smaller|limit|cells'):
                h.fetch_region('GLDAS_SM_TOP',geography.resolve('continent:africa'),2005,2024)
        request.assert_not_called()

    def test_source_definitions_do_not_relabel_water_mass_as_saturation_or_wind_as_two_metre(self):
        import hydrology_data as h
        self.assertNotIn('GWETTOP',h.FIELDS)
        self.assertNotIn('WS2M',h.FIELDS)


if __name__=='__main__':unittest.main()
