# Catálogo reproducible SINCA

Estos tres archivos pequeños son entradas versionadas del pipeline y no datos
descargados:

- `config_sinca_estaciones.json`: códigos de región/estación usados por el
  exportador horario SINCA.
- `estaciones.csv`: catálogo histórico que conserva nombre, comuna y
  coordenadas originales para auditoría.
- `politica_temporal.json`: semántica UTC/hora civil, zonas IANA por región y
  resolución reproducible de horas DST para SINCA; también documenta que el
  reloj del parquet MERRA-2 comunal es UTC−03 fijo y no hora civil.

`scripts_pipeline/actualizar_geometria_sinca.py` no confía en las coordenadas
defectuosas del catálogo: consulta o reutiliza la ficha oficial de cada
estación, reconstruye WGS84, valida la comuna y escribe el maestro operativo en
el disco externo. Las fichas HTML y los informes PDF MMA excepcionales quedan
cacheados con SHA-256 bajo `data/sinca/metadata/`, por lo que una segunda
ejecución puede hacerse completamente offline.
