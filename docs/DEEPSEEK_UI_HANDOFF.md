# TerraTrend: implement the next usability and persistence changes

You are continuing an existing local scientific application. Implement the changes below in the actual project, test them, and leave a working local app. Do not stop at a plan or replace the project with a mock-up. Read the current code before choosing an implementation. The newest requirements in this document supersede older statements that the UI work is complete.

## Workspace and preservation

- Project: `/home/templar/Documents/Projects/Nasa Space APP/Terratrend`
- Sibling reference prototype: `/home/templar/Documents/Projects/Nasa Space APP/TerraTrend 2`; this is NOT the implementation target.
- Normal app: `http://127.0.0.1:8517/`
- Last checked branch: `dev`; HEAD: `7e627a87fc63361889117ee2b9a67b13a11c58fe`. Recheck; keep newer changes.
- The working tree contains essential tracked modifications AND untracked implementation files. Preserve all of them, including unrelated edits and existing deletions. Do not reset, clean, reclone, switch checkouts, restore the deleted `backend/literature.py`, or overwrite files wholesale from an older version. No commit, push, merge or deployment is requested.
- Read applicable `AGENTS.md` files, `LOCAL_SESSION_HANDOFF.md`, `CONTINUE_LOCALLY.txt`, `README.md`, `docs/UI_WORKFLOW_IMPLEMENTATION.md`, and `docs/SOURCES_AND_PRESETS.md`. Older handoff paragraphs are historical where they conflict with newer entries.
- NASA Earthdata and AppEEARS connections are already remembered privately. Check configured/connected status only. Never print, copy, export, commit, put in browser storage, send to an AI, or ask for credentials in chat. AppEEARS remembers its issued token, not the password; expiration is possible.
- Do not interrupt another analysis. The previously running job `cc98133ee5cca15a99c7` was checked during handoff preparation and returned `complete / Analysis complete`. That is a historical observation, not permission to kill a newer job. Inspect current jobs/processes before any restart. Use an alternate local preview port if necessary.
- Keep the current olive globe and real scientific engine, boundary selection, independent A/B geometries, bundled libraries, and source integrations. Avoid a framework migration or broad rewrite. `rg` was unavailable in this environment; use an available equivalent if needed.

## Current architecture and verified baseline

The frontend is HTML/CSS/JavaScript, not a new React application. Existing controllers overlap, so check the final loaded definitions and event bindings rather than editing only a legacy function that is later overridden.

- `frontend/workflow.js`: investigation state, geographic selection, navigation, request identity, `jobSpec`, `/api/plan`, async jobs, observation/result reuse, current context, renderer binding.
- `frontend/workspace.js`: movable investigation controls, `refresh`, measurement filtering, `saveResult`, `restoreResult`, connection cards, connected badges and the current eight-step tour.
- `frontend/app.js`: legacy/shared chart and statistics controllers, expanded charts, local coupling, anomalies and interconnections views. Some chart/render functions appear more than once.
- `frontend/index.html`, `frontend/styles.css`, `frontend/overhaul.css`: layout, controls and styling. Inspect the actual stylesheet list. The investigation card is `#k-region-card`; its body is `#area-panel-body`; measurements use `#measurement-picker`, `#measurement-search`, `#var-list`; run control is `#run`.
- `frontend/map-panels.js`: draggable/collapsible panel sizing and viewport boundaries.
- `frontend/earth-renderer.js`: globe/plane, trend colours, boundaries and relationship arcs. Preserve projection/dateline/country-face fixes and hidden-map redraw suppression.
- `frontend/data-review.js`: data-use review, estimates and explicit request scope.
- `backend/server.py`, `backend/jobs.py`, `backend/data_sources.py`: API, in-memory jobs, scientific execution and automatic routing.
- `backend/analysis.py`, `backend/interconnect.py`: trend tests, correlation/lead diagnostics, decomposition and anomaly reporting.
- `backend/nasa_data.py`, `giovanni_data.py`, `appeears_data.py`, `hydrology_data.py`, `station_data.py`: real data and their existing caches.
- Existing regression tests: `tests/*.test.cjs`, `backend/test_*.py`.

Last full recorded validation: 224 backend tests passed, one opt-in network test skipped, 43 passing subtests; 79 frontend tests passed. Those numbers describe the previous implementation, not proof that the newly reported bugs are absent. Reproduce the new reports and add meaningful regressions.

Important existing limits: completed observations are cached on disk, but the UI's completed-job Map holds only 12 results and its recent-analysis list only six entries in page memory. Full refresh loses those result snapshots and the investigation. The current tour is a static Next/Back explanation, not the interactive training now requested. It traps focus inside its own three buttons, which must change if the user is expected to operate highlighted app controls.

## Work order

Fix request correctness and inaccessible controls first. Then implement durable results/map reuse, clear statistical communication and direct remote actions. Build the interactive onboarding using those reliable foundations. Add the glass styling with readability checks. Treat an optional AI explanation layer as the final enhancement; do not let an unavailable AI service block the deterministic improvements.

### 1. Fix single-area versus comparison state and labels

User reproduction: select only A, choose Precipitation and a time range, click **Analyze Area A**, and receive a demand to select B. This is a correctness bug, not a missing instruction for the user.

An observed code inconsistency to investigate: `TerraWorkspace.refresh()` labels the button from whether a valid B exists, while `jobSpec()` requires B whenever `state.compareMode` is true. Therefore comparison mode with an empty B can display an A-only action and send comparison validation. Confirm all entry points and fix the underlying state/request contract.

- Default to a simple A-only investigation. Hide the empty B row behind a clearly labelled **Add comparison area** action. Reveal B for an explicitly requested comparison, including the Compare workflow.
- A button labelled **Analyze Area A** must always submit an A-only request. It must not require or silently include B. An incomplete comparison must have a matching prompt/disabled action or an explicit A-only choice; never contradict the button label.
- Clearing B with X removes the comparison area, exits active comparison intent, disables/unchecks remote screening if it needs B, returns the picker to A, and restores the A-only action. Keep A and its completed evidence.
- Visiting a navigation page must not silently change the scope of the next request. Distinguish the page being viewed, editable selections, explicit operation/mode, and completed-result context.
- On Compare, identify both country/area names, measurement and requested dates prominently. If both are selected, the action must say **Change comparison areas** or equivalent and take the user to the existing map workspace, preserving A/B. Show **Add comparison area B** only when B is actually missing.
- Distinguish selected-but-not-computed areas from the context of the displayed completed result. Do not relabel old Ghana-only output as newly selected Ghana/Nigeria output.
- Preserve A-only evidence when adding B. Reuse valid observations when comparing; do not download A again unnecessarily. Keep async cancellation/stale-response protection.

### 2. Make the measurement dropdown reliably usable and scrollable

The user reports opening the measurement list and seeing nothing or having to stretch the card. Reproduce on the actual browser and smaller viewport heights, not just by inspecting the accessibility tree.

- Make the floating panel body genuinely scrollable with a sensible maximum viewport-relative height. All measurements, filters, dates and run controls must remain reachable. A large fixed-height list must not consume the entire card or collapse its siblings to zero height.
- Opening/collapsing Measurements must consistently show its heading and choices, including after scrolling far down, filtering, selecting an offscreen option, dragging/collapsing/reopening the card, resizing the window and using keyboard navigation.
- Recent fixes use `flex:0 0 auto; overflow:visible` for closed details to prevent retained inner scroll hiding its summary. Preserve the intent, but inspect the interaction between all competing CSS rules. Avoid accumulating contradictory overrides.
- Keep native labelled checkboxes, visible checked states, search and sphere filters. Explain genuinely unsupported measurements; automatic source selection must not unnecessarily grey out supported ones.
- Use one outer scroll area unless there is a strong reason for nested scrolling. Verify that pointer wheel, trackpad, touch and keyboard can reach controls. If action controls are sticky, they must not cover content.

### 3. Persist completed analyses and expose a Saved investigations library

The user wants completed calculations saved in the app across browser refreshes and server restarts, with a visible library that can restore them immediately. Raw observation cache reuse alone does not satisfy this.

- Add durable local result storage, preferably using a small backend SQLite database or an equally suitable existing storage mechanism. Do not store large scientific payloads in synchronous `localStorage`. Browser storage may hold small UI preferences or identifiers. Do not introduce an external account/cloud dependency.
- Save every successfully completed analysis, comparison, discovery result and relationship investigation with enough context to restore its real evidence. Failed, cancelled or incomplete jobs must not appear as completed findings. Save completion server-side where practical so closing a browser tab does not lose an otherwise completed job.
- Store a stable ID, creation time, schema/analysis-method version, full area identities and exact geometries/boundary versions, variables and units, requested/observed dates and coverage, actual products/provider routes and aggregation, statistics, chart series, relationships and provenance. No credentials, private headers or transient login URLs.
- Build canonical keys from scientifically relevant inputs, geometry/boundary, resolution/aggregation, products, dates and method version. Do not use area display name or variable name alone. Version and validate persisted records; do not reuse incompatible results as current calculations.
- Use safe/atomic writes, deduplication and tested restoration. Keep older results accessible with a clear stale/incompatible label when their engine/source version changes. A new request must not silently overwrite a different time period or geometry. Handle damaged records and storage errors without breaking the app.
- Provide a small persistent **Saved investigations** control accessible from the main workspace and result pages. List human-readable area names, variables, dates, result type and saved time; support search/filtering as needed. Clearly communicate that opening a saved result reads local data and does not start a download.
- Restore A/B, custom geometry registration, provider context, dates, selected variables, charts, statistics, local/remote results and relevant map overlays coherently. Keep the displayed saved context separate from unsaved edits. Do not lose the selected boundary when the current geography list differs.
- Do not silently evict older completed analyses merely because six/twelve new runs happened. Surface disk/storage limitations honestly. Do not delete or clear existing scientific caches while implementing this.

### 4. Reuse saved results as a persistent trend map

Second requested cache feature: after running Air Temperature for Ghana and Nigeria, choosing Air Temperature and the same dates later should show both previously computed country colours immediately. Repeated runs across Africa should gradually build that saved-result map, without an all-Africa download.

- Query an index of completed compatible area/measurement/window results when the active measurement, requested dates, geographic level or relevant product context changes. Populate colours from stored scientific verdicts without creating analysis jobs or observation requests.
- Match exact date windows and scientifically compatible product/geometry/method identity. Never silently combine a 2005–2024 Ghana trend with a 2016–2024 Nigeria trend or a 2 m temperature with 10 m temperature. Explain the displayed window and provenance where needed.
- Preserve independent verdicts for each country/region/custom shape. Do not colour all subregions from a national result or replace an exact polygon with its bounding box. Do not treat NOAA station cohorts as area-average colour layers.
- Use the established theme: blue increase, red decrease, distinct neutral nonsignificant, distinct missing/insufficient data, and an explicit not-yet-analyzed state. Display effect magnitude/units, significance, dates and saved status in hover/click evidence. Never make a nonsignificant slope look like a significant finding.
- Selecting a saved coloured area opens/restores its matching saved evidence. A selected outline and relationship arcs must remain distinguishable from trend fill.
- If multiple snapshots exist, select a documented compatible record and expose alternatives. If no exact match exists, show that honestly and optionally offer an explicit new calculation; do not automatically fetch missing regions or all variables.

### 5. Make charts and statistics readable to a first-time user

- Increase primary reading text and contrast across Map, Analysis, Compare, Interconnections, saved results, onboarding and dialogs. Aim for approximately 16 px body text and 14 px controls where practical, not the current pervasive 8–11 px text. Avoid clipping or overflow at 200% zoom. Use accessible contrast and visible focus states; validate against applicable accessibility guidance using an authoritative source if needed.
- Use colour plus labels, signs and line styles. Maintain A/B identity separately from increase/decrease colours.
- Every plotted area must have its own clearly named observed series and fitted trend. Match each trend line to its country's colour; distinguish observed/trend using solid/dashed patterns. Apply consistently to main and expanded charts. Current legacy chart code includes white A trend lines and cyan B overrides; inspect all loaded definitions, not just one chart.
- Legends and tooltips must identify area, measurement, observed versus fitted value, units, dates and above/below-trend distance. Preserve missing-data gaps and incomplete-year exclusions.
- In comparison statistics, put each area's name on its own column/card. A large `0.20` must explain whether it is change per decade, a coefficient, a probability or something else. Display slope with explicit units/time, e.g. `+0.20 °C per decade`, with `+0.020 °C per year` only as a clearly labelled equivalent. Include uncertainty/significance without ambiguous ownership.
- Explain Sen's slope as the estimated rate of change; keep method details in expandable help. Do not change calculations or round insignificant small changes into an apparently precise zero.
- Explain **Spatial grid** in plain language, e.g. **Variation across the area**: the individual source cells show where evidence differs within the selected area. State actual resolution and coverage. Regional summaries/station data lacking cell outputs must explain that absence rather than display an empty/misleading grid.

### 6. Explain relationship strength and practical meaning

The user sees `+0.58` and reasonably thinks this might mean 0.58 units of one variable caused by another. It is usually a dimensionless statistical correlation. Inspect the actual diagnostic and label its method accurately.

- Put **Relationship strength** beside the value; explain the applicable correlation scale from −1 to +1, where positive means moving together and negative means moving oppositely in the tested series. Say which transformations were used, e.g. monthly seasonal cycle and trend removed, and whether the value is partial correlation.
- For a real +0.58 result, an example explanation is: **A positive association: the variables often varied together. The score is 0.58 on a scale from −1 to +1; it is not an increase of 0.58 measurement units.** Make the wording conditional on actual evidence and the engine's strength labels.
- Keep effect size, overlap/coverage, uncertainty/significance, adjusted tests and time lead distinct. Statistical significance does not establish importance, danger or causation. A correlation coefficient alone cannot decide whether someone should worry; explain that magnitude in physical units, exposure and context are needed.
- Any r-squared display must describe the applicable simple relationship correctly; do not label it the fraction physically caused or treat it as a universal causal explanation of multivariate results.
- Show possible temporal leads only when resolved by the method. Simultaneous links have no directional arrow. No invented wind transport, physical mechanism, causal chain or future-impact claim.

### 7. Run remote relationships directly from Interconnections

The latest explicit request changes the earlier preference that every run action live only on the map. Allow a contextual remote action on the Interconnections page while reusing one shared request-building/controller path.

- When local results exist and Remote says **Remote search was not requested**, provide **Test relationships with another area** or **Run remote relationships** on that page.
- Reuse the current completed investigation's A, measurements and dates, display that context and the intended B, and explain edits that have not been calculated. Do not silently use unrelated form values from a different unsaved investigation.
- If B is already valid, allow the explicit run directly. If missing, offer **Choose comparison area** leading to the single map picker and return to the intended remote task without discarding local results. Avoid duplicating independent area-selection state across pages.
- Preserve the data-use review, automatic preflight/routing, companion-variable requirements, progress, cancellation and cache reuse. Remote scope remains ONLY explicitly selected B and chosen supported fields. Do not reinstate automatic searches of seven unrelated countries or global scans.
- Keep local results available while remote work runs and on failure/cancel. Persist remote results with the investigation. Retain Show on map, variable legend, hover/pinned evidence and paired histories.

### 8. Explain anomalies and provide useful drill-down

- Read `decompose_monthly`, `anomaly_report`, `anomaly_episodes` and their actual callers. Explain precisely what this app computes; do not invent a different baseline or claim every difference is an extreme event.
- Current relationship diagnostics remove a monthly seasonal cycle and a fitted trend; anomaly reporting uses the residual standard deviation, counts months above/below approximately one standard deviation, and identifies episodes. Verify this behavior and show the actual analysis period/baseline and threshold. Missing months, zero variance and short coverage need meaningful states.
- Add a clickable anomaly detail with the date/window, observed value if available, expected baseline, signed departure in physical units, standardized departure if used, duration, threshold, coverage and original-source information. Show a chart with its baseline/threshold bands and clearly highlight the selected episode.
- Explain what an unusual departure means and that this threshold alone is not a hazard assessment. Distinguish above-baseline and below-baseline episodes. Review the current high-side-only episode construction and handling of missing gaps; do not join nonconsecutive observations or silently drop a legitimate completed episode at a gap.
- A click cannot establish what caused the anomaly. Offer **Explore possible linked variables** using actual coincident/leading observations and the existing relationship tests, with an explicit association/attribution distinction. If attribution evidence is absent, say it has not been established. Any general scientific hypothesis must be labelled and sourced rather than presented as measured fact.

### 9. Replace the static tour with onboarding plus interactive learning

New visitor experience: a brief **Welcome to TerraTrend** introduction explains what the app does, who it is for, the difference between trends and relationships, and that ordinary live analyses can use network data. Then offer **Start interactive tour** and **Explore on my own**. Help must replay/resume individual lessons later.

- Build a small explicit tutorial state machine with real action-completion conditions. For action steps, **Next** must not skip the required interaction while pretending it happened. Advance after the real event/successful result; explanatory steps may have Next/Back. Support Skip, Exit, restart and sensible completion persistence/versioning.
- Cover choosing an area by globe OR list; continent/subcontinent/country/admin-region levels; curated rectangle presets; lasso and coordinate bounds; single-variable analysis; changing dates; reading Analysis; comparing two variables within one area; comparing A/B places; discovery with no measurement selected; local/remote relationships; anomaly interpretation; saved-results restoration; and where source details/live data review are available. Use short core lessons plus optional advanced chapters if a single tour becomes overwhelming.
- Each instruction anchors near the actual control with a clear pointer, readable text, current task and progress. Reposition on panel drag, page change, scroll, window resize and zoom. Keep the target visible and interactive. Wait for asynchronously loaded boundaries/options without advancing too early.
- Require the learner to select a region, check a measurement, choose/change dates, click the real Analyze action, and click the real Analysis/Compare/Interconnections navigation when instructed. Do not simulate these actions on their behalf and call it interactive. For charts, guide them to hover/focus/click a real data point or view its accessible data detail.
- Explain that Ghana North (Savannah) is a curated focus rectangle, not the exact Ghana national boundary. Never pass a country boundary to a rectangle-only service by silently substituting its bounds.
- Use real locally cached/saved evidence for the default tutorial. First create a reliable inventory/manifest of actual matching cached analyses and covered date ranges. Known bounded evidence is described below. A tutorial should not trigger broad NASA downloads, all-world boundary loads, full-continent scans or large background prefetches.
- The learner may choose dates within a demonstrably cached window; clearly identify the available range. Production discovery scans compatible supported fields, but a download-free tutorial may need an explicitly labelled scan of its available saved measurements. Never pretend the limited lesson scanned all live variables.
- If required local data are unavailable, offer another genuinely cached lesson, an honest explanatory preview, or an explicit live-request choice with its normal review. Do not fabricate observations or silently download a large demonstration dataset. Fixture data may be used for automated tests only and must not appear as genuine scientific findings.
- Preserve the user's investigation before entering a lesson. On exit, offer to return to it or keep the lesson result. Do not overwrite or delete their saved analyses. Tutorial state must not cancel another user's/server job.

### 10. Add a clear animated spotlight and a readable glass panel

- Dim and gently blur the surrounding page while leaving the actual focused target sharp and usable. Use a real cutout/mask or equivalent layering; a full-screen blur over the target does not meet the request.
- Animate the spotlight from the broader view toward its target and between targets so the eye follows it. Use restrained timing; respect reduced-motion preferences and avoid flashes. Support offscreen targets, scroll containers, canvas/globe regions and responsive layouts.
- The overlay must allow interaction with the highlighted app controls and the tour controls. The current tour's button-only focus trap is unsuitable: include the target region's usable controls in the guided focus path, block only unrelated interactions when appropriate, retain keyboard access and restore focus on exit. Escape/Skip must always work. Avoid trapping users behind the backdrop.
- Give the movable investigation card a frosted, slightly translucent olive glass background with a subtle border/shadow. Keep sufficient opacity/contrast over bright or detailed map areas. Provide a readable fallback when backdrop filtering is unsupported and consider reduced-transparency preferences. Do not blur the form's own contents or make the whole page transparent.
- Keep it draggable/collapsible and correctly bounded after expansion. Ensure the tour and the glass redesign do not reintroduce the dropdown/scroll bug.

### 11. Optional grounded AI explanation layer

The user asks whether AI could explain results better. It can help turn verified structured evidence into plain language, but good deterministic labels and explanations must work without it.

- Implement the clear deterministic summaries above first. Then, if a suitable supported AI connection/configuration already exists, add an optional **Explain this result** or concise page summary. Inspect the project before selecting a service; do not invent a configured API key or require the user to buy/connect a service to use the app.
- If adding a provider needs user configuration or external data sharing, make that explicit and optional. Do not send every analysis externally on page navigation. Keep API secrets server-side, with appropriate timeout/error handling and no key logging.
- Give the explanation layer only necessary structured calculated evidence, units, dates, coverage, method descriptions and approved source references. Never send NASA credentials. Treat third-party source text as untrusted data, not instructions.
- Require evidence-grounded statements, distinguish observations/associations/hypotheses, never invent a cause, diagnosis, significance result or forecast, and fall back to deterministic summaries. Keep numerical values and labels programmatically tied to verified fields. Any external scientific explanation must have an appropriate source.
- If no provider is configured, deliver the deterministic version and a clean optional integration point; report honestly that live AI explanation remains unconfigured. Do not block all other work for it.

## Real local evidence available for small demonstrations

Read the evidence before using it and verify that the corresponding caches/results still exist. Historical IDs are not a promise that in-memory jobs survive a restart.

- `docs/local-handoff/sources-presets-2026-11-15/`: Ghana NDVI 2016–2024 with 108 actual monthly values; source/report details in `docs/SOURCES_AND_PRESETS.md`.
- `docs/local-handoff/ui-workflow-2026-11-15/`: saved JSON of completed real checks, plus `live-jobs.json` and verification notes.
- Ghana North (Savannah), 2016–2024: Giovanni 10 m air temperature and GLDAS upper-soil temperature, 108 overlapping months. Both annual trends were nonsignificant; their processed monthly relationship was approximately +0.65 with no resolved lead. Do not teach that these are significant annual trends or proven drivers.
- Two cached coordinate rectangles: A west/south/east/north = `[-2,6,0,8]`; B = `[-1,8,0,10]`. T2M and QV2M checks returned 108 months per area for 2016–2024. One remote temperature association was approximately +0.78, simultaneous. Inspect result files for exact IDs, sources and context.
- These JSON records are evidence of specific real checks. If used to seed the saved-results library, validate/import them explicitly as those historical observed results with their original provenance and method version. Do not claim they are new live downloads or substitute their geometry/variables/dates.

Scientific constraints to preserve: automatic routing retains matched products for paired comparisons. T2M/QV2M can use Giovanni for compatible rectangles; mixed exact-boundary comparisons retain the native product across both areas. T10M/QV10M require compatible rectangles. AppEEARS vegetation, GLDAS hydrology and NOAA station summaries have their own limits. No raw-data accuracy, resolution, coverage or attribution guarantees should be invented by the UI.

## Required verification and acceptance cases

Add tests around the actual behavior and API contracts, not merely strings copied from the implementation. Use small fixtures for tests and actual existing cached observations for labelled live/local verification. Do not consume the user's bandwidth to prove the UI works.

1. Fresh A-only Ghana + Precipitation + dates: Analyze Area A creates an A-only request without B validation. Repeat after visiting Compare, after arming B without choosing it, and after clearing a previously selected B.
2. Completed Ghana/Nigeria comparison: page names both areas, dates and variable; **Change comparison areas** preserves both. Editing them retains the old result with its true old context until a new calculation completes.
3. Expand Measurements, scroll to a later item, select it, collapse/reopen, filter, drag/resize the panel and operate at a shorter viewport/200% zoom. Heading, checkboxes, dates and actions remain usable; focus does not disappear.
4. Complete an analysis, comparison and relationship request; refresh the browser and restart only a safely idle preview backend. The Saved library restores them, including a custom polygon, without observation downloads. Cancelled/failed work is not listed as complete. Include deduplication, schema/version and damaged-record tests.
5. Save different periods/products for one measurement. Only exact compatible records colour the map for the chosen window. Previously computed Ghana and Nigeria both appear without any new job or observation request; uncomputed countries and missing/nonsignificant findings remain distinct. Selecting a colour restores the matching result.
6. Verify main/expanded comparison chart datasets: A observed/trend use A colour and B observed/trend use B colour, with different line patterns and clear area/unit ownership. Preserve gaps, trend distances and calendar conversions.
7. A real correlation such as +0.58 is described as a unitless relationship score with method, period, coverage and uncertainty. It is never presented as a physical-unit change or automatic danger/causal verdict.
8. From a local-only Interconnections result, run remote directly for explicitly selected B. If B is missing, choose it through the shared picker; retain local results. Verify review estimates and outgoing request include no unrelated areas/variables.
9. Anomaly tests cover positive/negative departures, threshold/baseline, missing gaps, zero variance and insufficient data. Detail views report actual dates/units and do not claim attribution from an anomaly alone.
10. A new user sees Welcome, can skip/replay, and completes actual region/measurement/date/run/navigation actions. The tour cannot advance action steps without their conditions. Verify no large observation requests during the cached tutorial, correct data labels, keyboard access, reduced motion, responsive spotlight and clean exit/restoration.
11. Verify readable glass fallback/contrast and connected badges. No NASA secrets appear in persisted result payloads, exports, logs, browser storage or optional AI input. AI unavailable/unconfigured still leaves useful explanations.
12. Run appropriate existing regressions and the full suites after functional changes: `.venv/bin/python -m pytest backend -q -p no:cacheprovider` and `node --test tests/*.test.cjs`. Run syntax/whitespace checks. Do not assume the historical 224/79 counts are current. Investigate actual failures without discarding unrelated work.

Verify in the actual browser, not only mocked tests. Capture useful screenshots of the corrected panel, saved trend map, comparison communication and interactive spotlight, and report which checks were real cached data versus fixtures. Do not silently claim a live external integration was tested when only a fixture ran.

## Delivery

Work through the priorities autonomously. Provide brief meaningful updates. Ask only for genuinely missing input or a necessary account action; do not ask the user to re-enter remembered credentials as a routine step. Do not perform broad downloads or add a paid/external AI dependency as an unannounced prerequisite.

Update the local runbooks and a concise implementation report with what actually changed, how the new persistence works, test/browser evidence, remaining limitations and any incomplete items. Preserve the existing checkout and all uncommitted work. Finish with the working local URL and a plain-language explanation of how to use Saved investigations, compare areas, run remote relationships and start the new interactive tutorial. Report unfinished items honestly rather than declaring the whole list complete.
