"""Pruebas de candidatos.py (§4.2-§4.9).

Dueño: I13 (ola 3). Las que llevan «sNN» son la prueba NN de §9 del texto: S5 (la parte de los candidatos) y la parte de
los candidatos de S12. Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
Datos sólo sintéticos y en memoria: la verdad de S5 es la de ``sintetico.verdad`` (fondo + sesgo b(x, m, h) + anomalías
de MC-50, D42) y el resto son redes, estáticos y fondos hechos aquí. Nada se escribe en el disco, y ninguna prueba abre
DMC, la meteorología SINCA real, NASADEM real, ERA5L real ni GHS-POP real. Los umbrales son los anclados en M0
(``umbrales.cargar_m0``); sólo se leen el texto y el JSON de umbrales de APH.

Interfaces simuladas mientras los módulos hermanos de la ola 3 no estén (§6 del diseño):
- ``objetivo`` de ``candidatos.seleccionar`` (PED-3): lo arma ``orquestacion`` con ``validacion`` (los pesos del uso de
  §5.3 en el pliegue interno). Aquí ``_objetivo`` es la raíz de la media de los MSE por estación, igual en todos los
  usos: basta para probar la selección, no los pesos.
- La tabla de residuos sale de ``candidatos.residuos_estacion`` sobre residuos sintéticos (lo que haría
  ``orquestacion`` con ``fondo_era5l.residuos``), y los estáticos de C llevan la columna ``z_e5l`` (PED-2).
Semilla: ``SEMILLA`` del Anexo A (20261023), que no se eligió probando semillas.
"""
import sys

sys.dont_write_bytecode = True

import dataclasses  # noqa: E402
import hashlib  # noqa: E402
import math  # noqa: E402
import unittest  # noqa: E402
from datetime import datetime  # noqa: E402
from functools import lru_cache  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import (candidatos, constantes, estaticas_nasadem, homogeneidad, numerico,  # noqa: E402
                             particiones, sintetico, tipos, umbrales)
from meteo_combinada.tipos import Candidato, Hiper, Uso  # noqa: E402
# CAN-18: los nombres que usa la copia literal de la ola 3 de ``_bases`` y ``_diseno_bruto`` (tras los ayudantes).
from meteo_combinada.candidatos import (_ANUALES, _HORARIOS, BASES_C, COLUMNA_Z_C, COLUMNA_Z_E5L,  # noqa: E402
                                        ESTADO_C, HORAS_DIA, M_POR_KM, MACRO_C, MONOMIOS_C, TPI_C, TRUNCADO_C,
                                        ErrorCandidatos, _dia_del_anio)

_AP = _RAIZ.parent
_APH = _AP.parent / "Air-Pollution-Health-Chile"
_EPOCA = np.datetime64("2000-01-01T00", "h")
NAN = float("nan")

# Valores del Anexo A que suponen las redes hechas a mano; ``test_valores_que_suponen_las_pruebas`` los compara.
VALORES_ANEXO_A = {"NUC_L": (10, 25, 50, 100, 200), "NUC_LAMBDA": (0, 50, 150), "NUC_KAPPA": (0.05, 0.2, 0.5, 1.0),
                   "NUC_CORTE": 3, "NUC_VECINOS": 30, "A_MIN_N": 60, "A_MIN_ANIOS": 2, "A_HUECO_H": 4,
                   "A_HORAS_K3": 12, "A_RECORTE_PCT": 10, "B_INTERP_H": 3, "C_FILAS": 4000, "C_PESO_MAX": 10,
                   "C_ALFAS": (0.1, 1, 10, 100, 1000), "GRUPO_KM": 2, "P2_AMORT_KM": 25, "SEMILLA": 20261023,
                   "SEL_MOD": 11, "SEL_RESTO": 3, "SEL_MOD_RECORTE": 23}
_U = None


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


def _horas(desde: str, hasta: str) -> np.ndarray:
    return np.arange(_h(desde), _h(hasta), dtype=np.int64)


def _objetivo(internos, sumas, *, candidato, variable, uso):
    """Simulación del objetivo de §4.9 (PED-3): √(media de los MSE por estación de prueba interna)."""
    mse = [sse / n for por in sumas.values() for sse, n in por.values() if n > 0]
    return math.sqrt(float(np.mean(mse))) if mse else NAN


# ---------------------------------------------------------------------------
# Redes sintéticas
# ---------------------------------------------------------------------------
def _info(codigo: str, lat: float, lon: float, z: float, celda) -> tipos.InfoEstacion:
    e, n = (float(x[0]) for x in numerico.utm19s(np.array([lat, lat]), np.array([lon, lon])))   # pyproj: >1 punto
    return tipos.InfoEstacion(
        codigo=codigo, nombre=f"E{codigo}", conjunto="V", macrozona="centro", grupo=tipos.id_grupo([codigo]),
        omm=None, tipo=None, propietario=None, lat_txt=f"{lat:.4f}", lon_txt=f"{lon:.4f}", alt_txt=f"{z:.0f}",
        lat=float(lat), lon=float(lon), z_cat=float(z), rho_km=0.1, k3_pasa=True, z_s=float(z),
        z_s_fuente="catalogo", celda=celda, utm_e=float(e), utm_n=float(n), bloque="", pix0=0, pix1=-1, pix2=-1,
        pix3=-1, w0=1.0, w1=0.0, w2=0.0, w3=0.0, respaldo_16km=False, sin_fondo=False, excluida=False, motivo=None)


def _completar(infos: dict) -> dict:
    """Grupo y bloque de cada estación con ``particiones`` (A8, PAR-12)."""
    U = _umbrales()
    grupos = particiones.grupos_mismo_sitio(infos, U)
    codigos = sorted(infos)
    bloques = particiones.bloque(np.array([infos[c].lat for c in codigos]), np.array([infos[c].lon for c in codigos]), U)
    return {c: dataclasses.replace(infos[c], grupo=grupos.get(c, infos[c].grupo), bloque=str(b))
            for c, b in zip(codigos, bloques)}


def _red(n_lado: int, paso: float, *, par: bool = True, lat0: float = -33.0, lon0: float = -71.2,
         fuera_de_grilla: tuple[str, ...] = ()) -> dict:
    """Rejilla de n_lado × n_lado estaciones (con un desplazamiento fijo) y, con ``par``, una más a ≈ 0,8 km de la
    primera (un grupo a ≤ 2 km). Celda = 1.000 + índice, salvo las de ``fuera_de_grilla`` (D34)."""
    infos, k = {}, 0
    for i in range(n_lado):
        for j in range(n_lado):
            lat = lat0 - i * paso - 0.013 * ((i * 7 + j * 3) % 5)
            lon = lon0 + j * paso + 0.011 * ((i * 3 + j * 5) % 4)
            codigo = f"{330000 + k:06d}"
            infos[codigo] = _info(codigo, lat, lon, 200.0 + 600.0 * (lon - lon0) + 80.0 * i, 1000 + k)
            k += 1
    if par:
        primero = infos["330000"]
        codigo = f"{330000 + k:06d}"
        infos[codigo] = _info(codigo, primero.lat - 0.005, primero.lon + 0.006, primero.z_s + 15.0, 1000 + k)
    for c in fuera_de_grilla:
        infos[c] = dataclasses.replace(infos[c], celda=None)
    return _completar(infos)


def _sesgo(lat, lon, m, hora):
    """b(x, m, h) de S5: suave en el espacio, con ciclo anual y diario (cambio horario ≤ 0,11 K)."""
    return (1.0 + 0.8 * (np.asarray(lat) + 33.5) + 0.4 * np.cos(2 * np.pi * (m - 1) / 12)
            + 0.4 * np.cos(2 * np.pi * (hora - 15) / 24))


def _patron(h: np.ndarray, tipo: str) -> np.ndarray:
    hora = h % 24
    if tipo == "horaria":
        return np.ones(h.shape, bool)
    if tipo == "trihoraria":
        return hora % constantes.valor("S5_PASO_H") == 0
    if tipo == "diurna":                                 # aeródromo diurno (sintetico.HORARIO_DIURNO_UTC)
        desde, hasta = sintetico.HORARIO_DIURNO_UTC
        return (hora >= desde) & (hora <= hasta)
    if tipo == "huecos":                                 # CAN-19: horaria con huecos de 2, 3, 4 y 6 h sin reporte
        return ~((h % 37 == 0) | (h % 53 < 2) | (h % 71 < 3) | ((h // 5) % 41 == 0))
    raise ValueError(tipo)


def _verdad(infos: dict, h: np.ndarray, *, anomalias="MC-50") -> dict:
    codigos = sorted(infos)
    v = sintetico.verdad({"h": h, "lat": np.array([infos[c].lat for c in codigos]),
                          "lon": np.array([infos[c].lon for c in codigos]), "F": np.zeros((h.size, len(codigos)))},
                         _sesgo, anomalias, semilla=_umbrales().a("SEMILLA"))
    return {c: {"b": v["b"][:, i], "r": v["obs"][:, i] - v["F"][:, i]} for i, c in enumerate(codigos)}


def _estaticos(infos: dict, *, tpi_nan: tuple[str, ...] = ()) -> pd.DataFrame:
    """ESQUEMA_ESTATICAS_CELDA de las celdas de las estaciones, más ``z_e5l`` (PED-2). En las de ``tpi_nan`` los dos
    TPI son NaN y truncados, como en los reales sin dato en el disco (NAS-9: «Sin dato en la celda o en el disco, TPI es
    NaN (y el disco sin dato queda truncado)»); los demás valores no cambian."""
    filas = []
    rng = np.random.default_rng(_umbrales().a("SEMILLA"))
    for k, c in enumerate(sorted(infos)):
        info = infos[c]
        if info.celda is None:
            continue
        fr = rng.dirichlet(np.ones(len(tipos.LULC)))
        filas.append({"celda": int(info.celda), "z_media": info.z_s, "z_poblada": info.z_s, "z_poblada_es_media": True,
                      "frac_dato": 1.0, "tpi1": float(rng.normal(0, 20)), "tpi5": float(rng.normal(0, 60)),
                      "tpi1_truncado": k % 7 == 3, "tpi5_truncado": False, "pendiente_deg": float(rng.uniform(1, 15)),
                      "log_dist_costa": float(np.log1p(80 + 90 * (info.lon + 71.2))),
                      **{col: float(fr[i]) for i, col in enumerate(tipos.LULC)}, "lat": info.lat,
                      "macrozona_cod": 2, "cod_comuna": 13101})
        if c in tpi_nan:
            filas[-1].update({"tpi1": NAN, "tpi5": NAN, "tpi1_truncado": True, "tpi5_truncado": True})
    df = pd.DataFrame(filas).astype(dict(tipos.ESQUEMA_ESTATICAS_CELDA))
    df[candidatos.COLUMNA_Z_E5L] = df["z_media"] - 150.0 + 40.0 * np.sin(np.arange(len(df)))
    return df


def _amplitud(T: np.ndarray, h: np.ndarray) -> np.ndarray:
    dia = h // 24
    inicio = np.flatnonzero(np.r_[True, dia[1:] != dia[:-1]])
    largo = np.diff(np.r_[inicio, h.size])
    amp = np.maximum.reduceat(T, inicio) - np.minimum.reduceat(T, inicio)
    amp[largo != 24] = np.nan
    return np.repeat(amp, largo)


def _fondo(infos: dict, h: np.ndarray, *, desplazar: float = 0.0) -> tuple[dict, dict]:
    """El fondo en las estaciones (ESQUEMA_PUNTOS_E5L, float32) y su clima por mes y hora UTC (TIP-17)."""
    hora = h % 24
    doy = candidatos._dia_del_anio(h)
    _, mes, _ = candidatos._mes_y_hora(h)
    puntos, clima = {}, {}
    for k, c in enumerate(sorted(infos)):
        T = 15 + 6 * np.cos(2 * np.pi * (doy - 20) / 365.25) + 5 * np.cos(2 * np.pi * (hora - 19) / 24) \
            - 0.005 * infos[c].z_s + 0.3 * k + desplazar * np.sin(h / 37.0)
        Td = T - 4 - 2 * np.cos(2 * np.pi * (hora - 19) / 24) ** 2
        u, v = 1.5 * np.sin(2 * np.pi * hora / 24) + 0.1 * k, 0.5 + 0.0 * h
        datos = {"h": h.astype(np.int32), "T_F": T.astype(np.float32), "Td_F": Td.astype(np.float32),
                 "p_F": np.full(h.size, 950.0, np.float32), "u_F": u.astype(np.float32), "v_F": v.astype(np.float32),
                 "amp_TF": _amplitud(T, h).astype(np.float32)}
        puntos[c] = pd.DataFrame(datos)
        est = candidatos.estado_c(puntos[c], h)
        clima[c] = {}
        for var in tipos.VARIABLES_CLIMA_ESTADO:
            x = np.full((12, 24), np.nan)
            for m in range(12):
                for hh in range(24):
                    s = (mes == m + 1) & (hora == hh) & np.isfinite(est[var])
                    if s.any():
                        x[m, hh] = est[var][s].mean()
            clima[c][var] = x
    return puntos, clima


def _datos(infos: dict, h: np.ndarray, residuos_T: dict, *, patrones: dict | None = None, extra: dict | None = None,
           fondo=None, con_c: bool = True, estaticos: pd.DataFrame | None = None) -> tipos.DatosCompetencia:
    """DatosCompetencia como la armaría ``orquestacion``: tabla de residuos, climatologías de A y filas de C (con
    ``estaticos``, ésos en vez de los de ``_estaticos``)."""
    U = _umbrales()
    residuos, tramos = {}, []
    for c in sorted(infos):
        mascara = _patron(h, (patrones or {}).get(c, "horaria"))
        hc = h[mascara]
        r = {v: np.full(hc.size, np.nan) for v in candidatos.VARIABLES}
        r["T"] = residuos_T[c][mascara]
        for v, x in (extra or {}).get(c, {}).items():
            r[v] = x[mascara]
        residuos[c], tr = candidatos.residuos_estacion(c, hc, r, U)
        tramos.append(tr)
    clima_a = candidatos.climatologias_a(residuos, U)
    estaticos = _estaticos(infos) if estaticos is None else estaticos
    puntos, clima = fondo if fondo is not None else (_fondo(infos, h) if con_c else ({}, {}))
    filas = {"C": candidatos.filas_c(residuos, estaticos, puntos, U, infos=infos),
             "C_est": candidatos.filas_c(residuos, estaticos, clima, U, infos=infos, climatologico=True)} \
        if con_c else {}
    grupos = {c: infos[c].grupo for c in infos}
    pliegues = tuple(particiones.pliegues_p1(grupos, U) + particiones.pliegues_p2(infos, grupos, U))
    return tipos.DatosCompetencia(residuos=residuos, climatologias=clima_a, tramos=pd.concat(tramos, ignore_index=True),
                                  filas_c=filas, estaticos=estaticos, estaciones=infos, pliegues=pliegues,
                                  puntos_e5l=puntos, clima_estado=clima)


@lru_cache(maxsize=None)
def _red_s5():
    """La red de S5 para A: 6 × 6 estaciones a ≈ 20 km y un grupo, horarias, 2010-2012."""
    infos = _red(6, 0.2)
    h = _horas("2010-01-01T00", "2013-01-01T00")
    verdad = _verdad(infos, h)
    return infos, h, verdad, _datos(infos, h, {c: verdad[c]["r"] for c in infos}, con_c=False)


@lru_cache(maxsize=None)
def _red_chica():
    """Red chica para las pruebas bit a bit, de C y de S12: 4 × 4 estaciones a ≈ 25 km y un grupo, 2011-2012."""
    infos = _red(4, 0.22)
    h = _horas("2011-01-01T00", "2013-01-01T00")
    return infos, h, _verdad(infos, h)


@lru_cache(maxsize=None)
def _datos_chica() -> tipos.DatosCompetencia:
    """Los datos completos de la red chica (con C y C_est). Compartidos: las pruebas los cambian sólo con
    ``dataclasses.replace``, nunca en su lugar."""
    infos, h, verdad = _red_chica()
    return _datos(infos, h, {c: verdad[c]["r"] for c in infos})


def _pliegue_de(datos, particion: str, codigo: str) -> tipos.Pliegue:
    return next(p for p in datos.pliegues if p.particion.value == particion and codigo in p.prueba)


def _seleccionar(cand, variable, uso, externo, datos, **kw):
    return candidatos.seleccionar(cand, variable, uso, externo, datos, _umbrales(), objetivo=_objetivo, recorte=False,
                                  **kw)


def _prediccion(cand, variable, uso, hiper, externo, datos):
    return candidatos.predecir_prueba(cand, variable, uso, hiper, externo, datos, umbrales=_umbrales())


# ---------------------------------------------------------------------------
# CAN-18 (ola 4): copia literal de ``candidatos._bases`` y ``candidatos._diseno_bruto`` de la ola 3 (fila a fila, antes
# de vectorizar). Es el oráculo de la paridad bit a bit y no se toca.
# ---------------------------------------------------------------------------
def _bases_ola3(estaticos: pd.DataFrame, h: np.ndarray, estado) -> tuple[np.ndarray, np.ndarray]:
    """Predictores base en bruto (fila × 31) y truncado del TPI (fila × 2) (CAN-9)."""
    n = h.size
    if len(estaticos) not in (1, n):
        raise ErrorCandidatos("los estáticos de C son una fila (se repite) o una por hora")

    def est(c, dtype=np.float64):
        x = estaticos[c].to_numpy(dtype=dtype)
        return np.repeat(x, n) if x.size == 1 else x
    z = est(COLUMNA_Z_C)
    columnas = {"z_km": z / M_POR_KM, "dz_km": (z - est(COLUMNA_Z_E5L)) / M_POR_KM,
                "log_dist_costa": est("log_dist_costa"), "tpi1": est("tpi1"), "tpi5": est("tpi5"),
                "pendiente_deg": est("pendiente_deg"), **{c: est(c) for c in tipos.LULC}, "lat": est("lat")}
    cod = estaticos["macrozona_cod"].to_numpy()
    ind = np.array([tipos.indicadoras_macrozona(int(c)) for c in cod], dtype=np.float64)    # D22 (a)
    ind = np.repeat(ind, n, axis=0) if len(cod) == 1 else ind
    columnas.update({m: ind[:, i] for i, m in enumerate(MACRO_C)})
    hora = np.mod(h, HORAS_DIA).astype(np.float64)
    doy = _dia_del_anio(h).astype(np.float64) if n else np.empty(0)
    for nombre, funcion, orden, periodo in _HORARIOS + _ANUALES:
        x = hora if periodo == HORAS_DIA else doy
        angulo = 2 * np.pi * orden * x / periodo
        columnas[nombre] = np.sin(angulo) if funcion == "sen" else np.cos(angulo)
    for v in ESTADO_C:
        x = np.asarray(estado[v], dtype=np.float64)
        if x.shape != h.shape:
            raise ErrorCandidatos(f"estado de C: {v} debe tener una fila por hora")
        columnas[v] = x
    B = np.column_stack([columnas[b] for b in BASES_C]) if n else np.empty((0, len(BASES_C)))
    trunc = np.column_stack([est(TRUNCADO_C[k], dtype=bool) for k in TPI_C]) if n else np.empty((0, len(TPI_C)), bool)
    return B, trunc


def _diseno_bruto_ola3(B: np.ndarray, trunc: np.ndarray) -> np.ndarray:
    """Valores de los monomios (fila × monomio) desde los predictores base (CAN-11)."""
    atomos = {"1": np.ones(B.shape[0])}
    for i, b in enumerate(BASES_C):
        if b in TPI_C:
            t = trunc[:, TPI_C.index(b)]
            atomos[f"u1:{b}"] = np.where(t, 0.0, B[:, i])
            atomos[f"u0:{b}"] = np.where(t, 0.0, 1.0)
        else:
            atomos[b] = B[:, i]
    X = np.empty((B.shape[0], len(MONOMIOS_C)))
    for j, mono in enumerate(MONOMIOS_C):
        x = atomos["1"]
        for a in mono:
            x = x * atomos[a]
        X[:, j] = x
    return X


def _como_ola3():
    """``candidatos`` con ``_bases`` y ``_diseno_bruto`` de la ola 3 (la referencia de las salidas públicas)."""
    return mock.patch.multiple(candidatos, _bases=_bases_ola3, _diseno_bruto=_diseno_bruto_ola3)


def _resultado(f, *args, **kw):
    """(«ok», valor) o («error», tipo, mensaje): para comparar también los errores."""
    try:
        return ("ok", f(*args, **kw))
    except Exception as error:                     # noqa: BLE001 (se compara el error, sea cual sea)
        return ("error", type(error), str(error))


def _bits(x) -> tuple:
    """Forma, tipo, contigüidad y bytes de un arreglo: dos arreglos con los mismos bits dan lo mismo."""
    x = np.asarray(x)
    return x.shape, x.dtype.str, x.flags.c_contiguous, x.tobytes()


# Macrozonas de las celdas del caso de CAN-18: todas las de la grilla, con «sin_region» (5) e «insular» (6) y repetidas
# fuera de orden; y comunas de varias regiones, también ≤ 0 (macrozona heredada de la vecina, TIP-18).
_MZ_CAN18 = (2, 0, 6, 1, 5, 3, 4, 2, 5)
_COMUNAS_CAN18 = (13101, 1101, 5201, 4101, 0, 8101, 11101, 13114, -1)


def _caso_can18():
    """Celdas × horas como las arma ``producto`` (una fila por punto y hora): 9 celdas con macrozonas y comunas
    distintas, un TPI truncado, una celda con los dos TPI NaN y truncados (NAS-9), una fracción NaN, y horas en el
    cambio de año y el 29 de febrero, con un estado que trae un NaN y un infinito. Son > ``_BLOQUE_FILAS`` filas."""
    infos = _red(3, 0.2, par=False)
    est = _estaticos(infos, tpi_nan=("330004",))
    est["macrozona_cod"] = np.array(_MZ_CAN18, dtype=np.int8)
    est["cod_comuna"] = np.array(_COMUNAS_CAN18, dtype=np.int32)
    est.loc[7, "lulc_agua"] = NAN
    h = np.concatenate([_horas("2011-12-20T00", "2012-01-10T00"), _horas("2012-02-20T00", "2012-03-11T00")])
    n_p = len(est)
    filas = est.iloc[np.repeat(np.arange(n_p), h.size)]
    horas = np.tile(h, n_p)
    rng = np.random.default_rng(_umbrales().a("SEMILLA"))
    estado = {"T": rng.normal(12, 6, horas.size), "T_menos_Td": np.abs(rng.normal(4, 3, horas.size)),
              "rapidez": np.abs(rng.normal(2, 1.5, horas.size)), "amp": np.abs(rng.normal(10, 4, horas.size))}
    estado["T"][17] = NAN
    estado["rapidez"][4000] = np.inf
    nb = len(BASES_C)
    modelo = tipos.ModeloC(coef=rng.normal(0, 0.1, len(candidatos.COLUMNAS_C)), media=rng.normal(0, 1, nb),
                           desvio=np.where(np.arange(nb) % 9 == 4, 0.0, rng.uniform(0.5, 2, nb)), alfa=1.0,
                           diseno=tipos.DisenoC.ESTADO)
    return infos, est, h, filas, horas, estado, modelo


# ---------------------------------------------------------------------------
# S5 (§9): la parte de los candidatos
# ---------------------------------------------------------------------------
class PruebasS5(unittest.TestCase):
    def test_s05_a_recupera_b_con_rmse_menor_que_0_3(self):
        """S5: con la verdad sintética (fondo + b(x, m, h) + anomalías de MC-50), A recupera b en las estaciones de
        prueba de los diez pliegues de P1, con sus hiperparámetros elegidos por selección anidada, con RMSE < 0,3 K."""
        infos, h, verdad, datos = _red_s5()
        errores = []
        for externo in (p for p in datos.pliegues if p.particion.value == "P1"):
            hiper = _seleccionar(Candidato.A, "T", Uso.AGUDO, externo, datos)
            self.assertIsInstance(hiper, Hiper)
            pred = _prediccion(Candidato.A, "T", Uso.AGUDO, hiper, externo, datos)
            for c, g in pred.groupby("codigo"):
                b = verdad[c]["b"][np.searchsorted(h, g["h"].to_numpy())]
                errores.append(g["correccion"].to_numpy() - b)
        e = np.concatenate(errores)
        self.assertTrue(np.isfinite(e).all())
        rmse = float(np.sqrt(np.mean(e ** 2)))
        self.assertLess(rmse, constantes.valor("S5_RMSE_A_K"), f"RMSE de A frente a b: {rmse:.3f} K")

    def test_s05_nucleo_decae_a_cero_sin_nan(self):
        """S5: lejos de las estaciones Φ → 0 sin NaN; más allá de 3L vale 0 exacto, y sin estaciones disponibles a
        una hora también; A en esos puntos vale 0."""
        U = _umbrales()
        infos, h, verdad, datos = _red_s5()
        ent = {c: infos[c] for c in sorted(infos)}
        lat0, lon0 = infos["330014"].lat, infos["330014"].lon
        km = np.array([0.0, 30.0, 80.0, 150.0, 300.0, 600.0, 2000.0])
        puntos = {"lat": lat0 - km / 111.2, "lon": np.full(km.size, lon0), "z": np.full(km.size, 500.0)}
        vec = candidatos.vecinos(puntos, ent, Hiper(50.0, 0.0, 0.2), U)
        q = np.ones((3, len(ent)))
        disp = np.ones(q.shape, bool)
        disp[2] = False                                       # una hora sin ninguna estación disponible
        phi, sk = candidatos.campo(vec, q, disp)
        self.assertTrue(np.isfinite(phi).all() and np.isfinite(sk).all())
        self.assertTrue(np.all(np.diff(phi[0, 1:]) <= 0), phi[0])
        lejos = candidatos.distancia_efectiva(puntos, ent, 0.0).min(axis=1) > U.a("NUC_CORTE") * 50.0
        self.assertTrue(lejos[-3:].all())
        self.assertTrue(np.all(phi[:, lejos] == 0.0) and np.all(sk[:, lejos] == 0.0))
        self.assertTrue(np.all(phi[2] == 0.0) and np.all(sk[2] == 0.0))
        self.assertGreater(phi[0, 0], 0.8)
        A = candidatos.correccion_a(vec, datos.climatologias[datos.climatologias["variable"] == "T"], h[:48])
        self.assertTrue(np.isfinite(A).all())
        self.assertTrue(np.all(A[:, -1] == 0.0))
        # Una estación de prueba a más de 3L de todas: corrección 0 y sin soporte (§4.2, CAN-15); cerca, con soporte.
        lejana = _info("339999", -36.5, -71.0, 300.0, None)
        infos2 = _completar({**infos, "339999": lejana})
        r2 = {c: verdad[c]["r"] for c in infos}
        r2["339999"] = np.zeros(h.size)
        datos2 = _datos(infos2, h, r2, con_c=False)
        externo = tipos.Pliegue("prueba", tipos.Particion.P1, ("330014", "339999"),
                                tuple(c for c in sorted(infos) if c != "330014"))
        for cand, hiper in ((Candidato.A, Hiper(50.0, 0.0, 0.05)), (Candidato.B, Hiper(50.0, 0.0, 0.05)),
                            (Candidato.AB, (Hiper(50.0, 0.0, 0.05), Hiper(25.0, 0.0, 0.2)))):
            with self.subTest(candidato=cand.value):
                pred = _prediccion(cand, "T", Uso.AGUDO, hiper, externo, datos2)
                g = pred[pred["codigo"] == "339999"]
                self.assertTrue(len(g) and (g["correccion"] == 0.0).all() and not g["soporte"].any())
                self.assertTrue(pred[pred["codigo"] == "330014"]["soporte"].all())

    def test_s05_a_sin_saltos_horarios_con_estaciones_cada_3h_y_diurnas(self):
        """S5: con estaciones cada 3 h y aeródromos diurnos, A no salta más de 0,2 K de una hora a la siguiente en
        ningún punto ni hora (los diurnos, con hueco de 12 h, no entran en A: §4.3, «en vez de entrar sólo a ciertas
        horas»). La verdad cambia a lo más 0,11 K por hora."""
        U = _umbrales()
        infos = _red(5, 0.2, par=False)
        h = _horas("2010-01-01T00", "2013-01-01T00")
        verdad = _verdad(infos, h)
        codigos = sorted(infos)
        patrones = {c: ("trihoraria" if i % 2 == 0 else "diurna") for i, c in enumerate(codigos)}
        datos = _datos(infos, h, {c: verdad[c]["r"] for c in infos}, patrones=patrones, con_c=False)
        clima = datos.climatologias[datos.climatologias["variable"] == "T"]
        califica = clima.groupby("codigo")["califica"].all()
        for c in codigos:
            self.assertEqual(bool(califica[c]), patrones[c] == "trihoraria", c)
        lat = np.linspace(-33.05, -33.75, 6)
        lon = np.linspace(-71.15, -70.45, 6)
        puntos = {"lat": np.repeat(lat, lon.size), "lon": np.tile(lon, lat.size), "z": np.full(lat.size * lon.size, 400.0)}
        un_anio = _horas("2011-01-01T00", "2012-01-01T00")
        for L, lam, kappa in ((10.0, 0.0, 0.05), (50.0, 50.0, 0.05), (200.0, 150.0, 1.0)):
            vec = candidatos.vecinos(puntos, infos, Hiper(L, lam, kappa), U)
            A = candidatos.correccion_a(vec, clima, un_anio)
            salto = float(np.abs(np.diff(A, axis=0)).max())
            self.assertLessEqual(salto, constantes.valor("S5_SALTO_A_K"), f"L = {L}: salto de {salto:.3f} K")
        hh = np.arange(25)
        diurna = 0.4 * np.cos(2 * np.pi * (hh - 15) / 24)          # la parte diaria de _sesgo
        self.assertLess(float(np.abs(np.diff(diurna)).max()), constantes.valor("S5_SALTO_A_K"))

    def test_s05_perturbar_prueba_grupo_y_amortiguador_no_cambia_predicciones(self):
        """S5 (§4.9): perturbar una estación de prueba, su grupo a ≤ 2 km y, en P2, su amortiguador no cambia, bit a
        bit, ni sus hiperparámetros ni sus predicciones, en A, B, AB, C y C_est, en P1 y en P2. La perturbación
        pasa por toda la cadena: tabla de residuos, tramos y δ, climatologías de A y filas de C."""
        infos, h, verdad = _red_chica()
        codigo = "330000"                                      # el de su grupo (330016 está a ≈ 0,8 km)
        grupo = [c for c in infos if infos[c].grupo == infos[codigo].grupo]
        self.assertEqual(len(grupo), 2)
        fondo = _fondo(infos, h)
        base = _datos(infos, h, {c: verdad[c]["r"] for c in infos}, fondo=fondo)
        rng = np.random.default_rng(_umbrales().a("SEMILLA"))
        for particion in ("P1", "P2"):
            externo = _pliegue_de(base, particion, codigo)
            perturbadas = set(grupo) | (set(externo.excluidas) if particion == "P2" else set())
            if particion == "P2":
                self.assertTrue(externo.excluidas, "el pliegue de P2 debe tener amortiguador")
            r = {c: verdad[c]["r"] + (rng.normal(0, 2.0, h.size) + 3.0 if c in perturbadas else 0.0) for c in infos}
            otro = _datos(infos, h, r, fondo=fondo)
            for cand in (Candidato.A, Candidato.B, Candidato.AB, Candidato.C, Candidato.C_EST):
                uso = Uso.CRONICO if cand is Candidato.C_EST else Uso.AGUDO
                with self.subTest(particion=particion, candidato=cand.value):
                    sel = [_seleccionar(cand, "T", uso, externo, d) for d in (base, otro)]
                    self.assertEqual(repr(sel[0]), repr(sel[1]))
                    pred = [_prediccion(cand, "T", uso, sel[0], externo, d) for d in (base, otro)]
                    for p in pred:
                        self.assertTrue(set(grupo) <= set(p["codigo"]))
                    a, b = (p[p["codigo"].isin(grupo)] for p in pred)
                    self.assertTrue(np.array_equal(a["h"].to_numpy(), b["h"].to_numpy()))
                    self.assertEqual(a["correccion"].to_numpy().tobytes(), b["correccion"].to_numpy().tobytes())
                    self.assertTrue(np.array_equal(a["soporte"].to_numpy(), b["soporte"].to_numpy()))
                    self.assertTrue(np.isfinite(a["correccion"].to_numpy()).any())

    def test_s05_cambio_de_sensor_no_pasa_a_b_ni_ab(self):
        """S5 (§4.4, §4.8): un cambio de sensor sintético de 1 K en una estación da un tramo (δ lo quita) y no pasa a
        B ni a AB en un punto a 3 km: la diferencia con y sin el cambio no tiene escalón (≤ 0,2 K), mientras que con
        r sin homogeneizar el escalón sí pasaría (> 0,5 K)."""
        U = _umbrales()
        infos = _red(3, 0.25, par=False)
        h = _horas("2010-01-01T00", "2016-01-01T00")
        verdad = _verdad(infos, h)
        sensor = constantes.valor("S5_SENSOR_K")
        k0 = _h("2013-01-01T00")
        estacion = "330004"                                    # la del centro
        r_con = {c: verdad[c]["r"] + (np.where(h >= k0, sensor, 0.0) if c == estacion else 0.0) for c in infos}
        sin = _datos(infos, h, {c: verdad[c]["r"] for c in infos}, con_c=False)
        con = _datos(infos, h, r_con, con_c=False)
        tr = con.tramos[(con.tramos["codigo"] == estacion) & (con.tramos["variable"] == "T")]
        self.assertEqual(len(tr), 2)
        self.assertLessEqual(abs(int(tr["desde_mes"].iloc[1]) - int(homogeneidad.mes2000(np.array([k0]))[0])),
                             U.a("K4_VENTANA") // 2 - 1)
        info = infos[estacion]
        punto = {"lat": np.array([info.lat - 3.0 / 111.2]), "lon": np.array([info.lon]), "z": np.array([info.z_s])}
        vec = candidatos.vecinos(punto, infos, Hiper(10.0, 0.0, 0.05), U)
        hv = h[h % 3 == 0]
        antes, despues = hv < k0, hv >= k0

        def escalon(serie):
            return float(np.mean(serie[despues]) - np.mean(serie[antes]))

        def campo_de(datos, clase):
            Q = candidatos._matriz_en_horas(datos, vec.codigos, clase, "T", hv, U)
            return candidatos.campo(vec, Q, np.isfinite(Q))[0][:, 0]
        for clase in ("b", "a"):
            with self.subTest(candidato="B" if clase == "b" else "AB"):
                d = campo_de(con, clase) - campo_de(sin, clase)
                if clase == "a":
                    clima_con = con.climatologias[con.climatologias["variable"] == "T"]
                    clima_sin = sin.climatologias[sin.climatologias["variable"] == "T"]
                    d = d + candidatos.correccion_a(vec, clima_con, hv)[:, 0] - candidatos.correccion_a(vec, clima_sin, hv)[:, 0]
                self.assertLessEqual(abs(escalon(d)), 0.2 * sensor)
        d_crudo = campo_de(con, "r") - campo_de(sin, "r")
        self.assertGreater(abs(escalon(d_crudo)), 0.5 * sensor)


# ---------------------------------------------------------------------------
# S12 (§9): la parte de los candidatos
# ---------------------------------------------------------------------------
class PruebasS12Candidatos(unittest.TestCase):
    def test_s12_residuo_cero_da_correccion_cero_y_el_reloj_no_se_absorbe(self):
        """S12: con el reloj bien (residuo 0 en todas las estaciones), los cinco candidatos dan corrección 0 exacta
        en las estaciones de prueba: no agregan ciclo diario. Con un error de ±1 h en una estación de prueba (su
        residuo es T_F(u ± 1) − T_F(u)), su predicción sigue en 0 bit a bit (nada de ella entra a su predicción), así
        que el ciclo diario del error queda entero en el residuo menos la predicción, que es lo que ve CD (§5.2)."""
        infos, h, _ = _red_chica()
        fondo = _fondo(infos, h)
        cero = {c: np.zeros(h.size) for c in infos}
        codigo = "330005"
        T_F = fondo[0][codigo]["T_F"].to_numpy(np.float64)
        for desfase in (1, -1):
            r = dict(cero)
            r[codigo] = np.roll(T_F, -desfase) - T_F
            datos = _datos(infos, h, r, fondo=fondo)
            externo = _pliegue_de(datos, "P1", codigo)
            for cand in (Candidato.A, Candidato.B, Candidato.AB, Candidato.C, Candidato.C_EST):
                uso = Uso.CRONICO if cand is Candidato.C_EST else Uso.AMBIENTAL
                with self.subTest(desfase=desfase, candidato=cand.value):
                    hiper = _seleccionar(cand, "T", uso, externo, datos)
                    pred = _prediccion(cand, "T", uso, hiper, externo, datos)
                    v = pred["correccion"].to_numpy()
                    self.assertTrue(np.all(v[np.isfinite(v)] == 0.0))
                    self.assertTrue(np.isfinite(v).any())
                    g = pred[pred["codigo"] == codigo]
                    resto = r[codigo][np.searchsorted(h, g["h"].to_numpy())] - g["correccion"].to_numpy()
                    hora = g["h"].to_numpy() % 24
                    ciclo = np.array([np.nanmean(resto[hora == x]) for x in range(24)])
                    self.assertGreater(float(np.sqrt(np.mean((ciclo - ciclo.mean()) ** 2))), 0.5)


# ---------------------------------------------------------------------------
# Núcleo, A, B, AB, C y C_est
# ---------------------------------------------------------------------------
class PruebasCandidatos(unittest.TestCase):
    def test_valores_que_suponen_las_pruebas(self):
        U = _umbrales()
        for ident, valor in VALORES_ANEXO_A.items():
            self.assertEqual(U.a(ident), valor, ident)

    def test_phi_con_dos_productos_dispersos(self):
        """§3 del diseño y CAN-3: Φ = Σk·w·q/(κ + Σk·w) con dos productos dispersos; κ se aplica al final, así que las
        cuatro κ salen de las mismas sumas; Σk se devuelve. Se compara con el cálculo denso a mano."""
        U = _umbrales()
        infos = _red(5, 0.15)
        rng = np.random.default_rng(U.a("SEMILLA"))
        puntos = {"lat": rng.uniform(-33.8, -33.0, 9), "lon": rng.uniform(-71.2, -70.5, 9), "z": rng.uniform(0, 900, 9)}
        q = rng.normal(0, 1, (50, len(infos)))
        disp = rng.random(q.shape) > 0.3
        q[~disp & (rng.random(q.shape) > 0.5)] = np.nan
        vec = candidatos.vecinos(puntos, infos, Hiper(25.0, 50.0, 0.2), U)
        num, den = candidatos.sumas_nucleo(vec, q, disp)
        D = candidatos.distancia_efectiva(puntos, infos, 50.0)
        K = np.zeros_like(D)
        for i in range(D.shape[0]):
            for j, s in enumerate(vec.est[i]):
                if s >= 0:
                    K[i, s] = math.exp(-0.5 * (D[i, s] / 25.0) ** 2)
                    self.assertEqual(vec.d_ef[i, j], D[i, s])
        ok = disp & np.isfinite(q)
        grupo = vec.grupo_est
        cuenta = np.stack([ok[:, grupo == g].sum(axis=1) for g in range(len(vec.grupos))], axis=1)
        w = np.where(ok, 1.0 / np.maximum(cuenta[:, grupo], 1), 0.0)
        num_d = np.matmul(np.where(ok, w * np.nan_to_num(q), 0.0), K.T)
        den_d = np.matmul(w, K.T)
        np.testing.assert_allclose(num, num_d, rtol=1e-12, atol=1e-14)
        np.testing.assert_allclose(den, den_d, rtol=1e-12, atol=1e-14)
        for kappa in U.a("NUC_KAPPA"):
            phi, sk = candidatos.campo(dataclasses.replace(vec, hiper=Hiper(25.0, 50.0, kappa)), q, disp)
            self.assertEqual(phi.tobytes(), (num / (kappa + den)).tobytes())
            self.assertEqual(sk.tobytes(), den.tobytes())
        # El corte en 3L y la lista de 30, con empates por el menor código.
        self.assertTrue(np.all(vec.d_ef[vec.est >= 0] <= U.a("NUC_CORTE") * 25.0))
        for i in range(vec.est.shape[0]):
            d = vec.d_ef[i][vec.est[i] >= 0]
            self.assertTrue(np.all(np.diff(d) >= 0))
            self.assertTrue(np.all(vec.est[i][d.size:] == candidatos.SIN_VECINO))

    def test_corte_3l_inclusivo(self):
        """§4.2: «k(x,s) = exp(−½ (d_ef/L)²) si d_ef ≤ 3L»: una estación a d_ef = 3L exacto es vecina y pesa
        exp(−½·9); un metro más de desnivel la deja fuera. Con d_h = 0 (mismo lugar) y λ·|Δz|/1.000 = 3L la igualdad
        es exacta en coma flotante (CAN-1)."""
        U = _umbrales()
        infos = {"330000": _info("330000", -33.4, -70.6, 500.0, None)}     # una sola: su grupo es «G330000»
        for L, lam, dz in ((10.0, 50.0, 600.0), (100.0, 150.0, 2000.0)):
            with self.subTest(L=L, lam=lam):
                corte = U.a("NUC_CORTE") * L
                self.assertEqual(lam * dz / 1000, corte)
                puntos = {"lat": np.full(3, -33.4), "lon": np.full(3, -70.6),
                          "z": np.array([500.0 + dz, 500.0 - dz, 500.0 + dz + 1.0])}
                d = candidatos.distancia_efectiva(puntos, infos, lam)[:, 0]
                self.assertEqual(d[:2].tolist(), [corte, corte])
                self.assertGreater(d[2], corte)
                vec = candidatos.vecinos(puntos, infos, Hiper(L, lam, 0.05), U)
                self.assertEqual(vec.est[:, 0].tolist(), [0, 0, candidatos.SIN_VECINO])
                _, sk = candidatos.campo(vec, np.ones((1, 1)), np.ones((1, 1), bool))
                k = math.exp(-0.5 * (corte / L) ** 2)
                self.assertEqual(sk[0, 2], 0.0)
                np.testing.assert_allclose(sk[0, :2], [k, k], rtol=1e-14, atol=0)

    def test_pesos_de_grupo_1_entre_disponibles(self):
        """§2.5: cada miembro disponible del grupo pesa 1/(miembros disponibles a esa hora). Los miembros se cuentan
        entre todas las estaciones de entrenamiento, también los que no están en la lista de 30 del punto (CAN-2)."""
        U = _umbrales()
        lat0, lon0 = -33.4, -70.6
        infos = {}
        for k in range(29):                                     # 29 estaciones a 5 km, en círculo
            ang = 2 * np.pi * k / 29
            infos[f"{340000 + k:06d}"] = _info(f"{340000 + k:06d}", lat0 + 5 / 111.2 * np.sin(ang),
                                                lon0 + 5 / 92.7 * np.cos(ang), 500.0, None)
        infos["340100"] = _info("340100", lat0 + 8 / 111.2, lon0, 500.0, None)      # el 30.º vecino
        infos["340101"] = _info("340101", lat0 + 9 / 111.2, lon0, 500.0, None)      # el 31.º, a 1 km del 30.º
        infos = _completar(infos)
        self.assertEqual(infos["340100"].grupo, infos["340101"].grupo)
        punto = {"lat": np.array([lat0]), "lon": np.array([lon0]), "z": np.array([500.0])}
        vec = candidatos.vecinos(punto, infos, Hiper(10.0, 0.0, 0.05), U)
        codigos = list(vec.codigos)
        i100, i101 = codigos.index("340100"), codigos.index("340101")
        self.assertIn(i100, vec.est[0])
        self.assertNotIn(i101, vec.est[0])
        q = np.zeros((2, len(codigos)))
        q[:, i100] = 1.0
        disp = np.ones(q.shape, bool)
        disp[1, i101] = False                                   # hora 2: el compañero no está disponible
        num, den = candidatos.sumas_nucleo(vec, q, disp)
        k100 = math.exp(-0.5 * (vec.d_ef[0, list(vec.est[0]).index(i100)] / 10.0) ** 2)
        self.assertAlmostEqual(num[0, 0], 0.5 * k100, places=15)
        self.assertAlmostEqual(num[1, 0], k100, places=15)
        self.assertAlmostEqual(den[1, 0] - den[0, 0], 0.5 * k100, places=14)

    def test_filas_de_c_y_peso_mc05(self):
        """§4.6 y MC-05: hasta 4.000 filas al azar con la semilla de la etiqueta «C/<código>/<variable>» (MC-44), con
        peso mín(4.000/n_s; 10) y n_s = filas de s en la muestra; la muestra no depende de las otras estaciones."""
        U = _umbrales()
        infos = _red(2, 0.2, par=False)
        h = _horas("2010-01-01T00", "2011-06-01T00")
        largos = {"330000": 10000, "330001": 1000, "330002": 300, "330003": 0}
        r = {c: np.where(np.arange(h.size) < n, np.sin(h / 50.0), np.nan) for c, n in largos.items()}
        datos = _datos(infos, h, r)
        filas = datos.filas_c["C"]["T"]
        self.assertNotIn("330003", filas)
        for c, n in largos.items():
            if n == 0:
                continue
            s = filas[c]
            n_s = min(n, U.a("C_FILAS"))
            self.assertEqual(s.n_filas, n_s)
            self.assertEqual(s.peso, min(U.a("C_FILAS") / n_s, U.a("C_PESO_MAX")))
            self.assertAlmostEqual(s.xtx[0, 0], s.peso * n_s, places=6)
        self.assertEqual(filas["330000"].peso, 1.0)
        self.assertEqual(filas["330001"].peso, 4.0)
        self.assertEqual(filas["330002"].peso, 10.0)
        pool = np.arange(largos["330000"])
        esperado = np.sort(numerico.generador(U.a("SEMILLA"), "C", "330000", "T").choice(pool, U.a("C_FILAS"),
                                                                                           replace=False))
        self.assertTrue(np.array_equal(filas["330000"].horas, h[esperado]))
        sola = candidatos.filas_c({"330000": datos.residuos["330000"]}, datos.estaticos, datos.puntos_e5l, U,
                                  infos=infos)["T"]["330000"]
        self.assertEqual(sola.xtx.tobytes(), filas["330000"].xtx.tobytes())
        # C y C_est con las mismas horas válidas: la misma muestra.
        self.assertTrue(np.array_equal(datos.filas_c["C_est"]["T"]["330000"].horas, filas["330000"].horas))

    def test_c_est_con_estado_climatologico(self):
        """§4.7 y A14: C_est usa el clima del estado en el mes y la hora UTC de cada h; no depende del estado horario
        (perturbarlo no cambia C_est y sí C), y con el mismo mes, hora y día del año da lo mismo en años distintos."""
        U = _umbrales()
        infos, h, verdad = _red_chica()
        fondo = _fondo(infos, h)
        datos = _datos(infos, h, {c: verdad[c]["r"] for c in infos}, fondo=fondo)
        codigo = "330006"
        ent = [c for c in infos if c != codigo]
        clima = fondo[1][codigo]
        # El estado horario de C (CAN-10): T_F, T_F − Td_F, √(u_F² + v_F²) y amp_TF de los float32 guardados (A1).
        F = fondo[0][codigo]
        horas_f = np.array([F["h"].iloc[5], F["h"].iloc[100], -7], dtype=np.int64)
        ec = candidatos.estado_c(F, horas_f)
        fila_f = F.iloc[[5, 100]]
        T32 = fila_f["T_F"].to_numpy(np.float32).astype(np.float64)
        np.testing.assert_array_equal(ec["T"][:2], T32)
        np.testing.assert_array_equal(ec["T_menos_Td"][:2], T32 - fila_f["Td_F"].to_numpy(np.float32).astype(np.float64))
        np.testing.assert_array_equal(ec["rapidez"][:2], np.hypot(fila_f["u_F"].to_numpy(np.float32).astype(np.float64),
                                                                    fila_f["v_F"].to_numpy(np.float32).astype(np.float64)))
        np.testing.assert_array_equal(ec["amp"][:2], fila_f["amp_TF"].to_numpy(np.float32).astype(np.float64))
        self.assertTrue(all(np.isnan(ec[v][2]) for v in tipos.VARIABLES_CLIMA_ESTADO))   # hora fuera de la tabla
        est = candidatos.estado_c_est(clima, np.array([_h("2011-07-04T05"), _h("2012-02-29T23")]))
        self.assertEqual(est["T"][0], clima["T"][6, 5])
        self.assertEqual(est["amp"][1], clima["amp"][1, 23])
        m_est = candidatos.ajustar_c(datos.filas_c["C_est"]["T"], ent, 10.0)
        self.assertIs(m_est.diseno, tipos.DisenoC.CLIMATOLOGICO)
        fila = datos.estaticos[datos.estaticos["celda"] == infos[codigo].celda]
        horas = np.array([_h("2011-03-10T14"), _h("2012-03-09T14")])     # mismo día del año (2012 es bisiesto)
        self.assertEqual(candidatos._dia_del_anio(horas)[0], candidatos._dia_del_anio(horas)[1])
        p = candidatos.predecir_c(m_est, fila, horas, clima)
        self.assertEqual(p[0], p[1])
        otro = _fondo(infos, h, desplazar=3.0)
        datos2 = _datos(infos, h, {c: verdad[c]["r"] for c in infos}, fondo=(otro[0], fondo[1]))
        m_est2 = candidatos.ajustar_c(datos2.filas_c["C_est"]["T"], ent, 10.0)
        self.assertEqual(m_est.coef.tobytes(), m_est2.coef.tobytes())
        m_c, m_c2 = (candidatos.ajustar_c(d.filas_c["C"]["T"], ent, 10.0) for d in (datos, datos2))
        self.assertIs(m_c.diseno, tipos.DisenoC.ESTADO)
        self.assertNotEqual(m_c.coef.tobytes(), m_c2.coef.tobytes())
        # C_est sólo en lo crónico (§4.7, «Candidato C_est (sólo lo crónico)»): en la selección y en la predicción.
        for uso in (Uso.AGUDO, Uso.AMBIENTAL):
            with self.subTest(uso=uso.value):
                with self.assertRaises(candidatos.ErrorCandidatos):
                    _seleccionar(Candidato.C_EST, "T", uso, datos.pliegues[0], datos)
                with self.assertRaisesRegex(candidatos.ErrorCandidatos, "crónico"):
                    _prediccion(Candidato.C_EST, "T", uso, 10.0, datos.pliegues[0], datos)
        cronico = _prediccion(Candidato.C_EST, "T", Uso.CRONICO, 10.0, datos.pliegues[0], datos)
        self.assertTrue(len(cronico) and np.isfinite(cronico["correccion"].to_numpy()).any())

    def test_u_v_eligen_hiperparametros_juntos_mc43(self):
        """MC-43: u y v eligen juntos (L, λ, κ) con el error vectorial: el objetivo recibe Σ(Δu² + Δv²) en las horas
        con las dos, «u», «v» y «uv» dan lo mismo, y el rótulo es «uv». C elige α igual (CAN-14)."""
        U = _umbrales()
        infos, h, verdad = _red_chica()
        rng = np.random.default_rng(U.a("SEMILLA"))
        extra = {c: {"u": verdad[c]["r"] * 0.5 + rng.normal(0, 0.3, h.size),
                     "v": -verdad[c]["r"] * 0.2 + rng.normal(0, 0.3, h.size)} for c in infos}
        datos = _datos(infos, h, {c: verdad[c]["r"] for c in infos}, extra=extra)
        externo = _pliegue_de(datos, "P1", "330005")
        vistos = []

        def registrar(internos, sumas, *, candidato, variable, uso):
            vistos.append(variable)
            return _objetivo(internos, sumas, candidato=candidato, variable=variable, uso=uso)
        for cand in (Candidato.B, Candidato.C):
            with self.subTest(candidato=cand.value):
                elegidos = [candidatos.seleccionar(cand, v, Uso.AMBIENTAL, externo, datos, U, objetivo=registrar,
                                                   recorte=False) for v in ("u", "v", "uv")]
                self.assertEqual(repr(elegidos[0]), repr(elegidos[1]))
                self.assertEqual(repr(elegidos[0]), repr(elegidos[2]))
        self.assertEqual(set(vistos), {"uv"})
        interno = particiones.pliegues_internos(externo, infos, candidatos._grupos(infos), U)[0]
        juntos = candidatos._sse_nucleo(Candidato.B, ("u", "v"), interno, datos, U, False)
        solos = [candidatos._sse_nucleo(Candidato.B, (v,), interno, datos, U, False) for v in ("u", "v")]
        theta = next(iter(juntos))
        for c, (sse, n) in juntos[theta].items():
            self.assertEqual(n, solos[0][theta][c][1])
            self.assertAlmostEqual(sse, solos[0][theta][c][0] + solos[1][theta][c][0], places=8)

    def test_climatologia_a_requisitos_y_d19(self):
        """§4.3: ≥ 60 valores de ≥ 2 años, hueco circular ≤ 4 h, k = 3 sólo con ≥ 12 horas UTC y el recorte del
        10 %; D19: sin rango completo en el segundo ajuste la estación no entra en A ese mes (rbar NaN)."""
        U = _umbrales()
        h = _horas("2010-01-01T00", "2012-01-01T00")
        hora = h % 24
        pura = 0.7 + 0.5 * np.cos(2 * np.pi * (hora - 15) / 24) + 0.2 * np.sin(2 * np.pi * 2 * hora / 24)
        c = candidatos.climatologia_a(h, pura, U, codigo="330000", variable="T")
        tipos.validar_esquema(c, tipos.ESQUEMA_CLIMA_A, nombre="clima")
        self.assertEqual(len(c), 12 * 24)
        self.assertTrue(c["califica"].all())
        np.testing.assert_allclose(c["rbar"].to_numpy(), np.tile(pura[:24], 12), atol=1e-12)
        sucia = pura.copy()
        sucia[::97] += 40.0                                    # menos del 10 % de valores atípicos de una cola
        np.testing.assert_allclose(candidatos.climatologia_a(h, sucia, U, codigo="330000", variable="T")["rbar"],
                                   c["rbar"], atol=0.05)
        diurna = np.where((hora >= 11) & (hora <= 23), pura, np.nan)
        self.assertFalse(candidatos.climatologia_a(h, diurna, U, codigo="330000", variable="T")["califica"].any())
        un_anio = np.where(h < _h("2011-01-01T00"), pura, np.nan)
        self.assertFalse(candidatos.climatologia_a(h, un_anio, U, codigo="330000", variable="T")["califica"].any())
        pocos = np.full(h.size, np.nan)
        _, mes, _ = candidatos._mes_y_hora(h)
        idx = np.flatnonzero(np.isin(mes, (12, 1, 2)) & (hora % 3 == 0))
        for n, esperado in ((U.a("A_MIN_N") - 1, False), (U.a("A_MIN_N"), True)):
            x = pocos.copy()
            elegidos = np.r_[idx[:n // 2], idx[-(n - n // 2):]]
            x[elegidos] = pura[elegidos]
            cal = candidatos.climatologia_a(h, x, U, codigo="330000", variable="T")
            self.assertEqual(bool(cal[cal["mes"] == 1]["califica"].all()), esperado, n)
        tri = np.where(hora % 3 == 0, pura, np.nan)
        with mock.patch.object(numerico, "armonico_recortado", wraps=numerico.armonico_recortado) as espia:
            candidatos.climatologia_a(h, tri, U, codigo="330000", variable="T")
        self.assertTrue(all(llamada.args[2] == 2 for llamada in espia.call_args_list))
        with mock.patch.object(numerico, "armonico_recortado", wraps=numerico.armonico_recortado) as espia:
            candidatos.climatologia_a(h, pura, U, codigo="330000", variable="T")
        self.assertTrue(all(llamada.args[2] == 3 for llamada in espia.call_args_list))
        original = numerico.armonico_recortado
        llamadas = []

        def por_mes(hs, r, k, recorte):              # los meses se ajustan en orden: la 7.ª llamada es julio
            llamadas.append(1)
            if len(llamadas) == 7:
                raise numerico.DisenoDeficiente("segundo ajuste sin rango completo")
            return original(hs, r, k, recorte)
        with mock.patch.object(numerico, "armonico_recortado", side_effect=por_mes):
            d19 = candidatos.climatologia_a(h, pura, U, codigo="330000", variable="T")
        julio = d19[d19["mes"] == 7]
        self.assertFalse(julio["califica"].any())
        self.assertTrue(julio["rbar"].isna().all())
        self.assertTrue(d19[d19["mes"] != 7]["califica"].all())

    def test_climatologia_a_bordes_del_hueco_y_de_k3(self):
        """§4.3 en sus bordes: «hueco circular ≤ 4 h» (con 4 h exactas califica; con 5 h, no) y «k = 3 si hay ≥ 12
        horas UTC distintas» (con 12 exactas, k = 3; con 11, k = 2). Con la verdad armónica de orden ≤ 2, la que
        califica la recupera."""
        U = _umbrales()
        self.assertEqual((U.a("A_HUECO_H"), U.a("A_HORAS_K3")), (4, 12))     # los casos de abajo suponen estos
        h = _horas("2010-01-01T00", "2012-01-01T00")
        hora = h % 24
        pura = 0.7 + 0.5 * np.cos(2 * np.pi * (hora - 15) / 24) + 0.2 * np.sin(2 * np.pi * 2 * hora / 24)
        casos = (  # (horas UTC observadas, hueco circular, califica, órdenes k usados)
            (np.arange(0, 24, 4), 4, True, {2}),          # 0, 4, …, 20: hueco de 4 h exactas, 6 horas
            (np.arange(0, 24, 5), 5, False, set()),        # 0, 5, …, 20: hueco de 5 h
            (np.arange(0, 24, 2), 2, True, {3}),           # 12 horas UTC distintas exactas
            (np.arange(0, 22, 2), 4, True, {2}),           # 0, 2, …, 20: 11 horas, hueco de 4 h (20 → 0)
        )
        for horas_utc, hueco, califica, ks in casos:
            with self.subTest(horas=horas_utc.tolist()):
                self.assertEqual(numerico.hueco_circular_max(horas_utc, 24), hueco)
                x = np.where(np.isin(hora, horas_utc), pura, np.nan)
                with mock.patch.object(numerico, "armonico_recortado", wraps=numerico.armonico_recortado) as espia:
                    c = candidatos.climatologia_a(h, x, U, codigo="330000", variable="T")
                self.assertEqual(bool(c["califica"].all()), califica)
                self.assertEqual(bool(c["califica"].any()), califica)
                self.assertEqual({llamada.args[2] for llamada in espia.call_args_list}, ks)
                if califica:
                    np.testing.assert_allclose(c["rbar"].to_numpy(), np.tile(pura[:24], 12), atol=1e-9)
                else:
                    self.assertTrue(c["rbar"].isna().all())

    def test_a_interpolada_entre_centros_de_mes_mc41(self):
        """MC-41: A se interpola linealmente entre los centros de mes (punto medio entre la primera y la última hora
        UTC), con diciembre unido al enero siguiente; en el centro vale A del mes."""
        U = _umbrales()
        infos = {"330000": _info("330000", -33.4, -70.6, 500.0, None)}     # una sola: su grupo es «G330000»
        filas = []
        for m in range(1, 13):
            for hh in range(24):
                filas.append({"codigo": "330000", "variable": "T", "mes": m, "hora": hh, "rbar": float(m),
                              "califica": True})
        clima = pd.DataFrame(filas).astype(dict(tipos.ESQUEMA_CLIMA_A))
        punto = {"lat": np.array([-33.4]), "lon": np.array([-70.6]), "z": np.array([500.0])}
        vec = candidatos.vecinos(punto, infos, Hiper(10.0, 0.0, 0.05), U)
        factor = 1.0 / (0.05 + 1.0)                              # distancia 0: k = 1 y Φ = q/(κ + 1)

        def centro(desde, hasta):
            return (_h(desde) + _h(hasta)) / 2

        dic10, ene, feb = (centro("2010-12-01T00", "2010-12-31T23"), centro("2011-01-01T00", "2011-01-31T23"),
                           centro("2011-02-01T00", "2011-02-28T23"))
        dic, ene12 = centro("2011-12-01T00", "2011-12-31T23"), centro("2012-01-01T00", "2012-01-31T23")
        casos = [(math.floor(ene), dic10, ene, 12, 1), (math.ceil(ene), ene, feb, 1, 2),
                 (_h("2011-12-31T23"), dic, ene12, 12, 1), (_h("2012-01-01T00"), dic, ene12, 12, 1),
                 (_h("2011-02-14T12"), ene, feb, 1, 2)]
        h = np.array([c[0] for c in casos], dtype=np.int64)
        A = candidatos.correccion_a(vec, clima, h)[:, 0]
        for a, (hora, c_a, c_b, m_a, m_b) in zip(A, casos):
            t = (hora - c_a) / (c_b - c_a)
            self.assertTrue(0 < t < 1)
            self.assertAlmostEqual(a, factor * ((1 - t) * m_a + t * m_b), places=12)
        self.assertLess(abs(A[3] - A[2]), factor * 11 / (31 * 24) * 1.01)     # diciembre sigue en enero

    def test_interpolar_no_observadas(self):
        """§4.4 y CAN-6: sólo entre dos reportes consecutivos válidos a ≤ 3 h; un hueco mayor, un valor inválido o un
        reporte inválido en medio no se interpolan."""
        U = _umbrales()
        h = np.array([0, 3, 4, 8, 9, 10, 12, 14, 15], dtype=np.int64)
        v = np.array([0.0, 3.0, 1.0, 5.0, np.nan, 1.0, 3.0, np.nan, 2.0])
        hi, vi = candidatos.interpolar_no_observadas(h, v, U)
        self.assertEqual(hi.tolist(), [1, 2, 11])
        np.testing.assert_allclose(vi, [1.0, 2.0, 2.0])
        with self.assertRaises(candidatos.ErrorCandidatos):
            candidatos.interpolar_no_observadas(h[::-1], v, U)

    def test_residuos_estacion_y_delta_nan_d40(self):
        """CAN-8 y D40: la tabla de residuos sigue su esquema (float32, horas interpoladas aparte); con δ NaN (sin
        horas estables comunes a los tramos) r̃ queda NaN y la estación no está disponible en B ni en AB."""
        U = _umbrales()
        h = _horas("2010-01-01T00", "2014-01-01T00")
        meses = homogeneidad.mes2000(h)
        r = np.where(meses >= int(meses[0]) + 24, 1.0, 0.0) + 0.1 * np.sin(h / 7.0)
        vacio = np.full(h.size, np.nan)
        self.assertEqual(len(homogeneidad.tramos_homogeneos(h, r.astype(np.float32).astype(np.float64), "T", U)), 2)
        # HOM-11: δ = NaN en todos los tramos cuando H*_δ queda vacío (D40); se simula esa salida de homogeneidad.
        with mock.patch.object(homogeneidad, "desplazamientos", return_value={0: NAN, 1: NAN}):
            df, tr = candidatos.residuos_estacion("330000", h, {"T": r, "Td": vacio, "u": vacio, "v": vacio,
                                                                "p": vacio}, U)
        tipos.validar_esquema(df, tipos.ESQUEMA_RESIDUOS, nombre="residuos")
        tipos.validar_esquema(tr, tipos.ESQUEMA_TRAMOS_HOMOGENEOS, nombre="tramos")
        self.assertEqual(len(tr), 2)
        self.assertTrue(tr["delta"].isna().all())
        self.assertTrue(df["rt_T"].isna().all())
        self.assertTrue(df["observada"].all())
        # Una serie limpia cada 3 h: las horas intermedias son filas «interpolable».
        h3 = h[h % 3 == 0]
        df3, _ = candidatos.residuos_estacion("330001", h3, {"T": np.sin(h3 / 9.0), "Td": vacio[:h3.size],
                                                              "u": vacio[:h3.size], "v": vacio[:h3.size],
                                                              "p": vacio[:h3.size]}, U)
        nuevas = df3[~df3["observada"]]
        self.assertTrue(nuevas["interpolable"].all() and nuevas["r_T"].isna().all())
        self.assertEqual(len(df3), h3.size + 2 * (h3.size - 1))
        infos = _red(2, 0.1, par=False)
        datos = tipos.DatosCompetencia(residuos={"330000": df, "330001": df3}, climatologias=tipos.tabla_vacia(
            tipos.ESQUEMA_CLIMA_A), tramos=tr, filas_c={}, estaticos=_estaticos(infos), estaciones=infos, pliegues=(),
            puntos_e5l={}, clima_estado={})
        hb, vb = candidatos._serie(datos, "330000", "b", "T", U)
        self.assertTrue(np.isnan(vb).all())
        hb3, vb3 = candidatos._serie(datos, "330001", "b", "T", U)
        self.assertEqual(hb3.size, len(df3))
        np.testing.assert_allclose(vb3[1], (2 * np.sin(h3[0] / 9.0) + np.sin(h3[1] / 9.0)) / 3, rtol=1e-6)

    def test_diseno_c_columnas_tpi_truncado_d33_e_indicadoras_d22(self):
        """§4.6: 156 columnas; D22 (a): las indicadoras salen del ``macrozona_cod`` de la celda («sin_region» da
        todas 0); D33: el TPI truncado no entra a la media ni al desvío y vale 0 después (la fórmula de
        ``estaticas_nasadem.estandarizar_tpi``); el diseño estandarizado por la transformación lineal es el producto de
        los predictores base estandarizados (oráculo directo). Como en los reales (NAS-9: «Sin dato en la celda o en el
        disco, TPI es NaN (y el disco sin dato queda truncado)»), una celda trae los dos TPI NaN y truncados: su estación
        conserva sus filas de C y C_est, su TPI estandarizado vale 0 y su predicción es finita."""
        U = _umbrales()
        self.assertEqual(len(candidatos.COLUMNAS_C), 156)
        self.assertEqual(len(candidatos.BASES_C), 31)
        infos, h, verdad = _red_chica()
        sin_dato = "330010"                                   # truncada en tpi1 (k % 7 == 3); aquí, NaN en los dos
        datos = _datos(infos, h, {c: verdad[c]["r"] for c in infos}, estaticos=_estaticos(infos, tpi_nan=(sin_dato,)))
        ent = sorted(infos)
        est = datos.estaticos.set_index("celda")
        e_nan = est.loc[infos[sin_dato].celda]
        self.assertTrue(math.isnan(e_nan["tpi1"]) and math.isnan(e_nan["tpi5"]))
        self.assertTrue(bool(e_nan["tpi1_truncado"]) and bool(e_nan["tpi5_truncado"]))
        for cand in ("C", "C_est"):                           # D33: el TPI truncado NaN no le quita filas (CAN-11)
            s = datos.filas_c[cand]["T"].get(sin_dato)
            self.assertIsNotNone(s, cand)
            self.assertEqual(s.n_filas, U.a("C_FILAS"), cand)
            self.assertTrue(np.isfinite(s.xtx).all() and np.isfinite(s.xty).all(), cand)
        modelo = candidatos.ajustar_c(datos.filas_c["C"]["T"], ent, 1.0)
        # Media y desvío de cada TPI a mano, con los pesos de las filas y sin las celdas truncadas (D33).
        filas = datos.filas_c["C"]["T"]
        for tpi in candidatos.TPI_C:
            num = den = seg = 0.0
            for c in ent:
                if c not in filas:
                    continue
                e = est.loc[infos[c].celda]
                if e[candidatos.TRUNCADO_C[tpi]]:
                    continue
                peso = filas[c].peso * filas[c].n_filas
                num += peso * e[tpi]
                den += peso
                seg += peso * e[tpi] ** 2
            j = candidatos.BASES_C.index(tpi)
            self.assertAlmostEqual(modelo.media[j], num / den, places=9, msg=tpi)
            self.assertAlmostEqual(modelo.desvio[j], math.sqrt(seg / den - (num / den) ** 2), places=7, msg=tpi)
        i = candidatos.BASES_C.index("tpi1")
        truncada = next(c for c in ent if est.loc[infos[c].celda, "tpi1_truncado"])
        normal = next(c for c in ent if not est.loc[infos[c].celda, "tpi1_truncado"])
        self.assertNotEqual(truncada, sin_dato)
        hs = h[:30]
        for c in (truncada, normal, sin_dato):
            fila = datos.estaticos[datos.estaticos["celda"] == infos[c].celda]
            X = candidatos.diseno_estandarizado(candidatos.diseno_c(fila, hs, datos.puntos_e5l[c], U), modelo)
            self.assertEqual(X.shape, (hs.size, 156))
            columna_tpi = candidatos.COLUMNAS_C.index(("tpi1",))
            esperado = estaticas_nasadem.estandarizar_tpi(fila["tpi1"].to_numpy(), fila["tpi1_truncado"].to_numpy(),
                                                          modelo.media[i], modelo.desvio[i])
            np.testing.assert_allclose(X[:, columna_tpi], np.repeat(esperado, hs.size), rtol=1e-12, atol=1e-12)
            # Oráculo: cada columna es el producto de sus bases estandarizadas.
            B, trunc = candidatos._bases(candidatos._estaticos_validos(fila), hs,
                                         candidatos.estado_c(datos.puntos_e5l[c], hs))
            Z = np.where(modelo.desvio > 0, (B - modelo.media) / np.where(modelo.desvio > 0, modelo.desvio, 1), 0.0)
            for k, b in enumerate(candidatos.TPI_C):
                Z[:, candidatos.BASES_C.index(b)] = np.where(trunc[:, k], 0.0, Z[:, candidatos.BASES_C.index(b)])
            for j, factores in enumerate(candidatos.COLUMNAS_C):
                directo = np.ones(hs.size)
                for f in factores:
                    directo = directo * Z[:, candidatos.BASES_C.index(f)]
                np.testing.assert_allclose(X[:, j], directo, rtol=1e-9, atol=1e-9, err_msg=str(factores))
        # La celda sin dato: TPI estandarizado 0 en los dos radios, diseño y predicciones de C y C_est finitos.
        fila = datos.estaticos[datos.estaticos["celda"] == infos[sin_dato].celda]
        X = candidatos.diseno_estandarizado(candidatos.diseno_c(fila, h, datos.puntos_e5l[sin_dato], U), modelo)
        self.assertTrue(np.isfinite(X).all())
        for tpi in candidatos.TPI_C:
            self.assertTrue(np.all(X[:, candidatos.COLUMNAS_C.index((tpi,))] == 0.0), tpi)
        self.assertTrue(np.isfinite(candidatos.predecir_c(modelo, fila, h, datos.puntos_e5l[sin_dato])).all())
        m_est = candidatos.ajustar_c(datos.filas_c["C_est"]["T"], ent, 1.0)
        self.assertTrue(np.isfinite(candidatos.predecir_c(m_est, fila, h, datos.clima_estado[sin_dato])).all())
        externo = _pliegue_de(datos, "P1", sin_dato)
        for cand, uso in ((Candidato.C, Uso.AGUDO), (Candidato.C_EST, Uso.CRONICO)):
            with self.subTest(candidato=cand.value):
                g = _prediccion(cand, "T", uso, 1.0, externo, datos)
                g = g[g["codigo"] == sin_dato]
                self.assertEqual(len(g), h.size)
                self.assertTrue(np.isfinite(g["correccion"].to_numpy()).all() and g["soporte"].all())
        # D22 (a): indicadoras desde macrozona_cod; «sin_region» (5) da todas 0.
        fila = datos.estaticos.iloc[[0]].copy()
        B, _ = candidatos._bases(candidatos._estaticos_validos(fila), hs[:1], candidatos.estado_c(datos.puntos_e5l[ent[0]], hs[:1]))
        mz = [candidatos.BASES_C.index(m) for m in candidatos.MACRO_C]
        self.assertEqual(B[0, mz].tolist(), [0.0, 0.0, 1.0, 0.0, 0.0])
        fila["macrozona_cod"] = np.int8(tipos.MACROZONA_COD[tipos.MACROZONA_SIN_REGION])
        B, _ = candidatos._bases(candidatos._estaticos_validos(fila), hs[:1], candidatos.estado_c(datos.puntos_e5l[ent[0]], hs[:1]))
        self.assertEqual(B[0, mz].tolist(), [0.0] * 5)
        sin_z = datos.estaticos.drop(columns=[candidatos.COLUMNA_Z_E5L])
        with self.assertRaises(candidatos.ErrorCandidatos):            # PED-2
            candidatos.diseno_c(sin_z.iloc[[0]], hs, datos.puntos_e5l[ent[0]], U)

    def test_armonicos_de_tiempo_de_c_segun_el_texto(self):
        """§4.6, oráculo independiente de ``_bases``: «seno y coseno de 2πh/24 y de 4πh/24 (h = hora UTC), y de
        2π·doy/365,25 y de 4π·doy/365,25», con doy el día del año de la fecha UTC (1…366, CAN-9) que da el calendario de
        Python."""
        fechas = ("2011-01-01T00", "2012-12-31T23", "2011-12-31T12", "2012-02-29T05", "2012-03-01T17")
        h = np.array([_h(f) for f in fechas], dtype=np.int64)
        momentos = [datetime.strptime(f, "%Y-%m-%dT%H") for f in fechas]
        doy = np.array([m.timetuple().tm_yday for m in momentos], dtype=np.float64)
        hora = np.array([m.hour for m in momentos], dtype=np.float64)
        self.assertEqual(doy.tolist(), [1, 366, 365, 60, 61])
        self.assertEqual(hora.tolist(), [0, 23, 12, 5, 17])
        np.testing.assert_array_equal(candidatos._dia_del_anio(h), doy)
        esperado = {"sen_h1": np.sin(2 * np.pi * hora / 24), "cos_h1": np.cos(2 * np.pi * hora / 24),
                    "sen_h2": np.sin(4 * np.pi * hora / 24), "cos_h2": np.cos(4 * np.pi * hora / 24),
                    "sen_a1": np.sin(2 * np.pi * doy / 365.25), "cos_a1": np.cos(2 * np.pi * doy / 365.25),
                    "sen_a2": np.sin(4 * np.pi * doy / 365.25), "cos_a2": np.cos(4 * np.pi * doy / 365.25)}
        self.assertEqual(set(candidatos.HORARIOS_C) | set(candidatos.ANUALES_C), set(esperado))
        infos = _red(2, 0.2, par=False)
        fila = candidatos._estaticos_validos(_estaticos(infos).iloc[[0]])
        estado = {v: np.zeros(h.size) for v in candidatos.ESTADO_C}
        B, _ = candidatos._bases(fila, h, estado)
        for nombre, x in esperado.items():
            np.testing.assert_allclose(B[:, candidatos.BASES_C.index(nombre)], x, rtol=0, atol=1e-12, err_msg=nombre)

    def test_soporte_de_ab_si_a_o_phi_prima_lo_tienen(self):
        """CAN-15 («AB si A o Φ′ lo tienen»; §4.2, §5.3): la única vecina de entrenamiento de la estación de prueba
        tiene δ NaN (D40: r̃ y a NaN), pero su r es válido y entra en A (MC-65). En la estación de prueba A y AB tienen
        soporte y B no (Φ′ tampoco), y AB vale A (Φ′ = 0; §4.5: «Lejos de las estaciones vuelve a A»)."""
        U = _umbrales()
        h = _horas("2010-01-01T00", "2014-01-01T00")
        infos = _completar({"330000": _info("330000", -33.40, -70.60, 500.0, 1000),
                            "330001": _info("330001", -33.40 - 5.0 / 111.2, -70.60, 520.0, 1001)})
        self.assertNotEqual(infos["330000"].grupo, infos["330001"].grupo)
        vacio = np.full(h.size, np.nan)
        meses = homogeneidad.mes2000(h)
        con_quiebre = np.where(meses >= int(meses[0]) + 24, 1.0, 0.0) + 0.1 * np.sin(h / 7.0)    # dos tramos en T
        residuos, tramos = {}, []
        with mock.patch.object(homogeneidad, "desplazamientos",                       # HOM-11: H*_δ vacío (D40)
                               side_effect=lambda hh, r, lista, umbrales: {k: NAN for k in range(len(lista))}):
            residuos["330000"], tr = candidatos.residuos_estacion(
                "330000", h, {"T": con_quiebre, "Td": vacio, "u": vacio, "v": vacio, "p": vacio}, U)
        tramos.append(tr)
        residuos["330001"], tr = candidatos.residuos_estacion(
            "330001", h, {"T": 0.3 * np.cos(h / 11.0), "Td": vacio, "u": vacio, "v": vacio, "p": vacio}, U)
        tramos.append(tr)
        self.assertEqual(len(tramos[0]), 2)
        self.assertTrue(tramos[0]["delta"].isna().all() and residuos["330000"]["rt_T"].isna().all())
        clima = candidatos.climatologias_a(residuos, U)
        self.assertTrue(clima[(clima["codigo"] == "330000") & (clima["variable"] == "T")]["califica"].all())
        datos = tipos.DatosCompetencia(residuos=residuos, climatologias=clima, tramos=pd.concat(tramos, ignore_index=True),
                                       filas_c={}, estaticos=_estaticos(infos), estaciones=infos, pliegues=(),
                                       puntos_e5l={}, clima_estado={})
        externo = tipos.Pliegue("soporte_ab", tipos.Particion.P1, ("330001",), ("330000",))
        hiper_a, hiper_q = Hiper(10.0, 0.0, 0.05), Hiper(10.0, 0.0, 0.2)
        pa = _prediccion(Candidato.A, "T", Uso.AGUDO, hiper_a, externo, datos)
        pb = _prediccion(Candidato.B, "T", Uso.AGUDO, hiper_q, externo, datos)
        pab = _prediccion(Candidato.AB, "T", Uso.AGUDO, (hiper_a, hiper_q), externo, datos)
        for p in (pa, pb, pab):
            self.assertEqual(len(p), h.size)
        self.assertTrue(pa["soporte"].all() and (pa["correccion"] != 0.0).any())
        self.assertFalse(pb["soporte"].any())
        self.assertTrue((pb["correccion"] == 0.0).all())
        self.assertTrue(pab["soporte"].all())
        np.testing.assert_array_equal(pab["correccion"].to_numpy(), pa["correccion"].to_numpy())

    def _exigir_error_de_insumo(self, incompleto, codigo: str, con_error, sin_error):
        """Con un insumo de C o C_est que falta para ``codigo`` (que entra y tiene celda), la predicción con ``codigo``
        de prueba y la selección con ``codigo`` de prueba interna dan ``ErrorCandidatos`` en los candidatos de
        ``con_error``, y los de ``sin_error`` (que no usan ese insumo) siguen."""
        externo = _pliegue_de(incompleto, "P1", codigo)
        otro = next(p for p in incompleto.pliegues if p.particion.value == "P1" and codigo in p.entrenamiento)
        for cand in con_error:
            uso = Uso.CRONICO if cand is Candidato.C_EST else Uso.AGUDO
            with self.subTest(candidato=cand.value):
                with self.assertRaisesRegex(candidatos.ErrorCandidatos, codigo):
                    _prediccion(cand, "T", uso, 1.0, externo, incompleto)
                with self.assertRaisesRegex(candidatos.ErrorCandidatos, codigo):
                    _seleccionar(cand, "T", uso, otro, incompleto)
        for cand in sin_error:
            uso = Uso.CRONICO if cand is Candidato.C_EST else Uso.AGUDO
            with self.subTest(candidato=cand.value):
                g = _prediccion(cand, "T", uso, 1.0, externo, incompleto)
                self.assertTrue(np.isfinite(g[g["codigo"] == codigo]["correccion"].to_numpy()).all())

    def test_celda_ausente_de_los_estaticos_es_error_y_no_d34(self):
        """CAN-13 y CAN-16: D34 cubre sólo la estación que entra sin celda («fuera de la grilla»). Si la que entra con
        celda no tiene su celda en los estáticos (§4.6: «Los estáticos de una estación son los de su celda»), es un
        insumo incompleto: ``ErrorCandidatos`` en las filas de C y C_est, en la selección y en la predicción, en vez de
        quedar fuera de C «sin soporte»."""
        U = _umbrales()
        infos, _, _ = _red_chica()
        datos = _datos_chica()
        codigo = "330005"
        self.assertFalse(candidatos._fuera_de_la_grilla(infos[codigo]))
        sin_celda = datos.estaticos[datos.estaticos["celda"] != infos[codigo].celda]
        self.assertEqual(len(sin_celda), len(datos.estaticos) - 1)
        for climatologico, estados in ((False, datos.puntos_e5l), (True, datos.clima_estado)):
            with self.subTest(climatologico=climatologico), self.assertRaisesRegex(candidatos.ErrorCandidatos, codigo):
                candidatos.filas_c(datos.residuos, sin_celda, estados, U, infos=infos, climatologico=climatologico)
        self._exigir_error_de_insumo(dataclasses.replace(datos, estaticos=sin_celda), codigo,
                                     (Candidato.C, Candidato.C_EST), ())

    def test_sin_fondo_en_la_estacion_es_error_en_c(self):
        """CAN-13 y A14: a una estación que entra con celda le falta su fondo en ``puntos_e5l``: C da
        ``ErrorCandidatos`` (en las filas, la selección y la predicción), no 17.544 horas NaN; C_est, que usa el clima,
        sigue."""
        U = _umbrales()
        infos, _, _ = _red_chica()
        datos = _datos_chica()
        codigo = "330005"
        sin = {c: v for c, v in datos.puntos_e5l.items() if c != codigo}
        with self.assertRaisesRegex(candidatos.ErrorCandidatos, codigo):
            candidatos.filas_c(datos.residuos, datos.estaticos, sin, U, infos=infos)
        self._exigir_error_de_insumo(dataclasses.replace(datos, puntos_e5l=sin), codigo, (Candidato.C,),
                                     (Candidato.C_EST,))

    def test_sin_clima_del_estado_es_error_en_c_est(self):
        """CAN-13, A14 y D29: a una estación que entra con celda le falta su clima en ``clima_estado``: C_est da
        ``ErrorCandidatos`` (en las filas, la selección y la predicción); C, que usa el fondo horario, sigue."""
        U = _umbrales()
        infos, _, _ = _red_chica()
        datos = _datos_chica()
        codigo = "330005"
        sin = {c: v for c, v in datos.clima_estado.items() if c != codigo}
        with self.assertRaisesRegex(candidatos.ErrorCandidatos, codigo):
            candidatos.filas_c(datos.residuos, datos.estaticos, sin, U, infos=infos, climatologico=True)
        self._exigir_error_de_insumo(dataclasses.replace(datos, clima_estado=sin), codigo, (Candidato.C_EST,),
                                     (Candidato.C,))

    def test_ajuste_por_sumas_igual_al_directo_mc45(self):
        """MC-45: el ajuste desde las sumas por estación es el ridge ponderado directo sobre las filas apiladas, con
        la estandarización del entrenamiento y la constante sin penalizar (CAN-11, CAN-12)."""
        infos, h, verdad = _red_chica()
        datos = _datos(infos, h, {c: verdad[c]["r"] for c in infos})
        ent = sorted(infos)[:10]
        modelo = candidatos.ajustar_c(datos.filas_c["C"]["T"], ent, 10.0)
        Xs, ys, ws = [], [], []
        for c in ent:
            s = datos.filas_c["C"]["T"].get(c)
            if s is None:
                continue
            fila = datos.estaticos[datos.estaticos["celda"] == infos[c].celda]
            Xs.append(candidatos.diseno_estandarizado(candidatos.diseno_c(fila, s.horas, datos.puntos_e5l[c]), modelo))
            df = datos.residuos[c]
            ys.append(df.set_index("h").loc[s.horas, "r_T"].to_numpy(np.float64))
            ws.append(np.full(s.horas.size, s.peso))
        X, y, w = np.vstack(Xs), np.concatenate(ys), np.concatenate(ws)
        D = np.eye(X.shape[1])
        D[0, 0] = 0.0
        directo = np.linalg.solve(np.matmul(X.T * w, X) + 10.0 * D, np.matmul(X.T * w, y))
        np.testing.assert_allclose(modelo.coef, directo, rtol=1e-6, atol=1e-8)

    def test_estacion_fuera_de_la_grilla_d34(self):
        """D34: una estación que entra sin celda no aporta filas a C ni a C_est y su predicción de C es NaN (sin
        soporte), pero entrena A, B y AB: está en la lista de vecinos."""
        U = _umbrales()
        infos = _red(4, 0.22, fuera_de_grilla=("330005",))
        h = _horas("2011-01-01T00", "2013-01-01T00")
        verdad = _verdad(infos, h)
        datos = _datos(infos, h, {c: verdad[c]["r"] for c in infos})
        self.assertNotIn("330005", datos.filas_c["C"]["T"])
        self.assertNotIn("330005", datos.filas_c["C_est"]["T"])
        externo = _pliegue_de(datos, "P1", "330005")
        pred = _prediccion(Candidato.C, "T", Uso.AGUDO, 1.0, externo, datos)
        g = pred[pred["codigo"] == "330005"]
        self.assertTrue(len(g) and g["correccion"].isna().all() and not g["soporte"].any())
        otro = next(p for p in datos.pliegues if p.particion.value == "P1" and "330005" in p.entrenamiento)
        prueba = otro.prueba[0]
        vec = candidatos.vecinos(candidatos.puntos_de_estaciones(infos, [prueba]),
                                 {c: infos[c] for c in otro.entrenamiento}, Hiper(100.0, 0.0, 0.05), U)
        self.assertIn(vec.codigos.index("330005"), vec.est[0])
        # En la selección, tampoco entra al objetivo de ningún candidato (CAN-14).
        vistos = set()

        def registrar(internos, sumas, *, candidato, variable, uso):
            vistos.update(c for por in sumas.values() for c in por)
            return _objetivo(internos, sumas, candidato=candidato, variable=variable, uso=uso)
        produccion = tipos.Pliegue("produccion", tipos.Particion.P2, (), tuple(sorted(infos)))
        for cand in (Candidato.A, Candidato.B):
            candidatos.seleccionar(cand, "T", Uso.AGUDO, produccion, datos, U, objetivo=registrar, recorte=False)
        self.assertNotIn("330005", vistos)
        self.assertGreater(len(vistos), 10)
        # Paridad con el predicado de estaticas_nasadem (NAS-17), mientras no esté en tipos (PED-1).
        for c, info in infos.items():
            self.assertEqual(candidatos._fuera_de_la_grilla(info), estaticas_nasadem.fuera_de_la_grilla(info), c)

    def test_matriz_q_y_fuera_de_rango_c(self):
        """``matriz_q`` da el q de B (r̃) y de Φ′ (a) en las horas pedidas, con las interpoladas; ``fuera_de_rango_c``
        marca las celdas con algún estático fuera del rango del entrenamiento (§4.6, CAN-17), sin contar el TPI
        truncado."""
        U = _umbrales()
        infos, h, verdad = _red_chica()
        datos = _datos(infos, h, {c: verdad[c]["r"] for c in infos}, patrones={"330001": "trihoraria"})
        horas = np.r_[h[:10], h[::997][1:20]]                          # enero y horas de todos los meses
        _, meses, _ = candidatos._mes_y_hora(horas)
        self.assertEqual(len(set(meses.tolist())), 12)
        qb = candidatos.matriz_q(datos, ["330001", "330002"], Candidato.B, "T", horas, U)
        df = datos.residuos["330001"]
        self.assertEqual(qb[0, 0], np.float64(df["rt_T"].iloc[0]))
        self.assertTrue(np.isfinite(qb[:10, 0]).all())               # las horas entre reportes trihorarios
        qa = candidatos.matriz_q(datos, ["330002"], Candidato.AB, "T", horas, U)
        rbar = candidatos._rbar_estacion(datos, "330002", "T")
        _, mes, hora = candidatos._mes_y_hora(horas)
        qb2 = candidatos.matriz_q(datos, ["330002"], "B", "T", horas, U)[:, 0]
        np.testing.assert_allclose(qa[:, 0], qb2 - rbar[mes - 1, hora])
        with self.assertRaises(candidatos.ErrorCandidatos):
            candidatos.matriz_q(datos, ["330002"], Candidato.A, "T", horas, U)
        ent = datos.estaticos.iloc[:10]
        celdas = datos.estaticos.iloc[10:].copy()
        self.assertEqual(candidatos.fuera_de_rango_c(ent.iloc[:5], ent.iloc[:5]).tolist(), [False] * 5)
        celdas.loc[celdas.index[0], "z_media"] = ent["z_media"].max() + 500.0
        celdas.loc[celdas.index[1], "tpi1"] = 1e6
        celdas.loc[celdas.index[1], "tpi1_truncado"] = True              # truncado: no cuenta
        celdas.loc[celdas.index[1], "z_media"] = float(ent["z_media"].median())
        fuera = candidatos.fuera_de_rango_c(celdas, ent)
        self.assertTrue(fuera[0])
        self.assertEqual(len(fuera), len(celdas))
        uno = celdas.iloc[[1]].copy()
        for col in candidatos.ESTATICOS_C:                               # todo dentro, salvo el TPI truncado
            if col in ("z_km", "dz_km"):
                continue
            if col in uno.columns:
                uno[col] = float(ent[col].median()) if col != "tpi1" else 1e6
        uno["z_e5l"] = uno["z_media"] - float((ent["z_media"] - ent["z_e5l"]).median())
        uno["tpi5"] = float(ent["tpi5"].median())
        self.assertEqual(candidatos.fuera_de_rango_c(uno, ent).tolist(), [False])

    def test_objetivo_solo_en_los_dias_de_seleccion(self):
        """§4.9, «Días: los de (días desde el 2000-01-01) mód 11 = 3» (MC-44; hallazgo mayor del crítico de la ola 3):
        dentro de la selección, el objetivo ve sólo las horas de los días de selección. Con un objetivo que registra
        las sumas {pliegue interno: {código: (sse, n)}}, cada n de cada estación de prueba interna es el número de sus
        horas observadas con residuo válido y (h // 24) mód 11 = 3, o mód 23 = 3 con el recorte, contado aquí con los
        valores del Anexo A escritos a mano, en A, B, AB, C y C_est; una estación es trihoraria, para que el conteo no
        sea el mismo en todas, y dos estaciones no tienen residuo en la mitad de los días de selección (los pares de
        mód 11 = 3 en una, los impares de mód 23 = 3 en otra), para que el conteo dependa de qué días son. Aceptar todos
        los días, ninguno, otro resto u otro módulo hace fallar la prueba."""
        U = _umbrales()
        infos, h, verdad = _red_chica()
        dias = h // 24
        mod, resto, mod_r = (VALORES_ANEXO_A[k] for k in ("SEL_MOD", "SEL_RESTO", "SEL_MOD_RECORTE"))
        residuos = {c: verdad[c]["r"].copy() for c in infos}
        residuos["330001"][(dias % mod == resto) & (dias % 2 == 0)] = NAN
        residuos["330003"][(dias % mod_r == resto) & (dias % 2 == 1)] = NAN
        datos = _datos(infos, h, residuos, patrones={"330001": "trihoraria"})
        externo = _pliegue_de(datos, "P1", "330005")
        observada = {c: _patron(h, "trihoraria" if c == "330001" else "horaria") & np.isfinite(residuos[c])
                     for c in infos}
        for recorte, modulo in ((False, mod), (True, mod_r)):
            seleccion = dias % modulo == resto
            esperado = {c: int((observada[c] & seleccion).sum()) for c in infos}
            self.assertTrue(0 < esperado["330000"] * (modulo - 1) < len(h))      # ≈ 1/módulo de las horas
            self.assertTrue(0 < esperado["330001"] < esperado["330000"])
            for cand, uso in ((Candidato.A, Uso.AGUDO), (Candidato.B, Uso.AGUDO), (Candidato.AB, Uso.AGUDO),
                              (Candidato.C, Uso.AGUDO), (Candidato.C_EST, Uso.CRONICO)):
                vistos = []

                def registrar(internos, sumas, *, candidato, variable, uso):
                    vistos.append((candidato, {p: dict(por) for p, por in sumas.items()}))
                    return _objetivo(internos, sumas, candidato=candidato, variable=variable, uso=uso)
                with self.subTest(recorte=recorte, candidato=cand.value):
                    candidatos.seleccionar(cand, "T", uso, externo, datos, U, objetivo=registrar, recorte=recorte)
                    internos = {p.id: p for p in particiones.pliegues_internos(externo, infos,
                                                                               candidatos._grupos(infos), U)}
                    self.assertTrue(vistos and {c for c, _ in vistos} <= {cand, Candidato.A})
                    for _, sumas in vistos:
                        self.assertEqual(set(sumas), set(internos))
                        for pid, por in sumas.items():
                            self.assertEqual(set(por), set(internos[pid].prueba), pid)
                            self.assertEqual({c: n for c, (_, n) in por.items()},
                                             {c: esperado[c] for c in por}, pid)
                    for c in ("330001", "330003"):
                        self.assertTrue(any(c in por for _, s in vistos for por in s.values()), c)

    def test_seleccion_desempate_y_sin_objetivo(self):
        """CAN-14 y CAN-16: con un objetivo constante gana el primero en el orden del texto (L, λ, κ) y α; sin ningún
        objetivo finito, ``SinSeleccion``."""
        infos, h, verdad = _red_chica()
        datos = _datos(infos, h, {c: verdad[c]["r"] for c in infos})
        externo = _pliegue_de(datos, "P2", "330000")
        U = _umbrales()

        def constante(*a, **kw):
            return 1.0
        self.assertEqual(candidatos.seleccionar(Candidato.B, "T", Uso.AGUDO, externo, datos, U, objetivo=constante,
                                                recorte=False), Hiper(10.0, 0.0, 0.05))
        self.assertEqual(candidatos.seleccionar(Candidato.C, "T", Uso.AGUDO, externo, datos, U, objetivo=constante,
                                                recorte=True), 0.1)
        with self.assertRaises(candidatos.SinSeleccion):
            candidatos.seleccionar(Candidato.A, "T", Uso.AGUDO, externo, datos, U, objetivo=lambda *a, **k: NAN,
                                   recorte=False)
        ab = _seleccionar(Candidato.AB, "T", Uso.AGUDO, externo, datos)
        self.assertEqual(ab[0], _seleccionar(Candidato.A, "T", Uso.AGUDO, externo, datos))


# ---------------------------------------------------------------------------
# CAN-18 (ola 4): el diseño de C vectorizado no cambia ningún bit
# ---------------------------------------------------------------------------
class PruebasCan18(unittest.TestCase):
    """CAN-18: con las indicadoras de macrozona una vez por código y el diseño en bruto por bloques, el diseño, la
    predicción, las filas, el ajuste, la predicción de prueba y la selección de C y C_est tienen los mismos bits que con
    la copia literal de la ola 3 (``_bases_ola3``, ``_diseno_bruto_ola3``), y los errores son los mismos."""

    def assertMismaSalida(self, nueva, referencia, msg=None):
        self.assertEqual(nueva[0], referencia[0], msg)
        if nueva[0] == "error":
            self.assertEqual(nueva, referencia, msg)
            return
        valores = nueva[1] if isinstance(nueva[1], tuple) else (nueva[1],)
        esperados = referencia[1] if isinstance(referencia[1], tuple) else (referencia[1],)
        self.assertEqual([_bits(x) for x in valores], [_bits(x) for x in esperados], msg)

    def test_can18_diseno_y_prediccion_bit_a_bit(self):
        """Celdas × horas como en ``producto`` (más de un bloque, con NaN e infinitos), con bloques de varios tamaños;
        una fila que se repite, con el fondo de C y con el clima de C_est; y sin horas."""
        with np.errstate(invalid="ignore"):               # inf·0 del estado infinito: NaN, como en la ola 3
            self._diseno_y_prediccion()

    def _diseno_y_prediccion(self):
        infos, est, h, filas, horas, estado, modelo = _caso_can18()
        self.assertGreater(horas.size, candidatos._BLOQUE_FILAS)
        self.assertEqual(sorted(set(_MZ_CAN18)), sorted(tipos.MACROZONA_COD.values()))
        validos = candidatos._estaticos_validos(filas)
        B_ref, t_ref = _bases_ola3(validos, horas, estado)
        self.assertMismaSalida(("ok", candidatos._bases(validos, horas, estado)), ("ok", (B_ref, t_ref)))
        X_ref = _diseno_bruto_ola3(B_ref, t_ref)
        self.assertTrue(np.isnan(X_ref).any() and np.isinf(X_ref).any())
        R_ref = np.matmul(candidatos.diseno_estandarizado(X_ref, modelo), modelo.coef)
        for bloque in (candidatos._BLOQUE_FILAS, 7, 1000, horas.size):
            with self.subTest(bloque=bloque), mock.patch.object(candidatos, "_BLOQUE_FILAS", bloque):
                self.assertEqual(_bits(candidatos.diseno_c(filas, horas, estado)), _bits(X_ref))
                self.assertEqual(_bits(candidatos.predecir_c(modelo, filas, horas, estado)), _bits(R_ref))
        puntos, clima = _fondo(infos, h)
        m_est = dataclasses.replace(modelo, diseno=tipos.DisenoC.CLIMATOLOGICO)
        for k in (0, 2, 4, 7):                          # centro, insular, sin_region con TPI NaN, fracción NaN
            fila, codigo = est.iloc[[k]], sorted(infos)[k]
            for m, estado_k, est_ref in ((modelo, puntos[codigo], candidatos.estado_c(puntos[codigo], h)),
                                         (m_est, clima[codigo], candidatos.estado_c_est(clima[codigo], h))):
                with self.subTest(celda=k, diseno=m.diseno.value):
                    clim = m.diseno is tipos.DisenoC.CLIMATOLOGICO
                    X_k = _diseno_bruto_ola3(*_bases_ola3(candidatos._estaticos_validos(fila), h, est_ref))
                    self.assertEqual(_bits(candidatos.diseno_c(fila, h, estado_k, climatologico=clim)), _bits(X_k))
                    self.assertEqual(_bits(candidatos.predecir_c(m, fila, h, estado_k)),
                                     _bits(np.matmul(candidatos.diseno_estandarizado(X_k, m), m.coef)))
        vacio = np.empty(0, dtype=np.int64)
        estado_vacio = {v: np.empty(0) for v in ESTADO_C}
        for nombre, df in (("una fila", est.iloc[[1]]), ("sin filas", est.iloc[[]])):
            with self.subTest(sin_horas=nombre):
                self.assertMismaSalida(_resultado(candidatos.diseno_c, df, vacio, estado_vacio),
                                       _resultado(lambda: _diseno_bruto_ola3(*_bases_ola3(df, vacio, estado_vacio))))

    def test_can18_filas_ajuste_prediccion_y_seleccion_bit_a_bit(self):
        """Las salidas públicas sobre la red chica con macrozonas variadas: ``filas_c`` (C y C_est), ``ajustar_c``,
        ``predecir_prueba`` y ``seleccionar``, iguales bit a bit con ``_bases`` y ``_diseno_bruto`` de la ola 3."""
        infos, h, verdad = _red_chica()
        est = _estaticos(infos)
        est["macrozona_cod"] = np.array([_MZ_CAN18[k % len(_MZ_CAN18)] for k in range(len(est))], dtype=np.int8)
        residuos = {c: verdad[c]["r"] for c in infos}
        usos = ((Candidato.C, Uso.AGUDO), (Candidato.C_EST, Uso.CRONICO))

        def salidas():
            datos = _datos(infos, h, residuos, estaticos=est)
            externo = _pliegue_de(datos, "P1", "330001")
            modelos = {c.value: candidatos.ajustar_c(datos.filas_c[c.value]["T"], externo.entrenamiento, 1.0)
                       for c, _ in usos}
            prueba = {c.value: _prediccion(c, "T", u, 1.0, externo, datos) for c, u in usos}
            seleccion = {c.value: _seleccionar(c, "T", u, externo, datos) for c, u in usos}
            return datos.filas_c, modelos, prueba, seleccion

        filas, modelos, prueba, seleccion = salidas()
        with _como_ola3():
            filas_ref, modelos_ref, prueba_ref, seleccion_ref = salidas()
        for cand in ("C", "C_est"):
            for v in candidatos.VARIABLES:
                self.assertEqual(sorted(filas[cand][v]), sorted(filas_ref[cand][v]), (cand, v))
                for c, s in filas[cand][v].items():
                    r = filas_ref[cand][v][c]
                    self.assertEqual((s.codigo, s.variable, s.diseno, s.n_filas, s.peso),
                                     (r.codigo, r.variable, r.diseno, r.n_filas, r.peso), (cand, v, c))
                    self.assertEqual([_bits(x) for x in (s.xtx, s.xty, s.yty, s.horas)],
                                     [_bits(x) for x in (r.xtx, r.xty, r.yty, r.horas)], (cand, v, c))
            self.assertTrue(filas[cand]["T"], cand)
            m, r = modelos[cand], modelos_ref[cand]
            self.assertEqual([_bits(x) for x in (m.coef, m.media, m.desvio)] + [m.alfa, m.diseno],
                             [_bits(x) for x in (r.coef, r.media, r.desvio)] + [r.alfa, r.diseno], cand)
            p, q = prueba[cand], prueba_ref[cand]
            self.assertTrue(len(p) and p["soporte"].any(), cand)
            self.assertEqual(list(p.columns), list(q.columns), cand)
            self.assertEqual(p["codigo"].tolist(), q["codigo"].tolist(), cand)
            self.assertEqual([_bits(p[k].to_numpy()) for k in ("h", "correccion", "soporte")],
                             [_bits(q[k].to_numpy()) for k in ("h", "correccion", "soporte")], cand)
        self.assertEqual(seleccion, seleccion_ref)

    def test_can18_macrozona_desconocida_mismo_error_y_una_llamada_por_codigo(self):
        """``tipos.indicadoras_macrozona`` se llama una vez por código distinto, en el orden en que aparecen; un código
        desconocido da el mismo error que fila a fila (el de la primera fila que falla, no el del menor código), y un
        ``macrozona_cod`` que no es entero de numpy sigue fila a fila, con lo mismo que en la ola 3."""
        _, est, h, filas, horas, estado, modelo = _caso_can18()
        validos = candidatos._estaticos_validos(filas)
        with mock.patch.object(tipos, "indicadoras_macrozona", wraps=tipos.indicadoras_macrozona) as espia:
            candidatos._bases(validos, horas, estado)
        self.assertEqual([llamada.args for llamada in espia.call_args_list], [(m,) for m in dict.fromkeys(_MZ_CAN18)])
        self.assertTrue(all(type(llamada.args[0]) is int for llamada in espia.call_args_list))
        hs = h[:5]
        estado_5 = {v: np.zeros(hs.size) for v in ESTADO_C}
        base = est.iloc[[0] * hs.size].reset_index(drop=True)
        casos = {"desconocido_tras_uno_menor": np.array([2, 9, 7, 5, 9], dtype=np.int8),
                 "negativo": np.array([-1, 2, 2, 2, 2], dtype=np.int8),
                 "int64_fuera_de_rango": np.array([0, 1, 2 ** 40, 3, 4], dtype=np.int64),
                 "uint8_validos": np.array([4, 3, 2, 1, 0], dtype=np.uint8),
                 "flotante_con_nan": np.array([2.0, NAN, 1.0, 9.0, 2.0]),
                 "flotante_no_entero": np.array([2.0, 2.5, 1.0, 1.0, 2.0]),    # hoy int() lo trunca (ola 3)
                 "objeto_con_none": np.array([2, None, 1, 1, 2], dtype=object),
                 "entero_con_na": pd.array([2, pd.NA, 1, 1, 2], dtype="Int8")}
        errores = {}
        for nombre, cod in casos.items():
            with self.subTest(caso=nombre):
                df = base.copy()
                df["macrozona_cod"] = cod
                nueva = _resultado(candidatos._bases, df, hs, estado_5)
                self.assertMismaSalida(nueva, _resultado(_bases_ola3, df, hs, estado_5))
                publica = _resultado(candidatos.predecir_c, modelo, df, hs, estado_5)
                with _como_ola3():
                    self.assertMismaSalida(publica, _resultado(candidatos.predecir_c, modelo, df, hs, estado_5))
                errores[nombre] = nueva[1] if nueva[0] == "error" else None
        self.assertIs(errores["desconocido_tras_uno_menor"], ValueError)
        self.assertIs(errores["uint8_validos"], None)
        df = base.copy()
        df["macrozona_cod"] = casos["desconocido_tras_uno_menor"]
        self.assertIn("macrozona_cod 9 ", _resultado(candidatos.diseno_c, df, hs, estado_5)[2])


# ---------------------------------------------------------------------------
# CAN-19 (ola 6): copia literal de las funciones de la ola 4 que cambiaron (la caché de series que crecía con las horas,
# la búsqueda en la serie armada, el objetivo, ``_sse_c`` con todos los diseños vivos y ``sumas_nucleo`` de una vez).
# Es el oráculo de la paridad bit a bit y no se toca. Sólo se cambian los nombres (sufijo «_ola4») y se toman de
# ``candidatos`` los ayudantes que no cambiaron.
# ---------------------------------------------------------------------------
def _sumas_nucleo_ola4(vec, q, disponible) -> tuple[np.ndarray, np.ndarray]:
    """Σ k·w·q y Σ k·w (hora × punto), con w los pesos de grupo (CAN-2, CAN-3). ``q`` y ``disponible`` son
    hora × estación de entrenamiento (en el orden de ``vec.codigos``)."""
    candidatos._comprobar_vecinos(vec)
    n_t, n_p = len(vec.codigos), vec.est.shape[0]
    q = np.asarray(q, dtype=np.float64)
    disponible = np.asarray(disponible)
    if q.ndim != 2 or q.shape[1] != n_t or disponible.shape != q.shape:
        raise ErrorCandidatos(f"q y disponible deben ser hora × {n_t} estaciones de entrenamiento")
    if disponible.dtype != bool:
        raise ErrorCandidatos("disponible debe ser booleano")
    if n_t == 0 or q.shape[0] == 0:
        ceros = np.zeros((q.shape[0], n_p))
        return ceros, ceros.copy()
    ok = disponible & np.isfinite(q)
    w = candidatos._pesos_grupo(ok, vec.grupo_est, len(vec.grupos))
    qw = np.where(ok, w * np.where(ok, q, 0.0), 0.0)
    K = candidatos._matriz_nucleo(vec)
    num = np.ascontiguousarray(np.asarray(K.dot(qw.T)).T)
    den = np.ascontiguousarray(np.asarray(K.dot(w.T)).T)
    return num, den


def _serie_ola4(datos, codigo: str, clase: str, variable: str, umbrales) -> tuple[np.ndarray, np.ndarray]:
    """(horas, valores) de una estación: «r» y «rt» en las horas observadas; «b» (r̃) y «a» (anomalía de AB) con
    las horas no observadas interpoladas (CAN-6, CAN-7)."""
    clave = ("serie", codigo, clase, variable, id(umbrales))
    cache = candidatos._cache(datos)
    if clave in cache:
        return cache[clave]
    df = candidatos._tabla(datos, codigo)
    if df is None:
        salida = candidatos._VACIA
    else:
        h, mascara = candidatos._observadas(df)
        if clase == "r":
            salida = (h, df[candidatos.COLUMNA_R[variable]].to_numpy(np.float32)[mascara].astype(np.float64))
        elif clase == "rt":
            col = candidatos.COLUMNA_RT.get(variable, candidatos.COLUMNA_R[variable])
            salida = (h, df[col].to_numpy(np.float32)[mascara].astype(np.float64))
        elif clase in ("b", "a"):
            ho, vo = _serie_ola4(datos, codigo, "rt", variable, umbrales)
            if clase == "a":
                rbar = candidatos._rbar_estacion(datos, codigo, variable)
                _, mes, hora = candidatos._mes_y_hora(ho) if ho.size else (None, np.empty(0, np.int64),
                                                                             np.empty(0, np.int64))
                vo = vo - rbar[mes - 1, hora] if ho.size else vo
            hi, vi = candidatos.interpolar_no_observadas(ho, vo, umbrales)
            hh = np.concatenate([ho, hi])
            vv = np.concatenate([vo, vi])
            orden = np.argsort(hh, kind="stable")
            salida = (hh[orden], vv[orden])
        else:
            raise ErrorCandidatos(f"clase de serie desconocida: {clase!r}")
    cache[clave] = salida
    return salida


def _matriz_en_horas_ola4(datos, codigos, clase: str, variable: str, horas: np.ndarray, umbrales) -> np.ndarray:
    """Valores de la serie de cada estación en ``horas`` (hora × estación), NaN donde no tiene."""
    M = np.full((horas.size, len(codigos)), np.nan)
    for j, c in enumerate(codigos):
        hs, vs = _serie_ola4(datos, c, clase, variable, umbrales)
        if hs.size == 0 or horas.size == 0:
            continue
        pos = np.searchsorted(hs, horas)
        pos_c = np.clip(pos, 0, hs.size - 1)
        ok = (pos < hs.size) & (hs[pos_c] == horas)
        M[ok, j] = vs[pos_c[ok]]
    return M


def _objetivo_estacion_ola4(datos, codigo: str, cand: Candidato, variable: str, umbrales, recorte: bool) \
        -> tuple[np.ndarray, np.ndarray]:
    """(horas, objetivo) de una estación de prueba interna en los días de selección (CAN-14)."""
    h, r = _serie_ola4(datos, codigo, "r", variable, umbrales)
    if h.size == 0:
        return candidatos._VACIA
    sel = np.isfinite(r) & particiones.dias_de_seleccion(h, umbrales, recorte=recorte)
    hs = h[sel]
    if cand is Candidato.A:
        _, mes, hora = candidatos._mes_y_hora(hs) if hs.size else (None, np.empty(0, np.int64), np.empty(0, np.int64))
        y = candidatos._rbar_estacion(datos, codigo, variable)[mes - 1, hora]
    elif cand in (Candidato.B, Candidato.AB):
        hb, vb = _serie_ola4(datos, codigo, "rt" if cand is Candidato.B else "a", variable, umbrales)
        if cand is Candidato.AB:                  # «a» trae también las interpoladas: sólo las observadas
            observada = np.isin(hb, h)
            hb, vb = hb[observada], vb[observada]
        y = np.full(hs.shape, np.nan)
        if hb.size:
            pos = np.searchsorted(hb, hs)
            pos_c = np.clip(pos, 0, hb.size - 1)
            esta = (pos < hb.size) & (hb[pos_c] == hs)
            y[esta] = vb[pos_c[esta]]
    else:
        y = r[sel]
    ok = np.isfinite(y)
    return hs[ok], y[ok]


def _sse_c_ola4(cand: Candidato, variables, interno, datos, umbrales, recorte: bool) -> dict:
    """{α: {código: (sse, n)}} de un pliegue interno para C o C_est."""
    climatologico = cand is Candidato.C_EST
    prueba = {}
    for c in interno.prueba:
        dc = candidatos._datos_c_estacion(datos, c, cand)
        if dc is None:
            continue
        por_var = {v: _objetivo_estacion_ola4(datos, c, cand, v, umbrales, recorte) for v in variables}
        horas, valores = candidatos._comunes(por_var, variables)
        X = candidatos.diseno_c(dc[0], horas, dc[1], climatologico=climatologico)
        finita = np.isfinite(X).all(axis=1)                 # sin diseño finito C no predice (CAN-10)
        if finita.any():
            prueba[c] = (horas[finita], {v: valores[v][finita] for v in variables}, X[finita])
    alfas = [float(a) for a in umbrales.a("C_ALFAS")]
    salida = {a: {} for a in alfas}
    if not prueba:
        return salida
    ajustes = {v: candidatos._ajuste_c(candidatos._filas_de(datos, cand, v), interno.entrenamiento) for v in variables}
    estandar = {v: {c: np.matmul(prueba[c][2], ajustes[v].T) for c in prueba} for v in variables}
    for alfa in alfas:
        modelos = {v: candidatos._resolver_c(ajustes[v], alfa) for v in variables}
        for c, (horas, valores, _) in prueba.items():
            sse = 0.0
            for v in variables:
                e = np.matmul(estandar[v][c], modelos[v].coef) - valores[v]
                sse += float(np.dot(e, e))
            salida[alfa][c] = (sse, int(horas.size))
    return salida


def _horas_de_estacion_ola4(datos, codigo: str) -> np.ndarray:
    """La línea de la ola 4 en ``predecir_prueba``: ``_serie(datos, c, «r», variable, umbrales)[0]`` (las horas
    observadas no dependen de la variable ni de los umbrales)."""
    return _serie_ola4(datos, codigo, "r", "T", None)[0]


def _huella(x) -> tuple:
    """Forma, tipo, contigüidad y sha256 de los bytes de un arreglo: como ``_bits``, pero una diferencia se informa
    corta (CAN-19 compara arreglos grandes)."""
    x = np.asarray(x)
    return x.shape, x.dtype.str, x.flags.c_contiguous, hashlib.sha256(x.tobytes()).hexdigest()


def _como_ola4():
    """``candidatos`` con las funciones de la ola 4 que CAN-19 cambió (la referencia de las salidas públicas)."""
    return mock.patch.multiple(candidatos, _serie=_serie_ola4, _matriz_en_horas=_matriz_en_horas_ola4,
                               _objetivo_estacion=_objetivo_estacion_ola4, _sse_c=_sse_c_ola4,
                               sumas_nucleo=_sumas_nucleo_ola4, _horas_de_estacion=_horas_de_estacion_ola4)


class _UmbralesCon:
    """Los umbrales anclados con algunos valores cambiados (para los errores y los bordes de CAN-19)."""

    def __init__(self, U, **cambios):
        self._U, self._cambios = U, cambios

    def a(self, ident):
        return self._cambios[ident] if ident in self._cambios else self._U.a(ident)

    def frac(self, ident):
        return self._U.frac(ident)


def _bytes_arreglos(x) -> int:
    """Los bytes de los arreglos de una estructura, como ``costo._bytes_obj`` (tablas, arreglos, mapas, tuplas, listas
    y clases de datos; lo demás, 0)."""
    if isinstance(x, pd.DataFrame):
        return int(x.memory_usage(index=True, deep=True).sum())
    if isinstance(x, np.ndarray):
        return int(x.nbytes)
    if isinstance(x, dict):
        return sum(_bytes_arreglos(v) for v in x.values())
    if isinstance(x, (list, tuple)):
        return sum(_bytes_arreglos(v) for v in x)
    if dataclasses.is_dataclass(x):
        return sum(_bytes_arreglos(getattr(x, f.name)) for f in dataclasses.fields(x))
    return 0


@lru_cache(maxsize=None)
def _red_can19():
    """La red de CAN-19: la red chica con una estación fuera de la grilla (D34), dos trihorarias, una diurna y tres
    horarias con huecos de 2, 3, 4 y 6 h (horas interpolables y no), con las cinco variables (inválidas al azar y un
    mes sin Td en una estación, para que A no califique ahí y «a» quede NaN)."""
    infos = _red(4, 0.22, fuera_de_grilla=("330006",))
    h = _horas("2011-01-01T00", "2013-01-01T00")
    verdad = _verdad(infos, h)
    rng = np.random.default_rng(_umbrales().a("SEMILLA"))
    extra = {}
    for k, c in enumerate(sorted(infos)):
        base = verdad[c]["r"]
        x = {"Td": 0.7 * base + rng.normal(0, 0.3, h.size), "u": 0.3 * base + rng.normal(0, 0.5, h.size),
             "v": -0.2 * base + rng.normal(0, 0.5, h.size), "p": 1e-3 * base + rng.normal(0, 2e-4, h.size)}
        for v in x:
            x[v][rng.random(h.size) < 0.03] = NAN
        if k == 2:
            x["Td"][(h >= _h("2011-06-01T00")) & (h < _h("2011-08-01T00"))] = NAN
        extra[c] = x
    patrones = {"330001": "trihoraria", "330003": "trihoraria", "330005": "diurna", "330008": "huecos",
                "330010": "huecos", "330012": "huecos"}
    return infos, h, {c: verdad[c]["r"] for c in infos}, extra, patrones


@lru_cache(maxsize=None)
def _datos_can19() -> tipos.DatosCompetencia:
    """Los datos de la red de CAN-19; el fondo de una de cada tres estaciones trae T_F NaN en algunas horas, para que el
    diseño de C tenga filas no finitas."""
    infos, h, residuos, extra, patrones = _red_can19()
    puntos, clima = _fondo(infos, h)
    for k, c in enumerate(sorted(puntos)):
        if k % 3 == 0:
            T = puntos[c]["T_F"].to_numpy().copy()
            T[np.arange(T.size) % 29 == k % 29] = NAN
            puntos[c] = puntos[c].assign(T_F=T)
    return _datos(infos, h, residuos, patrones=patrones, extra=extra, fondo=(puntos, clima))


def _resultados_publicos(datos, U) -> dict:
    """Lo que dan ``seleccionar`` (con cada suma que recibe el objetivo, en orden y en hexadecimal), ``predecir_prueba``,
    ``matriz_q`` y ``_serie`` sobre ``datos``, cada arreglo por su huella (``_huella``)."""
    salida = {}
    externos = [_pliegue_de(datos, "P1", "330001"), _pliegue_de(datos, "P2", "330008")]
    casos = [(Candidato.A, "T", Uso.AGUDO), (Candidato.B, "T", Uso.AGUDO), (Candidato.AB, "T", Uso.AGUDO),
             (Candidato.C, "T", Uso.AGUDO), (Candidato.C_EST, "T", Uso.CRONICO), (Candidato.B, "uv", Uso.AMBIENTAL),
             (Candidato.AB, "uv", Uso.AMBIENTAL), (Candidato.C, "uv", Uso.AMBIENTAL), (Candidato.AB, "Td", Uso.AGUDO),
             (Candidato.C, "p", Uso.AMBIENTAL)]
    for externo in externos:
        for cand, var, uso in casos:
            vistos = []

            def registrar(internos, sumas, *, candidato, variable, uso):
                vistos.append((candidato.value, variable, {p: [(c, float(s).hex(), n) for c, (s, n) in por.items()]
                                                           for p, por in sumas.items()}))
                return _objetivo(internos, sumas, candidato=candidato, variable=variable, uso=uso)
            for recorte in (False, True):
                clave = (externo.id, cand.value, var, uso.value, recorte)
                hiper = candidatos.seleccionar(cand, var, uso, externo, datos, U, objetivo=registrar, recorte=recorte)
                salida[("seleccion",) + clave] = (repr(hiper), list(vistos))
                vistos.clear()
                for pv in (("u", "v") if var == "uv" else (var,)):
                    df = candidatos.predecir_prueba(cand, pv, uso, hiper, externo, datos, umbrales=U)
                    salida[("prediccion", pv) + clave] = (df["codigo"].tolist(), dict(df.attrs), list(df.columns),
                                                          [_huella(df[k].to_numpy()) for k in ("h", "correccion",
                                                                                             "soporte")])
    infos, h = _red_can19()[:2]
    codigos = sorted(infos)
    horas = np.r_[h[-30:], h[:500], h[::7], h[0] - np.arange(1, 6), h[-1] + np.arange(1, 6), h[100:90:-1]]
    for cand in (Candidato.B, Candidato.AB):
        for v in candidatos.VARIABLES:
            salida[("matriz_q", cand.value, v)] = _huella(candidatos.matriz_q(datos, codigos, cand, v, horas, U))
    for c in codigos:
        for clase in candidatos._CLASES:
            for v in candidatos.VARIABLES:
                salida[("serie", c, clase, v)] = tuple(_huella(x) for x in candidatos._serie(datos, c, clase, v, U))
    return salida


# ---------------------------------------------------------------------------
# CAN-19 (ola 6): la memoria de la selección sin cambiar ningún bit
# ---------------------------------------------------------------------------
class PruebasCan19(unittest.TestCase):
    """CAN-19: la caché de series ya no crece con las horas (sólo guarda la referencia validada a cada tabla y r̄),
    ``_matriz_en_horas`` busca en las filas de la tabla e interpola en el momento, ``_sse_c`` no retiene los diseños de
    todas las estaciones de prueba y ``sumas_nucleo`` va por bloques de horas. Todo con los mismos bits y los mismos
    errores que la copia literal de la ola 4 (``_como_ola4``)."""

    def test_can19_salidas_publicas_bit_a_bit(self):
        """``seleccionar`` (y cada suma de cuadrados que recibe el objetivo, en orden), ``predecir_prueba``,
        ``matriz_q`` y ``_serie`` en A, B, AB, C y C_est, con T, Td, uv y p, en P1 y P2, con y sin el recorte, sobre una
        red con horas interpolables, trihorarias, diurnas, inválidas, un mes sin A y una estación fuera de la grilla:
        iguales bit a bit con la ola 4. ``filas_c``, ``ajustar_c`` y ``predecir_c`` no usan la caché: también iguales."""
        U = _umbrales()
        base = _datos_can19()
        self.assertGreater(sum(int((~df["observada"]).sum()) for df in base.residuos.values()), 1000)
        nueva = _resultados_publicos(dataclasses.replace(base), U)
        with _como_ola4():
            ola4 = _resultados_publicos(dataclasses.replace(base), U)
        self.assertEqual(sorted(nueva), sorted(ola4))
        for clave in ola4:
            self.assertEqual(nueva[clave], ola4[clave], clave)
        for c in ("330001", "330008"):                   # trihoraria y con huecos: «b» trae horas interpoladas
            hb, _ = candidatos._serie(dataclasses.replace(base), c, "b", "T", U)
            self.assertGreater(hb.size, int(base.residuos[c]["observada"].sum()), c)
        externo = _pliegue_de(base, "P1", "330001")
        for cand in ("C", "C_est"):
            modelo = candidatos.ajustar_c(base.filas_c[cand]["T"], externo.entrenamiento, 1.0)
            with _como_ola4():
                ref = candidatos.ajustar_c(base.filas_c[cand]["T"], externo.entrenamiento, 1.0)
            self.assertEqual([_huella(x) for x in (modelo.coef, modelo.media, modelo.desvio)],
                             [_huella(x) for x in (ref.coef, ref.media, ref.desvio)], cand)

    def test_can19_los_mismos_errores_y_bordes(self):
        """Clase o variable desconocidas, estación sin tabla, tabla fuera de esquema, tabla con horas repetidas (una
        observada, o una interpolable fuera de orden), una sola hora observada, sin horas pedidas, ``B_INTERP_H``
        inválido o distinto (2 y 5) y una climatología fuera de esquema: ``_matriz_en_horas`` y ``_serie`` dan lo mismo
        que en la ola 4, sea el valor o el error (tipo y mensaje), estación por estación y todas juntas."""
        U = _umbrales()
        base = _datos_can19()
        res = dict(base.residuos)
        df = res["330008"]
        res["339001"] = pd.concat([df, df.iloc[[5]]], ignore_index=True)              # una observada repetida
        no_obs = np.flatnonzero(~df["observada"].to_numpy())
        res["339002"] = pd.concat([df.drop(index=no_obs[3]), df.iloc[[no_obs[3]]]], ignore_index=True)   # fuera de orden
        res["339003"] = df.astype({"r_T": "float64"})                                    # fuera de esquema
        res["339004"] = df.iloc[[10]].reset_index(drop=True)                              # una sola hora observada
        res["339005"] = df.iloc[:0].reset_index(drop=True)                                # sin filas
        h0 = np.arange(0, 300, dtype=np.int64)
        h0 = h0[h0 % 3 != 1]                                                               # desde la hora 0 (2000)
        res["339006"], _ = candidatos.residuos_estacion("339006", h0, {v: np.cos(h0 / 7.0) for v in
                                                                        candidatos.VARIABLES}, U)
        datos = dataclasses.replace(base, residuos=res)
        self.assertFalse(candidatos._Tabla(res["339001"]).creciente)
        self.assertFalse(candidatos._Tabla(res["339002"]).creciente)
        clima_mala = dataclasses.replace(datos, climatologias=datos.climatologias.astype({"rbar": "float32"}))
        h = _red_can19()[1]
        horas = np.r_[h[:400], h[5000:5400], h[0] - 3, h[-1] + 3, h[200:190:-1], h[30], h[30], np.arange(0, 20),
                      2 ** 32, 2 ** 32 + 2, -2 ** 32, 2 ** 40]                            # fuera de int32: nada
        estaciones = ["330008", "330001", "339001", "339002", "339003", "339004", "339005", "339006", "339999"]
        umbrales_ = {"anclados": U, "B=2.5": _UmbralesCon(U, B_INTERP_H=2.5), "B=2": _UmbralesCon(U, B_INTERP_H=2),
                     "B=5": _UmbralesCon(U, B_INTERP_H=5), "B=1": _UmbralesCon(U, B_INTERP_H=1)}

        def comparar(f_nueva, f_ola4, *args, msg):
            nueva, ola4 = _resultado(f_nueva, *args), _resultado(f_ola4, *args)
            self.assertEqual(nueva[0], ola4[0], msg)
            if nueva[0] == "error":
                self.assertEqual(nueva, ola4, msg)
            else:
                valores = nueva[1] if isinstance(nueva[1], tuple) else (nueva[1],)
                esperados = ola4[1] if isinstance(ola4[1], tuple) else (ola4[1],)
                self.assertEqual([_huella(x) for x in valores], [_huella(x) for x in esperados], msg)
            return nueva
        vistos = set()
        for n_u, Uc in umbrales_.items():
            for d_nombre, d in (("datos", datos), ("clima_mala", clima_mala)):
                for clase in ("r", "rt", "b", "a", "x"):
                    for v in ("T", "u", "q"):
                        for pedidas in (horas, horas[:0]):
                            for grupo in [[c] for c in estaciones] + [estaciones, estaciones[::-1]]:
                                msg = (n_u, d_nombre, clase, v, pedidas.size, tuple(grupo))
                                r = comparar(candidatos._matriz_en_horas, _matriz_en_horas_ola4,
                                             dataclasses.replace(d), grupo, clase, v, pedidas, Uc, msg=msg)
                                vistos.add(r[1] if r[0] == "error" else "ok")
                        for c in estaciones:
                            comparar(candidatos._serie, _serie_ola4, dataclasses.replace(d), c, clase, v, Uc,
                                     msg=(n_u, d_nombre, clase, v, c))
        self.assertEqual(vistos, {"ok", ErrorCandidatos, KeyError, ValueError})

    def test_can19_interpolacion_en_el_momento(self):
        """CAN-6 en el momento: en una serie con huecos de 1 a 8 h, reportes inválidos en los bordes y filas sin
        reporte que la tabla trae aunque no se interpolen, «b» y «a» en cada hora (pedidas en desorden y repetidas) son
        bit a bit las de ``interpolar_no_observadas`` sobre la serie entera, con ``B_INTERP_H`` de 2, 3 y 5."""
        U = _umbrales()
        rng = np.random.default_rng(U.a("SEMILLA"))
        h = _horas("2011-01-01T00", "2013-01-01T00")
        reporta = rng.random(h.size) < 0.55
        reporta[:3] = True
        ho = h[reporta]
        r = {v: rng.normal(0, 1, ho.size) for v in candidatos.VARIABLES}
        for v in r:
            r[v][rng.random(ho.size) < 0.1] = NAN
        df, _ = candidatos.residuos_estacion("330000", ho, r, U)
        sin = np.setdiff1d(h, df["h"].to_numpy().astype(np.int64))[::5]                  # filas que no se interpolan
        extra = pd.DataFrame({"h": sin.astype(np.int32), **{c: np.full(sin.size, np.nan, np.float32)
                                                             for c in ("r_T", "r_Td", "r_u", "r_v", "r_p", "rt_T",
                                                                       "rt_Td")},
                              "g_T": np.full(sin.size, -1, np.int8), "g_Td": np.full(sin.size, -1, np.int8),
                              "observada": np.zeros(sin.size, bool), "interpolable": np.ones(sin.size, bool)})
        df2 = pd.concat([df, extra]).sort_values("h", kind="stable").reset_index(drop=True)
        df2 = df2.astype(dict(tipos.ESQUEMA_RESIDUOS))
        datos0 = _datos_can19()
        for nombre, tabla in (("residuos_estacion", df), ("con filas de más", df2)):
            datos = dataclasses.replace(datos0, residuos={"330000": tabla})
            self.assertTrue(candidatos._Tabla(tabla).creciente)
            pedidas = np.r_[h, h[::-3], h[:50]]
            for B in (2, 3, 5):
                Ub = _UmbralesCon(U, B_INTERP_H=B)
                for clase in ("b", "a"):
                    for v in candidatos.VARIABLES:
                        with self.subTest(tabla=nombre, B=B, clase=clase, v=v):
                            nueva = candidatos._matriz_en_horas(dataclasses.replace(datos), ["330000"], clase, v,
                                                                 pedidas, Ub)
                            ola4 = _matriz_en_horas_ola4(dataclasses.replace(datos), ["330000"], clase, v, pedidas,
                                                         Ub)
                            self.assertEqual(_huella(nueva), _huella(ola4))
                            if B == 3 and clase == "b":
                                hi, _ = candidatos.interpolar_no_observadas(ho, tabla.loc[tabla["observada"],
                                                                            candidatos._columna_de("b", v)]
                                                                            .to_numpy(np.float64), Ub)
                                self.assertGreater(hi.size, 100)

    def test_can19_la_cache_no_crece_con_las_horas(self):
        """Tras seleccionar, predecir y pedir ``matriz_q`` en todas las clases, la caché de la DatosCompetencia sólo
        tiene, por estación con tabla, la referencia a su tabla validada (sin ningún arreglo: la tabla es la misma de
        los residuos) y r̄ (12 × 24 en float64) por estación y variable: sus bytes son exactamente 2.304 por r̄, sin
        nada que crezca con las horas, mientras que la de la ola 4 guardaba ≈ 300 B por estación-hora observada."""
        U = _umbrales()
        base = _datos_can19()
        d_nueva, d_ola4 = dataclasses.replace(base), dataclasses.replace(base)
        _resultados_publicos(d_nueva, U)
        with _como_ola4():
            _resultados_publicos(d_ola4, U)
        cache = candidatos._CACHE[d_nueva]
        tablas = {k: x for k, x in cache.items() if k[0] == "tabla"}
        rbar = {k: x for k, x in cache.items() if k[0] == "rbar"}
        self.assertEqual(set(cache), set(tablas) | set(rbar))
        self.assertEqual({k[1] for k in tablas}, set(base.residuos))
        for (_, c), t in tablas.items():
            self.assertIsInstance(t, candidatos._Tabla)
            self.assertIs(t.df, base.residuos[c])
            self.assertEqual(sorted(t.__slots__), ["creciente", "df", "n_observadas"])
            self.assertFalse(any(isinstance(getattr(t, s), np.ndarray) for s in t.__slots__))
        for x in rbar.values():
            self.assertEqual((x.shape, x.dtype), ((12, 24), np.float64))
        self.assertEqual({k[2] for k in rbar}, set(candidatos.VARIABLES))
        self.assertEqual(_bytes_arreglos(cache), 12 * 24 * 8 * len(rbar))
        observadas = sum(int(df["observada"].sum()) for df in base.residuos.values())
        antes = _bytes_arreglos(candidatos._CACHE[d_ola4])
        self.assertGreater(antes, 250 * observadas)
        self.assertGreater(antes, 300 * _bytes_arreglos(cache))

    def test_can19_sse_c_alfas_repetidos_e_invalidos(self):
        """``_sse_c`` de C y C_est, con u y v juntos, en cada pliegue interno: con los α del Anexo A, con un α repetido
        y con un α inválido (y un insumo que falta), lo mismo que la ola 4, valor a valor o el mismo error."""
        U = _umbrales()
        base = _datos_can19()
        externo = _pliegue_de(base, "P1", "330001")
        internos = particiones.pliegues_internos(externo, base.estaciones, candidatos._grupos(base.estaciones), U)
        alfas = {"anexo": U, "repetido": _UmbralesCon(U, C_ALFAS=(0.1, 1, 1.0, 10, 0.1)),
                 "invalido": _UmbralesCon(U, C_ALFAS=(0.1, 1, -1.0, 10))}
        sin_fondo = dataclasses.replace(base, puntos_e5l={c: F for c, F in base.puntos_e5l.items() if c != "330002"})

        def como_texto(r):
            if r[0] == "error":
                return r
            return [(a, [(c, float(s).hex(), n) for c, (s, n) in por.items()]) for a, por in r[1].items()]
        for nombre, Ua in alfas.items():
            for d_nombre, d in (("datos", base), ("sin_fondo", sin_fondo)):
                for cand, variables in ((Candidato.C, ("u", "v")), (Candidato.C_EST, ("T",)), (Candidato.C, ("p",))):
                    for interno in internos:
                        with self.subTest(alfas=nombre, datos=d_nombre, candidato=cand.value, interno=interno.id):
                            nueva = _resultado(candidatos._sse_c, cand, variables, interno, dataclasses.replace(d), Ua,
                                               False)
                            ola4 = _resultado(_sse_c_ola4, cand, variables, interno, dataclasses.replace(d), Ua, False)
                            self.assertEqual(como_texto(nueva), como_texto(ola4))
        self.assertEqual(_resultado(candidatos._sse_c, Candidato.C, ("T",), internos[0], base, alfas["invalido"],
                                    False)[1], ErrorCandidatos)

    def test_can19_sumas_nucleo_por_bloques(self):
        """``sumas_nucleo`` por bloques de 1, 7, ``_BLOQUE_HORAS`` y más horas que q da los mismos bits que la de una
        vez (ola 4), con estaciones no disponibles, q NaN, un grupo de dos y horas sin ninguna disponible; y los mismos
        errores."""
        U = _umbrales()
        datos = _datos_can19()
        infos = datos.estaciones
        ent = {c: infos[c] for c in sorted(infos) if c not in ("330001", "330005")}
        pts = candidatos.puntos_de_estaciones(infos, ["330001", "330005", "330010"])
        vec = candidatos.vecinos(pts, ent, Hiper(50.0, 50.0, 0.2), U)
        self.assertTrue(any(np.bincount(vec.grupo_est) > 1))
        h = _red_can19()[1][:2500]
        Q = _matriz_en_horas_ola4(dataclasses.replace(datos), vec.codigos, "b", "T", h, U)
        disp = np.isfinite(Q) & (np.arange(Q.shape[1]) % 4 != 1)
        disp[100:130] = False
        ref = _sumas_nucleo_ola4(vec, Q, disp)
        for bloque in (1, 7, candidatos._BLOQUE_HORAS, h.size + 1):
            with self.subTest(bloque=bloque), mock.patch.object(candidatos, "_BLOQUE_HORAS", bloque):
                self.assertEqual([_huella(x) for x in candidatos.sumas_nucleo(vec, Q, disp)], [_huella(x) for x in ref])
                self.assertEqual([_huella(x) for x in candidatos.campo(vec, Q, disp)],
                                 [_huella(x) for x in (ref[0] / (0.2 + ref[1]), ref[1])])
        for args in ((Q[:, :3], disp[:, :3]), (Q, disp.astype(int)), (Q[:0], disp[:0])):
            nueva, ola4 = _resultado(candidatos.sumas_nucleo, vec, *args), _resultado(_sumas_nucleo_ola4, vec, *args)
            self.assertEqual(nueva[0], ola4[0])
            self.assertEqual(nueva if nueva[0] == "error" else [_huella(x) for x in nueva[1]],
                             ola4 if ola4[0] == "error" else [_huella(x) for x in ola4[1]])

    def test_can19_el_fondo_solo_en_los_dias_de_seleccion(self):
        """PED-10 (I20): la selección de C lee el fondo de cada estación de prueba interna sólo en sus horas de los días
        de selección, y la predicción, el de las estaciones de prueba del externo en todas sus horas. Con el fondo de
        las demás estaciones recortado a los días de selección (mód 11 o, con el recorte, mód 23), ``seleccionar`` (con
        sus sumas) y ``predecir_prueba`` de C dan los mismos bits que con el fondo entero."""
        U = _umbrales()
        base = _datos_can19()
        externo = _pliegue_de(base, "P1", "330001")
        for recorte in (False, True):
            recortado = {c: (F if c in externo.prueba else F[particiones.dias_de_seleccion(
                F["h"].to_numpy().astype(np.int64), U, recorte=recorte)].reset_index(drop=True))
                for c, F in base.puntos_e5l.items()}
            self.assertLess(sum(len(F) for F in recortado.values()), sum(len(F) for F in base.puntos_e5l.values()) / 2)
            salidas = []
            for fondo in (base.puntos_e5l, recortado):
                datos = dataclasses.replace(base, puntos_e5l=fondo)
                vistos = []

                def registrar(internos, sumas, *, candidato, variable, uso):
                    vistos.append({p: [(c, float(s).hex(), n) for c, (s, n) in por.items()] for p, por in sumas.items()})
                    return _objetivo(internos, sumas, candidato=candidato, variable=variable, uso=uso)
                alfa = candidatos.seleccionar(Candidato.C, "uv", Uso.AMBIENTAL, externo, datos, U, objetivo=registrar,
                                              recorte=recorte)
                pred = [candidatos.predecir_prueba(Candidato.C, v, Uso.AMBIENTAL, alfa, externo, datos, umbrales=U)
                        for v in ("u", "v")]
                salidas.append((alfa, vistos, [[_huella(p[k].to_numpy()) for k in ("h", "correccion", "soporte")]
                                               for p in pred]))
            self.assertEqual(salidas[0], salidas[1], recorte)


if __name__ == "__main__":
    unittest.main()
