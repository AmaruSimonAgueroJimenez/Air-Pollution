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
