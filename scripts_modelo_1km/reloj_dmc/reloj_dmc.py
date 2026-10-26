"""Fachada con los nombres de §9 («funciones puras»), repartidas en módulos sin solape.

§9 nombra un solo archivo ``reloj_dmc.py``; el código se reparte en módulos para poder escribirse en
paralelo, y este archivo conserva los 23 nombres del texto (riesgo R-35: se registra en el addendum
de C1 como cambio de implementación).

Es perezosa: importarla no carga ningún otro módulo del paquete (ni zoneinfo, ni numpy, ni pandas). Cada
nombre se resuelve la primera vez que se pide, importando sólo su módulo, y queda guardado aquí; el objeto es
el mismo del módulo, no una copia ni un envoltorio. ``NOMBRES_9`` sigue el orden de §9.

«e4» de §9 es la línea E4 (§4.4): en el código, ``lineas_fisicas.ajustes_e4`` calcula los ajustes armónicos
y ``lineas_fisicas.e4p`` da los estados de la línea; el nombre de §9 se resuelve a ``e4p`` (``ALIAS_9``).
Depende de: nada al importarse.
"""
from __future__ import annotations

import importlib

PAQUETE = "reloj_dmc"

# Nombre de §9 → módulo del paquete, en el orden del texto.
NOMBRES_9 = {
    "transiciones_utc": "tablas", "reglas_anteriores": "tablas", "territorio_y_P": "tablas",
    "elegir_pixel": "extraccion", "extraer_dmc": "extraccion", "extraer_era5land": "extraccion",
    "e1a": "lineas_registro", "e1b": "lineas_registro", "e1c": "lineas_registro", "e2": "lineas_registro",
    "e3": "lineas_fisicas", "e3_fina": "lineas_fisicas", "e4": "lineas_fisicas", "e6": "lineas_fisicas",
    "guardas": "guardas", "marcas": "guardas",
    "controles_red": "red", "calibrar_e3t": "red",
    "decidir_anio": "decision", "rachas": "decision",
    "politica": "politica", "verificar_politica": "politica", "validar_regla_reloj_dmc": "politica",
}
# Nombre de §9 → nombre en su módulo, cuando difieren.
ALIAS_9 = {"e4": "e4p"}

__all__ = sorted(NOMBRES_9)


def modulo_de(nombre: str) -> str:
    """Módulo completo («reloj_dmc.tablas») donde vive el nombre de §9; KeyError si no es de §9."""
    return f"{PAQUETE}.{NOMBRES_9[nombre]}"


def __getattr__(nombre: str):
    if nombre not in NOMBRES_9:
        raise AttributeError(f"module {__name__!r} has no attribute {nombre!r} (no es un nombre de §9)")
    objeto = getattr(importlib.import_module(modulo_de(nombre)), ALIAS_9.get(nombre, nombre))
    globals()[nombre] = objeto
    return objeto


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(NOMBRES_9))
