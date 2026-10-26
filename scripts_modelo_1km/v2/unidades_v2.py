"""Unidades de la red ampliada: rótulo de la ficha, contraste con CAMS y conversión a 25 °C y 1 atm (bloque R6).

Regla única para las series de gases actuales, nuevas y SNIFA (decisiones U, U′, S, V e I del autor):

1. **Rótulo**: la unidad de la ficha SINCA (``unidad_ficha``). La ficha da una unidad por parámetro, que vale para la
   serie horaria y para la diaria. En las estaciones nuevas viene en ``manifiesto_descarga.csv`` de la ampliación; en
   las actuales, en la serie diaria del mismo parámetro de ``manifiesto_descarga_otras_series.csv`` (la que usó el
   contraste), y la actualización horaria tiene que coincidir con ella.
2. **Contraste**: rige la segunda corrida (R6), la de ``contraste_unidades_v2`` sobre el derivado de la red 2; la
   primera (``contraste_unidades_cams.csv``, ca0805ae…) sólo sirve para registrar los cambios de decisión. Las series
   en ppb son la referencia y quedan en ppb; si el contraste indica una unidad, la serie la toma; si es
   indeterminado, decide el rótulo (I): la rotulada µg/m³N se convierte según su ficha y la sin unidad queda fuera.
3. **Conversión** de µg/m³N a ppb a 25 °C y 1 atm: ppb = c × V_m / M, con V_m = 24,4654 L/mol y M de cada gas
   (NO2 46,0055; O3 47,998; SO2 64,064 g/mol, las literales de R6; CO 28,0101 g/mol, la del programa del contraste,
   ``contraste_unidades_cams.py:39``, porque R6 no la da). O3 es 47,998, la literal de R6, por la corrección de T12
   ([delegada]); antes era 47,9982, el valor del programa del contraste y de ``_features.py:40``. El contraste de la
   segunda corrida (``contraste_unidades_v2.M``) también usa 47,998, por T12, que no hace excepción para él: es su
   única diferencia con el programa de la primera corrida (diferencia relativa de unos 4·10⁻⁶). T12 corrige la
   conversión de R6 (esta) y el contraste; no toca el predictor ``cams_o3`` del panel, que sigue convirtiéndose con
   47,9982 (``_features.py:40`` y ``:104``: ``cams_o3 × M_AIRE / M_O3 × 1e9``), porque el panel usa el código de la v1
   con su huella (``panel_red2_v2.HUELLAS_CODIGO_V1``), como pide R11 («el de la v1 … con sus huellas registradas»):
   en el armado de la red 2 conviven las dos masas molares del O3, con un efecto numérico nulo (ronda 5 de la
   traducción, menor 6). 1 ppb de
   NO2 = 1,880 µg/m³N. SNIFA El Peñón pasa de 0,4872 (0 °C, ``_red_adicional.py:38``) a 0,5318; Charrúa y
   Progreso siguen en ppb, como decidió el contraste de la v1. CO, fuera de este contrato, pasaría a ppm con la misma
   fórmula (mg/m³N × V_m / M).
4. **PM2,5**: en µg/m³, sin contraste ni conversión; una serie sin unidad toma µg/m³ (S).

**Orden con R8.** Una serie cuya estación no tiene coordenada usable en los maestros de R8 (hoy, la 518) no se deriva, así
que tampoco está en la segunda corrida del contraste. Por eso sale **antes** de la regla de unidades
(``separar_sin_coordenadas``) y queda registrada con su motivo; si no, la regla, que exige que toda serie de gas esté
en el contraste, detendría el armado.

El rango operacional de R5 (PM2,5 0-1.500 µg/m³; NO2 0-1.000 ppb; O3 0-500 ppb) se aplica **después** de convertir,
en ``panel_red2_v2``. Funciones puras salvo ``leer_manifiestos`` y ``leer_contraste``; no importan ``_comun_modelo``.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
import pandas as pd

VM_25C_L_MOL = 24.4654                         # L/mol a 25 °C y 1 atm (decisión U′)
MASA_MOLAR = {"no2": 46.0055, "o3": 47.998, "so2": 64.064, "co": 28.0101}    # R6 literal (O3: T12); CO, del contraste
GASES = ("no2", "o3", "so2", "co")
CONTAMINANTES_RED2 = ("pm25", "no2", "o3")      # los del contrato (PM2,5 y NO2) y la rama O3 (R20)
REFERENCIA = {"no2": "ppb", "o3": "ppb", "so2": "ppb", "co": "ppm"}
UG_M3N, UG_M3, PPB, PPM, MG_M3N = "µg/m³N", "µg/m³", "ppb", "ppm", "mg/m³N"
SIN_UNIDAD = "(sin unidad)"
INDETERMINADA = "indeterminada"
SHA_CONTRASTE_PRIMERA = "ca0805ae0e7af3c2ff8f241600ad46327ebfd68c27c470361a210b301bc9f855"

# Red SNIFA (v1, _red_adicional.py:42-46): factor de la columna rotulada ug/m3N. Charrúa y Progreso ya vienen en
# escala de ppb (contraste de la v1); El Peñón se convierte, ahora a 25 °C.
SNIFA_ESTACIONES = {"charrua": "SNIFA-CHARRUA", "progreso": "SNIFA-PROGRESO", "el_penon": "SNIFA-ELPENON"}


def factor_a_ppb(gas: str) -> float:
    """ppb por µg/m³N a 25 °C y 1 atm (en CO, ppm por mg/m³N): V_m / M."""
    return VM_25C_L_MOL / MASA_MOLAR[gas]


def ug_m3n_por_ppb(gas: str) -> float:
    """µg/m³N por ppb a 25 °C y 1 atm: M / V_m (NO2: 1,880)."""
    return MASA_MOLAR[gas] / VM_25C_L_MOL


def a_ppb(valor, gas: str):
    """µg/m³N → ppb a 25 °C y 1 atm (CO: mg/m³N → ppm)."""
    return np.asarray(valor, dtype="float64") * factor_a_ppb(gas)


PPB_POR_UG_M3N_NO2 = factor_a_ppb("no2")       # 0,53179…


def factores_snifa() -> dict[str, float]:
    """Factor por estación SNIFA para la columna rotulada ug/m3N (1,0: ya está en ppb)."""
    return {"charrua": 1.0, "progreso": 1.0, "el_penon": PPB_POR_UG_M3N_NO2}


def normalizar_unidad(u) -> str:
    """Escritura única del rótulo (la del programa del contraste: μ griega → µ, «m3» → «m³»)."""
    if u is None or (isinstance(u, float) and math.isnan(u)) or str(u).strip() == "" or str(u).strip() == "nan":
        return SIN_UNIDAD
    u = str(u).strip().replace("μ", "µ")
    return {"µg/m3N": UG_M3N, "mg/m3N": MG_M3N, "µg/m3": UG_M3, "ppb": PPB, "ppm": PPM}.get(u, u)


# ---------------------------------------------------------------------------
# Rótulos
# ---------------------------------------------------------------------------
def rotulos_de_ficha(nuevas: pd.DataFrame, actualizacion: pd.DataFrame, otras: pd.DataFrame,
                     actuales: pd.DataFrame, contaminantes=CONTAMINANTES_RED2) -> pd.DataFrame:
    """Rótulo de cada serie horaria del contrato (estación × contaminante).

    ``actuales``: manifiesto sellado de ``DATOS/sinca`` (sin unidad); el rótulo de sus series sale de la serie diaria
    del mismo parámetro (``otras``, grupo «configurada») y, si no la hay, de la actualización horaria. Si la
    actualización horaria y la diaria discrepan, es un error (R6.1 dice que coinciden en todas)."""
    filas = []
    diaria = (otras[(otras["grupo"] == "configurada") & (otras["resolucion"] == "diario")]
              .drop_duplicates(["estacion", "contaminante"]).set_index(["estacion", "contaminante"])["unidad_ficha"])
    horaria = actualizacion.drop_duplicates(["estacion", "contaminante"]).set_index(
        ["estacion", "contaminante"])["unidad_ficha"]
    for (est, pol) in sorted(set(zip(actuales["estacion"], actuales["contaminante"]))):
        if pol not in contaminantes:
            continue
        d = normalizar_unidad(diaria.get((est, pol))) if (est, pol) in diaria.index else None
        h = normalizar_unidad(horaria.get((est, pol))) if (est, pol) in horaria.index else None
        if d is not None and h is not None and d != h:
            raise ValueError(f"{est} {pol}: el rótulo horario de la actualización ({h}) no es el diario ({d})")
        rot, fuente = (d, "otras_series_diaria") if d is not None else (
            (h, "actualizacion_horaria") if h is not None else (SIN_UNIDAD, "sin_ficha"))
        filas.append({"estacion": est, "contaminante": pol, "grupo": "actual", "rotulo": rot, "fuente_rotulo": fuente})
    for (est, pol), g in nuevas.groupby(["estacion", "contaminante"], sort=True):
        if pol not in contaminantes:
            continue
        rot = {normalizar_unidad(u) for u in g["unidad_ficha"]}
        if len(rot) != 1:
            raise ValueError(f"{est} {pol}: la serie nueva trae más de un rótulo ({sorted(rot)})")
        filas.append({"estacion": est, "contaminante": pol, "grupo": "nueva", "rotulo": rot.pop(),
                      "fuente_rotulo": "manifiesto_ampliacion"})
    out = pd.DataFrame(filas, columns=["estacion", "contaminante", "grupo", "rotulo", "fuente_rotulo"])
    dup = out.duplicated(["estacion", "contaminante"])
    if dup.any():
        raise ValueError(f"códigos repetidos entre actuales y nuevas: {out.loc[dup, 'estacion'].tolist()}")
    return out.sort_values(["contaminante", "estacion"], kind="stable").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Decisión de unidad
# ---------------------------------------------------------------------------
def decidir_unidad(pol: str, rotulo: str, indicada: str | None) -> dict:
    """Unidad en que vienen los valores de una serie, factor a la unidad del modelo y si entra (R6).

    ``indicada``: ``unidad_que_indica`` del contraste («ppb», «µg/m³N», «indeterminada», …); se ignora en PM2,5."""
    rotulo = normalizar_unidad(rotulo)
    if pol == "pm25":
        return {"unidad_valores": UG_M3, "factor": 1.0, "entra": True,
                "regla": "PM2,5 en µg/m³, sin contraste ni conversión (R6.4)"
                + ("; sin unidad en la ficha: toma µg/m³ (S)" if rotulo == SIN_UNIDAD else "")}
    if pol not in REFERENCIA:
        raise ValueError(f"contaminante sin regla de unidades: {pol}")
    ref = REFERENCIA[pol]
    ind = normalizar_unidad(indicada) if indicada not in (None, "") else INDETERMINADA
    if ind in (SIN_UNIDAD, "indeterminada"):
        ind = INDETERMINADA
    if rotulo == ref:
        return {"unidad_valores": ref, "factor": 1.0, "entra": True, "regla": "rótulo de referencia (ppb); no se decide"}
    if ind == ref:
        return {"unidad_valores": ref, "factor": 1.0, "entra": True,
                "regla": ("el contraste indica ppb: rótulo contradicho, entra sin convertir" if rotulo == UG_M3N
                          else "sin unidad en la ficha; el contraste indica ppb")}
    if ind == UG_M3N:
        return {"unidad_valores": UG_M3N, "factor": factor_a_ppb(pol), "entra": True,
                "regla": ("el contraste confirma µg/m³N: se convierte a 25 °C" if rotulo == UG_M3N
                          else "sin unidad en la ficha; el contraste indica µg/m³N: se convierte a 25 °C")}
    if ind != INDETERMINADA:
        raise ValueError(f"{pol}: unidad indicada no prevista por la regla R6 ({indicada!r})")
    if rotulo == UG_M3N:
        return {"unidad_valores": UG_M3N, "factor": factor_a_ppb(pol), "entra": True,
                "regla": "contraste indeterminado: decide el rótulo µg/m³N, se convierte a 25 °C (I)"}
    if rotulo == SIN_UNIDAD:
        return {"unidad_valores": None, "factor": float("nan"), "entra": False,
                "regla": "contraste indeterminado y sin unidad en la ficha: fuera (I)"}
    return {"unidad_valores": None, "factor": float("nan"), "entra": False,
            "regla": f"rótulo {rotulo} no previsto para {pol}: fuera"}


def unidades_de_series(rotulos: pd.DataFrame, contraste: pd.DataFrame | None,
                       contaminantes=CONTAMINANTES_RED2) -> pd.DataFrame:
    """Decisión de unidad de cada serie de ``rotulos``. Falla cerrado si una serie de gas no está en el contraste o
    si el contraste registra otro rótulo que la ficha."""
    filas = []
    con = None
    if contraste is not None:
        con = contraste.assign(rotulo=contraste["rotulo"].map(normalizar_unidad)).set_index(
            ["estacion", "contaminante"])
        if con.index.duplicated().any():
            raise ValueError("el contraste trae series repetidas")
    for f in rotulos.itertuples(index=False):
        if f.contaminante not in contaminantes:
            continue
        indicada = None
        if f.contaminante != "pm25":
            if con is None or (f.estacion, f.contaminante) not in con.index:
                raise ValueError(f"{f.estacion} {f.contaminante}: no está en el contraste de unidades")
            c = con.loc[(f.estacion, f.contaminante)]
            if c["rotulo"] != f.rotulo:
                raise ValueError(f"{f.estacion} {f.contaminante}: el contraste usó el rótulo {c['rotulo']} y la ficha "
                                 f"dice {f.rotulo}")
            indicada = c["unidad_que_indica"]
        d = decidir_unidad(f.contaminante, f.rotulo, indicada)
        filas.append({"estacion": f.estacion, "contaminante": f.contaminante, "grupo": f.grupo, "rotulo": f.rotulo,
                      "unidad_que_indica": indicada if indicada is not None else "", **d})
    return pd.DataFrame(filas, columns=["estacion", "contaminante", "grupo", "rotulo", "unidad_que_indica",
                                        "unidad_valores", "factor", "entra", "regla"])


# ---------------------------------------------------------------------------
# Lectura (sólo cabeceras y columnas de rótulo; ningún valor de concentración)
# ---------------------------------------------------------------------------
def sha256_archivo(ruta) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for bloque in iter(lambda: fh.read(8 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def leer_contraste(ruta, sha_esperado: str | None = None) -> tuple[pd.DataFrame, str]:
    """Columnas de decisión del contraste (``estacion``, ``contaminante``, ``grupo``, ``rotulo``,
    ``unidad_que_indica``) y su sha256; con ``sha_esperado``, exige la huella."""
    sha = sha256_archivo(ruta)
    if sha_esperado is not None and sha != sha_esperado:
        raise SystemExit(f"{Path(ruta).name}: sha256 {sha[:8]}… no es el registrado ({sha_esperado[:8]}…)")
    c = pd.read_csv(ruta, dtype=str, usecols=["estacion", "contaminante", "grupo", "rotulo", "unidad_que_indica"])
    return c, sha


def leer_manifiestos(datos) -> dict[str, pd.DataFrame]:
    """Los cuatro manifiestos que dan los rótulos, con las columnas de identidad y de rótulo."""
    datos = Path(datos)
    amp = datos / "sinca_ampliacion_20261024"
    cols_id = ["estacion", "contaminante", "resolucion"]
    return {
        "actuales": pd.read_csv(datos / "sinca" / "manifiesto_descarga.csv", dtype=str, usecols=cols_id),
        "actualizacion": pd.read_csv(amp / "actualizacion_configuradas" / "manifiesto_descarga.csv", dtype=str,
                                     usecols=cols_id + ["unidad_ficha"]),
        "nuevas": pd.read_csv(amp / "manifiesto_descarga.csv", dtype=str, usecols=cols_id + ["unidad_ficha"]),
        "otras": pd.read_csv(amp / "manifiesto_descarga_otras_series.csv", dtype=str,
                             usecols=cols_id + ["unidad_ficha", "grupo"]),
    }


def separar_sin_coordenadas(rotulos: pd.DataFrame, con_coordenada) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(series con coordenada usable en R8, series sin ella). Las segundas salen antes de la regla de unidades."""
    dentro = rotulos["estacion"].astype(str).isin({str(e) for e in con_coordenada})
    fuera = rotulos[~dentro].assign(regla="sin coordenada usable en los maestros de R8: fuera antes de la regla de "
                                          "unidades (no se deriva ni entra al contraste)")
    return rotulos[dentro].reset_index(drop=True), fuera.reset_index(drop=True)


def unidades_desde(rotulos: pd.DataFrame, contraste: pd.DataFrame, con_coordenada,
                   contaminantes=CONTAMINANTES_RED2) -> tuple[pd.DataFrame, pd.DataFrame]:
    """R8 y luego R6: (tabla de unidades de las series con coordenada, series fuera por coordenadas)."""
    dentro, fuera = separar_sin_coordenadas(rotulos, con_coordenada)
    return unidades_de_series(dentro, contraste, contaminantes), fuera


def unidades_red2(datos, ruta_contraste, sha_contraste: str, con_coordenada=None,
                  rechazar_primera: bool = False) -> tuple[pd.DataFrame, dict]:
    """Tabla de unidades de todas las series del contrato con coordenada usable, con la huella del contraste usado,
    que es obligatoria. Rige la segunda corrida (R6); la primera sólo sirve para registrar los cambios y para las
    pruebas que reproducen las listas de R6, y el armado la rechaza (``rechazar_primera``). ``con_coordenada``:
    códigos de los maestros de R8 (por omisión, ``maestro_red2``)."""
    if not sha_contraste:
        raise SystemExit("la regla de unidades exige la huella del contraste que se usa (rige la segunda corrida, R6)")
    if rechazar_primera and sha_contraste == SHA_CONTRASTE_PRIMERA:
        raise SystemExit("la regla de unidades del armado usa la segunda corrida del contraste (R6), no la primera "
                         f"({SHA_CONTRASTE_PRIMERA[:8]}…)")
    if con_coordenada is None:
        import red_ampliada_v2 as ra
        con_coordenada = set(ra.maestro_red2(datos)["estacion"])
    m = leer_manifiestos(datos)
    rot = rotulos_de_ficha(m["nuevas"], m["actualizacion"], m["otras"], m["actuales"])
    con, sha = leer_contraste(ruta_contraste, sha_contraste)
    tabla, fuera_coord = unidades_desde(rot, con, con_coordenada)
    info = {"contraste_sha256": sha, "series": int(len(tabla)), "entran": int(tabla["entra"].sum()),
            "fuera": tabla.loc[~tabla["entra"], ["estacion", "contaminante", "rotulo", "regla"]].to_dict("records"),
            "fuera_por_coordenadas": fuera_coord[["estacion", "contaminante", "rotulo", "regla"]].to_dict("records"),
            "convertidas": int((tabla["entra"] & (tabla["factor"] != 1.0)).sum()),
            "vm_l_mol": VM_25C_L_MOL, "masas_molares": MASA_MOLAR}
    return tabla, info
