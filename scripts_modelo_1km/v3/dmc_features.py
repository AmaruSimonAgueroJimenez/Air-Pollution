"""Puente DMC puro y explícito: normalización/QC → mismo operador en estaciones/grilla.

No descarga, entrena, escribe ni activa un modelo. Sólo lee manifiestos indicados
por el llamador, cuando éste haya autorizado su uso. QC de fuente y controles
numéricos documentados son modos distintos: el segundo no es «validado DMC».
nearest/IDW exigen todos sus parámetros; no se eligen por métricas de salud.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

ADAPTER = Path(__file__).resolve().parents[1] / "v2/meteorologia_v2.py"
R_TIERRA_KM = 6371.0088
UNIDADES = {"Ts": "degC", "Td": "degC", "relative_humidity": "%", "wind_speed_instant": "m/s",
            "wind_u": "m/s", "wind_v": "m/s", "QFE": "hPa", "QFF": "hPa", "QNH": "hPa"}


def hash_json(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def hash_frame(df):
    if df.columns.duplicated().any():
        raise ValueError("Columnas duplicadas")
    h = hashlib.sha256(hash_json({"columns": list(df.columns), "dtypes": [str(x) for x in df.dtypes]}).encode())
    h.update(pd.util.hash_pandas_object(df, index=True, categorize=False).to_numpy().tobytes())
    return h.hexdigest()


def sha_archivo(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def utc_aware(s, *, permitir_nulos=False):
    s = pd.Series(s)
    if not isinstance(s.dtype, pd.DatetimeTZDtype):
        if any(not pd.isna(x) and pd.Timestamp(x).tzinfo is None for x in s):
            raise ValueError("UTC debe tener zona explícita, sin inferir timestamps naive")
    t = pd.to_datetime(s, utc=True)
    if not permitir_nulos and t.isna().any():
        raise ValueError("Clave UTC nula")
    return t


def _local(t):
    d = datetime.fromisoformat(str(t))
    if d.tzinfo is not None:
        raise ValueError("Los intervalos de política corresponden al reloj fuente sin zona")
    return d


def _documentada(regla, momento):
    if not isinstance(regla, dict) or regla.get("verified") is not True:
        return False
    if not isinstance(regla.get("source"), str) or not regla["source"].strip():
        raise ValueError("Política verificada sin fuente documental")
    a, b = _local(regla["valid_from"]), _local(regla["valid_to"])
    if a > b:
        raise ValueError("Intervalo documental invertido")
    return a <= momento <= b


def _qc(row, rule):
    if not row.model_ready or not np.isfinite(row.value):
        return False, False, "semantics_or_value_unavailable"
    if not _documentada(rule, _local(row.timestamp_source)):
        return False, False, "quality_policy_unverified"
    if rule.get("unit") != row.unit:
        raise ValueError("Unidad de QC distinta de la normalizada")
    method = rule.get("method")
    codes = rule.get("accepted_source_codes")
    if not isinstance(codes, list) or any(not isinstance(c, str) for c in codes):
        raise ValueError("QC exige lista explícita de códigos fuente aceptados")
    unknown = pd.isna(row.source_qc)
    if not row.source_qc_available and not unknown:
        raise ValueError("Código QC presente pero su disponibilidad fuente está negada")
    accepted = not unknown and str(row.source_qc) in codes
    if method == "source_codes":
        return bool(accepted), True, "source_code_accepted" if accepted else "source_code_missing_or_rejected"
    if method != "documented_numeric_checks" or type(rule.get("allow_unknown_source_qc")) is not bool:
        raise ValueError("Modo QC no definido explícitamente")
    a, b = rule.get("minimum"), rule.get("maximum")
    if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or not np.isfinite([a, b]).all() or a > b:
        raise ValueError("Límites QC documentados inválidos")
    usable = a <= row.value <= b and (accepted or (unknown and rule["allow_unknown_source_qc"]))
    if not a <= row.value <= b:
        reason = "documented_numeric_range_rejected"
    elif not usable:
        reason = "documented_numeric_source_qc_missing_or_rejected"
    else:
        reason = "documented_numeric_checks_unknown_source_qc" if unknown else "documented_numeric_checks_with_source_code"
    return bool(usable), True, reason


def _adapter(expected_sha):
    if not isinstance(expected_sha, str) or not re.fullmatch("[0-9a-f]{64}", expected_sha):
        raise ValueError("Se exige SHA256 explícito del adaptador v2")
    if ADAPTER.is_symlink() or sha_archivo(ADAPTER) != expected_sha:
        raise ValueError("Origen/SHA del adaptador v2 no coincide")
    spec = importlib.util.spec_from_file_location("_dmc_v2_pinned_readonly", ADAPTER)
    if spec is None or Path(spec.origin).resolve() != ADAPTER.resolve():
        raise ValueError("Origen del adaptador inesperado")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if Path(module.__file__).resolve() != ADAPTER.resolve() or sha_archivo(ADAPTER) != expected_sha:
        raise ValueError("El adaptador cambió mientras se cargaba")
    return module


def cargar_dmc(manifiestos, policies, *, adapter_sha256):
    """policies: lista estación+valid_from/to+clock/coordinates/measurements+quality[variable].

    Los intervalos externos distribuyen las filas entre políticas históricas sin
    solapamiento. Cada regla documental mantiene además su intervalo propio.
    Sin política, conserva observaciones inhabilitadas; nunca inventa UTC/QC.
    """
    adapter = _adapter(adapter_sha256)
    if not isinstance(policies, list):
        raise ValueError("Las políticas históricas deben ser una lista explícita")
    for policy in policies:
        if not policy.get("station_code") or _local(policy["valid_from"]) > _local(policy["valid_to"]):
            raise ValueError("Política histórica inválida")
    frames, artifacts = [], []
    for path in manifiestos:
        payload, meta = adapter.leer_artefacto(path)
        artifacts.append({"artifact_sha256": meta["content_sha256"], "manifest_sha256": sha_archivo(path)})
        groups = {}
        for row in payload["rows"]:
            t = _local(row["timestamp_source"])
            candidates = [i for i, p in enumerate(policies) if str(p["station_code"]) == str(row["station_code"])
                          and _local(p["valid_from"]) <= t <= _local(p["valid_to"])]
            if len(candidates) > 1:
                raise ValueError("Políticas históricas solapadas para una observación")
            groups.setdefault(candidates[0] if candidates else None, []).append(row)
        for i, rows in groups.items():
            policy = policies[i] if i is not None else {}
            d = adapter.normalizar({**payload, "rows": rows}, politica=policy, content_sha256=meta["content_sha256"])
            quality = policy.get("quality", {})
            checks = [_qc(r, quality.get(r.variable)) if r.variable not in ("wind_u", "wind_v")
                      else (False, False, "derived_requires_both_components") for r in d.itertuples()]
            d[["usable", "quality_policy_verified", "quality_reason"]] = pd.DataFrame(checks, index=d.index)
            for _, g in d.groupby("timestamp_source", sort=False):
                parents = g[g.variable.isin(("wind_speed_instant", "wind_direction_instant"))]
                ready = len(parents) == 2 and parents.usable.all() and parents.measurement_verified.all()
                mask = (d.timestamp_source == g.timestamp_source.iloc[0]) & d.variable.isin(("wind_u", "wind_v"))
                d.loc[mask, "usable"] = ready & d.loc[mask, "model_ready"]
                d.loc[mask, "quality_policy_verified"] = len(parents) == 2 and parents.quality_policy_verified.all()
                d.loc[mask, "quality_reason"] = "derived_from_both_qc_components" if ready else "derived_component_unavailable"
            frames.append(d)
    if not frames:
        raise ValueError("Sin observaciones DMC; no declarar producto listo")
    long = pd.concat(frames, ignore_index=True)
    long["timestamp_utc"] = utc_aware(long.timestamp_utc, permitir_nulos=True)
    if long.duplicated(["station_code", "timestamp_source", "variable"]).any() or long[long.timestamp_utc.notna()].duplicated(["station_code", "timestamp_utc", "variable"]).any():
        raise ValueError("Observaciones DMC duplicadas/conflictivas")
    meta = {"schema": "dmc-normalized-qc/v3", "adapter_sha256": adapter_sha256,
            "module_sha256": sha_archivo(__file__), "artifacts": sorted(artifacts, key=hash_json),
            "policies_sha256": hash_json(policies), "long_content_sha256": hash_frame(long),
            "semantic_QC_enforced": True, "rows": len(long), "usable_rows": int(long.usable.sum()),
            "unusable_rows": int((~long.usable).sum()),
            "quality_reason_counts": {str(k): int(v) for k, v in long.quality_reason.value_counts().sort_index().items()},
            "note": "QC según política registrada; controles numéricos no son validación oficial DMC"}
    meta["source_identity"] = hash_json(meta)
    return long, meta


def _operador(op):
    if not isinstance(op, dict) or op.get("method") not in ("nearest", "idw"):
        raise ValueError("Operador espacial explícito nearest|idw requerido")
    required = {"method", "radius_km", "k", "min_support"} | ({"power"} if op["method"] == "idw" else set())
    if set(op) != required:
        raise ValueError("Faltan parámetros espaciales o hay parámetros ignorados")
    if any(type(op[k]) is not int or op[k] < 1 for k in ("k", "min_support")) or op["min_support"] > op["k"]:
        raise ValueError("k/min_support inválidos")
    if type(op["radius_km"]) not in (int, float) or not np.isfinite(op["radius_km"]) or not 0 < op["radius_km"] <= np.pi * R_TIERRA_KM:
        raise ValueError("Radio explícito inválido")
    if op["method"] == "nearest" and (op["k"], op["min_support"]) != (1, 1):
        raise ValueError("nearest exige k=min_support=1")
    if op["method"] == "idw" and (type(op["power"]) not in (int, float) or not np.isfinite(op["power"]) or op["power"] <= 0):
        raise ValueError("Potencia IDW explícita inválida")
    return dict(op)


def _xyz(lat, lon):
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    if not (np.isfinite(lat).all() and np.isfinite(lon).all() and (abs(lat) <= 90).all() and (abs(lon) <= 180).all()):
        raise ValueError("Coordenadas inválidas")
    a, b = np.deg2rad(lat), np.deg2rad(lon)
    return np.column_stack([np.cos(a) * np.cos(b), np.cos(a) * np.sin(b), np.sin(a)])


def asignar_dmc(long, targets, *, operator, variables, source_metadata):
    """Mismo operador para cualquier target; targets lleva target_id, ts_utc, lat/lon por hora.

    Sólo coincidencia UTC exacta. Sin interpolación temporal. Empates se ordenan
    por distancia y código de estación. En IDW, coincidencias exactas reciben
    peso igual entre las seleccionadas; el resto peso0. min_support cuenta
    estaciones seleccionadas calificadas antes de ese tratamiento numérico.
    """
    op = _operador(operator)
    if source_metadata.get("semantic_QC_enforced") is not True or source_metadata.get("source_identity") != hash_json({k: v for k, v in source_metadata.items() if k != "source_identity"}):
        raise ValueError("Identidad/política de fuente no acreditada")
    if source_metadata.get("long_content_sha256") != hash_frame(long):
        raise ValueError("Cambió el contenido DMC normalizado")
    if not variables or len(set(variables)) != len(variables) or any(v not in UNIDADES for v in variables):
        raise ValueError("Whitelist meteorológica inválida; RR06 y dirección circular no son escalares horarios")
    t = targets.copy()
    if t.empty or t.columns.duplicated().any() or t.target_id.isna().any() or not t.target_id.map(lambda x: isinstance(x, str) and bool(x.strip())).all():
        raise ValueError("Identidad de target inválida")
    t["ts_utc"] = utc_aware(t.ts_utc)
    if t.duplicated(["target_id", "ts_utc"]).any() or (t.ts_utc.dt.minute.ne(0) | t.ts_utc.dt.second.ne(0) | t.ts_utc.dt.microsecond.ne(0) | t.ts_utc.dt.nanosecond.ne(0)).any():
        raise ValueError("Targets duplicados o fuera de la hora UTC exacta")
    xyz = _xyz(t.latitude, t.longitude)
    out = t[["target_id", "ts_utc"]].copy()
    for v in variables:
        for suffix, initial in (("", np.nan), ("_support", 0), ("_nearest_km", np.nan), ("_farthest_km", np.nan)):
            out[f"dmc_{v}{suffix}"] = initial
    available = long[long.usable & long.timestamp_utc.notna() & long.variable.isin(variables)]
    radius_chord = 2 * np.sin(op["radius_km"] / (2 * R_TIERRA_KM))
    for (hour, variable), obs in available.groupby(["timestamp_utc", "variable"], sort=True):
        rows = np.flatnonzero(t.ts_utc.eq(hour).to_numpy())
        if not len(rows):
            continue
        obs = obs.sort_values("station_code", kind="stable").reset_index(drop=True)
        if obs.station_code.duplicated().any() or not obs.unit.eq(UNIDADES[variable]).all():
            raise ValueError("Fuente espacial duplicada o unidad incompatible")
        points = _xyz(obs.latitude, obs.longitude)
        tree = cKDTree(points)
        neighbors = tree.query_ball_point(xyz[rows], radius_chord + 1e-12, workers=1)
        for row, candidates in zip(rows, neighbors):
            if not candidates:
                continue
            dist = 2 * np.arcsin(np.clip(np.linalg.norm(points[candidates] - xyz[row], axis=1) / 2, 0, 1)) * R_TIERRA_KM
            candidates = np.asarray(candidates)[dist <= op["radius_km"] + 1e-9]
            dist = dist[dist <= op["radius_km"] + 1e-9]
            order = np.lexsort((obs.station_code.to_numpy()[candidates], dist))[:op["k"]]
            selected, dist = candidates[order], dist[order]
            out.iloc[row, out.columns.get_loc(f"dmc_{variable}_support")] = len(selected)
            if len(selected):
                out.iloc[row, out.columns.get_loc(f"dmc_{variable}_nearest_km")] = dist.min()
                out.iloc[row, out.columns.get_loc(f"dmc_{variable}_farthest_km")] = dist.max()
            if len(selected) < op["min_support"]:
                continue
            values = obs.value.to_numpy(float)[selected]
            if op["method"] == "nearest":
                value = values[0]
            else:
                weights = (dist == 0).astype(float) if (dist == 0).any() else (dist.min() / dist) ** op["power"]
                value = np.dot(values, weights / weights.sum())
            out.iloc[row, out.columns.get_loc(f"dmc_{variable}")] = value
    features = [f"dmc_{v}" for v in variables]
    meta = {"schema": "dmc-spatial-features/v3", "module_sha256": sha_archivo(__file__),
            "source_identity": source_metadata["source_identity"], "operator": op,
            "spatial_rules": "great-circle; tie=station_code; IDW exact=mean_selected_coincident; exact UTC only",
            "target_content_sha256": hash_frame(t), "feature_columns": features,
            "feature_units": {f"dmc_{v}": UNIDADES[v] for v in variables}, "content_sha256": hash_frame(out),
            "semantic_QC_enforced": True, "all_requested_values_finite": bool(np.isfinite(out[features]).all().all()),
            "note": "Soporte insuficiente=NaN, no cero; mismo operador para estaciones y grilla; no acredita producción"}
    meta["feature_identity"] = hash_json(meta)
    return out, meta
