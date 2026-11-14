"""Curated catalog of NASA POWER Earth science variables, Spheres and Regions.

Every variable is verified against the live NASA POWER API (MERRA-2 / GPCP / CERES).
Includes Earth System Spheres classification and plain-English explanatory metadata.
"""

SPHERES = [
    {"id": "all", "code": "ALL", "name": "All Spheres", "desc": "Complete Earth system observation"},
    {"id": "atmosphere", "code": "ATM", "name": "Atmosphere", "desc": "Gaseous envelope driving weather, thermodynamic gradients, and heat transport"},
    {"id": "hydrosphere", "code": "HYD", "name": "Hydrosphere", "desc": "Water cycle, atmospheric moisture transport, and saturation"},
    {"id": "land", "code": "LND", "name": "Land & Biosphere", "desc": "Terrestrial surface, soil moisture reservoir, and evapotranspiration"},
    {"id": "energy", "code": "ENG", "name": "Energy & Radiation", "desc": "Earth radiant energy balance: incoming solar shortwave vs. downwelling thermal infrared"},
]

CATALOG = [
    # ---- temperature (Atmosphere & Land) ----------------------------------
    {"id": "T2M", "name": "Air Temperature", "unit": "°C", "color": "#ff7a33",
     "mission": "MERRA-2", "group": "temperature",
     "sphere": "atmosphere", "sphere_code": "ATM", "sphere_name": "Atmosphere",
     "desc": "Mean near-surface air temperature at 2 m"},
    {"id": "T2M_MAX", "name": "Max Temperature", "unit": "°C", "color": "#ffa564",
     "mission": "MERRA-2", "group": "temperature",
     "sphere": "atmosphere", "sphere_code": "ATM", "sphere_name": "Atmosphere",
     "desc": "Monthly mean of the daily maximum temperature"},
    {"id": "T2M_MIN", "name": "Min Temperature", "unit": "°C", "color": "#ffc899",
     "mission": "MERRA-2", "group": "temperature",
     "sphere": "atmosphere", "sphere_code": "ATM", "sphere_name": "Atmosphere",
     "desc": "Monthly mean of the daily minimum temperature"},
    {"id": "TS", "name": "Skin Temperature", "unit": "°C", "color": "#ff8f5a",
     "mission": "MERRA-2", "group": "temperature",
     "sphere": "land", "sphere_code": "LND", "sphere_name": "Land & Biosphere",
     "desc": "Temperature of the Earth's surface skin — the layer a satellite actually sees, over land or ocean"},
    {"id": "T2M_RANGE", "name": "Diurnal Range", "unit": "°C", "color": "#ffc08a",
     "mission": "MERRA-2", "group": "temperature",
     "sphere": "atmosphere", "sphere_code": "ATM", "sphere_name": "Atmosphere",
     "desc": "Difference between daily maximum and minimum temperature — a fingerprint of cloud cover and soil moisture"},

    # ---- water & moisture (Hydrosphere & Land) ---------------------------
    {"id": "PRECTOTCORR", "name": "Precipitation", "unit": "mm/day",
     "color": "#5b9cf0", "mission": "GPCP", "group": "water",
     "sphere": "hydrosphere", "sphere_code": "HYD", "sphere_name": "Hydrosphere",
     "desc": "Bias-corrected total precipitation (rain and snow), averaged over the month"},
    {"id": "RH2M", "name": "Relative Humidity", "unit": "%", "color": "#8fb8d8",
     "mission": "MERRA-2", "group": "water",
     "sphere": "hydrosphere", "sphere_code": "HYD", "sphere_name": "Hydrosphere",
     "desc": "Relative humidity at 2 m — how close the air is to saturation"},
    {"id": "QV2M", "name": "Specific Humidity", "unit": "g/kg", "color": "#7fd3a0",
     "mission": "MERRA-2", "group": "water",
     "sphere": "hydrosphere", "sphere_code": "HYD", "sphere_name": "Hydrosphere",
     "desc": "Mass of water vapour per kilogram of air — actual moisture content"},
    {"id": "EVPTRNS", "name": "Evapotranspiration", "unit": "mm/day",
     "color": "#58c9b0", "mission": "MERRA-2", "group": "water",
     "sphere": "land", "sphere_code": "LND", "sphere_name": "Land & Biosphere",
     "desc": "Water leaving the surface through evaporation and plant transpiration"},
    {"id": "EVLAND", "name": "Evaporation (Land)", "unit": "mm/day",
     "color": "#46b39d", "mission": "MERRA-2", "group": "water",
     "sphere": "land", "sphere_code": "LND", "sphere_name": "Land & Biosphere",
     "desc": "Evaporation from the land surface alone, excluding transpiration"},
    {"id": "GWETROOT", "name": "Root-Zone Moisture", "unit": "0–1",
     "color": "#9bd36a", "mission": "MERRA-2", "group": "water",
     "sphere": "land", "sphere_code": "LND", "sphere_name": "Land & Biosphere",
     "desc": "Water content of the root zone as a fraction of saturation (0 = dry, 1 = saturated)"},
    {"id": "GWETTOP", "name": "Surface Moisture", "unit": "0–1",
     "color": "#b8dd8a", "mission": "MERRA-2", "group": "water",
     "sphere": "land", "sphere_code": "LND", "sphere_name": "Land & Biosphere",
     "desc": "Water content of the top soil layer as a fraction of saturation — early warning sign of flash drought"},

    # ---- energy & atmosphere ---------------------------------------------
    {"id": "WS2M", "name": "Wind Speed", "unit": "m/s", "color": "#b09be8",
     "mission": "MERRA-2", "group": "energy",
     "sphere": "atmosphere", "sphere_code": "ATM", "sphere_name": "Atmosphere",
     "desc": "Wind speed at 2 m above the surface"},
    {"id": "ALLSKY_SFC_SW_DNI", "name": "Solar Irradiance", "unit": "kWh/m²/day",
     "color": "#e3c265", "mission": "CERES", "group": "energy",
     "sphere": "energy", "sphere_code": "ENG", "sphere_name": "Energy & Radiation",
     "desc": "Direct normal solar irradiance reaching the surface"},
    {"id": "ALLSKY_SFC_LW_DWN", "name": "Longwave Flux", "unit": "W/m²",
     "color": "#e88bb0", "mission": "CERES", "group": "energy",
     "sphere": "energy", "sphere_code": "ENG", "sphere_name": "Energy & Radiation",
     "desc": "Downwelling thermal infrared radiation — the greenhouse signal"},
    {"id": "PS", "name": "Surface Pressure", "unit": "kPa", "color": "#9aa6b4",
     "mission": "MERRA-2", "group": "energy",
     "sphere": "atmosphere", "sphere_code": "ATM", "sphere_name": "Atmosphere",
     "desc": "Surface air pressure"},
]

REGIONS = [
    # ---- land ------------------------------------------------------------
    {"id": "sahara", "name": "Sahara West", "bbox": [-17.0, 14.0, -13.0, 18.0],
     "desc": "Western Sahara / Sahel transition", "surface": "land"},
    {"id": "madagascar", "name": "Madagascar South", "bbox": [43.0, -25.5, 47.5, -21.5],
     "desc": "Southern Madagascar drought zone", "surface": "land"},
    {"id": "amazon", "name": "Amazon East", "bbox": [-54.0, -12.0, -50.0, -8.0],
     "desc": "Eastern Amazon deforestation arc", "surface": "land"},
    {"id": "greenland", "name": "Greenland South", "bbox": [-50.0, 59.0, -44.0, 63.0],
     "desc": "Southern Greenland ice margin", "surface": "land"},
    {"id": "bengal", "name": "Bay of Bengal", "bbox": [88.0, 18.0, 92.0, 22.0],
     "desc": "Northern Bay of Bengal cyclone zone", "surface": "land"},
    {"id": "sahel", "name": "Sahel Central", "bbox": [-2.0, 12.0, 2.0, 16.0],
     "desc": "Central Sahel greening zone", "surface": "land"},
    {"id": "australia", "name": "Australia Southeast", "bbox": [144.0, -38.0, 148.0, -34.0],
     "desc": "SE Australia fire weather zone", "surface": "land"},
    {"id": "arctic", "name": "Arctic Siberia", "bbox": [100.0, 70.0, 106.0, 74.0],
     "desc": "Eastern Siberian permafrost zone", "surface": "land"},
    {"id": "california", "name": "California Central", "bbox": [-122.0, 34.0, -117.0, 39.0],
     "desc": "California drought & wildfire corridor", "surface": "land"},
    {"id": "europe", "name": "Central Europe", "bbox": [6.0, 46.0, 12.0, 51.0],
     "desc": "European heatwave & flood zone", "surface": "land"},
    {"id": "arabia", "name": "Arabian Peninsula", "bbox": [40.0, 20.0, 48.0, 28.0],
     "desc": "Arabian desert & dust source region", "surface": "land"},
    {"id": "china", "name": "East China", "bbox": [110.0, 28.0, 118.0, 36.0],
     "desc": "Eastern China monsoon & aerosol zone", "surface": "land"},
    {"id": "congo", "name": "Congo Basin", "bbox": [15.0, -4.0, 23.0, 4.0],
     "desc": "Congo rainforest carbon zone", "surface": "land"},
    {"id": "brazil", "name": "Brazil Cerrado", "bbox": [-54.0, -20.0, -46.0, -12.0],
     "desc": "Brazilian Cerrado agricultural frontier", "surface": "land"},
    {"id": "siberia", "name": "West Siberia", "bbox": [64.0, 56.0, 72.0, 62.0],
     "desc": "West Siberian wetland & methane zone", "surface": "land"},
    {"id": "pacific", "name": "Central Pacific", "bbox": [-165.0, -5.0, -155.0, 5.0],
     "desc": "ENSO central Pacific warm pool", "surface": "ocean"},

    # ---- Ghana focus regions ---------------------------------------------
    {"id": "ghana_north", "name": "Ghana North (Savannah)",
     "bbox": [-2.5, 9.0, 0.0, 11.0],
     "desc": "Northern Ghana / Savannah agro-ecological zone", "surface": "land"},
    {"id": "ghana_south", "name": "Ghana South (Forest/Coast)",
     "bbox": [-2.8, 5.0, 0.5, 7.0],
     "desc": "Southern Ghana forest belt and Gulf of Guinea coast", "surface": "land"},
    {"id": "lake_volta", "name": "Lake Volta Basin",
     "bbox": [-1.0, 6.0, 0.8, 8.5],
     "desc": "Lake Volta — largest artificial reservoir by surface area", "surface": "land"},

    # ---- ocean coverage --------------------------------------------------
    {"id": "north_atlantic", "name": "North Atlantic Subpolar",
     "bbox": [-40.0, 50.0, -30.0, 55.0],
     "desc": "AMOC cold blob / North Atlantic warming hole", "surface": "ocean"},
    {"id": "tropical_pacific", "name": "Tropical Pacific (Niño 3.4)",
     "bbox": [-170.0, -5.0, -120.0, 5.0],
     "desc": "Core El Niño / Southern Oscillation monitoring region", "surface": "ocean"},
    {"id": "mediterranean", "name": "Mediterranean Sea",
     "bbox": [10.0, 35.0, 20.0, 40.0],
     "desc": "Marine heatwave hotspot / enclosed basin", "surface": "ocean"},
    {"id": "southern_ocean", "name": "Southern Ocean (Drake)",
     "bbox": [-65.0, -60.0, -55.0, -55.0],
     "desc": "Antarctic circumpolar current / sea-ice boundary", "surface": "ocean"},
]

# ---------------------------------------------------------------------------
# Plain-English variable definitions and trend meanings.
# Built for a high-school / general-public audience.
# ---------------------------------------------------------------------------
EXPLAIN = {
    "T2M": {
        "plain": "How warm the air is, about 2 metres above the ground — roughly what you feel standing outside.",
        "trend_means": "Rising means the air is getting warmer on average.",
    },
    "T2M_MAX": {
        "plain": "The average of each day's highest temperature for the month.",
        "trend_means": "Rising means hotter afternoons — heat stress on crops and people.",
    },
    "T2M_MIN": {
        "plain": "The average of each day's lowest temperature for the month.",
        "trend_means": "Rising means warmer nights — plants burn more energy and lose more water overnight.",
    },
    "TS": {
        "plain": "The temperature of the very top of the surface — soil, leaves or water — the layer a satellite actually sees.",
        "trend_means": "Rising means the ground or sea surface itself is heating, not just the air above it.",
    },
    "T2M_RANGE": {
        "plain": "How much the temperature swings between the daily low and the daily high.",
        "trend_means": "A narrowing range usually means more cloud or moisture; a widening one means clearer, drier skies.",
    },
    "PRECTOTCORR": {
        "plain": "How much rain and snow falls, averaged over each day of the month. 1 mm/day is about 30 mm of rain in a month.",
        "trend_means": "Rising means more water arriving. Falling means drier months — the first signal of drought.",
    },
    "RH2M": {
        "plain": "How full of moisture the air is, as a percentage of the most it could hold at that temperature.",
        "trend_means": "Falling means drier air, which pulls more water out of the soil and out of plants.",
    },
    "QV2M": {
        "plain": "The actual mass of water vapour in a kilogram of air — the true moisture content, whatever the temperature.",
        "trend_means": "Rising means the atmosphere is holding more water, which can feed heavier rain when it condenses.",
    },
    "EVPTRNS": {
        "plain": "Water leaving the ground and plants into the air — evaporation from soil plus transpiration from leaves.",
        "trend_means": "Rising means the landscape is losing water faster. Falling can mean it has none left to lose.",
    },
    "EVLAND": {
        "plain": "Water evaporating from bare ground and open water, without the plant part.",
        "trend_means": "Tracks how quickly the land surface itself dries out.",
    },
    "GWETROOT": {
        "plain": "How much water is stored in the soil around plant roots, from 0 (bone dry) to 1 (saturated).",
        "trend_means": "Falling is the signature of agricultural drought — the water crops actually live on.",
    },
    "GWETTOP": {
        "plain": "Water in just the top layer of soil, from 0 to 1.",
        "trend_means": "Responds within days to rainfall, so it is the earliest warning sign of flash drought.",
    },
    "WS2M": {
        "plain": "How fast the air is moving, 2 metres above the ground.",
        "trend_means": "Rising means windier conditions — more evaporation, more dust, more fire risk.",
    },
    "ALLSKY_SFC_SW_DNI": {
        "plain": "How much direct sunshine reaches the surface.",
        "trend_means": "Falling often means more cloud or haze; rising means clearer skies.",
    },
    "ALLSKY_SFC_LW_DWN": {
        "plain": "Invisible heat radiation coming down from the sky and clouds — you feel it as warmth on a cloudy night.",
        "trend_means": "Rising is a fingerprint of a warmer, moister atmosphere — the greenhouse effect in action.",
    },
    "PS": {
        "plain": "The weight of the air pressing down on the surface.",
        "trend_means": "Small swings track day-to-day weather; a long rise points to a change in large-scale circulation.",
    },
}

for _v in CATALOG:
    _v.update(EXPLAIN.get(_v["id"], {}))

GROUP_LABELS = {
    "temperature": "TEMPERATURE",
    "water": "WATER & MOISTURE",
    "energy": "ENERGY & ATMOSPHERE",
}
