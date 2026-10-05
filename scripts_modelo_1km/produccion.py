"""Producción de superficies horarias de 1 km: redes observadas, contexto de predicción y escritura.

Esto vivía dentro de ``docs/modelo_1km_horario.qmd``. Vive aquí para que la producción de la serie
completa se pueda lanzar en procesos paralelos **sin renderizar el informe**, y para que exista una
sola implementación del contrato NetCDF: el documento importa estas mismas clases y funciones, de modo
que lo que publica el informe y lo que publica el lanzador no pueden divergir.

Las dependencias pesadas (celdas, enlaces, estáticas, LULC, observaciones) se **inyectan** en
``Entorno``: el documento pasa los objetos que ya tiene cargados y el lanzador los construye desde
disco con ``entorno_desde_disco``. Ninguna de las dos rutas vuelve a leer lo que la otra ya leyó.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from _comun_modelo import (
    CONTRATO, ESCALA_SUPERFICIE, GRILLA_DIR, MACROZONA_REGION, MODELO_ROOT, OFFSET_UTC_H,
    SUPERFICIES_ROOT, UNIDADES, cargar_celdas, cargar_enlaces, escribir_superficie_dia, fechas,
    hash_codigo, log, publicar_json, ruta_superficie_dia,
)
from _comun_modelo import leer_estaciones as _leer_estaciones_sinca
from _comun_modelo import series_sinca as _series_sinca_solo
from _features import (
    AcagMensual, FuentesHorarias, SatelitesDiarios, VecindarioFijo, cargar_estaticas,
    combinar_nodos, derivadas_horarias, estencil, productos_interpolados, unir_estaticas,
)
from _manifiesto_satelital import sha256
import _red_adicional as _radic

# --- Redes observadas -----------------------------------------------------------------------------
# La red adicional se suma a SINCA como una red más de observación: mismas reglas de QC, mismo panel,
# mismos protocolos. El reloj y la unidad de esa red se resuelven en ``_red_adicional`` con evidencia.
RED_ADICIONAL = os.environ.get("MODELO_1KM_RED_ADICIONAL", "1") == "1" and _radic.disponible()
REDES_ACTIVAS = ("sinca", _radic.RED) if RED_ADICIONAL else ("sinca",)
# Rachas de N o más registros consecutivos idénticos (sensor pegado); 0 lo desactiva.
QC_RACHA = int(os.environ.get("MODELO_1KM_QC_RACHA", "24"))


# El catálogo de SINCA a secas, para las tablas que contrastan una red con la otra.
leer_estaciones_sinca = _leer_estaciones_sinca


def leer_estaciones() -> pd.DataFrame:
    """Estaciones de SINCA y, si corresponde, de la red adicional, con una columna ``red``."""
    est = _leer_estaciones_sinca()
    est["red"] = "sinca"
    if not RED_ADICIONAL:
        return est
    return pd.concat([est, _radic.estaciones_adicionales()], ignore_index=True)


def series_sinca(pol: str, estaciones=None) -> pd.DataFrame:
    """Observaciones horarias de las redes activas, en el esquema del derivado SINCA."""
    s = _series_sinca_solo(pol, estaciones)
    if not RED_ADICIONAL:
        return s
    a = _radic.series_adicionales(pol)
    if estaciones is not None:
        a = a[a["estacion"].isin(estaciones)]
    return pd.concat([s, a], ignore_index=True) if len(a) else s


def estaciones_macrozona() -> pd.DataFrame:
    """Estaciones usables con su macrozona (misma partición regional que la grilla)."""
    est = leer_estaciones()
    region = (est["cod_comuna"].astype("float64") // 1000)
    est["macrozona"] = region.map(lambda r: MACROZONA_REGION.get(int(r), "sin_region") if np.isfinite(r) else "sin_region")
    return est


def marcar_rachas(obs: pd.DataFrame, minimo: int) -> pd.DataFrame:
    """Marca ``racha`` = el registro pertenece a una corrida de ``minimo`` o más valores idénticos
    consecutivos de la misma estación (los huecos no cortan la corrida)."""
    o = obs.sort_values(["estacion", "ts_utc"]).reset_index(drop=True)
    if minimo <= 0 or o.empty:
        o["racha"] = False
        return o
    cambio = (o["estacion"] != o["estacion"].shift()) | (o["obs"] != o["obs"].shift())
    corrida = cambio.cumsum()
    o["racha"] = corrida.groupby(corrida).transform("size").to_numpy() >= minimo
    return o


_ESTACIONES: pd.DataFrame | None = None
_OBS: dict[str, pd.DataFrame] = {}


def estaciones_usables() -> pd.DataFrame:
    """``estaciones_macrozona()`` memoizado. Es perezoso a propósito: importar este módulo no debe
    exigir que la grilla ya exista (la red adicional deriva su comuna de ella)."""
    global _ESTACIONES
    if _ESTACIONES is None:
        _ESTACIONES = estaciones_macrozona()
    return _ESTACIONES


def observaciones(pol: str) -> pd.DataFrame:
    """Serie horaria completa de ``pol`` con la bandera ``racha`` (memoizada). La bandera se calcula
    sobre el registro completo para que no dependa del período de calibración."""
    if pol not in _OBS:
        o = series_sinca(pol)
        _OBS[pol] = marcar_rachas(o[o["estacion"].isin(estaciones_usables()["estacion"])], QC_RACHA)
    return _OBS[pol]


# --- Retransformación de log1p(y) -----------------------------------------------------------------
def franja(hora_local: np.ndarray) -> np.ndarray:
    return np.where((hora_local >= 8) & (hora_local <= 18), "diurna", "nocturna")


def predecir(mod, smear: dict, X: np.ndarray, fr: np.ndarray) -> np.ndarray:
    adj = np.array([smear.get(f, smear["_global"]) for f in fr], dtype="float64")
    return np.expm1(mod.predict(X) + adj).astype("float32")


# Corrección de retransformación por contaminante: duan_oof | smearing_oof | duan_oof_macrozona.
# La varianza del residuo en escala log cambia mucho entre macrozonas —medida fuera de pliegue en
# PM₂.₅: 0,081 en la Región Metropolitana contra 0,196 en Los Lagos—, así que una corrección única
# sobrecorrige donde el modelo ajusta bien. El documento importa esto para no tener su propia copia.
# Los dos gases corrigen por macrozona x franja. En NO₂ la corrección global quedaba con un sesgo de
# −19,3 % en el norte grande, justo donde la red es más rala; repartida baja a −0,5 % y el sesgo
# nacional de +3,63 % a +1,69 % (medido sobre las predicciones fuera de pliegue del modelo vigente;
# clave retransformacion_diagnostico de modelos/<pol>/metricas.json). La justificación anterior para dejarlo global se había escrito con el
# modelo que todavía incluía la distancia a la costa.
RETRANSFORMACION_POR_DEFECTO = {"pm25": "duan_oof_macrozona", "no2": "duan_oof_macrozona"}


def retransformacion_de(pol: str) -> str:
    return os.environ.get(f"MODELO_1KM_RETRANSFORMACION_{pol.upper()}",
                          os.environ.get("MODELO_1KM_RETRANSFORMACION",
                                         RETRANSFORMACION_POR_DEFECTO.get(pol, "duan_oof")))


def claves_retrans(df: pd.DataFrame, metodo: str) -> np.ndarray:
    """Clave por fila de la corrección: la franja, o «macrozona|franja» si el método la reparte.
    ``retransformar_oof`` y ``smear_de`` agrupan por esta clave sin necesitar ningún cambio."""
    fr = franja(df["hora_local"].to_numpy())
    if not metodo.endswith("_macrozona"):
        return fr
    return np.char.add(np.char.add(df["macrozona_cod"].to_numpy().astype("U8"), "|"), fr.astype("U8"))

def smear_de(res: np.ndarray, fr: np.ndarray, metodo: str = "duan_oof") -> dict:
    """Corrección aditiva en escala log por grupo de ``fr``, con respaldo global."""
    ok = np.isfinite(res)
    f_adj = (lambda r: float(np.log(np.mean(np.exp(r))))) if metodo.startswith("smearing") else \
        (lambda r: 0.5 * float(np.var(r)))
    smear = {str(f): f_adj(res[ok & (fr == f)]) for f in np.unique(fr[ok]) if (ok & (fr == f)).sum() >= 100}
    smear["_global"] = f_adj(res[ok]) if ok.any() else 0.0
    for f in ("diurna", "nocturna"):                    # respaldo por franja para claves compuestas
        s = ok & np.char.endswith(fr.astype("U16"), f)
        if s.sum() >= 100:
            smear.setdefault(f, f_adj(res[s]))
            smear[f] = f_adj(res[s])
    return smear
_COLS_OOF = ["estacion", "celda", "region_sinca", "ts_utc", "fecha_local", "hora_local", "anio", "macrozona_cod", "obs"]


def claves_retransformacion(smear: dict, hora_local: np.ndarray, macrozona_cod=None) -> np.ndarray:
    """Clave de la corrección de retransformación de cada fila.

    La corrección de Duan es un término aditivo en escala log, y hasta aquí se estimaba **global**
    por franja. Pero la varianza del residuo en log cambia mucho entre macrozonas —medida fuera de
    pliegue en PM₂.₅: 0,081 en la Región Metropolitana contra 0,196 en Los Lagos—, de modo que una
    corrección única sobrecorrige justo donde el modelo ajusta bien. Si el modelo guardó claves
    ``"{macrozona}|{franja}"`` se usa la de la celda; si esa macrozona no está —celdas sin región o
    insulares, que no tienen estaciones— se cae a la de la franja. ``predecir`` no cambia: sigue
    siendo una búsqueda en el diccionario con respaldo en ``_global``.
    """
    fr = franja(hora_local)
    if macrozona_cod is None or not any("|" in k for k in smear):
        return fr
    comp = np.char.add(np.char.add(np.asarray(macrozona_cod).astype("U8"), "|"), fr.astype("U8"))
    return np.where(np.isin(comp, np.array(sorted(k for k in smear if "|" in k), dtype="U16")), comp, fr)


# --- Entorno de producción ------------------------------------------------------------------------
@dataclass
class Entorno:
    """Lo que la predicción necesita del resto del proyecto, inyectado en vez de leído dos veces."""
    celdas: pd.DataFrame                    # grilla completa (de ella sale el subconjunto a predecir)
    enlaces: pd.DataFrame                   # enlaces celda–píxel de cada producto
    estaticas: pd.DataFrame
    lulc: pd.DataFrame
    meta_grilla: dict
    superficies_dir: Path
    modelos_dir: Path
    sufijo: str = ""
    codigo: str = "desconocido"
    documento: str = "desconocido"
    observaciones: Callable[[str], pd.DataFrame] = observaciones
    estaciones: Callable[[], pd.DataFrame] = leer_estaciones

    def carpeta_modelo(self, pol: str) -> Path:
        c = self.modelos_dir / f"{pol}{self.sufijo}"
        c.mkdir(parents=True, exist_ok=True)
        return c

    @property
    def enlaces_sha256(self) -> str:
        return self.meta_grilla["archivos"]["enlaces_productos"]


def entorno_desde_disco(sufijo: str | None = None) -> Entorno:
    """Construye el entorno leyendo lo mismo que lee el documento. Para lanzadores y mediciones."""
    import json

    sufijo = sufijo if sufijo is not None else (f"_{e}" if (e := os.environ.get("MODELO_1KM_ETIQUETA", "")) else "")
    meta = json.loads((GRILLA_DIR / "metadata.json").read_text(encoding="utf-8"))
    if not str(meta.get("schema", "")).endswith("grilla.v2"):
        raise SystemExit(f"La grilla de {GRILLA_DIR} es anterior al enlace al píxel válido; reconstrúyela.")
    estaticas, lulc = cargar_estaticas()
    doc = Path(__file__).resolve().parent.parent / "docs" / "modelo_1km_horario.qmd"
    return Entorno(celdas=cargar_celdas(), enlaces=cargar_enlaces(), estaticas=estaticas, lulc=lulc,
                   meta_grilla=meta, superficies_dir=SUPERFICIES_ROOT / f"superficies{sufijo}",
                   modelos_dir=MODELO_ROOT / "modelos", sufijo=sufijo, codigo=hash_codigo(),
                   documento=sha256(doc)[:16] if doc.exists() else "desconocido")


class _Compilado:
    """El mismo árbol de decisión, compilado a código máquina con LLVM (``lleaves``).

    No es otro modelo: lee el mismo ``modelo_final.txt`` y recorre los mismos 800 árboles. Lo único
    que cambia es que el recorrido deja de ser interpretado. Medido sobre 838.430 filas reales, es
    10,4× más rápido en pared y 11,6× más barato en CPU, con una diferencia máxima de 2,7 × 10⁻¹⁴ en
    escala log1p (redondeo de float64: ninguna fila difiere en más de 10⁻⁹). Aun así, ``Modelo``
    verifica la equivalencia contra el booster la primera vez que predice, con datos reales.
    """

    def __init__(self, ruta: Path, cache: Path, hilos: int):
        import lleaves
        self.m = lleaves.Model(model_file=str(ruta))
        # ``lleaves`` escribe su caché con ``write_bytes``, sin atomicidad: con varios procesos
        # produciendo a la vez, uno podría leer un objeto a medio escribir. Se compila a un
        # temporal propio y se publica con ``os.replace``, que sí es atómico.
        if cache.exists():
            self.m.compile(cache=str(cache))
        else:
            tmp = cache.with_name(f"{cache.stem}.{os.getpid()}{cache.suffix}")
            self.m.compile(cache=str(tmp))
            try:
                os.replace(tmp, cache)
            except OSError:
                tmp.unlink(missing_ok=True)
        self.hilos = hilos

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.m.predict(np.ascontiguousarray(X, dtype="float64"), n_jobs=self.hilos)


PREDICTOR = os.environ.get("MODELO_1KM_PREDICTOR", "compilado")   # compilado | lightgbm
HILOS = int(os.environ.get("MODELO_1KM_HILOS_PREDICCION", str(os.cpu_count() or 8)))
TOLERANCIA_COMPILADO = 1e-9


class Modelo:
    def __init__(self, pol: str, entorno: Entorno):
        import lightgbm as lgb
        self.carpeta = entorno.carpeta_modelo(pol)
        meta = json_leer(self.carpeta / "modelo_final.json")
        self.features, self.smear, self.pol = meta["features"], meta["smear"], pol
        self.booster = lgb.Booster(model_file=str(self.carpeta / "modelo_final.txt"))
        self.sha = meta["sha256"]
        self.retransformacion = meta.get("retransformacion", "duan_oof")
        self.motor, self.verificado = self.booster, PREDICTOR != "compilado"
        if PREDICTOR == "compilado":
            try:
                self.motor = _Compilado(self.carpeta / "modelo_final.txt",
                                        self.carpeta / f"compilado_{self.sha[:12]}.o", HILOS)
                log.info("%s: predictor compilado (lleaves), %d hilos", pol, HILOS)
            except Exception as e:                                  # sin lleaves se sigue con LightGBM
                log.warning("%s: no se pudo compilar el modelo (%s); se predice con LightGBM", pol, e)
                self.motor, self.verificado = self.booster, True

    def _verificar(self, X: np.ndarray) -> None:
        """Compara compilado y booster sobre filas reales antes de confiar en el primero."""
        idx = np.linspace(0, len(X) - 1, min(20_000, len(X))).astype(int)
        d = float(np.max(np.abs(self.motor.predict(X[idx]) - self.booster.predict(X[idx]))))
        self.verificado = True
        if d > TOLERANCIA_COMPILADO:
            log.error("%s: el predictor compilado difiere del booster en %.2e (> %.0e); se vuelve a "
                      "LightGBM", self.pol, d, TOLERANCIA_COMPILADO)
            self.motor = self.booster
        else:
            log.info("%s: predictor compilado verificado contra el booster (dif. máx. %.2e)", self.pol, d)

    def predecir(self, X: np.ndarray, hora_local: np.ndarray, macrozona_cod=None) -> np.ndarray:
        if not self.verificado:
            self._verificar(X)
        return predecir(self.motor, self.smear, X, claves_retransformacion(self.smear, hora_local, macrozona_cod))


def json_leer(ruta: Path) -> dict | None:
    import json
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


class ContextoPrediccion:
    """Todo lo que se reutiliza entre días: celdas, enlaces, estáticas, ACAG, reanálisis y observaciones."""

    def __init__(self, pol: str, celdas: pd.DataFrame, entorno: Entorno):
        from construir_grilla import vecino_mas_cercano
        self.e = entorno
        self.pol, self.modelo = pol, Modelo(pol, entorno)
        self.celdas = celdas.reset_index(drop=True)
        self.n = len(self.celdas)
        self.enlaces = entorno.enlaces.set_index("celda").loc[self.celdas["celda"]].reset_index()
        self.acag = AcagMensual(self.celdas)
        self.fuentes = FuentesHorarias()
        self.satelites = SatelitesDiarios(self.celdas, self.enlaces)
        est = entorno.estaciones()
        obs = entorno.observaciones(pol)              # registro completo, sin rachas de sensor pegado
        obs = obs[~obs["racha"] & obs["estacion"].isin(est["estacion"])]
        self.O = obs.pivot_table(index="ts_utc", columns="estacion", values="obs", aggfunc="mean")
        meta_est = est.set_index("estacion").loc[self.O.columns]
        self.lat_e, self.lon_e = meta_est["lat"].to_numpy(float), meta_est["lon"].to_numpy(float)
        self.lat_c, self.lon_c = self.celdas["lat"].to_numpy(float), self.celdas["lon"].to_numpy(float)
        self.mz = self.celdas["macrozona_cod"].to_numpy()      # para la corrección de retransformación
        self.pix = {p: self.enlaces[f"{p}_pixel"].to_numpy(dtype="int64") for p in self.fuentes.productos
                    if f"{p}_pixel" in self.enlaces.columns}
        # Los mismos pesos bilineales con que se calibró. Si el modelo se ajustó con interpolación y la
        # producción no la aplicara, el motor recibiría predictores escalonados que nunca vio: el nombre
        # de las columnas es idéntico, así que nada avisaría.
        self.interp = {p: estencil(p, self.celdas["celda"]) for p in productos_interpolados()
                       if p in self.pix}
        if self.interp:
            log.info("%s: interpolación bilineal en %s", pol, ", ".join(sorted(self.interp)))
        _, self.dist_est = vecino_mas_cercano(self.lat_c, self.lon_c, self.lat_e, self.lon_e)
        # Los puntos de consulta son siempre estas celdas: los pesos del vecindario se calculan una vez.
        self.vecindario = VecindarioFijo(self.O, self.lat_e, self.lon_e, self.lat_c, self.lon_c)
        log.info("%s: contexto de predicción con %s celdas y %d estaciones", pol, f"{self.n:,}", len(self.lat_e))

    @property
    def firma_interpolacion(self) -> str:
        """Qué productos se interpolaron. Entra en el manifiesto y en el guardián por día, que sólo
        miraba bytes, modelo, enlaces, celdas y retransformación: sin esto, los días producidos con un
        diseño se darían por buenos bajo el otro."""
        return ",".join(sorted(self.interp))

    def reiniciar_ventana_satelital(self) -> None:
        """Vacía el historial de las ventanas móviles satelitales (MAIAC 3 y 7 d, TROPOMI 7 y 15 d).

        ``SatelitesDiarios`` exige que los días se pidan en orden cronológico: pedirle uno anterior
        al último lanza ``ValueError``. Un lanzador que reparte años **no contiguos** al mismo
        proceso —para producir primero los años de los mapas— salta hacia atrás, así que antes de
        cada año tiene que empezar la ventana de cero y volver a calentarla con sus 15 días previos.
        El resultado es idéntico al de una pasada cronológica: ``_ventana`` filtra el historial por
        distancia en días, de modo que 15 días de calentamiento llenan por completo la ventana más
        larga y nada de un año lejano puede colarse.
        """
        self.satelites = SatelitesDiarios(self.celdas, self.enlaces)

    def dia(self, fecha: date, forzar: bool = False) -> tuple[Path, bool]:
        """Predice y publica un día local; devuelve (ruta NetCDF, publicado ahora)."""
        nc_path, json_path = ruta_superficie_dia(self.e.superficies_dir, self.pol, fecha)
        sat = self.satelites.dia(fecha)        # mantiene la ventana móvil aunque el día se omita
        if nc_path.exists() and json_path.exists() and not forzar:
            reg = json_leer(json_path) or {}
            # La retransformación entra en la guarda: es un término posterior al ajuste, así que el
            # sha del booster no cambia con ella y sin esto un día viejo se daría por vigente.
            if reg.get("bytes") == nc_path.stat().st_size and reg.get("modelo_sha256") == self.modelo.sha \
                    and reg.get("enlaces_sha256") == self.e.enlaces_sha256 and reg.get("celdas") == int(self.n) \
                    and reg.get("retransformacion") == self.modelo.retransformacion \
                    and reg.get("interpolacion", "") == self.firma_interpolacion:
                return nc_path, False
        base = pd.DataFrame({"celda": self.celdas["celda"].to_numpy(), "lat": self.lat_c, "lon": self.lon_c,
                             "macrozona_cod": self.celdas["macrozona_cod"].to_numpy(),
                             "anio": np.int16(fecha.year)})
        base = base.merge(sat.drop(columns=["fecha_local"]), on="celda", how="left")
        base = unir_estaticas(base, self.e.estaticas, self.e.lulc)
        v_acag, clim = self.acag.mes(fecha.strftime("%Y%m"))
        base["acag_pm25"], base["acag_clim"] = v_acag, np.int8(clim)
        base["dist_est_km"] = self.dist_est.astype("float32")
        doy = fecha.timetuple().tm_yday
        base["doy_sin"], base["doy_cos"] = np.float32(np.sin(2 * np.pi * doy / 365.25)), np.float32(np.cos(2 * np.pi * doy / 365.25))
        base["dow"], base["mes"] = np.int8(fecha.weekday()), np.int8(fecha.month)
        salida = np.full((24, self.n), np.nan, dtype="float32")
        ts_dia = []
        for h in range(24):
            ts_utc = np.datetime64(datetime(fecha.year, fecha.month, fecha.day) + timedelta(hours=h + OFFSET_UTC_H), "ns")
            ts_dia.append(ts_utc)
            df = base.copy()
            ts_vec = np.full(self.n, ts_utc, dtype="datetime64[ns]")
            for producto, pixel in self.pix.items():
                if producto in self.interp:
                    pix4, pes4 = self.interp[producto]
                    vals = combinar_nodos(producto, ts_vec, pix4, pes4, self.fuentes)
                else:
                    vals = self.fuentes.extraer(producto, ts_vec, pixel)
                for col, arr in vals.items():
                    df[col] = arr
            df = derivadas_horarias(df)
            df["hora_local"] = np.int8(h)
            df["hora_sin"], df["hora_cos"] = np.float32(np.sin(2 * np.pi * h / 24)), np.float32(np.cos(2 * np.pi * h / 24))
            df["obs_vec"], df["peso_vec"] = self.vecindario.para(ts_utc)
            for c in self.modelo.features:
                if c not in df.columns:
                    df[c] = np.nan
            # float32, no float64: el panel de calibración guarda todas sus columnas en float32, así
            # que el modelo aprendió los cortes en esa precisión. ``lat`` y ``lon`` aquí son float64 y
            # con ellos en float64 el 0,88 % de las casillas cruza un umbral distinto (hasta 12,8
            # µg/m³ en celdas sueltas). El predictor compilado sube a float64 después, lo que es exacto.
            salida[h] = self.modelo.predecir(df[self.modelo.features].to_numpy(np.float32),
                                             np.full(self.n, h), self.mz)
        ts_dia = np.array(ts_dia, dtype="datetime64[ns]")
        atributos = {"contrato": CONTRATO, "contaminante": self.pol, "unidad": UNIDADES[self.pol],
                     "fecha_local": fecha.isoformat(), "reloj": f"bins horarios UTC; hora local = UTC-{OFFSET_UTC_H} fija",
                     "modelo": str(self.modelo.carpeta), "modelo_sha256": self.modelo.sha,
                     "predictores": self.modelo.features, "escala": ESCALA_SUPERFICIE[self.pol],
                     "retransformacion": self.modelo.retransformacion, "celdas": int(self.n),
                     "interpolacion": self.firma_interpolacion,
                     "codigo": self.e.codigo, "documento": self.e.documento, "acag_climatologico": int(clim),
                     "creado_utc": datetime.now(timezone.utc).isoformat(),
                     "nota": "estimación del modelo, no observación; incertidumbre en modelos/<pol>/residuos_sd.parquet"}
        escribir_superficie_dia(nc_path, self.pol, self.celdas["celda"].to_numpy(dtype="int64"), ts_dia, salida, atributos)
        publicar_json({"fecha": fecha.isoformat(), "contaminante": self.pol, "ruta": str(nc_path),
                       "bytes": nc_path.stat().st_size, "sha256": sha256(nc_path), "modelo_sha256": self.modelo.sha,
                       "enlaces_sha256": self.e.enlaces_sha256,
                       "retransformacion": self.modelo.retransformacion, "celdas": int(self.n),
                       "interpolacion": self.firma_interpolacion,
                       "fraccion_nan": float(np.mean(~np.isfinite(salida))),
                       "media": float(np.nanmean(salida)), "p50": float(np.nanmedian(salida)),
                       "p99": float(np.nanpercentile(salida, 99)),
                       "cobertura_satelital": {"aod_dia": float(sat["aod_dia"].notna().mean()),
                                               "no2_trop": float(sat["no2_trop"].notna().mean())},
                       "estaciones_con_obs": int(self.O.loc[self.O.index.isin(pd.DatetimeIndex(ts_dia))].notna().any().sum()),
                       "meses_reanalisis_faltantes": sorted(f"{p}:{m}" for p, m in self.fuentes.faltantes),
                       "utc": datetime.now(timezone.utc).isoformat()}, json_path)
        log.info("%s %s: media %.1f, NaN %.1f%%, %d KB", self.pol, fecha, float(np.nanmean(salida)),
                 100 * float(np.mean(~np.isfinite(salida))), nc_path.stat().st_size // 1024)
        return nc_path, True


def predecir_rango(pol: str, desde: str, hasta: str, celdas: pd.DataFrame, entorno: Entorno,
                   calentamiento: int = 15) -> dict:
    """Publica los días de [desde, hasta] (omitiendo los ya publicados) con ``calentamiento`` días previos
    para las ventanas satelitales."""
    ctx = ContextoPrediccion(pol, celdas, entorno)
    ini = date.fromisoformat(desde) - timedelta(days=calentamiento)
    hechos = omitidos = 0
    for f in fechas(ini.isoformat(), hasta):
        if f < date.fromisoformat(desde):
            ctx.satelites.dia(f)
            continue
        _, nuevo = ctx.dia(f)
        hechos += nuevo; omitidos += (not nuevo)
    log.info("%s: días publicados %d, omitidos %d", pol, hechos, omitidos)
    return {"contaminante": pol, "publicados": hechos, "omitidos": omitidos}
