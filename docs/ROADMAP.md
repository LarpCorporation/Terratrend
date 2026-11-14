# TerraTrend — Gap Analysis & Roadmap

Built from the challenge brief, the teammate notes, and the official
[NASA Space Apps resource list](https://www.spaceappschallenge.org/2026/challenges/earth-system-trend-detective/?tab=resources).
Every claim below was verified against the live APIs on **2026-11-13**.

---

## 1. Where we stand against the challenge

The brief names four elements a successful response must bring together:

| # | Required element | TerraTrend today | Status |
|---|---|---|---|
| 1 | **Identify variables of interest** that can be investigated for trends | 10 curated POWER variables (MERRA-2 / GPCP / CERES) | ⚠️ Partial — 10 is thin vs "wide variety" |
| 2 | **Acquire data for a particular region** (most trends are regional) | 16 focus regions + 5×5 grid + custom bbox API | ✅ Met |
| 3 | **Generate and visualize a time series** over a long enough period | Yearly/monthly chart + globe + satellite imagery | ✅ Met |
| 4 | **Basic statistical analysis**: rate of change + significance | Theil–Sen slope + Mann–Kendall + seasonal MK | ✅ Met, but no **confidence intervals** |

So we already satisfy the four elements. Everything below is about *depth*.

---

## 2. Verified API facts (2026-11-13)

These numbers drive the whole roadmap:

| Fact | Value | How verified |
|---|---|---|
| POWER **monthly** data, latest valid month | **2026-09** | `T2M` series ends `202609`; `202610+` returns −999 |
| POWER **daily** data, latest valid day | **2026-11-10** | `PRECTOTCORR` daily, 314 valid days in 2026 |
| POWER daily payload, full 2005→2026 record | **0.13 MB, 1.1 s** per point | `T2M` daily pull |
| NASA GIBS imagery, latest working date | **2026-11-08** | MODIS true color, 27 KB JPEG, HTTP 200 |
| POWER works over **ocean** | ✅ | `T2M`/`TS` at 0°N 160°W return data |
| Extra POWER variables that work | | |
| `EVPTRNS` | Evapotranspiration | ✅ 273 months |
| `EVLAND` | Evaporation over land | ✅ |
| `GWETROOT` | Root-zone soil wetness | ✅ |
| `GWETTOP` | Surface soil wetness | ✅ |
| `TS` | Surface skin temperature | ✅ |
| `T2M_RANGE` | Diurnal temperature range | ✅ |
| POWER variables that **fail** (422) | `RUNOFF`, `CDD`, `HDD` | ❌ not in AG monthly |
| POWER parameter-catalog endpoints | `/api/system/manager/parameters` | ❌ 422 — enumerate manually |

---

## 3. The gaps to close

### P0 — correctness first (must fix before extending the date range)

**3.1 Partial-year bias in annual means** — *blocking, subtle, important*

Our `_annualize()` averages whatever months exist for a year. That is safe today
because every year ends complete. The moment data runs to 2026-09, the 2026
"annual mean" would average **9 months** (Jan–Sep) instead of 12, which is
seasonally biased — the trend would bend for a statistical artefact, not climate.

**Fix:** a year counts for trend testing only with **12 valid months** (or ≥11
with an explicit `partial: true` flag excluded from the slope). Show the partial
year on the chart as a distinct dashed/muted segment, never in the regression.
Effort: **S**.

**3.2 Remove the hard 2024 cap** — *blocking*

Three places hardcode it: `server.py:123-124`, `server.py:219`, `server.py:255`,
plus `gibs.py:127-128` and `warm_cache.py:41`.

**Fix:** derive from the calendar — `MAX_YEAR = datetime.now().year`; min stays
1981. Effort: **S**.

**3.3 Availability endpoint** — *enables the "through 2026" claim honestly*

`GET /api/availability` → probes one POWER point, returns
`{latest_month: "2026-09", latest_day: "2026-11-10", variables: {...}}`,
cached 6 h. The UI shows **"DATA THROUGH 2026-09"** in the header instead of a
hardcoded number. Effort: **S**.

---

### P1 — variable breadth (the explicit ask in the brief)

The brief says variables range "from simple ones like temperature and rainfall to
more complex ones like evaporation or streamflow". We have temperature, rain,
humidity, wind, radiation, pressure — the *simple* half.

**3.4 Add 6 verified POWER variables** (all confirmed working):

| ID | Name | Unit | Why it matters |
|---|---|---|---|
| `EVPTRNS` | Evapotranspiration | mm/day | the brief's "evaporation" |
| `EVLAND` | Evaporation (land) | mm/day | water balance |
| `GWETROOT` | Root-zone soil moisture | fraction | drought / agriculture |
| `GWETTOP` | Surface soil moisture | fraction | flash drought |
| `TS` | Skin temperature | °C | satellite-comparable |
| `T2M_RANGE` | Diurnal range | °C | climate fingerprint |

Effort: **S** (catalog entries only — pipeline is generic).

**3.5 Ocean regions** — POWER works over water; add 3–4 ocean boxes (central
Pacific ENSO, North Atlantic, Indian Ocean, Southern Ocean). Ship `TS` as the
ocean-friendly variable. Effort: **S**.

**3.6 Aerosol / vegetation / ocean-colour variables** — MODIS-derived (AOD,
NDVI), OMI (absorbing aerosol), SeaWiFS/MODIS chlorophyll. **Not** in POWER;
requires AppEEARS or GES DISC. See §5 resources. Effort: **L**.

**3.7 Streamflow / discharge** — the brief names it. Not in POWER. Options:
CUAHSI Hydrology Time Series API (public REST), or GLDAS `RUNOFF` via GES DISC.
Effort: **M–L**.

---

### P2 — analysis depth named in the brief

**3.8 Confidence intervals** — the brief lists "t-test, the Mann–Kendall test, or
confidence intervals". We do MK but report **no CI**. Add Sen's slope **95% CI**
(needs Kendall's τ variance, already computed) shown as
`+0.21 mm/day/decade [0.06, 0.36]`. Effort: **S**.

**3.9 t-test as a second opinion** — the brief names it first. Adding a Welch/OLS
t-test alongside MK lets us show *both* methods agreeing (or disagreeing when
outliers matter) — a strong "we know the limits" talking point. Effort: **S**.

**3.10 "Find variables that are trending" — the discovery mode** ⭐

This is **the first half of the challenge statement** and we do not have it.
Today the user must already know which variable to look at (exactly the problem
the brief describes).

**Design:** a **SCAN** button that runs all loaded variables over the current
region+window and returns a ranked table:
`variable · slope/decade · p · Significant? · cells rising/falling`, sorted by
|τ| then significance, with a one-line plain-English verdict per row.

Cost: N variables × 25 points, but cached — a 6-variable scan on a warm region is
~1 s. Effort: **M**.

**3.11 In-app variable definitions for a public audience** ⭐

The brief is explicit: *"Providing simple definitions of the variables would help
these users considerably"*, and the audience is high-school/college/public.

We have a one-line `desc` in a tooltip and a long `docs/GUIDE.md`. **Fix:** an
expandable "?" per variable with: what it measures, units in plain words, why it
matters, and what a rising/falling trend *means* (e.g. "soil moisture falling =
drier root zone = drought stress"). Effort: **S–M**, high judge value.

---

### P3 — real-time and 2026

**3.12 Near-real-time imagery** — GIBS already serves 2026-11-08. Raise the year
clamp in `gibs.py`, then auto-walk back day-by-day from "today − 2 d" until a
non-placeholder tile returns. Show **"LIVE · last pass 2026-11-08"**. Effort: **S**.

**3.13 Daily resolution** — POWER daily is cheap (0.13 MB / 1.1 s for 22 years).
Add a DAILY toggle: enables daily series, shorter windows (≥1 year), and rainfall
event analysis. The brief explicitly says daily and monthly are both acceptable.
Effort: **M** (fetcher + aggregation split).

**3.14 "Latest available month" badge + current-year window** — let the year
inputs reach the current year, clamp the *monthly* end to the newest valid month,
and mark the trailing partial year. Effort: **S** (with 3.1).

---

## 4. Resource integrations (official list)

The challenge page lists these. None are drop-in APIs except CUAHSI; the honest
integration is **prefilled deep links** — one click carries the region + period
into the right tool.

| Resource | What it gives us | Integration |
|---|---|---|
| **Giovanni** | Menus of many NASA variables; generates time series | Deep link with bbox + dates → covers AOD, chlorophyll, cloud, ozone we can't get from POWER |
| **Hydrology Time Series (CUAHSI)** | Streamflow / discharge series | **Public REST API** → real streamflow panels; or deep link |
| **AppEEARS** | Subset MODIS/VIIRS/ASTER, returns time series | Deep link (needs Earthdata login) → NDVI / LST / snow |
| **Climate Data Online (NCEI CDO)** | Station observations, mapping tool | Deep link → ground-truth cross-check of a POWER cell |
| **KNMI Climate Explorer** | Scientific climate analysis tool | Deep link → ENSO / larger-scale context |
| **SWOT (CSA)** | Water surface elevation for lakes/rivers | Future: reservoir/lake level trends |
| **RCM / Geo.ca (CSA)** | SAR imagery, Canadian geospatial data | Canadian case study, all-weather imagery |
| **Statistical significance guide** | Reference for the method page | Cite in `GUIDE.md` / in-app methodology panel |

**Recommended slice for this hackathon:**
1. A **RESOURCES** panel listing all of them with prefilled region+period links — cheap, visible, shows we read the brief. Effort **S**.
2. **One real integration**: CUAHSI hydrology API for streamflow (the brief's own example). Effort **M**, only if time allows.

---

## 5. What the brief says is out of scope

Worth quoting to judges instead of building:

- *"More complex trend analyses are beyond the scope envisioned… detecting and
  analyzing linear trends would be a great start."* → our linear/monotonic MK is
  exactly the intended scope; non-linear methods are explicitly optional.
- *"A response that does both the visualization and the analysis meets the full
  scope."* → we do both, plus source data and a literature check.
- *"Sometimes all a trend needs to become significant is a longer period."* → our
  exposed time-window controls already demonstrate this live (Europe: 0.58 →
  0.99 °C/decade as the window shortens).

---

## 6. Suggested order of work

| Order | Task | Effort | Why now |
|---|---|---|---|
| 1 | **3.1 partial-year rule** + **3.2 remove cap** + **3.3 availability** | S S S | Correctness before currency; without 3.1, "through 2026" produces wrong slopes |
| 2 | **3.4 six new variables** + **3.5 ocean regions** | S S | Biggest visible answer to the brief's first element |
| 3 | **3.10 SCAN discovery mode** | M | Answers the challenge's *first* half |
| 4 | **3.11 public variable definitions** | S–M | The brief explicitly asks for it |
| 5 | **3.8 CI** + **3.9 t-test** | S | The brief names both |
| 6 | **3.12 NRT imagery** + **3.14 badges** | S | Delivers "real time" |
| 7 | **§4 resources panel** | S | Cheap credibility |
| 8 | **3.13 daily resolution** | M | Enables the daily story |
| 9 | **3.6 / 3.7 complex variables, streamflow** | L | Only with real time left |

---

## 7. Talking points for judges (from the brief itself)

- *"The concept is to help users become data detectives"* — we should use that
  phrase; the SCAN mode (3.10) is literally the detective's magnifying glass.
- *"Trends can move in opposite directions in different regions, even from the
  same process"* — our 5×5 cell map is the direct answer.
- *"Finding a trend is interesting even if it doesn't reach significance"* — we
  report the slope even when p > 0.05 (Arctic Siberia: +0.63 °C/decade, p=0.163).
- *"Some trends are not evident unless regular cycles are removed"* — our annual
  aggregation + Hirsch–Slack seasonal MK is exactly that step.
