#!/usr/bin/env python3
"""Preflight exhaustivo y de sólo lectura; nunca abre observaciones crudas DMC.

Inspecciona artefactos preparados y recoge todos los bloqueos independientes.
Un comando propuesto no ejecuta ni autoriza el ajuste o la producción. La
revisión científica de QC/OOF sigue siendo una entrada externa explícita.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shlex
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

import preparar_base_v3 as base
import produccion_v3 as production
import runner_v3 as runner
from dmc_features import _documentada, _local, _operador, _adapter, UNIDADES, utc_aware
from producto_horario_v3 import validar_geometria_grid


class Audit:
    def __init__(self):
        self.checks = []

    def check(self, name, stage, fn):
        try:
            detail = fn()
            self.checks.append({"id": name, "stage": stage, "status": "passed", "detail": detail})
            return detail
        except Exception as exc:
            self.checks.append({"id": name, "stage": stage, "status": "blocked",
                                "detail": f"{type(exc).__name__}: {exc}"})
            return None

    def defer(self, name, stage, reason):
        self.checks.append({"id": name, "stage": stage, "status": "deferred", "detail": reason})

    def ready(self, *stages):
        checks = [c for c in self.checks if c["stage"] in stages]
        return bool(checks) and all(c["status"] == "passed" for c in checks)


def require(condition, message):
    if not condition:
        raise ValueError(message)
    return True


def non_dmc_artifact(ref):
    p = Path((ref or {}).get("path", ""))
    require(not any(part.lower() == "dmc" for part in p.resolve().parts), "Crudo DMC prohibido en este preflight")
    return runner.artifact(ref)


def approved(ref, role):
    non_dmc_artifact(ref)
    return runner.approved(ref, role)


def read_table(ref, limit, columns):
    require(type(limit) is int and limit > 0, "Presupuesto de filas explícito requerido")
    p = non_dmc_artifact(ref)
    pf = pq.ParquetFile(p)
    require(0 < pf.metadata.num_rows <= limit, "Tabla vacía o sobre presupuesto; dividir antes")
    require(set(columns) <= set(pf.schema.names), f"Faltan columnas: {sorted(set(columns) - set(pf.schema.names))}")
    d = pd.read_parquet(p)
    non_dmc_artifact(ref)
    require(not d.columns.duplicated().any(), "Columnas duplicadas")
    return d


def validate_panel(d, cfg):
    require(not d[["target_id", "ts_utc"]].isna().any().any() and not d.duplicated(["target_id", "ts_utc"]).any(), "Claves de panel nulas/duplicadas")
    require(d.target_id.map(lambda x: isinstance(x, str) and bool(x.strip())).all(), "Identidad target inválida")
    d["ts_utc"] = utc_aware(d.ts_utc)
    require(d.ts_utc.eq(d.ts_utc.dt.floor("h")).all(), "Panel fuera de la grilla horaria UTC")
    xy = d[["lat", "lon"]].to_numpy(float)
    require(np.isfinite(xy).all() and (abs(xy[:, 0]) <= 90).all() and (abs(xy[:, 1]) <= 180).all(), "Coordenadas inválidas")
    require(np.isfinite(d.obs).all() and (d.obs >= 0).all(), "Observaciones inválidas")
    runner.validar_predictores(d, cfg, cfg["base_features"])
    return {"rows": len(d), "targets": int(d.target_id.nunique()), "start_utc": d.ts_utc.min().isoformat(),
            "end_utc": d.ts_utc.max().isoformat(), "missing_by_feature": {c: int(d[c].isna().sum()) for c in cfg["base_features"]}}


def validate_definition(cfg):
    d = runner.read_json(non_dmc_artifact(cfg["base_feature_definition"]))
    require(d.get("schema") == "baseline-feature-definition/3", "Definición de fábrica base requerida")
    require(d.get("base_features") == cfg["base_features"], "Columnas de definición y runner distintas")
    require(d.get("adapter_sha256") == base.sha_archivo(base.__file__), "Definición fabricada con otro adaptador")
    for name in ("_features.py", "_comun_modelo.py"):
        require(d["legacy_pins"][name] == base.sha_archivo(base.LEGACY / name), "Definición con legado distinto")
    return {"definition_sha256": cfg["base_feature_definition"]["sha256"], "columns": len(d["base_features"])}


def progress_complete(cfg):
    p = Path(cfg["dmc"]["progress_path"])
    d = runner.read_json(p)
    expected = cfg["dmc"]["completed_status"]
    require(expected and expected != "running" and d.get("status") == expected and d.get("coverage_complete") is True
            and d.get("jobs_pending") == 0 and d.get("stations_pending_inventory") == 0,
            "Descarga no terminada/verificada; manifiestos no se abren")
    return {"status": d["status"], "coverage_complete": True, "jobs_pending": 0, "stations_pending_inventory": 0}


def manifest_metadata(ref):
    # Sólo metadatos después de verificar cierre. Nunca abre/hash del gzip crudo.
    require(str((ref or {}).get("path", "")).endswith(".manifest.json"), "Sólo manifiesto .manifest.json; no archivo crudo")
    p = runner.artifact(ref)
    d = runner.read_json(p)
    require(isinstance(d.get("artifact_name"), str) and Path(d["artifact_name"]).name == d["artifact_name"], "Nombre de artefacto DMC inválido")
    require(re.fullmatch(r"[0-9a-f]{64}", str(d.get("artifact_sha256", ""))) is not None, "SHA de contenido DMC ausente")
    require(type(d.get("artifact_bytes")) is int and d["artifact_bytes"] > 0 and type(d.get("row_count")) is int and d["row_count"] > 0, "Metadatos DMC incompletos")
    raw = p.parent / d["artifact_name"]
    require(raw.is_file() and not raw.is_symlink() and raw.stat().st_size == d["artifact_bytes"], "Artefacto DMC ausente o tamaño cambiado")
    runner.artifact(ref)
    return {"path": str(p), "rows_declared": d["row_count"], "content_sha256_declared": d["artifact_sha256"], "raw_content_checked": False}


def policy_check(policy, group, variable, adapter_sha256):
    rule = policy[group] if variable is None else policy[group][variable]
    require(all(_documentada(rule, _local(policy[b])) for b in ("valid_from", "valid_to")), "Política no acreditada para todo su intervalo")
    adapter = _adapter(adapter_sha256)
    if group == "clock":
        for boundary in ("valid_from", "valid_to"):
            adapter._utc(_local(policy[boundary]), rule)
    elif group == "coordinates":
        lat, lon = float(rule["latitude"]), float(rule["longitude"])
        require(np.isfinite([lat, lon]).all() and abs(lat) <= 90 and abs(lon) <= 180, "Coordenadas históricas inválidas")
    elif group == "measurements":
        _, statistic, minutes = adapter._medicion(rule, _local(policy["valid_from"]), variable)
        require((statistic, minutes) == ("instantaneous", 0), "Esta rama habilita sólo covariables DMC instantáneas")
    if group == "quality":
        unit = "m/s" if variable == "wind_speed_instant" else "degree" if variable == "wind_direction_instant" else UNIDADES.get(variable)
        require(unit is not None and rule.get("unit") == unit, "Unidad QC distinta de la normalizada")
        require(rule.get("method") in ("source_codes", "documented_numeric_checks") and isinstance(rule.get("accepted_source_codes"), list)
                and all(isinstance(c, str) for c in rule["accepted_source_codes"]), "Método/códigos QC no explícitos")
        if rule["method"] == "documented_numeric_checks":
            a, b = rule.get("minimum"), rule.get("maximum")
            require(type(a) in (int, float) and type(b) in (int, float) and np.isfinite([a, b]).all() and a <= b
                    and type(rule.get("allow_unknown_source_qc")) is bool, "Límites/tratamiento QC desconocido no explícitos")
    return {"station": policy["station_code"], "group": group, "variable": variable, "source": rule["source"]}


def base_preflight(audit, path, index_number):
    stage = f"base_{index_number}"
    cfg = audit.check(stage + ".config", stage, lambda: base.validar_config(runner.read_json(path)))
    if cfg is None:
        return False
    frames = {}
    for name, keys in (("targets", ["target_id", "ts_utc", "celda"]), ("celdas", ["celda", "lat", "lon"]),
                       ("enlaces", ["celda"]), ("estaticas", ["celda"]), ("lulc", ["celda", "anio"])):
        def load(name=name, keys=keys):
            ref = cfg["tables"][name]
            p = base._ref(ref, max_bytes=cfg["limits"]["max_source_bytes"])
            if name == "targets":
                require(0 < pq.ParquetFile(p).metadata.num_rows <= cfg["limits"]["max_target_rows"], "Targets exceden presupuesto")
            d = pd.read_parquet(p)
            base._ref(ref)
            require(set(keys) <= set(d) and not d.empty and not d[keys].isna().any().any() and not d.duplicated(keys).any(), "Grano/claves de tabla base inválidos")
            frames[name] = d
            return {"rows": len(d), "sha256": ref["sha256"]}
        audit.check(stage + ".table." + name, stage, load)
    if set(frames) == {"targets", "celdas", "enlaces", "estaticas", "lulc"}:
        audit.check(stage + ".grid", stage, lambda: base.metadata_grilla(frames["celdas"]))
        def links():
            t = frames["targets"]
            ts = utc_aware(t.ts_utc)
            require(ts.eq(ts.dt.floor("h")).all(), "Target no horario")
            require(not (set(t) & set(cfg["base_features"])) - {"lat", "lon"}, "Targets contienen base previa")
            for name in ("celdas", "enlaces", "estaticas", "lulc"):
                require(set(t.celda) <= set(frames[name].celda), "FK incompleta: " + name)
            for product in cfg["hourly_products"]:
                require(product + "_pixel" in frames["enlaces"], "Enlace de producto ausente: " + product)
                pix = frames["enlaces"][product + "_pixel"].to_numpy(float)
                require(np.isfinite(pix).all() and np.equal(pix, np.rint(pix)).all() and (pix >= -1).all(), "Pixel de enlace no entero/válido")
            require(np.isfinite(frames["lulc"].anio).all() and np.equal(frames["lulc"].anio, np.rint(frames["lulc"].anio)).all(), "Años LULC inválidos")
            for col in ("lat", "lon"):
                if col in t:
                    coords = t.merge(frames["celdas"][["celda", col]], on="celda", validate="many_to_one", suffixes=("", "_cell"))
                    require(np.allclose(coords[col], coords[col + "_cell"], rtol=0, atol=1e-10), "Target fuera del centro de celda")
            local_days = (ts - pd.Timedelta(hours=4)).dt.date
            require((local_days.max() - local_days.min()).days + 1 <= cfg["limits"]["max_days"], "Días exceden presupuesto")
            return {"targets": int(t.target_id.nunique()), "utc_hours": int(ts.nunique())}
        audit.check(stage + ".relations", stage, links)
    def source_index():
        p = base._ref(cfg["source_index"], max_bytes=cfg["limits"]["max_source_bytes"])
        idx = runner.read_json(p)
        base._ref(cfg["source_index"])
        # El AST sólo carga definiciones; no abre NetCDF/Parquet de fuentes.
        features, _ = base.lectores_legacy(cfg, idx)
        require(set(cfg["base_features"]) <= set(features.FEATURES_MODELO_BASE) - base.FORBIDDEN, "Whitelist fuera del legado")
        t = frames["targets"]
        ts = utc_aware(t.ts_utc)
        needed = []
        def indexed(key, lookup, *, missing_allowed=False):
            def resolve():
                ref = lookup()
                require(missing_allowed or ref is not None, "Referencia ausente no permitida")
                needed.append((key, ref))
                if ref is None:
                    return {"declared_missing": True}
                return {"sha256": ref["sha256"], "bytes": base._ref(ref, max_bytes=cfg["limits"]["max_source_bytes"]).stat().st_size}
            audit.check(stage + ".source." + key, stage, resolve)
        for product in cfg["hourly_products"]:
            for month in sorted(set(ts.dt.strftime("%Y%m"))):
                indexed(f"monthly.{product}.{month}", lambda product=product, month=month: idx["monthly"][product][month], missing_allowed=True)
        if set(cfg["base_features"]) & set(features.COLUMNAS_SATELITE):
            days = (ts - pd.Timedelta(hours=4)).dt.date
            for day in pd.date_range(pd.Timestamp(days.min()) - pd.Timedelta(days=15), days.max()):
                key = day.date().isoformat()
                def maiac_key(key=key):
                    m = idx["maiac"][key]
                    require(m is None or isinstance(m, dict), "MAIAC debe declarar refs o null")
                    return {"declared_missing": m is None}
                mstatus = audit.check(stage + f".index.maiac.{key}", stage, maiac_key)
                if mstatus and not mstatus["declared_missing"]:
                    for k in ("obs", "pasadas"):
                        indexed(f"maiac.{key}.{k}", lambda key=key, k=k: idx["maiac"][key][k])
                def orbit_key(key=key):
                    orbits = idx["no2_orbits"][key]
                    require(isinstance(orbits, list), "Ausencia de órbitas debe ser lista vacía explícita")
                    for i, ref in enumerate(orbits):
                        indexed(f"no2.{key}.{i}", lambda ref=ref: ref)
                    return {"orbits": len(orbits)}
                audit.check(stage + f".index.no2.{key}", stage, orbit_key)
        return {"index_sha256": cfg["source_index"]["sha256"], "references": len(needed),
                "declared_missing_months": sum(ref is None for _, ref in needed), "native_arrays_read": False}
    audit.check(stage + ".source_index", stage, source_index)
    if cfg["interpolation"]["products"]:
        def weights():
            d = pd.read_parquet(base._ref(cfg["tables"]["weights"], max_bytes=cfg["limits"]["max_source_bytes"]))
            require(base.hash_frame(d) == cfg["interpolation"]["weights_sha256"], "Identidad de pesos distinta")
            require(not d.celda.isna().any() and not d.celda.duplicated().any() and set(frames["targets"].celda) <= set(d.celda), "FK/grano de pesos inválido")
            for product in cfg["interpolation"]["products"]:
                w = d[[f"{product}_w{k}" for k in range(4)]].to_numpy(float)
                pix = d[[f"{product}_pix{k}" for k in range(4)]].to_numpy(float)
                require(np.isfinite(w).all() and (w >= 0).all() and (np.isclose(w.sum(1), 0) | np.isclose(w.sum(1), 1)).all()
                        and np.isfinite(pix).all() and np.equal(pix, np.rint(pix)).all() and (pix >= -1).all() and not ((w > 0) & (pix < 0)).any(), "Pesos/píxeles inválidos")
            return {"rows": len(d)}
        audit.check(stage + ".weights", stage, weights)
    return audit.ready(stage)


def preflight(cfg, *, config_path=None, base_configs=(), label=None, python=sys.executable):
    audit = Audit()
    audit.check("fit.schema", "fit", lambda: require(cfg.get("schema") == "environmental-dmc-experiment/3" and cfg.get("state") == "approved_experiment", "Configuración sigue en preparación"))
    audit.check("fit.authorization", "fit", lambda: require(cfg.get("fit_approval", {}).get("verified") is True and bool(cfg.get("fit_approval", {}).get("source")), "Autorización de ajuste sin documentar"))
    for key, role in (("decision_criterion", "a_priori_selection_rule"), ("qc_approval", "qc_dmc_documentada")):
        audit.check("fit." + key, "fit", lambda key=key, role=role: approved(cfg.get(key), role))
    audit.check("fit.definition", "fit", lambda: validate_definition(cfg))
    audit.check("fit.missing_policy", "fit", lambda: runner._politica_faltantes(cfg))
    def whitelist():
        cols = cfg.get("base_features")
        require(isinstance(cols, list) and bool(cols) and len(set(cols)) == len(cols)
                and all(isinstance(c, str) and bool(c) for c in cols) and not set(cols) & runner.FORBIDDEN, "Whitelist base vacía/duplicada/prohibida")
        return {"columns": cols}
    audit.check("fit.whitelist", "fit", whitelist)
    def budgets():
        limits = cfg["limits"]
        require(limits.get("threads") == 2 and type(limits.get("seconds")) is int and 1 <= limits["seconds"] <= 900
                and all(type(limits.get(k)) is int and limits[k] > 0 for k in ("max_rows", "max_fold_rows")), "Límites de recursos explícitos inválidos/pendientes")
        return limits
    audit.check("fit.limits", "fit", budgets)
    def training_spec():
        t = cfg["training"]
        require(t.get("pollutant") in runner.UNITS and t.get("observation_unit") == runner.UNITS[t["pollutant"]]
                and type(t.get("rounds")) is int and t["rounds"] > 0, "Contaminante/unidad/rondas pendientes o inválidos")
        return {k: t[k] for k in ("pollutant", "observation_unit", "rounds")}
    audit.check("fit.training_spec", "fit", training_spec)
    for name in runner.PINNED:
        audit.check("fit.pin." + name, "fit", lambda name=name: require(runner.sha_archivo(runner.V2 / name) == cfg["pins"][name], "SHA legado distinto: " + name))
    if label is not None:
        audit.check("fit.next_label", "fit", lambda: require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", label) is not None, "Etiqueta inválida para próximo comando"))
    audit.check("fit.operator", "fit", lambda: _operador(cfg["dmc"]["operator"]))
    variables = cfg.get("dmc", {}).get("variables") or []
    policies = cfg.get("dmc", {}).get("policies") or []
    audit.check("fit.variables", "fit", lambda: require(bool(variables) and len(variables) == len(set(variables))
                and all(v in UNIDADES for v in variables), "Variables DMC vacías/duplicadas/no habilitadas"))
    audit.check("fit.policies", "fit", lambda: require(bool(policies), "Políticas DMC ausentes"))
    def policy_identity():
        qc = approved(cfg["qc_approval"], "qc_dmc_documentada")
        require(qc.get("policies_sha256") == runner.hash_json(policies), "QC aprobada para otras políticas")
        for i, p in enumerate(policies):
            require(bool(p.get("station_code")) and _local(p["valid_from"]) <= _local(p["valid_to"]), "Política sin estación/intervalo válido")
            for previous in policies[:i]:
                if previous["station_code"] == p["station_code"]:
                    require(_local(previous["valid_to"]) < _local(p["valid_from"]) or _local(p["valid_to"]) < _local(previous["valid_from"]), "Políticas históricas solapadas")
        return {"policies_sha256": runner.hash_json(policies)}
    audit.check("fit.qc_policy_identity", "fit", policy_identity)
    needed = set(variables)
    if needed & {"wind_u", "wind_v"}:
        needed = (needed - {"wind_u", "wind_v"}) | {"wind_speed_instant", "wind_direction_instant"}
    for i, policy in enumerate(policies):
        for group, variable in [("clock", None), ("coordinates", None)] + [(g, v) for g in ("measurements", "quality") for v in sorted(needed)]:
            audit.check(f"fit.policy.{i}.{group}.{variable or 'all'}", "fit", lambda policy=policy, group=group, variable=variable: policy_check(policy, group, variable, cfg["pins"]["meteorologia_v2.py"]))
    complete = audit.check("fit.download", "fit", lambda: progress_complete(cfg))
    manifests = cfg.get("dmc", {}).get("manifests") or []
    audit.check("fit.manifests", "fit", lambda: require(bool(manifests), "Manifiestos DMC ausentes"))
    for i, ref in enumerate(manifests):
        if complete is not None:
            audit.check(f"fit.manifest.{i}", "fit", lambda ref=ref: manifest_metadata(ref))
        else:
            audit.defer(f"fit.manifest.{i}", "fit", "Descarga abierta/no acreditada; ni manifiesto ni crudo leídos")
    # Guarda intacta la guarda del runner, además de los detalles independientes.
    def fit_guard():
        for ref in (cfg.get("decision_criterion"), cfg.get("qc_approval"), cfg.get("base_feature_definition"),
                    cfg.get("training", {}).get("panel"), cfg.get("training", {}).get("folds")):
            non_dmc_artifact(ref)
        p = runner.plan(cfg)
        require(p["ready_for_experimental_fit"], "; ".join(p["gaps"]))
        return p
    audit.check("fit.runner_guard", "fit", fit_guard)
    limits = cfg.get("limits", {})
    panel = None
    def panel_check():
        nonlocal panel
        columns = ["target_id", "ts_utc", "lat", "lon", "obs", *(cfg.get("base_features") or [])]
        panel = read_table(cfg["training"]["panel"], limits.get("max_rows"), columns)
        return validate_panel(panel, cfg)
    audit.check("fit.panel", "fit", panel_check)
    def fold_check():
        folds = read_table(cfg["training"]["folds"], limits.get("max_fold_rows"), ["target_id", "ts_utc", "fold_id", "role", "kind"])
        folds["ts_utc"] = utc_aware(folds.ts_utc)
        require(panel is not None, "Panel no verificable; relación folds pendiente")
        runner.validate_folds(panel, folds)
        return {"rows": len(folds), "folds_by_kind": {str(k): int(d.fold_id.nunique()) for k, d in folds.groupby("kind")}}
    audit.check("fit.folds", "fit", fold_check)
    prod = cfg.get("production", {})
    grid = None
    def grid_check():
        nonlocal grid
        info = prod["grid"]
        grid = read_table(info["artifact"], limits.get("max_rows"), ["grid_id", "lat", "lon"])
        require(not grid.grid_id.isna().any() and not grid.grid_id.duplicated().any(), "Ids grilla nulos/duplicados")
        validar_geometria_grid(info, grid)
        return {"cells": len(grid), "geometry": info.get("tipo", "metrica_regular")}
    audit.check("production.grid", "production", grid_check)
    parts = prod.get("prepared_grid_parts") or []
    audit.check("production.parts", "production", lambda: require(bool(parts), "Partes grilla ausentes"))
    last = None
    for i, ref in enumerate(parts):
        def part_check(ref=ref):
            nonlocal last
            d = read_table(ref, limits.get("max_rows"), ["grid_id", "target_id", "ts_utc", "lat", "lon", *(cfg.get("base_features") or [])])
            d["ts_utc"] = utc_aware(d.ts_utc)
            require(grid is not None, "Grilla no verificable")
            require(not d.duplicated(["grid_id", "ts_utc"]).any() and not d.duplicated(["target_id", "ts_utc"]).any(), "Parte con claves duplicadas")
            require(d.groupby("ts_utc").grid_id.apply(lambda s: set(s) == set(grid.grid_id)).all(), "Soporte grilla×hora incompleto")
            hours = d.ts_utc.drop_duplicates().sort_values()
            require(hours.eq(hours.dt.floor("h")).all() and hours.diff().dropna().eq(pd.Timedelta(hours=1)).all(), "Parte no horaria/continua")
            require(last is None or hours.iloc[0] == last + pd.Timedelta(hours=1), "Partes discontinuas/solapadas")
            joined = d.merge(grid[["grid_id", "lat", "lon"]], on="grid_id", validate="many_to_one", suffixes=("", "_grid"))
            require(np.allclose(joined[["lat", "lon"]], joined[["lat_grid", "lon_grid"]], rtol=0, atol=1e-12), "Centros distintos de grilla aprobada")
            runner.validar_predictores(d, cfg, cfg["base_features"])
            last = hours.iloc[-1]
            return {"rows": len(d), "hours": len(hours), "start_utc": hours.iloc[0].isoformat(), "end_utc": last.isoformat()}
        audit.check(f"production.part.{i}", "production", part_check)
    for key, role in (("selection_approval", "selected_environmental_model"), ("oof_approval", "validacion_ambiental_agrupada")):
        audit.check("production." + key, "production", lambda key=key, role=role: approved(prod.get(key), role))
    def production_guard():
        non_dmc_artifact(prod.get("selected_model_manifest"))
        for key in ("selection_approval", "oof_approval"):
            non_dmc_artifact(prod.get(key))
        p = production.plan(cfg)
        require(p["ready_to_produce"], "; ".join(p["gaps"]))
        manifest = runner.read_json(non_dmc_artifact(prod["selected_model_manifest"]))
        path = Path(prod["selected_model_manifest"]["path"])
        for name, sha in ((manifest["model_file"], manifest["model_sha256"]), (manifest["oof"]["file"], manifest["oof"]["sha256"])):
            require(Path(name).name == name, "Modelo/OOF fuera del manifiesto")
            non_dmc_artifact({"path": str(path.parent / name), "sha256": sha})
        return p
    audit.check("production.runner_guard", "production", production_guard)
    bases_ready = [base_preflight(audit, Path(path), i) for i, path in enumerate(base_configs)]
    fit_ready = audit.ready("fit") and all(bases_ready)
    produce_ready = fit_ready and audit.ready("production")
    next_commands = []
    if config_path and label and (produce_ready or fit_ready):
        action, script = ("predict", "produccion_v3.py") if produce_ready else ("train", "runner_v3.py")
        argv = [str(python), "-B", str(runner.HERE / script), action, "--config", str(Path(config_path).resolve()), "--label", label]
        next_commands.append({"stage": "production" if produce_ready else "fit", "argv": argv, "shell": shlex.join(argv), "executed": False})
    return {"schema": "environmental-dmc-preflight/3", "read_only": True, "raw_dmc_read": False,
            "ready_for_experimental_fit": fit_ready, "ready_to_produce": produce_ready,
            "base_preparation_ready": bases_ready, "checks": audit.checks,
            "pending": [c["id"] for c in audit.checks if c["status"] != "passed"], "next_commands": next_commands,
            "note": "Comandos sólo propuestos. Requieren etiqueta nueva. Hashes/guardas no sustituyen revisión científica; el ajuste real y la comparación completa v2 siguen separados."}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=runner.HERE / "config_preparacion_v3.json")
    ap.add_argument("--base-config", type=Path, action="append", default=[])
    ap.add_argument("--label", help="Etiqueta nueva para proponer el próximo comando; no se ejecuta")
    ap.add_argument("--report", type=Path, help="Informe nuevo; nunca sobrescribe")
    args = ap.parse_args(argv)
    result = preflight(runner.read_json(args.config), config_path=args.config, base_configs=args.base_config, label=args.label)
    payload = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.report:
        with args.report.open("x", encoding="utf-8") as stream:
            stream.write(payload)
    print(payload, end="")
    return 0 if result["ready_to_produce"] or result["ready_for_experimental_fit"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
