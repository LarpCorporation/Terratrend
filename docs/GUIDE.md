# TerraTrend — Judge Preparation Guide

**Everything in the app, explained from scratch — plus the questions you will be asked and how to answer them.**

Read this once end-to-end (~15 min). Then memorise section 6 (numbers) and section 7 (Q&A).

---

## 1. The 30-second pitch

> A measured Earth science variable can trend one way in one region and the opposite
> way in another, even when the same process drives both. With thousands of available
> variables, nobody can easily tell *which* variables are changing, *where*, by *how
> much*, or whether it is *statistically real*.
>
> TerraTrend is a tool that lets you pick a variable, tap anywhere on a 3D Earth, and
> instantly get four answers: **what** is changing, **where**, **by how much**, and
> **is it significant** — computed live from NASA's own open data using the two
> standard methods of climate trend analysis: **Theil–Sen** for magnitude and
> **Mann–Kendall** for significance.

If you only remember one sentence: **"We turn raw NASA Earth data into a statistically
tested trend, and we say 'not significant' when the evidence does not support a claim."**

---

## 2. How the app actually works — end to end

```
   ┌─────────────────┐
   │  NASA POWER API │   monthly data, one point at a time
   │  (MERRA-2 /     │
   │   GPCP / CERES) │
   └────────┬────────┘
            │  25 points per region (5×5 grid)
            ▼
   ┌─────────────────┐
   │  Disk cache     │   30-day TTL, so repeat analysis is instant
   └────────┬────────┘
            │
            ▼
   ┌─────────────────┐
   │  Aggregate      │   monthly  →  annual means
   │  to annual      │   (removes the seasonal cycle — see §4.3)
   └────────┬────────┘
            │
            ▼
   ┌──────────────────────────────┐
   │  Per grid cell:              │
   │    Theil–Sen  → slope        │
   │    Mann–Kendall → p-value    │
   │    Hirsch–Slack → cross-check│
   └────────┬─────────────────────┘
            │
            ▼
   ┌─────────────────┐
   │  Leaflet/three  │   globe cells coloured by direction+significance
   │  .js + Chart.js │   time series, dial, readouts
   └─────────────────┘
```

**In one sentence per stage:**

1. **Fetch** — NASA POWER serves monthly climate data for any lat/lon on Earth.
2. **Cache** — we save every response to disk so demos never stall.
3. **Aggregate** — we collapse 12 months into one annual mean per year.
4. **Test** — per grid cell, compute a slope (Theil–Sen) and a p-value (Mann–Kendall).
5. **Render** — colour each cell by direction and significance; plot the series.

**Why a 5×5 grid?** One region-wide average hides internal disagreement. Testing 25
cells lets the tool say "most of this region is rising, but these two corners are not" —
which is literally the challenge's core insight.

---

## 3. The data — what it is and where it comes from

| Term | What it means | Why it matters |
|---|---|---|
| **NASA POWER** | "Prediction Of Worldwide Energy Resources" — a NASA Langley service that serves climate data for any point as a simple API | Our single data source; no login, no API key |
| **MERRA-2** | NASA's reanalysis: a physics model that ingests millions of satellite/ground observations to produce a complete, gap-free global record from 1980 to present | Source of temperature, humidity, wind, pressure |
| **Reanalysis** | Not raw measurements — a *model output constrained by observations*. Best available continuous global record | Explains why some values differ slightly from a local weather station |
| **GPCP** | Global Precipitation Climatology Project — merged satellite + rain-gauge precipitation | Source of our precipitation variable |
| **CERES** | Clouds and the Earth's Radiant Energy System — satellite-measured radiation budget | Source of solar/longwave flux variables |
| **Grid resolution** | MERRA-2 is ~0.5° × 0.625° (roughly 50–60 km) | A "cell" is a ~55 km box, not a point measurement |

### The variables, with correct units

| ID | Name | Unit | Note |
|---|---|---|---|
| `T2M` | Air temperature at 2 m | °C | monthly mean |
| `T2M_MAX` / `T2M_MIN` | Max / min temperature | °C | mean of daily extremes |
| `PRECTOTCORR` | Precipitation | **mm/day** | *average daily rate for the month* |
| `RH2M` | Relative humidity | % | |
| `WS2M` | Wind speed at 2 m | m/s | |
| `ALLSKY_SFC_SW_DNI` | Direct normal irradiance | kWh/m²/day | |
| `ALLSKY_SFC_LW_DWN` | Downwelling longwave | **W/m²** | thermal infrared |
| `QV2M` | Specific humidity | g/kg | |
| `PS` | Surface pressure | kPa | |

> **Careful with precipitation units.** A value of `1.5` means **1.5 mm per day**,
> which is about **45 mm per month** or **550 mm per year**. If someone asks
> "mm per month?", the answer is: *no — it is a daily rate averaged over the month;
> multiply by ~30 to get a monthly total.*

---

## 4. The statistics — every piece of jargon, explained properly

This is the section judges will probe. Read it twice.

### 4.1 What is a "trend"?

A trend is a **consistent direction of change over time**. Not "it went up" — that is
one year. A trend means: *over many years, values tend to be higher later than earlier.*

Two separate things must be measured:

1. **How steep is it?** → magnitude → **Theil–Sen slope**
2. **Could this be luck?** → confidence → **Mann–Kendall p-value**

A good tool reports both. A tool that reports only one is incomplete.

---

### 4.2 Theil–Sen slope — "how much per decade"

**What it does:** takes every possible pair of years, computes the slope between them,
and takes the **median** of all those slopes.

With 20 years there are 190 pairs, so 190 candidate slopes; we report the middle one.

**Why median instead of a normal trendline (least squares)?**

Least squares is pulled around by outliers. A single anomalous year (a volcanic
eruption, a freak heatwave) can swing the line. The **median is robust** — half the
pairwise slopes can be nonsense and the median barely moves.

Concretely: if one year is 5 °C too warm, least squares tilts noticeably;
Theil–Sen barely notices.

**Reported as "per decade"** because climate science speaks in decades. Our data is
annual, so:

```
per-decade slope  =  per-year slope × 10
```

Example: Europe air temperature, 2005–2024 → **+0.99 °C per decade**.
(A typical global land warming rate is ~0.2–0.3 °C/decade, so this region is warming
faster than the global average — consistent with published European assessments.)

**Say this if asked "why not a simple linear regression?"**
> "Least squares is sensitive to outliers and assumes normally distributed residuals.
> Theil–Sen is the standard non-parametric alternative used alongside Mann–Kendall in
> climate literature. It has a high breakdown point — it tolerates up to ~29% of the
> data being outliers before the estimate fails."

---

### 4.3 Annual aggregation — the subtle trap most teams miss

**The problem:** our raw data is *monthly*. A monthly series looks like a sawtooth —
warm summers, cold winters, warm summers, cold winters. The seasonal swing
(±10 °C in Europe) is **huge compared with the trend** (~0.1 °C/year).

If you feed that sawtooth to a trend test, the up-and-down of the seasons dominates
and the trend is buried. During development, testing raw monthly data made **Arctic
warming come out as p = 0.52 — "no trend"** — which is obviously wrong.

**The fix:** collapse each year's 12 months into **one annual mean**, then test the
20 annual values. The seasonal cycle averages out; the long-term signal remains.

**The cost:** sample size drops from 240 to 20, which makes the test *more
conservative*. We accept that: a correct answer with less power beats a confident
wrong answer.

**And we add a cross-check:** the **Hirsch–Slack seasonal Mann–Kendall** test, which
works directly on the monthly data but compares Januaries to Januaries, Februaries to
Februaries, and then combines the evidence. If both methods agree (they do), the
result is solid.

> **This is a genuinely good thing to bring up unprompted.** It shows you understand
> *why* the naive approach fails, not just that you used a fancy-sounding test.

---

### 4.4 The Mann–Kendall test — "is it real?"

A **non-parametric** test for a monotonic trend. "Non-parametric" = it does not assume
your data follows a bell curve.

**How it works, step by step:**

1. Look at **every pair** of years (i, j) where j comes after i.
2. For each pair, ask: is the later value higher (+1), lower (−1), or equal (0)?
3. **Add them all up.** That sum is called **S**.
   - If values generally rise over time → most pairs are +1 → **S is large and positive**.
   - If they fall → **S is large and negative**.
   - If there is no pattern → +1s and −1s cancel → **S is near zero**.
4. Convert S into a **Z score** (how many standard deviations away from zero S is).
5. Convert Z into a **p-value**.

**Kendall's tau (τ)** is just S normalised to a −1…+1 scale:
`τ = S / (½·n·(n−1))`.

- τ = +1 → perfectly monotonic increase
- τ = 0 → no monotonic relationship
- τ = −1 → perfectly monotonic decrease

We display τ implicitly through the significance arc. Example: Europe τ = +0.48 —
a moderately strong, consistent upward ordering.

> **Why this test and not a t-test?**
> "Climate variables are rarely normally distributed and contain outliers. Mann–Kendall
> is rank-based, so it makes no distributional assumption and is resistant to extreme
> years. It is the World Meteorological Organization's recommended trend test."

---

### 4.5 The p-value — the single most misunderstood number in science

#### The correct definition

> **The p-value is the probability of seeing data at least as extreme as what we
> observed, IF there were actually no trend at all.**

In our case: *"If this region's climate were genuinely not changing, what is the chance
we would measure a trend this strong purely from natural year-to-year wobble?"*

- **p = 0.003** → a 0.3% chance. Very unlikely to be noise → **we call it significant.**
- **p = 0.673** → a 67% chance. Completely ordinary → **we say "no significant trend".**

#### Three things a p-value is NOT (judges love testing this)

| ❌ Wrong | ✅ Right |
|---|---|
| "p = 0.05 means there is a 5% chance the trend is fake." | It means: *if there were no trend*, we'd see this pattern 5% of the time. It says nothing directly about whether *this* trend is fake. |
| "p = 0.05 means there's a 95% chance our result is correct." | It is not the probability that our hypothesis is true. That would require Bayesian reasoning and a prior. |
| "p = 0.05 means 5% of the effect is due to chance." | p is not a proportion of the effect — it is a probability about the *data-generating process*. |

**The clean way to say it out loud:**
> "The p-value answers one question: if nothing were happening, how surprising would
> this data be? It is a measure of *surprise under the null hypothesis*, not a measure
> of how large or how important the change is."

#### Alpha (α = 0.05) and the stars

- **α (alpha)** is the **threshold we choose in advance**. Ours is **0.05** — the
  conventional line in climate and environmental science.
- If **p < α** → "statistically significant" → we reject the null hypothesis of no trend.
- Stars are a shorthand: `*` p<0.1, `**` p<0.05, `***` p<0.01.

**Important nuance:** a result with p = 0.06 is *not* "no trend" — it is
"not enough evidence at this threshold." Weak evidence, not zero evidence. Our
Arctic Siberia result (p = 0.163) is exactly this case.

---

### 4.6 Statistical significance ≠ importance

A trend can be **statistically significant but practically trivial**: over 200 data
points, a change of 0.001 units can produce p < 0.001.

This is why we always display **both**: the p-value *and* the slope. If you are asked
"is the change big?", the p-value is the wrong number — the **slope** is the answer.

**Say this if asked:** "We never report significance alone. Every result carries the
magnitude in physical units per decade, so the user can judge whether it matters."

---

### 4.7 Grid cells and the multiple-comparisons problem

We test **25 cells independently**. Each test uses α = 0.05.

If a region had *no real trend anywhere*, we would still expect
`25 × 0.05 = 1.25` cells to come out "significant" **by pure chance**.

This gives a powerful way to read the results:

| Cells significant | Interpretation |
|---|---|
| **0–2 of 25** | Consistent with random noise. Do not claim a regional signal. |
| **5+ of 25** | Beyond what chance would produce — a real spatial signal |
| **13 of 25** (Sahel) | Strong, coherent regional signal |
| **25 of 25** (Europe) | Overwhelming — the entire region is moving together |

**This is a great point to volunteer**, because it turns a potential criticism
("you tested 25 things, of course some came out significant") into evidence of rigour.

> **Honest caveat to mention if pressed:** the cells are not truly independent —
> neighbouring points share the same weather systems, so 1.25 is an estimate of
> independent noise. The formal fix is a false-discovery-rate (FDR) correction such as
> Benjamini–Hochberg. We have not implemented that; we mitigate by reading the
> *spatial pattern*, not the raw count.

---

### 4.8 Two known statistical limitations (know these — judges may raise them)

**1. Autocorrelation inflates false positives.**
Annual values are not fully independent — a hot year tends to be followed by another
warm year (El Niño, ocean memory). Mann–Kendall assumes independence, so
**positively autocorrelated data can produce too many "significant" results.**
The standard remedy is **pre-whitening** (Yue–Wang) or a variance correction.

**2. Short windows are noisy.**
A 20-year window is short for climate. Choosing 2005–2024 versus 1985–2024 changes the
headline number — and that is not a bug, it is a real property of trend estimation.
We turn this into a feature: the tool exposes the window so users can see the
sensitivity themselves (§6 shows Europe across windows).

**How to frame both:** "We know the assumptions, we know where they bite, and here is
what we would add next." Never pretend the method is perfect.

---

## 5. The interface — what every panel means

| Panel | What it shows | How to describe it |
|---|---|---|
| **01 Variables** | 10 NASA variables, pick up to 3 | "Multiple variables can be overlaid, each with its own colour identity" |
| **02 Region** | 16 focus regions worldwide | "Tapping the globe auto-selects the nearest region" |
| **03 Period** | Start/end year (min 9 years) | "Short windows are noisier — we let you see that" |
| **REGIONAL SIGNAL dial** | The active variable's per-decade slope, arc = trend strength | "The number is the physical rate; the arc is how coherent the trend is" |
| **VARIABLE SIGNALS** | One row per selected variable: slope + p | "Click a row to make that variable the active globe layer" |
| **TREND SERIES** | Annual or monthly series + dashed Theil–Sen line | "The dashed line is the robust fitted trend" |
| **GRID CELLS** | Count of rising / falling / no-trend cells | "This is the multiple-comparison read-out" |
| **LITERATURE CHECK** | Real papers from OpenAlex matching variable + region | "The tool checks itself against the published record" |
| **Globe cells** | Orange = significant rise, blue = significant fall, grey = none | Cell size scales with slope magnitude |
| **White ring** | Bounds the analysed region | |

**On the globe's appearance:** the 25-cell mesh is **visually amplified ~2.8×** so
individual cells are readable at planetary scale. Real coordinates appear in every
tooltip and in the bottom coordinate bar. Say so before a judge spots it — honesty
about a deliberate visual choice reads as confidence.

---

## 6. The numbers cheat sheet (all pre-warmed, demo instantly)

| Region | Variable | Period | Slope / decade | p | Significant cells |
|---|---|---|---|---|---|
| **Central Europe** | Air temp | 2005–2024 | **+0.99 °C** | **0.003** | **25 / 25** |
| Central Europe | Precipitation | 2005–2024 | +0.066 mm/day | 0.673 | 0 / 25 ❌ |
| **Sahel Central** | Precipitation | 2005–2024 | **+0.207 mm/day** | **0.009** | **13 / 25** |
| **Madagascar South** | Air temp | 2005–2024 | **+0.351 °C** | **0.013** | 9 / 25 |
| Arabian Peninsula | Air temp | 2005–2024 | — | **0.001** | high |
| East China | Air temp | 2005–2024 | — | **0.001** | high |
| Brazil Cerrado | Air temp | 2005–2024 | — | **0.001** | high |
| Amazon East | Air temp | 2005–2024 | — | **0.025** | — |
| California | Air temp | 2005–2024 | — | **0.048** | — |
| **Arctic Siberia** | Air temp | 2005–2024 | +0.63 °C | **0.163** | 0 / 25 ❌ |

### The window-sensitivity demonstration (impressive if asked "why this period?")

Central Europe air temperature, same region, different windows:

| Window | Slope / decade | p |
|---|---|---|
| 1985–2024 (40 yr) | **+0.58 °C** | < 0.0001 |
| 1995–2024 (30 yr) | **+0.69 °C** | 0.0001 |
| 2005–2024 (20 yr) | **+0.99 °C** | 0.003 |
| 2010–2024 (15 yr) | **+1.44 °C** | 0.006 |

The trend is significant in **every** window and the rate **increases** as the window
shortens — i.e. warming has **accelerated**. Longer windows give more conservative
(and more trustworthy) magnitudes; shorter windows react faster to acceleration.

> If asked "which number is *the* answer?", the honest response: "There is no single
> answer — a trend is a property of a chosen window. The 40-year estimate of
> +0.58 °C/decade is our most conservative, and it agrees with published European
> assessments."

---

## 7. Judge Q&A bank

Practice saying these out loud. Keep each answer to 20–30 seconds.

### On the science

**Q: What does p < 0.05 actually mean?**
> "It means: if there were genuinely no trend, we would see a pattern this strong or
> stronger less than 5% of the time. It is a measure of surprise under the
> no-trend hypothesis — not the probability that our trend is real."

**Q: Why Mann–Kendall instead of linear regression?**
> "Climate data isn't normally distributed and contains outliers like volcanic years.
> Mann–Kendall is rank-based and assumption-light; it's the WMO-recommended trend test.
> Theil–Sen is its natural companion for slope because the median of pairwise slopes is
> robust to outliers."

**Q: Why is Arctic Siberia not significant — isn't the Arctic warming fastest?**
> "It is, globally — but this is a small 6°×4° box and a 20-year window with very large
> year-to-year variability. The slope is positive (+0.63 °C/decade) but the noise is too
> big for the evidence to clear the 0.05 bar. That's the tool working correctly: it
> refuses to overclaim. A longer window or a larger box would likely clear it."

**Q: What is the difference between statistical and practical significance?**
> "Statistical significance asks 'could this be noise?'. Practical significance asks
> 'does it matter?'. A tiny change measured precisely can be statistically significant
> and physically irrelevant. That's why we always show the slope in physical units
> alongside the p-value."

**Q: Is your data raw measurements?**
> "No — it's NASA reanalysis: a physics model constrained by millions of observations.
> That's the best available gap-free global record, and it's what climate services use,
> but it is modelled, not a direct thermometer reading. We're explicit about that."

**Q: What about seasonality?**
> "That was our biggest technical trap. Testing raw monthly data lets the seasonal cycle
> swamp the trend — it made Arctic warming come out p = 0.52. We aggregate to annual
> means and cross-check with a seasonal Mann–Kendall that compares Januaries to
> Januaries."

**Q: How do you handle missing data?**
> "POWER's fill value is −999. We drop those points, and a cell needs at least 8 valid
> annual values before we will report a trend — otherwise it's marked insufficient data."

**Q: Twenty-five tests per region — aren't some significant by chance?**
> "At α = 0.05 you'd expect about 1.25 false positives out of 25 by chance alone. That's
> exactly why we report the *spatial pattern*, not just a count: 13/25 in the Sahel and
> 25/25 in Europe are far beyond chance, whereas 1/25 would be indistinguishable from
> noise. Formal FDR correction is on our roadmap."

**Q: What is autocorrelation and does it affect you?**
> "Year-to-year values aren't independent — warm years cluster. Mann–Kendall assumes
> independence, so strong autocorrelation can inflate false positives. The standard fix
> is pre-whitening, which we haven't implemented yet; we flag it as a known limitation."

### On the engineering

**Q: Where does the data come from and how fresh is it?**
> "NASA POWER's monthly point API — MERRA-2, GPCP and CERES. Data runs from 1981 to
> 2024. We cache every response for 30 days on disk, so a warm region returns in about
> a tenth of a second."

**Q: How long does an analysis take?**
> "A cold region fetches 25 grid points in parallel with retry and jitter to stay inside
> POWER's rate limits — about 3–5 seconds. Cached, it's effectively instant. We ship a
> warm-cache script and pre-warm 18 demo regions before judging."

**Q: Why no fancy frameworks?**
> "Deliberate. The backend is pure Python standard library — zero install, zero
> dependency risk on demo day. The frontend pulls three.js and Chart.js from CDN and
> ships its own globe geometry, so there are only two external requests."

**Q: How is the globe drawn?**
> "6,550 land points generated offline from Natural Earth's public-domain land polygons
> at 1.4° sampling, rendered as a three.js point cloud. Not a texture — a real point
> cloud, which is why it stays crisp at any zoom."

**Q: Is it responsive / accessible?**
> "It's a desktop cockpit layout by design — three columns, dense instrument readouts.
> Below 1240 px it collapses to a single column. The semantic structure is there, but
> keyboard access to the globe is the next accessibility task."

### On impact and product

**Q: Who is this for?**
> "Three audiences: scientists triaging which variables are worth investigating; policy
> analysts who need to know if a regional signal is real; and educators/journalists who
> need a defensible number rather than a chart."

**Q: What makes this different from just plotting data in a notebook?**
> "Three things. First, it selects and tests automatically instead of requiring the user
> to know which variables to look at. Second, it tests every grid cell rather than the
> regional average, so it exposes opposing local trends. Third, it pairs each result
> with a live literature check from OpenAlex."

**Q: What is the biggest limitation?**
> "Spatial resolution. We sample 25 points per region, so our 'map' is a coarse mesh,
> not pixels. The real upgrade is pulling true raster subsets via NASA Harmony or
> GES DISC netCDF, which would give thousands of cells."

**Q: What would you do with another month?**
> "Three things in priority order: true raster data via Harmony; freehand region
> selection instead of 16 presets; and pre-whitening plus FDR correction to harden the
> statistics. Then a Pettitt change-point test to answer 'when did it start?'."

---

## 8. The 3-minute demo script

**0:00 — Frame it (the hook).**
"This is a 3D Earth. Every dot is real land. I can pick up to three variables, tap
anywhere on the planet, and in a few seconds the tool tells me what's changing there
and whether it's real."

**0:20 — The strong case (Europe).**
*Select Central Europe + Air Temperature + Precipitation.*
"Twenty-five of twenty-five grid cells are significantly warming, at about one degree
per decade, p = 0.003. But look at precipitation over the exact same box and period —
p = 0.67, no significant trend. Same place, same window, completely different answers.
That's why you can't just ask 'is this region changing?' — you have to ask *which
variable*."

**0:50 — The famous case (Sahel).**
*Tap Africa near the Sahel.*
"The Sahel had catastrophic droughts in the 70s and 80s. The data shows a significant
recovery: plus 0.2 millimetres per day per decade, p = 0.009, thirteen of twenty-five
cells rising. That matches the published literature — which the tool surfaces
automatically."

**1:20 — The honest case (Arctic).**
*Tap Arctic Siberia.*
"p = 0.163. Not significant. The slope is positive but the evidence isn't strong enough.
We could have hidden this region. We show it, because a tool that only ever says
'significant' is not a tool, it's a marketing slide."

**1:50 — The engineering.**
"Under the hood: NASA POWER data, cached to disk; Theil–Sen for the slope because it's
robust to outliers; Mann–Kendall for significance because climate data isn't normal.
And critically — we test annual means, not raw monthly data, because the seasonal cycle
otherwise swamps the trend. That bug made Arctic warming look flat during development."

**2:30 — Close.**
"One tap, five seconds, four answers: what's changing, where, how much, and whether it's
real. That's the whole challenge prompt, delivered."

---

## 9. Glossary — one line each

| Term | One-line definition |
|---|---|
| **Anomaly** | A value expressed relative to a long-term average |
| **α (alpha)** | The significance threshold chosen before testing; ours is 0.05 |
| **Autocorrelation** | Year-to-year values not being independent |
| **Biased / bias** | A systematic error that pushes results consistently one way |
| **CERES** | NASA satellite experiment measuring Earth's radiation budget |
| **Confidence interval** | A range likely to contain the true value |
| **False positive (Type I)** | Declaring a trend that isn't there |
| **False negative (Type II)** | Missing a trend that is there |
| **GPCP** | Global Precipitation Climatology Project (merged precipitation dataset) |
| **Hirsch–Slack** | The seasonal version of Mann–Kendall; compares like months to like months |
| **Kendall's τ** | Rank correlation from −1 to +1; the effect size of Mann–Kendall |
| **MERRA-2** | NASA's modern reanalysis dataset (1980–present) |
| **Monotonic trend** | Consistently increasing (or decreasing) — not necessarily linear |
| **Multiple comparisons** | Testing many cells inflates the chance of false positives |
| **Non-parametric** | Makes no assumption that data follows a normal distribution |
| **Null hypothesis (H₀)** | The default claim: "there is no trend" |
| **p-value** | Probability of data this extreme *if H₀ were true* |
| **Per decade** | Slope × 10; the conventional climate rate unit |
| **Power** | Probability of detecting a trend that genuinely exists |
| **Pre-whitening** | Removing autocorrelation before testing |
| **Reanalysis** | Model output constrained by observations; a gap-free historical record |
| **Robust estimator** | An estimator not thrown off by outliers |
| **Seasonality** | The repeating annual cycle |
| **Statistical significance** | Unlikely to be explained by chance at the chosen α |
| **Theil–Sen** | Median of all pairwise slopes; a robust trend estimator |
| **Trend** | A consistent direction of change across many years |
| **Type I / Type II error** | False alarm / missed detection |
| **Z score** | Distance from the mean in standard deviations; MK's test statistic |
| **−999** | NASA POWER's "missing data" fill value |

---

## 10. If you remember only five things

1. **p-value = surprise under the null.** Not "probability we're right."
2. **We report both slope and significance** — magnitude and confidence are different questions.
3. **We test annual means, not monthly**, because the seasonal cycle otherwise destroys the test.
4. **We say "not significant" when the evidence is thin** — that's the tool's credibility.
5. **25 cells vs 1.25 expected false positives** — the spatial pattern is the evidence, not a single p-value.
