# TerraTrend — engine briefing

Everything a judge, mentor or NASA person might ask about **how the data is
obtained** and **how it is interpreted**, with the exact numbers the code uses.

---

## The 30-second answer

> "We don't collect data ourselves. TerraTrend asks NASA's own services for the
> exact monthly grid cells that cover the area you selected, on demand, using the
> user's Earthdata account. We never download the global file and we never touch a
> CSV. For each month we take the cells that actually intersect the boundary,
> weight them by real ground area, and require that at least 80% of the selected
> area reported before the month counts. Then we run Theil–Sen and Mann–Kendall
> on the annual series, with an autocorrelation correction, and we report
> 'insufficient data' as its own outcome rather than pretending it's 'no trend'."

---

## Part 1 — How the data is obtained

### The short version

```
you pick a place  →  NASA CMR lists real published months
                  →  NASA OPeNDAP returns just the cells in that place
                  →  we decode, validate units, and cache the raw bytes
                  →  we average with area weights
                  →  one number per month
```

### The detail, with the actual services

| Step | What happens | Where |
|---|---|---|
| 1 | Boundary → native grid cells that intersect it | `spatial.cells`, 0.625° × 0.5° |
| 2 | Which monthly files exist for this collection and period | NASA **CMR**: `cmr.earthdata.nasa.gov/search/granules.json` |
| 3 | Request only the needed field and window for one month | NASA **GES DISC OPeNDAP**: `opendap.earthdata.nasa.gov` |
| 4 | Decode, validate axes, reject fill/mask, verify units, convert | `netCDF4` + `nasa_data.decode_subset` |
| 5 | Cache the raw response bytes | `backend/cache/nasa/subsets/<sha256>.nc4` |
| 6 | Area-weighted mean over intersecting cells | `spatial` overlap × cos(latitude) |
| 7 | Coverage audit | ≥ **80%** of selected area must report |

**Key point to state clearly:** CMR is public — it tells us which months genuinely
exist. The observations themselves need the user's Earthdata login. File names are
**never constructed locally**; we only use what NASA publishes.

### What each source provides

| Source | What it is | Access |
|---|---|---|
| **MERRA-2** (M2TMNXSLV / LND / FLX) | NASA reanalysis, monthly, 0.625° × 0.5°, from **Jan 1980** | Earthdata |
| **Giovanni / Harmony** (M2IMNXASM) | Rectangle area-averages, 4 fields only | Earthdata |
| **AppEEARS** | MODIS monthly NDVI / EVI, polygon processed by NASA | separate token |
| **Hydrology Time Series** | GLDAS soil water, soil temperature, wind | Earthdata |
| **NOAA Climate Data Online** | Station observations, fixed cohort | no key needed |

### Honesty point — say this before you're asked

**MERRA-2 is a reanalysis, not a thermometer.** It is a numerical model of the
atmosphere that assimilates real observations. That is a legitimate, standard NASA
product — but the honest phrasing is *"computed from NASA reanalysis data"*, not
*"measured at every point"*.

Related: MERRA-2's `TS` is **surface skin temperature**, used as an **SST proxy**.
It is not the NOAA ERSSTv5 reconstruction, and the interface says so.

---

## Part 2 — How it is interpreted

### Step A: months → years

- A month counts only if ≥ **80%** of the selected area reported.
- A **year** counts only if all **12** months did. Partial years are excluded, not
  extrapolated. (This is why 2026 currently sits out — only 9 months published.)
- Minimum useful span: **9 calendar years** for a trend (the engine also refuses
  fewer than 8 data points). Below that it says *"insufficient data"*.
- **Relationships** need **at least 36 overlapping months** — three years of
  paired observations — before any lagged correlation is attempted.

### Step B: the trend test (`backend/analysis.py`)

| Component | What it does | Why |
|---|---|---|
| **Theil–Sen slope** | median of the slopes between all pairs of years | resistant to outliers and single bad years |
| **Mann–Kendall** | non-parametric trend test, **with AR(1) autocorrelation correction** | annual means are serially correlated; the uncorrected test overstates significance |
| **Confidence interval** | Kendall-based interval around the slope | gives a range, not just a point |
| **OLS + t-test** | reported *alongside* as a cross-check | if the two disagree, say so |

**Exact decision rules:**

```
ALPHA = 0.05
significant       → Mann–Kendall p < 0.05 after the AR(1) correction
direction         → "rising" / "falling" if significant
                  → provisional direction if 0.05 ≤ p < 0.1
                  → "flat" otherwise
stars             → *** p<0.01   ** p<0.05   * p<0.1
anything < 8 years → "insufficient data (<8 points)"  — not "no trend"
```

We also report **`p_uncorrected`** next to the corrected p, so anyone can see how
much the autocorrelation correction changed the verdict.

### Step C: comparing two areas

A/B comparison uses **only years complete in both places**, forms the **paired
difference series**, and tests that difference. Reporting "it warmed in both" is
weaker than "the difference between them is / is not significant".

### Step D: relationships / interconnections

1. Remove the seasonal cycle **and** the trend jointly → anomalies ("when did this
   run above its own history").
2. Lagged cross-correlation over a **±6 month** window.
3. p-value corrected for **effective sample size** (autocorrelation) **and** for
   the lag-search family (**Bonferroni ×13**).
4. **Benjamini–Hochberg** false-discovery control across every pathway tested.
5. Optional **partial correlation** to screen a shared confounder, and a
   **Granger F-test** for whether knowing X's past helps predict Y.

---

## Part 3 — The words to use and the words to avoid

| Say | Don't say |
|---|---|
| "NASA reanalysis data" | "NASA measured it" |
| "the data shows a trend of…" | "climate change caused…" |
| "statistically significant increase" | "definitely getting hotter" |
| "the areas are associated, with a two-month lag" | "El Niño causes this" |
| "insufficient data" | "no trend" |
| "we don't claim that" | (silence) |

**Missing data is not evidence of no change.** Distinct outcomes are shown
separately: significant increase, significant decrease, not significant,
insufficient observations, source error.

---

## Part 4 — Questions you should expect, and the answers

**"Where does your data actually come from?"**
> NASA GES DISC, product MERRA-2 version 5.12.4, three collections — M2TMNXSLV
> for atmosphere, M2TMNXLND for land, M2TMNXFLX for fluxes. Discovery through
> NASA CMR, retrieval through GES DISC OPeNDAP, authenticated with the user's
> Earthdata account.

**"How do you get it — scraping, APIs, manual?"**
> APIs only, and fully automatic. CMR lists which months exist; OPeNDAP returns
> just the cells covering the selected area. No web scraping, no manual CSV
> uploads — that was a deliberate design requirement.

**"Is the data real, or is it generated?"**
> It's NASA's. We keep the raw response bytes on disk with the granule ID and the
> exact request URL, and there's a checker that re-decodes them without using any
> of our code. *(Point them at `data_verification/`.)*

**"Is it a model or a measurement?"**
> A reanalysis — a model constrained by assimilated observations. We say so.

**"What's your spatial resolution?"**
> Native 0.625° longitude × 0.5° latitude, roughly 62 × 55 km at the equator.
> A sharper boundary on the map does not create sharper data.

**"How do you know a trend is real?"**
> Theil–Sen slope plus Mann–Kendall with an AR(1) autocorrelation correction, at
> p < 0.05, with a confidence interval, and an OLS test as a cross-check. We also
> show the uncorrected p so the correction is visible.

**"Could your trend be an artefact?"**
> Yes, in these specific ways: a short record, a coarse grid, serial correlation
> (which is why we correct for it), missing months in a year, or a change in the
> dataset version. Each of those has its own visible state in the app rather than
> being silently smoothed over.

**"Correlation doesn't equal causation — do you claim it does?"**
> No. Interconnections report association, timing and false-discovery control.
> They never claim mechanism, and they don't model physical transport.

**"Why is Ghana 1982–83 weak?"**
> Because MERRA-2 begins in 1980. That event has at most three years of preceding
> record, and the usual 1981–2010 baseline contains the drought itself. The panel
> says this rather than hiding it.

**"What about the 2026 El Niño card?"**
> It's a watch, not a forecast. The Pacific driver is observable now; the regional
> rainfall response lags by months and hasn't happened yet. We report the observed
> Pacific state and the historical lag relationship, and we don't predict.

**"What are you *not* doing?"**
> Three clean answers: no claimed physical attribution, no future prediction, and
> no substitute dataset when a real one is missing — a pathway with no source is
> labelled `awaiting_source` instead.

---

## Part 5 — Where to point a sceptic

| They ask | Open |
|---|---|
| "Show me the raw data" | `data_verification/ghana_air_temperature/02_raw_grid_2023-08.csv` |
| "What exactly did you request?" | `.../01_the_request.txt` — the full URL |
| "Prove the average is honest" | `.../05_how_the_number_is_made.md` |
| "Check it independently" | `python data_verification/verify.py` |
| "Where's the provenance?" | `data_verification/MANIFEST.json` |
| "What are the limits?" | `data_verification/README.md` |

The single strongest demo move: show the **112 raw Kelvin cells** and the
**weighted average that matches the app to four decimal places**, then show that
the **plain unweighted average differs by only 0.019 °C**. The method isn't
hiding anything.
