#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comprueba que los componentes compartidos entre Air-Pollution y Air-Pollution-Health-Chile coinciden.

Air-Pollution (AP, público) es el canónico de los componentes ambientales y Air-Pollution-Health-Chile (APH,
privado) su espejo: la copia va siempre de AP a APH. El manifiesto ``config/componentes_compartidos.json``
(esquema ``componentes-compartidos/v1``, idéntico en los dos repositorios) declara:

* grupos ``identico``: patrones de rutas y el sha256 de cada archivo, tomado del canónico;
* grupo ``adaptado``: las diferencias permitidas, con el sha256 de cada lado, el motivo y el plan para eliminarlas;
* ``propios``: lo que cada repositorio no sincroniza (si cae dentro de un grupo, ese lado lo ignora);
* ``hash_codigo``: la huella del modelo de 1 km esperada (la del canónico), la observada en cada repositorio y la
  excepción vigente, si la hay.

Qué comprueba (sólo lectura):

1. En cada grupo idéntico, el mismo conjunto de archivos y el mismo sha256 en canónico y espejo, y que el canónico
   no cambió desde el manifiesto (un archivo distinto, nuevo o ausente obliga a regenerarlo).
2. En los adaptados, el sha256 declarado de cada lado.
3. Que la copia del manifiesto en el espejo sea idéntica a la del canónico.
4. ``hash_codigo`` (réplica de ``scripts_modelo_1km/_comun_modelo.py::hash_codigo``): el del canónico es el
   esperado, el del espejo es el observado al generar y, si difieren o el informe estampa otra huella, hay una
   excepción vigente declarada.

Siempre excluye ``__pycache__/``, ``*.pyc``, ``.DS_Store``, ``* 2.*`` (copias de conflicto de Google Drive) y
``*.log``. Nunca entra en rutas cuyo nombre contiene «mni1» o «privado» (sin distinguir mayúsculas): ni las
recorre ni las abre. No sigue enlaces simbólicos: uno dentro de un grupo es una divergencia.

Opciones:
  --plan        además imprime, sin ejecutarlo, un ``rsync -a -v --checksum --dry-run --files-from=-`` del
                canónico al espejo con lo que falta o difiere. Nunca propone borrar.
  --generar     regenera el manifiesto desde el canónico (sha256, adaptados, hash_codigo, commit de anclaje y
                rutas sin confirmar) y conserva grupos, motivos y planes. Si el manifiesto existe y cambiaría,
                sólo muestra los cambios; ``--forzar`` lo sobrescribe.
  --actualizar-ruta RUTA  modo separado y repetible: --base BASE --salida CANDIDATA; ambas fuentes deben estar
                confirmadas y limpias en Git. Sólo actualiza SHA seleccionadas y añade actualizaciones_acotadas.
                Los metadatos globales se conservan como historia de la base; no se lee ningún informe ni se
                comprueba coherencia global. Vista previa por omisión; --forzar crea sólo una candidata externa
                nueva, fuera de ambos repositorios. Una salida existente sólo se admite si ya es una candidata válida
                e idéntica de esta operación; jamás se sobrescribe. Se ignoran refs/replace e info/grafts de Git.
                La base debe coincidir con el manifiesto de los HEAD reales, o con --commit-base-canonico y
                --commit-base-espejo (identificadores completos reales). Nunca instala manifiestos activos.
  --registrar   añade una línea JSON con el resultado a un registro (en APH,
                ``auditoria/registro_sincronizacion.jsonl``).

Repositorios: ``--canonico`` y ``--espejo``. Por omisión son las carpetas hermanas ``Air-Pollution`` y
``Air-Pollution-Health-Chile`` del repositorio que contiene este script. El manifiesto no lleva rutas absolutas.
Sólo escribe con ``--generar`` (el manifiesto), ``--actualizar-ruta --forzar`` (una candidata separada) o
``--registrar`` (una línea del registro). La operación acotada no certifica coherencia global.

Códigos de salida:
    0  coherente al verificar; al generar/actualizar: operación exitosa o sin cambios, NO verificación global;
    1  hay divergencias; al generar/actualizar sin --forzar: cambiaría y no se escribió;
    2  manifiesto inválido, repositorio inexistente o archivo ilegible. El 2 tiene prioridad.

Ejemplos, desde la raíz de cualquiera de los dos repositorios::

    python -B others_scripts/verificar_componentes_compartidos.py
    python -B others_scripts/verificar_componentes_compartidos.py --plan
    python -B others_scripts/verificar_componentes_compartidos.py --generar            # muestra qué cambiaría
    python -B others_scripts/verificar_componentes_compartidos.py --generar --forzar   # lo escribe

Sólo biblioteca estándar (Python >= 3.9).
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import functools
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

ESQUEMA = "componentes-compartidos/v1"
DIRECCION = "canonico->espejo"
RUTA_MANIFIESTO = "config/componentes_compartidos.json"
CANONICO_POR_DEFECTO = "Air-Pollution"
ESPEJO_POR_DEFECTO = "Air-Pollution-Health-Chile"
PROHIBIDOS = ("mni1", "privado")
EXCLUIR_SIEMPRE = ("**/__pycache__/**", "**/*.pyc", "**/.DS_Store", "** 2.*", "**/*.log")
CARPETAS_OMITIDAS = frozenset({".git", "__pycache__"})
QMD_MODELO = "docs/modelo_1km_horario.qmd"
INFORME_MODELO = "docs/modelo_1km_horario.html"
AUSENTE = "ausente"
ENLACE = "enlace simbólico"
BLOQUE = 8 * 1024 * 1024
MAX_LINEAS_CAMBIOS = 200
ETIQUETA_HASH = "scripts_modelo_1km/*.py + docs/modelo_1km_horario.qmd"
DEFINICION_HASH = (
    "Réplica de scripts_modelo_1km/_comun_modelo.py::hash_codigo: sha256 de, para cada scripts_modelo_1km/*.py "
    "en orden y después docs/modelo_1km_horario.qmd, el nombre en UTF-8 seguido del sha256 binario del "
    "archivo; primeros 16 hexadecimales. Es la huella «código» que estampan el informe del modelo y cada "
    "superficie.")

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_HEX16 = re.compile(r"[0-9a-f]{16}\Z")
_CODIGO_EN_INFORME = re.compile(r"[Cc](?:ó|&oacute;|&#243;|&#xf3;)digo\s*<code>([0-9a-f]{16})</code>")
_DOCUMENTO_EN_INFORME = re.compile(r"documento\s*<code>([0-9a-f]{16})</code>")

ORDEN_RAIZ = ("esquema", "descripcion", "generado", "generador", "canonico", "espejos", "direccion",
              "ruta_manifiesto", "excluir_siempre", "rutas_prohibidas", "grupos", "propios", "hash_codigo",
              "versiones_modelo")
ORDEN_CANONICO = ("repo", "alias", "commit_ancla", "rama", "rutas_sin_confirmar")
ORDEN_GRUPO = ("nombre", "modo", "descripcion", "incluir", "excluir", "sha256", "archivos")
ORDEN_ADAPTADO = ("tipo", "motivo", "plan", "sha256_canonico", "sha256_espejo")
ORDEN_HASH = ("definicion", "esperado", "observado", "declarado_en_informe", "excepcion", "nota")


class ManifiestoInvalido(Exception):
    """El manifiesto no cumple el esquema (salida 2)."""


class ErrorLectura(Exception):
    """Un archivo o carpeta de un repositorio no se pudo leer (salida 2)."""


# ---------------------------------------------------------------------------------------------------------------
# Rutas, patrones y lectura
# ---------------------------------------------------------------------------------------------------------------
def prohibida(ruta: str) -> bool:
    """True si la ruta o el nombre contiene «mni1» o «privado», sin distinguir mayúsculas."""
    minus = ruta.lower()
    return any(p in minus for p in PROHIBIDOS)


def _nfc(texto: str) -> str:
    return unicodedata.normalize("NFC", texto)


def _tiene_comodin(texto: str) -> bool:
    return "*" in texto or "?" in texto


@functools.lru_cache(maxsize=None)
def patron_a_regex(patron: str) -> "re.Pattern[str]":
    """Glob de rutas relativas: ``**`` cruza carpetas (``**/`` vale también por cero carpetas); ``*`` y ``?`` no
    cruzan ``/``. Todo lo demás es literal."""
    partes, i = [], 0
    while i < len(patron):
        if patron.startswith("**/", i):
            partes.append("(?:.*/)?")
            i += 3
        elif patron.startswith("**", i):
            partes.append(".*")
            i += 2
        elif patron[i] == "*":
            partes.append("[^/]*")
            i += 1
        elif patron[i] == "?":
            partes.append("[^/]")
            i += 1
        else:
            partes.append(re.escape(patron[i]))
            i += 1
    return re.compile("".join(partes) + r"\Z")


_RX_EXCLUIR_SIEMPRE = tuple(patron_a_regex(p) for p in EXCLUIR_SIEMPRE)


def _dir_viable(partes: list[str], segmentos: list[str]) -> bool:
    """¿Puede haber, debajo de la carpeta ``partes``, un archivo que coincida con el patrón ``segmentos``?"""
    for i, parte in enumerate(partes):
        if i >= len(segmentos):
            return False
        seg = segmentos[i]
        if "**" in seg:
            return True
        if i == len(segmentos) - 1:  # el último segmento nombra archivos, no carpetas
            return False
        if not patron_a_regex(seg).match(parte):
            return False
    return True


def _listar_directorio(carpeta: Path) -> list:
    """Único lugar donde se lista una carpeta de un repositorio (las pruebas lo espían)."""
    with os.scandir(carpeta) as entradas:
        return sorted(entradas, key=lambda e: e.name)


def _abrir_lectura(ruta: Path):
    """Único lugar donde se abre un archivo de un repositorio (las pruebas lo espían)."""
    return open(ruta, "rb")


def _leer_bytes(ruta: Path) -> bytes:
    with _abrir_lectura(ruta) as fh:
        return fh.read()


def sha256_archivo(ruta: Path, etiqueta: str | None = None) -> str:
    h = hashlib.sha256()
    try:
        with _abrir_lectura(ruta) as fh:
            for bloque in iter(lambda: fh.read(BLOQUE), b""):
                h.update(bloque)
    except OSError as exc:
        raise ErrorLectura(f"no se pudo leer {etiqueta or ruta.name}: {exc.strerror or exc}") from None
    return h.hexdigest()


def _componente_enlazado(raiz: Path, rel: str) -> bool:
    """True si algún componente de ``rel`` (bajo ``raiz``) es un enlace simbólico."""
    actual = raiz
    for parte in rel.split("/"):
        actual = actual / parte
        if actual.is_symlink():
            return True
    return False


def _sha_o_ausente(raiz: Path, rel: str) -> str:
    """sha256 de ``raiz/rel``, «ausente» si no es un archivo, o «enlace simbólico» (que no se sigue)."""
    if prohibida(rel):
        raise ErrorLectura(f"ruta prohibida: {rel}")
    if _componente_enlazado(raiz, rel):
        return ENLACE
    ruta = raiz.joinpath(*rel.split("/"))
    try:
        es_archivo = ruta.is_file()
    except OSError as exc:
        raise ErrorLectura(f"no se pudo examinar {rel}: {exc.strerror or exc}") from None
    return sha256_archivo(ruta, rel) if es_archivo else AUSENTE


def expandir(raiz: Path, incluir, excluir=(), ignorar=()) -> tuple[dict[str, Path], set[str]]:
    """Archivos regulares de ``raiz`` que coinciden con ``incluir`` y no con las exclusiones.

    Devuelve ``({ruta relativa en NFC: ruta en disco}, {enlaces simbólicos dentro del alcance})``. Nunca lista ni
    abre una ruta prohibida, no entra en ``.git`` ni ``__pycache__`` y no sigue enlaces."""
    rx_fuera = [*_RX_EXCLUIR_SIEMPRE, *(patron_a_regex(p) for p in excluir),
                *(patron_a_regex(p) for p in ignorar)]

    def fuera(rel: str) -> bool:
        return any(rx.match(rel) for rx in rx_fuera)

    archivos: dict[str, Path] = {}
    enlaces: set[str] = set()
    for patron in incluir:
        if prohibida(patron):
            continue
        rx = patron_a_regex(patron)
        segmentos = patron.split("/")
        if not _tiene_comodin(patron):
            if _componente_enlazado(raiz, patron):
                enlaces.add(_nfc(patron))
                continue
            ruta = raiz.joinpath(*segmentos)
            try:
                es_archivo = ruta.is_file()
            except OSError as exc:
                raise ErrorLectura(f"no se pudo examinar {patron}: {exc.strerror or exc}") from None
            if es_archivo and not fuera(patron):
                archivos[_nfc(patron)] = ruta
            continue
        fijos = []
        for seg in segmentos[:-1]:
            if _tiene_comodin(seg):
                break
            fijos.append(seg)
        base_rel = "/".join(fijos)
        if base_rel and _componente_enlazado(raiz, base_rel):
            enlaces.add(_nfc(base_rel))
            continue
        inicio = raiz.joinpath(*fijos)
        if not inicio.is_dir():
            continue
        pila = [(inicio, _nfc(base_rel))]
        while pila:
            carpeta, rel_carpeta = pila.pop()
            try:
                entradas = _listar_directorio(carpeta)
            except OSError as exc:
                raise ErrorLectura(f"no se pudo listar {rel_carpeta or '.'}: {exc.strerror or exc}") from None
            for entrada in entradas:
                if prohibida(entrada.name) or entrada.name in CARPETAS_OMITIDAS:
                    continue  # no se mira qué es: ni stat ni apertura
                rel = _nfc(f"{rel_carpeta}/{entrada.name}" if rel_carpeta else entrada.name)
                if fuera(rel):
                    continue
                try:
                    es_enlace = entrada.is_symlink()
                    es_carpeta = not es_enlace and entrada.is_dir(follow_symlinks=False)
                    es_archivo = not es_enlace and not es_carpeta and entrada.is_file(follow_symlinks=False)
                except OSError as exc:
                    raise ErrorLectura(f"no se pudo examinar {rel}: {exc.strerror or exc}") from None
                if es_enlace:
                    if rx.match(rel) or _dir_viable(rel.split("/"), segmentos):
                        enlaces.add(rel)
                elif es_carpeta:
                    if _dir_viable(rel.split("/"), segmentos):
                        pila.append((Path(entrada.path), rel))
                elif es_archivo and rx.match(rel):
                    archivos[rel] = Path(entrada.path)
    return archivos, enlaces


def hash_codigo(raiz: Path) -> str | None:
    """Réplica de ``scripts_modelo_1km/_comun_modelo.py::hash_codigo`` (ver ``DEFINICION_HASH``).

    No importa el módulo, que necesita numpy, pandas y el pipeline. Igual que el original, no aplica exclusiones y
    sigue enlaces, pero no abre un archivo cuyo nombre o destino sea una ruta prohibida. None si no hay
    ``scripts_modelo_1km``."""
    carpeta = (raiz / "scripts_modelo_1km").resolve()
    if not carpeta.is_dir():
        return None
    archivos = sorted(carpeta.glob("*.py"))
    qmd = carpeta.parent / "docs" / "modelo_1km_horario.qmd"  # el RAIZ del original: padre de la carpeta resuelta
    if qmd.exists():
        archivos.append(qmd)
    h = hashlib.sha256()
    for p in archivos:
        if prohibida(p.name) or (p.is_symlink() and prohibida(os.readlink(p))):
            raise ErrorLectura(f"hash_codigo: scripts_modelo_1km/{p.name} es una ruta prohibida; no se abre")
        h.update(p.name.encode())
        h.update(bytes.fromhex(sha256_archivo(p, f"scripts_modelo_1km/{p.name}")))
    return h.hexdigest()[:16]


def _huellas_informe(raiz: Path) -> dict | None:
    """Huellas «código» y «documento» que estampa el informe HTML del modelo, y la del qmd actual."""
    if _componente_enlazado(raiz, INFORME_MODELO):
        return None
    ruta = raiz.joinpath(*INFORME_MODELO.split("/"))
    if not ruta.is_file():
        return None
    try:
        texto = _leer_bytes(ruta).decode("utf-8", "replace")
    except OSError as exc:
        raise ErrorLectura(f"no se pudo leer {INFORME_MODELO}: {exc.strerror or exc}") from None
    qmd = raiz.joinpath(*QMD_MODELO.split("/"))
    return {
        "archivo": INFORME_MODELO,
        "codigo": sorted(set(_CODIGO_EN_INFORME.findall(texto))),
        "documento": sorted(set(_DOCUMENTO_EN_INFORME.findall(texto))),
        "documento_qmd_actual": sha256_archivo(qmd, QMD_MODELO)[:16] if qmd.is_file() else None,
    }


# ---------------------------------------------------------------------------------------------------------------
# Validación del manifiesto
# ---------------------------------------------------------------------------------------------------------------
def _validar_ruta(ruta: object, que: str, patron: bool = False) -> str:
    if not isinstance(ruta, str) or not ruta.strip():
        raise ManifiestoInvalido(f"{que}: ruta vacía o que no es texto ({ruta!r})")
    if ruta.startswith(("/", "~")) or re.match(r"[A-Za-z]:", ruta) or "\\" in ruta:
        raise ManifiestoInvalido(f"{que}: ruta absoluta o con barra invertida ({ruta!r})")
    if any(parte in ("", ".", "..") for parte in ruta.split("/")):
        raise ManifiestoInvalido(f"{que}: segmento vacío, «.» o «..» en {ruta!r}")
    if not patron and _tiene_comodin(ruta):
        raise ManifiestoInvalido(f"{que}: una ruta de archivo no lleva comodines ({ruta!r})")
    if prohibida(ruta):
        raise ManifiestoInvalido(f"{que}: nombra una ruta prohibida ({ruta!r})")
    return ruta


def _validar_lista_patrones(valor: object, que: str, vacia: bool = True) -> list[str]:
    if not isinstance(valor, list) or (not vacia and not valor):
        raise ManifiestoInvalido(f"{que}: se espera una lista{'' if vacia else ' no vacía'} de patrones")
    return [_validar_ruta(p, que, patron=True) for p in valor]


def _texto(valor: object, que: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ManifiestoInvalido(f"{que}: falta o está vacío")
    return valor


def _nombre_repo(valor: object, que: str) -> str:
    nombre = _texto(valor, que)
    if "/" in nombre or "\\" in nombre or nombre in (".", ".."):
        raise ManifiestoInvalido(f"{que}: un nombre de repositorio, no una ruta ({nombre!r})")
    return nombre


def validar_manifiesto(man: object, estricto: bool = True) -> None:
    """Valida el esquema. Con ``estricto=False`` (base para ``--generar``) no exige las huellas."""
    if not isinstance(man, dict):
        raise ManifiestoInvalido("la raíz no es un objeto JSON")
    if man.get("esquema") != ESQUEMA:
        raise ManifiestoInvalido(f"esquema {man.get('esquema')!r}; se espera {ESQUEMA!r}")
    if man.get("direccion") != DIRECCION:
        raise ManifiestoInvalido(f"direccion {man.get('direccion')!r}; se espera {DIRECCION!r}")
    canonico = man.get("canonico")
    if not isinstance(canonico, dict):
        raise ManifiestoInvalido("canonico: se espera un objeto con «repo»")
    nombre_c = _nombre_repo(canonico.get("repo"), "canonico.repo")
    espejos = man.get("espejos")
    if not isinstance(espejos, list) or len(espejos) != 1 or not isinstance(espejos[0], dict):
        raise ManifiestoInvalido("espejos: se espera una lista con exactamente un repositorio")
    nombre_e = _nombre_repo(espejos[0].get("repo"), "espejos[0].repo")
    if nombre_c == nombre_e:
        raise ManifiestoInvalido("canónico y espejo tienen el mismo nombre")
    if man.get("ruta_manifiesto", RUTA_MANIFIESTO) != RUTA_MANIFIESTO:
        raise ManifiestoInvalido(f"ruta_manifiesto debe ser {RUTA_MANIFIESTO!r}")
    extra = _validar_lista_patrones(man.get("excluir_siempre", []), "excluir_siempre")
    propios = man.get("propios", {})
    if not isinstance(propios, dict):
        raise ManifiestoInvalido("propios: se espera un objeto {repositorio: [patrones]}")
    for clave, valor in propios.items():
        if clave == "descripcion":
            _texto(valor, "propios.descripcion")
        else:
            _validar_lista_patrones(valor, f"propios.{clave}")
    rx_propios_c = [patron_a_regex(p) for p in propios.get(nombre_c, [])]

    grupos = man.get("grupos")
    if not isinstance(grupos, list) or not grupos:
        raise ManifiestoInvalido("grupos: se espera una lista no vacía")
    nombres: set[str] = set()
    declarados: dict[str, str] = {}
    adaptados: dict[str, str] = {}
    for i, g in enumerate(grupos):
        if not isinstance(g, dict):
            raise ManifiestoInvalido(f"grupos[{i}]: se espera un objeto")
        nombre = _texto(g.get("nombre"), f"grupos[{i}].nombre")
        if nombre in nombres or nombre in ("manifiesto", "hash_codigo"):
            raise ManifiestoInvalido(f"grupo {nombre!r}: nombre repetido o reservado")
        nombres.add(nombre)
        modo = g.get("modo")
        if modo == "identico":
            incluir = _validar_lista_patrones(g.get("incluir"), f"grupo {nombre}: incluir", vacia=False)
            excluir = _validar_lista_patrones(g.get("excluir", []), f"grupo {nombre}: excluir")
            if not estricto:  # --generar recalcula estas huellas desde el canónico
                continue
            sha = g.get("sha256")
            if not isinstance(sha, dict):
                raise ManifiestoInvalido(f"grupo {nombre}: sha256 debe ser un objeto {{ruta: sha256}}")
            rx_in = [patron_a_regex(p) for p in incluir]
            rx_fuera = [*_RX_EXCLUIR_SIEMPRE, *(patron_a_regex(p) for p in (*excluir, *extra)), *rx_propios_c]
            for rel, valor in sha.items():
                _validar_ruta(rel, f"grupo {nombre}")
                if not isinstance(valor, str) or not _HEX64.match(valor):
                    raise ManifiestoInvalido(f"grupo {nombre}: sha256 inválido para {rel}")
                if not any(rx.match(rel) for rx in rx_in) or any(rx.match(rel) for rx in rx_fuera):
                    raise ManifiestoInvalido(f"grupo {nombre}: {rel} no corresponde a sus patrones o está excluido")
                if rel == RUTA_MANIFIESTO:
                    raise ManifiestoInvalido(f"grupo {nombre}: el manifiesto no puede declarar su propio sha256")
                if rel in declarados:
                    raise ManifiestoInvalido(f"{rel} está en los grupos {declarados[rel]} y {nombre}")
                declarados[rel] = nombre
        elif modo == "adaptado":
            archivos = g.get("archivos")
            if not isinstance(archivos, dict):
                raise ManifiestoInvalido(f"grupo {nombre}: archivos debe ser un objeto {{ruta: {{...}}}}")
            for rel, d in archivos.items():
                _validar_ruta(rel, f"grupo {nombre}")
                if not isinstance(d, dict):
                    raise ManifiestoInvalido(f"grupo {nombre}: {rel} debe ser un objeto")
                _texto(d.get("motivo"), f"grupo {nombre}: {rel}: motivo")
                _texto(d.get("plan"), f"grupo {nombre}: {rel}: plan")
                if estricto:
                    lados = (d.get("sha256_canonico"), d.get("sha256_espejo"))
                    for lado, valor in zip(("sha256_canonico", "sha256_espejo"), lados):
                        if valor not in (AUSENTE, ENLACE) and not (isinstance(valor, str) and _HEX64.match(valor)):
                            raise ManifiestoInvalido(f"grupo {nombre}: {rel}: {lado} inválido ({valor!r})")
                    if lados[0] == lados[1]:
                        raise ManifiestoInvalido(f"grupo {nombre}: {rel} declara el mismo valor en los dos lados")
                if rel == RUTA_MANIFIESTO or rel in adaptados:
                    raise ManifiestoInvalido(f"grupo {nombre}: {rel} repetido o reservado")
                adaptados[rel] = nombre
        else:
            raise ManifiestoInvalido(f"grupo {nombre}: modo {modo!r}; se espera «identico» o «adaptado»")
    for rel, grupo in adaptados.items():
        if rel in declarados:
            raise ManifiestoInvalido(f"{rel} es adaptado ({grupo}) y está en el grupo idéntico {declarados[rel]}")

    hcod = man.get("hash_codigo")
    if hcod is None and not estricto:
        return
    if not isinstance(hcod, dict):
        raise ManifiestoInvalido("hash_codigo: se espera un objeto")
    if estricto:
        if hcod.get("esperado") is not None and not _HEX16.match(str(hcod.get("esperado"))):
            raise ManifiestoInvalido("hash_codigo.esperado: 16 hexadecimales o null")
        observado = hcod.get("observado")
        if not isinstance(observado, dict):
            raise ManifiestoInvalido("hash_codigo.observado: se espera un objeto {repositorio: huella}")
        for repo, valor in observado.items():
            if valor is not None and not _HEX16.match(str(valor)):
                raise ManifiestoInvalido(f"hash_codigo.observado.{repo}: 16 hexadecimales o null")
        informe = hcod.get("declarado_en_informe")
        if informe is not None:
            if not isinstance(informe, dict):
                raise ManifiestoInvalido("hash_codigo.declarado_en_informe: se espera null o un objeto")
            for clave in ("codigo", "documento"):
                valores = informe.get(clave, [])
                if not isinstance(valores, list) or not all(isinstance(v, str) and _HEX16.match(v) for v in valores):
                    raise ManifiestoInvalido(f"hash_codigo.declarado_en_informe.{clave}: lista de 16 hexadecimales")
    _validar_actualizaciones_acotadas(man)
    excepcion = hcod.get("excepcion")
    if excepcion is not None:
        if not isinstance(excepcion, dict) or not isinstance(excepcion.get("vigente"), bool):
            raise ManifiestoInvalido("hash_codigo.excepcion: se espera un objeto con «vigente» (true/false)")
        _texto(excepcion.get("motivo"), "hash_codigo.excepcion.motivo")
        _texto(excepcion.get("plan"), "hash_codigo.excepcion.plan")


# ---------------------------------------------------------------------------------------------------------------
# Verificación
# ---------------------------------------------------------------------------------------------------------------
class Informe:
    def __init__(self, nombre_c: str, nombre_e: str):
        self.nombre_c, self.nombre_e = nombre_c, nombre_e
        self.lineas: list[str] = []
        self.divergencias: list[tuple[str, str, str]] = []
        self.avisos: list[str] = []
        self.a_copiar: set[str] = set()
        self.sobran: set[str] = set()
        self.adaptados: set[str] = set()
        self.canonico_cambio = False
        self.hash: dict[str, str | None] = {}

    def diverge(self, grupo: str, ruta: str, motivo: str) -> None:
        self.divergencias.append((grupo, ruta, motivo))

    def cerrar(self, grupo: str, antes: int, texto_ok: str) -> None:
        n = len(self.divergencias) - antes
        self.lineas.append(f"ok  {grupo}: {texto_ok}" if n == 0
                           else f"!!  {grupo}: {n} divergencia{'s' if n > 1 else ''}")


def _corto(valor: str | None) -> str:
    return valor[:12] if isinstance(valor, str) and _HEX64.match(valor) else str(valor)


def _comparar_manifiestos(C: Path, E: Path, inf: Informe, man_bytes: bytes) -> None:
    antes = len(inf.divergencias)
    sc, se = _sha_o_ausente(C, RUTA_MANIFIESTO), _sha_o_ausente(E, RUTA_MANIFIESTO)
    if sc in (AUSENTE, ENLACE):
        inf.diverge("manifiesto", RUTA_MANIFIESTO, f"el canónico no tiene el manifiesto como archivo ({sc})")
    elif se == AUSENTE:
        inf.diverge("manifiesto", RUTA_MANIFIESTO, "falta en el espejo")
        inf.a_copiar.add(RUTA_MANIFIESTO)
    elif sc != se:
        inf.diverge("manifiesto", RUTA_MANIFIESTO, "la copia del espejo es distinta de la del canónico")
        inf.a_copiar.add(RUTA_MANIFIESTO)
    if sc not in (AUSENTE, ENLACE, hashlib.sha256(man_bytes).hexdigest()):
        inf.avisos.append(f"se usó un manifiesto distinto del que guarda el canónico en {RUTA_MANIFIESTO}")
    inf.cerrar("manifiesto", antes, "la copia del espejo es idéntica a la del canónico")


def _comparar_identico(g: dict, man: dict, C: Path, E: Path, inf: Informe) -> None:
    nombre, antes = g["nombre"], len(inf.divergencias)
    propios = man.get("propios") or {}
    excluir = [*g.get("excluir", []), *man.get("excluir_siempre", [])]
    c, enlaces_c = expandir(C, g["incluir"], excluir, propios.get(inf.nombre_c, []))
    e, enlaces_e = expandir(E, g["incluir"], excluir, propios.get(inf.nombre_e, []))
    for rel in inf.adaptados | {RUTA_MANIFIESTO}:
        c.pop(rel, None)
        e.pop(rel, None)
    for rel in sorted(enlaces_c):
        inf.diverge(nombre, rel, "enlace simbólico en el canónico: no se sigue ni se compara")
    for rel in sorted(enlaces_e):
        inf.diverge(nombre, rel, "enlace simbólico en el espejo: no se sigue ni se compara")
    hc = {rel: sha256_archivo(p, rel) for rel, p in sorted(c.items())}
    he = {rel: sha256_archivo(p, rel) for rel, p in sorted(e.items())}
    for rel in sorted(set(hc) - set(he)):
        inf.diverge(nombre, rel, "falta en el espejo")
        inf.a_copiar.add(rel)
    for rel in sorted(set(he) - set(hc)):
        inf.diverge(nombre, rel, "sobra en el espejo (no se borra: se decide en el canónico)")
        inf.sobran.add(rel)
    for rel in sorted(set(hc) & set(he)):
        if hc[rel] != he[rel]:
            inf.diverge(nombre, rel, f"distinto en el espejo (canónico {hc[rel][:12]}, espejo {he[rel][:12]})")
            inf.a_copiar.add(rel)
    declarado = g.get("sha256") or {}
    for rel in sorted(hc):
        if rel not in declarado:
            inf.diverge(nombre, rel, "nuevo en el canónico y no declarado: regenerar el manifiesto")
            inf.canonico_cambio = True
        elif declarado[rel] != hc[rel]:
            inf.diverge(nombre, rel, f"el canónico cambió desde el manifiesto ({declarado[rel][:12]} → "
                                     f"{hc[rel][:12]}): regenerar el manifiesto")
            inf.canonico_cambio = True
    for rel in sorted(set(declarado) - set(hc)):
        inf.diverge(nombre, rel, "declarado en el manifiesto y ausente del canónico: regenerar el manifiesto")
        inf.canonico_cambio = True
    n = len(hc)
    inf.cerrar(nombre, antes, f"{n} archivo{'s' if n != 1 else ''} idéntico{'s' if n != 1 else ''} en los dos "
                              "lados y sin cambios desde el manifiesto")


def _comparar_adaptados(g: dict, C: Path, E: Path, inf: Informe) -> None:
    nombre, antes = g["nombre"], len(inf.divergencias)
    for rel, d in sorted(g["archivos"].items()):
        real_c, real_e = _sha_o_ausente(C, rel), _sha_o_ausente(E, rel)
        if real_c == real_e:
            inf.diverge(nombre, rel, "ya es igual en los dos lados: quitarlo de «adaptado» y regenerar el manifiesto")
            continue
        if real_c != d["sha256_canonico"]:
            inf.diverge(nombre, rel, f"el canónico cambió ({_corto(d['sha256_canonico'])} → {_corto(real_c)}): "
                                     "regenerar el manifiesto")
            inf.canonico_cambio = True
        if real_e != d["sha256_espejo"]:
            inf.diverge(nombre, rel, f"el espejo cambió ({_corto(d['sha256_espejo'])} → {_corto(real_e)})")
    n = len(g["archivos"])
    inf.cerrar(nombre, antes, f"{n} diferencia{'s' if n != 1 else ''} declarada{'s' if n != 1 else ''}, con el "
                              "sha256 esperado en cada lado")


def _comparar_hash(man: dict, C: Path, E: Path, inf: Informe) -> None:
    antes = len(inf.divergencias)
    hcod = man.get("hash_codigo") or {}
    esperado = hcod.get("esperado")
    observado = hcod.get("observado") or {}
    vigente = bool((hcod.get("excepcion") or {}).get("vigente"))
    hc_c, hc_e = hash_codigo(C), hash_codigo(E)
    inf.hash = {"canonico": hc_c, "espejo": hc_e}
    if hc_c != esperado:
        inf.diverge("hash_codigo", ETIQUETA_HASH, f"el del canónico es {hc_c} y el manifiesto espera {esperado}: "
                                                  "regenerar el manifiesto")
        inf.canonico_cambio = True
    if hc_e != observado.get(inf.nombre_e):
        inf.diverge("hash_codigo", ETIQUETA_HASH,
                    f"el del espejo es {hc_e} y al generar el manifiesto era {observado.get(inf.nombre_e)}")
    if hc_e != hc_c and not vigente:
        inf.diverge("hash_codigo", ETIQUETA_HASH,
                    f"difiere entre canónico ({hc_c}) y espejo ({hc_e}) sin excepción vigente")
    estampados = (hcod.get("declarado_en_informe") or {}).get("codigo") or []
    otros = [x for x in estampados if x != esperado]
    if otros and not vigente:
        inf.diverge("hash_codigo", INFORME_MODELO,
                    f"el informe estampa {', '.join(otros)}, distinto del esperado {esperado}, sin excepción vigente")
    if vigente and hc_e == hc_c and not otros:
        inf.avisos.append("hash_codigo: canónico, espejo e informe coinciden; la excepción vigente ya no hace falta "
                          "(--generar --forzar la quita)")
    texto = f"canónico {hc_c}, espejo {hc_e}"
    if vigente:
        texto += "; excepción vigente (ver hash_codigo.excepcion del manifiesto)"
    inf.cerrar("hash_codigo", antes, texto)


def verificar(man: dict, C: Path, E: Path, man_bytes: bytes) -> Informe:
    inf = Informe(man["canonico"]["repo"], man["espejos"][0]["repo"])
    inf.adaptados = {rel for g in man["grupos"] if g["modo"] == "adaptado" for rel in g["archivos"]}
    if C.resolve() == E.resolve():
        inf.avisos.append("canónico y espejo son la misma carpeta (prueba de control)")
    _comparar_manifiestos(C, E, inf, man_bytes)
    for g in man["grupos"]:
        if g["modo"] == "identico":
            _comparar_identico(g, man, C, E, inf)
    for g in man["grupos"]:
        if g["modo"] == "adaptado":
            _comparar_adaptados(g, C, E, inf)
    _comparar_hash(man, C, E, inf)
    return inf


def _relativa(ruta: Path) -> str:
    try:
        return os.path.relpath(ruta, Path.cwd())
    except ValueError:
        return str(ruta)


def imprimir_informe(inf: Informe, man: dict) -> None:
    print(f"Manifiesto {ESQUEMA} generado {man.get('generado') or 'sin fecha'} · "
          f"canónico {inf.nombre_c} → espejo {inf.nombre_e}")
    for linea in inf.lineas:
        print(linea)
    for grupo, ruta, motivo in inf.divergencias:
        print(f"DIVERGE [{grupo}] {ruta}: {motivo}")
    for aviso in inf.avisos:
        print(f"AVISO {aviso}")
    n = len(inf.divergencias)
    print("COHERENTE" if n == 0 else f"{n} divergencia{'s' if n > 1 else ''}")


def imprimir_plan(inf: Informe, C: Path, E: Path) -> None:
    print("# Plan de copia canónico -> espejo. NO se ejecutó: revisa cada ruta y, para copiar, quita --dry-run.")
    print("# Rutas relativas a la carpeta actual. No borra nada en el espejo.")
    if inf.canonico_cambio:
        print("# Aviso: el canónico cambió desde el manifiesto. Primero --generar --forzar en el canónico.")
    lista = sorted(inf.a_copiar)
    if not lista:
        print("# Nada que copiar del canónico al espejo.")
    else:
        origen = shlex.quote(_relativa(C).rstrip("/") + "/")
        destino = shlex.quote(_relativa(E).rstrip("/") + "/")
        print(f"rsync -a -v --checksum --dry-run --files-from=- {origen} {destino} <<'LISTA'")
        for rel in lista:
            print(rel)
        print("LISTA")
    if inf.sobran:
        print(f"# No se copian ni se borran: {len(inf.sobran)} sobran en el espejo (se decide en el canónico):")
        for rel in sorted(inf.sobran):
            print(f"#   {rel}")
    adaptados = sorted({r for g, r, _ in inf.divergencias if r in inf.adaptados})
    if adaptados:
        print("# No se copian: adaptados con divergencias (su diferencia es intencional; revisar a mano):")
        for rel in adaptados:
            print(f"#   {rel}")


# ---------------------------------------------------------------------------------------------------------------
# Generación del manifiesto
# ---------------------------------------------------------------------------------------------------------------
def plantilla(nombre_c: str = CANONICO_POR_DEFECTO, nombre_e: str = ESPEJO_POR_DEFECTO) -> dict:
    """Estructura por omisión, para cuando todavía no hay manifiesto. No declara adaptados."""
    propios_comunes = [".gitignore", "README.md", "LICENSE", ".env.example", "data", "docs/index.html",
                       "docs/references/**", "others_files/**", "presentaciones/**", "logs/**", "auditoria/**",
                       "output_files/**/*.log"]
    return {
        "esquema": ESQUEMA,
        "descripcion": ("Componentes ambientales compartidos entre el canónico y su espejo. Todo cambio se hace "
                        "primero en el canónico y se copia al espejo; las diferencias permitidas se declaran en "
                        "«adaptado», con motivo y plan. Rutas relativas a la raíz de cada repositorio."),
        "canonico": {"repo": nombre_c},
        "espejos": [{"repo": nombre_e}],
        "direccion": DIRECCION,
        "ruta_manifiesto": RUTA_MANIFIESTO,
        "excluir_siempre": list(EXCLUIR_SIEMPRE),
        "rutas_prohibidas": list(PROHIBIDOS),
        "grupos": [
            {"nombre": "pipeline", "modo": "identico", "incluir": ["scripts_pipeline/**"]},
            {"nombre": "superficie", "modo": "identico", "incluir": ["scripts_superficie/**"]},
            {"nombre": "estacion", "modo": "identico", "incluir": ["scripts_estacion/**"]},
            {"nombre": "modelo_1km", "modo": "identico", "incluir": ["scripts_modelo_1km/**"]},
            {"nombre": "config", "modo": "identico", "incluir": ["config/**"]},
            {"nombre": "informe_modelo", "modo": "identico",
             "incluir": [QMD_MODELO, INFORME_MODELO, "docs/_tablas_compactas.html", "docs/_pdf_unicode.tex"]},
            {"nombre": "notas_pipeline", "modo": "identico", "incluir": ["docs/*.md"]},
            {"nombre": "utilitarios", "modo": "identico", "incluir": ["others_scripts/**"]},
            {"nombre": "salidas_modelo", "modo": "identico",
             "incluir": ["output_files/modelo_1km*/**", "output_files/figures/**", "output_files/*"]},
            {"nombre": "adaptados", "modo": "adaptado", "archivos": {}},
        ],
        "propios": {nombre_c: list(propios_comunes), nombre_e: [*propios_comunes, "README.en.md"]},
        "hash_codigo": {"definicion": DEFINICION_HASH},
    }


def _git(raiz: Path, *args: str) -> str | None:
    entorno = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    try:
        r = subprocess.run(["git", "--no-optional-locks", "-C", str(raiz), *args], capture_output=True,
                           env=entorno, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.decode("utf-8", "surrogateescape") if r.returncode == 0 else None


def _git_head(raiz: Path) -> str | None:
    """HEAD de ``raiz`` si es la raíz de un repositorio git (no recorre el árbol de trabajo)."""
    arriba = _git(raiz, "rev-parse", "--show-toplevel")
    try:
        if not arriba or Path(arriba.strip()).resolve() != raiz.resolve():
            return None
    except OSError:
        return None
    head = _git(raiz, "rev-parse", "HEAD")
    return head.strip() if head else None


def _estado_git(raiz: Path, rutas: list[str]) -> dict:
    """Commit de anclaje y rutas manifestadas sin confirmar. Usa el índice y ``git diff``: no recorre lo no
    rastreado."""
    head = _git_head(raiz)
    if head is None:
        return {"commit_ancla": None, "rama": None, "rutas_sin_confirmar": None}
    rama = (_git(raiz, "symbolic-ref", "--short", "-q", "HEAD") or "").strip() or None
    rastreadas = _git(raiz, "ls-files", "-z")
    modificadas = _git(raiz, "diff", "--name-only", "-z", "HEAD")
    if rastreadas is None or modificadas is None:
        return {"commit_ancla": head, "rama": rama, "rutas_sin_confirmar": None}
    rastreadas_set = {_nfc(x) for x in rastreadas.split("\0") if x}
    modificadas_set = {_nfc(x) for x in modificadas.split("\0") if x}
    return {"commit_ancla": head, "rama": rama, "rutas_sin_confirmar": {
        "sin_rastrear": sorted(r for r in rutas if r not in rastreadas_set),
        "modificadas": sorted(r for r in rutas if r in modificadas_set)}}


def _ordenar(d: dict, orden: tuple[str, ...]) -> dict:
    return {**{k: d[k] for k in orden if k in d}, **{k: d[k] for k in d if k not in orden}}


def _ordenar_manifiesto(man: dict) -> dict:
    man = _ordenar(man, ORDEN_RAIZ)
    if isinstance(man.get("canonico"), dict):
        man["canonico"] = _ordenar(man["canonico"], ORDEN_CANONICO)
    grupos = []
    for g in man["grupos"]:
        g = _ordenar(g, ORDEN_GRUPO)
        if isinstance(g.get("sha256"), dict):
            g["sha256"] = dict(sorted(g["sha256"].items()))
        if isinstance(g.get("archivos"), dict):
            g["archivos"] = {k: _ordenar(v, ORDEN_ADAPTADO) for k, v in sorted(g["archivos"].items())}
        grupos.append(g)
    man["grupos"] = grupos
    if isinstance(man.get("hash_codigo"), dict):
        man["hash_codigo"] = _ordenar(man["hash_codigo"], ORDEN_HASH)
    return man


def serializar(man: dict) -> str:
    return json.dumps(_ordenar_manifiesto(man), ensure_ascii=False, indent=2) + "\n"


def _ruta_generador(C: Path) -> str:
    propia = Path(__file__).resolve()
    try:
        return propia.relative_to(C.resolve()).as_posix()
    except ValueError:
        return f"others_scripts/{propia.name}"


def construir_manifiesto(base: dict, C: Path, E: Path | None, avisos: list[str]) -> dict:
    """Manifiesto nuevo: la estructura de ``base`` con las huellas tomadas del canónico (y del espejo, para los
    adaptados y su hash_codigo)."""
    man = copy.deepcopy(base)
    man["esquema"], man["direccion"], man["ruta_manifiesto"] = ESQUEMA, DIRECCION, RUTA_MANIFIESTO
    nombre_c, nombre_e = man["canonico"]["repo"], man["espejos"][0]["repo"]
    propios = man.get("propios") or {}

    for g in man["grupos"]:
        if g["modo"] != "adaptado":
            continue
        vigentes = {}
        for rel, d in g["archivos"].items():
            d = dict(d)
            sc = _sha_o_ausente(C, rel)
            se = _sha_o_ausente(E, rel) if E is not None else d.get("sha256_espejo")
            if se is None:
                raise ErrorLectura(f"no se encontró el espejo y {rel} no tiene sha256 del espejo previo")
            if sc == se:
                avisos.append(f"adaptado {rel}: ya es igual en los dos lados ({_corto(sc)}); sale de «adaptado»")
                continue
            for lado, nuevo in (("sha256_canonico", sc), ("sha256_espejo", se)):
                if d.get(lado) not in (None, nuevo):
                    avisos.append(f"adaptado {rel}: cambia {lado} ({_corto(d.get(lado))} → {_corto(nuevo)})")
                d[lado] = nuevo
            vigentes[rel] = d
        g["archivos"] = vigentes
    adaptados = {rel for g in man["grupos"] if g["modo"] == "adaptado" for rel in g["archivos"]}

    manifestadas: list[str] = []
    for g in man["grupos"]:
        if g["modo"] != "identico":
            continue
        excluir = [*g.get("excluir", []), *man.get("excluir_siempre", [])]
        archivos, enlaces = expandir(C, g["incluir"], excluir, propios.get(nombre_c, []))
        for rel in sorted(enlaces):
            avisos.append(f"grupo {g['nombre']}: {rel} es un enlace simbólico en el canónico; no se declara")
        for rel in adaptados | {RUTA_MANIFIESTO}:
            archivos.pop(rel, None)
        g["sha256"] = {rel: sha256_archivo(p, rel) for rel, p in sorted(archivos.items())}
        manifestadas += list(g["sha256"])
    if len(manifestadas) != len(set(manifestadas)):
        repetidas = sorted({r for r in manifestadas if manifestadas.count(r) > 1})
        raise ManifiestoInvalido(f"rutas en más de un grupo idéntico: {', '.join(repetidas[:10])}")

    hcod = dict(man.get("hash_codigo") or {})
    hcod.setdefault("definicion", DEFINICION_HASH)
    previo = (hcod.get("observado") or {}).get(nombre_e)
    hc_c = hash_codigo(C)
    hc_e = hash_codigo(E) if E is not None else previo
    hcod["esperado"] = hc_c
    hcod["observado"] = {nombre_c: hc_c, nombre_e: hc_e}
    hcod["declarado_en_informe"] = _huellas_informe(C)
    estampados = (hcod["declarado_en_informe"] or {}).get("codigo") or []
    hace_falta = (hc_e is not None and hc_e != hc_c) or any(x != hc_c for x in estampados)
    if hace_falta and not hcod.get("excepcion"):
        avisos.append("hash_codigo: el espejo o el informe difieren del canónico y no hay excepción: declárala a "
                      "mano en hash_codigo.excepcion (vigente, motivo y plan)")
    if not hace_falta and hcod.get("excepcion"):
        avisos.append("hash_codigo: canónico, espejo e informe coinciden; la excepción ya no hace falta y se quita")
        hcod.pop("excepcion")
    man["hash_codigo"] = hcod

    rutas_git = sorted(set(manifestadas) | adaptados)
    man["canonico"] = {**man["canonico"], **_estado_git(C, rutas_git)}
    man["generado"] = dt.datetime.now().astimezone().replace(microsecond=0).isoformat()
    man["generador"] = {"script": _ruta_generador(C), "sha256": sha256_archivo(Path(__file__).resolve())}
    return man


def _comparable(man: dict) -> dict:
    return {k: v for k, v in man.items() if k != "generado"}


def _resumen_cambios(viejo: dict | None, nuevo: dict) -> list[str]:
    if viejo is None:
        n = sum(len(g.get("sha256") or {}) for g in nuevo["grupos"] if g["modo"] == "identico")
        m = sum(len(g.get("archivos") or {}) for g in nuevo["grupos"] if g["modo"] == "adaptado")
        return [f"Manifiesto nuevo: {n} archivos en grupos idénticos y {m} adaptados."]
    lineas = []
    por_nombre_v = {g.get("nombre"): g for g in viejo.get("grupos", []) if isinstance(g, dict)}
    por_nombre_n = {g.get("nombre"): g for g in nuevo["grupos"]}
    for nombre in [*por_nombre_n, *[x for x in por_nombre_v if x not in por_nombre_n]]:
        a, b = por_nombre_v.get(nombre) or {}, por_nombre_n.get(nombre) or {}
        if b.get("modo", a.get("modo")) == "identico":
            sa, sb = a.get("sha256") or {}, b.get("sha256") or {}
            if not sa and sb:
                lineas.append(f"CAMBIA [{nombre}]: se declaran por primera vez {len(sb)} archivos")
                continue
            propias = [f"CAMBIA [{nombre}] {r}: nuevo" for r in sorted(set(sb) - set(sa))]
            propias += [f"CAMBIA [{nombre}] {r}: ya no está en el canónico" for r in sorted(set(sa) - set(sb))]
            propias += [f"CAMBIA [{nombre}] {r}: sha256 {_corto(sa[r])} → {_corto(sb[r])}"
                        for r in sorted(set(sa) & set(sb)) if sa[r] != sb[r]]
            if len(propias) > 25:
                propias = propias[:20] + [f"CAMBIA [{nombre}] … y {len(propias) - 20} cambios más en este grupo"]
            lineas += propias
        else:
            fa, fb = a.get("archivos") or {}, b.get("archivos") or {}
            for r in sorted(set(fa) | set(fb)):
                if fa.get(r) != fb.get(r):
                    que = ("se declara" if r not in fa else "sale de «adaptado»" if r not in fb
                           else "cambian sus datos o sus sha256")
                    lineas.append(f"CAMBIA [{nombre}] {r}: {que}")
    if viejo.get("hash_codigo") != nuevo.get("hash_codigo"):
        h = nuevo["hash_codigo"]
        lineas.append(f"CAMBIA [hash_codigo]: esperado {h.get('esperado')}, observado {h.get('observado')}")
    if viejo.get("canonico") != nuevo.get("canonico"):
        lineas.append("CAMBIA [canonico]: commit de anclaje o rutas sin confirmar")
    tratadas = {"grupos", "hash_codigo", "canonico", "generado"}
    for clave in sorted((set(viejo) | set(nuevo)) - tratadas):
        if viejo.get(clave) != nuevo.get(clave):
            lineas.append(f"CAMBIA [{clave}]")
    if len(lineas) > MAX_LINEAS_CAMBIOS:
        lineas = lineas[:MAX_LINEAS_CAMBIOS] + [f"… y {len(lineas) - MAX_LINEAS_CAMBIOS} cambios más"]
    return lineas


def _escribir_atomico(ruta: Path, texto: str, antes_reemplazar=None, crear_exclusivo=False) -> None:
    modo = stat.S_IMODE(ruta.stat().st_mode) if ruta.exists() else 0o644
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=f".{ruta.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(texto)
        os.chmod(tmp, modo)
        if antes_reemplazar is not None:
            antes_reemplazar()
        if crear_exclusivo:
            # Publicación atómica sin sobrescribir: también bloquea una aparición después de la revalidación.
            os.link(tmp, ruta, follow_symlinks=False)
            os.unlink(tmp)
        else:
            os.replace(tmp, ruta)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# El modo acotado nunca llama a construir_manifiesto, expandir, hash_codigo ni _huellas_informe.
_COMMIT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
GLOBAL_NO_EJECUTADA = "no_ejecutada"


def _ruta_acotada(rel: object) -> str:
    rel = _validar_ruta(rel, "actualización acotada")
    partes = rel.lower().split("/")
    if (rel != _nfc(rel) or any(ord(c) < 32 for c in rel)
            or any(c in rel for c in "[]{}")
            or any(p in (".git", ".hg", ".svn", ".ssh", ".aws", ".gnupg", ".docker", ".netrc",
                         ".npmrc", ".pypirc") or p.startswith(".env")
                   or "cache" in p or any(x in p for x in ("credencial", "credential", "secret", "token",
                                                           "password", "passwd"))
                   or p in ("id_rsa", "id_ed25519") or p.endswith((".pem", ".key", ".p12", ".pfx", ".keychain"))
                   for p in partes)
            or any(rx.match(rel) for rx in _RX_EXCLUIR_SIEMPRE)
            or rel == RUTA_MANIFIESTO):
        raise ManifiestoInvalido(f"ruta no admisible en actualización acotada: {rel}")
    return rel


def _validar_actualizaciones_acotadas(man: dict) -> None:
    registros = man.get("actualizaciones_acotadas", [])
    if not isinstance(registros, list):
        raise ManifiestoInvalido("actualizaciones_acotadas: se espera una lista")
    for r in registros:
        if not isinstance(r, dict) or set(r) != {
                "base", "fecha_utc", "actualizador", "fuentes", "seleccion", "cambios",
                "alcance", "verificacion_global", "metadatos_globales"}:
            raise ManifiestoInvalido("actualizaciones_acotadas: registro incompleto o desconocido")
        if (r["alcance"] != "rutas_explicitas" or r["verificacion_global"] != GLOBAL_NO_EJECUTADA
                or r["metadatos_globales"] != "historia_de_la_base_sin_refrescar"):
            raise ManifiestoInvalido("actualizaciones_acotadas: alcance o afirmación global inválidos")
        try:
            fecha = dt.datetime.fromisoformat(r["fecha_utc"].replace("Z", "+00:00"))
            if fecha.utcoffset() != dt.timedelta(0):
                raise ValueError
        except (TypeError, AttributeError, ValueError):
            raise ManifiestoInvalido("actualizaciones_acotadas: fecha UTC inválida") from None
        base, act, fuentes = r["base"], r["actualizador"], r["fuentes"]
        if (not isinstance(base, dict) or set(base) != {"sha256", "canonico", "espejo"}
                or not isinstance(base["sha256"], str) or not _HEX64.fullmatch(base["sha256"])
                or not isinstance(act, dict) or set(act) != {"script", "sha256"}
                or not isinstance(act["sha256"], str) or not _HEX64.fullmatch(act["sha256"])
                or not isinstance(fuentes, dict) or set(fuentes) != {"canonico", "espejo"}):
            raise ManifiestoInvalido("actualizaciones_acotadas: base, actualizador o fuentes inválidos")
        _validar_ruta(act["script"], "actualizador.script")
        for lado, repo in (("canonico", man["canonico"]["repo"]), ("espejo", man["espejos"][0]["repo"])):
            b, f = base[lado], fuentes[lado]
            if (not isinstance(b, dict) or set(b) != {"commit", "ruta"}
                    or b["ruta"] != RUTA_MANIFIESTO or not isinstance(b["commit"], str)
                    or not _COMMIT.fullmatch(b["commit"])
                    or not isinstance(f, dict) or set(f) != {"repo", "commit"} or f["repo"] != repo
                    or not isinstance(f["commit"], str) or not _COMMIT.fullmatch(f["commit"])):
                raise ManifiestoInvalido("actualizaciones_acotadas: procedencia Git inválida")
        seleccion = r["seleccion"]
        if not isinstance(seleccion, list) or not seleccion:
            raise ManifiestoInvalido("actualizaciones_acotadas: selección vacía o inválida")
        por_ruta = {}
        for x in seleccion:
            if not isinstance(x, dict) or set(x) != {"ruta", "grupo", "sha256"}:
                raise ManifiestoInvalido("actualizaciones_acotadas: selección inválida")
            rel = _ruta_acotada(x["ruta"])
            if (rel in por_ruta or not isinstance(x["sha256"], str) or not _HEX64.fullmatch(x["sha256"])
                    or _grupo_acotado(man, rel)["nombre"] != x["grupo"]):
                raise ManifiestoInvalido("actualizaciones_acotadas: selección repetida o inconsistente")
            por_ruta[rel] = x
        cambios = r["cambios"]
        if not isinstance(cambios, list) or not cambios:
            raise ManifiestoInvalido("actualizaciones_acotadas: cambios vacíos o inválidos")
        vistos = set()
        for x in cambios:
            if not isinstance(x, dict) or set(x) != {"ruta", "grupo", "anterior", "nuevo"}:
                raise ManifiestoInvalido("actualizaciones_acotadas: cambio inválido")
            rel, anterior = x["ruta"], x["anterior"]
            if (not isinstance(rel, str) or rel not in por_ruta or rel in vistos
                    or x["grupo"] != por_ruta[rel]["grupo"] or x["nuevo"] != por_ruta[rel]["sha256"]
                    or anterior == x["nuevo"] or (anterior is not None
                    and (not isinstance(anterior, str) or not _HEX64.fullmatch(anterior)))):
                raise ManifiestoInvalido("actualizaciones_acotadas: cambio fuera de selección o inválido")
            vistos.add(rel)


def _grupo_acotado(man: dict, rel: str) -> dict:
    if any(rel in g.get("archivos", {}) for g in man["grupos"] if g["modo"] == "adaptado"):
        raise ManifiestoInvalido(f"{rel}: es adaptado, no se actualiza como idéntico")
    propios = man.get("propios", {})
    lados = (man["canonico"]["repo"], man["espejos"][0]["repo"])
    candidatos = []
    for g in man["grupos"]:
        if g["modo"] != "identico":
            continue
        fuera = [*EXCLUIR_SIEMPRE, *man.get("excluir_siempre", []), *g.get("excluir", [])]
        fuera += [p for repo in lados for p in propios.get(repo, [])]
        if (any(patron_a_regex(p).fullmatch(rel) for p in g["incluir"])
                and not any(patron_a_regex(p).fullmatch(rel) for p in fuera)):
            candidatos.append(g)
    if len(candidatos) != 1:
        raise ManifiestoInvalido(f"{rel}: requiere exactamente un grupo idéntico efectivo ({len(candidatos)})")
    return candidatos[0]


def _git_acotado(repo: Path, *args: str) -> bytes:
    entorno = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    entorno["GIT_OPTIONAL_LOCKS"] = "0"
    entorno["GIT_GRAFT_FILE"] = os.devnull  # Ignorar también .git/info/grafts, no sólo refs/replace.
    try:
        r = subprocess.run(["git", "--no-optional-locks", "--no-replace-objects", "--literal-pathspecs", "-c", "core.fsmonitor=false",
                            "-C", str(repo), *args], capture_output=True, env=entorno, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ErrorLectura(f"Git no disponible para actualización acotada: {type(exc).__name__}") from None
    if r.returncode:
        raise ErrorLectura(f"Git falló en {repo.name}: {args[0]}")
    return r.stdout


def _head_acotado(repo: Path) -> str:
    arriba = _git_acotado(repo, "rev-parse", "--show-toplevel").decode().strip()
    if Path(arriba).resolve() != repo.resolve():
        raise ErrorLectura(f"{repo.name}: no es raíz de un repositorio Git")
    head = _git_acotado(repo, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    if not _COMMIT.fullmatch(head):
        raise ErrorLectura("HEAD Git inválido")
    return head


def _capturar_acotado(repo: Path, rutas: list[str]) -> dict:
    head = _head_acotado(repo)
    archivos = {}
    for rel in rutas:
        if _componente_enlazado(repo, rel) or not stat.S_ISREG((repo / rel).lstat().st_mode):
            raise ErrorLectura(f"{rel}: no es archivo regular sin enlaces")
        indice = _git_acotado(repo, "ls-files", "--stage", "-z", "--", rel).split(b"\0")
        arbol = _git_acotado(repo, "ls-tree", "-z", head, "--", rel).split(b"\0")
        nombre = rel.encode("utf-8")
        try:
            entrada, vacio = indice
            meta, ruta = entrada.split(b"\t", 1)
            modo, blob, etapa = meta.split()
            arb, fin = arbol
            meta_head, ruta_head = arb.split(b"\t", 1)
            modo_head, tipo_head, blob_head = meta_head.split()
            valido = (not vacio and not fin and ruta == ruta_head == nombre and etapa == b"0"
                      and modo in (b"100644", b"100755") and tipo_head == b"blob"
                      and modo == modo_head and blob == blob_head)
        except ValueError:
            valido = False
        if not valido:
            raise ErrorLectura(f"{rel}: ausente, sin rastrear o índice distinto de HEAD")
        banderas = _git_acotado(repo, "ls-files", "-v", "-z", "--", rel)
        estado = _git_acotado(repo, "status", "--porcelain=v1", "-z", "--untracked-files=no", "--", rel)
        if banderas != b"H " + nombre + b"\0" or estado:
            raise ErrorLectura(f"{rel}: estado Git modificado u oculto")
        sha_head = hashlib.sha256(_git_acotado(repo, "cat-file", "blob", blob.decode())).hexdigest()
        sha = _sha_o_ausente(repo, rel)
        if sha != sha_head:
            raise ErrorLectura(f"{rel}: bytes distintos de HEAD/índice")
        archivos[rel] = {"sha256": sha, "blob": blob.decode(), "modo": modo.decode()}
    if _head_acotado(repo) != head:
        raise ErrorLectura("HEAD cambió durante la lectura")
    return {"commit": head, "archivos": archivos}


def construir_actualizacion_acotada(base: dict, C: Path, E: Path, rutas: list[str],
                                     base_bytes: bytes, commits_base: dict, fuentes: dict) -> dict:
    """Sólo cambia SHA seleccionadas y añade procedencia parcial; no certifica coherencia global."""
    validar_manifiesto(base, estricto=True)
    man = copy.deepcopy(base)
    seleccion, cambios = [], []
    for rel in rutas:
        g = _grupo_acotado(man, _ruta_acotada(rel))
        nuevo = fuentes["canonico"]["archivos"][rel]["sha256"]
        if nuevo != fuentes["espejo"]["archivos"][rel]["sha256"]:
            raise ErrorLectura(f"{rel}: bytes distintos en el espejo")
        anterior = g["sha256"].get(rel)
        seleccion.append({"ruta": rel, "grupo": g["nombre"], "sha256": nuevo})
        if anterior != nuevo:
            cambios.append({"ruta": rel, "grupo": g["nombre"], "anterior": anterior, "nuevo": nuevo})
            g["sha256"][rel] = nuevo
    if cambios:
        registro = {
            "base": {"sha256": hashlib.sha256(base_bytes).hexdigest(),
                     **{lado: {"commit": commits_base[lado], "ruta": RUTA_MANIFIESTO}
                        for lado in ("canonico", "espejo")}},
            "fecha_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "actualizador": {"script": _ruta_generador(C), "sha256": sha256_archivo(Path(__file__).resolve())},
            "fuentes": {lado: {"repo": repo, "commit": fuentes[lado]["commit"]}
                        for lado, repo in (("canonico", base["canonico"]["repo"]),
                                           ("espejo", base["espejos"][0]["repo"]))},
            "seleccion": seleccion, "cambios": cambios, "alcance": "rutas_explicitas",
            "verificacion_global": GLOBAL_NO_EJECUTADA,
            "metadatos_globales": "historia_de_la_base_sin_refrescar"}
        man.setdefault("actualizaciones_acotadas", []).append(registro)
    validar_manifiesto(man, estricto=True)
    return man


def _sin_fechas_acotadas(man: dict) -> dict:
    man = copy.deepcopy(man)
    for r in man.get("actualizaciones_acotadas", []):
        r.pop("fecha_utc", None)
    return man


def _sin_enlaces_locales(ruta: Path) -> None:
    absoluta = ruta.absolute()
    for parte in (absoluta, *absoluta.parents):
        if parte.name:
            _ruta_acotada(parte.name)
        if parte.is_symlink():
            raise ErrorLectura("ruta local contiene un enlace simbólico")


def _identidad_normalizada(ruta: Path) -> str:
    return _nfc(str(ruta.resolve())).casefold()


def _misma_identidad(a: Path, b: Path) -> bool:
    if _identidad_normalizada(a) == _identidad_normalizada(b):
        return True
    try:
        return a.samefile(b)  # Incluye alias y enlaces duros, también fuera de los repositorios.
    except FileNotFoundError:
        return False


def _proteger_salida_acotada(salida: Path, base: Path, C: Path, E: Path, rutas: list[str]) -> None:
    for local in (salida, base, C, E):
        _sin_enlaces_locales(local)
    normalizada = _identidad_normalizada(salida)
    for repo in (C, E):
        raiz = _identidad_normalizada(repo).rstrip(os.sep)
        if normalizada == raiz or normalizada.startswith(raiz + os.sep):
            raise ErrorLectura("la candidata debe estar fuera de ambos repositorios, incluidos sus alias")
    protegidas = [base, C / RUTA_MANIFIESTO, E / RUTA_MANIFIESTO]
    protegidas += [repo / rel for repo in (C, E) for rel in rutas]
    if any(_misma_identidad(salida, p) for p in protegidas):
        raise ErrorLectura("la salida coincide con base, manifiesto activo o fuente seleccionada")


def _modo_actualizar_acotado(a: argparse.Namespace, C: Path) -> int:
    try:
        for local in (a.base, a.salida):
            _sin_enlaces_locales(local)
            _ruta_acotada(local.name)  # No leer ni escribir credenciales disfrazadas de base/candidata.
        _sin_enlaces_locales(C)
        base_bytes = _leer_bytes(a.base)
        base = json.loads(base_bytes.decode("utf-8"))
        validar_manifiesto(base, estricto=True)
        E = (a.espejo or C.parent / base["espejos"][0]["repo"]).expanduser()
        _sin_enlaces_locales(E)
        if C.resolve() == E.resolve():
            raise ErrorLectura("canónico y espejo no pueden ser el mismo repositorio")
        rutas = sorted(set(_ruta_acotada(r) for r in a.actualizar_ruta))
        for rel in rutas:
            _grupo_acotado(base, rel)
        _proteger_salida_acotada(a.salida, a.base, C, E, rutas)
        fuentes = {lado: _capturar_acotado(repo, rutas) for lado, repo in (("canonico", C), ("espejo", E))}
        commits_base = {}
        for lado, repo, revision in (("canonico", C, a.commit_base_canonico), ("espejo", E, a.commit_base_espejo)):
            revision = revision or fuentes[lado]["commit"]
            if not _COMMIT.fullmatch(revision):
                raise ErrorLectura("la procedencia de base requiere un identificador completo de commit real")
            commit = _git_acotado(repo, "rev-parse", "--verify", revision + "^{commit}").decode().strip()
            if commit != revision or _git_acotado(repo, "show", f"{commit}:{RUTA_MANIFIESTO}") != base_bytes:
                raise ErrorLectura("la base no coincide con el manifiesto de los commits declarados")
            _git_acotado(repo, "merge-base", "--is-ancestor", commit, fuentes[lado]["commit"])
            commits_base[lado] = commit
        previo = _leer_bytes(a.salida) if a.salida.exists() else None
        sha_actualizador = sha256_archivo(Path(__file__).resolve())
        nuevo = construir_actualizacion_acotada(base, C, E, rutas, base_bytes, commits_base, fuentes)
        def revalidar():
            # No reabrir árboles ajenos; también se llama inmediatamente antes del reemplazo atómico.
            _proteger_salida_acotada(a.salida, a.base, C, E, rutas)
            for lado, repo in (("canonico", C), ("espejo", E)):
                if _capturar_acotado(repo, rutas) != fuentes[lado]:
                    raise ErrorLectura("HEAD, índice o fuentes cambiaron durante la actualización")
            if sha256_archivo(Path(__file__).resolve()) != sha_actualizador:
                raise ErrorLectura("el actualizador cambió durante la actualización")
            if _leer_bytes(a.base) != base_bytes:
                raise ErrorLectura("la base cambió durante la actualización")
            _proteger_salida_acotada(a.salida, a.base, C, E, rutas)
            if (_leer_bytes(a.salida) if a.salida.exists() else None) != previo:
                raise ErrorLectura("la candidata cambió durante la actualización")
        revalidar()
        igual = False
        if previo is not None:
            try:
                anterior = json.loads(previo)
                validar_manifiesto(anterior, estricto=True)
                igual = _sin_fechas_acotadas(anterior) == _sin_fechas_acotadas(nuevo)
            except (UnicodeDecodeError, json.JSONDecodeError, ManifiestoInvalido):
                pass
        if igual:
            print("Sin cambios: candidata acotada idéntica; no se reescribe. Verificación global no ejecutada.")
            return 0
        if previo is not None:
            raise ErrorLectura("salida existente: sólo se admite una candidata válida e idéntica de esta operación")
        cambios = nuevo.get("actualizaciones_acotadas", [])
        n = len(cambios[-1]["cambios"]) if len(cambios) > len(base.get("actualizaciones_acotadas", [])) else 0
        print(f"Actualización acotada: {len(rutas)} rutas seleccionadas, {n} huellas cambiadas; resto conservado; "
              "verificación global no ejecutada.")
        if n == 0:
            print("Sin cambios de huellas: no se añade registro ni se escribe candidata.")
            return 0
        if not a.forzar:
            print("No se escribió: vista previa. Usa --forzar para escribir únicamente la candidata separada.")
            return 1 if n or previo is not None else 0
        _escribir_atomico(a.salida, serializar(nuevo), antes_reemplazar=revalidar, crear_exclusivo=True)
        print(f"Candidata escrita: {_relativa(a.salida)}. No se instaló ni copió ningún manifiesto activo.")
        return 0
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ManifiestoInvalido, ErrorLectura) as exc:
        print(f"ERROR actualización acotada: {exc}", file=sys.stderr)
        return 2


def _modo_generar(a: argparse.Namespace, C: Path, ruta_man: Path) -> int:
    existente = None
    if ruta_man.exists():
        try:
            existente = json.loads(_leer_bytes(ruta_man).decode("utf-8"))
            validar_manifiesto(existente, estricto=False)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ManifiestoInvalido) as exc:
            print(f"ERROR el manifiesto existente no es válido ({exc}); corrígelo o apártalo antes de generar",
                  file=sys.stderr)
            return 2
        base = existente
    else:
        base = plantilla(C.name, a.espejo.name if a.espejo else ESPEJO_POR_DEFECTO)
    if a.canonico is None and C.name != base["canonico"]["repo"]:
        print(f"ERROR la carpeta inferida {C.name} no es el canónico del manifiesto "
              f"({base['canonico']['repo']}); usa --canonico", file=sys.stderr)
        return 2
    E = (a.espejo or C.parent / base["espejos"][0]["repo"]).expanduser()
    avisos: list[str] = []
    if not E.is_dir():
        avisos.append(f"no se encontró el espejo ({_relativa(E)}); se conservan sus valores previos")
        E = None
    try:
        nuevo = construir_manifiesto(base, C, E, avisos)
        validar_manifiesto(nuevo, estricto=True)
    except ErrorLectura as exc:
        print(f"ERROR de lectura: {exc}", file=sys.stderr)
        return 2
    except ManifiestoInvalido as exc:
        print(f"ERROR el manifiesto generado no es válido: {exc}", file=sys.stderr)
        return 2
    for aviso in avisos:
        print(f"AVISO {aviso}")
    if existente is not None and _comparable(existente) == _comparable(json.loads(serializar(nuevo))):
        print(f"Sin cambios: {RUTA_MANIFIESTO} ya corresponde al canónico; no se reescribe.")
        return 0
    for linea in _resumen_cambios(existente, nuevo):
        print(linea)
    if existente is not None and not a.forzar:
        print("No se escribió: el manifiesto cambiaría. Repite con --forzar para sobrescribirlo.")
        return 1
    _escribir_atomico(ruta_man, serializar(nuevo))
    n = sum(len(g["sha256"]) for g in nuevo["grupos"] if g["modo"] == "identico")
    m = sum(len(g["archivos"]) for g in nuevo["grupos"] if g["modo"] == "adaptado")
    print(f"Escrito {_relativa(ruta_man)}: {n} archivos en grupos idénticos, {m} adaptados, hash_codigo "
          f"{nuevo['hash_codigo']['esperado']}. Cópialo al espejo y corre el comprobador allí.")
    return 0


# ---------------------------------------------------------------------------------------------------------------
# Registro y programa principal
# ---------------------------------------------------------------------------------------------------------------
def registrar(ruta: Path, inf: Informe | None, man: dict, man_bytes: bytes, C: Path, E: Path, codigo: int,
              error: str | None = None) -> None:
    por_grupo: dict[str, int] = {}
    for grupo, _, _ in (inf.divergencias if inf else []):
        por_grupo[grupo] = por_grupo.get(grupo, 0) + 1
    linea = {
        "fecha_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "resultado": {0: "coherente", 1: "divergente"}.get(codigo, "error"),
        "codigo_salida": codigo,
        "divergencias": len(inf.divergencias) if inf else None,
        "divergencias_por_grupo": por_grupo,
        "error": error,
        "manifiesto": {"ruta": RUTA_MANIFIESTO, "sha256": hashlib.sha256(man_bytes).hexdigest(),
                       "generado": man.get("generado")},
        "canonico": {"repo": man["canonico"]["repo"], "carpeta": C.name, "head": _git_head(C)},
        "espejo": {"repo": man["espejos"][0]["repo"], "carpeta": E.name, "head": _git_head(E)},
        "hash_codigo": inf.hash if inf else None,
        "comprobador_sha256": sha256_archivo(Path(__file__).resolve()),
    }
    with open(ruta, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(linea, ensure_ascii=False, sort_keys=True) + "\n")


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Comprueba los componentes compartidos entre Air-Pollution (canónico) y "
                    "Air-Pollution-Health-Chile (espejo) contra config/componentes_compartidos.json.",
        epilog="Salida: 0 coherente al verificar/éxito operativo al generar o actualizar; "
               "1 divergencia o vista previa con cambios; 2 entrada inválida o error de lectura.")
    p.add_argument("--canonico", type=Path, help="raíz del canónico (por omisión, la carpeta hermana Air-Pollution)")
    p.add_argument("--espejo", type=Path,
                   help="raíz del espejo (por omisión, la carpeta hermana del canónico con el nombre del manifiesto)")
    p.add_argument("--manifiesto", type=Path, help=f"manifiesto (por omisión, <canónico>/{RUTA_MANIFIESTO})")
    modo = p.add_mutually_exclusive_group()
    modo.add_argument("--plan", action="store_true", help="imprime, sin ejecutarlo, el rsync del canónico al espejo")
    modo.add_argument("--generar", action="store_true", help="regenera el manifiesto desde el canónico")
    modo.add_argument("--actualizar-ruta", action="append", metavar="RUTA",
                      help="actualización acotada de una ruta literal; repetible; sólo candidata separada")
    p.add_argument("--base", type=Path, help="base explícita y estricta, idéntica a la confirmada en ambos Git")
    p.add_argument("--salida", type=Path, help="candidata externa nueva; existente sólo si es idéntica de esta operación")
    p.add_argument("--commit-base-canonico", help="commit completo real que contiene la base (omisión: HEAD)")
    p.add_argument("--commit-base-espejo", help="commit completo real que contiene la base (omisión: HEAD)")
    p.add_argument("--forzar", action="store_true", help="escribe con --generar o --actualizar-ruta")
    p.add_argument("--registrar", type=Path, metavar="JSONL", help="añade el resultado como una línea JSON")
    a = p.parse_args(argv)
    if a.forzar and not (a.generar or a.actualizar_ruta):
        p.error("--forzar sólo vale con --generar o --actualizar-ruta")
    if a.registrar and (a.generar or a.actualizar_ruta):
        p.error("--registrar no vale con generación o actualización acotada")
    if a.actualizar_ruta:
        if a.base is None or a.salida is None or a.manifiesto is not None:
            p.error("--actualizar-ruta exige --base y --salida; no admite --manifiesto")
    elif any(x is not None for x in (a.base, a.salida, a.commit_base_canonico, a.commit_base_espejo)):
        p.error("--base/--salida/--commit-base-* sólo valen con --actualizar-ruta")
    return a


def _carpeta_de_hermanas() -> Path:
    """Carpeta que contiene los dos repositorios: la madre del repositorio de este script (others_scripts/..)."""
    propia = Path(__file__).resolve()
    return propia.parents[2] if len(propia.parents) > 2 else Path.cwd()


def main(argv: list[str] | None = None) -> int:
    a = _argumentos(argv)
    C = (a.canonico or _carpeta_de_hermanas() / CANONICO_POR_DEFECTO).expanduser()
    if not C.is_dir():
        print(f"ERROR no existe el canónico: {_relativa(C)} (usa --canonico)", file=sys.stderr)
        return 2
    ruta_man = (a.manifiesto or C / RUTA_MANIFIESTO).expanduser()
    if a.actualizar_ruta:
        return _modo_actualizar_acotado(a, C)
    if a.generar:
        return _modo_generar(a, C, ruta_man)

    try:
        man_bytes = _leer_bytes(ruta_man)
        man = json.loads(man_bytes.decode("utf-8"))
        validar_manifiesto(man, estricto=True)
    except FileNotFoundError:
        print(f"ERROR no existe el manifiesto {_relativa(ruta_man)} (créalo con --generar)", file=sys.stderr)
        return 2
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"ERROR manifiesto inválido: no es JSON ({exc})", file=sys.stderr)
        return 2
    except ManifiestoInvalido as exc:
        print(f"ERROR manifiesto inválido: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR no se pudo leer el manifiesto: {exc.strerror or exc}", file=sys.stderr)
        return 2
    if a.canonico is None and C.name != man["canonico"]["repo"]:
        print(f"ERROR la carpeta inferida {C.name} no es el canónico del manifiesto ({man['canonico']['repo']}); "
              "usa --canonico", file=sys.stderr)
        return 2
    E = (a.espejo or C.parent / man["espejos"][0]["repo"]).expanduser()
    if not E.is_dir():
        print(f"ERROR no existe el espejo: {_relativa(E)} (usa --espejo)", file=sys.stderr)
        return 2

    inf, error = None, None
    try:
        inf = verificar(man, C, E, man_bytes)
    except ErrorLectura as exc:
        error = str(exc)
    except Exception as exc:  # un manifiesto raro nunca debe confundirse con una divergencia (código 1)
        error = f"error inesperado ({type(exc).__name__}: {exc})"
    if inf is not None:
        imprimir_informe(inf, man)
        if a.plan:
            imprimir_plan(inf, C, E)
        codigo = 1 if inf.divergencias else 0
    else:
        print(f"ERROR de lectura: {error}", file=sys.stderr)
        codigo = 2
    if a.registrar:
        try:
            registrar(a.registrar, inf, man, man_bytes, C, E, codigo, error)
        except (OSError, ErrorLectura) as exc:
            print(f"ERROR no se pudo escribir el registro: {exc}", file=sys.stderr)
            return 2
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
