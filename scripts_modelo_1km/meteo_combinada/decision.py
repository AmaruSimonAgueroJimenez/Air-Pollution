"""Regla de decisión (§6) y Anexo B: compuertas, ``decidir_combinacion``, ``decision.json`` y M6.

Es puro: sólo recibe tablas de métricas, resultados de TF y comparaciones del Anexo B, nunca datos (§1 del diseño), y
no escribe: ``decision_json`` y ``decision_m6_json`` devuelven diccionarios que escribe ``salidas``.

En el orden de §6.2:
- ``compuertas``: las compuertas de §6.1 (TF, CD, EX, MZ, nivel y anomalía) de los candidatos de E0, con los mínimos
  de las relativas sobre E0. Una fila por candidato × compuerta × variable × ámbito (la prueba de TF o la macrozona).
- ``decidir_combinacion``: E0, E1, el ganador (pasos 3 a 5), ΔS y su intervalo, la red de TF2, los motivos y las notas
  (paso 6), en un ``tipos.DecisionGrupo``.
- ``decision_json``: el registro del paso 6, más los hiperparámetros de producción y las huellas (§8).
- Anexo B: ``condiciones_anexo_b`` (las 7 condiciones de un sentido, en LRO y BLQ-75 a la vez), ``ramas_m6`` (rama y
  variante por contaminante, la de O3 y, si la rama 3 rige en alguno, el ganador restringido), ``variante_o3``,
  ``ganador_restringido`` y ``decisiones_restringidas`` (rama 3), y ``decision_m6_json``.

Dueño: I10 (olas 2 y 3).
Lecturas propias (DEC-n), para el addendum de M1:
- DEC-1. **Variables de cada compuerta** (§6.1), por (uso, grupo), con los rótulos de ``tipos.VariableMetrica``
  (TIP-15; los de SIN-14), que este módulo exporta en ``VARIABLES``:
  - ambiental (T, Td): S y MZ en T y HR (S_par horario), CD en T y HR, EX en T y Td, TF en T y Td;
  - agudo (T, Td): S, MZ, EX y nivel en ``temp_media`` y ``hr_media`` (§5.2 y §5.8), CD en T y HR (horario), TF en T y
    Td;
  - crónico (T, Td): S, CD, MZ y anomalía en T, EX en ``temp_media``, TF sólo en T (MC-04);
  - ambiental (u, v): S en «uv» (RMSE vectorial), MZ en «uv» y en la rapidez (D43), CD y EX en la rapidez, TF en la
    rapidez;
  - ambiental p: S, CD, MZ y TF en p; sin EX (§6.1: «no hay EX de la presión»).
  MZ compara S_c,z (MC-33), así que va en las variables de S del grupo. En (u, v), §6.1 dice «CD y MZ, a las del puntaje
  del grupo: … la rapidez en (u, v)» y la tabla de §6.1 da el RMSE vectorial como puntaje: D43 elige la lectura más
  estricta, MZ en las dos (un candidato debe pasar en cada una). S_c,z de la rapidez es la columna ``S`` de sus filas de
  macrozona: el puntaje de §5.3 con el MSE horario de la rapidez y los π_b del uso (MC-33), que publica ``validacion``
  (I14). Sumandos: CD de T y de la rapidez con ``CD_T`` («+ 0,05 K o m/s», UMB-4), de HR con ``CD_HR`` y de p con
  ``CD_P``; EX de T y de ``temp_media`` con ``EX_T``, de Td con ``EX_TD``, de ``hr_media`` con ``EX_HR`` y de la
  rapidez con ``EX_FF``. Factores: ``CD_MULT``, ``MZ_MULT`` y ``NIVEL_MULT`` (nivel agudo y anomalía crónica).
- DEC-2. **Qué filas lee.** De ``validacion``: del estrato «nacional», las de partición «agregado» (P1 y P2 juntos,
  §5.3), que dan S, CD, EX, nivel y anomalía; las nacionales de P1 y de P2 y las de los demás estratos son
  descriptivas. Una fila nacional agregada debe ser publicable (MC-61: la regla de soporte no se aplica al agregado
  nacional). Del estrato «macrozona», las de P1, P2 y el agregado: el agregado da S_c,z para MZ y las tres deciden si el
  estrato es publicable (DEC-4). Una fila de macrozona en una variable que no es de MZ del grupo es un error
  (ValueError): con otros rótulos, MZ no regiría nunca y nada lo avisaría. Los rótulos son los de
  ``tipos.VariableMetrica`` y ``tipos.Estrato`` (TIP-15). Todas las filas deben ser del (uso, grupo) y de candidatos
  del uso (§6.1). De ``tf``, las del uso (MC-04) en las variables de TF del grupo.
- DEC-3. **Comparaciones en float64, sin tolerancia.** CD_c ≤ CD_MULT·mín + sumando; EX_c ≤ mín + sumando; MZ, nivel
  y anomalía ≤ factor·mín; el borde exacto pasa (el «≤» del texto). Los mínimos son sobre E0 (§6.2, paso 2), también en
  MZ (por macrozona y variable). Una métrica de un candidato de E0 que falta, no es finita o es negativa es un error
  (ValueError): la regla no se decide con métricas incompletas.
- DEC-4. **MZ** rige en una macrozona × variable si es una macrozona (``tipos.macrozona_o_ninguna``; D9, D16 y
  DEC-19), si ``n_estaciones`` del agregado ≥ ``MZ_MIN_EST`` y si el estrato es publicable en P1, en P2 y en el
  agregado (MC-61: «Un estrato se evalúa por partición y en el agregado, y no se publica si falla en cualquiera»;
  §0.4.4: no se «usa en una compuerta»). Todo candidato de E0 debe tener su fila en las tres particiones;
  ``publicable`` debe ser igual para todos los candidatos en cada partición, y ``n_estaciones`` en el agregado
  (dependen de la variable y del soporte de A, B y AB, no del candidato); si no, ValueError. Aquí se toma la conjunción
  de las tres ``publicable``, sin suponer que la del agregado ya lo es (TIP-15 fija qué dice ``publicable`` en cada
  partición; la prueba es de I14).
- DEC-5. **TF.** Este módulo no calcula la TF: lee ``resultado`` y lo comprueba. Las cotas de la fila deben ser las de
  §5.7 (``constantes.TF_COTAS_*``) y «pasa» debe ser «media ≤ cota y P95 ≤ cota»; en A, C y C_est una media o un P95
  > ``TF_CERO_TOL`` es un error de código (§5.7, errata; ValueError; el borde exacto no lo es). TF1 «no evaluable» no
  existe en el texto (ValueError). TF2 «no evaluable» (EMC1-2, D4) exige la red «ninguna», ``n_red`` <
  ``TF2_RED_MIN_ESTACIONES`` y el mismo resultado en todos los candidatos de la variable; una TF2 evaluable exige una
  red que no sea «ninguna» y ``n_red`` ≥ ese mínimo. Con TF2 no evaluable en v, B y AB no pasan TF en v (motivo «TF2
  no evaluable») y A, C y C_est la pasan («En la compuerta, A, C y C_est pasan TF2 en v»). La red de TF2 de cada
  variable es una sola, igual para todos los candidatos (``red_tf2``): un solo ``regla_red`` y un solo ``n_red``. Las
  comprobaciones valen para todas las filas de TF del uso en las variables del grupo, también las de un candidato
  fuera de E0 (las lee DEC-9): de los de E0 se exige cada fila; de los demás se comprueban las que vienen.
- DEC-6. **E0** (paso 1): los candidatos del uso (§6.1) menos los de ``motivos_e0``. Motivos admitidos: «deriva»
  (sólo B y AB, §5.7) y «finitud»; «cuyo código pasó M1» = todos (MC-56). E0 vacío es un error.
- DEC-7. **S del grupo** (§5.3): S_par = ``S_PAR_PESO``·(S_1/mín S_1 + S_2/mín S_2), con los mínimos sobre E0, en
  (T, Td) ambiental (T y HR) y agudo (``temp_media`` y ``hr_media``); en lo crónico, S_T; en (u, v) y p, el único S.
  Se registra para los de E0.
- DEC-8. **Empate exacto** = igualdad en float64 (MC-63): se elige por (S, posición en A, AB, B, C; C_est en lo
  crónico). Vale también en los pasos 4 y 5 y en la rama 3.
- DEC-9. **Regla crónica** (paso 5). «Falla TF» = falla la compuerta TF, también por TF2 no evaluable (EMC1-2); «falla
  la compuerta de deriva» = motivo «deriva» de E0. Un B o un AB fuera de E0 por finitud cuenta como «falla TF» si una
  de sus filas de ``tf``, comprobada como en DEC-5, dice «falla» o es una TF2 «no evaluable» (EMC1-2: «cuenta como falla
  en E1 y en los pasos 4 y 5»). Es la lectura más estricta, que dispara antes la regla, y la que fijó D45 [delegada]
  («cuenta su TF»; P35). Sin filas de ``tf``, no cuenta como «falla TF». Compiten A y C_est de E1, o de E0 si ninguno
  está en E1; si ninguno está en E0, ValueError.
- DEC-10. **Notas** (paso 6), en orden fijo: «regla crónica»; «regla sin ganador» siempre que E1 está vacío, también
  cuando rige la regla crónica (acuerdo A11: el texto calla y sólo cambia ``decision.json``); «TF2 no evaluable» si TF2
  no es evaluable en alguna variable de TF del grupo, aunque B y AB ya estén fuera («se declara», §5.7); y, en la rama
  3, «I restringido por TF de contaminantes».
- DEC-11. **Motivos de exclusión**, por candidato que no está en E1: los de E0 (deriva, finitud) o las compuertas que
  falla, en el orden TF, «TF2 no evaluable», CD, EX, MZ, nivel y anomalía; en la rama 3, B y AB suman «TF de
  contaminantes».
- DEC-12. **ΔS y su intervalo** (§5.4; MC-34, aceptada por D5; D46 [delegada], P36). ΔS_c = S_c − S_ganador, con el
  ganador de la decisión. El intervalo es el percentil del ``BOOT_IC_PCT`` % de ΔS_c,r = S_c,r − S_g(r),r sobre las
  réplicas, donde g(r) es el ganador de la réplica r: el de menor S de réplica dentro del mismo conjunto que usó la
  decisión, con el mismo desempate (DEC-8). Ese conjunto es E1 (paso 3); los de E0 que pasan TF (paso 4); A y C_est de
  E1, o de E0 si ninguno está en E1 (paso 5); y, en la rama 3, E1 ∩ {A, C} o los de E0 ∩ {A, C} que pasan TF (DEC-15,
  D46: «También para el ganador restringido»). Las compuertas no se rehacen por réplica: el conjunto es el de la
  decisión (D46). Como el desempate sólo elige entre S iguales, S_g(r),r es el mínimo de S de réplica en ese conjunto, y
  el intervalo del ganador ya no es [0, 0]: va de 0 hacia arriba. Sin interpolar (``inverted_cdf``) y con el redondeo
  de (1 − nivel)/2 de ``v2/bootstrap_v2._percentiles``. Cada réplica debe traer a todos los de E0, sólo a ellos y con S
  finito; si no, ValueError. El número de réplicas lo fija ``validacion`` (no se comprueba aquí). Reemplaza la lectura
  de la ola 2 (el ganador de la decisión fijo en todas las réplicas), que se apartaba de MC-34.
- DEC-13. **Condiciones del Anexo B.** Por sentido, cada condición se cumple en LRO y en BLQ-75 a la vez (una fila por
  protocolo, exigida). c = la variante que reemplaza (I en «I_frente_a_D»). 1: ``ic_bajo`` > 0 (el IC excluye 0 a
  favor de c) y la segunda prueba coincide; 2, 3, 4 y 6: sus columnas; 5: el signo sin ponderar y en log; 7:
  |NMB_c| ≤ |NMB_otra| + ``M6_NMB_PP``, con el NMB en puntos porcentuales (SIN-17). Un ``ic_bajo``, un ``ic_alto``
  o un NMB no finito, o un IC con ``ic_bajo`` > ``ic_alto``, es un error (ValueError): la condición no se decide con
  la comparación incompleta. ``ic_bajo`` = 0 no excluye 0 (la condición 1 no se cumple).
- DEC-14. **Ramas.** La TF de contaminantes es «pasa» o «falla» por contaminante × variante, y va siempre para las dos
  variantes. La de D se exige siempre; la de I, si algún grupo ambiental tiene ganador B o AB. Si ninguno lo tiene, la
  entrada de I es la verificación de un mes (Anexo B: «con A o C es 0 por construcción y se verifica en un mes»), que
  calcula ``tendencias`` (I15) con la TF de contaminantes en un lote de un mes: debe venir y decir «pasa»; si falta, o
  si dice «falla», es un error de código (ValueError). Que las dos variantes superen es un error (simetría: «a lo más
  una puede, por la condición 1»).
- DEC-15. **Ganador restringido** (rama 3). Se rehacen sólo los grupos cuyo ganador ambiental es B o AB; los demás
  quedan con su decisión original. Compiten A y C de E0, con las compuertas y los mínimos de la decisión original
  (sobre el E0 entero, con B y AB) y el mismo S_par: E1 ∩ {A, C} y, si queda vacío, el paso 4 entre A y C de E0 que
  pasan TF. Es la lectura más estricta y la que fijó D44 [delegada] («el E0 original»; P34). El intervalo de ΔS sigue
  DEC-12 con ese conjunto (D46). ``grupos_con_b_ab`` debe coincidir con los ganadores que dan las entradas.
- DEC-16. ``ramas_m6`` calcula el ganador restringido cuando la rama 3 rige en algún contaminante, con los argumentos de
  palabra clave ``entradas_ambientales`` y ``umbrales`` (aditivos a §3 del diseño). Vale para todos los contaminantes,
  O3 y la S6 (§6.4). Si recibe ``entradas_ambientales`` (obligatorias con la rama 3), exige que ``ganador_ambiental``
  sea, grupo por grupo, el ganador que dan (ValueError si no). Sin ellas (ramas 1 y 2), ``ganador_ambiental`` sale de
  ``decision.json``, cuyas huellas M6 comprueba antes de correr (Anexo B, «M6 se niega a correr»).
- DEC-17. **Claves de M6.** Contaminantes «pm25» y «no2» (los del panel de la red 2 y de v2) y «O3» en la variante
  (``tipos.CONTAMINANTES_M6`` y ``tipos.CLAVE_O3``, TIP-15); ``variante_o3`` exige exactamente pm25 y no2.
- DEC-18. **Registros.** ``decision.json`` y ``decision_m6.json`` llevan números de Python (sin NaN), las decisiones en
  el orden fijo de ``VARIABLES`` y las huellas como {ruta por alias: sha256} o {ruta: {sha256, bytes}} bajo la clave
  «huellas» (CEG-15); ninguna ruta absoluta. Los hiperparámetros de producción son obligatorios para cada (uso, grupo).
  Las versiones son ``tipos.VERSION_DECISION`` y ``tipos.VERSION_DECISION_M6`` (TIP-15).
- DEC-19. **Macrozonas** (D9, D16; TIP-8 y TIP-11). ``MACROZONAS`` es la lista cerrada de las que forman estrato y
  rigen en MZ, ``tipos.MACROZONAS`` (TIP-15): las de ``_comun_modelo.MACROZONA_CODIGO`` menos
  ``tipos.MACROZONAS_NINGUNA`` (una prueba la compara con ``fijados.macrozona_codigo``, por AST). Un ``valor_estrato``
  de macrozona que no está en ``MACROZONAS`` ni en ``MACROZONAS_NINGUNA`` es un error (ValueError); los de
  ``MACROZONAS_NINGUNA`` no rigen en MZ (motivo «sin_macrozona»).
- DEC-20. **Las mismas macrozonas en cada variable de MZ** (D43; como DEC-2). Las filas de macrozona de un (uso, grupo)
  traen el mismo conjunto de valores de ``valor_estrato`` en cada variable de MZ del grupo (T y HR; ``temp_media`` y
  ``hr_media``; «uv» y la rapidez); si no, ValueError. Sin esto, una variable de MZ sin sus filas (por ejemplo, la
  rapidez de D43 en una tabla hecha antes de D43) dejaría a MZ sin regir en ella y nada lo avisaría. Un grupo sin
  ninguna fila de macrozona pasa sin MZ; exigir las cinco de ``MACROZONAS`` en cada variable de MZ (TIP-15: «cada
  macrozona se publica en P1, P2 y el agregado») queda como pedido al coordinador.
Depende de: tipos, constantes, umbrales (un objeto con ``.a(id)``; no hace falta importarlo).
"""
from __future__ import annotations

import dataclasses
import math
import re
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from meteo_combinada import constantes, tipos
from meteo_combinada.tipos import (Candidato, Compuerta, DecisionGrupo, DecisionM6, EntradasDecision, Grupo,
                                   Protocolo, Prueba, Rama, ReglaRedConstante, ResultadoTF, Sentido, Uso, Variante)

# ---------------------------------------------------------------------------------------------------------------
# Rótulos que la regla lee de las tablas (DEC-1, DEC-2): los de ``tipos`` (TIP-15).
# ---------------------------------------------------------------------------------------------------------------
ESTRATO_NACIONAL = tipos.Estrato.NACIONAL.value
ESTRATO_MACROZONA = tipos.Estrato.MACROZONA.value
V_T = tipos.VariableMetrica.T.value
V_TD = tipos.VariableMetrica.TD.value
V_P = tipos.VariableMetrica.P.value
V_HR = tipos.VariableMetrica.HR.value
V_RAPIDEZ = tipos.VariableMetrica.RAPIDEZ.value
V_UV = tipos.VariableMetrica.UV.value                    # RMSE vectorial de (u, v) (§5.2)
V_TEMP_MEDIA = tipos.VariableMetrica.TEMP_MEDIA.value    # columnas de meteo_civil_v3 (§5.2, §5.8)
V_HR_MEDIA = tipos.VariableMetrica.HR_MEDIA.value
MACROZONAS = tipos.MACROZONAS                            # DEC-19 (TIP-15)
PARTICIONES = (tipos.Particion.P1.value, tipos.Particion.P2.value, tipos.PARTICION_AGREGADO)    # DEC-4 (MC-61)

_A, _B, _AB, _C, _CE = (c.value for c in (Candidato.A, Candidato.B, Candidato.AB, Candidato.C, Candidato.C_EST))
CON_DERIVA = (_B, _AB)                       # §5.7: la compuerta de deriva es de B y AB
CERO_POR_CONSTRUCCION = (_A, _C, _CE)        # §5.7: artefacto 0 por construcción
ESTABLES_CRONICO = (_A, _CE)                 # §6.2, paso 5
ELEGIBLES_RESTRINGIDO = (_A, _C)             # Anexo B, rama 3

CANDIDATOS_USO = MappingProxyType({Uso.AMBIENTAL: (_A, _B, _AB, _C), Uso.AGUDO: (_A, _B, _AB, _C),
                                   Uso.CRONICO: (_A, _B, _AB, _CE)})          # §6.1
ORDEN_DESEMPATE = MappingProxyType({Uso.AMBIENTAL: (_A, _AB, _B, _C), Uso.AGUDO: (_A, _AB, _B, _C),
                                    Uso.CRONICO: (_A, _AB, _B, _CE)})         # §6.2, paso 3


@dataclass(frozen=True)
class VariablesGrupo:
    """Variables de S y de cada compuerta de un (uso, grupo) (§6.1; DEC-1)."""
    S: tuple[str, ...]
    CD: tuple[str, ...]
    EX: tuple[str, ...]
    MZ: tuple[str, ...]
    nivel: tuple[str, ...]
    anomalia: tuple[str, ...]
    TF: tuple[str, ...]


VARIABLES = MappingProxyType({
    (Uso.AMBIENTAL, Grupo.T_TD): VariablesGrupo(S=(V_T, V_HR), CD=(V_T, V_HR), EX=(V_T, V_TD), MZ=(V_T, V_HR),
                                                nivel=(), anomalia=(), TF=(V_T, V_TD)),
    (Uso.AMBIENTAL, Grupo.U_V): VariablesGrupo(S=(V_UV,), CD=(V_RAPIDEZ,), EX=(V_RAPIDEZ,), MZ=(V_UV, V_RAPIDEZ),
                                               nivel=(), anomalia=(), TF=(V_RAPIDEZ,)),    # MZ en las dos: D43
    (Uso.AMBIENTAL, Grupo.P): VariablesGrupo(S=(V_P,), CD=(V_P,), EX=(), MZ=(V_P,), nivel=(), anomalia=(),
                                             TF=(V_P,)),
    (Uso.AGUDO, Grupo.T_TD): VariablesGrupo(S=(V_TEMP_MEDIA, V_HR_MEDIA), CD=(V_T, V_HR),
                                            EX=(V_TEMP_MEDIA, V_HR_MEDIA), MZ=(V_TEMP_MEDIA, V_HR_MEDIA),
                                            nivel=(V_TEMP_MEDIA, V_HR_MEDIA), anomalia=(), TF=(V_T, V_TD)),
    (Uso.CRONICO, Grupo.T_TD): VariablesGrupo(S=(V_T,), CD=(V_T,), EX=(V_TEMP_MEDIA,), MZ=(V_T,), nivel=(),
                                              anomalia=(V_T,), TF=(V_T,)),
})
GRUPOS_AMBIENTALES = tuple(g for (u, g) in VARIABLES if u is Uso.AMBIENTAL)

# Ids del Anexo A de los sumandos de CD y EX por variable (DEC-1) y constantes de las cotas de TF (§5.7, CON-9).
_SUMANDO_CD = MappingProxyType({V_T: "CD_T", V_RAPIDEZ: "CD_T", V_HR: "CD_HR", V_P: "CD_P"})
_SUMANDO_EX = MappingProxyType({V_T: "EX_T", V_TEMP_MEDIA: "EX_T", V_TD: "EX_TD", V_HR_MEDIA: "EX_HR",
                                V_RAPIDEZ: "EX_FF"})
_COTAS_TF = MappingProxyType({V_T: "TF_COTAS_T", V_TD: "TF_COTAS_TD", V_RAPIDEZ: "TF_COTAS_RAPIDEZ",
                              V_P: "TF_COTAS_P"})
_PRUEBAS = (Prueba.TF1.value, Prueba.TF2.value)

# Notas y motivos (DEC-10, DEC-11).
NOTA_REGLA_CRONICA = "regla crónica"
NOTA_REGLA_SIN_GANADOR = "regla sin ganador"                 # §6.2, paso 4
NOTA_TF2_NO_EVALUABLE = "TF2 no evaluable"                   # §5.7 (EMC1-2)
NOTA_RESTRINGIDO = "I restringido por TF de contaminantes"   # Anexo B, rama 3
ORDEN_NOTAS = (NOTA_REGLA_CRONICA, NOTA_REGLA_SIN_GANADOR, NOTA_TF2_NO_EVALUABLE, NOTA_RESTRINGIDO)
MOTIVO_TF2_NO_EVALUABLE = "TF2 no evaluable"                 # §5.7: el motivo de B y AB en decision.json
MOTIVO_TF_CONTAMINANTES = "TF de contaminantes"              # rama 3: B y AB fuera de la competencia restringida
ORDEN_MOTIVOS = (Compuerta.DERIVA.value, Compuerta.FINITUD.value, Compuerta.TF.value, MOTIVO_TF2_NO_EVALUABLE,
                 Compuerta.CD.value, Compuerta.EX.value, Compuerta.MZ.value, Compuerta.NIVEL.value,
                 Compuerta.ANOMALIA.value, MOTIVO_TF_CONTAMINANTES)
_MOTIVOS_E0 = (Compuerta.DERIVA.value, Compuerta.FINITUD.value)
_MOTIVOS_TF = (Compuerta.TF.value, MOTIVO_TF2_NO_EVALUABLE)

# Anexo B (DEC-13, DEC-17).
CONTAMINANTES_M6 = tipos.CONTAMINANTES_M6
CLAVE_O3 = tipos.CLAVE_O3
_REEMPLAZA = MappingProxyType({Sentido.I_FRENTE_A_D: Variante.I, Sentido.D_FRENTE_A_I: Variante.D})

# Registros (DEC-18).
ESQUEMA_DECISION = tipos.VERSION_DECISION
ESQUEMA_DECISION_M6 = tipos.VERSION_DECISION_M6
METODO_CUANTIL = "inverted_cdf"          # percentil sin interpolar, como v2/bootstrap_v2 (DEC-12)
_SHA256 = re.compile(r"[0-9a-f]{64}")

# Tabla de ``compuertas`` (interna; si cruza a otro módulo, su esquema va a ``tipos``).
COLUMNAS_COMPUERTAS = MappingProxyType({
    "candidato": "string", "compuerta": "string", "variable": "string", "ambito": "string", "valor": "float64",
    "referencia": "float64", "cota": "float64", "aplica": "bool", "pasa": "bool", "motivo": "string"})
VERSION_COMPUERTAS = "meteo-combinada-compuertas/1"
_NAN = float("nan")


# ---------------------------------------------------------------------------------------------------------------
# Lectura y validación de las entradas
# ---------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class _Preparadas:
    uso: Uso
    grupo: Grupo
    variables: VariablesGrupo
    candidatos: tuple[str, ...]                          # los del uso, en el orden de tipos.Candidato
    e0: tuple[str, ...]
    motivos_e0: Mapping[str, tuple[str, ...]]
    nacional: Mapping[tuple[str, str], dict]             # (variable, candidato) → fila nacional agregada
    macrozonas: Mapping[tuple[str, str], dict]           # (variable, macrozona) → {partición: {candidato: fila}}
    tf: Mapping[tuple[str, str, str], dict]              # (candidato, variable, prueba) → fila
    replicas: Any


@dataclass(frozen=True)
class _Evaluacion:
    filas: tuple[dict, ...]                              # filas de COLUMNAS_COMPUERTAS
    fallas: Mapping[str, tuple[str, ...]]                # candidato de E0 → motivos (compuertas que falla)
    red_tf2: Mapping[str, ReglaRedConstante]
    tf2_no_evaluable: bool
    falla_tf_fuera: Mapping[str, bool]                   # candidato fuera de E0 con filas de TF → si falla TF (DEC-9)


def _registros(df) -> list[dict]:
    """Filas como diccionarios con tipos de Python (texto nulo → None)."""
    salida = []
    for fila in df.to_dict("records"):
        salida.append({k: (None if v is pd.NA else v) for k, v in fila.items()})
    return salida


def _finito(x) -> bool:
    return isinstance(x, (int, float, np.integer, np.floating)) and not isinstance(x, bool) and math.isfinite(x)


def _texto(fila: Mapping, columna: str, nombre: str) -> str:
    valor = fila[columna]
    if not isinstance(valor, str) or not valor:
        raise ValueError(f"{nombre}: «{columna}» vacío o nulo en {fila}")
    return valor


def _candidato(c) -> str:
    return Candidato(c).value


def _motivos_e0(motivos, candidatos: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    """DEC-6: candidato → motivos de E0, normalizados al orden fijo."""
    if not isinstance(motivos, Mapping):
        raise TypeError(f"motivos_e0 debe ser un diccionario: {motivos!r}")
    salida: dict[str, tuple[str, ...]] = {}
    for c, ms in motivos.items():
        c = _candidato(c)
        if c not in candidatos:
            raise ValueError(f"motivos_e0: {c} no es candidato del uso ({candidatos})")
        if isinstance(ms, (str, bytes)) or not isinstance(ms, Iterable):
            raise TypeError(f"motivos_e0[{c}] debe ser una tupla de motivos: {ms!r}")
        ms = tuple(Compuerta(m).value for m in ms)
        if not ms:
            raise ValueError(f"motivos_e0[{c}] vacío: un candidato fuera de E0 lleva su motivo")
        if any(m not in _MOTIVOS_E0 for m in ms):
            raise ValueError(f"motivos_e0[{c}]: {ms}; E0 sólo excluye por {_MOTIVOS_E0} (§6.2, paso 1)")
        if Compuerta.DERIVA.value in ms and c not in CON_DERIVA:
            raise ValueError(f"motivos_e0[{c}]: la compuerta de deriva es sólo de B y AB (§5.7)")
        salida[c] = tuple(m for m in ORDEN_MOTIVOS if m in ms)
    return {c: salida[c] for c in candidatos if c in salida}


def _filas_validacion(df, uso: Uso, grupo: Grupo, candidatos: tuple[str, ...], variables_mz: tuple[str, ...]):
    """DEC-2: filas nacionales agregadas y filas de macrozona de las tres particiones (DEC-4, DEC-19)."""
    nacional: dict[tuple[str, str], dict] = {}
    macrozonas: dict[tuple[str, str], dict[str, dict[str, dict]]] = {}
    for fila in _registros(df):
        if fila["uso"] != uso.value or fila["grupo"] != grupo.value:
            raise ValueError(f"validacion: fila de ({fila['uso']}, {fila['grupo']}) en la decisión de "
                             f"({uso.value}, {grupo.value})")
        cand = _texto(fila, "candidato", "validacion")
        if cand not in candidatos:
            raise ValueError(f"validacion: {cand} no es candidato de lo {uso.value} (§6.1)")
        particion = _texto(fila, "particion", "validacion")
        if particion not in PARTICIONES:
            raise ValueError(f"validacion: partición desconocida {particion!r}")
        variable = _texto(fila, "variable", "validacion")
        estrato = _texto(fila, "estrato", "validacion")
        if estrato == ESTRATO_MACROZONA:
            macrozona = _texto(fila, "valor_estrato", "validacion")
            if macrozona not in MACROZONAS and macrozona not in tipos.MACROZONAS_NINGUNA:
                raise ValueError(f"validacion: {macrozona!r} no es una macrozona de {MACROZONAS} ni de "
                                 f"{sorted(tipos.MACROZONAS_NINGUNA)} (DEC-19)")
            if variable not in variables_mz:
                raise ValueError(f"validacion: fila de macrozona en {variable!r}; MZ de ({uso.value}, {grupo.value}) "
                                 f"va en {variables_mz} (DEC-1, DEC-2)")
            por = macrozonas.setdefault((variable, macrozona), {}).setdefault(particion, {})
            if cand in por:
                raise ValueError(f"validacion: fila de macrozona repetida {(variable, macrozona, particion, cand)}")
            por[cand] = fila
        elif estrato == ESTRATO_NACIONAL and particion == tipos.PARTICION_AGREGADO:
            clave = (variable, cand)
            if clave in nacional:
                raise ValueError(f"validacion: fila nacional repetida {clave}")
            if not fila["publicable"]:
                raise ValueError(f"validacion: la fila nacional {clave} no es publicable; la regla de soporte no se "
                                 "aplica al agregado nacional (MC-61)")
            nacional[clave] = fila
    # DEC-20: las mismas macrozonas en cada variable de MZ del grupo (D43: también en la rapidez de (u, v)).
    por_variable = {v: frozenset(z for (w, z) in macrozonas if w == v) for v in variables_mz}
    if len(set(por_variable.values())) > 1:
        detalle = {v: sorted(z) for v, z in por_variable.items()}
        raise ValueError(f"validacion: las variables de MZ de ({uso.value}, {grupo.value}) traen macrozonas distintas "
                         f"{detalle}; MZ se exige en cada una (D43, DEC-20)")
    return nacional, macrozonas


def _filas_tf(df, uso: Uso, candidatos: tuple[str, ...], variables: tuple[str, ...]):
    """DEC-2, DEC-5: filas de TF del uso en las variables del grupo."""
    salida: dict[tuple[str, str, str], dict] = {}
    for fila in _registros(df):
        if fila["uso"] != uso.value:
            raise ValueError(f"tf: fila de lo {fila['uso']} en la decisión de lo {uso.value} (MC-04)")
        cand = _texto(fila, "candidato", "tf")
        if cand not in candidatos:
            raise ValueError(f"tf: {cand} no es candidato de lo {uso.value}")
        prueba = Prueba(_texto(fila, "prueba", "tf")).value
        ResultadoTF(_texto(fila, "resultado", "tf"))
        variable = _texto(fila, "variable", "tf")
        if variable not in variables:
            continue
        clave = (cand, variable, prueba)
        if clave in salida:
            raise ValueError(f"tf: fila repetida {clave}")
        salida[clave] = fila
    return salida


def _preparar(uso, grupo, entradas) -> _Preparadas:
    if not isinstance(entradas, EntradasDecision):
        raise TypeError(f"se espera tipos.EntradasDecision, no {type(entradas).__name__}")
    uso, grupo = Uso(uso), Grupo(grupo)
    if Uso(entradas.uso) is not uso or Grupo(entradas.grupo) is not grupo:
        raise ValueError(f"las entradas son de ({entradas.uso}, {entradas.grupo}), no de ({uso.value}, "
                         f"{grupo.value})")
    if (uso, grupo) not in VARIABLES:
        raise ValueError(f"lo {uso.value} no decide el grupo {grupo.value} (§6.1)")
    variables = VARIABLES[(uso, grupo)]
    candidatos = CANDIDATOS_USO[uso]
    tipos.validar_esquema(entradas.validacion, tipos.ESQUEMA_VALIDACION_PUB, nombre="validacion")
    tipos.validar_esquema(entradas.tf, tipos.ESQUEMA_TF, nombre="tf")
    tipos.validar_esquema(entradas.replicas, tipos.ESQUEMA_REPLICAS, nombre="replicas")
    motivos_e0 = _motivos_e0(entradas.motivos_e0, candidatos)
    e0 = tuple(c for c in candidatos if c not in motivos_e0)
    if not e0:
        raise ValueError(f"E0 vacío en ({uso.value}, {grupo.value}): ningún candidato puede ganar (§6.2, paso 1)")
    nacional, macrozonas = _filas_validacion(entradas.validacion, uso, grupo, candidatos, variables.MZ)
    tf = _filas_tf(entradas.tf, uso, candidatos, variables.TF)
    return _Preparadas(uso=uso, grupo=grupo, variables=variables, candidatos=candidatos, e0=e0, motivos_e0=motivos_e0,
                       nacional=nacional, macrozonas=macrozonas, tf=tf, replicas=entradas.replicas)


# ---------------------------------------------------------------------------------------------------------------
# Compuertas (§6.1)
# ---------------------------------------------------------------------------------------------------------------
def _no_negativo(x, que: str) -> float:
    if not _finito(x) or x < 0:
        raise ValueError(f"{que}: se espera un número finito ≥ 0, no {x!r} (DEC-3)")
    return float(x)


def _metricas(prep: _Preparadas, variable: str, columna: str, candidatos) -> dict[str, float]:
    salida = {}
    for c in candidatos:
        fila = prep.nacional.get((variable, c))
        if fila is None:
            raise ValueError(f"({prep.uso.value}, {prep.grupo.value}): falta la fila nacional de {c} en {variable}")
        salida[c] = _no_negativo(fila[columna], f"{columna} de {c} en {variable}")
    return salida


def _fila(c, compuerta: Compuerta, variable, ambito, valor, referencia, cota, aplica, pasa, motivo="") -> dict:
    return {"candidato": c, "compuerta": compuerta.value, "variable": variable, "ambito": ambito, "valor": valor,
            "referencia": referencia, "cota": cota, "aplica": bool(aplica), "pasa": bool(pasa), "motivo": motivo}


def _fila_tf(c: str, variable: str, prueba: str, fila: Mapping, cota_media: float, cota_p95: float) -> dict:
    """DEC-5: comprueba una fila de TF (de E0 o de fuera de E0) y da su fila de la compuerta."""
    if fila["cota_media"] != cota_media or fila["cota_p95"] != cota_p95:
        raise ValueError(f"tf: cotas de {prueba} en {variable} ({fila['cota_media']}, {fila['cota_p95']}) "
                         f"distintas de las de §5.7 ({cota_media}, {cota_p95})")
    resultado = ResultadoTF(fila["resultado"])
    if resultado is ResultadoTF.NO_EVALUABLE:
        if prueba != Prueba.TF2.value:
            raise ValueError(f"tf: TF1 «no evaluable» no existe en el texto ({c}, {variable})")
        pasa = c not in CON_DERIVA          # EMC1-2: B y AB no pasan; A, C y C_est sí
        return _fila(c, Compuerta.TF, variable, prueba, _NAN, _NAN, _NAN, True, pasa, MOTIVO_TF2_NO_EVALUABLE)
    media = _no_negativo(fila["media_pond"], f"media de {prueba} de {c} en {variable}")
    p95 = _no_negativo(fila["p95_pond"], f"P95 de {prueba} de {c} en {variable}")
    cumple = media <= cota_media and p95 <= cota_p95
    if cumple != (resultado is ResultadoTF.PASA):
        raise ValueError(f"tf: {prueba} de {c} en {variable} dice «{resultado.value}» y las cotas dicen "
                         f"lo contrario (DEC-5)")
    tolerancia_cero = constantes.valor("TF_CERO_TOL")
    if c in CERO_POR_CONSTRUCCION and (media > tolerancia_cero or p95 > tolerancia_cero):
        raise ValueError(f"tf: {prueba} de {c} en {variable} > 10⁻⁶: es un error de código (§5.7, errata)")
    return _fila(c, Compuerta.TF, variable, prueba, media, p95, cota_media, True, cumple)


def _evaluar_tf(prep: _Preparadas) -> tuple[list[dict], dict[str, ReglaRedConstante], bool, dict[str, bool]]:
    """DEC-5: filas de la compuerta TF de los de E0, la red de TF2 por variable, si TF2 no es evaluable en alguna y,
    para los candidatos fuera de E0 con filas de TF, si fallan TF (DEC-9)."""
    minimo_red = constantes.valor("TF2_RED_MIN_ESTACIONES")
    filas, red, no_evaluable, falla_fuera = [], {}, False, {}
    for variable in prep.variables.TF:
        cotas = constantes.valor(_COTAS_TF[variable])          # (TF1 media, TF1 P95, TF2 media, TF2 P95)
        de_tf2 = [f for (c, v, p), f in prep.tf.items() if v == variable and p == Prueba.TF2.value]
        if not de_tf2:
            raise ValueError(f"tf: faltan las filas de TF2 de {variable} (lo {prep.uso.value})")
        reglas = {ReglaRedConstante(_texto(f, "regla_red", "tf")) for f in de_tf2}
        tamanos = {f["n_red"] for f in de_tf2}
        resultados = {ResultadoTF(f["resultado"]) for f in de_tf2}
        if len(reglas) != 1 or len(tamanos) != 1:
            raise ValueError(f"tf: la red de TF2 de {variable} debe ser una sola para todos los candidatos: "
                             f"reglas {reglas}, estaciones {tamanos} (DEC-5)")
        regla, n_red = reglas.pop(), tamanos.pop()
        ne = ResultadoTF.NO_EVALUABLE in resultados
        if ne and resultados != {ResultadoTF.NO_EVALUABLE}:
            raise ValueError(f"tf: TF2 de {variable} no evaluable sólo para algunos candidatos (EMC1-2)")
        if ne != (regla is ReglaRedConstante.NINGUNA) or ne != (n_red < minimo_red):
            raise ValueError(f"tf: TF2 de {variable} con resultado {sorted(r.value for r in resultados)}, red "
                             f"{regla.value} y {n_red} estaciones no calzan (§5.7, EMC1-2)")
        red[variable] = regla
        no_evaluable = no_evaluable or ne
        for i, prueba in enumerate(_PRUEBAS):
            for c in prep.candidatos:
                fila = prep.tf.get((c, variable, prueba))
                if fila is None:
                    if c in prep.e0:
                        raise ValueError(f"tf: falta {prueba} de {c} en {variable} (lo {prep.uso.value})")
                    continue
                f = _fila_tf(c, variable, prueba, fila, cotas[2 * i], cotas[2 * i + 1])
                if c in prep.e0:
                    filas.append(f)
                else:
                    falla_fuera[c] = falla_fuera.get(c, False) or not f["pasa"]
    return filas, red, no_evaluable, falla_fuera


def _relativa(prep, filas, compuerta: Compuerta, variables, columna: str, cota_de) -> None:
    for variable in variables:
        valores = _metricas(prep, variable, columna, prep.e0)
        minimo = min(valores.values())
        cota = cota_de(variable, minimo)
        for c in prep.e0:
            filas.append(_fila(c, compuerta, variable, "", valores[c], minimo, cota, True, valores[c] <= cota))


def _mz(prep: _Preparadas, filas: list, umbrales) -> None:
    """DEC-4: S_c,z ≤ MZ_MULT · mín S_c′,z (sobre E0) en cada macrozona con ≥ MZ_MIN_EST estaciones y publicable en
    P1, en P2 y en el agregado (MC-61)."""
    minimo_estaciones = umbrales.a("MZ_MIN_EST")
    factor = umbrales.a("MZ_MULT")
    for variable in prep.variables.MZ:
        for macrozona in sorted(z for (v, z) in prep.macrozonas if v == variable):
            por_particion = prep.macrozonas[(variable, macrozona)]
            motivo = ""
            if tipos.macrozona_o_ninguna(macrozona) is None:
                motivo = "sin_macrozona"                                   # D9 y D16: no rige
            else:
                faltan = [(p, c) for p in PARTICIONES for c in prep.e0 if c not in por_particion.get(p, {})]
                if faltan:
                    raise ValueError(f"validacion: faltan las filas {faltan} (partición, candidato) en la macrozona "
                                     f"{macrozona} ({variable}); MZ se evalúa en P1, P2 y el agregado (MC-61, DEC-4)")
                publicable = {}
                for p in PARTICIONES:
                    valores_p = {bool(f["publicable"]) for f in por_particion[p].values()}
                    if len(valores_p) != 1:
                        raise ValueError(f"validacion: publicable distinto entre candidatos en {macrozona} "
                                         f"({variable}, {p}): {valores_p} (DEC-4)")
                    publicable[p] = valores_p.pop()
                n_est = {f["n_estaciones"] for f in por_particion[tipos.PARTICION_AGREGADO].values()}
                if len(n_est) != 1:
                    raise ValueError(f"validacion: n_estaciones distinto entre candidatos en {macrozona} "
                                     f"({variable}): {n_est} (DEC-4)")
                n_est = n_est.pop()
                if not all(publicable.values()):
                    motivo = "no_publicable"                               # MC-61: falla en alguna partición
                elif n_est < minimo_estaciones:
                    motivo = "pocas_estaciones"
            if motivo:
                for c in prep.e0:
                    filas.append(_fila(c, Compuerta.MZ, variable, macrozona, _NAN, _NAN, _NAN, False, True, motivo))
                continue
            por = por_particion[tipos.PARTICION_AGREGADO]
            valores = {c: _no_negativo(por[c]["S"], f"S de {c} en {macrozona} ({variable})") for c in prep.e0}
            minimo = min(valores.values())
            cota = factor * minimo
            for c in prep.e0:
                filas.append(_fila(c, Compuerta.MZ, variable, macrozona, valores[c], minimo, cota, True,
                                   valores[c] <= cota))


def _evaluacion(prep: _Preparadas, umbrales) -> _Evaluacion:
    filas, red, no_evaluable, falla_fuera = _evaluar_tf(prep)
    cd_mult, nivel_mult = umbrales.a("CD_MULT"), umbrales.a("NIVEL_MULT")
    _relativa(prep, filas, Compuerta.CD, prep.variables.CD, "CD",
              lambda v, m: cd_mult * m + umbrales.a(_SUMANDO_CD[v]))
    _relativa(prep, filas, Compuerta.EX, prep.variables.EX, "EX", lambda v, m: m + umbrales.a(_SUMANDO_EX[v]))
    _mz(prep, filas, umbrales)
    _relativa(prep, filas, Compuerta.NIVEL, prep.variables.nivel, "nivel", lambda v, m: nivel_mult * m)
    _relativa(prep, filas, Compuerta.ANOMALIA, prep.variables.anomalia, "anomalia", lambda v, m: nivel_mult * m)
    fallas: dict[str, set[str]] = {c: set() for c in prep.e0}
    for f in filas:
        if not f["pasa"]:
            fallas[f["candidato"]].add(f["motivo"] if f["motivo"] == MOTIVO_TF2_NO_EVALUABLE else f["compuerta"])
    return _Evaluacion(filas=tuple(filas),
                       fallas={c: tuple(m for m in ORDEN_MOTIVOS if m in s) for c, s in fallas.items()},
                       red_tf2=red, tf2_no_evaluable=no_evaluable, falla_tf_fuera=falla_fuera)


def _tabla_compuertas(filas) -> pd.DataFrame:
    df = pd.DataFrame(list(filas), columns=list(COLUMNAS_COMPUERTAS)).astype(dict(COLUMNAS_COMPUERTAS))
    df.attrs["esquema"] = VERSION_COMPUERTAS
    return df


def compuertas(uso, grupo, tabla, umbrales) -> pd.DataFrame:
    """Compuertas de §6.1 de los candidatos de E0 de ``tabla`` (una ``tipos.EntradasDecision``), con los mínimos de las
    relativas sobre E0 (§6.2, paso 2). Columnas ``COLUMNAS_COMPUERTAS``; ``pasa`` = False es una compuerta fallida
    (DEC-1 a DEC-5). En TF, ``valor`` es la media ponderada, ``referencia`` el P95 y ``cota`` la de la media."""
    prep = _preparar(uso, grupo, tabla)
    return _tabla_compuertas(_evaluacion(prep, umbrales).filas)


# ---------------------------------------------------------------------------------------------------------------
# decidir_combinacion (§6.2)
# ---------------------------------------------------------------------------------------------------------------
def _s_del_grupo(prep: _Preparadas) -> dict[str, float]:
    """DEC-7: S del grupo para los de E0 (S_par con los mínimos sobre E0, §5.3)."""
    por_variable = [_metricas(prep, v, "S", prep.e0) for v in prep.variables.S]
    if len(por_variable) == 1:
        return dict(por_variable[0])
    if len(por_variable) != 2:
        raise ValueError(f"S de ({prep.uso.value}, {prep.grupo.value}) con {len(por_variable)} variables")
    s1, s2 = por_variable
    m1, m2 = min(s1.values()), min(s2.values())
    if m1 <= 0 or m2 <= 0:
        raise ValueError("S_par: un mínimo sobre E0 es 0 (§5.3)")
    peso = constantes.valor("S_PAR_PESO")
    return {c: peso * (s1[c] / m1 + s2[c] / m2) for c in prep.e0}


def _menor(conjunto, S: Mapping[str, float], orden: tuple[str, ...]) -> str:
    """DEC-8: menor S; un empate exacto en float64 se rompe por el orden fijo."""
    return min(conjunto, key=lambda c: (S[c], orden.index(c)))


def _falla_tf(motivos: tuple[str, ...]) -> bool:
    return any(m in _MOTIVOS_TF for m in motivos)


def _falla_tf_o_deriva(prep: _Preparadas, c: str, ev: _Evaluacion) -> bool:
    """DEC-9: «al menos uno de ellos falla TF o la compuerta de deriva» (§6.2, paso 5). Fuera de E0, con sus filas de
    TF comprobadas como las de E0 (DEC-5); una TF2 «no evaluable» de B o AB cuenta como falla (EMC1-2)."""
    if Compuerta.DERIVA.value in prep.motivos_e0.get(c, ()):
        return True
    if c in prep.e0:
        return _falla_tf(ev.fallas[c])
    return ev.falla_tf_fuera.get(c, False)


def _intervalos(prep: _Preparadas, reportados: tuple[str, ...], conjunto: tuple[str, ...],
                orden: tuple[str, ...]) -> dict[str, tuple[float, float]]:
    """DEC-12 (MC-34, D46): intervalo percentil de S_c,r − S_g(r),r, sin interpolar, con g(r) el de menor S de la
    réplica r dentro de ``conjunto`` (el de la decisión) y el desempate fijo ``orden``."""
    if not conjunto or not set(conjunto) <= set(prep.e0):
        raise ValueError(f"replicas: el conjunto de la decisión {conjunto} debe ser parte de E0 {prep.e0} (DEC-12)")
    por: dict[int, dict[str, float]] = {}
    for fila in _registros(prep.replicas):
        c = _texto(fila, "candidato", "replicas")
        if c not in prep.e0:
            raise ValueError(f"replicas: {c} no está en E0 {prep.e0}")
        if not _finito(fila["S"]):
            raise ValueError(f"replicas: S no finito de {c} en la réplica {fila['replica']}")
        d = por.setdefault(int(fila["replica"]), {})
        if c in d:
            raise ValueError(f"replicas: {c} repetido en la réplica {fila['replica']}")
        d[c] = float(fila["S"])
    if not por:
        raise ValueError("replicas: sin réplicas del remuestreo (§5.4)")
    incompletas = sorted(r for r, d in por.items() if set(d) != set(prep.e0))
    if incompletas:
        raise ValueError(f"replicas: {len(incompletas)} réplicas (la primera, {incompletas[0]}) no traen a todos "
                         f"los de E0 {prep.e0}")
    replicas = sorted(por)
    # MC-34 (D46): el ganador de cada réplica, con el mismo conjunto y el mismo desempate que la decisión (DEC-8).
    s_ganador = np.array([por[r][_menor(conjunto, por[r], orden)] for r in replicas], dtype="float64")
    nivel = constantes.valor("BOOT_IC_PCT") / 100
    a = round((1.0 - nivel) / 2, 12)
    salida = {}
    for c in reportados:
        d = np.array([por[r][c] for r in replicas], dtype="float64") - s_ganador
        salida[c] = (float(np.quantile(d, a, method=METODO_CUANTIL)),
                     float(np.quantile(d, 1.0 - a, method=METODO_CUANTIL)))
    return salida


def _notas(*presentes: str) -> tuple[str, ...]:
    return tuple(n for n in ORDEN_NOTAS if n in presentes)


def _decidir(prep: _Preparadas, umbrales, *, restringida: bool = False) -> DecisionGrupo:
    ev = _evaluacion(prep, umbrales)
    S = _s_del_grupo(prep)
    orden = ORDEN_DESEMPATE[prep.uso]
    e1 = tuple(c for c in prep.e0 if not ev.fallas[c])
    falla_tf = {c: _falla_tf(ev.fallas[c]) for c in prep.e0}
    presentes = [NOTA_TF2_NO_EVALUABLE] if ev.tf2_no_evaluable else []
    motivos = {c: prep.motivos_e0[c] if c in prep.motivos_e0 else ev.fallas[c] for c in prep.candidatos}
    if restringida:
        # DEC-15: entre A y C de E0, con las compuertas y los mínimos de la decisión original.
        if prep.uso is not Uso.AMBIENTAL:
            raise ValueError("el ganador restringido es del uso ambiental (Anexo B, rama 3)")
        e0 = tuple(c for c in prep.e0 if c in ELEGIBLES_RESTRINGIDO)
        e1 = tuple(c for c in e1 if c in ELEGIBLES_RESTRINGIDO)
        if not e0:
            raise ValueError(f"rama 3 en {prep.grupo.value}: ni A ni C están en E0")
        conjunto = e1 or tuple(c for c in e0 if not falla_tf[c])
        presentes.append(NOTA_RESTRINGIDO)
        for c in prep.candidatos:
            if c not in ELEGIBLES_RESTRINGIDO:
                motivos[c] = tuple(m for m in ORDEN_MOTIVOS if m in (*motivos[c], MOTIVO_TF_CONTAMINANTES))
    else:
        e0 = prep.e0
        regla_cronica = (prep.uso is Uso.CRONICO and not any(c in e1 for c in CON_DERIVA)
                         and any(_falla_tf_o_deriva(prep, c, ev) for c in CON_DERIVA))
        if regla_cronica:
            presentes.append(NOTA_REGLA_CRONICA)
            conjunto = (tuple(c for c in e1 if c in ESTABLES_CRONICO)
                        or tuple(c for c in e0 if c in ESTABLES_CRONICO))
            if not conjunto:
                raise ValueError("regla crónica: ni A ni C_est están en E0 (§6.2, paso 5)")
        else:
            conjunto = e1 or tuple(c for c in e0 if not falla_tf[c])
    if not e1:
        presentes.append(NOTA_REGLA_SIN_GANADOR)
    if not conjunto:
        raise ValueError(f"({prep.uso.value}, {prep.grupo.value}): E1 vacío y ningún candidato de E0 pasa TF "
                         "(§6.2, paso 4)")
    ganador = _menor(conjunto, S, orden)
    return DecisionGrupo(
        uso=prep.uso, grupo=prep.grupo, e0=e0, e1=e1,
        motivos={c: m for c, m in motivos.items() if m},
        S={c: S[c] for c in e0},
        delta_S={c: S[c] - S[ganador] for c in e0},
        ic_delta_S=_intervalos(prep, e0, conjunto, orden),      # DEC-12: el mismo conjunto, réplica por réplica (D46)
        red_tf2=dict(ev.red_tf2), notas=_notas(*presentes), ganador=ganador)


def decidir_combinacion(uso, grupo, entradas, *, umbrales) -> DecisionGrupo:
    """§6.2 para un (uso, grupo): E0 (paso 1), E1 con las compuertas de §6.1 y los mínimos sobre E0 (paso 2), el menor
    S de E1 con el desempate A, AB, B, C (C_est en lo crónico; paso 3), E1 vacío (paso 4), la regla crónica (paso 5) y
    el registro (paso 6). Devuelve ``tipos.DecisionGrupo``. Lecturas DEC-1 a DEC-12 y DEC-20."""
    return _decidir(_preparar(uso, grupo, entradas), umbrales)


# ---------------------------------------------------------------------------------------------------------------
# decision.json (§6.2, paso 6; §8)
# ---------------------------------------------------------------------------------------------------------------
def _a_json(x, donde: str) -> Any:
    """Números de Python (finitos), textos, booleanos, listas y diccionarios con claves de texto."""
    if isinstance(x, Enum):
        return x.value
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return {f.name: _a_json(getattr(x, f.name), f"{donde}.{f.name}") for f in dataclasses.fields(x)}
    if isinstance(x, Mapping):
        salida = {}
        for k in sorted(x, key=lambda k: str(k.value if isinstance(k, Enum) else k)):
            clave = k.value if isinstance(k, Enum) else k
            if not isinstance(clave, str):
                raise TypeError(f"{donde}: clave no textual {k!r}")
            salida[clave] = _a_json(x[k], f"{donde}.{clave}")
        return salida
    if isinstance(x, (list, tuple)):
        return [_a_json(v, f"{donde}[{i}]") for i, v in enumerate(x)]
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        if not math.isfinite(x):
            raise ValueError(f"{donde}: número no finito {x!r}")
        return float(x)
    if x is None or isinstance(x, str):
        return x
    raise TypeError(f"{donde}: tipo no admitido {type(x).__name__}")


def _huellas(huellas) -> dict:
    """DEC-18 (CEG-15): {ruta por alias: sha256} o {ruta: {sha256, bytes}}; ninguna ruta absoluta."""
    if not isinstance(huellas, Mapping):
        raise TypeError("huellas debe ser un diccionario {ruta por alias: sha256}")
    salida = {}
    for ruta in sorted(huellas):
        valor = huellas[ruta]
        if (not isinstance(ruta, str) or not ruta or ruta.startswith(("/", "~")) or "\\" in ruta
                or any(ch.isspace() for ch in ruta) or re.match(r"[A-Za-z]:", ruta)):
            raise ValueError(f"huellas: {ruta!r} no es una ruta por alias o relativa")
        if isinstance(valor, str) and _SHA256.fullmatch(valor):
            salida[ruta] = valor
        elif (isinstance(valor, Mapping) and set(valor) == {"sha256", "bytes"} and isinstance(valor["sha256"], str)
              and _SHA256.fullmatch(valor["sha256"]) and isinstance(valor["bytes"], int)
              and not isinstance(valor["bytes"], bool) and valor["bytes"] >= 0):
            salida[ruta] = {"sha256": valor["sha256"], "bytes": int(valor["bytes"])}
        else:
            raise ValueError(f"huellas: valor de {ruta!r} no es un sha256 ni {{sha256, bytes}}: {valor!r}")
    return salida


def _clave_uso_grupo(k) -> tuple[Uso, Grupo]:
    if isinstance(k, str):
        partes = k.split("/")
        if len(partes) != 2:
            raise ValueError(f"hiperparametros: clave {k!r}; se espera «uso/grupo» o (uso, grupo)")
        k = tuple(partes)
    if not isinstance(k, tuple) or len(k) != 2:
        raise ValueError(f"hiperparametros: clave {k!r}; se espera «uso/grupo» o (uso, grupo)")
    clave = (Uso(k[0]), Grupo(k[1]))
    if clave not in VARIABLES:
        raise ValueError(f"hiperparametros: ({clave[0].value}, {clave[1].value}) no es un (uso, grupo) de §6.1")
    return clave


def _comprobar_decision(d: DecisionGrupo) -> None:
    if not isinstance(d, DecisionGrupo):
        raise TypeError(f"se espera tipos.DecisionGrupo, no {type(d).__name__}")
    if not set(d.e1) <= set(d.e0) or d.ganador not in d.e0:
        raise ValueError(f"({d.uso}, {d.grupo}): E1 ⊆ E0 y el ganador en E0")
    if set(d.S) != set(d.e0) or set(d.delta_S) != set(d.e0) or set(d.ic_delta_S) != set(d.e0):
        raise ValueError(f"({d.uso}, {d.grupo}): S, ΔS y su intervalo deben ir para los de E0")


def decision_json(decisiones, hiperparametros, huellas: dict) -> dict:
    """``decision.json`` (§6.2, paso 6): por (uso, grupo), E0, E1, los motivos de exclusión, S, ΔS y su intervalo, la
    red de TF2, las notas y el ganador, más los hiperparámetros de producción (M3-4, paso 11) y las huellas de las
    entradas (§8, «Cadena de huellas»). ``hiperparametros``: {(uso, grupo) o «uso/grupo»: {…}} para cada decisión.
    Orden fijo (DEC-18)."""
    lista = list(decisiones)
    claves = []
    for d in lista:
        _comprobar_decision(d)
        claves.append((Uso(d.uso), Grupo(d.grupo)))
    if len(set(claves)) != len(claves):
        raise ValueError("decision_json: un (uso, grupo) repetido")
    if not isinstance(hiperparametros, Mapping):
        raise TypeError("hiperparametros debe ser un diccionario por (uso, grupo)")
    hip = {}
    for k, v in hiperparametros.items():
        clave = _clave_uso_grupo(k)
        if clave in hip:
            raise ValueError(f"hiperparametros: ({clave[0].value}, {clave[1].value}) repetido")
        hip[clave] = v
    if set(hip) != set(claves):
        raise ValueError("hiperparametros: deben ir exactamente para los (uso, grupo) decididos")
    orden = list(VARIABLES)
    salida = []
    for d in sorted(lista, key=lambda d: orden.index((Uso(d.uso), Grupo(d.grupo)))):
        clave = (Uso(d.uso), Grupo(d.grupo))
        donde = f"{clave[0].value}/{clave[1].value}"
        salida.append({
            "uso": clave[0].value, "grupo": clave[1].value, "ganador": _candidato(d.ganador),
            "e0": [_candidato(c) for c in d.e0], "e1": [_candidato(c) for c in d.e1],
            "motivos": {_candidato(c): [str(m) for m in d.motivos[c]] for c in d.motivos},
            "S": _a_json({c: d.S[c] for c in d.e0}, f"{donde}.S"),
            "delta_S": _a_json({c: d.delta_S[c] for c in d.e0}, f"{donde}.delta_S"),
            "ic_delta_S": _a_json({c: list(d.ic_delta_S[c]) for c in d.e0}, f"{donde}.ic_delta_S"),
            "red_tf2": {v: ReglaRedConstante(r).value for v, r in d.red_tf2.items()},
            "notas": [str(n) for n in d.notas],
            "hiperparametros": _a_json(hip[clave], f"{donde}.hiperparametros"),
        })
    return {"esquema": ESQUEMA_DECISION, "decisiones": salida, "huellas": _huellas(huellas)}


# ---------------------------------------------------------------------------------------------------------------
# Anexo B (M6)
# ---------------------------------------------------------------------------------------------------------------
def _condiciones_fila(fila: Mapping, margen) -> tuple[bool, ...]:
    """DEC-13: las 7 condiciones en una fila (un protocolo)."""
    donde = f"{fila['contaminante']}, {fila['sentido']}, {fila['protocolo']}"
    no_finitos = [c for c in ("ic_bajo", "ic_alto", "nmb_c", "nmb_otra") if not _finito(fila[c])]
    if no_finitos:
        raise ValueError(f"comparacion: {no_finitos} no finitos en {donde}; la condición no se decide (DEC-13)")
    bajo, alto, nmb_c, nmb_otra = (float(fila[c]) for c in ("ic_bajo", "ic_alto", "nmb_c", "nmb_otra"))
    if bajo > alto:
        raise ValueError(f"comparacion: ic_bajo > ic_alto en {donde} (DEC-13)")
    condiciones = (
        bool(bajo > 0 and fila["segunda_prueba_coincide"]),           # «excluye 0 a favor de c»
        bool(fila["supera_ruido"]),
        bool(fila["consistencia_e2"]),
        bool(fila["sobrevive_bloque"]),
        bool(fila["signo_sin_ponderar"] and fila["signo_log"]),
        bool(fila["decision_sigma2"]),
        bool(abs(nmb_c) <= abs(nmb_otra) + margen),
    )
    if len(condiciones) != constantes.valor("M6_CONDICIONES"):
        raise AssertionError("el Anexo B tiene 7 condiciones")
    return condiciones


def condiciones_anexo_b(comparacion, contaminante: str, sentido: str, umbrales) -> list[bool]:
    """Las 7 condiciones del Anexo B para un contaminante y un sentido (c = la variante que reemplaza), cada una en LRO
    y en BLQ-75 a la vez (DEC-13). ``comparacion`` va en ``ESQUEMA_COMPARACION_M6`` (MC-30)."""
    tipos.validar_esquema(comparacion, tipos.ESQUEMA_COMPARACION_M6, nombre="comparacion")
    if contaminante not in CONTAMINANTES_M6:
        raise ValueError(f"contaminante {contaminante!r}; el Anexo B compara {CONTAMINANTES_M6}")
    sentido = Sentido(sentido)
    filas: dict[Protocolo, dict] = {}
    for fila in _registros(comparacion):
        pol = _texto(fila, "contaminante", "comparacion")
        if pol not in CONTAMINANTES_M6:
            raise ValueError(f"comparacion: contaminante {pol!r} fuera del Anexo B")
        s = Sentido(_texto(fila, "sentido", "comparacion"))
        protocolo = Protocolo(_texto(fila, "protocolo", "comparacion"))
        if pol != contaminante or s is not sentido:
            continue
        if protocolo in filas:
            raise ValueError(f"comparacion: fila repetida {(pol, s.value, protocolo.value)}")
        filas[protocolo] = fila
    if set(filas) != set(Protocolo):
        raise ValueError(f"comparacion: {contaminante}, {sentido.value} debe traer LRO y BLQ-75 (a la vez)")
    margen = umbrales.a("M6_NMB_PP")
    por_protocolo = [_condiciones_fila(filas[p], margen) for p in Protocolo]
    return [all(c[i] for c in por_protocolo) for i in range(len(por_protocolo[0]))]


def _siete(valores, donde: str) -> tuple[bool, ...]:
    t = tuple(valores)
    if len(t) != constantes.valor("M6_CONDICIONES") or not all(isinstance(x, (bool, np.bool_)) for x in t):
        raise ValueError(f"{donde}: se esperan las 7 condiciones del Anexo B como booleanos: {valores!r}")
    return tuple(bool(x) for x in t)


def _quien_supera(por_sentido: Mapping[Sentido, tuple[bool, ...]], pol: str) -> Variante | None:
    """Simetría (DEC-14): «Supera» la variante que cumple las 7 condiciones; a lo más una."""
    quienes = [_REEMPLAZA[s] for s in Sentido if all(por_sentido[s])]
    if len(quienes) > 1:
        raise ValueError(f"{pol}: las dos variantes cumplen las 7 condiciones; la condición 1 no lo permite")
    return quienes[0] if quienes else None


def _ganadores_ambientales(ganador_ambiental) -> dict[Grupo, str]:
    if not isinstance(ganador_ambiental, Mapping):
        raise TypeError("ganador_ambiental debe ser {grupo: candidato}")
    salida = {Grupo(g): _candidato(c) for g, c in ganador_ambiental.items()}
    if set(salida) != set(GRUPOS_AMBIENTALES) or len(salida) != len(ganador_ambiental):
        raise ValueError(f"ganador_ambiental debe traer los grupos {[g.value for g in GRUPOS_AMBIENTALES]}")
    for g, c in salida.items():
        if c not in CANDIDATOS_USO[Uso.AMBIENTAL]:
            raise ValueError(f"ganador_ambiental[{g.value}] = {c}: no es candidato ambiental")
    return salida


def _tf_contaminante(tf_pol, variante: Variante, *, exigida: bool, pol: str) -> ResultadoTF:
    """DEC-14: «pasa» o «falla». Sin B ni AB, la de I es la verificación de un mes y debe venir con «pasa»."""
    if not isinstance(tf_pol, Mapping):
        raise TypeError(f"tf_contaminantes[{pol}] debe ser {{variante: resultado}}")
    claves = {Variante(k) for k in tf_pol}
    if len(claves) != len(tf_pol):
        raise ValueError(f"tf_contaminantes[{pol}]: variantes repetidas")
    valor = next((tf_pol[k] for k in tf_pol if Variante(k) is variante), None)
    if valor is None:
        que = "la TF" if exigida else "la verificación de un mes de la TF"
        raise ValueError(f"tf_contaminantes[{pol}]: falta {que} de {variante.value} (Anexo B; DEC-14)")
    resultado = ResultadoTF(valor)
    if resultado is ResultadoTF.NO_EVALUABLE:
        raise ValueError(f"tf_contaminantes[{pol}][{variante.value}]: la TF de contaminantes no tiene «no evaluable»")
    if not exigida and resultado is ResultadoTF.FALLA:
        raise ValueError(f"tf_contaminantes[{pol}][I] = falla con ganadores A o C: es 0 por construcción; es un error "
                         "de código (Anexo B)")
    return resultado


def variante_o3(por_contaminante: dict) -> str:
    """O3: la variante elegida en PM2,5 y NO2 si coinciden; si difieren, I (Anexo B; DEC-17)."""
    if not isinstance(por_contaminante, Mapping) or set(por_contaminante) != set(CONTAMINANTES_M6):
        raise ValueError(f"variante_o3 necesita exactamente {CONTAMINANTES_M6}: {por_contaminante!r}")
    variantes = {Variante(por_contaminante[p]) for p in CONTAMINANTES_M6}
    return variantes.pop().value if len(variantes) == 1 else Variante.I.value


def _entradas_ambientales(entradas_ambientales) -> dict[Grupo, EntradasDecision]:
    if not isinstance(entradas_ambientales, Mapping):
        raise TypeError("entradas_ambientales debe ser {grupo: tipos.EntradasDecision}")
    salida = {}
    for g, e in entradas_ambientales.items():
        g = Grupo(g)
        if g in salida:
            raise ValueError(f"entradas_ambientales: {g.value} repetido")
        if not isinstance(e, EntradasDecision) or Uso(e.uso) is not Uso.AMBIENTAL or Grupo(e.grupo) is not g:
            raise ValueError(f"entradas_ambientales[{g.value}] debe ser la EntradasDecision ambiental de ese grupo")
        salida[g] = e
    if set(salida) != set(GRUPOS_AMBIENTALES):
        raise ValueError(f"entradas_ambientales debe traer los grupos {[g.value for g in GRUPOS_AMBIENTALES]}")
    return salida


def _originales(entradas_ambientales, umbrales) -> dict[Grupo, tuple[_Preparadas, DecisionGrupo]]:
    """La decisión ambiental original de cada grupo (§6.2), con sus entradas preparadas."""
    entradas = _entradas_ambientales(entradas_ambientales)
    salida = {}
    for g in GRUPOS_AMBIENTALES:
        prep = _preparar(Uso.AMBIENTAL, g, entradas[g])
        salida[g] = (prep, _decidir(prep, umbrales))
    return salida


def _restringidas(originales, grupos_con_b_ab, umbrales) -> dict[str, DecisionGrupo]:
    if isinstance(grupos_con_b_ab, (str, bytes)):
        raise TypeError("grupos_con_b_ab debe ser un conjunto de grupos")
    pedidos = {Grupo(g) for g in grupos_con_b_ab}
    salida = {}
    for g in GRUPOS_AMBIENTALES:
        prep, original = originales[g]
        con_b_ab = original.ganador in CON_DERIVA
        if con_b_ab != (g in pedidos):
            raise ValueError(f"grupos_con_b_ab: el ganador ambiental de {g.value} es {original.ganador}")
        salida[g.value] = _decidir(prep, umbrales, restringida=True) if con_b_ab else original
    return salida


def decisiones_restringidas(entradas_ambientales, grupos_con_b_ab, *, umbrales) -> dict[str, DecisionGrupo]:
    """Rama 3 del Anexo B (DEC-15): la decisión ambiental de cada grupo, rehecha entre A y C en los grupos cuyo ganador
    era B o AB y la original en los demás. ``grupos_con_b_ab`` debe ser el conjunto que dan las entradas."""
    return _restringidas(_originales(entradas_ambientales, umbrales), grupos_con_b_ab, umbrales)


def ganador_restringido(entradas_ambientales, grupos_con_b_ab, *, umbrales) -> dict:
    """Rama 3 (Anexo B): {grupo: ganador} con A o C donde el ganador ambiental era B o AB, y el mismo en los demás."""
    return {g: d.ganador for g, d in decisiones_restringidas(entradas_ambientales, grupos_con_b_ab,
                                                             umbrales=umbrales).items()}


def ramas_m6(condiciones: dict, tf_contaminantes: dict, ganador_ambiental: dict, *, entradas_ambientales=None,
             umbrales=None) -> DecisionM6:
    """Ramas cerradas del Anexo B por contaminante, la variante de O3 y, si la rama 3 rige en alguno, el ganador
    ambiental restringido para todos (§6.4; DEC-14 a DEC-17).

    ``condiciones``: {contaminante: {sentido: 7 booleanos}} (``condiciones_anexo_b``); ``tf_contaminantes``:
    {contaminante: {variante: «pasa»|«falla»}}, las dos variantes siempre (DEC-14); ``ganador_ambiental``: {grupo:
    candidato} de ``decision.json``. Con la rama 3, ``entradas_ambientales`` ({grupo: EntradasDecision}) y ``umbrales``
    son obligatorios; si vienen, ``ganador_ambiental`` debe ser el que dan (DEC-16)."""
    ganadores = _ganadores_ambientales(ganador_ambiental)
    originales = None
    if entradas_ambientales is not None:
        if umbrales is None:
            raise ValueError("con entradas_ambientales hacen falta los umbrales (DEC-16)")
        originales = _originales(entradas_ambientales, umbrales)
        distintos = {g.value: (ganadores[g], d.ganador) for g, (_, d) in originales.items()
                     if d.ganador != ganadores[g]}
        if distintos:
            raise ValueError(f"ganador_ambiental distinto del que dan las entradas (recibido, calculado): {distintos} "
                             "(DEC-16)")
    i_exigida = any(c in CON_DERIVA for c in ganadores.values())
    for nombre, x in (("condiciones", condiciones), ("tf_contaminantes", tf_contaminantes)):
        if not isinstance(x, Mapping) or set(x) != set(CONTAMINANTES_M6):
            raise ValueError(f"{nombre} debe traer exactamente {CONTAMINANTES_M6}")
    rama, variante, conds = {}, {}, {}
    for pol in CONTAMINANTES_M6:
        if not isinstance(condiciones[pol], Mapping):
            raise TypeError(f"condiciones[{pol}] debe ser {{sentido: 7 booleanos}}")
        por_sentido = {Sentido(s): _siete(v, f"condiciones[{pol}][{s}]") for s, v in condiciones[pol].items()}
        if set(por_sentido) != set(Sentido) or len(por_sentido) != len(condiciones[pol]):
            raise ValueError(f"condiciones[{pol}] debe traer los dos sentidos (simetría)")
        conds[pol] = {s.value: por_sentido[s] for s in Sentido}
        supera = _quien_supera(por_sentido, pol)
        tf = {Variante.I: _tf_contaminante(tf_contaminantes[pol], Variante.I, exigida=i_exigida, pol=pol),
              Variante.D: _tf_contaminante(tf_contaminantes[pol], Variante.D, exigida=True, pol=pol)}
        if supera is not None and tf[supera] is ResultadoTF.PASA:
            rama[pol], variante[pol] = Rama.UNO, supera
        elif tf[Variante.I] is ResultadoTF.PASA:
            rama[pol], variante[pol] = Rama.DOS, Variante.I
        elif tf[Variante.D] is ResultadoTF.PASA:
            rama[pol], variante[pol] = Rama.DOS, Variante.D
        else:
            rama[pol], variante[pol] = Rama.TRES, Variante.I
    variante[CLAVE_O3] = Variante(variante_o3({p: variante[p] for p in CONTAMINANTES_M6}))
    restringido, notas = None, ()
    if any(r is Rama.TRES for r in rama.values()):
        if originales is None:
            raise ValueError("la rama 3 rige: hacen falta entradas_ambientales y umbrales para el ganador restringido")
        con_b_ab = {g for g, c in ganadores.items() if c in CON_DERIVA}
        restringido = {g: d.ganador for g, d in _restringidas(originales, con_b_ab, umbrales).items()}
        notas = (NOTA_RESTRINGIDO,)
    return DecisionM6(rama=rama, condiciones=conds, variante=variante, ganador_restringido=restringido, notas=notas)


def decision_m6_json(decision: DecisionM6, huellas: dict) -> dict:
    """``decision_m6.json`` (§8: ramas, condiciones y variante por contaminante; D14: clase «resumen»): quién supera,
    la rama, las 7 condiciones por sentido, la variante (y la de O3), el ganador restringido y las notas, con las
    huellas (DEC-18)."""
    if not isinstance(decision, DecisionM6):
        raise TypeError(f"se espera tipos.DecisionM6, no {type(decision).__name__}")
    if set(decision.rama) != set(CONTAMINANTES_M6) or set(decision.condiciones) != set(CONTAMINANTES_M6):
        raise ValueError(f"decision_m6: rama y condiciones deben ir para {CONTAMINANTES_M6}")
    if set(decision.variante) != {*CONTAMINANTES_M6, CLAVE_O3}:
        raise ValueError(f"decision_m6: la variante va para {CONTAMINANTES_M6} y {CLAVE_O3}")
    condiciones, supera = {}, {}
    for pol in CONTAMINANTES_M6:
        por_sentido = {Sentido(s): _siete(v, f"condiciones[{pol}][{s}]") for s, v in decision.condiciones[pol].items()}
        if set(por_sentido) != set(Sentido):
            raise ValueError(f"decision_m6: condiciones[{pol}] debe traer los dos sentidos")
        condiciones[pol] = {s.value: list(por_sentido[s]) for s in Sentido}
        quien = _quien_supera(por_sentido, pol)
        supera[pol] = quien.value if quien is not None else None
    restringido = decision.ganador_restringido
    if restringido is not None:
        restringido = {Grupo(g).value: _candidato(c) for g, c in restringido.items()}
        if set(restringido) != {g.value for g in GRUPOS_AMBIENTALES}:
            raise ValueError("decision_m6: el ganador restringido va para los tres grupos ambientales")
        if any(c not in ELEGIBLES_RESTRINGIDO for g, c in restringido.items()):
            raise ValueError("decision_m6: el ganador restringido es A o C (Anexo B, rama 3)")
    if (restringido is not None) != any(Rama(r) is Rama.TRES for r in decision.rama.values()):
        raise ValueError("decision_m6: el ganador restringido va si y sólo si la rama 3 rige en algún contaminante")
    return {"esquema": ESQUEMA_DECISION_M6,
            "rama": {p: int(Rama(decision.rama[p])) for p in CONTAMINANTES_M6},
            "supera": supera,
            "condiciones": condiciones,
            "variante": {k: Variante(decision.variante[k]).value for k in (*CONTAMINANTES_M6, CLAVE_O3)},
            "ganador_restringido": restringido,
            "notas": [str(n) for n in decision.notas],
            "huellas": _huellas(huellas)}
