"""Propuesta aislada: validar y unir una lateral ya calculada, sin E/S ni modelos.

No importa ejecutores ni meteo_combinada: recibe sus dependencias explícitamente.
``ambiental`` aporta METADATOS_LATERAL, COLUMNAS_VARIANTE, UNIDADES y la función
fijada huella_contenido; ``adaptador`` aporta meteorologia_v2.unir_sidecar.
La frontera que lee archivos debe verificar sus bytes ANTES de llamar aquí.
Una afirmación de huella junto a un DataFrame no acredita su procedencia.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

import pandas as pd


HUELLAS = ("content_sha256", "policy_sha256", "decision_sha256", "operador_sha256",
           "panel_sha256", "pliegues_sha256")
_CLAVES = ("estacion", "ts_utc")
_HEX = re.compile(r"[0-9a-f]{64}")
_NS_HORA = pd.Timedelta(hours=1).value
_IDENTIDAD_UNION = {"content_sha256", "policy_sha256", "source_artifact_sha256",
                    "columns", "sidecar_rows", "panel_rows"}


class ErrorIntegracion(ValueError):
    """El contrato estructural no permite esta unión; no hay reparación automática."""


def _claves_utc(tabla: pd.DataFrame, nombre: str, *, ingenuo_es_utc: bool) -> pd.MultiIndex:
    if not isinstance(tabla, pd.DataFrame) or not tabla.columns.is_unique \
            or not set(_CLAVES) <= set(tabla.columns):
        raise ErrorIntegracion(f"{nombre}: columnas únicas y claves estacion, ts_utc obligatorias")
    if tabla[list(_CLAVES)].isna().any().any():
        raise ErrorIntegracion(f"{nombre}: claves nulas")
    if not all(isinstance(e, str) and "\x00" not in e for e in tabla["estacion"]):
        raise ErrorIntegracion(f"{nombre}: códigos de estación de texto, sin carácter nulo")
    ts = tabla["ts_utc"]
    if isinstance(ts.dtype, pd.DatetimeTZDtype):
        ts = ts.dt.tz_convert("UTC")
    elif pd.api.types.is_datetime64_dtype(ts.dtype) and ingenuo_es_utc is True:
        ts = ts.dt.tz_localize("UTC")
    else:
        raise ErrorIntegracion(f"{nombre}: zona explícita o procedencia UTC del panel confirmada")
    if (pd.DatetimeIndex(ts).as_unit("ns").asi8 % _NS_HORA != 0).any():
        raise ErrorIntegracion(f"{nombre}: horas HH:00 exactas")
    claves = pd.MultiIndex.from_arrays([tabla["estacion"].astype(object), ts], names=_CLAVES)
    if claves.has_duplicates:
        raise ErrorIntegracion(f"{nombre}: claves duplicadas")
    return claves


def unir_lateral_validada(panel: pd.DataFrame, lateral: pd.DataFrame, metadatos: Mapping, *,
                         variante: str, identidades_esperadas: Mapping, ultima_hora_utc: pd.Timestamp,
                         ambiental, adaptador, panel_ingenuo_es_utc: bool = False) -> tuple[pd.DataFrame, dict]:
    """Une exactamente las claves cubiertas; sólo AMB-17 autoriza claves ausentes.

    ``identidades_esperadas`` tiene exactamente HUELLAS, obtenidas por el lector
    de los archivos registrados (no copiadas ciegamente de ``metadatos``).
    ``ultima_hora_utc`` viene de FON-1, no del máximo de la lateral. Exige zona y
    HH:00. No acredita valores NaN dentro de una fila: los conserva, sin imputar.
    Para un panel sin zona, la afirmación explícita ``panel_ingenuo_es_utc=True``
    sólo procede después de comprobar su procedencia UTC. Localiza una copia
    para el adaptador y restaura la representación original en el resultado.

    Devuelve el panel ampliado y la identidad REAL de unir_sidecar. Esa identidad
    NO sustituye la del panel, ni es el content_sha256 canónico de la lateral.
    No valida git, sellos, bytes del panel, selección científica ni ausencia de
    fuga en el productor; véase DISENO_INTEGRACION.md antes de usar en producción.
    """
    if variante not in ("I", "D"):
        raise ErrorIntegracion("variante: I o D, explícita")
    if not isinstance(metadatos, Mapping) or set(metadatos) != set(ambiental.METADATOS_LATERAL):
        raise ErrorIntegracion("metadatos: exactamente METADATOS_LATERAL del productor fijado")
    if not isinstance(identidades_esperadas, Mapping) or set(identidades_esperadas) != set(HUELLAS):
        raise ErrorIntegracion("identidades_esperadas: las seis HUELLAS verificadas por el lector")
    for nombre in HUELLAS:
        esperado = identidades_esperadas[nombre]
        if not isinstance(esperado, str) or _HEX.fullmatch(esperado) is None:
            raise ErrorIntegracion(f"identidad esperada inválida: {nombre}")
        if metadatos[nombre] != esperado:
            raise ErrorIntegracion(f"identidad distinta: {nombre}")
    if metadatos["model_ready"] is not True or metadatos["source_policy_verified"] is not True:
        raise ErrorIntegracion("lateral sin política fuente verificada")
    columnas = list(ambiental.COLUMNAS_VARIANTE[variante])
    if metadatos["variante"] != variante or metadatos["columnas"] != columnas:
        raise ErrorIntegracion("variante o columnas distintas de la variante solicitada")
    if metadatos["unidades"] != dict(ambiental.UNIDADES[variante]):
        raise ErrorIntegracion("unidades distintas de las del productor fijado")
    claves_panel = _claves_utc(panel, "panel", ingenuo_es_utc=panel_ingenuo_es_utc)
    claves_lateral = _claves_utc(lateral, "lateral", ingenuo_es_utc=False)
    # Reutiliza AMB-18: no reproduce la receta de huella ni calcula meteorología.
    if ambiental.huella_contenido(lateral) != metadatos["content_sha256"]:
        raise ErrorIntegracion("content_sha256 no coincide con el contenido de la lateral")
    if not isinstance(ultima_hora_utc, pd.Timestamp) or pd.isna(ultima_hora_utc) \
            or ultima_hora_utc.tzinfo is None or ultima_hora_utc.value % _NS_HORA:
        raise ErrorIntegracion("ultima_hora_utc: Timestamp con zona y HH:00, desde FON-1")
    cubiertas = claves_panel.get_level_values("ts_utc") <= ultima_hora_utc.tz_convert("UTC")
    esperadas = claves_panel[cubiertas]
    if len(esperadas.difference(claves_lateral)) or len(claves_lateral.difference(esperadas)):
        raise ErrorIntegracion("claves faltantes no autorizadas o claves extra en la lateral")
    tras = metadatos["claves_tras_ultima_hora"]
    if type(tras) is not int or tras != int((~cubiertas).sum()):
        raise ErrorIntegracion("claves_tras_ultima_hora no coincide con el panel y FON-1")
    if set(columnas) & set(panel.columns):
        raise ErrorIntegracion("columnas laterales solapadas con el panel")
    base = panel.copy()
    if not isinstance(base["ts_utc"].dtype, pd.DatetimeTZDtype):
        base["ts_utc"] = base["ts_utc"].dt.tz_localize("UTC")
    resultado, identidad = adaptador.unir_sidecar(base, lateral, metadata=dict(metadatos))
    if list(resultado.columns) != list(base.columns) + columnas \
            or not resultado.index.identical(base.index) \
            or not resultado[list(base.columns)].equals(base):
        raise ErrorIntegracion("la unión alteró filas, índice, orden o columnas del panel")
    # Se comprueba ANTES de restaurar la representación temporal original:
    # Contexto y Vecindario esperan la del panel, no la de la copia para el adaptador.
    resultado["ts_utc"] = panel["ts_utc"].copy()
    if not resultado[list(panel.columns)].equals(panel):
        raise ErrorIntegracion("no se preservó la representación original del panel")
    if not isinstance(identidad, Mapping) or set(identidad) != _IDENTIDAD_UNION \
            or identidad["columns"] != columnas \
            or identidad["policy_sha256"] != metadatos["policy_sha256"] \
            or identidad["panel_rows"] != len(panel) or identidad["sidecar_rows"] != len(lateral) \
            or identidad["source_artifact_sha256"] is not None \
            or not isinstance(identidad["content_sha256"], str) \
            or _HEX.fullmatch(identidad["content_sha256"]) is None:
        raise ErrorIntegracion("identidad de unión incompatible con el adaptador fijado")
    return resultado, dict(identidad)
