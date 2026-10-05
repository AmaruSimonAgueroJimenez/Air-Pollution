#!/usr/bin/env python3
"""Retira fuentes ERA5-Land heredadas solo tras validar su reemplazo final.

Este programa es deliberadamente separado de ``descargar_era5land.py`` para no
alterar una descarga que ya este en ejecucion. Examina exclusivamente los
NetCDF mensuales de ``ERA5Land/raw_chile`` y exige, para cada mes:

* salida final completa ``hora x pixel`` a 0,1 grados, con las seis variables;
* catalogo nativo y relacion pixel-comuna vigentes;
* hashes de salida, catalogo, relacion y fuentes iguales al manifiesto;
* fuente declarada por ruta exacta en el manifiesto del mes; y
* ausencia de una descarga ERA5-Land concurrente antes de cualquier borrado.

``--dry-run`` realiza las mismas lecturas y recalcula los hashes, pero no crea
locks, auditorias ni elimina archivos. La ejecucion real comparte el lock del
descargador y deja una bitacora JSONL durable, ademas de actualizar el
manifiesto mensual mediante el motor de normalizacion.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid

import pandas as pd


REPO = Path(__file__).resolve().parents[1]
EXTRACTORES = REPO / "scripts_superficie" / "extractores"
if str(EXTRACTORES) not in sys.path:
    sys.path.insert(0, str(EXTRACTORES))

import descargar_era5land as descargador  # noqa: E402
import normalizar_era5land_chile as motor  # noqa: E402


LEGADO = descargador.LEGADO.resolve()
RAIZ_SALIDA = motor.RAIZ_SALIDA.resolve()
CATALOGO = RAIZ_SALIDA / "catalogo_pixeles.parquet"
RELACION = RAIZ_SALIDA / "relacion_pixel_comuna.parquet"
AUDITORIA_DIR = RAIZ_SALIDA / "auditoria"
VARIABLES_REQUERIDAS = {"t2m", "d2m", "u10", "v10", "sp", "tp"}
PATRONES = (
    re.compile(r"^era5land_(?P<ym>\d{6})_chile\.nc$"),
    re.compile(r"^era5land_tp_(?P<ym>\d{6})\.nc$"),
)


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _periodo(valor: str) -> pd.Period:
    try:
        return pd.Period(str(valor)[:7], freq="M")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"mes/fecha invalido: {valor}") from exc


def _ruta_periodo(periodo: pd.Period) -> tuple[Path, Path]:
    ym = periodo.strftime("%Y%m")
    return (
        RAIZ_SALIDA / "mensual" / f"era5land_{ym}_chile_pixeles.nc",
        RAIZ_SALIDA / "manifiestos" / f"era5land_{ym}.json",
    )


def _periodo_nombre(path: Path) -> pd.Period | None:
    for patron in PATRONES:
        if coincidencia := patron.fullmatch(path.name):
            return pd.Period(coincidencia.group("ym"), freq="M")
    return None


def _fuentes_por_periodo(desde: pd.Period, hasta: pd.Period) -> dict[pd.Period, list[Path]]:
    resultado: dict[pd.Period, list[Path]] = {}
    if not LEGADO.is_dir():
        return resultado
    for path in sorted(LEGADO.iterdir()):
        periodo = _periodo_nombre(path)
        if periodo is None or periodo < desde or periodo > hasta:
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"fuente legacy no es un archivo regular: {path}")
        if path.resolve().parent != LEGADO:
            raise ValueError(f"fuente fuera de ERA5Land/raw_chile: {path}")
        resultado.setdefault(periodo, []).append(path.resolve())
    return resultado


def _leer_json(path: Path) -> dict:
    try:
        objeto = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f"manifiesto ilegible {path}: {exc}") from exc
    if not isinstance(objeto, dict):
        raise ValueError(f"manifiesto no es un objeto JSON: {path}")
    return objeto


@dataclass(frozen=True)
class MesValidado:
    periodo: pd.Period
    fuentes: tuple[Path, ...]
    salida: Path
    manifest: Path
    bytes_fuentes: int
    sha256_salida: str
    fuentes_declaradas: tuple[dict, ...]


def _validar_mes(
    periodo: pd.Period,
    fuentes: list[Path],
    *,
    recalcular_hashes_fuente: bool,
) -> MesValidado:
    salida, manifest = _ruta_periodo(periodo)
    for requerido in (salida, manifest, CATALOGO, RELACION):
        if not requerido.is_file():
            raise ValueError(f"falta artefacto final: {requerido}")

    meta = _leer_json(manifest)
    if meta.get("producto") != motor.PRODUCTO or meta.get("periodo") != str(periodo):
        raise ValueError("producto/periodo del manifiesto no coincide")
    parametros = meta.get("parametros_normalizacion", {})
    if bool(parametros.get("permitir_mes_parcial")):
        raise ValueError("un mes parcial nunca autoriza retirar fuentes")
    variables = set(parametros.get("variables_esperadas", []))
    if not VARIABLES_REQUERIDAS.issubset(variables):
        faltan = sorted(VARIABLES_REQUERIDAS - variables)
        raise ValueError(f"salida final sin variables requeridas: {faltan}")

    salida_declarada = Path(meta.get("salida", {}).get("archivo", "")).resolve()
    if salida_declarada != salida.resolve():
        raise ValueError("ruta de salida del manifiesto no coincide")
    catalogo_declarado = Path(meta.get("catalogo", {}).get("archivo", "")).resolve()
    relacion_declarada = Path(
        meta.get("relacion_pixel_comuna", {}).get("archivo", "")
    ).resolve()
    if catalogo_declarado != CATALOGO.resolve() or relacion_declarada != RELACION.resolve():
        raise ValueError("catalogo/relacion del manifiesto no coinciden")
    if not motor._catalogo_vigente(RAIZ_SALIDA, motor.COMUNAS):
        raise ValueError("catalogo nativo o mascara administrativa no estan vigentes")
    if motor.sha256_archivo(CATALOGO) != meta["catalogo"]["sha256"]:
        raise ValueError("hash del catalogo no coincide")
    if motor.sha256_archivo(RELACION) != meta["relacion_pixel_comuna"]["sha256"]:
        raise ValueError("hash de la relacion pixel-comuna no coincide")

    motor.validar_salida_mensual(
        salida,
        periodo,
        CATALOGO,
        sorted(VARIABLES_REQUERIDAS),
        permitir_parcial=False,
    )
    salida_hash = motor.sha256_archivo(salida)
    if salida_hash != meta["salida"]["sha256"]:
        raise ValueError("hash de la salida mensual no coincide")

    declaradas = {
        Path(item["ruta_al_normalizar"]).resolve(): item
        for item in meta.get("fuentes", [])
        if isinstance(item, dict) and item.get("ruta_al_normalizar")
    }
    info_fuentes: list[dict] = []
    for fuente in fuentes:
        item = declaradas.get(fuente)
        if item is None:
            raise ValueError(f"fuente legacy ajena al manifiesto: {fuente.name}")
        if int(item.get("bytes", -1)) != fuente.stat().st_size:
            raise ValueError(f"tamano de fuente cambio: {fuente.name}")
        if recalcular_hashes_fuente:
            actual = motor.sha256_archivo(fuente)
            if actual != item.get("sha256"):
                raise ValueError(f"hash de fuente cambio: {fuente.name}")
        info_fuentes.append(
            {
                "archivo": fuente.name,
                "ruta": str(fuente),
                "bytes": fuente.stat().st_size,
                "sha256": item.get("sha256"),
            }
        )
    return MesValidado(
        periodo=periodo,
        fuentes=tuple(fuentes),
        salida=salida,
        manifest=manifest,
        bytes_fuentes=sum(x.stat().st_size for x in fuentes),
        sha256_salida=salida_hash,
        fuentes_declaradas=tuple(info_fuentes),
    )


class Auditoria:
    def __init__(self, desde: pd.Period, hasta: pd.Period, reserva_gib: float):
        motor.asegurar_disco_externo(AUDITORIA_DIR)
        AUDITORIA_DIR.mkdir(parents=True, exist_ok=True)
        self.ejecucion = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "-" + uuid.uuid4().hex[:8]
        )
        self.path = AUDITORIA_DIR / f"retiro_legado_{self.ejecucion}.jsonl"
        self.registrar(
            "inicio",
            desde=str(desde),
            hasta=str(hasta),
            reserva_gib=reserva_gib,
            script=str(Path(__file__).resolve()),
            script_sha256=motor.sha256_archivo(Path(__file__)),
            motor_sha256=motor.sha256_archivo(Path(motor.__file__)),
            descargador_sha256=motor.sha256_archivo(Path(descargador.__file__)),
        )

    def registrar(self, evento: str, **datos) -> None:
        registro = {
            "schema": "airpollution.era5land-legacy-retirement.v1",
            "ejecucion": self.ejecucion,
            "registrado_utc": _ahora(),
            "evento": evento,
            **datos,
        }
        linea = json.dumps(registro, ensure_ascii=False, sort_keys=True, default=str) + "\n"
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(linea)
            fh.flush()
            os.fsync(fh.fileno())


def _reserva_gib() -> float:
    motor.asegurar_disco_externo(LEGADO)
    return shutil.disk_usage(LEGADO).free / 1024**3


def _descargas_activas() -> list[int]:
    return descargador._otros_descargadores_python()


def _planificar(
    desde: pd.Period,
    hasta: pd.Period,
    *,
    recalcular_hashes_fuente: bool,
) -> tuple[list[MesValidado], list[dict]]:
    planes: list[MesValidado] = []
    bloqueados: list[dict] = []
    for periodo, fuentes in sorted(_fuentes_por_periodo(desde, hasta).items()):
        try:
            planes.append(
                _validar_mes(
                    periodo,
                    fuentes,
                    recalcular_hashes_fuente=recalcular_hashes_fuente,
                )
            )
        except Exception as exc:  # cada mes se informa sin ocultar los demas
            bloqueados.append(
                {
                    "periodo": str(periodo),
                    "fuentes": [x.name for x in fuentes],
                    "motivo": f"{type(exc).__name__}: {exc}",
                }
            )
    return planes, bloqueados


def _imprimir_resumen(planes: list[MesValidado], bloqueados: list[dict], *, dry_run: bool) -> None:
    bytes_total = sum(x.bytes_fuentes for x in planes)
    accion = "ELIMINARIA" if dry_run else "ELIMINO"
    print(
        f"{accion}: {sum(len(x.fuentes) for x in planes)} fuentes de "
        f"{len(planes)} meses; {bytes_total / 1024**3:.2f} GiB"
    )
    if bloqueados:
        print(f"BLOQUEADOS: {len(bloqueados)} meses")
        for item in bloqueados:
            print(f"  {item['periodo']}: {item['motivo']}")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--desde", type=_periodo, default=_periodo("2000-01"))
    p.add_argument("--hasta", type=_periodo, default=_periodo(date.today().isoformat()))
    p.add_argument(
        "--min-gb-libres",
        type=float,
        default=100.0,
        help="reserva minima exigida en /Volumes/Datos (default: 100 GiB)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="recalcula hashes y muestra el plan; no escribe ni elimina",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.desde > args.hasta:
        raise SystemExit("--desde no puede ser posterior a --hasta")
    if args.min_gb_libres < 0:
        raise SystemExit("--min-gb-libres debe ser no negativo")
    libres = _reserva_gib()
    if libres < args.min_gb_libres:
        raise SystemExit(
            f"reserva insuficiente: {libres:.1f} GiB libres; se exigen "
            f"{args.min_gb_libres:.1f} GiB"
        )

    activos = _descargas_activas()
    if args.dry_run:
        if activos:
            print(
                "AVISO: hay descarga ERA5-Land activa; la simulacion es de solo "
                f"lectura (PID {activos})"
            )
        planes, bloqueados = _planificar(
            args.desde,
            args.hasta,
            recalcular_hashes_fuente=True,
        )
        _imprimir_resumen(planes, bloqueados, dry_run=True)
        return 1 if bloqueados else 0

    # El lock compartido vuelve imposible borrar mientras el descargador usa el
    # legado. No se crea siquiera la auditoria antes de adquirirlo.
    with descargador.bloqueo_exclusivo(LEGADO):
        auditoria = Auditoria(args.desde, args.hasta, args.min_gb_libres)
        planes, bloqueados = _planificar(
            args.desde,
            args.hasta,
            recalcular_hashes_fuente=False,
        )
        for item in bloqueados:
            auditoria.registrar("mes_bloqueado", **item)
        eliminados = 0
        bytes_liberados = 0
        for plan in planes:
            auditoria.registrar(
                "retiro_preparado",
                periodo=str(plan.periodo),
                salida=str(plan.salida),
                sha256_salida=plan.sha256_salida,
                fuentes=plan.fuentes_declaradas,
            )
            try:
                liberados = motor.eliminar_fuentes_validadas(
                    plan.fuentes,
                    plan.salida,
                    plan.manifest,
                    plan.periodo,
                    CATALOGO,
                    permitir_parcial=False,
                )
                if any(path.exists() for path in plan.fuentes):
                    raise IOError("alguna fuente sigue presente despues del retiro")
                meta_final = _leer_json(plan.manifest)
                registradas = set(meta_final.get("rutas_fuentes_eliminadas", []))
                faltan = [str(x) for x in plan.fuentes if str(x) not in registradas]
                if faltan:
                    raise ValueError(f"manifiesto no registro fuentes retiradas: {faltan}")
                auditoria.registrar(
                    "fuentes_eliminadas",
                    periodo=str(plan.periodo),
                    fuentes=[str(x) for x in plan.fuentes],
                    bytes_liberados=liberados,
                    manifest=str(plan.manifest),
                    sha256_manifest=motor.sha256_archivo(plan.manifest),
                )
                eliminados += len(plan.fuentes)
                bytes_liberados += liberados
            except BaseException as exc:
                auditoria.registrar(
                    "error_retiro",
                    periodo=str(plan.periodo),
                    error=f"{type(exc).__name__}: {exc}",
                )
                auditoria.registrar(
                    "fin",
                    estado="error",
                    fuentes_eliminadas=eliminados,
                    bytes_liberados=bytes_liberados,
                )
                raise
        estado = "completo" if not bloqueados else "incompleto"
        auditoria.registrar(
            "fin",
            estado=estado,
            meses_retirados=len(planes),
            meses_bloqueados=len(bloqueados),
            fuentes_eliminadas=eliminados,
            bytes_liberados=bytes_liberados,
            libres_gib_despues=_reserva_gib(),
        )
        print(f"AUDITORIA: {auditoria.path}")
    _imprimir_resumen(planes, bloqueados, dry_run=False)
    return 1 if bloqueados else 0


if __name__ == "__main__":
    raise SystemExit(main())
