"""Adaptador DMC de sólo lectura; no activa modelos ni modifica la referencia v1.

Lee únicamente la versión señalada por un manifiesto mensual. Una política
documentada debe confirmar reloj y coordenadas para cada intervalo antes de
considerar una observación lista para modelar. Sin ella no se inventa UTC.
No interpola estaciones, reparte lluvia acumulada ni declara datos validados.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

# ID28 describe viento medio en el inventario; no acredita las columnas DD/FF Inst.
ELEMENTOS = {"Ts": 26, "relative_humidity": 66, "QFE": 64, "QFF": 65, "QNH": 70, "RR06": 57}
UNIDADES = {"Ts": "degC", "Td": "degC", "relative_humidity": "%", "wind_direction_instant": "degree",
            "wind_speed_instant": "kt", "QFE": "hPa", "QFF": "hPa", "QNH": "hPa", "RR06": "mm"}
NUDO_MS = 1852 / 3600
MAX_COMPRIMIDO = 32 * 1024 * 1024
MAX_EXPANDIDO = 128 * 1024 * 1024


def _sha_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def leer_artefacto(manifiesto) -> tuple[dict, dict]:
    """Lee el único gzip apuntado; rechaza enlaces en ambos archivos y no escribe."""
    ruta = Path(manifiesto)
    if ruta.is_symlink():
        raise ValueError("El manifiesto no puede ser un enlace simbólico")
    meta = json.loads(ruta.read_text(encoding="utf-8"))
    nombre = meta.get("artifact_name", "")
    if not nombre or Path(nombre).name != nombre or not nombre.endswith(".json.gz"):
        raise ValueError("artifact_name no es un nombre gzip local seguro")
    archivo = ruta.parent / nombre
    if archivo.is_symlink():
        raise ValueError("El artefacto no puede ser un enlace simbólico")
    with archivo.open("rb") as stream:
        comprimido = stream.read(MAX_COMPRIMIDO + 1)
    if len(comprimido) > MAX_COMPRIMIDO:
        raise ValueError("Artefacto comprimido demasiado grande")
    sha = hashlib.sha256(comprimido).hexdigest()
    if meta.get("artifact_sha256") is not None and sha != meta["artifact_sha256"]:
        raise ValueError("SHA256 del artefacto no coincide")
    if meta.get("artifact_bytes") is not None and len(comprimido) != meta["artifact_bytes"]:
        raise ValueError("Tamaño del artefacto no coincide")
    with gzip.GzipFile(fileobj=io.BytesIO(comprimido)) as stream:
        expandido = stream.read(MAX_EXPANDIDO + 1)
    if len(expandido) > MAX_EXPANDIDO:
        raise ValueError("Artefacto expandido demasiado grande")
    payload = json.loads(expandido)
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("El artefacto no tiene una lista de observaciones")
    if meta.get("row_count") is not None and len(rows) != meta["row_count"]:
        raise ValueError("Recuento de observaciones no coincide")
    codigo = str(payload.get("station", {}).get("code", ""))
    if not codigo or any(str(row.get("station_code", "")) != codigo for row in rows):
        raise ValueError("Estación del artefacto y sus observaciones no coinciden")
    if meta.get("station_code") is not None and str(meta["station_code"]) != codigo:
        raise ValueError("Estación del manifiesto no coincide")
    return payload, {**meta, "content_sha256": sha}


def _momento(texto) -> datetime:
    d = datetime.fromisoformat(str(texto))
    if d.tzinfo is not None:
        raise ValueError("La hora fuente y los límites de política deben ser locales sin zona")
    return d


def _confirmado(regla, momento: datetime) -> bool:
    if not regla or regla.get("verified") is not True:
        return False
    if not isinstance(regla.get("source"), str) or not regla["source"].strip():
        raise ValueError("Una política confirmada necesita fuente documental")
    if "valid_from" not in regla or "valid_to" not in regla:
        raise ValueError("Una política confirmada necesita intervalo de validez")
    a, b = _momento(regla["valid_from"]), _momento(regla["valid_to"])
    if a > b:
        raise ValueError("Intervalo de política invertido")
    return a <= momento <= b


def _utc(momento: datetime, reloj: dict) -> datetime:
    if reloj.get("timestamp_semantics") != "instantaneous":
        raise ValueError("Debe confirmarse la semántica instantánea; no se desplazan intervalos por suposición")
    if ("timezone" in reloj) == ("fixed_offset_minutes" in reloj):
        raise ValueError("Declarar una zona IANA o un desfase fijo, no ambos")
    if "fixed_offset_minutes" in reloj:
        offset = reloj["fixed_offset_minutes"]
        if isinstance(offset, bool) or not isinstance(offset, int) or abs(offset) > 14 * 60:
            raise ValueError("Desfase fijo inválido")
        return momento.replace(tzinfo=timezone(timedelta(minutes=offset))).astimezone(timezone.utc)
    zona = ZoneInfo(reloj["timezone"])
    candidatos = {momento.replace(tzinfo=zona, fold=f).astimezone(timezone.utc)
                  for f in (0, 1)
                  if momento.replace(tzinfo=zona, fold=f).astimezone(timezone.utc)
                  .astimezone(zona).replace(tzinfo=None) == momento}
    if len(candidatos) != 1:
        raise ValueError("Hora local ambigua o inexistente; no se infiere su conversión")
    return candidatos.pop()


def _medicion(regla, momento: datetime, variable: str) -> tuple[bool, str | None, int | None]:
    if not _confirmado(regla, momento):
        return False, None, None
    estadistico, minutos = regla.get("statistic"), regla.get("interval_minutes")
    if (estadistico not in ("instantaneous", "mean", "sum") or isinstance(minutos, bool)
            or not isinstance(minutos, int) or minutos < 0
            or (estadistico == "instantaneous") != (minutos == 0)):
        raise ValueError("La medición necesita estadístico e intervalo explícitos compatibles")
    if variable.startswith("wind_") and (estadistico, minutos) != ("instantaneous", 0):
        raise ValueError("DD/FF Inst no se pueden declarar viento medio")
    if variable == "RR06" and (estadistico, minutos) != ("sum", 360):
        raise ValueError("RR06 debe conservar su acumulado de seis horas")
    return True, estadistico, minutos


def normalizar(payload: dict, *, politica: dict | None = None,
               content_sha256: str | None = None) -> pd.DataFrame:
    """Wide anidado → long, conservando origen, faltantes y calidad desconocida.

    ``politica`` identifica ``station_code`` y dos reglas ``clock`` y
    ``coordinates``. Cada regla confirmada requiere ``verified=True``,
    ``source``, ``valid_from`` y ``valid_to``. Reloj: ``timestamp_semantics``
    instantánea y ``timezone`` IANA o ``fixed_offset_minutes``. Coordenadas:
    ``latitude`` y ``longitude`` verificadas para ese intervalo. Cada variable
    necesita además ``measurements[variable]`` con la misma documentación y
    validez, ``statistic`` e ``interval_minutes``. Este adaptador habilita sólo
    covariables instantáneas; medias y acumulados se conservan sin habilitarlos.
    """
    codigo = str(payload.get("station", {}).get("code", ""))
    politica = politica or {}
    if politica and str(politica.get("station_code", "")) != codigo:
        raise ValueError("Política de otra estación")
    salida, vistos = [], set()
    for row in payload["rows"]:
        if str(row.get("station_code", "")) != codigo:
            raise ValueError("Observación de otra estación")
        momento = _momento(row["timestamp_source"])
        if momento.minute or momento.second or momento.microsecond or momento in vistos:
            raise ValueError("Hora no nativa o duplicada; no se promedian conflictos")
        vistos.add(momento)
        clock = _confirmado(politica.get("clock"), momento)
        coords = _confirmado(politica.get("coordinates"), momento)
        utc = _utc(momento, politica["clock"]) if clock else None
        lat, lon = None, None
        if coords:
            lat, lon = (float(politica["coordinates"][k]) for k in ("latitude", "longitude"))
            if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("Coordenadas confirmadas inválidas")
        base = {"station_code": codigo, "timestamp_source": momento.isoformat(),
                "timestamp_utc": utc, "latitude": lat, "longitude": lon,
                "clock_verified": clock, "coordinates_verified": coords,
                "source_qc_available": row.get("source_qc_available", False),
                "source_artifact_sha256": content_sha256,
                "policy_sha256": _sha_json(politica)}
        valores, listos = {}, {}
        for variable, field in row["fields"].items():
            valor = field.get("value")
            status = field.get("parse_status")
            if status != "numeric" or valor is None:
                valor = None
            elif isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
                raise ValueError("Valor declarado numérico no finito o inválido")
            unidad = field.get("unit")
            if variable in UNIDADES and unidad != UNIDADES[variable]:
                raise ValueError(f"Unidad inesperada para {variable}")
            if valor is not None and ((variable == "wind_speed_instant" and valor < 0)
                                     or (variable == "wind_direction_instant" and not 0 <= valor <= 360)):
                raise ValueError("Viento fuera de dominio")
            origen = valor
            if variable == "wind_speed_instant":
                valor, unidad = None if valor is None else valor * NUDO_MS, "m/s"
            valores[variable] = valor
            acumulado = 6 if variable == "RR06" else None
            med, estadistico, minutos = _medicion(politica.get("measurements", {}).get(variable), momento, variable)
            listo = (clock and coords and med and (estadistico, minutos) == ("instantaneous", 0)
                     and variable in UNIDADES and valor is not None and acumulado is None)
            listos[variable] = listo
            salida.append({**base, "variable": variable, "element_id": ELEMENTOS.get(variable),
                           "value": valor, "unit": unidad, "source_value": origen,
                           "source_unit": field.get("unit"), "raw": field.get("raw"),
                           "parse_status": status, "source_qc": field.get("source_qc"),
                           "source_policy_verified": clock and coords and med,
                           "measurement_verified": med, "statistic": estadistico, "interval_minutes": minutos,
                           "measurement_status": "verified" if med else "unverified",
                           "accumulation_hours": acumulado,
                           "model_ready": listo})
        vel, direccion = valores.get("wind_speed_instant"), valores.get("wind_direction_instant")
        if vel is not None and direccion is not None:
            ang = math.radians(direccion)
            listo = listos["wind_speed_instant"] and listos["wind_direction_instant"]
            for variable, valor in (("wind_u", -vel * math.sin(ang)), ("wind_v", -vel * math.cos(ang))):
                salida.append({**base, "variable": variable, "element_id": None, "value": valor,
                               "unit": "m/s", "source_value": None, "source_unit": None, "raw": None,
                               "parse_status": "derived", "source_qc": None, "accumulation_hours": None,
                               "source_policy_verified": listo, "measurement_verified": listo,
                               "statistic": "instantaneous" if listo else None,
                               "interval_minutes": 0 if listo else None,
                               "measurement_status": "verified" if listo else "unverified",
                               "model_ready": listo})
    df = pd.DataFrame(salida)
    if not df.empty:
        df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    candidatas = df["value"].notna() & df["accumulation_hours"].isna() if not df.empty else pd.Series(dtype=bool)
    df.attrs.update(policy_sha256=_sha_json(politica), source_artifact_sha256=content_sha256,
                    model_ready=bool(candidatas.any() and df.loc[candidatas, "model_ready"].all()),
                    note="Semántica no verificada se conserva sin habilitar; sin interpolación ni calidad validada")
    return df


def unir_sidecar(panel: pd.DataFrame, sidecar: pd.DataFrame, *, metadata: dict) -> tuple[pd.DataFrame, dict]:
    """Une covariables ya preparadas en estación×UTC sin cambiar filas ni índice.

    No convierte horas naïve ni calcula asignaciones espaciales. ``metadata``
    debe confirmar ``model_ready`` y ``source_policy_verified`` y declarar
    ``policy_sha256``. La identidad devuelta debe incorporarse a la firma del
    ajuste junto con la identidad del panel base, no sustituirla.
    """
    claves = ["estacion", "ts_utc"]
    if metadata.get("model_ready") is not True or metadata.get("source_policy_verified") is not True:
        raise ValueError("Sidecar sin política fuente verificada")
    policy = metadata.get("policy_sha256", "")
    if len(policy) != 64 or any(c not in "0123456789abcdef" for c in policy):
        raise ValueError("Falta identidad de la política documental")
    for tabla in (panel, sidecar):
        if not tabla.columns.is_unique or not set(claves).issubset(tabla.columns) or tabla[claves].isna().any().any():
            raise ValueError("Claves incompletas")
        if not isinstance(tabla["ts_utc"].dtype, pd.DatetimeTZDtype):
            raise ValueError("ts_utc debe tener zona explícita; no se infiere UTC")
    if sidecar.duplicated(claves).any():
        raise ValueError("Sidecar duplicado por estación y hora")
    nuevas = [c for c in sidecar.columns if c not in claves]
    if not nuevas or set(nuevas) & set(panel.columns):
        raise ValueError("Covariables vacías o solapadas con el panel")
    right = sidecar.copy()
    right["ts_utc"] = right["ts_utc"].dt.tz_convert("UTC")
    keys = pd.MultiIndex.from_arrays([panel["estacion"], panel["ts_utc"].dt.tz_convert("UTC")], names=claves)
    alineado = right.set_index(claves).reindex(keys)
    resultado = panel.copy()
    for col in nuevas:
        resultado[col] = alineado[col].to_numpy()
    h = hashlib.sha256()
    h.update(_sha_json({"columns": list(right.columns), "dtypes": list(map(str, right.dtypes)),
                        "policy_sha256": policy}).encode())
    h.update(pd.util.hash_pandas_object(right, index=False, categorize=False).to_numpy().tobytes())
    identidad = {"content_sha256": h.hexdigest(), "policy_sha256": policy,
                 "source_artifact_sha256": metadata.get("source_artifact_sha256"),
                 "columns": nuevas, "sidecar_rows": len(sidecar), "panel_rows": len(panel)}
    return resultado, identidad
