#!/usr/bin/env python3
"""Pliegues, pesos, bloque más influyente y evaluabilidad de E2 de la red ampliada (R13 a R16): una sola fuente.

Vuelve a aplicar, **sin cambiar ningún parámetro**, las reglas de ``pliegues_v2`` (§1, Enmienda 1 puntos 1.1, 8 y 13,
y Complemento punto 5) al universo de la red 2: LOSO-D por componentes conexas a ≤ 2 km que unen celdas compartidas;
LBO-10 y el amortiguador de BLQ-75 de 10 km; rejilla de 75 km en EPSG:32719 con origen (0, 0); LRO por región SINCA
con RXVI → RVIII; LPO por cuatrienios; k = posición lexicográfica de la etiqueta y semilla [42, k]; haversine con
R = 6.371 km. Las funciones son las de ``pliegues_v2`` (``completar_universo``, ``construir_contaminante``,
``parametros_de``, ``registro_estaciones`` y ``huella_pliegues``), importadas tal cual; aquí cambia la entrada:

* el universo de los radios son las estaciones con celda de la red 2 (los dos maestros de R8 más SNIFA, con los
  enlaces v1 y los de las estaciones nuevas, ``panel_red2_v2.estaciones_con_celda_red2``);
* los paneles son ``panel_{pm25,no2}_red2.parquet`` de la raíz v2.

**Una sola fuente (M1).** ``<raíz v2>/pliegues_v2_red2.json`` es el único manifiesto de la red ampliada: trae los
pliegues y, en el mismo archivo, los pesos (R14), el bloque más influyente (R16) y la evaluabilidad de E2 (R15). Lo fija
sólo este programa; ``pliegues_v2.py`` deja de fijar pliegues cuando la configuración trae ``red_de_monitores`` (ver
la propuesta), porque su registro del panel es otro y su huella no sería la misma. Al fijarlo por primera vez se hace el
reemplazo de R13: ``pliegues_v2.json`` (f001d48c…, huella 3e9f5acd…) pasa intacto a ``pliegues_v2_reemplazado_<marca>.json``
y la bitácora nueva empieza con el evento «reemplazo». El anexo «Registro de la red v2» (R22, paso 4) escribe la
huella de este archivo en la configuración y ``exigir_registro`` la exige antes de usarlo.

Registra, antes de cualquier ajuste:

* **pesos (R14):** el peso fijo de cada estación (``metricas_v2.peso_fijo_por_estacion``), el desagrupamiento con la
  población comunal del INE (obligatoria al fijar), el número de Kish y el G efectivo por protocolo, con W = peso fijo
  × filas (como los pares de ``metricas_v2``) y sin ponderar;
* **bloque más influyente (R16):** en LRO y BLQ-75, el grupo de mayor peso poblacional sumado en los dos
  contaminantes, con la lectura T1(1) del autor (peso fijo × filas; ``decisiones_autor_traduccion_20261025.md``); se
  informa también la suma de pesos fijos, y si no es RM o E004N083 se dice;
* **evaluabilidad de E2 (R15):** con las banderas ``calidad_<pol>_red2.parquet`` (obligatorias al fijar) y la regla de
  ``metricas_v2.evaluabilidad_e2`` (≥ 50 % del peso de E1 y ≥ 5 grupos con E2, nivel diario civil), por protocolo, con
  los umbrales, los códigos de E2 y el mínimo de horas del día leídos de la configuración, como en la decisión. Al
  fijar, cada bandera y cada panel tienen que ser los que declara el json de su panel (``calidad_sha256`` y
  ``sha256``) y la bandera se alinea por estación y hora. En la decisión rige ésta, la registrada antes del ajuste
  (``evaluabilidad_e2_que_rige``, que usa ``correr_v2.decidir``);
* **regímenes (R17):** los tramos comunes de ``paneles/regimenes_red2.json``, con su sha256, comprobados contra los
  ``regimenes`` de los json de los paneles; van en el mismo manifiesto, bajo ``huella_pesos``.

Nada se escribe antes de confirmar la traducción en git (R22). ``--anexo`` arma, sin escribir nada, el bloque completo
del anexo «Registro de la red v2» (R22, paso 4) desde los artefactos y lo valida con ``exigir_registro`` antes de
mostrarlo (``anexo_desde_artefactos`` y ``con_el_anexo``): entre otras cosas, la traducción con que se escribieron
todos los artefactos del armado, que tiene que ser la misma (``traduccion_comun``), y el estado de la procedencia de la
descarga (``procedencia_descarga_desde_artefactos``). Ningún ajuste corre con un ``config_v2.json`` sin confirmar en git
(``exigir_registro`` → ``red_ampliada_v2.exigir_config_confirmada``).

Uso::

    python -B scripts_modelo_1km/v2/pliegues_red2_v2.py --no-escribir
    python -B scripts_modelo_1km/v2/pliegues_red2_v2.py --motivo "Enmienda 2, bloque de la red ampliada (R13)"
    python -B scripts_modelo_1km/v2/pliegues_red2_v2.py --anexo          # muestra el anexo para pegarlo (no escribe)
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from _traza_v2 import fijar_hilos  # noqa: E402

if __name__ == "__main__":
    from _rutas_v2 import hilos_de_la_linea  # noqa: E402
    fijar_hilos(hilos_de_la_linea())

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import _rutas_v2 as rv  # noqa: E402
import metricas_v2 as mv  # noqa: E402
import pliegues_v2 as pv  # noqa: E402
import red_ampliada_v2 as ra  # noqa: E402
from _traza_v2 import sha256_archivo, sha256_json, traza  # noqa: E402

log = logging.getLogger("modelo_1km_v2.pliegues_red2")

SCHEMA = "airpollution.modelo-1km-v2.pliegues-red2.v1"
NOMBRE = "pliegues_v2_red2.json"
NOMBRE_PANEL = "panel_{pol}_red2.parquet"
NOMBRE_CALIDAD = "calidad_{pol}_red2.parquet"
CONTAMINANTES = pv.CONTAMINANTES
PROTOCOLOS = pv.PROTOCOLOS
COLUMNAS = ["estacion", "celda", "region_sinca", "lat_est", "lon_est", "anio", "pob_dens"]
NOMBRADOS_ENMIENDA_1 = {"LRO": "RM", "BLQ-75": "E004N083"}
# R15, «con los mismos umbrales»: los códigos de E2 y el mínimo de horas del día civil no son constantes de este módulo;
# se leen de la configuración, como en la decisión (evaluabilidad_e2_red2).
MANIFIESTO_VIGENTE = {"archivo": "pliegues_v2.json",
                      "sha256": "f001d48ca14a14a7f11c748f7ea1d349977727468cd8ed0d7bbb0f5092895053",
                      "huella_pliegues_prefijo": "3e9f5acd"}
NOMBRE_VIGENTE_ORIGINAL = "pliegues_v2.json"

# Un solo candado para los dos manifiestos (el original y el de la red 2): «pliegues». Así el reemplazo de R13, que
# toca ambos, y ``pliegues_v2.anotar_bitacora`` (que ya toma «pliegues») no pueden cruzarse.
rv.registrar_candado("raiz_v2", r"pliegues_v2_red2(?:_reemplazado_[^/]+)?\.json", "pliegues")


# ---------------------------------------------------------------------------
# Panel de la red 2
# ---------------------------------------------------------------------------
def leer_panel_red2(ruta: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Como ``pliegues_v2.leer_panel`` (mismas comprobaciones) sobre un panel de la red 2, más ``pob_dens`` para los
    pesos. Devuelve (por estación, filas por estación × año, columnas de la fila para los pesos)."""
    import pyarrow.parquet as pq

    if not Path(ruta).exists():
        raise SystemExit(f"Falta el panel de la red 2 {Path(ruta).name}")
    df = pq.read_table(ruta, columns=COLUMNAS, read_dictionary=["estacion", "region_sinca"]).to_pandas()
    df["estacion"] = df["estacion"].astype(str)
    df["region_sinca"] = df["region_sinca"].astype(str)
    g = df.groupby("estacion", sort=True)
    por_est = pd.DataFrame({
        "celda": g["celda"].first(), "n_celdas": g["celda"].nunique(),
        "region_sinca": g["region_sinca"].first().astype(str), "n_regiones": g["region_sinca"].nunique(),
        "lat_est": g["lat_est"].first(), "lon_est": g["lon_est"].first(),
        "n_coordenadas": g["lat_est"].nunique() + g["lon_est"].nunique() - 1, "filas": g.size()})
    por_est.index.name = "estacion"
    raras = por_est[(por_est["n_celdas"] > 1) | (por_est["n_regiones"] > 1) | (por_est["n_coordenadas"] > 1)]
    if len(raras):
        raise SystemExit(f"estaciones con más de una celda, región o coordenada en el panel: {list(raras.index)}")
    conteos = df.groupby(["estacion", "anio"], sort=True).size().rename("filas").reset_index()
    conteos["anio"] = conteos["anio"].astype("int64")
    filas = df[["estacion", "anio", "pob_dens"]]
    return por_est.drop(columns=["n_celdas", "n_regiones", "n_coordenadas"]), conteos, filas


# ---------------------------------------------------------------------------
# Pesos, bloque más influyente y evaluabilidad (funciones puras)
# ---------------------------------------------------------------------------
def _finito(x):
    """float, o None si no es finito (el JSON no lleva NaN)."""
    x = float(x)
    return x if np.isfinite(x) else None


def pesos_fijos(filas: pd.DataFrame) -> pd.Series:
    """Peso fijo por estación (R14 / Enmienda 1, punto 4): ``metricas_v2.peso_fijo_por_estacion``."""
    est = filas["estacion"].astype(str).to_numpy()
    nombres, cod = np.unique(est, return_inverse=True)
    w = mv.peso_fijo_por_estacion(cod.ravel(), filas["anio"].to_numpy("int64"), filas["pob_dens"].to_numpy("float64"))
    return pd.Series(w[: len(nombres)], index=nombres, name="peso_fijo")


def grupo_de_estacion(protocolo: dict) -> dict[str, str]:
    """Grupo de prueba de cada estación en un protocolo espacial (cada estación es de prueba en un solo pliegue)."""
    out = {}
    for f in protocolo["pliegues"]:
        for s in f["estaciones_prueba"]:
            if s in out:
                raise ValueError(f"{s} es de prueba en dos pliegues")
            out[s] = f["grupo"]
    return out


def resumen_pesos(pol_d: dict, peso: pd.Series, filas_est: dict[str, int]) -> dict:
    """Kish y G efectivo por protocolo espacial, ponderados (W = peso fijo × filas) y sin ponderar (W = filas)."""
    est = sorted(filas_est)
    w_fila = np.array([float(peso.get(s, np.nan)) * filas_est[s] for s in est])
    n = np.array([filas_est[s] for s in est], dtype="float64")
    out = {"estaciones": len(est), "sin_peso_finito": [s for s in est if not np.isfinite(peso.get(s, np.nan))],
           "kish": {"ponderado": _finito(mv.n_efectivo(w_fila)), "sin_ponderar": _finito(mv.n_efectivo(n))},
           "G_efectivo": {}}
    for prot in PROTOCOLOS:
        if prot == "LPO":
            continue
        gde = grupo_de_estacion(pol_d["protocolos"][prot])
        tot_w, tot_n = {}, {}
        for s, wf, nf in zip(est, w_fila, n):
            g = gde[s]
            tot_w[g] = tot_w.get(g, 0.0) + (wf if np.isfinite(wf) else 0.0)
            tot_n[g] = tot_n.get(g, 0.0) + nf
        out["G_efectivo"][prot] = {"G": len(tot_n), "ponderado": _finito(mv.n_efectivo(list(tot_w.values()))),
                                   "sin_ponderar": _finito(mv.n_efectivo(list(tot_n.values())))}
    return out


def bloque_mas_influyente(por_pol: dict, pesos: dict[str, pd.Series], filas: dict[str, dict[str, int]]) -> dict:
    """R16: en LRO y BLQ-75, el grupo de mayor peso poblacional sumado en los dos contaminantes. Lectura que rige: W
    del grupo = Σ peso fijo × filas de sus estaciones (el peso de sus pares en ``metricas_v2``); se informa también
    con W = Σ pesos fijos. Empate: la etiqueta menor."""
    out = {}
    for prot in ("LRO", "BLQ-75"):
        con_filas, sin_filas = {}, {}
        for pol, d in por_pol.items():
            for s, g in grupo_de_estacion(d["protocolos"][prot]).items():
                w = float(pesos[pol].get(s, np.nan))
                if not np.isfinite(w):
                    continue
                con_filas[g] = con_filas.get(g, 0.0) + w * filas[pol][s]
                sin_filas[g] = sin_filas.get(g, 0.0) + w
        elegir = lambda tot: min(tot, key=lambda g: (-tot[g], g)) if tot else None  # noqa: E731
        rige, alt = elegir(con_filas), elegir(sin_filas)
        total = sum(con_filas.values())
        out[prot] = {"grupo": rige, "fraccion_del_peso": (con_filas[rige] / total) if rige and total else None,
                     "lectura": "Σ peso fijo × filas, sumado en PM2,5 y NO2",
                     "con_suma_de_pesos_fijos": alt, "coinciden": rige == alt,
                     "nombrado_por_la_enmienda_1": NOMBRADOS_ENMIENDA_1[prot],
                     "cambia": rige != NOMBRADOS_ENMIENDA_1[prot],
                     "ranking": [{"grupo": g, "peso": con_filas[g]} for g in sorted(con_filas, key=lambda g: (-con_filas[g], g))[:5]]}
    return out


def evaluabilidad_e2_red2(pol_d: dict, panel: pd.DataFrame, calidad: pd.DataFrame, cfg: dict) -> dict:
    """R15: evaluabilidad de E2 por protocolo con la regla de ``metricas_v2.evaluabilidad_e2``, antes de cualquier
    ajuste y «con los mismos umbrales» que la decisión (``correr_v2.evidencia_de_decision``), todos leídos de la
    configuración (ronda 5 de la traducción, menor 9): la fracción del peso y los grupos
    (``metricas_v2.evaluabilidad_de_config``), los códigos de E2 (``metricas_v2.codigos_evaluacion_de_config``: hoy
    ``validado`` de SINCA y ``usable_native`` de SNIFA) y el mínimo de horas del día civil
    (``metricas.niveles.diario.minimo_horas``). E1 son todas las filas del panel; el grupo de cada fila es el del
    protocolo (la región en LRO, el bloque en BLQ-75), no la estación. No usa predicciones ni observaciones: sólo
    filas, días y pesos fijos.

    ``panel``: ``estacion``, ``ts_utc``, ``anio``, ``pob_dens``; ``calidad``: ``qc`` alineada 1 a 1."""
    ev = mv.evaluabilidad_de_config(cfg)
    codigos = tuple(mv.codigos_evaluacion_de_config(cfg)[mv.E2])
    minimo_horas = int(cfg["metricas"]["niveles"]["diario"]["minimo_horas"])
    e2 = calidad["qc"].astype(str).isin(codigos).to_numpy()
    est = panel["estacion"].astype(str).to_numpy()
    out = {"umbrales": ev, "codigos_E2": list(codigos), "minimo_horas_dia": minimo_horas, "filas_E2": int(e2.sum()),
           "filas_E1": int(len(e2)), "por_protocolo": {}}
    v = cfg["protocolos"]["LPO"]["ventanas"]
    for prot in PROTOCOLOS:
        if prot == "LPO":
            g = pv.ventana_de(panel["anio"].to_numpy(), int(v["anio_desde"]), int(v["anio_hasta"]), int(v["largo_anios"]))
        else:
            gde = grupo_de_estacion(pol_d["protocolos"][prot])
            g = np.array([gde[s] for s in est], dtype=object)
        _, grupo = np.unique(g.astype(str), return_inverse=True)
        cero = np.zeros(len(est))
        base = dict(obs=cero, pred={}, z={}, estacion=est, macrozona=np.zeros(len(est), "int64"),
                    anio=panel["anio"].to_numpy("int64"), peso_vec=cero, dist_est_km=cero,
                    poblacion=panel["pob_dens"].to_numpy("float64"), grupo=grupo.ravel())
        n1 = mv.niveles(mv.nivel_horario(**base), panel["ts_utc"].to_numpy(), minimo_horas=minimo_horas)["diario_civil"]
        n2 = mv.niveles(mv.nivel_horario(**base, mascara=e2), panel["ts_utc"].to_numpy()[e2],
                        minimo_horas=minimo_horas)["diario_civil"]
        out["por_protocolo"][prot] = mv.evaluabilidad_e2(n1, n2, ev["minimo_fraccion"], ev["minimo_grupos"])
    sin_e2 = sorted(set(est) - set(est[e2]))
    out["estaciones_sin_ninguna_fila_E2"] = {"n": len(sin_e2), "de": int(len(set(est))), "estaciones": sin_e2}
    return out


# ---------------------------------------------------------------------------
# Manifiesto
# ---------------------------------------------------------------------------
def verificar_regimenes(reg_json: dict, metas: dict[str, dict]) -> list[dict]:
    """R17 (cuarta revisión, menores 11 y 18): ``paneles/regimenes_red2.json`` tiene que ser el de los json de los
    paneles: ``por_contaminante`` igual a los ``regimenes`` que declaran ``panel_pm25_red2.json`` y
    ``panel_no2_red2.json``, y ``comunes`` igual a ``panel_red2_v2.regimenes_comunes`` sobre ellos. Devuelve los tramos
    comunes."""
    import panel_red2_v2 as pr

    por = {pol: (metas.get(pol) or {}).get("regimenes") for pol in CONTAMINANTES}
    faltan = [pol for pol, v in por.items() if not isinstance(v, dict)]
    if faltan:
        raise SystemExit(f"R17: el json del panel de {faltan} no declara sus regímenes")
    if (reg_json or {}).get("por_contaminante") != por:
        raise SystemExit("R17: regimenes_red2.json no trae los regímenes que declaran los json de los paneles")
    calculados = json.loads(json.dumps(pr.regimenes_comunes(por)))
    if reg_json.get("comunes") != calculados:
        raise SystemExit("R17: los tramos comunes de regimenes_red2.json no son los que da panel_red2_v2.regimenes_comunes "
                         "con los regímenes de los json de los paneles")
    return calculados["tramos"]


def construir_manifiesto_red2(r: rv.RutasV2, cfg: dict, est_con_celda: pd.DataFrame, paneles: dict[str, Path],
                              insumos: dict[str, Path], poblacion_comunal: pd.DataFrame | None = None,
                              calidades: dict[str, Path] | None = None, hilos: int | None = None,
                              regimenes: Path | None = None) -> dict:
    """Manifiesto de pliegues de la red 2 con sus pesos y diagnósticos (no escribe nada). Con ``calidades`` (lo que se
    fija: R15 exige la E2), el json de cada panel es obligatorio y su ``sha256`` y su ``calidad_sha256`` tienen que ser
    los de los archivos que se leen, la bandera se alinea por estación y hora, y los regímenes de ``regimenes`` (por
    omisión, ``paneles/regimenes_red2.json``) entran al manifiesto comprobados contra los json de los paneles (cuarta
    revisión, menores 10, 11 y 18)."""
    hilos_cfg = int(cfg["operacion"]["hilos_maximos"]) if hilos is None else min(int(hilos), int(cfg["operacion"]["hilos_maximos"]))
    fijar_hilos(hilos_cfg)
    parametros, valores_cfg = pv.parametros_de(cfg)
    universo = pv.completar_universo(est_con_celda, cfg)
    por_pol, filas_por_pol, pesos, pesos_info, metas = {}, {}, {}, {}, {}
    for pol, ruta in paneles.items():
        por_est, conteos, filas = leer_panel_red2(ruta)
        sha = sha256_archivo(ruta)
        meta = rv.leer_json(Path(ruta).with_suffix(".json"))
        if calidades and meta is None:
            raise SystemExit(f"{pol}: falta el json del panel red 2 ({Path(ruta).with_suffix('.json').name}): al fijar, el "
                             f"panel y su bandera se comprueban por las huellas que declara")
        meta = meta or {}
        metas[pol] = meta
        if (calidades or meta.get("sha256")) and meta.get("sha256") != sha:
            raise SystemExit(f"{pol}: el panel red 2 en disco no es el que registra su json")
        info = {**r.relativa(ruta), "sha256": sha, "sha256_declarado": meta.get("sha256"),
                "filas": int(por_est["filas"].sum()), "estaciones": int(len(por_est)), "redes": meta.get("redes"),
                "schema": meta.get("schema")}
        por_pol[pol] = pv.construir_contaminante(pol, universo, por_est, conteos, cfg, info)
        filas_por_pol[pol] = {s: int(n) for s, n in por_est["filas"].items()}
        pesos[pol] = pesos_fijos(filas)
        pesos_info[pol] = {"por_estacion": {s: _finito(w) for s, w in pesos[pol].items()},
                           **resumen_pesos(por_pol[pol], pesos[pol], filas_por_pol[pol])}
        if poblacion_comunal is not None:
            nombres = sorted(filas_por_pol[pol])
            idx = {s: i for i, s in enumerate(nombres)}
            com = universo.set_index("estacion")["cod_comuna"]
            comuna = np.array([-1 if pd.isna(com.get(s)) else int(com.get(s)) for s in nombres], dtype="int64")
            w, tabla = mv.peso_desagrupamiento(conteos["estacion"].map(idx).to_numpy("int64"),
                                               conteos["anio"].to_numpy("int64"), comuna, poblacion_comunal, nombres)
            pesos_info[pol]["desagrupamiento"] = {s: _finito(w[i]) for s, i in idx.items()}
        if calidades and pol in calidades:
            import pyarrow.parquet as pq
            if meta.get("calidad_sha256") != sha256_archivo(calidades[pol]):
                raise SystemExit(f"{pol}: {Path(calidades[pol]).name} no es la bandera que declara el json del panel "
                                 f"(calidad_sha256)")
            panel = pq.read_table(ruta, columns=["estacion", "ts_utc", "anio", "pob_dens"]).to_pandas()
            calidad = pq.read_table(calidades[pol], columns=["estacion", "ts_utc", "qc"]).to_pandas()
            alineada = len(calidad) == len(panel) and \
                (calidad["ts_utc"].to_numpy() == panel["ts_utc"].to_numpy()).all() and \
                (calidad["estacion"].astype(str).to_numpy() == panel["estacion"].astype(str).to_numpy()).all()
            if not alineada:
                raise SystemExit(f"{pol}: la bandera de calidad no está alineada 1 a 1 con el panel red 2 (estación y hora)")
            pesos_info[pol]["evaluabilidad_e2"] = evaluabilidad_e2_red2(por_pol[pol], panel, calidad, cfg)
            insumos = {**insumos, f"calidad_{pol}": calidades[pol]}
        insumos = {**insumos, f"panel_{pol}": ruta}
    if regimenes is None and calidades:
        regimenes = r.raiz_v2.joinpath(*RUTA_REGIMENES)
    info_reg = None
    if regimenes is not None:
        if not Path(regimenes).exists():
            raise SystemExit(f"falta {Path(regimenes).name}: R17 escribe los regímenes en el manifiesto antes de cualquier "
                             f"ajuste")
        tramos = verificar_regimenes(rv.leer_json(regimenes), metas)
        info_reg = {"archivo": "/".join(RUTA_REGIMENES), "sha256": sha256_archivo(regimenes), "comunes": tramos,
                    "regla": "R17: los tramos comunes de PM2,5 y NO2 (panel_red2_v2.regimenes_comunes), comprobados "
                             "contra los regímenes de los json de los paneles"}
        insumos = {**insumos, "regimenes": regimenes}
    semillas = {"regla": parametros["semilla"]["regla"], "semilla_base": int(parametros["semilla"]["regla"][0])}
    # «schema» es el de pliegues_v2 porque las reglas son las mismas y los consumidores (vecindario, correr) leen la
    # misma estructura; la huella NO es la que daría pliegues_v2.py (el registro del panel es otro), y por eso un solo
    # programa fija los pliegues de la red ampliada. «schema_red2» dice qué agrega este archivo.
    m = {"schema": pv.SCHEMA, "schema_red2": SCHEMA, "bloque": ra.BLOQUE,
         "descripcion": ("Pliegues de la red ampliada (Enmienda 2, bloque R13): las reglas de pliegues_v2.json, sin "
                         "cambiar ningún parámetro, sobre las estaciones con celda de la red 2 y los paneles red 2. "
                         "Es la única fuente de pliegues, pesos, E2 y bloque más influyente de la red ampliada; al "
                         "fijarlo por primera vez, pliegues_v2.json pasa intacto a pliegues_v2_reemplazado_<marca>.json "
                         "(R13) y la bitácora empieza con «reemplazo»."),
         "reemplaza_a": MANIFIESTO_VIGENTE,
         "parametros": parametros, "valores_de_la_configuracion": valores_cfg,
         "conteos": {pol: {p: d["protocolos"][p]["n_pliegues"] for p in PROTOCOLOS} for pol, d in por_pol.items()},
         "estaciones": pv.registro_estaciones(universo, filas_por_pol),
         "contaminantes": por_pol,
         "pesos": pesos_info,
         "bloque_mas_influyente": bloque_mas_influyente(por_pol, pesos, filas_por_pol),
         "regimenes": info_reg,
         "traza": traza(insumos, semillas, hilos_cfg, rutas=r)}
    m["huella_pliegues"] = pv.huella_pliegues(m)
    m["huella_pesos"] = huella_pesos(m)
    return m


def huella_pesos(m: dict) -> str:
    """Huella de lo que el manifiesto registra antes de cualquier ajuste además de los pliegues: pesos y E2 (R14 y
    R15), bloque más influyente (R16) y regímenes (R17)."""
    return sha256_json({"pesos": m["pesos"], "bloque_mas_influyente": m["bloque_mas_influyente"],
                        "regimenes": m.get("regimenes")})

# ---------------------------------------------------------------------------
# Anexo «Registro de la red v2» (R22, paso 4): lo que se registra y su comprobación
# ---------------------------------------------------------------------------
RUTA_REGIMENES = ("paneles", "regimenes_red2.json")          # la escribe panel_red2_v2 (R17)
RUTA_RELOJ = ("verificacion_reloj_sinca_red2", "resumen.json")              # reloj_sinca_v2.NOMBRE_SALIDA
RUTA_CONTRASTE = ("unidades_red2", "contraste_unidades_cams_segunda.csv")   # contraste_unidades_v2.NOMBRES_SALIDA
RUTA_REGISTRO_MAIAC = ("insumos_red2", "registro_catalogo_maiac.json")
RUTA_INVENTARIO = ("insumos_red2", "inventario.json")
RUTA_CONGELADOS = ("insumos_red2", "congelados.json")
JSON_PANEL = {"pm25": ("paneles", "panel_pm25_red2.json"), "no2": ("paneles", "panel_no2_red2.json"),
              "o3": ("paneles", "observaciones_o3_red2.json")}
# Las entradas de red_de_monitores.registro_de_la_red que escribe el anexo y comprueba verificar_registro_de_la_red
# (los pliegues los comprueba exigir_registro, que admite los recortes que el piloto anota después; los regímenes,
# además, exigir_lo_calculado).
CAMPOS_DEL_ANEXO = {"reloj": ("veredictos_sha256", "resumen_sha256", "huella_series", "conteos", "elegida",
                              "sin_transiciones_junto_a_civil"),
                    "regimenes": ("sha256",),
                    "catalogo_maiac": ("sha256", "huella_teselas"),
                    "contraste_segunda_corrida": ("sha256", "lateral_sha256"),
                    "panel": ("pm25", "no2", "o3"), "calidad": ("pm25", "no2"), "duplicados": ("pm25", "no2", "o3"),
                    "lista_cerrada": ("huella", "archivos"), "insumos": ("inventario_sha256", "congelados_sha256"),
                    "tropomi_por_fecha": ("entran", "por_anio", "huella_lista"),
                    "traduccion": ("commit", "commit_espejo", "huella_archivos"),
                    "procedencia_descarga": ("versiones",)}


def _leer(r: rv.RutasV2, partes: tuple) -> tuple[dict, str]:
    ruta = r.raiz_v2.joinpath(*partes)
    if not ruta.exists():
        raise SystemExit(f"anexo: falta {'/'.join(partes)} en la raíz v2")
    return rv.leer_json(ruta), sha256_archivo(ruta)


def traduccion_comun(artefactos: dict[str, dict]) -> dict:
    """§0 y R22 (quinta revisión, mayor 2): todos los artefactos del armado declaran con qué traducción se escribieron
    (``traza.traduccion`` de ``red_ampliada_v2.traza_red2``: el último commit de la traducción en AP y en el espejo y la
    huella conjunta de sus archivos) y tiene que ser la misma; si alguno no la declara, o declara otra (un commit nuevo
    a mitad del armado sin rehacer lo anterior), se detiene. Devuelve la traducción común, que va al anexo."""
    vistas: dict[tuple, list[str]] = {}
    for nombre, d in sorted(artefactos.items()):
        tr = (((d or {}).get("traza") or {}).get("traduccion") or {}) if isinstance(d, dict) else {}
        clave = tuple(tr.get(k) for k in ("commit", "commit_espejo", "huella_archivos"))
        if any(not x or x == "desconocido" for x in clave):
            raise SystemExit(f"anexo: {nombre} no declara con qué traducción se escribió (traza.traduccion: commit en AP "
                             f"y en el espejo y huella de los archivos de la traducción)")
        vistas.setdefault(clave, []).append(nombre)
    if len(vistas) != 1:
        detalle = "; ".join(f"{c[0][:8]}/{c[1][:8]}: {', '.join(n)}" for c, n in vistas.items())
        raise SystemExit(f"anexo: los artefactos del armado no se escribieron con la misma traducción ({detalle}); "
                         f"después de un commit nuevo de la traducción, lo ya escrito se rehace (CAMINO_518, §9.0)")
    ((commit, espejo, huella),) = vistas
    return {"commit": commit, "commit_espejo": espejo, "huella_archivos": huella, "artefactos": sorted(artefactos)}


def procedencia_descarga_desde_artefactos(r: rv.RutasV2) -> dict:
    """R2 y §9.3 de la propuesta (quinta revisión, menor 22): el estado de cada versión del descargador de
    ``red_ampliada_v2.PROCEDENCIA_DESCARGA``, sin escribir nada ni leer valores: «en_git» si es la del programa del
    commit (``scripts_pipeline/descargar_sinca_ampliacion.py`` con esa huella); «recuperada» si en
    ``<raíz v2>/procedencia_descarga/`` hay una copia con esa huella (la que el autor recupere del historial de versiones
    del Drive, comparada con 647f5518… o 93f20aeb…); «perdida» si no. Va a ``registro_de_la_red.procedencia_descarga``."""
    carpeta = r.raiz_v2 / ra.CARPETA_PROCEDENCIA_DESCARGA
    halladas: dict[str, Path] = {}
    if carpeta.is_dir():
        for q in sorted(carpeta.rglob("*")):
            if q.is_file() and not q.is_symlink():
                halladas.setdefault(sha256_archivo(q), q)
    programa = Path(r.repo) / ra.PROCEDENCIA_DESCARGA["programa"]
    sha_programa = sha256_archivo(programa) if programa.is_file() else None
    versiones = []
    for v in ra.PROCEDENCIA_DESCARGA["versiones"]:
        sha = v["script_sha256"]
        if sha == sha_programa:
            estado, copia = "en_git", {"raiz": "repo", "ruta": ra.PROCEDENCIA_DESCARGA["programa"], "sha256": sha}
        elif sha in halladas:
            estado, copia = "recuperada", {**r.relativa(halladas[sha]), "sha256": sha}
        else:
            estado, copia = "perdida", None
        versiones.append({"script_version": v["script_version"], "script_sha256": sha, "estado": estado,
                          "copia": copia})
    return {"versiones": versiones,
            "regla": "en_git: el programa del commit tiene la huella; recuperada: una copia con la huella en "
                     f"<raíz v2>/{ra.CARPETA_PROCEDENCIA_DESCARGA}/; perdida: ninguna de las dos"}


def registro_de_la_red_desde_artefactos(r: rv.RutasV2) -> dict:
    """R22, paso 4: los valores del anexo «Registro de la red v2», leídos de los artefactos del armado (sólo json y
    huellas de archivos pequeños; nunca valores): el reloj (resumen y veredictos), la segunda corrida del contraste (CSV
    y lateral), el registro MAIAC de T5, los json de los paneles (panel, calidad, observaciones y duplicados), la lista
    cerrada, el inventario y la copia congelada, lo que entra por fecha de modificación (T1(4) y T11, por referencia: el
    conteo por año y la huella de la lista, que está en ``inventario.json``), el límite de R7 que declara el reloj, la
    traducción con que se escribieron todos (``traduccion_comun``) y el estado de la procedencia de la descarga
    (``procedencia_descarga_desde_artefactos``). Comprueba además que cada json de panel declare las mismas huellas del
    reloj, del contraste, del registro MAIAC y de los insumos, y que ``regimenes_red2.json`` sea el de los json de los
    paneles (``verificar_regimenes``). Devuelve {entrada: {campo: valor}} con las entradas de ``CAMPOS_DEL_ANEXO``."""
    reloj, sha_resumen = _leer(r, RUTA_RELOJ)
    ver = r.raiz_v2 / RUTA_RELOJ[0] / "veredictos.parquet"
    if not ver.exists() or sha256_archivo(ver) != reloj.get("sha256_veredictos"):
        raise SystemExit("anexo: veredictos.parquet del reloj falta o no es el que registra su resumen.json")
    csv = r.raiz_v2.joinpath(*RUTA_CONTRASTE)
    lateral, sha_lateral = _leer(r, RUTA_CONTRASTE[:-1] + (Path(RUTA_CONTRASTE[-1]).with_suffix(".json").name,))
    if not csv.exists() or sha256_archivo(csv) != lateral.get("sha256_csv"):
        raise SystemExit("anexo: el CSV de la segunda corrida del contraste falta o no es el de su lateral")
    maiac, sha_maiac = _leer(r, RUTA_REGISTRO_MAIAC)
    inventario, sha_inv = _leer(r, RUTA_INVENTARIO)
    congelados, sha_cong = _leer(r, RUTA_CONGELADOS)
    limite = reloj.get("limite_sin_transiciones")
    if not isinstance(limite, dict) or not isinstance(limite.get("unidades_junto_a_civil"), list):
        raise SystemExit("anexo: el resumen.json del reloj no declara el límite de R7 (limite_sin_transiciones)")
    out = {"reloj": {"veredictos_sha256": reloj["sha256_veredictos"], "resumen_sha256": sha_resumen,
                     "huella_series": reloj.get("huella_series"),
                     "conteos": (reloj.get("convencion_civil") or {}).get("conteos"),
                     "elegida": (reloj.get("convencion_civil") or {}).get("elegida"),
                     "sin_transiciones_junto_a_civil": [f"{u['estacion']}:{u['contaminante']}:{u['anio']}"
                                                        for u in limite["unidades_junto_a_civil"]]},
           "catalogo_maiac": {"sha256": sha_maiac, "huella_teselas": maiac.get("huella_teselas")},
           "contraste_segunda_corrida": {"sha256": lateral["sha256_csv"], "lateral_sha256": sha_lateral},
           "panel": {}, "calidad": {}, "duplicados": {},
           "lista_cerrada": {"huella": sha256_json(ra.LISTA_CERRADA), "archivos": len(ra.LISTA_CERRADA)},
           "insumos": {"inventario_sha256": sha_inv, "congelados_sha256": sha_cong}}
    mtime = (((inventario.get("resumen") or {}).get("tropomi_no2") or {}).get("por_fecha_de_modificacion") or {})
    out["tropomi_por_fecha"] = {"entran": mtime.get("entran", 0), "por_anio": mtime.get("por_anio", {}),
                                "huella_lista": mtime.get("huella_lista")}
    declarados = {"reloj.veredictos_sha256": out["reloj"]["veredictos_sha256"],
                  "reloj.resumen_sha256": sha_resumen, "unidades.contraste_sha256": lateral["sha256_csv"],
                  "unidades.segunda_corrida.lateral_sha256": sha_lateral, "registro_catalogo_maiac.sha256": sha_maiac,
                  "insumos.inventario_sha256": sha_inv, "insumos.congelados_sha256": sha_cong}
    metas = {}
    for pol, partes in JSON_PANEL.items():
        meta, sha_json = _leer(r, partes)
        metas[pol] = meta
        for clave, valor in declarados.items():
            nodo = meta
            for k in clave.split("."):
                nodo = (nodo or {}).get(k) if isinstance(nodo, dict) else None
            if nodo != valor:
                raise SystemExit(f"anexo: {'/'.join(partes)} declara otro {clave} que el de su artefacto")
        out["panel"][pol] = {"json_sha256": sha_json, "sha256": meta.get("sha256")}
        if pol in ("pm25", "no2"):
            out["calidad"][pol] = meta.get("calidad_sha256")
        out["duplicados"][pol] = sha256_json((meta.get("qc") or {}).get("duplicados"))
    regimenes, sha_reg = _leer(r, RUTA_REGIMENES)
    verificar_regimenes(regimenes, metas)
    out["regimenes"] = {"sha256": sha_reg}
    out["traduccion"] = traduccion_comun({"reloj": reloj, "contraste_segunda_corrida": lateral,
                                          "catalogo_maiac": maiac, "inventario": inventario,
                                          "congelados": congelados, "regimenes": regimenes,
                                          **{f"panel_{pol}": meta for pol, meta in metas.items()}})
    out["procedencia_descarga"] = procedencia_descarga_desde_artefactos(r)
    return out


def verificar_registro_de_la_red(r: rv.RutasV2, cfg: dict) -> dict:
    """El anexo escrito en la configuración (``red_de_monitores.registro_de_la_red``) tiene que ser el que dan los
    artefactos (``registro_de_la_red_desde_artefactos``), campo por campo; si no, se detiene."""
    reg = (cfg.get("red_de_monitores") or {}).get("registro_de_la_red") or {}
    calculado = registro_de_la_red_desde_artefactos(r)
    distintos = [f"{e}.{c}" for e, campos in CAMPOS_DEL_ANEXO.items() for c in campos
                 if ((reg.get(e) or {}) if isinstance(reg.get(e), dict) else {}).get(c) != calculado[e].get(c)]
    if distintos:
        raise SystemExit(f"el anexo «Registro de la red v2» no es el de los artefactos del armado: {distintos[:8]}")
    return calculado


def aviso_r16(m: dict) -> dict:
    """R16, «si no es RM o E004N083, se dice»: por protocolo, el bloque calculado, el que nombró la Enmienda 1 y si
    cambia (lo que ``bloque_mas_influyente`` dejó en el manifiesto). El anexo lo escribe en
    ``bloque_mas_influyente_enmienda_2.aviso`` (``con_el_anexo``) y ``exigir_lo_calculado`` lo compara."""
    return {p: {"calculado": m["bloque_mas_influyente"][p]["grupo"],
                "nombrado_por_la_enmienda_1": m["bloque_mas_influyente"][p]["nombrado_por_la_enmienda_1"],
                "cambia": bool(m["bloque_mas_influyente"][p]["cambia"])} for p in ("LRO", "BLQ-75")}


def exigir_lo_calculado(r: rv.RutasV2, cfg: dict, m: dict) -> None:
    """R16 y R17: rigen el bloque más influyente y los regímenes **calculados**. ``decision_v2`` y ``metricas_v2`` los
    leen de la configuración (``inferencia_diferencias.influencia.bloque_mas_influyente`` y
    ``…regimen_de_predictores.criterio``), así que el anexo tiene que haberlos escrito ahí: el bloque de cada protocolo
    tiene que ser el grupo de ``m["bloque_mas_influyente"]``; ``bloque_mas_influyente_enmienda_2`` tiene que conservar
    el de la Enmienda 1 en ``red_original`` (RM y E004N083) y decir en ``aviso`` si el calculado cambia (``aviso_r16``,
    el «se dice» de R16; quinta revisión, menores 11 y 14); y los tramos vigentes, los comunes de
    ``paneles/regimenes_red2.json``, cuya huella registra el anexo en ``registro_de_la_red.regimenes``; ese archivo
    tiene que ser el de los json de los paneles (``verificar_regimenes``) y el que copió el manifiesto
    (``m["regimenes"]``, bajo ``huella_pesos``). Si difieren, se detiene."""
    vigente = cfg["inferencia_diferencias"]["influencia"]["bloque_mas_influyente"]
    for prot in ("LRO", "BLQ-75"):
        calculado = m["bloque_mas_influyente"][prot]["grupo"]
        if vigente.get(prot) != calculado:
            raise SystemExit(f"R16: la configuración dice que el bloque más influyente de {prot} es {vigente.get(prot)!r} "
                             f"y el calculado para la red 2 es {calculado!r}; el anexo tiene que escribir el calculado")
    enm2 = cfg["inferencia_diferencias"]["influencia"].get("bloque_mas_influyente_enmienda_2")
    enm2 = enm2 if isinstance(enm2, dict) else {}
    if enm2.get("red_original") != NOMBRADOS_ENMIENDA_1:
        raise SystemExit(f"R16: bloque_mas_influyente_enmienda_2.red_original dice {enm2.get('red_original')!r}, no el de la "
                         f"Enmienda 1 {NOMBRADOS_ENMIENDA_1}: el anexo lo conserva")
    if enm2.get("aviso") != aviso_r16(m):
        raise SystemExit("R16: bloque_mas_influyente_enmienda_2.aviso no dice, como el manifiesto, si el bloque calculado "
                         "cambia frente al de la Enmienda 1 (bloque_mas_influyente.<protocolo>.cambia)")
    reg = (((cfg.get("red_de_monitores") or {}).get("registro_de_la_red") or {}).get("regimenes") or {})
    ruta = r.raiz_v2.joinpath(*RUTA_REGIMENES)
    if not reg.get("sha256"):
        raise SystemExit("R17: el anexo todavía no registra la huella de regimenes_red2.json")
    if not ruta.exists() or sha256_archivo(ruta) != reg["sha256"]:
        raise SystemExit(f"R17: {ruta.name} falta o no es el que registró el anexo")
    metas = {pol: rv.leer_json(r.raiz_v2.joinpath(*JSON_PANEL[pol])) for pol in CONTAMINANTES}
    comunes = verificar_regimenes(rv.leer_json(ruta), metas)
    copiados = m.get("regimenes") or {}
    if copiados.get("sha256") != reg["sha256"] or copiados.get("comunes") != comunes:
        raise SystemExit(f"R17: {NOMBRE} no copió los regímenes de {ruta.name} que registró el anexo")
    # El tramo completo, con su rótulo de disponibilidad: es el que metricas_v2.etiquetas_regimen lleva a las tablas.
    calculados = [(x["id"], tuple(x["anios"]), x["disponibilidad"]) for x in mv._normalizar_regimenes(comunes)]
    vigentes = [(x["id"], tuple(x["anios"]), x["disponibilidad"]) for x in mv.regimenes_de_config(cfg)]
    if calculados != vigentes:
        raise SystemExit(f"R17: los regímenes de la configuración {vigentes} no son los calculados para la red 2 "
                         f"{calculados}; el anexo tiene que escribir los calculados")


def exigir_registro(r: rv.RutasV2, cfg: dict, ruta: Path | None = None, estado=None,
                    exigir_confirmada: bool = True) -> dict:
    """El manifiesto de la red 2 que registró el anexo «Registro de la red v2» (R22, paso 4) en
    ``red_de_monitores.registro_de_la_red.pliegues`` (sha256 del archivo, huella de pliegues y huella de pesos). Sin
    anexo, o con otro archivo, se detiene: ningún ajuste antes del paso 4. Después del anexo sólo caben los recortes
    del presupuesto que el piloto anota al final de la bitácora (§10, ``pliegues_v2.EVENTOS_TRAS_FIJAR``): el archivo
    vale si es el registrado o el registrado más esos eventos, lo que se comprueba volviendo a serializarlo sin ellos
    (``texto_json`` es determinista). Además exige que rijan el bloque más influyente y los regímenes calculados
    (R16 y R17, ``exigir_lo_calculado``) y que el resto del anexo sea el de los artefactos del armado
    (``verificar_registro_de_la_red``). R22, paso 4 («confirmado en git»; quinta revisión, menor 12): ``config_v2.json``
    tiene que estar rastreado y sin cambios en AP y en el espejo (``red_ampliada_v2.exigir_config_confirmada``), así que
    ni el piloto (que sale de ``correr_v2.main`` antes de ``verificar_sellado``) ni ningún ajuste corren con el anexo
    pegado y sin confirmar; ``exigir_confirmada=False`` sólo para ``--anexo``, que valida en memoria el anexo antes de
    pegarlo y no ajusta nada; ``estado``, para las pruebas. Devuelve el manifiesto."""
    ruta = Path(ruta) if ruta is not None else r.raiz_v2 / NOMBRE
    reg = (((cfg.get("red_de_monitores") or {}).get("registro_de_la_red") or {}).get("pliegues") or {})
    if not reg.get("sha256") or not reg.get("huella_pliegues"):
        raise SystemExit("el anexo «Registro de la red v2» todavía no registra la huella de los pliegues de la red 2")
    if exigir_confirmada:
        ra.exigir_config_confirmada(r, estado)
    if not ruta.exists():
        raise SystemExit(f"falta {ruta.name}")
    m = rv.leer_json(ruta)
    if pv.huella_pliegues(m) != m.get("huella_pliegues") or m.get("huella_pliegues") != reg["huella_pliegues"]:
        raise SystemExit(f"{ruta.name}: su huella de pliegues no calza con la registrada")
    if huella_pesos(m) != m.get("huella_pesos") or (reg.get("huella_pesos") and m["huella_pesos"] != reg["huella_pesos"]):
        raise SystemExit(f"{ruta.name}: su huella de pesos no calza con la registrada")
    if sha256_archivo(ruta) != reg["sha256"]:
        bitacora = list(m.get("bitacora", []))
        k, calza = len(bitacora), False
        while k > 0 and bitacora[k - 1].get("evento") in pv.EVENTOS_TRAS_FIJAR and not calza:
            k -= 1
            texto = rv.texto_json({**m, "bitacora": bitacora[:k]})
            calza = hashlib.sha256(texto.encode("utf-8")).hexdigest() == reg["sha256"]
        if not calza:
            raise SystemExit(f"{ruta.name} no es el que registró el anexo (ni el registrado más recortes del "
                             f"presupuesto)")
    red = (cfg.get("red_de_monitores") or {}).get("registro_de_la_red") or {}
    for pol in CONTAMINANTES:                                    # R15: la E2 del manifiesto, con la bandera registrada
        usada = (((m.get("traza") or {}).get("insumos") or {}).get(f"calidad_{pol}") or {}).get("sha256")
        if not usada or usada != (red.get("calidad") or {}).get(pol):
            raise SystemExit(f"{ruta.name}: la evaluabilidad de E2 de {pol} se calculó con otra bandera que la que registra "
                             f"el anexo (registro_de_la_red.calidad)")
    verificar_cobertura(cfg, m)
    verificar_evaluabilidad_e2(cfg, m)                           # R15: escrita en el registro de la red
    exigir_lo_calculado(r, cfg, m)
    verificar_registro_de_la_red(r, cfg)
    return m


def texto_cobertura(e2: dict) -> str:
    """R15: la cifra de la red ampliada para ``cobertura_conocida``, como la de la red original."""
    s = e2["estaciones_sin_ninguna_fila_E2"]
    return (f"{int(s['n'])} de las {int(s['de'])} estaciones no tienen ninguna fila validada (E2: validado en SINCA, "
            f"usable_native en SNIFA)")


CAMPOS_E2 = ("evaluable", "fraccion_del_peso", "grupos_con_E2", "peso_E1", "peso_E2")


def evaluabilidad_e2_del_manifiesto(m: dict) -> dict:
    """R15, «antes de cualquier ajuste, y se escribe en el registro de la red»: por contaminante y protocolo, la
    evaluabilidad de E2 que ``pliegues_v2_red2.json`` calculó al fijar (``pesos.<pol>.evaluabilidad_e2.por_protocolo``):
    si es evaluable, la fracción del peso, los grupos con E2 y los pesos de E1 y E2 (``CAMPOS_E2``). Va al anexo en
    ``registro_de_la_red.evaluabilidad_e2``."""
    out = {}
    for pol in CONTAMINANTES:
        por = ((((m.get("pesos") or {}).get(pol) or {}).get("evaluabilidad_e2") or {}).get("por_protocolo") or {})
        if not por:
            raise SystemExit(f"{NOMBRE} no trae la evaluabilidad de E2 de {pol} por protocolo (R15)")
        out[pol] = {prot: {c: por[prot].get(c) for c in CAMPOS_E2} for prot in sorted(por)}
    return out


def verificar_evaluabilidad_e2(cfg: dict, m: dict) -> dict:
    """R15: ``registro_de_la_red.evaluabilidad_e2`` es la del manifiesto (``evaluabilidad_e2_del_manifiesto``), como
    ``verificar_cobertura``; si no, se detiene."""
    reg = (((cfg.get("red_de_monitores") or {}).get("registro_de_la_red") or {}).get("evaluabilidad_e2") or {})
    esperado = evaluabilidad_e2_del_manifiesto(m)
    if sha256_json({pol: reg.get(pol) for pol in CONTAMINANTES}) != sha256_json(esperado):     # también con NaN
        raise SystemExit("R15: registro_de_la_red.evaluabilidad_e2 no es la que da pliegues_v2_red2.json; el anexo tiene "
                         "que escribirla")
    return esperado


def evaluabilidad_e2_que_rige(ev: dict, m: dict, pol: str, prot: str) -> tuple[dict, dict]:
    """R15 en la decisión (``correr_v2.decidir``, con la red 2; ronda 5 de la traducción, mayor 1): «la evaluabilidad de
    E2 se calcula sobre el panel de R11, con los mismos umbrales, antes de cualquier ajuste» (y su «Por qué»:
    «Calcularlo antes cierra la puerta a declararlo según convenga»). Rige la registrada antes del ajuste en
    ``pliegues_v2_red2.json`` (``m``: ``pesos.<pol>.evaluabilidad_e2.por_protocolo.<prot>``), no la que
    ``evidencia_de_decision`` vuelve a calcular sobre los pares de la decisión (``ev["evaluabilidad_E2"]``), que queda
    sólo como registro: no hay nada que elegir después de ver las métricas.

    Devuelve (evidencia que se entrega a ``decision_v2``, registro para ``decision.json``). La evidencia es una copia de
    ``ev`` con ``evaluabilidad_E2`` = la registrada (``decision_v2.evaluar_protocolo`` exige la condición 3 si ésta es
    evaluable; si no lo es, la condición 3 no bloquea, Enmienda 1, punto 7); ``ev`` no cambia. El registro trae las dos
    (``CAMPOS_E2``), si su «evaluable» coincide y la huella de la evidencia consolidada tal como se leyó
    (``decision_v2.huella_evidencia``). Si la registrada falta, o si es evaluable y la evidencia no tiene pares E2 (la
    vista ``decision_v2.V_E2``), se detiene: es un defecto de la corrida (la bandera o los pares de la decisión)
    que se corrige rehaciendo la consolidación, no una elección."""
    import decision_v2 as dc

    registrada = (((((m.get("pesos") or {}).get(pol) or {}).get("evaluabilidad_e2") or {}).get("por_protocolo") or {})
                  .get(prot))
    if not isinstance(registrada, dict) or "evaluable" not in registrada:
        raise SystemExit(f"{pol} {prot}: {NOMBRE} no registra la evaluabilidad de E2 antes del ajuste (R15)")
    de_la_decision = ev.get("evaluabilidad_E2") if isinstance(ev.get("evaluabilidad_E2"), dict) else {}
    con_pares_e2 = dc.V_E2 in (ev.get("vistas") or {})
    if bool(registrada["evaluable"]) and not con_pares_e2:
        raise SystemExit(f"{pol} {prot}: la evaluabilidad de E2 registrada antes del ajuste en {NOMBRE} es evaluable "
                         f"(fracción del peso {registrada.get('fraccion_del_peso')}, {registrada.get('grupos_con_E2')} "
                         f"grupos con E2), y por R15 rige, pero la evidencia de la decisión no tiene pares E2: es un "
                         f"defecto de la corrida (la bandera de calidad o los pares de la decisión); rehaz la "
                         f"consolidación del protocolo")
    rige = {**registrada, "fuente": f"{NOMBRE}: pesos.{pol}.evaluabilidad_e2.por_protocolo.{prot} (R15, antes del "
                                    f"ajuste)"}
    d = {c: de_la_decision.get(c) for c in CAMPOS_E2}
    g = {c: registrada.get(c) for c in CAMPOS_E2}
    registro = {"rige": g, "de_la_decision": d, "coinciden": bool(d["evaluable"]) == bool(g["evaluable"]),
                "evidencia_consolidada_sha256": dc.huella_evidencia(ev),
                "regla": "R15: rige la evaluabilidad de E2 registrada en pliegues_v2_red2.json (sobre el panel de R11, "
                         "con los mismos umbrales, antes de cualquier ajuste); la que la decisión calcula sobre sus pares "
                         "sólo se registra"}
    return {**ev, "evaluabilidad_E2": rige}, registro


def verificar_cobertura(cfg: dict, m: dict) -> dict:
    """R15, «``cobertura_conocida`` informa la red original y la ampliada» (cuarta revisión, menor 19): el anexo escribe
    en ``calidad_blanco.evaluacion.cobertura_conocida.red_ampliada``, por contaminante, la cifra del manifiesto; si no es
    la de ``m``, se detiene."""
    cob = (((cfg.get("calidad_blanco") or {}).get("evaluacion") or {}).get("cobertura_conocida") or {}).get("red_ampliada")
    esperado = {}
    for pol in CONTAMINANTES:
        e2 = ((m.get("pesos") or {}).get(pol) or {}).get("evaluabilidad_e2")
        if not e2:
            raise SystemExit(f"{NOMBRE} no trae la evaluabilidad de E2 de {pol} (R15)")
        esperado[pol] = texto_cobertura(e2)
    if not isinstance(cob, dict) or {pol: cob.get(pol) for pol in CONTAMINANTES} != esperado:
        raise SystemExit("R15: cobertura_conocida.red_ampliada no es la que da pliegues_v2_red2.json; el anexo tiene que "
                         "escribirla")
    return esperado


DONDE_DEL_ANEXO = {
    "registro_de_la_red": "red_de_monitores.registro_de_la_red: cada entrada junto a su «archivo» y su «regla»",
    "bloque_mas_influyente": "inferencia_diferencias.influencia.bloque_mas_influyente (el de la Enmienda 1 queda en "
                             "bloque_mas_influyente_enmienda_2.red_original)",
    "aviso_r16": "inferencia_diferencias.influencia.bloque_mas_influyente_enmienda_2.aviso (R16: si el calculado no es "
                 "RM o E004N083, se dice)",
    "regimenes": "metricas.desagregaciones.regimen_de_predictores.criterio.valor (los de la Enmienda 1 quedan en "
                 "valor_red_original)",
    "cobertura_red_ampliada": "calidad_blanco.evaluacion.cobertura_conocida.red_ampliada"}


def anexo_desde_artefactos(r: rv.RutasV2) -> dict:
    """R22, paso 4 (cuarta revisión, menor 34): el bloque completo del anexo «Registro de la red v2», armado de los
    artefactos: ``registro_de_la_red`` (lo de ``registro_de_la_red_desde_artefactos`` más los pliegues, con el sha256 de
    ``pliegues_v2_red2.json`` y sus dos huellas, y la evaluabilidad de E2 por contaminante y protocolo, R15:
    ``evaluabilidad_e2_del_manifiesto``), el bloque más influyente calculado (R16), los tramos comunes en el formato de
    ``metricas_v2.regimenes_de_config`` (R17) y la cobertura de E2 de la red ampliada (R15). No escribe nada;
    ``con_el_anexo`` lo pone donde lo leen los programas."""
    reg = registro_de_la_red_desde_artefactos(r)
    ruta = r.raiz_v2 / NOMBRE
    if not ruta.exists():
        raise SystemExit(f"anexo: falta {NOMBRE} en la raíz v2")
    m = rv.leer_json(ruta)
    if pv.huella_pliegues(m) != m.get("huella_pliegues") or huella_pesos(m) != m.get("huella_pesos"):
        raise SystemExit(f"anexo: {NOMBRE} no calza con sus propias huellas")
    if (m.get("regimenes") or {}).get("sha256") != reg["regimenes"]["sha256"]:
        raise SystemExit(f"anexo: {NOMBRE} no trae los regímenes de regimenes_red2.json (R17)")
    reg["pliegues"] = {"sha256": sha256_archivo(ruta), "huella_pliegues": m["huella_pliegues"],
                       "huella_pesos": m["huella_pesos"]}
    reg["evaluabilidad_e2"] = evaluabilidad_e2_del_manifiesto(m)          # R15, «se escribe en el registro de la red»
    return {"registro_de_la_red": reg,
            "bloque_mas_influyente": {p: m["bloque_mas_influyente"][p]["grupo"] for p in ("LRO", "BLQ-75")},
            "aviso_r16": aviso_r16(m),
            "regimenes": [{"id": x["id"], "anios": [int(x["anios"][0]), int(x["anios"][1])],
                           "disponibilidad": x["disponibilidad"]} for x in m["regimenes"]["comunes"]],
            "cobertura_red_ampliada": {pol: texto_cobertura(m["pesos"][pol]["evaluabilidad_e2"]) for pol in CONTAMINANTES},
            "donde": DONDE_DEL_ANEXO}


def con_el_anexo(cfg: dict, anexo: dict) -> dict:
    """La configuración con el anexo escrito donde lo leen los programas (``DONDE_DEL_ANEXO``); devuelve una copia y
    no toca ``cfg``. Es lo que el autor pega en ``config_v2.json`` en el paso 4; ``exigir_registro`` lo valida. Se puede
    aplicar de nuevo (después de ``fijar --reemplazar``): ``red_original`` conserva el valor de la Enmienda 1 y
    ``valor_red_original`` los regímenes de la Enmienda 1 (los dos con ``setdefault``), y ``aviso`` dice, como el
    manifiesto, si el bloque calculado cambia (R16; quinta revisión, menores 11 y 14)."""
    c = copy.deepcopy(cfg)
    reg = c.setdefault("red_de_monitores", {}).setdefault("registro_de_la_red", {})
    for entrada, valores in anexo["registro_de_la_red"].items():
        actual = reg.get(entrada)
        reg[entrada] = {**actual, **valores} if isinstance(actual, dict) else dict(valores)
    inf = c["inferencia_diferencias"]["influencia"]
    enm2 = inf.get("bloque_mas_influyente_enmienda_2")
    enm2 = dict(enm2) if isinstance(enm2, dict) else {}
    enm2.setdefault("red_original", dict(inf["bloque_mas_influyente"]))     # la Enmienda 1, aunque se aplique de nuevo
    enm2["valor"] = dict(anexo["bloque_mas_influyente"])
    enm2["aviso"] = copy.deepcopy(anexo["aviso_r16"])
    inf["bloque_mas_influyente_enmienda_2"] = enm2
    inf["bloque_mas_influyente"] = dict(anexo["bloque_mas_influyente"])
    crit = c["metricas"]["desagregaciones"]["regimen_de_predictores"]["criterio"]
    clave = "valor" if rv.estado_vigente(crit) == "ratificado" else "provisional"
    crit.setdefault("valor_red_original", copy.deepcopy(crit[clave]))
    crit[clave] = [dict(x) for x in anexo["regimenes"]]
    cob = c["calidad_blanco"]["evaluacion"]["cobertura_conocida"]
    actual = cob.get("red_ampliada")
    cob["red_ampliada"] = {**(actual if isinstance(actual, dict) else {}), **anexo["cobertura_red_ampliada"]}
    return c


def respaldo_de_r13(r: rv.RutasV2, sha_original: str = MANIFIESTO_VIGENTE["sha256"]) -> Path | None:
    """El respaldo que dejó el renombre de R13, reconocido por su sha256 (no por el nombre: en la raíz hay otros
    ``pliegues_v2_reemplazado_*.json``, de la Enmienda 1), o None."""
    for q in sorted(r.raiz_v2.glob(f"{Path(NOMBRE_VIGENTE_ORIGINAL).stem}_reemplazado_*.json")):
        if sha256_archivo(q) == sha_original:
            return q
    return None


def evento_r13(bitacora) -> dict | None:
    """El evento «reemplazo» de R13 (``regla`` «R13») de una bitácora, buscado también en las ``bitacora_anterior``
    anidadas (después de un ``fijar --reemplazar`` queda dentro de la del reemplazo genérico); None si no está."""
    for e in bitacora or []:
        if not isinstance(e, dict):
            continue
        if e.get("evento") == "reemplazo" and e.get("regla") == "R13":
            return e
        anidado = evento_r13(e.get("bitacora_anterior"))
        if anidado is not None:
            return anidado
    return None


def fijar(m: dict, r: rv.RutasV2, cfg: dict, reemplazar: bool = False, motivo: str | None = None,
          estado=None, sha_original: str = MANIFIESTO_VIGENTE["sha256"],
          permitir_sin_r13: bool = False) -> tuple[dict, str]:
    """Publica ``pliegues_v2_red2.json``, el único manifiesto de la red ampliada, después de exigir la traducción
    confirmada en git (R22; ``estado`` sólo para las pruebas). La primera vez hace el reemplazo de R13:
    ``pliegues_v2.json`` pasa intacto a ``pliegues_v2_reemplazado_<marca>.json`` y la bitácora empieza con «reemplazo».
    Si el original ya no está, la bitácora apunta al respaldo de R13 que lo conserva (``respaldo_de_r13``, por su
    sha256: pasa si una corrida se cortó entre el renombre y la publicación); sin ese respaldo se detiene
    (``permitir_sin_r13``, sólo para las pruebas). Igual huella → sin cambios; otra huella → se detiene salvo
    ``reemplazar``, que deja el anterior como respaldo. Al reemplazar, la bitácora nueva empieza con el evento de R13
    que traía el manifiesto anterior, copiado tal cual (``evento_r13``: regla R13, huella anterior y respaldo de
    ``pliegues_v2.json`` con su sha256), así que el reemplazo de R13 sigue a la vista; si el anterior no lo trae, se
    detiene (salvo ``permitir_sin_r13``)."""
    ra.exigir_traduccion_confirmada(r, cfg, estado)
    destino = r.raiz_v2 / NOMBRE
    original = r.raiz_v2 / NOMBRE_VIGENTE_ORIGINAL
    with rv.candado_escritura("pliegues", rutas=r):
        previo = rv.leer_json(destino)
        ahora = rv.ahora_utc()
        if previo is not None and previo.get("huella_pliegues") == m["huella_pliegues"] \
                and previo.get("huella_pesos") == m["huella_pesos"]:
            return previo, "sin_cambios"
        if previo is not None and not reemplazar:
            raise SystemExit(f"{NOMBRE} ya existe con otra huella; usa --reemplazar con --motivo")
        bitacora = []
        if previo is None and not original.exists():
            respaldo = respaldo_de_r13(r, sha_original)
            if respaldo is None and not permitir_sin_r13:
                raise SystemExit(f"falta {original.name} y no hay un respaldo con su sha256 ({sha_original[:8]}…): el "
                                 f"reemplazo de R13 no se puede registrar; revisa a mano antes de fijar")
            if respaldo is not None:
                anterior = rv.leer_json(respaldo)
                bitacora.append({"utc": ahora, "evento": "reemplazo", "regla": "R13",
                                 "huella_anterior": anterior.get("huella_pliegues"),
                                 "schema_anterior": anterior.get("schema"),
                                 "fijado_utc_anterior": anterior.get("fijado_utc"),
                                 "respaldo": {**r.relativa(respaldo), "sha256": sha_original},
                                 "motivo": motivo or "red ampliada (Enmienda 2, bloque R13)",
                                 "nota": "el renombre de R13 ya estaba hecho: se reconoce el respaldo por su sha256",
                                 "bitacora_anterior": list(anterior.get("bitacora", []))})
        elif previo is None:
            anterior = rv.leer_json(original)
            if pv.huella_pliegues(anterior) != anterior.get("huella_pliegues"):
                raise SystemExit(f"{original.name} no calza con su propia huella: se editó a mano; no se reemplaza")
            if sha256_archivo(original) != sha_original:
                raise SystemExit(f"{original.name} no es el manifiesto del 2026-10-13 que nombra R13 "
                                 f"({sha_original[:8]}…): no se reemplaza")
            sello = ahora.replace(":", "").replace("-", "")
            respaldo = rv.renombrar(original, r.raiz_v2 / f"pliegues_v2_reemplazado_{sello}.json", r)
            if sha256_archivo(respaldo) != sha_original:
                raise RuntimeError("el respaldo de pliegues_v2.json no conserva sus bytes")
            bitacora.append({"utc": ahora, "evento": "reemplazo", "regla": "R13",
                             "huella_anterior": anterior.get("huella_pliegues"), "schema_anterior": anterior.get("schema"),
                             "fijado_utc_anterior": anterior.get("fijado_utc"),
                             "respaldo": {**r.relativa(respaldo), "sha256": sha_original},
                             "motivo": motivo or "red ampliada (Enmienda 2, bloque R13)",
                             "bitacora_anterior": list(anterior.get("bitacora", []))})
        elif previo is not None:
            r13 = evento_r13(previo.get("bitacora"))
            if r13 is None and not permitir_sin_r13:
                raise SystemExit(f"{NOMBRE} no trae el evento «reemplazo» de R13 en su bitácora: no se reemplaza sin él; "
                                 f"revisa a mano")
            if r13 is not None:
                bitacora.append(copy.deepcopy(r13))                 # R13 sigue primero, tal cual
            respaldo = rv.ruta_de_respaldo(destino, "reemplazado")
            sha_previo = rv.copiar_artefacto(destino, respaldo, r)
            bitacora.append({"utc": ahora, "evento": "reemplazo", "huella_anterior": previo.get("huella_pliegues"),
                             "respaldo": {**r.relativa(respaldo), "sha256": sha_previo},
                             "motivo": motivo or "reemplazo pedido con --reemplazar",
                             "bitacora_anterior": list(previo.get("bitacora", []))})
        bitacora.append({"utc": ahora, "evento": "fijado", "huella_pliegues": m["huella_pliegues"],
                         "motivo": motivo or "red ampliada (Enmienda 2, bloque R13)",
                         "nota": "fijado antes de ajustar ningún motor; único manifiesto de la red ampliada"})
        final = {**m, "fijado_utc": ahora, "bitacora": bitacora}
        rv.publicar_json(final, destino, r)
    return final, ("reemplazado" if previo is not None else "fijado")


def comprobar_opciones(no_escribir: bool, sin_e2: bool, ruta_poblacion: Path) -> None:
    """Antes de leer nada: ``--sin-e2`` sólo sin escribir (R15 exige la E2 antes de fijar) y, para escribir, la
    población comunal del INE (R14 exige el desagrupamiento al fijar)."""
    if sin_e2 and not no_escribir:
        raise SystemExit("--sin-e2 sólo sirve con --no-escribir: R15 exige la evaluabilidad de E2 antes de fijar")
    if not no_escribir and not Path(ruta_poblacion).exists():
        raise SystemExit(f"falta la población comunal del INE ({Path(ruta_poblacion).name}): R14 exige el "
                         f"desagrupamiento al fijar")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pliegues y pesos de la red ampliada (R13-R16), en pliegues_v2_red2.json.")
    ap.add_argument("--no-escribir", action="store_true")
    ap.add_argument("--reemplazar", action="store_true")
    ap.add_argument("--motivo", default=None)
    ap.add_argument("--sin-e2", action="store_true", help="no calcula la evaluabilidad de E2 (sólo con --no-escribir)")
    ap.add_argument("--hilos", type=int, default=None)
    ap.add_argument("--anexo", action="store_true",
                    help="arma el anexo «Registro de la red v2» desde los artefactos, lo valida y lo muestra (no escribe)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    import panel_red2_v2 as pr

    r = rv.rutas_v2()
    if args.anexo:
        anexo = anexo_desde_artefactos(r)
        exigir_registro(r, con_el_anexo(rv.cargar_config(r), anexo), exigir_confirmada=False)   # en memoria
        print(json.dumps(anexo, ensure_ascii=False, indent=1))
        return 0
    ruta_pc = mv.ruta_poblacion_comunal(r.datos)
    comprobar_opciones(args.no_escribir, args.sin_e2, ruta_pc)
    cfg = rv.cargar_config(r)
    ra.verificar_lista_cerrada(r.datos)
    maestro = ra.maestro_red2(r.datos)
    snifa = pv.leer_estaciones_snifa(r, pv.leer_estaciones_sinca(r))
    enlaces = pd.concat([pd.read_parquet(r.grilla_v1 / n, columns=["estacion", "celda"])
                         for n in pr.INSUMOS_GRILLA_V1[4:6]] +
                        [pd.read_parquet(r.raiz_v2 / "grilla" / pr.NOMBRE_ENLACES, columns=["estacion", "celda"])],
                        ignore_index=True)
    est = pr.estaciones_con_celda_red2(maestro, snifa, enlaces)
    paneles = {pol: r.raiz_v2 / "paneles" / NOMBRE_PANEL.format(pol=pol) for pol in CONTAMINANTES}
    calidades = None if args.sin_e2 else {pol: r.raiz_v2 / "paneles" / NOMBRE_CALIDAD.format(pol=pol)
                                          for pol in CONTAMINANTES}
    pc = mv.leer_poblacion_comunal(ruta_pc) if ruta_pc.exists() else None
    insumos = {"maestro_actuales": r.datos / ra.MAESTRO_ACTUALES, "maestro_nuevas": r.datos / ra.MAESTRO_NUEVAS,
               "snifa": r.snifa, "enlaces_red2": r.raiz_v2 / "grilla" / pr.NOMBRE_ENLACES,
               **{f"grilla_{Path(n).stem}": r.grilla_v1 / n for n in pr.INSUMOS_GRILLA_V1[4:6]}}
    if pc is not None:
        insumos["poblacion_comunal"] = ruta_pc
    ruta_reg = r.raiz_v2.joinpath(*RUTA_REGIMENES)
    m = construir_manifiesto_red2(r, cfg, est, paneles, insumos, pc, calidades, args.hilos,
                                  regimenes=ruta_reg if (calidades or ruta_reg.exists()) else None)
    print({pol: m["conteos"][pol] for pol in m["conteos"]}, m["bloque_mas_influyente"]["LRO"]["grupo"],
          m["bloque_mas_influyente"]["BLQ-75"]["grupo"])
    if args.no_escribir:
        return 0
    _, estado = fijar(m, r, cfg, args.reemplazar, args.motivo)
    print(estado, m["huella_pliegues"][:16])
    return 0


if __name__ == "__main__":
    sys.exit(main())
