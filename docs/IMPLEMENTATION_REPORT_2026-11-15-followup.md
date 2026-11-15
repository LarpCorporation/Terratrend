# Follow-up usability and persistence work — 15 November 2026

Continues the approved workflow. Work was performed in the existing checkout
(`dev`, base HEAD `7e627a87fc63361889117ee2b9a67b13a11c58fe`) with every
uncommitted edit preserved. No commit, push, reset, clean or deployment was
performed. The normal app is <http://127.0.0.1:8517/> and now serves this build.

## 1. Request correctness: A-only versus comparison

`frontend/workflow.js` now has one resolver, `resolveRunAction()`, that decides
*what the run control will do* and *what it is labelled* from the same state.
`jobSpec(operation, {compare})` accepts an explicit comparison decision and
never needs area B for an area-A-only request.

| Situation | Label | Request |
| --- | --- | --- |
| Measurement chosen, comparison off | **ANALYZE AREA A** | `region` only, no `compare_region` |
| Comparison armed, B empty | **ADD COMPARISON AREA B** | nothing is submitted; a prompt explains, with **Analyze area A only** and **Change comparison areas** |
| Comparison armed, B different | **COMPARE A + B** | `region` + `compare_region` |
| No measurement chosen | **DISCOVER TRENDS IN AREA A** | discovery |

* The empty B row is hidden behind a visible **＋ Add comparison area B**
  control; it appears only for an explicit comparison.
* Clearing B with × now exits comparison intent, clears the remote-screening
  checkbox, disables it, returns the picker to A and restores the A-only action.
  Area A and its completed evidence are kept.
* Navigating between Map / Analysis / Compare / Interconnections / Data & Methods
  never changes scope, comparison intent or the completed result.
* The Compare page banner names both areas, the measurements and the requested
  period, and states explicitly when the displayed numbers belong to an earlier
  selection that has not been recalculated.
* Re-running a comparison reuses the scientific caches; area A's observations
  are not downloaded again when they are still cached.

## 2. Measurement dropdown

Root cause (reproduced in a real browser at 1400×560): the panel body was a flex
column with `overflow:hidden` while the open measurement picker was
`flex:0 1 auto; min-height:48px; overflow-y:auto`. The picker therefore collapsed
to **48 px** holding **2 029 px** of content — only its sticky heading stayed
visible — and the panel and the picker were two competing scroll areas.

Now there is exactly one scroll area (`#area-panel-body`, `overflow-y:auto`,
`max-height:clamp(200px, 100vh-235px, 820px)`); the picker and the list never
become scroll containers, the heading stays sticky inside the panel, and the
card itself never overflows. Checking a measurement updates that row in place
instead of rebuilding the list, so keyboard focus and scroll position survive.
Verified in the browser at short viewport heights and 200% zoom: late items are
reachable and selectable, collapse/reopen keeps heading and choices, filtering
cannot scroll the panel away, and dates/run control are reachable.

## 3. Durable saved investigations

**Storage**: `backend/result_store.py`, a standard-library SQLite database at
`backend/cache/results.sqlite3` (the cache tree is git-ignored; no other cache
was touched). WAL, `synchronous=FULL`, `BEGIN IMMEDIATE` transactions, a module
lock, no automatic eviction, and an honest storage report (count, bytes, kinds,
oldest/newest).

**Saved server-side at completion**: `_execute_and_persist` persists a finished
`analyze` / `scan` / `interconnections` / `overview` result inside the job, so a
closed browser tab does not lose it, and a storage failure can never fail the
analysis. Failed and cancelled jobs are never saved.

**Canonical identity**: sha256 over schema version, method version, operation,
provider family, the ordered areas with a hash of their real geometry, the
measurements with units, the requested years, the geographic level and the
aggregation/grid identity. Display names are never part of the key. The same
request updates one row; a different window, geometry, measurement or method is
a different row.

**Honesty states**: a record from a different method version stays readable and
is labelled `legacy` with a reason and excluded from current map cells; a record
whose payload cannot be decoded is `damaged`, is listed, and is excluded from
the index. Credentials (`token`, `password`, `secret`, `authorization`,
`cookie`, `api_key`, `credential`, bearer-looking values) are stripped on insert
*and* again on read.

**UI**: a **SAVED** button in the top bar (with a live count) opens a dialog that
lists human-readable area, measurements, years, result type, saved time and
method status, with search, **Open this result**, **Explain this result** and
**Remove**. It states that opening a saved result reads local data and starts no
download. Restoring rebuilds A/B (including re-registering an exact saved
polygon through `/api/geography/custom`), provider, dates, selected
measurements, charts, statistics and map overlays, and keeps the saved context
separate from later edits.

**API**: `GET /api/results`, `GET /api/results/<id>`, `GET /api/results/map`,
`POST /api/results` (`import` / `delete`), `GET|POST /api/explain`.

**Historical evidence import**: `backend/import_evidence.py` imports the
repository's documented hand-off payloads (15 files → 13 unique records) with
their original areas, measurements, units, window, provenance and the documented
engine version, plus an explicit `historical local evidence import` marker in
the payload stating they are not new downloads. Re-running it is idempotent.

## 4. Saved-result trend map

`GET /api/results/map?variable&start&end` returns one cell per stored area
verdict. The globe (`setSavedTrends`) colours only areas whose stored id **and**
level match a feature in the displayed layer — a national result never colours a
subregion and a bounding box never replaces a polygon. Only an exact
measurement + requested window match produces colours; other saved windows are
returned as `alternatives` and offered as an explicit choice, never merged.
Cells are kept separate from the current result, so editing never relabels old
evidence. Hover/click evidence gives the verdict, the magnitude with units, the
window and "saved result"; clicking a saved coloured area opens its stored
evidence. The globe palette and the on-screen colour key agree and are
distinguishable in every analysed state: blue `#59baff` significant increase,
red `#ff786a` significant decrease, pale sage `#9db3ab` analysed but not
significant, muted mauve `#7f7386` analysed but insufficient data, and a
near-background land tone for not-yet-analysed. (Verified in the page by reading
the painted mesh colour and opacity: Ghana, analysed and nonsignificant, paints
`#9db3ab` at 0.72 while unanalysed Nigeria stays `#3a4d41` at 0.04.) Colouring
performs no job and no observation request.

## 5. Readable charts and statistics

* The effective chart builder (`frontend/workflow.js` overrides `app.js`) and
  the expanded chart now plot, per area, an **observed** series (solid, area
  colour: A `#68b8ff`, B `#e9c77a`) and its **own fitted trend** (dashed, same
  area colour, A `[7,4]`, B `[2,3]`). The previous white A trend and cyan B
  override are gone. Direction is carried by labels and statistics, not by
  recolouring a series.
* A visible chart key names each area, measurement and which line is observed or
  fitted; tooltips give observed value, fitted value, signed distance above or
  below the trend, units and the real calendar period. Gaps and incomplete-year
  exclusions are preserved.
* Chart ticks and legends moved from 8–10 px to 12–13 px with higher contrast;
  the statistics guide explains Sen's slope as a rate (with the per-year
  equivalent), what significance is not, what a relationship score is, and what
  "insufficient data" means. Primary reading text across the panel, comparison
  banner, saved library, anomaly dialog and explanation dialog is 14–16 px.
* The spatial grid is labelled **Variation across the area** and its absence for
  regional/station summaries is explained rather than shown empty.

## 6. Relationship strength

Relationship cards and pinned evidence now say **relationship strength**, name
the −1…+1 unitless scale, state that the value is not a change in measurement
units, name the transformations actually applied (monthly seasonal cycle and
fitted trend removed; partial correlation and its control where used), separate
effect, overlap, adjusted significance and resolved lead, and state that
significance is not importance, danger or causation. `backend/analysis.py`
`explain_teleconnection` was corrected to the same reading. Simultaneous links
still carry no direction claim.

## 7. Remote relationships from Interconnections

With a completed local result and "remote search was not requested", the
Interconnections page shows a context strip naming the completed area,
measurements and dates, the intended area B, and any edits not yet calculated —
plus **RUN REMOTE RELATIONSHIPS** when B is valid or **CHOOSE COMPARISON AREA B**
when it is not. The request is built from the completed local investigation
(`investigation.remoteTask`), not from unrelated unsaved form values, and goes
through the same preflight, routing plan, data-use review, progress,
cancellation, cache reuse and job runner. Scope remains only the explicitly
selected B and its chosen supported fields. Local results stay available on
success, failure and cancel.

## 8. Anomalies

`backend/interconnect.py` fixes three real defects in `anomaly_episodes`: it
detected only the high side, it silently dropped a completed episode when a
missing month interrupted it, and it had no direction, duration or truncation
information. Episodes now carry `side`, `start`, `end`, `months` (and the legacy
`n`), signed `peak_sigma`, `peak_month`, `mean_sigma`, `threshold_sigma` and
`truncated`, and are never joined across a gap.

New `anomaly_detail(values, months)` returns the fitted baseline reconstructed as
`slope*i + intercept + climatology[i % 12]`, a per-month table of observed,
expected, departure and standardised departure, the episode list and summary
counts, with honest `insufficient_data` and `zero_variance` states instead of a
misleading "0 months above threshold". `anomaly_report` gained `status`,
`threshold_sigma`, `episodes_above`, `episodes_below`, `baseline_period` and a
side-aware narrative that explicitly disclaims hazard and attribution.

The Interconnections anomaly episodes are now buttons that open a drill-down
dialog with the analysis period, baseline, threshold, coverage, source and the
per-month observed/expected/departure/σ table for that episode, the peak month
highlighted, a plain reading of what a departure is not, and **Explore possible
linked variables** built from the surviving pairs of that run (association, not
attribution).

## 9–10. Interactive onboarding, spotlight and glass

The static Next/Back tour is retired. `frontend/onboarding.js` (with
`frontend/onboarding.css`) implements `window.TerraTour`:

* a **Welcome to TerraTrend** introduction (what the app does, who it is for,
  trends versus relationships, and that ordinary live analyses can use network
  data while the tour uses saved evidence), with **Start interactive tour** and
  **Explore on my own**;
* 15 core lessons plus an optional advanced chapter, covering area choice by
  globe or list, geographic levels, curated rectangles, lasso/bounds, choosing a
  measurement, changing dates, the real Analyze action, reading Analysis,
  comparing two variables in one area, comparing A/B places, discovery, local
  and remote relationships, anomaly interpretation, saved results and source
  details — including an explicit lesson that Ghana North (Savannah) is a
  curated rectangle, not the national boundary;
* a real state machine: an action lesson has no working Next and advances only
  on the matching `terratrend:action` event (or an explicit **Skip this step**
  which marks nothing complete); explanatory lessons keep Back/Next; busy states
  (`TerraTour.setBusy`) block advancing while boundaries or a job are loading;
  progress is versioned in `localStorage['terratrend-onboarding-v2']` and can be
  resumed, restarted or replayed lesson by lesson from HELP;
* a real cutout spotlight (scrim panels plus a ring, not a blurred layer over
  the target) that morphs between targets, keeps the highlighted control sharp
  and usable, repositions on scroll, resize, zoom, panel drag and screen change,
  respects `prefers-reduced-motion`, includes the target's controls in the
  keyboard path and restores focus on exit; Escape always exits;
* the movable investigation card is now a frosted olive glass panel with a
  subtle border and shadow, high enough opacity for contrast over a bright
  globe, a solid fallback when `backdrop-filter` is unsupported, and
  `prefers-reduced-transparency` / `prefers-contrast` handling.

## 11. Optional grounded explanation

`backend/explainer.py` always produces a deterministic summary from verified
fields (areas, measurements, units, requested vs observed window, coverage,
Sen slope with units per decade, significance and p, honest insufficient-data
states, the unitless relationship scale, and the association-is-not-causation
caveat). `GET|POST /api/explain` returns it with `available:false` and a clear
reason when no provider is configured, and `POST` accepts either a stored record
id or a completed result. An OpenAI-compatible provider is used only when
`TERRATREND_EXPLAIN_BASE_URL`, `TERRATREND_EXPLAIN_MODEL` and
`TERRATREND_EXPLAIN_API_KEY` are all present server-side; the key is never
logged, returned or sent anywhere else, the evidence sent is a bounded structured
subset with credential-like keys stripped, and any timeout/HTTP/parse failure
falls back to the deterministic summary. **Live AI explanation remains
unconfigured in this installation**, by design; the **Explain this result**
button works without it.

## Verification

| Check | Result |
| --- | --- |
| `backend` pytest suite | **292 passed, 1 opt-in network test skipped, 43 subtests passed** |
| `node --test tests/*.test.cjs` | **96 passed** |
| `node --check` on changed scripts; `git diff --check` | clean |
| Real browser, `http://127.0.0.1:8517/` | Saved library (13 records), Explain dialog, saved trend map colouring Ghana for NDVI 2016–2024 with no request, comparison banner naming both areas and the period, interactive spotlight, zero console errors |

Regressions added: A-only request never demands or includes B (including after
visiting Compare, after arming B, and after clearing a B); explicit comparison
still requires two different areas; a saved trend cell never crosses measurement
or window; an uncomputed country stays uncoloured; the remote action is built
from the completed investigation and reports unsaved edits; anomaly sides, gap
handling, zero variance, insufficient data and baseline reconstruction; chart
area identity colours and dash patterns in both chart builders; result-store
dedupe, versioning, damaged records, credential stripping, corrupt storage, map
index exactness and atomic concurrent writes; explainer grounding and provider
fallbacks; onboarding step gating, persistence, evidence matching and lesson
anchors.

**Test isolation fix**: `backend/test_geographic_workflow.py` exercises a real
job, which now persists. `backend/conftest.py` points the result library at a
temporary database for every test, so a fixture can never appear in the user's
Saved investigations as a genuine finding (a stray fixture row created during
development was removed and the full suite re-run to confirm it does not
reappear).

## Browser evidence (real cached data vs fixtures)

* **Real cached evidence**: the Saved library and saved trend map are populated
  by an explicit import of this repository's documented hand-off payloads
  (`backend/import_evidence.py`): Ghana NDVI 2016–2024 (−0.0136 index/decade,
  p = 0.7098, nonsignificant), Ghana North (Savannah) GLDAS soil temperature +
  Giovanni 10 m air temperature, the two cached coordinate rectangles compared
  for T2M/QV2M, one remote temperature association r ≈ +0.78 (simultaneous), the
  Ghana discovery result and the Ghana relationship checks. These are earlier
  observed results, not new downloads.
* **Fixtures only**: everything under `backend/test_*.py` and
  `tests/*.test.cjs`. No fixture value is presented in the app.

Screenshots: [tour · choose Ghana](local-handoff/screenshots/2026-11-15-tour-choose-ghana.png),
[saved library](local-handoff/screenshots/2026-11-15-saved-library.png),
[saved trend map](local-handoff/screenshots/2026-11-15-saved-trend-map.png),
[comparison communication](local-handoff/screenshots/2026-11-15-comparison-communication.png),
[interactive spotlight](local-handoff/screenshots/2026-11-15-interactive-spotlight.png),
[grounded explanation](local-handoff/screenshots/2026-11-15-explain-result.png).

## Corrections after the user walked the tutorial

The first version of this report claimed the onboarding was verified. It was not
walked end to end, and the user found it unusable. Walking it properly exposed
three real defects, all fixed now:

1. **The area list did not match the map layer.** After switching to Country the
   select still listed the eight continents, because `setAreaOptions()` ran
   *after* the map redraw, and a superseded redraw returned early — leaving the
   layer loaded but the list and breadcrumb stale. The list is now populated
   from the layer that just loaded, before the globe is touched, and
   `renderRegionSelect()` prefers the loaded layer over the catalog.
2. **Choosing an area from the list could register nothing.** `onRegionChange`
   only looked in `state.catalog.regions`; areas loaded into the boundary layer
   were not found. A shared `areaMetaFor()` now resolves the catalog, the loaded
   layer, the feature store and the current selection.
3. **`TerraWorkspace.init()` could be skipped entirely.** If the layer load
   threw, the boot chain jumped past it, so the measurement search, date-change
   events, SAVED button and tour hooks were never wired — which is why the tour
   could not advance on a date change. The interface is now wired *first*, and
   the layer load is isolated so a redraw problem cannot disable the controls.

Also corrected to match what the user asked for:

* the app opens on **Country**, not continent;
* the tutorial is reordered so the **map level comes before the area**, and each
  action step points at a control the learner can actually use inside the card
  (the area list and the measurement list), not a button that requires clicking
  a dimmed globe;
* the tour, the Welcome and the saved library no longer explain internals
  (caches, storage, network transfers); copy is one or two plain sentences;
* the walkthrough uses **Ghana + Air Temperature**, which is a real saved result
  (2016–2024, completed from cache in about three seconds); the tutorial was
  walked through selecting Ghana, checking Air Temperature, changing the dates,
  pressing Analyze Area A, confirming the review, opening Analysis and opening
  Interconnections — **15/15 lessons, no console errors**;
* selecting a measurement now paints every compatible saved country, and when
  only another exact window exists the map offers it as an explicit
  **Show saved YYYY–YYYY** button instead of colouring a mismatched period;
* restoring a saved investigation puts the **map first** — same area, same
  measurement, same dates, the result's own colouring plus the other saved
  colours — with Analysis already loaded and any saved relationship evidence
  attached to Interconnections.

## Remaining limitations and unfinished items

* The full core tour is now walked end to end in a real browser (15/15, real
  Ghana Air Temperature result). The optional advanced chapter is unit-tested
  but was not walked lesson by lesson in the browser.
* No new live NASA request was made. The Ghana Air Temperature 2016–2024 result
  used for the tutorial came from the existing observation cache (108/108 months,
  about three seconds) and is now part of the saved library. Remote screening still needs a real
  analysis run to produce an `anomaly_detail` payload; imported historical
  relationship records show the honest "this run did not retain a per-month
  drill-down" state instead.
* The saved trend map reflects exactly what has been saved. It currently has
  Ghana and the two coordinate rectangles; other countries remain uncoloured
  until an analysis of that exact measurement and window is completed.
* AppEEARS may still expire its issued token; nothing here changes that.
* A per-frame performance pass on very many saved cells (hundreds of countries)
  was not performed; the index is bounded to 400 cells per query.

## Readability pass after the student-style UI audit

An independent audit read the app the way a first-time 16-year-old would and
found the science legible to its author only. The following changed.

**Answer first, statistics second.** The Analysis page now opens with a
plain-English card before any technical panel:

> **No clear warming or cooling trend**
> Air Temperature over Ghana changed by about +0.22 °C in total over 19 years
> (roughly +0.12 °C every ten years).
> A change this size is within the normal year-to-year ups and downs of these
> data, so we cannot say the region is clearly changing. The small difference
> above is an estimate, not a proven shift.

It distinguishes "no clear change" from "not enough data", names the region,
measurement, units and period, and states the change as a **total over the
period** as well as per decade. A button toggles **Show the statistics**, which
reveals the estimate, p-value with one sentence of meaning, the 95 % plausible
range (read from the per-decade fields, previously the wrong units), and a note
that Mann–Kendall/Theil–Sen are standard climate-science methods. The dial and
per-variable panels are hidden until then.

**Map reading.** Hover/click now says "no clear trend · about +0.22 °C in total ·
2005–2024 · saved result" rather than "NO SIGNIFICANT TREND · -0.01 index/decade",
and the map card shows "+0.22 °C in total, 2005–2024". The per-variable chip no
longer says `1878/8594 SIG`; it says "7 of 85 cells changed clearly" with a
**Show where** link to the in-region grid, and single-value sources say there is
no inside-the-region grid rather than showing an empty one.

**No scary download modal.** The blocking warning with "ESTIMATED DOWNLOAD ·
EMPTY CACHE ≈ 603 MB · 2,112 requests" is gone. The confirmation now reads
"Here is what we will look up." → "Air Temperature for Ghana, 2005–2024." → "The
result is calculated from NASA observations for exactly this place and period."
with a **GET THE RESULT** button. The transfer estimate and technical notes live
inside a collapsed "Download size and data details" disclosure.

**Human labels.** "Area A / Area B" became **REGION** and **COMPARE WITH**;
buttons read **ANALYZE REGION**, **COMPARE REGIONS**, **ADD A REGION TO COMPARE**,
**FIND WHAT IS CHANGING HERE**; the sphere filters read **ALL / AIR / WATER /
LAND / ENERGY** instead of ATM/HYD/LND/ENG. The tutorial copy was updated to
match ("Choose Ghana", "Press Analyze Region").

**Dead options out of the way.** Measurements the current data source cannot run
are no longer listed greyed-out as "NOT AVAILABLE YET". They are hidden with one
line — "8 more measurements need a different data source and are hidden." — and
a **Show them anyway** control.

Verified in the browser on 8517 with a real Ghana Air Temperature 2005–2024 run:
plain card values, hidden technical panels, working toggle, corrected p-value and
plausible range, humanised hover text, and the in-region cell sentence (7 of 85
cells). Backend **292 passed**, frontend **96 passed**, whitespace clean.

Screenshots: [plain verdict](local-handoff/screenshots/2026-11-15-plain-verdict.png),
[statistics toggle](local-handoff/screenshots/2026-11-15-statistics-toggle.png).

Still limited: the in-region evidence is shown through the existing grid view /
**Show where**, not as highlighted cells painted on the 3D globe.
