# Auditoría de resolución, recorte y almacenamiento

Fecha de corte: 2026-09-02.

## Regla de conservación

El almacén final conserva únicamente la versión reproducible de mayor
resolución **nativa útil** de cada producto seleccionado. La ingesta no
promedia por comuna, estación, día ni hora. Cada observación mantiene su píxel
o huella, calidad, incertidumbre cuando existe y tiempo nativo.

Chile se procesa como cinco áreas separadas: continente, Juan Fernández,
Desventuradas, Rapa Nui y Sala y Gómez. La Antártica queda fuera. Esta división
evita descargar o conservar el corredor oceánico de una caja continental única.
La máscara administrativa contiene 345 comunas y una zona oficial sin demarcar
(`cod_comuna=0`); por eso algunos catálogos tienen 346 códigos, no 346 comunas.

"Máxima resolución temporal" no significa inventar 24 observaciones diarias:

- SINCA, ERA5/ERA5-Land, MERRA-2 y GEOS-CF conservan horas reales cuando la
  fuente es horaria.
- MODIS, MAIAC, TROPOMI, OMI y MOPITT conservan la hora exacta de cada pasada.
- Black Marble A2 es diario, DMSP LEN conserva cada segmento orbital nocturno,
  ACAG es mensual y ESA CCI es anual.
  Esos productos se enlazan después al modelo, sin rotularlos como horarios.

## Estado de los productos

| Producto maestro | Resolución nativa conservada | Periodo objetivo/disponible | Estado al corte |
|---|---|---|---|
| SINCA | Horaria por estación | 2000–2026 según inicio real de cada serie | Automatizado; 109 estaciones georreferenciadas y control de hora local/DST |
| MOD04_3K/MYD04_3K | 3 km al nadir; tiempo de escaneo | Terra 2000-02-24+; Aqua 2002-07-04+ | Descarga 2000–2026 activa; píxel/pasada, sin agregado comunal |
| MCD19A2 MAIAC | 1 km; `Orbit_time_stamp` | 2000-02-24+ | Descarga 2000–2026 activa; catálogo de píxeles y observaciones por pasada |
| Sentinel-5P TROPOMI L2 | Huella L2 nativa; UTC por scanline/píxel | 2018+ | Migración NO2 activa; descargador preparado para NO2/O3/SO2/CO y cinco AOI |
| Aura OMI L2 | Huella ~13×24 km al nadir; TAI93 convertido a UTC | 2004-10+ | Descargador y prueba real validados; L3 global eliminado |
| Terra MOPITT L2 v10 | Retrieval/pasada ~22 km | 2000-03-03–2025-02-01 | Descargador y prueba real validados; L3 global eliminado |
| ACAG V6GL03 | 0,01° mensual, cada píxel | 2000–2024 disponible | Completo: 300 meses y 900 recortes; la fuente sudamericana no cubre Rapa Nui/Sala y Gómez |
| ERA5 BLH | 0,25° horario | 2000–2026 disponible | 318 meses normalizados; junio de 2026 está marcado explícitamente como parcial |
| ERA5-Land | 0,1° horario | 2000–disponible en CDS | Descarga/migración activa; seis variables meteorológicas y precipitación; retiro legado separado y bloqueado mientras corre |
| MERRA-2 meteo/aerosol | 0,5°×0,625° horario | 2000+ según colección | Normalizador chileno y manifiestos implementados |
| CAMS EAC4 | 0,75° cada 3 h | 2003+ | Normalizador chileno implementado; no se interpola durante la ingesta |
| GEOS-CF | 0,25° horario | 2018+ | Normalizador chileno implementado |
| World Bank LEN DMSP-OLS | Grilla publicada de 30 arc-sec; cada segmento orbital nocturno, UTC inicial | 2000-01-01–2012-01-18 para el proyecto | Fuente S3 pública sin cuenta; descargador por ventanas Chile automatizado; descarga nacional pendiente de turno/espacio |
| VIIRS Black Marble A1+A2 | 15 arc-sec (~500 m); A1 aporta `UTC_Time`, A2 compuesto diario | 2012-01-19+ | Descargador y prueba real validados; descarga nacional activa |
| ESA CCI Land Cover | 300 m anual | 2000–2022 disponible | Completo: 23 años × 5 AOI = 115 GeoTIFF; ~70 MB con manifiesto |
| NASADEM HGT v001 | 1 arc-sec (~30 m), estático | Misión SRTM/NASADEM | 163 teselas chilenas identificadas; prueba real aprobada; descarga nacional pendiente |

En DMSP, 30 arc-sec describe el espaciado de la grilla COG publicada, no una
huella óptica independiente de 1 km. Light Every Night entrega OIS *smooth*, con
distancia de muestreo nominal de 2,7 km y resolución/IFOV nocturna efectiva
aproximada de 4,9 km. La alternativa *fine* de
0,55 km fue regional/limitada y no forma una serie nocturna abierta, continua y
homogénea para Chile 2000–2011; por eso no se mezcla con el maestro LEN.

Las relaciones píxel–comuna son muchos-a-muchos cuando una huella toca más de
una comuna. Se conserva cada píxel: una comuna puede tener dos, diez o miles de
píxeles según la resolución del sensor. `crear_enlaces_pixeles.py` construye el
enlace reversible a las estaciones SINCA con distancia, rango y diferencia
temporal, sin convertir ese enlace en la copia maestra.

## Pruebas reales representativas

- MODIS Terra, 2000-02-24: 6.302 píxeles, 116 tiempos UTC y 215 comunas; una
  comuna alcanza 129 píxeles. Los seis HDF de origen quedaron registrados por
  SHA-256 y se eliminaron tras validar la salida.
- MAIAC Terra, 2000-02-24: 255.758 observaciones píxel/pasada y tres pasadas.
  El catálogo tiene 880.219 píxeles únicos y cubre 345 comunas más la zona 0.
- OMI L2: pruebas NO2, SO2 y O3 conservaron huellas, hora exacta y QA.
- MOPITT L2: 1.171 retrievals, 236 comunas y hora UTC 03:36:57–14:49:22, con
  perfiles, errores, kernels y QA.
- Black Marble, 2024-01-15: 12 tiles físicos, 15 recortes territoriales y
  4.696.628 píxeles cuya huella toca Chile. A1 conserva radiancia, UTC por
  píxel y QA; A2 conserva radiancia BRDF y QA diaria.
- ESA CCI: cada año conserva 10.475.658 píxeles cuya huella toca Chile; todas
  las unidades administrativas tienen centros de píxel.

## Limpieza ejecutada

Se eliminaron permanentemente, después de comprobar su sustitución o su falta
de procedencia:

- grillas globales L3 de OMI y MOPITT (aproximadamente 85 GiB en conjunto);
- rectángulos ERA5 BLH antiguos (11,504 GiB) después de validar los 318 meses;
- ACAG V6 anterior, fuentes regionales V6GL03 ya recortadas y copias anuales
  redundantes; el resultado mensual chileno ocupa ~904 MB;
- agregados comunales de MODIS/MAIAC que habían perdido los píxeles nativos;
- compuestos mensuales MERRA-2 redundantes cuando existe la serie horaria;
- SINCA diario, conservando la resolución horaria;
- 31 rectángulos LULC y las salidas 1992–1999 fuera del alcance analítico;
- Nightlights armonizado sin fuente/unidades verificables;
- archivos de prueba OMI/MOPITT y un DEM rectangular de 0,01° reemplazable por
  NASADEM 30 m.

El volumen pasó de aproximadamente 498 GiB usados a 385 GiB aun mientras las
nuevas descargas crecían: la recuperación neta observada es de ~113 GiB. No se
elimina un TROPOMI legado ni una fuente de reanálisis hasta que su reemplazo
chileno se reabra, valide y quede registrado.

`topografia_comunal.csv` se mantiene de forma intencional: todavía tiene
consumidores activos. Se retirará únicamente después de completar NASADEM y
migrar esos lectores.

ERA5-Land conserva temporalmente unos 68 GiB en `raw_chile` mientras la
descarga nativa está activa. `retirar_legado_era5land.py` se ejecuta después:
comparte el bloqueo del descargador, rechaza meses parciales y sólo retira una
fuente cuya ruta y SHA-256 estén en el manifiesto de una salida mensual completa
reabierta. La simulación `--dry-run` no escribe ni elimina nada; la ejecución
real deja una auditoría JSONL durable.

## Contrato reproducible de cada descargador

1. Consultar la fuente y registrar producto, versión, URL, periodo y AOI.
2. Descargar el HDF/NetCDF/GeoTIFF global o regional a un staging del producto.
3. Recortar en resolución nativa, conservar tiempo/QA y crear la asociación
   píxel–comuna sin promediar.
4. Escribir primero como `.part`, cerrar, reabrir y validar esquema, conteos,
   rangos físicos, timestamps y cobertura territorial.
5. Publicar por reemplazo atómico y registrar SHA-256 de fuente, salida, máscara
   administrativa y versión del descargador.
6. Borrar el crudo y los temporales solo después de todas las validaciones. Si
   algo falla, conservar la fuente recuperable o marcar el intento incompleto.

Los runners usan 2000-01-01 como inicio general, dejan que cada fuente aplique
su fecha nativa y terminan en la fecha de ejecución. Son idempotentes: omiten
salidas ya validadas, reintentan ausencias transitorias y reservan como mínimo
100 GiB libres en el volumen externo.

## Proyección del disco externo

El volumen tiene 931 GiB (~1 TB comercial). Al corte usa 470 GiB y deja 461
GiB libres; AirPollution representa ~419 GiB y los otros contenidos del disco
~51 GiB.

| Componente futuro dominante | Proyección probable | Techo prudente |
|---|---:|---:|
| Black Marble A1+A2 diario 2012–2026 | ~359 GiB | ~380 GiB |
| TROPOMI compacto, cuatro gases | ~40–80 GiB | ~220 GiB hasta medir todos los gases |
| MAIAC píxel/pasada | ~23–32 GiB | ~47 GiB |
| ERA5-Land chileno final | ~22 GiB | ~25 GiB |
| MERRA-2/CAMS/GEOS-CF + ERA5 BLH | ~4,2 GiB | ~6 GiB |
| MODIS 3K | ~1,4–2 GiB | ~10 GiB |
| OMI L2 + MOPITT L2 | ~7–14 GiB | ~18 GiB |
| DMSP LEN orbital 2000-01-01–2012-01-18 | ~65–85 GiB | ~90 GiB |
| LULC + NASADEM | ~1–2,4 GiB | ~2,5 GiB |

La proyección **total del volumen**, incluyendo los ~45 GiB ajenos al proyecto,
tiene ahora un centro aproximado de 610 GiB y un rango probable de 585–700 GiB
usados (628–752 GB decimales), por lo que quedarían 231–346 GiB libres. Para
planificación se adopta un techo deliberadamente conservador de 830 GiB usados
(891 GB), que todavía deja ~101 GiB. El límite automático de 100 GiB impide que
una extrapolación desfavorable llene el disco.

La incertidumbre principal es Black Marble diario, seguido por la compresión
real de los cuatro gases TROPOMI y el volumen Aqua de MAIAC. Estas cifras deben
actualizarse desde los manifiestos cuando cierren las corridas completas.
