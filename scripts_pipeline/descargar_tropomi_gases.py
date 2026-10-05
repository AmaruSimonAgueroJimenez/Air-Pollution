#!/usr/bin/env python3
"""CO, SO2, O3 total, HCHO y CH4 L2 nativos: descarga → Chile → validación → retiro.

Motor independiente del migrador NO2. Dos procesos como máximo, un gránulo
por proceso, calendario diario equilibrado entre gases. Los ceros CMR quedan
pendientes y se vuelven a consultar. El histórico se reanuda por transacciones
durables, nunca por la mera existencia de un archivo. No remuestrea ni filtra QA.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import fcntl
import hashlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import unquote, urlsplit
import uuid

from _chile_aoi import seleccionar
from _common import CONTAMINANTES, DATA, load_env
from _manifiesto_satelital import sha256, sha256_conjunto_shapefile

GIB = 2**30
CONTRATO = "tropomi-gases-pixel-v1"
VOLUME_UUID = "54B3D309-A503-44C6-9229-581F3E4FECE3"
PRODUCTOS = {
    "co": ("S5P_L2__CO_____HiR", "C2087132178-GES_DISC"),
    "so2": ("S5P_L2__SO2____HiR", "C1918210292-GES_DISC"),
    "o3": ("S5P_L2__O3_TOT_HiR", "C1918209846-GES_DISC"),
    "hcho": ("S5P_L2__HCHO___HiR", "C1918210023-GES_DISC"),
    "ch4": ("S5P_L2__CH4____HiR", "C2087216530-GES_DISC"),
}
PREFIJOS_NATIVOS = {"co": "CO_____", "so2": "SO2____", "o3": "O3_____",
                    "hcho": "HCHO___", "ch4": "CH4____"}
NOMBRE = re.compile(r"_(\d{8}T\d{6})_(\d{8}T\d{6})_(\d{5})_(\d{2})_(\d{6})_(\d{8}T\d{6})\.nc$")
log = logging.getLogger("tropomi_gases")


class LimiteSeguro(RuntimeError):
    """Pausa recuperable de cuota/espacio; no autoriza retirar datos."""


def ahora():
    return datetime.now(timezone.utc).isoformat()


def fsync_archivo(path):
    with Path(path).open("rb") as f:
        os.fsync(f.fileno())


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def mkdir_durable(path):
    """Persiste cada enlace nuevo; un fallo conserva datos y permite reintentar."""
    path = Path(path)
    missing = []
    ancestor = path
    while not ancestor.is_dir():
        if ancestor.exists():
            raise NotADirectoryError(ancestor)
        missing.append(ancestor)
        ancestor = ancestor.parent
    # El ancestro puede venir de un intento cuyo fsync del padre falló.
    fsync_dir(ancestor)
    fsync_dir(ancestor.parent)
    for directory in reversed(missing):
        directory.mkdir(exist_ok=True)
        fsync_dir(directory)
        fsync_dir(directory.parent)


def atomico(path, value):
    path = Path(path)
    mkdir_durable(path.parent)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temp.open("x", encoding="utf8") as f:
        json.dump(value, f, ensure_ascii=False, sort_keys=True, default=str)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)
    fsync_dir(path.parent)


def evento(cfg, producto, nombre, **extra):
    path = Path(cfg["root"]) / "_control_gases" / f"{producto}.jsonl"
    mkdir_durable(path.parent)
    data = {**extra, "schema": CONTRATO, "execution_id": cfg["execution_id"],
            "utc": ahora(), "gas": producto, "evento": nombre}
    if "utc" in extra:
        data["transaction_utc"] = extra["utc"]
    with path.open("a", encoding="utf8") as f:
        f.write(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())
    fsync_dir(path.parent)


@contextmanager
def bloqueo(path, esperar=False):
    path = Path(path)
    mkdir_durable(path.parent)
    with path.open("a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX | (0 if esperar else fcntl.LOCK_NB))
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def bytes_arbol(path):
    return sum(p.stat().st_blocks * 512 for p in Path(path).rglob("*") if p.is_file())


def comprobar_disco(cfg, pendiente=0):
    root = Path(cfg["root"])
    # No continuar escribiendo a una carpeta local si se desmonta el disco.
    if cfg.get("volume_uuid"):
        info = plistlib.loads(subprocess.check_output(
            ["diskutil", "info", "-plist", "/Volumes/Datos"]))
        if info.get("VolumeUUID") != cfg["volume_uuid"]:
            raise LimiteSeguro("disco externo ausente o UUID distinto")
    free = shutil.disk_usage(root).free
    if free - pendiente < cfg["reserva_gib"] * GIB:
        raise LimiteSeguro("reserva de espacio insuficiente")
    return free


@contextmanager
def reservar(cfg, size):
    control = Path(cfg["root"]) / "_control_gases"
    path = control / "reservas.json"
    pid = str(os.getpid())
    allocation = max(int(size * 3), GIB)
    with bloqueo(control / "capacidad.lock", esperar=True):
        reservations = json.loads(path.read_text()) if path.exists() else {}
        for old in list(reservations):
            try:
                os.kill(int(old), 0)
            except ProcessLookupError:
                reservations.pop(old)
        others = sum(reservations.values())
        comprobar_disco(cfg, allocation + others)
        staging = sum(bytes_arbol(Path(cfg["root"]) / p.upper() / "_staging_gases")
                      for p in PRODUCTOS)
        retained = sum(bytes_arbol(Path(cfg["root"]) / p.upper() / "chile_l2_nativo_v1")
                       for p in PRODUCTOS)
        if staging + others + allocation > cfg["staging_gib"] * GIB:
            raise LimiteSeguro("cuota temporal alcanzada; fuentes protegidas")
        if retained + others + allocation > cfg["cuota_gib"] * GIB:
            raise LimiteSeguro("cuota de nuevos productos alcanzada")
        reservations[pid] = allocation
        atomico(path, reservations)
    try:
        yield
    finally:
        with bloqueo(control / "capacidad.lock", esperar=True):
            reservations = json.loads(path.read_text()) if path.exists() else {}
            reservations.pop(pid, None)
            atomico(path, reservations)


def publico(value):
    if isinstance(value, dict):
        return {k: publico(v) for k, v in value.items()}
    if isinstance(value, list):
        return [publico(v) for v in value]
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        return value.split("?", 1)[0]
    return value


def identidad(g, gas=None):
    links = [u for u in g.data_links() if urlsplit(u).scheme == "https"]
    if not links:
        raise ValueError("CMR sin enlace HTTPS")
    name = unquote(urlsplit(links[0]).path.rsplit("/", 1)[-1])
    match = NOMBRE.search(name)
    if not match or not name.startswith(("S5P_OFFL_", "S5P_RPRO_")):
        raise ValueError("se requiere una órbita completa OFFL/RPRO identificable")
    start, end, orbit, collection, processor, production = match.groups()
    for stamp in (start, end, production):
        datetime.strptime(stamp, "%Y%m%dT%H%M%S")
    if start >= end:
        raise ValueError("rango orbital inválido")
    doc = publico(dict(g))
    ref = doc["umm"].get("CollectionReference", {})
    matches = [p for p, (short, concept) in PRODUCTOS.items()
               if ref.get("ShortName") == short and
               doc.get("meta", {}).get("collection-concept-id") == concept]
    if len(matches) != 1 or (gas and gas != matches[0]) or str(ref.get("Version")) != "2":
        raise ValueError("colección/producto no corresponde al contrato")
    expected = tuple(f"S5P_{stream}_L2__{PREFIJOS_NATIVOS[matches[0]]}" for stream in ("OFFL", "RPRO"))
    if not name.startswith(expected) or name[len(expected[0]):] != match.group()[1:]:
        raise ValueError("producto del nombre distinto al producto de la colección")
    producer = doc["umm"].get("DataGranule", {}).get("Identifiers", [])
    if not any(x.get("Identifier") == name and x.get("IdentifierType") == "ProducerGranuleId" for x in producer):
        raise ValueError("nombre del enlace distinto al identificador CMR")
    content = json.dumps(doc, sort_keys=True, default=str).encode()
    archives = doc["umm"].get("DataGranule", {}).get("ArchiveAndDistributionInformation", [])
    size = 0
    checksum = None
    for entry in archives:
        if entry.get("Name", name) not in (name, name.removesuffix(".nc"), "Not provided"):
            continue
        factor = {"BYTES": 1, "KB": 1e3, "MB": 1e6, "GB": 1e9,
                  "KILOBYTES": 1e3, "MEGABYTES": 1e6, "GIGABYTES": 1e9}.get(
                      str(entry.get("SizeUnit", "MB")).upper(), 1e6)
        size = max(size, int(float(entry.get("Size", 0)) * factor))
        checksum = entry.get("Checksum") or checksum
    size = max(size, int(float(doc.get("size", 0)) * 2**20))
    return {"name": name, "url": links[0].split("?", 1)[0], "orbit": int(orbit),
            "gas": matches[0], "stream": "RPRO" if name.startswith("S5P_RPRO_") else "OFFL",
            "start": start, "end": end, "collection": int(collection),
            "processor": int(processor), "production": production,
            "size_estimated": max(size, 256 * 2**20), "checksum": checksum,
            "cmr": doc, "cmr_sha256": hashlib.sha256(content).hexdigest()}


def seleccionar_producciones(items):
    groups = {}
    for item in items:
        group = groups.setdefault((item.get("gas"), item["orbit"]), {})
        previous = group.get(item["name"])
        if previous and previous != item:
            raise ValueError("identidad CMR contradictoria para un mismo nombre")
        group[item["name"]] = item
    result = []
    for variants in groups.values():
        values = list(variants.values())
        rank = lambda x: (x["collection"], x["processor"],
                          x.get("stream", "RPRO" if x["name"].startswith("S5P_RPRO_") else "OFFL") == "RPRO",
                          x["production"])
        best = max(map(rank, values))
        winners = [x for x in values if rank(x) == best]
        if len(winners) != 1:
            raise ValueError("producción ambigua para la misma órbita")
        result.append(winners[0])
    return sorted(result, key=lambda x: (x["start"], x["orbit"]))


def consultar(cfg, gas, day):
    import earthaccess
    all_items, counts = {}, {}
    for aoi in seleccionar("todos", Path(cfg["comunas"])):
        found = earthaccess.search_data(
            concept_id=PRODUCTOS[gas][1],
            temporal=(day + "T00:00:00Z", day + "T23:59:59Z"),
            bounding_box=aoi.bbox)
        counts[aoi.id] = len(found)
        for g in found:
            item = identidad(g, gas)
            if item["start"][:8] == day.replace("-", ""):
                if item["name"] in all_items and all_items[item["name"]] != item:
                    raise ValueError("CMR cambió identidad entre consultas de AOIs")
                all_items[item["name"]] = item
    selected = seleccionar_producciones(all_items.values())
    base = Path(cfg["root"]) / gas.upper()
    # Snapshot por ejecución: no sobrescribe versiones/consultas anteriores.
    path = base / "_catalogos_gases" / cfg["execution_id"] / (day + "." + uuid.uuid4().hex + ".json")
    atomico(path, {"utc": ahora(), "day": day, "gas": gas,
                  "collection": PRODUCTOS[gas], "version": "2",
                  "aoi_counts": counts, "candidates": list(all_items.values()),
                  "selected": [x["name"] for x in selected],
                  "policy": "collection,processor,RPRO-over-OFFL,production timestamp; unique maximum per gas/orbit; conflicting CMR identities rejected",
                  "empty_is_final": False})
    evento(cfg, gas, "consulta_cmr", day=day, sources=len(selected),
           snapshot=str(path), snapshot_sha256=sha256(path), empty_is_final=False)
    return selected


_AUTH = None


def autenticar():
    global _AUTH
    if _AUTH is None:
        import earthaccess
        load_env()
        strategy = "environment" if os.environ.get("EARTHDATA_USERNAME") else "netrc"
        _AUTH = earthaccess.login(strategy=strategy, persist=False)
        if not _AUTH or not _AUTH.authenticated:
            raise RuntimeError("autenticación Earthdata no disponible")
    return _AUTH


def validar_fuente(path, item):
    import netCDF4
    with netCDF4.Dataset(path) as nc:
        if "orbit" not in nc.ncattrs() or int(nc.orbit) != item["orbit"]:
            raise ValueError("órbita NetCDF distinta a fuente CMR")
        if "id" not in nc.ncattrs() or str(nc.id).removesuffix(".nc") != item["name"].removesuffix(".nc"):
            raise ValueError("identidad NetCDF distinta a fuente CMR")
    check = item.get("checksum")
    if check:
        algorithm = str(check.get("Algorithm", "")).lower().replace("-", "")
        if algorithm not in hashlib.algorithms_available:
            raise ValueError("algoritmo de checksum CMR no soportado")
        with Path(path).open("rb") as f:
            digest = hashlib.file_digest(f, algorithm).hexdigest()
        if digest.lower() != str(check["Value"]).lower():
            raise ValueError("checksum de proveedor distinto; fuente preservada")


def descargar(cfg, item, stage):
    import earthaccess
    dest = stage / "source.nc"
    record = stage / "downloaded.json"
    if dest.exists():
        if not record.exists():
            raise ValueError("fuente reanudada sin registro durable; preservada")
        proof = json.loads(record.read_text())
        if proof["cmr_sha256"] != item["cmr_sha256"] or proof["sha256"] != sha256(dest):
            raise ValueError("fuente reanudada no coincide con registro; preservada")
        validar_fuente(dest, item)
        return dest
    # Caída tras fsync(downloaded.json) pero antes de publicar source.nc:
    # recuperar el parcial completo ya comprobado, sin solicitar Range al EOF.
    if record.exists():
        proof = json.loads(record.read_text())
        if proof["cmr_sha256"] != item["cmr_sha256"]:
            raise ValueError("registro de otra identidad; fuente preservada")
        for candidate in stage.glob("download.*.part"):
            if candidate.stat().st_size == proof["bytes"] and sha256(candidate) == proof["sha256"]:
                validar_fuente(candidate, item)
                os.replace(candidate, dest)
                fsync_dir(stage)
                return dest
        raise ValueError("registro de descarga sin parcial coincidente; preservado")
    autenticar()
    session = earthaccess.get_requests_https_session()
    partials = sorted(stage.glob("download.*.part"), key=lambda p: p.stat().st_mtime_ns)
    part = partials[-1] if partials else stage / ("download." + uuid.uuid4().hex + ".part")
    offset = part.stat().st_size if part.exists() else 0
    if part.exists() and not offset:
        part = stage / ("download." + uuid.uuid4().hex + ".part")
    headers = {"Accept-Encoding": "identity"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    with session.get(item["url"], stream=True, headers=headers, timeout=(40, 180)) as response:
        if response.status_code not in (200, 206):
            raise RuntimeError(f"HTTP {response.status_code}")
        if offset and response.status_code == 206:
            crange = response.headers.get("Content-Range", "")
            if not crange.startswith(f"bytes {offset}-"):
                raise ValueError("Content-Range inconsistente; parcial preservado")
        elif offset:
            # Servidor sin Range: conserva el prefijo hasta validar el reemplazo.
            part = stage / ("download." + uuid.uuid4().hex + ".part")
            offset = 0
        length = response.headers.get("Content-Length")
        total = offset + int(length) if length is not None else None
        if total and total > 3 * GIB:
            raise LimiteSeguro("gránulo supera el máximo temporal de 3 GiB")
        received = offset
        with part.open("ab" if offset else "xb") as stream:
            for block in response.iter_content(4 * 2**20):
                if not block:
                    continue
                comprobar_disco(cfg, 2 * GIB)
                if received + len(block) > 3 * GIB:
                    raise LimiteSeguro("descarga excede 3 GiB")
                stream.write(block)
                received += len(block)
            stream.flush()
            os.fsync(stream.fileno())
        if total is not None and received != total:
            raise ValueError("descarga truncada; parcial preservado")
    validar_fuente(part, item)
    atomico(record, {"cmr_sha256": item["cmr_sha256"], "sha256": sha256(part),
                    "bytes": part.stat().st_size, "url": item["url"], "utc": ahora()})
    os.replace(part, dest)
    fsync_dir(stage)
    return dest


def mismos_prefijos(part, source):
    if part.stat().st_size > source.stat().st_size:
        return False
    with part.open("rb") as a, source.open("rb") as b:
        while chunk := a.read(8 * 2**20):
            if chunk != b.read(len(chunk)):
                return False
    return True


def retirar(cfg, gas, stage, source, proof):
    from _tropomi_gases_subset import validar_subset
    output = Path(proof["output"])
    committed = json.loads(Path(proof["transaction"]).read_text())
    if committed != proof or sha256(output) != proof["output_sha256"]:
        raise ValueError("transacción/salida no coincide antes del retiro")
    if sha256(source) != proof["source_sha256"]:
        raise ValueError("fuente cambió antes del retiro")
    validar_subset(output, gas, cfg["mask_sha256"])
    # Esta barrera debe quedar ANTES del primer unlink en todos los caminos.
    evento(cfg, gas, "granulo_validado_pre_borrado", **proof)
    retired = []
    for part in stage.glob("download.*.part"):
        if mismos_prefijos(part, source):
            retired.append({"path": str(part), "sha256": sha256(part),
                            "bytes": part.stat().st_size, "same_source_prefix": True})
    for temp in stage.glob("subset.*.nc"):
        retired.append({"path": str(temp), "sha256": sha256(temp),
                        "bytes": temp.stat().st_size, "derived_from_validated_source": True})
    retired.append({"path": str(source), "sha256": proof["source_sha256"],
                    "bytes": source.stat().st_size})
    evento(cfg, gas, "retiro_temporales_autorizado", files=retired,
           transaction=proof["transaction"])
    for item in retired:
        path = Path(item["path"])
        if path.parent != stage or sha256(path) != item["sha256"]:
            raise ValueError("fuente temporal cambió antes del retiro")
        path.unlink()
    fsync_dir(stage)
    evento(cfg, gas, "crudo_eliminado_post_validacion", **proof,
           retired_bytes=sum(x["bytes"] for x in retired))
    # Sólo las pruebas redundantes de este staging: el catálogo, el WAL y la
    # transacción permanente ya conservan su procedencia íntegra.
    for name in ("identity.json", "prepare.json", "downloaded.json"):
        (stage / name).unlink(missing_ok=True)
    if not any(stage.iterdir()):
        stage.rmdir()


def procesar(cfg, gas, item):
    import netCDF4
    from _tropomi_gases_subset import crear_subset, validar_subset
    base = Path(cfg["root"]) / gas.upper()
    year, month = item["start"][:4], item["start"][4:6]
    out = base / "chile_l2_nativo_v1" / f"year={year}" / f"month={month}" / item["name"].replace(".nc", ".chile.nc")
    transaction = out.with_suffix(".json")
    stage_key = hashlib.sha256((item["name"] + item["cmr_sha256"] + cfg["mask_sha256"] + CONTRATO).encode()).hexdigest()
    stage = base / "_staging_gases" / stage_key
    if transaction.exists():
        proof = json.loads(transaction.read_text())
        if proof["mask_sha256"] != cfg["mask_sha256"] or proof["contract"] != CONTRATO:
            raise ValueError("publicación de otra máscara/contrato; no sobrescribir")
        if proof["cmr_sha256"] != item["cmr_sha256"]:
            raise ValueError("metadatos fuente revisados; requiere reconciliación")
        if sha256(out) != proof["output_sha256"]:
            raise ValueError("publicación alterada; no eliminar ni sobrescribir")
        validar_subset(out, gas, cfg["mask_sha256"])
        if (stage / "source.nc").exists():
            if sha256(stage / "source.nc") != proof["source_sha256"]:
                raise ValueError("fuente pendiente distinta; conservar")
            retirar(cfg, gas, stage, stage / "source.nc", proof)
        return {"status": "reused", "gas": gas, "output": str(out), **proof["summary"]}
    with reservar(cfg, item["size_estimated"]):
        mkdir_durable(stage)
        identity = stage / "identity.json"
        if not identity.exists():
            atomico(identity, {"item": item, "mask_sha256": cfg["mask_sha256"], "contract": CONTRATO})
        evento(cfg, gas, "transferencia_o_reanudacion_iniciada", source=item["name"], staging=str(stage))
        source = descargar(cfg, item, stage)
        source_hash = sha256(source)
        evento(cfg, gas, "fuente_validada_recorte_iniciado", source=item["name"],
               source_sha256=source_hash, source_bytes=source.stat().st_size)
        prepare = stage / "prepare.json"
        if out.exists():
            # Recuperación de caída tras publicación pero antes de commit/WAL.
            if not prepare.exists():
                raise ValueError("salida sin prueba de publicación; preservada")
            proof = json.loads(prepare.read_text())
            if proof["source_sha256"] != source_hash or sha256(out) != proof["output_sha256"]:
                raise ValueError("publicación pendiente no coincide; preservada")
            validar_subset(out, gas, cfg["mask_sha256"])
        else:
            temp = stage / ("subset." + uuid.uuid4().hex + ".nc")
            summary = crear_subset(source, temp, gas, Path(cfg["comunas"]), cfg["mask_sha256"])
            with netCDF4.Dataset(temp, "a") as nc:
                nc.setncattr("chile_subset_pipeline_contract", CONTRATO)
                nc.setncattr("chile_subset_pipeline_code_sha256", cfg["code_sha256"])
                nc.setncattr("chile_subset_cmr_metadata_sha256", item["cmr_sha256"])
            fsync_archivo(temp)
            validar_subset(temp, gas, cfg["mask_sha256"])
            comprobar_disco(cfg, 2 * GIB)
            proof = {"contract": CONTRATO, "gas": gas, "utc": ahora(),
                     "source_granule": item["name"], "source_url": item["url"],
                     "source_bytes": source.stat().st_size, "source_sha256": source_hash,
                     "cmr_sha256": item["cmr_sha256"], "mask_sha256": cfg["mask_sha256"],
                     "code_sha256": cfg["code_sha256"], "code_archive": cfg["code_archive"],
                     "output": str(out), "output_sha256": sha256(temp),
                     "output_bytes": temp.stat().st_size, "summary": summary,
                     "transaction": str(transaction), "raw_retirement_allowed": True}
            atomico(prepare, proof)
            mkdir_durable(out.parent)
            # Sin sobrescritura: hardlink falla si otro escritor publica primero.
            os.link(temp, out)
            fsync_dir(out.parent)
            validar_subset(out, gas, cfg["mask_sha256"])
        evento(cfg, gas, "publicacion_validada", **proof)
        atomico(transaction, proof)
        retirar(cfg, gas, stage, source, proof)
        evento(cfg, gas, "archivo_validado", **proof)
        return {"status": "downloaded", "gas": gas, "output": str(out), **proof["summary"]}


def dia_worker(cfg, gas, day):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    base = Path(cfg["root"]) / gas.upper()
    with bloqueo(base / "_gases_nativos.lock"):
        completed, failed, pixels = 0, 0, 0
        try:
            selected = consultar(cfg, gas, day)
            if not selected:
                evento(cfg, gas, "fuente_no_publicada_pendiente", day=day)
                return {"gas": gas, "day": day, "status": "pending_source"}
            if cfg["max_granulos"]:
                selected = selected[:cfg["max_granulos"]]
            for item in selected:
                try:
                    result = procesar(cfg, gas, item)
                    completed += 1
                    pixels += result["pixeles_chile"]
                    log.info("%s %s %s %s", gas.upper(), day, result["status"], item["name"])
                except LimiteSeguro:
                    raise
                except Exception as exc:
                    failed += 1
                    # Sin URLs/cookies/excepciones de sesión en los registros.
                    evento(cfg, gas, "granulo_fallido_preservado", day=day,
                           source=item["name"], error_type=type(exc).__name__,
                           detail=re.sub(r"https?://\S+", "[URL]", str(exc))[:300])
                    log.warning("%s %s fallo %s (%s)", gas, day, item["name"], type(exc).__name__)
            status = "con_fallos" if failed else "validado_contra_snapshot"
            evento(cfg, gas, "dia_revisado", day=day, status=status,
                   completed=completed, failed=failed, limited=bool(cfg["max_granulos"]))
            return {"gas": gas, "day": day, "status": status, "completed": completed,
                    "failed": failed, "pixeles_procesados": pixels}
        except LimiteSeguro as exc:
            evento(cfg, gas, "pausado_limite_seguro", day=day, reason=str(exc))
            return {"gas": gas, "day": day, "status": "pausado_limite_seguro"}
        except Exception as exc:
            evento(cfg, gas, "consulta_o_dia_fallido", day=day, error_type=type(exc).__name__,
                   detail=re.sub(r"https?://\S+", "[URL]", str(exc))[:300])
            return {"gas": gas, "day": day, "status": "con_fallos", "failed": 1}


def codigo_reproducible(root):
    import netCDF4
    import pyproj
    import shapely
    scripts = Path(__file__).resolve().parent
    names = [Path(__file__).name, "_tropomi_gases_subset.py", "_chile_aoi.py",
             "_common.py", "_manifiesto_satelital.py"]
    hashes = {name: sha256(scripts / name) for name in names}
    packages = {p: importlib.metadata.version(p) for p in
                ("earthaccess", "netCDF4", "cftime", "numpy", "geopandas", "shapely",
                 "pyproj", "pyogrio", "requests")}
    runtime = {"hashes": hashes, "packages": packages,
               "python": sys.version, "executable": sys.executable,
               "native_libraries": {"netcdf": netCDF4.__netcdf4libversion__,
                                    "hdf5": netCDF4.__hdf5libversion__,
                                    "geos": shapely.geos_version_string,
                                    "proj": pyproj.proj_version_str}}
    digest = hashlib.sha256(json.dumps(runtime, sort_keys=True).encode()).hexdigest()
    dest = root / "_control_gases" / "codigo" / digest
    mkdir_durable(dest)
    for name in names:
        target = dest / name
        if target.exists() and sha256(target) != hashes[name]:
            raise ValueError("archivo de procedencia modificado")
        if not target.exists():
            shutil.copyfile(scripts / name, target)
            fsync_archivo(target)
    if (dest / "runtime.json").exists():
        if json.loads((dest / "runtime.json").read_text()) != runtime:
            raise ValueError("procedencia de entorno modificada")
    else:
        atomico(dest / "runtime.json", runtime)
    fsync_dir(dest)
    return digest, str(dest)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gases", default="co,so2,o3,hcho,ch4")
    ap.add_argument("--desde", default="2018-04-30")
    ap.add_argument("--hasta", default=(date.today() - timedelta(days=1)).isoformat())
    ap.add_argument("--trabajadores", type=int, choices=(1, 2), default=2)
    ap.add_argument("--max-granulos-por-gas", type=int, default=0,
                    help="límite por gas/día sólo para pruebas; 0=todos")
    ap.add_argument("--reserva-gib", type=float, default=100)
    ap.add_argument("--staging-gib", type=float, default=10)
    ap.add_argument("--cuota-productos-gib", type=float, default=40,
                    help="pausa antes de superar cuota acumulada de nuevos gases")
    ap.add_argument("--comunas", type=Path, default=DATA / "comunas.shp")
    args = ap.parse_args(argv)
    gases = list(dict.fromkeys(args.gases.lower().split(",")))
    if not gases or any(p not in PRODUCTOS for p in gases):
        ap.error("gases permitidos: co,so2,o3,hcho,ch4; NO2 usa su proceso existente")
    if args.reserva_gib < 100 or args.staging_gib < 3 or args.cuota_productos_gib <= 0:
        ap.error("reserva >=100 GiB, staging >=3 GiB, cuota >0")
    if args.max_granulos_por_gas < 0:
        ap.error("max-granulos-por-gas debe ser >=0")
    start, end = date.fromisoformat(args.desde), date.fromisoformat(args.hasta)
    if start < date(2018, 4, 30) or end < start or end > date.today():
        ap.error("rango fuera de cobertura temporal")
    root = (CONTAMINANTES / "S5P_TROPOMI").resolve()
    if not str(root).startswith("/Volumes/Datos/"):
        ap.error("el destino debe estar en /Volumes/Datos")
    cfg = {"root": str(root), "comunas": str(args.comunas.resolve()),
           "volume_uuid": VOLUME_UUID, "reserva_gib": args.reserva_gib,
           "staging_gib": args.staging_gib, "cuota_gib": args.cuota_productos_gib,
           "max_granulos": args.max_granulos_por_gas,
           "execution_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]}
    comprobar_disco(cfg, 2 * GIB)
    control = root / "_control_gases"
    with bloqueo(control / "supervisor.lock"):
        cfg["mask_sha256"] = sha256_conjunto_shapefile(args.comunas)
        cfg["code_sha256"], cfg["code_archive"] = codigo_reproducible(root)
        atomico(control / "ejecucion_actual.json", {**cfg, "pid": os.getpid(),
                "gases": gases, "desde": str(start), "hasta": str(end),
                "trabajadores": args.trabajadores, "estado": "en_curso"})
        failed = pending = 0
        with ProcessPoolExecutor(max_workers=args.trabajadores) as pool:
            # La primera transferencia de cada gas es una prueba real acotada.
            # Sólo se amplía al histórico si los cinco cierres verifican fuente,
            # todos los campos nativos, publicación y retiro durable.
            if not args.max_granulos_por_gas:
                probe = min(end, date(2023, 10, 5)).isoformat()
                probe_cfg = {**cfg, "max_granulos": 1}
                checks = [pool.submit(dia_worker, probe_cfg, p, probe) for p in gases]
                probe_results = [f.result() for f in as_completed(checks)]
                passed = all(r.get("completed", 0) == 1 and r.get("pixeles_procesados", 0) > 0 and not r.get("failed", 0)
                             and r["status"] == "validado_contra_snapshot" for r in probe_results)
                atomico(control / "prueba_inicial.json", {"execution_id": cfg["execution_id"],
                        "utc": ahora(), "day": probe, "passed": passed, "resultados": probe_results})
                if not passed:
                    atomico(control / "avance.json", {"execution_id": cfg["execution_id"],
                            "utc": ahora(), "estado": "pausado_prueba_inicial", "resultados": probe_results})
                    return 2
            day = start
            while day <= end:
                futures = [pool.submit(dia_worker, cfg, p, day.isoformat()) for p in gases]
                results = [f.result() for f in as_completed(futures)]
                failed += sum(r.get("failed", 0) for r in results)
                pending += sum(r["status"] == "pending_source" for r in results)
                pause = any(r["status"] == "pausado_limite_seguro" for r in results)
                atomico(control / "avance.json", {"execution_id": cfg["execution_id"],
                        "utc": ahora(), "ultimo_dia_consultado": str(day), "resultados": results,
                        "fallos": failed, "dias_gas_sin_fuente": pending,
                        "estado": "pausado_limite_seguro" if pause else "en_curso"})
                if pause:
                    return 75
                day += timedelta(days=1)
        status = "con_pendientes" if failed or pending else "validado_contra_snapshots"
        atomico(control / "fin.json", {"execution_id": cfg["execution_id"],
                "utc": ahora(), "estado": status, "fallos": failed,
                "dias_gas_sin_fuente": pending, "prueba_limitada": bool(cfg["max_granulos"])})
        return 1 if failed else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(main())
