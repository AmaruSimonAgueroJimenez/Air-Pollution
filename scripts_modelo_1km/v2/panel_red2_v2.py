#!/usr/bin/env python3
"""Paneles de la red ampliada (bloque R11 y R3-R10): una sola elaboración para todas las filas, con los insumos de hoy.

La v2 deja de leer los paneles v1 (que quedan intactos) y lee ``<raíz v2>/paneles/panel_{pm25,no2}_red2.parquet``.
Este módulo los arma con el código de la v1 —``construir_panel``, ``satelites_estaciones``, ``observaciones_panel`` y
``matriz_vecindario`` del documento (``docs/modelo_1km_horario.qmd``, líneas 1968-2110 en d54012c, iguales en la copia
de trabajo en 1492-1634), replicados aquí con sus mismas llamadas a ``_features`` y ``_comun_modelo``, que se importan
**sólo después de comprobar su sha256** (``HUELLAS_CODIGO_V1``)— y con estas reglas del bloque:

* **Fuentes (R2):** el derivado SINCA de la red 2 (``derivado_red2_v2``: maestro sellado + actualización + ampliación),
  los dos maestros de coordenadas de R8 y los 3 monitores SNIFA. La lista cerrada se comprueba antes de leer nada.
* **Unidades (R6):** factor de ``unidades_v2`` por serie (contraste CAMS y, si no decide, el rótulo); las series sin
  unidad quedan fuera, salvo las que el contraste ubica (609 y 517 de O3 en la primera corrida). SNIFA El Peñón × 0,5318.
* **Reloj (R7):** UTC−4 fijo, salvo los estación-años con veredicto ``hora_civil`` de ``reloj_sinca_v2``, que se
  convierten con su zona IANA; dos etiquetas en la misma hora UTC se promedian, con conteo y bandera.
* **Calidad (R5):** filas ``seleccionada``; valor finito y en rango **después de convertir** (PM2,5 0-1.500 µg/m³; NO2
  0-1.000 ppb; O3 0-500 ppb); media por estación × hora; rachas de ≥ 24 registros idénticos sobre el registro completo;
  celda ≥ 0. La bandera ``qc`` (la peor de la hora) va a ``calidad_<pol>_red2.parquet``, alineada 1 a 1 con el panel.
* **Período (R4):** del 2000-01-01 al 2026-10-24 por día local UTC−4, como ``observaciones_panel``.
* **Duplicados (R9):** una copia por hora (``duplicados_v2``), antes de cualquier ajuste.
* **Insumos de hoy (R11):** ``inventario_insumos`` lista, por producto, los archivos cuyo registro en su manifiesto es
  anterior al **2026-10-25 03:00 UTC**, con su huella declarada; sólo las órbitas antiguas de TROPOMI (también las 146
  de 2024 del formato antiguo, T11 [delegada]) y GEOS-CF, que no tienen registro propio, entran por su fecha de
  modificación (lectura T1(4) del autor). ``congelar_insumos`` **copia**
  cada archivo que entra a la raíz v2 calculando su sha256 y se detiene si no calza con la declarada; los lectores de la
  v1 leen esa copia (``AIR_POLLUTION_DATA_ROOT``), de modo que nada de lo que cambie después en el disco de datos entra.
  MERRA-2 2026-10 sale de la copia de corte de T3 si el archivo del disco cambió. Las extensiones del §11 que estén en
  esa lista entran sin variante ni comparación (R11, R12).
* **Predictores:** las listas cerradas de 70 y 69 del §3 (``config_v2.json``); se exige que estén todas en el panel.
* **Regímenes (R17):** ``regimenes_calculados`` los vuelve a definir con la regla fija del bloque y los escribe en el
  json del panel, antes de cualquier ajuste.

Nada se escribe fuera de la raíz v2 (guarda y candados de ``_rutas_v2``), ni antes de confirmar la traducción en git. La v1 (paneles, grilla, satélites y derivado)
no se toca. Cada json que se escribe (los de cada panel y de O3, ``regimenes_red2.json``, ``inventario.json``,
``congelados.json`` y el registro MAIAC) lleva su procedencia (§0 del contrato): ``red_ampliada_v2.traza_red2``, con el
commit, la huella del código, las bibliotecas, los hilos y la traducción con que se escribió.

Uso::

    python -B scripts_modelo_1km/v2/panel_red2_v2.py --plan                 # inventario y conteos (no escribe)
    python -B scripts_modelo_1km/v2/panel_red2_v2.py --medir                # costo con una muestra pequeña (no escribe)
    python -B scripts_modelo_1km/v2/panel_red2_v2.py --registrar-catalogo-maiac          # T5, antes del armado
    python -B scripts_modelo_1km/v2/panel_red2_v2.py --ejecutar --derivado <raíz red 2> --contraste <csv> \\
        --contraste-sha256 <huella> --veredictos <parquet> [--convencion-civil fin|inicio_mas_1h] --procesos 8

El registro de los catálogos MAIAC y el armado (R22, paso 3) sólo corren con la traducción confirmada en git. La
convención de la etiqueta civil la toma el armado del ``resumen.json`` de ``reloj_sinca_v2`` (regla T4), verificando
su huella y volviendo a calcularla con los veredictos; ``--convencion-civil`` sólo puede confirmarla.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
REPO = AQUI.parents[1]
V1 = REPO / "scripts_modelo_1km"
sys.path.insert(0, str(AQUI))
import _rutas_v2 as rv  # noqa: E402
import calidad_v2 as cv  # noqa: E402
import duplicados_v2 as dv  # noqa: E402
import red_ampliada_v2 as ra  # noqa: E402
import reloj_sinca_v2 as rs  # noqa: E402
import unidades_v2 as uv  # noqa: E402

SCHEMA = "airpollution.modelo-1km-v2.panel-red2.v1"
SCHEMA_INVENTARIO = "airpollution.modelo-1km-v2.insumos-red2.v1"
DESDE, HASTA = "2000-01-01", "2026-10-24"                  # R4
CORTE_INSUMOS_UTC = "2026-10-25T03:00:00Z"                  # R11: fin del 2026-10-24 en Chile continental
CONTAMINANTES_PANEL = ("pm25", "no2")
RAMA_O3 = "o3"
NOMBRE_OBS_O3 = "observaciones_o3_red2.parquet"
NOMBRE_RELOJ = "reloj_civil_{pol}_red2.parquet"
NOMBRE_OBS = "observaciones_{pol}_red2.parquet"
NOMBRE_ESTACIONES = "estaciones_red2.parquet"
NOMBRE_REGIMENES = "regimenes_red2.json"
RANGO = {"pm25": (0.0, 1500.0), "no2": (0.0, 1000.0), "o3": (0.0, 500.0)}    # R5, en la unidad del modelo
QC_RACHA = 24
OFFSET_UTC_H = 4
RED_SINCA, RED_SNIFA = "sinca", "snifa"
NOMBRE_PANEL = "panel_{pol}_red2.parquet"
NOMBRE_CALIDAD = "calidad_{pol}_red2.parquet"
NOMBRE_SATELITES = "satelites_estaciones_red2.parquet"
NOMBRE_ENLACES = "estaciones_enlaces_red2.parquet"

# Código v1 que se importa en el armado y lo que él importa del pipeline, con la huella que tenía al traducir el
# bloque (2026-10-25). Rutas relativas al repositorio. Un archivo «adaptado» entre AP y el espejo (grupo «adaptados»
# de config/componentes_compartidos.json) lleva la huella de cada repositorio, por su nombre: la compuerta se lanza
# desde cualquiera de los dos y verificar_codigo_v1 lee el archivo del repositorio desde el que corre.
HUELLAS_CODIGO_V1 = {
    "scripts_modelo_1km/_comun_modelo.py": "a83c0384266554e16ab397749544759ae1cf161f138361eefa7d1ad3e29aa6f4",
    "scripts_modelo_1km/_features.py": "8fd699929c117067962e9ed24c0ea6b137d0c58d5ca17b9fce3a3759793d6838",
    "scripts_modelo_1km/construir_grilla.py": "56c014f9079cb7d69092a84239894a8d8e5d711fba1a66bafe3d97d99bb9742e",
    "scripts_pipeline/_common.py": "f0f648182802478c8ed41709daabe3abe21e40be46ffdf6fd2c4a0a67de9a260",
    "scripts_pipeline/_manifiesto_satelital.py": "1f74b85de820ddd6a6ce5a2a31343f02a9170a529d6e3f16c764801bf0ea565d",
    "scripts_pipeline/_satellite_streaming.py": "eaa78b1c0c330b54405f0614151c3d05e3a7fef1e303227891080c53407e979d",
    # T12 (corrección, [delegada]): el armado importa produccion.py (importar_produccion) y marca las rachas con su
    # marcar_rachas, la regla de produccion.observaciones. Es «adaptado»: el espejo sólo cambia el comentario de las
    # líneas 129-130 (config/componentes_compartidos.json), así que su huella va por repositorio.
    "scripts_modelo_1km/produccion.py": {
        "Air-Pollution": "dd2db2efad4aa202d58186ea2b3b0629614469a632dc891033c6a0568bc246af",
        "Air-Pollution-Health-Chile": "e9e18b5af31870cdc6c41d1fe6b47fa6d46292e504b42b5ecf4ffa1737e717ec"},
    # lo que importa produccion.py además de lo de arriba (con MODELO_1KM_RED_ADICIONAL=0 sólo define constantes)
    "scripts_modelo_1km/_red_adicional.py": "f7ab850b4784afa648e7e579294dee8f9e1a34c400b20a766a10e590a395941c",
}
DOCUMENTO_V1 = {"archivo": "docs/modelo_1km_horario.qmd", "commit": "d54012c", "lineas": "1968-2110",
                "funciones": ["estaciones_con_celda", "satelites_estaciones", "observaciones_panel",
                              "matriz_vecindario", "construir_panel", "identidad_red"]}
INSUMOS_GRILLA_V1 = ("celdas.parquet", "enlaces_productos.parquet", "estaticas.parquet", "estaticas_lulc.parquet",
                     "estaciones_enlaces.parquet", "estaciones_enlaces_adicional.parquet", "metadata.json")

# Candados de los artefactos nuevos (se registran al importar, como pide _rutas_v2).
rv.registrar_candado("raiz_v2", r"paneles/[^/]*_red2(?:_[^/]+)?\.(?:parquet|json|csv)", "panel_red2")
rv.registrar_candado("raiz_v2", r"insumos_red2/.+", "insumos_red2")
rv.registrar_candado("raiz_v2", r"grilla/estaciones_enlaces_red2\.(?:parquet|json)", "grilla_red2")

# ---------------------------------------------------------------------------
# Inventario de insumos (R11) y congelado
# ---------------------------------------------------------------------------
# Reglas de registro (R11, con la lectura T1(4) del autor, decisiones_autor_traduccion_20261025.md):
# * productos mensuales: el manifiesto del mes (``publicado_utc`` y ``salida.sha256``); sin manifiesto, no entran;
# * TROPOMI NO2 y ACAG: el último evento ``archivo_validado`` (``registrado_utc`` y ``sha256_salida``);
# * MAIAC: la última fila del día en ``manifest_pixeles_horario.csv``, cuya huella reúne las de sus archivos;
# * catálogos de píxeles: la huella que declaran los manifiestos mensuales de su producto; las teselas del catálogo
#   MAIAC, la de su registro de T5 (``registro_catalogo_maiac``), si su archivo es anterior al corte;
# * sólo las órbitas de TROPOMI sin evento propio (dentro de ``TROPOMI_MTIME_ANIOS``) y los archivos de GEOS-CF (sin
#   manifiesto) entran por su fecha de modificación, como autorizaron T1(4) y T11 [delegada]; su huella se calcula y se
#   registra al congelarlos, y el anexo cuenta por año lo que entra así. Nada más entra así.
# Al armar, cada archivo que entra se **copia** a la raíz v2 calculando su sha256 (``congelar_insumos``); si no calza con
# la huella declarada, el armado se detiene. Los lectores de la v1 leen esa copia, no el disco de datos.
PRODUCTOS_MENSUALES = {
    "era5land": ("ERA5Land/chile_nativo_01deg", "era5land_{m}.json"),
    "era5blh": ("ERA5/chile_nativo_025deg", "era5_blh_{m}.json"),
    "merra2": ("MERRA2_meteo/chile_nativo_05x0625deg", "merra2_meteo_{m}.json"),
    "cams": ("CAMS_EAC4/chile_nativo_075deg", "cams_eac4_{m}.json"),
}
CATALOGO_MAIAC = "MCD19A2.061/pixeles_horario/catalogo_pixeles"
# T3 (decisiones_autor_traduccion_20261025.md): copia de MERRA-2 2026-10 en el disco interno, relativa a la raíz local.
COPIAS_DE_CORTE = {
    "contaminantes/MERRA2_meteo/chile_nativo_05x0625deg/mensual/merra2_meteo_202610_chile_pixeles.nc": {
        "copia": "copias_corte_20261024/merra2_meteo/merra2_meteo_202610_chile_pixeles.nc",
        "sha256": "6c32980582930e257d366508d2211e73dbe650e80fc22c30df2afde2f5aa9364",
        "manifiesto": "copias_corte_20261024/merra2_meteo/merra2_meteo_202610.json",
        "sha256_manifiesto": "367b4d365ce374def3d37f7d011534e504b80afa1219b4f807ccaef035460bde",
        "sumas": "copias_corte_20261024/merra2_meteo/SHA256SUMS.txt",
        "sha256_sumas": "167269731fa901cd001311da8e6d902c1a6578044152567c472710f2a3676f66"},
}
# T1(4) y T11 [delegada, ratificada por el autor el 2026-10-26] (decisiones_autor_traduccion_20261025.md, 2026-10-26):
# las órbitas de TROPOMI sin evento propio entran por su fecha de modificación, sin límite de año de adquisición
# (None), también las 146 de 2024 del formato antiguo. El anexo lista por año las que entran así (``resumen_inventario``).
TROPOMI_MTIME_ANIOS: tuple[int, int] | None = None
HUELLA_EXACTA, HUELLA_PARTE, HUELLA_REGISTRAR = "sha256", "parte_de_la_huella_del_dia", "se_calcula_y_registra_T1_4"
COLUMNAS_INVENTARIO = ["producto", "clave", "ruta", "origen", "bytes", "sha256_declarado", "verificacion",
                       "registrado_utc", "fuente_registro", "entra", "motivo"]


def utc(texto) -> pd.Timestamp:
    t = pd.Timestamp(texto)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _mtime_utc(p: Path) -> pd.Timestamp:
    return pd.Timestamp(os.stat(p).st_mtime, unit="s", tz="UTC")


def raiz_local(entorno=None) -> Path:
    """Raíz local de AirPollution (``AIR_POLLUTION_LOCAL_ROOT`` o ``~/Asesorias_Data_local/AirPollution``), la misma
    regla de ``_rutas_v2.RutasV2.desde_entorno``; ahí está la copia de corte de T3."""
    e = os.environ if entorno is None else entorno
    return Path(e.get(rv.VAR_LOCAL) or Path.home() / "Asesorias_Data_local" / "AirPollution").expanduser()


def _fila(producto, clave, rel, bytes_, sha, reg, fuente, corte, verificacion=HUELLA_EXACTA, motivo: str = "",
          origen: str = "datos") -> dict:
    entra = reg is not None and reg < corte and not motivo
    if not motivo and not entra:
        motivo = "registrado después del corte"
    return {"producto": producto, "clave": clave, "ruta": rel, "origen": origen,
            "bytes": None if bytes_ is None else int(bytes_), "sha256_declarado": sha, "verificacion": verificacion,
            "registrado_utc": None if reg is None else reg.isoformat(), "fuente_registro": fuente,
            "entra": bool(entra), "motivo": motivo}


def copia_de_corte(rel: str, local: Path, copias: dict) -> dict | None:
    """La copia de corte de ``rel``, si existe y se registró antes del corte con su huella: {origen, sha256,
    registrado_utc}. La huella se vuelve a comprobar al congelar."""
    c = copias.get(rel)
    if c is None:
        return None
    archivo, manifiesto = Path(local) / c["copia"], Path(local) / c["manifiesto"]
    if not (archivo.exists() and manifiesto.exists()):
        return None
    if uv.sha256_archivo(manifiesto) != c["sha256_manifiesto"]:
        raise SystemExit(f"la copia de corte de {Path(rel).name}: su manifiesto no tiene la huella registrada")
    if "sumas" in c:                                      # T3: su SHA256SUMS.txt, también por su huella
        sumas = Path(local) / c["sumas"]
        if not sumas.exists() or not c.get("sha256_sumas") or uv.sha256_archivo(sumas) != c["sha256_sumas"]:
            raise SystemExit(f"la copia de corte de {Path(rel).name}: su {Path(c['sumas']).name} falta o no tiene la "
                             f"huella registrada")
    d = json.loads(manifiesto.read_text(encoding="utf-8"))
    if d["salida"]["sha256"] != c["sha256"] or Path(d["salida"]["archivo"]).name != Path(rel).name:
        raise SystemExit(f"la copia de corte de {Path(rel).name} no es la que describe su manifiesto")
    return {"origen": f"copia_de_corte:{c['copia']}", "sha256": c["sha256"], "registrado_utc": utc(d["publicado_utc"]),
            "bytes": d["salida"].get("bytes")}


def inventario_mensual(cont: Path, producto: str, corte: pd.Timestamp, local: Path | None = None,
                       copias: dict | None = None) -> list[dict]:
    """Productos con un NetCDF por mes y un manifiesto JSON por mes. Entra si su manifiesto se publicó antes del
    corte; si se volvió a publicar después y hay copia de corte (T3), entra la copia. Sin manifiesto, no entra."""
    carpeta, patron = PRODUCTOS_MENSUALES[producto]
    base = Path(cont) / carpeta
    copias = COPIAS_DE_CORTE if copias is None else copias
    filas = []
    for nc in sorted((base / "mensual").glob("*.nc")):
        m = re.search(r"_(\d{6})_", nc.name)
        if not m:
            continue
        mes = m.group(1)
        rel = f"contaminantes/{carpeta}/mensual/{nc.name}"
        man = base / "manifiestos" / patron.format(m=mes)
        if not man.exists():
            filas.append(_fila(producto, mes, rel, nc.stat().st_size, None, None, "sin manifiesto", corte,
                               motivo="sin manifiesto: la fecha de modificación sólo vale para T1(4)"))
            continue
        d = json.loads(man.read_text(encoding="utf-8"))
        sal = d.get("salida") or {}
        if Path(str(sal.get("archivo", ""))).name != nc.name:
            filas.append(_fila(producto, mes, rel, None, None, None, "manifiesto.publicado_utc", corte,
                               motivo="el manifiesto describe otro archivo"))
            continue
        reg = utc(d["publicado_utc"])
        if reg >= corte:
            c = copia_de_corte(rel, local or raiz_local(), copias)
            if c is not None and c["registrado_utc"] < corte:
                filas.append(_fila(producto, mes, rel, c["bytes"], c["sha256"], c["registrado_utc"],
                                   "copia de corte (T3)", corte, origen=c["origen"]))
                continue
        filas.append(_fila(producto, mes, rel, sal.get("bytes"), sal.get("sha256"), reg, "manifiesto.publicado_utc",
                           corte))
    return filas


def inventario_geoscf(cont: Path, corte: pd.Timestamp) -> list[dict]:
    """GEOS-CF ``raw_chile/geoscf_AAAAMM.nc``: no tiene registro propio; entra por su fecha de modificación (T1(4))."""
    filas = []
    for nc in sorted((Path(cont) / "GEOS_CF" / "raw_chile").glob("geoscf_*.nc")):
        mes = nc.stem.split("_", 1)[1]
        filas.append(_fila("geoscf", mes, f"contaminantes/GEOS_CF/raw_chile/{nc.name}", nc.stat().st_size, None,
                           _mtime_utc(nc), "mtime (sin registro propio; T1(4))", corte, verificacion=HUELLA_REGISTRAR))
    return filas


def _eventos_validados(carpeta: Path) -> dict[str, list[tuple[pd.Timestamp, str | None]]]:
    """{nombre de archivo: [(registrado_utc, sha256_salida)]} de los eventos ``archivo_validado`` de los jsonl."""
    out: dict[str, list] = {}
    for f in sorted(Path(carpeta).glob("*.jsonl")):
        with open(f, encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea:
                    continue
                d = json.loads(linea)
                if d.get("evento") != "archivo_validado":
                    continue
                sal = d.get("salida")
                nombre = Path(str(sal.get("ruta") if isinstance(sal, dict) else sal)).name
                out.setdefault(nombre, []).append((utc(d["registrado_utc"]), d.get("sha256_salida")))
    return out


def anio_de_orbita(nombre: str) -> int | None:
    """Año de adquisición de una órbita TROPOMI por su nombre (``…_YYYYMMDDTHHMMSS_…``), o None."""
    m = re.search(r"_(\d{4})\d{4}T\d{6}_", nombre)
    return int(m.group(1)) if m else None


def inventario_por_eventos(cont: Path, producto: str, carpeta_datos: str, carpeta_eventos: str, patron: str,
                           corte: pd.Timestamp, permitir_mtime: bool, anios_mtime: tuple[int, int] | None = None
                           ) -> list[dict]:
    """Archivos con eventos ``archivo_validado`` (TROPOMI NO2, ACAG). Rige el último evento del archivo: si es
    posterior al corte, el archivo en disco ya no es el de antes del corte y no entra. Los archivos sin evento propio
    entran por su fecha de modificación sólo si ``permitir_mtime`` (las órbitas antiguas de TROPOMI, T1(4)) y, si se da
    ``anios_mtime`` (desde, hasta), sólo las órbitas de esos años de adquisición; las demás quedan fuera, anotadas."""
    base = Path(cont)
    eventos = _eventos_validados(base / carpeta_eventos)
    filas = []
    for nc in sorted((base / carpeta_datos).glob(patron)):
        rel = f"contaminantes/{carpeta_datos}/{nc.name}"
        ev = sorted(eventos.get(nc.name, []), key=lambda x: x[0])
        if ev:
            reg, sha = ev[-1]
            filas.append(_fila(producto, nc.name, rel, nc.stat().st_size, sha, reg, "evento archivo_validado", corte,
                               motivo="" if reg < corte else "validado de nuevo después del corte"))
        elif permitir_mtime and anios_mtime is not None and not (
                anios_mtime[0] <= (anio_de_orbita(nc.name) or -1) <= anios_mtime[1]):
            filas.append(_fila(producto, nc.name, rel, nc.stat().st_size, None, None, "sin evento", corte,
                               motivo=f"sin evento y fuera de los años por fecha de modificación {anios_mtime}"))
        elif permitir_mtime:
            filas.append(_fila(producto, nc.name, rel, nc.stat().st_size, None, _mtime_utc(nc),
                               "mtime (órbita antigua sin evento propio; T1(4))", corte, verificacion=HUELLA_REGISTRAR))
        else:
            filas.append(_fila(producto, nc.name, rel, nc.stat().st_size, None, None, "sin evento", corte,
                               motivo="sin evento archivo_validado: la fecha de modificación sólo vale para T1(4)"))
    return filas


def _ruta_maiac(tipo: str, fecha: str) -> str:
    y, m, d = fecha.split("-")
    sub = f"year={y}/month={m}/day={d}"
    nombre = {"observaciones": f"maiac_obs_{y}{m}{d}.parquet", "catalogo_pasadas": f"maiac_pasadas_{y}{m}{d}.parquet"}
    return f"contaminantes/MCD19A2.061/pixeles_horario/{tipo}/{sub}/{nombre[tipo]}"


def inventario_maiac(datos: Path, corte: pd.Timestamp) -> list[dict]:
    """MAIAC: ``manifest_pixeles_horario.csv`` (``fecha``, ``estado``, ``sha256``, ``actualizado_utc``); rige la última
    fila de cada fecha, y su ``sha256`` reúne con «+» las huellas de sus archivos. Un día con estado distinto de
    ``ok`` no tiene archivos que leer. Los archivos del disco sin fila en el manifiesto no entran."""
    datos = Path(datos)
    man = datos / "contaminantes" / "MCD19A2.061" / "manifest_pixeles_horario.csv"
    filas = []
    if not man.exists():
        return filas
    m = pd.read_csv(man, dtype=str)
    m["_t"] = m["actualizado_utc"].map(utc)
    vistos = set()
    for fecha, g in m.sort_values("_t", kind="stable").groupby("fecha", sort=True):
        ult = g.iloc[-1]
        if ult["estado"] != "ok":
            continue
        for tipo in ("observaciones", "catalogo_pasadas"):
            rel = _ruta_maiac(tipo, fecha)
            vistos.add(rel)
            p = datos / rel
            if not p.exists():
                filas.append(_fila("maiac", f"{fecha}:{tipo}", rel, None, ult["sha256"], ult["_t"],
                                   "manifest_pixeles_horario.actualizado_utc", corte, HUELLA_PARTE, "falta en el disco"))
                continue
            filas.append(_fila("maiac", f"{fecha}:{tipo}", rel, p.stat().st_size, ult["sha256"], ult["_t"],
                               "manifest_pixeles_horario.actualizado_utc", corte, HUELLA_PARTE))
    base = datos / "contaminantes" / "MCD19A2.061" / "pixeles_horario"
    for tipo in ("observaciones", "catalogo_pasadas"):
        for q in sorted((base / tipo).rglob("*.parquet")):
            rel = str(q.relative_to(datos))
            if rel not in vistos:
                filas.append(_fila("maiac", f"{q.stem}:{tipo}", rel, q.stat().st_size, None, None, "sin registro", corte,
                                   motivo="sin fila en manifest_pixeles_horario.csv"))
    return filas


SCHEMA_REGISTRO_MAIAC = "airpollution.modelo-1km-v2.registro-catalogo-maiac.v1"
NOMBRE_REGISTRO_MAIAC = "registro_catalogo_maiac.json"          # en la raíz v2, insumos_red2/
DECISION_T5 = ("T5 (decisiones_autor_traduccion_20261025.md, 2026-10-26): las teselas del catálogo MAIAC sin registro "
               "por archivo se registran antes del armado con su sha256 y entran como los demás insumos; por el corte "
               "del 2026-10-24 entran sólo las teselas cuyo archivo es anterior al corte; las demás quedan fuera y se "
               "anotan")


def registro_catalogo_maiac(datos: Path, corte: str = CORTE_INSUMOS_UTC) -> dict:
    """T5: el registro de las teselas del catálogo MAIAC (``tile=*/pixeles.parquet``): ruta, bytes, fecha del archivo y
    sha256 (leer bytes, no valores). Entra la tesela cuyo archivo es anterior al corte; la otra queda fuera, anotada.
    La ``huella_teselas`` es la de la lista, sin la fecha en que se hizo el registro."""
    datos, c = Path(datos), utc(corte)
    teselas = []
    for q in sorted((datos / "contaminantes" / CATALOGO_MAIAC).glob("tile=*/pixeles.parquet")):
        fecha = _mtime_utc(q)
        h = hashlib.sha256()
        with open(q, "rb") as f:
            for bloque in iter(lambda: f.read(1 << 22), b""):
                h.update(bloque)
        entra = bool(fecha < c)
        teselas.append({"tesela": q.parent.name.split("=", 1)[1], "ruta": str(q.relative_to(datos)),
                        "bytes": int(q.stat().st_size), "fecha_archivo_utc": fecha.isoformat(), "sha256": h.hexdigest(),
                        "entra": entra, "motivo": "" if entra else "archivo posterior al corte (T5)"})
    huella = hashlib.sha256(json.dumps(teselas, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {"schema": SCHEMA_REGISTRO_MAIAC, "regla": DECISION_T5, "corte_utc": corte, "raiz": "AIR_POLLUTION_DATA_ROOT",
            "catalogo": f"contaminantes/{CATALOGO_MAIAC}", "teselas": teselas, "huella_teselas": huella,
            "entran": sum(t["entra"] for t in teselas), "fuera": sum(not t["entra"] for t in teselas)}


def registrar_catalogo_maiac(r: rv.RutasV2, datos: Path | None = None, corte: str = CORTE_INSUMOS_UTC, cfg=None,
                             estado=None) -> tuple[dict, str, str]:
    """Publica el registro de T5 en ``<raíz v2>/insumos_red2/registro_catalogo_maiac.json`` (después de exigir la
    traducción confirmada en git, R22). Se fija una vez: con la misma ``huella_teselas`` no se toca; con otra, se
    detiene (las teselas cambiaron después de registrarlas). Lleva su procedencia (``traza``, que no se compara).
    Devuelve (registro, sha256 del archivo, estado)."""
    compuerta = ra.exigir_traduccion_confirmada(r, cfg, estado)
    nuevo = registro_catalogo_maiac(datos if datos is not None else r.datos, corte)
    destino = r.raiz_v2 / "insumos_red2" / NOMBRE_REGISTRO_MAIAC
    with rv.candado_artefactos([destino], r):
        previo = rv.leer_json(destino)
        if previo is not None:
            if previo.get("huella_teselas") != nuevo["huella_teselas"]:
                raise SystemExit(f"{destino.name} ya existe con otra huella de teselas: el catálogo MAIAC cambió "
                                 f"después de registrarlo")
            return previo, sha256_de(destino), "sin_cambios"
        nuevo["registrado_utc"] = rv.ahora_utc()
        nuevo["traza"] = ra.traza_red2(r, compuerta, programa="panel_red2_v2 --registrar-catalogo-maiac")
        sha = rv.publicar_json(nuevo, destino, r)
    return nuevo, sha, "registrado"


def leer_registro_maiac(r: rv.RutasV2) -> tuple[dict | None, str | None]:
    """El registro de T5 y su sha256, o (None, None) si todavía no se hizo."""
    ruta = r.raiz_v2 / "insumos_red2" / NOMBRE_REGISTRO_MAIAC
    if not ruta.exists():
        return None, None
    reg = rv.leer_json(ruta)
    huella = hashlib.sha256(json.dumps(reg.get("teselas", []), sort_keys=True, ensure_ascii=False)
                            .encode("utf-8")).hexdigest()
    if reg.get("schema") != SCHEMA_REGISTRO_MAIAC or huella != reg.get("huella_teselas"):
        raise SystemExit(f"{ruta.name} no calza con su propia huella de teselas: se editó a mano")
    if reg.get("corte_utc") != CORTE_INSUMOS_UTC:
        raise SystemExit(f"{ruta.name} se hizo con otro corte ({reg.get('corte_utc')}), no con {CORTE_INSUMOS_UTC}")
    return reg, sha256_de(ruta)


def inventario_catalogos(datos: Path, corte: pd.Timestamp, registro_maiac: dict | None = None) -> list[dict]:
    """Catálogos de píxeles (los usa el enlace de las estaciones nuevas): la huella que declaran los manifiestos
    mensuales de su producto, que deben coincidir entre sí; se registró con el primero de esos manifiestos. Las
    teselas del catálogo MAIAC entran por su registro de T5 (``registro_catalogo_maiac``), con su sha256 y si su archivo
    es anterior al corte; sin registro, quedan fuera."""
    datos = Path(datos)
    cont = datos / "contaminantes"
    filas = []
    for prod, (carpeta, _) in PRODUCTOS_MENSUALES.items():
        rel = f"contaminantes/{carpeta}/catalogo_pixeles.parquet"
        p = datos / rel
        if not p.exists():
            continue
        shas, primero = set(), None
        for man in sorted((cont / carpeta / "manifiestos").glob("*.json")):
            d = json.loads(man.read_text(encoding="utf-8"))
            c = d.get("catalogo") or {}
            if c.get("sha256") and Path(str(c.get("archivo", ""))).name == p.name:
                shas.add(c["sha256"])
                t = utc(d["publicado_utc"])
                primero = t if primero is None or t < primero else primero
        if len(shas) != 1:
            filas.append(_fila("catalogo", prod, rel, p.stat().st_size, None, None, "manifiestos mensuales", corte,
                               motivo=f"los manifiestos declaran {len(shas)} huellas de catálogo"))
            continue
        filas.append(_fila("catalogo", prod, rel, p.stat().st_size, shas.pop(), primero,
                           "huella declarada por los manifiestos mensuales", corte))
    registradas = {t["ruta"]: t for t in (registro_maiac or {}).get("teselas", [])}
    en_disco = set()
    for q in sorted((datos / "contaminantes" / CATALOGO_MAIAC).glob("tile=*/pixeles.parquet")):
        rel = str(q.relative_to(datos))
        en_disco.add(rel)
        t = registradas.get(rel)
        if t is None:
            filas.append(_fila("catalogo", "maiac/" + q.parent.name, rel, q.stat().st_size, None, None, "sin registro",
                               corte, motivo="tesela MAIAC sin registro de T5 (registrar_catalogo_maiac)"))
            continue
        filas.append(_fila("catalogo", "maiac/" + q.parent.name, rel, t["bytes"], t["sha256"],
                           utc(t["fecha_archivo_utc"]), "registro_catalogo_maiac (T5): fecha del archivo", corte,
                           motivo=t.get("motivo", "")))
    for rel in sorted(set(registradas) - en_disco):
        t = registradas[rel]
        filas.append(_fila("catalogo", "maiac/tile=" + t["tesela"], rel, t["bytes"], t["sha256"], None,
                           "registro_catalogo_maiac (T5)", corte, motivo="tesela registrada que ya no está en el disco"))
    return filas


def inventario_insumos(datos, corte: str = CORTE_INSUMOS_UTC, local: Path | None = None,
                       copias: dict | None = None, registro_maiac: dict | None = None,
                       tropomi_mtime_anios: tuple[int, int] | None = TROPOMI_MTIME_ANIOS) -> pd.DataFrame:
    """Inventario R11 de todos los productos que leen los paneles: qué archivo entra, de dónde y con qué huella."""
    datos = Path(datos)
    cont = datos / "contaminantes"
    c = utc(corte)
    filas: list[dict] = []
    for prod in PRODUCTOS_MENSUALES:
        filas += inventario_mensual(cont, prod, c, local, copias)
    filas += inventario_geoscf(cont, c)
    filas += inventario_por_eventos(cont, "tropomi_no2", "S5P_TROPOMI/NO2/raw_chile", "S5P_TROPOMI/NO2/_manifiestos",
                                    "*.nc", c, permitir_mtime=True, anios_mtime=tropomi_mtime_anios)
    filas += inventario_por_eventos(cont, "acag", "ACAG_V6GL03/raw_chile", "ACAG_V6GL03/_manifiestos", "*.nc", c,
                                    permitir_mtime=False)
    filas += inventario_maiac(datos, c)
    filas += inventario_catalogos(datos, c, registro_maiac)
    return pd.DataFrame(filas, columns=COLUMNAS_INVENTARIO)


def anio_de_clave(producto: str, clave: str) -> int | None:
    """Año de adquisición de un archivo del inventario: el de la órbita TROPOMI o el de la clave «AAAAMM»."""
    if producto == "tropomi_no2":
        return anio_de_orbita(str(clave))
    m = re.match(r"^(\d{4})", str(clave))
    return int(m.group(1)) if m else None


def por_fecha_de_modificacion(inv: pd.DataFrame) -> dict:
    """T1(4) y T11: lo que entra por su fecha de modificación (sin registro propio), por producto y por año de
    adquisición, con la huella de la lista de archivos (lo que lista el anexo)."""
    out = {}
    m = inv[inv["entra"] & inv["fuente_registro"].astype(str).str.startswith("mtime")]
    for prod, g in m.groupby("producto", sort=True):
        anios = g["clave"].map(lambda c: anio_de_clave(prod, c))
        por_anio = {str(int(a)): int(n) for a, n in anios.value_counts(dropna=True).sort_index().items()}
        nombres = sorted(str(x) for x in g["ruta"])
        out[prod] = {"entran": int(len(g)), "por_anio": por_anio,
                     "huella_lista": hashlib.sha256(json.dumps(nombres).encode("utf-8")).hexdigest()}
    return out


def resumen_inventario(inv: pd.DataFrame) -> dict:
    out = {}
    mtime = por_fecha_de_modificacion(inv)
    for prod, g in inv.groupby("producto", sort=True):
        e = g[g["entra"]]
        out[prod] = {"archivos": int(len(g)), "entran": int(len(e)), "fuera": int(len(g) - len(e)),
                     "bytes_que_entran": int(pd.to_numeric(e["bytes"], errors="coerce").fillna(0).sum()),
                     "primera_clave": None if e.empty else str(e["clave"].min()),
                     "ultima_clave": None if e.empty else str(e["clave"].max()),
                     "motivos_fuera": g.loc[~g["entra"], "motivo"].value_counts().to_dict(),
                     "fuentes_registro": g["fuente_registro"].value_counts().to_dict(),
                     "origenes": e["origen"].map(lambda x: x.split(":", 1)[0]).value_counts().to_dict()}
        if prod in mtime:
            out[prod]["por_fecha_de_modificacion"] = mtime[prod]
    return out


class EscrituraFuera(rv.EscrituraNoPermitida):
    """Una ruta del inventario saldría de la carpeta congelada."""


def copiar_con_huella(origen: Path, destino: Path, bloque: int = 8 << 20) -> tuple[str, int]:
    """Copia ``origen`` en ``destino`` calculando el sha256 de lo leído; falla si el origen cambió durante la copia."""
    antes = os.stat(origen)
    h = hashlib.sha256()
    n = 0
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(origen, "rb") as fi, open(destino, "xb") as fo:
        for b in iter(lambda: fi.read(bloque), b""):
            h.update(b)
            fo.write(b)
            n += len(b)
        fo.flush()
        os.fsync(fo.fileno())
    despues = os.stat(origen)
    if (antes.st_size, antes.st_mtime_ns) != (despues.st_size, despues.st_mtime_ns) or n != antes.st_size:
        raise SystemExit(f"{origen.name} cambió mientras se copiaba")
    return h.hexdigest(), n


def huella_calza(fila, sha: str) -> bool:
    if fila["verificacion"] == HUELLA_REGISTRAR:
        return True
    declarada = str(fila["sha256_declarado"] or "")
    if fila["verificacion"] == HUELLA_PARTE:
        return sha in declarada.split("+")
    return sha == declarada


def congelar_insumos(inv: pd.DataFrame, datos: Path, destino: Path, r: rv.RutasV2, local: Path | None = None,
                     copias: dict | None = None) -> dict:
    """Copia a ``destino`` (en la raíz v2) cada archivo que entra, calculando su sha256, y se detiene si alguno no calza
    con su huella declarada. Si un mensual cambió en el disco de datos y hay copia de corte con la huella declarada
    (T3), se usa la copia. Se arma en una carpeta temporal y se publica de una vez; los archivos quedan de sólo
    lectura. Devuelve el registro (ruta, origen, sha256 y bytes de cada archivo) con su propia huella."""
    destino = Path(destino)
    rv.verificar_escritura(destino / "x", r)
    if destino.exists():
        raise SystemExit(f"{destino} ya existe: los insumos de hoy se congelan una sola vez (para retomar un armado "
                         f"cortado, congelar_o_retomar)")
    local = raiz_local() if local is None else Path(local)
    copias = COPIAS_DE_CORTE if copias is None else copias
    parcial = destino.with_name(destino.name + ".parcial")
    rv.verificar_escritura(parcial / "x", r)
    registro, errores = [], []
    with rv.candado_escritura("insumos_red2", r):
        if parcial.exists():
            shutil.rmtree(parcial)
        base = parcial.resolve()
        try:
            for fila in inv[inv["entra"]].to_dict("records"):
                rel = fila["ruta"]
                final = parcial / rel
                if ".." in Path(rel).parts or not final.resolve().is_relative_to(base):
                    raise EscrituraFuera(f"{rel} saldría de la carpeta congelada")
                fuente = (local / fila["origen"].split(":", 1)[1] if fila["origen"].startswith("copia_de_corte:")
                          else Path(datos) / rel)
                sha, n = copiar_con_huella(fuente, final)
                origen = fila["origen"]
                if not huella_calza(fila, sha) and rel in copias and not origen.startswith("copia_de_corte:"):
                    c = copias[rel]
                    if c["sha256"] == fila["sha256_declarado"]:      # el disco cambió; la copia es la de antes del corte
                        final.unlink()
                        sha, n = copiar_con_huella(local / c["copia"], final)
                        origen = f"copia_de_corte:{c['copia']}"
                if not huella_calza(fila, sha):
                    errores.append({"ruta": rel, "declarada": fila["sha256_declarado"], "calculada": sha})
                    final.unlink()
                    continue
                os.chmod(final, 0o444)
                registro.append({"ruta": rel, "origen": origen, "sha256": sha, "bytes": n,
                                 "verificacion": fila["verificacion"]})
            if errores:
                raise SystemExit(f"{len(errores)} insumos no calzan con su huella declarada: {errores[:5]}")
            os.replace(parcial, destino)
        except BaseException:
            if parcial.exists():
                for q in parcial.rglob("*"):
                    if q.is_file():
                        os.chmod(q, 0o644)
                shutil.rmtree(parcial)
            raise
    return {"archivos": len(registro), "bytes": int(sum(x["bytes"] for x in registro)), "registro": registro,
            "huella_del_registro": huella_de_registro(registro), "carpeta": r.relativa(destino)}


def huella_de_registro(registro: list[dict]) -> str:
    """La ``huella_del_registro`` de ``congelar_insumos``: sha256 de la lista (ruta, origen, sha256, bytes y
    verificación de cada archivo), en json con claves ordenadas."""
    return hashlib.sha256(json.dumps(registro, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def retomar_congelados(inv: pd.DataFrame, destino: Path, ruta_registro: Path, r: rv.RutasV2) -> dict:
    """Cuarta revisión, menor 33: si el armado se cortó después de congelar los insumos, la copia se reusa en lugar de
    volver a copiar ≈ 232 GB, pero sólo si sigue siendo la del inventario de ahora: ``congelados.json`` calza con su
    propia huella y con la carpeta; los archivos registrados son exactamente los que entran en el inventario, con la
    misma verificación y una huella que calza con la declarada; y cada archivo de la copia (sólo lectura, sin archivos
    de más) tiene el sha256 registrado, que se vuelve a calcular leyendo bytes. Si algo no calza, se detiene. Devuelve
    el registro de ``congelados.json``."""
    destino = Path(destino)
    reg = rv.leer_json(ruta_registro)
    if not isinstance(reg, dict) or huella_de_registro(reg.get("registro") or []) != reg.get("huella_del_registro"):
        raise SystemExit(f"{Path(ruta_registro).name} no calza con su propia huella: no se retoma la copia congelada")
    if reg.get("carpeta") != r.relativa(destino) or not destino.is_dir():
        raise SystemExit(f"{Path(ruta_registro).name} no describe la copia de {r.relativa(destino)['ruta']}")
    entra = {f["ruta"]: f for f in inv[inv["entra"]].to_dict("records")}
    registro = {x["ruta"]: x for x in reg["registro"]}
    if set(entra) != set(registro):
        faltan, sobran = sorted(set(entra) - set(registro)), sorted(set(registro) - set(entra))
        raise SystemExit(f"el inventario de ahora no es el de la copia congelada: faltan {len(faltan)} {faltan[:3]}; "
                         f"sobran {len(sobran)} {sobran[:3]}; no se retoma (se congelan una sola vez)")
    malos = [rel for rel, f in entra.items() if registro[rel].get("verificacion") != f["verificacion"]
             or not huella_calza(f, registro[rel].get("sha256"))]
    if malos:
        raise SystemExit(f"{len(malos)} archivos de la copia congelada no calzan con la huella del inventario de ahora: "
                         f"{malos[:3]}")
    en_disco = {str(q.relative_to(destino)) for q in destino.rglob("*") if q.is_file() or q.is_symlink()}
    if en_disco != set(registro):
        raise SystemExit(f"la copia congelada tiene archivos de más o de menos ({len(en_disco)} frente a "
                         f"{len(registro)} registrados): no se retoma")
    for rel, x in sorted(registro.items()):
        q = destino / rel
        if q.is_symlink() or os.access(q, os.W_OK) or uv.sha256_archivo(q) != x["sha256"]:
            raise SystemExit(f"{rel}: la copia congelada cambió (sha256, enlace o permiso de escritura): no se retoma")
    return reg


def congelar_o_retomar(inv: pd.DataFrame, r: rv.RutasV2, raiz_ins: Path, datos: Path | None = None,
                       local: Path | None = None, copias: dict | None = None,
                       compuerta: dict | None = None) -> tuple[dict, str, str]:
    """El paso de la copia congelada del armado: si no hay ni copia ni ``congelados.json``, congela y publica el
    registro, con su procedencia (``traza``; ``compuerta``, lo que devolvió ``exigir_traduccion_confirmada``); si están
    los dos, retoma (``retomar_congelados``, que compara la huella del registro, no la traza); si hay copia sin
    registro, el armado se cortó entre la copia y su registro y se detiene. ``datos``, ``local`` y ``copias``, como en
    ``congelar_insumos`` (por omisión, los del armado). Devuelve (registro, sha256 de congelados.json, «congelado» o
    «retomado»)."""
    destino, ruta = Path(raiz_ins) / "congelados" / "data", Path(raiz_ins) / "congelados.json"
    if ruta.exists():
        return retomar_congelados(inv, destino, ruta, r), sha256_de(ruta), "retomado"
    if destino.exists():
        raise SystemExit(f"{r.relativa(destino)['ruta']} existe sin congelados.json: el armado se cortó entre la copia y su "
                         f"registro; revisa a mano (la copia es de sólo lectura) antes de seguir")
    congelado = congelar_insumos(inv, r.datos if datos is None else datos, destino, r, local=local, copias=copias)
    inventario = Path(raiz_ins) / "inventario.json"
    congelado["traza"] = ra.traza_red2(r, compuerta, {"inventario": inventario} if inventario.exists() else {},
                                       programa="panel_red2_v2 --ejecutar")
    with rv.candado_artefactos([ruta], r):
        sha = rv.publicar_json(congelado, ruta, r)
    return congelado, sha, "congelado"


def _valor_json(v):
    """Un valor de una fila del inventario en json estable: sin NaN y con ``bytes`` entero aunque la columna haya
    quedado en coma flotante por una fila sin tamaño (así una fila nueva que no entra no cambia la huella de las que
    entran)."""
    if isinstance(v, (float, np.floating)):
        return None if not np.isfinite(v) else (int(v) if float(v).is_integer() else float(v))
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.bool_):
        return bool(v)
    return v


def _fila_json(fila: dict) -> dict:
    return {k: _valor_json(v) for k, v in fila.items()}


def huella_de_lo_que_entra(inv: pd.DataFrame) -> str:
    """sha256 de las filas del inventario que entran (todas sus columnas), ordenadas por producto y ruta: es lo que fija
    la escritura única de ``inventario.json`` (quinta revisión, menor 21)."""
    e = inv[inv["entra"].astype(bool)].sort_values(["producto", "ruta"], kind="stable")
    filas = [_fila_json(f) for f in e[COLUMNAS_INVENTARIO].to_dict("records")]
    return hashlib.sha256(json.dumps(filas, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def publicar_inventario(inv: pd.DataFrame, r: rv.RutasV2, raiz_ins: Path, compuerta: dict | None = None
                        ) -> tuple[str, str]:
    """``insumos_red2/inventario.json``, de escritura única. Trae todas las filas (también las que no entran) y su
    procedencia (``traza``). Si ya existe (un armado anterior se cortó), se compara sólo lo que entra
    (``huella_de_lo_que_entra``): un archivo nuevo que no entra (registrado después del corte o sin manifiesto) no
    detiene el armado retomado y queda fuera, como queda fuera de la copia congelada (``retomar_congelados``); si lo que
    entra cambió, se detiene. Devuelve (sha256, «escrito» o «sin_cambios»)."""
    ruta = Path(raiz_ins) / "inventario.json"
    huella = huella_de_lo_que_entra(inv)
    with rv.candado_artefactos([ruta], r):
        if ruta.exists():
            previo = rv.leer_json(ruta) or {}
            if previo.get("schema") != SCHEMA_INVENTARIO or previo.get("huella_de_lo_que_entra") != huella:
                raise SystemExit("insumos_red2/inventario.json ya existe con otro inventario (lo que entra es otro): los "
                                 "insumos de hoy se fijan una sola vez")
            return sha256_de(ruta), "sin_cambios"
        texto = rv.texto_json({"schema": SCHEMA_INVENTARIO, "corte_utc": CORTE_INSUMOS_UTC,
                               "resumen": resumen_inventario(inv), "huella_de_lo_que_entra": huella,
                               "archivos": [_fila_json(f) for f in inv.to_dict("records")],
                               "traza": ra.traza_red2(r, compuerta, programa="panel_red2_v2 --ejecutar")})
        return rv.publicar_texto(texto, ruta, r), "escrito"


# ---------------------------------------------------------------------------
# Observaciones de la red 2 (R3-R10)
# ---------------------------------------------------------------------------
def procesar_serie_sinca(df: pd.DataFrame, estacion: str, pol: str, factor: float, veredictos_anio: dict,
                         zona: str, version: str, convencion: str | None = None) -> pd.DataFrame:
    """Una serie del derivado → filas (estación, hora UTC) en la unidad del modelo, con su bandera y su reloj.

    ``df``: columnas ``ts_local``, ``obs``, ``qc_observacion`` y ``seleccionada`` del derivado. El rango de R5 se
    aplica después de convertir."""
    if not np.isfinite(factor):
        raise ValueError(f"{estacion} {pol}: serie sin unidad que entra; no debió llegar aquí")
    d = df[df["seleccionada"].astype(bool) & df["obs"].notna() & df["ts_local"].notna()]
    valores = d["obs"].to_numpy("float64") * float(factor)
    lo, hi = RANGO[pol]
    ok = np.isfinite(valores) & (valores >= lo) & (valores <= hi)
    d, valores = d[ok], valores[ok]
    reloj = rs.convertir(d["ts_local"].to_numpy(), veredictos_anio, zona, convencion)
    qc = d["qc_observacion"].map(cv.CODIGO_QC)
    if qc.isna().any():
        raise ValueError(f"{estacion} {pol}: qc_observacion fuera de {cv.QC_SINCA}: {sorted(d.loc[qc.isna(), 'qc_observacion'].unique())}")
    return pd.DataFrame({"estacion": estacion, "ts_utc": reloj["ts_utc"].to_numpy("datetime64[ns]"),
                         "obs": valores, "qc": qc.to_numpy("int8"), "reloj": reloj["reloj"].to_numpy(),
                         "qc_hora": reloj["qc_hora"].to_numpy(), "ts_local": d["ts_local"].to_numpy("datetime64[ns]"),
                         "ts_utc_alternativo": reloj["ts_utc_alternativo"].to_numpy("datetime64[ns]"),
                         "version": version})


def agregar_hora(filas: pd.DataFrame) -> pd.DataFrame:
    """Media por estación × hora UTC (``calidad_v2.agregar_por_hora``: ``obs`` media, ``n``, ``qc`` la peor), con la
    bandera de colisión de R7: dos etiquetas distintas en la misma hora UTC."""
    agg = cv.agregar_por_hora(filas[["estacion", "ts_utc", "obs", "qc"]], por=("estacion", "ts_utc"))
    etiquetas = filas.groupby(["estacion", "ts_utc"], sort=True)["ts_local"].nunique().rename("etiquetas")
    version = filas.groupby(["estacion", "ts_utc"], sort=True)["version"].first()
    agg = agg.merge(etiquetas.reset_index(), on=["estacion", "ts_utc"], how="left")
    agg = agg.merge(version.reset_index(), on=["estacion", "ts_utc"], how="left")
    agg["colision_utc"] = agg["etiquetas"] > 1
    return agg.drop(columns=["etiquetas"])


def series_snifa_red2(ruta: Path, pol: str, factores: dict | None = None) -> pd.DataFrame:
    """Horas SNIFA de ``pol`` como ``calidad_v2.reconstruir_snifa`` (réplica de ``_red_adicional.py:96-121``), con el
    factor de R6 (El Peñón a 25 °C). Columnas: estacion, ts_utc, obs, n, qc, mixta, version, colision_utc."""
    cols = ["estacion", "ts_utc", "obs", "n", "qc", "mixta", "version", "colision_utc"]
    if pol != "no2":
        return pd.DataFrame(columns=cols)
    factores = uv.factores_snifa() if factores is None else factores
    o = pd.read_parquet(ruta, columns=cv.COLUMNAS_SNIFA)
    o = o[o["station_id"].isin(list(uv.SNIFA_ESTACIONES)) & o["numeric_usable"].astype(bool)]
    o = o[(o["pollutant"] == pol) & o["unit"].isin(cv.UNIDADES_SNIFA)].copy()
    factor = o["station_id"].map(factores).to_numpy("float64")
    o["obs"] = np.where(o["unit"].to_numpy() == "ug/m3N", o["value"].to_numpy() * factor, o["value"].to_numpy())
    lo, hi = RANGO[pol]
    o = o[o["obs"].between(lo, hi)]
    hora = cv.hora_local_snifa(o["document_id"].to_numpy(), o["hour_index"].to_numpy())
    ts = pd.to_datetime(o["date_local"]) + pd.to_timedelta(hora + OFFSET_UTC_H, unit="h")
    nativo = o["usable_native"].astype("boolean").fillna(False).to_numpy(dtype=bool)
    filas = pd.DataFrame({"estacion": o["station_id"].map(uv.SNIFA_ESTACIONES).to_numpy(),
                          "ts_utc": ts.astype("datetime64[ns]").to_numpy(), "obs": o["obs"].to_numpy("float64"),
                          "qc": np.where(nativo, cv.CODIGO_QC["usable_native"],
                                         cv.CODIGO_QC["solo_numeric_usable"]).astype("int8")})
    s = cv.agregar_por_hora(filas, por=("estacion", "ts_utc"))
    s["version"] = RED_SNIFA
    s["colision_utc"] = False
    return s[cols]


def rachas_sin_produccion(obs: pd.DataFrame, minimo: int) -> pd.DataFrame:
    """La regla de ``produccion.marcar_rachas`` (corridas de ``minimo`` o más valores idénticos consecutivos de la misma
    estación; los huecos no cortan) con ``calidad_v2.marcar_rachas``, para las pruebas sin disco, que no importan
    ``produccion.py``. Misma firma: recibe las horas como tabla y devuelve una copia con ``racha``."""
    o = obs.copy()
    o["racha"] = cv.marcar_rachas(o["estacion"].to_numpy(), o["ts_utc"].to_numpy(), o["obs"].to_numpy(), minimo)
    return o


def observaciones_red2(series: list[pd.DataFrame], snifa: pd.DataFrame, con_celda: pd.DataFrame,
                       desde: str = DESDE, hasta: str = HASTA, racha: int = QC_RACHA,
                       marcar_rachas=None) -> tuple[pd.DataFrame, dict]:
    """Observaciones del panel de un contaminante: agregación por hora, rachas sobre el registro completo, período
    por día local UTC−4 y estaciones con celda (réplica de ``produccion.observaciones`` y de
    ``observaciones_panel``, ``qmd:2004-2010``), y luego una copia por hora en los duplicados (R9).

    T12 (corrección, [delegada]): en el armado, las rachas las marca ``produccion.marcar_rachas`` (``marcar_rachas``,
    de ``importar_produccion``: ``produccion.py`` con su huella comprobada, importado después de ``importar_v1``), la
    regla de ``produccion.observaciones``. La función ``produccion.observaciones`` misma no se puede usar: lee el
    derivado y el catálogo de la v1 (``series_sinca`` y ``estaciones_usables``) y no admite las series de la red 2, así
    que lo demás de su regla (las estaciones usables) se replica aquí (estaciones con celda).
    ``test_panel_red2_v2.ObservacionesTests.test_misma_regla_que_produccion_observaciones`` ejecuta ``marcar_rachas``
    y ``observaciones`` de ``produccion.py``, extraídas por AST, sobre las mismas horas: quedan las mismas horas que
    aquí, con ``marcar_rachas`` y sin él (sin él, las pruebas sin disco usan ``rachas_sin_produccion``)."""
    cols = ["estacion", "ts_utc", "obs", "n", "qc", "mixta", "version", "colision_utc"]
    partes = [agregar_hora(s) for s in series if len(s)]
    if len(snifa):
        partes.append(snifa[cols])
    o = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=cols)
    o["ts_utc"] = pd.to_datetime(o["ts_utc"])
    o = (marcar_rachas or rachas_sin_produccion)(o, racha).reset_index(drop=True)     # T12: produccion.marcar_rachas
    local = o["ts_utc"] - pd.Timedelta(hours=OFFSET_UTC_H)
    t0, t1 = pd.Timestamp(desde), pd.Timestamp(hasta) + pd.Timedelta(days=1)
    con = set(con_celda.loc[con_celda["celda"] >= 0, "estacion"].astype(str))
    en_periodo = (local >= t0) & (local < t1)
    info = {"horas_totales": int(len(o)), "horas_en_racha": int(o["racha"].sum()),
            "estaciones_con_racha": int(o.loc[o["racha"], "estacion"].nunique()),
            "racha_en_cero_pct": round(100 * float((o.loc[o["racha"], "obs"] == 0).mean()), 1) if o["racha"].any() else 0.0,
            "fuera_del_periodo": int((~en_periodo).sum()), "sin_celda": sorted(set(o["estacion"]) - con),
            "colisiones_utc": int(o["colision_utc"].sum())}
    o = o[~o["racha"] & en_periodo & o["estacion"].isin(con)].drop(columns=["racha"])
    coords = con_celda[["estacion", "lat", "lon"]]
    pares = dv.pares_duplicados(o[["estacion", "ts_utc", "obs"]], coords)
    sin_copias, registro = dv.quitar_copias(o, pares)
    info.update({"pares_cercanos_evaluados": int(len(pares)), "pares_duplicados": int(pares["duplicado"].sum()),
                 "duplicados": registro, "horas_quitadas_por_copias": int(len(o) - len(sin_copias)),
                 "filas": int(len(sin_copias)), "estaciones": int(sin_copias["estacion"].nunique())})
    sin_copias = sin_copias.sort_values(["estacion", "ts_utc"], kind="stable").reset_index(drop=True)
    return sin_copias, info


# ---------------------------------------------------------------------------
# Regímenes de predictores (R17)
# ---------------------------------------------------------------------------
def regimenes_calculados(fecha_local, anio, columnas: dict, familias: dict,
                         indicadoras=("acag_climatologico",), umbral: float = 0.5) -> dict:
    """R17: una familia está disponible en un año si alguna de sus columnas es finita (indicadoras: vale 1) en al
    menos la mitad de los días del año en el panel; los regímenes son los tramos de años seguidos con la misma
    combinación de familias disponibles."""
    dia = pd.to_datetime(pd.Series(fecha_local)).dt.normalize().to_numpy()
    a = np.asarray(anio, dtype="int64")
    base = pd.DataFrame({"dia": dia, "anio": a})
    dias_anio = base.groupby("anio")["dia"].nunique()
    disponibles: dict[int, list[str]] = {int(y): [] for y in dias_anio.index}
    fracciones: dict[str, dict[int, float]] = {}
    for fam, cols in familias.items():
        mejor = pd.Series(0.0, index=dias_anio.index)
        for c in cols:
            if c not in columnas:
                continue
            v = np.asarray(columnas[c], dtype="float64")
            ok = (v == 1.0) if fam in indicadoras else np.isfinite(v)
            dias_ok = base[ok].groupby("anio")["dia"].nunique().reindex(dias_anio.index, fill_value=0)
            mejor = np.maximum(mejor, dias_ok / dias_anio)
        fracciones[fam] = {int(y): round(float(x), 4) for y, x in mejor.items()}
        for y, x in mejor.items():
            if x >= umbral:
                disponibles[int(y)].append(fam)
    tramos = []
    for y in sorted(disponibles):
        combo = "+".join(disponibles[y]) or "ninguna"
        if tramos and tramos[-1]["familias"] == combo and tramos[-1]["anios"][1] == y - 1:
            tramos[-1]["anios"][1] = y
        else:
            tramos.append({"anios": [y, y], "familias": combo})
    for t in tramos:
        t["id"] = f"{t['anios'][0]}" if t["anios"][0] == t["anios"][1] else f"{t['anios'][0]}-{t['anios'][1]}"
    return {"regla": "familia disponible en un año si alguna columna es finita (indicadora: = 1) en ≥ 50 % de los "
                     "días del año en el panel; tramos de años seguidos con la misma combinación (R17)",
            "tramos": tramos, "fraccion_de_dias": fracciones}


# ---------------------------------------------------------------------------
# Código v1 con huella y entorno de lectura
# ---------------------------------------------------------------------------
def huellas_del_repositorio(raiz: Path = REPO, huellas: dict | None = None) -> dict[str, str]:
    """{ruta: sha256} que rige en el repositorio ``raiz``: la huella común o, en un archivo «adaptado» (la huella por
    repositorio), la del repositorio por su nombre (``Air-Pollution`` o ``Air-Pollution-Health-Chile``). Un archivo
    adaptado sin huella para ese repositorio detiene."""
    huellas = HUELLAS_CODIGO_V1 if huellas is None else huellas
    nombre = Path(raiz).resolve().name
    out = {}
    for rel, h in huellas.items():
        if isinstance(h, dict):
            if nombre not in h:
                raise SystemExit(f"{rel} tiene una huella por repositorio ({sorted(h)}) y {nombre} no es ninguno de ellos")
            h = h[nombre]
        out[rel] = h
    return out


def verificar_codigo_v1(raiz: Path = REPO, huellas: dict | None = None) -> dict:
    """Comprueba la huella del código v1 que replica o importa el panel y de sus dependencias del pipeline, con la de
    ese repositorio en los archivos adaptados (``huellas_del_repositorio``). Devuelve las huellas comprobadas."""
    esperadas = huellas_del_repositorio(raiz, huellas)
    distintos = {n: uv.sha256_archivo(Path(raiz) / n) for n in esperadas
                 if not (Path(raiz) / n).is_file() or uv.sha256_archivo(Path(raiz) / n) != esperadas[n]}
    if distintos:
        raise SystemExit(f"El código v1 que replica el panel cambió: {sorted(distintos)}; el bloque fija sus huellas")
    return dict(esperadas)


def entorno_lectura(vista_datos: Path, raiz_v1: Path) -> dict[str, str]:
    """Variables con que los lectores de la v1 leen los insumos congelados y la grilla v1, sin interpolar y con la
    convención SINCA de la v1. Se fijan antes de importar ``_comun_modelo`` (también en los procesos hijos)."""
    return {"AIR_POLLUTION_DATA_ROOT": str(vista_datos), "AIR_POLLUTION_MODELO_1KM_ROOT": str(raiz_v1),
            "MODELO_1KM_INTERPOLAR": "", "MODELO_1KM_ETIQUETA_SINCA": "fin", "MODELO_1KM_QC_RACHA": str(QC_RACHA),
            "MODELO_1KM_RED_ADICIONAL": "0"}


def importar_v1(entorno: dict[str, str]):
    """Importa ``_comun_modelo``, ``_features`` y ``construir_grilla`` con el entorno de lectura (huellas ya
    comprobadas). Devuelve los tres módulos."""
    os.environ.update(entorno)
    if str(V1) not in sys.path:
        sys.path.insert(0, str(V1))
    import _comun_modelo as cm
    import _features as ft
    import construir_grilla as cg
    if Path(cm.DATA).resolve() != Path(entorno["AIR_POLLUTION_DATA_ROOT"]).resolve():
        raise RuntimeError("_comun_modelo ya estaba importado con otra raíz de datos")
    return cm, ft, cg


def importar_produccion():
    """T12 (corrección, [delegada]): «el panel usa produccion.observaciones con su huella fijada». Importa
    ``produccion.py`` (su huella y la de ``_red_adicional.py``, que importa, ya comprobadas por ``verificar_codigo_v1``)
    después de ``importar_v1``: ``_comun_modelo`` y ``scripts_pipeline/_common.py`` ya están cargados con la raíz de la
    copia congelada, así que importarlo no agrega efectos (con ``MODELO_1KM_RED_ADICIONAL=0`` la red adicional queda
    fuera y ``_red_adicional`` sólo define constantes). Exige que sea el archivo de este repositorio, que no active la
    red adicional y que su ``QC_RACHA`` sea el del panel. El armado usa su ``marcar_rachas``, la regla de rachas de
    ``produccion.observaciones`` (ver ``observaciones_red2``). Devuelve el módulo."""
    if "_comun_modelo" not in sys.modules:
        raise RuntimeError("produccion.py se importa después de importar_v1 (con la raíz de datos de la copia congelada)")
    if str(V1) not in sys.path:
        sys.path.insert(0, str(V1))
    import produccion
    if Path(produccion.__file__).resolve() != (V1 / "produccion.py").resolve():
        raise RuntimeError(f"se importó otro produccion.py ({Path(produccion.__file__).name} fuera de scripts_modelo_1km)")
    if produccion.RED_ADICIONAL or int(produccion.QC_RACHA) != QC_RACHA:
        raise RuntimeError(f"produccion.py quedó con la red adicional ({produccion.RED_ADICIONAL}) o con otro QC_RACHA "
                           f"({produccion.QC_RACHA}, el panel usa {QC_RACHA})")
    return produccion


def tramos(desde: str, hasta: str, meses_por_tramo: int = 3) -> list[tuple[str, str]]:
    """Réplica de ``tramos`` del documento (``qmd:1483-1490`` de la copia de trabajo)."""
    cortes = pd.date_range(pd.Timestamp(desde).replace(day=1), pd.Timestamp(hasta), freq=f"{meses_por_tramo}MS")
    out = []
    for k, ini in enumerate(cortes):
        fin = (cortes[k + 1] - pd.Timedelta(days=1)) if k + 1 < len(cortes) else pd.Timestamp(hasta)
        out.append((max(ini, pd.Timestamp(desde)).date().isoformat(), min(fin, pd.Timestamp(hasta)).date().isoformat()))
    return out


def en_paralelo(funcion, tareas: list[tuple], procesos: int) -> list:
    """Réplica de ``en_paralelo`` del documento: ``funcion(*tarea)`` en ``procesos`` procesos (loky) o en serie."""
    if procesos <= 1 or len(tareas) <= 1:
        return [funcion(*t) for t in tareas]
    from joblib import Parallel, delayed
    return Parallel(n_jobs=min(procesos, len(tareas)), backend="loky")(delayed(funcion)(*t) for t in tareas)


def identidad_red(estaciones) -> str:
    """Réplica de ``identidad_red`` (``qmd:2077-2081``): huella del universo de estaciones con celda."""
    est = sorted(str(x) for x in estaciones)
    return hashlib.sha256(json.dumps(est).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Estaciones con celda de la red 2
# ---------------------------------------------------------------------------
def estaciones_con_celda_red2(maestro: pd.DataFrame, snifa: pd.DataFrame, enlaces: pd.DataFrame) -> pd.DataFrame:
    """Réplica de ``estaciones_con_celda`` (``qmd:1968-1970``) con los dos maestros de R8, SNIFA y los enlaces de las
    tres familias (v1 para las actuales y SNIFA; red 2 para las nuevas). Exige códigos únicos."""
    cols = ["estacion", "nombre", "region_sinca", "lat", "lon", "cod_comuna", "red"]
    est = pd.concat([maestro[cols + ["grupo"]], snifa[cols].assign(grupo="snifa")], ignore_index=True)
    if est["estacion"].duplicated().any():
        raise ValueError(f"códigos repetidos en la red 2: {est.loc[est['estacion'].duplicated(), 'estacion'].tolist()}")
    enl = enlaces[["estacion", "celda"]].drop_duplicates("estacion")
    est = est.merge(enl, on="estacion", how="inner")
    est = est[est["celda"] >= 0].reset_index(drop=True)
    est["celda"] = est["celda"].astype("int64")
    return est.sort_values("estacion", kind="stable").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Panel (réplica de construir_panel, qmd:2022-2075)
# ---------------------------------------------------------------------------
def matriz_vecindario(obs: pd.DataFrame, est: pd.DataFrame):
    """Réplica de ``matriz_vecindario`` (``qmd:2012-2020``)."""
    O = obs.pivot_table(index="ts_utc", columns="estacion", values="obs", aggfunc="mean")
    meta = est.set_index("estacion").loc[O.columns]
    return O, meta["lat"].to_numpy(float), meta["lon"].to_numpy(float)


def satelites_red2(ft, celdas_obj: pd.DataFrame, enlaces: pd.DataFrame, procesos: int,
                   desde: str = DESDE, hasta: str = HASTA) -> tuple[pd.DataFrame, dict]:
    """Réplica del cálculo de ``satelites_estaciones`` (``qmd:1972-2002``) para las celdas de la red 2."""
    enlaces_obj = enlaces[enlaces["celda"].isin(celdas_obj["celda"])].reset_index(drop=True)
    partes = en_paralelo(ft.satelites_tramo, [(a, b, celdas_obj, enlaces_obj) for a, b in tramos(desde, hasta)],
                         procesos)
    sat = pd.concat([p[0] for p in partes], ignore_index=True)
    sin_maiac = sorted({d for p in partes for d in p[1]})
    sin_no2 = sorted({d for p in partes for d in p[2]})
    meta = {"desde": desde, "hasta": hasta, "celdas": int(len(celdas_obj)), "dias": int(sat["fecha_local"].nunique()),
            "dias_sin_maiac": len(sin_maiac), "dias_sin_no2": len(sin_no2),
            "primer_dia_con_no2": (None if sat["no2_trop"].isna().all() else
                                   pd.Timestamp(sat.loc[sat["no2_trop"].notna(), "fecha_local"].min()).date().isoformat())}
    return sat, meta


def construir_panel_red2(pol: str, obs: pd.DataFrame, est: pd.DataFrame, sat: pd.DataFrame, ctx: dict,
                         procesos: int = 1) -> tuple[pd.DataFrame, dict]:
    """Réplica de ``construir_panel`` (``qmd:2022-2075``) sobre las observaciones de la red 2.

    ``ctx``: módulos ``ft`` (``_features``) y objetos de la grilla v1 (``CELDAS``, ``ENLACES``, ``ESTATICAS``,
    ``LULC``). ``obs`` trae ``estacion``, ``ts_utc``, ``obs``, ``n`` y ``version`` (las columnas del panel v1)."""
    ft = ctx["ft"]
    CELDAS, ENLACES = ctx["CELDAS"], ctx["ENLACES"]
    obs = obs[["estacion", "ts_utc", "obs", "n", "version"]].merge(
        est[["estacion", "celda", "lat", "lon", "region_sinca"]].rename(columns={"lat": "lat_est", "lon": "lon_est"}),
        on="estacion", how="inner")
    df = ft.calendario(obs)
    sat = sat.assign(fecha_local=pd.to_datetime(sat["fecha_local"]).astype(df["fecha_local"].dtype))
    df = df.merge(sat, on=["celda", "fecha_local"], how="left")
    enlaces_obj = ENLACES[ENLACES["celda"].isin(df["celda"].unique())].reset_index(drop=True)
    bloques = [(b.reset_index(drop=True), enlaces_obj) for _, b in df.groupby(df["ts_utc"].dt.year, sort=True)]
    partes = en_paralelo(ft.ensamblar_horario_tramo, bloques, procesos)
    df = pd.concat([p[0] for p in partes], ignore_index=True)
    faltantes = sorted({f"{prod}:{mes}" for p in partes for prod, mes in p[1]})
    acag = ft.AcagMensual(CELDAS)
    df["acag_pm25"], df["acag_clim"] = np.nan, 0
    pos = pd.Index(CELDAS["celda"]).get_indexer(df["celda"])
    for mes, idx in df.groupby(df["fecha_local"].dt.strftime("%Y%m")).indices.items():
        v, clim = acag.mes(mes)
        df.loc[df.index[idx], "acag_pm25"] = v[pos[idx]]
        df.loc[df.index[idx], "acag_clim"] = int(clim)
    df = ft.unir_estaticas(df, ctx["ESTATICAS"], ctx["LULC"])
    O, lat_e, lon_e = matriz_vecindario(obs, est)
    obs_vec, peso_vec = ft.obs_vecinas_para(O, lat_e, lon_e, df["ts_utc"].to_numpy(), df["lat_est"].to_numpy(),
                                            df["lon_est"].to_numpy(), excluir=df["estacion"].to_numpy())
    df["obs_vec"], df["peso_vec"] = obs_vec, peso_vec
    D = ft.haversine_km(lat_e[:, None], lon_e[:, None], lat_e[None, :], lon_e[None, :])
    np.fill_diagonal(D, np.inf)
    df["dist_est_km"] = df["estacion"].map(pd.Series(D.min(axis=1), index=O.columns)).astype("float32")
    for c in df.columns:
        if df[c].dtype == np.float64:
            df[c] = df[c].astype("float32")
    resumen = {"filas": int(len(df)), "estaciones": int(df["estacion"].nunique()), "meses_sin_fuente": faltantes,
               "cobertura": {c: round(float(df[c].notna().mean()), 3) for c in df.columns if df[c].dtype.kind == "f"},
               "columnas": list(df.columns)}
    return df, resumen


def calidad_alineada(panel: pd.DataFrame, obs: pd.DataFrame) -> pd.DataFrame:
    """Bandera ``qc`` de cada fila del panel, alineada 1 a 1 (esquema de ``calidad_v2``: estacion, ts_utc, qc,
    fuente). ``qc`` es el texto de ``calidad_v2.QC_TODOS``."""
    clave = obs[["estacion", "ts_utc", "qc", "version"]].copy()
    clave["fuente"] = np.where(clave["version"] == RED_SNIFA, RED_SNIFA, RED_SINCA)
    m = panel[["estacion", "ts_utc"]].merge(clave.drop(columns=["version"]), on=["estacion", "ts_utc"], how="left",
                                            validate="one_to_one")
    if m["qc"].isna().any():
        raise RuntimeError("hay filas del panel sin bandera de calidad")
    m["qc"] = np.asarray(cv.QC_TODOS, dtype=object)[m["qc"].to_numpy("int64")]
    return m


def predictores_cerrados(cfg: dict, pol: str) -> list[str]:
    """La lista cerrada del §3 (70 de PM2,5 y 69 de NO2), de ``motores.eje_A.predictores``."""
    v = cfg["motores"]["eje_A"]["predictores"][pol]
    return list(v.get("valor", v.get("lista", [])) if isinstance(v, dict) else v)


# ---------------------------------------------------------------------------
# Costo: muestra pequeña (no escribe)
# ---------------------------------------------------------------------------
def _fecha_manifiesto(texto: pd.Series) -> pd.Series:
    """Marcas de los manifiestos SINCA («AAMMDD HHMM», como el exportador) o ISO."""
    t = pd.to_datetime(texto, format="%y%m%d %H%M", errors="coerce")
    resto = t.isna() & texto.notna()
    if resto.any():
        t[resto] = pd.to_datetime(texto[resto], format="ISO8601", errors="coerce")
    return t


def filas_estimadas(series: pd.DataFrame, desde: str = DESDE, hasta: str = HASTA) -> dict:
    """Filas con observación por contaminante y origen, prorrateadas al período R4 (sólo conteos de manifiestos)."""
    t0, t1 = pd.Timestamp(desde), pd.Timestamp(hasta) + pd.Timedelta(days=1)
    s = series.copy()
    a, b = _fecha_manifiesto(s["primera_observacion"]), _fecha_manifiesto(s["ultima_observacion"])
    n = pd.to_numeric(s["filas_con_observacion"], errors="coerce").fillna(0)
    span = (b - a).dt.total_seconds().clip(lower=3600)
    dentro = (b.clip(upper=t1) - a.clip(lower=t0)).dt.total_seconds().clip(lower=0)
    s["filas_periodo"] = (n * (dentro / span).fillna(0)).round()
    return {pol: {o: int(v) for o, v in g.groupby("origen")["filas_periodo"].sum().items()}
            for pol, g in s.groupby("contaminante")}


def _muestra_claves(r: rv.RutasV2, pol: str, desde: str, hasta: str) -> pd.DataFrame:
    """Claves (estación, hora, celda, coordenadas, región) del panel v1 en una ventana, para medir: no se leen las
    observaciones; el valor se sustituye por uno sintético."""
    import pyarrow.dataset as ds

    cols = ["estacion", "ts_utc", "celda", "lat_est", "lon_est", "region_sinca"]
    t0, t1 = pd.Timestamp(desde), pd.Timestamp(hasta) + pd.Timedelta(days=1)
    tabla = ds.dataset(r.panel(pol)).to_table(columns=cols, filter=(ds.field("ts_utc") >= t0) & (ds.field("ts_utc") < t1))
    df = tabla.to_pandas()
    df["estacion"] = df["estacion"].astype(str)
    df["region_sinca"] = df["region_sinca"].astype(str)
    return df


def medir(r: rv.RutasV2, pol: str = "no2", mes: str = "2024-04", ventana_sin_tropomi: str = "2010-03-01",
          dias: int = 7) -> dict:
    """Costo del armado con una muestra pequeña, sin escribir nada: los satélites diarios de un mes con TROPOMI y de
    una semana sin TROPOMI, con **todas** las celdas de la red 2, y un mes del panel de ``pol`` (claves del panel v1
    y valores sintéticos) por ``construir_panel_red2``. Lee el disco de datos directamente (no la copia congelada)."""
    medidas = {"contaminante": pol, "mes": mes}
    t = time.perf_counter()
    huellas = verificar_codigo_v1()
    cm, ft, cg = importar_v1(entorno_lectura(r.datos, r.raiz_v1))
    CELDAS, ENLACES = cm.cargar_celdas(), cm.cargar_enlaces()
    ESTATICAS, LULC = ft.cargar_estaticas()
    medidas["carga_grilla_s"] = round(time.perf_counter() - t, 1)
    maestro = ra.maestro_red2(r.datos)
    celdas_m = cm.celda_de_lonlat(maestro["lon"].to_numpy(), maestro["lat"].to_numpy(), CELDAS)
    enl_ad = pd.read_parquet(r.grilla_v1 / "estaciones_enlaces_adicional.parquet", columns=["celda"])
    celdas_red2 = sorted(set(celdas_m[celdas_m >= 0].tolist()) | set(enl_ad["celda"].tolist()))
    celdas_obj = CELDAS[CELDAS["celda"].isin(celdas_red2)].reset_index(drop=True)
    medidas["celdas_red2"] = int(len(celdas_obj))
    ini = pd.Timestamp(f"{mes}-01")
    fin = (ini + pd.offsets.MonthEnd(0)).date().isoformat()
    t = time.perf_counter()
    sat, _ = satelites_red2(ft, celdas_obj, ENLACES, 1, ini.date().isoformat(), fin)
    medidas["satelites_mes_s"] = round(time.perf_counter() - t, 1)
    medidas["dias_satelites_mes"] = int(sat["fecha_local"].nunique())
    d0 = pd.Timestamp(ventana_sin_tropomi)
    t = time.perf_counter()
    satelites_red2(ft, celdas_obj, ENLACES, 1, d0.date().isoformat(), (d0 + pd.Timedelta(days=dias - 1)).date().isoformat())
    medidas["satelites_semana_sin_tropomi_s"] = round(time.perf_counter() - t, 1)
    medidas["dias_semana"] = dias
    claves = _muestra_claves(r, pol, ini.date().isoformat(), fin)
    rng = np.random.default_rng(42)
    obs = claves[["estacion", "ts_utc"]].copy()
    obs["obs"] = rng.lognormal(2.5, 0.8, len(obs))
    obs["n"], obs["version"] = 1, "medicion"
    est = (claves.drop_duplicates("estacion").rename(columns={"lat_est": "lat", "lon_est": "lon"})
           [["estacion", "celda", "lat", "lon", "region_sinca"]].reset_index(drop=True))
    ctx = {"ft": ft, "CELDAS": CELDAS, "ENLACES": ENLACES, "ESTATICAS": ESTATICAS, "LULC": LULC}
    t = time.perf_counter()
    df, _ = construir_panel_red2(pol, obs, est, sat, ctx, 1)
    medidas["panel_mes_s"] = round(time.perf_counter() - t, 1)
    medidas["filas_muestra"] = int(len(df))
    medidas["estaciones_muestra"] = int(df["estacion"].nunique())
    medidas["codigo_v1"] = huellas
    return medidas


def proyectar(medidas: dict, filas_red2: dict, procesos: int = 1,
              desde: str = DESDE, hasta: str = HASTA, inicio_tropomi: str = "2018-04-30",
              fin_tropomi: str = "2026-10-13", calentamiento: int = 15) -> dict:
    """Proyección gruesa del armado completo a partir de ``medir`` (horas de máquina, en serie y con ``procesos``).

    * Panel: el segundo por fila del mes medido × las filas de la red 2 de cada contaminante (incluye la lectura de
      los reanálisis, ACAG, estáticas y el vecindario).
    * Satélites: segundos por día con y sin TROPOMI, medidos con todas las celdas de la red 2 (cada tramo de 3 meses
      agrega 15 días de calentamiento), × los días del período."""
    dias_total = (pd.Timestamp(hasta) - pd.Timestamp(desde)).days + 1
    dias_trop = (pd.Timestamp(fin_tropomi) - pd.Timestamp(inicio_tropomi)).days + 1
    n_tramos = len(tramos(desde, hasta))
    dias_mes = medidas["dias_satelites_mes"] + calentamiento
    s_dia_con = medidas["satelites_mes_s"] / dias_mes
    s_dia_sin = medidas["satelites_semana_sin_tropomi_s"] / (medidas["dias_semana"] + calentamiento)
    sat_s = dias_trop * s_dia_con + (dias_total - dias_trop + n_tramos * calentamiento) * s_dia_sin
    s_fila = medidas["panel_mes_s"] / max(1, medidas["filas_muestra"])
    panel_s = {pol: s_fila * n for pol, n in filas_red2.items()}
    total_s = sat_s + sum(panel_s.values())
    return {"satelites_h": round(sat_s / 3600, 2), "panel_h": {p: round(v / 3600, 2) for p, v in panel_s.items()},
            "total_serie_h": round(total_s / 3600, 2), "procesos": procesos,
            "total_con_procesos_h": round(total_s / 3600 / max(1, procesos) * 1.15, 2),
            "supuestos": {"segundos_por_fila_panel": s_fila, "segundos_por_dia_satelite_con_tropomi": s_dia_con,
                          "segundos_por_dia_satelite_sin_tropomi": s_dia_sin, "dias_periodo": dias_total,
                          "dias_con_tropomi": dias_trop, "celdas": medidas.get("celdas_red2"),
                          "eficiencia_paralela": "1/1,15 (supuesto)"}}


def anios_evaluables(ts_local, anios: tuple[int, int] = rs.ANIOS_POR_OMISION,
                     minimo: int = rs.MINIMO_ETIQUETAS_ANIO) -> list[int]:
    """Los años locales del período del reloj con al menos ``minimo`` etiquetas: los que ``reloj_sinca_v2.verificar_serie``
    evalúa (cuenta todas las filas de ``observaciones.parquet``, como el reloj)."""
    conteo = pd.to_datetime(pd.Series(ts_local)).dt.year.value_counts(dropna=True)
    return sorted(int(a) for a, n in conteo.items() if anios[0] <= int(a) <= anios[1] and int(n) >= minimo)


def observaciones_desde_derivado(pol: str, series: list[dict], factor: dict, veredictos: dict, region_de: dict,
                                 politica: dict, ruta_snifa: Path, con_celda: pd.DataFrame, convencion: str | None = None,
                                 evaluadas: set | None = None, con_fila: set | None = None, marcar_rachas=None,
                                 huellas: dict | None = None) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Observaciones de un contaminante desde el derivado de la red 2 y SNIFA, con todas las reglas (R3 a R9).

    ``series``: las de ``reloj_sinca_v2.series_del_derivado``; ``factor``: {(estación, contaminante): factor} de las
    series que entran (``unidades_v2``); ``veredictos``: {(estación, contaminante): {año: veredicto}} de la convención
    elegida; ``region_de``: región SINCA de cada estación con celda; ``convencion``: la de la etiqueta civil (T4, la que
    eligió el reloj); ``evaluadas``: las series (estación, contaminante) que registró el reloj en su resumen; ``con_fila``:
    las unidades (estación, contaminante, año) que tienen fila en la tabla de veredictos del reloj. Una serie que el
    reloj no registró, o un año con 720 etiquetas o más sin fila en la tabla, detiene el armado; una serie sin ningún
    año evaluable (menos de 720 etiquetas en cada año) sigue la regla general UTC−4 y queda contada.
    ``marcar_rachas``: en el armado, ``produccion.marcar_rachas`` (T12; ``observaciones_red2``). ``huellas``: el sha256
    de cada serie que registró el armado al principio (``reloj_sinca_v2.huellas_de`` del registro de
    ``series_con_huella``), obligatorio: cada ``observaciones.parquet`` se lee desde los bytes cuyo sha256 es ése
    (``reloj_sinca_v2.leer_serie``), así que una serie que cambió entre el registro (y el reloj vuelto a calcular) y esta
    lectura detiene el armado antes de publicar ningún panel (ronda 5 de la traducción, menor 3). Devuelve
    (observaciones, registro, horas civiles especiales)."""
    if evaluadas is None or con_fila is None or huellas is None:
        raise ValueError("observaciones_desde_derivado necesita las series que registró el reloj (evaluadas), las "
                         "unidades con fila en su tabla (con_fila) y el sha256 de cada serie registrada (huellas)")
    lista, sin_anio_evaluable = [], []
    for s in (x for x in series if x["contaminante"] == pol):
        clave = (s["estacion"], pol)
        if clave not in factor or s["estacion"] not in region_de:
            continue
        if clave not in evaluadas:
            raise SystemExit(f"{s['estacion']} {pol}: serie sin veredicto del reloj (no la registró reloj_sinca_v2)")
        df = rs.leer_serie(s, ["ts_local", "obs", "qc_observacion", "seleccionada"], huellas, "panel_red2_v2")
        evaluables = anios_evaluables(df["ts_local"])
        sin_fila = [a for a in evaluables if (s["estacion"], pol, a) not in con_fila]
        if sin_fila:
            raise SystemExit(f"{s['estacion']} {pol}: años con {rs.MINIMO_ETIQUETAS_ANIO} etiquetas o más sin veredicto "
                             f"del reloj: {sin_fila[:10]}")
        if not evaluables:
            sin_anio_evaluable.append(f"{s['estacion']}:{pol}")
        lista.append(procesar_serie_sinca(df, s["estacion"], pol, factor[clave], veredictos.get(clave, {}),
                                          rs.zona_de(region_de[s["estacion"]], politica),
                                          Path(s["ruta"]).parent.name.split("=", 1)[1], convencion))
    sn = series_snifa_red2(ruta_snifa, pol) if pol == "no2" else pd.DataFrame()
    obs, info = observaciones_red2(lista, sn, con_celda, marcar_rachas=marcar_rachas)
    # R7: registro de las horas civiles repetidas (con su ocurrencia alternativa) e inexistentes (desplazadas).
    cols_reloj = ["estacion", "ts_local", "ts_utc", "ts_utc_alternativo", "qc_hora", "reloj"]
    civiles = pd.concat([pd.DataFrame(columns=cols_reloj)] + [x.loc[x["reloj"] == "civil", cols_reloj] for x in lista],
                        ignore_index=True)
    especiales = civiles[civiles["qc_hora"] != "civil_univoca"][cols_reloj[:-1]].reset_index(drop=True)
    anios = civiles.assign(a=pd.to_datetime(civiles["ts_local"]).dt.year).drop_duplicates(["estacion", "a"])
    info["reloj_civil"] = {"filas_convertidas": int(len(civiles)), "estaciones_anios": int(len(anios)),
                           "convencion": convencion, "horas_especiales": especiales["qc_hora"].value_counts().to_dict()}
    info["series_que_entran"] = len(lista)
    info["reloj_civil"]["series_sin_anio_evaluable"] = sorted(sin_anio_evaluable)   # regla general UTC−4
    return obs, info, especiales


def enlaces_estaciones_nuevas(cm, cg, nuevas: pd.DataFrame, enlaces_celda: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Enlaces de las estaciones nuevas (R8) con el procedimiento de ``construir_grilla.construir_enlaces``
    (``construir_grilla.py:199-219``: píxel válido más cercano con ``enlazar_pixel_valido``, las mismas distancias y
    la misma validez) para ERA5-Land, capa límite, MERRA-2, CAMS y GEOS-CF. El enlace MAIAC de la estación es el de su
    celda en la grilla v1 (``enlaces_productos``, f441617b…). Ese enlace por estación no tiene efecto en el panel:
    ``_features`` lee MAIAC por celda (``maiac_pixel`` de la celda, ``_features.py:148``). El catálogo MAIAC entra como
    insumo por su registro de T5."""
    out = nuevas[["estacion", "lat", "lon"]].copy()
    catalogos = {p: cm.leer_catalogo(p) for p in ("era5land", "era5blh", "merra2", "cams")}
    geos = cm.catalogo_geoscf()
    if geos is not None:
        catalogos["geoscf"] = geos
    validez = {p: cm.pixeles_validos(p) for p in cg.DISTANCIA_MAX_VECINO_KM}
    for producto, cat in catalogos.items():
        pid, d, tipo = cg.enlazar_pixel_valido(out["lat"].to_numpy(), out["lon"].to_numpy(), cat, validez.get(producto),
                                               cg.DISTANCIA_MAX_KM[producto], cg.DISTANCIA_MAX_VECINO_KM.get(producto))
        out[f"{producto}_pixel"] = pid
        out[f"{producto}_dist_km"] = d
        if producto in cg.DISTANCIA_MAX_VECINO_KM:
            out[f"{producto}_enlace"] = pd.Categorical(tipo, categories=["propio", "vecino_valido", "sin_enlace"])
    m = enlaces_celda.set_index("celda")["maiac_pixel"]
    out["maiac_pixel"] = m.reindex(nuevas["celda"].to_numpy()).fillna(-1).astype("int64").to_numpy()
    out["maiac_dist_km"] = np.nan
    out = out.merge(nuevas[["estacion", "celda", "cod_comuna", "region_sinca"]], on="estacion")
    return out, {"procedimiento": "construir_grilla.construir_enlaces (píxel válido más cercano)",
                 "maiac": "enlace de la celda en la grilla v1; sin efecto en el panel, porque _features lee MAIAC por "
                          "celda; el catálogo MAIAC entra como insumo por su registro de T5"}


def sha256_de(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 22), b""):
            h.update(bloque)
    return h.hexdigest()


def observaciones_float64(pol: str, r: rv.RutasV2, meta: dict) -> tuple[pd.DataFrame, dict]:
    """Las observaciones float64 con que se armó el panel red 2 de ``pol`` (``paneles/observaciones_<pol>_red2.parquet``),
    para la reproducción (a2) de ``validar_vecindario_v2`` con la red ampliada. No reconstruye nada: comprueba que el
    archivo es el que declaró el armado (``observaciones_sha256`` del json del panel) y devuelve
    (estacion, ts_utc, obs float64) y los conteos del QC con los nombres de la v1 (``filas_validas`` = horas antes de
    las rachas, ``filas_en_racha``, ``estaciones_con_racha``)."""
    ruta = r.raiz_v2 / "paneles" / NOMBRE_OBS.format(pol=pol)
    declarado = (meta.get("observaciones_sha256") or {}).get(pol)
    if not declarado:
        raise SystemExit(f"{pol}: el json del panel red 2 no declara el sha256 de sus observaciones")
    if not ruta.exists():
        raise SystemExit(f"{pol}: falta {ruta.name}")
    if sha256_de(ruta) != declarado:
        raise SystemExit(f"{pol}: {ruta.name} no es el que declaró el armado del panel")
    o = pd.read_parquet(ruta, columns=["estacion", "ts_utc", "obs"])
    if o["obs"].dtype != np.float64:
        raise SystemExit(f"{pol}: {ruta.name} no guarda obs en float64")
    ts = pd.to_datetime(o["ts_utc"])
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)
    o = pd.DataFrame({"estacion": o["estacion"].astype(str), "ts_utc": ts.astype("datetime64[ns]"), "obs": o["obs"]})
    qc = meta.get("qc") or {}
    info = {"filas_validas": qc.get("horas_totales"), "filas_en_racha": qc.get("horas_en_racha"),
            "estaciones_con_racha": qc.get("estaciones_con_racha"), "filas": int(len(o)),
            "observaciones_red2": {"archivo": f"paneles/{ruta.name}", "sha256": declarado}}
    return o.reset_index(drop=True), info


def regimenes_comunes(por_pol: dict[str, dict]) -> dict:
    """Regla para cuando PM2,5 y NO2 no dan los mismos tramos (R17): los tramos se cortan en todo año en que cambia la
    combinación de cualquiera de los dos, de modo que los dos comparten los mismos años de régimen (lo que lee
    ``metricas_v2``); cada tramo registra la combinación de cada contaminante."""
    anios = sorted({int(a) for r in por_pol.values() for t in r["tramos"] for a in range(t["anios"][0], t["anios"][1] + 1)})
    def combo(r, a):
        return next((t["familias"] for t in r["tramos"] if t["anios"][0] <= a <= t["anios"][1]), "ninguna")
    tramos = []
    for a in anios:
        c = {pol: combo(r, a) for pol, r in sorted(por_pol.items())}
        if tramos and tramos[-1]["familias_por_contaminante"] == c and tramos[-1]["anios"][1] == a - 1:
            tramos[-1]["anios"][1] = a
        else:
            tramos.append({"anios": [a, a], "familias_por_contaminante": c})
    for t in tramos:
        t["id"] = f"{t['anios'][0]}" if t["anios"][0] == t["anios"][1] else f"{t['anios'][0]}-{t['anios'][1]}"
        t["disponibilidad"] = "; ".join(f"{pol}: {c}" for pol, c in t["familias_por_contaminante"].items())
    return {"regla": "tramos cortados en todo año en que cambia la combinación de PM2,5 o de NO2 (R17)",
            "tramos": tramos, "iguales_en_los_dos": len({json.dumps(r["tramos"]) for r in por_pol.values()}) == 1}


def estaciones_con_propietario(est: pd.DataFrame, fichas: pd.DataFrame) -> pd.DataFrame:
    """R10: las estaciones con celda de la red 2 con ``propietario``, ``operador``, ``red`` (de la ficha) y
    ``calificacion``, y la clasificación descriptiva. Las SNIFA no tienen ficha SINCA: T1(3) (calificación de la ficha
    y, si falta, el propietario) no las alcanza, así que quedan en «no informado», como las cuatro fichas sin
    calificación ni propietario (cuarta revisión, menor 17); ``nota_tipo`` dice por qué."""
    f = fichas.rename(columns={"red": "red_ficha"})[["estacion", "id_sinca", "propietario", "operador", "red_ficha",
                                                       "calificacion", "tipo_propietario"]]
    out = est.merge(f, on="estacion", how="left")
    snifa = out["red"] == RED_SNIFA
    out.loc[snifa, "tipo_propietario"] = "no informado"
    out["nota_tipo"] = np.where(snifa, "SNIFA, sin ficha SINCA: T1(3) no la alcanza", "")
    return out


ETIQUETAS_PROPIETARIO = ("pública", "empresa", "no informado")


def estrato_propietario(r: rv.RutasV2, pol: str, nombres_estacion, js) -> tuple[np.ndarray, list[str], dict]:
    """R10: la desagregación descriptiva del §8 (pública o de empresa; no entra en el §9) como estrato de las métricas:
    código por fila (``js`` = índice de estación de cada fila en ``nombres_estacion``) desde
    ``paneles/estaciones_red2.parquet``, comprobado contra el sha256 que declara el json del panel. Las SNIFA y las
    fichas sin calificación ni propietario cuentan como «no informado» (``estaciones_con_propietario``). Devuelve
    (códigos, etiquetas, registro)."""
    meta = rv.leer_json(r.raiz_v2 / "paneles" / NOMBRE_PANEL.format(pol=pol).replace(".parquet", ".json")) or {}
    ruta = r.raiz_v2 / "paneles" / NOMBRE_ESTACIONES
    declarado = (meta.get("estaciones") or {}).get("sha256")
    if not declarado or not ruta.exists() or sha256_de(ruta) != declarado:
        raise SystemExit(f"{pol}: {NOMBRE_ESTACIONES} falta o no es el que declaró el armado del panel")
    est = pd.read_parquet(ruta, columns=["estacion", "tipo_propietario"])
    tipo = dict(zip(est["estacion"].astype(str), est["tipo_propietario"].fillna("no informado").astype(str)))
    nombres = [str(s) for s in nombres_estacion]
    faltan = sorted(set(nombres) - set(tipo))
    if faltan:
        raise SystemExit(f"{pol}: estaciones del panel sin fila en {NOMBRE_ESTACIONES}: {faltan[:5]}")
    clase = {"pública": 0, "empresa": 1, "no informado": 2}
    por_estacion = np.array([clase.get(tipo[s], 1 if tipo[s].startswith("empresa") else 2) for s in nombres],
                            dtype="int64")
    cod = por_estacion[np.asarray(js, dtype="int64")]
    registro = {"fuente": f"paneles/{NOMBRE_ESTACIONES}", "sha256": declarado, "regla": "R10, descriptiva",
                "estaciones": {e: int((por_estacion == k).sum()) for k, e in enumerate(ETIQUETAS_PROPIETARIO)}}
    return cod, list(ETIQUETAS_PROPIETARIO), registro


SCHEMA_CONTRASTE = "airpollution.modelo-1km-v2.contraste-unidades.v1"   # el de contraste_unidades_v2
GASES_CONTRASTE = ("no2", "o3")                                          # los de la segunda corrida
# contraste_unidades_v2.NOMBRES_SALIDA: los nombres fijos de la escritura única de la segunda corrida
NOMBRES_CONTRASTE = ("contraste_unidades_cams_segunda.csv", "contraste_unidades_cams_segunda.json")


def contraste_y_su_huella(ruta: Path, sha: str | None, r: rv.RutasV2, series: dict | None = None) -> dict:
    """R6, «rige la segunda corrida y el cambio se registra»: la huella dada tiene que ser la del CSV; el CSV, ser
    ``<raíz v2>/unidades_red2/contraste_unidades_cams_segunda.csv``, el nombre fijo de la escritura única (cuarta
    revisión, menor 7); y su json lateral, ``contraste_unidades_cams_segunda.json`` junto a él (lo escribe
    ``contraste_unidades_v2``), tiene que existir, con su
    ``schema``, ``sha256_csv`` igual a la huella, la primera corrida por su huella (ca0805ae…) con la lista de
    cambios (aunque esté vacía), los archivos CAMS que leyó, cada uno con su ruta y su sha256
    (``contraste_unidades_v2.exigir_cams``; quinta revisión, menor 7), y las series que leyó: las mismas raíces y, en
    NO2 y O3, las mismas series (estación, contaminante, versión y sha256) que lee el panel (``series``, de
    ``reloj_sinca_v2.series_con_huella``). La primera corrida (repositorio de salud, sin lateral) no pasa. Devuelve lo
    que se registra (huellas del CSV y del lateral)."""
    if series is None:
        raise ValueError("contraste_y_su_huella necesita las series del derivado que lee el panel")
    if not sha:
        raise SystemExit("--contraste-sha256 es obligatoria: la regla de unidades se ata a una corrida del contraste")
    ruta = Path(ruta)
    carpeta = r.raiz_v2 / "unidades_red2"
    if ruta.resolve() != (carpeta / NOMBRES_CONTRASTE[0]).resolve():
        raise SystemExit(f"{ruta.name}: la corrida del contraste que rige es la segunda, "
                         f"<raíz v2>/unidades_red2/{NOMBRES_CONTRASTE[0]} (escritura única)")
    real = uv.sha256_archivo(ruta)
    if real != sha:
        raise SystemExit(f"{ruta.name}: su sha256 no es el dado")
    lateral = carpeta / NOMBRES_CONTRASTE[1]
    if not lateral.exists():
        raise SystemExit(f"{ruta.name} no tiene su json lateral: no es una corrida de contraste_unidades_v2")
    d = json.loads(lateral.read_text(encoding="utf-8"))
    if d.get("schema") != SCHEMA_CONTRASTE or d.get("sha256_csv") != sha:
        raise SystemExit(f"{lateral.name} no es el lateral de esta corrida (schema o sha256_csv distintos)")
    primera = d.get("primera_corrida") or {}
    if primera.get("sha256") != uv.SHA_CONTRASTE_PRIMERA or not isinstance(primera.get("cambios"), list):
        raise SystemExit(f"{lateral.name} no registra los cambios frente a la primera corrida "
                         f"({uv.SHA_CONTRASTE_PRIMERA[:8]}…), como pide R6")
    import contraste_unidades_v2 as cu
    cu.exigir_cams(d, lateral.name)
    leidas = d.get("series_leidas") or {}
    gases = sorted(leidas.get("contaminantes") or [])
    if gases != sorted(GASES_CONTRASTE):
        raise SystemExit(f"{lateral.name}: la segunda corrida tiene que leer {GASES_CONTRASTE}, no {gases}")
    propias = [s for s in series["series"] if s["contaminante"] in gases]
    if (leidas.get("raices"), leidas.get("series")) != (series["raices"], propias):
        raise SystemExit(f"{lateral.name}: la segunda corrida no leyó el derivado que lee el panel (raíces o series de "
                         f"NO2 y O3 —estación, contaminante, versión y sha256— distintas)")
    return {"sha256": sha, "lateral_sha256": uv.sha256_archivo(lateral), "primera_corrida_sha256": primera["sha256"],
            "cambios_frente_a_la_primera": len(primera["cambios"]), "huella_series_leidas": leidas.get("huella_series"),
            "archivos_cams": len(d["cams"]["archivos"])}


def unidades_del_armado(r: rv.RutasV2, ruta_contraste: Path, sha_contraste: str, maestro: pd.DataFrame
                        ) -> tuple[pd.DataFrame, dict]:
    """La regla de unidades del armado (R6 y R8): ``unidades_v2.unidades_red2`` con la segunda corrida del contraste,
    las estaciones con coordenada de los maestros de R8 y la primera corrida rechazada por su huella (rige la segunda)."""
    return uv.unidades_red2(r.datos, ruta_contraste, sha_contraste, con_coordenada=set(maestro["estacion"]),
                            rechazar_primera=True)


def reloj_y_su_huella(ruta: Path, r: rv.RutasV2, series: dict, series_d: list[dict], region_de: dict, politica: dict,
                      sha_politica: str | None, confirmar: str | None = None, corrida: str | None = None,
                      raiz_derivado: Path | None = None) -> tuple[pd.DataFrame, dict, set]:
    """Veredictos del reloj y la convención civil de T4, tomados de la salida de ``reloj_sinca_v2`` y comprobados:

    * el parquet es ``<raíz v2>/verificacion_reloj_sinca_red2/veredictos.parquet``, la carpeta de escritura única del
      reloj, y el que registra su ``resumen.json`` (``schema`` del reloj, ``sha256_veredictos`` y
      ``huella_veredictos_contenido``);
    * el reloj corrió sobre todo SINCA (2000-2026 y los tres contaminantes), con la política temporal que lee el panel
      (``sha_politica``, 41018e4c…), sobre **las mismas series** que lee el panel (``series``, de
      ``reloj_sinca_v2.series_con_huella``: raíces y, por serie, estación, contaminante, versión y sha256) y sobre la
      misma corrida del derivado (``corrida``) o sobre una corrida equivalente: si el derivado se volvió a correr sin
      cambios después del reloj, el preparador reabrió las mismas versiones en otra corrida; vale si las dos terminaron
      y publicaron exactamente las versiones que registra el reloj (``derivado_red2_v2.corridas_equivalentes``, con
      ``raiz_derivado``; cuarta revisión, menores 5 y 32);
    * toda fila es de una serie registrada y su ``zona_iana`` es la de la región de su estación en los maestros de R8;
    * la tabla es la que vuelve a dar ``reloj_sinca_v2.verificar_red`` con esas series (sólo ``ts_local`` y
      ``hora_repetida_en_fuente``), las regiones (``region_de``) y la política: una tabla editada no pasa;
    * la base de zonas horarias del panel da las horas especiales fijadas (``reloj_sinca_v2.exigir_base_de_zonas``:
      132 en 2000-2026, 96a7b7cb…) y las mismas horas especiales y los mismos archivos de zona que la del reloj;
    * la elección que declara el resumen es la que vuelve a dar ``elegir_convencion``, y el límite de R7 que declara
      (``limite_sin_transiciones``: años sin cambio de hora y unidades ``sin_transiciones`` junto a un año
      ``hora_civil``) es el que vuelven a dar sus veredictos con esa convención; va al json del panel.

    ``confirmar`` (``--convencion-civil``) sólo puede confirmar la elegida, nunca contradecirla. Devuelve (veredictos,
    registro para el json del panel, series que el reloj evaluó)."""
    esperada = (r.raiz_v2 / rs.NOMBRE_SALIDA / "veredictos.parquet").resolve()
    if Path(ruta).resolve() != esperada:
        raise SystemExit(f"{Path(ruta).name}: los veredictos que rigen son los de <raíz v2>/{rs.NOMBRE_SALIDA}/, la carpeta "
                         f"de escritura única del reloj")
    sha = uv.sha256_archivo(esperada)
    ruta_resumen = esperada.with_name("resumen.json")
    resumen = json.loads(ruta_resumen.read_text(encoding="utf-8")) if ruta_resumen.exists() else {}
    if resumen.get("schema") != rs.SCHEMA or resumen.get("sha256_veredictos") != sha:
        raise SystemExit(f"{esperada.name} no es el que registra resumen.json de reloj_sinca_v2 (schema o huella)")
    if sha_politica != rs.SHA_POLITICA or resumen.get("politica_temporal_sha256") != sha_politica:
        raise SystemExit("el reloj no corrió con la política temporal que lee el panel (41018e4c…)")
    if (resumen.get("anios"), sorted(resumen.get("contaminantes") or [])) != \
            (list(rs.ANIOS_POR_OMISION), sorted(rs.CONTAMINANTES_SINCA)):
        raise SystemExit("el reloj no corrió sobre todo SINCA (2000-2026 y los tres contaminantes)")
    if (resumen.get("raices"), resumen.get("series_registradas")) != (series["raices"], series["series"]):
        raise SystemExit("el reloj no corrió sobre el derivado que lee el panel: sus raíces o sus series (estación, "
                         "contaminante, versión y sha256) no son las mismas")
    del_reloj = (resumen.get("derivado") or {}).get("corrida")
    equivalente = False
    if corrida is not None and del_reloj != corrida:
        import derivado_red2_v2 as dr
        versiones = {(s["estacion"], s["contaminante"]): s["version"] for s in series["series"]}
        equivalente = raiz_derivado is not None and del_reloj is not None and \
            dr.corridas_equivalentes(raiz_derivado, del_reloj, corrida, versiones)
        if not equivalente:
            raise SystemExit(f"el reloj no corrió sobre la última corrida del derivado ({corrida}) ni sobre una corrida "
                             f"equivalente (corrió sobre {del_reloj}: no terminó o publicó otras versiones)")
    tabla = pd.read_parquet(esperada)
    contenido = hashlib.sha256(tabla.to_csv(index=False).encode("utf-8")).hexdigest()
    if contenido != resumen.get("huella_veredictos_contenido"):
        raise SystemExit(f"{esperada.name}: su contenido no es el que registra resumen.json")
    registradas = {(s["estacion"], s["contaminante"]) for s in series["series"]}
    ajenas = sorted({(str(e), str(p)) for e, p in zip(tabla["estacion"], tabla["contaminante"])} - registradas)
    if ajenas:
        raise SystemExit(f"{esperada.name} trae series que el reloj no registró: {ajenas[:5]}")
    malas = sorted({str(e) for e, z in zip(tabla["estacion"], tabla["zona_iana"])
                    if str(e) not in region_de or z != rs.zona_de(region_de[str(e)], politica)})
    if malas:
        raise SystemExit(f"{esperada.name}: la zona IANA de {malas[:5]} no es la de su región en los maestros de R8")
    otra, _ = rs.verificar_red(series_d, region_de, politica, huellas=rs.huellas_de(series), quien="panel_red2_v2")
    if hashlib.sha256(otra.to_csv(index=False).encode("utf-8")).hexdigest() != contenido:
        raise SystemExit(f"{esperada.name} no es la tabla que dan las series del derivado con reloj_sinca_v2.verificar_red")
    zonas = [politica["zona_iana_default"], *politica["zonas_iana_por_region"].values()]
    base = rs.base_de_zonas(zonas)
    fijadas = rs.exigir_base_de_zonas(base, "panel_red2_v2")          # quinta revisión, menor 3
    suya = resumen.get("zonas_horarias") or {}
    if (base["huella_horas_especiales"], {z: a["sha256"] for z, a in base["archivos"].items()},
            base["conversion"]["biblioteca"]) != \
            (suya.get("huella_horas_especiales"), {z: (a or {}).get("sha256") for z, a in (suya.get("archivos") or {}).items()},
             (suya.get("conversion") or {}).get("biblioteca")):
        raise SystemExit("la base de zonas horarias del panel no es la del reloj (horas especiales, archivos de zona o "
                         "biblioteca de la conversión distintos)")
    eleccion = rs.elegir_convencion(tabla)
    declarada = resumen.get("convencion_civil") or {}
    if (declarada.get("elegida"), declarada.get("conteos")) != (eleccion["elegida"], eleccion["conteos"]):
        raise SystemExit("resumen.json de reloj_sinca_v2 declara otra convención civil (o otros conteos) que la que dan "
                         "sus veredictos con la regla T4")
    limite = rs.limite_sin_transiciones(tabla, eleccion["elegida"], zonas)     # quinta revisión, menor 4
    suyo = resumen.get("limite_sin_transiciones") or {}
    if (suyo.get("unidades_junto_a_civil"), suyo.get("anios_sin_cambio_de_hora")) != \
            (limite["unidades_junto_a_civil"], limite["anios_sin_cambio_de_hora"]):
        raise SystemExit("resumen.json de reloj_sinca_v2 no declara el límite de R7 que dan sus veredictos (años sin "
                         "cambio de hora y unidades sin_transiciones junto a un año hora_civil)")
    if confirmar is not None and confirmar != eleccion["elegida"]:
        raise SystemExit(f"--convencion-civil {confirmar} contradice la que eligió el reloj por T4 "
                         f"({eleccion['elegida']}): sólo puede confirmarla")
    evaluadas = {(str(x["estacion"]), str(x["contaminante"])) for x in resumen.get("evaluacion_por_serie") or []
                 if x.get("evaluada")}
    return tabla, {"veredictos_sha256": sha, "resumen_sha256": uv.sha256_archivo(ruta_resumen),
                   "convencion_civil": eleccion["elegida"], "conteos": eleccion["conteos"],
                   "empate": eleccion["empate"], "regla": "T4 con la unidad de T9",
                   "convenciones_evaluadas": list(rs.CONVENCIONES), "huella_series": resumen.get("huella_series"),
                   "politica_temporal_sha256": sha_politica, "derivado": resumen.get("derivado"),
                   "corrida_del_armado": corrida if corrida is not None else del_reloj,
                   "corrida_equivalente": bool(equivalente),
                   "zonas_horarias": base, "horas_especiales_fijadas": fijadas, "limite_sin_transiciones": limite,
                   "recalculado": "verificar_red sobre las mismas series: tabla idéntica",
                   "evaluadas": sorted(f"{e}:{p}" for e, p in evaluadas)}, evaluadas


def red_del_panel(previa: dict, est: pd.DataFrame, obs_pol: dict) -> dict:
    """R2 y R3 en el json del panel: por contaminante, la red antes de mirar las observaciones
    (``red_ampliada_v2.red_resultante``, con la regla de unidades del armado) frente a ``RED_ESPERADA``, y la que queda
    con al menos una hora, separando las estaciones que salen por no tener celda y las que salen por R3 (cero horas)."""
    grupo = dict(zip(est["estacion"].astype(str), est["grupo"].astype(str)))
    con_celda = set(est["estacion"].astype(str))
    out = {}
    for pol, o in obs_pol.items():
        antes = previa.get(pol) or {"estaciones": [], "actuales": 0, "nuevas": 0, "snifa": 0, "total": 0}
        con_horas = set(o["estacion"].astype(str))
        sinca = [e for e in antes["estaciones"] if e in con_celda and e in con_horas]
        snifa = sorted(e for e in con_horas if grupo.get(e) == "snifa")
        out[pol] = {"esperada": ra.RED_ESPERADA.get(pol),
                    "antes_de_las_observaciones": {k: antes[k] for k in ("actuales", "nuevas", "snifa", "total")},
                    "igual_a_la_esperada": ra.RED_ESPERADA.get(pol) == {k: antes[k] for k in
                                                                      ("actuales", "nuevas", "snifa", "total")},
                    "con_al_menos_una_hora": {"actuales": sum(grupo.get(e) == "actual" for e in sinca),
                                              "nuevas": sum(grupo.get(e) == "nueva" for e in sinca),
                                              "snifa": len(snifa), "total": len(sinca) + len(snifa)},
                    "fuera_sin_celda": sorted(e for e in antes["estaciones"] if e not in con_celda),
                    "fuera_por_R3_cero_horas": sorted(e for e in antes["estaciones"]
                                                      if e in con_celda and e not in con_horas),
                    "fuera_por_unidad": antes.get("fuera_por_unidad", [])}
    return out


def ejecutar(r: rv.RutasV2, inv: pd.DataFrame, args, cfg: dict | None = None, estado=None) -> int:
    """Armado completo (R22, paso 3). Exige la traducción confirmada en git (R22, paso 2) y, antes de leer nada, el
    registro de los catálogos MAIAC (T5). Después, antes de escribir: la lista cerrada; el derivado de la red 2
    completo (``derivado_red2_v2.exigir_derivado_completo``: una raíz, la de ``destino_por_omision``; su última
    corrida terminada, con el ``plan.json`` y la huella rastreada de ``derivado_red2_v2.py``; el conjunto estación ×
    contaminante de R2; las versiones de esa corrida; y cada versión sin ventana y con exactamente sus fuentes de los tres
    manifiestos de la lista cerrada); la segunda corrida del contraste sobre esas series
    (``contraste_y_su_huella``) y la regla de unidades con ella (``unidades_del_armado``: R6 y T12 a, la segunda corrida
    rige sobre el panel); los veredictos del reloj sobre esas mismas series, vueltos a calcular
    (``reloj_y_su_huella``); y el código v1 con su huella (``verificar_codigo_v1``). Las observaciones de cada serie se
    leen desde los bytes cuyo sha256 se registró al principio (``observaciones_desde_derivado`` con ``huellas``), antes
    de publicar ningún panel. Cada json que escribe (inventario, copia congelada, paneles, O3 y regímenes) lleva su
    procedencia (``red_ampliada_v2.traza_red2``, con la traducción con que se escribió). ``cfg`` y ``estado``, sólo
    para las pruebas."""
    import derivado_red2_v2 as dr

    cfg = cfg if cfg is not None else rv.cargar_config(r)
    compuerta = ra.exigir_traduccion_confirmada(r, cfg, estado)
    if not (args.derivado and args.contraste and args.veredictos):
        raise SystemExit("--ejecutar necesita --derivado, --contraste, --contraste-sha256 y --veredictos")
    reg_maiac, sha_reg_maiac = leer_registro_maiac(r)
    if reg_maiac is None:
        raise SystemExit("falta el registro de los catálogos MAIAC (T5): corre antes --registrar-catalogo-maiac")
    if not inv["fuente_registro"].astype(str).str.startswith("registro_catalogo_maiac").any():
        raise SystemExit("el inventario no se hizo con el registro de los catálogos MAIAC (T5)")
    ra.verificar_lista_cerrada(r.datos)                              # antes de leer los maestros
    maestro = ra.maestro_red2(r.datos)
    reg_series, series_d = rs.series_con_huella(args.derivado, r.datos)
    derivado = dr.exigir_derivado_completo(args.derivado, series_d, r.datos, "panel_red2_v2")
    contraste = contraste_y_su_huella(args.contraste, args.contraste_sha256, r, reg_series)
    sha_contraste = contraste["sha256"]
    # R6 y T12 (a): la regla de unidades, con la segunda corrida que rige sobre el panel, antes de escribir nada de
    # escritura única (ronda 5 de la traducción, menor 5): una segunda corrida que no cubre la red se ve aquí, no
    # después de congelar los insumos
    tabla_u, info_u = unidades_del_armado(r, args.contraste, sha_contraste, maestro)
    politica, sha_politica = rs.leer_politica_con_huella()
    region_maestro = dict(zip(maestro["estacion"], maestro["region_sinca"]))
    ver, reloj_reg, evaluadas = reloj_y_su_huella(args.veredictos, r, reg_series, series_d, region_maestro, politica,
                                                  sha_politica, args.convencion_civil, derivado["corrida"],
                                                  raiz_derivado=Path(args.derivado[0]))
    con_fila = {(str(e), str(p), int(a)) for e, p, a in zip(ver["estacion"], ver["contaminante"], ver["anio"])}
    convencion = reloj_reg["convencion_civil"]                      # T4, la del reloj
    veredictos = rs.veredictos_por_serie(ver, convencion)
    huellas_v1 = verificar_codigo_v1()
    raiz_ins = r.raiz_v2 / "insumos_red2"
    sha_inv, estado_inv = publicar_inventario(inv, r, raiz_ins, compuerta)   # escritura única (al retomar, lo que entra)
    # SINCA y SNIFA no pasan por la copia: los lee este módulo desde la raíz de datos, con la lista cerrada (R2). Si un
    # armado anterior se cortó después de congelar, la copia se retoma comprobando cada sha256 (menor 33).
    congelado, sha_cong, estado_cong = congelar_o_retomar(inv, r, raiz_ins, compuerta=compuerta)
    cm, ft, cg = importar_v1(entorno_lectura(raiz_ins / "congelados" / "data", r.raiz_v1))
    prod = importar_produccion()                                    # T12: la regla de rachas de produccion.py
    CELDAS, ENLACES = cm.cargar_celdas(), cm.cargar_enlaces()
    ESTATICAS, LULC = ft.cargar_estaticas()
    meta_grilla = json.loads((r.grilla_v1 / "metadata.json").read_text(encoding="utf-8"))
    import pliegues_v2 as pv
    snifa = pv.leer_estaciones_snifa(r, pv.leer_estaciones_sinca(r))
    enl_v1 = pd.concat([pd.read_parquet(r.grilla_v1 / n) for n in INSUMOS_GRILLA_V1[4:6]], ignore_index=True)
    nuevas = maestro[maestro["grupo"] == "nueva"].copy()
    nuevas["celda"] = cm.celda_de_lonlat(nuevas["lon"].to_numpy(), nuevas["lat"].to_numpy(), CELDAS)
    enl_new, info_enl = enlaces_estaciones_nuevas(cm, cg, nuevas, ENLACES)
    destino_enl = r.raiz_v2 / "grilla" / NOMBRE_ENLACES
    with rv.candado_artefactos([destino_enl], r):
        sha_enl = rv.publicar_parquet(enl_new, destino_enl, r)
    est = estaciones_con_celda_red2(maestro, snifa, pd.concat([enl_v1, enl_new], ignore_index=True))
    factor = {(e, p): f for e, p, f, ok in zip(tabla_u["estacion"], tabla_u["contaminante"], tabla_u["factor"],
                                                tabla_u["entra"]) if ok}
    region_de = dict(zip(est["estacion"], est["region_sinca"]))
    obs_pol, info_pol, especiales = {}, {}, {}
    for pol in CONTAMINANTES_PANEL + (RAMA_O3,):
        obs_pol[pol], info_pol[pol], especiales[pol] = observaciones_desde_derivado(
            pol, series_d, factor, veredictos, region_de, politica, r.snifa, est, convencion, evaluadas, con_fila,
            marcar_rachas=prod.marcar_rachas, huellas=rs.huellas_de(reg_series))
    red = red_del_panel(ra.red_resultante(ra.series_contrato(r.datos), tabla_u, maestro), est, obs_pol)
    # Observaciones en float64 de los tres contaminantes (la rama O3 las usa en su diseño, R20; la validación del
    # vecindario, para su reproducción bit a bit) y estaciones con sus propietarios (R10).
    fichas = ra.fichas_red2(r.datos)
    estaciones = estaciones_con_propietario(est, fichas)
    destinos = [r.raiz_v2 / "paneles" / NOMBRE_OBS.format(pol=pol) for pol in CONTAMINANTES_PANEL + (RAMA_O3,)]
    destino_est = r.raiz_v2 / "paneles" / NOMBRE_ESTACIONES
    with rv.candado_artefactos(destinos + [destino_est], r):
        sha_obs = {pol: rv.publicar_parquet(obs_pol[pol], d, r) for pol, d in zip(CONTAMINANTES_PANEL + (RAMA_O3,), destinos)}
        sha_est = rv.publicar_parquet(estaciones, destino_est, r)
    celdas_obj = CELDAS[CELDAS["celda"].isin(est["celda"].unique())].reset_index(drop=True)
    sat, meta_sat = satelites_red2(ft, celdas_obj, ENLACES, args.procesos)
    destino_sat = r.raiz_v2 / "paneles" / NOMBRE_SATELITES
    with rv.candado_artefactos([destino_sat], r):
        meta_sat["sha256"] = rv.publicar_parquet(sat, destino_sat, r)
    ctx = {"ft": ft, "CELDAS": CELDAS, "ENLACES": ENLACES, "ESTATICAS": ESTATICAS, "LULC": LULC}
    familias = {k: list(v) for k, v in cfg["metricas"]["desagregaciones"]["regimen_de_predictores"]["sensibilidad"]
                ["fila_a_fila"]["valor"]["familias"].items()}
    comunes = {"insumos": {"inventario_sha256": sha_inv, "congelados_sha256": sha_cong, "corte_utc": CORTE_INSUMOS_UTC,
                           "archivos_congelados": congelado["archivos"], "huella_del_registro": congelado["huella_del_registro"],
                           "por_fecha_de_modificacion": por_fecha_de_modificacion(inv),
                           # R11, «con su lista y sus huellas en el json del panel»: por referencia, con huella (la
                           # lista de cada archivo —ruta, origen y sha256— está en esos dos json; cuarta revisión,
                           # menores 20 y 37)
                           "lista": {"congelados": "insumos_red2/congelados.json", "inventario": "insumos_red2/inventario.json",
                                     "lectura": "por referencia: ruta, origen y sha256 de cada archivo en congelados.json; "
                                                "el inventario completo, con lo que no entra, en inventario.json"},
                           "estado": {"inventario": estado_inv, "copia": estado_cong}},
               "unidades": {**info_u, "contraste": r.relativa(args.contraste), "segunda_corrida": contraste},
               "reloj": reloj_reg, "derivado": derivado, "red": red,
               "registro_catalogo_maiac": {"archivo": f"insumos_red2/{NOMBRE_REGISTRO_MAIAC}", "sha256": sha_reg_maiac,
                                           "huella_teselas": reg_maiac["huella_teselas"],
                                           "entran": reg_maiac["entran"], "fuera": reg_maiac["fuera"]},
               "enlaces_red2": {"sha256": sha_enl, **info_enl}, "estaciones": {"sha256": sha_est},
               "observaciones_sha256": sha_obs, "codigo_v1": huellas_v1, "documento_v1": DOCUMENTO_V1,
               "rachas": {"funcion": "produccion.marcar_rachas", "minimo": int(prod.QC_RACHA),
                          "sha256_produccion": huellas_v1["scripts_modelo_1km/produccion.py"]}}
    # §0 del contrato (quinta revisión, mayores 1 y 2): commit, huella del código (la v2 y cada módulo de la red 2),
    # contrato, configuración, insumos pequeños con su sha256, bibliotecas, Python, procesos y la traducción
    ins_traza = {"inventario": raiz_ins / "inventario.json", "congelados": raiz_ins / "congelados.json",
                 "registro_catalogo_maiac": r.raiz_v2 / "insumos_red2" / NOMBRE_REGISTRO_MAIAC,
                 "contraste": Path(args.contraste), "contraste_lateral": Path(args.contraste).with_suffix(".json"),
                 "veredictos": Path(args.veredictos), "resumen_reloj": Path(args.veredictos).with_name("resumen.json"),
                 "politica_temporal": rs.RUTA_POLITICA, "grilla_metadata": r.grilla_v1 / "metadata.json"}
    comunes["traza"] = ra.traza_red2(r, compuerta, ins_traza, None, args.procesos, programa="panel_red2_v2 --ejecutar",
                                     parametros={"procesos": int(args.procesos)})
    regimenes = {}
    for pol in CONTAMINANTES_PANEL:
        df, resumen = construir_panel_red2(pol, obs_pol[pol], est, sat, ctx, args.procesos)
        faltan = [c for c in predictores_cerrados(cfg, pol) if c not in df.columns]
        if faltan:
            raise SystemExit(f"{pol}: faltan predictores de la lista cerrada en el panel red 2: {faltan}")
        calidad = calidad_alineada(df, obs_pol[pol])
        regimenes[pol] = regimenes_calculados(df["fecha_local"], df["anio"], {c: df[c].to_numpy() for c in df.columns},
                                              familias)
        ruta = r.raiz_v2 / "paneles" / NOMBRE_PANEL.format(pol=pol)
        ruta_q = r.raiz_v2 / "paneles" / NOMBRE_CALIDAD.format(pol=pol)
        ruta_c = r.raiz_v2 / "paneles" / NOMBRE_RELOJ.format(pol=pol)
        with rv.candado_artefactos([ruta, ruta_q, ruta_c, ruta.with_suffix(".json")], r):
            sha = rv.publicar_parquet(df, ruta, r)
            sha_q = rv.publicar_parquet(calidad, ruta_q, r)
            info_pol[pol]["reloj_civil"]["sha256"] = rv.publicar_parquet(especiales[pol], ruta_c, r)
            rv.publicar_json({
                "schema": SCHEMA, "contrato": "modelo-1km-horario-v2", "bloque": ra.BLOQUE,
                "decisiones_traduccion": ra.DECISIONES_TRADUCCION, "contaminante": pol, "desde": DESDE, "hasta": HASTA,
                "enlaces_sha256": meta_grilla["archivos"]["enlaces_productos"],
                "reloj_sinca": "UTC-4 fijo; etiqueta=fin; hora civil convertida donde el veredicto es hora_civil (R7), "
                               "con la convención de T4",
                "redes": [RED_SINCA, RED_SNIFA], "estaciones_sha256": identidad_red(est["estacion"]),
                "qc_racha_minima": QC_RACHA, "qc": info_pol[pol], "interpolacion": "", "satelites": meta_sat,
                **comunes, "regimenes": regimenes[pol], "calidad_sha256": sha_q, "sha256": sha, **resumen},
                ruta.with_suffix(".json"), r)
    ruta_reg = r.raiz_v2 / "paneles" / NOMBRE_REGIMENES
    with rv.candado_artefactos([ruta_reg, r.raiz_v2 / "paneles" / NOMBRE_OBS_O3.replace(".parquet", ".json")], r):
        rv.publicar_json({"schema": SCHEMA, "por_contaminante": regimenes, "comunes": regimenes_comunes(regimenes),
                          "traza": comunes["traza"]}, ruta_reg, r)
        rv.publicar_json({"schema": SCHEMA, "rama": "o3_next (R20)", "bloque": ra.BLOQUE, "desde": DESDE,
                          "hasta": HASTA, "qc": info_pol[RAMA_O3], "sha256": sha_obs[RAMA_O3], **comunes},
                         r.raiz_v2 / "paneles" / NOMBRE_OBS_O3.replace(".parquet", ".json"), r)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Paneles de la red ampliada (R11).")
    modo = ap.add_mutually_exclusive_group()
    modo.add_argument("--plan", action="store_true", help="inventario de insumos y conteos (por omisión; no escribe)")
    modo.add_argument("--medir", action="store_true", help="costo con una muestra pequeña, sin escribir")
    modo.add_argument("--ejecutar", action="store_true", help="congela los insumos y arma enlaces, satélites y paneles")
    modo.add_argument("--registrar-catalogo-maiac", action="store_true",
                      help="registra las teselas del catálogo MAIAC con su sha256 (T5, antes del armado)")
    ap.add_argument("--derivado", nargs="+", type=Path, help="raíz o raíces del derivado SINCA red 2")
    ap.add_argument("--contraste", type=Path, help="CSV de la segunda corrida del contraste de unidades")
    ap.add_argument("--contraste-sha256", default=None, help="huella del contraste (obligatoria con --ejecutar)")
    ap.add_argument("--veredictos", type=Path, help="veredictos.parquet de reloj_sinca_v2")
    ap.add_argument("--convencion-civil", choices=rs.CONVENCIONES, default=None,
                    help="opcional: confirma la convención civil que eligió reloj_sinca_v2 por T4 (no puede cambiarla)")
    ap.add_argument("--procesos", type=int, default=1)
    args = ap.parse_args(argv)
    r = rv.rutas_v2()
    ra.verificar_lista_cerrada(r.datos)
    filas = filas_estimadas(ra.series_contrato(r.datos))
    if args.medir:
        m = medir(r)
        total = {p: sum(v.values()) for p, v in filas.items() if p in CONTAMINANTES_PANEL}
        print(json.dumps({"medidas": m, "filas_estimadas": filas,
                          "proyeccion": proyectar(m, total, procesos=args.procesos)},
                         ensure_ascii=False, indent=1))
        return 0
    if args.registrar_catalogo_maiac:
        reg, sha, estado = registrar_catalogo_maiac(r)
        print(json.dumps({"estado": estado, "sha256": sha, "entran": reg["entran"], "fuera": reg["fuera"],
                          "huella_teselas": reg["huella_teselas"]}, ensure_ascii=False))
        return 0
    reg_maiac, _ = leer_registro_maiac(r)
    inv = inventario_insumos(r.datos, registro_maiac=reg_maiac)
    res = resumen_inventario(inv)
    if reg_maiac is None:
        previsto = registro_catalogo_maiac(r.datos)                # sólo se calcula: el registro lo escribe T5
        res["registro_catalogo_maiac_previsto"] = {k: previsto[k] for k in ("entran", "fuera", "huella_teselas")}
    print(json.dumps({"corte_utc": CORTE_INSUMOS_UTC, "insumos": res, "filas_estimadas": filas}, ensure_ascii=False,
                     indent=1))
    if not args.ejecutar:
        return 0
    return ejecutar(r, inv, args)


if __name__ == "__main__":
    sys.exit(main())
