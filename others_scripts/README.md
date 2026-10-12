# others_scripts/ — Trabajo legacy / exploratorio · Legacy / exploratory work

> ↩ [README principal](../README.md)

**Idioma / Language:** 🇪🇸 Español · 🇬🇧 [English below](#english)

---

## 🇪🇸 Español

Contenido que **NO forma parte del proceso** que produce el sitio/superficies vigentes. Se
conserva por trazabilidad (exploraciones, versiones previas de modelos, notebooks sueltos). El
pipeline vigente no depende de nada de aquí. Sus `.html`, `_files/` y `*.quarto_ipynb_*` están
en `.gitignore`.

Utilitario: `generar_indice_docs.py` mantiene `docs/` limpio (sólo `.qmd`, `.html` e índice): regenera
`docs/index.html` y `others_files/README.md`, y con `--archivar` mueve a `others_files/` —con el nombre
`AAAAMMDD_<tipo>_<nombre>`— las notas del pipeline que ya nadie cita ni modifica hace 72 h. Las que
siguen vivas se quedan en `docs/` porque los verificadores del pipeline las exigen ahí por ruta y hash.

Utilitario: `aligerar_html.py` reescribe las figuras PNG incrustadas de un HTML autocontenido con una
paleta de 256 colores (Pillow, `FASTOCTREE`), sin tocar los PNG de `output_files/`, mide el PSNR de cada
una y avisa si el HTML no queda bajo 50 MB. Se corre después de renderizar el informe del modelo:
`python -B others_scripts/aligerar_html.py docs/modelo_1km_horario.html`.

## 🇬🇧 English

Content that is **NOT part** of the current site/surface process. Kept for traceability
(exploratory work, previous model versions, one-off notebooks). The active pipeline does not
depend on anything here. Its `.html`, `_files/` and `*.quarto_ipynb_*` are gitignored.

Utility: `generar_indice_docs.py` keeps `docs/` clean (only `.qmd`, `.html` and the index): it rebuilds
`docs/index.html` and `others_files/README.md`, and with `--archivar` moves to `others_files/` —named
`YYYYMMDD_<type>_<name>`— the pipeline notes nobody has cited or modified for 72 h. Live ones stay in
`docs/` because the pipeline verifiers require them there by path and hash.

Utility: `aligerar_html.py` rewrites the PNG figures embedded in a self-contained HTML with a 256-colour
palette (Pillow, `FASTOCTREE`), without touching the PNG files in `output_files/`, measures the PSNR of
each one and warns if the HTML does not end up under 50 MB. Run it after rendering the model report:
`python -B others_scripts/aligerar_html.py docs/modelo_1km_horario.html`.

## Sincronización de componentes compartidos

Air-Pollution (AP, público) es el canónico de los componentes ambientales que también viven en
Air-Pollution-Health-Chile (APH, privado), y la copia va siempre de AP a APH. Esos componentes son
`scripts_pipeline/`, `scripts_superficie/`, `scripts_estacion/`, `scripts_modelo_1km/`, `config/`, el informe del
modelo con sus cabeceras, las notas del pipeline en `docs/`, `others_scripts/` y las salidas del modelo en
`output_files/`. El manifiesto `config/componentes_compartidos.json` (esquema `componentes-compartidos/v1`, igual
en los dos repositorios):

- fija el sha256 de cada archivo compartido, tomado de AP;
- declara como «adaptado» cada diferencia permitida, con el sha256 de cada lado, su motivo y el plan para
  eliminarla;
- lista lo propio de cada repositorio;
- guarda la huella `hash_codigo` del modelo, la esperada y la observada en cada repositorio, con su excepción
  vigente.

`verificar_componentes_compartidos.py` (sólo biblioteca estándar) lo comprueba. Sale con 0 si todo coincide, con 1
si hay divergencias y con 2 si el manifiesto no es válido o algo no se pudo leer. Excluye `__pycache__/`, `*.pyc`,
`.DS_Store`, `* 2.*` y `*.log`, no sigue enlaces simbólicos y nunca entra en rutas con «mni1» o «privado». Los
repositorios son, por omisión, las carpetas hermanas `Air-Pollution` y `Air-Pollution-Health-Chile`; si no, se
indican con `--canonico` y `--espejo`.

Procedimiento de cada sincronización:

1. **Cambio y pruebas en AP**, nunca en APH: si APH necesita un arreglo, se hace en AP y se trae. Pruebas:
   `python -B -m unittest discover -s scripts_modelo_1km/tests`, y lo mismo con `scripts_pipeline/tests` y
   `others_scripts/tests`. Después, commit en AP.
2. **Regenerar el manifiesto en AP.** `python -B others_scripts/verificar_componentes_compartidos.py --generar`
   muestra qué cambiaría, y con `--generar --forzar` lo escribe. Conserva grupos, motivos y planes, y refresca
   los sha256, `hash_codigo`, el commit de anclaje y las rutas sin confirmar. Una diferencia nueva que deba
   quedarse se declara a mano en el grupo «adaptado», con motivo y plan, y se vuelve a generar. Commit del
   manifiesto.
3. **Revisar el plan.** El mismo comando con `--plan` lista las divergencias e imprime, sin ejecutarlo,
   `rsync -a -v --checksum --dry-run --files-from=-` de AP a APH. Lo que sobra en el espejo no se borra: se
   decide en AP.
4. **Copiar de AP a APH** con ese `rsync` sin `--dry-run`, o con `cp -p` si son pocos archivos. Nunca con
   `--delete`.
5. **Comprobar en APH.** `python -B others_scripts/verificar_componentes_compartidos.py`, corrido desde APH, debe
   salir con 0. Luego vienen las pruebas de APH, un render de comprobación de los documentos que importan el
   modelo y el commit «Sincroniza componentes compartidos desde Air-Pollution@<sha>».
6. **Registro.** Con `--registrar auditoria/registro_sincronizacion.jsonl`, desde APH, el comprobador añade una
   línea con la fecha, el HEAD de cada repositorio, el sha256 del manifiesto, `hash_codigo` y el resultado.

**English.** Air-Pollution is canonical for the shared environmental components, and
Air-Pollution-Health-Chile mirrors them. `config/componentes_compartidos.json` pins every shared file by sha256
and declares each allowed difference ("adaptado") with its reason and removal plan.
`verificar_componentes_compartidos.py` checks both trees against it and exits with 0 when they are consistent, 1
on divergence and 2 for an invalid manifest. Change and test in Air-Pollution first, regenerate the manifest with
`--generar --forzar`, review `--plan`, copy to the mirror without `--delete`, and run the checker there until it
exits with 0.
