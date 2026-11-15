# How 112 raw numbers become one reading

Two operations separate the raw file from the number the app shows: **convert**
and **average**. Nothing else happens. There is no fitting, no smoothing, no gap
filling, and no adjustment of any kind for a single monthly reading.

## Step 1 — Convert Kelvin to Celsius

A constant offset. Every cell, same subtraction.

```
297.7584 K  - 273.15  =  24.6084 °C     coldest cell in Ghana
299.6202 K  - 273.15  =  26.4702 °C     warmest cell in Ghana
```

Because the offset is constant, it makes no difference whether you convert first
and then average, or average first and then convert. Both give 25.5491 °C for
the plain mean. There is nowhere for a number to be nudged.

## Step 2 — Give each cell an area weight

Each cell's weight is how much **ground** it represents inside Ghana:

```
weight = (overlap area in square degrees) x cos(latitude)
```

Worked example — the cell at longitude −3.125, latitude 5.000:

```
that cell spans   lon −3.4375 .. −2.8125   lat 4.750 .. 5.250
Ghana box spans   lon −3.300  ..  1.200    lat 4.700 .. 11.200

longitude overlap = 0.4875 of its 0.625 width  (Ghana stops at −3.300)
latitude  overlap = full

weight = 0.4875 x 0.5 x cos(5.0°)
       = 0.4875 x 0.5 x 0.996195
       = 0.242822          <- this is the number in ghana_cell_weights.csv
```

Two reasons the weighting exists:

- **Overlap.** A border cell mostly outside Ghana must not count as much as a
  cell wholly inside it. Cell (−3.125, 4.500) is only 8% inside the country, so
  it carries weight 0.0243 rather than 0.3125.
- **cos(latitude).** A degree of longitude is about 111 km at the equator but
  shrinks towards the poles. Multiplying by cos(latitude) makes the weight a real
  area rather than a count of degrees.

The weights are genuine areas, which is why they sum to Ghana's area rather than
to 112:

```
sum of weights = 28.953     (square degrees x cos lat)
Ghana box 4.5° x 6.5° = 29.25 deg², x cos ≈ 28.96
```

## Step 3 — Weighted mean

```
mean = Σ(value x weight) / Σ(weight)
     = 8648.8807 / 28.953343
     = 298.7179 K
     = 25.5679 °C
```

That is the whole calculation. It is three lines of arithmetic.

## The cross-checks that make fudging hard

| Check | Result |
|---|---|
| Plain unweighted mean of all 112 cells | **25.5491 °C** |
| Area-weighted mean (what the app uses) | **25.5679 °C** |
| Difference | **0.019 °C** |

The sophisticated weighting agrees with the naive average to within two
hundredths of a degree. If someone were massaging the numbers, the weighted and
unweighted answers would not sit on top of each other like this.

| Check | Result |
|---|---|
| Convert each cell, then average | 25.5491 °C |
| Average in Kelvin, then convert | 25.5491 °C |

Identical, because the offset is constant.

## What the single number hides

The average is 25.57 °C, but Ghana was not uniformly 25.57 °C that month:

| Part of the country | Mean |
|---|---|
| South (latitude ≤ 7°, coast and forest belt) | 25.19 °C |
| North (latitude ≥ 9°, savanna) | 25.98 °C |

Range across all cells: **24.61 °C to 26.47 °C** — a spread of 1.86 °C. The
warmest cells are in the far north around latitude 9.5–11°, the coolest in the
middle belt during the rains. Collapsing to one number is a deliberate choice
for trend plotting; it is not a claim that Ghana has one temperature.

## What "accurate" honestly means here

- It is an accurate **area-weighted average of the MERRA-2 field** over Ghana
  for that month. That statement is true.
- It is **not** a thermometer reading for every point in Ghana. MERRA-2 is a
  reanalysis: a model of the atmosphere constrained by assimilated observations.
- The cell is **0.625° × 0.5°**, roughly 69 × 55 km in Ghana. The data cannot
  resolve district-level differences, and a sharper boundary on the map does not
  create sharper data.
- A month enters the record only if **at least 80% of Ghana reported**. For
  August 2023 all 112 cells were present, so no coverage rule was applied.

## Where the trend mathematics begins — after this, not before

The 25.57 °C figure is a single monthly value. The trend analysis operates on the
**twelve monthly values per year, over many years**:

1. Twelve monthly area-averages, computed exactly as above, one per published
   month (and therefore twelve separate NASA requests).
2. A year is complete only if all twelve months cleared the 80% coverage rule.
3. Complete annual means are fitted with **Theil–Sen** (the median of slopes
   between all pairs of years), and tested with **Mann–Kendall**. Both are
   resistant to outliers and make no assumption that the change is linear.
4. Confidence intervals come from the Kendall rank correlation; an OLS fit is
   reported alongside purely as a diagnostic.

So the pipeline never fits anything to the 112 raw cells. The cells are averaged
honestly, and the statistics happen years later on the annual series.
