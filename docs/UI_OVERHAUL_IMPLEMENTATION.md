# TerraTrend geographic workflow implementation

**Local continuation:** The protected Earthdata download, Ghana/lasso A/B analysis, cache reuse and browser exports were verified on 14 November 2026. The export omission was repaired. See [the local verification report](LOCAL_VERIFICATION.md) for current observed results and evidence; the implementation history below retains its earlier verification states.

Implemented in the original Terratrend working directory on 14 November 2026. The sibling TerraTrend 2 directory was read for its map geometry and presentation; its demonstration values and random scientific events were not adopted. Existing working-tree edits were retained. Nothing has been committed, pushed or deployed.

## What changed

| Requirement | Current implementation |
| --- | --- |
| Kaspersky-inspired map-first interface | Olive globe, compact navigation and level toolbar, collapsible variable drawer, area card, variable strip and data legend; dedicated Analysis, Compare and Data & Methods screens |
| Four geographic levels | Shared stable IDs and complete polygon selections for continents, subcontinents, countries and first-level administrative regions |
| Globe and plane | Maintained Three.js renderer using the sibling project’s country/coast mesh; geographic fills, outlines, hover/picking, pan/zoom, labels and computed links in both views |
| Whole countries and islands | MultiPolygon geometry is retained. Duplicate Australian territory entries are merged into the country selection. Source resolution still limits tiny islands |
| Per-area trends | Explicit selected-area jobs or an independent calculation for every unit in the visible layer; no inherited parent verdicts |
| Compare two areas | Common variables, provider and dates; distinct A/B selections; calendar-aligned paired inference and separate fitted chart lines |
| Incoming and outgoing relationships | Lagged local/remote screening, signed association separate from lead direction, grouped evidence and an exploratory joint-driver regression when supported |
| Source policy | Automatic authenticated NASA MERRA-2 subsets from the Giovanni/GES DISC archive; legacy cache labeled separately; optional normalized imports; no new POWER downloads |
| Long-running work | Two bounded workers, immutable request identity, deduplication, progress, cancellation and stale-response rejection |

## Architecture

| File | Responsibility |
| --- | --- |
| `frontend/earth-renderer.js` | Maintained Three.js scene, shared polygon geometry, projection morph, selection and evidence arcs |
| `frontend/selection-geometry.js` | Geodesic circle/square geometry, coordinate bounds, lasso validation, approximate surface area and stable boundary identities |
| `frontend/selection-tools.js` | Independent A/B target controls, preview/commit, size controls, coordinate form and Analysis evidence tabs |
| `frontend/map-panels.js` | Draggable/collapsible map cards, keyboard movement and bounded persisted positions |
| `frontend/workflow.js` | Investigation state, explicit jobs, source import, geographic scopes and compatibility with original chart/statistics controllers |
| `frontend/overhaul.css` | New layout, responsive rules, map chrome and screen styling |
| `frontend/app.js` | Retained chart, glossary, export, scan, expanded-statistics and interconnection controllers |
| `backend/geography.py` | Boundary catalogue, hierarchy, geometry revisions and online ADM1 loading |
| `backend/spatial.py` | Polygon/native-cell overlap weights and spatial support |
| `backend/data_sources.py` | Automatic NASA dispatch, local legacy cache and validated optional imports |
| `backend/nasa_data.py` | CMR discovery, session-only Earthdata authentication, bounded native-grid NetCDF subsets, masking, conversion and disk cache |
| `backend/jobs.py` | Bounded, deduplicated and cancellable in-memory jobs |
| `backend/server.py` | HTTP contracts and scientific orchestration |
| `backend/analysis.py`, `backend/interconnect.py` | Trend, paired contrast, anomaly, lag, multiple-test and conditional diagnostics |

The original controllers remain for compatibility; the new workflow overrides their selection/job/renderer entry points. This is a deliberate integration step rather than a complete rewrite of the original 160 KB controller. Further modularization can be done separately.

## Boundaries

Bundled geographic reference files are separate from scientific observations:

- Countries: Natural Earth 1:50m, from `nvkelso/natural-earth-vector`, source blob `9d99f26dc470fcdbd08b062c813005acbdf73ccb`.
- Ghana: 16 regions, from `virgoaugustine/Ghana-GeoJSON-data`, source blob `495f4d9192fca74256536100b512006ba3702ffc`.
- Other ADM1: geoBoundaries gbOpen API, loaded and cached on demand. Live browser verification loaded 37 Nigerian units and 56 U.S. state/territory units. Other countries use the same on-demand path; availability and administrative conventions depend on the provider.

There are seven continent selections and 240 merged country/territory IDs in this catalogue. Natural Earth’s regional country membership determines continent/subcontinent assignments; these are not physical continent cuts through countries. A country and all disconnected pieces present in the source are one selection. Boundaries describe a cartographic scheme, not an endorsement of territorial claims.

Large fill triangles are adaptively subdivided so they follow the sphere above the ocean. Dateline polygons and line segments are split for the plane view, and shared country edges are removed from parent outlines. The full continent layer builds about 108,000 triangles; a pure geometry benchmark completed in approximately 3.6 seconds on this machine. That is not a browser frame-rate measurement.

## Data contract

CSV input accepts native cell centres, regular declared spacing, monthly dates and one value per cell/month. The uploader supplies catalogue units, collection/version name and citation. Nonfinite values, duplicate cell/month records, irregular grids and unlisted resources are rejected. Empty values and common NASA fill codes are excluded. Provider QA flags must be applied before upload; provenance is uploader-supplied and is not independently certified.

Imports are stored beneath `backend/cache/imports`; boundaries beneath `backend/cache/geography`. Existing cache files are reused without network downloads. Input files persist on disk, while job state/results are in memory and expire after one hour or bounded eviction. Analysis jobs are not durable across a server restart.

The existing POWER cache adapter infers native cells from old point-request coordinates. It is a continuity path, not a validated replacement for an original gridded product. Full selected land area is used as expected support; missing cells are not silently discarded from coverage denominators. Every month needs at least 80% spatial support. Annual inference excludes incomplete years. The default continental selection can correctly report insufficient data with the existing sparse cache.

Use exact dataset names and resource identifiers when importing companion variables. The current companion lookup assumes one version of a given variable per named collection; use a new collection/version name for a revised export. Automatic MERRA-2 ingestion and Earthdata authentication are now implemented, as described in the current README and update below. Original satellite helpers remain source-policy gated.

## Statistical repairs and interpretation

- Actual calendar coordinates are used for Sen and OLS slopes, including missing years. Both A and B expanded trend lines use their fitted intercepts.
- A/B comparisons align common complete years and test the paired difference. Marginal Sen-slope difference is reported separately from the Sen slope of that difference series.
- Regional series use native-cell overlap weights and per-month coverage masks consistently in trend and interconnection paths.
- Remote FDR includes all valid tested candidates before display thresholds. Lag-search correction and an approximate AR(1) effective sample size reduce optimistic association p-values.
- Local pair screening retains full-precision adjusted p-values, avoids controlling for temperature when it is itself a pair member, and does not infer lead direction from an unsupported lag.
- Granger diagnostics use a contiguous complete block. The joint model supports several selected candidate predictors and target history, with conditional F tests and adjusted p-values.

These are exploratory observational diagnostics. Sen intervals and the retained trend/dependence checks are not a complete dependence-aware inference framework for every irregular record. The selected joint model uses the same sample for discovery and fitting; its apparent fit and p-values are not independent validation. Anomaly links alone do not attribute the selected long-term trend. Mechanism descriptions are hypotheses. Map arcs do not track measured winds or water transport.

Remote searches are bounded and disclosed: other continents for a continent source, or a small set of sample countries otherwise. They do not exhaustively compare every global variable/area combination. Fine geographic boundaries do not improve coarse scientific resolution.

## API

| Method and route | Purpose |
| --- | --- |
| `GET /api/catalog` | Variable catalogue, compact geography metadata and year limits |
| `GET /api/geography?level=country&parent=continent:africa` | Active selectable GeoJSON layer |
| `GET /api/geography?level=region&parent=country:gha` | First-level regions for a country |
| `GET /api/data-sources` | Available cache/import providers and source-policy labels |
| `POST /api/data-sources/import` | Validate and persist a normalized monthly grid |
| `POST /api/geography/custom` | Validate and persist a user-defined polygon selection |
| `POST /api/jobs` | Submit `analyze`, `overview`, `scan` or `interconnections` |
| `GET /api/jobs/{id}` | Progress, failure or completed result |
| `POST /api/jobs/{id}/cancel` | Cancel and prevent late result publication |

Job requests include the chosen provider, variables, areas and dates; the server adds method and boundary versions to their identity. Older direct analysis routes remain supported under the explicit source policy. The HTTP server binds to loopback and rejects cross-origin write requests.

## Selection tools update

The map now has explicit blue A and amber B target buttons, mirrored in the variable drawer. Clicking either returns to the map and arms that target. Clicking a boundary no longer silently alternates the target. Drop-down lists remain as an alternative. Each target can use a different method and geographic level, including a boundary for A and a custom footprint for B. Changing the displayed layer preserves both selections. Selected areas outside that layer remain outlined.

| Method | Interaction |
| --- | --- |
| Boundary | Choose a geographic level and click an area; Region has an explicit Country menu |
| Lasso | Drag an outline and release; alternatively click vertices and choose Finish outline. Undo removes a vertex; Shift-drag navigates |
| Circle | Click a centre, adjust radius in km using a slider or number field, inspect covered area, then Use |
| Square | Click a centre, adjust side length in km, inspect covered area, then Use |
| Lat / Lon | Enter west/east longitude and south/north latitude, preview, then Use. West greater than east selects across the dateline |

Custom footprints remain geographic shapes through zoom and globe/plane changes. Circle points use spherical destination calculations; squares use four equal-distance corners with great-circle edges. Area is an approximate spherical polygon surface area using radius 6,371.0088 km, not a screen-area estimate or ellipsoidal survey measurement. Self-intersections, nonfinite coordinates, degenerate outlines and unsupported polar lassos are rejected. Coordinate bounds support wide/dateline extents; circles/squares that would cover a pole require a smaller size or a different centre.

A draft is separate from a committed area. Its controls cannot replace the other target, and a previous area is not reported as the new shape’s preview. Commit uses a stable geometry identity locally. The exact custom GeoJSON is sent as `custom_areas` with the analysis job; the backend independently validates, persists and resolves it before computing. Saved custom input boundaries can be resolved after a server restart. The browser investigation itself is not persisted across page reloads. Existing observations and coverage rules apply to custom areas unchanged.

**Analysis → Graphs & Statistics / Satellite Imagery** makes both destinations explicit. The satellite tab displays the source-setup state even without a trend result. No imagery source was enabled or new scientific dataset downloaded in this UI update. Empty remote screens now distinguish zero valid tests due to insufficient overlap from tested relationships that did not pass the evidence criteria.

The interaction research used NASA Earthdata Search’s spatial selection conventions and CMR’s west/south/east/north and centre/radius semantics, plus OpenLayers’ freehand and regular-shape examples. The implementation stays in the existing Three.js renderer; it does not add a map library.

- [NASA Earthdata Search guide](https://github.com/nasa/GEDI-Data-Resources/blob/main/guides/gedi-earthdata-search.md)
- [NASA CMR spatial query documentation](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html)
- [OpenLayers freehand drawing](https://openlayers.org/en/latest/examples/draw-freehand.html)
- [OpenLayers shape drawing](https://openlayers.org/en/latest/examples/draw-shapes.html)

## Validation and live review

The backend suite passes **131 tests, with one skipped**. The frontend suite passes **24 tests**. Coverage includes stale-response races, independent mixed-method A/B selections, level changes, calendar-aware charts, geodesic size/area checks, dateline and global extents, lasso validation, shared frontend/backend identities, custom-boundary persistence and an imported-data analysis job using a custom footprint. Geometry tests cover curved fills and lasso segments, parent borders, base-mesh country index alignment, plane focus and fitted globe focus. JavaScript syntax, local asset checks, unique HTML IDs and whitespace checks pass.

Desktop browser review exercised lasso vertex/finish/commit, coordinate bounds, circle and square centre placement, size input, approximate area readouts, independent A/B targets, projection changes and the satellite tab. Nigeria’s 37 and the United States’ 56 administrative units loaded on demand; Ghana’s 16 remain bundled. The mixed-method selections stayed intact through layer changes. A pointer-event regression test verifies freehand closure and Shift-drag navigation; browser interaction verification used the click-vertex lasso path. Mobile layout was not visually tested.

The current engine also computed a real Ghana T2M analysis for 2005–2024 from the labeled local POWER cache, with 81.24% area support. A valid computed result can be statistically nonsignificant; missing observations are separately reported as insufficient data. This is a continuity smoke check, not validation of the legacy cache as a challenge-approved source. Live challenge-resource ingestion remains the next stage.

The running browser server already has the first geographic workflow, but it must be restarted to load this update’s custom-selection validation/job contract and catalogue capability flag. The drawing UI works locally before that restart; attempting custom analysis against the older backend displays a restart instruction. From the repository root, stop the previous server, run `python3 backend/server.py 8517`, and reload. Nothing was committed, pushed or deployed.

## Navigation and automatic-data update — 14 November 2026

The persistent bottom-right selection button expands a compact icon rail with A/B targets, boundary/lasso/bounds/circle/square tools and hover/focus labels. Closing the contextual settings card retains access to the rail. A/B have independent clear buttons and clicking a selected boundary deselects it. Both floating panels support pointer dragging, keyboard movement, collapse/expand and locally saved positions. Vertical scrolling zooms, horizontal scrolling orbits/pans, and double-click starts rotation without selecting twice. Wheel input is normalized/capped and close-up motion scales with altitude.

Geographic requests have their own cancellation identity, independent of analysis requests. Mesh construction yields between batches; up to four small administrative layers are retained for reuse. Selected outlines that remain outside the active layer are retained rather than rebuilt for every country. Backend downloads use country-specific locks so one slow country does not block unrelated cached requests. A live HTTP check served Egypt’s 27 cached regions in 0.121 seconds; the geometry build was about 270 ms before reuse. Neither number is a promise for a first online download.

`POST /api/data-sources/earthdata` verifies a pasted token with a one-cell NASA observation before storing it in server memory. `GET /api/data-sources` reports configuration, reader availability and eight supported automatic variables. Tokens are excluded from URLs, status responses and disk caches. The server accepts only allowlisted HTTPS NASA destinations, refuses cross-origin writes and does not follow authentication redirects as if they were data.

Automatic requests use current CMR granule links/revisions, DAP4 native-resolution bounding windows (split at the date line), NetCDF provider masks, strict axis/unit checks, verified conversions, exact polygon overlap and coverage thresholds. Three download workers are bounded globally; cancellation propagates into them. Validated native subsets are cached by collection revision, variable and window. Provenance includes collection/version, field, granule IDs, actual observed dates, cache use and geometry version. Missing granules and cells are never filled. Unsupported automatic variables are named explicitly; scans and local screening use supported fields.

Actual external checks: NASA CMR and KNMI were reachable; CMR listed 261 M2TMNXLND monthly granules for 2005–September 2026. Protected observation access redirected to Earthdata login; no account token is present. KNMI’s anonymous tool presents human verification, and the old NASA Hydrology Data Rods endpoint redirects to a retirement notice. No access gate was bypassed. The implemented automatic route still needs the user to connect Earthdata before a full live scientific download can be verified. NetCDF parsing, conversions, fill masks, provenance, caching and the end-to-end trend pipeline are tested with scientific fixtures.

Run `./start.sh 8517` after stopping the previous server, then reload the browser. The current normal-browser server does not hot-reload Python code. Static UI changes can be previewed before restarting; automatic API routes require the updated process.

Verification after this update: **146 backend tests passed, one skipped, five subtests passed; 35 frontend tests passed**. Syntax checks, shell validation, 286 unique HTML IDs, balanced markup, all 13 local script/style assets and `git diff --check` passed. Browser checks verified the compact rail after closing X, independent primary clear, double-click spin without deselection, a saved 500 km B circle, both panel drag/collapse controls, and Egypt’s 27 regions. The current normal-browser API reports that its Python process needs restarting for the NASA routes. The new backend was separately checked over real local HTTP: automatic source catalogues, reader status, explicit authentication failure and cached Egyptian boundaries. A repeated Egyptian mesh build reused compiled geometry in about **0.41 ms**, compared with **377 ms** for its first progressive build in that benchmark.

## Data readiness follow-up

An older running API no longer silently switches the intended automatic NASA source to the sparse POWER cache. The frontend retains an explicit unavailable NASA option, displays RESTART SERVER, and routes analysis, layer scans and relationship actions to setup before any scientific job is submitted. Choosing legacy cache data remains an explicit user action. A missing NetCDF reader, missing Earthdata connection and unavailable source service have distinct setup states; token entry is disabled while the current server cannot accept it. The page includes the precise local restart command.

Automatic measurement availability now appears in the variable strip and drawer; fields without a source mapping cannot be added accidentally, while already selected unsupported fields can be removed. Variable controls also support keyboard selection. Six new controller regression tests cover source fallback, explicit cache use, setup states, failed discovery, availability and blocked credential submission. All **41 frontend tests** pass. Browser verification against the older normal-browser server confirmed the retained automatic source, RESTART SERVER readout, setup navigation without losing Africa’s selection, visible restart instructions and disabled token input. The protected live data check remains pending server restart/account connection.
