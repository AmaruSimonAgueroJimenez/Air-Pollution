# ERA5-Land: capa horaria para modelado, versión 1

El programa `scripts_pipeline/preparar_era5land_modelado.py` añade un derivado compacto e independiente de precipitación. **No modifica, duplica íntegramente ni elimina los seis campos meteorológicos originales.** Tampoco descarga, promedia comunas, interpola, remuestrea ni cambia la hora a Chile continental.

## Uso reproducible

Desde la raíz del proyecto, con Python y las dependencias del entorno de descarga:

```sh
python3 -B scripts_pipeline/preparar_era5land_modelado.py --mes 2000-02
```

Se procesa exactamente un mes, usando también el anterior si existe con su manifiesto. La API equivalente es `preparar_mes(mes, origen=ORIGEN, destino=DESTINO, comunas=COMUNAS)`; `validar_producto(directorio_revision)` vuelve a comprobar hashes, todas las celdas y la fórmula. `calcular_precipitacion(tp, times, anterior=None, tiempo_anterior=None)` es la función numérica sin escrituras.

La entrada predeterminada es `/Volumes/Datos/Asesorias_Data/AirPollution/data/contaminantes/ERA5Land/chile_nativo_01deg`. La salida es:

```text
/Volumes/Datos/Asesorias_Data/AirPollution/derived/modelado/ERA5Land/v1/
  meses/YYYY-MM/<sha256-identidad>/
    tp_1h_mm.nc
    manifest.json
    preparar_era5land_modelado.py
  wal/YYYY-MM/<transacción>.jsonl
  locks/YYYY-MM.lock
  staging/<mes>.<transacción>/  # sólo si hubo un fallo
```

La identidad incluye archivos y manifiestos de ambos meses, catálogo, relación píxel-comuna, todos los componentes de la máscara, contrato documental previo, código y versiones del entorno. También se registran hashes de tres extensiones binarias cargadas (NumPy, netCDF4 y cftime); esto no equivale a archivar todas sus dependencias. Se conserva una copia exacta del script ejecutado. Los originales referenciados deben conservarse para volver a verificar o reproducir numéricamente el resultado.

Repetir el mismo comando con las mismas entradas y entorno reabre/valida la revisión y la reutiliza. Un cambio de entrada, código o entorno crea otra identidad, **sin pisar revisiones previas**. Una revisión corrupta no se reemplaza automáticamente. El mecanismo de publicación exclusiva es `renamex_np(RENAME_EXCL)` de macOS; en sistemas sin esa operación se detiene, sin degradarse a una publicación que pudiera reemplazar archivos.

## Significado temporal y unidades

La entrada local corresponde al endpoint declarado **`reanalysis-era5-land`**, no al producto `reanalysis-era5-land-timeseries` ya des-acumulado. La precipitación `tp` representa metros de agua equivalente acumulados desde las 00 UTC del ciclo del pronóstico. El valor a las 00 UTC corresponde al final del ciclo de 24 horas del día anterior. La fórmula oficial para el intervalo horario es:

```text
tp_1h_mm(t) = 1000 × tp(t)                 si la hora UTC es 01
tp_1h_mm(t) = 1000 × [tp(t) − tp(t−1 h)]   para las otras horas, incluida 00
```

El tiempo del derivado es el **fin UTC del intervalo `(t−1 h, t]`**, guardado además en `time_bounds`. La fila 00 del primer día necesita la fila 23 del mes anterior. Enero de 2000, si no existe diciembre de 1999, empieza con NaN y flags: no se inventa el antecedente. La fila 01 puede calcularse sin la fila 00 porque comienza otro ciclo. [Documentación ERA5-Land](https://confluence.ecmwf.int/pages/viewpage.action?pageId=140385202), [tabla de conversión oficial](https://confluence.ecmwf.int/pages/viewpage.action?pageId=197702790).

La salida conserva los identificadores, coordenadas, celdas de 0,1° del producto CDS y códigos comunales originales, incluido el código 0. Varios píxeles de la misma comuna continúan siendo observaciones distintas. No se añaden valores en píxeles insulares que carecen de observación nativa. La resolución decimal del cálculo es float64 para no introducir redondeo adicional en las diferencias; esto **no mejora** la precisión física del original float32 ni su resolución espacial.

`tp_1h_mm` se expresa en **mm por intervalo de una hora**, una cantidad, no una tasa instantánea. Para la lluvia total del día UTC D se necesitan los intervalos terminados entre D 01 y D+1 00: un archivo terminado en D 23 no completa ese último día. Antes de unir SINCA hay que confirmar si sus marcas temporales significan inicio/fin del intervalo y su zona horaria; no se asume equivalencia automática.

El JSON proporciona un overlay, sin reescribir el NetCDF original: `t2m/d2m` en K, `u10/v10` en m s⁻¹, `sp` en Pa, y `tp` en m acumulados. Los primeros cinco son valores instantáneos en su hora válida, no promedios horarios. Cuando faltan `units` en el archivo, quedan señaladas como **inferidas a partir del endpoint declarado y documentación oficial**, nunca como atributos retrospectivamente observados. [Variables y convenciones ECMWF](https://confluence.ecmwf.int/pages/viewpage.action?pageId=140385202).

### Límite de procedencia de legados

Febrero de 2000 conserva aliases `T2M/D2M/U10M/V10M/PS`. El productor legado localizado en el proyecto vecino `Neurodegen-Epidemiology-Chile/scripts_pipeline/07_descargar_era5land.py` pide ERA5-Land y hace explícitamente esos renombres, sin remuestrear esos cinco campos; los aliases **no prueban origen MERRA**. Sin embargo, no se conserva un vínculo de ejecución que certifique ese código como productor del hash legado de febrero. Los atributos TP originales tampoco pueden releerse después de su retiro: las unidades y semántica se sustentan en solicitudes/manifiestos y documentación del producto. El overlay expone este límite; no certifica exhaustivamente todos los legados históricos.

## Faltantes, negativos y validación

`tp_1h_flags` usa bits combinables:

| Bit | Significado |
| --- | --- |
| 1 | Acumulado actual no finito |
| 2 | Antecedente necesario ausente/no finito |
| 4 | No existe antecedente exactamente una hora antes |
| 8 | Incremento finito negativo, conservado sin cambios |

Un cero indica ausencia de esas señales, no una garantía general de calidad meteorológica. No hay umbral ni corrección automática de negativos: ECMWF documenta artefactos de empaquetado, pero sus ejemplos de tolerancia para otros pronósticos no certifican una tolerancia universal ERA5-Land. [FAQ ecCodes](https://confluence.ecmwf.int/spaces/UDOC/pages/208501579/Why+are+there+sometimes+small+negative+precipitation+accumulations+-+ecCodes+GRIB+FAQ).

Antes de publicar se reabren **todas** las variables derivadas, se comparan todas las celdas con los originales y la fórmula, se verifican flags y coordenadas, y se comprueba conservación del acumulado en cada ciclo completo y finito. Los hashes de entrada se vuelven a revisar al final. El manifiesto distingue horas/píxeles, cantidades finitas, NaN, negativos y ciclos conservados; tener todas las horas no significa tener datos finitos en todos los píxeles.

## Seguridad de almacenamiento y pruebas

Se exige el volumen externo montado con UUID `54B3D309-A503-44C6-9229-581F3E4FECE3`, y al menos 100 GiB libres después de descontar una estimación conservadora del archivo adicional. Un lock por mes impide escritores cooperantes simultáneos; WAL, archivos y directorios se sincronizan antes/después de la publicación exclusiva. No se retira ninguna fuente ni revisión previa. Si falla una escritura, validación, manifiesto o publicación, se conservan los archivos nuevos incompletos para diagnóstico; **no son productos científicos publicados y no se deben consumir**. El comando puede volver a generar una revisión desde originales intactos, sin borrar ese staging fallido. Un fallo posterior al renombrado se resuelve al revalidar la publicación existente.

```sh
python3 -B -m unittest discover -s scripts_pipeline/tests -p test_preparar_era5land_modelado.py -v
```

Las pruebas cubren reset, medianoche, cambios de mes/año, año bisiesto, ausencia de antecedente, NaN por píxel, negativos, orden espacial distinto, hash/endpoint/unidades incompatibles, idempotencia y fallos de publicación. El primer ensayo con datos reales debe limitarse a un mes, sin ejecutar automáticamente todo el histórico.

### Ensayos reales autorizados, 15 de septiembre de 2026

A las 17:50 UTC se revalidaron los tres ensayos, cada uno con 9.725 píxeles intactos. Código ejecutado y archivado: SHA-256 `2aabcfc96ffe6e0821480379434c9abea5c24590eb0b80058a4371c92c19bc78`. Suite: **23 pruebas sintéticas aprobadas**. Los nativos, descargador y normalizador permanecen intactos.

| Mes probado | Horas | Tamaño NetCDF | Resultado relevante |
| --- | ---: | ---: | --- |
| 2000-02 | 696 | 13.367.947 bytes | Cruce con enero válido; repetir reutilizó idéntico archivo/hash |
| 2000-01 | 744 | 15.070.559 bytes | Primeras 00 UTC: 9.725 NaN con flag de antecedente; a 01 UTC existen 8.206 valores finitos |
| 2026-09 | 216 | 3.869.182 bytes | Termina exactamente el 9 de septiembre a las 23 UTC; no fabrica horas futuras |

Las tres revisiones están en `meses/<mes>/<identidad>/`, respectivamente:

- Febrero: `d40d9bbe9c093b8ed2e4679ba53b531a0b10d9224d796c613059f628297a18b2`; NetCDF SHA-256 `200b8dd54cb8614582a2a47c3c4edba18a90b4efcf9547ad90bb660f3cb0e9e8`.
- Enero: `19f14752a0ef40c958a26ca4ac88ee51d1e9832c8845cd07f5809c2b73e2c66e`; NetCDF SHA-256 `ba1ebda3040bd030ed3822c7f42de9807c938d41cd969377832b6e6229a3d76d`.
- Septiembre: `41939327ba8664b48afda6b1b4c0468195e5029ea937415c97b11b2f58418319`; NetCDF SHA-256 `915993c79024240c2ef083997643f8979da3c7c74ade0493deee2bbb87dc8a98`.

No quedaron archivos en staging de estos ensayos, ni se borró ningún dato anterior. La reserva verificada al terminar fue de 382.154.235.904 bytes libres (355,91 GiB; varía con otros procesos). Los manifiestos conservan los límites de unidades/procedencia inferidas: estos ensayos validan la transformación y sus entradas declaradas, no convierten retrospectivamente los metadatos ausentes en certificaciones observadas.
