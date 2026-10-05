"""Compara la validación de una etiqueta contra la definitiva y aplica la regla fijada de antemano.

Lee ``output_files/modelo_1km[_<etiqueta>]/eval_niveles_<pol>.csv``, que es la misma tabla que usa el
informe (docs/modelo_1km_horario.qmd); en Air-Pollution-Health-Chile también la leen el manuscrito y su
suplemento, que importan MEJORA_MINIMA y FACTOR_RUIDO de este módulo. **No** lee ``metricas.json``: ese archivo sólo guarda los
protocolos que corrió la última ejecución, de modo que el de PM₂,₅ hoy tiene únicamente LOSO y una
comparación basada en él saldría en blanco justo para el contaminante principal, sin avisar.

La regla se fijó antes de ver ningún resultado: **decide el LRO**, dejar una región fuera. El defecto
que se quiere corregir vive entre estaciones, donde un protocolo que deja fuera una sola estación
apenas lo ve.

**Suelo de ruido.** Un ΔR² pequeño no significa nada por sí solo. Reajustar el mismo modelo sobre el
mismo panel ya mueve las métricas, porque las filas de entrenamiento se submuestrean: comparando el
PM₂,₅ de la etiqueta `no2sincosta` contra el definitivo, que deberían ser idénticos porque esa corrida
no tocó PM₂,₅, el LRO se movió +0,004 horario, +0,005 diario, +0,009 mensual y +0,028 anual (el LOSO,
que sí reutilizó sus pliegues en caché, se movió 0,000). Por eso ``--nulo`` toma un par que debería ser
idéntico, mide cuánto se mueve, y la regla exige que el efecto lo supere con holgura.

**Base.** Para PM₂,₅ el definitivo en disco es del 2026-09-24 y sus LBO/LRO/LPO se recalcularon el 30
bajo otro código; comparar contra él mide la deriva del código, no el cambio de diseño. Usar
``--base pm25:no2sincosta``.

    python -B scripts_modelo_1km/comparar_etiquetas.py --etiqueta interp \
        --base pm25:no2sincosta --nulo pm25:no2sincosta
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
PROTOCOLOS = ("loso", "lbo", "lro", "lpo")
NIVELES = ("horario", "diario", "mensual", "anual")
MEJORA_MINIMA = 0.01       # ΔR² mínimo en términos absolutos
FACTOR_RUIDO = 2.0         # y además hay que duplicar lo que mueve un reajuste sin cambio de diseño
DECIDEN = ("horario", "diario")   # los niveles con más pares; mensual y anual los mueve el ruido


def ruta(pol: str, etq: str) -> Path:
    return RAIZ / "output_files" / (f"modelo_1km_{etq}" if etq else "modelo_1km") / f"eval_niveles_{pol}.csv"


def leer(pol: str, etq: str) -> pd.DataFrame | None:
    r = ruta(pol, etq)
    if not r.exists():
        print(f"  FALTA {r}", file=sys.stderr)
        return None
    return pd.read_csv(r)


def nacional(d: pd.DataFrame) -> pd.DataFrame:
    return d[d["estrato"] == "Chile"].set_index(["protocolo", "nivel"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--etiqueta", default="interp")
    ap.add_argument("--base", default="", help="etiqueta de referencia; admite 'pm25:etq,no2:etq' "
                    "o una sola etiqueta para todos (vacío = el definitivo)")
    ap.add_argument("--nulo", default="", help="par que debería ser idéntico, para medir el suelo de "
                    "ruido; mismo formato que --base")
    ap.add_argument("--contaminantes", default="pm25,no2")
    a = ap.parse_args(argv)
    pd.set_option("display.width", 200)

    def por_pol(spec: str, pol: str) -> str:
        if ":" not in spec:
            return spec
        for parte in spec.split(","):
            k, _, v = parte.partition(":")
            if k.strip() == pol:
                return v.strip()
        return ""

    def deltas(pol: str, base: str, otra: str) -> dict:
        A, B = leer(pol, base), leer(pol, otra)
        if A is None or B is None:
            return {}
        na, nb = nacional(A), nacional(B)
        return {k: float(nb.loc[k]["r2"] - na.loc[k]["r2"])
                for k in na.index if k in nb.index}

    veredictos, incompleto = {}, False
    for pol in a.contaminantes.split(","):
        base = por_pol(a.base, pol)
        ruido = deltas(pol, "", por_pol(a.nulo, pol)) if a.nulo else {}
        A, B = leer(pol, base), leer(pol, a.etiqueta)
        print(f"\n{'=' * 78}\n{pol.upper()}: {base or 'definitivo'}  vs  {a.etiqueta}\n{'=' * 78}")
        if ruido:
            print("  suelo de ruido (un par que debería ser idéntico): " +
                  ", ".join(f"{p.upper()} {n} {v:+.4f}" for (p, n), v in sorted(ruido.items())
                            if p == "lro"))
        if A is None or B is None:
            print("  sin tabla de evaluación en los dos lados; no se puede comparar")
            incompleto = True
            continue
        na, nb = nacional(A), nacional(B)
        filas = []
        for prot in PROTOCOLOS:
            for niv in NIVELES:
                k = (prot, niv)
                if k not in na.index and k not in nb.index:
                    continue
                ra = na.loc[k] if k in na.index else None
                rb = nb.loc[k] if k in nb.index else None
                filas.append({
                    "protocolo": prot.upper(), "nivel": niv,
                    "n": "" if rb is None else f"{int(rb['n']):,}",
                    "r2_base": None if ra is None else round(float(ra["r2"]), 4),
                    "r2_nuevo": None if rb is None else round(float(rb["r2"]), 4),
                    "dR2": None if ra is None or rb is None else round(float(rb["r2"] - ra["r2"]), 4),
                    "rmse_base": None if ra is None else round(float(ra["rmse"]), 3),
                    "rmse_nuevo": None if rb is None else round(float(rb["rmse"]), 3),
                    "ruido": round(abs(ruido[k]), 4) if k in ruido else None,
                })
        t = pd.DataFrame(filas)
        print(t.to_string(index=False, na_rep="falta"))
        if t["dR2"].isna().any():
            print("  AVISO: faltan celdas; la comparación está incompleta")
            incompleto = True

        lro = t[(t.protocolo == "LRO") & t["dR2"].notna()]
        otros = t[(t.protocolo != "LRO") & t["dR2"].notna()]
        if lro.empty:
            print("  AVISO: no hay LRO en los dos lados; la regla no se puede aplicar")
            incompleto = True
            continue
        def umbral(fila):
            r = fila.ruido if fila.ruido is not None and fila.ruido == fila.ruido else 0.0
            return max(MEJORA_MINIMA, FACTOR_RUIDO * r)

        decide = lro[lro.nivel.isin(DECIDEN)]
        print(f"\n  LRO, niveles que deciden ({', '.join(DECIDEN)}):")
        pasa = []
        for r in decide.itertuples():
            u = umbral(r)
            ok = r.dR2 >= u
            pasa.append(ok)
            print(f"    {r.nivel:9s} ΔR² {r.dR2:+.4f}   umbral {u:+.4f}"
                  f"{'  (ruido ' + format(r.ruido, '.4f') + ')' if r.ruido == r.ruido and r.ruido is not None else ''}"
                  f"   {'PASA' if ok else 'no pasa'}")
        otros_niv = lro[~lro.nivel.isin(DECIDEN)]
        if len(otros_niv):
            print("    informativos: " + ", ".join(f"{r.nivel} {r.dR2:+.4f}" for r in otros_niv.itertuples()))
        danio = otros[otros.apply(lambda r: r["dR2"] <= -umbral(r), axis=1)] if len(otros) else otros
        if len(danio):
            print("  Coste en los demás protocolos: " +
                  ", ".join(f"{r.protocolo} {r.nivel} {r.dR2:+.4f}" for r in danio.itertuples()))
        veredictos[pol] = bool(pasa) and all(pasa) and not len(danio)

        # el promedio nacional esconde el signo por zona: el defecto es regional por construcción
        for etiqueta, d in (("base", A), ("nuevo", B)):
            mz = d[(d.estrato_tipo == "macrozona") & (d.nivel == "diario") & (d.protocolo == "lro")]
            if len(mz):
                print(f"  LRO diario por macrozona ({etiqueta}): " +
                      ", ".join(f"{r.estrato} {r.r2:.3f}" for r in mz.itertuples()))

    print(f"\n{'=' * 78}")
    if incompleto:
        print("VEREDICTO: incompleto. No lanzar producción hasta cerrar lo que falta.")
        return 2
    gana = [p for p, v in veredictos.items() if v]
    print(f"VEREDICTO segun la regla fijada de antemano (decide el LRO):")
    for p, v in veredictos.items():
        print(f"  {p.upper()}: {'mejora' if v else 'no mejora'}")
    print("  -> " + ("conviene producir" if gana else "no conviene producir") +
          (f" (gana en {', '.join(x.upper() for x in gana)})" if gana else ""))
    print("  Recordar: la produccion debe usar el mismo diseno que se evaluo aqui.")
    return 0 if gana else 1


if __name__ == "__main__":
    raise SystemExit(main())
