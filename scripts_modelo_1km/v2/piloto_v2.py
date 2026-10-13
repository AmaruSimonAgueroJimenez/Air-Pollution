"""Piloto de tiempos de la comparación v2 (``DISENO_AMBIENTAL_V2.md`` §10): mide, no evalúa.

«Un tiempo no es un resultado» (§10). El piloto ajusta y predice con el mismo código de la corrida completa
(``correr_v2.correr_pliegue`` en modo piloto), pero no guarda predicciones ni calcula, guarda o muestra ninguna
métrica de desempeño. Registra sólo tiempo de pared, tiempo de CPU, memoria máxima y el tiempo de recálculo del
vecindario, fase por fase, así que no puede informar la elección del motor (§9). La MLP calcula internamente su
R² de validación agrupada para la parada temprana, porque es parte de su receta (§3), pero el piloto lo descarta
junto con el resto de ``modelo.info``.

Se lanza con ``python -B scripts_modelo_1km/v2/correr_v2.py piloto ...``; este módulo no tiene consola propia.

**Alcance** (instrucción de la etapa; ``config_v2.json`` → ``presupuesto.piloto.eleccion_de_los_pliegues``):

* por contaminante y protocolo, dos pliegues: el de más filas de entrenamiento disponibles y el de menos
  (desempate: menor k), con el recálculo del vecindario y los cuatro motores del eje A con el N común (750.000);
* en el pliegue de LRO con más filas de entrenamiento, los puntos de la curva de aprendizaje de LightGBM y XGBoost
  que no son el N común (300.000, 1,5 M y todas las filas) y RF con el punto más alto de su curva (1,5 M);
* con ``--calibrar-familias``, en el otro pliegue de LRO (el de más filas de prueba), una pasada de las familias
  que ese alcance no cubre (pérdidas de §6, alertas y eje B), para que la extrapolación no las suponga a ciegas;
* una vez por contaminante, la carga del contexto (panel, vecindario base y bandera de calidad) y la máscara de
  calidad de las variantes de §7.

**Medición** (``Medidor``), por fase: pared (``perf_counter``), CPU del proceso con todos sus hilos
(``process_time``), memoria residente (muestreo cada 0,2 s con psutil, con el pico de la fase, y el máximo del
proceso según ``getrusage``), CPU del resto de la máquina en la misma ventana (CPU ocupada del sistema menos la
propia) y carga media. Lo último deja constancia de la contención con el otro trabajo pesado que corre en paralelo:
**los tiempos de pared pueden estar sobreestimados**. Por eso el plan informa también una estimación con menos
contención, en la que cada fase vale ``CPU / p90`` del paralelismo (CPU/pared) de su tipo de fase y motor, y lista
los ajustes medidos con contención fuerte (otros procesos ≥ 50 % de la máquina). ``--remedir-contaminadas 0.5`` los
vuelve a medir; si una fase se midió más de una vez, la extrapolación usa la medición con menos contención.

**Horas de máquina**: horas de pared de un proceso con 12 hilos, que ocupa la máquina (16 núcleos lógicos, de los
cuales 12 de rendimiento). Paralelizar por pliegue (``--parte``) baja la duración, no las horas de máquina.

**Extrapolación** (``ModeloTiempos`` y ``costo_pliegue``): cada pliegue del manifiesto (con sus filas de
entrenamiento y de prueba) y cada tarea del plan de ``correr_v2.plan_protocolo`` se cuentan con el costo de sus
fases, tal como las ejecuta ``correr_pliegue``:

* vecindario: media de los dos pliegues medidos del protocolo;
* permutación, filas, matriz de entrenamiento (una por réplica × tope × calidad) y matriz de prueba: rectas
  ``a + b·filas`` ajustadas a todas las fases medidas del contaminante;
* ajuste del eje A con el N común: media de los dos pliegues del protocolo; con otro N (curvas y pliegues
  internos), esa media por el cociente de la curva medida en el pliegue de LRO (interpolación log–log; en la MLP,
  proporcional a N, porque el piloto no mide su curva);
* predicción: recta ``a + b·filas de prueba`` por motor;
* semillas y variantes de calidad: como el eje A (mismo motor y N, otra permutación o filtro, matriz propia);
* pérdidas y alertas: el ajuste y la predicción del motor por el cociente medido en la calibración frente al eje A
  del mismo pliegue (sin calibración, factores supuestos de ``SUPUESTOS``); δ de Huber con su tasa por fila;
* eje B: GP y LME con su ajuste medido y una tasa de predicción por fila; GWR, RK e IDW, costo medido por pliegue
  más su construcción, una vez por contaminante;
* pliegues internos (apilado y sensibilidad, LRO y BLQ-75; no se miden): ``n = min(5, grupos − 1)`` pliegues con
  ``(n − 1)/n`` del N común para entrenar y ``1/n`` para predecir, más un recálculo del vecindario cada uno;
* la carga del contexto, una vez por contaminante (un proceso por contaminante), y el sobrecosto fuera de las
  fases medidas (firmas, permutaciones de pliegue), como fracción medida del total por pliegue.

No entran la consolidación (retransformación, métricas y bootstrap de 2.000 réplicas) ni la escritura de los puntos
de control: no se miden aquí y se informan como no incluidas.

Sensibilidades del plan: ``horas_media_global`` (el ajuste del eje A con la media de los diez pliegues medidos por
motor, más estable para la MLP, cuyas épocas varían de un pliegue a otro), ``horas_sin_contencion_fuerte`` (sólo
los ajustes con contención fuerte corregidos con CPU / p90) y ``horas_menos_contencion`` (todas las fases).

**Recortes** (§10): si el total supera unas 120 horas de máquina, se aplican en orden 1) semillas sólo en LRO,
2) curvas sólo en LRO y 3) MLP sólo en LRO y BLQ-75, hasta quedar bajo el umbral. Si ni con los tres se llega, el
contrato no prevé un cuarto: se aplican los tres y el exceso queda para el autor (enmienda). La decisión usa la
estimación medida (conservadora) y el plan dice si alguna sensibilidad la cambiaría. Todo recorte queda en la
bitácora del plan y en la del manifiesto de pliegues.

Salidas:

* ``<raíz v2>/piloto_tiempos/mediciones.json``: una fila por fase medida, por sesión con su traza; reanudable;
* ``<raíz v2>/plan_corrida_v2.json``: la estimación por nivel de recorte, la bitácora de recortes y el plan
  resultante, con su traza;
* ``output_files/modelo_1km_v2/comparacion_piloto_tiempos.csv`` y ``comparacion_piloto.json`` (tablas pequeñas);
* el evento ``recorte_presupuesto`` en la bitácora de ``pliegues_v2.json`` si hay recorte.
"""
from __future__ import annotations

import contextlib
import gc
import hashlib
import logging
import math
import os
import platform
import resource
import sys
import threading
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correr_v2 as cr  # noqa: E402
import motores_v2 as mv  # noqa: E402
from _rutas_v2 import (  # noqa: E402
    RutasV2, ahora_utc, candado_escritura, leer_json, publicar_bytes, publicar_json, renombrar,
)
from _traza_v2 import sha256_archivo, traza  # noqa: E402
from pliegues_v2 import PROTOCOLOS  # noqa: E402

log = logging.getLogger("modelo_1km_v2.piloto")

SCHEMA_MEDICIONES = "airpollution.modelo-1km-v2.piloto-mediciones.v1"
SCHEMA_PLAN = "airpollution.modelo-1km-v2.plan-corrida.v1"
CARPETA = "piloto_tiempos"
NOMBRE_MEDICIONES = "mediciones.json"
NOMBRE_PLAN = "plan_corrida_v2.json"
TABLA_CSV = "comparacion_piloto_tiempos.csv"
TABLA_JSON = "comparacion_piloto.json"
CANDADO_MEDIR = "piloto_tiempos"
CANDADO_PLAN = "plan_corrida"
CONTAMINANTES = ("pm25", "no2")
INTERVALO_MUESTREO_S = 0.2
VENTANA_PROCESOS_S = 1.0             # muestreo de los procesos más activos al abrir y cerrar cada sesión
PARALELISMO_CUANTIL = 0.9            # «menos contención»: CPU / p90 del paralelismo de su tipo de fase y motor
PARALELISMO_MIN_SEGUNDOS = 1.0       # fases más cortas no informan el paralelismo de referencia
CONTENCION_FUERTE = 0.5              # otros procesos usaron al menos la mitad de la máquina durante la fase
CONTENCION_MIN_SEGUNDOS = 5.0        # sólo se juzga la contención de ajustes de al menos 5 s
CLAVE_FASE = ("contaminante", "protocolo", "k", "tarea", "replica", "fase")
FAMILIAS_CALIBRACION = ("perdidas", "alertas", "eje_B")
FASES_TAREA = ("ajuste", "prediccion", "ajuste_prediccion")

# Factores supuestos, sólo para las familias que no se calibran (sin --calibrar-familias). Cocientes frente al eje
# A del mismo motor (ajuste, predicción) o costos absolutos en segundos. Se informan como supuestos en el plan.
SUPUESTOS = {
    "perdidas": {"l2_original": (1.0, 1.0), "huber": (1.0, 1.0), "q05": (1.3, 1.0), "q50": (1.3, 1.0),
                 "q95": (1.3, 1.0),
                 "nota": "mismo motor, receta y N; los cuantílicos renuevan las hojas con el cuantil de los residuos "
                         "(LightGBM objective=quantile, XGBoost reg:quantileerror): +30 % supuesto"},
    "alertas": {"factor": (900 / 800 / 0.8 * 1.3, 900 / 800),
                "nota": "LightGBM cuantílico: 900/800 rondas, sin bagging (1/0,8 filas por árbol) y renovación de "
                        "hojas (+30 %)"},
    "delta_tasa_por_fila": {"lightgbm": None, "xgboost": None,
                            "nota": "predicción in-sample sobre las N filas: la tasa de predicción del motor"},
    "gp": {"ajuste_s": 30.0, "tasa_prediccion_s_por_fila": 2e-5, "nota": "orden de magnitud, sin medir"},
    "lme": {"ajuste_s": 120.0, "tasa_prediccion_s_por_fila": 1e-7, "nota": "orden de magnitud, sin medir"},
    "lineales": {"por_pliegue_s": 5.0, "construccion_s": 30.0, "nota": "orden de magnitud, sin medir"},
    "mascara_calidad_s": {"valor": 3.0, "nota": "np.isin sobre la bandera de todo el panel, sin medir"},
}


def sin_nan(o):
    """Copia con NaN e infinitos convertidos en None (el JSON estricto no los admite)."""
    if isinstance(o, dict):
        return {k: sin_nan(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [sin_nan(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    return o


def mb(b) -> float | None:
    return None if b is None or b < 0 else round(float(b) / 2 ** 20, 1)


def maxrss_proceso() -> int:
    """Memoria residente máxima del proceso en bytes (``ru_maxrss`` viene en bytes en macOS y en KiB en Linux)."""
    m = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(m if platform.system() == "Darwin" else m * 1024)


# ---------------------------------------------------------------------------
# Medidor
# ---------------------------------------------------------------------------
class Medidor:
    """Mide cada fase (``with medidor.fase(**etiquetas) as reg``): pared, CPU del proceso (todos los hilos), memoria
    residente (pico por muestreo), CPU del resto de la máquina y carga media. Las fases pueden anidarse. Cada fase
    cerrada agrega una fila a ``self.filas`` y llama a ``al_cerrar(fila)``. No mira lo que hace la fase."""

    def __init__(self, sesion: int = 0, intervalo_s: float = INTERVALO_MUESTREO_S, al_cerrar=None):
        import psutil
        self._ps = psutil
        self.proc = psutil.Process()
        self.sesion = int(sesion)
        self.intervalo = float(intervalo_s)
        self.al_cerrar = al_cerrar
        self.filas: list[dict] = []
        self.n_cpu = int(psutil.cpu_count(logical=True) or os.cpu_count() or 1)
        self._activas: list[dict] = []
        self._cerrojo = threading.Lock()
        self._fin = threading.Event()
        self._hilo: threading.Thread | None = None

    def __enter__(self) -> "Medidor":
        self._fin.clear()
        self._hilo = threading.Thread(target=self._muestrear, name="medidor-piloto", daemon=True)
        self._hilo.start()
        return self

    def __exit__(self, *exc) -> bool:
        self._fin.set()
        if self._hilo is not None:
            self._hilo.join(timeout=5)
        return False

    def _rss(self) -> int:
        try:
            return int(self.proc.memory_info().rss)
        except Exception:  # noqa: BLE001
            return -1

    def _muestrear(self) -> None:
        while not self._fin.wait(self.intervalo):
            rss, carga = self._rss(), os.getloadavg()[0]
            with self._cerrojo:
                for a in self._activas:
                    a["rss_pico"] = max(a["rss_pico"], rss)
                    a["carga_max"] = max(a["carga_max"], carga)
                    a["muestras"] += 1

    def _cpu_ocupada_sistema(self) -> float:
        """CPU·s ocupados de toda la máquina desde el arranque (todas las CPU lógicas)."""
        t = self._ps.cpu_times()
        total = float(sum(t))
        return total - float(t.idle) - float(getattr(t, "iowait", 0.0))

    @contextlib.contextmanager
    def fase(self, **etiquetas):
        reg = dict(etiquetas)
        estado = {"rss_pico": self._rss(), "carga_max": os.getloadavg()[0], "muestras": 0}
        rss0, max0, carga0 = estado["rss_pico"], maxrss_proceso(), estado["carga_max"]
        inicio = ahora_utc()
        oc0, c0, t0 = self._cpu_ocupada_sistema(), time.process_time(), time.perf_counter()
        with self._cerrojo:
            self._activas.append(estado)
        error = None
        try:
            yield reg
        except BaseException as exc:
            error = f"{type(exc).__name__}: {str(exc)[:200]}"
            raise
        finally:
            t1, c1, oc1 = time.perf_counter(), time.process_time(), self._cpu_ocupada_sistema()
            with self._cerrojo:                       # por identidad: dos fases anidadas pueden tener el mismo estado
                self._activas = [x for x in self._activas if x is not estado]
            rss1, max1 = self._rss(), maxrss_proceso()
            pared, cpu = t1 - t0, c1 - c0
            otros = max((oc1 - oc0) - cpu, 0.0)
            fila = {"sesion": self.sesion, **reg, "inicio_utc": inicio, "segundos_pared": round(pared, 4),
                    "segundos_cpu": round(cpu, 4), "paralelismo": round(cpu / pared, 3) if pared > 0 else None,
                    "cpu_otros_s": round(otros, 3),
                    "fraccion_maquina_otros": round(otros / (self.n_cpu * pared), 4) if pared > 0 else None,
                    "carga_1min_inicio": round(carga0, 2),
                    "carga_1min_max": round(max(estado["carga_max"], os.getloadavg()[0]), 2),
                    "rss_inicio_mb": mb(rss0), "rss_fin_mb": mb(rss1), "rss_pico_mb": mb(max(estado["rss_pico"], rss1)),
                    "maxrss_proceso_mb": mb(max1), "nuevo_maximo_proceso": bool(max1 > max0),
                    "muestras_memoria": int(estado["muestras"])}
            if error:
                fila["error"] = error
            self.filas.append(fila)
            if self.al_cerrar is not None:
                try:
                    self.al_cerrar(fila)
                except Exception as exc:  # noqa: BLE001  (no tapar el error de la fase)
                    log.error("no se pudo registrar la medición: %s", exc)


# ---------------------------------------------------------------------------
# Registro reanudable de mediciones
# ---------------------------------------------------------------------------
class Registro:
    """``<raíz v2>/piloto_tiempos/mediciones.json``: sesiones (con su traza) y una fila por fase medida. Se
    reescribe de forma atómica tras cada fase (exige el candado). ``rehacer`` respalda el anterior y empieza de
    cero."""

    def __init__(self, r: RutasV2, rehacer: bool = False):
        self.r = r
        self.ruta = r.raiz_v2 / CARPETA / NOMBRE_MEDICIONES
        previo = leer_json(self.ruta)
        if previo is not None and rehacer:
            sello = ahora_utc().replace(":", "").replace("-", "")
            renombrar(self.ruta, self.ruta.with_name(f"mediciones_reemplazado_{sello}.json"), r)
            previo = None
        if previo is not None and previo.get("schema") != SCHEMA_MEDICIONES:
            raise SystemExit(f"{self.ruta.name}: esquema desconocido {previo.get('schema')!r}")
        self.doc = previo or {
            "schema": SCHEMA_MEDICIONES,
            "descripcion": ("Piloto de tiempos de la comparación v2 (§10). Una fila por fase medida: tiempo de "
                            "pared, CPU, memoria y contención. Sin predicciones ni métricas de desempeño: un tiempo "
                            "no es un resultado."),
            "sesiones": [], "mediciones": []}

    @property
    def mediciones(self) -> list[dict]:
        return self.doc["mediciones"]

    def abrir_sesion(self, info: dict) -> int:
        self.doc["sesiones"].append({"sesion": len(self.doc["sesiones"]), **info})
        self.guardar()
        return len(self.doc["sesiones"]) - 1

    def cerrar_sesion(self, sesion: int, info: dict) -> None:
        self.doc["sesiones"][sesion].update(info)
        self.guardar()

    def agregar(self, fila: dict) -> None:
        self.doc["mediciones"].append(fila)
        self.guardar()

    def guardar(self) -> str:
        return publicar_json(self.doc, self.ruta, self.r)


def _nulo(v) -> bool:
    """None o NaN (las filas que pasan por un DataFrame traen NaN donde falta una clave)."""
    return v is None or (isinstance(v, float) and math.isnan(v))


def tareas_medidas(mediciones) -> set[tuple]:
    """(contaminante, protocolo, k, tarea, réplica) con su ajuste y su predicción medidos sin error."""
    fases = defaultdict(set)
    for m in mediciones:
        if not _nulo(m.get("error")) or m.get("fase") not in FASES_TAREA or _nulo(m.get("familia")):
            continue
        rep = 0 if _nulo(m.get("replica")) else int(m["replica"])
        fases[(m["contaminante"], m["protocolo"], int(m["k"]), m["tarea"], rep)].add(m["fase"])
    return {c for c, f in fases.items() if {"ajuste", "prediccion"} <= f or "ajuste_prediccion" in f}


def fases_medidas(mediciones, fase: str) -> set[tuple]:
    """(contaminante, protocolo, k) con la fase medida sin error (protocolo y k None si la fase es del contaminante)."""
    out = set()
    for m in mediciones:
        if m.get("fase") == fase and _nulo(m.get("error")):
            k, prot = m.get("k"), m.get("protocolo")
            out.add((m.get("contaminante"), None if _nulo(prot) else prot, None if _nulo(k) else int(k)))
    return out


def tareas_contaminadas(mediciones, umbral: float = CONTENCION_FUERTE,
                        minimo_s: float = CONTENCION_MIN_SEGUNDOS) -> set[tuple]:
    """Tareas cuyo ajuste (de al menos ``minimo_s``) sólo se midió con contención fuerte: otros procesos usaron al
    menos ``umbral`` de la máquina en todas sus mediciones. ``--remedir-contaminadas`` las vuelve a medir."""
    fracciones = defaultdict(list)
    for m in mediciones:
        if m.get("fase") != "ajuste" or not _nulo(m.get("error")) or _nulo(m.get("familia")):
            continue
        if float(m.get("segundos_pared") or 0.0) < minimo_s:
            continue
        rep = 0 if _nulo(m.get("replica")) else int(m["replica"])
        fr = m.get("fraccion_maquina_otros")
        fracciones[(m["contaminante"], m["protocolo"], int(m["k"]), m["tarea"], rep)].append(
            0.0 if _nulo(fr) else float(fr))
    return {c for c, v in fracciones.items() if min(v) >= umbral}


def menos_contaminada(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por fase (contaminante, protocolo, k, tarea, réplica, fase): si se midió más de una vez (por
    reanudación o remedición), la de menor fracción de la máquina usada por otros procesos."""
    if not len(df):
        return df
    d = df.copy()
    for c in CLAVE_FASE:
        if c not in d:
            d[c] = None
    clave = d[list(CLAVE_FASE)].astype(str).agg("|".join, axis=1)
    orden = pd.to_numeric(d.get("fraccion_maquina_otros"), errors="coerce").fillna(0.0)
    elegido = orden.groupby(clave).idxmin()
    return d.loc[sorted(elegido.to_numpy())]


# ---------------------------------------------------------------------------
# Alcance del piloto
# ---------------------------------------------------------------------------
def topes_curva_piloto(recetas: dict) -> dict[str, list]:
    """Puntos de la curva de aprendizaje que mide el piloto: LightGBM y XGBoost, todos los de la curva salvo el N
    común (que mide el eje A); RF, sólo el más alto de la suya (1,5 M)."""
    N = recetas["N_comun"]
    out = {m: [t for t in recetas["curvas"][m] if t != N] for m in ("lightgbm", "xgboost")}
    rf = [t for t in recetas["curvas"]["random_forest"] if t is not None and t != N]
    out["random_forest"] = [max(rf)] if rf else []
    return out


def pliegues_lro(elegidos: list[dict]) -> tuple[int, int]:
    """(k de las curvas, k de la calibración) entre los pliegues de LRO del piloto: las curvas en el de más filas de
    entrenamiento (su «todas» cubre el máximo de LRO); la calibración en el de más filas de prueba (mide mejor las
    tasas de predicción del eje B)."""
    curvas = max(elegidos, key=lambda f: (int(f["filas_entrenamiento_disponibles"]), -int(f["k"])))
    calib = max(elegidos, key=lambda f: (int(f["filas_prueba"]), -int(f["k"])))
    return int(curvas["k"]), int(calib["k"])


def seleccion(manifiesto: dict, pol: str, protocolos, criterio: str = "entrenamiento") -> dict[str, list[dict]]:
    """Los dos pliegues del piloto por protocolo (``correr_v2.pliegues_piloto``)."""
    pr = manifiesto["contaminantes"][pol]["protocolos"]
    return {prot: cr.pliegues_piloto(pr[prot]["pliegues"], criterio) for prot in protocolos}


def tareas_piloto(recetas: dict, prot: str, k: int, k_curvas: int | None, k_calib: int | None,
                  calibrar: bool) -> list:
    """Tareas del piloto en un pliegue, tomadas del plan completo de ``plan_protocolo`` (mismas definiciones)."""
    completo = cr.plan_protocolo(recetas, "LRO", cr.Opciones(), calidad_disponible=False)["tareas"]
    por_id = {(t.id, t.replica): t for t in completo}
    tareas = [por_id[(m, 0)] for m in mv.MOTORES_EJE_A]
    if prot == "LRO" and k == k_curvas:
        for motor, topes in topes_curva_piloto(recetas).items():
            tareas += [por_id[(f"{motor}_n{'todas' if t is None else t}", 0)] for t in topes]
    if calibrar and prot == "LRO" and k == k_calib:
        tareas += [t for t in completo if t.replica == 0 and t.familia in FAMILIAS_CALIBRACION]
    return tareas


def pendientes(tareas: list, hechas: set, pol: str, prot: str, k: int) -> list:
    """Las tareas aún sin medir; Huber arrastra a su ajuste cuadrático, que le da δ en la misma llamada."""
    pend = [t for t in tareas if (pol, prot, int(k), t.id, t.replica) not in hechas]
    for t in list(pend):
        if t.variante == "huber":
            par = next(x for x in tareas if x.id == f"{t.motor}_l2_original" and x.replica == t.replica)
            if par not in pend:
                pend.append(par)
    return pend


# ---------------------------------------------------------------------------
# Medición
# ---------------------------------------------------------------------------
def procesos_activos(n: int = 8, ventana_s: float | None = None) -> list[dict]:
    """Los procesos que más CPU usan (sólo el nombre, nunca la línea de órdenes, que puede tener rutas)."""
    import psutil
    ventana_s = VENTANA_PROCESOS_S if ventana_s is None else ventana_s
    yo = os.getpid()
    procs = []
    for p in psutil.process_iter(["name"]):
        try:
            p.cpu_percent(None)
            procs.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    time.sleep(ventana_s)
    filas = []
    for p in procs:
        try:
            if p.pid != yo:
                filas.append({"nombre": p.info.get("name"), "cpu_pct": round(p.cpu_percent(None), 1)})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    filas.sort(key=lambda d: -d["cpu_pct"])
    return [f for f in filas[:n] if f["cpu_pct"] > 0]


def info_maquina() -> dict:
    import psutil
    vm = psutil.virtual_memory()
    return {"cpu_logicas": psutil.cpu_count(logical=True), "cpu_fisicas": psutil.cpu_count(logical=False),
            "memoria_total_gb": round(vm.total / 2 ** 30, 1), "memoria_disponible_gb": round(vm.available / 2 ** 30, 1),
            "carga_media_1_5_15": [round(x, 2) for x in os.getloadavg()], "procesos_mas_activos": procesos_activos(),
            "sistema": platform.platform(), "maquina": platform.machine()}


def insumos_piloto(r: RutasV2, contaminantes) -> dict:
    import calidad_v2
    ins = {"manifiesto_pliegues": r.manifiesto_pliegues} if r.manifiesto_pliegues.exists() else {}
    for pol in contaminantes:
        if r.panel(pol).exists():
            ins[f"panel_{pol}"] = r.panel(pol)
        if calidad_v2.ruta_calidad(r, pol).exists():
            ins[f"calidad_{pol}"] = calidad_v2.ruta_calidad(r, pol)
    return ins


SEMILLAS_PILOTO = {"permutacion": "[42, k] (réplica 0, §4)",
                   "motores": "las de la receta (§3): LightGBM, XGBoost y alertas 42; RF y MLP 42 + k; GP 42 + k",
                   "nota": "el piloto sólo mide tiempos; las semillas fijan qué filas y qué ajuste se cronometran"}


def medir(r: RutasV2, cfg: dict, contaminantes, protocolos, hilos: int, criterio: str = "entrenamiento",
          calibrar: bool = False, rehacer: bool = False, crear_contexto=None,
          manifiesto: dict | None = None, remedir_si_otros: float | None = None) -> Registro:
    """Mide lo que falte del alcance (reanudable). Con ``remedir_si_otros``, vuelve a medir las tareas cuyo ajuste
    sólo se midió con otros procesos ocupando al menos esa fracción de la máquina (la extrapolación usa la medición
    con menos contención). ``crear_contexto(pol)`` sirve a las pruebas; por omisión, ``Contexto.desde_disco`` con
    la bandera de calidad."""
    recetas = mv.recetas_de(cfg, hilos)
    man = manifiesto if manifiesto is not None else leer_json(r.manifiesto_pliegues)
    if man is None:
        raise SystemExit("Falta el manifiesto de pliegues")
    if crear_contexto is None:
        def crear_contexto(pol):
            return cr.Contexto.desde_disco(pol, r, cfg, etiqueta=cr.ETIQUETA, hilos=hilos, con_calidad=True)
    with candado_escritura(CANDADO_MEDIR, rutas=r):
        reg = Registro(r, rehacer=rehacer)
        hechas = tareas_medidas(reg.mediciones)
        remedir = tareas_contaminadas(reg.mediciones, remedir_si_otros) if remedir_si_otros is not None else set()
        hechas -= remedir
        vecs = fases_medidas(reg.mediciones, "vecindario")
        ctxs, mascaras = fases_medidas(reg.mediciones, "contexto"), fases_medidas(reg.mediciones, "mascara_calidad")
        argumentos = {"contaminantes": list(contaminantes), "protocolos": list(protocolos), "hilos": int(hilos),
                      "criterio_pliegues": criterio, "calibrar_familias": bool(calibrar), "rehacer": bool(rehacer),
                      "remedir_si_otros": remedir_si_otros,
                      "tareas_a_remedir": sorted("/".join(map(str, t)) for t in remedir
                                                 if t[0] in contaminantes and t[1] in protocolos)}
        sesion = reg.abrir_sesion({"inicio_utc": ahora_utc(), "argumentos": argumentos,
                                   "maquina_al_inicio": info_maquina(),
                                   "traza": traza(insumos_piloto(r, contaminantes), SEMILLAS_PILOTO, hilos, rutas=r,
                                                  parametros=argumentos)})
        t0 = time.perf_counter()

        def avisar(fila):
            reg.agregar(fila)
            if fila.get("fase") in ("vecindario", "ajuste", "prediccion", "ajuste_prediccion", "contexto",
                                    "construccion_lineales", "pliegue"):
                error = f" ERROR {fila['error']}" if "error" in fila else ""
                log.info("%s %s k=%s %s %s: %.1f s pared, %.1f s CPU, pico %s MB, otros %.0f %%%s",
                         fila.get("contaminante"), fila.get("protocolo", "-"), fila.get("k", "-"), fila.get("tarea"),
                         fila["fase"], fila["segundos_pared"], fila["segundos_cpu"], fila["rss_pico_mb"],
                         100 * (fila.get("fraccion_maquina_otros") or 0), error)

        with Medidor(sesion, al_cerrar=avisar) as med:
            for pol in contaminantes:
                eleg = seleccion(man, pol, protocolos, criterio)
                k_cur, k_cal = pliegues_lro(eleg["LRO"]) if "LRO" in eleg else (None, None)
                trabajo = []
                for prot in protocolos:
                    for f in eleg[prot]:
                        k = int(f["k"])
                        tareas = tareas_piloto(recetas, prot, k, k_cur, k_cal, calibrar)
                        pend = pendientes(tareas, hechas, pol, prot, k)
                        if pend or (pol, prot, k) not in vecs:
                            trabajo.append((prot, k, pend))
                if not trabajo and (pol, None, None) in ctxs:
                    log.info("%s: todo medido", pol)
                    continue
                with med.fase(contaminante=pol, tarea="contexto", fase="contexto") as m:
                    ctx = crear_contexto(pol)
                    m.update(filas_panel=int(ctx.n), con_calidad=ctx.calidad is not None)
                if ctx.calidad is not None and (pol, None, None) not in mascaras:
                    with med.fase(contaminante=pol, tarea="mascara_calidad", fase="mascara_calidad",
                                  filas_panel=int(ctx.n)):
                        ctx.mascara_calidad("solo_validado")
                por_k = {prot: {int(f["k"]): f for f in ctx.pliegues(prot)} for prot in protocolos}
                for prot, k, pend in trabajo:
                    f = por_k[prot][k]
                    log.info("%s %s k=%d (%s): %d tareas — %s", pol, prot, k, f["grupo"], len(pend),
                             ", ".join(t.id for t in pend) or "sólo vecindario")
                    with med.fase(contaminante=pol, protocolo=prot, k=k, tarea="pliegue", fase="pliegue",
                                  filas_disponibles=int(f["filas_entrenamiento_disponibles"]),
                                  filas_prueba=int(f["filas_prueba"]), n_tareas=len(pend)):
                        cr.correr_pliegue(ctx, prot, f, {"tareas": pend, "interno": []}, piloto=True, medidor=med)
                del ctx
                gc.collect()
        reg.cerrar_sesion(sesion, {"fin_utc": ahora_utc(), "segundos_sesion": round(time.perf_counter() - t0, 1),
                                   "maquina_al_final": info_maquina()})
    return reg


# ---------------------------------------------------------------------------
# Modelo de tiempos
# ---------------------------------------------------------------------------
class Lineal:
    """``t = a + b·x`` por mínimos cuadrados con a, b ≥ 0 (pendiente negativa → constante = media; ordenada
    negativa → recta por el origen). Con una sola x distinta, la constante."""

    def __init__(self, x, y):
        x, y = np.asarray(x, dtype="float64"), np.asarray(y, dtype="float64")
        ok = np.isfinite(x) & np.isfinite(y)
        x, y = x[ok], y[ok]
        self.n = int(len(x))
        if self.n == 0:
            self.a, self.b = float("nan"), float("nan")
        elif len(np.unique(x)) < 2:
            self.a, self.b = float(np.mean(y)), 0.0
        else:
            b, a = np.polyfit(x, y, 1)
            if b < 0:
                a, b = float(np.mean(y)), 0.0
            elif a < 0:
                a, b = 0.0, float(np.sum(x * y) / np.sum(x * x))
            self.a, self.b = float(a), float(b)

    def __call__(self, x) -> float:
        return self.a + self.b * float(x)

    def resumen(self) -> dict:
        return {"a_s": self.a, "b_s_por_fila": self.b, "n": self.n}


class CurvaLogLog:
    """Tiempo en función de N por interpolación lineal en log–log entre puntos medidos; fuera del rango, la
    pendiente del tramo extremo; con un solo punto, ``t ∝ N^exponente``."""

    def __init__(self, puntos: dict, exponente: float = 1.0):
        pares = sorted((float(n), max(float(t), 1e-6)) for n, t in puntos.items() if n and np.isfinite(t))
        self.x = np.log([p[0] for p in pares]) if pares else np.zeros(0)
        self.y = np.log([p[1] for p in pares]) if pares else np.zeros(0)
        self.exponente = float(exponente)
        self.puntos = {int(math.exp(a) + 0.5): round(math.exp(b), 3) for a, b in zip(self.x, self.y)}

    def __call__(self, N) -> float:
        if len(self.x) == 0:
            return float("nan")
        lx = math.log(float(N))
        if len(self.x) == 1:
            return math.exp(self.y[0] + self.exponente * (lx - self.x[0]))
        if lx <= self.x[0]:
            i = 0
        elif lx >= self.x[-1]:
            i = len(self.x) - 2
        else:
            i = int(np.searchsorted(self.x, lx) - 1)
        pend = (self.y[i + 1] - self.y[i]) / (self.x[i + 1] - self.x[i])
        return math.exp(self.y[i] + pend * (lx - self.x[i]))

    def relativo(self, N, N0) -> float:
        return self(N) / self(N0)


def _media(d: pd.DataFrame, col: str) -> float:
    v = pd.to_numeric(d[col], errors="coerce").dropna()
    return float(v.mean()) if len(v) else float("nan")


def anadir_menos_contencion(df: pd.DataFrame) -> pd.DataFrame:
    """Columna ``segundos_pared_menos_contencion`` = mín(pared, CPU / p90 del paralelismo de su fase × motor),
    con el p90 sobre las fases de al menos 1 s (si hay menos de 3, la fase queda como se midió), y columna
    ``segundos_pared_sin_contencion_fuerte``, con esa corrección sólo en las fases de contención fuerte."""
    d = df.copy()
    d["motor_"] = d.get("motor", pd.Series(index=d.index, dtype=object)).fillna("-")
    largo = d[(d["segundos_pared"] >= PARALELISMO_MIN_SEGUNDOS) & d["paralelismo"].notna()]
    ref = largo.groupby(["fase", "motor_"])["paralelismo"].agg(
        lambda s: float(s.quantile(PARALELISMO_CUANTIL)) if len(s) >= 3 else float("nan"))
    p = d.set_index(["fase", "motor_"]).index.map(lambda i: ref.get(i, float("nan")))
    p = pd.Series(np.asarray(p, dtype="float64"), index=d.index)
    ajustado = d["segundos_cpu"] / p
    d["segundos_pared_menos_contencion"] = np.where(p.notna() & (p > 0), np.minimum(d["segundos_pared"], ajustado),
                                                    d["segundos_pared"])
    # Sólo las fases con contención fuerte (otros procesos ≥ 50 % de la máquina, al menos 5 s) se corrigen; las
    # demás quedan como se midieron, con la carga de fondo habitual de la máquina.
    fuerte = ((pd.to_numeric(d["fraccion_maquina_otros"], errors="coerce") >= CONTENCION_FUERTE)
              & (d["segundos_pared"] >= CONTENCION_MIN_SEGUNDOS))
    d["segundos_pared_sin_contencion_fuerte"] = np.where(fuerte, d["segundos_pared_menos_contencion"],
                                                         d["segundos_pared"])
    d["paralelismo_referencia"] = p
    return d.drop(columns="motor_")


class ModeloTiempos:
    """Costos por fase de un contaminante, ajustados a las mediciones del piloto en la columna ``col``."""

    def __init__(self, df: pd.DataFrame, pol: str, recetas: dict, col: str, k_curvas: int, k_calib: int | None,
                 media_global: bool = False):
        crudo = df[(df["contaminante"] == pol) & df["error"].isna()] if "error" in df else df[df["contaminante"] == pol]
        d = menos_contaminada(crudo)
        self.pol, self.col, self.recetas, self.media_global = pol, col, recetas, bool(media_global)
        self.N = int(recetas["N_comun"])
        self.supuestos_usados: list[str] = []
        f = d["fase"]
        self.contexto = _media(d[f == "contexto"], col)
        m = d[f == "mascara_calidad"]
        self.mascara = (_media(m, col) if len(m) else
                        self._supuesto("mascara_calidad_s", SUPUESTOS["mascara_calidad_s"]["valor"]))
        v = d[(f == "vecindario") & (d["tarea"] == "vecindario")]
        self.vec = v.groupby("protocolo")[col].mean().to_dict()
        p = d[f == "permutacion"]
        self.perm = Lineal(p["filas_disponibles"], p[col])
        fl = d[(f == "filas") & (d["calidad"].fillna("todo") == "todo")]
        self.filas = Lineal(fl["filas_entrenamiento"], fl[col])
        mt = d[f == "matriz_entrenamiento"]
        self.mtr = Lineal(mt["filas_entrenamiento"], mt[col])
        me = d[f == "matriz_prueba"]
        self.mte = Lineal(me["filas_prueba"], me[col])
        aj = d[(f == "ajuste") & (d["familia"] == "eje_A") & (d["replica"].fillna(0) == 0) & (d["tope"] == "N")]
        self.fit_n = aj.groupby(["protocolo", "motor"])[col].mean().to_dict()
        self.fit_n_global = aj.groupby("motor")[col].mean().to_dict()
        pr = d[(f == "prediccion") & (d["familia"] == "eje_A") & (d["replica"].fillna(0) == 0)]
        self.pred = {mo: Lineal(g["filas_prueba"], g[col]) for mo, g in pr.groupby("motor")}
        # Curvas en el pliegue de LRO de las curvas: puntos (N efectivo → ajuste)
        cu = d[(f == "ajuste") & (d["protocolo"] == "LRO") & (d["k"] == k_curvas)
               & d["familia"].isin(["eje_A", "curva"]) & (d["replica"].fillna(0) == 0)]
        self.curva = {}
        for mo in mv.MOTORES_EJE_A:
            g = cu[cu["motor"] == mo]
            puntos = g.groupby("filas_entrenamiento")[col].mean().to_dict()
            self.curva[mo] = CurvaLogLog(puntos, exponente=1.0)
        # Calibración (pliegue de LRO de más filas de prueba)
        cal = d[(d["protocolo"] == "LRO") & (d["k"] == k_calib)] if k_calib is not None else d.iloc[0:0]
        self.calibrado = bool(len(cal[cal["familia"].isin(FAMILIAS_CALIBRACION)]))

        def en_cal(tarea, fase):
            return _media(cal[(cal["tarea"] == tarea) & (cal["fase"] == fase)], col)

        self.factor_perdida, self.delta_tasa = {}, {}
        for mo in mv.MOTORES_PERDIDAS:
            ref_fit, ref_pred = en_cal(mo, "ajuste"), en_cal(mo, "prediccion")
            for e in cr.ETIQUETAS_PERDIDA:
                tid = f"{mo}_{e}"
                a, b = en_cal(tid, "ajuste"), en_cal(tid, "prediccion")
                if np.isfinite(a) and np.isfinite(ref_fit) and ref_fit > 0:
                    fp = b / ref_pred if np.isfinite(b) and np.isfinite(ref_pred) and ref_pred > 0 else 1.0
                    self.factor_perdida[tid] = (a / ref_fit, fp)
                else:
                    self.factor_perdida[tid] = self._supuesto(f"perdidas.{e}", SUPUESTOS["perdidas"][e])
            dl = cal[(cal["tarea"] == f"{mo}_l2_original") & (cal["fase"] == "delta_huber")]
            if len(dl):
                self.delta_tasa[mo] = _media(dl, col) / max(float(dl["filas_entrenamiento"].iloc[0]), 1.0)
            else:
                self.delta_tasa[mo] = self._supuesto(f"delta_huber.{mo}", self.pred[mo].b if mo in self.pred else 0.0)
        a, b = en_cal("alertas_q80", "ajuste"), en_cal("alertas_q80", "prediccion")
        rf_, rp_ = en_cal("lightgbm", "ajuste"), en_cal("lightgbm", "prediccion")
        if np.isfinite(a) and np.isfinite(rf_) and rf_ > 0:
            self.factor_alertas = (a / rf_, b / rp_ if np.isfinite(b) and np.isfinite(rp_) and rp_ > 0 else 900 / 800)
        else:
            self.factor_alertas = self._supuesto("alertas", SUPUESTOS["alertas"]["factor"])
        te_cal = (float(cal["filas_prueba"].dropna().iloc[0]) if len(cal) and cal["filas_prueba"].notna().any()
                  else float("nan"))
        self.eje_b = {}
        for mo in ("gp", "lme"):
            a, b = en_cal(mo, "ajuste"), en_cal(mo, "prediccion")
            if np.isfinite(a):
                self.eje_b[mo] = (a, b / te_cal if np.isfinite(b) and te_cal > 0 else 0.0)
            else:
                s = SUPUESTOS[mo]
                self.eje_b[mo] = self._supuesto(mo, (s["ajuste_s"], s["tasa_prediccion_s_por_fila"]))
        a = en_cal("lineales", "ajuste_prediccion")
        c = _media(d[f == "construccion_lineales"], col)
        if np.isfinite(a):
            self.lineales_pliegue = a
        else:
            self.lineales_pliegue = self._supuesto("lineales.por_pliegue", SUPUESTOS["lineales"]["por_pliegue_s"])
        self.lineales_construccion = c if np.isfinite(c) else self._supuesto(
            "lineales.construccion", SUPUESTOS["lineales"]["construccion_s"])
        # Sobrecosto fuera de las fases medidas: (pliegue − Σ fases de nivel 1 del pliegue) / Σ fases, por sesión
        self.sobrecosto = self._sobrecosto(crudo, col)

    def _supuesto(self, nombre: str, valor):
        self.supuestos_usados.append(nombre)
        return valor

    @staticmethod
    def _sobrecosto(d: pd.DataFrame, col: str) -> float:
        pl = d[d["fase"] == "pliegue"]
        if not len(pl):
            return 0.0
        dentro = d[~d["fase"].isin(["pliegue", "contexto", "mascara_calidad"])]
        suma_in = dentro.groupby(["protocolo", "k", "sesion"])[col].sum()
        suma_pl = pl.groupby(["protocolo", "k", "sesion"])[col].sum()
        comun = suma_pl.index.intersection(suma_in.index)
        if not len(comun) or suma_in[comun].sum() <= 0:
            return 0.0
        return float(max(suma_pl[comun].sum() - suma_in[comun].sum(), 0.0) / suma_in[comun].sum())

    # --- Costos ---------------------------------------------------------------
    def vecindario(self, prot: str) -> float:
        v = self.vec.get(prot)
        return float(v) if v is not None and np.isfinite(v) else float(np.nanmean(list(self.vec.values())))

    def ajuste(self, prot: str, motor: str, N: float) -> float:
        """Ajuste con N filas: la media del eje A con el N común en el protocolo (o la de los diez pliegues
        medidos, con ``media_global``) por el cociente de la curva."""
        base = (self.fit_n_global.get(motor, float("nan")) if self.media_global
                else self.fit_n.get((prot, motor), self.fit_n_global.get(motor, float("nan"))))
        return float(base) * self.curva[motor].relativo(N, self.N)

    def prediccion(self, motor: str, te: float) -> float:
        return max(self.pred[motor](te), 0.0)

    def n_efectivo(self, tope, disponibles: int) -> int:
        n = self.N if tope == "N" else (disponibles if tope is None else int(tope))
        return int(min(n, disponibles))

    def tarea(self, prot: str, t, disponibles: int, te: int) -> float:
        """Ajuste + predicción (+ δ de Huber) de una tarea; las matrices y las filas van aparte."""
        N = self.n_efectivo(t.tope, disponibles)
        if t.motor == "lineales":
            return self.lineales_pliegue
        if t.motor in ("gp", "lme"):
            a, tasa = self.eje_b[t.motor]
            return a + tasa * te
        if t.familia == "perdidas":
            ff, fp = self.factor_perdida[t.id]
            s = self.ajuste(prot, t.motor, N) * ff + self.prediccion(t.motor, te) * fp
            if t.variante == "l2_original":
                s += self.delta_tasa[t.motor] * N
            return s
        if t.familia == "alertas":
            ff, fp = self.factor_alertas
            return self.ajuste(prot, "lightgbm", N) * ff + self.prediccion("lightgbm", te) * fp
        return self.ajuste(prot, t.motor, N) + self.prediccion(t.motor, te)

    def internos(self, prot: str, disponibles: int, n_int: int, bases) -> float:
        """Pliegues internos de un pliegue externo: definición (permutación y filas), y por cada interno el
        recálculo del vecindario, sus dos matrices y el ajuste y la predicción de cada base."""
        N0 = min(self.N, disponibles)
        ntr, nte = N0 * (n_int - 1) / n_int, N0 / n_int
        s = self.perm(disponibles) + self.filas(N0)
        s += n_int * (self.vecindario(prot) + self.mtr(ntr) + self.mte(nte))
        for b in bases:
            s += n_int * (self.ajuste(prot, b, ntr) + self.prediccion(b, nte))
        return s

    def resumen(self) -> dict:
        return {"columna": self.col, "contexto_s": self.contexto, "mascara_calidad_s": self.mascara,
                "vecindario_s_por_pliegue": self.vec, "permutacion": self.perm.resumen(), "filas": self.filas.resumen(),
                "matriz_entrenamiento": self.mtr.resumen(), "matriz_prueba": self.mte.resumen(),
                "ajuste_N_comun_s": {f"{p}/{m}": v for (p, m), v in sorted(self.fit_n.items())},
                "prediccion": {m: v.resumen() for m, v in self.pred.items()},
                "curvas_ajuste_s": {m: c.puntos for m, c in self.curva.items()},
                "calibrado": self.calibrado,
                "factores_perdidas_ajuste_prediccion": {k: [float(a), float(b)]
                                                        for k, (a, b) in self.factor_perdida.items()},
                "delta_huber_s_por_fila": self.delta_tasa,
                "factor_alertas_ajuste_prediccion": [float(x) for x in self.factor_alertas],
                "eje_B_ajuste_s_y_tasa_prediccion": {k: [float(a), float(b)] for k, (a, b) in self.eje_b.items()},
                "lineales_s_por_pliegue": self.lineales_pliegue, "lineales_construccion_s": self.lineales_construccion,
                "sobrecosto_fuera_de_fases": self.sobrecosto, "supuestos_usados": sorted(set(self.supuestos_usados))}


def familia_de(t) -> str:
    if t.familia == "eje_A":
        return "eje_A" if t.replica == 0 else "semillas"
    return {"curva": "curvas"}.get(t.familia, t.familia)


def n_internos(prot_pliegues: list[dict], n_cfg: int) -> int:
    """Pliegues internos de un pliegue externo de LRO o BLQ-75: un grupo por pliegue externo, así que quedan
    ``grupos − 1`` en el entrenamiento; con menos grupos que pliegues, uno por pliegue."""
    return max(2, min(int(n_cfg), len(prot_pliegues) - 1))


def costo_pliegue(M: ModeloTiempos, prot: str, f: dict, plan: dict, n_int: int) -> dict[str, float]:
    """Segundos de un pliegue por componente, siguiendo el orden y la caché de matrices de ``correr_pliegue``."""
    disp, te = int(f["filas_entrenamiento_disponibles"]), int(f["filas_prueba"])
    out = defaultdict(float)
    out["vecindario"] += M.vecindario(prot)
    tareas = cr._orden_tareas(plan["tareas"])
    for r in sorted({t.replica for t in tareas if t.motor != "lineales"}):
        out["permutaciones"] += M.perm(disp)
    if any(t.motor != "lineales" for t in tareas):
        out["matrices"] += M.mte(te)
    claves = set()
    for t in tareas:
        fam = familia_de(t)
        if t.motor != "lineales":
            N = M.n_efectivo(t.tope, disp)
            out["filas"] += M.filas(N) + (M.mascara if t.calidad != "todo" else 0.0)
            clave = (t.replica, str(t.tope), t.calidad)
            if clave not in claves:
                claves.add(clave)
                out["matrices"] += M.mtr(N)
        out[fam] += M.tarea(prot, t, disp, te)
    if plan["interno"]:
        out["internos"] += M.internos(prot, disp, n_int, plan["interno"])
    factor = 1.0 + M.sobrecosto
    return {k: v * factor for k, v in out.items()}


# Estimaciones: nombre → (columna de tiempo, media global del ajuste por motor). La principal es «horas» (pared
# medida, media de los dos pliegues de cada protocolo); las otras son sensibilidades.
COLUMNAS_ESTIMACION = {"horas": ("segundos_pared", False), "horas_media_global": ("segundos_pared", True),
                       "horas_sin_contencion_fuerte": ("segundos_pared_sin_contencion_fuerte", False),
                       "horas_menos_contencion": ("segundos_pared_menos_contencion", False),
                       "horas_cpu": ("segundos_cpu", False)}
SENSIBILIDADES = ("horas_media_global", "horas_sin_contencion_fuerte", "horas_menos_contencion")


def extrapolar(df: pd.DataFrame, manifiesto: dict, recetas: dict, calidad_disponible: dict, k_curvas: dict,
               k_calib: dict, contaminantes=CONTAMINANTES, protocolos=PROTOCOLOS) -> dict:
    """Horas de la corrida completa por nivel de recorte (0 … 3), con el detalle por contaminante, protocolo y
    componente, en las tres columnas (pared medida, menos contención y CPU)."""
    d = anadir_menos_contencion(df)
    modelos = {nombre: {pol: ModeloTiempos(d, pol, recetas, col, k_curvas[pol], k_calib.get(pol), media_global=mg)
                        for pol in contaminantes} for nombre, (col, mg) in COLUMNAS_ESTIMACION.items()}
    n_cfg = int(recetas["apilado"]["pliegues_internos"])
    out = {"por_recorte": {}, "modelos": {pol: modelos["horas"][pol].resumen() for pol in contaminantes}}
    for rc in (0, 1, 2, 3):
        res = {"recorte": rc}
        for nombre in COLUMNAS_ESTIMACION:
            total, detalle, componentes = 0.0, {}, defaultdict(float)
            for pol in contaminantes:
                M = modelos[nombre][pol]
                seg_pol = M.contexto if np.isfinite(M.contexto) else 0.0
                usa_lineales = False
                for prot in protocolos:
                    plan = cr.plan_protocolo(recetas, prot, cr.Opciones(recorte=rc), calidad_disponible[pol])
                    pl = manifiesto["contaminantes"][pol]["protocolos"][prot]["pliegues"]
                    n_int = n_internos(pl, n_cfg)
                    usa_lineales |= any(t.motor == "lineales" for t in plan["tareas"])
                    comp = defaultdict(float)
                    for f in pl:
                        for k, v in costo_pliegue(M, prot, f, plan, n_int).items():
                            comp[k] += v
                    s = float(sum(comp.values()))
                    detalle[f"{pol}/{prot}"] = {"horas": round(s / 3600, 2), "pliegues": len(pl),
                                                "tareas_por_pliegue": len(plan["tareas"]),
                                                "internos": plan["interno"],
                                                "componentes_horas": {k: round(v / 3600, 3)
                                                                      for k, v in sorted(comp.items())}}
                    for k, v in comp.items():
                        componentes[k] += v
                    seg_pol += s
                if usa_lineales:
                    seg_pol += M.lineales_construccion
                    componentes["construccion_lineales"] += M.lineales_construccion
                componentes["contexto"] += M.contexto if np.isfinite(M.contexto) else 0.0
                total += seg_pol
            res[nombre] = round(total / 3600, 2)
            if nombre == "horas":
                res["detalle"] = detalle
                res["componentes_horas"] = {k: round(v / 3600, 2)
                                            for k, v in sorted(componentes.items(), key=lambda x: -x[1])}
        out["por_recorte"][str(rc)] = res
    return out


def decidir_recortes(estimacion: dict, umbral_h: float, orden: list[dict]) -> dict:
    """Aplica los recortes de §10 en orden hasta quedar bajo el umbral (con la estimación medida, conservadora) y
    deja la bitácora de cada paso."""
    textos = {int(x["orden"]): x["recorte"] for x in orden}
    bitacora, elegido = [], None
    for rc in (0, 1, 2, 3):
        e = estimacion["por_recorte"][str(rc)]
        supera = e["horas"] > umbral_h
        aplicados = "; ".join(textos[i] for i in range(1, rc + 1))
        paso = {"utc": ahora_utc(), "paso": rc,
                "evaluado": "sin recortes" if rc == 0 else f"con los recortes 1…{rc} ({aplicados})",
                "horas_estimadas": e["horas"], **{n: e[n] for n in SENSIBILIDADES}, "horas_cpu": e["horas_cpu"],
                "umbral_horas": umbral_h, "supera_umbral": bool(supera),
                **{f"supera_umbral_{n.removeprefix('horas_')}": bool(e[n] > umbral_h) for n in SENSIBILIDADES}}
        if not supera:
            paso["accion"] = "queda bajo el umbral: se corre así" + ("" if rc == 0 else f" (recorte {rc})")
            bitacora.append(paso)
            elegido = rc
            break
        if rc < 3:
            paso["accion"] = f"supera el umbral: se aplica el recorte {rc + 1} ({textos[rc + 1]})"
        else:
            paso["accion"] = ("supera el umbral aun con los tres recortes: el contrato no prevé un cuarto; se corre "
                              "con los tres y el exceso queda para el autor (enmienda)")
        bitacora.append(paso)
    excede = elegido is None
    elegido = 3 if excede else elegido
    # ¿La decisión cambiaría con las estimaciones de sensibilidad?
    sens = {}
    for nombre in SENSIBILIDADES:
        alt = next((rc for rc in (0, 1, 2, 3) if estimacion["por_recorte"][str(rc)][nombre] <= umbral_h), None)
        sens[nombre] = {"recorte": alt if alt is not None else 3, "excede_tras_recortes": alt is None,
                        "horas_por_recorte": {str(rc): estimacion["por_recorte"][str(rc)][nombre] for rc in range(4)}}
    return {"recorte": elegido, "excede_tras_recortes": excede,
            "aplicados": [textos[i] for i in range(1, elegido + 1)], "bitacora": bitacora,
            "recorte_con_menos_contencion": sens["horas_menos_contencion"]["recorte"],
            "excede_con_menos_contencion": sens["horas_menos_contencion"]["excede_tras_recortes"],
            "sensibilidad": sens}


# ---------------------------------------------------------------------------
# Completitud, contención y plan
# ---------------------------------------------------------------------------
def faltantes(df: pd.DataFrame, manifiesto: dict, recetas: dict, criterio: str, contaminantes=CONTAMINANTES,
              protocolos=PROTOCOLOS) -> list[str]:
    """Lo que el alcance mínimo exige para extrapolar la corrida completa y aún no está medido."""
    hechas = tareas_medidas(df.to_dict("records"))
    vecs = fases_medidas(df.to_dict("records"), "vecindario")
    ctxs = fases_medidas(df.to_dict("records"), "contexto")
    falta = []
    for pol in contaminantes:
        if (pol, None, None) not in ctxs:
            falta.append(f"{pol}: contexto")
        eleg = seleccion(manifiesto, pol, protocolos, criterio)
        k_cur, k_cal = pliegues_lro(eleg["LRO"])
        for prot in protocolos:
            for f in eleg[prot]:
                k = int(f["k"])
                if (pol, prot, k) not in vecs:
                    falta.append(f"{pol} {prot} k={k}: vecindario")
                for t in tareas_piloto(recetas, prot, k, k_cur, k_cal, calibrar=False):
                    if (pol, prot, k, t.id, t.replica) not in hechas:
                        falta.append(f"{pol} {prot} k={k}: {t.id}")
    return falta


def fases_con_contencion_fuerte(df: pd.DataFrame, umbral: float = CONTENCION_FUERTE,
                                minimo_s: float = CONTENCION_MIN_SEGUNDOS) -> list[dict]:
    """Ajustes que entran en la estimación (la medición con menos contención de cada fase) medidos con otros
    procesos ocupando al menos ``umbral`` de la máquina."""
    d = menos_contaminada(df[df["error"].isna()] if "error" in df else df)
    d = d[(d["fase"] == "ajuste") & (d["segundos_pared"] >= minimo_s)
          & (pd.to_numeric(d["fraccion_maquina_otros"], errors="coerce") >= umbral)]
    cols = ["contaminante", "protocolo", "k", "tarea", "segundos_pared", "segundos_cpu", "paralelismo",
            "fraccion_maquina_otros"]
    return [{c: (int(v) if c == "k" else v) for c, v in fila.items()}
            for fila in d.sort_values("segundos_pared", ascending=False)[cols].to_dict("records")]


def resumen_contencion(df: pd.DataFrame) -> dict:
    """Contención con otros procesos durante las fases de ajuste y predicción (la que más pesa en el total)."""
    d = df[df["fase"].isin(FASES_TAREA) & (df["segundos_pared"] >= PARALELISMO_MIN_SEGUNDOS)]
    if not len(d):
        return {}
    w = d["segundos_pared"]
    fr = d["fraccion_maquina_otros"].astype(float)
    return {"fases": int(len(d)), "horas_pared_medidas": round(float(w.sum()) / 3600, 2),
            "fraccion_maquina_otros_media_ponderada": round(float((fr * w).sum() / w.sum()), 3),
            "fraccion_maquina_otros_p50": round(float(fr.median()), 3),
            "fraccion_maquina_otros_p90": round(float(fr.quantile(0.9)), 3),
            "fraccion_maquina_otros_max": round(float(fr.max()), 3),
            "carga_1min_max": round(float(d["carga_1min_max"].max()), 2),
            "paralelismo_mediano_ajuste": (d[d["fase"] == "ajuste"].groupby("motor")["paralelismo"].median()
                                           .round(2).to_dict())}


def plan_resultante(recetas: dict, manifiesto: dict, recorte: int, calidad_disponible: dict, estimacion: dict,
                    contaminantes=CONTAMINANTES, protocolos=PROTOCOLOS) -> dict:
    out = {"recorte": recorte, "opciones": {**{k: v for k, v in asdict(cr.Opciones(recorte=recorte)).items()
                                              if k != "motores"}, "motores": list(mv.MOTORES_EJE_A)},
           "por_contaminante": {}}
    det = estimacion["por_recorte"][str(recorte)]["detalle"]
    for pol in contaminantes:
        out["por_contaminante"][pol] = {}
        for prot in protocolos:
            p = cr.plan_protocolo(recetas, prot, cr.Opciones(recorte=recorte), calidad_disponible[pol])
            out["por_contaminante"][pol][prot] = {
                "pliegues": int(manifiesto["conteos"][pol][prot]),
                "tareas": [t.id if t.replica == 0 else f"{t.id}@r{t.replica}" for t in p["tareas"]],
                "internos": p["interno"], "semillas": p["semillas"], "curvas": p["curvas"],
                "horas_estimadas": det[f"{pol}/{prot}"]["horas"]}
    rc = f" --recorte {recorte}" if recorte else ""
    pols = " ".join(contaminantes)
    out["comandos"] = [
        f"python -B scripts_modelo_1km/v2/correr_v2.py correr --contaminantes {pols}{rc} --hilos 12",
        "(en paralelo, un proceso por parte: ... correr ... --parte i/m; baja la duración, no las horas de máquina)",
        f"python -B scripts_modelo_1km/v2/correr_v2.py consolidar --contaminantes {pols}{rc}"]
    return out


def ejecutar(args, r: RutasV2, cfg: dict) -> int:
    """Acción ``piloto`` de ``correr_v2``: mide lo que falte (salvo ``--solo-estimar``) y, si el alcance está
    completo, extrapola, decide los recortes y publica el plan."""
    hilos = int(args.hilos or cfg["operacion"]["hilos_maximos"])
    if not args.solo_estimar:
        medir(r, cfg, args.contaminantes, args.protocolos, hilos, args.criterio_pliegues, args.calibrar_familias,
              args.rehacer, remedir_si_otros=getattr(args, "remedir_contaminadas", None))
    return estimar_y_publicar(r, cfg, hilos, args.criterio_pliegues)


def estimar_y_publicar(r: RutasV2, cfg: dict, hilos: int, criterio: str = "entrenamiento",
                       manifiesto: dict | None = None, anotar: bool = True, contaminantes=CONTAMINANTES) -> int:
    """Extrapola la corrida completa (los dos contaminantes del contrato) con las mediciones guardadas, decide
    los recortes y publica el plan, las tablas pequeñas y el evento de la bitácora. Si al alcance mínimo le falta
    algo, no escribe nada."""
    contaminantes = tuple(contaminantes)
    recetas = mv.recetas_de(cfg, hilos)
    man = manifiesto if manifiesto is not None else leer_json(r.manifiesto_pliegues)
    doc = leer_json(r.raiz_v2 / CARPETA / NOMBRE_MEDICIONES)
    if doc is None or not doc.get("mediciones"):
        print("Sin mediciones del piloto: nada que extrapolar")
        return 0
    df = pd.DataFrame(doc["mediciones"])
    if "error" not in df:
        df["error"] = None
    falta = faltantes(df, man, recetas, criterio, contaminantes)
    if falta:
        print(f"Piloto incompleto ({len(falta)} pendientes); no se escribe el plan. Primeros: " + "; ".join(falta[:12]))
        return 0
    import calidad_v2
    calidad = {pol: calidad_v2.ruta_calidad(r, pol).exists() for pol in contaminantes}
    eleg = {pol: seleccion(man, pol, PROTOCOLOS, criterio) for pol in contaminantes}
    kk = {pol: pliegues_lro(eleg[pol]["LRO"]) for pol in contaminantes}
    k_cur, k_cal = {p: v[0] for p, v in kk.items()}, {p: v[1] for p, v in kk.items()}
    est = extrapolar(df, man, recetas, calidad, k_cur, k_cal, contaminantes)
    umbral = float(cfg["presupuesto"]["umbral_horas_maquina"])
    dec = decidir_recortes(est, umbral, cfg["presupuesto"]["orden_de_recortes"])
    cont = resumen_contencion(df)
    ruta_med = r.raiz_v2 / CARPETA / NOMBRE_MEDICIONES
    sha_med = sha256_archivo(ruta_med)
    eleccion = cfg["presupuesto"]["piloto"]["eleccion_de_los_pliegues"]
    supuestos = sorted({s for m in est["modelos"].values() for s in m["supuestos_usados"]})
    plan = {
        "schema": SCHEMA_PLAN,
        "descripcion": ("Plan de la corrida completa de la comparación v2 (DISENO_AMBIENTAL_V2.md §3–§8) según el "
                        "piloto de tiempos (§10): estimación de horas de máquina por nivel de recorte, bitácora de "
                        "recortes y plan resultante. Un tiempo no es un resultado: el piloto no guardó predicciones "
                        "ni calculó métricas."),
        "contrato": {"seccion": "§10", "umbral_horas_maquina": umbral,
                     "umbral_aproximado": bool(cfg["presupuesto"].get("umbral_aproximado", True)),
                     "orden_de_recortes": cfg["presupuesto"]["orden_de_recortes"],
                     "registro_de_recortes": cfg["presupuesto"]["registro_de_recortes"]},
        "piloto": {
            "alcance": {"criterio_pliegues": criterio, "pliegues_por_protocolo": 2,
                        "eje_A": list(mv.MOTORES_EJE_A), "N_comun": recetas["N_comun"],
                        "curvas": {m: [("todas" if t is None else t) for t in v]
                                   for m, v in topes_curva_piloto(recetas).items()},
                        "pliegue_curvas": {p: {"protocolo": "LRO", "k": k_cur[p]} for p in contaminantes},
                        "calibracion_familias": {p: {"protocolo": "LRO", "k": k_cal[p],
                                                     "medida": est["modelos"][p]["calibrado"]} for p in contaminantes},
                        "provisional_config": eleccion.get("provisional"),
                        "sin_metricas": ("no se guardaron predicciones ni se calculó, guardó o miró ninguna métrica "
                                         "de desempeño")},
            "pliegues": {pol: {prot: [{"k": int(f["k"]), "grupo": f["grupo"],
                                       "filas_entrenamiento_disponibles": int(f["filas_entrenamiento_disponibles"]),
                                       "filas_prueba": int(f["filas_prueba"])} for f in eleg[pol][prot]]
                               for prot in PROTOCOLOS} for pol in contaminantes},
            "mediciones": {**r.relativa(ruta_med), "sha256": sha_med, "filas": int(len(df)),
                           "sesiones": [resumen_sesion(s) for s in doc.get("sesiones", [])]},
            "horas_pared_del_piloto": round(float(df[df["fase"] == "pliegue"]["segundos_pared"].sum()
                                                  + df[df["fase"] == "contexto"]["segundos_pared"].sum()) / 3600, 2),
            "memoria_maxima_mb": float(pd.to_numeric(df["maxrss_proceso_mb"], errors="coerce").max()),
            "contencion": cont},
        "definicion_horas_maquina": ("horas de pared de un proceso con 12 hilos, que ocupa la máquina; paralelizar "
                                     "por pliegue baja la duración, no las horas de máquina. «horas_cpu» suma la CPU "
                                     "de todos los hilos"),
        "modelo_de_extrapolacion": {
            "metodo": "por fase y por pliegue del manifiesto, con las filas de entrenamiento y de prueba de cada uno "
                      "(ver el docstring de piloto_v2.py)",
            "supuestos_usados": supuestos, "supuestos_valores": {k: SUPUESTOS[k.split(".")[0]] for k in supuestos
                                                                 if k.split(".")[0] in SUPUESTOS},
            "no_incluido": ["consolidación (retransformación, métricas y bootstrap de 2.000 réplicas)",
                            "escritura de los puntos de control"],
            "pliegues_internos": "modelados (no medidos): n = mín(5, grupos − 1) internos por pliegue externo",
            "modelos": est["modelos"]},
        "estimacion": est["por_recorte"],
        "sensibilidad": {
            "nota": ("la decisión usa «horas» (pared medida; ajuste del eje A con la media de los dos pliegues de cada "
                     "protocolo). «horas_media_global» usa la media de los diez pliegues medidos por motor (más "
                     "estable para la MLP, cuyas épocas varían de un pliegue a otro); «horas_sin_contencion_fuerte» "
                     "corrige con CPU / p90 del paralelismo sólo los ajustes medidos con otros procesos ocupando al "
                     "menos la mitad de la máquina; «horas_menos_contencion» aplica esa corrección a todas las "
                     "fases"),
            **dec["sensibilidad"]},
        "bitacora_de_recortes": dec["bitacora"],
        "recorte_aplicado": dec["recorte"],
        "recortes_aplicados": dec["aplicados"],
        "excede_tras_recortes": dec["excede_tras_recortes"],
        "posible_sobreestimacion": {
            "motivo": ("en paralelo corrían otro trabajo pesado y una descarga: los tiempos de pared pueden estar "
                       "sobreestimados"),
            "contencion_medida": cont,
            "ajustes_con_contencion_fuerte": {
                "criterio": (f"otros procesos ≥ {CONTENCION_FUERTE:.0%} de la máquina, ajustes ≥ "
                             f"{CONTENCION_MIN_SEGUNDOS:g} s"),
                "fases": fases_con_contencion_fuerte(df),
                "como_remedir": ("python -B scripts_modelo_1km/v2/correr_v2.py piloto --contaminantes pm25 no2 "
                                 "--calibrar-familias --remedir-contaminadas 0.5 --hilos 12 (con la máquina libre); "
                                 "la extrapolación usa la medición con menos contención de cada fase")},
            "horas_menos_contencion_del_plan": est["por_recorte"][str(dec["recorte"])]["horas_menos_contencion"],
            "recorte_con_menos_contencion": dec["recorte_con_menos_contencion"],
            "excede_con_menos_contencion": dec["excede_con_menos_contencion"],
            "criterio": "la decisión usa la estimación medida (conservadora)"},
        "plan_resultante": plan_resultante(recetas, man, dec["recorte"], calidad, est, contaminantes),
        "traza": traza({**insumos_piloto(r, contaminantes), "mediciones_piloto": ruta_med},
                       SEMILLAS_PILOTO, hilos, rutas=r, parametros={"criterio_pliegues": criterio}),
    }
    plan["bitacora_manifiesto"] = estado_bitacora(r, dec)
    if dec["excede_tras_recortes"]:
        plan["pendiente_del_autor"] = (
            f"Con los tres recortes de §10 la estimación sigue en {est['por_recorte']['3']['horas']} h de máquina "
            f"(umbral: unas {umbral:g} h). El contrato no prevé otro recorte: correr igual o reducir por enmienda "
            f"fechada es decisión del autor. Los componentes que más pesan están en "
            f"estimacion['3']['componentes_horas'].")
    tabla = df.drop(columns=[c for c in ("error",) if c in df and df[c].isna().all()])
    with candado_escritura(CANDADO_PLAN, rutas=r):
        plan = sin_nan(plan)
        sha_plan = publicar_json(plan, r.raiz_v2 / NOMBRE_PLAN, r)
        datos = tabla.to_csv(index=False, lineterminator="\n", float_format="%.6g").encode("utf-8")
        publicar_bytes(datos, r.salidas_v2 / TABLA_CSV, r)
        lateral = {"schema": cr.SCHEMA_PILOTO,
                   "nota": "un tiempo no es un resultado: el piloto no guarda predicciones ni métricas de desempeño",
                   "tabla": {"archivo": TABLA_CSV, "sha256": hashlib.sha256(datos).hexdigest(),
                             "filas": int(len(tabla))},
                   "plan": {**r.relativa(r.raiz_v2 / NOMBRE_PLAN), "sha256": sha_plan},
                   "horas_por_recorte": {k: {c: v[c] for c in COLUMNAS_ESTIMACION}
                                         for k, v in est["por_recorte"].items()},
                   "recorte_aplicado": dec["recorte"], "excede_tras_recortes": dec["excede_tras_recortes"],
                   "contencion": cont, "traza": plan["traza"]}
        publicar_json(sin_nan(lateral), r.salidas_v2 / TABLA_JSON, r)
    if anotar:
        anotar_recorte_plan(r, dec, est, sha_plan)
    imprimir_resumen(est, dec, umbral, cont)
    return 0


def estado_bitacora(r: RutasV2, dec: dict, etiqueta: str = cr.ETIQUETA) -> dict:
    """Relación del plan con la bitácora del manifiesto (§10): si el último evento ``recorte_presupuesto`` de la
    etiqueta ya tiene este recorte, el plan lo cita (una reestimación con la misma decisión no se vuelve a anotar);
    si no, el evento se anota al publicar este plan, con su sha256."""
    m = leer_json(r.manifiesto_pliegues) or {}
    previos = [e for e in m.get("bitacora", []) if e.get("evento") == "recorte_presupuesto"
               and e.get("etiqueta") == etiqueta]
    ultimo = previos[-1] if previos else None
    if ultimo is not None and ultimo.get("recorte") == dec["recorte"]:
        return {"estado": "ya anotado (misma decisión)", "evento_utc": ultimo.get("utc"),
                "plan_sha256_del_evento": ultimo.get("plan_sha256"), "horas_del_evento": ultimo.get("horas_estimadas")}
    if ultimo is None and dec["recorte"] == 0:
        return {"estado": "sin recorte: nada que anotar"}
    return {"estado": "se anota al publicar este plan (con su sha256)",
            "reemplaza": None if ultimo is None else {"recorte": ultimo.get("recorte"), "utc": ultimo.get("utc")}}


def resumen_sesion(s: dict) -> dict:
    """Lo esencial de una sesión de medición: fechas, argumentos, commit y hash del código con que se midió."""
    t = s.get("traza") or {}
    return {"sesion": s.get("sesion"), "inicio_utc": s.get("inicio_utc"), "fin_utc": s.get("fin_utc"),
            "segundos_sesion": s.get("segundos_sesion"), "argumentos": s.get("argumentos"),
            "commit": (t.get("git") or {}).get("commit"), "hash_codigo": (t.get("codigo") or {}).get("hash"),
            "procesos_mas_activos_al_inicio": (s.get("maquina_al_inicio") or {}).get("procesos_mas_activos")}


def anotar_recorte_plan(r: RutasV2, dec: dict, est: dict, sha_plan: str, etiqueta: str = cr.ETIQUETA) -> bool:
    """Evento ``recorte_presupuesto`` en la bitácora del manifiesto (§10) cuando la decisión cambia respecto del
    último evento de la etiqueta (o es el primer recorte): una reestimación con el mismo recorte no se repite, y
    una que lo cambia (también a 0) deja dicho a cuál reemplaza. ``correr_v2.anotar_recorte`` reconoce el evento y
    no lo duplica al correr. Devuelve si anotó."""
    import pliegues_v2
    m = leer_json(r.manifiesto_pliegues) or {}
    previos = [e for e in m.get("bitacora", []) if e.get("evento") == "recorte_presupuesto"
               and e.get("etiqueta") == etiqueta]
    ultimo = previos[-1] if previos else None
    if (ultimo is None and dec["recorte"] == 0) or (ultimo is not None and ultimo.get("recorte") == dec["recorte"]):
        return False
    evento = {"evento": "recorte_presupuesto", "recorte": dec["recorte"], "etiqueta": etiqueta,
              "aplicados": dec["aplicados"], "fuente": f"piloto de tiempos (§10): {NOMBRE_PLAN}",
              "plan_sha256": sha_plan, "horas_estimadas": {k: v["horas"] for k, v in est["por_recorte"].items()},
              "excede_tras_recortes": dec["excede_tras_recortes"]}
    if ultimo is not None:
        evento["reemplaza"] = {"recorte": ultimo.get("recorte"), "utc": ultimo.get("utc"),
                               "plan_sha256": ultimo.get("plan_sha256")}
    pliegues_v2.anotar_bitacora(evento, r)
    return True


def imprimir_resumen(est: dict, dec: dict, umbral: float, cont: dict) -> None:
    print(f"Horas de máquina estimadas (umbral {umbral:g} h):")
    for rc, e in est["por_recorte"].items():
        print(f"  recorte {rc}: {e['horas']:>6.1f} h medidas | {e['horas_media_global']:>6.1f} media global | "
              f"{e['horas_sin_contencion_fuerte']:>6.1f} sin contención fuerte | {e['horas_menos_contencion']:>6.1f} "
              f"menos contención | {e['horas_cpu']:>6.1f} h de CPU")
    print(f"Recorte aplicado: {dec['recorte']} ({'; '.join(dec['aplicados']) or 'ninguno'})"
          f"{' — EXCEDE el umbral aun con los tres recortes' if dec['excede_tras_recortes'] else ''}")
    if cont:
        media, p90 = cont["fraccion_maquina_otros_media_ponderada"], cont["fraccion_maquina_otros_p90"]
        print(f"Contención: otros procesos usaron en promedio {100 * media:.0f} % de la máquina durante los ajustes "
              f"y predicciones (p90 {100 * p90:.0f} %)")


__all__ = ["Medidor", "Registro", "medir", "extrapolar", "decidir_recortes", "estimar_y_publicar", "ejecutar",
           "tareas_piloto", "pliegues_lro", "topes_curva_piloto", "pendientes", "ModeloTiempos", "costo_pliegue"]
