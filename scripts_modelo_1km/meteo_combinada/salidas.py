"""La única escritura del paquete (§8 del texto; §0, regla 8, del diseño): atómica, vigilada por ``ceguera``, con
esquemas de ``tipos``, recibo, sello y privacidad; y la publicación de M5, como paso aparte.

Todo otro módulo es puro y devuelve tablas, diccionarios o bytes; sólo este módulo los lleva al disco.
- ``escribir(ruta, contenido, *, clase, …)``: guardas de la ruta (léxica y después resuelta), clase fijada por la ruta,
  contenido en bytes deterministas, ``ceguera.vigilar_salida``, privacidad, centinelas del residuo y escritura atómica.
  Devuelve el sha256 de los bytes escritos.
- ``agregar_linea``: una línea más en un archivo sólo agregado (``avance.jsonl``, ``intentos_*.jsonl``).
- ``inventario``, ``escribir_sha256``, ``recibo_corrida`` y ``sellar_corrida``: la cadena de huellas (§8).
- ``corrida_en_curso`` y ``vigilar_residuo``: contextos (la corrida en que se escribe, por hilo, y las
  ``ceguera.GuardaResiduo`` activas, en todo el proceso).
- ``fallas_de_cierre``, ``carpeta_publicacion`` y ``publicar_m5``: la publicación de M5 (§8, «Publicación (M5)»).

Dueño: I17 (ola 4; corregido tras la revisión independiente de la ola 4, hallazgos H1 a H17).
Lecturas propias (SLD-n), para el addendum de M1:
- SLD-1. **La raíz y la carpeta de la corrida** (§8: «Salidas en ``LOCAL/meteo_combinada/v1/<ETIQUETA>/``, nunca en
  ``/Volumes``»; ENT-4; H1). ``escribir`` escribe sólo bajo la raíz que se le indica: ``raiz=``, o la del contexto
  ``corrida_en_curso(carpeta)`` más interior **de este hilo**; sin ninguna de las dos se niega. La raíz es una ruta
  absoluta sin «..» y sólo puede tener una de las formas de ENT-4, sin distinguir mayúsculas: bajo
  ``LOCAL/meteo_combinada/v1`` (léxica y resuelta), ``v1/m1[/<sub>]``, ``v1/m2a[/<sub>]``, ``v1/<ETIQUETA>`` o
  ``v1/<ETIQUETA>/m6``; en la carpeta temporal del sistema, lo mismo bajo un ``meteo_combinada/v1`` (como
  ``entorno.rutas_sinteticas``) o, sin él, una carpeta temporal (hija directa de la carpeta temporal del sistema) que
  hace de corrida, con a lo más una subcarpeta. **La carpeta de la corrida** es la hija de ``v1`` (o esa carpeta
  temporal); ni ella ni nada entre ella y la raíz es un enlace (su nombre léxico y el resuelto coinciden, y su carpeta
  madre resuelta es la de su ruta resuelta). Nunca bajo /Volumes ni en AP o APH. **El cerrojo** (§10; P92; PED-2 de
  I22): ``v1/cerrojo`` (en la carpeta temporal, bajo un ``meteo_combinada/v1``; sin él, una subcarpeta «cerrojo» es una
  más) es también una raíz admitida, sin subcarpetas, para que toda corrida vea los archivos sólo agregado del
  cerrojo; allí sólo se escriben ``intentos_*.jsonl`` (procedencia, sin «.gz» ni subcarpetas), con las mismas guardas
  de ruta, clase y privacidad, y ninguna otra cosa (tampoco ``sha256.json`` ni un recibo).
- SLD-2. **Guardas de la ruta: primero la léxica, después la resuelta** (lección de los 7 accesos de C1 del reloj).
  Toda ruta se normaliza antes: sin el prefijo ``/System/Volumes/Data`` (en macOS, otro nombre de la raíz, por donde se
  llega a /Volumes, a la carpeta de usuarios y a /private; H6). La ruta (relativa a la raíz o absoluta dentro de ella)
  no lleva «..» ni termina en «.part». Primero, sin tocar el disco, el destino y su «.part»: ni /Volumes ni AP ni APH,
  sin distinguir mayúsculas (APFS no las distingue), y estrictamente dentro de la raíz. Después, la ruta resuelta
  componente a componente con la guarda propia (``_resolver``, copia del patrón de ``entorno._resolver_seguro`` que
  además ve el prefijo de arriba y nunca consulta un componente bajo /Volumes), **antes** que las de ``entorno``
  (``prohibido_volumes`` y ``prohibido_repositorios``, que vienen del reloj, distinguen mayúsculas y no ven el prefijo:
  diferencia anotada, PED-1): un enlace que lleve a /Volumes, a AP, a APH o fuera de la raíz resuelta se niega. Un
  «.part» que ya existe (de una escritura interrumpida, o plantado como enlace o vínculo duro) detiene la escritura: no
  se escribe sobre él (pregunta P-SAL-8 para I20). Las violaciones de ruta son ``PermissionError`` y sus mensajes nunca
  citan una ruta absoluta.
- SLD-3. **La clase la fija la ruta** (D3, D13, D14 y D53; A22; H1). Se busca con ``ceguera.clase_de_ruta`` sobre el
  nombre relativo a **la carpeta de la corrida** (SLD-1), no a la raíz: con la raíz en ``<ETIQUETA>/m6`` el nombre
  empieza con «m6/» (en minúsculas, aunque la carpeta se escriba «M6»). Los recibos archivados
  (``recibos/recibo_<n>.json``, procedencia) los fija ``ceguera`` en la raíz de la corrida y en ``m6/`` (PED-6,
  resuelto por I4); ``CLASES_PROPIAS`` los fija con cualquier otro prefijo en que ``ceguera`` no da clase (una raíz
  ``v1/m1/<sub>`` o una subcarpeta de la corrida temporal: ``<sub>/recibos/recibo_<n>.json``), para que también allí
  se pueda volver a sellar; donde ``ceguera`` da una clase, manda la suya. Si la
  fijada y la declarada difieren, se rechaza (``SalidaProhibida``), también entre métrica y resumen: más estricto que
  ``ceguera.vigilar_salida``. **Una ruta que no fija clase sólo se declara métrica, resumen o documento**, las clases
  que miran el contenido; nunca insumo ni procedencia (H16, la lectura más estricta; pregunta P-SAL-6).
- SLD-4. **Del contenido a los bytes.** Bytes, tal cual; texto, en UTF-8; diccionario, lista o tupla, en JSON canónico
  (``entorno.json_canonico``: claves ordenadas, sin NaN) sólo en ``.json``, y en ``.jsonl`` una línea canónica por
  elemento; un DataFrame, sólo con un ``tipos.Esquema`` de ``tipos.ESQUEMAS`` (``validar_esquema``), en ``.parquet``
  o en ``.csv``. Los de ``tipos.ESQUEMAS_EN_MEMORIA`` nunca se escriben. En el parquet, la versión del esquema va en
  los metadatos como los ``attrs`` de pandas (``PANDAS_ATTRS``: ``{"esquema": versión}``, y ``"metadatos"`` si se
  pasan con ``metadatos=``), así que ``pandas.read_parquet`` devuelve ``attrs["esquema"]`` como
  ``tipos.tabla_vacia``. El índice y los demás ``attrs`` no se guardan; un ``attrs["esquema"]`` distinto se rechaza.
  Un parquet sólo sale de un DataFrame: unos bytes que son un parquet, también dentro de un gzip, y un nombre con
  «.parquet» que no viene de un DataFrame se rechazan (H8). **Límite declarado:** un CSV no tiene metadatos, así que
  ``qc/no_normalizables.csv`` va sin la versión de su esquema (pregunta P-SAL-3).
- SLD-5. **Bytes deterministas** (S9). JSON canónico; parquet con ``pyarrow`` (compresión «snappy», sin índice, con
  los metadatos de arriba); CSV sin índice y con «\\n». Mismas entradas, mismo sha256, con las versiones fijadas.
- SLD-6. **Privacidad, en toda clase** (§8; la regla del reloj). Ni la ruta de la carpeta de usuario, ni la carpeta
  personal, ni la arroba (``entorno.sin_datos_privados``) en el nombre ni en ningún texto: el texto UTF-8 entero y, si
  es JSON o JSONL, sus textos ya decodificados (una arroba escrita como escape); en un parquet, columnas, metadatos y
  celdas de texto; en un NetCDF, nombres, atributos y variables de texto; un gzip se descomprime. Lo comprimido de
  otra forma (bz2, xz, zip, 7z, zstd, lz4), por su contenido o por su extensión, se rechaza: no se puede verificar
  (H7). En un binario sin forma conocida sólo se buscan la carpeta de usuario y la personal: la arroba suelta es un
  byte común en los números.
- SLD-7. **Centinelas del residuo** (S7, §0.4.6). ``vigilar_residuo(guarda)`` activa una ``ceguera.GuardaResiduo``
  en este proceso (en todos sus hilos); mientras dure, toda salida de toda clase se busca con cada guarda activa
  sobre sus bytes finales, y con un centinela no se escribe. Fuera del contexto no hay guarda.
- SLD-8. **Sólo agregado** (§8 y §10: ``avance.jsonl`` e ``intentos_*.jsonl``, también con «.gz», que se rechaza: un
  archivo sólo agregado no se comprime; H8). ``escribir`` sobre uno de ellos exige que el contenido nuevo empiece con
  el que hay (y que éste termine en «\\n»). ``agregar_linea`` agrega una línea JSON canónica con ``O_APPEND`` y fsync
  (y fsync de la carpeta si creó el archivo; H13), sin reescribir el archivo, y devuelve el sha256 de la línea; si la
  última línea no termina en «\\n» (una escritura interrumpida), se niega: no se repara sola. Un enlace o un archivo
  con otro vínculo duro (``st_nlink`` distinto de 1, también sobre el descriptor abierto; H3) se niega. Un solo
  proceso agrega a cada archivo (el principal).
- SLD-9. **``sha256.json``** (D14, procedencia): ``{"esquema": "meteo-combinada-sha256/1", "archivos": {ruta relativa:
  {"sha256", "bytes"}}}`` de todo archivo regular de la carpeta, salvo ``sha256.json`` y ``recibo_corrida.json`` de
  su raíz. Un «.part» (escritura incompleta), un enlace simbólico u otro tipo de archivo detienen el inventario.
- SLD-10. **``recibo_corrida.json``** (§8, «Cadena de huellas»; D3 y D12): ``{"esquema": "meteo-combinada-recibo/1",
  "huellas": {ruta por alias: sha256 o {"sha256", "bytes"}}, "entorno": {…}}``, con sha256 de 64 caracteres,
  ningún decimal y enteros sólo bajo ``ceguera.CLAVES_ENTERAS``; como se publica, ningún texto es una ruta absoluta
  ni empieza con «~/». ``sellar_corrida`` escribe ``sha256.json`` y después el recibo, que cita la huella de
  ``sha256.json`` por su ruta por alias. **Un recibo nunca se borra ni se sobrescribe** (H4, pregunta P-SAL-2): al
  sellar de nuevo, el anterior se copia con sus mismos bytes a ``recibos/recibo_<n>.json`` y, para que siga pudiendo
  verificarse, también el ``sha256.json`` que cita, a ``recibos/recibo_<n>_sha256.json`` (PED-6 de I20); los dos son
  procedencia, entran al nuevo ``sha256.json`` y el nuevo recibo cita sus huellas. Antes de archivar se exige que el
  recibo anterior cite el ``sha256.json`` de la corrida y que ése sea el que hay (si cambió después del recibo, no se
  archiva un par que no se verifica). ``escribir`` se niega a reemplazar un recibo cuyos bytes no estén ya en
  ``recibos/``, y a cambiar un archivo de ``recibos/``. ``fallas_de_sello_archivado(carpeta, n)`` verifica un sello
  archivado: el recibo cita la huella de su ``sha256.json`` archivado, y cada archivo que éste lista sigue con esa
  huella; en los sólo agregado (SLD-8), la huella es la de sus primeros «bytes» (lo que había al sellar).
  ``recibos/recibo_<n>_sha256.json`` calza con el patrón ``recibos/recibo_*.json`` que ``ceguera`` ya fija como
  procedencia en la raíz y en ``m6/`` (un nombre como ``recibos/sha256_<n>.json`` no tiene clase y en ``m6/`` sería
  resumen por la carpeta).
- SLD-11. **Cuándo una corrida está cerrada** (para ``publicar_m5``; ``fallas_de_cierre``). Su carpeta se llama
  ``HUMAN<AAAAMMDD>_METEO_COMB_<n>[_ERRATA<k>]`` (sin distinguir mayúsculas); no tiene «.part», enlaces ni archivos de
  otro tipo; tiene ``recibo_corrida.json`` y ``sha256.json`` que pasan la guarda de la procedencia; el recibo cita, por
  ``…/<ETIQUETA>/sha256.json``, la huella actual de ``sha256.json``; ``sha256.json`` lista exactamente los archivos de
  la carpeta (también ``m6/``, ``recibos/``, ``avance.jsonl`` e ``intentos_*.jsonl``); hay ``decision.json`` y
  ``politicas/politicas_meteo_v1.json``; y están los productos de M5: algún archivo en ``producto_01deg/``,
  ``salud/civil/``, ``salud/utc4/``, ``salud/regional/``, ``salud/representatividad/``, ``salud/cronico/`` y
  ``ambiental/``. **En curso** está toda corrida abierta con ``corrida_en_curso`` en cualquier hilo de este proceso:
  mientras haya una, ``publicar_m5`` se niega.
- SLD-12. **Qué publica M5** (§8: «``decision.json``, los resúmenes y las huellas»; §2.1, paso 4, y MC-53: «la
  política publicada»; H17). ``decision.json``; ``politicas/politicas_meteo_v1.json``; los archivos de clase resumen
  fuera de ``m6/``; y las huellas: los recibos archivados (``recibos/``), ``sha256.json`` y ``recibo_corrida.json``.
  Los productos se quedan en LOCAL: se publican sus huellas. ``validacion/`` (métrica) y ``m6/`` (de M6) no se publican
  (pregunta P-SAL-1). Cada archivo se copia byte a byte, con su sha256 comprobado contra ``sha256.json`` (y el de
  ``sha256.json`` contra el recibo), y pasa otra vez la guarda de su clase, la privacidad y la regla de las rutas
  absolutas del reloj (SAL-5 de ``reloj_dmc.salidas``: «/a/…» o «~/…»).
- SLD-13. **Dónde publica** (§8: ``AP/config/meteorologia/meteo_combinada/v1/``). ``destino_ap`` es la raíz de AP
  (la real, ``entorno.rutas_reales().ap``) o, en las pruebas, una carpeta bajo la carpeta temporal del sistema; nunca
  /Volumes, APH ni una carpeta dentro de la corrida. **Con el AP real, la corrida es una hija de
  ``LOCAL/meteo_combinada/v1``**, en su forma léxica y en la resuelta (H11). La subcarpeta conserva las rutas relativas
  de la corrida y no puede pasar por un enlace (su ruta resuelta es la de ``destino_ap`` resuelta más la subruta;
  H10). La escritura es atómica y propia («.part» nuevo con ``O_EXCL``, fsync, renombre y fsync de la carpeta; H13).
  Si la subcarpeta ya trae algunos de los archivos, cada uno con su huella, y ninguno más, se completan los que faltan
  (una publicación interrumpida); si los trae todos, no se escribe nada; si trae otros o distintos, se niega (una
  errata se publica aparte: §10, pregunta P-SAL-5). El espejo en APH y el commit no los hace este módulo.
- SLD-14. **El nombre de una salida** (H12): cada nombre relativo a la carpeta de la corrida tiene ya, al escribirse,
  la forma que exige ``sha256.json`` (sin espacios, decimales ni datos privados; la guarda de la procedencia de
  ``ceguera``), para no descubrirlo al sellar.
- SLD-15. **Declaraciones EMC3 del addendum (D65).** Antes de escribir addendum_m1.json o .md (también .gz),
  ``addendum`` valida las dos declaraciones exactas y post_hoc booleano True. La guarda documental general se conserva.
  Dependencia técnica [delegada]: salidas → addendum, puro y sin dependencia inversa; ver §1 del diseño.
Depende de: tipos, entorno, ceguera, addendum (umbrales, que el diseño permite, no hace falta). pyarrow, pandas y netCDF4 se
cargan sólo al llamarse.
"""
from __future__ import annotations

import fnmatch
import gzip
import hashlib
import io
import json
import os
import re
import stat as _stat
import tempfile
import threading
from collections import deque
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping

from meteo_combinada import addendum, ceguera, entorno, tipos
from meteo_combinada.ceguera import SalidaProhibida

# ---------------------------------------------------------------------------
# Nombres (§8 del texto; D14)
# ---------------------------------------------------------------------------
RECIBO = "recibo_corrida.json"
SHA256_JSON = "sha256.json"
DECISION = "decision.json"
POLITICA = "politicas/politicas_meteo_v1.json"                          # §8; la política publicada (H17)
CARPETA_RECIBOS = "recibos"                                              # SLD-10 (H4)
SUFIJO_PARCIAL = ".part"
ESQUEMA_RECIBO = "meteo-combinada-recibo/1"
ESQUEMA_SHA256 = "meteo-combinada-sha256/1"
SOLO_AGREGADO = ("avance.jsonl", "intentos_*.jsonl")                   # §8 y §10: sólo agregado (SLD-8)
SUBRUTA_PUBLICACION = "config/meteorologia/meteo_combinada/v1"          # §8, «Publicación (M5)»
CARPETA_M6 = "m6"                                                        # ENT-4: <ETIQUETA>/m6
CARPETA_CERROJO = "cerrojo"                                              # SLD-1: v1/cerrojo (§10; P92)
ARCHIVOS_CERROJO = ("intentos_*.jsonl",)                                 # lo único que se escribe en el cerrojo
COMPUERTAS_CON_SUBCARPETA = ("m1", "m2a")                               # ENT-4: v1/m1[/<sub>], v1/m2a[/<sub>]
PRODUCTOS_M5 = ("producto_01deg", "salud/civil", "salud/utc4", "salud/regional", "salud/representatividad",
                "salud/cronico", "ambiental")                            # SLD-11
PATRON_RECIBO_ARCHIVADO = "recibos/recibo_*.json"                       # SLD-10 (H4)
CLASES_PROPIAS: Mapping[str, str] = {PATRON_RECIBO_ARCHIVADO: "procedencia"}    # SLD-3: donde ceguera no da clase
CLASES_SIN_RUTA = ("metrica", "resumen", "documento")                   # SLD-3 (H16): las que miran el contenido
CLAVE_ATTRS = b"PANDAS_ATTRS"         # la clave con que pandas guarda y relee ``attrs`` en un parquet (SLD-4)
COMPRESION_PARQUET = "snappy"

_GZIP = b"\x1f\x8b"
_PAR1 = b"PAR1"
_NETCDF = (b"CDF", b"\x89HDF\r\n\x1a\n")          # NetCDF clásico y NetCDF-4 (HDF5), como ceguera
# SLD-6 (H7): comprimidos que no se descomprimen (bz2 va aparte: «BZh» y una cifra).
_COMPRIMIDOS = (b"\xfd7zXZ\x00", b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08", b"7z\xbc\xaf\x27\x1c",
                b"\x28\xb5\x2f\xfd", b"\x04\x22\x4d\x18", b"\x5d\x00\x00")
_BZ2 = re.compile(rb"BZh[1-9]")
_EXTENSIONES_COMPRIMIDAS = (".bz2", ".xz", ".lzma", ".zip", ".7z", ".zst", ".lz4", ".tbz2", ".txz")
_ALIAS_RAIZ = ("system", "volumes", "data")            # SLD-2 (H6): /System/Volumes/Data
_USUARIOS = ("/" + "Users" + "/").encode("utf-8")       # armado al cargar (privacidad del paquete)
_HEX64 = re.compile(r"[0-9a-f]{64}")
_SUBCARPETA = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_RECIBO_ARCHIVADO = re.compile(r"recibo_([1-9][0-9]*)\.json")
_SHA256_ARCHIVADO = re.compile(r"recibo_([1-9][0-9]*)_sha256\.json")       # el sha256.json que cita (PED-6 de I20)
_SHA_VACIO = entorno.sha256_bytes(b"")
_MAX_ENLACES = 40                     # no-umbral: tope de enlaces seguidos al resolver (MAXSYMLINKS), como entorno
_PERMISOS = 0o644                     # no-umbral: permisos de un archivo nuevo
_ILEGIBLE = (OSError, ValueError, RuntimeError, TypeError, KeyError, IndexError)   # al leer un parquet o NetCDF
_CITADOS = 5                          # no-umbral: fallas citadas en un mensaje
_MUESTRA = 80                         # no-umbral: caracteres de un nombre citados en un mensaje
_BLOQUE_LECTURA = 1 << 20             # no-umbral: bloque de lectura al calcular una huella (1 MiB)
# SLD-12: rutas absolutas en lo publicado (SAL-5 de reloj_dmc.salidas): «~/…» o «/a/…» al comienzo o después de un
# separador; no cuentan «America/Santiago», los alias («LOCAL/…») ni los URL («https://…»).
_ANTES_DE_RUTA = r"\s'\"«‹“‘`(\[{=,;:"
_FIN_DE_RUTA = r"\s'\"«»‹›“”‘’`()\[\]{}<>,;:"
_RUTA_ABSOLUTA = re.compile(rf"(?<![^{_ANTES_DE_RUTA}])(?:~/|/[\w.~-][^{_FIN_DE_RUTA}/]*/)")

# Contextos (SLD-1, SLD-7, SLD-11).
_CANDADO = threading.RLock()
_HILO = threading.local()             # las corridas en curso de cada hilo: su raíz por omisión (H13)
_ABIERTAS: list[str] = []             # todas las corridas en curso del proceso: publicar_m5 se niega
_GUARDAS: list[ceguera.GuardaResiduo] = []


# ---------------------------------------------------------------------------
# Rutas (SLD-1, SLD-2)
# ---------------------------------------------------------------------------
def _texto(ruta) -> str:
    if not isinstance(ruta, (str, bytes, os.PathLike)):
        raise TypeError(f"no es una ruta: {type(ruta).__name__}")
    return os.fsdecode(os.fspath(ruta))


def _sin_alias(texto: str) -> str:
    """Una ruta absoluta sin el prefijo ``/System/Volumes/Data`` (sin distinguir mayúsculas; H6)."""
    partes = PurePosixPath(texto).parts
    cambio = False
    while len(partes) > len(_ALIAS_RAIZ) and partes[0] == "/" and \
            tuple(p.casefold() for p in partes[1:len(_ALIAS_RAIZ) + 1]) == _ALIAS_RAIZ:
        partes, cambio = ("/",) + partes[len(_ALIAS_RAIZ) + 1:], True
    return str(PurePosixPath(*partes)) if cambio else texto


def _bajo(ruta: str, raiz: str, *, mayusculas: bool = True) -> bool:
    """True si ``ruta`` es ``raiz`` o cuelga de ella, componente a componente (con ``mayusculas=False``, sin
    distinguirlas, como APFS)."""
    if not mayusculas:
        ruta, raiz = ruta.casefold(), raiz.casefold()
    return ruta == raiz or ruta.startswith(raiz.rstrip(os.sep) + os.sep)


def _dentro(ruta: str, raiz: str) -> bool:
    """Estrictamente dentro de ``raiz``."""
    return ruta != raiz and _bajo(ruta, raiz)


def _en_volumes(texto: str) -> bool:
    partes = PurePosixPath(_sin_alias(texto)).parts
    return len(partes) >= 2 and partes[0] == "/" and partes[1].casefold() == "volumes"


def _sin_puntos(texto: str) -> None:
    if ".." in PurePosixPath(texto).parts:
        raise PermissionError("una ruta de salida no lleva «..» (SLD-2)")


def _repositorios() -> tuple[str, str]:
    r = entorno.rutas_reales()          # sólo arma rutas: no consulta el disco
    return str(r.ap), str(r.aph)


def _en_repositorio(texto: str) -> bool:
    texto = _sin_alias(texto)
    return any(_bajo(texto, r, mayusculas=False) for r in _repositorios())


def _resolver(texto: str) -> tuple[str, bool]:
    """(ruta física, toca /Volumes): sigue los enlaces componente a componente sin consultar nunca un componente bajo
    /Volumes, tampoco por ``/System/Volumes/Data`` (copia del patrón de ``entorno._resolver_seguro``; SLD-2). Un
    componente que no existe deja el resto léxico."""
    texto = _sin_alias(os.path.normpath(os.path.abspath(texto)))
    if _en_volumes(texto):
        return texto, True
    pendientes = deque(p for p in texto.split(os.sep) if p)
    actual, saltos = os.sep, 0
    while pendientes:
        parte = pendientes.popleft()
        if parte == ".":
            continue
        if parte == "..":
            actual = os.path.dirname(actual) or os.sep
            continue
        candidato = os.path.join(actual, parte)
        if _en_volumes(candidato):
            return _sin_alias(os.path.normpath(os.path.join(candidato, *pendientes))), True
        try:
            st = os.lstat(candidato)
        except OSError:
            resto = _sin_alias(os.path.normpath(os.path.join(candidato, *pendientes)))
            return resto, _en_volumes(resto)
        if _stat.S_ISLNK(st.st_mode):
            saltos += 1
            if saltos > _MAX_ENLACES:
                raise PermissionError("demasiados enlaces al resolver una ruta de salida")
            destino = os.readlink(candidato)
            if os.path.isabs(destino):
                actual = os.sep
            pendientes.extendleft(reversed([p for p in destino.split(os.sep) if p]))
            continue
        actual = candidato
    return _sin_alias(actual), False


def _lexica_absoluta(ruta, que: str) -> str:
    texto = _texto(ruta)
    if not os.path.isabs(texto):
        raise ValueError(f"{que} es una ruta absoluta")
    _sin_puntos(texto)
    return _sin_alias(os.path.normpath(texto))


def _prohibidas_lexicas(texto: str) -> None:
    if _en_volumes(texto):
        raise PermissionError("escritura bajo /Volumes prohibida (§8 del texto)")
    if _en_repositorio(texto):
        raise PermissionError("escritura en los repositorios prohibida durante una corrida (§0, regla 10, del diseño)")


def _prohibidas_resueltas(texto: str) -> str:
    """La guarda propia primero (ve ``/System/Volumes/Data`` y no distingue mayúsculas) y después las de ``entorno``;
    devuelve la ruta resuelta (SLD-2)."""
    fisica, volumes = _resolver(texto)
    if volumes:
        raise PermissionError("escritura bajo /Volumes prohibida (§8 del texto): la ruta lleva allí por un enlace")
    if _en_repositorio(fisica):
        raise PermissionError("escritura en los repositorios prohibida: la ruta lleva allí por un enlace")
    entorno.prohibido_volumes(texto)
    entorno.prohibido_repositorios(texto)
    return fisica


def _partes_bajo(ruta: str, base: str) -> tuple[str, ...]:
    return Path(ruta).relative_to(base).parts


def _ancla_v1(partes: tuple[str, ...]) -> int | None:
    """El índice del primer componente después de ``meteo_combinada/v1`` (sin distinguir mayúsculas), o None."""
    ancla = [p.casefold() for p in PurePosixPath(entorno.SUBRUTA_SALIDAS).parts]
    for i in range(len(partes) - len(ancla) + 1):
        if [p.casefold() for p in partes[i:i + len(ancla)]] == ancla:
            return i + len(ancla)
    return None


def _cola_ent4(partes: tuple[str, ...]) -> int:
    """Cuántos componentes de la raíz cuelgan de la carpeta de la corrida, para una raíz de ENT-4 (SLD-1)."""
    if not partes:
        raise PermissionError("la raíz no es la carpeta de una corrida: v1/m1, v1/m2a, v1/<ETIQUETA> o v1/cerrojo "
                              "(ENT-4; SLD-1)")
    primera, cola = partes[0], partes[1:]
    if primera.casefold() == CARPETA_CERROJO:
        valida = len(cola) == 0
    elif primera.casefold() in COMPUERTAS_CON_SUBCARPETA:
        valida = len(cola) == 0 or (len(cola) == 1 and _SUBCARPETA.fullmatch(cola[0]) is not None)
    elif entorno.es_etiqueta_corrida(primera.upper()):
        valida = len(cola) == 0 or (len(cola) == 1 and cola[0].casefold() == CARPETA_M6)
    else:
        valida = False
    if not valida:
        raise PermissionError("la raíz no tiene una forma de ENT-4: v1/m1[/<sub>], v1/m2a[/<sub>], v1/<ETIQUETA>, "
                              "v1/<ETIQUETA>/m6 o v1/cerrojo (SLD-1)")
    return len(cola)


def _validar_raiz(raiz) -> tuple[str, str]:
    """(raíz, carpeta de la corrida), léxicas (SLD-1): ni /Volumes ni repositorios; una forma de ENT-4 bajo
    LOCAL/meteo_combinada/v1 o su análogo en la carpeta temporal del sistema."""
    lexica = _lexica_absoluta(raiz, "la carpeta de la corrida")
    _prohibidas_lexicas(lexica)
    fisica = _prohibidas_resueltas(lexica)
    temporal = _resolver(tempfile.gettempdir())[0]
    if _dentro(fisica, temporal):
        partes = _partes_bajo(fisica, temporal)
        i = _ancla_v1(partes)
        if i is None:
            cola = len(partes) - 1
            if cola > 1 or (cola and _SUBCARPETA.fullmatch(partes[-1]) is None):
                raise PermissionError("en la carpeta temporal, la corrida es una carpeta temporal o una subcarpeta "
                                      "suya (SLD-1)")
        else:
            cola = _cola_ent4(partes[i:])
    else:
        salidas_reales = str(entorno.rutas_reales().salidas)
        salidas_fisica = _resolver(salidas_reales)[0]
        if not (_dentro(lexica, salidas_reales) and _dentro(fisica, salidas_fisica)):
            raise PermissionError("la carpeta de la corrida va bajo LOCAL/meteo_combinada/v1 (§8) o, en las pruebas, "
                                  "bajo la carpeta temporal del sistema (SLD-1)")
        cola = _cola_ent4(_partes_bajo(fisica, salidas_fisica))
    corrida, corrida_fisica = lexica, fisica
    for _ in range(cola):
        corrida, corrida_fisica = os.path.dirname(corrida), os.path.dirname(corrida_fisica)
    lex = [p.casefold() for p in PurePosixPath(lexica).parts[-(cola + 1):]]
    fis = [p.casefold() for p in PurePosixPath(fisica).parts[-(cola + 1):]]
    if lex != fis or _resolver(corrida)[0] != corrida_fisica or \
            _resolver(os.path.dirname(corrida))[0] != os.path.dirname(corrida_fisica):
        raise PermissionError("ni la carpeta de la corrida ni nada entre ella y la raíz es un enlace (SLD-1)")
    return lexica, corrida


def _es_cerrojo(corrida: str) -> bool:
    """True si la carpeta de la corrida es ``v1/cerrojo`` (SLD-1)."""
    ancla = [p.casefold() for p in PurePosixPath(entorno.SUBRUTA_SALIDAS).parts] + [CARPETA_CERROJO]
    return [p.casefold() for p in PurePosixPath(corrida).parts[-len(ancla):]] == ancla


def _exigir_cerrojo(nombre: str, corrida: str, clase: str) -> None:
    """SLD-1: en ``v1/cerrojo`` sólo caben ``intentos_*.jsonl`` de procedencia, sin subcarpetas ni «.gz»."""
    if not _es_cerrojo(corrida):
        return
    if "/" in nombre or clase != "procedencia" or \
            not any(fnmatch.fnmatchcase(nombre.casefold(), p) for p in ARCHIVOS_CERROJO):
        raise SalidaProhibida(f"{nombre}: en el cerrojo sólo se escriben {list(ARCHIVOS_CERROJO)} (procedencia, sólo "
                              "agregado; SLD-1)")


def _pila_del_hilo() -> list[str]:
    pila = getattr(_HILO, "corridas", None)
    if pila is None:
        pila = _HILO.corridas = []
    return pila


def _raiz_de(raiz) -> tuple[str, str]:
    if raiz is None:
        pila = _pila_del_hilo()
        if not pila:
            raise ValueError("escribir exige la carpeta de la corrida: raiz=… o dentro de "
                             "salidas.corrida_en_curso(…) en este hilo (SLD-1)")
        raiz = pila[-1]
    return _validar_raiz(raiz)


def _destino(ruta, raiz: str) -> str:
    texto = _texto(ruta)
    if not texto or texto.endswith(("/", os.sep)):
        raise ValueError("la ruta de una salida nombra un archivo")
    _sin_puntos(texto)
    destino = _sin_alias(os.path.normpath(texto if os.path.isabs(texto) else os.path.join(raiz, texto)))
    if destino.casefold().endswith(SUFIJO_PARCIAL):
        raise ValueError(f"«{SUFIJO_PARCIAL}» es el sufijo de la escritura atómica: ninguna salida lo lleva (SLD-2)")
    return destino


def _guardas_de_ruta(destino: str, raiz: str) -> None:
    """SLD-2: todo lo léxico primero (destino y «.part»), después lo resuelto; un «.part» que ya existe detiene."""
    parcial = destino + SUFIJO_PARCIAL
    for p in (destino, parcial):
        _prohibidas_lexicas(p)
        if not _dentro(p, raiz):
            raise PermissionError("la salida cae fuera de la carpeta de la corrida (SLD-1)")
    raiz_fisica = _resolver(raiz)[0]
    for p in (destino, parcial):
        if not _dentro(_prohibidas_resueltas(p), raiz_fisica):
            raise PermissionError("la salida lleva fuera de la carpeta de la corrida por un enlace (SLD-2)")
    if os.path.lexists(parcial):
        raise PermissionError("ya hay un «.part» de esta salida (una escritura interrumpida, un enlace o un vínculo "
                              "duro); no se escribe sobre él (SLD-2)")


def _nombre(destino: str, corrida: str) -> str:
    """El nombre relativo a la carpeta de la corrida, con «/» y «m6» en minúsculas al comienzo (SLD-3)."""
    partes = list(Path(destino).relative_to(corrida).parts)
    if partes and partes[0].casefold() == CARPETA_M6:
        partes[0] = CARPETA_M6
    return "/".join(partes)


# ---------------------------------------------------------------------------
# Clase y nombre (SLD-3, SLD-14)
# ---------------------------------------------------------------------------
def _calza(nombre: str, patron: str) -> bool:
    partes = [p.casefold() for p in PurePosixPath(nombre).parts if p not in ("/", ".")]
    if partes and partes[-1].endswith(".gz"):
        partes[-1] = partes[-1][:-len(".gz")]
    p = patron.casefold().split("/")
    return len(partes) >= len(p) and all(fnmatch.fnmatchcase(a, b) for a, b in zip(partes[-len(p):], p))


def clase_de_salida(nombre) -> str | None:
    """La clase que fija la ruta (``ceguera.clase_de_ruta``, D3, D13, D14 y D53), o, si ``ceguera`` no fija ninguna,
    la de ``CLASES_PROPIAS``; si no, None. Manda ``ceguera``, que es la guarda y ya fija los recibos archivados en la
    raíz de la corrida y en ``m6/`` (PED-6); ``CLASES_PROPIAS`` sólo rige con otros prefijos (SLD-3)."""
    texto = _texto(nombre)
    fijada = ceguera.clase_de_ruta(texto)
    if fijada is not None:
        return fijada
    return next((c for patron, c in CLASES_PROPIAS.items() if _calza(texto, patron)), None)


def _exigir_clase(nombre: str, clase: str) -> None:
    if clase not in ceguera.CLASES_SALIDA:
        raise ValueError(f"clase de salida desconocida: {clase!r} (son {list(ceguera.CLASES_SALIDA)})")
    fijada = clase_de_salida(nombre)
    if fijada is None:
        if clase not in CLASES_SIN_RUTA:
            raise SalidaProhibida(f"{nombre}: una ruta que no fija clase no se declara «{clase}»: sólo métrica, "
                                  "resumen o documento (SLD-3)")
    elif fijada != clase:
        raise SalidaProhibida(f"{nombre}: su clase es «{fijada}» (la fija la ruta; D3, D13, D14 y D53), no «{clase}»")


def _exigir_nombre(nombre: str) -> None:
    """SLD-14 (H12): el nombre cabe ya en ``sha256.json`` (la guarda de la procedencia de ``ceguera``)."""
    prueba = {"esquema": ESQUEMA_SHA256, "archivos": {nombre: {"sha256": _SHA_VACIO, "bytes": 0}}}
    try:
        ceguera.vigilar_salida(SHA256_JSON, prueba, clase="procedencia")
    except SalidaProhibida as e:
        raise SalidaProhibida("el nombre de una salida no cabe en sha256.json: sin espacios, decimales ni datos "
                              "privados (SLD-14)") from e


def _es_solo_agregado(nombre: str) -> bool:
    final = PurePosixPath(nombre).name.casefold()
    if final.endswith(".gz"):
        final = final[:-len(".gz")]
    return any(fnmatch.fnmatchcase(final, p) for p in SOLO_AGREGADO)


# ---------------------------------------------------------------------------
# Contenido → bytes (SLD-4, SLD-5)
# ---------------------------------------------------------------------------
def _es_tabla(x) -> bool:
    return hasattr(x, "columns") and hasattr(x, "dtypes") and hasattr(x, "index")


def _esquema_escribible(esquema, nombre: str) -> "tipos.Esquema":
    if not isinstance(esquema, tipos.Esquema):
        raise ValueError(f"{nombre}: una tabla se escribe con un tipos.Esquema (con su versión), no con "
                         f"{type(esquema).__name__}")
    if esquema.nombre in tipos.ESQUEMAS_EN_MEMORIA:
        raise ValueError(f"{nombre}: el esquema «{esquema.nombre}» sólo vive en memoria; nunca se escribe (TIP-21)")
    if tipos.ESQUEMAS.get(esquema.nombre) is not esquema:
        raise ValueError(f"{nombre}: el esquema «{esquema.nombre}» no está en tipos.ESQUEMAS (SLD-4)")
    return esquema


def _metadatos_json(metadatos, nombre: str):
    if not isinstance(metadatos, Mapping):
        raise ValueError(f"{nombre}: metadatos= es un diccionario")
    try:
        return json.loads(entorno.json_canonico(dict(metadatos)))
    except (TypeError, ValueError) as e:
        raise ValueError(f"{nombre}: los metadatos no son JSON canónico ({type(e).__name__})") from e


def _bytes_parquet(df, esquema: "tipos.Esquema", metadatos) -> bytes:
    import pyarrow as pa                 # sólo al llamarse
    import pyarrow.parquet as pq
    tabla = pa.Table.from_pandas(df, preserve_index=False)
    meta = dict(tabla.schema.metadata or {})
    attrs: dict[str, Any] = {"esquema": esquema.version}
    if metadatos is not None:
        attrs["metadatos"] = metadatos
    meta[CLAVE_ATTRS] = entorno.json_canonico(attrs)
    buf = io.BytesIO()
    pq.write_table(tabla.replace_schema_metadata(meta), buf, compression=COMPRESION_PARQUET)
    return buf.getvalue()


def _bytes_csv(df) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False, lineterminator="\n")
    return buf.getvalue().encode("utf-8")


def _a_json(obj):
    """Diccionarios (también de sólo lectura) y tuplas → dict y list, para ``json_canonico``."""
    if isinstance(obj, Mapping):
        return {k: _a_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_a_json(v) for v in obj]
    return obj


def _es_parquet_crudo(datos: bytes) -> bool:
    """SLD-4 (H8): unos bytes que son un parquet, también dentro de un gzip."""
    if datos.startswith(_PAR1):
        return True
    if datos.startswith(_GZIP):
        try:
            return _es_parquet_crudo(gzip.decompress(datos))
        except (OSError, EOFError):
            return False                  # un gzip ilegible lo rechaza la privacidad
    return False


def _serializar(nombre: str, contenido, *, esquema, metadatos) -> bytes:
    sufijo = PurePosixPath(nombre).suffix.casefold()
    con_parquet = any(s.casefold() == ".parquet" for s in PurePosixPath(nombre).suffixes)
    if _es_tabla(contenido):
        if esquema is None:
            raise ValueError(f"{nombre}: una tabla se escribe con su esquema de tipos (esquema=…; SLD-4)")
        esquema = _esquema_escribible(esquema, nombre)
        tipos.validar_esquema(contenido, esquema, nombre=nombre)
        propio = getattr(contenido, "attrs", {}).get("esquema")
        if propio is not None and propio != esquema.version:
            raise ValueError(f"{nombre}: attrs['esquema'] = {propio!r} no es la versión del esquema "
                             f"({esquema.version!r})")
        if sufijo == ".parquet":
            return _bytes_parquet(contenido, esquema, None if metadatos is None else _metadatos_json(metadatos, nombre))
        if metadatos is not None:
            raise ValueError(f"{nombre}: metadatos= sólo cabe en un parquet")
        if sufijo == ".csv":
            return _bytes_csv(contenido)
        raise ValueError(f"{nombre}: una tabla se escribe como .parquet o .csv")
    if esquema is not None or metadatos is not None:
        raise ValueError(f"{nombre}: esquema= y metadatos= son de una tabla (DataFrame)")
    if con_parquet:
        raise ValueError(f"{nombre}: un parquet sólo sale de un DataFrame con su esquema (SLD-4)")
    if isinstance(contenido, (bytes, bytearray, memoryview)):
        datos = bytes(contenido)
        if _es_parquet_crudo(datos):
            raise ValueError(f"{nombre}: un parquet sólo sale de un DataFrame con su esquema (SLD-4)")
        return datos
    if isinstance(contenido, str):
        return contenido.encode("utf-8")
    if isinstance(contenido, (Mapping, list, tuple)):
        if sufijo == ".jsonl":
            if isinstance(contenido, Mapping):
                raise ValueError(f"{nombre}: un .jsonl es una lista de registros")
            return b"".join(entorno.json_canonico(_a_json(x)) + b"\n" for x in contenido)
        if sufijo == ".json":
            return entorno.json_canonico(_a_json(contenido))
        raise ValueError(f"{nombre}: un diccionario o una lista se escriben como .json o .jsonl (SLD-4)")
    raise TypeError(f"{nombre}: no se escribe un contenido de tipo {type(contenido).__name__} (SLD-4)")


# ---------------------------------------------------------------------------
# Textos de unos bytes, para la privacidad (SLD-6) y las rutas absolutas (SLD-12)
# ---------------------------------------------------------------------------
def _textos_parquet(datos: bytes) -> list[str]:
    import pyarrow as pa                 # sólo al llamarse
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    tabla = pq.read_table(io.BytesIO(datos))
    textos = list(tabla.schema.names)
    for k, v in (tabla.schema.metadata or {}).items():
        textos += [k.decode("utf-8", "replace"), v.decode("utf-8", "replace")]
    for columna in tabla.columns:
        tipo = columna.type
        if pa.types.is_dictionary(tipo):
            columna, tipo = columna.cast(tipo.value_type), tipo.value_type
        if pa.types.is_string(tipo) or pa.types.is_large_string(tipo):
            textos += [x for x in pc.unique(columna).to_pylist() if x is not None]
    return textos


def _textos_de_valor(valor) -> list[str]:
    if isinstance(valor, bytes):
        return [valor.decode("utf-8", "replace")]
    if isinstance(valor, str):
        return [valor]
    if hasattr(valor, "dtype") and getattr(valor.dtype, "kind", "") in "OUS":
        return [x.decode("utf-8", "replace") if isinstance(x, bytes) else str(x) for x in valor.ravel().tolist()]
    return []


def _textos_netcdf(datos: bytes) -> list[str]:
    import netCDF4                       # sólo al llamarse
    textos: list[str] = []

    def recorrer(g) -> None:
        textos.extend(g.dimensions)
        for a in g.ncattrs():
            textos.append(a)
            textos.extend(_textos_de_valor(g.getncattr(a)))
        for nombre, var in g.variables.items():
            textos.append(nombre)
            for a in var.ncattrs():
                textos.append(a)
                textos.extend(_textos_de_valor(var.getncattr(a)))
            if var.dtype is str or getattr(var.dtype, "kind", "") in "OUS":
                textos.extend(_textos_de_valor(var[:]))
        for nombre, sub in g.groups.items():
            textos.append(nombre)
            recorrer(sub)

    with netCDF4.Dataset("memoria", mode="r", memory=datos) as ds:
        recorrer(ds)
    return textos


def _es_comprimido_ajeno(datos: bytes) -> bool:
    """SLD-6 (H7): bz2, xz, zip, 7z, zstd, lz4 o lzma: comprimidos que este módulo no descomprime."""
    return _BZ2.match(datos) is not None or datos.startswith(_COMPRIMIDOS)


def _textos_de(datos: bytes) -> list[str] | None:
    """Los textos de unos bytes; None si son un binario sin forma conocida."""
    if _es_comprimido_ajeno(datos):
        raise SalidaProhibida("un comprimido que no es gzip (bz2, xz, zip…) no se puede verificar (SLD-6)")
    if datos.startswith(_GZIP):
        try:
            return _textos_de(gzip.decompress(datos))
        except (OSError, EOFError) as e:
            raise SalidaProhibida("un gzip que no se puede leer no se puede verificar") from e
    if datos.startswith(_PAR1):
        try:
            return _textos_parquet(datos)
        except _ILEGIBLE:            # no es un parquet legible: se lee como texto o binario
            pass
    if datos.startswith(_NETCDF):
        try:
            return _textos_netcdf(datos)
        except _ILEGIBLE:            # no es un NetCDF legible: se lee como texto o binario
            pass
    try:
        texto = datos.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return [texto, *_textos_json(texto)]


def _textos_json(texto: str) -> list[str]:
    """Los textos de un JSON o de las líneas de un JSONL, ya decodificados (una arroba escrita «\\u0040» en los
    bytes es una arroba en el texto; SLD-6). Lo que no es JSON no agrega nada."""
    objetos = []
    try:
        objetos.append(json.loads(texto))
    except ValueError:
        for linea in texto.splitlines():
            try:
                objetos.append(json.loads(linea))
            except ValueError:
                continue
    return [t for o in objetos for t in _textos_de_objeto(o)]


def _privacidad(nombre: str, datos: bytes) -> None:
    """SLD-6: ni la carpeta de usuario, ni la personal, ni la arroba, en el nombre ni en ningún texto."""
    if not entorno.sin_datos_privados(nombre):
        raise SalidaProhibida("el nombre de la salida trae una ruta de la carpeta de usuario o una arroba")
    if any(s.casefold() in _EXTENSIONES_COMPRIMIDAS for s in PurePosixPath(nombre).suffixes):
        raise SalidaProhibida(f"{nombre}: un comprimido que no es gzip no se puede verificar (SLD-6)")
    textos = _textos_de(datos)
    if textos is None:
        casa = str(Path.home()).encode("utf-8")
        if _USUARIOS in datos or (len(casa) > 1 and casa in datos):
            raise SalidaProhibida(f"{nombre}: el binario trae la ruta de la carpeta de usuario o la personal")
        return
    for t in textos:
        if not entorno.sin_datos_privados(t):
            raise SalidaProhibida(f"{nombre}: trae una ruta de la carpeta de usuario, la carpeta personal o una arroba")


def _comprobar_contenido(nombre: str, datos: bytes, *, clase: str, referencia) -> None:
    """Privacidad (SLD-6), la guarda de la clase (``ceguera.vigilar_salida``) y los centinelas activos (SLD-7)."""
    _privacidad(nombre, datos)
    ceguera.vigilar_salida(nombre, datos, clase=clase, referencia=referencia)
    if clase == "documento":
        try:
            addendum._validar_publicacion(nombre, datos)
        except addendum.ErrorAddendum as e:
            raise SalidaProhibida(f"{nombre}: {e}") from e
    with _CANDADO:
        guardas = list(_GUARDAS)
    for guarda in guardas:
        guarda.comprobar(datos, nombre=nombre)


# ---------------------------------------------------------------------------
# Contextos (SLD-1, SLD-7, SLD-11)
# ---------------------------------------------------------------------------
@contextmanager
def corrida_en_curso(carpeta) -> Iterator[Path]:
    """Marca una corrida en curso en ``carpeta``: en este hilo, ``escribir`` y ``agregar_linea`` sin ``raiz``
    escriben en la más interior; en todo el proceso, ``publicar_m5`` se niega mientras haya alguna (SLD-1, SLD-11)."""
    raiz, _ = _validar_raiz(carpeta)
    pila = _pila_del_hilo()
    pila.append(raiz)
    with _CANDADO:
        _ABIERTAS.append(raiz)
    try:
        yield Path(raiz)
    finally:
        for i in range(len(pila) - 1, -1, -1):
            if pila[i] == raiz:
                del pila[i]
                break
        with _CANDADO:
            _ABIERTAS.remove(raiz)


def hay_corrida_en_curso() -> bool:
    """True si hay alguna corrida en curso en algún hilo de este proceso."""
    with _CANDADO:
        return bool(_ABIERTAS)


@contextmanager
def vigilar_residuo(guarda: "ceguera.GuardaResiduo") -> Iterator["ceguera.GuardaResiduo"]:
    """Activa una ``ceguera.GuardaResiduo``: mientras dure, ninguna salida de este proceso lleva sus centinelas
    (S7, §0.4.6; SLD-7)."""
    if not isinstance(guarda, ceguera.GuardaResiduo):
        raise TypeError("vigilar_residuo recibe una ceguera.GuardaResiduo")
    with _CANDADO:
        _GUARDAS.append(guarda)
    try:
        yield guarda
    finally:
        with _CANDADO:
            for i in range(len(_GUARDAS) - 1, -1, -1):
                if _GUARDAS[i] is guarda:
                    del _GUARDAS[i]
                    break


# ---------------------------------------------------------------------------
# Escritura
# ---------------------------------------------------------------------------
def _regular_unico(ruta: str, nombre: str) -> os.stat_result:
    """Un archivo regular (no un enlace) con un solo vínculo (SLD-8, H3)."""
    st = os.lstat(ruta)
    if not _stat.S_ISREG(st.st_mode):
        raise PermissionError(f"{nombre}: no es un archivo regular (enlace u otro tipo)")
    if st.st_nlink != 1:
        raise PermissionError(f"{nombre}: tiene otro vínculo duro; no se escribe a través de él (SLD-8)")
    return st


def _leer(ruta: str) -> bytes:
    with open(ruta, "rb") as f:
        return f.read()


def _exigir_solo_agregado(nombre: str, destino: str, datos: bytes) -> None:
    """SLD-8: sobre un archivo sólo agregado, el contenido nuevo empieza con el que hay; sin «.gz» ni vínculos."""
    if not _es_solo_agregado(nombre):
        return
    if nombre.casefold().endswith(".gz"):
        raise SalidaProhibida(f"{nombre}: un archivo sólo agregado no se comprime (SLD-8)")
    if not os.path.lexists(destino):
        return
    _regular_unico(destino, nombre)
    previo = _leer(destino)
    if previo and not previo.endswith(b"\n"):
        raise SalidaProhibida(f"{nombre}: su última línea está incompleta (escritura interrumpida); no se repara sola")
    if not datos.startswith(previo):
        raise SalidaProhibida(f"{nombre}: es sólo agregado; el contenido nuevo debe empezar con el que hay (SLD-8)")


def _recibos_archivados(carpeta: str) -> dict[int, str]:
    """{n: ruta} de ``<carpeta>/recibos/recibo_<n>.json`` (SLD-10)."""
    base = os.path.join(carpeta, CARPETA_RECIBOS)
    if not os.path.lexists(base):
        return {}
    st = os.lstat(base)
    if _stat.S_ISLNK(st.st_mode) or not _stat.S_ISDIR(st.st_mode):
        raise PermissionError(f"{CARPETA_RECIBOS}/ es una carpeta, no un enlace (SLD-10)")
    salida = {}
    with os.scandir(base) as it:
        for e in it:
            m = _RECIBO_ARCHIVADO.fullmatch(e.name)
            if m and e.is_file(follow_symlinks=False):
                salida[int(m.group(1))] = e.path
    return salida


def _exigir_recibos(nombre: str, destino: str, datos: bytes) -> None:
    """SLD-10 (H4): un recibo sólo se reemplaza si sus bytes ya están en ``recibos/``; un recibo archivado no cambia."""
    final = PurePosixPath(nombre).name.casefold()
    if not os.path.lexists(destino):
        return
    if final == RECIBO:
        _regular_unico(destino, nombre)
        previo = _leer(destino)
        if previo == datos:
            return
        sha = entorno.sha256_bytes(previo)
        if not any(_huella_y_tamano(r)[0] == sha for r in _recibos_archivados(os.path.dirname(destino)).values()):
            raise SalidaProhibida(f"{nombre}: un recibo no se borra ni se sobrescribe; el anterior va antes a "
                                  f"{CARPETA_RECIBOS}/ (sellar_corrida; SLD-10)")
    elif _calza(nombre, PATRON_RECIBO_ARCHIVADO) and _leer(destino) != datos:
        raise SalidaProhibida(f"{nombre}: un recibo archivado no cambia (SLD-10)")


def _fsync_carpeta(carpeta: str) -> None:
    """El renombre o la creación quedan en disco al sincronizar la carpeta (no todos los sistemas lo permiten)."""
    try:
        fd = os.open(carpeta, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def escribir(ruta, contenido, *, clase: str, esquema=None, referencia=None, raiz=None, metadatos=None) -> str:
    """Escribe una salida y devuelve el sha256 de sus bytes (§8; SLD-1 a SLD-8, SLD-10 y SLD-14). La única escritura
    del paquete.

    ``ruta``: relativa a la raíz o absoluta dentro de ella. ``raiz``: una carpeta de ENT-4 (SLD-1); si falta, la del
    contexto ``corrida_en_curso`` más interior de este hilo. ``clase``: la de ``ceguera.CLASES_SALIDA``; si la ruta
    fija una, debe ser ésa, y si no fija ninguna, sólo métrica, resumen o documento. ``contenido``: bytes, texto,
    diccionario o lista (JSON canónico), o un DataFrame con su ``esquema`` de ``tipos.ESQUEMAS`` (parquet o CSV;
    ``metadatos`` van al parquet). ``referencia``: la ``ceguera.ReferenciaDocumento`` de un documento (D13), y sólo de
    él. Antes de escribir: las guardas de la ruta (``PermissionError``), el nombre, la clase, los bytes deterministas,
    la privacidad, ``ceguera.vigilar_salida``, las ``GuardaResiduo`` activas (``SalidaProhibida``) y las reglas de lo
    sólo agregado y de los recibos. Después, ``entorno.escribir_atomico``.
    """
    raiz_l, corrida = _raiz_de(raiz)
    destino = _destino(ruta, raiz_l)
    _guardas_de_ruta(destino, raiz_l)
    nombre = _nombre(destino, corrida)
    _exigir_nombre(nombre)
    _exigir_cerrojo(nombre, corrida, clase)
    _exigir_clase(nombre, clase)
    datos = _serializar(nombre, contenido, esquema=esquema, metadatos=metadatos)
    _comprobar_contenido(nombre, datos, clase=clase, referencia=referencia)
    _exigir_solo_agregado(nombre, destino, datos)
    _exigir_recibos(nombre, destino, datos)
    sha = entorno.escribir_atomico(destino, datos)
    if sha != entorno.sha256_bytes(datos):
        raise RuntimeError(f"{nombre}: la huella escrita no es la de sus bytes")
    return sha


def agregar_linea(ruta, registro: Mapping, *, raiz=None) -> str:
    """Agrega un registro (una línea JSON canónica) a ``avance.jsonl`` o a un ``intentos_*.jsonl``, que son sólo
    agregado y de clase procedencia; devuelve el sha256 de la línea escrita (SLD-8)."""
    raiz_l, corrida = _raiz_de(raiz)
    destino = _destino(ruta, raiz_l)
    _guardas_de_ruta(destino, raiz_l)
    nombre = _nombre(destino, corrida)
    _exigir_nombre(nombre)
    _exigir_cerrojo(nombre, corrida, "procedencia")
    if not _es_solo_agregado(nombre):
        raise ValueError(f"{nombre}: agregar_linea es para {list(SOLO_AGREGADO)} (SLD-8)")
    if nombre.casefold().endswith(".gz"):
        raise SalidaProhibida(f"{nombre}: un archivo sólo agregado no se comprime (SLD-8)")
    _exigir_clase(nombre, "procedencia")
    if not isinstance(registro, Mapping):
        raise ValueError(f"{nombre}: cada línea es un registro (diccionario)")
    linea = entorno.json_canonico(_a_json(registro)) + b"\n"
    _comprobar_contenido(nombre, linea, clase="procedencia", referencia=None)
    existia = os.path.lexists(destino)
    if existia:
        st = _regular_unico(destino, nombre)
        if st.st_size:
            with open(destino, "rb") as f:
                f.seek(st.st_size - 1)
                if f.read() != b"\n":
                    raise SalidaProhibida(f"{nombre}: su última línea está incompleta (escritura interrumpida); no se "
                                          "repara sola (SLD-8)")
    Path(destino).parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(destino, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, _PERMISOS)
    try:
        st = os.fstat(fd)
        if not _stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise PermissionError(f"{nombre}: no es un archivo regular con un solo vínculo (SLD-8)")
        escritos = os.write(fd, linea)
        if escritos != len(linea):
            raise OSError(f"{nombre}: la línea quedó a medias")
        os.fsync(fd)
    finally:
        os.close(fd)
    if not existia:
        _fsync_carpeta(os.path.dirname(destino))
    return entorno.sha256_bytes(linea)


# ---------------------------------------------------------------------------
# Cadena de huellas (SLD-9, SLD-10)
# ---------------------------------------------------------------------------
def _carpeta_existente(carpeta, que: str) -> str:
    """Una carpeta que se lee: absoluta, sin «..», nunca bajo /Volumes (ni consultada), ni enlace."""
    texto = _lexica_absoluta(carpeta, que)
    if _en_volumes(texto) or _resolver(texto)[1]:
        raise PermissionError(f"{que} no está bajo /Volumes (§8)")
    try:
        st = os.lstat(texto)
    except FileNotFoundError as e:
        raise FileNotFoundError(f"{que} no existe") from e
    if _stat.S_ISLNK(st.st_mode) or not _stat.S_ISDIR(st.st_mode):
        raise ValueError(f"{que} es una carpeta, no un enlace")
    return texto


def _huella_y_tamano(ruta: str) -> tuple[str, int]:
    h, n = hashlib.sha256(), 0
    with open(ruta, "rb") as f:
        while bloque := f.read(_BLOQUE_LECTURA):
            h.update(bloque)
            n += len(bloque)
    return h.hexdigest(), n


def _recorrer_archivos(base: str, sub: str = "") -> Iterator[tuple[str, str]]:
    """(ruta relativa con «/», ruta) de cada archivo regular, en orden; ValueError con un «.part», un enlace u otro
    tipo de archivo (SLD-9)."""
    with os.scandir(os.path.join(base, sub) if sub else base) as it:
        entradas = sorted(it, key=lambda e: e.name)
    for e in entradas:
        relativo = f"{sub}/{e.name}" if sub else e.name
        if e.is_symlink():
            raise ValueError(f"{relativo}: es un enlace simbólico; no se sella (SLD-9)")
        if e.is_dir(follow_symlinks=False):
            yield from _recorrer_archivos(base, relativo)
        elif e.is_file(follow_symlinks=False):
            if e.name.casefold().endswith(SUFIJO_PARCIAL):
                raise ValueError(f"{relativo}: escritura incompleta; no se sella (SLD-9)")
            yield relativo, e.path
        else:
            raise ValueError(f"{relativo}: no es un archivo regular; no se sella (SLD-9)")


def inventario(carpeta) -> dict[str, dict[str, Any]]:
    """{ruta relativa: {"sha256", "bytes"}} de los archivos de la carpeta, salvo ``sha256.json`` y
    ``recibo_corrida.json`` de su raíz (SLD-9)."""
    base = _carpeta_existente(carpeta, "la carpeta del inventario")
    salida = {}
    for relativo, ruta in _recorrer_archivos(base):
        if relativo in (SHA256_JSON, RECIBO):
            continue
        sha, n = _huella_y_tamano(ruta)
        salida[relativo] = {"sha256": sha, "bytes": n}
    return salida


def escribir_sha256(carpeta, *, raiz=None) -> str:
    """Escribe ``<carpeta>/sha256.json`` con el inventario de la carpeta (SLD-9); devuelve su sha256. ``raiz``: la
    raíz de ENT-4, si no es la misma carpeta."""
    contenido = {"esquema": ESQUEMA_SHA256, "archivos": inventario(carpeta)}
    return escribir(Path(_texto(carpeta)) / SHA256_JSON, contenido, clase="procedencia",
                    raiz=carpeta if raiz is None else raiz)


def _exigir_huella(valor, donde: str) -> None:
    if isinstance(valor, Mapping):
        if set(valor) - set(ceguera.CLAVES_DE_HUELLA) or "sha256" not in valor:
            raise ValueError(f"{donde}: una huella es un sha256 o {{\"sha256\", \"bytes\"}}")
        n = valor.get("bytes", 0)
        if isinstance(n, bool) or not isinstance(n, int) or n < 0:
            raise ValueError(f"{donde}: «bytes» es un entero no negativo (D12)")
        valor = valor["sha256"]
    if not isinstance(valor, str) or _HEX64.fullmatch(valor) is None:
        raise ValueError(f"{donde}: la huella es un sha256 de 64 caracteres hexadecimales")


def _textos_de_objeto(obj) -> Iterator[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, Mapping):
        for k, v in obj.items():
            yield str(k)
            yield from _textos_de_objeto(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _textos_de_objeto(v)


def recibo_corrida(huellas: dict, entorno_: dict) -> dict:
    """El contenido de ``recibo_corrida.json`` (§8, «Cadena de huellas»; SLD-10), ya validado con la guarda de la
    procedencia (D3, D12): ``huellas`` {ruta por alias: sha256 o {"sha256", "bytes"}}, no vacío; ``entorno_`` las
    versiones fijadas y los conteos (``procesos``…), sin decimales ni rutas absolutas."""
    if not isinstance(huellas, Mapping) or not huellas:
        raise ValueError("el recibo cita al menos una huella")
    if not isinstance(entorno_, Mapping) or not entorno_:
        raise ValueError("el recibo lleva el entorno de la corrida (versiones fijadas)")
    for ruta, valor in huellas.items():
        if not isinstance(ruta, str) or not ceguera.es_ruta_por_alias(ruta):
            raise ValueError("en el recibo, las huellas van por ruta por alias («LOCAL/…», «ERA5L/…»; SLD-10)")
        if any(p in ("", ".", "..") for p in ruta.split("/")):
            raise ValueError("una ruta por alias del recibo no lleva «.», «..» ni tramos vacíos")
        _exigir_huella(valor, "recibo")
    contenido = {"esquema": ESQUEMA_RECIBO, "entorno": json.loads(entorno.json_canonico(_a_json(entorno_))),
                 "huellas": {k: _a_json(huellas[k]) for k in sorted(huellas)}}
    for t in _textos_de_objeto(contenido):
        if _RUTA_ABSOLUTA.search(t):
            raise SalidaProhibida("el recibo se publica: ningún texto es una ruta absoluta ni empieza con «~/» "
                                  "(SLD-10)")
    ceguera.vigilar_salida(RECIBO, contenido, clase="procedencia")
    return contenido


def sellar_corrida(carpeta, huellas_entrada: Mapping, entorno_: Mapping, *, rutas: "entorno.Rutas") -> str:
    """Sella la carpeta de una corrida (SLD-10): si ya hay un recibo, lo copia antes, con sus mismos bytes, a
    ``recibos/recibo_<n>.json``, y el ``sha256.json`` que cita a ``recibos/recibo_<n>_sha256.json``; después
    ``sha256.json`` y el recibo nuevo, que cita por su ruta por alias la huella de ``sha256.json`` y las de los dos
    archivados. Devuelve el sha256 del recibo nuevo."""
    carpeta = Path(_texto(carpeta))
    huellas = dict(huellas_entrada)
    propia = entorno.alias(carpeta, rutas) + "/"
    if any(isinstance(k, str) and (k.casefold() == (propia + SHA256_JSON).casefold() or k.casefold().startswith(
            (propia + CARPETA_RECIBOS + "/").casefold())) for k in huellas):
        raise ValueError("las huellas de entrada no traen el sha256.json ni los recibos de la corrida: los pone el "
                         "sello")
    if os.path.lexists(carpeta / RECIBO):
        huellas.update(_archivar_sello(carpeta, rutas))
    huellas[entorno.alias(carpeta / SHA256_JSON, rutas)] = escribir_sha256(carpeta)
    return escribir(carpeta / RECIBO, recibo_corrida(huellas, entorno_), clase="procedencia", raiz=carpeta)


def _archivar_sello(carpeta: Path, rutas: "entorno.Rutas") -> dict[str, str]:
    """Copia el recibo y el ``sha256.json`` que cita a ``recibos/recibo_<n>.json`` y ``recibos/recibo_<n>_sha256.json``
    con sus mismos bytes (SLD-10); devuelve {ruta por alias: sha256} de los dos. Nada se escribe si el par no se
    puede verificar o si alguna de las dos rutas no es procedencia."""
    ruta_recibo, ruta_inventario = str(carpeta / RECIBO), str(carpeta / SHA256_JSON)
    _regular_unico(ruta_recibo, RECIBO)
    previo = _leer(ruta_recibo)
    try:
        recibo = json.loads(previo.decode("utf-8"))
    except ValueError as e:
        raise ValueError("el recibo anterior no es un JSON legible; no se archiva (SLD-10)") from e
    huellas = recibo.get("huellas") if isinstance(recibo, Mapping) else None
    citado = _sha_de(huellas.get(entorno.alias(carpeta / SHA256_JSON, rutas))) if isinstance(huellas, Mapping) \
        else None
    if citado is None:
        raise ValueError("el recibo anterior no cita el sha256.json de la corrida; no se archiva un sello que no se "
                         "puede verificar (SLD-10)")
    if not os.path.lexists(ruta_inventario):
        raise ValueError("falta el sha256.json que cita el recibo anterior; no se archiva (SLD-10)")
    _regular_unico(ruta_inventario, SHA256_JSON)
    inventario_previo = _leer(ruta_inventario)
    if entorno.sha256_bytes(inventario_previo) != citado:
        raise ValueError("el sha256.json cambió después del recibo anterior; no se archiva un par que no se verifica "
                         "(SLD-10)")
    sha_previo = entorno.sha256_bytes(previo)
    archivados = _recibos_archivados(str(carpeta))
    n = next((k for k, r in sorted(archivados.items()) if _huella_y_tamano(r)[0] == sha_previo), None)
    if n is None:
        n = max(archivados, default=0) + 1
    destinos = ((carpeta / CARPETA_RECIBOS / f"recibo_{n}.json", previo),
                (carpeta / CARPETA_RECIBOS / f"recibo_{n}_sha256.json", inventario_previo))
    raiz_l, corrida = _validar_raiz(carpeta)
    for destino, _ in destinos:                    # las dos clases y nombres antes de escribir ninguna
        nombre = _nombre(_destino(destino, raiz_l), corrida)
        _exigir_nombre(nombre)
        _exigir_clase(nombre, "procedencia")
    salida = {}
    for destino, datos in destinos:
        if os.path.lexists(destino):
            _regular_unico(str(destino), destino.name)
            if _leer(str(destino)) != datos:
                raise SalidaProhibida(f"{CARPETA_RECIBOS}/{destino.name}: un archivo de {CARPETA_RECIBOS}/ no cambia "
                                      "(SLD-10)")
        else:
            escribir(destino, datos, clase="procedencia", raiz=carpeta)
        salida[entorno.alias(destino, rutas)] = entorno.sha256_bytes(datos)
    return salida


def _huella_del_prefijo(ruta: str, n: int) -> str | None:
    """sha256 de los primeros ``n`` bytes de un archivo, o None si tiene menos."""
    h, faltan = hashlib.sha256(), n
    with open(ruta, "rb") as f:
        while faltan > 0:
            bloque = f.read(min(faltan, _BLOQUE_LECTURA))
            if not bloque:
                return None
            h.update(bloque)
            faltan -= len(bloque)
    return h.hexdigest()


def fallas_de_sello_archivado(carpeta, n: int) -> list[str]:
    """Por qué el sello archivado ``n`` de una carpeta no la verifica tal como estaba al sellar (SLD-10); vacío si la
    verifica. El recibo ``recibos/recibo_<n>.json`` cita la huella de ``recibos/recibo_<n>_sha256.json``, y cada
    archivo que éste lista sigue con su huella (en los sólo agregado, la de sus primeros «bytes»). Sólo lee."""
    base = _carpeta_existente(carpeta, "la carpeta del sello")
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError("el número de un sello archivado es un entero positivo")
    rutas_archivadas = [os.path.join(base, CARPETA_RECIBOS, f) for f in (f"recibo_{n}.json", f"recibo_{n}_sha256.json")]
    faltan = [f"falta {CARPETA_RECIBOS}/{Path(r).name}" for r in rutas_archivadas if not os.path.lexists(r)]
    if faltan:
        return faltan
    try:
        _, recibo = _leer_json(rutas_archivadas[0], RECIBO)
        datos_inventario, inventario_sellado = _leer_json(rutas_archivadas[1], SHA256_JSON)
    except (OSError, ValueError) as e:
        return [f"el sello archivado {n} no es un JSON legible ({type(e).__name__})"]
    fallas = []
    citas = _cita_de_sha256_json(recibo, Path(base).name)
    if len(citas) != 1:
        fallas.append(f"{CARPETA_RECIBOS}/recibo_{n}.json no cita una sola vez el sha256.json de la carpeta")
    elif _sha_de(recibo["huellas"][citas[0]]) != entorno.sha256_bytes(datos_inventario):
        fallas.append(f"{CARPETA_RECIBOS}/recibo_{n}_sha256.json no es el sha256.json que cita su recibo")
    archivos = inventario_sellado.get("archivos") if isinstance(inventario_sellado, Mapping) else None
    if not isinstance(archivos, Mapping):
        return fallas + [f"{CARPETA_RECIBOS}/recibo_{n}_sha256.json no tiene el esquema {ESQUEMA_SHA256}"]
    for relativo, valor in sorted(archivos.items()):
        ruta = os.path.join(base, *str(relativo).split("/"))
        sha = _sha_de(valor)
        bytes_ = valor.get("bytes") if isinstance(valor, Mapping) else None
        if not os.path.lexists(ruta) or os.path.islink(ruta):
            fallas.append(f"falta {relativo}")
        elif _es_solo_agregado(relativo) and isinstance(bytes_, int):
            if _huella_del_prefijo(ruta, bytes_) != sha:
                fallas.append(f"cambió {relativo} (lo que había al sellar)")
        elif _huella_y_tamano(ruta)[0] != sha:
            fallas.append(f"cambió {relativo}")
    return fallas


# ---------------------------------------------------------------------------
# Publicación de M5 (SLD-11 a SLD-13)
# ---------------------------------------------------------------------------
def _leer_json(ruta: str, nombre: str):
    def sin_duplicados(pares):
        claves = [k for k, _ in pares]
        if len(claves) != len(set(claves)):
            raise ValueError(f"{nombre}: claves repetidas")
        return dict(pares)

    datos = _leer(ruta)
    return datos, json.loads(datos.decode("utf-8"), object_pairs_hook=sin_duplicados)


def _sha_de(valor) -> str | None:
    if isinstance(valor, Mapping):
        valor = valor.get("sha256")
    return valor if isinstance(valor, str) else None


def _cita_de_sha256_json(recibo: Mapping, etiqueta: str) -> list[str]:
    huellas = recibo.get("huellas") if isinstance(recibo, Mapping) else None
    if not isinstance(huellas, Mapping):
        return []
    sufijo = f"/{etiqueta}/{SHA256_JSON}".casefold()
    return [k for k in huellas if isinstance(k, str) and k.casefold().endswith(sufijo)]


def _cierre(carpeta: str) -> tuple[list[str], dict]:
    """(fallas, estado): las fallas de SLD-11 y, si no hay, los bytes y el contenido de ``sha256.json`` y del recibo."""
    etiqueta = Path(carpeta).name
    if not entorno.es_etiqueta_corrida(etiqueta.upper()):
        return [f"la carpeta no se llama HUMAN<AAAAMMDD>_METEO_COMB_<n>: {etiqueta[:_MUESTRA]}"], {}
    try:
        actual = inventario(carpeta)
    except ValueError as e:
        return [str(e)], {}
    fallas, estado = [], {}
    for nombre in (RECIBO, SHA256_JSON):
        ruta = os.path.join(carpeta, nombre)
        if not os.path.lexists(ruta):
            fallas.append(f"falta {nombre}: la corrida no está sellada")
            continue
        try:
            datos, objeto = _leer_json(ruta, nombre)
            ceguera.vigilar_salida(nombre, datos, clase="procedencia")
        except (OSError, ValueError) as e:
            fallas.append(f"{nombre} no es una procedencia legible ({type(e).__name__})")
            continue
        estado[nombre] = (datos, objeto)
    if fallas:
        return fallas, {}
    datos_sha, inventario_sellado = estado[SHA256_JSON]
    _, recibo = estado[RECIBO]
    citas = _cita_de_sha256_json(recibo, etiqueta)
    if len(citas) != 1:
        fallas.append(f"el recibo no cita una sola vez …/{etiqueta}/{SHA256_JSON}")
    elif _sha_de(recibo["huellas"][citas[0]]) != entorno.sha256_bytes(datos_sha):
        fallas.append(f"{SHA256_JSON} cambió después del recibo")
    archivos = inventario_sellado.get("archivos") if isinstance(inventario_sellado, Mapping) else None
    if not isinstance(inventario_sellado, Mapping) or inventario_sellado.get("esquema") != ESQUEMA_SHA256 \
            or not isinstance(archivos, Mapping):
        return fallas + [f"{SHA256_JSON} no tiene el esquema {ESQUEMA_SHA256}"], {}
    sellados = {k: _sha_de(v) for k, v in archivos.items()}
    fallas += [f"falta {r}" for r in sorted(set(sellados) - set(actual))]
    fallas += [f"sobra {r} (no está en {SHA256_JSON})" for r in sorted(set(actual) - set(sellados))]
    fallas += [f"cambió {r}" for r in sorted(set(sellados) & set(actual)) if sellados[r] != actual[r]["sha256"]]
    for requerido in (DECISION, POLITICA):
        if requerido not in actual:
            fallas.append(f"falta {requerido}")
    for prefijo in PRODUCTOS_M5:
        if not any(r.startswith(prefijo + "/") for r in actual):
            fallas.append(f"faltan los productos de M5 en {prefijo}/")
    return fallas, {"sellados": sellados, "sha256_json": datos_sha, "recibo": estado[RECIBO][0]}


def _carpeta_corrida(carpeta_corrida) -> str:
    texto = _carpeta_existente(carpeta_corrida, "la carpeta de la corrida")
    if _en_repositorio(texto) or _en_repositorio(_resolver(texto)[0]):
        raise PermissionError("una corrida no está en los repositorios (§8)")
    return texto


def fallas_de_cierre(carpeta_corrida) -> list[str]:
    """Por qué una corrida no está cerrada (SLD-11); vacío si lo está. Sólo lee la carpeta."""
    return _cierre(_carpeta_corrida(carpeta_corrida))[0]


def _publicacion(destino_ap) -> tuple[str, str, bool]:
    """(carpeta de publicación léxica, su ruta resuelta esperada, si ``destino_ap`` es el AP real) (SLD-13)."""
    lexica = _lexica_absoluta(destino_ap, "destino_ap")
    if _en_volumes(lexica):
        raise PermissionError("la publicación no va bajo /Volumes (§8)")
    ap, aph = _repositorios()
    fisica, volumes = _resolver(lexica)
    if volumes:
        raise PermissionError("la publicación no va bajo /Volumes (§8): destino_ap lleva allí por un enlace")
    for p in (lexica, fisica):
        if _bajo(p, aph, mayusculas=False):
            raise PermissionError("la publicación va a AP; el espejo en APH no lo hace este módulo (SLD-13)")
    base, base_fisica = os.path.join(lexica, SUBRUTA_PUBLICACION), os.path.join(fisica, SUBRUTA_PUBLICACION)
    if lexica.casefold() == ap.casefold() and fisica.casefold() == ap.casefold():
        return base, base_fisica, True
    if _en_repositorio(lexica) or _en_repositorio(fisica):
        raise PermissionError("destino_ap es la raíz de AP, no una carpeta dentro de un repositorio (SLD-13)")
    if _dentro(fisica, _resolver(tempfile.gettempdir())[0]):
        return base, base_fisica, False
    raise PermissionError("destino_ap es la raíz de AP o, en las pruebas, una carpeta temporal (SLD-13)")


def carpeta_publicacion(destino_ap) -> Path:
    """``<destino_ap>/config/meteorologia/meteo_combinada/v1`` (SLD-13). ``destino_ap`` es la raíz de AP real o, en
    las pruebas, una carpeta bajo la carpeta temporal del sistema; nunca /Volumes ni APH. No crea nada."""
    return Path(_publicacion(destino_ap)[0])


def es_ap_real(destino_ap) -> bool:
    """True si ``destino_ap`` es la raíz del AP real (léxica y resuelta, sin distinguir mayúsculas; SLD-13)."""
    return _publicacion(destino_ap)[2]


def _exigir_corrida_real(carpeta: str) -> None:
    """SLD-13 (H11): con el AP real, la corrida es una hija de LOCAL/meteo_combinada/v1, léxica y resuelta."""
    salidas_reales = str(entorno.rutas_reales().salidas)
    if os.path.dirname(carpeta) != salidas_reales or \
            os.path.dirname(_resolver(carpeta)[0]) != _resolver(salidas_reales)[0]:
        raise PermissionError("con el AP real, la corrida es una carpeta de LOCAL/meteo_combinada/v1 (§8; SLD-13)")


def _publicables(sellados: Mapping[str, str]) -> list[str]:
    """SLD-12: ``decision.json``, la política, los resúmenes fuera de ``m6/`` y las huellas, en ese orden."""
    resumenes = sorted(r for r in sellados if r not in (DECISION, POLITICA)
                       and not r.casefold().startswith(CARPETA_M6 + "/") and clase_de_salida(r) == "resumen")
    def orden(r: str) -> tuple[int, int] | None:
        nombre = PurePosixPath(r).name
        for tipo, patron in enumerate((_RECIBO_ARCHIVADO, _SHA256_ARCHIVADO)):
            m = patron.fullmatch(nombre)
            if m:
                return int(m.group(1)), tipo
        return None

    archivados = sorted((r for r in sellados if PurePosixPath(r).parent.as_posix() == CARPETA_RECIBOS
                         and orden(r) is not None), key=orden)
    return [DECISION, POLITICA, *resumenes, *archivados, SHA256_JSON, RECIBO]


def _publicable(nombre: str, datos: bytes) -> None:
    """La guarda de su clase, la privacidad y ninguna ruta absoluta (§8, «Publicación (M5)»; SLD-12)."""
    _privacidad(nombre, datos)
    clase = clase_de_salida(nombre)
    if clase is None:
        raise SalidaProhibida(f"{nombre}: lo publicado tiene una clase fijada por la ruta")
    ceguera.vigilar_salida(nombre, datos, clase=clase)
    textos = _textos_de(datos)
    if textos is None:
        raise SalidaProhibida(f"{nombre}: lo publicado es texto o una tabla, no un binario")
    if any(_RUTA_ABSOLUTA.search(t) for t in textos):
        raise SalidaProhibida(f"{nombre}: lo publicado no lleva rutas absolutas (§8)")


def _escribir_publicacion(destino: str, datos: bytes, *, base: str, base_fisica: str) -> str:
    """Escritura atómica bajo la carpeta de publicación (SLD-13): «.part» nuevo (``O_EXCL``, sin seguir enlaces),
    fsync, renombre y fsync de la carpeta."""
    parcial = destino + SUFIJO_PARCIAL
    _, aph = _repositorios()
    for p in (destino, parcial):
        if _en_volumes(p) or _bajo(p, aph, mayusculas=False) or not _dentro(p, base):
            raise PermissionError("la publicación cae fuera de su carpeta (SLD-13)")
    for p in (destino, parcial):
        fisica, volumes = _resolver(p)
        if volumes or _bajo(fisica, aph, mayusculas=False) or not _dentro(fisica, base_fisica):
            raise PermissionError("la publicación lleva fuera de su carpeta por un enlace (SLD-13)")
        entorno.prohibido_volumes(p)
    if os.path.lexists(parcial):
        raise PermissionError("ya hay un «.part» en la publicación (una escritura interrumpida); no se escribe sobre "
                              "él (SLD-13)")
    Path(destino).parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(parcial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, _PERMISOS)
        try:
            vista = memoryview(datos)
            while vista:
                vista = vista[os.write(fd, vista):]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(parcial, destino)
    except BaseException:
        try:
            os.unlink(parcial)
        except FileNotFoundError:
            pass
        raise
    _fsync_carpeta(os.path.dirname(destino))
    return entorno.sha256_bytes(datos)


def publicar_m5(carpeta_corrida, destino_ap) -> list[str]:
    """Publica ``decision.json``, la política, los resúmenes y las huellas de una corrida cerrada en
    ``<destino_ap>/config/meteorologia/meteo_combinada/v1/`` (§8, «Publicación (M5)»; SLD-11 a SLD-13).

    Paso aparte: se niega dentro de una corrida (``corrida_en_curso``, en cualquier hilo) y con una corrida no cerrada
    (``fallas_de_cierre``); con el AP real, la corrida es una hija de LOCAL/meteo_combinada/v1. Copia cada archivo byte
    a byte con su sha256 comprobado contra ``sha256.json`` (y éste contra el recibo). Devuelve las rutas publicadas,
    relativas a ``destino_ap``. Si ya están todas, idénticas, no escribe; si están algunas, idénticas, y ninguna más,
    completa las que faltan; si hay otras o distintas, se niega.
    """
    if hay_corrida_en_curso():
        raise RuntimeError("publicar_m5 es un paso aparte: nunca dentro de una corrida (§8; SLD-11)")
    carpeta = _carpeta_corrida(carpeta_corrida)
    base, base_fisica, real = _publicacion(destino_ap)
    if real:
        _exigir_corrida_real(carpeta)
    carpeta_fisica = _resolver(carpeta)[0]
    if any(_bajo(a, b, mayusculas=False) for a, b in ((base, carpeta), (carpeta, base),
                                                      (base_fisica, carpeta_fisica), (carpeta_fisica, base_fisica))):
        raise PermissionError("la publicación no va dentro de la corrida ni la corrida dentro de la publicación")
    if _resolver(base)[0] != base_fisica:
        raise PermissionError("la carpeta de publicación no pasa por un enlace (SLD-13)")
    fallas, estado = _cierre(carpeta)
    if fallas:
        raise PermissionError("la corrida no está cerrada; no se publica: " + "; ".join(fallas[:_CITADOS]))
    sellados = estado["sellados"]
    contenido: dict[str, bytes] = {}
    for nombre in _publicables(sellados):
        datos = _leer(os.path.join(carpeta, nombre))
        if nombre == SHA256_JSON:
            esperado = entorno.sha256_bytes(estado["sha256_json"])
        elif nombre == RECIBO:
            esperado = entorno.sha256_bytes(estado["recibo"])
        else:
            esperado = sellados[nombre]
        if entorno.sha256_bytes(datos) != esperado:
            raise PermissionError(f"{nombre} cambió mientras se publicaba (no es el de {SHA256_JSON})")
        _publicable(nombre, datos)
        contenido[nombre] = datos
    rutas = [f"{SUBRUTA_PUBLICACION}/{n}" for n in contenido]
    nuevos = {n: entorno.sha256_bytes(d) for n, d in contenido.items()}
    previos: dict[str, str] = {}
    if os.path.lexists(base):
        previos = {r: v["sha256"] for r, v in inventario(base).items()}
        for extra in (SHA256_JSON, RECIBO):            # inventario los deja fuera: aquí son parte de lo publicado
            ruta = os.path.join(base, extra)
            if os.path.lexists(ruta):
                previos[extra] = _huella_y_tamano(ruta)[0]
    if any(nuevos.get(r) != sha for r, sha in previos.items()):
        raise FileExistsError("ya hay otra publicación en config/meteorologia/meteo_combinada/v1; una errata se "
                              "publica aparte (§10; SLD-13)")
    for nombre, datos in contenido.items():
        if nombre not in previos:
            _escribir_publicacion(os.path.join(base, *nombre.split("/")), datos, base=base, base_fisica=base_fisica)
    for nombre, datos in contenido.items():
        if _huella_y_tamano(os.path.join(base, *nombre.split("/")))[0] != nuevos[nombre]:
            raise RuntimeError(f"{nombre}: lo publicado no tiene la huella de la corrida")
    return rutas
