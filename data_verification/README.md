# Is the data real? — verification bundle

**Short answer: no, nothing is fudged.** Everything in the Events tab is computed
from files NASA serves, and this folder contains the receipts — the raw files,
the exact URLs they came from, and a script that re-derives the numbers without
using any TerraTrend code.

Run this first:

```
python data_verification/verify.py
```

It opens the three `.nc4` files in `raw/`, reads the units NASA declared inside
the file, converts them, and prints `MATCHES MANIFEST: yes` for each.

---

## What is actually inside this folder

| File | What it is |
|---|---|
| `raw/*.nc4` | Unmodified NetCDF bytes returned by NASA's OPeNDAP service. Open them in Panoply, xarray or netCDF4. |
| `MANIFEST.json` | For each raw file: collection, field, published granule ID, the full OPeNDAP URL, the exact grid window, and both the source-unit and app-unit value. |
| `*_monthly.csv` | The full monthly series the Events tab computes from, so you can chart it in Excel. Empty cells are months that failed the 80% area-coverage rule — they are *not* zero. |
| `verify.py` | Independent re-decode. Imports nothing from TerraTrend. |

Three worked examples at a single native grid cell, August 2023:

| Measurement | NASA units in file | In app units |
|---|---|---|
| Niño 3.4 surface temperature | 300.8430 K | **27.693 °C** |
| Ghana precipitation | 0.000058 kg m⁻² s⁻¹ | **4.989 mm/day** |
| Amazon precipitation | 0.000025 kg m⁻² s⁻¹ | **2.191 mm/day** |

Those are the real numbers for a single ~62 × 55 km cell. The regional series in
the CSVs are area-weighted means over many such cells.

---

## Flow of operation

### A. Native MERRA-2 — this is what the Events tab uses

1. **Granule discovery.** `GET https://cmr.earthdata.nasa.gov/search/granules.json`
   with the collection concept ID and the requested date range. Public, no login.
   CMR returns the real published monthly granules — IDs, revision timestamps and
   OPeNDAP links. File names are never constructed locally. (`nasa_data.granules`)
2. **Geometry → native cells.** The selected boundary is mapped to the cells of
   MERRA-2's grid (0.625° longitude × 0.5° latitude) that actually intersect it.
3. **Subset request.** For each month, a DAP4 constraint is sent to
   `https://opendap.earthdata.nasa.gov/...:<granule>.dap.nc4`, asking only for the
   requested field plus its `lat`/`lon` axes, at the needed window — not the
   global file. Authenticated with the Earthdata bearer token.
4. **Decode and validate.** `netCDF4` reads the response. The code checks the
   axes match the native grid, rejects fill/mask values, and refuses to convert
   unless the units string in the file matches the verified mapping. (`decode_subset`)
5. **Aggregate.** Cells are weighted by polygon overlap × cos(latitude). A month
   is only used if at least **80% of the selected area** reported.
6. **Cache.** Raw bytes are stored under `backend/cache/nasa/subsets/<sha256>.nc4`.
   Provenance (granule IDs, retrieval time, coverage) travels with the result.
7. **Statistics.** Remaining analysis is in `backend/interconnect.py`: trend and
   seasonal cycle removed jointly, lagged cross-correlation, p-values corrected
   for effective sample size and for the lag-search family, then Benjamini–Hochberg
   across all pathways tested.

### B. Giovanni — a *different, optional* provider, not used by the Events tab

Giovanni does not power the event pathways. It is a separate mode for rectangles:

- `https://harmony.earthdata.nasa.gov` (NASA Harmony), product **M2IMNXASM**,
  asking for an area-averaged monthly CSV rather than grid cells.
- Supports only T2M, QV2M, T10M, QV10M.
- It is a different MERRA-2 product from native mode and is never substituted
  for it.

So there is no scraping of a web page anywhere: both routes are documented
machine APIs. Nothing is parsed out of HTML.

---

## Where the honest caveats are

These are real limitations, and the app states each one in the interface:

- **MERRA-2 is a reanalysis, not a pure satellite measurement.** It is a
  numerical model of the atmosphere constrained by assimilated observations. It
  is a standard scientific product from NASA GES DISC, but "NASA observed this
  exact temperature at this spot" would be an overstatement. The interface says
  "computed from NASA observations", which is the fair description.
- **The sea-surface temperature is a proxy.** The events use MERRA-2 surface skin
  temperature (`TS`), not the NOAA ERSSTv5 reconstruction. The app labels it as a
  proxy and says so in the panel. It tracks El Niño closely, but it is a
  different quantity from ERSSTv5.
- **The grid is coarse.** 0.625° × 0.5° is roughly 62 × 55 km at the equator. A
  sharp administrative boundary does not create finer data.
- **Correlation is not causation.** The pathways report association and timing
  with false-discovery control. They do not prove mechanism or predict the future.
- **The 1982–83 Ghana card is thin.** MERRA-2 begins in 1980, so that event has at
  most three years of preceding record, and the usual 1981–2010 baseline contains
  the drought itself. The panel says this.
- **Arctic sea ice is not implemented.** No proxy is substituted; the pathway
  stays marked `awaiting_source`.
- **Values are not byte-reproducible.** Re-downloading the same granule gives the
  same numbers but not an identical file (the service embeds a creation
  timestamp). That is why each export records its own hash prefix.

---

## Reproducing any number yourself

1. Open `MANIFEST.json`, take the `opendap_url` for a month.
2. Paste it into a browser where you are signed into Earthdata, or use `curl`
   with your bearer token.
3. You receive a small `.nc4`. Open it in Panoply or:
   `python -c "from netCDF4 import Dataset; d=Dataset('file.nc4'); print(d.variables)"`
4. Read the value, apply the conversion listed in the manifest, and compare.

If it disagrees with what the app shows, that is a bug worth reporting — please
do, because this bundle exists precisely so it can be checked.
