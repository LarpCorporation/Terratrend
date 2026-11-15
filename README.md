# TerraTrend — Earth Change Observatory

TerraTrend is a NASA Space Apps project for investigating environmental change across whole geographic areas. The original analysis engine and chart tools now sit behind a map-first interface inspired by Kaspersky Cybermap, using the globe geometry from the sibling TerraTrend 2 project.

## Run

From this repository’s root:

```bash
./start.sh 8517
```

Open <http://127.0.0.1:8517>. Stop any older TerraTrend server on that port first, then start this version and reload the browser. The new frontend needs the new backend routes; refreshing an already-running Python process does not reload its code.

The startup script uses a project virtual environment and installs missing Python dependencies from `requirements.txt` (NumPy, SciPy, Requests and NetCDF4). JavaScript libraries are bundled locally. `pytest` is needed for the Python test command below.

## Investigation workflow

1. Choose **Continent**, **Subcontinent**, **Country**, or **Region**. The scope selector limits the displayed units. Ghana’s 16 administrative regions are bundled; other countries request ADM1 boundaries on demand when online access is available. **◇ Presets** switches the same globe to 23 original focus boxes, including Savannah, Congo Basin and Sahel; these are curated boxes, not official ecosystem boundaries.
2. Click the blue **A / Primary area** card or amber **B / Comparison area** card to choose the target. Pick a whole boundary, draw a freehand/clicked **Lasso**, enter **Lat / Lon** bounds, or place a **Circle**/**Square** centre and adjust its size in kilometres. Custom shapes show approximate area; choose **Use for area A/B** to commit. A and B keep independent methods and stay selected when the displayed geographic level changes.
3. Use the persistent **selection icon at the bottom right** to open the compact icon rail. Hover/focus a tool for its label. The settings card opens only when a method needs controls; closing it leaves the rail accessible. Clear A/B with its × button, or click an already selected boundary again.
4. Choose a data source and a period of at least nine years. Variables are optional: leave them empty to discover what is changing, or select up to three for detailed analysis.
5. Choose **Analyze** explicitly. With no variables selected, it prepares a discovery scan of the source's supported measurements for primary area A. A data-use review shows the area, period, measurements and estimated uncached download size. Choose **Start this request** to submit it, or **Go back** to change the scope. Selecting an area alone does not start a scientific request.
6. Use **Analyze Layer** to calculate a separate trend for every area currently displayed. Results are calculated independently at each level. Missing data have their own status.
7. Discovery shows a ranked table of significant increases, significant decreases, nonsignificant results, insufficient observations and source errors. Choose a measurement to open **Analysis** for its graph, statistics, native-cell summaries and CSV export. Open **Compare** and choose two different units for an A/B analysis using the same variables and dates.
8. Open **Interconnections** to screen local candidate leads and simultaneous associations. In **Linked datasets**, select two or three measurements across sources. Remote screening is off by default and requires the explicit **Include remote areas** option and review. Each result retains its source and quality limits. **Globe / plane** switches the projection while retaining geographic identities.

## Scientific data

The default source is **NASA MERRA-2 · exact boundaries**, using GES DISC datasets available through the challenge’s **Giovanni** resource. Open **Data & Methods**, generate a user token in your [NASA Earthdata profile](https://urs.earthdata.nasa.gov/profile), and connect it there. The app verifies authorization by reading one real temperature cell. Enable **Remember this connection on this computer** to restore the connection after server restarts. The key uses the desktop credential store when available, or an owner-only local configuration file outside the project; it is not saved to browser storage or the repository. **Forget this connection** removes it. NASA can still expire or revoke the token. A server operator can instead provide `EARTHDATA_TOKEN` in the process environment.

If the running server is older than these files, the UI shows **RESTART SERVER** and opens setup. It does not silently change to cache-only data. Stop that Python process with Ctrl+C, run `./start.sh 8517` from this folder and reload. Measurements without an automatic source mapping are marked in the variable controls; cached data remain available only when explicitly selected.

**Additional sources:** **Data & Methods → Data source and processing** and the variable drawer now offer AppEEARS monthly NDVI/EVI, Hydrology GLDAS soil water/soil temperature/near-surface wind, and NOAA station temperature/rainfall/wind. **Linked datasets · NASA + NOAA** connects explicitly selected measurements across sources while preserving each product's identity. There are 20 distinct live measurement IDs. AppEEARS has a separate NASA sign-in form; **Remember** stores only the issued token, not the password. Both remembered NASA connections were verified after actual restarts. NOAA's public NCEI route needs no separate API key.

**Optional low-transfer mode:** Choose **NASA Giovanni · rectangle summaries (preview)** for bounds, an axis-aligned rectangular lasso or a preset box. NASA returns monthly air-temperature and specific-humidity averages at **2 m and 10 m**. This mode uses M2IMNXASM, a different MERRA-2 product; it retains charts, discovery, two-rectangle comparisons, local relationships, preset-box layers and export. It supplies neither native-cell maps nor a monthly valid-area audit. No automatic raw-download fallback is used. AppEEARS likewise processes the actual polygon on NASA servers and returns only statistics CSVs, though its first remote extraction can take minutes. See [sources, presets, caching and live checks](docs/SOURCES_AND_PRESETS.md), [the Giovanni integration report](docs/GIOVANNI_INTEGRATION.md) and [all 13 challenge resource links](docs/CHALLENGE_RESOURCES.md).

After connecting and reviewing data use, **Start this request** discovers published monthly granules in NASA CMR, downloads only the requested native grid windows through OPeNDAP, applies provider masks and verified unit conversions, clips cells to the exact selected polygon, and caches validated subsets. NASA supplies the scientific subsets; this computer downloads, stores and analyzes them. Progress and cancellation cover downloading as well as calculations. No manual data uploads are required. Large first-time requests can take minutes; subsequent analyses reuse cached data.

For Africa in 2005–2024, the current conservative planning estimate is **68.6 MB for one measurement** or **548.5 MB for all eight**, assuming an empty matching cache. These estimates are not measured transfers or a hard data cap. They allow for native values, coordinates and file metadata; compression, cache reuse and service responses can change actual data use. Each native download window can include cells outside the selected polygon. See [area-only discovery and data use](docs/AREA_DISCOVERY_AND_DATA_USE.md) for the implementation, verification and suggested small examples. Relationship searches and layer analyses also show the review before a scientific job is submitted.

| Automatic measurement | NASA collection / field | Conversion |
| --- | --- | --- |
| Air temperature | M2TMNXSLV / T2M | K → °C |
| Surface temperature | M2TMNXSLV / TS | K → °C |
| Specific humidity | M2TMNXSLV / QV2M | kg/kg → g/kg |
| Surface pressure | M2TMNXSLV / PS | Pa → kPa |
| Root-zone / surface soil moisture | M2TMNXLND / GWETROOT, GWETTOP | Saturation fraction retained |
| Land evaporation | M2TMNXLND / EVLAND | kg m⁻² s⁻¹ → mm/day |
| Precipitation | M2TMNXFLX / PRECTOTCORR | kg m⁻² s⁻¹ → mm/day |

All three native collections use version **5.12.4**, with a grid of **0.625° longitude × 0.5° latitude**. Each source enables only its verified mappings; unsupported fields are rejected explicitly. New GLDAS and station wind IDs remain separate from the unmapped 2 m wind ID. Monthly wind-component means are not substituted for mean wind speed, monthly maxima are not daily-maximum averages, and absorbed radiation is not substituted for direct normal irradiance.

All eight implemented measurements have now passed real authenticated download checks. Besides the country-scale examples below, the other six each returned 108 valid months and nine complete years for a single native cell in 2016–2024, with source units and conversions checked against the downloaded NetCDF files. These bounded checks do not establish coverage for every geographic selection.

On 14 November 2026, an Earthdata-connected local run verified real **Ghana 2005–2024 root-zone soil-moisture and air-temperature downloads**: 240 valid months and 20 complete years for each variable, with 85 intersecting native cells. A separately drawn 55-cell lasso was analyzed independently; repeat A/B calculations reused 960 cached subsets across the four series. Native-file checks reproduced all 960 regional monthly values and confirmed full monthly area support for these particular selections. Both Ghana trends and both paired contrasts were statistically nonsignificant. See [local verification and evidence](docs/LOCAL_VERIFICATION.md) for exact results, source granules, masks, units, exports and remaining work. That verification used session-only credentials. Remembered desktop connections are now implemented for automatic reconnection after restart.

Earlier unauthenticated requests reached the Earthdata login gate; this was not evidence of missing observations. The old Hydrology Data Rods URL redirects to a retirement notice. The new Hydrology connector uses NASA's current monthly time-series service, separately from the native MERRA-2 OPeNDAP adapter.

The sparse **Existing project cache** remains available and is labeled as a legacy POWER access route not verified against the challenge resource list. Overlapping cached observations are retained while missing months remain missing. Advanced normalized CSV import remains available under a collapsed section in Data & Methods for existing datasets; it is optional.

**Analysis → Satellite imagery** retains the earlier satellite panel. Imagery access remains source-policy gated; the new MERRA-2 trend adapter does not enable satellite image products.

## Map navigation and panels

Vertical scrolling zooms; horizontal trackpad scrolling rotates the globe or pans the plane. Wheel units are normalized and each event is limited; close-up zoom and drag scale with camera altitude. Double-click the globe to start spinning; drag or use the rotation button to pause it. Drawing tools retain their own click/drag behavior.

Drag either floating panel by its heading/grip, or use arrow keys on the grip (Shift for larger steps). The −/+ button collapses or expands the panel. Positions are kept inside the map on resize, and position/collapse preferences are saved locally. Boundary downloads are cached per country; recently viewed administrative meshes are reused. Progressive mesh construction and cancellation keep the map responsive while switching countries.

## Methods and limits

Whole Polygon/MultiPolygon selections, including disconnected pieces present in the boundary dataset, are shared between the renderer and backend. Native MERRA-2 and GLDAS cells use polygon overlap and `cos(latitude)`, a small-cell approximation. Those months need at least 80% selected-area support; incomplete years are excluded from annual trend testing. Giovanni and AppEEARS summaries do not provide that independently audited monthly support, and AppEEARS has no additional per-pixel VI quality filter. NOAA uses a fixed station cohort, not an area average or whole-country layer. Coarse data cannot resolve fine administrative differences simply because the map has sharper boundaries. Full limits and live outcomes are in [the source report](docs/SOURCES_AND_PRESETS.md).

Theil–Sen and Mann–Kendall summarize annual trends, with confidence intervals, seasonal checks and OLS diagnostics. Actual calendar years preserve gaps in slope calculations. A/B inference uses common complete years and the paired difference series.

CSV export retains the date/value columns and adds A/B area identities, source and boundary provenance, complete-year flags and explicit missing-value states. A comparison exports both areas for the selected variable. Missing values are empty cells; wholly missing requested years remain in annual exports. Coverage columns describe availability in **any month of the requested period**, not a per-month coverage fraction. The separate monthly coverage audit in the local verification evidence records measured support for the verified Ghana/lasso example.

Interconnection screens use anomaly series, lag-search correction, full-family false discovery control and conditional diagnostics where sufficient data exist. They identify exploratory associations and possible lead relationships. They do not establish physical causation, explain a long-term trend by themselves, or measure atmospheric transport. Moving packets illustrate computed lead direction.

Continents and subcontinents use Natural Earth’s regional country membership. Transcontinental countries remain whole under that scheme. Administrative boundaries can be dated or unavailable, and small islands may be absent at the bundled 1:50m resolution.

## Validation

```bash
.venv/bin/python -m pytest backend -q -p no:cacheprovider
node --test tests/*.test.cjs
node --check frontend/app.js
node --check frontend/workflow.js
node --check frontend/earth-renderer.js
node --check frontend/selection-tools.js
node --check frontend/selection-geometry.js
node --check frontend/map-panels.js
```

See [implementation notes](docs/UI_OVERHAUL_IMPLEMENTATION.md) for the architecture, validated behavior, API and remaining work. The [integration review](docs/UI_OVERHAUL_REVIEW.md) records the original assessment. The pre-overhaul README is preserved as [historical documentation](docs/LEGACY_README.md); its demo claims and old workflow are not the current contract.
