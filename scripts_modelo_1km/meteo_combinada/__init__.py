"""Producto meteorológico combinado ERA5-Land + DMC (protocolo v2.4; compuerta M1).

Paquete del código de M1. Manda el texto del protocolo
(``APH/auditoria/20261023/meteo_combinada/enmienda3/PROTOCOLO_METEO_COMBINADA_v2.4.md``); este código lo
implementa y ``DISENO_IMPLEMENTACION_M1.md`` fija módulos, firmas y pruebas.

Al importarse, y sin ninguna E/S:
- fija ``sys.dont_write_bytecode = True`` (toda ejecución va con ``python -B``: sin ``.pyc`` en los repositorios);
- si numpy todavía no está cargado, fija en «1» los hilos del álgebra lineal (``OMP_NUM_THREADS``,
  ``OPENBLAS_NUM_THREADS`` y ``MKL_NUM_THREADS``; §8 del texto y MC-36 del diseño). Si numpy ya está cargado,
  ``entorno.fijar_hilos`` lo comprueba con threadpoolctl y falla si no quedan en 1. Los procesos hijos heredan
  las variables.
"""
import os as _os
import sys as _sys

_sys.dont_write_bytecode = True

VARIABLES_HILOS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
UN_HILO = "1"

if "numpy" not in _sys.modules:
    for _variable in VARIABLES_HILOS:
        _os.environ[_variable] = UN_HILO
    del _variable
