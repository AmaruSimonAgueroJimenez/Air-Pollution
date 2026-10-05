# scripts_pipeline/ — Descarga de datos por contaminante · Data download pipeline

> ↩ [README principal](../README.md) · 🧩 [scripts_superficie/](../scripts_superficie/README.md)

**Idioma / Language:** 🇪🇸 Español · 🇬🇧 [English below](#english)

---

<a id="español"></a>
## 🇪🇸 Español

Descargadores **reproducibles** de los insumos de exposición para los 6 contaminantes
(**PM2.5, PM10, NO2, O3, SO2, CO**). Cada script resuelve sus rutas de forma absoluta y
escribe bajo `$AIR_POLLUTION_DATA_ROOT/contaminantes/<FUENTE>/` (satélite/reanálisis) o
`$AIR_POLLUTION_DATA_ROOT/sinca/<pol>/` (verdad-terreno). Si la variable no está definida,
usa `$ASESORIAS_DATA_ROOT/AirPollution/data`, con `/Volumes/Datos/Asesorias_Data` como raíz
común predeterminada. El código y `output_files/` permanecen en el repo. Todos aceptan
`--desde/--hasta` (YYYY-MM-DD) y `--dry-run`.

Si se usa la ruta predeterminada y `/Volumes/Datos` no está montado, los descargadores
abortarán antes de crear carpetas; una ruta definida explícitamente mediante
`AIR_POLLUTION_DATA_ROOT` siempre tiene prioridad.

### Preparación reproducible para modelos

La transformación de datos locales tiene un punto de entrada independiente:
[`preparar_datos_modelado.py`](preparar_datos_modelado.py). Coordina los
conversores de MERRA-2 meteorológico, SINCA y precipitación ERA5-Land, con
validación, versiones y procedencia. Conserva horas y píxeles nativos; no
descarga, imputa, promedia por comuna, entrena ni elimina fuentes.

Desde la raíz del proyecto, este comando **sólo muestra el plan**:

```sh
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -B scripts_pipeline/preparar_datos_modelado.py \
  --merra-hasta 2026-05 --sinca-hasta 2026-09-13 --era-hasta 2026-09
```

El alcance anterior ya fue transformado; no es necesario volver a ejecutarlo
para empezar a inspeccionar los productos. Añadir `--ejecutar` activa una
ejecución explícita; consultar antes la
[guía de preparación](../docs/PREPARACION_MODELADO.md) para rutas, selección de
versiones, dependencias y límites. SINCA aún necesita confirmar unidades,
reloj y etiqueta del intervalo antes del cruce horario definitivo. Los
satélites se conservan en sus publicaciones nativas, sin otra copia masiva ni
observaciones horarias inventadas. Las opciones de esta sección no son las
de los descargadores descritos a continuación.

### Red adicional publicada en SNIFA

[`descargar_snifa.py`](descargar_snifa.py) y
[`preparar_snifa_modelado.py`](preparar_snifa_modelado.py) recuperan los gases de
El Peñón, Charrúa, Progreso, SAPU y Quinel como `snifa_adicional`, con originales,
trazabilidad y productos separados de SINCA en el disco externo. El lanzador
[`ejecutar_snifa.sh`](ejecutar_snifa.sh) ejecuta ambas etapas. Consultar
[instalación, ejecución y límites](../docs/RED_ADICIONAL_SNIFA.md), especialmente
PDF escaneados, unidades y reloj pendiente de validar antes del cruce por UTC.

### Requisitos

```bash
pip install -r requirements.txt          # earthaccess, cdsapi, xarray, boto3, ...
cp ../.env.example ../.env                # y completa las credenciales
```

Credenciales (en `../.env`): **NASA Earthdata** (TROPOMI, OMI, MOPITT, MERRA-2, MODIS)
y **Copernicus ADS** (CAMS EAC4). ACAG PM2.5 y DMSP Light Every Night usan
buckets S3 **públicos**, sin cuenta ni tarjeta; SINCA y GEOS-CF tampoco requieren
credenciales. El descargador mensual EOG de pago queda sólo como legado opt-in.

### Descargadores (identificadores verificados en CMR/ADS/S3)

| Script | Fuente / producto | Contaminante(s) | ID verificado |
|---|---|---|---|
| `descargar_sinca.py` | SINCA (exportador `tsindico2`) | PM2.5,PM10,NO2,O3,SO2,CO | 109 estaciones (`config/sinca/config_sinca_estaciones.json`); `macro` único con ruta completa y sufijo `.ic` |
| `descargar_cams_eac4.py` | CAMS reanálisis EAC4 (ADS) | NO2,O3,SO2,CO,PM2.5,PM10 | `cams-global-reanalysis-eac4` (0,75°, 3-h, nivel modelo 60 para gases; 2003–último año publicado) |
| `descargar_geoscf.py` | NASA GEOS-CF (OPeNDAP) | O3,NO2,SO2,CO,PM2.5 | v1 `aqc_tavg_1hr_g1440x721_v1` hasta 2025 + v2 `aqc_tavg_1hr_glo_L1440x721_slv` desde 2026 (0,25°, horario HH:30) |
| `descargar_tropomi.py` | Sentinel-5P TROPOMI L2 (GES DISC) | NO2,O3,SO2,CO | `S5P_L2__NO2____HiR` · `…O3_TOT_HiR` · `…SO2____HiR` · `…CO_____HiR` (v2); recorta a Chile al vuelo |
| `descargar_omi_l2.py` | Aura OMI L2 píxel/pasada, 13×24 km nadir | NO2,O3,SO2 | `OMNO2` · `OMTO3` · `OMSO2` (v004); TAI93 exacto, huellas y QA |
| `descargar_mopitt_l2.py` | Terra MOPITT L2 retrieval/pasada, ~22 km | CO | `MOP02J` (collection `10`); perfil, error, kernels y QA; termina 2025-02-01 |
| `descargar_acag_pm25.py` | ACAG SatPM2.5 superficie (S3 público) | PM2.5 | `s3://satpmdata/` · V6GL03 (CNNPM25, FineResolution/SA) |
| `descargar_dmsp_len.py` | World Bank Light Every Night / DMSP-OLS | luces nocturnas | 2000-01-01→2012-01-18; todos los segmentos nocturnos de F14/F15/F16/F18; grilla publicada 30 arc-sec; UTC inicial, DN visible, iluminación lunar, posición transversal y QA; S3 público |
| `descargar_nightlights.py` | VIIRS Black Marble diario | radiancia nocturna | VNP46A1 (hora UTC por píxel + radiancia al sensor) y VNP46A2 (radiancia BRDF diaria); colección 002, 15 arc-sec |
| `../scripts_superficie/extractores/descargar_era5land.py` | ERA5-Land | meteorología | 0,1°, horario UTC, cinco AOI y relación píxel-comuna |
| `retirar_legado_era5land.py` | Limpieza ERA5-Land posterior | — | Revalida mes completo, catálogo y hashes; retira sólo fuentes declaradas en el manifiesto |
| `descargar_merra2_meteo.py` | MERRA-2 combinado | meteorología + AOD + PM2.5 | `M2T1NXSLV` + `M2T1NXFLX` + `M2T1NXAER` (v5.12.4, 0,5×0,625°, horario HH:30); reutiliza el legado y evita duplicar AOD/PM |
| `descargar_merra2_aer.py` | MERRA-2 aerosoles (opcional, no se lanza junto al combinado) | AOD + PM2.5 | `M2T1NXAER` (v5.12.4, 0,5×0,625°, horario HH:30); recorta a Chile al vuelo |
| `descargar_maiac_aod.py` | MODIS MAIAC AOD 1 km | (predictor PM) | `MCD19A2` (v061) |
| `descargar_modis_aod.py` | MODIS AOD 3 km (Terra/Aqua) | (predictor PM) | `MOD04_3K` / `MYD04_3K` (v6.1) |
| `descargar_goes_abi_aod.py` | GOES-East ABI L2 AOD disco completo (NOAA NODD, S3 público) | (predictor PM, horario diurno) | `ABI-L2-AODF` en `noaa-goes16` (hasta 2025-04-06) y `noaa-goes19` (desde 2025-04-07); grilla fija 2 km, cada escaneo de 10 min (modo 6), sólo celdas cuya huella toca Chile; ver [`others_files/20260918_nota_goes_abi_aod_nativo_v2.md`](../others_files/20260918_nota_goes_abi_aod_nativo_v2.md) |

Los antiguos `descargar_omi.py` (L3 diario) y `descargar_mopitt.py` (L3 1°)
quedan deshabilitados salvo `--permitir-l3-legado`; no forman parte de la
descarga reproducible ni deben conservarse en el disco final.

Helpers: `_common.py` (compatibilidad, `.env`, logging, reintentos) · `_chile_aoi.py`
(AOI derivados de los 346 polígonos administrativos: 345 comunas y
`cod_comuna=0`, incluida la parte insular; sin Antártica) · `_env_earthdata.py`
(autenticación earthaccess + `buscar_y_descargar` + tope `LIMITE_MBPS`) ·
`_recorte_tropomi.py` (recorte de gránulos L2 a un bbox).

### Reanálisis en la grilla nativa, sin corredor oceánico

`normalizar_reanalisis_chile.py` es el contrato común de MERRA-2, CAMS EAC4 y
GEOS-CF. Conserva la cadencia UTC y la resolución espacial nativas, selecciona
toda celda cuya huella intersecta Chile administrativo y publica un NetCDF
mensual `time × pixel`, un catálogo estable y la relación muchos-a-muchos
píxel↔comuna. Incluye continente, Juan Fernández, Desventuradas, Rapa Nui y
Sala y Gómez; excluye Antártica. No interpola, remuestrea, promedia por comuna
ni conserva el rectángulo oceánico entre Chile continental y Rapa Nui.

El contrato transaccional escribe primero `*.part`, reabre y valida cobertura,
cadencia y hashes, y solo entonces publica. Los cinco AOI de adquisición se
eliminan después de validar el mes final. Las fuentes rectangulares legadas no
se eliminan por defecto: su retiro requiere el indicador explícito del producto
y un reemplazo completo reabierto y verificado; un mes parcial nunca autoriza
limpieza. La reserva mínima predeterminada es 100 GiB.

Catálogos derivados de `comunas.shp`: MERRA-2, 419 celdas nativas y 1.298
relaciones; CAMS EAC4, 268 y 1.030; GEOS-CF, 1.780 y 3.377. Los tres conservan
las 346 unidades administrativas, incluido `cod_comuna=0`.

### Recorte administrativo a Chile al vuelo

Estas dos fuentes sirven **gránulos globales**: una órbita completa de polo a polo
(TROPOMI, ~600 MB) o el planeta entero (MERRA-2, ~470 MB), de los que solo ~5% cae
sobre Chile. Sin recortar, TROPOMI ocuparía ~13 TB y MERRA-2 ~1 TB.

Los descargadores bajan cada gránulo a un directorio temporal, generan salidas
separadas para continente, Juan Fernández, Desventuradas, Rapa Nui y Sala y
Gómez, validan su contenido y **solo entonces** borran el global. La máscara se
deriva de `data/comunas.shp`; `cod_comuna=-1` significa fuera de Chile y el
código administrativo 0 se conserva. TROPOMI mantiene todos los píxeles/huellas,
hora nativa, órbita, scanline y ground-pixel: no agrega a comuna ni interpola a
horario. ACAG mantiene cada píxel mensual de 0,01° y Black Marble cada píxel
diario de 15 arc-sec. Las asociaciones muchos-a-muchos píxel-comuna y el enlace
con `data/sinca/estaciones_georreferenciadas.csv` se generan aparte con
`crear_enlaces_pixeles.py`.

- Si una corrida se interrumpe, la siguiente recorta primero el backlog de
  `_tmp_global/` y sigue. Es seguro relanzar: salta lo ya recortado.
- `python descargar_tropomi.py --solo-recortar` procesa el backlog y termina.
- Los gránulos que CMR devuelve pero cuyos píxeles no alcanzan ningún AOI se marcan
  con un centinela `.vacio` para no volver a descargarlos.

VNP46A2 es un compuesto de 24 horas y no contiene una hora de pasada exacta.
El modo diario de `descargar_nightlights.py` lo empareja por
`fecha + tile + pixel_id` con VNP46A1, cuya variable `UTC_Time` sí conserva la
hora nativa por píxel. Nunca se interpola un producto diario/mensual a horario.

La brecha anterior a VIIRS se cubre con **World Bank Light Every Night (LEN)**,
un archivo público en AWS basado en NOAA/NCEI. `descargar_dmsp_len.py` conserva
2000-01-01→2012-01-18 a la máxima temporalidad disponible: cada segmento orbital
nocturno de todos los satélites publicados, no un promedio mensual. Mantiene la
grilla publicada de 30 arc-sec sin remuestreo, el UTC inicial del segmento (no
una hora exacta por píxel), DN visible, iluminación lunar, posición transversal
y banderas QA. La separación de la grilla no debe confundirse con detalle óptico
independiente de 1 km: LEN publica OIS *smooth*, con distancia de muestreo
nominal de 2,7 km y resolución/IFOV nocturna efectiva aproximada de 4,9 km.
No se encontró una serie nocturna *fine* homogénea y reproducible para Chile
2000–2011. El programa consulta
el STAC anónimo y lee sólo ventanas COG que tocan las cinco AOI; nunca almacena
los GeoTIFF globales. Los Parquet se publican y reabren atómicamente, quedan
vinculados muchos-a-muchos con las comunas, y todo parcial se elimina. El
descargador mensual EOG permanece sólo como alternativa legada de pago y no se
ejecuta en los runners.

La salida nacional larga se estima en **65–85 GiB** (aproximadamente 70–91 GB
decimales), incluidos observaciones, catálogos, estados y manifiestos. El
descargador informa esta proyección y exige 100 GiB libres antes de continuar.

### Limitar el ancho de banda

`LIMITE_MBPS=50` en `../.env` topea el promedio de descarga de las fuentes
Earthdata (pacing por gránulo). Coméntala o bórrala para ir a full.

### Cómo correr

```bash
# todo, en orden (una fuente a la vez):
# por defecto: 2000-01-01 hasta la fecha de ejecución
bash lanzar_descargas.sh

# o un descargador suelto (prueba sin bajar nada):
python descargar_tropomi.py --contaminantes no2 --desde 2023-06-01 --hasta 2023-06-03 --dry-run
python descargar_omi_l2.py --desde 2004-10-01 --hasta 2004-10-02 --dry-run
python descargar_mopitt_l2.py --desde 2000-03-03 --hasta 2000-03-04 --dry-run
python descargar_dmsp_len.py --desde 2000-01-01 --hasta 2011-12-31 --dry-run
python descargar_sinca.py --limite 3 --dry-run
python descargar_merra2_meteo.py --desde 2000-01 --hasta 2026-06 --dry-run
python descargar_cams_eac4.py --desde 2003-01 --hasta 2025-12 --dry-run
python descargar_geoscf.py --desde 2018-01 --hasta 2026-09 --dry-run
# GOES-East ABI AOD: plan sin red; prueba real de un escaneo; histórico horario
python descargar_goes_abi_aod.py --dry-run
python descargar_goes_abi_aod.py --desde 2023-10-05 --hasta 2023-10-05 --max-escaneos-por-dia 1
python descargar_goes_abi_aod.py --cadencia horaria --desde 2019-01-01 --hasta 2024-12-31

# ERA5-Land: simular primero el retiro del legado; el borrado real se ejecuta
# únicamente después de que descargar_era5land.py haya terminado.
python retirar_legado_era5land.py --desde 2000-01 --hasta 2026-09 --dry-run
python retirar_legado_era5land.py --desde 2000-01 --hasta 2026-09

# reconstruir el maestro geográfico y sus fuentes; no usa red si el cache está completo:
python actualizar_geometria_sinca.py
python actualizar_geometria_sinca.py --offline

# auditar las descargas SINCA locales y corregir sus manifiestos:
python descargar_sinca.py --validar-local --reconciliar-manifiestos

# con reintentos (CMR/GES DISC devuelven 500 intermitentes):
bash correr_con_reintentos.sh python descargar_mopitt_l2.py --desde 2005-01-01 --hasta 2024-12-31
```

### Notas

- **Cobertura temporal por fuente:** GOES-East ABI AOD 2017-12-18+ · TROPOMI 2018-04+ · OMI L2 2004-10+ · MOPITT L2 2000-03-03–2025-02-01 ·
  CAMS EAC4 2003–último año publicado · GEOS-CF v1 2018–2025 + v2 2026+ · ACAG anual/mensual histórico. Para un histórico largo
  de gases combina OMI/MOPITT/CAMS; TROPOMI aporta el detalle fino reciente.
- **GOES-East ABI AOD:** única fuente con cadencia sub-horaria sobre Chile (cada 10 min desde
  abril de 2019, 15 min antes). Sólo diurna y sólo sobre superficies oscuras (sin desierto ni
  nieve); píxel de 2 km al nadir que crece a ~4 km en Magallanes. Los escaneos con todo Chile
  de noche se omiten sin descargarlos; el tiempo es el del escaneo, no por píxel. Cadencia
  `nativa`, `30min` u `horaria` sin sustituir faltantes; `--enlaces` calcula los enlaces
  píxel↔comuna con huella exacta (≈1 min, una vez por grilla; 151 mil enlaces, 109 estaciones).
- **Resolución temporal satelital:** OMI y MOPITT conservan la hora UTC exacta
  de cada pasada; no son observaciones cada hora. Los Parquet mantienen todos
  los píxeles/huellas que tocan Chile y múltiples píxeles por comuna, sin
  promedios prematuros. El HDF global se borra sólo después de reabrir y
  validar la salida chilena.
- **Limpieza ERA5-Land:** los runners colocan `retirar_legado_era5land.py`
  inmediatamente después del descargador. El limpiador comparte su bloqueo,
  exige 100 GiB libres, rechaza meses parciales y sólo elimina un NetCDF de
  `raw_chile` si su ruta, tamaño y SHA-256 figuran en el manifiesto de una
  salida mensual completa que acaba de reabrir y validar. `--dry-run` no crea
  locks, auditorías ni archivos.
- **`descargar_sinca.py`** usa los códigos de parámetro SINCA/Airviro (`PARAM_CODES`): PM25,
  PM10, SO2=0001, NO2=0003 (confirmados), O3/CO estándar; si un gas no baja en una estación,
  verifica su código en la ficha SINCA. El exportador es lento (timeout 120 s por serie).
  Algunas respuestas son plantillas largas con todas las mediciones vacías: ahora se
  clasifican como **sin datos**. La auditoría conserva ruta, tamaño, SHA-256 y razón en
  `data/sinca/metadata/series_sin_observaciones.csv`.
  El catálogo pequeño de estaciones se versiona en `config/sinca/`; las fichas
  HTML y los dos informes PDF MMA que corrigen coordenadas defectuosas se
  conservan en el disco externo con SHA-256. El maestro resultante incluye la
  coordenada WGS84, comuna geométrica y banderas de control de calidad.
  La semántica horaria se versiona en `config/sinca/politica_temporal.json`:
  el manifiesto de cada serie guarda su SHA-256, la versión del descargador y
  el hash del catálogo de estaciones. El lector heredado conserva la etiqueta
  local, marca conflictos DST y aplica zonas IANA regionales; esa conversión
  **no acredita el reloj real del exportador**. Para la nueva preparación usar
  `preparar_sinca_modelado.py`, que deja `ts_utc` nulo y conserva los candidatos
  como hipótesis hasta confirmar reloj, intervalo y unidades. Véase
  [la evidencia pendiente](../docs/SINCA_SEMANTICA_PENDIENTE.md).
- Las descargas satelitales/reanálisis tardan **horas o días** y pesan mucho: todo `data/`
  está en `.gitignore`.

---

<a id="english"></a>
## 🇬🇧 English

Reproducible downloaders for the exposure inputs of all 6 pollutants
(**PM2.5, PM10, NO2, O3, SO2, CO**). Each script writes under
`$AIR_POLLUTION_DATA_ROOT/contaminantes/<SOURCE>/` (satellite/reanalysis) or
`$AIR_POLLUTION_DATA_ROOT/sinca/<pol>/` (ground truth). The fallback is
`$ASESORIAS_DATA_ROOT/AirPollution/data`, using `/Volumes/Datos/Asesorias_Data` as the
default shared root; code and `output_files/` stay in the repository. All downloaders accept
`--desde/--hasta` (YYYY-MM-DD) and `--dry-run`. See the Spanish table above
for the per-source product identifiers (all verified against CMR/ADS/S3). Install
`requirements.txt`, copy `../.env.example` to `../.env` and fill the credentials (NASA Earthdata
and Copernicus ADS; World Bank LEN DMSP, ACAG, SINCA and GEOS-CF need none). Run everything in order with
`bash lanzar_descargas.sh`, or a single downloader with `--dry-run` first. SINCA responses
whose measurement fields are entirely empty are classified as unavailable; audit existing
files with `python descargar_sinca.py --validar-local --reconciliar-manifiestos`.
