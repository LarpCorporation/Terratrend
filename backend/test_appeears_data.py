"""AppEEARS summary extraction; data values below are fixtures."""
import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch


class TestAppEEARS(unittest.TestCase):
    def test_region_request_keeps_polygon_and_monthly_product_instead_of_bbox(self):
        import appeears_data as a
        feature={'geometry':{'type':'Polygon','coordinates':[[[0,0],[1,0],[0,1],[0,0]]]},'name':'Triangle'}
        task=a.task_spec('NDVI',feature,2005,2024)
        self.assertEqual(task['task_type'],'area')
        self.assertEqual(task['params']['geo']['features'][0]['geometry'],feature['geometry'])
        self.assertEqual(task['params']['layers'][0]['product'],'MOD13A3.061')

    def test_physical_summary_means_are_not_scaled_twice_and_missing_months_remain_missing(self):
        import appeears_data as a
        raw=b'ID,Date,Dataset,Count,Minimum,Maximum,Range,Mean,Standard Deviation,Variance\n0,2024-01-01,MOD13A3.061__1_km_monthly_NDVI,4,0.1,0.9,0.8,0.5,0.1,0.01\n0,2024-02-01,MOD13A3.061__1_km_monthly_NDVI,0,-3000,-3000,0,-3000,0,0\n'
        values=a.decode_statistics(raw,'NDVI',2024,2024)
        self.assertEqual(values,{202401:.5,202402:None})
        with self.assertRaises(ValueError):a.decode_statistics(raw.replace(b'NDVI',b'EVI'),'NDVI',2024,2024)
        with self.assertRaises(ValueError):a.decode_statistics(raw+raw.splitlines(keepends=True)[1],'NDVI',2024,2024)
        with self.assertRaisesRegex(ValueError,'scale|range|physical'):a.decode_statistics(raw.replace(b',0.5,',b',5000,'),'NDVI',2024,2024)

    def test_service_credentials_are_separate_from_earthdata_and_status_has_no_token(self):
        import service_credentials as c
        import earthdata_credentials as earth
        with tempfile.TemporaryDirectory() as d,patch.object(earth,'DIRECTORY',Path(d)),patch.object(earth,'_find_secret_tool',return_value=None):
            c.remember('appeears','fixture-private-token')
            self.assertEqual(c.load('appeears'),'fixture-private-token')
            self.assertNotIn('fixture-private-token',json.dumps(c.status('appeears')))
            self.assertFalse((Path(d)/'earthdata-token').exists())
            c.forget('appeears');self.assertEqual(c.load('appeears'),'')

    def test_bundle_selection_downloads_only_summary_csv_never_tiffs_or_qa_lookup(self):
        import appeears_data as a
        files=[{'file_name':'MOD13A3-061-Statistics.csv','file_id':'stats'},
               {'file_name':'MOD13A3-061-Statistics-QA.csv','file_id':'qa'},
               {'file_name':'MOD13A3.061.tif','file_id':'raster'}]
        self.assertEqual(a.summary_file(files)['file_id'],'stats')
        with self.assertRaises(ValueError):a.summary_file(files[1:])

    def test_separate_desktop_keyring_uses_stdin_and_falls_back_when_locked(self):
        import service_credentials as c
        import earthdata_credentials as earth
        def run(args,**kwargs):
            self.assertNotIn('fixture-service-key',args)
            self.assertEqual(args[-1],'appeears')
            return SimpleNamespace(returncode=0,stdout='fixture-service-key' if 'lookup' in args else '')
        with tempfile.TemporaryDirectory() as d,patch.object(earth,'DIRECTORY',Path(d)),patch.object(earth,'_find_secret_tool',return_value='/fixture/secret-tool'),patch.object(c.subprocess,'run',side_effect=run):
            c.remember('appeears','fixture-service-key');self.assertEqual(c.load('appeears'),'fixture-service-key')
            self.assertFalse((Path(d)/'appeears-token').exists());c.forget('appeears')
        with tempfile.TemporaryDirectory() as d,patch.object(earth,'DIRECTORY',Path(d)),patch.object(earth,'_find_secret_tool',return_value='/fixture/secret-tool'),patch.object(c.subprocess,'run',side_effect=OSError('fixture locked service')):
            c.remember('appeears','fixture-service-key');self.assertEqual(c.load('appeears'),'fixture-service-key')
        with self.assertRaises(ValueError):c.load('other-service')


if __name__=='__main__':unittest.main()
