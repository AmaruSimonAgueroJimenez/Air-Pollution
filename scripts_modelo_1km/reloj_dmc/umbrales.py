"""Umbrales del Anexo B: lectura de reloj_dmc_v1.json, comparación con el texto y ajuste de §8.F.

Regla del paquete: ningún umbral del Anexo B se escribe a mano en el código. Todo módulo los pide
a un objeto ``Umbrales``:
- ``U.a(id)``: ajustable (23 ids del JSON, p. ej. "E3P_MU"); devuelve el valor vigente
  (el anclado o el que dejó §8.F). Los pares (E1B_PATRON, E6_I12, E6_I15) vuelven como tupla.
- ``U.f(id)``: fijo, traducido del texto literal de ``fijos_texto`` con PLANTILLAS_FIJOS
  (124 ids); devuelve el valor tal como lo escribe el texto (10 para «10 %»).
- ``U.frac(id)``: sólo para ids ``*_PCT``; devuelve valor/100.

C1 (§10): ``regenerar_desde_texto`` rehace el JSON desde el Anexo B del texto consolidado y
``comparar`` exige igualdad con el JSON publicado. ``traducir_fijos`` exige que cada línea de
``fijos_texto`` calce entera (re.fullmatch) con su plantilla; así la traducción no puede
desviarse del texto.

§8.F: ``Umbrales.ajustado`` mueve un paso por la lista del Anexo B, nunca hacia atrás, y comprueba
que el paso vaya en el sentido conservador de SENTIDO_CONSERVADOR; ``siguiente_ajuste`` elige el
primer umbral no agotado de la línea, en el orden de las filas del Anexo B.

Las huellas se calculan con hashlib y el mismo JSON canónico que documenta entorno.json_canonico
(claves ordenadas, separadores «,» y «:», UTF-8, sin NaN); así este módulo no depende de E/S ajena.
Depende de: nada del paquete.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

ESQUEMA_JSON = "reloj-dmc-umbrales/1"
SHA_JSON_C0 = "3251a4d81a76f5066fc217557f279d428740898f6a2f26d6c8fbbfb721c77002"
SHA_PROTOCOLO_C0 = "5fff072783e932843d210561a46f5344351a39b7dd85f5775ac884eaf96e4d85"

# Archivos anclados en C0, relativos a APH (los lee la comparación de C1; nunca se escriben).
PROTOCOLO_C0 = "auditoria/20261023/reloj_dmc/PROTOCOLO_RELOJ_DMC_v1_propuesta.md"
JSON_C0 = "auditoria/20261023/reloj_dmc/c0/reloj_dmc_v1.json"

# Rótulo del párrafo que la Enmienda 1 (E1-5) agrega al final del Anexo B; no es una línea de fijos.
FIJOS_DEL_CUERPO = "**Fijos del cuerpo**"

# Texto literal de c0/preparar_c0.anexo_b (la «nota» del JSON); la regeneración la reproduce tal cual.
NOTA_JSON = ("Generado del Anexo B del texto adoptado. Manda el texto: C1 regenera este JSON y lo compara. "
             "Los fijos se guardan como texto literal; C1 los traduce a valores y los compara con este texto.")

IDS_AJUSTABLES = ("E3P_MU", "E3P_CONF", "E3P_TAU", "E3_RMAX", "E3P_FINA_TAU", "E3P_FINA_ESTAB",
                  "E3P_FINA_APAGADO", "E4P_COMPAT", "E4P_INCOMPAT", "E4P_A2_EE", "E2_KAPPA", "E2_MIN_RR",
                  "E1A_P", "E1A_P0", "E1A_PLACEBO", "E1B_PATRON", "E1C_COMPLETO", "E3T_MU", "E3T_TAU",
                  "E6_I12", "E6_I15", "TP_VENTANA", "TP_MARGEN")

# Línea → filas del Anexo B en orden (§8.F «el primer umbral no agotado de su lista»).
# cargar_umbrales comprueba que coincida con la columna «Línea» y el orden de la tabla.
FILAS_POR_LINEA = {
    "E3p": ("E3P_MU", "E3P_CONF", "E3P_TAU", "E3_RMAX", "E3P_FINA_TAU", "E3P_FINA_ESTAB", "E3P_FINA_APAGADO"),
    "E4p": ("E4P_COMPAT", "E4P_INCOMPAT", "E4P_A2_EE"),
    "E2": ("E2_KAPPA", "E2_MIN_RR"),
    "E1a": ("E1A_P", "E1A_P0", "E1A_PLACEBO"),
    "E1b": ("E1B_PATRON",),
    "E1c": ("E1C_COMPLETO",),
    "E3t": ("E3T_MU", "E3T_TAU"),
    "E6": ("E6_I12", "E6_I15"),
    "T-P": ("TP_VENTANA", "TP_MARGEN"),
}
# Líneas, guardas y marcas de §4 sin filas en el Anexo B: agotadas desde el principio (§8.F).
LINEAS_SIN_FILAS = ("E5", "E3d", "P7", "E4t", "G-version", "G-HR", "G-viento")

# Sentido en que el valor se vuelve más conservador (menos confirmaciones), leído del cuerpo del texto.
# +1: subir endurece; −1: bajar endurece. En los pares, por componente. No es un umbral: sólo permite
# comprobar que la lista del Anexo B y cada paso de §8.F vayan hacia lo conservador (§8.F, «Fin»).
SENTIDO_CONSERVADOR: Mapping[str, Any] = MappingProxyType({
    "E3P_MU": +1,            # §4.3.2: margen μ_p mayor, menos compatibles e incompatibles
    "E3P_CONF": +1,          # §4.3.2: fracción de réplicas exigida
    "E3P_TAU": -1,           # §4.3.2: tolerancia τ_c más estrecha
    "E3_RMAX": +1,           # §4.3.1: «sin información si máx r < …»
    "E3P_FINA_TAU": -1,      # §4.3.4: |ĉ^f_cont − ĉ^f| ≤ …
    "E3P_FINA_ESTAB": +1,    # §4.3.4: ĉ^f igual en ≥ … de las réplicas
    "E3P_FINA_APAGADO": -1,  # §4.3.4: la regla se apaga si la mediana supera …
    "E4P_COMPAT": -1,        # §4.4: compatible si δ ≤ …
    "E4P_INCOMPAT": +1,      # §4.4: incompatible si δ ≥ … (menos exclusiones)
    "E4P_A2_EE": +1,         # §4.4: sin información si A2/EE < …
    "E2_KAPPA": +1,          # §4.2: informativa con κ3 ≥ …
    "E2_MIN_RR": +1,         # §4.2: informativa con ≥ … marcas RR
    "E1A_P": +1,             # §4.1.1: ausente exige p ≥ …
    "E1A_P0": -1,            # §4.1.1: patrón civil con P0 ≤ …
    "E1A_PLACEBO": -1,       # §4.1.1: tasa de placebos ausentes ≤ …
    "E1B_PATRON": (+1, +1),  # §4.1.2: ≥ … de los evaluables y ≥ … cambios
    "E1C_COMPLETO": +1,      # §4.1.3: casillas completas en ≥ … de los meses
    "E3T_MU": +1,            # §4.3.2: margen μ_t
    "E3T_TAU": -1,           # §4.3.2: tolerancia τ_t
    "E6_I12": (+1, +1),      # §4.6: I12_H ≥ … e I12_H ≥ razón·I12_H′
    "E6_I15": (+1, +1),      # §4.6: I15_H ≥ … e I15_H ≥ razón·I15_H′
    "TP_VENTANA": +1,        # §4.7: T-P falla con |δt_R − k| ≤ … (falla más)
    "TP_MARGEN": -1,         # §4.7: T-P falla con r_t(…) − r_t(…) ≥ … (falla más)
})

# Una plantilla por línea de ``fijos_texto`` (33). Cada {ID} es un número escrito como en el texto:
# signo «−» (U+2212), miles con «.», decimales con «,». Verificadas contra el JSON de C0.
PLANTILLAS_FIJOS = (
    "- **Datos y control propio:**",
    "- Ts: {TS_CENTINELA}; [{TS_MIN}; {TS_MAX}] °C; {TS_DESVIO_MEDIANA} °C de la mediana del mes; racha de {TS_RACHA_H} h.",
    "- QFE: {QFE_CENTINELA}; [{QFE_MIN}; {QFE_MAX}] hPa; {QFE_DESVIO_MEDIANA} hPa; racha de {QFE_RACHA_H} h.",
    "- Viento: dirección en {VIENTO_DIR_MIN}-{VIENTO_DIR_MAX} y rapidez ≥ {VIENTO_RAPIDEZ_MIN}.",
    "- Coordenadas: {COORD_TOL_GRADOS}° y {COORD_TOL_M} m.",
    "- **Píxel:** {PIXEL_RADIO_KM} km; meses de validez {PIXEL_MES_VALIDEZ_1}, {PIXEL_MES_VALIDEZ_2} y {PIXEL_MES_VALIDEZ_3}; Δz de {E3D_DZ_TS_M} m para E3d en Ts.",
    "- **Mínimos:**",
    "- E3: {E3_PARES_PARTE} pares y {E3_BLOQUES_PARTE} bloques de {E3_DIAS_BLOQUE_PARTE} días por parte; {E3_PARES_REGIMEN} pares por año-régimen.",
    "- E2: observador en {E2_OBSERVADOR} de las filas con RR; TX y TN con {E2_TXTN_MIN} marcas y κ {E2_TXTN_KAPPA}.",
    "- E4: {E4_VALORES_HORA_PARTE} y {E4_VALORES_HORA_REGIMEN} valores por hora; hueco ≤ {E4_HUECO_MAX_H} h; n_h ≥ {E4P_NH_MIN} para E4p; A2 ≥ {E4P_A2_MIN_HPA} hPa; S2 a {E4P_S2_FASE_H} h; EE × {E4_EE_FACTOR}.",
    "- E1a: ΔTs {E1A_DTS_MAX} °C; día habitual {E1A_DIA_HABITUAL}; {E1A_DIAS_P14} días y {E1A_FECHAS_PDOM} fechas.",
    "- E1b: q de {E1B_Q_NOCHE} (en ≥ {E1B_ETIQ_NOCHE} etiquetas) y de {E1B_Q_DIA} (en ≥ {E1B_ETIQ_DIA}); ≥ {E1B_FILAS_DIA} filas por día; ventanas de {E1B_VENTANA_DESDE_D} a {E1B_VENTANA_HASTA_D} días con ≥ {E1B_DIAS_VENTANA} días; placebos a ±{E1B_PLACEBO_1_D} y ±{E1B_PLACEBO_2_D} días; |Δ| ≥ {E1B_PLACEBO_DELTA} en ≤ {E1B_PLACEBO_PCT} %.",
    "- E6: {E6_MIN_ANIO} y {E6_MIN_MES} coincidencias; ±{E6_TOL_MIN} min; {E6_DIST_KM} km.",
    "- **E3:** ventana ±{E3_VENTANA}; {E3_REPLICAS} réplicas; bloques de {E3_DIAS_BLOQUE} días; semilla {SEMILLA}.",
    "- **Filtro de E3t:** Δz {E3T_DZ_M} m; cociente de A1 en [{E3T_A1_MIN}; {E3T_A1_MAX}]; correlación diaria {E3T_R_DIARIA}.",
    "- **Calibración de E3t:** ≥ {CAL_E3T_MIN} estación-años; |δt| > {CAL_E3T_DELTA_H} h en ≤ {CAL_E3T_PCT} %.",
    "- **Subhorario:** |ρ| > {SUBH_RHO_H} h con ≥ {SUBH_MIN_REGIMENES} años-régimen.",
    "- **Guardas y marcas:**",
    "- E3d: {E3D_PARES_BLOQUE} pares por bloque; margen {E3D_MARGEN}.",
    "- P7: {P7_ETIQUETAS} etiquetas; factor {P7_FACTOR}; {P7_SALTO_C} °C; caída {P7_CAIDA}.",
    "- Marca «desfase térmico local»: |δt| > {DTL_DELTA_H} h.",
    "- E4t: A1 {E4T_A1_MIN_C} °C; A1/EE {E4T_A1_EE}; ventana [{E4T_VENTANA_DESDE_H}; {E4T_VENTANA_HASTA_H}] h.",
    "- G-versión: {GVER_MESES} meses por versión; estabilidad {GVER_ESTAB}; κ {GVER_KAPPA}.",
    "- G-HR: {GHR_HORAS} horas; A1(HR) {GHR_A1_HR} puntos; {GHR_DIST_H} h.",
    "- G-viento: {GVIENTO_HORAS} horas; r {GVIENTO_R}; margen {GVIENTO_MARGEN}.",
    "- **Decisión y rachas:** cobertura de mín({COBERTURA_MESES}, meses con datos); {RACHA_ANIOS_CAMBIO} años por racha junto a un cambio; cuarentena de {CUARENTENA_MESES} mes; vecindad de {VECINDAD_MESES} meses; inestabilidad con ≥ {INESTABLE_ANIOS} años y > {INESTABLE_PCT} %; cambio del portal con {PORTAL_PCT} %.",
    "- **Red:**",
    "- A3: {A3_FRAC_PAIS} en el país y {A3_FRAC_MACRO} en la macrozona; |D| ≤ {A3_D_MAX_H} h; |mediana| ≤ {A3_MEDIANA_MAX_H} h; ≥ {A3_MIN_REGIMENES} años-régimen; |lat| ≤ {A3_LAT_MAX}°.",
    "- A4: {A4_PCT} %.",
    "- A5: {A5_M_MAX_H} h con ≥ {A5_MIN_REGIMENES} años-régimen.",
    "- Descripción: N con ≥ {RED_MIN_ESTACIONES} estaciones; {RED_UTC_HORAS_PCT} % de estación-horas; {RED_UTC_DISCREP_PCT} % de discrepantes.",
    "- **C3:** {C3A_PSI2_TOL_H} h; φ1 de t2m en [{C3A_PHI1_DESDE_H}; {C3A_PHI1_HASTA_H}] h; {C3B_PIX_NORTE} + {C3B_PIX_SUR} píxeles; ruido de {C3B_RUIDO_C} °C y {C3B_RUIDO_HPA} hPa; una unidad recupera con {C3B_UNIDAD_PCT} % de sus años; {C3B_RECUP_PCT} % de recuperación; pares a {C3C_DIST_DESDE_KM}-{C3C_DIST_HASTA_KM} km con Δz ≤ {C3C_DZ_M} m; T-P sin fallar en ≥ {C3C_TP_PCT} %.",
    "- **Batería:** sensibilidad {BAT_SENSIBILIDAD}; razón civil {BAT_RAZON_CIVIL}; {BAT_CORRECTA_PCT} % de confirmación correcta; {BAT_MEDIA_HORARIA_PCT} % de marcas de media horaria; {BAT_HORAS_MAX} h.",
)
NUMERO_DEL_TEXTO = r"(−?\d+(?:\.\d{3})*(?:,\d+)?)"   # «−40,0», «1.100», «0,0005», «200001»

_MARCADOR = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")
_CANDIDATO_NUMERO = re.compile(r"[−+\-]?\d(?:[\d.,]*\d)?")
_CLAVES_AJUSTABLE = ("linea", "texto", "anclado", "lista_conservadora")


class ErrorUmbrales(ValueError):
    """El JSON no coincide con el texto, una plantilla no calza o un id no existe."""


# ---------------------------------------------------------------------------------------------
# Utilidades internas

def _sha256_bytes(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _json_canonico(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _congelar(obj: Any) -> Any:
    """Listas → tuplas y dicts → MappingProxyType, en profundidad (el objeto Umbrales es inmutable)."""
    if isinstance(obj, Mapping):
        return MappingProxyType({k: _congelar(v) for k, v in obj.items()})
    if isinstance(obj, (list, tuple)):
        return tuple(_congelar(v) for v in obj)
    return obj


def _a_json(obj: Any) -> Any:
    """Inverso de _congelar para serializar."""
    if isinstance(obj, Mapping):
        return {k: _a_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_a_json(v) for v in obj]
    return obj


def _ids_de_plantilla(plantilla: str) -> list[str]:
    return _MARCADOR.findall(plantilla)


def _regex_de_plantilla(plantilla: str) -> re.Pattern:
    partes, pos = [], 0
    for m in _MARCADOR.finditer(plantilla):
        partes.append(re.escape(plantilla[pos:m.start()]))
        partes.append(f"(?P<{m.group(1)}>{NUMERO_DEL_TEXTO[1:-1]})")
        pos = m.end()
    partes.append(re.escape(plantilla[pos:]))
    return re.compile("".join(partes))


def _comprobar_plantillas() -> tuple[str, ...]:
    """Ids de PLANTILLAS_FIJOS en orden; ErrorUmbrales si alguno se repite o choca con un ajustable."""
    ids = [i for p in PLANTILLAS_FIJOS for i in _ids_de_plantilla(p)]
    repetidos = sorted({i for i in ids if ids.count(i) > 1})
    if repetidos:
        raise ErrorUmbrales(f"ids repetidos en PLANTILLAS_FIJOS: {repetidos}")
    choque = sorted(set(ids) & set(IDS_AJUSTABLES))
    if choque:
        raise ErrorUmbrales(f"ids fijos que también son ajustables: {choque}")
    return tuple(ids)


IDS_FIJOS = _comprobar_plantillas()
_REGEX_FIJOS = tuple(_regex_de_plantilla(p) for p in PLANTILLAS_FIJOS)


def _un_numero(texto: str) -> int | float:
    """El único número de una celda («0,5 h», «2 cambios», «razón 5»); ErrorUmbrales si hay 0 o varios."""
    candidatos = _CANDIDATO_NUMERO.findall(texto)
    if len(candidatos) != 1:
        raise ErrorUmbrales(f"se esperaba un solo número en {texto!r}; hay {len(candidatos)}")
    return numero_del_texto(candidatos[0])


def _valor_de_celda(texto: str) -> int | float | list:
    """Un elemento de «Anclado → lista»: número, o par «(a; b)» (como c0/preparar_c0.numero)."""
    texto = texto.strip()
    if texto.startswith("("):
        if not texto.endswith(")"):
            raise ErrorUmbrales(f"par sin cerrar: {texto!r}")
        return [_un_numero(x) for x in texto[1:-1].split(";")]
    return _un_numero(texto)


def _seccion(texto: str, inicio: str, fin: str) -> str:
    try:
        a = texto.index(inicio)
        b = texto.index(fin, a + len(inicio))
    except ValueError as e:
        raise ErrorUmbrales(f"no se halló la sección entre {inicio!r} y {fin!r}") from e
    if texto.count(inicio) != 1:
        raise ErrorUmbrales(f"{inicio!r} aparece {texto.count(inicio)} veces en el texto")
    return texto[a:b]


def _componentes(valor: Any) -> tuple:
    return tuple(valor) if isinstance(valor, (list, tuple)) else (valor,)


def _paso_conservador(ident: str, antes: Any, despues: Any) -> bool:
    """True si ir de ``antes`` a ``despues`` es un paso hacia lo conservador según SENTIDO_CONSERVADOR."""
    sentido = _componentes(SENTIDO_CONSERVADOR[ident])
    a, d = _componentes(antes), _componentes(despues)
    if not (len(a) == len(d) == len(sentido)):
        return False
    pasos = [(y - x) * s for x, y, s in zip(a, d, sentido)]
    if len(sentido) == 1:
        return pasos[0] > 0
    return all(p >= 0 for p in pasos) and any(p > 0 for p in pasos)


def _comprobar_ajustables(ajustables: Mapping[str, Any]) -> None:
    """Ids, orden, línea y listas monótonas hacia lo conservador (§8.F)."""
    if tuple(ajustables) != IDS_AJUSTABLES:
        raise ErrorUmbrales(f"ids o orden de ajustables distintos de IDS_AJUSTABLES: {list(ajustables)}")
    if set(SENTIDO_CONSERVADOR) != set(IDS_AJUSTABLES):
        raise ErrorUmbrales("SENTIDO_CONSERVADOR no cubre exactamente los 23 ajustables")
    filas: dict[str, list[str]] = {}
    for ident, entrada in ajustables.items():
        if tuple(entrada) != _CLAVES_AJUSTABLE:
            raise ErrorUmbrales(f"{ident}: claves {list(entrada)}; se esperan {list(_CLAVES_AJUSTABLE)}")
        filas.setdefault(entrada["linea"], []).append(ident)
        secuencia = [entrada["anclado"], *entrada["lista_conservadora"]]
        for antes, despues in zip(secuencia, secuencia[1:]):
            if not _paso_conservador(ident, antes, despues):
                raise ErrorUmbrales(f"{ident}: la lista {entrada['texto']!r} no va hacia lo conservador "
                                    f"({antes!r} → {despues!r})")
    if {k: tuple(v) for k, v in filas.items()} != FILAS_POR_LINEA or list(filas) != list(FILAS_POR_LINEA):
        raise ErrorUmbrales(f"FILAS_POR_LINEA no coincide con la tabla del Anexo B: {filas}")


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


# ---------------------------------------------------------------------------------------------
# Objeto de umbrales

@dataclass(frozen=True)
class Umbrales:
    """Umbrales vigentes de una corrida. Inmutable; ``ajustado`` devuelve otro objeto."""
    ajustables: Mapping[str, Any]          # id → {"linea", "texto", "anclado", "lista_conservadora"}
    fijos: Mapping[str, int | float]       # id → valor (124 ids de PLANTILLAS_FIJOS)
    pasos: Mapping[str, int] = field(default_factory=dict)   # id → pasos movidos por §8.F (0 = anclado)
    sha256_json: str = ""

    def __post_init__(self) -> None:
        ajustables = _congelar(self.ajustables)
        _comprobar_ajustables(ajustables)
        if tuple(self.fijos) != IDS_FIJOS:
            raise ErrorUmbrales("los fijos no son exactamente los ids de PLANTILLAS_FIJOS, en orden")
        for ident, v in self.fijos.items():
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ErrorUmbrales(f"fijo {ident} no numérico: {v!r}")
        pasos = {i: 0 for i in IDS_AJUSTABLES}
        for ident, n in dict(self.pasos).items():
            if ident not in pasos:
                raise ErrorUmbrales(f"pasos de un id que no es ajustable: {ident}")
            if isinstance(n, bool) or not isinstance(n, int) or not 0 <= n <= len(ajustables[ident]["lista_conservadora"]):
                raise ErrorUmbrales(f"pasos fuera de la lista en {ident}: {n!r}")
            pasos[ident] = n
        object.__setattr__(self, "ajustables", ajustables)
        object.__setattr__(self, "fijos", MappingProxyType(dict(self.fijos)))
        object.__setattr__(self, "pasos", MappingProxyType(pasos))

    def _entrada(self, ident: str) -> Mapping[str, Any]:
        if ident not in self.ajustables:
            otro = " (es fijo: use f)" if ident in self.fijos else ""
            raise ErrorUmbrales(f"umbral ajustable desconocido: {ident!r}{otro}")
        return self.ajustables[ident]

    def a(self, ident: str) -> Any:
        """Valor vigente de un ajustable: el anclado o el de la lista tras los pasos de §8.F."""
        entrada = self._entrada(ident)
        n = self.pasos[ident]
        return entrada["anclado"] if n == 0 else entrada["lista_conservadora"][n - 1]

    def f(self, ident: str) -> int | float:
        if ident not in self.fijos:
            otro = " (es ajustable: use a)" if ident in self.ajustables else ""
            raise ErrorUmbrales(f"umbral fijo desconocido: {ident!r}{otro}")
        return self.fijos[ident]

    def frac(self, ident: str) -> float:
        if not ident.endswith("_PCT"):
            raise ErrorUmbrales(f"frac sólo vale para ids *_PCT, no para {ident!r}")
        return self.f(ident) / 100

    def ajustado(self, ident: str) -> "Umbrales":
        """Un paso hacia lo conservador en ``ident``; ErrorUmbrales si su lista está agotada."""
        entrada = self._entrada(ident)
        n = self.pasos[ident]
        lista = entrada["lista_conservadora"]
        if n >= len(lista):
            raise ErrorUmbrales(f"lista agotada en {ident}: {entrada['texto']!r}")
        if not _paso_conservador(ident, self.a(ident), lista[n]):
            raise ErrorUmbrales(f"{ident}: {self.a(ident)!r} → {lista[n]!r} no es hacia lo conservador")
        return replace(self, pasos={**self.pasos, ident: n + 1})

    def agotado(self, ident: str) -> bool:
        """True si la lista de §8.F de ``ident`` ya no admite otro paso."""
        return self.pasos[ident] >= len(self._entrada(ident)["lista_conservadora"])

    def vigentes(self) -> dict[str, Any]:
        """Valores vigentes (para el informe y el registro de §8.F); pares como listas."""
        return {"ajustables": {i: _a_json(self.a(i)) for i in IDS_AJUSTABLES},
                "fijos": dict(self.fijos),
                "pasos": dict(self.pasos)}

    def huella(self) -> str:
        """sha256 del JSON canónico de los valores vigentes (va al informe)."""
        return _sha256_bytes(_json_canonico(self.vigentes()))


# ---------------------------------------------------------------------------------------------
# Texto del Anexo B

def numero_del_texto(token: str) -> int | float:
    """«−40,0» → -40.0; «1.100» → 1100; «0,0005» → 0.0005; sin coma da int."""
    if not isinstance(token, str) or re.fullmatch(NUMERO_DEL_TEXTO, token) is None:
        raise ErrorUmbrales(f"número mal escrito para el texto: {token!r}")
    negativo = token.startswith("−")
    cuerpo = token.lstrip("−").replace(".", "")
    valor: int | float = float(cuerpo.replace(",", ".")) if "," in cuerpo else int(cuerpo)
    return -valor if negativo else valor


def traducir_fijos(fijos_texto: list[str]) -> dict[str, int | float]:
    """Traduce las 33 líneas con PLANTILLAS_FIJOS (re.fullmatch por línea); ErrorUmbrales si no calza."""
    if len(fijos_texto) != len(PLANTILLAS_FIJOS):
        raise ErrorUmbrales(f"fijos_texto tiene {len(fijos_texto)} líneas; las plantillas, {len(PLANTILLAS_FIJOS)}")
    valores: dict[str, int | float] = {}
    for n, (patron, plantilla, linea) in enumerate(zip(_REGEX_FIJOS, PLANTILLAS_FIJOS, fijos_texto), start=1):
        m = patron.fullmatch(linea) if isinstance(linea, str) else None
        if m is None:
            raise ErrorUmbrales(f"la línea {n} de los fijos no calza con su plantilla:\n  texto:     {linea!r}\n"
                                f"  plantilla: {plantilla!r}")
        for ident in _ids_de_plantilla(plantilla):
            valores[ident] = numero_del_texto(m.group(ident))
    if tuple(valores) != IDS_FIJOS:
        raise ErrorUmbrales("la traducción no dio los ids de PLANTILLAS_FIJOS en orden")
    return valores


def regenerar_desde_texto(texto_protocolo: str, nombre_archivo: str) -> dict:
    """Rehace el JSON de umbrales desde el Anexo B (mismo algoritmo que c0/preparar_c0.anexo_b).

    Igual que preparar_c0: tabla de ajustables antes de «**Fijos**» (celdas «Línea | Id | Anclado → lista»,
    valores separados por «→») y lista de líneas «- » después. Más estricto que preparar_c0 sin cambiar
    su resultado: cada celda debe traer un solo número escrito como en el texto, no puede haber filas de
    tabla mal formadas ni líneas sueltas en «Fijos», y deben salir los 23 ajustables, sin repetir.
    ``generado_desde`` lleva ``nombre_archivo`` y el sha256 del texto en UTF-8.

    Desde la Enmienda 1 (E1-5, texto v1.0.1 y siguientes) el Anexo B cierra con el párrafo «**Fijos del
    cuerpo** …», que no es una línea de fijos: la lista termina ahí, como en preparar_c0, que sólo toma las
    líneas «- ». El párrafo debe aparecer una vez, empezar una línea y ser lo último del anexo (PEN-1 de C1:
    sin este corte, ``cargar_umbrales`` no cargaba el texto v1.1). Con el texto de C0, que no lo trae, el
    resultado no cambia.
    """
    b = _seccion(texto_protocolo, "## Anexo B.", "## Anexo C.")
    if b.count("**Fijos**") != 1:
        raise ErrorUmbrales(f"«**Fijos**» aparece {b.count('**Fijos**')} veces en el Anexo B")
    parte_ajustables, parte_fijos = b.split("**Fijos**")
    if parte_fijos.count(FIJOS_DEL_CUERPO) > 1:
        raise ErrorUmbrales(f"«{FIJOS_DEL_CUERPO}» aparece más de una vez en el Anexo B")
    if FIJOS_DEL_CUERPO in parte_fijos:
        parte_fijos, cola = parte_fijos.split(FIJOS_DEL_CUERPO)
        if not parte_fijos.endswith("\n"):
            raise ErrorUmbrales(f"«{FIJOS_DEL_CUERPO}» no empieza una línea del Anexo B")
        if any(linea.strip() for linea in cola.splitlines()[1:]):
            raise ErrorUmbrales(f"el párrafo «{FIJOS_DEL_CUERPO}» debe ser lo último del Anexo B")
    ajustables: dict[str, dict] = {}
    for linea in parte_ajustables.splitlines():
        if not linea.strip().startswith("|"):
            continue
        celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
        if len(celdas) != 3:
            raise ErrorUmbrales(f"fila de la tabla de ajustables sin tres celdas: {linea!r}")
        if celdas[0] in ("Línea", "---") or set(celdas[0]) <= {"-"}:
            continue
        linea_id, ident, valores = celdas
        if ident in ajustables:
            raise ErrorUmbrales(f"ajustable repetido en el Anexo B: {ident}")
        partes = [p.strip() for p in valores.split("→")]
        ajustables[ident] = {"linea": linea_id, "texto": valores, "anclado": _valor_de_celda(partes[0]),
                             "lista_conservadora": [_valor_de_celda(p) for p in partes[1:]]}
    if len(ajustables) != len(IDS_AJUSTABLES):
        raise ErrorUmbrales(f"el Anexo B trae {len(ajustables)} ajustables; se esperan {len(IDS_AJUSTABLES)}")
    lineas_fijos = parte_fijos.splitlines()
    for linea in lineas_fijos[1:]:          # la primera es el resto del rótulo: « (no se ajustan).»
        if linea.strip() and not linea.strip().startswith("-"):
            raise ErrorUmbrales(f"línea suelta en «Fijos» del Anexo B: {linea!r}")
    fijos = [l.strip() for l in lineas_fijos if l.strip().startswith("-")]
    return {"schema": ESQUEMA_JSON,
            "generado_desde": {"archivo": nombre_archivo,
                               "sha256": _sha256_bytes(texto_protocolo.encode("utf-8"))},
            "nota": NOTA_JSON,
            "ajustables": ajustables, "fijos_texto": fijos}


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


# Claves del JSON que no salen del Anexo B (riesgo R-04 del diseño): la huella de bateria_v1.csv (§8.D).
CLAVES_AJENAS_AL_ANEXO_B = ("bateria",)


def comparar(json_publicado: dict, json_regenerado: dict) -> list[str]:
    """Diferencias entre ambos (lista vacía = C1 pasa). Ignora sólo las claves de CLAVES_AJENAS_AL_ANEXO_B.

    Es estricta: tipos (int ≠ float), listas en orden y también el orden de las claves, porque el de
    «ajustables» es el de las filas del Anexo B (§8.F).
    """
    publicado = {k: v for k, v in json_publicado.items() if k not in CLAVES_AJENAS_AL_ANEXO_B}
    regenerado = {k: v for k, v in json_regenerado.items() if k not in CLAVES_AJENAS_AL_ANEXO_B}
    salida: list[str] = []
    _diferencias("$", publicado, regenerado, salida)
    return salida


def _comprobar_bateria(valor: Any) -> None:
    """Forma de la clave ajena «bateria» (R-04): {"archivo": texto, "sha256": 64 hex}."""
    if (not isinstance(valor, dict) or set(valor) != {"archivo", "sha256"} or not isinstance(valor["archivo"], str)
            or not isinstance(valor["sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", valor["sha256"]) is None):
        raise ErrorUmbrales(f"clave «bateria» mal formada: {valor!r}")


def cargar_umbrales(ruta_json: Path, ruta_protocolo: Path, *, sha256_json: str | None = None) -> Umbrales:
    """Lee el JSON, verifica su sha256 (si se da), lo compara con el texto y traduce los fijos."""
    datos = Path(ruta_json).read_bytes()
    huella = _sha256_bytes(datos)
    if sha256_json is not None and huella != sha256_json:
        raise ErrorUmbrales(f"sha256 del JSON de umbrales {huella} ≠ esperado {sha256_json}")
    publicado = _cargar_json_estricto(datos)
    if publicado.get("schema") != ESQUEMA_JSON:
        raise ErrorUmbrales(f"esquema {publicado.get('schema')!r}; se espera {ESQUEMA_JSON!r}")
    for clave in CLAVES_AJENAS_AL_ANEXO_B:
        if clave in publicado:
            _comprobar_bateria(publicado[clave])
    ruta_protocolo = Path(ruta_protocolo)
    try:
        texto = ruta_protocolo.read_bytes().decode("utf-8")   # sin traducir saltos de línea
    except UnicodeDecodeError as e:
        raise ErrorUmbrales(f"el protocolo no es UTF-8: {e}") from e
    diferencias = comparar(publicado, regenerar_desde_texto(texto, ruta_protocolo.name))
    if diferencias:
        raise ErrorUmbrales("el JSON de umbrales no coincide con el Anexo B:\n  " + "\n  ".join(diferencias))
    return Umbrales(ajustables=publicado["ajustables"], fijos=traducir_fijos(publicado["fijos_texto"]),
                    pasos={}, sha256_json=huella)


def cargar_c0(aph: Path) -> Umbrales:
    """Umbrales anclados en C0: JSON y texto de APH, ambos con el sha256 de la tabla de anclaje.

    Sirve a las pruebas y a la batería antes de que exista el texto consolidado v1.1.
    """
    ruta_protocolo = Path(aph) / PROTOCOLO_C0
    huella = _sha256_bytes(ruta_protocolo.read_bytes())
    if huella != SHA_PROTOCOLO_C0:
        raise ErrorUmbrales(f"sha256 del protocolo {huella} ≠ anclado en C0 {SHA_PROTOCOLO_C0}")
    return cargar_umbrales(Path(aph) / JSON_C0, ruta_protocolo, sha256_json=SHA_JSON_C0)


def siguiente_ajuste(umbrales: Umbrales, linea: str) -> str | None:
    """§8.F: el primer id de FILAS_POR_LINEA[linea] con lista no agotada; None si todas lo están
    (una línea sin filas, como E3d o P7, está agotada desde el principio)."""
    if linea in LINEAS_SIN_FILAS:
        return None
    if linea not in FILAS_POR_LINEA:
        raise ErrorUmbrales(f"línea desconocida para §8.F: {linea!r}")
    for ident in FILAS_POR_LINEA[linea]:
        if not umbrales.agotado(ident):
            return ident
    return None
