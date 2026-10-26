"""Controles ciegos con ERA5-Land real (C3, §8.E). Corren antes de C4, sin descargas activas y sin tocar
la DMC: no abren nada bajo DMC (ni catálogo DMC, ni manifiestos, ni progreso.json, ni metadata/); sólo
leen los mensuales de ERA5L y reciben su catalogo_pixeles.parquet ya leído.

- C3a, eje y marea (``c3a``): píxeles válidos con |lat| ≤ 50° en 2015-01 … 2024-12; anomalía de sp y de
  t2m respecto de la media de su día UTC; ajuste de §4.4 en hora solar aparente con K = 3 → ψ2 (sp) y
  φ1 (t2m). Pasa si la mediana de ψ2 (píxeles con A2/EE ≥ 3) dista ≤ 0,30 h de 9,75 h en el país y en
  cada macrozona con ≥ 30 píxeles, y si la mediana nacional de φ1 queda en [12,5; 16,0] h. Si falla, se
  enmienda antes de C4: la constante de 9,75 h (U.f("E4P_S2_FASE_H")) NUNCA se reemplaza sola; el
  resultado sólo informa la mediana de ERA5-Land.
- C3b, recuperación (``c3b``): 30 píxeles (24 con |lat| ≤ 50°, 6 al sur de 50° S) con la semilla 20261022;
  estación de prueba = serie del píxel válido más cercano con ruido de 0,3 °C y 0,3 hPa, etiquetada con
  F(0), F(−3), F(−4) y C(Santiago) en 2008-2026 sin RR06; líneas de orquestacion.LINEAS_C3B (E1a, E3p,
  E3t, E4p y las guardas). Unidad = píxel × reloj (120); recupera con ≥ 80 % de sus años confirmados con
  el reloj verdadero y ninguno con otro.
- C3c, pares costeros (``c3c``): 30 píxeles costeros emparejados con un interior a 10-15 km y |Δz| ≤
  1.000 m, en UTC; decisión con sólo Ts y con Ts y QFE, sin la exclusión costera; T-P no falla en ≥ 95 %
  de los pares; se publica la distribución de δt.
- Salida (``escribir_c3``): LOCAL/…/v1/c3/ (``carpeta_c3``) con un sha256.json de sus archivos.
- Conductor (``correr_c3``): C3a, sp̄ para z_pix y UNA extracción ERA5-Land para la unión de los píxeles de
  C3b y C3c (LOCAL/…/v1/c3_extractos/), y luego la salida. Lo llama el ejecutable (--control-era5), que
  antes comprueba que no haya descargas activas.
Las fases 4 a 10 de §5.2 son las de ``orquestacion.evaluar_red``; las pruebas la simulan (y una la corre).
Cada red de C3b y C3c emite su política en memoria y pasa la ida y vuelta de §8 (lectura C3-15).
Ningún umbral se escribe aquí: salen de ``Umbrales`` (U.f, U.frac) o de ``constantes``.
Depende de: entorno, extraccion (lector ERA5, control propio, píxel, InfoEstacion), fijados (adaptador),
numerico, orquestacion y politica (perezosos), sintetico (etiquetas por camino propio e ida y vuelta),
guardas (nombre de la marca de δt), tablas, tipos, umbrales y constantes.

Lecturas propias de este módulo (van al addendum de C1):
- C3-1. C3a, mediana de ψ2: se envuelve ψ2 − 9,75 h a [−6, 6) (período 12 h, como D en A3) y la distancia
  es el valor absoluto de la mediana de esa diferencia; «la mediana de ψ2» informada es 9,75 h más ella,
  mód 12. La mediana nacional de φ1 se toma con φ1 envuelto a ±12 h del centro de [12,5; 16,0] h. El corte
  circular queda a 6 h (ψ2) y a 12 h (φ1) del valor de referencia, así que no decide nada.
- C3-2. C3a, «macrozona con ≥ 30 píxeles»: cuenta los píxeles que entran en su mediana de ψ2 (válidos,
  |lat| ≤ 50° y A2/EE ≥ 3). La macrozona es la de §3.3 en el centro del píxel (tablas.territorio_y_P),
  incluida «sin_region» si alcanza 30. Una macrozona con menos no se evalúa. La mediana de φ1 usa todos
  los píxeles con ajuste: el texto no pide un mínimo de A1/EE.
- C3-3. C3a, ajuste: anomalía = valor − media de su día UTC, con los días de ≥ 20 valores (§4.4, p = 1);
  t0 = hora UTC + λ/15 + EoT/60, con λ del centro del píxel y n el día del año de la fecha UTC (como R-22);
  K = C3A_K fijo, EE × E4_EE_FACTOR y A2/EE ≥ C3A_A2_EE (constante del cuerpo, no el ajustable
  E4P_A2_EE). Se acumulan las ecuaciones normales mes a mes (sin guardar la serie); da lo mismo que
  numerico.ajuste_armonico (lo comprueba una prueba). t2m en °C y sp en hPa.
- C3-4. C3a falla también si falta algún mes de 2015-01 … 2024-12, si es ilegible, si su eje es anómalo o
  si sus unidades no pasan el rango de §3.4 (como A1), o si se corrió con otros meses (sólo en pruebas).
  «Ilegible» es todo error al leer un mensual que existe (OSError de netCDF4 ante bytes que no son NetCDF,
  RuntimeError de HDF o ErrorExtraccion de su estructura, ValueError): el mes se anota con el tipo del
  error, nunca con su texto, que puede llevar rutas (§7.4), y C3a sigue con los demás meses.
- C3-5. Muestreos (R-39): C3b crea un Generator(PCG64(20261022)) y llama a ``choice`` sin reposición dos
  veces: 24 entre los válidos con |lat| ≤ 50° y luego 6 entre los válidos con lat < −50°, cada lista por
  pixel_id ascendente. C3c crea otro generador con la misma semilla y llama una vez, sobre los costeros
  que tienen pareja (lectura C3-9).
- C3-6. C3b, estación de prueba: sus valores son la serie del píxel válido más cercano al elegido (distinto
  de él; empate, menor pixel_id; sin tope de distancia) más ruido gaussiano de σ = 0,3 °C y 0,3 hPa, una
  realización por píxel fuente y variable (la comparten sus cuatro relojes), con semilla
  sha256("20261022|C3b|ruido|<píxel>|<variable>")[:8]. Se ubica en el centro del píxel elegido, que es su
  celda propia y su píxel enlazado (no costera), y su z_cat es el z_pix del píxel fuente.
- C3-7. Etiquetas de C3b y C3c: las fabrica sintetico por su camino propio (§8, reglas comunes), tipo a,
  escenario completo y sin marcas (sin RR06, TMax, TMin ni observador): completas en los relojes fijos y,
  en C(Z), sin la etiqueta inexistente y con la repetida tomada del primer u. Años 2008-2026 (C3B_ANIOS;
  C3c no los fija y usa los mismos). Valores a 0,1, como el portal; se aplica el control propio de §3.2
  (extraccion.control_propio) y se recalcula p_v del mes. Un valor fuera del rango del control se deja
  NaN antes del generador, que no los acepta (el control lo habría descartado igual).
- C3-8. C3b corre una sola red con las 120 unidades (A3, A5 y la calibración de E3t se calculan dentro
  de ella), con LINEAS_C3B y la exclusión costera aplicada. La comparación con E3t restringida y el
  diagnóstico de reglas vencidas no entran en los criterios y no se calculan. G-versión, que también es
  guarda, no está en LINEAS_C3B; no cambia nada, porque cada estación de prueba tiene una sola versión.
- C3-9. C3c: un píxel es costero si es válido y tiene algún vecino del catálogo (8 contiguos por índice
  global, R-39) que no es válido; es interior si es válido y no tiene ninguno así (un vecino que no está en
  el catálogo no cuenta). Pareja: el interior más cercano (empate, menor pixel_id) entre los que están a
  10-15 km (bordes incluidos) y a |Δz| ≤ 1.000 m. Los costeros sin pareja no entran al sorteo. z_pix usa
  sp̄ de todas las horas 2000-01 … 2026-09 (R-20), con el mismo redondeo float32 de la serie mapeada.
- C3-10. C3c, estación: valores del píxel costero (t2m → Ts; sp → QFE en la variante con QFE), sin ruido
  (el texto no lo pide), en F(0); se ubica en el centro del costero y se enlaza al interior (costera =
  True), con z_cat = z_pix del costero. Dos redes de 30 (sólo Ts; Ts y QFE), con LINEAS_C3B y sin la
  exclusión costera.
- C3-11. C3c, «T-P no falla en ≥ 95 % de los pares»: T-P bajo F(0) (el reloj verdadero), la precalculada
  de la evidencia en cada año-régimen, sin las condiciones de año de la decisión. El denominador son los
  pares con algún T-P evaluable; un par falla si falla en algún año. Sin ningún par evaluable el criterio
  no se cumple. La distribución de δt es el valor de la marca «desfase térmico local» bajo F(0). «Se corre
  la decisión» exige, como en C3b, que las 60 estaciones tengan algún año evaluado (veredicto distinto de
  sin_datos) y que las 30 con QFE tengan alguna fila de T-P bajo F(0) en su evidencia; si no, C3c no pasa.
- C3-12. C3b y C3c: un año cuenta si su veredicto final no es «sin_datos». Es «con el reloj verdadero»
  si la clase confirmada lo contiene (en 2015, F(−3)|C(Santiago) cuenta para C(Santiago)). La
  recuperación (≥ 80 % de los años, ≥ 95 % de las unidades del norte) se mide con los veredictos finales,
  después de §5.3. Una confirmación, en cambio, es la del paso 9 de §5.1: todo año con clase confirmada
  que no contiene el reloj verdadero es una confirmación errónea, sea cual sea su veredicto final, porque
  §5.3 (estación inestable, cambio sin respaldo) y A6 la dejan sin confirmar pero conservan su clase
  (decision.rachas). Esas confirmaciones erróneas cuentan en «ninguna confirmación errónea», en «con sólo
  Ts, ninguna confirmación distinta de F(0)» y en el «ninguno con otro» de la unidad, que entonces no
  recupera; por unidad se informan las dos cuentas (finales y del paso 9). «≥ 95 % de recuperación» es la
  fracción de las 96 unidades del norte que recuperan. Si las ERA5-Land de algún mes son anómalas (A1),
  C3b y C3c fallan sin correr la red.
- C3-13. Salida: ``carpeta_c3`` = LOCAL/…/v1/c3/; por control, <control>.json (pasa y detalle, JSON
  canónico), <control>.csv y <control>_<tabla>.csv; al final sha256.json con el sha256 de cada archivo.
  La serie ERA5-Land de trabajo de C3b y C3c (``correr_c3``: LOCAL/…/v1/c3_extractos/) no es salida y no
  entra en esa lista: se rehace desde ERA5L. La carpeta queda con la salida de UNA corrida: antes de
  escribir se borra el sha256.json anterior; después de escribir los archivos nuevos se borran los
  C3a/C3b/C3c*.json|csv de corridas anteriores que no se volvieron a escribir, y sha256.json va al final,
  así que sólo existe cuando la carpeta es coherente. Los demás archivos de la carpeta no se tocan.
- C3-14. ``correr_c3`` extrae una sola vez la unión de los píxeles de C3b y C3c; los controles de mes de esa
  extracción (todos los meses 2000-01 … 2026-09) deciden el A1 de ambos. Una muestra imposible (ErrorC3) no
  detiene a los demás controles: ese control no pasa y lo dice en sus motivos. Lo mismo un mes ilegible:
  la pasada de sp̄ (que lee los mismos meses que la extracción) lo anota, la extracción no se intenta y
  C3b y C3c no pasan (A1) sin correr la red; si la extracción falla igual, sus dos controles no pasan. Un
  mes ilegible en ``medias_sp_hpa`` (llamada aparte) lanza ErrorC3; un mes ausente no entra en sp̄ y lo
  decide el A1 de la extracción, que lee los mismos meses.
- C3-15. Ida y vuelta (§8, reglas comunes: «obligatoria en cada caso de los grupos B a E»; E es C3). Cada
  red de C3b y de C3c arma su política en memoria (``evaluar_red(..., huellas=huellas_c3(control))``; no
  se escribe ni se publica) y sintetico.comprobar_ida_y_vuelta la somete, con el adaptador fijado
  (fijados.cargar_adaptador) y el CasoSintetico de cada estación de prueba, a ``_utc(L, regla emitida) ==
  u`` en toda etiqueta con regla. El control no pasa si hay alguna falla, si la red no emitió la política
  (A5 alto: no hay con qué comprobar) o si falta el adaptador. Las huellas de esa política: protocolo y
  configuración, las ancladas en C0; adaptador, transiciones, Python y tzdata, las vigentes; informe y
  artefactos, identificadores del control; commit_ap, 40 ceros (no hay commit que citar).
- C3-16. Con una ``serie`` ya extraída, ``controles_era5`` es obligatorio (ValueError si falta): el A1 no se
  salta nunca. Un mes de 2000-01 … 2026-09 sin control cuenta como anómalo («sin control»), igual que uno
  con el eje o las unidades fuera de rango o sin archivo.
"""
from __future__ import annotations

import hashlib
import math
import os
import platform
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

import numpy as np
import pandas as pd

from reloj_dmc import constantes, entorno, extraccion, fijados, numerico, sintetico
from reloj_dmc import tablas as mod_tablas
from reloj_dmc import umbrales as mod_umbrales
from reloj_dmc.guardas import MARCA_DESFASE_TERMICO_LOCAL
from reloj_dmc.tipos import DecisionAnio, Hipotesis, InfoEstacion, Linea, ResultadoGuarda, SerieEra5, Veredicto
from reloj_dmc.umbrales import Umbrales

_C = constantes.valor

CONTROLES = ("C3a", "C3b", "C3c")
# §8.E, C3b: «Se etiqueta con F(0), F(−3), F(−4) y C(Santiago)» (ids de tipos.Hipotesis).
RELOJES_C3B = ("F(0)", "F(-3)", "F(-4)", "C(Santiago)")
# §8.E, C3c: «Ambos llevan etiquetas en UTC».
RELOJ_C3C = "F(0)"
VARIANTE_TS, VARIANTE_TS_QFE = "Ts", "Ts+QFE"          # «con sólo Ts y con Ts y QFE»
VARIANTES_C3C = (VARIANTE_TS, VARIANTE_TS_QFE)
ZONA_NORTE, ZONA_SUR = "norte", "sur"
# Prefijos de los códigos de 6 dígitos de las estaciones de prueba (no son códigos de la DMC).
PREFIJO_C3B, PREFIJO_C3C = "93", "94"

HORAS_DIA = 24.0
PERIODO_S2_H = 12.0          # ψ2 = (12/2π)·atan2(β2, α2) mód 12 (§4.4)
_COLUMNAS_LON = 3600         # pixel_id = lat_index_global·3600 + lon_index_global (rejilla global de 0,1°)
_LAT_FILA_0 = 90.0           # no-umbral: la fila 0 de la rejilla global es 90° N
_GRADOS_VUELTA = 360.0       # no-umbral: una vuelta de longitud
_MEDIO_PASO = 0.5            # no-umbral: medio paso de rejilla, para comparar índices con centros
_BLOQUE_PIXELES = 1024       # píxeles por bloque al acumular C3a (sólo memoria)
_SEPARADOR_CLASE = "|"       # tipos.ClaseH.id une los miembros con «|»
CUANTILES_DELTA_T = (0.0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0)  # no-umbral: cuantiles de δt que se informan (C3c)
CARPETA_C3 = "c3"
NOMBRE_HUELLAS = "sha256.json"
# Archivos que escribe escribir_c3 (C3x.json, C3x.csv, C3x_<tabla>.csv): los únicos que borra (lectura C3-13).
_PATRON_SALIDA_C3 = re.compile(r"C3[abc](_[A-Za-z0-9_]+)?\.(json|csv)")
# Errores de lectura de un mensual que existe (lectura C3-4); PermissionError (guardas de rutas) nunca se traga.
_ERRORES_DE_LECTURA = (OSError, ValueError, RuntimeError)
COMMIT_SIN_PUBLICAR = "0" * 40   # no-umbral: largo de un commit de git; la política de C3 no se publica (C3-15)
MOTIVO_SIN_ADAPTADOR = ("sin el adaptador fijado (meteorologia_v2) no se puede comprobar la ida y vuelta "
                        "(§8, reglas comunes)")
MOTIVO_SIN_POLITICA = ("la red no emitió la política (A5 alto o sin huellas): la ida y vuelta no se pudo "
                       "comprobar (§8, reglas comunes)")


class ErrorC3(RuntimeError):
    """Un control C3 no se puede armar (muestra insuficiente, catálogo incoherente, resultado ajeno)."""


@dataclass(frozen=True)
class _MesIlegible:
    """Un mensual que existe pero no se pudo leer (lectura C3-4): sólo el tipo del error, sin su texto."""
    error: str


@dataclass
class ResultadoC3:
    control: str            # "C3a" | "C3b" | "C3c"
    pasa: bool
    detalle: dict           # JSON sin NaN; en detalle["tablas"] van DataFrames para los CSV
    tabla: pd.DataFrame


@dataclass(frozen=True)
class UnidadC3:
    """Una estación de prueba de C3b o C3c."""
    codigo: str
    control: str            # "C3b" | "C3c"
    sitio: int              # píxel en cuyo centro se ubica la estación
    fuente: int             # píxel cuya serie lleva la estación
    enlazado: int           # píxel de referencia (E3, E3d, T-P)
    reloj: str              # id de la hipótesis verdadera
    zona: str | None = None       # C3b: «norte» o «sur»
    variante: str | None = None   # C3c: «Ts» o «Ts+QFE»
    ruido: bool = False
    con_qfe: bool = True


def _orquestacion():
    """orquestacion se importa al usarla: así C3a y los muestreos no dependen del pipeline."""
    from reloj_dmc import orquestacion
    return orquestacion


def _nada(*_args) -> None:
    return None


def _nunca_hecho(_unidad: str, _huella: str) -> bool:
    return False


# ---------------------------------------------------------------------------------------------
# Catálogo de píxeles: vecinos, costa, distancias
# ---------------------------------------------------------------------------------------------
class _Rejilla:
    """Índices globales de los píxeles del catálogo (columnas lat/lon_index_global o, si faltan, pixel_id)."""

    def __init__(self, catalogo_pixeles: pd.DataFrame):
        ids = catalogo_pixeles["pixel_id"].to_numpy(dtype=np.int64)
        if len(np.unique(ids)) != len(ids):
            raise ErrorC3("pixel_id repetido en el catálogo de píxeles")
        if {"lat_index_global", "lon_index_global"} <= set(catalogo_pixeles.columns):
            ii = catalogo_pixeles["lat_index_global"].to_numpy(dtype=np.int64)
            jj = catalogo_pixeles["lon_index_global"].to_numpy(dtype=np.int64)
        else:
            ii, jj = np.divmod(ids, _COLUMNAS_LON)
        # Los índices deben calzar con el centro (rejilla de 0,1° desde 90° N y 0° E); si no, la convención
        # del catálogo es otra y los vecinos saldrían mal: mejor detenerse.
        por_grado = _COLUMNAS_LON / _GRADOS_VUELTA
        filas_esperadas = (_LAT_FILA_0 - catalogo_pixeles["latitude"].to_numpy(dtype=np.float64)) * por_grado
        columnas_esperadas = np.mod(catalogo_pixeles["longitude"].to_numpy(dtype=np.float64), _GRADOS_VUELTA) * por_grado
        desvio_j = np.abs(np.mod(jj - columnas_esperadas + _COLUMNAS_LON / 2, _COLUMNAS_LON) - _COLUMNAS_LON / 2)
        if len(ids) and (np.abs(ii - filas_esperadas).max() >= _MEDIO_PASO or desvio_j.max() >= _MEDIO_PASO):
            raise ErrorC3("los índices globales del catálogo de píxeles no calzan con sus centros (rejilla de 0,1°)")
        self.indice = {int(p): (int(i), int(j) % _COLUMNAS_LON) for p, i, j in zip(ids, ii, jj)}
        self.por_indice = {v: p for p, v in self.indice.items()}
        if len(self.por_indice) != len(self.indice):
            raise ErrorC3("dos píxeles del catálogo con los mismos índices globales")

    def vecinos(self, pixel_id: int) -> tuple[int, ...]:
        if int(pixel_id) not in self.indice:
            raise KeyError(f"el píxel {pixel_id} no está en el catálogo")
        i, j = self.indice[int(pixel_id)]
        salida = []
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                if di == 0 and dj == 0:
                    continue
                q = self.por_indice.get((i + di, (j + dj) % _COLUMNAS_LON))
                if q is not None:
                    salida.append(q)
        return tuple(sorted(salida))

    def con_vecino_sin_dato(self, pixel_id: int, validos: Iterable[int] | set[int]) -> bool:
        return any(q not in validos for q in self.vecinos(pixel_id))


def vecinos_catalogo(catalogo_pixeles: pd.DataFrame, pixel_id: int) -> Sequence[int]:
    """Los 8 contiguos por lat_index_global y lon_index_global presentes en el catálogo, por pixel_id (R-39).

    Sin esas columnas, los índices salen de pixel_id = lat_index_global·3600 + lon_index_global.
    """
    return _Rejilla(catalogo_pixeles).vecinos(int(pixel_id))


def _ordenado(catalogo_pixeles: pd.DataFrame) -> pd.DataFrame:
    return catalogo_pixeles.sort_values("pixel_id", kind="mergesort").reset_index(drop=True)


def _validos_del_catalogo(catalogo_pixeles: pd.DataFrame, validos: Iterable[int]) -> pd.DataFrame:
    """Filas del catálogo con pixel_id válido, por pixel_id ascendente."""
    conjunto = np.fromiter((int(v) for v in validos), dtype=np.int64)
    cat = _ordenado(catalogo_pixeles)
    return cat[cat["pixel_id"].isin(conjunto)].reset_index(drop=True)


def _coordenadas(catalogo_pixeles: pd.DataFrame) -> dict[int, tuple[float, float]]:
    return {int(p): (float(la), float(lo)) for p, la, lo in zip(catalogo_pixeles["pixel_id"],
                                                                catalogo_pixeles["latitude"],
                                                                catalogo_pixeles["longitude"])}


def _distancias(lat: float, lon: float, cat: pd.DataFrame) -> np.ndarray:
    return numerico.distancia_km(lat, lon, cat["latitude"].to_numpy(dtype=np.float64),
                                 cat["longitude"].to_numpy(dtype=np.float64))


def pixel_valido_mas_cercano(catalogo_pixeles: pd.DataFrame, validos: Iterable[int], pixel_id: int) -> int:
    """C3b: el píxel válido más cercano a ``pixel_id`` (distinto de él), por centros; empate, menor pixel_id."""
    lat, lon = _coordenadas(catalogo_pixeles)[int(pixel_id)]
    cat = _validos_del_catalogo(catalogo_pixeles, validos)
    cat = cat[cat["pixel_id"] != int(pixel_id)]
    if cat.empty:
        raise ErrorC3(f"no hay otro píxel válido para la estación de prueba del píxel {pixel_id}")
    ids = cat["pixel_id"].to_numpy(dtype=np.int64)
    orden = np.lexsort((ids, _distancias(lat, lon, cat)))
    return int(ids[orden[0]])


# ---------------------------------------------------------------------------------------------
# Muestras (R-39)
# ---------------------------------------------------------------------------------------------
def muestra_c3b(catalogo_pixeles: pd.DataFrame, validos: set[int], umbrales: Umbrales) -> list[int]:
    """Generator(PCG64(20261022)).choice sin reposición sobre los pixel_id ordenados: 24 del norte
    (|lat| ≤ 50°), luego 6 del sur (lat < −50°), en ese orden de llamadas (R-39, lectura C3-5)."""
    U = umbrales
    corte = float(_C("C3B_LAT_CORTE"))
    cat = _validos_del_catalogo(catalogo_pixeles, validos)
    lat = cat["latitude"].to_numpy(dtype=np.float64)
    ids = cat["pixel_id"].to_numpy(dtype=np.int64)
    norte, sur = np.sort(ids[np.abs(lat) <= corte]), np.sort(ids[lat < -corte])
    n_norte, n_sur = int(U.f("C3B_PIX_NORTE")), int(U.f("C3B_PIX_SUR"))
    if len(norte) < n_norte or len(sur) < n_sur:
        raise ErrorC3(f"C3b necesita {n_norte} píxeles válidos con |lat| ≤ {corte:g}° y {n_sur} al sur; "
                      f"hay {len(norte)} y {len(sur)}")
    rng = numerico.generador(int(U.f("SEMILLA")))
    primeros = rng.choice(norte, size=n_norte, replace=False)
    segundos = rng.choice(sur, size=n_sur, replace=False)
    return [int(p) for p in primeros] + [int(p) for p in segundos]


def parejas_c3c(catalogo_pixeles: pd.DataFrame, validos: set[int],
                z_pix: Mapping[int, float], umbrales: Umbrales) -> dict[int, tuple[int, float]]:
    """Costero → (interior, distancia_km) para cada píxel costero que tiene pareja (lectura C3-9)."""
    U = umbrales
    rejilla = _Rejilla(catalogo_pixeles)
    cat = _validos_del_catalogo(catalogo_pixeles, validos)
    validos_cat = {int(p) for p in cat["pixel_id"]}
    costa = np.array([rejilla.con_vecino_sin_dato(int(p), validos_cat) for p in cat["pixel_id"]], dtype=bool)
    costeros, interiores = cat[costa], cat[~costa]
    ids_i = interiores["pixel_id"].to_numpy(dtype=np.int64)
    z_i = np.array([float(z_pix.get(int(p), np.nan)) for p in ids_i], dtype=np.float64)
    desde, hasta = float(U.f("C3C_DIST_DESDE_KM")), float(U.f("C3C_DIST_HASTA_KM"))
    dz_max = float(U.f("C3C_DZ_M"))
    salida: dict[int, tuple[int, float]] = {}
    for fila in costeros.itertuples(index=False):
        z_c = float(z_pix.get(int(fila.pixel_id), np.nan))
        if not math.isfinite(z_c) or not len(ids_i):
            continue
        d = _distancias(float(fila.latitude), float(fila.longitude), interiores)
        with np.errstate(invalid="ignore"):
            ok = (d >= desde) & (d <= hasta) & np.isfinite(z_i) & (np.abs(z_i - z_c) <= dz_max)
        if not ok.any():
            continue
        orden = np.lexsort((ids_i[ok], d[ok]))
        salida[int(fila.pixel_id)] = (int(ids_i[ok][orden[0]]), float(d[ok][orden[0]]))
    return salida


def muestra_c3c(catalogo_pixeles: pd.DataFrame, validos: set[int], z_pix: dict[int, float],
                umbrales: Umbrales) -> list[tuple[int, int]]:
    """30 (costero, interior) con Generator(PCG64(20261022)).choice sin reposición sobre los costeros con
    pareja, ordenados por pixel_id (R-39, lecturas C3-5 y C3-9)."""
    return _sortear_c3c(parejas_c3c(catalogo_pixeles, validos, z_pix, umbrales), umbrales)


def _sortear_c3c(parejas: Mapping[int, tuple[int, float]], U: Umbrales) -> list[tuple[int, int]]:
    elegibles = np.array(sorted(parejas), dtype=np.int64)
    n = int(_C("C3C_N_PIXELES"))
    if len(elegibles) < n:
        raise ErrorC3(f"C3c necesita {n} píxeles costeros con pareja; hay {len(elegibles)}")
    rng = numerico.generador(int(U.f("SEMILLA")))
    return [(int(c), parejas[int(c)][0]) for c in rng.choice(elegibles, size=n, replace=False)]


# ---------------------------------------------------------------------------------------------
# C3a: ajuste armónico acumulado (§4.4)
# ---------------------------------------------------------------------------------------------
def meses_c3a() -> tuple[str, ...]:
    """Los meses AAAAMM de §8.E, C3a (2015-01 a 2024-12)."""
    desde, hasta = (m.replace("-", "") for m in _C("C3A_MESES"))
    return tuple(m for m in extraccion.MESES_ERA5 if desde <= m <= hasta)


def pixeles_c3a(catalogo_pixeles: pd.DataFrame, validos: set[int], macrozona_region: Mapping[int, str]) -> pd.DataFrame:
    """Píxeles válidos con |lat| ≤ 50° (C3A_LAT_MAX), con su macrozona de §3.3, por pixel_id."""
    cat = _validos_del_catalogo(catalogo_pixeles, validos)
    cat = cat[cat["latitude"].abs() <= float(_C("C3A_LAT_MAX"))].reset_index(drop=True)
    macro = [mod_tablas.territorio_y_P(float(la), float(lo), catalogo_pixeles, macrozona_region)[2]
             for la, lo in zip(cat["latitude"], cat["longitude"])]
    return pd.DataFrame({"pixel_id": cat["pixel_id"].to_numpy(dtype=np.int64),
                         "latitude": cat["latitude"].to_numpy(dtype=np.float64),
                         "longitude": cat["longitude"].to_numpy(dtype=np.float64),
                         "macrozona": pd.array(macro, dtype="string")})


def _hora_solar_utc(tiempos: np.ndarray, lon_este: np.ndarray) -> np.ndarray:
    """t0 (tiempo × píxel) = (hora UTC + λ/15 + EoT/60) mód 24, como numerico.hora_solar (lectura C3-3)."""
    t = np.asarray(tiempos).astype("datetime64[h]")
    dia = t.astype("datetime64[D]")
    enero_1 = t.astype("datetime64[Y]").astype("datetime64[D]")
    n = (dia - enero_1).astype(np.int64) + 1
    hora = (t - dia.astype("datetime64[h]")).astype(np.int64).astype(np.float64)
    eot = numerico.ecuacion_del_tiempo_min(n) / 60
    t0 = hora[:, None] + np.asarray(lon_este, dtype=np.float64)[None, :] / numerico.GRADOS_POR_HORA + eot[:, None]
    return np.asarray(numerico.envolver(t0, 0.0, HORAS_DIA), dtype=np.float64)


def _diseno(t0: np.ndarray, K: int) -> np.ndarray:
    """Columnas cos(2πk·t0/24), sen(2πk·t0/24), k = 1 … K (α_k, β_k alternados), sobre el último eje."""
    fase = 2 * np.pi * np.mod(t0, HORAS_DIA) / HORAS_DIA
    columnas = []
    for k in range(1, K + 1):
        columnas += [np.cos(k * fase), np.sin(k * fase)]
    return np.stack(columnas, axis=-1)


def _anomalias_dia_utc(x: np.ndarray, dias: np.ndarray, min_valores: int) -> np.ndarray:
    """x − media de su día UTC, por columna; NaN en los días con menos de ``min_valores`` valores."""
    salida = np.full(x.shape, np.nan)
    for d in np.unique(dias[~np.isnat(dias)]):
        filas = dias == d
        bloque = x[filas]
        finitos = np.isfinite(bloque)
        cuenta = finitos.sum(axis=0)
        media = np.where(finitos, bloque, 0.0).sum(axis=0) / np.maximum(cuenta, 1)
        salida[filas] = np.where((cuenta >= min_valores)[None, :], bloque - media[None, :], np.nan)
    return salida


class _Normales:
    """Ecuaciones normales por píxel: XᵀX, Xᵀy, yᵀy y n (filas con y finito)."""

    def __init__(self, n_pix: int, p: int):
        self.XtX = np.zeros((n_pix, p, p))
        self.Xty = np.zeros((n_pix, p))
        self.yty = np.zeros(n_pix)
        self.n = np.zeros(n_pix, dtype=np.int64)

    def sumar(self, columnas: np.ndarray, X: np.ndarray, y: np.ndarray) -> None:
        """X: tiempo × píxel × p; y: tiempo × píxel; ``columnas``: posiciones de esos píxeles."""
        ok = np.isfinite(y)
        Xm = np.where(ok[..., None], X, 0.0)
        y0 = np.where(ok, y, 0.0)
        self.XtX[columnas] += np.einsum("tpi,tpj->pij", Xm, Xm)
        self.Xty[columnas] += np.einsum("tpi,tp->pi", Xm, y0)
        self.yty[columnas] += np.einsum("tp,tp->p", y0, y0)
        self.n[columnas] += ok.sum(axis=0)


def ajuste_desde_normales(XtX: np.ndarray, Xty: np.ndarray, yty: float, n: int, K: int, factor_ee: float,
                          periodo: float = HORAS_DIA) -> numerico.AjusteArmonico | None:
    """El ajuste de numerico.ajuste_armonico (sin constante; EE con σ̂² = RSS/(n − 2K) y método delta,
    × factor_ee) a partir de las ecuaciones normales acumuladas. None si n ≤ 2K o el diseño no tiene rango
    completo."""
    p = 2 * int(K)
    XtX = np.asarray(XtX, dtype=np.float64)
    Xty = np.asarray(Xty, dtype=np.float64)
    if int(n) <= p or not np.all(np.isfinite(XtX)) or np.linalg.matrix_rank(XtX) < p:
        return None
    coef = np.linalg.solve(XtX, Xty)
    alfa, beta = coef[0::2], coef[1::2]
    amplitudes = np.hypot(alfa, beta)
    rss = max(float(yty) - float(coef @ Xty), 0.0)
    cov = rss / (int(n) - p) * np.linalg.inv(XtX)
    ee = np.full(int(K), np.nan)
    for k in range(int(K)):
        if amplitudes[k] > 0:
            va, vb, cab = cov[2 * k, 2 * k], cov[2 * k + 1, 2 * k + 1], cov[2 * k, 2 * k + 1]
            var_a = (alfa[k] ** 2 * va + beta[k] ** 2 * vb + 2 * alfa[k] * beta[k] * cab) / amplitudes[k] ** 2
            ee[k] = np.sqrt(max(var_a, 0.0))
    ee = ee * factor_ee
    phi1 = float(numerico.envolver(periodo / (2 * np.pi) * np.arctan2(beta[0], alfa[0]), 0.0, periodo))
    psi2 = None
    if int(K) >= 2:
        psi2 = float(numerico.envolver(periodo / 2 / (2 * np.pi) * np.arctan2(beta[1], alfa[1]), 0.0, periodo / 2))
    return numerico.AjusteArmonico(K=int(K), alfa=tuple(float(v) for v in alfa), beta=tuple(float(v) for v in beta),
                                   amplitudes=tuple(float(v) for v in amplitudes),
                                   ee_amplitudes=tuple(float(v) for v in ee), phi1=phi1, psi2=psi2, n=int(n))


def _dentro_del_mes(tiempos: np.ndarray, yyyymm: str) -> np.ndarray:
    """Horas del mes dentro del eje de ERA5-Land (como extraccion al volcar la serie)."""
    mes = np.datetime64(datetime.strptime(yyyymm, "%Y%m").strftime("%Y-%m"), "M")
    inicio = max(mes.astype("datetime64[h]"), extraccion.T0_ERA5)
    fin = min((mes + 1).astype("datetime64[h]") - np.timedelta64(1, "h"), extraccion.ULTIMA_HORA_ERA5)
    t = np.asarray(tiempos).astype("datetime64[h]")
    return ~np.isnat(t) & (t >= inicio) & (t <= fin)


def _columnas(pid: np.ndarray, pixel_ids: np.ndarray) -> np.ndarray:
    """Columna de cada píxel pedido en el mes (−1 si no está)."""
    columna = {int(p): c for c, p in enumerate(np.asarray(pid))}
    return np.array([columna.get(int(p), -1) for p in pixel_ids], dtype=np.int64)


def _acumular_mes(normales: Mapping[str, _Normales], tiempos: np.ndarray, pid: np.ndarray,
                  valores: Mapping[str, np.ndarray], yyyymm: str, pixeles: pd.DataFrame, K: int,
                  min_valores: int) -> int:
    """Suma un mes a las normales de t2m y sp; devuelve cuántos píxeles de la muestra trae el mes."""
    dentro = _dentro_del_mes(tiempos, yyyymm)
    cols = _columnas(pid, pixeles["pixel_id"].to_numpy(dtype=np.int64))
    presentes = np.flatnonzero(cols >= 0)
    if not len(presentes) or not dentro.any():
        return int(len(presentes))
    t = np.asarray(tiempos).astype("datetime64[h]")[dentro]
    dias = t.astype("datetime64[D]")
    anomalias = {
        "t2m": _anomalias_dia_utc(valores["t2m"][dentro][:, cols[presentes]].astype(np.float64)
                                  - extraccion.KELVIN_A_CELSIUS, dias, min_valores),
        "sp": _anomalias_dia_utc(valores["sp"][dentro][:, cols[presentes]].astype(np.float64)
                                 / extraccion.PA_POR_HPA, dias, min_valores),
    }
    lon = pixeles["longitude"].to_numpy(dtype=np.float64)
    for a in range(0, len(presentes), _BLOQUE_PIXELES):
        bloque = slice(a, a + _BLOQUE_PIXELES)
        posiciones = presentes[bloque]
        X = _diseno(_hora_solar_utc(t, lon[posiciones]), K)
        for variable, acumulado in normales.items():
            acumulado.sumar(posiciones, X, anomalias[variable][:, bloque])
    return int(len(presentes))


def _tabla_c3a(pixeles: pd.DataFrame, normales: Mapping[str, _Normales], U: Umbrales) -> pd.DataFrame:
    K, factor = int(_C("C3A_K")), float(U.f("E4_EE_FACTOR"))
    a2_ee_min = float(_C("C3A_A2_EE"))
    filas = []
    for i, fila in enumerate(pixeles.itertuples(index=False)):
        sp = ajuste_desde_normales(normales["sp"].XtX[i], normales["sp"].Xty[i], normales["sp"].yty[i],
                                   normales["sp"].n[i], K, factor)
        t2m = ajuste_desde_normales(normales["t2m"].XtX[i], normales["t2m"].Xty[i], normales["t2m"].yty[i],
                                    normales["t2m"].n[i], K, factor)
        a2 = sp.amplitudes[1] if sp is not None else np.nan
        ee2 = sp.ee_amplitudes[1] if sp is not None else np.nan
        cociente = a2 / ee2 if np.isfinite(ee2) and ee2 > 0 else np.nan
        filas.append({
            "pixel_id": int(fila.pixel_id), "latitude": float(fila.latitude), "longitude": float(fila.longitude),
            "macrozona": fila.macrozona,
            "n_sp": int(normales["sp"].n[i]), "A2_hpa": a2, "EE_A2_hpa": ee2,
            "psi2_h": sp.psi2 if sp is not None else np.nan, "A2_EE": cociente,
            "entra_psi2": bool(np.isfinite(cociente) and cociente >= a2_ee_min and sp is not None),
            "n_t2m": int(normales["t2m"].n[i]),
            "A1_c": t2m.amplitudes[0] if t2m is not None else np.nan,
            "EE_A1_c": t2m.ee_amplitudes[0] if t2m is not None else np.nan,
            "phi1_h": t2m.phi1 if t2m is not None else np.nan,
        })
    columnas = ["pixel_id", "latitude", "longitude", "macrozona", "n_sp", "A2_hpa", "EE_A2_hpa", "psi2_h", "A2_EE",
                "entra_psi2", "n_t2m", "A1_c", "EE_A1_c", "phi1_h"]
    tabla = pd.DataFrame(filas, columns=columnas)
    return tabla.astype({"pixel_id": "int64", "macrozona": "string", "n_sp": "int64", "n_t2m": "int64",
                         "entra_psi2": "bool"})


def _resumen_psi2(psi2: np.ndarray, s2: float, tol: float) -> dict:
    psi2 = np.asarray(psi2, dtype=np.float64)
    psi2 = psi2[np.isfinite(psi2)]
    if not len(psi2):
        return {"n": 0, "mediana_psi2_h": None, "desvio_mediano_h": None, "distancia_h": None, "pasa": False}
    d = np.asarray(numerico.envolver(psi2 - s2, -PERIODO_S2_H / 2, PERIODO_S2_H), dtype=np.float64)
    mediana = float(np.median(d))
    return {"n": int(len(psi2)),
            "mediana_psi2_h": float(numerico.envolver(s2 + mediana, 0.0, PERIODO_S2_H)),
            "desvio_mediano_h": mediana, "distancia_h": abs(mediana), "pasa": bool(abs(mediana) <= tol)}


def criterios_c3a(tabla: pd.DataFrame, umbrales: Umbrales) -> dict:
    """Las dos condiciones de C3a sobre la tabla de ajustes por píxel (lecturas C3-1 y C3-2).

    La referencia es siempre la constante vigente U.f("E4P_S2_FASE_H"): la mediana de ERA5-Land sólo se
    informa y nunca la reemplaza.
    """
    U = umbrales
    s2, tol = float(U.f("E4P_S2_FASE_H")), float(U.f("C3A_PSI2_TOL_H"))
    min_macro = int(_C("C3A_MIN_PIXELES_MACRO"))
    entra = tabla[tabla["entra_psi2"]]
    pais = _resumen_psi2(entra["psi2_h"].to_numpy(dtype=np.float64), s2, tol)
    macrozonas = {}
    for mz in sorted(str(m) for m in tabla["macrozona"].dropna().unique()):
        r = _resumen_psi2(entra.loc[entra["macrozona"] == mz, "psi2_h"].to_numpy(dtype=np.float64), s2, tol)
        r["evaluada"] = r["n"] >= min_macro
        if not r["evaluada"]:
            r["pasa"] = None
        macrozonas[mz] = r
    desde, hasta = float(U.f("C3A_PHI1_DESDE_H")), float(U.f("C3A_PHI1_HASTA_H"))
    centro = (desde + hasta) / 2
    phi1 = tabla["phi1_h"].to_numpy(dtype=np.float64)
    phi1 = phi1[np.isfinite(phi1)]
    if len(phi1):
        mediana_phi1 = float(np.median(numerico.envolver(phi1, centro - HORAS_DIA / 2, HORAS_DIA)))
        phi1_pasa = bool(desde <= mediana_phi1 <= hasta)
    else:
        mediana_phi1, phi1_pasa = None, False
    malas = sorted(mz for mz, r in macrozonas.items() if r["evaluada"] and not r["pasa"])
    return {
        "s2_fase_vigente_h": s2, "tolerancia_h": tol, "a2_ee_min": float(_C("C3A_A2_EE")),
        "min_pixeles_macrozona": min_macro,
        "pais": pais, "macrozonas": macrozonas, "macrozonas_que_fallan": malas,
        "phi1": {"n": int(len(phi1)), "mediana_h": mediana_phi1, "intervalo_h": [desde, hasta], "pasa": phi1_pasa},
        "pasa": bool(pais["pasa"] and not malas and phi1_pasa),
    }


def _c3a_desde_meses(meses: Iterable[tuple[str, tuple | _MesIlegible | None]], pixeles: pd.DataFrame,
                     umbrales: Umbrales) -> tuple[pd.DataFrame, dict, list[str]]:
    """Núcleo de C3a. ``meses``: (AAAAMM, lectura) con lectura = (tiempos, pixel_id, valores, control) de
    extraccion.leer_mes_era5land, None si el archivo falta o _MesIlegible si no se pudo leer (lectura
    C3-4). Devuelve (tabla, detalle, motivos)."""
    U = umbrales
    K, min_valores = int(_C("C3A_K")), int(_C("E4_DIA_MIN_VALORES"))
    normales = {"t2m": _Normales(len(pixeles), 2 * K), "sp": _Normales(len(pixeles), 2 * K)}
    corridos, ausentes, eje_malo, unidades_malas, incompletos = [], [], [], [], []
    ilegibles: dict[str, str] = {}
    for yyyymm, lectura in meses:
        corridos.append(yyyymm)
        if lectura is None:
            ausentes.append(yyyymm)
            continue
        if isinstance(lectura, _MesIlegible):
            ilegibles[yyyymm] = lectura.error
            continue
        tiempos, pid, valores, control = lectura
        if not control.eje_ok:
            eje_malo.append(yyyymm)
        if not control.unidades_ok:
            unidades_malas.append(yyyymm)
        presentes = _acumular_mes(normales, tiempos, pid, valores, yyyymm, pixeles, K, min_valores)
        if presentes < len(pixeles):
            incompletos.append(yyyymm)
    tabla = _tabla_c3a(pixeles, normales, U)
    motivos = []
    for nombre, lista in (("meses ausentes", ausentes), ("meses con eje anómalo", eje_malo),
                          ("meses con unidades fuera de rango", unidades_malas)):
        if lista:
            motivos.append(f"{nombre} (A1): {', '.join(lista)}")
    if ilegibles:
        motivos.append(_motivo_ilegibles(ilegibles))
    criterios = criterios_c3a(tabla, U)
    if not criterios["pais"]["pasa"]:
        motivos.append("la mediana nacional de ψ2 no queda a ≤ la tolerancia de la constante de S2")
    if criterios["macrozonas_que_fallan"]:
        motivos.append("macrozonas con la mediana de ψ2 fuera de tolerancia: "
                       + ", ".join(criterios["macrozonas_que_fallan"]))
    if not criterios["phi1"]["pasa"]:
        motivos.append("la mediana nacional de φ1 de t2m queda fuera del intervalo")
    detalle = {
        "meses": corridos, "meses_ausentes": ausentes, "meses_ilegibles": ilegibles, "meses_eje_anomalo": eje_malo,
        "meses_unidades_anomalas": unidades_malas, "meses_sin_todos_los_pixeles": incompletos,
        "n_pixeles": int(len(pixeles)), "n_pixeles_psi2": int(tabla["entra_psi2"].sum()),
        "criterios": criterios,
        "s2_fase_vigente_h": criterios["s2_fase_vigente_h"],
        "constante_reemplazada": False,
        "si_falla": "se enmienda antes de C4 (§8.E y §10, C3); la constante de S2 nunca se reemplaza sola "
                    "por la de ERA5-Land",
    }
    return tabla, detalle, motivos


def _leer_mes(raiz_era5l: Path, yyyymm: str) -> tuple | _MesIlegible | None:
    """extraccion.leer_mes_era5land del mes; None si el archivo falta; _MesIlegible si existe y no se puede
    leer (lectura C3-4). PermissionError (las guardas de rutas) no se traga."""
    ruta = extraccion.ruta_mes_era5(raiz_era5l, yyyymm)
    try:
        if not ruta.is_file():
            return None
        return extraccion.leer_mes_era5land(ruta)
    except PermissionError:
        raise
    except _ERRORES_DE_LECTURA as e:
        return _MesIlegible(type(e).__name__)


def _motivo_ilegibles(ilegibles: Mapping[str, str]) -> str:
    return "meses ilegibles (A1): " + ", ".join(f"{m} ({e})" for m, e in sorted(ilegibles.items()))


def _lector_meses(raiz_era5l: Path, meses: Sequence[str], avance: Callable[[str, int, int], None]
                  ) -> Iterator[tuple[str, tuple | _MesIlegible | None]]:
    for k, yyyymm in enumerate(meses, start=1):
        yield yyyymm, _leer_mes(raiz_era5l, yyyymm)
        avance("C3a/era5", k, len(meses))


def c3a(raiz_era5l: Path, catalogo_pixeles: pd.DataFrame, validos: set[int], macrozona_region: dict,
        umbrales: Umbrales, *, meses: Sequence[str] | None = None,
        avance: Callable[[str, int, int], None] | None = None) -> ResultadoC3:
    """C3a de §8.E sobre los mensuales de ``raiz_era5l`` (lecturas C3-1 a C3-4).

    ``meses`` sólo cambia en las pruebas; con otros meses que los del texto, C3a no pasa. Lee cada mes una
    vez, entero, y acumula las ecuaciones normales de los píxeles de la muestra (memoria acotada).
    """
    U = umbrales
    del_texto = meses_c3a()
    meses = tuple(del_texto if meses is None else meses)
    pixeles = pixeles_c3a(catalogo_pixeles, validos, macrozona_region)
    tabla, detalle, motivos = _c3a_desde_meses(_lector_meses(Path(raiz_era5l), meses, avance or _nada), pixeles, U)
    detalle["meses_del_texto"] = meses == del_texto
    if meses != del_texto:
        motivos.insert(0, "los meses corridos no son los de §8.E (2015-01 a 2024-12)")
    detalle["motivos"] = motivos
    return ResultadoC3("C3a", not motivos, detalle, tabla)


# ---------------------------------------------------------------------------------------------
# sp̄ y z_pix (R-20), por lectura en flujo
# ---------------------------------------------------------------------------------------------
def _medias_sp(raiz_era5l: Path, pixel_ids: Iterable[int], meses: Sequence[str],
               avance: Callable[[str, int, int], None]) -> tuple[dict[int, float], list[str], dict[str, str]]:
    """(sp̄ por píxel, meses ausentes, meses ilegibles → tipo de error): un mes por vez (lectura C3-14)."""
    ids = np.array(sorted({int(p) for p in pixel_ids}), dtype=np.int64)
    suma, cuenta = np.zeros(len(ids)), np.zeros(len(ids), dtype=np.int64)
    ausentes, ilegibles = [], {}
    for k, yyyymm in enumerate(meses, start=1):
        lectura = _leer_mes(raiz_era5l, yyyymm)
        if lectura is None:
            ausentes.append(yyyymm)
        elif isinstance(lectura, _MesIlegible):
            ilegibles[yyyymm] = lectura.error
        else:
            tiempos, pid, valores, _ = lectura
            dentro = _dentro_del_mes(tiempos, yyyymm)
            cols = _columnas(pid, ids)
            ok = np.flatnonzero(cols >= 0)
            if len(ok) and dentro.any():
                x = (valores["sp"][dentro][:, cols[ok]].astype(np.float64) / extraccion.PA_POR_HPA)
                x = x.astype(np.float32).astype(np.float64)
                finitos = np.isfinite(x)
                suma[ok] += np.where(finitos, x, 0.0).sum(axis=0)
                cuenta[ok] += finitos.sum(axis=0)
            del lectura, valores
        avance("C3c/sp_medio", k, len(meses))
    medias = {int(p): float(s / c) for p, s, c in zip(ids, suma, cuenta) if c > 0}
    return medias, ausentes, ilegibles


def medias_sp_hpa(raiz_era5l: Path, pixel_ids: Iterable[int], *, meses: Sequence[str] | None = None,
                  avance: Callable[[str, int, int], None] | None = None) -> dict[int, float]:
    """sp̄ (hPa) de cada píxel sobre las horas con dato de los meses (por omisión 2000-01 … 2026-09), con el
    mismo redondeo float32 que la serie mapeada de extraccion. Sin guardar la serie: un mes por vez.

    Un mes ausente no entra (lo decide el A1 de la extracción, que lee los mismos meses); un mes ilegible
    lanza ErrorC3 con el mes y el tipo del error (lectura C3-14)."""
    meses = tuple(extraccion.MESES_ERA5 if meses is None else meses)
    medias, _, ilegibles = _medias_sp(raiz_era5l, pixel_ids, meses, avance or _nada)
    if ilegibles:
        raise ErrorC3(_motivo_ilegibles(ilegibles))
    return medias


def z_pix_de(medias: Mapping[int, float]) -> dict[int, float]:
    """z_pix (§3.3) de cada sp̄ finito."""
    return {int(p): numerico.z_pixel(float(m)) for p, m in medias.items() if math.isfinite(float(m))}


# ---------------------------------------------------------------------------------------------
# C3b y C3c: plan, estaciones de prueba y red
# ---------------------------------------------------------------------------------------------
def plan_c3b(catalogo_pixeles: pd.DataFrame, validos: set[int], umbrales: Umbrales) -> list[UnidadC3]:
    """Las 120 unidades píxel × reloj, en el orden de la muestra y de RELOJES_C3B (lectura C3-6)."""
    muestra = muestra_c3b(catalogo_pixeles, validos, umbrales)
    n_norte = int(umbrales.f("C3B_PIX_NORTE"))
    unidades = []
    for k, pixel in enumerate(muestra):
        fuente = pixel_valido_mas_cercano(catalogo_pixeles, validos, pixel)
        zona = ZONA_NORTE if k < n_norte else ZONA_SUR
        for j, reloj in enumerate(RELOJES_C3B):
            unidades.append(UnidadC3(codigo=f"{PREFIJO_C3B}{k:02d}{j:02d}", control="C3b", sitio=pixel, fuente=fuente,
                                     enlazado=pixel, reloj=reloj, zona=zona, ruido=True, con_qfe=True))
    return unidades


def plan_c3c(pares: Sequence[tuple[int, int]]) -> dict[str, list[UnidadC3]]:
    """Variante → 30 estaciones (costero, enlazada al interior), en el orden de la muestra (lectura C3-10)."""
    salida = {}
    for v, variante in enumerate(VARIANTES_C3C):
        salida[variante] = [UnidadC3(codigo=f"{PREFIJO_C3C}{k:02d}{v:02d}", control="C3c", sitio=c, fuente=c,
                                     enlazado=i, reloj=RELOJ_C3C, variante=variante, ruido=False,
                                     con_qfe=variante == VARIANTE_TS_QFE)
                            for k, (c, i) in enumerate(pares)]
    return salida


def _texto_numero(x: float) -> str:
    """Decimal con punto y hasta 6 decimales (el texto del catálogo y de los artefactos de prueba)."""
    if not math.isfinite(float(x)):
        raise ErrorC3(f"coordenada o altitud no finita: {x!r}")
    t = f"{float(x):.6f}".rstrip("0").rstrip(".")
    return "0" if t in ("", "-0") else t


def infos_de_prueba(unidades: Sequence[UnidadC3], catalogo_pixeles: pd.DataFrame, medias_sp: Mapping[int, float],
                    macrozona_region: Mapping[int, str], umbrales: Umbrales) -> dict[str, InfoEstacion]:
    """InfoEstacion de cada estación de prueba, por extraccion.info_estaciones (territorio, P, z_pix, Δz).

    Coordenadas: el centro del píxel ``sitio``; z_cat: z_pix del píxel ``fuente``; píxel enlazado:
    ``enlazado``, costera si no es la celda propia del sitio.
    """
    coords = _coordenadas(catalogo_pixeles)
    filas, enlaces = [], {}
    for u in unidades:
        lat, lon = coords[u.sitio]
        if u.fuente not in medias_sp or u.enlazado not in medias_sp:
            raise ErrorC3(f"falta sp̄ del píxel {u.fuente} o {u.enlazado} para {u.codigo}")
        alt = numerico.z_pixel(float(medias_sp[u.fuente]))
        lat_t, lon_t, alt_t = _texto_numero(lat), _texto_numero(lon), _texto_numero(alt)
        filas.append({"codigo": u.codigo, "nombre": f"{u.control} {u.codigo}", "lat_txt": lat_t, "lon_txt": lon_t,
                      "alt_txt": alt_t, "tipo": None, "propietario": None, "omm": None, "oaci": None})
        propia = mod_tablas.celda_que_contiene(float(lat_t), float(lon_t), catalogo_pixeles)
        lat_e, lon_e = coords[u.enlazado]
        d = float(numerico.distancia_km(float(lat_t), float(lon_t), np.array([lat_e]), np.array([lon_e]))[0])
        enlaces[u.codigo] = extraccion.EleccionPixel(int(u.enlazado), d, propia != u.enlazado)
    catalogo_dmc = pd.DataFrame(filas, columns=list(extraccion.COLUMNAS_CATALOGO_DMC))
    medias = {int(p): float(m) for p, m in medias_sp.items()}
    return extraccion.info_estaciones(catalogo_dmc, catalogo_pixeles, enlaces, medias, {}, macrozona_region, umbrales)


def eje_utc_c3() -> np.ndarray:
    """Horas UTC de C3b y C3c: desde el 1 de enero del primer año de C3B_ANIOS hasta la última de ERA5-Land."""
    desde, hasta = _C("C3B_ANIOS")
    inicio = np.datetime64(f"{int(desde):04d}-01-01T00", "h")
    fin = min(np.datetime64(f"{int(hasta) + 1:04d}-01-01T00", "h") - np.timedelta64(1, "h"),
              extraccion.ULTIMA_HORA_ERA5)
    return np.arange(inicio, fin + np.timedelta64(1, "h"), np.timedelta64(1, "h"))


def ruido_c3b(pixel_id: int, variable: str, n: int, sigma: float, umbrales: Umbrales) -> np.ndarray:
    """Ruido gaussiano de C3b (lectura C3-6): σ·N(0, 1) con semilla sha256(«20261022|C3b|ruido|<píxel>|<var>»)."""
    texto = f"{int(umbrales.f('SEMILLA'))}|C3b|ruido|{int(pixel_id)}|{variable}"
    semilla = int.from_bytes(hashlib.sha256(texto.encode("utf-8")).digest()[:int(_C("SEMILLA_BYTES"))], "big")
    return float(sigma) * numerico.generador(semilla).standard_normal(int(n))


def _en_rango(x: np.ndarray, minimo: float, maximo: float) -> np.ndarray:
    """NaN fuera del rango abierto (minimo, maximo) (lectura C3-7)."""
    x = np.asarray(x, dtype=np.float64).copy()
    with np.errstate(invalid="ignore"):
        x[~((x > minimo) & (x < maximo))] = np.nan
    return x


def senales_de_prueba(unidad: UnidadC3, serie: SerieEra5, umbrales: Umbrales) -> pd.DataFrame:
    """ts (°C) y, si corresponde, qfe (hPa) de la estación de prueba en cada hora UTC de eje_utc_c3."""
    U = umbrales
    u = eje_utc_c3()
    ts = serie.valores(unidad.fuente, "t2m", u)
    columnas = {"ts": ts}
    if unidad.con_qfe:
        columnas["qfe"] = serie.valores(unidad.fuente, "sp", u)
    if unidad.ruido:
        columnas["ts"] = columnas["ts"] + ruido_c3b(unidad.fuente, "Ts", len(u), U.f("C3B_RUIDO_C"), U)
        if unidad.con_qfe:
            columnas["qfe"] = columnas["qfe"] + ruido_c3b(unidad.fuente, "QFE", len(u), U.f("C3B_RUIDO_HPA"), U)
    columnas["ts"] = _en_rango(columnas["ts"], U.f("TS_MIN"), U.f("TS_MAX"))
    if unidad.con_qfe:
        columnas["qfe"] = _en_rango(columnas["qfe"], U.f("QFE_MIN"), U.f("QFE_MAX"))
    return pd.DataFrame(columnas, index=pd.DatetimeIndex(u.astype("datetime64[ns]"), name="u"))


def _espec_sintetico(reloj: str) -> str:
    """Id de hipótesis → gramática de sintetico («F(-3)», «C(America/Santiago)»)."""
    h = Hipotesis.desde_id(reloj)
    if h.tipo == "F":
        return h.id
    if h.tipo == "C":
        return f"C({h.zona})"
    raise ErrorC3(f"reloj de prueba no admitido: {reloj}")


def _pasos_del_mes(extracto: pd.DataFrame, meses: pd.DataFrame) -> pd.DataFrame:
    """p_ts y p_qfe de cada mes evaluado, recalculados después del control propio (como extraer_dmc)."""
    pasos: dict[tuple[int, int], dict[str, int | None]] = {}
    L = extracto["L"].to_numpy(dtype="datetime64[ns]")
    for (anio, mes), idx in extracto.groupby(["anio", "mes"], sort=False).indices.items():
        pasos[(int(anio), int(mes))] = {
            col: numerico.paso_nativo(L[idx][np.isfinite(extracto[var].to_numpy(dtype=np.float64)[idx])])
            for col, var in (("p_ts", "ts"), ("p_qfe", "qfe"))}
    meses = meses.copy()
    for col in ("p_ts", "p_qfe"):
        valores = [pasos.get((int(a), int(m)), {}).get(col) if bool(e) else None
                   for a, m, e in zip(meses["anio"], meses["mes"], meses["entra"])]
        meses[col] = pd.array(valores, dtype="Int16")
    return meses


def caso_de_prueba(unidad: UnidadC3, info: InfoEstacion, catalogo_pixeles: pd.DataFrame) -> sintetico.CasoSintetico:
    """El CasoSintetico de una estación de prueba (lectura C3-7): de él salen sus etiquetas y su verdad por
    etiqueta para la ida y vuelta (lectura C3-15)."""
    cod = catalogo_pixeles.loc[catalogo_pixeles["pixel_id"] == unidad.sitio, "cod_comuna"]
    return sintetico.CasoSintetico(
        codigo=info.codigo, relojes=sintetico.relojes_desde_texto(_espec_sintetico(unidad.reloj)), tipo="a",
        escenario="completo", lat=float(info.lat), lon=float(info.lon), alt_m=float(info.alt_m), con_pixel=True,
        cod_comuna=int(cod.iloc[0]) if len(cod) else 0, perturbaciones={"sin_marcas": 1}, replica=0, semilla=0,
        anios=tuple(int(a) for a in _C("C3B_ANIOS")))


def entrada_de_prueba(unidad: UnidadC3, info: InfoEstacion, serie: SerieEra5, catalogo_pixeles: pd.DataFrame,
                      umbrales: Umbrales, *, caso: sintetico.CasoSintetico | None = None):
    """orquestacion.EntradaEstacion de una estación de prueba (lecturas C3-6, C3-7 y C3-10)."""
    orq = _orquestacion()
    caso = caso if caso is not None else caso_de_prueba(unidad, info, catalogo_pixeles)
    extracto, meses = sintetico.entrada_en_memoria(caso, senales_dadas=senales_de_prueba(unidad, serie, umbrales))
    extracto = extraccion.control_propio(extracto, umbrales)
    return orq.EntradaEstacion(info=info, extracto=extracto, meses=_pasos_del_mes(extracto, meses), isd=None)


def _opciones(exclusion_costera: bool):
    orq = _orquestacion()
    return orq.OpcionesCorrida(lineas_activas=orq.LINEAS_C3B, aplicar_exclusion_costera=exclusion_costera,
                               remuestreo=True, comparacion_e3t_restringida=False, diagnostico_reglas_vencidas=False)


def huellas_c3(control: str):
    """politica.HuellasPolitica de la política que una red de C3 arma en memoria sólo para la ida y vuelta
    (lectura C3-15): nunca se escribe ni se publica."""
    from reloj_dmc import politica as mod_politica

    def identificador(que: str) -> str:
        return entorno.sha256_bytes(f"reloj-dmc/v1|{control}|{que}|sin publicar".encode("utf-8"))

    return mod_politica.HuellasPolitica(
        protocolo_sha256=mod_umbrales.SHA_PROTOCOLO_C0, commit_ap=COMMIT_SIN_PUBLICAR,
        configuracion_sha256=mod_umbrales.SHA_JSON_C0, informe_sha256=identificador("informe"),
        artefactos_evaluados_sha256=identificador("artefactos_evaluados"), adaptador_sha256=fijados.SHA_ADAPTADOR,
        python=platform.python_version(), tzdata=mod_tablas.version_de_base(),
        transiciones_sha256=mod_tablas.SHA_ANEXO_A)


def ida_y_vuelta(politica: Mapping | None, casos: Sequence[sintetico.CasoSintetico],
                 adaptador: ModuleType | None) -> dict:
    """§8, reglas comunes, sobre la política de una red de C3 (lectura C3-15). ``comprobada`` es False sin
    política o sin adaptador; ``fallas`` es la lista de sintetico.comprobar_ida_y_vuelta (vacía si pasa)."""
    if politica is None or adaptador is None:
        return {"comprobada": False, "politica_emitida": politica is not None, "reglas": 0,
                "estaciones_con_reglas": 0, "fallas": [], "pasa": False}
    reglas = list(politica.get("politicas_reloj", []))
    fallas = sintetico.comprobar_ida_y_vuelta(politica, list(casos), adaptador)
    return {"comprobada": True, "politica_emitida": True, "reglas": len(reglas),
            "estaciones_con_reglas": len({str(r.get("station_code")) for r in reglas}),
            "fallas": list(fallas), "pasa": not fallas}


def _motivos_ida(ida: Mapping, nombre: str = "") -> list[str]:
    if ida["pasa"]:
        return []
    if not ida["politica_emitida"]:
        return [f"{nombre}{MOTIVO_SIN_POLITICA}"]
    if not ida["comprobada"]:
        return [f"{nombre}{MOTIVO_SIN_ADAPTADOR}"]
    return [f"{nombre}la ida y vuelta falla: alguna etiqueta con regla no vuelve al u que la generó (§8, reglas "
            "comunes; las fallas, en «ida_y_vuelta» del detalle)"]


def _correr_red(unidades: Sequence[UnidadC3], infos: Mapping[str, InfoEstacion], serie: SerieEra5,
                catalogo_pixeles: pd.DataFrame, tablas_calendario: object, umbrales: Umbrales, opciones,
                evaluar_red: Callable | None, avance: Callable[[str, int, int], None], *, huellas,
                adaptador: ModuleType | None) -> tuple[Any, dict]:
    """Una red de C3 (fases 4 a 10, con la política en memoria) y su ida y vuelta: (ResultadoRed, ida)."""
    casos = {u.codigo: caso_de_prueba(u, infos[u.codigo], catalogo_pixeles) for u in unidades}

    def fabrica() -> Iterator:
        for u in unidades:
            yield entrada_de_prueba(u, infos[u.codigo], serie, catalogo_pixeles, umbrales, caso=casos[u.codigo])
    correr = evaluar_red if evaluar_red is not None else _orquestacion().evaluar_red
    resultado = correr(fabrica, serie, tablas_calendario, umbrales, opciones, avance=avance, huellas=huellas)
    return resultado, ida_y_vuelta(getattr(resultado, "politica", None), list(casos.values()), adaptador)


def _serie_extraida(raiz_era5l: Path, pixeles: Iterable[int], destino: Path, validos: set[int],
                    control: str, avance: Callable[[str, int, int], None], hecho, registrar
                    ) -> tuple[SerieEra5, Mapping[str, Any]]:
    """extraccion.extraer_era5land de los píxeles del control (todos los meses); devuelve serie y controles.

    Si no se puede (un mes ilegible la detiene), lanza ErrorC3 con el tipo del error (lectura C3-14);
    PermissionError (las guardas de rutas) no se traga."""
    try:
        return extraccion.extraer_era5land(
            Path(raiz_era5l), sorted({int(p) for p in pixeles}), Path(destino), hecho=hecho or _nunca_hecho,
            registrar=registrar or _nada, avance=lambda h, t: avance(f"{control}/era5", h, t), validos=validos)
    except PermissionError:
        raise
    except _ERRORES_DE_LECTURA as e:
        raise ErrorC3(f"la extracción de ERA5-Land de {control} no se pudo hacer ({type(e).__name__}): algún mes "
                      "es ilegible o la serie no se pudo escribir (A1)") from e


def meses_era5_anomalos(controles: Mapping[str, Any]) -> list[str]:
    """Meses sin archivo (sha256 vacío), con eje anómalo o con unidades fuera de rango (A1, §3.4)."""
    return sorted(m for m, c in controles.items() if not (c.sha256 and c.eje_ok and c.unidades_ok))


def meses_era5_sin_control(controles: Mapping[str, Any], meses: Sequence[str] | None = None) -> list[str]:
    """Meses de ``meses`` (por omisión 2000-01 … 2026-09) que no tienen control: también A1 (lectura C3-16)."""
    return sorted(set(extraccion.MESES_ERA5 if meses is None else meses) - set(controles))


def _a1(controles: Mapping[str, Any], detalle: dict) -> list[str]:
    """Motivos A1 de los controles de mes de la extracción; anota las dos listas en ``detalle``."""
    anomalos, sin_control = meses_era5_anomalos(controles), meses_era5_sin_control(controles)
    detalle["meses_era5_anomalos"], detalle["meses_era5_sin_control"] = anomalos, sin_control
    motivos = []
    if anomalos:
        motivos.append(f"meses de ERA5-Land anómalos (A1): {', '.join(anomalos)}")
    if sin_control:
        motivos.append(f"{len(sin_control)} meses de ERA5-Land sin control de A1 ({sin_control[0]} … "
                       f"{sin_control[-1]})")
    return motivos


def _miembros(clase: str | None) -> frozenset[str]:
    return frozenset(clase.split(_SEPARADOR_CLASE)) if clase else frozenset()


def es_confirmacion_erronea(decision: DecisionAnio, reloj_verdadero: str) -> bool:
    """Confirmación del paso 9 de §5.1 (clase confirmada no nula) que no contiene el reloj verdadero, sea
    cual sea el veredicto final: §5.3 y A6 la dejan sin confirmar, pero conservan su clase (lectura C3-12)."""
    return bool(decision.clase_confirmada) and reloj_verdadero not in _miembros(decision.clase_confirmada)


def recupera_unidad(decisiones: Sequence[DecisionAnio], reloj_verdadero: str, umbrales: Umbrales) -> dict:
    """§8.E, C3b: una unidad recupera si ≥ 80 % de sus años quedan confirmados con el reloj verdadero y
    ninguno con otro (lectura C3-12). La fracción se mide con los veredictos finales; «ninguno con otro»
    cuenta también las confirmaciones erróneas del paso 9 de §5.1 que §5.3 dejó sin confirmar."""
    con_datos = [d for d in decisiones if Veredicto(d.veredicto) != Veredicto.SIN_DATOS]
    confirmados = [d for d in con_datos if Veredicto(d.veredicto) == Veredicto.CONFIRMADO]
    verdaderos = [d for d in confirmados if reloj_verdadero in _miembros(d.clase_confirmada)]
    otros = [d for d in confirmados if reloj_verdadero not in _miembros(d.clase_confirmada)]
    erroneas = [d for d in decisiones if es_confirmacion_erronea(d, reloj_verdadero)]
    fraccion = len(verdaderos) / len(con_datos) if con_datos else 0.0
    return {"n_anios": len(con_datos), "n_confirmados_verdadero": len(verdaderos), "n_confirmados_otro": len(otros),
            "n_confirmaciones_erroneas": len(erroneas),
            "n_erroneas_retiradas": sum(Veredicto(d.veredicto) != Veredicto.CONFIRMADO for d in erroneas),
            "frac_verdadero": fraccion,
            "anios_otro": sorted(int(d.anio) for d in otros),
            "anios_erroneos": sorted(int(d.anio) for d in erroneas),
            "recupera": bool(con_datos and fraccion >= umbrales.frac("C3B_UNIDAD_PCT") and not erroneas)}


def _decisiones_por_codigo(decisiones: Iterable[DecisionAnio], unidades: Sequence[UnidadC3]) -> dict[str, list]:
    por_codigo: dict[str, list] = {u.codigo: [] for u in unidades}
    for d in decisiones:
        if d.codigo not in por_codigo:
            raise ErrorC3(f"la red devolvió una decisión de una estación ajena al control: {d.codigo}")
        por_codigo[d.codigo].append(d)
    return por_codigo


def tabla_anios(decisiones: Iterable[DecisionAnio], unidades: Sequence[UnidadC3]) -> pd.DataFrame:
    """Una fila por estación-año: veredicto final, clase confirmada (paso 9 de §5.1), si el año quedó
    confirmado con el verdadero o con otro, y si es una confirmación errónea (lectura C3-12)."""
    por_codigo = _decisiones_por_codigo(decisiones, unidades)
    verdad = {u.codigo: u.reloj for u in unidades}
    filas = []
    for codigo, lista in por_codigo.items():
        for d in sorted(lista, key=lambda x: int(x.anio)):
            confirmado = Veredicto(d.veredicto) == Veredicto.CONFIRMADO
            miembros = _miembros(d.clase_confirmada)
            filas.append({"codigo": codigo, "anio": int(d.anio), "reloj_verdadero": verdad[codigo],
                          "veredicto": str(Veredicto(d.veredicto)), "motivo": None if d.motivo is None else str(d.motivo),
                          "clase_confirmada": d.clase_confirmada,
                          "confirmado_verdadero": bool(confirmado and verdad[codigo] in miembros),
                          "confirmado_otro": bool(confirmado and verdad[codigo] not in miembros),
                          "confirmacion_erronea": es_confirmacion_erronea(d, verdad[codigo])})
    columnas = ["codigo", "anio", "reloj_verdadero", "veredicto", "motivo", "clase_confirmada",
                "confirmado_verdadero", "confirmado_otro", "confirmacion_erronea"]
    return pd.DataFrame(filas, columns=columnas).astype({"codigo": "string", "anio": "int64", "reloj_verdadero": "string",
                                                         "veredicto": "string", "motivo": "string",
                                                         "clase_confirmada": "string", "confirmado_verdadero": "bool",
                                                         "confirmado_otro": "bool", "confirmacion_erronea": "bool"})


def tabla_unidades(decisiones: Iterable[DecisionAnio], unidades: Sequence[UnidadC3], umbrales: Umbrales) -> pd.DataFrame:
    """Una fila por unidad (estación de prueba) con su recuperación."""
    por_codigo = _decisiones_por_codigo(decisiones, unidades)
    filas = []
    for u in unidades:
        r = recupera_unidad(por_codigo[u.codigo], u.reloj, umbrales)
        filas.append({"codigo": u.codigo, "control": u.control, "sitio": u.sitio, "fuente": u.fuente,
                      "enlazado": u.enlazado, "zona": u.zona, "variante": u.variante, "reloj_verdadero": u.reloj,
                      "n_anios": r["n_anios"], "n_confirmados_verdadero": r["n_confirmados_verdadero"],
                      "n_confirmados_otro": r["n_confirmados_otro"],
                      "n_confirmaciones_erroneas": r["n_confirmaciones_erroneas"],
                      "n_erroneas_retiradas": r["n_erroneas_retiradas"], "frac_verdadero": r["frac_verdadero"],
                      "recupera": r["recupera"]})
    columnas = ["codigo", "control", "sitio", "fuente", "enlazado", "zona", "variante", "reloj_verdadero", "n_anios",
                "n_confirmados_verdadero", "n_confirmados_otro", "n_confirmaciones_erroneas", "n_erroneas_retiradas",
                "frac_verdadero", "recupera"]
    return pd.DataFrame(filas, columns=columnas).astype({
        "codigo": "string", "control": "string", "sitio": "int64", "fuente": "int64", "enlazado": "int64",
        "zona": "string", "variante": "string", "reloj_verdadero": "string", "n_anios": "int64",
        "n_confirmados_verdadero": "int64", "n_confirmados_otro": "int64", "n_confirmaciones_erroneas": "int64",
        "n_erroneas_retiradas": "int64", "frac_verdadero": "float64", "recupera": "bool"})


def criterios_c3b(tabla: pd.DataFrame, umbrales: Umbrales) -> dict:
    """Los tres criterios de C3b sobre la tabla de unidades (lectura C3-12)."""
    U = umbrales
    n_norte, n_sur = int(U.f("C3B_PIX_NORTE")), int(U.f("C3B_PIX_SUR"))
    esperadas = (n_norte + n_sur) * len(RELOJES_C3B)
    norte = tabla[tabla["zona"] == ZONA_NORTE]
    sur_f0 = tabla[(tabla["zona"] == ZONA_SUR) & (tabla["reloj_verdadero"] == RELOJES_C3B[0])]
    erroneas = int(tabla["n_confirmaciones_erroneas"].sum())        # paso 9 de §5.1 (lectura C3-12)
    frac_norte = float(norte["recupera"].mean()) if len(norte) else 0.0
    completo = (len(tabla) == esperadas and len(norte) == n_norte * len(RELOJES_C3B)
                and bool((tabla["n_anios"] > 0).all()))
    norte_ok = bool(len(norte) and frac_norte >= U.frac("C3B_RECUP_PCT"))
    sur_ok = bool(len(sur_f0) == n_sur and sur_f0["recupera"].all())
    return {"unidades": int(len(tabla)), "unidades_esperadas": esperadas, "completo": bool(completo),
            "confirmaciones_erroneas": erroneas,
            "confirmaciones_erroneas_finales": int(tabla["n_confirmados_otro"].sum()),
            "confirmaciones_erroneas_retiradas": int(tabla["n_erroneas_retiradas"].sum()),
            "unidades_norte": int(len(norte)), "recuperan_norte": int(norte["recupera"].sum()),
            "frac_recuperan_norte": frac_norte, "norte_ok": norte_ok,
            "unidades_sur_f0": int(len(sur_f0)), "recuperan_sur_f0": int(sur_f0["recupera"].sum()), "sur_ok": sur_ok,
            "recuperan_sur_otros": int(tabla[(tabla["zona"] == ZONA_SUR)
                                             & (tabla["reloj_verdadero"] != RELOJES_C3B[0])]["recupera"].sum()),
            "pasa": bool(completo and erroneas == 0 and norte_ok and sur_ok)}


def c3b(raiz_era5l: Path, catalogo_pixeles: pd.DataFrame, validos: set[int], umbrales: Umbrales, *,
        macrozona_region: Mapping[int, str], destino: Path | None = None, serie: SerieEra5 | None = None,
        tablas_calendario: object | None = None, evaluar_red: Callable | None = None,
        avance: Callable[[str, int, int], None] | None = None,
        hecho: Callable[[str, str], bool] | None = None,
        registrar: Callable[[str, str, str], None] | None = None,
        controles_era5: Mapping[str, Any] | None = None, adaptador: ModuleType | None = None,
        huellas: Any = None, fallas_era5: Sequence[str] = ()) -> ResultadoC3:
    """C3b de §8.E (lecturas C3-5 a C3-8, C3-12, C3-15 y C3-16).

    Sin ``serie``, extrae de ``raiz_era5l`` los píxeles elegidos y sus fuentes (todos los meses) en
    ``destino``. Con ``serie`` ya extraída, ``controles_era5`` (los controles de mes de esa extracción) es
    obligatorio. Si algún mes es anómalo o no tiene control (A1), o si ``fallas_era5`` trae motivos A1 ya
    conocidos (meses ilegibles, extracción imposible), no corre la red. ``evaluar_red`` (por omisión
    orquestacion.evaluar_red) recibe la fábrica de entradas, la serie, el calendario, los umbrales, las
    opciones (LINEAS_C3B, con la exclusión costera) y ``huellas`` (por omisión huellas_c3("C3b")), y emite la
    política en memoria; su ida y vuelta se comprueba con ``adaptador`` (el fijado, de
    fijados.cargar_adaptador). Sin adaptador no corre la red y C3b no pasa.
    """
    U = umbrales
    avance = avance or _nada
    _validar_fuente_era5("C3b", serie, controles_era5, destino)
    try:
        unidades = plan_c3b(catalogo_pixeles, validos, U)
    except ErrorC3 as e:
        return ResultadoC3("C3b", False, {"motivos": [str(e)]}, tabla_unidades([], [], U))
    pixeles = sorted({u.sitio for u in unidades} | {u.fuente for u in unidades})
    detalle: dict[str, Any] = {
        "muestra": [u.sitio for u in unidades[::len(RELOJES_C3B)]],
        "fuentes": {str(u.sitio): u.fuente for u in unidades[::len(RELOJES_C3B)]},
        "relojes": list(RELOJES_C3B), "anios": list(_C("C3B_ANIOS")),
        "lineas": sorted(str(x) for x in _orquestacion().LINEAS_C3B), "exclusion_costera": True,
        "ruido": {"ts_c": float(U.f("C3B_RUIDO_C")), "qfe_hpa": float(U.f("C3B_RUIDO_HPA"))},
    }
    sin_red = tabla_unidades([], unidades, U)
    previos = list(fallas_era5) + ([] if adaptador is not None else [MOTIVO_SIN_ADAPTADOR])
    if previos:
        detalle["motivos"] = previos
        return ResultadoC3("C3b", False, detalle, sin_red)
    if serie is None:
        try:
            serie, controles_era5 = _serie_extraida(raiz_era5l, pixeles, destino, validos, "C3b", avance, hecho,
                                                    registrar)
        except ErrorC3 as e:
            detalle["motivos"] = [str(e)]
            return ResultadoC3("C3b", False, detalle, sin_red)
    motivos_a1 = _a1(controles_era5, detalle)
    if motivos_a1:
        detalle["motivos"] = motivos_a1
        return ResultadoC3("C3b", False, detalle, sin_red)
    medias = {p: serie.media(p, "sp") for p in pixeles}
    infos = infos_de_prueba(unidades, catalogo_pixeles, medias, macrozona_region, U)
    calendario = tablas_calendario if tablas_calendario is not None else mod_tablas.cargar_tablas()
    resultado, ida = _correr_red(unidades, infos, serie, catalogo_pixeles, calendario, U, _opciones(True),
                                 evaluar_red, avance, huellas=huellas if huellas is not None else huellas_c3("C3b"),
                                 adaptador=adaptador)
    decisiones = list(resultado.decisiones)
    tabla = tabla_unidades(decisiones, unidades, U)
    criterios = criterios_c3b(tabla, U)
    motivos = []
    if not criterios["completo"]:
        motivos.append("la red no evaluó las 120 unidades")
    if criterios["confirmaciones_erroneas"]:
        motivos.append(f"{criterios['confirmaciones_erroneas']} confirmaciones erróneas (paso 9 de §5.1; "
                       f"{criterios['confirmaciones_erroneas_retiradas']} quedaron sin confirmar por §5.3)")
    if not criterios["norte_ok"]:
        motivos.append("recuperación del norte bajo el mínimo")
    if not criterios["sur_ok"]:
        motivos.append("no recuperan todas las unidades F(0) del sur")
    motivos += _motivos_ida(ida)
    detalle.update(criterios=criterios, ida_y_vuelta=ida, motivos=motivos,
                   tablas={"anios": tabla_anios(decisiones, unidades)})
    return ResultadoC3("C3b", bool(criterios["pasa"] and ida["pasa"]), detalle, tabla)


def _validar_fuente_era5(control: str, serie: SerieEra5 | None, controles_era5: Mapping[str, Any] | None,
                         destino: Path | None) -> None:
    """Con ``serie``, sus controles de mes son obligatorios (lectura C3-16); sin ella, hace falta ``destino``."""
    if serie is not None and controles_era5 is None:
        raise ValueError(f"{control}: con una ``serie`` ya extraída hacen falta sus ``controles_era5`` (A1); "
                         "sin ellos el A1 quedaría sin comprobar")
    if serie is None and destino is None:
        raise ValueError(f"{control} necesita ``destino`` para la serie ERA5-Land (o una ``serie`` con sus controles)")


def _guardas_tp(evidencias: Iterable[Any], codigos: Iterable[str], reloj: str) -> pd.DataFrame:
    """T-P bajo ``reloj`` por estación-año: falla > pasa > no_evaluable (lectura C3-11), y su δt."""
    codigos = set(codigos)
    filas = []
    for ev in evidencias:
        codigo = ev.info.codigo
        if codigo not in codigos:
            continue
        g, m = ev.guardas, ev.marcas
        g = None if g is None or "guarda" not in g.columns else g[(g["guarda"] == Linea.TP.value) & (g["H"] == reloj)]
        m = (None if m is None or "marca" not in m.columns
             else m[(m["marca"] == MARCA_DESFASE_TERMICO_LOCAL) & (m["H"] == reloj)])
        anios = sorted({int(a) for a in (g["anio"] if g is not None else [])}
                       | {int(a) for a in (m["anio"] if m is not None else [])})
        for anio in anios:
            filas_tp = [] if g is None else [str(r) for r in g.loc[g["anio"] == anio, "resultado"]]
            res = set(filas_tp)
            if ResultadoGuarda.FALLA.value in res:
                tp = ResultadoGuarda.FALLA.value
            elif ResultadoGuarda.PASA.value in res:
                tp = ResultadoGuarda.PASA.value
            else:
                tp = ResultadoGuarda.NO_EVALUABLE.value
            delta = None
            if m is not None:
                vals = [v for v in m.loc[m["anio"] == anio, "valor"]
                        if v is not None and not (isinstance(v, float) and math.isnan(v))]
                delta = float(vals[0]) if vals else None
            filas.append({"codigo": codigo, "anio": anio, "tp": tp, "tp_filas": len(filas_tp), "delta_t_h": delta})
    return pd.DataFrame(filas, columns=["codigo", "anio", "tp", "tp_filas", "delta_t_h"]).astype(
        {"codigo": "string", "anio": "int64", "tp": "string", "tp_filas": "int64", "delta_t_h": "float64"})


def tabla_pares(decisiones: Mapping[str, Sequence[DecisionAnio]], evidencias: Mapping[str, Sequence[Any]],
                planes: Mapping[str, Sequence[UnidadC3]], distancias: Mapping[int, float],
                z_pix: Mapping[int, float], umbrales: Umbrales) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(una fila por par y variante, δt y T-P por estación-año) de C3c."""
    filas, deltas = [], []
    for variante, unidades in planes.items():
        tabla = tabla_unidades(decisiones.get(variante, ()), unidades, umbrales)
        tp = _guardas_tp(evidencias.get(variante, ()), [u.codigo for u in unidades], RELOJ_C3C)
        tp = tp.assign(variante=variante)
        deltas.append(tp)
        for u, fila in zip(unidades, tabla.itertuples(index=False)):
            propios = tp[tp["codigo"] == u.codigo]
            evaluados = propios[propios["tp"] != ResultadoGuarda.NO_EVALUABLE.value]
            z_c, z_i = z_pix.get(u.sitio), z_pix.get(u.enlazado)
            filas.append({"codigo": u.codigo, "variante": variante, "costero": u.sitio, "interior": u.enlazado,
                          "distancia_km": distancias.get(u.sitio), "dz_m": (None if z_c is None or z_i is None
                                                                            else float(z_c) - float(z_i)),
                          "n_anios": fila.n_anios, "n_confirmados_f0": fila.n_confirmados_verdadero,
                          "n_confirmados_otro": fila.n_confirmados_otro,
                          "n_confirmaciones_erroneas": fila.n_confirmaciones_erroneas,
                          "n_erroneas_retiradas": fila.n_erroneas_retiradas,
                          "tp_anios_con_guarda": int((propios["tp_filas"] > 0).sum()),
                          "tp_anios_evaluados": int(len(evaluados)),
                          "tp_anios_falla": int((evaluados["tp"] == ResultadoGuarda.FALLA.value).sum())})
    columnas = ["codigo", "variante", "costero", "interior", "distancia_km", "dz_m", "n_anios", "n_confirmados_f0",
                "n_confirmados_otro", "n_confirmaciones_erroneas", "n_erroneas_retiradas", "tp_anios_con_guarda",
                "tp_anios_evaluados", "tp_anios_falla"]
    tabla = pd.DataFrame(filas, columns=columnas).astype({
        "codigo": "string", "variante": "string", "costero": "int64", "interior": "int64", "distancia_km": "float64",
        "dz_m": "float64", "n_anios": "int64", "n_confirmados_f0": "int64", "n_confirmados_otro": "int64",
        "n_confirmaciones_erroneas": "int64", "n_erroneas_retiradas": "int64", "tp_anios_con_guarda": "int64",
        "tp_anios_evaluados": "int64", "tp_anios_falla": "int64"})
    delta = (pd.concat(deltas, ignore_index=True) if deltas else
             pd.DataFrame(columns=["codigo", "anio", "tp", "tp_filas", "delta_t_h", "variante"]))
    return tabla, delta[["codigo", "variante", "anio", "tp", "delta_t_h"]]


def criterios_c3c(tabla: pd.DataFrame, umbrales: Umbrales) -> dict:
    """Los tres criterios de C3c sobre la tabla de pares (lecturas C3-11 y C3-12). «completo»: las 60
    estaciones con algún año evaluado y las 30 con QFE con alguna fila de T-P bajo F(0)."""
    U = umbrales
    n = int(_C("C3C_N_PIXELES"))
    solo_ts = tabla[tabla["variante"] == VARIANTE_TS]
    con_qfe = tabla[tabla["variante"] == VARIANTE_TS_QFE]
    erroneas = int(tabla["n_confirmaciones_erroneas"].sum())        # paso 9 de §5.1 (lectura C3-12)
    otras_solo_ts = int(solo_ts["n_confirmaciones_erroneas"].sum())
    evaluables = con_qfe[con_qfe["tp_anios_evaluados"] > 0]
    sin_fallar = int((evaluables["tp_anios_falla"] == 0).sum())
    frac = sin_fallar / len(evaluables) if len(evaluables) else None
    tp_ok = bool(frac is not None and frac >= U.frac("C3C_TP_PCT"))
    sin_anios = int((tabla["n_anios"] == 0).sum())
    sin_tp = int((con_qfe["tp_anios_con_guarda"] == 0).sum())
    completo = len(solo_ts) == n and len(con_qfe) == n and sin_anios == 0 and sin_tp == 0
    return {"pares": n, "completo": bool(completo), "estaciones_sin_anios": sin_anios,
            "estaciones_qfe_sin_tp": sin_tp, "confirmaciones_erroneas": erroneas,
            "confirmaciones_erroneas_finales": int(tabla["n_confirmados_otro"].sum()),
            "confirmaciones_erroneas_retiradas": int(tabla["n_erroneas_retiradas"].sum()),
            "confirmaciones_no_f0_solo_ts": otras_solo_ts,
            "pares_tp_evaluable": int(len(evaluables)), "pares_tp_sin_fallar": sin_fallar,
            "frac_tp_sin_fallar": frac,
            "frac_tp_sin_fallar_sobre_todos": (int((con_qfe["tp_anios_falla"] == 0).sum()) / len(con_qfe)
                                               if len(con_qfe) else None),
            "tp_ok": tp_ok,
            "pasa": bool(completo and erroneas == 0 and otras_solo_ts == 0 and tp_ok)}


def c3c(raiz_era5l: Path, catalogo_pixeles: pd.DataFrame, validos: set[int], umbrales: Umbrales, *,
        macrozona_region: Mapping[int, str], destino: Path | None = None, z_pix: Mapping[int, float] | None = None,
        serie: SerieEra5 | None = None, tablas_calendario: object | None = None,
        evaluar_red: Callable | None = None, avance: Callable[[str, int, int], None] | None = None,
        hecho: Callable[[str, str], bool] | None = None,
        registrar: Callable[[str, str, str], None] | None = None,
        controles_era5: Mapping[str, Any] | None = None, adaptador: ModuleType | None = None,
        huellas: Any = None, fallas_era5: Sequence[str] = ()) -> ResultadoC3:
    """C3c de §8.E (lecturas C3-9 a C3-12, C3-15 y C3-16).

    Sin ``z_pix``, lo calcula de sp̄ (todos los meses) para los píxeles válidos; un mes ilegible deja C3c
    sin pasar (A1). Sin ``serie``, extrae los 60 píxeles de los pares en ``destino``; con ``serie``,
    ``controles_era5`` (los de su extracción) es obligatorio. ``fallas_era5``: motivos A1 ya conocidos.
    Corre dos redes (sólo Ts; Ts y QFE) sin la exclusión costera; cada una emite su política en memoria
    (``huellas``, por omisión huellas_c3("C3c")) y pasa la ida y vuelta con ``adaptador``. Sin adaptador no
    corre ninguna red y C3c no pasa.
    """
    U = umbrales
    avance = avance or _nada
    _validar_fuente_era5("C3c", serie, controles_era5, destino)
    previos = list(fallas_era5) + ([] if adaptador is not None else [MOTIVO_SIN_ADAPTADOR])
    if z_pix is None and not previos:
        medias_sp, _, ilegibles = _medias_sp(raiz_era5l, validos, extraccion.MESES_ERA5, avance)
        if ilegibles:
            previos.append(_motivo_ilegibles(ilegibles))
        z_pix = z_pix_de(medias_sp)
    detalle: dict[str, Any] = {"reloj": RELOJ_C3C, "variantes": list(VARIANTES_C3C), "anios": list(_C("C3B_ANIOS")),
                               "lineas": sorted(str(x) for x in _orquestacion().LINEAS_C3B),
                               "exclusion_costera": False}
    vacia = pd.DataFrame(columns=["codigo", "variante", "costero", "interior"])
    if z_pix is not None:
        parejas = parejas_c3c(catalogo_pixeles, validos, dict(z_pix), U)
        try:
            pares = _sortear_c3c(parejas, U)
        except ErrorC3 as e:
            detalle["motivos"] = previos + [str(e)]
            return ResultadoC3("C3c", False, detalle, vacia)
        distancias = {c: parejas[c][1] for c, _ in pares}
        detalle["pares"] = [[c, i] for c, i in pares]
    if previos:
        detalle["motivos"] = previos
        return ResultadoC3("C3c", False, detalle, vacia)
    pixeles = sorted({p for par in pares for p in par})
    if serie is None:
        try:
            serie, controles_era5 = _serie_extraida(raiz_era5l, pixeles, destino, validos, "C3c", avance, hecho,
                                                    registrar)
        except ErrorC3 as e:
            detalle["motivos"] = [str(e)]
            return ResultadoC3("C3c", False, detalle, vacia)
    motivos_a1 = _a1(controles_era5, detalle)
    if motivos_a1:
        detalle["motivos"] = motivos_a1
        return ResultadoC3("C3c", False, detalle, vacia)
    medias = {p: serie.media(p, "sp") for p in pixeles}
    planes = plan_c3c(pares)
    calendario = tablas_calendario if tablas_calendario is not None else mod_tablas.cargar_tablas()
    huellas = huellas if huellas is not None else huellas_c3("C3c")
    decisiones, evidencias, idas = {}, {}, {}
    for variante, unidades in planes.items():
        infos = infos_de_prueba(unidades, catalogo_pixeles, medias, macrozona_region, U)
        resultado, idas[variante] = _correr_red(unidades, infos, serie, catalogo_pixeles, calendario, U,
                                                _opciones(False), evaluar_red, avance, huellas=huellas,
                                                adaptador=adaptador)
        decisiones[variante] = list(resultado.decisiones)
        evidencias[variante] = list(getattr(resultado, "evidencias", ()) or ())
    tabla, delta = tabla_pares(decisiones, evidencias, planes, distancias, z_pix, U)
    criterios = criterios_c3c(tabla, U)
    motivos = []
    if not criterios["completo"]:
        motivos.append("las redes no evaluaron los 30 pares (estaciones sin años evaluados o con QFE y sin T-P)")
    if criterios["confirmaciones_erroneas"]:
        motivos.append(f"{criterios['confirmaciones_erroneas']} confirmaciones erróneas (paso 9 de §5.1; "
                       f"{criterios['confirmaciones_erroneas_retiradas']} quedaron sin confirmar por §5.3)")
    if criterios["confirmaciones_no_f0_solo_ts"]:
        motivos.append("con sólo Ts hay confirmaciones distintas de F(0)")
    if not criterios["tp_ok"]:
        motivos.append("T-P falla en más pares de los admitidos, o en ningún par es evaluable")
    for variante, ida in idas.items():
        motivos += _motivos_ida(ida, f"{variante}: ")
    anios = pd.concat([tabla_anios(decisiones[v], planes[v]).assign(variante=v) for v in planes], ignore_index=True)
    valores_dt = delta.loc[delta["variante"] == VARIANTE_TS_QFE, "delta_t_h"].dropna().to_numpy(dtype=np.float64)
    detalle.update(criterios=criterios, ida_y_vuelta=idas, motivos=motivos, tablas={"delta_t": delta, "anios": anios},
                   delta_t={"n": int(len(valores_dt)),
                            "cuantiles_h": ({str(q): float(np.quantile(valores_dt, q)) for q in CUANTILES_DELTA_T}
                                            if len(valores_dt) else {})})
    pasa = bool(criterios["pasa"] and all(ida["pasa"] for ida in idas.values()))
    return ResultadoC3("C3c", pasa, detalle, tabla)


# ---------------------------------------------------------------------------------------------
# Salida (LOCAL/…/v1/c3/, con sha256)
# ---------------------------------------------------------------------------------------------
def carpeta_c3(rutas: entorno.Rutas) -> Path:
    """LOCAL/modelado_1km/verificacion_reloj_dmc/v1/c3 (R-32): nunca en los repositorios ni en /Volumes."""
    return rutas.corridas / CARPETA_C3


def _a_json(x: Any) -> Any:
    """Valores de un detalle → JSON canónico: sin NaN (None), sin numpy, claves de texto, sin rutas."""
    if x is None or isinstance(x, (bool, str)):
        return x
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return float(x) if math.isfinite(float(x)) else None
    if isinstance(x, Mapping):
        return {str(k): _a_json(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_a_json(v) for v in x]
    if isinstance(x, (set, frozenset)):
        return sorted(_a_json(v) for v in x)
    if isinstance(x, np.ndarray):
        return [_a_json(v) for v in x.tolist()]
    if isinstance(x, Path):
        raise TypeError("el detalle de C3 no lleva rutas (privacidad, §7.4)")
    if hasattr(x, "value") and isinstance(getattr(x, "value"), str):
        return x.value
    raise TypeError(f"valor no serializable en el detalle de C3: {type(x).__name__}")


def _csv(tabla: pd.DataFrame) -> bytes:
    return tabla.to_csv(index=False, lineterminator="\n").encode("utf-8")


def escribir_c3(resultados: Sequence[ResultadoC3], carpeta: Path) -> dict[str, str]:
    """Escribe <control>.json, <control>.csv y <control>_<tabla>.csv de cada resultado y, al final,
    sha256.json con la huella de cada uno; devuelve nombre → sha256 (incluido el de sha256.json).

    Escritura atómica (entorno.escribir_atomico: nunca bajo /Volumes ni en los repositorios). Antes de
    escribir nada comprueba que ningún archivo contenga «/Users/» ni «@» (§7.4). La carpeta queda con la
    salida de esta corrida (lectura C3-13): primero se borra el sha256.json anterior, después de escribir
    se borran los C3a/C3b/C3c*.json|csv que no se volvieron a escribir y sha256.json va al final. Los
    demás archivos de la carpeta no se tocan.
    """
    archivos: dict[str, bytes] = {}
    for r in resultados:
        if r.control not in CONTROLES:
            raise ValueError(f"control desconocido: {r.control!r}")
        detalle = dict(r.detalle)
        extra = detalle.pop("tablas", None) or {}
        cuerpo = {"control": r.control, "pasa": bool(r.pasa), "detalle": _a_json(detalle)}
        archivos[f"{r.control}.json"] = entorno.json_canonico(cuerpo) + b"\n"
        archivos[f"{r.control}.csv"] = _csv(r.tabla)
        for nombre in sorted(extra):
            archivos[f"{r.control}_{nombre}.csv"] = _csv(extra[nombre])
    if NOMBRE_HUELLAS in archivos:
        raise ValueError(f"{NOMBRE_HUELLAS} es el nombre reservado de la lista de huellas")
    for nombre, datos in archivos.items():
        if not entorno.sin_datos_privados(datos.decode("utf-8")):
            raise ValueError(f"{nombre} contiene «/Users/», «@» o la carpeta personal (§7.4)")
    carpeta = Path(os.path.normpath(os.path.abspath(os.fspath(carpeta))))
    for r in (carpeta, carpeta / NOMBRE_HUELLAS):     # antes de borrar nada: nunca bajo /Volumes ni en los repos
        entorno.prohibido_volumes(r)
        entorno.prohibido_repositorios(r)
    anteriores = (sorted(p.name for p in carpeta.iterdir() if p.is_file() and _PATRON_SALIDA_C3.fullmatch(p.name))
                  if carpeta.is_dir() else [])
    (carpeta / NOMBRE_HUELLAS).unlink(missing_ok=True)   # sin lista de huellas mientras la carpeta está a medias
    huellas = {nombre: entorno.escribir_atomico(carpeta / nombre, datos) for nombre, datos in sorted(archivos.items())}
    for nombre in anteriores:
        if nombre not in archivos:
            (carpeta / nombre).unlink(missing_ok=True)
    lista = entorno.json_canonico({"archivos": huellas}) + b"\n"
    huellas[NOMBRE_HUELLAS] = entorno.escribir_atomico(carpeta / NOMBRE_HUELLAS, lista)
    return huellas


# ---------------------------------------------------------------------------------------------
# Conductor: C3 completo con el mínimo de lecturas de ERA5-Land
# ---------------------------------------------------------------------------------------------
CARPETA_EXTRACTOS_C3 = "c3_extractos"


def correr_c3(rutas: entorno.Rutas, catalogo_pixeles: pd.DataFrame, validos: set[int],
              macrozona_region: Mapping[int, str], umbrales: Umbrales, *, evaluar_red: Callable | None = None,
              tablas_calendario: object | None = None, avance: Callable[[str, int, int], None] | None = None,
              hecho: Callable[[str, str], bool] | None = None,
              registrar: Callable[[str, str, str], None] | None = None,
              adaptador: ModuleType | None = None) -> tuple[list[ResultadoC3], dict[str, str]]:
    """C3a, C3b y C3c sobre ``rutas.era5l``, con la salida en carpeta_c3(rutas) (lectura C3-13).

    Lee ERA5-Land tres veces: los 120 meses de C3a; todos los meses para sp̄ (z_pix de C3c); y todos una
    sola vez para la serie de la unión de los píxeles de C3b y C3c, en LOCAL/…/v1/c3_extractos/. No recibe
    ni abre nada de rutas.dmc. Quien llama comprueba antes que no haya descargas activas (§8.E).
    ``adaptador``: el fijado; por omisión fijados.cargar_adaptador(rutas.ap), ANTES de leer ERA5-Land (sin
    él no hay ida y vuelta, lectura C3-15). Un mes ilegible no detiene nada (lectura C3-14): C3a lo
    anota, la pasada de sp̄ lo encuentra antes de la extracción, que entonces no se intenta, y C3b y C3c no
    pasan (A1). Devuelve los tres resultados y nombre → sha256 de lo escrito.
    """
    U = umbrales
    avance = avance or _nada
    if adaptador is None:
        adaptador = fijados.cargar_adaptador(rutas.ap)
    ra = c3a(rutas.era5l, catalogo_pixeles, validos, macrozona_region, U, avance=avance)
    medias, _, ilegibles = _medias_sp(rutas.era5l, validos, extraccion.MESES_ERA5, avance)
    z = z_pix_de(medias)
    fallas: list[str] = [_motivo_ilegibles(ilegibles)] if ilegibles else []
    pixeles: set[int] = set()
    try:
        pixeles |= {p for u in plan_c3b(catalogo_pixeles, validos, U) for p in (u.sitio, u.fuente)}
    except ErrorC3:
        pass                                   # c3b lo informa como motivo
    try:
        pixeles |= {p for par in muestra_c3c(catalogo_pixeles, validos, z, U) for p in par}
    except ErrorC3:
        pass                                   # c3c lo informa como motivo
    destino = rutas.corridas / CARPETA_EXTRACTOS_C3
    serie, controles = None, None
    if pixeles and not fallas:
        try:
            serie, controles = _serie_extraida(rutas.era5l, pixeles, destino, validos, "C3b-C3c", avance, hecho,
                                               registrar)
        except ErrorC3 as e:
            fallas.append(str(e))
    comunes = dict(macrozona_region=macrozona_region, destino=destino, serie=serie, controles_era5=controles,
                   tablas_calendario=tablas_calendario, evaluar_red=evaluar_red, avance=avance, hecho=hecho,
                   registrar=registrar, adaptador=adaptador, fallas_era5=tuple(fallas))
    rb = c3b(rutas.era5l, catalogo_pixeles, validos, U, **comunes)
    rc = c3c(rutas.era5l, catalogo_pixeles, validos, U, z_pix=z, **comunes)
    resultados = [ra, rb, rc]
    return resultados, escribir_c3(resultados, carpeta_c3(rutas))
