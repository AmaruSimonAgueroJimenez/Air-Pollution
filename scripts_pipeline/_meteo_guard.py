"""Fail-closed safety checks for the single-supervisor DMC downloader.

These guards do not authorize or restart any pre-existing download.  They never
mount a volume, alter another product's controls, remove files, or send signals.
Only the meteorological output tree may be created after identity checks pass.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shlex
import stat
import subprocess
import threading
import uuid
from functools import wraps

GIB = 1024 ** 3
MIB = 1024 ** 2
EXPECTED_UUID = "54B3D309-A503-44C6-9229-581F3E4FECE3"
MOUNT_POINT = Path("/Volumes/Datos")
DEFAULT_OUTPUT_ROOT = MOUNT_POINT / "Asesorias_Data/AirPollution/data/meteorologia/estaciones_horarias/DMC"
MAIN_NAME = "descargar_meteo_chile_horaria.py"
_DIAGNOSTIC_FLAGS = {"--check", "--check-api", "--probe", "--help", "-h"}
CONCURRENT_SCHEMA = "meteo-concurrent-producer/v1"
CONCURRENT_MAX_BYTES = 64 * 1024


def _synchronized(method):
    @wraps(method)
    def locked(self, *args, **kwargs):
        with self._state_lock:
            return method(self, *args, **kwargs)
    return locked


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class GuardBlocked(RuntimeError):
    """A condition requiring waiting or a new human decision, never a restart."""

    def __init__(self, reason, *, code="safety_block", detail=None):
        super().__init__(reason)
        self.reason, self.code, self.detail = reason, code, detail

    def as_dict(self):
        return {"ready": False, "state": self.code, "reason": self.reason,
                **({"detail": self.detail} if self.detail is not None else {})}


def _concurrent_path(raw, *, directory=False):
    """Inspect paths only; never inspect a concurrent producer's data contents."""
    if not isinstance(raw, str) or not raw or not os.path.isabs(raw) or os.path.normpath(raw) != raw:
        raise GuardBlocked("Ruta concurrente no canónica.", code="invalid_concurrent_authorization")
    path = Path(raw)
    for ancestor in [*reversed(path.parents), path]:
        try:
            entry = ancestor.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(entry.st_mode) or (ancestor != path and not stat.S_ISDIR(entry.st_mode)):
            raise GuardBlocked("Ruta concurrente contiene un enlace o padre no seguro.", code="invalid_concurrent_authorization")
    if directory and path.exists() and not path.is_dir():
        raise GuardBlocked("Una raíz concurrente no es un directorio.", code="invalid_concurrent_authorization")
    return path


def _script_sha256(path):
    path = _concurrent_path(str(path))
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > 4 * MIB:
                raise ValueError("script type/size")
            value = hashlib.file_digest(stream, "sha256").hexdigest()
            after = os.fstat(stream.fileno())
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError("script changed")
            return value
    except (OSError, ValueError) as exc:
        raise GuardBlocked("No se pudo verificar el código del productor concurrente.", code="concurrent_script_mismatch") from exc


def validate_concurrent_authorization(config, *, output_root=DEFAULT_OUTPUT_ROOT, mount_point=MOUNT_POINT):
    """Authorize one exact process, never a script name, descendants or PID alone."""
    if not isinstance(config, dict) or config.get("schema") != CONCURRENT_SCHEMA:
        raise GuardBlocked("Esquema concurrente inválido.", code="invalid_concurrent_authorization")
    if not isinstance(config.get("authorization_id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", config["authorization_id"]):
        raise GuardBlocked("Identificador concurrente inválido.", code="invalid_concurrent_authorization")
    if not isinstance(config.get("human_scope"), str) or not config["human_scope"].strip():
        raise GuardBlocked("Falta el alcance humano de concurrencia.", code="invalid_concurrent_authorization")
    identity, script, roots = config.get("identity"), config.get("script"), config.get("output_roots")
    if not isinstance(identity, dict) or not isinstance(script, dict) or not isinstance(roots, list) or not roots:
        raise GuardBlocked("Identidad, código o raíces concurrentes ausentes.", code="invalid_concurrent_authorization")
    if any(type(identity.get(key)) is not int or identity[key] <= 0 for key in ("pid", "ppid", "pgid")) or any(not isinstance(identity.get(key), str) or not identity[key].strip() for key in ("started_local", "command")):
        raise GuardBlocked("Identidad concurrente incompleta.", code="invalid_concurrent_authorization")
    path = _concurrent_path(script.get("path"))
    expected = script.get("sha256")
    if path.name != "download_data.py" or not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise GuardBlocked("Código concurrente no fijado.", code="invalid_concurrent_authorization")
    try:
        tokens = shlex.split(identity["command"])
    except ValueError as exc:
        raise GuardBlocked("Comando concurrente no interpretable.", code="invalid_concurrent_authorization") from exc
    name, _ = _python_script(identity["command"])
    parts = []
    for token in tokens[1:]:
        if token.startswith("-") and not parts:
            continue
        parts.append(token)
        if token.endswith(".py"):
            break
    if name != path.name or " ".join(parts) != str(path):
        raise GuardBlocked("El comando no invoca el código concurrente fijado.", code="invalid_concurrent_authorization")
    if _script_sha256(path) != expected:
        raise GuardBlocked("Cambió el código del productor concurrente.", code="concurrent_script_mismatch")
    dmc, mount = Path(output_root).absolute(), Path(mount_point).absolute()
    checked = []
    for raw in roots:
        root = _concurrent_path(raw, directory=True)
        if root == mount or root in dmc.parents or dmc in root.parents or root == dmc:
            raise GuardBlocked("Las raíces concurrentes se superponen con DMC.", code="invalid_concurrent_authorization")
        checked.append(str(root))
    if len(set(checked)) != len(checked):
        raise GuardBlocked("Raíces concurrentes duplicadas.", code="invalid_concurrent_authorization")
    return config


def load_concurrent_authorization(path, expected_sha, *, output_root=DEFAULT_OUTPUT_ROOT, mount_point=MOUNT_POINT):
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise GuardBlocked("Falta SHA de la autorización concurrente.", code="invalid_concurrent_authorization")
    path = _concurrent_path(str(path))
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > CONCURRENT_MAX_BYTES:
                raise ValueError("authorization type/size")
            data = stream.read(CONCURRENT_MAX_BYTES + 1)
        if len(data) > CONCURRENT_MAX_BYTES or hashlib.sha256(data).hexdigest() != expected_sha:
            raise ValueError("authorization hash/size")
        config = json.loads(data, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (OSError, ValueError) as exc:
        raise GuardBlocked("La autorización concurrente no coincide con su SHA.", code="invalid_concurrent_authorization") from exc
    validate_concurrent_authorization(config, output_root=output_root, mount_point=mount_point)
    return {**config, "_authorization_path": str(path), "_authorization_sha256": expected_sha}


def parse_processes(text):
    """Read `ps -axo pid=,ppid=,pgid=,lstart=,command=` without shell evaluation."""
    result = []
    for line in text.splitlines():
        fields = line.strip().split(None, 8)
        if len(fields) != 9 or not all(x.isdigit() for x in fields[:3]):
            continue
        result.append({"pid": int(fields[0]), "ppid": int(fields[1]),
                       "pgid": int(fields[2]), "started_local": " ".join(fields[3:8]),
                       "command": fields[8]})
    return result


def _python_script(command):
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None, []
    if not tokens:
        return None, tokens
    executable = Path(tokens[0]).name.lower()
    if not re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", executable):
        return None, tokens
    # ps prints argv without reliable quoting. Real repository paths contain
    # "Mi unidad", so reconstruct the script argument through its .py suffix.
    # Never treat a filename mentioned in `python -c` as an invoked script.
    script_parts = []
    for token in tokens[1:]:
        if token in {"-c", "-m"}:
            return None, tokens
        if token.startswith("-") and not script_parts:
            continue
        script_parts.append(token)
        if token.endswith(".py"):
            return Path(" ".join(script_parts)).name, tokens
    return None, tokens


def data_producers(processes, *, allowed_pids=()):
    """Identify actual Python downloader invocations, not quoted diagnostics.

    Ambiguous orphan multiprocessing workers are also a conservative blocker:
    a free historical lock is not sufficient to prove that they cannot write.
    Nothing is terminated, including independent modelling processes.
    """
    allowed = set(allowed_pids)
    result = []
    for item in processes:
        if item["pid"] in allowed:
            continue
        name, tokens = _python_script(item["command"])
        # Actual legacy shell wrappers may launch a writer after a delay; a
        # quoted shell diagnostic or sincronizar.sh is never a downloader.
        shell_wrappers = {"correr_con_reintentos.sh", "ejecutar_descargas.sh",
                          "lanzar_descargas.sh", "ejecutar_snifa.sh"}
        if tokens and Path(tokens[0]).name in {"bash", "zsh", "sh"} and "-c" not in tokens:
            shell_script = next((Path(token).name for token in tokens[1:] if token.endswith(".sh")), None)
            if shell_script in shell_wrappers:
                result.append({**item, "script": shell_script, "kind": "data_producer_wrapper"})
                continue
        if name is not None and not _DIAGNOSTIC_FLAGS.intersection(tokens):
            lower = name.lower()
            if (lower.startswith(("descargar_", "download_", "migrar_tropomi", "migrador_tropomi",
                                  "reanudar_tropomi_", "recuperar_tropomi_", "lanzar_tropomi_"))
                    or lower in {"migracion_tropomi.py", "migrar_tropomi.py", "download.py",
                                 "download_era5.py", "download_era5land.py"}):
                result.append({**item, "script": name, "kind": "data_producer"})
                continue
        if tokens and item["ppid"] == 1 and "-c" in tokens:
            payload = " ".join(tokens[tokens.index("-c") + 1:])
            if "multiprocessing.spawn" in payload and "spawn_main" in payload:
                result.append({**item, "kind": "unidentified_orphan_worker"})
    return result


def existing_flock_available(path, *, expected_dev=None):
    """Inspect an existing BSD flock using a read-only descriptor, never create.

    F_GETLK does not inspect the BSD flock used by the historical engine on
    macOS. A nonblocking flock on O_RDONLY is released immediately; no contents,
    timestamps, controls or ownership are changed. Missing is reported as such,
    not as evidence of historical completion or permission for a TROPOMI run.
    """
    path = Path(path)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return {"path": str(path), "state": "absent"}
    except OSError as exc:
        raise GuardBlocked("No se pudo verificar un lock histórico.", code="lock_unverifiable",
                           detail={"path": str(path), "errno": exc.errno}) from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or (expected_dev is not None and info.st_dev != expected_dev):
            raise GuardBlocked("Lock histórico fuera del volumen esperado.", code="unsafe_lock_path")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK}:
                return {"path": str(path), "state": "held"}
            raise GuardBlocked("No se pudo consultar el lock histórico.", code="lock_unverifiable") from exc
        fcntl.flock(fd, fcntl.LOCK_UN)
        return {"path": str(path), "state": "available"}
    finally:
        os.close(fd)


class DiskGuard:
    def __init__(self, output_root=DEFAULT_OUTPUT_ROOT, *, expected_uuid=EXPECTED_UUID,
                 mount_point=MOUNT_POINT, reserve_bytes=50 * GIB,
                 max_response_bytes=32 * MIB, max_retained_bytes=10 * GIB,
                 allowed_pids=None, runner=subprocess.run, concurrent_authorization=None,
                 defer_heavy_checks=False, http_workers=1, frsize_allocation_grain=False):
        if type(http_workers) is not int or http_workers not in (1, 2, 4):
            raise ValueError("Only one, two or four HTTP workers are supported")
        if type(frsize_allocation_grain) is not bool:
            raise ValueError("frsize_allocation_grain must be a boolean")
        # Authorized fast schedule only: between station boundaries, charge each
        # write by the volume's allocation unit (f_frsize, 4 KiB on APFS) instead
        # of its preferred I/O size (f_bsize, 1 MiB on APFS). Still an upper bound
        # of the exact recount, which adds max(size, allocated blocks) per file.
        self.frsize_allocation_grain = frsize_allocation_grain
        self._state_lock = threading.RLock()
        self.abort_check = None
        self.http_workers = http_workers
        self.output_root = Path(output_root).absolute()
        self.mount_point = Path(mount_point).absolute()
        self.expected_uuid = expected_uuid
        self.reserve_bytes = int(reserve_bytes)
        self.max_response_bytes = int(max_response_bytes)
        self.max_retained_bytes = int(max_retained_bytes)
        # Reserve every bounded response throughout a parallel run, including
        # completed results waiting for the sole writer. Full scans must never
        # erase these reservations. This is conservative, not extra disk quota.
        self._http_reservation_bytes = (http_workers * self.max_response_bytes if http_workers > 1 else 0)
        self.allowed_pids = {os.getpid()} if allowed_pids is None else set(allowed_pids)
        self.runner = runner
        self.concurrent_authorization = concurrent_authorization
        self.defer_heavy_checks = bool(defer_heavy_checks)
        self._full_snapshot = None
        self._retained_upper = 0
        self._mount_fingerprint = None
        self._allocation_grain = 4096
        if concurrent_authorization is not None:
            validate_concurrent_authorization(concurrent_authorization,
                                              output_root=self.output_root, mount_point=self.mount_point)
        self._pinned_dev = None
        if min(self.reserve_bytes, self.max_response_bytes, self.max_retained_bytes) < 1:
            raise ValueError("Positive safety limits are required")
        try:
            self.output_root.relative_to(self.mount_point)
        except ValueError as exc:
            raise GuardBlocked("La salida no pertenece al disco externo esperado.", code="unsafe_output_path") from exc
        if self.output_root == self.mount_point:
            raise GuardBlocked("La salida no puede ser la raíz del volumen.", code="unsafe_output_path")

    def _run(self, argv, timeout=15):
        try:
            return self.runner(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               check=False, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GuardBlocked("No se pudo verificar el sistema de forma segura.",
                               code="system_unverifiable", detail={"command": argv[0]}) from exc

    def _mount_identity(self):
        if not self.mount_point.exists():
            raise GuardBlocked("Esperando el disco externo correcto; no se creó ninguna ruta sustituta.",
                               code="waiting_disk")
        if self.mount_point.is_symlink() or self.mount_point.resolve() != self.mount_point:
            raise GuardBlocked("El punto de montaje contiene un enlace simbólico.", code="unsafe_mount_path")
        result = self._run(["diskutil", "info", "-plist", str(self.mount_point)])
        if result.returncode != 0:
            raise GuardBlocked("El volumen externo no es verificable.", code="waiting_disk")
        try:
            info = plistlib.loads(result.stdout)
        except (ValueError, plistlib.InvalidFileException, TypeError) as exc:
            raise GuardBlocked("La identidad del volumen no pudo leerse.", code="volume_unverifiable") from exc
        # Some valid diskutil plists omit Mounted. A present field must still
        # be the literal boolean True; the independent mount/device checks
        # below remain mandatory even when this optional field is absent.
        if (info.get("VolumeUUID") != self.expected_uuid
                or ("Mounted" in info and info["Mounted"] is not True)
                or info.get("MountPoint") != str(self.mount_point)):
            raise GuardBlocked("No está montado el volumen con el UUID autorizado.", code="wrong_volume")
        if not os.path.ismount(self.mount_point):
            raise GuardBlocked("La ruta no es un punto de montaje real.", code="unsafe_mount_path")
        mounted = os.stat(self.mount_point, follow_symlinks=False)
        if mounted.st_dev == os.stat(self.mount_point.parent, follow_symlinks=False).st_dev:
            raise GuardBlocked("La ruta pertenece al disco local, no al externo.", code="unsafe_mount_path")
        if self._pinned_dev is not None and mounted.st_dev != self._pinned_dev:
            raise GuardBlocked("Cambió la identidad del dispositivo durante esta ejecución.", code="volume_changed")
        self._pinned_dev = mounted.st_dev
        return {"volume_uuid": info["VolumeUUID"], "mount_point": str(self.mount_point),
                "device": mounted.st_dev}

    def _validate_path(self, path, *, dev):
        path = Path(path).absolute()
        try:
            parts = path.relative_to(self.mount_point).parts
        except ValueError as exc:
            raise GuardBlocked("Escritura fuera del volumen autorizado.", code="unsafe_output_path") from exc
        if any(part in {"", ".", ".."} for part in parts):
            raise GuardBlocked("Ruta no canónica.", code="unsafe_output_path")
        current = self.mount_point
        for part in parts:
            current = current / part
            try:
                entry = current.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(entry.st_mode) or entry.st_dev != dev:
                raise GuardBlocked("Enlace simbólico o dispositivo distinto en la ruta de salida.", code="unsafe_output_path")
        return path

    def retained_bytes(self, dev):
        self._validate_path(self.output_root, dev=dev)
        if not self.output_root.exists():
            return 0
        # Fresh, complete accounting on every check, including partials and old
        # versions. Walk anchored descriptors: scandir(path) could follow a
        # directory swapped to a symlink after its no-follow stat.
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        opened = []
        total = 0
        try:
            fd = os.open(self.mount_point, flags)
            opened.append(fd)
            if os.fstat(fd).st_dev != dev:
                raise GuardBlocked("El montaje cambió durante el recuento.", code="volume_changed")
            for part in self.output_root.relative_to(self.mount_point).parts:
                child = os.open(part, flags, dir_fd=fd)
                opened.append(child)
                if os.fstat(child).st_dev != dev:
                    raise GuardBlocked("Dispositivo distinto durante el recuento.", code="unsafe_output_path")
                os.close(fd)
                opened.remove(fd)
                fd = child
            def scan(current):
                subtotal = 0
                with os.scandir(current) as entries:
                    for item in entries:
                        entry = item.stat(follow_symlinks=False)
                        if stat.S_ISLNK(entry.st_mode) or entry.st_dev != dev:
                            raise GuardBlocked("El árbol meteorológico contiene una ruta no segura.", code="unsafe_output_path")
                        if stat.S_ISDIR(entry.st_mode):
                            child = os.open(item.name, flags, dir_fd=current)
                            try:
                                actual = os.fstat(child)
                                if actual.st_dev != dev or actual.st_ino != entry.st_ino:
                                    raise GuardBlocked("El directorio cambió durante el recuento.", code="unsafe_output_path")
                                # Close each child before opening its sibling:
                                # descriptor use is bounded by depth, not width.
                                subtotal += scan(child)
                            finally:
                                os.close(child)
                        elif stat.S_ISREG(entry.st_mode):
                            subtotal += max(entry.st_size, entry.st_blocks * 512)
                return subtotal
            return scan(fd)
        except OSError as exc:
            raise GuardBlocked("No se pudo recorrer de forma segura todo el árbol meteorológico.",
                               code="unsafe_output_path", detail={"errno": exc.errno}) from exc
        finally:
            for fd in opened:
                os.close(fd)

    def _processes(self):
        result = self._run(["ps", "-axo", "pid=,ppid=,pgid=,lstart=,command="])
        if result.returncode != 0:
            raise GuardBlocked("No se pudo verificar el árbol de procesos.", code="processes_unverifiable")
        text = result.stdout.decode("utf8", errors="replace") if isinstance(result.stdout, bytes) else result.stdout
        return parse_processes(text)

    def _historical_locks(self, dev):
        base = self.mount_point / "Asesorias_Data/AirPollution/data/contaminantes/S5P_TROPOMI"
        locks = [base / "_control_gases/supervisor.lock", base / "_control_gases/capacidad.lock"]
        locks += [base / gas / "_gases_nativos.lock" for gas in ("CO", "SO2", "O3", "HCHO", "CH4")]
        result = []
        for path in locks:
            self._validate_path(path, dev=dev)
            result.append(existing_flock_available(path, expected_dev=dev))
        if any(item["state"] == "held" for item in result):
            raise GuardBlocked("Un productor TROPOMI aún retiene un lock; la nueva descarga espera.",
                               code="other_producer_lock", detail=result)
        return result

    def _concurrent_process(self, processes):
        config = self.concurrent_authorization
        if config is None:
            return set(), None
        # The file is pinned by SHA in both launcher and child CLI; a later edit
        # does not silently change permissions during a long download.
        if "_authorization_path" in config:
            config = load_concurrent_authorization(config["_authorization_path"],
                         config["_authorization_sha256"], output_root=self.output_root,
                         mount_point=self.mount_point)
        else:
            validate_concurrent_authorization(config, output_root=self.output_root,
                                              mount_point=self.mount_point)
        expected = config["identity"]
        actual = next((item for item in processes if item["pid"] == expected["pid"]), None)
        if actual is None:
            return set(), {"authorization_id": config["authorization_id"], "state": "authorized_process_absent"}
        if any(actual.get(key) != expected[key] for key in ("pid", "ppid", "pgid", "started_local", "command")):
            raise GuardBlocked("El PID concurrente ya no tiene la identidad autorizada.",
                               code="concurrent_identity_mismatch", detail={"pid": expected["pid"]})
        return {actual["pid"]}, {"authorization_id": config["authorization_id"],
                "state": "exact_process_authorized", "identity": expected,
                "script": config["script"], "output_roots": config["output_roots"],
                "descendants_authorized": False}

    def _concurrent_descendant_blockers(self, processes):
        if self.concurrent_authorization is None:
            return []
        branch = {self.concurrent_authorization["identity"]["pid"]}
        descendants = []
        remaining = list(processes)
        while True:
            children = [item for item in remaining if item["ppid"] in branch and item["pid"] not in branch]
            if not children:
                break
            descendants.extend(children)
            branch.update(item["pid"] for item in children)
            remaining = [item for item in remaining if item["pid"] not in branch]
        blockers = []
        for item in descendants:
            # Classification of this authorized branch treats ambiguous spawn
            # workers as blockers before they become orphans. A parent-only
            # exception must never implicitly authorize its worker processes.
            classified = data_producers([{**item, "ppid": 1}], allowed_pids=self.allowed_pids)
            if classified:
                blockers.append({**classified[0], **item,
                                 "kind": "unauthorized_concurrent_descendant",
                                 "detected_kind": classified[0]["kind"]})
        return blockers

    def check_boundary(self):
        """Fresh full inventory, process, volume and lock check at each job edge."""
        return self.check(full=True)

    def _light_check(self, additional_bytes):
        identity = self._full_snapshot
        try:
            mount = self.mount_point.lstat()
            volume = os.statvfs(self.mount_point)
            fingerprint = (mount.st_dev, mount.st_ino, getattr(volume, "f_fsid", None))
            if (stat.S_ISLNK(mount.st_mode) or self.mount_point.resolve() != self.mount_point
                    or fingerprint != self._mount_fingerprint):
                raise GuardBlocked("El volumen cambió desde la frontera anterior.", code="volume_changed")
            self._validate_path(self.output_root, dev=identity["device"])
        except OSError as exc:
            raise GuardBlocked("El volumen ya no está disponible.", code="waiting_disk") from exc
        free = volume.f_bavail * volume.f_frsize
        if self._retained_upper + additional_bytes + self._http_reservation_bytes > self.max_retained_bytes:
            raise GuardBlocked("Se alcanzó la cota conservadora de 10 GiB.", code="meteo_capacity_pause")
        if free - self.http_workers * self.max_response_bytes - additional_bytes < self.reserve_bytes:
            raise GuardBlocked(f"La descarga no garantiza la reserva de {self.reserve_bytes / GIB:g} GiB más el buffer temporal.", code="reserve_pause")
        return {**identity, "utc": utc_now(), "free_bytes": free,
                "retained_bytes": self._retained_upper,
                "check_scope": "light_since_last_full_boundary",
                "retained_bytes_scope": "conservative_own_write_upper_bound",
                "full_checked_at_utc": identity["utc"]}

    @_synchronized
    def _charge_write(self, count):
        if self.defer_heavy_checks:
            # Retain this reservation even on failure: partials are preserved.
            # Replacements are not subtracted until the next exhaustive scan.
            grain = self._allocation_grain
            allocation = ((int(count) + grain - 1) // grain) * grain + grain
            self.check(additional_bytes=allocation)
            self._retained_upper += allocation

    @_synchronized
    def check(self, additional_bytes=0, *, check_producers=True, full=False):
        if self.abort_check is not None:
            self.abort_check()
        additional_bytes = int(additional_bytes)
        if additional_bytes < 0:
            raise ValueError("additional_bytes must not be negative")
        if self.defer_heavy_checks and self._full_snapshot is not None and not full:
            return self._light_check(additional_bytes)
        identity = self._mount_identity()
        self._validate_path(self.output_root, dev=identity["device"])
        processes, locks, concurrent = [], [], None
        if check_producers:
            observed = self._processes()
            authorized, concurrent = self._concurrent_process(observed)
            processes = data_producers(observed, allowed_pids=self.allowed_pids | authorized)
            known = {item["pid"] for item in processes}
            processes += [item for item in self._concurrent_descendant_blockers(observed)
                          if item["pid"] not in known]
            if processes:
                raise GuardBlocked("Hay otro descargador o worker residual; no se inicia ni se escribe.",
                                   code="other_producer", detail=processes)
            locks = self._historical_locks(identity["device"])
        retained = self.retained_bytes(identity["device"])
        if retained + additional_bytes + self._http_reservation_bytes > self.max_retained_bytes:
            raise GuardBlocked("Se alcanzó el límite preventivo de 10 GiB de esta descarga nueva.", code="meteo_capacity_pause")
        volume = os.statvfs(self.mount_point)
        free = volume.f_bavail * volume.f_frsize
        if free - self.http_workers * self.max_response_bytes - additional_bytes < self.reserve_bytes:
            raise GuardBlocked(f"La descarga no garantiza la reserva de {self.reserve_bytes / GIB:g} GiB más el buffer temporal.", code="reserve_pause")
        # Repeat identity after filesystem/process inspection: no local fallback.
        if self._mount_identity()["device"] != identity["device"]:
            raise GuardBlocked("El volumen cambió durante la comprobación.", code="volume_changed")
        snapshot = {"ready": True, "state": "ready", "utc": utc_now(), **identity,
                "output_root": str(self.output_root), "free_bytes": free,
                "retained_bytes": retained, "reserve_bytes": self.reserve_bytes,
                "max_response_bytes": self.max_response_bytes,
                "max_retained_bytes": self.max_retained_bytes, "historical_locks": locks,
                "http_workers": self.http_workers,
                "http_response_reservations_bytes": self._http_reservation_bytes,
                "aggregate_response_buffer_bytes": self.http_workers * self.max_response_bytes,
                "concurrent_producer": concurrent}
        if self.defer_heavy_checks:
            mount = self.mount_point.lstat()
            self._mount_fingerprint = (mount.st_dev, mount.st_ino, getattr(volume, "f_fsid", None))
            frsize = int(getattr(volume, "f_frsize", 4096))
            self._allocation_grain = (max(4096, frsize) if self.frsize_allocation_grain else
                                      max(4096, int(getattr(volume, "f_bsize", 4096)), frsize))
            self._full_snapshot = snapshot
            self._retained_upper = retained
        return {**snapshot, "check_scope": "full_fresh"}

    def _scoped_path(self, path):
        path = Path(path).absolute()
        try:
            path.relative_to(self.output_root)
        except ValueError as exc:
            raise GuardBlocked("La escritura solicitada no pertenece al árbol meteorológico.", code="unsafe_output_path") from exc
        return path

    def _open_directory(self, path):
        """Walk from the pinned mount with dirfds and O_NOFOLLOW."""
        path = self._scoped_path(path)
        snapshot = self.check()
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.mount_point, flags)
        try:
            if os.fstat(fd).st_dev != snapshot["device"]:
                raise GuardBlocked("El directorio abierto no es del disco esperado.", code="volume_changed")
            for component in path.relative_to(self.mount_point).parts:
                child = os.open(component, flags, dir_fd=fd)
                os.close(fd)
                fd = child
                if os.fstat(fd).st_dev != snapshot["device"]:
                    raise GuardBlocked("Cambió el dispositivo en la ruta abierta.", code="volume_changed")
            return fd
        except Exception:
            os.close(fd)
            raise

    def ensure_directory(self, path):
        fd = self._ensure_directory_open(path)
        os.close(fd)

    def _ensure_directory_open(self, path, *, additional_bytes=4096):
        """Ensure parents durably and return their already anchored descriptor.

        A snapshot is local to this single operation, never time-cached. Fresh
        full checks remain before each mkdir and every subsequent file mutation.
        """
        path = self._scoped_path(path)
        snapshot = self.check(additional_bytes=max(4096, additional_bytes))
        self._validate_path(path, dev=snapshot["device"])
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.mount_point, flags)
        try:
            if os.fstat(fd).st_dev != snapshot["device"]:
                raise GuardBlocked("El montaje abierto cambió antes de crear directorios.", code="volume_changed")
            for component in path.relative_to(self.mount_point).parts:
                try:
                    child = os.open(component, flags, dir_fd=fd)
                except FileNotFoundError:
                    self.check(additional_bytes=4096)
                    if os.fstat(fd).st_dev != self._pinned_dev:
                        raise GuardBlocked("Cambió el dispositivo antes de crear el directorio.", code="volume_changed")
                    self._charge_write(4096)
                    os.mkdir(component, 0o755, dir_fd=fd)
                    os.fsync(fd)
                    child = os.open(component, flags, dir_fd=fd)
                os.close(fd)
                fd = child
                if os.fstat(fd).st_dev != self._pinned_dev:
                    raise GuardBlocked("Directorio de un dispositivo distinto.", code="volume_changed")
            os.fsync(fd)
            return fd
        except BaseException:
            os.close(fd)
            raise

    @_synchronized
    def write_atomic_bytes(self, path, data):
        path = self._scoped_path(path)
        data = bytes(data)
        if len(data) > self.max_response_bytes:
            raise GuardBlocked("La respuesta o artefacto excede el buffer de 32 MiB.", code="response_too_large")
        # Reuse the descriptor opened while ensuring the parent. Do not perform
        # another full preflight and identical path walk just to reopen it.
        dir_fd = self._ensure_directory_open(path.parent, additional_bytes=len(data) + 4096)
        temp_name = "." + path.name + "." + uuid.uuid4().hex + ".pending"
        fd = None
        try:
            self.check(additional_bytes=len(data) + 4096)
            self._charge_write(len(data))
            fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                         0o644, dir_fd=dir_fd)
            for offset in range(0, len(data), MIB):
                block = memoryview(data)[offset:offset + MIB]
                self.check(additional_bytes=len(block))
                if os.fstat(fd).st_dev != self._pinned_dev or os.fstat(dir_fd).st_dev != self._pinned_dev:
                    raise GuardBlocked("El volumen cambió antes de escribir.", code="volume_changed")
                while block:
                    written = os.write(fd, block)
                    block = block[written:]
            self.check()
            os.fsync(fd)
            os.close(fd)
            fd = None
            self.check()
            os.rename(temp_name, path.name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
            os.fsync(dir_fd)
            self.check()
        finally:
            # A failed partial is deliberately retained; no manual cleanup here.
            if fd is not None:
                os.close(fd)
            os.close(dir_fd)

    def read_response(self, response, *, cancel_check=None):
        if cancel_check:
            cancel_check()
        self.check()
        header = response.headers.get("Content-Length") if hasattr(response, "headers") else None
        if header and str(header).isdigit() and int(header) > self.max_response_bytes:
            raise GuardBlocked("La fuente excede el máximo de respuesta de 32 MiB.", code="response_too_large")
        chunks, received = [], 0
        while True:
            if cancel_check:
                cancel_check()
            self.check(additional_bytes=received)
            block = response.read(min(MIB, self.max_response_bytes - received + 1))
            if cancel_check:
                cancel_check()
            if not block:
                break
            received += len(block)
            if received > self.max_response_bytes:
                raise GuardBlocked("La fuente excede el máximo de respuesta de 32 MiB.", code="response_too_large")
            chunks.append(block)
        self.check(additional_bytes=received)
        return b"".join(chunks)

    @contextmanager
    def meteo_lock(self):
        self.check(additional_bytes=4096)
        self.ensure_directory(self.output_root)
        directory = self._open_directory(self.output_root)
        fd = None
        try:
            self.check(additional_bytes=4096)
            fd = os.open(".meteo_download.lock", os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
                         0o644, dir_fd=directory)
            if os.fstat(fd).st_dev != self._pinned_dev:
                raise GuardBlocked("Lock meteorológico fuera del volumen.", code="volume_changed")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise GuardBlocked("Ya hay una descarga meteorológica que retiene el lock.", code="meteo_already_running") from exc
            os.fsync(directory)
            self.check()
            yield
        finally:
            if fd is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
            os.close(directory)
