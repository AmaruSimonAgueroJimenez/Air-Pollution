"""Constantes del texto que NO están en el Anexo B (definiciones, fórmulas y umbrales del cuerpo).

No son ajustables por §8.F. Cada una lleva su sección y un fragmento literal del protocolo;
``verificar_contra_texto`` exige que el fragmento aparezca tal cual en el texto, dentro de su sección, y
que los números que contiene coincidan con el valor. Si un texto consolidado cambia alguno, la prueba
falla y obliga a revisar. Ver el riesgo R-17 del diseño (umbrales del cuerpo fuera del Anexo B).

Versiones del texto (``TEXTOS_PROTOCOLO``). El Anexo B, «Fijos del cuerpo» [Enmienda 1, E1-5], pide que
cada fragmento aparezca tal cual en el texto VIGENTE, que es la última versión (``VERSION_VIGENTE``). El
``fragmento`` de una constante es el del texto vigente. Una constante que nace en una versión posterior a
la de C0 lleva ``desde``; si su fragmento cambió (el de SUBH_LAT_MAX, con la Enmienda 3, E3-5), el de las
versiones anteriores va en ``fragmento_anterior``, con los mismos ``ajenos``. Así una misma lista se
verifica contra cada versión (``verificar_contra_texto(texto, version=…)``): una constante nueva no se
busca en los textos anteriores a ``desde``.

Cómo se leen los números (``numeros_del_fragmento``): como los escribe el texto, con «−» (U+2212) o
«+» de signo (también «− 0,03» en una suma), miles con «.» y decimales con «,»; el guion ASCII de
«2008-2026» o «00-05» no es signo. No cuentan las cifras pegadas a una letra («A1», «E3p», «t2m»,
«κ3», «2π», «2B»). En un valor de texto cuentan sus grupos de cifras («2015-09-06T00:00»).
Regla: los números del valor, en orden, son una subsucesión de los del fragmento, y los que sobran
son exactamente ``ajenos`` (en su orden): números de otras constantes o del Anexo B que el fragmento
cita para ser legible. Los textos sin cifras ni llaves del valor deben estar tal cual en el fragmento.
Depende de: nada.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterator


# Versiones del texto del protocolo, en orden: (versión, ruta relativa a APH, sha256). La primera es la
# anclada en C0 (la misma ruta y huella que umbrales.PROTOCOLO_C0 y SHA_PROTOCOLO_C0; lo comprueba
# test_umbrales). Las huellas del v1.0.1 y del v1.0.2 son las de enmienda2/ENMIENDA_2.md; la del v1.0.3
# (Enmiendas 1, 2 y 3, adoptadas el 2026-10-24), la de enmienda3/ENMIENDA_3.md, anclada en APH e43a6fe; la
# del v1.0.4 (Enmienda 4 del reloj, adoptada el 2026-10-25: el tipo f sale de lo indecidible de §8.D), la que
# da enmienda4/generar_v1_0_4.py y cita enmienda4/ENMIENDA_4.md (su anclaje, un commit local y su sello, está
# pendiente: si el texto cambia antes, las pruebas fallan y hay que revisar los fragmentos antes de poner la
# huella nueva). La Enmienda 4 no cambia ningún fragmento de CONSTANTES ni de bateria.CONSTANTES_BATERIA; la
# frase que cambia la lee bateria.FRAGMENTO_INDECIDIBLE. La última versión es la vigente.
TEXTOS_PROTOCOLO = (
    ("v1", "auditoria/20261023/reloj_dmc/PROTOCOLO_RELOJ_DMC_v1_propuesta.md",
     "5fff072783e932843d210561a46f5344351a39b7dd85f5775ac884eaf96e4d85"),
    ("v1.0.1", "auditoria/20261023/reloj_dmc/enmienda1/PROTOCOLO_RELOJ_DMC_v1.0.1.md",
     "8a1e538346dac4cb286119e6a041f84c555c2e86e0313b73162d5dc5e73d8f52"),
    ("v1.0.2", "auditoria/20261023/reloj_dmc/enmienda2/PROTOCOLO_RELOJ_DMC_v1.0.2.md",
     "ee5dec6e7a1ff65f19a814d4994d804e9a4e3e8ad2765b6d8590e9286543217d"),
    ("v1.0.3", "auditoria/20261023/reloj_dmc/enmienda3/PROTOCOLO_RELOJ_DMC_v1.0.3.md",
     "7a019348b8ff6e26cef81c86881265a3392172acbf175b118a8682e9cd345f97"),
    ("v1.0.4", "auditoria/20261023/reloj_dmc/enmienda4/PROTOCOLO_RELOJ_DMC_v1.0.4.md",
     "d8f61cfc1ab01da17fd97b8e5e871b55d4557a66ff2599a585b362689475b54d"),
)
VERSIONES_TEXTO = tuple(v for v, _, _ in TEXTOS_PROTOCOLO)
VERSION_VIGENTE = VERSIONES_TEXTO[-1]
# El texto consolidado de C1 (§10, v1.1): el v1.0.4 con el cierre de C1, sin cambiar ningún fragmento (lo comprueba
# generar_v1_1.py con verificar_contra_texto(v1.1, version=VERSION_C1)). Va después de la vigente y lleva sus
# fragmentos. Su sha256 no puede estar aquí: el v1.1 cita la salida de la corrida de C1, que corre este código, así
# que su huella la fija el addendum de C1 («texto_v1_1»). PEN-9 de C1.
VERSION_C1 = "v1.1"


def indice_version(version: str) -> int:
    """Posición de una versión del texto en VERSIONES_TEXTO (VERSION_C1 va a continuación de la última);
    ValueError si no es ninguna de ellas."""
    if version == VERSION_C1:
        return len(VERSIONES_TEXTO)
    if version not in VERSIONES_TEXTO:
        raise ValueError(f"versión del texto desconocida: {version!r} (son {[*VERSIONES_TEXTO, VERSION_C1]})")
    return VERSIONES_TEXTO.index(version)


@dataclass(frozen=True)
class ConstanteTexto:
    nombre: str
    valor: Any
    seccion: str
    fragmento: str          # tal cual en el texto vigente (VERSION_VIGENTE)
    ajenos: tuple = ()      # números del fragmento que no son de esta constante, en su orden
    desde: str = VERSIONES_TEXTO[0]          # primera versión del texto con ``fragmento``
    fragmento_anterior: str | None = None    # el de las versiones anteriores a ``desde``; None: no estaba

    def fragmento_en(self, version: str) -> str | None:
        """Fragmento de la constante en esa versión del texto; None si la constante todavía no estaba."""
        if indice_version(version) >= indice_version(self.desde):
            return self.fragmento
        return self.fragmento_anterior


CONSTANTES = (
    # §1, punto 13: predicciones registradas para N. Son descriptivas, no umbrales (las usa red.predicciones; un
    # incumplimiento es «predicción no cumplida», nunca una desviación). Los 0, 2 y −4 de los fragmentos son la
    # clase de E2 y el ĉ que cada reloj da por definición; red los deriva de c_H(R).
    ConstanteTexto("PRED_E1A_PRESENTE_PCT", 95, "§1", "E1a «presente» en ≥ 95 % de los adelantos evaluables;"),
    ConstanteTexto("PRED_E2_CLASE_PCT", 95, "§1", "E2 en clase 0 en ≥ 95 % de las partes informativas;", ajenos=(0,)),
    ConstanteTexto("PRED_E3P_E4P_ANIOS_PCT", 90, "§1",
                   "E3p con ĉ = 0, y E4p compatible con F(0), en ≥ 90 % de los años;", ajenos=(0, 0)),
    ConstanteTexto("PRED_GUARDAS_FALLAS_PCT", 1, "§1", "guardas con fallas en ≤ 1 % de los años, y A3 y A5 sin alto."),
    ConstanteTexto("PRED_F_MENOS4_PCT", (95, 95, 90), "§1",
                   "E1a «presente» en ≥ 95 %; E2 en clase 2 en ≥ 95 %; E3p con ĉ = −4 en ≥ 90 % de los años.",
                   ajenos=(2, -4)),     # E1a, E2 y E3p, en ese orden
    ConstanteTexto("PRED_CIVIL_E1A_PCT", 80, "§1",
                   "patrón civil de E1a en ≥ 80 % de las estaciones evaluables, con placebos ≤ 10 %;", ajenos=(10,)),
    ConstanteTexto("PRED_CIVIL_PLACEBOS_PCT", 10, "§1",
                   "patrón civil de E1a en ≥ 80 % de las estaciones evaluables, con placebos ≤ 10 %;", ajenos=(80,)),
    ConstanteTexto("COORD_LAT", (-90, -17), "§3.3", "Deben quedar dentro de −90 ≤ lat ≤ −17 y −110 ≤ lon ≤ −55.",
                   ajenos=(-110, -55)),
    ConstanteTexto("COORD_LON", (-110, -55), "§3.3", "Deben quedar dentro de −90 ≤ lat ≤ −17 y −110 ≤ lon ≤ −55.",
                   ajenos=(-90, -17)),
    ConstanteTexto("LAT_ANTARTICA", -60, "§3.3", "lat < −60 → Antártica"),
    ConstanteTexto("LON_PASCUA", -100, "§3.3", "lon < −100 → Isla de Pascua y Sala y Gómez"),
    ConstanteTexto("LON_JUAN_FERNANDEZ", (-100, -77), "§3.3", "−100 ≤ lon < −77 → Juan Fernández o Desventuradas"),
    ConstanteTexto("REGIONES_AUSTRALES", (11, 12), "§3.3", "11 → Aysén, 12 → Magallanes"),
    ConstanteTexto("REGION_DIVISOR", 1000, "§3.3", "la región es `cod_comuna // 1000`"),
    ConstanteTexto("PASOS_NATIVOS", (1, 2, 3, 6), "§3.2", "Si no es 1, 2, 3 o 6 h, E3 y E4 quedan sin información."),
    ConstanteTexto("HUELLA_TEXTOS", 21, "§3.2", "sha256 de los 21 textos crudos, sin día ni hora"),
    ConstanteTexto("ERA5_T2M_K", (200, 330), "§3.4", "la mediana de t2m debe quedar entre 200 y 330 K"),
    ConstanteTexto("ERA5_SP_PA", (40000, 110000), "§3.4", "la de sp entre 40.000 y 110.000 Pa"),
    ConstanteTexto("ERA5_ULTIMA_HORA_UTC", "2026-09-15T23:00", "§3.4", "El último dato es del 2026-09-15 a las 23:00 UTC."),
    ConstanteTexto("Z_PIX", (44330.8, 1013.25, 0.190263), "§3.3", "z_pix = 44.330,8·[1 − (sp̄/1.013,25)^0,190263] m",
                   ajenos=(1,)),
    ConstanteTexto("E3_CCONT_MAX", 8, "§4.3.1", "Se define sólo si |ĉ| ≤ 8."),
    ConstanteTexto("ALIAS_H", 12, "§4.3.1", "ĉ ≡ c_H (mód 12), con ĉ ≠ c_H."),
    ConstanteTexto("PERIODO_FILTRO_H", 24, "§4.3.1", "(mínimos cuadrados con constante, coseno y seno de período 24 h)"),
    ConstanteTexto("E3_DIST_RIVAL", 2, "§4.3.2", "r(H) − r(H′) ≥ μ para toda H′ con |c_H′ − c_H| ≥ 2;"),
    ConstanteTexto("E3_DIST_CHAT", 3, "§4.3.2", "|ĉ − c_H| ≥ 3, ĉ no es alias de 12 h de c_H, y r(ĉ) − r(H) ≥ μ.",
                   ajenos=(12,)),
    ConstanteTexto("E3T_DIA_MIN_VALORES", 20, "§4.3.3",
                   "Para Ts se usan los días de etiqueta con ≥ 20 valores (o completos si p > 1)", ajenos=(1,)),
    ConstanteTexto("FINA_LAT_MAX", 50, "§4.3.4", "|lat| ≤ 50°;"),
    ConstanteTexto("FINA_C_MAX", 8, "§4.3.4", "|ĉ^f| ≤ 8;"),
    ConstanteTexto("SUBH_LAT_MAX", 50, "§4.3.5",       # Enmienda 3, E3-5 (B6): cambia la frase, no el valor
                   "en todos los años-régimen de la estación con |lat| ≤ 50° y ĉ^f_cont definido", desde="v1.0.3",
                   fragmento_anterior="de los años confirmados con |lat| ≤ 50° y ĉ^f_cont definido"),
    # §4.3.5 con E3-5: período e intervalo de ρ. Es «el estadístico m de A5», así que lineas_fisicas usa
    # A5_ENVOLVER; test_umbrales comprueba que coinciden.
    ConstanteTexto("SUBH_MEDIA_CIRCULAR", (1, (-0.5, 0.5)), "§4.3.5",
                   "ρ es la media circular de período 1 h de ĉ^f_cont, llevada a horas en [−0,5; 0,5)", desde="v1.0.3"),
    ConstanteTexto("GRADOS_POR_HORA", 15, "§4.4", "t0(L) = (hora decimal de L + λ/15 + EoT/60) mód 24",
                   ajenos=(60, 24)),
    ConstanteTexto("E4_K_MAX", 3, "§4.4", "K = mín(3, ⌊(n_h − 1)/2⌋)", ajenos=(-1, 2)),
    ConstanteTexto("E4_DIA_MIN_VALORES", 20, "§4.4", "Se usan los días con ≥ 20 valores si p = 1, o completos si p > 1.",
                   ajenos=(1, 1)),
    ConstanteTexto("E4_PASO_6H", 6, "§4.4", "Con paso de 6 h, siempre queda sin información."),
    ConstanteTexto("SPENCER", (229.18, 0.000075, 0.001868, -0.032077, -0.014615, -0.040849), "§4.4",
                   "EoT = 229,18·(0,000075 + 0,001868 cos B − 0,032077 sen B − 0,014615 cos 2B − 0,040849 sen 2B)"),
    ConstanteTexto("SPENCER_B", 365, "§4.4", "B = 2π(n − 1)/365", ajenos=(-1,)),
    ConstanteTexto("E4T_K_PASO_6", 1, "§4.7", "Con paso de 6 h, usa K = 1.", ajenos=(6,)),   # 6: E4_PASO_6H
    ConstanteTexto("ANUAL_MIN_PARTES", 2, "§4.0", "o si lo es en ≥ 2 partes (en E6, ≥ 2 meses)", ajenos=(2,)),
    ConstanteTexto("E1A_PLACEBO_DIAS_CAMBIO", 3, "§4.1.1", "que estén a ≥ 3 días de cualquier cambio"),
    ConstanteTexto("E1A_PATRON_MIN_AUSENTES", 2, "§4.1.1", "≥ 2 eventos ausentes, con P0 = Π(1 − p_i) ≤ 0,01;",
                   ajenos=(1, 0.01)),   # 0,01: E1A_P0 del Anexo B
    ConstanteTexto("E1A_PATRON_AUSENTES_PCT", 80, "§4.1.1", "los ausentes son ≥ 80 % de los eventos evaluables de la estación;"),
    # §4.1.1 con E3-2 (A′): el patrón de regla vencida(Z, r) repite «los umbrales del patrón civil(Z)».
    # lineas_registro usa los del patrón civil (la misma regla, _patron); test_umbrales comprueba que
    # coinciden, y que los ajenos son E1A_P0 y E1A_PLACEBO del Anexo B.
    ConstanteTexto("E1A_RV_MIN_AUSENTES", 2, "§4.1.1", "≥ 2 eventos de r ausentes, con P0 ≤ 0,01;", ajenos=(0.01,),
                   desde="v1.0.3"),
    ConstanteTexto("E1A_RV_AUSENTES_PCT", 80, "§4.1.1",
                   "los ausentes son ≥ 80 % de los eventos evaluables de r; y la tasa de ausentes en los placebos del "
                   "mismo día de la semana que no son eventos de regla vencida es ≤ 0,10.", ajenos=(0.1,),
                   desde="v1.0.3"),
    ConstanteTexto("E1A_PLACEBO_2015", ("2015-09-06T00:00", "2015-09-05T22:00"), "§4.1.1",
                   "2015-09-06 00:00 (en Pascua, 2015-09-05 22:00)"),
    ConstanteTexto("E1B_PLACEBO_SEPARACION_D", 21, "§4.1.2", "a ±42 y ±63 días, a más de 21 días de otro cambio;",
                   ajenos=(42, 63)),    # E1B_PLACEBO_1_D y _2_D del Anexo B
    ConstanteTexto("E1C_MIN_MESES", 2, "§4.1.3", "y una casilla menos en ≥ 2 meses con adelanto de Z, y en ningún otro mes."),
    ConstanteTexto("E2_MODULO", 3, "§4.2", "La clase de una etiqueta es su hora módulo 3."),
    ConstanteTexto("E2_TXTN_DIST_H", 12, "§4.2", "sus etiquetas modales deben distar 12 h"),
    ConstanteTexto("E2_MIN_PARTES_COMPAT", 2, "§4.2", "E2 es compatible en el año sólo si hay ≥ 2 partes informativas"),
    ConstanteTexto("E3D_BLOQUES", ((0, 5), (6, 11), (12, 17), (18, 23)), "§4.7", "Bloques de etiqueta: 00-05, 06-11, 12-17 y 18-23 h."),
    ConstanteTexto("E3D_K", (-24, 0, 24), "§4.7", "con k ∈ {−24, 0, +24}"),
    ConstanteTexto("P7_PRESENCIA", 0.8, "§4.7", "en las estaciones con ≥ 22 etiquetas de presencia ≥ 0,8",
                   ajenos=(22,)),       # P7_ETIQUETAS del Anexo B
    ConstanteTexto("TP_DIST_RIVAL", 2, "§4.7", "D_R = {c_H′(R) − c_H(R) : H′ ∈ P, |c_H′(R) − c_H(R)| ≥ 2}"),
    # El 5 es A1(HR), que también está en el Anexo B (GHR_A1_HR): usar U.f("GHR_A1_HR"); ver el informe de C1.
    ConstanteTexto("GHR_A1_TS_Y_EE", (1, 5, 3), "§4.7", "con A1(Ts) ≥ 1 °C, A1(HR) ≥ 5 puntos y A1/EE ≥ 3 en ambas"),
    ConstanteTexto("GVIENTO_DIST", 2, "§4.7", "su ĉw cumple |ĉw − c_H(R)| ≥ 2"),
    ConstanteTexto("GVER_MIN_VERSIONES", 2, "§4.7", "con meses de ≥ 2 versiones admitidas, con ≥ 2 meses cada una",
                   ajenos=(2,)),        # GVER_MESES del Anexo B
    ConstanteTexto("E6_VENTANA", (-9, 9), "§4.6", "Para c ∈ [−9, 9] y para las C(Z) de P"),
    ConstanteTexto("E6_TOL_FM12_C", 0.05, "§4.6", "I12_c es la fracción de FM-12 con |Ts − TMP| ≤ 0,05 °C;",
                   ajenos=(12,)),       # el 12 de «FM-12»
    ConstanteTexto("E6_FM15_DIST", 2, "§4.6", "sirve sólo para separar a H de las H′ con |c_H′ − c_H| ≥ 2"),
    ConstanteTexto("E6_PALABRAS", ("AEROPUERTO", "AERODROMO", "AD", "AP", "ESTACION", "INTL", "INTERNACIONAL"), "§4.6",
                   "sin las palabras AEROPUERTO, AERODROMO, AD, AP, ESTACION, INTL e INTERNACIONAL"),
    ConstanteTexto("APOYO_MINIMOS", (2, 2), "§5.1", "Se exigen ≥ 2 líneas de apoyo, de ≥ 2 familias, y al menos una Q."),
    ConstanteTexto("INESTABLE_RELOJES", 3, "§5.3", "tiene ≥ 3 relojes distintos o vuelve a uno anterior (H1 → H2 → H1)"),
    ConstanteTexto("A3_ENVOLVER", (-6, 6), "§5.4", "Los tres valores se envuelven a [−6, 6)."),
    ConstanteTexto("A5_LAT_MAX", 50, "§5.4",
                   "**Muestra:** los años-régimen con |lat| ≤ 50°, E3p filtrada evaluable, ≥ 1.000 pares y ĉ^f_cont definido.",
                   ajenos=(1000,)),     # E3_PARES_REGIMEN del Anexo B
    ConstanteTexto("A5_ENVOLVER", (-0.5, 0.5), "§5.4", "llevada a horas en [−0,5; 0,5)"),
    ConstanteTexto("EXPEDIENTES_CONTROL_N", 20, "§5.5", "una muestra al azar de 20 estaciones con algún año confirmado"),
    # Repeticiones de umbrales de otras secciones en frases que reescribió la Enmienda 3 (fila de §5.5, E3-2 R;
    # §6 y §8.16, E3-4). Ningún módulo las lee: rigen ANUAL_MIN_PARTES (§4.0), E3T_DIA_MIN_VALORES (§4.3.3) y
    # E4_DIA_MIN_VALORES (§4.4), y test_umbrales comprueba que coinciden.
    ConstanteTexto("DISCREPANCIAS_PARTES", 2, "§5.5", "Con ≥ 2 partes, el año queda discrepante", desde="v1.0.3"),
    ConstanteTexto("DIURNOS_DIA_MIN_VALORES", 20, "§6",
                   "Con menos de 20 valores por día, E3t, T-P, E4t y G-HR quedan sin información", desde="v1.0.3"),
    ConstanteTexto("C16_DIA_MIN_VALORES", 20, "§8", "Un aeródromo UTC con días de ≥ 20 valores, sin E4p, queda insuficiente",
                   desde="v1.0.3"),
    ConstanteTexto("DESFASES_PERMITIDOS", (0, -180, -240, -300, -360), "§7.2",
                   "Sólo se usa `fixed_offset_minutes` ∈ {0, −180, −240, −300, −360}"),
    ConstanteTexto("SEMILLA_FORMATO", "{semilla}|{codigo}|{anio}|{unidad}|{variable}", "§4.0",
                   "\"20261022|<código>|<año>|<unidad>|<variable>\"", ajenos=(20261022,)),   # SEMILLA del Anexo B
    ConstanteTexto("SEMILLA_BYTES", 8, "§4.0", "digest()[:8], \"big\")"),
    ConstanteTexto("C3A_MESES", ("2015-01", "2024-12"), "§8.E", "en los meses 2015-01 a 2024-12"),
    ConstanteTexto("C3A_LAT_MAX", 50, "§8.E", "**Datos:** los píxeles válidos con |lat| ≤ 50°"),
    ConstanteTexto("C3A_K", 3, "§8.E", "(con K = 3)"),
    ConstanteTexto("C3A_A2_EE", 3, "§8.E", "sobre los píxeles con A2/EE ≥ 3"),
    ConstanteTexto("C3A_MIN_PIXELES_MACRO", 30, "§8.E", "en cada macrozona con ≥ 30 píxeles"),
    ConstanteTexto("C3B_LAT_CORTE", 50, "§8.E", "24 con |lat| ≤ 50°", ajenos=(24,)),   # C3B_PIX_NORTE del Anexo B
    ConstanteTexto("C3B_ANIOS", (2008, 2026), "§8.E", "para 2008-2026 y sin RR06"),
    ConstanteTexto("C3C_N_PIXELES", 30, "§8.E", "**Muestra:** 30 píxeles válidos costeros"),
    ConstanteTexto("BATERIA_ANIOS", (2008, 2026), "§8.D", "cubren 2008-2026"),
    ConstanteTexto("BATERIA_S2", (1.16, 9.75, 20), "§8.D",
                   "S2 = 1,16·cos³(lat) hPa, con máximo a las 9,75 h solares y modulación semestral de ±20 %"),
    ConstanteTexto("BATERIA_REPLICAS_D1", 20, "§8.D", "**Bloque D1, núcleo** (20 réplicas por celda)."),
    ConstanteTexto("BATERIA_REPLICAS_D2", 10, "§8.D", "**Bloque D2, perturbaciones** (10 réplicas)."),
    ConstanteTexto("BATERIA_REPLICAS_D3", 10, "§8.D", "(FM-12 y FM-15) y 10 réplicas", ajenos=(12, 15)),
    ConstanteTexto("BATERIA_REPLICAS_REDUCIDAS", 5, "§8.D", "se reducen a 5 las réplicas de D2 y D3"),
)

POR_NOMBRE = {c.nombre: c for c in CONSTANTES}


def valor(nombre: str) -> Any:
    """Valor de una constante del texto; KeyError si no existe."""
    return POR_NOMBRE[nombre].valor


# ---------------------------------------------------------------------------------------------
# Lectura de números y secciones del texto

_NUMERO_FRAGMENTO = re.compile(r"(?<![\w.,])(?:([−+])\s?)?(\d+(?:\.\d{3})*(?:,\d+)?)(?!\w)")
_SECCION = re.compile(r"§(\d+)(?:\.(\d+|[A-Z]))?(?:\.(\d+))?")
_NIVEL_1 = re.compile(r"## ")
_NIVEL_2 = re.compile(r"\*\*(?:\d+\.\d+|[A-Z]\.) ")
_NIVEL_3 = re.compile(r"\*\d+\.\d+\.\d+ ")


def numeros_del_fragmento(texto: str) -> list[int | float]:
    """Números de un fragmento del protocolo, en orden (ver el docstring del módulo)."""
    salida: list[int | float] = []
    for m in _NUMERO_FRAGMENTO.finditer(texto):
        cuerpo = m.group(2).replace(".", "")
        numero: int | float = float(cuerpo.replace(",", ".")) if "," in cuerpo else int(cuerpo)
        salida.append(-numero if m.group(1) == "−" else numero)
    return salida


def numeros_del_valor(v: Any) -> Iterator[int | float]:
    """Números de un valor, en profundidad; en los textos, sus grupos de cifras."""
    if isinstance(v, bool):
        raise TypeError("una constante del texto no es booleana")
    if isinstance(v, (int, float)):
        yield v
    elif isinstance(v, str):
        for cifras in re.findall(r"\d+", v):
            yield int(cifras)
    elif isinstance(v, (tuple, list)):
        for x in v:
            yield from numeros_del_valor(x)
    else:
        raise TypeError(f"tipo no admitido en una constante del texto: {type(v).__name__}")


def _textos_sin_cifras(v: Any) -> Iterator[str]:
    if isinstance(v, str):
        if not re.search(r"[\d{}]", v):
            yield v
    elif isinstance(v, (tuple, list)):
        for x in v:
            yield from _textos_sin_cifras(x)


def _nivel(linea: str) -> int | None:
    if _NIVEL_1.match(linea):
        return 1
    if _NIVEL_2.match(linea):
        return 2
    if _NIVEL_3.match(linea):
        return 3
    return None


def tramo_de_seccion(texto: str, seccion: str) -> str | None:
    """Texto de una sección («§3.3», «§4.3.4», «§8.D»): desde su encabezado hasta el siguiente del
    mismo nivel o superior. None si la sección no existe o su rótulo no se entiende."""
    m = _SECCION.fullmatch(seccion)
    if m is None:
        return None
    n, sub, subsub = m.groups()
    if sub is None:
        nivel, inicio = 1, f"## {n}. "
    elif sub.isalpha():                       # §8.D: «**D. …**» dentro de «## 8.»
        if subsub is not None:
            return None
        texto = tramo_de_seccion(texto, f"§{n}")
        if texto is None:
            return None
        nivel, inicio = 2, f"**{sub}. "
    elif subsub is None:
        nivel, inicio = 2, f"**{n}.{sub} "
    else:
        nivel, inicio = 3, f"*{n}.{sub}.{subsub} "
    lineas = texto.splitlines(keepends=True)
    comienzos = [i for i, l in enumerate(lineas) if l.startswith(inicio)]
    if len(comienzos) != 1:
        return None
    a = comienzos[0]
    b = next((j for j in range(a + 1, len(lineas)) if (_nivel(lineas[j]) or 99) <= nivel), len(lineas))
    return "".join(lineas[a:b])


def verificar_contra_texto(texto_protocolo: str, version: str = VERSION_VIGENTE) -> list[str]:
    """Lista de problemas: fragmentos ausentes del texto o números del fragmento que no calzan.
    ``version`` es la del texto que se pasa (por omisión, la vigente): cada constante se busca con su
    fragmento en esa versión, y las que todavía no estaban (``desde`` posterior) no se buscan."""
    indice_version(version)          # ValueError si la versión no es una de VERSIONES_TEXTO
    problemas: list[str] = []
    nombres = [c.nombre for c in CONSTANTES]
    for nombre in sorted({n for n in nombres if nombres.count(n) > 1}):
        problemas.append(f"{nombre}: nombre repetido en CONSTANTES")
    for c in CONSTANTES:
        try:
            primera = indice_version(c.desde) == 0
            fragmento = c.fragmento_en(version)
        except ValueError as e:
            problemas.append(f"{c.nombre}: {e}")
            continue
        if primera and c.fragmento_anterior is not None:
            problemas.append(f"{c.nombre}: fragmento_anterior sin «desde» posterior a {VERSIONES_TEXTO[0]}")
        if fragmento is None:
            continue                 # la constante nace en una versión posterior a la del texto
        if fragmento not in texto_protocolo:
            problemas.append(f"{c.nombre}: el fragmento no está tal cual en el texto: {fragmento!r}")
            continue
        tramo = tramo_de_seccion(texto_protocolo, c.seccion)
        if tramo is None:
            problemas.append(f"{c.nombre}: no se halló la sección {c.seccion}")
        elif fragmento not in tramo:
            problemas.append(f"{c.nombre}: el fragmento está en el texto, pero no en {c.seccion}")
        try:
            del_valor = list(numeros_del_valor(c.valor))
        except TypeError as e:
            problemas.append(f"{c.nombre}: {e}")
            continue
        del_fragmento = numeros_del_fragmento(fragmento)
        usados, pos = [], 0
        for v in del_valor:
            while pos < len(del_fragmento) and del_fragmento[pos] != v:
                pos += 1
            if pos == len(del_fragmento):
                problemas.append(f"{c.nombre}: {v!r} del valor no está, en ese orden, entre los números del "
                                 f"fragmento {del_fragmento}")
                break
            usados.append(pos)
            pos += 1
        else:
            sobrantes = [x for i, x in enumerate(del_fragmento) if i not in usados]
            if sobrantes != list(c.ajenos):
                problemas.append(f"{c.nombre}: números del fragmento fuera del valor {sobrantes}; "
                                 f"declarados como ajenos {list(c.ajenos)}")
        for palabra in _textos_sin_cifras(c.valor):
            if palabra not in fragmento:
                problemas.append(f"{c.nombre}: {palabra!r} del valor no está en el fragmento")
    return problemas
