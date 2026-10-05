#!/usr/bin/env python3
"""Convierte el MERRA-2 local a meses nativos chilenos, sin descargar ni imputar.

Reutiliza el normalizador científico sin editarlo. Añade comparación exhaustiva
con cada fuente, publicación sin sobrescritura, procedencia archivada y retiro
opcional del legado sólo después de certificado durable. Meses incompletos
quedan pendientes. RH2M y metadatos heredados no se reinterpretan silenciosamente.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import uuid

import numpy as np
import pandas as pd
from netCDF4 import Dataset
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parent))
import normalizar_reanalisis_chile as nr

VERSION = "1.1.0"
DAILY_CONTRACT = "merra2.daily-exact-24-hh30.v1"
VOLUME = Path("/Volumes/Datos")
VOLUME_UUID = "54B3D309-A503-44C6-9229-581F3E4FECE3"
SPEC = nr.PRODUCTOS["merra2_meteo"]
LEGACY = SPEC.salida.parent / "raw_chile_horario"
CONTROL = SPEC.salida / "_control_transformacion"
SOURCE_NAME = re.compile(r"M2_merra2_hourly_(\d{8})_chile\.nc\Z")


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def guard(path, reserve=100):
    if reserve < 100 or not VOLUME.is_mount():
        raise RuntimeError("Se exige volumen externo montado y reserva >=100 GiB")
    real = Path(path).resolve()
    if VOLUME not in real.parents:
        raise RuntimeError(f"Destino fuera de /Volumes/Datos: {real}")
    info = plistlib.loads(subprocess.check_output(["diskutil", "info", "-plist", str(VOLUME)]))
    if info.get("VolumeUUID") != VOLUME_UUID:
        raise RuntimeError("El UUID del disco externo no corresponde")
    free = shutil.disk_usage(VOLUME).free
    # Reserva también margen de trabajo, no sólo el resultado ya escrito.
    if free < (reserve + 1) * 2**30:
        raise RuntimeError("Reserva insuficiente: se preservan100GiB más1GiB de trabajo")
    return free


def write_json(path, data, *, immutable=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".part")
    try:
        with tmp.open("xb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        if immutable:
            try:
                os.link(tmp, path)
            except FileExistsError:
                if path.read_bytes() != payload:
                    raise RuntimeError(f"No se sobrescribe evidencia previa: {path}")
        else:
            os.replace(tmp, path)
        sync_dir(path.parent)
    finally:
        # Únicamente nuestro JSON temporal, nunca fuentes ni artefactos previos.
        tmp.unlink(missing_ok=True)


@contextmanager
def supervisor_lock(control):
    control.mkdir(parents=True, exist_ok=True)
    with (control / "supervisor.lock").open("a+") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Ya existe un transformador MERRA-2 activo") from exc
        yield


def event(control, execution, kind, **details):
    record = {"utc": utc(), "execution_id": execution, "evento": kind, **details}
    with (control / "eventos.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def archive_code(control):
    folder = Path(__file__).resolve().parent
    files = [Path(__file__).resolve(), Path(nr.__file__).resolve(), folder / "_chile_aoi.py"]
    hashes = {p.name: sha(p) for p in files}
    runtime = {"python": platform.python_version(), "executable": sys.executable,
               "packages": {n: importlib.metadata.version(n) for n in
                            ("numpy", "pandas", "netCDF4", "xarray", "geopandas", "shapely", "pyarrow")},
               "hashes": hashes, "contract_version": VERSION}
    bundle = control / "codigo" / digest(runtime)
    bundle.mkdir(parents=True, exist_ok=True)
    for source in files:
        dest = bundle / source.name
        if not dest.exists():
            with source.open("rb") as src, dest.open("xb") as dst:
                shutil.copyfileobj(src, dst)
                dst.flush()
                os.fsync(dst.fileno())
        if sha(dest) != hashes[source.name]:
            raise RuntimeError("Código archivado alterado")
    write_json(bundle / "runtime.json", runtime, immutable=True)
    sync_dir(bundle)
    return {"bundle": str(bundle), "runtime_sha256": sha(bundle / "runtime.json"), **runtime}


def source_inventory(period, legacy=LEGACY):
    period = pd.Period(period, freq="M")
    sources = sorted(Path(legacy).glob(f"M2_merra2_hourly_{period.strftime('%Y%m')}??_chile.nc"))
    expected = {d.strftime("%Y%m%d") for d in pd.date_range(period.start_time, period.end_time, freq="D")}
    actual = set()
    for path in sources:
        match = SOURCE_NAME.fullmatch(path.name)
        if path.is_symlink() or not match or path.resolve().parent != Path(legacy).resolve():
            raise RuntimeError(f"Fuente fuera del legado permitido: {path}")
        if match[1] not in expected:
            raise ValueError(f"Fecha fuente fuera del mes/calendario permitido: {path}")
        if match[1] in actual:
            raise ValueError("Día fuente duplicado")
        actual.add(match[1])
    return sources, sorted(expected - actual)


def validate_source_day(path, period):
    """El archivo completo, no sólo su intersección mensual, debe ser un día."""
    path = Path(path)
    match = SOURCE_NAME.fullmatch(path.name)
    if not match:
        raise ValueError(f"Nombre diario MERRA-2 inválido: {path}")
    try:
        day = pd.to_datetime(match[1], format="%Y%m%d", utc=True)
    except ValueError as exc:
        raise ValueError(f"Fecha diaria inválida: {path}") from exc
    if day.tz_localize(None).to_period("M") != pd.Period(period, "M"):
        raise ValueError(f"Fuente pertenece a otro mes: {path}")
    expected = pd.date_range(day + pd.Timedelta(minutes=30), periods=24, freq="h")
    with xr.open_dataset(path) as source:
        name = nr._coord(source, ("valid_time", "time"), "tiempo")
        times = pd.DatetimeIndex(pd.to_datetime(np.asarray(source[name]).reshape(-1), utc=True))
    if not times.equals(expected):
        raise ValueError(f"{path.name}: se exigen exactamente 24 horas HH:30 UTC de su fecha, sin extras")


def validate_record_days(records, period):
    """El certificado también debe enumerar una y sólo una fuente por día."""
    period = pd.Period(period, "M")
    expected = {d.strftime("%Y%m%d") for d in pd.date_range(period.start_time, period.end_time, freq="D")}
    actual = []
    for record in records:
        path = Path(record["ruta_al_normalizar"])
        match = SOURCE_NAME.fullmatch(path.name)
        if not match or record["archivo"] != path.name or match[1] not in expected:
            raise ValueError("Certificado con fuente ajena al día/mes declarado")
        actual.append(match[1])
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Certificado no contiene exactamente una fuente por día del mes")


def json_attr(value):
    if isinstance(value, np.ndarray):
        return {"dtype": str(value.dtype), "shape": list(value.shape), "values": json_attr(value.tolist())}
    if isinstance(value, np.generic):
        return json_attr(value.item())
    if isinstance(value, list):
        return [json_attr(x) for x in value]
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite_float": str(value)}
    return value


def inspect_sources(sources):
    records = []
    for p in sources:
        before = p.stat()
        h = sha(p)
        with Dataset(p) as n:
            metadata = {"global": {k: json_attr(n.getncattr(k)) for k in n.ncattrs()},
                        "variables": {k: {"dtype": str(v.dtype), "dimensions": list(v.dimensions),
                                          "attrs": {a: json_attr(v.getncattr(a)) for a in v.ncattrs()}}
                                      for k, v in n.variables.items()}}
        after = p.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError(f"Fuente cambió mientras se leía: {p}")
        records.append({"archivo": p.name, "ruta_al_normalizar": str(p.resolve()),
                        "bytes": before.st_size, "mtime_ns": before.st_mtime_ns,
                        "sha256": h, "metadata_original": metadata})
    return records


def equal_values(actual, expected, label):
    if actual.dtype != expected.dtype or not np.array_equal(actual, expected, equal_nan=True):
        raise ValueError(f"No se conservaron exactamente los valores/tipo: {label}")


def compare_full(output, sources, period, spec=SPEC):
    """Reabre todos los valores; cada día debe aportar cada píxel y variable."""
    cat_path = spec.salida / "catalogo_pixeles.parquet"
    cat = pd.read_parquet(cat_path)
    expected_time = nr._esperado(spec, period)
    summary = nr.validar_salida(output, spec, period, cat_path, False)
    count = 0
    with Dataset(output) as target:
        target.set_auto_maskandscale(False)
        for path in sources:
            validate_source_day(path, period)
            inv = nr._inventario(path, spec, period)
            if inv is None or set(inv["variables"]) != set(spec.requeridas):
                raise ValueError(f"Día sin las nueve variables: {path}")
            op, si, sj = nr._mapear_pixeles(cat, inv)
            if not np.array_equal(op, np.arange(len(cat))):
                raise ValueError(f"La fuente no cubre todos los píxeles chilenos: {path}")
            positions = expected_time.get_indexer(inv["times"])
            with xr.open_dataset(path) as source:
                allowed = set(inv["variables"].values())
                if set(source.data_vars) != allowed:
                    raise ValueError(f"Variables fuente adicionales no conservadas: {path}")
                for name, original in inv["variables"].items():
                    if source[original].dtype != np.dtype("float32"):
                        raise ValueError(f"Conversión no autorizada de precisión: {path}:{original}")
                    for ss, oo in nr._segmentos(inv["src_time_idx"], positions):
                        values = nr._leer_directa(source, original, inv, ss)[:, si, sj]
                        got = np.asarray(target[name][oo, :])
                        equal_values(got, values, f"{path.name}:{name}")
                        count += values.size
                    # Unidades originales conocidas deben seguir iguales, nunca supuestas.
                    if "units" in source[original].attrs:
                        if target[name].getncattr("units") != source[original].attrs["units"]:
                            raise ValueError(f"Unidades cambiadas: {path}:{name}")
    return {**summary, "valores_comparados": count, "igualdad_exacta_incluidos_nan": True,
            "source_day_contract": DAILY_CONTRACT,
            "limitaciones_metadata": ["RH2M heredada puede carecer de unidades/formula verificable; se conserva sin reinterpretar.",
                                     "La procedencia desde proveedor de los derivados legacy no se inventa; se archivan metadatos y hash de cada entrada."]}


def check_sources(records, *, allow_absent=False):
    for r in records:
        p = Path(r["ruta_al_normalizar"])
        if not p.exists() and allow_absent:
            continue
        if p.is_symlink() or not p.is_file() or p.stat().st_size != r["bytes"] or sha(p) != r["sha256"]:
            raise RuntimeError(f"Fuente ausente o modificada: {p}")


def validate_certificate(cert, spec=SPEC):
    period = pd.Period(cert["period"], "M")
    validate_record_days(cert["sources"], period)
    expected_output, expected_manifest = nr.rutas_periodo(spec, period)
    output = Path(cert["output"])
    if output.is_symlink() or output.resolve() != expected_output.resolve():
        raise RuntimeError("Salida del certificado fuera del mes permitido")
    expected_refs = [spec.salida / "catalogo_pixeles.parquet", spec.salida / "relacion_pixel_comuna.parquet",
                     spec.salida / "metadata/catalogo_manifest.json", expected_manifest]
    if [Path(r["path"]).resolve() for r in cert["references"]] != [p.resolve() for p in expected_refs]:
        raise RuntimeError("Referencias del certificado no corresponden al producto/mes")
    if sha(output) != cert["output_sha256"] or output.stat().st_size != cert["output_bytes"]:
        raise RuntimeError("Salida publicada alterada")
    for ref in cert["references"]:
        if sha(ref["path"]) != ref["sha256"]:
            raise RuntimeError(f"Referencia alterada: {ref['path']}")
    code = cert["code"]
    if sha(Path(code["bundle"]) / "runtime.json") != code["runtime_sha256"]:
        raise RuntimeError("Runtime archivado alterado")
    for name, expected in code["hashes"].items():
        if sha(Path(code["bundle"]) / name) != expected:
            raise RuntimeError("Archivo de código alterado")
    nr.validar_salida(output, spec, period, spec.salida / "catalogo_pixeles.parquet", False)


def prior_strict_retirement(control, certificate_hash, missing):
    """Una ausencia sólo se admite tras intención durable con el contrato nuevo."""
    allowed = set()
    wal = Path(control) / "eventos.jsonl"
    if wal.exists():
        for line in wal.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if (record.get("evento") == "retiro_legado_autorizado"
                    and record.get("certificate_sha256") == certificate_hash
                    and record.get("source_day_contract") == DAILY_CONTRACT):
                allowed.update((r["ruta_al_normalizar"], r["sha256"]) for r in record["sources"])
    if any((r["ruta_al_normalizar"], r["sha256"]) not in allowed for r in missing):
        raise RuntimeError("Fuente ausente sin autorización durable bajo el contrato diario estricto")


def retire(cert, control, execution, legacy=LEGACY):
    """No llama el borrador legacy: WAL durable ANTES del primer unlink."""
    validate_certificate(cert)
    cert_path = Path(control) / "meses" / f"{pd.Period(cert['period'], 'M')}.json"
    if cert_path.is_symlink() or json.loads(cert_path.read_text(encoding="utf-8")) != cert:
        raise RuntimeError("Certificado de retiro no coincide con el archivo publicado")
    certificate_hash = sha(cert_path)
    records = cert["sources"]
    present = []
    missing = []
    for r in records:
        p = Path(r["ruta_al_normalizar"])
        if p.resolve().parent != Path(legacy).resolve() or not SOURCE_NAME.fullmatch(p.name):
            raise RuntimeError("Fuente no pertenece al mes legado permitido")
        if p.exists():
            present.append(r)
        else:
            missing.append(r)
    if missing:
        prior_strict_retirement(control, certificate_hash, missing)
    check_sources(present)
    if not present:
        return 0
    # También para certificados v1.0: nunca confiar sólo en su antigua comparación
    # mensual, que podía descartar silenciosamente horas externas al mes.
    validation = compare_full(Path(cert["output"]), [Path(r["ruta_al_normalizar"]) for r in present],
                              pd.Period(cert["period"], "M"))
    check_sources(present)
    validate_certificate(cert)
    if sha(cert_path) != certificate_hash:
        raise RuntimeError("Certificado cambió durante la revalidación de retiro")
    event(control, execution, "retiro_legado_autorizado", period=cert["period"],
          certificate_sha256=certificate_hash, source_day_contract=DAILY_CONTRACT,
          validation=validation, output_sha256=cert["output_sha256"], sources=present)
    total = 0
    for r in present:
        p = Path(r["ruta_al_normalizar"])
        # Segunda comprobación inmediatamente antes del borrado de cada archivo.
        check_sources([r])
        p.unlink()
        sync_dir(p.parent)
        total += r["bytes"]
        event(control, execution, "fuente_retirada", period=cert["period"],
              source=str(p), source_sha256=r["sha256"], bytes=r["bytes"])
    return total


def publish_file(source, target, expected_hash):
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except FileExistsError:
        if sha(target) != expected_hash:
            raise RuntimeError(f"No se sobrescribe una salida previa: {target}")
    sync_dir(target.parent)
    if sha(target) != expected_hash:
        raise RuntimeError("Publicación no coincide con preparación")


def clean_stage_copies(cert, control):
    """Reanudable: sólo copias derivadas de esta transacción ya certificada."""
    stage = Path(cert["stage"])
    if stage.resolve().parent != (control / "staging").resolve():
        raise RuntimeError("Staging fuera del control de esta transformación")
    prep = json.loads((stage / "prepared.json").read_text())
    if prep["existing_publication"]:
        return
    expected = {stage / "catalogo_pixeles.parquet": cert["references"][0]["sha256"],
                stage / "relacion_pixel_comuna.parquet": cert["references"][1]["sha256"],
                stage / "metadata/catalogo_manifest.json": cert["references"][2]["sha256"],
                Path(prep["staged_output"]): cert["output_sha256"],
                Path(prep["staged_manifest"]): prep["manifest_sha256"]}
    for p, h in expected.items():
        if stage.resolve() not in p.resolve().parents or p.is_symlink():
            raise RuntimeError("Copia de trabajo ajena a esta transacción")
        if p.exists():
            if sha(p) != h:
                raise RuntimeError("Copia staging modificada: se conserva")
            p.unlink()
    # El manifiesto interno del normalizador también es procedencia: conservarlo.
    # identity/prepared y dicho JSON son pequeños registros, no datos temporales.


def process_month(period, code, execution, *, reserve=100, retire_legacy=False):
    period = pd.Period(period, freq="M")
    guard(SPEC.salida, reserve)
    for name, expected in code["hashes"].items():
        if sha(Path(__file__).resolve().parent / name) != expected:
            raise RuntimeError("El código cambió durante la ejecución; se preservan fuentes")
    cert_path = CONTROL / "meses" / f"{period}.json"
    if cert_path.exists():
        with nr.bloqueo(SPEC.salida / ".locks" / f"normalizar_{period.strftime('%Y%m')}.lock"):
            cert = json.loads(cert_path.read_text())
            if pd.Period(cert["period"], "M") != period:
                raise RuntimeError("Certificado no corresponde al mes solicitado")
            validate_certificate(cert)
            freed = retire(cert, CONTROL, execution) if retire_legacy else 0
            clean_stage_copies(cert, CONTROL)
            event(CONTROL, execution, "mes_previamente_validado", period=str(period), bytes_retired=freed)
            return {"period": str(period), "status": "validated_existing", "bytes_retired": freed}
    sources, missing = source_inventory(period)
    if missing:
        event(CONTROL, execution, "mes_pendiente", period=str(period), missing_days=missing)
        return {"period": str(period), "status": "pending_local_sources", "missing_days": missing}
    # Catálogos científicos existentes ya auditados, o reconstruidos por el motor original.
    cat, rel, cm = nr.crear_catalogos(SPEC, nr.COMUNAS)
    references = [{"path": str(p), "sha256": sha(p)} for p in (cat, rel, cm)]
    records = inspect_sources(sources)
    ident = digest({"period": str(period), "sources": [(r["archivo"], r["sha256"]) for r in records],
                    "references": references, "code": code})
    stage = CONTROL / "staging" / ident
    stage.mkdir(parents=True, exist_ok=True)
    identity_path = stage / "identity.json"
    identity = {"period": str(period), "sources": records, "references": references, "code": code}
    write_json(identity_path, identity, immutable=True)
    output, manifest = nr.rutas_periodo(SPEC, period)
    # Mismo bloqueo mensual que usa el descargador; jamás cambia su código activo.
    with nr.bloqueo(SPEC.salida / ".locks" / f"normalizar_{period.strftime('%Y%m')}.lock"):
        prepared_path = stage / "prepared.json"
        if prepared_path.exists():
            prepared = json.loads(prepared_path.read_text())
            if prepared["identity_sha256"] != sha(identity_path):
                raise RuntimeError("Identidad staging inconsistente")
        elif output.exists() or manifest.exists():
            if not (output.exists() and manifest.exists() and nr.salida_vigente(SPEC, period, aceptar_parcial=False)):
                raise RuntimeError("Publicación previa incompleta/inconsistente: requiere diagnóstico, no sobrescritura")
            check = compare_full(output, sources, period)
            check_sources(records)
            prepared = {"existing_publication": True, "identity_sha256": sha(identity_path),
                        "output_sha256": sha(output), "output_bytes": output.stat().st_size,
                        "manifest_sha256": sha(manifest), "validation": check}
            write_json(prepared_path, prepared, immutable=True)
        else:
            stage_spec = replace(SPEC, salida=stage)
            for origin, dest in ((cat, stage / cat.name), (rel, stage / rel.name),
                                 (cm, stage / "metadata" / cm.name)):
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    with origin.open("rb") as src, dest.open("xb") as dst:
                        shutil.copyfileobj(src, dst); dst.flush(); os.fsync(dst.fileno())
                if sha(dest) != sha(origin):
                    raise RuntimeError("Catálogo staging inconsistente")
            new_output, new_manifest = nr.normalizar_mes(stage_spec, sources, period,
                                                        permitir_parcial=False, espacio_minimo_gib=reserve)
            check = compare_full(new_output, sources, period)
            check_sources(records)
            meta = json.loads(new_manifest.read_text())
            meta["salida"]["archivo"] = str(output)
            meta["catalogo"].update(archivo=str(cat), manifest=str(cm))
            meta["relacion_pixel_comuna"]["archivo"] = str(rel)
            meta["transformacion_local"] = {"script": str(Path(__file__).resolve()), "code": code,
                                           "validation": check, "source_identity": str(identity_path)}
            meta["adquisicion"] = {"estado_periodo": "completo", "modo": "local_only", "network_requests": 0,
                                  "sources_from_legacy": len(sources), "upstream_legacy_provenance_not_reconstructed": True}
            publish_manifest = stage / "publication_manifest.json"
            write_json(publish_manifest, meta, immutable=True)
            prepared = {"existing_publication": False, "identity_sha256": sha(identity_path),
                        "output_sha256": sha(new_output), "output_bytes": new_output.stat().st_size,
                        "manifest_sha256": sha(publish_manifest), "staged_output": str(new_output),
                        "staged_manifest": str(publish_manifest), "validation": check}
            write_json(prepared_path, prepared, immutable=True)
        if not prepared["existing_publication"]:
            check_sources(records)
            publish_file(Path(prepared["staged_output"]), output, prepared["output_sha256"])
            publish_file(Path(prepared["staged_manifest"]), manifest, prepared["manifest_sha256"])
        cert = {"schema": "airpollution.merra2.local-transformation.v1", "period": str(period),
                "published_utc": utc(), "output": str(output), "output_sha256": prepared["output_sha256"],
                "output_bytes": prepared["output_bytes"], "references": references + [{"path": str(manifest), "sha256": prepared["manifest_sha256"]}],
                "sources": records, "code": code, "validation": prepared["validation"],
                "original_sources_not_deleted_by_certificate_creation": True, "stage": str(stage)}
        validate_certificate(cert)
        write_json(cert_path, cert, immutable=True)
        event(CONTROL, execution, "mes_validado_antes_retiro", period=str(period),
              certificate=str(cert_path), certificate_sha256=sha(cert_path), output_sha256=cert["output_sha256"])
        freed = retire(cert, CONTROL, execution) if retire_legacy else 0
        clean_stage_copies(cert, CONTROL)
        event(CONTROL, execution, "mes_completado", period=str(period), bytes_retired=freed)
        return {"period": str(period), "status": "validated", "bytes_retired": freed,
                "pixels": prepared["validation"]["pixeles"], "hours": prepared["validation"]["pasos_temporales"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--desde", default="2000-01")
    ap.add_argument("--hasta", default="2026-05")
    ap.add_argument("--reserva-gib", type=float, default=100)
    ap.add_argument("--retirar-legado-validado", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    first, last = pd.Period(args.desde, "M"), pd.Period(args.hasta, "M")
    if first < pd.Period("2000-01", "M") or last < first:
        ap.error("Rango mensual inválido: inicio >=2000-01")
    guard(SPEC.salida, args.reserva_gib)
    periods = list(pd.period_range(first, last, freq="M"))
    if args.dry_run:
        print(json.dumps({"mode": "read_only", "months": [{"period": str(p), "sources": len(source_inventory(p)[0]), "missing_days": source_inventory(p)[1]} for p in periods]}))
        return 0
    execution = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    with supervisor_lock(CONTROL):
        code = archive_code(CONTROL)
        config = {"execution_id": execution, "pid": os.getpid(), "from": str(first), "to": str(last),
                  "reserve_gib": args.reserva_gib, "retire_legacy": args.retirar_legado_validado,
                  "code": code, "status": "running", "started_utc": utc()}
        write_json(CONTROL / "ejecucion_actual.json", config)
        event(CONTROL, execution, "inicio", config=config)
        results = []
        try:
            for period in periods:
                result = process_month(period, code, execution, reserve=args.reserva_gib,
                                       retire_legacy=args.retirar_legado_validado)
                results.append(result)
                state = {"execution_id": execution, "utc": utc(), "status": "running",
                         "last_period": str(period), "completed_months": sum(x["status"].startswith("validated") for x in results),
                         "pending_months": sum(x["status"].startswith("pending") for x in results),
                         "bytes_retired": sum(x.get("bytes_retired", 0) for x in results), "results": results}
                write_json(CONTROL / "avance.json", state)
                print(json.dumps(result), flush=True)
            state["status"] = "complete" if not state["pending_months"] else "finished_with_pending_sources"
            write_json(CONTROL / "fin.json", state)
            event(CONTROL, execution, "fin", status=state["status"])
            return 0 if not state["pending_months"] else 2
        except BaseException as exc:
            event(CONTROL, execution, "fallo_protegido", error_type=type(exc).__name__, detail=str(exc))
            write_json(CONTROL / "fin.json", {"execution_id": execution, "utc": utc(), "status": "failed_protected", "detail": str(exc)})
            raise


if __name__ == "__main__":
    raise SystemExit(main())
