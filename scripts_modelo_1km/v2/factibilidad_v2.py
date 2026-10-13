#!/usr/bin/env python3
"""Factibilidad de producción con predictores compilados (``DISENO_AMBIENTAL_V2.md``, Complemento de la Enmienda 1,
punto 3, que reemplaza la factibilidad del punto 11): sólo tiempos.

**La regla** (``config_v2.json`` → ``decision.factibilidad``, fijada antes de cualquier ajuste comparativo e
irrevisable): un candidato es factible si su producción 2000-2026 de los dos contaminantes cuesta ≤ 5 veces la de
LightGBM compilado y ≤ 21 días de máquina con 12 hilos. El promedio simple cuesta la suma de sus miembros. LightGBM es
la referencia, no un candidato: la regla no lo excluye. Con la «lectura» de la configuración, por contaminante la
producción cuesta la media de los tiempos de los 3 días medidos por los 9.862 días del calendario 2000-2026; se suman
los dos contaminantes y con esas sumas se calculan los días de máquina y el cociente frente a LightGBM.

**Un tiempo no es un resultado.** Este programa no calcula, guarda ni muestra ninguna métrica de desempeño ni ningún
descriptivo de predicciones reales: los motores se ajustan sin conjuntos de evaluación (sin métrica de entrenamiento,
sin OOB y la MLP sin validación), de cada predicción de los días reales sólo se comprueba el largo y los modelos viven
en un temporal que se borra al terminar. La equivalencia de cada predictor compilado con su motor se comprueba con
**filas sintéticas** (cada columna del entrenamiento permutada por separado, más faltantes): se registra sólo la
diferencia máxima entre las dos predicciones, nunca un valor observado.

**Qué se mide**, por contaminante:

1. **Matrices reales de 3 días**: verano, transición (otoño) e invierno; las fechas las fija este código antes de medir,
   sin mirar nada: el día 15 del mes central de cada estación (enero, abril y julio) del año central del régimen de
   predictores 2019-2024 (Enmienda 1, punto 10: con GEOS-CF y TROPOMI). Las arma el código de producción v1
   (``scripts_modelo_1km/produccion.py`` y sus módulos) en sólo lectura y en un subproceso propio:
   ``ContextoPrediccion.dia`` (produccion.py:359-437) con el bucle de ``producir_serie.py:82-95`` (un contexto por
   contaminante; la ventana satelital se reinicia y se calienta con los 15 días previos de cada fecha). Lo único que se
   reemplaza, en memoria, es el ``Modelo`` de la v1 (produccion.py:262-296): un capturador que guarda en el temporal la
   matriz de cada hora, la misma que produccion.py:409 entrega al motor, y devuelve ceros; las superficies de ceros que
   ``dia`` escribe (produccion.py:421-434) van también al temporal. ``derivadas_horarias`` se envuelve sin cambiar su
   resultado para registrar qué predictores tendría que rellenar con NaN produccion.py:402-404. Una guardia de
   auditoría (``sys.addaudithook``) rechaza en ese subproceso toda escritura de Python fuera del temporal y todo
   subproceso, y Python corre sin bytecode (``-B``).
2. **Ajuste** (una vez, sin evaluación, con ``--hilos`` = 8 hilos): los cuatro motores del eje A con las recetas de
   ``motores_v2`` y el N de producción (``decision.N_de_produccion`` = 750.000 filas: prefijo de
   ``default_rng([42]).permutation`` sobre todo el panel v1, porque en producción no hay grupo retirado). La MLP recorre
   ``EPOCAS_MLP`` épocas fijas: el costo de predecir de una red no depende de sus épocas.
3. **Compilación** (8 hilos): LightGBM con ``lleaves`` (``compile()`` por omisión y entrada float64, como el
   ``_Compilado`` de produccion.py:226-254); XGBoost y RF con ``treelite`` → ``tl2cgen`` (clang ``-O3``, una unidad de
   compilación por cada ``NODOS_POR_UNIDAD`` nodos); en el RF, el ``default_left`` de cada nodo se toma del
   ``missing_go_to_left`` de scikit-learn, que el importador de treelite ignora (sin eso las filas con NaN cambian de
   rama); la MLP en float32, por lotes de ``LOTE_MLP`` filas en hilos (recorte de entradas, imputación, escala, capas
   densas ReLU y recorte de la salida, con los parámetros del modelo ajustado).
4. **Predicción medida** (12 hilos, ``decision.factibilidad.hilos``): en otro subproceso, iniciado con 12 hilos de
   OpenMP y BLAS y que sólo carga los predictores compilados (como un proceso de producción), cada predictor predice
   los 24 bloques horarios de 838.430 filas de cada día, ``REPETICIONES`` veces en orden rotado tras un calentamiento.
   Cada fase la mide ``piloto_v2.Medidor`` (pared, CPU, memoria, CPU del resto de la máquina y carga media de 1 minuto
   al empezar y máxima). Antes de medir se espera, con un tope de ``ESPERA_MAXIMA_S``, a que la carga media de 1 minuto
   baje de ``CARGA_LIBRE`` (el criterio del punto 8 del Complemento para el piloto); la espera queda registrada.

**Estadístico**: por día, la mediana de las repeticiones (pared de los 24 bloques); por contaminante, la media de los 3
días. **No incluido** (común a todos los motores): armar la matriz desde los productos, el vecindario, la
retransformación, la escritura NetCDF y el ajuste; el tiempo de armar las matrices con la v1 se registra sólo como
información.

**Hilos.** Todo corre con 8 hilos como máximo (tope de esta etapa, porque otros trabajos usan la máquina) salvo la
predicción medida, que usa los 12 que fija la regla. tl2cgen no admite más hilos que los de su OpenMP al iniciarse,
por eso la medición va en su propio proceso.

Salidas (con el candado ``factibilidad``):

* ``<raíz v2>/factibilidad/mediciones.json``: cada fase medida, por contaminante, con su traza;
* ``output_files/modelo_1km_v2/factibilidad_produccion.json``: la regla aplicada (tabla pequeña).

Los dos archivos de la medición del punto 11 (esquemas ``…v1``) se conservan con el sufijo ``_reemplazado_<fecha>``.

Uso::

    TMPDIR=<temporal> python -B scripts_modelo_1km/v2/factibilidad_v2.py medir
    python -B scripts_modelo_1km/v2/factibilidad_v2.py publicar
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import gc
import json
import logging
import math
import os
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from _traza_v2 import VARIABLES_HILOS, fijar_hilos  # noqa: E402  (antes de numpy: tope de hilos de BLAS y OpenMP)

HILOS_AJUSTE = 8             # ajuste, compilación, verificación y matrices: tope de la etapa (otros trabajos en paralelo)

if __name__ == "__main__":
    from _rutas_v2 import hilos_de_la_linea  # noqa: E402  (sólo biblioteca estándar)
    fijar_hilos(hilos_de_la_linea(por_omision=HILOS_AJUSTE))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import motores_v2 as mv  # noqa: E402
import piloto_v2 as pl  # noqa: E402
from _rutas_v2 import (  # noqa: E402
    REGLAS_CANDADO, RutasV2, a_json, ahora_utc, candado_escritura, cargar_config, leer_json, publicar_json,
    registrar_candado, renombrar, rutas_v2, valor_vigente,
)
from _traza_v2 import hash_codigo_v2, sha256_archivo, sha256_json, traza, versiones_bibliotecas  # noqa: E402
from perdidas_v2 import Variante  # noqa: E402

log = logging.getLogger("modelo_1km_v2.factibilidad")

SCHEMA_MEDICIONES = "airpollution.modelo-1km-v2.factibilidad-mediciones.v2"
SCHEMA_RESUMEN = "airpollution.modelo-1km-v2.factibilidad-produccion.v2"
SCHEMAS_PUNTO_11 = ("airpollution.modelo-1km-v2.factibilidad-mediciones.v1",
                    "airpollution.modelo-1km-v2.factibilidad-produccion.v1")
SCHEMA_ENCARGO_MATRICES = "airpollution.modelo-1km-v2.factibilidad-encargo-matrices.v1"
SCHEMA_MATRICES = "airpollution.modelo-1km-v2.factibilidad-matrices.v1"
SCHEMA_ENCARGO_PREDICCION = "airpollution.modelo-1km-v2.factibilidad-encargo-prediccion.v1"
SCHEMA_TIEMPOS = "airpollution.modelo-1km-v2.factibilidad-tiempos.v1"
CARPETA = "factibilidad"
NOMBRE_MEDICIONES = "mediciones.json"
NOMBRE_RESUMEN = "factibilidad_produccion.json"
NOMBRE_MATRICES = "matrices.json"
CANDADO = "factibilidad"
_REGLAS = (("raiz_v2", r"factibilidad/[^/]+", CANDADO),
           ("salidas_v2", r"factibilidad_produccion(?:_reemplazado_[^/]+)?\.json", CANDADO))
for _raiz, _patron, _plantilla in _REGLAS:          # un solo candado para los artefactos de esta pieza y sus respaldos
    if not any(r == _raiz and p.pattern == _patron for r, p, _ in REGLAS_CANDADO):
        registrar_candado(_raiz, _patron, _plantilla)

CONTAMINANTES = ("pm25", "no2")
MOTORES = tuple(mv.MOTORES_EJE_A)                   # lightgbm, xgboost, random_forest, mlp
PROMEDIO = "promedio_simple"
REFERENCIA = "lightgbm"
HORAS = 24
REPETICIONES = 3
SEMILLA_FILAS = [42]                 # filas de producción: default_rng([42]).permutation (sin pliegue)
SEMILLA_MOTORES = 42                 # semilla de la receta (LightGBM, XGBoost) y 42 + k con k = 0 (RF, MLP)
SEMILLA_SINTETICA = [42, 7]          # filas sintéticas de la verificación de equivalencia
EPOCAS_MLP = 2                       # épocas fijas de la MLP (su costo de predicción no depende de ellas)
FILAS_CALENTAMIENTO = 50_000         # filas del calentamiento de cada predictor antes de medir un día
FILAS_VERIFICACION = 20_000          # filas sintéticas de la verificación de equivalencia
FRACCION_NAN_VERIFICACION = 0.05     # faltantes agregados a las filas sintéticas (ejercen las ramas de NaN)
LOTE_MLP = 8_192                     # filas por lote de la MLP compilada
NODOS_POR_UNIDAD = 20_000            # tl2cgen: nodos por unidad de compilación (parallel_comp); clang tarda mucho más
                                     # que el doble con dos árboles hondos por unidad (146,9 s frente a 12,4 s,
                                     # sintético): así cada árbol del RF va en su unidad. Sólo cambia la compilación
TOOLCHAIN = "clang"
SEGUNDOS_DIA = 86_400.0
CALENTAMIENTO_SATELITAL = 15         # días previos de la ventana satelital (producir_serie.py:92; produccion.py:441)
REGIMEN_MEDICION = "2019-2024"       # Enmienda 1, punto 10: el régimen con GEOS-CF y TROPOMI
DIA_DEL_MES = 15
ESTACIONES_DEL_ANIO = (("verano", 1), ("transicion", 4), ("invierno", 7))   # mes central de DEF, MAM y JJA
MESES_ESTACION = {"verano": (12, 1, 2), "transicion": (3, 4, 5, 9, 10, 11), "invierno": (6, 7, 8)}
CARGA_LIBRE = 2.0                    # carga media de 1 minuto «libre» (Complemento, punto 8, para el piloto)
ESPERA_MAXIMA_S = 1200.0
INTERVALO_ESPERA_S = 30.0
# |compilado − motor| máximo sobre las filas sintéticas, en log1p: 1e-9 es la tolerancia de la producción v1
# (produccion.py:259) para los predictores en float64; XGBoost y la MLP trabajan en float32.
TOLERANCIAS = {"lightgbm": 1e-9, "xgboost": 1e-3, "random_forest": 1e-9, "mlp": 1e-4}
COLUMNAS_TRAS_DERIVADAS = ("hora_local", "hora_sin", "hora_cos", "obs_vec", "peso_vec")   # produccion.py:399-401
# Variables que cambian lo que arma la producción v1; el subproceso las quita para usar los valores por omisión, que
# son los de la producción publicada (panel sin interpolación, SINCA + SNIFA, racha 24, reloj al fin del intervalo).
VARIABLES_V1 = ("MODELO_1KM_INTERPOLAR", "MODELO_1KM_RED_ADICIONAL", "MODELO_1KM_QC_RACHA", "MODELO_1KM_ETIQUETA_SINCA",
                "MODELO_1KM_ETIQUETA", "MODELO_1KM_RETRANSFORMACION", "MODELO_1KM_RETRANSFORMACION_PM25",
                "MODELO_1KM_RETRANSFORMACION_NO2", "MODELO_1KM_PREDICTOR", "MODELO_1KM_HILOS_PREDICCION",
                "MODELO_1KM_EXCLUIR")
MODULOS_V1 = ("produccion.py", "_features.py", "_comun_modelo.py", "_red_adicional.py", "construir_grilla.py",
              "producir_serie.py")
METRICAS_PROHIBIDAS = ("r2", "rmse", "mae", "nmb", "sesgo", "score", "pinball", "cobertura_intervalo")


# ---------------------------------------------------------------------------
# Calendario y fechas de la medición (fijadas antes de medir)
# ---------------------------------------------------------------------------
def dias_entre(desde: date, hasta: date) -> int:
    """Días del intervalo cerrado [desde, hasta]."""
    if hasta < desde:
        raise ValueError(f"intervalo vacío: {desde} > {hasta}")
    return (hasta - desde).days + 1


def dias_calendario(anios) -> int:
    """Días del calendario completo de los años [a0, a1] (``decision.factibilidad.periodo``: 9.862 en 2000-2026)."""
    a0, a1 = (int(a) for a in anios)
    return dias_entre(date(a0, 1, 1), date(a1, 12, 31))


def fecha_central(desde: date, hasta: date) -> date:
    """Día central de [desde, hasta]: ``desde + n // 2`` con n el número de días."""
    return desde + timedelta(days=dias_entre(desde, hasta) // 2)


def regimenes_de(cfg: dict) -> list[dict]:
    """Regímenes de predictores (Enmienda 1, punto 10) tal como los fija la configuración."""
    crit = cfg["metricas"]["desagregaciones"]["regimen_de_predictores"]["criterio"]
    return [{"id": str(r["id"]), "anios": [int(r["anios"][0]), int(r["anios"][1])]}
            for r in valor_vigente(crit, "metricas.desagregaciones.regimen_de_predictores.criterio")]


def estacion_del_anio(fecha: date) -> str:
    """Estación del hemisferio sur de una fecha: verano (DEF), invierno (JJA) o transición (MAM y SON)."""
    for nombre, meses in MESES_ESTACION.items():
        if fecha.month in meses:
            return nombre
    raise ValueError(fecha)


def fechas_de_medicion(cfg: dict) -> dict[str, date]:
    """Las 3 fechas de la medición, fijadas por regla de calendario y sin mirar ningún dato: el día 15 del mes central
    de cada estación (enero, abril y julio) del año del día central del régimen 2019-2024 (2022)."""
    reg = {r["id"]: r for r in regimenes_de(cfg)}
    if REGIMEN_MEDICION not in reg:
        raise ValueError(f"la configuración no tiene el régimen de predictores {REGIMEN_MEDICION}")
    a0, a1 = reg[REGIMEN_MEDICION]["anios"]
    anio = fecha_central(date(a0, 1, 1), date(a1, 12, 31)).year
    out = {nombre: date(anio, mes, DIA_DEL_MES) for nombre, mes in ESTACIONES_DEL_ANIO}
    for nombre, f in out.items():
        if estacion_del_anio(f) != nombre or not a0 <= f.year <= a1:
            raise AssertionError(f"la fecha {f} no es de {nombre} en {a0}-{a1}")
    return out


def nombre_matriz(pol: str, fecha: date) -> str:
    return f"X_{pol}_{fecha:%Y%m%d}.npy"


# ---------------------------------------------------------------------------
# Guardia de escritura del subproceso v1
# ---------------------------------------------------------------------------
# evento → posición de su ``dir_fd`` en los argumentos (None si no lleva), según la tabla de eventos de CPython
EVENTOS_UNA_RUTA = {"os.mkdir": 2, "os.remove": 1, "os.rmdir": 1, "os.truncate": None, "os.chmod": 2, "os.chown": 3,
                    "os.utime": 3, "os.chflags": None, "os.lchflags": None, "os.lchmod": None, "os.lchown": None,
                    "os.mkfifo": 2, "os.mknod": 3, "os.setxattr": None, "os.removexattr": None, "shutil.rmtree": 1,
                    "tempfile.mkstemp": None, "tempfile.mkdtemp": None}
EVENTOS_DESTINO = ("os.rename", "os.link", "os.symlink", "shutil.copyfile", "shutil.copytree", "shutil.move",
                   "shutil.copymode", "shutil.copystat", "shutil.chown")
EVENTOS_PROCESO = ("subprocess.Popen", "os.system", "os.posix_spawn", "os.spawn", "os.exec", "os.fork", "os.forkpty")
_ESCRITURA = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC


def ruta_permitida(ruta, raices, dir_fd=None) -> bool:
    """¿La ruta (texto, bytes, ``PathLike`` o descriptor) cae dentro de alguna de ``raices`` (ya resueltas)?"""
    if isinstance(ruta, int):                        # descriptor ya abierto: su apertura pasó por la guardia
        return True
    try:
        texto = os.fsdecode(ruta)
    except TypeError:
        return False
    if dir_fd not in (None, -1) and not os.path.isabs(texto):
        return False                                 # relativa a un descriptor de carpeta: no se puede verificar
    real = os.path.realpath(texto)
    if real == os.devnull:
        return True
    return any(real == r or real.startswith(r.rstrip(os.sep) + os.sep) for r in raices)


def instalar_guardia_escritura(permitidas) -> tuple[str, ...]:
    """Gancho de auditoría (irreversible en el proceso): toda escritura de Python fuera de ``permitidas`` y todo
    subproceso levantan ``PermissionError``. Las lecturas no se tocan. Devuelve las raíces resueltas."""
    raices = tuple(os.path.realpath(os.fspath(p)) for p in permitidas)

    def gancho(evento, args):
        if evento == "open":
            ruta, modo, banderas = (tuple(args) + (None, None, None))[:3]
            escribe = (isinstance(modo, str) and any(c in modo for c in "wax+")) or \
                      (isinstance(banderas, int) and bool(banderas & _ESCRITURA))
            if escribe and not ruta_permitida(ruta, raices):
                raise PermissionError(f"factibilidad: escritura fuera del temporal ({os.fsdecode(ruta)})")
        elif evento in EVENTOS_UNA_RUTA:
            i = EVENTOS_UNA_RUTA[evento]
            dir_fd = args[i] if i is not None and len(args) > i else None
            if not ruta_permitida(args[0], raices, dir_fd):
                raise PermissionError(f"factibilidad: {evento} fuera del temporal")
        elif evento in EVENTOS_DESTINO:
            extremos = (args[0], args[1]) if evento in ("os.rename", "shutil.move") else (args[1],)
            if not all(ruta_permitida(x, raices) for x in extremos):
                raise PermissionError(f"factibilidad: {evento} fuera del temporal")
        elif evento in EVENTOS_PROCESO:
            raise PermissionError(f"factibilidad: el subproceso de la v1 no lanza procesos ({evento})")

    sys.addaudithook(gancho)
    return raices


# ---------------------------------------------------------------------------
# Matrices reales con la producción v1 (subproceso de sólo lectura)
# ---------------------------------------------------------------------------
class _Captura:
    """Escribe en un ``.npy`` del temporal la matriz de cada hora que la producción v1 entrega a su modelo."""

    def __init__(self):
        self.actual: dict | None = None

    def abrir(self, pol: str, ruta: Path, n: int, p: int) -> None:
        if self.actual is not None:
            raise RuntimeError("ya hay una captura abierta")
        m = np.lib.format.open_memmap(str(ruta), mode="w+", dtype=np.float32, shape=(HORAS, int(n), int(p)))
        self.actual = {"pol": pol, "ruta": ruta, "m": m, "horas": [], "nan": np.zeros(int(p), np.int64),
                       "inf": 0, "rellenadas": set(), "orden": set()}

    def guardar(self, pol: str, X, hora_local, columnas_previas, predictores) -> None:
        a = self.actual
        if a is None or a["pol"] != pol:
            raise RuntimeError(f"captura de {pol} sin abrir")
        X = np.asarray(X)
        h = int(np.asarray(hora_local).reshape(-1)[0])
        if X.shape != a["m"].shape[1:] or X.dtype != np.float32:
            raise RuntimeError(f"la matriz de la hora {h} es {X.shape} {X.dtype}; se esperaba {a['m'].shape[1:]} float32")
        if not 0 <= h < HORAS or h in a["horas"]:
            raise RuntimeError(f"hora {h} inválida o repetida")
        a["orden"].add("C" if X.flags["C_CONTIGUOUS"] else "F" if X.flags["F_CONTIGUOUS"] else "otro")
        a["m"][h] = X
        a["horas"].append(h)
        a["nan"] += np.isnan(X).sum(axis=0)
        a["inf"] += int(np.isinf(X).sum())
        if columnas_previas is not None:          # columnas que produccion.py:402-404 rellena con NaN
            a["rellenadas"].update(c for c in predictores
                                   if c not in columnas_previas and c not in COLUMNAS_TRAS_DERIVADAS)

    def cerrar(self, predictores) -> dict:
        a, self.actual = self.actual, None
        if a is None:
            raise RuntimeError("no hay captura abierta")
        if sorted(a["horas"]) != list(range(HORAS)):
            raise RuntimeError(f"la producción v1 entregó {len(a['horas'])} horas, no {HORAS}")
        forma = list(a["m"].shape)
        a["m"].flush()
        del a["m"]
        frac = a["nan"] / float(forma[0] * forma[1])
        return {"archivo": a["ruta"].name, "forma": forma, "dtype": "float32",
                "fraccion_nan_por_columna": {c: round(float(f), 6) for c, f in zip(predictores, frac)},
                "columnas_sin_dato": [c for c, f in zip(predictores, frac) if f >= 1.0],
                "infinitos": int(a["inf"]), "columnas_rellenadas_con_nan_por_la_v1": sorted(a["rellenadas"]),
                "orden_en_memoria_de_la_v1": sorted(a["orden"])}


def armar_matrices(P, temporal: Path, encargo: dict) -> dict:
    """Con el módulo ``produccion`` de la v1 (``P``) arma y escribe en ``temporal`` la matriz de predictores de cada
    contaminante y fecha del encargo, y devuelve su registro. Reemplaza en memoria ``P.Modelo`` (por el capturador) y
    envuelve ``P.derivadas_horarias`` (mismo resultado); los restaura al terminar."""
    temporal = Path(temporal)
    fechas = {k: date.fromisoformat(v) for k, v in encargo["fechas"].items()}
    predictores = {p: list(v) for p, v in encargo["predictores"].items()}
    calentamiento = int(encargo.get("calentamiento_dias", CALENTAMIENTO_SATELITAL))
    captura = _Captura()
    columnas: dict[str, set] = {}
    original_modelo, original_derivadas = P.Modelo, P.derivadas_horarias

    def derivadas_vigiladas(df):
        out = original_derivadas(df)
        columnas["previas"] = set(out.columns)
        return out

    class ModeloCaptura:
        """Sustituto del ``Modelo`` de la v1 (produccion.py:262-296): guarda la matriz y devuelve ceros."""

        def __init__(self, pol, entorno):
            self.pol = pol
            self.features = list(predictores[pol])
            self.smear = {"_global": 0.0}
            self.sha = "factibilidad-v2-captura"
            self.retransformacion = "ninguna (captura de la matriz, sin modelo)"
            self.carpeta = temporal / "modelo_captura" / pol

        def predecir(self, X, hora_local, macrozona_cod=None):
            captura.guardar(self.pol, X, hora_local, columnas.get("previas"), self.features)
            return np.zeros(len(X), dtype="float32")

    P.Modelo, P.derivadas_horarias = ModeloCaptura, derivadas_vigiladas
    salida = {"schema": SCHEMA_MATRICES, "creado_utc": ahora_utc(), "contaminantes": {}}
    try:
        t0 = time.perf_counter()
        entorno = P.entorno_desde_disco("")                     # producir_serie.py:72 (sufijo de la producción base)
        entorno.superficies_dir = temporal / "superficies_v1"   # producir_serie.py:73, aquí al temporal
        entorno.modelos_dir = temporal / "modelos_v1"
        celdas = entorno.celdas                                 # ámbito nacional (producir_serie.py:74)
        salida["entorno_s"] = round(time.perf_counter() - t0, 2)
        salida["codigo_v1"] = {"hash_codigo": P.hash_codigo() if hasattr(P, "hash_codigo") else None,
                               "enlaces_sha256": getattr(entorno, "enlaces_sha256", None)}
        for pol in encargo["contaminantes"]:
            t0, c0 = time.perf_counter(), time.process_time()
            ctx = P.ContextoPrediccion(pol, celdas, entorno)    # producir_serie.py:82-83
            por_pol = {"celdas": int(ctx.n), "estaciones": int(len(ctx.lat_e)),
                       "contexto_s": round(time.perf_counter() - t0, 2),
                       "contexto_cpu_s": round(time.process_time() - c0, 2), "fechas": {}}
            for fid, fecha in sorted(fechas.items(), key=lambda kv: kv[1]):
                t0 = time.perf_counter()
                ctx.reiniciar_ventana_satelital()               # producir_serie.py:91
                for k in range(calentamiento, 0, -1):           # producir_serie.py:92-93
                    ctx.satelites.dia(date.fromordinal(fecha.toordinal() - k))
                t_cal = time.perf_counter() - t0
                captura.abrir(pol, temporal / nombre_matriz(pol, fecha), ctx.n, len(predictores[pol]))
                t0, c0 = time.perf_counter(), time.process_time()
                try:
                    ctx.dia(fecha, forzar=True)                 # producir_serie.py:94-95 (produccion.py:359-437)
                except BaseException:
                    captura.actual = None
                    raise
                t_dia, c_dia = time.perf_counter() - t0, time.process_time() - c0
                info = captura.cerrar(predictores[pol])
                ventana = {(fecha - timedelta(days=k)).isoformat() for k in range(calentamiento + 1)}
                info.update({"fecha": fecha.isoformat(), "calentamiento_s": round(t_cal, 2), "dia_s": round(t_dia, 2),
                             "dia_cpu_s": round(c_dia, 2),
                             "dias_sin_maiac": sorted(set(getattr(ctx.satelites, "dias_sin_maiac", [])) & ventana),
                             "dias_sin_no2": sorted(set(getattr(ctx.satelites, "dias_sin_no2", [])) & ventana),
                             "meses_sin_fuente": sorted(f"{a}:{b}" for a, b in getattr(ctx.fuentes, "faltantes", set()))})
                info.update(estaciones_con_obs(ctx, fecha))
                por_pol["fechas"][fid] = info
                log.info("%s %s (%s): matriz %s escrita (%.0f s)", pol, fecha, fid, info["forma"], t_dia)
            salida["contaminantes"][pol] = por_pol
            del ctx
            gc.collect()
    finally:
        P.Modelo, P.derivadas_horarias = original_modelo, original_derivadas
    salida["fin_utc"] = ahora_utc()
    return salida


def estaciones_con_obs(ctx, fecha: date) -> dict:
    """Estaciones de la red del contexto con observación en cada hora del día (descriptivo de los predictores)."""
    O = getattr(ctx, "O", None)
    if O is None:
        return {}
    ts = pd.DatetimeIndex([datetime(fecha.year, fecha.month, fecha.day) + timedelta(hours=h + 4) for h in range(HORAS)])
    n = O.reindex(ts).notna().sum(axis=1)
    return {"estaciones_con_obs_por_hora": {"min": int(n.min()), "max": int(n.max())}}


def _armar_matrices_cli(ruta_encargo) -> int:
    """Entrada del subproceso v1: guardia de escritura, raíz v1 para ``_comun_modelo`` y producción v1."""
    enc = json.loads(Path(ruta_encargo).read_text(encoding="utf-8"))
    if enc.get("schema") != SCHEMA_ENCARGO_MATRICES:
        raise SystemExit(f"encargo desconocido: {enc.get('schema')!r}")
    temporal = Path(enc["temporal"]).resolve()
    guardia = instalar_guardia_escritura([temporal])
    sys.dont_write_bytecode = True
    for v in VARIABLES_V1:
        os.environ.pop(v, None)
    os.environ["AIR_POLLUTION_MODELO_1KM_ROOT"] = enc["raiz_v1"]                         # _comun_modelo.py:73
    os.environ["AIR_POLLUTION_SUPERFICIES_ROOT"] = str(temporal / "superficies_v1")       # _comun_modelo.py:74
    scripts_v1 = Path(enc["scripts_v1"]).resolve()
    sys.path.insert(0, str(scripts_v1))
    import produccion as P  # noqa: E402  (v1, sólo lectura)
    if Path(P.__file__).resolve().parent != scripts_v1:
        raise SystemExit(f"se importó otro «produccion»: {P.__file__}")
    from _comun_modelo import GRILLA_DIR, MODELO_ROOT  # noqa: E402
    if Path(MODELO_ROOT).resolve() != Path(enc["raiz_v1"]).resolve():
        raise SystemExit("la raíz de la producción v1 no es la raíz v1")
    doc = armar_matrices(P, temporal, enc)
    doc["guardia"] = {"escritura_permitida": ["temporal"], "procesos": "prohibidos", "bytecode": "desactivado",
                      "raices": len(guardia)}
    doc["entorno_v1"] = {"AIR_POLLUTION_MODELO_1KM_ROOT": "raiz_v1", "AIR_POLLUTION_SUPERFICIES_ROOT": "temporal",
                         "grilla": Path(GRILLA_DIR).name, "variables_quitadas": list(VARIABLES_V1),
                         "valores_por_omision": "los de la producción publicada (_comun_modelo, _features, produccion)"}
    tmp = temporal / f".{NOMBRE_MATRICES}.part"
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=a_json), encoding="utf-8")
    os.replace(tmp, temporal / NOMBRE_MATRICES)
    return 0


def entorno_subproceso(temporal: Path, hilos: int) -> dict:
    """Entorno de un subproceso: sin bytecode, temporales en ``temporal/tmp`` y el tope de hilos de BLAS y OpenMP."""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    (temporal / "tmp").mkdir(parents=True, exist_ok=True)
    env["TMPDIR"] = str(temporal / "tmp")
    for v in VARIABLES_HILOS:
        env[v] = str(int(hilos))
    return env


def lanzar_subproceso(orden: str, encargo: Path, temporal: Path, hilos: int) -> dict:
    """Corre este programa con ``orden`` en un proceso propio (espera a que termine) y devuelve su consumo."""
    cmd = [sys.executable, "-B", str(Path(__file__).resolve()), orden, "--encargo", str(encargo), "--hilos", str(int(hilos))]
    antes = resource.getrusage(resource.RUSAGE_CHILDREN)
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, env=entorno_subproceso(temporal, hilos), cwd=str(temporal), stdin=subprocess.DEVNULL,
                          check=False)
    pared = time.perf_counter() - t0
    despues = resource.getrusage(resource.RUSAGE_CHILDREN)
    if proc.returncode != 0:
        raise RuntimeError(f"el subproceso «{orden}» terminó con código {proc.returncode}")
    return {"orden": orden, "hilos": int(hilos), "segundos_pared": round(pared, 2),
            "segundos_cpu_subproceso": round((despues.ru_utime - antes.ru_utime) + (despues.ru_stime - antes.ru_stime), 2)}


def armar_en_subproceso(r: RutasV2, cfg: dict, contaminantes, fechas: dict[str, date], temporal: Path,
                        hilos: int) -> dict:
    """Arma las matrices con la producción v1 en un subproceso (``armar-matrices``) y devuelve su registro."""
    enc = {"schema": SCHEMA_ENCARGO_MATRICES, "temporal": str(temporal), "raiz_v1": str(r.raiz_v1),
           "scripts_v1": str(AQUI.parent), "contaminantes": list(contaminantes),
           "fechas": {k: v.isoformat() for k, v in fechas.items()},
           "predictores": {p: list(cfg["motores"]["eje_A"]["predictores"][p]) for p in contaminantes},
           "calentamiento_dias": CALENTAMIENTO_SATELITAL}
    ruta = temporal / "encargo_matrices.json"
    ruta.write_text(json.dumps(enc, ensure_ascii=False, indent=1), encoding="utf-8")
    consumo = lanzar_subproceso("armar-matrices", ruta, temporal, hilos)
    doc = leer_json(temporal / NOMBRE_MATRICES)
    if doc is None or doc.get("schema") != SCHEMA_MATRICES:
        raise RuntimeError("el subproceso de la v1 no dejó el registro de las matrices")
    doc["subproceso"] = consumo
    (temporal / NOMBRE_MATRICES).write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=a_json),
                                            encoding="utf-8")     # con el consumo, por si se reutilizan
    return doc


# ---------------------------------------------------------------------------
# Motores: ajuste sin evaluación
# ---------------------------------------------------------------------------
def recetas_factibilidad(cfg: dict, hilos: int, epocas_mlp: int = EPOCAS_MLP) -> dict:
    """Recetas de ``motores_v2`` con los hilos del ajuste y la MLP con épocas fijas (sin parada temprana)."""
    rec = copy.deepcopy(mv.recetas_de(cfg, hilos))
    rec["mlp"]["max_iter"] = int(epocas_mlp)
    return rec


def crear_motor(motor: str, recetas: dict):
    """Modelo de producción (sin pliegue): semilla de la receta, réplica 0 y k = 0."""
    return mv.crear_modelo(motor, recetas, Variante(mv.VARIANTE_REFERENCIA), SEMILLA_MOTORES, replica=0, k=0)


def ajustar_motor(modelo, motor: str, X, y):
    """Ajuste sin evaluación: LightGBM y XGBoost sin conjuntos de validación, RF sin OOB y la MLP sin validación
    (``ValidacionMLP`` vacía: recorre sus épocas fijas). Descarta ``info``: nada de lo que el ajuste registre sale de
    aquí."""
    if motor == "mlp":
        val = mv.ValidacionMLP(filas=np.zeros(len(y), dtype=bool),
                               registro={"motivo": "factibilidad: épocas fijas y sin validación (sólo tiempos)"})
        modelo.ajustar(X, y, validacion=val)
    else:
        modelo.ajustar(X, y)
    modelo.info = {}
    return modelo


def matriz_de_tabla(tabla, feats) -> np.ndarray:
    """Predictores de una tabla de Arrow en float32, en el orden de ``feats``."""
    X = np.empty((tabla.num_rows, len(feats)), dtype=np.float32)
    for j, c in enumerate(feats):
        X[:, j] = np.asarray(tabla.column(c).to_numpy(zero_copy_only=False), dtype=np.float32)
    return X


def filas_de_produccion(r: RutasV2, pol: str, feats, n_prod: int) -> dict:
    """Filas de entrenamiento de producción del panel v1 (sólo lectura): el prefijo de ``default_rng([42])
    .permutation`` sobre todas las filas, ordenado."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    t = pq.read_table(r.panel(pol), columns=list(dict.fromkeys(["obs", *feats])))
    faltan = [c for c in feats if c not in t.column_names]
    if faltan:
        raise SystemExit(f"{pol}: el panel no tiene los predictores {faltan}")
    n = t.num_rows
    filas = np.sort(np.random.default_rng(SEMILLA_FILAS).permutation(n)[:min(int(n_prod), n)])
    sub = t.take(pa.array(filas))
    return {"X": matriz_de_tabla(sub, feats), "y": np.asarray(sub.column("obs").to_numpy(zero_copy_only=False), "float64"),
            "filas": int(len(filas)), "filas_panel": int(n)}


# ---------------------------------------------------------------------------
# Predictores compilados
# ---------------------------------------------------------------------------
class LightGBMCompilado:
    """El ``_Compilado`` de la producción v1 (produccion.py:226-254) sobre el booster v2: ``lleaves`` con ``compile()``
    por omisión y caché en el temporal; predice en float64 contiguo con ``hilos`` hilos."""

    def __init__(self, texto: Path, cache: Path, hilos: int):
        import lleaves
        self.m = lleaves.Model(model_file=str(texto))
        self.m.compile(cache=str(cache))                 # si la caché existe, se carga sin recompilar (produccion.py:242)
        self.hilos = int(hilos)

    @classmethod
    def compilar(cls, booster, carpeta: Path, hilos: int) -> tuple["LightGBMCompilado", dict]:
        texto, cache = carpeta / "lightgbm_modelo.txt", carpeta / "lightgbm_compilado.o"
        booster.save_model(str(texto))
        t0 = time.perf_counter()
        c = cls(texto, cache, hilos)
        return c, {"biblioteca": "lleaves", "arboles": int(c.m.num_trees()), "segundos": round(time.perf_counter() - t0, 2),
                   "opciones": "compile() por omisión (use_fp64, fblocksize 34, finline, fcodemodel large), como "
                               "produccion.py:242-246", "entrada": "float64 contiguo (produccion.py:254)",
                   "archivos": {"texto": texto.name, "cache": cache.name}, "bytes_objeto": cache.stat().st_size}

    def predict(self, X) -> np.ndarray:
        return self.m.predict(np.ascontiguousarray(X, dtype="float64"), n_jobs=self.hilos)


def nodos_treelite(modelo) -> int:
    return int(sum(int(modelo.get_tree_accessor(i).get_field("num_nodes")[0]) for i in range(modelo.num_tree)))


def unidades_de_compilacion(n_arboles: int, nodos: int, hilos: int, nodos_por_unidad: int = NODOS_POR_UNIDAD) -> int:
    """``parallel_comp`` de tl2cgen: una unidad por cada ``nodos_por_unidad`` nodos, al menos una por hilo de compilación
    y como mucho una por árbol (sólo reparte el código C; no cambia lo que se predice)."""
    return int(max(1, min(int(n_arboles), max(int(hilos), math.ceil(int(nodos) / int(nodos_por_unidad))))))


def treelite_de_rf(rf):
    """El bosque de scikit-learn en treelite, con el ``default_left`` de cada nodo tomado de ``missing_go_to_left``
    (scikit-learn ≥ 1.3 manda los NaN por esa rama; el importador de treelite deja ``default_left = 1`` en todos)."""
    import treelite
    tm = treelite.sklearn.import_model(rf)
    cambiados = internos = 0
    for i, est in enumerate(rf.estimators_):
        t, ta = est.tree_, tm.get_tree_accessor(i)
        interno = t.children_left != -1
        mismos = (np.array_equal(ta.get_field("cleft"), t.children_left.astype(np.int32))
                  and np.array_equal(ta.get_field("cright"), t.children_right.astype(np.int32))
                  and np.array_equal(ta.get_field("split_index")[interno], t.feature[interno].astype(np.int32))
                  and np.array_equal(ta.get_field("threshold")[interno], t.threshold[interno]))
        if not mismos:
            raise RuntimeError(f"árbol {i}: los nodos de treelite no siguen el orden de scikit-learn")
        dl = np.ascontiguousarray(t.missing_go_to_left, dtype=np.uint8)
        cambiados += int((ta.get_field("default_left")[interno] != dl[interno]).sum())
        internos += int(interno.sum())
        ta.set_field("default_left", dl)
    return tm, {"default_left_desde_missing_go_to_left": True, "nodos_internos": internos,
                "default_left_corregidos": cambiados}


class ArbolesCompilados:
    """Árboles compilados a C con treelite → tl2cgen y cargados con ``tl2cgen.Predictor`` (OpenMP, ``hilos``)."""

    def __init__(self, biblioteca: Path, hilos: int):
        import tl2cgen
        self.p = tl2cgen.Predictor(str(biblioteca), nthread=int(hilos))
        self.dtype = np.float32 if self.p.threshold_type == "float32" else np.float64
        self.hilos = int(hilos)

    @classmethod
    def compilar(cls, modelo_treelite, carpeta: Path, nombre: str, hilos_compilacion: int, hilos: int,
                 extra: dict | None = None) -> tuple["ArbolesCompilados", dict]:
        import tl2cgen
        nodos = nodos_treelite(modelo_treelite)
        unidades = unidades_de_compilacion(modelo_treelite.num_tree, nodos, hilos_compilacion)
        fuente = carpeta / f"{nombre}_c"
        fuente.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        tl2cgen.generate_c_code(modelo_treelite, str(fuente), {"parallel_comp": unidades})
        bytes_c = int(sum(p.stat().st_size for p in fuente.glob("*.c")))
        lib = Path(tl2cgen.create_shared(TOOLCHAIN, str(fuente), nthread=int(hilos_compilacion),
                                         long_build_time_warning=False))
        destino = carpeta / f"{nombre}{lib.suffix}"
        shutil.move(str(lib), destino)
        shutil.rmtree(fuente, ignore_errors=True)
        c = cls(destino, hilos)
        return c, {"biblioteca": "treelite → tl2cgen", "toolchain": TOOLCHAIN, "opciones_compilador": "-O3 -fPIC -std=c99",
                   "arboles": int(modelo_treelite.num_tree), "nodos": nodos, "parallel_comp": unidades,
                   "hilos_compilacion": int(hilos_compilacion), "bytes_codigo_c": bytes_c,
                   "bytes_biblioteca": destino.stat().st_size, "segundos": round(time.perf_counter() - t0, 2),
                   "umbral": c.p.threshold_type, "salida": c.p.leaf_output_type, "archivo": destino.name, **(extra or {})}

    def predict(self, X) -> np.ndarray:
        import tl2cgen
        Xc = np.ascontiguousarray(X, dtype=self.dtype)
        return self.p.predict(tl2cgen.DMatrix(Xc)).reshape(len(Xc))


class MLPCompilada:
    """La MLP de ``motores_v2.ModeloMLP`` en float32, por lotes y en hilos (BLAS a un hilo por lote): columnas vacías
    en el entrenamiento a NaN, recorte de entradas al rango del entrenamiento, imputación por mediana, escala, capas
    densas ReLU y salida identidad recortada a [lo, hi], con los parámetros del modelo ajustado (``ModeloMLP.predecir``)."""

    CAMPOS = ("vacias", "acotar", "bajo", "alto", "mediana", "media", "escala", "lo", "hi", "n_capas")

    def __init__(self, arreglos: dict, hilos: int, lote: int = LOTE_MLP):
        a = arreglos
        self.vacias = np.asarray(a["vacias"], dtype=bool)
        self.acotar = bool(np.asarray(a["acotar"]).item())
        self.bajo, self.alto = (np.asarray(a[k], dtype=np.float32) for k in ("bajo", "alto"))
        self.mediana, self.media, self.escala = (np.asarray(a[k], dtype=np.float32) for k in ("mediana", "media", "escala"))
        self.lo, self.hi = np.float32(np.asarray(a["lo"]).item()), np.float32(np.asarray(a["hi"]).item())
        n = int(np.asarray(a["n_capas"]).item())
        self.capas = [(np.ascontiguousarray(a[f"W{i}"], dtype=np.float32), np.asarray(a[f"b{i}"], dtype=np.float32))
                      for i in range(n)]
        self.hilos, self.lote = int(hilos), int(lote)

    @staticmethod
    def arreglos_de(modelo) -> dict:
        """Parámetros de un ``motores_v2.ModeloMLP`` ajustado, en float32."""
        red, imp, esc = modelo.modelo, modelo.imp, modelo.esc
        if red.activation != "relu" or getattr(red, "out_activation_", "identity") != "identity":
            raise ValueError("la MLP compilada supone ReLU y salida identidad (receta v1)")
        if not (esc.with_mean and esc.with_std):
            raise ValueError("la MLP compilada supone StandardScaler con media y desviación")
        a = {"vacias": np.asarray(modelo.vacias, dtype=bool), "acotar": np.array(bool(modelo.receta["acotar_entradas"])),
             "bajo": np.nan_to_num(np.asarray(modelo.bajo, dtype=np.float32), nan=-np.inf),
             "alto": np.nan_to_num(np.asarray(modelo.alto, dtype=np.float32), nan=np.inf),
             "mediana": np.asarray(imp.statistics_, dtype=np.float32), "media": np.asarray(esc.mean_, dtype=np.float32),
             "escala": np.asarray(esc.scale_, dtype=np.float32), "lo": np.array(modelo.lo, dtype=np.float32),
             "hi": np.array(modelo.hi, dtype=np.float32), "n_capas": np.array(len(red.coefs_))}
        for i, (W, b) in enumerate(zip(red.coefs_, red.intercepts_)):
            a[f"W{i}"], a[f"b{i}"] = np.asarray(W, dtype=np.float32), np.asarray(b, dtype=np.float32)
        return a

    @classmethod
    def compilar(cls, modelo, carpeta: Path, hilos: int) -> tuple["MLPCompilada", dict]:
        t0 = time.perf_counter()
        a = cls.arreglos_de(modelo)
        ruta = carpeta / "mlp_float32.npz"
        np.savez(ruta, **a)
        c = cls.desde_archivo(ruta, hilos)
        capas = [list(W.shape) for W, _ in c.capas]
        return c, {"biblioteca": "numpy (OpenBLAS sgemm, un hilo por lote)", "dtype": "float32", "lote_filas": c.lote,
                   "capas": capas, "segundos": round(time.perf_counter() - t0, 3), "archivo": ruta.name,
                   "pasos": "vacías → NaN, recorte de entradas, imputación por mediana, escala, ReLU, recorte de salida"}

    @classmethod
    def desde_archivo(cls, ruta: Path, hilos: int, lote: int = LOTE_MLP) -> "MLPCompilada":
        with np.load(ruta) as z:
            return cls({k: z[k] for k in z.files}, hilos, lote)

    def _lote(self, X: np.ndarray, out: np.ndarray, i: int) -> None:
        Z = np.array(X[i:i + self.lote], dtype=np.float32, copy=True)
        if self.vacias.any():
            Z[:, self.vacias] = np.nan
        if self.acotar:
            np.clip(Z, self.bajo, self.alto, out=Z)          # NaN sigue NaN (como np.where de ModeloMLP.predecir)
        falta = np.isnan(Z)
        if falta.any():
            np.copyto(Z, np.broadcast_to(self.mediana, Z.shape), where=falta)
        Z -= self.media
        Z /= self.escala
        H = Z
        for W, b in self.capas[:-1]:
            H = H @ W
            H += b
            np.maximum(H, 0.0, out=H)
        W, b = self.capas[-1]
        z = (H @ W).reshape(-1) + b[0]
        np.clip(z, self.lo, self.hi, out=z)
        out[i:i + len(z)] = z

    def predict(self, X) -> np.ndarray:
        from threadpoolctl import threadpool_limits
        X = np.asarray(X, dtype=np.float32)
        out = np.empty(len(X), dtype=np.float32)
        inicios = range(0, len(X), self.lote)
        with threadpool_limits(limits=1, user_api="blas"):
            if self.hilos > 1 and len(inicios) > 1:
                with ThreadPoolExecutor(max_workers=self.hilos) as ex:
                    list(ex.map(lambda i: self._lote(X, out, i), inicios))
            else:
                for i in inicios:
                    self._lote(X, out, i)
        return out


def compilar_motores(modelos: dict, carpeta: Path, hilos_compilacion: int, hilos: int, medidor=None,
                     pol: str = "") -> tuple[dict, dict]:
    """Compila los cuatro motores en ``carpeta`` y los carga con ``hilos`` hilos de predicción."""
    import treelite
    carpeta.mkdir(parents=True, exist_ok=True)
    compilados, info = {}, {}
    for motor in MOTORES:
        fase = medidor.fase(contaminante=pol, tarea=motor, fase="compilacion") if medidor else contextlib.nullcontext({})
        with fase:
            if motor == "lightgbm":
                compilados[motor], info[motor] = LightGBMCompilado.compilar(modelos[motor].modelo, carpeta, hilos)
            elif motor == "xgboost":
                tm = treelite.frontend.from_xgboost(modelos[motor].modelo)
                compilados[motor], info[motor] = ArbolesCompilados.compilar(tm, carpeta, motor, hilos_compilacion, hilos)
            elif motor == "random_forest":
                tm, extra = treelite_de_rf(modelos[motor].modelo)
                compilados[motor], info[motor] = ArbolesCompilados.compilar(tm, carpeta, motor, hilos_compilacion, hilos,
                                                                            extra)
            else:
                compilados[motor], info[motor] = MLPCompilada.compilar(modelos[motor], carpeta, hilos)
        log.info("%s: %s compilado (%s s)", pol, motor, info[motor].get("segundos"))
    return compilados, info


def cargar_compilados(carpeta: Path, info: dict, hilos: int) -> dict:
    """Predictores compilados desde sus archivos del temporal (lo que hace el subproceso que mide)."""
    out = {}
    for motor in MOTORES:
        i = info[motor]
        if motor == "lightgbm":
            out[motor] = LightGBMCompilado(carpeta / i["archivos"]["texto"], carpeta / i["archivos"]["cache"], hilos)
        elif motor in ("xgboost", "random_forest"):
            out[motor] = ArbolesCompilados(carpeta / i["archivo"], hilos)
        else:
            out[motor] = MLPCompilada.desde_archivo(carpeta / i["archivo"], hilos)
    return out


# ---------------------------------------------------------------------------
# Equivalencia con filas sintéticas
# ---------------------------------------------------------------------------
def filas_sinteticas(X: np.ndarray, n: int = FILAS_VERIFICACION, semilla=SEMILLA_SINTETICA,
                     fraccion_nan: float = FRACCION_NAN_VERIFICACION) -> np.ndarray:
    """Filas que no son de ningún lugar ni hora: cada columna de una muestra de ``X`` permutada por separado (rompe la
    relación entre columnas y con el blanco), más faltantes al azar."""
    rng = np.random.default_rng(semilla)
    idx = rng.choice(len(X), size=int(n), replace=len(X) < int(n))
    Z = np.array(X[idx], dtype=np.float32, copy=True)
    for j in range(Z.shape[1]):
        Z[:, j] = Z[rng.permutation(len(Z)), j]
    Z[rng.random(Z.shape) < float(fraccion_nan)] = np.nan
    return Z


def verificar_equivalencia(modelos: dict, compilados: dict, X: np.ndarray, n: int = FILAS_VERIFICACION) -> dict:
    """Diferencia máxima (log1p) entre cada predictor compilado y su motor sobre filas sintéticas; no se guarda ninguna
    predicción ni se compara con observaciones."""
    Z = filas_sinteticas(X, n)
    dif, ok = {}, {}
    for motor in MOTORES:
        a = np.asarray(modelos[motor].predecir(Z), dtype="float64").reshape(-1)
        b = np.asarray(compilados[motor].predict(Z), dtype="float64").reshape(-1)
        if a.shape != b.shape:
            raise RuntimeError(f"{motor}: el compilado devuelve {b.shape} y el motor {a.shape}")
        nan_distinto = bool((np.isnan(a) != np.isnan(b)).any())
        d = float("inf") if nan_distinto else float(np.nanmax(np.abs(a - b))) if len(a) else 0.0
        dif[motor], ok[motor] = d, bool(d <= TOLERANCIAS[motor])
        del a, b
    return {"filas_sinteticas": int(len(Z)), "semilla": SEMILLA_SINTETICA, "fraccion_nan_agregada": FRACCION_NAN_VERIFICACION,
            "construccion": "cada columna de una muestra del entrenamiento permutada por separado, más faltantes",
            "dif_max_log1p": dif, "tolerancia_log1p": dict(TOLERANCIAS), "equivalentes": ok}


# ---------------------------------------------------------------------------
# Medición (subproceso de predicción, 12 hilos)
# ---------------------------------------------------------------------------
def rotar(seq, k: int) -> list:
    seq = list(seq)
    k = k % len(seq) if seq else 0
    return seq[k:] + seq[:k]


def predecir_comprobando(predictor, X) -> None:
    """Predice y comprueba sólo el largo de la salida (no se mira ningún valor)."""
    z = predictor.predict(X)
    if len(z) != len(X):
        raise RuntimeError(f"la predicción tiene {len(z)} filas y el bloque {len(X)}")
    del z


def medir_dia(predictores: dict, bloques, medidor, pol: str, fecha_id: str, repeticiones: int, hilos: int) -> None:
    """Cada predictor predice los bloques horarios del día, ``repeticiones`` veces en orden rotado. Sólo tiempos."""
    filas = int(sum(len(b) for b in bloques))
    for rep in range(int(repeticiones)):
        for motor in rotar(MOTORES, rep):
            gc.collect()
            tiempos = []
            with medidor.fase(contaminante=pol, tarea=motor, fase="dia", fecha=fecha_id, repeticion=rep,
                              bloques=len(bloques), filas=filas, hilos=int(hilos)) as reg:
                for X in bloques:
                    t0 = time.perf_counter()
                    predecir_comprobando(predictores[motor], X)
                    tiempos.append(time.perf_counter() - t0)
                reg["segundos_por_bloque"] = [round(t, 4) for t in tiempos]
        log.info("%s %s: repetición %d medida", pol, fecha_id, rep)


def esperar_maquina_libre(umbral: float = CARGA_LIBRE, maximo_s: float = ESPERA_MAXIMA_S,
                          intervalo_s: float = INTERVALO_ESPERA_S, carga=os.getloadavg, reloj=time.monotonic,
                          dormir=time.sleep) -> dict:
    """Espera, con tope, a que la carga media de 1 minuto baje de ``umbral``; registra lo que pasó."""
    t0 = reloj()
    muestras = []
    while True:
        c = float(carga()[0])
        muestras.append(round(c, 2))
        transcurrido = reloj() - t0
        if c < umbral:
            return {"libre": True, "umbral_carga_1min": umbral, "espera_s": round(transcurrido, 1), "carga_1min": round(c, 2),
                    "muestras": len(muestras)}
        if transcurrido >= maximo_s:
            return {"libre": False, "umbral_carga_1min": umbral, "espera_s": round(transcurrido, 1),
                    "carga_1min": round(c, 2), "muestras": len(muestras), "carga_min_vista": min(muestras),
                    "nota": "la carga no bajó del umbral en el tope de espera: se midió igual y queda registrado"}
        dormir(intervalo_s)


def cargar_matriz(ruta: Path, forma: list) -> np.ndarray:
    """La matriz de un día, entera en memoria (no proyectada) antes de medir."""
    X = np.load(ruta)
    if list(X.shape) != list(forma) or X.dtype != np.float32 or not X.flags["C_CONTIGUOUS"]:
        raise RuntimeError(f"{ruta.name}: forma {X.shape} {X.dtype}; se esperaba {forma} float32 contiguo")
    return X


def medir_prediccion(encargo: dict, temporal: Path) -> dict:
    """Mide la predicción de los días del encargo con los predictores compilados (en el subproceso de 12 hilos)."""
    pol, hilos = encargo["contaminante"], int(encargo["hilos"])
    compilados = cargar_compilados(temporal / encargo["carpeta_modelos"], encargo["compilacion"], hilos)
    espera = (esperar_maquina_libre(**encargo["espera"]) if encargo.get("espera") is not None
              else {"libre": None, "nota": "sin espera (pedido)"})
    maquina0 = pl.info_maquina()
    with pl.Medidor() as med:
        for fid, f in encargo["fechas"].items():
            with med.fase(contaminante=pol, tarea="matriz", fase="carga", fecha=fid):
                bloques = cargar_matriz(temporal / f["archivo"], f["forma"])
            for motor in MOTORES:
                with med.fase(contaminante=pol, tarea=motor, fase="calentamiento", fecha=fid,
                              filas=min(FILAS_CALENTAMIENTO, bloques.shape[1])):
                    predecir_comprobando(compilados[motor], bloques[0][:FILAS_CALENTAMIENTO])
            medir_dia(compilados, bloques, med, pol, fid, int(encargo["repeticiones"]), hilos)
            del bloques
            gc.collect()
        filas = [pl.sin_nan(f) for f in med.filas]
    return {"schema": SCHEMA_TIEMPOS, "contaminante": pol, "hilos": hilos, "espera_maquina_libre": espera,
            "maquina_inicio": maquina0, "maquina_fin": pl.info_maquina(), "bibliotecas_de_hilos": info_hilos(),
            "filas": filas}


def _medir_prediccion_cli(ruta_encargo) -> int:
    ruta = Path(ruta_encargo)
    enc = json.loads(ruta.read_text(encoding="utf-8"))
    if enc.get("schema") != SCHEMA_ENCARGO_PREDICCION:
        raise SystemExit(f"encargo desconocido: {enc.get('schema')!r}")
    temporal = Path(enc["temporal"]).resolve()
    doc = medir_prediccion(enc, temporal)
    tmp = temporal / f".{enc['salida']}.part"
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=a_json), encoding="utf-8")
    os.replace(tmp, temporal / enc["salida"])
    return 0


def info_hilos() -> list[dict]:
    """Bibliotecas de hilos cargadas (sin rutas)."""
    try:
        from threadpoolctl import threadpool_info
    except ImportError:
        return []
    return [{k: d.get(k) for k in ("user_api", "internal_api", "num_threads", "version", "threading_layer")}
            for d in threadpool_info()]


def version_toolchain() -> str | None:
    try:
        out = subprocess.run([TOOLCHAIN, "--version"], capture_output=True, text=True, timeout=60, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return out.splitlines()[0].strip() if out else None


def versiones() -> dict:
    v = versiones_bibliotecas((*("numpy", "scipy", "scikit-learn", "lightgbm", "xgboost", "threadpoolctl", "psutil"),
                               "lleaves", "llvmlite", "treelite", "tl2cgen"))
    v["toolchain"] = version_toolchain()
    v["nota_tl2cgen"] = ("tl2cgen 1.0.0 deserializa el modelo con su propio treelite (4.1.2) y avisa que el modelo viene "
                         "de una versión más nueva; la equivalencia con el motor se verifica igual")
    return v


# ---------------------------------------------------------------------------
# Medición de un contaminante y de la pieza
# ---------------------------------------------------------------------------
def _receta_registro(recetas: dict) -> dict:
    """Recetas efectivas de los cuatro motores, para el registro (sin objetos)."""
    def limpio(o):
        if isinstance(o, dict):
            return {str(k): limpio(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [limpio(v) for v in o]
        return o if isinstance(o, (str, int, float, bool)) or o is None else str(o)
    m = recetas["mlp"]
    return {"lightgbm": limpio({"params": recetas["lightgbm"]["params"], "num_boost_round": recetas["lightgbm"]["num_boost_round"]}),
            "xgboost": limpio({"params": recetas["xgboost"]["params"], "num_boost_round": recetas["xgboost"]["num_boost_round"]}),
            "random_forest": limpio(recetas["random_forest"]),
            "mlp": limpio({"params": m["params"], "epocas": m["max_iter"], "hilos": m["hilos"],
                           "recorte_salida_log": m["recorte_salida_log"], "acotar_entradas": m["acotar_entradas"],
                           "nota": "épocas fijas y sin parada temprana: el costo de predecir no depende de las épocas"})}


def medir_contaminante(r: RutasV2, cfg: dict, pol: str, fechas: dict[str, date], matrices: dict, temporal: Path,
                       hilos_ajuste: int, hilos_prediccion: int, repeticiones: int = REPETICIONES,
                       epocas_mlp: int = EPOCAS_MLP, esperar: bool = True, medir_en_subproceso: bool = True) -> dict:
    """Ajusta, compila y verifica los cuatro motores (``hilos_ajuste``) y mide su predicción de los días
    (``hilos_prediccion``, en un subproceso). Devuelve la entrada del contaminante para ``mediciones.json``."""
    feats = list(cfg["motores"]["eje_A"]["predictores"][pol])
    recetas = recetas_factibilidad(cfg, hilos_ajuste, epocas_mlp)
    n_prod = int(cfg["decision"]["N_de_produccion"])
    m_pol = matrices["contaminantes"][pol]
    carpeta = temporal / f"modelos_{pol}"
    inicio = ahora_utc()
    with pl.Medidor() as med:
        with med.fase(contaminante=pol, tarea="insumos", fase="filas_entrenamiento"):
            pan = filas_de_produccion(r, pol, feats, n_prod)
        modelos = {}
        for motor in MOTORES:
            gc.collect()
            with med.fase(contaminante=pol, tarea=motor, fase="ajuste", filas=pan["filas"], hilos=int(hilos_ajuste)):
                modelos[motor] = ajustar_motor(crear_motor(motor, recetas), motor, pan["X"], pan["y"])
            log.info("%s: %s ajustado (%.1f s)", pol, motor, med.filas[-1]["segundos_pared"])
        compilados, compilacion = compilar_motores(modelos, carpeta, hilos_ajuste, hilos_ajuste, med, pol)
        with med.fase(contaminante=pol, tarea="compilados", fase="equivalencia", filas=FILAS_VERIFICACION):
            equivalencia = verificar_equivalencia(modelos, compilados, pan["X"])
        malos = [m for m, ok in equivalencia["equivalentes"].items() if not ok]
        if malos:
            raise RuntimeError(f"{pol}: el predictor compilado de {malos} no reproduce a su motor en las filas "
                               f"sintéticas ({ {m: equivalencia['dif_max_log1p'][m] for m in malos} })")
        del modelos, compilados, pan["X"], pan["y"]
        gc.collect()
        filas_padre = [pl.sin_nan(f) for f in med.filas]
    encargo = {"schema": SCHEMA_ENCARGO_PREDICCION, "temporal": str(temporal), "contaminante": pol,
               "hilos": int(hilos_prediccion), "repeticiones": int(repeticiones), "carpeta_modelos": carpeta.name,
               "compilacion": compilacion, "salida": f"tiempos_{pol}.json",
               "espera": ({"umbral": CARGA_LIBRE, "maximo_s": ESPERA_MAXIMA_S, "intervalo_s": INTERVALO_ESPERA_S}
                          if esperar else None),
               "fechas": {fid: {"fecha": fechas[fid].isoformat(), "archivo": m_pol["fechas"][fid]["archivo"],
                                "forma": m_pol["fechas"][fid]["forma"]} for fid in sorted(fechas, key=fechas.get)}}
    ruta_enc = temporal / f"encargo_prediccion_{pol}.json"
    ruta_enc.write_text(json.dumps(encargo, ensure_ascii=False, indent=1, default=a_json), encoding="utf-8")
    if medir_en_subproceso:
        consumo = lanzar_subproceso("medir-prediccion", ruta_enc, temporal, hilos_prediccion)
    else:                                           # pruebas: en el mismo proceso
        _medir_prediccion_cli(ruta_enc)
        consumo = {"orden": "medir-prediccion", "en_el_mismo_proceso": True}
    tiempos = leer_json(temporal / encargo["salida"])
    if tiempos is None or tiempos.get("schema") != SCHEMA_TIEMPOS:
        raise RuntimeError(f"{pol}: el subproceso de predicción no dejó sus tiempos")
    shutil.rmtree(carpeta, ignore_errors=True)
    return {
        "inicio_utc": inicio, "fin_utc": ahora_utc(),
        "parametros": {
            "hilos_ajuste": int(hilos_ajuste), "hilos_prediccion": int(hilos_prediccion), "repeticiones": int(repeticiones),
            "N_de_produccion": n_prod, "filas_entrenamiento": pan["filas"], "filas_panel": pan["filas_panel"],
            "semilla_filas": SEMILLA_FILAS, "semilla_motores": SEMILLA_MOTORES, "epocas_mlp": int(epocas_mlp),
            "celdas": int(m_pol["celdas"]), "horas": HORAS, "lote_mlp": LOTE_MLP,
            "predictores": {"n": len(feats), "sha256": sha256_json(feats)},
            "fechas": {fid: fechas[fid].isoformat() for fid in fechas}, "recetas": _receta_registro(recetas)},
        "compilacion": compilacion, "equivalencia": equivalencia,
        "subproceso_prediccion": consumo, "espera_maquina_libre": tiempos["espera_maquina_libre"],
        "maquina_inicio": tiempos["maquina_inicio"], "maquina_fin": tiempos["maquina_fin"],
        "bibliotecas_de_hilos": tiempos["bibliotecas_de_hilos"],
        "filas": filas_padre + tiempos["filas"],
        "modelos": "descartados: vivieron en un temporal que se borró; ninguno se escribió en la raíz v2 ni en la v1",
    }


def ruta_mediciones(r: RutasV2) -> Path:
    return r.raiz_v2 / CARPETA / NOMBRE_MEDICIONES


def ruta_resumen(r: RutasV2) -> Path:
    return r.salidas_v2 / NOMBRE_RESUMEN


def documento_vacio() -> dict:
    return {"schema": SCHEMA_MEDICIONES,
            "descripcion": ("Factibilidad de producción (Complemento de la Enmienda 1, punto 3): cada fase medida (pared, "
                            "CPU, memoria, contención y carga), por contaminante, con predictores compilados y matrices "
                            "reales de 3 días armadas por la producción v1. Sin predicciones ni métricas de desempeño: un "
                            "tiempo no es un resultado."),
            "contaminantes": {}}


def leer_mediciones(r: RutasV2) -> dict:
    """Las mediciones vigentes; las de la medición del punto 11 (esquema anterior) no cuentan: se respaldan al escribir."""
    doc = leer_json(ruta_mediciones(r))
    if doc is None or doc.get("schema") in SCHEMAS_PUNTO_11:
        return documento_vacio()
    if doc.get("schema") != SCHEMA_MEDICIONES:
        raise SystemExit(f"{NOMBRE_MEDICIONES}: esquema desconocido {doc.get('schema')!r}")
    return doc


def respaldar_si_es_anterior(ruta: Path, r: RutasV2) -> Path | None:
    """Si ``ruta`` es un artefacto de la medición del punto 11, lo conserva como ``<nombre>_reemplazado_<fecha>``."""
    doc = leer_json(ruta)
    if doc is None or doc.get("schema") not in SCHEMAS_PUNTO_11:
        return None
    sello = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destino = ruta.with_name(f"{ruta.stem}_reemplazado_{sello}{ruta.suffix}")
    renombrar(ruta, destino, r)
    log.info("respaldo del punto 11: %s", destino.name)
    return destino


def guardar_mediciones(doc: dict, r: RutasV2) -> None:
    respaldo = respaldar_si_es_anterior(ruta_mediciones(r), r)
    if respaldo is not None:
        doc.setdefault("respaldos_punto_11", []).append(r.relativa(respaldo))
    publicar_json(doc, ruta_mediciones(r), r)


def insumos_de(r: RutasV2, pol: str) -> dict[str, Path]:
    ins = {f"panel_{pol}": r.panel(pol)}
    g = r.grilla_v1
    for nombre in ("celdas", "enlaces_productos", "estaticas", "estaticas_lulc"):
        if (g / f"{nombre}.parquet").exists():
            ins[nombre] = g / f"{nombre}.parquet"
    if (g / "metadata.json").exists():
        ins["grilla_metadata"] = g / "metadata.json"
    return ins


def modulos_v1() -> list[Path]:
    return [AQUI.parent / m for m in MODULOS_V1 if (AQUI.parent / m).exists()]


def matrices_existentes(base: Path, contaminantes, fechas: dict[str, date]) -> dict | None:
    """El registro de matrices ya armadas en ``base`` si cubre los contaminantes y las fechas pedidas (con sus
    archivos); si no, None. Las matrices son predictores (no resultados): reutilizarlas no cambia la medición."""
    doc = leer_json(base / NOMBRE_MATRICES)
    if not doc or doc.get("schema") != SCHEMA_MATRICES:
        return None
    for pol in contaminantes:
        m = (doc.get("contaminantes") or {}).get(pol)
        if not m:
            return None
        for fid, f in fechas.items():
            info = (m.get("fechas") or {}).get(fid)
            if not info or info.get("fecha") != f.isoformat() or not (base / info["archivo"]).exists():
                return None
    return {**doc, "reutilizadas": True}


def medir(r: RutasV2, cfg: dict, contaminantes=CONTAMINANTES, hilos_ajuste: int = HILOS_AJUSTE,
          hilos_prediccion: int | None = None, repeticiones: int = REPETICIONES, temporal=None,
          conservar_temporal: bool = False, armar=armar_en_subproceso, esperar: bool = True,
          medir_en_subproceso: bool = True, epocas_mlp: int = EPOCAS_MLP, reusar_matrices: bool = False) -> dict:
    """Mide los contaminantes pedidos bajo el candado ``factibilidad``: arma las matrices con la producción v1 (o
    reutiliza las de ``temporal`` con ``reusar_matrices``), mide cada contaminante, guarda tras cada uno y borra el
    temporal (modelos y matrices) al terminar, salvo ``conservar_temporal``."""
    fact = cfg["decision"]["factibilidad"]
    hilos_prediccion = int(fact["hilos"]) if hilos_prediccion is None else int(hilos_prediccion)
    fechas = fechas_de_medicion(cfg)
    base = Path(temporal) if temporal is not None else Path(tempfile.mkdtemp(prefix="factibilidad_v2_"))
    base.mkdir(parents=True, exist_ok=True)
    base = base.resolve()
    log.info("fechas fijadas antes de medir: %s", {k: v.isoformat() for k, v in fechas.items()})
    try:
        with candado_escritura(CANDADO, r):
            doc = leer_mediciones(r)
            t0 = time.perf_counter()
            matrices = matrices_existentes(base, contaminantes, fechas) if reusar_matrices else None
            if matrices is None:
                matrices = armar(r, cfg, list(contaminantes), fechas, base, hilos_ajuste)
            doc["fechas"] = {"valores": {k: v.isoformat() for k, v in fechas.items()},
                             "regla": (f"día {DIA_DEL_MES} del mes central de cada estación (enero, abril y julio) del año "
                                       f"del día central del régimen {REGIMEN_MEDICION}"),
                             "fijadas": "en el código, antes de medir y sin mirar ningún dato ni resultado"}
            doc["matrices"] = {**matrices, "segundos_pared": round(time.perf_counter() - t0, 1)}
            doc["versiones"] = versiones()
            for pol in contaminantes:
                log.info("%s: ajuste, compilación y medición con %d/%d hilos", pol, hilos_ajuste, hilos_prediccion)
                entrada = medir_contaminante(r, cfg, pol, fechas, matrices, base, hilos_ajuste, hilos_prediccion,
                                             repeticiones, epocas_mlp, esperar, medir_en_subproceso)
                entrada["traza"] = traza(insumos_de(r, pol), {"filas": SEMILLA_FILAS, "motores": SEMILLA_MOTORES,
                                                              "sinteticas": SEMILLA_SINTETICA}, hilos_ajuste, rutas=r,
                                         extra_codigo=modulos_v1(),
                                         parametros={"programa": "factibilidad_v2", "contaminante": pol,
                                                     "hilos_prediccion": hilos_prediccion})
                doc["contaminantes"][pol] = entrada
                guardar_mediciones(doc, r)
                for f in matrices["contaminantes"][pol]["fechas"].values():
                    (base / f["archivo"]).unlink(missing_ok=True)
    finally:
        if not conservar_temporal:
            shutil.rmtree(base, ignore_errors=True)
    return doc


# ---------------------------------------------------------------------------
# Regla (resumen)
# ---------------------------------------------------------------------------
def mediana(xs) -> float:
    xs = [float(x) for x in xs if x is not None]
    return float(np.median(xs)) if xs else float("nan")


def tiempos_de(entrada: dict, fechas=None) -> dict:
    """Por motor: la mediana de las repeticiones de cada día y la media de los días (pared de los 24 bloques)."""
    d = pd.DataFrame(entrada["filas"])
    if d.empty or "fase" not in d.columns:
        raise ValueError("no hay fases medidas")
    dia = d[d["fase"] == "dia"]
    fechas = sorted(entrada["parametros"]["fechas"]) if fechas is None else list(fechas)
    out = {}
    for motor in MOTORES:
        x = dia[dia["tarea"] == motor]
        por_fecha, reps, otros, carga, paral = {}, {}, {}, {}, {}
        for fid in fechas:
            g = x[x["fecha"] == fid].sort_values("repeticion")
            if g.empty:
                raise ValueError(f"falta la medición de {motor} en {fid}")
            por_fecha[fid] = mediana(g["segundos_pared"])
            reps[fid] = [round(float(v), 3) for v in g["segundos_pared"]]
            otros[fid] = [round(float(v), 4) for v in g["fraccion_maquina_otros"]]
            carga[fid] = [round(float(v), 2) for v in g["carga_1min_max"]]
            paral[fid] = mediana(g["paralelismo"])
        out[motor] = {"segundos_por_dia": float(np.mean(list(por_fecha.values()))), "por_fecha_s": por_fecha,
                      "repeticiones_s": reps, "fraccion_maquina_otros": otros, "carga_1min_max": carga,
                      "paralelismo_mediana": paral}
    return out


def aplicar_regla(tiempos: dict, cfg: dict) -> dict:
    """La regla del Complemento, punto 3, sobre los segundos por día de cada motor y contaminante."""
    fact = cfg["decision"]["factibilidad"]
    factor, umbral = float(fact["factor_maximo_frente_a_lightgbm"]), float(fact["umbral_dias_de_maquina"])
    dias = dias_calendario(fact["periodo"])
    pols = [str(p) for p in fact["contaminantes"]]
    faltan = [p for p in pols if p not in tiempos]
    if faltan:
        raise ValueError(f"la regla suma los dos contaminantes y faltan las mediciones de {faltan}")
    seg = {m: {p: float(tiempos[p][m]["segundos_por_dia"]) * dias for p in pols} for m in MOTORES}
    seg[PROMEDIO] = {p: sum(seg[m][p] for m in MOTORES) for p in pols}
    total = {m: sum(v.values()) for m, v in seg.items()}
    ref = total[REFERENCIA]
    produccion = {m: {"segundos_2000_2026": round(total[m], 1), "por_contaminante_s": {p: round(v, 1) for p, v in seg[m].items()},
                      "dias_de_maquina": round(total[m] / SEGUNDOS_DIA, 4),
                      "cociente_frente_a_lightgbm": round(total[m] / ref, 4) if ref > 0 else None}
                  for m in (*MOTORES, PROMEDIO)}
    candidatos = {}
    for c in cfg["decision"]["candidatos"]:
        coc, dm = total[c] / ref, total[c] / SEGUNDOS_DIA
        cumple_f, cumple_d = bool(coc <= factor), bool(dm <= umbral)
        factible = cumple_f and cumple_d
        motivo = [] if factible else ([f"cuesta {coc:.2f} veces LightGBM compilado (> {factor:g})"] if not cumple_f else []) + \
            ([f"tomaría {dm:.2f} días de máquina (> {umbral:g})"] if not cumple_d else [])
        candidatos[c] = {"factible": factible, "fuera_de_la_decision": not factible, "cumple_factor": cumple_f,
                         "cumple_dias": cumple_d, "cociente_frente_a_lightgbm": round(coc, 4),
                         "dias_de_maquina": round(dm, 4),
                         "registro": (f"{c}: {dm:.2f} días de máquina con {int(fact['hilos'])} hilos para 2000-2026 y los dos "
                                      f"contaminantes, {coc:.2f} veces LightGBM compilado: "
                                      + ("factible, sigue en la decisión" if factible else
                                         "no factible, queda fuera de la decisión (" + "; ".join(motivo) + ")"))}
    return {"dias_calendario": dias, "contaminantes": pols, "factor_maximo": factor, "umbral_dias_de_maquina": umbral,
            "produccion": produccion, "candidatos": candidatos,
            "referencia_lightgbm": {"dias_de_maquina": produccion[REFERENCIA]["dias_de_maquina"],
                                    "excede_el_umbral_de_dias": bool(ref / SEGUNDOS_DIA > umbral),
                                    "nota": "LightGBM es la referencia y el motor por omisión, no un candidato: la regla "
                                            "no lo excluye"},
            "orden_por_costo": sorted(cfg["decision"]["candidatos"], key=lambda c: total[c])}


def resumir(doc: dict, cfg: dict) -> dict:
    """``factibilidad_produccion.json`` desde ``mediciones.json``: la regla aplicada y su registro."""
    fact = cfg["decision"]["factibilidad"]
    pols = [p for p in CONTAMINANTES if p in doc.get("contaminantes", {})]
    if not pols:
        raise SystemExit("no hay mediciones de factibilidad que resumir")
    tiempos = {p: tiempos_de(doc["contaminantes"][p]) for p in pols}
    regla = aplicar_regla(tiempos, cfg)
    dias = regla["dias_calendario"]
    por_pol = {}
    for p in pols:
        e = doc["contaminantes"][p]
        t = tiempos[p]
        seg = {m: t[m]["segundos_por_dia"] for m in MOTORES}
        seg[PROMEDIO] = sum(seg.values())
        por_pol[p] = {
            "segundos_por_dia": {m: round(v, 3) for m, v in seg.items()},
            "produccion": {m: {"segundos_por_dia": round(v, 3), "segundos_2000_2026": round(v * dias, 1),
                               "dias_de_maquina": round(v * dias / SEGUNDOS_DIA, 4),
                               "nota": "este contaminante solo; la regla suma los dos (factibilidad)"}
                           for m, v in seg.items()},
            "candidatos": {c: {"fuera_de_la_decision": regla["candidatos"][c]["fuera_de_la_decision"],
                               "estado": "factible" if regla["candidatos"][c]["factible"] else "no factible",
                               "registro": regla["candidatos"][c]["registro"]} for c in cfg["decision"]["candidatos"]},
            "dias_produccion": dias,
            "detalle_por_motor": t,
            "ajuste_s": {m: _fase(e, m, "ajuste") for m in MOTORES},
            "compilacion": e.get("compilacion"),
            "equivalencia": e.get("equivalencia"),
            "espera_maquina_libre": e.get("espera_maquina_libre"),
            "maquina": {"carga_media_inicio": (e.get("maquina_inicio") or {}).get("carga_media_1_5_15"),
                        "carga_media_fin": (e.get("maquina_fin") or {}).get("carga_media_1_5_15"),
                        "procesos_mas_activos_inicio": (e.get("maquina_inicio") or {}).get("procesos_mas_activos"),
                        "memoria_total_gb": (e.get("maquina_inicio") or {}).get("memoria_total_gb"),
                        "fraccion_maquina_otros_max": max(max(v) for m in MOTORES for v in t[m]["fraccion_maquina_otros"].values()),
                        "fraccion_maquina_otros_mediana": mediana(x for m in MOTORES
                                                                  for v in t[m]["fraccion_maquina_otros"].values() for x in v),
                        "carga_1min_max": max(max(v) for m in MOTORES for v in t[m]["carga_1min_max"].values()),
                        "bibliotecas_de_hilos": e.get("bibliotecas_de_hilos")},
            "matriz": _matriz_resumen(doc.get("matrices", {}), p),
        }
    advertencias = []
    hilos_pred = int(doc["contaminantes"][pols[0]]["parametros"]["hilos_prediccion"])
    for p in pols:
        x = por_pol[p]
        otros = x["maquina"]["fraccion_maquina_otros_mediana"]
        if x["maquina"]["fraccion_maquina_otros_max"] is not None and x["maquina"]["fraccion_maquina_otros_max"] >= pl.CONTENCION_FUERTE:
            advertencias.append(f"{p}: otros procesos usaron ≥ {pl.CONTENCION_FUERTE:.0%} de la máquina en alguna repetición "
                                f"(los tiempos de pared pueden estar sobreestimados)")
        esp = x.get("espera_maquina_libre") or {}
        if esp.get("libre") is False:
            advertencias.append(f"{p}: la carga media de 1 minuto no bajó de {esp.get('umbral_carga_1min')} antes de medir "
                                f"(se esperó {esp.get('espera_s')} s; carga {esp.get('carga_1min')}); durante la medición otros "
                                f"procesos usaron una mediana de {otros:.0%} de la máquina (máximo "
                                f"{x['maquina']['fraccion_maquina_otros_max']:.0%})")
        for m in MOTORES:
            par = mediana(x["detalle_por_motor"][m]["paralelismo_mediana"].values())
            if par > hilos_pred + 0.5:
                causa = ("OpenBLAS, compilado con OpenMP, sigue el omp_get_max_threads() de cada hilo que lo llama y no el "
                         "tope de threadpoolctl, así que sus llamadas pueden abrir hilos propios dentro de los hilos de la "
                         "MLP" if m == "mlp" else "la espera activa de OpenMP u otros hilos del proceso suman CPU")
                advertencias.append(f"{p}: {m} usó un paralelismo mediano de {par:.1f} (CPU ÷ pared) con {hilos_pred} hilos: "
                                    f"{causa}; su tiempo de pared puede estar algo subestimado")
        rell = sorted({c for f in x["matriz"].get("fechas", {}).values() for c in f.get("columnas_rellenadas_con_nan_por_la_v1", [])})
        if rell:
            advertencias.append(f"{p}: la producción v1 rellenó con NaN predictores que no arma: {rell}")
    if regla["referencia_lightgbm"]["excede_el_umbral_de_dias"]:
        advertencias.append("LightGBM compilado (referencia) pasa por sí solo el umbral de días de máquina")
    p0 = doc["contaminantes"][pols[0]]["parametros"]
    return {
        "schema": SCHEMA_RESUMEN,
        "descripcion": ("Factibilidad de producción de los candidatos v2 con predictores compilados (Complemento de la "
                        "Enmienda 1, punto 3): tiempo de predecir 3 días reales de superficies de 1 km con cada motor y "
                        "12 hilos, extrapolado a 2000-2026 y a los dos contaminantes, y la regla aplicada. Sólo tiempos: "
                        "sin métricas de desempeño ni descriptivos de predicciones."),
        "creado_utc": ahora_utc(),
        "regla": {"texto": fact["regla"], "fuente": "DISENO_AMBIENTAL_V2.md, Complemento de la Enmienda 1, punto 3; "
                                                    "config_v2.json → decision.factibilidad",
                  "factor_maximo_frente_a_lightgbm": float(fact["factor_maximo_frente_a_lightgbm"]),
                  "umbral_dias_de_maquina": float(fact["umbral_dias_de_maquina"]), "hilos": int(fact["hilos"]),
                  "periodo": list(fact["periodo"]), "dias_calendario": dias, "contaminantes": list(fact["contaminantes"]),
                  "candidatos": list(cfg["decision"]["candidatos"]), "referencia": REFERENCIA,
                  "promedio_simple": fact.get("promedio_simple"), "irrevisable": bool(fact.get("irrevisable")),
                  "lectura": fact.get("lectura"),
                  "reemplaza": {"fuente": "Enmienda 1, punto 11", **(fact.get("antes_del_complemento") or {})}},
        "medicion": {
            "fechas": doc.get("fechas"),
            "matrices": {"origen": ("producción v1 en sólo lectura y en un subproceso: ContextoPrediccion.dia "
                                    "(produccion.py:359-437) con el bucle de producir_serie.py:82-95; el Modelo de la v1 "
                                    "(produccion.py:262-296) reemplazado en memoria por un capturador de la matriz que "
                                    "produccion.py:409 le entrega; superficies de ceros y matrices en un temporal borrado "
                                    "al terminar"),
                         "celdas": p0["celdas"], "horas": p0["horas"], "filas_por_dia": p0["celdas"] * p0["horas"],
                         "bloques": f"{p0['horas']} bloques horarios de {p0['celdas']} filas, como la producción v1",
                         "guardia": (doc.get("matrices") or {}).get("guardia"),
                         "entorno_v1": (doc.get("matrices") or {}).get("entorno_v1"),
                         "armado": {"subproceso": (doc.get("matrices") or {}).get("subproceso"),
                                    "reutilizadas": bool((doc.get("matrices") or {}).get("reutilizadas")),
                                    "nota": "tiempo del subproceso de la v1 que armó las 6 matrices (sólo información)"},
                         "orden_en_memoria": ("C contiguo para todos los motores; la v1 las entrega en orden F y pasarlas "
                                              "a orden C es común a todos los motores")},
            "entrenamiento": {"filas": p0["N_de_produccion"], "origen": "panel v1 completo (todas las estaciones y años)",
                              "semilla": p0["semilla_filas"], "epocas_mlp": p0["epocas_mlp"],
                              "evaluacion": "ninguna: sin conjuntos de validación, sin OOB y la MLP sin parada temprana"},
            "predictores_compilados": {
                "lightgbm": "lleaves, compile() por omisión y entrada float64 (produccion.py:226-254)",
                "xgboost": "treelite → tl2cgen (clang -O3), umbrales y salida float32",
                "random_forest": "treelite → tl2cgen (clang -O3), float64, default_left = missing_go_to_left de scikit-learn",
                "mlp": f"float32 por lotes de {LOTE_MLP} filas en hilos (BLAS a un hilo por lote)"},
            "hilos_prediccion": p0["hilos_prediccion"], "hilos_ajuste_compilacion_y_matrices": p0["hilos_ajuste"],
            "repeticiones": p0["repeticiones"],
            "estadistico": "por día, la mediana de las repeticiones (pared de los 24 bloques); por contaminante, la media de los 3 días",
            "dias_de_maquina": "segundos × días del calendario ÷ 86.400, sumando los dos contaminantes",
            "carga": ("piloto_v2.Medidor en cada fase (carga media de 1 minuto al empezar y máxima, fracción de la máquina "
                      f"usada por otros procesos) y espera previa, con tope de {ESPERA_MAXIMA_S:.0f} s, a que la carga "
                      f"media de 1 minuto baje de {CARGA_LIBRE:g}"),
            "no_incluido": ["armar la matriz de predictores desde los productos (común a todos los motores; su tiempo con "
                            "la v1 se registra aparte)", "vecindario, retransformación y escritura NetCDF (comunes)",
                            "el ajuste y la compilación (una vez por contaminante)"],
            "versiones": doc.get("versiones"),
        },
        "contaminantes": por_pol,
        "factibilidad": regla,
        "resumen": {"factibles": [c for c, v in regla["candidatos"].items() if v["factible"]],
                    "no_factibles": [c for c, v in regla["candidatos"].items() if not v["factible"]],
                    "orden_por_costo": regla["orden_por_costo"],
                    "dias_de_maquina": {m: v["dias_de_maquina"] for m, v in regla["produccion"].items()},
                    "cociente_frente_a_lightgbm": {m: v["cociente_frente_a_lightgbm"] for m, v in regla["produccion"].items()}},
        "advertencias": advertencias,
        "trazas": {p: {k: doc["contaminantes"][p]["traza"].get(k) for k in ("creado_utc", "git", "codigo", "contrato",
                                                                             "config", "insumos", "bibliotecas", "hilos",
                                                                             "semillas")}
                   for p in pols if "traza" in doc["contaminantes"][p]},
    }


def _matriz_resumen(matrices: dict, pol: str) -> dict:
    m = (matrices.get("contaminantes") or {}).get(pol)
    if not m:
        return {}
    fechas = {}
    for fid, f in m.get("fechas", {}).items():
        frac = list((f.get("fraccion_nan_por_columna") or {}).values())
        fechas[fid] = {k: f.get(k) for k in ("fecha", "forma", "calentamiento_s", "dia_s", "columnas_sin_dato", "infinitos",
                                             "columnas_rellenadas_con_nan_por_la_v1", "estaciones_con_obs_por_hora",
                                             "dias_sin_maiac", "dias_sin_no2", "meses_sin_fuente",
                                             "orden_en_memoria_de_la_v1")}
        fechas[fid]["fraccion_nan_media"] = round(float(np.mean(frac)), 4) if frac else None
    return {"celdas": m.get("celdas"), "estaciones": m.get("estaciones"), "contexto_s": m.get("contexto_s"),
            "fechas": fechas}


def _fase(entrada: dict, tarea: str, fase: str) -> float | None:
    """Segundos de pared de una fase única (el ajuste: una vez por contaminante, no entra en la regla)."""
    d = pd.DataFrame(entrada.get("filas", []))
    if d.empty:
        return None
    x = d[(d["tarea"] == tarea) & (d["fase"] == fase)]
    return None if x.empty else round(float(x["segundos_pared"].iloc[0]), 3)


def claves_prohibidas(o, camino: str = "") -> list[str]:
    """Claves de un documento que nombran una métrica de desempeño (defensa: no debe haber ninguna)."""
    out = []
    if isinstance(o, dict):
        for k, v in o.items():
            kk = str(k).lower()
            if any(kk == m or kk.startswith(m + "_") or kk.endswith("_" + m) for m in METRICAS_PROHIBIDAS):
                out.append(f"{camino}/{k}")
            out += claves_prohibidas(v, f"{camino}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            out += claves_prohibidas(v, f"{camino}[{i}]")
    return out


def procedencia_publicacion(r: RutasV2) -> dict:
    """Huella del código que arma el resumen y de las mediciones que resume (``publicar`` puede rehacerlo con otra
    versión del código que la de la medición, que queda en ``trazas``)."""
    med = ruta_mediciones(r)
    return {"creado_utc": ahora_utc(), "codigo_v2": hash_codigo_v2(r)["hash"],
            "factibilidad_v2_sha256": sha256_archivo(Path(__file__)),
            "mediciones": {**r.relativa(med), "sha256": sha256_archivo(med)} if med.exists() else None}


def publicar(r: RutasV2, cfg: dict) -> dict:
    """Escribe ``factibilidad_produccion.json`` (candado ``factibilidad``); el resumen del punto 11 se respalda."""
    with candado_escritura(CANDADO, r):
        res = pl.sin_nan(resumir(leer_mediciones(r), cfg))
        res["publicacion"] = procedencia_publicacion(r)
        malas = claves_prohibidas(res)
        if malas:
            raise RuntimeError(f"el resumen nombra métricas de desempeño: {malas}")
        respaldo = respaldar_si_es_anterior(ruta_resumen(r), r)
        if respaldo is not None:
            res["publicacion"]["respaldo_punto_11"] = r.relativa(respaldo)
        publicar_json(res, ruta_resumen(r), r)
    return res


def imprimir(res: dict) -> None:
    f = res["factibilidad"]
    print(f"\nFactibilidad (Complemento, punto 3): {f['dias_calendario']} días × {len(f['contaminantes'])} contaminantes, "
          f"{res['regla']['hilos']} hilos; factible si ≤ {f['factor_maximo']:g} × LightGBM y ≤ {f['umbral_dias_de_maquina']:g} días")
    for p, x in res["contaminantes"].items():
        print(f"  {p}: " + ", ".join(f"{m} {v:.1f} s/día" for m, v in x["segundos_por_dia"].items()))
    for m, v in f["produccion"].items():
        c = f["candidatos"].get(m)
        estado = "referencia" if m == REFERENCIA else ("FACTIBLE" if c and c["factible"] else "NO FACTIBLE")
        print(f"  {m:16s} {v['dias_de_maquina']:8.2f} días  {v['cociente_frente_a_lightgbm']:7.2f} × LightGBM  {estado}")
    for a in res["advertencias"]:
        print("AVISO:", a)


# ---------------------------------------------------------------------------
# Consola
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Factibilidad de producción con predictores compilados (sólo tiempos).")
    sub = ap.add_subparsers(dest="orden", required=True)
    m = sub.add_parser("medir", help="arma las matrices con la v1, ajusta, compila, mide y publica")
    m.add_argument("--contaminantes", nargs="+", default=list(CONTAMINANTES), choices=CONTAMINANTES)
    m.add_argument("--hilos", type=int, default=HILOS_AJUSTE, help="ajuste, compilación y matrices (tope de la etapa)")
    m.add_argument("--hilos-prediccion", type=int, default=None, help="por omisión, decision.factibilidad.hilos")
    m.add_argument("--repeticiones", type=int, default=REPETICIONES)
    m.add_argument("--temporal", default=None, help="carpeta temporal (por omisión, una nueva en TMPDIR)")
    m.add_argument("--conservar-temporal", action="store_true")
    m.add_argument("--reusar-matrices", action="store_true", help="usa las matrices ya armadas en --temporal")
    m.add_argument("--sin-esperar", action="store_true", help="no esperar a que la máquina se desocupe")
    m.add_argument("--sin-publicar", action="store_true")
    sub.add_parser("publicar", help="rehace factibilidad_produccion.json desde las mediciones")
    for nombre in ("armar-matrices", "medir-prediccion"):
        s = sub.add_parser(nombre, help="uso interno (subproceso)")
        s.add_argument("--encargo", required=True)
        s.add_argument("--hilos", type=int, default=HILOS_AJUSTE)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.orden == "armar-matrices":
        return _armar_matrices_cli(args.encargo)
    if args.orden == "medir-prediccion":
        return _medir_prediccion_cli(args.encargo)
    r = rutas_v2()
    cfg = cargar_config(r)
    if args.orden == "medir":
        tope = int(cfg["operacion"]["hilos_maximos"])
        hp = int(cfg["decision"]["factibilidad"]["hilos"]) if args.hilos_prediccion is None else args.hilos_prediccion
        if not 1 < args.hilos <= tope or not 1 < hp <= tope:
            raise SystemExit(f"--hilos y --hilos-prediccion deben estar entre 2 y {tope}")
        medir(r, cfg, args.contaminantes, args.hilos, hp, args.repeticiones, args.temporal, args.conservar_temporal,
              esperar=not args.sin_esperar, reusar_matrices=args.reusar_matrices)
        if args.sin_publicar:
            return 0
    imprimir(publicar(r, cfg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
