"""Umbrales del Anexo A: lectura de ``meteo_combinada_v1.json``, regeneración desde el texto y traducción a valores.

Regla del paquete (§0, regla 2): ningún umbral del Anexo A se escribe a mano. Todo módulo los pide a ``Umbrales``:
``U.a("QTS_MIN")`` devuelve el valor tal como lo escribe el texto (−39 para «−39»; las listas vuelven como tupla) y
``U.frac(id)`` el de los ids ``*_PCT`` entre 100. ``regenerar_desde_texto`` rehace el JSON con el algoritmo de
``m0/preparar_m0.anexo_a`` y debe reproducirlo byte a byte; ``comparar`` es estricto; ``traducir`` exige
``re.fullmatch`` de cada fila con su plantilla (Anexo P del diseño). Este protocolo no tiene umbrales ajustables: todo
valor es fijo desde M0 y sólo una enmienda lo cambia (§10).

Cómo se leen los números del Anexo A (``numero_del_texto``): signo «−» (U+2212) o «+», miles con «.» y decimales con
«,»; sin coma el valor es entero. Las listas van entre llaves: «, » entre enteros y «; » cuando algún elemento lleva
decimales («{0,05; 0,2; 0,5; 1,0}», «{0,1; 1; 10; 100; 1.000}»).

Plantillas (``PLANTILLAS``): una por grupo, en el orden del Anexo A. Cada ``{ID}`` es un número escrito como en el
texto; ``{ID}`` de una lista (``IDS_LISTA``) calza con la lista entera, llaves incluidas; ``{ID[k]}`` es el elemento k
de un id cuyo valor es una tupla armada por posiciones (``BANDAS_KM``). Todo lo demás de la fila es literal: si el
texto cambia fuera de los números, la traducción falla en vez de desviarse.

Lecturas propias (UMB-n), para el addendum de M1:
- UMB-1. ``HR_SAT`` aparece tres veces en la fila «Rachas» («HR < 100», «HR = 100» de Td y «HR = 100 y calma») y dos en
  «Td y HR» («(100, 103] → 100»). El Anexo P dice «dos veces» en Rachas; la fila tiene tres, y las tres son la
  saturación. La traducción exige que todas valgan lo mismo, también entre grupos (como ``SEMILLA``, ``SEL_MOD`` y
  ``SEL_RESTO``).
- UMB-2. ``BANDAS_KM`` = (10, 25, 50): los cortes de «0-10, 10-25, 25-50 y > 50 km»; cada corte aparece dos veces y el
  0 inicial es literal (el origen de las distancias).
- UMB-3. Quedan literales, como dice el Anexo P: «§2.3», «marca 14», «K3», «T2a», «T2b», «K4», «s/p = 0», «rapidez > 0»,
  «u = v = 0», «360» y «0» de la regla del cero, «→ 0» del TPI, «½», «TF en §5.7», «int16», «P2», «M1», «P95», «w_ghs»,
  «rama 3» y «[M0, A3]»/«[M0, B8]». La fila «Decisión» no tiene ids: se compara entera como texto.
- UMB-4. ``CD_T`` es el sumando de CD en la temperatura y en la rapidez («+ 0,05 K o m/s»); ``NIVEL_MULT`` es el factor
  del nivel agudo y de la anomalía crónica («nivel agudo y anomalía crónica 1,15×»); ``F_1H``/``DT_1H`` y
  ``F_23H``/``DT_23_DESDE``/``DT_23_HASTA`` son el factor f y su Δt.
- UMB-5. Los valores se guardan como los escribe el Anexo A: ``QTS_MIN`` = −39 (entero) aunque §2.3 escriba «−39,0»;
  ``QQFE_BAJO`` = −80 y ``QQFE_ALTO`` = 50 son desplazamientos respecto de p_std(z_s). Quien escribe una regla
  ``quality`` los pasa a ``float`` de Python (§2.1, «Números de Python»).
- UMB-6. ``opciones_m0`` no sale del Anexo A (MC-35): ``regenerar_desde_texto`` lo recibe por argumento;
  ``cargar_umbrales`` usa el del JSON y la comparación con ``OPCIONES_M0`` de ``m0/preparar_m0.py`` se hace aparte (por
  AST, ``fijados.opciones_m0``).
- UMB-7. Hallazgo m-8: el JSON se regenera desde el v2.1, su fuente declarada en ``generado_desde``, y ``cargar_m0``
  comprueba que la sección del Anexo A del texto vigente es idéntica, byte a byte, a la del v2.1 (``seccion_anexo_a``).
  ``Umbrales.sha256_texto`` es la del v2.1 (la fuente del JSON) y ``sha256_texto_vigente`` la del texto vigente.
- UMB-13. **El texto vigente es el v2.3** (desde el 2026-10-27): el v2.2 con la Enmienda 2 del producto (EMC2-1, en
  §2.5), anclada en APH ``dd6c1c6`` con su sello en ``e3f9f97``. Antes era el v2.2 (f059c14c…, Enmienda 1). El Anexo A
  del v2.3 es byte a byte el del v2.2 y el del v2.1, así que ningún umbral cambia y el JSON de M0 sigue valiendo.
- UMB-8. La regeneración es más estricta que ``preparar_m0`` sin cambiar su resultado: los marcadores de sección deben
  aparecer una sola vez y toda línea «|» de la sección debe tener dos celdas (o ser la cabecera o el separador).
- UMB-9. **Signos fijos por id.** Un número de una plantilla no admite signo, salvo los ids negativos del texto
  (``IDS_NEGATIVOS``: QTS_MIN, QTD_MIN, QQFE_BAJO, CENT_TS, GAMMA_K_KM y FMT_RELLENO), que exigen «−», y QQFE_ALTO, que
  exige «+» («−80/+50»). Así «Γ = +6,5», «−80/50» o «12 + +12» no calzan.
- UMB-10. **Listas.** Llevan «, » si todos sus elementos son enteros y «; » si alguno lleva decimales (§4.2 del
  diseño), y tienen el largo del texto (``LARGO_LISTAS``: L 5, λ 3, κ 4 y α 5; las 60 combinaciones de §4.2 son
  5 × 3 × 4). Una lista de otro largo, o «{0; 50; 150}», no calza: es un cambio de la fila fuera de los números.
- UMB-11. Los nombres son los del Anexo P: ``QFF_MIN`` y ``QFF_MAX`` son la **rapidez** del viento (FF, en m/s: «rapidez
  0 a 50 m/s»), y ``QQFF_MIN`` y ``QQFF_MAX`` la **presión** QFF (920 a 1.065 hPa). No se renombran, porque el Anexo P es
  el contrato con los demás módulos.
- UMB-12. ``SECO_HR_PCT`` (HR < 2 %) es un umbral de HR en puntos de porcentaje, no una fracción de horas: ``U.frac`` lo
  rechaza (``U.a`` da 2, para comparar con la HR en %). Los demás ``*_PCT`` son fracciones de horas, meses, estaciones,
  artefactos, celdas o del intervalo, y ``U.frac`` los divide por 100.
Depende de: nada del paquete (biblioteca estándar); no importa numpy ni pandas.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

ESQUEMA_JSON = "meteo-combinada-umbrales/1"
SHA_JSON_M0 = "156587f195f77009fe49bfa9497fd4a334d6b4bbe14064b46b8f3d3bca5e488a"
SHA_TEXTO_M0 = "0d0972d8c8ebf09bb39bf45154496e72b524cdb8d57f9ce029aa53a16708edaf"
SHA_TEXTO_VIGENTE = "b4175f785ec57811702352d9d063164a5dce05f325a48c327a6d554a09ceddc2"   # v2.3 (Enmienda 2; UMB-13)
SHA_PREPARAR_M0 = "49503a3a88a9b9b331d8f51704708a7154bfc311a1f4a0eb6ca1f22d2f255d81"

# Archivos anclados, relativos a APH (sólo se leen).
TEXTO_M0 = "auditoria/20261023/meteo_combinada/m0/PROTOCOLO_METEO_COMBINADA_v2.1.md"
JSON_M0 = "auditoria/20261023/meteo_combinada/m0/meteo_combinada_v1.json"
PREPARAR_M0 = "auditoria/20261023/meteo_combinada/m0/preparar_m0.py"
TEXTO_VIGENTE = "auditoria/20261023/meteo_combinada/enmienda2/PROTOCOLO_METEO_COMBINADA_v2.3.md"

# Marcadores de la sección del Anexo A y texto literal de m0/preparar_m0.anexo_a (la «nota» del JSON).
INICIO_ANEXO_A = "## Anexo A."
FIN_ANEXO_A = "## Anexo B."
NOTA_JSON = ("Generado del Anexo A del texto de M0. Manda el texto: M1 regenera este JSON y lo compara. Los valores se "
             "guardan como texto literal (con las barras escapadas del original); M1 los traduce a valores y comprueba "
             "cada uno contra esta fila. Los fijos del cuerpo van al anexo A2 que genera M1 (§10).")
N_FILAS = 27

# Grupo del Anexo A → plantilla con {ID} (Anexo P del diseño), en el orden de la tabla.
PLANTILLAS: dict[str, str] = {
    "Rangos `quality`": (
        "§2.3 (Ts {QTS_MIN} a {QTS_MAX} °C; Td {QTD_MIN} a {QTD_MAX} °C; HR {QHR_MIN} a {QHR_MAX} %; rapidez "
        "{QFF_MIN} a {QFF_MAX} m/s; dirección {QDD_MIN} a {QDD_MAX}; QFE p_std(z_s) {QQFE_BAJO}/{QQFE_ALTO} hPa; QFF "
        "{QQFF_MIN} a {QQFF_MAX} hPa)"),
    "Centinelas": "Ts {CENT_TS}; QFE {CENT_QFE} (tolerancia {CENT_TOL})",
    "Rachas": (
        "{RACHA_H} h (Ts, QFE, QFF, HR < {HR_SAT}, Td sin las horas con HR = {HR_SAT}, viento con rapidez > 0); "
        "{RACHA_LARGA_H} h (HR = {HR_SAT} y calma); ≥ {RACHA_MIN_REPORTES} reportes; consecutivos a ≤ {CONSECUTIVO_H} h"),
    "Picos (θ)": (
        "Ts {PICO_TS} K; Td {PICO_TD} K; QFE y QFF {PICO_P} hPa; rapidez {PICO_FF} m/s; f = {F_1H} ({DT_1H} h) o "
        "{F_23H} ({DT_23_DESDE}-{DT_23_HASTA} h); salto único {SALTO_MULT}θ"),
    "Td y HR": (
        "Td − Ts > {TD_TS_INV} K invalida; ≤ {TD_TS_INV} recorta; incoherencia {INCOH_TD} K y {INCOH_HR} puntos, agua "
        "o hielo bajo {CERO_C} °C; HR ({HR_SAT}, {HR_RECORTE_MAX}] → {HR_SAT}; HR < {SECO_HR_PCT} % durante ≥ {SECO_H} "
        "h invalida"),
    "Viento": (
        "cero como norte si no hay 360 y el 0 está en ≥ {CERO_NORTE_PCT} % de las horas con rapidez > 0; calma sin "
        "dirección → u = v = 0"),
    "Error grueso": (
        "T {EG_T} K, Td {EG_TD} K, p {EG_P} hPa o {EG_MULT}·{EG_MAD_K}·MAD; ≥ {EG_MIN_N} valores por (s, m, h), si no "
        "(s, m); aislado < {EG_CORTO_H} h invalida; {EG_CORTO_H}-{EG_LARGO_H} h marca; > {EG_LARGO_H} h invalida"),
    "Altitud": "marca 14: {ALT_QFE_HPA} hPa; K3: {K3_DZ_M} m dentro de ρ ∈ [{RHO_MIN_KM}; {RHO_MAX_KM}] km",
    "Traslados": (
        "{K4_T2A_M} m (T2a); {K4_T2B_HPA} hPa (T2b); ≥ {K4_MIN_MES_HORA} valores por mes-hora; horas en ≥ "
        "{K4_HORAS_PCT} % de los meses; {K4_VENTANA} + {K4_VENTANA} meses con ≥ {K4_MIN_LADO} por lado; ≥ "
        "{K4_MIN_PARES} pares por mes; ≤ {K4_MAX_QUIEBRES} quiebres; tramos ≥ {K4_TRAMO_MIN} meses; coincidencia ± "
        "{K4_COINC_MESES} meses y máx({K4_COINC_M} m; {K4_COINC_FRAC}·\\|Δz_b\\|)"),
    "Tramos homogéneos": "{HOM_T} K (T); {HOM_TD} K (Td); el detector de K4",
    "RR06": "s/p = 0; válido en [{RR_MIN}, {RR_MAX}] mm",
    "Alarmas": (
        "Q1 {Q1_PCT} % de la red; Q1z {Q1Z_PCT} % de una macrozona; Q2 {Q2_PCT} % en {Q2_DESDE}-{Q2_HASTA} o "
        "{Q2Z_PCT} % de una macrozona; Q3 {Q3_PCT} % de los artefactos; lista con > {LISTA_PCT} %"),
    "Fondo": (
        "Γ = {GAMMA_K_KM} K/km; Td por conservación de q; z_E5L: geopotencial, NASADEM con ≥ {ZE5L_NASADEM_PCT} % de "
        "huella o hipsométrica; vecino ≤ {VECINO_KM} km"),
    "Núcleo": "L {NUC_L} km; λ {NUC_LAMBDA}; κ {NUC_KAPPA}; corte {NUC_CORTE}L; {NUC_VECINOS} vecinos",
    "A": (
        "ventana de ±{A_VENTANA_MESES} mes; armónicos {A_P1_H} y {A_P2_H} h (y {A_P3_H} h con ≥ {A_HORAS_K3} horas); "
        "recorte del {A_RECORTE_PCT} %; ≥ {A_MIN_N} valores de ≥ {A_MIN_ANIOS} años; hueco ≤ {A_HUECO_H} h"),
    "B y AB": "interpolación del residuo entre reportes a ≤ {B_INTERP_H} h",
    "C y C_est": (
        "α {C_ALFAS}; ≤ {C_FILAS} h por estación; peso ≤ {C_PESO_MAX}; cobertura del suelo de {C_ANIO_LULC}; TPI con "
        "< {C_TPI_PCT} % de dato → 0"),
    "Selección anidada": (
        "{SEL_PLIEGUES} pliegues internos de bloques de {SEL_BLOQUE_KM} km (amortiguador de {SEL_AMORT_KM} km en los "
        "de P2); días con mód {SEL_MOD} = {SEL_RESTO} (mód {SEL_MOD_RECORTE} si M1 proyecta > {SEL_UMBRAL_H} h); "
        "semilla {SEMILLA}"),
    "P1 / P2": (
        "{P1_PLIEGUES} pliegues de grupos a ≤ {GRUPO_KM} km / bloques de {P2_BLOQUE_KM} km con amortiguador de "
        "{P2_AMORT_KM} km"),
    "Mínimos": (
        "{MIN_HORAS} h; día con ≥ {DIA_MIN_H} h y hueco ≤ {DIA_HUECO_H} h; estrato agudo con ≥ {AGUDO_MIN_DIAS} días; "
        "año con ≥ {ANIO_MIN_DIAS} días; ≥ {MIN_ANIOS} años (≥ {MIN_ANIOS_ANOM} para la anomalía); extremos con ≥ "
        "{EX_MIN_DIAS} días"),
    "Pesos": (
        "bandas 0-{BANDAS_KM[0]}, {BANDAS_KM[0]}-{BANDAS_KM[1]}, {BANDAS_KM[1]}-{BANDAS_KM[2]} y > {BANDAS_KM[2]} km; "
        "bandas con < {BANDA_MIN_EVAL} evaluaciones se unen; ambiental ½ monitores + ½ población"),
    "Soporte": "estrato sin soporte en > {SOPORTE_PCT} % de las horas: no se publica ni entra a compuertas",
    "Remuestreo": "{BOOT_REPLICAS} réplicas por bloque de {BOOT_BLOQUE_KM} km, P1 y P2 juntos; semilla {SEMILLA}",
    "Compuertas": (
        "CD {CD_MULT}× + {CD_T} K o m/s, + {CD_HR} puntos (HR), + {CD_P} hPa; EX + {EX_T} K / {EX_TD} K / {EX_HR} "
        "puntos / {EX_FF} m/s; MZ {MZ_MULT}× con ≥ {MZ_MIN_EST} estaciones; nivel agudo y anomalía crónica "
        "{NIVEL_MULT}×; TF en §5.7"),
    "Decisión": (
        "menor S en E1; empate exacto A, AB, B, C (C_est en lo crónico); E1 vacío: menor S entre los que pasan TF; "
        "crónico, si ni B ni AB están en E1 y al menos uno falla TF o deriva: compiten A y C_est (menor S en E1; si "
        "ninguno está, en E0) [M0, B8]"),
    "Formato": (
        "int16, relleno {FMT_RELLENO}; T y Td {FMT_ESC_T} °C; u y v {FMT_ESC_UV} m/s; p {FMT_ESC_P} hPa con "
        "desplazamiento {FMT_DESP_P} hPa"),
    "M6 (Anexo B)": (
        "LightGBM con N = {M6_N} y {M6_REPLICAS} réplicas; B = {M6_B} réplicas; IC percentil del {M6_IC_PCT} %; NMB + "
        "{M6_NMB_PP} punto porcentual; TF de contaminantes con hasta {M6_CELDAS_COMUNA} celdas por comuna, con "
        "probabilidad proporcional a w_ghs, días con mód {SEL_MOD} = {SEL_RESTO}, semilla {SEMILLA}, media ponderada "
        "de \\|Δ_c\\| ≤ {M6_TF_MEDIA_PCT} % y P95 ≤ {M6_TF_P95_PCT} % de la media nacional ponderada "
        "{M6_TF_DESDE}-{M6_TF_HASTA} del escenario completo; rama 3 sólo en los grupos con B o AB [M0, A3]"),
}
# Ids cuyo valor es una lista entre llaves (vuelven como tupla) y su largo en el texto (UMB-10).
IDS_LISTA = ("NUC_L", "NUC_LAMBDA", "NUC_KAPPA", "C_ALFAS")
LARGO_LISTAS = {"NUC_L": 5, "NUC_LAMBDA": 3, "NUC_KAPPA": 4, "C_ALFAS": 5}
# Signo que exige cada id (UMB-9); los demás no admiten signo.
IDS_NEGATIVOS = ("QTS_MIN", "QTD_MIN", "QQFE_BAJO", "CENT_TS", "GAMMA_K_KM", "FMT_RELLENO")
SIGNO = {**{i: "−" for i in IDS_NEGATIVOS}, "QQFE_ALTO": "+"}
# ``*_PCT`` que no son fracciones (UMB-12).
PCT_NO_FRACCION = {"SECO_HR_PCT": "es un umbral de HR en puntos de porcentaje (HR < 2 %), no una fracción"}

NUMERO_DEL_TEXTO = r"[−+]?\d+(?:\.\d{3})*(?:,\d+)?"       # «−39», «+50», «1.065», «0,05», «20261023»
_SIN_SIGNO = r"\d+(?:\.\d{3})*(?:,\d+)?"
_ENTERO = r"\d+(?:\.\d{3})*"


def _regex_lista(n: int) -> str:
    return rf"\{{(?:{_ENTERO}(?:, {_ENTERO}){{{n - 1}}}|{_SIN_SIGNO}(?:; {_SIN_SIGNO}){{{n - 1}}})\}}"


def _regex_numero(ident: str) -> str:
    signo = SIGNO.get(ident)
    return _SIN_SIGNO if signo is None else re.escape(signo) + _SIN_SIGNO
_MARCADOR = re.compile(r"\{([A-Z][A-Z0-9_]*)(?:\[(\d+)\])?\}")
_CELDA = re.compile(r"(?<!\\)\|")


class ErrorUmbrales(ValueError):
    """El JSON no coincide con el texto, una plantilla no calza o un id no existe."""


# ---------------------------------------------------------------------------------------------
# Plantillas

def _ids_de_plantilla(plantilla: str) -> list[tuple[str, int | None]]:
    return [(m.group(1), None if m.group(2) is None else int(m.group(2))) for m in _MARCADOR.finditer(plantilla)]


def _regex_de_plantilla(plantilla: str) -> tuple[re.Pattern, list[tuple[str, str, int | None]]]:
    """Patrón de la fila y, por grupo con nombre, (grupo, id, índice)."""
    partes, grupos, pos = [], [], 0
    for n, m in enumerate(_MARCADOR.finditer(plantilla)):
        ident, k = m.group(1), m.group(2)
        nombre = f"g{n}"
        partes.append(re.escape(plantilla[pos:m.start()]))
        partes.append(f"(?P<{nombre}>{_regex_lista(LARGO_LISTAS[ident]) if ident in IDS_LISTA else _regex_numero(ident)})")
        grupos.append((nombre, ident, None if k is None else int(k)))
        pos = m.end()
    partes.append(re.escape(plantilla[pos:]))
    return re.compile("".join(partes)), grupos


def _comprobar_plantillas() -> tuple[str, ...]:
    """Ids de PLANTILLAS en orden de primera aparición; ErrorUmbrales si una plantilla está mal formada."""
    ids: list[str] = []
    for grupo, plantilla in PLANTILLAS.items():
        for ident, k in _ids_de_plantilla(plantilla):
            if k is not None and ident in IDS_LISTA:
                raise ErrorUmbrales(f"{grupo}: la lista {ident} no admite índice")
            if ident not in ids:
                ids.append(ident)
    if len(PLANTILLAS) != N_FILAS:
        raise ErrorUmbrales(f"PLANTILLAS tiene {len(PLANTILLAS)} grupos; el Anexo A, {N_FILAS}")
    return tuple(ids)


IDS = _comprobar_plantillas()
_REGEX = {grupo: _regex_de_plantilla(p) for grupo, p in PLANTILLAS.items()}


# ---------------------------------------------------------------------------------------------
# Números

def numero_del_texto(token: str) -> int | float:
    """«−39» → -39; «1.065» → 1065; «0,05» → 0.05; «+50» → 50; sin coma da int."""
    if not isinstance(token, str) or re.fullmatch(NUMERO_DEL_TEXTO, token) is None:
        raise ErrorUmbrales(f"número mal escrito para el texto: {token!r}")
    negativo = token.startswith("−")
    cuerpo = token.lstrip("−+").replace(".", "")
    valor: int | float = float(cuerpo.replace(",", ".")) if "," in cuerpo else int(cuerpo)
    return -valor if negativo else valor


def _lista_del_texto(token: str) -> tuple:
    """«{10, 25, 50}» o «{0,05; 0,2}»: «, » entre enteros y «; » si algún elemento lleva decimales (UMB-10)."""
    cuerpo = token[1:-1] if token.startswith("{") and token.endswith("}") else None
    if cuerpo is None or not cuerpo:
        raise ErrorUmbrales(f"lista mal escrita para el texto: {token!r}")
    separador = "; " if "; " in cuerpo else ", "
    elementos = cuerpo.split(separador)
    if any(re.fullmatch(_SIN_SIGNO, x) is None for x in elementos):
        raise ErrorUmbrales(f"lista mal escrita para el texto: {token!r}")
    if (separador == ", ") == any("," in x for x in elementos):
        raise ErrorUmbrales(f"lista con el separador equivocado (UMB-10): {token!r}")
    return tuple(numero_del_texto(x) for x in elementos)


# ---------------------------------------------------------------------------------------------
# Objeto de umbrales

def _congelar(obj: Any) -> Any:
    if isinstance(obj, Mapping):
        return MappingProxyType({k: _congelar(v) for k, v in obj.items()})
    if isinstance(obj, (list, tuple)):
        return tuple(_congelar(v) for v in obj)
    return obj


def _a_json(obj: Any) -> Any:
    if isinstance(obj, Mapping):
        return {k: _a_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_a_json(v) for v in obj]
    return obj


@dataclass(frozen=True)
class Umbrales:
    """Umbrales de una corrida (todos fijos). Inmutable."""
    valores: Mapping[str, Any]
    sha256_json: str = ""
    sha256_texto: str = ""                 # el texto del que sale el JSON (v2.1, UMB-7)
    opciones_m0: Mapping[str, Any] = field(default_factory=dict)
    sha256_texto_vigente: str = ""         # el texto vigente (v2.3), cuyo Anexo A se comprobó idéntico (m-8)

    def __post_init__(self) -> None:
        if tuple(self.valores) != IDS:
            raise ErrorUmbrales("los valores no son exactamente los ids de PLANTILLAS, en orden")
        for ident, v in self.valores.items():
            for x in (v if isinstance(v, (tuple, list)) else (v,)):
                if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
                    raise ErrorUmbrales(f"umbral {ident} no numérico: {v!r}")
        object.__setattr__(self, "valores", _congelar(dict(self.valores)))
        object.__setattr__(self, "opciones_m0", _congelar(dict(self.opciones_m0)))

    def a(self, ident: str) -> int | float | tuple:
        """Valor de un id del Anexo P; ErrorUmbrales si no existe."""
        if ident not in self.valores:
            raise ErrorUmbrales(f"umbral desconocido: {ident!r}")
        return self.valores[ident]

    def frac(self, ident: str) -> float:
        """Sólo ids ``*_PCT``: valor/100."""
        if not ident.endswith("_PCT"):
            raise ErrorUmbrales(f"frac sólo vale para ids *_PCT, no para {ident!r}")
        if ident in PCT_NO_FRACCION:
            raise ErrorUmbrales(f"frac no vale para {ident}: {PCT_NO_FRACCION[ident]}; use U.a (UMB-12)")
        return self.a(ident) / 100

    def vigentes(self) -> dict[str, Any]:
        """Valores (listas como listas) y opciones de M0, para el recibo y el addendum."""
        return {"valores": _a_json(self.valores), "opciones_m0": _a_json(self.opciones_m0)}

    def huella(self) -> str:
        """sha256 del JSON canónico de ``vigentes()`` (claves ordenadas, «,» y «:», UTF-8, sin NaN)."""
        datos = json.dumps(self.vigentes(), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                           allow_nan=False).encode("utf-8")
        return hashlib.sha256(datos).hexdigest()


# ---------------------------------------------------------------------------------------------
# Regeneración y comparación (§4.3 del diseño)

def _sha256_bytes(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def seccion_anexo_a(texto: str) -> str:
    """El texto desde «## Anexo A.» hasta «## Anexo B.», como ``preparar_m0.seccion`` (marcadores únicos)."""
    for marca in (INICIO_ANEXO_A, FIN_ANEXO_A):
        if texto.count(marca) != 1:
            raise ErrorUmbrales(f"{marca!r} aparece {texto.count(marca)} veces en el texto")
    a = texto.index(INICIO_ANEXO_A)
    try:
        b = texto.index(FIN_ANEXO_A, a + len(INICIO_ANEXO_A))
    except ValueError as e:
        raise ErrorUmbrales("«## Anexo B.» no sigue al Anexo A") from e
    return texto[a:b]


def filas_anexo_a(texto: str) -> list[dict]:
    """Las 27 filas {grupo, texto} del Anexo A, partidas por «|» no escapadas (algoritmo de preparar_m0.anexo_a)."""
    filas = []
    for linea in seccion_anexo_a(texto).splitlines():
        if not linea.startswith("|"):
            continue
        celdas = [c.strip() for c in _CELDA.split(linea.strip())[1:-1]]
        if celdas and (celdas[0] == "Grupo" or set(celdas[0]) <= {"-"}):
            continue
        if len(celdas) != 2:
            raise ErrorUmbrales(f"fila del Anexo A sin dos celdas: {linea!r}")
        filas.append({"grupo": celdas[0], "texto": celdas[1]})
    if len(filas) != N_FILAS or len({f["grupo"] for f in filas}) != N_FILAS:
        raise ErrorUmbrales(f"el Anexo A trae {len(filas)} filas y {len({f['grupo'] for f in filas})} grupos; "
                            f"se esperan {N_FILAS}")
    return filas


def regenerar_desde_texto(texto: str, nombre_archivo: str, sha256_texto: str, opciones_m0: dict) -> dict:
    """El JSON desde el Anexo A del texto, con el algoritmo de ``m0/preparar_m0.anexo_a`` (MC-35: ``opciones_m0``
    llega por argumento). ``sha256_texto`` debe ser la del texto en UTF-8."""
    if _sha256_bytes(texto.encode("utf-8")) != sha256_texto:
        raise ErrorUmbrales("sha256_texto no es la huella del texto que se regenera")
    return {"schema": ESQUEMA_JSON,
            "generado_desde": {"archivo": nombre_archivo, "sha256": sha256_texto},
            "nota": NOTA_JSON,
            "anexo_a": filas_anexo_a(texto), "opciones_m0": dict(opciones_m0)}


def serializar(obj: dict) -> bytes:
    """Los bytes que escribe ``preparar_m0``: ``json.dumps(…, ensure_ascii=False, indent=1)`` más un salto."""
    return (json.dumps(obj, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def _diferencias(ruta: str, a: Any, b: Any, salida: list[str]) -> None:
    if type(a) is not type(b):
        salida.append(f"{ruta}: tipo {type(a).__name__} en el publicado, {type(b).__name__} en el regenerado "
                      f"({a!r} ≠ {b!r})")
    elif isinstance(a, dict):
        for k in a.keys() - b.keys():
            salida.append(f"{ruta}.{k}: sólo en el publicado")
        for k in b.keys() - a.keys():
            salida.append(f"{ruta}.{k}: sólo en el regenerado")
        comunes = [k for k in a if k in b]
        if comunes != [k for k in b if k in a]:
            salida.append(f"{ruta}: claves en otro orden ({comunes} ≠ {[k for k in b if k in a]})")
        for k in comunes:
            _diferencias(f"{ruta}.{k}", a[k], b[k], salida)
    elif isinstance(a, list):
        if len(a) != len(b):
            salida.append(f"{ruta}: {len(a)} elementos en el publicado, {len(b)} en el regenerado")
        for i, (x, y) in enumerate(zip(a, b)):
            _diferencias(f"{ruta}[{i}]", x, y, salida)
    elif a != b:
        salida.append(f"{ruta}: {a!r} en el publicado ≠ {b!r} en el regenerado")


def comparar(publicado: dict, regenerado: dict) -> list[str]:
    """Diferencias estrictas (tipos, listas en orden y orden de claves); lista vacía si coinciden."""
    salida: list[str] = []
    _diferencias("$", publicado, regenerado, salida)
    return salida


def traducir(filas_anexo_a: list[dict]) -> dict[str, int | float | tuple]:
    """Filas del Anexo A → valores por id, con ``PLANTILLAS`` y ``re.fullmatch``; un id repetido vale lo mismo en cada
    aparición (también entre grupos). ErrorUmbrales si una fila no calza o los grupos no son los de PLANTILLAS."""
    grupos = [f.get("grupo") for f in filas_anexo_a]
    if grupos != list(PLANTILLAS):
        raise ErrorUmbrales(f"grupos del Anexo A distintos de PLANTILLAS (o en otro orden): {grupos}")
    vistos: dict[str, Any] = {}
    indexados: dict[str, dict[int, Any]] = {}
    for fila in filas_anexo_a:
        grupo, texto = fila["grupo"], fila.get("texto")
        patron, nombres = _REGEX[grupo]
        m = patron.fullmatch(texto) if isinstance(texto, str) else None
        if m is None:
            raise ErrorUmbrales(f"la fila «{grupo}» no calza con su plantilla:\n  texto:     {texto!r}\n"
                                f"  plantilla: {PLANTILLAS[grupo]!r}")
        for nombre, ident, k in nombres:
            token = m.group(nombre)
            valor = _lista_del_texto(token) if ident in IDS_LISTA else numero_del_texto(token)
            if k is None:
                if ident in vistos and (vistos[ident] != valor or type(vistos[ident]) is not type(valor)):
                    raise ErrorUmbrales(f"{ident} vale {vistos[ident]!r} y también {valor!r}")
                vistos[ident] = valor
            else:
                previo = indexados.setdefault(ident, {}).get(k)
                if previo is not None and (previo != valor or type(previo) is not type(valor)):
                    raise ErrorUmbrales(f"{ident}[{k}] vale {previo!r} y también {valor!r}")
                indexados[ident][k] = valor
    for ident, partes in indexados.items():
        if sorted(partes) != list(range(len(partes))):
            raise ErrorUmbrales(f"{ident}: índices {sorted(partes)} incompletos")
        vistos[ident] = tuple(partes[k] for k in range(len(partes)))
    return {ident: vistos[ident] for ident in IDS}


def _cargar_json_estricto(datos: bytes) -> dict:
    def sin_duplicados(pares):
        claves = [k for k, _ in pares]
        repetidas = sorted({k for k in claves if claves.count(k) > 1})
        if repetidas:
            raise ErrorUmbrales(f"claves repetidas en el JSON: {repetidas}")
        return dict(pares)

    def sin_no_finitos(token):
        raise ErrorUmbrales(f"valor no finito en el JSON: {token}")

    try:
        obj = json.loads(datos.decode("utf-8"), object_pairs_hook=sin_duplicados, parse_constant=sin_no_finitos)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ErrorUmbrales(f"JSON ilegible: {e}") from e
    if not isinstance(obj, dict):
        raise ErrorUmbrales("el JSON de umbrales no es un objeto")
    return obj


def _leer_texto(ruta: Path) -> tuple[str, str]:
    datos = Path(ruta).read_bytes()
    try:
        return datos.decode("utf-8"), _sha256_bytes(datos)     # sin traducir saltos de línea
    except UnicodeDecodeError as e:
        raise ErrorUmbrales(f"{Path(ruta).name} no es UTF-8: {e}") from e


def cargar_umbrales(ruta_json, ruta_texto, *, sha256_json: str | None = None) -> Umbrales:
    """Lee el JSON (con su sha256, si se da), lo regenera desde el texto, exige ``comparar(...) == []`` y traduce
    las filas. ``opciones_m0`` es la del JSON (UMB-6)."""
    datos = Path(ruta_json).read_bytes()
    huella = _sha256_bytes(datos)
    if sha256_json is not None and huella != sha256_json:
        raise ErrorUmbrales(f"sha256 del JSON de umbrales {huella} ≠ esperado {sha256_json}")
    publicado = _cargar_json_estricto(datos)
    if publicado.get("schema") != ESQUEMA_JSON:
        raise ErrorUmbrales(f"esquema {publicado.get('schema')!r}; se espera {ESQUEMA_JSON!r}")
    opciones = publicado.get("opciones_m0")
    if not isinstance(opciones, dict):
        raise ErrorUmbrales("el JSON no trae opciones_m0")
    texto, sha_texto = _leer_texto(Path(ruta_texto))
    regenerado = regenerar_desde_texto(texto, Path(ruta_texto).name, sha_texto, opciones)
    diferencias = comparar(publicado, regenerado)
    if diferencias:
        raise ErrorUmbrales("el JSON de umbrales no coincide con el Anexo A:\n  " + "\n  ".join(diferencias))
    if serializar(regenerado) != datos:
        raise ErrorUmbrales("el JSON regenerado no es byte a byte el publicado")
    return Umbrales(valores=traducir(publicado["anexo_a"]), sha256_json=huella, sha256_texto=sha_texto,
                    opciones_m0=opciones)


def cargar_m0(aph) -> Umbrales:
    """JSON y texto de M0 (con sus huellas), más la comprobación de que el Anexo A del texto vigente (v2.3) es
    idéntico (m-8)."""
    aph = Path(aph)
    texto_m0, sha_m0 = _leer_texto(aph / TEXTO_M0)
    if sha_m0 != SHA_TEXTO_M0:
        raise ErrorUmbrales(f"sha256 del texto de M0 {sha_m0} ≠ anclado {SHA_TEXTO_M0}")
    vigente, sha_vigente = _leer_texto(aph / TEXTO_VIGENTE)
    if sha_vigente != SHA_TEXTO_VIGENTE:
        raise ErrorUmbrales(f"sha256 del texto vigente {sha_vigente} ≠ anclado {SHA_TEXTO_VIGENTE}")
    if seccion_anexo_a(vigente) != seccion_anexo_a(texto_m0):
        raise ErrorUmbrales("el Anexo A del texto vigente no es idéntico al del v2.1 (hallazgo m-8)")
    U = cargar_umbrales(aph / JSON_M0, aph / TEXTO_M0, sha256_json=SHA_JSON_M0)
    return Umbrales(valores=U.valores, sha256_json=U.sha256_json, sha256_texto=U.sha256_texto,
                    opciones_m0=U.opciones_m0, sha256_texto_vigente=sha_vigente)
