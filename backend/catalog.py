"""Curated catalog of NASA POWER Earth science variables.

Every entry is verified against the live POWER API: the monthly endpoint must
return a non-empty series for that parameter (see test_catalog.py).
"""

CATALOG = [
    # ---- temperature ------------------------------------------------------
    {"id": "T2M", "name": "Air Temperature", "unit": "°C", "color": "#ff7a33",
     "mission": "MERRA-2", "group": "temperature",
     "desc": "Mean near-surface air temperature at 2 m"},
    {"id": "T2M_MAX", "name": "Max Temperature", "unit": "°C", "color": "#ffa564",
     "mission": "MERRA-2", "group": "temperature",
     "desc": "Monthly mean of the daily maximum temperature"},
    {"id": "T2M_MIN", "name": "Min Temperature", "unit": "°C", "color": "#ffc899",
     "mission": "MERRA-2", "group": "temperature",
     "desc": "Monthly mean of the daily minimum temperature"},
    {"id": "TS", "name": "Skin Temperature", "unit": "°C", "color": "#ff8f5a",
     "mission": "MERRA-2", "group": "temperature",
     "desc": "Temperature of the Earth's surface skin — the layer a satellite "
             "actually sees, over land or ocean"},
    {"id": "T2M_RANGE", "name": "Diurnal Range", "unit": "°C", "color": "#ffc08a",
     "mission": "MERRA-2", "group": "temperature",
     "desc": "Difference between daily maximum and minimum temperature — a "
             "fingerprint of cloud cover, soil moisture and urbanisation"},

    # ---- water ------------------------------------------------------------
    {"id": "PRECTOTCORR", "name": "Precipitation", "unit": "mm/day",
     "color": "#5b9cf0", "mission": "GPCP", "group": "water",
     "desc": "Bias-corrected total precipitation (rain and snow), averaged "
             "over the month"},
    {"id": "RH2M", "name": "Relative Humidity", "unit": "%", "color": "#8fb8d8",
     "mission": "MERRA-2", "group": "water",
     "desc": "Relative humidity at 2 m — how close the air is to saturation"},
    {"id": "QV2M", "name": "Specific Humidity", "unit": "g/kg", "color": "#7fd3a0",
     "mission": "MERRA-2", "group": "water",
     "desc": "Mass of water vapour per kilogram of air — the actual moisture "
             "content, unlike relative humidity"},
    {"id": "EVPTRNS", "name": "Evapotranspiration", "unit": "mm/day",
     "color": "#58c9b0", "mission": "MERRA-2", "group": "water",
     "desc": "Water leaving the surface through evaporation and plant "
             "transpiration — the 'evaporation' variable the brief names"},
    {"id": "EVLAND", "name": "Evaporation (Land)", "unit": "mm/day",
     "color": "#46b39d", "mission": "MERRA-2", "group": "water",
     "desc": "Evaporation from the land surface alone, excluding transpiration"},
    {"id": "GWETROOT", "name": "Root-Zone Moisture", "unit": "0–1",
     "color": "#9bd36a", "mission": "MERRA-2", "group": "water",
     "desc": "Water content of the root zone as a fraction of saturation "
             "(0 = dry, 1 = saturated) — the drought indicator"},
    {"id": "GWETTOP", "name": "Surface Moisture", "unit": "0–1",
     "color": "#b8dd8a", "mission": "MERRA-2", "group": "water",
     "desc": "Water content of the top soil layer as a fraction of saturation "
             "— responds fast to rainfall, drives flash drought"},

    # ---- energy & atmosphere ---------------------------------------------
    {"id": "WS2M", "name": "Wind Speed", "unit": "m/s", "color": "#b09be8",
     "mission": "MERRA-2", "group": "energy",
     "desc": "Wind speed at 2 m above the surface"},
    {"id": "ALLSKY_SFC_SW_DNI", "name": "Solar Irradiance", "unit": "kWh/m²/day",
     "color": "#e3c265", "mission": "CERES", "group": "energy",
     "desc": "Direct normal solar irradiance reaching the surface"},
    {"id": "ALLSKY_SFC_LW_DWN", "name": "Longwave Flux", "unit": "W/m²",
     "color": "#e88bb0", "mission": "CERES", "group": "energy",
     "desc": "Downwelling thermal infrared radiation — the greenhouse signal"},
    {"id": "PS", "name": "Surface Pressure", "unit": "kPa", "color": "#9aa6b4",
     "mission": "MERRA-2", "group": "energy",
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

    # ---- ocean -----------------------------------------------------------
    {"id": "pacific", "name": "Central Pacific", "bbox": [-165.0, -5.0, -155.0, 5.0],
     "desc": "ENSO central Pacific warm pool", "surface": "ocean"},
    {"id": "north_atlantic", "name": "North Atlantic", "bbox": [-40.0, 40.0, -20.0, 50.0],
     "desc": "Subpolar Atlantic storm-track & AMOC zone", "surface": "ocean"},
    {"id": "indian_ocean", "name": "Indian Ocean", "bbox": [60.0, -20.0, 80.0, -5.0],
     "desc": "Southern Indian Ocean monsoon & cyclone basin", "surface": "ocean"},
    {"id": "southern_ocean", "name": "Southern Ocean", "bbox": [-10.0, -60.0, 10.0, -52.0],
     "desc": "Antarctic Circumpolar Current zone", "surface": "ocean"},
]
