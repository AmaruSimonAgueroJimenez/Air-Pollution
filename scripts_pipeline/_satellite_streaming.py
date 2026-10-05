"""Infraestructura transaccional para descargadores satelitales diarios.

Los HDF viven solamente dentro de ``_trabajo_descarga``. Una partición de
píxeles se marca terminada después de publicar y volver a leer su Parquet ZSTD;
recién entonces el llamador elimina el directorio HDF. Checksums, manifiestos,
bloqueo y limpieza de señales hacen la reanudación idempotente.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
from urllib.parse import unquote, urlsplit
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Iterator, Sequence

import pandas as pd


ESTADOS_TERMINADOS = frozenset({"ok", "sin_datos", "no_disponible"})


def requerir_modulos(*nombres: str) -> None:
    """Falla antes de autenticar/descargar si faltan lectores obligatorios."""
    faltan = [n for n in nombres if importlib.util.find_spec(n) is None]
    if faltan:
        raise SystemExit(
            "Faltan dependencias para procesar HDF/Parquet: "
            + ", ".join(faltan)
            + ". Activa el entorno que contiene pyhdf, rasterio, rioxarray, "
              "geopandas y pyarrow antes de iniciar la descarga."
        )


def fechas_inclusivas(desde: str, hasta: str) -> Iterator[date]:
    """Itera fechas ISO inclusivas, sin permitir días futuros."""
    try:
        ini = date.fromisoformat(desde)
        fin = min(date.fromisoformat(hasta), date.today())
    except ValueError as exc:
        raise ValueError("--desde/--hasta deben usar YYYY-MM-DD") from exc
    if ini > fin:
        raise ValueError(f"rango vacío: {ini} > {fin}")
    actual = ini
    while actual <= fin:
        yield actual
        actual += timedelta(days=1)


def sha256_archivo(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for bloque in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def sha256_conjunto(paths: Iterable[Path]) -> str:
    """Checksum reproducible de varios archivos (nombre + contenido)."""
    h = hashlib.sha256()
    for path in sorted((Path(p) for p in paths), key=lambda p: p.name):
        h.update(path.name.encode("utf-8"))
        h.update(b"\0")
        with path.open("rb") as fh:
            for bloque in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(bloque)
    return h.hexdigest()


def escribir_json_atomico(datos: dict, destino: Path) -> str:
    """Publica un manifiesto JSON canónico mediante fsync + replace."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".part")
    try:
        with parcial.open("w", encoding="utf-8") as fh:
            json.dump(datos, fh, ensure_ascii=False, sort_keys=True, indent=2,
                      default=str)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(parcial, destino)
        # El renombre del WAL también debe persistir antes de retirar fuentes.
        fd_directorio = os.open(destino.parent, os.O_RDONLY)
        try:
            os.fsync(fd_directorio)
        finally:
            os.close(fd_directorio)
    finally:
        parcial.unlink(missing_ok=True)
    return sha256_archivo(destino)


def describir_granulos(granulos: Iterable) -> list[dict]:
    """Extrae de resultados Earthaccess ID, URL y checksum de origen si existe."""

    def buscar_checksums(obj, out):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if "checksum" in str(k).lower() and not isinstance(v, (dict, list)):
                    out.append(str(v))
                else:
                    buscar_checksums(v, out)
        elif isinstance(obj, list):
            for v in obj:
                buscar_checksums(v, out)

    descripciones = []
    for g in granulos:
        try:
            meta = dict(g)
        except Exception:
            meta = {}
        concept_id = ""
        for ruta in (("meta", "concept-id"), ("meta", "native-id")):
            actual = meta
            try:
                for clave in ruta:
                    actual = actual[clave]
                if actual:
                    concept_id = str(actual)
                    break
            except Exception:
                continue
        try:
            urls = [str(u) for u in g.data_links()]
        except Exception:
            urls = []
        checksums: list[str] = []
        buscar_checksums(meta, checksums)
        descripciones.append({
            "concept_id": concept_id,
            "url": urls[0] if urls else "",
            "checksum_origen": sorted(set(checksums)),
        })
    return descripciones


def anotar_checksums_descargados(
    descripciones: Sequence[dict],
    paths: Sequence[Path],
) -> list[dict]:
    """Vincula cada gránulo CMR con el HDF local y calcula su SHA-256.

    CMR no siempre publica un checksum (p. ej. LAADS/LP DAAC devuelven una
    lista vacía). El hash se calcula mientras el crudo aún existe, antes del
    procesamiento y de su eliminación transaccional. También se comprueba que
    no falte ningún archivo anunciado: procesar una descarga parcial produciría
    una cobertura silenciosamente incompleta.
    """
    locales: dict[str, Path] = {}
    for item in paths:
        path = Path(item).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"descarga local ausente: {path}")
        if path.name in locales:
            raise ValueError(f"nombre de descarga local duplicado: {path.name}")
        locales[path.name] = path

    out: list[dict] = []
    usados: set[str] = set()
    faltantes: list[str] = []
    for original in descripciones:
        item = dict(original)
        nombre = Path(unquote(urlsplit(str(item.get("url", ""))).path)).name
        path = locales.get(nombre)
        if path is None:
            faltantes.append(nombre or str(item.get("concept_id", "sin-id")))
            out.append(item)
            continue
        item.update({
            "archivo_descargado": path.name,
            "bytes_descargados": int(path.stat().st_size),
            "sha256_descargado": sha256_archivo(path),
        })
        usados.add(path.name)
        out.append(item)

    extras = sorted(set(locales) - usados)
    if faltantes or extras:
        partes = []
        if faltantes:
            partes.append(f"faltan {sorted(faltantes)}")
        if extras:
            partes.append(f"sobran {extras}")
        raise RuntimeError(
            "descarga Earthdata no coincide con los gránulos CMR: "
            + "; ".join(partes)
        )
    return out


def componentes_shapefile(path: Path) -> list[Path]:
    """Lista todos los componentes existentes del shapefile, sin omitir CPG.

    El DBF y su archivo de codificación determinan las etiquetas comunales;
    hashear sólo ``.shp`` no basta para reproducir la máscara y sus atributos.
    """
    path = Path(path)
    componentes = [
        p for p in path.parent.glob(f"{path.stem}.*")
        if p.is_file()
    ]
    if path not in componentes:
        raise FileNotFoundError(f"no existe el shapefile: {path}")
    return sorted(componentes, key=lambda p: p.name.lower())


TERRITORIOS = ("continente", "juan_fernandez", "desventuradas", "rapa_nui")


def territorio_desde_lonlat(lon, lat):
    """Etiqueta componentes administrativos no antárticos de Chile."""
    import numpy as np

    lon = np.asarray(lon)
    lat = np.asarray(lat)
    out = np.full(lon.shape, "continente", dtype=object)
    out[lon < -100.0] = "rapa_nui"
    insular_oeste = (lon < -77.0) & (lon >= -100.0)
    out[insular_oeste & (lat < -30.0)] = "juan_fernandez"
    out[insular_oeste & (lat >= -30.0)] = "desventuradas"
    return out


def cobertura_territorios(valores) -> dict[str, int]:
    """Conteo completo, incluyendo territorios con cero observaciones."""
    import pandas as pd

    conteos = pd.Series(valores, dtype="object").value_counts().to_dict()
    return {t: int(conteos.get(t, 0)) for t in TERRITORIOS}


def validar_parquet(
    path: Path,
    columnas: Sequence[str],
    validar: Callable[[pd.DataFrame], None],
    columnas_validacion: Sequence[str] | None = None,
) -> int:
    """Valida esquema, metadatos y contenido crítico de un Parquet."""
    import pyarrow.parquet as pq

    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Parquet vacío o ausente: {path}")
    pf = pq.ParquetFile(path)
    nombres = set(pf.schema_arrow.names)
    faltan = [c for c in columnas if c not in nombres]
    if faltan:
        raise ValueError(f"Parquet sin columnas requeridas: {faltan}")
    if pf.metadata is None or pf.metadata.num_rows <= 0:
        raise ValueError("Parquet sin filas")
    cols = list(columnas_validacion or columnas)
    muestra = pd.read_parquet(path, columns=cols)
    if len(muestra) != pf.metadata.num_rows:
        raise ValueError("metadatos y lectura Parquet discrepan en número de filas")
    validar(muestra)
    return int(pf.metadata.num_rows)


def escribir_parquet_atomico(
    df: pd.DataFrame,
    destino: Path,
    columnas: Sequence[str],
    validar: Callable[[pd.DataFrame], None],
    columnas_validacion: Sequence[str] | None = None,
) -> tuple[int, str]:
    """Escribe Parquet ZSTD, valida el temporal y recién entonces lo publica.

    Si hay una versión final previa, permanece intacta hasta que el nuevo
    archivo pasa la validación completa. Un corte retira el ``.part.parquet``.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".part.parquet")
    try:
        df.loc[:, list(columnas)].to_parquet(
            parcial, index=False, engine="pyarrow", compression="zstd",
        )
        with parcial.open("rb") as fh:
            os.fsync(fh.fileno())
        filas = validar_parquet(
            parcial, columnas, validar,
            columnas_validacion=columnas_validacion,
        )
        os.replace(parcial, destino)
        # Verifica también el nombre publicado (detecta fallas del volumen).
        validar_parquet(
            destino, columnas, validar,
            columnas_validacion=columnas_validacion,
        )
        return filas, sha256_archivo(destino)
    finally:
        parcial.unlink(missing_ok=True)


@dataclass(frozen=True)
class Registro:
    fecha: str
    flujo: str
    estado: str
    filas: int
    sha256: str
    actualizado_utc: str


class Manifiesto:
    """Manifiesto CSV pequeño, actualizado por reemplazo atómico."""

    CAMPOS = ("fecha", "flujo", "estado", "filas", "sha256", "actualizado_utc")

    def __init__(self, path: Path):
        self.path = path
        self._registros: dict[tuple[str, str], Registro] = {}
        if path.exists():
            with path.open(newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    try:
                        reg = Registro(
                            fecha=row["fecha"], flujo=row["flujo"],
                            estado=row["estado"], filas=int(row.get("filas") or 0),
                            sha256=row.get("sha256", ""),
                            actualizado_utc=row.get("actualizado_utc", ""),
                        )
                    except (KeyError, ValueError):
                        continue
                    self._registros[(reg.fecha, reg.flujo)] = reg

    def obtener(self, fecha: str, flujo: str) -> Registro | None:
        return self._registros.get((fecha, flujo))

    def terminado(self, fecha: str, flujo: str) -> bool:
        reg = self.obtener(fecha, flujo)
        return bool(reg and reg.estado in ESTADOS_TERMINADOS)

    def marcar(
        self,
        fecha: str,
        flujo: str,
        estado: str,
        filas: int = 0,
        sha256: str = "",
    ) -> None:
        if estado not in ESTADOS_TERMINADOS | {"error"}:
            raise ValueError(f"estado de manifiesto inválido: {estado}")
        ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._registros[(fecha, flujo)] = Registro(
            fecha, flujo, estado, int(filas), sha256, ahora,
        )
        self._guardar()

    def _guardar(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        parcial = self.path.with_name(self.path.name + ".part")
        try:
            with parcial.open("w", newline="", encoding="utf-8") as fh:
                wr = csv.DictWriter(fh, fieldnames=self.CAMPOS)
                wr.writeheader()
                for key in sorted(self._registros):
                    wr.writerow(self._registros[key].__dict__)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(parcial, self.path)
        finally:
            parcial.unlink(missing_ok=True)


class AreaTrabajo(AbstractContextManager):
    """Área exclusiva de HDF con retención opcional hasta validar la procedencia.

    En modo ``preservar_no_validados`` ni el inicio, la reutilización de un día,
    ni una salida normal o interrumpida borran fuentes. El llamador sólo puede
    retirar explícitamente un día tras reabrir sus salidas y persistir su WAL.
    El modo heredado conserva su comportamiento de limpieza automática.
    INT/TERM se convierten en ``KeyboardInterrupt`` en ambos modos.
    """

    def __init__(self, root: Path, *, preservar_no_validados: bool = False):
        self.root = root.resolve()
        self.preservar_no_validados = preservar_no_validados
        self._signals: dict[int, object] = {}

    def __enter__(self):
        self._validar_raiz()
        if not self.preservar_no_validados:
            self.limpiar()
        self.root.mkdir(parents=True, exist_ok=True)
        for sig in (signal.SIGINT, signal.SIGTERM):
            self._signals[sig] = signal.getsignal(sig)
            signal.signal(sig, self._interrumpir)
        return self

    def _interrumpir(self, signum, _frame):
        raise KeyboardInterrupt(f"señal {signum}")

    def carpeta_dia(self, fecha: str, flujo: str) -> Path:
        seguro = re.sub(r"[^A-Za-z0-9_.-]+", "_", flujo)
        path = self.root / seguro / fecha
        if self.root not in path.resolve().parents:
            raise ValueError("ruta de trabajo fuera del área permitida")
        if not self.preservar_no_validados:
            shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def limpiar_dia(self, path: Path) -> None:
        rp = path.resolve()
        if rp != self.root and self.root not in rp.parents:
            raise ValueError("intento de limpiar fuera del área de trabajo")
        if self.preservar_no_validados:
            if rp == self.root:
                raise ValueError("la retirada validada debe limitarse a un día")
            if rp.exists():
                # No declarar crudos eliminados si el sistema de archivos falla.
                shutil.rmtree(rp)
            if rp.exists():
                raise OSError(f"no se retiró el día validado: {rp}")
        else:
            shutil.rmtree(rp, ignore_errors=True)

    def _validar_raiz(self) -> None:
        # ``root`` es una ruta fija bajo el producto, no acepta / ni HOME.
        if len(self.root.parts) < 4 or self.root == Path.home().resolve():
            raise ValueError(f"ruta de trabajo insegura: {self.root}")

    def limpiar(self) -> None:
        self._validar_raiz()
        if self.preservar_no_validados:
            raise ValueError("no se permite limpieza global de fuentes no validadas")
        shutil.rmtree(self.root, ignore_errors=True)

    def __exit__(self, exc_type, exc, tb):
        try:
            if not self.preservar_no_validados:
                self.limpiar()
        finally:
            for sig, previo in self._signals.items():
                signal.signal(sig, previo)
        return False


class BloqueoProceso(AbstractContextManager):
    """Impide dos escritores simultáneos sobre el mismo producto."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._fh = None

    def __enter__(self):
        import fcntl

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a+")
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._fh.close()
            self._fh = None
            raise RuntimeError(
                f"ya hay otro descargador usando {self.path.parent}"
            ) from exc
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(f"pid={os.getpid()}\n")
        self._fh.flush()
        return self

    def __exit__(self, exc_type, exc, tb):
        import fcntl

        if self._fh is not None:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            self._fh.close()
        return False


def deduplicar_granulos(resultados: Iterable) -> list:
    """Deduplica resultados CMR obtenidos desde más de un bbox."""
    vistos: set[str] = set()
    out = []
    for granulo in resultados:
        try:
            clave = granulo["meta"]["concept-id"]
        except Exception:
            try:
                clave = granulo.data_links()[0]
            except Exception:
                clave = repr(granulo)
        if clave in vistos:
            continue
        vistos.add(clave)
        out.append(granulo)
    return out


def salida_diaria(root: Path, fecha: str, nombre: str) -> Path:
    """Ruta Hive diaria estable: year=YYYY/month=MM/day=DD/nombre.parquet."""
    y, m, d = fecha.split("-")
    seguro = re.sub(r"[^A-Za-z0-9_.-]+", "_", nombre)
    return root / f"year={y}" / f"month={m}" / f"day={d}" / f"{seguro}.parquet"


def limpiar_parciales(*roots: Path) -> int:
    """Elimina sólo ``*.part`` de raíces explícitas de este pipeline."""
    borrados = 0
    for root in roots:
        root = Path(root).resolve()
        if root == Path.home().resolve() or len(root.parts) < 4:
            raise ValueError(f"raíz insegura para limpiar parciales: {root}")
        if not root.exists():
            continue
        candidatos = []
        if root.is_file():
            candidatos = [root] if ".part" in root.name else []
        else:
            candidatos = list(root.rglob("*.part")) + list(root.rglob("*.part.parquet"))
        for path in set(candidatos):
            if path.is_file():
                path.unlink()
                borrados += 1
    return borrados


def cargar_comunas(path: Path):
    """Carga las comunas oficiales en WGS84 con un índice entero interno."""
    try:
        import geopandas as gpd
    except ImportError as exc:
        raise RuntimeError("Falta geopandas para recortar a comunas") from exc
    if not path.is_file():
        raise FileNotFoundError(f"no existe el shapefile comunal: {path}")
    comunas = gpd.read_file(path).to_crs("EPSG:4326").reset_index(drop=True)
    requeridas = {"cod_comuna", "Comuna", "Region", "Provincia"}
    faltan = requeridas - set(comunas.columns)
    if faltan:
        raise ValueError(f"shapefile comunal sin campos {sorted(faltan)}")
    # El archivo oficial contiene algunos multipolígonos inválidos. Repararlos
    # evita perder comunas completas durante sjoin/rasterize.
    comunas.geometry = comunas.geometry.make_valid()
    comunas = comunas[~comunas.geometry.is_empty & comunas.geometry.notna()].copy()
    comunas = comunas.reset_index(drop=True)
    comunas["_ci"] = range(len(comunas))
    return comunas


def etiquetar_puntos_chile(
    lon,
    lat,
    comunas,
) -> tuple[object, object]:
    """Retorna posiciones originales e índices comunales de puntos en Chile.

    La unión espacial contra el polígono —no el bbox de búsqueda— constituye
    el recorte definitivo. Los puntos fuera de toda comuna quedan excluidos.
    """
    import geopandas as gpd
    import numpy as np

    lon = np.asarray(lon).ravel()
    lat = np.asarray(lat).ravel()
    finitos = np.isfinite(lon) & np.isfinite(lat)
    if not finitos.any():
        vacio = np.array([], dtype=np.int64)
        return vacio, vacio.copy()
    posiciones = np.flatnonzero(finitos)
    puntos = gpd.GeoDataFrame(
        {"_pos": posiciones},
        geometry=gpd.points_from_xy(lon[finitos], lat[finitos]),
        crs="EPSG:4326",
    )
    unidos = gpd.sjoin(
        puntos, comunas[["_ci", "geometry"]], how="inner", predicate="intersects",
    )
    if unidos.empty:
        vacio = np.array([], dtype=np.int64)
        return vacio, vacio.copy()
    # Polígonos administrativos no deberían solaparse; protege el borde igual.
    unidos = unidos.sort_values(["_pos", "_ci"]).drop_duplicates("_pos")
    return (
        unidos["_pos"].to_numpy(dtype=np.int64),
        unidos["_ci"].to_numpy(dtype=np.int64),
    )
