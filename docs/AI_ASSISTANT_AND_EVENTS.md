# Ask TerraTrend, reading levels and Events

Implemented in the existing checkout on 15 November 2026. The normal address is <http://127.0.0.1:8517/>. No commit, push, reset, clean, merge or deployment is part of this change. Existing uncommitted work and scientific caches are preserved.

## Use the assistant

Choose **ASK** in the header. Examples:

- “Scan all variables in Ghana from 2016 to 2024.”
- “Analyse air temperature in Ghana from 2016 to 2024.”
- “Compare air temperature in Ghana and Nigeria for 2016–2024.”
- “Find relationships between soil moisture and vegetation in Ghana from 2016 to 2024.”

The assistant prepares an explicit request. **Review data & run** sets the existing map controls and opens the normal data-use review. It uses the same geometry checks, automatic source routing, worker queue, cancellation, scientific engine and saved-result library as the map. Planning alone starts no scientific download. Discovery includes only the measurements compatible with the chosen area; the review discloses exclusions. A scan is not a forecast or causal attribution.

When a calculation finishes, the assistant displays an explanation and can open the evidence. Follow-ups such as “Is that significant?”, “What does the relationship score mean?” and “What caused this trend?” describe the stored result. They do not manufacture a cause, hazard or forecast. Questions about missing diagnostics say what the record cannot establish. The conversation remains in this page; completed investigations remain in the durable Saved library.

Common requests can be understood locally without a provider. Groq adds model interpretation for more flexible phrasing and relevance selection for verified explanations. Ambiguous places, unsupported variables, changed dates/areas, unrequested comparisons and unknown model actions fail closed with a clarification. The chosen primary area, comparison area and period stay authoritative even when taken from the current map selection; a model cannot turn a local relationship check into a remote one or expand a single-measurement request into a scan. There is no shell, arbitrary URL, filesystem, credential-management or unrestricted browser tool available to the model.

## Connect Groq when ready

Open **Data & Methods → Connect Groq**, enter the key in that local password field, choose a text model and press **Connect Groq**. Keep keys out of chat. Enable **Remember this connection privately on this computer** if persistence is wanted; it is opt-in. A connected badge replaces the form, with deliberate Update/Forget controls. NASA connections are separate.

The connector uses the fixed [Groq OpenAI-compatible endpoint](https://console.groq.com/docs/openai). Model choices include GPT OSS 20B/120B and supported Llama text models; the key is checked against the account’s active model list. GPT OSS requests use the documented [low reasoning effort](https://console.groq.com/docs/reasoning), bounded output and JSON mode. Schemas and scientific scope are validated locally even when provider output is valid JSON. Transport rejects redirects, limits response size, sanitizes errors and handles rate limits.

Only explicit assistant/explanation requests use Groq. The planner sends the question, a small set of region candidates, supported measurement names and current selection context. The explainer sends a bounded bank of already verified statements for the chosen reading level and question topic. Raw observation files, full time series, NASA credentials and other service keys are not included. Page navigation does not send an AI request.

The user chose **“I’ll connect later”** during verification. The connection form and mocked provider/transport contracts were checked, but **no live Groq request with the user’s key was verified**. Without Groq, deterministic explanations and common commands remain available.

## Reading levels and grounding

**Explain this result** and the assistant provide **Plain / Student / Researcher**. Changing the reading level changes wording and detail while retaining the same evidence fingerprint, statistics, sources and dates. The explanation dialog supports questions about that frozen result.

For Groq, model output selects/reorders IDs from the verified statement bank. The app renders the corresponding local statements; the model cannot introduce free-text scientific claims, numbers or causal assertions through that interface. Invalid selection, provider error or an unavailable key returns the local explanation. The existing advanced OpenAI-compatible environment route remains available with conservative checks on free-text output; those checks are not a general proof of semantic truth.

Explicit explanations are audited in the existing local results database’s `explanations` table, recording the evidence hash, result identity when supplied, reader level, question topic, analysis-method version, explanation version, model, selected wording and creation time. Raw chat questions and API keys are not stored there. No additional Python/JavaScript package is required.

## Teammates’ Events feature

Selectively integrated from `origin/events-and-ux`, commit `5b5a94fc344e4aff25cdb266052ddee740685a4a`. Imported the curated event network, image manifest, diagnostic engine, event interface and associated tests; adapted their wiring to the newer application. Unrelated theme changes, old navigation/job handlers, credentials changes and bulk data-warming commands were not merged over the working tree.

**Events** contains six curated stories, including El Niño, Ghana/West African drought, Amazon drought, Southern African drought, Arctic sea ice and a developing-event watch. Selecting a story opens the narrative, declared mechanisms, literature references, source/proxy disclosures and named globe points. This is editorial context, not evidence that the current investigation established its mechanism.

- Gold globe lines are catalogue pathways. They have no invented correlation or time lead.
- Blue links require an actually computed association surviving the diagnostic’s lag-family and false-discovery checks. A resolved lead can animate; simultaneous or unestablished leads do not.
- Clicking a line selects its evidence card. Marker hover/focus explains the place and its pathways.
- **Check with data** takes a user-selected window and prepares the exact source/area list for review. The backend rebuilds that list; client-supplied extra sources are ignored. No event observations are fetched by the catalogue/preview endpoints.
- Event checks use the source-matched native/linked routes to retain the catalogue connector’s actual product identity. They are not automatically changed to a different Giovanni product. Some sources/extents remain unsupported, with explicit reasons.
- Requested dates constrain every source and date alignment precedes correlation. The check tests associations across that window; it does not attribute the individual historical event to a cause.
- **Explain this event** distinguishes a story not yet checked from computed findings. Events can be saved/restored without replacing the ordinary map investigation.
- **Walk through an event** is a four-step interactive lesson. Actual selection, a trusted click to open pathway details, and opening its explanation complete action steps. Merely revealing an element for a spotlight cannot complete the learner’s action.
- Photographs load only when their disclosure is opened. Source/author/licence credits are retained. The server restricts image hosts, caps each download at 4 MB, checks image bytes and caches successful images locally. Missing images retain a readable failure note and source credits.

The added “Ghana study rectangle” is explicitly a box surrounding Ghana, including land beyond the border. It is not labelled an exact national boundary. Existing exact-country investigations remain separate. Proxy measurements and missing sea-ice observations remain disclosed; the watch item is not presented as a current forecast.

## Verification

Evidence is under `docs/local-handoff/ai-events-2026-11-15/`. The browser’s real Ghana chat run for 2016–2024 reused **108 of 108 monthly native subsets**. The computed temperature rate was about **−0.448 °C per decade**, with **p≈0.602**, so the assistant correctly reported no statistically significant trend for that window. This is a real cached-data check, not a fabricated demonstration or a new download.

Automated checks cover local and model planning, scope/date/field validation, reader levels, unsupported/causal claims, source caps, private connection handling, cross-origin writes, transport failures, audited explanations, event previews, authoritative request rebuilding, date alignment, cache/image behavior and real-action tutorial transitions. **371 backend tests passed**, with one existing opt-in network skip and 43 passing subtests; **102 frontend tests passed**. New-module line execution coverage, including HTTP handler threads, ranges from 88.8% to 100%; this is not branch coverage. Syntax and whitespace checks passed. The Events lesson was walked 4/4 with actual clicks; request reviews were cancelled before downloading event observations. The final run counts, screenshots, rollout details and remaining live-verification limits are recorded in `verification.json` in the evidence folder.
