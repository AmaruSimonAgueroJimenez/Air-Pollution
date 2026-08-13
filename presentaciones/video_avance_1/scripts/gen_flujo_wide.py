#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Flujograma compacto (formato ancho) para la plantilla UC de 10×5,625 in."""

import os
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

INK = "#0b0b0b"; INK2 = "#52514e"; MUTED = "#898781"
GRID = "#e1e0d9"; AXIS = "#c3c2b7"
ORANGE = "#B24E1C"; AQUA = "#0F7D57"
SEQ = {350: "#5598e7", 450: "#2a78d6", 600: "#184f95", 700: "#0d366b"}
UCBLUE = "#3366CC"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Carlito", "Calibri", "Liberation Sans", "DejaVu Sans"],
    "figure.facecolor": "#ffffff", "savefig.facecolor": "#ffffff",
    "figure.dpi": 300, "savefig.dpi": 300,
    "savefig.bbox": "tight", "savefig.pad_inches": 0.04,
})

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")


def caja(ax, x, y, w, h, fc, ec="none", lw=1.0, r=0.9, z=2):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                 boxstyle=f"round,pad=0,rounding_size={r}", facecolor=fc,
                 edgecolor=ec, linewidth=lw, zorder=z))


def wrap(ax, x, y, text, width, size=8.0, color=INK, weight="normal",
         ha="center", va="center", lh=1.22, z=4):
    ax.text(x, y, "\n".join(textwrap.wrap(text, width)), fontsize=size,
            color=color, weight=weight, ha=ha, va=va, linespacing=lh, zorder=z)


def flecha(ax, p1, p2, col=AXIS, lw=1.6, ms=12, rad=0.0, z=1):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=ms,
                 color=col, lw=lw, shrinkA=2, shrinkB=2, zorder=z,
                 connectionstyle=f"arc3,rad={rad}"))


fig = plt.figure(figsize=(12.4, 5.28))
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 122); ax.set_ylim(0, 52)
ax.axis("off")

# ---------------- encabezados de columna ----------------
for x, t in [(19.0, "1 · FUENTES DE DATOS"), (56.5, "2 · PIPELINE REPRODUCIBLE"),
             (101.5, "3 · PRODUCTOS")]:
    ax.text(x, 50.6, t, fontsize=10.5, weight="bold", color=SEQ[700],
            ha="center", va="center")

# ---------------- columna 1: fuentes ----------------
chips = [
    (SEQ[600], "SATÉLITES: GASES Y AEROSOL",
     ["Sentinel-5P TROPOMI (2018+) · Aura OMI (2004+)",
      "Terra MOPITT, CO (2000+) · MODIS MAIAC/AOD"]),
    (SEQ[450], "REANÁLISIS Y SUPERFICIES",
     ["CAMS EAC4 (2003+) · NASA GEOS-CF (2018+)",
      "MERRA-2 aerosoles · ACAG PM₂.₅ superficie"]),
    (AQUA, "PREDICTORES COMUNES",
     ["ERA5 / ERA5-Land · ESA CCI suelo · OSM vial",
      "NASADEM · luces VIIRS · censo (población, leña)"]),
    (ORANGE, "VERDAD-TERRENO",
     ["Red SINCA (MMA): 109 estaciones",
      "6 contaminantes · resolución horaria"]),
]
H, GAP = 10.5, 1.35
ytop = 48.6
mids = []
for col, tit, lineas in chips:
    caja(ax, 1.5, ytop - H, 35.0, H, "#ffffff", ec=col, lw=1.5)
    caja(ax, 1.5, ytop - 3.1, 35.0, 3.1, col, r=0.9)
    caja(ax, 1.5, ytop - 3.1, 35.0, 1.2, col, r=0.0)
    ax.text(19.0, ytop - 1.55, tit, fontsize=8.1, weight="bold",
            color="#ffffff", ha="center", va="center", zorder=4)
    y = ytop - 3.1 - 1.9
    for ln in lineas:
        ax.text(19.0, y, ln, fontsize=7.3, color=INK, ha="center",
                va="center", zorder=4)
        y -= 3.15
    mids.append(ytop - H / 2)
    ytop -= H + GAP

# ---------------- columna 2: pipeline ----------------
pasos = [
    ("Descarga programática por contaminante", "scripts_pipeline/ · credenciales .env · reintentos"),
    ("Recorte a Chile «al vuelo»", "gránulos globales → bbox Chile (~5 % del volumen)"),
    ("Agregación comuna × hora / día", "345 comunas · raw_chile/ → comunal_horario/"),
    ("Panel de modelamiento", "predictores + meteorología + estáticos, unidos a SINCA"),
]
PH, PGAP = 7.6, 1.15
py = 48.6
for t1, t2 in pasos:
    caja(ax, 40.0, py - PH, 33.0, PH, "#f4f7fc", ec=SEQ[350], lw=1.3)
    wrap(ax, 56.5, py - PH / 2 + 1.35, t1, 40, size=8.3, weight="bold")
    wrap(ax, 56.5, py - PH / 2 - 1.55, t2, 52, size=7.0, color=INK2)
    if py < 48.6:
        flecha(ax, (56.5, py + PGAP - 0.1), (56.5, py + 0.1), col=SEQ[450], lw=1.7)
    py -= PH + PGAP

caja(ax, 40.0, 1.6, 33.0, 8.4, "#fdf2ec", ec=ORANGE, lw=1.5)
wrap(ax, 56.5, 7.7, "Modelos de estimación por contaminante", 40, size=8.3, weight="bold")
wrap(ax, 56.5, 5.1, "GWR · gradient boosting (LightGBM) · kriging", 52, size=7.1, color=INK2)
wrap(ax, 56.5, 3.1, "Validación cruzada dejando una estación fuera (LOSO)", 56, size=7.1, color=INK2)
flecha(ax, (56.5, py + PGAP - 0.1), (56.5, 10.1), col=SEQ[450], lw=1.7)

# entradas desde la columna 1 (conectores ortogonales)
CONN = SEQ[450]


def codo(pts, col=CONN, lw=1.6, z=1):
    """Polilínea ortogonal con punta de flecha en el último tramo."""
    xs = [p[0] for p in pts[:-1]]
    ys = [p[1] for p in pts[:-1]]
    ax.plot(xs, ys, color=col, lw=lw, zorder=z,
            solid_capstyle="round", solid_joinstyle="round")
    ax.add_patch(FancyArrowPatch(pts[-2], pts[-1], arrowstyle="-|>",
                 mutation_scale=13, color=col, lw=lw,
                 shrinkA=0, shrinkB=2, zorder=z))


XCOL = 38.3
for m_ in mids[:3]:
    ax.plot([36.5, XCOL], [m_, m_], color=CONN, lw=1.4, zorder=1,
            solid_capstyle="round")
codo([(XCOL, mids[2]), (XCOL, 44.8), (39.9, 44.8)], lw=1.5)
flecha(ax, (36.5, mids[3]), (39.8, mids[3]), col=ORANGE, lw=1.8)
ax.text(38.65, 11.9, "SINCA:\nsolo verdad-\nterreno", fontsize=6.0, color=ORANGE,
        ha="center", va="center", linespacing=1.15, zorder=4)

# ---------------- columna 3: productos ----------------
caja(ax, 84.0, 37.2, 35.0, 10.6, SEQ[700], r=1.0)
wrap(ax, 101.5, 44.8, "Superficies de exposición", 32, size=9.3, weight="bold", color="#ffffff")
wrap(ax, 101.5, 41.9, "PM₂.₅ · PM₁₀ · NO₂ · O₃ · SO₂ · CO", 44, size=8.0, color="#ffffff")
wrap(ax, 101.5, 39.3, "comuna × hora / día · todo Chile", 44, size=7.2, color="#cde2fb")

caja(ax, 84.0, 27.4, 35.0, 7.6, "#ffffff", ec=SEQ[600], lw=1.4)
wrap(ax, 101.5, 32.6, "Agregación por macrozona", 40, size=8.4, weight="bold")
wrap(ax, 101.5, 29.9, "Norte Grande · Norte Chico · Centro · Sur · Austral", 46, size=7.0, color=INK2)

caja(ax, 84.0, 17.6, 35.0, 7.6, "#ffffff", ec=SEQ[600], lw=1.4)
wrap(ax, 101.5, 22.8, "Métricas de validación por estación", 40, size=8.4, weight="bold")
wrap(ax, 101.5, 20.1, "R² · RMSE · sesgo, por contaminante y zona", 46, size=7.0, color=INK2)

caja(ax, 84.0, 8.6, 35.0, 6.9, "#f4f5f2", ec=GRID, lw=1.2)
wrap(ax, 101.5, 13.3, "Repositorio abierto y reproducible", 42, size=8.2, weight="bold")
wrap(ax, 101.5, 10.7, "github.com/AmaruSimonAgueroJimenez/Air-Pollution", 60, size=6.6, color=INK2)

codo([(73.15, 5.8), (78.6, 5.8), (78.6, 42.5), (83.9, 42.5)], lw=1.9)
for a, b in [(36.8, 35.0), (27.0, 25.2), (17.2, 15.5)]:
    flecha(ax, (101.5, a), (101.5, b), col=SEQ[450], lw=1.6)

wrap(ax, 101.5, 5.6, "Alcance AFG: estimación y validación contra SINCA, sin validación epidemiológica", 52, size=6.6, color=MUTED)

path = os.path.join(OUT, "flujograma_wide.png")
fig.savefig(path); plt.close(fig)
print("->", path)
