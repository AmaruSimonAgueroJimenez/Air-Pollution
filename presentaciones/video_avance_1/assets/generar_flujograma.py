#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flujograma de obtención y procesamiento de datos — proyecto Air-Pollution (AFG 1).
Reproduce el pipeline real del repositorio: fuentes → descarga/recorte → agregación
comunal → panel con SINCA → modelos → superficies → macrozonas.
"""

import os
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

SURFACE = "#ffffff"; INK = "#0b0b0b"; INK2 = "#52514e"; MUTED = "#898781"
GRID = "#e1e0d9"; AXIS = "#c3c2b7"
BLUE = "#2a78d6"; ORANGE = "#eb6834"; AQUA = "#1baf7a"
SEQ = {250: "#86b6ef", 350: "#5598e7", 450: "#2a78d6", 550: "#1c5cab",
       600: "#184f95", 700: "#0d366b"}

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Liberation Sans", "DejaVu Sans", "Arial"],
    "figure.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "figure.dpi": 300, "savefig.dpi": 300,
    "savefig.bbox": "tight", "savefig.pad_inches": 0.06,
})

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
os.makedirs(OUT, exist_ok=True)


def caja(ax, x, y, w, h, fc, ec="none", lw=1.0, r=0.9, z=2):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                 boxstyle=f"round,pad=0,rounding_size={r}", facecolor=fc,
                 edgecolor=ec, linewidth=lw, zorder=z))


def wrap(ax, x, y, text, width, size=8.0, color=INK, weight="normal",
         ha="center", va="center", lh=1.25, z=4):
    ax.text(x, y, "\n".join(textwrap.wrap(text, width)), fontsize=size,
            color=color, weight=weight, ha=ha, va=va, linespacing=lh, zorder=z)


def flecha(ax, p1, p2, col=AXIS, lw=1.6, ms=13, estilo="-|>", rad=0.0, z=1,
           ls="solid"):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle=estilo, mutation_scale=ms,
                 color=col, lw=lw, shrinkA=2, shrinkB=2, zorder=z,
                 linestyle=ls, connectionstyle=f"arc3,rad={rad}"))


def main():
    fig = plt.figure(figsize=(12.2, 6.55))
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 122); ax.set_ylim(0, 65.5)
    ax.axis("off")

    # ================= COLUMNA 1: FUENTES =================
    ax.text(19.0, 63.2, "1 · FUENTES DE DATOS", fontsize=10, weight="bold",
            color=SEQ[700], ha="center")

    grupos = [
        (SEQ[600], "SATÉLITES (gases y aerosol)",
         [("Sentinel-5P TROPOMI", "NO₂ · O₃ · SO₂ · CO — 2018+"),
          ("Aura OMI", "NO₂ · O₃ · SO₂ — 2004+"),
          ("Terra MOPITT", "CO — 2000+"),
          ("MODIS MAIAC / AOD 3K", "AOD, predictor de PM")]),
        (SEQ[450], "REANÁLISIS Y SUPERFICIES",
         [("CAMS EAC4 (Copernicus)", "6 contaminantes — 2003+"),
          ("NASA GEOS-CF", "gases + PM, horario — 2018+"),
          ("MERRA-2 aerosoles", "componentes PM₂.₅/PM₁₀"),
          ("ACAG PM₂.₅ superficie", "van Donkelaar, histórico")]),
        (AQUA, "PREDICTORES COMUNES",
         [("ERA5 / ERA5-Land · met.", "ESA CCI suelo · OSM vial"),
          ("NASADEM · luces VIIRS", "censo: población y leña")]),
        (ORANGE, "VERDAD-TERRENO",
         [("Red SINCA (MMA)", "109 estaciones · 6 contaminantes")]),
    ]

    HEAD, ROW, GAP = 3.0, 3.9, 1.5
    ytop = 60.9
    y_sat_mid = y_sinca_mid = None
    for col, titulo, filas in grupos:
        h = HEAD + len(filas) * ROW
        caja(ax, 1.5, ytop - h, 35.0, h, "#ffffff", ec=col, lw=1.4)
        caja(ax, 1.5, ytop - HEAD, 35.0, HEAD, col, r=0.9)
        caja(ax, 1.5, ytop - HEAD, 35.0, 1.2, col, r=0.0)
        ax.text(19.0, ytop - HEAD / 2, titulo, fontsize=7.9, weight="bold",
                color="#ffffff", ha="center", va="center", zorder=4)
        y = ytop - HEAD
        for nombre, detalle in filas:
            y -= ROW
            ax.text(3.3, y + 2.55, nombre, fontsize=7.5, weight="bold",
                    color=INK, va="center", zorder=4)
            ax.text(3.3, y + 0.95, detalle, fontsize=6.8, color=INK2,
                    va="center", zorder=4)
        if titulo.startswith("SATÉLITES"):
            y_sat_mid = ytop - h / 2
        if titulo.startswith("VERDAD"):
            y_sinca_mid = ytop - h / 2
        ytop = ytop - h - GAP


    # ================= COLUMNA 2: PIPELINE =================
    ax.text(56.5, 63.2, "2 · PIPELINE REPRODUCIBLE", fontsize=10, weight="bold",
            color=SEQ[700], ha="center")

    pasos = [
        (56.5, 56.0, "Descarga programática por contaminante",
         "scripts_pipeline/ · credenciales .env · reintentos"),
        (56.5, 46.4, "Recorte a Chile «al vuelo»",
         "gránulos globales → bbox Chile (~5 % del volumen)"),
        (56.5, 36.8, "Agregación comuna × hora / día",
         "raw_chile/ → comunal_horario/ · 345 comunas"),
        (56.5, 27.2, "Panel de modelamiento",
         "predictores satelitales + meteorología + estáticos, unidos a SINCA"),
    ]
    for cx, cy, t1, t2 in pasos:
        caja(ax, cx - 16.5, cy - 4.1, 33.0, 8.2, "#f4f7fc", ec=SEQ[350], lw=1.3)
        wrap(ax, cx, cy + 1.5, t1, 34, size=8.2, weight="bold", color=INK)
        wrap(ax, cx, cy - 1.7, t2, 40, size=7.0, color=INK2)
    for a, b in [(51.9, 46.4 + 4.1), (42.3, 36.8 + 4.1), (32.7, 27.2 + 4.1)]:
        flecha(ax, (56.5, a), (56.5, b), col=SEQ[450], lw=1.8)

    # entradas desde columna 1
    flecha(ax, (36.9, y_sat_mid), (39.7, 55.5), col=AXIS, lw=1.4, rad=0.22)
    flecha(ax, (37.3, y_sinca_mid + 1.5), (40.0, 23.0), col=ORANGE, lw=1.6, rad=0.0)
    wrap(ax, 50.5, 7.6, "SINCA entra solo como verdad-terreno de los modelos", 60, size=6.6, color=ORANGE)

    # modelos
    caja(ax, 40.0, 9.8, 33.0, 9.4, "#fff6f1", ec=ORANGE, lw=1.4)
    wrap(ax, 56.5, 16.4, "Modelos de estimación por contaminante", 36, size=8.2,
         weight="bold", color=INK)
    wrap(ax, 56.5, 13.2, "GWR · gradient boosting (LightGBM) · kriging", 44,
         size=7.2, color=INK2)
    wrap(ax, 56.5, 10.9, "Validación cruzada dejando una estación fuera (LOSO)",
         46, size=7.2, color=INK2)
    flecha(ax, (56.5, 23.1), (56.5, 19.2), col=SEQ[450], lw=1.8)

    # ================= COLUMNA 3: PRODUCTOS =================
    ax.text(101.5, 63.2, "3 · PRODUCTOS", fontsize=10, weight="bold",
            color=SEQ[700], ha="center")

    caja(ax, 84.0, 44.0, 35.0, 13.6, SEQ[700], r=1.1)
    wrap(ax, 101.5, 53.4, "Superficies de exposición", 30, size=9.6,
         weight="bold", color="#ffffff")
    wrap(ax, 101.5, 49.9, "PM₂.₅ · PM₁₀ · NO₂ · O₃ · SO₂ · CO", 40, size=8.4,
         color="#ffffff")
    wrap(ax, 101.5, 46.6, "comuna × hora / día · todo Chile", 40, size=7.6,
         color="#cde2fb")

    caja(ax, 84.0, 30.0, 35.0, 9.6, "#ffffff", ec=SEQ[600], lw=1.4)
    wrap(ax, 101.5, 36.6, "Agregación por macrozona", 34, size=8.6,
         weight="bold", color=INK)
    wrap(ax, 101.5, 33.0, "Norte Grande · Norte Chico · Centro · Sur · Austral",
         44, size=7.2, color=INK2)

    caja(ax, 84.0, 16.4, 35.0, 9.6, "#ffffff", ec=SEQ[600], lw=1.4)
    wrap(ax, 101.5, 23.0, "Métricas de validación por estación", 36, size=8.6,
         weight="bold", color=INK)
    wrap(ax, 101.5, 19.4, "R² · RMSE · sesgo, por contaminante y zona", 44,
         size=7.2, color=INK2)

    caja(ax, 84.0, 3.6, 35.0, 8.8, "#f4f5f2", ec=GRID, lw=1.2)
    wrap(ax, 101.5, 9.4, "Repositorio abierto y reproducible", 40, size=8.4,
         weight="bold", color=INK)
    wrap(ax, 101.5, 6.1, "github.com/AmaruSimonAgueroJimenez/Air-Pollution", 52,
         size=6.9, color=INK2)

    flecha(ax, (73.3, 14.2), (81.6, 50.0), col=SEQ[450], lw=2.0, rad=-0.42)
    flecha(ax, (101.5, 43.6), (101.5, 40.0), col=SEQ[450], lw=1.8)
    flecha(ax, (101.5, 29.6), (101.5, 26.4), col=SEQ[450], lw=1.8)
    flecha(ax, (101.5, 16.0), (101.5, 12.8), col=SEQ[450], lw=1.8)

    # alcance
    wrap(ax, 101.5, 1.2, "Alcance AFG: estimación y validación contra SINCA — "
         "sin validación epidemiológica", 90, size=6.8, color=MUTED)

    path = os.path.join(OUT, "flujograma_datos.png")
    fig.savefig(path); plt.close(fig)
    print("->", path)


if __name__ == "__main__":
    main()
