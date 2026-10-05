#!/usr/bin/env python3
"""Mantiene ``docs/`` limpio y genera los dos índices del repositorio.

``docs/`` es el sitio: sólo los ``.qmd``, ``.html`` y ``.pdf`` vigentes más ``index.html``. Todo lo demás se archiva
en ``others_files/`` (en la raíz) con el nombre ``AAAAMMDD_<tipo>_<nombre>``: la fecha es la última vez que
el archivo se ocupó y el tipo es ``informe``, ``nota``, ``script`` o ``prueba``.

Las notas ``.md``/``.json`` del pipeline de datos no son caché: los registros de control de ``logs/`` las
citan por ruta y los verificadores comprueban que existan, en ``docs/``, con su hash exacto. Por eso una
nota sólo se archiva cuando está **dormida**: nadie la ha citado ni modificado en ``--horas`` horas (72 por
defecto) y ninguna nota viva la enlaza. Moverla antes rompería la verificación del pipeline.

    python3 others_scripts/generar_indice_docs.py              # regenera índices; dice qué se podría archivar
    python3 others_scripts/generar_indice_docs.py --archivar   # además archiva las notas dormidas

Sólo usa la biblioteca estándar. ``others_files/origen.json`` conserva el nombre original de cada archivo,
para poder seguir las citas de los registros antiguos.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DOCS, ARCHIVO, LOGS = RAIZ / "docs", RAIZ / "others_files", RAIZ / "logs"
ORIGEN = ARCHIVO / "origen.json"
VIGENTES = [  # (archivo, título, descripción)
    ("modelo_1km_horario.html", "Informe: modelo horario de PM₂.₅ y NO₂ a 1 km",
     "Descriptivo SINCA, descriptivo de todas las fuentes a resolución nativa, LightGBM con validación LOSO/LRO/LPO, "
     "comparación con GWR y regression-kriging, evaluación espacial y temporal, superficies."),
    ("modelo_1km_horario.qmd", "Fuente del informe (Quarto)",
     "Documento ejecutable donde vive el modelo; su librería, contrato, estado y resultados están en "
     "scripts_modelo_1km/ (README.md)."),
]
DESCRIPCION = {  # por nombre sin el código de fecha
    "informe_modelos_estimacion.html": "Informe anterior: modelos por estación y hora, 2019–2024 (GWR, RK y LightGBM, seis contaminantes).",
    "informe_modelos_estimacion.qmd": "Fuente del informe anterior; sigue renderizando desde aquí. Su librería, scripts_superficie/afg_lib.py, no se movió: el pipeline de datos la usa con ruta y hash fijos.",
    "informe_modelo_1km_previoenlace.html": "Primera corrida completa del modelo de 1 km, anterior al enlace de ERA5-Land al píxel válido, a la comparación de motores y al descriptivo de fuentes.",
    "informe_modelo_1km_smoke.html": "Render de prueba corta (una semana, motor reducido); métricas no representativas.",
    "informe_modelo_1km_smoke_preview.html": "Vista previa de la prueba corta hecha en el entorno de desarrollo.",
    "script_descargar_goes_abi_aod.py": "Versión anterior del descargador GOES; la vigente está en scripts_pipeline/.",
    "nota_goes_abi_aod_nativo_v1.md": "Nota del descargador GOES, versión de las 20:29.",
    "nota_goes_abi_aod_nativo_v2.md": "Nota del descargador GOES, última versión (22:32); documenta scripts_pipeline/descargar_goes_abi_aod.py.",
    "nota_preparar_sinca_modelado.md": "Nota de diseño de la preparación de SINCA para modelado.",
    "prueba_preparar_sinca_modelado.json": "Resultado de la prueba de preparar_sinca_modelado.py.",
    "nota_auditoria_lulc_topografia.md": "Auditoría de las fuentes de uso de suelo y topografía.",
    "nota_auditoria_reanalisis_nativos.md": "Auditoría de la resolución nativa de los reanálisis.",
    "nota_auditoria_procedencia_modis_maiac.md": "Auditoría de procedencia de MODIS y MAIAC.",
    "nota_correccion_procedencia_antes_borrado.md": "Corrección de procedencia hecha antes de retirar archivos legados.",
    "prueba_verificacion_merra2_retiro_estricto.json": "Verificación previa al retiro estricto de MERRA-2.",
    "nota_actualizacion_era5land.md": "Bitácora de la actualización diaria de ERA5-Land de esa fecha.",
}
CODIGO = re.compile(r"^(\d{8})_(informe|nota|script|prueba)_(.+)$")
EXTENSIONES_SITIO = {".qmd", ".html", ".pdf"}   # el PDF es entregable, no nota archivable


def titulo_de(ruta: Path) -> str:
    """Primer encabezado Markdown del archivo, o su nombre."""
    if ruta.suffix.lower() == ".md":
        for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines()[:40]:
            m = re.match(r"^#{1,3}\s+(.*\S)", linea)
            if m:
                return m.group(1)
    return ruta.name


def tamano(ruta: Path) -> str:
    b = ruta.stat().st_size
    return f"{b / 1e6:.1f} MB" if b >= 1e6 else f"{max(b // 1000, 1)} KB"


def notas_de_docs() -> list[Path]:
    """Lo que hay en ``docs/`` y no es parte del sitio."""
    return sorted(p for p in DOCS.iterdir() if p.is_file() and not p.name.startswith(".")
                  and p.suffix.lower() not in EXTENSIONES_SITIO)


def ultima_cita(notas: list[Path]) -> dict[str, float]:
    """Momento (epoch) de la cita más reciente de cada nota en ``logs/`` (registros y scripts)."""
    ultima = {p.name: 0.0 for p in notas}
    if not LOGS.is_dir():
        return ultima
    patron = re.compile("|".join(re.escape(f"docs/{n}") for n in ultima) or r"$^")
    for f in LOGS.iterdir():
        if f.suffix not in {".json", ".py", ".jsonl", ".sh"} or not f.is_file():
            continue
        m = f.stat().st_mtime
        if m <= min(ultima.values(), default=0.0):
            continue
        try:
            texto = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for cita in set(patron.findall(texto)):
            nombre = cita[5:]
            ultima[nombre] = max(ultima[nombre], m)
    return ultima


def clasificar(horas: float) -> tuple[list[Path], list[tuple[Path, str]]]:
    """(dormidas, [(viva, motivo)]). Viva = citada o modificada hace menos de ``horas``, o enlazada por una viva."""
    notas = notas_de_docs()
    cita, ahora = ultima_cita(notas), time.time()
    motivo = {}
    for p in notas:
        h_cita, h_mod = (ahora - cita[p.name]) / 3600, (ahora - p.stat().st_mtime) / 3600
        if cita[p.name] and h_cita < horas:
            motivo[p.name] = f"citada en logs/ hace {h_cita:.0f} h"
        elif h_mod < horas:
            motivo[p.name] = f"modificada hace {h_mod:.0f} h"
    cambio = True
    while cambio:                                   # una nota enlazada por una viva también se queda
        cambio = False
        for viva in [p for p in notas if p.name in motivo and p.suffix.lower() == ".md"]:
            texto = viva.read_text(encoding="utf-8", errors="replace")
            for p in notas:
                if p.name not in motivo and p.name in texto:
                    motivo[p.name] = f"enlazada desde {viva.name}, que sigue viva"
                    cambio = True
    return [p for p in notas if p.name not in motivo], [(p, motivo[p.name]) for p in notas if p.name in motivo]


def nombre_de_archivo(p: Path) -> str:
    """``AAAAMMDD_<tipo>_<nombre>``: la fecha del nombre si la trae; si no, la de su última modificación."""
    m = re.search(r"(20\d{6})", p.stem)
    codigo = m.group(1) if m else datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y%m%d")
    base = re.sub(r"_?20\d{6}(T\d+)?", "", p.stem).strip("_").lower()
    tipo = "prueba" if p.suffix.lower() == ".json" else "nota"
    candidato, k = f"{codigo}_{tipo}_{base}{p.suffix.lower()}", 1
    while (ARCHIVO / candidato).exists():
        k += 1
        candidato = f"{codigo}_{tipo}_{base}_v{k}{p.suffix.lower()}"
    return candidato


def archivar(dormidas: list[Path]) -> list[tuple[str, str]]:
    ARCHIVO.mkdir(exist_ok=True)
    origen = json.loads(ORIGEN.read_text(encoding="utf-8")) if ORIGEN.exists() else {}
    hechos = []
    for p in dormidas:
        nuevo = nombre_de_archivo(p)
        shutil.move(str(p), str(ARCHIVO / nuevo))
        origen[nuevo] = f"docs/{p.name}"
        hechos.append((p.name, nuevo))
    ORIGEN.write_text(json.dumps(origen, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return hechos


def indice_archivo() -> int:
    """``others_files/README.md``: una fila por archivo, ordenadas por código."""
    if not ARCHIVO.is_dir():
        return 0
    origen = json.loads(ORIGEN.read_text(encoding="utf-8")) if ORIGEN.exists() else {}
    filas = []
    for p in sorted(ARCHIVO.iterdir()):
        if not p.is_file() or p.name.startswith(".") or p.name in {"README.md", "origen.json"}:
            continue
        m = CODIGO.match(p.name)
        codigo, tipo, resto = m.groups() if m else ("sin código", "s/d", p.name)
        clave = re.sub(r"^\d{8}_", "", p.name)
        filas.append(f"| `{codigo}` | {tipo} | [`{p.name}`]({p.name}) | {tamano(p)} | `{origen.get(p.name, 's/d')}` | "
                     f"{DESCRIPCION.get(clave, titulo_de(p) if p.suffix == '.md' else '')} |")
    (ARCHIVO / "README.md").write_text(f"""# others_files/: material antiguo

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
{chr(10).join(filas)}
""", encoding="utf-8")
    return len(filas)


def fila(ruta: Path, titulo: str, descripcion: str = "") -> str:
    enlace = html.escape(ruta.relative_to(DOCS).as_posix())
    detalle = f"<span class='d'>{html.escape(descripcion)}</span>" if descripcion else ""
    return (f"<li><a href='{enlace}'>{html.escape(titulo)}</a> <code>{enlace}</code>"
            f"<span class='m'>{tamano(ruta)} · {datetime.fromtimestamp(ruta.stat().st_mtime):%Y-%m-%d}</span>{detalle}</li>")


def indice_sitio(vivas: list[tuple[Path, str]], n_archivo: int) -> None:
    vigentes = [fila(DOCS / a, t, d) for a, t, d in VIGENTES if (DOCS / a).exists()]
    pipeline = [fila(p, titulo_de(p), f"Sigue aquí: {motivo}.") for p, motivo in vivas]
    seccion_vivas = f"""<h2>Notas del pipeline de datos que todavía no se pueden archivar</h2>
<p class="s">No son caché: son la evidencia y los contratos de las descargas. Los ciclos del pipeline las comprueban
en esta carpeta por ruta y por hash, así que moverlas ahora rompería su verificación. Se archivan solas, con
<code>generar_indice_docs.py --archivar</code>, cuando dejan de citarse.</p><ul>{''.join(pipeline)}</ul>""" if pipeline else ""
    (DOCS / "index.html").write_text(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Air-Pollution · documentos</title>
<style>
:root {{ --fondo:#fcfcfb; --texto:#1d1d1b; --tenue:#6b6b66; --linea:#e3e2dd; --enlace:#1f5fa8; --codigo:#f1f0ec; }}
@media (prefers-color-scheme: dark) {{ :root {{ --fondo:#161716; --texto:#e9e8e3; --tenue:#a3a29b; --linea:#30312e; --enlace:#8ab8f0; --codigo:#232422; }} }}
body {{ background:var(--fondo); color:var(--texto); font:16px/1.55 Arial, "Helvetica Neue", Helvetica, sans-serif;
       max-width:54rem; margin:0 auto; padding:2rem 1rem 4rem; }}
h1 {{ font-size:1.6rem; margin:0 0 .3rem; }} h2 {{ font-size:1.1rem; margin:2.2rem 0 .6rem; padding-bottom:.3rem; border-bottom:1px solid var(--linea); }}
p.s {{ color:var(--tenue); margin:0 0 1rem; }} ul {{ list-style:none; padding:0; margin:0; }}
li {{ padding:.55rem 0; border-bottom:1px solid var(--linea); overflow-wrap:anywhere; }}
a {{ color:var(--enlace); font-weight:600; text-decoration:none; }} a:hover {{ text-decoration:underline; }}
code {{ background:var(--codigo); padding:.05rem .3rem; border-radius:3px; font-size:.8rem; color:var(--tenue); }}
.m {{ color:var(--tenue); font-size:.8rem; margin-left:.4rem; white-space:nowrap; }} .d {{ display:block; color:var(--tenue); font-size:.9rem; margin-top:.15rem; }}
</style></head><body>
<h1>Air-Pollution · documentos</h1>
<p class="s">Estimación multi-contaminante de la calidad del aire en Chile. Índice generado el {datetime.now():%Y-%m-%d %H:%M}
con <code>others_scripts/generar_indice_docs.py</code>.</p>
<h2>Modelos vigentes</h2><ul>{''.join(vigentes)}</ul>
<h2>Material antiguo</h2>
<p class="s"><a href="../others_files/README.md">others_files/</a>, {n_archivo} archivos con código de fecha
(<code>AAAAMMDD_tipo_nombre</code>): informes reemplazados, notas y scripts que ya no están en uso.</p>
{seccion_vivas}
</body></html>
""", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archivar", action="store_true", help="mover a others_files/ las notas dormidas de docs/")
    ap.add_argument("--horas", type=float, default=72.0, help="horas sin citas ni cambios para considerar dormida una nota")
    args = ap.parse_args()
    dormidas, vivas = clasificar(args.horas)
    if args.archivar and dormidas:
        for viejo, nuevo in archivar(dormidas):
            print(f"archivado: docs/{viejo} → others_files/{nuevo}")
        dormidas, vivas = clasificar(args.horas)
    n = indice_archivo()
    indice_sitio(vivas, n)
    print(f"docs/index.html y others_files/README.md regenerados: {n} archivados, {len(vivas)} notas vivas en docs/")
    for p, motivo in vivas:
        print(f"  viva     {p.name}: {motivo}")
    for p in dormidas:
        print(f"  dormida  {p.name}: se puede archivar con --archivar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
