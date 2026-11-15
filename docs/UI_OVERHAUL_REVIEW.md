# TerraTrend UI overhaul and integration review

Reviewed 14 November 2026. This review records the plan prepared before implementation, grounded in both working directories, the reference video’s visuals, and the supplied transcript. The overhaul has since been implemented in the original repository; see [the implementation notes](UI_OVERHAUL_IMPLEMENTATION.md) for current behavior, validation, and remaining limitations.

**Recommendation: use the original `Terratrend` repository as the integration destination, retain and repair its scientific analysis, and adapt TerraTrend 2's globe behind a small renderer interface. Rebuild the application controls and navigation around the transcript.** Copying the newer folder over the original would lose functioning application features and carry demonstration data into scientific results.

## Requirements established by the transcript

The timestamps below refer to the user's transcript sections. They are requirements references, rather than verified frame-accurate timings.

| Transcript | Required behavior | Implementation consequence |
| --- | --- | --- |
| 00:00–00:24 | Full-screen globe, collapsible variable drawer, explicit Analyze action | Land on the map; selecting an area or variable prepares a request rather than immediately running every expensive analysis |
| 00:24–00:46 | Globe and plane views | Both projections share geographic IDs, selected areas, colors, results, and overlays |
| 00:46–01:25 | Analyze the entire selected continent | A continent boundary determines the data mask and aggregation; moving the camera to Africa is insufficient |
| 01:25–02:00 | Subcontinental differences remain visible | Compute each subdivision independently; do not assign the continent's verdict to all its children |
| 02:00–02:44 | Country outlines and trend colors | A true choropleth layer, with distinct values for each analyzed country |
| 02:44–03:22 | First-level regions within countries, globally if feasible, Africa as a fallback | Load administrative boundaries separately; Ghana's Ashanti and Greater Accra are administrative regions, unlike the existing ecological focus boxes |
| 03:22–05:08 | Hover and select only the geographic level currently active | A four-position level control changes the hit-testing layer and highlight geometry |
| 03:22–05:08 | Investigate variables and processes associated with a trend | Discover candidate relationships beyond the variable currently displayed; expose the evidence for each explanation |
| 05:08–05:50 | Compare two selected areas at any supported level | The same A/B workflow must accept continents, subcontinents, countries, and administrative regions |
| 05:50–06:17 | Whole-country selection includes islands | Use complete Polygon/MultiPolygon geometries, stable IDs, and shared frontend/backend boundaries |
| 06:17–06:40 | Closely follow the Kaspersky Cybermap layout | Match the spatial layout, globe treatment, restrained typography, floating panels, and compact controls; use TerraTrend names and scientific content |
| 06:40–07:15 | Show what precedes the selected change and what follows it, locally and remotely, involving one or several variables | Separate candidate drivers, downstream responses, and simultaneous relationships; retain ambiguity when direction cannot be supported |
| 07:15–07:34 | Use the challenge resources shown in the project | Enforce a dataset/provider allowlist and attach provenance to every scientific result |

## What is actually present in the two projects

Both folders contain an identical copy of the newer reference video. The original also contains an older, different video. The newer video and its copy at `videos/new UI inspiration video.MOV` have the same SHA-256 hash.

| Component | Original `Terratrend` | `TerraTrend 2` | Integration decision |
| --- | --- | --- | --- |
| Trend statistics | Mann–Kendall, Theil–Sen, confidence intervals, seasonal checks, autocorrelation diagnostics | `analysis.py` is byte-for-byte identical | Preserve; fix identified edge cases |
| Interconnections | Seasonal decomposition, lag search, partial correlation, two-way Granger tests, anomaly summaries | `interconnect.py` is byte-for-byte identical | Preserve as a starting point; strengthen inference and direction handling |
| Application features | Multiple variables, scans, charts, A/B contrast, interconnections screen, grid inspection, exports, satellite comparison | Much smaller replacement controller with incomplete wiring | Port original feature controllers into the new application shell |
| Globe | Custom Three.js presentation, custom-area picking, labels, scientific overlays | Country mesh, country picking/borders, shaders, textures, globe/plane projection pipeline | Prefer the newer renderer for visual continuity; isolate it from scientific calculations |
| Geography | Preset rectangular focus areas and custom rectangles | Adds focus boxes, country IDs, and a country-centre fallback box | Replace with one real geographic catalog |
| Cache | Existing disk cache | Adds a lock around cache-index initialization/invalidation | Review and port the synchronization improvement |
| Scientific event display | Calculated remote-link response is available | Random binary event feed, static remote-link rows, example statistics on fetch failure | Connect typed scientific results directly; remove fabricated scientific states |

Important code evidence:

- `TerraTrend 2/backend/server.py`, `generate_planetary_events()`: generates random event counts and hard-coded country pairs. This is not the teleconnection analysis engine.
- `TerraTrend 2/frontend/app.js`, `fetchTerraTrendData()`: failure handlers substitute specific positive trend and coupling values. Static initial values also appear in `frontend/index.html`.
- The same controller's `openRegionalContrast()` shows an alert with a fixed divergence value; it does not perform A/B analysis.
- Its remote-link rows are static HTML. The controller does not fetch the scientific `/api/teleconnections` endpoint.
- `TerraTrend 2/backend/catalog.py`, `_init_country_cache()`: represents countries by a box extending 2.5 degrees from a map centre. That is not an analysis of the national territory. Ghana selection is separately mapped to the `ghana_south` focus region.
- `TerraTrend 2/frontend/index.html`, `focusContinent()` and `focusSubcontinent()`: attempt camera movement without establishing a geographic selection or analysis. Their camera reference also differs from the renderer's exposed `MAP._env.geocam` state.
- The newer satellite modal initially shows the same global topology image as both historical and recent evidence. Opening the modal does not fetch the original satellite-comparison result.
- The original `frontend/app.js` uses `REGION_MAG = 2.8` to spread plotted sample positions for visibility. Scientific map overlays should retain their actual coordinates; display amplification belongs in a clearly labeled inset.

The newer README describes more functionality than these application paths implement. Code and runtime acceptance checks should be the basis for integration.

## The proposed user experience

Open directly into a Kaspersky-like map with a large olive globe, dark background, fine borders, compact header, left floating area card, right map controls, and a bottom legend. Keep the map visually dominant. Put explanations and large charts on separate screens.

Use primary navigation for **Map**, **Analysis**, **Interconnections**, **Compare**, and **Data & Methods**. Retain the same header and the current investigation when moving between them. The main action is **Analyze**.

| Existing feature or new requirement | Location in the new interface |
| --- | --- |
| Sixteen variables and Earth-sphere filters | Collapsible Variables drawer; one active variable colors the map, with additional selected variables available in charts |
| Date range and data availability | Compact investigation controls in the drawer; actual valid date range in results |
| Continent / subcontinent / country / region | Four-stop segmented level control over the map, independent of zoom |
| Geographic context | Breadcrumb such as World → Africa → West Africa → Ghana → Ashanti |
| Hover and selection | Subtle hover outline; persistent A/B selection outlines with labels; search/list access for tiny islands and keyboard use |
| Selection summary | Compact floating card with name, level, selected variable, coverage, trend rate, and evidence state |
| Trend results and enlarged observatory | Dedicated Analysis screen with monthly/yearly charts, trend line, confidence interval, significance checks, and sample coverage |
| Per-cell inspection and consensus | Spatial-detail panel inside Analysis, preserving true sample coordinates |
| Scan all variables | Discover action in the drawer, with a ranked results view on Analysis |
| Local coupling, global links, anomaly history, impact ledger | Interconnections screen with Drivers, Responses, and Anomalies views; map links open the matching evidence card |
| Regional contrast | Compare mode: select A and B, choose variable/window, then Analyze; dedicated comparison results |
| Satellite comparison | Evidence tab, retaining the original comparison controls when the imagery provider is permitted by the data-source policy |
| CSV export | Analysis and Compare actions |
| Resource links, glossary, statistical definitions | Data & Methods screen and contextual help |
| Globe/plane, zoom, rotation, reset | Compact right-side map controls |

Selection and analysis are separate states. A stale result must never remain labeled as the result for a newly selected geography, variable, or date range. Show a pending or out-of-date state until a matching result is ready.

**Single-area workflow:** choose level → hover/select area → choose variable and dates → Analyze → show a concise result card with polygon color → open detailed Analysis or investigate Drivers/Responses.

**Comparison workflow:** enable Compare → select A and B at the active level → choose the same variable, dataset, and common time window → Analyze → compare slopes, uncertainty, and associated relationships. Different colors alone do not establish a statistically significant difference.

At each level, use independently computed results to color the visible units. A continent's aggregate and its children's individual trends can legitimately disagree. In-scope overview results should load from precomputed summaries or bounded background jobs; uncomputed units remain visibly uncomputed.

Use separate states for significant increase, significant decrease, no statistically significant trend, insufficient data, and pending/not analyzed. Red and blue can represent increase and decrease. Keep no-significant-trend neutral so decreasing values are distinguishable. Selection outlines must remain readable over every fill.

## Can the existing globe support the requested selection?

**Yes, as an engineering extension. The complete four-level system is not already implemented.**

The newer renderer has actual country triangles, per-country face ranges, boundary indices, a GPU picking pass, and a globe/plane projection pipeline. That is a usable foundation for hover, selection, outlines, and result fills.

| Requested interaction | Existing foundation | Required work |
| --- | --- | --- |
| Rotate, zoom, globe/plane | Renderer and projection code exist | Verify controls and preserve overlays through projection changes |
| Hover/select a country | Country GPU picking and border drawing exist | Connect stable geographic IDs, replace centre-box analysis, support persistent A/B outlines |
| Select an entire continent or subcontinent | Countries can provide some building blocks | Add explicit parent geometries and hit testing; combine or split meshes where the geographic scheme requires it |
| Select Ashanti or another administrative region | No general first-level administrative polygon layer | Add and triangulate administrative boundaries, with their own picking IDs and parent-country relationships |
| Include all islands | Country mesh has disconnected components | Obtain complete geographic boundaries for both analysis and display; do not rely on the simplified 176-entry display mesh as exhaustive coverage |
| Color each geographic unit by its trend | Shaders and per-country mesh ranges exist | Add a result layer keyed by geographic ID and active variable; implement the same layer for all four levels |
| Select two units | Can build on picking | Maintain two selection slots, separate outlines, and consistent comparison payloads |
| Click an animated scientific link | Missile/arc presentation machinery exists | Replace its event feed with computed relationship objects and evidence lookup |

A country-to-continent lookup alone is not sufficient for every boundary: transcontinental countries require an explicit continent scheme. At country level, the whole country's MultiPolygon remains one selection. At continent level, the selected geometry follows the chosen continent definition.

Create a renderer adapter with operations such as `setProjection`, `setLevel`, `setBoundaries`, `setSelections`, `setTrendResults`, `setConnections`, `focusFeature`, and `onFeatureHover/onFeatureSelect`. Keep application state and calculations outside the minified renderer. Boundary overlays and picking must share the same projection mathematics; disable selection during morphing unless intermediate-projection picking is verified.

**Fallback recommendation: CesiumJS**, styled with the same TerraTrend shell. Its official APIs support scene picking, globe-conforming polygon hierarchies, and 2D/3D transitions. This would replace the rendering implementation; it would still need our administrative data, geographic model, and scientific aggregation. First validate the existing renderer with country selection plus one Ghana administrative layer in both projections. Switch renderers if that integration cannot meet correctness or measured performance requirements.

## The engine work this requires

**1. Shared geography.** Introduce stable feature IDs, level, parent/child relationships, complete Polygon/MultiPolygon geometry, geometry version, and display bounds. Administrative regions and ecological focus areas must be separate concepts. Define continent/subcontinent membership explicitly, including transcontinental cases. Handle holes, islands, enclaves, antimeridian crossing, and small areas.

**2. Real spatial aggregation.** A bounding box becomes a data-download envelope, not the definition of the measurement. Mask native data cells to the selected geometry and area-weight their contributions, including partial boundary cells. Retain coverage and unique native-cell counts. Calculate a regional time series first and run the trend test on it. Report spatial variation separately; averaging already-classified child colors or counting 25 arbitrary sample points is not a continental estimate.

**3. Data adapters and provenance.** Preserve the analysis routines independently of data retrieval. The resource screen in the video lists Giovanni, Hydrology Time Series, AppEEARS, Climate Data Online, a SeaWiFS time-series study, and KNMI Climate Explorer. POWER and GIBS are not among the links visible in that frame. Do not assume NASA branding automatically satisfies the user's stricter source restriction. Document permitted service/dataset/access routes before enabling them, and use the listed resources and their documented supported data access routes for the new pipeline. Keep dataset ID, variable, units, native resolution, quality flags, valid dates, processing version, and source attribution with every result. Large downloads or Earthdata access may need separate dataset-specific preparation; a resource website is not itself a ready-made application API.

**4. Bidirectional relationship discovery.** Given the selected area and variable, evaluate plausible local and remote candidate variables, retaining whether candidates precede, follow, or have no clear lead relative to the selected series. Separate signed association from temporal direction: an inverse relationship can still be an incoming or outgoing link. Animate along the supported lead direction; show simultaneous or ambiguous links without a causal arrow. Show the actual screened geographic/variable coverage so a limited scan is not presented as an exhaustive planetary search.

The three-variable display limit must not limit the internal driver search. Obtain confounder series independently of which variables are visible. Multiple contributing variables require conditional/multivariate analysis; displaying several pairwise links alone does not establish their combined contribution. Preserve seasonal/trend decomposition for anomaly relationships, while explaining that anomaly co-variation and attribution of a long-term trend answer different questions.

**5. Evidence-based explanations.** The current engine can suggest associations and predictive relationships. Granger testing concerns whether past values add predictive information; it does not, by itself, establish a physical cause. Use labels such as candidate driver, associated response, and no clear directional evidence. Show the data window, lag, effect size, raw and adjusted significance, confounder checks, and method behind each link. Leave an honest empty result when evidence is insufficient.

The current `WS2M` wind-speed series cannot identify where winds originate. A physical airflow explanation requires appropriate wind-vector/transport data and a defined diagnostic from the permitted resources. Curved statistical links must not be presented as measured wind trajectories. Keep mechanism descriptions distinct from measured evidence.

**6. Comparison at every level.** Replace preset-only resolution with the shared geography resolver for both A and B. Align actual dates and valid spatial support. Use a consistent trend estimator and compatible uncertainty method for the slope difference, allowing for temporal dependence and covariance between areas. The current contrast calculation mixes Theil–Sen slopes with independent OLS standard errors; audit it before claiming a definitive difference between linked regions.

**7. Correct known statistical defects before broad discovery.** Two read-only probes reproduced issues missed by the existing suites:

| Probe | Expected | Current result | Required correction |
| --- | --- | --- | --- |
| Perfect +0.1 units/year series from 2000–2020, with 2010 absent | +1.000 units/decade | +1.058823529 units/decade | Pass actual year coordinates through aggregation and trend routines; do not compress missing years into adjacent observations |
| 56 candidate p-values: one 0.009 and 55 equal to 0.5; BH at q=0.10 | Zero discoveries across the complete test family | Filtering to p<0.01 first leaves one test and admits it | Retain all valid candidate tests and full-precision p-values, correct the complete declared family, then apply effect-size/display gates |

The existing remote scan builds its FDR input from already-admitted connections. It must also account for selecting the strongest lag from many lags, rather than treating the selected lag's ordinary p-value as a single prespecified test. Validate significance with an appropriate dependence-aware method. Align event composites with the lag being reported. Apply consistent missing-data/coverage treatment across trends, comparisons, and relationships.

**8. Jobs and caching.** The four-level choropleth needs region-result caching and background work. Naively repeating the current 25-point fetch for 176 displayed countries and 16 variables would create up to 70,400 point requests before reuse or deduplication. That is not a suitable interaction model. Cache native cells and area summaries, use suitable bulk/subset routes from permitted providers, and prioritize the selected unit and its visible siblings. NASA POWER documentation, if that adapter is retained under the source policy, specifically warns against oversampling native cells and recommends its bulk archive for monthly-scale downloads.

Use bounded workers, request deduplication, cancellation, progress reporting, and resumable jobs. Key results by geometry version, dataset/version, variable, dates, mask/aggregation method, and statistics version. A result computed for a focus box must not satisfy a request for an entire country with the same name.

## Proposed module boundaries and API evolution

These names describe new responsibilities; they do not claim these modules already exist.

| Proposed component | Responsibility |
| --- | --- |
| Geographic catalog/service | Four-level IDs, boundaries, hierarchy, search, and coverage metadata |
| Dataset adapters | Source-policy enforcement, retrieval, units, quality, dates, native-grid metadata |
| Spatial aggregation service | Polygon masks, cell-overlap weights, coverage, regional time series |
| Existing statistics module, repaired | Trend magnitude, uncertainty, significance, and diagnostics |
| Relationship service | Candidate screening, local/remote and incoming/outgoing evidence, multiple-testing correction |
| Job and result store | Background analysis, progress, cancellation, deduplication, versioned caching |
| Frontend investigation store | Level, projection, A/B IDs, variables, dates, results, and request identity |
| Globe adapter | Rendering, picking, boundaries, fills, connections, and camera movement |
| Separate screen controllers | Map, Analysis, Compare, Interconnections, Data & Methods |

Retain existing `/api/analyze`, `/api/scan`, `/api/coupling`, and `/api/teleconnections` contracts while migrating their geographic resolution behind a shared service. Add geography/children queries, cached level-overview results, and a job interface for expensive requests. Extend contracts deliberately with canonical feature IDs, full provenance, and relationship direction. Replace the old Kaspersky binary events transport with an application-owned scientific JSON contract.

## Implementation order and completion checks

| Stage | Work | Reviewable completion condition |
| --- | --- | --- |
| 1. Preserve and define | Snapshot existing work, record current baselines, define geography/source/result contracts, fix reproduced statistics defects | Original features remain available; regression cases for missing years and full-family FDR pass |
| 2. Prove globe integration | Integrate newer globe through adapter; implement country plus Ghana administrative polygon layer | Hover, selection, A/B outlines, fills, islands, and projection changes refer to the same feature IDs; no generated scientific events |
| 3. Rebuild the map shell | Closely match the reference's layout; add variable drawer, level control, date range, selection card, Analyze | Entry view remains map-first; no blocking onboarding modal; controls produce one coherent investigation state |
| 4. Implement area analysis | Shared boundaries, permitted dataset adapter, polygon aggregation, coverage, background summaries | Country/continent results use their full geometry; parent and child series can legitimately differ; pending and missing data are explicit |
| 5. Restore all original features | Dedicated analysis/compare/interconnections screens; charts, scans, grid detail, glossary, CSV, permitted imagery | Every feature in the placement table has a working destination and matching backend contract |
| 6. Extend discovery | Candidate drivers/responses, signed and directed evidence, conditional multi-variable work, justified animations | Clicking every displayed link opens the exact computed evidence; no hard-coded narrative replaces a failed computation |
| 7. Broaden geographic coverage | Expand administrative boundaries and dataset coverage; optimize/validate loading | Unsupported areas are stated explicitly; coverage is measured rather than inferred from a country label |

Start with a complete vertical slice: soil moisture → Africa aggregate → African subregions → Ghana → Ashanti/Greater Accra, plus a genuine A/B comparison. Use global continent/country coverage as the target, and expand administrative coverage from Ghana to Africa and then worldwide where boundaries and scientific data support it. This follows the transcript's permitted Africa-first fallback without pretending that a visual boundary guarantees usable scientific resolution.

Acceptance checks should include disconnected islands, holes/enclaves, small coastal regions, transcontinental assignments, antimeridian geometry, globe/plane selection equivalence, true data coordinates, and an example where a parent aggregate conceals opposite child trends. Verify same-window A/B comparison, stale-response suppression, network/empty-data states, and known synthetic relationship directions, including an inverse relationship. Test statistics against independent reference calculations where practical, alongside the existing unit tests. Compare the finished map shell against the reference at representative desktop and narrow viewport sizes.

## Verification and limits of this review

- Original offline suite: **97 passed, 1 skipped**.
- TerraTrend 2 offline suite: **98 passed, 1 skipped**.
- Both runs used `python3 -m pytest <backend-directory> -q -p no:cacheprovider`. The skipped test requires live NASA access.
- Shared statistical files and other identical components were compared directly, rather than inferred from README claims.
- The original repository already has substantial uncommitted work. This review leaves it intact.
- Missing-year slope and FDR-order issues were reproduced through direct function calls without changing application code.
- The Kaspersky reference was inspected in the browser. Local interactive startup could not be verified because this execution environment denied opening server sockets. Therefore the renderer feasibility assessment is grounded in source inspection, not a completed four-level interaction prototype.
- Video visuals and the supplied transcript were reviewed together. Audio was not independently transcribed by the assistant.
- The resource names above were read from the reference video. Fetching the current official Resources tab was unsuccessful; final dataset access routes still need direct validation during implementation.

## Primary references

- [Kaspersky Cybermap](https://cybermap.kaspersky.com/) — visual and interaction reference.
- [NASA Space Apps: Be An Earth System Trend Detective!](https://www.spaceappschallenge.org/2026/challenges/earth-system-trend-detective/) — challenge identification and objectives; resource constraints in this plan also follow the user's transcript.
- [NASA POWER data services](https://power.larc.nasa.gov/docs/services/) — native resolution, bulk monthly archive guidance, and data revision considerations for the existing adapter.
- [CesiumJS Scene](https://cesium.com/learn/cesiumjs/ref-doc/Scene.html) — picking and 2D/3D transition capabilities of the proposed fallback.
- [CesiumJS PolygonGraphics](https://cesium.com/learn/cesiumjs/ref-doc/PolygonGraphics.html) — globe-conforming polygon hierarchies and holes.
- [statsmodels Granger-test documentation](https://www.statsmodels.org/stable/generated/statsmodels.tsa.stattools.grangercausalitytests.html) — predictive interpretation of the statistical test.
