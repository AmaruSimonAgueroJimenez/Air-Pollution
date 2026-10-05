"""Produce la serie completa de superficies horarias de 1 km, en paralelo y reanudable.

No renderiza el informe: importa ``produccion`` y escribe exactamente los mismos NetCDF que escribiría
``MODELO_1KM_PRODUCCION=1``, con el mismo contrato y el mismo manifiesto por día.

**Se puede apagar el equipo en cualquier momento.** Cada día se escribe con ``.part`` + ``os.replace``
y sólo entonces se publica su manifiesto, así que no existe un archivo a medio escribir. Al relanzar
con el mismo comando, cada día ya publicado se salta en milisegundos y la producción continúa donde
quedó. Interrumpir con Ctrl-C pierde, como mucho, el día en curso.

Uso típico (todo el país, toda la serie, seis procesos):

    python -B scripts_modelo_1km/producir_serie.py

Sólo los años de los mapas, o una región (cada ámbito escribe en su propia raíz, así que producir
primero una región no pisa ni retrasa la serie nacional):

    python -B scripts_modelo_1km/producir_serie.py --anios 2000,2002,2004
    python -B scripts_modelo_1km/producir_serie.py --ambito rm
    python -B scripts_modelo_1km/producir_serie.py --ambito biobio --solo-estado

El orden por omisión pone primero los años pares (los de los mapas cada dos años) y después el
resto: así los mapas se pueden armar sin esperar a que termine toda la serie.
"""
from __future__ import annotations

import argparse
import json
import logging
import multiprocessing as mp
import os
import sys
import time
from datetime import date
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

from _comun_modelo import AMBITOS_GRILLA  # noqa: E402

DESDE_POR_OMISION = "2000-01-01"
HASTA_POR_OMISION = "2026-09-13"


def _rango_anio(anio: int, desde: str, hasta: str) -> tuple[str, str] | None:
    """Intersección del año calendario con el período pedido."""
    a, b = max(f"{anio}-01-01", desde), min(f"{anio}-12-31", hasta)
    return (a, b) if a <= b else None


def _orden(anios: list[int], salto_primero: int) -> list[int]:
    """Primero los años que caen en el muestreo de los mapas, después el resto."""
    if salto_primero <= 1:
        return anios
    base = min(anios)
    prioritarios = [a for a in anios if (a - base) % salto_primero == 0]
    return prioritarios + [a for a in anios if a not in set(prioritarios)]


def _trabajar(trabajos: list[tuple[str, int]], args, hilos: int, indice: int) -> None:
    os.environ["MODELO_1KM_HILOS_PREDICCION"] = str(hilos)
    for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ[v] = str(hilos)
    try:                                         # el fork hereda el BLAS del padre: se limita en caliente
        from threadpoolctl import threadpool_limits
        threadpool_limits(hilos)
    except Exception:
        pass
    import produccion as P
    from _comun_modelo import SUPERFICIES_ROOT, carpeta_ambito, celdas_de_ambito

    log = logging.getLogger("modelo_1km")
    entorno = P.entorno_desde_disco(args.sufijo)
    entorno.superficies_dir = carpeta_ambito(SUPERFICIES_ROOT, "superficies", args.sufijo, args.ambito)
    celdas = celdas_de_ambito(entorno.celdas, args.ambito)
    ctx, pol_ctx = None, None
    for pol, anio in trabajos:
        rango = _rango_anio(anio, args.desde, args.hasta)
        if rango is None:
            continue
        if pol != pol_ctx:                       # el contexto se reconstruye sólo al cambiar de contaminante
            ctx, pol_ctx = P.ContextoPrediccion(pol, celdas, entorno), pol
        t0 = time.perf_counter()
        hechos = omitidos = 0
        dias = P.fechas(*rango)
        # Los años que toca un proceso NO son contiguos (primero los pares), así que la ventana
        # satelital empieza de cero y se vuelve a calentar: pedirle a SatelitesDiarios un día
        # anterior al último lanza ValueError, y el resultado con calentamiento es el mismo.
        ctx.reiniciar_ventana_satelital()
        for k in range(15, 0, -1):               # calentamiento de las ventanas satelitales móviles
            ctx.satelites.dia(date.fromordinal(dias[0].toordinal() - k))
        for f in dias:
            _, nuevo = ctx.dia(f)
            hechos += nuevo
            omitidos += (not nuevo)
        log.info("[w%d] %s %d: %d días nuevos, %d ya estaban (%.1f min)", indice, pol, anio, hechos,
                 omitidos, (time.perf_counter() - t0) / 60)
        print(f"[w{indice}] {pol} {anio}: {hechos} nuevos, {omitidos} ya estaban, "
              f"{(time.perf_counter() - t0) / 60:.1f} min", flush=True)


def estado(raiz: Path, pols, desde: str, hasta: str) -> dict:
    """Cuántos días de cada contaminante y año ya están publicados."""
    fuera = {}
    for pol in pols:
        por_anio = {}
        for a in range(int(desde[:4]), int(hasta[:4]) + 1):
            d = raiz / pol / f"year={a}"
            por_anio[a] = len(list(d.rglob(f"{pol}_1km_*.nc"))) if d.exists() else 0
        fuera[pol] = por_anio
    return fuera


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--desde", default=DESDE_POR_OMISION)
    p.add_argument("--hasta", default=HASTA_POR_OMISION)
    p.add_argument("--contaminantes", default="pm25,no2")
    p.add_argument("--anios", default="", help="lista separada por comas; por omisión, todos los del período")
    p.add_argument("--ambito", default="nacional", choices=sorted(AMBITOS_GRILLA))
    p.add_argument("--procesos", type=int, default=6)
    p.add_argument("--salto-primero", type=int, default=2,
                   help="produce primero los años del muestreo de los mapas (0 o 1 lo desactiva)")
    p.add_argument("--sufijo", default=None, help="sufijo de carpeta (por omisión MODELO_1KM_ETIQUETA)")
    p.add_argument("--solo-estado", action="store_true", help="informa lo ya producido y termina")
    args = p.parse_args(argv)

    pols = tuple(c.strip() for c in args.contaminantes.split(",") if c.strip())
    anios = ([int(a) for a in args.anios.split(",") if a.strip()]
             or list(range(int(args.desde[:4]), int(args.hasta[:4]) + 1)))

    sys.path.insert(0, str(AQUI))
    from _comun_modelo import SUPERFICIES_ROOT, carpeta_ambito
    sufijo = args.sufijo if args.sufijo is not None else (f"_{e}" if (e := os.environ.get("MODELO_1KM_ETIQUETA", "")) else "")
    args.sufijo = sufijo
    raiz = carpeta_ambito(SUPERFICIES_ROOT, "superficies", sufijo, args.ambito)

    salida = AQUI.parent / "output_files" / f"modelo_1km{sufijo}"
    salida.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(salida / "produccion_serie.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
    logging.getLogger("modelo_1km").addHandler(fh)
    logging.getLogger("modelo_1km").setLevel(logging.INFO)

    if args.solo_estado:
        e = estado(raiz, pols, args.desde, args.hasta)
        for pol, por_anio in e.items():
            hechos = sum(por_anio.values())
            print(f"{pol}: {hechos} días publicados")
            print("   " + " ".join(f"{a}:{n}" for a, n in sorted(por_anio.items()) if n))
        return 0

    trabajos = [(pol, a) for pol in pols for a in _orden(anios, args.salto_primero)]
    n = max(1, min(args.procesos, len(trabajos)))
    hilos = max(1, (os.cpu_count() or 8) // n)
    repartos = [trabajos[i::n] for i in range(n)]
    print(f"{len(trabajos)} trabajos (contaminante × año) en {n} procesos de {hilos} hilos · ámbito "
          f"{args.ambito} · {args.desde} → {args.hasta}\nsuperficies en {raiz}\nbitácora "
          f"{salida / 'produccion_serie.log'}", flush=True)

    ctx_mp = mp.get_context("fork")
    procesos = [ctx_mp.Process(target=_trabajar, args=(r, args, hilos, i), daemon=False)
                for i, r in enumerate(repartos)]
    t0 = time.perf_counter()
    for pr in procesos:
        pr.start()
    codigos = []
    try:
        for pr in procesos:
            pr.join()
            codigos.append(pr.exitcode)
    except KeyboardInterrupt:                     # apagar a mitad no corrompe nada: el día en curso se repite
        for pr in procesos:
            pr.terminate()
        print("\ninterrumpido; relanza el mismo comando para continuar donde quedó", flush=True)
        return 130
    resumen = {"desde": args.desde, "hasta": args.hasta, "ambito": args.ambito,
               "contaminantes": list(pols), "procesos": n, "horas": round((time.perf_counter() - t0) / 3600, 2),
               "salidas": codigos, "publicados": estado(raiz, pols, args.desde, args.hasta)}
    (salida / "produccion_serie.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"listo en {resumen['horas']} h; códigos de salida {codigos}", flush=True)
    return 0 if all(c == 0 for c in codigos) else 1


if __name__ == "__main__":
    raise SystemExit(main())
