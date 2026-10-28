"""Pruebas de salud.py (§3, §7.2 y §7.3; S8 y S14 de §9).

Dueño: I18 (ola 5). Las que llevan «sNN» son la prueba NN de §9 del texto. Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest meteo_combinada.tests.test_salud
Datos: todas las pruebas salvo S14 usan sólo datos de ``sintetico`` (la grilla, los pesos y meses ERA5-Land en el NetCDF
real), escritos en carpetas temporales. La referencia es el código de APH ``scripts_riesgo_agudo/v3_next/meteo_civil_v3.py``
(483f63a6…) y ``scripts_riesgo_agudo/v3/exposicion_horaria_v3.py`` (2eef68b3…), leído por AST con su huella y ejecutado en
un espacio aislado (nunca importado: arrastra ``_rutas_v3``, ``dlnm_v3`` y ``_pesos``). La regresión S14 sintética corre la
``calcular_anio`` de esa v3 sobre los meses sintéticos y compara con ``salud.regresion_s14``; las pruebas que la alteran
(una variable, un conteo o una fila por carpeta; los pesos de otro año; una hora sin sp; ``config_v3.json`` con otra
carpeta) comprueban que S14 ve cada diferencia (H1, H2, H5 y H6 de la revisión). Lo crónico se prueba también releído
de un parquet escrito por ``salidas.escribir`` en una carpeta temporal (H8), y el acumulador por tramos de horas, bit a
bit frente a la serie entera (SAL-13, PED-8 de I20).
S14 (``PruebasS14.test_s14_regresion_aguda``) lee datos reales, en sólo lectura y dentro de un ``ceguera.RegistroAccesos``
en bloqueo que sólo deja pasar ``salud.insumos_s14`` (MC-31): ERA5-Land de 2024-01 a 2025-01, la grilla, los pesos, los
productos v3 de 2024 y ``config_v3.json``; exige 0 accesos fuera de ellas. Si falta un insumo se omite con su motivo y
no se da por aprobada. Sólo informa «igual» o «distinto» y la diferencia máxima; con la variable de entorno
``METEO_COMB_INFORME_S14=1`` lo escribe, con el tiempo y la memoria, en la salida de errores. Ninguna prueba abre DMC, el
reloj, la meteorología SINCA real, NASADEM real ni GHS-POP real. Los umbrales son los de M0 (``umbrales.cargar_m0``).
"""
import sys

sys.dont_write_bytecode = True

import __future__  # noqa: E402
import ast  # noqa: E402
import builtins  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import resource  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import types  # noqa: E402
import unittest  # noqa: E402
import warnings  # noqa: E402
import zoneinfo  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from datetime import date, datetime, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from typing import Iterable, Mapping  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import (ceguera, constantes, entorno, fijados, fondo_era5l, numerico, producto,  # noqa: E402
                             salidas, salud, sinca_meteo, sintetico, tipos, umbrales, validacion)

_AP = _RAIZ.parent
_APH = _AP.parent / "Air-Pollution-Health-Chile"
_EPOCA = np.datetime64("2000-01-01T00", "h")
_H_UNIX = 10957 * 24                         # horas de 1970-01-01 a 2000-01-01
_ORD70 = date(1970, 1, 1).toordinal()
SANTIAGO, COYHAIQUE, PUNTA_ARENAS = "America/Santiago", "America/Coyhaique", "America/Punta_Arenas"
TOL = constantes.valor("S14_TOLERANCIA")
ANIO = 2024                                  # MC-32
_U = None


def setUpModule():
    producto._netcdf4()          # netCDF4 con su aviso conocido de ABI silenciado, antes de que sintetico lo importe


def _umbrales():
    global _U
    if _U is None:
        texto = _APH / umbrales.TEXTO_M0
        if not texto.is_file():
            raise unittest.SkipTest(f"falta {texto.name} anclado en M0; la prueba no se da por aprobada")
        _U = umbrales.cargar_m0(_APH)
    return _U


def _h(fecha: str) -> int:
    return int((np.datetime64(fecha, "h") - _EPOCA).astype(np.int64))


def _d(fecha: str) -> int:
    return date.fromisoformat(fecha).toordinal() - _ORD70


def _fecha_local(h, zona: str) -> np.ndarray:
    """La fecha civil de cada hora, hora por hora con ``astimezone`` (la regla de ``dias_de_horas``)."""
    tz = zoneinfo.ZoneInfo(zona)
    return np.asarray([datetime.fromtimestamp((int(x) + _H_UNIX) * 3600, tz=timezone.utc).astimezone(tz).date()
                       .toordinal() - _ORD70 for x in h], dtype=np.int64)


# ---------------------------------------------------------------------------------------------
# Código de la v3 por AST (con su huella; las clases con el decorador dataclass se ejecutan con él)
# ---------------------------------------------------------------------------------------------
def _extraer(ruta: Path, sha: str, nombres, espacio: dict) -> dict:
    datos = Path(ruta).read_bytes()
    if hashlib.sha256(datos).hexdigest() != sha:
        raise AssertionError(f"{Path(ruta).name}: la huella no es la fijada")
    fuente = datos.decode("utf-8")
    lineas = fuente.splitlines()
    pedidos, elegidos = set(nombres), []
    vistos: dict[str, int] = {}
    for nodo in ast.parse(fuente).body:
        if isinstance(nodo, (ast.FunctionDef, ast.ClassDef)):
            propios = {nodo.name}
        elif isinstance(nodo, ast.Assign):
            propios = {t.id for t in nodo.targets if isinstance(t, ast.Name)}
            propios |= {e.id for t in nodo.targets if isinstance(t, ast.Tuple) for e in t.elts if isinstance(e, ast.Name)}
        elif isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name):
            propios = {nodo.target.id}
        else:
            continue
        if propios & pedidos:
            for n in propios & pedidos:
                vistos[n] = vistos.get(n, 0) + 1
            elegidos.append(nodo)
    if set(vistos) != pedidos or any(v != 1 for v in vistos.values()):
        raise AssertionError(f"nombres no hallados una sola vez: {sorted(pedidos - set(vistos))}")
    # Un módulo en memoria (sys.modules) para que dataclass resuelva sus anotaciones; nunca es el módulo de la v3.
    modulo = types.ModuleType(f"_ast_salud_{Path(ruta).stem}")
    sys.modules[modulo.__name__] = modulo
    ns = modulo.__dict__
    ns.update({"__builtins__": builtins, **espacio})
    for nodo in elegidos:
        inicio = min([nodo.lineno] + [d.lineno for d in getattr(nodo, "decorator_list", [])])
        segmento = "\n" * (inicio - 1) + "\n".join(lineas[inicio - 1:nodo.end_lineno])
        exec(compile(segmento, str(ruta), "exec", flags=__future__.annotations.compiler_flag, dont_inherit=True), ns)
    return ns


_V3 = None


def _v3() -> dict:
    """``exposicion_horaria_v3`` (EX) y ``meteo_civil_v3`` por AST, en un espacio aislado."""
    global _V3
    if _V3 is None:
        ex = _extraer(_APH / "scripts_riesgo_agudo/v3/exposicion_horaria_v3.py", fijados.SHA_EXPOSICION_V3,
                      ("EPOCA", "HORAS_PRODUCTO", "ZONA_BASE", "ZONAS_REGIONALES", "DESFASE_PRODUCTO_H", "dias_de_horas",
                       "limites_civiles", "horas_esperadas", "region_de_comuna", "zonas_por_comuna", "comunas_por_zona"),
                      {"np": np, "pd": pd, "zoneinfo": zoneinfo, "date": date, "datetime": datetime,
                       "timedelta": timedelta, "timezone": timezone, "Iterable": Iterable, "Mapping": Mapping})
        EX = SimpleNamespace(**{k: v for k, v in ex.items() if not k.startswith("__")},
                             anio_pesos=lambda a: min(max(int(a), 2000), 2025))
        nombres = ("VARIABLES", "KELVIN", "MAGNUS_A", "MAGNUS_B", "DESFASE_UTC4_H", "UNIDADES_TIEMPO", "CALENDARIOS",
                   "ATRIBUTOS_PROHIBIDOS", "BLOQUE_PIXELES", "EPOCA", "ESQUEMA_DIARIO", "PesosMeteo", "construir_pesos",
                   "HorasMeteo", "leer_mes", "leer_horas", "_iso", "humedad_relativa", "lluvia_horaria", "dias_utc4",
                   "anio_de_dia", "segmentos", "TipoDia", "tipo_dia", "_media", "_suma", "agregados_dia", "ponderar",
                   "agregar_tipos", "tabla_meteo", "a_arrow", "leer_tabla", "calcular_anio", "_fecha")
        ns = _extraer(_APH / fijados.RUTA_METEO_CIVIL_V3, fijados.SHA_METEO_CIVIL_V3, nombres,
                      {"np": np, "pd": pd, "pa": pa, "pq": pq, "netCDF4": producto._netcdf4(), "zoneinfo": zoneinfo,
                       "dataclass": dataclass, "Path": Path, "Iterable": Iterable, "Mapping": Mapping,
                       "warnings": warnings, "datetime": datetime, "timezone": timezone, "date": date,
                       "timedelta": timedelta, "EX": EX, "a_alias": lambda ruta, estricto=False: Path(ruta).name})
        ns["EX"] = EX
        _V3 = ns
    return _V3


def _v3_productos(anio: int, archivos, grilla_dir: Path, pesos_parquet: Path, *,
                  anio_pesos_v3: int | None = None) -> dict[str, pd.DataFrame]:
    """Las tablas civil, utc4 y regional de ``meteo_civil_v3.calcular_anio`` (AST) sobre insumos sintéticos;
    ``anio_pesos_v3``: hace que la v3 use los pesos de otro año (para ver que S14 lo detecta)."""
    ns = _v3()
    cel = pd.read_parquet(grilla_dir / "celdas.parquet", columns=["celda", "cod_comuna"])
    enl = pd.read_parquet(grilla_dir / "enlaces_productos.parquet", columns=["celda", "era5land_pixel"])
    tabla = pd.read_parquet(pesos_parquet)

    def pesos_meteo(a):                       # meteo_civil_v3.pesos_meteo con la tabla sintética (_pesos._tabla_anio)
        aa = ns["EX"].anio_pesos(a if anio_pesos_v3 is None else anio_pesos_v3)
        d = tabla[tabla["anio"] == aa].drop(columns="anio").set_index("celda").sort_index()
        s = d["w_ghs"].astype("float64")
        pob = pd.DataFrame({"celda": s.index.to_numpy(), "pob_dens": s.to_numpy("float64")})
        return ns["construir_pesos"](cel, enl, pob, aa)

    ns["pesos_meteo"] = pesos_meteo
    ns["replica_v1"] = lambda *a, **k: pd.DataFrame()      # la réplica float32 del panel v1 no es un producto
    r = ns["calcular_anio"](anio, list(archivos))
    return {t: r["tablas"][t] for t in salud.TIPOS_DIA}


# ---------------------------------------------------------------------------------------------
# Escenario sintético (grilla, pesos, 13 meses ERA5-Land, config_v3.json y productos v3)
# ---------------------------------------------------------------------------------------------
_COMUNAS = (11101, 12101, 13101, 13102)


_H_SP_SIN_DATO = "-07-20T15"                 # la hora del escenario con sólo sp sin dato (H5, P-SAU-2)


def _era5_sintetico(carpeta: Path, anio: int, pixeles, semilla: int, *, sp_sin_dato: bool = False) -> list[Path]:
    rng = np.random.default_rng(semilla)
    horas = np.arange(np.datetime64(f"{anio}-01-01T00", "h"), np.datetime64(f"{anio + 1}-02-01T00", "h"))
    nh, npx = horas.size, len(pixeles)
    hora = (horas - horas.astype("datetime64[D]")).astype(np.int64)
    doy = (horas.astype("datetime64[D]") - horas.astype("datetime64[Y]")).astype(np.int64)
    k = np.arange(npx)[None, :]
    t2m = (283.15 + 2.0 * k + 7.0 * np.sin(2 * np.pi * (hora[:, None] - 19) / 24)
           + 3.0 * np.sin(2 * np.pi * doy[:, None] / 365) + rng.normal(0, 0.5, (nh, npx)))
    campos = {"t2m": t2m, "d2m": t2m - rng.uniform(-1.0, 9.0, (nh, npx)),          # a veces Td > T: S14 no recorta
              "sp": 90000.0 + 1000.0 * k + rng.normal(0, 200, (nh, npx)),
              "u10": rng.normal(0, 3, (nh, npx)), "v10": rng.normal(0, 3, (nh, npx))}
    lluvia = np.where(rng.random((nh, npx)) < 0.1, rng.uniform(0, 0.002, (nh, npx)), 0.0)
    campos["tp"] = sintetico.tp_acumulado(horas, lluvia)
    i_hueco = (horas >= np.datetime64(f"{anio}-03-10T05")) & (horas <= np.datetime64(f"{anio}-03-10T08"))
    i_dia = (horas >= np.datetime64(f"{anio}-06-15T04")) & (horas < np.datetime64(f"{anio}-06-16T04"))
    for v in campos:
        campos[v][i_hueco, 0] = np.nan              # unas horas sin dato en un píxel
        campos[v][i_dia, 1] = np.nan                # un día civil entero sin dato en otro
    if sp_sin_dato:                                 # una hora con sólo sp sin dato (t2m y d2m con dato) en un píxel
        campos["sp"][horas == np.datetime64(f"{anio}{_H_SP_SIN_DATO}"), 2] = np.nan
    meses = horas.astype("datetime64[M]")
    rutas = []
    for m in np.unique(meses):
        sel = meses == m
        nombre = f"era5land_{str(m).replace('-', '')}_chile_pixeles.nc"
        rutas.append(sintetico.mes_era5_netcdf(carpeta / nombre, {v: x[sel] for v, x in campos.items()}, horas[sel],
                                               pixeles))
    return rutas


def _escenario(raiz: Path, *, anio: int = ANIO, comuna_sin_poblacion: bool = False, semilla: int = 11,
               sp_sin_dato: bool = False, anio_pesos_v3: int | None = None) -> dict:
    """Insumos sintéticos con la anidación real (``entorno.rutas_sinteticas``) y los productos v3 hechos con la v3.
    ``sp_sin_dato``: una hora con sólo sp sin dato en un píxel (H5); ``anio_pesos_v3``: la v3 con los pesos de otro
    año."""
    rutas = entorno.rutas_sinteticas(raiz)
    comunas = _COMUNAS + ((5101,) if comuna_sin_poblacion else ())
    g = sintetico.grilla(44, comunas, anios_pesos=(anio - 1, anio, anio + 1), semilla=semilla, celdas_sin_comuna=2)
    celdas = g["celdas"]
    n = len(celdas)
    archivo = sintetico.catalogo_pixeles(-33.0, -71.0, 2, 3)["pixel_id"].to_numpy(np.int64)   # 6 píxeles
    enlazados = archivo[:5]
    pix = enlazados[np.arange(n) % 5].copy()
    pix[[3, 17]] = -1                                                       # celdas sin enlace (costeras)
    enlaces = g["enlaces_productos"].copy()
    enlaces["era5land_pixel"] = pix
    enlaces["era5land_enlace"] = pd.Categorical(np.where(pix < 0, "sin_enlace", "contiene"))
    pesos = g["pesos"].copy()
    k = np.arange(len(pesos)) % n
    base = 10.0 + (37.0 * k) % 500.0
    base[k % 7 == 0] = 0.0                                                  # celdas sin población
    base[k == 9] = np.nan                                                   # un peso nulo (nan_to_num en la v3)
    base[k == 13] = -5.0                                                    # un peso negativo (recorte en 0 en la v3)
    # Los pesos cambian con el año y no por un factor común a todas las celdas, que se cancelaría al normalizar (H2):
    # con los pesos de otro año, la media comunal cambia.
    factor = 1.0 + 0.05 * (pesos["anio"].to_numpy(np.int64) - anio) * ((k % 3) - 1.0)   # k % 3: no es el píxel
    w = base * factor
    if comuna_sin_poblacion:
        w[pesos["cod_comuna"].to_numpy() == 5101] = 0.0                     # la v3 la pesa por área
    pesos["w_ghs"] = w
    celdas.to_parquet(rutas.grilla / "celdas.parquet")
    enlaces.to_parquet(rutas.grilla / "enlaces_productos.parquet")
    pesos.to_parquet(rutas.pesos / "poblacion_celda_anio.parquet")
    archivos = _era5_sintetico(rutas.era5l / "mensual", anio, archivo, semilla, sp_sin_dato=sp_sin_dato)
    cfg = {"confusores": {"meteorologia_productos": {
        t: {"carpeta": f"LOCAL/AirPollution/riesgo_agudo_v3/meteo_civil/{t}"} for t in salud.TIPOS_DIA}}}
    ruta_cfg = rutas.aph / salud.RUTA_CONFIG_V3
    ruta_cfg.parent.mkdir(parents=True, exist_ok=True)
    ruta_cfg.write_text(json.dumps(cfg), encoding="utf-8")
    tablas = _v3_productos(anio, archivos, rutas.grilla, rutas.pesos / "poblacion_celda_anio.parquet",
                           anio_pesos_v3=anio_pesos_v3)
    for t, tabla in tablas.items():
        destino = rutas.v3 / t / f"meteo_{anio}.parquet"
        destino.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(_v3()["a_arrow"](tabla), destino)
    return {"rutas": rutas, "celdas": celdas, "enlaces": enlaces, "pesos": pesos, "archivos": archivos,
            "pixeles": archivo, "tablas_v3": tablas, "anio": anio}


def _leer_meses(archivos, pixeles):
    meses = [fondo_era5l.leer_mes(r) for r in archivos]
    h = fondo_era5l.horas_de(meses)
    idx = pd.Index(meses[0].pixel_id).get_indexer(pixeles)
    tp = np.concatenate([m.datos["tp"][:, idx] for m in meses], axis=0)
    return meses, h, tp


_ESQUEMA_V3 = None


def _esquema_v3() -> dict:
    global _ESQUEMA_V3
    if _ESQUEMA_V3 is None:
        _ESQUEMA_V3 = fijados.esquema_meteo_civil_v3(_APH)
    return _ESQUEMA_V3


# ---------------------------------------------------------------------------------------------
# Celdas y campos hechos a mano (S8)
# ---------------------------------------------------------------------------------------------
def _celdas_a_mano():
    """12 celdas: 4 de 12101 (Punta Arenas), 4 de 13101, 3 de 13102 y una sin comuna; pesos hechos a mano."""
    g = sintetico.grilla(12, (12101, 13101, 13102), anios_pesos=(ANIO,), celdas_sin_comuna=1)
    celdas = g["celdas"][["celda", "cod_comuna"]].copy()
    w = np.array([1.0, 2.0, 3.0, 0.0, 5.0, 5.0, 0.0, 2.5, 1.0, 4.0, 2.0, 9.0])   # la última no tiene comuna
    tabla = pd.DataFrame({"celda": celdas["celda"].to_numpy(), "anio": np.full(12, ANIO, np.int16),
                          "cod_comuna": celdas["cod_comuna"].to_numpy(), "w_ghs": w})
    return celdas, tabla, w


def _campos_a_mano(h: np.ndarray, celdas: pd.DataFrame) -> dict:
    n = len(celdas)
    hora = h % 24
    base = 4.0 + 1.5 * np.arange(n)
    T = base[None, :] + 6.0 * np.sin(2 * np.pi * hora[:, None] / 24) + 0.01 * (h - h[0])[:, None]
    Td = T - (2.0 + 0.3 * np.arange(n))[None, :]
    return {"h": h, "celdas": celdas["celda"].to_numpy(), "T": T, "Td": Td}


def _esperado(h, campos, celdas, w, tipo, pedidos):
    """La media comunal por fuerza bruta: la fecha de cada hora con ``astimezone`` (o h − 4 h), media, mínima y máxima
    por celda con las horas con dato y media ponderada con los pesos a mano, renormalizada."""
    cod = celdas["cod_comuna"].to_numpy()
    T, Td = campos["T"], campos["Td"]
    HR = np.clip(numerico.hr_desde(T, Td), 0, 100)
    salida = {}
    for c in sorted(set(cod[(cod > 0) & (w > 0)])):
        if tipo == "utc4":
            fecha = (h - 4) // 24 + 10957
        else:
            zona = PUNTA_ARENAS if (tipo == "regional" and c // 1000 == 12) else SANTIAGO
            fecha = _fecha_local(h, zona)
        cols = np.flatnonzero((cod == c) & (w > 0))
        for d in pedidos:
            sel = fecha == d
            fila = {}
            for v, x, f in (("temp_media", T, np.nanmean), ("temp_min", T, np.nanmin), ("temp_max", T, np.nanmax),
                            ("hr_media", HR, np.nanmean), ("td_media", Td, np.nanmean)):
                num = den = 0.0
                for j in cols:
                    xs = x[sel, j]
                    if np.isfinite(xs).any():
                        num += w[j] * f(xs)
                        den += w[j]
                fila[v] = num / den if den > 0 else np.nan
            fila["n_horas"] = int(sel.sum())
            salida[(int(c), int(d))] = fila
    return salida


def _lluvia_a_mano(comunas, pedidos, tipo):
    t = pd.DataFrame({"cod_comuna": np.repeat(np.asarray(comunas, np.int32), len(pedidos)),
                      "dia": np.tile(np.asarray(pedidos, np.int32), len(comunas)),
                      "precip_mm": np.arange(len(comunas) * len(pedidos), dtype=np.float64) / 10})
    t.attrs["tipo_dia"] = tipo
    return t


# =============================================================================================
# S8
# =============================================================================================
class PruebasS8(unittest.TestCase):
    def test_s08_dias_de_23_y_25_horas(self):
        """Días civiles de 23 y 25 h."""
        d = np.arange(_d("2024-01-01"), _d("2025-01-01"))
        e = salud.horas_esperadas(d, SANTIAGO)
        self.assertEqual([int(x) for x in d[e == 25]], [_d("2024-04-06")])     # fin del horario de verano
        self.assertEqual([int(x) for x in d[e == 23]], [_d("2024-09-08")])     # comienzo
        self.assertTrue((e[(e != 23) & (e != 25)] == 24).all())
        self.assertTrue((salud.horas_esperadas(d, PUNTA_ARENAS) == 24).all())  # UTC−3 fijo desde 2016
        self.assertTrue((salud.horas_esperadas(d, None) == 24).all())          # el reloj UTC−4 no cambia
        # La duración es la cuenta de horas que caen en cada fecha (fuerza bruta, hora por hora).
        h = np.arange(_h("2023-12-30T00"), _h("2025-01-03T00"))
        for zona in (SANTIAGO, COYHAIQUE, PUNTA_ARENAS):
            fechas = _fecha_local(h, zona)
            cuenta = pd.Series(fechas).value_counts()
            np.testing.assert_array_equal(salud.horas_esperadas(d, zona), cuenta.reindex(d).to_numpy())
        # Un producto en las horas de esos días: n_horas = 25 y 23, sin faltantes, y la media sobre todas sus horas.
        celdas, tabla, w = _celdas_a_mano()
        pesos = salud.pesos_comuna(ANIO, celdas, tabla)
        for dia, horas_dia in (("2024-04-06", 25), ("2024-09-08", 23)):
            h = np.arange(_h(f"{dia}T00") - 24, _h(f"{dia}T00") + 72)
            campos = _campos_a_mano(h, celdas)
            pedidos = np.array([_d(dia)])
            for tipo in ("civil", "regional"):
                t = salud.meteo_comunal(campos, _lluvia_a_mano(pesos.comunas, pedidos, tipo), pesos, tipo,
                                        dias=pedidos)
                santiago = t[t["cod_comuna"] != 12101]
                self.assertTrue((santiago["n_horas"] == horas_dia).all(), (dia, tipo))
                self.assertTrue((santiago["n_horas_esperadas"] == horas_dia).all())
                self.assertFalse(santiago["faltan_horas"].any())
                esperado = _esperado(h, campos, celdas, w, tipo, pedidos)
                for fila in t.itertuples():
                    ref = esperado[(fila.cod_comuna, fila.dia)]
                    self.assertEqual(fila.n_horas, ref["n_horas"])
                    for v in salud.VARIABLES_CAMPO:
                        self.assertAlmostEqual(getattr(fila, v), ref[v], delta=1e-12, msg=(dia, tipo, v))
            punta = t[t["cod_comuna"] == 12101]                                   # regional: 24 h en UTC−3
            self.assertTrue((punta["n_horas_esperadas"] == 24).all() and (punta["n_horas"] == 24).all())
        # Una hora que falta en la serie: el día queda con faltan_horas.
        h = np.arange(_h("2024-04-06T00") - 24, _h("2024-04-06T00") + 72)
        h = np.delete(h, 40)
        campos = _campos_a_mano(h, celdas)
        pedidos = np.array([_d("2024-04-06")])
        t = salud.meteo_comunal(campos, _lluvia_a_mano(pesos.comunas, pedidos, "civil"), pesos, "civil", dias=pedidos)
        self.assertTrue((t["n_horas"] == 24).all() and (t["n_horas_esperadas"] == 25).all())
        self.assertTrue(t["faltan_horas"].all())

    def test_s08_media_comunal_con_pesos_conocidos(self):
        """Producto que varía por celda y pesos a mano."""
        celdas, tabla, w = _celdas_a_mano()
        pesos = salud.pesos_comuna(ANIO, celdas, tabla)
        h = np.arange(_h("2024-04-03T00"), _h("2024-04-10T00"))
        campos = _campos_a_mano(h, celdas)
        # Huecos: la celda 1 sin dato un día civil entero; la celda 4 sin dato tres horas; la 8 sin Td dos horas.
        campos["T"][(h >= _h("2024-04-05T03")) & (h < _h("2024-04-06T03")), 1] = np.nan
        campos["Td"][(h >= _h("2024-04-05T03")) & (h < _h("2024-04-06T03")), 1] = np.nan
        campos["T"][[50, 51, 52], 4] = np.nan
        campos["Td"][[60, 61], 8] = np.nan
        pedidos = np.arange(_d("2024-04-04"), _d("2024-04-09"))
        for tipo in salud.TIPOS_DIA:
            t = salud.meteo_comunal(campos, _lluvia_a_mano(pesos.comunas, pedidos, tipo), pesos, tipo, dias=pedidos)
            esperado = _esperado(h, campos, celdas, w, tipo, pedidos)
            self.assertEqual(sorted(esperado), list(zip(t["cod_comuna"], t["dia"])))
            for fila in t.itertuples():
                ref = esperado[(fila.cod_comuna, fila.dia)]
                self.assertEqual(fila.n_horas, ref["n_horas"])
                for v in salud.VARIABLES_CAMPO:
                    self.assertAlmostEqual(getattr(fila, v), ref[v], delta=1e-12, msg=(tipo, v, fila.cod_comuna))
            np.testing.assert_array_equal(t["precip_mm"].to_numpy(), _lluvia_a_mano(pesos.comunas, pedidos,
                                                                                     tipo)["precip_mm"].to_numpy())
        # Un producto constante no detectaría errores de pesos (§9, S8): éste sí. Con pesos uniformes cambia la media.
        tabla_unif = tabla.assign(w_ghs=np.where(w > 0, 1.0, 0.0))
        t_unif = salud.meteo_comunal(campos, _lluvia_a_mano(pesos.comunas, pedidos, "civil"),
                                     salud.pesos_comuna(ANIO, celdas, tabla_unif), "civil", dias=pedidos)
        t = salud.meteo_comunal(campos, _lluvia_a_mano(pesos.comunas, pedidos, "civil"), pesos, "civil", dias=pedidos)
        self.assertGreater(float(np.nanmax(np.abs(t_unif["temp_media"] - t["temp_media"]))), 0.1)

    def test_s08_esquema_identico_a_meteo_civil_v3(self):
        """fijados.esquema_meteo_civil_v3 por AST."""
        e = _esquema_v3()
        self.assertEqual(e["version"], tipos.ESQUEMA_METEO_DIARIA.version)
        self.assertEqual(tuple(e["variables"]), salud.VARIABLES)
        self.assertEqual(dict(e["columnas"]), dict(tipos.ESQUEMA_METEO_DIARIA))
        self.assertEqual(list(e["columnas"]), list(tipos.ESQUEMA_METEO_DIARIA))
        self.assertEqual(tuple(e["magnus"]), tuple(constantes.valor("MAGNUS_AGUA")[1:]))
        celdas, tabla, _ = _celdas_a_mano()
        pesos = salud.pesos_comuna(ANIO, celdas, tabla)
        h = np.arange(_h("2024-07-01T00"), _h("2024-07-04T00"))
        pedidos = np.arange(_d("2024-07-01"), _d("2024-07-03"))
        for tipo in salud.TIPOS_DIA:
            t = salud.meteo_comunal(_campos_a_mano(h, celdas), _lluvia_a_mano(pesos.comunas, pedidos, tipo), pesos,
                                    tipo, dias=pedidos)
            self.assertEqual({c: str(t[c].dtype) for c in t.columns}, dict(e["columnas"]))
            self.assertEqual(list(t.columns), list(e["columnas"]))
            self.assertEqual(t.attrs["esquema"], e["version"])
            self.assertEqual(t.attrs["tipo_dia"], tipo)


# =============================================================================================
# S14 (datos reales; MC-31)
# =============================================================================================
def _calentar() -> None:
    """Una regresión sintética fuera del registro: deja cargado todo lo que la real usa (netCDF4, pyarrow, pandas, las
    zonas del paquete tzdata), para que dentro del registro no haga falta importar nada."""
    with tempfile.TemporaryDirectory() as tmp:
        esc = _escenario(Path(tmp))
        salud.regresion_s14(esc["anio"], esc["rutas"], esquema_v3=_esquema_v3(), umbrales=_umbrales(),
                            exigir_huellas=False)


class PruebasS14(unittest.TestCase):
    informe: dict | None = None

    def test_s14_regresion_aguda(self):
        """Con corrección 0, reproduce civil, UTC−4 y regional dentro de 1e-9 en 2024 (MC-32). Lee datos reales: se omite con su motivo si falta un insumo, y entonces no se da por aprobada."""
        rutas = entorno.rutas_reales()
        insumos = salud.insumos_s14(ANIO, rutas)
        U = _umbrales()
        esquema = _esquema_v3()
        _calentar()
        vigiladas = ("/Volumes", rutas.local, rutas.aph, rutas.ap)
        faltan, r = [], None
        rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        t0 = time.perf_counter()
        with ceguera.RegistroAccesos(vigiladas, bloquear=True, permitidas=tuple(insumos.values())) as reg:
            faltan = [a for a, p in insumos.items() if not os.path.isfile(p)]
            if not faltan:
                r = salud.regresion_s14(ANIO, rutas, esquema_v3=esquema, umbrales=U)
        segundos = time.perf_counter() - t0
        rss1 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        self.assertEqual((reg.accesos, reg.por_enlace, reg.negados_dentro), ([], [], []),
                         "accesos fuera de los insumos de S14")
        if faltan:
            self.skipTest(f"faltan insumos de S14: {faltan}; S14 no se da por aprobada")
        abiertos = {Path(p).name for e, p in reg.lecturas_permitidas if e == "open"}
        self.assertEqual(abiertos, {p.name for p in insumos.values()}, "S14 no abrió todos sus insumos")
        self.assertEqual(set(r["huellas"]), set(insumos))
        PruebasS14.informe = {"resultado": r["resultado"],
                              "carpetas": {t: (c["resultado"], c["dif_max"], c["motivo"]) for t, c in r["carpetas"].items()},
                              "segundos": round(segundos, 1), "memoria_pico_gb": round(rss1 / 2 ** 30, 2),
                              "memoria_pico_previa_gb": round(rss0 / 2 ** 30, 2), "archivos": len(insumos)}
        if os.environ.get("METEO_COMB_INFORME_S14") == "1":
            print(f"\nS14 {ANIO}: {json.dumps(PruebasS14.informe, ensure_ascii=False)}", file=sys.stderr)
        for t, c in r["carpetas"].items():
            self.assertEqual(c["resultado"], "igual", f"{t}: {c['motivo']} (dif. máx. {c['dif_max']:.3g})")
            self.assertLessEqual(c["dif_max"], TOL)
        self.assertEqual(r["resultado"], "igual")


# =============================================================================================
# Lo demás
# =============================================================================================
class PruebasSalud(unittest.TestCase):
    def test_lluvia_igual_que_hoy_mc13(self):
        """precip_mm como en meteo_civil_v3."""
        with tempfile.TemporaryDirectory() as tmp:
            esc = _escenario(Path(tmp), comuna_sin_poblacion=True)      # con una comuna que la v3 pesa por área
            rutas = esc["rutas"]
            cel = pd.read_parquet(rutas.grilla / "celdas.parquet", columns=["celda", "cod_comuna"])
            enl = pd.read_parquet(rutas.grilla / "enlaces_productos.parquet", columns=["celda", "era5land_pixel"])
            tabla = pd.read_parquet(rutas.pesos / "poblacion_celda_anio.parquet")
            pl = salud.pesos_lluvia(ANIO, cel, enl, tabla)
            self.assertEqual(pl.comunas_por_area, (5101,))
            _, h, tp = _leer_meses(esc["archivos"], pl.pixeles)
            pedidos = salud.dias_del_anio(h, ANIO)
            for tipo in salud.TIPOS_DIA:
                ll = salud.lluvia_comunal(h, tp, pl.pixeles, pl, tipo)
                v3 = esc["tablas_v3"][tipo]
                np.testing.assert_array_equal(ll["cod_comuna"].to_numpy(), v3["cod_comuna"].to_numpy())
                np.testing.assert_array_equal(ll["dia"].to_numpy(), v3["dia"].to_numpy())
                a, b = ll["precip_mm"].to_numpy(), v3["precip_mm"].to_numpy()
                self.assertTrue(np.array_equal(a, b, equal_nan=True), tipo)              # bit a bit
                self.assertEqual(a.tobytes(), b.tobytes(), tipo)
                self.assertEqual(ll.attrs["tipo_dia"], tipo)
                np.testing.assert_array_equal(np.unique(ll["dia"]), pedidos)
            # Los meses en otro orden de columnas dan lo mismo (se toman por pixel_id).
            orden = np.argsort(-pl.pixeles)
            ll2 = salud.lluvia_comunal(h, tp[:, orden], pl.pixeles[orden], pl, "civil")
            self.assertEqual(ll2["precip_mm"].to_numpy().tobytes(),
                             salud.lluvia_comunal(h, tp, pl.pixeles, pl, "civil")["precip_mm"].to_numpy().tobytes())
            with self.assertRaises(salud.ErrorSalud):
                salud.lluvia_comunal(h, tp[:, 1:], pl.pixeles[1:], pl, "civil")         # falta un píxel enlazado

    def _diarios_cronicos(self):
        """Dos años de tablas civiles a mano, cada una con los pesos de su año (que cambian celda por celda)."""
        celdas, tabla, w = _celdas_a_mano()
        tabla = pd.concat([tabla.assign(anio=np.int16(2023), w_ghs=w * (1.0 + 0.1 * np.arange(w.size))), tabla],
                          ignore_index=True)
        diarios, pesos = {}, {}
        for anio in (2023, 2024):
            p = salud.pesos_comuna(anio, celdas, tabla)
            h = np.arange(_h(f"{anio}-01-01T00"), _h(f"{anio + 1}-01-02T00"))
            campos = _campos_a_mano(h, celdas)
            dia = (h - 4) // 24 + 10957
            campos["T"] = campos["T"] + 8.0 * np.cos(2 * np.pi * (dia % 365) / 365)[:, None] + (anio - 2023)
            pedidos = salud.dias_del_anio(h, anio)
            diarios[anio] = salud.meteo_comunal(campos, _lluvia_a_mano(p.comunas, pedidos, "civil"), p, "civil")
            pesos[anio] = p
        diarios[2024].loc[diarios[2024].index[5], "temp_media"] = np.nan           # un día sin dato no cuenta
        return celdas, tabla, diarios, pesos

    def test_cronico_anual(self):
        """temp_media_anual y temp_media_fria (abril a septiembre)."""
        celdas, tabla, diarios, pesos = self._diarios_cronicos()
        c = salud.cronico_anual(diarios, pesos)
        tipos.validar_esquema(c, tipos.ESQUEMA_CRONICO, nombre="crónico")
        self.assertEqual(c.attrs["esquema"], tipos.ESQUEMA_CRONICO.version)
        for fila in c.itertuples():
            t = diarios[fila.anio]
            t = t[t["cod_comuna"] == fila.cod_comuna]
            meses = np.asarray([date.fromordinal(int(x) + _ORD70).month for x in t["dia"]])
            self.assertAlmostEqual(fila.temp_media_anual, float(np.nanmean(t["temp_media"])), delta=1e-12)
            frio = (meses >= 4) & (meses <= 9)
            self.assertAlmostEqual(fila.temp_media_fria, float(np.nanmean(t["temp_media"].to_numpy()[frio])),
                                   delta=1e-12)
        self.assertEqual(list(zip(c["cod_comuna"], c["anio"])),
                         sorted((int(k), int(a)) for a in (2023, 2024) for k in pesos[a].comunas))
        # Cada año con sus pesos w_ghs (§7.3): otros pesos, otro tipo de día u otro año son un error.
        with self.assertRaises(salud.ErrorSalud):
            salud.cronico_anual(diarios, {2023: pesos[2024], 2024: pesos[2024]})
        with self.assertRaises(salud.ErrorSalud):
            salud.cronico_anual({2024: diarios[2023]}, {2024: pesos[2024]})
        otros = salud.pesos_comuna(2024, celdas, tabla.assign(w_ghs=tabla["w_ghs"] + 1.0))   # mismo año, otros pesos
        with self.assertRaises(salud.ErrorSalud):
            salud.cronico_anual(diarios, {2023: pesos[2023], 2024: otros})
        utc4 = diarios[2024].copy()
        utc4.attrs = {**diarios[2024].attrs, "tipo_dia": "utc4"}
        with self.assertRaises(salud.ErrorSalud):
            salud.cronico_anual({2024: utc4}, pesos)

    def test_cronico_desde_parquet_de_salidas(self):
        """SAL-10 (H8): una tabla diaria escrita con ``salidas.escribir(…, metadatos=salud.metadatos_tabla(t))`` y
        releída de disco (con ``attrs`` = {"esquema", "metadatos"}, lo único que guarda ``salidas``) arma lo mismo que
        la de memoria, como en una M5 reanudada. Sin esos metadatos, con otros pesos o con una clave distinta en
        ``attrs`` y en ``attrs["metadatos"]``, es un error."""
        _, _, diarios, pesos = self._diarios_cronicos()
        en_memoria = salud.cronico_anual(diarios, pesos)
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            for anio, t in diarios.items():
                meta = salud.metadatos_tabla(t)
                self.assertEqual(set(meta), set(salud.CLAVES_METADATOS))
                self.assertEqual(json.loads(json.dumps(meta)), meta)               # JSON tal cual
                salidas.escribir(f"salud/cronico/meteo_{anio}.parquet", t, clase="insumo",
                                 esquema=tipos.ESQUEMA_METEO_DIARIA, raiz=raiz, metadatos=meta)
            releidos = {a: pd.read_parquet(raiz / f"salud/cronico/meteo_{a}.parquet") for a in diarios}
        for anio, t in releidos.items():
            self.assertEqual(set(t.attrs), {"esquema", "metadatos"})
            self.assertEqual(t.attrs["metadatos"], salud.metadatos_tabla(diarios[anio]))
            self.assertEqual(t.attrs["metadatos"]["pesos_sha256"], pesos[anio].huella)
            pd.testing.assert_frame_equal(t, diarios[anio], check_like=False)
        pd.testing.assert_frame_equal(salud.cronico_anual(releidos, pesos), en_memoria)
        # Las dos formas juntas (attrs y metadatos con los mismos valores) también sirven.
        juntos = {a: t.copy() for a, t in releidos.items()}
        for a, t in juntos.items():
            t.attrs = {**releidos[a].attrs, **salud.metadatos_tabla(diarios[a])}
        pd.testing.assert_frame_equal(salud.cronico_anual(juntos, pesos), en_memoria)
        sin_meta = releidos[2024].copy()
        sin_meta.attrs = {"esquema": tipos.ESQUEMA_METEO_DIARIA.version}
        otra_huella = releidos[2024].copy()
        otra_huella.attrs = {**releidos[2024].attrs,
                             "metadatos": {**releidos[2024].attrs["metadatos"], "pesos_sha256": pesos[2023].huella}}
        en_conflicto = releidos[2024].copy()                    # attrs con lo bueno y metadatos con otra huella
        en_conflicto.attrs = {**releidos[2024].attrs, **salud.metadatos_tabla(diarios[2024]),
                              "metadatos": {**releidos[2024].attrs["metadatos"], "pesos_sha256": pesos[2023].huella}}
        mal_formados = releidos[2024].copy()
        mal_formados.attrs = {**releidos[2024].attrs, "metadatos": ["civil"]}
        for nombre, t in (("sin metadatos", sin_meta), ("otros pesos", otra_huella), ("en conflicto", en_conflicto),
                          ("metadatos que no son un diccionario", mal_formados)):
            with self.subTest(nombre), self.assertRaises(salud.ErrorSalud):
                salud.cronico_anual({**releidos, 2024: t}, pesos)

    def test_dias_contra_la_conversion_hora_a_hora(self):
        """SAL-2: la fecha civil de cada hora de 2000-2026 en las tres zonas es la de ``astimezone``; UTC−4 es h − 4 h."""
        h = np.arange(_h("1999-12-30T00"), _h("2027-01-03T00"))
        d = np.arange(_d("2000-01-01"), _d("2027-01-01"))
        for zona in (SANTIAGO, COYHAIQUE, PUNTA_ARENAS):
            fechas = _fecha_local(h, zona)
            np.testing.assert_array_equal(salud.dias(h, zona), fechas, err_msg=zona)
            e = salud.horas_esperadas(d, zona)                       # la duración es la cuenta de horas de cada fecha
            np.testing.assert_array_equal(e, pd.Series(fechas).value_counts().reindex(d).to_numpy(), err_msg=zona)
            self.assertTrue(np.isin(e, (23, 24, 25)).all())
        utc = (np.datetime64("2000-01-01T00", "h") + (h - 4).astype("timedelta64[h]")).astype("datetime64[D]")
        np.testing.assert_array_equal(salud.dias(h, None), (utc - np.datetime64("1970-01-01", "D")).astype(np.int64))
        self.assertEqual(salud.dias(h[:3], None).dtype, np.int32)
        self.assertEqual(salud.dias(h[:3], SANTIAGO).dtype, np.int32)
        with self.assertRaises(salud.ErrorSalud):
            salud.dias(np.array([1.5]), SANTIAGO)

    def test_dias_y_zonas_como_exposicion_horaria_v3(self):
        """SAL-2 a SAL-4 frente a ``exposicion_horaria_v3`` por AST: días, duraciones, zonas por comuna y el UTC−4."""
        EX = _v3()["EX"]
        h = np.arange(_h("2023-12-25T00"), _h("2025-01-05T00"))
        ts = (h + _H_UNIX) * 3600
        for zona in (SANTIAGO, COYHAIQUE, PUNTA_ARENAS):
            np.testing.assert_array_equal(salud.dias(h, zona), EX.dias_de_horas(ts, zona=zoneinfo.ZoneInfo(zona)))
            d = np.arange(_d("2024-01-01"), _d("2025-01-01"))
            esperadas = EX.horas_esperadas(d, zoneinfo.ZoneInfo(zona))
            np.testing.assert_array_equal(salud.horas_esperadas(d, zona), [esperadas[int(x)] for x in d])
        np.testing.assert_array_equal(salud.dias(h, None), EX.dias_de_horas(ts, desfase_h=-salud.DESFASE_UTC4_H))
        self.assertEqual(salud.DESFASE_UTC4_H, _v3()["DESFASE_UTC4_H"])
        self.assertEqual(salud.DESFASE_UTC4_H, EX.DESFASE_PRODUCTO_H)
        self.assertEqual(salud.DESFASE_UTC4_H, sinca_meteo.DESFASE_FIJO_H)
        self.assertEqual(dict(salud.ZONAS_REGIONALES), dict(EX.ZONAS_REGIONALES))
        self.assertEqual(salud.ZONA_BASE, EX.ZONA_BASE)
        comunas = [1101, 5101, 11101, 11201, 12101, 12401, 13101, 16101]
        self.assertEqual(salud.zonas_por_comuna(comunas), EX.zonas_por_comuna(comunas))
        self.assertEqual(salud.HORAS_UTC4, EX.HORAS_PRODUCTO)

    def test_pesos_comuna(self):
        """SAL-6: celdas con cod_comuna > 0 y w_ghs > 0; la matriz; el año de los pesos (2026 usa 2025); la huella."""
        celdas, tabla, w = _celdas_a_mano()
        tabla_nan = tabla.copy()
        tabla_nan.loc[2, "w_ghs"] = np.nan
        p = salud.pesos_comuna(ANIO, celdas, tabla_nan)
        cod = celdas["cod_comuna"].to_numpy()
        ok = (cod > 0) & (w > 0)
        ok[2] = False
        np.testing.assert_array_equal(p.celdas, np.sort(celdas["celda"].to_numpy()[ok]))
        self.assertEqual(p.comunas.dtype, np.int32)
        np.testing.assert_array_equal(p.comunas, [12101, 13101, 13102])
        denso = p.matriz.toarray()
        for j, celda in enumerate(p.celdas):
            i = list(celdas["celda"]).index(celda)
            fila = list(p.comunas).index(cod[i])
            self.assertEqual(denso[fila, j], w[i])
            self.assertEqual(denso[:, j].sum(), w[i])
        varios = pd.concat([tabla.assign(anio=np.int16(a), w_ghs=w + (a - 2000)) for a in (2023, 2024, 2025)],
                           ignore_index=True)
        self.assertEqual(salud.pesos_comuna(2026, celdas, varios).anio_pesos, 2025)
        self.assertEqual(salud.pesos_comuna(2026, celdas, varios).anio, 2026)
        self.assertEqual(salud.pesos_comuna(2024, celdas, varios).anio_pesos, 2024)
        self.assertNotEqual(salud.pesos_comuna(2024, celdas, varios).huella,
                            salud.pesos_comuna(2025, celdas, varios).huella)
        self.assertEqual(salud.pesos_comuna(2024, celdas, varios).huella, salud.pesos_comuna(2024, celdas, varios).huella)
        mala = tabla.copy()
        mala.loc[0, "cod_comuna"] = 13101                                   # otra comuna que la de la grilla
        with self.assertRaises(salud.ErrorSalud):
            salud.pesos_comuna(ANIO, celdas, mala)
        with self.assertRaises(salud.ErrorSalud):
            salud.pesos_comuna(ANIO, pd.concat([celdas, celdas.iloc[:1]]), tabla)    # celda repetida
        sin_hueco = pd.concat([tabla.assign(anio=np.int16(2020)), tabla.assign(anio=np.int16(2025))])
        with self.assertRaises(salud.ErrorSalud):
            salud.pesos_comuna(2024, celdas, sin_hueco)                     # 2024 no está y no se interpola

    def test_pesos_lluvia_como_construir_pesos(self):
        """SAL-7: los pares comuna × píxel son los de ``meteo_civil_v3.construir_pesos``, bit a bit."""
        with tempfile.TemporaryDirectory() as tmp:
            esc = _escenario(Path(tmp), comuna_sin_poblacion=True)
            rutas = esc["rutas"]
            cel = pd.read_parquet(rutas.grilla / "celdas.parquet", columns=["celda", "cod_comuna"])
            enl = pd.read_parquet(rutas.grilla / "enlaces_productos.parquet", columns=["celda", "era5land_pixel"])
            tabla = pd.read_parquet(rutas.pesos / "poblacion_celda_anio.parquet")
            for anio in (ANIO, ANIO + 2):                                   # 2026 usa 2025
                pl = salud.pesos_lluvia(anio, cel, enl, tabla)
                d = tabla[tabla["anio"] == min(anio, ANIO + 1)].drop(columns="anio").set_index("celda").sort_index()
                s = d["w_ghs"].astype("float64")
                ref = _v3()["construir_pesos"](cel, enl, pd.DataFrame({"celda": s.index.to_numpy(),
                                                                       "pob_dens": s.to_numpy("float64")}),
                                               min(anio, ANIO + 1))
                self.assertEqual(pl.anio_pesos, ref.anio_pesos)
                for campo in ("comunas", "pixeles", "fila", "col", "w", "w_norm", "cortes"):
                    a, b = getattr(pl, campo), getattr(ref, campo)
                    self.assertEqual(a.dtype, b.dtype, campo)
                    self.assertEqual(a.tobytes(), b.tobytes(), campo)
                self.assertEqual(pl.comunas_por_area, ref.comunas_por_area)

    def test_ponderar_como_v3(self):
        """SAL-7: la media comunal de la lluvia es la de ``meteo_civil_v3.ponderar``, bit a bit, con y sin píxeles sin
        dato (pesos al azar, cuyas sumas normalizadas no son 1 exacto)."""
        rng = np.random.default_rng(8)
        g = sintetico.grilla(300, 7, anios_pesos=(ANIO,), semilla=4)
        enl = g["enlaces_productos"][["celda", "era5land_pixel"]].copy()
        enl["era5land_pixel"] = rng.integers(0, 40, len(enl)) + 1_000_000
        tabla = g["pesos"].assign(w_ghs=rng.uniform(0.1, 1000.0, len(g["pesos"])))
        cel = g["celdas"][["celda", "cod_comuna"]]
        pl = salud.pesos_lluvia(ANIO, cel, enl, tabla)
        s = tabla.set_index("celda").sort_index()["w_ghs"].astype("float64")
        ref = _v3()["construir_pesos"](cel, enl, pd.DataFrame({"celda": s.index.to_numpy(), "pob_dens": s.to_numpy()}),
                                       ANIO)
        self.assertTrue((np.add.reduceat(pl.w_norm, pl.cortes) != 1.0).any())
        valores = rng.uniform(0, 30, (20, pl.pixeles.size))
        for x in (valores, np.where(rng.random(valores.shape) < 0.1, np.nan, valores)):
            self.assertEqual(salud._ponderar(x, pl).tobytes(), _v3()["ponderar"](x, ref).tobytes())

    def test_lluvia_horaria_como_v3_y_fondo(self):
        """SAL-7 (H4): ``lluvia_horaria`` es la de ``meteo_civil_v3`` (con un hueco en la serie) y la de
        ``fondo_era5l.incrementos_tp`` (FON-11), también en una hora en que el acumulado baja (como por redondeo en
        ERA5-Land): esa lluvia es 0, por el recorte en 0, y no negativa."""
        rng = np.random.default_rng(3)
        h = np.r_[np.arange(_h("2024-03-01T00"), _h("2024-03-03T00")), np.arange(_h("2024-03-03T05"),
                                                                                   _h("2024-03-05T00"))]
        tp = np.cumsum(rng.uniform(0, 0.001, (h.size, 4)), axis=0).astype(np.float32)
        k, j = 30, 2                                                     # 06 UTC: ni la 01 ni sin la hora previa
        self.assertTrue(h[k] - h[k - 1] == 1 and h[k] % 24 != 1)
        tp[k, j] = tp[k - 1, j] - np.float32(2e-6)                       # el acumulado baja
        self.assertLess(float(tp[k, j]) - float(tp[k - 1, j]), 0.0)
        ref = _v3()["lluvia_horaria"]((h + _H_UNIX) * 3600, tp)
        nuestra = salud.lluvia_horaria(h, tp)
        self.assertEqual(nuestra.tobytes(), ref.tobytes())
        self.assertEqual(float(nuestra[k, j]), 0.0)
        self.assertTrue((nuestra[np.isfinite(nuestra)] >= 0).all())
        self.assertTrue(np.isnan(nuestra[0]).all() and np.isnan(nuestra[48]).all())    # sin la hora previa
        with tempfile.TemporaryDirectory() as tmp:
            pix = sintetico.catalogo_pixeles(-33.0, -71.0, 1, 3)["pixel_id"].to_numpy()
            archivos = _era5_sintetico(Path(tmp), ANIO, pix, 5)[:2]
            meses = [fondo_era5l.leer_mes(r) for r in archivos]
            hh = fondo_era5l.horas_de(meses)
            tp0 = np.array(meses[0].datos["tp"], copy=True)
            k = int(np.flatnonzero((np.arange(tp0.shape[0]) > 0) & (hh[:tp0.shape[0]] % 24 > 1)
                                   & (tp0[np.maximum(np.arange(tp0.shape[0]) - 1, 0), 0] > 1e-5))[0])
            tp0[k, 0] = tp0[k - 1, 0] - np.float32(2e-6)                 # el acumulado baja en el primer mes
            meses[0].datos["tp"] = tp0
            tpp = np.concatenate([m.datos["tp"] for m in meses])
            nuestra = salud.lluvia_horaria(hh, tpp)
            np.testing.assert_array_equal(nuestra, fondo_era5l.incrementos_tp(meses))
            self.assertEqual(float(nuestra[k, 0]), 0.0)

    def test_filas_y_n_horas(self):
        """SAL-5: las filas son los días UTC−4 del año con alguna hora; ``n_horas`` cuenta las horas de la serie (con o
        sin dato); las horas de los días pedidos deben ser contiguas."""
        h = np.arange(_h("2023-12-31T02"), _h("2024-01-05T07"))
        np.testing.assert_array_equal(salud.dias_del_anio(h, 2024), np.arange(_d("2024-01-01"), _d("2024-01-06")))
        np.testing.assert_array_equal(salud.dias_del_anio(h, 2023), [_d("2023-12-30"), _d("2023-12-31")])
        celdas, tabla, w = _celdas_a_mano()
        pesos = salud.pesos_comuna(ANIO, celdas, tabla)
        campos = _campos_a_mano(h, celdas)
        campos["T"][:30] = np.nan                                           # sin dato, pero las horas cuentan
        pedidos = salud.dias_del_anio(h, ANIO)
        t = salud.meteo_comunal(campos, _lluvia_a_mano(pesos.comunas, pedidos, "utc4"), pesos, "utc4")
        np.testing.assert_array_equal(np.unique(t["dia"]), pedidos)
        primero = t[t["dia"] == pedidos[0]]
        self.assertTrue((primero["n_horas"] == 24).all() and not primero["faltan_horas"].any())
        ultimo = t[t["dia"] == pedidos[-1]]
        self.assertTrue((ultimo["n_horas"] == 3).all() and ultimo["faltan_horas"].all())   # 04 a 06 UTC
        self.assertEqual(t.attrs["anio"], ANIO)
        with self.assertRaises(salud.ErrorSalud):                           # la lluvia de otros días
            salud.meteo_comunal(campos, _lluvia_a_mano(pesos.comunas, pedidos[1:], "utc4"), pesos, "utc4")
        with self.assertRaises(salud.ErrorSalud):                           # la lluvia de otro tipo de día
            salud.meteo_comunal(campos, _lluvia_a_mano(pesos.comunas, pedidos, "civil"), pesos, "utc4")
        with self.assertRaises(salud.ErrorSalud):                           # horas desordenadas
            salud.meteo_comunal({**campos, "h": h[::-1]}, _lluvia_a_mano(pesos.comunas, pedidos, "utc4"), pesos, "utc4")

    def test_acumulador_por_lotes(self):
        """SAL-6: por lotes de celdas en cualquier orden da lo mismo (≤ 1e-12), y el mismo orden los mismos bits; una celda
        fuera de los pesos se ignora, una repetida o una que falta son errores."""
        celdas, tabla, w = _celdas_a_mano()
        pesos = salud.pesos_comuna(ANIO, celdas, tabla)
        h = np.arange(_h("2024-08-30T00"), _h("2024-09-12T00"))
        campos = _campos_a_mano(h, celdas)
        campos["HR"] = salud.hr_del_producto(campos["T"], campos["Td"])
        ids = campos["celdas"]
        pedidos = np.arange(_d("2024-08-31"), _d("2024-09-11"))

        def por_lotes(lotes):
            acc = salud.AcumuladorMeteo(pesos, h, salud.TIPOS_DIA, dias=pedidos)
            for lote in lotes:
                acc.agregar({c: campos[c][:, lote] for c in salud.CAMPOS}, ids[lote])
            return {t: acc.tabla(t, _lluvia_a_mano(pesos.comunas, pedidos, t)) for t in salud.TIPOS_DIA}

        uno = por_lotes([np.arange(12)])
        varios = por_lotes([np.array([7, 2]), np.array([11, 0, 5]), np.array([1, 3, 4, 6, 8, 9, 10])])
        otra_vez = por_lotes([np.array([7, 2]), np.array([11, 0, 5]), np.array([1, 3, 4, 6, 8, 9, 10])])
        for t in salud.TIPOS_DIA:
            for v in salud.VARIABLES:
                np.testing.assert_allclose(varios[t][v], uno[t][v], rtol=0, atol=1e-12)
                self.assertEqual(varios[t][v].to_numpy().tobytes(), otra_vez[t][v].to_numpy().tobytes())
            unica = salud.meteo_comunal(campos, _lluvia_a_mano(pesos.comunas, pedidos, t), pesos, t, dias=pedidos)
            pd.testing.assert_frame_equal(unica, uno[t])
        acc = salud.AcumuladorMeteo(pesos, h, ("civil",), dias=pedidos)
        acc.agregar({c: campos[c][:, :6] for c in salud.CAMPOS}, ids[:6])
        with self.assertRaises(salud.ErrorSalud):
            acc.tabla("civil", _lluvia_a_mano(pesos.comunas, pedidos, "civil"))        # faltan celdas
        with self.assertRaises(salud.ErrorSalud):
            acc.agregar({c: campos[c][:, 5:7] for c in salud.CAMPOS}, ids[5:7])        # la 5 otra vez
        with self.assertRaises(salud.ErrorSalud):
            acc.tabla("utc4", _lluvia_a_mano(pesos.comunas, pedidos, "utc4"))          # no lleva ese tipo

    def test_acumulador_por_tramos_de_horas(self):
        """SAL-13 (PED-8 de I20): un año pasado por meses, o por cortes al azar (también de una hora y justo en los
        bordes de los días civiles, UTC−4 y de Punta Arenas, en los cambios de hora), con los lotes por fuera o por
        dentro de los tramos, da bit a bit la tabla de la serie entera con los mismos lotes; lo guardado de un lote
        nunca pasa de un día. Lotes en otro orden en un tramo, huecos, repeticiones, otras celdas o un tramo que no es
        de la serie son errores, y la tabla exige todas las horas de todas las celdas."""
        celdas, tabla, _ = _celdas_a_mano()
        pesos = salud.pesos_comuna(ANIO, celdas, tabla)
        rng = np.random.default_rng(12)
        h = np.arange(_h(f"{ANIO}-01-01T00"), _h(f"{ANIO + 1}-02-01T00"))       # el año y el enero siguiente
        campos = _campos_a_mano(h, celdas)
        campos["T"] = campos["T"] + rng.normal(0, 1, campos["T"].shape)
        campos["T"][rng.random(campos["T"].shape) < 0.02] = np.nan
        campos["Td"][rng.random(campos["Td"].shape) < 0.02] = np.nan
        campos["T"][(h >= _h(f"{ANIO}-06-10T04")) & (h < _h(f"{ANIO}-06-11T04")), 3] = np.nan   # un día entero
        ids = campos["celdas"]
        pedidos = salud.dias_del_anio(h, ANIO)
        lotes = [np.array([7, 2]), np.array([11, 0, 5]), np.array([1, 3, 4, 6, 8, 9, 10])]
        mes = (_EPOCA + h.astype("timedelta64[h]")).astype("datetime64[M]")
        por_mes = np.flatnonzero(np.r_[True, mes[1:] != mes[:-1]])
        bordes = [_h(f) for f in (f"{ANIO}-04-06T03", f"{ANIO}-04-06T04", f"{ANIO}-04-07T03", f"{ANIO}-04-07T04",
                                  f"{ANIO}-09-08T03", f"{ANIO}-09-08T04", f"{ANIO}-09-09T03", f"{ANIO}-09-09T04",
                                  f"{ANIO}-12-31T03", f"{ANIO}-12-31T04", f"{ANIO + 1}-01-01T03",
                                  f"{ANIO + 1}-01-01T04")]
        de_a_una = np.arange(_h(f"{ANIO}-04-05T20"), _h(f"{ANIO}-04-07T08"))     # tramos de una hora
        al_azar = rng.choice(np.arange(1, h.size), 40, replace=False)
        cortes_raros = np.unique(np.r_[np.searchsorted(h, bordes), np.searchsorted(h, de_a_una), al_azar])

        def tramos(cortes):
            c = np.unique(np.r_[0, np.asarray(cortes, dtype=np.int64), h.size])
            return [slice(int(a), int(b)) for a, b in zip(c[:-1], c[1:])]

        def correr(cortes, *, lotes_por_fuera=False, sin_horas=False):
            acc = salud.AcumuladorMeteo(pesos, h, salud.TIPOS_DIA, dias=pedidos)
            pares = ([(l, t) for l in lotes for t in tramos(cortes)] if lotes_por_fuera
                     else [(l, t) for t in tramos(cortes) for l in lotes])
            for l, t in pares:
                horas = None if sin_horas else h[t]
                acc.agregar({c: campos[c][t][:, l] for c in ("T", "Td")}, ids[l], horas=horas)
                for lote in acc._lotes:
                    filas = 0 if lote.buffer is None else lote.buffer["T"].shape[0]
                    self.assertLess(filas, max(salud.HORAS_DIA))                # nunca más de un día guardado
            return {t: acc.tabla(t, _lluvia_a_mano(pesos.comunas, pedidos, t)) for t in salud.TIPOS_DIA}

        entera = correr([], sin_horas=True)
        for nombre, r in (("una vez, con horas", correr([])),
                          ("por meses", correr(por_mes)),
                          ("por meses, lotes por fuera", correr(por_mes, lotes_por_fuera=True)),
                          ("cortes raros", correr(cortes_raros)),
                          ("cortes raros, lotes por fuera", correr(cortes_raros, lotes_por_fuera=True))):
            for t in salud.TIPOS_DIA:
                for c in entera[t].columns:
                    self.assertEqual(r[t][c].to_numpy().tobytes(), entera[t][c].to_numpy().tobytes(), (nombre, t, c))
                self.assertEqual(r[t].attrs, entera[t].attrs)
        self.assertTrue(np.isfinite(entera["civil"]["temp_media"]).all())
        pd.testing.assert_frame_equal(entera["civil"], salud.meteo_comunal(
            campos, _lluvia_a_mano(pesos.comunas, pedidos, "civil"), pesos, "civil", dias=pedidos))

        def nuevo():
            return salud.AcumuladorMeteo(pesos, h, ("civil", "regional"), dias=pedidos)

        def parte(acc, l, t, **k):
            acc.agregar({c: campos[c][t][:, l] for c in ("T", "Td")}, ids[l], horas=h[t], **k)

        t0, t1, t2 = tramos(por_mes)[:3]
        acc = nuevo()
        parte(acc, lotes[0], t0)
        parte(acc, lotes[1], t0)
        with self.assertRaises(salud.ErrorSalud):                      # el lote 1 completaría un día antes que el 0
            parte(acc, lotes[1], t1)
        acc = nuevo()
        parte(acc, lotes[0], t0)
        malos = {"un hueco": lambda: parte(acc, lotes[0], t2),
                 "una repetición": lambda: parte(acc, lotes[0], t0),
                 "otras celdas": lambda: parte(acc, lotes[0][::-1], t1),
                 "un lote que no empieza en la primera hora": lambda: parte(acc, lotes[1], t1),
                 "la serie entera de un lote empezado": lambda: acc.agregar(
                     {c: campos[c][:, lotes[0]] for c in ("T", "Td")}, ids[lotes[0]]),
                 "horas que no son un tramo de la serie": lambda: acc.agregar(
                     {c: campos[c][[0, 2]][:, lotes[1]] for c in ("T", "Td")}, ids[lotes[1]], horas=h[[0, 2]]),
                 "horas fuera de la serie": lambda: acc.agregar(
                     {c: campos[c][-2:][:, lotes[1]] for c in ("T", "Td")}, ids[lotes[1]], horas=h[-2:] + 2),
                 "campos que no son del tramo": lambda: acc.agregar(
                     {c: campos[c][t1][:, lotes[0]] for c in ("T", "Td")}, ids[lotes[0]], horas=h[t1][:-1]),
                 "un tramo vacío": lambda: acc.agregar(
                     {c: campos[c][:0][:, lotes[0]] for c in ("T", "Td")}, ids[lotes[0]], horas=h[:0]),
                 "la tabla antes de las últimas horas": lambda: acc.tabla(
                     "civil", _lluvia_a_mano(pesos.comunas, pedidos, "civil"))}
        for nombre, f in malos.items():
            with self.subTest(nombre), self.assertRaises(salud.ErrorSalud):
                f()
        # Un lote nuevo con la serie entera completaría días que el lote 0 todavía no completa: error, sin dejar nada a
        # medias. Tras los errores, el lote 0 sigue donde iba, y los otros dos entran después con la serie entera: la
        # tabla es bit a bit la de la serie entera con los mismos lotes.
        with self.assertRaises(salud.ErrorSalud):
            acc.agregar({c: campos[c][:, lotes[1]] for c in ("T", "Td")}, ids[lotes[1]])
        for t in tramos(por_mes)[1:]:
            parte(acc, lotes[0], t)
        for l in lotes[1:]:
            acc.agregar({c: campos[c][:, l] for c in ("T", "Td")}, ids[l])
        for t in ("civil", "regional"):
            r = acc.tabla(t, _lluvia_a_mano(pesos.comunas, pedidos, t))
            for c in entera[t].columns:
                self.assertEqual(r[c].to_numpy().tobytes(), entera[t][c].to_numpy().tobytes(), (t, c))

    def test_hr_del_producto(self):
        """SAL-6: la HR es Magnus sobre agua recortada en [0, 100], la de ``meteo_civil_v3.humedad_relativa``."""
        rng = np.random.default_rng(1)
        T = rng.uniform(-30, 40, 1000)
        Td = T - rng.uniform(-3, 30, 1000)
        np.testing.assert_allclose(salud.hr_del_producto(T, Td), _v3()["humedad_relativa"](T, Td), rtol=0, atol=1e-11)
        self.assertEqual(float(salud.hr_del_producto(np.array([10.0]), np.array([12.0]))[0]), 100.0)
        self.assertTrue(np.isnan(salud.hr_del_producto(np.array([np.nan]), np.array([1.0]))).all())

    def test_representatividad(self):
        """SAL-9 (H3): r de las medias diarias < 0,8 o cociente de amplitudes de los ciclos medios por hora UTC fuera de
        [0,5; 2] excluyen; también lo que no se puede calcular; sólo vuelven los códigos. El cociente es el de las
        amplitudes (máximo menos mínimo), no el de las desviaciones (un pico estrecho los separa), y la media del día
        del píxel se toma en las horas emparejadas (§5.2), no en todas las suyas."""
        U = _umbrales()
        r_min = constantes.valor("REPRES_CORRELACION_MIN")
        c_min, c_max = constantes.valor("REPRES_COCIENTE")
        rng = np.random.default_rng(20261023)
        h = np.arange(_h("2024-05-01T00"), _h("2024-08-01T00"))      # Santiago en UTC−4: el día civil empieza a las 04
        hora = h % 24
        ndias = h.size // 24
        anom = np.repeat(rng.normal(0, 3, ndias), 24)
        ciclo = np.sin(2 * np.pi * (hora - 19) / 24)
        t2m = 283.0 + 6 * ciclo + anom                                  # K, en el píxel del reloj
        pico = np.exp(-((hora - 15) / 1.0) ** 2)                        # un ciclo de otra forma: un pico estrecho
        obs = {"A": t2m - 273.15 + rng.normal(0, 0.3, h.size),          # representativa
               "B": 10 + 6 * ciclo + np.repeat(rng.normal(0, 3, ndias), 24),    # medias diarias sin relación
               "C": 10 + 18 * ciclo + anom,                             # amplitud ×3
               "D": 10 + 2.4 * ciclo + anom,                            # amplitud ×0,4
               "E": np.where(hora % 4 == 0, t2m - 273.15, np.nan),     # 6 horas por día: ningún día válido
               "G": np.where(hora == 12, t2m - 273.15, np.nan),        # una sola hora UTC
               "H": 10 + 10.8 * ciclo + anom,                           # amplitud ×1,8: queda
               "I": 10 + 13.2 * ciclo + anom,                           # amplitud ×2,2: fuera
               "J": np.where(hora < 12, t2m - 273.15, np.nan),          # 12 horas seguidas: hueco de 12 h, sin días
               "K": 10 + 30 * pico + anom,                              # pico: amplitudes ×2,5 y desviaciones ×1,5
               "L": 10 + 9 * pico + anom}                               # pico: amplitudes ×0,75 y desviaciones ×0,46
        valido = rng.random(h.size) > 0.3
        diarios = {c: {"h": h, "T": x} for c, x in obs.items()}
        diarios["F"] = {"h": h, "T": t2m - 273.15 + 1.0, "valido": valido}   # sesgo fijo y horas no válidas: queda
        pixel = {c: {"h": h, "t2m": t2m} for c in diarios}
        # K y L: el cociente de amplitudes y el de desviaciones caen a lados distintos de la cota.
        ciclo_px = 6 * np.sin(2 * np.pi * (np.arange(24) - 19) / 24)
        for codigo, alto in (("K", 30.0), ("L", 9.0)):
            c = alto * np.exp(-((np.arange(24) - 15) / 1.0) ** 2)
            amp, desv = np.ptp(c) / np.ptp(ciclo_px), c.std() / ciclo_px.std()
            if codigo == "K":
                self.assertTrue(amp > c_max and c_min <= desv <= c_max, (amp, desv))
            else:
                self.assertTrue(c_min <= amp <= c_max and desv < c_min, (amp, desv))
        # M: horas válidas sólo de día (alrededor del máximo del ciclo, y cada 4 h el resto) en la mitad de los días.
        dia_civil = salud.dias(h, SANTIAGO).astype(np.int64)
        dias_m, cual = np.unique(dia_civil, return_inverse=True)
        posicion = (h - 4) % 24
        de_dia = np.isin(posicion, (0, 4, 8, 12, 16, 18, 19, 20, 21, 22, 23))   # 11 h y hueco máximo de 4 h
        parcial = rng.random(dias_m.size) < 0.5
        valido_m = ~parcial[cual] | de_dia
        t2m_m = 283.0 + 6 * ciclo + rng.normal(0, 0.8, dias_m.size)[cual]
        diarios["M"] = {"h": h, "T": np.where(valido_m, t2m_m - 273.15, np.nan)}
        pixel["M"] = {"h": h, "t2m": t2m_m}
        d_m, ok_m = salud._dias_validos(h[valido_m], SANTIAGO, int(U.a("DIA_MIN_H")), int(U.a("DIA_HUECO_H")))
        validos = np.unique(d_m[ok_m])
        obs_dia = pd.Series(t2m_m[valido_m][ok_m]).groupby(d_m[ok_m]).mean()
        todas = pd.Series(t2m_m).groupby(dia_civil).mean().reindex(validos)
        self.assertLess(np.corrcoef(obs_dia.to_numpy(), todas.to_numpy())[0, 1], r_min)   # con todas las horas: fuera
        self.assertTrue(parcial[np.isin(dias_m, validos)].any() and (~parcial[np.isin(dias_m, validos)]).any())
        excluidas = salud.representatividad(diarios, pixel, U)
        self.assertIsInstance(excluidas, frozenset)
        self.assertEqual(excluidas, frozenset({"B", "C", "D", "E", "G", "I", "J", "K"}))
        self.assertTrue(all(isinstance(c, str) for c in excluidas))
        en_celsius = {c: (v["h"], v["t2m"] - 273.15) for c, v in pixel.items()}
        self.assertEqual(salud.representatividad(diarios, en_celsius, U), excluidas)   # no depende de la unidad
        corrida = {c: {"h": v["h"][100:], "t2m": v["t2m"][100:]} for c, v in pixel.items()}   # sólo las horas comunes
        self.assertEqual(salud.representatividad(diarios, corrida, U), excluidas)
        with self.assertRaises(salud.ErrorSalud):
            salud.representatividad(diarios, {c: v for c, v in pixel.items() if c != "A"}, U)

    def test_representatividad_en_el_dia_civil(self):
        """SAL-9 (H3): con anomalías alineadas al día civil de verano (UTC−3), que se cancelan dentro del día civil pero
        no dentro del día UTC−4, la estación es representativa en el día civil, el de omisión, y no en el UTC−4: un día
        UTC−4 por omisión no pasaría."""
        U = _umbrales()
        rng = np.random.default_rng(3)
        h = np.arange(_h("2024-01-02T03"), _h("2024-03-30T03"))       # días civiles enteros, 2 de enero a 29 de marzo
        dia = salud.dias(h, SANTIAGO).astype(np.int64)
        dias_n, cual = np.unique(dia, return_inverse=True)
        self.assertTrue((np.bincount(cual) == 24).all() and dias_n.size % 2 == 0)
        posicion = np.arange(h.size) % 24
        signo = rng.permutation(np.r_[np.ones(dias_n.size // 2), -np.ones(dias_n.size // 2)])
        hora = h % 24
        t2m = 283.0 + 6 * np.sin(2 * np.pi * (hora - 19) / 24) + rng.normal(0, 0.5, dias_n.size)[cual]
        e = np.zeros(h.size)
        e[posicion == 0] = 20 * signo                                  # la primera hora del día civil (03 UTC)
        e[posicion == 23] = -20 * signo                                # y la última (02 UTC): se cancelan en el día
        diarios = {"N": {"h": h, "T": t2m - 273.15 + e}}
        pixel = {"N": {"h": h, "t2m": t2m}}
        self.assertEqual(salud.representatividad(diarios, pixel, U), frozenset())
        self.assertEqual(salud.representatividad(diarios, pixel, U, zona=SANTIAGO), frozenset())
        self.assertEqual(salud.representatividad(diarios, pixel, U, zona=None), frozenset({"N"}))

    def test_dias_validos_como_validacion(self):
        """SAL-9 (H3): los días válidos de la representatividad son los de ``validacion.dias_validos`` (VAL-3; §5.2:
        ≥ DIA_MIN_H horas y hueco circular ≤ DIA_HUECO_H), en series al azar con días de 23 y 25 h en las tres zonas, y
        en los bordes: 8 h, 7 h, hueco de 4 y de 5 (dentro del día y al dar la vuelta), y la vuelta de un día de 25 o
        23 h."""
        U = _umbrales()
        min_h, hueco = int(U.a("DIA_MIN_H")), int(U.a("DIA_HUECO_H"))
        d2000 = _d("2000-01-01")                                          # validacion cuenta los días desde 2000

        def comparar(hv, zona) -> dict:
            d, ok = salud._dias_validos(hv, zona, min_h, hueco)
            ref = validacion.dias_validos(hv, np.ones(hv.size, dtype=bool), zona, U)
            unicos, primero = np.unique(d, return_index=True)
            np.testing.assert_array_equal(unicos, ref["dia"].to_numpy(np.int64) + d2000, err_msg=zona)
            np.testing.assert_array_equal(ok[primero], ref["valido"].to_numpy(), err_msg=zona)
            for x, v in zip(unicos, ok[primero]):                       # el mismo valor en todas las horas del día
                self.assertTrue((ok[d == x] == v).all())
            return dict(zip(unicos.tolist(), ok[primero].tolist()))

        rng = np.random.default_rng(17)
        h = np.r_[np.arange(_h("2024-03-28T00"), _h("2024-04-14T00")), np.arange(_h("2024-08-30T00"),
                                                                                   _h("2024-09-15T00"))]
        vistos = []
        for zona in (SANTIAGO, COYHAIQUE, PUNTA_ARENAS):
            for p in (0.3, 0.4, 0.5, 0.6, 0.75, 0.9):
                vistos.extend(comparar(h[rng.random(h.size) < p], zona).values())
        self.assertTrue(any(vistos) and not all(vistos))

        def inicio(fecha: str) -> int:
            f = date.fromisoformat(fecha)
            local = datetime(f.year, f.month, f.day, tzinfo=zoneinfo.ZoneInfo(SANTIAGO))
            return int(local.timestamp()) // 3600 - _H_UNIX

        casos = [("2024-07-10", (0, 1, 2, 4, 8, 12, 16, 20), True),          # 8 h y hueco 4
                 ("2024-07-10", (0, 4, 8, 12, 15, 18, 21), False),            # 7 h y hueco 4
                 ("2024-07-10", (0, 1, 2, 3, 4, 9, 13, 17, 21), False),       # hueco 5 dentro del día
                 ("2024-07-10", (2, 5, 8, 11, 14, 17, 20, 22), True),         # hueco 4 al dar la vuelta
                 ("2024-07-10", (3, 5, 8, 11, 14, 17, 20, 22), False),        # hueco 5 al dar la vuelta
                 ("2024-04-06", (0, 4, 8, 12, 16, 19, 20, 21), True),         # 25 h: la vuelta es 25 − 21 = 4
                 ("2024-04-06", (0, 4, 8, 12, 16, 18, 19, 20), False),        # 25 h: 5 (con 24 serían 4)
                 ("2024-09-08", (0, 4, 8, 12, 16, 17, 18, 19), True),         # 23 h: 4 (con 24 serían 5)
                 ("2024-09-08", (0, 4, 8, 12, 15, 16, 17, 18), False)]        # 23 h: 5
        for fecha, posiciones, esperado in casos:
            with self.subTest(fecha=fecha, posiciones=posiciones):
                r = comparar(inicio(fecha) + np.asarray(posiciones, dtype=np.int64), SANTIAGO)
                self.assertEqual(list(r.values()), [esperado])
                self.assertEqual(list(r), [_d(fecha)])

    def test_regla_de_representatividad_en_los_bordes(self):
        """SAL-9: r = 0,8 queda; el cociente 0,5 o 2 queda; fuera o sin valor, se excluye."""
        f = salud._fuera
        self.assertFalse(f(0.8, 1.0))
        self.assertTrue(f(0.7999999, 1.0))
        self.assertFalse(f(0.9, 0.5))
        self.assertFalse(f(0.9, 2.0))
        self.assertTrue(f(0.9, 0.4999999))
        self.assertTrue(f(0.9, 2.0000001))
        self.assertTrue(f(float("nan"), 1.0))
        self.assertTrue(f(0.9, float("inf")))

    def test_regresion_s14_sintetica(self):
        """SAL-11: con los meses, la grilla y los pesos sintéticos, el lector por celda reproduce las tres carpetas que
        hace la ``calcular_anio`` de la v3 (AST) dentro de 1e-9, bajo un registro que sólo deja leer ``insumos_s14``."""
        U = _umbrales()
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            esc = _escenario(raiz)
            insumos = salud.insumos_s14(ANIO, esc["rutas"])
            for lote in (7, salud.LOTE_CELDAS_S14):
                with ceguera.RegistroAccesos((raiz,), bloquear=True, permitidas=tuple(insumos.values())) as reg:
                    r = salud.regresion_s14(ANIO, esc["rutas"], esquema_v3=_esquema_v3(), umbrales=U,
                                            exigir_huellas=False, lote_celdas=lote)
                self.assertEqual((reg.accesos, reg.por_enlace, reg.negados_dentro), ([], [], []))
                self.assertEqual({Path(p).name for e, p in reg.lecturas_permitidas if e == "open"},
                                 {p.name for p in insumos.values()})
                self.assertEqual(r["resultado"], "igual", r["carpetas"])
                for t, c in r["carpetas"].items():
                    self.assertEqual(c["resultado"], "igual", (t, c))
                    self.assertLessEqual(c["dif_max"], TOL)
                    self.assertIsNone(c["motivo"])
                self.assertEqual(set(r["huellas"]), set(insumos))
                self.assertEqual(r["huellas"][f"V3/civil/meteo_{ANIO}.parquet"],
                                 hashlib.sha256(insumos[f"V3/civil/meteo_{ANIO}.parquet"].read_bytes()).hexdigest())
            self.assertEqual(set(r), {"anio", "resultado", "tolerancia", "carpetas", "huellas"})
            # La v3 no recorta Td ≤ T; el escenario trae horas con Td > T, así que con el recorte daría «distinto».
            mes = fondo_era5l.leer_mes(esc["archivos"][0])
            self.assertTrue((mes.datos["d2m"] > mes.datos["t2m"]).any())
            # Las huellas fijadas no son las sintéticas: con exigir_huellas, S14 se niega.
            with self.assertRaises(salud.ErrorSalud):
                salud.regresion_s14(ANIO, esc["rutas"], esquema_v3=_esquema_v3(), umbrales=U)

    def test_regresion_s14_sintetica_ve_las_diferencias(self):
        """SAL-11 (H1): cada una de las seis variables corrida 1e-7 en una fila (repartidas entre las tres carpetas, en
        dos rondas), un ``n_horas``, un ``n_horas_esperadas`` o un ``faltan_horas`` distintos (cada uno en su carpeta) y
        una fila de menos dan «distinto» en su carpeta, con el motivo y sin números, y la diferencia máxima ≈ 1e-7
        cuando es un valor; una carpeta «igual» junto a dos «distinto» deja el resultado en «distinto». Una comparación
        que mirara sólo algunas variables o columnas, o un «igual» global con «alguna», no pasaría."""
        U = _umbrales()
        corrimiento = 1e-7
        with tempfile.TemporaryDirectory() as tmp:
            esc = _escenario(Path(tmp) / "a")
            rutas = esc["rutas"]
            archivos = {t: rutas.v3 / t / f"meteo_{ANIO}.parquet" for t in salud.TIPOS_DIA}
            originales = {t: a.read_bytes() for t, a in archivos.items()}
            fila = {}                                   # una fila con las seis variables con dato, en cada carpeta
            for t, tabla in esc["tablas_v3"].items():
                con_dato = np.flatnonzero(np.isfinite(tabla[list(salud.VARIABLES)].to_numpy()).all(axis=1))
                fila[t] = int(con_dato[con_dato.size // 3])

            def corrido(v):
                def cambio(tabla, t):
                    tabla.loc[fila[t], v] = tabla.loc[fila[t], v] + corrimiento
                    return tabla
                return cambio

            def conteo(c, nuevo):
                def cambio(tabla, t):
                    tabla.loc[fila[t] + 1, c] = nuevo(tabla.loc[fila[t] + 1, c])
                    return tabla
                return cambio

            def correr(cambios):
                for t, a in archivos.items():
                    a.write_bytes(originales[t])
                for t, cambio in cambios.items():
                    esquema = pq.read_schema(archivos[t])
                    tabla = cambio(pq.read_table(archivos[t]).to_pandas(), t)
                    pq.write_table(pa.Table.from_pandas(tabla, preserve_index=False, schema=esquema), archivos[t])
                r = salud.regresion_s14(ANIO, rutas, esquema_v3=_esquema_v3(), umbrales=U, exigir_huellas=False)
                for c in r["carpetas"].values():
                    self.assertFalse(any(ch.isdigit() for ch in (c["motivo"] or "")), c["motivo"])
                    self.assertIn(c["resultado"], ("igual", "distinto"))
                self.assertEqual(r["resultado"], "distinto" if any(c["resultado"] == "distinto"
                                                                   for c in r["carpetas"].values()) else "igual")
                return r

            self.assertEqual(correr({})["resultado"], "igual")
            # Las seis variables, una por carpeta en cada ronda.
            for ronda in (("temp_media", "temp_min", "temp_max"), ("hr_media", "td_media", "precip_mm")):
                r = correr({t: corrido(v) for t, v in zip(salud.TIPOS_DIA, ronda)})
                self.assertEqual(r["resultado"], "distinto")
                for t, v in zip(salud.TIPOS_DIA, ronda):
                    c = r["carpetas"][t]
                    self.assertEqual((c["resultado"], c["motivo"]), ("distinto", "valores fuera de la tolerancia"),
                                     (t, v))
                    self.assertAlmostEqual(c["dif_max"], corrimiento, delta=1e-9, msg=(t, v))
            # Los conteos, cada uno en su carpeta y con la civil intacta: una «igual» y dos «distinto».
            r = correr({"utc4": conteo("n_horas_esperadas", lambda x: x - 1),
                        "regional": conteo("faltan_horas", lambda x: not x)})
            self.assertEqual(r["resultado"], "distinto")
            self.assertEqual((r["carpetas"]["civil"]["resultado"], r["carpetas"]["civil"]["motivo"]), ("igual", None))
            self.assertLessEqual(r["carpetas"]["civil"]["dif_max"], TOL)
            for t in ("utc4", "regional"):
                c = r["carpetas"][t]
                self.assertEqual((c["resultado"], c["motivo"]), ("distinto", "conteos de horas distintos"), t)
                self.assertLessEqual(c["dif_max"], TOL)
            # n_horas y una fila de menos, con la regional intacta.
            r = correr({"civil": conteo("n_horas", lambda x: x - 1), "utc4": lambda tabla, t: tabla.iloc[1:]})
            self.assertEqual(r["resultado"], "distinto")
            self.assertEqual(r["carpetas"]["regional"]["resultado"], "igual")
            self.assertEqual((r["carpetas"]["civil"]["resultado"], r["carpetas"]["civil"]["motivo"]),
                             ("distinto", "conteos de horas distintos"))
            self.assertEqual(r["carpetas"]["utc4"]["resultado"], "distinto")
            self.assertIn("filas distintas", r["carpetas"]["utc4"]["motivo"])
            # Una comuna sin población en sus celdas enlazadas: la v3 la pesa por área y salud no (w_ghs > 0, SAL-6).
            esc2 = _escenario(Path(tmp) / "b", comuna_sin_poblacion=True)
            r2 = salud.regresion_s14(ANIO, esc2["rutas"], esquema_v3=_esquema_v3(), umbrales=U, exigir_huellas=False)
            self.assertEqual(r2["resultado"], "distinto")
            self.assertTrue(all("NaN en otras posiciones" in c["motivo"] for c in r2["carpetas"].values()))

    def test_regresion_s14_sintetica_ve_los_pesos_de_otro_anio(self):
        """SAL-6, SAL-7 (H2): los pesos sintéticos cambian de un año a otro celda por celda (no por un factor común, que
        se cancelaría al normalizar), así que una v3 hecha con los pesos del año siguiente da «distinto» en las tres
        carpetas: S14 no pasaría con los pesos de otro año."""
        U = _umbrales()
        with tempfile.TemporaryDirectory() as tmp:
            esc = _escenario(Path(tmp), anio_pesos_v3=ANIO + 1)
            r = salud.regresion_s14(ANIO, esc["rutas"], esquema_v3=_esquema_v3(), umbrales=U, exigir_huellas=False)
            self.assertEqual(r["resultado"], "distinto")
            for t, c in r["carpetas"].items():
                self.assertEqual((c["resultado"], c["motivo"]), ("distinto", "valores fuera de la tolerancia"), t)
                self.assertGreater(c["dif_max"], 1e-6, t)
            # Y la causa son los pesos: los normalizados por comuna de los dos años difieren, en T y en la lluvia.
            tabla = esc["pesos"]
            cel = esc["celdas"][["celda", "cod_comuna"]]
            enl = esc["enlaces"][["celda", "era5land_pixel"]]
            for a in (ANIO, ANIO + 1):
                self.assertEqual(salud.pesos_comuna(a, cel, tabla).anio_pesos, a)
            p0, p1 = (salud.pesos_comuna(a, cel, tabla) for a in (ANIO, ANIO + 1))
            n0, n1 = (np.asarray(p.matriz.multiply(1 / p.matriz.sum(axis=1)).todense()) for p in (p0, p1))
            self.assertGreater(float(np.abs(n0 - n1).max()), 1e-3)
            l0, l1 = (salud.pesos_lluvia(a, cel, enl, tabla) for a in (ANIO, ANIO + 1))
            self.assertGreater(float(np.abs(l0.w_norm - l1.w_norm).max()), 1e-3)

    def test_regresion_s14_sintetica_sp_sin_dato(self):
        """SAL-11, P-SAU-2, PED-3 (H5): en una hora en que el píxel trae t2m y d2m pero no sp, ``campos_fondo`` con
        Δz = 0 deja Td_F (y la HR) sin dato, porque su identidad exige p finita, y la v3, que no usa sp, no; T_F sigue
        siendo t2m − 273,15 y, en las demás horas, Td_F es d2m − 273,15. S14 no lo arregla: lo informa «distinto» en
        las tres carpetas, con el motivo de Td y sin números."""
        U = _umbrales()
        kelvin = _v3()["KELVIN"]
        with tempfile.TemporaryDirectory() as tmp:
            esc = _escenario(Path(tmp), sp_sin_dato=True)
            pid = esc["pixeles"][2]
            julio = next(a for a in esc["archivos"] if f"{ANIO}07" in Path(a).name)
            mes, _ = salud._reducir_mes(fondo_era5l, fondo_era5l.leer_mes(julio), np.array([pid]))
            op = salud._operador_enlazado(fondo_era5l, np.array([1]), np.array([pid]))
            F = fondo_era5l.campos_fondo(mes, op, U, recortar_td=False)
            i = int(np.flatnonzero(np.asarray(mes.tiempos, np.int64) == _h(f"{ANIO}{_H_SP_SIN_DATO}"))[0])
            t2m, d2m, sp = (np.asarray(mes.datos[v][:, 0], np.float64) for v in ("t2m", "d2m", "sp"))
            self.assertTrue(np.isnan(sp[i]) and np.isfinite(t2m[i]) and np.isfinite(d2m[i]))
            self.assertTrue(np.isnan(F["Td_F"][i, 0]))                              # la v3 tendría d2m − 273,15
            self.assertEqual(F["T_F"][i, 0], t2m[i] - kelvin)
            otras = np.isfinite(sp) & np.isfinite(t2m) & np.isfinite(d2m)
            otras[i] = False
            np.testing.assert_array_equal(F["Td_F"][otras, 0], d2m[otras] - kelvin)  # la identidad de Δz = 0
            r = salud.regresion_s14(ANIO, esc["rutas"], esquema_v3=_esquema_v3(), umbrales=U, exigir_huellas=False)
            self.assertEqual(r["resultado"], "distinto")
            for t, c in r["carpetas"].items():
                self.assertEqual(c["resultado"], "distinto", t)
                self.assertEqual(c["motivo"], f"valores fuera de la tolerancia; {salud.MOTIVO_TD_SIN_DATO}", t)
                self.assertFalse(any(ch.isdigit() for ch in c["motivo"]))
            # Sin esa hora (el escenario de siempre), el motivo de Td no aparece aunque una carpeta difiera.
        with tempfile.TemporaryDirectory() as tmp:
            esc = _escenario(Path(tmp))
            civil = esc["rutas"].v3 / "civil" / f"meteo_{ANIO}.parquet"
            t = pq.read_table(civil).to_pandas()
            t.loc[10, "temp_media"] += 1e-7
            pq.write_table(pa.Table.from_pandas(t, preserve_index=False, schema=pq.read_schema(civil)), civil)
            r = salud.regresion_s14(ANIO, esc["rutas"], esquema_v3=_esquema_v3(), umbrales=U, exigir_huellas=False)
            self.assertEqual(r["carpetas"]["civil"]["motivo"], "valores fuera de la tolerancia")

    def test_regresion_s14_carpetas_de_config_v3(self):
        """SAL-11 (H6): cada carpeta de ``confusores.meteorologia_productos`` de ``config_v3.json`` debe ser V3/<tipo>.
        Otra carpeta, dos tipos cambiados entre sí, una subcarpeta distinta, una carpeta fuera de LOCAL/AirPollution/,
        un tipo que falta o el nodo que falta detienen S14 (``ErrorSalud``) apenas leído el config, sin abrir nada
        más (bajo un registro que sólo deja leer el config)."""
        U = _umbrales()
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            esc = _escenario(raiz)
            ruta_cfg = esc["rutas"].aph / salud.RUTA_CONFIG_V3
            original = ruta_cfg.read_bytes()
            prods = json.loads(original)["confusores"]["meteorologia_productos"]
            base = prods["civil"]["carpeta"].rsplit("/", 1)[0]

            def con(productos):
                return {"confusores": {"meteorologia_productos": productos}}

            casos = {
                "otra carpeta": con({**prods, "civil": {"carpeta": f"{base}_otra/civil"}}),
                "civil y utc4 cambiados": con({**prods, "civil": prods["utc4"], "utc4": prods["civil"]}),
                "otra subcarpeta": con({**prods, "regional": {"carpeta": f"{base}/regional_v2"}}),
                "fuera de LOCAL/AirPollution": con({**prods, "utc4": {"carpeta": prods["utc4"]["carpeta"].replace(
                    salud.PREFIJO_LOCAL_V3, "LOCAL/otra/")}}),
                "falta un tipo": con({k: v for k, v in prods.items() if k != "regional"}),
                "falta el nodo": {"confusores": {}},
            }
            for nombre, cfg in casos.items():
                ruta_cfg.write_text(json.dumps(cfg), encoding="utf-8")
                with self.subTest(nombre):
                    with ceguera.RegistroAccesos((raiz,), bloquear=True, permitidas=(ruta_cfg,)):
                        with self.assertRaises(salud.ErrorSalud):
                            salud.regresion_s14(ANIO, esc["rutas"], esquema_v3=_esquema_v3(), umbrales=U,
                                                exigir_huellas=False)
            ruta_cfg.write_bytes(original)
            r = salud.regresion_s14(ANIO, esc["rutas"], esquema_v3=_esquema_v3(), umbrales=U, exigir_huellas=False)
            self.assertEqual(r["resultado"], "igual")

    def test_regresion_s14_falta_un_insumo(self):
        """SAL-11: sin un mes ERA5-Land, S14 no corre (FileNotFoundError); la prueba real se omite en ese caso."""
        with tempfile.TemporaryDirectory() as tmp:
            esc = _escenario(Path(tmp))
            Path(esc["archivos"][-1]).unlink()
            with self.assertRaises(FileNotFoundError):
                salud.regresion_s14(ANIO, esc["rutas"], esquema_v3=_esquema_v3(), umbrales=_umbrales(),
                                    exigir_huellas=False)
            otro = dict(_esquema_v3())
            otro["columnas"] = {**otro["columnas"], "dia": "int64"}
            with self.assertRaises(salud.ErrorSalud):
                salud.regresion_s14(ANIO, esc["rutas"], esquema_v3=otro, umbrales=_umbrales(), exigir_huellas=False)

    def test_insumos_s14_por_alias(self):
        """SAL-11: los insumos de S14 son exactamente los de MC-31, por alias y sin consultar el disco."""
        rutas = entorno.rutas_reales()
        ins = salud.insumos_s14(ANIO, rutas)
        self.assertEqual(len(ins), 1 + 3 + 13 + 3)
        meses = sorted(a for a in ins if a.startswith("ERA5L/"))
        self.assertEqual(meses[0], "ERA5L/mensual/era5land_202401_chile_pixeles.nc")
        self.assertEqual(meses[-1], "ERA5L/mensual/era5land_202501_chile_pixeles.nc")
        for alias, ruta in ins.items():
            self.assertEqual(entorno.alias(ruta, rutas), alias)
        self.assertEqual(sorted(a for a in ins if a.startswith("V3/")),
                         [f"V3/{t}/meteo_{ANIO}.parquet" for t in sorted(salud.TIPOS_DIA)])


if __name__ == "__main__":
    unittest.main()
