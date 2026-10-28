"""Pruebas de ambiental.py (§7.1 y Anexo B).

Dueño: I19 (ola 5). Las que llevan «sNN» son la prueba NN de §9 del texto: aquí, la TF de contaminantes de S16 con la
fábrica de A26. Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest meteo_combinada.tests.test_ambiental
Datos sólo sintéticos, en carpetas temporales o en memoria: una red DMC de 11 estaciones hecha aquí (residuos, fondo en
las estaciones y estáticos de sus celdas), los paneles y ``pliegues_v2_red2.json`` de ``sintetico.panel_y_pliegues``, un
mes ERA5-Land de ``sintetico.mes_era5_netcdf`` leído con ``fondo_era5l.leer_mes`` y, para los demás meses, la misma
función armada en memoria (``fondo_era5l.MesE5L``), el catálogo de ``sintetico.catalogo_pixeles`` y la grilla de
``sintetico.grilla``. Ninguna prueba abre DMC, el reloj, la meteorología SINCA real, NASADEM real, ERA5L real, GHS-POP
real, el panel v2 real ni ``pliegues_v2_red2.json`` real. Se leen, sin escribir, el texto y el JSON de umbrales anclados
en M0 (APH), y el código fijado ``meteorologia_v2.py`` y ``_features.py`` (por ``fijados``). Semilla: ``SEMILLA`` del
Anexo A. La política (``politicas_meteo_v1.json``) es una lista sintética de ``politicas.a_json``; los paneles con otras
filas (otra zona, claves repetidas, dos años) llevan su registro rehecho en memoria (``_registro_con``).

Las correcciones de la revisión de la ola 5 (H2 a H9, PED-7) tienen pruebas propias: las horas tras el último dato
de ERA5-Land, el panel atado a su registro y ``unir_partes`` (``PruebasPartes``), la política verificada, el recorte de
``mc_d2m`` donde Td supera a T, la receta de ``content_sha256``, el operador inmutable y sus umbrales, y adaptadores
falsos para ``comprobar_union``.
"""
import sys

sys.dont_write_bytecode = True

import copy  # noqa: E402
import dataclasses  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import struct  # noqa: E402
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

from meteo_combinada import (ambiental, candidatos, ceguera, constantes, decision, entorno, fijados,  # noqa: E402
                             fondo_era5l, numerico, particiones, politicas, producto, salidas, sintetico, tendencias,
                             tipos, umbrales)
from meteo_combinada.tipos import Candidato, Grupo, Hiper, Uso  # noqa: E402

_AP = _RAIZ.parent
_APH = _AP.parent / "Air-Pollution-Health-Chile"
_EPOCA = np.datetime64("2000-01-01T00", "h")
NAN = float("nan")
K = constantes.valor("KELVIN")
ErrorAmbiental = ambiental.ErrorAmbiental
_U = None

H_A = Hiper(50.0, 50.0, 0.2)
H_B = Hiper(25.0, 0.0, 0.5)
H_PHI = Hiper(100.0, 150.0, 1.0)
# θ distintos por variable (u y v comparten el suyo, MC-43), para que «el θ de T en todas» no pase.
HIPER_DE = {
    "A": {"T": H_A, "Td": H_B, "u": H_A, "v": H_A, "p": H_PHI},
    "B": {"T": H_B, "Td": H_A, "u": H_B, "v": H_B, "p": H_A},
    "AB": {"T": (H_A, H_B), "Td": (H_B, H_PHI), "u": (H_A, H_PHI), "v": (H_A, H_PHI), "p": (H_PHI, H_B)},
    "C": {"T": 10.0, "Td": 1.0, "u": 1.0, "v": 1.0, "p": 100.0},
}
G_MIXTO = (("T_Td", "B"), ("u_v", "AB"), ("p", "A"))
G_CON_C = (("T_Td", "C"), ("u_v", "A"), ("p", "C"))
G_OTRO = (("T_Td", "AB"), ("u_v", "C"), ("p", "B"))
G_A_C = (("T_Td", "A"), ("u_v", "C"), ("p", "A"))
G_B = (("T_Td", "B"), ("u_v", "B"), ("p", "B"))
G_AB = (("T_Td", "AB"), ("u_v", "AB"), ("p", "AB"))
# politicas_meteo_v1.json sintético (H7): una lista de políticas como la que escribe M3-4 con politicas.a_json.
POLITICA_BYTES = politicas.a_json([{"station_code": "330000", "valid_from": "2018-01-01T00:00:00",
                                    "valid_to": "2019-12-31T23:00:00", "variables": ["Ts", "Td"]}])
POLITICA = hashlib.sha256(POLITICA_BYTES).hexdigest()
TRAS = ambiental.CLAVE_TRAS_ULTIMA


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


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


# ---------------------------------------------------------------------------
# Red DMC sintética: 10 estaciones en Santiago (una en el grupo de otra) y una excluida
# ---------------------------------------------------------------------------
def _info(codigo: str, lat: float, lon: float, z: float, celda, *, excluida: bool = False) -> tipos.InfoEstacion:
    e, n = (float(x[0]) for x in numerico.utm19s(np.array([lat, lat]), np.array([lon, lon])))
    return tipos.InfoEstacion(
        codigo=codigo, nombre=f"E{codigo}", conjunto="V", macrozona="centro", grupo=tipos.id_grupo([codigo]),
        omm=None, tipo=None, propietario=None, lat_txt=f"{lat:.4f}", lon_txt=f"{lon:.4f}", alt_txt=f"{z:.0f}",
        lat=float(lat), lon=float(lon), z_cat=float(z), rho_km=0.1, k3_pasa=not excluida, z_s=float(z),
        z_s_fuente="catalogo", celda=celda, utm_e=float(e), utm_n=float(n), bloque="", pix0=0, pix1=-1, pix2=-1,
        pix3=-1, w0=1.0, w1=0.0, w2=0.0, w3=0.0, respaldo_16km=False, sin_fondo=False, excluida=excluida,
        motivo="k3_falla" if excluida else None)


@lru_cache(maxsize=None)
def _red() -> dict:
    U = _umbrales()
    infos, k = {}, 0
    for i in range(3):
        for j in range(3):
            lat = -33.38 - 0.11 * i - 0.011 * ((i + 2 * j) % 3)
            lon = -70.78 + 0.11 * j + 0.009 * ((2 * i + j) % 3)
            codigo = f"{330000 + k:06d}"
            infos[codigo] = _info(codigo, lat, lon, 450.0 + 700.0 * (lon + 70.8) + 50.0 * i, 1000 + k)
            k += 1
    primero = infos["330000"]
    infos["330009"] = _info("330009", primero.lat - 0.005, primero.lon + 0.006, primero.z_s + 12.0, 1009)
    infos["330010"] = _info("330010", -33.52, -70.62, 600.0, 1010, excluida=True)
    grupos = particiones.grupos_mismo_sitio(infos, U)
    codigos = sorted(infos)
    bloques = particiones.bloque(np.array([infos[c].lat for c in codigos]), np.array([infos[c].lon for c in codigos]), U)
    return {c: dataclasses.replace(infos[c], grupo=grupos.get(c, infos[c].grupo), bloque=str(b))
            for c, b in zip(codigos, bloques)}


def _estaticos_estaciones(infos: dict) -> pd.DataFrame:
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
    hora = h % 24
    doy = (h // 24) % 365
    amplitud = 5 * (1 + 0.3 * np.sin(2 * np.pi * doy / 45) + 0.05 * k)
    T = 15 + 6 * np.cos(2 * np.pi * (doy - 20) / 365.25) + amplitud * np.cos(2 * np.pi * (hora - 19) / 24) \
        - 0.005 * z + 0.3 * k
    return {"T_F": T, "Td_F": T - 4 - 2 * np.cos(2 * np.pi * (hora - 19) / 24) ** 2,
            "p_F": numerico.p_std(z) + 2.0 * np.sin(h / 50.0), "u_F": 1.5 * np.sin(2 * np.pi * hora / 24) + 0.1 * k,
            "v_F": 0.5 + 0.2 * np.cos(h / 30.0)}


def _residuos(infos: dict, h: np.ndarray, semilla_extra: int = 1) -> dict:
    rng = np.random.default_rng(_umbrales().a("SEMILLA") + semilla_extra)
    hora = h % 24
    mes = (_EPOCA + h.astype("timedelta64[h]")).astype("datetime64[M]").astype(np.int64) % 12 + 1
    salida = {}
    for k, c in enumerate(sorted(infos)):
        if infos[c].excluida:
            continue
        b = 1.0 + 0.8 * (infos[c].lat + 33.4) + 0.4 * np.cos(2 * np.pi * (mes - 1) / 12) \
            + 0.4 * np.cos(2 * np.pi * (hora - 15) / 24) + 0.15 * k
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


def _armar_datos(h: np.ndarray, semilla_extra: int = 1) -> tipos.DatosCompetencia:
    U = _umbrales()
    infos = _red()
    residuos, tramos = {}, []
    for c, (hc, r) in _residuos(infos, h, semilla_extra).items():
        residuos[c], tr = candidatos.residuos_estacion(c, hc, r, U)
        tramos.append(tr)
    puntos = {}
    for k, c in enumerate(sorted(infos)):
        if not infos[c].excluida:
            puntos[c] = fondo_era5l.tabla_puntos(h, _fondo_estacion(k, infos[c].z_s, h))
    activas = {c: i for c, i in infos.items() if not i.excluida}
    estaticos = _estaticos_estaciones(activas)
    filas = {"C": candidatos.filas_c(residuos, estaticos, puntos, U, infos=infos)}
    return tipos.DatosCompetencia(residuos=residuos, climatologias=candidatos.climatologias_a(residuos, U),
                                  tramos=pd.concat(tramos, ignore_index=True), filas_c=filas, estaticos=estaticos,
                                  estaciones=infos, pliegues=(), puntos_e5l=puntos, clima_estado={})


@lru_cache(maxsize=None)
def _datos() -> tipos.DatosCompetencia:
    """Residuos 2018-2019 (horarios), climatologías de A y filas de C de producción."""
    return _armar_datos(np.arange(_h("2018-01-01T00"), _h("2020-01-01T00"), dtype=np.int64))


@lru_cache(maxsize=None)
def _datos_tf() -> tipos.DatosCompetencia:
    """Residuos sólo en enero-marzo de 2015 y de 2020, para la TF de contaminantes de 2015-2024."""
    h = np.concatenate([np.arange(_h("2015-01-01T00"), _h("2015-04-01T00")),
                        np.arange(_h("2020-01-01T00"), _h("2020-04-01T00"))]).astype(np.int64)
    return _armar_datos(h, semilla_extra=7)


# ---------------------------------------------------------------------------
# Píxeles, meses ERA5-Land, celdas, panel y pliegues
# ---------------------------------------------------------------------------
_BLOQUES_PIXELES = ((-33.2, -70.9, 6, 6), (-32.8, -71.8, 4, 5), (-36.5, -73.2, 5, 13), (-34.0, -70.9, 4, 4))


@lru_cache(maxsize=None)
def _pixeles():
    partes = [sintetico.catalogo_pixeles(*b) for b in _BLOQUES_PIXELES]
    cat = pd.concat(partes, ignore_index=True).drop_duplicates("pixel_id").sort_values("pixel_id").reset_index(drop=True)
    pid = cat["pixel_id"].to_numpy(np.int64)
    lat, lon = cat["latitude"].to_numpy(), cat["longitude"].to_numpy()
    z = 350.0 + 250.0 * (lon + 73.5) + 60.0 * np.sin(lat * 7.0)
    return types.SimpleNamespace(cat=cat, pid=pid, lat=lat, lon=lon, z=z,
                                 z_tabla=pd.DataFrame({"pixel_id": pid, "z_e5l": z}))


def _campos_mes(anio: int, mes: int) -> tuple:
    """Los campos ERA5-Land sintéticos de un mes (unidades nativas), con ciclo diario y variación entre píxeles."""
    px = _pixeles()
    t = sintetico.horas_del_mes(anio, mes)
    h = (t.astype("datetime64[h]") - _EPOCA).astype(np.int64)
    hora = (h % 24)[:, None]
    a, b = (px.lat + 33.0)[None, :], (px.lon + 71.0)[None, :]
    t2m = 289.0 + 5.0 * np.cos(2 * np.pi * (hora - 19) / 24) - 0.0065 * px.z[None, :] + 0.3 * a \
        + 0.5 * np.sin(h / 97.0)[:, None]
    campos = {"t2m": t2m, "d2m": t2m - 6.0 - 0.4 * b - 1.5 * np.cos(2 * np.pi * (hora - 19) / 24) ** 2,
              "sp": numerico.p_std(px.z)[None, :] * 100.0 + 200.0 * np.sin(h / 5.0)[:, None],
              "u10": 2.0 * np.sin(2 * np.pi * hora / 24) + 0.2 * b,
              "v10": -1.0 + 0.5 * np.cos(2 * np.pi * hora / 24) + 0.1 * a,
              "tp": np.zeros((h.size, px.pid.size))}
    return t, h, campos


def _mes_memoria(yyyymm: int) -> fondo_era5l.MesE5L:
    """Un mes ERA5-Land armado en memoria con los mismos números que lee ``leer_mes`` (float32, unidades nativas)."""
    _, h, campos = _campos_mes(yyyymm // 100, yyyymm % 100)
    datos = {v: np.asarray(x, dtype=np.float32) for v, x in campos.items()}
    return fondo_era5l.MesE5L(tiempos=h.astype(np.int32), pixel_id=_pixeles().pid, datos=datos,
                              sha256=_sha(f"mes {yyyymm}".encode()))


@lru_cache(maxsize=None)
def _mes_201901() -> fondo_era5l.MesE5L:
    t, _, campos = _campos_mes(2019, 1)
    with tempfile.TemporaryDirectory() as tmp:
        ruta = sintetico.mes_era5_netcdf(Path(tmp) / "era5land_201901.nc", campos, t, _pixeles().pid)
        return fondo_era5l.leer_mes(ruta)


def _meses(yyyymm: int):
    return _mes_201901() if yyyymm == 201901 else _mes_memoria(yyyymm)


def _mes_saturado(yyyymm: int, horas: int) -> fondo_era5l.MesE5L:
    """El mes en memoria con d2m sobre t2m en sus primeras ``horas``: allí el recorte de §4.1 deja Td_F = T_F, y el mín
    de Td recorta donde R_Td > R_T (H4)."""
    _, h, campos = _campos_mes(yyyymm // 100, yyyymm % 100)
    d2m = np.array(campos["d2m"], dtype=np.float64)
    d2m[:horas] = np.asarray(campos["t2m"])[:horas] + 2.0
    datos = {v: np.asarray(d2m if v == "d2m" else x, dtype=np.float32) for v, x in campos.items()}
    return fondo_era5l.MesE5L(tiempos=h.astype(np.int32), pixel_id=_pixeles().pid, datos=datos,
                              sha256=_sha(f"saturado {yyyymm}".encode()))


def _mes_hasta(yyyymm: int, h_ultima: int) -> fondo_era5l.MesE5L:
    """El mes en memoria cortado en ``h_ultima``, como el último mes de ERA5-Land (FON-1: completo hasta ahí)."""
    mes = _mes_memoria(yyyymm)
    ok = np.asarray(mes.tiempos, dtype=np.int64) <= h_ultima
    return fondo_era5l.MesE5L(tiempos=mes.tiempos[ok], pixel_id=mes.pixel_id,
                              datos={k: v[ok] for k, v in mes.datos.items()}, sha256=mes.sha256)


def _centro(celda) -> tuple[float, float]:
    """El centro de una celda con los ids de ``sintetico`` (sólo en esta prueba: el código nunca deduce celdas de ids)."""
    i, j = int(celda) // 36000, int(celda) % 36000
    return round(i / 100 - 90 + 0.005, 6), round(j / 100 - 180 + 0.005, 6)


@lru_cache(maxsize=None)
def _red2():
    """Paneles y pliegues de la red 2 (``sintetico.panel_y_pliegues``), leídos en memoria."""
    with tempfile.TemporaryDirectory() as tmp:
        rutas = sintetico.panel_y_pliegues(tmp)
        bytes_panel = {pol: Path(rutas[f"panel_{pol}"]).read_bytes() for pol in tipos.CONTAMINANTES_M6}
        paneles = {pol: pd.read_parquet(io.BytesIO(b)) for pol, b in bytes_panel.items()}
        sha_panel = {pol: _sha(b) for pol, b in bytes_panel.items()}
        pliegues = Path(rutas["pliegues"]).read_bytes()
    return types.SimpleNamespace(paneles=paneles, sha_panel=sha_panel, pliegues=pliegues, bytes_panel=bytes_panel,
                                 monitores=rutas["monitores"])


def _registro_con(pol: str, panel: pd.DataFrame, **cambios) -> tuple[bytes, bytes]:
    """(bytes del panel, bytes de pliegues_v2_red2.json) con ``panel`` como el de ``pol`` de la red 2 sintética: su
    sha256, sus filas y sus estaciones en ``contaminantes.<pol>.panel`` (como ``pliegues_v2``); ``cambios`` reemplaza
    (o con None quita) campos de ese registro."""
    buf = io.BytesIO()
    panel.to_parquet(buf, index=False)
    datos = buf.getvalue()
    manifiesto = json.loads(_red2().pliegues)
    registro = manifiesto["contaminantes"][pol]["panel"]
    registro.update({"sha256": _sha(datos), "filas": int(len(panel)), "estaciones": int(panel["estacion"].nunique())})
    for k, v in cambios.items():
        if v is None:
            registro.pop(k)
        else:
            registro[k] = v
    return datos, json.dumps(manifiesto, ensure_ascii=False, indent=1).encode("utf-8") + b"\n"


H_ULTIMA = _h("2019-01-31T23")       # la última hora con dato de ERA5-Land de estas pruebas (el panel llega hasta ahí)


class _UmbralesCambiados:
    """Los umbrales de M0 con algunos ids cambiados (sólo para ver que el operador no acepta otros, AMB-6)."""

    def __init__(self, U, cambios: dict):
        self._U, self._cambios = U, dict(cambios)

    def a(self, ident):
        return self._cambios.get(ident, self._U.a(ident))


@lru_cache(maxsize=None)
def _celdas():
    """Las celdas del operador: las 12 de los monitores y 30 de ``sintetico.grilla`` sobre la red DMC."""
    g = sintetico.grilla(30, 2, lat0=-33.36, lon0=-70.76)
    rejilla = g["celdas"][["celda", "lat", "lon", "cod_comuna"]]
    monitores = sorted(set(int(c) for c in _red2().monitores["celda"]))
    filas = [{"celda": c, "lat": _centro(c)[0], "lon": _centro(c)[1], "cod_comuna": 13101} for c in monitores]
    tabla = pd.concat([rejilla, pd.DataFrame(filas)], ignore_index=True).drop_duplicates("celda")
    tabla = tabla.sort_values("celda").reset_index(drop=True)
    lat, lon = tabla["lat"].to_numpy(), tabla["lon"].to_numpy()
    z = 420.0 + 300.0 * (lon + 72.5) + 80.0 * np.cos(lat * 11.0)
    rng = np.random.default_rng(_umbrales().a("SEMILLA") + 3)
    n = len(tabla)
    fr = rng.dirichlet(np.ones(len(tipos.LULC)), size=n)
    est = pd.DataFrame({"celda": tabla["celda"].to_numpy(np.int64), "z_media": z, "z_poblada": z - 10.0,
                        "z_poblada_es_media": False, "frac_dato": 1.0, "tpi1": rng.normal(0, 20, n),
                        "tpi5": rng.normal(0, 60, n), "tpi1_truncado": False, "tpi5_truncado": np.arange(n) == 4,
                        "pendiente_deg": rng.uniform(1, 15, n), "log_dist_costa": np.log1p(20 + 40 * (lon + 74.0)),
                        **{c: fr[:, i] for i, c in enumerate(tipos.LULC)}, "lat": lat, "macrozona_cod": 2,
                        "cod_comuna": tabla["cod_comuna"].to_numpy(np.int32)})
    px = _pixeles()
    op = fondo_era5l.operador(lat, lon, z, px.cat, px.pid, px.z_tabla, _umbrales(), ids=tabla["celda"].to_numpy())
    z_de = dict(zip(px.pid.tolist(), px.z.tolist()))
    pix, w = np.asarray(op.pix), np.asarray(op.w)
    est[tipos.COLUMNA_Z_E5L] = [sum(w[i, k] * z_de[int(pix[i, k])] for k in range(4) if pix[i, k] >= 0)
                                for i in range(n)]
    esquema = tipos.ESQUEMA_ESTATICAS_CELDA_C
    estaticos = est[list(esquema)].astype(dict(esquema))
    return types.SimpleNamespace(tabla=tabla[["celda", "lat", "lon"]], comunas=tabla["cod_comuna"].to_numpy(),
                                 estaticos=estaticos, rejilla=rejilla["celda"].to_numpy(np.int64),
                                 monitores=np.array(monitores, dtype=np.int64))


# ---------------------------------------------------------------------------
# decision.json y el operador
# ---------------------------------------------------------------------------
def _decisiones(ganador: tuple) -> list:
    salida = []
    for g, c in ganador:
        e0 = ("A", "B", "AB", "C")
        S = {x: 1.0 + 0.1 * i for i, x in enumerate(e0)}
        S[c] = 0.5
        salida.append(tipos.DecisionGrupo(
            uso=Uso.AMBIENTAL, grupo=Grupo(g), e0=e0, e1=e0, motivos={}, S=S,
            delta_S={x: S[x] - S[c] for x in e0}, ic_delta_S={x: (S[x] - S[c], S[x] - S[c] + 0.1) for x in e0},
            red_tf2={}, notas=(), ganador=c))
    return salida


@lru_cache(maxsize=None)
def _decision_bytes(ganador: tuple = G_MIXTO, alfa_C_T: float = 10.0) -> bytes:
    hip = {}
    for g, _ in ganador:
        variables = producto.VARIABLES_DE_GRUPO[Grupo(g)]
        hip[("ambiental", g)] = {c: {v: (alfa_C_T if (c == "C" and v == "T") else HIPER_DE[c][v]) for v in variables}
                                 for c in ("A", "B", "AB", "C")}
    registro = decision.decision_json(_decisiones(ganador), hip, {"LOCAL/x/residuos.parquet": "0" * 64})
    return entorno.json_canonico(registro)


def _operador_de(ganador: tuple = G_MIXTO, **kw) -> ambiental.OperadorGrilla:
    cl, px = _celdas(), _pixeles()
    return ambiental.operador_grilla(kw.pop("decision", _decision_bytes(ganador)), celdas=cl.tabla,
                                     estaciones=_red(), catalogo=px.cat, z_celdas=cl.estaticos, validos=px.pid,
                                     z_pix=px.z_tabla, umbrales=_umbrales(), **kw)


_OPERADORES: dict = {}


def _operador(ganador: tuple = G_MIXTO) -> ambiental.OperadorGrilla:
    if ganador not in _OPERADORES:
        _OPERADORES[ganador] = _operador_de(ganador)
    return _OPERADORES[ganador]


def _lateral(pol: str = "pm25", variante: str = "I", ganador: tuple = G_MIXTO, **kw):
    r2 = _red2()

    def tomar(clave, por_omision):
        return kw.pop(clave) if clave in kw else por_omision()
    panel = tomar("panel", lambda: r2.paneles[pol])
    por_omision = (lambda: None) if isinstance(panel, bytes) else (lambda: r2.sha_panel.get(pol, "0" * 64))
    return ambiental.lateral_monitores(
        pol, tomar("decision", lambda: _decision_bytes(ganador)), tomar("operador", lambda: _operador(ganador)),
        variante=variante, panel=panel, pliegues=tomar("pliegues", lambda: r2.pliegues),
        meses=tomar("meses", lambda: _meses), datos=tomar("datos", _datos), umbrales=tomar("umbrales", _umbrales),
        politica=tomar("politica", lambda: POLITICA_BYTES), h_ultima=tomar("h_ultima", lambda: H_ULTIMA),
        panel_sha256=tomar("panel_sha256", por_omision),
        estaticos=tomar("estaticos", lambda: _celdas().estaticos), **kw)


_LATERALES: dict = {}


def _lateral_cache(pol: str = "pm25", variante: str = "I", ganador: tuple = G_MIXTO):
    clave = (pol, variante, ganador)
    if clave not in _LATERALES:
        _LATERALES[clave] = _lateral(pol, variante, ganador)
    return _LATERALES[clave]


@lru_cache(maxsize=None)
def _adaptador():
    return fijados.cargar_adaptador(_AP)


def _columnas(variante: str, ganador: tuple = G_MIXTO, celdas=None, horas=None, **kw) -> dict:
    cl = _celdas()
    return ambiental.columnas_bloque(cl.tabla["celda"].to_numpy() if celdas is None else celdas,
                                     _horas_mes(2019, 1) if horas is None else horas, variante,
                                     operador=kw.pop("operador", _operador(ganador)), meses=kw.pop("meses", _meses),
                                     datos=kw.pop("datos", _datos()), umbrales=kw.pop("umbrales", _umbrales()),
                                     estaticos=kw.pop("estaticos", cl.estaticos), **kw)


# ---------------------------------------------------------------------------
# La unión con meteorologia_v2.unir_sidecar real (§7.1, punto 2; A29)
# ---------------------------------------------------------------------------
class PruebasUnion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adaptador = _adaptador()

    def _unir(self, panel, tabla, meta):
        base = panel.copy()
        if not isinstance(base["ts_utc"].dtype, pd.DatetimeTZDtype):
            base["ts_utc"] = base["ts_utc"].dt.tz_localize("UTC")
        return self.adaptador.unir_sidecar(base, tabla, metadata=meta)

    def test_union_con_unir_sidecar_sin_cambiar_filas_ni_orden(self):
        """meteorologia_v2.unir_sidecar real sobre un panel sintético."""
        for pol in tipos.CONTAMINANTES_M6:
            panel = _red2().paneles[pol]
            for variante in ("I", "D"):
                with self.subTest(pol=pol, variante=variante):
                    tabla, meta = _lateral_cache(pol, variante)
                    identidad = ambiental.comprobar_union(tabla, meta, self.adaptador, panel=panel)
                    self.assertEqual(identidad["columns"], list(ambiental.COLUMNAS_VARIANTE[variante]))
                    resultado, _ = self._unir(panel, tabla, meta)
                    self.assertEqual(len(resultado), len(panel))
                    self.assertTrue(resultado.index.equals(panel.index))
                    np.testing.assert_array_equal(resultado["estacion"].to_numpy(object),
                                                  panel["estacion"].to_numpy(object))
                    np.testing.assert_array_equal(resultado["ts_utc"].dt.tz_localize(None).to_numpy(),
                                                  panel["ts_utc"].to_numpy())
                    for c in panel.columns:
                        if c != "ts_utc":
                            self.assertTrue(resultado[c].equals(panel[c]), c)
                    # Cada fila del panel trae su valor de la lateral (todas sus claves están en ella).
                    self.assertFalse(resultado[list(meta["columnas"])].isna().all(axis=1).any())
                    por_clave = tabla.set_index(["estacion", "ts_utc"])
                    muestra = resultado.sample(200, random_state=3)
                    for _, fila in muestra.iterrows():
                        esperado = por_clave.loc[(fila["estacion"], fila["ts_utc"])]
                        for c in meta["columnas"]:
                            np.testing.assert_array_equal(np.float32(fila[c]), np.float32(esperado[c]))

    def test_union_con_panel_desordenado_y_claves_de_mas(self):
        """El orden del panel manda; una clave que la lateral no tiene queda NaN; el panel de prueba propio también."""
        tabla, meta = _lateral_cache("pm25", "D")
        panel = _red2().paneles["pm25"]
        rng = np.random.default_rng(5)
        desordenado = panel.iloc[rng.permutation(len(panel))].reset_index(drop=True)
        extra = desordenado.iloc[:3].copy()
        extra["ts_utc"] = extra["ts_utc"] + pd.Timedelta(days=400)
        desordenado = pd.concat([desordenado, extra], ignore_index=True)
        ambiental.comprobar_union(tabla, meta, self.adaptador, panel=desordenado)
        resultado, _ = self._unir(desordenado, tabla, meta)
        self.assertTrue(resultado[list(meta["columnas"])].iloc[-3:].isna().all().all())
        self.assertFalse(resultado[list(meta["columnas"])].iloc[:-3].isna().all(axis=1).any())
        identidad = ambiental.comprobar_union(tabla, meta, self.adaptador)       # panel de prueba propio (AMB-13)
        self.assertEqual(identidad["panel_rows"], len(tabla) + 1)
        objeto = panel.astype({"estacion": object})
        ambiental.comprobar_union(tabla, meta, self.adaptador, panel=objeto)

    def test_union_se_niega_con_metadatos_falsos(self):
        """§7.1, punto 2: el código fijado se niega sin política verificada o sin su identidad, y comprobar_union se
        niega además con un contenido, una variante, columnas o unidades que no son los de la tabla."""
        tabla, meta = _lateral_cache("pm25", "I")
        panel = _red2().paneles["pm25"]
        del_fijado = {
            "model_ready falso": {**meta, "model_ready": False},
            "model_ready como texto": {**meta, "model_ready": "True"},
            "sin source_policy_verified": {k: v for k, v in meta.items() if k != "source_policy_verified"},
            "source_policy_verified falso": {**meta, "source_policy_verified": False},
            "sin policy_sha256": {k: v for k, v in meta.items() if k != "policy_sha256"},
            "policy_sha256 corta": {**meta, "policy_sha256": "ab" * 10},
            "policy_sha256 en mayúsculas": {**meta, "policy_sha256": "AB" * 32},
        }
        for caso, falsos in del_fijado.items():
            with self.subTest(caso=caso):
                with self.assertRaises(ValueError):
                    self._unir(panel, tabla, falsos)
                with self.assertRaises(ValueError):
                    ambiental.comprobar_union(tabla, falsos, self.adaptador, panel=panel)
        propios = {
            "content_sha256 falsa": {**meta, "content_sha256": "2" * 64},
            "variante falsa": {**meta, "variante": "D"},
            "columnas falsas": {**meta, "columnas": list(meta["columnas"])[::-1]},
            "unidades falsas": {**meta, "unidades": {**meta["unidades"], "mc_sp": "hPa"}},
            "decision_sha256 que no es sha256": {**meta, "decision_sha256": "x"},
            "clave de más": {**meta, "otra": 1},
            "sin panel_sha256": {k: v for k, v in meta.items() if k != "panel_sha256"},
            "sin el conteo tras la última hora": {k: v for k, v in meta.items() if k != TRAS},
            "conteo negativo": {**meta, TRAS: -1},
            "conteo que no es entero": {**meta, TRAS: 1.0},
        }
        for caso, falsos in propios.items():
            with self.subTest(caso=caso):
                self._unir(panel, tabla, falsos)                 # el código fijado no mira esto…
                with self.assertRaises(ErrorAmbiental):          # … comprobar_union sí (AMB-12, AMB-13)
                    ambiental.comprobar_union(tabla, falsos, self.adaptador, panel=panel)
        otra = tabla.copy()
        otra.loc[5, "mc_t2m"] = np.float32(otra.loc[5, "mc_t2m"] + 1)
        with self.assertRaises(ErrorAmbiental):
            ambiental.comprobar_union(otra, meta, self.adaptador, panel=panel)

    def test_union_se_niega_con_claves_faltantes(self):
        """§7.1, punto 2."""
        tabla, meta = _lateral_cache("no2", "D")
        panel = _red2().paneles["no2"]
        sin_zona = tabla.copy()
        sin_zona["ts_utc"] = sin_zona["ts_utc"].dt.tz_localize(None)
        con_nulo = tabla.copy()
        con_nulo.loc[3, "estacion"] = pd.NA
        duplicada = pd.concat([tabla, tabla.iloc[:1]], ignore_index=True)
        casos = {"sin ts_utc": tabla.drop(columns=["ts_utc"]), "sin estacion": tabla.drop(columns=["estacion"]),
                 "estacion nula": con_nulo, "ts_utc sin zona": sin_zona, "clave repetida": duplicada}
        for caso, mala in casos.items():
            with self.subTest(caso=caso):
                with self.assertRaises(ValueError):
                    self._unir(panel, mala, meta)
                with self.assertRaises(ValueError):
                    ambiental.comprobar_union(mala, meta, self.adaptador, panel=panel)
        with self.subTest(caso="panel sin ts_utc"):
            with self.assertRaises(ValueError):
                ambiental.comprobar_union(tabla, meta, self.adaptador, panel=panel.drop(columns=["ts_utc"]))
        with self.subTest(caso="panel sin estacion"):
            with self.assertRaises(ValueError):
                ambiental.comprobar_union(tabla, meta, self.adaptador, panel=panel.drop(columns=["estacion"]))

    def test_union_se_niega_con_columnas_solapadas(self):
        """§7.1, punto 2."""
        for variante, columna in (("I", "mc_t2m"), ("D", "dmc_R_p"), ("D", "fe_wind")):
            tabla, meta = _lateral_cache("pm25", variante)
            panel = _red2().paneles["pm25"].copy()
            panel[columna] = np.float32(0.0)
            with self.subTest(variante=variante, columna=columna):
                with self.assertRaises(ValueError):
                    self._unir(panel, tabla, meta)
                with self.assertRaises(ValueError):
                    ambiental.comprobar_union(tabla, meta, self.adaptador, panel=panel)
        tabla, meta = _lateral_cache("pm25", "I")
        with self.assertRaises(ValueError):                      # «Covariables vacías»
            self._unir(_red2().paneles["pm25"], tabla[list(ambiental.CLAVES)], meta)

    def test_union_se_niega_sin_el_adaptador(self):
        tabla, meta = _lateral_cache("pm25", "I")
        with self.assertRaises(ErrorAmbiental):
            ambiental.comprobar_union(tabla, meta, types.SimpleNamespace())
        with self.assertRaises(ErrorAmbiental):
            ambiental.comprobar_union(tabla, list(meta.items()), self.adaptador)

    def test_union_se_niega_con_un_adaptador_falso(self):
        """AMB-13 (H4): las comprobaciones propias de comprobar_union, con adaptadores que llaman al real y después
        desordenan valores, cambian el panel, el índice o el orden de las columnas, o devuelven otra identidad."""
        tabla, meta = _lateral_cache("pm25", "I")
        panel = _red2().paneles["pm25"]
        real = self.adaptador.unir_sidecar
        primera = meta["columnas"][0]

        def falso(cambio):
            def unir_sidecar(base, lateral, *, metadata):
                resultado, identidad = real(base, lateral, metadata=metadata)
                return cambio(resultado.copy(), dict(identidad))
            return types.SimpleNamespace(unir_sidecar=unir_sidecar)

        def valores_al_reves(r, i):
            r[primera] = r[primera].to_numpy()[::-1]
            return r, i

        def otra_fila(r, i):
            r.loc[r.index[0], primera] = np.float32(r[primera].iloc[0] + 1)
            return r, i

        def panel_cambiado(r, i):
            r["estacion"] = r["estacion"].iloc[::-1].to_numpy()
            return r, i

        def otro_indice(r, i):
            return r.set_axis(np.arange(len(r)) + 1), i

        def columnas_desordenadas(r, i):
            return r[[c for c in r.columns if c not in meta["columnas"]] + meta["columnas"][::-1]], i

        def sin_una_fila(r, i):
            return r.iloc[1:], i
        casos = {
            "valores al revés": valores_al_reves, "un valor cambiado": otra_fila, "panel cambiado": panel_cambiado,
            "otro índice": otro_indice, "columnas desordenadas": columnas_desordenadas, "una fila menos": sin_una_fila,
            "identidad con otra política": lambda r, i: (r, {**i, "policy_sha256": "9" * 64}),
            "identidad con otras columnas": lambda r, i: (r, {**i, "columns": i["columns"][::-1]}),
            "identidad con otras filas": lambda r, i: (r, {**i, "sidecar_rows": i["sidecar_rows"] + 1}),
            "identidad con otro panel": lambda r, i: (r, {**i, "panel_rows": i["panel_rows"] - 1}),
            "identidad sin huella": lambda r, i: (r, {**i, "content_sha256": "x"}),
            "identidad con otro artefacto": lambda r, i: (r, {**i, "source_artifact_sha256": "8" * 64}),
            "identidad con una clave de más": lambda r, i: (r, {**i, "otra": 1}),
            "identidad sin una clave": lambda r, i: (r, {k: v for k, v in i.items() if k != "panel_rows"}),
            "identidad que no es un diccionario": lambda r, i: (r, list(i.items())),
        }
        identidad = ambiental.comprobar_union(tabla, meta, falso(lambda r, i: (r, i)), panel=panel)   # el inocuo pasa
        self.assertEqual(identidad, ambiental.comprobar_union(tabla, meta, self.adaptador, panel=panel))
        for caso, cambio in casos.items():
            with self.subTest(caso=caso):
                with self.assertRaises(ErrorAmbiental):
                    ambiental.comprobar_union(tabla, meta, falso(cambio), panel=panel)


# ---------------------------------------------------------------------------
# Las columnas de I y de D (MC-28; AMB-1 a AMB-5, AMB-12)
# ---------------------------------------------------------------------------
class PruebasAmbiental(unittest.TestCase):
    def test_columnas_de_i_y_d(self):
        """9 mc_*; 9 fe_* y 5 dmc_R_* (MC-28)."""
        self.assertEqual(ambiental.COLUMNAS_MC, tuple(f"mc_{s}" for s in tipos.SUFIJOS_EL))
        self.assertEqual(len(ambiental.COLUMNAS_MC), 9)
        self.assertEqual(ambiental.COLUMNAS_VARIANTE["D"], tuple(f"fe_{s}" for s in tipos.SUFIJOS_EL)
                         + ("dmc_R_T", "dmc_R_Td", "dmc_R_u", "dmc_R_v", "dmc_R_p"))
        self.assertEqual(len(ambiental.COLUMNAS_VARIANTE["D"]), 14)
        for pol in tipos.CONTAMINANTES_M6:
            for variante, esquema in (("I", tipos.ESQUEMA_LATERAL_I), ("D", tipos.ESQUEMA_LATERAL_D)):
                with self.subTest(pol=pol, variante=variante):
                    tabla, meta = _lateral_cache(pol, variante)
                    tipos.validar_esquema(tabla, esquema, nombre="lateral")
                    self.assertEqual(tabla.attrs["esquema"], esquema.version)
                    self.assertEqual(list(tabla.columns), list(esquema))
                    self.assertEqual(meta["columnas"], [c for c in esquema if c not in ambiental.CLAVES])
                    self.assertTrue((tabla[meta["columnas"]].dtypes == np.float32).all())
                    self.assertEqual(str(tabla["ts_utc"].dtype), "datetime64[ns, UTC]")
        tabla = _lateral_cache("pm25", "I")[0]
        with self.assertRaises(ValueError):
            tipos.validar_esquema(tabla, tipos.ESQUEMA_LATERAL_D, nombre="I no es D")

    def test_convencion_de_el_features(self):
        """MC-28: los sufijos, los kelvin y arctan2(u, v) de _features.py (por AST, con su huella); Magnus distinto."""
        regla = ambiental.regla_el(_AP)
        self.assertEqual(regla["sha256"], fijados.SHA_FEATURES)
        self.assertEqual(ambiental.diferencias_con_el(regla), [])
        self.assertEqual(regla["direccion"], ("el_u10", "el_v10"))
        self.assertEqual(sorted(n[3:] for n in regla["meteorologicas"]), sorted(tipos.SUFIJOS_EL))
        mala = {**regla, "direccion": ("el_v10", "el_u10")}
        self.assertTrue(any("dirección" in d for d in ambiental.diferencias_con_el(mala)))
        igual = {**regla, "magnus": (6.112, 17.625, 243.04)}
        self.assertTrue(ambiental.diferencias_con_el(igual))
        for variante in ("I", "D"):
            unidades = ambiental.UNIDADES[variante]
            for s in tipos.SUFIJOS_EL:
                prefijo = "mc_" if variante == "I" else "fe_"
                self.assertEqual(unidades[prefijo + s], tipos.UNIDADES_EL[s])
        self.assertEqual({ambiental.UNIDADES["D"][c] for c in tipos.COLUMNAS_R_D}, {"K", "m/s", "1"})
        self.assertEqual(ambiental.UNIDADES["D"]["dmc_R_p"], "1")
        self.assertEqual(set(tipos.UNIDADES_EL.values()), {"K", "Pa", "%", "m/s", "1"})

    def test_unidades(self):
        """K, Pa, %, m/s y adimensional: las columnas frente al fondo y al producto en °C y hPa (AMB-3, AMB-4)."""
        F = fondo_era5l.campos_fondo(_mes_201901(), _operador().puntos_fondo(np.arange(len(_celdas().tabla))),
                                     _umbrales())
        d = _columnas("D", float64=True)
        np.testing.assert_array_equal(d["fe_t2m"], F["T_F"] + K)
        np.testing.assert_array_equal(d["fe_d2m"], F["Td_F"] + K)
        np.testing.assert_array_equal(d["fe_sp"], F["p_F"] * 100.0)
        np.testing.assert_array_equal(d["fe_u10"], F["u_F"])
        np.testing.assert_array_equal(d["fe_v10"], F["v_F"])
        hr = np.clip(numerico.hr_desde(F["T_F"], F["Td_F"]), 0, 100)
        np.testing.assert_array_equal(d["fe_rh"], hr)
        i = _columnas("I")
        for c in ("mc_t2m", "mc_d2m"):
            x = i[c][np.isfinite(i[c])]
            self.assertTrue(((x > 200) & (x < 330)).all(), c)
        sp = i["mc_sp"][np.isfinite(i["mc_sp"])]
        self.assertTrue(((sp > 40000) & (sp < 110000)).all())
        rh = i["mc_rh"][np.isfinite(i["mc_rh"])]
        self.assertTrue(((rh >= 0) & (rh <= 100)).all())
        self.assertGreater(rh.max() - rh.min(), 5)
        np.testing.assert_allclose(i["mc_wdir_sin"] ** 2 + i["mc_wdir_cos"] ** 2, 1.0, rtol=0, atol=1e-6)
        self.assertTrue(np.isfinite(i["mc_t2m"]).all())
        for c, x in i.items():
            self.assertEqual(x.dtype, np.float32, c)

    def test_i_y_d_difieren_solo_en_integrar(self):
        """Anexo B y AMB-4: mc_t2m = fe_t2m + dmc_R_T (K), mc_d2m = mín(fe_d2m + dmc_R_Td, mc_t2m), mc_u10 y mc_v10
        sumados, mc_sp = fe_sp·exp(dmc_R_p); HR, rapidez y dirección desde esos valores, en float64 y en float32."""
        for ganador in (G_MIXTO, G_CON_C, G_OTRO):
            with self.subTest(ganador=ganador):
                i = _columnas("I", ganador, float64=True)
                d = _columnas("D", ganador, float64=True)
                for c in i:
                    self.assertTrue(np.isfinite(i[c]).all(), c)
                np.testing.assert_allclose(i["mc_t2m"], d["fe_t2m"] + d["dmc_R_T"], rtol=0, atol=1e-10)
                np.testing.assert_allclose(i["mc_d2m"], np.minimum(d["fe_d2m"] + d["dmc_R_Td"], i["mc_t2m"]), rtol=0,
                                           atol=1e-10)
                np.testing.assert_allclose(i["mc_u10"], d["fe_u10"] + d["dmc_R_u"], rtol=0, atol=1e-12)
                np.testing.assert_allclose(i["mc_v10"], d["fe_v10"] + d["dmc_R_v"], rtol=0, atol=1e-12)
                np.testing.assert_allclose(i["mc_sp"], d["fe_sp"] * np.exp(d["dmc_R_p"]), rtol=1e-14, atol=0)
                hr = np.clip(numerico.hr_desde(i["mc_t2m"] - K, i["mc_d2m"] - K), 0, 100)
                np.testing.assert_allclose(i["mc_rh"], hr, rtol=0, atol=1e-9)
                np.testing.assert_allclose(i["mc_wind"], np.sqrt(i["mc_u10"] ** 2 + i["mc_v10"] ** 2), rtol=1e-14)
                ang = np.arctan2(i["mc_u10"], i["mc_v10"])
                np.testing.assert_allclose(i["mc_wdir_sin"], np.sin(ang), rtol=0, atol=1e-14)
                np.testing.assert_allclose(i["mc_wdir_cos"], np.cos(ang), rtol=0, atol=1e-14)
                for s in ("t2m", "d2m", "rh", "sp", "wind"):
                    self.assertFalse(np.array_equal(i[f"mc_{s}"], d[f"fe_{s}"]), s)   # R no es 0
                i32, d32 = _columnas("I", ganador), _columnas("D", ganador)
                for c in i32:
                    np.testing.assert_array_equal(i32[c], i[c].astype(np.float32))
                for c in d32:
                    np.testing.assert_array_equal(d32[c], d[c].astype(np.float32))
                np.testing.assert_allclose(i32["mc_t2m"], d32["fe_t2m"] + d32["dmc_R_T"], rtol=0, atol=1e-4)

    def test_dmc_R_y_mc_son_los_de_producto(self):
        """AMB-5: dmc_R_* es la R de producto.correccion del ganador ambiental, bit a bit, y mc_* sale de producto.campos
        con esa R (el mismo soporte que la producción)."""
        U, cl = _umbrales(), _celdas()
        h = _horas_mes(2019, 1)
        for ganador in (G_MIXTO, G_CON_C, G_OTRO):
            with self.subTest(ganador=ganador):
                op = _operador(ganador)
                F = fondo_era5l.campos_fondo(_mes_201901(), op.puntos_fondo(np.arange(op.celdas.size)), U)
                puntos = {"ids": op.celdas, "lat": op.lat, "lon": op.lon, "z": op.z}
                R = {}
                for g, cand in ganador:
                    variables = producto.VARIABLES_DE_GRUPO[Grupo(g)]
                    R.update(producto.correccion(cand, {v: HIPER_DE[cand][v] for v in variables}, puntos, h, _datos(),
                                                 umbrales=U, uso=Uso.AMBIENTAL, fondo=F, estaticos=cl.estaticos,
                                                 celdas=op.celdas))
                d = _columnas("D", ganador, float64=True)
                for col, clave in ambiental.R_DE_COLUMNA.items():
                    np.testing.assert_array_equal(d[col], R[clave], err_msg=col)
                    self.assertGreater(np.nanmax(np.abs(R[clave])), 0, col)
                campos = producto.campos(F, R)
                i = _columnas("I", ganador, float64=True)
                np.testing.assert_array_equal(i["mc_t2m"], campos["T"] + K)
                np.testing.assert_array_equal(i["mc_d2m"], campos["Td"] + K)
                np.testing.assert_array_equal(i["mc_rh"], campos["HR"])
                np.testing.assert_array_equal(i["mc_sp"], campos["p"] * 100.0)
                np.testing.assert_array_equal(i["mc_u10"], campos["u"])
                np.testing.assert_array_equal(i["mc_wind"], campos["rapidez"])
        # Lejos de las estaciones DMC (Concepción), A, B y AB vuelven al fondo: R = 0.
        op = _operador(G_MIXTO)
        lejos = cl.monitores[[_centro(c)[0] < -36.0 for c in cl.monitores]]
        self.assertGreater(lejos.size, 0)
        d = _columnas("D", G_MIXTO, celdas=lejos, float64=True)
        for col in ambiental.COLUMNAS_R:
            np.testing.assert_array_equal(d[col], 0.0)
        self.assertTrue(np.isfinite(d["fe_t2m"]).all())
        del op

    def test_mc_d2m_recortado_donde_td_supera_a_t(self):
        """AMB-3 a AMB-5 (H4): en celda-horas sembradas con Td_F + R_Td > T_F + R_T, dmc_R_Td es la R_Td de
        producto.correccion antes del mín y mc_d2m = mc_t2m (HR 100), en float64 y en float32. En «cambio», con las
        redes de T y de Td distintas, mc_d2m se recorta contra la T de la red de Td y queda sobre mc_t2m en algunas:
        dentro de la TF, I no es D integrada (P-AMB-1)."""
        U, cl = _umbrales(), _celdas()
        n_sat = 48
        meses = {201901: _mes_saturado(201901, n_sat)}
        h = _horas_mes(2019, 1)
        op = _operador(G_B)
        F = fondo_era5l.campos_fondo(meses[201901], op.puntos_fondo(np.arange(op.celdas.size)), U)
        np.testing.assert_array_equal(F["Td_F"][:n_sat], F["T_F"][:n_sat])          # el recorte de §4.1
        puntos = {"ids": op.celdas, "lat": op.lat, "lon": op.lon, "z": op.z}
        R = producto.correccion("B", {v: HIPER_DE["B"][v] for v in ("T", "Td")}, puntos, h, _datos(), umbrales=U,
                                uso=Uso.AMBIENTAL, fondo=F, estaticos=cl.estaticos, celdas=op.celdas)
        kw = dict(horas=h, meses=meses)
        d = _columnas("D", G_B, float64=True, **kw)
        i = _columnas("I", G_B, float64=True, **kw)
        np.testing.assert_array_equal(d["dmc_R_T"], R["R_T"])
        np.testing.assert_array_equal(d["dmc_R_Td"], R["R_Td"])
        recorta = F["Td_F"] + R["R_Td"] > F["T_F"] + R["R_T"]
        self.assertGreater(int(recorta.sum()), 20)
        self.assertGreater(int((~recorta).sum()), 20)
        self.assertFalse(recorta[n_sat:].any())               # sólo donde se sembró
        np.testing.assert_array_equal(i["mc_d2m"][recorta], i["mc_t2m"][recorta])
        np.testing.assert_allclose(i["mc_rh"][recorta], 100.0, rtol=0, atol=1e-12)
        self.assertTrue((d["fe_d2m"] + d["dmc_R_Td"] > i["mc_d2m"])[recorta].all())   # dmc_R_Td, antes del mín
        menor = F["Td_F"] + R["R_Td"] < F["T_F"] + R["R_T"]
        self.assertTrue((i["mc_d2m"] < i["mc_t2m"])[menor].all())
        self.assertTrue((i["mc_d2m"] <= i["mc_t2m"]).all())
        np.testing.assert_allclose(i["mc_d2m"], np.minimum(d["fe_d2m"] + d["dmc_R_Td"], i["mc_t2m"]), rtol=0,
                                   atol=1e-10)
        i32, d32 = _columnas("I", G_B, **kw), _columnas("D", G_B, **kw)
        np.testing.assert_array_equal(i32["mc_d2m"][recorta], i32["mc_t2m"][recorta])
        np.testing.assert_array_equal(d32["dmc_R_Td"], R["R_Td"].astype(np.float32))
        # «cambio» (AMB-10, P-AMB-1): T con las estaciones de b menor, Td con otras.
        codigos = op.codigos
        red_T, red_Td = codigos[:3], codigos[5:9]
        redes = {"T": lambda a: red_T, "Td": lambda a: red_Td, "rapidez": lambda a: None, "p": lambda a: None}
        de_td = {**redes, "T": lambda a: red_Td}
        ic = _columnas("I", G_B, float64=True, redes=redes, **kw)
        dc = _columnas("D", G_B, float64=True, redes=redes, **kw)
        d_td = _columnas("D", G_B, float64=True, redes=de_td, **kw)
        self.assertTrue((ic["mc_d2m"] > ic["mc_t2m"]).any())
        self.assertFalse(np.allclose(ic["mc_d2m"], np.minimum(dc["fe_d2m"] + dc["dmc_R_Td"], ic["mc_t2m"]), rtol=0,
                                     atol=1e-10))
        np.testing.assert_allclose(ic["mc_d2m"], np.minimum(dc["fe_d2m"] + dc["dmc_R_Td"],
                                                            dc["fe_t2m"] + d_td["dmc_R_T"]), rtol=0, atol=1e-10)
        np.testing.assert_allclose(ic["mc_t2m"], dc["fe_t2m"] + dc["dmc_R_T"], rtol=0, atol=1e-10)

    def test_receta_de_content_sha256(self):
        """AMB-18 (H9): la receta escrita, rehecha con sólo hashlib, json y struct (sin este módulo), da content_sha256
        en I y en D, también con NaN de bits no canónicos."""
        def receta(tabla, esquema, columnas):
            n = len(tabla)
            cab = json.dumps({"columnas": list(tabla.columns), "esquema": esquema.version, "filas": n,
                              "tipos": [esquema[c] for c in tabla.columns]}, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
            partes = [cab, b"".join(str(c).encode("utf-8") + b"\x00" for c in tabla["estacion"].tolist()),
                      struct.pack(f"<{n}q", *pd.DatetimeIndex(tabla["ts_utc"]).tz_convert("UTC").asi8.tolist())]
            for c in columnas:
                x = tabla[c].to_numpy(np.float32)
                bits = [0x7FC00000 if v != v else struct.unpack("<I", struct.pack("<f", v))[0] for v in x.tolist()]
                partes.append(struct.pack(f"<{n}I", *bits))
            return hashlib.sha256(b"".join(partes)).hexdigest()
        self.assertEqual(int(np.array([ambiental._NAN32]).view(np.uint32)[0]), 0x7FC00000)
        for variante, esquema in (("I", tipos.ESQUEMA_LATERAL_I), ("D", tipos.ESQUEMA_LATERAL_D)):
            with self.subTest(variante=variante):
                tabla, meta = _lateral_cache("pm25", variante)
                self.assertEqual(receta(tabla, esquema, meta["columnas"]), meta["content_sha256"])
                otra = tabla.copy()
                for k, c in enumerate(meta["columnas"][:3]):
                    columna = otra[c].to_numpy(np.float32).copy()
                    columna.view(np.uint32)[k:k + 2] = (0x7FC00001, 0xFFC00000)
                    otra[c] = columna
                self.assertTrue(otra[meta["columnas"][0]].isna().any())
                self.assertEqual(receta(otra, esquema, meta["columnas"]), ambiental.huella_contenido(otra))
                self.assertNotEqual(ambiental.huella_contenido(otra), meta["content_sha256"])

    def test_lateral_es_mc_bloque_en_la_celda_del_monitor(self):
        """AMB-1: la lateral de cada monitor es, bit a bit, la columna de mc_bloque de su celda (pliegues_v2_red2.json),
        en las horas del panel; las filas son las claves distintas del panel, ordenadas."""
        r2 = _red2()
        celda_de = dict(zip(r2.monitores["estacion"].astype(str), r2.monitores["celda"].astype(np.int64)))
        for pol, variante in (("pm25", "I"), ("no2", "D")):
            tabla, _ = _lateral_cache(pol, variante)
            panel = r2.paneles[pol]
            claves = panel[["estacion", "ts_utc"]].drop_duplicates().sort_values(["estacion", "ts_utc"])
            self.assertEqual(len(tabla), len(claves))
            np.testing.assert_array_equal(tabla["estacion"].to_numpy(object), claves["estacion"].to_numpy(object))
            np.testing.assert_array_equal(tabla["ts_utc"].dt.tz_localize(None).to_numpy(), claves["ts_utc"].to_numpy())
            celdas = np.unique(list(celda_de.values()))
            bloque = ambiental.mc_bloque(celdas, _horas_mes(2019, 1), variante, operador=_operador(), meses=_meses,
                                         datos=_datos(), umbrales=_umbrales(), estaticos=_celdas().estaticos)
            ts = tabla["ts_utc"].dt.tz_localize(None).to_numpy()
            fila = pd.MultiIndex.from_arrays([bloque["celda"].to_numpy(),
                                              bloque["ts_utc"].dt.tz_localize(None).to_numpy()])
            pos = fila.get_indexer(pd.MultiIndex.from_arrays(
                [np.array([celda_de[e] for e in tabla["estacion"]]), ts]))
            self.assertTrue((pos >= 0).all())
            for c in ambiental.COLUMNAS_VARIANTE[variante]:
                np.testing.assert_array_equal(tabla[c].to_numpy(), bloque[c].to_numpy()[pos], err_msg=c)
            if pol == "no2":
                self.assertNotIn("S012", set(tabla["estacion"]))

    def test_panel_en_solo_lectura(self):
        """AMB-2 (H4): el panel recién leído de sus bytes no cambia (contenido, tipos, índice, attrs y la huella de su
        forma en pandas), comparado contra una copia tomada antes de cualquier uso; con zona y sin ella."""
        datos = _red2().bytes_panel["pm25"]
        for zona in (None, "UTC", "America/Santiago"):
            with self.subTest(zona=zona):
                panel = pd.read_parquet(io.BytesIO(datos))
                if zona is not None:
                    panel["ts_utc"] = panel["ts_utc"].dt.tz_localize("UTC").dt.tz_convert(zona)
                panel.attrs["marca"] = "antes"
                copia = panel.copy(deep=True)
                attrs = copy.deepcopy(panel.attrs)
                huella = pd.util.hash_pandas_object(panel, index=True).to_numpy().tobytes()
                _lateral("pm25", "D", panel=panel)
                pd.testing.assert_frame_equal(panel, copia, check_exact=True)
                self.assertEqual(panel.attrs, attrs)
                self.assertEqual(pd.util.hash_pandas_object(panel, index=True).to_numpy().tobytes(), huella)
        _lateral("pm25", "D", panel=datos)
        self.assertEqual(_sha(datos), _red2().sha_panel["pm25"])

    def test_metadatos(self):
        """§2.3 del diseño y AMB-12: exactamente tipos.METADATOS_LATERAL, con la red 2 (R21, MC-09)."""
        r2 = _red2()
        for variante in ("I", "D"):
            tabla, meta = _lateral_cache("no2", variante)
            with self.subTest(variante=variante):
                self.assertEqual(tuple(meta), ambiental.METADATOS_LATERAL)
                self.assertEqual(ambiental.METADATOS_LATERAL[:len(tipos.METADATOS_LATERAL)], tipos.METADATOS_LATERAL)
                self.assertEqual(meta[TRAS], 0)
                self.assertIs(meta["model_ready"], True)
                self.assertIs(meta["source_policy_verified"], True)
                self.assertEqual(meta["policy_sha256"], POLITICA)
                self.assertEqual(meta["variante"], variante)
                self.assertEqual(meta["unidades"], dict(ambiental.UNIDADES[variante]))
                self.assertEqual(meta["content_sha256"], ambiental.huella_contenido(tabla))
                self.assertEqual(meta["decision_sha256"], _sha(_decision_bytes(G_MIXTO)))
                self.assertEqual(meta["operador_sha256"], _operador().sha256)
                self.assertEqual(meta["panel_sha256"], r2.sha_panel["no2"])
                self.assertEqual(meta["pliegues_sha256"], _sha(r2.pliegues))
                ceguera.vigilar_salida("ambiental/lateral_no2_D.json", meta, clase="insumo")
        tabla, meta = _lateral_cache("no2", "I")
        otra = tabla.copy()
        otra.loc[0, "mc_rh"] = np.float32(np.nan)
        self.assertNotEqual(ambiental.huella_contenido(otra), meta["content_sha256"])
        # El NaN canónico (H4): la columna se arma desde un arreglo de numpy con bits de NaN no canónicos, y se
        # comprueba que la tabla los conserva antes de pedir la huella.
        canonica = ambiental.huella_contenido(otra)
        for patron in (0x7FC00001, 0xFFC00000, 0x7F800001, 0xFFFFFFFF):
            with self.subTest(nan=hex(patron)):
                columna = otra["mc_rh"].to_numpy(np.float32).copy()
                columna.view(np.uint32)[0] = patron
                nan_otro = otra.copy()
                nan_otro["mc_rh"] = columna
                self.assertEqual(int(nan_otro["mc_rh"].to_numpy().view(np.uint32)[0]), patron)
                self.assertTrue(np.isnan(nan_otro["mc_rh"].iloc[0]))
                self.assertEqual(ambiental.huella_contenido(nan_otro), canonica)
        # content_sha256 cambia si cambian la hora o el código de una fila, o el orden de dos (H4).
        for caso, cambio in {"ts_utc": lambda t: t.assign(ts_utc=t["ts_utc"].where(t.index != 0,
                                                                                    t["ts_utc"] + pd.Timedelta(hours=1))),
                             "código": lambda t: t.assign(estacion=t["estacion"].where(t.index != 0, "S999")),
                             "orden": lambda t: t.iloc[[1, 0, *range(2, len(t))]].reset_index(drop=True)}.items():
            with self.subTest(cambio=caso):
                cambiada = cambio(tabla.copy())
                tipos.validar_esquema(cambiada, tipos.ESQUEMA_LATERAL_I, nombre=caso)
                self.assertNotEqual(ambiental.huella_contenido(cambiada), meta["content_sha256"])
        # Determinismo: la misma lateral dos veces da los mismos metadatos.
        self.assertEqual(_lateral("no2", "I")[1], meta)
        # Con el contenido de decision.json en vez de sus bytes, se exige su sha256 y da lo mismo.
        contenido = ambiental.leer_decision(_decision_bytes(G_MIXTO))[0]
        con_dict = _lateral("no2", "I", decision=contenido, decision_sha256=meta["decision_sha256"])[1]
        self.assertEqual(con_dict, meta)

    def test_lateral_se_niega(self):
        """AMB-1, AMB-2, AMB-8 y AMB-9: lo que no calza detiene la lateral (ErrorAmbiental), sin tocar el panel."""
        r2 = _red2()
        panel = r2.paneles["pm25"]
        ajeno = panel.iloc[:2].copy()
        ajeno["estacion"] = pd.array(["S999", "S999"], dtype="string")
        media_hora = panel.copy()
        media_hora.loc[0, "ts_utc"] = media_hora.loc[0, "ts_utc"] + pd.Timedelta(minutes=30)
        otra_celda = panel.copy()
        otra_celda.loc[0, "celda"] = otra_celda.loc[0, "celda"] + 1
        con_s012 = pd.concat([r2.paneles["no2"], panel[panel["estacion"] == "S012"].iloc[:2]], ignore_index=True)
        datos = _datos()
        otras = dict(datos.estaciones)
        otras["330001"] = dataclasses.replace(otras["330001"], lat=otras["330001"].lat + 0.01)
        b_ajeno, pl_ajeno = _registro_con("pm25", pd.concat([panel, ajeno], ignore_index=True))
        b_s012, pl_s012 = _registro_con("no2", con_s012)
        U = _umbrales()
        casos = {
            "o3": (dict(pol="o3", panel=panel), "contaminante"),
            "panel_sha256 que no es la del registro": (dict(panel_sha256="3" * 64), "R21, MC-09"),
            "otro decision.json": (dict(decision=_decision_bytes(G_OTRO)), "no es el del operador"),
            "monitor que no está en pliegues": (dict(panel=b_ajeno, pliegues=pl_ajeno), "S999"),
            "monitor de otro contaminante": (dict(pol="no2", panel=b_s012, pliegues=pl_s012), "S012"),
            "hora que no es HH:00": (dict(panel=media_hora), "HH:00"),
            "celda del panel distinta": (dict(panel=otra_celda), "celda del panel"),
            "falta el mes": (dict(meses={}), "falta el mes"),
            "otras estaciones": (dict(datos=dataclasses.replace(datos, estaciones=otras)), "entrenamiento"),
            "pliegues_sha256 distinta": (dict(pliegues_sha256="4" * 64), "pliegues_sha256"),
            "policy_sha256 inválida": (dict(policy_sha256="abc"), "policy_sha256"),
            "policy_sha256 que no es la de la política": (dict(policy_sha256="1" * 64), "policy_sha256 no es"),
            "política que no es JSON": (dict(politica=b"\xff\xfe"), "JSON"),
            "política que no es una lista": (dict(politica=entorno.json_canonico({"a": 1})), "lista"),
            "política vacía": (dict(politica=b"[]"), "lista no vacía"),
            "política con NaN": (dict(politica=b'[{"x": NaN}]'), "NaN"),
            "política con una clave repetida": (dict(politica=b'[{"x": 1, "x": 2}]'), "se repite"),
            "política como huella": (dict(politica=POLITICA), "bytes"),
            "variante desconocida": (dict(variante="E"), "variante"),
            "pliegues sin su sha256": (dict(pliegues=json.loads(r2.pliegues)), "pliegues_sha256"),
            "decision sin su sha256": (dict(decision=ambiental.leer_decision(_decision_bytes(G_MIXTO))[0]),
                                       "decision_sha256"),
            "panel sin ts_utc": (dict(panel=panel.drop(columns=["ts_utc"])), "panel"),
            "ts_utc que no es fecha": (dict(panel=panel.assign(ts_utc=np.arange(len(panel)))), "fecha"),
            "h_ultima que no es entera": (dict(h_ultima=float(H_ULTIMA)), "h_ultima"),
            "h_ultima booleana": (dict(h_ultima=True), "h_ultima"),
            "años mal dados": (dict(anios="2019"), "anios"),
            "años repetidos": (dict(anios=[2019, 2019]), "anios"),
            "otros umbrales": (dict(umbrales=_UmbralesCambiados(U, {"NUC_CORTE": U.a("NUC_CORTE") + 1})),
                               "umbrales no son los del operador"),
        }
        copia = panel.copy(deep=True)
        for caso, (kw, motivo) in casos.items():
            with self.subTest(caso=caso):
                kw = dict(kw)
                pol = kw.pop("pol", "pm25")
                variante = kw.pop("variante", "I")
                with self.assertRaisesRegex(ErrorAmbiental, motivo):
                    _lateral(pol, variante, **kw)
        pd.testing.assert_frame_equal(panel, copia)

    def test_insumo_en_ambiental(self):
        """MC-02, D3 y P98: las laterales y el operador son insumo en ambiental/ (y en m6/ambiental/ en la rama 3), pasan
        por ceguera.vigilar_salida y salidas.escribir los escribe con sus metadatos; ahí no se declaran métrica."""
        tabla_i, meta_i = _lateral_cache("pm25", "I")
        tabla_d, meta_d = _lateral_cache("pm25", "D")
        op = _operador()
        for ruta in ("ambiental/lateral_pm25_I.parquet", "m6/ambiental/lateral_pm25_I.parquet"):
            self.assertEqual(ceguera.clase_de_ruta(ruta), "insumo")
        ceguera.vigilar_salida("ambiental/lateral_pm25_I.parquet", tabla_i, clase="insumo")
        ceguera.vigilar_salida("ambiental/lateral_pm25_D.parquet", tabla_d, clase="insumo")
        ceguera.vigilar_salida("ambiental/operador_grilla.bin", op.a_bytes(), clase="insumo")
        ceguera.vigilar_salida("m6/ambiental/lateral_pm25_D.parquet", tabla_d, clase="insumo")
        with self.assertRaises(ceguera.SalidaProhibida):
            ceguera.vigilar_salida("ambiental/lateral_pm25_D.parquet", tabla_d, clase="metrica")
        with tempfile.TemporaryDirectory() as tmp:
            for nombre, tabla, meta, esquema in (("lateral_pm25_I.parquet", tabla_i, meta_i, tipos.ESQUEMA_LATERAL_I),
                                                 ("lateral_pm25_D.parquet", tabla_d, meta_d, tipos.ESQUEMA_LATERAL_D)):
                sha = salidas.escribir(f"ambiental/{nombre}", tabla, clase="insumo", esquema=esquema, raiz=tmp,
                                       metadatos=meta)
                ruta = Path(tmp) / "ambiental" / nombre
                self.assertEqual(sha, _sha(ruta.read_bytes()))
                leida = pd.read_parquet(ruta)
                pd.testing.assert_frame_equal(leida, tabla, check_like=False)
                self.assertEqual(leida.attrs["esquema"], esquema.version)
                self.assertEqual(leida.attrs["metadatos"], meta)
                self.assertEqual(ambiental.huella_contenido(leida), meta["content_sha256"])
            sha = salidas.escribir("ambiental/operador_grilla.bin", op.a_bytes(), clase="insumo", raiz=tmp)
            self.assertEqual(sha, op.sha256)
            releido = ambiental.leer_operador((Path(tmp) / "ambiental" / "operador_grilla.bin").read_bytes())
            self.assertEqual(releido.sha256, op.sha256)
            salidas.escribir("m6/ambiental/lateral_pm25_D.parquet", tabla_d, clase="insumo",
                             esquema=tipos.ESQUEMA_LATERAL_D, raiz=tmp, metadatos=meta_d)
            with self.assertRaises(ceguera.SalidaProhibida):
                salidas.escribir("ambiental/otra.parquet", tabla_d, clase="resumen", esquema=tipos.ESQUEMA_LATERAL_D,
                                 raiz=tmp)

    def test_direccion_en_calma_y_sin_dato(self):
        """MC-28 (AMB-3): arctan2(u, v) «hacia»; en calma sin 0 y cos 1, como el_wdir_*; NaN sin u o v."""
        s, c = ambiental.direccion_sin_cos(np.array([0.0, 1.0, 0.0, -1.0, NAN, 1.0]),
                                           np.array([0.0, 0.0, 1.0, 0.0, 1.0, NAN]))
        np.testing.assert_allclose(s[:4], [0.0, 1.0, 0.0, -1.0], atol=1e-15)
        np.testing.assert_allclose(c[:4], [1.0, 0.0, 1.0, 0.0], atol=1e-15)
        self.assertTrue(np.isnan(s[4:]).all() and np.isnan(c[4:]).all())
        u = np.array([3.0, -2.0], dtype=np.float32)
        v = np.array([-1.0, 4.0], dtype=np.float32)
        el = (np.sin(np.arctan2(u, v)), np.cos(np.arctan2(u, v)))            # la cuenta de _features.py
        np.testing.assert_allclose(ambiental.direccion_sin_cos(u, v), el, rtol=1e-6)

    def test_magnus_de_mc_rh(self):
        """§7.1: mc_rh usa Magnus 17,625 y 243,04, distinto de el_rh (17,67 y 243,5)."""
        i = _columnas("I", float64=True)
        t, td = i["mc_t2m"] - K, i["mc_d2m"] - K
        a, b = constantes.valor("MAGNUS_AGUA")[1:]
        self.assertEqual((a, b), (17.625, 243.04))
        propio = np.clip(100 * np.exp(a * td / (b + td)) / np.exp(a * t / (b + t)), 0, 100)
        np.testing.assert_allclose(i["mc_rh"], propio, rtol=0, atol=1e-9)
        a_el, b_el = constantes.valor("MAGNUS_EL_FEATURES")
        del_el = np.clip(100 * np.exp(a_el * td / (b_el + td)) / np.exp(a_el * t / (b_el + t)), 0, 100)
        self.assertGreater(np.max(np.abs(i["mc_rh"] - del_el)), 1e-4)


# ---------------------------------------------------------------------------
# El panel atado a su registro, las horas tras el último dato, las partes y la política (AMB-2, AMB-12, AMB-16, AMB-17)
# ---------------------------------------------------------------------------
def _panel_dos_anios(pol: str = "pm25") -> pd.DataFrame:
    """El panel de enero de 2019 y su copia 31 días antes (diciembre de 2018): dos años UTC, claves sin repetir."""
    panel = _red2().paneles[pol]
    antes = panel.copy()
    antes["ts_utc"] = antes["ts_utc"] - pd.Timedelta(days=31)
    return pd.concat([antes, panel], ignore_index=True)


def _ts_de(h: int) -> pd.Timestamp:
    return pd.Timestamp("2000-01-01", tz="UTC") + pd.Timedelta(hours=int(h))


class PruebasPartes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel = _panel_dos_anios()
        cls.datos_panel, cls.pliegues = _registro_con("pm25", cls.panel)
        cls.h_corte = _h("2019-01-12T05")
        cls.meses_corte = {201812: _mes_memoria(201812), 201901: _mes_hasta(201901, cls.h_corte)}
        cls.adaptador = _adaptador()

    def _lat(self, variante="I", **kw):
        return _lateral("pm25", variante, panel=kw.pop("panel", self.datos_panel),
                        pliegues=kw.pop("pliegues", self.pliegues), **kw)

    def test_horas_tras_el_ultimo_dato(self):
        """§3 y AMB-17 (H2): con el panel más allá del último dato de ERA5-Land, las claves posteriores a h_ultima
        quedan fuera de la lateral y se cuentan (claves distintas, un entero); lo demás es bit a bit la lateral entera;
        unir_sidecar les pone NaN; un mes que falta antes de h_ultima, o una hora suya, sigue siendo un error."""
        entera, meta_e = self._lat("I")
        self.assertEqual(meta_e[TRAS], 0)
        self.assertEqual(len(entera), len(self.panel[["estacion", "ts_utc"]].drop_duplicates()))
        cortada, meta_c = self._lat("I", h_ultima=self.h_corte, meses=self.meses_corte)
        dentro = (entera["ts_utc"] <= _ts_de(self.h_corte)).to_numpy()
        self.assertGreater(int((~dentro).sum()), 0)
        self.assertEqual(meta_c[TRAS], int((~dentro).sum()))
        self.assertIsInstance(meta_c[TRAS], int)
        pd.testing.assert_frame_equal(cortada, entera[dentro].reset_index(drop=True), check_exact=True)
        sin = ("content_sha256", TRAS)
        self.assertEqual({k: v for k, v in meta_c.items() if k not in sin},
                         {k: v for k, v in meta_e.items() if k not in sin})
        ceguera.vigilar_salida("ambiental/lateral_pm25_I.parquet", cortada, clase="insumo")
        # La unión: NaN en las claves tras la última hora, valores en las demás.
        ambiental.comprobar_union(cortada, meta_c, self.adaptador, panel=self.panel)
        base = self.panel.copy()
        base["ts_utc"] = base["ts_utc"].dt.tz_localize("UTC")
        unido, identidad = self.adaptador.unir_sidecar(base, cortada, metadata=meta_c)
        tras = (unido["ts_utc"] > _ts_de(self.h_corte)).to_numpy()
        self.assertTrue(unido.loc[tras, meta_c["columnas"]].isna().all().all())
        self.assertFalse(unido.loc[~tras, meta_c["columnas"]].isna().all(axis=1).any())
        self.assertEqual(identidad["sidecar_rows"], len(cortada))
        # Sin ningún mes después de la última hora (h_ultima a fin de diciembre, y sólo ese mes).
        dic, meta_d = self._lat("I", h_ultima=_h("2018-12-31T23"), meses={201812: _mes_memoria(201812)})
        enero = (entera["ts_utc"] >= pd.Timestamp("2019-01-01", tz="UTC")).to_numpy()
        self.assertEqual(meta_d[TRAS], int(enero.sum()))
        pd.testing.assert_frame_equal(dic, entera[~enero].reset_index(drop=True), check_exact=True)
        # h_ultima antes de todo el panel: la lateral vacía, todas contadas, y la unión la acepta.
        vacia, meta_v = self._lat("D", h_ultima=_h("2018-11-30T23"), meses={})
        self.assertEqual((len(vacia), meta_v[TRAS]), (0, len(entera)))
        tipos.validar_esquema(vacia, tipos.ESQUEMA_LATERAL_D, nombre="vacía")
        ambiental.comprobar_union(vacia, meta_v, self.adaptador, panel=self.panel)
        # Un mes que falta antes de la última hora, o una hora que el mes no trae, siguen siendo errores (§3).
        with self.assertRaisesRegex(ErrorAmbiental, "falta el mes"):
            self._lat("I", h_ultima=self.h_corte, meses={201901: self.meses_corte[201901]})
        with self.assertRaisesRegex(ErrorAmbiental, "no trae"):
            self._lat("I", h_ultima=self.h_corte + 5, meses=self.meses_corte)

    def test_panel_atado_a_su_registro(self):
        """AMB-2 (H5): el panel en bytes (huella calculada aquí) da la misma lateral que ya leído; ya leído, con la
        huella declarada, se exigen las filas y las estaciones del registro; y lo que no calza con el registro se
        rechaza."""
        r2 = _red2()
        panel = r2.paneles["pm25"]
        t_df, m_df = _lateral_cache("pm25", "D")
        for kw in (dict(panel=r2.bytes_panel["pm25"]),
                   dict(panel=r2.bytes_panel["pm25"], panel_sha256=r2.sha_panel["pm25"]),
                   dict(panel=bytearray(r2.bytes_panel["pm25"]))):
            t, m = _lateral("pm25", "D", **kw)
            pd.testing.assert_frame_equal(t, t_df, check_exact=True)
            self.assertEqual(m, m_df)
        self.assertEqual(m_df["panel_sha256"], json.loads(r2.pliegues)["contaminantes"]["pm25"]["panel"]["sha256"])
        estaciones = sorted(set(panel["estacion"]))
        una_menos = panel.copy()
        una_menos.loc[una_menos["estacion"] == estaciones[1], "estacion"] = estaciones[0]
        no_parquet = b"no es un parquet"
        casos = {
            "bytes de otro panel": (dict(panel=r2.bytes_panel["no2"]), "R21, MC-09"),
            "panel_sha256 distinta de los bytes": (dict(panel=r2.bytes_panel["pm25"], panel_sha256="3" * 64),
                                                   "panel_sha256 no es"),
            "una fila de menos": (dict(panel=panel.iloc[1:]), "filas"),
            "una fila de más": (dict(panel=pd.concat([panel, panel.iloc[:1]], ignore_index=True)), "filas"),
            "una parte del panel ya leído": (dict(panel=panel[panel["ts_utc"] < "2019-01-15"]), "filas"),
            "una estación de menos con las mismas filas": (dict(panel=una_menos), "estaciones"),
            "registro sin filas": (dict(zip(("panel", "pliegues"), _registro_con("pm25", panel, filas=None))),
                                   "panel.filas"),
            "registro con estaciones en texto": (dict(zip(("panel", "pliegues"),
                                                          _registro_con("pm25", panel, estaciones="12"))),
                                                 "panel.estaciones"),
            "registro sin sha256": (dict(zip(("panel", "pliegues"), _registro_con("pm25", panel, sha256=None))),
                                    "panel.sha256"),
            "bytes que no son un parquet": (dict(panel=no_parquet, pliegues=_registro_con(
                "pm25", panel, sha256=_sha(no_parquet))[1]), "parquet"),
            "panel que no es tabla ni bytes": (dict(panel=panel.to_dict("list")), "panel"),
            "panel ya leído sin su huella": (dict(panel=panel, panel_sha256=None), "panel_sha256"),
        }
        for caso, (kw, motivo) in casos.items():
            with self.subTest(caso=caso):
                with self.assertRaisesRegex(ErrorAmbiental, motivo):
                    _lateral("pm25", "D", **kw)

    def test_unir_partes_es_la_lateral_entera(self):
        """AMB-16 (PED-7): las partes por año (con anios, sobre el panel entero) unidas con unir_partes son bit a bit la
        lateral armada de una vez, con sus metadatos (también el conteo tras la última hora), en I y en D, de memoria
        o releídas del disco; y unir_partes se niega con partes que no son de la misma lateral."""
        kw = dict(h_ultima=self.h_corte, meses=self.meses_corte)
        partes = {}
        for variante in ("I", "D"):
            with self.subTest(variante=variante):
                entera = self._lat(variante, **kw)
                p18 = self._lat(variante, anios=2018, **kw)
                p19 = self._lat(variante, anios=[2019], **kw)
                partes[variante] = (p18, p19)
                self.assertEqual((p18[1][TRAS], p19[1][TRAS]), (0, entera[1][TRAS]))
                self.assertEqual(len(p18[0]) + len(p19[0]), len(entera[0]))
                self.assertTrue((p18[0]["ts_utc"] < pd.Timestamp("2019-01-01", tz="UTC")).all())
                for orden in ((p18, p19), (p19, p18)):
                    tabla, meta = ambiental.unir_partes(list(orden))
                    pd.testing.assert_frame_equal(tabla, entera[0], check_exact=True)
                    self.assertEqual(tabla.attrs, entera[0].attrs)
                    self.assertEqual(meta, entera[1])
                    self.assertEqual(tuple(meta), ambiental.METADATOS_LATERAL)
                with tempfile.TemporaryDirectory() as tmp:          # releídas del disco, como orquestacion (ORQ-27)
                    leidas = []
                    for anio, (t, m) in ((2018, p18), (2019, p19)):
                        nombre = f"ambiental/partes/lateral_pm25_{variante}_{anio}.parquet"
                        salidas.escribir(nombre, t, clase="insumo", esquema=ambiental.ESQUEMA_DE[variante], raiz=tmp,
                                         metadatos=m)
                        leida = pd.read_parquet(Path(tmp) / nombre)
                        leidas.append((leida, leida.attrs["metadatos"]))
                    tabla, meta = ambiental.unir_partes(iter(leidas))
                    pd.testing.assert_frame_equal(tabla, entera[0], check_exact=True)
                    self.assertEqual(meta, entera[1])
                todo = self._lat(variante, anios=(2018, 2019), **kw)
                pd.testing.assert_frame_equal(todo[0], entera[0], check_exact=True)
                self.assertEqual(todo[1], entera[1])
                uno = ambiental.unir_partes([entera])                 # una sola parte: ella misma
                pd.testing.assert_frame_equal(uno[0], entera[0], check_exact=True)
                self.assertEqual(uno[1], entera[1])
        (p18, p19), (q18, q19) = partes["I"], partes["D"]
        alterada = p19[0].copy()
        alterada.loc[0, "mc_t2m"] = np.float32(alterada.loc[0, "mc_t2m"] + 1)
        otro = self._lat("I", anios=2019, ganador=G_OTRO, **kw)
        vacio_2017 = self._lat("I", anios=2017, **kw)
        self.assertEqual((len(vacio_2017[0]), vacio_2017[1][TRAS]), (0, 0))
        tabla, _ = ambiental.unir_partes([p18, vacio_2017, p19])          # una parte vacía no cambia nada
        pd.testing.assert_frame_equal(tabla, ambiental.unir_partes([p18, p19])[0], check_exact=True)
        casos = {
            "sin partes": [], "una parte repetida": [p18, p18], "variantes distintas": [p18, q19],
            "un valor cambiado": [p18, (alterada, p19[1])], "otro operador y otra decisión": [p18, otro],
            "otra política": [p18, self._lat("I", anios=2019, politica=politicas.a_json([{"x": 1}]), **kw)],
            "una tabla sin metadatos": [p18[0]], "una tabla sola": p18[0], "metadatos sin tabla": [(p18[1],)],
        }
        for caso, lista in casos.items():
            with self.subTest(caso=caso):
                with self.assertRaises(ErrorAmbiental):
                    ambiental.unir_partes(lista)

    def test_panel_con_otra_zona_y_claves_repetidas(self):
        """AMB-2 (H4): un panel con ts_utc en otra zona da la misma lateral (en UTC) y la unión lo acepta; uno con
        claves repetidas da la lateral de las claves distintas, y unir_sidecar le pone a cada fila repetida sus
        valores."""
        r2 = _red2()
        panel = r2.paneles["pm25"]
        base_t, base_m = _lateral_cache("pm25", "I")
        santiago = panel.copy()
        santiago["ts_utc"] = santiago["ts_utc"].dt.tz_localize("UTC").dt.tz_convert("America/Santiago")
        t, m = _lateral("pm25", "I", panel=santiago)
        pd.testing.assert_frame_equal(t, base_t, check_exact=True)
        self.assertEqual(m, base_m)
        ambiental.comprobar_union(base_t, base_m, self.adaptador, panel=santiago)
        unido, _ = self.adaptador.unir_sidecar(santiago, base_t, metadata=base_m)
        self.assertFalse(unido[base_m["columnas"]].isna().all(axis=1).any())
        datos_z, pl_z = _registro_con("pm25", santiago)
        t, m = _lateral("pm25", "I", panel=datos_z, pliegues=pl_z)
        pd.testing.assert_frame_equal(t, base_t, check_exact=True)
        distintas = {k for k in m if m[k] != base_m[k]}
        self.assertEqual(distintas, {"panel_sha256", "pliegues_sha256"})
        repetido = pd.concat([panel, panel.iloc[:40]], ignore_index=True)
        datos_r, pl_r = _registro_con("pm25", repetido)
        t, m = _lateral("pm25", "I", panel=datos_r, pliegues=pl_r)
        pd.testing.assert_frame_equal(t, base_t, check_exact=True)
        self.assertEqual({k for k in m if m[k] != base_m[k]}, {"panel_sha256", "pliegues_sha256"})
        identidad = ambiental.comprobar_union(t, m, self.adaptador, panel=repetido)
        self.assertEqual(identidad["panel_rows"], len(repetido))
        base = repetido.copy()
        base["ts_utc"] = base["ts_utc"].dt.tz_localize("UTC")
        unido, _ = self.adaptador.unir_sidecar(base, t, metadata=m)
        np.testing.assert_array_equal(unido[m["columnas"]].iloc[-40:].to_numpy(),
                                      unido[m["columnas"]].iloc[:40].to_numpy())

    def test_politica_verificada(self):
        """AMB-12 (H7): policy_sha256 es la de los bytes de politicas_meteo_v1.json, calculada aquí (la forma de
        politicas.de_json); otra política da otra huella, y la huella esperada, si llega, debe calzar."""
        _, meta = _lateral_cache("pm25", "I")
        self.assertEqual(meta["policy_sha256"], _sha(POLITICA_BYTES))
        self.assertEqual(politicas.de_json(POLITICA_BYTES), json.loads(POLITICA_BYTES))
        otra = politicas.a_json([{"station_code": "330001", "valid_from": "2018-01-01T00:00:00"}])
        _, m2 = _lateral("pm25", "I", politica=otra)
        self.assertEqual(m2["policy_sha256"], _sha(otra))
        self.assertEqual({k for k in m2 if m2[k] != meta[k]}, {"policy_sha256"})
        self.assertEqual(_lateral("pm25", "I", policy_sha256=POLITICA)[1], meta)
        self.assertEqual(_lateral("pm25", "I", politica=memoryview(POLITICA_BYTES))[1], meta)


# ---------------------------------------------------------------------------
# El operador de la grilla (AMB-6 a AMB-8; MC-15)
# ---------------------------------------------------------------------------
class PruebasOperador(unittest.TestCase):
    def test_operador_es_el_de_fondo_era5l_y_candidatos(self):
        """El fondo celda × píxel es fondo_era5l.operador (z_media) y cada núcleo, candidatos.vecinos con el
        entrenamiento de producción (las no excluidas), bit a bit; los pesos k, los de candidatos."""
        U, cl, px = _umbrales(), _celdas(), _pixeles()
        for ganador in (G_MIXTO, G_OTRO):
            op = _operador(ganador)
            orden = np.argsort(cl.tabla["celda"].to_numpy())
            tabla = cl.tabla.iloc[orden]
            z = cl.estaticos.set_index("celda").loc[tabla["celda"], "z_media"].to_numpy()
            fondo = fondo_era5l.operador(tabla["lat"].to_numpy(), tabla["lon"].to_numpy(), z, px.cat, px.pid,
                                         px.z_tabla, U, ids=tabla["celda"].to_numpy())
            np.testing.assert_array_equal(op.celdas, tabla["celda"].to_numpy())
            for campo in ("pix", "w", "dz", "respaldo", "z"):
                np.testing.assert_array_equal(getattr(op, campo), getattr(fondo, campo), err_msg=campo)
            entrenamiento = {c: i for c, i in _red().items() if not i.excluida}
            self.assertEqual(op.codigos, tuple(sorted(entrenamiento)))
            self.assertNotIn("330010", op.codigos)
            puntos = {"ids": op.celdas, "lat": op.lat, "lon": op.lon, "z": op.z}
            esperados = set()
            for v in producto.VARIABLES:
                cand = op.candidato_de(v)
                theta = HIPER_DE[cand.value][v]
                juego = (theta,) if cand.value in ("A", "B") else (theta if cand.value == "AB" else ())
                self.assertEqual(op.nucleo_de[v], tuple(ambiental.etiqueta_hiper(t) for t in juego))
                for t in juego:
                    esperados.add(ambiental.etiqueta_hiper(t))
                    vec = candidatos.vecinos(puntos, entrenamiento, t, U)
                    mio = op.vecinos(ambiental.etiqueta_hiper(t), np.arange(op.celdas.size))
                    for campo in ("est", "d_ef", "grupo_de", "grupo_est"):
                        np.testing.assert_array_equal(getattr(mio, campo), getattr(vec, campo), err_msg=campo)
                    self.assertEqual((mio.codigos, mio.grupos, mio.hiper), (vec.codigos, vec.grupos, vec.hiper))
                    K_mio = op.matriz_nucleo(ambiental.etiqueta_hiper(t))
                    K_can = candidatos._matriz_nucleo(vec)
                    np.testing.assert_array_equal(K_mio.toarray(), K_can.toarray())
                    sub = np.array([5, 0, 17])
                    parcial = op.vecinos(ambiental.etiqueta_hiper(t), sub)
                    np.testing.assert_array_equal(parcial.est, vec.est[sub])
                    np.testing.assert_array_equal(parcial.d_ef, vec.d_ef[sub])
            self.assertEqual(set(op.nucleos), esperados)
            W, DZ = op.matriz_fondo()
            np.testing.assert_allclose(np.asarray(W.sum(axis=1)).ravel(), 1.0, rtol=0, atol=1e-12)
            self.assertEqual(W.shape[0], op.celdas.size)
            self.assertEqual(DZ.nnz, int((op.pix >= 0).sum()))
        self.assertEqual(dict(_operador(G_MIXTO).ganador), dict(G_MIXTO))

    def test_operador_bytes_sha256_y_lectura(self):
        """AMB-6: sha256 de sus bytes, deterministas; la lectura los reproduce; cambian con el ganador o con θ."""
        op = _operador()
        datos = op.a_bytes()
        self.assertEqual(op.sha256, _sha(datos))
        self.assertTrue(datos.startswith(ambiental.FIRMA_OPERADOR))
        with self.assertRaises(UnicodeDecodeError):
            datos.decode("utf-8")
        self.assertEqual(op.tamano_bytes, len(datos))
        otro = _operador_de(G_MIXTO)
        self.assertEqual(otro.sha256, op.sha256)
        leido = ambiental.leer_operador(datos)
        self.assertEqual(leido.sha256, op.sha256)
        self.assertEqual(leido.a_bytes(), datos)
        self.assertEqual(dict(leido.hiper), dict(op.hiper))
        self.assertEqual(leido.cabecera(), op.cabecera())
        cab = op.cabecera()
        self.assertEqual(cab["esquema"], ambiental.ESQUEMA_OPERADOR)
        self.assertEqual(cab["decision_sha256"], _sha(_decision_bytes(G_MIXTO)))
        self.assertEqual(cab["hiperparametros"]["u"], [ambiental._hiper_json(H_A), ambiental._hiper_json(H_PHI)])
        self.assertEqual(cab["hiperparametros"]["p"], ambiental._hiper_json(H_PHI))
        # Las columnas desde el operador releído son las mismas.
        a = _columnas("D", operador=op, horas=_horas_mes(2019, 1)[:30])
        b = _columnas("D", operador=leido, horas=_horas_mes(2019, 1)[:30])
        for c in a:
            np.testing.assert_array_equal(a[c], b[c])
        self.assertNotEqual(_operador(G_OTRO).sha256, op.sha256)
        self.assertNotEqual(_operador_de(G_CON_C, decision=_decision_bytes(G_CON_C, 3.0)).sha256,
                            _operador(G_CON_C).sha256)
        with self.assertRaises(ErrorAmbiental):
            ambiental.leer_operador(datos[:-1])
        alterados = datos[:-8] + (b"\x01" * 8 if datos[-8:] == b"\x00" * 8 else b"\x00" * 8)
        self.assertNotEqual(ambiental.leer_operador(alterados).sha256, op.sha256)     # coherentes consigo mismos…
        with self.assertRaises(ErrorAmbiental):                                       # … no con la esperada
            ambiental.leer_operador(alterados, sha256=op.sha256)
        self.assertEqual(ambiental.leer_operador(datos, sha256=op.sha256).sha256, op.sha256)
        with self.assertRaises(ErrorAmbiental):
            ambiental.leer_operador(b"PK\x03\x04" + datos)

    def test_operador_ganador_restringido(self):
        """Anexo B, rama 3, y AMB-7: sólo cambian los grupos con B o AB, a A o C, con la huella de m6/ramas_m6.json
        (H3: no la de decision_m6.json, que cita al operador)."""
        m6 = "5" * 64
        restringido = {"T_Td": "A", "u_v": "C", "p": "A"}
        op = _operador_de(G_MIXTO, restringido=restringido, ramas_m6_sha256=m6)
        self.assertEqual(dict(op.ganador), restringido)
        self.assertTrue(op.restringido)
        self.assertEqual(op.ramas_m6_sha256, m6)
        self.assertEqual(op.cabecera()["ramas_m6_sha256"], m6)
        self.assertNotIn("decision_m6_sha256", op.cabecera())
        self.assertFalse(hasattr(op, "decision_m6_sha256"))
        self.assertEqual(ambiental.leer_operador(op.a_bytes()).ramas_m6_sha256, m6)
        self.assertNotEqual(_operador_de(G_MIXTO, restringido=restringido, ramas_m6_sha256="6" * 64).sha256, op.sha256)
        self.assertEqual(op.hiper["T"], HIPER_DE["A"]["T"])
        self.assertEqual(op.hiper["u"], HIPER_DE["C"]["u"])
        self.assertNotEqual(op.sha256, _operador().sha256)
        # La lateral con el ganador restringido (m6/ambiental/).
        tabla, meta = _lateral("pm25", "D", operador=op)
        self.assertEqual(meta["operador_sha256"], op.sha256)
        ceguera.vigilar_salida("m6/ambiental/lateral_pm25_D.parquet", tabla, clase="insumo")
        malos = {
            "cambia un grupo con A": {"T_Td": "A", "u_v": "C", "p": "C"},
            "restringido a B": {"T_Td": "B", "u_v": "C", "p": "A"},
            "restringido a AB": {"T_Td": "C", "u_v": "AB", "p": "A"},
            "falta un grupo": {"T_Td": "A", "u_v": "C"},
            "candidato desconocido": {"T_Td": "A", "u_v": "X", "p": "A"},
        }
        for caso, r in malos.items():
            with self.subTest(caso=caso):
                with self.assertRaises(ErrorAmbiental):
                    _operador_de(G_MIXTO, restringido=r, ramas_m6_sha256=m6)
        with self.assertRaises(ErrorAmbiental):
            _operador_de(G_MIXTO, restringido=restringido)
        with self.assertRaises(ErrorAmbiental):
            _operador_de(G_MIXTO, ramas_m6_sha256=m6)
        with self.assertRaises(ErrorAmbiental):
            _operador_de(G_MIXTO, restringido=restringido, ramas_m6_sha256="no es una huella")
        with self.assertRaises(TypeError):                       # el nombre viejo ya no existe (H3)
            _operador_de(G_MIXTO, restringido=restringido, decision_m6_sha256=m6)

    def test_operador_se_niega(self):
        """AMB-7 y AMB-8: decision.json sin lo ambiental, sin hiperparámetros, con u y v distintos o mal formados; el
        diccionario sin su sha256; z_media que falta; celdas repetidas."""
        contenido, sha = ambiental.leer_decision(_decision_bytes(G_MIXTO))
        sin_p = {**contenido, "decisiones": [d for d in contenido["decisiones"] if d["grupo"] != "p"]}
        sin_hiper = __import__("copy").deepcopy(contenido)
        sin_hiper["decisiones"][0]["hiperparametros"].pop(sin_hiper["decisiones"][0]["ganador"])
        uv = __import__("copy").deepcopy(contenido)
        d_uv = next(d for d in uv["decisiones"] if d["grupo"] == "u_v")
        d_uv["hiperparametros"]["AB"]["v"] = [ambiental._hiper_json(H_A), ambiental._hiper_json(H_B)]
        mal_theta = __import__("copy").deepcopy(contenido)
        d_t = next(d for d in mal_theta["decisiones"] if d["grupo"] == "T_Td")
        d_t["hiperparametros"]["B"]["T"] = {"L_km": 50.0, "lam": 0.0}
        kappa_cero = __import__("copy").deepcopy(contenido)
        next(d for d in kappa_cero["decisiones"] if d["grupo"] == "T_Td")["hiperparametros"]["B"]["T"]["kappa"] = 0.0
        otro_esquema = {**contenido, "esquema": "otra/1"}
        for caso, dec in {"sin p": sin_p, "sin hiperparámetros": sin_hiper, "u y v distintos": uv,
                          "θ incompleto": mal_theta, "κ = 0": kappa_cero, "otro esquema": otro_esquema}.items():
            with self.subTest(caso=caso):
                with self.assertRaises(ErrorAmbiental):
                    _operador_de(decision=dec, decision_sha256=sha)
        with self.assertRaises(ErrorAmbiental):
            _operador_de(decision=contenido)
        with self.assertRaises(ErrorAmbiental):
            _operador_de(decision=_decision_bytes(G_MIXTO), decision_sha256="6" * 64)
        cl, px = _celdas(), _pixeles()
        with self.assertRaises(ErrorAmbiental):
            ambiental.operador_grilla(_decision_bytes(G_MIXTO), celdas=cl.tabla, estaciones=_red(), catalogo=px.cat,
                                      z_celdas=cl.estaticos.iloc[1:], validos=px.pid, z_pix=px.z_tabla,
                                      umbrales=_umbrales())
        with self.assertRaises(ErrorAmbiental):
            ambiental.operador_grilla(_decision_bytes(G_MIXTO), celdas=pd.concat([cl.tabla, cl.tabla.iloc[:1]]),
                                      estaciones=_red(), catalogo=px.cat, z_celdas=cl.estaticos, validos=px.pid,
                                      z_pix=px.z_tabla, umbrales=_umbrales())
        with self.assertRaises(ErrorAmbiental):
            ambiental.operador_grilla(_decision_bytes(G_MIXTO), celdas=cl.tabla, estaciones=_red(), catalogo=px.cat,
                                      z_celdas=cl.estaticos.rename(columns={"z_media": "z"}), validos=px.pid,
                                      z_pix=px.z_tabla, umbrales=_umbrales())
        todas_fuera = {c: dataclasses.replace(i, excluida=True) for c, i in _red().items()}
        with self.assertRaises(ErrorAmbiental):
            ambiental.operador_grilla(_decision_bytes(G_MIXTO), celdas=cl.tabla, estaciones=todas_fuera,
                                      catalogo=px.cat, z_celdas=cl.estaticos, validos=px.pid, z_pix=px.z_tabla,
                                      umbrales=_umbrales())

    def test_tamano_del_operador(self):
        """MC-15: el tamaño de los bytes del operador es el de su cabecera y sus arreglos, y crece por celda con 81 B
        del fondo, 32 B de la celda y 8 B más 12 B por vecino de cada núcleo."""
        op = _operador()
        n = op.celdas.size
        cab = len(ambiental._json_canonico(op.cabecera()))
        nucleos = sum(8 * (n + 1) + 12 * nuc.indices.size for nuc in op.nucleos.values())
        esperado = len(ambiental.FIRMA_OPERADOR) + 8 + cab + n * (4 * 8 + 4 * 4 + 4 * 8 + 4 * 8 + 1) \
            + 4 * len(op.codigos) + nucleos
        self.assertEqual(op.tamano_bytes, esperado)
        self.assertEqual(len(op.a_bytes()), esperado)
        self.assertEqual(ambiental._json_canonico(op.cabecera()), entorno.json_canonico(op.cabecera()))
        # AMB-15 (P-AMB-3): la cota con la lista llena y los 8 juegos de AB en las 838.430 celdas de §3.
        por_celda = 4 * 8 + 4 * (4 + 8 + 8) + 1 + 8 * (8 + 12 * _umbrales().a("NUC_VECINOS"))
        self.assertEqual(por_celda, 3057)
        self.assertAlmostEqual(por_celda * 838_430 / 1e9, 2.56, places=2)

    def test_operador_inmutable_con_sus_umbrales(self):
        """AMB-6 (H9): los arreglos del operador (también los de los núcleos y los del releído) son de sólo lectura; la
        cabecera trae los umbrales del operador y su huella, y evaluar con otros umbrales es un error."""
        U = _umbrales()
        op = _operador()
        leido = ambiental.leer_operador(op.a_bytes())
        for o in (op, leido):
            for nombre in ("celdas", "lat", "lon", "z", "pix", "w", "dz", "respaldo", "grupo_est"):
                self.assertFalse(getattr(o, nombre).flags.writeable, nombre)
                with self.assertRaises(ValueError):
                    getattr(o, nombre)[(0,) * getattr(o, nombre).ndim] = 0
            for nuc in o.nucleos.values():
                for nombre in ("indptr", "indices", "d_ef"):
                    self.assertFalse(getattr(nuc, nombre).flags.writeable, nombre)
        self.assertTrue(leido.celdas.flags.owndata)                     # una sola copia (H6), dueña de sus datos
        cab = op.cabecera()
        self.assertEqual(list(cab["umbrales"]), list(ambiental.UMBRALES_OPERADOR))
        for ident in ambiental.UMBRALES_OPERADOR:
            valor = U.a(ident)
            self.assertEqual(cab["umbrales"][ident], list(valor) if isinstance(valor, tuple) else valor, ident)
        self.assertEqual(cab["umbrales_sha256"], _sha(entorno.json_canonico(cab["umbrales"])))
        self.assertEqual(op.umbrales_sha256, cab["umbrales_sha256"])
        self.assertEqual(leido.umbrales_sha256, op.umbrales_sha256)
        with self.assertRaises(TypeError):
            op.umbrales["NUC_CORTE"] = 0
        for ident, cambio in (("GAMMA_K_KM", U.a("GAMMA_K_KM") - 1), ("NUC_VECINOS", U.a("NUC_VECINOS") - 1),
                              ("VECINO_KM", U.a("VECINO_KM") + 1), ("NUC_L", tuple(U.a("NUC_L"))[:-1])):
            with self.subTest(umbral=ident):
                otros = _UmbralesCambiados(U, {ident: cambio})
                with self.assertRaisesRegex(ErrorAmbiental, "umbrales no son los del operador"):
                    _columnas("D", celdas=_celdas().rejilla[:2], horas=_horas_mes(2019, 1)[:3], umbrales=otros)
                with self.assertRaisesRegex(ErrorAmbiental, "umbrales no son los del operador"):
                    ambiental.fabrica_tf_contaminantes(_predecir(), operador=op, meses=_mes_memoria, datos=_datos_tf(),
                                                       umbrales=otros, escenarios=_escenarios())
        with self.assertRaises(ErrorAmbiental):
            dataclasses.replace(op, umbrales={**op.umbrales, "NUC_CORTE": 0, "otro": 1})
        with self.assertRaises(ErrorAmbiental):
            dataclasses.replace(op, w=op.w.astype(np.float32))

    def test_leer_operador_se_niega_sin_keyerror(self):
        """AMB-6 (H9): una cabecera sin una clave, con una de más, sin un arreglo, con otro tipo, fuera de lugar o mal
        formada da ErrorAmbiental, nunca KeyError."""
        datos = _operador().a_bytes()
        firma = len(ambiental.FIRMA_OPERADOR)
        largo = struct.unpack_from("<Q", datos, firma)[0]
        cab = json.loads(datos[firma + 8:firma + 8 + largo].decode("utf-8"))
        arreglos = datos[firma + 8 + largo:]

        def con(cambio):
            c = copy.deepcopy(cab)
            cambio(c)
            nueva = entorno.json_canonico(c)
            return ambiental.FIRMA_OPERADOR + struct.pack("<Q", len(nueva)) + nueva + arreglos
        self.assertEqual(con(lambda c: None), datos)                    # rehacer la cabecera da los mismos bytes

        def renombrar(c):
            c["arreglos"][-1]["nombre"] = c["arreglos"][-1]["nombre"] + "_otro"

        def otro_tipo(c):
            c["arreglos"][1]["tipo"] = "<f4"

        def corrido(c):
            c["arreglos"][2]["inicio"] += 8

        def sin_arreglo(c):
            c["arreglos"].pop(3)
        nucleo_extra = {"L1.0_lam0.0_kappa1.0": ambiental._hiper_json(Hiper(1.0, 0.0, 1.0))}
        casos = {                                       # caso: (cambio, el motivo del mensaje)
            "sin umbrales": (lambda c: c.pop("umbrales"), "AMB-6"),
            "sin ramas_m6_sha256": (lambda c: c.pop("ramas_m6_sha256"), "AMB-6"),
            "con una clave de más": (lambda c: c.update(otra=1), "AMB-6"),
            "un arreglo renombrado": (renombrar, "no son los de su cabecera"),
            "un arreglo de menos": (sin_arreglo, "no son los de su cabecera"),
            "un núcleo sin sus arreglos": (lambda c: c["nucleos"].update(nucleo_extra), "no son los de su cabecera"),
            "otro tipo": (otro_tipo, "su tipo"),
            "fuera de lugar": (corrido, "fuera de lugar"),
            "ganador sin un grupo": (lambda c: c["ganador"].pop("p"), "mal formada"),
            "hiperparámetros sin una variable": (lambda c: c["hiperparametros"].pop("T"), "mal formada"),
            "umbrales sin uno": (lambda c: c["umbrales"].pop("NUC_CORTE"), "los umbrales son"),
            "umbrales con otra huella": (lambda c: c.update(umbrales_sha256="7" * 64), "sus umbrales"),
            "nucleos como lista": (lambda c: c.update(nucleos=[]), "es un objeto"),
            "arreglos como objeto": (lambda c: c.update(arreglos={}), "una lista"),
            "decision_sha256 que no es huella": (lambda c: c.update(decision_sha256="x"), "decision_sha256"),
            "ramas_m6_sha256 sin rama 3": (lambda c: c.update(ramas_m6_sha256="5" * 64), "sólo va con"),
        }
        for caso, (cambio, motivo) in casos.items():
            with self.subTest(caso=caso):
                with self.assertRaisesRegex(ErrorAmbiental, motivo):   # un KeyError haría fallar la prueba con error
                    ambiental.leer_operador(con(cambio))
        with self.assertRaises(ErrorAmbiental):
            ambiental.leer_operador(ambiental.FIRMA_OPERADOR + struct.pack("<Q", 10 ** 6) + b"{}")
        with self.assertRaises(ErrorAmbiental):
            ambiental.leer_operador("no son bytes")


# ---------------------------------------------------------------------------
# mc_bloque (AMB-9, AMB-14)
# ---------------------------------------------------------------------------
class PruebasMcBloque(unittest.TestCase):
    def test_mc_bloque_tabla_larga(self):
        """La tabla larga: celda, ts_utc (UTC) y las columnas de la variante en float32; las horas de cada celda
        seguidas, en el orden pedido."""
        cl = _celdas()
        celdas = cl.rejilla[[3, 0, 7]]
        h = _horas_mes(2019, 1)[10:58]
        for variante in ("I", "D"):
            tabla = ambiental.mc_bloque(celdas, h, variante, operador=_operador(), meses=_meses, datos=_datos(),
                                        umbrales=_umbrales(), estaticos=cl.estaticos)
            self.assertEqual(list(tabla.columns), ["celda", "ts_utc", *ambiental.COLUMNAS_VARIANTE[variante]])
            self.assertEqual(len(tabla), celdas.size * h.size)
            np.testing.assert_array_equal(tabla["celda"].to_numpy(), np.repeat(celdas, h.size))
            self.assertEqual(str(tabla["ts_utc"].dtype), "datetime64[ns, UTC]")
            ts = (np.datetime64("2000-01-01T00:00:00", "ns") + h.astype("timedelta64[h]")).astype("datetime64[ns]")
            np.testing.assert_array_equal(tabla["ts_utc"].dt.tz_localize(None).to_numpy(), np.tile(ts, celdas.size))
            col = _columnas(variante, celdas=celdas, horas=h)
            for c in ambiental.COLUMNAS_VARIANTE[variante]:
                self.assertEqual(tabla[c].dtype, np.float32)
                np.testing.assert_array_equal(tabla[c].to_numpy(), col[c].T.ravel())
        vacia = ambiental.mc_bloque(celdas[:0], h, "I", operador=_operador(), meses=_meses, datos=_datos(),
                                    umbrales=_umbrales(), estaticos=cl.estaticos)
        self.assertEqual(len(vacia), 0)

    def test_mc_bloque_lotes_de_celdas_y_horas(self):
        """AMB-14 (S9, MC-37): partir las celdas o las horas no cambia ningún bit, con A, B, AB y C."""
        cl = _celdas()
        todas = cl.tabla["celda"].to_numpy()
        h = _horas_mes(2019, 1)
        for ganador in (G_MIXTO, G_CON_C, G_OTRO):
            for variante in ("I", "D"):
                with self.subTest(ganador=ganador, variante=variante):
                    entero = _columnas(variante, ganador, celdas=todas, horas=h)
                    a = _columnas(variante, ganador, celdas=todas[:13], horas=h)
                    b = _columnas(variante, ganador, celdas=todas[13:], horas=h)
                    desordenadas = np.array(todas[::-1])
                    r = _columnas(variante, ganador, celdas=desordenadas, horas=h)
                    sel = np.r_[np.arange(30, 54), np.arange(300, 330)]
                    parte = _columnas(variante, ganador, celdas=todas, horas=h[sel])
                    for c in entero:
                        np.testing.assert_array_equal(np.hstack([a[c], b[c]]), entero[c], err_msg=c)
                        np.testing.assert_array_equal(r[c][:, ::-1], entero[c], err_msg=c)
                        np.testing.assert_array_equal(parte[c], entero[c][sel], err_msg=c)

    def test_mc_bloque_dos_meses_y_mes_leido(self):
        """AMB-9: las horas se parten por mes UTC; el mes en memoria es el que lee fondo_era5l.leer_mes."""
        leido, memoria = _mes_201901(), _mes_memoria(201901)
        np.testing.assert_array_equal(leido.tiempos, memoria.tiempos)
        for v in fondo_era5l.VARIABLES_E5L:
            np.testing.assert_array_equal(leido.datos[v], memoria.datos[v])
        cl = _celdas()
        h1, h2 = _horas_mes(2019, 1), _horas_mes(2019, 2)
        h = np.r_[h1[-30:], h2[:40]]
        junto = _columnas("D", celdas=cl.rejilla, horas=h)
        a = _columnas("D", celdas=cl.rejilla, horas=h1[-30:])
        b = _columnas("D", celdas=cl.rejilla, horas=h2[:40])
        for c in junto:
            np.testing.assert_array_equal(junto[c], np.vstack([a[c], b[c]]), err_msg=c)
        meses = {201901: leido, "201902": _mes_memoria(201902)}
        por_mapa = _columnas("D", celdas=cl.rejilla, horas=h, meses=meses)
        for c in junto:
            np.testing.assert_array_equal(por_mapa[c], junto[c])

    def test_mc_bloque_se_niega(self):
        """AMB-5, AMB-9 y AMB-14: una hora que el mes no trae, una celda fuera del operador, horas desordenadas, otras
        estaciones, C sin estáticos, un mes equivocado o una red mal dada."""
        cl = _celdas()
        h = _horas_mes(2019, 1)
        datos = _datos()
        corto = _mes_memoria(201901)
        corto = fondo_era5l.MesE5L(tiempos=corto.tiempos[:-5], pixel_id=corto.pixel_id,
                                   datos={k: v[:-5] for k, v in corto.datos.items()}, sha256=corto.sha256)
        sin_c = {c: f for c, f in datos.filas_c.items()}
        sin_c["C"] = {v: x for v, x in datos.filas_c["C"].items() if v != "p"}
        casos = {
            "hora que el mes no trae": dict(meses={201901: corto}),
            "mes equivocado": dict(meses={201901: _mes_memoria(201902)}),
            "celda fuera del operador": dict(celdas=np.array([1, 2], dtype=np.int64)),
            "celdas repetidas": dict(celdas=cl.rejilla[[0, 0]]),
            "horas desordenadas": dict(horas=h[::-1]),
            "horas que no son enteros": dict(horas=h.astype(float)),
            "otras estaciones": dict(datos=dataclasses.replace(datos, estaciones={
                c: i for c, i in datos.estaciones.items() if c != "330004"})),
            "C sin estáticos": dict(ganador=G_CON_C, estaticos=None),
            "C sin filas de p": dict(ganador=G_CON_C, datos=dataclasses.replace(datos, filas_c=sin_c)),
            "red incompleta": dict(redes={"T": lambda a: None}),
            "otros umbrales": dict(umbrales=_UmbralesCambiados(_umbrales(), {"GAMMA_K_KM": 0.0})),
            "variante desconocida": dict(variante="X"),
        }
        for caso, kw in casos.items():
            with self.subTest(caso=caso):
                kw = dict(kw)
                variante = kw.pop("variante", "I")
                ganador = kw.pop("ganador", G_MIXTO)
                with self.assertRaises((ErrorAmbiental, fondo_era5l.ErrorFondo)):
                    _columnas(variante, ganador, celdas=kw.pop("celdas", cl.rejilla), horas=kw.pop("horas", h), **kw)


# ---------------------------------------------------------------------------
# La fábrica de la TF de contaminantes (A26; AMB-10, AMB-11; S16)
# ---------------------------------------------------------------------------
MODELO_FALSO = {"b0": 20.0, "b_t": 0.5, "b_rh": 0.05, "b_w": -1.0, "b_p": 0.001}
_NS_DIA = 86_400 * 10 ** 9


def _predecir(registro=None):
    """Fábrica de producción falsa: una función conocida de las columnas, promediada por día UTC (AMB-11)."""
    def predecir(modelo, variante, tabla, celdas, dias):
        if registro is not None:
            registro.append(tabla)
        n_c, n_d = len(celdas), len(dias)
        np.testing.assert_array_equal(tabla["celda"].to_numpy(), np.repeat(celdas, n_d * 24))
        dia = (pd.DatetimeIndex(tabla["ts_utc"]).asi8 - pd.Timestamp("2000-01-01", tz="UTC").value) // _NS_DIA
        np.testing.assert_array_equal(dia, np.tile(np.repeat(dias, 24), n_c))
        if variante == "I":
            t, rh, w, p = (tabla[c].to_numpy(np.float64) for c in ("mc_t2m", "mc_rh", "mc_wind", "mc_sp"))
        else:
            t = tabla["fe_t2m"].to_numpy(np.float64) + tabla["dmc_R_T"].to_numpy(np.float64)
            rh = tabla["fe_rh"].to_numpy(np.float64) + 10 * tabla["dmc_R_Td"].to_numpy(np.float64)
            w = tabla["fe_wind"].to_numpy(np.float64) + tabla["dmc_R_u"].to_numpy(np.float64)
            p = tabla["fe_sp"].to_numpy(np.float64) * np.exp(tabla["dmc_R_p"].to_numpy(np.float64))
        x = modelo["b0"] + modelo["b_t"] * (t - 273.15) + modelo["b_rh"] * rh + modelo["b_w"] * w \
            + modelo["b_p"] * (p / 100.0 - 900.0)
        return x.reshape(n_c, n_d, 24).mean(axis=2).T
    return predecir


def _escenarios(historicas: dict | None = None) -> dict:
    codigos = tuple(sorted(c for c, i in _red().items() if not i.excluida))
    historicas = historicas or {}
    return {v: tendencias.EscenariosTF(variable=v, historica=frozenset(historicas.get(v, codigos[:4])),
                                       constante=frozenset(codigos), regla="r2000_2025")
            for v in ambiental.VARIABLES_RED}


def _historicas_distintas() -> dict:
    """Una red histórica distinta para cada variable de la TF (H4)."""
    codigos = tuple(sorted(c for c, i in _red().items() if not i.excluida))
    return {"T": codigos[:3], "Td": codigos[2:6], "rapidez": codigos[4:9], "p": codigos[::2]}


def _operador_tf(ganador):
    """El operador con el entrenamiento de _datos_tf (las mismas estaciones, otro período)."""
    return _operador(ganador)


def _fabrica(ganador, registro=None, escenarios=None):
    return ambiental.fabrica_tf_contaminantes(_predecir(registro), operador=_operador_tf(ganador), meses=_mes_memoria,
                                              datos=_datos_tf(), umbrales=_umbrales(),
                                              escenarios=escenarios or _escenarios(), estaticos=_celdas().estaticos)


def _muestra():
    cl = _celdas()
    en = np.isin(cl.tabla["celda"].to_numpy(), cl.rejilla)
    tabla = pd.DataFrame({"celda": cl.tabla["celda"].to_numpy()[en], "cod_comuna": cl.comunas[en]})
    w = 100.0 + np.arange(len(tabla), dtype=float)
    return tendencias.muestra_tf_contaminantes(tabla, w, _umbrales())


def _dias_mes(anio: int, mes: int) -> np.ndarray:
    inicio = int((np.datetime64(f"{anio:04d}-{mes:02d}-01") - np.datetime64("2000-01-01")).astype(np.int64))
    fin = int((np.datetime64(f"{anio:04d}-{mes:02d}-01") + np.timedelta64(32, "D")).astype("datetime64[M]")
              .astype("datetime64[D]").astype(np.int64) - np.datetime64("2000-01-01").astype(np.int64))
    d = np.arange(inicio, fin, dtype=np.int64)
    return d[d % 11 == 3]


class PruebasFabrica(unittest.TestCase):
    def test_fabrica_nombres_y_completo_es_mc_bloque(self):
        """A26: fabrica(modelo, variante, escenario, celdas, dias) → día × celda; «completo» es la cuenta de producción
        (mc_bloque sin redes), bit a bit; los escenarios son los de tendencias."""
        self.assertEqual(ambiental.ESCENARIOS_TF, tendencias.ESCENARIOS)
        self.assertEqual(set(ambiental.VARIABLES_RED), set(tendencias.VARIABLES_TF))
        registro = []
        fabrica = _fabrica(G_B, registro)
        celdas = _muestra()["celda"].astype(np.int64)
        dias = _dias_mes(2015, 2)
        for variante in ("I", "D"):
            P = fabrica(MODELO_FALSO, variante, "completo", celdas, dias)
            self.assertEqual(P.shape, (dias.size, celdas.size))
            self.assertTrue(np.isfinite(P).all())
            tabla = ambiental.mc_bloque(celdas, ambiental.horas_dia_utc(dias), variante, operador=_operador_tf(G_B),
                                        meses=_mes_memoria, datos=_datos_tf(), umbrales=_umbrales(),
                                        estaticos=_celdas().estaticos)
            pd.testing.assert_frame_equal(registro[-1], tabla)
        np.testing.assert_array_equal(ambiental.horas_dia_utc(np.array([1, 3])),
                                      np.r_[np.arange(24, 48), np.arange(72, 96)])
        with self.assertRaises(ErrorAmbiental):
            fabrica(MODELO_FALSO, "I", "otro", celdas, dias)
        with self.assertRaises(ErrorAmbiental):
            fabrica(MODELO_FALSO, "I", "completo", celdas, dias[::-1])
        with self.assertRaises(ErrorAmbiental):
            ambiental.fabrica_tf_contaminantes(_predecir(), operador=_operador_tf(G_B), meses=_mes_memoria,
                                               datos=_datos_tf(), umbrales=_umbrales(),
                                               escenarios={k: v for k, v in _escenarios().items() if k != "p"})
        mala = ambiental.fabrica_tf_contaminantes(lambda *a: np.zeros((1, 1)), operador=_operador_tf(G_B),
                                                  meses=_mes_memoria, datos=_datos_tf(), umbrales=_umbrales(),
                                                  escenarios=_escenarios(), estaticos=_celdas().estaticos)
        with self.assertRaises(ErrorAmbiental):
            mala(MODELO_FALSO, "I", "completo", celdas, dias)

    def test_fabrica_red_por_variable(self):
        """AMB-10 (H4): con B y con AB, cada R usa la red de su variable (T, Td, rapidez y p) en 2015-2019 de «cambio»,
        también la R_T del mín de mc_d2m (la de Td); en 2020-2024 «cambio» es «completo»."""
        U, cl = _umbrales(), _celdas()
        codigos = tuple(sorted(c for c, i in _red().items() if not i.excluida))
        historicas = {"T": codigos[:3], "Td": codigos[2:6], "rapidez": codigos[4:9], "p": codigos[::2]}
        esc = _escenarios(historicas)
        celdas = cl.rejilla
        h = ambiental.horas_dia_utc(_dias_mes(2015, 1))
        redes = {v: (lambda anio, e=esc[v]: e.red("cambio", anio)) for v in ambiental.VARIABLES_RED}
        entrenamiento = {c: _red()[c] for c in codigos}
        clima = _datos_tf().climatologias
        for ganador, cand in ((G_B, "B"), (G_AB, "AB")):
            with self.subTest(candidato=cand):
                op = _operador_tf(ganador)
                kw = dict(operador=op, meses=_mes_memoria, datos=_datos_tf(), umbrales=U, estaticos=cl.estaticos,
                          float64=True)
                d_cambio = ambiental.columnas_bloque(celdas, h, "D", redes=redes, **kw)
                i_cambio = ambiental.columnas_bloque(celdas, h, "I", redes=redes, **kw)
                d_completo = ambiental.columnas_bloque(celdas, h, "D", **kw)
                idx = op.indices(celdas)
                puntos = {"ids": celdas, "lat": op.lat[idx], "lon": op.lon[idx], "z": op.z[idx]}

                def r_red(v, red, cand=cand):
                    q = candidatos.matriz_q(_datos_tf(), codigos, cand, v, h, U)
                    disponible = np.isfinite(q) & np.array([c in red for c in codigos])[None, :]
                    if cand == "B":
                        return candidatos.correccion_b(candidatos.vecinos(puntos, entrenamiento, HIPER_DE["B"][v], U),
                                                       q, disponible)
                    t_a, t_phi = HIPER_DE["AB"][v]
                    return candidatos.correccion_ab(candidatos.vecinos(puntos, entrenamiento, t_a, U),
                                                    candidatos.vecinos(puntos, entrenamiento, t_phi, U),
                                                    clima[clima["variable"] == v], q, disponible, h)
                for col, v, red in (("dmc_R_T", "T", historicas["T"]), ("dmc_R_Td", "Td", historicas["Td"]),
                                    ("dmc_R_u", "u", historicas["rapidez"]), ("dmc_R_v", "v", historicas["rapidez"]),
                                    ("dmc_R_p", "p", historicas["p"])):
                    np.testing.assert_array_equal(d_cambio[col], r_red(v, red), err_msg=col)
                    self.assertFalse(np.array_equal(d_cambio[col], d_completo[col]), col)
                    self.assertFalse(np.array_equal(d_cambio[col], r_red(v, codigos[:4])), col)   # no otra red
                F = {"T_F": d_cambio["fe_t2m"] - K, "Td_F": d_cambio["fe_d2m"] - K}
                np.testing.assert_allclose(i_cambio["mc_t2m"], F["T_F"] + r_red("T", historicas["T"]) + K, rtol=0,
                                           atol=1e-10)
                t_de_td = F["T_F"] + r_red("T", historicas["Td"])
                np.testing.assert_allclose(i_cambio["mc_d2m"],
                                           np.minimum(F["Td_F"] + r_red("Td", historicas["Td"]), t_de_td) + K, rtol=0,
                                           atol=1e-10)
                hr = np.clip(numerico.hr_desde(t_de_td, i_cambio["mc_d2m"] - K), 0, 100)
                np.testing.assert_allclose(i_cambio["mc_rh"], hr, rtol=0, atol=1e-9)
                h20 = ambiental.horas_dia_utc(_dias_mes(2020, 1))
                a = ambiental.columnas_bloque(celdas, h20, "I", redes=redes, **kw)
                b = ambiental.columnas_bloque(celdas, h20, "I", **kw)
                for c in a:
                    np.testing.assert_array_equal(a[c], b[c])

    def test_s16_tf_contaminantes_cero_con_a_y_c(self):
        """Anexo B y S16: con ganadores A y C la fábrica da lo mismo en «cambio» y «completo» (bit a bit): la
        verificación de un mes pasa en I y la TF de D da 0."""
        fabrica = _fabrica(G_A_C, escenarios=_escenarios(_historicas_distintas()))
        celdas = _muestra()["celda"].astype(np.int64)
        for dias in (_dias_mes(2015, 1), _dias_mes(2017, 6)):
            for variante in ("I", "D"):
                np.testing.assert_array_equal(fabrica(MODELO_FALSO, variante, "cambio", celdas, dias),
                                              fabrica(MODELO_FALSO, variante, "completo", celdas, dias))
        v = tendencias.tf_contaminantes(fabrica, MODELO_FALSO, "I", _muestra(), _umbrales(), verificacion_un_mes=True)
        self.assertEqual((v["resultado"], v["dif_max"], v["mes"]), ("pasa", 0.0, "2015-01"))
        r = tendencias.tf_contaminantes(fabrica, MODELO_FALSO, "D", _muestra(), _umbrales())
        self.assertEqual((r["resultado"], r["media_pond"], r["p95_pond"]), ("pasa", 0.0, 0.0))
        self.assertGreater(r["media_nacional"], 0)

    def test_s16_tf_contaminantes_con_b_y_la_red_historica(self):
        """Anexo B y S16 (H4): con B o con AB y una red histórica distinta por variable que deja fuera estaciones,
        «cambio» difiere de «completo» sólo en 2015-2019 (y de la fábrica con una sola red para todas): la TF de D es
        ≠ 0 y la verificación de un mes de I se niega (TEN-21)."""
        celdas = _muestra()["celda"].astype(np.int64)
        d15, d20 = _dias_mes(2015, 2), _dias_mes(2020, 2)
        for ganador in (G_B, G_AB):
            with self.subTest(ganador=ganador):
                fabrica = _fabrica(ganador, escenarios=_escenarios(_historicas_distintas()))
                una_red = _fabrica(ganador)                       # la misma red histórica para las cuatro variables
                cambio = fabrica(MODELO_FALSO, "D", "cambio", celdas, d15)
                self.assertFalse(np.array_equal(cambio, fabrica(MODELO_FALSO, "D", "completo", celdas, d15)))
                self.assertFalse(np.array_equal(cambio, una_red(MODELO_FALSO, "D", "cambio", celdas, d15)))
                np.testing.assert_array_equal(fabrica(MODELO_FALSO, "D", "cambio", celdas, d20),
                                              fabrica(MODELO_FALSO, "D", "completo", celdas, d20))
                r = tendencias.tf_contaminantes(fabrica, MODELO_FALSO, "D", _muestra(), _umbrales())
                self.assertGreater(r["media_pond"], 0)
                self.assertGreater(r["p95_pond"], 0)
                with self.assertRaises(tendencias.ErrorTendencias):
                    tendencias.tf_contaminantes(fabrica, MODELO_FALSO, "I", _muestra(), _umbrales(),
                                                verificacion_un_mes=True)

if __name__ == "__main__":
    unittest.main()
