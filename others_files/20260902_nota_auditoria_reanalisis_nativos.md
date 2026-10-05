# Auditoría de reanálisis nativos para Chile

Fecha de auditoría: 2026-09-02.

## Contrato reproducible

Los descargadores de MERRA-2, CAMS EAC4 y GEOS-CF conservan la máxima
resolución espacial y temporal que entrega cada producto. Los AOI se derivan
de los 346 polígonos de `comunas.shp` (incluido `cod_comuna=0`), cubren Chile
continental, Juan Fernández, Desventuradas, Rapa Nui y Sala y Gómez y excluyen
Antártica. La salida conserva todas las celdas nativas que intersectan esos
polígonos y su relación muchos-a-muchos a comuna; no crea promedios comunales,
interpolaciones ni un corredor oceánico.

Cada mes se publica de forma atómica después de reabrirlo y comprobar la
cadencia UTC, las variables, los territorios y los SHA-256 de fuentes, máscara,
código, catálogo y salida. Los globales y AOI transitorios se borran solo tras
esa validación. Ninguna fuente rectangular legada se retira durante la
auditoría.

| Producto | Resolución nativa conservada | Catálogo | Cobertura objetivo/disponible auditada |
|---|---:|---:|---|
| MERRA-2 combinado | 0,5×0,625°, horario HH:30 UTC | 419 píxeles; 1.298 relaciones; 346 códigos | 2000–último mes de 2026 disponible |
| MERRA-2 AER opcional | 0,5×0,625°, horario HH:30 UTC | mismo catálogo MERRA-2 | 2000–último mes disponible |
| CAMS EAC4 | 0,75°, 3 horas | 268 píxeles; 1.030 relaciones; 346 códigos | 2003–2025 publicado al auditar |
| GEOS-CF | 0,25°, horario HH:30 UTC | 1.780 píxeles; 3.377 relaciones; 346 códigos | v1 2018–2025; v2 desde 2026 |

## Inventario legado y prueba local

- `MERRA2_meteo/raw_chile_horario`: 9.649 días, 2000-01-01 a
  2026-06-01, 24.489.256.025 bytes. Cada archivo tiene 24 marcas horarias y
  una grilla rectangular de 79×70 que incluye un gran corredor oceánico.
- `M2TMNXAER.5.12.4/raw_chile`: 2.192 días, 2019-01-01 a 2024-12-31,
  8.627.954.811 bytes. Es solo continental y el nombre de carpeta histórico
  no corresponde al identificador oficial M2T1NXAER.
- `CAMS_EAC4/raw_chile`: 12 archivos anuales, 2019–2024, 193.378.766
  bytes. Faltan seis celdas insulares nativas por variable y tiempo.
- `GEOS_CF/raw_chile`: 72 archivos mensuales, 2019–2024, 2.728.423.058
  bytes. Faltan doce celdas insulares nativas por variable y tiempo.

El smoke oficial de MERRA-2 para 2000-01 publicó 744 horas, 419 píxeles y
nueve variables en 6.882.670 bytes. Se compararon los 2.805.624 valores con
los 31 archivos fuente y fueron idénticos bit a bit. La reducción fue 91,23 %
frente a 78.519.592 bytes de fuentes del mes, sin perder tiempo ni celdas
chilenas. El SHA-256 de la salida es
`4e7efee357e9d0b3a6322b838ef69b24665ed9659deae76035629e19f5d64433`.

En una fecha coincidente de MERRA-2, `TOTEXTTAU` fue idéntico a `AOD_M2` y
el PM2.5 calculado con la fórmula GMAO fue idéntico a `PM25_M2`. Por eso el
runner usa el producto combinado como maestro y deja la descarga AER
independiente como opción, evitando duplicar AOD y PM2.5.

La barrera de publicación también se probó con los rectángulos legados de
2019-01. CAMS fue rechazado por 1.488 celdas-tiempo insulares ausentes y
GEOS-CF por 8.928; en ambos casos faltaban cero celdas continentales, no se
publicó salida y no quedó ningún archivo temporal.

## Proyección y retiro seguro

La extrapolación del smoke da aproximadamente 2,15 GB para MERRA-2 combinado
entre 2000-01 y 2026-06, frente a 24,49 GB del rectángulo legado. MERRA-2 AER
independiente ocuparía unos 0,58 GB, pero no agrega datos necesarios cuando se
conserva el combinado. CAMS completo 2003–2025 se estima en 0,27 GB y GEOS-CF
2018–2026 en 1,08 GB. Son proyecciones, no tamaños finales de una migración aún
no ejecutada.

Al cierre, **ninguna carpeta legada completa es todavía segura de borrar**.
Los candidatos y sus condiciones son:

1. `MERRA2_meteo/raw_chile_horario`: solo después de normalizar y reabrir
   todos los meses 2000–último disponible, validar sus hashes y cambiar al
   lector mensual nuevo.
2. `M2TMNXAER.5.12.4/raw_chile`: solo después de decidir formalmente que el
   MERRA-2 combinado es el maestro o de migrar los 2.192 días completos; se
   recupera con `descargar_merra2_aer.py` desde M2T1NXAER.
3. `CAMS_EAC4/raw_chile`: solo cuando los 72 meses 2019–2024 tengan reemplazo
   completo, incluidas las cuatro AOI insulares, y hashes verificados.
4. `GEOS_CF/raw_chile`: solo cuando los 72 meses 2019–2024 tengan reemplazo
   completo, incluidas las cuatro AOI insulares, y hashes verificados.

Los descargadores son reanudables y reservan 100 GiB. Un mes parcial queda
marcado como tal, conserva su staging y nunca habilita el borrado de fuentes.
