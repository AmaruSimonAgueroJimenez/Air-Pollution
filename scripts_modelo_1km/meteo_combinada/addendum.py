"""Addendum de M1 (§10; MC-54; P44; A33): lista cerrada de huellas, anexo A2, compuerta de deriva, recorte, costo,
lecturas, decisiones, lecturas del diseño, diferencias, preguntas, acuerdos, la declaración sobre el C4 de RELOJ y
commits.

Qué hay:
- ``claves_lista_cerrada(rutas, *, carpeta_bateria)`` y ``lista_cerrada(rutas, *, bateria, rutas_bateria)``: qué entra
  en la lista cerrada {ruta por alias: sha256} y sus huellas del disco (ADD-1, ADD-2). ``verificar`` exige las claves.
- ``fuentes_documento(rutas)`` y ``referencia(rutas)``: el texto vigente y las fuentes de las lecturas con que se
  vigila un documento (``ceguera.ReferenciaDocumento``; CEG-18).
- ``extraer_lecturas``, ``extraer_mc``, ``decisiones_del_autor``, ``respondidas``, ``secciones_coordinacion`` y
  ``lecturas_m1(rutas)``: lo que el addendum copia del código del paquete, del diseño, de los tres archivos de
  decisiones y de ``COORDINACION_M1.md``.
- ``anexo_a2(rutas)``: el contenido de ``anexo_a2.json``, de ``constantes.anexo_a2`` sobre el texto vigente (v2.4).
- ``addendum_m1(lista, anexo_a2, deriva, recorte, costo, lecturas, commits, *, fecha, bateria)`` y
  ``addendum_md(contenido)``: el contenido de ``addendum_m1.json`` (clase documento, con las claves de ``CLAVES``) y su
  ``.md``. Este módulo no escribe: los escribe la batería por ``salidas`` en su subcarpeta de
  ``LOCAL/meteo_combinada/v1/m1/`` y el coordinador los copia a APH en un paso aparte (A33).

Dueño: I22 (ola 6; corregido tras la revisión independiente de la ola 6).
Lecturas propias (ADD-n), para el addendum de M1:
- ADD-1. **La lista cerrada** (§10, M1: «la lista cerrada de huellas (texto, JSON, código, pruebas y salida de la
  batería)»; MC-54; §9.3 y §9.4 del diseño). Entran, calculadas del disco: los textos del producto anclados en APH (v2.1
  con su JSON, su generador, su tabla de anclaje y sus huellas de M0; las Enmiendas 1 y 2 con el v2.2 y el v2.3,
  y la Enmienda 3 operativa con el v2.4; los tres archivos de decisiones del autor), todo ``.py`` del paquete y de ``tests/`` (también ``__init__.py``), los dos
  documentos del paquete (``COORDINACION_M1.md`` y ``DISENO_IMPLEMENTACION_M1.md``: el addendum copia su contenido, así
  que entran con su huella; rige la más estricta, P-ADD-1), el código fijado de ``fijados.HUELLAS_CODIGO`` (que trae
  además los textos del reloj, la Enmienda 2 ambiental, ``correr_v2.py``, ``config_v2.json`` y la configuración de la
  v3) y los diez archivos de la clausura del reloj. Si una huella del código fijado o de la clausura no es la fijada,
  la lista no se arma (``ErrorAddendum``): M1 no puede cambiarlas (§9.3 del diseño). Los datos de §9.3 no entran: los
  comprueba M2a con sus entradas (FIJ-4; decisión 4 de la coordinación). Las claves son rutas por alias, sin la
  carpeta de usuario ni la arroba. ``claves_lista_cerrada`` da las claves sin leer los archivos (para que ``verificar``
  exija que el addendum las traiga todas).
- ADD-2. **La salida de la batería en la lista** (§10, M1). Cada batería escribe en su subcarpeta
  ``LOCAL/meteo_combinada/v1/m1/<AAAAMMDDTHHMMSSZ>/`` (ENT-4 admite ``m1/<sub>``), así que su ``sha256.json`` lista sólo
  lo de esa corrida. ``bateria`` trae {alias: sha256} de sus seis salidas (``pruebas_m1.txt``, ``resumen_m1.json``,
  ``deriva_s6.json``, ``anexo_a2.json``, ``costo_m1.json`` y ``sha256.json``), todas de la misma subcarpeta; cada una se
  vuelve a leer del disco con su huella. El addendum se escribe después de ``sha256.json`` y no entra en él (no puede
  citar su propia huella); cita la subcarpeta en ``bateria.carpeta``.
- ADD-3. **Las lecturas** (§0, regla 9, del diseño: «Al cerrar M1 se copian al addendum»). Del encabezado (la cadena de
  documentación del módulo) de cada ``.py`` del paquete y de ``tests/``: cada viñeta que empieza en la columna 0 con un
  identificador «XXX-n» (lectura), «P-XXX-n» (pregunta del módulo) o «PED-n» (pedido), con sus líneas de continuación
  (sangradas); y las preguntas escritas en prosa («Preguntas para el autor (P-ORQ-n; …): P-ORQ-1 (…); P-ORQ-2 …»),
  partidas en cada «P-XXX-n» que abre un tramo. Se copian tal cual, con su módulo; una viñeta sangrada es parte de la
  anterior.
- ADD-4. **Las decisiones del autor.** Las filas de tabla «| Dn | … |» de los tres archivos de decisiones (enmienda1,
  m1 y enmienda3), con la huella de cada archivo; deben ir de D1 sin huecos y sin repetir. Las menciones en viñetas
  («- **D3:** …») son referencias, no decisiones. Una pregunta está **respondida** por la decisión que la nombra en su
  segunda columna («Pregunta», o el tema o el riesgo en las tablas de D1-D10: «P10: …», «P41 a P77»), o que dice
  «Pn queda descartada»; una mención en otra columna no la responde (P28 la responde D52, no D42); si dos la nombran,
  rige la última (P47: D56, después de D53).
- ADD-5. **Diferencias, preguntas, acuerdos y S6 de ``COORDINACION_M1.md``**, con su huella. Diferencias: los ítems
  (numerados o en viñeta) de las secciones «Diferencias con el diseño» y del párrafo «Diferencias con el diseño que se
  anotan» de la ola 1. Preguntas: las viñetas «- **Pn.** …» de las secciones «Preguntas para el autor», con su texto,
  las abiertas y las respondidas con su decisión; si una pregunta aparece en dos secciones, rige la
  última. Acuerdos: las viñetas «- **An.** …» (y «- **A2 y A3.** …») de las secciones «Acuerdos …», todas, con su
  sección y marcadas «revisado» las de una sección de acuerdos revisados; deben cubrir de A1 sin huecos. S6: las
  viñetas «- **S6-n.** …» de la sección de D15.
- ADD-6. **Por referencia, con su veredicto** (P44; CEG-18: un documento no lleva números de datos). La deriva, el
  anexo A2 y el costo van por su ruta por alias y su sha256; de la deriva, el veredicto de B y AB («pasa» o «falla»),
  que es la compuerta de §5.7 y fija ``Cfg.deriva``; del costo, el recorte («mod11» o «mod23»), que fija
  ``Cfg.recorte``, y los procesos por fase (ADD-12). Lo que falta queda «pendiente» y el addendum no habilita M2a ni
  M3-4 (``verificar`` se niega).
- ADD-7. **Los commits de M1** (MC-54: «``commit_m1`` de AP y de APH»). Hoy «pendiente» los dos: no hay commits sin
  la autorización del autor (A33). Un commit es un texto de 40 hexadecimales; M3-4 y M6 se niegan si alguno sigue
  pendiente.
- ADD-8. **La guarda del documento** (CEG-18). El addendum cita la huella entera del texto vigente y todo número suyo
  sale del texto o de las fuentes: el código y los documentos del paquete y los tres archivos de decisiones (rutas por
  alias de ``ceguera.RAICES_FUENTES``). No lleva enteros sueltos (ni conteos): las listas se cuentan solas, y los
  títulos del ``.md`` no traen rangos fijos. La batería lo escribe con ``salidas.escribir(…, clase="documento",
  referencia=referencia(rutas))``, que llama a ``ceguera.vigilar_salida``.
- ADD-9. **Las lecturas del diseño** (D5: «Lecturas MC-04 a MC-54 … Entran tal como están en el diseño al addendum de
  M1»). Las viñetas «- **MC-nn …**» de §7 de ``DISENO_IMPLEMENTACION_M1.md`` (todas, de §7.1 a §7.3), con su sección y
  su marca ([E], [D] o [M]).
- ADD-10. **El esquema exacto** (``CLAVES``). ``addendum_m1`` da siempre las mismas claves, en ese orden de
  ``CLAVES``; ``verificar`` exige exactamente ésas, el texto vigente v2.4 con su huella, la batería aprobada y su
  subcarpeta.
- ADD-11. **La declaración sobre el C4 de RELOJ** (§10: «M1 se sella antes del C4 de RELOJ si alcanza. Si no, rige el
  ítem prospectivo de §1.9 y, desde el inicio del C4 de RELOJ, el régimen estricto de abajo para todo cambio de M1»;
  P122). M1 no alcanzó: la corrida confirmatoria C4 de RELOJ quedó sellada el 2026-10-27. El addendum lo declara
  (``DECLARACION_C4``): qué se leyó del reloj, qué olas de M1 fueron antes y después del inicio del C4, y la lectura
  para el código posterior, con la excepción operativa formalizada por D65.
- ADD-12. **Los procesos por fase** (D59, respuesta a P145: «La fase que no quepa en memoria con 8 procesos corre con
  el mayor número que quepa … Se declara en el addendum y en el registro de M3-4, y modifica D2 sólo en esa fase»; A39;
  P146, la extensión a M5). El costo de entrada es {ruta, sha256, recorte, procesos_por_fase} y el del addendum
  {ruta, sha256, veredicto, procesos_por_fase}, con «procesos_por_fase» = {compuerta: {fase: n}} tal como sale de
  ``costo_m1.json``. Con el veredicto «mod11» o «mod23», cada n es un entero (no bool) de 1 a
  ``constantes.valor("PROCESOS")``; este módulo valida sólo la forma (no importa ``orquestacion``) y ``verificar``
  coteja los nombres exactos con ``orquestacion.FASES_REPARTO``. Un costo medido con el recorte «pendiente» (una fase
  que no cabe ni con 1 proceso, o sin medir; A39) deja el recorte y el costo «pendiente», sin error, y el addendum no
  habilita ninguna corrida. El ``.md`` muestra los procesos por fase en la línea del costo, con la declaración de D59
  (``DECLARACION_D59``): D59 no cambia ningún bit por sí mismo (S9), pero la pared que se vuelve a proyectar con esos
  procesos decide el recorte de §4.9 (§8), que sí cambia los días de selección; si con P = 8 el recorte fuera otro,
  ``costo_m1.json`` lo dice en una nota de su veredicto. D64 la adoptó; P147 está cerrada y D65 la formaliza como
  EMC3-2.
- ADD-13. **Enmienda operativa posterior al C4 (D65).** El esquema /2 agrega ``enmienda_operativa``: ``post_hoc``
  debe ser True, con la regla anclada y la enmendada, las fuentes y lo visto. El lector, el formateador y el escritor
  exigen por sí mismos esta declaración y ``DECLARACION_C4`` exactas con la comprobación privada común. No se propaga
  ese post_hoc a C5 ni se elimina ninguna negativa del reloj.
Preguntas para el autor (P-ADD-n; rige la más estricta):
- P-ADD-1. Cita: §10, M1, «la lista cerrada de huellas (texto, JSON, código, pruebas y salida de la batería)»; §9.4
  del diseño, «el paquete ``meteo_combinada/`` (cada archivo)». Problema: con los dos documentos del paquete en la
  lista, cada nota posterior del coordinador en ``COORDINACION_M1.md`` hace que M3-4 se niegue hasta un addendum
  nuevo. Rige (la más estricta, pedida en la revisión): entran. Propuesta: ratificarlo, o sacar los documentos de la
  lista y dejar en el addendum sólo su huella como fuente.
- P-ADD-2 (P122). La declaración sobre el C4 de RELOJ (ADD-11): rige la lectura de ``DECLARACION_C4``. La responde
  D60 («P80 a P144, incluida P122»): entra al addendum tal como está, y si un revisor ve que alguna lectura cambia una
  regla, se le pregunta aparte al autor.
Pedidos (PED-n): ninguno propio (los de la ola van en ``verificar_meteo_combinada``).
Depende de: umbrales, constantes, fijados, entorno, ceguera.
"""
from __future__ import annotations

import ast
import gzip
import json
import re
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from meteo_combinada import ceguera, constantes, entorno, fijados, umbrales

ESQUEMA = "meteo-combinada-addendum-m1/2"
PENDIENTE = "pendiente"
NOMBRE_JSON = "addendum_m1.json"
NOMBRE_MD = "addendum_m1.md"
VEREDICTOS = ("pasa", "falla")
CANDIDATOS_DERIVA = ("B", "AB")                     # §5.7: la compuerta de deriva es de B y AB

# Dónde está cada cosa (relativa a su repositorio).
CARPETA_PAQUETE = "scripts_modelo_1km/meteo_combinada"                       # AP
COORDINACION = "COORDINACION_M1.md"
DISENO = "DISENO_IMPLEMENTACION_M1.md"
DOCUMENTOS_PAQUETE = (COORDINACION, DISENO)
_PRODUCTO = "auditoria/20261023/meteo_combinada"                              # APH
CARPETA_PRODUCTO = _PRODUCTO
DECISIONES = (f"{_PRODUCTO}/enmienda1/decisiones_autor_20261026.md",          # D1-D8
              f"{_PRODUCTO}/m1/decisiones_autor_m1_20261026.md",              # D9-D64
              f"{_PRODUCTO}/enmienda3/decisiones_autor_20261028.md")           # D65-D67
TEXTO_V2_2 = f"{_PRODUCTO}/enmienda1/PROTOCOLO_METEO_COMBINADA_v2.2.md"
TEXTO_V2_3 = f"{_PRODUCTO}/enmienda2/PROTOCOLO_METEO_COMBINADA_v2.3.md"
# ADD-1: textos y decisiones; EMC3 anclada en APH ae670dd (sello b07791e), más su concordancia técnica.
TEXTOS_PRODUCTO = (umbrales.TEXTO_M0, umbrales.JSON_M0, umbrales.PREPARAR_M0, f"{_PRODUCTO}/m0/tabla_anclaje_m0.json",
                   f"{_PRODUCTO}/m0/huellas_m0.json", f"{_PRODUCTO}/enmienda1/ENMIENDA_1.md", TEXTO_V2_2,
                   f"{_PRODUCTO}/enmienda2/ENMIENDA_2.md", TEXTO_V2_3,
                   f"{_PRODUCTO}/enmienda3/ENMIENDA_3.md", f"{_PRODUCTO}/enmienda3/generar_v2_4.py",
                   f"{_PRODUCTO}/enmienda3/NOTA_FIRMAS_RECIBOS.md",
                   f"{_PRODUCTO}/enmienda3_borrador/BORRADOR_ENMIENDA_3_PROCESOS.md",
                   umbrales.TEXTO_VIGENTE, *DECISIONES)
# ADD-2: lo que escribe la batería en su subcarpeta de LOCAL/meteo_combinada/v1/m1/.
SALIDA_BATERIA = ("pruebas_m1.txt", "resumen_m1.json", "deriva_s6.json", "anexo_a2.json", "costo_m1.json",
                  "sha256.json")
PREFIJO_M1 = "LOCAL/meteo_combinada/v1/m1/"
# ADD-10: las claves de addendum_m1.json, en este orden.
CLAVES = ("esquema", "fecha", "texto_vigente", "textos_anteriores", "umbrales", "lista_cerrada", "anexo_a2", "deriva",
          "recorte", "costo", "lecturas", "lecturas_diseno", "decisiones", "diferencias", "preguntas_abiertas",
          "preguntas_respondidas", "acuerdos", "declaracion_c4_reloj", "enmienda_operativa", "fuentes", "commits", "bateria")
# ADD-11 (P122): la declaración sobre el C4 de RELOJ, tal como va al addendum.
DECLARACION_C4 = MappingProxyType({
    "hecho": ("La corrida confirmatoria C4 de RELOJ (HUMAN20261027_RELOJ_DMC_1) quedó sellada el 2026-10-27 a las "
              "13:06 hora de Chile (APH 4e16614), antes de sellar M1. Por §10 rigen el ítem prospectivo de §1.9 y, "
              "desde el inicio del C4 de RELOJ, el régimen estricto para todo cambio de M1."),
    "item_prospectivo": ("Se cumplió el ítem prospectivo de §1.9: nadie del equipo de M1 abrió el informe ni las tablas "
                         "de evidencia del reloj. Del reloj sólo se leyó su código, los umbrales anclados de C0 y, por "
                         "su huella, el JSON y el generador del v1.2 (FIJ-11); la política publicada no se abrió en M1 "
                         "(las pruebas usan políticas y registros de C5 sintéticos)."),
    "olas": ("Antes del inicio del C4 de RELOJ (2026-10-27): las olas 0 a 3 de M1 y las Enmiendas 1 y 2 del producto "
             "(APH 0517360 y dd6c1c6). Después: las olas 4 a 6."),
    "lectura_propuesta": ("Las olas 4 a 6 implementan el texto, salvo la regla operativa D59/D63/D64 de §8, que sí es "
                          "enmienda: D65 la formaliza como EMC3, post_hoc = true por su fecha posterior al inicio "
                          "del C4 de RELOJ. No se cambia §10 ni se presenta esa regla como mera implementación."),
    "pregunta": ("P122 cerrada por D60; D65 formaliza la excepción operativa. P79, P145 y P147 siguen cerradas por "
                 "D58, D59 y D64. No se vieron informes ni tablas de evidencia del reloj ni competencia "
                 "meteorológica real para elegir la regla."),
})
# ADD-13 (D65): metadatos del producto, separados de post_hoc de la política C5 del reloj.
ENMIENDA_OPERATIVA = MappingProxyType({
    "id": "EMC3", "fecha": "2026-10-28", "post_hoc": True, "decision": "D65",
    "decisiones_formalizadas": "D59, D63 y D64",
    "fuente": f"APH/{_PRODUCTO}/enmienda3/decisiones_autor_20261028.md",
    "enmienda": f"APH/{_PRODUCTO}/enmienda3/ENMIENDA_3.md",
    "texto_anclado": f"APH/{TEXTO_V2_3}", "sha256_anclado": fijados.SHA_TEXTO_V2_3,
    "texto_enmendado": f"APH/{umbrales.TEXTO_VIGENTE}", "sha256_enmendado": umbrales.SHA_TEXTO_VIGENTE,
    "regla_anclada": "v2.3 §8: M3-4 con 8 procesos; recorte de §4.9 desde la proyección.",
    "regla_enmendada": ("v2.4 §8: hasta 8 procesos, el mayor número que cumpla los topes por fase de M3-4 y M5; "
                        "recorte antes de M3-4 con la proyección efectiva, conservando además la de 8 procesos."),
    "lo_visto": ("Código, pruebas sintéticas y ensayos preliminares de costo de M1. S6 vista y congelada: D58 "
                 "ratifica B y AB fuera. Sin costo final ni competencia meteorológica real vistos para elegir "
                 "procesos o recorte. No se abrieron informes ni tablas de evidencia del reloj."),
    "limite": ("Esta enmienda no cambia el reloj ni su política C5, ni S6; no autoriza dos corridas confirmatorias "
               "ni elimina negativas de integridad, ceguera, procedencia y testigo externo."),
})
# ADD-12 (D59, A39, P146): la declaración que acompaña a los procesos por fase en el .md.
DECLARACION_D59 = (f"D59/P145 y D63/P146, formalizadas por D65 (EMC3-1): hasta {constantes.valor('PROCESOS')} "
                   "procesos por fase de M3-4 y M5. No cambia bits por sí mismo (S9) para un recorte dado, pero la "
                   "duración efectiva sí puede cambiar el recorte y los días de selección. D64/P147 (EMC3-2): "
                   "§4.9 y §8, desde la proyección efectiva; costo_m1.json conserva también la proyección de "
                   f"{constantes.valor('PROCESOS')} procesos e informa si daría otro recorte. post_hoc = true por §10.")


_SHA = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_FECHA = re.compile(r"\d{4}-\d{2}-\d{2}")
_RECORTE = re.compile(r"mod\d+")
_SUB = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_NOMBRE_FASE = re.compile(r"[a-z][a-z0-9_]*")       # ADD-12: una compuerta («m34») o una fase («anual»)
# ADD-3: una viñeta de lectura, pregunta o pedido en la columna 0 de un encabezado; una pregunta en prosa.
_ITEM = re.compile(r"^- (?:\*\*)?(?P<id>(?:P-)?[A-Z]{2,4}-\d+)\b")
_PROSA = re.compile(r"^Preguntas para el autor \(P-[A-Z]{2,4}-n")
_TRAMO_PROSA = re.compile(r"(?:^|(?<=; ))(?P<id>P-[A-Z]{2,4}-\d+)\b")
_FIN_PARRAFO = ("Pedidos", "Diferencias", "Depende de", "Lecturas", "Firmas", "Preguntas")
# ADD-4: una fila de decisión.
_FILA_D = re.compile(r"^\|\s*D(?P<n>\d+)\s*\|(?P<resto>.*)\|\s*$")
_P_CITADA = re.compile(r"\bP(?P<a>\d+)(?:\s+a\s+P(?P<b>\d+))?\b")
_DESCARTADA = re.compile(r"\bP(?P<n>\d+) queda descartada\b")
# ADD-5: ítems de COORDINACION_M1.md.
_TITULO = re.compile(r"^(?P<nivel>#{2,3}) (?P<texto>.+?)\s*$")
_ITEM_LISTA = re.compile(r"^(?:- |\d+\. )")
_NUMERO_LISTA = re.compile(r"^(?P<n>\d+)\. |^- \*\*(?P<m>\d+)\.\*\*")
_PREGUNTA = re.compile(r"^- \*\*P(?P<n>\d+)\.")
_ACUERDO = re.compile(r"^- \*\*(?P<ids>A\d+(?: y A\d+)*)\.")
_S6 = re.compile(r"^- \*\*(?P<id>S6-\d+)\.")
_DIFERENCIAS = "Diferencias con el diseño"
_PREGUNTAS = "Preguntas para el autor"
_ACUERDOS = "Acuerdos"
_REVISADOS = "revisad"
_D15 = "D15: los parámetros de S6"
# ADD-9: las lecturas MC-nn de §7 del diseño.
_MC = re.compile(r"^- \*\*(?P<id>MC-\d+)(?P<marca>[^*]*?)(?:\*\*|\.)")
_MARCA = re.compile(r"\[(?P<m>[EDM])\b")


class ErrorAddendum(ValueError):
    """La lista cerrada, las lecturas o el contenido del addendum no se pueden armar como fija §10 (MC-54)."""


# ---------------------------------------------------------------------------
# Lista cerrada (ADD-1, ADD-2)
# ---------------------------------------------------------------------------
def _leer(ruta: Path) -> bytes:
    with open(ruta, "rb") as f:
        return f.read()


def codigo_del_paquete(ap) -> dict[str, Path]:
    """{ruta por alias: ruta} de cada ``.py`` del paquete y de ``tests/`` bajo ``ap`` (ADD-1)."""
    carpeta = Path(ap) / CARPETA_PAQUETE
    salida = {f"AP/{CARPETA_PAQUETE}/{p.name}": p for p in sorted(carpeta.glob("*.py"))}
    salida.update({f"AP/{CARPETA_PAQUETE}/tests/{p.name}": p for p in sorted((carpeta / "tests").glob("*.py"))})
    if not salida:
        raise ErrorAddendum("el paquete no tiene código (ADD-1)")
    return salida


def _exigir_alias(alias_: str) -> None:
    if not isinstance(alias_, str) or not ceguera.es_ruta_por_alias(alias_) or not entorno.sin_datos_privados(alias_) \
            or any(p in ("", ".", "..") for p in alias_.split("/")):
        raise ErrorAddendum("la lista cerrada va por rutas por alias, sin la carpeta de usuario ni la arroba (ADD-1)")


def carpeta_bateria(alias_: str) -> str:
    """El alias de la subcarpeta de una batería (``LOCAL/meteo_combinada/v1/m1/<sub>``), comprobado (ADD-2)."""
    if not isinstance(alias_, str) or not alias_.startswith(PREFIJO_M1) \
            or not _SUB.fullmatch(alias_[len(PREFIJO_M1):]):
        raise ErrorAddendum(f"la batería escribe en {PREFIJO_M1}<subcarpeta> (ADD-2)")
    return alias_


def _fijadas(rutas) -> dict[str, tuple[Path, str | None]]:
    """{alias: (ruta, huella fijada o None)} de lo que entra en la lista sin la batería (ADD-1)."""
    raices = {"AP": Path(rutas.ap), "APH": Path(rutas.aph)}
    salida: dict[str, tuple[Path, str | None]] = {}
    for rel in TEXTOS_PRODUCTO:
        salida[f"APH/{rel}"] = (raices["APH"] / rel, None)
    for repo, rel, sha, _ in fijados.HUELLAS_CODIGO:
        salida[f"{repo}/{rel}"] = (raices[repo] / rel, sha)
    for modulo in fijados.ARCHIVOS_CLAUSURA:
        rel = f"{fijados.RUTA_RELOJ}/{modulo}.py"
        salida[f"AP/{rel}"] = (raices["AP"] / rel, fijados.HUELLAS_CLAUSURA[modulo])
    for alias_, ruta in codigo_del_paquete(rutas.ap).items():
        salida[alias_] = (ruta, None)
    for nombre in DOCUMENTOS_PAQUETE:
        salida[f"AP/{CARPETA_PAQUETE}/{nombre}"] = (raices["AP"] / CARPETA_PAQUETE / nombre, None)
    return salida


def huellas_fijadas() -> dict[str, str]:
    """{alias: sha256} de lo que M1 no puede cambiar: el código fijado y la clausura del reloj (§9.3 del diseño)."""
    salida = {f"{repo}/{rel}": sha for repo, rel, sha, _ in fijados.HUELLAS_CODIGO}
    salida.update({f"AP/{fijados.RUTA_RELOJ}/{m}.py": fijados.HUELLAS_CLAUSURA[m] for m in fijados.ARCHIVOS_CLAUSURA})
    return salida


def claves_lista_cerrada(rutas, *, carpeta_bateria_: str | None = None) -> list[str]:
    """Las claves que debe traer la lista cerrada (ADD-1, ADD-2), sin leer los archivos; con ``carpeta_bateria_``,
    también las seis salidas de esa batería."""
    claves = set(_fijadas(rutas))
    if carpeta_bateria_ is not None:
        base = carpeta_bateria(carpeta_bateria_)
        claves.update(f"{base}/{n}" for n in SALIDA_BATERIA)
    return sorted(claves)


def lista_cerrada(rutas, *, bateria: Mapping[str, str] | None = None, rutas_bateria=None) -> dict[str, str]:
    """{ruta por alias: sha256} de §10 (ADD-1, ADD-2), en orden de alias. ``ErrorAddendum`` si falta un archivo, si una
    huella del código fijado o de la clausura del reloj no es la fijada, o si una de ``bateria`` no es la del disco o no
    está en una sola subcarpeta de ``m1``. ``rutas_bateria``: dónde está ``LOCAL`` de la batería (por omisión,
    ``rutas``)."""
    salida: dict[str, str] = {}

    def poner(alias_: str, ruta: Path, esperado: str | None = None) -> None:
        _exigir_alias(alias_)
        try:
            sha = entorno.sha256_bytes(_leer(ruta))
        except FileNotFoundError as e:
            raise ErrorAddendum(f"{alias_}: no existe (ADD-1)") from e
        if esperado is not None and sha != esperado:
            raise ErrorAddendum(f"{alias_}: su sha256 no es la fijada; M1 no puede cambiarla (§9.3 del diseño)")
        if salida.get(alias_, sha) != sha:
            raise ErrorAddendum(f"{alias_}: dos huellas distintas en la lista cerrada")
        salida[alias_] = sha

    for alias_, (ruta, esperado) in _fijadas(rutas).items():
        poner(alias_, ruta, esperado)
    rb = rutas if rutas_bateria is None else rutas_bateria
    subcarpetas = set()
    for alias_, sha in sorted((bateria or {}).items()):
        base, _, nombre = str(alias_).rpartition("/")
        try:
            carpeta_bateria(base)
        except ErrorAddendum:
            raise ErrorAddendum(f"{alias_}: la salida de la batería va en {PREFIJO_M1}<subcarpeta> (ADD-2)") from None
        if nombre not in SALIDA_BATERIA or not isinstance(sha, str) or not _SHA.fullmatch(sha):
            raise ErrorAddendum(f"{alias_}: la salida de la batería es {list(SALIDA_BATERIA)} (ADD-2)")
        subcarpetas.add(base)
        sub = base[len(PREFIJO_M1):]
        poner(alias_, entorno.carpeta_salida(rb, "m1", sub) / nombre, sha)
    if len(subcarpetas) > 1:
        raise ErrorAddendum("la salida de la batería es de una sola subcarpeta de m1 (ADD-2)")
    if salida.get(f"APH/{umbrales.TEXTO_VIGENTE}") != umbrales.SHA_TEXTO_VIGENTE:
        raise ErrorAddendum("el texto vigente no es el v2.4 declarado")
    return dict(sorted(salida.items()))


# ---------------------------------------------------------------------------
# Fuentes y referencia del documento (ADD-8; CEG-18)
# ---------------------------------------------------------------------------
def fuentes_documento(rutas) -> dict[str, str]:
    """{ruta por alias: texto} de las fuentes de las lecturas: el código y los documentos del paquete y los tres
    archivos de decisiones del autor."""
    carpeta = Path(rutas.ap) / CARPETA_PAQUETE
    salida = {a: _leer(p).decode("utf-8") for a, p in codigo_del_paquete(rutas.ap).items()}
    for nombre in DOCUMENTOS_PAQUETE:
        salida[f"AP/{CARPETA_PAQUETE}/{nombre}"] = _leer(carpeta / nombre).decode("utf-8")
    for rel in DECISIONES:
        salida[f"APH/{rel}"] = _leer(Path(rutas.aph) / rel).decode("utf-8")
    return salida


def texto_vigente(rutas) -> tuple[str, str]:
    """(texto, sha256) del texto vigente v2.4, comprobado contra ``umbrales.SHA_TEXTO_VIGENTE``."""
    datos = _leer(Path(rutas.aph) / umbrales.TEXTO_VIGENTE)
    sha = entorno.sha256_bytes(datos)
    if sha != umbrales.SHA_TEXTO_VIGENTE:
        raise ErrorAddendum("el texto vigente no es el v2.4 declarado")
    return datos.decode("utf-8"), sha


def referencia(rutas, *, fuentes: Mapping[str, str] | None = None) -> "ceguera.ReferenciaDocumento":
    """La ``ReferenciaDocumento`` del texto vigente con las fuentes de las lecturas (por omisión, todas las de
    ``fuentes_documento``)."""
    texto, sha = texto_vigente(rutas)
    return ceguera.ReferenciaDocumento(texto, sha, fuentes=fuentes_documento(rutas) if fuentes is None else fuentes)


def anexo_a2(rutas) -> dict:
    """El contenido de ``anexo_a2.json`` (§10: «M1 los lista en un anexo A2 generado del texto»), del v2.4."""
    texto, sha = texto_vigente(rutas)
    return constantes.anexo_a2(texto, sha)


# ---------------------------------------------------------------------------
# Lecturas (ADD-3 a ADD-5, ADD-9)
# ---------------------------------------------------------------------------
def _texto_de_item(lineas: Sequence[str]) -> str:
    primera = lineas[0][len("- "):] if lineas[0].startswith("- ") else lineas[0]
    resto = [ln[len("  "):] if ln.startswith("  ") else ln.lstrip() for ln in lineas[1:]]
    return "\n".join([primera, *resto]).rstrip()


def _items(lineas: Sequence[str], inicio=_ITEM_LISTA) -> list[list[str]]:
    """Ítems de lista en la columna 0 con sus líneas de continuación (sangradas); otra línea termina el ítem."""
    salida: list[list[str]] = []
    actual: list[str] | None = None
    for linea in lineas:
        if inicio.match(linea):
            actual = [linea]
            salida.append(actual)
        elif actual is not None and linea[:1] in (" ", "\t") and linea.strip():
            actual.append(linea)
        else:
            actual = None
    return salida


def _tipo(ident: str) -> str:
    if ident.startswith("P-"):
        return "pregunta"
    if ident.startswith("PED-"):
        return "pedido"
    return "lectura"


def _preguntas_en_prosa(doc: str) -> list[tuple[str, str]]:
    """ADD-3: (id, texto) de cada «P-XXX-n» del párrafo «Preguntas para el autor (P-XXX-n…): …» en prosa."""
    salida = []
    lineas = doc.splitlines()
    for i, linea in enumerate(lineas):
        if not _PROSA.match(linea):
            continue
        parrafo = [linea]
        for siguiente in lineas[i + 1:]:
            if not siguiente.strip() or siguiente.startswith(("- ", *_FIN_PARRAFO)):
                break
            parrafo.append(siguiente)
        texto = " ".join(x.strip() for x in parrafo)
        cuerpo = (texto.split("):", 1)[1] if "):" in texto else texto).strip()
        marcas = list(_TRAMO_PROSA.finditer(cuerpo))
        for k, m in enumerate(marcas):
            fin = marcas[k + 1].start() if k + 1 < len(marcas) else len(cuerpo)
            salida.append((m.group("id"), cuerpo[m.start():fin].strip(" ;")))
    return salida


def extraer_lecturas(fuentes: Mapping[str, str]) -> list[dict]:
    """ADD-3: {modulo, id, tipo, texto} de cada viñeta «XXX-n», «P-XXX-n» o «PED-n» del encabezado de cada ``.py`` de
    ``fuentes`` ({ruta por alias: texto}) y de cada pregunta en prosa, en el orden del archivo y por alias."""
    salida = []
    for alias_, texto in sorted(fuentes.items()):
        if not alias_.endswith(".py"):
            continue
        doc = ast.get_docstring(ast.parse(texto, filename=PurePosixPath(alias_).name), clean=False) or ""
        vistas = set()
        for lineas in _items(doc.splitlines(), _ITEM):
            ident = _ITEM.match(lineas[0]).group("id")
            vistas.add(ident)
            salida.append({"modulo": alias_, "id": ident, "tipo": _tipo(ident), "texto": _texto_de_item(lineas)})
        for ident, tramo in _preguntas_en_prosa(doc):
            if ident not in vistas:
                vistas.add(ident)
                salida.append({"modulo": alias_, "id": ident, "tipo": "pregunta", "texto": tramo})
    return salida


def extraer_mc(diseno: str) -> list[dict]:
    """ADD-9: {id, marca, seccion, texto} de cada viñeta «- **MC-nn …**» de §7 del diseño."""
    salida = []
    lineas = diseno.splitlines()
    bloques: list[tuple[str, list[str]]] = []
    seccion, en_7 = "", False
    actual: list[str] | None = None
    for linea in lineas:
        t = _TITULO.match(linea)
        if t:
            en_7, seccion, actual = t.group("texto").startswith("7"), t.group("texto"), None
            continue
        if not en_7:
            continue
        if _MC.match(linea):
            actual = [linea]
            bloques.append((seccion, actual))
        elif actual is not None and linea[:1] in (" ", "\t") and linea.strip():
            actual.append(linea)
        else:
            actual = None
    for seccion, lineas_mc in bloques:
        m = _MC.match(lineas_mc[0])
        marca = _MARCA.search(m.group("marca") or "")
        salida.append({"id": m.group("id"), "marca": marca.group("m") if marca else None, "seccion": seccion,
                       "texto": _texto_de_item(lineas_mc)})
    if not salida:
        raise ErrorAddendum("el diseño no trae lecturas MC-nn en §7 (ADD-9)")
    return salida


def decisiones_del_autor(textos: Mapping[str, str]) -> list[dict]:
    """ADD-4: {id, fuente, pregunta, texto} de cada fila «| Dn | … |», en orden de n (``pregunta``: su segunda
    columna); ``ErrorAddendum`` con huecos o repetidas."""
    filas = []
    for alias_, texto in textos.items():
        for linea in texto.splitlines():
            m = _FILA_D.match(linea)
            if m:
                celdas = [c.strip() for c in m.group("resto").split("|")]
                filas.append((int(m.group("n")), alias_, celdas[0] if celdas else "",
                              " | ".join([f"D{m.group('n')}", *celdas])))
    numeros = [n for n, _, _, _ in filas]
    if not numeros or sorted(numeros) != list(range(1, max(numeros) + 1)):
        raise ErrorAddendum("las decisiones del autor deben ir de D1 sin huecos ni repetidas (ADD-4)")
    return [{"id": f"D{n}", "fuente": a, "pregunta": p, "texto": t} for n, a, p, t in sorted(filas)]


def respondidas(decisiones: Sequence[Mapping]) -> dict[str, str]:
    """ADD-4: {Pn: Dm} de las preguntas que una fila de decisión nombra en su columna de la pregunta (también «P41 a
    P77») o declara descartadas («Pn queda descartada»); si la nombran dos, rige la última (D56 responde P47 después de
    D53)."""
    salida: dict[str, str] = {}
    for d in decisiones:
        for m in _P_CITADA.finditer(d.get("pregunta", "")):
            a = int(m.group("a"))
            b = int(m.group("b")) if m.group("b") else a
            for n in range(a, b + 1):
                salida[f"P{n}"] = d["id"]
        for m in _DESCARTADA.finditer(d["texto"]):
            salida[f"P{m.group('n')}"] = d["id"]
    return dict(sorted(salida.items(), key=lambda kv: int(kv[0][1:])))


def secciones_coordinacion(texto: str) -> dict[str, list[dict]]:
    """ADD-5: {"diferencias", "preguntas", "acuerdos", "parametros_s6"} de ``COORDINACION_M1.md``, cada ítem con su
    sección («## …» › «### …»)."""
    ola, sub, tipo_titulo, en_parrafo = "", "", None, False
    bloques: list[tuple[str | None, str, list[str]]] = []

    def seccion() -> str:
        return f"{ola} › {sub}" if sub else ola

    for linea in texto.splitlines():
        t = _TITULO.match(linea)
        if t:
            if t.group("nivel") == "##":
                ola, sub = t.group("texto"), ""
            else:
                sub = t.group("texto")
            titulo = t.group("texto")
            tipo_titulo = ("diferencias" if _DIFERENCIAS in titulo else "preguntas" if _PREGUNTAS in titulo
                           else "acuerdos" if titulo.startswith(_ACUERDOS)
                           else "parametros_s6" if titulo.startswith(_D15) else None)
            en_parrafo = False
            bloques.append((tipo_titulo, seccion(), []))
            continue
        if linea.startswith("**"):
            # El párrafo «**Diferencias con el diseño que se anotan**» de la ola 1 (ADD-5) dura hasta el siguiente
            # párrafo en negrita; los demás párrafos en negrita (subtítulos de preguntas) no cambian la sección.
            if _DIFERENCIAS in linea:
                en_parrafo = True
                bloques.append(("diferencias", seccion(), []))
                continue
            if en_parrafo:
                en_parrafo = False
                bloques.append((tipo_titulo, seccion(), []))
                continue
        if bloques:
            bloques[-1][2].append(linea)
    salida: dict[str, list[dict]] = {"diferencias": [], "preguntas": [], "acuerdos": [], "parametros_s6": []}
    for tipo, seccion_, lineas in bloques:
        if tipo is None:
            continue
        for item in _items(lineas):
            texto_item, cabeza = _texto_de_item(item), item[0]
            if tipo == "diferencias":
                m = _NUMERO_LISTA.match(cabeza)
                numero = None if m is None else (m.group("n") or m.group("m"))
                salida[tipo].append({"seccion": seccion_, "numero": numero, "texto": texto_item})
            elif tipo == "preguntas" and (m := _PREGUNTA.match(cabeza)):
                salida[tipo].append({"seccion": seccion_, "id": f"P{m.group('n')}", "texto": texto_item})
            elif tipo == "acuerdos" and (m := _ACUERDO.match(cabeza)):
                salida[tipo].append({"seccion": seccion_, "ids": m.group("ids").split(" y "), "texto": texto_item,
                                     "revisado": _REVISADOS in seccion_.casefold()})
            elif tipo == "parametros_s6" and (m := _S6.match(cabeza)):
                salida[tipo].append({"seccion": seccion_, "id": m.group("id"), "texto": texto_item})
    vistos = sorted({int(i[1:]) for a in salida["acuerdos"] for i in a["ids"]})
    if not vistos or vistos != list(range(1, vistos[-1] + 1)):
        raise ErrorAddendum("los acuerdos deben ir de A1 sin huecos (ADD-5)")
    if not salida["parametros_s6"]:
        raise ErrorAddendum("COORDINACION_M1.md no trae los parámetros de S6 de D15 (ADD-5)")
    return salida


def lecturas_m1(rutas, *, fuentes: Mapping[str, str] | None = None) -> dict:
    """Lo textual del addendum (ADD-3 a ADD-5, ADD-9): lecturas del código, del diseño, D1-Dn, parámetros de S6,
    diferencias, preguntas abiertas y respondidas (con su texto), acuerdos y las fuentes con su huella."""
    fuentes = fuentes_documento(rutas) if fuentes is None else dict(fuentes)
    alias_coord = f"AP/{CARPETA_PAQUETE}/{COORDINACION}"
    alias_diseno = f"AP/{CARPETA_PAQUETE}/{DISENO}"
    decisiones = decisiones_del_autor({f"APH/{rel}": fuentes[f"APH/{rel}"] for rel in DECISIONES})
    secciones = secciones_coordinacion(fuentes[alias_coord])
    resp = respondidas(decisiones)
    ultima: dict[str, dict] = {}
    for p in secciones["preguntas"]:
        ultima[p["id"]] = p
    orden = sorted(ultima.items(), key=lambda kv: int(kv[0][1:]))
    abiertas = [p for i, p in orden if i not in resp]
    resueltas = [{**p, "decision": resp[i]} for i, p in orden if i in resp]
    return {"lecturas": extraer_lecturas(fuentes), "lecturas_diseno": extraer_mc(fuentes[alias_diseno]),
            "decisiones": decisiones, "parametros_s6": secciones["parametros_s6"],
            "diferencias": secciones["diferencias"], "preguntas_abiertas": abiertas,
            "preguntas_respondidas": resueltas, "acuerdos": secciones["acuerdos"],
            "fuentes": {a: entorno.sha256_bytes(t.encode("utf-8")) for a, t in sorted(fuentes.items())}}


# ---------------------------------------------------------------------------
# El addendum (ADD-6 a ADD-8, ADD-10, ADD-11)
# ---------------------------------------------------------------------------
def _referencia_archivo(x, que: str) -> dict:
    if not isinstance(x, Mapping) or not {"ruta", "sha256"} <= set(x) or not isinstance(x["ruta"], str) \
            or not ceguera.es_ruta_por_alias(x["ruta"]) or not isinstance(x["sha256"], str) \
            or not _SHA.fullmatch(x["sha256"]):
        raise ErrorAddendum(f"{que}: {{ruta por alias, sha256}} (ADD-6)")
    return {"ruta": x["ruta"], "sha256": x["sha256"]}


def _procesos_por_fase(x) -> dict[str, dict[str, int]]:
    """ADD-12 (D59; A39): la forma de «procesos_por_fase», {compuerta: {fase: n}}, con cada n un entero (no bool) de 1
    a ``constantes.valor("PROCESOS")``; ``ErrorAddendum`` si no la tiene. Los nombres exactos los coteja ``verificar``
    con ``orquestacion.FASES_REPARTO``."""
    tope = int(constantes.valor("PROCESOS"))
    forma = "procesos_por_fase es {compuerta: {fase: n}}, con cada n un entero de 1 a PROCESOS (D59, A39)"
    if not isinstance(x, Mapping) or not x:
        raise ErrorAddendum(forma)
    salida: dict[str, dict[str, int]] = {}
    for compuerta, fases in x.items():
        if not isinstance(compuerta, str) or not _NOMBRE_FASE.fullmatch(compuerta) or not isinstance(fases, Mapping) \
                or not fases:
            raise ErrorAddendum(forma)
        salida[compuerta] = {}
        for fase, n in fases.items():
            if not isinstance(fase, str) or not _NOMBRE_FASE.fullmatch(fase) or isinstance(n, bool) \
                    or not isinstance(n, int) or not 1 <= n <= tope:
                raise ErrorAddendum(forma)
            salida[compuerta][fase] = int(n)
    return salida


def veredicto_deriva(pasa: Mapping[str, bool]) -> dict[str, str]:
    """{«B»: «pasa»|«falla», «AB»: …} de la compuerta de deriva ({«B»: bool, «AB»: bool})."""
    if set(pasa) != set(CANDIDATOS_DERIVA) or not all(isinstance(v, bool) for v in pasa.values()):
        raise ErrorAddendum("la compuerta de deriva es {«B»: bool, «AB»: bool} (§5.7)")
    return {c: VEREDICTOS[0] if pasa[c] else VEREDICTOS[1] for c in CANDIDATOS_DERIVA}


def deriva_de_veredicto(veredicto: Mapping[str, str]) -> dict[str, bool]:
    """La inversa de ``veredicto_deriva``: lo que va a ``Cfg.deriva``."""
    if set(veredicto) != set(CANDIDATOS_DERIVA) or not all(v in VEREDICTOS for v in veredicto.values()):
        raise ErrorAddendum("el veredicto de la deriva es {«B»: «pasa»|«falla», «AB»: …} (ADD-6)")
    return {c: veredicto[c] == VEREDICTOS[0] for c in CANDIDATOS_DERIVA}


def _commit(x, que: str) -> str:
    if x == PENDIENTE or (isinstance(x, str) and _COMMIT.fullmatch(x)):
        return x
    raise ErrorAddendum(f"{que}: un commit de 40 hexadecimales o «{PENDIENTE}» (ADD-7)")


def addendum_m1(lista, anexo_a2, deriva, recorte, costo, lecturas, commits, *, fecha: str | None = None,
                bateria: Mapping | None = None) -> dict:
    """El contenido de ``addendum_m1.json`` (MC-54, P44; clase documento), con las claves de ``CLAVES``.

    ``lista``: {alias: sha256} (``lista_cerrada``); ``anexo_a2``: {ruta, sha256} o None; ``deriva``: {ruta, sha256,
    pasa: {«B»: bool, «AB»: bool}} o None; ``recorte``: «mod11», «mod23», «pendiente» o None; ``costo``: {ruta, sha256,
    recorte, procesos_por_fase} o None (ADD-12: con su recorte «pendiente», el recorte y el costo del addendum quedan
    «pendiente»); ``lecturas``: ``lecturas_m1``; ``commits``: {«ap», «aph»}, cada uno un commit o «pendiente»;
    ``fecha``: AAAA-MM-DD; ``bateria``: {carpeta (alias de su subcarpeta), resumen: {ruta, sha256}, aprobada: bool} o
    None. Lo que falta queda «pendiente»."""
    if not isinstance(lista, Mapping) or not lista:
        raise ErrorAddendum("la lista cerrada es {ruta por alias: sha256} (ADD-1)")
    for a, s in lista.items():
        _exigir_alias(a)
        if not isinstance(s, str) or not _SHA.fullmatch(s):
            raise ErrorAddendum(f"{a}: la huella es un sha256 de 64 hexadecimales")
    vigente = f"APH/{umbrales.TEXTO_VIGENTE}"
    if lista.get(vigente) != umbrales.SHA_TEXTO_VIGENTE:
        raise ErrorAddendum("la lista cerrada no trae el texto vigente v2.4 con su huella")
    if fecha is not None and not (isinstance(fecha, str) and _FECHA.fullmatch(fecha)):
        raise ErrorAddendum("la fecha del addendum es AAAA-MM-DD")
    if recorte == PENDIENTE:                        # ADD-12: un recorte «pendiente» es un recorte que falta
        recorte = None
    if recorte is not None and not (isinstance(recorte, str) and _RECORTE.fullmatch(recorte)):
        raise ErrorAddendum("el recorte es «mod11», «mod23» o «pendiente» (§4.9)")
    salida_costo: Any = PENDIENTE
    if costo is not None:
        ref_costo = _referencia_archivo(costo, "costo")
        veredicto = costo.get("recorte")
        if veredicto == PENDIENTE:
            # A39: medido, pero alguna fase no cabe ni con 1 proceso (o no se midió): el recorte y el costo quedan
            # «pendiente», y el addendum no habilita ninguna corrida
            if recorte is not None:
                raise ErrorAddendum("con el recorte del costo «pendiente», el del addendum también queda pendiente "
                                    "(A39)")
        else:
            if not (isinstance(veredicto, str) and _RECORTE.fullmatch(veredicto)):
                raise ErrorAddendum("el costo trae su recorte («mod11», «mod23» o «pendiente»)")
            if recorte is not None and recorte != veredicto:
                raise ErrorAddendum("el recorte del addendum no es el del costo medido (§8)")
            salida_costo = {**ref_costo, "veredicto": veredicto,
                            "procesos_por_fase": _procesos_por_fase(costo.get("procesos_por_fase"))}
            recorte = veredicto
    salida_deriva: dict = {"parametros": [dict(p) for p in lecturas["parametros_s6"]], "estado": PENDIENTE}
    if deriva is not None:
        salida_deriva = {**_referencia_archivo(deriva, "deriva"), "veredicto": veredicto_deriva(deriva["pasa"]),
                         "medicion": "por referencia a deriva_s6.json (P44)", "parametros": salida_deriva["parametros"]}
    if not isinstance(commits, Mapping) or set(commits) != {"ap", "aph"}:
        raise ErrorAddendum("los commits de M1 son {«ap», «aph»} (ADD-7)")
    salida_bateria: Any = PENDIENTE
    if bateria is not None:
        if not isinstance(bateria.get("aprobada"), bool):
            raise ErrorAddendum("la batería trae «aprobada» (bool)")
        salida_bateria = {"carpeta": carpeta_bateria(bateria.get("carpeta")),
                          "resumen": _referencia_archivo(bateria.get("resumen"), "bateria.resumen"),
                          "aprobada": bateria["aprobada"]}
    anteriores = [{"ruta": f"APH/{rel}", "sha256": lista[f"APH/{rel}"]} for rel in (TEXTO_V2_3, TEXTO_V2_2, umbrales.TEXTO_M0)
                  if f"APH/{rel}" in lista]
    contenido = {
        "esquema": ESQUEMA, "fecha": fecha,
        "texto_vigente": {"ruta": vigente, "sha256": umbrales.SHA_TEXTO_VIGENTE},
        "textos_anteriores": anteriores,
        "umbrales": {"ruta": f"APH/{umbrales.JSON_M0}", "sha256": lista.get(f"APH/{umbrales.JSON_M0}")},
        "lista_cerrada": dict(sorted(lista.items())),
        "anexo_a2": PENDIENTE if anexo_a2 is None else _referencia_archivo(anexo_a2, "anexo_a2"),
        "deriva": salida_deriva,
        "recorte": PENDIENTE if recorte is None else recorte,
        "costo": salida_costo,
        "lecturas": [dict(x) for x in lecturas["lecturas"]],
        "lecturas_diseno": [dict(x) for x in lecturas["lecturas_diseno"]],
        "decisiones": [dict(x) for x in lecturas["decisiones"]],
        "diferencias": [dict(x) for x in lecturas["diferencias"]],
        "preguntas_abiertas": [dict(x) for x in lecturas["preguntas_abiertas"]],
        "preguntas_respondidas": [dict(x) for x in lecturas["preguntas_respondidas"]],
        "acuerdos": [dict(x) for x in lecturas["acuerdos"]],
        "declaracion_c4_reloj": dict(DECLARACION_C4),
        "enmienda_operativa": dict(ENMIENDA_OPERATIVA),
        "fuentes": [{"ruta": a, "sha256": s} for a, s in sorted(lecturas["fuentes"].items())],
        "commits": {"ap": _commit(commits["ap"], "commits.ap"), "aph": _commit(commits["aph"], "commits.aph")},
        "bateria": salida_bateria,
    }
    return {k: contenido[k] for k in CLAVES}


def _validar_declaraciones(contenido) -> None:
    """D65: las dos declaraciones exactas, con post_hoc booleano True (no 1 ni 1.0). Sin E/S."""
    if not isinstance(contenido, Mapping) or contenido.get("esquema") != ESQUEMA:
        raise ErrorAddendum("el addendum no tiene el esquema vigente (ADD-10, D65)")
    if contenido.get("declaracion_c4_reloj") != dict(DECLARACION_C4):
        raise ErrorAddendum("la declaración C4 no es exactamente la adoptada (D65; §10)")
    enmienda = contenido.get("enmienda_operativa")
    if not isinstance(enmienda, Mapping) or enmienda.get("post_hoc") is not True \
            or enmienda != dict(ENMIENDA_OPERATIVA):
        raise ErrorAddendum("falta la Enmienda 3 operativa exacta con post_hoc booleano true (D65; §10)")


def _declaraciones_md(contenido: Mapping) -> list[str]:
    """Bloque canónico de las dos declaraciones, común al formateador y al publicador."""
    _validar_declaraciones(contenido)
    lineas = ["## Declaración sobre el C4 de RELOJ (§10; P122)", ""]
    lineas += [f"- {v}" for v in DECLARACION_C4.values()]
    lineas += ["", "## Enmienda operativa del producto (D65; §10)", ""]
    lineas += [f"- {k}: {str(v).lower() if isinstance(v, bool) else v}"
               for k, v in ENMIENDA_OPERATIVA.items()]
    return lineas


def _validar_publicacion(nombre: str, datos: bytes) -> None:
    """Los addendum_m1.json/.md (también .gz) deben llevar ambas declaraciones exactas antes de publicarse."""
    base = PurePosixPath(nombre).name.casefold()
    if base.endswith(".gz"):
        base = base[:-len(".gz")]
        if base not in (NOMBRE_JSON, NOMBRE_MD):
            return
        try:
            datos = gzip.decompress(datos)
        except (OSError, EOFError) as e:
            raise ErrorAddendum("el addendum comprimido no es válido") from e
    if base not in (NOMBRE_JSON, NOMBRE_MD):
        return
    try:
        texto = datos.decode("utf-8")
        if base == NOMBRE_JSON:
            def objeto(pares):
                d = {}
                for clave, valor in pares:
                    if clave in d:
                        raise ErrorAddendum("el addendum JSON repite una clave")
                    d[clave] = valor
                return d
            _validar_declaraciones(json.loads(texto, object_pairs_hook=objeto))
        else:
            inicio = "## Declaración sobre el C4 de RELOJ (§10; P122)"
            fin = "## Lista cerrada de huellas (§10, M1)"
            if texto.count(inicio) != 1 or texto.count(fin) != 1:
                raise ErrorAddendum("el addendum Markdown no trae las declaraciones una sola vez")
            bloque = texto[texto.index(inicio):texto.index(fin)]
            esperado = "\n".join(_declaraciones_md({"esquema": ESQUEMA,
                "declaracion_c4_reloj": dict(DECLARACION_C4), "enmienda_operativa": dict(ENMIENDA_OPERATIVA)})) + "\n\n"
            if bloque != esperado:
                raise ErrorAddendum("las declaraciones del addendum Markdown no son exactamente las adoptadas")
    except (UnicodeError, json.JSONDecodeError) as e:
        raise ErrorAddendum("el addendum no es un documento válido") from e


def _bloque(texto: str) -> list[str]:
    return [f"  {ln}" if i else ln for i, ln in enumerate(texto.splitlines())]


def addendum_md(contenido: Mapping) -> str:
    """El ``.md`` del addendum: lo mismo que el JSON, en Markdown (clase documento; títulos sin rangos fijos)."""
    _validar_declaraciones(contenido)
    c = contenido
    ln = ["# Addendum de M1 del producto meteorológico combinado ERA5-Land + DMC", "",
          f"Texto vigente: `{c['texto_vigente']['ruta']}`, sha256 {c['texto_vigente']['sha256']}.",
          f"Fecha: {c['fecha'] or PENDIENTE}. Commits de M1: AP {c['commits']['ap']}; APH {c['commits']['aph']}.", ""]
    for t in c["textos_anteriores"]:
        ln.append(f"- Texto anterior: `{t['ruta']}` {t['sha256']}")
    ln += ["", *_declaraciones_md(c)]
    ln += ["", "## Lista cerrada de huellas (§10, M1)", ""]
    ln += [f"- `{a}` {s}" for a, s in c["lista_cerrada"].items()]
    ln += ["", "## Anexo A2, compuerta de deriva, recorte y costo (P44)", ""]
    a2 = c["anexo_a2"]
    ln.append(f"- Anexo A2: {PENDIENTE}" if a2 == PENDIENTE else f"- Anexo A2: `{a2['ruta']}` {a2['sha256']}")
    d = c["deriva"]
    if "veredicto" in d:
        ln.append(f"- Compuerta de deriva: `{d['ruta']}` {d['sha256']}; B {d['veredicto']['B']}, AB "
                  f"{d['veredicto']['AB']} ({d['medicion']}).")
    else:
        ln.append(f"- Compuerta de deriva: {PENDIENTE}.")
    co = c["costo"]
    ln.append(f"- Recorte: {c['recorte']}.")
    if co == PENDIENTE:
        ln.append(f"- Costo: {PENDIENTE}.")
    else:                                           # ADD-12: los procesos por fase, con la declaración de D59
        fases = "; ".join(f"{compuerta}: " + ", ".join(f"{fase} {n}" for fase, n in por_fase.items())
                          for compuerta, por_fase in co["procesos_por_fase"].items())
        ln.append(f"- Costo: `{co['ruta']}` {co['sha256']}; {co['veredicto']}; procesos por fase: {fases}.")
        ln.append(f"  - {DECLARACION_D59}")
    b = c["bateria"]
    ln.append(f"- Batería: {PENDIENTE}." if b == PENDIENTE else
              f"- Batería: `{b['carpeta']}`; resumen `{b['resumen']['ruta']}` {b['resumen']['sha256']}; "
              f"{'aprobada' if b['aprobada'] else 'no aprobada'}.")
    ln += ["", "## Parámetros de S6, fijados antes de correrla (D15)", ""]
    for p in d["parametros"]:
        ln += _bloque(f"- {p['texto']}")
    ln += ["", "## Lecturas de implementación (§0, regla 9, del diseño)", ""]
    modulo = None
    for x in c["lecturas"]:
        if x["modulo"] != modulo:
            modulo = x["modulo"]
            ln += ["", f"### `{modulo}`", ""]
        ln += _bloque(f"- {x['texto']}")
    ln += ["", "## Lecturas del diseño (§7; D5)", ""]
    for x in c["lecturas_diseno"]:
        ln += _bloque(f"- {x['texto']}")
    ln += ["", "## Decisiones del autor", ""]
    for x in c["decisiones"]:
        ln.append(f"- {x['texto']} (`{x['fuente']}`)")
    ln += ["", "## Diferencias con el diseño", ""]
    seccion = None
    for x in c["diferencias"]:
        if x["seccion"] != seccion:
            seccion = x["seccion"]
            ln += ["", f"### {seccion}", ""]
        ln += _bloque(f"- {x['texto']}")
    ln += ["", "## Preguntas abiertas para el autor (rige lo que dice cada una)", ""]
    for x in c["preguntas_abiertas"]:
        ln += _bloque(f"- {x['texto']}")
    ln += ["", "## Preguntas ya respondidas, con su decisión", ""]
    for x in c["preguntas_respondidas"]:
        ln += _bloque(f"- ({x['decision']}) {x['texto']}")
    ln += ["", "## Acuerdos de interfaces", ""]
    for x in c["acuerdos"]:
        ln += _bloque(f"- {x['texto']} ({x['seccion']}{'; revisado' if x.get('revisado') else ''})")
    ln += ["", "## Fuentes de las lecturas", ""]
    ln += [f"- `{f['ruta']}` {f['sha256']}" for f in c["fuentes"]]
    return "\n".join(ln) + "\n"
