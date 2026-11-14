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

> **Status: DONE (2026-11-13).** Implemented as `test_currency.py` (8 tests):
> `_annualize()` now returns `{year, value, months, complete}`; only years with
> 12 valid months enter any trend test. The reference probe confirms the trap
> is real — Central Europe's 2026 partial mean is **11.96 °C** (Jan–Sep) vs
> **9.39 °C** for full-year 2025; including it would have manufactured a
> +2.6 °C jump. The UI draws partial years as an isolated hollow diamond,
> joined to nothing, with the note "shown, excluded from trend".

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

> **Status: DONE.** The catalog now holds **16 variables** in three groups
> (temperature / water / atmosphere), each verified live via
> `test_catalog.py` with `TERRATREND_NET=1` (all 16 return data).
> First result from the new set: Sahel root-zone soil moisture is rising
> **+0.015/decade, p = 0.024, 14/25 cells** — a coherent companion to the
> documented rainfall recovery.

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

> **Status: DONE.** 4 ocean regions added (Central Pacific, North Atlantic,
> Indian Ocean, Southern Ocean) and every region now carries
> `surface: land|ocean`. Verified: `TS` over the North Atlantic returns a full
> 21-complete-year series (+0.213 °C/decade, p = 0.264 — genuinely not
> significant in that box, which is the honest answer).

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

> **Status: DONE.** `theil_sen_ci()` implements the Gilbert (1987) normal
> approximation; `analyze_series()` now returns `ci_low/high` and
> `ci_low/high_per_decade`. Shown under every chart, e.g. Europe Min
> Temperature **+1.100 °C/decade, 95% CI [+0.612, +1.560]**. 4 new tests,
> including "CI must contain the true slope" and "noise widens the interval".

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

> **Status: DONE.** `GET /api/scan` scores every variable on the same 5×5 grid
> as the full analysis (so p-values agree when you open a row), ranks by
> significance then |τ|, and retries any variable that POWER throttles.
> The UI scans in **chunks of 4 with progressive rendering**, so results appear
> as they arrive instead of one long hang. `warm_scan.py` pre-warms demo regions
> (Sahel: 42 s cold, 0 failures; Europe: 6 s warm).
>
> **What it found on its first run** (Europe 2005–2026): minimum temperature is
> warming fastest at **+1.10 °C/decade, p<0.001**, ahead of mean (+0.96) and max
> (+0.94) — the well-documented asymmetric warming of cold extremes — plus
> specific humidity rising (+0.23 g/kg/decade, p=0.001). On the Sahel the scan
> ranked evapotranspiration (+0.09 mm/day/dec, p=0.002), root-zone moisture
> (+0.013, p=0.024) and specific humidity (+0.26, p=0.034) above precipitation
> (p=0.057) — a coherent water-cycle story the single-variable view would hide.

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

## 3b. Ghana / El Niño verification (2026-11-13)

Ghana is now in the catalog as three regions — **Ghana North**, **Ghana South**
and **Lake Volta** — so the local demo runs through the real app.

**The headline finding: the popular "El Niño dries Ghana" framing does NOT hold
in the annual data. Do not build the demo on it.**

What the data actually says (POWER + NOAA ONI, 1991–2025):

| Test | Result |
|---|---|
| Current state | **2026 is a very strong El Niño** — ONI +2.46 (ASO), +1.80 (JJA) |
| Annual precip vs ONI, Ghana North | r = **−0.04** (none) |
| Annual precip vs ONI, Ghana South | r = **−0.12** (weak) |
| El Niño (ONI≥0.8) vs La Niña years, North | 3.21 vs 3.26 mm/day — **0.05 mm/day difference** |
| **JAS (main rainy season) vs ONI, both regions** | r = **−0.25** — the only consistent signal |
| OND (minor season), North | r = +0.30 (slightly wetter) |
| Lagged (previous-year ONI) | North +0.25, South −0.13 — inconsistent |

So El Niño's fingerprint on Ghana is **seasonal and modest**: it nudges the
main Jul–Sep rainy season drier, not the annual total. Southern Ghana's driest
year (1998, 2.08 mm/day) came the year *after* the 1997–98 El Niño — a lag.

What *is* strong and defensible in Ghana:

| Region | Variable | Trend |
|---|---|---|
| **Ghana South** | Precipitation | **+0.688 mm/day/decade, p = 0.002**, CI [+0.262, +1.046] |
| **Ghana South** | Air temperature | **+0.212 °C/decade, p = 0.003**, CI [+0.096, +0.324] |
| **Ghana North** | Precipitation | **+0.332 mm/day/decade, p = 0.014**, 14/25 cells |
| Ghana North | Air temperature | +0.093 °C/decade, p = 0.526 — not significant |

**Recommended Ghana demo (defensible):**
1. Open **Ghana South**, run the SCAN — the tool finds significant warming **and**
   significant wetting. Two answers in one place.
2. Show **Ghana North** precipitation (+0.33, p=0.014) — the Sahel-recovery
   pattern reaching Ghana's north.
3. Then say the honest thing about El Niño: *"We tested the El Niño hypothesis
   directly against NOAA's ONI index. The annual correlation is essentially zero
   — the effect is concentrated in the Jul–Sep rainy season (r = −0.25). We
   report the seasonal signal and we do not overclaim a drought."*
4. Close with the live hook: **2026 is one of the strongest El Niño events on
   record (ONI +2.46)**, and this tool will measure what it does to Ghana.

**Follow-up feature worth building (not done):** an **ENSO context strip** in the
app — current ONI plus shading of El Niño years on the time-series chart, so the
seasonal relationship is visible instead of asserted. Effort **M**.

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
