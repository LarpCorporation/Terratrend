# Area-only discovery and data use — 15 November 2026

## Current behavior

The map starts with no scientific variables selected. Pick primary area A, choose a period, then **Analyze**. An empty variable selection opens discovery for the supported measurements. The NASA adapter currently supports eight; unsupported catalogue fields stay disabled.

Before a scientific job is submitted, a review shows the selected area(s), dates, measurements, estimated download size and monthly subset count. **Go back**, closing the review, clicking its backdrop or pressing Escape does not submit the new job. Changing the investigation invalidates any pending review. The review is shared by selected-variable analysis, discovery, layer analysis and relationship screening. Cancelling an existing job may still send its local cancellation request before reviewing a replacement.

Discovery concerns primary A. It does not require B or silently present a primary-only scan as an A/B result. Choosing a discovery row prepares that measurement, opens Analysis and reviews the detailed request; an already selected comparison B remains available for the subsequent comparison.

After a scan completes, the ranked table distinguishes:

- Significant increasing and decreasing signals, ordered before nonsignificant results, then by absolute trend coherence.
- Nonsignificant tests, explicitly labeled **NOT SIGNIFICANT**, rather than stable or unchanged.
- Insufficient observations, separate from a source-service error. Source errors retain their explanation in the row tooltip.

Rows can be opened by mouse, Enter or Space. Their detailed Analysis screen retains the time series, expanded statistics and export. The active measurement colors the selected area; other measurements have their own results. A single Africa result does not establish individual country results. **Analyze Layer** calculates those separately and reviews their combined data use.

## Where the computation happens

The current path is **NASA subset API → download to this computer → validated local cache → polygon aggregation and statistics → graphs and map colors**. API use still consumes the computer's internet data. The source request specifies a field, monthly observation file and native latitude/longitude window; it does not download the entire global multi-variable archive. Native cells are aggregated using the saved polygon and the documented coverage rules.

For a variable, the adapter assembles the requested published monthly subsets before calculating the time series and trend. A discovery scan repeats this for supported measurements. At most three subset downloads run concurrently. Files are cached by field, source revision and exact native window; overlapping areas with identical windows can reuse them. Cache reuse reduces external traffic but does not eliminate all local calculation time.

NASA does not currently run TerraTrend's Mann–Kendall/Sen/relationship calculations and send back only final answers. Moving exact-polygon processing to a hosted service could reduce user-side data transfer, but no such remote aggregation service was implemented here.

## Africa estimate and its limits

An offline calculation using the current continent geometry found **8,594 intersecting native cells** and source window `[74, 255, 247, 406]`: **182 latitude rows × 160 longitude columns = 29,120 source cells**. The enclosing window includes extra cells outside the aggregation polygon. This is partly affected by the catalogue's existing country/island grouping, including distant territories.

For January 2005–December 2024:

| Request | Monthly subset files if uncached | Current planning estimate |
| --- | ---: | ---: |
| One measurement | 240 | 68.6 MB |
| All eight implemented measurements | 1,920 | 548.5 MB |

The planner allows eight bytes per source value and coordinate plus 50,000 bytes per monthly subset for container/metadata overhead. This is an intentionally conservative **empty-cache planning allowance**, not an exact wire-size forecast or enforced quota. Real files may have smaller numeric types or compression, matching source subsets may already be cached, and metadata or service responses can differ. Polygon bounding boxes can overestimate a narrower dateline-aware download envelope. The review states these limits explicitly. It does not promise that a transfer will stop at its displayed estimate.

Relationship estimates include companion variables and the requested remote screening areas, rather than pricing only the visible variable. Layer estimates include all requested geographic units. Providers that read existing local cache/imports show zero new NASA observation downloads; this does not describe unrelated page visits or first-time administrative-boundary downloads.

Africa's full scientific run was **not started** for this change. No measured Africa completion time or scientific trend result is claimed. The earlier observed Ghana 2005–2024 first soil-moisture download/analysis took **168.07 seconds**; a later fully cached two-variable A/B calculation took **5.70 seconds**. Those are Ghana observations, not Africa performance guarantees. A continent has more cells to calculate, and a scan multiplies the variables; first runs can take many minutes or longer depending on the connection, NASA and local computation.

## Suggested significant-trend examples

An educated first choice is **air temperature in Switzerland and Finland, 1981–2024**, beginning with one country and one variable. The longer full-year period is a stronger starting point for detecting a persistent climate signal than the earlier 20-year Ghana example. This is a hypothesis for TerraTrend to test, not a fabricated p-value or a guarantee that its reanalysis and adjusted test will match a national observational analysis.

The Finnish Meteorological Institute reports clear long-term annual warming and discusses substantial decade-to-decade variability. That supports Finland as a candidate, while explaining why short windows can be noisy. [FMI research summary](https://en.ilmatieteenlaitos.fi/news/55HzVqhEyUskN4O8sqrWIc).

MeteoSwiss's Climate CH2025 assessment documents strong observed Swiss warming through 2024. This supports Switzerland as a second small-country example. [MeteoSwiss assessment](https://www.meteoswiss.admin.ch/dam/jcr%3A75c75c1b-ff3d-42a7-aa5c-4eabfc222d37/Broschuere_CH2025_EN_Spread.pdf).

Neither example was downloaded or analyzed here. The earlier Ghana results had positive estimated slopes but did not pass the adjusted Mann–Kendall significance threshold for 2005–2024; that is not proof of no change. See [the recorded live results](LOCAL_VERIFICATION.md).

## Drivers, responses and limits

Interconnections already screens candidate local drivers, remote responses and possible lead/lag relationships, with conditional diagnostics and multiple-test correction where supported. It can display the evidence and map links. It does not establish the physical cause of a long-term trend, demonstrate a transport path, or forecast what the trend will cause in future. A significant temperature trend alone does not make such claims valid. Relationship screening is a separate, potentially larger data request and now passes through the same review.

## Verification

New regressions first reproduced the missing area-only dispatch and the absence of a download-review gate. The implementation then passed **60 frontend tests**. Coverage includes empty-selection discovery, supported measurement filtering, primary-only scan identity, review rejection without job submission, stale selection rejection, result-to-Analysis navigation, distinct result states, cache-only estimates, A/B and layer estimates, companion/remote variables, dateline bounds and the actual review's Start/cancel promise.

The backend suite passed **146 tests, with one opt-in legacy POWER network test skipped and five passing subtests**. No backend source, token handling or scientific method was changed. JavaScript syntax, unique HTML IDs, local script assets and `git diff --check` passed.

`node --experimental-test-coverage --test tests/data-review.test.cjs` reports **100% line coverage, 82.35% branch coverage and 90% function coverage** for the new review module. Its eight tests include the pending review, Start, cancellation, backdrop, Escape, focus restoration and Tab containment.

Browser checks verified Africa with zero selected variables, the eight-measurement review at **548.5 MB**, the one-temperature review at **68.6 MB**, closing/cancellation and restored controls. The **Start this request** button was not clicked. The validated observation cache remained at **1,167 files / 35,428,316 bytes**, matching its pre-check state. See the [saved verification facts](local-handoff/discovery-2026-11-15/verification.json).

Screenshots: [area-only discovery review](local-handoff/screenshots/2026-11-15-africa-discovery-review.jpg), [one-variable review](local-handoff/screenshots/2026-11-15-africa-single-variable-review.jpg).

All existing uncommitted work was retained. Changes remain local and uncommitted; the running Earthdata connection was retained because no backend restart was needed.
