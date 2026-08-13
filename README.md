# Contaminación del aire en Chile · Air Pollution in Chile

**Idioma / Language:** 🇪🇸 Español (a continuación) · 🇬🇧 [English below](#english)

Estimación reproducible de exposición a **múltiples contaminantes** (comuna × hora / día)
para Chile, derivada de percepción remota + reanálisis y validada contra las estaciones de
tierra de la red SINCA. Contaminantes cubiertos:

| Contaminante | Fuentes satelitales / reanálisis principales | Verdad-terreno |
|---|---|---|
| **PM₂.₅** | ACAG (GWR superficie), MERRA-2 (M2TMNXAER), MODIS MAIAC/AOD 3K, CAMS EAC4, GEOS-CF | SINCA |
| **PM₁₀** | CAMS EAC4, MERRA-2 (polvo/aerosol), MODIS AOD | SINCA |
| **NO₂** | Sentinel-5P TROPOMI, OMI (OMNO2), CAMS EAC4, GEOS-CF | SINCA |
| **O₃** | Sentinel-5P TROPOMI, OMI (OMTO3/OMDOAO3), MERRA-2, CAMS EAC4, GEOS-CF | SINCA |
| **SO₂** | Sentinel-5P TROPOMI, OMI (OMSO2), CAMS EAC4, GEOS-CF | SINCA |
| **CO** | Sentinel-5P TROPOMI, MOPITT (MOP03), CAMS EAC4, GEOS-CF | SINCA |

Predictores comunes a todos los contaminantes: meteorología (ERA5, ERA5-Land, MERRA-2),
uso/cobertura de suelo (ESA CCI), red vial (OpenStreetMap), altitud (NASADEM/Topografía),
luces nocturnas (VIIRS/DMSP) y variables censales (población, uso de leña).

---

<a id="español"></a>
## 🇪🇸 Español

### Estructura del repositorio

```
.
├── README.md · LICENSE · .env.example · .gitignore
│
├── scripts_pipeline/    ← PIPELINE de datos: descarga (01–NN) + procesamiento/validación + runners
├── scripts_superficie/  ← generadores de las superficies de exposición por contaminante
│
├── docs/                ← SITIO (fuentes .qmd + .html renderizado); portada bilingüe
│   └── references/
│       ├── references.bib    bibliografía consolidada
│       └── apa.csl           estilo APA
│
├── output_files/        ← resultados chicos + figuras (versionados); parquets/CSVs GB en .gitignore
│   └── figures/
│
├── data/                ← datos crudos (en .gitignore; regenerables con scripts_pipeline/)
│   ├── contaminantes/                 ← una carpeta por PRODUCTO satelital/reanálisis
│   │   ├── ACAG_V6.GL.02.04/              PM₂.₅ de superficie (GWR, van Donkelaar/ACAG)
│   │   ├── S5P_TROPOMI/                   Sentinel-5P — gases (2018+): NO2/ O3/ SO2/ CO/
│   │   ├── OMI/                           Aura OMI — gases (2004+): NO2/ O3/ SO2/
│   │   ├── MOPITT_CO/                     Terra MOPITT — CO columna (2000+)
│   │   ├── CAMS_EAC4/                     reanálisis CAMS multi-gas (NO2,O3,SO2,CO,PM2.5,PM10)
│   │   ├── GEOS_CF/                       NASA GEOS-CF composición (multi-gas, alta res, 2018+)
│   │   ├── M2TMNXAER.5.12.4/              MERRA-2 aerosoles (componentes PM₂.₅/PM₁₀)
│   │   ├── MCD19A2.061/                   MODIS MAIAC AOD (predictor de PM)
│   │   ├── MODIS_AOD_3K/                  MODIS MOD04/MYD04 3K AOD (predictor de PM)
│   │   ├── ERA5/ · ERA5Land/ · MERRA2_meteo/   meteorología (predictores comunes)
│   │   ├── Nightlights/ · Topografia/ · Censo/  predictores estáticos comunes
│   │   └── (cada producto: _tmp_global/ crudo global → raw_chile/ recortado → comunal_horario/ agregado)
│   │
│   ├── sinca/           ← verdad-terreno por contaminante: pm25/ pm10/ no2/ o3/ so2/ co/ (diario + horario)
│   ├── lulc/ · osm/ · shapefiles_regiones/   ← insumos geográficos
│
├── others_scripts/  ← trabajo LEGACY / exploratorio, NO parte del sitio
├── papers/          ← PDFs de referencia (en .gitignore)
└── tesis/           ← borradores (en .gitignore)
```

### Guías por carpeta (READMEs)

- **[`scripts_pipeline/README.md`](scripts_pipeline/README.md)** — descarga y procesamiento por
  contaminante, runners `.sh` y credenciales.
- **[`scripts_superficie/README.md`](scripts_superficie/README.md)** — generadores de las
  superficies de exposición (modelo, validación, figuras).
- **[`others_scripts/README.md`](others_scripts/README.md)** — trabajo legacy / exploratorio.
- **Bibliografía:** [`docs/references/references.bib`](docs/references/references.bib), estilo APA
  (`docs/references/apa.csl`).

### Reproducibilidad

```bash
# entorno con quarto + Python (numpy, pandas, scipy, scikit-learn, statsmodels, pyarrow,
# matplotlib, lightgbm, geopandas, pykrige, xarray, netCDF4, cdsapi)
# 1) descargar y procesar insumos por contaminante
bash scripts_pipeline/lanzar_descargas.sh
# 2) generar superficies de exposición
python scripts_superficie/surface_pipeline.py     # (parametrizado por contaminante)
# 3) renderizar el sitio
quarto render docs/index.qmd
```

- **Regenerar un artefacto:** bórralo de `output_files/` y re-renderiza (o corre su script).
- **Regenerar datos crudos** (los pesados no se versionan): pipeline de `scripts_pipeline/`
  (requiere credenciales NASA Earthdata / CDS / ADS-CAMS; ver `.env.example`).

### Datos pesados (no en GitHub)

`data/` y los insumos grandes de `output_files/` (parquets, CSVs de GB) están en `.gitignore`
(superan el límite de 100 MB de GitHub). Se **regeneran** con `scripts_pipeline/` o se comparten
aparte (Zenodo/Drive). Sí se versionan los **resultados chicos** y las **figuras**.

---

<a id="english"></a>
## 🇬🇧 English

Reproducible **multi-pollutant** exposure estimation (commune × hour / day) for Chile, derived
from remote sensing + reanalysis and validated against the SINCA ground-station network.
Pollutants covered: **PM₂.₅, PM₁₀, NO₂, O₃, SO₂, CO** (see the table at the top).

### Repository structure

```
.
├── README.md · LICENSE · .env.example · .gitignore
├── scripts_pipeline/    ← data PIPELINE: download + processing/validation + runners
├── scripts_superficie/  ← per-pollutant exposure-surface generators
├── docs/                ← SITE (.qmd sources + rendered .html) + references/
├── output_files/        ← small results + figures (versioned); GB parquets/CSVs gitignored
├── data/                ← raw data (gitignored): contaminantes/ (one folder per product),
│                          sinca/ (ground truth per pollutant), lulc/, osm/, shapefiles
├── others_scripts/  ← LEGACY / exploratory work, NOT part of the site
├── papers/ · tesis/ ← reference PDFs / drafts (gitignored)
```

Each product folder under `data/contaminantes/` follows the same pattern: `_tmp_global/` (raw
global download) → `raw_chile/` (clipped to Chile) → `comunal_horario/` (commune-aggregated).
Gas sensors (TROPOMI, OMI) fan out by pollutant (`NO2/ O3/ SO2/ CO/`); meteorology and static
predictors (ERA5, MERRA-2, land use, roads, DEM, nightlights, census) are shared across all
pollutants.

### Reproducibility

```bash
bash scripts_pipeline/lanzar_descargas.sh   # download + process inputs per pollutant
python scripts_superficie/surface_pipeline.py   # build exposure surfaces (parametrized by pollutant)
quarto render docs/index.qmd                 # render the site
```

Raw data and GB-scale outputs are gitignored (they exceed GitHub's 100 MB limit); they are
regenerated with `scripts_pipeline/` (needs NASA Earthdata / CDS / ADS-CAMS credentials — see
`.env.example`) or shared separately. Small results and figures are versioned.
