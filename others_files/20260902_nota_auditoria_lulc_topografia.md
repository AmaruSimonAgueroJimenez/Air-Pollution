# Auditoría reproducible: cobertura de suelo y topografía

Fecha de verificación: 2026-09-02.

## Decisión de producto

La serie elegida de cobertura de suelo se mantiene en **ESA CCI/C3S Land
Cover**, versión 2.0.7cds (hasta 2015) y 2.1.1 (desde 2016). Su resolución
nativa es 1/360 de grado (aproximadamente 300 m) y su frecuencia nativa es
anual. Para el alcance analítico se conservan los años **2000–2022**. El
catálogo máquina-a-máquina del CDS sólo ofrece hasta 2022 al momento de esta
auditoría, aunque el título de la portada diga “hasta el presente”.
Los años 1992–1999, aunque existen en el producto, se retiraron del disco
porque el alcance solicitado comienza en 2000 y ningún código del análisis los
referenciaba.

Este criterio significa “máxima resolución nativa del producto elegido”. No
se mezcla la serie con Dynamic World por escena, pues hacerlo cambiaría clases,
algoritmo, sensores y período, además de multiplicar el volumen sin aportar
una serie homogénea desde 2000. Las fuentes oficiales consultadas son:

- CDS ESA CCI/C3S Land Cover: <https://cds.climate.copernicus.eu/datasets/satellite-land-cover>
- Catálogo CDS verificable: <https://cds.climate.copernicus.eu/api/catalogue/v1/collections/satellite-land-cover>
- Dynamic World (comparación, no seleccionado): <https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1>
- Copernicus LCFM 10 m (por ahora sólo 2020 publicado): <https://land.copernicus.eu/en/products/global-dynamic-land-cover>

## Problema encontrado y corrección

Los 31 archivos heredados `ESA_CCI_AAAA_chile.tif` sí preservaban 300 m y los
años 1992–2022, pero no eran un recorte administrativo. Cada archivo tenía
15.660 × 14.040 = 219.866.400 celdas en el rectángulo -109,5°…-66° y
-56°…-17°. En 2022 sólo 10.475.658 celdas tocaban Chile; 209.390.742 celdas
(95,2 %) quedaban fuera de la geometría administrativa.

El descargador `scripts_pipeline/descargar_lulc_esa_cci.py` ahora:

1. consulta el inventario oficial de años/versiones del CDS;
2. descarga o reutiliza una fuente local con hash SHA-256;
3. conserva `lccs_class` a 1/360°, sin remuestreo;
4. separa continente, Juan Fernández, Desventuradas, Rapa Nui y Sala y Gómez;
5. conserva toda celda cuya huella toca la máscara administrativa;
6. valida cinco salidas, cobertura de 345 comunas más código 0 y al menos dos
   centros de píxel por unidad;
7. compara valores y máscara píxel a píxel; y
8. sólo entonces elimina el rectángulo fuente y cualquier temporal.

Una prueba completa de 2022 produjo 10.475.658 celdas de huella chilena. Las
346 unidades quedaron representadas, con un mínimo de 80 centros de píxel por
unidad. Las cinco salidas ocuparon aproximadamente 2,8 MB frente a 5,8 MB del
rectángulo anterior. La colección final 2000–2022 contiene 115 GeoTIFF (cinco
por año) y, junto con su manifiesto, ocupa aproximadamente **70 MB**.

## Topografía

El único insumo previo era `topografia_comunal.csv` (346 filas, 15,7 KB) con
altitud, TPI, TRI, pendiente y distancia a costa ya agregados por comuna. No
existía raster nativo, hash de fuente ni manifiesto; por ello no demuestra
máxima resolución ni permite mantener varios píxeles dentro de una comuna.
Se conserva temporalmente porque el análisis actual todavía lo consume.

Se eligió **NASADEM HGT v001**: altura en metros, entero de 16 bits, a un
segundo de arco (aproximadamente 30 m), con referencia vertical EGM96. Es una
superficie estática basada principalmente en la misión SRTM de febrero de
2000; no corresponde asignarle resolución horaria. Fuentes oficiales:

- DOI y colección: <https://doi.org/10.5067/MEaSUREs/NASADEM/NASADEM_HGT.001>
- Guía NASADEM: <https://lpdaac.usgs.gov/documents/1318/NASADEM_User_Guide_V12.pdf>
- Inventario CMR: <https://cmr.earthdata.nasa.gov/search/site/collections/directory/LPCLOUD/gov.nasa.eosdis>

El nuevo `scripts_pipeline/descargar_topografia_nasadem.py` encontró en CMR
las 163 teselas que intersectan el Chile administrativo completo, incluidas
las islas y sin Antártica. El descargador procesa sólo esas teselas, mantiene
30 m sin remuestreo, enmascara por huella, valida y borra ZIP/HGT crudos.

La estimación geométrica es de 1.030 millones de celdas chilenas: 2,06 GB sin
compresión para una banda `int16`. Con GeoTIFF DEFLATE se proyectan **0,9–2,3
GB finales**. La descarga nacional no se inició durante esta auditoría para no
competir con MODIS y MAIAC. `topografia_comunal.csv` no se elimina hasta que
los consumidores analíticos se migren y el raster nacional haya sido validado.

Una prueba real de la tesela `s27w106` (Sala y Gómez) descargó un ZIP de
51.403 bytes, validó 256 píxeles cuya huella toca la isla (192 centros dentro
de la comuna 5201), escribió un GeoTIFF nativo de prueba y eliminó por completo
la carpeta temporal. No se conservó ningún archivo de esa prueba.
