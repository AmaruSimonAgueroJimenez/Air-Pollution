"""Tipos compartidos: enumerados, identificadores, clases de datos y esquemas de tablas (§2 del diseño).

Es el contrato entre módulos. Ningún otro módulo define columnas ni enumerados propios: los toma de aquí.
``sintetico.py`` copia los esquemas que fabrica (no importa el paquete) y ``test_sintetico`` los compara con
estos. Un cambio de firma o de esquema se pide al coordinador y se anota en ``COORDINACION_M1.md`` (§0, regla 1).

Sin lógica ni E/S: sólo los identificadores triviales de §2.1, la validación de esquemas y la tabla vacía.
**No importa numpy ni pandas al importarse** (§1, «Base sin numpy»): ``tabla_vacia`` carga pandas al llamarse.
Así ``entorno`` puede fijar los hilos antes de que se carguen (MC-36).

Convenciones (§2.1 del diseño):
- ``h``: hora UTC como int32, horas desde ``EPOCA_H`` (2000-01-01T00:00Z). En las fronteras con v2, ``ts_utc``
  con zona UTC (``datetime64[ns, UTC]``).
- ``d2000``: días desde 2000-01-01 de la fecha UTC de la hora (MC-44).
- ``mes2000``: meses desde enero de 2000 (0 = 2000-01). Es el índice de mes de K4, de los tramos homogéneos y de
  ``desde_mes``/``hasta_mes``.
- Tipos de columnas: cadenas de tipo de pandas («float32» es f4 de pyarrow, «float64» f8, «string» texto,
  «boolean» bool con nulos, «Int32»/«Int64» enteros con nulos). ``validar_esquema`` compara ``str(df[c].dtype)``.
- Cada esquema lleva su versión (``Esquema.version``), que va a los metadatos de la tabla (``df.attrs["esquema"]``
  en memoria; los metadatos del parquet los escribe ``salidas``).

Lecturas propias (TIP-n), para el addendum de M1:
- TIP-1. Las marcas se numeran por su orden en la tabla de §2.4 (bit 0 a 22) y su nombre en minúsculas es el del
  texto (``Marca.SIN_RELOJ.name.lower() == "sin_reloj"``); ``test_tipos`` lo compara con el texto anclado.
- TIP-2. «Una marca invalidante de §2.4 (bits 3-17)» (§2.7, Q1) son las marcas de los bits 3 a 17 que invalidan
  algo según la tabla: las 8, 10 y 15 están en ese rango pero no invalidan («no»), así que no son alarmas Q1
  (``MARCAS_Q1``).
- TIP-3. Los orígenes de ``td_final``, ``hr_final`` y del viento llevan además ``SIN_VALOR`` (−1) para las horas sin
  valor final: la tabla ancha tiene una fila por hora con algún reporte (§2.3 del diseño) y la columna es int8.
- TIP-4. La marca 22 («posible media horaria») sólo informa: la invalidación la hace el bit 2 que la acompaña
  (§2.4: «marca de RELOJ §4.3.5 (con el bit 2)»).
- TIP-5. ``ESQUEMA_BANDAS_PUB`` lleva además ``uso`` y ``variable`` como claves: π y la fracción sin soporte
  dependen de la variable (la banda se mide con las estaciones con ≥ 2.000 h de la variable, §5.3) y del uso
  (hiperparámetros). El diseño dice «sólo banda, pi_mon, pi_pob y frac_sin_soporte por candidato».
- TIP-6. ``ReglaRedConstante`` lleva ``NINGUNA`` («ninguna»): la red de TF2 cuando no es evaluable (EMC1-2).
- TIP-7. Las 7 fracciones ``lulc_*`` son las columnas de ``grilla_1km/estaticas_lulc.parquet`` (leído sólo su
  esquema, como el diseño): urbano, cultivo, bosque, matorral_pastizal, desnudo, agua y nieve_hielo.
- TIP-8. **Macrozonas (D9).** Los nombres son los de ``_comun_modelo.MACROZONA_REGION`` y ``macrozona_cod`` sigue la
  codificación de ``_comun_modelo.MACROZONA_CODIGO`` (la de ``celdas.parquet``, que arma ``construir_grilla``); los dos
  se copian por AST en ``fijados``, no aquí. «sin_region» (región 0, ``cod_comuna = 0``) no es una macrozona:
  ``macrozona_o_ninguna`` la vuelve None, igual que una estación sin coordenadas legibles o fuera de la grilla.
- TIP-9. **Marcas del viento por variable de la fuente (D11).** La tabla ancha guarda ``marcas_FF`` y ``marcas_DD`` por
  separado (el diseño traía una sola ``marcas_viento``): un pico de la rapidez (θ = 15 m/s) sólo toca FF, y las
  marcas que invalidan «el viento» (11 y 12) van en las dos. Es lo que fijó D11 [delegada] para Q1: toda marca cuenta
  por variable de la fuente, en cada variable que invalida. D11 no pidió nada más de este módulo.
- TIP-11. **La macrozona «insular» (D16) y la macrozona de una celda.** «insular» (6 en ``MACROZONA_CODIGO``) tampoco
  es una macrozona: ``macrozona_o_ninguna`` la vuelve None, como «sin_region» (``MACROZONAS_NINGUNA``). En
  ``celdas.parquet`` las islas (``aoi_id`` rapa_nui, sala_y_gomez, juan_fernandez y desventuradas) llevan
  ``macrozona`` «insular» aunque su región sea la 5, y las celdas con ``cod_comuna`` −1 o 0 heredan la región de la
  celda válida más cercana a ≤ 30 km (``construir_grilla.construir_celdas``, leído sólo el código). Por eso la
  macrozona de una estación o de una celda sale de ``macrozona_de_celda`` (la columna ``macrozona`` de la celda y su
  ``cod_comuna``), no de ``cod_comuna // 1000`` con ``MACROZONA_REGION``: ese camino daría «centro» a Juan Fernández y
  a las Desventuradas. Una celda con ``cod_comuna`` ≤ 0 no tiene macrozona: D9 nombra el 0 y D20 [delegada] trata el
  −1 como el 0 («No se inventa una macrozona»). Esto vale para los conteos y los estratos; las indicadoras de C usan
  la macrozona de la grilla tal cual (D22, TIP-18).
- TIP-12. **Entradas de la decisión.** ``EntradasDecision`` lleva las tablas que ya fabrica
  ``sintetico.tablas_metricas`` (S7): las filas de ``ESQUEMA_VALIDACION_PUB`` del (uso, grupo), las de ``ESQUEMA_TF``
  del uso, las réplicas (``ESQUEMA_REPLICAS``) y los motivos de E0. ``decision`` calcula con ellas las compuertas, el
  S del grupo (S_par con los mínimos sobre E0, §5.3) y la red de TF2; por eso ya no lleva tablas de candidatos ni de
  compuertas armadas por otro módulo (el diseño traía ``candidatos``, ``compuertas`` y ``red_tf2``).
- TIP-10. ``ESQUEMA_VALIDACION_PUB`` lleva ``n_estaciones`` además de ``n_evaluaciones``: la compuerta MZ exige
  «≥ 10 estaciones evaluables» (§6.1) y cada estación da dos evaluaciones (P1 y P2, §5.1).
- TIP-13. **La errata confirmada de C5** (§2.1, precondición 1; POL-1). ``RegistroReloj.errata_confirmada`` es None o
  un ``ErrataConfirmada`` (ruta por alias, sha256 del archivo y commit de APH), el objeto
  ``{"ruta", "sha256", "commit"}`` de ``registro_politica_reloj.json``; antes era un texto «ruta=… sha256=… commit=…»
  que ``verificar_meteo_combinada`` (I22) tendría que volver a partir para comprobarlo en git (pedido de I6).
- TIP-14. **Motivos de exclusión de una estación** (``MotivoExclusion``; pedidos de I8). Los cinco de
  ``estaticas_nasadem`` (NAS-12 y NAS-16: coordenadas ilegibles, fuera del rango de RELOJ §3.3, sin tesela NASADEM a
  ≤ ρ, K3 fallida y sin z_s) y «sin_fondo», que pone ``orquestacion`` con el operador del fondo (A8, PAR-1). El
  enumerado va en el orden de precedencia de ``estaticas_nasadem.MOTIVOS``, con «sin_fondo» al final. Una estación
  lleva un solo motivo: el de ``estaticas_nasadem`` prevalece y «sin_fondo» va sólo en las que no estaban ya
  excluidas, porque Q2 (§2.7) cuenta por motivo y no debe perderlas:
  - ``MOTIVOS_SIN_COORDENADAS_K3``: las que «K3 deja sin coordenadas» (numerador de Q2; D36 [delegada] confirma que
    cuentan también las ilegibles y las fuera de rango);
  - ``MOTIVOS_FUERA_DE_Q2``: «sin_nasadem» (D37 [delegada]): sin ninguna tesela a ≤ ρ no hay prueba K3, y la estación
    sale del numerador y del denominador de Q2, se informa aparte y sigue fuera. No está en
    ``MOTIVOS_SIN_COORDENADAS_K3``: los dos conjuntos son disjuntos.
  Q2 se cuenta por estos motivos y por K4, no por ``coordinates.verified`` de la política, que también es falso en una
  «sin_nasadem» con z_cat (su ``source`` dice «k3», NAS-16). Los motivos de la regla ``coordinates`` de una política
  («sin_coordenadas», «k3», «k2», «traslado», POL-5 y POL-9) son otra cosa: dicen por qué una pieza va sin coordenadas
  confirmadas, no por qué una estación queda fuera.
- TIP-15. **Rótulos de las tablas de la decisión** (pedidos de I10). ``VariableMetrica``: los valores de ``variable``
  en ``ESQUEMA_VALIDACION_PUB`` y ``ESQUEMA_TF`` (los de SIN-14 y DEC-1). ``Estrato``: los de ``estrato`` que lee la
  regla («nacional» y «macrozona»); los demás estratos descriptivos de §5.5 los agrega I14 por medio del coordinador.
  ``MACROZONAS``: las que forman estrato y rigen en MZ, las de ``_comun_modelo.MACROZONA_CODIGO`` menos
  ``MACROZONAS_NINGUNA`` (``test_tipos`` las compara por AST, como DEC-19). ``CONTAMINANTES_M6`` y ``CLAVE_O3``
  (Anexo B, DEC-17) y las versiones de ``decision.json`` y ``decision_m6.json`` (DEC-18). ``publicable`` en
  ``ESQUEMA_VALIDACION_PUB`` es la regla de soporte de §5.5 evaluada en la partición de la fila (P1, P2 o el agregado)
  para ese estrato × variable, igual para todos los candidatos de la fila; el agregado nacional es siempre publicable
  (MC-61), y un estrato se publica y entra a una compuerta sólo si es publicable en P1, en P2 y en el agregado (MC-61,
  DEC-4). Lo implementa I14 con su prueba. ``decision`` ya toma estos nombres de aquí (I10, al aplicar D43-D46);
  ``test_tipos`` sigue comparando los que fabrica ``sintetico``, que no importa el paquete.
- TIP-16. **SINCA** (pedido de I11). ``ESQUEMA_SINCA_HORA`` no cambia: el conteo y la bandera de dos etiquetas en la
  misma hora UTC (R7) y el tipo de reloj de cada serie van en el registro (``attrs["registro_sinca"]``, SNC-8 y SNC-13),
  que ``orquestacion`` lleva al registro de M3-4. Ninguna métrica de §5.6 los necesita por hora.
- TIP-17. **El estado del fondo en las estaciones, para C y C_est** (pedido de I7; acuerdo A14). ``candidatos`` no puede
  importar ``fondo_era5l`` (§1 del diseño), y ``DatosCompetencia`` no traía el estado: ``climatologias`` es la tabla de
  A (``ESQUEMA_CLIMA_A``). Se suman dos campos, que arma ``orquestacion`` (I20) con ``fondo_era5l``:
  - ``puntos_e5l``: código → ``ESQUEMA_PUNTOS_E5L`` (A1), el estado de C en la estación (§4.6: T_F, T_F − Td_F, la
    rapidez del fondo y la amplitud diaria de T_F en el día UTC);
  - ``clima_estado``: código → {variable de ``VARIABLES_CLIMA_ESTADO``: 12 × 24 en float64, el mes 0 es enero y la
    columna es la hora UTC}, la fila de la estación de ``fondo_era5l.clima_en_puntos`` con el operador de las
    estaciones (D29, FON-14). Es el estado de C_est (§4.7). ``fondo_era5l.clima_en_horas`` lo lleva a las horas;
    ``candidatos`` hace lo mismo con el mes y la hora UTC de cada h.
  Los nombres de las variables (``VARIABLES_CLIMA_ESTADO``) son las columnas de ``ESQUEMA_CLIMA_ESTADO`` sin las claves;
  ``test_tipos`` los compara con ``fondo_era5l.VARIABLES_CLIMA``. No cambia ninguna regla.
- TIP-18. **Indicadoras de macrozona de C** (D22 (a) [delegada]). C usa la macrozona como predictor (§4.6): las
  indicadoras salen del ``macrozona_cod`` de la celda tal como está en la grilla, con la macrozona heredada de la
  vecina en las celdas con ``cod_comuna`` ≤ 0. Con «sin_region» o «insular», todas van en 0. ``MACROZONA_COD`` copia
  la codificación de ``_comun_modelo.MACROZONA_CODIGO``: las cinco ``MACROZONAS`` en su orden y después «sin_region» e
  «insular». ``test_tipos`` la compara por AST, con su huella; ``candidatos`` no puede importar ``fijados``.
  ``indicadoras_macrozona`` da las cinco indicadoras de un código. Una estación toma las de su celda («Los estáticos
  de una estación son los de su celda»), no las de ``InfoEstacion.macrozona``: ésa es None con ``cod_comuna`` ≤ 0
  (TIP-11) y sirve para los conteos y los estratos. Lo crónico de D22 (b) es de I14 y no toca este módulo.
- TIP-19. **Estratos descriptivos de §5.5** (pedido de I14; VAL-17). ``Estrato`` suma «conjunto», «altitud», «periodo»,
  «tipo», «propietario» y «omm», en el orden de ``validacion.ESTRATOS``, y ``VALOR_ESTRATO_OMM`` («con_indicativo_omm»):
  «con indicativo OMM» es un solo estrato, el que nombra el texto. ``decision`` sigue leyendo sólo «nacional» y
  «macrozona» (DEC-2): los demás no entran a ninguna compuerta. Los rótulos de la tabla SINCA («red», «tercil_tpi») son
  de ``ESQUEMA_SINCA_PUB`` y no son estratos de §5.5: quedan en ``validacion``.
- TIP-20. **Fuera de la grilla** (D34 [delegada], NAS-17; pedidos de I13 e I14, P46). ``fuera_de_la_grilla(info)``: la
  estación entra (no está excluida) y no tiene celda. Es el predicado de ``estaticas_nasadem.fuera_de_la_grilla``, que
  ``candidatos`` y ``validacion`` copian por ahora (no pueden importar ``estaticas_nasadem``); ``test_tipos`` compara
  las tres copias con ésta. Quien vuelva a esos módulos lo toma de aquí.
- TIP-21. **Esquemas de la ola 3.** Copias de las columnas que cada dueño definió en su módulo (``test_tipos`` vigila la
  paridad; quien vuelva al módulo las toma de aquí):
  - publicados (en ``ESQUEMAS``; pasan la guarda de S7 como métrica): ``ESQUEMA_SOPORTE_PUB``
    (``validacion/soporte.parquet``: la fracción sin soporte de los estratos no publicados, VAL-13),
    ``ESQUEMA_DESCRIPTIVOS_PUB`` (``validacion/descriptivos.parquet``, VAL-21) y ``ESQUEMA_SINCA_PUB``
    (``validacion/sinca.parquet``, VAL-19). Su clase de salida queda en la pregunta P42;
  - en memoria, nunca se escriben (``ESQUEMAS_EN_MEMORIA``): ``ESQUEMA_CONTEOS_QC`` (QC-22: una fila por estación × año ×
    variable × clave; ``resumen_qc`` publica sólo sus sumas) y ``ESQUEMA_PREDICCION`` (CAN-15: la corrección del
    candidato en las horas de prueba; R nunca se guarda ni se informa, §0.4.3, y por eso no pasa ninguna guarda).
- TIP-22. **Los estáticos de C** (pedido PED-2 de I13; CAN-9, P-CAN-3). ``ESQUEMA_ESTATICAS_CELDA`` sigue siendo lo que
  da ``estaticas_nasadem.estaticos_celdas`` (NASADEM, GHS y las fracciones). ``ESQUEMA_ESTATICAS_CELDA_C`` le suma
  ``COLUMNA_Z_E5L`` («z_e5l», f8, en m): Σ w_i z_E5L,i con el operador de la celda (A10; los pesos bilineales no
  dependen de la z del uso), que agrega ``orquestacion`` (I20) en M2a antes de escribir ``estaticas/celdas.parquet``
  (insumo, D14). Es la entrada de los estáticos de C (Δz = z_media − z_e5l). Desde la ola 4 está en ``ESQUEMAS``:
  ``test_ceguera.test_s07_esquemas_de_tipos`` (I4) ya la cuenta entre los esquemas que sólo pasan como insumo.
- TIP-23. **Vecinos del núcleo y filas de C** (pedidos PED-1 y PED-4 de I13). ``VecinosNucleo`` lleva los códigos de
  entrenamiento en el orden de ``est``, los ids de grupo en el orden de ``grupo_de`` y el grupo de cada estación de
  entrenamiento (``codigos``, ``grupos`` y ``grupo_est``), que hoy agrega ``candidatos.VecinosEntrenamiento``.
  ``SumasC`` es la muestra fija de una estación y sus sumas (MC-05, MC-45), copia de ``candidatos.SumasC`` con
  paridad de campos, y ``DatosCompetencia.filas_c`` tiene la forma {«C» o «C_est»: {variable: {código: SumasC}}}.
  D33 (la fórmula de ``estaticas_nasadem.estandarizar_tpi`` dentro de la transformación lineal de C) queda con su
  prueba de paridad en ``test_candidatos``, sin sumar la dependencia: es una decisión de interfaz del coordinador.
- TIP-24. **La columna ``tramo`` de la tabla ancha** (QC-20; anotación a A6). Hasta el paso 3 lleva el id del
  ``TramoPolitica`` de lectura (A6). Desde la marca 14 (paso 4) lleva el de la política efectiva (D24,
  ``politicas.tramos_marca_14``): la pieza en que se tomó la mediana de la marca 14 y la que elige ``cargar_dmc`` al
  releer con la efectiva. Así la escribe ``qc_dmc_meteo.tabla_ancha`` en ``qc/estaciones/``.
Depende de: nada (biblioteca estándar).
"""
from __future__ import annotations

import re
from collections.abc import Mapping as _MappingABC
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Iterator, Mapping

if TYPE_CHECKING:  # sólo para las anotaciones; nunca se cargan al importar
    import numpy as np
    import pandas as pd

# ---------------------------------------------------------------------------
# Convenciones de tiempo (§2.1 del diseño)
# ---------------------------------------------------------------------------
EPOCA_H = "2000-01-01T00:00:00+00:00"       # h = 0; d2000 = 0; mes2000 = 0 es enero de ese año
ZONA_CIVIL = "America/Santiago"             # §3: día civil de salud
PARTICION_AGREGADO = "agregado"             # valor de ``particion`` en la validación publicada (P1, P2 o agregado)
# TIP-8 (D9) y TIP-11 (D16): las macrozonas de ``_comun_modelo`` que no son macrozona. Sus horas cuentan sólo en lo
# nacional y se informan aparte.
MACROZONA_SIN_REGION = "sin_region"
MACROZONA_INSULAR = "insular"
MACROZONAS_NINGUNA = frozenset({MACROZONA_SIN_REGION, MACROZONA_INSULAR})


def macrozona_o_ninguna(nombre: str | None) -> str | None:
    """D9 y D16: la macrozona de una estación o celda, o None si no tiene (sin coordenadas legibles, fuera de la
    grilla, en una celda con ``cod_comuna = 0``, cuya macrozona es «sin_region», o en una isla, «insular»). Una hora
    sin macrozona no forma estrato ni cuenta en Q1z, Q2 por macrozona ni Q3 por macrozona; se informa aparte."""
    return None if nombre is None or nombre in MACROZONAS_NINGUNA else nombre


def macrozona_de_celda(macrozona: str | None, cod_comuna) -> str | None:
    """TIP-11 (D9 y D16): la macrozona de una estación o celda desde su celda de ``celdas.parquet``: la columna
    ``macrozona`` y ``cod_comuna``. None sin celda (``cod_comuna`` None o nulo), en una celda sin comuna
    (``cod_comuna`` ≤ 0, cuya macrozona la heredó de otra región) o con macrozona «sin_region» o «insular»."""
    if cod_comuna is None:
        return None
    if isinstance(cod_comuna, (bool, str, bytes)):
        raise TypeError(f"cod_comuna debe ser un entero: {cod_comuna!r}")
    try:
        cod = int(cod_comuna)
    except (TypeError, ValueError):     # pd.NA o NaN: sin celda
        return None
    if cod != cod_comuna:
        raise ValueError(f"cod_comuna no es entero: {cod_comuna!r}")
    return None if cod <= 0 else macrozona_o_ninguna(macrozona)


# ---------------------------------------------------------------------------
# Enumerados (§2.2 del diseño)
# ---------------------------------------------------------------------------
class Variable(StrEnum):
    """Variables del producto (§3)."""
    T = "T"
    TD = "Td"
    U = "u"
    V = "v"
    P = "p"


class Derivada(StrEnum):
    """Derivadas del producto (§3)."""
    HR = "HR"
    RAPIDEZ = "rapidez"
    DIRECCION = "direccion"


class VariableDMC(StrEnum):
    """Nombres de variable del adaptador fijado (``meteorologia_v2.normalizar``)."""
    TS = "Ts"
    TD = "Td"
    HR = "relative_humidity"
    FF = "wind_speed_instant"
    DD = "wind_direction_instant"
    QFE = "QFE"
    QFF = "QFF"
    QNH = "QNH"
    RR06 = "RR06"
    WIND_U = "wind_u"
    WIND_V = "wind_v"


# §2.7 [EMC1-1, EMC1-3]: Q1 de la marca 3 y Q2 se cuentan por variable de la fuente (wind_u y wind_v no entran).
VARIABLES_FUENTE = (VariableDMC.TS, VariableDMC.TD, VariableDMC.HR, VariableDMC.FF, VariableDMC.DD,
                    VariableDMC.QFE, VariableDMC.QFF)
# Columna de la tabla ancha de cada variable de la fuente (§2.3 del diseño).
COLUMNA_ANCHA = MappingProxyType({VariableDMC.TS: "Ts", VariableDMC.TD: "Td", VariableDMC.HR: "HR",
                                  VariableDMC.FF: "FF", VariableDMC.DD: "DD", VariableDMC.QFE: "QFE",
                                  VariableDMC.QFF: "QFF"})
# Columna de marcas de cada variable de la fuente (TIP-9: FF y DD por separado).
COLUMNA_MARCAS = MappingProxyType({VariableDMC.TS: "marcas_Ts", VariableDMC.TD: "marcas_Td",
                                   VariableDMC.HR: "marcas_HR", VariableDMC.FF: "marcas_FF",
                                   VariableDMC.DD: "marcas_DD", VariableDMC.QFE: "marcas_QFE",
                                   VariableDMC.QFF: "marcas_QFF"})


class Candidato(StrEnum):
    """Candidatos de §4. No hay «fondo» ni «sin DMC»: lo prohibido de §0.4.1 y §0.4.2 no se puede nombrar."""
    A = "A"
    B = "B"
    AB = "AB"
    C = "C"
    C_EST = "C_est"


class Uso(StrEnum):
    AMBIENTAL = "ambiental"
    AGUDO = "agudo"
    CRONICO = "cronico"


class Grupo(StrEnum):
    """Grupos de variables con un ganador cada uno (§6.1)."""
    T_TD = "T_Td"
    U_V = "u_v"
    P = "p"


class Particion(StrEnum):
    P1 = "P1"
    P2 = "P2"


class Conjunto(StrEnum):
    """Conjuntos de RELOJ §1 (V, V2 y N)."""
    V = "V"
    V2 = "V2"
    N = "N"


class _MarcaBase(IntEnum):
    """Base de ``Marca``: el bit y el nombre del texto."""

    @property
    def bit(self) -> int:
        """Máscara de la marca en las columnas uint32 ``marcas_*``."""
        return 1 << int(self)

    @property
    def nombre_texto(self) -> str:
        """Nombre de la columna «Marca» de §2.4 («sin_reloj», «fuera_de_rango»…)."""
        return self.name.lower()


# §2.4, en el orden de la tabla: el bit es la posición (TIP-1).
NOMBRES_MARCAS = ("SIN_RELOJ", "SIN_COORDENADAS", "MEDICION_NO_VERIFICADA", "FUERA_DE_RANGO", "CENTINELA", "RACHA",
                  "PICO_O_SALTO", "TD_MAYOR_TS", "TD_RECORTADO", "TD_HR_INCOHERENTE", "TD_DERIVADO",
                  "DIR0_CON_RAPIDEZ", "CALMA_PERSISTENTE", "ERROR_GRUESO", "ALTITUD_INCOHERENTE", "HR_RECORTADA",
                  "BAROMETRO_INHOMOGENEO", "AIRE_SECO_SOSTENIDO", "DESVIO_PERSISTENTE", "CERO_ES_NORTE",
                  "CALMA_SIN_DIRECCION", "SIN_PRUEBA_DE_TRASLADO", "POSIBLE_MEDIA_HORARIA")
Marca = _MarcaBase("Marca", [(nombre, bit) for bit, nombre in enumerate(NOMBRES_MARCAS)], module=__name__,
                   qualname="Marca")


class Alcance(StrEnum):
    """Qué invalida una marca (columna «¿Invalida?» de §2.4)."""
    FILA = "fila"            # «sí, toda la fila»
    VARIABLE = "variable"    # «sí, la variable» (más las arrastradas, si las hay)
    VARIABLES = "variables"  # «sí, Td y HR», «sí, el viento», «sí, QFE del tramo»…: las variables listadas
    NO = "no"                # «no», «no (informa)», «informa»


@dataclass(frozen=True)
class Invalidacion:
    """Fila de la tabla de §2.4: alcance, variables que invalida y lo que arrastra una variable fuente."""
    alcance: Alcance
    variables: tuple[str, ...] = ()
    arrastra: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


_VIENTO = (VariableDMC.FF.value, VariableDMC.DD.value)
_TD_HR = (VariableDMC.TD.value, VariableDMC.HR.value)
INVALIDANTES: Mapping[Any, Invalidacion] = MappingProxyType({
    Marca.SIN_RELOJ: Invalidacion(Alcance.FILA),
    Marca.SIN_COORDENADAS: Invalidacion(Alcance.FILA),
    Marca.MEDICION_NO_VERIFICADA: Invalidacion(Alcance.VARIABLE),
    Marca.FUERA_DE_RANGO: Invalidacion(Alcance.VARIABLE),
    # «sí. Con Ts, también Td y HR de la fila; con QFE, también QFF» (y D7: mira el valor aunque el rango lo quitó)
    Marca.CENTINELA: Invalidacion(Alcance.VARIABLE, arrastra=MappingProxyType({
        VariableDMC.TS.value: _TD_HR, VariableDMC.QFE.value: (VariableDMC.QFF.value,)})),
    Marca.RACHA: Invalidacion(Alcance.VARIABLE),
    Marca.PICO_O_SALTO: Invalidacion(Alcance.VARIABLE),
    Marca.TD_MAYOR_TS: Invalidacion(Alcance.VARIABLES, _TD_HR),
    Marca.TD_RECORTADO: Invalidacion(Alcance.NO),
    Marca.TD_HR_INCOHERENTE: Invalidacion(Alcance.VARIABLES, _TD_HR),
    Marca.TD_DERIVADO: Invalidacion(Alcance.NO),
    Marca.DIR0_CON_RAPIDEZ: Invalidacion(Alcance.VARIABLES, _VIENTO),
    Marca.CALMA_PERSISTENTE: Invalidacion(Alcance.VARIABLES, _VIENTO),
    Marca.ERROR_GRUESO: Invalidacion(Alcance.VARIABLE),
    Marca.ALTITUD_INCOHERENTE: Invalidacion(Alcance.VARIABLES, (VariableDMC.QFE.value,)),
    Marca.HR_RECORTADA: Invalidacion(Alcance.NO),
    Marca.BAROMETRO_INHOMOGENEO: Invalidacion(Alcance.VARIABLES, (VariableDMC.QFE.value, VariableDMC.QFF.value)),
    Marca.AIRE_SECO_SOSTENIDO: Invalidacion(Alcance.VARIABLES, (VariableDMC.HR.value, VariableDMC.TD.value)),
    Marca.DESVIO_PERSISTENTE: Invalidacion(Alcance.NO),
    Marca.CERO_ES_NORTE: Invalidacion(Alcance.NO),
    Marca.CALMA_SIN_DIRECCION: Invalidacion(Alcance.NO),
    Marca.SIN_PRUEBA_DE_TRASLADO: Invalidacion(Alcance.NO),
    Marca.POSIBLE_MEDIA_HORARIA: Invalidacion(Alcance.NO),          # TIP-4
})
# §2.7, Q1: «una marca invalidante de §2.4 (bits 3-17)» (TIP-2).
MARCAS_Q1 = tuple(m for m in Marca
                  if Marca.FUERA_DE_RANGO <= m <= Marca.AIRE_SECO_SOSTENIDO and INVALIDANTES[m].alcance is not Alcance.NO)
# §2.7 [EMC1-1]: motivo de cargar_dmc que es el numerador de Q1 de la marca 3.
RAZON_FUERA_DE_RANGO = "documented_numeric_range_rejected"


class OrigenTd(IntEnum):
    SIN_VALOR = -1           # TIP-3
    OBSERVADO = 0
    RECORTADO = 1
    DERIVADO = 2


class OrigenHR(IntEnum):
    SIN_VALOR = -1
    OBSERVADO = 0
    RECORTADO = 1


class OrigenViento(IntEnum):
    SIN_VALOR = -1
    OBSERVADO = 0
    CERO_ES_NORTE = 1
    CALMA_SIN_DIRECCION = 2


class FuenteZs(StrEnum):
    """De dónde sale z_s (§2.5): el catálogo, o NASADEM bilineal sin z_cat legible."""
    CATALOGO = "catalogo"
    NASADEM = "nasadem"


class CasoZE5L(StrEnum):
    """Los tres casos de z_E5L (§4.1)."""
    GEOPOTENCIAL = "geopotencial"
    NASADEM = "nasadem"
    HIPSOMETRICA = "hipsometrica"


class Estadistico(StrEnum):
    """Estadísticos de K4 (§2.5)."""
    T2A = "T2a"
    T2B = "T2b"


class ClaseQuiebre(StrEnum):
    TRASLADO = "traslado"
    BAROMETRO = "barometro"
    METODO_REDUCCION = "metodo_reduccion"


class Prueba(StrEnum):
    TF1 = "TF1"
    TF2 = "TF2"


class ResultadoTF(StrEnum):
    PASA = "pasa"
    FALLA = "falla"
    NO_EVALUABLE = "no_evaluable"


class ReglaRedConstante(StrEnum):
    """Regla de la red constante de TF2 que rigió (§5.7); ``NINGUNA`` si TF2 no es evaluable (TIP-6)."""
    R2000_2025 = "r2000_2025"
    R2003_2025 = "r2003_2025"
    R2010_2025 = "r2010_2025"
    NINGUNA = "ninguna"


class Compuerta(StrEnum):
    DERIVA = "deriva"
    FINITUD = "finitud"
    TF = "TF"
    CD = "CD"
    EX = "EX"
    MZ = "MZ"
    NIVEL = "nivel"
    ANOMALIA = "anomalia"


class Alarma(StrEnum):
    Q1 = "Q1"
    Q1Z = "Q1z"
    Q2 = "Q2"
    Q3 = "Q3"


class Variante(StrEnum):
    """Anexo B: integrado (I) o covariables separadas (D)."""
    I = "I"  # noqa: E741
    D = "D"


class Rama(IntEnum):
    """Ramas cerradas del Anexo B."""
    UNO = 1
    DOS = 2
    TRES = 3  # no-umbral: numeración de las ramas del Anexo B


class MotivoNoNormalizable(StrEnum):
    """Motivo de un artefacto «no normalizable» (§2.1), normalizado desde el texto del error (MC-21)."""
    DD_FUERA_DE_DOMINIO = "dd_fuera_de_dominio"
    RAPIDEZ_NEGATIVA = "rapidez_negativa"
    HORA_NO_NATIVA_O_REPETIDA = "hora_no_nativa_o_repetida"
    CODIGO_QC_PRESENTE = "codigo_qc_presente"
    INTERVALO_NO_ENTERO = "intervalo_no_entero"
    LIMITE_NO_PYTHON = "limite_no_python"
    SHA_O_TAMANO = "sha_o_tamano"
    SIN_OBSERVACIONES = "sin_observaciones"
    OTRO = "otro"


class OrigenAborto(StrEnum):
    """MC-21: «datos» si ``normalizar`` aborta también sin política; si no, «regla»."""
    DATOS = "datos"
    REGLA = "regla"


class Modo(StrEnum):
    """Modos del ejecutable (§8)."""
    SINTETICO = "sintetico"
    ESTATICOS = "estaticos"
    APLICAR = "aplicar"
    PRODUCIR = "producir"
    M6 = "m6"


class Sentido(StrEnum):
    """Sentido de una comparación del Anexo B: qué variante reemplaza a cuál."""
    I_FRENTE_A_D = "I_frente_a_D"
    D_FRENTE_A_I = "D_frente_a_I"


class Protocolo(StrEnum):
    """Protocolos de validación de v2 que usa el Anexo B."""
    LRO = "LRO"
    BLQ_75 = "BLQ-75"


class DisenoC(StrEnum):
    """Diseño de C (§4.6) y de C_est (§4.7)."""
    ESTADO = "estado"
    CLIMATOLOGICO = "climatologico"


class MotivoExclusion(StrEnum):
    """Por qué una estación queda fuera del entrenamiento y de la evaluación (TIP-14; NAS-12, NAS-16, A8, PAR-1). En
    el orden de precedencia de ``estaticas_nasadem.MOTIVOS``, con «sin_fondo» al final."""
    COORDENADAS_ILEGIBLES = "coordenadas_ilegibles"
    COORDENADAS_FUERA_DE_RANGO = "coordenadas_fuera_de_rango"     # fuera del rango de RELOJ §3.3 (NAS-1)
    SIN_NASADEM = "sin_nasadem"                                   # ninguna tesela NASADEM a ≤ ρ (D37, NAS-16)
    K3 = "k3"
    SIN_Z_S = "sin_z_s"                                           # coordenadas confirmadas, sin altitud (NAS-11)
    SIN_FONDO = "sin_fondo"                                       # lo pone orquestacion (A8)


# §2.7, Q2: los motivos que cuentan como «K3 deja sin coordenadas» (NAS-12; D36).
MOTIVOS_SIN_COORDENADAS_K3 = frozenset({MotivoExclusion.COORDENADAS_ILEGIBLES.value,
                                        MotivoExclusion.COORDENADAS_FUERA_DE_RANGO.value, MotivoExclusion.K3.value})
# §2.7, Q2 (D37): los que salen del numerador y del denominador y se informan aparte. Disjunto del anterior.
MOTIVOS_FUERA_DE_Q2 = frozenset({MotivoExclusion.SIN_NASADEM.value})


class VariableMetrica(StrEnum):
    """Rótulos de ``variable`` en ``ESQUEMA_VALIDACION_PUB`` y ``ESQUEMA_TF`` (TIP-15; SIN-14, DEC-1)."""
    T = "T"
    TD = "Td"
    HR = "HR"
    RAPIDEZ = "rapidez"
    UV = "uv"                      # RMSE vectorial de (u, v) (§5.2)
    P = "p"
    TEMP_MEDIA = "temp_media"      # columnas de meteo_civil_v3 (§5.2, §5.8)
    HR_MEDIA = "hr_media"


class Estrato(StrEnum):
    """Rótulos de ``estrato`` de ``ESQUEMA_VALIDACION_PUB`` (TIP-15, TIP-19). La regla de decisión sólo lee «nacional» y
    «macrozona» (DEC-2); los demás son los estratos descriptivos de §5.5 (VAL-17), en el orden de
    ``validacion.ESTRATOS``."""
    NACIONAL = "nacional"
    MACROZONA = "macrozona"
    CONJUNTO = "conjunto"
    ALTITUD = "altitud"
    PERIODO = "periodo"
    TIPO = "tipo"
    PROPIETARIO = "propietario"
    OMM = "omm"


# TIP-19: el único valor del estrato «omm» (§5.5: «con indicativo OMM»).
VALOR_ESTRATO_OMM = "con_indicativo_omm"


# TIP-15 (D9, D16): las macrozonas que forman estrato y rigen en MZ (MACROZONA_CODIGO menos MACROZONAS_NINGUNA).
MACROZONAS = ("norte_grande", "norte_chico", "centro", "sur", "austral")
# TIP-18 (D22 (a)): la codificación de ``macrozona_cod`` (``_comun_modelo.MACROZONA_CODIGO``, comparada por AST en
# ``test_tipos``): las cinco macrozonas en su orden y después «sin_region» e «insular».
MACROZONA_COD: Mapping[str, int] = MappingProxyType(
    {m: i for i, m in enumerate((*MACROZONAS, MACROZONA_SIN_REGION, MACROZONA_INSULAR))})


def indicadoras_macrozona(macrozona_cod) -> tuple[int, ...]:
    """TIP-18 (D22 (a)): las indicadoras de macrozona de C (§4.6), una por macrozona de ``MACROZONAS`` y en su orden,
    desde el ``macrozona_cod`` de la celda tal como está en la grilla (con la macrozona heredada en las celdas con
    ``cod_comuna`` ≤ 0). Con «sin_region» o «insular», todas en 0. Un código que no está en ``MACROZONA_COD`` o que no
    es entero es un error."""
    if isinstance(macrozona_cod, (bool, str, bytes)) or macrozona_cod is None:
        raise TypeError(f"macrozona_cod debe ser un entero: {macrozona_cod!r}")
    try:
        cod = int(macrozona_cod)
    except (TypeError, ValueError) as error:          # pd.NA, NaN u otro objeto
        raise TypeError(f"macrozona_cod debe ser un entero: {macrozona_cod!r}") from error
    if cod != macrozona_cod:
        raise ValueError(f"macrozona_cod no es entero: {macrozona_cod!r}")
    if cod not in MACROZONA_COD.values():
        raise ValueError(f"macrozona_cod {cod} no está en la codificación de la grilla {dict(MACROZONA_COD)}")
    return tuple(int(MACROZONA_COD[m] == cod) for m in MACROZONAS)
# Anexo B (DEC-17): contaminantes de M6 y la clave de la variante de ozono.
CONTAMINANTES_M6 = ("pm25", "no2")
CLAVE_O3 = "O3"
# Versiones de los registros de la decisión (DEC-18).
VERSION_DECISION = "meteo-combinada-decision/1"
VERSION_DECISION_M6 = "meteo-combinada-decision-m6/1"


# Columnas de las tablas laterales (§7.1, MC-28): sufijos de ``el_*``, con prefijo ``mc_`` (I) o ``fe_`` (D).
SUFIJOS_EL = ("t2m", "d2m", "rh", "sp", "u10", "v10", "wind", "wdir_sin", "wdir_cos")
UNIDADES_EL = MappingProxyType({"t2m": "K", "d2m": "K", "rh": "%", "sp": "Pa", "u10": "m/s", "v10": "m/s",
                                "wind": "m/s", "wdir_sin": "1", "wdir_cos": "1"})
COLUMNAS_R_D = ("dmc_R_T", "dmc_R_Td", "dmc_R_u", "dmc_R_v", "dmc_R_p")
UNIDADES_R_D = MappingProxyType({"dmc_R_T": "K", "dmc_R_Td": "K", "dmc_R_u": "m/s", "dmc_R_v": "m/s",
                                 "dmc_R_p": "1"})
LULC = ("lulc_urbano", "lulc_cultivo", "lulc_bosque", "lulc_matorral_pastizal", "lulc_desnudo", "lulc_agua",
        "lulc_nieve_hielo")      # TIP-7
VARIABLES_SINCA = ("TEMP", "RHUM", "WSPD", "WDIR")       # MC-10, punto 6

# Tabla larga de ``dmc_features.cargar_dmc`` (código fijado): no se redefine; qc_dmc_meteo exige estas columnas
# y estas claves de su ``meta`` (§2.3 del diseño).
COLUMNAS_LARGA_DMC = ("station_code", "timestamp_source", "timestamp_utc", "variable", "value", "unit", "raw",
                      "parse_status", "source_qc", "clock_verified", "coordinates_verified", "measurement_verified",
                      "model_ready", "usable", "quality_reason")
META_LARGA_DMC = ("long_content_sha256", "policies_sha256", "adapter_sha256")


# ---------------------------------------------------------------------------
# Identificadores (§2.1 del diseño)
# ---------------------------------------------------------------------------
PATRON_CODIGO = re.compile(r"\d{6}")
PATRON_GRUPO = re.compile(r"G\d{6}")
PATRON_TRAMO_RELOJ = re.compile(r"[1-9]\d*\.[1-9]\d*")
PATRON_TRAMO = re.compile(r"(?P<reloj>[1-9]\d*\.[1-9]\d*)/(?P<k>[1-9]\d*)")
PATRON_BLOQUE = re.compile(r"(?P<ie>-?\d+)_(?P<in>-?\d+)")
PATRON_PLIEGUE = re.compile(r"(?P<externo>P1-\d|P2--?\d+_-?\d+)(?:/i(?P<interno>\d))?")


def id_grupo(codigos) -> str:
    """«G» + el menor código del grupo a ≤ 2 km."""
    codigos = sorted(codigos)
    if not codigos or not all(isinstance(c, str) and PATRON_CODIGO.fullmatch(c) for c in codigos):
        raise ValueError("un grupo necesita códigos de 6 dígitos")
    return "G" + codigos[0]


def id_tramo(tramo_reloj: str, k: int) -> str:
    """«<id de tramo de RELOJ>/<k>», con k ≥ 1 contando los cortes de K4 y de los años G dentro del tramo."""
    if not isinstance(tramo_reloj, str) or not PATRON_TRAMO_RELOJ.fullmatch(tramo_reloj):
        raise ValueError(f"id de tramo de RELOJ inválido: {tramo_reloj!r}")
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError(f"k de un tramo de política debe ser un entero ≥ 1: {k!r}")
    return f"{tramo_reloj}/{k}"


def id_bloque(ie: int, i_n: int) -> str:
    """«<ie>_<in>», con ie = ⌊E/75.000⌋ e in = ⌊N/75.000⌋ en EPSG:32719 (los índices los calcula particiones)."""
    for x in (ie, i_n):
        if isinstance(x, bool) or not isinstance(x, int):
            raise ValueError("los índices de bloque son enteros")
    return f"{ie}_{i_n}"


def id_pliegue_p1(k: int) -> str:
    return f"P1-{k}"


def id_pliegue_p2(bloque: str) -> str:
    if not PATRON_BLOQUE.fullmatch(bloque):
        raise ValueError(f"bloque inválido: {bloque!r}")
    return f"P2-{bloque}"


def id_interno(externo: str, j: int) -> str:
    """Pliegue interno j de un externo: «<externo>/i<j>»."""
    return f"{externo}/i{j}"


# ---------------------------------------------------------------------------
# Esquemas (§2.3 del diseño)
# ---------------------------------------------------------------------------
class Esquema(_MappingABC):
    """Columnas → tipo de pandas, en orden, con su nombre y su versión. Inmutable."""
    __slots__ = ("nombre", "version", "_columnas")

    def __init__(self, nombre: str, version: str, columnas: Mapping[str, str]):
        object.__setattr__(self, "nombre", nombre)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "_columnas", MappingProxyType(dict(columnas)))

    def __setattr__(self, nombre, valor):
        raise AttributeError("Esquema es inmutable")

    def __getitem__(self, columna: str) -> str:
        return self._columnas[columna]

    def __iter__(self) -> Iterator[str]:
        return iter(self._columnas)

    def __len__(self) -> int:
        return len(self._columnas)

    def __repr__(self) -> str:
        return f"Esquema({self.nombre!r}, {self.version!r}, {len(self)} columnas)"


def _version(nombre: str) -> str:
    return f"meteo-combinada-{nombre.replace('_', '-')}/1"


def _esquema(nombre: str, columnas: Mapping[str, str], version: str | None = None) -> Esquema:
    return Esquema(nombre, version or _version(nombre), columnas)


_F4, _F8 = "float32", "float64"

ESQUEMA_QC_ESTACION = _esquema("qc_estacion", {        # qc/estaciones/<código>.parquet; una fila por hora con reporte
    "h": "int32", "ts_fuente": "string", "id_artefacto": "int32", "tramo": "string",   # tramo: el de la efectiva (TIP-24)
    "Ts": _F4, "Td": _F4, "HR": _F4, "FF": _F4, "DD": _F4, "QFE": _F4, "QFF": _F4,
    "td_final": _F4, "hr_final": _F4, "u_final": _F4, "v_final": _F4,
    "origen_td": "int8", "origen_hr": "int8", "origen_viento": "int8",
    "marcas_Ts": "uint32", "marcas_Td": "uint32", "marcas_HR": "uint32", "marcas_FF": "uint32",
    "marcas_DD": "uint32", "marcas_QFE": "uint32", "marcas_QFF": "uint32",
    "valido_T": "bool", "valido_Td": "bool", "valido_HR": "bool", "valido_viento": "bool", "valido_p": "bool",
    "rr06_mm": _F4, "rr06_valido": "bool",
})

ESQUEMA_ESTACIONES_MC = _esquema("estaciones_mc", {    # estaticas/estaciones.parquet (M2a); = InfoEstacion
    "codigo": "string", "nombre": "string", "conjunto": "string", "macrozona": "string", "grupo": "string",
    "omm": "boolean", "tipo": "string", "propietario": "string",
    "lat_txt": "string", "lon_txt": "string", "alt_txt": "string", "lat": _F8, "lon": _F8, "z_cat": _F8,
    "rho_km": _F8, "k3_pasa": "bool", "z_s": _F8, "z_s_fuente": "string",
    "celda": "Int64", "utm_e": _F8, "utm_n": _F8, "bloque": "string",
    "pix0": "int32", "pix1": "int32", "pix2": "int32", "pix3": "int32",
    "w0": _F8, "w1": _F8, "w2": _F8, "w3": _F8, "respaldo_16km": "bool", "sin_fondo": "bool",
    "excluida": "bool", "motivo": "string",
})

ESQUEMA_ESTATICAS_CELDA = _esquema("estaticas_celda", {    # estaticas/celdas.parquet (M2a)
    "celda": "int64", "z_media": _F8, "z_poblada": _F8, "z_poblada_es_media": "bool", "frac_dato": _F8,
    "tpi1": _F8, "tpi5": _F8, "tpi1_truncado": "bool", "tpi5_truncado": "bool", "pendiente_deg": _F8,
    "log_dist_costa": _F8, **{c: _F8 for c in LULC}, "lat": _F8, "macrozona_cod": "int8", "cod_comuna": "int32",
})

ESQUEMA_ZE5L = _esquema("ze5l", {                     # estaticas/z_e5l.parquet (M2a)
    "pixel_id": "int64", "valido": "bool", "z_e5l": _F8, "caso": "string", "z_nasadem": _F8,
    "frac_nasadem": _F8, "z_hipso": _F8, "dif_mayor_50m": "bool",
})

ESQUEMA_PUNTOS_E5L = _esquema("puntos_e5l", {         # insumos/puntos_estacion/<código>.parquet (M2a; insumo)
    "h": "int32", "T_F": _F4, "Td_F": _F4, "p_F": _F4, "u_F": _F4, "v_F": _F4, "amp_TF": _F4,
})

ESQUEMA_CLIMA_ESTADO = _esquema("clima_estado", {     # insumos/clima_estado.parquet (M2a; para C_est)
    "pixel_id": "int64", "mes": "int8", "hora": "int8", "T": _F4, "T_menos_Td": _F4, "rapidez": _F4, "amp": _F4,
})
# TIP-17: las variables del estado climatológico (las columnas de ESQUEMA_CLIMA_ESTADO sin las claves), en su orden.
VARIABLES_CLIMA_ESTADO = tuple(c for c in ESQUEMA_CLIMA_ESTADO if c not in ("pixel_id", "mes", "hora"))

ESQUEMA_RESIDUOS = _esquema("residuos", {             # producto/residuos/<código>.parquet (M3-4; insumo restringido)
    "h": "int32", "r_T": _F4, "r_Td": _F4, "r_u": _F4, "r_v": _F4, "r_p": _F4, "rt_T": _F4, "rt_Td": _F4,
    "g_T": "int8", "g_Td": "int8", "observada": "bool", "interpolable": "bool",
})

ESQUEMA_TRAMOS_HOMOGENEOS = _esquema("tramos_homogeneos", {   # producto/tramos_homogeneos.parquet
    "codigo": "string", "variable": "string", "g": "int8", "desde_mes": "int32", "hasta_mes": "int32",
    "delta": _F8,
})

ESQUEMA_CLIMA_A = _esquema("clima_a", {               # producto/clima_a.parquet
    "codigo": "string", "variable": "string", "mes": "int8", "hora": "int8", "rbar": _F8, "califica": "bool",
})

ESQUEMA_EVALUACIONES = _esquema("evaluaciones", {     # validacion/_interno/evaluaciones.parquet (interna)
    "codigo": "string", "particion": "string", "pliegue": "string", "candidato": "string", "uso": "string",
    "variable": "string", "n_horas": "int32", "n_dias": "int32", "n_anios": "int32",
    "mse_h": _F8, "mae_h": _F8, "sesgo_h": _F8, "mse_dia": _F8, "mse_estrato": _F8, "mse_anual_neto": _F8,
    "mse_anomalia": _F8, "cd": _F8, "ex": _F8, "frac_sin_soporte": _F8,
})

ESQUEMA_VALIDACION_PUB = _esquema("validacion_pub", {     # validacion/puntajes.parquet
    "uso": "string", "grupo": "string", "variable": "string", "candidato": "string", "particion": "string",
    "S": _F8, "CD": _F8, "EX": _F8, "nivel": _F8, "anomalia": _F8, "estrato": "string", "valor_estrato": "string",
    "n_evaluaciones": "int32", "n_estaciones": "int32", "publicable": "bool",     # TIP-10
})

ESQUEMA_BANDAS_PUB = _esquema("bandas_pub", {         # validacion/bandas.parquet (TIP-5)
    "uso": "string", "variable": "string", "banda": "string", "candidato": "string", "pi_mon": _F8, "pi_pob": _F8,
    "frac_sin_soporte": _F8,
})

ESQUEMA_REPLICAS = _esquema("replicas", {             # S por réplica del remuestreo y candidato (§5.4); en memoria
    "replica": "int32", "candidato": "string", "S": _F8,
})

ESQUEMA_TF = _esquema("tf", {                         # tendencias/resumen_tf.parquet
    "candidato": "string", "uso": "string", "variable": "string", "prueba": "string", "media_pond": _F8,
    "p95_pond": _F8, "cota_media": _F8, "cota_p95": _F8, "resultado": "string", "regla_red": "string",
    "n_red": "int32",
})

ESQUEMA_NO_NORMALIZABLES = _esquema("no_normalizables", {     # qc/no_normalizables.csv; sin valores
    "id_artefacto": "int32", "codigo": "string", "anio": "int16", "mes": "int8", "macrozona": "string",
    "conjunto": "string", "motivo": "string", "origen": "string",
})

ESQUEMA_LATERAL_I = _esquema("lateral_i", {           # ambiental/lateral_<pol>_I.parquet
    "estacion": "string", "ts_utc": "datetime64[ns, UTC]", **{f"mc_{s}": _F4 for s in SUFIJOS_EL},
})

ESQUEMA_LATERAL_D = _esquema("lateral_d", {           # ambiental/lateral_<pol>_D.parquet: 9 fe_* + 5 dmc_R_* = 14
    "estacion": "string", "ts_utc": "datetime64[ns, UTC]", **{f"fe_{s}": _F4 for s in SUFIJOS_EL},
    **{c: _F4 for c in COLUMNAS_R_D},
})

# Metadatos de una tabla lateral (§2.3 del diseño): los que exige unir_sidecar, y más.
METADATOS_LATERAL = ("model_ready", "source_policy_verified", "policy_sha256", "variante", "columnas", "unidades",
                     "content_sha256", "decision_sha256", "operador_sha256", "panel_sha256", "pliegues_sha256")

ESQUEMA_METEO_DIARIA = _esquema("meteo_diaria", {     # salud/{civil,utc4,regional,representatividad}/meteo_<año>
    "cod_comuna": "int32", "dia": "int32", "temp_media": _F8, "temp_min": _F8, "temp_max": _F8, "hr_media": _F8,
    "td_media": _F8, "precip_mm": _F8, "n_horas": "int8", "n_horas_esperadas": "int8", "faltan_horas": "bool",
}, version="meteo-diaria-v3/1")                        # la de meteo_civil_v3 (S8 la compara por AST)

ESQUEMA_CRONICO = _esquema("cronico", {               # salud/cronico/temperatura_anual.parquet
    "cod_comuna": "int32", "anio": "int16", "temp_media_anual": _F8, "temp_media_fria": _F8,
})

ESQUEMA_SINCA_HORA = _esquema("sinca_hora", {         # series SINCA en memoria (§5.6)
    "estacion": "string", "h": "int32", "variable": "string", "valor": _F8, "valido": "bool", "serie": "string",
})

ESQUEMA_COMPARACION_M6 = _esquema("comparacion_m6", {     # interfaz con v2 (MC-30); una fila por pol × sentido × protocolo
    "contaminante": "string", "sentido": "string", "protocolo": "string",
    "delta_r2": _F8, "ic_bajo": _F8, "ic_alto": _F8,
    "segunda_prueba_coincide": "bool", "supera_ruido": "bool", "consistencia_e2": "bool", "sobrevive_bloque": "bool",
    "signo_sin_ponderar": "bool", "signo_log": "bool", "decision_sigma2": "bool",
    "nmb_c": _F8, "nmb_otra": _F8,
})

# TIP-21 (ola 3): publicados por validacion (copias de COLUMNAS_SOPORTE, COLUMNAS_DESCRIPTIVOS y COLUMNAS_SINCA).
ESQUEMA_SOPORTE_PUB = _esquema("soporte_pub", {       # validacion/soporte.parquet: lo único de un estrato no publicado
    "uso": "string", "grupo": "string", "variable": "string", "candidato": "string", "particion": "string",
    "estrato": "string", "valor_estrato": "string", "frac_sin_soporte": _F8, "publicable": "bool",
})

ESQUEMA_DESCRIPTIVOS_PUB = _esquema("descriptivos_pub", {     # validacion/descriptivos.parquet (VAL-21), en lo nacional
    "uso": "string", "grupo": "string", "variable": "string", "candidato": "string", "particion": "string",
    "descriptivo": "string", "valor": _F8, "n_evaluaciones": "int32", "n_estaciones": "int32",
})

ESQUEMA_SINCA_PUB = _esquema("sinca_pub", {           # validacion/sinca.parquet (§5.6, VAL-19)
    "uso": "string", "candidato": "string", "lugar": "string", "variable": "string", "metrica": "string",
    "estrato": "string", "valor_estrato": "string", "valor": _F8, "n_estaciones": "int32",
})

# TIP-22: los estáticos de C, con la altitud del fondo en la celda (en ESQUEMAS desde la ola 4; sólo pasa como insumo).
COLUMNA_Z_E5L = "z_e5l"
ESQUEMA_ESTATICAS_CELDA_C = _esquema("estaticas_celda_c", {**ESQUEMA_ESTATICAS_CELDA, COLUMNA_Z_E5L: _F8})

ESQUEMAS: Mapping[str, Esquema] = MappingProxyType({e.nombre: e for e in (
    ESQUEMA_QC_ESTACION, ESQUEMA_ESTACIONES_MC, ESQUEMA_ESTATICAS_CELDA, ESQUEMA_ZE5L, ESQUEMA_PUNTOS_E5L,
    ESQUEMA_CLIMA_ESTADO, ESQUEMA_RESIDUOS, ESQUEMA_TRAMOS_HOMOGENEOS, ESQUEMA_CLIMA_A, ESQUEMA_EVALUACIONES,
    ESQUEMA_VALIDACION_PUB, ESQUEMA_BANDAS_PUB, ESQUEMA_REPLICAS, ESQUEMA_TF, ESQUEMA_NO_NORMALIZABLES, ESQUEMA_LATERAL_I,
    ESQUEMA_LATERAL_D, ESQUEMA_METEO_DIARIA, ESQUEMA_CRONICO, ESQUEMA_SINCA_HORA, ESQUEMA_COMPARACION_M6,
    ESQUEMA_SOPORTE_PUB, ESQUEMA_DESCRIPTIVOS_PUB, ESQUEMA_SINCA_PUB, ESQUEMA_ESTATICAS_CELDA_C)})

# TIP-21: tablas que sólo viven en memoria (nunca se escriben).
ESQUEMA_CONTEOS_QC = _esquema("conteos_qc", {         # QC-22: estación × año × variable × clave
    "codigo": "string", "conjunto": "string", "macrozona": "string", "anio": "int16", "variable": "string",
    "clave": "string", "n": "int64",
})
ESQUEMA_PREDICCION = _esquema("prediccion", {         # CAN-15: R en las horas de prueba (§0.4.3: nunca se guarda)
    "codigo": "string", "h": "int32", "correccion": _F8, "soporte": "bool",
})
ESQUEMAS_EN_MEMORIA: Mapping[str, Esquema] = MappingProxyType({e.nombre: e for e in (
    ESQUEMA_CONTEOS_QC, ESQUEMA_PREDICCION)})


def validar_esquema(df, esquema: Mapping[str, str], *, nombre: str) -> None:
    """Exige exactamente esas columnas, en ese orden y con esos tipos (``str(df[c].dtype)``); si no, ValueError."""
    columnas = list(df.columns)
    if columnas != list(esquema):
        raise ValueError(f"{nombre}: columnas {columnas} distintas del esquema {list(esquema)}")
    distintos = {c: (str(df[c].dtype), t) for c, t in esquema.items() if str(df[c].dtype) != t}
    if distintos:
        raise ValueError(f"{nombre}: tipos distintos del esquema (actual, esperado): {distintos}")


def tabla_vacia(esquema: Mapping[str, str]) -> "pd.DataFrame":
    """DataFrame vacío con las columnas y tipos del esquema, y su versión en ``attrs["esquema"]``."""
    import pandas as pd      # sólo al llamarse (la base no carga pandas al importarse)
    df = pd.DataFrame({c: pd.Series(dtype=t) for c, t in esquema.items()})
    if isinstance(esquema, Esquema):
        df.attrs["esquema"] = esquema.version
    return df


# ---------------------------------------------------------------------------
# Clases de datos que cruzan fases (§2.4 del diseño)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class InfoEstacion:
    """La fila de ``ESQUEMA_ESTACIONES_MC`` en memoria (mismos nombres y orden). NaN donde no hay número."""
    codigo: str
    nombre: str
    conjunto: str
    macrozona: str | None         # None: sin macrozona (D9 y D16: sólo cuenta en lo nacional; macrozona_de_celda)
    grupo: str
    omm: bool | None
    tipo: str | None
    propietario: str | None
    lat_txt: str
    lon_txt: str
    alt_txt: str | None
    lat: float
    lon: float
    z_cat: float                  # NaN sin z_cat legible
    rho_km: float
    k3_pasa: bool
    z_s: float
    z_s_fuente: str               # FuenteZs
    celda: int | None             # None: fuera de la grilla
    utm_e: float
    utm_n: float
    bloque: str
    pix0: int                     # −1 si no hay vecino
    pix1: int
    pix2: int
    pix3: int
    w0: float
    w1: float
    w2: float
    w3: float
    respaldo_16km: bool
    sin_fondo: bool
    excluida: bool
    motivo: str | None


def fuera_de_la_grilla(info: InfoEstacion) -> bool:
    """TIP-20 (D34, NAS-17): la estación entra (no está excluida) y no tiene celda. Entrena A, B y AB, no entra en C ni
    en C_est (sin estáticos) y sale de la evaluación de todos los candidatos, contada aparte."""
    return not info.excluida and info.celda is None


@dataclass(frozen=True)
class ErrataConfirmada:
    """La errata que corrige la política de RELOJ, como la cita el registro de C5 (TIP-13; POL-1)."""
    ruta: str                     # por alias de AP o APH
    sha256: str                   # del archivo de la errata
    commit: str                   # 40 hexadecimales; que sea antecesor de origin/main lo comprueba I22 con git


@dataclass(frozen=True)
class RegistroReloj:
    """Registro de la política de RELOJ en C5 (§2.1, precondición 1; RELOJ Enmienda 2, E2-4)."""
    ruta: str                     # alias del registro_politica_reloj.json
    sha256_politica: str
    sha256_artefactos: str
    commit_c5: str
    post_hoc: bool
    errata_post_c4: bool
    errata_confirmada: ErrataConfirmada | None = None     # la errata que corrige la política, si la hay (TIP-13)


@dataclass(frozen=True)
class TramoPolitica:
    """Tramo de política de lectura de una estación (§2.5, «Tramos»)."""
    codigo: str
    id: str                       # «<tramo de RELOJ>/<k>»
    valid_from: str               # etiqueta ingenua «AAAA-MM-DDTHH:MM:SS», inclusiva
    valid_to: str
    clock: Mapping[str, Any]      # la regla de RELOJ, copiada sin cambios
    coordenadas_confirmadas: bool
    motivo: str | None = None


@dataclass(frozen=True, eq=False)
class ResultadoArtefacto:
    """Resultado del paso 1 de §2.1 para un artefacto."""
    id_artefacto: int
    codigo: str
    anio: int
    mes: int
    content_sha256: str | None
    larga: "pd.DataFrame | None" = None       # tabla larga de cargar_dmc; None si no es normalizable
    meta: Mapping[str, Any] | None = None
    motivo: MotivoNoNormalizable | None = None
    origen: OrigenAborto | None = None
    reglas_rechazadas: tuple[str, ...] = ()   # ids de tramo que validar_regla_reloj_dmc rechazó

    @property
    def normalizable(self) -> bool:
        return self.motivo is None


@dataclass(frozen=True)
class Quiebre:
    """Un quiebre de K4 o de los tramos homogéneos (§2.5, §4.8)."""
    estadistico: str              # Estadistico (K4) o variable del residuo (§4.8)
    mes: int                      # mes2000 del primer mes del tramo nuevo (k)
    D: float
    clase: ClaseQuiebre | None = None


@dataclass(frozen=True)
class ResultadoK4:
    """K4 de una estación: quiebres, el último traslado y el último quiebre de barómetro (meses2000)."""
    codigo: str
    quiebres: tuple[Quiebre, ...]
    ultimo_traslado: int | None
    ultimo_barometro: int | None
    sin_prueba: bool              # marca 21: sin QFE válida


@dataclass(frozen=True)
class Hiper:
    """Hiperparámetros del núcleo (§4.2)."""
    L_km: float
    lam: float
    kappa: float


@dataclass(frozen=True, eq=False)
class OperadorPuntos:
    """Operador del fondo para estaciones, celdas o píxeles (§4.1). ``pix`` = −1 donde no hay vecino."""
    ids: "np.ndarray"
    z: "np.ndarray"
    pix: "np.ndarray"             # n × 4, int32
    w: "np.ndarray"               # n × 4, float64 (renormalizados)
    dz: "np.ndarray"              # n × 4, float64: z_x − z_i en m
    respaldo: "np.ndarray"        # n, bool: vecino a ≤ 16 km en vez de bilineal


@dataclass(frozen=True, eq=False)
class VecinosNucleo:
    """Vecinos fijos de cada punto en d_ef (§4.2); la disponibilidad se aplica hora a hora (TIP-23)."""
    puntos: "np.ndarray"
    est: "np.ndarray"             # n × 30, int32 (índice de estación de entrenamiento; −1 si no hay)
    d_ef: "np.ndarray"            # n × 30, float64
    grupo_de: "np.ndarray"        # n × 30, int32 (índice del grupo a ≤ 2 km de cada vecino)
    hiper: Hiper
    codigos: tuple[str, ...]      # TIP-23: los códigos de entrenamiento, en el orden de los índices de ``est``
    grupos: tuple[str, ...]       # los ids de grupo, en el orden de los índices de ``grupo_de``
    grupo_est: "np.ndarray"       # int32: el índice de grupo de cada estación de entrenamiento (CAN-2)


@dataclass(frozen=True, eq=False)
class SumasC:
    """Muestra fija de una estación y sus sumas ponderadas sobre el diseño en bruto de C o C_est (§4.6, MC-05, MC-45;
    TIP-23, copia de ``candidatos.SumasC``)."""
    codigo: str
    variable: str
    diseno: "DisenoC"
    xtx: "np.ndarray"             # monomio × monomio, Σ w x xᵀ
    xty: "np.ndarray"             # Σ w x y
    yty: float                    # Σ w y²
    n_filas: int                  # n_s (MC-05)
    peso: float                   # mín(C_FILAS/n_s; C_PESO_MAX)
    horas: "np.ndarray"           # horas de la muestra (int64, crecientes)


@dataclass(frozen=True)
class Pliegue:
    """Pliegue externo de P1 o P2, o interno de la selección anidada (§4.9, §5.1). Códigos ordenados."""
    id: str
    particion: Particion
    prueba: tuple[str, ...]
    entrenamiento: tuple[str, ...]
    excluidas: tuple[str, ...] = ()   # grupo y amortiguador de las de prueba: fuera de todo (§4.9)
    externo: str | None = None        # en un pliegue interno, el id del externo

    def __post_init__(self) -> None:
        for nombre in ("prueba", "entrenamiento", "excluidas"):
            valor = getattr(self, nombre)
            if list(valor) != sorted(set(valor)):
                raise ValueError(f"Pliegue {self.id}: «{nombre}» debe ir ordenado y sin repetir")
        if set(self.prueba) & set(self.entrenamiento) or set(self.excluidas) & (set(self.prueba) | set(self.entrenamiento)):
            raise ValueError(f"Pliegue {self.id}: prueba, entrenamiento y excluidas deben ser disjuntos")


@dataclass(frozen=True, eq=False)
class DatosCompetencia:
    """Entrada común de la selección y de la validación (§2.4 del diseño). Todo calculado una vez por estación."""
    residuos: Mapping[str, "pd.DataFrame"]        # código → ESQUEMA_RESIDUOS
    climatologias: "pd.DataFrame"                 # ESQUEMA_CLIMA_A (la climatología de A, §4.3)
    tramos: "pd.DataFrame"                        # ESQUEMA_TRAMOS_HOMOGENEOS
    filas_c: Mapping[str, Any]                    # muestra fija y sumas por estación (MC-45; TIP-23): {«C» o «C_est»:
                                                  # {variable: {código: SumasC}}}
    estaticos: "pd.DataFrame"                     # ESQUEMA_ESTATICAS_CELDA_C de las celdas de las estaciones (TIP-22)
    estaciones: Mapping[str, InfoEstacion]
    pliegues: tuple[Pliegue, ...]
    puntos_e5l: Mapping[str, "pd.DataFrame"]      # TIP-17: código → ESQUEMA_PUNTOS_E5L (A1), el estado de C (§4.6)
    clima_estado: Mapping[str, Mapping[str, "np.ndarray"]]    # TIP-17: código → {VARIABLES_CLIMA_ESTADO: 12 × 24
                                                  # (mes, hora UTC), float64}, el estado de C_est (§4.7; D29)


@dataclass(frozen=True, eq=False)
class ModeloC:
    """C o C_est ajustado (§4.6, §4.7)."""
    coef: "np.ndarray"
    media: "np.ndarray"
    desvio: "np.ndarray"
    alfa: float
    diseno: DisenoC


@dataclass(frozen=True, eq=False)
class EntradasDecision:
    """Entrada de ``decidir_combinacion`` para un (uso, grupo) (§6.2; TIP-12). Los candidatos del uso son los de
    ``validacion``; ``decision`` calcula E0, las compuertas, el S del grupo y la red de TF2."""
    uso: Uso
    grupo: Grupo
    validacion: "pd.DataFrame"    # ESQUEMA_VALIDACION_PUB: filas del (uso, grupo), por variable, estrato y partición
    tf: "pd.DataFrame"            # ESQUEMA_TF: filas del uso (TF1 y TF2 por candidato y variable, con la red de TF2)
    replicas: "pd.DataFrame"      # ESQUEMA_REPLICAS: S del grupo por réplica del remuestreo y candidato de E0
    motivos_e0: Mapping[str, tuple[str, ...]]     # candidato → motivos de exclusión de E0 (deriva, finitud); sólo
                                                  # los excluidos


@dataclass(frozen=True)
class DecisionGrupo:
    """Resultado de §6.2 para un (uso, grupo); va a ``decision.json``."""
    uso: Uso
    grupo: Grupo
    e0: tuple[str, ...]
    e1: tuple[str, ...]
    motivos: Mapping[str, tuple[str, ...]]
    S: Mapping[str, float]
    delta_S: Mapping[str, float]
    ic_delta_S: Mapping[str, tuple[float, float]]
    red_tf2: Mapping[str, ReglaRedConstante]
    notas: tuple[str, ...]
    ganador: str


@dataclass(frozen=True)
class DecisionM6:
    """Resultado del Anexo B (``decision_m6.json``)."""
    rama: Mapping[str, Rama]                      # contaminante → rama
    condiciones: Mapping[str, Mapping[str, tuple[bool, ...]]]     # contaminante → sentido → 7 condiciones
    variante: Mapping[str, Variante]              # contaminante (y «O3») → variante
    ganador_restringido: Mapping[str, str] | None # grupo → ganador, si la rama 3 rige en algún contaminante
    notas: tuple[str, ...] = ()


@dataclass(frozen=True)
class Unidad:
    """Unidad reanudable de ``avance.jsonl``: sólo nombre y huellas, sin métricas (§8)."""
    nombre: str
    huella_entrada: str
    huella_salida: str | None = None
