# Raw data: air temperature in Ghana

This folder is one measurement, opened up completely, so you can read the data
before any averaging happens.

**Question it answers:** if I pick *air temperature* in *Ghana*, what does
TerraTrend actually receive?

## Read these in order

| File | What it is |
|---|---|
| `01_the_request.txt` | The exact request sent to NASA, with the full URL. This is the whole transaction — no hidden steps. |
| `02_raw_grid_2023-08.csv` | Every one of the **112 cells** NASA returned for August 2023, in **Kelvin**, exactly as stored in the file. Nothing averaged, nothing converted. |
| `ghana_cell_weights.csv` | How much of each of those cells lies inside Ghana (polygon overlap × cos latitude). |
| `04_aggregate.py` | Computes the weighted mean from the two files above. Imports only netCDF4 — no TerraTrend code. |
| `03_result.json` | The computed result, recorded. |
| `*.nc4` | The raw NASA response body, unmodified. Open it in Panoply or with netCDF4. |

Run the checker:

```
python data_verification/ghana_air_temperature/04_aggregate.py
```

## What it shows

```
raw file : M2TMNXSLV_T2M_202308_ghana_raw.nc4
units    : K
window   : 14 latitudes x 8 longitudes = 112 cells
lat range: 4.500 .. 11.000
lon range: -3.125 .. 1.250

sum of weights       : 28.953343
weighted mean        : 298.7179 K
converted            : 25.5679 degC
TerraTrend reports   : 25.5679 degC
AGREES               : yes
```

## The two steps, in plain terms

1. **Ask NASA for Ghana's window.** TerraTrend does not download the global
   MERRA-2 file. It asks the OPeNDAP service for rows 189–202 and columns
   283–290 of `T2M` only — 112 numbers, about 30 KB.
2. **Average with area weights.** Each cell contributes in proportion to how
   much of it falls inside Ghana, and cells near the equator count slightly
   more than cells near the poles because they cover more ground. That is the
   entire difference between the 112 raw numbers and the single figure the app
   shows.

Nothing else happens between those steps. There is no gap-filling, no smoothing,
no adjustment to make a trend look a particular way.

## What the app reports for 2023

| Month | °C |
|---|---|
| January | 25.47 |
| February | 27.80 |
| March | 28.54 |
| April | 28.33 |
| May | 28.01 |
| June | 26.31 |
| July | 25.94 |
| August | **25.57** |
| September | 25.98 |
| October | 26.49 |
| November | 26.90 |
| December | 25.37 |

These twelve figures come from twelve separate requests, one per published month.

## Caveats that apply to this data

- **T2M is a reanalysis field**, not a direct thermometer reading at each point.
  It is NASA's model of the atmosphere constrained by assimilated observations.
- **The cell is coarse** — 0.625° × 0.5°, roughly 69 × 55 km in Ghana.
- **A month is only used if at least 80% of Ghana reported.** For this month all
  112 of 112 cells were present, so no coverage rule was triggered.
