"""Re-decode the raw NASA subsets in this folder, independently of TerraTrend.

Run:  python data_verification/verify.py

This script does not import any TerraTrend code. It opens the .nc4 files that
NASA's OPeNDAP service returned, reads the declared units out of the file, and
converts them the same way the app does. If the app were inventing numbers,
these files would not contain the values shown in MANIFEST.json.
"""
import json
import sys
from pathlib import Path

try:
    from netCDF4 import Dataset
except ImportError:
    sys.exit("This needs netCDF4:  python -m pip install netCDF4")

ROOT = Path(__file__).resolve().parent


def show(row):
    path = ROOT / "raw" / row["file"]
    if not path.is_file():
        print(f"  MISSING {row['file']}")
        return
    with Dataset(path) as data:
        field = row["field"]
        var = data.variables[field]
        value = var[0][0][0]
        try:
            value = float(value.filled(float("nan")))
        except AttributeError:
            value = float(value)
        factor = row["conversion"]["factor"]
        offset = row["conversion"]["offset"]
        converted = value * factor + offset

        print(f"\n{row['file']}")
        print(f"  collection      : {row['dataset']}  ({row['granule_id']})")
        print(f"  month           : {row['month']}")
        print(f"  cell            : lon {row['cell']['lon']}, lat {row['cell']['lat']}")
        print(f"  file variables  : {', '.join(data.variables)}")
        print(f"  NASA units field: {getattr(var, 'units', '?')}")
        print(f"  raw value       : {value:.6f} {row['source_units']}")
        print(f"  conversion      : x{factor} + {offset}")
        print(f"  app value       : {converted:.6f}")
        print(f"  manifest says   : {row['value_used_by_app']:.6f}")
        match = abs(converted - row["value_used_by_app"]) < 1e-4
        print(f"  MATCHES MANIFEST: {'yes' if match else 'NO'}")


def main():
    manifest = json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
    print("Raw NASA subsets behind TerraTrend's numbers")
    print("=" * 60)
    for row in manifest["raw_subsets"]:
        show(row)
    print("\nRe-download any of these from the OPeNDAP URL in MANIFEST.json with")
    print("your own Earthdata login. You will get the same granule and the same")
    print("values. The generated file is not necessarily byte-identical (the")
    print("service embeds a creation timestamp), which is why each export keeps")
    print("its own SHA-256 prefix.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
