#!/usr/bin/env python3
"""Prueba exploratoria de pérdidas, sin DMC, producción ni contrato v2 modificado.

``plan`` sólo inspecciona metadatos. ``ejecutar --etiqueta NUEVA`` usa muestras
de días completos y escribe únicamente un namespace nuevo del piloto. Los
datos históricos ya fueron explorados en v1: no es confirmación independiente.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sys
import time

for _nombre in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
                "NUMEXPR_NUM_THREADS"):
    try:
        _previo = int(os.environ.get(_nombre, "2"))
    except ValueError:
        _previo = 2
    os.environ[_nombre] = str(min(2, max(1, _previo)))

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

V2 = Path(__file__).resolve().parent
REPO = V2.parents[1]
V1 = Path(os.environ.get("AIR_POLLUTION_MODELO_1KM_V1_ROOT", str(Path.home() / "Asesorias_Data_local/AirPollution/modelado_1km")))
RAIZ_V2 = Path(os.environ.get("AIR_POLLUTION_MODELO_1KM_ROOT", str(Path.home() / "Asesorias_Data_local/AirPollution/modelado_1km_v2")))
UNIDADES = {"pm25": "µg/m³", "no2": "ppb"}
EXCLUIDAS = ("obs_vec", "peso_vec", "dist_est_km", "acag_pm25", "acag_clim")
VARIANTES = ("l2_original", "l2_log_smearing", "huber", "q05", "q50", "q95")
SEMILLA, MAX_AJUSTE, MAX_OTROS, RONDAS = 20261013, 50000, 20000, 150
RELOJ = "UTC−4 fijo del panel; inicio del bin, no día civil America/Santiago"


def hash_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def hash_archivo(p: Path) -> str:
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def identidad_filas(df: pd.DataFrame, feats=()) -> str:
    cols = ["estacion", "ts_utc", *feats]
    h = hashlib.sha256(hash_json(cols).encode())
    h.update(pd.util.hash_pandas_object(df[cols], index=False, categorize=False).to_numpy().tobytes())
    return h.hexdigest()


def preparar_calendario(df: pd.DataFrame) -> pd.DataFrame:
    """Conserva el reloj fuente UTC−4 fijo y comprueba su fecha contra el bin UTC."""
    df = df.copy()
    ts = pd.to_datetime(df["ts_utc"])
    df["ts_utc"] = ts.dt.tz_localize("UTC") if ts.dt.tz is None else ts.dt.tz_convert("UTC")
    local = df["ts_utc"].dt.tz_localize(None) - pd.Timedelta(hours=4)
    fecha = pd.to_datetime(df["fecha_local"])
    if df.ts_utc.isna().any() or fecha.isna().any() or fecha.dt.tz is not None or not fecha.dt.normalize().eq(local.dt.normalize()).all():
        raise ValueError("fecha_local no coincide con el reloj fuente UTC−4 fijo")
    df["fecha_fuente"] = local.dt.strftime("%Y-%m-%d")
    df["anio_fuente"], df["dia_mes"] = local.dt.year, local.dt.day
    return df


def limitar_dias(df: pd.DataFrame, tope: int, clave: str) -> pd.DataFrame:
    """Selecciona station-day usando sólo claves y semilla, sin mirar obs ni predictores."""
    grupos = df.groupby(["estacion", "fecha_fuente"], sort=True).size()
    orden = sorted(grupos.items(), key=lambda x: hashlib.sha256(f"{SEMILLA}|{clave}|{x[0]}".encode()).digest())
    elegidos, n = [], 0
    for grupo, cuenta in orden:
        if n + cuenta <= tope:
            elegidos.append(grupo)
            n += cuenta
    indice = pd.MultiIndex.from_frame(df[["estacion", "fecha_fuente"]])
    return df.loc[indice.isin(elegidos)].sort_values(["estacion", "ts_utc"]).reset_index(drop=True)


def dividir(df: pd.DataFrame, estaciones_biobio) -> dict:
    fuera = sorted(set(df.estacion.astype(str)) - set(estaciones_biobio))
    orden = sorted(fuera, key=lambda e: hashlib.sha256(f"{SEMILLA}|cal_espacial|{e}".encode()).digest())
    ncal = max(1, int(np.ceil(len(orden) * .2)))
    if len(orden) < 2:
        raise ValueError("No hay suficientes estaciones fuera del test espacial")
    cal = set(orden[:min(ncal, len(orden) - 1)])
    espacial = {"ajuste": df[~df.estacion.isin(set(estaciones_biobio) | cal)],
                "cal": df[df.estacion.isin(cal)], "test": df[df.estacion.isin(estaciones_biobio)]}
    temporal = {"ajuste": df[df.anio_fuente.between(2019, 2022)],
                "cal": df[df.anio_fuente == 2023], "test": df[df.anio_fuente == 2024]}
    salida = {}
    for prueba, partes in (("espacial_RVIII", espacial), ("temporal_2024", temporal)):
        salida[prueba] = {nombre: limitar_dias(parte, MAX_AJUSTE if nombre == "ajuste" else MAX_OTROS,
                                             f"{prueba}|{nombre}") for nombre, parte in partes.items()}
        if any(parte.empty for parte in salida[prueba].values()):
            raise ValueError(f"{prueba}: alguna partición quedó vacía")
    return salida


def leer_muestra(ruta: Path, feats: list, comprobar) -> pd.DataFrame:
    pf = pq.ParquetFile(ruta)
    columnas = list(dict.fromkeys(["estacion", "ts_utc", "obs", "fecha_local", *feats]))
    if not set(columnas).issubset(pf.schema_arrow.names):
        raise ValueError("Faltan columnas requeridas en el panel")
    partes = []
    for batch in pf.iter_batches(batch_size=65536, columns=columnas, use_threads=False):
        comprobar()
        df = preparar_calendario(batch.to_pandas())
        mask = df.anio_fuente.between(2019, 2024) & df.dia_mes.isin((5, 12, 19, 26))
        if mask.any():
            partes.append(df.loc[mask])
    if not partes:
        raise ValueError("No hay filas para los días calendario fijados")
    df = pd.concat(partes, ignore_index=True)
    if df.estacion.isna().any() or not np.isfinite(df.obs).all() or (df.obs < 0).any():
        raise ValueError("Claves u observaciones inválidas: no se filtran según cada modelo")
    if df.duplicated(["estacion", "ts_utc"]).any():
        raise ValueError("El conjunto seleccionado contiene claves duplicadas")
    return df


def unir_calidad(particiones: dict, ruta: Path, comprobar) -> dict:
    """Lee QC en lotes; exige exactamente una bandera por clave seleccionada."""
    claves = ["estacion", "ts_utc"]
    wanted = pd.concat([d[claves] for partes in particiones.values() for d in partes.values()]).drop_duplicates()
    indice = pd.MultiIndex.from_frame(wanted)
    seleccion = []
    for batch in pq.ParquetFile(ruta).iter_batches(batch_size=65536, columns=[*claves, "qc", "fuente"], use_threads=False):
        comprobar()
        df = batch.to_pandas()
        df["ts_utc"] = pd.to_datetime(df.ts_utc, utc=True)
        mask = pd.MultiIndex.from_frame(df[claves]).isin(indice)
        if mask.any():
            seleccion.append(df.loc[mask])
    if not seleccion:
        raise ValueError("QC no contiene las claves seleccionadas")
    qc = pd.concat(seleccion, ignore_index=True)
    if qc.duplicated(claves).any() or len(qc) != len(wanted):
        raise ValueError("QC: claves duplicadas o cobertura incompleta")
    return {prueba: {nombre: d.merge(qc, on=claves, how="left", sort=False, validate="one_to_one")
                    for nombre, d in partes.items()} for prueba, partes in particiones.items()}


def duan_global(y_cal, z_cal) -> float:
    residuos = np.log1p(np.asarray(y_cal, dtype=float)) - np.asarray(z_cal, dtype=float)
    if not len(residuos) or not np.isfinite(residuos).all():
        raise ValueError("Residuos de calibración no finitos")
    factor = float(np.mean(np.exp(residuos)))
    if not np.isfinite(factor) or factor <= 0:
        raise ValueError("Factor Duan inválido")
    return factor


def metricas(y, p) -> dict:
    y, p = np.asarray(y, float), np.asarray(p, float)
    if not len(y) or not (np.isfinite(y).all() and np.isfinite(p).all()):
        raise ValueError("Pares de evaluación incompletos")
    e, sst = p - y, np.sum((y - y.mean()) ** 2)
    return {"n": len(y), "rmse": float(np.sqrt(np.mean(e ** 2))), "mae": float(np.mean(abs(e))),
            "sesgo": float(e.mean()), "nmb_pct": float(100 * e.sum() / y.sum()) if y.sum() else None,
            "r2": float(1 - np.sum(e ** 2) / sst) if sst else None}


def diario(test: pd.DataFrame, pred) -> dict | None:
    pares = test[["estacion", "ts_utc", "fecha_fuente", "obs"]].assign(pred=np.asarray(pred))
    agrupado = pares.groupby(["estacion", "fecha_fuente"]).agg(horas=("ts_utc", "nunique"),
                                                               obs=("obs", "mean"), pred=("pred", "mean"))
    agrupado = agrupado[agrupado.horas >= 18]
    return metricas(agrupado.obs, agrupado.pred) if len(agrupado) else None


def cuantiles(y, raw: dict) -> tuple[dict, dict]:
    from perdidas_v2 import reordenar_cuantiles, cobertura, puntaje_intervalo
    ordenados = reordenar_cuantiles(raw["q05"], raw["q50"], raw["q95"])
    salidas = dict(zip(("q05", "q50", "q95"), ordenados[:3]))
    reporte = {"cruces": ordenados[3], "q50_cambiado_al_ordenar": int(np.sum(raw["q50"] != salidas["q50"]))}
    y = np.asarray(y)
    for nombre, valores in (("bruto", raw), ("reordenado", salidas)):
        lo, hi = valores["q05"], valores["q95"]
        validos = lo <= hi
        reporte[nombre] = {"cobertura_90": cobertura(y, lo, hi), "anchura_media": float(np.mean(hi - lo)),
                           "interval_score_sin_cruces": float(np.mean(puntaje_intervalo(y[validos], lo[validos], hi[validos])))
                           if validos.any() else None, "filas_interval_score": int(validos.sum())}
        for q, tau in (("q05", .05), ("q50", .5), ("q95", .95)):
            error = y - valores[q]
            reporte[nombre][q] = {"pinball": float(np.mean(np.maximum(tau * error, (tau - 1) * error))),
                                  "fraccion_obs_menor_igual": float(np.mean(y <= valores[q]))}
    return reporte, salidas


def plan(v1=V1, raiz_v2=RAIZ_V2) -> dict:
    fuentes = {}
    cfg = json.loads((V2 / "config_v2.json").read_text())
    for pol, unidad in UNIDADES.items():
        ruta = v1 / "paneles" / f"panel_{pol}.parquet"
        meta = json.loads((v1 / "modelos" / pol / "modelo_final.json").read_text())
        if meta.get("unidad") != unidad or meta.get("contaminante") != pol:
            raise ValueError(f"Unidad v1 no confirmada para {pol}")
        pf = pq.ParquetFile(ruta)
        qc = raiz_v2 / "paneles" / f"calidad_{pol}.parquet"
        qc_meta = json.loads(qc.with_suffix(".json").read_text())
        sha_panel = json.loads(ruta.with_suffix(".json").read_text()).get("sha256")
        if qc_meta["panel"]["sha256"] != sha_panel or pq.ParquetFile(qc).metadata.num_rows != pf.metadata.num_rows:
            raise ValueError(f"QC no está vinculado al panel {pol}")
        feats = [c for c in cfg["motores"]["eje_A"]["predictores"][pol] if c not in EXCLUIDAS]
        if len(feats) != {"pm25": 65, "no2": 64}[pol]:
            raise ValueError(f"Whitelist inesperada para {pol}: {len(feats)}")
        fuentes[pol] = {"ruta": str(ruta), "bytes": ruta.stat().st_size, "mtime_ns": ruta.stat().st_mtime_ns,
                        "filas": pf.metadata.num_rows, "columnas": pf.metadata.num_columns, "unidad": unidad,
                        "sha256_declarado_panel": sha_panel, "predictores_n": len(feats), "qc_ruta": str(qc),
                        "qc_meta_sha256": hash_archivo(qc.with_suffix(".json"))}
    versiones = {}
    for nombre in ("numpy", "pandas", "pyarrow", "lightgbm", "xgboost", "scikit-learn"):
        try:
            versiones[nombre] = importlib.metadata.version(nombre)
        except importlib.metadata.PackageNotFoundError:
            versiones[nombre] = None
    return {"schema": "piloto-perdidas-sin-dmc/v1", "fuentes": fuentes, "versiones": versiones,
            "motores": [m for m in ("lightgbm", "xgboost") if versiones[m]],
            "variantes": VARIANTES, "rondas": RONDAS, "hilos": 2, "semilla": SEMILLA,
            "max_ajuste": MAX_AJUSTE, "max_cal_test": MAX_OTROS, "dias_mes": [5, 12, 19, 26],
            "periodo": [2019, 2024], "reloj": RELOJ, "limite_segundos": 900,
            "deadline": "cooperativo, comprobado entre lotes y antes/después de cada fit; no cancelación exacta a 900 s",
            "salida_base": str(raiz_v2 / "pilotos_exploratorios"),
            "ablacion": {"excluidas": EXCLUIDAS, "motivo": "Sin vecindario de observaciones; sin ACAG calibrado con monitores "
                         "ni su climatología 2018–2024, potencial anticipación temporal. Whitelist explícita restante."},
            "calibracion": "global, separada, sin refit; Duan y delta Huber sólo con cal; sin CQR",
            "advertencia": "Histórico ya explorado en v1. Piloto no confirmatorio; Huber y cuantiles no estiman la media. "
                           "Transferencia retrospectiva, no pronóstico operativo. Entrenamiento mixto; métricas test globales "
                           "y subconjunto QC validado/usable_native. Cal no es evaluación independiente."}


def escribir_json(ruta: Path, datos) -> None:
    texto = json.dumps(datos, ensure_ascii=False, indent=2, allow_nan=False)
    temporal = ruta.with_suffix(ruta.suffix + ".part")
    temporal.write_text(texto, encoding="utf-8")
    os.replace(temporal, ruta)


def ejecutar(etiqueta: str, limite=900, v1=V1, raiz_v2=RAIZ_V2) -> dict:
    inicio = time.monotonic()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", etiqueta) or not 1 <= limite <= 900:
        raise ValueError("Etiqueta o límite inválido")
    v1, raiz_v2 = v1.resolve(), raiz_v2.resolve()
    if v1 == raiz_v2 or v1 in raiz_v2.parents or raiz_v2 in v1.parents:
        raise ValueError("Las raíces v1 y v2 deben ser independientes")
    if Path("/Volumes/Datos") in raiz_v2.parents or REPO == raiz_v2 or REPO in raiz_v2.parents:
        raise ValueError("La salida no puede estar en datos crudos ni en el repositorio")
    salida = raiz_v2 / "pilotos_exploratorios" / etiqueta
    if salida.exists():
        raise FileExistsError("La etiqueta ya existe; no se sobrescribe")
    contexto = plan(v1, raiz_v2)
    if "lightgbm" not in contexto["motores"]:
        raise ValueError("LightGBM no está disponible; no se instala nada")
    from motores_v2 import recetas_de, crear_modelo
    from perdidas_v2 import variante_de_etiqueta, delta_huber, a_escala_original
    pa.set_cpu_count(2)
    pa.set_io_thread_count(2)
    cfg_path = V2 / "config_v2.json"
    cfg = json.loads(cfg_path.read_text())
    recetas = recetas_de(cfg, hilos=2)
    for motor in contexto["motores"]:
        recetas[motor]["num_boost_round"] = RONDAS
    manifiesto_path = raiz_v2 / "pliegues_v2.json"
    manifiesto = json.loads(manifiesto_path.read_text())
    for fuente in contexto["fuentes"].values():
        sha = hash_archivo(Path(fuente["ruta"]))
        if sha != fuente["sha256_declarado_panel"]:
            raise ValueError("El panel no coincide con su SHA256 declarado")
        fuente.update(sha256_verificado_panel=sha, qc_sha256=hash_archivo(Path(fuente["qc_ruta"])))
    contexto.update(limite_segundos=limite, etiqueta=etiqueta, recetas={m: recetas[m] for m in contexto["motores"]},
                    codigo={p.name: hash_archivo(p) for p in (Path(__file__), V2 / "motores_v2.py", V2 / "perdidas_v2.py")},
                    config_sha256=hash_archivo(cfg_path), pliegues_sha256=hash_archivo(manifiesto_path))
    contexto["config_hash"] = hash_json(contexto)
    salida.mkdir(parents=True, exist_ok=False)
    escribir_json(salida / "config.json", contexto)
    resultados, completados = [], []

    def comprobar():
        if time.monotonic() - inicio >= limite:
            raise TimeoutError("Presupuesto del piloto agotado; resultados parciales conservados")

    estado = "completo"
    try:
        for pol in UNIDADES:
            comprobar()
            feats = [c for c in cfg["motores"]["eje_A"]["predictores"][pol] if c not in EXCLUIDAS]
            pool = leer_muestra(v1 / "paneles" / f"panel_{pol}.parquet", feats, comprobar)
            folds = manifiesto["contaminantes"][pol]["protocolos"]["LRO"]["pliegues"]
            bio = next(f["estaciones_prueba"] for f in folds if f["grupo"] == "RVIII")
            particiones = dividir(pool, bio)
            del pool
            particiones = unir_calidad(particiones, Path(contexto["fuentes"][pol]["qc_ruta"]), comprobar)
            fuente = contexto["fuentes"][pol]
            if hash_archivo(Path(fuente["qc_ruta"])) != fuente["qc_sha256"]:
                raise ValueError("QC cambió durante su lectura")
            stat = Path(fuente["ruta"]).stat()
            if (stat.st_size, stat.st_mtime_ns) != (fuente["bytes"], fuente["mtime_ns"]):
                raise ValueError("El panel cambió durante su lectura")
            for prueba, partes in particiones.items():
                sello = {k: {"n": len(d), "station_days": len(d.groupby(["estacion", "fecha_fuente"])),
                             "qc_conteos": d.qc.fillna("sin_bandera").value_counts().to_dict(),
                             "claves_sha256": identidad_filas(d), "datos_sha256": identidad_filas(d, [*feats, "obs"])}
                         for k, d in partes.items()}
                escribir_json(salida / f"seleccion_{pol}_{prueba}.json", {"predictores": feats, "seleccion": sello})
                pd.concat([d[["estacion", "ts_utc", "fecha_fuente", "qc", "fuente"]].assign(particion=k) for k, d in partes.items()]).to_parquet(
                    salida / f"filas_{pol}_{prueba}.parquet", index=False)
                tr, cal, test = (partes[k] for k in ("ajuste", "cal", "test"))
                Xtr, Xcal, Xtest = (d[feats].to_numpy(dtype="float32") for d in (tr, cal, test))
                validado = test.qc.isin(("validado", "usable_native")).to_numpy()
                delta_comun = None
                for motor in contexto["motores"]:
                    raw = {}
                    for variante in VARIANTES:
                        comprobar()
                        v = variante_de_etiqueta(variante)
                        if variante == "huber":
                            if delta_comun is None:
                                raise ValueError("Falta delta común calibrado por LightGBM MSE")
                            v = v.con_delta(delta_comun)
                        modelo = crear_modelo(motor, recetas, v, 0, replica=0, k=0)
                        t0 = time.monotonic()
                        modelo.ajustar(Xtr, tr.obs.to_numpy())
                        comprobar()
                        pc, pt = modelo.predecir(Xcal), modelo.predecir(Xtest)
                        comprobar()
                        extras = {}
                        if variante == "l2_original" and motor == "lightgbm":
                            delta_comun = delta_huber(cal.obs.to_numpy() - pc)
                        if variante == "huber":
                            extras.update(delta_huber_desde_cal_lg=delta_comun)
                        if variante == "l2_log_smearing":
                            factor = duan_global(cal.obs, pc)
                            pred = np.maximum(np.exp(pt) * factor - 1, 0)
                            extras["factor_duan_desde_cal"] = factor
                        else:
                            pred = a_escala_original(pt, v)
                        if variante.startswith("q"):
                            raw[variante] = pred
                        registro = {"contaminante": pol, "unidad": UNIDADES[pol], "prueba": prueba, "motor": motor,
                                    "variante": variante, "segundos": time.monotonic() - t0,
                                    "test_claves_sha256": sello["test"]["claves_sha256"],
                                    "horario": metricas(test.obs, pred),
                                    "horario_qc_validado": metricas(test.obs.to_numpy()[validado], pred[validado]) if validado.any() else None,
                                    "qc_validado_n": int(validado.sum()), **extras}
                        if variante in ("l2_original", "l2_log_smearing"):
                            registro["diario_fuente_media"] = diario(test, pred)
                        predicciones = test[["estacion", "ts_utc", "fecha_fuente", "obs", "qc", "fuente"]].copy()
                        predicciones["pred"] = pred
                        predicciones.to_parquet(salida / f"pred_{pol}_{prueba}_{motor}_{variante}.parquet", index=False)
                        resultados.append(registro)
                        completados.append(f"{pol}/{prueba}/{motor}/{variante}")
                        escribir_json(salida / "metricas.json", resultados)
                        escribir_json(salida / "estado.json", {"estado": "en_curso", "completados": completados})
                    reporte, ordenados = cuantiles(test.obs.to_numpy(), raw)
                    reporte["qc_validado"] = cuantiles(test.obs.to_numpy()[validado], {q: x[validado] for q, x in raw.items()})[0] if validado.any() else None
                    escribir_json(salida / f"cuantiles_{pol}_{prueba}_{motor}.json", reporte)
                    qs = test[["estacion", "ts_utc", "fecha_fuente", "obs", "qc", "fuente"]].copy()
                    for q in raw:
                        qs[q + "_bruto"], qs[q + "_reordenado"] = raw[q], ordenados[q]
                    qs.to_parquet(salida / f"intervalos_{pol}_{prueba}_{motor}.parquet", index=False)
            del particiones
    except TimeoutError as exc:
        estado, motivo = "parcial", str(exc)
    except Exception as exc:
        escribir_json(salida / "estado.json", {"estado": "error", "motivo": str(exc), "completados": completados})
        raise
    pd.json_normalize(resultados).to_csv(salida / "metricas.csv", index=False)
    final = {"estado": estado, "completados": completados, "segundos": time.monotonic() - inicio,
             "salida": str(salida), "motivo": motivo if estado == "parcial" else None}
    escribir_json(salida / "estado.json", final)
    return final


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accion", choices=("plan", "ejecutar"), nargs="?", default="plan")
    parser.add_argument("--etiqueta")
    parser.add_argument("--limite-segundos", type=int, default=900)
    args = parser.parse_args(argv)
    if args.accion == "ejecutar" and not args.etiqueta:
        parser.error("ejecutar necesita --etiqueta nueva")
    resultado = plan() if args.accion == "plan" else ejecutar(args.etiqueta, args.limite_segundos)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
