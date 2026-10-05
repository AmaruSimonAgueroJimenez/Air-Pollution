"""Métricas de exposición por celda, desde las superficies horarias de 1 km.

Replica celda a celda las **once métricas vigentes** del proyecto hermano de neuroepidemiología
(`Neurodegen-Epidemiology-Chile/scripts_superficie/neurodeg_pm25_maxrr.py`), que allá se calculaban
por comuna × ventana de años:

===========================  ==========================================================  =============
métrica                      definición                                                  unidad
===========================  ==========================================================  =============
``media``                    media de las **medias diarias** del período                 µg/m³ · ppb
``p95``                      percentil 95 de las **medias diarias** (no de las horarias)  µg/m³ · ppb
``horas_sobre_U``            Σ horas con valor **estrictamente** > U, por año             h/año
``auc_sobre_U``              Σ máx(0, valor − U), por año (dosis = intensidad × duración) µg/m³·h/año
``n_episodios_U``            Σ rachas contiguas de horas > U, por año                     episodios/año
===========================  ==========================================================  =============

con U ∈ {15, 25, 50} µg/m³ en PM₂.₅ — guía OMS 2021 de 24 h, valor intermedio y norma chilena de 24 h
(D.S. 12/2011 MMA). Se agrega ``max_horario``, el máximo horario del período, que allá se calculaba
como primitiva diaria pero no entraba en la rejilla final.

**Dos decisiones nuevas, que no son réplica y hay que declarar como tales:**

* **La unidad temporal.** El proyecto de neuroepidemiología nunca calculó estas métricas por año ni
  por bienio: la exposición crónica era **un** valor por comuna por ventana larga. Agregar por bienio
  es una decisión de este proyecto.
* **Los umbrales de NO₂.** Allá no existen: todo el aparato de umbrales es de PM₂.₅. Aquí se usan los
  ``CORTES_DIARIOS`` que ya emplea el informe (13,3 · 26,6 · 63,8 ppb = guía OMS 2021 de 24 h de 25,
  50 y 120 µg/m³ a 25 °C), aplicados a valores horarios igual que allá se aplicaba a PM₂.₅ el corte
  de 24 h.

Además se corrige un artefacto del original: allá las rachas se cortaban en el límite de año porque
cada año se procesaba por separado. Aquí el estado de la última hora del año se guarda y lo usa el año
siguiente, de modo que un episodio que cruza el Año Nuevo se cuenta una sola vez, en su día de inicio.

**Reanudable.** Cada año se guarda al terminar, de forma atómica. Apagar el equipo cuesta, como mucho,
el año en curso (uno a dos minutos de cómputo). Relanzar el mismo comando continúa donde quedó.

    python -B scripts_modelo_1km/exposicion.py                       # todos los años disponibles
    python -B scripts_modelo_1km/exposicion.py --ventanas 2          # además, las métricas por bienio
    python -B scripts_modelo_1km/exposicion.py --ambito rm --ventanas 2
    python -B scripts_modelo_1km/exposicion.py --solo-estado
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

from _comun_modelo import (  # noqa: E402
    AMBITOS_GRILLA, ESCALA_SUPERFICIE, MODELO_ROOT, SUPERFICIES_ROOT, cargar_celdas, carpeta_ambito,
    celdas_de_ambito, leer_superficie_dia, log, publicar_json, publicar_parquet,
)

ESQUEMA = "airpollution.modelo-1km.exposicion.v1"
# Cortes de excedencia por contaminante. PM₂.₅: guía OMS 2021 de 24 h, intermedio y norma chilena de
# 24 h. NO₂: los mismos ``CORTES_DIARIOS`` del informe (guía OMS 2021 de 24 h, en ppb).
UMBRALES = {"pm25": (15.0, 25.0, 50.0), "no2": (13.3, 26.6, 63.8)}
NOMBRE_UMBRAL = {"pm25": {15.0: "15", 25.0: "25", 50.0: "50"},
                 "no2": {13.3: "13_3", 26.6: "26_6", 63.8: "63_8"}}


def raiz_exposicion(sufijo: str = "", ambito: str = "nacional") -> Path:
    return carpeta_ambito(MODELO_ROOT, "exposicion", sufijo, ambito)


def raiz_superficies(sufijo: str = "", ambito: str = "nacional") -> Path:
    return carpeta_ambito(SUPERFICIES_ROOT, "superficies", sufijo, ambito)


def dias_disponibles(pol: str, anio: int, sufijo: str = "", ambito: str = "nacional") -> list[Path]:
    d = raiz_superficies(sufijo, ambito) / pol / f"year={anio}"
    return sorted(d.rglob(f"{pol}_1km_*.nc")) if d.exists() else []


class AcumuladorAnual:
    """Recorre los días de un año sumando lo que cada métrica necesita, sin guardar las horas."""

    def __init__(self, pol: str, n_celdas: int, estado_previo: np.ndarray | None = None):
        self.pol, self.n = pol, n_celdas
        self.umbrales = UMBRALES[pol]
        self.suma_media = np.zeros(n_celdas, "float64")
        self.n_dias = np.zeros(n_celdas, "int32")
        self.max_horario = np.full(n_celdas, np.nan, "float32")
        self.horas = np.zeros((len(self.umbrales), n_celdas), "int32")
        self.auc = np.zeros((len(self.umbrales), n_celdas), "float64")
        self.episodios = np.zeros((len(self.umbrales), n_celdas), "int32")
        # Estado de la última hora del día anterior por umbral: hace que una racha cruce la medianoche
        # (y, si viene del año anterior, también el Año Nuevo).
        self.sobre_previo = (np.zeros((len(self.umbrales), n_celdas), bool)
                            if estado_previo is None else estado_previo.astype(bool))
        self.medias_diarias: list[np.ndarray] = []
        self.fechas: list[int] = []

    def dia(self, fecha: date, valores: np.ndarray) -> None:
        """``valores`` es (24, celdas) en la unidad del contaminante."""
        con_dato = np.isfinite(valores).any(axis=0)
        media = np.full(self.n, np.nan, "float64")
        maximo = np.full(self.n, np.nan, "float32")
        if con_dato.any():                       # nanmean de una columna toda NaN avisa y devuelve NaN
            media[con_dato] = np.nanmean(valores[:, con_dato], axis=0)
            maximo[con_dato] = np.nanmax(valores[:, con_dato], axis=0)
        self.suma_media += np.nan_to_num(media)
        self.n_dias += con_dato
        self.max_horario = np.fmax(self.max_horario, maximo.astype("float32"))
        self.medias_diarias.append(media.astype("float32"))
        self.fechas.append(fecha.toordinal())
        for k, u in enumerate(self.umbrales):
            sobre = valores > u                      # NaN > u es False, igual que en el original
            self.horas[k] += sobre.sum(axis=0, dtype="int32")
            self.auc[k] += np.where(sobre, valores - u, 0.0).sum(axis=0, dtype="float64")
            previo = np.vstack([self.sobre_previo[k][None, :], sobre[:-1]])
            self.episodios[k] += (sobre & ~previo).sum(axis=0, dtype="int32")
            self.sobre_previo[k] = sobre[-1]

    def tabla(self, celdas: np.ndarray) -> pd.DataFrame:
        with np.errstate(invalid="ignore", divide="ignore"):
            media = np.where(self.n_dias > 0, self.suma_media / np.maximum(self.n_dias, 1), np.nan)
        d = {"celda": celdas, "n_dias": self.n_dias, "suma_media_diaria": self.suma_media,
             "media": media.astype("float32"), "max_horario": self.max_horario}
        for k, u in enumerate(self.umbrales):
            s = NOMBRE_UMBRAL[self.pol][u]
            d[f"horas_sobre_{s}"] = self.horas[k]
            d[f"auc_sobre_{s}"] = self.auc[k].astype("float32")
            d[f"n_episodios_{s}"] = self.episodios[k]
        return pd.DataFrame(d)


def _ruta_anio(pol: str, anio: int, sufijo: str = "", ambito: str = "nacional") -> tuple[Path, Path, Path]:
    base = raiz_exposicion(sufijo, ambito) / pol
    base.mkdir(parents=True, exist_ok=True)
    return (base / f"anual_{anio}.parquet", base / f"diario_{anio}.npz", base / f"anual_{anio}.json")


def agregar_anio(pol: str, anio: int, celdas: np.ndarray, sufijo: str = "", forzar: bool = False,
                 ambito: str = "nacional") -> dict | None:
    """Agrega un año completo. Devuelve su resumen, o ``None`` si no hay superficies de ese año."""
    rutas = dias_disponibles(pol, anio, sufijo, ambito)
    if not rutas:
        return None
    p_anual, p_diario, p_meta = _ruta_anio(pol, anio, sufijo, ambito)
    # ``dias_previos`` entra en la firma porque el conteo de episodios arranca con el estado de la
    # última hora del año anterior: si ese año se re-agrega con más días, éste tiene que recalcularse.
    # La retransformación entra en la firma: si cambia, los NetCDF se reescalan y estas métricas,
    # que son niveles, dejan de corresponder.
    _meta_modelo = json.loads((MODELO_ROOT / "modelos" / f"{pol}{sufijo}" / "modelo_final.json")
                              .read_text(encoding="utf-8")) if (MODELO_ROOT / "modelos" / f"{pol}{sufijo}" /
                                                                "modelo_final.json").exists() else {}
    firma = {"esquema": ESQUEMA, "contaminante": pol, "anio": anio, "dias": len(rutas),
             "umbrales": list(UMBRALES[pol]), "celdas": int(len(celdas)), "ambito": ambito,
             "retransformacion": _meta_modelo.get("retransformacion"),
             "dias_previos": len(dias_disponibles(pol, anio - 1, sufijo, ambito))}
    if not forzar and p_anual.exists() and p_diario.exists():
        previo = json.loads(p_meta.read_text(encoding="utf-8")) if p_meta.exists() else {}
        if {k: previo.get(k) for k in firma} == firma:
            return previo

    # El estado de la última hora del año anterior, si ya se agregó, para no cortar la racha.
    estado = None
    p_prev = _ruta_anio(pol, anio - 1, sufijo, ambito)[1]
    if p_prev.exists():
        with np.load(p_prev) as z:
            if "sobre_final" in z and z["sobre_final"].shape[1] == len(celdas):
                estado = z["sobre_final"]

    t0 = time.perf_counter()
    acc = AcumuladorAnual(pol, len(celdas), estado)
    for ruta in rutas:
        _, celdas_nc, valores = leer_superficie_dia(ruta)
        if len(celdas_nc) != len(celdas) or celdas_nc[0] != celdas[0] or celdas_nc[-1] != celdas[-1]:
            raise SystemExit(f"{ruta} tiene otra grilla ({len(celdas_nc)} celdas) que {len(celdas)}; "
                             f"agrega por separado las superficies regionales y las nacionales.")
        acc.dia(date(*map(int, (ruta.stem[-8:-4], ruta.stem[-4:-2], ruta.stem[-2:]))), valores)

    tabla = acc.tabla(celdas)
    escala = ESCALA_SUPERFICIE[pol]
    diarias = np.vstack(acc.medias_diarias)
    cuant = np.where(np.isfinite(diarias), np.rint(diarias / escala), -32768).astype("int16")
    tmp = p_diario.with_suffix(".npz.part")
    with open(tmp, "wb") as fh:                  # por el manejador: savez_compressed le añade .npz al nombre
        np.savez_compressed(fh, fechas=np.array(acc.fechas, "int32"), celdas=celdas.astype("int64"),
                            media_diaria=cuant, escala=np.float32(escala), sobre_final=acc.sobre_previo)
    os.replace(tmp, p_diario)
    firma["sha256_anual"] = publicar_parquet(tabla, p_anual)
    firma.update({"media_nacional": float(np.nanmean(tabla["media"])),
                  "dias_con_dato_mediana": int(np.median(tabla["n_dias"])),
                  "minutos": round((time.perf_counter() - t0) / 60, 2)})
    publicar_json(firma, p_meta)
    # La clave del JSON se llama "media_nacional" por compatibilidad con los agregados ya
    # publicados; el log dice el ámbito real.
    log.info("exposición %s %s %d: %d días, media %.2f, %.1f min", pol, ambito, anio, len(rutas),
             firma["media_nacional"], firma["minutos"])
    return firma


def ventana(pol: str, y0: int, y1: int, sufijo: str = "", ambito: str = "nacional",
            anios: list[int] | None = None) -> pd.DataFrame | None:
    """Métricas de exposición del período por celda, con las definiciones del proyecto hermano.

    ``anios`` permite dar una lista explícita en vez del rango completo, para comparar contaminantes
    sobre exactamente los mismos años cuando uno de ellos todavía no tiene la serie entera.
    """
    candidatos = range(y0, y1 + 1) if anios is None else [a for a in anios if y0 <= a <= y1]
    anios = [a for a in candidatos if _ruta_anio(pol, a, sufijo, ambito)[0].exists()]
    if not anios:
        return None
    tablas = [pd.read_parquet(_ruta_anio(pol, a, sufijo, ambito)[0]) for a in anios]
    base = tablas[0][["celda"]].copy()
    ny = len(anios)
    suma = sum(t["suma_media_diaria"].to_numpy() for t in tablas)
    n_dias = sum(t["n_dias"].to_numpy() for t in tablas)
    with np.errstate(invalid="ignore", divide="ignore"):
        base["media"] = np.where(n_dias > 0, suma / np.maximum(n_dias, 1), np.nan).astype("float32")
    base["n_dias"] = n_dias
    base["max_horario"] = np.fmax.reduce([t["max_horario"].to_numpy() for t in tablas])
    # «por año» = tasa por 365,25 días **efectivamente cubiertos**, no el total dividido por el
    # número de parquet anuales presentes. 2026 llega sólo al 13 de septiembre y un año a medio
    # producir cubre menos tiempo todavía: dividir por ``ny`` los contaría como años enteros y
    # subestimaría la tasa (un 30 % en el caso de 2026). Con años completos ambas coinciden.
    with np.errstate(invalid="ignore", divide="ignore"):
        factor = np.where(n_dias > 0, 365.25 / np.maximum(n_dias, 1), np.nan)
    for col in [c for c in tablas[0].columns if c.startswith(("horas_sobre_", "auc_sobre_", "n_episodios_"))]:
        base[col] = (sum(t[col].to_numpy(dtype="float64") for t in tablas) * factor).astype("float32")
    # p95 de las medias diarias: exige las medias diarias de todos los años de la ventana.
    diarias = []
    for a in anios:
        with np.load(_ruta_anio(pol, a, sufijo, ambito)[1]) as z:
            v = z["media_diaria"].astype("float32")
            v[v == -32768] = np.nan
            diarias.append(v * float(z["escala"]))
    d = np.vstack(diarias)
    with np.errstate(invalid="ignore"):       # un solo pase: ordenar 838.430 columnas es lo caro
        q = np.nanpercentile(d, [95, 98], axis=0)
    base["p95"], base["p98"] = q[0].astype("float32"), q[1].astype("float32")
    base["anios"] = ny
    base["periodo"] = f"{y0}–{y1}" if y1 > y0 else str(y0)
    return base


def ventanas_publicadas(pol: str, y0: int, y1: int, salto: int, sufijo: str = "",
                        ambito: str = "nacional") -> list[Path]:
    """Publica una tabla por ventana de ``salto`` años dentro de [y0, y1]."""
    fuera = []
    for a in range(y0, y1 + 1, salto):
        b = min(a + salto - 1, y1)
        t = ventana(pol, a, b, sufijo, ambito)
        if t is None or t.empty:
            continue
        ruta = raiz_exposicion(sufijo, ambito) / pol / f"ventana_{a}_{b}.parquet"
        publicar_parquet(t, ruta)
        fuera.append(ruta)
        log.info("exposición %s %s %s: media %.2f, p95 %.2f", pol, ambito, t["periodo"].iloc[0],
                 float(np.nanmean(t["media"])), float(np.nanmean(t["p95"])))
    return fuera


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--contaminantes", default="pm25,no2")
    p.add_argument("--desde", type=int, default=2000)
    p.add_argument("--hasta", type=int, default=2026)
    p.add_argument("--ventanas", type=int, default=0, help="además, publica métricas por ventana de N años")
    p.add_argument("--ambito", default="nacional", choices=sorted(AMBITOS_GRILLA))
    p.add_argument("--sufijo", default=None)
    p.add_argument("--forzar", action="store_true")
    p.add_argument("--solo-estado", action="store_true")
    args = p.parse_args(argv)
    sufijo = args.sufijo if args.sufijo is not None else (f"_{e}" if (e := os.environ.get("MODELO_1KM_ETIQUETA", "")) else "")
    pols = tuple(c.strip() for c in args.contaminantes.split(",") if c.strip())

    logging.getLogger("modelo_1km").setLevel(logging.INFO)
    if not logging.getLogger("modelo_1km").handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
        logging.getLogger("modelo_1km").addHandler(h)

    if args.solo_estado:
        for pol in pols:
            base = raiz_exposicion(sufijo, args.ambito) / pol
            hechos = sorted(int(f.stem.split("_")[1]) for f in base.glob("anual_*.parquet")) if base.exists() else []
            disp = [a for a in range(args.desde, args.hasta + 1) if dias_disponibles(pol, a, sufijo, args.ambito)]
            print(f"{pol}: {len(hechos)} años agregados de {len(disp)} con superficies")
            print(f"   agregados: {hechos}")
            print(f"   pendientes: {[a for a in disp if a not in hechos]}")
        return 0

    celdas = celdas_de_ambito(cargar_celdas(), args.ambito)["celda"].to_numpy(dtype="int64")
    print(f"ámbito {args.ambito}: {len(celdas):,} celdas", flush=True)
    for pol in pols:
        for anio in range(args.desde, args.hasta + 1):
            r = agregar_anio(pol, anio, celdas, sufijo, args.forzar, args.ambito)
            if r is None:
                continue
            print(f"{pol} {anio}: {r['dias']} días, media {r['media_nacional']:.2f}", flush=True)
        if args.ventanas:
            ventanas_publicadas(pol, args.desde, args.hasta, args.ventanas, sufijo, args.ambito)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
