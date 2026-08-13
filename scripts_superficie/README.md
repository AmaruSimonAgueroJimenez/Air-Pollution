# scripts_superficie/ — Generadores de las superficies de exposición · Exposure-surface generators

> ↩ [README principal](../README.md) · 📥 [scripts_pipeline/](../scripts_pipeline/README.md)

**Idioma / Language:** 🇪🇸 Español · 🇬🇧 [English below](#english)

---

<a id="español"></a>
## 🇪🇸 Español

Código que produce las **superficies de exposición** (comuna × hora / día) para cada
contaminante — **PM₂.₅, PM₁₀, NO₂, O₃, SO₂, CO** — a partir de los insumos de
`scripts_pipeline/`, y sus figuras/validaciones. Están pensados para parametrizarse por
contaminante (p. ej. `POLLUTANT=no2`).

### Cómo se reproduce

- **Render normal** (con `output_files/` intacto): los scripts se saltan; se usan artefactos cacheados.
- **Regenerar UN artefacto:** bórralo de `output_files/` y re-renderiza el qmd (o corre su script).
- **Correr un contaminante suelto:**
  `POLLUTANT=no2 python scripts_superficie/surface_pipeline.py`

Entorno: micromamba/conda (numpy, pandas, scipy, scikit-learn, statsmodels, pyarrow,
matplotlib, lightgbm, geopandas, pykrige, xarray, netCDF4).

### Grafo (plantilla, por contaminante)

| Script | Lee (insumos) | Escribe (en `output_files/`) |
|---|---|---|
| `build_panel.py` | `data/contaminantes/<fuentes>`, SINCA | `panel_<pol>.parquet` (predictores + observado) |
| `surface_pipeline.py` | `panel_<pol>.parquet` | `expo_<pol>_comuna_horario.parquet`, `metricas_cv_<pol>.json` |
| `surface_figs.py` | `expo_<pol>_*`, `data/comunas.shp` | `figures/<pol>_{mapa,serie,validacion}.png` |
| `gen_importancias.py` | modelo `<pol>` | `importancias_<pol>.csv` |
| `cmp_motores.py` | paneles/OOF por motor | `comparacion_motores_<pol>.csv` |

`<pol>` ∈ {`pm25`, `pm10`, `no2`, `o3`, `so2`, `co`}.

### Validación

Validación cruzada por estación (LOSO) contra SINCA, por contaminante; comparación de motores
(GWR / gradient boosting / kriging); y control de sesgos temporales.

---

<a id="english"></a>
## 🇬🇧 English

Code that builds the **exposure surfaces** (commune × hour / day) for each pollutant —
**PM₂.₅, PM₁₀, NO₂, O₃, SO₂, CO** — from the `scripts_pipeline/` inputs, plus their
figures/validations. Meant to be parametrized per pollutant (e.g. `POLLUTANT=no2`). See the
Spanish dependency-graph template above; `<pol>` ∈ {pm25, pm10, no2, o3, so2, co}. Validation is
leave-one-station-out (LOSO) against SINCA, per pollutant.
