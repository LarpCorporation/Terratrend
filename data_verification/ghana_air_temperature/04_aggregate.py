"""Prove the Ghana number from the raw file, with no TerraTrend code.

Run:  python data_verification/ghana_air_temperature/04_aggregate.py

It reads the raw NASA response, looks up each Ghana cell inside that file, and
computes the same weighted mean the app reports for August 2023. It imports
only netCDF4 and the standard library.
"""
import csv
import sys
from pathlib import Path

try:
    from netCDF4 import Dataset
except ImportError:
    sys.exit("This needs netCDF4:  python -m pip install netCDF4")

HERE = Path(__file__).resolve().parent
RAW = HERE / "M2TMNXSLV_T2M_202308_ghana_raw.nc4"
WEIGHTS = HERE / "ghana_cell_weights.csv"
EXPECTED_DEGC = 25.5679   # what TerraTrend reports for 2023-08


def main():
    with Dataset(RAW) as data:
        field = data.variables["T2M"]
        units = getattr(field, "units", "?")
        lats = [float(v) for v in data.variables["lat"][:]]
        lons = [float(v) for v in data.variables["lon"][:]]
        grid = field[0][:]

    print(f"raw file : {RAW.name}")
    print(f"units    : {units}")
    print(f"window   : {len(lats)} latitudes x {len(lons)} longitudes "
          f"= {len(lats) * len(lons)} cells")
    print(f"lat range: {min(lats):.3f} .. {max(lats):.3f}")
    print(f"lon range: {min(lons):.3f} .. {max(lons):.3f}")

    cells = []
    with open(WEIGHTS, encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row or row[0].startswith("#") or row[0] == "longitude":
                continue
            cells.append((float(row[0]), float(row[1]), float(row[2])))

    print(f"\nweights  : {len(cells)} cells inside Ghana")
    print("\n  longitude  latitude   raw K   weight    K x weight")
    total_weight = 0.0
    total = 0.0
    for lon, lat, weight in cells[:10]:
        iy = min(range(len(lats)), key=lambda i: abs(lats[i] - lat))
        ix = min(range(len(lons)), key=lambda i: abs(lons[i] - lon))
        kelvin = float(grid[iy, ix])
        total += kelvin * weight
        total_weight += weight
        print(f"  {lon:9.3f} {lat:9.3f} {kelvin:8.4f} {weight:8.6f} {kelvin * weight:12.6f}")
    for lon, lat, weight in cells[10:]:
        iy = min(range(len(lats)), key=lambda i: abs(lats[i] - lat))
        ix = min(range(len(lons)), key=lambda i: abs(lons[i] - lon))
        kelvin = float(grid[iy, ix])
        total += kelvin * weight
        total_weight += weight
    print("  ...")

    mean_k = total / total_weight
    mean_c = mean_k - 273.15
    print(f"\nsum of weights       : {total_weight:.6f}")
    print(f"weighted mean        : {mean_k:.4f} K")
    print(f"converted            : {mean_c:.4f} degC")
    print(f"TerraTrend reports   : {EXPECTED_DEGC:.4f} degC")
    ok = abs(mean_c - EXPECTED_DEGC) < 0.001
    print(f"AGREES               : {'yes' if ok else 'NO'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
