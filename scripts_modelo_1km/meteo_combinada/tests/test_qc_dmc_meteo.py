"""Pruebas de qc_dmc_meteo.py (§2.1-§2.7).

Las que llevan «sNN» son la prueba NN de §9 del texto. Dueño: I12 (ola 3). Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
Datos sólo sintéticos, en carpetas temporales: ninguna prueba abre DMC, la meteorología SINCA real, NASADEM real ni
GHS-POP real. Leen, sin escribir, el código fijado (descargador, adaptador y ``dmc_features``), la clausura del reloj
(``validar_regla_reloj_dmc`` por ``fijados.cargar_validador_reloj``) y los textos anclados de APH (umbrales); si falta
un archivo o cambió de huella, la prueba se omite con el motivo y no se da por aprobada.

Las tablas largas de S1 se hacen a mano (``larga_a_mano``) con el esquema de ``cargar_dmc``; la prueba
``test_s01_larga_a_mano_con_el_esquema_de_cargar_dmc`` las compara, columna por columna, con una salida real de
``cargar_dmc`` sobre un artefacto de ``run_download`` (cliente y guarda falsos).
"""
import sys

sys.dont_write_bytecode = True

import copy  # noqa: E402
import hashlib  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import ceguera, fijados, fondo_era5l, homogeneidad, numerico, politicas, tipos, umbrales  # noqa: E402
from meteo_combinada import qc_dmc_meteo as Q  # noqa: E402
from meteo_combinada import sintetico as S  # noqa: E402
from meteo_combinada.tipos import (Marca, MotivoNoNormalizable, OrigenAborto, OrigenHR, OrigenTd,  # noqa: E402
                                   OrigenViento)

AP = _RAIZ.parent
APH = AP.parent / "Air-Pollution-Health-Chile"
CODIGO = "330020"
SHA_CATALOGO = hashlib.sha256(b"catalogo DMC sintetico de las pruebas de qc").hexdigest()
UTC_MENOS_4, UTC_MENOS_3 = -240, -180
NUDO = 1852 / 3600


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Insumos fijados (se omite la prueba si faltan o cambiaron)
# ---------------------------------------------------------------------------
_U: list = []


def _umbrales(prueba) -> umbrales.Umbrales:
    if not _U:
        for rel in (umbrales.TEXTO_M0, umbrales.JSON_M0, umbrales.TEXTO_VIGENTE):
            if not (APH / rel).is_file():
                prueba.skipTest(f"falta {rel} en APH: no se da por aprobada")
        try:
            _U.append(umbrales.cargar_m0(APH))
        except umbrales.ErrorUmbrales as e:
            prueba.skipTest(f"los umbrales anclados no cargan ({e}); no se da por aprobada")
    return _U[0]


def _codigo_fijado(prueba):
    """Descargador, adaptador y dmc_features con sus huellas de §9.3."""
    for ruta, sha in ((AP / fijados.RUTA_DESCARGADOR, fijados.SHA_DESCARGADOR),
                      (AP / fijados.RUTA_ADAPTADOR, fijados.SHA_ADAPTADOR),
                      (AP / fijados.RUTA_DMC_FEATURES, fijados.SHA_DMC_FEATURES)):
        if not ruta.is_file() or _sha(ruta) != sha:
            prueba.skipTest(f"{ruta.name} falta o cambió de huella; no se da por aprobada")
    return fijados.cargar_descargador(AP), fijados.cargar_adaptador(AP), fijados.cargar_dmc_features(AP)


def _validador(prueba):
    """``validar_regla_reloj_dmc`` con la huella de la clausura del reloj (MC-17, FIJ-1)."""
    esperadas = dict(fijados.HUELLAS_RELOJ)
    try:
        actuales = fijados.huellas_reloj(AP)
    except (OSError, ValueError) as e:
        prueba.skipTest(f"no se puede leer la clausura del reloj ({e}); no se da por aprobada")
    if actuales != esperadas:
        prueba.skipTest("la clausura del reloj cambió respecto de la fijada (FIJ-1, AP 1da0236); no se da por aprobada")
    return fijados.cargar_validador_reloj(AP, esperadas, permitir_cargados=True)


# ---------------------------------------------------------------------------
# Fabricación a mano
# ---------------------------------------------------------------------------
def _info(codigo: str = CODIGO, *, macrozona="centro", conjunto="N", z=520.0, k3=True, fuente="catalogo",
          excluida=None, motivo=None, lat=-33.45, lon=-70.66) -> tipos.InfoEstacion:
    nan = math.nan
    if excluida is None:
        excluida = not k3 or motivo is not None
    if motivo is None and not k3:
        motivo = "k3"
    return tipos.InfoEstacion(
        codigo=codigo, nombre=f"Estación sintética {codigo}", conjunto=conjunto, macrozona=macrozona,
        grupo=tipos.id_grupo([codigo]), omm=None, tipo=None, propietario=None, lat_txt=str(lat), lon_txt=str(lon),
        alt_txt=None if fuente != "catalogo" else str(z), lat=lat, lon=lon, z_cat=z if fuente == "catalogo" else nan,
        rho_km=0.1, k3_pasa=k3, z_s=z, z_s_fuente=fuente, celda=None, utm_e=nan, utm_n=nan, bloque="", pix0=-1,
        pix1=-1, pix2=-1, pix3=-1, w0=nan, w1=nan, w2=nan, w3=nan, respaldo_16km=False, sin_fondo=False,
        excluida=excluida, motivo=motivo)


_ORDEN_PORTAL = ("QFE", "QFF", "QNH", "RR06", "Td", "Ts", "relative_humidity", "wind_direction_instant",
                 "wind_speed_instant")      # el orden de los campos del artefacto (JSON con claves ordenadas)
_CORTO = {"Ts": "Ts", "Td": "Td", "HR": "relative_humidity", "FF": "wind_speed_instant",
          "DD": "wind_direction_instant", "QFE": "QFE", "QFF": "QFF", "QNH": "QNH", "RR06": "RR06"}
_DE_PORTAL = {v: k for k, v in _CORTO.items()}
_UNIDAD = {"Ts": "degC", "Td": "degC", "relative_humidity": "%", "wind_direction_instant": "degree",
           "wind_speed_instant": "m/s", "QFE": "hPa", "QFF": "hPa", "QNH": "hPa", "RR06": "mm"}
_INSTANTANEAS = ("Ts", "Td", "relative_humidity", "wind_speed_instant", "wind_direction_instant", "QFE", "QFF")
_NUMERO = re.compile(r"[+-]?\d+(?:[.,]\d+)?")


def _por_hora(x, n):
    if x is None:
        return [None] * n
    if isinstance(x, (list, tuple, np.ndarray, pd.Series)):
        x = list(x)
        if len(x) != n:
            raise ValueError("un valor por etiqueta")
        return x
    return [x] * n


def _texto(variable: str, x):
    """(raw, value, parse_status) como el descargador y el adaptador (FF en nudos → m/s)."""
    if variable == "RR06":
        raw = "" if x is None else str(x)
    else:
        raw = S._texto_celda(x, S._FORMATO.get(variable))
    if raw == "":
        return raw, None, "empty_source"
    if _NUMERO.fullmatch(raw):
        valor = float(raw.replace(",", "."))
        if variable == "wind_speed_instant":
            valor = valor * NUDO
        return raw, valor, "numeric"
    return raw, None, "literal_source"


def _rango(U, variable: str, z_s):
    if variable == "QFE":
        if z_s is None:
            return None
        p0 = float(numerico.p_std(z_s))
        return p0 + U.a("QQFE_BAJO"), p0 + U.a("QQFE_ALTO")
    _, id_min, id_max, _ = politicas.CALIDAD[variable]
    return U.a(id_min), U.a(id_max)


def larga_a_mano(U, etiquetas, *, codigo=CODIGO, minutos=UTC_MENOS_4, reloj=True, coord=True, med=None,
                 z_s=520.0, id_artefacto=0, **valores) -> pd.DataFrame:
    """La tabla larga de ``cargar_dmc`` hecha a mano (columnas ``tipos.COLUMNAS_LARGA_DMC`` e ``id_artefacto``).

    ``valores``: Ts, Td, HR, FF (en nudos), DD, QFE, QFF y QNH como números (None o NaN = vacío) y RR06 como textos,
    escalares o uno por etiqueta. ``reloj``, ``coord`` y cada ``med[variable corta]``: bool o uno por etiqueta."""
    etiquetas = [pd.Timestamp(e) for e in etiquetas]
    n = len(etiquetas)
    reloj = np.broadcast_to(np.asarray(reloj, dtype=bool), (n,))
    coord = np.broadcast_to(np.asarray(coord, dtype=bool), (n,))
    med = dict(med or {})
    if set(med) - set(_CORTO):
        raise ValueError(f"med con variables desconocidas: {set(med) - set(_CORTO)}")
    meds = {_CORTO[k]: np.broadcast_to(np.asarray(med.get(k, k != "QNH"), dtype=bool), (n,)) for k in _CORTO}
    datos = {_CORTO[k]: _por_hora(valores.get(k), n) for k in _CORTO}
    ajenas = set(valores) - set(_CORTO)
    if ajenas:
        raise ValueError(f"variables desconocidas: {ajenas}")
    filas = []
    for i, L in enumerate(etiquetas):
        utc = (L - pd.Timedelta(minutes=minutos)).tz_localize("UTC") if reloj[i] else pd.NaT
        base = {"station_code": codigo, "timestamp_source": L.isoformat(), "timestamp_utc": utc,
                "clock_verified": bool(reloj[i]), "coordinates_verified": bool(coord[i]), "source_qc": None,
                "id_artefacto": id_artefacto}
        listos, usables, valores_n = {}, {}, {}
        for variable in _ORDEN_PORTAL:
            x = datos[variable][i]
            if isinstance(x, float) and math.isnan(x):
                x = None
            raw, valor, estado = _texto(variable, x)
            m = bool(meds[variable][i])
            listo = bool(reloj[i] and coord[i] and m and variable in _INSTANTANEAS and valor is not None)
            if not listo:
                usable, razon = False, "semantics_or_value_unavailable"
            else:
                rango = _rango(U, variable, z_s)
                if rango is None:
                    usable, razon = False, "quality_policy_unverified"
                elif rango[0] <= valor <= rango[1]:
                    usable, razon = True, "documented_numeric_checks_unknown_source_qc"
                else:
                    usable, razon = False, "documented_numeric_range_rejected"
            listos[variable], usables[variable], valores_n[variable] = listo, usable, valor
            filas.append({**base, "variable": variable, "value": valor, "unit": _UNIDAD[variable], "raw": raw,
                          "parse_status": estado, "measurement_verified": m, "model_ready": listo, "usable": usable,
                          "quality_reason": razon})
        vel, direccion = valores_n["wind_speed_instant"], valores_n["wind_direction_instant"]
        if vel is not None and direccion is not None:
            ang = math.radians(direccion)
            listo = listos["wind_speed_instant"] and listos["wind_direction_instant"]
            listo_qc = listo and usables["wind_speed_instant"] and usables["wind_direction_instant"]
            for variable, valor in (("wind_u", -vel * math.sin(ang)), ("wind_v", -vel * math.cos(ang))):
                filas.append({**base, "variable": variable, "value": valor, "unit": "m/s", "raw": None,
                              "parse_status": "derived", "measurement_verified": listo, "model_ready": listo,
                              "usable": listo_qc, "quality_reason": "derived_from_both_qc_components" if listo_qc
                              else "derived_component_unavailable"})
    d = pd.DataFrame(filas, columns=[*tipos.COLUMNAS_LARGA_DMC, "id_artefacto"])
    d["timestamp_utc"] = pd.to_datetime(d["timestamp_utc"], utc=True).astype("datetime64[ns, UTC]")
    d["value"] = d["value"].astype(np.float64)
    for c in ("clock_verified", "coordinates_verified", "measurement_verified", "model_ready", "usable"):
        d[c] = d[c].astype(bool)
    d["id_artefacto"] = d["id_artefacto"].astype(np.int32)
    return d


def _politica_a_mano(U, codigo: str, desde: str, hasta: str, *, tramo="1.1", media_horaria=False) -> dict:
    """Una política de lectura mínima (lo que lee qc_meteo_combinada: intervalos, ``clock.source`` y los motivos)."""
    sha = U.sha256_texto_vigente
    clock = {"verified": True, "source": (f"reloj-dmc/v1 informe=config/meteorologia/reloj_dmc/v1/informe_reloj_dmc.json "
                                          f"sha256={'a' * 64} estacion={codigo} tramo={tramo} protocolo={'b' * 64}"),
             "valid_from": desde, "valid_to": hasta, "timestamp_semantics": "instantaneous",
             "fixed_offset_minutes": UTC_MENOS_4}
    motivo = politicas.MOTIVO_MEDIA_HORARIA if media_horaria else None
    intervalo = {"valid_from": desde, "valid_to": hasta}
    return {"station_code": codigo, **intervalo, "clock": clock,
            "coordinates": {"verified": True, "source": politicas.source_coordenadas(codigo, SHA_CATALOGO, sha),
                            **intervalo},
            "measurements": {v: {"verified": not media_horaria,
                                 "source": politicas.source_medicion(v, sha, motivo=motivo), **intervalo}
                             for v in politicas.MEDICIONES},
            "quality": {}}


def _etiquetas(n: int, *, desde="2010-01-01T00:00", paso=1) -> list:
    return list(pd.date_range(desde, periods=n, freq=f"{paso}h"))


def _h(etiquetas, minutos=UTC_MENOS_4) -> np.ndarray:
    """La hora UTC (h) de cada etiqueta."""
    u = pd.DatetimeIndex(etiquetas) - pd.Timedelta(minutes=minutos)
    return ((u - pd.Timestamp("2000-01-01")) // pd.Timedelta(hours=1)).to_numpy(np.int64)


def _fondo(h, **campos) -> pd.DataFrame:
    """``ESQUEMA_PUNTOS_E5L`` en las horas ``h`` (continuas), con los campos dados (0 por omisión)."""
    h = np.asarray(h, dtype=np.int64)
    F = {c: np.asarray(campos.get(c, np.zeros(len(h))), dtype=np.float64) for c in fondo_era5l.CAMPOS_F}
    return fondo_era5l.tabla_puntos(h, F)


def _variado(n: int, base: float, paso: float = 0.1) -> np.ndarray:
    """Valores de un decimal que nunca repiten el anterior (sin rachas ni picos)."""
    return np.round(base + paso * (np.arange(n) % 7), 1)


def _qc(U, etiquetas, *, info=None, F=None, k2=frozenset(), pols=None, media_horaria=False, **kw):
    info = info or _info()
    larga = larga_a_mano(U, etiquetas, codigo=info.codigo, **kw)
    if pols is None:
        e = sorted(pd.Timestamp(x) for x in etiquetas)
        pols = [_politica_a_mano(U, info.codigo, e[0].isoformat(), e[-1].isoformat(), media_horaria=media_horaria)]
    return Q.qc_meteo_combinada(larga, info, F, U, k2=k2, politicas=pols)


def _tiene(tabla, columna: str, marca) -> np.ndarray:
    return (tabla[f"marcas_{columna}"].to_numpy(np.uint32) & np.uint32(Marca(marca).bit)) != 0


def _conteo(filas) -> pd.DataFrame:
    """Una tabla de conteo a mano: (codigo, conjunto, macrozona, anio, variable, clave, n)."""
    d = pd.DataFrame([dict(zip(Q.COLUMNAS_CONTEO, f)) for f in filas], columns=list(Q.COLUMNAS_CONTEO))
    return d.astype(Q.COLUMNAS_CONTEO)


def _k4(codigo: str, *, traslado=None, barometro=None, reduccion=(), sin_prueba=False) -> tipos.ResultadoK4:
    quiebres = []
    if traslado is not None:
        quiebres.append(tipos.Quiebre(tipos.Estadistico.T2B.value, traslado, 0.0, tipos.ClaseQuiebre.TRASLADO))
    if barometro is not None:
        quiebres.append(tipos.Quiebre(tipos.Estadistico.T2B.value, barometro, 0.0, tipos.ClaseQuiebre.BAROMETRO))
    for k in reduccion:
        quiebres.append(tipos.Quiebre(tipos.Estadistico.T2A.value, k, 0.0, tipos.ClaseQuiebre.METODO_REDUCCION))
    quiebres.sort(key=lambda q: (q.mes, q.estadistico))
    return tipos.ResultadoK4(codigo=codigo, quiebres=tuple(quiebres), ultimo_traslado=traslado,
                             ultimo_barometro=barometro, sin_prueba=sin_prueba)


def _mes2000(anio: int, mes: int) -> int:
    return (anio - 2000) * 12 + mes - 1


# ---------------------------------------------------------------------------
# Fabricación por el descargador (S2, S15 y la validación de larga_a_mano)
# ---------------------------------------------------------------------------
def _estacion(codigo, L, **columnas) -> S.EstacionSintetica:
    n = len(L)
    base = {"Ts": _variado(n, 15.0), "Td": _variado(n, 5.0), "relative_humidity": np.full(n, 50.0),
            "wind_direction_instant": (np.arange(n) % 35 + 1) * 10.0, "wind_speed_instant": np.full(n, 10.0),
            "QFE": _variado(n, 955.0), "QFF": _variado(n, 1015.0), "RR06": ["s/p"] * n}
    base.update(columnas)
    return S.estacion_sintetica(codigo, -33.45, -70.66, 520.0, L, **base)


def _tramo(tramo: str, desde: str, hasta: str, minutos: int = UTC_MENOS_4, veredicto: str | None = "F(-4)") -> dict:
    return {"tramo": tramo, "valid_from": desde, "valid_to": hasta, "minutos": minutos, "veredicto": veredicto}


class Mundo:
    """Una descarga sintética por ``run_download`` y la publicación de RELOJ con su registro de C5, en ``raiz``.

    ``alterar``: código → cambio del contenido de sus artefactos (``sintetico.alterar_artefacto``), aplicado antes de
    publicar la política, así el artefacto alterado es uno de ``artefactos_evaluados`` (como lo evaluaría RELOJ)."""

    def __init__(self, prueba, raiz: Path, estaciones, reglas, *, desde, hasta, alterar=None, **kw):
        self.descargador, self.adaptador, self.dmc_features = _codigo_fijado(prueba)
        self.dmc = S.fabricar_descarga(estaciones, raiz / "descarga", self.descargador, desde, hasta)
        self.manifiestos = S.manifiestos_de(self.dmc)
        for codigo, cambio in dict(alterar or {}).items():
            for manifiesto in self.manifiestos[codigo]:
                S.alterar_artefacto(manifiesto, cambio)
        shas = S.artefactos_de_descarga(self.dmc)
        self.ruta_politica = S.politica_reloj_sintetica(raiz / "publicacion", shas, reglas, **kw)
        self.rutas = S.rutas_politica_sintetica(raiz / "publicacion")
        self.ap = raiz / "publicacion" / "AP"
        registro = politicas.leer_registro_c5(self.rutas["registro"], ap=self.ap)
        self.politica, self.artefactos = politicas.leer_politica_reloj(registro, ap=self.ap)

    def meses(self, codigo: str) -> set:
        return {tuple(int(x) for x in r.name[:7].split("-")) for r in self.manifiestos.get(codigo, [])}

    def lectura(self, U, info, *, k2=frozenset()):
        tramos = politicas.tramos_de_lectura(self.politica, info.codigo, self.meses(info.codigo),
                                             politicas.marcas_g(self.politica, info.codigo), info=info, k2=k2)
        return politicas.politicas_de_lectura(self.politica, info, tramos, U, sha_protocolo=U.sha256_texto_vigente,
                                              sha_catalogo=SHA_CATALOGO)

    def normalizar(self, manifiesto, pols, validar=None, *, id_artefacto=0, dmc_features=None, artefactos=None):
        def regla(r, s):
            return None if validar is None else validar(r, s, politica_ruta=self.ruta_politica)
        return Q.normalizar_artefacto(manifiesto, pols, adaptador=self.adaptador,
                                      dmc_features=dmc_features or self.dmc_features, validar_regla=regla,
                                      sha_adaptador=fijados.SHA_ADAPTADOR, id_artefacto=id_artefacto,
                                      artefactos=self.artefactos if artefactos is None else artefactos)


def _por(larga, variable):
    return larga[larga.variable == variable]


# ---------------------------------------------------------------------------
# S1: cada regla de §2.4 con series hechas a mano
# ---------------------------------------------------------------------------
class PruebasS1(unittest.TestCase):
    def test_s01_centinela_ts_invalida_td_y_hr(self):
        """Ts = −40,0 invalida también Td y HR de la fila."""
        U = _umbrales(self)
        e = _etiquetas(5)
        ts = _variado(5, 15.0)
        ts[2] = -40.0
        t = _qc(U, e, Ts=ts, Td=_variado(5, 5.0), HR=50)
        for c in ("Ts", "Td", "HR"):
            self.assertEqual(list(_tiene(t, c, Marca.CENTINELA)), [False, False, True, False, False], c)
        self.assertEqual(list(t["valido_Td"]), [True, True, False, True, True])
        self.assertEqual(list(t["valido_HR"]), [True, True, False, True, True])
        self.assertFalse(_tiene(t, "QFE", Marca.CENTINELA).any())
        self.assertTrue(np.isnan(t["td_final"].iloc[2]) and np.isnan(t["hr_final"].iloc[2]))

    def test_s01_centinela_qfe_invalida_qff(self):
        """QFE = 500,0 invalida también QFF."""
        U = _umbrales(self)
        e = _etiquetas(5)
        qfe = _variado(5, 955.0)
        qfe[1] = 500.0
        t = _qc(U, e, Ts=_variado(5, 15.0), QFE=qfe, QFF=_variado(5, 1015.0))
        self.assertEqual(list(_tiene(t, "QFE", Marca.CENTINELA)), [False, True, False, False, False])
        self.assertEqual(list(_tiene(t, "QFF", Marca.CENTINELA)), [False, True, False, False, False])
        self.assertFalse(_tiene(t, "Ts", Marca.CENTINELA).any())
        self.assertEqual(list(t["valido_p"]), [True, False, True, True, True])

    def test_s01_centinela_mira_la_fuente_aunque_el_rango_la_quito(self):
        """D7: la marca 4 mira el valor de la fuente; una hora puede llevar las marcas 3 y 4."""
        U = _umbrales(self)
        e = _etiquetas(4)
        ts = np.array([15.0, -40.0, 15.2, 15.3])
        t = _qc(U, e, Ts=ts, Td=5.0, HR=50)
        self.assertTrue(_tiene(t, "Ts", Marca.FUERA_DE_RANGO)[1] and _tiene(t, "Ts", Marca.CENTINELA)[1])
        self.assertTrue(_tiene(t, "Td", Marca.CENTINELA)[1] and _tiene(t, "HR", Marca.CENTINELA)[1])
        # Una estación alta (≈ 5.000 m): QFE = 500,0 queda dentro del rango y sólo la marca 4 la quita; la tolerancia
        # es «< 0,05» en decimal (500,05 no es centinela, 499,96 sí).
        qfe = np.array([520.0, 500.0, 500.05, 499.96])
        t = _qc(U, e, info=_info(z=5000.0), z_s=5000.0, Ts=_variado(4, 15.0), QFE=qfe, QFF=np.nan)
        self.assertEqual(list(_tiene(t, "QFE", Marca.FUERA_DE_RANGO)), [False] * 4)
        self.assertEqual(list(_tiene(t, "QFE", Marca.CENTINELA)), [False, True, False, True])

    def test_s01_racha_hr100_de_20h_no_y_de_50h_si(self):
        """HR = 100 de 20 h no se marca; de 50 h sí."""
        U = _umbrales(self)
        no_h, si_h = 20, 50
        self.assertEqual((no_h, si_h), (Q.constantes.valor("S1_RACHA_HR100_NO_H"),
                                        Q.constantes.valor("S1_RACHA_HR100_SI_H")))
        for n, esperado in ((no_h, False), (si_h, True)):
            with self.subTest(horas=n):
                t = _qc(U, _etiquetas(n), Ts=_variado(n, 10.0), HR=100)
                self.assertEqual(bool(_tiene(t, "HR", Marca.RACHA).all()), esperado)
                self.assertEqual(bool(_tiene(t, "HR", Marca.RACHA).any()), esperado)
        # HR < 100 idéntica: 12 h sí, 11 h no; y 101 (dentro del recorte) también con 12 h (QC-11, QC-P2).
        for hr, n, esperado in ((60, 12, True), (60, 11, False), (101, 12, True), (101, 11, False)):
            with self.subTest(hr=hr, horas=n):
                t = _qc(U, _etiquetas(n), Ts=_variado(n, 20.0), HR=hr)
                self.assertEqual(bool(_tiene(t, "HR", Marca.RACHA).all()), esperado)

    def test_s01_racha_td_con_hr100_no_se_marca(self):
        """Td idéntico sin contar las horas con HR = 100."""
        U = _umbrales(self)
        n = 20
        t = _qc(U, _etiquetas(n), Ts=_variado(n, 10.1), Td=10.0, HR=100)
        self.assertFalse(_tiene(t, "Td", Marca.RACHA).any())
        self.assertFalse(_tiene(t, "Td", Marca.TD_HR_INCOHERENTE).any())
        # Con HR = 80 (que cambia hora a hora), el mismo Td idéntico 20 h sí es racha.
        t = _qc(U, _etiquetas(n), Ts=_variado(n, 13.3), Td=10.0, HR=80 + np.arange(n) % 2)
        self.assertTrue(_tiene(t, "Td", Marca.RACHA).all())
        self.assertFalse(_tiene(t, "HR", Marca.RACHA).any())
        # Las horas con HR = 100 salen de la serie: un hueco de ≤ 3 h no corta la racha de Td (QC-11, QC-P3).
        hr = np.full(n, 80.0)
        hr[8:10] = 100.0
        t = _qc(U, _etiquetas(n), Ts=_variado(n, 13.3), Td=10.0, HR=hr)
        racha = _tiene(t, "Td", Marca.RACHA)
        self.assertEqual(list(racha), [True] * 8 + [False, False] + [True] * 10)

    def test_s01_racha_ts_qfe_qff_de_12h(self):
        """Ts, QFE y QFF idénticos ≥ 12 h con ≥ 4 reportes.

        Con consecutivos a ≤ 3 h, cubrir 12 h exige ya ≥ 4 reportes (3 reportes cubren a lo más 6 + 3 = 9 h): quitar el
        mínimo de reportes es una mutación equivalente en las rachas de 12 y 48 h, y no lleva prueba propia."""
        U = _umbrales(self)
        for n, esperado in ((12, True), (11, False)):
            with self.subTest(horas=n):
                t = _qc(U, _etiquetas(n), Ts=15.0, QFE=955.0, QFF=1015.0)
                for c in ("Ts", "QFE", "QFF"):
                    self.assertEqual(bool(_tiene(t, c, Marca.RACHA).all()), esperado, c)
                    self.assertEqual(bool(_tiene(t, c, Marca.RACHA).any()), esperado, c)
        # Cada 3 h: 4 reportes cubren 12 h (9 + la mediana de 3 h); 3 reportes, sólo 9 h.
        for n, esperado in ((4, True), (3, False)):
            with self.subTest(cada_3h=n):
                t = _qc(U, _etiquetas(n, paso=3), Ts=15.0)
                self.assertEqual(bool(_tiene(t, "Ts", Marca.RACHA).all()), esperado)
        # Con un hueco de 4 h, dos sucesiones de 6 h no se unen.
        e = _etiquetas(6) + _etiquetas(6, desde="2010-01-01T09:00")
        t = _qc(U, e, Ts=15.0)
        self.assertFalse(_tiene(t, "Ts", Marca.RACHA).any())

    def test_s01_racha_viento_constante_12h(self):
        """Viento con rapidez > 0 y la misma dirección y rapidez ≥ 12 h."""
        U = _umbrales(self)
        for n, esperado in ((12, True), (11, False)):
            with self.subTest(horas=n):
                t = _qc(U, _etiquetas(n), FF=10, DD=270)
                for c in ("FF", "DD"):
                    self.assertEqual(bool(_tiene(t, c, Marca.RACHA).all()), esperado, c)
                self.assertEqual(bool(t["valido_viento"].any()), not esperado)
        # La misma dirección con rapidez que cambia no es racha.
        n = 14
        t = _qc(U, _etiquetas(n), FF=10 + np.arange(n) % 3, DD=270)
        self.assertFalse(_tiene(t, "DD", Marca.RACHA).any())

    def test_s01_pico_con_f1_y_f15(self):
        """Picos con f = 1 (Δt = 1 h) y 1,5 (Δt de 2-3 h; MC-23)."""
        U = _umbrales(self)
        casos = [
            ("f1_pico", 1, [10.0, 10.5, 19.5, 11.0, 11.5], [False, False, True, False, False]),
            ("f1_borde", 1, [10.0, 10.1, 18.1, 10.1, 10.2], [False] * 5),          # 8,0 no supera 8 (decimal)
            ("f15_pico", 3, [10.0, 10.5, 23.1, 11.0, 11.5], [False, False, True, False, False]),
            ("f15_no", 3, [10.0, 10.5, 22.4, 11.0, 11.5], [False] * 5),            # 11,9 y 11,4 ≤ 12
        ]
        for nombre, paso, ts, esperado in casos:
            with self.subTest(caso=nombre):
                t = _qc(U, _etiquetas(len(ts), paso=paso), Ts=np.array(ts))
                self.assertEqual(list(_tiene(t, "Ts", Marca.PICO_O_SALTO)), esperado)
        # Δt de 1 h y de 3 h a cada lado: f = 1,5 (el mayor de los dos).
        e = [pd.Timestamp("2010-01-01T00:00"), pd.Timestamp("2010-01-01T01:00"), pd.Timestamp("2010-01-01T04:00"),
             pd.Timestamp("2010-01-01T05:00")]
        t = _qc(U, e, Ts=np.array([10.0, 20.0, 10.5, 10.6]))       # 10 y 9,5: superan 8 pero no 12
        self.assertFalse(_tiene(t, "Ts", Marca.PICO_O_SALTO).any())
        # Td (10 K), QFE (4 hPa) y FF (15 m/s): el pico sólo en su variable.
        n = 5
        qfe = np.array([955.0, 955.2, 960.0, 955.3, 955.4])
        ff = np.array([5, 6, 40, 6, 7])                               # nudos: 34 kt ≈ 17,5 m/s > 15
        t = _qc(U, _etiquetas(n), Ts=_variado(n, 20.0), QFE=qfe, FF=ff, DD=(np.arange(n) + 1) * 10.0)
        self.assertEqual(list(_tiene(t, "QFE", Marca.PICO_O_SALTO)), [False, False, True, False, False])
        self.assertEqual(list(_tiene(t, "FF", Marca.PICO_O_SALTO)), [False, False, True, False, False])
        self.assertFalse(_tiene(t, "DD", Marca.PICO_O_SALTO).any())                   # D11: sólo FF
        self.assertFalse(bool(t["valido_viento"].iloc[2]))

    def test_s01_salto_unico_invalida_el_posterior(self):
        """Salto > 2θf: se invalida el valor posterior."""
        U = _umbrales(self)
        t = _qc(U, _etiquetas(6), Ts=np.array([10.0, 10.3, 27.0, 27.2, 27.4, 27.6]))
        self.assertEqual(list(_tiene(t, "Ts", Marca.PICO_O_SALTO)), [False, False, True, False, False, False])
        t = _qc(U, _etiquetas(6), Ts=np.array([10.0, 10.3, 26.3, 26.5, 26.7, 26.9]))      # 16,0 no supera 16
        self.assertFalse(_tiene(t, "Ts", Marca.PICO_O_SALTO).any())
        # A 3 h, f = 1,5 también en el salto: el límite es 2·8·1,5 = 24 K (20 K no lo supera; 25 K sí).
        t = _qc(U, _etiquetas(6, paso=3), Ts=np.array([10.0, 10.3, 30.3, 30.5, 30.7, 30.9]))
        self.assertFalse(_tiene(t, "Ts", Marca.PICO_O_SALTO).any())
        t = _qc(U, _etiquetas(6, paso=3), Ts=np.array([10.0, 10.3, 35.3, 35.5, 35.7, 35.9]))
        self.assertEqual(list(_tiene(t, "Ts", Marca.PICO_O_SALTO)), [False, False, True, False, False, False])

    def test_s01_td_mayor_ts_invalida_td_y_hr(self):
        """Td − Ts > 0,5 K (marca 7)."""
        U = _umbrales(self)
        t = _qc(U, _etiquetas(4), Ts=10.0, Td=np.array([10.6, 10.5, 10.2, 9.0]), HR=100)
        self.assertEqual(list(_tiene(t, "Td", Marca.TD_MAYOR_TS)), [True, False, False, False])
        self.assertEqual(list(_tiene(t, "HR", Marca.TD_MAYOR_TS)), [True, False, False, False])
        self.assertEqual(list(t["valido_Td"]), [False, True, True, True])
        self.assertEqual(list(t["valido_HR"]), [False, True, True, True])

    def test_s01_td_recortado(self):
        """0 < Td − Ts ≤ 0,5 K → td_final = Ts (marca 8)."""
        U = _umbrales(self)
        t = _qc(U, _etiquetas(4), Ts=10.0, Td=np.array([10.6, 10.5, 10.2, 9.0]), HR=100)
        self.assertEqual(list(_tiene(t, "Td", Marca.TD_RECORTADO)), [False, True, True, False])
        self.assertEqual(list(t["origen_td"]), [OrigenTd.SIN_VALOR, OrigenTd.RECORTADO, OrigenTd.RECORTADO,
                                                OrigenTd.OBSERVADO])
        self.assertEqual(list(t["td_final"].iloc[1:]), [10.0, 10.0, 9.0])
        self.assertEqual(list(t["Td"]), [10.6, 10.5, 10.2, 9.0])                   # la fuente no cambia

    def test_s01_incoherencia_doble_condicion(self):
        """Marca 9: las dos condiciones a la vez."""
        U = _umbrales(self)

        def condiciones(ts, td, hr):
            dtd = abs(td - float(numerico.td_desde_hr(hr, ts)))
            dhr = abs(hr - float(numerico.hr_desde(ts, td)))
            return dtd > U.a("INCOH_TD"), dhr > U.a("INCOH_HR")

        casos = [((20.0, 10.0, 80.0), True), ((20.0, -1.0, 20.0), False), ((35.0, 25.0, 62.0), False),
                 ((20.0, 10.0, 52.0), False)]
        esperadas = [(True, True), (True, False), (False, True), (False, False)]
        for (fila, marca), cond in zip(casos, esperadas):
            self.assertEqual(condiciones(*fila), cond, fila)              # el caso aísla lo que dice
        n = len(casos)
        ts, td, hr = (np.array([c[0][i] for c in casos]) for i in range(3))
        e = _etiquetas(n, paso=4)                 # a 4 h: no son consecutivos (sin picos ni saltos)
        t = _qc(U, e, Ts=ts, Td=td, HR=hr)
        self.assertEqual(list(_tiene(t, "Td", Marca.TD_HR_INCOHERENTE)), [m for _, m in casos])
        self.assertEqual(list(_tiene(t, "HR", Marca.TD_HR_INCOHERENTE)), [m for _, m in casos])
        self.assertEqual(list(t["valido_Td"]), [not m for _, m in casos])

    def test_s01_incoherencia_bajo_cero_agua_o_hielo_con_conteo(self):
        """Bajo 0 °C, agua o hielo, y se cuenta cuál (MC-25)."""
        U = _umbrales(self)
        a, b, c = Q.constantes.valor("MAGNUS_HIELO")
        ts1, hr1 = -20.0, 80.0
        e = hr1 / 100 * float(numerico.magnus_agua(ts1))
        lg = math.log(e / a)
        td1 = round(c * lg / (b - lg), 1)                      # punto de escarcha de esa HR
        dtd = abs(td1 - float(numerico.td_desde_hr(hr1, ts1)))
        dhr = abs(hr1 - float(numerico.hr_desde(ts1, td1)))
        self.assertTrue(dtd > U.a("INCOH_TD") and dhr > U.a("INCOH_HR"))  # sobre agua no calza
        ts2, hr2 = -5.0, 90.0
        td2 = round(float(numerico.td_desde_hr(hr2, ts2)), 1)  # calza sobre agua y también sobre hielo
        # «Bajo 0 °C» es Ts < 0 (QC-13, QC-P5): con Ts = 1 y Td = −12 no se mira el hielo, aunque sobre hielo calce.
        ts3, td3, hr3 = 1.0, -12.0, 30.5

        def no_calza(ts, td, hr, hielo):
            """Las dos condiciones de la marca 9, con Magnus sobre agua o sobre hielo (Td como punto de escarcha)."""
            if hielo:
                lg_ = math.log(hr / 100 * float(numerico.magnus_agua(ts)) / a)
                td_m = c * lg_ / (b - lg_)
            else:
                td_m = float(numerico.td_desde_hr(hr, ts))
            hr_m = float(numerico.hr_desde(ts, td, hielo=hielo))
            return abs(td - td_m) > U.a("INCOH_TD") and abs(hr - hr_m) > U.a("INCOH_HR")

        for ts, td, hr, sobre_agua, sobre_hielo in ((ts2, td2, hr2, False, False), (ts3, td3, hr3, True, False)):
            self.assertEqual((no_calza(ts, td, hr, False), no_calza(ts, td, hr, True)), (sobre_agua, sobre_hielo),
                             (ts, td, hr))                    # el caso aísla lo que dice
        t = _qc(U, _etiquetas(3, paso=4), Ts=np.array([ts1, ts2, ts3]), Td=np.array([td1, td2, td3]),
                HR=np.array([hr1, hr2, hr3]))
        self.assertEqual(list(_tiene(t, "Td", Marca.TD_HR_INCOHERENTE)), [False, False, True])
        num, _ = Q.conteos_estacion(t, _info())
        cuenta = {k: int(num.loc[num["clave"] == k, "n"].sum()) for k in Q.NUM_CALZA.values()}
        self.assertEqual(cuenta, {"calza_agua": 0, "calza_hielo": 1, "calza_ambas": 1})

    def test_s01_aire_seco_sostenido(self):
        """HR < 2 % ≥ 6 h con ≥ 3 reportes (marca 17)."""
        U = _umbrales(self)
        for n, paso, esperado in ((6, 1, True), (5, 1, False), (3, 3, True), (2, 3, False)):
            with self.subTest(n=n, paso=paso):
                t = _qc(U, _etiquetas(n, paso=paso), Ts=_variado(n, 25.0), HR=1)
                self.assertEqual(bool(_tiene(t, "HR", Marca.AIRE_SECO_SOSTENIDO).all()), esperado)
                self.assertEqual(bool(_tiene(t, "Td", Marca.AIRE_SECO_SOSTENIDO).all()), esperado)
                self.assertEqual(bool(t["valido_HR"].any()), not esperado)
                self.assertEqual(bool(t["valido_Td"].any()), not esperado)      # sin Td derivado de esa HR

    def test_s01_td_derivado(self):
        """Sin Td, con HR y Ts válidas → td_final = Magnus⁻¹ (marca 10)."""
        U = _umbrales(self)
        t = _qc(U, _etiquetas(3), Ts=np.array([20.0, 20.1, 20.2]), Td=np.array([np.nan, 15.0, np.nan]),
                HR=np.array([60.0, 73.0, 60.0]), med={"Ts": [True, True, False]})
        self.assertEqual(list(t["origen_td"]), [OrigenTd.DERIVADO, OrigenTd.OBSERVADO, OrigenTd.SIN_VALOR])
        self.assertAlmostEqual(float(t["td_final"].iloc[0]), float(numerico.td_desde_hr(60.0, 20.0)), places=12)
        self.assertEqual(list(_tiene(t, "Td", Marca.TD_DERIVADO)), [True, False, False])
        self.assertTrue(np.isnan(t["Td"].iloc[0]))                     # la fuente sigue vacía
        self.assertEqual(list(t["valido_Td"]), [True, True, False])    # sin Ts válida no hay derivada
        # «Sin Td» es sin valor en la fuente (QC-14, QC-P4): un Td presente pero inválido no se deriva de la HR.
        t = _qc(U, _etiquetas(2), Ts=np.array([20.0, 20.1]), Td=np.array([12.0, 12.1]), HR=np.array([60.0, 60.5]),
                med={"Td": [False, True]})
        self.assertEqual(list(t["origen_td"]), [OrigenTd.SIN_VALOR, OrigenTd.OBSERVADO])
        self.assertTrue(bool(t["valido_HR"].iloc[0]) and not bool(t["valido_Td"].iloc[0]))

    def test_s01_cero_es_norte(self):
        """Regla del cero por estación-año (marca 19)."""
        U = _umbrales(self)
        n = 100
        dd = (np.arange(n) % 35 + 1) * 10.0                          # 10 … 350, nunca 360
        dd[[20, 70]] = 0.0                                            # 2 % de las horas con rapidez > 0
        ff = 5 + np.arange(n) % 3
        t = _qc(U, _etiquetas(n), FF=ff, DD=dd)
        self.assertEqual(list(np.flatnonzero(_tiene(t, "DD", Marca.CERO_ES_NORTE))), [20, 70])
        self.assertFalse(_tiene(t, "DD", Marca.DIR0_CON_RAPIDEZ).any())
        self.assertEqual(int(t["origen_viento"].iloc[20]), OrigenViento.CERO_ES_NORTE)
        self.assertTrue(t["valido_viento"].all())
        self.assertLess(float(t["v_final"].iloc[20]), 0)              # el 0 leído como norte (S11)
        # El borde: 1 cero en 100 horas es el 1 %, y «≥ 1 %» lo incluye (QC-15).
        dd = (np.arange(n) % 35 + 1) * 10.0
        dd[50] = 0.0
        t = _qc(U, _etiquetas(n), FF=ff, DD=dd)
        self.assertEqual(list(np.flatnonzero(_tiene(t, "DD", Marca.CERO_ES_NORTE))), [50])
        self.assertFalse(_tiene(t, "DD", Marca.DIR0_CON_RAPIDEZ).any())
        # Con 1 cero en 200 horas (0,5 %) no es «cero_es_norte»: rige la 11.
        n = 200
        dd = (np.arange(n) % 35 + 1) * 10.0
        dd[50] = 0.0
        t = _qc(U, _etiquetas(n), FF=5 + np.arange(n) % 3, DD=dd)
        self.assertEqual(list(np.flatnonzero(_tiene(t, "DD", Marca.DIR0_CON_RAPIDEZ))), [50])
        self.assertFalse(_tiene(t, "DD", Marca.CERO_ES_NORTE).any())

    def test_s01_regla_synop_dir0_con_rapidez(self):
        """Con algún 360, el 0 con rapidez > 0 se invalida (marca 11)."""
        U = _umbrales(self)
        n = 100
        dd = (np.arange(n) % 35 + 1) * 10.0
        dd[[20, 70]] = 0.0
        dd[40] = 360.0
        ff = (5 + np.arange(n) % 3).astype(float)
        ff[75] = 0.0                                                  # una calma con DD = 0: no es la 11
        dd[75] = 0.0
        t = _qc(U, _etiquetas(n), FF=ff, DD=dd)
        for c in ("FF", "DD"):
            self.assertEqual(list(np.flatnonzero(_tiene(t, c, Marca.DIR0_CON_RAPIDEZ))), [20, 70], c)
        self.assertFalse(bool(t["valido_viento"].iloc[20]))
        self.assertTrue(bool(t["valido_viento"].iloc[75]))
        # Por año de la etiqueta (MC-58): el 360 de otro año no cuenta.
        e = _etiquetas(n, desde="2010-12-31T00:00")                   # cruza al 2011
        dd2 = dd.copy()
        anios = pd.DatetimeIndex(e).year.to_numpy()
        self.assertEqual(int(anios[40]), 2011)
        t = _qc(U, e, FF=ff, DD=dd2)
        self.assertEqual(int(anios[20]), 2010)
        self.assertTrue(_tiene(t, "DD", Marca.CERO_ES_NORTE)[20])     # 2010: sin 360, 1 de 24 ≥ 1 %
        self.assertTrue(_tiene(t, "DD", Marca.DIR0_CON_RAPIDEZ)[70])  # 2011: con el 360

    def test_s01_calma_persistente(self):
        """Rapidez = 0 en una racha ≥ 48 h (marca 12)."""
        U = _umbrales(self)
        for n, esperado in ((48, True), (47, False)):
            with self.subTest(horas=n):
                t = _qc(U, _etiquetas(n), FF=0, DD=(np.arange(n) % 35 + 1) * 10.0)
                for c in ("FF", "DD"):
                    self.assertEqual(bool(_tiene(t, c, Marca.CALMA_PERSISTENTE).all()), esperado, c)
                self.assertFalse(_tiene(t, "FF", Marca.RACHA).any())
                if not esperado:
                    self.assertTrue((t["u_final"] == 0).all() and (t["v_final"] == 0).all())

    def test_s01_calma_sin_direccion(self):
        """Rapidez 0 válida sin dirección → u = v = 0 (marca 20)."""
        U = _umbrales(self)
        t = _qc(U, _etiquetas(3), FF=np.array([0.0, np.nan, 0.0]), DD=np.array([np.nan, 90.0, 180.0]))
        self.assertEqual(list(t["origen_viento"]), [OrigenViento.CALMA_SIN_DIRECCION, OrigenViento.SIN_VALOR,
                                                    OrigenViento.OBSERVADO])
        self.assertEqual(list(_tiene(t, "FF", Marca.CALMA_SIN_DIRECCION)), [True, False, False])
        self.assertEqual((float(t["u_final"].iloc[0]), float(t["v_final"].iloc[0])), (0.0, 0.0))
        self.assertEqual((float(t["u_final"].iloc[2]), float(t["v_final"].iloc[2])), (0.0, 0.0))
        self.assertEqual(list(t["valido_viento"]), [True, False, True])
        self.assertEqual(np.signbit(t["u_final"].to_numpy()[[0, 2]]).tolist(), [False, False])     # sin −0

    def _con_fondo(self, U, e, *, campo="Ts", desvio=(), escala=1.0, fondo=(), **otras):
        """Una estación en las etiquetas ``e`` con su fondo: el de ``campo`` es la observación más un ruido de
        amplitud ``escala``; ``desvio``: {índice: K o hPa} restado al fondo; ``fondo``: {índice: valor} que lo
        reemplaza. Devuelve (tabla intermedia, residuo float32(obs) − float32(fondo) de cada reporte)."""
        n = len(e)
        h = _h(e)
        i = np.arange(n)
        ruido = ((i * 37) % 11 - 5) / 10.0 * escala
        valores = {"Ts": np.round(15 + 5 * np.sin(2 * np.pi * i / 24), 1)} if campo == "Ts" else {}
        if campo == "Td":
            valores = {"Td": np.round(5 + 3 * np.sin(2 * np.pi * i / 24), 1), "HR": 60 + i % 3}
        if campo == "QFE":
            valores = {"QFE": np.round(955 + 2 * np.sin(2 * np.pi * i / 24), 1)}
        valores.update(otras)
        x = np.asarray(valores[campo], dtype=float)
        en_reporte = x + ruido
        for k, d in dict(desvio).items():
            en_reporte[k] -= d
        for k, v in dict(fondo).items():
            en_reporte[k] = v
        nombre = {"Ts": "T_F", "Td": "Td_F", "QFE": "p_F"}[campo]
        horas = np.arange(h[0], h[-1] + 1)
        F = np.zeros(len(horas))                     # fuera de los reportes el fondo no se mira
        F[h - h[0]] = en_reporte
        campos = {nombre: F}
        if nombre != "p_F":
            campos["p_F"] = np.full(len(horas), 955.0)
        F_est = _fondo(horas, **campos)
        f4 = lambda y: np.asarray(y, dtype=np.float32).astype(np.float64)       # noqa: E731
        return _qc(U, e, F=F_est, **valores), f4(x) - f4(en_reporte)

    def _enero(self, U, *, dias=31, paso=1, **kw):
        """Una estación de enero de 2010 hora a hora (``_con_fondo``)."""
        return self._con_fondo(U, _etiquetas(dias * 24 // paso, paso=paso), **kw)

    def test_s01_error_grueso_aislado(self):
        """Desvío de < 3 h (incluye el reporte suelto): se invalidan los reportes sobre U."""
        U = _umbrales(self)
        t, _ = self._enero(U, desvio={300: 12.0})
        self.assertEqual(list(np.flatnonzero(_tiene(t, "Ts", Marca.ERROR_GRUESO))), [300])
        self.assertFalse(bool(t["valido_T"].iloc[300]))
        self.assertFalse(_tiene(t, "Ts", Marca.DESVIO_PERSISTENTE).any())
        # Dos horas (dura 2 h): sólo la que supera U; la que supera U/2 queda.
        t, _ = self._enero(U, desvio={300: 12.0, 301: 6.0})
        self.assertEqual(list(np.flatnonzero(_tiene(t, "Ts", Marca.ERROR_GRUESO))), [300])
        # Un desvío de 10 K con MAD grande no supera U = 6·1,4826·MAD (≈ 21 K); con el MAD chico, sí (U = 8 K).
        t, _ = self._enero(U, desvio={300: 10.0}, escala=8.0)
        self.assertFalse(_tiene(t, "Ts", Marca.ERROR_GRUESO).any())
        t, _ = self._enero(U, desvio={300: 10.0})
        self.assertEqual(list(np.flatnonzero(_tiene(t, "Ts", Marca.ERROR_GRUESO))), [300])
        # Td (10 K, sólo invalida Td; MC-26) y p (6 hPa, QFE − p_F en hPa).
        t, _ = self._enero(U, campo="Td", desvio={200: 15.0})
        self.assertEqual(list(np.flatnonzero(_tiene(t, "Td", Marca.ERROR_GRUESO))), [200])
        self.assertTrue(bool(t["valido_HR"].iloc[200]))
        self.assertFalse(bool(t["valido_Td"].iloc[200]))
        t, _ = self._enero(U, campo="QFE", desvio={100: 9.0, 101: -9.0})
        self.assertEqual(list(np.flatnonzero(_tiene(t, "QFE", Marca.ERROR_GRUESO))), [100, 101])

    def test_s01_error_grueso_persistente_3_a_24h(self):
        """Desvío de 3 a 24 h: marca 18, no invalida."""
        U = _umbrales(self)
        for largo in (3, 6, 24):
            with self.subTest(horas=largo):
                t, _ = self._enero(U, desvio={300 + k: 12.0 for k in range(largo)})
                marcadas = np.flatnonzero(_tiene(t, "Ts", Marca.DESVIO_PERSISTENTE))
                self.assertEqual(list(marcadas), list(range(300, 300 + largo)))
                self.assertFalse(_tiene(t, "Ts", Marca.ERROR_GRUESO).any())
                self.assertTrue(t["valido_T"].all())

    def test_s01_error_grueso_largo(self):
        """Desvío de > 24 h: se invalida la sucesión entera."""
        U = _umbrales(self)
        desvio = {300 + k: (12.0 if k % 2 else 5.0) for k in range(30)}          # > U/2 todas, > U algunas
        t, _ = self._enero(U, desvio=desvio)
        self.assertEqual(list(np.flatnonzero(_tiene(t, "Ts", Marca.ERROR_GRUESO))), list(range(300, 330)))
        self.assertFalse(_tiene(t, "Ts", Marca.DESVIO_PERSISTENTE).any())
        # 25 h cada hora (dura 25 > 24): también.
        t, _ = self._enero(U, desvio={300 + k: 12.0 for k in range(25)})
        self.assertEqual(int(_tiene(t, "Ts", Marca.ERROR_GRUESO).sum()), 25)
        # Base por (s, m) si la celda (s, m, h) tiene < 30 valores; sin 30 en el mes, la marca no se evalúa.
        t, _ = self._enero(U, desvio={100: 12.0}, dias=20)
        self.assertEqual(list(np.flatnonzero(_tiene(t, "Ts", Marca.ERROR_GRUESO))), [100])
        t, _ = self._enero(U, desvio={10: 20.0}, dias=1)
        self.assertFalse(_tiene(t, "Ts", Marca.ERROR_GRUESO).any())

    def _sin_desvio(self, t, columna="Ts"):
        self.assertFalse(_tiene(t, columna, Marca.ERROR_GRUESO).any())
        self.assertFalse(_tiene(t, columna, Marca.DESVIO_PERSISTENTE).any())

    def test_s01_desvio_del_mismo_signo_y_con_uno_sobre_u(self):
        """§2.4: «sucesión máxima de reportes consecutivos con |r − med| > U/2 del mismo signo y con al menos uno sobre
        U» (QC-17)."""
        U = _umbrales(self)
        # ±12 K alternados 6 h: seis desvíos sueltos de signo opuesto (marca 13 en los seis), no uno de 6 h (marca 18).
        t, _ = self._enero(U, desvio={300 + k: (12.0 if k % 2 else -12.0) for k in range(6)})
        self.assertEqual(list(np.flatnonzero(_tiene(t, "Ts", Marca.ERROR_GRUESO))), list(range(300, 306)))
        self.assertFalse(_tiene(t, "Ts", Marca.DESVIO_PERSISTENTE).any())
        # +5 K 6 h: todos sobre U/2 = 4 y ninguno sobre U = 8; no es desvío.
        self.assertEqual((U.a("EG_T") / Q.constantes.valor("EG_DESVIO_DIVISOR"), U.a("EG_T")), (4.0, 8.0))
        t, _ = self._enero(U, desvio={300 + k: 5.0 for k in range(6)})
        self._sin_desvio(t)

    def _desfase_de_una_hora(self, U, e, *, hora_local=10, desfase=10.0):
        """Un desfase propio de una hora UTC del día (local 10 = 14 UTC) en todos los reportes: con la celda (s, m, h)
        se absorbe; con (s, m) cada reporte de esa hora es un desvío suelto sobre U = 8 K (marca 13)."""
        desvio = {k: desfase for k, x in enumerate(e) if pd.Timestamp(x).hour == hora_local}
        t, _ = self._con_fondo(U, e, desvio=desvio)
        hora_utc = (hora_local - UTC_MENOS_4 // 60) % 24
        en_celda = (_h(e) % 24) == hora_utc
        self.assertEqual(int(en_celda.sum()), len(desvio))
        return t, int(en_celda.sum())

    def test_s01_error_grueso_por_celda_mes_del_anio_y_hora(self):
        """§2.4: mediana y MAD «por mes del año y hora UTC, con todos sus años. Si la celda (s, m, h) tiene < 30
        valores, se usa (s, m)» (QC-17)."""
        U = _umbrales(self)
        n_min = U.a("EG_MIN_N")
        # 30 días: la celda tiene exactamente 30 valores (no es < 30) y manda.
        t, n = self._desfase_de_una_hora(U, _etiquetas(30 * 24))
        self.assertEqual(n, n_min)
        self._sin_desvio(t)
        # 31 días: también manda la celda, no el mes.
        t, n = self._desfase_de_una_hora(U, _etiquetas(31 * 24))
        self.assertEqual(n, n_min + 1)
        self._sin_desvio(t)
        # Dos eneros de 20 días: la celda junta los años (40 ≥ 30), aunque cada enero tenga sólo 20.
        e = _etiquetas(20 * 24, desde="2010-01-01T00:00") + _etiquetas(20 * 24, desde="2011-01-01T00:00")
        t, n = self._desfase_de_una_hora(U, e)
        self.assertEqual(n, 40)
        self._sin_desvio(t)
        # Contraste: un solo enero de 20 días va por (s, m), y ahí el desfase de esa hora sí es desvío.
        t, n = self._desfase_de_una_hora(U, _etiquetas(20 * 24))
        self.assertEqual(int(_tiene(t, "Ts", Marca.ERROR_GRUESO).sum()), n)

    def test_s01_error_grueso_u_con_el_factor_1_4826(self):
        """§2.4: «U = máx(θ_g; 6 · 1,4826 · MAD_s(m,h))»: con 6·MAD < θ_g < 6·1,4826·MAD, un desvío entre θ_g y
        6·1,4826·MAD no supera U (QC-17)."""
        U = _umbrales(self)
        k = 300
        t, r = self._enero(U, desvio={k: 7.7}, escala=4.0)
        h = _h(_etiquetas(31 * 24))
        celda = (h % 24) == (h[k] % 24)                       # todas de enero UTC: la celda (s, m, h) de k
        med, mad = numerico.mediana_mad(r[celda])
        seis, factor, theta = U.a("EG_MULT"), U.a("EG_MAD_K"), U.a("EG_T")
        self.assertLess(seis * mad, theta)                                    # el caso aísla lo que dice
        self.assertLess(theta, seis * factor * mad)
        self.assertTrue(theta < abs(r[k] - med) < seis * factor * mad)
        self._sin_desvio(t)

    def test_s01_error_grueso_sin_td_derivado(self):
        """MC-26: el Td derivado no entra en la base de la marca 13 y no se marca, aunque su residuo sea grande."""
        U = _umbrales(self)
        n, k = 31 * 24, 200
        e = _etiquetas(n)
        i = np.arange(n)
        td = np.round(5 + 3 * np.sin(2 * np.pi * i / 24), 1)
        td[k] = np.nan
        ts = np.full(n, np.nan)
        ts[k] = 15.0                                         # Ts sólo en k: Td derivado allí, sin marca 9 en el resto
        hr = 60 + i % 3
        derivado = float(numerico.td_desde_hr(float(hr[k]), ts[k]))
        t, _ = self._con_fondo(U, e, campo="Td", Td=td, Ts=ts, fondo={k: derivado - 15.0})
        self.assertEqual(int(t["origen_td"].iloc[k]), OrigenTd.DERIVADO)
        self.assertAlmostEqual(float(t["td_final"].iloc[k]), derivado, places=9)
        self.assertGreater(float(t["td_final"].iloc[k]) - (derivado - 15.0), U.a("EG_TD"))     # r = 15 K
        self._sin_desvio(t, "Td")
        self.assertTrue(bool(t["valido_Td"].iloc[k]))

    def test_s01_monotonia_de_usable(self):
        """El envoltorio sólo quita usable, nunca lo da."""
        U = _umbrales(self)
        n = 6
        t = _qc(U, _etiquetas(n), Ts=_variado(n, 15.0), Td=_variado(n, 5.0), HR=50, FF=10,
                DD=(np.arange(n) + 1) * 10.0, QFE=_variado(n, 955.0), QFF=_variado(n, 1015.0),
                med={"Ts": [True, False, True, True, True, True], "HR": [True] * 5 + [False],
                     "QFE": [False] + [True] * 5}, coord=[True, True, True, False, True, True])
        self.assertEqual(list(t["valido_T"]), [True, False, True, False, True, True])
        self.assertEqual(list(t["valido_p"]), [False, True, True, False, True, True])
        self.assertEqual(list(t["valido_HR"]), [True, True, True, False, True, False])
        self.assertTrue(_tiene(t, "Ts", Marca.MEDICION_NO_VERIFICADA)[1])
        self.assertTrue(all(_tiene(t, c, Marca.SIN_COORDENADAS)[3] for c in ("Ts", "Td", "HR", "FF", "DD", "QFE", "QFF")))

    def test_s01_derivadas_aparte(self):
        """td_final, hr_final, u_final y v_final en columnas aparte, con su origen."""
        U = _umbrales(self)
        t = _qc(U, _etiquetas(3), Ts=np.array([10.0, 10.0, 20.0]), Td=np.array([10.3, np.nan, 12.0]),
                HR=np.array([102.0, 101.0, 60.0]), FF=np.array([10, 0, 5]), DD=np.array([270.0, 0.0, 360.0]))
        self.assertEqual(list(t["HR"]), [102.0, 101.0, 60.0])                       # la fuente, sin recortar
        self.assertEqual(list(t["hr_final"]), [100.0, 100.0, 60.0])
        self.assertEqual(list(t["origen_hr"]), [OrigenHR.RECORTADO, OrigenHR.RECORTADO, OrigenHR.OBSERVADO])
        self.assertEqual(list(_tiene(t, "HR", Marca.HR_RECORTADA)), [True, True, False])
        self.assertEqual(list(t["origen_td"]), [OrigenTd.RECORTADO, OrigenTd.DERIVADO, OrigenTd.OBSERVADO])
        self.assertAlmostEqual(float(t["td_final"].iloc[1]), 10.0, places=9)        # Magnus⁻¹(100, Ts) = Ts
        self.assertAlmostEqual(float(t["u_final"].iloc[0]), 10 * NUDO, places=12)  # DD 270: u = +5,144 (S11)
        self.assertLess(float(t["v_final"].iloc[2]), 0)                              # DD 360: v < 0
        anch = Q.tabla_ancha(t)
        for c in ("td_final", "hr_final", "u_final", "v_final"):
            self.assertEqual(str(anch[c].dtype), "float32")
        for c in ("origen_td", "origen_hr", "origen_viento"):
            self.assertEqual(str(anch[c].dtype), "int8")

    def test_s01_propiedad_usable_nunca_vuelve_a_true(self):
        """Propiedad: con marcas al azar, ninguna fila pasa de usable False a True."""
        U = _umbrales(self)
        for semilla in range(6):
            with self.subTest(semilla=semilla):
                rng = np.random.default_rng(semilla)
                n = 300
                e = _etiquetas(n, paso=1)
                vacio = lambda p: rng.random(n) < p            # noqa: E731
                valores = {
                    "Ts": np.where(vacio(0.1), np.nan, np.round(rng.normal(12, 8, n), 1)),
                    "Td": np.where(vacio(0.2), np.nan, np.round(rng.normal(5, 8, n), 1)),
                    "HR": np.where(vacio(0.2), np.nan, rng.integers(0, 105, n).astype(float)),
                    "FF": np.where(vacio(0.1), np.nan, rng.integers(0, 4, n) * rng.integers(0, 30, n)),
                    "DD": np.where(vacio(0.1), np.nan, rng.integers(0, 37, n) * 10.0),
                    "QFE": np.where(vacio(0.1), np.nan, np.round(rng.normal(955, 20, n), 1)),
                    "QFF": np.where(vacio(0.1), np.nan, np.round(rng.normal(1015, 30, n), 1)),
                }
                for c in ("Ts", "QFE"):
                    valores[c][rng.random(n) < 0.03] = {"Ts": -40.0, "QFE": 500.0}[c]
                for c in ("Ts", "HR", "FF"):                     # rachas al azar
                    a = int(rng.integers(0, n - 60))
                    valores[c][a:a + int(rng.integers(5, 60))] = valores[c][a]
                med = {k: rng.random(n) > 0.1 for k in ("Ts", "Td", "HR", "FF", "DD", "QFE", "QFF")}
                larga = larga_a_mano(U, e, reloj=rng.random(n) > 0.05, coord=rng.random(n) > 0.05, med=med,
                                     **valores)
                h = _h(e)
                horas = np.arange(h.min(), h.max() + 1)
                F = _fondo(horas, T_F=rng.normal(12, 8, len(horas)), Td_F=rng.normal(5, 8, len(horas)),
                           p_F=rng.normal(955, 20, len(horas)))
                pols = [_politica_a_mano(U, CODIGO, e[0].isoformat(), e[-1].isoformat())]
                t0 = Q.qc_meteo_combinada(larga, _info(), F, U, k2=frozenset(), politicas=pols)
                k = _mes2000(2010, 1) + int(rng.integers(0, 2))
                t1 = Q.aplicar_k4(t0, _k4(CODIGO, traslado=k if rng.random() < 0.5 else None,
                                          barometro=k + 1 if rng.random() < 0.5 else None), U)
                t2 = Q.marca_14(t1, F, U, tramos=politicas.tramos_de_politicas(pols))
                usables = {c: larga[larga.variable == _CORTO[c]].sort_values("timestamp_source").usable.to_numpy()
                           for c in ("Ts", "QFE", "HR")}
                orden = np.argsort(t0["ts_fuente"].to_numpy())
                for anterior, siguiente in ((t0, t1), (t1, t2)):
                    for c in ("valido_T", "valido_Td", "valido_HR", "valido_viento", "valido_p"):
                        self.assertFalse((siguiente[c].to_numpy() & ~anterior[c].to_numpy()).any(), c)
                for c, col in (("Ts", "valido_T"), ("QFE", "valido_p"), ("HR", "valido_HR")):
                    valido = t2[col].to_numpy()[orden]
                    self.assertFalse((valido & ~usables[c]).any(), c)
                # Una derivada sólo nace de filas fuente válidas.
                der = t2["origen_td"].to_numpy() == OrigenTd.DERIVADO
                self.assertTrue(t2.loc[der, "valido_T"].all() and t2.loc[der, "valido_HR"].all())

    def test_s01_alarmas_q1_q1z_q2_q3_con_su_denominador(self):
        """Q1, Q1z, Q2 y Q3 con su denominador (§2.7)."""
        U = _umbrales(self)
        q1 = Q.clave_q1(Marca.PICO_O_SALTO)
        for n_pico, salta in ((101, True), (100, False)):          # «más del 10 %»: estricto
            with self.subTest(q1=n_pico):
                num = _conteo([(CODIGO, "N", "centro", 2015, "Ts", q1, n_pico)])
                den = _conteo([(CODIGO, "N", "centro", 2015, "Ts", Q.DEN_Q1, 1000),
                               ("330021", "N", "sur", 2015, "Ts", Q.DEN_Q1, 0)])
                a = Q.alarmas(num, den, U)
                nacional = [x for x in a if x["alarma"] == "Q1"]
                self.assertEqual(bool(nacional), salta)
                if salta:
                    self.assertEqual(nacional[0], {"alarma": "Q1", "regla": "pico_o_salto", "variable": "Ts",
                                                   "zona": "nacional", "tasa": 10.1})
        # Q1z: 26 % de una macrozona salta aunque la red quede bajo el 10 %.
        num = _conteo([("330021", "N", "sur", 2015, "Ts", q1, 26)])
        den = _conteo([(CODIGO, "N", "centro", 2015, "Ts", Q.DEN_Q1, 900),
                       ("330021", "N", "sur", 2015, "Ts", Q.DEN_Q1, 100)])
        a = Q.alarmas(num, den, U)
        self.assertEqual([(x["alarma"], x["zona"]) for x in a], [("Q1z", "sur")])
        # Q2: 7 % en 2000-2009 en la red y 23 % en una macrozona; nada fuera del período.
        num = _conteo([(CODIGO, "N", "centro", 2005, "QFE", Q.NUM_Q2, 7), ("330021", "N", "sur", 2005, "QFE",
                                                                        Q.NUM_Q2, 0)])
        den = _conteo([(CODIGO, "N", "centro", 2005, "QFE", Q.DEN_Q2, 30), ("330021", "N", "sur", 2005, "QFE",
                                                                         Q.DEN_Q2, 70)])
        a = Q.alarmas(num, den, U)
        self.assertEqual([(x["alarma"], x["regla"], x["variable"], x["zona"]) for x in a],
                         [("Q2", "coordenadas", "QFE", "nacional"), ("Q2", "coordenadas", "QFE", "centro")])
        num2, den2 = num.copy(), den.copy()
        num2["anio"], den2["anio"] = np.int16(2015), np.int16(2015)
        self.assertEqual(Q.alarmas(num2, den2, U), [])
        # Q3: 3 de 200 artefactos (1,5 %) salta; 2 (1 %) no.
        for malos, salta in ((3, True), (2, False)):
            num = _conteo([(CODIGO, "N", "centro", 2015, Q.VARIABLE_ARTEFACTO, Q.NUM_NO_NORMALIZABLES, malos)])
            den = _conteo([(CODIGO, "N", "centro", 2015, Q.VARIABLE_ARTEFACTO, Q.DEN_ARTEFACTOS, 200)])
            self.assertEqual([x["alarma"] for x in Q.alarmas(num, den, U)], ["Q3"] if salta else [])

    def test_s01_q1_de_la_marca_3_emc1_1(self):
        """EMC1-1: numerador y denominador de la marca 3, por variable de la fuente."""
        U = _umbrales(self)
        n = 100
        for malas, salta in ((11, True), (10, False)):
            with self.subTest(fuera_de_rango=malas):
                ts = _variado(n, 15.0)
                ts[np.arange(malas) * 9 + 3] = 60.0                       # fuera de [−39, 50]
                t = _qc(U, _etiquetas(n), Ts=ts, FF=10 + np.arange(n) % 3, DD=(np.arange(n) % 35 + 1) * 10.0)
                num, den = Q.conteos_estacion(t, _info())
                self.assertEqual(int(num.loc[(num.clave == Q.clave_q1(Marca.FUERA_DE_RANGO)) & (num.variable == "Ts"),
                                             "n"].sum()), malas)
                self.assertEqual(int(den.loc[(den.clave == Q.DEN_Q1_RANGO) & (den.variable == "Ts"), "n"].sum()), n)
                self.assertEqual(int(den.loc[(den.clave == Q.DEN_Q1) & (den.variable == "Ts"), "n"].sum()), n - malas)
                a = Q.alarmas(num, den, U)
                self.assertEqual([(x["alarma"], x["regla"], x["variable"]) for x in a],
                                 [("Q1", "fuera_de_rango", "Ts")] if salta else [])
                # Con el denominador de antes (sólo las usables), 10 de 90 habría saltado: EMC1-1 lo corrige.
                self.assertGreater(10 * 100, U.a("Q1_PCT") * (n - 10))
                self.assertTrue({"wind_u", "wind_v"}.isdisjoint(set(num["variable"]) | set(den["variable"])))
        # Un centinela fuera de rango cuenta en la 3 de Ts y en la 4 de Td y HR, no en la 4 de Ts (EMC1-1).
        ts = _variado(n, 15.0)
        ts[5] = -40.0
        t = _qc(U, _etiquetas(n), Ts=ts, Td=_variado(n, 5.0), HR=50 + np.arange(n) % 3)
        num, _ = Q.conteos_estacion(t, _info())

        def q1(m, v):
            return int(num.loc[(num.clave == Q.clave_q1(m)) & (num.variable == v), "n"].sum())

        self.assertEqual((q1(Marca.FUERA_DE_RANGO, "Ts"), q1(Marca.CENTINELA, "Ts")), (1, 0))
        self.assertEqual((q1(Marca.CENTINELA, "Td"), q1(Marca.CENTINELA, "relative_humidity")), (1, 1))

    def test_s01_q2_emc1_3(self):
        """EMC1-3: el numerador dentro del denominador; las estaciones que K3 deja fuera se cuentan."""
        U = _umbrales(self)
        e = _etiquetas(100, desde="2005-03-01T00:00")
        valores = {"QFE": _variado(100, 955.0)}
        buena = _qc(U, e, info=_info("330021"), **valores)
        k3 = _qc(U, e[:6], info=_info("330022", k3=False), coord=False, **{"QFE": valores["QFE"][:6]})
        fuera = _qc(U, e[:50], info=_info("330023", k3=False, motivo="sin_nasadem"), coord=False,
                    **{"QFE": valores["QFE"][:50]})
        ilegible = _qc(U, e[:1], info=_info("330024", k3=False, motivo="coordenadas_ilegibles", macrozona=None),
                       coord=False, **{"QFE": valores["QFE"][:1]})
        partes = [Q.conteos_estacion(buena, _info("330021")),
                  Q.conteos_estacion(k3, _info("330022", k3=False)),
                  Q.conteos_estacion(fuera, _info("330023", k3=False, motivo="sin_nasadem")),
                  Q.conteos_estacion(ilegible, _info("330024", k3=False, motivo="coordenadas_ilegibles",
                                                     macrozona=None))]
        num = pd.concat([p[0] for p in partes], ignore_index=True)
        den = pd.concat([p[1] for p in partes], ignore_index=True)

        def suma(d, clave, codigo=None):
            sel = (d.clave == clave) & (d.variable == "QFE")
            if codigo:
                sel &= d.codigo == codigo
            return int(d.loc[sel, "n"].sum())

        self.assertEqual(suma(den, Q.DEN_Q2), 100 + 6 + 1)                      # D37: la «sin_nasadem» no entra
        self.assertEqual(suma(num, Q.NUM_Q2), 6 + 1)                            # D36: la ilegible sí
        self.assertEqual(suma(den, Q.DEN_Q2_FUERA, "330023"), 50)              # aparte
        self.assertEqual(suma(den, Q.DEN_Q1, "330022"), 0)                      # sin coordenadas: no es usable
        a = Q.alarmas(num, den, U)
        self.assertEqual([(x["alarma"], x["zona"]) for x in a], [("Q2", "nacional")])
        self.assertAlmostEqual(a[0]["tasa"], 700 / 107)
        # K4 también deja sin coordenadas: las horas antes del último traslado.
        t = Q.aplicar_k4(buena, _k4("330021", traslado=_mes2000(2005, 3) + 1), U)
        n2, d2 = Q.conteos_estacion(t, _info("330021"))
        self.assertEqual(suma(n2, Q.NUM_Q2), suma(d2, Q.DEN_Q2))      # todo marzo antes de abril

    def test_s01_sin_macrozona_solo_en_lo_nacional_d9(self):
        """D9: horas sin macrozona sólo en lo nacional, informadas aparte."""
        U = _umbrales(self)
        q1 = Q.clave_q1(Marca.RACHA)
        for macrozona in (None, "sin_region", "insular"):
            with self.subTest(macrozona=macrozona):
                n = 24
                info = _info("330031", macrozona=macrozona)
                t = _qc(U, _etiquetas(n), info=info, Ts=15.0)              # racha de 24 h: el 100 %
                num, den = Q.conteos_estacion(t, info)
                self.assertTrue(num["macrozona"].isna().all() and den["macrozona"].isna().all())
                otra = _info("330032", macrozona="centro")
                t2 = _qc(U, _etiquetas(n * 5), info=otra, Ts=_variado(n * 5, 15.0))
                n2, d2 = Q.conteos_estacion(t2, otra)
                a = Q.alarmas(pd.concat([num, n2]), pd.concat([den, d2]), U)
                self.assertFalse(any(x["alarma"] == "Q1z" for x in a))                       # en ninguna macrozona
                self.assertEqual([(x["alarma"], x["regla"], x["zona"]) for x in a],
                                 [("Q1", "racha", "nacional")])                              # 24 de 144 en la red
                r = Q.resumen_qc(pd.concat([num, n2]), a, tipos.tabla_vacia(tipos.ESQUEMA_NO_NORMALIZABLES), [],
                                 denominadores=pd.concat([den, d2]), lista=[], umbrales=U)
                self.assertEqual(r["sin_macrozona"], ["330031"])
                self.assertIn(q1, {c["clave"] for c in r["conteos"] if c["macrozona"] is None})

    def test_s01_q2_por_macrozona_en_2000_2009_d10(self):
        """D10: los dos criterios de Q2 miran 2000-2009."""
        U = _umbrales(self)
        for anio, salta in ((2009, True), (2010, False)):
            with self.subTest(anio=anio):
                num = _conteo([("330041", "N", "sur", anio, "Ts", Q.NUM_Q2, 21),
                               (CODIGO, "N", "centro", anio, "Ts", Q.NUM_Q2, 0)])
                den = _conteo([("330041", "N", "sur", anio, "Ts", Q.DEN_Q2, 100),
                               (CODIGO, "N", "centro", anio, "Ts", Q.DEN_Q2, 900)])
                a = Q.alarmas(num, den, U)
                self.assertEqual([(x["alarma"], x["zona"]) for x in a], [("Q2", "sur")] if salta else [])
                self.assertEqual(Q.lista_descriptiva(num, den, U), [])

    def test_s01_larga_a_mano_con_el_esquema_de_cargar_dmc(self):
        """La tabla larga de S1 se valida contra una salida real de cargar_dmc sobre un artefacto sintético."""
        U = _umbrales(self)
        L = list(pd.date_range("2010-01-01T00:00", periods=30, freq="h"))
        n = len(L)
        ts = _variado(n, 15.0)
        ts[[3, 4]] = [60.0, -40.0]
        hr = np.full(n, 50.0)
        hr[7] = 102.0
        dd = (np.arange(n) % 35 + 1) * 10.0
        dd[9] = np.nan
        qfe = _variado(n, 955.0)
        qfe[11] = 500.0
        rr06 = ["s/p"] * n
        rr06[2], rr06[5], rr06[6] = "12.5", "", "-3.0"
        columnas = {"Ts": ts, "Td": _variado(n, 5.0), "relative_humidity": hr, "wind_direction_instant": dd,
                    "wind_speed_instant": 10 + np.arange(n) % 3, "QFE": qfe, "QFF": _variado(n, 1015.0), "RR06": rr06}
        with tempfile.TemporaryDirectory() as tmp:
            m = Mundo(self, Path(tmp), [_estacion(CODIGO, L, **columnas)],
                      {CODIGO: [_tramo("1.1", "2010-01-01T00:00:00", "2010-01-01T23:00:00")]},
                      desde="2010-01-01", hasta="2010-01-31")
            info = _info()
            pols = m.lectura(U, info)
            (manifiesto,) = m.manifiestos[CODIGO]
            r = m.normalizar(manifiesto, pols, _validador(self), id_artefacto=7)
            self.assertTrue(r.normalizable)
            real = Q.unir_largas([r])
        mano = larga_a_mano(U, L, Ts=ts, Td=columnas["Td"], HR=hr, DD=dd, FF=columnas["wind_speed_instant"],
                            QFE=qfe, QFF=columnas["QFF"], RR06=rr06, id_artefacto=7,
                            reloj=np.arange(n) < 24, coord=np.arange(n) < 24,
                            med={k: np.arange(n) < 24 for k in ("Ts", "Td", "HR", "FF", "DD", "QFE", "QFF", "RR06")})
        columnas_qc = [*tipos.COLUMNAS_LARGA_DMC, "id_artefacto"]
        a = real[columnas_qc].sort_values(["timestamp_source", "variable"]).reset_index(drop=True)
        b = mano[columnas_qc].sort_values(["timestamp_source", "variable"]).reset_index(drop=True)
        self.assertEqual({c: str(a[c].dtype) for c in columnas_qc}, {c: str(b[c].dtype) for c in columnas_qc})
        pd.testing.assert_frame_equal(a, b, check_exact=True)
        # Y el envoltorio da lo mismo con la una que con la otra.
        t_real = Q.tabla_ancha(Q.qc_meteo_combinada(real, info, None, U, k2=frozenset(), politicas=pols))
        t_mano = Q.tabla_ancha(Q.qc_meteo_combinada(mano, info, None, U, k2=frozenset(), politicas=pols))
        pd.testing.assert_frame_equal(t_real, t_mano, check_exact=True)
        self.assertEqual(len(t_real), 24)                                   # fuera del tramo: sin reloj ni h


# ---------------------------------------------------------------------------
# S2: el paso 1 con artefactos de run_download y políticas
# ---------------------------------------------------------------------------
class PruebasS2QC(unittest.TestCase):
    def test_s02_reglas_rechazadas_no_se_entregan_a_cargar_dmc(self):
        """Paso 1 de §2.1: una regla rechazada no se entrega."""
        U = _umbrales(self)
        validar = _validador(self)
        L = list(pd.date_range("2010-01-30T00:00", periods=72, freq="h"))
        reglas = {CODIGO: [_tramo("1.1", "2010-01-30T00:00:00", "2010-01-31T23:00:00"),
                           _tramo("1.2", "2010-02-01T00:00:00", "2010-02-01T23:00:00", UTC_MENOS_4, None)]}
        with tempfile.TemporaryDirectory() as tmp:
            m = Mundo(self, Path(tmp), [_estacion(CODIGO, L)], reglas, desde="2010-01-01", hasta="2010-02-28")
            info = _info()
            pols = m.lectura(U, info)
            self.assertEqual([politicas.tramos_de_politicas(pols)[i].id for i in range(2)], ["1.1/1", "1.2/1"])
            enero, febrero = sorted(m.manifiestos[CODIGO])
            r_ene = m.normalizar(enero, pols, validar, id_artefacto=0)
            r_feb = m.normalizar(febrero, pols, validar, id_artefacto=1)
            self.assertEqual((r_ene.reglas_rechazadas, r_feb.reglas_rechazadas), ((), ("1.2",)))
            self.assertTrue(r_ene.normalizable and r_feb.normalizable)
            self.assertTrue(r_ene.larga.clock_verified.all())
            self.assertFalse(r_feb.larga.clock_verified.any())
            self.assertFalse(r_feb.larga.usable.any())
            self.assertEqual(r_feb.meta["policies_sha256"], m.dmc_features.hash_json([]))   # nada entregado
            t = Q.qc_meteo_combinada([r_ene, r_feb], info, None, U, k2=frozenset(), politicas=pols)
            sin_h = t["h"].isna().to_numpy()
            self.assertEqual(int(sin_h.sum()), 24)
            self.assertTrue(_tiene(t, "Ts", Marca.SIN_RELOJ)[sin_h].all())
            ancha = Q.tabla_ancha(t)
            self.assertEqual(len(ancha), 48)
            self.assertEqual(set(ancha["id_artefacto"]), {0})
            self.assertEqual(set(ancha["tramo"]), {"1.1/1"})

    def test_s02_politicas_de_la_estacion_que_cruzan_el_mes(self):
        """cargar_dmc con [manifiesto] y las políticas que cruzan el mes."""
        U = _umbrales(self)
        validar = _validador(self)
        L = list(pd.date_range("2010-01-30T00:00", periods=72, freq="h"))
        reglas = {CODIGO: [_tramo("1.1", "2010-01-30T00:00:00", "2010-01-31T11:00:00", UTC_MENOS_3, "F(-3)"),
                           _tramo("1.2", "2010-01-31T12:00:00", "2010-02-01T23:00:00")]}     # −180 → −240: sin choque
        with tempfile.TemporaryDirectory() as tmp:
            m = Mundo(self, Path(tmp), [_estacion(CODIGO, L)], reglas, desde="2010-01-01", hasta="2010-02-28")
            info = _info()
            pols = m.lectura(U, info)
            self.assertEqual([(p["valid_from"], p["valid_to"]) for p in pols],
                             [("2010-01-30T00:00:00", "2010-01-31T11:00:00"),
                              ("2010-01-31T12:00:00", "2010-02-01T23:00:00")])          # cruza el mes (POL-4)
            enero, febrero = sorted(m.manifiestos[CODIGO])
            r = m.normalizar(febrero, pols, validar, id_artefacto=1)
            self.assertEqual(r.meta["policies_sha256"], m.dmc_features.hash_json([pols[1]]))
            r = m.normalizar(enero, pols, validar, id_artefacto=0)
            self.assertEqual(r.meta["policies_sha256"], m.dmc_features.hash_json(pols))
            self.assertTrue(_por(r.larga, "Ts").usable.all())
            utc = pd.DatetimeIndex(_por(r.larga, "Ts").timestamp_utc).tz_convert(None)
            local = pd.to_datetime(_por(r.larga, "Ts").timestamp_source)
            desfase = (utc - pd.DatetimeIndex(local)) / pd.Timedelta(hours=1)
            self.assertEqual(sorted(set(desfase)), [3.0, 4.0])
            # Los dos tramos de enero y el de febrero, con la columna tramo de lectura (A6).
            r_feb = m.normalizar(febrero, pols, validar, id_artefacto=1)
            t = Q.qc_meteo_combinada([r, r_feb], info, None, U, k2=frozenset(), politicas=pols)
            ancha = Q.tabla_ancha(t)
            self.assertEqual(list(pd.unique(ancha["tramo"])), ["1.1/1", "1.2/1"])
            self.assertTrue((np.diff(ancha["h"].to_numpy()) > 0).all())


# ---------------------------------------------------------------------------
# S15: abortos («no normalizables»)
# ---------------------------------------------------------------------------
class PruebasS15QC(unittest.TestCase):
    def _mundo(self, tmp, columnas=None, *, codigo=CODIGO, caso="caso", alterar=None):
        L = list(pd.date_range("2010-01-01T00:00", periods=24, freq="h"))
        reglas = {codigo: [_tramo("1.1", "2010-01-01T00:00:00", "2010-01-01T23:00:00")]}
        return Mundo(self, Path(tmp) / caso, [_estacion(codigo, L, **(columnas or {}))], reglas,
                     desde="2010-01-01", hasta="2010-01-31", alterar={codigo: alterar} if alterar else None)

    def test_s15_dd_990_no_normalizable(self):
        """dd_990 queda «no normalizable» por los datos."""
        U = _umbrales(self)
        dd = ["270"] * 24
        dd[5] = "990"
        ff = ["010"] * 24
        ff[7] = "-005"
        with tempfile.TemporaryDirectory() as tmp:
            for caso, columnas, motivo in (("dd", {"wind_direction_instant": dd}, MotivoNoNormalizable.DD_FUERA_DE_DOMINIO),
                                           ("ff", {"wind_speed_instant": ff}, MotivoNoNormalizable.RAPIDEZ_NEGATIVA)):
                with self.subTest(caso=caso):
                    m = self._mundo(tmp, columnas, caso=caso)
                    (manifiesto,) = m.manifiestos[CODIGO]
                    r = m.normalizar(manifiesto, m.lectura(U, _info()))
                    self.assertFalse(r.normalizable)
                    self.assertIsNone(r.larga)
                    self.assertEqual((r.motivo, r.origen), (motivo, OrigenAborto.DATOS))
                    self.assertIsNotNone(r.content_sha256)

    def test_s15_codigo_qc_presente_no_normalizable(self):
        """Un código QC presente aborta el artefacto."""
        U = _umbrales(self)

        def con_codigo(payload):
            payload["rows"][3]["fields"]["Ts"]["source_qc"] = "1"
            return payload

        with tempfile.TemporaryDirectory() as tmp:
            m = self._mundo(tmp, alterar=con_codigo)
            (manifiesto,) = m.manifiestos[CODIGO]
            r = m.normalizar(manifiesto, m.lectura(U, _info()))
            self.assertEqual(r.motivo, MotivoNoNormalizable.CODIGO_QC_PRESENTE)
            # QC-3 (MC-21, comprobación 7 de RELOJ): sin política cargar_dmc no mira el código → «regla».
            self.assertEqual(r.origen, OrigenAborto.REGLA)

    def test_s15_interval_minutes_float_origen_regla(self):
        """interval_minutes en float: «no normalizable», origen «regla» (MC-21)."""
        U = _umbrales(self)
        with tempfile.TemporaryDirectory() as tmp:
            m = self._mundo(tmp)
            (manifiesto,) = m.manifiestos[CODIGO]
            for intervalo in (0.0, np.int64(0)):          # float, o un entero de numpy (aborta en la huella JSON)
                with self.subTest(intervalo=type(intervalo).__name__):
                    pols = copy.deepcopy(m.lectura(U, _info()))
                    pols[0]["measurements"]["Ts"]["interval_minutes"] = intervalo
                    r = m.normalizar(manifiesto, pols)
                    self.assertEqual((r.motivo, r.origen),
                                     (MotivoNoNormalizable.INTERVALO_NO_ENTERO, OrigenAborto.REGLA))

    def test_s15_limite_float32_origen_regla(self):
        """Un límite en float32: «no normalizable», origen «regla»."""
        U = _umbrales(self)
        with tempfile.TemporaryDirectory() as tmp:
            m = self._mundo(tmp)
            (manifiesto,) = m.manifiestos[CODIGO]
            pols = copy.deepcopy(m.lectura(U, _info()))
            pols[0]["quality"]["Ts"]["minimum"] = np.float32(-39.0)
            r = m.normalizar(manifiesto, pols)
            self.assertEqual((r.motivo, r.origen), (MotivoNoNormalizable.LIMITE_NO_PYTHON, OrigenAborto.REGLA))

    def test_s15_sin_filas_origen_datos(self):
        """QC-3: un artefacto sin filas aborta también en ``cargar_dmc([manifiesto], [])``: origen «datos»."""
        U = _umbrales(self)

        def sin_filas(payload):
            payload["rows"] = []
            return payload

        with tempfile.TemporaryDirectory() as tmp:
            m = self._mundo(tmp, alterar=sin_filas)
            (manifiesto,) = m.manifiestos[CODIGO]
            payload, meta = m.adaptador.leer_artefacto(manifiesto)
            m.adaptador.normalizar(payload, politica=None, content_sha256=meta["content_sha256"])  # éste no aborta
            r = m.normalizar(manifiesto, m.lectura(U, _info()))
            self.assertEqual((r.motivo, r.origen), (MotivoNoNormalizable.SIN_OBSERVACIONES, OrigenAborto.DATOS))

    def test_s15_solo_artefactos_evaluados_de_la_estacion(self):
        """§2.1, paso 1, «por artefacto de artefactos_evaluados» (QC-1; comprobación 7 de RELOJ): un artefacto que no
        está en artefactos_evaluados, o que figura en otra estación, es un error fuera de la captura."""
        U = _umbrales(self)
        with tempfile.TemporaryDirectory() as tmp:
            m = self._mundo(tmp)
            (manifiesto,) = m.manifiestos[CODIGO]
            pols = m.lectura(U, _info())
            self.assertTrue(m.normalizar(manifiesto, pols).normalizable)
            sha = m.adaptador.leer_artefacto(manifiesto)[1]["content_sha256"]
            self.assertEqual(m.artefactos, {sha: CODIGO})
            for nombre, mapa in (("de otra estación", {sha: "330099"}), ("vacío", {})):
                with self.subTest(mapa=nombre), self.assertRaisesRegex(ValueError, "no es un artefacto evaluado"):
                    m.normalizar(manifiesto, pols, artefactos=mapa)
            with self.assertRaises(TypeError):
                m.normalizar(manifiesto, pols, artefactos=[sha])

            def sin_la_ultima(payload):
                payload["rows"].pop()
                return payload

            S.alterar_artefacto(manifiesto, sin_la_ultima)           # cambió después de publicar la política
            with self.assertRaisesRegex(ValueError, "no es un artefacto evaluado"):
                m.normalizar(manifiesto, pols)

    def test_s15_contados_por_motivo_y_origen_sin_tumbar_la_corrida(self):
        """Se cuentan por motivo y origen y la corrida sigue."""
        U = _umbrales(self)
        dd = ["270"] * 24
        dd[5] = "990"

        def hora_no_nativa(payload):
            payload["rows"][2]["timestamp_source"] = "2010-01-01T02:30:00"
            return payload

        with tempfile.TemporaryDirectory() as tmp:
            m_bien = self._mundo(tmp, caso="bien")
            m_dd = self._mundo(tmp, {"wind_direction_instant": dd}, codigo="330021", caso="dd")
            m_hora = self._mundo(tmp, codigo="330022", caso="hora", alterar=hora_no_nativa)
            infos = {CODIGO: _info(), "330021": _info("330021", macrozona="sur", conjunto="V"),
                     "330022": _info("330022", macrozona=None)}
            resultados = []
            for i, (mundo, codigo) in enumerate(((m_bien, CODIGO), (m_dd, "330021"), (m_hora, "330022"))):
                (manifiesto,) = mundo.manifiestos[codigo]
                resultados.append(mundo.normalizar(manifiesto, mundo.lectura(U, infos[codigo]), id_artefacto=i))
            self.assertEqual([r.normalizable for r in resultados], [True, False, False])
            self.assertEqual([r.motivo for r in resultados[1:]],
                             [MotivoNoNormalizable.DD_FUERA_DE_DOMINIO, MotivoNoNormalizable.HORA_NO_NATIVA_O_REPETIDA])
            nn = Q.tabla_no_normalizables(resultados, infos)
            tipos.validar_esquema(nn, tipos.ESQUEMA_NO_NORMALIZABLES, nombre="nn")
            self.assertEqual(list(nn["id_artefacto"]), [1, 2])
            self.assertEqual(list(nn["origen"]), ["datos", "datos"])
            self.assertTrue(pd.isna(nn["macrozona"].iloc[1]))
            num, den = Q.conteos_artefactos(resultados, infos)
            self.assertEqual(int(den["n"].sum()), 3)
            self.assertEqual(int(num["n"].sum()), 2)
            a = Q.alarmas(num, den, U)
            self.assertEqual(a, [{"alarma": "Q3", "regla": "no_normalizable", "variable": "artefacto",
                                  "zona": "nacional", "tasa": 200 / 3}])
            # La corrida sigue: la estación buena pasa al envoltorio.
            t = Q.qc_meteo_combinada([resultados[0]], infos[CODIGO], None, U, k2=frozenset(),
                                     politicas=m_bien.lectura(U, infos[CODIGO]))
            self.assertEqual(len(Q.tabla_ancha(t)), 24)
            r = Q.resumen_qc(num, a, nn, [], denominadores=den, lista=[], umbrales=U)
            self.assertEqual(r["no_normalizables"]["total"], 2)
            self.assertEqual({(x["motivo"], x["origen"]) for x in r["no_normalizables"]["por_motivo"]},
                             {("dd_fuera_de_dominio", "datos"), ("hora_no_nativa_o_repetida", "datos")})
            self.assertTrue(r["detener"])


# ---------------------------------------------------------------------------
# Lo demás: K4, marca 14, tramo, colisiones, RR06, resumen y los textos del código fijado
# ---------------------------------------------------------------------------
class PruebasQC(unittest.TestCase):
    def test_rr06_desde_raw_sp_es_cero(self):
        """§2.6: «s/p» = 0 mm; celda vacía sin dato; válido en [0, 200] mm."""
        U = _umbrales(self)
        rr = ["s/p", "", "12.5", "250.0", "-1.0", "Inap.", " s/p ", "200.0"]
        n = len(rr)
        t = _qc(U, _etiquetas(n), Ts=_variado(n, 15.0), RR06=rr, coord=[True] * (n - 1) + [False])
        self.assertTrue(np.array_equal(t["rr06_mm"].to_numpy(), [0.0, np.nan, 12.5, 250.0, -1.0, np.nan, 0.0, 200.0],
                                       equal_nan=True))
        self.assertEqual(list(t["rr06_valido"]), [True, False, True, False, False, False, True, False])
        # validar_rr06: sólo los pares con reloj y coordenadas, con la suma del producto; sin enlace y ventanas
        # incompletas aparte.
        ancha = Q.tabla_ancha(t)
        suma = np.array([0.0, 1.0, 10.0, 3.0, 0.0, 0.0, np.nan, 5.0])
        sin = np.array([False, False, False, False, False, False, False, True])
        r = Q.validar_rr06({CODIGO: ancha}, {CODIGO: (suma, sin)}, {CODIGO: _info()}, U)
        self.assertEqual(r["sujeto"], "lluvia_producto")
        self.assertEqual((r["reportes_sin_enlace"], r["reportes_ventana_incompleta"]), (0, 1))
        total = [g for g in r["grupos"] if g["zona"] == "nacional" and g["estacion_del_anio"] is None][0]
        self.assertEqual(total["n_periodos"], 2)
        self.assertEqual((total["total_obs_mm"], total["total_lluvia_producto_mm"]), (12.5, 10.0))
        self.assertEqual(total["frecuencia_obs_lluvia"], 0.5)
        self.assertIn({"zona": "centro", "estacion_del_anio": "DEF"}, [{k: g[k] for k in ("zona", "estacion_del_anio")}
                                                                       for g in r["grupos"]])
        ceguera.vigilar_salida("validacion/rr06.json", r, clase="metrica")

    def test_sumas_lluvia_rr06_por_el_pixel_enlazado_d27(self):
        """D27: el píxel que enlaces_productos enlaza a la celda; sin celda o sin enlace, «sin_enlace»; por lotes."""
        import dataclasses
        U = _umbrales(self)
        e = _etiquetas(3, desde="2000-01-01T00:00")                     # h = 4, 5 y 6
        ancha = Q.tabla_ancha(_qc(U, e, Ts=_variado(3, 15.0), RR06="s/p"))
        self.assertEqual(list(ancha["h"]), [4, 5, 6])
        enlaces = pd.DataFrame({"celda": np.array([5, 6], dtype=np.int64),
                                "era5land_pixel": np.array([101, -1], dtype=np.int64)})
        h = np.arange(0, 48, dtype=np.int64)
        tp = np.column_stack([np.full(48, 1.0), np.full(48, 2.0)])
        infos = {CODIGO: dataclasses.replace(_info(), celda=5), "330021": dataclasses.replace(_info("330021"), celda=6),
                 "330022": _info("330022")}
        tablas = {c: ancha for c in infos}
        r = Q.sumas_lluvia_rr06(tablas, infos, enlaces, tp, h=h, pixel_ids=np.array([101, 102]))
        suma, sin = r[CODIGO]
        self.assertTrue(np.isnan(suma[0]))                               # la ventana de h = 4 empieza en h = −1
        self.assertEqual(list(suma[1:]), [6.0, 6.0])                     # el píxel 101, no el 102
        self.assertFalse(sin.any())
        for codigo in ("330021", "330022"):                             # enlace −1 y estación sin celda (D34)
            self.assertTrue(r[codigo][1].all() and np.isnan(r[codigo][0]).all())
        # Por lotes: lo ya sumado queda; lo que faltaba se llena con el lote siguiente.
        h2 = np.arange(-6, 10, dtype=np.int64)
        r2 = Q.sumas_lluvia_rr06({CODIGO: ancha}, infos, enlaces, np.full((16, 2), 0.5), h=h2,
                                 pixel_ids=np.array([101, 102]), previas=r)
        self.assertEqual(list(r2[CODIGO][0]), [3.0, 6.0, 6.0])

    def test_resumen_qc_sin_estadisticas_del_residuo(self):
        """§0.4.6: sólo marcas, conteos y listas."""
        U = _umbrales(self)
        n = 31 * 24
        e = _etiquetas(n)
        i = np.arange(n)
        ts = np.round(15 + 5 * np.sin(2 * np.pi * i / 24), 1)
        h = _h(e)
        T_F = ts + ((i * 37) % 11 - 5) / 10.0
        T_F[300] -= 12.0
        F = _fondo(h, T_F=T_F, p_F=np.full(n, 955.0))
        t = _qc(U, e, F=F, Ts=ts, QFE=np.round(955 + np.sin(i), 1))
        num, den = Q.conteos_estacion(t, _info())
        lista = Q.lista_descriptiva(num, den, U)
        a = Q.alarmas(num, den, U)
        r = Q.resumen_qc(num, a, tipos.tabla_vacia(tipos.ESQUEMA_NO_NORMALIZABLES), ["330099"],
                         denominadores=den, lista=lista, umbrales=U)
        self.assertEqual(set(r), {"schema", "conteos", "denominadores", "q2_periodo", "q2", "alarmas", "detener",
                                  "no_normalizables", "sin_prueba_de_traslado", "sin_macrozona",
                                  "lista_descriptiva"})
        for fila in r["conteos"] + r["denominadores"]:
            self.assertEqual(set(fila), {"clave", "variable", "macrozona", "conjunto", "n"})
            self.assertIsInstance(fila["n"], int)
        claves = {f["clave"] for f in r["conteos"]}
        self.assertIn(Q.clave_marca(Marca.ERROR_GRUESO), claves)
        texto = repr(r)
        for prohibido in ("mediana", "mad", "residuo", "T_F", "p_F", "r_T"):
            self.assertNotIn(prohibido, texto)
        # Ningún número del residuo: los valores del resumen son conteos y la tasa de las alarmas.
        numeros = [f["n"] for f in r["conteos"] + r["denominadores"]]
        self.assertTrue(all(isinstance(x, int) and x >= 0 for x in numeros))
        ceguera.vigilar_salida("qc/resumen_qc.json", r, clase="resumen")
        self.assertEqual(r["sin_prueba_de_traslado"], ["330099"])

    def test_tabla_ancha_con_el_esquema(self):
        """tipos.ESQUEMA_QC_ESTACION, ordenada por h."""
        U = _umbrales(self)
        e = _etiquetas(5)
        larga = pd.concat([larga_a_mano(U, e[3:], Ts=_variado(2, 15.0), id_artefacto=4),
                           larga_a_mano(U, e[:3], Ts=_variado(3, 16.0), id_artefacto=2)], ignore_index=True)
        pols = [_politica_a_mano(U, CODIGO, e[0].isoformat(), e[-1].isoformat())]
        t = Q.qc_meteo_combinada(larga, _info(), None, U, k2=frozenset(), politicas=pols)
        ancha = Q.tabla_ancha(t)
        tipos.validar_esquema(ancha, tipos.ESQUEMA_QC_ESTACION, nombre="ancha")
        self.assertEqual(ancha.attrs["esquema"], tipos.ESQUEMA_QC_ESTACION.version)
        self.assertEqual(list(ancha["h"]), list(_h(e)))
        self.assertEqual(list(ancha["id_artefacto"]), [2, 2, 2, 4, 4])
        self.assertEqual(list(ancha["ts_fuente"]), [x.isoformat() for x in e])
        self.assertTrue(ancha["Td"].isna().all())
        self.assertFalse(any(c.startswith("_") for c in ancha.columns))

    def test_textos_de_aborto_en_el_codigo_fijado(self):
        """QC-4: cada texto de error que se lee está en el código fijado (adaptador o dmc_features)."""
        _codigo_fijado(self)
        fuente = ((AP / fijados.RUTA_ADAPTADOR).read_text(encoding="utf-8")
                  + (AP / fijados.RUTA_DMC_FEATURES).read_text(encoding="utf-8"))
        for fragmento, _ in Q._TEXTOS_ABORTO:
            self.assertIn(fragmento, fuente)

    def test_error_fondo_no_cuenta_como_no_normalizable(self):
        """ErrorFondo (y lo que no es ValueError ni TypeError) no se captura en el paso 1 (MC-57, FON-2)."""
        U = _umbrales(self)
        with tempfile.TemporaryDirectory() as tmp:
            L = list(pd.date_range("2010-01-01T00:00", periods=24, freq="h"))
            m = Mundo(self, Path(tmp), [_estacion(CODIGO, L)],
                      {CODIGO: [_tramo("1.1", "2010-01-01T00:00:00", "2010-01-01T23:00:00")]},
                      desde="2010-01-01", hasta="2010-01-31")
            (manifiesto,) = m.manifiestos[CODIGO]

            class DmcQueFalla:
                """Falla con las políticas con ``error``; sin política, con un ValueError (así el origen sería
                «datos» si el error se capturara: la prueba no pasa por la segunda llamada)."""
                def __init__(self, error):
                    self.error = error

                def cargar_dmc(self, manifiestos, politicas_, **k):
                    if politicas_:
                        raise self.error
                    raise ValueError("sin política")

            for error in (fondo_era5l.ErrorFondo("fondo mal armado"), KeyError("clave"), OSError("disco")):
                with self.subTest(error=type(error).__name__):
                    with self.assertRaises(type(error)):
                        m.normalizar(manifiesto, m.lectura(U, _info()), dmc_features=DmcQueFalla(error))
            r = m.normalizar(manifiesto, m.lectura(U, _info()), dmc_features=DmcQueFalla(TypeError("tipo")))
            self.assertEqual(r.motivo, MotivoNoNormalizable.OTRO)
            with self.assertRaises(ValueError):
                Q.normalizar_artefacto(manifiesto, [], adaptador=m.adaptador, dmc_features=m.dmc_features,
                                       validar_regla=lambda r_, s: None, sha_adaptador="0" * 64, id_artefacto=0,
                                       artefactos=m.artefactos)
        # El fondo mal armado en el envoltorio: ErrorFondo, que detiene la corrida.
        e = _etiquetas(3)
        malo = _fondo(_h(e)).drop(columns=["amp_TF"])
        with self.assertRaises(fondo_era5l.ErrorFondo):
            _qc(U, e, F=malo, Ts=_variado(3, 15.0))

    def test_k4_entrada_a4_y_codigo(self):
        """A4: NaN donde no es válida tras el paso 2; ``k4(…, codigo=…)`` con z_cat; sin QFE válida, marca 21."""
        U = _umbrales(self)
        n = 6
        e = _etiquetas(n)
        qfe = _variado(n, 955.0)
        qfe[2] = 500.0
        t = _qc(U, e, Ts=_variado(n, 15.0), QFE=qfe, QFF=_variado(n, 1015.0))
        F = _fondo(_h(e), p_F=np.full(n, 954.0))
        entrada, p_F = Q.entrada_k4(t, F)
        self.assertEqual(list(entrada.columns), ["h", "Ts", "QFE", "QFF"])
        self.assertEqual(str(entrada["h"].dtype), "int32")
        self.assertTrue(np.isnan(entrada["QFE"].iloc[2]) and np.isnan(entrada["QFF"].iloc[2]))
        self.assertEqual(list(p_F), [954.0] * n)
        r = Q.k4_estacion(t, F, _info(), U)
        self.assertEqual((r.codigo, r.sin_prueba), (CODIGO, False))
        sin_qfe = _qc(U, e, Ts=_variado(n, 15.0), QFE=np.nan)
        r = Q.k4_estacion(sin_qfe, None, _info(), U)
        self.assertTrue(r.sin_prueba)
        t2 = Q.aplicar_k4(sin_qfe, r, U)
        for c, esperado in (("QFE", True), ("QFF", True), ("Ts", False), ("Td", False), ("HR", False)):
            self.assertEqual(bool(_tiene(t2, c, Marca.SIN_PRUEBA_DE_TRASLADO).all()), esperado, c)   # QC-9
            self.assertEqual(bool(_tiene(t2, c, Marca.SIN_PRUEBA_DE_TRASLADO).any()), esperado, c)
        with self.assertRaises(ValueError):
            Q.aplicar_k4(t, _k4("330099"), U)

    def test_mc53_aplicar_k4_coincide_con_la_efectiva(self):
        """MC-53: releer con la política efectiva da las mismas filas con coordenadas que las sin marca 1."""
        U = _umbrales(self)
        L = list(pd.date_range("2019-01-30T00:00", periods=48, freq="h")) + \
            list(pd.date_range("2019-02-01T00:00", periods=48, freq="h"))
        k_traslado = _mes2000(2019, 2)
        k_barometro = _mes2000(2019, 2)
        with tempfile.TemporaryDirectory() as tmp:
            m = Mundo(self, Path(tmp), [_estacion(CODIGO, L)],
                      {CODIGO: [_tramo("1.1", "2019-01-30T00:00:00", "2019-02-02T23:00:00")]},
                      desde="2019-01-01", hasta="2019-02-28")
            info = _info()
            lectura = m.lectura(U, info)
            resultados = [m.normalizar(man, lectura, id_artefacto=i) for i, man in enumerate(sorted(m.manifiestos[CODIGO]))]
            k4 = _k4(CODIGO, traslado=k_traslado, barometro=k_barometro)
            t = Q.aplicar_k4(Q.qc_meteo_combinada(resultados, info, None, U, k2=frozenset(), politicas=lectura), k4, U)
            efectivas = politicas.politicas_efectivas(lectura, {CODIGO: k4})
            releidas = [m.normalizar(man, efectivas, id_artefacto=i).larga
                        for i, man in enumerate(sorted(m.manifiestos[CODIGO]))]
            coord = pd.concat(releidas)
            coord = coord[coord.variable == "Ts"].set_index("timestamp_source")["coordinates_verified"].sort_index()
            sin_marca_1 = pd.Series(~_tiene(t, "Ts", Marca.SIN_COORDENADAS), index=t["ts_fuente"].to_numpy()).sort_index()
            self.assertEqual(list(coord.index), list(sin_marca_1.index))
            self.assertEqual(list(coord), list(sin_marca_1))
            self.assertTrue((~coord).any() and coord.any())
            # La 16 en QFE y QFF antes del barómetro; Ts sigue con su valor y su marca 1.
            antes = t["h"].to_numpy(dtype=float) < (pd.Timestamp("2019-02-01") - pd.Timestamp("2000-01-01")) / pd.Timedelta(hours=1)
            for c in ("QFE", "QFF"):                          # §2.4: «QFE y QFF antes del quiebre»
                self.assertTrue(_tiene(t, c, Marca.BAROMETRO_INHOMOGENEO)[antes].all(), c)
                self.assertFalse(_tiene(t, c, Marca.BAROMETRO_INHOMOGENEO)[~antes].any(), c)
            self.assertFalse(_tiene(t, "Ts", Marca.BAROMETRO_INHOMOGENEO).any())

    def test_marca_14_en_los_tramos_de_la_efectiva_d24(self):
        """D24: |mediana(QFE − p_F)| > 8 hPa en cada tramo de la política efectiva; la columna tramo es la efectiva."""
        U = _umbrales(self)
        e = _etiquetas(24 * 4, desde="2010-01-30T00:00")             # 30-31 de enero y 1-2 de febrero
        n = len(e)
        qfe = _variado(n, 955.0)
        h = _h(e)
        febrero = h >= (pd.Timestamp("2010-02-01") - pd.Timestamp("2000-01-01")) / pd.Timedelta(hours=1)
        p_F = qfe - np.where(febrero, 10.0, 0.3)
        F = _fondo(h, p_F=p_F)
        info = _info()
        pols = [_politica_a_mano(U, CODIGO, e[0].isoformat(), e[-1].isoformat())]
        t = _qc(U, e, F=F, pols=pols, Ts=_variado(n, 15.0), QFE=qfe)
        self.assertEqual(set(t["tramo"]), {"1.1/1"})
        k4 = _k4(CODIGO, reduccion=(_mes2000(2010, 2),))              # sólo corta la política, sin marcas
        t = Q.aplicar_k4(t, k4, U)
        efectivas = politicas.politicas_efectivas(pols, {CODIGO: k4})
        tramos = politicas.tramos_marca_14(efectivas, CODIGO)
        self.assertEqual([x.id for x in tramos], ["1.1/1", "1.1/2"])
        t = Q.marca_14(t, F, U, tramos=tramos)
        self.assertEqual(list(_tiene(t, "QFE", Marca.ALTITUD_INCOHERENTE)), list(febrero))
        self.assertFalse(_tiene(t, "QFF", Marca.ALTITUD_INCOHERENTE).any())
        self.assertEqual(list(t["valido_p"]), list(~febrero))
        self.assertEqual(list(t["tramo"]), ["1.1/2" if f else "1.1/1" for f in febrero])
        self.assertEqual(list(Q.tabla_ancha(t)["tramo"]), list(t["tramo"]))
        # qc_estacion encadena los pasos 2 a 4 y da la efectiva.
        larga = larga_a_mano(U, e, Ts=_variado(n, 15.0), QFE=qfe)
        tabla, r, ef = Q.qc_estacion(larga, info, F, U, k2=frozenset(), politicas=pols)
        self.assertEqual(r.codigo, CODIGO)
        self.assertEqual(ef, politicas.politicas_efectivas(pols, {CODIGO: r}))
        self.assertTrue(_tiene(tabla, "QFE", Marca.ALTITUD_INCOHERENTE)[febrero].all())    # toda la pieza

    def test_marca_14_tambien_en_horas_ya_quitadas_qc_20(self):
        """QC-20 y QC-9: la marca 14 va en todas las horas del tramo con valor, aunque otra regla ya las haya quitado
        (MC-24); la mediana es sólo de las válidas. Q1 la cuenta en cada hora de su denominador (QC-P6)."""
        U = _umbrales(self)
        n, racha = 48, 13
        e = _etiquetas(n)
        qfe = np.r_[np.full(racha, 955.0), _variado(n - racha, 956.0)]
        F = _fondo(_h(e), p_F=qfe - 10.0)
        pols = [_politica_a_mano(U, CODIGO, e[0].isoformat(), e[-1].isoformat())]
        t = _qc(U, e, F=F, pols=pols, Ts=_variado(n, 15.0), QFE=qfe)
        self.assertEqual(list(_tiene(t, "QFE", Marca.RACHA)), [True] * racha + [False] * (n - racha))
        t = Q.marca_14(t, F, U, tramos=politicas.tramos_de_politicas(pols))
        self.assertTrue(_tiene(t, "QFE", Marca.ALTITUD_INCOHERENTE).all())
        self.assertFalse(t["valido_p"].any())
        num, den = Q.conteos_estacion(t, _info())

        def suma(d, clave):
            return int(d.loc[(d.clave == clave) & (d.variable == "QFE"), "n"].sum())

        self.assertEqual((suma(num, Q.clave_q1(Marca.ALTITUD_INCOHERENTE)), suma(den, Q.DEN_Q1)), (n, n))
        self.assertEqual(suma(num, Q.clave_q1(Marca.RACHA)), racha)

    def test_k2_k3_media_horaria_y_excluidas(self):
        """Marca 1 por K2 y K3; marca 22 con el bit 2 en toda la estación; una excluida no tiene horas válidas."""
        U = _umbrales(self)
        n = 4
        e = _etiquetas(n)
        t = _qc(U, e, k2=frozenset({CODIGO}), Ts=_variado(n, 15.0))
        self.assertTrue(_tiene(t, "Ts", Marca.SIN_COORDENADAS).all())
        self.assertFalse(t["valido_T"].any())
        with self.assertRaises(ValueError):
            _qc(U, e, k2=CODIGO, Ts=_variado(n, 15.0))                  # un texto no es la lista K2
        t = _qc(U, e, info=_info(k3=False), Ts=_variado(n, 15.0))
        self.assertTrue(_tiene(t, "QFF", Marca.SIN_COORDENADAS).all())
        t = _qc(U, e, media_horaria=True, med={k: False for k in ("Ts", "Td", "HR", "FF", "DD", "QFE", "QFF")},
                Ts=_variado(n, 15.0))
        for c in ("Ts", "Td", "HR", "FF", "DD", "QFE", "QFF"):
            self.assertTrue(_tiene(t, c, Marca.POSIBLE_MEDIA_HORARIA).all() and
                            _tiene(t, c, Marca.MEDICION_NO_VERIFICADA).all(), c)
        # §2.1: «la estación y el tramo no están excluidos» en todas las columnas valido_* (QC-8).
        todo = dict(Ts=_variado(n, 15.0), Td=_variado(n, 5.0), HR=50 + np.arange(n), FF=10 + np.arange(n),
                    DD=(np.arange(n) + 1) * 10.0, QFE=_variado(n, 955.0), QFF=_variado(n, 1015.0))
        validos = ("valido_T", "valido_Td", "valido_HR", "valido_viento", "valido_p")
        t = _qc(U, e, **todo)
        self.assertTrue(all(t[c].all() for c in validos))                 # el caso aísla lo que dice
        t = _qc(U, e, info=_info(motivo="sin_z_s"), **todo)
        for c in validos:
            self.assertFalse(t[c].any(), c)
        self.assertFalse(_tiene(t, "Ts", Marca.SIN_COORDENADAS).any())   # coordenadas confirmadas, pero fuera
        num, den = Q.conteos_estacion(t, _info(motivo="sin_z_s"))
        self.assertEqual(int(den.loc[(den.clave == Q.DEN_Q1) & (den.variable == "Ts"), "n"].sum()), n)

    def test_colision_utc_y_sin_reloj(self):
        """QC-6: dos etiquetas con la misma hora UTC quedan fuera de la tabla ancha y se cuentan; sin reloj, sin h."""
        U = _umbrales(self)
        a = larga_a_mano(U, [pd.Timestamp("2010-01-31T22:00"), pd.Timestamp("2010-01-31T23:00")],
                         Ts=np.array([15.0, 15.1]), id_artefacto=0)
        b = larga_a_mano(U, [pd.Timestamp("2010-02-01T00:00"), pd.Timestamp("2010-02-01T01:00")],
                         Ts=np.array([15.2, 15.3]), minutos=UTC_MENOS_3, id_artefacto=1)
        c = larga_a_mano(U, [pd.Timestamp("2010-02-01T02:00")], Ts=np.array([15.4]), reloj=False, id_artefacto=1)
        pols = [_politica_a_mano(U, CODIGO, "2010-01-31T22:00:00", "2010-02-01T02:00:00")]
        t = Q.qc_meteo_combinada(pd.concat([a, b, c], ignore_index=True), _info(), None, U, k2=frozenset(),
                                 politicas=pols)
        ancha = Q.tabla_ancha(t)
        self.assertEqual(list(ancha["ts_fuente"]), ["2010-01-31T22:00:00", "2010-02-01T01:00:00"])
        num, den = Q.conteos_estacion(t, _info())
        self.assertEqual(int(num.loc[(num.clave == Q.NUM_COLISION) & (num.variable == "Ts"), "n"].sum()), 2)
        sin_reloj = num[(num.clave == Q.clave_marca(Marca.SIN_RELOJ)) & (num.variable == "Ts")]
        self.assertEqual((int(sin_reloj["n"].sum()), list(sin_reloj["anio"])), (1, [2010]))
        self.assertEqual(int(den.loc[(den.clave == Q.DEN_HORAS) & (den.variable == "Ts"), "n"].sum()), 5)

    def test_conteos_d11_viento_y_lista(self):
        """D11 y D21: 11, 12 y la racha del viento en FF y DD; el pico de la rapidez sólo en FF; lista descriptiva."""
        U = _umbrales(self)
        n = 48
        t = _qc(U, _etiquetas(n), FF=0, DD=(np.arange(n) % 35 + 1) * 10.0)      # calma persistente
        num, den = Q.conteos_estacion(t, _info())
        q12 = num[num.clave == Q.clave_q1(Marca.CALMA_PERSISTENTE)]
        self.assertEqual(dict(zip(q12.variable, q12.n)), {"wind_speed_instant": n, "wind_direction_instant": n})
        lista = Q.lista_descriptiva(num, den, U)
        self.assertEqual(lista, [{"codigo": CODIGO, "variables": ["wind_speed_instant", "wind_direction_instant"]}])
        # «Más del 30 %»: una racha de 12 de 40 horas (30 %) no entra; de 13 (32,5 %), sí.
        for k, entra in ((12, False), (13, True)):
            with self.subTest(racha=k):
                ts = np.r_[np.full(k, 15.0), _variado(40 - k, 16.0)]
                t = _qc(U, _etiquetas(40), Ts=ts)
                num, den = Q.conteos_estacion(t, _info())
                self.assertEqual(int(_tiene(t, "Ts", Marca.RACHA).sum()), k)
                self.assertEqual(Q.lista_descriptiva(num, den, U), [{"codigo": CODIGO, "variables": ["Ts"]}] if entra
                                 else [])
        t = _qc(U, _etiquetas(5), Ts=_variado(5, 20.0), FF=np.array([5, 6, 40, 6, 7]), DD=(np.arange(5) + 1) * 10.0)
        num, _ = Q.conteos_estacion(t, _info())
        q6 = num[num.clave == Q.clave_q1(Marca.PICO_O_SALTO)]
        self.assertEqual(dict(zip(q6.variable, q6.n)), {"wind_speed_instant": 1})


if __name__ == "__main__":
    unittest.main()
