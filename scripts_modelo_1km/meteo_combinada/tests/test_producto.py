"""Pruebas de producto.py (§3, §4.1, §6.2 y §8).

Dueño: I16 (ola 4). Las que llevan «sNN» son la prueba NN de §9 del texto: aquí, la parte del int16 de S15. Correr desde
scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest meteo_combinada.tests.test_producto
Datos sólo sintéticos: una red de 10 estaciones hecha aquí (residuos, fondo en las estaciones, clima del estado y
estáticos de sus celdas), un mes ERA5-Land de ``sintetico.mes_era5_netcdf`` escrito en una carpeta temporal y leído en
memoria, el catálogo de ``sintetico.catalogo_pixeles`` y la grilla de ``sintetico.grilla``. Ninguna prueba abre DMC, la
meteorología SINCA real, NASADEM real, ERA5L real ni GHS-POP real. Los umbrales son los anclados en M0
(``umbrales.cargar_m0``); sólo se leen el texto y el JSON de umbrales de APH. Semilla: ``SEMILLA`` del Anexo A.
"""
import sys

sys.dont_write_bytecode = True

import dataclasses  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import types  # noqa: E402
import unittest  # noqa: E402
from functools import lru_cache  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import (candidatos, ceguera, constantes, fondo_era5l, numerico, particiones,  # noqa: E402
                             producto, sintetico, tipos, umbrales)
from meteo_combinada.tipos import Candidato, Grupo, Hiper, Uso  # noqa: E402

_AP = _RAIZ.parent
_APH = _AP.parent / "Air-Pollution-Health-Chile"
_EPOCA = np.datetime64("2000-01-01T00", "h")
NAN = float("nan")
K = constantes.valor("KELVIN")
VARIABLES = producto.VARIABLES
H_A = Hiper(50.0, 50.0, 0.2)
H_B = Hiper(25.0, 0.0, 0.5)
HIPER = {Candidato.A: H_A, Candidato.B: H_B, Candidato.AB: (H_A, H_B), Candidato.C: 10.0, Candidato.C_EST: 10.0}
# H1 del revisor: un θ distinto en cada variable (u y v comparten el suyo, MC-43), para que «el θ de T en todas las
# variables» no pase la paridad. En AB los pares van cruzados entre T y Td.
H_1, H_2, H_3, H_4 = Hiper(50.0, 50.0, 0.2), Hiper(25.0, 0.0, 0.5), Hiper(100.0, 150.0, 1.0), Hiper(200.0, 0.0, 0.05)
HIPER_POR_VARIABLE = {
    Candidato.A: {"T": H_1, "Td": H_2, "u": H_3, "v": H_3, "p": H_4},
    Candidato.B: {"T": H_2, "Td": H_1, "u": H_4, "v": H_4, "p": H_3},
    Candidato.AB: {"T": (H_1, H_2), "Td": (H_2, H_1), "u": (H_3, H_4), "v": (H_3, H_4), "p": (H_4, H_3)},
    Candidato.C: {"T": 10.0, "Td": 0.1, "u": 1.0, "v": 1.0, "p": 100.0},
    Candidato.C_EST: {"T": 10.0, "Td": 0.1, "u": 1.0, "v": 1.0, "p": 100.0},
}
USO_DE = {Candidato.A: Uso.AGUDO, Candidato.B: Uso.AGUDO, Candidato.AB: Uso.AGUDO, Candidato.C: Uso.AGUDO,
          Candidato.C_EST: Uso.CRONICO}
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


def _horas_mes(anio: int, mes: int) -> np.ndarray:
    return (sintetico.horas_del_mes(anio, mes).astype("datetime64[h]") - _EPOCA).astype(np.int64)


def _hiper(cand: Candidato, variables=VARIABLES) -> dict:
    return {v: HIPER[cand] for v in variables}


# ---------------------------------------------------------------------------
# Red sintética: 10 estaciones, residuos, fondo en las estaciones, clima del estado y estáticos
# ---------------------------------------------------------------------------
def _info(codigo: str, lat: float, lon: float, z: float, celda) -> tipos.InfoEstacion:
    e, n = (float(x[0]) for x in numerico.utm19s(np.array([lat, lat]), np.array([lon, lon])))   # pyproj: >1 punto
    return tipos.InfoEstacion(
        codigo=codigo, nombre=f"E{codigo}", conjunto="V", macrozona="centro", grupo=tipos.id_grupo([codigo]),
        omm=None, tipo=None, propietario=None, lat_txt=f"{lat:.4f}", lon_txt=f"{lon:.4f}", alt_txt=f"{z:.0f}",
        lat=float(lat), lon=float(lon), z_cat=float(z), rho_km=0.1, k3_pasa=True, z_s=float(z),
        z_s_fuente="catalogo", celda=celda, utm_e=float(e), utm_n=float(n), bloque="", pix0=0, pix1=-1, pix2=-1,
        pix3=-1, w0=1.0, w1=0.0, w2=0.0, w3=0.0, respaldo_16km=False, sin_fondo=False, excluida=False, motivo=None)


@lru_cache(maxsize=None)
def _red() -> dict:
    """3 × 3 estaciones a ≈ 13 km y una más a ≈ 0,8 km de la primera (un grupo); celdas 1.000 + índice."""
    U = _umbrales()
    infos, k = {}, 0
    for i in range(3):
        for j in range(3):
            lat = -33.10 - 0.12 * i - 0.011 * ((i + 2 * j) % 3)
            lon = -70.90 + 0.12 * j + 0.009 * ((2 * i + j) % 3)
            codigo = f"{330000 + k:06d}"
            infos[codigo] = _info(codigo, lat, lon, 300.0 + 900.0 * (lon + 70.9) + 60.0 * i, 1000 + k)
            k += 1
    primero = infos["330000"]
    infos["330009"] = _info("330009", primero.lat - 0.005, primero.lon + 0.006, primero.z_s + 12.0, 1009)
    grupos = particiones.grupos_mismo_sitio(infos, U)
    codigos = sorted(infos)
    bloques = particiones.bloque(np.array([infos[c].lat for c in codigos]), np.array([infos[c].lon for c in codigos]), U)
    return {c: dataclasses.replace(infos[c], grupo=grupos.get(c, infos[c].grupo), bloque=str(b))
            for c, b in zip(codigos, bloques)}


def _estaticos_estaciones(infos: dict) -> pd.DataFrame:
    """``ESQUEMA_ESTATICAS_CELDA_C`` de las celdas de las estaciones (TIP-22), con un TPI truncado."""
    rng = np.random.default_rng(_umbrales().a("SEMILLA"))
    filas = []
    for k, c in enumerate(sorted(infos)):
        info = infos[c]
        fr = rng.dirichlet(np.ones(len(tipos.LULC)))
        filas.append({"celda": int(info.celda), "z_media": info.z_s, "z_poblada": info.z_s, "z_poblada_es_media": True,
                      "frac_dato": 1.0, "tpi1": float(rng.normal(0, 20)), "tpi5": float(rng.normal(0, 60)),
                      "tpi1_truncado": k == 3, "tpi5_truncado": False, "pendiente_deg": float(rng.uniform(1, 15)),
                      "log_dist_costa": float(np.log1p(60 + 90 * (info.lon + 71.0))),
                      **{col: float(fr[i]) for i, col in enumerate(tipos.LULC)}, "lat": info.lat,
                      "macrozona_cod": 2, "cod_comuna": 13101,
                      tipos.COLUMNA_Z_E5L: info.z_s - 120.0 + 35.0 * np.sin(k)})
    esquema = tipos.ESQUEMA_ESTATICAS_CELDA_C
    return pd.DataFrame(filas, columns=list(esquema)).astype(dict(esquema))


def _fondo_estacion(k: int, z: float, h: np.ndarray) -> dict:
    """El fondo sintético de una estación (°C, hPa, m/s), con Td_F ≤ T_F y una amplitud diaria que cambia de un día a
    otro y entre estaciones (si fuera constante, C la estandarizaría a 0 y no se vería en las pruebas)."""
    hora = h % 24
    doy = (h // 24) % 365
    amplitud = 5 * (1 + 0.3 * np.sin(2 * np.pi * doy / 45) + 0.05 * k)
    T = 15 + 6 * np.cos(2 * np.pi * (doy - 20) / 365.25) + amplitud * np.cos(2 * np.pi * (hora - 19) / 24) \
        - 0.005 * z + 0.3 * k
    return {"T_F": T, "Td_F": T - 4 - 2 * np.cos(2 * np.pi * (hora - 19) / 24) ** 2,
            "p_F": numerico.p_std(z) + 2.0 * np.sin(h / 50.0), "u_F": 1.5 * np.sin(2 * np.pi * hora / 24) + 0.1 * k,
            "v_F": 0.5 + 0.2 * np.cos(h / 30.0)}


def _clima_estado(tabla: pd.DataFrame, h: np.ndarray) -> dict:
    """{variable: 12 × 24} de una estación: las medias por mes y hora UTC de su estado de C (TIP-17)."""
    est = candidatos.estado_c(tabla, h)
    mes = (_EPOCA + h.astype("timedelta64[h]")).astype("datetime64[M]").astype(np.int64) % 12
    celda = mes * 24 + h % 24
    salida = {}
    for v in tipos.VARIABLES_CLIMA_ESTADO:
        ok = np.isfinite(est[v])
        suma = np.bincount(celda[ok], weights=est[v][ok], minlength=288)
        n = np.bincount(celda[ok], minlength=288)
        salida[v] = np.where(n > 0, suma / np.maximum(n, 1), np.nan).reshape(12, 24)
    return salida


def _residuos(infos: dict, h: np.ndarray) -> dict:
    """Residuos sintéticos por estación en sus horas observadas (sin una de cada 11, para que B interpole)."""
    rng = np.random.default_rng(_umbrales().a("SEMILLA") + 1)
    hora = h % 24
    mes = (_EPOCA + h.astype("timedelta64[h]")).astype("datetime64[M]").astype(np.int64) % 12 + 1
    salida = {}
    for k, c in enumerate(sorted(infos)):
        b = 1.0 + 0.8 * (infos[c].lat + 33.2) + 0.4 * np.cos(2 * np.pi * (mes - 1) / 12) \
            + 0.4 * np.cos(2 * np.pi * (hora - 15) / 24)
        n = h.size
        r = {"T": b + rng.normal(0, 0.6, n), "Td": 0.5 * b + rng.normal(0, 0.8, n),
             "u": 0.3 + 0.2 * np.sin(2 * np.pi * hora / 24) + rng.normal(0, 0.5, n), "v": -0.2 + rng.normal(0, 0.5, n),
             "p": 0.002 + 0.0005 * np.cos(2 * np.pi * hora / 24) + rng.normal(0, 0.0004, n)}
        invalida = rng.random(n) < 0.05
        for v in r:
            r[v][invalida] = NAN
        observada = (h + k) % 11 != 5
        salida[c] = (h[observada], {v: x[observada] for v, x in r.items()})
    return salida


@lru_cache(maxsize=None)
def _datos() -> tipos.DatosCompetencia:
    """``DatosCompetencia`` como la armaría ``orquestacion`` (2010-2011, horaria)."""
    U = _umbrales()
    infos = _red()
    h = np.arange(_h("2010-01-01T00"), _h("2012-01-01T00"), dtype=np.int64)
    residuos, tramos = {}, []
    for c, (hc, r) in _residuos(infos, h).items():
        residuos[c], tr = candidatos.residuos_estacion(c, hc, r, U)
        tramos.append(tr)
    puntos, clima = {}, {}
    for k, c in enumerate(sorted(infos)):
        puntos[c] = fondo_era5l.tabla_puntos(h, _fondo_estacion(k, infos[c].z_s, h))
        clima[c] = _clima_estado(puntos[c], h)
    estaticos = _estaticos_estaciones(infos)
    filas = {"C": candidatos.filas_c(residuos, estaticos, puntos, U, infos=infos),
             "C_est": candidatos.filas_c(residuos, estaticos, clima, U, infos=infos, climatologico=True)}
    return tipos.DatosCompetencia(residuos=residuos, climatologias=candidatos.climatologias_a(residuos, U),
                                  tramos=pd.concat(tramos, ignore_index=True), filas_c=filas, estaticos=estaticos,
                                  estaciones=infos, pliegues=(), puntos_e5l=puntos, clima_estado=clima)


PRUEBA = ("330004", "330007")


def _externo() -> tipos.Pliegue:
    infos = _red()
    return tipos.Pliegue("manual", tipos.Particion.P1, PRUEBA, tuple(c for c in sorted(infos) if c not in PRUEBA))


def _insumos_de_estaciones(datos, codigos, h) -> dict:
    """Puntos, estáticos, fondo (A1: los float32 guardados) y clima del estado de unas estaciones en las horas h."""
    infos = datos.estaciones
    puntos = {"ids": np.array(codigos, dtype=object), "lat": [infos[c].lat for c in codigos],
              "lon": [infos[c].lon for c in codigos], "z": [infos[c].z_s for c in codigos]}
    estaticos = pd.concat([datos.estaticos[datos.estaticos["celda"] == infos[c].celda] for c in codigos],
                          ignore_index=True)
    columnas = [fondo_era5l.en_horas(datos.puntos_e5l[c], h) for c in codigos]
    fondo = {k: np.column_stack([col[k] for col in columnas]) for k in ("T_F", "Td_F", "u_F", "v_F", "amp_TF")}
    clima = {v: np.stack([datos.clima_estado[c][v] for c in codigos]) for v in tipos.VARIABLES_CLIMA_ESTADO}
    return {"puntos": puntos, "estaticos": estaticos, "fondo": fondo, "clima": clima,
            "celdas": np.array([infos[c].celda for c in codigos], dtype=np.int64)}


def _correccion(cand, puntos, h, datos, insumos=None, **kw):
    insumos = insumos or {}
    return producto.correccion(cand, kw.pop("hiper", _hiper(cand)), puntos, h, datos, umbrales=_umbrales(),
                               uso=kw.pop("uso", USO_DE[cand]), fondo=insumos.get("fondo"),
                               estaticos=insumos.get("estaticos"), clima=insumos.get("clima"),
                               celdas=kw.pop("celdas", insumos.get("celdas")), **kw)


def _puntos_sueltos(n: int = 7) -> dict:
    """Puntos cualesquiera cerca de la red (celdas o píxeles), con sus estáticos, fondo y clima sintéticos."""
    rng = np.random.default_rng(_umbrales().a("SEMILLA") + 2)
    lat = -33.1 - 0.25 * rng.random(n)
    lon = -70.9 + 0.25 * rng.random(n)
    z = 300.0 + 800.0 * rng.random(n)
    base = _estaticos_estaciones(_red())
    estaticos = base.iloc[np.arange(n) % len(base)].reset_index(drop=True)
    estaticos["celda"] = np.arange(5000, 5000 + n, dtype=np.int64)
    estaticos["z_media"] = z
    h = _horas_mes(2011, 3)
    F = {k: np.column_stack([_fondo_estacion(i, z[i], h)[k] for i in range(n)]) for k in ("T_F", "Td_F", "u_F", "v_F")}
    hora = np.arange(24)
    clima = {"T": np.stack([np.tile(12 + 5 * np.cos(2 * np.pi * (hora - 19) / 24), (12, 1)) + i for i in range(n)]),
             "T_menos_Td": np.full((n, 12, 24), 5.0), "rapidez": np.full((n, 12, 24), 2.0),
             "amp": np.full((n, 12, 24), 9.0)}
    return {"puntos": {"ids": estaticos["celda"].to_numpy(), "lat": lat, "lon": lon, "z": z}, "estaticos": estaticos,
            "fondo": F, "clima": clima, "h": h}


# ---------------------------------------------------------------------------
# Píxeles y celdas sintéticos con un mes ERA5-Land
# ---------------------------------------------------------------------------
@lru_cache(maxsize=None)
def _pixeles():
    """6 × 6 píxeles de 0,1° sobre la red y un mes (2011-01) ERA5-Land sintético, leído en memoria."""
    cat = sintetico.catalogo_pixeles(-33.0, -71.0, 6, 6)
    pid = cat.pixel_id.to_numpy(np.int64)
    a = np.round((-33.0 - cat.latitude.to_numpy()) / 0.1)
    b = np.round((cat.longitude.to_numpy() + 71.0) / 0.1)
    z_pix = 300.0 + 150.0 * a + 120.0 * b
    t = sintetico.horas_del_mes(2011, 1)
    h = (t.astype("datetime64[h]") - _EPOCA).astype(np.int64)
    hora = (h % 24)[:, None]
    t2m = 290.0 + 5.0 * np.cos(2 * np.pi * (hora - 19) / 24) - 0.0065 * z_pix[None, :] + 0.2 * a[None, :]
    campos = {"t2m": t2m, "d2m": t2m - 6.0 - 0.5 * b[None, :],
              "sp": numerico.p_std(z_pix)[None, :] * 100.0 + 200.0 * np.sin(h / 5.0)[:, None],
              "u10": 2.0 * np.sin(2 * np.pi * hora / 24) + 0.1 * b[None, :],
              "v10": -1.0 + 0.5 * np.cos(2 * np.pi * hora / 24) + 0.0 * a[None, :],
              "tp": np.zeros((h.size, pid.size))}
    with tempfile.TemporaryDirectory() as tmp:
        mes = fondo_era5l.leer_mes(sintetico.mes_era5_netcdf(Path(tmp) / "era5land_201101.nc", campos, t, pid))
    z_tabla = pd.DataFrame({"pixel_id": pid, "z_e5l": z_pix})
    op = fondo_era5l.operador_pixeles(pid, cat, pid, z_tabla)
    puntos = {"ids": pid, "lat": cat.latitude.to_numpy(), "lon": cat.longitude.to_numpy(), "z": np.asarray(op.z)}
    return types.SimpleNamespace(cat=cat, pid=pid, z_tabla=z_tabla, mes=mes, op=op, puntos=puntos, campos=campos)


@lru_cache(maxsize=None)
def _celdas():
    """24 celdas de ``sintetico.grilla`` sobre la red: su operador, sus estáticos con ``z_e5l`` y el clima del estado."""
    U = _umbrales()
    px = _pixeles()
    g = sintetico.grilla(24, 2, lat0=-33.15, lon0=-70.85)
    celdas = g["celdas"].sort_values("celda").reset_index(drop=True)
    est = g["estaticas_mc"].set_index("celda").loc[celdas["celda"]].reset_index()
    lat, lon = celdas["lat"].to_numpy(np.float64), celdas["lon"].to_numpy(np.float64)
    z = est["z_media"].to_numpy(np.float64)
    op = fondo_era5l.operador(lat, lon, z, px.cat, px.pid, px.z_tabla, U, ids=celdas["celda"].to_numpy())
    z_de = dict(zip(px.pid.tolist(), px.z_tabla["z_e5l"].tolist()))
    pix, w = np.asarray(op.pix), np.asarray(op.w)
    z_e5l = np.array([sum(w[i, k] * z_de[int(pix[i, k])] for k in range(pix.shape[1]) if pix[i, k] >= 0)
                      for i in range(len(lat))])
    est[tipos.COLUMNA_Z_E5L] = z_e5l
    esquema = tipos.ESQUEMA_ESTATICAS_CELDA_C
    estaticos = est[list(esquema)].astype(dict(esquema))
    acumulador = fondo_era5l.acumulador_estado(px.pid)
    fondo_era5l.climatologias_estado(acumulador, px.mes)
    tabla = fondo_era5l.tabla_clima_estado(acumulador)
    clima = fondo_era5l.clima_en_puntos(tabla, op, U)
    puntos = {"ids": celdas["celda"].to_numpy(), "lat": lat, "lon": lon, "z": z}
    return types.SimpleNamespace(puntos=puntos, op=op, estaticos=estaticos, clima=clima, tabla_clima=tabla)


GANADOR = {Grupo.T_TD.value: "A", Grupo.U_V.value: "B", Grupo.P.value: "AB"}
HIPER_GANADOR = {"T": H_A, "Td": H_A, "u": H_B, "v": H_B, "p": (H_A, H_B)}
HUELLAS = {"ERA5L/era5land_201101.nc": "a" * 64, "LOCAL/meteo_combinada/v1/decision.json": "0123456789abcdef" * 4}


@lru_cache(maxsize=None)
def _producto_pixeles():
    px = _pixeles()
    return producto.producto_mes(px.mes, px.op, px.puntos, GANADOR, HIPER_GANADOR, _datos(), umbrales=_umbrales(),
                                 uso=Uso.AMBIENTAL)


def _bytes_01deg(**cambios) -> bytes:
    px = _pixeles()
    campos, _ = _producto_pixeles()
    kw = {"uso": Uso.AMBIENTAL, "ganador": GANADOR, "huellas": HUELLAS, **cambios}
    huellas = kw.pop("huellas")
    return producto.mes_01deg(campos, px.pid, px.mes.tiempos, _umbrales(), huellas, **kw)


def _abrir(datos: bytes):
    return producto._netcdf4().Dataset("releido.nc", mode="r", memory=datos)


def _validos(n: int) -> dict:
    """Un producto que cabe en int16 (p = 900 hPa: con p = 0 desbordaría la presión)."""
    x = {v: np.zeros(n) for v in VARIABLES}
    x["p"] = np.full(n, 900.0)
    return x


def _media_escala(U, v: str) -> float:
    return float(U.a(producto.FORMATO_IDS[v][0])) / 2


# ---------------------------------------------------------------------------
# S15 (§9): ida y vuelta int16
# ---------------------------------------------------------------------------
class PruebasS15(unittest.TestCase):
    def test_s15_ida_y_vuelta_int16_en_los_extremos(self):
        """p de 470 y 1.085 hPa; T de −60 y 50 °C; u de ±60 m/s (y Td y v igual): el int16 de §8 los representa y la
        ida y vuelta cae a ≤ media escala; los valores salen del Anexo A (fila «Formato»), no del código."""
        U = _umbrales()
        p_bajo, p_alto, t_bajo, t_alto, u_max = constantes.valor("S15_EXTREMOS")
        formato, relleno = producto.formato_int16(U)
        self.assertEqual(relleno, U.a("FMT_RELLENO"))
        self.assertEqual(formato, {"T": (U.a("FMT_ESC_T"), 0.0), "Td": (U.a("FMT_ESC_T"), 0.0),
                                   "u": (U.a("FMT_ESC_UV"), 0.0), "v": (U.a("FMT_ESC_UV"), 0.0),
                                   "p": (U.a("FMT_ESC_P"), float(U.a("FMT_DESP_P")))})
        campos = {"T": [t_bajo, t_alto, 0.0, 12.345], "Td": [t_bajo, t_alto, -0.005, 7.777],
                  "u": [-u_max, u_max, 0.0, 1.234], "v": [-u_max, u_max, 0.015, -3.21],
                  "p": [p_bajo, p_alto, 800.0, 1013.25]}
        x = {v: np.array(campos[v], dtype=np.float64) for v in VARIABLES}
        enteros = producto.codificar_int16(x, U)
        vuelta = producto.decodificar_int16(enteros, U)
        for v in VARIABLES:
            with self.subTest(variable=v):
                self.assertEqual(enteros[v].dtype, np.int16)
                self.assertFalse((enteros[v] == relleno).any())
                error = np.abs(vuelta[v] - x[v])
                self.assertTrue(np.all(error <= _media_escala(U, v) + 4 * np.spacing(np.abs(x[v]))), error)
                self.assertTrue(np.isfinite(vuelta[v]).all())
        # Los extremos caen en enteros exactos de la escala.
        self.assertEqual(int(enteros["p"][0]), round((p_bajo - U.a("FMT_DESP_P")) / U.a("FMT_ESC_P")))
        self.assertEqual(int(enteros["T"][0]), round(t_bajo / U.a("FMT_ESC_T")))
        self.assertEqual(int(enteros["u"][1]), round(u_max / U.a("FMT_ESC_UV")))

    def test_s15_cobertura_de_la_presion_145_a_1455(self):
        """§8: con escala 0,02 y desplazamiento 800, p cubre 145-1.455 hPa; fuera de eso, o en el relleno, es un error
        con aviso (no un desborde silencioso), igual que T, u y los infinitos."""
        U = _umbrales()
        base = {v: np.zeros(3) for v in VARIABLES}
        base["p"] = np.array([145.0, 1455.0, 144.66])
        vuelta = producto.decodificar_int16(producto.codificar_int16(base, U), U)
        self.assertTrue(np.all(np.abs(vuelta["p"] - base["p"]) <= _media_escala(U, "p") + 1e-9))
        malos = {"p": (1455.4, 144.64, 2000.0, -np.inf, np.inf), "T": (327.68, -327.68, 400.0, np.inf),
                 "Td": (-500.0,), "u": (327.7, -np.inf), "v": (-327.68,)}
        for v, valores in malos.items():
            for valor in valores:
                with self.subTest(variable=v, valor=valor):
                    caso = _validos(2)
                    caso[v] = np.array([caso[v][0], valor])
                    with self.assertRaises(producto.DesbordeInt16):
                        producto.codificar_int16(caso, U)
        # El borde que sí cabe: −327,67 °C es −32.767; −327,68 caería en el relleno.
        caso = _validos(1)
        caso["T"] = np.array([-327.67])
        self.assertEqual(int(producto.codificar_int16(caso, U)["T"][0]), -32767)

    def test_s15_nan_es_relleno_y_vuelve_a_nan(self):
        U = _umbrales()
        x = {v: np.array([[NAN, 1.0], [2.0, NAN]]) for v in VARIABLES}
        x["p"] = np.array([[NAN, 900.0], [1000.0, NAN]])
        enteros = producto.codificar_int16(x, U)
        vuelta = producto.decodificar_int16(enteros, U)
        for v in VARIABLES:
            self.assertEqual(enteros[v].shape, (2, 2))
            self.assertTrue(np.array_equal(enteros[v] == U.a("FMT_RELLENO"), np.isnan(x[v])))
            self.assertTrue(np.array_equal(np.isnan(vuelta[v]), np.isnan(x[v])))

    def test_s15_redondeo_al_azar_dentro_de_media_escala(self):
        """Valores al azar en todo el rango útil: error ≤ media escala, y decodificar ∘ codificar es idempotente."""
        U = _umbrales()
        rng = np.random.default_rng(U.a("SEMILLA"))
        rangos = {"T": (-60, 50), "Td": (-80, 40), "u": (-60, 60), "v": (-60, 60), "p": (470, 1085)}
        x = {v: rng.uniform(*rangos[v], size=(50, 40)) for v in VARIABLES}
        uno = producto.decodificar_int16(producto.codificar_int16(x, U), U)
        dos = producto.decodificar_int16(producto.codificar_int16(uno, U), U)
        for v in VARIABLES:
            self.assertLessEqual(float(np.abs(uno[v] - x[v]).max()), _media_escala(U, v) * (1 + 1e-9))
            self.assertTrue(np.array_equal(uno[v], dos[v]))

    def test_formato_de_umbrales_no_del_codigo(self):
        """Con otros valores en el objeto de umbrales cambia el int16: ningún número del formato está escrito a mano."""
        U = _umbrales()
        otros = {"FMT_ESC_T": 0.1, "FMT_ESC_UV": 0.05, "FMT_ESC_P": 0.5, "FMT_DESP_P": 1000, "FMT_RELLENO": 32767}
        falso = types.SimpleNamespace(a=lambda i: otros[i] if i in otros else U.a(i))
        x = {v: np.array([10.0]) for v in VARIABLES}
        x["p"] = np.array([1100.0])
        e = producto.codificar_int16(x, falso)
        self.assertEqual({v: int(e[v][0]) for v in VARIABLES}, {"T": 100, "Td": 100, "u": 200, "v": 200, "p": 200})
        x["T"] = np.array([NAN])
        self.assertEqual(int(producto.codificar_int16(x, falso)["T"][0]), 32767)
        with self.assertRaises(producto.DesbordeInt16):           # 3.276,7 °C caería en el relleno 32.767
            producto.codificar_int16({**x, "T": np.array([3276.7])}, falso)

    def test_int16_rechaza_claves_ajenas_tipos_y_faltantes(self):
        """R nunca se guarda: una clave que no es del producto es un error; HR, rapidez y dirección se aceptan pero no
        se codifican; decodificar exige int16."""
        U = _umbrales()
        x = _validos(2)
        e = producto.codificar_int16({**x, "HR": np.ones(2), "rapidez": np.ones(2), "direccion": np.ones(2)}, U)
        self.assertEqual(sorted(e), sorted(VARIABLES))
        for malo in ({**x, "R_T": np.zeros(2)}, {k: x[k] for k in VARIABLES if k != "p"}, [1, 2]):
            with self.subTest(malo=type(malo).__name__), self.assertRaises(producto.ErrorProducto):
                producto.codificar_int16(malo, U)
        with self.assertRaises(producto.ErrorProducto):
            producto.decodificar_int16({**e, "T": e["T"].astype(np.int32)}, U)
        with self.assertRaises(producto.ErrorProducto):
            producto.decodificar_int16({k: e[k] for k in VARIABLES if k != "u"}, U)


# ---------------------------------------------------------------------------
# Campos del producto
# ---------------------------------------------------------------------------
class PruebasCampos(unittest.TestCase):
    def _F_R(self):
        rng = np.random.default_rng(_umbrales().a("SEMILLA"))
        forma = (6, 5)
        T = rng.uniform(-10, 30, forma)
        F = {"T_F": T, "Td_F": T - rng.uniform(0, 10, forma), "p_F": rng.uniform(600, 1010, forma),
             "u_F": rng.normal(0, 3, forma), "v_F": rng.normal(0, 3, forma), "renormalizada": np.zeros(forma, bool)}
        R = {"R_T": rng.normal(0, 1, forma), "R_Td": rng.normal(0, 2, forma), "R_u": rng.normal(0, 1, forma),
             "R_v": rng.normal(0, 1, forma), "R_p": rng.normal(0, 0.002, forma)}
        R["R_Td"][0, 0] = 20.0                                       # Td_F + R_Td > T: Td = T y HR = 100
        R["R_T"][1, 1] = NAN
        return F, R

    def test_campos_con_producto_desde_y_derivadas(self):
        """§3 y §4.1: T, Td, u, v y p son los de ``fondo_era5l.producto_desde`` (bit a bit); HR por Magnus sobre agua
        recortada en [0, 100]; rapidez √(u² + v²); Td ≤ T; NaN donde R no es finito."""
        F, R = self._F_R()
        c = producto.campos(F, R)
        esperado = fondo_era5l.producto_desde(F, R)
        self.assertEqual(sorted(c), sorted([*VARIABLES, "HR", "rapidez", "direccion"]))
        for v in VARIABLES:
            self.assertEqual(c[v].tobytes(), esperado[v].tobytes(), v)
        self.assertTrue(np.array_equal(c["p"], F["p_F"] * np.exp(R["R_p"])))
        with np.errstate(invalid="ignore"):
            self.assertTrue(np.all((c["Td"] <= c["T"]) | np.isnan(c["T"])))
        lo, hi = constantes.valor("HR_PRODUCTO_RECORTE")
        self.assertTrue(np.array_equal(c["HR"], np.clip(numerico.hr_desde(c["T"], c["Td"]), lo, hi), equal_nan=True))
        self.assertEqual(float(c["HR"][0, 0]), 100.0)
        self.assertTrue(np.isnan(c["HR"][1, 1]) and np.isnan(c["T"][1, 1]))
        finita = np.isfinite(c["HR"])
        self.assertTrue(np.all((c["HR"][finita] >= 0) & (c["HR"][finita] <= 100)))
        self.assertTrue(np.array_equal(c["rapidez"], np.hypot(c["u"], c["v"])))

    def test_hr_saturada_recortada_en_100(self):
        """H3 (§3, «recortada en [0, 100]»): en una malla de puntos saturados (Td = T por el mín de §4.1), Magnus da a
        veces 100 + ε por redondeo; ``campos`` la deja en [0, 100] (y la prueba comprueba que el caso existe)."""
        T = np.linspace(-50.0, 50.0, 2001)[None, :]
        F = {"T_F": T, "Td_F": T - 1.0, "p_F": np.full(T.shape, 900.0), "u_F": np.zeros(T.shape),
             "v_F": np.zeros(T.shape)}
        R = {c: np.zeros(T.shape) for c in producto.CLAVE_R.values()}
        R["R_Td"] = np.full(T.shape, 5.0)                            # Td_F + R_Td > T: Td = T
        c = producto.campos(F, R)
        self.assertTrue(np.array_equal(c["Td"], c["T"]))
        crudo = numerico.hr_desde(c["T"], c["Td"])
        self.assertGreater(int((crudo > 100).sum()), 0, "la malla no tiene casos de 100 + ε: la prueba no vería nada")
        lo, hi = constantes.valor("HR_PRODUCTO_RECORTE")
        self.assertTrue(np.all((c["HR"] >= lo) & (c["HR"] <= hi)))
        self.assertTrue(np.all(c["HR"][crudo > 100] == hi))
        self.assertTrue(np.array_equal(c["HR"][crudo <= 100], crudo[crudo <= 100]))

    def test_direccion_es_la_de_mc28(self):
        """MC-28: el ángulo ``arctan2(u, v)`` de ``el_*`` (``_features.py``) en grados de [0, 360), «hacia»: 90 hacia el
        este, 180 hacia el sur; calma 0 (como arctan2(0, 0)); NaN si u o v no es finito."""
        u = np.array([0.0, 1.0, 0.0, -1.0, 0.0, 3.0, -2.0, NAN, np.inf, -1e-300])
        v = np.array([1.0, 0.0, -1.0, 0.0, 0.0, 3.0, -2.0, 1.0, 1.0, 1.0])
        d = producto.direccion_hacia(u, v)
        self.assertEqual(d[:7].tolist(), [0.0, 90.0, 180.0, 270.0, 0.0, 45.0, 225.0])
        self.assertTrue(np.isnan(d[7]) and np.isnan(d[8]))
        self.assertTrue(np.all((d[np.isfinite(d)] >= 0) & (d[np.isfinite(d)] < 360)))
        ang = np.arctan2(u, v)                                     # el_wdir_sin y el_wdir_cos de _features.py
        ok = np.isfinite(d)
        np.testing.assert_allclose(np.sin(np.radians(d[ok])), np.sin(ang[ok]), atol=1e-12)
        np.testing.assert_allclose(np.cos(np.radians(d[ok])), np.cos(ang[ok]), atol=1e-12)

    def test_campos_rechaza_R_incompleta_o_ajena(self):
        F, R = self._F_R()
        for malo in ({k: R[k] for k in R if k != "R_p"}, {**R, "R_x": R["R_T"]}, [R["R_T"]]):
            with self.subTest(claves=sorted(malo) if isinstance(malo, dict) else "lista"):
                with self.assertRaises(producto.ErrorProducto):
                    producto.campos(F, malo)
        with self.assertRaises(fondo_era5l.ErrorFondo):           # formas distintas: lo detecta producto_desde
            producto.campos(F, {**R, "R_T": R["R_T"][:, :2]})


# ---------------------------------------------------------------------------
# La corrección de cada candidato en un conjunto de puntos
# ---------------------------------------------------------------------------
class PruebasCorreccion(unittest.TestCase):
    def test_paridad_con_predecir_prueba_bit_a_bit(self):
        """En los puntos de dos estaciones de prueba, con el entrenamiento de su pliegue y los mismos hiperparámetros,
        ``correccion`` da, bit a bit, la corrección de ``candidatos.predecir_prueba`` en sus horas observadas del mes,
        en A, B, AB, C y C_est y en las cinco variables (PRO-5 a PRO-7): reutiliza ``candidatos`` sin cambiar ninguna
        cuenta, también el estado de C (copia con paridad) y el de C_est (con ``clima_en_horas``). Va dos veces: con el
        mismo θ en todas las variables y con un θ distinto en cada una (H1: así no pasa «el θ de T en todas»)."""
        U = _umbrales()
        datos = _datos()
        externo = _externo()
        h = _horas_mes(2011, 3)
        insumos = _insumos_de_estaciones(datos, PRUEBA, h)
        for caso, hiper_de in (("mismo θ", lambda c: _hiper(c)), ("θ por variable", lambda c: HIPER_POR_VARIABLE[c])):
            for cand in (Candidato.A, Candidato.B, Candidato.AB, Candidato.C, Candidato.C_EST):
                hiper = hiper_de(cand)
                R = _correccion(cand, insumos["puntos"], h, datos, insumos, entrenamiento=externo.entrenamiento,
                                hiper=hiper)
                self.assertEqual(sorted(R), sorted(producto.CLAVE_R.values()))
                for v in VARIABLES:
                    with self.subTest(caso=caso, candidato=cand.value, variable=v):
                        self._paridad(cand, v, hiper[v], externo, datos, U, h, R)

    def _paridad(self, cand, v, theta, externo, datos, U, h, R):
        pred = candidatos.predecir_prueba(cand, v, USO_DE[cand], theta, externo, datos, umbrales=U)
        pred = pred[(pred["h"] >= h[0]) & (pred["h"] <= h[-1])]
        for j, c in enumerate(PRUEBA):
            g = pred[pred["codigo"] == c]
            self.assertGreater(len(g), 600)
            mio = R[producto.CLAVE_R[v]][np.searchsorted(h, g["h"].to_numpy()), j]
            self.assertEqual(mio.tobytes(), g["correccion"].to_numpy(np.float64).tobytes())
            self.assertTrue(np.isfinite(mio).all())

    def test_lotes_de_puntos_no_cambian_ningun_bit(self):
        """PRO-2 (PED-6, S9): lotes de 1, 3 o el de omisión dan los mismos bits en los cinco candidatos."""
        datos = _datos()
        s = _puntos_sueltos(7)
        for cand in (Candidato.A, Candidato.B, Candidato.AB, Candidato.C, Candidato.C_EST):
            with self.subTest(candidato=cand.value):
                salidas = [_correccion(cand, s["puntos"], s["h"], datos, s, lote_puntos=t) for t in (1, 3, None)]
                for otra in salidas[1:]:
                    for clave in salidas[0]:
                        self.assertEqual(salidas[0][clave].tobytes(), otra[clave].tobytes(), clave)
                self.assertTrue(all(np.isfinite(x).all() for x in salidas[0].values()))
        otra = _correccion(Candidato.A, s["puntos"], s["h"], datos, s)          # S9: misma entrada, mismos bits
        self.assertEqual(otra["R_T"].tobytes(), _correccion(Candidato.A, s["puntos"], s["h"], datos, s)["R_T"].tobytes())

    def test_estado_de_c_es_la_formula_de_candidatos(self):
        """PRO-6 (PED-7): ``estado_c_puntos`` sobre los float32 de ``ESQUEMA_PUNTOS_E5L`` es ``candidatos.estado_c``,
        bit a bit; y el clima llevado a las horas con ``clima_en_horas`` es ``candidatos.estado_c_est`` (PRO-7)."""
        datos = _datos()
        h = _horas_mes(2011, 7)
        for c in ("330001", "330009"):
            tabla = datos.puntos_e5l[c]
            esperado = candidatos.estado_c(tabla, h)
            F = fondo_era5l.en_horas(tabla, h)
            mio = producto.estado_c_puntos(F["T_F"], F["Td_F"], F["u_F"], F["v_F"], F["amp_TF"])
            esperado_c_est = candidatos.estado_c_est(datos.clima_estado[c], h)
            cubo = {v: datos.clima_estado[c][v][None, :, :] for v in tipos.VARIABLES_CLIMA_ESTADO}
            mio_c_est = fondo_era5l.clima_en_horas(cubo, h)
            for v in candidatos.ESTADO_C:
                self.assertEqual(mio[v].tobytes(), esperado[v].tobytes(), v)
                self.assertEqual(mio_c_est[v][:, 0].tobytes(), esperado_c_est[v].tobytes(), v)

    def test_lejos_de_las_estaciones_vuelve_al_fondo(self):
        """§4.2: a más de 3L de toda estación el núcleo da R = 0 exacto (no NaN): el producto es el fondo."""
        datos = _datos()
        h = _horas_mes(2011, 2)
        lejos = {"lat": [-40.0, -20.0], "lon": [-72.0, -70.0], "z": [100.0, 3000.0]}
        for cand in (Candidato.A, Candidato.B, Candidato.AB):
            R = _correccion(cand, lejos, h, datos)
            for clave, x in R.items():
                self.assertTrue(np.all(x == 0.0), f"{cand.value} {clave}")

    def test_solo_las_variables_del_ganador_y_grupos_enteros(self):
        """PRO-3: se calculan las variables de ``hiper``; los grupos van enteros (T con Td, u con v) y u y v con el
        mismo θ (MC-43, P66); un θ de otro tipo o una variable desconocida es un error."""
        datos = _datos()
        s = _puntos_sueltos(3)
        R = _correccion(Candidato.B, s["puntos"], s["h"], datos, s, hiper={"u": H_B, "v": H_B})
        self.assertEqual(sorted(R), ["R_u", "R_v"])
        R = _correccion(Candidato.C, s["puntos"], s["h"], datos, s, hiper={"p": 1.0})
        self.assertEqual(sorted(R), ["R_p"])
        malos = [(Candidato.A, {"T": H_A}), (Candidato.A, {"u": H_A, "v": H_B}), (Candidato.C, {"u": 1.0, "v": 10.0}),
                 (Candidato.A, {"T": 10.0, "Td": 10.0}), (Candidato.C, {"p": H_A}), (Candidato.C, {"p": True}),
                 (Candidato.C, {"p": -1.0}), (Candidato.AB, {"p": H_A}), (Candidato.A, {"x": H_A}), (Candidato.A, {})]
        for cand, hiper in malos:
            with self.subTest(candidato=cand.value, hiper=repr(hiper)), self.assertRaises(producto.ErrorProducto):
                _correccion(cand, s["puntos"], s["h"], datos, s, hiper=hiper)

    def test_usos_de_cada_candidato(self):
        """PRO-9 (§6.1, §4.7, §6.4): C_est sólo en lo crónico y C nunca en lo crónico; A, B y AB en los tres."""
        datos = _datos()
        s = _puntos_sueltos(2)
        for cand, uso in ((Candidato.C_EST, Uso.AMBIENTAL), (Candidato.C_EST, Uso.AGUDO), (Candidato.C, Uso.CRONICO),
                          (Candidato.A, "otro")):
            with self.subTest(candidato=cand.value, uso=str(uso)), self.assertRaises(producto.ErrorProducto):
                _correccion(cand, s["puntos"], s["h"], datos, s, uso=uso)
        for uso in Uso:
            self.assertEqual(len(_correccion(Candidato.AB, s["puntos"], s["h"], datos, s, uso=uso)), 5)
        with self.assertRaises(producto.ErrorProducto):              # un candidato desconocido (PRO-17)
            producto.correccion("D", {"T": H_A, "Td": H_A}, s["puntos"], s["h"], datos, umbrales=_umbrales(),
                                uso="agudo")
        with self.assertRaises(producto.ErrorProducto):              # datos de otro tipo
            producto.correccion("A", {"T": H_A, "Td": H_A}, s["puntos"], s["h"], {}, umbrales=_umbrales(), uso="agudo")

    def test_lote_de_horas_de_un_mes(self):
        """PRO-1 (MC-37, H5): horas enteras y consecutivas desde la primera hora de un mes UTC; un mes que queda corto
        al final vale; un hueco, un comienzo a mitad de mes o dos meses no (en A y en C)."""
        datos = _datos()
        s = _puntos_sueltos(2)
        parcial = s["h"][:200]
        self.assertEqual(_correccion(Candidato.A, s["puntos"], parcial, datos)["R_T"].shape, (200, 2))
        dos_meses = np.arange(_h("2011-03-31T20"), _h("2011-04-01T04"))
        con_hueco = np.delete(s["h"], 50)                              # H5: la amplitud del día daría NaN sin aviso
        for malo in (dos_meses, s["h"][::-1], s["h"].astype(np.float64), s["h"][:0], np.array([s["h"][0]] * 2),
                     s["h"].reshape(-1, 24), con_hueco, s["h"][24:], s["h"][::3]):
            with self.subTest(forma=malo.shape, tipo=str(malo.dtype)), self.assertRaises(producto.ErrorProducto):
                _correccion(Candidato.A, s["puntos"], malo, datos)
        recortado = {**s, "fondo": {k: x[:200] for k, x in s["fondo"].items()}}
        self.assertEqual(_correccion(Candidato.C, s["puntos"], parcial, datos, recortado)["R_T"].shape, (200, 2))
        hueco = {**s, "fondo": {k: np.delete(x, 50, axis=0) for k, x in s["fondo"].items()}}
        with self.assertRaises(producto.ErrorProducto):
            _correccion(Candidato.C, s["puntos"], con_hueco, datos, hueco)

    def test_insumos_de_c_y_c_est(self):
        """PRO-6 a PRO-8: C sin fondo, con Td_F > T_F o con otra forma; C y C_est sin estáticos, con otro largo o
        con otro esquema; C_est sin clima o con otra forma: todos son errores."""
        datos = _datos()
        s = _puntos_sueltos(3)
        sin = lambda **kw: {**s, **kw}                                          # noqa: E731
        Td_mal = {**s["fondo"], "Td_F": s["fondo"]["T_F"] + 0.5}
        casos = [(Candidato.C, sin(fondo=None)), (Candidato.C, sin(fondo={**s["fondo"], "u_F": s["fondo"]["u_F"][:, :2]})),
                 (Candidato.C, sin(fondo={k: x for k, x in s["fondo"].items() if k != "v_F"})),
                 (Candidato.C, sin(fondo=Td_mal)), (Candidato.C, sin(fondo={**s["fondo"], "T_F": s["fondo"]["T_F"][:5]})),
                 (Candidato.C, sin(estaticos=None)), (Candidato.C, sin(estaticos=s["estaticos"].iloc[:2])),
                 (Candidato.C, sin(estaticos=s["estaticos"].drop(columns=[tipos.COLUMNA_Z_E5L]))),
                 (Candidato.C, sin(estaticos=s["estaticos"].astype({"z_media": "float32"}))),
                 (Candidato.C, sin(estaticos=s["estaticos"].iloc[::-1].reset_index(drop=True))),   # H6: otro orden
                 (Candidato.C_EST, sin(estaticos=s["estaticos"].assign(celda=np.arange(3, dtype=np.int64)))),
                 (Candidato.C, sin(celdas=["a", "b", "c"])), (Candidato.C, sin(celdas=[5000, 5001])),
                 (Candidato.C_EST, sin(clima=None)), (Candidato.C_EST, sin(estaticos=None)),
                 (Candidato.C_EST, sin(clima={**s["clima"], "amp": s["clima"]["amp"][:, :6]})),
                 (Candidato.C_EST, sin(clima={k: x for k, x in s["clima"].items() if k != "rapidez"}))]
        for cand, insumos in casos:
            with self.subTest(candidato=cand.value), self.assertRaises(producto.ErrorProducto):
                _correccion(cand, s["puntos"], s["h"], datos, insumos)
        # Un estático NaN deja NaN sólo en su punto (C no predice sin diseño finito, CAN-10).
        est = s["estaticos"].copy()
        est.loc[1, "pendiente_deg"] = NAN
        R = _correccion(Candidato.C, s["puntos"], s["h"], datos, sin(estaticos=est))
        self.assertTrue(np.isnan(R["R_T"][:, 1]).all() and np.isfinite(R["R_T"][:, [0, 2]]).all())

    def test_entrenamiento_de_produccion(self):
        """PRO-4: por omisión, todas las estaciones que no están excluidas; una excluida o desconocida en
        ``entrenamiento`` es un error; sin estaciones, también."""
        datos = _datos()
        s = _puntos_sueltos(2)
        todas = tuple(sorted(datos.estaciones))
        por_omision = _correccion(Candidato.B, s["puntos"], s["h"], datos)
        explicita = _correccion(Candidato.B, s["puntos"], s["h"], datos, entrenamiento=todas[::-1])
        self.assertEqual(por_omision["R_T"].tobytes(), explicita["R_T"].tobytes())
        excluida = dataclasses.replace(datos.estaciones["330003"], excluida=True, motivo="k3")
        otros = dataclasses.replace(datos, estaciones={**datos.estaciones, "330003": excluida})
        sin_ella = _correccion(Candidato.B, s["puntos"], s["h"], otros)
        a_mano = _correccion(Candidato.B, s["puntos"], s["h"], datos,
                             entrenamiento=[c for c in todas if c != "330003"])
        self.assertEqual(sin_ella["R_T"].tobytes(), a_mano["R_T"].tobytes())
        for malo in (["330003"], ["999999"], ["330001", "330001"], "330001", []):
            datos_ = otros if malo == ["330003"] else datos
            with self.subTest(entrenamiento=malo), self.assertRaises(producto.ErrorProducto):
                _correccion(Candidato.B, s["puntos"], s["h"], datos_, entrenamiento=malo)


# ---------------------------------------------------------------------------
# El producto de un mes, el NetCDF de 0,1° y la finitud de E0
# ---------------------------------------------------------------------------
class PruebasProducto(unittest.TestCase):
    def test_fraccion_finita_e0(self):
        """MC-51: ≥ 99 % de los puntos con fondo. Se cuentan los puntos-hora con fondo y, entre ellos, los finitos en
        todas las variables del grupo; los conteos se suman entre lotes; 99 % justo pasa (en enteros) y uno menos no;
        sin puntos-hora con fondo la fracción es NaN y no hay decisión."""
        pct = constantes.valor("E0_FINITO_PCT")
        n_h, n_p = 10, 10                                            # 100 puntos-hora
        base = {v: np.ones((n_h, n_p)) for v in VARIABLES}
        con_fondo = np.ones((n_h, n_p), bool)
        faltan = 100 - pct
        T = base["T"].copy()
        T.ravel()[:faltan] = NAN
        justo = {**base, "T": T}
        conteo = producto.conteo_finito(justo, con_fondo, variables=("T", "Td"))
        self.assertEqual((conteo.n_puntos_hora, conteo.n_finitos), (100, pct))
        self.assertTrue(conteo.pasa())
        self.assertEqual(producto.fraccion_finita(justo, con_fondo, grupo="T_Td"), pct / 100)
        self.assertEqual(producto.conteo_finito(justo, con_fondo, grupo=Grupo.T_TD), conteo)
        Td = base["Td"].copy()
        Td.ravel()[-1] = NAN                                         # uno más, en otra variable del grupo
        menos = {**justo, "Td": Td}
        self.assertFalse(producto.conteo_finito(menos, con_fondo, variables=("T", "Td")).pasa())
        self.assertTrue(producto.conteo_finito(menos, con_fondo, variables=("u", "v")).pasa())
        self.assertEqual(producto.conteo_finito(menos, con_fondo, variables=("u", "v")).fraccion, 1.0)
        # Un punto-hora sin fondo no cuenta, aunque su producto sea NaN.
        sin_fondo = con_fondo.copy()
        sin_fondo.ravel()[-1] = False
        c = producto.conteo_finito(menos, sin_fondo, variables=("T", "Td"))
        self.assertEqual((c.n_puntos_hora, c.n_finitos), (99, 99 - faltan))
        # Sumar lotes de puntos (A21) da lo mismo que todo junto.
        lotes = [producto.conteo_finito({v: x[:, sl] for v, x in menos.items()}, con_fondo[:, sl], variables=VARIABLES)
                 for sl in (slice(0, 3), slice(3, 4), slice(4, 10))]
        self.assertEqual(producto.sumar_conteos(lotes), producto.conteo_finito(menos, con_fondo, variables=VARIABLES))
        self.assertEqual(lotes[0] + lotes[1] + lotes[2], producto.sumar_conteos(lotes))
        # Un valor por punto vale para todas sus horas.
        por_punto = np.array([True] * 9 + [False])
        self.assertEqual(producto.conteo_finito(menos, por_punto, grupo="p").n_puntos_hora, 90)
        # Sin puntos-hora con fondo.
        vacio = producto.conteo_finito(menos, np.zeros(n_p, bool), grupo="T_Td")
        self.assertTrue(np.isnan(vacio.fraccion))
        with self.assertRaises(producto.ErrorProducto):
            vacio.pasa()
        for malo in (lambda: producto.conteo_finito(menos, con_fondo.astype(int), grupo="p"),
                     lambda: producto.conteo_finito(menos, con_fondo[:3], grupo="p"),
                     lambda: producto.conteo_finito(menos, con_fondo, variables=("HR",)),
                     lambda: producto.conteo_finito({"T": np.ones(3)}, np.ones(3, bool), variables="T"),
                     lambda: producto.conteo_finito(menos, con_fondo),                    # H8: sin omisión
                     lambda: producto.conteo_finito(menos, con_fondo, variables="T", grupo="T_Td"),
                     lambda: producto.conteo_finito(menos, con_fondo, grupo="x"),
                     lambda: producto.fraccion_finita(menos, con_fondo),
                     lambda: producto.hay_fondo({"T_F": T}),
                     lambda: producto.ConteoFinito(3, 4), lambda: producto.ConteoFinito(-1, 0),
                     lambda: producto.sumar_conteos([conteo, (1, 1)])):
            with self.assertRaises(producto.ErrorProducto):
                malo()

    def test_hay_fondo_y_finitud_de_un_mes_en_celdas(self):
        """MC-51 de punta a punta: el fondo de un mes en 24 celdas (``producto_mes`` en lo crónico con C_est) da
        ``con_fondo`` (``hay_fondo``) y la finitud del grupo (T, Td); sin fondo en una celda y una hora, ese punto-hora
        no cuenta. Las variables de los grupos que lo crónico no decide quedan NaN (PRO-9)."""
        U = _umbrales()
        px, ce = _pixeles(), _celdas()
        campos, F = producto.producto_mes(px.mes, ce.op, ce.puntos, {"T_Td": "C_est"}, {"T": 10.0, "Td": 10.0},
                                          _datos(), umbrales=U, uso=Uso.CRONICO, estaticos=ce.estaticos,
                                          clima_estado=ce.tabla_clima)
        con_fondo = producto.hay_fondo(F, grupo="T_Td")
        self.assertTrue(con_fondo.all())
        conteo = producto.conteo_finito(campos, con_fondo, grupo="T_Td")
        self.assertEqual((conteo.n_puntos_hora, conteo.n_finitos), (con_fondo.size, con_fondo.size))
        self.assertTrue(conteo.pasa())
        for v in ("u", "v", "p", "rapidez", "direccion"):
            self.assertTrue(np.isnan(campos[v]).all(), v)
        self.assertTrue(np.isfinite(campos["HR"]).all())
        # El clima que calcula producto_mes con el operador es el de clima_en_puntos (PRO-7).
        R = producto.correccion("C_est", {"T": 10.0, "Td": 10.0}, ce.puntos, np.asarray(px.mes.tiempos), _datos(),
                                umbrales=U, uso=Uso.CRONICO, estaticos=ce.estaticos, clima=ce.clima)
        self.assertEqual(campos["T"].tobytes(), (F["T_F"] + R["R_T"]).tobytes())
        # Sin fondo en una celda y una hora, ese punto-hora no cuenta (y su producto es NaN).
        F2 = {**F, "T_F": F["T_F"].copy()}
        F2["T_F"][5, 3] = NAN
        con_fondo2 = producto.hay_fondo(F2, grupo="T_Td")
        self.assertEqual(int((~con_fondo2).sum()), 1)
        self.assertTrue(producto.hay_fondo(F2, grupo="u_v").all())
        campos2 = producto.campos(F2, {c: (R[c] if c in R else np.zeros(F["T_F"].shape)) for c in producto.CLAVE_R.values()})
        conteo2 = producto.conteo_finito(campos2, con_fondo2, grupo="T_Td")
        self.assertEqual((conteo2.n_puntos_hora, conteo2.n_finitos), (con_fondo.size - 1, con_fondo.size - 1))
        self.assertEqual(producto.conteo_finito(campos2, con_fondo, grupo="T_Td").n_finitos, con_fondo.size - 1)
        with self.assertRaises(producto.ErrorProducto):
            producto.hay_fondo({"T_F": F["T_F"]}, variables=("T", "Td"))
        with self.assertRaises(producto.ErrorProducto):            # C_est sin la tabla del clima
            producto.producto_mes(px.mes, ce.op, ce.puntos, {"T_Td": "C_est"}, {"T": 10.0, "Td": 10.0}, _datos(),
                                  umbrales=U, uso=Uso.CRONICO, estaticos=ce.estaticos)

    def test_hay_fondo_exige_todas_las_variables_del_grupo(self):
        """H4: en 2 × 2, Td_F NaN con T_F finito deja sin fondo ese punto-hora para (T, Td), no para T solo."""
        F = {k: np.ones((2, 2)) for k in ("T_F", "Td_F", "u_F", "v_F", "p_F")}
        F["Td_F"][0, 1] = NAN
        F["p_F"][1, 0] = NAN
        self.assertEqual(producto.hay_fondo(F, grupo="T_Td").tolist(), [[True, False], [True, True]])
        self.assertTrue(producto.hay_fondo(F, variables="T").all())
        self.assertEqual(producto.hay_fondo(F, grupo="p").tolist(), [[True, True], [False, True]])
        self.assertTrue(producto.hay_fondo(F, grupo="u_v").all())
        campos = {v: np.ones((2, 2)) for v in VARIABLES}
        campos["Td"][0, 1] = NAN
        c = producto.conteo_finito(campos, producto.hay_fondo(F, grupo="T_Td"), grupo="T_Td")
        self.assertEqual((c.n_puntos_hora, c.n_finitos), (3, 3))

    def test_pasa_e0_con_celdas_y_estaciones_por_separado(self):
        """N1 (la más estricta): las celdas pobladas y las estaciones de validación pasan E0 cada una por su lado; un
        conjunto vacío no decide."""
        bien, mal = producto.ConteoFinito(100, 99), producto.ConteoFinito(100, 98)
        self.assertTrue(producto.pasa_e0({"celdas_pobladas": bien, "estaciones_validacion": bien}))
        self.assertFalse(producto.pasa_e0({"celdas_pobladas": bien, "estaciones_validacion": mal}))
        self.assertTrue((bien + mal).pasa() is False and (producto.ConteoFinito(1000, 999) + mal).pasa())
        for malo in ({}, {"celdas": bien, "estaciones": producto.ConteoFinito()}, {"celdas": (100, 99)}, [bien]):
            with self.subTest(malo=repr(malo)), self.assertRaises(producto.ErrorProducto):
                producto.pasa_e0(malo)

    def test_conteo_finito_c_sin_calcular_r(self):
        """H2 (PRO-18): la finitud de C y C_est desde la del diseño (estáticos y estado) es la de ``correccion`` +
        ``campos`` + ``conteo_finito``, con NaN sembrados en un estático, en el fondo y en el clima."""
        U = _umbrales()
        px, ce = _pixeles(), _celdas()
        h = np.asarray(px.mes.tiempos, dtype=np.int64)
        F = fondo_era5l.campos_fondo(px.mes, ce.op, U)
        F = {k: (x.copy() if isinstance(x, np.ndarray) else x) for k, x in F.items()}
        F["T_F"][10, 2] = NAN                                     # sin fondo: no cuenta
        F["Td_F"][10, 2] = NAN
        F["u_F"][30, 4] = NAN                                     # con fondo de (T, Td), pero sin estado de C
        est = ce.estaticos.copy()
        est.loc[6, "pendiente_deg"] = NAN                         # un estático NaN: toda la celda
        est.loc[7, "tpi5"] = NAN                                  # un TPI NaN pero truncado: cuenta como finito
        est.loc[7, "tpi5_truncado"] = True
        clima = {k: (x.copy() if isinstance(x, np.ndarray) else x) for k, x in ce.clima.items()}
        clima["amp"][8, 0, 5] = NAN                               # enero a las 05 UTC en una celda
        con_fondo = producto.hay_fondo(F, grupo="T_Td")
        for cand, uso in ((Candidato.C, Uso.AGUDO), (Candidato.C_EST, Uso.CRONICO)):
            with self.subTest(candidato=cand.value):
                R = producto.correccion(cand, {"T": 10.0, "Td": 0.1}, ce.puntos, h, _datos(), umbrales=U, uso=uso,
                                        fondo=F, estaticos=est, clima=clima)
                todas = {c: R.get(c, np.zeros(F["T_F"].shape)) for c in producto.CLAVE_R.values()}
                esperado = producto.conteo_finito(producto.campos(F, todas), con_fondo, grupo="T_Td")
                mio = producto.conteo_finito_c(cand, ce.puntos, h, con_fondo, estaticos=est, fondo=F, clima=clima)
                self.assertEqual(mio, esperado)
                self.assertLess(esperado.n_finitos, esperado.n_puntos_hora)
        with self.assertRaises(producto.ErrorProducto):
            producto.conteo_finito_c("B", ce.puntos, h, con_fondo, estaticos=est, fondo=F)
        with self.assertRaises(producto.ErrorProducto):            # sin fondo para C
            producto.conteo_finito_c("C", ce.puntos, h, con_fondo, estaticos=est)

    def test_producto_mes_en_pixeles_es_era5_land_mas_la_correccion(self):
        """§3: en los centros de los píxeles válidos el fondo es ERA5-Land tal cual (T_F = t2m − 273,15, bit a bit) y
        el producto suma la corrección del ganador de cada grupo (A en (T, Td), B en (u, v) y AB en p)."""
        U = _umbrales()
        px = _pixeles()
        campos, F = _producto_pixeles()
        t2m = px.mes.datos["t2m"].astype(np.float64)
        self.assertEqual(F["T_F"].tobytes(), (t2m - K).tobytes())
        d2m = px.mes.datos["d2m"].astype(np.float64)
        self.assertTrue(np.all(d2m < t2m))                         # sin el recorte Td ≤ T en este mes
        self.assertEqual(F["Td_F"].tobytes(), (d2m - K).tobytes())
        self.assertEqual(F["p_F"].tobytes(), (px.mes.datos["sp"].astype(np.float64) / 100.0).tobytes())
        self.assertEqual(F["u_F"].tobytes(), px.mes.datos["u10"].astype(np.float64).tobytes())
        self.assertEqual(F["v_F"].tobytes(), px.mes.datos["v10"].astype(np.float64).tobytes())
        datos = _datos()
        h = np.asarray(px.mes.tiempos, dtype=np.int64)
        R = {}
        for grupo, cand in GANADOR.items():
            variables = producto.VARIABLES_DE_GRUPO[Grupo(grupo)]
            R.update(producto.correccion(cand, {v: HIPER_GANADOR[v] for v in variables}, px.puntos, h, datos,
                                         umbrales=U, uso=Uso.AMBIENTAL))
        esperado = producto.campos(F, R)
        for v in esperado:
            self.assertTrue(np.array_equal(campos[v], esperado[v], equal_nan=True), v)
        self.assertTrue(np.all(campos["Td"] <= campos["T"]))
        self.assertTrue(np.isfinite(campos["T"]).all() and np.abs(R["R_T"]).max() > 0.1)
        with self.assertRaises(producto.ErrorProducto):              # A10: la misma z en los puntos y el operador
            producto.producto_mes(px.mes, px.op, {**px.puntos, "z": px.puntos["z"] + 1.0}, GANADOR, HIPER_GANADOR,
                                  datos, umbrales=U, uso=Uso.AMBIENTAL)
        otros = [{**px.puntos, "ids": px.puntos["ids"][::-1]}, {k: x for k, x in px.puntos.items() if k != "ids"},
                 {**px.puntos, "ids": px.puntos["ids"] + 1}]
        for puntos in otros:                                         # H6: los mismos ids que el operador
            with self.assertRaises(producto.ErrorProducto):
                producto.producto_mes(px.mes, px.op, puntos, GANADOR, HIPER_GANADOR, datos, umbrales=U,
                                      uso=Uso.AMBIENTAL)
        for ganador in ({"T_Td": "A", "u_v": "B"}, {**GANADOR, "p": "C_est"}, {**GANADOR, "x": "A"}):
            with self.subTest(ganador=ganador), self.assertRaises(producto.ErrorProducto):
                producto.producto_mes(px.mes, px.op, px.puntos, ganador, HIPER_GANADOR, datos, umbrales=U,
                                      uso=Uso.AMBIENTAL)

    def test_producto_mes_en_celdas_con_c(self):
        """C en lo agudo, en celdas: su estado sale del fondo del mes en las celdas (T_F, T_F − Td_F, rapidez y la
        amplitud del día UTC) y sus estáticos de ``ESQUEMA_ESTATICAS_CELDA_C``; el producto es finito y Td ≤ T."""
        U = _umbrales()
        px, ce = _pixeles(), _celdas()
        campos, F = producto.producto_mes(px.mes, ce.op, ce.puntos, {"T_Td": "C"}, {"T": 10.0, "Td": 10.0}, _datos(),
                                          umbrales=U, uso=Uso.AGUDO, estaticos=ce.estaticos)
        self.assertTrue(np.isfinite(campos["T"]).all() and np.isfinite(campos["HR"]).all())
        self.assertTrue(np.all(campos["Td"] <= campos["T"]))
        R = producto.correccion("C", {"T": 10.0, "Td": 10.0}, ce.puntos, np.asarray(px.mes.tiempos), _datos(),
                                umbrales=U, uso=Uso.AGUDO, fondo=F, estaticos=ce.estaticos)
        self.assertTrue(np.array_equal(campos["T"], F["T_F"] + R["R_T"]))
        amp = fondo_era5l.amplitud_dia_utc(F["T_F"], np.asarray(px.mes.tiempos))
        R2 = producto.correccion("C", {"T": 10.0, "Td": 10.0}, ce.puntos, np.asarray(px.mes.tiempos), _datos(),
                                 umbrales=U, uso=Uso.AGUDO, fondo={**F, "amp_TF": amp}, estaticos=ce.estaticos)
        self.assertEqual(R["R_T"].tobytes(), R2["R_T"].tobytes())

    def test_mes_01deg_atributos(self):
        """Huellas, uso (MC-08) y ganador en los atributos; dimensiones ``time`` × ``pixel``; ``pixel_id``; T, Td, u, v y
        p en int16 con ``scale_factor``, ``add_offset`` y ``_FillValue`` del Anexo A; nada más (ninguna R)."""
        U = _umbrales()
        px = _pixeles()
        ds = _abrir(_bytes_01deg())
        try:
            attrs = {k: ds.getncattr(k) for k in ds.ncattrs()}
            self.assertEqual(attrs["uso"], "ambiental")
            self.assertEqual({k: attrs[f"ganador_{k}"] for k in GANADOR}, GANADOR)
            self.assertEqual(json.loads(attrs["huellas"]), HUELLAS)
            self.assertEqual(attrs["esquema"], producto.ESQUEMA_01DEG)
            self.assertEqual(attrs["mes"], "201101")
            self.assertEqual(attrs["convencion_viento"], producto.CONVENCION_VIENTO)
            self.assertFalse(any("fecha" in k or "date" in k or "history" in k for k in attrs))
            self.assertEqual(list(ds.dimensions), ["time", "pixel"])
            self.assertEqual((len(ds.dimensions["time"]), len(ds.dimensions["pixel"])), (744, 36))
            self.assertEqual(sorted(ds.variables), sorted(["time", "pixel_id", *VARIABLES]))   # netCDF-C las lista por nombre
            self.assertEqual(ds.variables["pixel_id"][:].tolist(), px.pid.tolist())
            self.assertEqual(ds.variables["time"][:].tolist(), np.asarray(px.mes.tiempos).tolist())
            self.assertEqual(ds.variables["time"].units, producto.UNIDADES_TIEMPO)
            self.assertEqual(ds.variables["time"].calendar, producto.CALENDARIO)
            self.assertEqual(ds.variables["time"].dtype, np.int32)
            self.assertEqual(ds.variables["pixel_id"].dtype, np.int64)
            self.assertEqual(ds.variables["pixel_id"].dimensions, ("pixel",))
            formato, relleno = producto.formato_int16(U)
            for v in VARIABLES:
                var = ds.variables[v]
                self.assertEqual(var.dtype, np.int16)
                self.assertEqual(var.dimensions, ("time", "pixel"))
                self.assertEqual(int(var.getncattr("_FillValue")), relleno)
                self.assertEqual(float(var.scale_factor), formato[v][0])
                self.assertEqual(float(var.add_offset), formato[v][1])
                self.assertEqual(var.units, producto.UNIDADES[v])
        finally:
            ds.close()

    def test_mes_01deg_en_memoria_sin_archivos_y_releido(self):
        """A19: los bytes salen de la memoria (ningún archivo nuevo en la carpeta de trabajo) y se releen también en
        memoria: los enteros son los de ``codificar_int16``, la lectura con escala de netCDF4 es la de
        ``decodificar_int16`` y la diferencia con el producto es ≤ media escala."""
        U = _umbrales()
        px = _pixeles()
        campos, _ = _producto_pixeles()
        anterior = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                datos = producto.mes_01deg(campos, px.pid, px.mes.tiempos, U, HUELLAS, uso="ambiental",
                                           ganador=GANADOR)
                self.assertEqual(os.listdir(tmp), [])
            finally:
                os.chdir(anterior)
        self.assertFalse(Path(producto._ETIQUETA_NC).exists())
        self.assertIsInstance(datos, bytes)
        self.assertTrue(datos.startswith(b"\x89HDF\r\n\x1a\n"))
        enteros = producto.codificar_int16(campos, U)
        decod = producto.decodificar_int16(enteros, U)
        ds = _abrir(datos)
        try:
            for v in VARIABLES:
                var = ds.variables[v]
                var.set_auto_maskandscale(False)
                self.assertEqual(np.asarray(var[:]).tobytes(), enteros[v].tobytes(), v)
                var.set_auto_maskandscale(True)
                leido = np.ma.filled(var[:].astype(np.float64), np.nan)
                self.assertTrue(np.array_equal(leido, decod[v], equal_nan=True), v)
                self.assertLessEqual(float(np.nanmax(np.abs(leido - campos[v]))), _media_escala(U, v) * (1 + 1e-9))
        finally:
            ds.close()

    def test_mes_01deg_bytes_deterministas(self):
        """S9: mismas entradas, mismo sha256 (sin fechas de creación); el orden de las huellas no cambia los bytes; otro
        ganador u otra huella sí."""
        a, b = _bytes_01deg(), _bytes_01deg()
        self.assertEqual(hashlib.sha256(a).hexdigest(), hashlib.sha256(b).hexdigest())
        invertidas = dict(reversed(list(HUELLAS.items())))
        self.assertEqual(_bytes_01deg(huellas=invertidas), a)
        self.assertNotEqual(_bytes_01deg(ganador={**GANADOR, "p": "C"}), a)
        self.assertNotEqual(_bytes_01deg(huellas={**HUELLAS, "LOCAL/otra.json": "b" * 64}), a)

    def test_s09_mismo_sha256_en_dos_procesos(self):
        """H9 (S9): dos procesos aparte, con el intérprete fijado (``-B -I``, los hilos en 1 y semillas de hash
        distintas: con ``-I`` cada proceso toma la suya al azar y se comprueba que difieren), arman el mismo NetCDF de
        0,1° desde cero y dan el mismo sha256, el mismo que en este proceso."""
        codigo = ("import hashlib, sys; sys.dont_write_bytecode = True; sys.path.insert(0, sys.argv[1]); "
                  "from meteo_combinada.tests import test_producto as T; "
                  "print(hashlib.sha256(T._bytes_01deg()).hexdigest(), hash('semilla de hash'))")
        entorno = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR", "LANG") if k in os.environ}
        entorno.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
        procesos = [subprocess.Popen([sys.executable, "-B", "-I", "-c", codigo, str(_RAIZ)], stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, env=entorno, text=True) for _ in range(2)]
        salidas = [p.communicate(timeout=600) for p in procesos]
        for p, (_, err) in zip(procesos, salidas):
            self.assertEqual(p.returncode, 0, err[-2000:])
        lineas = [out.strip().splitlines()[-1].split() for out, _ in salidas]
        self.assertNotEqual(lineas[0][1], lineas[1][1], "las dos semillas de hash deberían ser distintas")
        aqui = hashlib.sha256(_bytes_01deg()).hexdigest()
        self.assertEqual([x[0] for x in lineas], [aqui, aqui])

    def test_mes_01deg_rechaza(self):
        """Sin huellas o con huellas mal formadas; otro uso que el ambiental (MC-08); ganador incompleto o con un
        candidato de otro uso; horas de dos meses o desordenadas; píxeles repetidos o desordenados; formas que no
        calzan; un valor que desborda int16."""
        U = _umbrales()
        px = _pixeles()
        campos, _ = _producto_pixeles()
        h, pid = np.asarray(px.mes.tiempos), px.pid
        base = {"campos": campos, "pixel_id": pid, "h": h, "huellas": HUELLAS, "uso": "ambiental", "ganador": GANADOR}
        casos = {"sin huellas": {"huellas": {}}, "huella corta": {"huellas": {"LOCAL/x.json": "abc"}},
                 "huella mayúscula": {"huellas": {"LOCAL/x.json": "A" * 64}},
                 "ruta absoluta": {"huellas": {"/tmp/x.json": "a" * 64}},
                 "arroba": {"huellas": {"x" + chr(64) + "y": "a" * 64}}, "huellas lista": {"huellas": ["a" * 64]},
                 "agudo": {"uso": "agudo"}, "crónico": {"uso": "cronico"},
                 "agudo con su ganador": {"uso": "agudo", "ganador": {"T_Td": "A"}},
                 "ganador incompleto": {"ganador": {"T_Td": "A", "u_v": "B"}},
                 "ganador C_est": {"ganador": {**GANADOR, "T_Td": "C_est"}},
                 "dos meses": {"h": h + 24 * 30}, "horas al revés": {"h": h[::-1]},
                 "un hueco": {"h": np.delete(h, 100)}, "desde la mitad del mes": {"h": h[24:]},
                 "carpeta de usuario": {"huellas": {"LOCAL/x" + "/" + "Users" + "/y.json": "a" * 64}},
                 "segmento ..": {"huellas": {"LOCAL/../x.json": "a" * 64}},
                 "píxel repetido": {"pixel_id": np.r_[pid[:-1], pid[0]]}, "píxeles al revés": {"pixel_id": pid[::-1]},
                 "forma": {"campos": {**campos, "T": campos["T"][:, :5]}},
                 "una R": {"campos": {**campos, "R_T": campos["T"]}},
                 "desborde": {"campos": {**campos, "p": campos["p"] + 600.0}}}
        for nombre, cambio in casos.items():
            kw = {**base, **cambio}
            with self.subTest(caso=nombre), self.assertRaises(producto.ErrorProducto):
                producto.mes_01deg(kw["campos"], kw["pixel_id"], kw["h"], U, kw["huellas"], uso=kw["uso"],
                                   ganador=kw["ganador"])

    def test_s07_vigilancia_de_las_salidas(self):
        """S7: los bytes del NetCDF pasan ``ceguera.vigilar_salida`` como «insumo» (D14), y su ruta no admite otra
        clase; los atributos que elige este módulo y los conteos de la finitud pasan la guarda de un resumen (sin
        «fondo», «era5l», «sin_dmc», «correccion» ni «R_»)."""
        datos = _bytes_01deg()
        ceguera.vigilar_salida("producto_01deg/meteo_201101.nc", datos, clase="insumo")
        with self.assertRaises(ceguera.SalidaProhibida):
            ceguera.vigilar_salida("producto_01deg/meteo_201101.nc", datos, clase="metrica")
        ds = _abrir(datos)
        try:
            propios = {k: ds.getncattr(k) for k in ds.ncattrs() if k != "huellas"}
            propios["huellas"] = json.loads(ds.getncattr("huellas"))
            for v in ds.variables:
                propios[f"variable_{v}"] = {k: str(ds.variables[v].getncattr(k)) for k in ds.variables[v].ncattrs()}
        finally:
            ds.close()
        ceguera.vigilar_salida("registro_m34.json", propios, clase="resumen")
        conteo = producto.ConteoFinito(100, 99)
        ceguera.vigilar_salida("registro_m34.json", {"finitud_e0": {"ambiental/T_Td/A": conteo.como_dict()}},
                               clase="resumen")
        with self.assertRaises(ceguera.SalidaProhibida):              # la guarda sí ve una R si alguien la publica
            ceguera.vigilar_salida("registro_m34.json", {"columnas": list(producto.CLAVE_R.values())}, clase="resumen")


if __name__ == "__main__":
    unittest.main()
