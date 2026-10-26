"""Tipos compartidos: enumerados, identificadores, estructuras y esquemas de tablas.

Es el contrato entre módulos. No tiene lógica ni E/S, salvo los métodos triviales de
identificación (``id``/``desde_id``) y la validación de esquemas. Ningún otro módulo
define columnas ni enumerados propios: los toma de aquí.

Convenciones (§2.1):
- L es la etiqueta ingenua (``timestamp_source``); u el instante UTC; c = L − u en horas.
- ``fixed_offset_minutes = 60·c``: F(0) → 0, F(−4) → −240.
- Las etiquetas y los instantes viajan como ``datetime64[ns]`` ingenuos en pandas/numpy;
  u es siempre UTC (sin zona en numpy, con zona sólo en la frontera con ``_utc``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
import re
from typing import Mapping, Protocol

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Enumerados
# ---------------------------------------------------------------------------
class Estado(StrEnum):
    """Estado de una línea, por unidad y por H (§4.0). «Dudosa» y «sin información» valen lo mismo."""
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    DUDOSA = "dudosa"
    SIN_INFORMACION = "sin_informacion"


class Senal(StrEnum):
    """Señal adicional de una línea en una unidad (§4.0: «además, reloj anómalo»)."""
    NINGUNA = "ninguna"
    RELOJ_ANOMALO = "reloj_anomalo"


class Familia(StrEnum):
    """Familias por fuente de error (§4.0) y papeles que no apoyan."""
    REGISTRO = "registro"
    TERMICA = "termica"
    PRESION_REANALISIS = "presion_reanalisis"
    PRESION_MAREA = "presion_marea"
    EXTERNA = "externa"
    DOCUMENTAL = "documental"
    GUARDA = "guarda"
    MARCA = "marca"


class Linea(StrEnum):
    """Líneas, guardas y marcas de §4 (tabla de §4.0)."""
    E1A = "E1a"
    E1B = "E1b"
    E1C = "E1c"
    E2 = "E2"
    E3T = "E3t"
    E3P = "E3p"
    E4P = "E4p"
    E6 = "E6"
    E5 = "E5"
    E3D = "E3d"
    P7 = "P7"
    TP = "T-P"
    E4T = "E4t"
    G_VERSION = "G-version"
    G_HR = "G-HR"
    G_VIENTO = "G-viento"


@dataclass(frozen=True)
class PropiedadesLinea:
    familia: Familia
    cuantitativa: bool      # Q de §4.0 (E3t sólo en modo completo: se resuelve en decision)
    no_termica: bool        # «cualquiera salvo E3t»
    excluye: bool           # puede excluir en el paso 3 de §5.1 (E4p deja de hacerlo si falla A3)


LINEAS: Mapping[Linea, PropiedadesLinea] = {
    Linea.E1A: PropiedadesLinea(Familia.REGISTRO, False, True, True),
    Linea.E1B: PropiedadesLinea(Familia.REGISTRO, False, True, True),
    Linea.E1C: PropiedadesLinea(Familia.REGISTRO, False, True, True),
    Linea.E2: PropiedadesLinea(Familia.REGISTRO, False, True, True),
    Linea.E3T: PropiedadesLinea(Familia.TERMICA, False, False, False),
    Linea.E3P: PropiedadesLinea(Familia.PRESION_REANALISIS, True, True, True),
    Linea.E4P: PropiedadesLinea(Familia.PRESION_MAREA, True, True, True),
    Linea.E6: PropiedadesLinea(Familia.EXTERNA, True, True, True),
    Linea.E5: PropiedadesLinea(Familia.DOCUMENTAL, False, True, False),
    Linea.E3D: PropiedadesLinea(Familia.GUARDA, False, True, False),
    Linea.P7: PropiedadesLinea(Familia.GUARDA, False, True, False),
    Linea.TP: PropiedadesLinea(Familia.GUARDA, False, True, False),
    Linea.E4T: PropiedadesLinea(Familia.GUARDA, False, True, False),
    Linea.G_VERSION: PropiedadesLinea(Familia.GUARDA, False, True, False),
    Linea.G_HR: PropiedadesLinea(Familia.MARCA, False, True, False),
    Linea.G_VIENTO: PropiedadesLinea(Familia.MARCA, False, True, False),
}

LINEAS_DE_APOYO = (Linea.E1A, Linea.E1B, Linea.E1C, Linea.E2, Linea.E3T, Linea.E3P, Linea.E4P, Linea.E6)
LINEAS_DE_COBERTURA = (Linea.E2, Linea.E3P, Linea.E4P, Linea.E6)   # §5.1 paso 8
GUARDAS_DE_DECISION = (Linea.E3D, Linea.P7, Linea.TP, Linea.E4T)  # §5.1 paso 5


class Nivel(StrEnum):
    """Nivel de la unidad a la que se refiere una fila de estado."""
    EVENTO = "evento"        # E1a, E1b (un cambio de hora o un placebo)
    PARTE = "parte"          # «AAAA-MM-n»
    MES = "mes"              # «AAAA-MM» (E1c, E6)
    REGIMEN = "regimen"      # «R0» | «R1»
    ANIO = "anio"            # «AAAA»
    ESTACION = "estacion"    # «*» (patrones de E1, apagado de la regla fina)


class Regla(StrEnum):
    """Sub-regla dentro de una línea (sólo E3p y E3t usan gruesa/fina)."""
    UNICA = "unica"
    GRUESA = "gruesa"
    FINA = "fina"


class MotivoSinInfo(StrEnum):
    MINIMOS = "minimos"
    RMAX = "rmax"
    EMPATE = "empate"
    RESIDUAL = "residual"
    ALIAS = "alias"
    COORDENADAS = "coordenadas"            # no interpretables o inconsistentes (§3.1, §3.3)
    COSTERA = "costera"
    SIN_PIXEL = "sin_pixel"
    SIN_DESNIVEL = "sin_desnivel"
    PASO = "paso"                          # p_v ∉ {1, 2, 3, 6}
    FILTRO = "filtro_representatividad"
    SIN_OBSERVADOR = "sin_observador"
    NO_INFORMATIVA = "no_informativa"
    HUECO = "hueco"
    AMPLITUD = "amplitud"
    CAMPOS = "campos_faltantes"            # E1c sin row_count o source_empty_slots
    SIN_EVIDENCIA = "sin_evidencia"        # E1a/E1b
    APAGADA = "apagada"                    # consecuencia de A3 o apagado de la regla fina
    INACTIVA = "inactiva"                  # línea no activada en C0 (E5, E6)


class Veredicto(StrEnum):
    """Veredicto por estación-año (§5.1)."""
    CONFIRMADO = "confirmado"
    DISCREPANTE = "discrepante"
    INSUFICIENTE = "insuficiente"
    SIN_DATOS = "sin_datos"
    SIN_CONFIRMAR = "sin_confirmar"     # después de §5.3 (cambio sin respaldo, inestable) o de A6


class MotivoAnio(StrEnum):
    RELOJ_ANOMALO = "reloj_anomalo"
    G_VERSION = "g_version"
    LINEAS_EN_CONFLICTO = "lineas_en_conflicto"
    GUARDA_E3D = "guarda_E3d"
    GUARDA_P7 = "guarda_P7"
    GUARDA_TP = "guarda_T-P"
    GUARDA_E4T = "guarda_E4t"
    NO_DISTINGUE = "no_distingue"
    APOYO = "apoyo"
    COBERTURA = "cobertura"
    CAMBIO_SIN_RESPALDO = "cambio_sin_respaldo"
    INESTABLE = "inestable"
    DOCUMENTAL_A6 = "documental_A6"


class VeredictoEstacion(StrEnum):
    CONFIRMADA = "confirmada"
    SIN_CONFIRMAR = "sin_confirmar"


class Conjunto(StrEnum):
    V = "V"
    V2 = "V2"
    N = "N"


class Territorio(StrEnum):
    CONTINENTAL = "continental"
    JUAN_FERNANDEZ_DESVENTURADAS = "juan_fernandez_desventuradas"
    AYSEN = "aysen"
    MAGALLANES = "magallanes"
    ANTARTICA = "antartica"
    PASCUA_SALA_Y_GOMEZ = "pascua_sala_y_gomez"
    INCIERTO = "incierto"


class ModoE3t(StrEnum):
    RESTRINGIDO = "restringido"
    COMPLETO = "completo"


class ResultadoGuarda(StrEnum):
    PASA = "pasa"
    FALLA = "falla"
    NO_EVALUABLE = "no_evaluable"


class ResultadoEvento(StrEnum):
    PRESENTE = "presente"
    AUSENTE = "ausente"
    SIN_EVIDENCIA = "sin_evidencia"


class ClaseEvento(StrEnum):
    REAL = "real"
    PLACEBO_SEMANA = "placebo_semana"        # E1a: 8 fechas del mismo día de la semana
    PLACEBO_A2 = "placebo_A2"                # E1a/E1b/E1c: Anexo A2
    PLACEBO_DESPLAZADO = "placebo_desplazado"  # E1b: ±42 y ±63 días
    # E1a, Enmienda 3 (E3-2, opción A′; Anexo A3): etiqueta inexistente bajo una regla vencida que no está
    # ya en la tabla como placebo (las fechas de adelanto del A2 son a la vez placebo_A2 y evento de regla
    # vencida; ver lineas_registro, lectura 9).
    REGLA_VENCIDA = "regla_vencida"


# ---------------------------------------------------------------------------
# Hipótesis y clases fusionadas (§2)
# ---------------------------------------------------------------------------
ZONAS = ("America/Santiago", "America/Coyhaique", "America/Punta_Arenas", "Pacific/Easter")
ABREVIATURA_ZONA = {"America/Santiago": "Santiago", "America/Coyhaique": "Coyhaique",
                    "America/Punta_Arenas": "Punta_Arenas", "Pacific/Easter": "Pacific/Easter"}


@dataclass(frozen=True)
class Hipotesis:
    """Un reloj: F(c) fijo, C(Z) civil o Cv(Z) civil con reglas vencidas (sólo diagnóstico §4.1.4).

    Identificador canónico ASCII:
      F(0), F(-3), F(-4), F(-5), F(-6), F(+1) …  (signo explícito salvo en 0);
      C(Santiago), C(Coyhaique), C(Punta_Arenas), C(Pacific/Easter);
      Cv(Santiago) … (el año va en la unidad, no en el id).
    «America/Easter» no existe y debe dar error en ``desde_id`` y en el constructor de C.
    """
    tipo: str              # "F" | "C" | "Cv"
    desfase: int | None    # horas (c = L − u) sólo en F
    zona: str | None       # nombre IANA completo en C y Cv

    def __post_init__(self):
        if self.tipo == "F":
            if isinstance(self.desfase, bool) or not isinstance(self.desfase, int) or self.zona is not None:
                raise ValueError(f"F(c) exige un desfase entero y ninguna zona: {self!r}")
        elif self.tipo in ("C", "Cv"):
            if self.desfase is not None or self.zona not in ZONAS:
                raise ValueError(f"{self.tipo}(Z) exige una zona de {ZONAS} y ningún desfase: {self!r}")
        else:
            raise ValueError(f"tipo de hipótesis desconocido: {self.tipo!r}")

    @property
    def id(self) -> str:
        if self.tipo == "F":
            return "F(0)" if self.desfase == 0 else f"F({self.desfase:+d})"
        return f"{self.tipo}({ABREVIATURA_ZONA[self.zona]})"

    @classmethod
    def desde_id(cls, texto: str) -> "Hipotesis":
        m = re.fullmatch(r"F\((0|[+-][1-9][0-9]*)\)", texto)
        if m:
            return cls("F", int(m.group(1)), None)
        m = re.fullmatch(r"(Cv|C)\(([A-Za-z_/]+)\)", texto)
        zonas = {abreviatura: zona for zona, abreviatura in ABREVIATURA_ZONA.items()}
        if m and m.group(2) in zonas:
            return cls(m.group(1), None, zonas[m.group(2)])
        raise ValueError(f"identificador de hipótesis inválido: {texto!r}")

    @property
    def es_fija(self) -> bool:
        return self.tipo == "F"

    def orden(self) -> tuple:
        """Clave de orden canónico: F por desfase descendente, luego C según ZONAS, luego Cv."""
        if self.tipo == "F":
            return (0, -self.desfase)
        return (1 if self.tipo == "C" else 2, ZONAS.index(self.zona))


@dataclass(frozen=True)
class Regimen:
    """Año-régimen (§3.5): R0 contiene el 1 de enero; R1 el otro (si existe)."""
    anio: int
    id: str                          # "R0" | "R1"
    desfases_zs: tuple[int, ...]     # desfase (h) de cada zona de Zs, en el orden de Zs


@dataclass(frozen=True)
class ClaseH:
    """Clase de hipótesis fusionadas en un año (§2.3).

    ``id`` = ids de los miembros en orden canónico unidos por «|», p. ej. «F(-3)|C(Santiago)».
    Una clase de un solo miembro tiene por id el de ese miembro.
    ``desfases`` da c (h) por régimen con datos; todos los miembros comparten esos valores.
    """
    miembros: tuple[Hipotesis, ...]
    desfases: Mapping[str, int]

    @property
    def id(self) -> str:
        if not self.miembros:
            raise ValueError("una clase necesita al menos un miembro")
        return "|".join(h.id for h in sorted(self.miembros, key=lambda h: h.orden()))

    @property
    def ids_miembros(self) -> frozenset[str]:
        return frozenset(h.id for h in self.miembros)


def interseccion_de_clases(a: frozenset[str], b: frozenset[str]) -> frozenset[str]:
    """Comparación de clases de dos años (§2.3, §5.3): intersección de los ids de miembros."""
    return a & b


# ---------------------------------------------------------------------------
# Calendario (Anexos A y A2) y unidades (§3.5)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Cambio:
    """Un cambio de hora de una zona (Anexo A) y sus etiquetas especiales en hora de pared de esa zona."""
    zona: str
    u: datetime                  # instante UTC consciente de la primera hora con el desfase nuevo
    antes_min: int
    despues_min: int
    tipo: str                    # "adelanto" | "atraso"
    etiqueta: datetime           # adelanto: h0 inexistente; atraso: etiqueta repetida (ingenuas)
    fecha_D: date                # fecha de ``etiqueta``
    domingo: date                # domingo correspondiente (E1b y Anexo A2)


@dataclass(frozen=True)
class FilaA2:
    """Fila del Anexo A2 en el orden del texto (huella b0727bee… en C0)."""
    anio: int
    cambio: str                  # "atraso" | "adelanto" | "sin atraso" | "sin adelanto"
    fecha_real: date | None
    regla: str                   # texto literal, p. ej. «marzo, domingo ≥ 9»
    fechas_placebo: tuple[date, ...]


@dataclass(frozen=True)
class ParteDef:
    """Parte (§3.5): estación-mes cortado en las etiquetas civiles de cambio de las zonas de Zs.

    ``id`` = «AAAA-MM-n», n ≥ 1 en orden de etiqueta (es el ``<unidad>`` de la semilla).
    ``regimen`` es None en una astilla de borde (etiquetas entre los cambios de dos zonas de Zs).
    """
    id: str
    anio: int
    mes: int
    n: int
    desde: datetime              # primera etiqueta incluida
    hasta: datetime              # última etiqueta incluida
    regimen: str | None


@dataclass(frozen=True)
class InfoEstacion:
    """Lo que se sabe de una estación antes de mirar sus valores (§3.1, §3.3)."""
    codigo: str
    nombre: str | None
    lat: float | None
    lon: float | None
    alt_m: float | None                # z_cat
    coordenadas_validas: bool
    coordenadas_inconsistentes: bool
    territorio: Territorio
    region: int | None
    macrozona: str
    zs: tuple[str, ...]
    P: tuple[Hipotesis, ...]
    pixel_id: int | None
    distancia_km: float | None
    costera: bool
    z_pix: float | None
    dz: float | None                   # z_cat − z_pix
    conjunto: Conjunto
    tipo: str | None = None
    propietario: str | None = None
    omm: str | None = None
    oaci: str | None = None


@dataclass(frozen=True)
class ContextoEstacion:
    """Entrada común de todas las líneas de una estación (armada por orquestacion.contexto_estacion).

    ``tablas`` es un tablas.TablasCalendario y ``umbrales`` un umbrales.Umbrales (se tipan como object
    para que este módulo no importe a otros). ``P`` es el mismo cada año; las clases cambian por año.
    """
    info: InfoEstacion
    tablas: object
    umbrales: object
    anios: tuple[int, ...]                              # años con datos
    regimenes: Mapping[int, tuple["Regimen", ...]]      # todos los del año
    regimenes_con_datos: Mapping[int, tuple[str, ...]]  # ids con alguna etiqueta no especial con datos
    clases: Mapping[int, tuple["ClaseH", ...]]
    meses_con_datos: Mapping[int, tuple[int, ...]]
    lineas_activas: frozenset["Linea"]
    aplicar_exclusion_costera: bool = True              # C3c la apaga (§8.E)


# ---------------------------------------------------------------------------
# ERA5-Land (§3.4)
# ---------------------------------------------------------------------------
VARIABLES_ERA5 = ("t2m", "sp", "u10", "v10")   # t2m en °C, sp en hPa, u10 y v10 en m/s


class SerieEra5(Protocol):
    """Series horarias UTC por píxel enlazado. Implementaciones: extraccion.SerieEra5Mapeada
    (arreglo mapeado en disco) y sintetico.SerieEra5Memoria (batería D)."""
    t0: np.datetime64        # primera hora UTC del eje global (datetime64[h], ingenua)
    n_horas: int

    def tiene(self, pixel_id: int) -> bool: ...

    def valores(self, pixel_id: int, variable: str, u: np.ndarray) -> np.ndarray:
        """x(u) en float64; NaN fuera del eje o sin dato. ``u`` es datetime64 UTC ingenuo."""
        ...

    def media(self, pixel_id: int, variable: str) -> float: ...


# ---------------------------------------------------------------------------
# Resultados que pasan entre módulos
# ---------------------------------------------------------------------------
@dataclass
class ResultadoLinea:
    """Salida común de toda línea: estados largos y métricas propias."""
    linea: Linea
    estados: pd.DataFrame                       # ESQUEMA_ESTADOS
    metricas: pd.DataFrame | None = None        # esquema propio de la línea (ESQUEMA_METRICAS_*)
    eventos: pd.DataFrame | None = None         # ESQUEMA_EVENTOS (E1a, E1b, E1c)


@dataclass
class EvidenciaEstacion:
    """Todo lo que la fase 4 de §5.2 deja de una estación; basta para las fases 5 a 10."""
    info: InfoEstacion
    estados: pd.DataFrame                  # ESQUEMA_ESTADOS, todas las líneas
    metricas_e2: pd.DataFrame              # ESQUEMA_METRICAS_E2
    metricas_e3: pd.DataFrame              # ESQUEMA_METRICAS_E3 (Ts y QFE)
    metricas_e4: pd.DataFrame              # ESQUEMA_METRICAS_E4 (QFE y Ts)
    eventos: pd.DataFrame                  # ESQUEMA_EVENTOS
    guardas: pd.DataFrame                  # ESQUEMA_GUARDAS (precalculadas para toda H de P)
    marcas: pd.DataFrame                   # ESQUEMA_MARCAS (precalculadas para toda H de P)
    meses: pd.DataFrame                    # ESQUEMA_MES de la estación
    horas: pd.DataFrame                    # ESQUEMA_HORAS (denominadores de §5.4)
    # Clases del año (= ContextoEstacion.clases, §2.3). None mientras orquestacion no las copie; entonces
    # decision las recibe con su argumento ``clases=``, que manda si llegan las dos.
    clases: Mapping[int, tuple["ClaseH", ...]] | None = None


@dataclass(frozen=True)
class ConsecuenciasRed:
    """Consecuencias fijadas de A3, A4 y A5 y modo de E3t por macrozona (§4.3.3, §5.4)."""
    a3_falla_pais: bool
    a3_fallan_macrozonas: frozenset[str]
    a5_alto: bool
    modo_e3t: Mapping[str, ModoE3t]
    a4_restringe: bool | None = None       # None hasta calcular A4 (después del paso 6)

    def _a3_falla_en(self, macrozona: str) -> bool:
        return self.a3_falla_pais or macrozona in self.a3_fallan_macrozonas

    def e4p_activa(self, macrozona: str) -> bool:
        """E4p excluye y es cuantitativa salvo que A3 falle en el país o en esa macrozona (§5.4)."""
        return not self._a3_falla_en(macrozona)

    def fina_activa(self, macrozona: str) -> bool:
        """La regla fina de E3p se apaga donde falla A3 (§5.4)."""
        return not self._a3_falla_en(macrozona)

    def modo_e3t_en(self, macrozona: str) -> ModoE3t:
        """Restringido si falla A3 allí o en el país, si A4 restringe, o si la calibración no la habilitó (§4.3.3, §5.4)."""
        if self._a3_falla_en(macrozona) or self.a4_restringe:
            return ModoE3t.RESTRINGIDO
        return ModoE3t(self.modo_e3t.get(macrozona, ModoE3t.RESTRINGIDO))


@dataclass
class DecisionAnio:
    """Traza completa de §5.1 para un estación-año (va a evidencia_estacion_anio.parquet)."""
    codigo: str
    anio: int
    P: tuple[str, ...]
    clases: tuple[str, ...]
    excluidas: Mapping[str, tuple[str, ...]]        # id de clase → líneas que la excluyen
    K: tuple[str, ...]
    veredicto: Veredicto
    motivo: MotivoAnio | None = None
    detalle: str | None = None
    clase_confirmada: str | None = None
    lineas_apoyo: tuple[str, ...] = ()
    familias_apoyo: tuple[str, ...] = ()
    n_lineas_q: int = 0
    meses_con_apoyo: tuple[str, ...] = ()           # «AAAA-MM»
    meses_con_datos: tuple[str, ...] = ()
    partes_discordantes: tuple[str, ...] = ()
    guardas: Mapping[str, str] = field(default_factory=dict)   # Linea → ResultadoGuarda
    marcas: Mapping[str, object] = field(default_factory=dict)
    reglas_vencidas: bool = False
    modo_e3t: ModoE3t | None = None


@dataclass(frozen=True)
class Tramo:
    """Un intervalo de regla ``clock`` (§7.2). ``id`` = «<racha>.<tramo>», p. ej. «1.1»."""
    codigo: str
    id: str
    valid_from: datetime
    valid_to: datetime
    fixed_offset_minutes: int
    clase: str
    meses: tuple[str, ...]


# ---------------------------------------------------------------------------
# Esquemas de tablas (columna → tipo pandas). ``validar_esquema`` los hace cumplir.
# ---------------------------------------------------------------------------
ESQUEMA_EXTRACTO_HORA = {          # extractos/dmc/<código>.parquet, una fila por etiqueta evaluada
    "L": "datetime64[ns]",
    "anio": "int16",
    "mes": "int8",
    "id_artefacto": "int32",       # índice en artefactos_evaluados
    "medida": "bool",              # H(L) = 1 (§3.2)
    "ts": "float64",               # NaN si falta o la descartó el control propio
    "motivo_ts": "int8",           # CODIGOS_DESCARTE
    "qfe": "float64",
    "motivo_qfe": "int8",
    "td": "float64",
    "hr": "float64",
    "ff_kt": "float64",
    "dd_grados": "float64",
    "viento_valido": "bool",
    "qff_numerica": "bool",
    "rr": "bool",                  # fields["RR06"]["raw"].strip() != "" (incluye «s/p»)
    "tx": "bool",
    "tn": "bool",
    "observador": "bool",          # un dígito en CL, CM o CH
    "huella": "string",            # sha256 hex de los 21 textos crudos sin día ni hora
}

CODIGOS_DESCARTE = {0: "valido", 1: "ausente", 2: "centinela", 3: "rango", 4: "mediana", 5: "racha"}

ESQUEMA_ANOTACION = {              # columnas que agrega tablas.anotar_partes al extracto
    "parte": "string",             # «AAAA-MM-n»
    "regimen": "string",           # «R0» | «R1» | <NA> en astillas de borde
    "especial": "bool",            # etiqueta repetida o inexistente de alguna zona de Zs
}

ESQUEMA_MES = {                    # extractos/dmc/meses.parquet, un manifiesto por fila
    "codigo": "string",
    "anio": "int16",
    "mes": "int8",
    "manifiesto": "string",        # ruta por alias (DMC/estaciones/<código>/<AAAA-MM>.manifest.json)
    "manifiesto_sha256": "string",
    "artefacto_sha256": "string",
    "id_artefacto": "Int32",
    "script_sha256": "string",
    "entra": "bool",
    "motivo_exclusion": "string",  # pending, failed, candidato, version_no_admitida, sin_codigo, artifact_name, row_count
    "row_count": "Int32",
    "source_empty_slots": "Int32",
    "expected_hour_slots": "Int32",
    "n_available_hours": "Int32",
    "duplicate_display_rows_removed": "Int32",
    "source_sha256": "string",
    "requested_start": "string",
    "requested_end": "string",
    "campos_faltantes": "object",  # lista de nombres
    "p_ts": "Int16",               # paso nativo del mes (h); Int16, porque un paso > 127 h no cabe en Int8
    "p_qfe": "Int16",
    "lat_txt": "string",           # station.source_metadata del artefacto (para §3.1)
    "lon_txt": "string",
    "alt_txt": "string",
}

ESQUEMA_ESTACIONES = {             # pixeles_dmc.parquet (§7.4) ampliado; una fila por estación
    "codigo": "string", "nombre": "string", "lat": "float64", "lon": "float64", "alt_m": "float64",
    "coordenadas_validas": "bool", "coordenadas_inconsistentes": "bool", "territorio": "string",
    "region": "Int16", "macrozona": "string", "zs": "object", "P": "object", "pixel_id": "Int64",
    "distancia_km": "float64", "costera": "bool", "z_pix": "float64", "dz": "float64",
    "conjunto": "string", "tipo": "string", "propietario": "string", "omm": "string", "oaci": "string",
}

ESQUEMA_ESTADOS = {                # estados_largos.parquet: la traza de cada decisión
    "codigo": "string",
    "anio": "int16",
    "linea": "string",             # Linea
    "regla": "string",             # Regla
    "nivel": "string",             # Nivel
    "unidad": "string",            # «AAAA-MM-n», «AAAA-MM», «R0», «AAAA», «*» o id de evento
    "H": "string",                 # id de Hipotesis (nunca de clase)
    "estado": "string",            # Estado
    "reloj_anomalo": "bool",       # señal de la unidad (repetida en cada H)
    "discordante": "bool",         # parte o mes discordante (§4.0)
    "motivo": "string",            # MotivoSinInfo u otro texto corto
}

ESQUEMA_METRICAS_E2 = {
    "codigo": "string", "anio": "int16", "nivel": "string", "unidad": "string", "regimen": "string",
    "n_rr": "int32", "frac_observador": "float64", "valida": "bool", "informativa": "bool",
    "j_estrella": "Int8", "kappa3": "float64",
    "n_tx": "int32", "kappa3_tx": "float64", "j_tx": "Int8", "hora_modal_tx": "Int8",
    "n_tn": "int32", "kappa3_tn": "float64", "j_tn": "Int8", "hora_modal_tn": "Int8",
}

ESQUEMA_METRICAS_E3 = {
    "codigo": "string", "anio": "int16", "nivel": "string", "unidad": "string", "regimen": "string",
    "variable": "string",          # "Ts" | "QFE"
    "paso_h": "Int8", "n_pares": "int32", "n_bloques": "int32",
    "r": "object",                 # lista de 19 float64, c = −9 … 9
    "c_hat": "Int8", "c_hat_cont": "float64", "estab_c_hat": "float64",
    "r_f": "object", "c_hat_f": "Int8", "c_hat_f_cont": "float64", "estab_c_hat_f": "float64",
    "fino": "bool",                # año-régimen fino (§4.3.4)
    "filtro_e3t": "bool",          # sólo Ts (§4.3.3)
    "cociente_a1": "float64", "r_diaria": "float64",
}

ESQUEMA_METRICAS_E4 = {
    "codigo": "string", "anio": "int16", "nivel": "string", "unidad": "string", "regimen": "string",
    "variable": "string", "paso_h": "Int8", "n_h": "int8", "hueco_max_h": "int8", "K": "int8",
    "A1": "float64", "EE_A1": "float64", "phi1": "float64",
    "A2": "float64", "EE_A2": "float64", "psi2": "float64",
}

ESQUEMA_EVENTOS = {                # eventos_transicion.csv
    "codigo": "string", "linea": "string", "zona": "string", "anio": "int16", "tipo": "string",
    "clase_evento": "string", "fecha_D": "string", "etiqueta": "string",
    "p14": "float64", "pdom": "float64", "p": "float64", "resultado": "string",
    "delta_s": "Int8", "delta_e": "Int8", "delta": "Int8", "casillas": "Int32", "esperadas": "Int32",
}

ESQUEMA_GUARDAS = {
    "codigo": "string", "anio": "int16", "guarda": "string", "H": "string", "unidad": "string",
    "resultado": "string", "detalle": "string",
}

ESQUEMA_MARCAS = {
    "codigo": "string", "anio": "int16", "marca": "string", "H": "string", "valor": "object",
}

ESQUEMA_HORAS = {                  # estación-horas por mes (etiquetas con Ts o QFE), §5.4
    "codigo": "string", "anio": "int16", "mes": "int8", "horas_ts_o_qfe": "int32",
}

ESQUEMA_ISD = {                    # partes sintéticos o descargados para E6
    "codigo": "string", "u": "datetime64[ns]", "tipo_parte": "string", "tmp": "float64",
}

ESQUEMA_RACHAS = {
    "codigo": "string", "racha": "int16", "anio_desde": "int16", "anio_hasta": "int16",
    "clase": "string", "n_confirmados": "int16", "aceptada": "bool", "motivo": "string",
}

# --- Controles de red (§5.4, §4.3.3). Vivían en red.py hasta la ola 4b; red los conserva como alias. ---
ESQUEMA_MUESTRA_A3 = {             # años-régimen de A3: D = ĉ^f_cont − (ψ2 − 9,75 h), envueltos a [−6, 6)
    "codigo": "string", "anio": "int16", "regimen": "string", "macrozona": "string",
    "c_f_cont": "float64", "c_s2_cont": "float64", "D": "float64",
}
ESQUEMA_MUESTRA_A5 = {             # años-régimen de A5, con tipo y propietario de la estación
    "codigo": "string", "anio": "int16", "regimen": "string", "macrozona": "string",
    "tipo": "string", "propietario": "string", "c_f_cont": "float64",
}
ESQUEMA_CALIBRACION = {            # estación-años de la calibración de E3t (δt)
    "codigo": "string", "anio": "int16", "macrozona": "string", "H": "string",
    "n_regimenes": "int16", "delta_t": "float64", "deltas_R": "object", "tp": "string",
    "motivo": "string",
}
ESQUEMA_GDUP = {                   # casos de «Filas DMC duplicadas con valores contradictorios»
    "archivo": "string", "codigo": "string", "mes": "string", "url": "string",
    "atraso_en_zs": "boolean", "zonas_con_atraso": "string",
}

# --- Tablas de §7.4 (SAL-1). Vivían en salidas.py hasta la ola 4b; salidas las conserva como alias. ---
# evidencia_estacion_parte copia las métricas por parte con el prefijo de su línea (e2_, e3_…_ts/_qfe,
# e4_…_ts/_qfe/_hr); los enteros y booleanos pasan a sus tipos con nulos, porque una parte puede no tenerlas.
CLAVES_METRICAS = ("codigo", "anio", "nivel", "unidad", "regimen", "variable")
TIPO_CON_NULOS = {"int8": "Int8", "int16": "Int16", "int32": "Int32", "int64": "Int64", "bool": "boolean"}
VARIABLES_EVIDENCIA_E3 = ("Ts", "QFE")
VARIABLES_EVIDENCIA_E4 = ("Ts", "QFE", "HR")
COLUMNAS_EVIDENCIA_E2 = tuple(c for c in ESQUEMA_METRICAS_E2 if c not in CLAVES_METRICAS)
COLUMNAS_EVIDENCIA_E3 = tuple(c for c in ESQUEMA_METRICAS_E3 if c not in CLAVES_METRICAS)
COLUMNAS_EVIDENCIA_E4 = tuple(c for c in ESQUEMA_METRICAS_E4 if c not in CLAVES_METRICAS)

ESQUEMA_EVIDENCIA_PARTE = {        # evidencia_estacion_parte.parquet
    "codigo": "string", "anio": "int16", "mes": "int8", "parte": "string", "regimen": "string",
    **{f"e2_{c}": TIPO_CON_NULOS.get(ESQUEMA_METRICAS_E2[c], ESQUEMA_METRICAS_E2[c]) for c in COLUMNAS_EVIDENCIA_E2},
    **{f"e3_{c}_{v.lower()}": TIPO_CON_NULOS.get(ESQUEMA_METRICAS_E3[c], ESQUEMA_METRICAS_E3[c])
       for v in VARIABLES_EVIDENCIA_E3 for c in COLUMNAS_EVIDENCIA_E3},
    **{f"e4_{c}_{v.lower()}": TIPO_CON_NULOS.get(ESQUEMA_METRICAS_E4[c], ESQUEMA_METRICAS_E4[c])
       for v in VARIABLES_EVIDENCIA_E4 for c in COLUMNAS_EVIDENCIA_E4},
    "estados": "string",                 # JSON canónico {línea[/regla]: {H: estado}}
    "lineas_reloj_anomalo": "object",
    "discordante": "bool",
    "lineas_discordantes": "object",
}

ESQUEMA_EVIDENCIA_ANIO = {         # evidencia_estacion_anio.parquet
    "codigo": "string", "anio": "int16", "conjunto": "string", "territorio": "string", "macrozona": "string",
    "P": "object", "clases": "object",
    "estados": "string",                 # JSON canónico {línea[/regla]: {H: estado}} del nivel anio
    "excluidas": "string",               # JSON canónico {H′: [líneas]}
    "K": "object", "veredicto": "string", "motivo": "string", "detalle": "string", "clase_confirmada": "string",
    "lineas_apoyo": "object", "familias_apoyo": "object", "n_lineas_q": "int16",
    "meses_con_apoyo": "object", "meses_con_datos": "object", "n_meses_con_apoyo": "int16",
    "n_meses_con_datos": "int16", "partes_discordantes": "object",
    "guardas": "string", "marcas": "string",   # JSON canónico
    "reglas_vencidas": "bool", "modo_e3t": "string",
    "versiones_descargador": "object",   # script_sha256 de los meses evaluados del año (SAL-10)
    "veredicto_e3t_restringida": "string", "clase_e3t_restringida": "string",   # SAL-12
}

ESQUEMA_NO_NORMALIZABLES = {       # no_normalizables.csv (§7.3, comprobación 7)
    "codigo": "string", "manifiesto": "string", "artefacto_sha256": "string", "motivo": "string",
}
ESQUEMA_CALIBRACION_CSV = {**ESQUEMA_CALIBRACION, "fuera": "boolean"}   # calibracion_e3t.csv


def validar_esquema(df: pd.DataFrame, esquema: Mapping[str, str], *, nombre: str) -> None:
    """Exige exactamente esas columnas, en ese orden y con esos tipos; si no, ValueError."""
    columnas = list(df.columns)
    if columnas != list(esquema):
        raise ValueError(f"{nombre}: columnas {columnas} distintas del esquema {list(esquema)}")
    distintos = {c: (str(df[c].dtype), t) for c, t in esquema.items() if str(df[c].dtype) != t}
    if distintos:
        raise ValueError(f"{nombre}: tipos distintos del esquema (actual, esperado): {distintos}")


def tabla_vacia(esquema: Mapping[str, str]) -> pd.DataFrame:
    """DataFrame vacío con las columnas y tipos del esquema."""
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in esquema.items()})
