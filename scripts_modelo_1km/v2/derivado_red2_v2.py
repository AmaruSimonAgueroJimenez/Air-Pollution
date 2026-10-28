#!/usr/bin/env python3
"""Derivado SINCA de la red ampliada (bloque R5): el mismo contrato y el mismo ranking, en una raíz aparte.

R5 conserva el contrato (``airpollution.sinca.modelado.v1.0.0``) y el ranking ``afg_lib`` del preparador original
``scripts_pipeline/preparar_sinca_modelado.py`` (sha256 95f1ecd3…), que queda intacto como procedencia. Desde la
autorización del 2026-10-28 (``red_ampliada_v2.DECISION_ESPACIO``), este módulo carga la copia explícita
``scripts_pipeline/preparar_sinca_modelado_red2.py`` por su propia huella y usa su API de orquestador
(``load_inputs``, ``consolidate`` y ``process_series``). Es un cambio operativo: reserva predeterminada de 1 GiB
(margen técnico, no cifra literal del autor) más el presupuesto pendiente, en lugar del mínimo rígido de 100 GiB.
Conserva los presupuestos dinámicos, montaje, UUID, integridad y publicación sin reemplazo; no cambia la raíz red 2.

Qué arma, por estación × contaminante (PM2,5, NO2 y O3):

* **estaciones actuales**: las filas del manifiesto sellado (``DATOS/sinca``) **y** las de la actualización
  (``…/actualizacion_configuradas``) en una sola serie, para que el ranking elija la fila ``seleccionada`` en las horas
  del solape (R4). La geometría es la de ``DATOS/sinca/estaciones_georreferenciadas.geojson`` (idéntica en la
  actualización);
* **estaciones nuevas**: las filas de la ampliación, con la geometría del maestro corregido de R8
  (``geometria_20261025/estaciones_georreferenciadas.geojson``, eaeaf965…), no la del 2026-10-24. Las estaciones sin
  coordenada usable en ese maestro (518, 408) no se derivan y se registran.

Las rutas relativas de cada fuente se toman desde la raíz de datos (``sinca/…`` o ``sinca_ampliacion_20261024/…``),
de modo que las filas de los dos orígenes no se confunden en la procedencia. El destino por omisión es
``derived/modelado/SINCA/v1_red2`` junto al derivado v1; la guarda rechaza el derivado v1, cualquier carpeta dentro de
él y la raíz de datos crudos.

Quien lo lee para escribir (el reloj, el contraste y el panel) lo exige completo (``exigir_derivado_completo``): esa
raíz y ninguna otra; su última corrida terminada y escrita por este programa (``plan.json`` con su huella rastreada);
las series de la red 2 con las versiones de esa corrida; y cada versión sin ventana (``since`` y ``until`` nulos), con
exactamente sus filas de los tres manifiestos de la lista cerrada, comparadas en todas sus columnas de identidad; con
tantas filas publicadas como filas declaran esos manifiestos y, archivo por archivo, las que declaró el preparador
(``statistics.filas_seleccionadas`` en ``observaciones.parquet`` y ``statistics.filas_alternativas_conservadas`` en
``solapamientos.parquet``); y con las etiquetas que deja el ranking afg (cada etiqueta válida una sola vez en
``observaciones.parquet`` y toda etiqueta de ``solapamientos.parquet`` también en ``observaciones.parquet``), leídas
sólo de ``ts_local``, como el reloj (``exigir_fuentes_y_ventana``). Un derivado auténtico pero parcial, con el contenido
recortado o con filas pasadas de un archivo al otro no pasa. Límite: una reescritura del contenido que conserve los
conteos de cada archivo y las etiquetas del ranking (otras etiquetas en el mismo número, otros valores u otras columnas)
sólo se detecta volviendo a derivar desde los CSV sellados; para esa auditoría el reloj registra el sha256 de cada
``observaciones.parquet`` (``reloj_sinca_v2.series_con_huella``), y quien lee lo comprueba al leer
(``reloj_sinca_v2.leer_serie``).

Uso::

    python -B scripts_modelo_1km/v2/derivado_red2_v2.py                  # plan (no escribe nada)
    python -B scripts_modelo_1km/v2/derivado_red2_v2.py --medir 3        # tiempo de consolidar 3 series, sin escribir
    python -B scripts_modelo_1km/v2/derivado_red2_v2.py --ejecutar       # publica el derivado (armado, R22 paso 3)
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
REPO = AQUI.parents[1]
sys.path.insert(0, str(AQUI))
import red_ampliada_v2 as ra  # noqa: E402

RUTA_PREPARADOR_ORIGINAL = REPO / "scripts_pipeline" / "preparar_sinca_modelado.py"
SHA_PREPARADOR_ORIGINAL = "95f1ecd3c9071f3877e858e0b822b4e525b00b49ab4aced8f0490a71d0a65401"
RUTA_PREPARADOR = REPO / "scripts_pipeline" / "preparar_sinca_modelado_red2.py"
SHA_PREPARADOR = "b1d134da9e447124f6c643c36346feb2ae4fb93a1db5a65fea17b106ff2b470a"
RESERVA_GIB = 1  # margen técnico autorizado por DECISION_ESPACIO, además del presupuesto dinámico
OVERHEAD_INICIO_BYTES = 2**20  # directorios, candado, temporales atómicos y progreso; además del plan serializado
RUTA_POLITICA = REPO / "config" / "sinca" / "politica_temporal.json"
RUTA_AFG = REPO / "scripts_superficie" / "afg_lib.py"
# T8 (decisiones_autor_traduccion_20261025.md, tras la segunda revisión): en R5, «la misma huella del ranking» es el
# sha256 del archivo afg_lib.py, igual al de la v1. Las huellas del árbol de sintaxis cambian con la versión de Python
# y quedan como procedencia.
SHA_AFG = "4391787a739915a1a96ff04ad0b2bbaf2f952449c89d01fc1aeec1d52b9db4c2"
PROCEDENCIA_AST_AFG = {
    "v1": {"python": "3.14.3", "ranking_ast_sha256": "8188ae3fe92c73e57bb8b4380b03e97ae7f2e4bb26c17e504c531a15c0976eec",
           "parser_ast_sha256": "3eff1519c8ed373cecde61009c0c0ee2e162cab360045829fdd5afb2e24661e0"},
    "amb_v2": {"python": "3.11.16",
               "ranking_ast_sha256": "877fb0f5d730dc0d17dca89da6f22f59b384165fac9f627690203d58acce9b86",
               "parser_ast_sha256": "04734f63b603a48f536046f2d620438e1ea44676d9de4786a14fda67c07bf582"},
}
SUBRUTA_V1 = ("modelado", "SINCA", "v1")
SUBRUTA_RED2 = ("modelado", "SINCA", "v1_red2")
CONTAMINANTES = ra.CONTAMINANTES
SCHEMA_PLAN = "airpollution.modelo-1km-v2.derivado-red2-plan.v1"
CONTRATO = "airpollution.sinca.modelado.v1.0.0"            # el del preparador (preparar_sinca_modelado.CONTRACT)
ESTADO_COMPLETO = "complete_for_selected_scope"            # el último progreso.json de una corrida que terminó
# T8 (y operacion.entorno de la configuración): el derivado red 2 corre en amb_v2, con su Python. El código lo exige al
# derivar (``verificar_afg``) y en quien lee cada versión (``contrato_de_la_version``); la huella del árbol de sintaxis
# sigue siendo sólo procedencia.
ENTORNO = {"nombre": "amb_v2", "python": PROCEDENCIA_AST_AFG["amb_v2"]["python"]}
# Los dos archivos de una versión publicada, en el orden de su manifest.json (``validate_publication``,
# preparar_sinca_modelado.py:394-395).
ARCHIVOS_DE_LA_VERSION = ("observaciones.parquet", "solapamientos.parquet")
# Las columnas de identidad de una fuente: las de su fila en los manifiestos de la lista cerrada, que cada versión copia
# en inputs.sources (el preparador toma desde, hasta y filas de esa fila, no del archivo: preparar_sinca_modelado.py:
# 252-253), y la ruta relativa a la raíz de datos.
CAMPOS_DE_LA_FUENTE = ("relative_path", "region", "estacion", "contaminante", "resolucion", "desde", "hasta", "bytes",
                       "filas", "sha256")


def digest_del_preparador(valor) -> str:
    """El ``digest`` de ``preparar_sinca_modelado.py`` (líneas 47-49), sólo sobre el json: el nombre de cada versión
    publicada es ``digest(inputs)`` de su manifiesto. Réplica para no ejecutar el preparador al leer; la prueba la
    compara con la del preparador cargado por su huella."""
    return hashlib.sha256(json.dumps(valor, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def verificar_entorno() -> dict:
    """T8: el derivado red 2 se arma en ``amb_v2`` (Python 3.11.16); si no, se detiene. Devuelve lo que se registra."""
    import platform

    nombre, version = Path(sys.prefix).name, platform.python_version()
    if (nombre, version) != (ENTORNO["nombre"], ENTORNO["python"]):
        raise SystemExit(f"el derivado red 2 corre en {ENTORNO['nombre']} (Python {ENTORNO['python']}), no en {nombre} "
                         f"(Python {version}) (T8)")
    return {"entorno": nombre, "python": version}


def cargar_preparador(ruta: Path = RUTA_PREPARADOR, sha256: str = SHA_PREPARADOR) -> types.ModuleType:
    """Carga la variante red 2 ejecutando exactamente los bytes con su propia huella exigida."""
    datos = Path(ruta).read_bytes()
    if hashlib.sha256(datos).hexdigest() != sha256:
        raise SystemExit(f"{Path(ruta).name} no tiene la huella fijada ({sha256[:8]}…); el derivado red 2 no se arma")
    modulo = types.ModuleType("preparar_sinca_modelado_red2_fijado")
    modulo.__file__ = str(ruta)
    exec(compile(datos, str(ruta), "exec"), modulo.__dict__)
    if hashlib.sha256(Path(ruta).read_bytes()).hexdigest() != sha256:
        raise SystemExit(f"{Path(ruta).name} cambió durante la carga")
    return modulo


def verificar_afg(semantics: dict) -> dict:
    """T8: el ``afg_lib.py`` que carga el preparador tiene que ser el de la v1 (``SHA_AFG``). Devuelve la procedencia
    que se registra: las huellas del archivo y del árbol de sintaxis de esta corrida, con el entorno y la versión de
    Python, y las de referencia (v1 y ``amb_v2``). El entorno se exige (``verificar_entorno``: amb_v2); las huellas del
    árbol de sintaxis, no (T8: son procedencia)."""
    if semantics.get("file_sha256") != SHA_AFG:
        raise SystemExit(f"afg_lib.py no es el de la v1 (sha256 {str(semantics.get('file_sha256'))[:8]}…, se exige "
                         f"{SHA_AFG[:8]}…): el derivado red 2 no se arma (T8)")
    entorno = verificar_entorno()
    return {"regla": "T8: rige el sha256 del archivo; el derivado corre en amb_v2", "file_sha256": SHA_AFG,
            "esta_corrida": {**entorno, "ranking_ast_sha256": semantics.get("ranking_ast_sha256"),
                             "parser_ast_sha256": semantics.get("parser_ast_sha256")},
            "referencias_ast": PROCEDENCIA_AST_AFG}


def contrato_de_la_version(observaciones: Path, sha256_observaciones: str | None = None) -> dict:
    """T8 y R5 en quien lee el derivado (el reloj, el contraste y el panel), antes de usar una serie:

    * el ``manifest.json`` de la versión elegida declara el contrato del preparador, el ``afg_lib.py`` de la v1
      (``SHA_AFG``), el preparador sellado (``SHA_PREPARADOR``) y el Python de ``amb_v2`` (T8: el derivado corre en
      amb_v2);
    * y es la publicación que hizo el preparador, con las comprobaciones de su ``validate_publication``
      (``preparar_sinca_modelado.py``, líneas 384-412) que no leen valores, sólo metadatos: ``files`` nombra
      ``observaciones.parquet`` y ``solapamientos.parquet``, en ese orden; el sha256 de cada uno calza (el de
      ``observaciones.parquet`` es ``sha256_observaciones``; si no se da, se calcula); sus filas
      (``pyarrow.parquet.read_metadata``) son las de ``files[].rows`` y la huella de su esquema
      (``pyarrow.parquet.read_schema``) es ``files[].schema_sha256``; ``version`` es el nombre de la carpeta
      ``version=…`` y es ``digest(inputs)``; y la estación y el contaminante de ``inputs`` son los de la carpeta.

    ``files`` y ``statistics`` quedan fuera de ``digest(inputs)``: una versión con los ``inputs`` del derivado completo
    y un parquet recortado, o con filas pasadas de un archivo al otro, con su sha256 al día pasa estas comprobaciones; la
    detiene ``exigir_fuentes_y_ventana``, que ancla el conteo de filas en los manifiestos de la lista cerrada, cada
    archivo en lo que declaró el preparador y las etiquetas en el ranking. Si algo no calza, la serie no se lee. Devuelve la
    procedencia que se registra por serie: la sintaxis de ``afg_lib`` con la versión de Python de la corrida."""
    observaciones = Path(observaciones)
    mani = observaciones.parent / "manifest.json"
    nombre = "/".join(observaciones.parts[-4:-1])
    try:
        m = json.loads(mani.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"{nombre}: sin manifest.json legible ({type(e).__name__}): no es una versión del preparador")
    inp = m.get("inputs") if isinstance(m.get("inputs"), dict) else {}
    afg = inp.get("afg_semantics") if isinstance(inp.get("afg_semantics"), dict) else {}
    if m.get("contract") != CONTRATO or inp.get("contract", CONTRATO) != CONTRATO:
        raise SystemExit(f"{nombre}: el manifiesto no declara el contrato {CONTRATO}")
    if afg.get("file_sha256") != SHA_AFG:
        raise SystemExit(f"{nombre}: afg_lib.py no es el de la v1 (T8: se exige {SHA_AFG[:8]}…, el manifiesto dice "
                         f"{str(afg.get('file_sha256'))[:8]}…)")
    if inp.get("code_sha256") != SHA_PREPARADOR:
        raise SystemExit(f"{nombre}: no la publicó el preparador sellado (se exige {SHA_PREPARADOR[:8]}…, el "
                         f"manifiesto dice {str(inp.get('code_sha256'))[:8]}…)")
    runtime = inp.get("runtime") if isinstance(inp.get("runtime"), dict) else {}
    python = str(runtime.get("python", "")).split(" ")[0] or None
    if python != ENTORNO["python"]:
        raise SystemExit(f"{nombre}: se armó con Python {python}, no con el de {ENTORNO['nombre']} "
                         f"({ENTORNO['python']}): el derivado red 2 corre en {ENTORNO['nombre']} (T8)")
    sha = sha256_observaciones or hashlib.sha256(observaciones.read_bytes()).hexdigest()
    declarado = [f.get("sha256") for f in (m.get("files") or []) if isinstance(f, dict)
                 and f.get("name") == "observaciones.parquet"]
    if declarado != [sha]:
        raise SystemExit(f"{nombre}: observaciones.parquet no es el que publicó el preparador (su manifest.json declara "
                         f"{[str(x)[:8] for x in declarado]}, el archivo es {sha[:8]}…)")
    archivos = [f for f in (m.get("files") or []) if isinstance(f, dict)]
    if [f.get("name") for f in archivos] != list(ARCHIVOS_DE_LA_VERSION):
        raise SystemExit(f"{nombre}: el manifest.json declara los archivos {[f.get('name') for f in archivos]}, no los "
                         f"dos de una publicación del preparador {list(ARCHIVOS_DE_LA_VERSION)}: no es el que publicó el "
                         f"preparador")
    import pyarrow.parquet as pq
    for f in archivos:
        p = observaciones.parent / f["name"]
        real = sha if f["name"] == ARCHIVOS_DE_LA_VERSION[0] else (
            hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None)
        if real is None or f.get("sha256") != real:
            raise SystemExit(f"{nombre}: {f['name']} no es el que publicó el preparador (su manifest.json declara "
                             f"{str(f.get('sha256'))[:8]}…, el archivo es {str(real)[:8]}…)")
        try:
            filas = pq.read_metadata(p).num_rows
            esquema = hashlib.sha256(pq.read_schema(p).serialize().to_pybytes()).hexdigest()
        except Exception as e:                                   # noqa: BLE001 (un parquet ilegible no se lee)
            raise SystemExit(f"{nombre}: {f['name']} no es un parquet legible ({type(e).__name__})")
        if filas != f.get("rows"):
            raise SystemExit(f"{nombre}: {f['name']} tiene {filas} filas y su manifest.json declara {f.get('rows')!r}")
        if esquema != f.get("schema_sha256"):
            raise SystemExit(f"{nombre}: el esquema de {f['name']} no es el que declara su manifest.json "
                             f"(schema_sha256 {str(f.get('schema_sha256'))[:8]}…, el archivo {esquema[:8]}…)")
    carpeta = observaciones.parent.name.split("=", 1)[-1]
    if m.get("version") != carpeta:
        raise SystemExit(f"{nombre}: el manifest.json declara la versión {str(m.get('version'))[:8]}…, no la de su "
                         f"carpeta ({carpeta[:8]}…)")
    try:
        identidad = digest_del_preparador(inp)
    except (TypeError, ValueError):
        identidad = None
    if identidad != carpeta:
        raise SystemExit(f"{nombre}: la identidad de la publicación está alterada (digest(inputs) no es la versión)")
    est, pol = observaciones.parts[-4].split("=", 1)[-1], observaciones.parts[-3].split("=", 1)[-1]
    if (inp.get("station"), inp.get("pollutant")) != (est, pol):
        raise SystemExit(f"{nombre}: el manifest.json es de {inp.get('station')} {inp.get('pollutant')}, no de la "
                         f"carpeta")
    return {"python": python, "ranking_ast_sha256": afg.get("ranking_ast_sha256"),
            "parser_ast_sha256": afg.get("parser_ast_sha256")}


def leer_corrida(raiz: Path, nombre: str | None) -> dict:
    """Una corrida del derivado red 2 (``_runs/<nombre>``) y su ``progreso.json``: {corrida, status, versiones:
    {(estación, contaminante): versión}}. Si no existe, status None."""
    import re
    carpeta = Path(raiz) / "_runs" / str(nombre) if nombre else None
    if carpeta is None or not carpeta.is_dir() or not str(nombre).endswith("-red2"):
        return {"corrida": nombre, "status": None, "versiones": {}}
    try:
        prog = json.loads((carpeta / "progreso.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        prog = {}
    versiones = {}
    for x in prog.get("results") or []:
        m = re.search(r"estacion=([^/]+)/contaminante=([^/]+)/version=([^/]+)$", str(x.get("path", "")))
        if m:
            versiones[(m.group(1), m.group(2))] = m.group(3)
    return {"corrida": carpeta.name, "status": prog.get("status"), "versiones": versiones}


def ultima_corrida(raiz: Path) -> dict:
    """La última corrida del derivado red 2 (``_runs/<marca>-red2``, por su marca) y su ``progreso.json``: {corrida,
    status, versiones: {(estación, contaminante): versión}}. Sin corridas, status None."""
    corridas = sorted(q for q in (Path(raiz) / "_runs").glob("*-red2") if q.is_dir())
    if not corridas:
        return {"corrida": None, "status": None, "versiones": {}}
    return leer_corrida(raiz, corridas[-1].name)


def corridas_equivalentes(raiz: Path, una: str | None, otra: str | None, versiones: dict) -> bool:
    """Cuarta revisión, menores 5 y 32: dos corridas del derivado son «la misma» si las dos terminaron y publicaron
    exactamente las mismas versiones, que son ``versiones`` ({(estación, contaminante): versión}). Pasa cuando el
    derivado se vuelve a correr sin cambios: el preparador reabre las mismas versiones («reused») en otra corrida."""
    a, b = leer_corrida(raiz, una), leer_corrida(raiz, otra)
    return (a["status"] == b["status"] == ESTADO_COMPLETO and a["versiones"] == b["versiones"] == dict(versiones)
            and bool(versiones))


PROGRAMA = "scripts_modelo_1km/v2/derivado_red2_v2.py"     # como lo registra plan.json (plan_con_procedencia)


def huella_del_programa() -> str:
    """sha256 de este archivo tal como corre. Quien lee el derivado para escribir (el reloj, el contraste y el panel)
    pasa antes por la compuerta de R22 (``red_ampliada_v2.exigir_traduccion_confirmada``), que exige este archivo
    rastreado y sin cambios en AP y en el espejo: es la huella rastreada en git."""
    return ra.sha256_archivo(Path(__file__).resolve())


def identidad_de_la_fuente(fila: dict) -> tuple[str, ...]:
    """Las columnas de identidad de una fuente (``CAMPOS_DE_LA_FUENTE``), como texto y sin convertir los vacíos; un
    campo que falta queda como «(falta)»."""
    return tuple("(falta)" if fila.get(c) is None else str(fila.get(c)) for c in CAMPOS_DE_LA_FUENTE)


def fuentes_de_la_red_2(datos: Path) -> dict[tuple[str, str], set[tuple[str, ...]]]:
    """R2, R4 y T4: las fuentes que tiene que declarar cada versión del derivado de la red 2. Por estación ×
    contaminante, la identidad completa (``CAMPOS_DE_LA_FUENTE``: región, estación, contaminante, resolución, desde,
    hasta, bytes, filas, sha256 y la ruta relativa a la raíz de datos, como la escribe ``insumos_red2``) de sus filas en
    los tres manifiestos de la lista cerrada (``sinca/manifiesto_descarga.csv``, el de la actualización y el de la
    ampliación; ``red_ampliada_v2.series_contrato`` leído como texto, sólo columnas de identidad). Una fila cuya ruta no
    está bajo la raíz de datos detiene (``load_inputs`` tampoco la aceptaría)."""
    datos = Path(datos).resolve()
    s = ra.series_contrato(datos, texto=True)
    out: dict[tuple[str, str], set[tuple[str, ...]]] = {}
    fuera = []
    for fila in s.to_dict("records"):
        e, p = fila["estacion"], fila["contaminante"]
        q = Path(str(fila["ruta"])).resolve()
        if not q.is_relative_to(datos):
            fuera.append(f"{e}:{p}")
            continue
        out.setdefault((str(e), str(p)), set()).add(identidad_de_la_fuente({**fila,
                                                                            "relative_path": str(q.relative_to(datos))}))
    if fuera:
        raise SystemExit(f"{len(fuera)} filas de los manifiestos de la red 2 apuntan fuera de la raíz de datos: "
                         f"{sorted(set(fuera))[:10]}")
    return out


def exigir_plan_de_la_corrida(raiz: Path, corrida: str, quien: str) -> dict:
    """El ``plan.json`` de la corrida que se lee lo escribió este programa (``plan_con_procedencia``): declara
    ``codigo.programa`` = ``PROGRAMA`` y ``codigo.sha256`` = la huella rastreada de este archivo
    (``huella_del_programa``). Si no, se detiene. Devuelve lo que se registra."""
    ruta = Path(raiz) / "_runs" / str(corrida) / "plan.json"
    try:
        plan = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"{quien}: la corrida {corrida} del derivado no tiene un plan.json legible "
                         f"({type(e).__name__}): no la escribió derivado_red2_v2 --ejecutar")
    codigo = plan.get("codigo") if isinstance(plan, dict) and isinstance(plan.get("codigo"), dict) else {}
    propia = huella_del_programa()
    if (codigo.get("programa"), codigo.get("sha256")) != (PROGRAMA, propia):
        raise SystemExit(f"{quien}: el plan.json de la corrida {corrida} no trae la huella rastreada de {PROGRAMA} "
                         f"(declara {codigo.get('programa')!r} con {str(codigo.get('sha256'))[:8]}…; se exige "
                         f"{propia[:8]}…)")
    return {"programa": PROGRAMA, "sha256": propia, "plan_sha256": ra.sha256_archivo(ruta)}


def exigir_fuentes_y_ventana(series: list[dict], datos: Path, quien: str) -> dict:
    """R2, R4 y T4: cada versión que se lee se armó con todo lo de la lista cerrada, tal como está, y sin recorte. Su
    ``manifest.json`` declara ``inputs.since`` e ``inputs.until`` nulos (sin ventana: R4 pide el período completo); cada
    fila de ``inputs.sources`` es, en todas sus columnas de identidad (``CAMPOS_DE_LA_FUENTE``, como texto), una de sus
    filas en los tres manifiestos (``fuentes_de_la_red_2``), y están todas, sin repetidos (el preparador toma desde,
    hasta y filas de la fila que recibe, no del archivo, y el ranking afg desempata por ellas: una fila con otro «hasta»
    y la misma ruta y sha256 cambia la fila seleccionada en los solapes, contra R4 y R5); y el contenido está anclado a
    esos manifiestos por los conteos, sólo con metadatos: las filas publicadas (``observaciones.parquet`` más
    ``solapamientos.parquet``, ``pyarrow.parquet.read_metadata``) son ``statistics.filas_en_ventana``,
    ``statistics.filas_originales_leidas`` y la suma de la columna «filas» de sus filas en los manifiestos; y, archivo
    por archivo (ronda 5 de la traducción, menor 2), las de ``observaciones.parquet`` son
    ``statistics.filas_seleccionadas`` y las de ``solapamientos.parquet``, ``statistics.filas_alternativas_conservadas``.
    Como ``statistics`` queda fuera de ``digest(inputs)``, se exige además lo que deja el ranking afg
    (``afg_lib.py:320-324``, ``drop_duplicates(["estacion", "ts_local"], keep="last")``; el preparador marca
    seleccionada toda fila sin etiqueta válida, ``preparar_sinca_modelado.py:306``), leyendo sólo ``ts_local`` (etiquetas,
    como el reloj, ningún valor; ``invariante_del_ranking``): cada etiqueta válida aparece una sola vez en
    ``observaciones.parquet`` y toda fila de ``solapamientos.parquet`` tiene una etiqueta válida que está en
    ``observaciones.parquet``. Un derivado auténtico pero parcial (grupos filtrados, ``until``), con el contenido
    recortado o con filas pasadas de ``observaciones.parquet`` a ``solapamientos.parquet`` (el total no cambia) cambia
    las etiquetas que ve el reloj, y con ellas la elección de T4. Si algo no calza, se detiene mostrando la diferencia.
    Límite declarado: una reescritura del contenido que conserve los conteos de cada archivo y las etiquetas del ranking
    (otras etiquetas en el mismo número, otros valores u otras columnas) sólo se detecta volviendo a derivar desde los
    CSV sellados (el reloj registra el sha256 de cada ``observaciones.parquet`` para esa auditoría). Devuelve lo que se
    registra."""
    import pyarrow.parquet as pq

    esperadas = fuentes_de_la_red_2(datos)
    i_ruta, i_filas = CAMPOS_DE_LA_FUENTE.index("relative_path"), CAMPOS_DE_LA_FUENTE.index("filas")
    malas, archivos, filas_total = [], 0, 0
    for s in series:
        clave = (str(s["estacion"]), str(s["contaminante"]))
        nombre = f"{clave[0]}:{clave[1]}"
        carpeta = Path(s["ruta"]).parent
        mani = carpeta / "manifest.json"
        try:
            m = json.loads(mani.read_text(encoding="utf-8"))
            inp = m.get("inputs")
        except (OSError, ValueError, AttributeError):
            m, inp = {}, None
        if not isinstance(inp, dict):
            malas.append(f"{nombre}: sin inputs legibles en su manifest.json")
            continue
        for campo in ("since", "until"):
            if campo not in inp or inp[campo] is not None:
                malas.append(f"{nombre}: inputs.{campo} = {inp.get(campo, '(falta)')!r}, no null (R4: sin ventana)")
        fuentes = inp.get("sources")
        if not isinstance(fuentes, list) or not all(isinstance(x, dict) for x in fuentes):
            malas.append(f"{nombre}: inputs.sources no es una lista de filas")
            continue
        declaradas = [identidad_de_la_fuente(x) for x in fuentes]
        archivos += len(declaradas)
        esperado = esperadas.get(clave, set())
        faltan = sorted(esperado - set(declaradas))
        sobran = sorted(set(declaradas) - esperado)
        repetidas = len(declaradas) - len(set(declaradas))
        if faltan or sobran or repetidas:
            de_la_lista = {t[i_ruta]: t for t in esperado}
            distintos = []
            for t in sobran:                                     # la misma ruta con otra identidad: qué campo cambió
                e = de_la_lista.get(t[i_ruta])
                if e is not None:
                    campos = [f"{c}: {a!r} en la lista cerrada, {b!r} en el derivado"
                              for c, a, b in zip(CAMPOS_DE_LA_FUENTE, e, t) if a != b]
                    distintos.append(f"{Path(t[i_ruta]).name} ({'; '.join(campos)})")
            malas.append(f"{nombre}: fuentes distintas de las de la lista cerrada: faltan {len(faltan)} "
                         f"{[t[i_ruta] for t in faltan][:3]}; sobran {len(sobran)} {[t[i_ruta] for t in sobran][:3]}; "
                         f"repetidas {repetidas}" + (f"; campos distintos: {' | '.join(distintos[:3])}" if distintos
                                                     else ""))
        # R4 y R2: el contenido, anclado a los manifiestos de la lista cerrada por los conteos (sólo metadatos)
        try:
            de_la_lista = sum(int(t[i_filas]) for t in esperado)
        except ValueError:
            de_la_lista = None
        try:
            por_archivo = {n: int(pq.read_metadata(carpeta / n).num_rows) for n in ARCHIVOS_DE_LA_VERSION}
            publicadas = sum(por_archivo.values())
        except Exception as e:                                   # noqa: BLE001 (sin los dos parquet no hay conteo)
            por_archivo, publicadas = None, f"ilegible ({type(e).__name__})"
        est = m.get("statistics") if isinstance(m.get("statistics"), dict) else {}
        if por_archivo is not None:                              # archivo por archivo, lo que declaró el preparador
            for n, campo in ESTADISTICA_DE_CADA_ARCHIVO.items():
                if str(por_archivo[n]) != str(est.get(campo)):
                    malas.append(f"{nombre}: {n} tiene {por_archivo[n]} filas y statistics.{campo} declara "
                                 f"{est.get(campo)!r}: las filas de cada archivo tienen que ser las que declaró el "
                                 f"preparador (R4)")
            ranking = invariante_del_ranking(carpeta)
            if ranking:
                malas.append(f"{nombre}: {ranking}")
        conteos = (publicadas, est.get("filas_en_ventana"), est.get("filas_originales_leidas"), de_la_lista)
        if de_la_lista is None or len(set(map(str, conteos))) != 1:
            malas.append(f"{nombre}: filas publicadas (observaciones y solapamientos) {publicadas}, "
                         f"statistics.filas_en_ventana {est.get('filas_en_ventana')!r}, "
                         f"statistics.filas_originales_leidas {est.get('filas_originales_leidas')!r} y filas de sus filas "
                         f"en la lista cerrada {de_la_lista!r}: tienen que ser iguales (R4: el período completo, sin "
                         f"recortes)")
        elif isinstance(publicadas, int):
            filas_total += publicadas
    if malas:
        raise SystemExit(f"{quien}: {len(malas)} diferencias entre el derivado y la lista cerrada (R2, R4): "
                         f"{malas[:10]}")
    return {"series": len(series), "archivos": archivos, "filas": filas_total,
            "regla": "inputs.since y inputs.until nulos; inputs.sources = las filas de la serie en los tres "
                     "manifiestos de la lista cerrada, en todas sus columnas de identidad (CAMPOS_DE_LA_FUENTE, como "
                     "texto); filas publicadas = statistics.filas_en_ventana = statistics.filas_originales_leidas = "
                     "Σ filas de la lista cerrada; filas de observaciones.parquet = statistics.filas_seleccionadas y de "
                     "solapamientos.parquet = statistics.filas_alternativas_conservadas; ranking afg: cada etiqueta "
                     "válida una vez en observaciones.parquet y las de solapamientos.parquet, válidas y en "
                     "observaciones.parquet (sólo ts_local) (R2, R4)"}


# Lo que el preparador declara de cada archivo de una versión (``consolidate``, preparar_sinca_modelado.py:343-344).
ESTADISTICA_DE_CADA_ARCHIVO = {"observaciones.parquet": "filas_seleccionadas",
                               "solapamientos.parquet": "filas_alternativas_conservadas"}


def invariante_del_ranking(carpeta: Path) -> str | None:
    """Lo que deja el ranking afg en una versión publicada, leyendo sólo la columna ``ts_local`` de sus dos parquet
    (etiquetas, como el reloj; ningún valor): el ranking (``afg_lib.py:320-324``) deja, por etiqueta válida, una sola
    fila seleccionada, y el preparador marca seleccionada toda fila sin etiqueta válida
    (``preparar_sinca_modelado.py:306``), así que cada etiqueta válida aparece una sola vez en ``observaciones.parquet``
    y toda fila de ``solapamientos.parquet`` tiene una etiqueta válida que también está en ``observaciones.parquet``.
    Devuelve None si se cumple o la diferencia, para mostrarla."""
    import pyarrow.parquet as pq

    try:
        sel = pq.read_table(Path(carpeta) / ARCHIVOS_DE_LA_VERSION[0], columns=["ts_local"]).column(0).to_pandas()
        alt = pq.read_table(Path(carpeta) / ARCHIVOS_DE_LA_VERSION[1], columns=["ts_local"]).column(0).to_pandas()
    except Exception as e:                                       # noqa: BLE001 (sin etiquetas no hay ranking)
        return f"las etiquetas (ts_local) de sus dos parquet no se pueden leer ({type(e).__name__})"
    validas = sel.dropna()
    repetidas = int(validas.duplicated().sum())
    sin_etiqueta = int(alt.isna().sum())
    ajenas = int((~alt.dropna().isin(validas)).sum())
    if repetidas or sin_etiqueta or ajenas:
        return (f"las etiquetas no son las que deja el ranking afg: {repetidas} etiquetas repetidas en "
                f"{ARCHIVOS_DE_LA_VERSION[0]}, {ajenas} filas de {ARCHIVOS_DE_LA_VERSION[1]} con etiquetas que no están en "
                f"{ARCHIVOS_DE_LA_VERSION[0]} y {sin_etiqueta} sin etiqueta (el ranking deja una fila seleccionada por "
                f"etiqueta válida y sólo alternativas de esas etiquetas; R4 y R5)")
    return None


def exigir_derivado_completo(raices, series: list[dict], datos: Path, quien: str) -> dict:
    """R2, R4 y R5 en quien lee el derivado para escribir (el reloj, el contraste y el panel): una sola raíz, la de
    ``destino_por_omision(datos)``; su última corrida terminó (``progreso.json`` en «complete_for_selected_scope») y la
    escribió este programa (``plan.json`` con su huella rastreada: ``exigir_plan_de_la_corrida``); el conjunto estación
    × contaminante que se lee es el de la red 2 (``red_ampliada_v2.series_esperadas_red2``); la versión de cada serie
    es la que publicó esa corrida; y cada versión se armó sin ventana y con exactamente sus filas de los tres
    manifiestos (``exigir_fuentes_y_ventana``; ronda 3 de la traducción, mayor). Si no, se detiene mostrando la
    diferencia. Devuelve lo que se registra."""
    raices = [Path(x) for x in raices]
    if len(raices) != 1:
        raise SystemExit(f"{quien}: la red 2 tiene un solo derivado (una raíz), no {len(raices)}")
    esperada = destino_por_omision(datos).resolve()
    if raices[0].resolve() != esperada:
        raise SystemExit(f"{quien}: el derivado de la red 2 es derived/{'/'.join(SUBRUTA_RED2)} junto a la raíz de "
                         f"datos (destino_por_omision), no {raiz_portable(raices[0], datos)}")
    corrida = ultima_corrida(raices[0])
    if corrida["status"] != ESTADO_COMPLETO:
        raise SystemExit(f"{quien}: la última corrida del derivado ({corrida['corrida']}) no terminó: su progreso.json "
                         f"dice {corrida['status']!r}, no {ESTADO_COMPLETO!r}")
    plan = exigir_plan_de_la_corrida(raices[0], corrida["corrida"], quien)
    vistas = {(s["estacion"], s["contaminante"]) for s in series}
    red = ra.exigir_la_red_2(vistas, ra.series_esperadas_red2(datos), quien)
    leidas = {(s["estacion"], s["contaminante"]): Path(s["ruta"]).parent.name.split("=", 1)[1] for s in series}
    otras = sorted(f"{e}:{p}" for (e, p), v in leidas.items() if corrida["versiones"].get((e, p)) != v)
    if otras:
        raise SystemExit(f"{quien}: {len(otras)} series no tienen la versión que publicó la última corrida del derivado "
                         f"({corrida['corrida']}): {otras[:10]}")
    fuentes = exigir_fuentes_y_ventana(series, datos, quien)
    return {**red, "corrida": corrida["corrida"], "estado_de_la_corrida": corrida["status"], "plan": plan,
            "fuentes": fuentes}


def raiz_portable(raiz: Path, datos: Path, partes: int = 4) -> str:
    """Una raíz para los mensajes, sin rutas absolutas: relativa a la carpeta que contiene la raíz de datos
    (``derived/…``); si no está debajo, «fuera de la carpeta de la raíz de datos: …/» con sus ``partes`` últimos
    componentes (ronda 5 de la traducción, menor 30: con sólo el nombre, la raíz rechazada y la esperada se veían
    iguales)."""
    p, base = Path(raiz).resolve(), Path(datos).resolve().parent
    if p.is_relative_to(base):
        return p.relative_to(base).as_posix()
    cola = [x for x in p.parts if x != p.anchor][-int(partes):]
    return "fuera de la carpeta de la raíz de datos: …/" + "/".join(cola)


def raiz_derivados(datos: Path) -> Path:
    """``derived`` junto a la raíz de datos (``_comun_modelo.py:66``)."""
    return Path(datos).resolve().parent / "derived"


def destino_por_omision(datos: Path) -> Path:
    return raiz_derivados(datos).joinpath(*SUBRUTA_RED2)


def verificar_destino(salida: Path, datos: Path) -> Path:
    """Exige la única raíz registrada; además protege el derivado v1 y los datos crudos antes de escribir."""
    s = Path(salida).resolve()
    v1 = raiz_derivados(datos).joinpath(*SUBRUTA_V1).resolve()
    crudos = Path(datos).resolve()
    for nombre, otra in (("el derivado v1", v1), ("los datos crudos", crudos)):
        if s == otra or s.is_relative_to(otra) or otra.is_relative_to(s):
            raise SystemExit(f"El derivado red 2 no puede escribirse en {nombre} ({otra})")
    if s != destino_por_omision(datos).resolve():
        raise SystemExit('El derivado red 2 exige la raíz registrada derived/modelado/SINCA/v1_red2; '
                         'no se escribe una salida alternativa')
    return s


def _features_geojson(ruta: Path) -> tuple[dict, bytes]:
    contenido = Path(ruta).read_bytes()
    geo = json.loads(contenido)
    out = {}
    for f in geo["features"]:
        code = str(f["properties"]["estacion"])
        if code in out:
            raise ValueError(f"estación geográfica duplicada en {Path(ruta).name}: {code}")
        out[code] = f
    return out, contenido


def insumos_red2(prep: types.ModuleType, datos: Path) -> dict:
    """Insumos del preparador para las dos familias de series.

    Devuelve {"actual": inputs, "nueva": inputs, "grupos": {(estación, contaminante): (familia, filas)},
    "excluidas": [...]} donde cada ``inputs`` es el de ``load_inputs`` con la geometría que corresponde y ``source`` =
    la raíz de datos (común a los dos orígenes de las actuales)."""
    datos = Path(datos).resolve()
    sinca = datos / "sinca"
    act = datos / ra.ACT
    amp = datos / ra.AMP
    base_act = prep.load_inputs(sinca, RUTA_POLITICA, RUTA_AFG)
    base_upd = prep.load_inputs(act, RUTA_POLITICA, RUTA_AFG)
    base_new = prep.load_inputs(amp, RUTA_POLITICA, RUTA_AFG)
    if base_act["semantics"] != base_new["semantics"] or base_act["semantics"] != base_upd["semantics"]:
        raise ValueError("el ranking afg_lib no es el mismo en las tres cargas")
    verificar_afg(base_act["semantics"])
    if base_upd["hashes"]["geometry"] != base_act["hashes"]["geometry"]:
        raise ValueError("la geometría de la actualización no es la de DATOS/sinca (R2 exige que sean idénticas)")
    geo_new, bytes_new = _features_geojson(datos / ra.GEOJSON_NUEVAS)
    inputs_act = dict(base_act)
    inputs_act["source"] = datos
    inputs_new = dict(base_new)
    inputs_new["source"] = datos
    inputs_new["geometry"] = geo_new
    inputs_new["hashes"] = {**base_new["hashes"], "geometry": hashlib.sha256(bytes_new).hexdigest()}
    inputs_new["frozen_files"] = {**base_new["frozen_files"], "estaciones_georreferenciadas.geojson": bytes_new}

    def relativas(filas, raiz):
        out = []
        for f in filas:
            g = copy.deepcopy(f)
            g["relative_path"] = str(Path(f["ruta"]).resolve().relative_to(datos))
            g["origen_red2"] = raiz
            out.append(g)
        return out

    grupos: dict[tuple[str, str], tuple[str, list]] = {}
    for fam, base, origen in (("actual", base_act, "sellado"), ("actual", base_upd, "actualizacion"),
                              ("nueva", base_new, "ampliacion")):
        for f in relativas(base["rows"], origen):
            if f["contaminante"] not in CONTAMINANTES:
                continue
            clave = (f["estacion"], f["contaminante"])
            if clave in grupos and grupos[clave][0] != fam:
                raise ValueError(f"{clave}: la misma serie en actuales y nuevas")
            grupos.setdefault(clave, (fam, []))[1].append(f)
    excluidas = []
    for clave in sorted(grupos):
        fam, _ = grupos[clave]
        geo = inputs_new["geometry"] if fam == "nueva" else inputs_act["geometry"]
        if clave[0] not in geo:
            excluidas.append({"estacion": clave[0], "contaminante": clave[1],
                              "motivo": "sin coordenada usable en el maestro de R8"})
    for e in excluidas:
        grupos.pop((e["estacion"], e["contaminante"]))
    for clave, (fam, filas) in grupos.items():
        filas.sort(key=lambda r: r["relative_path"])
    return {"actual": inputs_act, "nueva": inputs_new, "grupos": grupos, "excluidas": excluidas}


def plan(ins: dict) -> dict:
    """Series a derivar (sin escribir): conteos por contaminante y familia."""
    series = [{"estacion": e, "contaminante": p, "familia": fam, "archivos": len(filas),
               "origenes": sorted({f["origen_red2"] for f in filas})}
              for (e, p), (fam, filas) in sorted(ins["grupos"].items())]
    conteo: dict = {}
    for s in series:
        conteo.setdefault(s["contaminante"], {}).setdefault(s["familia"], 0)
        conteo[s["contaminante"]][s["familia"]] += 1
    return {"schema": SCHEMA_PLAN, "series": len(series), "por_contaminante": conteo,
            "excluidas": ins["excluidas"], "detalle": series,
            "geometria_actuales_sha256": ins["actual"]["hashes"]["geometry"],
            "geometria_nuevas_sha256": ins["nueva"]["hashes"]["geometry"],
            "ranking_afg": verificar_afg(ins["actual"]["semantics"])}


def medir(prep: types.ModuleType, ins: dict, claves: list[tuple[str, str]]) -> list[dict]:
    """Tiempo de ``consolidate`` (lectura, ranking y tabla Arrow) de algunas series, sin escribir nada."""
    out = []
    for clave in claves:
        fam, filas = ins["grupos"][clave]
        t0 = time.perf_counter()
        sel, alt, stats = prep.consolidate(filas, ins[fam])
        out.append({"estacion": clave[0], "contaminante": clave[1], "familia": fam, "archivos": len(filas),
                    "filas_leidas": int(stats["filas_originales_leidas"]), "segundos": round(time.perf_counter() - t0, 2)})
    return out


def plan_con_procedencia(ins: dict, r, compuerta: dict | None) -> dict:
    """``plan.json`` de una corrida: el plan sin el detalle, la huella de este programa (que reemplaza la geometría de
    ``load_inputs``, §8.2 de la propuesta) y de ``red_ampliada_v2``, y la procedencia (``red_ampliada_v2.traza_red2``:
    commit, código, bibliotecas, hilos y la traducción). El entorno (T8: amb_v2) va en ``ranking_afg.esta_corrida``
    (quinta revisión, mayor 1)."""
    p = {k: v for k, v in plan(ins).items() if k != "detalle"}
    p["codigo"] = {"programa": PROGRAMA, "sha256": huella_del_programa(),
                   "red_ampliada_v2_sha256": ra.sha256_archivo(Path(ra.__file__).resolve()),
                   "preparador": str(RUTA_PREPARADOR.relative_to(REPO)), "preparador_sha256": SHA_PREPARADOR,
                   "preparador_original": {"programa": str(RUTA_PREPARADOR_ORIGINAL.relative_to(REPO)),
                                           "sha256": SHA_PREPARADOR_ORIGINAL},
                   "politica_espacio": {"reserva_gib_por_omision": RESERVA_GIB,
                                        "regla": "reserva más pending_bytes; presupuestos dinámicos sin cambios",
                                        "inicio_corrida": "bytes JSON UTF-8 del plan, incluido salto final, más overhead",
                                        "overhead_inicio_bytes": OVERHEAD_INICIO_BYTES,
                                        "autoridad": ra.DECISION_ESPACIO}}
    p["traza"] = ra.traza_red2(r, compuerta, {"politica_temporal": RUTA_POLITICA, "afg_lib": RUTA_AFG}, None, 1,
                               programa="derivado_red2_v2 --ejecutar")
    return p


def presupuesto_inicio_corrida(plan_corrida: dict) -> int:
    """Bytes exactos del JSON que escribe json_atomic y margen pequeño para el resto de la escritura inicial.

    Se calcula antes del primer mkdir/candado. No sustituye la reserva ni los presupuestos posteriores por serie,
    por tabla y antes de publicar. La serialización es la misma del preparador, con su salto de línea final.
    """
    serializado = json.dumps(plan_corrida, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    return len(serializado.encode("utf-8")) + OVERHEAD_INICIO_BYTES


def ejecutar(prep: types.ModuleType, ins: dict, salida: Path, datos: Path, reserva_gib: float = RESERVA_GIB,
             r=None, cfg: dict | None = None, estado=None) -> dict:
    """Publica el derivado red 2 serie por serie con ``process_series`` (candado, procedencia y reapertura del
    propio preparador). Se corre en el armado (R22, paso 3), con la traducción confirmada en git. ``plan.json`` lleva
    la huella de este programa y la procedencia de la corrida (``plan_con_procedencia``)."""
    import _rutas_v2 as rv
    r = r or rv.rutas_v2()
    compuerta = ra.exigir_traduccion_confirmada(r, cfg, estado)
    salida = verificar_destino(salida, datos)
    plan_corrida = plan_con_procedencia(ins, r, compuerta)
    prep.check_disk(salida, reserva_gib, pending_bytes=presupuesto_inicio_corrida(plan_corrida))
    salida.mkdir(parents=True, exist_ok=True)
    codigo = Path(RUTA_PREPARADOR).read_bytes()
    resultados = []
    with prep.exclusive_lock(salida / ".writer.lock"):
        corrida = salida / "_runs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-red2")
        corrida.mkdir(parents=True)
        # plan.json registra el entorno (T8: amb_v2), en ranking_afg.esta_corrida, y su procedencia
        prep.json_atomic(corrida / "plan.json", plan_corrida)
        for (e, p), (fam, filas) in sorted(ins["grupos"].items()):
            resultados.append(prep.process_series(filas, ins[fam], salida, reserve_gib=reserva_gib, code_bytes=codigo))
            prep.json_atomic(corrida / "progreso.json", {"status": "running", "results": resultados})
        prep.json_atomic(corrida / "progreso.json", {"status": "complete_for_selected_scope", "results": resultados})
    return {"series": len(resultados), "corrida": str(corrida.name)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Derivado SINCA de la red ampliada (R5), sin tocar el derivado v1.")
    ap.add_argument("--datos", type=Path, default=None, help="raíz de datos (por omisión, la de la v2)")
    ap.add_argument("--salida", type=Path, default=None)
    ap.add_argument("--medir", type=int, default=0, help="consolida N series de muestra sin escribir y mide")
    ap.add_argument("--ejecutar", action="store_true")
    args = ap.parse_args(argv)
    import _rutas_v2 as rv

    datos = (args.datos or rv.rutas_v2().datos).resolve()
    ra.verificar_lista_cerrada(datos)
    prep = cargar_preparador()
    ins = insumos_red2(prep, datos)
    p = plan(ins)
    print(json.dumps({k: v for k, v in p.items() if k != "detalle"}, ensure_ascii=False))
    if args.medir:
        claves = sorted(ins["grupos"])[: max(1, args.medir)]
        print(json.dumps(medir(prep, ins, claves), ensure_ascii=False))
    if args.ejecutar:
        print(json.dumps(ejecutar(prep, ins, args.salida or destino_por_omision(datos), datos), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
