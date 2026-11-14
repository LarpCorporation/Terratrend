"""NASA GIBS (Global Imagery Browse Services) & Worldview integration.

Generates WMS request URLs for calibrated MODIS and VIIRS satellite imagery,
determines optimal cloud-minimized seasonal dates, and builds direct
NASA Worldview deep-links for any bounding box and time period.
"""
from urllib.parse import quote

# NASA GIBS WMS endpoint (EPSG:4326 / WGS84)
GIBS_WMS_BASE = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"

# NASA Worldview base web app
WORLDVIEW_BASE = "https://worldview.earthdata.nasa.gov"

# Supported satellite imagery layers
LAYERS = {
    "true_color": {
        "id": "MODIS_Terra_CorrectedReflectance_TrueColor",
        "name": "MODIS Terra True Color",
        "desc": "Natural color imagery (bands 1-4-3) showing Earth as seen by the human eye",
        "sensor": "MODIS (Terra)",
        "min_year": 2000,
    },
    "false_color": {
        "id": "MODIS_Terra_CorrectedReflectance_Bands721",
        "name": "MODIS Terra False Color (7-2-1)",
        "desc": "Shortwave infrared false color highlighting vegetation vitality (green), burn scars (red), and water bodies (black/dark blue)",
        "sensor": "MODIS (Terra)",
        "min_year": 2000,
    },
    "viirs_true_color": {
        "id": "VIIRS_SNPP_CorrectedReflectance_TrueColor",
        "name": "VIIRS True Color (Suomi NPP)",
        "desc": "High-resolution modern satellite imagery",
        "sensor": "VIIRS (Suomi NPP)",
        "min_year": 2012,
    },
}

# Optimal seasonal month-day per region to minimize cloud/snow interference
# Default is August 15 for Northern Hemisphere summer, February 15 for Southern Hemisphere
REGION_SEASONAL_DATES = {
    "sahara": "03-15",       # Spring clear skies before summer dust storms
    "madagascar": "09-15",   # Dry season peak
    "amazon": "08-15",       # Dry season (minimizes equatorial cloud cover)
    "greenland": "07-25",    # Peak summer melt season
    "bengal": "02-15",       # Winter post-monsoon clear skies
    "sahel": "09-15",        # End of monsoon / peak greening
    "australia": "01-20",    # Austral summer / fire season
    "arctic": "07-20",       # Peak Arctic summer / sea-ice minimum window
    "california": "08-15",   # Late summer wildfire/drought conditions
    "europe": "08-05",       # High summer / heatwave window
    "arabia": "02-20",       # Clear winter atmospheric window
    "china": "10-15",        # Autumn clear window / post-monsoon
    "congo": "07-15",        # Low-sun dry season (minimizes deep convective clouds)
    "brazil": "08-20",       # Cerrado dry season
    "siberia": "07-15",      # Short summer / thaw window
    "pacific": "09-01",      # Equinoctial clear window
}


def get_optimal_date_slice(region_id, lat=None):
    """Determine the best M-D date for clear satellite passes."""
    if region_id and region_id in REGION_SEASONAL_DATES:
        return REGION_SEASONAL_DATES[region_id]
    if lat is not None and lat < 0:
        return "02-15"  # Southern hemisphere summer
    return "08-15"      # Northern hemisphere summer


def build_gibs_wms_url(bbox, date_str, layer_key="true_color", width=600, height=400):
    """Build a NASA GIBS WMS 1.1.1 GetMap image URL for a bounding box [min_lon, min_lat, max_lon, max_lat]."""
    layer_info = LAYERS.get(layer_key, LAYERS["true_color"])
    layer_id = layer_info["id"]

    min_lon, min_lat, max_lon, max_lat = bbox
    bbox_str = f"{min_lon:.4f},{min_lat:.4f},{max_lon:.4f},{max_lat:.4f}"

    params = [
        ("SERVICE", "WMS"),
        ("REQUEST", "GetMap"),
        ("VERSION", "1.1.1"),
        ("LAYERS", layer_id),
        ("STYLES", ""),
        ("FORMAT", "image/jpeg"),
        ("TRANSPARENT", "FALSE"),
        ("WIDTH", str(width)),
        ("HEIGHT", str(height)),
        ("SRS", "EPSG:4326"),
        ("BBOX", bbox_str),
        ("TIME", date_str),
    ]
    query = "&".join(f"{k}={v}" for k, v in params)
    return f"{GIBS_WMS_BASE}?{query}"


def build_worldview_url(bbox, date_str, layer_key="true_color"):
    """Build a deep-link URL into NASA Worldview for interactive exploration."""
    layer_info = LAYERS.get(layer_key, LAYERS["true_color"])
    layer_id = layer_info["id"]

    min_lon, min_lat, max_lon, max_lat = bbox
    # Add a small padding if bbox is a point or very narrow
    if abs(max_lon - min_lon) < 0.1:
        min_lon -= 0.5
        max_lon += 0.5
    if abs(max_lat - min_lat) < 0.1:
        min_lat -= 0.5
        max_lat += 0.5

    v_param = f"{min_lon:.4f},{min_lat:.4f},{max_lon:.4f},{max_lat:.4f}"
    layers = f"{layer_id},Reference_Labels_15m,Reference_Features_15m,Coastlines_15m"

    return f"{WORLDVIEW_BASE}/?v={v_param}&t={date_str}-T00%3A00%3A00Z&l={layers}"


def get_satellite_evidence(region, start_year, end_year, bbox=None, layer_key="true_color", custom_date=None):
    """Produce the complete satellite evidence payload comparing baseline to recent year."""
    reg_id = region.get("id") if isinstance(region, dict) else str(region)
    reg_name = region.get("name") if isinstance(region, dict) else reg_id
    reg_bbox = bbox or (region.get("bbox") if isinstance(region, dict) else None)

    if not reg_bbox:
        raise ValueError("Bounding box is required for satellite imagery")

    # Clamping: MODIS Terra began in year 2000
    baseline_year = max(2000, min(start_year, 2024))
    recent_year = max(2000, min(end_year, 2024))

    # Center latitude for seasonal fallback
    center_lat = (reg_bbox[1] + reg_bbox[3]) / 2.0
    season_md = custom_date if (custom_date and len(custom_date) == 5 and "-" in custom_date) else get_optimal_date_slice(reg_id, center_lat)

    baseline_date = f"{baseline_year}-{season_md}"
    recent_date = f"{recent_year}-{season_md}"

    active_layer = LAYERS.get(layer_key, LAYERS["true_color"])

    return {
        "region_id": reg_id,
        "region_name": reg_name,
        "bbox": reg_bbox,
        "layer": active_layer,
        "available_layers": list(LAYERS.values()),
        "seasonal_md": season_md,
        "baseline": {
            "year": baseline_year,
            "date": baseline_date,
            "image_url": build_gibs_wms_url(reg_bbox, baseline_date, layer_key),
            "worldview_url": build_worldview_url(reg_bbox, baseline_date, layer_key),
        },
        "recent": {
            "year": recent_year,
            "date": recent_date,
            "image_url": build_gibs_wms_url(reg_bbox, recent_date, layer_key),
            "worldview_url": build_worldview_url(reg_bbox, recent_date, layer_key),
        },
        "attribution": "NASA EOSDIS Global Imagery Browse Services (GIBS) · MODIS / VIIRS",
    }
