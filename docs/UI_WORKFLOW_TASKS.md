# Approved interface task order

Requested and approved ('do it') on 15 November 2026. Implemented in the existing checkout, preserving uncommitted changes. See [implementation and verification](UI_WORKFLOW_IMPLEMENTATION.md) for the completed behavior, evidence and practical limits. The problem descriptions below record the starting state.

## Current behavior and confirmed problems

- Header Analyze and drawer Analyze Selected Area call the same action. With selected variables it analyzes A, or A/B in comparison mode; with no variables it scans supported measurements for A.
- Analyze Layer requests every feature in the displayed layer and only the first selected variable. It explicitly removes comparison B from the request. It is not the selected Ghana/Nigeria comparison action.
- Opening Compare while in single-area mode toggles comparison mode. That calls `prepareInvestigation`, which clears the existing result and map. This confirms a navigation-triggered data-loss path rather than a need to download the observations again.
- Interconnections uses a separate overlay and navigation forces recomputation. It does not behave like the Analysis/Compare pages.
- The movable A/B card's Run Analysis area is intended for a computed trend summary. Before a result it shows placeholders; Open Analysis opens the page without starting a calculation. This needs explicit ready/running/result states.
- Provider selection currently controls which measurements are enabled. Automatic routing by both measurement and area is not implemented yet; the linked mode routes by measurement only.

## Recommended priorities

1. **Retain the investigation and results during navigation.** Keep A/B, variables, dates, computed analyses, comparison evidence and map overlays. Separate editing from navigation, and keep prior results available with their original context when a new investigation is prepared.
2. **Clarify request scope and remove duplicate Analyze actions.** One primary action analyzes the selected areas and variables. No-variable discovery is explicit. Move whole-layer analysis to a clearly named secondary action with its area count, never a surprise request for all countries.
3. **One investigation workspace.** Consolidate A/B, collapsible variable selection, filters, visible checkboxes, dates and run controls. Preserve the movable panel. Keep dates/actions visible, show selected-variable count, and replace the empty Run Analysis space with clear readiness, progress and result summaries. Other pages link back to edit the same investigation.
4. **Choose compatible sources automatically.** Enable all supported measurements without requiring provider expertise. Route by variable and exact selected geometry. Keep processing overrides in advanced settings and show actual sources after analysis. Preserve a consistent product/definition for direct A/B inference.
5. **Explain incompatible shapes and combinations before fetching.** Name the affected variable/area, the limitation and a useful next step. Offer buttons to activate rectangle/bounds tools or change the measurement. Retain existing areas until the user commits a replacement. Restrict tools when a selected route genuinely requires it.
6. **Populate Analysis and Compare from the same investigation.** Reuse completed values. With A only, Compare explains how to add B; with both present, it shows both without clearing A or repeating an unnecessary download. A one-variable run and a multi-variable run use the same clear rules.
7. **Make Interconnections a normal page.** Use the current areas, measurements and dates. Show ready/running/completed/unavailable states. Offer one clear run/edit path, no automatic remote scan on navigation. Support explicit selected-area remote comparisons; a single focus variable needs clearly disclosed companion choices. Keep association separate from causal attribution and future impacts.
8. **Connect remote evidence to the globe.** View on Map opens source/target arcs, variable colors and a visible legend. Hover shows evidence; clicking pins the detail. Support inspecting several links and opening the corresponding regional series together. Retain the overlay when returning from another screen. Use directional arrows only where a temporal lead is supported.
9. **Readable local relationship diagram.** Use familiar measurement names, readable labels and source details when useful. Distinguish an incoming candidate, an associated response and a simultaneous relationship with no resolved lead. Do not invent arrows to imply physical causation.
10. **Explain trend numbers and statistics.** Put units and time basis directly beside rates, such as °C per decade. Use plain-language significance, sample-size and missing-data labels; explain statistical symbols in contextual help. Make series and region identities clear in graphs.
11. **Show distance from the fitted trend in chart tooltips.** Include observation, fitted value and signed difference with units and above/below wording, using the actual displayed trend and calendar dates. Keep partial/missing observations explicit.
12. **Show connected account states.** Connected/remembered status replaces the unused login prompt; reconnect and forget remain deliberate actions. Handle expiry and service-specific failures clearly without exposing saved credentials.
13. **Add a guided walkthrough.** A short skippable tour highlights area selection, variables, dates, Analyze, Compare, relationships and result meanings. It is available again from Help and uses the current interface after the earlier changes settle.
14. **Change the direction colors last.** Blue for increases/above-trend, red for decreases/below-trend, neutral for nonsignificant/missing states with distinct labels. Apply consistently across maps, charts, badges, tooltips and keys; keep variable-identity colors distinguishable from trend direction.

Each approved increment needs focused regression checks and browser verification. The latest existing source work passed 217 backend and 68 frontend tests, plus 43 backend subtests; that does not mean these proposed UI tasks are complete.

## Source-routing constraint

Giovanni is a faster route only for supported products and actual compatible rectangles. The current connector has temperature/humidity at 2 m and 10 m; it has no verified precipitation mapping. A kilometre-based square is not necessarily an axis-aligned latitude/longitude rectangle. Different MERRA-2 collections can give different monthly values even with similar variable names. Automatic routing must preserve the selected boundary and make A/B scientific compatibility part of its decision, rather than equating two products by label.
