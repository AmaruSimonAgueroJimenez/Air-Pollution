"""Carga cerrada de mediciones persistidas para una batería NUEVA (EMC5, D69).

API: ``cargar(ruta, *, sha256, umbrales) -> (mediciones, procedencia)``.
La huella SHA-256 esperada, hexadecimal minúscula de 64 caracteres, debe llegar
por un canal externo al JSON. ``umbrales`` aporta ``sha256_json``,
``sha256_texto`` y ``a("SEL_UMBRAL_H")``; no se abre ningún archivo de M0.
Su texto vigente puede ser posterior: se ancla aquí sólo el histórico v2.5.

Se invierte el resumen ``meteo-combinada-costo/1``: ``mediciones`` pasa a
``puntos``, ``mes_real_leido`` a ``real_era5`` e ``insumos_bytes`` a ``bytes``.
Los procesos MEDIDOS salen de ``contencion``, no de la proyección histórica.
El entero de bytes de ``mes_real`` y los diccionarios de los otros puntos
conservan su tipo. No se reconstruyen los PID eliminados, las tuplas ni el
valor no finito que pasó a null: se conserva None, también en las cargas.
Los PID y el tipo tupla no los consume ``proyectar`` del contrato original;
la admisibilidad de recursos/tiempos desconocidos queda a proyectar/veredictos.

No mide, proyecta, evalúa recursos ni aprueba resultados. Quien llama debe
comparar exactamente la proyección reconstruida con la original usando el
código histórico, y ejecutar y declarar la suite de la batería NUEVA. Cargar
no modifica ni aprueba la historia, aunque su recorte fuera pendiente o su
carga no fuese libre. No hay lecturas DMC ni datos meteorológicos brutos.
Sólo se abre el JSON indicado; las huellas de sus lecturas no se siguen.
"""

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat


SHA_TEXTO_HISTORICO = "7771e830c526d8a0da93453e7e2d821896ba797147d14803969907ce5749589d"
PUNTOS = ("qc", "pliegue", "tf", "m5", "grilla", "mes_real", "contencion")
_CLAVES = frozenset((
    "a_escala", "aislada", "carga", "carga_es_excluyente", "carga_referencia_historica",
    "escala", "esquema", "fallas_escala", "lecturas", "mediciones", "mes_real_leido",
    "procesos_por_fase", "proyeccion", "recorte", "recorte_pendiente", "sistema",
    "umbral_recorte_h", "umbrales", "veredicto",
))
# Presencia de los campos directos usados por proyectar y de los envoltorios
# de medir. No es otra validación numérica ni una nueva regla científica.
_CAMPOS_PUNTO = {
    "qc": ("ms_por_hora", "anchas_tablas", "memoria_antes_unidades_gb",
           "memoria_por_meses", "horas_estacion"),
    "pliegue": ("horas_dato", "estaciones", "pliegue_tibio", "por_estacion_prueba_s",
                "prueba", "pliegue", "prueba_max_p1", "filas_c_s", "residuos_s",
                "en_horas_residuos_s", "clima_a_s", "residuos_tablas", "filas_residuos",
                "representatividad_s", "insumos_bytes"),
    "tf": ("celdas", "pasadas", "memoria_tras_fabricar_gb", "insumos_bytes"),
    "m5": ("pixeles", "celdas_salud", "pixeles_producto", "salud", "pixeles_netcdf",
           "lluvia", "horas", "operador_salud", "bytes_netcdf", "insumos_bytes"),
    "grilla": ("celdas", "celdas_medidas", "horas", "configuraciones", "operador_mayor",
               "insumos_bytes"),
    "mes_real": ("huella", "lectura", "horas", "pixeles", "insumos_bytes",
                 "huellas_lecturas_reales"),
    "contencion": ("procesos", "solo_s", "copias_s", "factor", "memoria_pico_gb", "celdas"),
}
_ENVOLTORIO = ("total", "memoria_inicio_gb", "memoria_pico_gb", "lecturas_reales", "carga")


class ErrorReutilizacionCosto(ValueError):
    """El archivo no satisface el contrato cerrado de reutilización."""


def _sha(valor, nombre):
    if not isinstance(valor, str) or re.fullmatch(r"[0-9a-f]{64}", valor) is None:
        raise ErrorReutilizacionCosto(f"{nombre}: se exige SHA-256 hexadecimal minúscula de 64 caracteres")
    return valor


def _campos(objeto, campos, nombre):
    if not isinstance(objeto, dict):
        raise ErrorReutilizacionCosto(f"{nombre}: se exige un objeto JSON")
    if not set(campos).issubset(objeto):
        raise ErrorReutilizacionCosto(f"{nombre}: faltan campos obligatorios")


def _leer_regular(ruta):
    """No seguir enlaces finales ni bloquearse con una FIFO, tampoco ante sustitución."""
    try:
        ruta = Path(ruta)
        if ruta.suffix.lower() == ".zip":
            raise ErrorReutilizacionCosto("la entrada debe ser JSON, no un archivo ZIP")
        previo = ruta.lstat()
        if not stat.S_ISREG(previo.st_mode):
            raise ErrorReutilizacionCosto("la entrada debe ser un archivo regular sin enlace simbólico")

        def abrir(nombre, flags):
            return os.open(nombre, flags | os.O_NOFOLLOW | os.O_NONBLOCK)

        with open(ruta, "rb", opener=abrir) as archivo:
            antes = os.fstat(archivo.fileno())
            if (not stat.S_ISREG(antes.st_mode)
                    or (antes.st_dev, antes.st_ino) != (previo.st_dev, previo.st_ino)):
                raise ErrorReutilizacionCosto("la entrada cambió o no es un archivo regular")
            datos = archivo.read()
            despues = os.fstat(archivo.fileno())
        if (antes.st_size, antes.st_mtime_ns, antes.st_ctime_ns) != (
                despues.st_size, despues.st_mtime_ns, despues.st_ctime_ns):
            raise ErrorReutilizacionCosto("la entrada cambió durante la lectura")
        return datos
    except (OSError, TypeError, ValueError) as exc:
        if isinstance(exc, ErrorReutilizacionCosto):
            raise
        # No incluir la ruta, ni el contenido, en los mensajes de error.
        raise ErrorReutilizacionCosto("no se pudo leer un archivo JSON regular") from None


def _objeto_unico(pares):
    objeto = {}
    for clave, valor in pares:
        if clave in objeto:
            raise ErrorReutilizacionCosto("JSON: clave duplicada")
        objeto[clave] = valor
    return objeto


def _constante_prohibida(_):
    raise ErrorReutilizacionCosto("JSON: NaN e infinitos no están permitidos; se exige null")


def _real_finito(texto):
    valor = float(texto)
    if not math.isfinite(valor):
        _constante_prohibida(texto)
    return valor


def _json_estricto(datos):
    try:
        return json.loads(datos.decode("utf-8"), object_pairs_hook=_objeto_unico,
                          parse_constant=_constante_prohibida, parse_float=_real_finito)
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, ErrorReutilizacionCosto):
            raise
        raise ErrorReutilizacionCosto("la entrada no es JSON UTF-8 estricto") from None


def _validar(contenido, umbrales):
    _campos(contenido, _CLAVES, "costo")
    if set(contenido) != _CLAVES or contenido["esquema"] != "meteo-combinada-costo/1":
        raise ErrorReutilizacionCosto("esquema o conjunto de claves de costo no reconocido")
    for clave in ("a_escala", "aislada", "mes_real_leido"):
        if contenido[clave] is not True:
            raise ErrorReutilizacionCosto(f"{clave}: debe ser True")
    if contenido["fallas_escala"] != []:
        raise ErrorReutilizacionCosto("fallas_escala debe ser una lista vacía")
    if contenido["carga_es_excluyente"] is not False:
        raise ErrorReutilizacionCosto("la carga histórica no puede ser excluyente")
    referencia = contenido["carga_referencia_historica"]
    if type(referencia) not in (int, float) or referencia != 2:
        raise ErrorReutilizacionCosto("carga_referencia_historica debe ser 2")

    for clave in ("escala", "sistema", "carga", "proyeccion", "procesos_por_fase", "veredicto"):
        _campos(contenido[clave], (), clave)
        if not contenido[clave]:
            raise ErrorReutilizacionCosto(f"{clave}: objeto vacío")
    _campos(contenido["sistema"], ("memoria_fisica_bytes", "nucleos"), "sistema")
    _campos(contenido["carga"], ("inicio", "inicio_libre", "maxima_ajena", "libre"), "carga")
    _campos(contenido["proyeccion"], ("procesos",), "proyeccion")
    procesos_historicos = contenido["proyeccion"]["procesos"]
    if type(procesos_historicos) is not int or procesos_historicos < 1:
        raise ErrorReutilizacionCosto("proyeccion.procesos: se exige un entero positivo")
    if not isinstance(contenido["lecturas"], list) or not contenido["lecturas"]:
        raise ErrorReutilizacionCosto("lecturas: se exige una lista no vacía")
    if contenido["recorte"] not in ("mod11", "mod23", "pendiente"):
        raise ErrorReutilizacionCosto("recorte: valor histórico no reconocido")
    if type(contenido["recorte_pendiente"]) is not bool:
        raise ErrorReutilizacionCosto("recorte_pendiente: se exige booleano")

    historicos = contenido["umbrales"]
    _campos(historicos, ("sha256_json", "sha256_texto", "sha256_texto_vigente"), "umbrales")
    try:
        for clave in ("sha256_json", "sha256_texto"):
            esperado = _sha(getattr(umbrales, clave), f"umbrales.{clave}")
            if _sha(historicos[clave], f"histórico.{clave}") != esperado:
                raise ErrorReutilizacionCosto("las huellas del JSON o texto de M0 no coinciden con U")
        if historicos["sha256_texto_vigente"] != SHA_TEXTO_HISTORICO:
            raise ErrorReutilizacionCosto("el texto histórico vigente no es el v2.5 fijado")
        umbral = umbrales.a("SEL_UMBRAL_H")
    except (AttributeError, KeyError, TypeError):
        raise ErrorReutilizacionCosto("umbrales: faltan huellas de M0 o SEL_UMBRAL_H") from None
    for valor in (umbral, contenido["umbral_recorte_h"]):
        if type(valor) not in (int, float) or valor != 36:  # no-umbral: identidad del contrato histórico fijado, no regla nueva
            raise ErrorReutilizacionCosto("SEL_UMBRAL_H y umbral_recorte_h deben ser 36 h")

    puntos = contenido["mediciones"]
    _campos(puntos, PUNTOS, "mediciones")
    if set(puntos) != set(PUNTOS):
        raise ErrorReutilizacionCosto("mediciones debe contener exactamente los siete puntos conocidos")
    for nombre in PUNTOS:
        punto = puntos[nombre]
        _campos(punto, _CAMPOS_PUNTO[nombre], f"mediciones.{nombre}")
        if punto.get("estado") in ("sin_medir", "SIN_MEDIR", "pendiente"):
            raise ErrorReutilizacionCosto(f"{nombre}: punto sin medir")
        if "bytes" in punto or "pid" in punto:
            raise ErrorReutilizacionCosto(f"{nombre}: campos ajenos al resumen persistido")
        if nombre != "contencion":
            _campos(punto, _ENVOLTORIO, f"mediciones.{nombre}")
        if nombre in ("pliegue", "tf", "m5", "grilla"):
            _campos(punto["insumos_bytes"], (), f"{nombre}.insumos_bytes")
    if type(puntos["mes_real"]["insumos_bytes"]) is not int:
        raise ErrorReutilizacionCosto("mes_real.insumos_bytes: se exige un entero, no un diccionario")
    procesos = puntos["contencion"]["procesos"]
    if type(procesos) is not int or procesos < 1:
        raise ErrorReutilizacionCosto("contencion.procesos: se exige un entero positivo")


def cargar(ruta, *, sha256: str, umbrales, verificar=None) -> tuple[dict, dict]:
    """Leer, verificar y reconstruir; cualquier rechazo levanta ErrorReutilizacionCosto.

    ``procedencia`` contiene alias neutro, SHA y bytes del archivo, huellas
    históricas de U, recorte y procesos históricos y advertencia expresa.
    ``comparacion_proyeccion_original`` siempre queda ``pendiente``: esta API
    no importa costo ni certifica la equivalencia con la proyección anterior.
    Si se aporta ``verificar``, recibe (mediciones, contenido_original) de la misma
    lectura protegida antes de devolver, sin reabrir el archivo. Su excepción se propaga.
    El contenido debe ser un archivo regular final, no enlace, FIFO o ZIP.
    Los tipos y la finitud de recursos/tiempos se dejan a proyectar/veredictos.
    """
    esperado = _sha(sha256, "sha256 esperado externo")
    datos = _leer_regular(ruta)
    huella = hashlib.sha256(datos).hexdigest()
    if huella != esperado:
        raise ErrorReutilizacionCosto("SHA-256 del archivo no coincide con la esperada externamente")
    contenido = _json_estricto(datos)
    _validar(contenido, umbrales)
    puntos = {
        nombre: {("bytes" if clave == "insumos_bytes" else clave): valor
                 for clave, valor in punto.items()}
        for nombre, punto in contenido["mediciones"].items()
    }
    mediciones = {
        "esquema": "meteo-combinada-costo-mediciones/1",
        "escala": contenido["escala"], "a_escala": contenido["a_escala"],
        "fallas_escala": contenido["fallas_escala"], "real_era5": contenido["mes_real_leido"],
        "aislada": contenido["aislada"], "procesos": puntos["contencion"]["procesos"],
        "puntos": puntos, "sistema": contenido["sistema"], "carga": contenido["carga"],
    }
    procedencia = {
        "esquema": "meteo-combinada-reutilizacion-costo/1",
        "alias": "costo_m1_persistido", "sha256": huella, "bytes": len(datos),
        "umbrales_historicos": {clave: contenido["umbrales"][clave]
                                for clave in ("sha256_json", "sha256_texto", "sha256_texto_vigente")},
        "umbral_recorte_h_historico": contenido["umbral_recorte_h"],
        "recorte_historico": contenido["recorte"],
        "recorte_pendiente_historico": contenido["recorte_pendiente"],
        "procesos_proyeccion_historica": contenido["proyeccion"]["procesos"],
        "nueva_medicion": False, "comparacion_proyeccion_original": "pendiente",
        "advertencia": (
            "No es una medición nueva. Se reutiliza un resumen histórico en una batería NUEVA, "
            "que debe ejecutar y declarar su suite y esta procedencia. No altera ni aprueba la historia "
            "ni valida la proyección: falta compararla exactamente con la original usando costo de HEAD. "
            "Los null se conservan como desconocidos; la carga no implica máquina libre."
        ),
    }
    if verificar is not None:
        verificar(mediciones, contenido)
    return mediciones, procedencia


__all__ = ("ErrorReutilizacionCosto", "cargar")
