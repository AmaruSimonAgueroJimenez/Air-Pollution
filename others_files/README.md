# others_files/: material antiguo

Informes, notas y scripts que ya no están en uso; se conservan como referencia, con el contenido intacto.
Lo vigente está en [`docs/`](../docs/index.html) (el sitio: sólo `.qmd` y `.html`) y en las carpetas
`scripts_*`.

**Nombres:** `AAAAMMDD_<tipo>_<nombre>`. El código es la fecha en que el archivo se ocupó por última vez (la
que traía en su nombre o, si no traía, la de su última modificación); el tipo es `informe`, `nota`, `script`
o `prueba`. La columna «nombre original» (y `origen.json`) permite seguir las citas que los registros
antiguos de `logs/` hacen por la ruta vieja.

**Cómo se mantiene:** `python3 others_scripts/generar_indice_docs.py --archivar` mueve aquí las notas de
`docs/` que ya están dormidas (nadie las cita ni las modifica hace 72 h) y regenera este índice. Las que
siguen vivas se quedan en `docs/` porque los verificadores del pipeline las exigen ahí por ruta y hash.

| Código | Tipo | Archivo | Tamaño | Nombre original | Qué es |
| --- | --- | --- | --- | --- | --- |
| `20260902` | informe | [`20260902_informe_modelos_estimacion.html`](20260902_informe_modelos_estimacion.html) | 12.4 MB | `docs/modelos_estimacion.html` | Informe anterior: modelos por estación y hora, 2019–2024 (GWR, RK y LightGBM, seis contaminantes). |
| `20260902` | informe | [`20260902_informe_modelos_estimacion.qmd`](20260902_informe_modelos_estimacion.qmd) | 159 KB | `docs/modelos_estimacion.qmd` | Fuente del informe anterior; sigue renderizando desde aquí. Su librería, scripts_superficie/afg_lib.py, no se movió: el pipeline de datos la usa con ruta y hash fijos. |
| `20260902` | nota | [`20260902_nota_auditoria_lulc_topografia.md`](20260902_nota_auditoria_lulc_topografia.md) | 4 KB | `docs/auditoria_lulc_topografia.md` | Auditoría de las fuentes de uso de suelo y topografía. |
| `20260902` | nota | [`20260902_nota_auditoria_reanalisis_nativos.md`](20260902_nota_auditoria_reanalisis_nativos.md) | 4 KB | `docs/auditoria_reanalisis_nativos.md` | Auditoría de la resolución nativa de los reanálisis. |
| `20260906` | nota | [`20260906_nota_auditoria_procedencia_modis_maiac.md`](20260906_nota_auditoria_procedencia_modis_maiac.md) | 2 KB | `docs/auditoria_procedencia_modis_maiac_20260906.md` | Auditoría de procedencia de MODIS y MAIAC. |
| `20260914` | nota | [`20260914_nota_correccion_procedencia_antes_borrado.md`](20260914_nota_correccion_procedencia_antes_borrado.md) | 8 KB | `docs/correccion_procedencia_antes_borrado_20260914.md` | Corrección de procedencia hecha antes de retirar archivos legados. |
| `20260915` | nota | [`20260915_nota_preparar_sinca_modelado.md`](20260915_nota_preparar_sinca_modelado.md) | 7 KB | `docs/preparar_sinca_modelado.md` | Nota de diseño de la preparación de SINCA para modelado. |
| `20260915` | prueba | [`20260915_prueba_preparar_sinca_modelado.json`](20260915_prueba_preparar_sinca_modelado.json) | 7 KB | `docs/prueba_preparar_sinca_modelado_20260915.json` | Resultado de la prueba de preparar_sinca_modelado.py. |
| `20260915` | prueba | [`20260915_prueba_verificacion_merra2_retiro_estricto.json`](20260915_prueba_verificacion_merra2_retiro_estricto.json) | 1 KB | `docs/verificacion_merra2_retiro_estricto_20260915.json` | Verificación previa al retiro estricto de MERRA-2. |
| `20260917` | nota | [`20260917_nota_actualizacion_era5land.md`](20260917_nota_actualizacion_era5land.md) | 2 KB | `docs/ACTUALIZACION_ERA5LAND_20260917.md` | Bitácora de la actualización diaria de ERA5-Land de esa fecha. |
| `20260918` | nota | [`20260918_nota_goes_abi_aod_nativo_v1.md`](20260918_nota_goes_abi_aod_nativo_v1.md) | 10 KB | `Claude outputs/GOES_ABI_AOD_NATIVO.md` | Nota del descargador GOES, versión de las 20:29. |
| `20260918` | nota | [`20260918_nota_goes_abi_aod_nativo_v2.md`](20260918_nota_goes_abi_aod_nativo_v2.md) | 10 KB | `docs/GOES_ABI_AOD_NATIVO.md` | Nota del descargador GOES, última versión (22:32); documenta scripts_pipeline/descargar_goes_abi_aod.py. |
| `20260918` | script | [`20260918_script_descargar_goes_abi_aod.py`](20260918_script_descargar_goes_abi_aod.py) | 72 KB | `Claude outputs/descargar_goes_abi_aod.py` | Versión anterior del descargador GOES; la vigente está en scripts_pipeline/. |
| `20260919` | informe | [`20260919_informe_modelo_1km_previoenlace.html`](20260919_informe_modelo_1km_previoenlace.html) | 18.9 MB | `docs/modelo_1km_horario_previoenlace.html` | Primera corrida completa del modelo de 1 km, anterior al enlace de ERA5-Land al píxel válido, a la comparación de motores y al descriptivo de fuentes. |
| `20260919` | informe | [`20260919_informe_modelo_1km_smoke.html`](20260919_informe_modelo_1km_smoke.html) | 13.4 MB | `docs/modelo_1km_horario_smoke.html` | Render de prueba corta (una semana, motor reducido); métricas no representativas. |
| `20260919` | informe | [`20260919_informe_modelo_1km_smoke_preview.html`](20260919_informe_modelo_1km_smoke_preview.html) | 3.5 MB | `Claude outputs/modelo_1km_horario_smoke_preview.html` | Vista previa de la prueba corta hecha en el entorno de desarrollo. |
| `20261003` | nota | [`20261003_nota_revision_producto_1km.md`](20261003_nota_revision_producto_1km.md) | 40 KB | `s/d` | Revisión del 2026-10-03: hallazgos sobre el modelo de 1 km y su estado |
