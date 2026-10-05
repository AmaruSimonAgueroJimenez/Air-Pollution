"""Aligera un HTML autocontenido de Quarto: reescribe sus PNG incrustados con una paleta de 256 colores.

El informe del modelo de 1 km (``docs/modelo_1km_horario.html``) se renderiza con ``embed-resources: true``,
de modo que cada figura va dentro del HTML como ``data:image/png;base64,...``. Así pesa más de 100 MB, el
límite por archivo de GitHub, y casi todo ese peso son las figuras. Este script decodifica cada PNG
incrustado, lo cuantiza a 256 colores con Pillow (``FASTOCTREE``, sin tramado) y lo vuelve a incrustar si
queda más chico. Las figuras de ``output_files/`` no se tocan: el script sólo lee y escribe el HTML.

Por cada imagen mide el PSNR contra la original (sobre los canales RGB, o RGBA si tiene transparencia) y
la fracción de píxeles que se desvían en más de 16 niveles en algún canal, e informa el peor caso. Sale
con código 1 si el HTML final no queda bajo ``--max-mb`` o si alguna imagen queda bajo ``--psnr-min``.

    python -B others_scripts/aligerar_html.py docs/modelo_1km_horario.html
    python -B others_scripts/aligerar_html.py docs/modelo_1km_horario.html --salida /tmp/prueba.html --informe /tmp/psnr.csv
"""
from __future__ import annotations

import argparse
import base64
import csv
import io
import os
import re
import stat
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

PATRON = re.compile(rb"data:image/png;base64,([A-Za-z0-9+/=]+)")
UMBRAL_NIVELES = 16          # desviación por canal que se cuenta como píxel «desviado»


def cuantizar(blob: bytes) -> tuple[bytes, dict]:
    """PNG original (bytes) -> PNG con paleta de 256 colores (bytes) y su medición de fidelidad."""
    orig = Image.open(io.BytesIO(blob))
    orig.load()
    info = {"ancho": orig.width, "alto": orig.height, "modo": orig.mode, "bytes_antes": len(blob)}
    if orig.mode in ("P", "L", "1"):                 # ya es de paleta o gris: no hay nada que ganar
        return blob, {**info, "bytes_despues": len(blob), "psnr": float("inf"), "desviados_pct": 0.0,
                      "cambiada": False}
    base = orig.convert("RGBA")
    # Las figuras de matplotlib son RGBA con el canal alfa entero en 255: se cuantizan en RGB, porque un
    # alfa constante sólo le quita precisión a la paleta. Con transparencia real se cuantiza en RGBA.
    fuente = base.convert("RGB") if base.getchannel("A").getextrema() == (255, 255) else base
    pal = fuente.quantize(colors=256, method=Image.Quantize.FASTOCTREE)
    buf = io.BytesIO()
    pal.save(buf, format="PNG", optimize=True)
    nuevo = buf.getvalue()
    a = np.asarray(fuente, dtype=np.int16)
    b = np.asarray(Image.open(io.BytesIO(nuevo)).convert(fuente.mode), dtype=np.int16)
    if a.shape != b.shape:
        raise ValueError(f"la imagen cuantizada cambió de tamaño: {a.shape} -> {b.shape}")
    dif = np.abs(a - b)
    mse = float(np.mean(dif.astype(np.float64) ** 2))
    psnr = float("inf") if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)
    desviados = 100 * float(np.mean(dif.max(axis=2) > UMBRAL_NIVELES))
    if len(nuevo) >= len(blob):                      # no se gana: queda la original
        return blob, {**info, "bytes_despues": len(blob), "psnr": float("inf"), "desviados_pct": 0.0,
                      "cambiada": False}
    return nuevo, {**info, "bytes_despues": len(nuevo), "psnr": psnr, "desviados_pct": desviados,
                   "cambiada": True}


def _tarea(b64: bytes) -> tuple[bytes, bytes, dict]:
    nuevo, info = cuantizar(base64.b64decode(b64))
    return b64, base64.b64encode(nuevo), info


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("html", type=Path, help="HTML autocontenido de entrada")
    ap.add_argument("--salida", type=Path, default=None, help="HTML de salida (por omisión, se reescribe la entrada)")
    ap.add_argument("--max-mb", type=float, default=50.0, help="tamaño máximo aceptado del HTML final, en MB")
    ap.add_argument("--psnr-min", type=float, default=30.0, help="PSNR mínimo aceptado por imagen, en dB")
    ap.add_argument("--informe", type=Path, default=None, help="CSV con la medición de cada imagen")
    ap.add_argument("--procesos", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = ap.parse_args(argv)

    texto = a.html.read_bytes()
    blobs = list(dict.fromkeys(m.group(1) for m in PATRON.finditer(texto)))   # únicas, en orden de aparición
    if not blobs:
        print(f"{a.html}: no hay PNG incrustados; no se cambia nada")
        return 0
    with ProcessPoolExecutor(max_workers=a.procesos) as ex:
        resultados = list(ex.map(_tarea, blobs, chunksize=4))
    reemplazo = {viejo: nuevo for viejo, nuevo, _ in resultados}
    salida = PATRON.sub(lambda m: b"data:image/png;base64," + reemplazo[m.group(1)], texto)

    destino = a.salida or a.html
    destino.parent.mkdir(parents=True, exist_ok=True)
    modo = stat.S_IMODE((destino if destino.exists() else a.html).stat().st_mode)
    with tempfile.NamedTemporaryFile(dir=destino.parent, prefix=".aligerar_", suffix=".html", delete=False) as tmp:
        tmp.write(salida)
    os.chmod(tmp.name, modo)                       # el temporal nace con 0600: se le dan los permisos del HTML
    os.replace(tmp.name, destino)

    infos = [info for _, _, info in resultados]
    cambiadas = [i for i in infos if i["cambiada"]]
    psnr = np.array([i["psnr"] for i in cambiadas]) if cambiadas else np.array([np.inf])
    peor = min(cambiadas, key=lambda i: i["psnr"]) if cambiadas else None
    mb = lambda n: n / 1e6
    print(f"{a.html.name}: {mb(len(texto)):.1f} MB -> {destino.name}: {mb(len(salida)):.1f} MB")
    print(f"  PNG incrustados: {len(blobs)} únicos; reescritos {len(cambiadas)}; "
          f"binario {mb(sum(i['bytes_antes'] for i in infos)):.1f} -> {mb(sum(i['bytes_despues'] for i in infos)):.1f} MB")
    if cambiadas:
        print(f"  PSNR (dB): mínimo {psnr.min():.1f}, percentil 5 {np.percentile(psnr, 5):.1f}, mediana {np.median(psnr):.1f}")
        print(f"  píxeles desviados en más de {UMBRAL_NIVELES} niveles: mediana "
              f"{np.median([i['desviados_pct'] for i in cambiadas]):.3f} %, máximo {max(i['desviados_pct'] for i in cambiadas):.3f} %")
        print(f"  peor imagen: {peor['ancho']}×{peor['alto']} px, PSNR {peor['psnr']:.1f} dB, "
              f"{peor['desviados_pct']:.3f} % de píxeles desviados")
    if a.informe:
        with open(a.informe, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["orden", "ancho", "alto", "modo", "bytes_antes", "bytes_despues",
                                              "psnr", "desviados_pct", "cambiada"])
            w.writeheader()
            for k, i in enumerate(infos):
                w.writerow({"orden": k, **i})
    ok = True
    if mb(len(salida)) >= a.max_mb:
        print(f"  ATENCIÓN: el HTML queda en {mb(len(salida)):.1f} MB, no bajo {a.max_mb:g} MB", file=sys.stderr)
        ok = False
    if cambiadas and psnr.min() < a.psnr_min:
        print(f"  ATENCIÓN: alguna imagen queda bajo {a.psnr_min:g} dB de PSNR", file=sys.stderr)
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
