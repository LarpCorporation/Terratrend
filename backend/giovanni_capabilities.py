"""Read-only preflight for a possible Giovanni replacement, not a data adapter.

Run: .venv/bin/python backend/giovanni_capabilities.py
Only public metadata are requested. No token, geometry, scientific job or
observation download is involved. A positive capability match still requires
independent validation of boundaries, weights, missing data and statistics.
"""
import datetime as dt
import json
from urllib.parse import urlencode

import requests

import nasa_data


CATALOG_URL = "https://api.giovanni.earthdata.nasa.gov/configured-variables"


def capabilities_url(product):
    return "https://harmony.earthdata.nasa.gov/capabilities?" + urlencode({
        "collectionId": nasa_data.PRODUCTS[product], "version": 3})


def get_json(url):
    allowed = {CATALOG_URL, *(capabilities_url(p) for p in nasa_data.PRODUCTS)}
    if url not in allowed:
        raise ValueError("Unsupported public metadata endpoint")
    with requests.Session() as session:
        # Do not read unrelated .netrc credentials, even if present locally.
        session.auth = lambda request: request
        with session.get(url, headers={"Accept": "application/json", "User-Agent": "TerraTrend/1.0"},
                         timeout=(10, 25), stream=True, allow_redirects=False) as response:
            if response.status_code != 200:
                raise ValueError(f"NASA metadata service returned HTTP {response.status_code}")
            body = bytearray()
            for part in response.iter_content(64_000):
                body.extend(part)
                if len(body) > 1_000_000:
                    raise ValueError("NASA metadata response exceeds the size limit")
            return json.loads(body)


def assess(configured, capabilities):
    fields = configured.get("configured_variables") if isinstance(configured, dict) else None
    if not isinstance(fields, list) or not all(isinstance(v, str) for v in fields):
        raise ValueError("Invalid Giovanni configured-variable catalogue")
    if not isinstance(capabilities, dict):
        raise ValueError("Invalid collection capabilities")
    fields = set(fields)
    missing = [variable for variable, (product, field, *_) in nasa_data.FIELDS.items()
               if f"{product}_5_12_4_{field}" not in fields]
    rows = []
    for product, concept in nasa_data.PRODUCTS.items():
        cap = capabilities.get(product)
        if not isinstance(cap, dict) or cap.get("conceptId") != concept or cap.get("shortName") != product:
            raise ValueError("Collection capabilities do not match TerraTrend's source collection")
        services = cap.get("services")
        if not isinstance(services, list) or not all(isinstance(s, dict) for s in services):
            raise ValueError("Invalid collection service metadata")
        averaging = []
        for service in services:
            if "giovanni" not in str(service.get("name", "")).lower():
                continue
            properties = service.get("capabilities", {})
            subset = properties.get("subsetting", {})
            formats = [fmt.get("mimeType") if isinstance(fmt, dict) else fmt
                       for fmt in properties.get("outputFormats", [])]
            if (properties.get("averaging", {}).get("area") is True
                    and subset.get("temporal") is True and subset.get("variable") is True
                    and "text/csv" in formats):
                averaging.append(properties)
        # A different service's shape support cannot be borrowed by averaging.
        shape = any(p.get("subsetting", {}).get("shape") is True for p in averaging)
        rows.append({"product": product, "concept_id": concept,
                     "area_averaging": bool(averaging), "exact_shape_request": shape,
                     "metadata_url": capabilities_url(product)})
    ready = not missing and all(r["area_averaging"] and r["exact_shape_request"] for r in rows)
    return {"status": "validation_required" if ready else "unsupported",
            "replacement_verified": False, "ready_to_validate": ready,
            "configured_variable_count": len(fields), "missing_fields": missing, "collections": rows,
            "requirement": "Same monthly MERRA-2 5.12.4 fields and unsimplified selected polygons",
            "validation_remaining": ["Fractional boundary/latitude weighting and holes/islands",
                                     "Monthly valid-area coverage and complete-year handling",
                                     "Independent monthly values and trend-statistic comparison",
                                     "Native-cell evidence and spatial-analysis feature preservation"]}


def probe(fetch=None):
    fetch = fetch or get_json
    checked = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        configured = fetch(CATALOG_URL)
        capabilities = {product: fetch(capabilities_url(product)) for product in nasa_data.PRODUCTS}
        result = assess(configured, capabilities)
    except (ValueError, requests.RequestException):
        result = {"status": "unavailable", "replacement_verified": False, "ready_to_validate": False,
                  "reason": "Could not verify public NASA service metadata; no source switch is justified."}
    return {**result, "checked_utc": checked, "catalogue_url": CATALOG_URL,
            "observation_downloads": 0, "earthdata_credentials_used": False}


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2))
