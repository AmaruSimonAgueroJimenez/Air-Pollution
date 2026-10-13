#!/usr/bin/env python3
"""Orquestador de la comparación v2 de motores y pérdidas (``DISENO_AMBIENTAL_V2.md`` §3–§8 y §10).

Reanudable por pliegue, con puntos de control atómicos en la raíz v2:
``<raíz v2>/comparacion/<etiqueta>/<pol>/<protocolo>/kNNN/{vecindario,r0,r1,r2,interno}/<tarea>.npz``. Cada punto
lleva su **firma** (panel, manifiesto de pliegues, pliegue y conjunto excluido, tarea y receta efectiva, filas de
entrenamiento, huella del vecindario recalculado, calidad, código de ajuste, bibliotecas e hilos) y su **traza**
(commit, hash del código, sha256 de insumos, bibliotecas, hilos y semillas). Un punto con la firma vigente no se
recalcula; uno con otra firma se rehace. Cada pliegue se trabaja bajo su propio candado de escritura, así que se
pueden lanzar varios procesos sobre pliegues distintos (``--parte i/m``).

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

**Consolidación** (``consolidar``), cuando están todos los pliegues de un protocolo: promedio simple y apilado,
retransformación primaria (Duan honesto por macrozona × franja) y sensibilidad (OOF interno), intersección
forzada de los pares finitos de todos los motores, métricas (niveles, desagregaciones, escalas y población),
cuantiles, alertas y bootstrap pareado por bloques con la regla de superioridad.

**Piloto** (§10, ``piloto_v2``): dos pliegues por protocolo (el de más y el de menos filas de entrenamiento,
provisional), los motores del eje A con el N común y los puntos de la curva de aprendizaje en un pliegue de LRO,
con el mismo ``correr_pliegue`` en modo piloto: no guarda predicciones ni calcula métricas; mide tiempo de pared,
CPU y memoria de cada fase (``medidor``), extrapola las horas de máquina de la corrida completa y aplica los
recortes de §10 en orden (``plan_corrida_v2.json`` en la raíz v2).

Uso::

    python -B scripts_modelo_1km/v2/correr_v2.py plan --contaminantes pm25 no2
    python -B scripts_modelo_1km/v2/correr_v2.py piloto --contaminantes pm25 no2 --hilos 12 --calibrar-familias
    python -B scripts_modelo_1km/v2/correr_v2.py correr --contaminantes pm25 --protocolos LRO BLQ-75 --hilos 12
    python -B scripts_modelo_1km/v2/correr_v2.py correr --contaminantes no2 --parte 0/2 --hilos 6   # y 1/2 en otro
    python -B scripts_modelo_1km/v2/correr_v2.py estado --contaminantes pm25 no2
    python -B scripts_modelo_1km/v2/correr_v2.py consolidar --contaminantes pm25 --protocolos LRO
"""
from __future__ import annotations

import argparse
import contextlib
import functools
import hashlib
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
    _pre = argparse.ArgumentParser(add_help=False)
    _pre.add_argument("--hilos", type=int, default=None)
    _h = _pre.parse_known_args()[0].hilos
    fijar_hilos(_h if _h else 12)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import bootstrap_v2 as bs  # noqa: E402
import metricas_v2 as mt  # noqa: E402
import motores_v2 as mv  # noqa: E402
import perdidas_v2 as pv  # noqa: E402
import retransformacion_v2 as rt  # noqa: E402
from _rutas_v2 import (  # noqa: E402
    CandadoOcupado, RutasV2, candado_escritura, cargar_config, leer_json, publicar_bytes, publicar_json,
    publicar_parquet, rutas_v2, valor_vigente,
)
from _traza_v2 import sha256_archivo, sha256_json, traza, versiones_bibliotecas  # noqa: E402
from pliegues_v2 import PROTOCOLOS, huella_pliegues  # noqa: E402
from vecindario_v2 import Vecindario  # noqa: E402

log = logging.getLogger("modelo_1km_v2.correr")

SCHEMA_PUNTO = "airpollution.modelo-1km-v2.comparacion-punto.v1"
SCHEMA_CONSOLIDADO = "airpollution.modelo-1km-v2.comparacion-consolidado.v1"
SCHEMA_TABLAS = "airpollution.modelo-1km-v2.comparacion-tablas.v1"
SCHEMA_PILOTO = "airpollution.modelo-1km-v2.comparacion-piloto.v1"
VERSION_AJUSTE = 1                     # súbela si cambia la forma de armar un pliegue en este archivo
CARPETA = "comparacion"
ETIQUETA = "principal"
CODIGO_AJUSTE = ("motores_v2.py", "perdidas_v2.py", "vecindario_v2.py")
PROTOCOLOS_SEMILLAS = ("LRO", "BLQ-75")
PROTOCOLOS_CALIDAD = ("LOSO-D", "LRO")
VARIANTES_CALIDAD = ("validado_y_preliminar", "solo_validado")
ETIQUETAS_PERDIDA = ("l2_original", "huber", "q05", "q50", "q95")
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
    variante: str = "l2_log_duan"
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
    motores: tuple = mv.MOTORES_EJE_A
    perdidas: bool = True
    alertas: bool = True
    eje_b: bool = True
    curvas: bool = True
    semillas: bool = True
    apilado: bool = True
    calidad: bool = True
    recorte: int = 0


def plan_protocolo(recetas: dict, prot: str, op: Opciones, calidad_disponible: bool) -> dict:
    """Tareas de un protocolo según el contrato y los recortes de §10 (``op.recorte`` = 0 … 3)."""
    if prot not in PROTOCOLOS:
        raise ValueError(f"protocolo desconocido: {prot}")
    eje_a = [m for m in mv.MOTORES_EJE_A if m in op.motores]
    if op.recorte >= 3 and prot not in PROTOCOLOS_SEMILLAS:
        eje_a = [m for m in eje_a if m != "mlp"]                       # recorte 3: MLP sólo en LRO y BLQ-75
    tareas = [Tarea(m, m, "eje_A") for m in eje_a]
    if op.perdidas:
        for m in mv.MOTORES_PERDIDAS:
            if m in op.motores:
                tareas += [Tarea(f"{m}_{e}", m, "perdidas", variante=e) for e in ETIQUETAS_PERDIDA]
    if op.alertas:
        tareas.append(Tarea("alertas_q80", "alertas", "alertas"))
    if op.eje_b:
        tareas += [Tarea("gp", "gp", "eje_B", tope=recetas["gp"]["tope"]),
                   Tarea("lme", "lme", "eje_B", tope=recetas["lme"]["tope"]),
                   Tarea("lineales", "lineales", "eje_B", tope=None, salidas=mv.MOTORES_LINEALES)]
    curvas = op.curvas and prot in recetas["protocolos_curvas"] and not (op.recorte >= 2 and prot != "LRO")
    if curvas:
        for m in ("lightgbm", "xgboost", "random_forest"):
            if m in eje_a:
                for t in recetas["curvas"][m]:
                    if t != recetas["N_comun"]:
                        tareas.append(Tarea(f"{m}_n{'todas' if t is None else t}", m, "curva", tope=t))
    semillas = op.semillas and prot in PROTOCOLOS_SEMILLAS and not (op.recorte >= 1 and prot != "LRO")
    if semillas:
        tareas += [Tarea(m, m, "eje_A", replica=r) for r in (1, 2) for m in eje_a]
    if op.calidad and calidad_disponible and prot in PROTOCOLOS_CALIDAD and "lightgbm" in eje_a:
        tareas += [Tarea(f"lightgbm_cal_{v}", "lightgbm", "calidad", calidad=v) for v in VARIANTES_CALIDAD]
    bases = recetas["apilado"]["bases"]
    interno = (op.apilado and prot in recetas["apilado"]["protocolos"] and all(b in eje_a for b in bases))
    return {"protocolo": prot, "tareas": tareas, "interno": list(bases) if interno else [],
            "semillas": semillas, "curvas": curvas, "recorte": op.recorte}


def _orden_tareas(tareas) -> list:
    """Agrupa por réplica, tope y calidad (reusa la matriz de entrenamiento) y deja l2_original antes de Huber."""
    prioridad = {"l2_original": 0, "huber": 1}
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
    _lineales: object = None
    _traza: dict | None = None

    @property
    def n(self) -> int:
        return len(self.y)

    # --- Construcción -------------------------------------------------------
    @classmethod
    def desde_tablas(cls, pol: str, panel: pd.DataFrame, manifiesto: dict, cfg: dict, rutas: RutasV2,
                     etiqueta: str = ETIQUETA, hilos: int | None = None, calidad=None, vec: Vecindario | None = None,
                     identidad_panel: str | None = None, insumos: dict | None = None) -> "Contexto":
        """Contexto desde un panel en memoria (filas en el orden del panel) y el manifiesto de pliegues."""
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
                   huella_calidad=huella_qc, insumos=dict(insumos or {}))

    @classmethod
    def desde_disco(cls, pol: str, rutas: RutasV2 | None = None, cfg: dict | None = None, etiqueta: str = ETIQUETA,
                    hilos: int | None = None, con_calidad: bool = True) -> "Contexto":
        """Panel v1 (sólo lectura), manifiesto de pliegues y, si existe, la bandera de calidad de la raíz v2."""
        import pyarrow.parquet as pq

        r = rutas or rutas_v2()
        cfg = cfg if cfg is not None else cargar_config(r)
        h = int(cfg["operacion"]["hilos_maximos"]) if hilos is None else int(hilos)
        man = leer_json(r.manifiesto_pliegues)
        if man is None:
            raise SystemExit(f"Falta el manifiesto de pliegues {r.relativa(r.manifiesto_pliegues)}")
        vec = Vecindario.desde_panel(pol, r, manifiesto=man, cfg=cfg, hilos=h)
        feats = list(cfg["motores"]["eje_A"]["predictores"][pol])
        columnas = list(dict.fromkeys(["estacion", "ts_utc", "obs", "anio", "hora_local", "macrozona_cod", "pob_dens",
                                       *feats]))
        panel = pq.read_table(r.panel(pol), columns=columnas, read_dictionary=["estacion"]).to_pandas()
        calidad, insumos = None, {f"panel_{pol}": r.panel(pol), "manifiesto_pliegues": r.manifiesto_pliegues}
        if con_calidad:
            import calidad_v2
            ruta_qc = calidad_v2.ruta_calidad(r, pol)
            if ruta_qc.exists():
                calidad = calidad_v2.cargar_bandera(pol, panel[["estacion", "ts_utc"]], r)["qc"].to_numpy(dtype=object)
                insumos[f"calidad_{pol}"] = ruta_qc
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

    def codigo_ajuste(self) -> dict:
        return {nombre: sha256_archivo(AQUI / nombre) for nombre in CODIGO_AJUSTE}

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


def hilos_de_firma(ctx: Contexto, tarea) -> int | None:
    return None if tarea is not None and tarea.motor in INVARIANTES_A_HILOS else ctx.hilos


def receta_de(ctx: Contexto, tarea: Tarea) -> dict:
    r = ctx.recetas
    if tarea.motor == "lineales":
        return r["lineales"]
    if tarea.motor == "alertas":
        return r["alertas"]
    return r[tarea.motor]


@functools.lru_cache(maxsize=1)
def _bibliotecas() -> dict:
    """Versiones de las bibliotecas (no cambian dentro de un proceso; la firma se calcula miles de veces)."""
    return versiones_bibliotecas()


def _base_firma(ctx: Contexto, prot: str, pliegue: dict) -> dict:
    return {"schema": SCHEMA_PUNTO, "version_ajuste": VERSION_AJUSTE, "contaminante": ctx.pol,
            "panel": ctx.identidad_panel, "huella_pliegues": ctx.huella_pliegues, "protocolo": prot,
            "k": int(pliegue["k"]), "grupo": pliegue["grupo"], "excluidas": list(pliegue.get("excluidas", [])),
            "exclusion_temporal": pliegue.get("exclusion_temporal"), "codigo_ajuste": ctx.codigo_ajuste(),
            "bibliotecas": _bibliotecas()}


def firma_tarea(ctx: Contexto, prot: str, pliegue: dict, tarea: Tarea, huella_vec: dict, filas: np.ndarray,
                extra: dict | None = None, hilos="ctx") -> str:
    """Identidad de un ajuste. ``hilos="ctx"`` usa los de la corrida (o ninguno si el motor es invariante)."""
    h = hilos_de_firma(ctx, tarea) if hilos == "ctx" else hilos
    return sha256_json({**_base_firma(ctx, prot, pliegue), "tarea": asdict(tarea), "receta": _receta_firma(ctx, tarea),
                        "filas_entrenamiento": {"n": int(len(filas)), "sha256": _sha(filas)}, "vecindario": huella_vec,
                        "calidad": ctx.huella_calidad if tarea.calidad != "todo" else None, "hilos": h, **(extra or {})})


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
    r = tarea.replica
    s = {"permutacion": mv.semilla_permutacion(k, r)}
    if tarea.motor in ("lightgbm", "xgboost"):
        s["motor"] = mv.semilla_motor(ctx.recetas[tarea.motor]["params"]["seed"], r)
    elif tarea.motor in ("random_forest", "mlp", "gp"):
        s["motor"] = mv.semilla_motor(mv.SEMILLA_BASE + int(k), r)
    elif tarea.motor == "alertas":
        s["motor"] = mv.semilla_motor(ctx.recetas["alertas"]["params"]["seed"], r)
    return s


def correr_pliegue(ctx: Contexto, prot: str, pliegue: dict, plan: dict, piloto: bool = False,
                   medidor=None) -> list[dict]:
    """Corre (o reanuda) todas las tareas de un pliegue. Con ``piloto`` no guarda nada y sólo mide tiempos.
    ``medidor`` (``piloto_v2.Medidor``) mide cada fase; por omisión no se mide nada. Escribir exige tener tomado
    un candado de la raíz v2 (lo toma ``main``)."""
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
    deltas: dict[str, float] = {}
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
        if tarea.variante == "huber":
            par = f"{tarea.motor}_l2_original"
            if par not in deltas:
                p = leer_punto(ruta_punto(ctx, prot, k, f"r{r}", par))
                if p is None or "delta_huber" not in p[1].get("info", {}):
                    raise RuntimeError(f"{prot} k={k}: Huber necesita antes el ajuste {par} (δ de sus residuos)")
                deltas[par] = float(p[1]["info"]["delta_huber"])
            extra["delta_huber"] = deltas[par]
        firma = firma_tarea(ctx, prot, pliegue, tarea, huella_vec, filas, extra)
        ruta = ruta_punto(ctx, prot, k, f"r{r}", tarea.id)
        if not piloto and firma_vigente(ruta, firma):
            if tarea.variante == "l2_original":
                deltas[tarea.id] = float(leer_punto(ruta)[1]["info"]["delta_huber"])
            continue
        t1 = time.perf_counter()
        semillas = _semillas(ctx, tarea, k)
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
            with med.fase(**etiq, fase="ajuste"):
                modelo.ajustar(cache["X"], ctx.y[filas], ctx.estaciones_de(filas))
            with med.fase(**etiq, fase="prediccion"):
                salida = modelo.predecir(Xte)
            info = dict(modelo.info)
            if tarea.variante == "l2_original":
                with med.fase(**etiq, fase="delta_huber"):
                    d, info_d = mv.delta_desde_ajuste(modelo, cache["X"], ctx.y[filas])
                deltas[tarea.id] = d
                info.update(info_d)
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
                "tarea": asdict(tarea), "escalas": escalas,
                "filas_prueba": {"n": int(len(prueba)), "sha256": _sha(prueba)},   # el arreglo vive en «vecindario»
                "filas_entrenamiento": {"n": int(len(filas)), "sha256": _sha(filas), "tope": ctx.tope(tarea.tope),
                                        "disponibles": int(len(disp))},
                "huella_vecindario": huella_vec, "semillas": semillas, "info": info, "segundos": segundos,
                "traza": {**ctx.traza_base(), "semillas": semillas}}
        guardar_punto(ruta, arreglos, meta, ctx.rutas)
        log.info("%s %s k=%d %s r%d: %s filas, %.1f s", ctx.pol, prot, k, tarea.id, r, f"{len(filas):,}", segundos)
    if plan["interno"]:
        tiempos += correr_internos(ctx, prot, pliegue, disp, plan["interno"], piloto, medidor=med)
    return tiempos


def definicion_internos(ctx: Contexto, prot: str, pliegue: dict, disp: np.ndarray) -> dict:
    """Filas con tope del pliegue externo (réplica 0) y su reparto en pliegues internos agrupados, con el conjunto
    excluido de cada uno (el externo más las estaciones del pliegue interno)."""
    k = int(pliegue["k"])
    filas = mv.filas_tope(mv.permutacion(disp, mv.semilla_permutacion(k, 0)), ctx.recetas["N_comun"])
    g_est = ctx.grupo_de_estacion(prot)
    est_filas = ctx.vec.js[filas]
    internos = mv.pliegues_internos(np.unique(g_est[est_filas]), k, ctx.recetas["apilado"]["pliegues_internos"])
    externas = [str(s) for s in pliegue.get("excluidas", [])]
    partes = []
    for j, grupos_j in enumerate(internos):
        est_j = np.flatnonzero(np.isin(g_est, grupos_j))
        en_j = np.isin(est_filas, est_j)
        tr_j, te_j = filas[~en_j], filas[en_j]
        excl = sorted(set(externas) | {str(ctx.vec.estaciones[i]) for i in est_j})
        partes.append({"j": j, "tr": tr_j, "te": te_j, "excluidas": excl,
                       "definicion": {"j": j, "grupos": grupos_j, "excluidas": excl, "filas_prueba_sha256": _sha(te_j)}})
    return {"filas": filas, "internos": internos, "partes": partes}


def correr_internos(ctx: Contexto, prot: str, pliegue: dict, disp: np.ndarray, bases, piloto: bool = False,
                    medidor=None) -> list[dict]:
    """Pliegues internos agrupados dentro del entrenamiento con tope del pliegue externo (réplica 0): sirven al
    apilado anidado y a la sensibilidad de la retransformación. Exclusión: la externa más el pliegue interno, en
    las filas y en el vecindario (recalculado para cada pliegue interno)."""
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
            modelo = mv.crear_modelo(motor, ctx.recetas, pv.Variante("l2_log_duan"), 0, replica=0, k=k)
            with med.fase(**etiq, fase="ajuste"):
                modelo.ajustar(X_cache[0], ctx.y[tr_j], ctx.estaciones_de(tr_j))
            with med.fase(**etiq, fase="prediccion"):
                z = modelo.predecir(X_cache[1]).astype("float32")
            segundos = round(time.perf_counter() - t1, 3)
            tiempos.append({"contaminante": ctx.pol, "protocolo": prot, "k": k, "tarea": f"interno_{motor}", "replica": 0,
                            "filas_entrenamiento": int(len(tr_j)), "filas_prueba": int(len(te_j)), "segundos": segundos})
            if piloto:
                continue
            semillas = {**_semillas(ctx, Tarea(motor, motor, "eje_A"), k), "internos": [mv.SEMILLA_BASE, k, mv.SEMILLA_INTERNOS]}
            guardar_punto(ruta, {"filas": te_j, "z": z},
                          {"schema": SCHEMA_PUNTO, "firma": firma, "hilos_firma": hilos_de_firma(ctx, tarea),
                           "hilos": ctx.hilos, "tarea": asdict(tarea), "interno": definicion,
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
            extra = {"delta_huber": deltas[f"{tarea.motor}_l2_original"]} if tarea.variante == "huber" else None
            arr, meta = _leer_vigente(ctx, prot, pliegue, tarea, huella_vec, filas, extra)
            if tarea.variante == "l2_original":
                deltas[tarea.id] = float(meta["info"]["delta_huber"])
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


def consolidar(ctx: Contexto, prot: str, plan: dict, escribir: bool = True, replicas_bootstrap: int = bs.REPLICAS) -> dict:
    """Retransformación, pares comunes, métricas, cuantiles, alertas y bootstrap de un protocolo completo."""
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
            sufijo = "" if r == 0 else f"@r{r}"
            nombres = [f"{m}{sufijo}" for m in mv.MOTORES_EJE_A]
            if all(nm in z for nm in nombres):
                z[f"promedio{sufijo}"] = np.mean(np.column_stack([z[nm].astype("float64") for nm in nombres]), axis=1).astype("float32")
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
    # --- Retransformación primaria de todo lo que está en log ---
    pred, adj, nivel_duan, registro_duan = {}, {}, {}, {}
    est = ctx.vec.js.astype("int64")
    for nm, zz in z.items():
        if nm.startswith("alertas"):
            pred[nm] = mv.salida_alertas(zz)
            continue
        p, a, niv, reg = rt.duan_fuera_de_pliegue(zz, ctx.y, est, ctx.macrozona, ctx.hora_local, pliegue_de_fila,
                                                  excluidas, temporal)
        pred[nm], adj[nm], nivel_duan[nm], registro_duan[nm] = p, a, niv, reg
    for nm, s in salidas.items():
        if escalas[nm] == "original":
            pred[nm] = s
    # --- Sensibilidad: Duan con OOF interno ---
    sens_registro = {}
    if R["internos"]:
        bases = ctx.recetas["apilado"]["bases"]
        for nm in [*bases, "promedio"]:
            if nm not in z:
                continue
            ps = np.full(ctx.n, np.nan, dtype="float32")
            regs = []
            for k, I in R["internos"].items():
                zi = (np.mean(np.column_stack([I["z"][b] for b in bases]), axis=1) if nm == "promedio" else I["z"][nm])
                f = I["filas"]
                tabla = rt.tabla_interna(zi, ctx.y[f], ctx.macrozona[f], ctx.hora_local[f])
                te = np.flatnonzero(pliegue_de_fila == k)
                p, _, _, reg = rt.duan_interno(z[nm][te], ctx.macrozona[te], ctx.hora_local[te], tabla)
                ps[te] = p
                regs += [{"k": int(k), **x} for x in reg]
            pred[f"{nm}~sens"] = ps
            z[f"{nm}~sens"] = z[nm]
            sens_registro[nm] = regs
    # --- Pares comunes ---
    comunes, info_pares = mt.pares_comunes(ctx.y, pred)
    puntuales = [nm for nm in pred if not nm.startswith("alertas") and not nm.endswith(("_q05", "_q95"))]
    cortes = {"peso_vec": mt.cortes_cuartiles(R["vecindario"]["peso_vec"][comunes]),
              "dist_est_km": mt.cortes_cuartiles(R["vecindario"]["dist_est_km"][comunes])}
    subconjuntos = {"todas": comunes}
    if ctx.calidad is not None:
        subconjuntos["validadas"] = comunes & np.isin(ctx.calidad.astype(str), ctx.codigos_qc("evaluacion_validadas"))
    etiqueta_est = lambda c: str(ctx.vec.estaciones[c])  # noqa: E731
    tablas, resumen_niveles, nvs_todas = [], {}, None
    for sub, mascara in subconjuntos.items():
        base = mt.nivel_horario(ctx.y, {nm: pred[nm] for nm in puntuales},
                                {nm: (z[nm] if nm in z and not nm.startswith("alertas") else None) for nm in puntuales},
                                est, ctx.macrozona, ctx.anio, R["vecindario"]["peso_vec"], R["vecindario"]["dist_est_km"],
                                ctx.poblacion, pliegue_de_fila, mascara)
        nvs = mt.niveles(base, ctx.ts_utc[mascara], minimo_horas=int(ctx.cfg["metricas"]["niveles"]["diario"]["minimo_horas"]),
                         minimo_dias=_minimo(ctx.cfg, "mensual"), minimo_meses=_minimo(ctx.cfg, "anual"))
        resumen_niveles[sub] = mt.resumen_niveles(nvs)
        t = mt.tabla_metricas(nvs, cortes, etiqueta_estacion=etiqueta_est, regimen=_regimen(ctx.cfg))
        t.insert(0, "subconjunto", sub)
        tablas.append(t)
        if sub == "todas":
            nvs_todas = nvs
    metricas = pd.concat(tablas, ignore_index=True)
    metricas.insert(0, "protocolo", prot)
    metricas.insert(0, "contaminante", ctx.pol)
    # --- Cuantiles y alertas ---
    cuantiles = []
    for m in mv.MOTORES_PERDIDAS:
        if all(f"{m}_{q}" in pred for q in ("q05", "q50", "q95")):
            c = mt.metricas_cuantiles(ctx.y[comunes], pred[f"{m}_q05"][comunes], pred[f"{m}_q50"][comunes],
                                      pred[f"{m}_q95"][comunes], ctx.macrozona[comunes], ctx.hora_local[comunes])
            c.insert(0, "motor", m)
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
    # --- Bootstrap pareado por bloques y regla de superioridad ---
    boot = bootstrap_protocolo(ctx, prot, nvs_todas, eje_a, replicas_bootstrap)
    # --- Salidas ---
    resultado = {"metricas": metricas, "cuantiles": cuantiles, "alertas": alertas, "bootstrap": boot,
                 "pred": pred, "z": z, "comunes": comunes, "pliegue_de_fila": pliegue_de_fila}
    consolidado = {
        "schema": SCHEMA_CONSOLIDADO, "contaminante": ctx.pol, "protocolo": prot, "etiqueta": ctx.etiqueta,
        "pares": info_pares, "niveles": resumen_niveles, "cortes_soporte": {k: list(map(float, v)) for k, v in cortes.items()},
        "retransformacion": {"primaria": {nm: rt.resumen_niveles(v) for nm, v in nivel_duan.items()},
                             "registro_primaria": registro_duan, "sensibilidad": sens_registro},
        "apilado": {"pesos_por_pliegue": pesos_apilado, "bases": ctx.recetas["apilado"]["bases"] if pesos_apilado else []},
        "plan": [asdict(t) for t in plan["tareas"]], "interno": plan["interno"], "recorte": plan["recorte"],
        "ajustes": R["infos"], "vecindario": R["registros_vecindario"],
        "segundos_consolidacion": round(time.perf_counter() - t0, 2),
        "traza": {**ctx.traza_base(), "semillas": {"bootstrap": bs.semilla_bootstrap(PROTOCOLOS.index(prot)),
                                                     "permutacion": "[42, k] y [42, k, r]"}},
    }
    resultado["consolidado"] = consolidado
    if escribir:
        escribir_consolidado(ctx, prot, resultado, R["vecindario"])
    return resultado


def _regimen(cfg: dict) -> tuple[int, int]:
    c = cfg["metricas"]["desagregaciones"]["regimen_de_predictores"]["criterio"]
    a0, a1 = valor_vigente(c, "metricas.desagregaciones.regimen_de_predictores.criterio")
    return int(a0), int(a1)


def _minimo(cfg: dict, nivel: str) -> int:
    n = cfg["metricas"]["niveles"][nivel]
    clave = "minimo_dias" if nivel == "mensual" else "minimo_meses"
    return int(valor_vigente(n[clave], f"metricas.niveles.{nivel}.{clave}"))


def pares_bootstrap(nombres, eje_a) -> list[tuple[str, str]]:
    """Cada motor puntual contra LightGBM (referencia), todos los pares del eje A con el promedio y el apilado, y
    cada sensibilidad contra su primaria."""
    nombres = [nm for nm in nombres if "@r" not in nm]
    pares = []
    if "lightgbm" in nombres:
        pares += [(nm, "lightgbm") for nm in nombres if nm != "lightgbm" and not nm.endswith("~sens")]
    grupo = [nm for nm in [*eje_a, "promedio", "apilado"] if nm in nombres and nm != "lightgbm"]
    for i, a in enumerate(grupo):
        for b in grupo[i + 1:]:
            pares.append((a, b))
    pares += [(nm, nm.replace("~sens", "")) for nm in nombres if nm.endswith("~sens") and nm.replace("~sens", "") in nombres]
    return list(dict.fromkeys(pares))


def bootstrap_protocolo(ctx: Contexto, prot: str, nvs: dict, eje_a, replicas: int) -> pd.DataFrame:
    semilla = bs.semilla_bootstrap(PROTOCOLOS.index(prot))
    filas = []
    for nombre_nivel, nv in nvs.items():
        motores = list(nv.pred)
        pares = pares_bootstrap(motores, eje_a)
        if not pares:
            continue
        for pond in ("ninguna", "poblacion"):
            w = None if pond == "ninguna" else nv.poblacion
            S = bs.SumasBloques.desde_pares(nv.grupo, nv.obs, {m: nv.pred[m] for m in {x for p in pares for x in p}}, w)
            t = bs.bootstrap_diferencias(S, pares, replicas=replicas, semilla=semilla)
            ruido = ruido_por_semillas(nv, w)
            t = bs.aplicar_regla(t, ruido)
            t.insert(0, "ponderacion", pond)
            t.insert(0, "nivel", nombre_nivel)
            filas.append(t)
    out = pd.concat(filas, ignore_index=True) if filas else pd.DataFrame()
    if len(out):
        out.insert(0, "protocolo", prot)
        out.insert(0, "contaminante", ctx.pol)
    return out


def ruido_por_semillas(nv, w) -> dict:
    """Rango entre las réplicas 0, 1 y 2 de R², RMSE y |NMB| de cada motor que tiene réplicas (§8)."""
    ruido = {}
    base = {nm.split("@r")[0] for nm in nv.pred if "@r" in nm}
    for m in base:
        nombres = [m] + sorted(nm for nm in nv.pred if nm.startswith(f"{m}@r"))
        if len(nombres) < 2:
            continue
        valores = {"r2": [], "rmse": [], "abs_nmb": []}
        for nm in nombres:
            d = mt.metricas(nv.obs, nv.pred[nm], w)
            valores["r2"].append(d["r2"])
            valores["rmse"].append(d["rmse"])
            valores["abs_nmb"].append(abs(d["nmb"]) if np.isfinite(d["nmb"]) else np.nan)
        for est, v in valores.items():
            ruido[(m, est)] = bs.ruido_semillas(v)
    return ruido


def escribir_consolidado(ctx: Contexto, prot: str, res: dict, vecindario: dict) -> dict:
    """OOF y métricas completas en la raíz v2; tablas resumen en ``output_files/modelo_1km_v2`` con su JSON lateral."""
    r = ctx.rutas
    carpeta = ctx.raiz() / prot
    oof = pd.DataFrame({"fila": np.arange(ctx.n, dtype="int64"),
                        "estacion": pd.Categorical.from_codes(ctx.vec.js, categories=[str(s) for s in ctx.vec.estaciones]),
                        "ts_utc": ctx.ts_utc, "obs": ctx.y.astype("float32"), "pliegue": res["pliegue_de_fila"],
                        "par_comun": res["comunes"], "peso_vec_pliegue": vecindario["peso_vec"],
                        "dist_est_km_pliegue": vecindario["dist_est_km"], "obs_vec_pliegue": vecindario["obs_vec"]})
    # El ajuste de Duan y su nivel de respaldo no se repiten fila a fila: están por pliegue × clave en el registro
    # de consolidado.json, y para cada motor en log adj = log1p(pred) − z.
    columnas = {}
    for nm in sorted(res["pred"]):
        columnas[f"pred__{nm}"] = np.asarray(res["pred"][nm], dtype="float32")
        if nm in res["z"] and not nm.endswith("~sens"):
            columnas[f"z__{nm}"] = np.asarray(res["z"][nm], dtype="float32")
    oof = pd.concat([oof, pd.DataFrame(columnas)], axis=1)
    shas = {}
    nombre = f"comparacion_{ctx.etiqueta}_{ctx.pol}_{prot}"
    with candado_escritura(f"{CARPETA}.{ctx.etiqueta}.{ctx.pol}.{prot}.consolidar", rutas=r):
        shas["oof.parquet"] = publicar_parquet(oof, carpeta / "oof.parquet", r)
        shas["metricas.parquet"] = publicar_parquet(res["metricas"], carpeta / "metricas.parquet", r)
        res["consolidado"]["archivos"] = shas
        publicar_json(res["consolidado"], carpeta / "consolidado.json", r)
        resumen = res["metricas"][(res["metricas"]["desagregacion"] != "estacion")
                                  & ~res["metricas"]["motor"].str.contains("@r", regex=False)]
        tablas_csv = {f"{nombre}_metricas.csv": resumen, f"{nombre}_cuantiles.csv": res["cuantiles"],
                      f"{nombre}_alertas.csv": res["alertas"], f"{nombre}_bootstrap.csv": res["bootstrap"]}
        m = res["metricas"]
        con_replica = {x.split("@r")[0] for x in m["motor"].unique() if "@r" in x}
        replicas = m[m["motor"].map(lambda x: x.split("@r")[0] in con_replica) & (m["desagregacion"] == "total")]
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
                       "descripcion": ("Resumen de la comparación v2; la fuente completa (OOF, métricas por estación y "
                                       "registro) está en la raíz v2, comparacion/<etiqueta>/<pol>/<protocolo>/."),
                       "tablas": shas_csv, "fuente": {k: {**r.relativa(carpeta / k), "sha256": v} for k, v in shas.items()},
                       "pares_comunes": res["consolidado"]["pares"]["pares_comunes"],
                       "traza": res["consolidado"]["traza"]}, r.salidas_v2 / f"{nombre}.json", r)
    return shas


# ---------------------------------------------------------------------------
# Piloto de tiempos (§10)
# ---------------------------------------------------------------------------
CRITERIOS_PILOTO = {"entrenamiento": "filas_entrenamiento_disponibles", "prueba": "filas_prueba"}


def pliegues_piloto(pliegues: list[dict], criterio: str = "entrenamiento") -> list[dict]:
    """Los dos pliegues del piloto (§10): el de más filas de entrenamiento disponibles y el de menos (desempate:
    menor k), según el provisional de la configuración (``presupuesto.piloto.eleccion_de_los_pliegues``).
    ``criterio="prueba"`` ordena por filas de prueba, el provisional anterior; en los protocolos sin exclusión
    adicional los dos criterios eligen el mismo par, porque entrenamiento = total − prueba."""
    campo = CRITERIOS_PILOTO[criterio]
    mas = sorted(pliegues, key=lambda f: (-int(f[campo]), int(f["k"])))[0]
    menos = sorted(pliegues, key=lambda f: (int(f[campo]), int(f["k"])))[0]
    return [mas] + ([menos] if int(menos["k"]) != int(mas["k"]) else [])


def estimar_presupuesto(tiempos: pd.DataFrame, planes: dict, conteos: dict, umbral_h: float) -> dict:
    """Estimación gruesa: media por pliegue de cada tarea medida × pliegues del protocolo, por contaminante y
    protocolo, para cada nivel de recorte (0 … 3) en el orden de §10. Las tareas no medidas cuentan 0. El piloto
    de §10 usa la extrapolación por fase de ``piloto_v2.extrapolar``, que escala con las filas de cada pliegue."""
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
def _opciones(args) -> Opciones:
    return Opciones(motores=tuple(args.motores), perdidas=not args.sin_perdidas, alertas=not args.sin_alertas,
                    eje_b=not args.sin_eje_b, curvas=not args.sin_curvas, semillas=not args.sin_semillas,
                    apilado=not args.sin_apilado, calidad=not args.sin_calidad, recorte=int(args.recorte))


def _seleccion(pliegues: list[dict], ks, parte) -> list[dict]:
    out = [f for f in pliegues if ks is None or int(f["k"]) in ks]
    if parte:
        i, m = (int(x) for x in parte.split("/"))
        out = [f for f in out if int(f["k"]) % m == i]
    return out


def anotar_recorte(r: RutasV2, recorte: int, etiqueta: str) -> None:
    """Deja el recorte del presupuesto en la bitácora del manifiesto de pliegues (§10), una sola vez."""
    if recorte <= 0:
        return
    import pliegues_v2
    m = leer_json(r.manifiesto_pliegues) or {}
    ya = any(e.get("evento") == "recorte_presupuesto" and e.get("recorte") == recorte and e.get("etiqueta") == etiqueta
             for e in m.get("bitacora", []))
    if not ya:
        orden = cargar_config(r)["presupuesto"]["orden_de_recortes"]
        pliegues_v2.anotar_bitacora({"evento": "recorte_presupuesto", "recorte": recorte, "etiqueta": etiqueta,
                                     "aplicados": [x["recorte"] for x in orden if x["orden"] <= recorte]}, r)


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
    ap.add_argument("accion", choices=("plan", "piloto", "correr", "estado", "consolidar"))
    ap.add_argument("--contaminantes", nargs="+", default=["pm25", "no2"], choices=("pm25", "no2"))
    ap.add_argument("--protocolos", nargs="+", default=list(PROTOCOLOS), choices=PROTOCOLOS)
    ap.add_argument("--pliegues", nargs="*", type=int, default=None, help="k de los pliegues (todos si se omite)")
    ap.add_argument("--parte", default=None, help="i/m: sólo los pliegues con k %% m == i (procesos en paralelo)")
    ap.add_argument("--etiqueta", default=ETIQUETA)
    ap.add_argument("--hilos", type=int, default=None, help="hilos por proceso (máximo operacion.hilos_maximos)")
    ap.add_argument("--motores", nargs="+", default=list(mv.MOTORES_EJE_A), choices=mv.MOTORES_EJE_A)
    ap.add_argument("--recorte", type=int, default=0, choices=(0, 1, 2, 3), help="recortes de §10 en orden")
    for nombre in ("perdidas", "alertas", "eje-b", "curvas", "semillas", "apilado", "calidad"):
        ap.add_argument(f"--sin-{nombre}", action="store_true")
    ap.add_argument("--replicas-bootstrap", type=int, default=bs.REPLICAS)
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
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
    r = rutas_v2()
    cfg = cargar_config(r)
    op = _opciones(args)
    recetas = mv.recetas_de(cfg, args.hilos)
    if args.accion == "piloto":
        import piloto_v2
        return piloto_v2.ejecutar(args, r, cfg)
    if args.accion == "plan":
        man = leer_json(r.manifiesto_pliegues)
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
    if args.accion == "correr":
        anotar_recorte(r, op.recorte, args.etiqueta)
    for pol in args.contaminantes:
        ctx = Contexto.desde_disco(pol, r, cfg, etiqueta=args.etiqueta, hilos=args.hilos, con_calidad=op.calidad)
        for prot in args.protocolos:
            plan = plan_protocolo(ctx.recetas, prot, op, calidad_disponible=ctx.calidad is not None)
            if args.accion == "consolidar":
                res = consolidar(ctx, prot, plan, escribir=True, replicas_bootstrap=args.replicas_bootstrap)
                print(f"{pol} {prot}: consolidado, {res['consolidado']['pares']['pares_comunes']:,} pares comunes")
                continue
            for f in _seleccion(ctx.pliegues(prot), args.pliegues, args.parte):
                nombre = f"{CARPETA}.{args.etiqueta}.{pol}.{prot}.k{int(f['k']):03d}"
                try:
                    with candado_escritura(nombre, rutas=r):
                        correr_pliegue(ctx, prot, f, plan)
                except CandadoOcupado:
                    log.info("%s %s k=%s: otro proceso tiene el pliegue; sigo", pol, prot, f["k"])
        del ctx
    return 0


if __name__ == "__main__":
    sys.exit(main())
