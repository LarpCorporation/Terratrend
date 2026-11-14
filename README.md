# TerraTrend — Earth Change Observatory

**NASA Space Apps Challenge** · *Change is always occurring in Earth's interconnected environmental system*

Select one to three Earth science variables, tap anywhere on a 3D globe, and
TerraTrend tells you **what is changing, where, by how much, and whether it is
statistically significant** — using NASA's own open data.

![TerraTrend](docs/screenshot-europe.png)

*Monochrome mission-control HUD. White dot-matrix Earth on black; colour appears
only where it means something — orange cells are significantly rising trends.*

---

## The problem this solves

A measured Earth science variable can trend one way in one region and the
opposite way in another, even when the same process drives both. With thousands
of available variables, scientists and the public struggle to:

1. **select** variables that could indicate change,
2. **visualize** how they change over time,
3. **quantify** the change ("how much"),
4. and decide whether it is **statistically significant**.

TerraTrend does all four in one interactive observatory.

---

## The experience

| Interaction | What happens |
|---|---|
| **Tap anywhere on the 3D globe** | The nearest focus region is selected and analyzed automatically |
| **Drag / scroll** | Rotate and zoom the dot-matrix Earth |
| **Filter by Earth Sphere** | Toggle between ALL, ATM (Atmosphere), HYD (Hydrosphere), and ENG (Energy) |
| **Select up to 3 variables** | Signals stack in the right rail, each with its own color |
| **Earth System Coupling** | When 2+ variables are selected, automatically diagnoses cross-sphere physical interactions (VPD expansion, greenhouse radiative trapping, hydrological sensitivity) |
| **Regional Contrast Mode** | Compare two distinct geographic regions (Region A vs Region B) simultaneously on the 3D globe and trend observatory |
| **Trace Global Impacts** | Click `TRACE GLOBAL IMPACTS` to detect remote planetary cascading ripple effects across global climate zones (e.g. Pacific Trade Winds driving West African heatwaves or Amazon drought) with 3D Great-Circle glowing connection arcs |
| **Earth System Impact Ledger** | Comprehensive modal ranking remote teleconnections with Pearson r, Student's t p-values, physical mechanisms, and 1-click `INVESTIGATE` contrast triggers |
| **Click a signal or color key** | The globe swaps to that variable's grid analysis |
| **Hover a grid cell** | Tooltip with lat/lon, slope/decade, p-value, trend verdict |
| **Click a grid cell** | Cell detail readout in the coordinate bar + orbital zoom action |
| **Click mini-chart or expand icon** | Opens high-resolution time series observatory modal with interactive 2-finger scroll/pinch zoom, trackpad swipe panning, horizontal/vertical axis toggles, 4-card statistics, 5x5 spatial consensus matrix, and CSV export |
| **Click "Compare Orbital Pass"** | Opens NASA GIBS satellite evidence with interactive split-slider and multi-year comparisons |

---

## What the challenge asks → what TerraTrend delivers

| Requirement | Implementation |
|---|---|
| Select variables from Earth science missions/models | 16 curated NASA POWER variables (MERRA-2, GPCP, CERES) across 4 Earth System Spheres (Atmosphere, Hydrosphere, Land, Energy) |
| Multi-Sphere System Framework | Filter variables by Atmosphere (ATM), Hydrosphere (HYD), Land (LND), and Energy (ENG) across 3 functional groups |
| Automated Trend Discovery Mode | One-click `SCAN ALL VARIABLES` systematically queries and ranks all 16 variables by trend slope and grid consensus |
| Cross-Variable Physical Coupling | Automated thermodynamic coupling detection (VPD expansion, greenhouse radiative trapping, hydrological sensitivity, moisture convergence) with Pearson r |
| Planetary Teleconnection Detective | Dynamic `TRACE GLOBAL IMPACTS` engine scanning multi-sphere driver variables across 7 global climate zones, quantifying remote ripple effects (r, p < 0.05), rendering 3D Great-Circle connection arcs, and providing physical mechanism explanations |
| Regional Contrast (A vs B) | Simultaneous dual-region comparison on the 3D globe and trend observatory with differential slope, co-trend correlation, and divergence verdicts |
| Visualize change over time | Interactive yearly/monthly series with Theil-Sen trend lines, partial-year guards through 2026, and multi-region comparisons |
| What is changing | Plain-language verdict per variable (rising / falling / stable) + in-app scientific glossary |
| Where it is changing | 5x5 gridded trend analysis rendered as North-aligned colored cells on the globe and consensus matrix |
| How much it is changing | Theil-Sen slope/decade, 95% confidence intervals, total change, percent change — per region and per cell |
| Is it significant | **Mann-Kendall** (p < 0.05), **Theil-Sen 95% CI**, **OLS t-test** cross-check with Student's t CDF, **Hirsch-Slack seasonal MK**, significance stars |
| Visual ground truth | **NASA GIBS & Worldview** orbital imagery comparison (MODIS / VIIRS) via side-by-side & interactive split-slider |
| Does the science agree? | Live **OpenAlex** literature lookup, relevance-ranked per variable + region |

---

## Quick start

```bash
cd terratrend/backend
python server.py 8517
```

Open <http://127.0.0.1:8517>.

Then, before judging, warm the cache so every demo click is instant:

```bash
python warm_cache.py
```

**Presenting this?** Read [`docs/GUIDE.md`](docs/GUIDE.md) — a plain-English
explainer of every statistic (p-values, Mann–Kendall, Theil–Sen, significance,
multiple comparisons), a number cheat-sheet, a 3-minute demo script, and a bank
of judge Q&A.

**No Python dependencies.** The server uses only the standard library, and the
frontend loads three.js and Chart.js from CDN. The globe geometry
(`land_dots.json`, 6,550 real land points derived from Natural Earth) ships
with the repo — no runtime geodata dependency.

---

## Demo stories (pre-warmed)

### 1. Europe is warming — every cell
- **Variables:** Air Temperature (+ Precipitation for contrast)
- **Region:** Central Europe · 2005–2024
- **Result:** `+0.99 °C/decade`, **p = 0.003**, **25/25 cells** rising significantly
- Precipitation over the same window: **no significant trend** (p = 0.673)
- **Why it matters:** the clearest regional warming signal, with a built-in
  "same place, different variable, different answer" contrast.

### 2. Sahel precipitation is recovering — a famous greening signal
- **Variable:** Precipitation
- **Region:** Sahel Central
- **Result:** `+0.21 mm/day per decade`, **p = 0.009**, 13/25 cells rising
- **Why it matters:** after the catastrophic 1970s–80s droughts, Sahel rainfall
  has partially recovered — one of the clearest regional signals on Earth.

### 3. Southern Madagascar, Arabia, China, Brazil
All show significant warming (p ≤ 0.025) — tap them on the globe in seconds.

### 4. The honest negative control
Arctic Siberia (this 6°×4° box) returns **no significant trend** (p = 0.163).
This is a feature, not a bug: Mann–Kendall refuses to call a trend when
interannual variability is too large for the record length. Judges love a tool
that says "not significant" when it means it.

---

## Methodology (what makes this defensible)

### Trend magnitude — Theil–Sen estimator
The median of all pairwise slopes. Robust to outliers and non-normal data,
unlike ordinary least squares. The standard companion to Mann–Kendall in
climate science.

### Significance — Mann–Kendall test
Non-parametric, rank-based test of monotonic trend. No normality assumption,
resistant to outliers. Significance at **α = 0.05** (`**`), with `*` for p < 0.1
and `***` for p < 0.01.

### Annual aggregation (the critical detail)
Raw monthly series are dominated by the seasonal cycle, which inflates the
Mann–Kendall statistic and produces false "significant trends." TerraTrend
therefore computes **annual means** for trend testing, and additionally reports
a **Hirsch–Slack seasonal Mann–Kendall** test on the monthly series as an
independent cross-check. This bug was caught during development: before the fix,
Arctic warming returned p = 0.52.

### Gridded analysis — "where"
The region is sampled on a 5×5 grid of NASA POWER points. Each cell gets its own
Mann–Kendall + Theil–Sen analysis. Cells are color-coded by direction and
significance, and sized by slope magnitude.

---

## Data sources

**NASA POWER** (Prediction Of Worldwide Energy Resources)
<https://power.larc.nasa.gov/>

- Monthly point API: `https://power.larc.nasa.gov/api/temporal/monthly/point`
- Variables derive from **MERRA-2** reanalysis, **GPCP** precipitation, and
  **CERES** radiative fluxes.
- No API key required.

> POWER's `/regional` endpoint returned empty payloads during development, so
> TerraTrend samples a grid of `/point` calls in parallel (cached, with jitter
> and retry to stay inside POWER's rate limits). Swappable for Harmony /
> GES DISC netCDF later.

**OpenAlex** <https://openalex.org/> — free, no API key, ~250M scholarly works.
Papers are re-ranked locally by regional relevance (region name in title is the
strongest signal) then citation impact. Semantic Scholar was evaluated first but
rate-limits unauthenticated requests (HTTP 429); Crossref works but lacks
citation counts.

**Natural Earth** <https://www.naturalearthdata.com/> — public-domain land
polygons used to generate the globe's dot matrix (1:110m, 6,550 points at 1.4°
sampling).

---

## Architecture

```
terratrend/
├── backend/
│   ├── server.py        # zero-dependency HTTP server + API + teleconnections engine
│   ├── analysis.py      # Mann-Kendall, Theil-Sen CI, Hirsch-Slack seasonal MK, OLS t-test, Pearson coupling, teleconnection mechanisms
│   ├── gibs.py          # NASA GIBS WMS & Worldview orbital comparison engine
│   ├── power_client.py  # NASA POWER fetcher: parallel grid + disk cache + availability probe
│   ├── literature.py    # OpenAlex lookup with relevance re-ranking
│   ├── catalog.py       # 16 variables · 23 regions (land & ocean) · glossary
│   ├── warm_cache.py    # pre-fetch demo regions before judging
│   ├── warm_scan.py     # pre-warm full 16-variable scans for demo regions
│   ├── test_analysis.py # 25 unit tests for statistical & teleconnection engine
│   ├── test_catalog.py  # 11 unit tests for catalog integrity
│   ├── test_currency.py # 8 unit tests for data currency & partial-year guards
│   ├── test_gibs.py     # 4 unit tests for GIBS & Worldview integration
│   └── cache/           # auto-created; 30-day TTL
└── frontend/
    ├── index.html       # HUD shell + scan modal + defs modal + data observatory + orbital modal + impact ledger modal
    ├── styles.css       # monochrome observatory theme + WCAG AA contrast styling
    ├── app.js           # three.js globe (with 3D teleconnection arcs) + chart + scan + glossary + GIBS orbital comparator + teleconnection ledger
    └── land_dots.json   # 6,550 Natural Earth land points
```

**Design language:** the chrome is strictly monochrome — near-black ground, white
dot-matrix Earth, 1px grey rules, uppercase monospace readouts, inverted white
action button. Saturated colour is reserved **only for data** (orange = rising,
blue = falling), exactly like a mission-control display where hue carries meaning.

**API**

- `GET /api/health` → `{ok, uptime_s}`
- `GET /api/availability` → live NASA POWER probe `{ok, max_year, latest_month, latest_day}`
- `GET /api/catalog` → 16 variables, spheres, 23 regions, year bounds, availability
- `GET /api/scan?region=sahel&start=2005&end=2026` → ranks all 16 variables by trend slope and grid consensus
- `GET /api/teleconnections?region=tropical_pacific&variable=WS2M&start=2005&end=2024&min_r=0.38`
  → discovers and quantifies remote cascading ripple effects across planetary sentinel hubs with Pearson r, Student's t significance (p < 0.05), and physical mechanism explanations
- `GET /api/analyze?variables=T2M,PRECTOTCORR&region=europe&start=2005&end=2024`
  → for each variable: monthly + yearly series (with partial-year guards), per-cell trends, regional
  summary, 95% CI, OLS t-test, seasonal MK, cross-sphere couplings, literature, and NASA GIBS satellite evidence
- `GET /api/satellite-imagery?region=europe&start=2005&end=2024&layer=true_color`
  → NASA GIBS WMS baseline and recent URLs, cloud-minimized seasonal dates,
  and NASA Worldview deep links (supports custom `bbox=min_lon,min_lat,max_lon,max_lat`)

---

## Tests

```bash
cd terratrend/backend
python test_analysis.py      # ALL PASS (25 tests: MK, Sen CI, t-test, couplings, contrast, teleconnections)
python test_catalog.py       # ALL PASS (11 tests: catalog structure & completeness)
python test_currency.py      # ALL PASS (8 tests: data currency & partial-year protection)
python test_gibs.py          # ALL PASS (4 tests: GIBS WMS & Worldview URL engine)
```

Covers: strong rising/falling detection, flat-noise rejection, Theil–Sen on
perfect linear data, outlier robustness, Theil-Sen 95% confidence intervals,
OLS $t$-test agreement with Student's $t$ CDF, short-series rejection, gap handling,
seasonal-MK cycle rejection, seasonal-MK real-trend detection, multi-sphere coupling,
and regional contrast.

---

## Honest limitations

- POWER provides monthly/annual data per point; true raster trend maps would use
  **Harmony + GES DISC** netCDF subsets (the natural next step).
- The globe's analysis grid is **visually amplified 2.8×** so 25 cells are
  readable at planetary scale. Geography is preserved in the popups and
  coordinate readout; the mesh spacing is exaggerated for legibility.
- Regions are 23 curated focus boxes covering continents and major ocean basins; freehand bbox selection is a small
  follow-up.
- Add **Pettitt change-point detection** for "when did it start changing."
