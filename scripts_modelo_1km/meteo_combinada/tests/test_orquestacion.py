"""Pruebas de orquestacion.py (§2.1, §7.1-§7.3, §8, §9 S9 y S13, §10, Anexo B; §2.5 del diseño).

Dueño: I20 (ola 5: M2a y M3-4 en la primera fase; M5 y M6 en la segunda; ola 6: ORQ-42 a ORQ-44; cierre: ORQ-45,
D59). Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest meteo_combinada.tests.test_orquestacion
Datos sólo sintéticos, en carpetas temporales (``entorno.rutas_sinteticas`` y los generadores de ``sintetico``): la
descarga DMC con el descargador fijado y el cliente falso, la política y el registro de C5 del reloj, meses ERA5-Land,
el geopotencial y su parquet, teselas NASADEM y GHS-POP, la grilla y los pesos, la meteorología SINCA y la red 2.
Ninguna prueba abre DMC, el reloj real, ERA5L, NASADEM, GHS-POP, SINCA, la grilla ni los pesos reales: toda corrida va
bajo ``ceguera.RegistroAccesos`` en bloqueo sobre /Volumes (0 accesos) y ``ceguera.SinRed``. Leen, sin escribir, el
código fijado (descargador, adaptador, ``dmc_features`` y la clausura del reloj) y los textos anclados de APH; si falta
uno o cambió de huella, la prueba se omite con el motivo y no se da por aprobada.

La red mínima (ORQ-14): 10 estaciones horarias de diciembre de 2019 a febrero de 2020 (cruza el corte de TF1) en dos
filas de cinco a ≈ 30 km, con 9 celdas cada una; sólo lo ambiental de p es decidible con meses de datos (no tiene EX).
Para que M5 y M6 sean comprobables: la población GHS crece hacia el este (z_poblada ≠ z_media), los pesos de la mitad
de las celdas crecen con el año, y cada monitor de la red 2 está en una celda de la grilla (AMB-1; sus coordenadas no
cambian). M5 y M6 corren sobre una copia de la corrida de M3-4 con la decisión de los cinco pares fabricada desde
``sintetico.tablas_metricas`` (las mismas tablas que lee ``decidir_combinacion``) y sellada otra vez; M6, además, con
las tablas de ``sintetico.tablas_m6`` y una fábrica de A26 falsa (la de producción v2 no está escrita), que una vez
arma la real (``Cfg.fabrica_m6``, ORQ-29) en dos días de enero de 2020. Los productos de M5 y M6 se comparan con los
de llamar a mano a ``producto``, ``salud`` y ``ambiental`` sobre las mismas entradas. La memoria de la selección
(ola 6: el fondo de los días de selección, ORQ-42, y las predicciones reducidas, ORQ-43) se compara bit a bit, con los
cinco pares, contra una copia literal de la unidad de la ola 5 sobre los residuos de la corrida de M3-4. Los procesos
por fase (D59, ORQ-45) se prueban en su forma, en el mínimo que recibe cada ``repartir`` (envuelto para anotarlo; con 3
procesos y topes de 1 y 2, el mínimo nunca es ``procesos``), en los mismos bytes de M3-4 y M5 con y sin ellos, y en que
M6 sigue con ``Cfg.procesos``.

Lo que la red mínima no muestra y queda sin prueba aquí (H8): la rama de dos pasadas de M2a (ningún píxel válido
necesita la hipsométrica, y fabricarlo cambia la alineación de S13); el objetivo de A16, las horas emparejadas y un
candidato no finito en E0 (con meses de datos sólo se decide lo ambiental de p, ORQ-14; la deriva en E0 sí se prueba);
las filas del panel en años sin ningún mes ERA5-Land (el panel sintético cae en los meses de datos; lo prueba I19 con
``anios`` y ``h_ultima``); y la lectura de las teselas NASADEM por lote (ORQ-4 las lee por ventana y las guarda).
"""
import sys

sys.dont_write_bytecode = True

import contextlib  # noqa: E402
import dataclasses  # noqa: E402
import gzip  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import pickle  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import Mock, patch  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import entorno  # noqa: E402,F401  (VAL-3: la base de zonas antes de validacion)
from meteo_combinada import candidatos, ceguera, constantes, fijados, fondo_era5l, numerico, orquestacion  # noqa: E402
from meteo_combinada import particiones, salidas  # noqa: E402
from meteo_combinada import sinca_meteo, tipos, umbrales  # noqa: E402
from meteo_combinada import sintetico as S  # noqa: E402
from meteo_combinada.orquestacion import Cfg  # noqa: E402

_AP = _RAIZ.parent
_APH = _AP.parent / "Air-Pollution-Health-Chile"
_ETIQUETA = "HUMAN20261027_METEO_COMB_1"
_UTC_MENOS_4 = -240
_DESDE, _HASTA = "2019-12-01", "2020-02-29"
_MESES_DATOS = ("201912", "202001", "202002")
_FILAS, _COLUMNAS = 2, 5                              # la red mínima: dos filas de cinco estaciones
_LAT0, _LON0, _PASO_LAT, _PASO_LON = -33.30, -71.20, 0.33, 0.30
_GRADIENTE = 0.0065                                   # K/m: sólo para fabricar un QFF coherente con QFE
_PAR_P = ((tipos.Uso.AMBIENTAL.value, tipos.Grupo.P.value),)
_CELDAS_POR_ESTACION = 9
_COMPARACION_M6 = "DATOS/m6/comparacion_v2.parquet"


# ---------------------------------------------------------------------------
# Funciones de módulo para los trabajadores (se pasan por referencia)
# ---------------------------------------------------------------------------
def _cuadrado(x):
    return x * x


def _con_contexto(x, ctx):
    return (x, ctx["suma"] + x)


def _t2m_emc3(unidad, ctx):
    """Sólo formas sintéticas para recorrer M5 sin entradas ambientales ni código de RELOJ."""
    return {"h": np.array([0]), "t2m": np.empty((1, len(unidad["pixeles"])))}


def _anio_emc3(unidad, ctx):
    return {"nc": {}, "salud": {}, "laterales": {}}


def _grupo_e_hilos(x):
    from meteo_combinada import entorno as e
    import threadpoolctl
    return {"x": x, "pid": os.getpid(), "pgid": os.getpgid(0), "nice": os.nice(0),
            "variables": {v: os.environ.get(v) for v in e.VARIABLES_HILOS},
            "hilos": sorted({b["num_threads"] for b in threadpoolctl.threadpool_info()}),
            "bytecode": sys.flags.dont_write_bytecode or sys.dont_write_bytecode}


def _falla_en_tres(x):
    if x == 3:
        raise ValueError("unidad mala")
    time.sleep(0.05)
    return x


def _lee_volumes(x):
    with open("/" + "Volumes" + "/no_existe_meteo_combinada/x", "rb") as f:
        return f.read()


def _dormir(x):
    time.sleep(0.2)
    return x


def _larga_o_falla(x):
    if x == 0:
        time.sleep(0.3)
        raise ValueError("unidad mala")
    time.sleep(120)
    return x


# ---------------------------------------------------------------------------
# Ayudas
# ---------------------------------------------------------------------------
def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _umbrales():
    if not (_APH / umbrales.TEXTO_M0).is_file() or not (_APH / umbrales.TEXTO_VIGENTE).is_file():
        raise unittest.SkipTest("faltan los textos anclados en APH; la prueba no se da por aprobada")
    return umbrales.cargar_m0(_APH)


def _codigo_fijado():
    for ruta, sha in ((_AP / fijados.RUTA_DESCARGADOR, fijados.SHA_DESCARGADOR),
                      (_AP / fijados.RUTA_ADAPTADOR, fijados.SHA_ADAPTADOR),
                      (_AP / fijados.RUTA_DMC_FEATURES, fijados.SHA_DMC_FEATURES)):
        if not ruta.is_file() or _sha(ruta.read_bytes()) != sha:
            raise unittest.SkipTest(f"{ruta.name} falta o cambió de huella; no se da por aprobada")
    try:
        if fijados.huellas_reloj(_AP) != dict(fijados.HUELLAS_RELOJ):
            raise unittest.SkipTest("la clausura del reloj cambió respecto de la fijada (FIJ-1); no se da por aprobada")
    except (OSError, ValueError) as e:
        raise unittest.SkipTest(f"no se puede leer la clausura del reloj ({e}); no se da por aprobada")
    return fijados.cargar_descargador(_AP)


def _guardas():
    """Las de S10: bloqueo sobre /Volumes y sin red (el registro se devuelve para contar sus accesos)."""
    return ceguera.RegistroAccesos(("/" + "Volumes",), bloquear=True), ceguera.SinRed()


def _escribir_parquet(ruta: Path, df: pd.DataFrame) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    ruta.write_bytes(buf.getvalue())


def _z_terreno(lat, lon):
    """La altitud sintética (m), suave: sube hacia el este."""
    return 400.0 + 600.0 * (np.asarray(lon) + 71.4) + 50.0 * np.sin(np.asarray(lat) * 20.0)


def _portal(Ts, p_F, z_s: float, h: np.ndarray, k: int) -> dict:
    """Textos de una estación limpia (como ``test_integracion._portal``): Ts al décimo, Td bajo Ts, HR coherente, viento
    sin rachas ni ceros, QFE = p_F·exp(r_p) y un QFF coherente con QFE: ninguna regla de §2.4 debería saltar."""
    i = np.arange(h.size)
    hora = h % numerico.PERIODO_DIA_H
    Ts = np.round(np.asarray(Ts, dtype=np.float64), 1)
    deficit = 4.5 + 2.0 * np.cos(2 * np.pi * (hora - 19) / 24) ** 2 + 0.3 * np.sin(i / 3.7 + k)
    Td = np.round(Ts - deficit, 1)
    HR = np.round(numerico.hr_desde(Ts, Td))
    r_p = 0.002 * (1 + 0.3 * k) + 0.0002 * np.sin(i / 17.0 + k)
    QFE = np.round(np.asarray(p_F, dtype=np.float64) * np.exp(r_p), 1)
    t_media = Ts + constantes.valor("KELVIN") + _GRADIENTE * z_s / 2
    QFF = np.round(QFE * np.exp(constantes.valor("GRAVEDAD") * z_s / (constantes.valor("R_SECO") * t_media)), 1)
    return {"Ts": Ts, "Td": Td, "relative_humidity": HR, "wind_speed_instant": (4 + (i + k) % 9).astype(float),
            "wind_direction_instant": (((37 * i + 7 * k) % 36 + 1) * 10).astype(float), "QFE": QFE, "QFF": QFF}


def _campos_era5(pid: np.ndarray, cat: pd.DataFrame, horas: np.ndarray) -> dict:
    """Campos ERA5-Land suaves (unidades nativas) en los píxeles, hora × píxel."""
    lat = cat.set_index("pixel_id").loc[pid, "latitude"].to_numpy()
    lon = cat.set_index("pixel_id").loc[pid, "longitude"].to_numpy()
    z = _z_terreno(lat, lon)
    hh = horas.astype(np.float64)[:, None]
    hora = (horas % 24).astype(np.float64)[:, None]
    t2m = 288.15 - 0.0065 * z[None, :] + 5.0 * np.cos(2 * np.pi * (hora - 19) / 24) + 0.4 * np.sin(hh / 53.0)
    d2m = t2m - 6.0 - 1.5 * np.cos(2 * np.pi * (hora - 19) / 24)
    sp = 101325.0 * np.exp(-z[None, :] / 8434.0) * (1 + 0.002 * np.sin(hh / 31.0) + 0.0005 * np.cos(4 * np.pi * hora / 24))
    u10 = 1.5 + 0.5 * np.sin(2 * np.pi * hora / 24) + 0.0 * z[None, :]
    v10 = -0.5 + 0.3 * np.cos(hh / 41.0) + 0.0 * z[None, :]
    return {"t2m": t2m, "d2m": d2m, "sp": sp, "u10": u10, "v10": v10}


def _horas_de_mes(yyyymm: str) -> np.ndarray:
    t = S.horas_del_mes(int(yyyymm[:4]), int(yyyymm[4:]))
    return ((t - np.datetime64("2000-01-01T00:00:00", "s")) // np.timedelta64(1, "h")).astype(np.int64)


# ---------------------------------------------------------------------------
# El mundo sintético de M2a y M3-4 (una vez por proceso)
# ---------------------------------------------------------------------------
class _Mundo:
    """La carpeta base: entradas de M2a y M3-4 y la corrida de M2a; las corridas de M3-4 van en copias de ella."""

    def __init__(self):
        self.U = _umbrales()
        self.descargador = _codigo_fijado()
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.rutas = entorno.rutas_sinteticas(self.base)
        self._entradas()
        registro, red = _guardas()
        with registro, red:
            cfg = self.cfg_m2a(self.rutas)
            self.m2a = orquestacion.correr_m2a(cfg, avance=orquestacion.abrir_avance(cfg, "m2a"))
        self.accesos_m2a = list(registro.accesos)

    # --- las entradas ---
    def _entradas(self) -> None:
        r = self.rutas
        self.codigos = [f"{330300 + n:06d}" for n in range(_FILAS * _COLUMNAS)]
        puntos = []
        for i in range(_FILAS):
            for j in range(_COLUMNAS):
                n = i * _COLUMNAS + j
                puntos.append((round(_LAT0 - i * _PASO_LAT - 0.011 * (n % 3), 4),
                               round(_LON0 + j * _PASO_LON + 0.013 * (n % 4), 4)))
        self.puntos = dict(zip(self.codigos, puntos))
        self.z = {c: float(np.round(_z_terreno(la, lo))) for c, (la, lo) in self.puntos.items()}
        # ERA5-Land: catálogo, geopotencial y meses (con sus píxeles válidos: todos)
        cat = S.catalogo_pixeles(-33.1, -71.4, 9, 16)
        self.cat = cat
        _escribir_parquet(r.era5l / "catalogo_pixeles.parquet", cat)
        z_pix = _z_terreno(cat["latitude"].to_numpy(), cat["longitude"].to_numpy())
        S.geopotencial_sintetico(r.invariantes, cat, z_pix)
        pid = cat["pixel_id"].to_numpy(np.int64)
        self.meses = {}
        for m in sorted({*_MESES_DATOS, *orquestacion.MESES_VALIDEZ}):
            horas = _horas_de_mes(m)
            campos = _campos_era5(pid, cat, horas)
            tiempos = S.horas_del_mes(int(m[:4]), int(m[4:]))
            campos["tp"] = S.tp_acumulado(tiempos, np.full((horas.size, pid.size), 1e-4))
            ruta = S.mes_era5_netcdf(r.era5l / f"era5land_chile_{m}.nc", campos, tiempos, pid)
            self.meses[m] = f"ERA5L/{ruta.name}"
        self.h_ultima = int(_horas_de_mes(max(self.meses))[-1])
        # el fondo en las estaciones, por el camino del módulo, para fabricar observaciones limpias
        z_tabla = pd.DataFrame({"pixel_id": pid, "z_e5l": z_pix})
        lat = np.array([self.puntos[c][0] for c in self.codigos])
        lon = np.array([self.puntos[c][1] for c in self.codigos])
        op = fondo_era5l.operador(lat, lon, np.array([self.z[c] for c in self.codigos]), cat, pid, z_tabla, self.U,
                                  ids=np.array(self.codigos, dtype=object))
        F = {c: [] for c in fondo_era5l.CAMPOS_F}
        horas = []
        for m in _MESES_DATOS:
            mes = fondo_era5l.leer_mes(orquestacion.ruta_de_alias(r, self.meses[m]))
            campos = fondo_era5l.campos_fondo(mes, op, self.U)
            horas.append(np.asarray(mes.tiempos, dtype=np.int64))
            for k in F:
                F[k].append(campos[k])
        h_todas = np.concatenate(horas)
        F = {k: np.concatenate(v, axis=0) for k, v in F.items()}
        L = pd.date_range(f"{_DESDE}T00:00", f"{_HASTA}T19:00", freq="h")
        h = ((L - pd.Timedelta(minutes=_UTC_MENOS_4) - pd.Timestamp("2000-01-01")) // pd.Timedelta(hours=1)).to_numpy()
        pos = np.searchsorted(h_todas, h)
        estaciones = []
        for k, c in enumerate(self.codigos):
            T_F, p_F = F["T_F"][pos, k], F["p_F"][pos, k]
            Ts = T_F + 1.0 + 0.4 * (self.puntos[c][0] + 33.3) + 0.2 * np.sin(np.arange(h.size) / 5.3 + k)
            columnas = _portal(Ts, p_F, self.z[c], h, k)
            estaciones.append(S.estacion_sintetica(c, *self.puntos[c], self.z[c], L, **columnas))
        dmc = S.fabricar_descarga(estaciones, r.dmc.parent, self.descargador, _DESDE, _HASTA)
        assert dmc == Path(os.path.realpath(r.dmc))
        regla = [{"tramo": "1.1", "valid_from": f"{_DESDE}T00:00:00", "valid_to": f"{_HASTA}T23:00:00",
                  "minutos": _UTC_MENOS_4, "veredicto": "F(-4)"}]
        S.politica_reloj_sintetica(r.ap.parent, S.artefactos_de_descarga(dmc), {c: regla for c in self.codigos})
        self.registro_c5 = entorno.alias(S.rutas_politica_sintetica(r.ap.parent)["registro"], r)
        # NASADEM (una tesela por estación) y GHS-POP (una ventana junto a la primera)
        self.teselas = []
        for c in self.codigos:
            la, lo = self.puntos[c]
            ruta = S.tesela_nasadem(r.nasadem / f"s34w072_{c}.tif", _z_terreno, oeste=lo - 0.065, norte=la + 0.065,
                                    filas=470, columnas=470)
            self.teselas.append(f"NASADEM/{ruta.name}")
        la, lo = self.puntos[self.codigos[0]]
        # la población crece hacia el este (como el terreno), así z_poblada ≠ z_media en esas celdas (§3)
        ghs = S.tesela_ghs(r.ghs / "GHS_POP_E2020_sintetica.tif",
                           lambda a, b: 10.0 + 4000.0 * np.clip(np.asarray(b) - (lo - 0.04), 0.0, None),
                           lat_centro=la, lon_centro=lo, filas=60, columnas=60)
        self.ghs = [f"GHS/{ghs.name}"]
        # la grilla y los pesos: 9 celdas por estación, una comuna por estación
        partes = {k: [] for k in ("celdas", "estaticas", "estaticas_lulc", "enlaces_productos", "pesos")}
        for n, c in enumerate(self.codigos):
            la, lo = self.puntos[c]
            g = S.grilla(_CELDAS_POR_ESTACION, (13101 + n,), lat0=math.floor(la * 100) / 100 + 0.02,
                         lon0=math.floor(lo * 100) / 100 - 0.01,
                         anios_pesos=tuple(range(2000, 2026)), semilla=20261023 + n)
            for k in partes:
                partes[k].append(g[k])
        for k, nombre in (("celdas", "celdas.parquet"), ("estaticas", "estaticas.parquet"),
                          ("estaticas_lulc", "estaticas_lulc.parquet"),
                          ("enlaces_productos", "enlaces_productos.parquet")):
            _escribir_parquet(r.grilla / nombre, pd.concat(partes[k], ignore_index=True))
        # los pesos de las celdas de id impar crecen un 2 % al año: los pesos de cada año importan (§7.2, §7.3)
        pesos = pd.concat(partes["pesos"], ignore_index=True)
        tendencia = 1.0 + 0.02 * (pesos["anio"].to_numpy(np.float64) - 2000) * (pesos["celda"].to_numpy() % 2)
        pesos["w_ghs"] = (pesos["w_ghs"].to_numpy(np.float64) * tendencia).astype(pesos["w_ghs"].dtype)
        _escribir_parquet(r.pesos / "poblacion_celda_anio.parquet", pesos)
        # SINCA y la red 2
        S.sinca_sintetico(r.sinca_met, desde=_DESDE, hasta=_HASTA)
        politica = {"sinca": {"reloj_fuente": "hora_local_civil_sinca_sin_offset",
                              "utc_salida": "datetime_naive_que_representa_utc",
                              "zona_iana_default": "America/Santiago",
                              "zonas_iana_por_region": {"RXI": "America/Coyhaique", "RXII": "America/Punta_Arenas"},
                              "hora_ambigua": ("conservar_hora_local_asumir_ocurrencia_estandar_y_registrar_utc_"
                                               "alternativo"),
                              "hora_inexistente": "conservar_hora_local_desplazar_adelante_y_marcar_qc",
                              "colision_misma_utc_en_panel": ("media_con_conteo_y_bandera_manteniendo_el_lector_crudo_"
                                                              "sin_agregar")}}
        (r.datos / "sinca_politica").mkdir(parents=True, exist_ok=True)
        (r.datos / "sinca_politica" / "politica_temporal.json").write_text(json.dumps(politica), encoding="utf-8")
        veredictos = pd.DataFrame({"estacion": pd.Series([], dtype="string"),
                                   "contaminante": pd.Series([], dtype="string"),
                                   "anio": pd.Series([], dtype="int64"), "veredicto_fin": pd.Series([], dtype="string"),
                                   "veredicto_inicio_mas_1h": pd.Series([], dtype="string")})
        _escribir_parquet(r.datos / "sinca_politica" / "veredictos.parquet", veredictos)
        sha_v = _sha((r.datos / "sinca_politica" / "veredictos.parquet").read_bytes())
        resumen = {"schema": "airpollution.modelo-1km-v2.reloj-sinca-red2.v1",
                   "politica_temporal_sha256": sinca_meteo.SHA_POLITICA_TEMPORAL,
                   "huella_veredictos_contenido": sinca_meteo.huella_contenido(
                       pd.read_parquet(r.datos / "sinca_politica" / "veredictos.parquet")),
                   "sha256_veredictos": sha_v, "convencion_civil": {"elegida": "fin"}, "series": 0}
        (r.datos / "sinca_politica" / "resumen.json").write_text(json.dumps(resumen), encoding="utf-8")
        red2 = S.panel_y_pliegues(r.datos / "red2", desde=_DESDE, hasta=_HASTA)
        _red2_en_la_grilla(red2, pd.concat(partes["celdas"], ignore_index=True))

    def entradas_m2a(self) -> dict:
        return {"catalogo_dmc": f"DMC/{orquestacion.CATALOGO_DMC}", "catalogo_pixeles": "ERA5L/catalogo_pixeles.parquet",
                "geopotencial": "INVARIANTES/era5land_geopotencial_invariante_chile.nc",
                "altitud_pixeles": "INVARIANTES/era5land_altitud_modelo_pixeles.parquet",
                "meses_era5l": dict(self.meses), "h_ultima": self.h_ultima, "nasadem": list(self.teselas),
                "ghs": list(self.ghs), "celdas": "GRILLA/celdas.parquet", "estaticas": "GRILLA/estaticas.parquet",
                "estaticas_lulc": "GRILLA/estaticas_lulc.parquet", "pesos": "PESOS/poblacion_celda_anio.parquet"}

    def entradas_m34(self) -> dict:
        sinca = ["SINCA_MET/" + n for n in S.huellas_sinca(self.rutas.sinca_met)]
        return {"m2a": "LOCAL/meteo_combinada/v1/m2a", "registro_c5": self.registro_c5,
                "catalogo_dmc": f"DMC/{orquestacion.CATALOGO_DMC}", "catalogo_pixeles": "ERA5L/catalogo_pixeles.parquet",
                "meses_era5l": dict(self.meses), "h_ultima": self.h_ultima, "celdas": "GRILLA/celdas.parquet",
                "enlaces": "GRILLA/enlaces_productos.parquet", "pesos": "PESOS/poblacion_celda_anio.parquet",
                "red2": {"pliegues": "DATOS/red2/" + S.NOMBRE_PLIEGUES_RED2,
                         "paneles": {p: f"DATOS/red2/paneles/panel_{p}_red2.parquet" for p in tipos.CONTAMINANTES_M6}},
                "sinca": {"raiz": "SINCA_MET", "archivos": sinca,
                          "politica_temporal": "DATOS/sinca_politica/politica_temporal.json",
                          "veredictos": "DATOS/sinca_politica/veredictos.parquet",
                          "resumen": "DATOS/sinca_politica/resumen.json", "convencion": "fin"}}

    @staticmethod
    def _huellas(rutas, entradas) -> dict:
        salida = {}

        def recorrer(v):
            if isinstance(v, dict):
                for x in v.values():
                    recorrer(x)
            elif isinstance(v, (list, tuple)):
                for x in v:
                    recorrer(x)
            elif isinstance(v, str) and "/" in v:
                ruta = orquestacion.ruta_de_alias(rutas, v)
                if ruta.is_file():
                    salida[v] = _sha(ruta.read_bytes())
        recorrer(entradas)
        return salida

    def cfg_m2a(self, rutas, **cambios) -> Cfg:
        e = self.entradas_m2a()
        return Cfg(rutas=rutas, umbrales=self.U, entradas=e, huellas=self._huellas(rutas, e), **cambios)

    @staticmethod
    def _registros(rutas, *nombres) -> dict:
        """H5: los registros de las compuertas anteriores en la lista cerrada (el de M2a; ``decision.json`` y el recibo
        de la corrida), con su huella, si existen."""
        salida = {}
        for carpeta, nombre in nombres:
            ruta = carpeta / nombre
            if ruta.is_file():
                salida[entorno.alias(ruta, rutas)] = _sha(ruta.read_bytes())
        return salida

    def cfg_m34(self, rutas, **cambios) -> Cfg:
        e = self.entradas_m34()
        base = {"pares": _PAR_P, "etiqueta": _ETIQUETA}
        huellas = {**self._huellas(rutas, e),
                   **self._registros(rutas, (entorno.carpeta_salida(rutas, "m2a"), orquestacion.REGISTRO_M2A))}
        return Cfg(rutas=rutas, umbrales=self.U, entradas=e, huellas=huellas, **{**base, **cambios})

    def copia(self, *, con_m2a: bool = True) -> tuple[tempfile.TemporaryDirectory, entorno.Rutas]:
        """Una copia de la carpeta base (entradas y, si ``con_m2a``, la corrida de M2a) para otra corrida: los mismos
        alias y bytes."""
        return _copiar(self.base, sin_salidas=not con_m2a)

    def entradas_m5(self) -> dict:
        """ORQ-21: las entradas de M5 (y, con la comparación de v2, las de M6)."""
        e = self.entradas_m34()
        return {k: e[k] for k in orquestacion.ENTRADAS_M5}

    def cfg_m5(self, rutas, **cambios) -> Cfg:
        e = self.entradas_m5()
        corrida = entorno.carpeta_salida(rutas, "m5", _ETIQUETA)
        huellas = {**self._huellas(rutas, e), **self._registros(rutas, (corrida, salidas.DECISION))}
        return Cfg(rutas=rutas, umbrales=self.U, entradas=e, huellas=huellas, **{"etiqueta": _ETIQUETA, **cambios})

    def cfg_m6(self, rutas, **cambios) -> Cfg:
        e = {**self.entradas_m5(), "comparacion_m6": _COMPARACION_M6}
        corrida = entorno.carpeta_salida(rutas, "m5", _ETIQUETA)
        huellas = {**self._huellas(rutas, e),
                   **self._registros(rutas, (corrida, salidas.DECISION), (corrida, salidas.RECIBO))}
        return Cfg(rutas=rutas, umbrales=self.U, entradas=e, huellas=huellas, **{"etiqueta": _ETIQUETA, **cambios})


def _copiar(base, *, sin_salidas: bool = False) -> tuple[tempfile.TemporaryDirectory, entorno.Rutas]:
    """Una copia de una carpeta base sintética (entradas y corridas) en otra carpeta temporal: los mismos alias y
    bytes. ``sin_salidas`` deja fuera ``LOCAL/meteo_combinada``."""
    base = Path(base)
    tmp = tempfile.TemporaryDirectory()
    salidas_base = Path(os.path.realpath(entorno.rutas_sinteticas(base).salidas))
    ignorar = None if not sin_salidas else (lambda d, nombres: [n for n in nombres
                                                                if Path(os.path.realpath(d)) / n == salidas_base])
    shutil.copytree(base, tmp.name, symlinks=True, dirs_exist_ok=True, ignore=ignorar)
    return tmp, entorno.rutas_sinteticas(tmp.name)


def _red2_en_la_grilla(red2: dict, celdas: pd.DataFrame) -> None:
    """La red 2 sintética con cada monitor en una celda de la grilla mínima, con sus huellas rehechas (R21). La lateral
    se evalúa en la celda del monitor y sus coordenadas no entran a la cuenta (AMB-1); π^mon usa las coordenadas, que
    no cambian. Sin esto, ningún monitor de ``sintetico.panel_y_pliegues`` cae en la grilla de 90 celdas."""
    ruta_pl = Path(red2["pliegues"])
    manifiesto = json.loads(ruta_pl.read_text(encoding="utf-8"))
    ids = sorted(int(c) for c in celdas["celda"])
    nueva = {e["estacion"]: ids[(k * _CELDAS_POR_ESTACION + _CELDAS_POR_ESTACION // 2) % len(ids)]
             for k, e in enumerate(manifiesto["estaciones"])}
    for e in manifiesto["estaciones"]:
        e["celda"] = nueva[e["estacion"]]
    for pol, registro in manifiesto["contaminantes"].items():
        ruta = Path(red2[f"panel_{pol}"])
        panel = pd.read_parquet(ruta)
        panel["celda"] = panel["estacion"].astype(str).map(nueva).astype(np.int64)
        buf = io.BytesIO()
        panel.to_parquet(buf, index=False)
        ruta.write_bytes(buf.getvalue())
        registro["panel"]["sha256"] = _sha(buf.getvalue())
        lado = ruta.with_suffix(".json")
        if lado.is_file():
            meta = json.loads(lado.read_text(encoding="utf-8"))
            meta["sha256"] = registro["panel"]["sha256"]
            lado.write_text(json.dumps(meta, sort_keys=True), encoding="utf-8")
    manifiesto["huella_pliegues"] = S.huella_pliegues(manifiesto)
    ruta_pl.write_bytes(json.dumps(manifiesto, ensure_ascii=False, indent=1).encode("utf-8") + b"\n")


_MUNDO: _Mundo | None = None
_CORRIDAS: dict = {}


def _mundo() -> _Mundo:
    global _MUNDO
    if _MUNDO is None:
        _MUNDO = _Mundo()
    return _MUNDO


def _correr_m34(procesos: int, *, interrumpir_tras: int | None = None) -> dict:
    """Una corrida de M3-4 en una copia de la base; con ``interrumpir_tras``, cortada y reanudada (S9)."""
    clave = (procesos, interrumpir_tras)
    if clave in _CORRIDAS:
        return _CORRIDAS[clave]
    m = _mundo()
    tmp, rutas = m.copia()
    cfg = m.cfg_m34(rutas, procesos=procesos)
    registro, red = _guardas()
    cortada = False
    t0 = time.time()
    with registro, red:
        if interrumpir_tras is not None:
            try:
                orquestacion.correr_m34(cfg, avance=orquestacion.abrir_avance(cfg, "m34", interrumpir_tras=interrumpir_tras),
                                        procesos=procesos)
            except orquestacion.InterrupcionSimulada:
                cortada = True
            vivos_corte = ceguera.procesos_hijos_vivos()
        avance = orquestacion.abrir_avance(cfg, "m34")
        r = orquestacion.correr_m34(cfg, avance=avance, procesos=procesos)
    carpeta = r["carpeta"]
    inventario = json.loads((carpeta / salidas.SHA256_JSON).read_text(encoding="utf-8"))["archivos"]
    salida = {"tmp": tmp, "rutas": rutas, "cfg": cfg, "r": r, "carpeta": carpeta, "inventario": inventario,
              "accesos": list(registro.accesos), "red": list(red.intentos), "cortada": cortada,
              "saltadas": list(avance.saltadas), "segundos": time.time() - t0,
              "vivos_corte": vivos_corte if interrumpir_tras is not None else []}
    _CORRIDAS[clave] = salida
    return salida


def _sin_avance(inventario: dict) -> dict:
    """Lo comparable entre corridas (S9): todo menos ``avance.jsonl`` (huellas y estado de la corrida)."""
    return {k: v for k, v in inventario.items() if k != orquestacion.AVANCE}


# ORQ-45 (D59, A39): unos procesos por fase con topes de los dos lados de 2 procesos (3 y PROCESOS por encima, 1 por
# debajo), para la forma y el mínimo; y, para las corridas, 3 procesos con topes de 1 y 2 en las cinco fases: en cada
# una el mínimo es su tope y no ``procesos``, así que una fase que pasara ``procesos`` a ``repartir`` se ve.
_POR_FASE = {"m34": {"artefactos": 3, "seleccion_y_prediccion": 1,
                     "tendencias_y_finitud": constantes.valor("PROCESOS")},
             "m5": {"representatividad": 1, "anual": constantes.valor("PROCESOS")}}
_PROCESOS_CORRIDA = 3
_POR_FASE_CORRIDA = {"m34": {"artefactos": 2, "seleccion_y_prediccion": 1, "tendencias_y_finitud": 2},
                     "m5": {"representatividad": 1, "anual": 2}}
_POR_FASE_CORRIDAS: dict = {}


@contextlib.contextmanager
def _repartir_anotado(llamadas: list):
    """Anota (unidad, procesos) de cada llamada a ``orquestacion.repartir`` mientras dura (ORQ-45, D59)."""
    original = orquestacion.repartir

    def anotado(unidades, funcion, procesos, **k):
        llamadas.append((funcion.__name__, procesos))
        return original(unidades, funcion, procesos, **k)
    orquestacion.repartir = anotado
    try:
        yield llamadas
    finally:
        orquestacion.repartir = original


def _correr_por_fase(compuerta: str, procesos: int, por_fase: dict) -> dict:
    """M3-4 (en una copia de la base) o M5 (en una copia de su plantilla) con ``Cfg.procesos_por_fase`` = ``por_fase``
    y ``procesos``, anotando (unidad, procesos) de cada llamada a ``orquestacion.repartir`` (ORQ-45, D59)."""
    clave = (compuerta, procesos, json.dumps(por_fase, sort_keys=True))
    if clave in _POR_FASE_CORRIDAS:
        return _POR_FASE_CORRIDAS[clave]
    m = _mundo()
    if compuerta == "m34":
        tmp, rutas = m.copia()
        cfg, correr = m.cfg_m34(rutas, procesos=procesos, procesos_por_fase=por_fase), orquestacion.correr_m34
    else:
        tmp, rutas = _copiar(_plantilla_m5("base")["tmp"].name)
        cfg, correr = m.cfg_m5(rutas, procesos=procesos, procesos_por_fase=por_fase), orquestacion.correr_m5
    registro, red = _guardas()
    llamadas: list = []
    with _repartir_anotado(llamadas), registro, red:
        r = correr(cfg, avance=orquestacion.abrir_avance(cfg, compuerta), procesos=procesos)
    carpeta = r["carpeta"]
    _POR_FASE_CORRIDAS[clave] = {
        "tmp": tmp, "cfg": cfg, "r": r, "carpeta": carpeta, "llamadas": llamadas, "accesos": list(registro.accesos),
        "red": list(red.intentos),
        "inventario": json.loads((carpeta / salidas.SHA256_JSON).read_text(encoding="utf-8"))["archivos"],
        "recibo": json.loads((carpeta / salidas.RECIBO).read_text(encoding="utf-8"))}
    return _POR_FASE_CORRIDAS[clave]


# ---------------------------------------------------------------------------
# M5 y M6: la decisión de los cinco pares, fabricada (ORQ-14)
# ---------------------------------------------------------------------------
# La red mínima sólo decide lo ambiental de p (ORQ-14). Para M5 y M6 la carpeta de M3-4 se copia y su decisión se
# rehace con los casos de ``sintetico.tablas_metricas`` (las mismas tablas que lee ``decidir_combinacion``): (T, Td)
# ambiental gana AB, (u, v) A y p B (como ``test_decision._ambientales``); lo agudo, «agudo_nivel» con el nivel de AB
# de vuelta a la base (gana AB, como ``test_decision._agudo_base``); lo crónico, «tf2_no_evaluable» (gana C_est por la
# regla crónica). Así M5 pasa por A, B, AB y C_est, y M6 tiene B y AB en lo ambiental (la rama 3 rehace T_Td y p).
_H_A = tipos.Hiper(50.0, 150.0, 0.2)
_H_B = tipos.Hiper(25.0, 50.0, 0.5)
_H_PHI = tipos.Hiper(25.0, 0.0, 1.0)
_ALFA = 10.0
_CASOS_DECISION = {("ambiental", "T_Td"): "ganador_claro", ("ambiental", "u_v"): "uv", ("ambiental", "p"): "p_sin_ex",
                   ("agudo", "T_Td"): "agudo_nivel", ("cronico", "T_Td"): "tf2_no_evaluable"}
_GANADORES = {("ambiental", "T_Td"): "AB", ("ambiental", "u_v"): "A", ("ambiental", "p"): "B",
              ("agudo", "T_Td"): "AB", ("cronico", "T_Td"): "C_est"}
_VARIABLES_GRUPO = {"T_Td": ("T", "Td"), "u_v": ("u", "v"), "p": ("p",)}
_THETA = {"A": _H_A, "B": _H_B, "AB": (_H_A, _H_PHI), "C": _ALFA, "C_est": _ALFA}            # los ambientales
_H_A_SALUD, _H_PHI_SALUD = tipos.Hiper(100.0, 50.0, 0.05), tipos.Hiper(50.0, 0.0, 0.5)
_THETA_SALUD = {"A": _H_A_SALUD, "B": tipos.Hiper(50.0, 150.0, 1.0), "AB": (_H_A_SALUD, _H_PHI_SALUD), "C": 100.0,
                "C_est": 100.0}                                                              # los agudos y crónicos
_PLANTILLA: dict = {}
_M5: dict = {}
_M6: dict = {}


_SIN_B_AB = (("ambiental", "T_Td"), ("ambiental", "p"))     # «sin_b_ab»: B y AB fuera de E0 por deriva (gana A)
_EXCLUIDA = "330304"                                           # «una_excluida»: su T observada, invertida


def _tablas_de_par(uso: str, grupo: str, variante: str = "base") -> dict:
    d = S.tablas_metricas(_CASOS_DECISION[(uso, grupo)])
    val = d["validacion"].copy()
    if (uso, grupo) == ("agudo", "T_Td"):
        m = ((val.candidato == "AB") & (val.variable == "temp_media") & (val.estrato == "nacional")
             & (val.particion == "agregado")).to_numpy(dtype=bool)
        val.loc[m, "nivel"] = 1.05
    t = {"validacion": val, "tf": d["tf"], "replicas": d["replicas"], "motivos": d["e0_excluidos"]}
    if variante == "sin_b_ab" and (uso, grupo) in _SIN_B_AB:          # como test_decision._ambientales_sin_b_ab
        t["motivos"] = {"B": ("deriva",), "AB": ("deriva",)}
        t["replicas"] = d["replicas"][d["replicas"].candidato.isin(["A", "C"]).to_numpy(bool)].reset_index(drop=True)
    return t


def _ganadores(variante: str) -> dict:
    return {**_GANADORES, **({par: "A" for par in _SIN_B_AB} if variante == "sin_b_ab" else {})}


def _entradas_de(uso: str, grupo: str, t: dict) -> tipos.EntradasDecision:
    return tipos.EntradasDecision(tipos.Uso(uso), tipos.Grupo(grupo), t["validacion"], t["tf"], t["replicas"],
                                  t["motivos"])


def _hiper_fabricados(uso: str, grupo: str) -> dict:
    cands = ("A", "B", "AB", "C_est") if uso == "cronico" else ("A", "B", "AB", "C")
    theta = _THETA if uso == "ambiental" else _THETA_SALUD
    return {c: {v: theta[c] for v in _VARIABLES_GRUPO[grupo]} for c in cands}


def _plantilla_m5(variante: str = "base") -> dict:
    """La carpeta de M3-4 (1 proceso) copiada, con la decisión de los cinco pares fabricada (arriba), sus tablas en
    ``validacion/`` y ``tendencias/`` (las que M6 relee, DEC-16) y sellada otra vez (SLD-10). «una_excluida»: además,
    la T observada de una estación invertida en su tabla de control de calidad, para que la representatividad la
    excluya (r = −1 con la t2m de su píxel, §7.2, punto 6)."""
    if variante in _PLANTILLA:
        return _PLANTILLA[variante]
    from meteo_combinada import decision
    m = _mundo()
    c34 = _correr_m34(1)
    tmp, rutas = _copiar(c34["tmp"].name)
    carpeta = entorno.carpeta_salida(rutas, "m34", _ETIQUETA)
    tablas = {par: _tablas_de_par(*par, variante) for par in _CASOS_DECISION}
    decisiones = [decision.decidir_combinacion(u, g, _entradas_de(u, g, t), umbrales=m.U)
                  for (u, g), t in tablas.items()]
    assert {(d.uso.value, d.grupo.value): d.ganador for d in decisiones} == _ganadores(variante)
    if variante == "una_excluida":
        nombre = f"qc/estaciones/{_EXCLUIDA}.parquet"
        ancha = pd.read_parquet(carpeta / nombre)
        meta = ancha.attrs["metadatos"]
        ancha["Ts"] = (40.0 - ancha["Ts"].astype(np.float64)).astype(np.float32)
        ancha.attrs = {"esquema": tipos.ESQUEMA_QC_ESTACION.version}
        salidas.escribir(nombre, ancha, clase="insumo", esquema=tipos.ESQUEMA_QC_ESTACION, raiz=carpeta, metadatos=meta)
    juntas = {k: pd.concat([t[k] for t in tablas.values()], ignore_index=True) for k in ("validacion", "tf")}
    escribir = {"validacion/puntajes.parquet": (juntas["validacion"], tipos.ESQUEMA_VALIDACION_PUB),
                "tendencias/resumen_tf.parquet": (juntas["tf"], tipos.ESQUEMA_TF)}
    for (u, g), t in tablas.items():
        escribir[f"validacion/remuestreo_{u}_{g}.parquet"] = (t["replicas"], tipos.ESQUEMA_REPLICAS)
    huellas = {}
    for nombre, (df, esquema) in escribir.items():
        df = df.astype(dict(esquema))
        df.attrs = {"esquema": esquema.version}
        huellas[entorno.alias(carpeta / nombre, rutas)] = salidas.escribir(
            nombre, df, clase=ceguera.clase_de_ruta(nombre), esquema=esquema, raiz=carpeta)
    hiper = {f"{u}/{g}": _hiper_fabricados(u, g) for (u, g) in _CASOS_DECISION}
    contenido = decision.decision_json(decisiones, hiper, huellas)
    salidas.escribir(salidas.DECISION, contenido, clase="metrica", raiz=carpeta)
    salidas.sellar_corrida(carpeta, m._huellas(rutas, m.entradas_m34()), orquestacion._entorno_recibo(1), rutas=rutas)
    _PLANTILLA[variante] = {"tmp": tmp, "rutas": rutas, "tablas": tablas, "decision": contenido}
    return _PLANTILLA[variante]


def _correr_m5(procesos: int, *, interrumpir_tras: int | None = None, variante: str = "base") -> dict:
    """Una corrida de M5 en una copia de la plantilla; con ``interrumpir_tras``, cortada y reanudada (S9)."""
    clave = (procesos, interrumpir_tras, variante)
    if clave in _M5:
        return _M5[clave]
    m = _mundo()
    tmp, rutas = _copiar(_plantilla_m5(variante)["tmp"].name)
    cfg = m.cfg_m5(rutas, procesos=procesos)
    registro, red = _guardas()
    cortada, vivos_corte = False, []
    t0 = time.time()
    with registro, red:
        if interrumpir_tras is not None:
            try:
                cortar = orquestacion.abrir_avance(cfg, "m5", interrumpir_tras=interrumpir_tras)
                orquestacion.correr_m5(cfg, avance=cortar, procesos=procesos)
            except orquestacion.InterrupcionSimulada:
                cortada = True
            vivos_corte = ceguera.procesos_hijos_vivos()
        avance = orquestacion.abrir_avance(cfg, "m5")
        r = orquestacion.correr_m5(cfg, avance=avance, procesos=procesos)
    carpeta = r["carpeta"]
    inventario = json.loads((carpeta / salidas.SHA256_JSON).read_text(encoding="utf-8"))["archivos"]
    _M5[clave] = {"tmp": tmp, "rutas": rutas, "cfg": cfg, "r": r, "carpeta": carpeta, "inventario": inventario,
                  "accesos": list(registro.accesos), "red": list(red.intentos), "cortada": cortada,
                  "saltadas": list(avance.saltadas), "segundos": time.time() - t0, "vivos_corte": vivos_corte}
    return _M5[clave]


class _FabricaFalsa:
    """``Cfg.fabrica_m6`` de las pruebas: en vez de la fábrica de producción v2 (no escrita), una fábrica de A26 que
    predice 10 en «completo» y 15 en «cambio» de 2015-2019 si su TF debe fallar (Δ = 2,5 > 1 % de 10). La primera
    vez, además, arma la fábrica real de A26 (``base(predecir)``) y la llama en dos días de enero de 2020 con un
    ``predecir`` falso, para comprobar que orquestacion la ata bien (operador, meses, datos, escenarios)."""

    def __init__(self, resultados: dict):
        self.resultados = resultados
        self.llamadas: list = []
        self.columnas: dict = {}
        self.celdas: set = set()

    def __call__(self, pol, var, base):
        self.llamadas.append((pol, var))
        if not self.columnas:
            def predecir(modelo, variante, tabla, celdas, dias):
                self.columnas[variante] = list(tabla.columns)
                return np.zeros((len(dias), len(celdas)))
            d0 = int((np.datetime64("2020-01-10") - np.datetime64("2000-01-01")).astype(np.int64))
            real = base(predecir)
            muestra = [int(c) for c in _mundo_celdas()[:2]]
            for v in ("I", "D"):
                P = real(None, v, "completo", np.array(muestra), np.array([d0, d0 + 1]))
                assert P.shape == (2, len(muestra))

        def fabrica(modelo, variante, escenario, celdas, dias):
            self.celdas.add(tuple(int(x) for x in celdas))
            P = np.full((len(dias), len(celdas)), 10.0)
            return P * 1.5 if (modelo["resultado"] == "falla" and escenario == "cambio") else P
        return fabrica, {"contaminante": pol, "variante": var, "resultado": self.resultados[pol][var]}


def _mundo_celdas() -> list:
    return sorted(int(c) for c in pd.read_parquet(_mundo().rutas.grilla / "celdas.parquet")["celda"])


def _correr_m6(caso: str, variante: str = "base", procesos: int = 1, por_fase: dict | None = None) -> dict:
    """Una corrida de M6 sobre una copia de la corrida de M5 (1 proceso), con la comparación de v2 y las TF de
    contaminantes del caso de ``sintetico.tablas_m6``; con ``por_fase``, también con ``Cfg.procesos_por_fase``,
    anotando los procesos de cada llamada a ``orquestacion.repartir`` (ORQ-45)."""
    clave = (caso, variante, procesos) if por_fase is None else (caso, variante, procesos,
                                                                 json.dumps(por_fase, sort_keys=True))
    if clave in _M6:
        return _M6[clave]
    m = _mundo()
    tmp, rutas = _copiar(_correr_m5(1, variante=variante)["tmp"].name)
    d6 = S.tablas_m6(caso)
    _escribir_parquet(orquestacion.ruta_de_alias(rutas, _COMPARACION_M6), d6["comparacion"])
    fabrica = _FabricaFalsa(d6["tf_contaminantes"])
    extra = {} if por_fase is None else {"procesos_por_fase": por_fase}
    cfg = m.cfg_m6(rutas, fabrica_m6=fabrica, procesos=procesos, **extra)
    registro, red = _guardas()
    llamadas: list = []
    with _repartir_anotado(llamadas) if por_fase is not None else contextlib.nullcontext(), registro, red:
        r = orquestacion.correr_m6(cfg, avance=orquestacion.abrir_avance(cfg, "m6"))
    carpeta = r["carpeta"]
    inventario = json.loads((carpeta / salidas.SHA256_JSON).read_text(encoding="utf-8"))["archivos"]
    _M6[clave] = {"tmp": tmp, "rutas": rutas, "cfg": cfg, "r": r, "carpeta": carpeta, "inventario": inventario,
                  "accesos": list(registro.accesos), "red": list(red.intentos), "d6": d6, "fabrica": fabrica,
                  "llamadas": llamadas}
    return _M6[clave]


# ---------------------------------------------------------------------------
# M5 y M6: los mismos productos, a mano con producto, salud y ambiental
# ---------------------------------------------------------------------------
def _hiper_de(uso: str, cand: str) -> dict:
    """Los hiperparámetros fabricados de (T, Td) de un candidato (los mismos en cada uso, ``_hiper_fabricados``)."""
    return _hiper_fabricados(uso, "T_Td")[cand]


def _leer_meses(c: dict, meses) -> list:
    m = _mundo()
    return [fondo_era5l.leer_mes(orquestacion.ruta_de_alias(c["rutas"], m.meses[x])) for x in meses]


def _validos_y_z(c: dict):
    z = pd.read_parquet(entorno.carpeta_salida(c["rutas"], "m2a") / "estaticas/z_e5l.parquet")
    return sorted(int(p) for p in z.loc[z["valido"].to_numpy(bool), "pixel_id"]), z


def _datos_de(c: dict, *, c_est: bool = False):
    """La DatosCompetencia de producción, releída de M2a y de la corrida (la misma función que M3-4)."""
    return orquestacion._produccion(c["cfg"], entorno.carpeta_salida(c["rutas"], "m5", _ETIQUETA), "corrida",
                                    c_est=c_est)["datos"]


def _salud_a_mano(c: dict, anio: int, ganador: dict, hiper: dict, *, entrenamiento=None, datos=None,
                  uso: str = "agudo") -> pd.DataFrame:
    """La tabla civil de un año con ``producto.producto_mes`` y ``salud`` (§7.2, punto 1): las celdas con cod_comuna > 0
    y z_poblada finita, los pesos de su año, los meses del año y el enero siguiente, todas las celdas en un lote."""
    from meteo_combinada import producto, salud
    m, rutas = _mundo(), c["rutas"]
    celdas = pd.read_parquet(rutas.grilla / "celdas.parquet")
    est = pd.read_parquet(entorno.carpeta_salida(rutas, "m2a") / "estaticas/celdas.parquet")
    t = celdas[["celda", "lat", "lon", "cod_comuna"]].merge(est[["celda", "z_poblada"]], on="celda")
    t = t[(t["cod_comuna"] > 0) & np.isfinite(t["z_poblada"])].sort_values("celda")
    pesos = pd.read_parquet(rutas.pesos / "poblacion_celda_anio.parquet")
    pc = salud.pesos_comuna(anio, t[["celda", "cod_comuna"]], pesos)
    sub = t.set_index("celda").loc[pc.celdas]
    validos, z = _validos_y_z(c)
    op = fondo_era5l.operador(sub["lat"].to_numpy(), sub["lon"].to_numpy(), sub["z_poblada"].to_numpy(), m.cat, validos,
                              z, m.U, ids=pc.celdas)
    puntos = {"ids": pc.celdas, "lat": sub["lat"].to_numpy(), "lon": sub["lon"].to_numpy(),
              "z": sub["z_poblada"].to_numpy(np.float64)}
    siguiente = f"{anio + 1}01"
    claves = sorted(x for x in m.meses if int(x[:4]) == anio) + ([siguiente] if siguiente in m.meses else [])
    meses = _leer_meses(c, claves)
    h = fondo_era5l.horas_de(meses)
    pedidos = salud.dias_del_anio(h, anio)
    enlaces = pd.read_parquet(rutas.grilla / "enlaces_productos.parquet")
    pl = salud.pesos_lluvia(anio, celdas[["celda", "cod_comuna"]], enlaces, pesos)
    lluvia = salud.lluvia_comunal(h, np.concatenate([x.datos["tp"] for x in meses]), meses[0].pixel_id, pl, "civil",
                                  dias=pedidos)
    acc = salud.AcumuladorMeteo(pc, h, ("civil",), dias=pedidos)
    datos = datos or _datos_de(c, c_est=uso == "cronico")
    est_p = est.set_index("celda").loc[pc.celdas].reset_index()[list(tipos.ESQUEMA_ESTATICAS_CELDA_C)]
    clima = pd.read_parquet(entorno.carpeta_salida(rutas, "m2a") / "insumos/clima_estado.parquet")
    partes = {k: [] for k in ("T", "Td", "HR")}
    for mes in meses:
        campos, _ = producto.producto_mes(mes, op, puntos, ganador, hiper, datos, umbrales=m.U, uso=uso,
                                          entrenamiento=entrenamiento, estaticos=est_p, clima_estado=clima)
        for k in partes:
            partes[k].append(campos[k])
    acc.agregar({k: np.concatenate(v) for k, v in partes.items()}, pc.celdas)
    return acc.tabla("civil", lluvia)


def _comparar_salud(caso: unittest.TestCase, carpeta: Path, nombre: str, esperada: pd.DataFrame) -> None:
    """La tabla diaria escrita es la de a mano, valor a valor, y sus metadatos (año, año y huella de los pesos, SAL-6)
    son los ``attrs`` de la de a mano."""
    from meteo_combinada import salud
    leida = pd.read_parquet(carpeta / nombre)
    caso.assertEqual(leida.attrs["metadatos"], salud.metadatos_tabla(esperada), nombre)
    copia = esperada.copy()
    leida.attrs, copia.attrs = {}, {}
    pd.testing.assert_frame_equal(leida, copia, check_exact=True)


def _tabla(carpeta: Path, nombre: str) -> pd.DataFrame:
    t = pd.read_parquet(carpeta / nombre)
    t.attrs = {}
    return t


# ---------------------------------------------------------------------------
# Reparto (ORQ-10)
# ---------------------------------------------------------------------------
class PruebasOrquestacion(unittest.TestCase):
    def test_repartir_conserva_el_orden(self):
        """Resultados en el orden de las unidades, con 1, 2 y 8 procesos, y con contexto."""
        unidades = list(range(23))
        esperado = [x * x for x in unidades]
        for procesos in (1, 2, 8):
            with self.subTest(procesos=procesos):
                self.assertEqual(orquestacion.repartir(unidades, _cuadrado, procesos), esperado)
        self.assertEqual(orquestacion.repartir([1, 2, 3], _con_contexto, 2, contexto={"suma": 10}),
                         [(1, 11), (2, 12), (3, 13)])
        self.assertEqual(orquestacion.repartir([], _cuadrado, 8), [])

    def test_trabajadores_en_un_grupo_propio_hilos_en_1_y_sin_vivos(self):
        """§8 y S10: los trabajadores van en un grupo de procesos propio (distinto del de este proceso), con los tres
        hilos en «1» y sin bytecode; al terminar no queda ninguno vivo, ni con ``grupos=``."""
        r = orquestacion.repartir(list(range(8)), _grupo_e_hilos, 4)
        pgids = {x["pgid"] for x in r}
        self.assertEqual(len(pgids), 1)
        pgid = pgids.pop()
        self.assertNotEqual(pgid, os.getpgid(0))
        self.assertIn(pgid, {x["pid"] for x in r})                         # el primero creó el grupo
        self.assertEqual(len({x["pid"] for x in r}), 4)
        for x in r:
            self.assertGreater(x["nice"], os.nice(0))                       # §8: «nice» (H18)
            self.assertEqual(x["variables"], dict.fromkeys(entorno.VARIABLES_HILOS, "1"))
            self.assertTrue(set(x["hilos"]) <= {1})
            self.assertTrue(x["bytecode"])
        self.assertEqual(ceguera.procesos_hijos_vivos(grupos=[pgid]), [])
        self.assertEqual(ceguera.procesos_hijos_vivos(), [])

    def test_error_en_una_unidad_detiene_sin_dejar_vivos(self):
        """Una unidad que falla en un trabajador detiene el reparto (con la traza) y el grupo se cierra."""
        with self.assertRaises(orquestacion.ErrorTrabajador) as e:
            orquestacion.repartir(list(range(12)), _falla_en_tres, 3)
        self.assertIn("unidad mala", str(e.exception))
        self.assertEqual(ceguera.procesos_hijos_vivos(), [])

    def test_corte_en_al_terminar_cierra_el_grupo(self):
        """``al_terminar`` recibe los resultados en orden en este proceso; si corta (S9), el grupo se mata y se
        espera."""
        vistos = []

        def al_terminar(i, r):
            vistos.append(i)
            if i == 2:
                raise orquestacion.InterrupcionSimulada("corte")
            return r

        with self.assertRaises(orquestacion.InterrupcionSimulada):
            orquestacion.repartir(list(range(10)), _dormir, 4, al_terminar=al_terminar)
        self.assertEqual(vistos, [0, 1, 2])
        self.assertEqual(ceguera.procesos_hijos_vivos(), [])

    def test_error_con_unidades_largas_mata_el_grupo(self):
        """H8 (i): una unidad que falla mientras otras corren largo detiene el reparto enseguida: el grupo se mata y se
        espera, sin esperar a las largas."""
        t0 = time.time()
        with self.assertRaises(orquestacion.ErrorTrabajador):
            orquestacion.repartir(list(range(4)), _larga_o_falla, 3)
        self.assertLess(time.time() - t0, 30)
        self.assertEqual(ceguera.procesos_hijos_vivos(), [])

    def test_sigterm_al_principal_cierra_el_grupo(self):
        """H18: un SIGTERM al proceso principal mientras reparte cierra el grupo de trabajadores (se matan y se esperan)
        y sale como error; después vuelve el manejo anterior de la señal."""
        import signal
        import threading
        previo = signal.getsignal(signal.SIGTERM)

        def disparar():
            time.sleep(2.0)
            if signal.getsignal(signal.SIGTERM) is not previo:            # sólo con el manejo de repartir puesto
                os.kill(os.getpid(), signal.SIGTERM)
        hilo = threading.Thread(target=disparar)
        hilo.start()
        try:
            with self.assertRaises(orquestacion.ErrorOrquestacion):
                orquestacion.repartir(list(range(1, 4)), _larga_o_falla, 3)
        finally:
            hilo.join()
        self.assertIs(signal.getsignal(signal.SIGTERM), previo)
        self.assertEqual(ceguera.procesos_hijos_vivos(), [])

    def test_un_proceso_con_el_mismo_bloqueo(self):
        """H18: con un proceso, las unidades corren aquí con el mismo bloqueo de /Volumes que en un trabajador."""
        with self.assertRaises(PermissionError):
            orquestacion.repartir([1], _lee_volumes, 1)

    def test_trabajador_bloquea_volumes(self):
        """ORQ-10: cada trabajador corre bajo su propio registro en bloqueo sobre /Volumes: la lectura se niega antes
        de llegar al disco y el reparto se detiene."""
        with self.assertRaises(orquestacion.ErrorTrabajador) as e:
            orquestacion.repartir([1, 2], _lee_volumes, 2)
        self.assertIn("PermissionError", str(e.exception))
        self.assertEqual(ceguera.procesos_hijos_vivos(), [])

class PruebasAvanceYCfg(unittest.TestCase):
    def test_avance_compuerta_m5_en_la_carpeta_de_m34(self):
        """ORQ-20: M5 sigue el ``avance.jsonl`` de su M3-4 (misma carpeta, ENT-4) con una línea de compuerta propia;
        sin M3-4, con otra corrida o con otras entradas de M5, se niega; sus unidades se reanudan como las demás."""
        with tempfile.TemporaryDirectory() as tmp:
            rutas = entorno.rutas_sinteticas(tmp)
            carpeta = entorno.carpeta_salida(rutas, "m34", _ETIQUETA)
            with self.assertRaises(orquestacion.ErrorReanudacion):
                orquestacion.Avance(carpeta, corrida=_ETIQUETA, huella="c" * 64, compuerta="m5")
            orquestacion.Avance(carpeta, corrida=_ETIQUETA, huella="b" * 64).iniciar()             # la de M3-4
            a5 = orquestacion.Avance(carpeta, corrida=_ETIQUETA, huella="c" * 64, compuerta="m5")
            sha = salidas.escribir("salud/civil/x.json", {"n": 1}, clase="insumo", raiz=carpeta)
            a5.registrar("anual", "anio-2020", "d" * 64, {"salud/civil/x.json": sha})
            b5 = orquestacion.Avance(carpeta, corrida=_ETIQUETA, huella="c" * 64, compuerta="m5")
            self.assertIsNotNone(b5.hecha("anual", "anio-2020", "d" * 64))
            with self.assertRaises(orquestacion.ErrorReanudacion):
                orquestacion.Avance(carpeta, corrida=_ETIQUETA, huella="e" * 64, compuerta="m5")
            with self.assertRaises(orquestacion.ErrorReanudacion):
                orquestacion.Avance(carpeta, corrida="HUMAN20261028_METEO_COMB_1", huella="c" * 64, compuerta="m5")
            texto = (carpeta / orquestacion.AVANCE).read_text(encoding="utf-8")
            ceguera.vigilar_salida(orquestacion.AVANCE, texto, clase="procedencia")
            lineas = [json.loads(x) for x in texto.splitlines()]
            self.assertEqual([x.get("fase") for x in lineas], [None, orquestacion.FASE_COMPUERTA, "anual"])


    def test_avance_cabecera_unidades_y_otra_corrida(self):
        """ORQ-8: la cabecera ata la carpeta a una corrida; otra huella se niega (una corrida nueva exige errata). Una
        unidad se salta sólo con la misma huella de entrada y sus archivos con su sha256; las líneas son procedencia."""
        with tempfile.TemporaryDirectory() as tmp:
            rutas = entorno.rutas_sinteticas(tmp)
            carpeta = entorno.carpeta_salida(rutas, "m34", _ETIQUETA)
            a = orquestacion.Avance(carpeta, corrida=_ETIQUETA, huella="a" * 64)
            sha = salidas.escribir("qc/resumen_qc.json", {"n": 1}, clase="resumen", raiz=carpeta)
            a.registrar("artefactos", "estacion-330001", "b" * 64, {"qc/resumen_qc.json": sha})
            b = orquestacion.Avance(carpeta, corrida=_ETIQUETA, huella="a" * 64)
            self.assertIsNotNone(b.hecha("artefactos", "estacion-330001", "b" * 64))
            self.assertIsNone(b.hecha("artefactos", "estacion-330001", "c" * 64))
            self.assertIsNone(b.hecha("artefactos", "estacion-330002", "b" * 64))
            with self.assertRaises(orquestacion.ErrorReanudacion):
                orquestacion.Avance(carpeta, corrida=_ETIQUETA, huella="d" * 64)
            texto = (carpeta / orquestacion.AVANCE).read_text(encoding="utf-8")
            ceguera.vigilar_salida(orquestacion.AVANCE, texto, clase="procedencia")
            # un archivo que cambió hace que la unidad se rehaga
            salidas.escribir("qc/resumen_qc.json", {"n": 2}, clase="resumen", raiz=carpeta)
            self.assertIsNone(b.hecha("artefactos", "estacion-330001", "b" * 64))
            # S9: el corte simulado tras n unidades nuevas
            c = orquestacion.Avance(carpeta, corrida=_ETIQUETA, huella="a" * 64, interrumpir_tras=1)
            with self.assertRaises(orquestacion.InterrupcionSimulada):
                c.registrar("artefactos", "estacion-330003", "b" * 64, {"qc/resumen_qc.json": sha})

    def test_avance_linea_truncada_detiene(self):
        """H18: una última línea truncada de ``avance.jsonl`` (un corte duro al escribirla) da ``ErrorReanudacion``."""
        with tempfile.TemporaryDirectory() as tmp:
            rutas = entorno.rutas_sinteticas(tmp)
            carpeta = entorno.carpeta_salida(rutas, "m34", _ETIQUETA)
            orquestacion.Avance(carpeta, corrida=_ETIQUETA, huella="a" * 64).iniciar()
            with open(carpeta / orquestacion.AVANCE, "ab") as f:
                f.write(b'{"fase": "artefactos", "uni')
            with self.assertRaises(orquestacion.ErrorReanudacion):
                orquestacion.Avance(carpeta, corrida=_ETIQUETA, huella="a" * 64)

    def test_avance_no_ata_la_carpeta_hasta_iniciar(self):
        """H7 (ORQ-35): abrir el avance no escribe nada; la cabecera va al iniciar (o al primer registro)."""
        with tempfile.TemporaryDirectory() as tmp:
            rutas = entorno.rutas_sinteticas(tmp)
            carpeta = entorno.carpeta_salida(rutas, "m34", _ETIQUETA)
            orquestacion.Avance(carpeta, corrida=_ETIQUETA, huella="a" * 64)
            self.assertFalse((carpeta / orquestacion.AVANCE).exists())
            orquestacion.Avance(carpeta, corrida=_ETIQUETA, huella="b" * 64).iniciar()      # otra corrida, sin error
            with self.assertRaises(orquestacion.ErrorReanudacion):
                orquestacion.Avance(carpeta, corrida=_ETIQUETA, huella="a" * 64)

    def test_cfg_real_exige_recorte_deriva_y_conjuntos(self):
        """H13: en los modos reales, el recorte y la compuerta de deriva vienen explícitos (y, D59, los procesos por
        fase: ``PruebasProcesosPorFase``), y en M2a los conjuntos; en el sintético rigen los de omisión."""
        U = _umbrales()
        por_fase = {"procesos_por_fase": _POR_FASE}
        with tempfile.TemporaryDirectory() as tmp:
            rutas = entorno.rutas_sinteticas(tmp)
            for modo in (tipos.Modo.APLICAR.value, tipos.Modo.PRODUCIR.value, tipos.Modo.M6.value):
                with self.assertRaisesRegex(orquestacion.ErrorOrquestacion, "recorte"):
                    Cfg(rutas=rutas, umbrales=U, entradas={}, huellas={}, modo=modo, **por_fase)
                Cfg(rutas=rutas, umbrales=U, entradas={}, huellas={}, modo=modo, recorte=False,
                    deriva={"B": False, "AB": False}, **por_fase)
            with self.assertRaisesRegex(orquestacion.ErrorOrquestacion, "conjuntos"):
                Cfg(rutas=rutas, umbrales=U, entradas={}, huellas={}, modo=tipos.Modo.ESTATICOS.value, recorte=False,
                    deriva={"B": False, "AB": False}, **por_fase)
            Cfg(rutas=rutas, umbrales=U, entradas={"conjuntos": {}}, huellas={}, modo=tipos.Modo.ESTATICOS.value,
                recorte=False, deriva={"B": False, "AB": False}, **por_fase)
            sint = Cfg(rutas=rutas, umbrales=U, entradas={}, huellas={})
            self.assertEqual((sint.recorte, dict(sint.deriva), sint.procesos_por_fase),
                             (False, {"B": True, "AB": True}, None))

    def test_huella_de_corrida_lleva_umbrales_codigo_y_funciones(self):
        """H12: la huella de la corrida cambia con la fábrica de v2 o las negativas, y lleva la del código del paquete
        y la de los umbrales."""
        U = _umbrales()
        with tempfile.TemporaryDirectory() as tmp:
            rutas = entorno.rutas_sinteticas(tmp)
            base = Cfg(rutas=rutas, umbrales=U, entradas={}, huellas={}, etiqueta=_ETIQUETA)
            otra = Cfg(rutas=rutas, umbrales=U, entradas={}, huellas={}, etiqueta=_ETIQUETA, fabrica_m6=_cuadrado)
            neg = Cfg(rutas=rutas, umbrales=U, entradas={}, huellas={}, etiqueta=_ETIQUETA, negativas=_cuadrado)
            h = {c: orquestacion.huella_de_corrida(c, "m6") for c in (base, otra, neg)}
            self.assertEqual(len(set(h.values())), 3)
            self.assertEqual(orquestacion.identidad_funcion(_cuadrado)["nombre"], "_cuadrado")
            self.assertRegex(orquestacion.huella_del_codigo(), r"[0-9a-f]{64}")

    def test_avance_parcial_de_un_corte_duro_detiene(self):
        """ORQ-9 (P-SAL-8): un «.part» que quedó de un corte duro detiene la reanudación; no se borra."""
        with tempfile.TemporaryDirectory() as tmp:
            rutas = entorno.rutas_sinteticas(tmp)
            carpeta = entorno.carpeta_salida(rutas, "m34", _ETIQUETA)
            a = orquestacion.Avance(carpeta, corrida=_ETIQUETA, huella="a" * 64)
            parcial = carpeta / "qc" / "estaciones" / "330001.parquet.part"
            parcial.parent.mkdir(parents=True)
            parcial.write_bytes(b"x")
            with self.assertRaises(orquestacion.ErrorReanudacion):
                a.parcial_pendiente(["qc/estaciones/330001.parquet"], "estacion-330001")
            self.assertTrue(parcial.exists())

    def test_cfg_y_lista_cerrada(self):
        """ORQ-1: una corrida real decide los cinco pares; una entrada fuera de la lista cerrada o con otra huella no
        se lee."""
        U = _umbrales()
        with tempfile.TemporaryDirectory() as tmp:
            rutas = entorno.rutas_sinteticas(tmp)
            with self.assertRaises(orquestacion.ErrorOrquestacion):
                Cfg(rutas=rutas, umbrales=U, entradas={}, huellas={}, modo=tipos.Modo.APLICAR.value, pares=_PAR_P)
            self.assertEqual(Cfg(rutas=rutas, umbrales=U, entradas={}, huellas={}).pares, orquestacion.PARES)
            (rutas.grilla / "celdas.parquet").write_bytes(b"datos")
            cfg = Cfg(rutas=rutas, umbrales=U, entradas={"celdas": "GRILLA/celdas.parquet"},
                      huellas={"GRILLA/celdas.parquet": _sha(b"otros")})
            with self.assertRaises(orquestacion.ErrorOrquestacion):
                orquestacion.leer_entrada(cfg, "GRILLA/celdas.parquet")
            with self.assertRaises(orquestacion.ErrorOrquestacion):
                orquestacion.leer_entrada(cfg, "GRILLA/estaticas.parquet")
            ok = Cfg(rutas=rutas, umbrales=U, entradas={}, huellas={"GRILLA/celdas.parquet": _sha(b"datos")})
            self.assertEqual(orquestacion.leer_entrada(ok, "GRILLA/celdas.parquet"), b"datos")


# ---------------------------------------------------------------------------
# M2a
# ---------------------------------------------------------------------------
class PruebasS13Orquestacion(unittest.TestCase):
    def test_s13_m2a_se_detiene_con_geopotencial_corrido(self):
        """§4.1 y S13 (MC-38, ORQ-5): con la grilla del geopotencial corrida un píxel respecto del parquet de altitud,
        M2a se detiene con ``ErrorAlineacion`` antes de leer ningún mes y sin escribir los estáticos ni el registro."""
        m = _mundo()
        tmp, rutas = m.copia(con_m2a=False)
        with tmp:
            S.geopotencial_sintetico(rutas.invariantes, m.cat, _z_terreno(m.cat["latitude"].to_numpy(),
                                                                          m.cat["longitude"].to_numpy()),
                                     corrimiento_filas=1)
            cfg = m.cfg_m2a(rutas)
            registro, red = _guardas()
            meses = ceguera.RegistroAccesos((str(rutas.era5l),))         # H8 (c): ningún mes se abre
            with registro, red, meses:
                with self.assertRaises(fondo_era5l.ErrorAlineacion):
                    orquestacion.correr_m2a(cfg, avance=orquestacion.abrir_avance(cfg, "m2a"))
            self.assertEqual(registro.accesos, [])
            self.assertFalse([a for a in meses.accesos if a[0].endswith(".nc") or a[1].endswith(".nc")], meses.accesos)
            self.assertFalse((orquestacion.carpeta_de(cfg, "m2a") / orquestacion.AVANCE).exists())   # H7
            carpeta = orquestacion.carpeta_de(cfg, "m2a")
            for nombre in ("estaticas/z_e5l.parquet", "estaticas/celdas.parquet", orquestacion.REGISTRO_M2A,
                           salidas.RECIBO):
                self.assertFalse((carpeta / nombre).exists(), nombre)


class PruebasM2a(unittest.TestCase):
    def test_m2a_de_punta_a_punta(self):
        """M2a desde el disco (§2.5 del diseño): estáticos de las estaciones (K1, K3, grupo, bloque y operador),
        celdas con ``z_e5l`` (TIP-22), z_E5L, el fondo en cada estación, las climatologías del estado, el registro
        (resumen, pasa su guarda) y el sello; 0 accesos bajo /Volumes."""
        m = _mundo()
        self.assertEqual(m.accesos_m2a, [])
        carpeta = m.m2a["carpeta"]
        inventario = json.loads((carpeta / salidas.SHA256_JSON).read_text(encoding="utf-8"))["archivos"]
        for nombre in ("estaticas/estaciones.parquet", "estaticas/celdas.parquet", "estaticas/z_e5l.parquet",
                       "insumos/clima_estado.parquet", orquestacion.REGISTRO_M2A, orquestacion.AVANCE,
                       *(f"insumos/puntos_estacion/{c}.parquet" for c in m.codigos)):
            self.assertIn(nombre, inventario)
        est = pd.read_parquet(carpeta / "estaticas/estaciones.parquet")
        tipos.validar_esquema(est, tipos.ESQUEMA_ESTACIONES_MC, nombre="estaciones")
        infos = orquestacion.infos_de_tabla(est)
        self.assertEqual(sorted(infos), m.codigos)
        for c, i in infos.items():
            self.assertTrue(i.k3_pasa and not i.excluida and not i.sin_fondo, c)
            self.assertIsNotNone(i.celda)
            self.assertTrue(tipos.PATRON_BLOQUE.fullmatch(i.bloque), i.bloque)
            self.assertAlmostEqual(i.w0 + i.w1 + i.w2 + i.w3, 1.0, places=12)
        self.assertGreaterEqual(len({i.bloque for i in infos.values()}), 2)
        celdas = pd.read_parquet(carpeta / "estaticas/celdas.parquet")
        tipos.validar_esquema(celdas, tipos.ESQUEMA_ESTATICAS_CELDA_C, nombre="celdas")
        self.assertTrue(np.isfinite(celdas[tipos.COLUMNA_Z_E5L].to_numpy()).all())
        # H8 (d): z_e5l = Σ w_i z_E5L,i del operador de la celda con z = z_media (ORQ-7), a mano
        z_pix = pd.read_parquet(carpeta / "estaticas/z_e5l.parquet")
        validos = z_pix.loc[z_pix["valido"].to_numpy(bool), "pixel_id"].to_numpy(np.int64)
        grilla = pd.read_parquet(m.rutas.grilla / "celdas.parquet").set_index("celda").loc[celdas["celda"]]
        op = fondo_era5l.operador(grilla["lat"].to_numpy(), grilla["lon"].to_numpy(), celdas["z_media"].to_numpy(),
                                  m.cat, validos, z_pix, m.U, ids=celdas["celda"].to_numpy(np.int64))
        z_de = dict(zip(z_pix["pixel_id"].to_numpy(np.int64), z_pix["z_e5l"].to_numpy(np.float64)))
        a_mano = [sum(float(op.w[i, k]) * z_de[int(op.pix[i, k])] for k in range(op.pix.shape[1]) if op.pix[i, k] >= 0)
                  for i in range(len(celdas))]
        np.testing.assert_array_equal(celdas[tipos.COLUMNA_Z_E5L].to_numpy(np.float64), np.array(a_mano))
        z = pd.read_parquet(carpeta / "estaticas/z_e5l.parquet")
        self.assertEqual(set(z["caso"].astype(str)), {"geopotencial"})
        F = pd.read_parquet(carpeta / f"insumos/puntos_estacion/{m.codigos[0]}.parquet")
        tipos.validar_esquema(F, tipos.ESQUEMA_PUNTOS_E5L, nombre="puntos")
        self.assertEqual(len(F), sum(len(_horas_de_mes(x)) for x in m.meses))
        reg = json.loads((carpeta / orquestacion.REGISTRO_M2A).read_text(encoding="utf-8"))
        ceguera.vigilar_salida(orquestacion.REGISTRO_M2A, reg, clase="resumen")
        self.assertEqual(reg["pasadas"], 1)
        pesos = pd.read_parquet(m.rutas.pesos / "poblacion_celda_anio.parquet")              # H14, a mano
        self.assertEqual(reg["celdas"]["con_poblacion"], int(pesos.loc[pesos["w_ghs"] > 0, "celda"].nunique()))
        self.assertEqual(reg["celdas"]["con_poblacion_sin_vecino_valido"], 0)
        self.assertEqual(reg["pixeles"]["validos"], len(m.cat))
        self.assertEqual(reg["estaciones"]["estaciones"], len(m.codigos))
        recibo = json.loads((carpeta / salidas.RECIBO).read_text(encoding="utf-8"))
        self.assertEqual(recibo["huellas"][entorno.alias(carpeta / salidas.SHA256_JSON, m.rutas)],
                         _sha((carpeta / salidas.SHA256_JSON).read_bytes()))

    def test_m2a_interrupcion_y_reanudacion_identicas(self):
        """S9 en M2a: cortada tras su primera unidad y reanudada, da los mismos bytes que la corrida de una vez, y la
        unidad hecha se salta."""
        m = _mundo()
        tmp, rutas = m.copia(con_m2a=False)
        with tmp:
            cfg = m.cfg_m2a(rutas)
            registro, red = _guardas()
            with registro, red:
                with self.assertRaises(orquestacion.InterrupcionSimulada):
                    orquestacion.correr_m2a(cfg, avance=orquestacion.abrir_avance(cfg, "m2a", interrumpir_tras=1))
                avance = orquestacion.abrir_avance(cfg, "m2a")
                r = orquestacion.correr_m2a(cfg, avance=avance)
            self.assertEqual(registro.accesos, [])
            self.assertEqual(avance.saltadas, ["pasada"])
            una = json.loads((m.m2a["carpeta"] / salidas.SHA256_JSON).read_text(encoding="utf-8"))["archivos"]
            otra = json.loads((r["carpeta"] / salidas.SHA256_JSON).read_text(encoding="utf-8"))["archivos"]
            self.assertEqual(_sin_avance(otra), _sin_avance(una))


# ---------------------------------------------------------------------------
# M3-4 y S9
# ---------------------------------------------------------------------------
class PruebasM34(unittest.TestCase):
    def test_m34_de_punta_a_punta_hasta_la_decision_y_el_sello(self):
        """M3-4 desde el disco: políticas de lectura, paso 1 por artefacto con el código fijado, envoltorio, K4 y
        alarmas, residuos, selección y predicción en P1 y P2, métricas, TF y finitud, RR06 y SINCA, la decisión
        (``decision.json`` con huellas) y el sello; toda salida por ``salidas`` con su clase; 0 accesos, sin red ni
        procesos vivos."""
        c = _correr_m34(1)
        self.assertEqual((c["accesos"], c["red"]), ([], []))
        self.assertEqual(ceguera.procesos_hijos_vivos(), [])
        inv, carpeta = c["inventario"], c["carpeta"]
        m = _mundo()
        for nombre in (salidas.DECISION, salidas.POLITICA, "qc/resumen_qc.json", "qc/no_normalizables.csv",
                       "validacion/puntajes.parquet", "validacion/bandas.parquet", "validacion/soporte.parquet",
                       "validacion/descriptivos.parquet", "validacion/rr06.json", "validacion/replica_n.json",
                       "validacion/_interno/evaluaciones.parquet", "tendencias/resumen_tf.parquet",
                       "producto/tramos_homogeneos.parquet", "producto/clima_a.parquet", orquestacion.REGISTRO_M34,
                       orquestacion.AVANCE, *(f"qc/estaciones/{x}.parquet" for x in m.codigos),
                       *(f"producto/residuos/{x}.parquet" for x in m.codigos)):
            self.assertIn(nombre, inv)
        for nombre in inv:                                   # cada salida tiene la clase que fija su ruta
            self.assertIsNotNone(salidas.clase_de_salida(nombre) or ceguera.clase_de_ruta(nombre), nombre)
        dec = json.loads((carpeta / salidas.DECISION).read_text(encoding="utf-8"))
        ceguera.vigilar_salida(salidas.DECISION, dec, clase="metrica")
        self.assertEqual(len(dec["decisiones"]), 1)
        d = dec["decisiones"][0]
        self.assertEqual((d["uso"], d["grupo"]), _PAR_P[0])
        self.assertIn(d["ganador"], d["e0"])
        for cand, por_variable in d["hiperparametros"].items():           # ORQ-22: la forma de AMB-7
            self.assertEqual(set(por_variable), {"p"})
            orquestacion._theta_de_json(cand, por_variable["p"], f"ambiental/p/{cand}")
        self.assertTrue(dec["huellas"])
        self.assertIn(entorno.alias(carpeta / "validacion/puntajes.parquet", c["rutas"]), dec["huellas"])
        reg = json.loads((carpeta / orquestacion.REGISTRO_M34).read_text(encoding="utf-8"))
        ceguera.vigilar_salida(orquestacion.REGISTRO_M34, reg, clase="resumen")
        self.assertEqual(reg["estaciones"]["con_tabla"], len(m.codigos))
        self.assertEqual(reg["sinca"]["estado"], "leida_sin_producto")
        qc = json.loads((carpeta / "qc/resumen_qc.json").read_text(encoding="utf-8"))
        self.assertFalse(qc["detener"])
        ancha = pd.read_parquet(carpeta / f"qc/estaciones/{m.codigos[0]}.parquet")
        tipos.validar_esquema(ancha, tipos.ESQUEMA_QC_ESTACION, nombre="tabla ancha")
        meta = ancha.attrs["metadatos"]
        self.assertEqual(sorted(meta), ["artefactos", "den", "efectivas", "num", "sin_prueba"])
        self.assertNotIn('"D":', json.dumps(meta))                                      # §0.4.6: nunca D de K4
        self.assertTrue(ancha["valido_p"].all())
        pol = salidas.POLITICA
        politicas_ = json.loads((carpeta / pol).read_text(encoding="utf-8"))
        self.assertEqual(sorted({p["station_code"] for p in politicas_}), m.codigos)
        avance = (carpeta / orquestacion.AVANCE).read_text(encoding="utf-8")
        ceguera.vigilar_salida(orquestacion.AVANCE, avance, clase="procedencia")
        self.assertEqual(len(avance.splitlines()), 1 + len(m.codigos))
        recibo = json.loads((carpeta / salidas.RECIBO).read_text(encoding="utf-8"))
        self.assertEqual(recibo["entorno"]["procesos"], 1)


    def test_m34_se_detiene_por_alarma_y_sella(self):
        """§2.7 y §10 («las alarmas de §2.7 son su única detención»): con un artefacto «no normalizable» (DD 990) de
        los 30, Q3 salta; M3-4 escribe ``qc/resumen_qc.json`` (con «detener»), la política efectiva y el registro,
        sella y se detiene con ``DetencionPorAlarma``, sin ``decision.json`` ni procesos vivos."""
        m = _mundo()
        tmp, rutas = m.copia()
        with tmp:
            primero = S.manifiestos_de(rutas.dmc)[m.codigos[0]][0]

            def dd_990(payload):
                fila = payload["rows"][0]
                fila["fields"]["wind_direction_instant"].update(raw="990", value=990.0)
                fila["raw_cells"]["wind_direction_instant"]["text"] = "990"
                return payload

            S.alterar_artefacto(primero, dd_990)
            regla = [{"tramo": "1.1", "valid_from": f"{_DESDE}T00:00:00", "valid_to": f"{_HASTA}T23:00:00",
                      "minutos": _UTC_MENOS_4, "veredicto": "F(-4)"}]
            S.politica_reloj_sintetica(rutas.ap.parent, S.artefactos_de_descarga(rutas.dmc),
                                       {c: regla for c in m.codigos})
            cfg = m.cfg_m34(rutas, procesos=8)
            registro, red = _guardas()
            with registro, red:
                with self.assertRaises(orquestacion.DetencionPorAlarma) as e:
                    orquestacion.correr_m34(cfg, avance=orquestacion.abrir_avance(cfg, "m34"), procesos=8)
            self.assertEqual((registro.accesos, red.intentos), ([], []))
            self.assertEqual(ceguera.procesos_hijos_vivos(), [])
            carpeta = e.exception.resultado["carpeta"]
            qc = json.loads((carpeta / "qc/resumen_qc.json").read_text(encoding="utf-8"))
            self.assertTrue(qc["detener"])
            self.assertIn("Q3", {a["alarma"] for a in qc["alarmas"]})
            reg = json.loads((carpeta / orquestacion.REGISTRO_M34).read_text(encoding="utf-8"))
            self.assertTrue(reg["detenida"])
            self.assertFalse((carpeta / salidas.DECISION).exists())
            self.assertTrue((carpeta / salidas.RECIBO).is_file() and (carpeta / salidas.POLITICA).is_file())
            nn = pd.read_csv(carpeta / "qc/no_normalizables.csv")
            self.assertEqual(len(nn), 1)


class PruebasS9(unittest.TestCase):
    def test_s09_mismas_huellas_con_1_2_y_8_procesos(self):
        """S9 (MC-37, ORQ-10): con los hilos en 1, las mismas entradas dan los mismos bytes en cada salida con 1, 2 y 8
        procesos (todo ``sha256.json`` salvo ``avance.jsonl``), y la misma decisión."""
        uno = _correr_m34(1)
        for procesos in (2, 8):
            with self.subTest(procesos=procesos):
                otra = _correr_m34(procesos)
                self.assertEqual((otra["accesos"], otra["red"]), ([], []))
                self.assertEqual(_sin_avance(otra["inventario"]), _sin_avance(uno["inventario"]))
                self.assertEqual(otra["r"]["decision"], uno["r"]["decision"])
        self.assertEqual(ceguera.procesos_hijos_vivos(), [])

    def test_s09_interrupcion_y_reanudacion_identicas(self):
        """S9: una interrupción simulada entre unidades (tras 3 estaciones, con 2 procesos) y su reanudación dan
        salidas idénticas, bit a bit, a la corrida de una vez; las unidades hechas se saltan y no quedan procesos."""
        uno = _correr_m34(1)
        cortada = _correr_m34(2, interrumpir_tras=3)
        self.assertTrue(cortada["cortada"])
        self.assertEqual(cortada["vivos_corte"], [])
        self.assertEqual(len(cortada["saltadas"]), 3)
        self.assertEqual((cortada["accesos"], cortada["red"]), ([], []))
        self.assertEqual(_sin_avance(cortada["inventario"]), _sin_avance(uno["inventario"]))
        self.assertEqual(cortada["r"]["decision"], uno["r"]["decision"])


# ---------------------------------------------------------------------------
# Memoria de la selección (ola 6: ORQ-42, ORQ-43): los mismos bits que la ola 5
# ---------------------------------------------------------------------------
def _unidad_pliegue_ola5(unidad, ctx) -> dict:
    """Copia literal de ``orquestacion._unidad_pliegue`` de la ola 5 (sha256 7406e5de… de ``orquestacion.py``): las 30
    predicciones a la vez y el fondo entero de todas las estaciones en ``ctx``. Sólo para comparar bit a bit."""
    from meteo_combinada import candidatos, producto, validacion
    from meteo_combinada.tipos import Candidato, Grupo, Uso
    O = orquestacion
    U, datos, infos = ctx["U"], ctx["datos"], ctx["infos"]
    externo = unidad["pliegue"]
    hiper = O._seleccionar_todo(unidad["selecciones"], externo, ctx)
    pred: dict = {}
    for (cand, var, uso), h in hiper.items():
        for pv in O._PRODUCTO_SEL[var]:
            pred[(cand, pv, uso)] = candidatos.predecir_prueba(cand, pv, uso, h, externo, datos, umbrales=U)
    filas, descriptivas, anuales, finitud = [], [], {}, {}
    periodos = {k: [] for k in ctx["periodos"]}
    for uso, grupo in ctx["pares"]:
        uso_sel = Uso.AMBIENTAL.value if uso == Uso.AMBIENTAL.value else Uso.AGUDO.value
        metricas = list(validacion.METRICAS[(Uso(uso), Grupo(grupo))])
        pvs = sorted({pv for v in metricas for pv in O._DEPENDE[v]})
        for c in externo.prueba:
            info = infos[c]
            ancha = ctx["anchas"][c]
            hq = ancha["h"].to_numpy(np.int64)
            Fh = fondo_era5l.en_horas(ctx["F"][c], hq) if ctx["F"].get(c) is not None else {
                k: np.full(hq.size, np.nan) for k in fondo_era5l.CAMPOS_F}
            cands = [x for x in validacion.CANDIDATOS_USO[Uso(uso)]
                     if not (tipos.fuera_de_la_grilla(info) and x in (Candidato.C.value, Candidato.C_EST.value))]
            campos, soporte = {}, {}
            for cand in cands:
                u_h = uso if cand == Candidato.C_EST.value else uso_sel
                R, sop = {}, {}
                for pv in ("T", "Td", "u", "v", "p"):
                    clave = (cand, pv, u_h)
                    if pv not in pvs or clave not in pred:
                        R[f"R_{pv}"], sop[pv] = np.zeros(hq.size), np.ones(hq.size, dtype=bool)
                        continue
                    g = pred[clave]
                    g = g[(g["codigo"] == c).to_numpy(dtype=bool)]
                    pos = np.searchsorted(g["h"].to_numpy(np.int64), hq)
                    esta = (pos < len(g))
                    pos_c = np.clip(pos, 0, max(len(g) - 1, 0))
                    if len(g):
                        esta &= g["h"].to_numpy(np.int64)[pos_c] == hq
                    r = np.full(hq.size, np.nan)
                    s = np.zeros(hq.size, dtype=bool)
                    r[esta] = g["correccion"].to_numpy(np.float64)[pos_c[esta]]
                    s[esta] = g["soporte"].to_numpy(bool)[pos_c[esta]]
                    R[f"R_{pv}"], sop[pv] = r, s
                campos[cand] = producto.campos(Fh, R)
                soporte[cand] = sop
                if not tipos.fuera_de_la_grilla(info):
                    col = {k: np.asarray(x, dtype=np.float64)[:, None] for k, x in campos[cand].items()}
                    con = producto.hay_fondo({k: x[:, None] for k, x in Fh.items()}, grupo=grupo)
                    finitud[(uso, grupo, cand)] = finitud.get((uso, grupo, cand), producto.ConteoFinito(0, 0)) + \
                        producto.conteo_finito(col, con, grupo=grupo)
            for v in metricas:
                pred_v, obs_v, sop_v = {}, None, {}
                for cand in cands:
                    pred_v[cand], obs_v = O._serie(v, campos[cand], ancha)
                    sop_v[cand] = np.logical_and.reduce([soporte[cand][pv] for pv in O._DEPENDE[v]])
                fin = [np.isfinite(p) if not isinstance(p, tuple) else np.isfinite(p[0]) & np.isfinite(p[1])
                       for p in pred_v.values()]
                obs_fin = np.isfinite(obs_v) if not isinstance(obs_v, tuple) else (np.isfinite(obs_v[0])
                                                                                  & np.isfinite(obs_v[1]))
                comun = obs_fin & np.logical_and.reduce(fin)
                for nombre_p, mascara in (("", np.ones(hq.size, dtype=bool)), *ctx["periodos"].items()):
                    if nombre_p:
                        mascara = O._mascara_periodo(hq, mascara)
                    for cand in cands:
                        m_c = comun & mascara
                        p_c = O._con_mascara(pred_v[cand], m_c)
                        met = validacion.evaluacion(hq, p_c, obs_v, uso=uso, variable=v, umbrales=U)
                        if met is None:
                            continue
                        frac = (float(1 - sop_v[cand][m_c].mean()) if cand in validacion.NUCLEO and m_c.any()
                                else math.nan)
                        fila = validacion.fila_evaluacion(met, codigo=c, particion=externo.particion.value,
                                                          pliegue=externo.id, candidato=cand, uso=uso, variable=v,
                                                          frac_sin_soporte=frac)
                        if nombre_p:
                            periodos[nombre_p].append(fila)
                            continue
                        filas.append(fila)
                        descriptivas += validacion.filas_descriptivas(met, codigo=c, particion=externo.particion.value,
                                                                      candidato=cand, uso=uso, variable=v)
                        if met.get("anuales") is not None:
                            anuales[(c, externo.particion.value, cand)] = met["anuales"]
    return {"pliegue": externo.id, "hiper": hiper, "filas": filas, "descriptivas": descriptivas, "anuales": anuales,
            "periodos": periodos, "finitud": finitud}


def _bits(x) -> str:
    return hashlib.sha256(pickle.dumps(x, protocol=4)).hexdigest()


_SELECCION: dict = {}


def _seleccion_de_m34() -> dict:
    """La receta de la ``DatosCompetencia`` de la corrida de M3-4 de un proceso (con C_est, para los cinco pares) y el
    contexto de la selección (``correr_m34``, paso 7) con los π del objetivo parejos por banda."""
    if _SELECCION:
        return _SELECCION
    c = _correr_m34(1)
    carpeta, inv, cfg = c["carpeta"], c["inventario"], c["cfg"]
    m2a = orquestacion._leer_m2a(cfg)
    cods = sorted(n[len("producto/residuos/"):-len(".parquet")] for n in inv if n.startswith("producto/residuos/"))
    U = cfg.U
    infos = orquestacion.infos_de_tabla(orquestacion._parquet(m2a["leer"]("estaticas/estaciones.parquet")))
    entran = {x: infos[x] for x in cods}
    grupos = {x: entran[x].grupo for x in entran}
    pliegues = tuple(particiones.pliegues_p1(grupos, U) + particiones.pliegues_p2(entran, grupos, U))
    receta = orquestacion._receta_datos(lambda n: orquestacion._ref_de_archivo(carpeta, n, inv[n]["sha256"]),
                                        m2a["ref"], cods, c_est=True, pliegues=pliegues)
    anchas = {x: pd.read_parquet(carpeta / f"qc/estaciones/{x}.parquet") for x in cods}
    horas = orquestacion._horas_validas_total(anchas, entran)
    n_bandas = len(tuple(U.a("BANDAS_KM"))) + 1
    pi = np.full(n_bandas, 1.0 / n_bandas)
    d1, h1, d2, h2 = constantes.valor("ESTRATO_PERIODOS")
    ctx = {"U": U, "receta": receta, "horas": horas, "recorte": False, "pares": orquestacion.PARES,
           "pi_sel": {u: {k: pi for k in horas} for u in (x.value for x in tipos.Uso)},
           "anchas": {x: orquestacion._ref_de_archivo(carpeta, f"qc/estaciones/{x}.parquet",
                                                     inv[f"qc/estaciones/{x}.parquet"]["sha256"]) for x in cods},
           "periodos": {f"{d1}-{h1}": (d1, h1), f"{d2}-{h2}": (d2, h2)}}
    _SELECCION.update({"receta": receta, "pliegues": pliegues, "ctx": ctx, "U": U, "cods": cods})
    return _SELECCION


def _unidades_de_prueba(pliegues, U) -> list:
    """Un pliegue de P1, uno de P2 con estaciones de prueba y la producción (sus selecciones, como ``correr_m34``)."""
    p1 = [p for p in pliegues if p.particion is tipos.Particion.P1 and p.prueba]
    p2 = [p for p in pliegues if p.particion is tipos.Particion.P2 and p.prueba]
    sel = orquestacion._selecciones(orquestacion.PARES)
    todas = tuple(sorted({x for p in pliegues for x in (*p.prueba, *p.entrenamiento)}))
    produccion = tipos.Pliegue("produccion", tipos.Particion.P2, prueba=(), entrenamiento=todas)
    return [{"pliegue": p1[0], "selecciones": sel}, {"pliegue": p2[0], "selecciones": sel},
            {"pliegue": produccion, "selecciones": sel, "produccion": True}]


class PruebasMemoriaSeleccion(unittest.TestCase):
    """ORQ-42 (PED-10) y ORQ-43: el fondo de los días de selección y las predicciones reducidas dan los mismos bits."""

    def setUp(self):
        orquestacion._DATOS.clear()

    def tearDown(self):
        orquestacion._DATOS.clear()

    def test_variantes_de_la_receta(self):
        """ORQ-42: la variante de la selección guarda, de cada estación, las filas del fondo en los días de selección
        (mód SEL_MOD, o SEL_MOD_RECORTE con el recorte), con sus valores y tipos y un índice de 0 a n − 1; las filas de
        C, los residuos y el clima del estado son los de la completa bit a bit, armada de cero o derivada de la
        completa; la ligera de cero es la derivada."""
        s = _seleccion_de_m34()
        receta, U = s["receta"], s["U"]
        completa, _ = orquestacion._datos_de_receta(receta, U)
        bits_completa = {k: _bits(getattr(completa, k)) for k in ("residuos", "filas_c", "clima_estado", "estaticos",
                                                                   "estaciones", "pliegues")}
        for recorte in (False, True):
            with self.subTest(recorte=recorte):
                derivada, _ = orquestacion._datos_de_receta(orquestacion._para_seleccion(receta, recorte), U)
                orquestacion._DATOS.clear()
                de_cero, _ = orquestacion._datos_de_receta(orquestacion._para_seleccion(receta, recorte), U)
                for datos in (derivada, de_cero):
                    self.assertEqual({k: _bits(getattr(datos, k)) for k in bits_completa}, bits_completa)
                    self.assertEqual(sorted(datos.puntos_e5l), sorted(completa.puntos_e5l))
                    for cod, F in completa.puntos_e5l.items():
                        dias = particiones.dias_de_seleccion(F["h"].to_numpy(), U, recorte=recorte)
                        self.assertTrue(0 < dias.sum() < len(F))
                        esperado = F[dias].reset_index(drop=True)
                        pd.testing.assert_frame_equal(datos.puntos_e5l[cod].reset_index(drop=True), esperado,
                                                      check_exact=True)
                        tipos.validar_esquema(datos.puntos_e5l[cod], tipos.ESQUEMA_PUNTOS_E5L, nombre=cod)
                        self.assertIsInstance(datos.puntos_e5l[cod].index, pd.RangeIndex)
                orquestacion._DATOS.clear()
                orquestacion._datos_de_receta(receta, U)
        ligera_derivada, _ = orquestacion._datos_de_receta(orquestacion._solo_celdas(receta), U)
        orquestacion._DATOS.clear()
        ligera, _ = orquestacion._datos_de_receta(orquestacion._solo_celdas(receta), U)
        for datos in (ligera_derivada, ligera):
            self.assertEqual((dict(datos.puntos_e5l), dict(datos.clima_estado)), ({}, {}))
            self.assertEqual(_bits(datos.filas_c), bits_completa["filas_c"])

    def test_un_solo_fondo_entero_en_memoria(self):
        """ORQ-42: al armar la variante de la selección (y la ligera) el fondo entero de cada estación se lee de a una,
        y la anterior ya se soltó cuando se lee la siguiente."""
        import weakref
        s = _seleccion_de_m34()
        original = orquestacion._fondo_de_prueba
        vivos, maximo = [], [0]

        def vigilado(receta):
            leer = original(receta)

            def fondo(c):
                F = leer(c)
                vivos.append(weakref.ref(F))
                maximo[0] = max(maximo[0], sum(r() is not None for r in vivos))
                return F
            return fondo
        for receta in (orquestacion._para_seleccion(s["receta"], False), orquestacion._solo_celdas(s["receta"])):
            vivos.clear()
            maximo[0] = 0
            orquestacion._DATOS.clear()
            orquestacion._fondo_de_prueba = vigilado
            try:
                datos, _ = orquestacion._datos_de_receta(receta, s["U"])
            finally:
                orquestacion._fondo_de_prueba = original
            self.assertEqual(len(vivos), len(s["cods"]))
            self.assertEqual(maximo[0], 1)
            self.assertEqual(sum(r() is not None for r in vivos), 0)

    def test_pliegues_y_produccion_bit_a_bit_con_la_ola_5(self):
        """ORQ-42 y ORQ-43: en un pliegue de P1, uno de P2 y la producción, con los cinco pares, la unidad de la
        selección por la receta de la selección (con y sin recorte) da los mismos bytes que la de la ola 5 con el fondo
        entero de todas las estaciones."""
        s = _seleccion_de_m34()
        for recorte in (False, True):
            ctx = {**s["ctx"], "recorte": recorte}
            for unidad in _unidades_de_prueba(s["pliegues"], s["U"]):
                with self.subTest(recorte=recorte, pliegue=unidad["pliegue"].id):
                    viejo = orquestacion._materializar(ctx)
                    esperado = (orquestacion._unidad_produccion(unidad, viejo) if unidad.get("produccion")
                                else _unidad_pliegue_ola5(unidad, viejo))
                    nuevo = orquestacion._unidad_seleccion(
                        unidad, {**ctx, "receta": orquestacion._para_seleccion(ctx["receta"], recorte)})
                    self.assertEqual(_bits(nuevo), _bits(esperado))
                    if not unidad.get("produccion"):
                        self.assertTrue(esperado["filas"])

    def test_predicciones_se_sueltan_y_los_errores_salen_como_antes(self):
        """ORQ-43: las 30 predicciones se calculan en el orden de siempre, nunca hay más de 8 a la vez (las de un par),
        el error de una evaluación sale después de todas las predicciones (el del primer par que falla) y el de una
        predicción, en su lugar, antes que el de una evaluación. ORQ-42: predicen con la misma ``DatosCompetencia`` del
        proceso (la caché de candidatos sigue tibia), con el fondo entero de las estaciones de prueba mientras dura la
        unidad, y al salir (también por un error) vuelve el de los días de selección."""
        s = _seleccion_de_m34()
        ctx = {**s["ctx"], "receta": orquestacion._para_seleccion(s["receta"], False)}
        unidad = _unidades_de_prueba(s["pliegues"], s["U"])[0]
        orden = [(cand, pv, uso) for cand, var, uso in unidad["selecciones"] for pv in orquestacion._PRODUCTO_SEL[var]]
        self.assertEqual(len(orden), 30)
        del_proceso, _ = orquestacion._datos_de_receta(ctx["receta"], s["U"])
        prueba = unidad["pliegue"].prueba
        recortado = {c: del_proceso.puntos_e5l[c] for c in prueba}
        entero = {c: len(orquestacion._fondo_de_prueba(ctx["receta"])(c)) for c in prueba}
        self.assertTrue(all(entero[c] > len(recortado[c]) for c in prueba))
        predecir, evaluar = candidatos.predecir_prueba, orquestacion._evaluar_par
        llamadas, guardadas = [], []

        def predecir_contando(cand, pv, uso, h, externo, datos, **k):
            llamadas.append((cand, pv, uso))
            self.assertIs(datos, del_proceso)
            self.assertEqual({c: len(datos.puntos_e5l[c]) for c in prueba}, entero)
            if len(llamadas) == fallar_en[0]:
                raise RuntimeError("predicción")
            return predecir(cand, pv, uso, h, externo, datos, **k)

        def evaluar_vigilando(uso, grupo, externo, ctx_, F, reducidas, claves, U):
            guardadas.append(len(reducidas))
            if (uso, grupo) in fallan:
                raise ValueError(f"evaluación {uso}/{grupo}")
            return evaluar(uso, grupo, externo, ctx_, F, reducidas, claves, U)
        candidatos.predecir_prueba, orquestacion._evaluar_par = predecir_contando, evaluar_vigilando
        try:
            fallar_en, fallan = [0], set()
            orquestacion._unidad_seleccion(unidad, ctx)
            self.assertTrue(all(del_proceso.puntos_e5l[c] is recortado[c] for c in prueba))
            self.assertEqual(llamadas, orden)
            self.assertEqual(len(guardadas), len(orquestacion.PARES))
            self.assertLessEqual(max(guardadas), 8)
            llamadas.clear()
            fallan = {orquestacion.PARES[3], orquestacion.PARES[0]}
            with self.assertRaisesRegex(ValueError, "evaluación ambiental/T_Td"):
                orquestacion._unidad_seleccion(unidad, ctx)
            self.assertEqual(llamadas, orden)
            llamadas.clear()
            fallar_en = [20]
            with self.assertRaisesRegex(RuntimeError, "predicción"):
                orquestacion._unidad_seleccion(unidad, ctx)
            self.assertEqual(llamadas, orden[:20])
            for c in prueba:
                self.assertIs(del_proceso.puntos_e5l[c], recortado[c])
        finally:
            candidatos.predecir_prueba, orquestacion._evaluar_par = predecir, evaluar

    def test_principal_lee_las_tablas_anchas_de_a_una(self):
        """ORQ-44: RR06 recibe las tablas anchas enteras desde el disco, de a una y sin guardarlas (las mismas tablas
        que tenía el principal, con sus metadatos fuera); los residuos y la evaluación, sólo sus columnas, y las horas
        válidas sólo las suyas; las horas válidas sumadas estación por estación son las de todas juntas."""
        c = _correr_m34(1)
        carpeta, inv = c["carpeta"], c["inventario"]
        cods = _seleccion_de_m34()["cods"]
        nombre = "qc/estaciones/{}.parquet".format
        refs = {x: orquestacion._ref_de_archivo(carpeta, nombre(x), inv[nombre(x)]["sha256"]) for x in reversed(cods)}
        tablas = orquestacion._TablasAnchas(refs)
        self.assertEqual((list(tablas), len(tablas)), (sorted(cods), len(cods)))
        enteras = {}
        for x in cods:
            entera = pd.read_parquet(carpeta / nombre(x))
            entera.attrs = {"esquema": tipos.ESQUEMA_QC_ESTACION.version}
            enteras[x] = entera
            una, otra = tablas[x], tablas[x]
            self.assertIsNot(una, otra)
            pd.testing.assert_frame_equal(una, entera, check_exact=True)
            self.assertEqual(una.attrs, entera.attrs)
            tipos.validar_esquema(una, tipos.ESQUEMA_QC_ESTACION, nombre=x)
            for columnas, datos in ((orquestacion._COLUMNAS_ANCHAS, refs[x]),
                                    (orquestacion._COLUMNAS_VALIDAS, (carpeta / nombre(x)).read_bytes())):
                parte = orquestacion._ancha_de(datos, columnas)
                self.assertEqual(tuple(parte.columns), tuple(columnas))
                pd.testing.assert_frame_equal(parte, entera[list(columnas)], check_exact=True)
        entran = dict.fromkeys(cods[1:])                              # una estación que no entra no cuenta
        anios = range(constantes.valor("PI_POB_PERIODO")[0], constantes.valor("PI_POB_PERIODO")[1] + 1)
        juntas = (orquestacion._horas_validas_anio(enteras, entran, anios),
                  orquestacion._horas_validas_total(enteras, entran))
        horas_anio = {k: {a: {} for a in anios} for k in juntas[1]}
        horas = {k: {} for k in juntas[1]}
        for x in sorted(entran):
            orquestacion._horas_de_una(horas_anio, horas, x, orquestacion._ancha_de(refs[x]), anios)
        self.assertEqual(json.dumps(horas_anio), json.dumps(juntas[0]))
        self.assertEqual(json.dumps(horas), json.dumps(juntas[1]))
        self.assertTrue(any(horas["T"].values()))

    def test_reducir_prediccion_son_las_filas_de_cada_estacion(self):
        """ORQ-43: por estación de prueba, las filas de ``g["codigo"] == código`` en su orden (también desordenadas o
        sin filas), h en int64, y las horas iguales de otra predicción son el mismo arreglo."""
        g = pd.DataFrame({"codigo": ["b", "a", "b", "a", "b"], "h": [3, 1, 5, 2, 7],
                          "correccion": [0.5, -1.0, np.nan, 2.0, 1.25], "soporte": [True, False, True, True, False]}
                         ).astype(dict(candidatos.COLUMNAS_PREDICCION))
        horas = {}
        r = orquestacion._reducir_prediccion(g, ("a", "b", "c"), horas)
        for c in ("a", "b", "c"):
            m = (g["codigo"] == c).to_numpy(dtype=bool)
            esperado = (g["h"].to_numpy(np.int64)[m], g["correccion"].to_numpy(np.float64)[m],
                        g["soporte"].to_numpy(bool)[m])
            for x, y in zip(r[c], esperado):
                self.assertEqual((x.dtype, x.tobytes()), (y.dtype, y.tobytes()))
        otra = orquestacion._reducir_prediccion(g.assign(correccion=1.0), ("a", "b", "c"), horas)
        self.assertIs(otra["b"][0], r["b"][0])
        distinta = orquestacion._reducir_prediccion(g.assign(h=g["h"] + 1), ("a", "b", "c"), horas)
        self.assertEqual(distinta["b"][0].tolist(), [4, 6, 8])


# ---------------------------------------------------------------------------
# Negativas, registros y entradas defectuosas (H2, H4, H5, H7, H8 b)
# ---------------------------------------------------------------------------
def _cambiar_un_byte(ruta: Path) -> bytes:
    datos = ruta.read_bytes()
    ruta.write_bytes(datos[:-1] + bytes([datos[-1] ^ 1]))
    return datos


class PruebasNegativas(unittest.TestCase):
    def test_negativas_comparan_huellas_y_no_atan_la_carpeta(self):
        """H8 (b), H7 (ORQ-35): con un byte cambiado en una entrada de la lista cerrada, cada compuerta se niega antes
        de escribir nada (ni la cabecera de ``avance.jsonl``, ni en M5 la línea de compuerta); con la entrada
        corregida, la misma carpeta corre (M5 de punta a punta)."""
        m = _mundo()
        casos = (("m2a", m.copia(con_m2a=False), "ERA5L/" + Path(m.meses["202001"]).name),
                 ("m34", m.copia(), "GRILLA/enlaces_productos.parquet"))
        for compuerta, (tmp, rutas), alias_ in casos:
            with self.subTest(compuerta=compuerta), tmp:
                cfg = m.cfg_m2a(rutas) if compuerta == "m2a" else m.cfg_m34(rutas)
                _cambiar_un_byte(orquestacion.ruta_de_alias(rutas, alias_))
                correr = orquestacion.correr_m2a if compuerta == "m2a" else orquestacion.correr_m34
                kw = {} if compuerta == "m2a" else {"procesos": 1}
                with self.assertRaises(orquestacion.ErrorOrquestacion) as e:
                    correr(cfg, avance=orquestacion.abrir_avance(cfg, compuerta), **kw)
                self.assertIn("se niega", str(e.exception))
                self.assertFalse((orquestacion.carpeta_de(cfg, compuerta) / orquestacion.AVANCE).exists())
        tmp, rutas = _copiar(_plantilla_m5()["tmp"].name)
        with tmp:
            cfg = m.cfg_m5(rutas)
            ruta = orquestacion.ruta_de_alias(rutas, "PESOS/poblacion_celda_anio.parquet")
            original = _cambiar_un_byte(ruta)
            avance = orquestacion.carpeta_de(cfg, "m5") / orquestacion.AVANCE
            antes = avance.read_bytes()
            with self.assertRaises(orquestacion.ErrorOrquestacion):
                orquestacion.correr_m5(cfg, avance=orquestacion.abrir_avance(cfg, "m5"), procesos=1)
            self.assertEqual(avance.read_bytes(), antes)                    # sin línea de compuerta
            ruta.write_bytes(original)
            r = orquestacion.correr_m5(cfg, avance=orquestacion.abrir_avance(cfg, "m5"), procesos=1)
            self.assertEqual(r["fases"], list(orquestacion.FASES_M5))
        tmp, rutas = _copiar(_correr_m5(1)["tmp"].name)
        with tmp:
            _escribir_parquet(orquestacion.ruta_de_alias(rutas, _COMPARACION_M6), S.tablas_m6("rama1_D")["comparacion"])
            cfg = m.cfg_m6(rutas, fabrica_m6=_FabricaFalsa(S.tablas_m6("rama1_D")["tf_contaminantes"]))
            _cambiar_un_byte(orquestacion.ruta_de_alias(rutas, _COMPARACION_M6))
            with self.assertRaises(orquestacion.ErrorOrquestacion):
                orquestacion.correr_m6(cfg, avance=orquestacion.abrir_avance(cfg, "m6"))
            self.assertFalse((orquestacion.carpeta_de(cfg, "m6") / orquestacion.AVANCE).exists())

    def test_m34_se_niega_si_un_mes_cambio_tras_m2a(self):
        """H5 (§10: «alguna huella … del registro de M2a difiere»): si un mes de ERA5-Land cambió después de M2a, M3-4
        se niega aunque la lista cerrada traiga la huella nueva (el registro de M2a cita la vieja); sin el registro
        de M2a en la lista, también."""
        m = _mundo()
        tmp, rutas = m.copia()
        with tmp:
            _cambiar_un_byte(orquestacion.ruta_de_alias(rutas, m.meses["202001"]))
            cfg = m.cfg_m34(rutas)
            with self.assertRaises(orquestacion.ErrorOrquestacion) as e:
                orquestacion.correr_m34(cfg, avance=orquestacion.abrir_avance(cfg, "m34"), procesos=1)
            self.assertIn("registró M2a", str(e.exception))
            huellas = {k: v for k, v in cfg.huellas.items() if not k.endswith(orquestacion.REGISTRO_M2A)}
            sin_registro = Cfg(rutas=rutas, umbrales=m.U, entradas=cfg.entradas, huellas=huellas, pares=_PAR_P,
                               etiqueta=_ETIQUETA)
            with self.assertRaises(orquestacion.ErrorOrquestacion) as e:
                orquestacion.correr_m34(sin_registro, avance=orquestacion.abrir_avance(sin_registro, "m34"), procesos=1)
            self.assertIn("no está en la lista cerrada", str(e.exception))

    def test_m5_se_niega_si_decision_no_es_la_de_la_lista(self):
        """H5: M5 exige ``decision.json`` en la lista cerrada con su huella."""
        m = _mundo()
        tmp, rutas = _copiar(_plantilla_m5()["tmp"].name)
        with tmp:
            cfg = m.cfg_m5(rutas)
            alias_ = next(a for a in cfg.huellas if a.endswith("/" + salidas.DECISION))
            mala = Cfg(rutas=rutas, umbrales=m.U, entradas=cfg.entradas, huellas={**cfg.huellas, alias_: "0" * 64},
                       etiqueta=_ETIQUETA)
            with self.assertRaises(orquestacion.ErrorOrquestacion) as e:
                orquestacion.correr_m5(mala, avance=orquestacion.abrir_avance(mala, "m5"), procesos=1)
            self.assertIn("difiere", str(e.exception))

    def test_m34_artefacto_evaluado_sin_manifiesto_detiene(self):
        """H4: un artefacto de ``artefactos_evaluados`` sin manifiesto detiene M3-4 antes de normalizar (un defecto de
        la entrada, no un «no normalizable»)."""
        m = _mundo()
        tmp, rutas = m.copia()
        with tmp:
            S.manifiestos_de(rutas.dmc)[m.codigos[0]][0].unlink()
            cfg = m.cfg_m34(rutas)
            registro, red = _guardas()
            with registro, red, self.assertRaises(orquestacion.ErrorOrquestacion) as e:
                orquestacion.correr_m34(cfg, avance=orquestacion.abrir_avance(cfg, "m34"), procesos=1)
            self.assertIn("artefactos_evaluados", str(e.exception))
            self.assertFalse((orquestacion.carpeta_de(cfg, "m34") / "qc/estaciones").exists())

    def test_rr06_por_anios_igual_a_un_lote(self):
        """H2 (ORQ-37): RR06 por lotes de un año, con el último día del mes anterior delante (aquí cruza el 1 de enero
        de 2020), da lo mismo que un solo lote con los meses contiguos, y es lo que escribe M3-4."""
        from meteo_combinada import qc_dmc_meteo as Q
        m, c = _mundo(), _correr_m34(1)
        carpeta = c["carpeta"]
        infos = orquestacion.infos_de_tabla(pd.read_parquet(entorno.carpeta_salida(c["rutas"], "m2a")
                                                            / "estaticas/estaciones.parquet"))
        anchas = {}
        for x in m.codigos:
            t = pd.read_parquet(carpeta / f"qc/estaciones/{x}.parquet")
            t.attrs = {"esquema": tipos.ESQUEMA_QC_ESTACION.version}
            anchas[x] = t
        meses = orquestacion._meses_ordenados(c["cfg"])
        por_anios = orquestacion._rr06(c["cfg"], anchas, infos, meses)
        enlaces = pd.read_parquet(c["rutas"].grilla / "enlaces_productos.parquet")
        sumas = None
        for lote in (["200001"], ["201307"], ["201912", "202001", "202002"], ["202507"]):
            serie = [fondo_era5l.leer_mes(orquestacion.ruta_de_alias(c["rutas"], m.meses[x])) for x in lote]
            sumas = Q.sumas_lluvia_rr06(anchas, infos, enlaces, fondo_era5l.incrementos_tp(serie),
                                        h=fondo_era5l.horas_de(serie), pixel_ids=np.asarray(serie[0].pixel_id),
                                        previas=sumas)
        por_hora = orquestacion._sumas_rr06(c["cfg"], anchas, infos, meses)
        self.assertEqual(sorted(por_hora), sorted(sumas))
        cruzan = 0
        for x in sorted(sumas):                                      # las sumas de 6 h de cada hora, bit a bit
            np.testing.assert_array_equal(por_hora[x][0], sumas[x][0])
            np.testing.assert_array_equal(por_hora[x][1], sumas[x][1])
            h = anchas[x]["h"].to_numpy(np.int64)
            enero = (h >= _horas_de_mes("202001")[0]) & (h < _horas_de_mes("202001")[0] + 6)
            cruzan += int(np.isfinite(sumas[x][0][enero]).sum())
        self.assertGreater(cruzan, 0)                                # hay ventanas que cruzan el 1 de enero
        un_lote = orquestacion._numeros_python(Q.validar_rr06(anchas, sumas, infos, m.U))
        self.assertEqual(json.dumps(por_anios, sort_keys=True), json.dumps(un_lote, sort_keys=True))
        escrito = json.loads((carpeta / "validacion/rr06.json").read_text(encoding="utf-8"))
        self.assertEqual(json.dumps(escrito, sort_keys=True), json.dumps(un_lote, sort_keys=True))

    def test_decision_de_m34_en_los_cinco_pares_la_lee_ambiental(self):
        """H8 (a), ORQ-22: los hiperparámetros de producción de los cinco pares, por ``_hiper_de_par`` y
        ``decision.decision_json`` (lo que escribe M3-4), los leen ``ambiental.ganador_ambiental``, ``_ganador_y_hiper``
        y ``ambiental.operador_grilla`` con los mismos θ (con «uv» como clave, no se leerían)."""
        from meteo_combinada import ambiental, decision
        m = _mundo()
        theta = {"A": _H_A, "B": _H_B, "AB": (_H_A, _H_PHI), "C": _ALFA, "C_est": 100.0}
        hiper_prod = {(c, v, u): theta[c] for c, v, u in orquestacion._selecciones(orquestacion.PARES)}
        hiper_json = {f"{u}/{g}": orquestacion._hiper_de_par(u, g, hiper_prod) for u, g in orquestacion.PARES}
        tablas = _plantilla_m5()["tablas"]
        decisiones = [decision.decidir_combinacion(u, g, _entradas_de(u, g, t), umbrales=m.U)
                      for (u, g), t in tablas.items()]
        dec = decision.decision_json(decisiones, hiper_json, {"GRILLA/celdas.parquet": "0" * 64})
        datos = entorno.json_canonico(dec)
        contenido = json.loads(datos)
        ganador, hiper = ambiental.ganador_ambiental(contenido)
        self.assertEqual(ganador, {"T_Td": "AB", "u_v": "A", "p": "B"})
        self.assertEqual(hiper, {"T": theta["AB"], "Td": theta["AB"], "u": _H_A, "v": _H_A, "p": _H_B})
        self.assertEqual(orquestacion._ganador_y_hiper(contenido, "agudo"),
                         ("AB", {"T": theta["AB"], "Td": theta["AB"]}))
        self.assertEqual(orquestacion._ganador_y_hiper(contenido, "cronico"), ("C_est", {"T": 100.0, "Td": 100.0}))
        c5 = _correr_m5(1)
        p = orquestacion._produccion(c5["cfg"], c5["carpeta"], "M5", c_est=False)
        op = ambiental.operador_grilla(datos, celdas=p["celdas_g"], estaciones=p["datos"].estaciones, catalogo=m.cat,
                                       z_celdas=p["estaticos_m2a"], validos=p["validos"], z_pix=p["z_tabla"],
                                       umbrales=m.U)
        self.assertEqual(dict(op.ganador), ganador)
        self.assertEqual(dict(op.hiper), hiper)

    def test_m34_recorte_pliegue_de_produccion_y_deriva(self):
        """H8 (f): con el recorte (mód 23) y B fuera por la compuerta de deriva, cada selección recibe ``recorte`` y
        la de producción va en un pliegue P2 sin prueba con todas las estaciones (P61, ORQ-13); B queda fuera de E0
        por «deriva» en ``decision.json``."""
        from unittest import mock
        from meteo_combinada import candidatos
        m = _mundo()
        tmp, rutas = m.copia()
        with tmp:
            cfg = m.cfg_m34(rutas, recorte=True, deriva={"B": False, "AB": True})
            llamadas = []
            original = candidatos.seleccionar

            def espia(cand, var, uso, externo, datos, U, **kw):
                llamadas.append((externo.id, externo.particion.value, tuple(externo.prueba),
                                 tuple(externo.entrenamiento), kw.get("recorte")))
                return original(cand, var, uso, externo, datos, U, **kw)
            with mock.patch.object(candidatos, "seleccionar", espia):
                r = orquestacion.correr_m34(cfg, avance=orquestacion.abrir_avance(cfg, "m34"), procesos=1)
            self.assertTrue(llamadas and all(x[4] is True for x in llamadas))
            prod = [x for x in llamadas if x[0] == "produccion"]
            self.assertTrue(prod)
            self.assertEqual({(x[1], x[2], x[3]) for x in prod}, {("P2", (), tuple(m.codigos))})
            d = r["decision"]["decisiones"][0]
            self.assertNotIn("B", d["e0"])
            self.assertIn("deriva", d["motivos"]["B"])


# ---------------------------------------------------------------------------
# M5 (segunda fase)
# ---------------------------------------------------------------------------
_ANIOS = (2000, 2013, 2019, 2020, 2025)                 # los años de los meses de la red mínima
_CARPETAS_M5 = ("salud/civil", "salud/utc4", "salud/regional", "salud/representatividad", "salud/cronico")


class PruebasM5(unittest.TestCase):
    def test_m5_archivos_esquemas_clases_y_sello(self):
        """M5 desde el disco (§2.5 del diseño; §8): el 0,1° de cada mes, la salud de cada año en las cinco carpetas,
        lo crónico anual, la lista de excluidas, el operador y las laterales I y D por contaminante; toda salida con
        la clase de su ruta (insumo), cada tabla con su esquema; la carpeta sellada otra vez (el recibo de M3-4
        archivado, SLD-10) y publicable (SLD-11); 0 accesos bajo /Volumes, sin red ni procesos vivos."""
        c = _correr_m5(1)
        self.assertEqual((c["accesos"], c["red"]), ([], []))
        self.assertEqual(ceguera.procesos_hijos_vivos(), [])
        m, r, inv, carpeta = _mundo(), c["r"], c["inventario"], c["carpeta"]
        self.assertEqual(r["fases"], list(orquestacion.FASES_M5))
        self.assertEqual(sorted({int(x[:4]) for x in m.meses}), list(_ANIOS))
        esperados = [orquestacion.OPERADOR_GRILLA, orquestacion.EXCLUIDAS, orquestacion.CRONICO_ANUAL,
                     *(f"producto_01deg/meteo_{x}.nc" for x in m.meses),
                     *(f"{d}/meteo_{a}.parquet" for d in _CARPETAS_M5 for a in _ANIOS),
                     *(f"ambiental/lateral_{pol}_{v}.parquet" for pol in tipos.CONTAMINANTES_M6 for v in ("I", "D"))]
        for nombre in esperados:
            self.assertIn(nombre, inv)
            self.assertEqual(ceguera.clase_de_ruta(nombre), "insumo", nombre)
        for nombre in inv:
            self.assertIsNotNone(salidas.clase_de_salida(nombre) or ceguera.clase_de_ruta(nombre), nombre)
        self.assertEqual(set(r["archivos"]) - set(inv), set())
        self.assertEqual(salidas.fallas_de_cierre(carpeta), [])
        recibo = json.loads((carpeta / salidas.RECIBO).read_text(encoding="utf-8"))
        self.assertEqual(recibo["huellas"][entorno.alias(carpeta / salidas.SHA256_JSON, c["rutas"])],
                         _sha((carpeta / salidas.SHA256_JSON).read_bytes()))
        self.assertIn(entorno.alias(carpeta / "recibos/recibo_2.json", c["rutas"]), recibo["huellas"])
        self.assertEqual(salidas.fallas_de_sello_archivado(carpeta, 2), [])     # PED-6: el sello de M3-4 verifica
        avance = (carpeta / orquestacion.AVANCE).read_text(encoding="utf-8")
        ceguera.vigilar_salida(orquestacion.AVANCE, avance, clase="procedencia")
        lineas = [json.loads(x) for x in avance.splitlines()]
        self.assertEqual(sum(1 for x in lineas if x.get("fase") == orquestacion.FASE_COMPUERTA), 1)
        filas = None
        for d in _CARPETAS_M5:
            for a in _ANIOS:
                t = pd.read_parquet(carpeta / f"{d}/meteo_{a}.parquet")
                tipos.validar_esquema(t, tipos.ESQUEMA_METEO_DIARIA, nombre=d)
                self.assertEqual(t.attrs["metadatos"]["anio"], a)
                if a == 2020:
                    clave = t[["cod_comuna", "dia"]].reset_index(drop=True)
                    if filas is None:
                        filas = clave
                    pd.testing.assert_frame_equal(clave, filas)            # SAL-5: las mismas filas
            self.assertTrue(np.isfinite(pd.read_parquet(carpeta / f"{d}/meteo_2020.parquet")["temp_media"]).any(), d)
        cro = pd.read_parquet(carpeta / orquestacion.CRONICO_ANUAL)
        tipos.validar_esquema(cro, tipos.ESQUEMA_CRONICO, nombre="crónico")
        self.assertEqual(sorted(set(cro["anio"].astype(int))), list(_ANIOS))
        self.assertEqual(len(cro), len(_ANIOS) * len(m.codigos))           # una comuna por estación
        for pol in tipos.CONTAMINANTES_M6:
            for v, esquema in (("I", tipos.ESQUEMA_LATERAL_I), ("D", tipos.ESQUEMA_LATERAL_D)):
                t = pd.read_parquet(carpeta / f"ambiental/lateral_{pol}_{v}.parquet")
                tipos.validar_esquema(t, esquema, nombre=f"lateral {pol} {v}")
                from meteo_combinada import ambiental
                self.assertEqual(tuple(sorted(t.attrs["metadatos"])), tuple(sorted(ambiental.METADATOS_LATERAL)))
        self.assertEqual(r["ganadores"], {"ambiental": {"T_Td": "AB", "u_v": "A", "p": "B"}, "agudo": "AB",
                                          "cronico": "C_est"})

    def test_m5_01deg_coincide_con_producto_a_mano(self):
        """MC-08, ORQ-25: el NetCDF de 0,1° de cada mes es, byte a byte, el de ``producto.producto_mes`` y
        ``producto.mes_01deg`` con el ganador y los hiperparámetros ambientales en los píxeles válidos (z = z_E5L) y
        las huellas de la decisión, de z_E5L, del catálogo y del mes."""
        from meteo_combinada import producto
        c = _correr_m5(1)
        m, carpeta, rutas = _mundo(), c["carpeta"], c["rutas"]
        validos, z = _validos_y_z(c)
        op = fondo_era5l.operador_pixeles(np.array(validos), m.cat, validos, z)
        cat = m.cat.set_index("pixel_id").loc[validos]
        puntos = {"ids": np.array(validos), "lat": cat["latitude"].to_numpy(), "lon": cat["longitude"].to_numpy(),
                  "z": np.asarray(op.z, dtype=np.float64)}
        ganador = {"T_Td": "AB", "u_v": "A", "p": "B"}
        hiper = {"T": _THETA["AB"], "Td": _THETA["AB"], "u": _H_A, "v": _H_A, "p": _H_B}
        datos = _datos_de(c)
        m2a = entorno.carpeta_salida(rutas, "m2a")
        z_e5l = m2a / "estaticas/z_e5l.parquet"
        base = {entorno.alias(carpeta / salidas.DECISION, rutas): _sha((carpeta / salidas.DECISION).read_bytes()),
                entorno.alias(z_e5l, rutas): _sha(z_e5l.read_bytes()),
                "ERA5L/catalogo_pixeles.parquet": _sha((rutas.era5l / "catalogo_pixeles.parquet").read_bytes())}
        for x in ("202001", "202507"):
            mes = _leer_meses(c, [x])[0]
            campos, _ = producto.producto_mes(mes, op, puntos, ganador, hiper, datos, umbrales=m.U, uso="ambiental")
            nc = producto.mes_01deg(campos, np.array(validos), np.asarray(mes.tiempos, np.int64), m.U,
                                    {**base, m.meses[x]: mes.sha256}, uso="ambiental", ganador=ganador)
            self.assertEqual(_sha(nc), c["inventario"][f"producto_01deg/meteo_{x}.nc"]["sha256"], x)

    def test_m5_salud_civil_coincide_con_salud_a_mano(self):
        """§7.2, punto 1 (SAL-5 a SAL-8): la tabla civil de 2020 (enero y febrero) y la de 2019 (diciembre y el enero
        siguiente) son las de ``producto.producto_mes`` con el ganador agudo (AB) y ``salud`` (pesos del año, lluvia
        como ``meteo_civil_v3``, días civiles), en un solo lote de celdas; sin excluidas, la de representatividad es
        la misma."""
        c = _correr_m5(1)
        datos = _datos_de(c)
        for anio in (2019, 2020):
            esperada = _salud_a_mano(c, anio, {"T_Td": "AB"}, _hiper_de("agudo", "AB"), datos=datos)
            _comparar_salud(self, c["carpeta"], f"salud/civil/meteo_{anio}.parquet", esperada)
            pd.testing.assert_frame_equal(_tabla(c["carpeta"], f"salud/representatividad/meteo_{anio}.parquet"),
                                          _tabla(c["carpeta"], f"salud/civil/meteo_{anio}.parquet"), check_exact=True)
        self.assertEqual(c["r"]["excluidas"], [])

    def test_m5_cronico_coincide_con_salud_a_mano(self):
        """§7.3 (SAL-10): los días civiles de lo crónico son los del ganador crónico (C_est, con el clima del estado y
        los estáticos de las celdas) y sus hiperparámetros, y ``temperatura_anual`` es ``salud.cronico_anual`` de ellos
        con los pesos de cada año."""
        from meteo_combinada import salud
        c = _correr_m5(1)
        datos = _datos_de(c, c_est=True)
        esperada = _salud_a_mano(c, 2020, {"T_Td": "C_est"}, _hiper_de("cronico", "C_est"), datos=datos, uso="cronico")
        _comparar_salud(self, c["carpeta"], "salud/cronico/meteo_2020.parquet", esperada)
        celdas = pd.read_parquet(c["rutas"].grilla / "celdas.parquet")
        est = pd.read_parquet(entorno.carpeta_salida(c["rutas"], "m2a") / "estaticas/celdas.parquet")
        t = celdas[["celda", "cod_comuna"]].merge(est[["celda", "z_poblada"]], on="celda")
        t = t[(t["cod_comuna"] > 0) & np.isfinite(t["z_poblada"])].sort_values("celda")[["celda", "cod_comuna"]]
        pc = salud.pesos_comuna(2020, t, pd.read_parquet(c["rutas"].pesos / "poblacion_celda_anio.parquet"))
        anual = salud.cronico_anual({2020: esperada}, {2020: pc})
        leida = _tabla(c["carpeta"], orquestacion.CRONICO_ANUAL)
        leida = leida[leida["anio"] == 2020].reset_index(drop=True)
        anual.attrs = {}
        pd.testing.assert_frame_equal(leida, anual, check_exact=True)

    def test_m5_laterales_y_operador_coinciden_con_ambiental_a_mano(self):
        """§7.1, ORQ-27, ORQ-28: el operador es el de ``ambiental.operador_grilla`` y cada lateral, armada por partes
        anuales, es bit a bit la de ``ambiental.lateral_monitores`` sobre el panel entero, con los mismos metadatos."""
        from meteo_combinada import ambiental
        c = _correr_m5(1)
        m, carpeta, rutas = _mundo(), c["carpeta"], c["rutas"]
        validos, z = _validos_y_z(c)
        datos = _datos_de(c)
        dec = (carpeta / salidas.DECISION).read_bytes()
        est = pd.read_parquet(entorno.carpeta_salida(rutas, "m2a") / "estaticas/celdas.parquet")
        op = ambiental.operador_grilla(dec, celdas=pd.read_parquet(rutas.grilla / "celdas.parquet"),
                                       estaciones=datos.estaciones, catalogo=m.cat, z_celdas=est, validos=validos,
                                       z_pix=z, umbrales=m.U)
        self.assertEqual(op.sha256, c["inventario"][orquestacion.OPERADOR_GRILLA]["sha256"])
        pliegues = (rutas.datos / "red2" / S.NOMBRE_PLIEGUES_RED2).read_bytes()
        meses = {int(x): mes for x, mes in zip(_MESES_DATOS, _leer_meses(c, _MESES_DATOS))}
        politica = (carpeta / salidas.POLITICA).read_bytes()
        for pol in tipos.CONTAMINANTES_M6:
            ruta_panel = rutas.datos / "red2" / "paneles" / f"panel_{pol}_red2.parquet"
            for var in ("I", "D"):
                tabla, meta = ambiental.lateral_monitores(
                    pol, dec, op, variante=var, panel=ruta_panel.read_bytes(), pliegues=pliegues, meses=meses,
                    datos=datos, umbrales=m.U, politica=politica, h_ultima=m.h_ultima, estaticos=est)
                leida = pd.read_parquet(carpeta / f"ambiental/lateral_{pol}_{var}.parquet")
                self.assertEqual(leida.attrs["metadatos"], meta, (pol, var))
                tabla.attrs, leida.attrs = {}, {}
                pd.testing.assert_frame_equal(leida, tabla, check_exact=True)

    def test_m5_representatividad_con_el_pixel_del_reloj(self):
        """§7.2, punto 6 (MC-52, A27, ORQ-24): la lista de excluidas es la de ``salud.representatividad`` con la T
        válida de cada estación y la t2m del píxel que elige ``fijados.cargar_elegir_pixel``; con la T de una estación
        invertida, ella queda fuera, sólo se guarda la lista, y el producto de representatividad es el agudo rehecho
        sin ella (``entrenamiento``), distinto del civil."""
        from meteo_combinada import salud
        for variante, esperada in (("base", []), ("una_excluida", [_EXCLUIDA])):
            with self.subTest(variante=variante):
                c = _correr_m5(1, variante=variante)
                self.assertEqual((c["accesos"], c["red"]), ([], []))
                m, carpeta = _mundo(), c["carpeta"]
                datos = _datos_de(c)
                validos, _ = _validos_y_z(c)
                pixel = fijados.cargar_elegir_pixel(_AP, _APH, fijados.HUELLAS_CLAUSURA, permitir_cargados=True)
                meses = _leer_meses(c, sorted(m.meses))
                h = np.concatenate([np.asarray(x.tiempos, np.int64) for x in meses])
                obs, serie = {}, {}
                for cod, info in sorted(datos.estaciones.items()):
                    e = pixel.enlazar(info.lat, info.lon, m.cat, set(validos))
                    k = list(meses[0].pixel_id).index(e.pixel_id)
                    serie[cod] = (h, np.concatenate([x.datos["t2m"][:, k] for x in meses]).astype(np.float64))
                    ancha = pd.read_parquet(carpeta / f"qc/estaciones/{cod}.parquet")
                    obs[cod] = {"h": ancha["h"].to_numpy(np.int64), "T": ancha["Ts"].to_numpy(np.float64),
                                "valido": ancha["valido_T"].to_numpy(bool)}
                self.assertEqual(sorted(salud.representatividad(obs, serie, m.U)), esperada)
                lista = json.loads((carpeta / orquestacion.EXCLUIDAS).read_text(encoding="utf-8"))
                self.assertEqual(lista, {"esquema": orquestacion.ESQUEMA_EXCLUIDAS, "excluidas": esperada})
                self.assertEqual(c["r"]["excluidas"], esperada)
                if esperada:
                    restantes = tuple(x for x in sorted(datos.estaciones) if x not in esperada)
                    a_mano = _salud_a_mano(c, 2020, {"T_Td": "AB"}, _hiper_de("agudo", "AB"), entrenamiento=restantes,
                                           datos=datos)
                    _comparar_salud(self, carpeta, "salud/representatividad/meteo_2020.parquet", a_mano)
                    leida = _tabla(carpeta, "salud/representatividad/meteo_2020.parquet")
                    civil = _tabla(carpeta, "salud/civil/meteo_2020.parquet")
                    self.assertFalse(np.allclose(civil["temp_media"], leida["temp_media"], equal_nan=True))


class PruebasReanudacionM5(unittest.TestCase):
    def test_m5_reanudado_con_otros_residuos_rehace_todo(self):
        """H8 (h), ORQ-8: si una salida de M3-4 que M5 lee cambió (un residuo, con la carpeta sellada otra vez), la
        reanudación de M5 rehace toda unidad que depende de lo leído (la lista, el operador y los años; las uniones de
        las laterales se saltan sólo si sus partes salen iguales) y sus productos cambian."""
        m = _mundo()
        uno = _correr_m5(1)
        tmp, rutas = _copiar(uno["tmp"].name)
        with tmp:
            carpeta = entorno.carpeta_salida(rutas, "m5", _ETIQUETA)
            nombre = f"producto/residuos/{m.codigos[0]}.parquet"
            res = pd.read_parquet(carpeta / nombre)
            for col in ("r_T", "rt_T"):                                        # B y AB usan r̃ (rt_T)
                res[col] = (res[col].astype(np.float64) + 0.5).astype(np.float32)
            res.attrs = {"esquema": tipos.ESQUEMA_RESIDUOS.version}
            salidas.escribir(nombre, res, clase="insumo", esquema=tipos.ESQUEMA_RESIDUOS, raiz=carpeta)
            salidas.sellar_corrida(carpeta, {}, orquestacion._entorno_recibo(1), rutas=rutas)
            cfg = m.cfg_m5(rutas)
            avance = orquestacion.abrir_avance(cfg, "m5")
            orquestacion.correr_m5(cfg, avance=avance, procesos=1)
            dependen = [u for u in avance.saltadas if u in ("excluidas", "operador") or u.startswith("anio-")]
            self.assertEqual(dependen, [])                                      # todo lo que lee M3-4 se rehace
            nuevo = json.loads((carpeta / salidas.SHA256_JSON).read_text(encoding="utf-8"))["archivos"]
            civil = "salud/civil/meteo_2020.parquet"
            self.assertNotEqual(nuevo[civil], uno["inventario"][civil])


class PruebasS9M5(unittest.TestCase):
    def test_s09_m5_mismas_huellas_con_1_y_8_procesos(self):
        """S9 en M5 (MC-37, ORQ-10): con los hilos en 1, las mismas entradas dan los mismos bytes en cada salida con 1
        y 8 procesos (todo ``sha256.json`` salvo ``avance.jsonl``)."""
        uno, ocho = _correr_m5(1), _correr_m5(8)
        self.assertEqual((ocho["accesos"], ocho["red"]), ([], []))
        self.assertEqual(_sin_avance(ocho["inventario"]), _sin_avance(uno["inventario"]))
        self.assertEqual(ceguera.procesos_hijos_vivos(), [])

    def test_s09_m5_interrupcion_y_reanudacion_identicas(self):
        """S9 en M5: cortada tras tres unidades (la lista de excluidas, el operador y el primer año) con 2 procesos y
        reanudada, da los mismos bytes que la corrida de una vez; las unidades hechas se saltan."""
        uno, cortada = _correr_m5(1), _correr_m5(2, interrumpir_tras=3)
        self.assertTrue(cortada["cortada"])
        self.assertEqual(cortada["vivos_corte"], [])
        self.assertEqual(cortada["saltadas"], ["excluidas", "operador", f"anio-{_ANIOS[0]}"])
        self.assertEqual((cortada["accesos"], cortada["red"]), ([], []))
        self.assertEqual(_sin_avance(cortada["inventario"]), _sin_avance(uno["inventario"]))


# ---------------------------------------------------------------------------
# Los procesos por fase (D59, A39; ORQ-45)
# ---------------------------------------------------------------------------
class PruebasRecibosEMC3(unittest.TestCase):
    """Regresiones breves, sin _Mundo, textos anclados, datos reales, costo ni S6."""

    def setUp(self):
        registro, red = _guardas()
        self.enterContext(registro)
        self.enterContext(red)
        self.addCleanup(self.assertEqual, registro.accesos, [])
        self.addCleanup(self.assertEqual, red.intentos, [])

    def assertUso(self, uso, unidades, limite, procesos, trabajadores):
        self.assertEqual(uso, {"unidades": unidades, "limite": {"procesos": limite}, "procesos": procesos,
                               "trabajadores_creados": {"procesos": trabajadores}})

    def test_limites_solos_no_son_procesos_observados(self):
        """EMC3-1: un límite no acredita trabajadores ni procesos de ejecución observados."""
        with self.assertRaisesRegex(orquestacion.ErrorOrquestacion, "repartos"):
            orquestacion._entorno_recibo(8, {"fase": 8})

    def test_reparto_0_1_2_y_varias_unidades_con_limite_8(self):
        """Cuenta PIDs de ejecución y creaciones reales, no el límite 8; conserva orden y cierre."""
        for n in (0, 1, 2, 11):
            with self.subTest(unidades=n):
                registro = []
                with patch.object(orquestacion.subprocess, "Popen", wraps=orquestacion.subprocess.Popen) as crear:
                    salida = orquestacion.repartir(range(n), _grupo_e_hilos, 8, registro=registro)
                ejecutores = min(n, 8)
                trabajadores = ejecutores if n > 1 else 0
                self.assertEqual([r["x"] for r in salida], list(range(n)))
                self.assertEqual(len({r["pid"] for r in salida}), ejecutores)
                # La comprobación de cierre también usa Popen para «ps», pero no crea trabajadores.
                creaciones = [c for c in crear.call_args_list if c.args[0][0] == sys.executable]
                self.assertEqual(len(creaciones), trabajadores)
                if n == 1:
                    self.assertEqual(salida[0]["pid"], os.getpid())
                self.assertUso(registro[0], n, 8, ejecutores, trabajadores)
                self.assertEqual(ceguera.procesos_hijos_vivos(), [])

    def test_limite_de_fase_secuencial_y_resumen_de_varios_repartos(self):
        """Los topes siguen intactos; cada llamada secuencial crea 0 hijos; el resumen usa máximo, no suma."""
        with tempfile.TemporaryDirectory(prefix="emc3-limites-") as tmp:
            cfg = Cfg(rutas=entorno.rutas_sinteticas(tmp), umbrales=None, entradas={}, huellas={}, procesos=8,
                      procesos_por_fase=_POR_FASE_CORRIDA)
            limites = orquestacion._procesos_de_fases(cfg, "m34", 8)
            repartos = {f: [] for f in limites}
            for n in (0, 1, 2, 5):
                for fase, limite in limites.items():
                    salida = orquestacion.repartir(range(n), _con_contexto, limite, contexto={"suma": 10},
                                                   al_terminar=lambda i, r: (i, r[1]), registro=repartos[fase])
                    self.assertEqual(salida, [(i, i + 10) for i in range(n)])
            recibo = orquestacion._entorno_recibo(8, limites, repartos=repartos)
            self.assertEqual(recibo["procesos"], 2)
            self.assertEqual(recibo["presupuesto"]["procesos"], 8)
            self.assertEqual(recibo["alcance"], "repartos_de_esta_invocacion")
            for fase, limite in limites.items():
                detalle = recibo["procesos_por_fase"][fase]
                self.assertEqual(detalle["procesos"], limite)
                self.assertEqual(detalle["trabajadores_creados"]["procesos"], 4 if limite == 2 else 0)
                for uso, n in zip(detalle["repartos"], (0, 1, 2, 5)):
                    self.assertUso(uso, n, limite, min(n, limite), min(n, limite) if n > 1 and limite > 1 else 0)
            # El recibo es una instantánea: otra llamada no modifica el detalle ya construido.
            antes = entorno.json_canonico(recibo)
            orquestacion.repartir([0], _cuadrado, 1, registro=repartos["artefactos"])
            self.assertEqual(entorno.json_canonico(recibo), antes)
            salidas.recibo_corrida({"LOCAL/entrada.json": "a" * 64}, recibo)  # CEG-11 sin cambios

    def test_avance_interrumpido_reanudado_y_ya_completo(self):
        """La contabilidad se toma después de saltar unidades: al reanudar quedan 1, 2 y finalmente 0."""
        for total in (3, 4):
            with self.subTest(total=total), tempfile.TemporaryDirectory(prefix="emc3-avance-") as tmp:
                rutas = entorno.rutas_sinteticas(tmp)
                carpeta = entorno.carpeta_salida(rutas, "m34", _ETIQUETA)

                def correr(avance):
                    pendientes = [u for u in range(total) if avance.hecha("artefactos", f"u-{u}", _sha(str(u).encode()))
                                  is None]
                    usos = []

                    def guardar(i, resultado):
                        u = pendientes[i]
                        nombre = f"salud/civil/u-{u}.json"
                        sha = orquestacion._escribir(avance, nombre, {"n": resultado})
                        avance.registrar("artefactos", f"u-{u}", _sha(str(u).encode()), {nombre: sha})
                        return resultado
                    try:
                        orquestacion.repartir(pendientes, _cuadrado, 8, al_terminar=guardar, registro=usos)
                    finally:
                        self.assertEqual(ceguera.procesos_hijos_vivos(), [])
                    return usos

                cortado = orquestacion.Avance(carpeta, corrida=_ETIQUETA, huella="b" * 64, interrumpir_tras=2)
                with self.assertRaises(orquestacion.InterrupcionSimulada):
                    correr(cortado)
                reanudado = orquestacion.Avance(carpeta, corrida=_ETIQUETA, huella="b" * 64)
                n = total - 2
                self.assertUso(correr(reanudado)[0], n, 8, n, 0 if n == 1 else n)
                completo = orquestacion.Avance(carpeta, corrida=_ETIQUETA, huella="b" * 64)
                self.assertUso(correr(completo)[0], 0, 8, 0, 0)
                for u in range(total):
                    self.assertEqual(json.loads((carpeta / f"salud/civil/u-{u}.json").read_bytes()), {"n": u * u})

    def test_m34_recibo_efectivo_y_s9_datos_huellas_cfg_1_2_8(self):
        """Sello M3-4 real sobre dos unidades triviales: mismos datos/registro/hash, distinto entorno de ejecución."""
        inventarios, registros, huellas = [], [], []
        presupuesto = {c: dict.fromkeys(fases, 8) for c, fases in orquestacion.FASES_REPARTO.items()}
        for procesos in (1, 2, 8):
            with self.subTest(procesos=procesos), tempfile.TemporaryDirectory(prefix="emc3-s9-") as tmp:
                rutas = entorno.rutas_sinteticas(tmp)
                cfg = Cfg(rutas=rutas, umbrales=None, entradas={}, huellas={}, etiqueta=_ETIQUETA,
                          procesos=procesos, procesos_por_fase=presupuesto)
                avance = orquestacion.abrir_avance(cfg, "m34")
                avance.iniciar()
                huellas.append(orquestacion.huella_de_corrida(cfg, "m34"))
                limites = orquestacion._procesos_de_fases(cfg, "m34", procesos)
                repartos = {f: [] for f in limites}
                for fase, limite in limites.items():
                    valores = orquestacion.repartir(range(2), _cuadrado, limite, registro=repartos[fase])
                    self.assertEqual(valores, [0, 1])
                sal = {salidas.POLITICA: orquestacion._escribir(avance, salidas.POLITICA, b"[]"),
                       "qc/resumen_qc.json": orquestacion._escribir(avance, "qc/resumen_qc.json", {"n": sum(valores)})}
                r = orquestacion._sellar_m34(cfg, avance, {"huellas": {}},
                                           {"esquema": orquestacion.ESQUEMA_REGISTRO_M34,
                                            "procesos_por_fase": presupuesto}, [], None, sal, procesos, {}, limites,
                                           repartos=repartos)
                registros.append(r["registro"])
                inventarios.append(json.loads((avance.carpeta / salidas.SHA256_JSON).read_bytes())["archivos"])
                recibo = json.loads((avance.carpeta / salidas.RECIBO).read_bytes())["entorno"]
                self.assertEqual(recibo["procesos"], min(procesos, 2))
                self.assertEqual(recibo["presupuesto"]["procesos"], procesos)
                for fase in limites:
                    self.assertEqual(recibo["procesos_por_fase"][fase]["procesos"], min(procesos, 2))
        self.assertEqual(len(set(huellas)), 1)
        self.assertEqual(registros, [registros[0]] * 3)
        self.assertEqual(inventarios, [inventarios[0]] * 3)

    def test_m34_principal_y_fases_no_ejecutadas(self):
        """Al sellar una detención, las fases no ejecutadas no heredan ficticiamente el límite 8."""
        with tempfile.TemporaryDirectory(prefix="emc3-m34-principal-") as tmp:
            cfg = Cfg(rutas=entorno.rutas_sinteticas(tmp), umbrales=None, entradas={}, huellas={},
                      etiqueta=_ETIQUETA, procesos=8)
            avance = orquestacion.abrir_avance(cfg, "m34")
            avance.iniciar()
            limites = orquestacion._procesos_de_fases(cfg, "m34", 8)
            repartos = {f: [] for f in limites}
            orquestacion.repartir([0], _cuadrado, 8, registro=repartos["artefactos"])
            sal = {salidas.POLITICA: orquestacion._escribir(avance, salidas.POLITICA, b"[]")}
            orquestacion._sellar_m34(cfg, avance, {"huellas": {}}, {"detenida": True}, [], None, sal, 8, {}, limites,
                                    repartos=repartos)
            recibo = json.loads((avance.carpeta / salidas.RECIBO).read_bytes())["entorno"]
            self.assertEqual(recibo["procesos"], 1)
            self.assertEqual(recibo["procesos_por_fase"]["artefactos"]["trabajadores_creados"], {"procesos": 0})
            for fase in ("seleccion_y_prediccion", "tendencias_y_finitud"):
                self.assertEqual(recibo["procesos_por_fase"][fase],
                                 {"procesos": 0, "trabajadores_creados": {"procesos": 0}, "repartos": []})

    def test_anual_solo_cuenta_los_anios_pendientes(self):
        """La función anual real filtra el avance antes de repartir; la unidad científica se sustituye."""
        meses = {f"{anio}02": f"ERA5L/sintetico_{anio}.nc" for anio in (2019, 2020, 2021)}
        with tempfile.TemporaryDirectory(prefix="emc3-anual-") as tmp:
            cfg = Cfg(rutas=entorno.rutas_sinteticas(tmp), umbrales=None, entradas={"meses_era5l": meses},
                      huellas={a: "a" * 64 for a in meses.values()})
            for n in (0, 1, 2):
                with self.subTest(pendientes=n):
                    pendientes = {f"anio-{anio}" for anio in (2019, 2020, 2021)[:n]}
                    avance = Mock()
                    avance.hecha.side_effect = lambda fase, unidad, entrada: (None if unidad in pendientes else
                                                                             {"archivos": {"x": "b" * 64}})
                    usos = []
                    with patch.object(orquestacion, "_unidad_anio", _anio_emc3):
                        orquestacion._correr_anual(cfg, avance, {}, {"pixeles": True}, "b" * 64, 8, registro=usos)
                    self.assertUso(usos[0], n, 8, n, 0 if n <= 1 else n)
                    self.assertEqual(len(avance.saltadas.append.call_args_list), 3 - n)

    def test_m5_recibo_1_2_y_reanudacion_sin_trabajo(self):
        """M5 real con cálculo sustituido: propaga las observaciones hasta el recibo, aun al saltar una fase."""
        from meteo_combinada import ambiental, salud
        inventarios, huellas = {1: [], 2: []}, {1: [], 2: []}
        for n, procesos in ((n, p) for n in (1, 2) for p in (1, 2, 8)):
            with self.subTest(unidades=n, procesos=procesos), tempfile.TemporaryDirectory(prefix="emc3-m5-") as tmp:
                rutas = entorno.rutas_sinteticas(tmp)
                meses = {f"2020{m:02d}": f"ERA5L/sintetico_{m}.nc" for m in range(1, n + 1)}
                cfg = Cfg(rutas=rutas, umbrales=None, entradas={"meses_era5l": meses, "h_ultima": 0,
                          "catalogo_pixeles": "LOCAL/catalogo.json"}, huellas={a: "a" * 64 for a in
                          (*meses.values(), "LOCAL/catalogo.json")}, etiqueta=_ETIQUETA, procesos=procesos)
                carpeta = orquestacion.carpeta_de(cfg, "m34")
                orquestacion.Avance(carpeta, corrida=_ETIQUETA, huella="b" * 64).iniciar()
                p = {"datos": SimpleNamespace(estaciones={"s": SimpleNamespace(lat=0., lon=0.)}), "decision": {},
                     "validos": [], "cat_pix": None, "corrida": {"sha": lambda _: "c" * 64, "leer": lambda _: b""},
                     "m2a": {"carpeta": entorno.carpeta_salida(rutas, "m2a"), "sha": lambda _: "d" * 64,
                             "huellas": {}}}
                pendientes = n

                def anual(cfg, avance, p, ctx, base, procesos, *, registro):
                    orquestacion.repartir(range(pendientes), _cuadrado, procesos, registro=registro)
                    return {}

                unica = orquestacion._unidad_unica

                def unidad(avance, fase, unidad, entrada, nombre, producir, **kwargs):
                    return (unica(avance, fase, unidad, entrada, nombre, producir, **kwargs)
                            if nombre == orquestacion.EXCLUIDAS else "e" * 64)

                sustituciones = {"_negativas": lambda *a: [], "_leer_carpeta": lambda *a: {},
                    "_negativas_registro": lambda *a: [], "_produccion": lambda *a, **k: p,
                    "_base_de": lambda *a: "f" * 64, "_ganador_y_hiper": lambda *a: ("A", {}),
                    "_parquet": lambda *a: pd.DataFrame({"h": [0], "Ts": [0.], "valido_T": [True]}),
                    "_unidad_t2m": _t2m_emc3, "_producto_salud": lambda *a: {}, "_clave_producto": lambda *a: {},
                    "_contexto_pixeles": lambda *a: None, "_contexto_anual": lambda *a, **k: {},
                    "_correr_anual": anual, "_ensamblar_laterales": lambda *a: {}, "_unidad_unica": unidad}
                with (patch.multiple(orquestacion, **sustituciones),
                      patch.object(ambiental, "ganador_ambiental", return_value=({}, {})),
                      patch.object(salud, "representatividad", return_value=[]),
                      patch.object(fijados, "cargar_elegir_pixel", return_value=Mock(
                          enlazar=Mock(return_value=SimpleNamespace(pixel_id=None))))):
                    for repeticion in (0, 1):
                        avance = orquestacion.abrir_avance(cfg, "m5")
                        orquestacion.correr_m5(cfg, avance=avance, procesos=procesos)
                        recibo = json.loads((carpeta / salidas.RECIBO).read_bytes())["entorno"]
                        esperado = min(n, procesos) if repeticion == 0 else 0
                        if not repeticion:
                            inventarios[n].append(json.loads((carpeta / salidas.SHA256_JSON).read_bytes())["archivos"])
                            huellas[n].append(orquestacion.huella_de_corrida(cfg, "m5"))
                        self.assertEqual(recibo["procesos"], esperado)
                        for fase in orquestacion.FASES_REPARTO["m5"]:
                            self.assertEqual(recibo["procesos_por_fase"][fase]["procesos"], esperado)
                        self.assertEqual(recibo["presupuesto"]["procesos"], procesos)
                        if repeticion:
                            self.assertEqual(recibo["procesos_por_fase"]["representatividad"]["repartos"], [])
                        pendientes = 0
        for n in (1, 2):
            self.assertEqual(inventarios[n], [inventarios[n][0]] * 3)
            self.assertEqual(len(set(huellas[n])), 1)


class PruebasProcesosPorFase(unittest.TestCase):
    def test_cfg_procesos_por_fase_forma_modos_reales_y_huella(self):
        """ORQ-45 (D59, A39): ``Cfg.procesos_por_fase`` es None o exactamente {compuerta: {fase: n}} con las compuertas
        y fases de ``FASES_REPARTO`` y n entero (no bool) de 1 a PROCESOS, congelado en el orden de FASES_REPARTO;
        obligatorio en todos los modos reales y None por omisión en el sintético; no entra en la huella de la
        corrida (ORQ-8)."""
        U = _umbrales()
        tope = constantes.valor("PROCESOS")
        fases = orquestacion.FASES_REPARTO
        self.assertEqual({c: tuple(f) for c, f in fases.items()},
                         {"m34": ("artefactos", "seleccion_y_prediccion", "tendencias_y_finitud"),
                          "m5": ("representatividad", "anual")})
        self.assertTrue(set(fases["m34"]) <= set(orquestacion.FASES_M34))
        self.assertTrue(set(fases["m5"]) <= set(orquestacion.FASES_M5))
        with self.assertRaises(TypeError):
            fases["m6"] = ("anual",)

        def con(compuerta, **cambios):
            d = json.loads(json.dumps(_POR_FASE))
            d[compuerta].update(cambios)
            return d
        malos = {"compuerta de más": {**_POR_FASE, "m6": {"anual": 1}}, "compuerta de menos": {"m34": _POR_FASE["m34"]},
                 "fase de más": con("m34", residuos=1), "fase de menos": {**_POR_FASE, "m5": {"representatividad": 1}},
                 "cero": con("m5", anual=0), "más de PROCESOS": con("m5", anual=tope + 1),
                 "negativo": con("m34", artefactos=-1), "bool": con("m34", artefactos=True),
                 "decimal": con("m34", artefactos=2.0), "texto": con("m34", artefactos="2"),
                 "fases que no son un mapa": {**_POR_FASE, "m5": [["representatividad", 1], ["anual", 1]]},
                 "no es un mapa": [["m34", _POR_FASE["m34"]], ["m5", _POR_FASE["m5"]]]}
        with tempfile.TemporaryDirectory() as tmp:
            rutas = entorno.rutas_sinteticas(tmp)
            base = dict(rutas=rutas, umbrales=U, entradas={}, huellas={}, etiqueta=_ETIQUETA)
            for nombre, valor in malos.items():
                with self.subTest(nombre), self.assertRaisesRegex(orquestacion.ErrorOrquestacion, "procesos_por_fase"):
                    Cfg(**base, procesos_por_fase=valor)
            pedido = json.loads(json.dumps({c: dict(reversed(list(v.items()))) for c, v in _POR_FASE.items()}))
            cfg = Cfg(**base, procesos_por_fase=pedido)
            self.assertEqual(json.loads(json.dumps(orquestacion._a_plano(cfg.procesos_por_fase))), _POR_FASE)
            self.assertEqual({c: tuple(v) for c, v in cfg.procesos_por_fase.items()}, dict(fases))   # su orden
            pedido["m34"]["artefactos"] = 1                     # congelado: no sigue al diccionario de quien llama
            self.assertEqual(cfg.procesos_por_fase["m34"]["artefactos"], _POR_FASE["m34"]["artefactos"])
            with self.assertRaises(TypeError):
                cfg.procesos_por_fase["m34"]["artefactos"] = 1
            sin = Cfg(**base)
            self.assertIsNone(sin.procesos_por_fase)
            otro = Cfg(**base, procesos_por_fase=con("m5", anual=1))
            for compuerta in ("m34", "m5"):                     # ORQ-8: los procesos no cambian la huella
                self.assertEqual(len({orquestacion.huella_de_corrida(x, compuerta) for x in (cfg, sin, otro)}), 1)
            real = dict(recorte=False, deriva={"B": False, "AB": False})
            for modo in orquestacion.MODOS_REALES:
                entradas = {"conjuntos": {}} if modo == tipos.Modo.ESTATICOS.value else {}
                with self.subTest(modo=modo):
                    with self.assertRaisesRegex(orquestacion.ErrorOrquestacion, "D59"):
                        Cfg(rutas=rutas, umbrales=U, entradas=entradas, huellas={}, modo=modo, **real)
                    Cfg(rutas=rutas, umbrales=U, entradas=entradas, huellas={}, modo=modo, **real,
                        procesos_por_fase=_POR_FASE)

    def test_procesos_de_cada_fase_y_recibo(self):
        """ORQ-45: cada fase que reparte corre con mín(procesos, n), o con procesos si no hay procesos por fase; un
        procesos que no es un entero ≥ 1 llega tal cual a ``repartir``, que lo rechaza como siempre; el recibo lleva
        los de cada fase sólo si se le dan."""
        U = _umbrales()
        tope = constantes.valor("PROCESOS")
        with tempfile.TemporaryDirectory() as tmp:
            base = dict(rutas=entorno.rutas_sinteticas(tmp), umbrales=U, entradas={}, huellas={})
            cfg, sin = Cfg(**base, procesos_por_fase=_POR_FASE), Cfg(**base)
        self.assertEqual(orquestacion._procesos_de_fases(cfg, "m34", 2),
                         {"artefactos": 2, "seleccion_y_prediccion": 1, "tendencias_y_finitud": 2})
        self.assertEqual(orquestacion._procesos_de_fases(cfg, "m34", tope),
                         {"artefactos": 3, "seleccion_y_prediccion": 1, "tendencias_y_finitud": tope})
        self.assertEqual(orquestacion._procesos_de_fases(cfg, "m5", 1), {"representatividad": 1, "anual": 1})
        self.assertEqual(orquestacion._procesos_de_fases(sin, "m5", tope), {"representatividad": tope, "anual": tope})
        with self.assertRaises(orquestacion.ErrorOrquestacion):
            orquestacion._procesos_de_fases(cfg, "m6", 2)              # M6 sigue con Cfg.procesos
        for malo in (0, True, "2"):
            self.assertEqual(list(orquestacion._procesos_de_fases(cfg, "m5", malo).values()), [malo, malo])
            with self.assertRaises(orquestacion.ErrorOrquestacion):
                orquestacion.repartir([1, 2], _cuadrado, orquestacion._procesos_de_fases(cfg, "m5", malo)["anual"])
        limites = {"representatividad": 1, "anual": 2}
        repartos = {f: [] for f in limites}
        for fase, limite in limites.items():
            orquestacion.repartir([0, 1], _cuadrado, limite, registro=repartos[fase])
        recibo = orquestacion._entorno_recibo(2, limites, repartos=repartos)
        self.assertEqual((recibo["procesos"], {f: r["procesos"] for f, r in recibo["procesos_por_fase"].items()}),
                         (2, limites))
        self.assertEqual(recibo["presupuesto"]["procesos_por_fase"],
                         {f: {"procesos": n} for f, n in limites.items()})
        self.assertNotIn("procesos_por_fase", orquestacion._entorno_recibo(2))
        sello = salidas.recibo_corrida({"LOCAL/x.json": _sha(b"x")}, recibo)    # la guarda de la procedencia lo admite
        self.assertEqual(sello["entorno"]["procesos_por_fase"], recibo["procesos_por_fase"])

    def test_m34_y_m5_con_procesos_por_fase_mismos_bits(self):
        """ORQ-45 (D59, A39; S9): con ``Cfg.procesos_por_fase`` y 3 procesos, con topes de 1 y 2 en las cinco fases
        (en cada una, mín(procesos, n) es su tope y no ``procesos``; n ≥ procesos lo cubre
        ``test_procesos_de_cada_fase_y_recibo``), cada ``repartir`` de una fase que reparte recibe el mínimo de su fase
        y todas reparten; M3-4 y M5 dan los mismos bytes que con 1 proceso y sin procesos por fase (todo
        ``sha256.json`` salvo ``avance.jsonl`` y, en el registro de M3-4, «procesos_por_fase», que lleva los de Cfg:
        None en el sintético), y el recibo lleva los procesos con que corrió cada fase."""
        de_fase = {"_unidad_estacion": ("m34", "artefactos"), "_unidad_seleccion": ("m34", "seleccion_y_prediccion"),
                   "_unidad_mes_tf": ("m34", "tendencias_y_finitud"), "_unidad_t2m": ("m5", "representatividad"),
                   "_unidad_anio": ("m5", "anual")}
        procesos = _PROCESOS_CORRIDA
        for compuerta, base in (("m34", _correr_m34(1)), ("m5", _correr_m5(1))):
            with self.subTest(compuerta=compuerta):
                c = _correr_por_fase(compuerta, procesos, _POR_FASE_CORRIDA)
                self.assertEqual((c["accesos"], c["red"]), ([], []))
                esperados = {f: min(procesos, n) for f, n in _POR_FASE_CORRIDA[compuerta].items()}
                self.assertEqual(esperados, _POR_FASE_CORRIDA[compuerta])
                self.assertTrue(all(n < procesos for n in esperados.values()))      # nunca ``procesos``
                self.assertEqual(set(esperados.values()), {1, 2})            # en el principal y con trabajadores
                vistas: dict = {}
                for nombre, n in c["llamadas"]:
                    self.assertEqual(de_fase[nombre][0], compuerta, nombre)
                    self.assertEqual(n, esperados[de_fase[nombre][1]], nombre)
                    vistas[de_fase[nombre][1]] = n
                self.assertEqual(vistas, esperados)
                env = c["recibo"]["entorno"]
                self.assertEqual(env["presupuesto"],
                                 {"procesos": procesos, "procesos_por_fase": {f: {"procesos": n}
                                                                           for f, n in esperados.items()}})
                self.assertEqual((env["procesos"], {f: r["procesos"] for f, r in env["procesos_por_fase"].items()}),
                                 (max(esperados.values()), esperados))
                recibo_base = json.loads((base["carpeta"] / salidas.RECIBO).read_text(encoding="utf-8"))
                self.assertEqual({f: r["procesos"] for f, r in recibo_base["entorno"]["procesos_por_fase"].items()},
                                 dict.fromkeys(orquestacion.FASES_REPARTO[compuerta], 1))
                if compuerta == "m34":
                    self.assertEqual(c["r"]["decision"], base["r"]["decision"])
                    reg, reg_base = (json.loads((x["carpeta"] / orquestacion.REGISTRO_M34).read_text(encoding="utf-8"))
                                     for x in (c, base))
                    ceguera.vigilar_salida(orquestacion.REGISTRO_M34, reg, clase="resumen")
                    self.assertEqual((reg.pop("procesos_por_fase"), reg_base.pop("procesos_por_fase")),
                                     (_POR_FASE_CORRIDA, None))
                    self.assertEqual(reg, reg_base)
                    quitar = (orquestacion.AVANCE, orquestacion.REGISTRO_M34)
                    self.assertEqual({k: v for k, v in c["inventario"].items() if k not in quitar},
                                     {k: v for k, v in base["inventario"].items() if k not in quitar})
                else:
                    self.assertEqual(_sin_avance(c["inventario"]), _sin_avance(base["inventario"]))
        self.assertEqual(ceguera.procesos_hijos_vivos(), [])

    def test_m6_sigue_con_cfg_procesos(self):
        """ORQ-45 (A39: D59 no nombra M6): con ``Cfg.procesos_por_fase`` en 1 en todas las fases y ``Cfg.procesos`` =
        2, M6 reparte con 2 (la rama 3, que rehace el operador y las laterales restringidos en sus unidades anuales) y
        da los mismos bytes que con 1 proceso y sin procesos por fase."""
        todo_uno = {c: dict.fromkeys(f, 1) for c, f in orquestacion.FASES_REPARTO.items()}
        c = _correr_m6("rama3", procesos=2, por_fase=todo_uno)
        self.assertEqual((c["accesos"], c["red"]), ([], []))
        self.assertEqual(c["cfg"].procesos_por_fase["m5"]["anual"], 1)
        self.assertTrue(c["llamadas"])
        self.assertEqual(sorted({n for _, n in c["llamadas"]}), [2])
        self.assertEqual(_sin_avance(c["inventario"]), _sin_avance(_correr_m6("rama3")["inventario"]))
        self.assertEqual(ceguera.procesos_hijos_vivos(), [])


# ---------------------------------------------------------------------------
# M6 (segunda fase)
# ---------------------------------------------------------------------------
class PruebasM6(unittest.TestCase):
    def _comunes(self, c: dict) -> dict:
        """Lo de toda corrida de M6: fases, guardas, la TF de contaminantes por la fábrica de A26, ``ramas_m6.json`` y
        ``decision_m6.json`` (resumen, con la rama, la variante y O3 del caso), ``s6.json``, la S6 sobre las mismas
        filas que la civil de M5, y el sello de ``m6/``."""
        self.assertEqual((c["accesos"], c["red"]), ([], []))
        self.assertEqual(ceguera.procesos_hijos_vivos(), [])
        r, inv, carpeta, d6 = c["r"], c["inventario"], c["carpeta"], c["d6"]
        self.assertEqual(r["fases"], list(orquestacion.FASES_M6))
        self.assertEqual(carpeta, entorno.carpeta_salida(c["rutas"], "m6", _ETIQUETA))
        for nombre in inv:
            self.assertIsNotNone(salidas.clase_de_salida("m6/" + nombre) or ceguera.clase_de_ruta("m6/" + nombre),
                                 nombre)
        # la TF de contaminantes (Anexo B; A26): las cuatro, con la fábrica de la corrida
        self.assertEqual(c["fabrica"].llamadas, [(p, v) for p in tipos.CONTAMINANTES_M6 for v in ("I", "D")])
        self.assertTrue(all(x.startswith("mc_") for x in c["fabrica"].columnas["I"][2:]))
        self.assertTrue(any(x.startswith("dmc_R_") for x in c["fabrica"].columnas["D"]))
        for pol in tipos.CONTAMINANTES_M6:
            for v in ("I", "D"):
                tf = json.loads((carpeta / f"tf_contaminantes_{pol}_{v}.json").read_text(encoding="utf-8"))
                ceguera.vigilar_salida(f"m6/tf_contaminantes_{pol}_{v}.json", tf, clase="resumen")
                self.assertEqual(tf["resultado"], d6["tf_contaminantes"][pol][v])
                self.assertFalse(tf["verificacion_un_mes"])               # B y AB ganan en lo ambiental (DEC-14)
        # decision_m6.json y ramas_m6.json
        dec = json.loads((carpeta / "decision_m6.json").read_text(encoding="utf-8"))
        ceguera.vigilar_salida("m6/decision_m6.json", dec, clase="resumen")
        ramas = json.loads((carpeta / orquestacion.RAMAS_M6).read_text(encoding="utf-8"))
        ceguera.vigilar_salida("m6/" + orquestacion.RAMAS_M6, ramas, clase="resumen")
        self.assertEqual(dec["esquema"], tipos.VERSION_DECISION_M6)
        self.assertEqual(dec["rama"], d6["esperado"]["rama"])
        self.assertEqual(dec["variante"], d6["esperado"]["variante"])
        self.assertEqual({k: dec[k] for k in ("rama", "variante", "ganador_restringido", "condiciones")},
                         {k: ramas[k] for k in ("rama", "variante", "ganador_restringido", "condiciones")})
        self.assertIn(entorno.alias(carpeta / orquestacion.RAMAS_M6, c["rutas"]), dec["huellas"])
        self.assertEqual(dec["huellas"][_COMPARACION_M6], c["cfg"].huellas[_COMPARACION_M6])
        # la S6 (§7.2, punto 5): s6.json y las tablas, sobre las filas de la civil de M5
        s6 = json.loads((carpeta / orquestacion.S6_M6).read_text(encoding="utf-8"))
        ceguera.vigilar_salida("m6/" + orquestacion.S6_M6, s6, clase="resumen")
        corrida = carpeta.parent
        for a in _ANIOS:
            t = _tabla(carpeta, f"salud/s6/meteo_{a}.parquet")
            tipos.validar_esquema(t, tipos.ESQUEMA_METEO_DIARIA, nombre="s6")
            civil = _tabla(corrida, f"salud/civil/meteo_{a}.parquet")
            fijas = ["cod_comuna", "dia", "precip_mm", "n_horas", "n_horas_esperadas", "faltan_horas"]
            pd.testing.assert_frame_equal(t[fijas], civil[fijas], check_exact=True)
            self.assertIn(entorno.alias(carpeta / f"salud/s6/meteo_{a}.parquet", c["rutas"]), dec["huellas"])
        recibo = json.loads((carpeta / salidas.RECIBO).read_text(encoding="utf-8"))
        self.assertEqual(recibo["huellas"][entorno.alias(carpeta / salidas.SHA256_JSON, c["rutas"])],
                         _sha((carpeta / salidas.SHA256_JSON).read_bytes()))
        return {"dec": dec, "s6": s6, "corrida": corrida}

    def _segundo_agudo(self) -> str:
        d = next(x for x in _plantilla_m5()["decision"]["decisiones"] if (x["uso"], x["grupo"]) == ("agudo", "T_Td"))
        return min((x for x in d["e1"] if x != d["ganador"]), key=lambda x: d["S"][x])

    def _sin_restringido(self, c: dict, comunes: dict) -> None:
        """Ramas 1 y 2: sin ganador restringido, nada en ``m6/ambiental/``; las laterales vigentes son las de M5; la S6
        es la del segundo agudo de E1 (AB gana en lo agudo y en (T, Td) ambiental), con sus hiperparámetros agudos."""
        dec, s6 = comunes["dec"], comunes["s6"]
        self.assertIsNone(dec["ganador_restringido"])
        self.assertFalse(any(n.startswith("ambiental/") for n in c["inventario"]))
        for pol in tipos.CONTAMINANTES_M6:
            for v in ("I", "D"):
                nombre = f"ambiental/lateral_{pol}_{v}.parquet"
                alias = entorno.alias(comunes["corrida"] / nombre, c["rutas"])
                self.assertEqual(dec["huellas"][alias], _sha((comunes["corrida"] / nombre).read_bytes()))
        segundo = self._segundo_agudo()
        self.assertEqual((s6["regla"], s6["candidato"], s6["uso_hiperparametros"]),
                         (orquestacion.REGLA_S6_SEGUNDO, segundo, "agudo"))
        a_mano = _salud_a_mano(c, 2020, {"T_Td": segundo}, _hiper_de("agudo", segundo))
        _comparar_salud(self, c["carpeta"], "salud/s6/meteo_2020.parquet", a_mano)

    def test_m6_rama_1_supera_d_y_o3(self):
        """Rama 1 (Anexo B): D supera a I en los dos contaminantes y pasa su TF: gana D; O3 toma la de los dos (D)."""
        c = _correr_m6("rama1_D")
        comunes = self._comunes(c)
        self.assertEqual(comunes["dec"]["rama"], {"pm25": 1, "no2": 1})
        self.assertEqual(comunes["dec"]["variante"]["O3"], "D")
        self._sin_restringido(c, comunes)

    def test_m6_rama_2_ninguna_supera(self):
        """Rama 2: ninguna supera y I pasa su TF: gana I en los dos y en O3."""
        c = _correr_m6("rama2_ninguna")
        comunes = self._comunes(c)
        self.assertEqual(comunes["dec"]["rama"], {"pm25": 2, "no2": 2})
        self.assertEqual(comunes["dec"]["variante"], {"pm25": "I", "no2": "I", "O3": "I"})
        self._sin_restringido(c, comunes)

    def test_m6_rama_3_restringido_rehace_solo_b_y_ab(self):
        """Rama 3 (Anexo B; §6.4): en pm25 las dos fallan su TF: I restringido para todos. Se rehacen sólo (T, Td) y p
        (que ganaban AB y B), entre A y C; (u, v) queda con A. El operador y las cuatro laterales restringidos van en
        ``m6/ambiental/`` (P98), citan ``ramas_m6.json`` (ORQ-30) y son las vigentes en ``decision_m6.json``; la S6 es
        la del ganador ambiental definitivo de (T, Td), distinto del agudo, con sus hiperparámetros ambientales."""
        from meteo_combinada import ambiental, decision
        c = _correr_m6("rama3")
        comunes = self._comunes(c)
        dec, s6, carpeta = comunes["dec"], comunes["s6"], c["carpeta"]
        tablas = _plantilla_m5()["tablas"]
        entradas = {g: _entradas_de("ambiental", g, tablas[("ambiental", g)]) for g in ("T_Td", "u_v", "p")}
        esperado = decision.ganador_restringido(entradas, {"T_Td", "p"}, umbrales=_mundo().U)
        self.assertEqual(dec["ganador_restringido"], esperado)
        self.assertEqual(c["r"]["restringido"], esperado)
        self.assertEqual(esperado["u_v"], "A")
        self.assertTrue({esperado["T_Td"], esperado["p"]} <= {"A", "C"})
        op = ambiental.leer_operador((carpeta / orquestacion.OPERADOR_GRILLA).read_bytes())
        self.assertTrue(op.restringido)
        self.assertEqual(dict(op.ganador), esperado)
        self.assertEqual(op.ramas_m6_sha256, _sha((carpeta / orquestacion.RAMAS_M6).read_bytes()))
        for pol in tipos.CONTAMINANTES_M6:
            for v in ("I", "D"):
                nombre = f"ambiental/lateral_{pol}_{v}.parquet"
                t = pd.read_parquet(carpeta / nombre)
                self.assertEqual(t.attrs["metadatos"]["operador_sha256"], op.sha256)
                self.assertEqual(ceguera.clase_de_ruta("m6/" + nombre), "insumo")
                self.assertEqual(dec["huellas"][entorno.alias(carpeta / nombre, c["rutas"])],
                                 _sha((carpeta / nombre).read_bytes()))
                vieja = pd.read_parquet(comunes["corrida"] / nombre)
                self.assertEqual(len(t), len(vieja))
        self.assertEqual((s6["regla"], s6["candidato"], s6["uso_hiperparametros"]),
                         (orquestacion.REGLA_S6_AMBIENTAL, esperado["T_Td"], "ambiental"))
        cand = esperado["T_Td"]
        a_mano = _salud_a_mano(c, 2020, {"T_Td": cand}, _hiper_de("ambiental", cand))
        _comparar_salud(self, carpeta, "salud/s6/meteo_2020.parquet", a_mano)

    def test_m6_sin_b_ni_ab_verifica_i_en_un_mes(self):
        """DEC-14 (TEN-21): con A en los tres grupos ambientales, la TF de I es la verificación de un mes (0 por
        construcción) y la de D se exige entera; la rama 2 elige I."""
        c = _correr_m6("rama2_ninguna", "sin_b_ab")
        self.assertEqual((c["accesos"], c["red"]), ([], []))
        self.assertEqual(c["r"]["fases"], list(orquestacion.FASES_M6))
        for pol in tipos.CONTAMINANTES_M6:
            tf_i = json.loads((c["carpeta"] / f"tf_contaminantes_{pol}_I.json").read_text(encoding="utf-8"))
            tf_d = json.loads((c["carpeta"] / f"tf_contaminantes_{pol}_D.json").read_text(encoding="utf-8"))
            self.assertEqual((tf_i["verificacion_un_mes"], tf_i["resultado"]), (True, "pasa"))
            self.assertFalse(tf_d["verificacion_un_mes"])
        self.assertEqual(c["r"]["decision_m6"]["variante"], {"pm25": "I", "no2": "I", "O3": "I"})

    def test_m6_con_dos_procesos_igual(self):
        """H8 (g), S9 en M6: la rama 3 (S6, operador y laterales restringidos) da los mismos bytes con 1 y 2
        procesos."""
        uno, dos = _correr_m6("rama3"), _correr_m6("rama3", procesos=2)
        self.assertEqual((dos["accesos"], dos["red"]), ([], []))
        self.assertEqual(_sin_avance(dos["inventario"]), _sin_avance(uno["inventario"]))
        self.assertEqual(ceguera.procesos_hijos_vivos(), [])

    def test_m6_muestra_de_la_tf(self):
        """H8 (j), TEN-19: la fábrica recibe las celdas de la muestra fija de la TF de contaminantes (hasta 50 por
        comuna, con w_ghs de 2020), la de ``tendencias.muestra_tf_contaminantes`` a mano."""
        from meteo_combinada import tendencias
        m, c = _mundo(), _correr_m6("rama1_D")
        celdas = pd.read_parquet(c["rutas"].grilla / "celdas.parquet")
        pesos = pd.read_parquet(c["rutas"].pesos / "poblacion_celda_anio.parquet")
        p20 = pesos[pesos["anio"] == constantes.valor("TF_PESOS_ANIO")][["celda", "w_ghs"]]
        t = celdas[["celda", "cod_comuna"]].merge(p20, on="celda").sort_values("celda").reset_index(drop=True)
        muestra = tendencias.muestra_tf_contaminantes(t[["celda", "cod_comuna"]], t["w_ghs"].to_numpy(), m.U)
        self.assertEqual(c["fabrica"].celdas, {tuple(int(x) for x in muestra["celda"])})

    def test_m6_sin_fabrica_se_niega(self):
        """ORQ-29: sin ``Cfg.fabrica_m6`` (la fábrica de producción v2, aún no escrita) la TF de contaminantes no
        corre."""
        m = _mundo()
        tmp, rutas = _copiar(_correr_m5(1)["tmp"].name)
        with tmp:
            _escribir_parquet(orquestacion.ruta_de_alias(rutas, _COMPARACION_M6), S.tablas_m6("rama1_D")["comparacion"])
            cfg = m.cfg_m6(rutas)
            with self.assertRaises(orquestacion.ErrorOrquestacion) as e:
                orquestacion.correr_m6(cfg, avance=orquestacion.abrir_avance(cfg, "m6"))
            self.assertIn("fabrica_m6", str(e.exception))


def tearDownModule():
    for grupo in (_POR_FASE_CORRIDAS, _M6, _M5, _PLANTILLA, _CORRIDAS):
        for c in grupo.values():
            c["tmp"].cleanup()
    if _MUNDO is not None:
        _MUNDO._tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
