CURRENT UPDATE — sources and presets, 15 November 2026
AppEEARS, NASA Hydrology Time Series and NOAA monthly stations are integrated and live-checked. Giovanni now supports four fields (temperature/humidity at 2 m and 10 m). Linked datasets exposes 20 unique measurement IDs; local relationships are the default, remote requests explicit. The existing globe has a 23-focus-box Presets toggle, preserving independent A/B areas.
Read docs/SOURCES_AND_PRESETS.md and docs/local-handoff/sources-presets-2026-11-15/verification.json first. The usual app remains http://127.0.0.1:8517/. Both Earthdata and AppEEARS connections are remembered privately and were restored after actual restarts. Do not request, print or copy their values. AppEEARS saves its issued token only, never the password; NASA can expire the token.
Ghana NDVI 2016–2024 has 108 real monthly values matching NASA's physical-unit summary exactly. Ghana root-moisture/NDVI found no surviving relationship. A Ghana Savannah GLDAS soil-temperature/Giovanni 10 m air-temperature pair has r≈0.65, 108 overlapping months, no resolved lead. These are exploratory associations, not causes or impact forecasts. AppEEARS returns summary CSVs only, has no additional pixel-QA filter/monthly area audit; NOAA station averages are not area averages. Full source bounds and cache limits are in the report. No presets were silently prefetched.
Latest validation: 217 backend tests passed, one skipped, 43 passing subtests; 68 frontend tests passed. All original paths and the preexisting backend/literature.py deletion are retained. HEAD is unchanged; no commit, push, reset, clean or deployment was performed. Preserve the complete dirty tree. Earlier handoff sections below are historical where they conflict with this update.

CURRENT UPDATE — 15 November 2026
The optional NASA Giovanni rectangle mode and remembered Earthdata connections are now implemented and live-verified.
Read docs/GIOVANNI_INTEGRATION.md, docs/CHALLENGE_RESOURCES.md and docs/local-handoff/giovanni-2026-11-15/verification.json first.
The usual preview at http://127.0.0.1:8517 now runs the updated backend. Its Earthdata key is saved in the desktop credential store and restored after a real restart. Do not request or print it.
Native mode retains eight fields and exact boundaries; optional Giovanni mode uses two M2IMNXASM monthly fields for rectangles and retains charts, discovery and two-rectangle comparisons. No automatic raw-grid fallback.
All work remains uncommitted; preserve it. Session-only-token instructions below describe the earlier state.

# TerraTrend — complete handover for a local Codex session

Prepared 14 November 2026 from the connected Terratrend working directory. This is a continuation of ongoing authorized work, not a request to start a new implementation.

## 1. Read this first

The user wants to continue locally because this conversation began in ChatGPT cloud mode. The project files are accessible and have been edited successfully, but the cloud command environment cannot control the Python process serving the user's normal-browser localhost preview. Do not carry that limitation over to a genuine local session without checking its actual capabilities.

**The UI overhaul is implemented. The next operational step is to start the updated backend locally, then connect NASA Earthdata and verify a real observation download.** The existing normal-browser server was still the old cache-only process at the last browser check. The browser now clearly reports **RESTART SERVER** rather than silently using sparse POWER cache data.

A complete live scientific download has **not** been verified. Do not describe fixture tests or public catalogue discovery as a completed live data integration. There is no Earthdata token configured in this executor's environment; a different local environment may already have one. Check presence/status only, never print credentials.

All work is uncommitted. The working tree already contained significant edits before this agent worked on it. Preserve the entire current working tree, including untracked files, existing deletions and unrelated edits. Do not reset, clean, checkout over it, replace it with a fresh clone, or create a new worktree that drops uncommitted changes. Nothing has been committed, pushed, merged or deployed.

## 2. Exact workspace and relevant files

Primary project, the original engine plus the implemented overhaul:

```text
/home/templar/Documents/Projects/Nasa Space APP/Terratrend
```

Sibling prototype used as a globe/mesh reference:

```text
/home/templar/Documents/Projects/Nasa Space APP/TerraTrend 2
```

The user's speech used TerraTrend/TerraTrench inconsistently. These are the actual paths; keep the original **Terratrend** directory as the integration target. Other nearby projects, including Martian Map and trend-detective, are not the target.

Recorded Git state before handover files were added:

- Branch: `dev`
- HEAD: `2fbda28faa2fb9467535d690669c610737457732`
- 13 tracked paths modified/deleted; 39 nonignored untracked files.
- One Git remote is configured; no remote operations were performed for this handover.

Read these current files before substantial edits:

1. `README.md` — current startup, controls, data access and limitations.
2. `docs/UI_OVERHAUL_IMPLEMENTATION.md` — detailed integration history, contracts and validation.
3. `docs/UI_OVERHAUL_REVIEW.md` — original review of both projects and the video requirements.
4. This handover and `docs/local-handoff/manifest.json`.
5. Applicable local `AGENTS.md` instructions, if any.

`docs/LEGACY_README.md`, parts of `docs/ROADMAP.md`, old screenshots and existing algorithm PDFs are historical context. Some old demo/scientific claims and earlier proposed integrations are stale; the current source and current README govern behavior.

Relevant media, if visual reinspection is needed:

- Primary project `IMG_8547.MOV` (121,743,779 bytes).
- Primary project `videos/new UI inspiration video.MOV` (159,052,998 bytes).
- Sibling `TerraTrend 2/IMG_8561.MOV` (159,052,998 bytes).

The user provided the spoken transcript because audio was important. Its requirements are summarized below; do not ask them to transcribe it again.

## 3. What the user actually wants

### Original video and integration request

- Preserve and extend the original project's real scientific engine; use the sibling prototype's globe and visual reference where useful. Do not adopt randomized prototype events or demonstration values as science.
- A Kaspersky Cybermap-inspired, map-first interface: https://cybermap.kaspersky.com/ . Keep the app branded TerraTrend. The user likes the current olive visual direction and current boundary selection behavior; do not replace it with a different design.
- A hideable variable drawer, globe and plane views, and explicit Analyze actions that open dedicated scientific results.
- Four independent geographic levels: continent, subcontinent, country and first-level administrative region. Each unit has its own calculation, not an inherited parent verdict. Ghana regions were the first example; extend globally where source boundaries permit it.
- Hover/highlight/select whole units, including disconnected country pieces/islands. Geography level changes what can be picked.
- Show increasing, decreasing, nonsignificant and insufficient-data outcomes distinctly. A missing observation is not a finding of no trend.
- Compare two independently selected areas at any supported level, using the same variable and time window. Investigate inverse and same-direction relationships.
- Investigate candidate incoming drivers and outgoing responses, including multiple variables. Animated connections should reflect computed evidence; do not claim physical causation or measured wind transport from correlation alone.
- Use challenge-listed science resources, not arbitrary replacement sources. The user explicitly wants the app to fetch data automatically; they do not want to download/normalize/upload CSVs to make core features work.

### Later selection/UI requirements

- Independent blue **A / Primary** and amber **B / Comparison** map-picking targets. Clicking B should arm picking on the globe, not force a dropdown.
- Boundary selection plus freehand/clicked lasso, latitude/longitude bounds, a circle with radius in kilometres, and a square with side length in kilometres. Centre dot and approximate covered area; A and B can use different methods.
- Persistent bottom-right selection icon. Clicking expands a compact icon rail with tooltips; it must remain accessible after closing the settings card. Only show contextual controls for the chosen method, rather than opening the whole workbench for every action.
- Allow clearing A/B, including the primary area.
- Vertical scroll zoom; horizontal trackpad scroll moves/orbits left/right; double-click starts globe spinning. Soften wheel zoom and close-up dragging.
- Improve administrative-region loading, particularly Egypt, and communicate first-time loading.
- Draggable, collapsible floating panels so plane-view North America is not obscured.
- Human-readable variable names on the bottom strip, with technical IDs/units retained in tooltips.
- Retain expanded graphs/statistics and the satellite-imagery panel under Analysis.

### Collaboration preferences

The user expects implementation and persistence, not repeated proposals, permission questions or vague blockers. Continue authorized reversible work autonomously. Explain a real blocked step precisely. Keep the working UI, verify changes, and do not invent results. Ask the user only for the account action or truly missing input that cannot be obtained from the project. Do not ask for a challenge URL, video transcript or manual CSV imports again as a substitute for integration.

## 4. What is already implemented

### Interface and map

- Olive map-first chrome, compact navigation, geography-level/scope controls, variable drawer, A/B area card, bottom variable strip and legend.
- Dedicated Map, Analysis, Compare, Interconnections and Data & Methods screens.
- Local Three.js renderer using the sibling country's/coast mesh. Reference-map triangles and dateline handling were repaired; do not regress the country face-range fix, adaptive sphere tessellation, shared parent-edge removal or Mercator splitting.
- Full Polygon/MultiPolygon selections with stable geographic IDs and geometry revisions. Seven continents and 240 merged country/territory IDs in the current catalogue.
- Ghana's 16 regions bundled. Other countries use on-demand geoBoundaries gbOpen ADM1 loading and disk caching when available. Browser checks loaded Nigeria (37 units), USA (56 state/territory units) and Egypt (27 governorates). Global country picking works; administrative coverage still depends on the reference provider.
- Independent A/B selections survive displayed-layer changes and globe/plane changes. Custom boundaries also survive those changes.
- Lasso drag-to-close and click-vertices/Finish; Shift-drag navigates while lasso is active. Circle/square centre and kilometre size controls; decimal W/S/E/N bounds including antimeridian crossing. Invalid or self-intersecting shapes are rejected.
- Preview versus committed selections, stable frontend/backend custom polygon identities, validation and persistence. Analyze sends exact custom boundaries through the new backend contract.
- Persistent compact selection rail, A/B targets, accessible labels/tooltips, contextual settings, clear buttons and same-boundary deselection.
- Horizontal wheel orbit/pan; normalized/capped vertical zoom; altitude-scaled close-up zoom/drag. Double-click starts spin without treating both clicks as selection toggles. Drawing tools keep their own interactions.
- Both area/results and selection-settings cards are draggable and collapsible. Keyboard arrows on the grip move panels, Shift makes a larger step. Saved positions/collapse state are clamped inside the map after resizing.
- Administrative requests have separate cancellation identities from science requests. Progressive geometry construction yields between batches and up to four small administrative layers reuse compiled meshes. Selected overlays are retained when their geometry/membership has not changed.
- A benchmark built Egypt's 27 meshes in about 377 ms and reused them in 0.41 ms. A local HTTP check served cached Egyptian GeoJSON in 0.121 s. These are observations, not guarantees for first-time external downloads or browser frame rates.
- Friendly variable names and active-strip scrolling. Keyboard-accessible variable controls.

### Scientific orchestration

- Original charts, expanded observatory/statistics, glossary, scans and export retained through compatibility controllers.
- Exact polygon/native-cell overlap weights with a documented small-cell `cos(latitude)` approximation. At least 80% selected-area support is required per month; incomplete years are excluded from annual trend tests.
- Sen/Mann–Kendall calculations preserve actual calendar coordinates across gaps. A/B inference aligns common complete years and analyzes the paired difference; expanded fitted lines use each area's intercept.
- Exploratory anomaly/lag relationships, multiple-testing correction, conditional diagnostics and separate association-sign/lead-direction evidence. Do not describe these as established physical causes.
- Bounded jobs: two scientific workers, deduplication, progress, cancellation, immutable selection/method/geometry identities and stale-response rejection. In-memory jobs/results expire or are evicted; they do not survive server restart.

### Last source-readiness follow-up

- The intended default remains `nasa-merra2` even when an old API lacks that provider. The frontend does not silently select POWER cache instead.
- The header shows **RESTART SERVER** and **Set up NASA** for the older live server. Analysis, Analyze Layer, Scan and Interconnections route to setup without submitting a science job when the source is unavailable.
- Reader missing, account connection missing and source-service failure are distinct states. Token entry is disabled while the running server cannot accept the connection.
- Cache-only analysis remains available only if the user explicitly selects that provider.
- Unmapped automatic measurements are marked in the drawer and disabled on the strip. Already selected unsupported measurements can still be removed.

## 5. Automatic NASA data: implemented versus actually verified

The challenge found in the project is:

https://www.spaceappschallenge.org/2026/challenges/earth-system-trend-detective/

Title: **Be An Earth System Trend Detective!**

The video/project resources include Giovanni, Hydrology Time Series, AppEEARS, Climate Data Online, KNMI Climate Explorer, and a SeaWiFS time-series study/reference. Older roadmap text labels Hydrology Time Series as CUAHSI; do not treat that as verified equivalence to the GES DISC tool. The NASA Hydrology Data Rods URL tested during this work redirected to a retirement notice. KNMI's anonymous interface presented human verification. No gate was bypassed.

POWER and GIBS were not among the visible video resource links. Existing POWER cache is explicitly legacy/unverified. New map workflow requests do not silently use live POWER, and existing imagery helpers remain source-policy gated.

The automatic provider uses current NASA CMR discovery and the current GES DISC OPeNDAP service for MERRA-2 collections exposed by Giovanni. It requests native grid windows, not bbox-averaged time series represented as exact polygons.

| Catalogue ID | Measurement | Collection / field | Source conversion |
| --- | --- | --- | --- |
| T2M | Air temperature | M2TMNXSLV / T2M | K to °C |
| TS | Surface temperature | M2TMNXSLV / TS | K to °C |
| QV2M | Specific humidity | M2TMNXSLV / QV2M | kg/kg to g/kg |
| PS | Surface pressure | M2TMNXSLV / PS | Pa to kPa |
| GWETROOT | Root-zone soil moisture | M2TMNXLND / GWETROOT | Saturation fraction retained |
| GWETTOP | Surface soil moisture | M2TMNXLND / GWETTOP | Saturation fraction retained |
| EVLAND | Land evaporation | M2TMNXLND / EVLAND | kg m⁻² s⁻¹ to mm/day |
| PRECTOTCORR | Precipitation | M2TMNXFLX / PRECTOTCORR | kg m⁻² s⁻¹ to mm/day |

Collection version: **5.12.4**. Native spacing: **0.625° longitude by 0.5° latitude**.

Collection concept IDs currently used:

- M2TMNXSLV: C1276812859-GES_DISC
- M2TMNXLND: C1276812856-GES_DISC
- M2TMNXFLX: C1276812868-GES_DISC

Data path:

1. Public CMR granule discovery uses actual published months, URLs and revisions.
2. Earthdata bearer-authenticated DAP4 subsets include the selected field plus latitude/longitude axes. Dateline windows split to avoid fetching an unnecessary global span.
3. NetCDF parser validates axes, shapes and units, excludes provider masks/fill values and performs declared conversions.
4. Only intersecting native cells enter the exact selected polygon's aggregation, with complete selected-area support as denominator.
5. Validated scientific subsets are cached by field, revision and native window. Granule metadata have a one-day cache. Three bounded download workers propagate job cancellation.
6. Provenance includes dataset/version/field, granule IDs, actual observed months, geometry revision, source coverage, retrieval time and cache use.

Live external verification on 14 November 2026:

- NASA CMR and KNMI were reachable from the command environment.
- CMR listed **261 M2TMNXLND monthly granules from January 2005 through September 2026** for the requested 2005–2026 period.
- An actual one-cell OPeNDAP observation request redirected to Earthdata login (HTTP 302; following login reaches 401).
- No bearer token was available here. A full live observation download and real regional analysis through this provider are **pending**.
- NetCDF reading, fill handling, unit conversion, caching, provenance, cancellation and the end-to-end trend pipeline were verified with scientific fixtures. Fixtures are not live observations.

The remaining original catalogue fields do **not** yet have verified automatic mappings: T2M_MAX, T2M_MIN, T2M_RANGE, RH2M, EVPTRNS, WS2M, ALLSKY_SFC_SW_DNI and ALLSKY_SFC_LW_DWN. Scans/local relationship screening use supported fields. Do not substitute the magnitude of monthly mean wind components for mean wind speed, monthly extreme maxima for means of daily maxima, or absorbed radiation for direct normal irradiance. Audit legacy field definitions/units carefully before extending mappings, particularly EVPTRNS.

Earthdata handling:

- `Data & Methods → Connect Earthdata` accepts a user-generated token and verifies it by reading a real one-cell T2M subset before storing it in server memory.
- `EARTHDATA_TOKEN` in the server environment is also supported.
- Tokens are not written into the repository, disk cache, URLs, browser storage or status responses.
- Do not request a token in chat, read unrelated credential files, generate fake tokens or bypass NASA authorization. The user can connect through the app; preserve normal Earthdata/GES DISC authorization requirements.

## 6. Immediate local-session runbook

1. Confirm the primary path, branch, HEAD and dirty working tree. Compare with the handover manifest before editing. A difference may be a newer user edit; preserve it rather than restoring blindly.
2. Inspect the process listening on **127.0.0.1:8517** using the local environment's normal tools. Identify its command and working directory. Stop only the verified old TerraTrend server if a restart is needed; do not kill all Python processes or unrelated servers.
3. Start the current project in a normal local terminal/process, keeping it alive beyond a short tool cell:

```bash
cd '/home/templar/Documents/Projects/Nasa Space APP/Terratrend'
./start.sh 8517
```

The script creates/reuses `.venv`, installs missing dependencies from `requirements.txt`, and runs `.venv/bin/python backend/server.py`. Requirements are NumPy, SciPy, Requests and NetCDF4. In the current workspace those packages are installed. `pytest` is needed for tests; Node is needed for frontend tests. No npm build is required.

4. Check the real running API, not only imported Python functions:

```text
GET http://127.0.0.1:8517/api/health
GET http://127.0.0.1:8517/api/catalog
GET http://127.0.0.1:8517/api/data-sources
```

Expected: `automatic_data: true`, `custom_selections: true`, provider `nasa-merra2`, and Earthdata status with `reader_installed: true`. The last cloud browser check still had an older server without those automatic-source capabilities.

5. Reload the page. If no token is already available locally, complete the one necessary user account step through Data & Methods. Work on independent remaining items while waiting if appropriate. Do not ask the user to manually upload data.
6. Verify connection with the real one-cell request. Then use **Ghana, 2005–2024, Root-Zone Soil Moisture** or Air Temperature for the first regional download. Prefer a bounded country example over a first request for every continent and variable. Record actual source granules, units, masks, observed dates and area coverage; accept the scientifically valid result, whether significant or not.
7. Check a second variable and A/B comparison, cache reuse, cancellation and stale-result handling. Verify a drawn circle or lasso passes its exact saved polygon to analysis. Expand Analysis graphs and inspect exported observed dates/coverage.
8. Continue verified mappings for the remaining variables and the challenge-approved satellite imagery route. Keep unsupported fields explicit until implemented and checked. Large global layer scans can be expensive; native resolution must not be replaced by invented high-resolution observations.
9. Keep the existing UI and check for regressions rather than starting another visual overhaul. Do not commit/push/deploy without a separate user instruction.

## 7. Key implementation files

| File | Responsibility |
| --- | --- |
| frontend/index.html | Map-first shell, screens, tool rail, area controls and NASA setup |
| frontend/overhaul.css | Final theme/layout, responsive controls and setup styling |
| frontend/earth-renderer.js | Three.js geometry, globe/plane morph, picking, overlays, navigation, mesh reuse |
| frontend/selection-geometry.js | Geodesic shapes, bounds/lasso validation, area and stable custom identities |
| frontend/selection-tools.js | A/B target arming, preview/commit/clear and contextual controls |
| frontend/map-panels.js | Panel drag, collapse, keyboard motion and bounded saved positions |
| frontend/workflow.js | Selection/source state, jobs, readiness gates, geographic requests and compatibility overrides |
| frontend/app.js | Retained charts, glossary, observatory, exports and legacy controllers; variable accessibility |
| frontend/vendor/ | Bundled Three.js, chart libraries and other local JavaScript assets |
| frontend/data/ | Natural Earth country features, Ghana regions and sibling globe mesh |
| backend/geography.py | IDs, hierarchy, geometry revisions, custom validation and gbOpen ADM1 cache |
| backend/spatial.py | Native-cell/polygon overlap and coverage-aware weighted series |
| backend/nasa_data.py | CMR, Earthdata, native NetCDF subsets, conversions, cancellation and cache |
| backend/data_sources.py | Automatic adapter dispatch, optional import validation and legacy cache |
| backend/jobs.py | Bounded cancellable/deduplicated in-memory jobs |
| backend/server.py | Local HTTP API, source/catalogue contracts and scientific orchestration |
| backend/analysis.py, backend/interconnect.py | Trend, paired contrast, anomaly/lag and conditional diagnostics |
| backend/catalog.py | Variable metadata, spheres and legacy focus regions |
| backend/gibs.py | Retained imagery helpers, currently policy gated |
| start.sh, requirements.txt | Local startup and Python dependencies |

New HTTP contracts in addition to retained legacy routes:

- GET `/api/geography?level=continent|subcontinent|country|region&parent=...`
- POST `/api/geography/custom`
- GET `/api/data-sources`
- POST `/api/data-sources/earthdata` with token or `{ "disconnect": true }`
- POST `/api/data-sources/import` for optional advanced normalized imports
- POST `/api/jobs`; GET `/api/jobs/{id}`; POST `/api/jobs/{id}/cancel`

Job operations: `analyze`, `overview`, `scan`, `interconnections`. Common fields include region ID, variable IDs, start/end year, provider; A/B uses compare_region; custom selections use custom_areas. Backend adds method and geometry versions. Trace the existing controller contract before changing it.

## 8. Validation at handover

Freshly rerun during this handover:

```bash
.venv/bin/python -m pytest backend -q -p no:cacheprovider
# 146 passed, 1 skipped, 5 subtests passed

node --test tests/*.test.cjs
# 41 passed, 0 failed
```

That is **187 passing tests, plus five passing subtests, with one skipped backend test**. Syntax/shell checks, HTML checks and `git diff --check` had also passed during implementation. Rerun appropriate checks after new source changes, not repeatedly without a reason.

Important coverage includes sphere/dateline geometry, mesh reuse, lasso versus navigation, close-up input scaling, horizontal wheel/pinch normalization, double-click without selection changes, independent A/B clearing and method retention, stale response rejection, paired calendar slopes, custom API identity, NetCDF masks/units/axis checks, exact spatial coverage, observed-month gaps, cache reuse, authentication handling and automatic-source readiness/fallback behavior.

Normal-browser checks performed before handover:

- Persistent rail reopens after X; toolbar-only open does not reveal a large settings panel.
- A clears independently; double-click spins while retaining A.
- A Africa and a committed B circle of radius 500 km coexist; circle area about 784,358 km².
- Both floating cards were dragged and collapsed; plane North America is clear.
- Egypt's 27 governorates loaded; horizontal plane scroll changed x positions without changing y.
- Friendly variable names and active-strip scrolling work.
- Old-server detection retains NASA as the intended source, reports RESTART SERVER, opens setup, retains Africa while navigating and disables the unusable token form.

Screenshots are copied under `docs/local-handoff/screenshots/`. They document UI state before live NASA connection, not results computed from newly downloaded observations.

## 9. Working-tree preservation and recovery snapshot

Significant dirty paths existed before the overhaul. Recorded tracked changes include `.gitignore`, README, backend analysis/catalog/interconnect/power_client/server and tests, and frontend app/index/styles. `backend/literature.py` is deleted in the existing working tree; a disabled historical file is also present locally. Do not restore either automatically or assume all changes in these files belong to this single session.

Many essential new implementation files are untracked. A Git pull, clean clone or worktree based only on HEAD will omit them. Continue in the existing folder.

The handover bundle contains:

- This handover and the starter prompt.
- A manifest with source hashes, file sizes, base commit, branch, Git status and test counts.
- A binary-safe patch of tracked changes against the recorded HEAD.
- A snapshot of current nonignored project files and local data caches, with deleted paths recorded in Git status/patch.
- UI screenshots.

The bundle excludes Git internals, virtual environments, private credential/configuration files, temporary process state, and the very large videos. It does not migrate a running server, in-memory jobs or an Earthdata session token. The videos remain in the original folders listed above.

**This bundle is for recovery/reference. Do not unzip it over newer work or apply its patch to the already-modified folder blindly.** Prefer verifying the existing local working tree against the manifest. The full current files are under `project/` inside the ZIP, while `handoff/` holds supporting state. If recovering into a fresh checkout of the exact base HEAD, review the tracked patch and untracked snapshot carefully and preserve recorded deletions. Do not restore excluded credentials from unrelated locations.

## 10. Cloud-to-local handoff status

The app tool describes direct cloud handoff as unsupported. Its saved-project listing request failed twice in this cloud conversation, so no saved local project ID could be resolved. A separate local-session creation was then attempted with the complete starter prompt and explicit existing-project path; the create_thread request also returned an app connection error, with no thread ID or confirmed success. Automatic session creation/delivery could not be verified. Do not claim that the whole chat history was transferred, and do not repeatedly create duplicate tasks. If a partially created local task appears in the app, inspect it before creating another.

Use `CONTINUE_LOCALLY.txt` as the initial prompt of a real local Codex session attached to the primary folder. The prompt and this handover carry the task state. If an automatic local task is created separately, it must use this same existing directory, not an empty output folder or a clean checkout.

## 11. Known limits and follow-ups worth reviewing

- The primary outstanding verification is a protected real NASA observation download after account connection. A code path being present and fixtures passing do not prove remote interoperability with the user's token/service permissions.
- Review the exact current OPeNDAP subset response with valid credentials before declaring all eight routes live-ready. Validate source units/coordinates and any redirects rather than weakening TLS or following login pages as data.
- Unmapped original fields and satellite imagery remain incomplete. No physical attribution or wind trajectory model has been implemented by the statistical connection display.
- Native source cells are coarse and can be shared by multiple small administrative units. Sharp boundaries do not create more scientific resolution.
- Spatial weights use the documented cell-overlap/cos(latitude) approximation; this is not a full equal-area GIS integration.
- Parent membership follows a country-based UN cartographic grouping, not physical continent cuts across transcontinental countries. Small islands missing at source resolution cannot be recovered by UI logic.
- First-time country boundary and long-period science downloads depend on external service speed. Cached timings above are not promises of instant first access.
- The large compatibility controller is intentionally retained; modularization is a possible later task, not a reason to rewrite working features now.
- Follow-up robustness candidates, not completed claims: handle HTTP-date Retry-After values; review cancellation responsiveness during spatial planning/network timeouts; ensure source errors stay informative in all job types. Address these only when relevant to real local verification.
- Source/licence attribution for reference boundaries and any reused visual assets must remain available; review before a future public release. There is no current instruction to publish.

Proceed from the local runbook and report concrete observed results. Preserve the user's progress and avoid another cycle of asking them to continue without completing the authorized work.
