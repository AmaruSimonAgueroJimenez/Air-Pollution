"""Pruebas de salidas.py (tablas e informe de §7.4, artefactos evaluados, expedientes, privacidad y sello).

Las que llevan «pNN» son el punto NN de §8 (grupos A, B y C). El resultado de la red se arma a mano con las
firmas del Anexo F del diseño (ResultadoRed, EvidenciaEstacion, DecisionAnio, Tramo…), así que no depende de
que orquestacion ya funcione. Ningún dato es real y todo se escribe en carpetas temporales. Correr desde
scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .
"""
import sys

sys.dont_write_bytecode = True

import contextlib  # noqa: E402
import gzip  # noqa: E402
from collections import Counter  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
import warnings  # noqa: E402
from dataclasses import dataclass, field, replace  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from reloj_dmc import constantes, decision, entorno, extraccion, fijados, politica, red, salidas, tablas, umbrales  # noqa: E402
from reloj_dmc.tipos import (ESQUEMA_ESTACIONES, ESQUEMA_ESTADOS, ESQUEMA_EVENTOS, ESQUEMA_EXTRACTO_HORA,  # noqa: E402
                             ESQUEMA_GUARDAS, ESQUEMA_HORAS, ESQUEMA_MARCAS, ESQUEMA_MES, ESQUEMA_METRICAS_E2,
                             ESQUEMA_METRICAS_E3, ESQUEMA_METRICAS_E4, ESQUEMA_RACHAS, Conjunto, ConsecuenciasRed,
                             DecisionAnio, Estado, EvidenciaEstacion, InfoEstacion, ModoE3t, MotivoAnio, Territorio,
                             Tramo, Veredicto, tabla_vacia)

C, I = str(Estado.COMPATIBLE), str(Estado.INCOMPATIBLE)
F0, F3, F4, CS = "F(0)", "F(-3)", "F(-4)", "C(Santiago)"
P_CONT = (F0, F3, F4, CS)
SOLO_F0 = {F0: C, F3: I, F4: I, CS: I}
SEMILLA = 20261022        # la de U.f("SEMILLA") (Anexo B); test_semilla_es_la_del_anexo_b lo comprueba
N_CONTROL = constantes.valor("EXPEDIENTES_CONTROL_N")
PALABRAS_DE_VEREDICTO = ("confirmad", "discrepante", "insuficiente", "sin_confirmar", "F(0)", "C(Santiago)")
_APH = Path(umbrales.__file__).resolve().parents[2].parent / "Air-Pollution-Health-Chile"


@dataclass
class ResultadoRedSintetico:
    """Mismos campos que orquestacion.ResultadoRed (Anexo F)."""
    evidencias: list
    consecuencias: ConsecuenciasRed
    controles: dict
    decisiones: list
    decisiones_e3t_restringida: list | None
    rachas: pd.DataFrame
    meses_con_regla: dict
    tramos: dict
    politica: dict | None
    descripcion_red: dict
    predicciones: dict
    no_normalizables: list = field(default_factory=list)
    estaciones: dict = field(default_factory=dict)      # agregado de orquestacion (ORQ-7), sin «tramos»
    estados_reglas_vencidas: pd.DataFrame | None = None  # agregado de orquestacion (ORQ-3), ESQUEMA_ESTADOS


# ---------------------------------------------------------------------------------------------
# Constructores del resultado sintético
def _sha(texto):
    return entorno.sha256_bytes(texto.encode("utf-8"))


def _tabla(filas, esquema):
    return pd.DataFrame(filas, columns=list(esquema)).astype(esquema) if filas else tabla_vacia(esquema)


def _info(codigo, conjunto, *, tipo=None, propietario=None, inconsistentes=False, nombre=None):
    return InfoEstacion(codigo=codigo, nombre=nombre or f"sintetica {codigo}", lat=-33.4, lon=-70.6, alt_m=500.0,
                        coordenadas_validas=True, coordenadas_inconsistentes=inconsistentes,
                        territorio=Territorio.CONTINENTAL, region=13, macrozona="centro", zs=("America/Santiago",),
                        P=tablas.hipotesis_de_P(P_CONT), pixel_id=101, distancia_km=1.2, costera=False, z_pix=480.0,
                        dz=20.0, conjunto=conjunto, tipo=tipo, propietario=propietario)


def _r(c0):
    return [0.6 - 0.03 * abs(c - c0) for c in range(-9, 10)]


PARTES_DEL_ANIO = ((1, "R0"), (7, "R1"))


def _metricas(codigo, anios):
    e2, e3, e4 = [], [], []
    for anio in anios:
        for mes, reg in PARTES_DEL_ANIO:
            parte = f"{anio}-{mes:02d}-1"
            e2.append({"codigo": codigo, "anio": anio, "nivel": "parte", "unidad": parte, "regimen": reg, "n_rr": 120,
                       "frac_observador": 0.9, "valida": True, "informativa": True, "j_estrella": 0, "kappa3": 0.97,
                       "n_tx": 30, "kappa3_tx": 0.95, "j_tx": 0, "hora_modal_tx": 18, "n_tn": 30, "kappa3_tn": 0.95,
                       "j_tn": 0, "hora_modal_tn": 6})
            for variable in ("Ts", "QFE"):
                qfe = variable == "QFE"
                for nivel, unidad in (("parte", parte), ("regimen", reg)):
                    e3.append({"codigo": codigo, "anio": anio, "nivel": nivel, "unidad": unidad, "regimen": reg,
                               "variable": variable, "paso_h": 1, "n_pares": 700, "n_bloques": 6, "r": _r(0),
                               "c_hat": 0, "c_hat_cont": 0.1, "estab_c_hat": 0.99, "r_f": _r(0) if qfe else None,
                               "c_hat_f": 0 if qfe else None, "c_hat_f_cont": 0.05 if qfe else np.nan,
                               "estab_c_hat_f": 0.98 if qfe else np.nan, "fino": False, "filtro_e3t": not qfe,
                               "cociente_a1": 1.1, "r_diaria": 0.9})
            e4.append({"codigo": codigo, "anio": anio, "nivel": "parte", "unidad": parte, "regimen": reg,
                       "variable": "QFE", "paso_h": 1, "n_h": 24, "hueco_max_h": 1, "K": 3, "A1": 0.5, "EE_A1": 0.05,
                       "phi1": 4.0, "A2": 0.8, "EE_A2": 0.04, "psi2": 9.8})
    return (_tabla(e2, ESQUEMA_METRICAS_E2), _tabla(e3, ESQUEMA_METRICAS_E3), _tabla(e4, ESQUEMA_METRICAS_E4))


def _estados(codigo, por_anio, *, discordante=None):
    filas = []
    for anio, por_h in por_anio.items():
        for mes, _ in PARTES_DEL_ANIO:
            parte = f"{anio}-{mes:02d}-1"
            for linea, regla in (("E2", "unica"), ("E3p", "gruesa")):
                for h, e in por_h.items():
                    filas.append({"codigo": codigo, "anio": anio, "linea": linea, "regla": regla, "nivel": "parte",
                                  "unidad": parte, "H": h, "estado": e, "reloj_anomalo": False,
                                  "discordante": parte == discordante and linea == "E2", "motivo": None})
        for linea in ("E2", "E3p", "E4p"):
            for h, e in por_h.items():
                filas.append({"codigo": codigo, "anio": anio, "linea": linea, "regla": "unica", "nivel": "anio",
                              "unidad": str(anio), "H": h, "estado": e, "reloj_anomalo": False, "discordante": False,
                              "motivo": None})
    return _tabla(filas, ESQUEMA_ESTADOS)


def _eventos(codigo):
    base = {"codigo": codigo, "linea": "E1a", "zona": "America/Santiago", "anio": 2019, "p14": 0.9, "pdom": 0.95,
            "p": 0.92, "delta_s": None, "delta_e": None, "delta": None, "casillas": None, "esperadas": None}
    filas = [{**base, "tipo": "atraso", "clase_evento": "real", "fecha_D": "2019-04-07",
              "etiqueta": "2019-04-06T23:00:00", "resultado": "ausente"},
             {**base, "tipo": "adelanto", "clase_evento": "real", "fecha_D": "2019-09-08",
              "etiqueta": "2019-09-08T00:00:00", "resultado": "presente"},
             {**base, "tipo": "adelanto", "clase_evento": "placebo_semana", "fecha_D": "2019-10-06",
              "etiqueta": "2019-10-06T00:00:00", "resultado": "presente"}]
    return _tabla(filas, ESQUEMA_EVENTOS)


def _meses(codigo, anios):
    filas = []
    for anio in anios:
        for mes in range(1, 13):
            texto = f"{anio}-{mes:02d}"
            filas.append({"codigo": codigo, "anio": anio, "mes": mes,
                          "manifiesto": f"DMC/estaciones/{codigo}/{texto}.manifest.json",
                          "manifiesto_sha256": _sha(f"manifiesto {codigo} {texto}"),
                          "artefacto_sha256": _sha(f"artefacto {codigo} {texto}"), "id_artefacto": None,
                          "script_sha256": _sha("descargador fc1f1bb6"), "entra": True, "motivo_exclusion": None,
                          "row_count": 744, "source_empty_slots": 0, "expected_hour_slots": 744,
                          "n_available_hours": 744, "duplicate_display_rows_removed": 0,
                          "source_sha256": _sha(f"fuente {codigo} {texto}"), "requested_start": None,
                          "requested_end": None, "campos_faltantes": [], "p_ts": 1, "p_qfe": 1, "lat_txt": "-33.4",
                          "lon_txt": "-70.6", "alt_txt": "500"})
    if filas:
        filas[0]["campos_faltantes"] = ["source_empty_slots"]
    previo = min(anios) - 1     # meses excluidos fuera de los años con datos: un manifiesto por mes, como extraccion
    excluidos = [(f"{previo}-11", "pending"), (f"{previo}-12", "version_no_admitida")]
    for texto, motivo in excluidos:
        a, m = (int(x) for x in texto.split("-"))
        filas.append({**filas[-1], "anio": a, "mes": m, "manifiesto": f"DMC/estaciones/{codigo}/{texto}.manifest.json",
                      "artefacto_sha256": None, "entra": False, "motivo_exclusion": motivo, "campos_faltantes": []})
    return filas


CODIGO_SIN_EVALUAR = "330024"
EXCLUIDOS_SIN_EVALUAR = ((1, "version_no_admitida"), (2, "version_no_admitida"), (3, "version_no_admitida"),
                         (4, "pending"), (5, "pending"))


def _meses_sin_evaluar(codigo):
    """Una estación sin ningún mes evaluado: no llega a las evidencias (ORQ-1), pero sus meses están en la
    tabla de extraccion.leer_meses."""
    base = _meses(codigo, [2019])[0]
    filas = []
    for mes, motivo in EXCLUIDOS_SIN_EVALUAR:
        texto = f"2019-{mes:02d}"
        filas.append({**base, "mes": mes, "manifiesto": f"DMC/estaciones/{codigo}/{texto}.manifest.json",
                      "manifiesto_sha256": _sha(f"manifiesto {codigo} {texto}"), "artefacto_sha256": None,
                      "id_artefacto": None, "entra": False, "motivo_exclusion": motivo, "campos_faltantes": []})
    return _tabla(filas, ESQUEMA_MES)


def meses_completos(resultado):
    """La tabla completa de meses (como extraccion.leer_meses): la de cada evidencia y la de 330024."""
    return pd.concat([ev.meses for ev in resultado.evidencias] + [_meses_sin_evaluar(CODIGO_SIN_EVALUAR)],
                     ignore_index=True)


def _horas(codigo, anios):
    return _tabla([{"codigo": codigo, "anio": a, "mes": m, "horas_ts_o_qfe": 744} for a in anios for m in range(1, 13)],
                  ESQUEMA_HORAS)


def _evidencia(info, anios, por_anio, *, discordante=None):
    m2, m3, m4 = _metricas(info.codigo, anios)
    guardas = _tabla([{"codigo": info.codigo, "anio": a, "guarda": "E3d", "H": F0, "unidad": str(a), "resultado": "pasa",
                       "detalle": None} for a in anios], ESQUEMA_GUARDAS)
    marcas = _tabla([{"codigo": info.codigo, "anio": anios[0], "marca": "desfase_termico_local", "H": "*",
                      "valor": None}], ESQUEMA_MARCAS)
    return EvidenciaEstacion(info=info, estados=_estados(info.codigo, por_anio, discordante=discordante),
                             metricas_e2=m2, metricas_e3=m3, metricas_e4=m4, eventos=_eventos(info.codigo),
                             guardas=guardas, marcas=marcas, meses=None, horas=_horas(info.codigo, anios))


def _decision(codigo, anio, veredicto, *, motivo=None, clase=None, K=(), detalle=None):
    confirmado = veredicto == Veredicto.CONFIRMADO
    meses = tuple(f"{anio}-{m:02d}" for m in range(1, 13))
    return DecisionAnio(codigo=codigo, anio=anio, P=P_CONT, clases=P_CONT,
                        excluidas={F3: ("E2", "E3p"), F4: ("E3p",), CS: ("E2",)} if confirmado else {F0: ("E2",)},
                        K=K, veredicto=veredicto, motivo=motivo, detalle=detalle, clase_confirmada=clase,
                        lineas_apoyo=("E2", "E3p", "E4p") if confirmado else (),
                        familias_apoyo=("registro", "presion_reanalisis", "presion_marea") if confirmado else (),
                        n_lineas_q=2 if confirmado else 0, meses_con_apoyo=meses[:2] if confirmado else (),
                        meses_con_datos=meses, partes_discordantes=(),
                        guardas={"G-version": "pasa", "E3d": "pasa"} if confirmado else {"G-version": "pasa"},
                        marcas={"posible_media_horaria": False}, reglas_vencidas=False, modo_e3t=ModoE3t.RESTRINGIDO)


def _meses_texto(desde, hasta):
    return tuple(str(p) for p in pd.period_range(desde, hasta, freq="M"))


def _huellas_politica(informe="informe de la fase 10", artefactos="artefactos de la fase 10"):
    return politica.HuellasPolitica(
        protocolo_sha256=_sha("protocolo v1.0.1"), commit_ap="0123456789abcdef0123456789abcdef01234567",
        configuracion_sha256=_sha("reloj_dmc_v1.json"), informe_sha256=_sha(informe),
        artefactos_evaluados_sha256=_sha(artefactos), adaptador_sha256=fijados.SHA_ADAPTADOR, python="3.11.16",
        tzdata="2026c", transiciones_sha256=tablas.SHA_ANEXO_A)


def _controles():
    m3 = _tabla([{"codigo": "330020", "anio": 2019, "regimen": "R0", "macrozona": "centro", "c_f_cont": 0.05,
                  "c_s2_cont": 0.1, "D": -0.05}], red.ESQUEMA_MUESTRA_A3)
    m5 = _tabla([{"codigo": "330020", "anio": 2019, "regimen": "R0", "macrozona": "centro", "tipo": "sin_dato",
                  "propietario": "sin_dato", "c_f_cont": 0.05}], red.ESQUEMA_MUESTRA_A5)
    cal = _tabla([{"codigo": "330020", "anio": 2019, "macrozona": "centro", "H": F0, "n_regimenes": 2, "delta_t": 0.4,
                   "deltas_R": [0.3, 0.5], "tp": "pasa", "motivo": None, "fuera": False}], salidas.ESQUEMA_CALIBRACION_CSV)
    gdup = _tabla([{"archivo": "stdout_20261020.log", "codigo": "330020", "mes": "2019-04",
                    "url": "https://climatologia.meteochile.gob.cl/application/servicios/hojaMensualDatos/330020/2019/4",
                    "atraso_en_zs": True, "zonas_con_atraso": "America/Santiago"}], red.ESQUEMA_GDUP)
    return {"A1": red.ResultadoControl("A1", True, {"c2_cumplida": True, "meses_controlados": 24}),
            "A2": red.a2(tablas.SHA_ANEXO_A, tablas.SHA_ANEXO_A2, tablas.SHA_ANEXO_A3),
            "A3": {"pais": {"n": 1, "evaluado": False}}, "A4": {"evaluados": 4, "fallan": 0, "restringe_e3t": False},
            "A5": {"n": 1, "alto": False}, "A6": [], "G-dup": gdup,
            "calibracion_e3t": {"modos": {"centro": "restringido"}},
            "tablas": {"muestra_a3": m3, "muestra_a5": m5, "calibracion_e3t": cal}}


def resultado_sintetico():
    """Cuatro estaciones: 330020 confirmada F(0) en 2019-2020; 330021 con 2019 discrepante y 2020
    insuficiente; 330022 insuficiente; 330023 con 2018 discrepante y 2019 confirmado."""
    infos = {"330020": _info("330020", Conjunto.N), "330021": _info("330021", Conjunto.V, inconsistentes=True),
             "330022": _info("330022", Conjunto.V2, tipo="sinoptica", propietario="DMC"),
             "330023": _info("330023", Conjunto.N)}
    anios = {"330020": [2019, 2020], "330021": [2019, 2020], "330022": [2019], "330023": [2018, 2019]}
    evidencias = []
    for codigo, info in infos.items():
        ev = _evidencia(info, anios[codigo], {a: SOLO_F0 for a in anios[codigo]},
                        discordante="2019-07-1" if codigo == "330021" else None)
        ev.meses = _tabla(_meses(codigo, anios[codigo]), ESQUEMA_MES)
        evidencias.append(ev)
    id_ = 0
    for ev in evidencias:      # id_artefacto en orden de código y mes, como extraccion
        ids = []
        for entra in ev.meses["entra"]:
            ids.append(id_ if entra else None)
            id_ += bool(entra)
        ev.meses["id_artefacto"] = pd.array(ids, dtype="Int32")
    V = Veredicto
    decisiones = [_decision("330020", 2019, V.CONFIRMADO, clase=F0, K=(F0,)),
                  _decision("330020", 2020, V.CONFIRMADO, clase=F0, K=(F0,)),
                  _decision("330021", 2019, V.DISCREPANTE, motivo=MotivoAnio.LINEAS_EN_CONFLICTO,
                            detalle="F(0): E2; F(-3): E2, E3p"),
                  _decision("330021", 2020, V.INSUFICIENTE, motivo=MotivoAnio.NO_DISTINGUE, K=(F0, F3)),
                  _decision("330022", 2019, V.INSUFICIENTE, motivo=MotivoAnio.APOYO, K=(F0,)),
                  _decision("330023", 2018, V.DISCREPANTE, motivo=MotivoAnio.RELOJ_ANOMALO),
                  _decision("330023", 2019, V.CONFIRMADO, clase=F0, K=(F0,))]
    restringidas = [replace(d) for d in decisiones]
    restringidas[1] = replace(restringidas[1], veredicto=V.INSUFICIENTE, motivo=MotivoAnio.APOYO, clase_confirmada=None)
    rachas = _tabla([{"codigo": "330020", "racha": 1, "anio_desde": 2019, "anio_hasta": 2020, "clase": F0,
                      "n_confirmados": 2, "aceptada": True, "motivo": None},
                     {"codigo": "330023", "racha": 1, "anio_desde": 2019, "anio_hasta": 2019, "clase": F0,
                      "n_confirmados": 1, "aceptada": True, "motivo": None}], ESQUEMA_RACHAS)
    meses_20 = _meses_texto("2019-01", "2020-12")
    meses_23 = _meses_texto("2019-02", "2019-12")
    tramos = {"330020": [Tramo("330020", "1.1", datetime(2019, 1, 1, 0), datetime(2020, 12, 31, 23), 0, F0, meses_20)],
              "330023": [Tramo("330023", "1.1", datetime(2019, 2, 1, 0), datetime(2019, 12, 31, 23), 0, F0, meses_23)]}
    marcas = {"posible_media_horaria": False, "reloj_no_verificado": []}
    estaciones = {"330020": {"veredicto": "confirmada", "reloj": F0, "conjunto": "N", "marcas": marcas},
                  "330021": {"veredicto": "sin_confirmar", "motivo": "discrepante", "detalle": "2019 discrepante",
                             "conjunto": "V"},
                  "330022": {"veredicto": "sin_confirmar", "motivo": "insuficiente", "detalle": "apoyo",
                             "conjunto": "V2"},
                  "330023": {"veredicto": "confirmada", "reloj": F0, "conjunto": "N", "marcas": marcas}}
    pol = politica.politica(tramos, estaciones, _huellas_politica())
    estaciones_orq = {c: dict(e) for c, e in estaciones.items()}
    consecuencias = ConsecuenciasRed(a3_falla_pais=False, a3_fallan_macrozonas=frozenset(), a5_alto=False,
                                     modo_e3t={"centro": ModoE3t.RESTRINGIDO}, a4_restringe=False)
    return ResultadoRedSintetico(
        evidencias=evidencias, consecuencias=consecuencias, controles=_controles(), decisiones=decisiones,
        decisiones_e3t_restringida=restringidas, rachas=rachas,
        meses_con_regla={"330020": {m: F0 for m in meses_20}, "330023": {m: F0 for m in meses_23}},
        tramos=tramos, politica=pol, descripcion_red={"aplica": False, "n_estaciones_con_datos": 2, "red_en_utc": False},
        predicciones={}, estaciones=estaciones_orq)


def artefactos_de(resultado):
    salida = []
    for ev in resultado.evidencias:
        m = ev.meses[ev.meses["entra"]]
        for f in m.itertuples(index=False):
            salida.append({"id_artefacto": int(f.id_artefacto), "codigo": f.codigo, "anio": int(f.anio), "mes": int(f.mes),
                           "manifiesto": f.manifiesto, "manifiesto_sha256": f.manifiesto_sha256,
                           "artefacto": f.manifiesto.replace(".manifest.json", ".json.gz"),
                           "artefacto_sha256": f.artefacto_sha256, "row_count": int(f.row_count),
                           "script_sha256": f.script_sha256})
    return salida


def huellas_entrada():
    return {"protocolo": {"ruta": "APH/auditoria/20261023/reloj_dmc/enmienda1/PROTOCOLO_RELOJ_DMC_v1.0.1.md",
                          "sha256": _sha("protocolo v1.0.1")},
            "configuracion": {"ruta": "AP/config/meteorologia/reloj_dmc_v1.json", "sha256": _sha("reloj_dmc_v1.json")},
            "codigo": {"salidas.py": _sha("salidas"), "politica.py": _sha("politica")},
            "adaptador": {"sha256": fijados.SHA_ADAPTADOR},
            "interprete": {"python": "3.11.16", "tzdata": "2026.3", "iana": "2026c"},
            "anexo_a": {"sha256": tablas.SHA_ANEXO_A}, "anexo_a2": {"sha256": tablas.SHA_ANEXO_A2},
            "manifiestos": {"huella_agregada": _sha("manifiestos"), "n": 56},
            "progreso": {"ruta": "LOCAL/evidencia_vista/reloj_dmc/c2/progreso.json", "sha256": _sha("progreso")},
            "catalogo_dmc": {"ruta": "LOCAL/evidencia_vista/reloj_dmc/c2/catalogo_dmc.html", "sha256": _sha("catalogo")},
            "era5l": {"201901": _sha("era5 201901")},
            "copias_c2": {"LOCAL/evidencia_vista/reloj_dmc/c2/stdout_20261020.log": _sha("bitacora")}}


TABLAS_FALSAS = {n: _sha(n) for n in salidas.TABLAS}


def leer_extracto(codigo):
    """Extracto horario sintético 2018-2020 (ESQUEMA_EXTRACTO_HORA), con marcas cada 6 h."""
    L = pd.date_range("2018-01-01", "2020-12-31 23:00", freq="h")
    rng = np.random.default_rng(int(codigo))
    h = L.hour.to_numpy()
    ts = 15 + 8 * np.sin(2 * np.pi * (h - 9) / 24) + rng.normal(0, 0.5, len(L))
    qfe = 950 + 0.8 * np.cos(2 * np.pi * (h - 9.75) / 12) + rng.normal(0, 0.2, len(L))
    sinoptica = (h % 6) == 0
    datos = {"L": L.to_numpy(), "anio": L.year, "mes": L.month, "id_artefacto": np.zeros(len(L)), "medida": True,
             "ts": ts, "motivo_ts": 0, "qfe": qfe, "motivo_qfe": 0, "td": ts - 5, "hr": 60.0, "ff_kt": 5.0,
             "dd_grados": 180.0, "viento_valido": True, "qff_numerica": True, "rr": sinoptica, "tx": h == 18,
             "tn": h == 6, "observador": sinoptica, "huella": [_sha(f"{codigo}")] * len(L)}
    return pd.DataFrame(datos).astype(ESQUEMA_EXTRACTO_HORA)


class VerificadorFalso:
    """Hace de §7.3: relee la política provisional desde disco y devuelve fallas y no normalizables."""

    def __init__(self, fallas=(), no_normalizables=()):
        self.fallas, self.no_normalizables, self.rutas = list(fallas), list(no_normalizables), []

    def __call__(self, ruta):
        ruta = Path(ruta)
        self.rutas.append(ruta)
        json.loads(ruta.read_bytes())          # releída desde disco
        return list(self.fallas), list(self.no_normalizables)


NO_NORMALIZABLE = {"codigo": "330021", "manifiesto": "2020-03.manifest.json",
                   "artefacto_sha256": _sha("artefacto 330021 2020-03"),
                   "motivo": "lectura: [Errno 2] No such file: '/Volumes/Datos/x/2020-03.json.gz' (aviso a operador@dmc)"}


def correr(resultado, carpeta, *, verificar=None, n_control=N_CONTROL, huellas=True, **otros):
    """escribir_corrida con lo que pasaría el ejecutable en --aplicar (fuera del modo sintético); ``otros``
    reemplaza cualquier argumento."""
    kw = dict(artefactos=artefactos_de(resultado), huellas_entrada=huellas_entrada(),
              huellas_politica=_huellas_politica() if huellas else None, desviaciones=[], leer_extracto=leer_extracto,
              semilla=SEMILLA, n_control=n_control, verificar=verificar, meses=meses_completos(resultado))
    kw.update(otros)
    return salidas.escribir_corrida(resultado, carpeta, **kw)


_TMP = None
R = None
CORRIDA = None          # (carpeta, resumen, verificador)
CORRIDA_2 = None


def setUpModule():
    global _TMP, R, CORRIDA, CORRIDA_2
    _TMP = tempfile.TemporaryDirectory()
    R = resultado_sintetico()
    for nombre in ("a", "b"):     # mismo nombre de carpeta: el recibo lo lleva
        carpeta = Path(_TMP.name) / nombre / "HUMAN20261101_RELOJ_DMC_1"
        v = VerificadorFalso(no_normalizables=[NO_NORMALIZABLE])
        salida = (carpeta, correr(R, carpeta, verificar=v), v)
        if nombre == "a":
            CORRIDA = salida
        else:
            CORRIDA_2 = salida


def tearDownModule():
    if _TMP is not None:
        _TMP.cleanup()


def _titulos(texto):
    return [l for l in texto.splitlines() if l.startswith("#") and not l.startswith("# ")]


# ---------------------------------------------------------------------------------------------
class PruebasSalidas(unittest.TestCase):
    def test_p28_salidas_sin_users_ni_arroba(self):
        """Ningún archivo de texto contiene «/Users/» ni «@»."""
        carpeta = CORRIDA[0]
        self.assertEqual(salidas.verificar_privacidad(carpeta), [])
        for ruta in carpeta.rglob("*"):
            if ruta.suffix in salidas.EXTENSIONES_TEXTO:
                texto = ruta.read_text(encoding="utf-8")
                self.assertNotIn("/Users/", texto, ruta.name)
                self.assertNotIn("@", texto, ruta.name)
                self.assertNotIn(str(Path.home()), texto, ruta.name)
        # El motivo del no normalizable llega con una ruta y un correo: se redactan enteros (SAL-5).
        nn = (carpeta / "no_normalizables.csv").read_text(encoding="utf-8")
        self.assertIn("'<ruta>'", nn)
        self.assertIn("(aviso a <correo>)", nn)
        self.assertNotIn("/Volumes/", nn)
        self.assertNotIn("operador", nn)
        self.assertEqual(salidas.redactar(f"{Path.home()}/x y /Users/otro/z en a@b"), "<ruta> y <ruta> en <correo>")
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            # Un dato estructurado con «@» o «/Users/» no se escribe.
            ev = R.evidencias[0]
            malo = replace(R, evidencias=[replace(ev, info=replace(ev.info, nombre="correo@dominio"))] + R.evidencias[1:])
            with self.assertRaises(ValueError):
                salidas.escribir_tablas(malo, d / "malo")
            salidas.informe(R, TABLAS_FALSAS, huellas_entrada(), ["sin rutas"])     # el mismo informe, limpio, pasa
            with self.assertRaises(ValueError):
                salidas.informe(R, TABLAS_FALSAS, huellas_entrada(), ["/Users/alguien/x"])
            with self.assertRaises(ValueError):
                salidas.informe(R, TABLAS_FALSAS,
                                {**huellas_entrada(), "progreso": {"ruta": Path("/Users/alguien/progreso.json")}}, [])
            # verificar_privacidad encuentra un archivo plantado y sellar se niega.
            plantada = d / "plantada"
            (plantada / "sub").mkdir(parents=True)
            (plantada / "sub" / "nota.json").write_text('{"ruta": "/Users/alguien/x"}', encoding="utf-8")
            (plantada / "limpio.csv").write_text("a,b\n1,2\n", encoding="utf-8")
            (plantada / "datos.json.gz").write_bytes(gzip.compress(b'{"correo": "a@b"}', mtime=0))
            self.assertEqual(salidas.verificar_privacidad(plantada), ["datos.json.gz", "sub/nota.json"])
            with self.assertRaises(ValueError):
                salidas.sellar(plantada)
            self.assertFalse((plantada / salidas.RECIBO).exists())

    def test_tablas_de_7_4_con_sus_esquemas(self):
        """Nombres y columnas."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            huellas = salidas.escribir_tablas(R, d / "uno")
            self.assertEqual(tuple(huellas), salidas.TABLAS)
            self.assertEqual(salidas.TABLAS[:len(salidas.TABLAS_7_4)], salidas.TABLAS_7_4)
            for nombre, sha in huellas.items():
                self.assertEqual(entorno.sha256_archivo(d / "uno" / nombre), sha, nombre)
            # Deterministas: otra escritura da las mismas huellas.
            self.assertEqual(salidas.escribir_tablas(R, d / "dos"), huellas)
            base = d / "uno"
            pix = pd.read_parquet(base / "pixeles_dmc.parquet")
            self.assertEqual(list(pix.columns), list(ESQUEMA_ESTACIONES))
            self.assertEqual(list(pix["codigo"]), ["330020", "330021", "330022", "330023"])
            self.assertEqual(list(pix.loc[1, "P"]), list(P_CONT))
            self.assertTrue(bool(pix.loc[1, "coordenadas_inconsistentes"]))

            parte = pd.read_parquet(base / "evidencia_estacion_parte.parquet")
            self.assertEqual(list(parte.columns), list(salidas.ESQUEMA_EVIDENCIA_PARTE))
            self.assertEqual(len(parte), 2 * (2 + 2 + 1 + 2))       # dos partes por estación-año
            f = parte[(parte["codigo"] == "330021") & (parte["parte"] == "2019-07-1")].iloc[0]
            self.assertEqual(len(f["e3_r_ts"]), 19)
            self.assertEqual(len(f["e3_r_f_qfe"]), 19)
            self.assertTrue(pd.isna(f["e3_r_f_ts"]) if not isinstance(f["e3_r_f_ts"], np.ndarray) else False)
            self.assertAlmostEqual(f["e2_kappa3"], 0.97)
            self.assertAlmostEqual(f["e4_psi2_qfe"], 9.8)
            self.assertTrue(pd.isna(f["e4_psi2_ts"]))
            self.assertEqual(f["regimen"], "R1")
            self.assertTrue(bool(f["discordante"]))
            self.assertEqual(list(f["lineas_discordantes"]), ["E2"])
            estados = json.loads(f["estados"])
            self.assertEqual(estados["E2"], SOLO_F0)
            self.assertEqual(estados["E3p/gruesa"], SOLO_F0)

            anio = pd.read_parquet(base / "evidencia_estacion_anio.parquet")
            self.assertEqual(list(anio.columns), list(salidas.ESQUEMA_EVIDENCIA_ANIO))
            self.assertEqual(len(anio), len(R.decisiones))
            fila = anio[(anio["codigo"] == "330020") & (anio["anio"] == 2020)].iloc[0]
            self.assertEqual(fila["veredicto"], "confirmado")
            self.assertEqual(fila["veredicto_e3t_restringida"], "insuficiente")
            self.assertEqual(fila["conjunto"], "N")
            self.assertEqual(list(fila["versiones_descargador"]), [_sha("descargador fc1f1bb6")])
            self.assertEqual(json.loads(fila["estados"])["E4p"], SOLO_F0)
            self.assertEqual(json.loads(fila["excluidas"])[F3], ["E2", "E3p"])
            self.assertEqual(int(fila["n_meses_con_datos"]), 12)

            for nombre, esquema in (("eventos_transicion.csv", ESQUEMA_EVENTOS),
                                    ("calibracion_e3t.csv", salidas.ESQUEMA_CALIBRACION_CSV),
                                    ("no_normalizables.csv", salidas.ESQUEMA_NO_NORMALIZABLES)):
                encabezado = (base / nombre).read_text(encoding="utf-8").splitlines()[0]
                self.assertEqual(encabezado.split(","), list(esquema), nombre)
            cal = pd.read_csv(base / "calibracion_e3t.csv")
            self.assertEqual(json.loads(cal.loc[0, "deltas_R"]), [0.3, 0.5])
            self.assertEqual(len(pd.read_csv(base / "eventos_transicion.csv")), 3 * 4)

            ctrl = json.loads((base / "controles_red.json").read_bytes())
            self.assertEqual(ctrl["consecuencias"]["a5_alto"], False)
            self.assertEqual(ctrl["consecuencias"]["modo_e3t"], {"centro": "restringido"})
            self.assertTrue(ctrl["controles"]["A2"]["pasa"])
            self.assertEqual(ctrl["controles"]["tablas"]["muestra_a3"]["columnas"], list(red.ESQUEMA_MUESTRA_A3))
            self.assertEqual(len(ctrl["controles"]["tablas"]["muestra_a5"]["filas"]), 1)

            for nombre, esquema in (("rachas.parquet", ESQUEMA_RACHAS), ("estados_largos.parquet", ESQUEMA_ESTADOS)):
                df = pd.read_parquet(base / nombre)
                self.assertEqual(list(df.columns), list(esquema), nombre)
            self.assertEqual(len(pd.read_parquet(base / "estados_largos.parquet")),
                             sum(len(ev.estados) for ev in R.evidencias))
            # Un esquema que no calza se rechaza.
            malo = replace(R, rachas=R.rachas.drop(columns=["motivo"]))
            with self.assertRaises(ValueError):
                salidas.escribir_tablas(malo, d / "tres")

    def test_cadena_de_huellas(self):
        """tablas → informe → política → recibo."""
        carpeta, resumen, verificador = CORRIDA
        self.assertEqual(salidas.comprobar_cadena(carpeta), [])
        inf_bytes = (carpeta / salidas.ARCHIVO_INFORME).read_bytes()
        inf = json.loads(inf_bytes)
        sha_inf = entorno.sha256_bytes(inf_bytes)
        self.assertEqual(sha_inf, resumen[salidas.ARCHIVO_INFORME])
        for nombre in salidas.TABLAS:
            self.assertEqual(inf["tablas"][nombre], entorno.sha256_archivo(carpeta / nombre), nombre)
        self.assertEqual(inf["tablas"][salidas.CLAVE_EXPEDIENTES],
                         salidas.huella_carpeta(carpeta, salidas.CARPETA_EXPEDIENTES))
        sha_art = entorno.sha256_archivo(carpeta / salidas.ARCHIVO_ARTEFACTOS)
        self.assertEqual(inf["tablas"][salidas.ARCHIVO_ARTEFACTOS], sha_art)
        pol = json.loads((carpeta / salidas.ARCHIVO_POLITICA).read_bytes())
        self.assertEqual(pol["informe"]["sha256"], sha_inf)
        self.assertEqual(pol["artefactos_evaluados"]["sha256"], sha_art)
        self.assertTrue(all(f"sha256={sha_inf} " in r["clock"]["source"] for r in pol["politicas_reloj"]))
        # La política de la fase 10 no cambió de contenido (SAL-13).
        self.assertEqual(salidas.diferencias_salvo_informe(R.politica, {**pol, "artefactos_evaluados":
                                                                         R.politica["artefactos_evaluados"]}), [])
        recibo = json.loads((carpeta / salidas.RECIBO).read_bytes())
        self.assertEqual(recibo["total_sha256"], resumen["total_sha256"])
        self.assertEqual(recibo["total_sha256"], salidas.huella_agregada(recibo["archivos"]))
        for nombre in (*salidas.TABLAS, *salidas.INFORMES, salidas.ARCHIVO_POLITICA, salidas.ARCHIVO_ARTEFACTOS,
                       "expedientes/indice.json", "expedientes/330021.md"):
            self.assertEqual(recibo["archivos"][nombre], entorno.sha256_archivo(carpeta / nombre), nombre)
        self.assertNotIn(salidas.RECIBO, recibo["archivos"])
        # §7.3 corrió sobre la política provisional releída, que ya no está (SAL-2), y A7 entró al informe.
        self.assertEqual(len(verificador.rutas), 1)
        self.assertEqual(verificador.rutas[0].parent.name, salidas.CARPETA_PROVISIONAL)
        self.assertFalse((carpeta / salidas.CARPETA_PROVISIONAL).exists())
        self.assertIs(inf["controles"]["A7"]["pasa"], True)
        self.assertEqual(inf["no_normalizables"]["n"], 1)
        # validar_regla_reloj_dmc acepta la política y los artefactos escritos aquí (§7.3, §7.5).
        regla = pol["politicas_reloj"][0]
        politica.validar_regla_reloj_dmc(regla, _sha("artefacto 330020 2019-05"),
                                         politica_ruta=carpeta / salidas.ARCHIVO_POLITICA)
        with self.assertRaises(ValueError):
            politica.validar_regla_reloj_dmc(regla, _sha("artefacto que no se evaluó"),
                                             politica_ruta=carpeta / salidas.ARCHIVO_POLITICA)
        # El informe trae lo que pide §7.4; los meses excluidos, de la tabla completa (con 330024, SAL-9).
        self.assertFalse(inf["modo_sintetico"])
        self.assertEqual(inf["exclusiones"]["fuente"], salidas.FUENTE_EXTRACCION)
        self.assertEqual(inf["exclusiones"]["por_version"], {"version_no_admitida": 4 + 3})
        self.assertEqual(inf["exclusiones"]["por_estado"], {"pending": 4 + 2})
        self.assertEqual(inf["exclusiones"]["con_campos_faltantes"], {"meses": 4, "por_campo": {"source_empty_slots": 4}})
        self.assertEqual(inf["coordenadas_inconsistentes"], ["330021"])
        self.assertEqual(inf["estaciones"]["330020"]["tramos"][0]["id"], "1.1")
        self.assertEqual(inf["estaciones"]["330021"]["anios"]["2019"]["veredicto"], "discrepante")
        self.assertEqual(inf["conteos"]["estacion_anios"]["total"],
                         {"confirmado": 3, "discrepante": 2, "insuficiente": 2})
        self.assertEqual(inf["conteos"]["estaciones"]["por_conjunto"]["N"], {"confirmada": 2})
        self.assertIn("por_propietario", inf["conteos"]["estacion_anios"])
        self.assertEqual(len(inf["comparacion_e3t_restringida"]["cambian"]), 1)
        self.assertEqual(inf["controles"]["tablas"]["muestra_a3"], {"n_filas": 1, "en": "controles_red.json"})
        self.assertEqual(inf["controles"]["G-dup"]["columnas"], list(red.ESQUEMA_GDUP))
        self.assertEqual(inf["artefactos_evaluados"]["n"], len(artefactos_de(R)))
        self.assertEqual(inf["desviaciones"], [])
        # Un eslabón alterado rompe la cadena.
        with tempfile.TemporaryDirectory() as d:
            copia = Path(d) / "copia"
            shutil.copytree(carpeta, copia)
            (copia / "rachas.parquet").write_bytes((copia / "rachas.parquet").read_bytes() + b"\0")
            fallas = salidas.comprobar_cadena(copia)
            self.assertIn("cambió rachas.parquet", fallas)
            self.assertIn("rachas.parquet no tiene la huella que cita el informe", fallas)

    def test_expedientes_discrepantes_y_de_control(self):
        """Misma profundidad."""
        carpeta = CORRIDA[0]
        raiz = carpeta / salidas.CARPETA_EXPEDIENTES
        indice = json.loads((raiz / salidas.INDICE_EXPEDIENTES).read_bytes())
        self.assertEqual(indice["discrepancias"], ["330021", "330023"])
        self.assertEqual(indice["control"], decision.muestra_expedientes_control(["330020", "330023"], SEMILLA, N_CONTROL))
        self.assertEqual(sorted(p.name for p in raiz.glob("*.md")), ["330020.md", "330021.md", "330023.md"])
        textos = {c: (raiz / f"{c}.md").read_text(encoding="utf-8") for c in ("330020", "330021", "330023")}
        self.assertIn("Motivo de apertura: control", textos["330020"])
        self.assertIn("Motivo de apertura: discrepancia (años discrepantes: 2019)", textos["330021"])
        self.assertIn("discrepancia (años discrepantes: 2018); control", textos["330023"])
        # Misma profundidad: las mismas secciones y las mismas cinco figuras.
        titulos = {c: _titulos(t) for c, t in textos.items()}
        self.assertEqual(titulos["330020"], titulos["330021"])
        self.assertEqual(titulos["330020"], titulos["330023"])
        for codigo, texto in textos.items():
            for nombre in salidas.FIGURAS:
                self.assertIn(f"]({codigo}/{nombre}.png)", texto)
                png = (raiz / codigo / f"{nombre}.png").read_bytes()
                self.assertTrue(png.startswith(b"\x89PNG"), f"{codigo}/{nombre}")
        self.assertIn("| 2019 | E3p | compatible |", textos["330020"])
        # La muestra de control es la de decision con la semilla, también cuando hay más candidatas que n.
        abiertos = salidas.expedientes_a_abrir(R, SEMILLA, 1)
        self.assertEqual(abiertos["control"], decision.muestra_expedientes_control(["330020", "330023"], SEMILLA, 1))
        self.assertEqual(abiertos["candidatos_control"], 2)
        # Sin extracto ni eventos, las figuras dicen que faltan datos, pero están (misma profundidad).
        with tempfile.TemporaryDirectory() as d:
            rutas = salidas.expedientes(R, lambda c: None, Path(d), SEMILLA, 0)
            self.assertEqual(rutas, ["expedientes/330021.md", "expedientes/330023.md"])
            for nombre in salidas.FIGURAS:
                self.assertTrue((Path(d) / "expedientes" / "330021" / f"{nombre}.png").is_file())
            self.assertEqual(_titulos((Path(d) / "expedientes" / "330021.md").read_text(encoding="utf-8")),
                             titulos["330021"])

    def test_dos_corridas_iguales_dan_las_mismas_huellas(self):
        """Prueba 26 (parte de salidas): tablas, figuras, informe, política y recibo idénticos."""
        a, b = CORRIDA[1], CORRIDA_2[1]
        self.assertEqual(a, b)
        for ruta in sorted((CORRIDA[0] / salidas.CARPETA_EXPEDIENTES).rglob("*.png")):
            rel = ruta.relative_to(CORRIDA[0])
            self.assertEqual(ruta.read_bytes(), (CORRIDA_2[0] / rel).read_bytes(), str(rel))

    def test_artefactos_evaluados_json_gz(self):
        """Lista de objetos con artefacto_sha256 y codigo (la convención de politica); gzip con mtime 0."""
        artefactos = artefactos_de(R)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            sha = salidas.escribir_artefactos_evaluados(list(reversed(artefactos)), d / "a")
            self.assertEqual(salidas.escribir_artefactos_evaluados(artefactos, d / "b"), sha)
            datos = (d / "a" / salidas.ARCHIVO_ARTEFACTOS).read_bytes()
            self.assertEqual(entorno.sha256_bytes(datos), sha)
            self.assertEqual(datos[4:8], b"\0\0\0\0")      # mtime = 0
            texto = gzip.decompress(datos)
            lista = json.loads(texto)
            self.assertEqual(texto, entorno.json_canonico(lista))
            self.assertEqual([a["id_artefacto"] for a in lista], list(range(len(artefactos))))
            self.assertTrue(all({"artefacto_sha256", "codigo"} <= set(a) for a in lista))
            self.assertEqual(len(politica._artefactos_desde_json(lista)), len(artefactos))
            for malo in ({**artefactos[0], "veredicto": "confirmado"}, {"artefacto_sha256": artefactos[0]["artefacto_sha256"]},
                         {**artefactos[0], "artefacto_sha256": "abc"}, {**artefactos[0], "manifiesto": "/Volumes/x.json"}):
                with self.assertRaises(ValueError):
                    salidas.escribir_artefactos_evaluados([malo], d / "c")
            with self.assertRaises(ValueError):    # un mismo artefacto en dos estaciones
                salidas.escribir_artefactos_evaluados([artefactos[0], {**artefactos[0], "codigo": "999999",
                                                                       "id_artefacto": 99}], d / "c")

    def test_sello_recibo_corrida(self):
        """sha256 de cada archivo y total; no se sella dos veces ni con escrituras a medias."""
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "corrida"
            (c / "sub").mkdir(parents=True)
            (c / "a.txt").write_bytes(b"uno\n")
            (c / "sub" / "b.bin").write_bytes(b"\x00\x01")
            total = salidas.sellar(c)
            esperados = {"a.txt": entorno.sha256_bytes(b"uno\n"), "sub/b.bin": entorno.sha256_bytes(b"\x00\x01")}
            texto = "".join(f"{sha}  {ruta}\n" for ruta, sha in sorted(esperados.items()))
            self.assertEqual(total, entorno.sha256_bytes(texto.encode("utf-8")))
            recibo = json.loads((c / salidas.RECIBO).read_bytes())
            self.assertEqual(recibo["archivos"], esperados)
            self.assertEqual(recibo["carpeta"], "corrida")
            self.assertEqual(salidas.verificar_sello(c), [])
            with self.assertRaises(FileExistsError):
                salidas.sellar(c)
            (c / "a.txt").write_bytes(b"dos\n")
            (c / "nuevo.txt").write_bytes(b"x")
            self.assertEqual(salidas.verificar_sello(c), ["sobra nuevo.txt", "cambió a.txt"])
            otra = Path(d) / "otra"
            otra.mkdir()
            (otra / "tabla.parquet.part").write_bytes(b"a medias")
            with self.assertRaises(ValueError):
                salidas.sellar(otra)

    def test_a5_alto_sin_politica(self):
        """§5.4: con A5 alto se termina el informe y se sella, pero no se escribe la política ni corre §7.3."""
        # Sin «estaciones» de orquestacion, la entrada de cada estación se deriva de las decisiones (SAL-11).
        r = replace(R, politica=None, estaciones={}, consecuencias=replace(R.consecuencias, a5_alto=True))
        v = VerificadorFalso()
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "corrida"
            resumen = correr(r, c, verificar=v, n_control=0, huellas=False)
            self.assertIsNone(resumen[salidas.ARCHIVO_POLITICA])
            self.assertFalse((c / salidas.ARCHIVO_POLITICA).exists())
            self.assertEqual(v.rutas, [])
            self.assertEqual(salidas.comprobar_cadena(c), [])
            inf = json.loads((c / salidas.ARCHIVO_INFORME).read_bytes())
            self.assertFalse(inf["politica"]["se_escribe"])
            self.assertIsNone(inf["controles"]["A7"]["pasa"])
            e = inf["estaciones"]["330020"]
            self.assertEqual((e["veredicto"], e["reloj"], e["derivada_de_las_decisiones"]), ("confirmada", F0, True))
            self.assertEqual(inf["estaciones"]["330022"]["veredicto"], "sin_confirmar")
        # Con las «estaciones» de orquestacion (ORQ-7), el informe usa ésas.
        r2 = replace(r, estaciones=R.estaciones)
        inf2 = salidas.informe(r2, TABLAS_FALSAS, huellas_entrada(), [])
        self.assertEqual(inf2["estaciones"]["330021"]["motivo"], "discrepante")
        self.assertNotIn("derivada_de_las_decisiones", inf2["estaciones"]["330020"])
        self.assertIsNone(salidas.politica_de_la_corrida(r2, _huellas_politica()))

    def test_salidas_sin_veredictos_en_consola(self):
        """§5.2: nada se imprime y lo que se devuelve son huellas; A7 con fallas queda en el informe, redactado."""
        v = VerificadorFalso(fallas=["comprobación 3: 330020: _utc aborta con «/Users/alguien/x» (aviso a a@b)"])
        salida, errores = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(salida), \
                contextlib.redirect_stderr(errores), warnings.catch_warnings(record=True):
            c = Path(d) / "corrida"
            resumen = correr(R, c, verificar=v, n_control=0)
            inf = json.loads((c / salidas.ARCHIVO_INFORME).read_bytes())
        self.assertEqual(salida.getvalue(), "")
        self.assertFalse(any(p in errores.getvalue() for p in PALABRAS_DE_VEREDICTO), errores.getvalue())
        for clave, valor in resumen.items():
            self.assertTrue(valor is None or (isinstance(valor, str) and len(valor) == 64), clave)
        self.assertIs(inf["controles"]["A7"]["pasa"], False)
        self.assertEqual(inf["controles"]["A7"]["detalle"]["fallas"],
                         ["comprobación 3: 330020: _utc aborta con «<ruta>» (aviso a <correo>)"])

    def test_informe_exige_huellas_de_entrada_y_tablas(self):
        """SAL-14: claves obligatorias, sha256 de 64 hexadecimales, huellas de las nueve tablas."""
        tablas_ = dict(TABLAS_FALSAS)
        inf = salidas.informe(R, tablas_, huellas_entrada(), [])
        self.assertEqual(inf["schema"], salidas.ESQUEMA_INFORME)
        self.assertEqual(salidas.informe_md(inf), salidas.informe_md(json.loads(entorno.json_canonico(inf))))
        for clave in ("progreso", "anexo_a2"):
            h = huellas_entrada()
            del h[clave]
            with self.assertRaises(ValueError):
                salidas.informe(R, tablas_, h, [])
        with self.assertRaises(ValueError):
            salidas.informe(R, tablas_, {**huellas_entrada(), "anexo_a": {"sha256": "8ea58b78"}}, [])
        for tabla in ("rachas.parquet", salidas.TABLA_REGLAS_VENCIDAS):
            with self.assertRaises(ValueError):
                salidas.informe(R, {k: v for k, v in tablas_.items() if k != tabla}, huellas_entrada(), [])
        with self.assertRaises(ValueError):
            salidas.informe(R, tablas_, huellas_entrada(), "sin desviaciones")
        md = salidas.informe_md(salidas.informe(R, tablas_, huellas_entrada(), ["se corrió dos veces la fase 4"]))
        self.assertIn("- se corrió dos veces la fase 4", md)
        self.assertIn("| 330020 | N | confirmada | F(0) |", md)

    def test_politica_rehecha_conserva_el_contenido(self):
        """SAL-13: la política de la corrida es la de la fase 10 con otras huellas; si cambia, error."""
        nueva = salidas.politica_de_la_corrida(R, _huellas_politica(informe="otro informe"))
        self.assertEqual(salidas.diferencias_salvo_informe(R.politica, nueva), [])
        otra = salidas.politica_de_la_corrida(R, _huellas_politica(artefactos="otros artefactos"))
        self.assertEqual(salidas.diferencias_salvo_informe(R.politica, otra), ["artefactos_evaluados"])
        tramos = {**R.tramos, "330023": [replace(R.tramos["330023"][0], valid_to=datetime(2019, 11, 30, 23))]}
        with self.assertRaises(ValueError):
            salidas.politica_de_la_corrida(replace(R, tramos=tramos), _huellas_politica())
        a5 = replace(R, consecuencias=replace(R.consecuencias, a5_alto=True))
        self.assertIsNone(salidas.politica_de_la_corrida(a5, _huellas_politica()))
        # Si politica.politica rechaza las entradas, el mensaje no muestra veredictos (§5.2); el detalle se retiene.
        ajeno = {**R.tramos, "330021": [replace(R.tramos["330023"][0], codigo="330021")]}
        with self.assertRaises(salidas.ErrorRetenido) as error:
            salidas.politica_de_la_corrida(replace(R, politica=None, tramos=ajeno), _huellas_politica())
        self.assertFalse(any(p in str(error.exception) for p in ("330021", *PALABRAS_DE_VEREDICTO)), str(error.exception))
        self.assertIn("330021", error.exception.detalle)


    def test_politica_desde_estaciones_cuando_orquestacion_no_tiene_huellas(self):
        """ORQ-9: sin huellas, orquestacion deja la política en None (sin A5 alto); salidas la arma con
        ``estaciones`` y ``tramos``, igual a la que habría armado la fase 10."""
        r = replace(R, politica=None)
        nueva = salidas.politica_de_la_corrida(r, _huellas_politica())
        self.assertEqual(entorno.json_canonico(nueva), entorno.json_canonico(R.politica))
        with self.assertRaises(ValueError):
            salidas.politica_de_la_corrida(replace(r, estaciones={}), _huellas_politica())
        # Las marcas son las de la corrida (SAL-13): orquestacion las deja en falso.
        self.assertIs(salidas.politica_de_la_corrida(R, _huellas_politica(), post_hoc=True)["post_hoc"], True)
        self.assertIs(salidas.politica_de_la_corrida(r, _huellas_politica(), post_hoc=True)["post_hoc"], True)
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "corrida"
            v = VerificadorFalso()
            correr(r, c, verificar=v, n_control=0)
            self.assertEqual(len(v.rutas), 1)
            self.assertEqual(salidas.comprobar_cadena(c), [])
            pol = json.loads((c / salidas.ARCHIVO_POLITICA).read_bytes())
            self.assertEqual(salidas.diferencias_salvo_informe(R.politica, {**pol, "artefactos_evaluados":
                                                                             R.politica["artefactos_evaluados"]}), [])
            inf = json.loads((c / salidas.ARCHIVO_INFORME).read_bytes())
            self.assertEqual(inf["estaciones"]["330021"]["motivo"], "discrepante")

    def test_a7_de_orquestacion_se_redacta_y_la_comparacion_usa_5_1(self):
        """El A7 que deja orquestacion.comprobar_politica también se redacta; un año que §5.3 dejó sin
        confirmar cuenta como confirmado al compararlo con E3t restringida (ORQ-4)."""
        controles = {**R.controles, "A7": {"pasa": False, "fallas": ["comprobación 7: «/Users/alguien/x» de a@b"],
                                           "n": 1, "no_normalizables": 0}}
        inestable = replace(R.decisiones[0], veredicto=Veredicto.SIN_CONFIRMAR, motivo=MotivoAnio.INESTABLE)
        r = replace(R, controles=controles, decisiones=[inestable] + R.decisiones[1:])
        inf = salidas.informe(r, TABLAS_FALSAS, huellas_entrada(), [])
        self.assertEqual(inf["controles"]["A7"]["fallas"], ["comprobación 7: «<ruta>» de <correo>"])
        self.assertEqual(salidas.controles_red(r)["controles"]["A7"]["fallas"], inf["controles"]["A7"]["fallas"])
        cambian = {(c["codigo"], c["anio"]) for c in inf["comparacion_e3t_restringida"]["cambian"]}
        self.assertEqual(cambian, {("330020", 2020)})
        self.assertIn("| A7 | falla |", salidas.informe_md(inf))

    def test_campos_de_resultado_red_y_motivos_de_extraccion(self):
        """Lo que se lee de ResultadoRed y de los meses calza con orquestacion y extraccion (las claves de los
        artefactos se comparan con las que escribe extraccion en test_h8_…)."""
        self.assertLessEqual(set(salidas.CAMPOS_RESULTADO_RED), set(ResultadoRedSintetico.__dataclass_fields__))
        self.assertEqual(set(salidas.MOTIVOS_POR_ESTADO) | set(salidas.MOTIVOS_POR_VERSION) | {"artifact_name", "row_count"},
                         set(extraccion.MOTIVOS_EXCLUSION))
        try:
            from reloj_dmc import orquestacion
        except Exception as e:  # noqa: BLE001 - orquestacion se implementa en paralelo
            self.skipTest(f"orquestacion no importa todavía: {e}")
        campos = set(getattr(orquestacion.ResultadoRed, "__dataclass_fields__", {}))
        self.assertLessEqual(set(salidas.CAMPOS_RESULTADO_RED) | {"estaciones", "estados_reglas_vencidas"}, campos)

    # --- Hallazgos de la revisión independiente ------------------------------------------------------
    def test_h1_redactar_no_deja_el_correo_de_una_carpeta_de_google_drive(self):
        """SAL-5: la ruta va entera, antes que el correo; no queda ni el usuario ni el dominio (§7.4, §10)."""
        ruta = f"{Path.home()}/Library/CloudStorage/GoogleDrive-usuario.prueba@dominio.com/Mi unidad/AP/v3/x.py"
        textos = (f"no se pudo leer {ruta}: sin permiso", f"[Errno 2] No such file: '{ruta}'",
                  f"_utc aborta con «{ruta}»", f"ruta={ruta}", f'abrir "{ruta}"',
                  "~/Library/CloudStorage/GoogleDrive-usuario.prueba@dominio.com/Mi unidad/AP/v3/x.py",
                  "x/Users/usuario.prueba@dominio.com/y", "aviso a usuario.prueba@dominio.com.")
        for texto in textos:
            r = salidas.redactar(texto)
            for resto in ("usuario.prueba", "dominio", "@", "arroba", "GoogleDrive", "Library", "~/", "/Users/",
                          str(Path.home())):
                self.assertNotIn(resto, r, texto)
            self.assertTrue(entorno.sin_datos_privados(r), r)
        self.assertEqual(salidas.redactar(textos[0]), "no se pudo leer <ruta>: sin permiso")
        self.assertEqual(salidas.redactar(textos[1]), "[Errno 2] No such file: '<ruta>'")
        self.assertEqual(salidas.redactar(textos[2]), "_utc aborta con «<ruta>»")
        # Sin rutas ni correos, el texto no cambia (zonas, reglas, clases fusionadas y URL).
        for limpio in ("comprobación 5: 330020 tramo 1.1 con −240 sin F(-4); E3p/gruesa en America/Santiago",
                       "F(-3)|C(Santiago) en 2019/2020",
                       "https://climatologia.meteochile.gob.cl/application/servicios/hojaMensualDatos/330020/2019/4"):
            self.assertEqual(salidas.redactar(limpio), limpio)
        # Una corrida cuyo §7.3 falla con esa ruta, con un no normalizable que la trae: nada sellado la muestra.
        v = VerificadorFalso(fallas=[f"comprobación 3: _utc aborta al leer {ruta}"],
                             no_normalizables=[{**NO_NORMALIZABLE, "motivo": f"lectura: {ruta} ilegible"}])
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "corrida"
            correr(R, c, verificar=v, n_control=0)
            self.assertEqual(salidas.comprobar_cadena(c), [])
            for archivo in c.rglob("*"):
                if archivo.suffix in salidas.EXTENSIONES_TEXTO:
                    texto = archivo.read_text(encoding="utf-8")
                    for resto in ("usuario.prueba", "dominio.com", "GoogleDrive", "arroba"):
                        self.assertNotIn(resto, texto, archivo.name)
            inf = json.loads((c / salidas.ARCHIVO_INFORME).read_bytes())
            self.assertEqual(inf["controles"]["A7"]["detalle"]["fallas"], ["comprobación 3: _utc aborta al leer <ruta>"])
            self.assertEqual(list(pd.read_csv(c / "no_normalizables.csv")["motivo"]), ["lectura: <ruta> ilegible"])

    def test_h2_no_se_sella_una_politica_sin_7_3(self):
        """§5.2 (fase 10: política y comprobaciones de §7.3; fase 11: sello). Sin verificador, sólo en modo
        sintético explícito, que queda en el informe y en las desviaciones. A7 es siempre el de esta corrida."""
        a7_ajeno = {"pasa": True, "fallas": [], "n": 0, "no_normalizables": 1}   # de orquestacion, sobre otra política
        r = replace(R, controles={**R.controles, "A7": a7_ajeno}, no_normalizables=[NO_NORMALIZABLE])
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "corrida"
            with self.assertRaises(ValueError) as error:
                correr(r, c, n_control=0)
            self.assertIn("verificador de §7.3", str(error.exception))
            self.assertFalse(c.exists())            # no se escribió nada
            correr(r, c, n_control=0, modo_sintetico=True)
            self.assertEqual(salidas.comprobar_cadena(c), [])
            inf = json.loads((c / salidas.ARCHIVO_INFORME).read_bytes())
            self.assertIs(inf["modo_sintetico"], True)
            self.assertIsNone(inf["controles"]["A7"]["pasa"])
            self.assertEqual(inf["no_normalizables"]["n"], 0)
            self.assertEqual(inf["desviaciones"], [salidas.DESVIACION_SIN_7_3])
            self.assertIn("Modo sintético: sí.", (c / salidas.ARCHIVO_INFORME_MD).read_text(encoding="utf-8"))
            # Con verificador, el A7 que dejó orquestacion se reemplaza por el de la política de esta corrida.
            c2 = Path(d) / "corrida_2"
            correr(r, c2, n_control=0, verificar=VerificadorFalso(fallas=["comprobación 2: tramo fuera de regla"]))
            inf2 = json.loads((c2 / salidas.ARCHIVO_INFORME).read_bytes())
            self.assertIs(inf2["controles"]["A7"]["pasa"], False)
            self.assertEqual(inf2["no_normalizables"]["n"], 0)
            self.assertIs(inf2["modo_sintetico"], False)
            self.assertEqual(inf2["desviaciones"], [])

    def test_h3_sin_a1_a2_gdup_ni_entradas_no_se_sella_fuera_del_modo_sintetico(self):
        """§7.4 (A1 a A7, G-dup, progreso.json, catálogo y copias de C2 en el informe) y §10 (toda diferencia
        de procedimiento va a las desviaciones)."""
        sin = replace(R, controles={k: v for k, v in R.controles.items() if k not in ("A1", "A2", "G-dup")})
        h = {**huellas_entrada(), "progreso": None, "catalogo_dmc": None, "copias_c2": {}}
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "corrida"
            for r, kw, esperado in ((sin, {}, "A1"), (R, {"huellas_entrada": h}, "«progreso»")):
                with self.assertRaises(ValueError) as error:
                    correr(r, c, verificar=VerificadorFalso(), n_control=0, **kw)
                self.assertIn(esperado, str(error.exception))
                self.assertFalse(c.exists())
            # En modo sintético se sella, y cada faltante queda en las desviaciones.
            correr(sin, c, verificar=VerificadorFalso(), n_control=0, huellas_entrada=h, modo_sintetico=True)
            self.assertEqual(salidas.comprobar_cadena(c), [])
            inf = json.loads((c / salidas.ARCHIVO_INFORME).read_bytes())
            texto = "\n".join(inf["desviaciones"])
            for clave in ("de A1 ", "de A2 ", "de G-dup ", "«progreso»", "«catalogo_dmc»", "«copias_c2»"):
                self.assertIn(clave, texto)
            self.assertNotIn("de A7 ", texto)
            self.assertEqual(len(inf["desviaciones"]), 6)
            self.assertIn("| A1 | no informado |", (c / salidas.ARCHIVO_INFORME_MD).read_text(encoding="utf-8"))
        # informe() directo también las agrega, después de las del llamador (aquí falta además A7).
        inf = salidas.informe(sin, TABLAS_FALSAS, h, ["la del llamador"], meses=meses_completos(R))
        self.assertEqual(inf["desviaciones"][0], "la del llamador")
        self.assertEqual(len(inf["desviaciones"]), 1 + 4 + 3)
        self.assertEqual(salidas.informe(R, TABLAS_FALSAS, huellas_entrada(), ["x"], meses=meses_completos(R))
                         ["desviaciones"], ["x", "falta el resultado de A7 (§7.4: «Resultados de A1 a A7, de G-dup y "
                                                 "de la calibración»)"])

    def test_h4_meses_excluidos_de_una_estacion_sin_meses_evaluados(self):
        """§7.4: «Meses excluidos por versión, por estado o por campos faltantes», sobre todos los manifiestos;
        330024 no tiene ningún mes evaluado y no llega a las evidencias (ORQ-1)."""
        meses = meses_completos(R)
        self.assertNotIn(CODIGO_SIN_EVALUAR, {ev.info.codigo for ev in R.evidencias})
        x = salidas.informe(R, TABLAS_FALSAS, huellas_entrada(), [], meses=meses)["exclusiones"]
        self.assertEqual(x["fuente"], salidas.FUENTE_EXTRACCION)
        contados = Counter({**x["por_estado"], **x["por_version"], **x["otros"]})
        self.assertEqual(contados, Counter(str(m) for m in meses.loc[~meses["entra"], "motivo_exclusion"]))
        self.assertEqual(x["por_version"], {"version_no_admitida": 4 + 3})
        self.assertEqual(x["por_estado"], {"pending": 4 + 2})
        self.assertIn({"codigo": CODIGO_SIN_EVALUAR, "mes": "2019-01", "motivo": "version_no_admitida"},
                      x["meses_excluidos"])
        # Sin la tabla completa: sólo las evidencias, y queda en las desviaciones.
        sin = salidas.informe(R, TABLAS_FALSAS, huellas_entrada(), [])
        self.assertEqual(sin["exclusiones"]["fuente"], salidas.FUENTE_EVIDENCIAS)
        self.assertEqual(sin["exclusiones"]["por_version"], {"version_no_admitida": 4})
        self.assertIn(salidas.DESVIACION_SIN_MESES, sin["desviaciones"])
        # Una tabla que no trae los meses de las evidencias, o con otra admisión, se rechaza.
        otra = meses.copy()
        otra.loc[0, "entra"] = False
        otra.loc[0, "motivo_exclusion"] = "pending"
        for mala in (meses.iloc[1:].reset_index(drop=True), otra, pd.concat([meses, meses.iloc[:1]], ignore_index=True)):
            with self.assertRaises(ValueError):
                salidas.informe(R, TABLAS_FALSAS, huellas_entrada(), [], meses=mala)
        # escribir_corrida exige la tabla fuera del modo sintético, y que artefactos sean sus meses evaluados.
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "corrida"
            for kw in ({"meses": None}, {"artefactos": artefactos_de(R)[1:]}):
                with self.assertRaises(ValueError):
                    correr(R, c, verificar=VerificadorFalso(), n_control=0, **kw)
                self.assertFalse(c.exists())

    def test_h5_rutas_absolutas_fuera_de_users(self):
        """§7.4: «sin rutas absolutas, «/Users/» ni «@»»; los URL, los alias y las zonas no son rutas."""
        era5 = {"201901": {"ruta": "/Volumes/Datos/Asesorias_Data/era5land/era5l_201901.nc", "sha256": _sha("era5")}}
        for h in ({**huellas_entrada(), "era5l": era5}, {**huellas_entrada(), "nota": "copiada desde ~/c2/progreso.json"}):
            with self.assertRaises(ValueError):
                salidas.informe(R, TABLAS_FALSAS, h, [], meses=meses_completos(R))
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            with self.assertRaises(ValueError):
                correr(R, d / "corrida", verificar=VerificadorFalso(), n_control=0,
                       huellas_entrada={**huellas_entrada(), "era5l": era5})
            self.assertFalse((d / "corrida").exists())
            ev = R.evidencias[0]
            malo = replace(R, evidencias=[replace(ev, info=replace(ev.info, nombre="copia de /Volumes/Datos/x"))]
                           + R.evidencias[1:])
            with self.assertRaises(ValueError):
                salidas.escribir_tablas(malo, d / "tablas")
            plantada = d / "plantada"
            plantada.mkdir()
            (plantada / "nota.json").write_text('{"ruta": "/Volumes/Datos/x/2020-03.json.gz"}', encoding="utf-8")
            (plantada / "otra.txt").write_text("leído de ~/c2/progreso.json\n", encoding="utf-8")
            (plantada / "limpio.md").write_text(
                "E3p/gruesa en America/Santiago; DMC/estaciones/330020/2019-01.manifest.json; https://climatologia."
                "meteochile.gob.cl/application/servicios/hojaMensualDatos/330020/2019/4\n", encoding="utf-8")
            self.assertEqual(salidas.verificar_privacidad(plantada), ["nota.json", "otra.txt"])
            with self.assertRaises(ValueError):
                salidas.sellar(plantada)
        # No son rutas: zonas, reglas, alias, URL, clases fusionadas y un nombre con « /».
        limpio = {**huellas_entrada(), "nota": [
            "America/Santiago", "E3p/gruesa", "DMC/estaciones/330020/2019-01.manifest.json", "Arica /Chacalluta",
            "https://climatologia.meteochile.gob.cl/application/servicios/hojaMensualDatos/330020/2019/4",
            "F(-3)|C(Santiago)", "1/2", "a / b"]}
        salidas.informe(R, TABLAS_FALSAS, limpio, [], meses=meses_completos(R))
        self.assertEqual(salidas.verificar_privacidad(CORRIDA[0]), [])     # trae la url de G-dup

    def test_h6_errata_con_la_politica_de_orquestacion(self):
        """§10: una corrida _ERRATA<n> lleva errata_post_c4 aunque orquestacion haya armado la política con las
        marcas en falso; una marca que trae la fase 10 nunca se quita (SAL-13)."""
        nueva = salidas.politica_de_la_corrida(R, _huellas_politica(), errata_post_c4=True)
        self.assertIs(nueva["errata_post_c4"], True)
        self.assertIs(nueva["post_hoc"], False)
        self.assertEqual(salidas.diferencias_salvo_informe(R.politica, nueva), ["errata_post_c4"])
        marcada = politica.politica(R.tramos, R.estaciones, _huellas_politica(), post_hoc=True)
        with self.assertRaises(ValueError):
            salidas.politica_de_la_corrida(replace(R, politica=marcada), _huellas_politica())
        self.assertIs(salidas.politica_de_la_corrida(replace(R, politica=marcada), _huellas_politica(),
                                                     post_hoc=True)["post_hoc"], True)
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "HUMAN20261101_RELOJ_DMC_1_ERRATA1"
            v = VerificadorFalso()
            correr(R, c, verificar=v, n_control=0, errata_post_c4=True)
            self.assertEqual(salidas.comprobar_cadena(c), [])
            pol = json.loads((c / salidas.ARCHIVO_POLITICA).read_bytes())
            self.assertIs(pol["errata_post_c4"], True)
            self.assertEqual(len(v.rutas), 1)

    def test_h7_estados_del_diagnostico_de_reglas_vencidas(self):
        """§7.4 («estados_largos.parquet, la traza de cada decisión»): los estados del diagnóstico de reglas
        vencidas (P ∪ Cv) deciden la marca y van en estados_reglas_vencidas.parquet (SAL-19)."""
        ev = R.evidencias[1]
        rv = ev.estados[ev.estados["nivel"] == "anio"].reset_index(drop=True)
        rv["H"] = pd.array(["Cv(Santiago)"] * len(rv), dtype="string")
        r = replace(R, estados_reglas_vencidas=rv)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            huellas = salidas.escribir_tablas(r, d / "con")
            df = pd.read_parquet(d / "con" / salidas.TABLA_REGLAS_VENCIDAS)
            self.assertEqual(list(df.columns), list(ESQUEMA_ESTADOS))
            self.assertEqual(len(df), len(rv))
            self.assertEqual(set(df["H"]), {"Cv(Santiago)"})
            self.assertEqual(huellas[salidas.TABLA_REGLAS_VENCIDAS], entorno.sha256_archivo(d / "con" / salidas.TABLA_REGLAS_VENCIDAS))
            salidas.escribir_tablas(R, d / "sin")          # sin diagnóstico: la tabla está, vacía
            vacia = pd.read_parquet(d / "sin" / salidas.TABLA_REGLAS_VENCIDAS)
            self.assertEqual((len(vacia), list(vacia.columns)), (0, list(ESQUEMA_ESTADOS)))
            with self.assertRaises(ValueError):
                salidas.escribir_tablas(replace(R, estados_reglas_vencidas=rv.drop(columns=["motivo"])), d / "mala")
        # En la corrida, su huella entra al informe y a la cadena.
        carpeta = CORRIDA[0]
        inf = json.loads((carpeta / salidas.ARCHIVO_INFORME).read_bytes())
        self.assertEqual(inf["tablas"][salidas.TABLA_REGLAS_VENCIDAS],
                         entorno.sha256_archivo(carpeta / salidas.TABLA_REGLAS_VENCIDAS))
        with tempfile.TemporaryDirectory() as d:
            copia = Path(d) / "copia"
            shutil.copytree(carpeta, copia)
            (copia / salidas.TABLA_REGLAS_VENCIDAS).write_bytes(b"otra")
            self.assertIn(f"{salidas.TABLA_REGLAS_VENCIDAS} no tiene la huella que cita el informe",
                          salidas.comprobar_cadena(copia))

    def test_h8_claves_de_artefacto_son_las_que_escribe_extraccion(self):
        """SAL-16: las claves de artefactos_evaluados son las que escribe extraccion.extraer_dmc, sobre una
        descarga fabricada con el formato real (como test_extraccion); se omite si falta el código fijado."""
        from reloj_dmc.tests import test_extraccion as tx
        with tempfile.TemporaryDirectory() as d:
            raiz, destino = Path(d).resolve() / "DMC", Path(d).resolve() / "corrida"
            raiz.mkdir()
            destino.mkdir()
            desc = tx._descargador()
            tx._fabricar(raiz, lambda c, a, m: tx._filas_normales(desc, dias=1), "2020-01-01", "2020-02-29")
            tx._extraer(raiz, destino)
            artefactos = extraccion.leer_artefactos_evaluados(destino)
            meses = extraccion.leer_meses(destino)
        self.assertEqual(len(artefactos), 2)
        self.assertEqual({frozenset(a) for a in artefactos}, {frozenset(salidas.CLAVES_ARTEFACTO)})
        self.assertEqual(len(salidas.contenido_artefactos(artefactos)), len(artefactos))
        salidas._exigir_artefactos_de_los_meses(artefactos, meses)

    def test_semilla_es_la_del_anexo_b(self):
        """La semilla de las pruebas es U.f("SEMILLA"); se omite si falta el JSON de C0."""
        for ruta in (_APH / umbrales.PROTOCOLO_C0, _APH / umbrales.JSON_C0):
            if not ruta.is_file():
                self.skipTest(f"falta {ruta.name} anclado en C0; la prueba no se da por aprobada")
        self.assertEqual(int(umbrales.cargar_c0(_APH).f("SEMILLA")), SEMILLA)

    def test_h9_reloj_derivado_con_la_regla_de_orq7(self):
        """SAL-11 (ola 4b): sin política ni «estaciones», el «reloj» derivado de las rachas aceptadas sigue la
        regla única de ORQ-7 (politica.reloj_de_rachas): intersección y «→» sólo donde hay cambio."""
        V = Veredicto
        civil = "F(-3)|C(Santiago)"
        dec = [_decision("330020", 2015, V.CONFIRMADO, clase=civil), _decision("330020", 2016, V.DISCREPANTE),
               _decision("330020", 2017, V.CONFIRMADO, clase=CS), _decision("330020", 2019, V.CONFIRMADO, clase=F0)]

        def racha(n, desde, hasta, clase, aceptada=True):
            return {"codigo": "330020", "racha": n, "anio_desde": desde, "anio_hasta": hasta, "clase": clase,
                    "n_confirmados": 1, "aceptada": aceptada, "motivo": None}
        rachas = _tabla([racha(1, 2015, 2015, civil), racha(2, 2017, 2017, CS), racha(3, 2019, 2019, F0),
                         racha(4, 2020, 2020, F4, aceptada=False)], ESQUEMA_RACHAS)
        e = salidas._estacion_derivada("330020", dec, rachas)
        self.assertEqual((e["veredicto"], e["reloj"], e["derivada_de_las_decisiones"]),
                         ("confirmada", "C(Santiago)→F(0)", True))
        self.assertEqual(e["reloj"], politica.reloj_de_rachas([civil, CS, F0]))
        # Sin rachas aceptadas, las clases confirmadas, con la misma regla.
        self.assertEqual(salidas._estacion_derivada("330020", dec, rachas.iloc[0:0])["reloj"], "C(Santiago)→F(0)")
        self.assertEqual(salidas._estacion_derivada("330020", dec[1:2], rachas)["veredicto"], "sin_confirmar")

    def test_h10_lineas_sin_cv_van_a_las_desviaciones(self):
        """SAL-22 (ORQ-3f): ``controles["reglas_vencidas"]["lineas_sin_cv"]`` no vacía es una desviación del
        informe; vacía o ausente, no."""
        desv = salidas.DESVIACION_LINEAS_SIN_CV.format(lineas="E6")
        base = salidas.informe(R, TABLAS_FALSAS, huellas_entrada(), [], meses=meses_completos(R))["desviaciones"]
        for lineas, esperadas in ((["E6"], [*base, desv]), ([], base)):
            controles = {**R.controles, "reglas_vencidas": {"diagnosticados": {}, "con_marca": [],
                                                            "lineas_sin_cv": lineas}}
            inf = salidas.informe(replace(R, controles=controles), TABLAS_FALSAS, huellas_entrada(), [],
                                  meses=meses_completos(R))
            self.assertEqual(inf["desviaciones"], esperadas)
        self.assertNotIn(desv, base)
        # La del llamador no se repite.
        controles = {**R.controles, "reglas_vencidas": {"lineas_sin_cv": ["E6"]}}
        inf = salidas.informe(replace(R, controles=controles), TABLAS_FALSAS, huellas_entrada(), [desv],
                              meses=meses_completos(R))
        self.assertEqual(inf["desviaciones"].count(desv), 1)
        self.assertEqual(salidas.desviaciones_de_controles(None), [])
        self.assertEqual(salidas.desviaciones_de_controles({"reglas_vencidas": None}), [])
        self.assertIn("E6", salidas.desviaciones_de_controles({"reglas_vencidas": {"lineas_sin_cv": ["E6"]}})[0])


if __name__ == "__main__":
    unittest.main()
