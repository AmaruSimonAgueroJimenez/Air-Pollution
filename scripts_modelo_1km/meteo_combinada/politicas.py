"""Reglas ``measurements``, ``quality`` y ``coordinates`` (§2.2, §2.3, §2.5), tramos y políticas de lectura y efectiva.

Registro de C5, política y ``artefactos_evaluados`` de RELOJ; lista K2 por código (MC-19); textos ``source``; JSON
con números de Python (ida y vuelta exacta, S2).

Qué hace cada parte:
- **C5** (§2.1, precondición 1): ``leer_registro_c5`` y ``leer_politica_reloj`` leen el registro, la política y
  ``artefactos_evaluados`` y exigen sus sha256 (``ErrorC5`` si falta algo o no coincide); ``comprobar_c5`` lista lo que
  invalida la política (``post_hoc``, errata sin confirmar, citas y estructura); ``declaracion_c5`` da lo que el
  registro de M3-4 declara de un C5 válido (D23). Sólo leen: nunca escriben.
- **K2** (MC-19): ``coordenadas_inconsistentes`` toma, por código, sólo esa clave del informe publicado de RELOJ.
- **Tramos y reglas**: ``tramos_de_lectura`` parte los tramos de RELOJ (años G y meses sin artefacto evaluado);
  ``politicas_de_lectura`` arma, por tramo, la política de §2.5 que recibe ``cargar_dmc``; ``politicas_efectivas`` la
  parte en los meses de K4 y deja sin coordenadas lo anterior al último traslado (MC-53).
- **Uso**: ``politicas_que_cruzan`` (las de un mes de etiqueta), ``regla_reloj`` y ``validar_reglas`` (el envoltorio de
  RELOJ §7.5: una regla rechazada no se entrega), ``tramos_de_politicas`` (ids «<RELOJ>/<k>») y ``tramos_marca_14``
  (los tramos de la marca 14, D24; la marca la aplica ``qc_dmc_meteo``, I12).
- **JSON**: ``a_json`` y ``de_json``, con tipos exactos de Python.

Dueño: I6 (ola 2; en la ola 3, D23 a D26 de ``APH/auditoria/20261023/meteo_combinada/m1/decisiones_autor_m1_20261026.md``,
decisiones [delegada]).

Lecturas propias (POL-n), para el addendum de M1:
- POL-1. **Registro de C5** (§2.1; RELOJ, Enmienda 2, E2-4; SIN-5 y H14). Es
  ``APH/auditoria/<AAAAMMDD>/meteo_combinada/registro_politica_reloj.json``. La ruta debe estar dentro del APH hermano
  de ``ap`` (el APH real si ``ap`` es el AP real; «<raíz>/APH» si ``ap`` es un «<raíz>/AP» sintético, fuera de AP y de
  APH reales: la anidación de ``entorno``, ENT-6), con exactamente esa forma y una fecha que exista. Una copia fuera de
  APH (en AP, el repositorio público, o en «<otra>/auditoria/…») se rechaza: no se registra como de APH. El
  registro trae sólo rutas, huellas y commit: ``schema`` («meteo-combinada-registro-politica-reloj/1»),
  ``politica_ruta`` y ``artefactos_ruta`` (por alias, exactamente las de publicación de RELOJ §7.1:
  ``AP/config/meteorologia/reloj_dmc/v1/…``), ``sha256_politica``, ``sha256_artefactos``, ``commit_c5`` (40
  hexadecimales) y ``errata_confirmada``: null, o ``{"ruta", "sha256", "commit"}`` de la errata que corrige la política.
  Ninguna clave más. Las banderas ``post_hoc``, ``errata_post_c4`` y ``ajuste_documental`` son de la política, no del
  registro: ``leer_registro_c5`` recibe ``ap`` (obligatorio: cambio incompatible con §3, ver «Firmas») y lee la
  política sólo para tomar las dos primeras, después de comprobar su sha256. En memoria,
  ``RegistroReloj.errata_confirmada`` es un ``tipos.ErrataConfirmada`` (ruta, sha256 y commit; TIP-13, cambio de
  interfaz del coordinador al cerrar la ola 2).
  **El formato lo fija M1** (D26): es éste, y el ejecutable del C5 de RELOJ (RELOJ §10, «C5, publicación»; Enmienda 2,
  E2-4) debe escribirlo así: un objeto JSON en UTF-8, sin claves repetidas, sin NaN ni Infinity, con exactamente esas
  siete claves y estos valores: ``schema`` el texto de arriba; ``politica_ruta`` = ``RUTA_POLITICA_AP`` y
  ``artefactos_ruta`` = ``RUTA_ARTEFACTOS_AP`` (las de publicación, por alias); ``sha256_politica`` y ``sha256_artefactos`` en 64 hexadecimales en minúscula (de los bytes publicados; del ``.gz``
  tal cual, no del JSON expandido); ``commit_c5`` en 40 hexadecimales en minúscula; ``errata_confirmada`` null, o
  ``{"ruta", "sha256", "commit"}`` con la ruta por alias de AP o APH, sin espacios ni datos privados.
  **Política corregida por una errata** (D26, P15; §2.1, «o la corregida por una errata confirmada, con su sha256 igual
  al registrado»): reemplaza a la publicada **en la misma ruta** de RELOJ §7.1 (que es también la que lee por omisión
  ``validar_regla_reloj_dmc``), con su nueva sha256 en ``sha256_politica`` y la errata en ``errata_confirmada``; si la
  corrida corregida republica ``artefactos_evaluados``, va también en su ruta, con su sha256. La original se archiva con
  un sufijo, junto a la publicada o donde lo fije RELOJ: M1 no la lee ni la cita (la errata de RELOJ §10 publica las
  dos políticas y su diferencia). Una política corregida en otra ruta, o un registro que cite la archivada, se rechaza
  (``ErrorC5``: no es la ruta de publicación). El registro que recibe M3-4 es el que cita la sha256 de la política
  publicada: uno anterior a la errata ya no calza y ``leer_registro_c5`` lo rechaza.
- POL-2. **C5 válido** (§2.1, precondición 1; S2). ``leer_registro_c5`` y ``leer_politica_reloj`` lanzan ``ErrorC5``
  sin registro, con una forma o una ruta distintas, o con una sha256 que no coincide (política o artefactos).
  ``comprobar_c5`` devuelve la lista de fallas: ``post_hoc = true``; ``errata_post_c4 = true`` sin
  ``errata_confirmada`` (y una errata citada en una política sin ``errata_post_c4``); banderas del registro distintas de
  las de la política; esquema y claves de la política; la cita de ``artefactos_evaluados`` (ruta y sha256 del
  registro), la del informe, la huella del adaptador fijado y la de la tabla de cambios de hora de RELOJ (sin ella,
  ``validar_regla_reloj_dmc`` rechazaría todas las reglas y la red quedaría sin regla en silencio); y la estructura de
  ``politicas_reloj`` (claves, intervalo
  externo igual al de ``clock``, sin solapes, ``source`` de RELOJ de la misma estación, estación «confirmada» con el
  veredicto del tramo y marcas bien formadas). «Errata confirmada» quiere decir citada así en el registro; que su commit
  sea antecesor de ``origin/main`` y que el archivo tenga esa sha256 lo comprueba ``verificar_meteo_combinada`` con git
  (§10), no este módulo, que no lee APH fuera del registro. ``ajuste_documental`` debe ser booleano; ``true`` (RELOJ
  §4.5: un documento D1 obtenido después de C4 deja sin confirmar lo que contradice, «ese mismo efecto y nada más»)
  **se acepta** (D23, P13): RELOJ no la trata como posterior al hecho ni como errata, y sólo quita confirmaciones. Se
  declara en el registro de M3-4 con ``declaracion_c5`` (POL-15). Antes de D23 era una falla (la lectura más estricta
  mientras el autor no decidía).
- POL-3. **K2** (MC-19, §1.9). La lista sale del ``informe_reloj_dmc.json`` publicado, con la sha256 que cita la
  política (que a su vez se comprueba contra el registro): se parsea en memoria sólo para tomar la clave
  ``coordenadas_inconsistentes`` (lista de códigos de 6 dígitos sin repetir); nada más del informe se devuelve, se
  guarda ni se imprime. No se lee ``pixeles_dmc.parquet``: no está publicado ni citado por la política.
- POL-4. **Tramos de lectura** (§2.5, «Tramos»; §2.2, «el intervalo se parte por año»). Cada tramo de RELOJ se parte
  (a) **la literal de §2.2 (D25)**: el 1 de enero a las 00:00 (etiqueta, MC-58) de cada año con marcas G-HR o
  G-viento y el del año siguiente, aunque dos años seguidos tengan las mismas marcas (así el año marcado queda en su
  propia pieza); un año sin marcas entre años sin marcas no se corta. Sólo cuentan los cortes dentro del tramo
  (después de su primera etiqueta y hasta la última, inclusive). Antes de D25 se juntaban en una pieza los años seguidos
  con las mismas marcas; con D24 eso cambiaría qué horas llevan la marca 14 (P14). (b) Para no cubrir ningún mes de
  etiqueta sin artefacto evaluado (``meses_con_artefacto``, pares (año, mes) de etiqueta): una pieza termina a las 23:00
  del último día de su último mes y la siguiente empieza a las 00:00 del primero. Los límites de RELOJ (primera y última
  etiqueta con dato) se conservan. k cuenta las piezas de cada tramo de RELOJ en orden (id «<RELOJ>/<k>», §2.1 del
  diseño). ``politicas_de_lectura`` rechaza un tramo que contenga uno de esos cortes sin partirse.
- POL-5. **Coordenadas de lectura** (§2.5, K1-K3; A7). Confirmadas en todo el registro salvo: sin latitud o longitud
  legibles («sin_coordenadas»), K3 fallida («k3») o en la lista K2 («k2»); el motivo sigue ese orden de precedencia y
  va al final de ``source`` (« motivo=<m>»). ``k2`` es un conjunto (o iterable) de códigos de 6 dígitos: un texto
  («900701») o un objeto se rechazan, porque darían el conjunto de sus caracteres o de sus claves y K2 se ignoraría sin
  aviso. Las estaciones con K3 fallida reciben igual sus políticas (para Q2, §2.7). Latitud y longitud son las de
  ``InfoEstacion`` (el catálogo leído como RELOJ §3.3), en float de Python; sin coordenadas legibles la regla va sin
  ``latitude`` ni ``longitude`` (el JSON no admite NaN).
- POL-6. **Mediciones** (§2.2). Ts, Td, ``relative_humidity``, ``wind_speed_instant``, ``wind_direction_instant``, QFE
  y QFF instantáneas con intervalo 0; RR06 ``sum`` con 360; QNH sin regla. G-HR deja ``verified = false`` en Td y HR
  (motivo «g_hr»), G-viento en FF y DD («g_viento»), por año de etiqueta; «posible media horaria» en todas las
  variables, RR06 y QFF incluidas, en todo el registro («posible_media_horaria», que prevalece). Las variables que lista
  RELOJ por año deben ser pares completos (Td y HR; FF y DD): si no, la política está mal formada. Un año sin marca
  (también uno que G-HR o G-viento no pudieron evaluar, RELOJ §6) queda verificado: §2.2 quita la verificación sólo con
  la marca, y RELOJ lista sólo los años marcados (``reloj_no_verificado``).
- POL-7. **Calidad** (§2.3). DD con ``int`` 0 y 360 (§2.1, «`int` 0 y 360»; §2.3 los escribe sin decimales); los demás
  límites en float de Python. QFF con ``QQFF_MIN``/``QQFF_MAX`` (la presión; ``QFF_MIN``/``QFF_MAX`` son la rapidez,
  UMB-11). QFE de float(p_std(z_s)) + ``QQFE_BAJO`` a float(p_std(z_s)) + ``QQFE_ALTO`` (``numerico.p_std``), sólo con
  la z_s del catálogo (K3 pasa y ``z_s_fuente`` = «catalogo»); si no, QFE queda sin regla (§2.3 y MC-11). RR06 y QNH sin
  regla ``quality``.
- POL-8. ``sha_protocolo`` debe ser el del texto vigente (``Umbrales.sha256_texto_vigente``, b4175f78…, el v2.3), y
  ``sha_catalogo`` un sha256 en minúscula.
- POL-9. **Política efectiva** (MC-53; acuerdo A5). Los meses de corte son los de todos los quiebres de K4, más el
  último traslado y el último barómetro. El corte del mes k va en la etiqueta L_k = u_k + ``fixed_offset_minutes`` del
  ``clock`` del tramo, con u_k la primera hora UTC del mes k; un tramo se parte si valid_from < L_k ≤ valid_to (la pieza
  anterior termina en L_k − 1 h). Las piezas cuyo valid_to es anterior, en UTC, a u_k del último traslado quedan con
  ``coordinates.verified = false`` y motivo «traslado» (las que ya estaban sin confirmar conservan su motivo). Las reglas
  internas toman el intervalo de su pieza; ``clock`` sigue copiado sin cambios. La marca 16 no toca la política (es del
  envoltorio).
- POL-10. **Ids de tramo.** ``tramos_de_politicas`` los deriva de ``clock.source`` («tramo=<RELOJ>») sobre la lista
  completa de una estación, en orden de ``valid_from``: nunca sobre un subconjunto filtrado, que los renumeraría. Vale
  para la de lectura y para la efectiva.
- POL-11. **Validación de uso** (§2.1, paso 1; RELOJ §7.5). ``regla_reloj`` rehace la regla publicada de RELOJ
  (``station_code`` y el intervalo de ``clock``, que en RELOJ es el externo) y ``validar_reglas`` la pasa a
  ``validar_regla_reloj_dmc`` una vez por tramo de RELOJ. Un rechazo (``ValueError``) quita todas las piezas de ese
  tramo: no se entregan a ``cargar_dmc``. Devuelve los ids de RELOJ rechazados. Sólo se captura ``ValueError`` (MC-57).
- POL-12. **JSON** (§2.1, «Números de Python»). ``a_json`` es el JSON canónico (claves ordenadas, «,» y «:», UTF-8, sin
  NaN) y exige tipos exactos ``dict``, ``list``, ``str``, ``bool``, ``int``, ``float`` y None: rechaza numpy (también
  ``np.float64``, que es subclase de float), tuplas y no finitos. ``de_json`` lee sin claves repetidas ni NaN. Ida y
  vuelta exacta: ``de_json(a_json(p)) == p``, con los mismos tipos.
- POL-13. ``politicas_que_cruzan``: las políticas de la estación cuyo intervalo externo corta el mes de etiqueta
  [AAAA-MM-01T00:00:00, último día T23:00:00], en el orden recibido.
- POL-14. **Tramos de la marca 14** (D24, P14; §2.4, «|mediana(QFE − p_F)| > 8 hPa en el tramo»; §2.1, paso 4, «con
  los tramos ya cortados»). Son los de la política efectiva: ``tramos_marca_14(efectivas, codigo)`` es
  ``tramos_de_politicas`` sobre la lista completa de ``politicas_efectivas`` (POL-10), sólo los de ``codigo``, en orden
  de ``valid_from``. Quedan partidos por todos los quiebres de K4 (también los de T2a sin T2b), por los años G (POL-4,
  D25) y por los meses sin artefacto evaluado. Las horas de un tramo son las de etiqueta (``timestamp_source``) dentro
  de su intervalo inclusivo, la regla con que ``cargar_dmc`` elige la política (A6). La marca la aplica
  ``qc_dmc_meteo.marca_14`` (I12): este módulo sólo da los tramos y no ve valores.
- POL-15. **Declaración de C5 en el registro de M3-4** (D23 y D26). ``declaracion_c5(registro, politica)`` da, de un C5
  válido (``comprobar_c5`` vacío; si no, ``ErrorC5`` con las fallas), sólo rutas, huellas, commit y banderas:
  ``registro`` (el alias del registro de C5), ``sha256_politica``, ``sha256_artefactos``, ``commit_c5``, ``post_hoc``,
  ``errata_post_c4``, ``ajuste_documental`` y ``errata_confirmada`` (null u objeto). Ningún número de datos. La escribe
  ``orquestacion`` en el registro de M3-4 (I20); este módulo no escribe.

Firmas respecto de §3 del diseño (para el anexo de firmas que se regenera al cerrar M1):
- **Incompatibles** (una llamada con la firma de §3 lanza ``TypeError``; I12, I20 e I22 deben pasar estos
  argumentos): ``leer_registro_c5(ruta, *, ap)`` (§3: ``leer_registro_c5(ruta)``; ``ap`` hace falta para leer las
  banderas de la política y para ubicar el APH del registro, POL-1) y ``tramos_de_lectura(politica_reloj, codigo,
  meses_con_artefacto, marcas_g, *, info, k2)`` (§3 no trae ``info`` ni ``k2``: sin ellos no hay coordenadas de K1-K3
  ni de K2, POL-5). No llevan valor por omisión: uno haría pasar en silencio una estación de K2 como confirmada.
- **Más estricta:** ``leer_politica_reloj`` devuelve (política, {sha256 del artefacto: código}); §3 dice sólo
  ``tuple[dict, dict]``.
- **Aditivos:** ``ErrorC5``; el ``motivo=`` de sólo palabra clave, con None por omisión, de ``source_coordenadas``;
  ``marcas_g``, ``media_horaria``, ``tramos_de_politicas``, ``regla_reloj``, ``validar_reglas`` y ``de_json``; en la
  ola 3, ``tramos_marca_14`` (POL-14) y ``declaracion_c5`` (POL-15); y las constantes públicas.
Depende de: tipos, constantes, umbrales, numerico, entorno, fijados.
"""
from __future__ import annotations

import copy
import gzip
import json
import math
import os
import re
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, NamedTuple

from meteo_combinada import constantes, entorno, fijados, numerico, tipos
from meteo_combinada.tipos import FuenteZs, RegistroReloj, ResultadoK4, TramoPolitica, VariableDMC


class ErrorC5(ValueError):
    """El registro de C5, la política o ``artefactos_evaluados`` faltan, no tienen la forma o no tienen la huella."""


# ---------------------------------------------------------------------------
# Lo publicado por RELOJ (copiado de reloj_dmc.politica; test_politicas lo compara)
# ---------------------------------------------------------------------------
ESQUEMA_POLITICA_RELOJ = "dmc-reloj-politica/1"
CLAVES_POLITICA_RELOJ = ("schema", "post_hoc", "errata_post_c4", "ajuste_documental", "protocolo", "configuracion",
                         "informe", "artefactos_evaluados", "adaptador_sha256", "interprete", "transiciones_sha256",
                         "politicas_reloj", "estaciones")
CLAVES_TRAMO_RELOJ = ("station_code", "valid_from", "valid_to", "clock")
CLAVES_CLOCK_RELOJ = ("verified", "source", "valid_from", "valid_to", "timestamp_semantics", "fixed_offset_minutes")
PATRON_SOURCE_RELOJ = (r"^reloj-dmc/v1 informe=(\S+) sha256=([0-9a-f]{64}) estacion=(\d{6}) "
                       r"tramo=(\d+\.\d+) protocolo=([0-9a-f]{64})$")
RUTA_PUBLICACION_RELOJ = "config/meteorologia/reloj_dmc/v1"
ARCHIVO_POLITICA_RELOJ = "politica_reloj_dmc.json"
ARCHIVO_INFORME_RELOJ = "informe_reloj_dmc.json"
ARCHIVO_ARTEFACTOS_RELOJ = "artefactos_evaluados.json.gz"
RUTA_INFORME_RELOJ = f"{RUTA_PUBLICACION_RELOJ}/{ARCHIVO_INFORME_RELOJ}"          # como la cita la política
RUTA_ARTEFACTOS_RELOJ = f"{RUTA_PUBLICACION_RELOJ}/{ARCHIVO_ARTEFACTOS_RELOJ}"
VEREDICTO_CONFIRMADA = "confirmada"
CLAVE_TRAMOS_ESTACION = "tramos"
CLAVES_MARCAS_RELOJ = ("posible_media_horaria", "reloj_no_verificado")
CLAVE_K2 = "coordenadas_inconsistentes"                                           # clave del informe (MC-19)
# reloj_dmc.tablas.SHA_ANEXO_A: la tabla de cambios de hora que exige validar_regla_reloj_dmc (POL-2).
SHA_TRANSICIONES_RELOJ = "8ea58b788ad6d8e236c5dae5f749a7fc7fe837cb2e34cb947e9904cf8f345a33"

# ---------------------------------------------------------------------------
# Registro de C5 (POL-1)
# ---------------------------------------------------------------------------
ESQUEMA_REGISTRO_C5 = "meteo-combinada-registro-politica-reloj/1"
CLAVES_REGISTRO_C5 = ("schema", "politica_ruta", "sha256_politica", "artefactos_ruta", "sha256_artefactos",
                      "commit_c5", "errata_confirmada")
CLAVES_ERRATA = ("ruta", "sha256", "commit")
ARCHIVO_REGISTRO_C5 = "registro_politica_reloj.json"
_COLA_REGISTRO = ("auditoria", None, "meteo_combinada", ARCHIVO_REGISTRO_C5)    # None: la fecha de C5
ALIAS_AP, ALIAS_APH = entorno.ALIAS["ap"], entorno.ALIAS["aph"]                 # «AP» y «APH»
RUTA_POLITICA_AP = f"{ALIAS_AP}/{RUTA_PUBLICACION_RELOJ}/{ARCHIVO_POLITICA_RELOJ}"  # alias
RUTA_ARTEFACTOS_AP = f"{ALIAS_AP}/{RUTA_PUBLICACION_RELOJ}/{ARCHIVO_ARTEFACTOS_RELOJ}"
PREFIJO_AP = f"{ALIAS_AP}/"

# ---------------------------------------------------------------------------
# Reglas de §2.2 y §2.3
# ---------------------------------------------------------------------------
PREFIJO_SOURCE = "meteo-combinada/v1"
INSTANTANEA = "instantaneous"
SUMA = "sum"
METODO_CALIDAD = "documented_numeric_checks"
TS, TD, HR, FF, DD, QFE, QFF, RR06 = (VariableDMC.TS.value, VariableDMC.TD.value, VariableDMC.HR.value,
                                      VariableDMC.FF.value, VariableDMC.DD.value, VariableDMC.QFE.value,
                                      VariableDMC.QFF.value, VariableDMC.RR06.value)
# §2.2: (statistic, constante del intervalo); QNH no recibe regla.
MEDICIONES: Mapping[str, tuple[str, str]] = {
    TS: (INSTANTANEA, "MED_INTERVALO_TS_TD_HR"), TD: (INSTANTANEA, "MED_INTERVALO_TS_TD_HR"),
    HR: (INSTANTANEA, "MED_INTERVALO_TS_TD_HR"), FF: (INSTANTANEA, "MED_INTERVALO_VIENTO"),
    DD: (INSTANTANEA, "MED_INTERVALO_VIENTO"), QFE: (INSTANTANEA, "MED_INTERVALO_QFE"),
    QFF: (INSTANTANEA, "MED_INTERVALO_QFF"), RR06: (SUMA, "MED_INTERVALO_RR06"),
}
# §2.3: (unidad normalizada, id del mínimo, id del máximo, en float). QFE va aparte (p_std(z_s)); RR06 y QNH sin regla.
CALIDAD: Mapping[str, tuple[str, str, str, bool]] = {
    TS: ("degC", "QTS_MIN", "QTS_MAX", True), TD: ("degC", "QTD_MIN", "QTD_MAX", True),
    HR: ("%", "QHR_MIN", "QHR_MAX", True), FF: ("m/s", "QFF_MIN", "QFF_MAX", True),
    DD: ("degree", "QDD_MIN", "QDD_MAX", False),          # POL-7: int 0 y 360
    QFF: ("hPa", "QQFF_MIN", "QQFF_MAX", True),           # POL-7: la presión QFF, no la rapidez (UMB-11)
}
UNIDAD_QFE = "hPa"
ORDEN_CALIDAD = (TS, TD, HR, FF, DD, QFE, QFF)
# §2.2: variables que deja sin verificar cada marca G de RELOJ (VARIABLES_MARCA de reloj_dmc.orquestacion).
VARIABLES_G = {"g_hr": (TD, HR), "g_viento": (FF, DD)}
MOTIVO_MEDIA_HORARIA = "posible_media_horaria"
MOTIVO_SIN_COORDENADAS = "sin_coordenadas"
MOTIVO_K3 = "k3"
MOTIVO_K2 = "k2"
MOTIVO_TRASLADO = "traslado"

UNA_HORA = timedelta(hours=1)
_EPOCA = datetime.fromisoformat(tipos.EPOCA_H).replace(tzinfo=None)      # mes2000 = 0
_SHA = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_FECHA = re.compile(r"\d{8}")
_ETIQUETA = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:00:00")
_TOKEN = re.compile(r"[a-z0-9_]+")
_PATRON_SOURCE_RELOJ = re.compile(PATRON_SOURCE_RELOJ)
_COORDENADAS = re.compile(rf"{re.escape(PREFIJO_SOURCE)} coordenadas=catalogo sha256=([0-9a-f]{{64}}) "
                          r"continuidad=supuesta estacion=(\d{6}) protocolo=([0-9a-f]{64})(?: motivo=([a-z0-9_]+))?")
_TIPOS_JSON = (dict, list, str, bool, int, float, type(None))


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
class _Source(NamedTuple):
    informe: str
    sha256: str
    estacion: str
    tramo: str
    protocolo: str


class _Pieza(NamedTuple):
    codigo: str
    tramo: str
    desde: datetime
    hasta: datetime
    indice: int


def _partes_source(texto: Any) -> _Source | None:
    """Los cinco grupos de un ``source`` de RELOJ, o None si no cumple el patrón."""
    m = _PATRON_SOURCE_RELOJ.fullmatch(texto) if isinstance(texto, str) else None
    return None if m is None else _Source(*m.groups())


def _pares_sin_repetir(pares: list[tuple[str, Any]]) -> dict:
    claves = [k for k, _ in pares]
    if len(set(claves)) != len(claves):
        raise ValueError(f"claves repetidas en el JSON: {sorted({k for k in claves if claves.count(k) > 1})}")
    return dict(pares)


def _sin_constantes(texto: str):
    raise ValueError(f"constante no admitida en el JSON: {texto}")


def _leer_json(datos: bytes) -> Any:
    """JSON en UTF-8 sin claves repetidas ni NaN/Infinity (como ``reloj_dmc.politica._leer_json``)."""
    return json.loads(datos.decode("utf-8"), object_pairs_hook=_pares_sin_repetir, parse_constant=_sin_constantes)


def _es_sha(x: Any) -> bool:
    return isinstance(x, str) and _SHA.fullmatch(x) is not None


def _exigir_sha(x: Any, nombre: str) -> str:
    if not _es_sha(x):
        raise ValueError(f"{nombre} no es un sha256 de 64 hexadecimales en minúscula")
    return x


def _exigir_codigo(codigo: Any) -> str:
    if not isinstance(codigo, str) or tipos.PATRON_CODIGO.fullmatch(codigo) is None:
        raise ValueError(f"código DMC inválido: {codigo!r}")
    return codigo


def _etiqueta(texto: Any) -> datetime:
    """Etiqueta ingenua «AAAA-MM-DDTHH:00:00» (hora exacta)."""
    if not isinstance(texto, str) or _ETIQUETA.fullmatch(texto) is None:
        raise ValueError(f"etiqueta fuera del formato «AAAA-MM-DDTHH:00:00»: {texto!r}")
    return datetime.fromisoformat(texto)


def _texto(d: datetime) -> str:
    return d.isoformat(timespec="seconds")


def _indice_mes(anio: int, mes: int) -> int:
    return anio * 12 + (mes - 1)


def _mes_de_indice(i: int) -> tuple[int, int]:
    return i // 12, i % 12 + 1


def _inicio_mes(anio: int, mes: int) -> datetime:
    return datetime(anio, mes, 1)


def _ultima_hora_mes(anio: int, mes: int) -> datetime:
    return _inicio_mes(*_mes_de_indice(_indice_mes(anio, mes) + 1)) - UNA_HORA


def _utc_de_mes2000(k: int) -> datetime:
    """Primera hora UTC (ingenua) del mes2000 k."""
    if isinstance(k, bool) or not isinstance(k, int):
        raise ValueError(f"mes2000 debe ser un entero: {k!r}")
    return _inicio_mes(*_mes_de_indice(_indice_mes(_EPOCA.year, _EPOCA.month) + k))


def _ruta_ap(ap, alias: str) -> Path:
    if not alias.startswith(PREFIJO_AP):
        raise ErrorC5(f"la ruta {alias!r} no es de AP")
    return Path(ap) / PurePosixPath(alias[len(PREFIJO_AP):])


def _leer_archivo(ruta: Path, que: str) -> bytes:
    """Bytes de un archivo de RELOJ o del registro: nunca bajo /Volumes, regular y no enlace."""
    try:
        entorno.prohibido_volumes(ruta)
    except PermissionError as e:
        raise ErrorC5(f"{que}: los archivos de RELOJ y del registro nunca están bajo /Volumes") from e
    if ruta.is_symlink():
        raise ErrorC5(f"{que}: es un enlace simbólico")
    if not ruta.is_file():
        raise ErrorC5(f"{que}: no existe ({ruta.name})")
    return ruta.read_bytes()


def _json_de(datos: bytes, que: str) -> Any:
    try:
        return _leer_json(datos)
    except (ValueError, UnicodeDecodeError) as e:
        raise ErrorC5(f"{que}: JSON inválido: {e}") from e


# ---------------------------------------------------------------------------
# Registro de C5, política y artefactos evaluados (§2.1; POL-1, POL-2)
# ---------------------------------------------------------------------------
def _lexica(ruta) -> Path:
    """Ruta absoluta normalizada sin tocar el disco (como la de ``entorno``)."""
    return Path(os.path.normpath(os.path.abspath(os.fspath(ruta))))


def _aph_de(ap) -> Path:
    """POL-1: el APH hermano de ``ap``, con la anidación de ``entorno`` (ENT-6): el APH real si ``ap`` es el AP real
    (``entorno.rutas_reales``), o «<raíz>/APH» si ``ap`` es un «<raíz>/AP» sintético (``entorno.rutas_sinteticas`` y
    ``sintetico``), que nunca está dentro de AP ni de APH reales. Léxico: no consulta ni escribe el disco (por eso no
    llama a ``tempfile.gettempdir``, que prueba la carpeta temporal escribiendo un archivo)."""
    ap_lex = _lexica(ap)
    try:
        reales = entorno.rutas_reales()
    except RuntimeError:
        reales = None
    repositorios = () if reales is None else (_lexica(reales.ap), _lexica(reales.aph))
    if repositorios and ap_lex == repositorios[0]:
        return repositorios[1]
    if ap_lex.name != ALIAS_AP or any(r == ap_lex or r in ap_lex.parents for r in repositorios):
        raise ErrorC5("«ap» no es el AP real ni un «<raíz>/AP» sintético fuera de los repositorios")
    return ap_lex.parent / ALIAS_APH


def _alias_registro(ruta, ap) -> str:
    """POL-1: «APH/auditoria/<AAAAMMDD>/meteo_combinada/registro_politica_reloj.json», con la ruta dentro del APH
    hermano de ``ap`` (``_aph_de``): una copia fuera de APH (en AP, o en «<otra>/auditoria/…») se rechaza."""
    forma = "el registro de C5 debe ser APH/auditoria/<AAAAMMDD>/meteo_combinada/registro_politica_reloj.json"
    aph = _aph_de(ap)                     # fuera del try: ErrorC5 es un ValueError
    try:
        cola = _lexica(ruta).relative_to(aph).parts
    except ValueError as e:
        raise ErrorC5(f"{forma}: la ruta no está en el APH de «ap»") from e
    if len(cola) != len(_COLA_REGISTRO) or any(e is not None and c != e for c, e in zip(cola, _COLA_REGISTRO)):
        raise ErrorC5(forma)
    auditoria, fecha, carpeta, archivo = cola
    if _FECHA.fullmatch(fecha) is None:
        raise ErrorC5(f"la carpeta del registro de C5 no es una fecha AAAAMMDD: {fecha}")
    try:
        datetime.strptime(fecha, "%Y%m%d")
    except ValueError as e:
        raise ErrorC5(f"la fecha de C5 del registro no existe: {fecha}") from e
    return f"{ALIAS_APH}/{auditoria}/{fecha}/{carpeta}/{archivo}"


def _texto_errata(errata: Any) -> tipos.ErrataConfirmada | None:
    """POL-1: null o {"ruta", "sha256", "commit"} → None o ``tipos.ErrataConfirmada`` (TIP-13)."""
    if errata is None:
        return None
    if not isinstance(errata, Mapping) or tuple(sorted(errata)) != tuple(sorted(CLAVES_ERRATA)):
        raise ErrorC5(f"errata_confirmada debe ser null o un objeto con exactamente {CLAVES_ERRATA}")
    ruta, sha, commit = errata["ruta"], errata["sha256"], errata["commit"]
    if not isinstance(ruta, str) or not ruta.startswith((PREFIJO_AP, f"{ALIAS_APH}/")) \
            or not re.fullmatch(r"\S+", ruta) or not entorno.sin_datos_privados(ruta):
        raise ErrorC5("errata_confirmada.ruta debe ser una ruta por alias de AP o APH, sin espacios ni datos privados")
    if not _es_sha(sha) or not isinstance(commit, str) or _COMMIT.fullmatch(commit) is None:
        raise ErrorC5("errata_confirmada necesita un sha256 y un commit de 40 hexadecimales")
    return tipos.ErrataConfirmada(ruta=ruta, sha256=sha, commit=commit)


def _politica_de_bytes(datos: bytes) -> dict:
    politica = _json_de(datos, "política de RELOJ")
    if not isinstance(politica, dict) or politica.get("schema") != ESQUEMA_POLITICA_RELOJ:
        raise ErrorC5(f"la política no es una «{ESQUEMA_POLITICA_RELOJ}»")
    return politica


def _bandera(politica: Mapping, clave: str) -> bool:
    valor = politica.get(clave)
    if not isinstance(valor, bool):
        raise ErrorC5(f"la política no trae «{clave}» booleano")
    return valor


def leer_registro_c5(ruta, *, ap) -> RegistroReloj:
    """El registro de C5 (POL-1) y las banderas de la política que cita, tras comprobar su sha256. ``ErrorC5`` si falta,
    si su forma o sus rutas no son las fijadas, o si la sha256 de la política no es la registrada (§2.1)."""
    ruta = Path(ruta)
    alias = _alias_registro(ruta, ap)
    registro = _json_de(_leer_archivo(ruta, "sin registro de C5"), "registro de C5")
    if not isinstance(registro, dict) or set(registro) != set(CLAVES_REGISTRO_C5):
        raise ErrorC5(f"el registro de C5 debe traer exactamente {CLAVES_REGISTRO_C5} (sólo rutas, huellas y commit)")
    if registro["schema"] != ESQUEMA_REGISTRO_C5:
        raise ErrorC5(f"el registro de C5 no es un «{ESQUEMA_REGISTRO_C5}»")
    if registro["politica_ruta"] != RUTA_POLITICA_AP or registro["artefactos_ruta"] != RUTA_ARTEFACTOS_AP:
        raise ErrorC5(f"el registro de C5 debe citar {RUTA_POLITICA_AP} y {RUTA_ARTEFACTOS_AP}")
    try:
        sha_politica = _exigir_sha(registro["sha256_politica"], "sha256_politica")
        sha_artefactos = _exigir_sha(registro["sha256_artefactos"], "sha256_artefactos")
    except ValueError as e:
        raise ErrorC5(str(e)) from e
    commit = registro["commit_c5"]
    if not isinstance(commit, str) or _COMMIT.fullmatch(commit) is None:
        raise ErrorC5("commit_c5 no es un commit de 40 hexadecimales en minúscula")
    errata = _texto_errata(registro["errata_confirmada"])
    datos = _leer_archivo(_ruta_ap(ap, RUTA_POLITICA_AP), "política de RELOJ")
    if entorno.sha256_bytes(datos) != sha_politica:
        raise ErrorC5("la sha256 de la política de RELOJ no es la registrada en C5")
    politica = _politica_de_bytes(datos)
    return RegistroReloj(ruta=alias, sha256_politica=sha_politica, sha256_artefactos=sha_artefactos, commit_c5=commit,
                         post_hoc=_bandera(politica, "post_hoc"), errata_post_c4=_bandera(politica, "errata_post_c4"),
                         errata_confirmada=errata)


def _artefactos_de(obj: Any) -> dict[str, str]:
    """sha256 → código de ``artefactos_evaluados`` (una lista, o ``{"artefactos": [...]}``, como RELOJ)."""
    lista = obj.get("artefactos") if isinstance(obj, Mapping) else obj
    if not isinstance(lista, list):
        raise ErrorC5("artefactos_evaluados no es una lista")
    salida: dict[str, str] = {}
    for item in lista:
        sha = item.get("artefacto_sha256") if isinstance(item, Mapping) else None
        codigo = item.get("codigo") if isinstance(item, Mapping) else None
        if not _es_sha(sha) or not isinstance(codigo, str) or tipos.PATRON_CODIGO.fullmatch(codigo) is None:
            raise ErrorC5("cada artefacto evaluado necesita «artefacto_sha256» y un «codigo» de 6 dígitos")
        if salida.get(sha, codigo) != codigo:
            raise ErrorC5("un artefacto evaluado figura en dos estaciones")
        salida[sha] = codigo
    return salida


def leer_politica_reloj(registro, *, ap) -> tuple[dict, dict]:
    """Política y ``artefactos_evaluados`` (sha256 → código); exige sus sha256 (las del registro de C5)."""
    if not isinstance(registro, RegistroReloj):
        raise TypeError("leer_politica_reloj recibe un tipos.RegistroReloj")
    datos = _leer_archivo(_ruta_ap(ap, RUTA_POLITICA_AP), "política de RELOJ")
    if entorno.sha256_bytes(datos) != registro.sha256_politica:
        raise ErrorC5("la sha256 de la política de RELOJ no es la registrada en C5")
    politica = _politica_de_bytes(datos)
    comprimido = _leer_archivo(_ruta_ap(ap, RUTA_ARTEFACTOS_AP), "artefactos_evaluados")
    if entorno.sha256_bytes(comprimido) != registro.sha256_artefactos:
        raise ErrorC5("la sha256 de artefactos_evaluados no es la registrada en C5")
    try:
        expandido = gzip.decompress(comprimido)
    except (OSError, EOFError) as e:
        raise ErrorC5(f"artefactos_evaluados no es un gzip válido: {e}") from e
    return politica, _artefactos_de(_json_de(expandido, "artefactos_evaluados"))


def _fallas_marcas(codigo: str, marcas: Any) -> list[str]:
    if not isinstance(marcas, Mapping) or set(marcas) != set(CLAVES_MARCAS_RELOJ):
        return [f"{codigo}: «marcas» debe traer exactamente {CLAVES_MARCAS_RELOJ}"]
    fallas = []
    if not isinstance(marcas["posible_media_horaria"], bool):
        fallas.append(f"{codigo}: «posible_media_horaria» no es booleano")
    lista = marcas["reloj_no_verificado"]
    if not isinstance(lista, list):
        return fallas + [f"{codigo}: «reloj_no_verificado» no es una lista"]
    anios = []
    for item in lista:
        if not isinstance(item, Mapping) or set(item) != {"anio", "variables"}:
            fallas.append(f"{codigo}: cada «reloj_no_verificado» trae «anio» y «variables»")
            continue
        anio, variables = item["anio"], item["variables"]
        if isinstance(anio, bool) or not isinstance(anio, int):
            fallas.append(f"{codigo}: año G {anio!r} no es entero")
            continue
        anios.append(anio)
        if not isinstance(variables, list) or not variables or not all(isinstance(v, str) for v in variables) \
                or len(set(variables)) != len(variables):
            fallas.append(f"{codigo} {anio}: variables G vacías, repetidas o no son textos")
            continue
        conjunto = set(variables)
        pares = [set(par) for par in VARIABLES_G.values()]
        if not conjunto or any(not (conjunto & p == p or not conjunto & p) for p in pares) \
                or conjunto - set().union(*pares):
            fallas.append(f"{codigo} {anio}: variables G {sorted(conjunto)} no son pares completos de G-HR o G-viento")
    if len(set(anios)) != len(anios):
        fallas.append(f"{codigo}: años G repetidos")
    return fallas


def _fallas_politicas_reloj(politica: Mapping, solo: str | None = None, *, veredictos: bool = True) -> list[str]:
    """Estructura de ``politicas_reloj`` (POL-2), de una estación (``solo``) o de todas. Con ``veredictos`` exige
    además el veredicto de cada tramo en ``estaciones`` (C5); sin él (al armar los tramos), un tramo sin veredicto
    recibe su política y lo rechaza ``validar_regla_reloj_dmc`` al usarlo (§2.1, paso 1)."""
    entradas = politica.get("politicas_reloj")
    estaciones = politica.get("estaciones")
    if not isinstance(entradas, list) or not isinstance(estaciones, Mapping):
        return ["la política no trae «politicas_reloj» (lista) y «estaciones» (objeto)"]
    fallas: list[str] = []
    por_estacion: dict[str, list[tuple[datetime, datetime, str]]] = {}
    for n, e in enumerate(entradas):
        codigo = e.get("station_code") if isinstance(e, Mapping) else None
        if solo is not None and codigo != solo:
            continue
        nombre = f"regla n.º {n} ({codigo})"
        if not isinstance(e, Mapping) or set(e) != set(CLAVES_TRAMO_RELOJ):
            fallas.append(f"{nombre}: claves distintas de {CLAVES_TRAMO_RELOJ}")
            continue
        if not isinstance(codigo, str) or tipos.PATRON_CODIGO.fullmatch(codigo) is None:
            fallas.append(f"{nombre}: station_code inválido")
            continue
        clock = e["clock"]
        if not isinstance(clock, Mapping) or set(clock) != set(CLAVES_CLOCK_RELOJ):
            fallas.append(f"{nombre}: «clock» sin exactamente {CLAVES_CLOCK_RELOJ}")
            continue
        try:
            a, b = _etiqueta(e["valid_from"]), _etiqueta(e["valid_to"])
        except ValueError as x:
            fallas.append(f"{nombre}: {x}")
            continue
        if a > b:
            fallas.append(f"{nombre}: intervalo invertido")
        if clock["valid_from"] != e["valid_from"] or clock["valid_to"] != e["valid_to"]:
            fallas.append(f"{nombre}: el intervalo de «clock» no es el externo")
        if clock["verified"] is not True or clock["timestamp_semantics"] != INSTANTANEA:
            fallas.append(f"{nombre}: «clock» no verificado o no instantáneo")
        minutos = clock["fixed_offset_minutes"]
        if isinstance(minutos, bool) or not isinstance(minutos, int):
            fallas.append(f"{nombre}: «fixed_offset_minutes» no es entero")
        partes = _partes_source(clock["source"])
        if partes is None or partes.estacion != codigo or tipos.PATRON_TRAMO_RELOJ.fullmatch(partes.tramo) is None:
            fallas.append(f"{nombre}: «source» fuera del patrón de RELOJ o de otra estación")
            continue
        por_estacion.setdefault(codigo, []).append((a, b, partes.tramo))
    for codigo, lista in sorted(por_estacion.items()):
        lista.sort()
        ids = [t for _, _, t in lista]
        if len(set(ids)) != len(ids):
            fallas.append(f"{codigo}: ids de tramo de RELOJ repetidos")
        if any(lista[i][0] <= lista[i - 1][1] for i in range(1, len(lista))):
            fallas.append(f"{codigo}: tramos de RELOJ solapados")
        entrada = estaciones.get(codigo)
        if not isinstance(entrada, Mapping) or entrada.get("veredicto") != VEREDICTO_CONFIRMADA:
            fallas.append(f"{codigo}: tiene tramos pero no está «{VEREDICTO_CONFIRMADA}» en «estaciones»")
            continue
        por_tramo = entrada.get(CLAVE_TRAMOS_ESTACION)
        sin = [t for t in ids if not isinstance(por_tramo, Mapping) or not isinstance(por_tramo.get(t), str)]
        if sin and veredictos:
            fallas.append(f"{codigo}: tramos sin veredicto en «estaciones»: {sin}")
        fallas += _fallas_marcas(codigo, entrada.get("marcas"))
    return fallas


def comprobar_c5(registro, politica) -> list[str]:
    """``post_hoc``, ``errata_post_c4`` y sha256, más las citas y la estructura de la política (POL-2). Lista vacía:
    C5 válido. No vuelve a leer archivos (las sha256 de los archivos las exigen ``leer_*``)."""
    if not isinstance(registro, RegistroReloj):
        raise TypeError("comprobar_c5 recibe un tipos.RegistroReloj")
    fallas: list[str] = []
    for nombre in ("sha256_politica", "sha256_artefactos"):
        if not _es_sha(getattr(registro, nombre)):
            fallas.append(f"registro: {nombre} no es un sha256")
    if not isinstance(registro.commit_c5, str) or _COMMIT.fullmatch(registro.commit_c5) is None:
        fallas.append("registro: commit_c5 no es un commit")
    if not isinstance(politica, Mapping) or politica.get("schema") != ESQUEMA_POLITICA_RELOJ:
        return fallas + [f"la política no es una «{ESQUEMA_POLITICA_RELOJ}»"]
    if set(politica) != set(CLAVES_POLITICA_RELOJ):
        fallas.append(f"la política no trae exactamente {CLAVES_POLITICA_RELOJ}")
    for clave in ("post_hoc", "errata_post_c4", "ajuste_documental"):
        if not isinstance(politica.get(clave), bool):
            fallas.append(f"la política no trae «{clave}» booleano")
    if politica.get("post_hoc") is not registro.post_hoc or politica.get("errata_post_c4") is not registro.errata_post_c4:
        fallas.append("las banderas del registro no son las de la política")
    if politica.get("post_hoc") is True or registro.post_hoc is True:
        fallas.append("post_hoc = true: la política de RELOJ no es válida para M3-4 (§2.1)")
    errata = politica.get("errata_post_c4") is True or registro.errata_post_c4 is True
    if errata and registro.errata_confirmada is None:
        fallas.append("errata_post_c4 = true sin una errata confirmada en el registro de C5 (§2.1)")
    if not errata and registro.errata_confirmada is not None:
        fallas.append("el registro cita una errata, pero la política no lleva errata_post_c4 = true")
    # D23 (P13): ajuste_documental = true se acepta (sólo debe ser booleano, arriba) y lo declara declaracion_c5.
    if politica.get("artefactos_evaluados") != {"ruta": RUTA_ARTEFACTOS_RELOJ, "sha256": registro.sha256_artefactos}:
        fallas.append("la política no cita artefactos_evaluados con la ruta publicada y la sha256 del registro")
    informe = politica.get("informe")
    if not isinstance(informe, Mapping) or set(informe) != {"ruta", "sha256"} \
            or informe.get("ruta") != RUTA_INFORME_RELOJ or not _es_sha(informe.get("sha256")):
        fallas.append("la política no cita el informe publicado con su sha256")
    if politica.get("adaptador_sha256") != fijados.SHA_ADAPTADOR:
        fallas.append("la política no es la del adaptador fijado (f61559ea…)")
    if politica.get("transiciones_sha256") != SHA_TRANSICIONES_RELOJ:
        fallas.append("la política no es la de la tabla de cambios de hora del Anexo A de RELOJ (8ea58b78…)")
    return fallas + _fallas_politicas_reloj(politica)


CLAVES_DECLARACION_C5 = ("registro", "sha256_politica", "sha256_artefactos", "commit_c5", "post_hoc",
                         "errata_post_c4", "ajuste_documental", "errata_confirmada")


def declaracion_c5(registro, politica) -> dict:
    """POL-15 (D23 y D26): lo que el registro de M3-4 declara de C5, sólo de un C5 válido. Rutas, huellas, commit y
    banderas (``ajuste_documental`` incluida, D23), con tipos de Python y sin números de datos. ``ErrorC5`` con las
    fallas de ``comprobar_c5`` si las hay."""
    fallas = comprobar_c5(registro, politica)
    if fallas:
        raise ErrorC5("C5 no válido; no se declara: " + "; ".join(fallas))
    errata = registro.errata_confirmada
    declaracion = {"registro": registro.ruta, "sha256_politica": registro.sha256_politica,
                   "sha256_artefactos": registro.sha256_artefactos, "commit_c5": registro.commit_c5,
                   "post_hoc": politica["post_hoc"], "errata_post_c4": politica["errata_post_c4"],
                   "ajuste_documental": politica["ajuste_documental"],
                   "errata_confirmada": None if errata is None else {"ruta": errata.ruta, "sha256": errata.sha256,
                                                                     "commit": errata.commit}}
    _exigir_python(declaracion, "declaracion_c5")
    return declaracion


def coordenadas_inconsistentes(registro, *, ap) -> frozenset[str]:
    """K2: sólo esa lista, por código (MC-19; POL-3), del informe publicado con la sha256 que cita la política."""
    politica, _ = leer_politica_reloj(registro, ap=ap)
    cita = politica.get("informe")
    if not isinstance(cita, Mapping) or cita.get("ruta") != RUTA_INFORME_RELOJ or not _es_sha(cita.get("sha256")):
        raise ErrorC5("la política no cita el informe publicado con su sha256")
    datos = _leer_archivo(_ruta_ap(ap, PREFIJO_AP + RUTA_INFORME_RELOJ), "informe de RELOJ")
    if entorno.sha256_bytes(datos) != cita["sha256"]:
        raise ErrorC5("la sha256 del informe de RELOJ no es la que cita la política")
    informe = _json_de(datos, "informe de RELOJ")
    lista = informe.get(CLAVE_K2) if isinstance(informe, Mapping) else None
    del informe, datos                # §1.9: del informe sólo se toma esta lista; nada más se devuelve ni se guarda
    if not isinstance(lista, list) or not all(isinstance(c, str) and tipos.PATRON_CODIGO.fullmatch(c) for c in lista) \
            or len(set(lista)) != len(lista):
        raise ErrorC5(f"el informe no trae «{CLAVE_K2}» como lista de códigos de 6 dígitos sin repetir")
    return frozenset(lista)


# ---------------------------------------------------------------------------
# Textos source (§2.2, §2.3, §2.5)
# ---------------------------------------------------------------------------
def _partes_coordenadas(texto: Any) -> tuple[str, str, str, str | None] | None:
    """(sha del catálogo, código, sha del protocolo, motivo) de un ``coordinates.source`` de §2.5, o None."""
    m = _COORDENADAS.fullmatch(texto) if isinstance(texto, str) else None
    return None if m is None else m.groups()


def _sufijo_motivo(motivo: str | None) -> str:
    if motivo is None:
        return ""
    if not isinstance(motivo, str) or _TOKEN.fullmatch(motivo) is None:
        raise ValueError(f"motivo de source inválido: {motivo!r}")
    return f" motivo={motivo}"


def _exigir_variable(variable: str, validas: Iterable[str]) -> str:
    if variable not in tuple(validas):
        raise ValueError(f"variable sin regla en §2.2-§2.3: {variable!r}")
    return variable


def source_coordenadas(codigo: str, sha_catalogo: str, sha_protocolo: str, *, motivo: str | None = None) -> str:
    """§2.5: «meteo-combinada/v1 coordenadas=catalogo sha256=<64> continuidad=supuesta estacion=<código>
    protocolo=<64>», con « motivo=<m>» si las coordenadas quedan sin confirmar (POL-5, POL-9)."""
    _exigir_codigo(codigo)
    _exigir_sha(sha_catalogo, "sha_catalogo")
    _exigir_sha(sha_protocolo, "sha_protocolo")
    return (f"{PREFIJO_SOURCE} coordenadas=catalogo sha256={sha_catalogo} continuidad=supuesta estacion={codigo} "
            f"protocolo={sha_protocolo}{_sufijo_motivo(motivo)}")


def source_medicion(variable: str, sha_protocolo: str, *, motivo: str | None = None) -> str:
    """§2.5: «meteo-combinada/v1 medicion=<variable> protocolo=<64>», con « motivo=<m>» (§2.2: «con el motivo en
    `source`»; POL-6)."""
    _exigir_variable(variable, MEDICIONES)
    _exigir_sha(sha_protocolo, "sha_protocolo")
    return f"{PREFIJO_SOURCE} medicion={variable} protocolo={sha_protocolo}{_sufijo_motivo(motivo)}"


def source_calidad(variable: str, sha_protocolo: str) -> str:
    """§2.5: «meteo-combinada/v1 calidad=<variable> protocolo=<64>»."""
    _exigir_variable(variable, ORDEN_CALIDAD)
    _exigir_sha(sha_protocolo, "sha_protocolo")
    return f"{PREFIJO_SOURCE} calidad={variable} protocolo={sha_protocolo}"


# ---------------------------------------------------------------------------
# Marcas de RELOJ (§2.2)
# ---------------------------------------------------------------------------
def _entrada_estacion(politica_reloj: Mapping, codigo: str) -> Mapping | None:
    estaciones = politica_reloj.get("estaciones") if isinstance(politica_reloj, Mapping) else None
    if not isinstance(estaciones, Mapping):
        raise ValueError("la política de RELOJ no trae «estaciones»")
    entrada = estaciones.get(_exigir_codigo(codigo))
    if entrada is None or entrada.get("veredicto") != VEREDICTO_CONFIRMADA:
        return None
    fallas = _fallas_marcas(codigo, entrada.get("marcas"))
    if fallas:
        raise ValueError("; ".join(fallas))
    return entrada


def marcas_g(politica_reloj, codigo: str) -> dict[int, frozenset[str]]:
    """Año de etiqueta → variables de la fuente que G-HR o G-viento dejan sin verificar (§2.2; POL-6)."""
    entrada = _entrada_estacion(politica_reloj, codigo)
    if entrada is None:
        return {}
    return {int(i["anio"]): frozenset(i["variables"]) for i in entrada["marcas"]["reloj_no_verificado"]}


def media_horaria(politica_reloj, codigo: str) -> bool:
    """«Posible media horaria» de RELOJ §4.3.5 para la estación (§2.2)."""
    entrada = _entrada_estacion(politica_reloj, codigo)
    return False if entrada is None else entrada["marcas"]["posible_media_horaria"]


def _marcas_por_anio(marcas: Mapping | None) -> dict[int, frozenset[str]]:
    salida = {}
    for anio, variables in (marcas or {}).items():
        if isinstance(anio, bool) or not isinstance(anio, int):
            raise ValueError(f"año G {anio!r} no es entero")
        conjunto = frozenset(variables)
        if not all(isinstance(v, str) for v in conjunto):
            raise ValueError(f"variables G de {anio} no son textos")
        salida[anio] = conjunto
    return salida


def _motivo_g(variable: str, marcadas: frozenset[str]) -> str | None:
    for motivo, variables in VARIABLES_G.items():
        if variable in variables and variable in marcadas:
            return motivo
    return None


# ---------------------------------------------------------------------------
# Tramos (§2.5, «Tramos»; POL-4, POL-5, POL-10)
# ---------------------------------------------------------------------------
def _reglas_de_estacion(politica_reloj: Mapping, codigo: str) -> list[tuple[str, datetime, datetime, dict]]:
    """(id de RELOJ, desde, hasta, clock) de la estación, en orden; ValueError si la política está mal formada."""
    fallas = _fallas_politicas_reloj(politica_reloj, solo=_exigir_codigo(codigo), veredictos=False)
    if fallas:
        raise ValueError("política de RELOJ mal formada: " + "; ".join(fallas))
    salida = []
    for e in politica_reloj["politicas_reloj"]:
        if e["station_code"] == codigo:
            tramo = _partes_source(e["clock"]["source"]).tramo
            salida.append((tramo, _etiqueta(e["valid_from"]), _etiqueta(e["valid_to"]), dict(e["clock"])))
    return sorted(salida, key=lambda t: t[1])


def _lista_k2(k2) -> frozenset[str]:
    """POL-5: la lista K2 como conjunto de códigos de 6 dígitos. Un texto («900701») o un objeto se rechazan: harían
    el conjunto de sus caracteres o de sus claves y K2 se ignoraría sin aviso."""
    if isinstance(k2, (str, bytes, bytearray, Mapping)):
        raise ValueError(f"k2 es un conjunto de códigos de la lista K2, no un {type(k2).__name__}: {k2!r}")
    return frozenset(_exigir_codigo(c) for c in k2)


def _estado_coordenadas(info, k2: frozenset[str]) -> tuple[bool, str | None]:
    """POL-5: (confirmadas, motivo) en todo el registro de la estación, antes de K4."""
    try:
        legibles = math.isfinite(float(info.lat)) and math.isfinite(float(info.lon))
    except (TypeError, ValueError):
        legibles = False
    if not legibles:
        return False, MOTIVO_SIN_COORDENADAS
    if info.k3_pasa is not True:
        return False, MOTIVO_K3
    if info.codigo in k2:
        return False, MOTIVO_K2
    return True, None


def _meses_validos(meses) -> frozenset[int]:
    salida = set()
    for par in meses:
        enteros = isinstance(par, tuple) and len(par) == 2 and all(type(x) is int for x in par)
        if not enteros or not 1 <= par[1] <= 12:
            raise ValueError(f"meses_con_artefacto lleva pares (año, mes) enteros: {par!r}")
        salida.add(_indice_mes(*par))
    return frozenset(salida)


def _cortes_g(desde: datetime, hasta: datetime, por_anio: Mapping[int, frozenset[str]]) -> list[datetime]:
    """POL-4 (D25, la literal de §2.2): el 1 de enero de cada año con marcas G y el del año siguiente, aunque dos años
    seguidos tengan las mismas marcas; sólo los que caen en (desde, hasta]."""
    anios = {y for anio, variables in por_anio.items() if variables for y in (anio, anio + 1)}
    return sorted(c for c in (datetime(y, 1, 1) for y in anios) if desde < c <= hasta)


def _segmentos_g(desde: datetime, hasta: datetime,
                 por_anio: Mapping[int, frozenset[str]]) -> list[tuple[datetime, datetime]]:
    """[desde, hasta] partido en los cortes de los años G (POL-4, D25)."""
    bordes = [desde, *_cortes_g(desde, hasta, por_anio)]
    return [(a, (bordes[i + 1] - UNA_HORA) if i + 1 < len(bordes) else hasta) for i, a in enumerate(bordes)]


def _rachas_de_meses(desde: datetime, hasta: datetime, meses: frozenset[int]) -> list[tuple[datetime, datetime]]:
    """Sucesiones de meses de etiqueta con artefacto evaluado dentro de [desde, hasta] (POL-4)."""
    i0, i1 = _indice_mes(desde.year, desde.month), _indice_mes(hasta.year, hasta.month)
    rachas, actual = [], None
    for i in range(i0, i1 + 1):
        if i in meses:
            actual = [i, i] if actual is None else [actual[0], i]
        elif actual is not None:
            rachas.append(actual)
            actual = None
    if actual is not None:
        rachas.append(actual)
    return [(max(desde, _inicio_mes(*_mes_de_indice(a))), min(hasta, _ultima_hora_mes(*_mes_de_indice(b))))
            for a, b in rachas]


def tramos_de_lectura(politica_reloj, codigo, meses_con_artefacto, marcas_g, *, info, k2) -> list[TramoPolitica]:
    """Tramos de RELOJ de la estación, partidos por los años G y sin meses sin artefacto evaluado (§2.5; POL-4), con
    las coordenadas de K1-K3 y K2 (POL-5). ``marcas_g``: año → variables G (``politicas.marcas_g``)."""
    _exigir_codigo(codigo)
    if not isinstance(info, tipos.InfoEstacion) or info.codigo != codigo:
        raise ValueError("tramos_de_lectura necesita la InfoEstacion de la misma estación")
    k2 = _lista_k2(k2)
    confirmadas, motivo = _estado_coordenadas(info, k2)
    meses = _meses_validos(meses_con_artefacto)
    por_anio = _marcas_por_anio(marcas_g)
    salida = []
    for tramo, desde, hasta, clock in _reglas_de_estacion(politica_reloj, codigo):
        piezas = []
        for ga, gb in _segmentos_g(desde, hasta, por_anio):
            for ra, rb in _rachas_de_meses(desde, hasta, meses):
                a, b = max(ga, ra), min(gb, rb)
                if a <= b:
                    piezas.append((a, b))
        for k, (a, b) in enumerate(sorted(piezas), start=1):
            salida.append(TramoPolitica(codigo=codigo, id=tipos.id_tramo(tramo, k), valid_from=_texto(a),
                                        valid_to=_texto(b), clock=dict(clock), coordenadas_confirmadas=confirmadas,
                                        motivo=motivo))
    return salida


def tramos_de_politicas(politicas) -> list[TramoPolitica]:
    """Un ``TramoPolitica`` por política, en el mismo orden, con el id «<RELOJ>/<k>» (POL-10). Exige la lista completa
    de cada estación: k cuenta las piezas de cada tramo de RELOJ en orden de ``valid_from``."""
    filas: list[_Pieza] = []
    for i, p in enumerate(politicas):
        codigo = _exigir_codigo(p.get("station_code"))
        clock = p.get("clock")
        partes = _partes_source(clock.get("source")) if isinstance(clock, Mapping) else None
        if partes is None or partes.estacion != codigo:
            raise ValueError(f"política n.º {i}: «clock» sin el source de RELOJ de su estación")
        filas.append(_Pieza(codigo, partes.tramo, _etiqueta(p["valid_from"]), _etiqueta(p["valid_to"]), i))
    k_de: dict[int, int] = {}
    por_estacion: dict[str, list[_Pieza]] = {}
    for fila in filas:
        por_estacion.setdefault(fila.codigo, []).append(fila)
    for codigo, lista in por_estacion.items():
        lista.sort(key=lambda f: f.desde)
        if any(f.desde > f.hasta for f in lista) or any(sig.desde <= ant.hasta for ant, sig in zip(lista, lista[1:])):
            raise ValueError(f"{codigo}: políticas solapadas o invertidas")
        cuenta: dict[str, int] = {}
        for f in lista:
            cuenta[f.tramo] = cuenta.get(f.tramo, 0) + 1
            k_de[f.indice] = cuenta[f.tramo]
    salida = []
    for codigo, tramo, _, _, i in filas:
        p = politicas[i]
        coord = p.get("coordinates", {})
        partes = _partes_coordenadas(coord.get("source")) if isinstance(coord, Mapping) else None
        salida.append(TramoPolitica(codigo=codigo, id=tipos.id_tramo(tramo, k_de[i]), valid_from=p["valid_from"],
                                    valid_to=p["valid_to"], clock=dict(p["clock"]),
                                    coordenadas_confirmadas=isinstance(coord, Mapping) and coord.get("verified") is True,
                                    motivo=None if partes is None else partes[-1]))
    return salida


def tramos_marca_14(efectivas, codigo: str) -> list[TramoPolitica]:
    """POL-14 (D24, P14): los tramos en que la marca 14 toma |mediana(QFE − p_F)| (§2.4) son los de la política
    efectiva. ``efectivas`` es la lista completa que da ``politicas_efectivas`` (los ids salen de
    ``tramos_de_politicas`` sobre ella, POL-10); devuelve los de ``codigo`` en orden de ``valid_from``. Las horas de cada
    tramo son las de etiqueta dentro de su intervalo inclusivo (A6). La marca la aplica ``qc_dmc_meteo`` (I12)."""
    _exigir_codigo(codigo)
    return sorted((t for t in tramos_de_politicas(efectivas) if t.codigo == codigo), key=lambda t: t.valid_from)


# ---------------------------------------------------------------------------
# Políticas de lectura (§2.2, §2.3, §2.5; POL-5 a POL-8)
# ---------------------------------------------------------------------------
def _float(x: Any) -> float:
    v = float(x)
    if not math.isfinite(v):
        raise ValueError(f"límite no finito: {x!r}")
    return v


def _limite(x: Any, en_float: bool) -> int | float:
    if en_float:
        return _float(x)
    if isinstance(x, bool) or not isinstance(x, int):
        raise ValueError(f"límite entero esperado: {x!r}")
    return int(x)


def _z_del_catalogo(info) -> float | None:
    """POL-7: z_s sólo si K3 pasa y viene del catálogo; si no, QFE queda sin regla."""
    if info.k3_pasa is not True or info.z_s_fuente != FuenteZs.CATALOGO.value:
        return None
    try:
        z = float(info.z_s)
    except (TypeError, ValueError):
        return None
    return z if math.isfinite(z) else None


def politicas_de_lectura(politica_reloj, info, tramos, umbrales, *, sha_protocolo, sha_catalogo) -> list[dict]:
    """La política de §2.5 de cada tramo, en el orden y con los intervalos de ``tramos`` (acuerdo A6), lista para
    ``cargar_dmc``: ``clock`` de RELOJ sin cambios, ``coordinates``, ``measurements`` (§2.2) y ``quality`` (§2.3)."""
    if not isinstance(info, tipos.InfoEstacion):
        raise TypeError("politicas_de_lectura recibe una tipos.InfoEstacion")
    codigo = _exigir_codigo(info.codigo)
    _exigir_sha(sha_catalogo, "sha_catalogo")
    if not _es_sha(sha_protocolo) or sha_protocolo != getattr(umbrales, "sha256_texto_vigente", None):
        raise ValueError("sha_protocolo debe ser el sha256 del texto vigente (Umbrales.sha256_texto_vigente; POL-8)")
    publicadas = {t: (a, b, clock) for t, a, b, clock in _reglas_de_estacion(politica_reloj, codigo)}
    por_anio = marcas_g(politica_reloj, codigo)
    mh = media_horaria(politica_reloj, codigo)
    z = _z_del_catalogo(info)
    salida = []
    fin_previo = None
    for t in tramos:
        if not isinstance(t, TramoPolitica) or t.codigo != codigo:
            raise ValueError("cada tramo debe ser un TramoPolitica de la misma estación")
        m = tipos.PATRON_TRAMO.fullmatch(t.id)
        if m is None or m.group("reloj") not in publicadas:
            raise ValueError(f"{codigo}: el tramo {t.id!r} no es de un tramo de RELOJ publicado")
        a_reloj, b_reloj, clock = publicadas[m.group("reloj")]
        if dict(t.clock) != clock:
            raise ValueError(f"{codigo} {t.id}: «clock» distinto del publicado por RELOJ")
        a, b = _etiqueta(t.valid_from), _etiqueta(t.valid_to)
        if not a_reloj <= a <= b <= b_reloj:
            raise ValueError(f"{codigo} {t.id}: intervalo fuera de su tramo de RELOJ o invertido")
        if fin_previo is not None and a <= fin_previo:
            raise ValueError(f"{codigo} {t.id}: tramos solapados o fuera de orden")
        fin_previo = b
        marcadas = {por_anio.get(y, frozenset()) for y in range(a.year, b.year + 1)}
        if _cortes_g(a, b, por_anio) or len(marcadas) != 1:
            raise ValueError(f"{codigo} {t.id}: el tramo cruza el 1 de enero de un año con marcas G, o el del año "
                             "siguiente, sin partirse (§2.2 y §2.5; POL-4, D25)")
        (marcadas,) = marcadas
        intervalo = {"valid_from": t.valid_from, "valid_to": t.valid_to}
        coord = {"verified": bool(t.coordenadas_confirmadas),
                 "source": source_coordenadas(codigo, sha_catalogo, sha_protocolo,
                                              motivo=None if t.coordenadas_confirmadas else t.motivo),
                 **intervalo}
        try:
            lat, lon = float(info.lat), float(info.lon)
        except (TypeError, ValueError):
            lat = lon = math.nan
        if math.isfinite(lat) and math.isfinite(lon):
            coord.update(latitude=lat, longitude=lon)
        elif t.coordenadas_confirmadas:
            raise ValueError(f"{codigo} {t.id}: coordenadas confirmadas sin latitud y longitud legibles")
        mediciones = {}
        for variable, (estadistico, constante) in MEDICIONES.items():
            motivo = MOTIVO_MEDIA_HORARIA if mh else _motivo_g(variable, marcadas)
            intervalo_min = constantes.valor(constante)
            if isinstance(intervalo_min, bool) or not isinstance(intervalo_min, int):
                raise ValueError(f"{constante} no es entero")
            mediciones[variable] = {"verified": motivo is None,
                                    "source": source_medicion(variable, sha_protocolo, motivo=motivo), **intervalo,
                                    "statistic": estadistico, "interval_minutes": int(intervalo_min)}
        calidad = {}
        for variable in ORDEN_CALIDAD:
            if variable == QFE:
                if z is None:
                    continue
                p0 = float(numerico.p_std(z))
                unidad = UNIDAD_QFE
                minimo, maximo = _float(p0 + umbrales.a("QQFE_BAJO")), _float(p0 + umbrales.a("QQFE_ALTO"))
            else:
                unidad, id_min, id_max, en_float = CALIDAD[variable]
                minimo, maximo = _limite(umbrales.a(id_min), en_float), _limite(umbrales.a(id_max), en_float)
            calidad[variable] = {"verified": True, "source": source_calidad(variable, sha_protocolo), **intervalo,
                                 "unit": unidad, "method": METODO_CALIDAD, "accepted_source_codes": [],
                                 "allow_unknown_source_qc": True, "minimum": minimo, "maximum": maximo}
        salida.append({"station_code": codigo, **intervalo, "clock": dict(clock), "coordinates": coord,
                       "measurements": mediciones, "quality": calidad})
    return salida


# ---------------------------------------------------------------------------
# Política efectiva (MC-53; POL-9)
# ---------------------------------------------------------------------------
def _con_intervalo(p: dict, a: datetime, b: datetime) -> dict:
    nueva = copy.deepcopy(p)
    intervalo = {"valid_from": _texto(a), "valid_to": _texto(b)}
    nueva.update(intervalo)
    nueva["coordinates"].update(intervalo)
    for grupo in ("measurements", "quality"):
        for regla in nueva[grupo].values():
            regla.update(intervalo)
    return nueva


def _sin_coordenadas(p: dict, motivo: str) -> dict:
    coord = p["coordinates"]
    if coord.get("verified") is not True:
        return p
    partes = _partes_coordenadas(coord.get("source"))
    if partes is None:
        raise ValueError(f"{p['station_code']}: «coordinates.source» fuera del formato de §2.5")
    sha_catalogo, codigo, sha_protocolo, _ = partes
    coord.update(verified=False, source=source_coordenadas(codigo, sha_catalogo, sha_protocolo, motivo=motivo))
    return p


def politicas_efectivas(politicas_lectura, resultados_k4: dict) -> list[dict]:
    """La política publicada (MC-53; A5): cada tramo partido en los meses de K4 y sin coordenadas antes del último
    traslado (POL-9). ``resultados_k4``: código → ``tipos.ResultadoK4``."""
    tramos_de_politicas(politicas_lectura)        # valida la forma, el orden y que no haya solapes
    for codigo, r in resultados_k4.items():
        if not isinstance(r, ResultadoK4) or r.codigo != codigo:
            raise ValueError(f"resultados_k4[{codigo!r}] debe ser el ResultadoK4 de esa estación")
    salida = []
    for p in politicas_lectura:
        r = resultados_k4.get(p["station_code"])
        if r is None:
            salida.append(copy.deepcopy(p))
            continue
        meses = {q.mes for q in r.quiebres} | {k for k in (r.ultimo_traslado, r.ultimo_barometro) if k is not None}
        minutos = p["clock"]["fixed_offset_minutes"]
        if isinstance(minutos, bool) or not isinstance(minutos, int):
            raise ValueError(f"{p['station_code']}: «fixed_offset_minutes» no es entero")
        desfase = timedelta(minutes=minutos)
        a, b = _etiqueta(p["valid_from"]), _etiqueta(p["valid_to"])
        cortes = sorted({L for L in (_utc_de_mes2000(k) + desfase for k in meses) if a < L <= b})
        bordes = [a, *cortes]
        traslado = None if r.ultimo_traslado is None else _utc_de_mes2000(r.ultimo_traslado)
        for i, desde in enumerate(bordes):
            hasta = bordes[i + 1] - UNA_HORA if i + 1 < len(bordes) else b
            pieza = _con_intervalo(p, desde, hasta)
            if traslado is not None and hasta - desfase < traslado:
                pieza = _sin_coordenadas(pieza, MOTIVO_TRASLADO)
            salida.append(pieza)
    return salida


# ---------------------------------------------------------------------------
# Uso por artefacto (§2.1, paso 1; POL-11, POL-13)
# ---------------------------------------------------------------------------
def politicas_que_cruzan(politicas, codigo: str, anio: int, mes: int) -> list[dict]:
    """Las políticas de la estación cuyo intervalo externo corta el mes de etiqueta (POL-13), en el orden recibido."""
    _exigir_codigo(codigo)
    if any(isinstance(x, bool) or not isinstance(x, int) for x in (anio, mes)) or not 1 <= mes <= 12:
        raise ValueError(f"mes de etiqueta inválido: {anio!r}-{mes!r}")
    inicio, fin = _inicio_mes(anio, mes), _ultima_hora_mes(anio, mes)
    return [p for p in politicas if p.get("station_code") == codigo
            and _etiqueta(p["valid_from"]) <= fin and _etiqueta(p["valid_to"]) >= inicio]


def regla_reloj(politica) -> dict:
    """La regla publicada de RELOJ detrás de una política (POL-11): ``station_code``, el intervalo de ``clock`` y
    ``clock`` sin cambios."""
    clock = politica.get("clock") if isinstance(politica, Mapping) else None
    if not isinstance(clock, Mapping):
        raise ValueError("la política no trae «clock»")
    return {"station_code": politica["station_code"], "valid_from": clock["valid_from"], "valid_to": clock["valid_to"],
            "clock": dict(clock)}


def validar_reglas(politicas, content_sha256: str, validar_regla: Callable) -> tuple[list[dict], tuple[str, ...]]:
    """Pasa cada regla de RELOJ de ``politicas`` por ``validar_regla`` (``validar_regla_reloj_dmc``) con el
    ``content_sha256`` del artefacto. Devuelve las políticas aceptadas (en orden) y los ids de RELOJ rechazados: una
    regla rechazada no se entrega (§2.1; POL-11)."""
    veredicto: dict[str, bool] = {}
    aceptadas, rechazadas = [], set()
    for p in politicas:
        nucleo = regla_reloj(p)
        clave = entorno.json_canonico(nucleo).decode("utf-8")
        if clave not in veredicto:
            try:
                validar_regla(nucleo, content_sha256)
                veredicto[clave] = True
            except ValueError:
                veredicto[clave] = False
        if veredicto[clave]:
            aceptadas.append(p)
        else:
            partes = _partes_source(nucleo["clock"].get("source"))
            rechazadas.add(partes.tramo if partes else "?")
    return aceptadas, tuple(sorted(rechazadas))


# ---------------------------------------------------------------------------
# JSON (§2.1, «Números de Python»; POL-12)
# ---------------------------------------------------------------------------
def _exigir_python(x: Any, donde: str) -> None:
    t = type(x)
    if t not in _TIPOS_JSON:
        raise TypeError(f"{donde}: {t.__name__} no es un tipo de Python admitido (§2.1, «Números de Python»)")
    if t is float and not math.isfinite(x):
        raise ValueError(f"{donde}: número no finito")
    if t is dict:
        for k, v in x.items():
            if type(k) is not str:
                raise TypeError(f"{donde}: clave {k!r} no es texto")
            _exigir_python(v, f"{donde}.{k}")
    elif t is list:
        for i, v in enumerate(x):
            _exigir_python(v, f"{donde}[{i}]")


def a_json(politicas) -> bytes:
    """Números de Python; ida y vuelta exacta (POL-12)."""
    if type(politicas) is not list:
        raise TypeError("a_json recibe la lista de políticas")
    _exigir_python(politicas, "politicas")
    return entorno.json_canonico(politicas)


def de_json(datos: bytes) -> list[dict]:
    """La lista de políticas releída de ``a_json``: sin claves repetidas ni NaN, y con los tipos de Python."""
    politicas = _leer_json(datos)
    if type(politicas) is not list or not all(type(p) is dict for p in politicas):
        raise ValueError("el JSON de políticas no es una lista de objetos")
    _exigir_python(politicas, "politicas")
    return politicas

