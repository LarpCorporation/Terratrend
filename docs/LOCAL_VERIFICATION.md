# TerraTrend local continuation — 14 November 2026

The protected NASA download that was pending at handover has now been verified with the user's Earthdata connection. Real observations reached the existing trend engine, custom-area comparison, expanded charts and browser CSV downloads. No token was read into chat or written to the repository. All project changes remain uncommitted.

## Working tree and running service

- Continued in the original `Terratrend` directory on `dev`, at base commit `2fbda28faa2fb9467535d690669c610737457732`.
- All **6,786 files** in the original handover manifest matched their recorded hashes before this session made changes. Existing tracked edits, untracked files and the deletion of `backend/literature.py` were retained.
- The process listening on `127.0.0.1:8517` was PID 252916, running `.venv/bin/python backend/server.py 8517` in this exact project. Its backend sources were not newer than the process.
- Contrary to the older browser state in the cloud handover, this local API already returned `automatic_data: true`, `custom_selections: true`, provider `nasa-merra2` and `reader_installed: true`. A backend restart was unnecessary; retaining the current process also retained the newly verified in-memory connection.
- The user entered the token through **Data & Methods → Connect Earthdata**. The app reported a successful real one-cell temperature read. Browser reloads retained this server connection. A future server restart still requires reconnecting unless the operator supplies `EARTHDATA_TOKEN`.

## Ghana and the independently drawn comparison

All four series below use **January 2005–December 2024**, with **240 valid months and 20 complete calendar years**. The native NetCDF files were independently reread from cache and all **960 regional monthly values** reproduced the API output at its declared rounding precision. Monthly overlap-weight coverage was 100% for both selected areas and both variables, within floating-point precision.

| Area | Variable | Native cells | Sen slope per decade | Adjusted Mann–Kendall p | Significant at 0.05 |
| --- | --- | ---: | ---: | ---: | --- |
| Ghana | Root-zone soil moisture | 85 | +0.0316625 saturation fraction | 0.0848401 | No |
| Drawn lasso | Root-zone soil moisture | 55 | +0.0314394 saturation fraction | 0.1099186 | No |
| Ghana | Air temperature | 85 | +0.1164038 °C | 0.5604680 | No |
| Drawn lasso | Air temperature | 55 | +0.1039917 °C | 0.5013494 | No |

The soil-moisture OLS cross-check disagrees with adjusted Mann–Kendall; the expanded observatory exposes that disagreement. Positive fitted slopes alone do not establish significant trends. These are reanalysis data and exploratory tests, not direct measurements at every map location or evidence of physical causation.

The paired common-year contrast reports **no significant difference** for soil moisture (`p_diff = 0.2497`) or air temperature (`p_diff = 0.7703`). The lasso overlaps Ghana, so the two areas are not spatially independent samples; the paired calculation uses their aligned difference series.

The committed lasso is `custom:6886c3df83c68350e63f`, geometry revision `ab944d808126253c`, approximately **130,747.4 km²**. Its exact saved polygon is:

```json
[[[-2.88966, 11.094982], [1.184642, 5.999046], [-2.163324, 4.942967], [-2.88966, 11.094982]]]
```

Ghana retains ID `country:gha` and revision `35339921e7a23101`. Both footprints use download window `[190, 202, 283, 290]` on the native 0.625° × 0.5° grid. Their aggregation masks differ: cached source windows were reused while the exact polygons produced different regional means.

### Source files and cache reuse

- Soil moisture: `M2TMNXLND` version `5.12.4`, field `GWETROOT`, dimensionless saturation fraction. First granule: `G1278016337-GES_DISC`; last: `G3381657958-GES_DISC`.
- Air temperature: `M2TMNXSLV` version `5.12.4`, field `T2M`, source units `K`, converted to °C. The first granule is `G1278025954-GES_DISC`.
- January 2005 subsets have shape `1 × 13 × 8`, latitude 5–11°, longitude −3.125–1.25°. The soil-moisture download window contains two masked cells; the temperature window contains none. The two masked soil cells lie outside these selected aggregation footprints.
- Ghana's first soil-moisture job downloaded 240 subsets with zero cache hits. A later two-variable job reused all 240 soil-moisture subsets and downloaded temperature separately.
- The final two-variable A/B job reused **240 subsets for each of four series: 960 cache hits**, with the same observed values as the initial downloads.

The full granule IDs, provider revisions, observed dates, masks, units and statistical results are retained in the [live evidence folder](local-handoff/live-2026-11-14/). This folder contains science results and metadata, not credentials.

## Additional automatic measurements

**All eight implemented automatic measurements passed real authenticated downloads.** In addition to the two full-country examples above, the remaining six each returned **108 valid monthly observations and nine complete years for 2016–2024**. These bounded checks use one native cell near 0°E, 7°N, not a claim of global or fine-resolution validation.

| Measurement | NASA collection / field | Actual source units | Output units | Observed months | Complete years |
| --- | --- | --- | --- | ---: | ---: |
| Surface temperature | M2TMNXSLV / TS | K | °C | 108 | 9 |
| Specific humidity | M2TMNXSLV / QV2M | kg kg⁻¹ | g/kg | 108 | 9 |
| Surface pressure | M2TMNXSLV / PS | Pa | kPa | 108 | 9 |
| Surface soil moisture | M2TMNXLND / GWETTOP | 1 | Saturation fraction | 108 | 9 |
| Land evaporation | M2TMNXLND / EVLAND | kg m⁻² s⁻¹ | mm/day | 108 | 9 |
| Precipitation | M2TMNXFLX / PRECTOTCORR | kg m⁻² s⁻¹ | mm/day | 108 | 9 |

Both source-probe jobs completed: `d1ab0f533b2e59fc9eb8` and `abe1cd80ca8b344a31c3`. Every field reported zero cache hits on that first request. Each first native response had shape `1 × 1 × 1`; its source units, coordinates, masks and converted value were checked against the real file. Converted single-cell values matched the returned regional values at rounding precision.

The source-check area is `custom:26ad29a78b8764195393`, rectangle −0.1–0.1° longitude and 6.9–7.1° latitude, native window `[194, 194, 288, 288]`. It did not change the user's visible A/B selections. See the [machine-readable eight-field check](local-handoff/live-2026-11-14/automatic-source-checks.json) and the saved source-probe responses for source samples, actual granules and provenance.

## Cancellation and stale results

Queued job `ffba64b72887cca4fea7` was cancelled before publication. A running lasso comparison, `eae4ea378b820fad4302`, was cancelled after 39 monthly subsets had completed. Later HTTP reads still showed `cancelled` with `result: null` for both jobs. The revised polygon was then analyzed successfully. Cancelled work may leave valid source subsets available in the cache, but it did not publish a late scientific result.

The frontend regression suite separately verifies stale completed responses, selection changes during cancellation and slower geographic requests. The browser session exercised running cancellation, replacing B's lasso, keeping Ghana as A, expanded graphs and both variable tabs.

## CSV export repair

The browser check reproduced a real omission: the old export had only date/value columns, wrote missing values as literal `null`, omitted B and lost provenance and annual completeness. Only the export section of the existing `frontend/app.js` controller was changed.

The updated export keeps the original first two column names and adds both areas for the active variable, geographic IDs/revisions, complete-year flags, valid-month counts, value status, provider/collection/field/citation, observed dates, source resolution and retrieval time. Missing values are empty; wholly missing requested years are retained. Comparison files have a `_comparison` suffix. CSV quoting preserves metadata containing commas, quotes or newlines; text that could become a spreadsheet formula is neutralized.

`Period_Area_Fraction_With_Any_Data` is deliberately **period-wide availability**, not monthly coverage. The current API does not return per-month coverage in its series payload. For this verification, the separate [monthly coverage audit](local-handoff/live-2026-11-14/observed-monthly-coverage.csv) recomputes actual monthly support from the saved native source files.

Actual browser downloads were parsed using Python's independent CSV reader:

- [Monthly soil moisture](local-handoff/live-2026-11-14/ghana-lasso-soil-moisture-monthly.csv): **480 rows**, 240 for A and 240 for B, January 2005–December 2024.
- [Annual temperature](local-handoff/live-2026-11-14/ghana-lasso-temperature-annual.csv): **40 rows**, 20 for each area, 2005–2024.
- Both files have **27 columns**, correct collection/field/units, distinct boundary revisions and complete-year flags matching the live analysis.

## Validation evidence

The five new export regressions were run before the production edit. All failed for the intended omissions: source metadata absent, `null` instead of an empty value, no B rows, missing annual gaps and no escaped metadata. After the export repair, all five passed. No checkpoint commits were created because this continuation explicitly preserves uncommitted work.

| Check actually run | Observed result |
| --- | --- |
| `node --test tests/csv-export.test.cjs` before repair | 5 failures reproducing the export omissions |
| Same target after repair | 5 passed |
| `node --experimental-test-coverage --test tests/*.test.cjs` | 46 passed, 0 failed |
| `.venv/bin/python -m pytest backend -q -p no:cacheprovider` | 146 passed, 1 skipped, 5 passing subtests |
| `node --check frontend/app.js` | Passed |
| `git diff --check` | Passed |
| Browser exports parsed independently | 480 monthly / 40 annual A/B rows and correct provenance |
| Cached native-file reconstruction | All 960 regional monthly values matched |
| Other six implemented source mappings | 108 valid months and nine complete years each; real units/conversions verified |

The skipped backend test is the opt-in live **POWER** catalogue test (`TERRATREND_NET=1`), not the newly verified MERRA-2 route. It remains skipped under the existing source policy. The built-in JavaScript coverage report omits the VM-evaluated controller functions, so no full-controller coverage percentage is claimed.

Screenshots: [Ghana soil-moisture observatory](local-handoff/screenshots/local-ghana-root-live.jpg), [temperature observatory](local-handoff/screenshots/local-ghana-temperature-live.jpg), [final live comparison](local-handoff/screenshots/local-live-comparison.jpg).

## Remaining integration work

The original unsupported catalogue fields remain disabled for automatic analysis. In particular, NASA's daily `M2SDNXSLV` statistics provide temperature extremes; monthly daily-extreme means require complete daily aggregation. `EVPTRNS` denotes a transpiration **energy** flux, while `EVLAND` includes land evapotranspiration components; the legacy catalogue's description of EVLAND as excluding plants needs correction when reconciling those two definitions. Absorbed longwave radiation (`LWGAB`) must not be relabeled as incoming downwelling radiation. These distinctions are documented in the [NASA MERRA-2 file specification](https://gmao.gsfc.nasa.gov/pubs/docs/Bosilovich785.pdf), including the land-budget appendix.

The satellite tab still displays its source-policy state. An AppEEARS imagery integration needs its own supported authentication/task/output contract; its API documents a login-issued token, and an existing GES DISC connection does not by itself verify AppEEARS access. See the [official AppEEARS API documentation](https://appeears.earthdatacloud.nasa.gov/api/). No satellite images or new mappings for the disabled catalogue fields are claimed in this continuation.

The existing olive UI and map controls were retained. No commit, push, merge or deployment was performed. The comparison tab was left open, and the verified server was left running.
