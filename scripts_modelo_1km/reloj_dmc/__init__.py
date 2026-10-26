"""Procedimiento para confirmar el reloj de las horas DMC (protocolo v1, anclado en C0).

Paquete de la compuerta C1. Manda el texto del protocolo; este código lo implementa.
El paquete no importa ``_comun_modelo`` ni ``_common`` (§9) y no hace E/S al importarse.
Toda ejecución va con ``python -B`` (§9: sin ``.pyc`` en los repositorios).
"""
import sys as _sys

_sys.dont_write_bytecode = True
