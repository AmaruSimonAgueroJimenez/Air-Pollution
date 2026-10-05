#!/usr/bin/env python3
"""Verificación empírica del reloj SINCA (UTC−4 fijo frente a hora civil).

Prueba estructural, por estación, contaminante y año, sobre las etiquetas
horarias originales del exportador (``ts_local`` del derivado SINCA v1):

* En el cambio a horario de verano (primer domingo de septiembre en Chile
  continental) la hora civil 00:00 no existe. Un exportador en hora civil no
  puede emitir esa etiqueta; uno en reloj fijo emite las 24.
* En el fin del horario de verano (primer domingo de abril) una hora civil
  se repite. Un exportador en hora civil repite u omite una etiqueta; uno en
  reloj fijo emite exactamente 24 etiquetas distintas.

Veredicto por estación-año: ``reloj_fijo`` cuando ambos días traen 24
etiquetas distintas, incluida la hora civil inexistente; ``hora_civil``
cuando falta la inexistente o se repite la ambigua; ``sin_evidencia`` cuando
faltan etiquetas por otras causas (caída de la estación). Se usan las zonas
IANA regionales de ``config/sinca/politica_temporal.json`` sólo para
localizar las fechas de cambio; Aysén y Magallanes tienen sus propias reglas.

Prueba secundaria, informativa: corrimiento estacional del máximo diurno de
O3 (solar) entre verano e invierno; bajo reloj fijo no se corre, bajo hora
civil se corre una hora. No modifica datos ni la política temporal.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun_modelo import MODELO_ROOT, RAIZ, SINCA_DERIVADO, hash_codigo, leer_estaciones, log, publicar_json, publicar_parquet, version_sinca  # noqa: E402

POLITICA = json.loads((RAIZ / "config" / "sinca" / "politica_temporal.json").read_text(encoding="utf-8"))["sinca"]


def zona_de(region: str) -> str:
    return POLITICA["zonas_iana_por_region"].get(region, POLITICA["zona_iana_default"])


def transiciones(zona: str, anio: int) -> list[tuple[date, str, int]]:
    """Fechas locales con cambio de offset y la hora civil afectada.

    Devuelve (fecha, tipo, hora): tipo ``inexistente`` (adelanto) con la hora
    que desaparece, o ``ambigua`` (atraso) con la hora que se repite.
    """
    tz = ZoneInfo(zona)
    out = []
    t = datetime(anio, 1, 1, tzinfo=tz)
    fin = datetime(anio + 1, 1, 1, tzinfo=tz)
    prev = t.utcoffset()
    while t < fin:
        t2 = t + timedelta(hours=1)
        off = t2.utcoffset()
        if off != prev:
            delta = (off - prev).total_seconds() / 3600.0
            utc = t2.astimezone(ZoneInfo("UTC"))
            if delta > 0:   # adelanto: la hora civil que sigue a t no existe
                local_previa = t.replace(tzinfo=None)
                hora = (local_previa.hour + 1) % 24
                out.append((t2.date(), "inexistente", hora))
            else:           # atraso: la hora civil se repite
                local = t2.replace(tzinfo=None)
                out.append((local.date(), "ambigua", local.hour))
            prev = off
        t = t2
    return out


def evaluar_dia(etiquetas: pd.DatetimeIndex, fecha: date, tipo: str, hora: int) -> dict:
    dia = etiquetas[etiquetas.normalize() == pd.Timestamp(fecha)]
    horas = dia.hour.to_numpy()
    n, unicas = int(len(horas)), int(len(np.unique(horas)))
    presente = bool((horas == hora).any())
    repetida = int((horas == hora).sum()) > 1
    if n == 0:
        estado = "sin_etiquetas"
    elif tipo == "inexistente":
        estado = "reloj_fijo" if (presente and unicas == 24) else ("hora_civil" if (not presente and unicas == 23) else "sin_evidencia")
    else:
        estado = "hora_civil" if (repetida or unicas == 23 and n == 24) else ("reloj_fijo" if (unicas == 24 and n == 24) else "sin_evidencia")
    return {"fecha": fecha.isoformat(), "tipo": tipo, "hora_civil": int(hora), "etiquetas": n,
            "horas_unicas": unicas, "hora_presente": presente, "hora_repetida": repetida, "estado": estado}


def veredicto(estados: list[str]) -> str:
    if "hora_civil" in estados:
        return "hora_civil"
    if estados.count("reloj_fijo") >= 1 and "sin_evidencia" not in estados:
        return "reloj_fijo"
    if "reloj_fijo" in estados:
        return "reloj_fijo_parcial"
    return "sin_evidencia"


def prueba_o3(serie: pd.Series) -> dict | None:
    """Corrimiento del máximo diurno de O3 entre verano (oct–mar) e invierno (may–ago)."""
    if serie.empty:
        return None
    out = {}
    for nombre, meses_ in (("verano", (10, 11, 12, 1, 2, 3)), ("invierno", (5, 6, 7, 8))):
        s = serie[serie.index.month.isin(meses_)]
        if len(s) < 500:
            return None
        perfil = s.groupby(s.index.hour).mean()
        if perfil.isna().any() or len(perfil) < 24:
            return None
        p = perfil.to_numpy()
        k = int(np.argmax(p))
        # interpolación parabólica alrededor del máximo (hora fraccional)
        a, b, c = p[(k - 1) % 24], p[k], p[(k + 1) % 24]
        d = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
        out[f"pico_o3_{nombre}"] = float(k + d)
    out["corrimiento_o3"] = out["pico_o3_verano"] - out["pico_o3_invierno"]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--anios", default="2018-2026")
    ap.add_argument("--estaciones", help="lista separada por comas")
    ap.add_argument("--contaminantes", default="pm25,no2,o3")
    args = ap.parse_args(argv)
    a0, a1 = (int(x) for x in args.anios.split("-"))
    sel = set(x.strip() for x in args.estaciones.split(",")) if args.estaciones else None
    est = leer_estaciones().set_index("estacion")
    filas, detalle = [], []
    for pol in args.contaminantes.split(","):
        for carpeta in sorted(SINCA_DERIVADO.glob(f"estacion=*/contaminante={pol}")):
            estacion = carpeta.parent.name.split("=", 1)[1]
            if sel and estacion not in sel or estacion not in est.index:
                continue
            ruta = version_sinca(carpeta)
            if ruta is None:
                continue
            df = pd.read_parquet(ruta, columns=["ts_local", "obs"])
            etiquetas = pd.DatetimeIndex(pd.to_datetime(df["ts_local"]))
            zona = zona_de(str(est.loc[estacion, "region_sinca"]))
            serie_o3 = df.set_index(etiquetas)["obs"] if pol == "o3" else None
            for anio in range(a0, a1 + 1):
                del_anio = etiquetas[etiquetas.year == anio]
                if len(del_anio) < 24 * 30:
                    continue
                estados = []
                for fecha, tipo, hora in transiciones(zona, anio):
                    r = evaluar_dia(del_anio, fecha, tipo, hora)
                    r.update({"estacion": estacion, "contaminante": pol, "anio": anio, "zona_iana": zona})
                    detalle.append(r)
                    estados.append(r["estado"])
                fila = {"estacion": estacion, "contaminante": pol, "anio": anio, "zona_iana": zona,
                        "n_transiciones": len(estados), "estados": "|".join(estados),
                        "veredicto": veredicto(estados) if estados else "sin_transiciones"}
                if serie_o3 is not None:
                    o3 = prueba_o3(serie_o3[serie_o3.index.year == anio].dropna())
                    if o3:
                        fila.update(o3)
                filas.append(fila)
    if not filas:
        log.warning("Sin series para verificar")
        return 1
    tabla = pd.DataFrame(filas)
    salida = MODELO_ROOT / "verificacion_reloj_sinca"
    sha = publicar_parquet(tabla, salida / "veredictos.parquet")
    tabla.to_csv(salida / "veredictos.csv", index=False)
    pd.DataFrame(detalle).to_csv(salida / "detalle_transiciones.csv", index=False)
    resumen = tabla["veredicto"].value_counts().to_dict()
    o3_info = None
    if "corrimiento_o3" in tabla:
        c = tabla["corrimiento_o3"].dropna()
        if len(c):
            o3_info = {"n": int(len(c)), "mediana_h": float(c.median()),
                       "mediana_pico_verano_h": float(tabla["pico_o3_verano"].dropna().median()),
                       "mediana_pico_invierno_h": float(tabla["pico_o3_invierno"].dropna().median()),
                       "interpretacion": ("pico_o3_verano − pico_o3_invierno en horas de etiqueta; un reloj civil "
                                          "sumaría +1 h en verano, pero la estacionalidad fotoquímica del pico "
                                          "(desconocida a ±1 h) se mezcla con el reloj, así que esta prueba es "
                                          "sólo indicativa; la evidencia es la prueba estructural")}
    publicar_json({
        "schema": "airpollution.modelo-1km.reloj-sinca.v2", "hipotesis_modelo": "UTC-4 fijo, etiqueta fin de intervalo",
        "metodo_primario": "etiquetas presentes/repetidas en las fechas de cambio de hora civil (zoneinfo)",
        "resumen_veredictos": resumen, "estaciones_anios": int(len(tabla)),
        "sospechosas_hora_civil": tabla.loc[tabla["veredicto"] == "hora_civil",
                                            ["estacion", "contaminante", "anio"]].to_dict("records"),
        "prueba_secundaria_o3": o3_info, "codigo": hash_codigo(), "sha256": sha,
    }, salida / "resumen.json")
    log.info("Veredictos: %s → %s", resumen, salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
