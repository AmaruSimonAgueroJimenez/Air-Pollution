#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Figura: la brecha de monitoreo SINCA, cuantificada (datos reales del repo)."""

import os
import json
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

INK = "#0b0b0b"; INK2 = "#52514e"; MUTED = "#898781"
GRID = "#e1e0d9"
SEQ = {450: "#2a78d6", 600: "#184f95", 700: "#0d366b"}

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Carlito", "Calibri", "Liberation Sans", "DejaVu Sans"],
    "figure.facecolor": "#ffffff", "savefig.facecolor": "#ffffff",
    "figure.dpi": 300, "savefig.dpi": 300,
    "savefig.bbox": "tight", "savefig.pad_inches": 0.05,
    "axes.edgecolor": GRID, "axes.linewidth": 0.8,
})

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "assets")

cfg = pd.DataFrame(json.load(open(os.path.join(HERE, "config_sinca_estaciones.json"))))
man = pd.read_csv(os.path.join(HERE, "manifiesto_descarga.csv"))

ORDEN = ["Arica y Parinacota", "Tarapacá", "Antofagasta", "Atacama", "Coquimbo",
         "Valparaíso", "Metropolitana", "O'Higgins", "Maule", "Ñuble", "Biobío",
         "Araucanía", "Los Ríos", "Los Lagos", "Aysén", "Magallanes"]
MACRO = {"Arica y Parinacota": "Norte Grande", "Tarapacá": "Norte Grande", "Antofagasta": "Norte Grande",
         "Atacama": "Norte Chico", "Coquimbo": "Norte Chico",
         "Valparaíso": "Centro", "Metropolitana": "Centro", "O'Higgins": "Centro", "Maule": "Centro",
         "Ñuble": "Sur", "Biobío": "Sur", "Araucanía": "Sur", "Los Ríos": "Sur", "Los Lagos": "Sur",
         "Aysén": "Austral", "Magallanes": "Austral"}
CZONA = {"Norte Grande": "#B24E1C", "Norte Chico": "#eb6834", "Centro": "#2a78d6",
         "Sur": "#184f95", "Austral": "#0F7D57"}

cfg["macro"] = cfg["nombre_region"].map(MACRO)
geo = cfg[pd.to_numeric(cfg.lat, errors="coerce").between(-56.6, -17.0)].copy()

fig = plt.figure(figsize=(9.6, 3.78))
gs = fig.add_gridspec(1, 3, width_ratios=[1.0, 1.05, 1.05], wspace=0.36,
                      left=0.045, right=0.985, top=0.86, bottom=0.15)

# ---------- Panel A: mapa de Chile con las estaciones ----------
import geopandas as gpd
MAPA = os.path.join(HERE, "chile_regiones_simplificado.geojson")
regiones = gpd.read_file(MAPA)
COD_MACRO = {15: "Norte Grande", 1: "Norte Grande", 2: "Norte Grande",
             3: "Norte Chico", 4: "Norte Chico",
             5: "Centro", 13: "Centro", 6: "Centro", 7: "Centro",
             16: "Sur", 8: "Sur", 9: "Sur", 14: "Sur", 10: "Sur",
             11: "Austral", 12: "Austral"}
regiones["macro"] = regiones["codregion"].map(COD_MACRO)

# solo estaciones cuyo punto cae dentro de Chile (algunas traen longitud errónea)
_chile = regiones.union_all()
_pts = gpd.points_from_xy(geo.lon, geo.lat)
geo = geo[[p.within(_chile) or p.distance(_chile) < 0.30 for p in _pts]]
NGEO = len(geo)

ax = fig.add_subplot(gs[0])
for z, sub in regiones.dropna(subset=["macro"]).groupby("macro"):
    sub.plot(ax=ax, color=CZONA[z], alpha=0.18, edgecolor="#b9b8b0",
             linewidth=0.45, zorder=1)
regiones[regiones["macro"].isna()].plot(ax=ax, color="#eceae2", edgecolor="#b9b8b0",
                                        linewidth=0.4, zorder=1)
for z, sub in geo.groupby("macro"):
    ax.scatter(sub.lon, sub.lat, s=30, color=CZONA[z], alpha=0.95,
               edgecolors="#ffffff", linewidths=0.45, zorder=3)
ax.set_xlim(-77.8, -62.6); ax.set_ylim(-56.4, -17.0)
ax.set_aspect(1.25)
ax.set_xticks([]); ax.set_yticks([])
for s in ("top", "right", "bottom", "left"):
    ax.spines[s].set_visible(False)
cuenta = cfg.groupby("macro").size()
zlab = [("Norte Grande", -21.6), ("Norte Chico", -29.1), ("Centro", -34.0),
        ("Sur", -39.6), ("Austral", -49.6)]
for z, ylab in zlab:
    ax.text(-67.0, ylab, f"{z}\n{int(cuenta.get(z, 0))} estaciones", fontsize=11,
            color=CZONA[z], ha="left", va="center", weight="bold", linespacing=1.12)
ax.set_title("1 · Mapa de la red", fontsize=11.5, weight="bold",
             color=SEQ[700], loc="left", pad=8)
ax.text(0.5, -0.045, f"se muestran las {NGEO} de {len(cfg)} estaciones con coordenadas válidas",
        fontsize=8.2, color=MUTED, ha="center", transform=ax.transAxes)

# ---------- Panel B: estaciones por región ----------
ax = fig.add_subplot(gs[1])
por_reg = cfg.groupby("nombre_region").size().reindex(ORDEN)
ypos = range(len(ORDEN) - 1, -1, -1)
cols = [CZONA[MACRO[r]] for r in ORDEN]
ax.barh(list(ypos), por_reg.values, color=cols, height=0.68, zorder=3)
ax.set_yticks(list(ypos))
ax.set_yticklabels(ORDEN, fontsize=9.6, color=INK)
for y, v in zip(ypos, por_reg.values):
    ax.text(v + 0.5, y, str(v), fontsize=9.2, color=INK2, va="center")
ax.set_xlim(0, 30)
ax.set_xticks([0, 10, 20, 30])
ax.tick_params(axis="x", labelsize=8.8, colors=INK2, length=0)
ax.grid(axis="x", color=GRID, lw=0.7, zorder=0)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.set_title("2 · Estaciones por región",
             fontsize=11.5, weight="bold", color=SEQ[700], loc="left", pad=8)

# ---------- Panel C: cobertura por contaminante ----------
ax = fig.add_subplot(gs[2])
cov = man.groupby("contaminante").estacion.nunique()
orden_c = ["pm25", "pm10", "so2", "no2", "o3", "co"]
lab_c = {"pm25": "PM$_{2.5}$", "pm10": "PM$_{10}$", "so2": "SO$_2$", "no2": "NO$_2$", "o3": "O$_3$", "co": "CO"}
vals = [int(cov[c]) for c in orden_c]
ypos = range(len(orden_c) - 1, -1, -1)
colsc = [SEQ[600] if c.startswith("pm") else "#B24E1C" for c in orden_c]
ax.barh(list(ypos), vals, color=colsc, height=0.6, zorder=3)
ax.barh(list(ypos), [109] * 6, color="#f0efe9", height=0.6, zorder=1)
ax.set_yticks(list(ypos))
ax.set_yticklabels([lab_c[c] for c in orden_c], fontsize=11.5, color=INK)
for y, v in zip(ypos, vals):
    ax.text(v + 1.5, y, f"{v}  ({v/109:.0%})", fontsize=9.6, color=INK2, va="center")
ax.set_xlim(0, 109)
ax.set_xticks([])
for s in ("top", "right", "left", "bottom"):
    ax.spines[s].set_visible(False)
ax.set_title("3 · Datos por contaminante",
             fontsize=11.5, weight="bold", color=SEQ[700], loc="left", pad=8)
ax.text(2, -0.72, "material particulado en azul · gases en naranjo: los gases tienen la mitad de la red",
        fontsize=8.8, color=MUTED)

fig.text(0.045, 0.035,
         "Comunas con al menos una estación: 61 de 345 · comunas sin ninguna: 284 (82 %). "
         "Fuente: red SINCA (MMA), configuración y manifiesto de descarga del repositorio del proyecto (2019–2024).",
         fontsize=8.8, color=MUTED)

path = os.path.join(OUT, "brecha_sinca.png")
fig.savefig(path)
print("->", path)
