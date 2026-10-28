"""Fachada con los nombres de código que cita el texto, repartidos en módulos sin solape.

§8 del texto nombra los módulos y §2.1, §6.2 y §7.1 cinco funciones: ``qc_meteo_combinada`` (§2.1),
``decidir_combinacion`` (§6.2), ``lateral_monitores``, ``operador_grilla`` y ``mc_bloque`` (§7.1). Esta fachada los
conserva con su nombre (como la fachada del reloj, riesgo R-35; MC-20 del diseño).

Es perezosa: importarla no carga ningún otro módulo del paquete (ni numpy, ni pandas, ni zoneinfo). Cada nombre se
resuelve la primera vez que se pide, importando sólo su módulo, y queda guardado aquí; el objeto es el mismo del
módulo, no una copia ni un envoltorio.

Dueño: I0 en la ola 0; I22 la revisó en la ola 6, sin cambiar el código: los cinco nombres se resuelven al objeto de su
módulo (``qc_dmc_meteo``, ``decision`` y ``ambiental`` ya los implementan), y la importación sigue sin cargar nada
(``test_meteo_combinada.PruebasFachada``).
Lecturas propias (FAC-n): ninguna.
Depende de: nada al importarse.
"""
from __future__ import annotations

import importlib

PAQUETE = "meteo_combinada"

# Nombre del texto → módulo del paquete.
NOMBRES_TEXTO = {"qc_meteo_combinada": "qc_dmc_meteo", "decidir_combinacion": "decision",
                 "lateral_monitores": "ambiental", "operador_grilla": "ambiental", "mc_bloque": "ambiental"}

__all__ = sorted(NOMBRES_TEXTO)


def modulo_de(nombre: str) -> str:
    """Módulo completo («meteo_combinada.decision») donde vive un nombre del texto; KeyError si no es uno."""
    return f"{PAQUETE}.{NOMBRES_TEXTO[nombre]}"


def __getattr__(nombre: str):
    if nombre not in NOMBRES_TEXTO:
        raise AttributeError(f"module {__name__!r} has no attribute {nombre!r} (no es un nombre del texto)")
    objeto = getattr(importlib.import_module(modulo_de(nombre)), nombre)
    globals()[nombre] = objeto
    return objeto


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(NOMBRES_TEXTO))
