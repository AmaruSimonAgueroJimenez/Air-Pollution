"""Fijos del cuerpo y del Anexo B que no están en el Anexo A (anexo A2), y definiciones físicas y de formato.

§10 del texto: «todo umbral numérico del cuerpo o del Anexo B que no esté en el Anexo A es fijo, con el valor y el
alcance de su frase. M1 los lista en un anexo A2 generado del texto, cada uno con su fragmento literal».

Tres listas, todas con su sección y un fragmento literal del texto vigente (v2.5, Enmienda 4; CON-n abajo):
- ``CONSTANTES``: el anexo A2 (clase «umbral» u «operacion») y las definiciones físicas y de formato (clase
  «definicion»: Magnus, p_std, la hipsométrica, 287,05, 9,80665…). ``valor(nombre)`` las da.
- ``REPETICIONES``: frases del cuerpo que repiten un valor del Anexo A, o de una constante de esta lista
  (§4.4 del diseño: «la repetición de un valor del Anexo A en el cuerpo se acepta si el fragmento del cuerpo calza con
  el id del Anexo A»). ``repite`` nombra los ids o constantes; ``verificar_repeticiones`` compara con el Anexo A.
- ``NO_NORMATIVOS``: números que no son reglas (justificaciones, datos vistos en V, ejemplos, cifras de costo, conteos,
  citas, ceros definicionales…), cada uno con su motivo. ``MASCARAS``: categorías de números que no son números del
  texto (referencias a secciones, huellas, numeración de listas, nombres como «MC-09» o «UTC−4»…).

``verificar_contra_texto`` exige que cada fragmento esté tal cual en su sección y que sus números calcen con el valor;
``completitud`` falla si un número del cuerpo (§0 a §10) o del Anexo B queda sin constante, repetición ni exclusión, o si
una cifra que la regla no lee no está declarada; ``anexo_a2`` genera ``anexo_a2.json``.

Cómo se leen los números (``numeros_del_fragmento``): la regla de ``reloj_dmc.constantes`` (signo «−» o «+», también
con un espacio, miles con «.», decimales con «,»; el guion ASCII no es signo; no cuentan las cifras pegadas a una
letra: «A1», «t2m», «Q95», «2π»), más la notación científica de este texto («2,25577·10⁻⁵», «10⁻⁶» y «1e-9») y las
fracciones «½», «¼», «¾», «⅓» y «⅔». En esas dos cosas se aparta de la del reloj (``test_constantes`` lo declara).

Lecturas propias (CON-n), para el addendum de M1:
- CON-1. **Dónde rige el A2:** el cuerpo, §0 a §10, y el Anexo B (§10: «todo umbral numérico del cuerpo o del Anexo
  B»). Quedan fuera el encabezado (versiones y huellas), el Anexo A (la fuente de los umbrales con id) y las Referencias
  (años de publicación). §1 («Lo ya visto») son conteos y datos vistos: van a las exclusiones con su motivo, igual que
  la historia de §0 (líneas del tablero, horas de la sesión) y las fechas y números de línea de §10.
  **Normativo** es todo número del cuerpo y del Anexo B que fija cómo se calcula, se decide o se prueba algo,
  también los criterios de las pruebas de §9, los períodos y los años (2000-2025, 2015-2019, 2020), las definiciones
  que el código usa (alturas de 2 y 10 m, las 23, 24 o 25 horas del día civil, el paso 1/3.600° de NASADEM, los meses
  200001, 201307 y 202507, la resolución de 100 m y la versión R2023A de GHS-POP, las 343 comunas de los nudos) y las
  condiciones de operación (hilos en 1, hasta 8 procesos; factibilidad física del grupo). EMC4/D68 conserva carga < 2 sólo como referencia
  diagnóstica histórica, sin veto por carga al inicio ni durante el costo. **No normativo:** las justificaciones físicas
  de §2.3, los datos vistos en V, los ejemplos (la política de §2.5, el 990 de §2.1), los conteos de insumos (8.206
  píxeles, 838.430 celdas, 9.725 píxeles), el nombre nominal de la grilla («≈ 1 km», celdas de 0,01°), las citas
  (años de publicación), las fechas de historia (2026-…), las cifras de costo, memoria y disco (las tablas de §7.1, §8 y
  el Anexo B), las reglas de otros documentos citadas para eliminarlas (PEND-17), los ceros y unos definicionales
  (rapidez nula, dirección cero, Σk = 0, «1 −» de una fórmula) y las conversiones (/1000, 100·).
- CON-2. Un número que una fórmula resta («1 − 2,25577·10⁻⁵ · z», «exp(−9,80665 · …)», «(sp_i − 0,378·e_i)») se
  guarda en positivo y se declara en ``negativos``: la regla del reloj lo lee con signo. Así ``P_STD`` es
  (1.013,25; 2,25577·10⁻⁵; 5,25588) y ``numerico.p_std`` calcula 1.013,25·(1 − 2,25577·10⁻⁵·z)^5,25588.
- CON-3. **Ajenos.** Los números del fragmento que no son del valor van en ``ajenos``, en su orden; un ajeno cuenta
  como cubierto si repite un número del propio valor («12 + 12 meses», «< 500, 500-2.000 y > 2.000 m») y si no, otra
  entrada debe cubrirlo (``completitud`` lo exige).
- CON-4. Una exclusión sin ``numeros`` cubre todos los números de su fragmento (párrafos de costo, ejemplos, datos
  vistos); con ``numeros``, sólo esos (el «1» de «(1 − …)», el «0» de «0-10»).
- CON-5. **Máscaras** (``MASCARAS``): se aplican, sin cambiar las posiciones, al leer los números para la completitud
  y para verificar los fragmentos. No son exclusiones de reglas: son cifras que no son números del texto (referencias
  «§2.4», «marca 14», «bits 3-17», «paso 1 de»; huellas; números de línea; la numeración «1.» de una lista; nombres
  «MC-09», «BLQ-75», «M3-4», «UTC−4» y «F(−4)»; «HH:00»; los índices «y_{i−1}» e «y_{i+1}» de la regla de picos (no la
  ventana «{m−1, m, m+1}» de A, que es ``A_VENTANA_MESES`` y se repite); «<64>»; el número de bit de la tabla de §2.4,
  que fija ``tipos``; los encabezados; la numeración «0.2.3»; las fechas 2026-… y las de las carpetas de una ruta;
  «líneas 206-215» e «ítem 3»).
- CON-6. Los «bits 3-17» de Q1 (§2.7) son una referencia a las marcas (máscara), no una constante: los fija
  ``tipos.MARCAS_Q1`` y ``test_tipos`` los compara con el texto.
- CON-7. Un valor de texto («2000-01-01», «EPSG:32719», «Q95», «½·σ²») debe aparecer tal cual en el fragmento, y
  cubre las cifras que contiene.
- CON-8. ``PROCESOS`` (8, §8) repite la opción D2 de M0 (``opciones_m0``), que no es del Anexo A: va al A2 y una
  prueba la compara con el JSON de umbrales. Desde EMC3-1 es un tope, no ocho obligatorios en toda fase.
- CON-9. Las cotas de TF de §5.7 van por variable como (TF1 media, TF1 P95, TF2 media, TF2 P95); el texto las escribe
  iguales para TF1 y TF2. La red histórica de TF1 es (horas, desde, hasta) = (2.000, 2000, 2009); el 2.000 coincide con
  ``MIN_HORAS`` del Anexo A, pero la frase es otra regla (§4.4 del diseño la pone en el A2).
- CON-10. ``A_ARMONICOS_K`` = (1, 2, 3): los órdenes armónicos de §4.3, cuyos períodos 24/k son los del Anexo A
  (``A_P1_H``, ``A_P2_H``, ``A_P3_H``); una prueba lo comprueba.
- CON-11. **Lo que la regla no lee** (``pegados`` de cada entrada; ``anexo_a2.json`` los lista como «no_leidos»):
  - cifras pegadas a una letra: «3L» (el corte del núcleo, ``NUC_CORTE``, §4.2); «2πh», «4πh», «2π», «4π» (los órdenes
    1 y 2 de los armónicos de C, §4.6) y «2πk» (§4.3, k simbólico); «Q95» y «Q05» (§5.8) y «P95» (§5.7 y Anexo B), los
    cuantiles; «19S» (la zona UTM de P2, dentro de ``P2_CRS``); «01T00» y «31T23» (fechas del ejemplo de §2.5);
  - nombres con cifras que no son números: «R2023A» (la versión de GHS-POP, dentro de ``GHS_PRODUCTO``);
  - números escritos con palabras: «una vez más» (el segundo ajuste de A, §4.3), «en un año» (S14), «se verifica en un
    mes» y «Por lotes de un mes» (Anexo B).
  ``completitud`` busca en el cuerpo toda cifra pegada a una letra que la sigue (``3L``, ``2πh``, ``19S``) y todo
  cuantil «Q»/«P» de dos cifras, y exige que esté declarada en ``pegados`` de una entrada que la cubre, o dentro de un
  valor de texto. Los nombres como «R2023A» y los números en palabras no se pueden buscar así: la lista de arriba es a
  mano (las otras palabras del texto, como «los dos escenarios», «una sola vez» o «los dos sentidos», cuentan la
  estructura de una regla que ya está escrita y no fijan una cantidad).
- CON-12. Los ½ de los pesos ambientales («π = ½ π^mon + ½ π^pob», §5.3) son literales en el Anexo A (Anexo P: «½»),
  sin id: van al A2 como ``PI_AMBIENTAL`` y una prueba comprueba que la fila «Pesos» del Anexo A trae los mismos ½.
- CON-13. Un literal pegado declara su posición en el valor (``pegados`` = ((literal, posición), …)) o ``None`` si no es
  un número del valor («2πk»). La verificación lo busca en el fragmento, en orden, y comprueba su lectura a mano: las
  cifras del literal («3L» → 3, «Q05» → 5), la mitad de las que van con π («4πh» → 2) y 1 para «un», «una».
- CON-14. Ninguna máscara oculta un número que lleva una unidad: ``completitud`` falla si una cifra enmascarada va
  seguida de h, K, hPa, m, km, mm, %, °, días, meses, años u horas (así «la marca 14 y 9 h» no esconde el 9).
- CON-15. **El v2.3 (EMC2-1, 2026-10-27).** La repetición de K4 del v2.2 («hay un quiebre de T2a a ≤ 3 meses, con
  |Δz_a − Δz_b| ≤ máx(10 m; 0,3·|Δz_b|)») ya no está en el texto. La reemplazan cuatro: ``K4_T2A_M`` y ``K4_COINC_M`` con
  ``K4_COINC_FRAC`` en la viñeta del traslado, y ``K4_COINC_MESES`` y ``K4_T2B_HPA`` en la regla de T2a. Con ellas,
  ``verificar_contra_texto`` y ``completitud`` dan 0 problemas con el v2.3. Las repeticiones de §2.5 que siguen se
  renumeran (``REP_2.5_n`` sale del orden de la lista).
- CON-16. **EMC3 (D65).** PROCESOS conserva el valor ocho y pasa a citar «hasta 8 procesos» en §8. Se repite en la
  proyección conservada del recorte (EMC3-2). EMC5/D69 conserva MEMORIA_MAX_GB sólo como referencia histórica,
  sin exclusión individual; la factibilidad sigue por memoria física. No cambian criterios meteorológicos.
Depende de: nada del paquete (biblioteca estándar); no importa numpy ni pandas.
"""
from __future__ import annotations

import bisect
import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterator, Mapping

ESQUEMA_ANEXO_A2 = "meteo-combinada-anexo-a2/2"
CLASES = ("umbral", "definicion", "operacion")
# Secciones donde rige el A2 (§10: «del cuerpo o del Anexo B»; CON-1): §0 a §10 y el Anexo B.
SECCIONES_NORMATIVAS = tuple(f"§{n}" for n in range(0, 11)) + ("Anexo B",)


@dataclass(frozen=True)
class ConstanteTexto:
    nombre: str
    valor: Any
    seccion: str
    fragmento: str            # tal cual en el texto vigente
    ajenos: tuple = ()        # números del fragmento que no son de esta constante, en su orden (CON-3)
    clase: str = "umbral"     # umbral, definicion u operacion (CONSTANTES); repeticion (REPETICIONES)
    repite: tuple = ()        # ids del Anexo A o constantes («MAGNUS_AGUA[1]») que la frase repite
    negativos: tuple = ()     # posiciones del valor que el fragmento escribe con «−» (CON-2)
    pegados: tuple = ()       # ((literal, posición en el valor o None), …) que la regla no lee (CON-11, CON-13)


@dataclass(frozen=True)
class NoNormativo:
    seccion: str
    fragmento: str
    motivo: str
    numeros: tuple | None = None     # None: todos los números del fragmento (CON-4)
    pegados: tuple = ()              # literales que la regla no lee, en orden (CON-11)


def _c(nombre, valor, seccion, fragmento, ajenos=(), *, clase="umbral", negativos=(), pegados=()):
    return ConstanteTexto(nombre, valor, seccion, fragmento, tuple(ajenos), clase, (), tuple(negativos), tuple(pegados))


def _d(nombre, valor, seccion, fragmento, ajenos=(), *, negativos=(), pegados=()):
    return _c(nombre, valor, seccion, fragmento, ajenos, clase="definicion", negativos=negativos, pegados=pegados)


def _x(seccion, fragmento, motivo, numeros=None, pegados=()):
    return NoNormativo(seccion, fragmento, motivo, None if numeros is None else tuple(numeros), tuple(pegados))


# ---------------------------------------------------------------------------------------------
# Anexo A2 y definiciones

_Z_IMPL = "z_impl = 29,27 · T̄ · ln(QFF/QFE), con T̄ = Ts + 273,15 + 0,0065·z_cat/2 (K)"
_DZ_B = "Δz_b = −ΔQFE · 287,05 · T̄ / (9,80665 · p̄)"

CONSTANTES: tuple[ConstanteTexto, ...] = (
    # Definiciones físicas (ola 0, I0; nombres y valores fijos para numerico). §4.1 del diseño, punto 3.
    _d("MAGNUS_AGUA", (6.112, 17.625, 243.04), "§2.4", "e_s(T) = 6,112·exp(17,625·T/(243,04 + T))"),
    _d("MAGNUS_HIELO", (6.112, 22.46, 272.62), "§2.4", "e_i(T) = 6,112·exp(22,46·T/(272,62 + T))"),
    _d("P_STD", (1013.25, 2.25577e-05, 5.25588), "§2.3", "p_std(z) = 1.013,25 · (1 − 2,25577·10⁻⁵ · z)^5,25588",
       ajenos=(1,), negativos=(1,)),
    _d("HIPSOMETRICA", (44330.8, 1013.25, 0.190263), "§4.1", "z = 44.330,8 · [1 − (sp̄/1.013,25)^0,190263]",
       ajenos=(1,)),
    _d("R_SECO", 287.05, "§2.5", _DZ_B, ajenos=(9.80665,)),
    _d("GRAVEDAD", 9.80665, "§2.5", _DZ_B, ajenos=(287.05,)),
    _d("Q_ESPECIFICA", (0.622, 0.378), "§4.1", "e′_i = q_i·p′_i/(0,622 + 0,378·q_i)"),
    _d("Z_IMPLICITA", (29.27, 273.15, 0.0065), "§2.5", _Z_IMPL, ajenos=(2,)),
    _d("KELVIN", 273.15, "§2.5", _Z_IMPL, ajenos=(29.27, 0.0065, 2)),
    _d("Z_IMPLICITA_DIVISOR", 2, "§2.5", "0,0065·z_cat/2 (K)", ajenos=(0.0065,)),    # T̄ a la altitud media
    _d("NUDO_MS", (1852, 3600), "§2.3", "el adaptador convierte nudos con 1.852/3.600"),
    _d("R_TIERRA_KM", 6371, "§4.2", "con d_h por haversine (R = 6.371 km)"),
    _d("MAGNUS_EL_FEATURES", (17.67, 243.5), "§2.4", "Es distinto del de `_features.py` (17,67 y 243,5)"),
    # §2.2 Reglas measurements.
    _c("MED_INTERVALO_TS_TD_HR", 0, "§2.2", "| Ts, Td, `relative_humidity` | instantaneous | 0 | producto |"),
    _c("MED_INTERVALO_VIENTO", 0, "§2.2",
       "| `wind_speed_instant`, `wind_direction_instant` | instantaneous | 0 | producto (u, v) |"),
    _c("MED_INTERVALO_QFE", 0, "§2.2", "| QFE | instantaneous | 0 | producto (presión) |"),
    _c("MED_INTERVALO_QFF", 0, "§2.2", "| QFF | instantaneous | 0 | sólo para K4 |"),
    _c("MED_INTERVALO_RR06", 360, "§2.2", "| RR06 | sum | 360 | sólo validación de la lluvia"),
    # §2.4 Envoltorio.
    _c("SECO_MIN_REPORTES", 3, "§2.4", "cubren ≥ 6 h (≥ 3 reportes)", ajenos=(6,)),
    _c("EG_DESVIO_DIVISOR", 2, "§2.4", "con |r − med| > U/2 del mismo signo"),
    # §2.5 Coordenadas.
    _c("K1_DECIMALES", (0.5, 10), "§2.5", "con d decimales, 0,5·10⁻ᵈ grados"),
    _c("K1_SEGUNDOS", 0.5, "§2.5", "con segundos, 0,5″"),
    _c("K1_MINUTOS", 0.5, "§2.5", "sólo minutos, 0,5′"),
    _c("K1_RAIZ_DE", 2, "§2.5", "se multiplica por √2"),      # el factor es √(K1_RAIZ_DE) = √2
    # §2.6 RR06.
    _c("RR06_HORAS", 6, "§2.6", "contra la suma de las 6 horas ERA5-Land que terminan en la"),
    _c("RR06_LLUVIA_MM", 1, "§2.6", "frecuencia de períodos con ≥ 1 mm"),
    # §3 Variables y resoluciones.
    _d("ALTURA_T_M", 2, "§3", "Temperatura a 2 m (T, °C)"),
    _d("ALTURA_VIENTO_M", 10, "§3", "viento a 10 m (u y v, m/s)"),
    _c("HR_PRODUCTO_RECORTE", (0, 100), "§3", "HR por Magnus sobre agua, recortada en [0, 100]"),
    _c("PRODUCTO_DESDE", "2000-01-01", "§3", "del 2000-01-01 a su último dato"),
    _d("DIA_CIVIL_HORAS", (23, 24, 25), "§3", "el día civil de America/Santiago con 23, 24 o 25 horas"),
    _d("PRODUCTO_01_GRADOS", 0.1, "§3", "**0,1°:** en los centros de los 8.206 píxeles", ajenos=(8206,)),
    _c("GHS_ANIO", 2020, "§3", "de 100 m de 2020 (las teselas que ya", ajenos=(100,)),
    _d("GHS_RESOLUCION_M", 100, "§3", "GHS-POP R2023A de 100 m de 2020", ajenos=(2020,)),
    _d("GHS_PRODUCTO", "GHS-POP R2023A", "§3", "la población GHS-POP R2023A de 100 m", ajenos=(100,)),
    _d("NASADEM_PASO_GRADOS", (1, 3600), "§3", "paso 1/3.600°"),
    # §4.1 Fondo.
    _c("ZE5L_SP_PERIODO", (2000, 2025), "§4.1", "con sp̄ la media 2000-2025 de sp del píxel"),
    _c("ZE5L_DIF_INFORME_M", 50, "§4.1", "|z_NASADEM − z_hipsométrica| > 50 m"),
    _d("FONDO_VECINOS", 4, "§4.1", "Los 4 centros ERA5-Land que lo rodean"),
    _c("PIXEL_MESES_VALIDEZ", (200001, 201307, 202507), "§4.1", "en cada uno de los meses 200001, 201307 y 202507"),
    _c("E5L_T_K", (200, 330), "§4.1", "mediana de t2m y d2m en [200, 330] K"),
    _c("E5L_SP_PA", (40000, 110000), "§4.1", "de sp en [40.000, 110.000] Pa"),
    _c("E5L_UV_MS", 30, "§4.1", "|mediana| de u10 y v10 < 30 m/s"),
    # §4.2 Núcleo.
    _d("NUCLEO_MEDIO", 0.5, "§4.2", "k(x,s) = exp(−½ (d_ef/L)²)", negativos=(0,)),
    # §4.3 A.
    _c("A_ARMONICOS_K", (1, 2, 3), "§4.3", "con k = 1, 2, y además k = 3 si hay ≥ 12 horas UTC", ajenos=(12,)),
    _c("A_SEGUNDO_AJUSTE", 1, "§4.3", "una vez más. r̄_s(m, h) es el valor ajustado", pegados=(("una vez más", 0),)),
    # §4.6 C.
    _d("C_LOG_DISTANCIA", 1, "§4.6", "log(1 + distancia a la costa en km)"),
    _c("TPI_RADIOS_KM", (1, 5), "§4.6", "TPI a 1 y a 5 km"),
    _d("C_PERIODOS", ((1, 24), (2, 24), (1, 365.25), (2, 365.25)), "§4.6",      # (orden, período)
       "seno y coseno de 2πh/24 y de 4πh/24 (h = hora UTC), y de 2π·doy/365,25 y de 4π·doy/365,25",
       pegados=(("2πh", 0), ("4πh", 2), ("2π", 4), ("4π", 6))),
    _d("C_INTERACCIONES", (4, 2), "§4.6", "cada estático por los 4 armónicos horarios y los 2 anuales de primer orden"),
    # §4.7 C_est.
    _c("C_EST_PERIODO", (2000, 2025), "§4.7", "climatologías por píxel, mes y hora UTC de 2000-2025"),
    # §4.9 Selección anidada.
    _c("DIAS_EPOCA", "2000-01-01", "§4.9", "(días desde el 2000-01-01)"),
    # §5.1 Particiones.
    _c("P2_CRS", ("UTM 19S", "EPSG:32719"), "§5.1", "Rejilla de 75 km en UTM 19S (EPSG:32719)", ajenos=(75,)),
    _c("P2_ORIGEN_M", (0, 0), "§5.1", "con el origen (0, 0) de"),
    # §5.2 Métricas.
    _c("ANOMALIA_PERIODO", (2010, 2023), "§5.2", "2010-2023, con ≥ 5 años válidos", ajenos=(5,)),
    _c("CD_MIN_VALORES", 10, "§5.2", "Para cada mes del año y hora UTC con ≥ 10 valores"),
    # §5.3 Pesos.
    _c("PI_POB_PERIODO", (2000, 2025), "§5.3", "para cada año 2000-2025, la distancia"),
    _c("PI_AMBIENTAL", (0.5, 0.5), "§5.3", "Ambiental: π = ½ π^mon + ½ π^pob"),                     # CON-12
    _c("S_PAR_PESO", 0.5, "§5.3", "S_par,c = ½ (S_T,c / mín_c′ S_T,c′ + S_HR,c / mín_c′ S_HR,c′)"),
    # §5.4 Remuestreo.
    _c("BOOT_IC_PCT", 95, "§5.4", "su intervalo percentil del 95 %"),
    # §5.5 Estratos.
    _c("ESTRATO_ALTITUD_M", (500, 2000), "§5.5", "altitud < 500, 500-2.000 y > 2.000 m", ajenos=(500, 2000)),
    _c("ESTRATO_PERIODOS", (2000, 2009, 2010, 2026), "§5.5", "período 2000-2009 y 2010-2026"),
    # §5.6 SINCA.
    _c("SINCA_AVISO_PCT", 15, "§5.6", "es peor que el segundo en más de 15 % en esta red"),
    # §5.7 TF.
    _c("TF_PESOS_ANIO", 2020, "§5.7", "2020), resumido por comuna y año con medias ponderadas"),
    _c("TF1_RED_HISTORICA", (2000, 2000, 2009), "§5.7", "las estaciones con ≥ 2.000 horas válidas de v en 2000-2009"),
    _c("TF1_ESCENARIO_CAMBIO", (2015, 2019, 2020, 2024), "§5.7",
       "2015-2019 sólo con la red histórica y 2020-2024 con todas"),
    _c("TF1_ESCENARIO_COMPLETO", (2015, 2024), "§5.7", "todas las estaciones en 2015-2024"),
    _c("TF1_DELTA_C", "[media 2020-24 − media 2015-19]_cambio − [lo mismo]_completo", "§5.7",
       "Δ_c = [media 2020-24 − media 2015-19]_cambio − [lo mismo]_completo"),
    _c("TF2_RED_R2000_2025", (50, 22, 26, 2000, 2025), "§5.7",
       "con ≥ 50 % de horas válidas de v en ≥ 22 de los 26 años 2000-2025"),
    _c("TF2_RED_MIN_ESTACIONES", 10, "§5.7", "2000-2025. Con < 10", ajenos=(2000, 2025)),
    _c("TF2_RED_R2003_2025", (80, 2003, 2025), "§5.7", "en ≥ 80 % de los años 2003-2025"),
    _c("TF2_RED_R2010_2025", (80, 2010, 2025), "§5.7", "en ≥ 80 % de los años 2010-2025"),
    _c("DERIVA_K_DECADA", 0.3, "§5.7", "con una deriva del fondo de 0,3 K por década"),
    _c("DERIVA_ANIO", 2010, "§5.7", "aparecen en 2010, B y AB deben cumplir"),
    _c("TF_PERCENTIL", 95, "§5.7", "y su percentil 95"),
    _c("TF_COTAS_T", (0.05, 0.15, 0.05, 0.15), "§5.7", "| T | 0,05 / 0,15 K | 0,05 / 0,15 K |"),
    _c("TF_COTAS_TD", (0.1, 0.25, 0.1, 0.25), "§5.7", "| Td | 0,10 / 0,25 K | 0,10 / 0,25 K |"),
    _c("TF_COTAS_RAPIDEZ", (0.05, 0.15, 0.05, 0.15), "§5.7", "| rapidez | 0,05 / 0,15 m/s | 0,05 / 0,15 m/s |"),
    _c("TF_COTAS_P", (0.1, 0.3, 0.1, 0.3), "§5.7", "| p | 0,10 / 0,30 hPa | 0,10 / 0,30 hPa |"),
    _c("TF_CERO_TOL", 1e-06, "§5.7", "un valor > 10⁻⁶ es un error de código"),
    # §5.8 Extremos.
    _c("EX_CUANTILES_AMBIENTAL", (95, 5), "§5.8",
       "b_calor = Q95(Tmáx diaria del producto) − Q95(Tmáx observada) y b_frío = Q05(Tmín) − Q05(Tmín)",
       pegados=(("Q95", 0), ("Q95", 0), ("Q05", 1), ("Q05", 1))),
    _c("EX_CUANTIL_RAPIDEZ", 95, "§5.8", "En la rapidez, |sesgo del Q95 del", pegados=(("Q95", 0),)),
    _c("EX_CUANTILES_AGUDO", (5, 10, 90, 95), "§5.8", "la media de |sesgo| en los cuantiles 5, 10, 90 y 95"),
    _c("EX_CUANTILES_DESCRIPTIVOS", (95, 5), "§5.8",
       "el sesgo condicional en los días observados sobre el Q95 o bajo el Q05", pegados=(("Q95", 0), ("Q05", 1))),
    _c("EX_ACIERTO_CUANTIL", 95, "§5.8", "de días sobre el Q95 observado que el producto también pone sobre su propio Q95",
       pegados=(("Q95", 0), ("Q95", 0))),
    # §6.2 Decisión.
    _c("E0_FINITO_PCT", 99, "§6.2", "que dan valor finito en ≥ 99 % de los puntos con fondo"),
    # §7.2 Agudo (texto para la Enmienda 4).
    _c("AGUDO_NUDOS_PERIODO", (2000, 2023), "§7.2", "(percentiles nacionales 2000-2023, 343", ajenos=(343,)),
    _c("AGUDO_NUDOS_COMUNAS", 343, "§7.2", "2000-2023, 343", ajenos=(2000, 2023)),
    _c("REPRES_CORRELACION_MIN", 0.8, "§7.2", "sea < 0,8 o cuyo cociente"),
    _c("REPRES_COCIENTE", (0.5, 2), "§7.2", "quede fuera de [0,5; 2]"),
    # §8 Operación.
    _c("HILOS_ALGEBRA", 1, "§8", "`MKL_NUM_THREADS` = 1)", clase="operacion"),
    _c("COSTO_CARGA_MAX", 2, "§8", "referencia diagnóstica histórica: carga < 2", clase="definicion"),
    _c("PROCESOS", 8, "§8", "En M3-4 y M5 se usan hasta 8 procesos", clase="operacion"),
    _c("MEMORIA_MAX_GB", 8, "§8", "referencia histórica de memoria individual: 8 GB", clase="definicion"),
    # §9 Pruebas sintéticas (criterios).
    _c("S1_RACHA_HR100_NO_H", 20, "§9", "rachas (HR = 100 de 20 h no se marca,", ajenos=(100,)),
    _c("S1_RACHA_HR100_SI_H", 50, "§9", "de 50 h sí; Td con HR = 100 no se marca", ajenos=(100,)),
    _c("S2_PLANTILLA_MIN", -240, "§9", "−240 sin veredicto se rechaza"),
    _c("S4_TRASLADOS_M", (15, 5), "§9", "Un traslado de 15 m con QFE y QFF coherentes se declara traslado; uno de 5 m, no"),
    _c("S4_BAROMETRO_HPA", 1.5, "§9", "de 1,5 hPa da «inhomogeneidad del barómetro»"),
    _c("S4_ALTITUDES_M", (500, 1000, 2500), "§9", "en estaciones a 500, 1.000 y 2.500 m"),
    _c("S4_FALSOS", (2, 200), "§9", "Falsos quiebres en ≤ 2 % de 200 series"),
    _c("S5_RMSE_A_K", 0.3, "§9", "A recupera b con RMSE < 0,3 K"),
    _c("S5_PASO_H", 3, "§9", "Con estaciones cada 3 h y aeródromos diurnos"),
    _c("S5_SALTO_A_K", 0.2, "§9", "mayores que 0,2 K"),
    _c("S5_SENSOR_K", 1, "§9", "Un cambio de sensor sintético de 1 K"),
    _c("S6_RED", (20, 2000, 2009, 120, 2010, 2024), "§9", "(20 estaciones en 2000-2009 y 120 en 2010-2024;"),
    _c("S6_SESGO_K", -1.5, "§9", "−1,5 K en los valles"),
    _c("S11_VIENTO", (270, 10, 5.144, 0, 360, 0), "§9", "DD 270 con 10 kt da u = +5,144 m/s y v ≈ 0; DD 360 da v < 0"),
    _c("S12_RELOJ", (-240, -180, 0, 1), "§9", "con reglas −240 y −180 dan residuo 0. Un error de ±1 h aparece en CD"),
    _c("S14_CORRECCION", 0, "§9", "Con corrección 0, z_x = z del píxel enlazado"),
    _c("S14_TOLERANCIA", 1e-09, "§9", "dentro de 1e-9, en un año"),
    _c("S14_ANIOS", 1, "§9", "dentro de 1e-9, en un año", ajenos=(1e-09,), pegados=(("en un año", 0),)),
    _c("S15_EXTREMOS", (470, 1085, -60, 50, 60), "§9", "(p de 470 y 1.085 hPa; T de −60 y 50 °C; u de ±60 m/s)"),
    # Anexo B.
    _d("M6_FE_COLUMNAS", 9, "Anexo B", "(9 columnas análogas a `mc_*`)"),
    _c("M6_SIGMA2", "½·σ²", "Anexo B", "la decisión se repite con la corrección ½·σ²"),
    _c("M6_CONDICIONES", 7, "Anexo B", "la variante que cumple las 7 condiciones"),
    _c("M6_TF_VERIFICACION_MESES", 1, "Anexo B", "es 0 por construcción y se verifica en un mes", ajenos=(0,),
       pegados=(("en un mes", 0),)),
    _c("M6_TF_LOTE_MESES", 1, "Anexo B", "Por lotes de un mes con la fábrica de producción", clase="operacion",
       pegados=(("de un mes", 0),)),
    # §10 Erratas.
    _c("ERRATA_MUESTRA", (20, 20), "§10",
       "una muestra al azar de 20 estaciones con alguna marca invalidante y 20 sin ella"),
)


# ---------------------------------------------------------------------------------------------
# Repeticiones del Anexo A (y de constantes de arriba) en el cuerpo

_REPETICIONES_ESPEC = (
    # (repite, valor, sección, fragmento[, ajenos[, negativos[, pegados]]])
    (("SOPORTE_PCT",), (50,), "§0.4", "carece de soporte (Σk = 0) en más del 50 % de sus horas de prueba", (0,)),
    (("QDD_MIN", "QDD_MAX"), (0, 360), "§2.1", "una dirección fuera de [0, 360]"),
    (("QDD_MIN", "QDD_MAX"), (0, 360), "§2.1", "Las reglas se escriben con `int` 0 y 360"),
    (("QTS_MIN", "QTS_MAX"), (-39.0, 50.0), "§2.3", "| Ts | degC | −39,0 | 50,0 |"),
    (("CENT_TS",), (-40.0,), "§2.3", "−40,0 es centinela"),
    (("QTS_MIN",), (-39,), "§2.3", "no hay registros cercanos a −39"),
    (("QTS_MAX",), (50,), "§2.3", "50 está sobre cualquier máximo registrado en Chile"),
    (("QTD_MIN", "QTD_MAX"), (-50.0, 35.0), "§2.3", "| Td | degC | −50,0 | 35,0 |"),
    (("QHR_MIN", "QHR_MAX"), (1.0, 103.0), "§2.3", "| `relative_humidity` | % | 1,0 | 103,0 |"),
    (("HR_RECORTE_MAX", "HR_SAT"), (103, 100), "§2.3", "hasta 103 % por saturación del sensor, que se recorta a 100"),
    (("QFF_MIN", "QFF_MAX"), (0.0, 50.0), "§2.3", "| m/s | 0,0 | 50,0 |"),
    (("QDD_MIN", "QDD_MAX"), (0, 360), "§2.3", "| `wind_direction_instant` | degree | 0 | 360 |"),
    (("QQFE_BAJO", "QQFE_ALTO"), (-80, 50), "§2.3", "| QFE | hPa | p_std(z_s) − 80 | p_std(z_s) + 50 |"),
    (("QQFF_MIN", "QQFF_MAX"), (920.0, 1065.0), "§2.3", "| QFF | hPa | 920,0 | 1.065,0 |"),
    (("CONSECUTIVO_H",), (3,), "§2.4", "Dos reportes son consecutivos si distan ≤ 3 h"),
    (("RACHA_MIN_REPORTES",), (4,), "§2.4", "con ≥ 4 reportes. Se invalida la racha entera"),
    (("PICO_TS", "PICO_TD"), (8, 10), "§2.4", "θ: Ts 8 K, Td 10 K"),
    (("PICO_P", "PICO_FF"), (4, 15), "§2.4", "QFF 4 hPa, rapidez 15 m/s"),
    (("F_1H", "DT_1H", "F_23H", "DT_23_DESDE", "DT_23_HASTA"), (1, 1, 1.5, 2, 3), "§2.4",
     "f = 1 con Δt = 1 h y 1,5 con Δt de 2-3 h"),
    (("SALTO_MULT",), (2,), "§2.4", "mayor que 2·θ·f"),
    (("CENT_TS", "CENT_QFE", "CENT_TOL"), (-40.0, 500.0, 0.05), "§2.4", "Ts = −40,0 o QFE = 500,0 (\\|x − c\\| < 0,05)"),
    (("RACHA_H", "HR_SAT", "RACHA_H", "HR_SAT", "RACHA_LARGA_H", "RACHA_H", "RACHA_H", "HR_SAT", "RACHA_H"),
     (12, 100, 12, 100, 48, 12, 12, 100, 12), "§2.4",
     "Ts, QFE y QFF idénticos ≥ 12 h; HR < 100 idéntica ≥ 12 h; HR = 100 ≥ 48 h (exenta de la de 12 h); Td idéntico "
     "≥ 12 h, sin contar las horas con HR = 100; viento con rapidez > 0 y la misma dirección y rapidez ≥ 12 h", (0,)),
    (("TD_TS_INV",), (0.5,), "§2.4", "td_mayor_ts | Td − Ts > 0,5 K"),
    (("TD_TS_INV",), (0.5,), "§2.4", "0 < Td − Ts ≤ 0,5 K → `td_final` = Ts", (0,)),
    (("INCOH_TD", "INCOH_HR", "CERO_C"), (2.0, 5, 0), "§2.4",
     "> 2,0 K **y** \\|HR − HR_M(Td, Ts)\\| > 5 puntos. Bajo 0 °C"),
    (("RACHA_LARGA_H",), (48,), "§2.4", "rapidez = 0 en una racha ≥ 48 h", (0,)),
    (("EG_LARGO_H",), (24,), "§2.4", "desvío aislado o desvío de más de 24 h"),
    (("ALT_QFE_HPA",), (8,), "§2.4", "\\|mediana(QFE − p_F)\\| > 8 hPa en el tramo"),
    (("HR_SAT", "HR_RECORTE_MAX", "HR_SAT"), (100, 103, 100), "§2.4", "100 < HR ≤ 103 → `hr_final` = 100"),
    (("SECO_HR_PCT", "SECO_H"), (2, 6), "§2.4", "HR < 2 % en reportes consecutivos que cubren ≥ 6 h"),
    (("EG_CORTO_H", "EG_LARGO_H"), (3, 24), "§2.4", "desvío de 3 a 24 h"),
    (("CERO_NORTE_PCT",), (1,), "§2.4",
     "si entre las horas con rapidez > 0 nunca aparece 360 y el 0 aparece en ≥ 1 % de", (0, 360, 0)),
    (("EG_MULT", "EG_MAD_K", "EG_T", "EG_TD", "EG_P"), (6, 1.4826, 8, 10, 6), "§2.4",
     "U = máx(θ_g; 6 · 1,4826 · MAD_s(m,h)), con θ_g: T 8 K, Td 10 K y p 6 hPa"),
    (("EG_MIN_N", "EG_MIN_N"), (30, 30), "§2.4", "(s, m, h) tiene < 30 valores, se usa (s, m). Si (s, m) también tiene < 30"),
    (("EG_CORTO_H",), (3,), "§2.4", "Dura < 3 h (incluye el reporte suelto)"),
    (("EG_CORTO_H", "EG_LARGO_H"), (3, 24), "§2.4", "Dura de 3 a 24 h"),
    (("EG_LARGO_H",), (24,), "§2.4", "Dura más de 24 h: se invalida la sucesión entera"),
    (("RHO_MIN_KM", "RHO_MAX_KM"), (0.1, 2), "§2.5", "ρ = mín(máx(ρ; 0,1 km); 2 km)"),
    (("K3_DZ_M",), (50,), "§2.5", "con |z_DEM − z_cat| ≤ 50 m"),
    (("K4_MIN_MES_HORA",), (5,), "§2.5", "en las horas válidas, si hay ≥ 5"),
    (("K4_HORAS_PCT", "K4_VENTANA", "K4_VENTANA"), (80, 12, 12), "§2.5",
     "con mediana en ≥ 80 % de los meses válidos de cada lado (12 antes y 12"),
    (("K4_MIN_PARES",), (100,), "§2.5", "Un mes es válido con ≥ 100 pares"),
    (("K4_VENTANA", "K4_VENTANA", "K4_MIN_LADO"), (12, 12, 6), "§2.5",
     "mediana de M en los 12 meses posteriores menos la de los 12 anteriores, con ≥ 6 meses válidos por lado"),
    (("K4_T2A_M", "K4_T2B_HPA", "K4_MAX_QUIEBRES"), (10, 1.2, 3), "§2.5",
     "≥ 10 m (T2a) o ≥ 1,2 hPa (T2b), en el k del máximo. Varios: segmentación binaria, hasta 3 por"),
    (("K4_TRAMO_MIN",), (12,), "§2.5", "con tramos de ≥ 12 meses"),
    # EMC2-1 (v2.3): el traslado, con el D(k) de T2a en el mes del quiebre de T2b, y la regla de T2a («Sin T2b»).
    # Reemplazan a la repetición del v2.2 («hay un quiebre de T2a a ≤ 3 meses, con |Δz_a − Δz_b| ≤ …»).
    (("K4_T2A_M",), (10,), "§2.5", "cumple |D(k)| ≥ 10 m"),
    (("K4_COINC_M", "K4_COINC_FRAC"), (10, 0.3), "§2.5", "|Δz_a − Δz_b| ≤ máx(10 m; 0,3·|Δz_b|)"),
    (("K4_COINC_MESES",), (3,), "§2.5", "hay un quiebre de T2b a ≤ 3 meses"),
    (("K4_T2B_HPA",), (1.2,), "§2.5", "|D(k)| < 1,2 hPa"),
    (("GRUPO_KM",), (2,), "§2.5", "Las estaciones a ≤ 2 km (componentes conexas)"),
    (("RR_MIN", "RR_MAX"), (0, 200), "§2.6", "válido en [0, 200] mm"),
    (("Q1_PCT",), (10,), "§2.7", "quita más del 10 % de las horas de la red"),
    (("CENT_TS", "CENT_QFE"), (-40.0, 500.0), "§2.7", "Los centinelas Ts = −40,0 y QFE = 500,0"),
    (("Q1Z_PCT",), (25,), "§2.7", "con más del 25 % de las horas de una macrozona"),
    (("Q2_PCT", "Q2_DESDE", "Q2_HASTA", "Q2Z_PCT"), (5, 2000, 2009, 20), "§2.7",
     "más del 5 % de las horas de una variable en 2000-2009, o más del 20 %"),
    (("Q3_PCT",), (1,), "§2.7", "más del 1 % de los artefactos evaluados"),
    (("LISTA_PCT",), (30,), "§2.7", "las estaciones con más del 30 % de horas marcadas"),
    (("GRAVEDAD",), (9.80665,), "§4.1", "dividido por 9,80665"),
    (("ZE5L_NASADEM_PCT",), (95,), "§4.1", "cuando ≥ 95 % de la celda tiene dato"),
    (("GAMMA_K_KM",), (-6.5,), "§4.1", "Γ = −6,5 K/km"),
    (("Q_ESPECIFICA",), (0.622, 0.378), "§4.1", "q_i = 0,622·e_i/(sp_i − 0,378·e_i)", (), (1,)),
    (("VECINO_KM",), (16,), "§4.1", "el centro válido más cercano a ≤ 16 km"),
    (("VECINO_KM",), (16,), "§4.1", "Un solo radio, 16 km,"),
    (("GRAVEDAD", "R_SECO"), (9.80665, 287.05), "§4.1", "p′_i = sp_i · exp(−9,80665 · (z_x − z_i)/(287,05 · T̄_i))",
     (), (0,)),
    (("NUC_CORTE", "NUC_VECINOS"), (3, 30), "§4.2",
     "si d_ef ≤ 3L y s está entre las 30 estaciones de entrenamiento más cercanas", (), (), (("3L", 0),)),
    (("NUC_L", "NUC_LAMBDA", "NUC_KAPPA"), (10, 25, 50, 100, 200, 0, 50, 150, 0.05, 0.2, 0.5, 1.0), "§4.2",
     "L ∈ {10, 25, 50, 100, 200} km; λ ∈ {0, 50, 150}; κ ∈ {0,05; 0,2; 0,5; 1,0}"),
    (("A_VENTANA_MESES", "A_VENTANA_MESES"), (1, 1), "§4.3", "sobre los residuos de los meses {m−1, m, m+1} de"),
    (("A_P1_H", "A_P1_H"), (24, 24), "§4.3", "cos(2πk·h/24) + β_k sen(2πk·h/24)", (), (),
     (("2πk", None), ("2πk", None))),
    (("A_HORAS_K3",), (12,), "§4.3", "k = 3 si hay ≥ 12 horas UTC", (3,)),
    (("A_RECORTE_PCT",), (10,), "§4.3", "se quita el 10 % de cada cola"),
    (("A_MIN_N", "A_MIN_ANIOS", "A_HUECO_H"), (60, 2, 4), "§4.3",
     "≥ 60 valores de ≥ 2 años distintos, y horas observadas con un hueco circular ≤ 4 h"),
    (("B_INTERP_H",), (3,), "§4.4", "reportes válidos consecutivos (≤ 3 h) a ambos lados"),
    (("C_TPI_PCT",), (50,), "§4.6", "si el disco tiene < 50 % con"),
    (("C_ANIO_LULC",), (2015,), "§4.6", "**del año 2015 en todos los años**"),
    (("C_ALFAS",), (0.1, 1, 10, 100, 1000), "§4.6", "α ∈ {0,1; 1; 10; 100; 1.000}"),
    (("C_FILAS", "SEMILLA", "C_FILAS", "C_PESO_MAX"), (4000, 20261023, 4000, 10), "§4.6",
     "hasta 4.000 horas válidas por estación, al azar (semilla 20261023), con peso mín(4.000/n_s; 10)"),
    (("K4_VENTANA", "K4_VENTANA", "K4_MIN_LADO"), (12, 12, 6), "§4.8", "D(k) con 12 + 12 meses y ≥ 6 válidos por lado"),
    (("K4_MAX_QUIEBRES", "K4_TRAMO_MIN"), (3, 12), "§4.8", "segmentación binaria hasta 3 quiebres y tramos de ≥ 12 meses"),
    (("HOM_T", "HOM_TD"), (0.5, 1.0), "§4.8", "0,5 K en T y 1,0 K en Td"),
    (("GRUPO_KM",), (2,), "§4.9", "su grupo a ≤ 2 km y su amortiguador quedan fuera"),
    (("SEL_PLIEGUES", "SEL_BLOQUE_KM", "SEMILLA"), (5, 75, 20261023), "§4.9",
     "5 pliegues internos de bloques de 75 km asignados al azar (semilla 20261023)"),
    (("SEL_AMORT_KM",), (25,), "§4.9", "el mismo amortiguador de 25 km"),
    (("SEL_AMORT_KM",), (25,), "§4.9", "las estaciones a ≤ 25 km de las de prueba interna"),
    (("SEL_MOD", "SEL_RESTO"), (11, 3), "§4.9", "mód 11 = 3, que rotan el día de la semana"),
    (("SEL_UMBRAL_H", "SEL_MOD_RECORTE", "SEL_RESTO"), (36, 23, 3), "§4.9",
     "en más de 36 h, el addendum de M1 fija mód 23 = 3"),
    (("GRUPO_KM", "P1_PLIEGUES"), (2, 10), "§5.1", "Los grupos a ≤ 2 km se reparten al azar en 10 pliegues"),
    (("SEMILLA",), (20261023,), "§5.1", "(semilla 20261023)."),
    (("P2_BLOQUE_KM",), (75,), "§5.1", "Rejilla de 75 km en UTM 19S"),
    (("P2_AMORT_KM",), (25,), "§5.1", "las estaciones a ≤ 25 km de cualquier estación de prueba"),
    (("MIN_HORAS",), (2000,), "§5.2", "≥ 2.000 horas válidas de la variable en su pliegue de prueba"),
    (("DIA_MIN_H", "DIA_HUECO_H"), (8, 4), "§5.2", "≥ 8 horas válidas y un hueco circular máximo ≤ 4 h"),
    (("AGUDO_MIN_DIAS",), (10,), "§5.2", "(≥ 10 días válidos en el estrato)"),
    (("ANIO_MIN_DIAS", "MIN_ANIOS"), (300, 3), "§5.2", "año válido con ≥ 300 días válidos; evaluable con ≥ 3 años válidos"),
    (("MIN_ANIOS_ANOM",), (5,), "§5.2", "2010-2023, con ≥ 5 años válidos", (2010, 2023)),
    (("MIN_HORAS",), (2000,), "§5.3", "estación de entrenamiento más cercana con ≥ 2.000"),
    (("BANDAS_KM[0]", "BANDAS_KM[0]", "BANDAS_KM[1]", "BANDAS_KM[1]", "BANDAS_KM[2]", "BANDAS_KM[2]"),
     (10, 10, 25, 25, 50, 50), "§5.3", "en 0-10, 10-25, 25-50 y > 50 km", (0,)),
    (("MIN_HORAS",), (2000,), "§5.3", "cercana con ≥ 2.000 horas válidas de la variable ese año"),
    (("BANDA_MIN_EVAL",), (10,), "§5.3", "Una banda con < 10 evaluaciones se une"),
    (("BANDAS_KM[0]", "BANDAS_KM[0]", "BANDAS_KM[1]"), (10, 10, 25), "§5.3",
     "más cercana a 0 (la de 0-10 km, con la de 10-25)", (0, 0)),
    (("BOOT_REPLICAS", "SEMILLA"), (1999, 20261023), "§5.4", "1.999 réplicas, semilla 20261023"),
    (("BOOT_BLOQUE_KM",), (75,), "§5.4", "75 km de P2 y toma todas las evaluaciones"),
    (("ALTURA_T_M",), (2,), "§5.5", "la T y HR a 2 m"),
    (("SOPORTE_PCT",), (50,), "§5.5", "carece de soporte en más del 50 %"),
    (("TF_PERCENTIL", "TF_PERCENTIL"), (95, 95), "§5.7", "| Variable | TF1: media / P95 | TF2: media / P95 (por década) |",
     (), (), (("P95", 0), ("P95", 1))),
    (("TF_PERCENTIL",), (95,), "§5.7", "la media y el P95 ponderados", (), (), (("P95", 0),)),
    (("TF2_RED_MIN_ESTACIONES",), (10,), "§5.7", "Con < 10 todavía"),
    (("TF2_RED_MIN_ESTACIONES",), (10,), "§5.7", "Si ninguna alcanza 10, TF2 no es evaluable"),
    (("EX_MIN_DIAS",), (900,), "§5.8", "estaciones con ≥ 900 días válidos"),
    (("CD_MULT", "CD_T", "CD_HR", "CD_P"), (1.1, 0.05, 0.5, 0.05), "§6.1",
     "CD_c ≤ 1,10 · mín CD + 0,05 K (T) o m/s (rapidez), + 0,5 puntos (HR) o + 0,05 hPa (p)"),
    (("EX_T", "EX_TD", "EX_HR", "EX_FF"), (0.25, 0.4, 2.0, 0.3), "§6.1",
     "EX_c ≤ mín EX + 0,25 K (T), 0,40 K (Td), 2,0 puntos (HR) o 0,30 m/s (rapidez)"),
    (("MZ_MIN_EST",), (10,), "§6.1", "en cada macrozona con ≥ 10 estaciones evaluables"),
    (("MZ_MULT",), (1.15,), "§6.1", "S_c,z ≤ 1,15 · mín S_c′,z"),
    (("NIVEL_MULT",), (1.15,), "§6.1", "RMSE de las medias diarias ≤ 1,15 · mín"),
    (("NIVEL_MULT",), (1.15,), "§6.1", "**Anomalía interanual (crónico):** RMSE ≤ 1,15 · mín"),
    (("MAGNUS_AGUA[1]", "MAGNUS_AGUA[2]"), (17.625, 243.04), "§7.1", "`mc_rh` usa Magnus 17,625 y 243,04"),
    (("MAGNUS_EL_FEATURES",), (17.67, 243.5), "§7.1", "`el_rh` (17,67 y 243,5)"),
    (("FMT_RELLENO", "FMT_ESC_T"), (-32768, 0.01), "§8", "en int16 con relleno −32768: T y Td con escala 0,01 °C"),
    (("FMT_ESC_UV", "FMT_ESC_P", "FMT_DESP_P"), (0.01, 0.02, 800), "§8",
     "u y v con 0,01 m/s; p con escala 0,02 hPa y desplazamiento 800 hPa"),
    (("SEL_MOD_RECORTE",), (23,), "§8", "(mód 23), fijado en el addendum de M1"),
    (("PROCESOS",), (8,), "§8", "la proyección con 8 procesos"),
    (("COSTO_CARGA_MAX",), (2,), "§8.1", "histórico «carga < 2». No hay marcas temporales individuales por muestra"),
    (("COSTO_CARGA_MAX",), (2,), "§8.1", "`CARGA_MAX = 2` queda sólo como referencia diagnóstica histórica"),
    (("COSTO_CARGA_MAX",), (2,), "§8.1", "El fragmento «con la máquina libre, carga < 2» puede citarse como antecedente"),
    (("SEL_UMBRAL_H",), (36,), "§8.1", "recorte de 36 h de §4.9"),
    (("PROCESOS",), (8,), "§8.1", "la proyección adicional con 8 procesos"),
    (("HR_SAT",), (100,), "§9", "rachas (HR = 100 de"),
    (("HR_SAT",), (100,), "§9", "Td con HR = 100 no se marca"),
    (("CERO_C",), (0,), "§9", "bajo 0 °C sobre hielo"),
    (("EG_CORTO_H", "EG_LARGO_H", "EG_LARGO_H"), (3, 24, 24), "§9", "persistente (3-24 h) y largo (> 24 h)"),
    (("GRUPO_KM",), (2,), "§9", "su grupo a ≤ 2 km y su amortiguador de P2"),
    (("DERIVA_K_DECADA", "DERIVA_ANIO"), (0.3, 2010), "§9",
     "con una deriva del fondo de 0,3 K por década y estaciones que aparecen en 2010"),
    (("TF2_RED_MIN_ESTACIONES",), (10,), "§9", "una red constante con menos de 10 estaciones en las tres reglas"),
    (("DIA_CIVIL_HORAS[0]", "DIA_CIVIL_HORAS[2]"), (23, 25), "§9", "Días de 23 y 25 h"),
    (("M6_N", "M6_REPLICAS"), (750000, 3), "Anexo B", "N = 750.000 y las 3 réplicas"),
    (("M6_IC_PCT",), (95,), "Anexo B", "tiene un IC percentil del 95 %"),
    (("M6_B",), (1999,), "Anexo B", "B = 1.999 réplicas"),
    (("M6_REPLICAS",), (3,), "Anexo B", "con las 3 réplicas comunes"),
    (("M6_NMB_PP",), (1,), "Anexo B", "|NMB_LightGBM| + 1 punto porcentual"),
    (("M6_CELDAS_COMUNA",), (50,), "Anexo B", "hasta 50 celdas por comuna"),
    (("SEMILLA", "SEL_MOD", "SEL_RESTO", "M6_TF_MEDIA_PCT"), (20261023, 11, 3, 1), "Anexo B",
     "(semilla 20261023), y los días con mód 11 = 3. Cotas: media ponderada de |Δ_c| ≤ 1 %"),
    (("TF_PERCENTIL", "M6_TF_P95_PCT", "M6_TF_DESDE", "M6_TF_HASTA"), (95, 3, 2015, 2024), "Anexo B",
     "P95 ≤ 3 % de la media nacional ponderada 2015-2024", (), (), (("P95", 0),)),
    (("SEMILLA",), (20261023,), "§10", "y 20 sin ella (semilla 20261023)", (20,)),
)


def _repeticiones() -> tuple[ConstanteTexto, ...]:
    salida, contador = [], {}
    for espec in _REPETICIONES_ESPEC:
        repite, valor, seccion, fragmento, *resto = espec
        ajenos = tuple(resto[0]) if resto else ()
        negativos = tuple(resto[1]) if len(resto) > 1 else ()
        pegados = tuple(resto[2]) if len(resto) > 2 else ()
        clave = seccion.replace("§", "").replace("Anexo ", "")
        contador[clave] = contador.get(clave, 0) + 1
        salida.append(ConstanteTexto(f"REP_{clave}_{contador[clave]:02d}", tuple(valor), seccion, fragmento, ajenos,
                                     "repeticion", tuple(repite), negativos, pegados))
    return tuple(salida)


REPETICIONES: tuple[ConstanteTexto, ...] = _repeticiones()


# ---------------------------------------------------------------------------------------------
# Números que no son reglas

_DEF = "cero o uno definicional (rapidez nula, dirección cero, Σk = 0, artefacto 0 por construcción…), no un umbral"
_JUST = "justificación física del rango (§2.3); el valor normativo es el de la columna, del Anexo A"
_VISTO = "dato visto en V (§1.10), no una regla"
_COSTO = "cifra de costo, memoria o disco (tablas y pasajes de costo de §7.1, §8 y el Anexo B)"
_CONTEO = "conteo de un insumo (descripción, no regla)"
_GRILLA = "nombre nominal de la grilla (≈ 1 km: las celdas de 0,01° de celdas.parquet), no una regla"
_RESOLUCION = "resolución de un insumo dado (NASADEM de 30 m), descripción, no regla"
_HISTORIA = "historia del protocolo (líneas del tablero, horas de la sesión, documentos citados), no una regla"
_VISTO_1 = "conteo o dato ya visto que declara §1 (lo ya visto), no una regla"
_EJEMPLO = "ejemplo o explicación, no una regla"

NO_NORMATIVOS: tuple[NoNormativo, ...] = (
    _x("§2.1", "ejemplo 990)", "ejemplo de un artefacto que aborta (dominio del adaptador)"),
    _x("§2.2", "la media de los 10 minutos previos", "convención OMM citada para declarar la diferencia"),
    _x("§2.3", "el máximo visto, 49,1, queda dentro", _VISTO),
    _x("§2.3", "Td = −50 °C equivale a HR ≈ 1 % a 0 °C y ≈ 0,3 % a 20 °C", _JUST),
    _x("§2.3", "35 °C es del orden del máximo mundial", _JUST),
    _x("§2.3", "el 40,9 visto queda fuera; parte de los 485 Td < −40 de Visviri queda dentro", _VISTO),
    _x("§2.3", "0 % no ocurre en superficie", _JUST),
    _x("§2.3", "50 m/s ≈ 97 kt", _JUST),
    _x("§2.3", "el máximo visto, 70 kt ≈ 36 m/s, queda dentro", _VISTO),
    _x("§2.3", "Excluye el centinela 500,0 bajo ≈ 4.465 m",
       "consecuencia del rango de QFE (altitud derivada de p_std); el centinela es el del Anexo A"),
    _x("§2.3", "Los ciclones más profundos cerca de Chile rondan 940-950 hPa", _JUST),
    _x("§2.3", "el 830,8 visto queda fuera; los < 950 vistos, en parte dentro", _VISTO),
    _x("§2.3", "· (1 − 2,25577·10⁻⁵", "el 1 de la fórmula de p_std", numeros=(1,)),
    _x("§2.4", "viento con rapidez > 0 y la misma dirección", _DEF, numeros=(0,)),
    _x("§2.4", "td_recortado | 0 <", _DEF, numeros=(0,)),
    _x("§2.4", "dirección = 0 y rapidez > 0, salvo en un estación-año", _DEF),
    _x("§2.4", "calma_persistente | rapidez = 0", _DEF, numeros=(0,)),
    _x("§2.4", "estación-año que lee el 0 como norte", _DEF),
    _x("§2.4", "rapidez = 0 válida y dirección vacía → `u_final` = `v_final` = 0", _DEF),
    _x("§2.4", "HR = 100·e(Td)/e_s(T)", "100: porcentaje (definición de la HR)"),
    _x("§2.4", "si entre las horas con rapidez > 0 nunca aparece 360 y el 0 aparece en", _DEF + "; el 360 y el 0 de la "
       "regla del cero son literales en el Anexo A (Anexo P)", numeros=(0, 360, 0)),
    _x("§2.4", "el 0 se lee como norte (marca 19; u y v del adaptador, que ya lo trata como 0°). Si aparece 360, rige "
       "la regla", _DEF),
    _x("§2.4", "SYNOP: el 0 con rapidez > 0 se invalida", _DEF),
    _x("§2.4", "rapidez 0 da u = v = 0 con cualquier dirección. Si la dirección falta y la rapidez 0 es válida", _DEF),
    _x("§2.4", "deriva u = v = 0", _DEF),
    _x("§2.5", "(un aeródromo diurno que pasa a 24 h, una serie cada 3 h que pasa a horaria)", _EJEMPLO),
    _x("§2.5", "pesa 1/(miembros disponibles a esa hora)", "definición del peso 1/n", numeros=(1,)),
    _x("§2.5", "\"valid_from\": \"2010-01-01T00:00:00\", \"valid_to\": \"2014-12-31T23:00:00\",",
       "ejemplo ilustrativo de política (§2.5: «ilustrativo»)", pegados=("01T00", "31T23")),
    _x("§2.5", "\"latitude\": -33.4, \"longitude\": -70.6", "ejemplo ilustrativo de política"),
    _x("§2.5", "\"interval_minutes\": 0}, \"RR06\": {\"…\": \"sum, 360\"}}", "ejemplo ilustrativo de política"),
    _x("§2.5", "\"minimum\": -39.0, \"maximum\": 50.0", "ejemplo ilustrativo de política"),
    _x("§2.6", "«s/p» = 0 mm (auditoría del 2026-10-12)",
       "lectura de «s/p», literal en el Anexo A (Anexo P: «s/p = 0»), y fecha de la auditoría"),
    _x("§2.6", "el 379,7 visto", _VISTO),
    _x("§2.7", "bajo ≈ 4.465 m quedan fuera", "consecuencia del rango de QFE (altitud derivada de p_std)"),
    _x("§3", "(hoy 2026-09-15 23:00 UTC)", "último dato de ERA5-Land al redactar (descripción)"),
    _x("§3", "8.206 píxeles ERA5-Land válidos", _CONTEO),
    _x("§3", "**≈ 1 km:** en las 838.430 celdas de 0,01°", _GRILLA + "; y el conteo de sus celdas"),
    _x("§4.1", "9.725 píxeles del catálogo", _CONTEO),
    _x("§4.1", "[1 − (sp̄/", "el 1 de la fórmula hipsométrica", numeros=(1,)),
    _x("§4.1", "Dutra et al. (2020)", "año de una cita"),
    _x("§4.1", "Equivale a ≈ −1,8 K/km", "consecuencia de conservar q (descripción)"),
    _x("§4.1", "(RELOJ usa 15 km sólo para elegir su píxel)", "regla de otro protocolo, citada"),
    _x("§4.1", "(z_x − z_i)/1000]", "conversión de m a km", numeros=(1000,)),
    _x("§4.1", "un error sinóptico de 2 hPa a nivel del mar es ≈ 1,3 hPa a 3.500 m", _EJEMPLO),
    _x("§4.2", "|z_x − z_s|/1000", "conversión de m a km", numeros=(1000,)),
    _x("§4.2", "Si no, 0. La lista de vecinos", _DEF),
    _x("§4.2", "Tiende a 0 cuando", _DEF),
    _x("§4.2", "(sin soporte vale 0)", _DEF),
    _x("§4.2", "si Σk = 0 sobre sus estaciones", _DEF),
    _x("§4.2", ": 60 combinaciones", "producto de las tres listas (5 × 3 × 4)"),
    _x("§4.3", "lo que haría oscilar A con período de 3 h", _EJEMPLO),
    _x("§4.5", "Las anomalías tienen media 0 por tramo", _EJEMPLO),
    _x("§4.6", "su celda de ≈ 1 km", _GRILLA),
    _x("§4.6", "TPI = 0 tras estandarizar", "el 0 de la regla del TPI, literal en el Anexo A (Anexo P)"),
    _x("§4.6", "pendientes de 30 m de la celda", _RESOLUCION),
    _x("§4.6", "las 7 fracciones de cobertura del suelo", "número de columnas de estaticas_lulc.parquet (las fija tipos.LULC)"),
    _x("§4.6", "(1 + β) veces la del fondo", _EJEMPLO),
    _x("§4.6", "(Meyer y Pebesma, 2021)", "año de una cita"),
    _x("§4.7", "artefacto de tendencia 0 por construcción", _DEF),
    _x("§4.8", "Sin quiebres, δ = 0.", _DEF),
    _x("§4.9", "(mód 7 caería siempre en martes)", _EJEMPLO),
    _x("§5.3", "en 0-10,", "el 0 es el origen de las distancias", numeros=(0,)),
    _x("§5.3", "cada celda con w_ghs > 0", _DEF),
    _x("§5.3", "al., 2022)", "año de una cita"),
    _x("§5.3", "más cercana a 0 (la de 0-", "el 0 es el origen de las distancias"),
    _x("§5.7", "(w_ghs > 0, pesos fijos de", _DEF),
    _x("§5.7", "(artefacto 0 por construcción)", _DEF),
    _x("§5.7", "**A, C y C_est** dan artefacto 0 por construcción", _DEF),
    _x("§5.8", "EX_e = (|b_calor| + |b_frío|)/2", "promedio de los dos sesgos (definición)", numeros=(2,)),
    _x("§7.1", "en la celda de ≈ 1 km del monitor", _GRILLA),
    _x("§7.1", "(≈ 200 MB)", _COSTO),
    _x("§7.1", "**Costo.** Tablas laterales: ≈ 15,5 millones de monitor-horas × 9 columnas en I y × 14 en D, ≤ 1 h cada "
       "una.", _COSTO),
    _x("§7.1", "meteorológicas en la grilla: ≈ 2,0·10¹¹ celda-horas por variable (838.430 × 234.120) × 5 variables",
       _COSTO),
    _x("§7.2", "en las celdas de ≈ 1 km con `cod_comuna > 0`,", _GRILLA + "; y un cero definicional"),
    _x("§7.2", "w_ghs > 0 y producto finito", _DEF),
    _x("§7.2", "(estación a ≤ 20 km con ≥ 80 % de horas)", "regla eliminada (PEND-17), citada"),
    _x("§7.2", "(desfase de máxima correlación 0 h en el 90 % de los meses)", "regla eliminada (punto 12), citada"),
    _x("§7.2", "El cómputo crece ≈ 13 veces (108.579 celdas con población frente a ≈ 8.200 píxeles): de ≈ 3 min a ≈ 1 h.",
       _COSTO),
    _x("§8", "(≈ 3 GB)", _COSTO),
    _x("§8", "(≈ 0,5 GB)", _COSTO),
    _x("§8", "los 8.206 píxeles válidos", _CONTEO),
    _x("§8", "(cubre 145-1.455 hPa; con escala 0,01 y sin", "consecuencia del formato (descripción)"),
    _x("§8", "≈ 19,2 GB", _COSTO),
    _x("§8", "| M1: medición a escala con datos sintéticos | ≈ 2-4 h | local |", _COSTO),
    _x("§8", "| M2a: K1, K3, estáticos NASADEM y altitud poblada | 0,5-1 h | ≈ 0,6 GB NASADEM y las teselas GHS-POP |",
       _COSTO),
    _x("§8", "| 0,5-1 h | ≈ 19 GB leídos |", _COSTO),
    _x("§8", "(≈ 2,45 ms por hora de dato × 52,2 M horas) | ≈ 35 h de CPU: ≈ 4,5 h con 8 procesos [M0, D2] | ≈ 5 GB de "
       "artefactos |", _COSTO),
    _x("§8", "| M3-4: envoltorio, K4, tramos homogéneos y marcas | ≈ 1-2 h | local |", _COSTO),
    _x("§8", "sin medir; cota 12-24 h con 8 procesos", _COSTO),
    _x("§8", "| M5: 0,1°, salud (civil, UTC−4, regional, representatividad y crónico) y monitores; la S6, después de M6 "
       "[M0] | 8-12 h | ≈ 23 GB leídos, ≈ 25 GB escritos |", _COSTO),
    _x("§8", "| Agudo: lector por celda | ≈ 1 h | local |", _COSTO),
    _x("§8", "| 8-20 h, más la TF por lotes de un mes | ≈ 60 GB si se armara de una vez |", _COSTO),
    _x("§8", "**≈ 48-100 h de máquina", _COSTO),
    _x("§8", "≈ 2,0·10¹¹ celda-horas por variable × 5", _COSTO),
    _x("§8", "Los ≈ 340 MB del control de calidad son una referencia", _COSTO),
    _x("§8", "Quedan ≈ 469 GiB libres en el disco interno; el producto y el control de calidad ocupan ≈ 22 GB", _COSTO),
    _x("§8", "TROPOMI planean ≈ 276 GB", _COSTO),
    _x("§9", "horario diurno a 24 h", "el régimen de 24 h del caso de prueba (definición)"),
    _x("§9", "núcleo decae a 0 sin NaN", _DEF),
    _x("§9", "A, C y C_est dan exactamente 0", _DEF),
    _x("§9", "dan residuo 0 con el mismo viento", _DEF),
    _x("§9", "en 0 por construcción", _DEF),
    _x("§9", "distinta de 0 con un artefacto sembrado", _DEF),
    _x("Anexo B", "Holm sobre los 4 candidatos que excluye 0 a favor de c",
       "cita de la Enmienda 1 ambiental: sus 4 candidatos (aquí Holm no ajusta) y el 0 de un ΔR² nulo"),
    _x("Anexo B", "(con A o C es 0 por construcción", _DEF),
    _x("Anexo B", "los candidatos de E0 con artefacto 0 por construcción", _DEF),
    _x("Anexo B", "8-20 h de LightGBM, las tablas laterales de D (≈ 15,5 M filas × 14 columnas)", _COSTO),
    _x("Anexo B", "(≈ 17.000 celdas × ≈ 12.500 h ≈ 2,2·10⁸ filas con ≈ 70 predictores, por 2 escenarios, 2 variantes, 3 "
       "réplicas y 2", _COSTO),
    _x("Anexo B", "contaminantes, ≈ 60 GB en float32 si se armara de una vez", _COSTO),
    # §0: historia y nombres (CON-1).
    _x("§0.1", "en la grilla de ≈ 1 km (AP, contrato v2, por enmienda)", _GRILLA),
    _x("§0.1", "del Paper 1 v3", "nombre de un artículo"),
    _x("§0.2", "líneas 206-215):", _HISTORIA),
    _x("§0.2", "cerca de las 08:00**", _HISTORIA),
    _x("§0.2", "la pregunta se hizo a las 07:49 y la respuesta llegó a las", _HISTORIA),
    _x("§0.2", "07:51 (hora de Chile continental, 10:49 y 10:51 UTC del 2026-10-23)", _HISTORIA),
    _x("§0.2", "meteorología a ≈ 1 km y como predictor", _GRILLA),
    _x("§0.3", "la corrida ambiental de ~115 h antes del producto", _HISTORIA),
    _x("§0.4", "carece de soporte (Σk = 0)", _DEF, numeros=(0,)),
    # §1: lo ya visto (CON-1).
    _x("§1", "579 estaciones, 87.190 estación-meses y 52,2 millones de horas; horas válidas Ts 80 %, HR 82 %,", _VISTO_1),
    _x("§1", "viento ≈ 57 %, QFE 66 %, QFF 49 % y QNH 0 %; mucho más dato desde 2010 y 2000-2009 ralo;", _VISTO_1),
    _x("§1", "97.680 manifiestos; 87.188 artefactos verificados y 2 rechazos; 11.797 completos, 75.391", _VISTO_1),
    _x("§1", "parciales, 10.490 sin artefacto y 2 con verificación fallida;", _VISTO_1),
    _x("§1", "51 estaciones con datos de 1.043 del catálogo y ≈ 4,3 millones de filas.", _VISTO_1),
    _x("§1", "conjunto V: 51 estaciones del norte y", _VISTO_1),
    _x("§1", "la cabecera de la 407.", _HISTORIA),
    _x("§1", "con 829.405 casos; centinelas Ts −40,0, QFE 500,0, QFF < 950, RR06 > 100; Td > Ts + 0,5 en Azapa 2 y Td < −40 "
       "en Visviri", _VISTO_1),
    _x("§1", "2024; rangos; coordenadas sólo del catálogo vigente; semántica de la hora rotulada; las 20 correcciones de "
       "completitud).", _VISTO_1),
    _x("§1", "la 305 recomienda «consistencia con ERA5-Land»", _HISTORIA),
    _x("§1", "la 14 dice que QNH se exige", _HISTORIA),
    _x("§1", "concentra el 59,7 % de la ganancia en PM2,5»; R² diario LRO 0,119 en NO2 y 0,444 con la MLP", _VISTO_1),
    _x("§1", "con +0,017 y +0,025, y −0,015 a −0,034; las costuras de MERRA-2 de 1,5× y 4,3×.", _VISTO_1),
    _x("§1", "(corrección que decae a 0, QFF sin QNH, centinelas, memoria de ~20 GB", _VISTO_1),
    _x("§1", "VIII, 2024, visto después del sellado v2.", _VISTO_1),
    _x("§1", "ninguna de sus 48 lecturas (40 por la terminal y 8 de archivos)", _VISTO_1),
    _x("§1", "los nombres de los 321 meses", _VISTO_1),
    _x("§1", "máscara de NASADEM (48,7 % de píxeles con dato; crudo borrado), 108.579 celdas con w_ghs > 0 en 345 comunas, "
       "7.557", _VISTO_1),
    _x("§1", "celdas sin enlace a ERA5-Land (772 con población, 20.301 habitantes en 2020), 1.332 celdas enlazadas a 15-16 "
       "km, 321", _VISTO_1),
    _x("§1", "archivos ERA5-Land (23,36 GB), paneles v1 de 9.740.634 y 5.711.491 filas", _VISTO_1),
    _x("§1", "comparó z/9,80665 con la", _VISTO_1),
    _x("§1", "La diferencia típica fue de 64 m sin desplazamiento, y de 108 a 133 m", _VISTO_1),
    _x("§1", "de ERA5-Land de 2024-01 y 2024-07", _VISTO_1),
    _x("§1", "(4.593 y 3.071 horas-píxel, con un exceso de hasta 0,0036 K)", _VISTO_1),
)

# Unidades que no pueden seguir a una cifra enmascarada (CON-14).
_UNIDADES = r"(?:hPa|km|mm|m/s|°C|kt|días|meses|años|horas|h|K|m|%|°)(?![\w/])"
_SIN_UNIDAD = r"(?!\s?" + _UNIDADES + r")"

# (nombre, patrón, motivo): cifras que no son números del texto (CON-5).
MASCARAS: tuple[tuple[str, str, str], ...] = (
    ("seccion", r"§\s?\d+(?:\.\d+)*(?:\.[A-Z])?", "referencia a una sección"),
    ("huella", r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,64}\b", "huella o commit"),
    ("linea_de_codigo", r"`:\d+(?:-\d+)?", "número de línea de un archivo de código"),
    ("linea", r"\b(?:l\.|líneas?)\s\d+(?:-\d+)?(?:(?:,\s|\sy\s)\d+(?:-\d+)?)*", "número de línea de un documento"),
    ("referencia", r"(?i:\b(?:puntos?|pasos|marcas?|bits?|enmiendas?|complemento|ramas?|condición|condiciones|"
     r"comprobación|precondición|sensibilidad|etapa|ítems?))\s+\d+(?:(?:-|\s?y\s|,\s|\sa\s)\d+(?!\d)" + _SIN_UNIDAD + r")*",
     "número de un punto, paso, marca, bit, rama, condición, enmienda, etapa o ítem (referencia); la lista no sigue "
     "por un número con unidad (CON-14)"),
    ("paso", r"\bpaso\s+\d+(?![/\d])", "número de un paso (referencia)"),
    ("lista", r"(?m)^\s*(?:-\s)?\d+\.(?=\s)", "numeración de una lista"),
    ("nombre", r"\b[A-Z][A-Za-z0-9]*-\d+\b", "parte de un nombre («MC-09», «EMC1-1», «BLQ-75», «M3-4», «PEND-17»)"),
    ("zona", r"UTC[−+]\d+", "nombre de un día o zona («UTC−4»)"),
    ("hipotesis", r"F\([−+]?\d+\)", "nombre de una hipótesis de reloj («F(−4)»)"),
    ("hora", r"HH:00", "formato de hora"),
    ("indice", r"(?<=\{i)[−+]1(?=\})", "índice de la serie en la regla de picos («y_{i−1}», «y_{i+1}»); la ventana "
     "{m−1, m, m+1} de A no es índice: es A_VENTANA_MESES"),
    ("ruta_fecha", r"(?<=/)\d{8}(?=/)", "fecha en el nombre de una carpeta de una ruta"),
    ("longitud_huella", r"<64>", "longitud de una huella en un texto de plantilla"),
    ("bit", r"(?m)^\| \d+ \|", "número de bit en la tabla de §2.4 (lo fija tipos)"),
    ("encabezado", r"(?m)^#{2,3} \d+(?:\.\d+)?\.? ", "número de un encabezado"),
    ("numeracion", r"(?<![\d.])\d{1,2}\.\d{1,2}\.\d{1,2}(?![\d.])", "numeración de otro documento («0.2.3»)"),
    ("fecha", r"\b2026-\d{2}-\d{2}\b", "fecha de la historia del protocolo y de las decisiones"),
)

POR_NOMBRE = {c.nombre: c for c in CONSTANTES}


def valor(nombre: str) -> Any:
    """Valor de una constante del texto; KeyError si no existe."""
    return POR_NOMBRE[nombre].valor


# ---------------------------------------------------------------------------------------------
# Lectura de números

_SUPER = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")
FRACCIONES = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3}
_NUMERO = re.compile(r"(?<![\w.,])(?:([−+])\s?)?(?:(\d+(?:\.\d{3})*(?:,\d+)?)"
                     r"(?:(·10)?([⁻⁺]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+)|[eE]([−+-]?\d+))?|([½¼¾⅓⅔]))(?!\w)")
# Cifras que la regla no lee (CON-11): pegadas a una letra que las sigue («3L», «2πh», «19S») y cuantiles «Q95», «P95».
_NO_LEIDO = re.compile(r"(?<![\w.,])\d+(?:,\d+)?[A-Za-zθπ][\w]*|\b[QP]\d{2}\b")
_PALABRAS_UNO = ("un", "una")


def _numeros_con_posicion(texto: str) -> list[tuple[int, int, int | float]]:
    """(inicio, fin, número) en orden, con la regla del módulo (signo, miles, decimales, notación científica y
    fracciones)."""
    salida = []
    for m in _NUMERO.finditer(texto):
        signo, cuerpo, por10, sup, exp_e, fraccion = m.groups()
        if fraccion is not None:
            numero_f = FRACCIONES[fraccion]
            salida.append((m.start(), m.end(), -numero_f if signo == "−" else numero_f))
            continue
        cuerpo = cuerpo.replace(".", "")
        decimal = cuerpo.replace(",", ".")
        if sup is not None:
            if por10 is None and cuerpo != "10":
                continue                      # una cifra con superíndice que no es una potencia de 10 (no es número)
            exponente = sup.translate(_SUPER)
            numero: int | float = float(f"1e{exponente}") if por10 is None else float(f"{decimal}e{exponente}")
        elif exp_e is not None:
            numero = float(f"{decimal}e{exp_e.replace('−', '-')}")
        else:
            numero = float(decimal) if "," in cuerpo else int(cuerpo)
        salida.append((m.start(), m.end(), -numero if signo == "−" else numero))
    return salida


def numeros_del_fragmento(texto: str) -> list[int | float]:
    """Números de un fragmento, en orden: la regla de ``reloj_dmc.constantes`` más la notación científica y las
    fracciones «½», «¼», «¾», «⅓» y «⅔»."""
    return [n for _, _, n in _numeros_con_posicion(texto)]


def _no_leidos(texto: str, leidos: list[tuple[int, int, Any]]) -> list[tuple[int, int, str]]:
    """(inicio, fin, literal) de las cifras pegadas y los cuantiles (CON-11), sin las que son parte de un número leído
    («1e-9»)."""
    salida = []
    for m in _NO_LEIDO.finditer(texto):
        if any(s < m.end() and m.start() < e for s, e, _ in leidos):
            continue
        salida.append((m.start(), m.end(), m.group(0)))
    return salida


def valor_de_literal(literal: str) -> int | None:
    """La lectura a mano de un literal que la regla no lee (CON-13): sus cifras («3L» → 3, «Q05» → 5), la mitad de las
    que van con π («4πh» → 2) y 1 para «un»/«una» en palabras. None si no tiene cifras ni esas palabras."""
    cifras = re.findall(r"\d+", literal)
    if cifras:
        n = int(cifras[0])
        return n // 2 if "π" in literal and n % 2 == 0 else n
    palabras = re.findall(r"\w+", literal.lower())
    return 1 if any(w in _PALABRAS_UNO for w in palabras) else None


def _enmascarar(texto: str) -> str:
    """El texto con las cifras de ``MASCARAS`` cambiadas por espacios (mismas posiciones)."""
    for _, patron, _ in MASCARAS:
        texto = re.sub(patron, lambda m: " " * len(m.group(0)), texto)
    return texto


def _numeros_normativos(texto: str) -> list[tuple[int, int, int | float]]:
    return _numeros_con_posicion(_enmascarar(texto))


def _aplanar(valor: Any) -> Iterator[Any]:
    if isinstance(valor, bool):
        raise TypeError("una constante del texto no es booleana")
    if isinstance(valor, (int, float, str)):
        yield valor
    elif isinstance(valor, (tuple, list)):
        for x in valor:
            yield from _aplanar(x)
    else:
        raise TypeError(f"tipo no admitido en una constante del texto: {type(valor).__name__}")


def _calce(entrada: ConstanteTexto, fragmento: str, numeros: list[tuple[int, int, Any]]) -> tuple[set[int], list, str | None]:
    """Posiciones propias (índices en ``numeros``), números sobrantes y el problema, si lo hay.

    Un valor de texto debe estar tal cual y cubre las cifras que contiene; uno numérico es una subsucesión de los números
    del fragmento (con el signo de ``negativos`` invertido)."""
    try:
        partes = list(_aplanar(entrada.valor))
    except TypeError as e:
        return set(), [], str(e)
    pegados = {i for _, i in getattr(entrada, "pegados", ()) if i is not None} if isinstance(entrada, ConstanteTexto) else set()
    propias: set[int] = set()
    if partes and all(isinstance(p, str) for p in partes):
        desde = 0
        for p in partes:
            a = fragmento.find(p, desde)
            if a < 0:
                return set(), [], f"{p!r} del valor no está en el fragmento"
            propias.update(i for i, (s, e, _) in enumerate(numeros) if a <= s and e <= a + len(p))
            desde = a + len(p)
    elif any(isinstance(p, str) for p in partes):
        return set(), [], "valor que mezcla texto y números"
    else:
        esperados = [(-v if i in entrada.negativos else v) for i, v in enumerate(partes) if i not in pegados]
        pos = 0
        for v in esperados:
            while pos < len(numeros) and not (numeros[pos][2] == v and type(numeros[pos][2]) in (int, float)):
                pos += 1
            if pos == len(numeros):
                return set(), [], (f"{v!r} del valor no está, en ese orden, entre los números del fragmento "
                                   f"{[n for _, _, n in numeros]}")
            propias.add(pos)
            pos += 1
    sobrantes = [n for i, (_, _, n) in enumerate(numeros) if i not in propias]
    return propias, sobrantes, None


# ---------------------------------------------------------------------------------------------
# Secciones

_ENCABEZADO = re.compile(r"(?m)^(#{2,3}) (.+)$")


def _seccion_de_encabezado(nivel: str, titulo: str) -> str | None:
    if nivel == "##":
        if m := re.match(r"(\d+)\. ", titulo):
            return f"§{m.group(1)}"
        if m := re.match(r"Anexo ([A-Z])\.", titulo):
            return f"Anexo {m.group(1)}"
        return None
    if m := re.match(r"(\d+\.\d+) ", titulo):
        return f"§{m.group(1)}"
    return None


@lru_cache(maxsize=8)
def _encabezados(texto: str) -> tuple[tuple[int, int, str | None], ...]:
    return tuple((m.start(), len(m.group(1)), _seccion_de_encabezado(m.group(1), m.group(2)))
                 for m in _ENCABEZADO.finditer(texto))


def tramo_de_seccion(texto: str, seccion: str) -> tuple[int, int] | None:
    """(inicio, fin) de una sección («§2.4», «§9», «Anexo B»): desde su encabezado («### 2.4 », «## 9. »,
    «## Anexo B.») hasta el siguiente del mismo nivel o superior. None si no existe o se repite."""
    encabezados = _encabezados(texto)
    propios = [(i, pos, nivel) for i, (pos, nivel, s) in enumerate(encabezados) if s == seccion]
    if len(propios) != 1:
        return None
    i, inicio, nivel = propios[0]
    fin = next((pos for pos, otro, _ in encabezados[i + 1:] if otro <= nivel), len(texto))
    return inicio, fin


def _regiones(texto: str) -> list[tuple[int, int]]:
    """§2 a §9 y el Anexo B (las secciones del A2)."""
    salida = []
    for seccion in SECCIONES_NORMATIVAS:
        tramo = tramo_de_seccion(texto, seccion)
        if tramo is None:
            raise ValueError(f"no se halló {seccion} en el texto")
        salida.append(tramo)
    return salida


def _ocurrencias(texto: str, fragmento: str, tramo: tuple[int, int]) -> list[int]:
    a, b = tramo
    salida, desde = [], a
    while (i := texto.find(fragmento, desde, b)) >= 0:
        salida.append(i)
        desde = i + 1
    return salida


# ---------------------------------------------------------------------------------------------
# Verificación

def _referencia(nombre: str) -> tuple[str, int | None]:
    m = re.fullmatch(r"([A-Z][A-Z0-9_]*)(?:\[(\d+)\])?", nombre)
    if m is None:
        raise ValueError(f"referencia mal escrita: {nombre!r}")
    return m.group(1), None if m.group(2) is None else int(m.group(2))


def _resolver(referencias, valores_anexo_a: Mapping[str, Any] | None) -> list | None:
    """Los números a los que remiten ``repite`` (constantes de CONSTANTES o ids del Anexo A); None si falta un id."""
    salida = []
    for ref in referencias:
        nombre, k = _referencia(ref)
        if nombre in POR_NOMBRE:
            v = POR_NOMBRE[nombre].valor
        elif valores_anexo_a is not None and nombre in valores_anexo_a:
            v = valores_anexo_a[nombre]
        else:
            return None
        if k is not None:
            v = v[k]
        salida.extend(_aplanar(v))
    return salida


def verificar_contra_texto(texto_protocolo: str) -> list[str]:
    """Problemas: nombres repetidos; fragmentos ausentes de su sección; números que no calzan con el valor (con sus
    ajenos y ``negativos``); repeticiones de una constante de esta lista que no coinciden; exclusiones mal formadas."""
    problemas: list[str] = []
    todas = CONSTANTES + REPETICIONES
    nombres = [c.nombre for c in todas]
    for nombre in sorted({n for n in nombres if nombres.count(n) > 1}):
        problemas.append(f"{nombre}: nombre repetido")
    for c in todas:
        if c.seccion not in SECCIONES_NORMATIVAS and not c.seccion.startswith(tuple(f"{s}." for s in SECCIONES_NORMATIVAS)):
            problemas.append(f"{c.nombre}: sección {c.seccion} fuera de §2-§9 y del Anexo B")
        esperada = "repeticion" if c.repite else None
        if (esperada and c.clase != esperada) or (not esperada and c.clase not in CLASES):
            problemas.append(f"{c.nombre}: clase {c.clase!r} no válida")
        tramo = tramo_de_seccion(texto_protocolo, c.seccion)
        if tramo is None:
            problemas.append(f"{c.nombre}: no se halló la sección {c.seccion}")
            continue
        if not _ocurrencias(texto_protocolo, c.fragmento, tramo):
            donde = "en el texto, pero no en su sección" if c.fragmento in texto_protocolo else "en el texto"
            problemas.append(f"{c.nombre}: el fragmento no está tal cual {donde}: {c.fragmento!r}")
            continue
        _, sobrantes, problema = _calce(c, c.fragmento, _numeros_normativos(c.fragmento))
        if problema:
            problemas.append(f"{c.nombre}: {problema}")
        elif sobrantes != list(c.ajenos):
            problemas.append(f"{c.nombre}: números del fragmento fuera del valor {sobrantes}; declarados como ajenos "
                             f"{list(c.ajenos)}")
        problemas += [f"{c.nombre}: {m}" for m in _problemas_pegados(c)]
        if c.repite:
            try:
                resueltos = _resolver(c.repite, {})
            except ValueError as e:
                problemas.append(f"{c.nombre}: {e}")
                continue
            if resueltos is not None and resueltos != list(_aplanar(c.valor)):
                problemas.append(f"{c.nombre}: repite {list(c.repite)} = {resueltos}, pero su valor es {c.valor!r}")
    for x in NO_NORMATIVOS:
        if not x.motivo.strip():
            problemas.append(f"exclusión sin motivo: {x.fragmento!r}")
        tramo = tramo_de_seccion(texto_protocolo, x.seccion)
        if tramo is None or not _ocurrencias(texto_protocolo, x.fragmento, tramo):
            problemas.append(f"exclusión ({x.seccion}): el fragmento no está tal cual en su sección: {x.fragmento!r}")
            continue
        if x.numeros is not None:
            falsa = ConstanteTexto("exclusión", x.numeros, x.seccion, x.fragmento)
            _, _, problema = _calce(falsa, x.fragmento, _numeros_normativos(x.fragmento))
            if problema:
                problemas.append(f"exclusión ({x.seccion}) {x.fragmento!r}: {problema}")
        if _literales_en_orden(x.fragmento, x.pegados) is None:
            problemas.append(f"exclusión ({x.seccion}) {x.fragmento!r}: sus pegados {list(x.pegados)} no están en orden")
    return problemas


def _literales_en_orden(fragmento: str, literales) -> list[tuple[int, int]] | None:
    """Posiciones (inicio, fin) de los literales en el fragmento, buscados en orden; None si alguno falta."""
    salida, desde = [], 0
    for literal in literales:
        a = fragmento.find(literal, desde)
        if a < 0:
            return None
        salida.append((a, a + len(literal)))
        desde = a + len(literal)
    return salida


def _problemas_pegados(c: ConstanteTexto) -> list[str]:
    """CON-13: cada literal pegado está en el fragmento, en orden; su posición es del valor y no se repite con otra
    lectura; y su lectura a mano coincide con el valor."""
    if not c.pegados:
        return []
    problemas = []
    if _literales_en_orden(c.fragmento, [lit for lit, _ in c.pegados]) is None:
        problemas.append(f"los pegados {[lit for lit, _ in c.pegados]} no están, en orden, en el fragmento")
    try:
        partes = list(_aplanar(c.valor))
    except TypeError:
        return problemas
    for literal, i in c.pegados:
        if i is None:
            continue
        if not (isinstance(i, int) and 0 <= i < len(partes)) or isinstance(partes[i], str):
            problemas.append(f"el pegado {literal!r} apunta a una posición que no es un número del valor: {i!r}")
            continue
        esperado = valor_de_literal(literal)
        if esperado is None or esperado != partes[i]:
            problemas.append(f"el pegado {literal!r} se lee {esperado!r}, pero el valor en {i} es {partes[i]!r}")
    return problemas


def verificar_repeticiones(valores_anexo_a: Mapping[str, Any]) -> list[str]:
    """Cada repetición vale lo que los ids del Anexo A (``U.valores``) o las constantes que repite; los ids existen."""
    problemas = []
    for c in REPETICIONES:
        try:
            resueltos = _resolver(c.repite, valores_anexo_a)
        except (ValueError, IndexError, TypeError) as e:
            problemas.append(f"{c.nombre}: {e}")
            continue
        if resueltos is None:
            problemas.append(f"{c.nombre}: repite un id que no está en el Anexo A ni en CONSTANTES: {list(c.repite)}")
        elif resueltos != list(_aplanar(c.valor)):
            problemas.append(f"{c.nombre}: {list(c.repite)} valen {resueltos} en el Anexo A, pero el cuerpo dice {c.valor!r}")
    return problemas


# ---------------------------------------------------------------------------------------------
# Completitud

def _cubiertas(texto: str, numeros: list[tuple[int, int, Any]]) -> set[int]:
    """Índices de ``numeros`` (del texto enmascarado entero) cubiertos por alguna entrada en alguna ocurrencia."""
    inicios = [s for s, _, _ in numeros]
    cubiertas: set[int] = set()

    def internos(a: int, largo: int) -> list[int]:
        desde = bisect.bisect_left(inicios, a)
        hasta = bisect.bisect_left(inicios, a + largo)
        return [i for i in range(desde, hasta) if numeros[i][1] <= a + largo]

    for c in CONSTANTES + REPETICIONES:
        tramo = tramo_de_seccion(texto, c.seccion)
        if tramo is None:
            continue
        for a in _ocurrencias(texto, c.fragmento, tramo):
            idx = internos(a, len(c.fragmento))
            locales = [(numeros[i][0] - a, numeros[i][1] - a, numeros[i][2]) for i in idx]
            propias, _, problema = _calce(c, c.fragmento, locales)
            if problema:
                continue
            valores_propios = {locales[j][2] for j in propias}
            for j, i in enumerate(idx):
                if j in propias or locales[j][2] in valores_propios:      # CON-3: un ajeno que repite el propio valor
                    cubiertas.add(i)
    for x in NO_NORMATIVOS:
        tramo = tramo_de_seccion(texto, x.seccion)
        if tramo is None:
            continue
        for a in _ocurrencias(texto, x.fragmento, tramo):
            idx = internos(a, len(x.fragmento))
            if x.numeros is None:
                cubiertas.update(idx)
                continue
            locales = [(numeros[i][0] - a, numeros[i][1] - a, numeros[i][2]) for i in idx]
            propias, _, problema = _calce(ConstanteTexto("x", x.numeros, x.seccion, x.fragmento), x.fragmento, locales)
            if not problema:
                cubiertas.update(idx[j] for j in propias)
    return cubiertas


def _declarados(texto: str) -> set[int]:
    """Inicios (en el texto) de los literales no leídos que alguna entrada declara (``pegados``) o que caen dentro de un
    valor de texto de una constante (CON-11)."""
    salida: set[int] = set()
    for e in CONSTANTES + REPETICIONES + NO_NORMATIVOS:
        tramo = tramo_de_seccion(texto, e.seccion)
        if tramo is None:
            continue
        literales = [lit for lit, _ in e.pegados] if isinstance(e, ConstanteTexto) else list(e.pegados)
        textos = []
        if isinstance(e, ConstanteTexto):
            try:
                textos = [p for p in _aplanar(e.valor) if isinstance(p, str)]
            except TypeError:
                textos = []
        for a in _ocurrencias(texto, e.fragmento, tramo):
            for s, _ in _literales_en_orden(e.fragmento, literales) or []:
                salida.add(a + s)
            for s, f in _literales_en_orden(e.fragmento, textos) or []:
                salida.update(a + s + m.start() for m in _NO_LEIDO.finditer(e.fragmento[s:f]))
    return salida


def _enmascarados_con_unidad(texto: str, regiones) -> list[str]:
    """CON-14: cifras que una máscara oculta y que van seguidas de una unidad."""
    problemas = []
    for nombre, patron, _ in MASCARAS:
        for m in re.finditer(patron, texto):
            if not any(a <= m.start() < b for a, b in regiones) or not re.search(r"\d", m.group(0)):
                continue
            if re.match(r"\s?" + _UNIDADES, texto[m.end():]):
                linea = texto.count("\n", 0, m.start()) + 1
                problemas.append(f"l. {linea}: la máscara «{nombre}» oculta {m.group(0)!r}, seguida de una unidad")
    return problemas


def completitud(texto_protocolo: str) -> list[str]:
    """Números de §2-§9 y del Anexo B sin constante, sin repetición del Anexo A y sin exclusión (con su línea)."""
    regiones = _regiones(texto_protocolo)
    leidos = _numeros_normativos(texto_protocolo)
    numeros = [(s, e, n) for s, e, n in leidos if any(a <= s < b for a, b in regiones)]
    cubiertas = _cubiertas(texto_protocolo, numeros)
    problemas = _enmascarados_con_unidad(texto_protocolo, regiones)
    declarados = _declarados(texto_protocolo)
    for s, e, literal in _no_leidos(_enmascarar(texto_protocolo), leidos):
        if any(a <= s < b for a, b in regiones) and s not in declarados:
            linea = texto_protocolo.count("\n", 0, s) + 1
            problemas.append(f"l. {linea}: {literal!r} no lo lee la regla y ninguna entrada lo declara (CON-11)")
    for i, (s, e, n) in enumerate(numeros):
        if i in cubiertas:
            continue
        linea = texto_protocolo.count("\n", 0, s) + 1
        inicio = texto_protocolo.rfind("\n", 0, s) + 1
        fin = texto_protocolo.find("\n", e)
        contexto = texto_protocolo[inicio:fin if fin >= 0 else None].strip()
        problemas.append(f"l. {linea}: {texto_protocolo[s:e]!r} sin constante ni exclusión: «{contexto[:140]}»")
    return problemas


# ---------------------------------------------------------------------------------------------
# Anexo A2

def _a_json(v: Any) -> Any:
    return [_a_json(x) for x in v] if isinstance(v, (tuple, list)) else v


def _extras(c: ConstanteTexto) -> dict:
    """Ajenos, negativos y lo no leído de una entrada (CON-2, CON-3, CON-11)."""
    return {"ajenos": _a_json(c.ajenos), "negativos": list(c.negativos),
            "no_leidos": [{"literal": lit, "posicion": i} for lit, i in c.pegados]}


def anexo_a2(texto_protocolo: str, sha256_texto: str) -> dict:
    """``anexo_a2.json``: el A2 (id, valor, sección, fragmento y clase), las repeticiones del Anexo A, las exclusiones
    y las máscaras, con el sha256 del texto. ValueError si el texto no es el de ``sha256_texto`` o si la verificación o
    la completitud dan problemas (no se genera un anexo que no calza con el texto)."""
    if hashlib.sha256(texto_protocolo.encode("utf-8")).hexdigest() != sha256_texto:
        raise ValueError("sha256_texto no es la huella del texto")
    problemas = verificar_contra_texto(texto_protocolo) + completitud(texto_protocolo)
    if problemas:
        raise ValueError("el anexo A2 no calza con el texto:\n  " + "\n  ".join(problemas[:50]))
    return {"schema": ESQUEMA_ANEXO_A2, "texto_sha256": sha256_texto,
            "constantes": [{"id": c.nombre, "valor": _a_json(c.valor), "seccion": c.seccion, "fragmento": c.fragmento,
                            "clase": c.clase, **_extras(c)} for c in CONSTANTES],
            "repeticiones_del_anexo_a": [{"id": c.nombre, "repite": list(c.repite), "valor": _a_json(c.valor),
                                          "seccion": c.seccion, "fragmento": c.fragmento, **_extras(c)}
                                         for c in REPETICIONES],
            "no_normativos": [{"seccion": x.seccion, "fragmento": x.fragmento, "motivo": x.motivo,
                               "numeros": None if x.numeros is None else list(x.numeros), "no_leidos": list(x.pegados)}
                              for x in NO_NORMATIVOS],
            "mascaras": [{"nombre": n, "patron": p, "motivo": m} for n, p, m in MASCARAS]}
