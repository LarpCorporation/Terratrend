# Official challenge resources, checked 15 November 2026

Challenge: [Be An Earth System Trend Detective! — NASA Space Apps 2026](https://www.spaceappschallenge.org/2026/challenges/earth-system-trend-detective/). The brief asks for variable selection, regional time series, rate of change and significance testing. It also discusses finding related processes and providing understandable examples. These are the project context; association alone does not prove causation.

The Resources tab was read directly in the browser after the text-only reader could not load it. These are its 13 links, not a claim that every linked service has been integrated.

| Listed resource | Link | Relationship to TerraTrend |
| --- | --- | --- |
| Giovanni | [NASA tool](https://giovanni.gsfc.nasa.gov/) | Optional cloud rectangle series implemented; native mode separately retrieves GES DISC grids |
| Hydrology Time Series | [NASA resource](https://disc.gsfc.nasa.gov/information/tools?title=Hydrology%20Time%20Series) | Integrated through the current NASA monthly time-series API: GLDAS soil water, soil temperature and near-surface wind; every intersecting native cell, up to 512 |
| AppEEARS | [NASA tool](https://appeears.earthdatacloud.nasa.gov/) | Integrated monthly MODIS NDVI/EVI polygon processing; only summary CSVs returned locally; separate NASA connection |
| Climate Data Online | [NOAA tool](https://www.ncei.noaa.gov/cdo-web/) | Integrated GSOM station temperature, wind and precipitation through NOAA's public NCEI Access API; station cohorts, not area averages |
| SeaWiFS time-series study | [NASA paper](https://ntrs.nasa.gov/api/citations/20090042747/downloads/20090042747.pdf) | Scientific reference; not a general-purpose observation API |
| KNMI Climate Explorer | [KNMI tool](https://climexp.knmi.nl/) | Additional data/analysis resource; not connected |
| Trend-testing article | [Challenge-listed article](https://medium.com/@snp.kriss/statistical-test-methods-to-detect-trends-in-time-series-data-b361a0ec530b) | Background reading; listing does not validate TerraTrend's implementation |
| Significance explainer | [Challenge-listed guide](https://www.statsig.com/perspectives/a-comprehensive-guide-to-statistical-significance) | Background reading |
| RADARSAT Constellation Mission data | [Canadian Space Agency](https://donnees-data.asc-csa.gc.ca/en/dataset/rcm) | Additional mission resource; not connected |
| GEO.ca | [Canadian geospatial portal](https://geo.ca/) | Additional reference/data portal; not connected |
| SWOT | [Canadian Space Agency](https://www.asc-csa.gc.ca/eng/satellites/swot/) | Additional mission resource; not connected |
| Ecosystem monitoring from space | [Canadian Space Agency](https://www.asc-csa.gc.ca/eng/satellites/everyday-lives/monitoring-and-protecting-our-ecosystems-from-space.asp) | Background and application examples |
| SAR tutorial | [Canadian Space Agency tutorial](https://github.com/asc-csa/Synthetic_Aperture_Radar_Tutorial) | Additional learning resource; not connected |

NASA POWER is another legitimate NASA service. It is not among these 13 links; the challenge brief inspected here does not prohibit additional NASA resources. The previous app restriction was an implementation/source-policy choice, not evidence that POWER is scientifically invalid or forbidden by the challenge.

**Four of the 13 linked resources now have automatic data routes in TerraTrend:** Giovanni, Hydrology Time Series, AppEEARS and Climate Data Online observations. These expose **20 unique live measurement IDs** across the native and linked modes. The remaining entries include research/tutorial resources, portals and mission-specific sources; they are not all interchangeable monthly data APIs. KNMI's anonymous interface presented human verification during the earlier investigation; no gate was bypassed. RCM, SWOT and Canadian reference layers require different spatial/temporal processing and have not been attached to this monthly trend workflow. See [the completed source and preset report](SOURCES_AND_PRESETS.md) for actual mappings, source quality limits, caching and live evidence. Giovanni now offers four measurements: temperature and humidity at 2 m and 10 m.

The existing POWER cache remains an explicit option. A live POWER option has not been added in this change. Its earlier 25-point sampling is not equivalent to complete native-cell polygon aggregation, so restoring that behavior without labeling its coverage would not preserve the current scientific method. See [NASA's monthly API documentation](https://power.larc.nasa.gov/docs/services/api/temporal/monthly/) for its prepared time-series and regional interfaces, and [the implemented Giovanni scope](GIOVANNI_INTEGRATION.md) for the current low-transfer option.
