"""NOAA monthly station summaries must never masquerade as gridded area means."""
import unittest


class TestStationData(unittest.TestCase):
    def test_station_membership_respects_polygon_holes(self):
        import station_data as n
        f={'geometry':{'type':'Polygon','coordinates':[
            [[0,0],[2,0],[2,2],[0,2],[0,0]],[[.5,.5],[1.5,.5],[1.5,1.5],[.5,1.5],[.5,.5]]]}}
        self.assertTrue(n.inside(f,.25,.25));self.assertFalse(n.inside(f,1,1));self.assertFalse(n.inside(f,3,1))

    def test_fixed_cohort_excludes_short_records_and_preserves_missing_months(self):
        import station_data as n
        rows=[{'STATION':'a','DATE':f'{y}-{m:02}','TAVG':'20','TAVG_ATTRIBUTES':',W'}
              for y in range(2010,2020) for m in range(1,13)]
        rows += [{'STATION':'b','DATE':'2019-01','TAVG':'40','TAVG_ATTRIBUTES':',W'}]
        series,cohort=n.monthly_series(rows,'TAVG',2010,2019)
        self.assertEqual(cohort,['a']);self.assertEqual(len(series),120)
        self.assertEqual(series[201901],20)

    def test_monthly_rain_total_converts_to_daily_mean_and_duplicate_rows_are_rejected(self):
        import station_data as n
        rows=[{'STATION':'a','DATE':f'2024-{m:02}','PRCP':str(__import__('calendar').monthrange(2024,m)[1]*2)} for m in range(1,13)]
        values,_=n.monthly_series(rows,'PRCP',2024,2024)
        self.assertEqual(values[202402],2)
        with self.assertRaisesRegex(ValueError,'Duplicate|duplicate'):n.monthly_series(rows+[rows[0]],'PRCP',2024,2024)

    def test_missing_wind_is_insufficient_data_without_invented_station_values(self):
        import station_data as n
        values,cohort=n.monthly_series([{'STATION':'a','DATE':'2024-01','TAVG':'20'}],'AWND',2024,2024)
        self.assertFalse(cohort);self.assertTrue(all(v is None for v in values.values()))

    def test_gsom_missing_days_and_quality_flags_preserve_source_codes(self):
        import station_data as n
        for field in ('TMAX','TMIN','PRCP'):
            with self.subTest(field=field):
                rows=[{'STATION':'a','DATE':f'2024-{m:02}',field:'20',field+'_ATTRIBUTES':',,,W'} for m in range(1,13)]
                rows[0][field+'_ATTRIBUTES']='2,,,W'
                rows[1][field+'_ATTRIBUTES']=' , ,X,W'
                values,cohort=n.monthly_series(rows,field,2024,2024)
                self.assertEqual(cohort,['a'])
                self.assertIsNone(values[202401]);self.assertIsNone(values[202402])
                self.assertGreater(values[202403],0)
        rows=[{'STATION':'a','DATE':f'2024-{m:02}','PRCP':'31','PRCP_ATTRIBUTES':',,,W'} for m in range(1,13)]
        rows[0]['PRCP_ATTRIBUTES']=',a,,W'
        values,cohort=n.monthly_series(rows,'PRCP',2024,2024)
        self.assertEqual(cohort,['a']);self.assertIsNone(values[202401])


if __name__=='__main__':unittest.main()
