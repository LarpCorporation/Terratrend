# Team & Contributions

**NASA Space Apps Challenge 2026 — Project TerraTrend**  
*Challenge: "Be An Earth System Trend Detective!"*

---

## Table of Contents

1. [Team Roster & Core Responsibilities](#1-team-roster--core-responsibilities)
2. [Architectural Ownership Breakdown](#2-architectural-ownership-breakdown)
   - [2.1 Geospatial & 3D Visualization Engineering (Kwame Brown)](#21-geospatial--3d-visualization-engineering-kwame-brown)
   - [2.2 Backend Architecture & Scientific Computing (Asenso Owusu Ansah / holmes1560)](#22-backend-architecture--scientific-computing-asenso-owusu-ansah--holmes1560)
3. [Joint Team Accomplishments](#3-joint-team-accomplishments)
4. [Synergy with AI: Human Vision vs. AI Acceleration](#4-synergy-with-ai-human-vision-vs-ai-acceleration)
5. [Project Evolution & Milestones](#5-project-evolution--milestones)
6. [Acknowledgments & NASA Data Partners](#6-acknowledgments--nasa-data-partners)

---

## 1. Team Roster & Core Responsibilities

TerraTrend was developed by a focused, multidisciplinary team of engineers and data detectives uniting spatial graphics engineering, scientific backend architecture, and non-parametric data science.

```
                      TERRATREND CORE TEAM
            ┌──────────────────────────────────────┐
            │          NASA Space Apps 2026        │
            │   "Be An Earth System Trend Detective"│
            └──────────────────┬───────────────────┘
                               │
            ┌──────────────────┴───────────────────┐
            │                                      │
            ▼                                      ▼
     KWAME BROWN                       ASENSO OWUSU ANSAH (holmes1560)
  Lead Geospatial & 3D             Lead Backend Systems & Climate
 Visualization Engineer                  Data Architect
- Three.js 3D Photoreal Globe      - Statistical Engine (MK / Theil-Sen)
- Shaders, Atmosphere & Terminator - Interconnection & Teleconnection Engine
- Cybermap UI & Control Cockpit    - Multi-Source NASA Pipeline (OPeNDAP)
- Frontend Contract & QA Tests     - Zero-Hallucination Explainer & Cloud
```

---

## 2. Architectural Ownership Breakdown

### 2.1 Geospatial & 3D Visualization Engineering (Kwame Brown)
- **Interactive 3D Planetary Engine**:
  - Implemented the custom Three.js globe renderer featuring dynamic dot-matrix and blue-relief topographic texture modes.
  - Engineered procedural cloud layers and a physically accurate solar day/night terminator with atmospheric Rayleigh-scattering glow.
  - Solved complex 3D raycasting and depth-testing challenges: ensured region boundary rings follow the planetary sphere without clipping artifacts or dead zones at the planetary limb.
- **Cybermap UI & Interaction Experience**:
  - Designed the Kaspersky Cybermap-inspired visual cockpit with a dark slate palette, monospaced telemetry dials, and glowing trend vectors.
  - Engineered the two-panel investigation workflow (Measurement Selection & Area Inspector), allowing seamless switching between national boundaries, subnational administrative zones, and freehand lasso tools.
  - Implemented UI state persistence and keyboard-accessible draggable floating panels.
- **Frontend Quality Assurance**:
  - Built frontend contract verification suites (`tests/*.test.cjs`) guaranteeing seamless API-to-UI data binding.
  - Integrated resilient fallback mechanisms for external bibliographic lookups (OpenAlex with Crossref failover).

### 2.2 Backend Architecture & Scientific Computing (Asenso Owusu Ansah / holmes1560)
- **Core Statistical & Mathematical Engine**:
  - Engineered the non-parametric trend detection pipeline in `backend/analysis.py`, implementing the Mann-Kendall test with exact tie corrections, AR(1) serial correlation variance inflation on detrended residuals, and the Theil–Sen robust median slope estimator.
  - Implemented Gilbert (1987) non-parametric confidence intervals and Lentz continued fractions for incomplete beta functions.
  - Built the dual-method diagnostic matrix (comparing Mann-Kendall non-parametric results against parametric OLS $t$-tests).
- **Earth-System Interconnectivity Engine**:
  - Formulated the teleconnection discovery engine in `backend/interconnect.py`, including tri-component monthly time-series decomposition (trend + seasonal climatology + anomaly residual) via alternating projection.
  - Developed optimal lag search with Quenouille–Bartlett effective sample size corrections ($N_{\text{eff}}$), first-order partial correlation confounder screening, and two-way Granger causality $F$-tests.
  - Integrated Benjamini–Hochberg False Discovery Rate (FDR) control to prevent statistical data dredging.
- **NASA Data Ingestion & Spatial Clipping**:
  - Architected the multi-source pipeline integrating NASA MERRA-2 (via OPeNDAP), NASA Giovanni (M2IMNXASM), NASA AppEEARS (MODIS NDVI/EVI), NASA Hydrology (GLDAS), and NOAA NCEI.
  - Implemented exact polygon raycasting intersection and $\cos(\text{latitude})$ cell-area weighting with an $80\%$ minimum spatial coverage gate.
- **AI Explainer & Cloud Deployment**:
  - Built the "Zero-Hallucination" Verified Statement Bank explainer architecture, pairing pure-Python evidence hashes with Groq LLM routing.
  - Containerized the platform with multi-stage Docker builds, Render Blueprint automation, and Vercel proxy configurations.

---

## 3. Joint Team Accomplishments

Together, the team achieved:
1. **End-to-End Scientific Integrity**: Transformed the competition challenge into a rigorous scientific observatory that refuses to guess, actively warns users about non-significant trends, and protects against the seasonal sawtooth trap.
2. **Comprehensive Test Suite**: Engineered **371 backend automated tests** and **102 frontend tests**, validating every formula, boundary edge case, and data converter against real NASA ground truth.
3. **Multi-Source Ingestion**: Unified 20 distinct environmental measurements across 4 separate federal data providers into a standardized, unified analysis contract.
4. **Universal Clone-and-Run Portability**: Guaranteed that any collaborator or judge can clone the repository and run `./start.sh` or Docker without manual configuration or proprietary cloud dependencies.

---

## 4. Synergy with AI: Human Vision vs. AI Acceleration

The development of TerraTrend was fundamentally human-led, with AI tools serving as an intelligent co-pilot and velocity accelerator:

```
┌─────────────────────────────────────────────────────────────┐
│                    HUMAN TEAM (100% OWNED)                  │
│  - Conceived the project idea & user journey                │
│  - Identified the seasonal sawtooth trap & climate pitfalls │
│  - Formulated AR(1) variance inflation & Theil-Sen math     │
│  - Designed the Cybermap UI layout & 3D visual language     │
│  - Audited code against real NASA NetCDF4 binary granules   │
│  - Built the Zero-Hallucination Statement Bank guardrails   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   AI TOOLS (FORCE MULTIPLIER)               │
│  - Scaffolded boilerplate endpoints & SQLite schema models  │
│  - Accelerated CSS token writing & responsive panel layout  │
│  - Recommending Lentz continued fraction convergence logic  │
│  - Synthesized exhaustive parameterized test case suites    │
│  - Helped document technical findings at industry standard  │
└─────────────────────────────────────────────────────────────┘
```

**Key Takeaway**:
> "If it wasn't for the human team, TerraTrend could not have existed. AI did not know that raw Arctic climate data would yield $p = 0.52$ due to seasonal cycles; AI did not know that negative autocorrelation in small samples requires a variance floor to prevent false certainty; AI did not design the spatial cosine weighting. The human team provided the scientific soul, mathematical guardrails, and architectural vision—AI helped us type faster, prototype designs rapidly, and build an airtight test suite."

---

## 5. Project Evolution & Milestones

- **Phase 1: Conceptualization & Proof-of-Concept**
  - Analyzed the NASA Space Apps 2026 challenge brief ("Be An Earth System Trend Detective!").
  - Prototyped initial data queries against NASA POWER and recognized the limitations of point sampling versus true spatial polygon integration.
- **Phase 2: Mathematical Foundation & De-Seasoning**
  - Identified the seasonal sawtooth trap; implemented annual aggregation and Hirsch–Slack seasonal tests.
  - Implemented the Mann-Kendall $S$-statistic, Theil–Sen median slope, and AR(1) autocorrelation variance inflation.
- **Phase 3: 3D Visualization Overhaul & Cybermap Experience**
  - Rebuilt the frontend from the ground up with Three.js, introducing photoreal Earth shaders, day/night terminators, and the dual-panel inspection cockpit.
- **Phase 4: Teleconnections & Cross-Sphere Interconnectivity**
  - Developed the tri-component time series decomposition engine.
  - Implemented lagged cross-correlation, partial correlation, Granger causality, and Benjamini–Hochberg FDR control.
- **Phase 5: Multi-Source NASA Expansion & Native Polygon Integration**
  - Connected direct OPeNDAP access to NASA GES DISC MERRA-2 grids, AppEEARS vegetation indices, and GLDAS Hydrology series.
  - Formulated exact polygon clipping with $\cos(\text{latitude})$ weighting.
- **Phase 6: Grounded AI Assistant & Cloud Deployment**
  - Engineered the Zero-Hallucination Explainer with Groq LLM integration and multi-tier reading levels (Plain / Student / Researcher).
  - Containerized with Docker, automated Render Blueprint deployments, and configured Vercel static routing.

---

## 6. Acknowledgments & NASA Data Partners

We express our sincere gratitude to:
- **NASA Space Apps Challenge 2026** for providing an inspiring challenge that bridges raw space observations with real-world environmental detective work.
- **NASA Goddard Earth Sciences Data and Information Services Center (GES DISC)** for MERRA-2 reanalysis and Giovanni time-series access.
- **NASA Land Processes Distributed Active Archive Center (LP DAAC)** for AppEEARS MODIS NDVI/EVI processing.
- **NOAA National Centers for Environmental Information (NCEI)** for public Global Summary of the Month (GSOM) station records.
- **Natural Earth** for public-domain 1:50m cultural boundaries and administrative subdivisions.
