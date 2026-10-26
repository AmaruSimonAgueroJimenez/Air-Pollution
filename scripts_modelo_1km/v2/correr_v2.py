#!/usr/bin/env python3
"""Orquestador de la comparación v2 de motores y pérdidas (``DISENO_AMBIENTAL_V2.md`` §3–§8 y §10).

Reanudable por pliegue, con puntos de control atómicos en la raíz v2:
``<raíz v2>/comparacion/<etiqueta>/<pol>/<protocolo>/kNNN/{vecindario,r0,r1,r2,interno}/<tarea>.npz``. Cada punto
lleva su **firma** (Enmienda 1, punto 14: panel, sha256 de la lista ordenada de predictores, manifiesto de pliegues,
pliegue y conjunto excluido, tarea, receta efectiva, pérdida, variante de calidad, filas de entrenamiento, huella del
vecindario recalculado, **semillas efectivas** (``_semillas``), sha256 del contrato y de la configuración, código de
ajuste, bibliotecas e hilos) y su **traza** (commit, hash del código, sha256 de insumos, bibliotecas, hilos y
semillas). El **código de ajuste** son los sha256 de ``motores_v2``, ``perdidas_v2`` y ``vecindario_v2`` y el de cada
función de este archivo que define filas, semillas, vecindario o ajuste (``FUNCIONES_AJUSTE``: las semillas, la
validación de la MLP, el δ honesto de Huber, el amortiguador interno, los pliegues internos, …), calculado de su
código fuente: la firma cambia cuando cambia ese código, sin subir una versión a mano (Complemento, punto 7), y
cuando cambian las semillas que entrega. La retransformación no entra en la firma del ajuste: se aplica al consolidar
y queda registrada en ``consolidado.json``. Un punto con la firma vigente no se recalcula; uno con otra firma se
rehace. Cada pliegue se trabaja bajo su propio candado de escritura (el del artefacto, ``_rutas_v2.candado_de``,
con el nombre normalizado: Complemento, punto 10), así que se pueden lanzar varios procesos sobre pliegues distintos
(``--parte i/m``). ``correr`` y ``consolidar`` exigen que el contrato, la configuración y el código v2 estén
confirmados en git (sellado, Enmienda 1, punto 14).

**MLP** (Enmienda 1, punto 6): la validación de la parada temprana es por conglomerados LOSO-D y, en LRO y BLQ-75,
por grupos completos del protocolo; su vecindario se recalcula sin las estaciones de validación y la red se reajusta
con todas las estaciones durante la época elegida (``validacion_mlp``). **Huber** (punto 9): el δ es común a LightGBM
y XGBoost y sale de residuos honestos del ``l2_original`` de LightGBM en una partición agrupada en dos del
entrenamiento (``delta_huber_honesto``, dentro de la tarea ``lightgbm_l2_original``); la sensibilidad de Friedman
(``huber_friedman``) usa los mismos residuos.

**Amortiguador interno de BLQ-75** (Complemento, punto 5; ``amortiguador_interno``): en las particiones internas de
un pliegue de BLQ-75 —la validación de la MLP, los pliegues internos del apilado y de la retransformación con OOF
interno y la partición honesta del δ de Huber— se sacan del entrenamiento interno, y de su vecindario, las
estaciones a ≤ 10 km (haversine) de las estaciones de su conjunto interno de validación. La distancia se mide sólo
desde las estaciones de ese conjunto **que tienen filas en el entrenamiento del pliegue** (las que validan de verdad;
las demás —p. ej., las que el conjunto excluido externo dejó sin filas— no se miden).

**Por pliegue** (``correr_pliegue``):

1. El vecindario (``obs_vec``, ``peso_vec``, ``dist_est_km``) se recalcula con ``vecindario_v2`` sin el conjunto
   excluido, en todas las filas (entrenamiento y prueba), sin atajos; en LPO, la red concurrente (§1, §2).
2. Una permutación común con semilla ``[42, k]`` (réplica 0) o ``[42, k, r]`` (réplicas de ruido); cada tope es
   un prefijo, así que los topes quedan anidados y todos los motores con el mismo tope ven las mismas filas.
3. Tareas: eje A (LightGBM, XGBoost, RF y MLP con N común), pérdidas de §6 (LightGBM y XGBoost), alertas
   (cuantil 0,80), eje B (GP, LME y GWR/RK/IDW), curvas de aprendizaje y réplicas de ruido (LRO y BLQ-75),
   variantes de calidad (LightGBM, LOSO-D y LRO) y pliegues internos (apilado anidado y sensibilidad de la
   retransformación, LRO y BLQ-75).

La regla única de exclusión (§1) se aplica en los cuatro lugares: filas de entrenamiento (las de las estaciones
excluidas no entran), vecindario de entrenamiento y de prueba (recalculado sin ellas) y residuos de la
retransformación (``retransformacion_v2`` no usa ninguna fila de una estación excluida, tampoco el entorno de
LBO-10). Los pliegues internos usan el conjunto excluido externo más las estaciones del pliegue interno.

**Consolidación** (``consolidar``), cuando están todos los pliegues de un protocolo (Enmienda 1, puntos 2–5, 7, 10
y 11): promedio simple y apilado; retransformación primaria (``smearing_duan`` por macrozona × franja, con el
respaldo honesto por conglomerados LOSO-D, ``retransformacion_v2.conglomerados_loso_d``), sensibilidad fija ½·σ²
(``<motor>~lognormal``) y, en LRO y BLQ-75, OOF interno (``<motor>~sens``, ``retransformacion_v2.tabla_interna``
con la estación, el grupo y el conglomerado de cada fila); intersección forzada de los pares finitos de todos los
motores; métricas por conjunto de evaluación (E1, E2, E2-SINCA y E1′), con niveles, desagregaciones, los cinco
regímenes (``metricas_v2.regimenes_de_config``) y la sensibilidad fila a fila con las columnas de las familias
leídas del panel en sólo lectura, escalas, pesos fijos por estación, desagrupamiento y números efectivos; cuantiles;
alertas; bootstrap pareado por bloques de inferencia (el bloque de 75 km de la estación en LOSO-D y LBO-10; B =
1.999) con Δ_r, Δ̄ y el ruido de la diferencia (3 réplicas), la segunda prueba (decide el cambio de signo del
bootstrap salvaje; el jackknife CV3 sólo informa), la regla de superioridad y su robustez sin el bloque más
influyente; Δ̄ sin cada bloque; y, en LRO y BLQ-75, la evidencia de la decisión (``decision_v2``: sumas por bloque
del nivel diario civil sobre los pares de la decisión, sin predicciones).

**Decisión** (``decidir``, por contaminante, sin cargar el panel): ``decision_v2.decidir_motor`` con la evidencia de
LRO y BLQ-75 y la factibilidad medida antes de cualquier ajuste comparativo, de los dos contaminantes
(``--factibilidad``; por omisión, el resumen de ``factibilidad_v2``; Complemento, punto 3). La decisión no se toma a
mano.

**Piloto** (§10, ``piloto_v2``): dos pliegues por protocolo (el de más y el de menos filas de entrenamiento),
los motores del eje A con el N común y los puntos de la curva de aprendizaje en un pliegue de LRO, con el mismo
``correr_pliegue`` en modo piloto: no guarda predicciones ni calcula métricas; mide tiempo de pared, CPU y memoria
de cada fase (``medidor``), extrapola las horas de máquina de la corrida completa y aplica en orden los cuatro
recortes de la Enmienda 1, punto 12 (``plan_protocolo``: 1, curvas de aprendizaje fuera de LRO; 2, MLP fuera de LRO
y BLQ-75; 3, semillas fuera de LRO y BLQ-75; 4, pérdidas del §6 fuera de LRO, BLQ-75 y LOSO-D), sin elección a mano
(``plan_corrida_v2.json`` en la raíz v2; Complemento, punto 8).

**Guardas de la consola.** El recorte del presupuesto lo elige el código con el piloto (Complemento, punto 8):
``correr`` y ``consolidar`` toman por omisión el ``recorte_aplicado`` de ``plan_corrida_v2.json`` (que debe haberse
hecho con el orden de recortes vigente y bajo el contrato vigente) y rechazan otro ``--recorte``, o un plan que no
sirve, salvo ``--forzar-recorte MOTIVO``, que queda en la bitácora del manifiesto (§10). ``consolidar`` y
``decidir`` sólo aceptan ``--replicas-bootstrap 1999`` (Complemento, punto 2) salvo ``--forzar MOTIVO``, que queda
registrado en ``consolidado.json`` o en ``decision.json``.

Uso::

    python -B scripts_modelo_1km/v2/correr_v2.py plan --contaminantes pm25 no2
    python -B scripts_modelo_1km/v2/correr_v2.py piloto --contaminantes pm25 no2 --hilos 12 --calibrar-familias
    python -B scripts_modelo_1km/v2/correr_v2.py correr --contaminantes pm25 --protocolos LRO BLQ-75 --hilos 12
    python -B scripts_modelo_1km/v2/correr_v2.py correr --contaminantes no2 --parte 0/2 --hilos 6   # y 1/2 en otro
    python -B scripts_modelo_1km/v2/correr_v2.py estado --contaminantes pm25 no2
    python -B scripts_modelo_1km/v2/correr_v2.py consolidar --contaminantes pm25 --protocolos LRO
    python -B scripts_modelo_1km/v2/correr_v2.py decidir --contaminantes pm25 no2
"""
from __future__ import annotations

import argparse
import contextlib
import functools
import hashlib
import inspect
import io
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _traza_v2 import fijar_hilos  # noqa: E402  (antes de numpy: fija el tope de hilos de BLAS y OpenMP)

if __name__ == "__main__":
    from _rutas_v2 import hilos_de_la_linea  # noqa: E402  (sólo biblioteca estándar)
    fijar_hilos(hilos_de_la_linea())

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import bootstrap_v2 as bs  # noqa: E402
import decision_v2 as dc  # noqa: E402
import metricas_v2 as mt  # noqa: E402
import motores_v2 as mv  # noqa: E402
import perdidas_v2 as pv  # noqa: E402
import retransformacion_v2 as rt  # noqa: E402
from _rutas_v2 import (  # noqa: E402
    CandadoOcupado, RutasV2, ahora_utc, candado_escritura, cargar_config, leer_json, normalizar_candado,
    publicar_bytes, publicar_json, publicar_parquet, rutas_v2, valor_vigente,
)
from _traza_v2 import commit_git, sha256_archivo, sha256_json, traza, versiones_bibliotecas  # noqa: E402
from pliegues_v2 import PROTOCOLOS, huella_pliegues  # noqa: E402
from vecindario_v2 import Vecindario  # noqa: E402

log = logging.getLogger("modelo_1km_v2.correr")

SCHEMA_PUNTO = "airpollution.modelo-1km-v2.comparacion-punto.v3"   # v3: código de ajuste por función (Complemento, 7)
SCHEMA_CONSOLIDADO = "airpollution.modelo-1km-v2.comparacion-consolidado.v3"   # v3: Complemento, puntos 1, 2 y 6
SCHEMA_TABLAS = "airpollution.modelo-1km-v2.comparacion-tablas.v3"
SCHEMA_PILOTO = "airpollution.modelo-1km-v2.comparacion-piloto.v1"
CARPETA = "comparacion"
ETIQUETA = "principal"
CODIGO_AJUSTE = ("motores_v2.py", "perdidas_v2.py", "vecindario_v2.py")
PROTOCOLOS_SEMILLAS = ("LRO", "BLQ-75")
PROTOCOLOS_CALIDAD = ("LOSO-D", "LRO")
VARIANTES_CALIDAD = ("validado_y_preliminar", "solo_validado")
ETIQUETAS_PERDIDA = ("l2_original", "huber", "huber_friedman", "q05", "q50", "q95")   # huber_friedman: sensibilidad (punto 9)
TAREA_DELTA_HUBER = "lightgbm_l2_original"          # el δ común de Huber se calcula en esta tarea (Enmienda 1, punto 9)
AQUI = Path(__file__).resolve().parent


class _SinMedir:
    """Medidor nulo. ``correr_pliegue`` y ``correr_internos`` envuelven cada fase (vecindario, permutación, filas,
    matrices, ajuste y predicción) en ``medidor.fase(**etiquetas)``; el piloto le pasa ``piloto_v2.Medidor``, que
    mide tiempo de pared, CPU y memoria, y fuera del piloto no se mide nada. El bloque recibe un dict de etiquetas
    que puede completar (p. ej., con las filas del pliegue)."""

    @contextlib.contextmanager
    def fase(self, **etiquetas):
        yield dict(etiquetas)


SIN_MEDIR = _SinMedir()


# ---------------------------------------------------------------------------
# Tareas y plan
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Tarea:
    """Un ajuste por pliegue. ``tope``: «N» (N común), un entero o None (todas las disponibles)."""

    id: str
    motor: str
    familia: str
    variante: str = mv.VARIANTE_REFERENCIA
    tope: object = "N"
    replica: int = 0
    calidad: str = "todo"
    salidas: tuple = ()

    def nombres(self) -> tuple[str, ...]:
        """Nombres de las predicciones que produce (con la réplica, si no es la 0)."""
        base = self.salidas or (self.id,)
        return tuple(b if self.replica == 0 else f"{b}@r{self.replica}" for b in base)


@dataclass
class Opciones:
    """Qué familias corren. ``recorte`` = 0 … 4: cuántos recortes del presupuesto se aplican, en el orden de la
    Enmienda 1, punto 12 (``presupuesto.orden_de_recortes``; ``recetas["recortes"]``)."""

    motores: tuple = mv.MOTORES_EJE_A
    perdidas: bool = True
    alertas: bool = True
    eje_b: bool = True
    curvas: bool = True
    semillas: bool = True
    apilado: bool = True
    calidad: bool = True
    recorte: int = 0


def niveles_de_recorte(recetas: dict) -> tuple[int, ...]:
    """Niveles de recorte del presupuesto: 0 (ninguno) … el número de recortes de la configuración (4)."""
    return tuple(range(len(recetas["recortes"]) + 1))


def recortado(recetas: dict, elemento: str, prot: str, recorte: int) -> bool:
    """¿Los recortes 1 … ``recorte`` quitan ``elemento`` (``curvas_de_aprendizaje``, ``mlp``, ``semillas`` o
    ``perdidas``) en ``prot``? Cada recorte lo conserva sólo en sus ``se_conserva_en`` (Enmienda 1, punto 12)."""
    if not 0 <= int(recorte) <= len(recetas["recortes"]):
        raise ValueError(f"recorte fuera de rango: {recorte} (0 … {len(recetas['recortes'])})")
    return any(x["elemento"] == elemento and x["orden"] <= int(recorte) and prot not in x["se_conserva_en"]
               for x in recetas["recortes"])


def plan_protocolo(recetas: dict, prot: str, op: Opciones, calidad_disponible: bool) -> dict:
    """Tareas de un protocolo según el contrato y los recortes del presupuesto (``op.recorte`` = 0 … 4), en el
    orden de la Enmienda 1, punto 12, implementado en el código (Complemento, punto 8): 1, curvas de aprendizaje
    fuera de LRO; 2, MLP fuera de LRO y BLQ-75; 3, semillas fuera de LRO y BLQ-75; 4, pérdidas del §6 fuera de LRO,
    BLQ-75 y LOSO-D. El recorte 3, leído con el §8 (3 semillas sólo en LRO y BLQ-75), no quita nada; se aplica tal
    cual (``presupuesto.orden_de_recortes`` → advertencia)."""
    if prot not in PROTOCOLOS:
        raise ValueError(f"protocolo desconocido: {prot}")
    rc = int(op.recorte)
    eje_a = [m for m in mv.MOTORES_EJE_A if m in op.motores]
    if recortado(recetas, "mlp", prot, rc):
        eje_a = [m for m in eje_a if m != "mlp"]
    tareas = [Tarea(m, m, "eje_A") for m in eje_a]
    perdidas = op.perdidas and not recortado(recetas, "perdidas", prot, rc)
    if perdidas:
        for m in mv.MOTORES_PERDIDAS:
            if m in op.motores:
                tareas += [Tarea(f"{m}_{e}", m, "perdidas", variante=e) for e in ETIQUETAS_PERDIDA]
    if op.alertas:
        tareas.append(Tarea("alertas_q80", "alertas", "alertas"))
    if op.eje_b:
        tareas += [Tarea("gp", "gp", "eje_B", tope=recetas["gp"]["tope"]),
                   Tarea("lme", "lme", "eje_B", tope=recetas["lme"]["tope"]),
                   Tarea("lineales", "lineales", "eje_B", tope=None, salidas=mv.MOTORES_LINEALES)]
    curvas = (op.curvas and prot in recetas["protocolos_curvas"]
              and not recortado(recetas, "curvas_de_aprendizaje", prot, rc))
    if curvas:
        for m in ("lightgbm", "xgboost", "random_forest"):
            if m in eje_a:
                for t in recetas["curvas"][m]:
                    if t != recetas["N_comun"]:
                        tareas.append(Tarea(f"{m}_n{'todas' if t is None else t}", m, "curva", tope=t))
    semillas = op.semillas and prot in PROTOCOLOS_SEMILLAS and not recortado(recetas, "semillas", prot, rc)
    if semillas:
        tareas += [Tarea(m, m, "eje_A", replica=r) for r in (1, 2) for m in eje_a]
    if op.calidad and calidad_disponible and prot in PROTOCOLOS_CALIDAD and "lightgbm" in eje_a:
        tareas += [Tarea(f"lightgbm_cal_{v}", "lightgbm", "calidad", calidad=v) for v in VARIANTES_CALIDAD]
    bases = recetas["apilado"]["bases"]
    interno = (op.apilado and prot in recetas["apilado"]["protocolos"] and all(b in eje_a for b in bases))
    aplicados = [x["recorte"] for x in recetas["recortes"] if x["orden"] <= rc]
    quitan = [x["recorte"] for x in recetas["recortes"] if x["orden"] <= rc and prot not in x["se_conserva_en"]]
    return {"protocolo": prot, "tareas": tareas, "interno": list(bases) if interno else [],
            "semillas": semillas, "curvas": curvas, "perdidas": perdidas, "mlp": "mlp" in eje_a, "recorte": rc,
            "recortes_aplicados": aplicados, "recortes_que_tocan_el_protocolo": quitan}


def _orden_tareas(tareas) -> list:
    """Agrupa por réplica, tope y calidad (reusa la matriz de entrenamiento) y deja l2_original antes de Huber (el
    δ común sale de ``lightgbm_l2_original``, que va antes que todas las tareas de XGBoost)."""
    prioridad = {"l2_original": 0, "huber": 1, "huber_friedman": 1}
    return sorted(tareas, key=lambda t: (t.replica, str(t.tope), t.calidad, t.motor == "lineales",
                                         t.motor, prioridad.get(t.variante, 2), t.id))


# ---------------------------------------------------------------------------
# Contexto de un contaminante
# ---------------------------------------------------------------------------
@dataclass
class Contexto:
    """Todo lo que un pliegue necesita de un contaminante, en memoria y alineado con el panel."""

    pol: str
    rutas: RutasV2
    cfg: dict
    recetas: dict
    etiqueta: str
    hilos: int
    feats: list
    X: np.ndarray
    y: np.ndarray
    hora_local: np.ndarray
    macrozona: np.ndarray
    anio: np.ndarray
    ts_utc: np.ndarray
    poblacion: np.ndarray
    vec: Vecindario
    manifiesto_pol: dict
    huella_pliegues: str
    identidad_panel: str
    calidad: np.ndarray | None = None
    huella_calidad: str | None = None
    insumos: dict = field(default_factory=dict)
    regimen_fila_a_fila: tuple | None = None      # (código por fila, etiquetas, registro): familias leídas del panel
    _lineales: object = None
    _traza: dict | None = None
    _huellas: dict | None = None
    _congl: np.ndarray | None = None

    @property
    def n(self) -> int:
        return len(self.y)

    def huellas_firma(self) -> dict:
        """sha256 de la lista ordenada de predictores, del contrato y de la configuración en uso (Enmienda 1,
        punto 14). El contrato es el archivo si existe; si no (raíces de prueba), el que declara la configuración."""
        if self._huellas is None:
            contrato = (sha256_archivo(self.rutas.contrato) if self.rutas.contrato.exists()
                        else self.cfg.get("contrato", {}).get("sha256"))
            self._huellas = {"predictores": {"n": len(self.feats), "sha256": sha256_json(list(self.feats))},
                             "contrato": contrato, "configuracion": sha256_json(self.cfg)}
        return self._huellas

    # --- Construcción -------------------------------------------------------
    @classmethod
    def desde_tablas(cls, pol: str, panel: pd.DataFrame, manifiesto: dict, cfg: dict, rutas: RutasV2,
                     etiqueta: str = ETIQUETA, hilos: int | None = None, calidad=None, vec: Vecindario | None = None,
                     identidad_panel: str | None = None, insumos: dict | None = None) -> "Contexto":
        """Contexto desde un panel en memoria (filas en el orden del panel) y el manifiesto de pliegues. El régimen
        de predictores fila a fila (sensibilidad del punto 10) se calcula aquí con las columnas de las familias que
        trae el panel, sean o no predictores del motor (``regimen_de_panel``), y el panel no se modifica."""
        recetas = mv.recetas_de(cfg, hilos)
        h = recetas["hilos"]
        feats = list(cfg["motores"]["eje_A"]["predictores"][pol])
        faltan = [c for c in feats if c not in panel.columns]
        if faltan:
            raise SystemExit(f"{pol}: el panel no tiene los predictores {faltan}")
        if huella_pliegues(manifiesto) != manifiesto.get("huella_pliegues"):
            raise SystemExit("el manifiesto de pliegues no calza con su propia huella")
        if vec is None:
            coords = {e["estacion"]: (e["lat"], e["lon"]) for e in manifiesto["estaciones"]}
            imp = cfg["vecindario"]["implementacion"]
            vec = Vecindario(pol, panel["estacion"], panel["ts_utc"].to_numpy(), panel["obs"].to_numpy(), coords,
                             anio=panel["anio"].to_numpy(), h_km=float(imp["ancho_km"]),
                             umbral=float(imp["umbral_suma_de_pesos"]), hilos=h)
        est_panel = panel["estacion"].astype(str).to_numpy()
        if not np.array_equal(vec.estaciones[vec.js], est_panel):
            raise SystemExit(f"{pol}: el vecindario no está alineado con el panel (estación)")
        if not np.array_equal(vec.tiempos[vec.it].to_numpy(), panel["ts_utc"].to_numpy("datetime64[ns]")):
            raise SystemExit(f"{pol}: el vecindario no está alineado con el panel (ts_utc)")
        X = np.ascontiguousarray(panel[feats].to_numpy(np.float32))
        y = panel["obs"].to_numpy("float64")
        if identidad_panel is None:
            identidad_panel = sha256_json({"X": _sha(X), "y": _sha(y), "estacion": list(map(str, vec.estaciones)),
                                           "ts_utc": _sha(panel["ts_utc"].to_numpy("datetime64[ns]")), "filas": int(len(y))})
        qc, huella_qc = None, None
        if calidad is not None:
            qc = np.asarray(calidad, dtype=object)
            if len(qc) != len(y):
                raise SystemExit(f"{pol}: la bandera de calidad no tiene una entrada por fila")
            cat = pd.Categorical(pd.Series(qc).astype(str))
            huella_qc = sha256_json({"categorias": list(cat.categories), "codigos": _sha(np.asarray(cat.codes))})
        return cls(pol=pol, rutas=rutas, cfg=cfg, recetas=recetas, etiqueta=etiqueta, hilos=h, feats=feats, X=X, y=y,
                   hora_local=panel["hora_local"].to_numpy().astype("int64"),
                   macrozona=panel["macrozona_cod"].to_numpy().astype("int64"),
                   anio=panel["anio"].to_numpy().astype("int64"), ts_utc=panel["ts_utc"].to_numpy("datetime64[ns]"),
                   poblacion=panel["pob_dens"].to_numpy("float64"), vec=vec, manifiesto_pol=manifiesto["contaminantes"][pol],
                   huella_pliegues=manifiesto["huella_pliegues"], identidad_panel=identidad_panel, calidad=qc,
                   huella_calidad=huella_qc, insumos=dict(insumos or {}), regimen_fila_a_fila=regimen_de_panel(panel, cfg))

    @classmethod
    def desde_disco(cls, pol: str, rutas: RutasV2 | None = None, cfg: dict | None = None, etiqueta: str = ETIQUETA,
                    hilos: int | None = None, con_calidad: bool = True) -> "Contexto":
        """Panel v1 (sólo lectura), manifiesto de pliegues y, si existe, la bandera de calidad de la raíz v2."""
        import pyarrow.parquet as pq

        r = rutas or rutas_v2()
        cfg = cfg if cfg is not None else cargar_config(r)
        h = int(cfg["operacion"]["hilos_maximos"]) if hilos is None else int(hilos)
        if "red_de_monitores" in cfg and not con_calidad:   # Enmienda 2: la bandera es obligatoria, sin excepción
            raise SystemExit(f"{pol}: con la red ampliada la bandera de calidad es obligatoria: no se corre sin "
                             f"calidad (--sin-calidad)")
        man = leer_json(r.manifiesto_pliegues)
        if man is None:
            raise SystemExit(f"Falta el manifiesto de pliegues {r.relativa(r.manifiesto_pliegues)}")
        if "red_de_monitores" in cfg:                     # Enmienda 2, R22 paso 4: el que registró el anexo
            import pliegues_red2_v2
            man = pliegues_red2_v2.exigir_registro(r, cfg, r.manifiesto_pliegues)
        vec = Vecindario.desde_panel(pol, r, manifiesto=man, cfg=cfg, hilos=h)
        feats = list(cfg["motores"]["eje_A"]["predictores"][pol])
        columnas = list(dict.fromkeys(["estacion", "ts_utc", "obs", "anio", "hora_local", "macrozona_cod", "pob_dens",
                                       *feats]))
        # las columnas de las familias del régimen fila a fila (punto 10) que trae el panel, aunque no sean predictores
        esquema = set(pq.read_schema(r.panel(pol)).names)
        columnas += [c for c in columnas_de_familias(cfg) if c in esquema and c not in columnas]
        panel = pq.read_table(r.panel(pol), columns=columnas, read_dictionary=["estacion"]).to_pandas()
        calidad, insumos = None, {f"panel_{pol}": r.panel(pol), "manifiesto_pliegues": r.manifiesto_pliegues}
        if con_calidad:
            import calidad_v2
            ruta_qc = calidad_v2.ruta_calidad(r, pol)
            if ruta_qc.exists():
                calidad = calidad_v2.cargar_bandera(pol, panel[["estacion", "ts_utc"]], r)["qc"].to_numpy(dtype=object)
                insumos[f"calidad_{pol}"] = ruta_qc
            elif "red_de_monitores" in cfg:                   # Enmienda 2: la bandera es obligatoria
                raise SystemExit(f"{pol}: con la red ampliada la bandera de calidad es obligatoria "
                                 f"({r.relativa(ruta_qc)['ruta']}, la escribe panel_red2_v2)")
            else:
                log.warning("%s: no hay bandera de calidad (%s); sin variantes ni evaluación sobre validadas", pol,
                            r.relativa(ruta_qc)["ruta"])
        return cls.desde_tablas(pol, panel, man, cfg, r, etiqueta, h, calidad=calidad, vec=vec,
                                identidad_panel=man["contaminantes"][pol]["panel"]["sha256"], insumos=insumos)

    # --- Utilidades ---------------------------------------------------------
    def pliegues(self, prot: str) -> list[dict]:
        return self.manifiesto_pol["protocolos"][prot]["pliegues"]

    def matriz(self, filas: np.ndarray, rec) -> np.ndarray:
        """Predictores de ``filas`` con el vecindario del recálculo ``rec`` (copia)."""
        X = self.X[filas]
        rec.asignar(X, self.feats, filas=filas)
        return X

    def estaciones_de(self, filas: np.ndarray) -> np.ndarray:
        """Nombre de la estación de cada fila (para la validación agrupada de la MLP)."""
        return self.vec.estaciones[self.vec.js[filas]]

    def tope(self, t) -> int | None:
        return self.recetas["N_comun"] if t == "N" else t

    def codigos_qc(self, variante: str) -> list[str]:
        prov = valor_vigente(self.cfg["calidad_blanco"]["codigos_qc"], "calidad_blanco.codigos_qc")
        return list(prov[variante])

    def mascara_calidad(self, variante: str) -> np.ndarray | None:
        if variante == "todo":
            return None
        if self.calidad is None:
            raise SystemExit(f"{self.pol}: la variante de calidad {variante} necesita calidad_{self.pol}.parquet")
        return np.isin(self.calidad.astype(str), self.codigos_qc(variante))

    def lineales(self) -> mv.LinealesPorUnidades:
        if self._lineales is None:
            v = self.cfg["protocolos"]["LPO"]["ventanas"]
            ventana = (self.anio - int(v["anio_desde"])) // int(v["largo_anios"])
            self._lineales = mv.LinealesPorUnidades(self.pol, self.feats, self.X, self.y, self.vec.js, ventana,
                                                    self.vec.D, self.recetas["lineales"])
        return self._lineales

    def grupo_de_estacion(self, prot: str) -> np.ndarray:
        """Etiqueta del grupo de ``prot`` de cada estación (código del vecindario)."""
        g = np.full(len(self.vec.estaciones), "", dtype=object)
        for f in self.pliegues(prot):
            g[self.vec.indices(f["estaciones_prueba"])] = f["grupo"]
        return g

    def conglomerado_de_estacion(self) -> np.ndarray:
        """Código entero del conglomerado LOSO-D (su k) de cada estación, en el orden del vecindario, con
        ``retransformacion_v2.conglomerados_loso_d`` (cada estación en un solo conglomerado del manifiesto)."""
        if self._congl is None:
            self._congl = rt.conglomerados_loso_d(self.manifiesto_pol, [str(s) for s in self.vec.estaciones])
        return self._congl

    def codigo_ajuste(self) -> dict:
        """Código de ajuste de la firma (Complemento, punto 7): el sha256 de cada archivo de ``CODIGO_AJUSTE`` y el
        de cada función de ``FUNCIONES_AJUSTE`` (su código fuente), tomados al importar este módulo: la firma es la
        del código que corre, aunque los archivos cambien durante la corrida."""
        return {**huella_archivos_ajuste(), "funciones": huella_funciones_ajuste()}

    def traza_base(self) -> dict:
        if self._traza is None:
            self._traza = traza(self.insumos, {"nota": "las semillas de cada ajuste van en el punto de control"},
                                self.hilos, rutas=self.rutas, parametros={"etiqueta": self.etiqueta})
        return self._traza

    def raiz(self) -> Path:
        return self.rutas.raiz_v2 / CARPETA / self.etiqueta / self.pol


# ---------------------------------------------------------------------------
# Puntos de control
# ---------------------------------------------------------------------------
def ruta_punto(ctx: Contexto, prot: str, k: int, sub: str, nombre: str) -> Path:
    return ctx.raiz() / prot / f"k{int(k):03d}" / sub / f"{nombre}.npz"


def guardar_punto(ruta: Path, arreglos: dict, meta: dict, rutas: RutasV2) -> str:
    """``.npz`` atómico (bytes en memoria y ``publicar_bytes``, que exige el candado) con ``meta`` en JSON."""
    buf = io.BytesIO()
    texto = json.dumps(meta, ensure_ascii=False, sort_keys=True, default=_a_json)
    np.savez(buf, meta=np.array(texto), **arreglos)
    return publicar_bytes(buf.getvalue(), ruta, rutas)


def leer_punto(ruta: Path) -> tuple[dict, dict] | None:
    if not ruta.exists():
        return None
    with np.load(ruta, allow_pickle=False) as c:
        arreglos = {k: c[k] for k in c.files if k != "meta"}
        meta = json.loads(str(c["meta"]))
    return arreglos, meta


def firma_vigente(ruta: Path, firma: str) -> bool:
    p = leer_punto(ruta)
    return p is not None and p[1].get("firma") == firma


def _a_json(o):
    if hasattr(o, "item") and callable(o.item) and getattr(o, "ndim", 0) == 0:
        return o.item()
    if hasattr(o, "tolist"):
        return o.tolist()
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if isinstance(o, Path):
        return o.name
    return str(o)


def _sha(a: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


# Motores cuyo resultado no depende del número de hilos: LightGBM con deterministic=True (así lo garantiza su
# documentación) y el bosque de scikit-learn con random_state fijo. En los demás (XGBoost, MLP, GP, LME y los
# lineales, que usan BLAS) los hilos entran en la firma: reanudar con otros --hilos rehace esos ajustes.
INVARIANTES_A_HILOS = ("lightgbm", "random_forest", "alertas")
DECLARACION_HUBER = ("con el gradiente recortado y 800 rondas, los picos invernales pueden quedar fuera de alcance; "
                     "Huber no estima la media y no compite en el §9 (Enmienda 1, punto 9)")


def hilos_de_firma(ctx: Contexto, tarea) -> int | None:
    return None if tarea is not None and tarea.motor in INVARIANTES_A_HILOS else ctx.hilos


def es_huber(tarea: Tarea) -> bool:
    return tarea.motor in mv.MOTORES_PERDIDAS and tarea.variante in ("huber", "huber_friedman")


def receta_de(ctx: Contexto, tarea: Tarea) -> dict:
    """Receta efectiva del ajuste. Las tareas que fijan o usan el δ de Huber llevan además su regla."""
    r = ctx.recetas
    if tarea.motor == "lineales":
        return r["lineales"]
    if tarea.motor == "alertas":
        return r["alertas"]
    if tarea.id == TAREA_DELTA_HUBER or es_huber(tarea):
        return {**r[tarea.motor], "huber": r["huber"]}
    return r[tarea.motor]


def perdida_de(ctx: Contexto, tarea: Tarea) -> dict:
    """La pérdida del ajuste, para la firma (Enmienda 1, punto 14)."""
    if tarea.motor in mv.MOTORES_EJE_A:
        return pv.variante_de_etiqueta(tarea.variante).descripcion()
    if tarea.motor == "alertas":
        p = ctx.recetas["alertas"]["params"]
        return {"objetivo": p["objective"], "alpha": float(p["alpha"]), "blanco": "log1p"}
    return {"ajuste": tarea.motor, "blanco": "y" if tarea.motor == "lineales" else "log1p"}


def variante_calidad_de(ctx: Contexto, tarea: Tarea) -> dict:
    """La variante de calidad del ajuste (con sus códigos y la huella de la bandera), para la firma."""
    if tarea.calidad == "todo":
        return {"id": "todo", "codigos": None, "huella_bandera": None}
    return {"id": tarea.calidad, "codigos": ctx.codigos_qc(tarea.calidad), "huella_bandera": ctx.huella_calidad}


@functools.lru_cache(maxsize=1)
def _bibliotecas() -> dict:
    """Versiones de las bibliotecas (no cambian dentro de un proceso; la firma se calcula miles de veces)."""
    return versiones_bibliotecas()


def _base_firma(ctx: Contexto, prot: str, pliegue: dict) -> dict:
    """Lo común a las firmas de un pliegue. El código de ajuste (archivos y funciones) reemplaza a la versión que se
    subía a mano (Complemento, punto 7)."""
    hf = ctx.huellas_firma()
    return {"schema": SCHEMA_PUNTO, "contaminante": ctx.pol,
            "panel": ctx.identidad_panel, "predictores": hf["predictores"], "huella_pliegues": ctx.huella_pliegues,
            "protocolo": prot, "k": int(pliegue["k"]), "grupo": pliegue["grupo"],
            "excluidas": list(pliegue.get("excluidas", [])), "exclusion_temporal": pliegue.get("exclusion_temporal"),
            "contrato": hf["contrato"], "configuracion": hf["configuracion"], "codigo_ajuste": ctx.codigo_ajuste(),
            "bibliotecas": _bibliotecas()}


def firma_tarea(ctx: Contexto, prot: str, pliegue: dict, tarea: Tarea, huella_vec: dict, filas: np.ndarray,
                extra: dict | None = None, hilos="ctx") -> str:
    """Identidad de un ajuste (Enmienda 1, punto 14; Complemento, punto 7): la base del pliegue (panel, predictores,
    pliegues, contrato, configuración, código de ajuste con el hash de cada función que define filas, semillas,
    vecindario o ajuste, y bibliotecas), la tarea, la receta, la pérdida, la variante de calidad, las filas de
    entrenamiento, el vecindario y las **semillas efectivas** (``_semillas``: permutación, motor, sorteo de la
    validación de la MLP, partición honesta del δ y pliegues internos). ``hilos="ctx"`` usa los de la corrida (o
    ninguno si el motor es invariante)."""
    h = hilos_de_firma(ctx, tarea) if hilos == "ctx" else hilos
    return sha256_json({**_base_firma(ctx, prot, pliegue), "tarea": asdict(tarea), "receta": _receta_firma(ctx, tarea),
                        "perdida": perdida_de(ctx, tarea), "variante_calidad": variante_calidad_de(ctx, tarea),
                        "filas_entrenamiento": {"n": int(len(filas)), "sha256": _sha(filas)}, "vecindario": huella_vec,
                        "semillas": _semillas(ctx, tarea, int(pliegue["k"])), "hilos": h, **(extra or {})})


def componentes_firma(ctx: Contexto, tarea: Tarea) -> dict:
    """Lo que la firma agrega por la Enmienda 1 (punto 14) y el Complemento (punto 7), legible en el punto de
    control."""
    hf = ctx.huellas_firma()
    return {"predictores": hf["predictores"], "contrato": hf["contrato"], "configuracion": hf["configuracion"],
            "perdida": perdida_de(ctx, tarea), "variante_calidad": variante_calidad_de(ctx, tarea),
            "codigo_ajuste": ctx.codigo_ajuste()}


def _receta_firma(ctx: Contexto, tarea: Tarea) -> dict:
    """Receta sin los hilos (que entran aparte, sólo donde importan)."""
    def sin_hilos(o):
        if isinstance(o, dict):
            return {k: sin_hilos(v) for k, v in o.items() if k not in ("num_threads", "nthread", "n_jobs", "hilos")}
        return o
    return sin_hilos(receta_de(ctx, tarea))


def firma_vecindario(ctx: Contexto, prot: str, pliegue: dict) -> str:
    """Identidad del recálculo del pliegue; sus valores quedan además en la huella sha256 de las tres columnas."""
    return sha256_json({**_base_firma(ctx, prot, pliegue), "vecindario_base": ctx.vec.huella()["huella"],
                        "parametros": ctx.vec.parametros(con_tamano=False)})


def nombre_candado_pliegue(etiqueta: str, pol: str, prot: str, k: int) -> str:
    """Candado del artefacto «puntos de control de un pliegue»: el que deriva ``_rutas_v2.candado_de`` de sus rutas,
    con el nombre normalizado (NFC + casefold; Complemento, punto 10)."""
    return normalizar_candado(f"{CARPETA}.{etiqueta}.{pol}.{prot}.k{int(k):03d}")


def verificar_sellado(r: RutasV2, permitir_sin_sellar: bool = False, git: dict | None = None) -> dict:
    """Sellado (Enmienda 1, punto 14): el contrato, la configuración y el código v2 se confirman en git antes de
    cualquier ajuste comparativo. Sin commit conocido o con cambios sin confirmar en ``scripts_modelo_1km/v2``, se
    detiene, salvo ``permitir_sin_sellar`` (pruebas), que lo deja registrado en el log. Devuelve el estado de git."""
    estado_git = git if git is not None else commit_git(r.repo)
    pendientes = list(estado_git.get("v2_sin_commit") or [])
    sellado = estado_git.get("commit") not in (None, "desconocido") and not pendientes
    if not sellado:
        mensaje = (f"sellado pendiente: commit {estado_git.get('commit')}, cambios sin confirmar en scripts_modelo_1km/v2: "
                   f"{pendientes[:8]}{' …' if len(pendientes) > 8 else ''}. El contrato, la configuración y el código se "
                   f"confirman en git antes de cualquier ajuste comparativo (Enmienda 1, punto 14)")
        if not permitir_sin_sellar:
            raise SystemExit(mensaje)
        log.warning("%s; se sigue por --sin-sellar", mensaje)
    return {**estado_git, "sellado": sellado}


# ---------------------------------------------------------------------------
# Un pliegue
# ---------------------------------------------------------------------------
def _crear(ctx: Contexto, tarea: Tarea, k: int, delta: float | None = None):
    if tarea.motor == "gp":
        return mv.ModeloGP(ctx.recetas["gp"], ctx.pol, ctx.feats, mv.SEMILLA_BASE + int(k), ctx.hilos)
    if tarea.motor == "lme":
        return mv.ModeloLME(ctx.recetas["lme"], ctx.pol, ctx.feats)
    variante = pv.variante_de_etiqueta(tarea.variante)
    if variante.nombre == "huber":
        variante = variante.con_delta(delta)
    return mv.crear_modelo(tarea.motor, ctx.recetas, variante, 0, replica=tarea.replica, k=k)


def _semillas(ctx: Contexto, tarea: Tarea, k: int) -> dict:
    """Semillas efectivas de un ajuste, que entran en su firma (Complemento, punto 7) y en su traza: la de la
    permutación común (``[42, k]`` o ``[42, k, r]``, §4), la del motor (la de la receta, o 42 + k en RF, MLP y GP,
    más 1.000·r), la del sorteo de la validación agrupada de la MLP (la de la MLP; Enmienda 1, punto 6), la de la
    partición honesta del δ de Huber (``[42, k, 1001]``; punto 9) y la de los pliegues internos (``[42, k, 1000]``)."""
    r = tarea.replica
    s = {"permutacion": mv.semilla_permutacion(k, r)}
    if tarea.motor in ("lightgbm", "xgboost"):
        s["motor"] = mv.semilla_motor(ctx.recetas[tarea.motor]["params"]["seed"], r)
    elif tarea.motor in ("random_forest", "mlp", "gp"):
        s["motor"] = mv.semilla_motor(mv.SEMILLA_BASE + int(k), r)
    elif tarea.motor == "alertas":
        s["motor"] = mv.semilla_motor(ctx.recetas["alertas"]["params"]["seed"], r)
    if tarea.motor == "mlp":
        s["validacion"] = s["motor"]                      # sorteo de las unidades de validación (validacion_mlp)
    if tarea.id == TAREA_DELTA_HUBER:
        s["particion_honesta"] = [mv.SEMILLA_BASE, int(k), mv.SEMILLA_PARTICION_HONESTA]
    if tarea.familia == "interno":
        s["internos"] = [mv.SEMILLA_BASE, int(k), mv.SEMILLA_INTERNOS]
    return s


MEDIDA_DESDE_INTERNA = ("las estaciones del conjunto interno de validación con filas en el entrenamiento del pliegue "
                        "(las que validan; las que no tienen filas allí no se miden)")


def estaciones_con_filas(ctx: Contexto, filas) -> list[str]:
    """Estaciones (nombres, ordenados) con alguna fila en ``filas`` (índices del panel)."""
    f = np.asarray(filas, dtype="int64")
    if not len(f):
        return []
    return sorted(str(s) for s in ctx.vec.estaciones[np.unique(ctx.vec.js[f])])


def amortiguador_interno(ctx: Contexto, prot: str, internas, excluidas=(), *, filas=None) -> tuple[list[str], dict]:
    """Amortiguador de una partición interna de BLQ-75 (Complemento de la Enmienda 1, punto 5): las estaciones a
    ≤ 10 km (haversine, ``protocolos.BLQ-75.exclusion_adicional.particiones_internas``) de alguna estación del
    conjunto interno de validación ``internas``, que no son de él ni del conjunto ya excluido ``excluidas``. Se
    suman al conjunto excluido de la partición interna: salen de las filas del entrenamiento interno y de su
    vecindario. Fuera de BLQ-75 no hay amortiguador interno.

    Con ``filas`` (las del entrenamiento del pliegue, como lo pasan la validación de la MLP, la partición honesta del
    δ y los pliegues internos) la distancia se mide **sólo desde las estaciones internas con filas en él**: las que no
    tienen (p. ej., las del conjunto excluido externo, o las que el tope dejó sin filas) no validan nada; se registran
    aparte (``internas_sin_filas``) y tampoco entran al amortiguador. Sin ``filas`` (uso aislado), desde todas.
    Devuelve los nombres y el registro."""
    regla = ctx.recetas["amortiguador_interno"]
    if prot not in regla["protocolos"]:
        return [], {"aplica": False, "protocolo": prot}
    todas = sorted({str(s) for s in internas})
    if filas is None:
        medidas, sin_filas, desde = todas, [], "las estaciones dadas del conjunto interno de validación"
    else:
        con = set(estaciones_con_filas(ctx, filas))
        medidas = [s for s in todas if s in con]
        sin_filas = [s for s in todas if s not in con]
        desde = MEDIDA_DESDE_INTERNA
    registro = {"aplica": True, "radio_km": float(regla["radio_km"]), "comparacion": regla["comparacion"],
                "distancia": regla["distancia"], "medida_desde": desde,
                "fuente": "Complemento de la Enmienda 1, punto 5", "internas": len(medidas),
                "internas_sin_filas": sin_filas}
    if not medidas:
        return [], {**registro, "estaciones": []}
    idx = ctx.vec.indices(medidas)
    ya_fuera = sorted({str(s) for s in excluidas} | set(sin_filas))
    fuera = ctx.vec.indices(ya_fuera) if ya_fuera else np.zeros(0, dtype="int64")
    cerca = mv.estaciones_a_radio(ctx.vec.D, idx, fuera, regla["radio_km"])
    nombres = sorted(str(s) for s in ctx.vec.estaciones[cerca])
    distancias = {s: round(float(ctx.vec.D[idx, i].min()), 4) for s, i in zip(nombres, np.flatnonzero(cerca))}
    return nombres, {**registro, "estaciones": nombres, "distancia_minima_km": distancias}


def _mascara_de_estaciones(ctx: Contexto, filas: np.ndarray, nombres) -> np.ndarray:
    """Máscara sobre ``filas`` de las filas de las estaciones ``nombres``."""
    if not len(nombres):
        return np.zeros(len(filas), dtype=bool)
    en = np.zeros(len(ctx.vec.estaciones), dtype=bool)
    en[ctx.vec.indices(nombres)] = True
    return en[ctx.vec.js[filas]]


def validacion_mlp(ctx: Contexto, prot: str, filas: np.ndarray, excluidas_base, semilla, contexto: dict | None = None,
                   medidor=None, etiquetas: dict | None = None) -> mv.ValidacionMLP:
    """Validación de la parada temprana de la MLP sobre las filas de entrenamiento ``filas`` (Enmienda 1, punto 6).

    En LRO y BLQ-75, grupos completos del protocolo (``motores_v2.seleccionar_grupos_validacion``); en los demás,
    conglomerados LOSO-D (``sortear_conglomerados_validacion``), con ``default_rng(semilla)``, la semilla de la MLP
    (``_semillas(...)["validacion"]``). En BLQ-75, las estaciones a ≤ 10 km de las de validación con filas en
    ``filas`` tampoco entrenan en esa fase (``amortiguador_interno``; Complemento, punto 5). El vecindario de esa fase
    se recalcula sin el conjunto excluido del pliegue (``excluidas_base``), **sin las estaciones de validación** y sin
    las del amortiguador, en todas las filas."""
    med = medidor or SIN_MEDIR
    etiq = dict(etiquetas or {})
    fraccion = ctx.recetas["mlp"]["fraccion_validacion"]
    js = ctx.vec.js[filas]
    if prot in mv.PROTOCOLOS_VALIDACION_POR_GRUPOS:
        g_est = ctx.grupo_de_estacion(prot)
        elegidos, registro = mv.seleccionar_grupos_validacion(g_est[js], ctx.macrozona[filas], semilla, fraccion)
        en_val = np.isin(g_est, elegidos)
    else:
        c_est = ctx.grupo_de_estacion("LOSO-D")
        presentes = np.unique(c_est[js])
        elegidos = mv.sortear_conglomerados_validacion(presentes, semilla, fraccion)
        en_val = np.isin(c_est, elegidos)
        registro = {"unidad": "conglomerados LOSO-D", "conglomerados_presentes": int(len(presentes)),
                    "conglomerados": elegidos}
        if not elegidos:
            registro["motivo"] = "menos de dos conglomerados en el entrenamiento: sin validación agrupada"
    val = en_val[js]
    estaciones = sorted(str(s) for s in ctx.vec.estaciones[np.flatnonzero(en_val)])
    amort, reg_amort = amortiguador_interno(ctx, prot, estaciones if val.any() else [], excluidas_base, filas=filas)
    fuera = _mascara_de_estaciones(ctx, filas, amort)
    registro.update({"protocolo": prot, "semilla": semilla, "estaciones": estaciones, "filas_validacion": int(val.sum()),
                     "fraccion_filas": float(val.mean()) if len(val) else float("nan"),
                     "amortiguador_interno": reg_amort, "filas_amortiguador": int(fuera.sum())})
    if not (val.any() and (~val & ~fuera).any()):
        registro.setdefault("motivo", "sin filas de validación o sin filas que entrenen fuera del amortiguador: "
                                      "sin parada temprana")
        return mv.ValidacionMLP(filas=np.zeros(len(filas), dtype=bool), X=None, registro=registro)
    excl = sorted({str(s) for s in excluidas_base} | set(estaciones) | set(amort))
    with med.fase(**etiq, fase="vecindario_validacion"):
        rec_v = ctx.vec.recalcular(excl, contexto={**(contexto or {}), "validacion_mlp": registro["unidad"]})
    with med.fase(**etiq, fase="matriz_validacion"):
        Xv = ctx.matriz(filas, rec_v)
    registro["vecindario"] = {"excluidas": int(len(excl)), "sha256": rec_v.registro.get("sha256")}
    return mv.ValidacionMLP(filas=val, X=Xv, registro=registro, fuera=fuera if fuera.any() else None)


def delta_huber_honesto(ctx: Contexto, prot: str, pliegue: dict, filas: np.ndarray, devolver_residuos: bool = False):
    """δ común de Huber del pliegue (Enmienda 1, punto 9): partición agrupada en dos de los conglomerados LOSO-D de
    las filas con tope (``motores_v2.particion_honesta``); cada mitad se predice con el ``l2_original`` de LightGBM
    (receta del eje A, réplica 0) ajustado en la otra, con el vecindario recalculado sin el conjunto excluido del
    pliegue ni las estaciones de la mitad que se predice (las de sus conglomerados). En BLQ-75 el ajuste de cada
    mitad saca además, de sus filas y de su vecindario, las estaciones a ≤ 10 km de las de la mitad que se predice
    con filas en ``filas`` (``amortiguador_interno``; Complemento, punto 5). δ = 1,345 × MAD normalizado de
    r = y − ŷ y, para la sensibilidad, el cuantil 0,9 de |r| (Friedman 2001). Con ``devolver_residuos`` devuelve
    además r y la máscara de la mitad 1 (para verificar que son honestos)."""
    k = int(pliegue["k"])
    js = ctx.vec.js[filas]
    c_est = ctx.grupo_de_estacion("LOSO-D")
    en_1, definicion = mv.particion_honesta(c_est[js], k)
    externas = [str(s) for s in pliegue.get("excluidas", [])]
    r = np.full(len(filas), np.nan)
    estaciones, huellas, amortiguadores = [], [], []
    for mitad in (0, 1):
        pred = en_1 if mitad == 1 else ~en_1
        est_m = sorted(str(s) for s in ctx.vec.estaciones[np.isin(c_est, definicion["conglomerados"][mitad])])
        amort, reg_amort = amortiguador_interno(ctx, prot, est_m, externas, filas=filas)
        fuera = _mascara_de_estaciones(ctx, filas, amort)
        rec_m = ctx.vec.recalcular(sorted(set(externas) | set(est_m) | set(amort)),
                                   contexto={"protocolo": prot, "k": k, "grupo": pliegue["grupo"], "particion_honesta": mitad})
        ajuste, prueba = filas[~pred & ~fuera], filas[pred]
        if len(ajuste) == 0:
            raise ValueError(f"{prot} k={k}: la partición honesta deja sin filas el ajuste de la mitad {1 - mitad}")
        modelo = mv.crear_modelo("lightgbm", ctx.recetas, pv.Variante("l2_original"), 0, replica=0, k=k)
        modelo.ajustar(ctx.matriz(ajuste, rec_m), ctx.y[ajuste])
        r[pred] = ctx.y[prueba] - modelo.predecir(ctx.matriz(prueba, rec_m))
        estaciones.append(est_m)
        huellas.append(rec_m.registro.get("sha256"))
        amortiguadores.append({**reg_amort, "filas_fuera_del_ajuste": int(fuera.sum())})
    d = pv.deltas_honestos(r)
    info = {"delta_huber": d["mad"], "delta_huber_friedman": d["friedman"], "mad_normalizado": d["mad_normalizado"],
            "residuos_honestos": d["residuos"], "factor": pv.FACTOR_HUBER, "cuantil_friedman": pv.CUANTIL_FRIEDMAN,
            "ajuste_cuadratico": {"motor": "lightgbm", "variante": "l2_original", "receta": "la del eje A",
                                  "comun_a": list(mv.MOTORES_PERDIDAS)},
            "particion_honesta": {**definicion, "estaciones": estaciones, "vecindario_sha256": huellas,
                                  "amortiguador_interno": amortiguadores,
                                  "regla": "perdidas.variantes[2].delta.particion_honesta (ratificada, Complemento 4.2)"}}
    return (info, r, en_1) if devolver_residuos else info


def _deltas_de_info(info: dict) -> dict:
    return {"mad": float(info["delta_huber"]), "friedman": float(info["delta_huber_friedman"])}


def calibrar_cuantiles(ctx: Contexto, prot: str, pred: dict, pliegue_de_fila: np.ndarray, excluidas: dict,
                       temporal: bool) -> dict:
    """Cuantiles de un protocolo consolidado (Enmienda 1, punto 9). Para cada motor con q05, q50 y q95: los reordena
    (q05 ≤ q50 ≤ q95, con el conteo de cruces) y calibra el intervalo del 90 % con conformal agrupado (CQR) con los
    puntajes fuera de pliegue de los demás grupos, la misma exclusión del protocolo y la clave macrozona × franja,
    con el respaldo honesto de la retransformación (``perdidas.variantes[3].calibracion``). Reemplaza en ``pred`` los
    cuantiles por los reordenados, agrega ``<motor>_cqr_q05`` y ``<motor>_cqr_q95`` y devuelve el registro."""
    cfg = ctx.cfg
    cal = next(v for v in cfg["perdidas"]["variantes"] if v["id"] == "pinball")["calibracion"]
    prim = cfg["retransformacion"]["primaria"]
    regla = prim["respaldo_honesto"]["macrozona_franja"]
    desde, hasta = (int(h) for h in prim["franja_diurna_horas_locales"])
    franja = ((ctx.hora_local >= desde) & (ctx.hora_local <= hasta)).astype("int64")
    congl = ctx.conglomerado_de_estacion()
    registro = {}
    for m in mv.MOTORES_PERDIDAS:
        nombres = [f"{m}_q05", f"{m}_q50", f"{m}_q95"]
        if not all(n in pred for n in nombres):
            continue
        q05, q50, q95, reg_orden = pv.reordenar_cuantiles(*(pred[n] for n in nombres))
        pred[nombres[0]], pred[nombres[1]], pred[nombres[2]] = q05, q50, q95
        lo, hi, _, _, reg_cqr, resumen = pv.cqr_fuera_de_pliegue(
            ctx.y, q05, q95, ctx.vec.js, ctx.macrozona, franja, pliegue_de_fila, excluidas, temporal, congl,
            nivel=float(cal["nivel"]), minimo_filas=int(regla["minimo_filas"]),
            minimo_conglomerados=int(regla["minimo_conglomerados_loso_d"]),
            minimo_grupos=int(regla["minimo_grupos_del_protocolo"]))
        pred[f"{m}_cqr_q05"], pred[f"{m}_cqr_q95"] = lo, hi
        registro[m] = {"reordenamiento": reg_orden, "cqr": {**resumen, "metodo": cal["metodo"],
                                                            "por_pliegue_y_clave": reg_cqr}}
    return registro


def deltas_guardados(ctx: Contexto, prot: str, pliegue: dict, huella_vec: dict, filas: np.ndarray) -> dict:
    """δ común (primario y de Friedman) del punto de control vigente de ``lightgbm_l2_original`` del pliegue."""
    k = int(pliegue["k"])
    p = leer_punto(ruta_punto(ctx, prot, k, "r0", TAREA_DELTA_HUBER))
    tarea = Tarea(TAREA_DELTA_HUBER, "lightgbm", "perdidas", variante="l2_original")
    if (p is None or "delta_huber_friedman" not in p[1].get("info", {})
            or p[1].get("firma") != firma_tarea(ctx, prot, pliegue, tarea, huella_vec, filas, hilos=p[1].get("hilos_firma"))):
        raise RuntimeError(f"{prot} k={k}: Huber necesita antes el δ común de {TAREA_DELTA_HUBER}, vigente "
                           f"(Enmienda 1, punto 9)")
    return _deltas_de_info(p[1]["info"])


def correr_pliegue(ctx: Contexto, prot: str, pliegue: dict, plan: dict, piloto: bool = False,
                   medidor=None) -> list[dict]:
    """Corre (o reanuda) todas las tareas de un pliegue. Con ``piloto`` no guarda nada y sólo mide tiempos.
    ``medidor`` (``piloto_v2.Medidor``) mide cada fase; por omisión no se mide nada. Escribir exige tener tomado
    el candado del pliegue (``nombre_candado_pliegue``; lo toma ``main``)."""
    med = medidor or SIN_MEDIR
    k = int(pliegue["k"])
    base = {"contaminante": ctx.pol, "protocolo": prot, "k": k}
    t0 = time.perf_counter()
    with med.fase(**base, tarea="vecindario", fase="vecindario") as m:
        rec = ctx.vec.para_pliegue(pliegue, prot)
        prueba = np.flatnonzero(rec.prueba)
        disp = np.flatnonzero(rec.entrenamiento)
        m.update(filas_disponibles=int(len(disp)), filas_prueba=int(len(prueba)),
                 n_excluidas=int(rec.registro.get("n_excluidas", 0)))
    huella_vec = rec.registro["sha256"]
    tiempos = [{"contaminante": ctx.pol, "protocolo": prot, "k": k, "tarea": "vecindario", "replica": 0,
                "filas_entrenamiento": int(len(disp)), "filas_prueba": int(len(prueba)),
                "segundos": round(time.perf_counter() - t0, 3)}]
    if not piloto:
        ruta_v = ruta_punto(ctx, prot, k, "vecindario", "vecindario")
        fv = firma_vecindario(ctx, prot, pliegue)
        previo = leer_punto(ruta_v)
        if previo is None or previo[1].get("firma") != fv or previo[1].get("huella_vecindario") != huella_vec:
            guardar_punto(ruta_v, {"filas_prueba": prueba, "obs_vec": rec.obs_vec[prueba], "peso_vec": rec.peso_vec[prueba],
                                   "dist_est_km": rec.dist_est_km[prueba]},
                          {"schema": SCHEMA_PUNTO, "firma": fv, "huella_vecindario": huella_vec, "registro": rec.registro,
                           "filas_entrenamiento_disponibles": int(len(disp)), "traza": ctx.traza_base()}, ctx.rutas)
    ordenes: dict[int, np.ndarray] = {}
    cache = {"clave": None, "X": None}
    Xte = None
    deltas: dict[str, float] = {}                 # regla («mad», «friedman») → δ común a LightGBM y XGBoost
    for tarea in _orden_tareas(plan["tareas"]):
        r = tarea.replica
        etiq = {**base, "tarea": tarea.id, "motor": tarea.motor, "familia": tarea.familia, "variante": tarea.variante,
                "tope": tarea.tope, "replica": r, "calidad": tarea.calidad, "filas_disponibles": int(len(disp)),
                "filas_prueba": int(len(prueba))}
        if tarea.motor == "lineales":
            filas = disp
        else:
            if r not in ordenes:
                with med.fase(**base, tarea=f"permutacion_r{r}", fase="permutacion", replica=r,
                              filas_disponibles=int(len(disp))):
                    ordenes[r] = mv.permutacion(disp, mv.semilla_permutacion(k, r))
            with med.fase(**etiq, fase="filas") as m:
                filas = mv.filas_tope(ordenes[r], ctx.tope(tarea.tope), ctx.mascara_calidad(tarea.calidad))
                m["filas_entrenamiento"] = int(len(filas))
        etiq["filas_entrenamiento"] = int(len(filas))
        extra = {}
        if es_huber(tarea):
            regla = pv.variante_de_etiqueta(tarea.variante).regla
            if regla not in deltas:
                deltas.update(deltas_guardados(ctx, prot, pliegue, huella_vec, filas))
            extra = {"delta_huber": deltas[regla], "regla_delta": regla}
        semillas = _semillas(ctx, tarea, k)                   # las mismas que entran en la firma (firma_tarea)
        firma = firma_tarea(ctx, prot, pliegue, tarea, huella_vec, filas, extra)
        ruta = ruta_punto(ctx, prot, k, f"r{r}", tarea.id)
        if not piloto and firma_vigente(ruta, firma):
            if tarea.id == TAREA_DELTA_HUBER:
                deltas.update(_deltas_de_info(leer_punto(ruta)[1]["info"]))
            continue
        t1 = time.perf_counter()
        if tarea.motor == "lineales":
            if ctx._lineales is None:                                # se arma una vez por contaminante
                with med.fase(**base, tarea="construccion_lineales", fase="construccion_lineales"):
                    ctx.lineales()
            with med.fase(**etiq, fase="ajuste_prediccion"):
                pred, info = ctx.lineales().ajustar_predecir(rec.obs_vec, rec.entrenamiento, rec.prueba)
            arreglos = {nombre: pred[nombre] for nombre in tarea.salidas}
            escalas = {nombre: "original" for nombre in tarea.salidas}
        else:
            clave = (r, str(tarea.tope), tarea.calidad)
            if cache["clave"] != clave:
                with med.fase(**etiq, fase="matriz_entrenamiento"):
                    cache["clave"], cache["X"] = clave, ctx.matriz(filas, rec)
            if Xte is None:
                with med.fase(**base, tarea="matriz_prueba", fase="matriz_prueba", filas_prueba=int(len(prueba))):
                    Xte = ctx.matriz(prueba, rec)
            modelo = _crear(ctx, tarea, k, extra.get("delta_huber"))
            opciones = {}
            if tarea.motor == "mlp":
                opciones["validacion"] = validacion_mlp(
                    ctx, prot, filas, pliegue.get("excluidas", []), semillas["validacion"],
                    contexto={"protocolo": prot, "k": k, "grupo": pliegue["grupo"], "replica": r}, medidor=med,
                    etiquetas=etiq)
            with med.fase(**etiq, fase="ajuste"):
                modelo.ajustar(cache["X"], ctx.y[filas], ctx.estaciones_de(filas), **opciones)
            opciones.clear()
            with med.fase(**etiq, fase="prediccion"):
                salida = modelo.predecir(Xte)
            info = dict(modelo.info)
            if tarea.id == TAREA_DELTA_HUBER:
                with med.fase(**etiq, fase="delta_huber"):
                    info_d = delta_huber_honesto(ctx, prot, pliegue, filas)
                deltas.update(_deltas_de_info(info_d))
                info.update(info_d)
            if es_huber(tarea):
                with med.fase(**etiq, fase="registro_huber"):
                    info["registro_huber"] = pv.registro_huber(ctx.y[filas], modelo.predecir(cache["X"]),
                                                               extra["delta_huber"])
                info["declaracion"] = DECLARACION_HUBER
            if modelo.escala == "original":
                salida = pv.a_escala_original(salida, pv.variante_de_etiqueta(tarea.variante))
            arreglos = {tarea.id: np.asarray(salida, dtype="float32")}
            escalas = {tarea.id: modelo.escala}
        segundos = round(time.perf_counter() - t1, 3)
        tiempos.append({"contaminante": ctx.pol, "protocolo": prot, "k": k, "tarea": tarea.id, "replica": r,
                        "filas_entrenamiento": int(len(filas)), "filas_prueba": int(len(prueba)), "segundos": segundos})
        if piloto:
            continue
        meta = {"schema": SCHEMA_PUNTO, "firma": firma, "hilos_firma": hilos_de_firma(ctx, tarea), "hilos": ctx.hilos,
                "tarea": asdict(tarea), "escalas": escalas, "firma_componentes": componentes_firma(ctx, tarea),
                "filas_prueba": {"n": int(len(prueba)), "sha256": _sha(prueba)},   # el arreglo vive en «vecindario»
                "filas_entrenamiento": {"n": int(len(filas)), "sha256": _sha(filas), "tope": ctx.tope(tarea.tope),
                                        "disponibles": int(len(disp))},
                "huella_vecindario": huella_vec, "semillas": semillas, "info": info, "segundos": segundos,
                "traza": {**ctx.traza_base(), "semillas": semillas}}
        if extra:
            meta["extra_firma"] = extra
        guardar_punto(ruta, arreglos, meta, ctx.rutas)
        log.info("%s %s k=%d %s r%d: %s filas, %.1f s", ctx.pol, prot, k, tarea.id, r, f"{len(filas):,}", segundos)
    if plan["interno"]:
        tiempos += correr_internos(ctx, prot, pliegue, disp, plan["interno"], piloto, medidor=med)
    return tiempos


def definicion_internos(ctx: Contexto, prot: str, pliegue: dict, disp: np.ndarray) -> dict:
    """Filas con tope del pliegue externo (réplica 0) y su reparto en pliegues internos agrupados, con el conjunto
    excluido de cada uno: el externo, las estaciones del pliegue interno y, en BLQ-75, las estaciones a ≤ 10 km de
    las del pliegue interno con filas en esas filas con tope (``amortiguador_interno``; Complemento, punto 5), que
    salen de las filas de entrenamiento interno y de su vecindario. Las filas de prueba de cada pliegue interno no
    cambian: el OOF interno cubre todas las filas."""
    k = int(pliegue["k"])
    filas = mv.filas_tope(mv.permutacion(disp, mv.semilla_permutacion(k, 0)), ctx.recetas["N_comun"])
    g_est = ctx.grupo_de_estacion(prot)
    est_filas = ctx.vec.js[filas]
    internos = mv.pliegues_internos(np.unique(g_est[est_filas]), k, ctx.recetas["apilado"]["pliegues_internos"])
    externas = [str(s) for s in pliegue.get("excluidas", [])]
    partes = []
    for j, grupos_j in enumerate(internos):
        est_j = np.flatnonzero(np.isin(g_est, grupos_j))
        nombres_j = sorted(str(ctx.vec.estaciones[i]) for i in est_j)
        amort, reg_amort = amortiguador_interno(ctx, prot, nombres_j, externas, filas=filas)
        en_j = np.isin(est_filas, est_j)
        fuera = _mascara_de_estaciones(ctx, filas, amort)
        tr_j, te_j = filas[~en_j & ~fuera], filas[en_j]
        excl = sorted(set(externas) | set(nombres_j) | set(amort))
        definicion = {"j": j, "grupos": grupos_j, "excluidas": excl, "filas_prueba_sha256": _sha(te_j)}
        if reg_amort["aplica"]:
            definicion["amortiguador_interno"] = {**reg_amort, "filas_fuera_del_entrenamiento": int(fuera.sum())}
        partes.append({"j": j, "tr": tr_j, "te": te_j, "excluidas": excl, "definicion": definicion})
    return {"filas": filas, "internos": internos, "partes": partes}


def correr_internos(ctx: Contexto, prot: str, pliegue: dict, disp: np.ndarray, bases, piloto: bool = False,
                    medidor=None) -> list[dict]:
    """Pliegues internos agrupados dentro del entrenamiento con tope del pliegue externo (réplica 0): sirven al
    apilado anidado y a la sensibilidad de la retransformación. Exclusión: la externa más el pliegue interno, en
    las filas y en el vecindario (recalculado para cada pliegue interno). La MLP valida con grupos completos del
    protocolo dentro del entrenamiento interno (Enmienda 1, punto 6)."""
    med = medidor or SIN_MEDIR
    k = int(pliegue["k"])
    base = {"contaminante": ctx.pol, "protocolo": prot, "k": k}
    with med.fase(**base, tarea="definicion_internos", fase="definicion_internos", filas_disponibles=int(len(disp))):
        D = definicion_internos(ctx, prot, pliegue, disp)
    filas, internos = D["filas"], D["internos"]
    tiempos = []
    for parte in D["partes"]:
        j, tr_j, te_j, excl, definicion = parte["j"], parte["tr"], parte["te"], parte["excluidas"], parte["definicion"]
        etiq_j = {**base, "interno": j, "filas_entrenamiento": int(len(tr_j)), "filas_prueba": int(len(te_j)),
                  "n_excluidas": int(len(excl))}
        t0 = time.perf_counter()
        with med.fase(**etiq_j, tarea="vecindario_interno", fase="vecindario"):
            rec_j = ctx.vec.recalcular(excl, contexto={"protocolo": prot, "k": k, "grupo": pliegue["grupo"],
                                                        "interno": j, "grupos_internos": definicion["grupos"]})
        X_cache = None
        for motor in bases:
            tarea = Tarea(f"interno_{motor}_j{j}", motor, "interno")
            semillas = _semillas(ctx, tarea, k)               # las mismas que entran en la firma (firma_tarea)
            firma = firma_tarea(ctx, prot, pliegue, tarea, rec_j.registro["sha256"], tr_j, {"interno": definicion,
                                                                                            "filas_externas": _sha(filas)})
            ruta = ruta_punto(ctx, prot, k, "interno", f"{motor}_j{j}")
            if not piloto and firma_vigente(ruta, firma):
                continue
            t1 = time.perf_counter()
            etiq = {**etiq_j, "tarea": tarea.id, "motor": motor, "familia": "interno", "variante": tarea.variante,
                    "tope": "N", "replica": 0, "calidad": "todo"}
            if X_cache is None:
                with med.fase(**etiq, fase="matrices_internas"):
                    X_cache = (ctx.matriz(tr_j, rec_j), ctx.matriz(te_j, rec_j))
            modelo = mv.crear_modelo(motor, ctx.recetas, pv.Variante(mv.VARIANTE_REFERENCIA), 0, replica=0, k=k)
            opciones = {}
            if motor == "mlp":
                opciones["validacion"] = validacion_mlp(
                    ctx, prot, tr_j, excl, semillas["validacion"],
                    contexto={"protocolo": prot, "k": k, "grupo": pliegue["grupo"], "interno": j}, medidor=med,
                    etiquetas=etiq)
            with med.fase(**etiq, fase="ajuste"):
                modelo.ajustar(X_cache[0], ctx.y[tr_j], ctx.estaciones_de(tr_j), **opciones)
            opciones.clear()
            with med.fase(**etiq, fase="prediccion"):
                z = modelo.predecir(X_cache[1]).astype("float32")
            segundos = round(time.perf_counter() - t1, 3)
            tiempos.append({"contaminante": ctx.pol, "protocolo": prot, "k": k, "tarea": f"interno_{motor}", "replica": 0,
                            "filas_entrenamiento": int(len(tr_j)), "filas_prueba": int(len(te_j)), "segundos": segundos})
            if piloto:
                continue
            guardar_punto(ruta, {"filas": te_j, "z": z},
                          {"schema": SCHEMA_PUNTO, "firma": firma, "hilos_firma": hilos_de_firma(ctx, tarea),
                           "hilos": ctx.hilos, "tarea": asdict(tarea), "interno": definicion,
                           "firma_componentes": componentes_firma(ctx, tarea),
                           "pliegues_internos": internos, "huella_vecindario": rec_j.registro["sha256"],
                           "info": modelo.info, "segundos": segundos, "semillas": semillas,
                           "traza": {**ctx.traza_base(), "semillas": semillas}}, ctx.rutas)
        tiempos.append({"contaminante": ctx.pol, "protocolo": prot, "k": k, "tarea": "interno_vecindario", "replica": 0,
                        "filas_entrenamiento": int(len(tr_j)), "filas_prueba": int(len(te_j)),
                        "segundos": round(time.perf_counter() - t0, 3)})
    return tiempos


# ---------------------------------------------------------------------------
# Consolidación de un protocolo
# ---------------------------------------------------------------------------
class Incompleto(RuntimeError):
    """Faltan puntos de control (o están vencidos) para consolidar un protocolo."""


def _leer_vigente(ctx, prot, pliegue, tarea, huella_vec, filas, extra=None):
    ruta = ruta_punto(ctx, prot, int(pliegue["k"]), f"r{tarea.replica}", tarea.id)
    p = leer_punto(ruta)
    if p is None:
        raise Incompleto(f"{ctx.pol} {prot} k={pliegue['k']}: falta {tarea.id} r{tarea.replica}")
    # Se valida con los hilos con que se ajustó (registrados en el punto): consolidar no exige repetir --hilos.
    if p[1].get("firma") != firma_tarea(ctx, prot, pliegue, tarea, huella_vec, filas, extra, hilos=p[1].get("hilos_firma")):
        raise Incompleto(f"{ctx.pol} {prot} k={pliegue['k']}: {tarea.id} r{tarea.replica} tiene otra firma (vencido)")
    return p


def reunir(ctx: Contexto, prot: str, plan: dict) -> dict:
    """Lee los puntos de control de todos los pliegues del protocolo y arma las salidas por fila del panel,
    comprobando las firmas (sin reajustar nada) y que cada fila sea de prueba en un solo pliegue."""
    n = ctx.n
    pliegue_de_fila = np.full(n, -1, dtype="int64")
    vecindario = {c: np.full(n, np.nan, dtype="float32") for c in ("obs_vec", "peso_vec", "dist_est_km")}
    salidas, escalas, infos, registros, internos = {}, {}, {}, [], {}
    for pliegue in ctx.pliegues(prot):
        k = int(pliegue["k"])
        pv_ = leer_punto(ruta_punto(ctx, prot, k, "vecindario", "vecindario"))
        if pv_ is None or pv_[1].get("firma") != firma_vecindario(ctx, prot, pliegue):
            raise Incompleto(f"{ctx.pol} {prot} k={k}: falta el vecindario del pliegue (o está vencido)")
        arr_v, meta_v = pv_
        huella_vec = meta_v["huella_vecindario"]
        entrenamiento, prueba_m, _ = ctx.vec.mascaras(pliegue, prot)
        prueba = np.flatnonzero(prueba_m)
        if not np.array_equal(arr_v["filas_prueba"], prueba):
            raise Incompleto(f"{ctx.pol} {prot} k={k}: las filas de prueba del vecindario no son las del pliegue")
        if (pliegue_de_fila[prueba] >= 0).any():
            raise ValueError(f"{prot}: hay filas de prueba en dos pliegues")
        pliegue_de_fila[prueba] = k
        for c in vecindario:
            vecindario[c][prueba] = arr_v[c]
        registros.append(meta_v["registro"])
        disp = np.flatnonzero(entrenamiento)
        ordenes = {}
        deltas = {}
        for tarea in _orden_tareas(plan["tareas"]):
            r = tarea.replica
            if tarea.motor == "lineales":
                filas = disp
            else:
                if r not in ordenes:
                    ordenes[r] = mv.permutacion(disp, mv.semilla_permutacion(k, r))
                filas = mv.filas_tope(ordenes[r], ctx.tope(tarea.tope), ctx.mascara_calidad(tarea.calidad))
            extra = None
            if es_huber(tarea):                                       # δ común del pliegue (Enmienda 1, punto 9)
                regla = pv.variante_de_etiqueta(tarea.variante).regla
                if regla not in deltas:
                    deltas.update(deltas_guardados(ctx, prot, pliegue, huella_vec, filas))
                extra = {"delta_huber": deltas[regla], "regla_delta": regla}
            arr, meta = _leer_vigente(ctx, prot, pliegue, tarea, huella_vec, filas, extra)
            if tarea.id == TAREA_DELTA_HUBER:
                deltas.update(_deltas_de_info(meta["info"]))
            fp = meta.get("filas_prueba", {})
            if fp.get("n") != len(prueba) or fp.get("sha256") != _sha(prueba):
                raise Incompleto(f"{prot} k={k} {tarea.id}: filas de prueba distintas de las del pliegue")
            for nombre_base, nombre in zip(tarea.salidas or (tarea.id,), tarea.nombres()):
                if nombre not in salidas:
                    salidas[nombre] = np.full(n, np.nan, dtype="float32")
                salidas[nombre][prueba] = arr[nombre_base]
                escalas[nombre] = meta["escalas"][nombre_base]
            infos.setdefault(tarea.id if r == 0 else f"{tarea.id}@r{r}", {})[str(k)] = {
                "info": meta["info"], "segundos": meta["segundos"], "filas_entrenamiento": meta["filas_entrenamiento"]}
        if plan["interno"]:
            internos[k] = reunir_internos(ctx, prot, pliegue, disp)
    if (pliegue_de_fila < 0).any():
        raise Incompleto(f"{ctx.pol} {prot}: {int((pliegue_de_fila < 0).sum())} filas sin pliegue de prueba")
    return {"pliegue_de_fila": pliegue_de_fila, "vecindario": vecindario, "salidas": salidas, "escalas": escalas,
            "infos": infos, "registros_vecindario": registros, "internos": internos}


def reunir_internos(ctx: Contexto, prot: str, pliegue: dict, disp: np.ndarray) -> dict:
    """OOF interno (log) de cada base sobre las filas con tope del pliegue externo, con sus firmas comprobadas."""
    k = int(pliegue["k"])
    D = definicion_internos(ctx, prot, pliegue, disp)
    filas = D["filas"]
    salida = {"filas": filas, "z": {}, "pliegues_internos": D["internos"]}
    for motor in ctx.recetas["apilado"]["bases"]:
        z = np.full(len(filas), np.nan)
        for parte in D["partes"]:
            j = parte["j"]
            p = leer_punto(ruta_punto(ctx, prot, k, "interno", f"{motor}_j{j}"))
            if p is None:
                raise Incompleto(f"{ctx.pol} {prot} k={k}: falta el pliegue interno {j} de {motor}")
            arr, meta = p
            tarea = Tarea(f"interno_{motor}_j{j}", motor, "interno")
            esperada = firma_tarea(ctx, prot, pliegue, tarea, meta["huella_vecindario"], parte["tr"],
                                   {"interno": parte["definicion"], "filas_externas": _sha(filas)},
                                   hilos=meta.get("hilos_firma"))
            if meta.get("firma") != esperada or not np.array_equal(arr["filas"], parte["te"]):
                raise Incompleto(f"{ctx.pol} {prot} k={k}: el pliegue interno {j} de {motor} está vencido")
            z[np.searchsorted(filas, parte["te"])] = arr["z"]
        if not np.isfinite(z).all():
            raise Incompleto(f"{ctx.pol} {prot} k={k}: OOF interno incompleto de {motor}")
        salida["z"][motor] = z
    return salida


SUFIJO_LOGNORMAL = rt.SUFIJO_FORMA[rt.LOGNORMAL]          # sensibilidad fija: «<motor>~lognormal[@rN]»
FORMA_ESCALA_ORIGINAL = "ninguna (escala original)"
NOMBRE_EVIDENCIA = "evidencia_decision.json"


def formas_retransformacion(cfg: dict) -> dict:
    """Formas de la configuración, que deben ser las de la Enmienda 1, punto 2: primaria ``smearing_duan``,
    sensibilidad fija ``lognormal_medio_sigma2`` y sensibilidad con OOF interno ``smearing_duan``."""
    f = rt.formas_de_config(cfg)
    if (f["primaria"], f["sensibilidad_fija"], f["sensibilidad"]) != (rt.SMEARING, rt.LOGNORMAL, rt.SMEARING):
        raise SystemExit(f"retransformación: la Enmienda 1 (punto 2) fija la primaria {rt.SMEARING}, la sensibilidad "
                         f"fija {rt.LOGNORMAL} y la interna {rt.SMEARING}; la configuración dice {f}")
    return f


def retransformar(ctx: Contexto, z: dict, pliegue_de_fila: np.ndarray, excluidas: dict, temporal: bool):
    """Primaria (``smearing_duan``) y sensibilidad fija (``lognormal_medio_sigma2``) de todo lo que está en log, en
    una sola pasada por motor: comparten clave macrozona × franja, exclusión del protocolo y respaldo honesto, con el
    conglomerado LOSO-D de cada estación (Enmienda 1, punto 2). La de ½·σ² se llama ``<motor>~lognormal`` (antes del
    sufijo de la réplica). Las alertas pasan a escala original sin corrección. Devuelve las predicciones, los ẑ de las
    de ½·σ² (los mismos del motor), la forma de cada predicción y el registro por pliegue × clave."""
    formas = formas_retransformacion(ctx.cfg)
    regla = rt.regla_de_config(ctx.cfg)
    congl = ctx.conglomerado_de_estacion()
    est = ctx.vec.js.astype("int64")
    nombres_est = [str(s) for s in ctx.vec.estaciones]
    pred, z_ln, forma_de, registro = {}, {}, {}, {}
    for nm, zz in z.items():
        if nm.startswith("alertas"):
            pred[nm] = mv.salida_alertas(zz)
            forma_de[nm] = "sin corrección (cuantil 0,80)"
            continue
        res = rt.fuera_de_pliegue(zz, ctx.y, est, ctx.macrozona, ctx.hora_local, pliegue_de_fila, excluidas, temporal,
                                  conglomerado_de_estacion=congl, formas=(formas["primaria"], formas["sensibilidad_fija"]),
                                  regla=regla, nombres_estacion=nombres_est)
        ln = dc.con_forma(nm, SUFIJO_LOGNORMAL)
        pred[nm], pred[ln] = res.pred[formas["primaria"]], res.pred[formas["sensibilidad_fija"]]
        z_ln[ln] = zz
        forma_de[nm], forma_de[ln] = formas["primaria"], formas["sensibilidad_fija"]
        registro[nm] = {**res.resumen(), "por_pliegue_y_clave": res.registro}
    return pred, z_ln, forma_de, registro


def sensibilidad_interna(ctx: Contexto, R: dict, z: dict, pliegue_de_fila: np.ndarray, excluidas: dict):
    """Sensibilidad con OOF interno (LRO y BLQ-75; Enmienda 1, punto 2): la tabla de cada pliegue externo sale de
    los residuos de sus pliegues internos (ningún modelo que aportó un residuo vio al pliegue), con la clave, el
    respaldo honesto y la exclusión de la primaria; el grupo de cada fila de entrenamiento es su pliegue externo.
    Usa ``smearing_duan`` (``<motor>~sens``) e informa también ½·σ² (``<motor>~sens~lognormal``)."""
    if not R["internos"]:
        return {}, {}, {}, {}
    formas = formas_retransformacion(ctx.cfg)
    regla = rt.regla_de_config(ctx.cfg)
    congl = ctx.conglomerado_de_estacion()
    est = ctx.vec.js.astype("int64")
    nombres_est = [str(s) for s in ctx.vec.estaciones]
    bases = ctx.recetas["apilado"]["bases"]
    pred, zs, forma_de, registro = {}, {}, {}, {}
    for nm in [*bases, "promedio"]:
        if nm not in z:
            continue
        ps = {f: np.full(ctx.n, np.nan, dtype="float32") for f in rt.FORMAS}
        regs = []
        for k, I in R["internos"].items():
            zi = (np.mean(np.column_stack([I["z"][b] for b in bases]), axis=1) if nm == "promedio" else I["z"][nm])
            f = I["filas"]
            tabla = rt.tabla_interna(zi, ctx.y[f], ctx.macrozona[f], ctx.hora_local[f], forma=formas["sensibilidad"],
                                     estacion=est[f], grupo=pliegue_de_fila[f], conglomerado_de_estacion=congl,
                                     regla=regla, retirado=int(k), excluidas=excluidas[int(k)])
            te = np.flatnonzero(pliegue_de_fila == int(k))
            res = rt.aplicar_tabla(z[nm][te], ctx.macrozona[te], ctx.hora_local[te], tabla, formas=rt.FORMAS,
                                   nombres_estacion=nombres_est)
            for fo in rt.FORMAS:
                ps[fo][te] = res.pred[fo]
            regs += [{"k": int(k), **x} for x in res.registro]
        s_nm = f"{nm}{rt.SUFIJO_INTERNA}"
        s_ln = f"{s_nm}{SUFIJO_LOGNORMAL}"
        pred[s_nm], pred[s_ln] = ps[formas["sensibilidad"]], ps[rt.LOGNORMAL]
        zs[s_nm] = zs[s_ln] = z[nm]
        forma_de[s_nm] = f"{formas['sensibilidad']} (OOF interno)"
        forma_de[s_ln] = f"{rt.LOGNORMAL} (OOF interno)"
        registro[nm] = regs
    return pred, zs, forma_de, registro


def bloque_inferencia(ctx: Contexto, prot: str, pliegue_de_fila: np.ndarray) -> np.ndarray:
    """Bloque de inferencia de cada fila (``inferencia_diferencias.bootstrap.unidad``; Enmienda 1, punto 5): el
    bloque de 75 km de la estación en LOSO-D, LBO-10 y BLQ-75 (su grupo de BLQ-75: el bloque de la rejilla que la
    contiene), la región en LRO y el cuatrienio en LPO (el grupo del pliegue de la fila)."""
    unidad = ctx.cfg["inferencia_diferencias"]["bootstrap"]["unidad"][prot]
    if unidad == "cuatrienio":
        grupo_k = {int(f["k"]): str(f["grupo"]) for f in ctx.pliegues(prot)}
        if (pliegue_de_fila < 0).any():
            raise ValueError(f"{prot}: hay filas sin pliegue de prueba")
        g = np.array([grupo_k.get(k, "") for k in range(max(grupo_k) + 1)], dtype=object)
        b = g[pliegue_de_fila].astype(str)
    elif unidad in ("bloque", "region"):
        por_est = ctx.grupo_de_estacion("BLQ-75" if unidad == "bloque" else "LRO")
        b = por_est[ctx.vec.js].astype(str)
    else:
        raise ValueError(f"unidad del bootstrap desconocida: {unidad!r}")
    if (b == "").any():
        raise ValueError(f"{prot}: hay filas sin bloque de inferencia ({unidad})")
    return b


def pesos_de_sensibilidad(ctx: Contexto) -> tuple[dict, dict]:
    """Peso de desagrupamiento (sensibilidad del punto 4), si están el insumo INE (sólo lectura) y el manifiesto de
    pliegues en disco con la huella del contexto; si no, no se calcula y queda registrado."""
    r = ctx.rutas
    ruta_ine = mt.ruta_poblacion_comunal(r.datos)
    man = leer_json(r.manifiesto_pliegues) if r.manifiesto_pliegues.exists() else None
    if man is None or man.get("huella_pliegues") != ctx.huella_pliegues or not ruta_ine.exists():
        return {}, {mt.DESAGRUPAMIENTO: "no calculado: falta el insumo INE o el manifiesto de pliegues del contexto"}
    comunas = mt.comunas_de_manifiesto(man, [str(s) for s in ctx.vec.estaciones])
    w, tabla = mt.peso_desagrupamiento(ctx.vec.js, ctx.anio, comunas, mt.leer_poblacion_comunal(ruta_ine),
                                       nombres_estacion=ctx.vec.estaciones)
    return ({mt.DESAGRUPAMIENTO: w[ctx.vec.js]},
            {mt.DESAGRUPAMIENTO: {"insumo": {**r.relativa(ruta_ine), "sha256": sha256_archivo(ruta_ine)},
                                  "cita": mt.CITA_POBLACION_COMUNAL, "por_estacion": tabla.to_dict(orient="records")}})


def columnas_de_familias(cfg: dict) -> list[str]:
    """Columnas de las familias de la sensibilidad fila a fila (ratificadas por el Complemento, punto 4.4), en orden."""
    return list(dict.fromkeys(c for cols in mt.familias_de_config(cfg).values() for c in cols))


def regimen_de_panel(panel: pd.DataFrame, cfg: dict) -> tuple | None:
    """Régimen de predictores fila a fila (sensibilidad descriptiva del punto 10) con las columnas de las familias
    **leídas del panel** en sólo lectura (no sólo las que son predictores del motor: GEOS-CF, TROPOMI o ACAG pueden
    estar en el panel sin entrar al modelo). Una columna que el panel no trae cuenta como no disponible y queda en el
    registro. Devuelve ``(código por fila, etiquetas, registro)``, o None si el panel no trae ninguna."""
    familias = mt.familias_de_config(cfg)
    columnas = {c: panel[c].to_numpy() for c in columnas_de_familias(cfg) if c in panel.columns}
    if not columnas:
        return None
    cod, etiquetas, info = mt.disponibilidad_fila_a_fila(columnas, familias)
    info = {**info, "fuente": "columnas del panel v1 (sólo lectura), sean o no predictores del motor",
            "columnas_leidas": sorted(columnas)}
    return cod.astype("int16" if len(etiquetas) < 2 ** 15 else "int64"), etiquetas, info


def estratos_fila_a_fila(ctx: Contexto) -> tuple[dict, dict]:
    """Régimen de predictores fila a fila del contexto (``regimen_de_panel``) como estrato de las métricas y, con la
    red ampliada (Enmienda 2, R10), el propietario de la estación de cada fila (descriptivo; no entra en el §9)."""
    if ctx.regimen_fila_a_fila is None:
        estratos, info = {}, {"estado": "el panel no trae ninguna columna de las familias del régimen fila a fila"}
    else:
        cod, etiquetas, info = ctx.regimen_fila_a_fila
        estratos = {"regimen_fila_a_fila": (np.asarray(cod, dtype="int64"), etiquetas)}
    if "red_de_monitores" in ctx.cfg:
        import panel_red2_v2
        cod, etiquetas, info_p = panel_red2_v2.estrato_propietario(ctx.rutas, ctx.pol, ctx.vec.estaciones, ctx.vec.js)
        estratos["propietario"] = (cod, etiquetas)
        info = {**info, "propietario": info_p}
    return estratos, info


def conjuntos_de(ctx: Contexto, comunes: np.ndarray, pliegue_de_fila: np.ndarray) -> tuple[dict, dict]:
    """Conjuntos de evaluación del punto 7 (E1, E2, E2-SINCA y E1′) sobre los pares comunes, con su registro."""
    if ctx.calidad is None:
        return {mt.E1: comunes}, {"estado": "sin bandera de calidad (calidad_v2): sólo E1"}
    c = mt.conjuntos_evaluacion(comunes, ctx.calidad, ctx.vec.js, mt.codigos_evaluacion_de_config(ctx.cfg))
    return c, mt.registro_conjuntos(c, ctx.vec.js, pliegue_de_fila, nombres_estacion=ctx.vec.estaciones)


def _niveles(ctx: Contexto, base: mt.Nivel, mascara: np.ndarray) -> dict:
    return mt.niveles(base, ctx.ts_utc[mascara], minimo_horas=int(ctx.cfg["metricas"]["niveles"]["diario"]["minimo_horas"]),
                      minimo_dias=_minimo(ctx.cfg, "mensual"), minimo_meses=_minimo(ctx.cfg, "anual"))


def evidencia_de_decision(ctx: Contexto, prot: str, pred: dict, z: dict, vecindario: dict, pliegue_de_fila: np.ndarray,
                          bloque_fila: np.ndarray) -> dict | None:
    """Evidencia de la decisión (Enmienda 1, punto 11) en LRO y BLQ-75: los pares de la decisión (intersección sólo
    entre LightGBM y los candidatos, con sus réplicas y las dos formas), su nivel diario civil en E1 y en E2 (los
    pares de la decisión que están en E2) y la evaluabilidad de E2, como sumas por bloque (``decision_v2``)."""
    regla = dc.regla_de_config(ctx.cfg)
    if prot not in regla.protocolos:
        return None
    nombres = dc.nombres_de_la_decision(list(pred), regla)
    if regla.referencia not in nombres:
        log.warning("%s %s: sin LightGBM no hay evidencia de la decisión", ctx.pol, prot)
        return None
    m, info = dc.pares_de_la_decision(ctx.y, pred, regla)
    est = ctx.vec.js.astype("int64")
    zz = {n: z.get(n) for n in nombres}

    def diario(mascara):
        base = mt.nivel_horario(ctx.y, {n: pred[n] for n in nombres}, zz, est, ctx.macrozona, ctx.anio,
                                vecindario["peso_vec"], vecindario["dist_est_km"], ctx.poblacion, pliegue_de_fila,
                                mascara, bloque=bloque_fila)
        return _niveles(ctx, base, mascara)[regla.nivel]

    nv1, nv2 = diario(m), None
    if ctx.calidad is None:
        evaluab = {"evaluable": False, "estado": mt.SIN_CONFIRMACION, "motivo": [dc.SIN_BANDERA]}
    else:
        e2 = mt.conjuntos_evaluacion(m, ctx.calidad, est, mt.codigos_evaluacion_de_config(ctx.cfg))[mt.E2]
        if e2.any():
            nv2 = diario(e2)
            evc = mt.evaluabilidad_de_config(ctx.cfg)
            evaluab = mt.evaluabilidad_e2(nv1, nv2, evc["minimo_fraccion"], evc["minimo_grupos"])
        else:
            evaluab = {"evaluable": False, "estado": mt.SIN_CONFIRMACION, "motivo": ["ningún par de la decisión está en E2"]}
    return dc.evidencia_protocolo(prot, nv1, nv2, pares=info, evaluabilidad=evaluab, contaminante=ctx.pol, regla=regla,
                                  posicion_protocolo=PROTOCOLOS.index(prot))


def consolidar(ctx: Contexto, prot: str, plan: dict, escribir: bool = True, replicas_bootstrap: int = bs.REPLICAS,
               forzado: dict | None = None) -> dict:
    """Consolidación de un protocolo completo (Enmienda 1, puntos 2–5, 7, 10 y 11): retransformación primaria y
    sensibilidades, pares comunes, métricas por conjunto de evaluación (con los pesos fijos, el desagrupamiento, los
    regímenes y los bloques de inferencia), cuantiles, alertas, bootstrap con el ruido de la diferencia, la segunda
    prueba y la influencia, Δ̄ sin cada bloque y, en LRO y BLQ-75, la evidencia de la decisión. ``forzado`` registra
    en ``consolidado.json`` lo que la consola aceptó con ``--forzar`` o ``--forzar-recorte`` (B o recorte distintos
    de los del contrato y del plan)."""
    t0 = time.perf_counter()
    R = reunir(ctx, prot, plan)
    pliegue_de_fila, salidas, escalas = R["pliegue_de_fila"], R["salidas"], R["escalas"]
    pl = {int(f["k"]): f for f in ctx.pliegues(prot)}
    excluidas = {k: ctx.vec.indices(f.get("excluidas", [])) for k, f in pl.items()}
    temporal = prot == "LPO"
    eje_a = [t.id for t in plan["tareas"] if t.familia == "eje_A" and t.replica == 0]
    # --- Derivados en log: promedio simple (por réplica) y apilado anidado ---
    z = {nm: s for nm, s in salidas.items() if escalas[nm] == "log"}
    replicas = sorted({t.replica for t in plan["tareas"] if t.familia == "eje_A"})
    if set(mv.MOTORES_EJE_A) <= set(eje_a):
        for r in replicas:
            nombres = [bs.nombre_replica(m, r) for m in mv.MOTORES_EJE_A]
            if all(nm in z for nm in nombres):
                z[bs.nombre_replica("promedio", r)] = np.mean(np.column_stack([z[nm].astype("float64") for nm in nombres]),
                                                              axis=1).astype("float32")
    pesos_apilado = {}
    if R["internos"]:
        bases = ctx.recetas["apilado"]["bases"]
        zap = np.full(ctx.n, np.nan, dtype="float32")
        for k, I in R["internos"].items():
            Z = np.column_stack([I["z"][b] for b in bases])
            w = mv.pesos_simplex(Z, np.log1p(np.clip(ctx.y[I["filas"]], 0, None)))
            pesos_apilado[str(k)] = dict(zip(bases, (float(x) for x in w)))
            te = np.flatnonzero(pliegue_de_fila == k)
            zap[te] = (np.column_stack([z[b][te].astype("float64") for b in bases]) @ w).astype("float32")
        z["apilado"] = zap
    # --- Retransformación: primaria, sensibilidad fija (½·σ²) y, en LRO y BLQ-75, OOF interno (punto 2) ---
    pred, z_ln, forma_de, registro_rt = retransformar(ctx, z, pliegue_de_fila, excluidas, temporal)
    for nm, s in salidas.items():
        if escalas[nm] == "original":
            pred[nm] = s
            forma_de[nm] = FORMA_ESCALA_ORIGINAL
    registro_cuantiles = calibrar_cuantiles(ctx, prot, pred, pliegue_de_fila, excluidas, temporal)
    p_int, z_int, f_int, registro_interno = sensibilidad_interna(ctx, R, z, pliegue_de_fila, excluidas)
    pred.update(p_int)
    forma_de.update(f_int)
    z = {**z, **z_ln, **z_int}
    # --- Pares comunes (§4) y atributos de la evaluación ---
    comunes, info_pares = mt.pares_comunes(ctx.y, pred)
    puntuales = [nm for nm in pred if not nm.startswith("alertas") and not nm.endswith(("_q05", "_q95"))]
    vecindario = R["vecindario"]
    cortes = {"peso_vec": mt.cortes_cuartiles(vecindario["peso_vec"][comunes]),
              "dist_est_km": mt.cortes_cuartiles(vecindario["dist_est_km"][comunes])}
    est = ctx.vec.js.astype("int64")
    bloque_fila = bloque_inferencia(ctx, prot, pliegue_de_fila)
    regimenes = mt.regimenes_de_config(ctx.cfg)
    periodos = mt.periodos_lpo_de_config(ctx.cfg) if temporal else None
    pesos_extra, registro_pesos = pesos_de_sensibilidad(ctx)
    estratos, registro_estratos = estratos_fila_a_fila(ctx)
    conjuntos, registro_conjuntos = conjuntos_de(ctx, comunes, pliegue_de_fila)
    etiqueta_est = lambda c: str(ctx.vec.estaciones[c])  # noqa: E731
    z_punt = {nm: (z[nm] if nm in z else None) for nm in puntuales}
    # --- Métricas y bootstrap por conjunto de evaluación (punto 7) ---
    tablas, boots, sin_cada, resumen_niveles, diarios = [], [], [], {}, {}
    for conjunto, mascara in conjuntos.items():
        if not mascara.any():
            resumen_niveles[conjunto] = {}
            continue
        base = mt.nivel_horario(ctx.y, {nm: pred[nm] for nm in puntuales}, z_punt, est, ctx.macrozona, ctx.anio,
                                vecindario["peso_vec"], vecindario["dist_est_km"], ctx.poblacion, pliegue_de_fila, mascara,
                                bloque=bloque_fila, pesos_extra=pesos_extra, estratos=estratos)
        nvs = _niveles(ctx, base, mascara)
        del base
        resumen_niveles[conjunto] = mt.resumen_niveles(nvs)
        t = mt.tabla_metricas(nvs, cortes, etiqueta_estacion=etiqueta_est, regimen=regimenes, periodos_lpo=periodos,
                              retransformacion=forma_de)
        t.insert(0, "conjunto", conjunto)
        tablas.append(t)
        boots.append(bootstrap_protocolo(ctx, prot, nvs, eje_a, replicas_bootstrap, conjunto, formas=forma_de))
        if conjunto == mt.E1:
            sin_cada.append(tabla_sin_cada_bloque(ctx, prot, nvs, eje_a, conjunto))
        diarios[conjunto] = nvs["diario_civil"]
        del nvs
    if mt.E2 in diarios:
        evc = mt.evaluabilidad_de_config(ctx.cfg)
        evaluabilidad = mt.evaluabilidad_e2(diarios[mt.E1], diarios[mt.E2], evc["minimo_fraccion"], evc["minimo_grupos"])
    else:
        evaluabilidad = {"evaluable": False, "estado": mt.SIN_CONFIRMACION,
                         "motivo": ["sin bandera de calidad o sin pares E2"]}
    del diarios
    metricas = pd.concat(tablas, ignore_index=True)
    metricas.insert(0, "protocolo", prot)
    metricas.insert(0, "contaminante", ctx.pol)
    # --- Cuantiles y alertas ---
    cuantiles = []
    for m in mv.MOTORES_PERDIDAS:
        if all(f"{m}_{q}" in pred for q in ("q05", "q50", "q95")):
            # cuantiles reordenados (calibrar_cuantiles) y, aparte, el intervalo calibrado con CQR
            for etiqueta_c, inferior, superior in ((m, f"{m}_q05", f"{m}_q95"), (f"{m}_cqr", f"{m}_cqr_q05", f"{m}_cqr_q95")):
                if inferior not in pred:
                    continue
                c = mt.metricas_cuantiles(ctx.y[comunes], pred[inferior][comunes], pred[f"{m}_q50"][comunes],
                                          pred[superior][comunes], ctx.macrozona[comunes], ctx.hora_local[comunes])
                c.insert(0, "motor", etiqueta_c)
                cuantiles.append(c)
    cuantiles = pd.concat(cuantiles, ignore_index=True) if cuantiles else pd.DataFrame()
    alertas = pd.DataFrame()
    if "alertas_q80" in pred:
        alertas = mt.metricas_alerta(ctx.y[comunes], pred["alertas_q80"][comunes], ctx.macrozona[comunes],
                                     ctx.hora_local[comunes])
    for tabla in (cuantiles, alertas):
        if len(tabla):
            tabla.insert(0, "protocolo", prot)
            tabla.insert(0, "contaminante", ctx.pol)
    boot = pd.concat([b for b in boots if len(b)], ignore_index=True) if any(len(b) for b in boots) else pd.DataFrame()
    sin_cada = pd.concat([s for s in sin_cada if len(s)], ignore_index=True) if any(len(s) for s in sin_cada) else pd.DataFrame()
    # --- Evidencia de la decisión (LRO y BLQ-75) ---
    evidencia = evidencia_de_decision(ctx, prot, pred, z, vecindario, pliegue_de_fila, bloque_fila)
    # --- Salidas ---
    regla_d = dc.regla_de_config(ctx.cfg)
    resultado = {"metricas": metricas, "cuantiles": cuantiles, "alertas": alertas, "bootstrap": boot,
                 "sin_cada_bloque": sin_cada, "evidencia_decision": evidencia, "pred": pred, "z": z,
                 "comunes": comunes, "pliegue_de_fila": pliegue_de_fila, "bloque": bloque_fila}
    p = PROTOCOLOS.index(prot)
    consolidado = {
        "schema": SCHEMA_CONSOLIDADO, "contaminante": ctx.pol, "protocolo": prot, "etiqueta": ctx.etiqueta,
        "pares": info_pares, "niveles": resumen_niveles, "cortes_soporte": {k: list(map(float, v)) for k, v in cortes.items()},
        "conjuntos": {"registro": registro_conjuntos, "evaluabilidad_E2": evaluabilidad},
        "ponderacion": {"decision": {"nombre": mt.PESO_FIJO, "regla": "pob_dens fija por estación: la mediana de sus años"},
                        "sensibilidades": registro_pesos},
        "regimenes": {"por_anio": [dict(x) for x in regimenes], "fila_a_fila": registro_estratos,
                      "periodos_lpo": [list(x) for x in periodos] if periodos else None},
        "bloques_de_inferencia": {"unidad": ctx.cfg["inferencia_diferencias"]["bootstrap"]["unidad"][prot],
                                  "bloques": sorted(set(bloque_fila[comunes].tolist())),
                                  "bloque_mas_influyente": regla_d.bloque_mas_influyente.get(prot),
                                  "descriptivo": prot == "LPO"},
        "retransformacion": {"formas": formas_retransformacion(ctx.cfg), "regla": rt.regla_de_config(ctx.cfg).como_dict(),
                             "forma_por_prediccion": forma_de, "primaria_y_fija": registro_rt,
                             "sensibilidad_oof_interno": registro_interno},
        "apilado": {"pesos_por_pliegue": pesos_apilado, "bases": ctx.recetas["apilado"]["bases"] if pesos_apilado else [],
                    "ruido": "el máximo del ruido de la diferencia de sus bases (Enmienda 1, punto 3)"},
        "cuantiles": registro_cuantiles,
        "decision": (None if evidencia is None else
                     {"evidencia": NOMBRE_EVIDENCIA, "pares": evidencia["pares"], "G": evidencia["G"],
                      "G_efectivo": evidencia["G_efectivo"], "evaluabilidad_E2": evidencia["evaluabilidad_E2"],
                      "candidatos_ausentes": evidencia["candidatos_ausentes"]}),
        "plan": [asdict(t) for t in plan["tareas"]], "interno": plan["interno"], "recorte": plan["recorte"],
        "recortes_aplicados": plan.get("recortes_aplicados", []),
        "replicas_bootstrap": {"B": int(replicas_bootstrap), "del_contrato": int(regla_d.replicas_bootstrap)},
        "forzado": forzado or None,
        "ajustes": R["infos"], "vecindario": R["registros_vecindario"],
        "segundos_consolidacion": round(time.perf_counter() - t0, 2),
        "traza": {**ctx.traza_base(), "semillas": {"bootstrap": bs.semilla_bootstrap(p),
                                                     "bootstrap_salvaje": bs.semilla_salvaje(p),
                                                     "permutacion": "[42, k] y [42, k, r]"}},
    }
    resultado["consolidado"] = consolidado
    if escribir:
        escribir_consolidado(ctx, prot, resultado, vecindario)
    return resultado


def _minimo(cfg: dict, nivel: str) -> int:
    n = cfg["metricas"]["niveles"][nivel]
    clave = "minimo_dias" if nivel == "mensual" else "minimo_meses"
    return int(valor_vigente(n[clave], f"metricas.niveles.{nivel}.{clave}"))


def pares_bootstrap(nombres, eje_a) -> list[tuple[str, str]]:
    """Pares de la tabla descriptiva: cada motor puntual contra LightGBM con la misma corrección (las primarias contra
    ``lightgbm`` y las de ½·σ² contra ``lightgbm~lognormal``: «su par en el bootstrap»), todos los pares del eje A
    con el promedio y el apilado, cada sensibilidad con OOF interno contra su motor con la misma corrección y cada
    motor del eje A, el promedio y el apilado con ½·σ² contra su primaria. Las réplicas no forman pares: entran como
    Δ_r de cada par (punto 3)."""
    bases = [nm for nm in nombres if bs.separar_replica(nm)[1] == 0]
    presentes = set(bases)
    ln, sens = SUFIJO_LOGNORMAL, rt.SUFIJO_INTERNA
    primarias = [nm for nm in bases if "~" not in nm]
    pares = []
    if "lightgbm" in presentes:
        pares += [(nm, "lightgbm") for nm in primarias if nm != "lightgbm"]
    ref_ln = dc.con_forma("lightgbm", ln)
    if ref_ln in presentes:
        pares += [(nm, ref_ln) for nm in bases if nm.endswith(ln) and sens not in nm and nm != ref_ln]
    grupo = [nm for nm in [*eje_a, "promedio", "apilado"] if nm in presentes and nm != "lightgbm"]
    pares += [(a, b) for i, a in enumerate(grupo) for b in grupo[i + 1:]]
    pares += [(nm, nm.replace(sens, "")) for nm in bases if sens in nm and nm.replace(sens, "") in presentes]
    principales = [*eje_a, "promedio", "apilado"]
    pares += [(dc.con_forma(nm, ln), nm) for nm in principales if nm in presentes and dc.con_forma(nm, ln) in presentes]
    return list(dict.fromkeys(pares))


def motores_de_los_pares(pares, disponibles, bases_sin_replicas: dict | None = None) -> list[str]:
    """Predicciones que necesita el bootstrap de ``pares``: las de cada motor, con sus réplicas, y las bases de los
    motores sin réplicas (para su ruido)."""
    usados = {x for par in pares for x in par}
    for b, lista in (bases_sin_replicas or {}).items():
        if b in usados:
            usados |= set(lista)
    return [nm for nm in disponibles if bs.separar_replica(nm)[0] in usados]


def _bases_sin_replicas(ctx: Contexto) -> dict:
    bases = list(ctx.recetas["apilado"]["bases"])
    return {"apilado": bases, dc.con_forma("apilado", SUFIJO_LOGNORMAL): [dc.con_forma(b, SUFIJO_LOGNORMAL) for b in bases]}


def bootstrap_protocolo(ctx: Contexto, prot: str, nvs: dict, eje_a, replicas: int, conjunto: str = mt.E1,
                        formas: dict | None = None) -> pd.DataFrame:
    """Tabla descriptiva de diferencias (§8; Enmienda 1, puntos 3 y 5; Complemento, puntos 1, 2 y 6) de un conjunto
    de evaluación: en cada nivel, sin ponderar y con los pesos fijos, el bootstrap percentil por bloques de inferencia
    (``replicas``, 1.999 por omisión) con Δ_r, Δ̄ y el ruido de la diferencia (3 réplicas), la segunda prueba (decide
    el cambio de signo del bootstrap salvaje; el jackknife CV3 sólo informa), la regla de superioridad y, en LRO y
    BLQ-75, su robustez sin el bloque más influyente. Semillas ``[42, 2000, p]`` y ``[42, 3000, p]``; LPO es
    descriptivo. ``formas`` (predicción → retransformación) agrega la corrección de cada motor del par."""
    p = PROTOCOLOS.index(prot)
    bloque = dc.regla_de_config(ctx.cfg).bloque_mas_influyente.get(prot)
    bases_sin = _bases_sin_replicas(ctx)
    filas = []
    for nombre_nivel, nv in nvs.items():
        pares = pares_bootstrap(list(nv.pred), eje_a)
        if not pares or len(nv.obs) == 0:
            continue
        usados = motores_de_los_pares(pares, list(nv.pred), bases_sin)
        for pond in ("ninguna", mt.PESO_FIJO):
            S = dc.sumas_de_nivel(nv, usados, pond, "original")
            t = bs.comparar(S, pares, replicas, bs.semilla_bootstrap(p), bases_sin_replicas=bases_sin,
                            bloque_influyente=bloque, semilla_salvaje=bs.semilla_salvaje(p), descriptivo=prot == "LPO")
            if formas is not None:
                j = list(t.columns).index("motor_b") + 1
                t.insert(j, "retransformacion_b", t["motor_b"].map(lambda x: formas.get(bs.separar_replica(x)[0], "")))
                t.insert(j, "retransformacion_a", t["motor_a"].map(lambda x: formas.get(bs.separar_replica(x)[0], "")))
            t.insert(0, "ponderacion", pond)
            t.insert(0, "nivel", nombre_nivel)
            t.insert(0, "conjunto", conjunto)
            filas.append(t)
    out = pd.concat(filas, ignore_index=True) if filas else pd.DataFrame()
    if len(out):
        out.insert(0, "protocolo", prot)
        out.insert(0, "contaminante", ctx.pol)
    return out


def tabla_sin_cada_bloque(ctx: Contexto, prot: str, nvs: dict, eje_a, conjunto: str = mt.E1,
                          nivel: str = "diario_civil") -> pd.DataFrame:
    """Δ̄ de ΔR² sin cada bloque de inferencia (Enmienda 1, punto 5, «Informes») de cada motor del eje A, el promedio
    y el apilado frente a LightGBM, en el nivel diario civil, sin ponderar y con los pesos fijos."""
    nv = nvs.get(nivel)
    if nv is None or "lightgbm" not in nv.pred or len(nv.obs) == 0:
        return pd.DataFrame()
    motores = [m for m in [*eje_a, "promedio", "apilado"] if m in nv.pred and m != "lightgbm"]
    pares = [(m, "lightgbm") for m in motores]
    bases_sin = _bases_sin_replicas(ctx)
    usados = motores_de_los_pares(pares, list(nv.pred), bases_sin)
    filas = []
    for pond in ("ninguna", mt.PESO_FIJO):
        S = dc.sumas_de_nivel(nv, usados, pond, "original")
        for a, b in pares:
            t = bs.delta_sin_cada_bloque(S, a, b, "delta_r2")
            for col, v in (("motor_b", b), ("motor_a", a), ("ponderacion", pond), ("nivel", nivel),
                           ("conjunto", conjunto), ("protocolo", prot), ("contaminante", ctx.pol)):
                t.insert(0, col, v)
            t["delta"] = bs.delta_medio(S, a, b, "delta_r2")
            filas.append(t)
    return pd.concat(filas, ignore_index=True) if filas else pd.DataFrame()


CONJUNTOS_RESUMEN = (mt.E1, mt.E2)
RESUMEN_METRICAS = ("E1 y E2; sin la desagregación por estación ni la sensibilidad fila a fila del régimen; sin réplicas; "
                    "las variantes ½·σ² sólo del eje A, el promedio y el apilado (lo demás, en metricas.parquet)")
RESUMEN_BOOTSTRAP = ("E1 y E2; el eje A, el promedio y el apilado frente a LightGBM con la misma corrección y cada uno con "
                     "½·σ² frente a su primaria (lo demás, en bootstrap.parquet)")


def _principales(ctx: Contexto) -> set:
    return {*mv.MOTORES_EJE_A, "promedio", "apilado"}


def _base_sin_forma(nombre: str) -> str:
    return bs.separar_replica(nombre)[0].replace(SUFIJO_LOGNORMAL, "")


def resumen_metricas(m: pd.DataFrame, principales: set) -> pd.DataFrame:
    """Tabla pequeña de métricas para ``output_files`` (``RESUMEN_METRICAS``)."""
    if not len(m):
        return m
    ln = m["motor"].str.contains(SUFIJO_LOGNORMAL, regex=False) & ~m["motor"].str.contains(rt.SUFIJO_INTERNA, regex=False)
    ln_ok = m["motor"].map(_base_sin_forma).isin(principales)
    return m[m["conjunto"].isin(CONJUNTOS_RESUMEN) & ~m["desagregacion"].isin(("estacion", "regimen_fila_a_fila"))
             & ~m["motor"].str.contains("@r", regex=False) & (~ln | ln_ok)]


def resumen_bootstrap(b: pd.DataFrame, principales: set) -> pd.DataFrame:
    """Tabla pequeña del bootstrap para ``output_files`` (``RESUMEN_BOOTSTRAP``)."""
    if not len(b):
        return b
    a = b["motor_a"].map(_base_sin_forma)
    frente_a_lgbm = b["motor_b"].isin(("lightgbm", dc.con_forma("lightgbm", SUFIJO_LOGNORMAL)))
    correccion = b["motor_a"].str.endswith(SUFIJO_LOGNORMAL) & (b["motor_b"] == a)
    return b[b["conjunto"].isin(CONJUNTOS_RESUMEN) & a.isin(principales)
             & ~b["motor_a"].str.contains(rt.SUFIJO_INTERNA, regex=False) & (frente_a_lgbm | correccion)]


def escribir_consolidado(ctx: Contexto, prot: str, res: dict, vecindario: dict) -> dict:
    """OOF, métricas, bootstrap y la evidencia de la decisión en la raíz v2; tablas resumen en
    ``output_files/modelo_1km_v2`` con su JSON lateral."""
    r = ctx.rutas
    carpeta = ctx.raiz() / prot
    oof = pd.DataFrame({"fila": np.arange(ctx.n, dtype="int64"),
                        "estacion": pd.Categorical.from_codes(ctx.vec.js, categories=[str(s) for s in ctx.vec.estaciones]),
                        "ts_utc": ctx.ts_utc, "obs": ctx.y.astype("float32"), "pliegue": res["pliegue_de_fila"],
                        "bloque_inferencia": pd.Categorical(res["bloque"]),
                        "par_comun": res["comunes"], "peso_vec_pliegue": vecindario["peso_vec"],
                        "dist_est_km_pliegue": vecindario["dist_est_km"], "obs_vec_pliegue": vecindario["obs_vec"]})
    # El ajuste de la retransformación y su nivel de respaldo no se repiten fila a fila: están por pliegue × clave en
    # el registro de consolidado.json, y para cada predicción en log adj = log1p(pred) − z. Las variantes «~» (½·σ²
    # y OOF interno) comparten el ẑ de su motor, que se guarda una vez.
    columnas = {}
    for nm in sorted(res["pred"]):
        columnas[f"pred__{nm}"] = np.asarray(res["pred"][nm], dtype="float32")
        if nm in res["z"] and "~" not in nm:
            columnas[f"z__{nm}"] = np.asarray(res["z"][nm], dtype="float32")
    oof = pd.concat([oof, pd.DataFrame(columnas)], axis=1)
    shas = {}
    nombre = f"comparacion_{ctx.etiqueta}_{ctx.pol}_{prot}"
    with candado_escritura(f"{CARPETA}.{ctx.etiqueta}.{ctx.pol}.{prot}.consolidar", rutas=r):
        shas["oof.parquet"] = publicar_parquet(oof, carpeta / "oof.parquet", r)
        shas["metricas.parquet"] = publicar_parquet(res["metricas"], carpeta / "metricas.parquet", r)
        if len(res["bootstrap"]):
            shas["bootstrap.parquet"] = publicar_parquet(res["bootstrap"], carpeta / "bootstrap.parquet", r)
        if res.get("evidencia_decision") is not None:
            shas[NOMBRE_EVIDENCIA] = publicar_json(res["evidencia_decision"], carpeta / NOMBRE_EVIDENCIA, r)
        res["consolidado"]["archivos"] = shas
        publicar_json(res["consolidado"], carpeta / "consolidado.json", r)
        principales = _principales(ctx)
        tablas_csv = {f"{nombre}_metricas.csv": resumen_metricas(res["metricas"], principales),
                      f"{nombre}_cuantiles.csv": res["cuantiles"], f"{nombre}_alertas.csv": res["alertas"],
                      f"{nombre}_bootstrap.csv": resumen_bootstrap(res["bootstrap"], principales),
                      f"{nombre}_sin_cada_bloque.csv": res["sin_cada_bloque"]}
        m = res["metricas"]
        con_replica = {x.split("@r")[0] for x in m["motor"].unique() if "@r" in x}
        replicas = m[m["motor"].map(lambda x: x.split("@r")[0] in con_replica) & (m["desagregacion"] == "total")
                     & m["conjunto"].isin(CONJUNTOS_RESUMEN)]
        if len(replicas):
            tablas_csv[f"{nombre}_semillas.csv"] = replicas
        shas_csv = {}
        for nombre_csv, df in tablas_csv.items():
            datos = df.to_csv(index=False, lineterminator="\n", float_format="%.10g").encode("utf-8")
            destino = r.salidas_v2 / nombre_csv
            shas_csv[nombre_csv] = hashlib.sha256(datos).hexdigest()
            if not (destino.exists() and destino.read_bytes() == datos):
                publicar_bytes(datos, destino, r)
        publicar_json({"schema": SCHEMA_TABLAS, "contaminante": ctx.pol, "protocolo": prot, "etiqueta": ctx.etiqueta,
                       "descripcion": ("Resumen de la comparación v2; la fuente completa (OOF, métricas por estación, "
                                       "bootstrap, evidencia de la decisión y registro) está en la raíz v2, "
                                       "comparacion/<etiqueta>/<pol>/<protocolo>/."),
                       "resumen": {"metricas": RESUMEN_METRICAS, "bootstrap": RESUMEN_BOOTSTRAP},
                       "tablas": shas_csv, "fuente": {k: {**r.relativa(carpeta / k), "sha256": v} for k, v in shas.items()},
                       "pares_comunes": res["consolidado"]["pares"]["pares_comunes"],
                       "retransformacion": {"primaria": rt.SMEARING, "sensibilidad_fija": rt.LOGNORMAL,
                                            "nombres": f"<motor> ({rt.SMEARING}), <motor>{SUFIJO_LOGNORMAL} ({rt.LOGNORMAL}), "
                                                       f"<motor>{rt.SUFIJO_INTERNA} (OOF interno)"},
                       "traza": res["consolidado"]["traza"]}, r.salidas_v2 / f"{nombre}.json", r)
    return shas


# ---------------------------------------------------------------------------
# Decisión del producto v2 (§9; Enmienda 1, punto 11)
# ---------------------------------------------------------------------------
def ruta_evidencia(r: RutasV2, etiqueta: str, pol: str, prot: str) -> Path:
    return r.raiz_v2 / CARPETA / etiqueta / pol / prot / NOMBRE_EVIDENCIA


def _verificar_regla_factibilidad(d: dict, nombre: str, cfg: dict | None) -> None:
    """Si el resumen declara la regla con que se midió, debe ser la del Complemento (punto 3): un resumen que declara
    otro umbral de días (la regla anterior: 7 días por contaminante) u otro factor frente a LightGBM no sirve para
    decidir. Lo que el resumen no declara no se puede comprobar y no lo detiene."""
    regla = d.get("regla") if isinstance(d.get("regla"), dict) else None
    if regla is None or cfg is None:
        return
    f = cfg["decision"]["factibilidad"]
    declarado = {"umbral_dias_de_maquina": regla.get("umbral_dias_de_maquina"),
                 "factor_maximo_frente_a_lightgbm": regla.get("factor_maximo_frente_a_lightgbm")}
    esperado = {"umbral_dias_de_maquina": float(f["umbral_dias_de_maquina"]),
                "factor_maximo_frente_a_lightgbm": float(f["factor_maximo_frente_a_lightgbm"])}
    distintos = {k: v for k, v in declarado.items() if v is not None and float(v) != esperado[k]}
    if distintos:
        raise SystemExit(f"{nombre}: la factibilidad se midió con otra regla ({declarado}); la vigente es la del "
                         f"Complemento de la Enmienda 1, punto 3 ({esperado}, predictores compilados, los dos "
                         f"contaminantes): vuelve a medirla con factibilidad_v2 antes de cualquier ajuste comparativo")


def factibilidad_de_archivo(ruta, pol: str) -> tuple[dict, dict]:
    """Tiempos de la factibilidad de **un** contaminante desde un JSON: el resumen de ``factibilidad_v2``
    (``factibilidad_produccion.json``: ``contaminantes[pol].produccion[c].segundos_por_dia``, con su marca) o un
    mapa simple ``{pol: {motor: segundos por día}}``. Devuelve el mapa por motor y la fuente (nombre y sha256, sin
    rutas absolutas). La decisión suma los dos contaminantes: lee ``factibilidad_de_los_dos``."""
    p = Path(ruta)
    d = json.loads(p.read_text(encoding="utf-8"))
    por_pol = (d.get("contaminantes") or d).get(pol)
    if por_pol is None:
        raise SystemExit(f"{p.name}: no tiene la factibilidad de {pol}")
    if "produccion" in por_pol:                                   # resumen de factibilidad_v2
        marcas = por_pol.get("candidatos", {})
        tiempos = {c: {"segundos_por_dia": float(v["segundos_por_dia"]),
                       "factibilidad_v2": {"dias_de_maquina": v.get("dias_de_maquina"),
                                           "dias": por_pol.get("dias_produccion"),
                                           "fuera_de_la_decision": marcas.get(c, {}).get("fuera_de_la_decision"),
                                           "marca_robusta": v.get("marca_robusta")}}
                   for c, v in por_pol["produccion"].items()}
    else:
        tiempos = {c: v for c, v in por_pol.items()}
    return tiempos, {"archivo": p.name, "sha256": sha256_archivo(p), "schema": d.get("schema")}


def factibilidad_de_los_dos(ruta, cfg: dict | None = None,
                            contaminantes=dc.CONTAMINANTES_FACTIBILIDAD) -> tuple[dict, dict]:
    """La factibilidad que usa la decisión (Complemento de la Enmienda 1, punto 3): los segundos por día de LightGBM
    y de cada motor en **los dos contaminantes** (``factibilidad_de_archivo`` de cada uno), como ``{motor:
    {"segundos_por_dia": {pol: s}, "factibilidad_v2": {…}}}``; la regla la aplica ``decision_v2.evaluar_factibilidad``.
    Si el resumen trae su propio veredicto conjunto (``factibilidad.candidatos[c].factible``), queda como la marca de
    ``factibilidad_v2`` para cotejarla. Con ``cfg``, un resumen que declara otra regla que la vigente se rechaza."""
    p = Path(ruta)
    d = json.loads(p.read_text(encoding="utf-8"))
    _verificar_regla_factibilidad(d, p.name, cfg)
    veredicto = ((d.get("factibilidad") or {}).get("candidatos") or {}) if isinstance(d.get("factibilidad"), dict) else {}
    tiempos: dict[str, dict] = {}
    fuente = None
    for pol in contaminantes:
        por_motor, fuente = factibilidad_de_archivo(p, pol)
        for m, v in por_motor.items():
            entrada = tiempos.setdefault(m, {"segundos_por_dia": {}, "factibilidad_v2": {"por_contaminante": {}}})
            entrada["segundos_por_dia"][pol] = v["segundos_por_dia"] if isinstance(v, dict) else v
            if isinstance(v, dict) and v.get("factibilidad_v2"):
                entrada["factibilidad_v2"]["por_contaminante"][pol] = v["factibilidad_v2"]
    for m, entrada in tiempos.items():
        marcas = {x.get("fuera_de_la_decision") for x in entrada["factibilidad_v2"]["por_contaminante"].values()} - {None}
        if m in veredicto and "factible" in veredicto[m]:
            entrada["factibilidad_v2"]["fuera_de_la_decision"] = not bool(veredicto[m]["factible"])
        elif len(marcas) == 1:
            entrada["factibilidad_v2"]["fuera_de_la_decision"] = bool(marcas.pop())
        if not entrada["factibilidad_v2"]["por_contaminante"] and "fuera_de_la_decision" not in entrada["factibilidad_v2"]:
            del entrada["factibilidad_v2"]
    return tiempos, {**(fuente or {}), "contaminantes": list(contaminantes)}


def decidir(r: RutasV2, cfg: dict, pol: str, etiqueta: str = ETIQUETA, factibilidad: dict | None = None,
            fuente_factibilidad: dict | None = None, escribir: bool = True, replicas: int | None = None,
            forzado: dict | None = None) -> dict:
    """Aplica ``decision_v2.decidir_motor`` a la evidencia consolidada de LRO y BLQ-75 de un contaminante (sin
    cargar el panel) y, con ``escribir``, deja ``decision.json`` en la raíz v2 y la tabla y el registro en
    ``output_files/modelo_1km_v2``. La factibilidad (tiempos de LightGBM y de cada motor en los dos contaminantes,
    medidos antes de cualquier ajuste comparativo: ``factibilidad_de_los_dos``) es obligatoria y es la misma para
    las dos decisiones (Complemento, punto 3). ``forzado`` (de ``resolver_replicas_bootstrap``: un B distinto de
    1.999 aceptado con ``--forzar``) queda en el registro como ``replicas_bootstrap_forzadas``."""
    regla = dc.regla_de_config(cfg)
    e2_red2 = {}
    if "red_de_monitores" in cfg:                         # Enmienda 2, R22 paso 4 (y R16 y R17): el anexo
        import pliegues_red2_v2
        manifiesto_red2 = pliegues_red2_v2.exigir_registro(r, cfg)
    evidencias, insumos = {}, {}
    for prot in regla.protocolos:
        ruta = ruta_evidencia(r, etiqueta, pol, prot)
        ev = leer_json(ruta)
        if ev is None:
            raise Incompleto(f"{pol} {prot}: falta {NOMBRE_EVIDENCIA}; consolida antes el protocolo")
        if "red_de_monitores" in cfg and ev.get("bloque_mas_influyente") != regla.bloque_mas_influyente.get(prot):
            raise SystemExit(f"{pol} {prot}: la evidencia se consolidó con el bloque más influyente "
                             f"{ev.get('bloque_mas_influyente')!r} y la configuración dice "
                             f"{regla.bloque_mas_influyente.get(prot)!r} (R16): consolida de nuevo")
        if "red_de_monitores" in cfg:                     # R15: rige la E2 registrada antes del ajuste
            ev, e2_red2[prot] = pliegues_red2_v2.evaluabilidad_e2_que_rige(ev, manifiesto_red2, pol, prot)
        evidencias[prot] = ev
        insumos[f"evidencia_{prot}"] = ruta
    tr = traza(insumos, {"bootstrap": {p: evidencias[p]["semilla_bootstrap"] for p in regla.protocolos},
                         "bootstrap_salvaje": {p: evidencias[p]["semilla_salvaje"] for p in regla.protocolos}},
               int(cfg["operacion"]["hilos_maximos"]), rutas=r, parametros={"etiqueta": etiqueta})
    tr["factibilidad"] = fuente_factibilidad
    tabla, registro = dc.decidir_motor(evidencias, factibilidad, regla=regla, replicas=replicas, traza=tr,
                                       contaminante=pol)
    if forzado is not None:
        registro["replicas_bootstrap_forzadas"] = dict(forzado)
    if e2_red2:                                           # Enmienda 2, R15: la E2 que rige y la de la decisión (registro)
        registro["evaluabilidad_E2_red2"] = e2_red2
    if escribir:
        nombre = f"comparacion_{etiqueta}_{pol}_decision"
        with candado_escritura(f"{CARPETA}.{etiqueta}.{pol}", rutas=r):
            sha = publicar_json(registro, r.raiz_v2 / CARPETA / etiqueta / pol / "decision.json", r)
            datos = tabla.to_csv(index=False, lineterminator="\n", float_format="%.10g").encode("utf-8")
            publicar_bytes(datos, r.salidas_v2 / f"{nombre}.csv", r)
            publicar_json({**registro, "fuente": {"decision.json": {**r.relativa(r.raiz_v2 / CARPETA / etiqueta / pol /
                                                                                 "decision.json"), "sha256": sha}},
                           "tabla": {f"{nombre}.csv": hashlib.sha256(datos).hexdigest()}}, r.salidas_v2 / f"{nombre}.json", r)
    return {"tabla": tabla, "registro": registro}


# ---------------------------------------------------------------------------
# Piloto de tiempos (§10)
# ---------------------------------------------------------------------------
CRITERIOS_PILOTO = {"entrenamiento": "filas_entrenamiento_disponibles", "prueba": "filas_prueba"}


def pliegues_piloto(pliegues: list[dict], criterio: str = "entrenamiento") -> list[dict]:
    """Los dos pliegues del piloto (§10): el de más filas de entrenamiento disponibles y el de menos (desempate:
    menor k), según la configuración (``presupuesto.piloto.eleccion_de_los_pliegues``, ratificado por la Enmienda 1,
    punto 1.12). ``criterio="prueba"`` ordena por filas de prueba, el provisional anterior; en los protocolos sin
    exclusión adicional los dos criterios eligen el mismo par, porque entrenamiento = total − prueba."""
    campo = CRITERIOS_PILOTO[criterio]
    mas = sorted(pliegues, key=lambda f: (-int(f[campo]), int(f["k"])))[0]
    menos = sorted(pliegues, key=lambda f: (int(f[campo]), int(f["k"])))[0]
    return [mas] + ([menos] if int(menos["k"]) != int(mas["k"]) else [])


def estimar_presupuesto(tiempos: pd.DataFrame, planes: dict, conteos: dict, umbral_h: float) -> dict:
    """Estimación gruesa: media por pliegue de cada tarea medida × pliegues del protocolo, por contaminante y
    protocolo, para cada nivel de recorte de ``planes`` (0 … 4, en el orden de la Enmienda 1, punto 12). Las tareas
    no medidas cuentan 0. El piloto de §10 usa la extrapolación por fase de ``piloto_v2.extrapolar``, que escala con
    las filas de cada pliegue."""
    out = {"umbral_horas": umbral_h, "por_recorte": {}}
    media = tiempos.groupby(["contaminante", "protocolo", "tarea", "replica"])["segundos"].mean()
    for recorte, por_pol in planes.items():
        total, detalle = 0.0, {}
        for pol, por_prot in por_pol.items():
            for prot, plan in por_prot.items():
                claves = [("vecindario", 0)] + [(t.id, t.replica) for t in plan["tareas"]]
                if plan["interno"]:
                    claves += [(f"interno_{m}", 0) for m in plan["interno"]] + [("interno_vecindario", 0)]
                seg = 0.0
                for tarea, rep in claves:
                    clave = (pol, prot, tarea, rep)
                    if clave in media.index:
                        mult = conteos[pol][prot]
                        if tarea.startswith("interno_"):          # cada pliegue externo tiene varios internos
                            n_int = tiempos[(tiempos["contaminante"] == pol) & (tiempos["protocolo"] == prot)
                                            & (tiempos["tarea"] == tarea)].groupby("k").size().mean()
                            mult *= float(n_int)
                        seg += float(media.loc[clave]) * mult
                detalle[f"{pol}/{prot}"] = round(seg / 3600.0, 2)
                total += seg
        out["por_recorte"][str(recorte)] = {"horas": round(total / 3600.0, 2), "detalle": detalle,
                                            "bajo_el_umbral": bool(total / 3600.0 <= umbral_h)}
    sugerido = next((int(k) for k, v in out["por_recorte"].items() if v["bajo_el_umbral"]), None)
    out["recorte_sugerido"] = sugerido
    return out


# ---------------------------------------------------------------------------
# Consola
# ---------------------------------------------------------------------------
def _opciones(args, recorte: int) -> Opciones:
    return Opciones(motores=tuple(args.motores), perdidas=not args.sin_perdidas, alertas=not args.sin_alertas,
                    eje_b=not args.sin_eje_b, curvas=not args.sin_curvas, semillas=not args.sin_semillas,
                    apilado=not args.sin_apilado, calidad=not args.sin_calidad, recorte=int(recorte))


def sha256_contrato(r: RutasV2, cfg: dict) -> str | None:
    """sha256 del contrato vigente: el del archivo si existe; si no (raíces de prueba), el que declara la
    configuración (como ``Contexto.huellas_firma``)."""
    return sha256_archivo(r.contrato) if r.contrato.exists() else (cfg.get("contrato") or {}).get("sha256")


def plan_de_corrida(r: RutasV2, cfg: dict) -> tuple[dict | None, list[str], str | None]:
    """El plan de la corrida que deja el piloto de tiempos (``plan_corrida_v2.json``, §10) y por qué no sirve para
    fijar el recorte, si no sirve: falta, tiene otro esquema, se hizo con otro orden de recortes que el vigente (como
    el plan congelado por la Enmienda 1, con el orden de antes del punto 12) o bajo otro contrato, o su
    ``recorte_aplicado`` no es un nivel válido. Devuelve (plan, problemas, sha256 del archivo)."""
    import piloto_v2
    ruta = r.raiz_v2 / piloto_v2.NOMBRE_PLAN
    plan = leer_json(ruta)
    if plan is None:
        return None, [f"falta {piloto_v2.NOMBRE_PLAN} (lo escribe el piloto de tiempos, §10)"], None
    problemas = []
    if plan.get("schema") != piloto_v2.SCHEMA_PLAN:
        problemas.append(f"tiene el esquema {plan.get('schema')!r} y no {piloto_v2.SCHEMA_PLAN!r}")
    c = plan.get("contrato") or {}
    orden = cfg["presupuesto"]["orden_de_recortes"]
    if c.get("orden_de_recortes") != orden:
        problemas.append("se hizo con otro orden de recortes que el vigente (Enmienda 1, punto 12)")
    vigente = sha256_contrato(r, cfg)
    if c.get("sha256") != vigente:
        problemas.append(f"se hizo bajo otro contrato ({str(c.get('sha256'))[:8]}…; el vigente es {str(vigente)[:8]}…)")
    rc = plan.get("recorte_aplicado")
    if isinstance(rc, bool) or not isinstance(rc, int) or not 0 <= rc <= len(orden):
        problemas.append(f"su recorte_aplicado no es un nivel válido: {rc!r}")
    return plan, problemas, sha256_archivo(ruta)


def resolver_recorte(r: RutasV2, cfg: dict, pedido: int | None, forzar: str | None,
                     estricto: bool = True) -> tuple[int, dict]:
    """El recorte del presupuesto de la corrida, que elige el código con el piloto, sin elección a mano (Complemento,
    punto 8): por omisión, el ``recorte_aplicado`` de ``plan_corrida_v2.json`` (``plan_de_corrida``). Con
    ``estricto`` (``correr`` y ``consolidar``) se rechaza otro ``--recorte``, o un plan que no sirve, salvo ``forzar``
    (el motivo de ``--forzar-recorte``), que exige ``--recorte`` y se registra en la bitácora del manifiesto
    (``anotar_recorte``). Sin ``estricto`` (``plan`` y ``estado``, que no ajustan ni escriben) vale el pedido, el del
    plan o, si el plan no sirve, 0. Devuelve el recorte y su origen (para el registro)."""
    plan, problemas, sha = plan_de_corrida(r, cfg)
    del_plan = None if problemas else int(plan["recorte_aplicado"])
    base = {"recorte_del_plan": del_plan, "plan_sha256": sha, "problemas_del_plan": problemas}
    if forzar is not None:
        motivo = str(forzar).strip()
        if not estricto:
            raise SystemExit("--forzar-recorte sólo sirve con correr y consolidar")
        if not motivo:
            raise SystemExit("--forzar-recorte exige un motivo, que queda en la bitácora del manifiesto (§10)")
        if pedido is None:
            raise SystemExit("--forzar-recorte exige --recorte N (el recorte que se fuerza)")
        if int(pedido) == del_plan:
            log.info("--recorte %s es el del plan: no hace falta forzarlo", pedido)
            return del_plan, {**base, "origen": "plan"}
        return int(pedido), {**base, "origen": "forzado", "motivo": motivo, "utc": ahora_utc()}
    if not estricto:
        if pedido is not None:
            return int(pedido), {**base, "origen": "pedido"}
        if del_plan is not None:
            return del_plan, {**base, "origen": "plan"}
        log.warning("el plan de la corrida no sirve (%s); se muestra el recorte 0", "; ".join(problemas))
        return 0, {**base, "origen": "sin plan válido (0, sólo para mostrar)"}
    if problemas:
        raise SystemExit("el recorte de la corrida sale de plan_corrida_v2.json (Complemento, punto 8), pero el plan "
                         "no sirve: " + "; ".join(problemas) + ". Vuelve a medir el piloto con la máquina libre y rehaz "
                         "el plan (correr_v2.py piloto --contaminantes pm25 no2 --calibrar-familias "
                         "--remedir-contaminadas 0.5), o usa --recorte N --forzar-recorte MOTIVO, que queda en la "
                         "bitácora del manifiesto")
    if pedido is not None and int(pedido) != del_plan:
        raise SystemExit(f"--recorte {pedido} no es el del plan (recorte_aplicado = {del_plan} en plan_corrida_v2.json): "
                         f"el recorte no se elige a mano (Complemento, punto 8). --forzar-recorte MOTIVO lo permite y "
                         f"lo deja en la bitácora del manifiesto")
    return del_plan, {**base, "origen": "plan"}


def resolver_replicas_bootstrap(cfg: dict, pedido: int | None, forzar: str | None,
                                accion: str = "decidir") -> tuple[int, dict | None]:
    """B del bootstrap percentil de ``consolidar`` y ``decidir``: el del contrato (1.999, Complemento, punto 2;
    ``inferencia_diferencias.bootstrap.replicas``), con el que el umbral de Holm nunca empata con el intervalo
    escalonado. Otro valor sólo con ``forzar`` (el motivo de ``--forzar``), que se registra en lo que se escribe
    (``decision.json`` → ``replicas_bootstrap_forzadas``; ``consolidado.json`` → ``forzado``). Devuelve B y el
    registro del forzado (None si no lo hubo)."""
    exigido = int(dc.regla_de_config(cfg).replicas_bootstrap)
    B = exigido if pedido is None else int(pedido)
    if B == exigido:
        return B, None
    motivo = str(forzar or "").strip()
    if not motivo:
        raise SystemExit(f"{accion} --replicas-bootstrap {B}: el contrato fija B = {exigido} (Complemento, punto 2: "
                         f"ningún umbral de Holm empata con el intervalo escalonado); otro valor sólo con --forzar "
                         f"MOTIVO, que queda registrado")
    if B < 1:
        raise SystemExit(f"--replicas-bootstrap {B}: debe ser positivo")
    log.warning("%s con B = %d en vez de %d (--forzar: %s); queda registrado", accion, B, exigido, motivo)
    return B, {"replicas_bootstrap": B, "replicas_del_contrato": exigido, "motivo": motivo, "utc": ahora_utc(),
               "fuente": f"{accion} --forzar (Complemento, punto 2)"}


def _seleccion(pliegues: list[dict], ks, parte) -> list[dict]:
    out = [f for f in pliegues if ks is None or int(f["k"]) in ks]
    if parte:
        i, m = (int(x) for x in parte.split("/"))
        out = [f for f in out if int(f["k"]) % m == i]
    return out


def anotar_recorte(r: RutasV2, recorte: int, etiqueta: str, forzado: dict | None = None) -> None:
    """Deja el recorte del presupuesto (1 … 4, en el orden de la Enmienda 1, punto 12) en la bitácora del manifiesto
    de pliegues (§10), una sola vez, con los recortes aplicados. Un recorte forzado (``forzado``: el origen que
    devuelve ``resolver_recorte`` con ``--forzar-recorte``) se anota siempre, también el 0, con su motivo, el recorte
    del plan y por qué no se usó; uno idéntico (mismo recorte, etiqueta, motivo y plan) no se repite."""
    import pliegues_v2
    m = leer_json(r.manifiesto_pliegues) or {}
    eventos = [e for e in m.get("bitacora", []) if e.get("evento") == "recorte_presupuesto"
               and e.get("recorte") == recorte and e.get("etiqueta") == etiqueta]
    if forzado is not None:
        registro = {k: forzado.get(k) for k in ("motivo", "recorte_del_plan", "plan_sha256", "problemas_del_plan")}
        if any((e.get("forzado") or {}).get("motivo") == registro["motivo"]
               and (e.get("forzado") or {}).get("plan_sha256") == registro["plan_sha256"] for e in eventos):
            return
    elif recorte <= 0 or any(not e.get("forzado") for e in eventos):
        return
    orden = cargar_config(r)["presupuesto"]["orden_de_recortes"]
    evento = {"evento": "recorte_presupuesto", "recorte": recorte, "etiqueta": etiqueta,
              "aplicados": [x["recorte"] for x in orden if x["orden"] <= recorte]}
    if forzado is not None:
        evento.update({"fuente": "forzado con --forzar-recorte: no es el recorte_aplicado de plan_corrida_v2.json",
                       "forzado": registro})
    pliegues_v2.anotar_bitacora(evento, r)


def estado(r: RutasV2, cfg: dict, recetas: dict, op: Opciones, args) -> int:
    """Puntos de control presentes frente a los del plan, sin cargar el panel (sólo el manifiesto)."""
    import calidad_v2
    man = leer_json(r.manifiesto_pliegues)
    if man is None:
        raise SystemExit("Falta el manifiesto de pliegues")
    for pol in args.contaminantes:
        raiz = r.raiz_v2 / CARPETA / args.etiqueta / pol
        con_qc = op.calidad and calidad_v2.ruta_calidad(r, pol).exists()
        for prot in args.protocolos:
            plan = plan_protocolo(recetas, prot, op, calidad_disponible=con_qc)
            pl = man["contaminantes"][pol]["protocolos"][prot]["pliegues"]
            hechos = sum(1 for f in pl for t in plan["tareas"]
                         if (raiz / prot / f"k{int(f['k']):03d}" / f"r{t.replica}" / f"{t.id}.npz").exists())
            internos = sum(len(list((raiz / prot / f"k{int(f['k']):03d}" / "interno").glob("*.npz"))) for f in pl)
            listo = (raiz / prot / "consolidado.json").exists()
            print(f"{pol} {prot}: {hechos}/{len(pl) * len(plan['tareas'])} puntos de control"
                  f"{f', {internos} internos' if plan['interno'] else ''}{'; consolidado' if listo else ''}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Comparación v2 de motores y pérdidas (DISENO_AMBIENTAL_V2.md §3–§8).")
    ap.add_argument("accion", choices=("plan", "piloto", "correr", "estado", "consolidar", "decidir"))
    ap.add_argument("--contaminantes", nargs="+", default=["pm25", "no2"], choices=("pm25", "no2"))
    ap.add_argument("--protocolos", nargs="+", default=list(PROTOCOLOS), choices=PROTOCOLOS)
    ap.add_argument("--pliegues", nargs="*", type=int, default=None, help="k de los pliegues (todos si se omite)")
    ap.add_argument("--parte", default=None, help="i/m: sólo los pliegues con k %% m == i (procesos en paralelo)")
    ap.add_argument("--etiqueta", default=ETIQUETA)
    ap.add_argument("--hilos", type=int, default=None, help="hilos por proceso (máximo operacion.hilos_maximos)")
    ap.add_argument("--motores", nargs="+", default=list(mv.MOTORES_EJE_A), choices=mv.MOTORES_EJE_A)
    ap.add_argument("--recorte", type=int, default=None, choices=(0, 1, 2, 3, 4),
                    help="recortes del presupuesto en el orden de la Enmienda 1, punto 12. Por omisión, el "
                         "recorte_aplicado de plan_corrida_v2.json (lo elige el piloto: Complemento, punto 8); correr "
                         "y consolidar rechazan otro valor salvo --forzar-recorte")
    ap.add_argument("--forzar-recorte", default=None, metavar="MOTIVO",
                    help="correr/consolidar: usa --recorte aunque no sea el del plan, o aunque el plan no sirva; el "
                         "motivo queda en la bitácora del manifiesto de pliegues (§10)")
    for nombre in ("perdidas", "alertas", "eje-b", "curvas", "semillas", "apilado", "calidad"):
        ap.add_argument(f"--sin-{nombre}", action="store_true")
    ap.add_argument("--replicas-bootstrap", type=int, default=None,
                    help=f"réplicas del bootstrap percentil; consolidar y decidir sólo aceptan {bs.REPLICAS} "
                         f"(Complemento, punto 2) salvo --forzar")
    ap.add_argument("--forzar", default=None, metavar="MOTIVO",
                    help="consolidar/decidir: acepta --replicas-bootstrap distinto de 1.999; el motivo queda registrado "
                         "en consolidado.json o en decision.json")
    ap.add_argument("--factibilidad", default=None, metavar="JSON",
                    help="decidir: tiempos de la factibilidad de los dos contaminantes (Complemento de la Enmienda 1, "
                         "punto 3); por omisión, el resumen de factibilidad_v2 en "
                         "output_files/modelo_1km_v2/factibilidad_produccion.json")
    ap.add_argument("--sin-sellar", action="store_true",
                    help="permite correr o consolidar con cambios sin confirmar en scripts_modelo_1km/v2 (sólo para "
                         "pruebas: la Enmienda 1, punto 14, exige el sellado antes de cualquier ajuste comparativo)")
    piloto = ap.add_argument_group("piloto de tiempos (§10, piloto_v2)")
    piloto.add_argument("--calibrar-familias", action="store_true",
                        help="mide además, en un pliegue de LRO, las familias que el alcance del piloto no cubre "
                             "(pérdidas de §6, alertas y eje B), para no extrapolarlas a ciegas")
    piloto.add_argument("--rehacer", action="store_true", help="vuelve a medir lo ya medido (si no, reanuda)")
    piloto.add_argument("--solo-estimar", action="store_true",
                        help="no ajusta nada: extrapola y escribe el plan con las mediciones guardadas")
    piloto.add_argument("--criterio-pliegues", choices=tuple(CRITERIOS_PILOTO), default="entrenamiento")
    piloto.add_argument("--remedir-contaminadas", type=float, default=None, metavar="FRACCION",
                        help="vuelve a medir las tareas cuyo ajuste sólo se midió con otros procesos ocupando al "
                             "menos esta fracción de la máquina (la extrapolación usa la medición con menos contención)")
    piloto.add_argument("--aunque-ocupada", action="store_true",
                        help="mide aunque la carga media al empezar no esté bajo 2 (el Complemento, punto 8, pide la "
                             "máquina libre; queda registrado en la sesión y en el plan)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
    r = rutas_v2()
    cfg = cargar_config(r)
    if "red_de_monitores" in cfg and args.sin_calidad:   # Enmienda 2: la bandera es obligatoria con la red 2
        raise SystemExit("--sin-calidad no se admite con la red ampliada: la bandera de calidad es obligatoria "
                         "(Enmienda 2, segunda revisión, menor 8)")
    recetas = mv.recetas_de(cfg, args.hilos)
    if args.accion == "piloto":
        import piloto_v2
        return piloto_v2.ejecutar(args, r, cfg)
    if args.forzar is not None and args.accion not in ("consolidar", "decidir"):
        raise SystemExit("--forzar sólo sirve con consolidar y decidir (--replicas-bootstrap)")
    if args.forzar_recorte is not None and args.accion not in ("correr", "consolidar"):
        raise SystemExit("--forzar-recorte sólo sirve con correr y consolidar")
    # Guardas (antes del sellado y de cargar nada): el recorte sale del plan del piloto (Complemento, punto 8) y B es
    # el del contrato (Complemento, punto 2), salvo lo forzado con motivo, que queda registrado.
    op, origen_recorte = None, None
    if args.accion != "decidir":
        recorte, origen_recorte = resolver_recorte(r, cfg, args.recorte, args.forzar_recorte,
                                                   estricto=args.accion in ("correr", "consolidar"))
        op = _opciones(args, recorte)
        log.info("recorte del presupuesto: %d (%s)", recorte, origen_recorte["origen"])
    replicas, forzado_replicas = (resolver_replicas_bootstrap(cfg, args.replicas_bootstrap, args.forzar, args.accion)
                                  if args.accion in ("consolidar", "decidir") else (bs.REPLICAS, None))
    recorte_forzado = origen_recorte if (origen_recorte or {}).get("origen") == "forzado" else None
    forzado = ({"recorte": recorte_forzado, "replicas_bootstrap": forzado_replicas}
               if recorte_forzado or forzado_replicas else None)
    if args.accion == "plan":
        man = leer_json(r.manifiesto_pliegues)
        print(f"recorte del presupuesto: {op.recorte} ({origen_recorte['origen']})")
        for pol in args.contaminantes:
            for prot in args.protocolos:
                p = plan_protocolo(recetas, prot, op, calidad_disponible=True)
                n_k = man["conteos"][pol][prot] if man else "?"
                print(f"{pol} {prot}: {n_k} pliegues × {len(p['tareas'])} tareas"
                      f"{' + internos ' + '/'.join(p['interno']) if p['interno'] else ''}")
                for t in p["tareas"]:
                    print(f"    {t.id:<34} {t.familia:<9} r{t.replica} tope {t.tope} {t.calidad}")
        return 0
    if args.accion == "estado":
        return estado(r, cfg, recetas, op, args)
    if args.accion in ("correr", "consolidar", "decidir"):
        verificar_sellado(r, permitir_sin_sellar=args.sin_sellar)
    if args.accion == "decidir":
        ruta_fac = Path(args.factibilidad) if args.factibilidad else r.salidas_v2 / "factibilidad_produccion.json"
        if not ruta_fac.exists():
            raise SystemExit(f"falta la factibilidad ({ruta_fac.name}): el tiempo de predecir un día de superficies con "
                             f"cada candidato y con LightGBM compilado se mide antes de cualquier ajuste comparativo "
                             f"(Complemento de la Enmienda 1, punto 3; factibilidad_v2)")
        fac, fuente = factibilidad_de_los_dos(ruta_fac, cfg)          # los dos contaminantes: la misma para los dos
        for pol in args.contaminantes:
            decidir(r, cfg, pol, args.etiqueta, fac, fuente, escribir=True, replicas=replicas, forzado=forzado_replicas)
            print(f"{pol}: decisión registrada en {CARPETA}/{args.etiqueta}/{pol}/decision.json")
        return 0
    if args.accion == "correr" or recorte_forzado is not None:
        anotar_recorte(r, op.recorte, args.etiqueta, forzado=recorte_forzado)
    for pol in args.contaminantes:
        ctx = Contexto.desde_disco(pol, r, cfg, etiqueta=args.etiqueta, hilos=args.hilos, con_calidad=op.calidad)
        for prot in args.protocolos:
            plan = plan_protocolo(ctx.recetas, prot, op, calidad_disponible=ctx.calidad is not None)
            if args.accion == "consolidar":
                res = consolidar(ctx, prot, plan, escribir=True, replicas_bootstrap=replicas, forzado=forzado)
                print(f"{pol} {prot}: consolidado, {res['consolidado']['pares']['pares_comunes']:,} pares comunes")
                continue
            for f in _seleccion(ctx.pliegues(prot), args.pliegues, args.parte):
                nombre = nombre_candado_pliegue(args.etiqueta, pol, prot, int(f["k"]))
                try:
                    with candado_escritura(nombre, rutas=r):
                        correr_pliegue(ctx, prot, f, plan)
                except CandadoOcupado:
                    log.info("%s %s k=%s: otro proceso tiene el pliegue; sigo", pol, prot, f["k"])
        del ctx
    return 0


# ---------------------------------------------------------------------------
# Código de ajuste de la firma (Complemento de la Enmienda 1, punto 7)
# ---------------------------------------------------------------------------
# Las funciones de este archivo que definen las filas (de entrenamiento, de validación o del amortiguador), las
# semillas, el vecindario, las matrices o el ajuste de un punto de control. Su huella entra en la firma junto con la
# de los archivos de CODIGO_AJUSTE: cambiar su código rehace los puntos que dependen de él, sin subir una versión a
# mano. Cambiar sólo un comentario o un docstring no la cambia. Las semillas que entrega ``_semillas`` entran además
# en la firma (``firma_tarea``).
FUNCIONES_AJUSTE = (
    Contexto.desde_tablas, Contexto.matriz, Contexto.estaciones_de, Contexto.tope, Contexto.codigos_qc,
    Contexto.mascara_calidad, Contexto.lineales, Contexto.grupo_de_estacion,
    receta_de, es_huber, _crear, _semillas, deltas_guardados, correr_pliegue,
    estaciones_con_filas, amortiguador_interno, _mascara_de_estaciones, validacion_mlp, delta_huber_honesto,
    definicion_internos, correr_internos,
)


def huella_de_funcion(f) -> str:
    """sha256 del árbol sintáctico de una función (de su código fuente), sin su docstring ni los de lo que defina
    dentro: el código, no su documentación ni sus comentarios. El árbol depende de la versión de Python, que ya
    está en la firma (bibliotecas)."""
    import ast
    import textwrap

    arbol = ast.parse(textwrap.dedent(inspect.getsource(f)))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and nodo.body:
            primero = nodo.body[0]
            if isinstance(primero, ast.Expr) and isinstance(primero.value, ast.Constant) and isinstance(primero.value.value, str):
                nodo.body = nodo.body[1:] or [ast.Pass()]
    return hashlib.sha256(ast.dump(arbol, include_attributes=False).encode("utf-8")).hexdigest()


@functools.lru_cache(maxsize=1)
def huella_funciones_ajuste() -> dict:
    """``{nombre calificado: sha256}`` de ``FUNCIONES_AJUSTE``, más el sha256 conjunto (se calcula al importar)."""
    por_funcion = {f.__qualname__: huella_de_funcion(f) for f in FUNCIONES_AJUSTE}
    return {**por_funcion, "conjunto": sha256_json(por_funcion)}


@functools.lru_cache(maxsize=1)
def huella_archivos_ajuste() -> dict:
    """sha256 de los archivos de ``CODIGO_AJUSTE`` (se calcula al importar: el código que corre)."""
    return {nombre: sha256_archivo(AQUI / nombre) for nombre in CODIGO_AJUSTE}


def codigo_ajuste_actual() -> dict:
    """El código de ajuste que corre (Complemento, punto 7; el mismo de la firma, ``Contexto.codigo_ajuste``): los
    sha256 de los archivos de ``CODIGO_AJUSTE``, el sha256 conjunto de las funciones de ``FUNCIONES_AJUSTE`` y la
    huella de todo («huella»), que distingue las sesiones del piloto de tiempos (``piloto_v2.vigencia_por_codigo``)."""
    archivos, funciones = huella_archivos_ajuste(), huella_funciones_ajuste()
    return {"huella": sha256_json({**archivos, "funciones": funciones}), "archivos": dict(archivos),
            "funciones_conjunto": funciones["conjunto"]}


huella_funciones_ajuste()
huella_archivos_ajuste()


if __name__ == "__main__":
    sys.exit(main())
