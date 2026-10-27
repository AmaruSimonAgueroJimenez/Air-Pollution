"""Guardas (E3d, P7, T-P, E4t, G-versión) y marcas (G-HR, G-viento, posible media horaria,
desfase térmico local) de §4.7 y §4.3.5. Bloquean o marcan; nunca apoyan.

Las guardas que dependen de H se PRECALCULAN para toda H de P en la fase 4 (así la decisión no
vuelve a leer extractos); decision.py sólo consulta la de la H de K = {H} (§5.1, paso 5). Las marcas
se precalculan igual y se aplican sólo en años confirmados.
Salidas: filas de ESQUEMA_GUARDAS y ESQUEMA_MARCAS.
Depende de: tipos, numerico, umbrales (vía ctx), constantes, tablas, lineas_fisicas (pares_e3,
ajustes_e4, e3, diagnostico_subhorario) y lineas_registro (e2, para el j* de G-versión).

Convenciones que lee decision.py (COORDINACION_C1.md, «Ola 2 cerrada»):
- ``guarda`` = valor de Linea («E3d», «P7», «T-P», «E4t», «G-version»); ``H`` = id de hipótesis, o «*»
  si la guarda no depende de H (G-versión, y P7 en una estación sin referencia; con referencia, P7 va por H
  desde la Enmienda 5, E5-2, GU-3); ``unidad`` = «AAAA» (E3d, P7, G-versión) o «R0»/«R1»
  (T-P, E4t); ``resultado`` ∈ {pasa, falla, no_evaluable}; ``detalle`` = texto corto con el motivo.
- Marcas: ``marca`` = «G-HR» (H = «*»), «G-viento» (por H) y «desfase_termico_local» (por H, valor = δt en
  horas o None); ``valor`` de G-HR y G-viento = True (reloj no verificado), False (evaluada, sin marca) o
  None (no aplica). El umbral de la marca térmica (DTL_DELTA_H) y la condición «T-P se evaluó y pasó»
  los aplica decision. T-P queda «no_evaluable» en los años-régimen sin sus condiciones; las de año
  (K = {H}, E3p compatible) las pone decision.
- ``guardas()`` y ``marcas()`` reciben ``metricas`` con las claves METRICAS_E3 (ESQUEMA_METRICAS_E3, Ts y
  QFE), METRICAS_E4 (ESQUEMA_METRICAS_E4, Ts y HR) y FILTRO_E3T (lineas_fisicas.filtro_representatividad).
  Si falta una clave o una variable, se calcula aquí con lineas_fisicas. Las guardas y marcas que no están
  en ``ctx.lineas_activas`` no se calculan (decision las ve no_evaluable).

Lecturas propias de este módulo (van al addendum de C1):
- GU-1. Pares de E3d (L, L − 24 h) y de P7 (L, L + 1 h): ambas etiquetas con dato, fuera de las etiquetas
  especiales y de las astillas (R-24, R-08), en el mismo año y en el mismo año-régimen; así no cruzan un
  cambio de hora (§3.5). No se exige la misma parte: un borde de mes no corta el par.
- GU-2. E3d: un par exige Δ24x finito para los tres k; el bloque es el de la hora de etiqueta de L;
  r_B(k) es la correlación de Pearson de los pares del bloque. Un bloque con ≥ E3D_PARES_BLOQUE pares es
  informativo si r_B(0) y alguno de r_B(±24) están definidos. No exige paso nativo válido (Δ24 no usa p).
  Ts exige z_cat legible y |Δz| ≤ E3D_DZ_TS_M; ambas variables, coordenadas válidas y consistentes y
  píxel. Resultado del año: falla si falla algún bloque informativo de Ts o de QFE; pasa si hay alguno
  informativo y ninguno falla; si no, no_evaluable.
- GU-3 [Enmienda 5, E5-2]. P7: la presencia de la etiqueta h es la fracción de los días del año con algún Ts
  que traen Ts en h. m_h y r_h usan todos los pares (L, L + 1 h) con L a la hora h (el texto no fija un mínimo
  de pares; r_h exige 3, como numerico.pearson). Si un vecino no tiene pares se usa el otro; sin ninguno, esa h
  no se juzga. Por E5-2, en una estación con referencia (``p7_con_referencia``: no costera por §3.3, también en
  C3c, y con las condiciones de E3d en Ts) P7 da una fila por H de P, como E3d; la referencia x(L) =
  t2m(u_H(L)) del píxel enlazado usa los mismos pares, con x finito en los dos extremos; s_h^x vale 1 si su
  denominador es 0, y s_h^x = 1 y d_h^x = 0 si no están definidos. Sin referencia, P7 da una sola fila con
  H = «*», la de antes de la Enmienda 5, que vale para todas las H. La referencia sólo se calcula en los años
  en que la P7 sin referencia falla: con s_h^x ≥ 1 y d_h^x ≥ 0, la de E5-2 no puede fallar donde aquélla pasa
  o no es evaluable, y allí cada H lleva esa misma fila. Las condiciones son las de la estación, no si E3d
  está entre las líneas activas: en C4, en C3 y en la batería, P7 y E3d van siempre juntas.
- GU-4. T-P: un año-régimen es evaluable con el filtro de §4.3.3 aprobado (tabla del filtro o, sin ella,
  la columna ``filtro_e3t`` de las métricas), ≥ E3_PARES_REGIMEN pares y ĉt_cont definido (R-46). Un
  r_t(c) fuera de la ventana no cuenta. δt es la mediana de los δt_R de los años-régimen evaluables.
- GU-5. E4t: filas de Ts de ``lineas_fisicas.ajustes_e4`` al nivel de año-régimen, sin otros mínimos que
  A1 y A1/EE (n_h y el hueco son de E4p). Con paso de 6 h el ajuste ya trae K = 1 (n_h ≤ 4).
- GU-6. G-versión:
  a. las versiones son los ``script_sha256`` de los meses que entran; la guarda se aplica en el año si
     ≥ GVER_MIN_VERSIONES versiones tienen ≥ GVER_MESES meses;
  b. **la comparación se hace dentro de cada año-régimen**: ĉ de E3p con los pares de las partes de la
     versión en ese año-régimen y j* de E2 con sus partes válidas en él. Comparar entre regímenes haría
     fallar a toda estación civil cuyas versiones caen en regímenes distintos (C(Santiago) da ĉ −3 y −4 y
     clases 0 y 2). Va al addendum de C1 como lectura;
  c. ĉ: máximo estricto de r(c) agregado, estable si es el mismo en ≥ GVER_ESTAB de E3_REPLICAS réplicas
     por bloques de E3_DIAS_BLOQUE días, contados desde el primer día calendario de la primera parte de la
     unidad (R-42). Semilla con unidad «V-<sha8>» y variable «QFE» (R-40): las dos unidades de una versión
     que cruza los dos regímenes comparten semilla;
  d. j*: el de E2 (lineas_registro.e2 sobre los meses de la versión), definido y con κ3 ≥ GVER_KAPPA;
  e. no se exigen otros mínimos (pares, máx r, marcas) que los que nombra el texto;
  f. falla si en algún año-régimen dos versiones comparables difieren en ĉ o en j*; pasa si hubo alguna
     comparación y ninguna difiere; si no, no_evaluable.
- GU-7. G-HR: por año-régimen con los ajustes de E4 de Ts y HR (hora solar de etiqueta: la diferencia de
  fases es la misma que en hora de etiqueta, porque λ/15 y la EoT del día son comunes a ambas); las
  ≥ GHR_HORAS horas con Ts y HR se cuentan en el año; el año lleva la marca si algún año-régimen evaluable
  da distancia > GHR_DIST_H (como R-36). No depende de H. A1(HR) usa U.f("GHR_A1_HR") (punto 1 de las
  ambigüedades de umbrales); A1(Ts) y A1/EE, la constante GHR_A1_TS_Y_EE.
- GU-8. G-viento: u = −ff·sen(dd) y v = −ff·cos(dd) (dd es la dirección de procedencia), en nudos (la
  correlación no depende de la escala). Las primeras diferencias siguen la regla de pares de E3
  (lineas_fisicas.pares_e3: misma parte, paso nativo del mes, Δx finito en toda la ventana), con u10 o v10
  en lugar de t2m. r̄(c) = (r_u(c) + r_v(c))/2; ĉw es su máximo estricto; «no alias de 12 h» es respecto de
  c_H(R). Se evalúa por año-régimen (R-36) y por H; las ≥ GVIENTO_HORAS horas con viento se cuentan en el año.
- GU-9. Las hipótesis Cv (diagnóstico de reglas vencidas) no tienen desfase por régimen: las guardas y
  marcas que dependen de H no las evalúan. El diagnóstico aplica sólo los pasos 2 a 4 (E1-4), y G-versión
  no depende de H.
- GU-10. T-P compara δt_R con el D_R de la H evaluada, sin descontar una fase térmica común a la red: el texto no
  prevé esa corrección. Bajo F(0), D_R = {−3, −4}, así que T-P falla con δt_R entre −4,75 y −2,25 h: con k = −3
  de −3,75 a −2,25 h y con k = −4 de −4,75 a −3,25 h, si además r_t sube ≥ TP_MARGEN. Con TP_VENTANA = 1,0 (su
  lista de §8.F) la banda va de −5,0 a −2,0 h. Un corrimiento así entre Ts y t2m (el sesgo de referencia de +2,5 h
  o el desfase físico de la estación de −2,5 h, los dos de §8.D2) deja discrepantes los años F(0). Bajo F(−3),
  F(−4) y C(Santiago), D_R es {+3} o {+4}: con δt_R < 0 sólo queda la marca térmica. Con δt_R > 0 la banda
  vulnerable es de +2,25 a +3,75 h para F(−3) y el R0 de C(Santiago) (k = +3), y de +3,25 a +4,75 h para F(−4) y
  el R1 de C(Santiago) (k = +4). Es una propiedad del texto (E3-3 de PROPUESTA_ENMIENDA_3.md), que la Enmienda 3
  no cambia (decisión del autor del 2026-10-24). Esas pérdidas de D2 no cuentan en el 90 % de confirmación
  correcta porque la frase de §8.D, enmendada (BAT-5 en bateria), pide sin otra perturbación que el sesgo de la
  referencia y a ≤ 50° S: el desfase físico de −2,5 h queda fuera. Lo fijan
  test_guardas.test_tp_falla_en_f0_con_fase_termica_corrida_2_5h_texto_anclado y
  test_guardas.test_tp_banda_de_f0_llega_a_k_menos4_texto_anclado.
- ERR-2 [errata E-2 de la Enmienda 5]. Los dos «≥» del salto de P7 (m_h ≥ 2·máx(…) y m_h ≥ 1,5 °C, §4.7) se
  comparan con la tolerancia EMPATE_P7_C (1e-9 °C), también en la P7 de E5-2. Con Ts en décimas, la coma
  flotante resolvía contra el «≥» los empates exactos: m_08 = 3,4 = 2·1,7 se comparaba como 3,4000000000000004
  contra 3,4000000000000021, y el año pasaba. La caída (r_h < …) es estricta y no lleva tolerancia.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from reloj_dmc import constantes, lineas_fisicas, lineas_registro, numerico, tablas
from reloj_dmc.tipos import (ESQUEMA_GUARDAS, ESQUEMA_MARCAS, ESQUEMA_METRICAS_E3, ESQUEMA_METRICAS_E4,
                             ContextoEstacion, Hipotesis, Linea, MotivoSinInfo, Nivel, Regimen, ResultadoGuarda,
                             SerieEra5, tabla_vacia, validar_esquema)

_c = constantes.valor

H_TODAS = "*"                                           # guarda o marca que no depende de H
MARCA_DESFASE_TERMICO_LOCAL = "desfase_termico_local"   # §4.7, T-P (la misma cadena que lee decision)
MARCA_G_HR = str(Linea.G_HR)
MARCA_G_VIENTO = str(Linea.G_VIENTO)

# Claves de ``metricas`` en guardas() y marcas().
METRICAS_E3 = "e3"
METRICAS_E4 = "e4"
FILTRO_E3T = "filtro_e3t"

COLUMNAS_RESUMEN_VERSION = ("codigo", "anio", "version", "regimen", "n_meses", "n_pares", "c_hat", "estab_c_hat",
                            "n_rr", "j_estrella", "kappa3")
_TIPOS_RESUMEN_VERSION = {"codigo": "string", "anio": "int16", "version": "string", "regimen": "string",
                          "n_meses": "int16", "n_pares": "int32", "c_hat": "Int8", "estab_c_hat": "float64",
                          "n_rr": "int32", "j_estrella": "Int8", "kappa3": "float64"}

_HORAS_DIA = 24
_UNA_HORA = np.timedelta64(1, "h")
_LARGO_SHA_VERSION = 8  # no-umbral: largo de la abreviatura «V-<sha8>» de la unidad de semilla (R-40)
_VARIABLE_SEMILLA = "QFE"                               # el ĉ de G-versión es el de E3p
_SIN_COORDENADAS = str(MotivoSinInfo.COORDENADAS)
_SIN_PIXEL = str(MotivoSinInfo.SIN_PIXEL)
_SIN_DESNIVEL = str(MotivoSinInfo.SIN_DESNIVEL)
_DESNIVEL = "desnivel"
# ERR-2 (errata E-2 de la Enmienda 5): los «≥» del salto de P7 se cumplen en los empates exactos de Ts en décimas
# (3,4 = 2·1,7 se calculaba 3,4000000000000004 < 3,4000000000000021).
EMPATE_P7_C = 1e-9  # no-umbral: tolerancia de coma flotante para el «≥» de §4.7, en °C

# E3d: (variable, columna del extracto, variable ERA5-Land).
_VARIABLES_E3D = (("Ts", "ts", "t2m"), ("QFE", "qfe", "sp"))


# ---------------------------------------------------------------------------------------------
# Utilidades comunes
# ---------------------------------------------------------------------------------------------
def _exigir(extracto: pd.DataFrame, columnas: Sequence[str], quien: str) -> None:
    faltan = [c for c in columnas if c not in extracto.columns]
    if faltan:
        raise ValueError(f"{quien}: el extracto anotado no trae {faltan}")


def _columna(extracto: pd.DataFrame, nombre: str) -> np.ndarray:
    return extracto[nombre].to_numpy(dtype=np.float64, na_value=np.nan)


def _horas_td(n) -> np.ndarray:
    return np.asarray(n, dtype=np.int64).astype("timedelta64[h]")


def _nulo(v) -> bool:
    return v is None or (not isinstance(v, (list, tuple, np.ndarray)) and pd.isna(v))


def _hipotesis(ctx: ContextoEstacion) -> tuple[Hipotesis, ...]:
    """H de P con desfase por régimen (sin Cv; GU-9), en el orden de P."""
    return tuple(h for h in ctx.info.P if h.tipo in ("F", "C"))


def _coordenadas_y_pixel(ctx: ContextoEstacion, serie: SerieEra5 | None) -> str | None:
    """Motivo de estación que impide comparar con ERA5-Land (§3.1, §3.3); None si se puede."""
    info = ctx.info
    if (not info.coordenadas_validas or info.coordenadas_inconsistentes or info.lat is None
            or info.lon is None):
        return _SIN_COORDENADAS
    if info.pixel_id is None or serie is None or not serie.tiene(int(info.pixel_id)):
        return _SIN_PIXEL
    return None


@dataclass
class _Serie:
    """Etiquetas de una variable con dato, fuera de especiales y astillas, ordenadas por L."""
    L: np.ndarray            # datetime64[ns]
    y: np.ndarray            # float64
    anio: np.ndarray         # int64
    regimen: np.ndarray      # object (str)
    hora: np.ndarray         # int64: hora de etiqueta


def _serie(extracto: pd.DataFrame, valores: np.ndarray) -> _Serie:
    L = extracto["L"].to_numpy(dtype="datetime64[ns]")
    if np.isnat(L).any():
        raise ValueError("L con valores nulos")
    especial = extracto["especial"].to_numpy(dtype=bool)
    regimen = extracto["regimen"].to_numpy(dtype=object, na_value=None)
    y = np.asarray(valores, dtype=np.float64)
    ok = np.isfinite(y) & ~especial & (regimen != None)    # noqa: E711 (arreglo de objetos)
    filas = np.flatnonzero(ok)
    orden = filas[np.argsort(L[filas], kind="stable")]
    Lo = L[orden]
    if np.unique(Lo).size != Lo.size:
        raise ValueError("etiquetas repetidas en el extracto")
    idx = pd.DatetimeIndex(Lo)
    return _Serie(Lo, y[orden], idx.year.to_numpy().astype(np.int64), regimen[orden],
                  idx.hour.to_numpy().astype(np.int64))


def _vecino(s: _Serie, horas: int) -> np.ndarray:
    """Para cada fila, la fila de L + ``horas`` h con dato en el mismo año y año-régimen; −1 si no hay (GU-1)."""
    n = len(s.L)
    if n == 0:
        return np.empty(0, dtype=np.int64)
    objetivo = s.L + np.timedelta64(int(horas), "h")
    j = np.searchsorted(s.L, objetivo)
    jj = np.minimum(j, n - 1)
    ok = (j < n) & (s.L[jj] == objetivo) & (s.anio[jj] == s.anio) & (s.regimen[jj] == s.regimen)
    return np.where(ok, jj, -1).astype(np.int64)


class _Desfases:
    """c_H(R) de las H de P por año-régimen (tablas.desfase), con memoria."""

    def __init__(self, ctx: ContextoEstacion):
        self.ctx = ctx
        self.zs = tuple(ctx.info.zs)
        self._regs: dict[int, dict[str, Regimen]] = {}

    def regimenes(self, anio: int) -> dict[str, Regimen]:
        if anio not in self._regs:
            regs = (self.ctx.regimenes or {}).get(anio) or tablas.regimenes_del_anio(self.zs, anio, self.ctx.tablas)
            self._regs[anio] = {r.id: r for r in regs}
        return self._regs[anio]

    def de(self, h: Hipotesis, anio: int, regimen: str) -> int:
        return tablas.desfase(h, self.regimenes(int(anio))[regimen], self.zs)

    def por_fila(self, h: Hipotesis, anio: int, regimenes: np.ndarray) -> np.ndarray:
        c = np.zeros(len(regimenes), dtype=np.int64)
        for reg in set(regimenes.tolist()):
            c[regimenes == reg] = self.de(h, anio, reg)
        return c


def _regimenes(ctx: ContextoEstacion, anio: int, extra: Sequence[str] = ()) -> tuple[str, ...]:
    """Años-régimen con datos del año (ctx) más los que traigan las métricas."""
    return tuple(sorted(set((ctx.regimenes_con_datos or {}).get(anio, ())) | {str(r) for r in extra}))


def _fila_guarda(ctx: ContextoEstacion, anio: int, guarda: Linea, H: str, unidad: str,
                 resultado: ResultadoGuarda, detalle: str | None) -> dict:
    return {"codigo": ctx.info.codigo, "anio": int(anio), "guarda": str(guarda), "H": H, "unidad": unidad,
            "resultado": str(resultado), "detalle": detalle}


def _fila_marca(ctx: ContextoEstacion, anio: int, marca: str, H: str, valor) -> dict:
    return {"codigo": ctx.info.codigo, "anio": int(anio), "marca": marca, "H": H, "valor": valor}


def _tabla(filas: list[dict], esquema: Mapping[str, str], nombre: str) -> pd.DataFrame:
    if not filas:
        return tabla_vacia(esquema)
    df = pd.DataFrame(filas, columns=list(esquema)).astype(esquema)
    if "valor" in esquema:                       # None y NaN quedan tal cual (decision los lee como sin valor)
        df["valor"] = pd.Series([f["valor"] for f in filas], dtype="object")
    validar_esquema(df, esquema, nombre=nombre)
    return df


def _unir(marcos: list[pd.DataFrame], esquema: Mapping[str, str], nombre: str) -> pd.DataFrame:
    marcos = [m for m in marcos if len(m)]
    if not marcos:
        return tabla_vacia(esquema)
    df = pd.concat(marcos, ignore_index=True).astype(esquema)
    validar_esquema(df, esquema, nombre=nombre)
    return df


def _de_regimen(metricas: pd.DataFrame | None, variable: str, esquema: Mapping[str, str]) -> pd.DataFrame:
    """Filas de una variable al nivel de año-régimen."""
    if metricas is None or not len(metricas):
        return tabla_vacia(esquema)
    return metricas[(metricas["variable"] == variable) & (metricas["nivel"] == str(Nivel.REGIMEN))]


def _por_unidad(m: pd.DataFrame) -> dict[tuple[int, str], pd.Series]:
    salida = {}
    for _, fila in m.iterrows():
        clave = (int(fila["anio"]), str(fila["unidad"]))
        if clave in salida:
            raise ValueError(f"métricas repetidas para {clave}")
        salida[clave] = fila
    return salida


def _x(v: float) -> str:
    return "nan" if v is None or not np.isfinite(v) else f"{v:+.3f}"


# ---------------------------------------------------------------------------------------------
# E3d, fecha corrida (§4.7)
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class _BloqueE3d:
    texto: str
    n: int
    r: tuple[float, ...]         # r_B(k) en el orden de E3D_K
    informativo: bool
    diferencia: float            # máx(r_B(−24), r_B(+24)) − r_B(0)
    falla: bool


def _motivo_e3d(ctx: ContextoEstacion, serie: SerieEra5 | None, variable: str) -> str | None:
    motivo = _coordenadas_y_pixel(ctx, serie)
    if motivo is not None or variable != "Ts":
        return motivo
    dz = ctx.info.dz
    if dz is None or not np.isfinite(dz):
        return _SIN_DESNIVEL                     # §3.3: sin z_cat, E3d en Ts queda sin información
    if abs(dz) > ctx.umbrales.f("E3D_DZ_TS_M"):
        return _DESNIVEL
    return None


def _bloques_e3d(dy: np.ndarray, dx_por_k: Sequence[np.ndarray], hora: np.ndarray, U) -> list[_BloqueE3d]:
    ks = tuple(int(k) for k in _c("E3D_K"))
    i0 = ks.index(0)
    salida = []
    for desde, hasta in _c("E3D_BLOQUES"):
        sel = (hora >= desde) & (hora <= hasta)
        n = int(sel.sum())
        r = tuple(numerico.pearson(dx[sel], dy[sel]) for dx in dx_por_k)
        otros = np.array([v for i, v in enumerate(r) if i != i0], dtype=np.float64)
        informativo = bool(n >= U.f("E3D_PARES_BLOQUE") and np.isfinite(r[i0]) and np.isfinite(otros).any())
        diferencia = float(np.nanmax(otros) - r[i0]) if informativo else float("nan")
        falla = bool(informativo and diferencia >= U.f("E3D_MARGEN"))
        salida.append(_BloqueE3d(f"{desde:02d}-{hasta:02d}", n, r, informativo, diferencia, falla))
    return salida


def _e3d_variable(s: _Serie, i: np.ndarray, j: np.ndarray, c_filas: np.ndarray, serie: SerieEra5, pixel: int,
                  var_era5: str, U) -> list[_BloqueE3d]:
    """r_B(k) entre Δ24y(L) y Δ24x(u_H(L) + k), con u_H(L) = L − c_H(R)."""
    dy = s.y[i] - s.y[j]
    u = s.L[i] - _horas_td(c_filas)
    dx = []
    for k in _c("E3D_K"):
        a = u + np.timedelta64(int(k), "h")
        b = a - np.timedelta64(_HORAS_DIA, "h")
        xa = np.asarray(serie.valores(pixel, var_era5, a), dtype=np.float64)
        xb = np.asarray(serie.valores(pixel, var_era5, b), dtype=np.float64)
        dx.append(xa - xb)
    dx = np.vstack(dx) if dx else np.empty((0, 0))
    ok = np.isfinite(dy) & np.isfinite(dx).all(axis=0)
    return _bloques_e3d(dy[ok], [d[ok] for d in dx], s.hora[i][ok], U)


def _texto_e3d(variable: str, motivo: str | None, bloques: list[_BloqueE3d] | None) -> str:
    if motivo is not None:
        return f"{variable}: {motivo}"
    informativos = [b for b in bloques or [] if b.informativo]
    if not informativos:
        return f"{variable}: sin bloques informativos"
    return f"{variable}: " + ", ".join(f"{b.texto} n={b.n} Δr={_x(b.diferencia)}{' falla' if b.falla else ''}"
                                       for b in informativos)


def e3d(extracto: pd.DataFrame, serie: SerieEra5 | None, ctx: ContextoEstacion) -> pd.DataFrame:
    """Fecha corrida, por año y H: en Ts (|Δz| ≤ 1.000 m) y en QFE (con píxel), bloques 00-05 … 18-23,
    r_B(k) de Δ24y(L) con Δ24x(u_H(L) + k), k ∈ {−24, 0, +24}; bloque informativo con ≥ 100 pares;
    falla si máx(r_B(−24), r_B(+24)) − r_B(0) ≥ 0,10 en algún bloque informativo (GU-1, GU-2)."""
    _exigir(extracto, ("L", "especial", "regimen", "ts", "qfe"), "E3d")
    U = ctx.umbrales
    des = _Desfases(ctx)
    motivos = {v: _motivo_e3d(ctx, serie, v) for v, _, _ in _VARIABLES_E3D}
    bases = {}
    for variable, columna, var_era5 in _VARIABLES_E3D:
        if motivos[variable] is None:
            s = _serie(extracto, _columna(extracto, columna))
            bases[variable] = (s, _vecino(s, -_HORAS_DIA), var_era5)
    pixel = None if ctx.info.pixel_id is None else int(ctx.info.pixel_id)
    filas = []
    for anio in ctx.anios:
        memoria: dict[tuple, tuple[ResultadoGuarda, str]] = {}
        for h in _hipotesis(ctx):
            por_variable = []
            clave = []
            for variable, _, _ in _VARIABLES_E3D:
                if variable not in bases:
                    por_variable.append((variable, None, None))
                    continue
                s, j_ant, var_era5 = bases[variable]
                i = np.flatnonzero((s.anio == anio) & (j_ant >= 0))
                c_filas = des.por_fila(h, anio, s.regimen[i])
                clave.append((variable, tuple(sorted({(r, int(c)) for r, c in zip(s.regimen[i].tolist(), c_filas)}))))
                por_variable.append((variable, i, c_filas))
            clave = tuple(clave)
            if clave not in memoria:
                informativo, falla, textos = False, False, []
                for variable, i, c_filas in por_variable:
                    if i is None:
                        textos.append(_texto_e3d(variable, motivos[variable], None))
                        continue
                    s, j_ant, var_era5 = bases[variable]
                    bloques = _e3d_variable(s, i, j_ant[i], c_filas, serie, pixel, var_era5, U)
                    informativo |= any(b.informativo for b in bloques)
                    falla |= any(b.falla for b in bloques)
                    textos.append(_texto_e3d(variable, None, bloques))
                resultado = (ResultadoGuarda.FALLA if falla else
                             ResultadoGuarda.PASA if informativo else ResultadoGuarda.NO_EVALUABLE)
                memoria[clave] = (resultado, "; ".join(textos))
            resultado, detalle = memoria[clave]
            filas.append(_fila_guarda(ctx, anio, Linea.E3D, h.id, f"{int(anio):04d}", resultado, detalle))
    return _tabla(filas, ESQUEMA_GUARDAS, "guardas E3d")


# ---------------------------------------------------------------------------------------------
# P7, continuidad (§4.7)
# ---------------------------------------------------------------------------------------------
def _vecinos_p7(h: int) -> list[int]:
    return [(h - 1) % _HORAS_DIA, (h + 1) % _HORAS_DIA]


def _perfil_p7(y: np.ndarray, i: np.ndarray, j: np.ndarray, hora: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """m_h (mediana de |y(L + 1 h) − y(L)|) y r_h (Pearson de y(L) con y(L + 1 h)) de los pares (i, j) con L a la
    hora h; NaN donde no hay pares (r_h exige PEARSON_MIN_PARES)."""
    m = np.full(_HORAS_DIA, np.nan)
    r = np.full(_HORAS_DIA, np.nan)
    for h in range(_HORAS_DIA):
        sel = hora == h
        if sel.any():
            a, b = y[i[sel]], y[j[sel]]
            m[h] = float(np.median(np.abs(b - a)))
            r[h] = numerico.pearson(a, b)
    return m, r


def _referencia_p7(mx: np.ndarray, rx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """E5-2 (GU-3): s_h^x = m_h^x / máx(m_{h−1}^x, m_{h+1}^x) y d_h^x = mín(r_{h−1}^x, r_{h+1}^x) − r_h^x. Si no
    están definidos, o si el denominador de s_h^x es 0, valen 1 y 0: la P7 anterior a la Enmienda 5."""
    s_x = np.ones(_HORAS_DIA)
    d_x = np.zeros(_HORAS_DIA)
    for h in range(_HORAS_DIA):
        mv, rv = mx[_vecinos_p7(h)], rx[_vecinos_p7(h)]
        if np.isfinite(mx[h]) and np.isfinite(mv).any() and np.nanmax(mv) > 0:
            s_x[h] = mx[h] / np.nanmax(mv)
        if np.isfinite(rx[h]) and np.isfinite(rv).any():
            d_x[h] = np.nanmin(rv) - rx[h]
    return s_x, d_x


def _fallas_p7(m: np.ndarray, r: np.ndarray, U, s_x: np.ndarray | None = None,
               d_x: np.ndarray | None = None) -> list[str]:
    """§4.7: la h falla con m_h ≥ 2·máx(1, s_h^x)·máx(m_{h−1}, m_{h+1}) y m_h ≥ 1,5 °C, o con r_h < mín(r_{h−1},
    r_{h+1}) − 0,20 − máx(0, d_h^x). Sin referencia, s_h^x = 1 y d_h^x = 0. Los «≥» del salto se cumplen también en
    los empates exactos de valores en décimas (ERR-2): se comparan con la tolerancia EMPATE_P7_C."""
    con_referencia = s_x is not None
    s_x = np.ones(_HORAS_DIA) if s_x is None else s_x
    d_x = np.zeros(_HORAS_DIA) if d_x is None else d_x
    fallas = []
    for h in range(_HORAS_DIA):
        mv, rv = m[_vecinos_p7(h)], r[_vecinos_p7(h)]
        factor = U.f("P7_FACTOR") * max(1.0, float(s_x[h]))
        salto = bool(np.isfinite(m[h]) and np.isfinite(mv).any()
                     and m[h] >= factor * np.nanmax(mv) - EMPATE_P7_C and m[h] >= U.f("P7_SALTO_C") - EMPATE_P7_C)
        caida = bool(np.isfinite(r[h]) and np.isfinite(rv).any()
                     and r[h] < np.nanmin(rv) - U.f("P7_CAIDA") - max(0.0, float(d_x[h])))
        if salto or caida:
            ref = f", s^x={s_x[h]:.2f}, d^x={d_x[h]:+.3f}" if con_referencia else ""
            fallas.append(f"{h:02d} h ({'salto' if salto else ''}{'+' if salto and caida else ''}"
                          f"{'caída' if caida else ''}: m={m[h]:.2f}, r={r[h]:.3f}{ref})")
    return fallas


def _pares_p7(s: _Serie, j_sig: np.ndarray, anio: int) -> tuple[np.ndarray, np.ndarray]:
    i = np.flatnonzero((s.anio == anio) & (j_sig >= 0))
    return i, j_sig[i]


def _p7_anio(s: _Serie, j_sig: np.ndarray, anio: int, U) -> tuple[ResultadoGuarda, str]:
    """P7 sin referencia (la anterior a la Enmienda 5, con ERR-2): presencia y m_h, r_h del año."""
    en = s.anio == anio
    dias = s.L[en].astype("datetime64[D]")
    n_dias = int(np.unique(dias).size)
    if n_dias == 0:
        return ResultadoGuarda.NO_EVALUABLE, "sin Ts"
    hora_en = s.hora[en]
    presencia = np.array([np.unique(dias[hora_en == h]).size / n_dias for h in range(_HORAS_DIA)])
    n_etiquetas = int((presencia >= _c("P7_PRESENCIA")).sum())
    if n_etiquetas < U.f("P7_ETIQUETAS"):
        return ResultadoGuarda.NO_EVALUABLE, f"{n_etiquetas} etiquetas con presencia ≥ {_c('P7_PRESENCIA')}"
    i, j = _pares_p7(s, j_sig, anio)
    fallas = _fallas_p7(*_perfil_p7(s.y, i, j, s.hora[i]), U)
    if fallas:
        return ResultadoGuarda.FALLA, "; ".join(fallas)
    return ResultadoGuarda.PASA, f"{n_etiquetas} etiquetas con presencia suficiente"


def p7_con_referencia(ctx: ContextoEstacion, serie: SerieEra5 | None) -> bool:
    """E5-2: P7 se compara con ERA5-Land sólo en una estación no costera que cumple las condiciones de E3d en Ts
    (coordenadas válidas y consistentes, píxel con serie, z_cat legible y |Δz| ≤ E3D_DZ_TS_M). La condición
    «no costera» es la de §3.3 (``info.costera``), también donde no se aplica la exclusión de E3t y T-P (C3c)."""
    return serie is not None and not bool(ctx.info.costera) and _motivo_e3d(ctx, serie, "Ts") is None


def _p7_relativa(s: _Serie, j_sig: np.ndarray, anio: int, h: Hipotesis, des: _Desfases, serie: SerieEra5,
                 pixel: int, U) -> list[str]:
    """E5-2: las fallas de P7 bajo H, con la referencia x(L) = t2m(u_H(L)) del píxel en los mismos pares (L, L + 1 h),
    con x finito en los dos extremos (GU-3)."""
    i, j = _pares_p7(s, j_sig, anio)
    m, r = _perfil_p7(s.y, i, j, s.hora[i])
    filas = np.unique(np.concatenate([i, j]))
    x = np.full(len(s.y), np.nan)
    if len(filas):
        u = s.L[filas] - _horas_td(des.por_fila(h, anio, s.regimen[filas]))
        x[filas] = np.asarray(serie.valores(pixel, "t2m", u), dtype=np.float64)
    ok = np.isfinite(x[i]) & np.isfinite(x[j])
    s_x, d_x = _referencia_p7(*_perfil_p7(x, i[ok], j[ok], s.hora[i][ok]))
    return _fallas_p7(m, r, U, s_x, d_x)


def p7(extracto: pd.DataFrame, ctx: ContextoEstacion, serie: SerieEra5 | None = None) -> pd.DataFrame:
    """Continuidad, por año: estaciones con ≥ 22 etiquetas de presencia ≥ 0,8; m_h y r_h circulares (23 h contra
    00 h del día siguiente); falla por salto o por caída (GU-1, GU-3, ERR-2).

    Enmienda 5, E5-2: con ``serie`` y en una estación con referencia (``p7_con_referencia``), una fila por H de P,
    con el salto y la caída relativos a los de ERA5-Land bajo esa H. Sin referencia, una sola fila con H = «*»,
    la P7 anterior a la Enmienda 5, que vale para todas las H. La referencia sólo se calcula en los años en que
    la P7 sin referencia falla: con s_h^x ≥ 1 y d_h^x ≥ 0 la de E5-2 no puede fallar donde aquélla pasa o no es
    evaluable, y allí la fila de cada H es la suya (GU-3)."""
    _exigir(extracto, ("L", "especial", "regimen", "ts"), "P7")
    U = ctx.umbrales
    s = _serie(extracto, _columna(extracto, "ts"))
    j_sig = _vecino(s, 1)
    referencia = p7_con_referencia(ctx, serie)
    hipotesis = _hipotesis(ctx) if referencia else ()
    referencia = bool(hipotesis)
    des = _Desfases(ctx) if referencia else None
    pixel = int(ctx.info.pixel_id) if referencia else None
    filas = []
    for anio in ctx.anios:
        unidad = f"{int(anio):04d}"
        resultado, detalle = _p7_anio(s, j_sig, int(anio), U)
        if not referencia:
            filas.append(_fila_guarda(ctx, anio, Linea.P7, H_TODAS, unidad, resultado, detalle))
            continue
        memoria: dict[tuple, tuple[ResultadoGuarda, str]] = {}
        for h in hipotesis:
            if resultado != ResultadoGuarda.FALLA:
                filas.append(_fila_guarda(ctx, anio, Linea.P7, h.id, unidad, resultado, detalle))
                continue
            regs = des.regimenes(int(anio))
            clave = tuple(sorted((reg, des.de(h, int(anio), reg)) for reg in regs))
            if clave not in memoria:
                fallas = _p7_relativa(s, j_sig, int(anio), h, des, serie, pixel, U)
                memoria[clave] = ((ResultadoGuarda.FALLA, "relativa a ERA5-Land: " + "; ".join(fallas)) if fallas
                                  else (ResultadoGuarda.PASA, f"relativa a ERA5-Land: pasa (sin referencia: {detalle})"))
            filas.append(_fila_guarda(ctx, anio, Linea.P7, h.id, unidad, *memoria[clave]))
    return _tabla(filas, ESQUEMA_GUARDAS, "guardas P7")


# ---------------------------------------------------------------------------------------------
# T-P, Ts y QFE en el mismo reloj, y marca «desfase térmico local» (§4.7)
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class _EvalTP:
    resultado: ResultadoGuarda
    delta: float | None          # δt_R = ĉt_cont − c_H(R) en un año-régimen evaluable
    detalle: str


def _filtro_pasa(filtro: pd.DataFrame | None, fila: pd.Series, anio: int, regimen: str) -> bool:
    if filtro is None:
        return bool(fila["filtro_e3t"])
    f = filtro[(filtro["anio"] == anio) & (filtro["regimen"] == regimen)]
    return bool(f["pasa"].iloc[0]) if len(f) else False


def _evaluar_tp(fila: pd.Series | None, pasa_filtro: bool, c_h: int, desfases_P: Sequence[int],
                vent: tuple[int, ...], U) -> _EvalTP:
    if fila is None:
        return _EvalTP(ResultadoGuarda.NO_EVALUABLE, None, "sin métricas de E3t")
    if not pasa_filtro:
        return _EvalTP(ResultadoGuarda.NO_EVALUABLE, None, str(MotivoSinInfo.FILTRO))
    if int(fila["n_pares"]) < U.f("E3_PARES_REGIMEN"):
        return _EvalTP(ResultadoGuarda.NO_EVALUABLE, None, f"{str(MotivoSinInfo.MINIMOS)}: {int(fila['n_pares'])} pares")
    cc = fila["c_hat_cont"]
    if _nulo(cc) or not np.isfinite(float(cc)):
        return _EvalTP(ResultadoGuarda.NO_EVALUABLE, None, "sin ĉt_cont (R-46)")
    delta = float(cc) - c_h
    D = sorted({c - c_h for c in desfases_P if abs(c - c_h) >= _c("TP_DIST_RIVAL")})
    r = np.full(len(vent), np.nan) if _nulo(fila["r"]) else np.asarray(fila["r"], dtype=np.float64)
    pos = {int(c): n for n, c in enumerate(vent)}
    for k in D:
        if abs(delta - k) > U.a("TP_VENTANA"):
            continue
        a, b = pos.get(c_h + k), pos.get(c_h)
        if a is None or b is None or not (np.isfinite(r[a]) and np.isfinite(r[b])):
            continue
        if r[a] - r[b] >= U.a("TP_MARGEN"):
            return _EvalTP(ResultadoGuarda.FALLA, delta,
                           f"δt_R={delta:+.2f} h; forma de reloj con k={k:+d} (Δr={r[a] - r[b]:+.3f})")
    return _EvalTP(ResultadoGuarda.PASA, delta, f"δt_R={delta:+.2f} h; D_R={D}")


def _tp_y_marca(metricas_e3t: pd.DataFrame | None, filtro_e3t: pd.DataFrame | None,
                ctx: ContextoEstacion) -> tuple[list[dict], list[dict]]:
    U = ctx.umbrales
    vent = numerico.desfases_ventana(U)
    des = _Desfases(ctx)
    hs = _hipotesis(ctx)
    m = _de_regimen(metricas_e3t, "Ts", ESQUEMA_METRICAS_E3)
    por_unidad = _por_unidad(m)
    guardas_, marcas_ = [], []
    for anio in ctx.anios:
        anio = int(anio)
        deltas: dict[str, list[float]] = {h.id: [] for h in hs}
        regs = _regimenes(ctx, anio, [u for a, u in por_unidad if a == anio])
        for reg in regs:
            fila = por_unidad.get((anio, reg))
            pasa = False if fila is None else _filtro_pasa(filtro_e3t, fila, anio, reg)
            desfases = {h.id: des.de(h, anio, reg) for h in hs}
            for h in hs:
                ev = _evaluar_tp(fila, pasa, desfases[h.id], list(desfases.values()), vent, U)
                if ev.delta is not None:
                    deltas[h.id].append(ev.delta)
                guardas_.append(_fila_guarda(ctx, anio, Linea.TP, h.id, reg, ev.resultado, ev.detalle))
        for h in hs:
            valor = float(np.median(deltas[h.id])) if deltas[h.id] else None
            marcas_.append(_fila_marca(ctx, anio, MARCA_DESFASE_TERMICO_LOCAL, h.id, valor))
    return guardas_, marcas_


def tp(metricas_e3t: pd.DataFrame, filtro_e3t: pd.DataFrame | None, ctx: ContextoEstacion) -> pd.DataFrame:
    """Ts y QFE en el mismo reloj, por año-régimen y H, en ambos modos de E3t. Evaluable en años-régimen con
    filtro aprobado, ≥ 1.000 pares y ĉt_cont definido; falla si existe k ∈ D_R con |δt_R − k| ≤ TP_VENTANA
    y r_t(c_H(R) + k) − r_t(c_H(R)) ≥ TP_MARGEN. Las condiciones de año (K = {H}, E3p compatible) las
    aplica decision.py (GU-4). ``metricas_e3t``: ESQUEMA_METRICAS_E3 (se usan las filas de Ts);
    ``filtro_e3t``: lineas_fisicas.filtro_representatividad o None (entonces, la columna ``filtro_e3t``).
    δt (mediana de δt_R) va a la marca de ``desfase_termico_local``."""
    guardas_, _ = _tp_y_marca(metricas_e3t, filtro_e3t, ctx)
    return _tabla(guardas_, ESQUEMA_GUARDAS, "guardas T-P")


def desfase_termico_local(metricas_e3t: pd.DataFrame, filtro_e3t: pd.DataFrame | None,
                          ctx: ContextoEstacion) -> pd.DataFrame:
    """Marca «desfase térmico local» por año y H (ESQUEMA_MARCAS): valor = δt, la mediana de los δt_R de
    los años-régimen evaluables por T-P, o None. decision la aplica si T-P pasó y |δt| > DTL_DELTA_H."""
    _, marcas_ = _tp_y_marca(metricas_e3t, filtro_e3t, ctx)
    return _tabla(marcas_, ESQUEMA_MARCAS, "marca desfase térmico local")


# ---------------------------------------------------------------------------------------------
# E4t, fase térmica gruesa (§4.7, §4.4)
# ---------------------------------------------------------------------------------------------
def _evaluable_a1(fila: pd.Series | None, a1_min: float, a1_ee: float) -> bool:
    if fila is None:
        return False
    a1, ee, phi1 = fila["A1"], fila["EE_A1"], fila["phi1"]
    if _nulo(a1) or _nulo(ee) or _nulo(phi1) or not ee > 0:
        return False
    return bool(a1 >= a1_min and a1 / ee >= a1_ee)


def e4t(metricas_e4_ts: pd.DataFrame, ctx: ContextoEstacion) -> pd.DataFrame:
    """Fase térmica gruesa, por año-régimen y H: evaluable si A1 ≥ 1,0 °C y A1/EE ≥ 3 (con p = 6, K = 1);
    falla si (φ1 − c_H(R)) mód 24 ∉ [10,0; 19,0] h (GU-5). ``metricas_e4_ts``: ajustes_e4 de Ts."""
    U = ctx.umbrales
    des = _Desfases(ctx)
    hs = _hipotesis(ctx)
    por_unidad = _por_unidad(_de_regimen(metricas_e4_ts, "Ts", ESQUEMA_METRICAS_E4))
    desde, hasta = U.f("E4T_VENTANA_DESDE_H"), U.f("E4T_VENTANA_HASTA_H")
    filas = []
    for anio in ctx.anios:
        anio = int(anio)
        for reg in _regimenes(ctx, anio, [u for a, u in por_unidad if a == anio]):
            fila = por_unidad.get((anio, reg))
            evaluable = _evaluable_a1(fila, U.f("E4T_A1_MIN_C"), U.f("E4T_A1_EE"))
            for h in hs:
                if not evaluable:
                    detalle = "sin ajuste de Ts" if fila is None else str(MotivoSinInfo.AMPLITUD)
                    filas.append(_fila_guarda(ctx, anio, Linea.E4T, h.id, reg, ResultadoGuarda.NO_EVALUABLE, detalle))
                    continue
                fase = float(numerico.envolver(float(fila["phi1"]) - des.de(h, anio, reg), 0.0, _HORAS_DIA))
                falla = fase < desde or fase > hasta
                filas.append(_fila_guarda(ctx, anio, Linea.E4T, h.id, reg,
                                          ResultadoGuarda.FALLA if falla else ResultadoGuarda.PASA,
                                          f"(φ1 − c_H) mód 24 = {fase:.2f} h"))
    return _tabla(filas, ESQUEMA_GUARDAS, "guardas E4t")


# ---------------------------------------------------------------------------------------------
# G-versión (§4.7; R-40)
# ---------------------------------------------------------------------------------------------
def _versiones_del_anio(meses: pd.DataFrame | None, ctx: ContextoEstacion) -> dict[int, dict[str, list[int]]]:
    """año → versión (script_sha256) → meses que entran con esa versión."""
    salida: dict[int, dict[str, list[int]]] = {}
    if meses is None or not len(meses):
        return salida
    m = meses[(meses["codigo"] == ctx.info.codigo) & meses["entra"].fillna(False).astype(bool)]
    for anio, mes, version in zip(m["anio"], m["mes"], m["script_sha256"]):
        if _nulo(version):
            continue
        salida.setdefault(int(anio), {}).setdefault(str(version), []).append(int(mes))
    return salida


def _unidad_semilla(version: str) -> str:
    return f"V-{version[:_LARGO_SHA_VERSION].lower()}"


def _primer_dia(ctx: ContextoEstacion, anio: int, meses: Sequence[int], regimen: str) -> date | None:
    """Primer día calendario de la unidad versión × año-régimen: el de su primera parte (R-42)."""
    dias = [tablas.fecha_de(p.desde) for mes in meses
            for p in tablas.partes_del_mes(tuple(ctx.info.zs), anio, mes, ctx.tablas) if p.regimen == regimen]
    return min(dias) if dias else None


def _c_hat_estable(pares: pd.DataFrame, primer_dia: date, semilla_: int, U,
                   vent: tuple[int, ...]) -> tuple[int | None, float]:
    """(ĉ del agregado, fracción de réplicas con el mismo ĉ) (GU-6 c)."""
    cols = list(lineas_fisicas.columnas_dx(U))
    dy = pares["dy"].to_numpy(dtype=np.float64)
    dx = np.ascontiguousarray(pares[cols].to_numpy(dtype=np.float64).T)
    c_hat = numerico.maximo_estricto(numerico.correlaciones_por_desfase(dy, dx), vent)
    if c_hat is None:
        return None, float("nan")
    bloques = numerico.bloques_de_dias(pares["L"].to_numpy(dtype="datetime64[ns]"), primer_dia,
                                       int(U.f("E3_DIAS_BLOQUE")))
    replicas = numerico.replicas_por_bloques(bloques, int(U.f("E3_REPLICAS")), numerico.generador(semilla_))
    iguales = sum(numerico.maximo_estricto(numerico.correlaciones_por_desfase(dy[k], dx[:, k]), vent) == c_hat
                  for k in replicas)
    return int(c_hat), float(iguales / len(replicas)) if replicas else float("nan")


def resumen_por_version(extracto: pd.DataFrame, serie: SerieEra5 | None, meses: pd.DataFrame,
                        ctx: ContextoEstacion) -> pd.DataFrame:
    """Por año, versión admitida con ≥ 2 meses y año-régimen (GU-6): ĉ de E3p agregado de sus partes y su
    estabilidad en las réplicas (unidad de semilla «V-<sha8>», R-40), y j* de E2 con su κ3.
    Sólo en los años con ≥ 2 versiones de ≥ 2 meses. Columnas: COLUMNAS_RESUMEN_VERSION.

    El extracto debe ser el anotado completo (ESQUEMA_EXTRACTO_HORA + ESQUEMA_ANOTACION), porque j* sale
    de lineas_registro.e2 sobre los meses de cada versión."""
    U = ctx.umbrales
    codigo = ctx.info.codigo
    vent = numerico.desfases_ventana(U)
    filas = []
    pares: pd.DataFrame | None = None
    L = extracto["L"].to_numpy(dtype="datetime64[ns]")
    idx = pd.DatetimeIndex(L)
    anio_L, mes_L = idx.year.to_numpy(), idx.month.to_numpy()
    for anio, por_version in sorted(_versiones_del_anio(meses, ctx).items()):
        aplicables = {v: sorted(ms) for v, ms in por_version.items() if len(set(ms)) >= U.f("GVER_MESES")}
        if len(aplicables) < _c("GVER_MIN_VERSIONES"):
            continue
        if pares is None:
            p = lineas_fisicas.pares_e3(extracto, serie, ctx, "QFE") if _coordenadas_y_pixel(ctx, serie) is None \
                else pd.DataFrame(columns=list(lineas_fisicas.COLUMNAS_PARES_BASE))
            pares = p[p["nivel"] == str(Nivel.REGIMEN)].reset_index(drop=True) if len(p) else p
            if len(pares):
                ip = pd.DatetimeIndex(pares["L"])
                pares = pares.assign(_anio=ip.year.to_numpy(), _mes=ip.month.to_numpy())
        for version, meses_v in sorted(aplicables.items()):
            en_version = (anio_L == anio) & np.isin(mes_L, meses_v)
            sub = extracto.loc[en_version].reset_index(drop=True)
            m2 = lineas_registro.e2(sub, ctx).metricas
            m2 = m2[(m2["anio"] == anio) & (m2["nivel"] == str(Nivel.REGIMEN))]
            e2_por_reg = {str(r): f for r, (_, f) in zip(m2["unidad"], m2.iterrows())}
            pv = (pares[(pares["_anio"] == anio) & pares["_mes"].isin(meses_v)]
                  if pares is not None and len(pares) else None)
            regs_e3 = sorted(set(pv["unidad"].astype(str))) if pv is not None else []
            for reg in sorted(set(regs_e3) | set(e2_por_reg)):
                c_hat, estab, n_pares = None, float("nan"), 0
                if pv is not None and reg in regs_e3:
                    pr = pv[pv["unidad"] == reg]
                    n_pares = len(pr)
                    primer = _primer_dia(ctx, anio, meses_v, reg)
                    semilla_ = numerico.semilla(int(U.f("SEMILLA")), codigo, anio, _unidad_semilla(version),
                                                _VARIABLE_SEMILLA)
                    c_hat, estab = _c_hat_estable(pr, primer, semilla_, U, vent)
                f2 = e2_por_reg.get(reg)
                j = None if f2 is None or _nulo(f2["j_estrella"]) else int(f2["j_estrella"])
                filas.append({"codigo": codigo, "anio": anio, "version": version, "regimen": reg,
                              "n_meses": len(set(meses_v)), "n_pares": n_pares, "c_hat": c_hat, "estab_c_hat": estab,
                              "n_rr": 0 if f2 is None else int(f2["n_rr"]), "j_estrella": j,
                              "kappa3": float("nan") if f2 is None or _nulo(f2["kappa3"]) else float(f2["kappa3"])})
    if not filas:
        return pd.DataFrame({c: pd.Series(dtype=t) for c, t in _TIPOS_RESUMEN_VERSION.items()})
    return pd.DataFrame(filas, columns=list(COLUMNAS_RESUMEN_VERSION)).astype(_TIPOS_RESUMEN_VERSION)


def g_version(resumen: pd.DataFrame, ctx: ContextoEstacion) -> pd.DataFrame:
    """Falla en un estación-año con ≥ 2 versiones si, en un mismo año-régimen, sus ĉ estables o sus j*
    (κ3 ≥ 0,95) difieren (GU-6). Una fila por año, con H = «*» y unidad «AAAA»."""
    U = ctx.umbrales
    filas = []
    for anio in ctx.anios:
        anio = int(anio)
        del_anio = resumen[resumen["anio"] == anio] if len(resumen) else resumen
        if not len(del_anio):
            filas.append(_fila_guarda(ctx, anio, Linea.G_VERSION, H_TODAS, f"{anio:04d}", ResultadoGuarda.NO_EVALUABLE,
                                      "menos de 2 versiones con meses suficientes"))
            continue
        comparaciones, diferencias = 0, []
        for reg, f in del_anio.groupby("regimen", sort=True):
            estables = {v: int(c) for v, c, e in zip(f["version"], f["c_hat"], f["estab_c_hat"])
                        if not _nulo(c) and not _nulo(e) and e >= U.f("GVER_ESTAB")}
            clases = {v: int(j) for v, j, k in zip(f["version"], f["j_estrella"], f["kappa3"])
                      if not _nulo(j) and not _nulo(k) and k >= U.f("GVER_KAPPA")}
            for nombre, valores in (("ĉ", estables), ("j*", clases)):
                if len(valores) >= _c("GVER_MIN_VERSIONES"):
                    comparaciones += 1
                    if len(set(valores.values())) > 1:
                        diferencias.append(f"{reg} {nombre}: " + ", ".join(
                            f"{_unidad_semilla(v)}={x:+d}" if nombre == "ĉ" else f"{_unidad_semilla(v)}={x}"
                            for v, x in sorted(valores.items())))
        if diferencias:
            resultado, detalle = ResultadoGuarda.FALLA, "; ".join(diferencias)
        elif comparaciones:
            resultado, detalle = ResultadoGuarda.PASA, f"{comparaciones} comparaciones sin diferencias"
        else:
            resultado, detalle = ResultadoGuarda.NO_EVALUABLE, "sin ĉ estables ni j* comparables entre versiones"
        filas.append(_fila_guarda(ctx, anio, Linea.G_VERSION, H_TODAS, f"{anio:04d}", resultado, detalle))
    return _tabla(filas, ESQUEMA_GUARDAS, "guardas G-versión")


# ---------------------------------------------------------------------------------------------
# G-HR y G-viento (§4.7)
# ---------------------------------------------------------------------------------------------
def _horas_por_anio(extracto: pd.DataFrame, validas: np.ndarray) -> dict[int, int]:
    """Etiquetas del año (fuera de especiales y astillas) donde ``validas`` es verdadero."""
    usa = validas & ~extracto["especial"].to_numpy(dtype=bool) & extracto["regimen"].notna().to_numpy(dtype=bool)
    anios = pd.DatetimeIndex(extracto["L"]).year.to_numpy()[usa]
    valores, cuentas = np.unique(anios, return_counts=True)
    return {int(a): int(n) for a, n in zip(valores, cuentas)}


def g_hr(metricas_e4_ts: pd.DataFrame, metricas_e4_hr: pd.DataFrame, ctx: ContextoEstacion, *,
         extracto: pd.DataFrame) -> pd.DataFrame:
    """Marca «reloj no verificado» en HR y Td si la distancia circular entre φ1(Ts) y φ1(HR) + 12 h > 2,0 h
    (≥ 1.000 horas con Ts y HR en el año; A1(Ts) ≥ 1 °C, A1(HR) ≥ 5 puntos y A1/EE ≥ 3 en ambas), por
    año-régimen (GU-7). Una fila por año con H = «*»; ``extracto`` (anotado) da las horas con Ts y HR."""
    _exigir(extracto, ("L", "especial", "regimen", "ts", "hr"), "G-HR")
    U = ctx.umbrales
    a1_ts, _, a1_ee = _c("GHR_A1_TS_Y_EE")
    a1_hr = U.f("GHR_A1_HR")                      # punto 1 de las ambigüedades de umbrales (COORDINACION_C1)
    horas = _horas_por_anio(extracto, np.isfinite(_columna(extracto, "ts")) & np.isfinite(_columna(extracto, "hr")))
    ts = _por_unidad(_de_regimen(metricas_e4_ts, "Ts", ESQUEMA_METRICAS_E4))
    hr = _por_unidad(_de_regimen(metricas_e4_hr, "HR", ESQUEMA_METRICAS_E4))
    filas = []
    for anio in ctx.anios:
        anio = int(anio)
        valor = None
        if horas.get(anio, 0) >= U.f("GHR_HORAS"):
            for reg in _regimenes(ctx, anio, [u for a, u in ts if a == anio]):
                f_ts, f_hr = ts.get((anio, reg)), hr.get((anio, reg))
                if not (_evaluable_a1(f_ts, a1_ts, a1_ee) and _evaluable_a1(f_hr, a1_hr, a1_ee)):
                    continue
                distancia = numerico.distancia_circular(float(f_ts["phi1"]), float(f_hr["phi1"]) + _HORAS_DIA // 2,
                                                        _HORAS_DIA)
                valor = bool(valor) or bool(distancia > U.f("GHR_DIST_H"))
        filas.append(_fila_marca(ctx, anio, MARCA_G_HR, H_TODAS, valor))
    return _tabla(filas, ESQUEMA_MARCAS, "marcas G-HR")


class _SerieSustituta:
    """Sirve u10 (o v10) donde lineas_fisicas.pares_e3 pide t2m, para usar la regla de pares de E3 (GU-8)."""

    def __init__(self, serie: SerieEra5, variable: str):
        self._serie = serie
        self._variable = variable
        self.t0 = getattr(serie, "t0", None)
        self.n_horas = getattr(serie, "n_horas", None)

    def tiene(self, pixel_id: int) -> bool:
        return self._serie.tiene(pixel_id)

    def valores(self, pixel_id: int, variable: str, u: np.ndarray) -> np.ndarray:
        if variable != lineas_fisicas.VARIABLE_ERA5["Ts"]:
            raise ValueError(f"la serie sustituta sólo sirve la variable de Ts, no {variable!r}")
        return self._serie.valores(pixel_id, self._variable, u)

    def media(self, pixel_id: int, variable: str) -> float:
        return self._serie.media(pixel_id, self._variable)


def _componentes_viento(extracto: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """u = −ff·sen(dd), v = −ff·cos(dd), en nudos; NaN donde el viento no es válido (§3.2)."""
    ff = _columna(extracto, "ff_kt")
    dd = np.deg2rad(_columna(extracto, "dd_grados"))
    valido = extracto["viento_valido"].to_numpy(dtype=bool) & np.isfinite(ff) & np.isfinite(dd)
    u = np.where(valido, -ff * np.sin(dd), np.nan)
    v = np.where(valido, -ff * np.cos(dd), np.nan)
    return u, v


def _r_viento(extracto: pd.DataFrame, componente: np.ndarray, serie: SerieEra5, variable: str,
              ctx: ContextoEstacion) -> dict[tuple[int, str], np.ndarray]:
    """r(c) de las primeras diferencias de una componente contra las de u10 o v10, por año-régimen."""
    w = extracto[["L", "parte", "regimen", "especial"]].copy()
    w[lineas_fisicas.COLUMNA["Ts"]] = componente
    pares = lineas_fisicas.pares_e3(w, _SerieSustituta(serie, variable), ctx, "Ts")
    salida = {}
    if not len(pares):
        return salida
    cols = list(lineas_fisicas.columnas_dx(ctx.umbrales))
    pares = pares[pares["nivel"] == str(Nivel.REGIMEN)]
    for (anio, reg), f in pares.groupby(["anio", "unidad"], sort=True):
        dx = np.ascontiguousarray(f[cols].to_numpy(dtype=np.float64).T)
        salida[(int(anio), str(reg))] = numerico.correlaciones_por_desfase(f["dy"].to_numpy(dtype=np.float64), dx)
    return salida


def g_viento(extracto: pd.DataFrame, serie: SerieEra5 | None, ctx: ContextoEstacion) -> pd.DataFrame:
    """Marca en el viento, por año y H (por año-régimen; R-36): r̄(c) de las primeras diferencias de u y v
    contra u10 y v10; marca si máx r̄ ≥ 0,20, |ĉw − c_H(R)| ≥ 2, no alias y r̄(ĉw) − r̄(c_H(R)) ≥ 0,05 (GU-8)."""
    _exigir(extracto, ("L", "parte", "especial", "regimen", "ff_kt", "dd_grados", "viento_valido"), "G-viento")
    U = ctx.umbrales
    vent = numerico.desfases_ventana(U)
    pos = {int(c): n for n, c in enumerate(vent)}
    des = _Desfases(ctx)
    hs = _hipotesis(ctx)
    u, v = _componentes_viento(extracto)
    con_pixel = _coordenadas_y_pixel(ctx, serie) is None
    horas = _horas_por_anio(extracto, np.isfinite(u) & np.isfinite(v)) if con_pixel else {}
    r_u = _r_viento(extracto, u, serie, "u10", ctx) if con_pixel else {}
    r_v = _r_viento(extracto, v, serie, "v10", ctx) if con_pixel else {}
    filas = []
    for anio in ctx.anios:
        anio = int(anio)
        aplica = horas.get(anio, 0) >= U.f("GVIENTO_HORAS")
        regs = [reg for (a, reg) in sorted(set(r_u) & set(r_v)) if a == anio] if aplica else []
        for h in hs:
            valor = None
            for reg in regs:
                r = (r_u[(anio, reg)] + r_v[(anio, reg)]) / 2
                if not np.isfinite(r).any():
                    continue
                valor = bool(valor)
                c_w = numerico.maximo_estricto(r, vent)
                c_h = des.de(h, anio, reg)
                if c_w is None or c_h not in pos or not np.nanmax(r) >= U.f("GVIENTO_R"):
                    continue
                if (abs(c_w - c_h) >= _c("GVIENTO_DIST") and not numerico.es_alias_12(c_w, c_h)
                        and r[pos[c_w]] - r[pos[c_h]] >= U.f("GVIENTO_MARGEN")):
                    valor = True
            filas.append(_fila_marca(ctx, anio, MARCA_G_VIENTO, h.id, valor))
    return _tabla(filas, ESQUEMA_MARCAS, "marcas G-viento")


# ---------------------------------------------------------------------------------------------
# Posible media horaria (§4.3.5)
# ---------------------------------------------------------------------------------------------
def marca_media_horaria(metricas_e3p: pd.DataFrame, ctx: ContextoEstacion) -> bool:
    """§4.3.5 con la Enmienda 3 (B6): ρ = media circular de período 1 h de ĉ^f_cont en todos los años-régimen
    de la estación con |lat| ≤ 50° y ĉ^f_cont definido; marca si |ρ| > 0,35 h con ≥ 6 años-régimen. Delega en
    lineas_fisicas.diagnostico_subhorario (LF-18)."""
    return bool(lineas_fisicas.diagnostico_subhorario(metricas_e3p, ctx)["marca"])


# ---------------------------------------------------------------------------------------------
# Nombres de §9
# ---------------------------------------------------------------------------------------------
def _metricas_de(metricas: Mapping[str, pd.DataFrame] | None, clave: str, variable: str,
                 calcular: Callable[[], pd.DataFrame]) -> pd.DataFrame:
    """Filas de ``variable`` en ``metricas[clave]``; si la clave falta o no trae esa variable, las calcula."""
    tabla = (metricas or {}).get(clave)
    if tabla is not None and len(tabla) and (tabla["variable"] == variable).any():
        return tabla[tabla["variable"] == variable]
    return calcular()


def _metricas_e3_ts(metricas, extracto, serie, ctx) -> pd.DataFrame:
    return _metricas_de(metricas, METRICAS_E3, "Ts", lambda: lineas_fisicas.e3(extracto, serie, ctx, "Ts").metricas)


def _metricas_e4(metricas, extracto, ctx, variable: str) -> pd.DataFrame:
    return _metricas_de(metricas, METRICAS_E4, variable, lambda: lineas_fisicas.ajustes_e4(extracto, ctx, variable))


def guardas(extracto: pd.DataFrame, serie: SerieEra5 | None, meses: pd.DataFrame, metricas: dict[str, pd.DataFrame],
            ctx: ContextoEstacion) -> pd.DataFrame:
    """Nombre de §9: todas las guardas activas precalculadas de una estación (ESQUEMA_GUARDAS).
    ``metricas``: claves METRICAS_E3, METRICAS_E4 y FILTRO_E3T (ver el encabezado del módulo)."""
    activas = ctx.lineas_activas
    marcos = []
    if Linea.E3D in activas:
        marcos.append(e3d(extracto, serie, ctx))
    if Linea.P7 in activas:
        marcos.append(p7(extracto, ctx, serie))
    if Linea.TP in activas:
        marcos.append(tp(_metricas_e3_ts(metricas, extracto, serie, ctx), (metricas or {}).get(FILTRO_E3T), ctx))
    if Linea.E4T in activas:
        marcos.append(e4t(_metricas_e4(metricas, extracto, ctx, "Ts"), ctx))
    if Linea.G_VERSION in activas:
        marcos.append(g_version(resumen_por_version(extracto, serie, meses, ctx), ctx))
    return _unir(marcos, ESQUEMA_GUARDAS, "guardas")


def marcas(extracto: pd.DataFrame, serie: SerieEra5 | None, metricas: dict[str, pd.DataFrame],
           ctx: ContextoEstacion) -> pd.DataFrame:
    """Nombre de §9: G-HR, G-viento y «desfase térmico local» (con T-P) precalculadas (ESQUEMA_MARCAS).
    La «posible media horaria» es de la estación y va aparte: marca_media_horaria (§4.3.5, Enmienda 3, B6)."""
    activas = ctx.lineas_activas
    marcos = []
    if Linea.G_HR in activas:
        marcos.append(g_hr(_metricas_e4(metricas, extracto, ctx, "Ts"), _metricas_e4(metricas, extracto, ctx, "HR"),
                           ctx, extracto=extracto))
    if Linea.G_VIENTO in activas:
        marcos.append(g_viento(extracto, serie, ctx))
    if Linea.TP in activas:
        marcos.append(desfase_termico_local(_metricas_e3_ts(metricas, extracto, serie, ctx),
                                            (metricas or {}).get(FILTRO_E3T), ctx))
    return _unir(marcos, ESQUEMA_MARCAS, "marcas")
