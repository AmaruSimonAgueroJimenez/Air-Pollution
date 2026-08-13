# scripts_pipeline/ — Descarga de datos por contaminante · Data download pipeline

> ↩ [README principal](../README.md) · 🧩 [scripts_superficie/](../scripts_superficie/README.md)

**Idioma / Language:** 🇪🇸 Español · 🇬🇧 [English below](#english)

---

<a id="español"></a>
## 🇪🇸 Español

Descargadores **reproducibles** de los insumos de exposición para los 6 contaminantes
(**PM2.5, PM10, NO2, O3, SO2, CO**). Cada script resuelve sus rutas de forma absoluta y
escribe bajo `../data/contaminantes/<FUENTE>/` (satélite/reanálisis) o `../data/sinca/<pol>/`
(verdad-terreno). Todos aceptan `--desde/--hasta` (YYYY-MM-DD) y `--dry-run`.

### Requisitos

```bash
pip install -r requirements.txt          # earthaccess, cdsapi, xarray, boto3, ...
cp ../.env.example ../.env                # y completa las credenciales
```

Credenciales (en `../.env`): **NASA Earthdata** (TROPOMI, OMI, MOPITT, MERRA-2, MODIS),
**Copernicus ADS** (CAMS EAC4). ACAG PM2.5 usa un bucket S3 **público** (sin credenciales);
SINCA y GEOS-CF tampoco requieren credenciales.

### Descargadores (identificadores verificados en CMR/ADS/S3)

| Script | Fuente / producto | Contaminante(s) | ID verificado |
|---|---|---|---|
| `descargar_sinca.py` | SINCA (exportador `tsindico2`) | PM2.5,PM10,NO2,O3,SO2,CO | 109 estaciones (`data/sinca/config_sinca_estaciones.json`); `macro` único con ruta completa y sufijo `.ic` |
| `descargar_cams_eac4.py` | CAMS reanálisis EAC4 (ADS) | NO2,O3,SO2,CO,PM2.5,PM10 | `cams-global-reanalysis-eac4` (nivel modelo 60 para gases) |
| `descargar_geoscf.py` | NASA GEOS-CF (OPeNDAP) | O3,NO2,SO2,CO,PM2.5 | `aqc_tavg_1hr_g1440x721_v1` (superficie, horario) |
| `descargar_tropomi.py` | Sentinel-5P TROPOMI L2 (GES DISC) | NO2,O3,SO2,CO | `S5P_L2__NO2____HiR` · `…O3_TOT_HiR` · `…SO2____HiR` · `…CO_____HiR` (v2); recorta a Chile al vuelo |
| `descargar_omi.py` | Aura OMI L3 diario | NO2,O3,SO2 | `OMNO2d` · `OMTO3d` · `OMSO2e` (v004) |
| `descargar_mopitt.py` | Terra MOPITT L3 diario | CO | `MOP03J` (version_id `10`, no `010`) |
| `descargar_acag_pm25.py` | ACAG SatPM2.5 superficie (S3 público) | PM2.5 | `s3://satpmdata/` · V6GL03 (CNNPM25, FineResolution/SA) |
| `descargar_merra2_aer.py` | MERRA-2 aerosoles | PM2.5,PM10 (componentes) | `M2T1NXAER` (v5.12.4); recorta a Chile al vuelo |
| `descargar_maiac_aod.py` | MODIS MAIAC AOD 1 km | (predictor PM) | `MCD19A2` (v061) |
| `descargar_modis_aod.py` | MODIS AOD 3 km (Terra/Aqua) | (predictor PM) | `MOD04_3K` / `MYD04_3K` (v6.1) |

Helpers: `_common.py` (bbox de Chile, `.env`, logging, reintentos) · `_env_earthdata.py`
(autenticación earthaccess + `buscar_y_descargar` + tope `LIMITE_MBPS`) ·
`_recorte_tropomi.py` (recorte de gránulos L2 a un bbox).

### Recorte a Chile al vuelo (TROPOMI y MERRA-2)

Estas dos fuentes sirven **gránulos globales**: una órbita completa de polo a polo
(TROPOMI, ~600 MB) o el planeta entero (MERRA-2, ~470 MB), de los que solo ~5% cae
sobre Chile. Sin recortar, TROPOMI ocuparía ~13 TB y MERRA-2 ~1 TB.

Ambos descargadores bajan cada gránulo a `_tmp_global/`, lo recortan a
`raw_chile/` y **borran el global de inmediato**, así que nunca conviven dos
copias completas. El recorte conserva todas las variables, todos los grupos y la
resolución nativa: solo desaparece la geografía fuera de `CHILE_BBOX` (verificado
variable a variable contra el original). Resultado: ~4-5% del tamaño.

- Si una corrida se interrumpe, la siguiente recorta primero el backlog de
  `_tmp_global/` y sigue. Es seguro relanzar: salta lo ya recortado.
- `python descargar_tropomi.py --solo-recortar` procesa el backlog y termina.
- Los gránulos que CMR devuelve pero cuyos píxeles no alcanzan Chile se marcan
  con un centinela `.vacio` para no volver a descargarlos.

### Limitar el ancho de banda

`LIMITE_MBPS=50` en `../.env` topea el promedio de descarga de las fuentes
Earthdata (pacing por gránulo). Coméntala o bórrala para ir a full.

### Cómo correr

```bash
# todo, en orden (una fuente a la vez):
DESDE=2019-01-01 HASTA=2024-12-31 bash lanzar_descargas.sh

# o un descargador suelto (prueba sin bajar nada):
python descargar_tropomi.py --contaminantes no2 --desde 2023-06-01 --hasta 2023-06-03 --dry-run
python descargar_sinca.py --limite 3 --dry-run

# con reintentos (CMR/GES DISC devuelven 500 intermitentes):
bash correr_con_reintentos.sh python descargar_mopitt.py --desde 2005-01-01 --hasta 2024-12-31
```

### Notas

- **Cobertura temporal por fuente:** TROPOMI 2018-04+ · OMI 2004-10+ · MOPITT 2000-03+ ·
  CAMS EAC4 2003+ · GEOS-CF 2018-01+ · ACAG anual/mensual histórico. Para un histórico largo
  de gases combina OMI/MOPITT/CAMS; TROPOMI aporta el detalle fino reciente.
- **`descargar_sinca.py`** usa los códigos de parámetro SINCA/Airviro (`PARAM_CODES`): PM25,
  PM10, SO2=0001, NO2=0003 (confirmados), O3/CO estándar; si un gas no baja en una estación,
  verifica su código en la ficha SINCA. El exportador es lento (timeout 120 s por serie).
- Las descargas satelitales/reanálisis tardan **horas o días** y pesan mucho: todo `data/`
  está en `.gitignore`.

---

<a id="english"></a>
## 🇬🇧 English

Reproducible downloaders for the exposure inputs of all 6 pollutants
(**PM2.5, PM10, NO2, O3, SO2, CO**). Each script writes under
`../data/contaminantes/<SOURCE>/` (satellite/reanalysis) or `../data/sinca/<pol>/` (ground
truth) and accepts `--desde/--hasta` (YYYY-MM-DD) and `--dry-run`. See the Spanish table above
for the per-source product identifiers (all verified against CMR/ADS/S3). Install
`requirements.txt`, copy `../.env.example` to `../.env` and fill the credentials (NASA Earthdata
+ Copernicus ADS; ACAG/SINCA/GEOS-CF need none). Run everything in order with
`bash lanzar_descargas.sh`, or a single downloader with `--dry-run` first.
