const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { execFileSync } = require('node:child_process');

const app = fs.readFileSync(require('node:path').join(__dirname, '../frontend/app.js'), 'utf8');

function result() {
  return {
    start: 2005, end: 2006, months: ['2005-01', '2005-02'],
    region: { id: 'country:gha', name: 'Ghana', geometry_version: 'boundary-a' },
    series: [{
      variable: { id: 'T2M', unit: '°C' },
      monthly_timeseries: [{ month: '2005-01', value: 0 }, { month: '2005-02', value: null }],
      yearly_timeseries: [{ year: 2005, value: 0, months: 1, complete: false }],
      provenance: {
        source: 'NASA GES DISC / MERRA-2', provider: 'nasa-merra2', dataset: 'M2TMNXSLV',
        collection_version: '5.12.4', field: 'T2M', geometry_version: 'boundary-a',
        available_area_fraction: .94, available_cells: 85, expected_cells: 90,
        first_observed_month: 200501, last_observed_month: 200501,
        retrieved_utc: '2026-11-14T23:00:00Z', citation: 'https://example.test/dataset',
      },
    }],
  };
}

async function exported(data, mode = 'monthly') {
  let blob;
  const ctx = {
    state: { result: data, expandedVarIdx: 0, expandedMode: mode }, Blob,
    URL: { createObjectURL(value) { blob = value; return 'blob:test'; }, revokeObjectURL() {} },
    document: { createElement() { return { click() {} }; }, body: { appendChild() {}, removeChild() {} } },
  };
  vm.createContext(ctx);
  const helper = app.indexOf('function buildAnalysisCSV(');
  const start = helper >= 0 ? helper : app.indexOf('function exportDataCSV()');
  vm.runInContext(app.slice(start, app.indexOf('\nfunction drawChart()', start)), ctx);
  ctx.exportDataCSV();
  const csv = await blob.text();
  // Parse with the independent standard-library CSV reader, including quoted newlines.
  const rows = JSON.parse(execFileSync('python3', ['-c',
    'import csv,io,json,sys; print(json.dumps(list(csv.DictReader(io.StringIO(sys.stdin.read())))))',
  ], { input: csv, encoding: 'utf8' }));
  return { csv, rows };
}

test('CSV retains source, geometry and explicitly period-wide coverage', async () => {
  const { rows } = await exported(result());
  assert.equal(rows[0].Dataset, 'M2TMNXSLV');
  assert.equal(rows[0].Collection_Version, '5.12.4');
  assert.equal(rows[0].Source_Field, 'T2M');
  assert.equal(rows[0].Geometry_Revision, 'boundary-a');
  assert.equal(rows[0].Period_Area_Fraction_With_Any_Data, '0.94');
  assert.equal(rows[0].Expected_Native_Cells, '90');
  assert.equal(rows[0].First_Observed_Month, '2005-01');
  assert.equal(rows[0].Last_Observed_Month, '2005-01');
  assert.ok(!Object.hasOwn(rows[0], 'Monthly_Area_Coverage'));
});

test('CSV preserves zero and calendar dates while leaving missing values empty', async () => {
  const { rows } = await exported(result());
  assert.equal(rows[0].Month_YYYY_MM, '2005-01');
  assert.equal(rows[0]['Regional_Mean_T2M_°C'], '0');
  assert.equal(rows[1].Month_YYYY_MM, '2005-02');
  assert.equal(rows[1]['Regional_Mean_T2M_°C'], '');
  assert.equal(rows[1].Value_Status, 'unavailable');
});

test('comparison CSV includes independent A/B values matched by variable ID', async () => {
  const data = result();
  data.compare = { region: { id: 'custom:abc', name: 'Lasso area' }, series: [
    { variable: { id: 'PS', unit: 'kPa' }, monthly_timeseries: [] },
    { ...structuredClone(data.series[0]), monthly_timeseries: [{ month: '2005-02', value: 27.5 }],
      provenance: { dataset: 'M2TMNXSLV', geometry_version: 'boundary-b' } },
  ] };
  const { rows } = await exported(data);
  assert.equal(rows.length, 4);
  assert.deepEqual(rows.map(row => row.Area_Slot), ['A', 'A', 'B', 'B']);
  assert.equal(rows[2].Area_ID, 'custom:abc');
  assert.equal(rows[2]['Regional_Mean_T2M_°C'], '');
  assert.equal(rows[3]['Regional_Mean_T2M_°C'], '27.5');
  assert.equal(rows[3].Geometry_Revision, 'boundary-b');
});

test('annual CSV marks partial years and retains wholly missing requested years', async () => {
  const { rows } = await exported(result(), 'yearly');
  assert.equal(rows.length, 2);
  assert.equal(rows[0].Year, '2005');
  assert.equal(rows[0].Valid_Months_In_Year, '1');
  assert.equal(rows[0].Complete_Year, 'false');
  assert.equal(rows[0].Value_Status, 'partial_year');
  assert.equal(rows[1].Year, '2006');
  assert.equal(rows[1]['Annual_Mean_T2M_°C'], '');
  assert.equal(rows[1].Valid_Months_In_Year, '0');
  assert.equal(rows[1].Value_Status, 'unavailable');
});

test('CSV quotes metadata and prevents area names from becoming spreadsheet formulas', async () => {
  const data = result();
  data.region.name = '=SUM(1,2)';
  data.series[0].provenance.source = 'NASA, "MERRA-2"\nReanalysis';
  const { rows } = await exported(data);
  assert.equal(rows[0].Area_Name, "'=SUM(1,2)");
  assert.equal(rows[0].Source, 'NASA, "MERRA-2"\nReanalysis');
  assert.equal(rows[0]['Regional_Mean_T2M_°C'], '0');
});
