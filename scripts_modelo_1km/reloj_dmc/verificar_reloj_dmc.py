#!/usr/bin/env python3
"""Ejecutable del procedimiento del reloj DMC (§9): --sintetico (C1), --control-era5 (C3), --aplicar (C4).

Uso (siempre con el intérprete fijado y -B):
  ~/micromamba/envs/amb_v2/bin/python -B verificar_reloj_dmc.py --sintetico [--bateria] [--salida DIR] [--patron P]
  ~/micromamba/envs/amb_v2/bin/python -B verificar_reloj_dmc.py --control-era5 --addendum RUTA [--salida DIR]
  ~/micromamba/envs/amb_v2/bin/python -B verificar_reloj_dmc.py --aplicar --addendum RUTA --linea-cierre RUTA
                                          [--reanudar] [--errata RUTA] [--enmienda4 RUTA]

Responsabilidades propias (el resto es de los módulos):
- C4 se niega a correr en los cuatro casos de §10: difiere una huella de la lista cerrada del addendum de C1;
  ``git --no-optional-locks status --porcelain --untracked-files=all -- <rutas>`` no sale vacío en AP o APH,
  o el commit de C1 no es antecesor de origin/main de APH; no se cumple C2 o no se pudo tomar el candado;
  o intentos_aplicar.jsonl ya registra una corrida confirmatoria sin una errata confirmada.
- C2 (§3.1): línea de cierre, progreso.json (phase, status, final_verification, sha256) y el candado
  DMC/.meteo_download.lock abierto O_RDONLY con flock exclusivo sin bloqueo, RETENIDO hasta terminar de
  leer; «held» o «absent» fallan. Al terminar la lectura se recalculan las huellas (si cambian, aborta).
- Cerrojo: LOCAL/…/v1/intentos_aplicar.jsonl de sólo agregado, con cada intento (también los rechazados y
  los abortados) y sus huellas. avance.jsonl, dentro de la carpeta de la corrida, sólo con huellas y estado.
  Un candado propio de --aplicar (LOCAL/…/v1/.aplicar.lock) se retiene durante toda la corrida (VER-16).
- Carpeta HUMAN<AAAAMMDD>_RELOJ_DMC_1 (o _ERRATA<n>); orden de §5.2; sello al final (salidas.escribir_corrida).
- Consola sin veredictos: sólo conteos de avance (``consola``) y avisos fijos, nunca veredictos.
- Un proceso, ``nice``, sin multiprocesamiento; nada se escribe en /Volumes ni en los repositorios (R-49:
  la publicación de C5 es un paso aparte; con la Enmienda 2, E2-4, la huella de la política va entonces al
  registro del producto meteorológico combinado y no a insumos_tardios_v3.jsonl). Ningún script de este
  paquete se llama descargar_* ni download_*: así el control de descargas activas no se ve a sí mismo.

Inyección para pruebas: el Namespace puede traer ``configuracion`` (una ``Configuracion``: rutas, reloj de
pared, código fijado, catálogo de píxeles…). Nunca llega por la línea de comandos; sin ella rige
``configuracion_real()``.

Lecturas de implementación de este módulo (van al addendum de C1):
- VER-1. Formatos de E1-6 (R-06). ``addendum_c1.json`` (schema «dmc-reloj-addendum-c1/1»): «fecha»,
  «commit_c1», «lista_cerrada» {alias: sha256} (alias AP/…, APH/… o LOCAL/…), «texto_v1_1» y «configuracion»
  ({ruta, sha256}, ambos dentro de la lista cerrada), «salida_bateria» ({alias: sha256}, dentro de la lista),
  «versiones_admitidas» (sha256 del Anexo C; contiene las seis de C0) y «lecturas» (lista). Opcional:
  «rutas_protocolo». ``cierre_descarga.json`` (schema «dmc-reloj-cierre-c2/1»): «fecha», «progreso_sha256»,
  «frase_autor» (texto no vacío) y «commit». Ambos deben estar en APH/auditoria/<AAAAMMDD>/reloj_dmc/ con
  esa fecha.
- VER-2. «Comprueba sus huellas contra el commit» (E1-6): el archivo pasado por argumento es idéntico, byte a
  byte, a su versión en el último commit de APH que lo tocó (``git log -n 1``, ``git show``), y ese commit es
  antecesor de origin/main de APH (subido al remoto privado, §10). El commit que cada archivo declara
  («commit_c1», «commit» del cierre) es antecesor o igual del commit que lo registra, porque un archivo no
  puede contener el hash del commit que lo guarda. Además, por el orden C1 → C3 → C2 de §10, el commit de C1
  es antecesor del commit que declara el cierre. Todo con la referencia local origin/main: sin red.
- VER-3. «Rutas del protocolo» de §10: RUTAS_PROTOCOLO (el paquete, el código fijado con huella en C0 y la
  carpeta de C0 y de las enmiendas), las de la lista cerrada que caen en AP o APH, las carpetas del
  addendum, del cierre, de la errata y del punto 12, y las «rutas_protocolo» del addendum si las trae.
- VER-4. Lista cerrada: además de comparar cada huella, se exige que cubra el código que corre (cada .py del
  paquete y de tests/, con la huella del archivo en ejecución), el texto v1.1, la configuración, las listas V
  y V2 y la salida de C1 en LOCAL/…/v1/c1/ (§10, C1: «de las pruebas, de bateria_v1.csv y de la salida de la
  batería»): pruebas_c1.txt, resumen_c1.json, los cinco archivos de la batería y el propio sha256.json, cada
  uno con la huella que le da ese sha256.json. El código fijado (adaptador, dmc_features, preflight_v3,
  _meteo_guard) debe tener las huellas de C0. Una lista que no cubre algo de eso cuenta como «una huella
  difiere».
- VER-5. Orden de los rechazos: primero lo que no toca la DMC (lista cerrada, git, cerrojo, entorno fijado y
  carpeta), y sólo si todo pasa se toma el candado y se mira C2. Un intento rechazado no abre nada bajo DMC
  salvo, en C2, el candado, progreso.json y los manifiestos (no artefactos).
- VER-6. Corrida confirmatoria: la que pasó los cuatro rechazos y A2. Se registra en el cerrojo antes de crear
  la carpeta y de leer ERA5-Land. Una corrida confirmatoria sin sellar (abortada o detenida por A1) se
  retoma con --reanudar, en la misma carpeta y con las mismas entradas (addendum, cierre, progreso.json,
  huella de los manifiestos, commit de C1 y errata), o se reemplaza con una errata (VER-7) cuando hace falta
  cambiar el código. Una sellada no se repite sin errata.
- VER-7. Errata confirmada y sellada (§10): ``--errata`` con APH/auditoria/<AAAAMMDD>/reloj_dmc/errata_<n>.json
  (schema «dmc-reloj-errata/1»: «n» ≥ 1, «fecha», «prueba» y «sello», cada uno {ruta, sha256} con el archivo
  presente y esa huella), registrado en git como en VER-2. Al verificarla se agrega al cerrojo; una errata
  no usada habilita UNA corrida nueva, con carpeta _ERRATA<n> y la política con errata_post_c4 = true. Si hay
  una corrida confirmatoria sin sellar, la corrida de la errata la reemplaza: su línea
  «corrida_confirmatoria» lleva «reemplaza» con la etiqueta de la pendiente, que ya no se puede reanudar; su
  carpeta no se toca (§10: «la nueva corrida usa _ERRATA<n>»). --errata y --reanudar no se combinan.
- VER-8. Punto 12 de la Enmienda 4 (§10, C4): ``--enmienda4 RUTA`` opcional. Queda «anclado» si el archivo
  pasa VER-2; sin el argumento, o si no pasa, queda «no anclado». Se registra en el cerrojo y en el informe
  (otras huellas), y no detiene nada: rige §7.5 (Enmienda 2).
- VER-9. Fin de la lectura de la DMC: después de la última lectura, que es la comprobación 7 de §7.3 (dentro de
  salidas.escribir_corrida, con orquestacion.verificador_7_3). Ahí se recalculan la sha256 de progreso.json y
  la huella agregada de los manifiestos, y se suelta el candado. Si cambiaron, la corrida aborta antes del
  sello. Con A5 alto (sin política ni §7.3) se hace antes de escribir. La huella de los manifiestos leídos
  por extraer_dmc debe ser además la de C2.
- VER-10. C2 exige también la copia de progreso.json en LOCAL/evidencia_vista/reloj_dmc/c2/ con la misma
  sha256 (§10, C2: «se copian … con su sha256, progreso.json y las bitácoras que lee G-dup»). G-dup lee todos
  los archivos regulares de esa carpeta.
- VER-11. Errores después de registrar la corrida confirmatoria: la consola y el cerrojo muestran sólo la fase
  y el tipo del error; el detalle (redactado, SAL-5) queda en error_retenido_<intento>.json dentro de la
  carpeta de la corrida (salidas.ErrorRetenido). Los mensajes de C2 y de las huellas finales no traen
  veredictos y se muestran. Si además falla el registro en el cerrojo, se avisa sólo su tipo y nada se
  relanza con el error original encadenado (una interrupción se relanza sin contexto).
- VER-12. Descargas activas (C3, §8.E): las que reconoce el guardián fijado de la descarga
  (``_meteo_guard.data_producers`` sobre ``ps -axo pid=,ppid=,pgid=,lstart=,command=``): todo
  descargar_*/download_* en Python, sus envoltorios de shell y los trabajadores huérfanos de multiprocessing,
  de cualquier fuente (también TROPOMI). Se mira antes y después de C3; durante C3, un registro de accesos
  bloquea todo open, stat o listado bajo DMC.
- VER-13. Umbrales de C3: C3 va después de C1 (§10: C0 → C1 → C3 → C2), así que --control-era5 exige
  --addendum y corre con los umbrales de la lista cerrada (texto v1.1 y configuración); la lista debe cubrir
  además el código que corre (VER-4). La lista se comprueba con las raíces de siempre: --salida sólo cambia
  dónde se escribe. LOCAL/…/v1/c3_registro.json guarda la fuente de los umbrales, el addendum (alias, sha256 y
  commit_c1) y la huella de cada .py del paquete, para atar C3 a lo que corre en C4.
- VER-14. Ceguera (§8, prueba 27): ``RegistroAccesos`` registra «open» y los listados por el gancho de
  auditoría, y os.stat y os.lstat con envoltorios (esas dos no emiten eventos de auditoría). No ve lo que
  abren bibliotecas en C (pyarrow, netCDF4) ni lo que hacen los subprocesos. Los registros anidados se miran
  del más interior al más exterior: el primero que bloquea niega el acceso antes de que ocurra, y los que
  están afuera lo anotan aparte («negados_dentro»), no como acceso. --sintetico corre con un registro en
  bloqueo sobre /Volumes (falla cerrado: nada llega a /Volumes) y C1 no aprueba si anota algún acceso que no
  negó antes un registro de las propias pruebas; --control-era5 lo usa en modo bloqueo sobre DMC. Corrido
  como script, el ejecutable delega en ``reloj_dmc.verificar_reloj_dmc``: así hay un solo ejemplar del módulo
  y el registro de --sintetico es el mismo que el de las pruebas que importan el paquete.
- VER-15. Salida de --sintetico (R-32): LOCAL/…/v1/c1/ (o --salida): pruebas_c1.txt (salida de unittest,
  redactada), resumen_c1.json, y con --bateria las salidas de bateria (``bateria.escribir_salidas``:
  bateria_v1.csv, resultados_bateria.parquet, criterios_bateria.json y tiempo_bateria.json con
  ``bateria.tiempo_bateria``; registro_8F.jsonl lo reescribe ``bateria.ajustar_umbrales`` después de cada
  iteración); el ejecutable sólo escribe sha256.json al final, con la huella de cada uno. La primera corrida
  de la batería mide el tiempo y es la primera iteración de §8.F; si pasa de 48 h se regenera la tabla con 5
  réplicas en D2 y D3 antes de iterar, y tiempo_bateria.json guarda esa primera medición. C1 se da por
  aprobado («exito») sólo si: corre con el intérprete fijado (sus versiones van al resumen), con todas las
  pruebas de tests/ (patrón completo), sin fallas, errores, omitidas, fallas esperadas ni éxitos inesperados
  (§10, C1: «se aprueban las pruebas de §8, grupos A a D»; una prueba omitida no se da por aprobada), con la
  batería corrida y aprobada, y sin accesos bajo /Volumes. Si no, resumen_c1.json lista los motivos y la
  salida del proceso no es 0.
- VER-16. Concurrencia del cerrojo: cada registro relee intentos_aplicar.jsonl bajo su flock, verifica toda la
  cadena, exige que lo ya leído siga igual al principio (sólo se admiten líneas agregadas por otros) y
  encadena la línea nueva sobre el final real; el número de intento se asigna ahí. Además, --aplicar retiene
  durante toda la corrida un candado propio, LOCAL/…/v1/.aplicar.lock (flock exclusivo sin bloqueo), porque
  el de la DMC se suelta en §7.3, antes del sello: otro --aplicar que llega mientras tanto queda registrado
  («intento» y «rechazo») y no corre. La línea «intento» lleva las sha256 de los archivos pasados por
  argumento (addendum, cierre, errata y punto 12), ninguno de la DMC (§7.1: «con … sus huellas»).
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse  # noqa: E402
import errno  # noqa: E402
import fcntl  # noqa: E402
import hashlib  # noqa: E402
import importlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import platform  # noqa: E402
import re  # noqa: E402
import stat  # noqa: E402
import subprocess  # noqa: E402
import traceback  # noqa: E402
import unittest  # noqa: E402
from dataclasses import dataclass, field, replace  # noqa: E402
from datetime import date, datetime, timezone  # noqa: E402
from pathlib import Path, PurePosixPath  # noqa: E402
from types import ModuleType  # noqa: E402
from typing import Any, Callable, Iterable, Mapping, Sequence  # noqa: E402

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # scripts_modelo_1km, para «import reloj_dmc»

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from reloj_dmc import (constantes, controles_era5, entorno, extraccion, fijados, orquestacion,  # noqa: E402
                       red, salidas)
from reloj_dmc import politica as mod_politica  # noqa: E402
from reloj_dmc import tablas as mod_tablas  # noqa: E402
from reloj_dmc import umbrales as mod_umbrales  # noqa: E402

ETIQUETA_CORRIDA = "HUMAN{fecha}_RELOJ_DMC_1"
SUFIJO_ERRATA = "_ERRATA{n}"
CERROJO = "intentos_aplicar.jsonl"
AVANCE = "avance.jsonl"
CANDADO_DMC = ".meteo_download.lock"
CANDADO_APLICAR = ".aplicar.lock"          # en LOCAL/…/v1/, propio de --aplicar (VER-16)
PROGRESO_DMC = "progreso.json"
FASES_5_2 = ("C2_y_huellas", "ERA5-Land", "extraccion_DMC", "estados_de_lineas", "A3_A5_calibracion",
             "pasos_1_a_6", "A4", "pasos_7_a_9", "rachas_y_meses", "politica_y_comprobaciones", "sello")
(FASE_C2, FASE_ERA5, FASE_DMC, FASE_ESTADOS, _FASE_A3_A5, _FASE_PASOS_1_6, _FASE_A4, _FASE_PASOS_7_9, _FASE_RACHAS,
 FASE_POLITICA, FASE_SELLO) = FASES_5_2

# Códigos de salida del proceso.
SALIDA_OK = 0
SALIDA_FALLA = 1          # corrió y algo no pasó (pruebas, C3, A1/A2, corrida abortada)
SALIDA_RECHAZO = 2        # no corrió: rechazos de C4, descargas activas, entorno

# Estados del candado (§3.1).
TOMADO = "tomado"
RETENIDO = "held"
AUSENTE = "absent"
INSEGURO = "inseguro"            # enlace simbólico, no regular u otro volumen
NO_VERIFICABLE = "no_verificable"

# Formatos (VER-1, VER-7).
ESQUEMA_ADDENDUM = "dmc-reloj-addendum-c1/1"
ESQUEMA_CIERRE = "dmc-reloj-cierre-c2/1"
ESQUEMA_ERRATA = "dmc-reloj-errata/1"
ESQUEMA_CERROJO = "dmc-reloj-intentos/1"
ESQUEMA_RESUMEN_C1 = "dmc-reloj-c1/1"
ESQUEMA_REGISTRO_C3 = "dmc-reloj-c3-registro/1"
ARCHIVO_ADDENDUM = "addendum_c1.json"
ARCHIVO_CIERRE = "cierre_descarga.json"
PATRON_ERRATA = re.compile(r"errata_([1-9]\d*)\.json")
CARPETA_AUDITORIA = "auditoria"
CARPETA_RELOJ = "reloj_dmc"
CLAVES_ADDENDUM = ("schema", "fecha", "commit_c1", "lista_cerrada", "texto_v1_1", "configuracion",
                   "salida_bateria", "versiones_admitidas", "lecturas")
CLAVES_CIERRE = ("schema", "fecha", "progreso_sha256", "frase_autor", "commit")
CLAVES_ERRATA = ("schema", "n", "fecha", "prueba", "sello")
RAICES_LISTA = ("AP", "APH", "LOCAL")

# C2 (§3.1).
PHASE_TERMINADA = "finished"
STATUS_ADMITIDOS = ("finished", "finished_with_pending")
CLAVE_VERIFICACION_FINAL = "final_verification"
SUBRUTA_COPIAS_C2 = "evidencia_vista/reloj_dmc/c2"

# Rutas fijas (alias). VER-3.
RUTA_C0_APH = "auditoria/20261023/reloj_dmc"
RUTA_LISTA_V = f"{RUTA_C0_APH}/inventario_c0/lista_V.csv"
RUTA_LISTA_V2 = f"{RUTA_C0_APH}/inventario_c0/lista_V2.csv"
RUTA_METEO_GUARD = "scripts_pipeline/_meteo_guard.py"
MODULO_METEO_GUARD = "_reloj_dmc_meteo_guard"
NOMBRE_CATALOGO_PIXELES = "catalogo_pixeles.parquet"
RUTA_PAQUETE_AP = "scripts_modelo_1km/reloj_dmc"
RUTAS_PROTOCOLO = (
    f"AP/{RUTA_PAQUETE_AP}",
    f"AP/{fijados.RUTA_ADAPTADOR}", f"AP/{fijados.RUTA_DMC_FEATURES}", f"AP/{fijados.RUTA_PREFLIGHT_V3}",
    f"AP/{fijados.RUTA_COMUN_MODELO}", f"AP/{fijados.RUTA_RELOJ_SINCA}", f"AP/{RUTA_METEO_GUARD}",
    f"AP/{fijados.RUTA_DESCARGADOR}",
    f"APH/{RUTA_C0_APH}",
)
# Código fijado con huella de C0 que la corrida usa (VER-4).
CODIGO_FIJADO = ((fijados.RUTA_ADAPTADOR, fijados.SHA_ADAPTADOR), (fijados.RUTA_DMC_FEATURES, fijados.SHA_DMC_FEATURES),
                 (fijados.RUTA_PREFLIGHT_V3, fijados.SHA_PREFLIGHT_V3), (RUTA_METEO_GUARD, fijados.SHA_METEO_GUARD))

# --sintetico (VER-15).
CARPETA_C1 = "c1"
PATRON_PRUEBAS = "test*.py"
ARCHIVO_PRUEBAS = "pruebas_c1.txt"
ARCHIVO_RESUMEN_C1 = "resumen_c1.json"
ARCHIVO_HUELLAS = "sha256.json"
ARCHIVOS_BATERIA = ("bateria_v1.csv", "resultados_bateria.parquet", "criterios_bateria.json", "tiempo_bateria.json",
                    "registro_8F.jsonl")
ARCHIVOS_C1 = (ARCHIVO_PRUEBAS, ARCHIVO_RESUMEN_C1, *ARCHIVOS_BATERIA)
ARCHIVO_REGISTRO_C3 = "c3_registro.json"
VOLUMES = Path("/Volumes")

_SHA = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_FECHA = re.compile(r"(\d{4})-?(\d{2})-?(\d{2})")
_FASE_CONSOLA = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,47}")
_UNIDAD_AVANCE = re.compile(r"[a-z0-9]+/[A-Za-z0-9_-]+")
ABREVIATURA = 8           # no-umbral: caracteres de una huella abreviada en un mensaje
PASOS_CONSOLA = 20        # no-umbral: cuántas líneas de avance, a lo más, por fase en la consola
MAX_EJEMPLOS = 5          # no-umbral: ejemplos que lleva un mensaje de rechazo
TIEMPO_GIT_S = 900        # no-umbral: tope de espera (s) de un comando git de sólo lectura
TIEMPO_PS_S = 60          # tope de espera (s) de ps
ANCHO_ESTADO_GIT = 3      # no-umbral: «XY » antes de la ruta en git status --porcelain
NICE_CORRIDA = 10         # no-umbral: prioridad baja del proceso (§9: «con nice»)
SHA_VACIO = hashlib.sha256(b"").hexdigest()


# El cuarto caso de §10 (C4). La palabra «confirmada» del texto («errata confirmada y sellada») no se escribe en
# la consola, para que ningún aviso se lea como un veredicto (§5.2).
MOTIVO_CERROJO = ("intentos_aplicar.jsonl ya registra una corrida confirmatoria y no hay una errata sellada con "
                  "testigo externo (§10)")


class ErrorC2(RuntimeError):
    """C2 dejó de cumplirse durante la corrida (huellas cambiadas): la corrida aborta sin sellar. El mensaje no
    trae veredictos."""


class ErrorCerrojo(RuntimeError):
    """intentos_aplicar.jsonl ilegible, reescrito o modificado por otro proceso: nada corre."""


# =========================================================================================================
# Configuración
# =========================================================================================================
def _reloj_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ps() -> str:
    r = subprocess.run(["ps", "-axo", "pid=,ppid=,pgid=,lstart=,command="], capture_output=True, check=False,
                       timeout=TIEMPO_PS_S)
    if r.returncode != 0:
        raise RuntimeError("no se pudo listar los procesos (ps)")
    return r.stdout.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class Configuracion:
    """Todo lo que la corrida toma del mundo. ``configuracion_real()`` la arma para AP, APH, LOCAL, DMC y ERA5L;
    las pruebas la arman con raíces falsas (``entorno.rutas_sinteticas``)."""
    rutas: entorno.Rutas
    ap_codigo: Path                       # de dónde se carga el código fijado (adaptador, preflight, guardián)
    paquete: Path                         # el código que corre (VER-4)
    catalogo_pixeles: Path
    sha_catalogo_pixeles: str
    lista_v: Path
    lista_v2: Path
    copias_c2: Path
    rutas_protocolo: tuple[str, ...] = RUTAS_PROTOCOLO
    reloj: Callable[[], datetime] = _reloj_utc     # R-31: inyectable
    procesos: Callable[[], str] = _ps
    nice: int = NICE_CORRIDA
    lineas_activas: frozenset = orquestacion.LINEAS_ACTIVAS_C0
    vigiladas_c1: tuple = (VOLUMES,)              # registro en bloqueo de --sintetico (VER-14); las pruebas suman otras


def configuracion_real(rutas: entorno.Rutas | None = None) -> Configuracion:
    rutas = rutas or entorno.rutas_reales()
    return Configuracion(
        rutas=rutas, ap_codigo=rutas.ap, paquete=Path(__file__).resolve().parent,
        catalogo_pixeles=rutas.era5l / NOMBRE_CATALOGO_PIXELES, sha_catalogo_pixeles=fijados.SHA_CATALOGO_PIXELES,
        lista_v=rutas.aph / RUTA_LISTA_V, lista_v2=rutas.aph / RUTA_LISTA_V2,
        copias_c2=rutas.local / SUBRUTA_COPIAS_C2)


def _configuracion(args: argparse.Namespace) -> Configuracion:
    cfg = getattr(args, "configuracion", None)
    return cfg if cfg is not None else configuracion_real()


# =========================================================================================================
# Utilidades
# =========================================================================================================
def _corto(sha: str | None) -> str:
    return (sha or "")[:ABREVIATURA]


def _aviso(texto: str) -> None:
    """Avisos fijos del ejecutable (rechazos, fin); nunca veredictos. A stderr, con la privacidad de §7.4."""
    print(f"[reloj_dmc] {salidas.redactar(texto)}", file=sys.stderr, flush=True)


def _leer_json_estricto(ruta: Path) -> Any:
    def sin_duplicados(pares):
        claves = [k for k, _ in pares]
        if len(set(claves)) != len(claves):
            raise ValueError("clave repetida")
        return dict(pares)

    def sin_no_finitos(token):
        raise ValueError(f"valor no finito {token}")

    return json.loads(Path(ruta).read_bytes().decode("utf-8"), object_pairs_hook=sin_duplicados,
                      parse_constant=sin_no_finitos)


def _a_json(x: Any) -> Any:
    """Estructura JSON sin NaN (NaN e infinito → None; numpy y pandas → tipos de Python)."""
    if isinstance(x, Mapping):
        return {str(k): _a_json(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set, frozenset)):
        valores = sorted(x, key=str) if isinstance(x, (set, frozenset)) else x
        return [_a_json(v) for v in valores]
    if isinstance(x, pd.DataFrame):
        return {"columnas": [str(c) for c in x.columns], "filas": _a_json(x.astype(object).to_dict("records"))}
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return None if not math.isfinite(float(x)) else float(x)
    if x is None or isinstance(x, (str, int)):
        return x
    if x is pd.NA or x is pd.NaT:
        return None
    if hasattr(x, "__dataclass_fields__"):
        return _a_json({k: getattr(x, k) for k in x.__dataclass_fields__})
    return str(x)


def _fecha_ocho(texto: Any) -> str | None:
    """«AAAA-MM-DD» o «AAAAMMDD» → «AAAAMMDD» (fecha válida) o None."""
    m = _FECHA.fullmatch(str(texto)) if isinstance(texto, str) else None
    if m is None:
        return None
    anio, mes, dia = (int(g) for g in m.groups())
    try:
        date(anio, mes, dia)
    except ValueError:
        return None
    return "".join(m.groups())


def _lexica(ruta: Path | str) -> Path:
    return Path(os.path.normpath(os.path.abspath(os.fspath(ruta))))


def resolver_alias(alias: str, rutas: entorno.Rutas, raices: Sequence[str] = RAICES_LISTA) -> Path:
    """«AP/…», «APH/…» o «LOCAL/…» → ruta bajo esa raíz (sin «..» ni rutas absolutas)."""
    if not isinstance(alias, str):
        raise ValueError("alias que no es texto")
    raiz, _, resto = alias.partition("/")
    base = {"AP": rutas.ap, "APH": rutas.aph, "LOCAL": rutas.local, "DMC": rutas.dmc, "ERA5L": rutas.era5l}.get(raiz)
    partes = PurePosixPath(resto).parts
    if raiz not in raices or base is None or not resto or PurePosixPath(resto).is_absolute() or ".." in partes:
        raise ValueError(f"alias fuera de {', '.join(raices)}: {alias}")
    return Path(base).joinpath(*partes)


def _alias(ruta: Path, rutas: entorno.Rutas) -> str:
    try:
        return entorno.alias(_lexica(ruta), rutas)
    except ValueError:
        return "<fuera de los alias>"


def _sha_o_none(ruta: Path) -> str | None:
    try:
        if ruta.is_symlink() or not ruta.is_file():
            return None
        return entorno.sha256_archivo(ruta)
    except OSError:
        return None


def _archivos_regulares(carpeta: Path) -> list[Path]:
    if not carpeta.is_dir():
        return []
    salida = []
    for raiz, dirs, archivos in os.walk(carpeta):
        dirs.sort()
        for nombre in sorted(archivos):
            ruta = Path(raiz) / nombre
            if not nombre.startswith(".") and ruta.is_file() and not ruta.is_symlink():
                salida.append(ruta)
    return sorted(salida, key=lambda p: p.as_posix())


def _codigo_del_paquete(paquete: Path) -> dict[str, Path]:
    """Nombre relativo al paquete («x.py», «tests/test_x.py») → ruta, de cada .py del código que corre."""
    paquete = Path(paquete)
    salida = {p.name: p for p in sorted(paquete.glob("*.py"))}
    salida.update({f"tests/{p.name}": p for p in sorted((paquete / "tests").glob("*.py"))})
    return salida


# =========================================================================================================
# Git (sólo lectura, sin red)
# =========================================================================================================
def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """git de sólo lectura: sin candados opcionales, sin fsmonitor, sin preguntas y con rutas literales."""
    entorno_git = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
    orden = ["git", "--no-optional-locks", "--literal-pathspecs", "-c", "core.fsmonitor=false", "-C", str(repo), *args]
    try:
        return subprocess.run(orden, capture_output=True, env=entorno_git, timeout=TIEMPO_GIT_S, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(orden, -1, b"", type(e).__name__.encode("ascii"))


def _es_antecesor(repo: Path, antecesor: str, descendiente: str) -> bool | None:
    """True / False; None si git no lo puede decidir (commit o referencia inexistente)."""
    r = _git(repo, "merge-base", "--is-ancestor", antecesor, descendiente)
    return True if r.returncode == 0 else False if r.returncode == 1 else None


@dataclass(frozen=True)
class RegistroGit:
    """Resultado de VER-2 para un archivo de APH."""
    commit: str | None
    motivos: tuple[str, ...]
    ruta_relativa: str | None = None


def registro_en_git(archivo: Path, repo: Path, nombre: str) -> RegistroGit:
    """VER-2: el archivo es su versión del último commit que lo tocó, y ese commit está en origin/main."""
    try:
        rel = Path(archivo).resolve().relative_to(Path(repo).resolve())
    except (ValueError, OSError):
        return RegistroGit(None, (f"{nombre} no está dentro del repositorio APH",))
    rel_txt = PurePosixPath(*rel.parts).as_posix()
    try:
        datos = Path(archivo).read_bytes()
    except OSError:
        return RegistroGit(None, (f"{nombre} no se puede leer",), rel_txt)
    r = _git(repo, "log", "-n", "1", "--format=%H", "--", rel_txt)
    commit = r.stdout.decode("ascii", errors="replace").strip()
    if r.returncode != 0 or not _COMMIT.fullmatch(commit):
        return RegistroGit(None, (f"{nombre} no está registrado en git",), rel_txt)
    motivos = []
    r = _git(repo, "show", f"{commit}:{rel_txt}")
    if r.returncode != 0 or r.stdout != datos:
        motivos.append(f"{nombre} difiere de su versión en git ({_corto(commit)})")
    if _es_antecesor(repo, commit, "origin/main") is not True:
        motivos.append(f"{nombre}: su commit ({_corto(commit)}) no está en origin/main de APH")
    return RegistroGit(commit, tuple(motivos), rel_txt)


def _exigir_ubicacion(rel: str | None, fecha: str | None, nombre_archivo: str | re.Pattern, nombre: str) -> list[str]:
    """E1-6: APH/auditoria/<fecha>/reloj_dmc/<archivo>, con la fecha del propio archivo."""
    partes = PurePosixPath(rel).parts if rel else ()
    nombre_ok = bool(partes) and (partes[-1] == nombre_archivo if isinstance(nombre_archivo, str)
                                  else nombre_archivo.fullmatch(partes[-1]) is not None)
    if not (nombre_ok and tuple(partes[:-1]) == (CARPETA_AUDITORIA, fecha, CARPETA_RELOJ)):
        return [f"{nombre} no está en APH/{CARPETA_AUDITORIA}/<fecha>/{CARPETA_RELOJ}/ con su fecha (E1-6)"]
    return []


def comprobar_git(ap: Path, aph: Path, rutas_protocolo: Sequence[str], commit_c1: str) -> list[str]:
    """Sólo lectura (``git --no-optional-locks``); lista de motivos de rechazo (§10, C4, segundo caso)."""
    motivos: list[str] = []
    por_repo: dict[str, set[str]] = {"AP": set(), "APH": set()}
    for alias in rutas_protocolo:
        raiz, _, resto = str(alias).partition("/")
        if raiz not in por_repo or not resto or ".." in PurePosixPath(resto).parts:
            motivos.append(f"ruta del protocolo fuera de AP o APH: {alias}")
            continue
        por_repo[raiz].add(resto)
    for nombre, repo in (("AP", ap), ("APH", aph)):
        rutas = sorted(por_repo[nombre])
        if not rutas:
            continue
        r = _git(repo, "status", "--porcelain", "--untracked-files=all", "--", *rutas)
        if r.returncode != 0:
            motivos.append(f"git status no se pudo correr en {nombre}")
            continue
        lineas = [ln[ANCHO_ESTADO_GIT:] for ln in r.stdout.decode("utf-8", errors="replace").splitlines()
                  if ln.strip()]
        if lineas:
            motivos.append(f"{nombre}: el árbol no está limpio en las rutas del protocolo ({len(lineas)}): "
                           + ", ".join(lineas[:MAX_EJEMPLOS]))
    if not isinstance(commit_c1, str) or not _COMMIT.fullmatch(commit_c1):
        motivos.append("el commit de C1 no es un commit de 40 hexadecimales")
    else:
        antecesor = _es_antecesor(aph, commit_c1, "origin/main")
        if antecesor is False:
            motivos.append(f"el commit de C1 ({_corto(commit_c1)}) no es antecesor de origin/main de APH")
        elif antecesor is None:
            motivos.append(f"no se pudo comprobar el commit de C1 ({_corto(commit_c1)}) contra origin/main de APH")
    return motivos


# =========================================================================================================
# Addendum de C1, línea de cierre de C2, errata y punto 12 (VER-1, VER-7, VER-8)
# =========================================================================================================
def _exigir_entrada(x: Any, donde: str) -> dict:
    if not isinstance(x, Mapping) or set(x) != {"ruta", "sha256"} or not isinstance(x["ruta"], str) \
            or not isinstance(x["sha256"], str) or not _SHA.fullmatch(x["sha256"]):
        raise ValueError(f"«{donde}» debe ser {{ruta, sha256}} con un sha256 de 64 hexadecimales")
    return dict(x)


def leer_addendum(ruta: Path) -> dict:
    """addendum_c1.json con el formato de VER-1; ValueError si no lo cumple."""
    datos = _leer_json_estricto(ruta)
    if not isinstance(datos, dict):
        raise ValueError("el addendum no es un objeto JSON")
    faltan = [k for k in CLAVES_ADDENDUM if k not in datos]
    if faltan:
        raise ValueError(f"faltan las claves {faltan}")
    if datos["schema"] != ESQUEMA_ADDENDUM:
        raise ValueError(f"schema {datos['schema']!r}; se espera {ESQUEMA_ADDENDUM!r}")
    if _fecha_ocho(datos["fecha"]) is None:
        raise ValueError("fecha inválida")
    if not isinstance(datos["commit_c1"], str) or not _COMMIT.fullmatch(datos["commit_c1"]):
        raise ValueError("commit_c1 no es un commit de 40 hexadecimales")
    for clave in ("lista_cerrada", "salida_bateria"):
        lista = datos[clave]
        if not isinstance(lista, Mapping) or not all(isinstance(k, str) and isinstance(v, str) and _SHA.fullmatch(v)
                                                      for k, v in lista.items()):
            raise ValueError(f"«{clave}» debe ser {{alias: sha256}}")
    if not datos["lista_cerrada"]:
        raise ValueError("la lista cerrada está vacía")
    for clave in ("texto_v1_1", "configuracion"):
        datos[clave] = _exigir_entrada(datos[clave], clave)
    versiones = datos["versiones_admitidas"]
    if not isinstance(versiones, list) or not all(isinstance(v, str) and _SHA.fullmatch(v) for v in versiones) \
            or len(set(versiones)) != len(versiones):
        raise ValueError("«versiones_admitidas» debe ser una lista de sha256 distintos")
    if not set(fijados.VERSIONES_ADMITIDAS_C0) <= set(versiones):
        raise ValueError("«versiones_admitidas» no contiene las seis versiones admitidas en C0")
    fuera = set(versiones) - set(fijados.VERSIONES_ADMITIDAS_C0) - set(fijados.VERSIONES_SIN_CODIGO_C0)
    if fuera:
        raise ValueError("«versiones_admitidas» trae versiones que no son del Anexo C")
    if not isinstance(datos["lecturas"], list):
        raise ValueError("«lecturas» debe ser una lista")
    extra = datos.get("rutas_protocolo", [])
    if not isinstance(extra, list) or not all(isinstance(r, str) for r in extra):
        raise ValueError("«rutas_protocolo» debe ser una lista de alias")
    return datos


def leer_cierre(ruta: Path) -> dict:
    """cierre_descarga.json con el formato de VER-1; ValueError si no lo cumple."""
    datos = _leer_json_estricto(ruta)
    if not isinstance(datos, dict):
        raise ValueError("la línea de cierre no es un objeto JSON")
    faltan = [k for k in CLAVES_CIERRE if k not in datos]
    if faltan:
        raise ValueError(f"faltan las claves {faltan}")
    if datos["schema"] != ESQUEMA_CIERRE:
        raise ValueError(f"schema {datos['schema']!r}; se espera {ESQUEMA_CIERRE!r}")
    if _fecha_ocho(datos["fecha"]) is None:
        raise ValueError("fecha inválida")
    if not isinstance(datos["progreso_sha256"], str) or not _SHA.fullmatch(datos["progreso_sha256"]):
        raise ValueError("progreso_sha256 no es un sha256")
    if not isinstance(datos["frase_autor"], str) or not datos["frase_autor"].strip():
        raise ValueError("falta la frase textual del autor que cierra la descarga")
    if not isinstance(datos["commit"], str) or not _COMMIT.fullmatch(datos["commit"]):
        raise ValueError("commit no es un commit de 40 hexadecimales")
    return datos


def leer_errata(ruta: Path) -> dict:
    datos = _leer_json_estricto(ruta)
    if not isinstance(datos, dict):
        raise ValueError("la errata no es un objeto JSON")
    faltan = [k for k in CLAVES_ERRATA if k not in datos]
    if faltan:
        raise ValueError(f"faltan las claves {faltan}")
    if datos["schema"] != ESQUEMA_ERRATA:
        raise ValueError(f"schema {datos['schema']!r}; se espera {ESQUEMA_ERRATA!r}")
    n = datos["n"]
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError("«n» debe ser un entero ≥ 1")
    if _fecha_ocho(datos["fecha"]) is None:
        raise ValueError("fecha inválida")
    for clave in ("prueba", "sello"):
        datos[clave] = _exigir_entrada(datos[clave], clave)
    return datos


def comprobar_lista_cerrada(addendum: Path, *, rutas: entorno.Rutas | None = None,
                            exigidos: Mapping[str, str | None] | None = None) -> list[str]:
    """Huellas del addendum de C1 que difieren (texto v1.1, JSON, código, pruebas, bateria_v1.csv, salida).

    ``exigidos``: alias que la lista debe traer (VER-4), con la huella que deben tener (None: cualquiera).
    Devuelve los motivos de rechazo; [] si todo coincide."""
    rutas = rutas or entorno.rutas_reales()
    try:
        datos = leer_addendum(addendum)
    except (OSError, ValueError, UnicodeDecodeError) as e:
        return [f"el addendum de C1 no se puede usar: {e}"]
    lista = dict(datos["lista_cerrada"])
    motivos = []
    for alias, sha in sorted(lista.items()):
        try:
            ruta = resolver_alias(alias, rutas)
        except ValueError:
            motivos.append(f"lista cerrada: alias fuera de AP, APH o LOCAL: {alias}")
            continue
        actual = _sha_o_none(ruta)
        if actual is None:
            motivos.append(f"lista cerrada: falta {alias}")
        elif actual != sha:
            motivos.append(f"lista cerrada: la huella de {alias} difiere ({_corto(actual)} ≠ {_corto(sha)})")
    for clave in ("texto_v1_1", "configuracion"):
        entrada = datos[clave]
        if lista.get(entrada["ruta"]) != entrada["sha256"]:
            motivos.append(f"«{clave}» no está en la lista cerrada con la misma huella")
    for alias, sha in sorted(datos["salida_bateria"].items()):
        if lista.get(alias) != sha:
            motivos.append(f"la salida de la batería {alias} no está en la lista cerrada con la misma huella")
    for alias, sha in sorted((exigidos or {}).items()):
        if alias not in lista:
            motivos.append(f"la lista cerrada no incluye {alias}")
        elif sha is not None and lista[alias] != sha:
            motivos.append(f"{alias}: el archivo en uso difiere de la lista cerrada")
    return motivos


def _huellas_salida_c1(carpeta: Path) -> dict[str, str]:
    """{archivo: sha256} de LOCAL/…/v1/c1/sha256.json ({} si falta o no se puede leer)."""
    try:
        datos = _leer_json_estricto(Path(carpeta) / ARCHIVO_HUELLAS)
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    if not isinstance(datos, dict):
        return {}
    return {k: v for k, v in datos.items() if isinstance(k, str) and isinstance(v, str) and _SHA.fullmatch(v)}


def _exigidos(cfg: Configuracion) -> dict[str, str | None]:
    """VER-4: el código que corre (con su huella), las listas V y V2 y la salida de C1 (pruebas y batería, con
    las huellas de su sha256.json; sin ese archivo, cualquier huella, y la lista debe traerlo igual)."""
    salida: dict[str, str | None] = {f"AP/{RUTA_PAQUETE_AP}/{nombre}": entorno.sha256_archivo(ruta)
                                     for nombre, ruta in _codigo_del_paquete(cfg.paquete).items()}
    for ruta in (cfg.lista_v, cfg.lista_v2):
        salida[entorno.alias(_lexica(ruta), cfg.rutas)] = None
    carpeta_c1 = cfg.rutas.corridas / CARPETA_C1
    huellas_c1 = _huellas_salida_c1(carpeta_c1)
    for nombre in (*ARCHIVOS_C1, ARCHIVO_HUELLAS):
        salida[entorno.alias(_lexica(carpeta_c1 / nombre), cfg.rutas)] = huellas_c1.get(nombre)
    return salida


def _comprobar_codigo_fijado(ap_codigo: Path) -> list[str]:
    motivos = []
    for rel, sha in CODIGO_FIJADO:
        actual = _sha_o_none(Path(ap_codigo) / rel)
        if actual != sha:
            motivos.append(f"código fijado AP/{rel}: huella {_corto(actual) or 'ausente'} ≠ {_corto(sha)} (C0)")
    return motivos


def _registro_archivo(ruta: Path | None, aph: Path, nombre: str, *, fecha: str | None, archivo: str | re.Pattern,
                      declarado: str | None = None) -> tuple[RegistroGit | None, list[str]]:
    """VER-2 completo para el addendum, el cierre o la errata."""
    if ruta is None:
        return None, []
    reg = registro_en_git(Path(ruta), aph, nombre)
    motivos = list(reg.motivos)
    motivos += _exigir_ubicacion(reg.ruta_relativa, fecha, archivo, nombre)
    if reg.commit and declarado and _es_antecesor(aph, declarado, reg.commit) is not True:
        motivos.append(f"{nombre}: el commit que declara ({_corto(declarado)}) no es antecesor del que lo registra")
    return reg, motivos


# =========================================================================================================
# C2 y candado (§3.1)
# =========================================================================================================
@dataclass(frozen=True)
class EstadoC2:
    cumple: bool
    motivos: tuple[str, ...]
    progreso_sha256: str | None
    huella_manifiestos: str | None
    n_manifiestos: int | None = None
    cierre: Mapping | None = None


class CandadoDMC:
    """Context manager: abre el candado existente en sólo lectura y retiene ``flock(LOCK_EX | LOCK_NB)``
    hasta salir (o hasta ``liberar``). No crea ni escribe nada. Estado: «tomado», «held» o «absent» (los dos
    últimos fallan C2), o «inseguro»/«no_verificable» (también fallan)."""

    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        self.estado: str | None = None
        self._fd: int | None = None

    def __enter__(self) -> "CandadoDMC":
        try:
            fd = os.open(self.ruta, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            self.estado = AUSENTE
            return self
        except OSError as e:
            self.estado = INSEGURO if e.errno == errno.ELOOP else NO_VERIFICABLE
            return self
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_dev != os.stat(self.ruta.parent).st_dev:
                self.estado = INSEGURO
                os.close(fd)
                return self
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            self.estado = RETENIDO if e.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK) else NO_VERIFICABLE
            os.close(fd)
            return self
        self._fd = fd
        self.estado = TOMADO
        return self

    @property
    def retenido(self) -> bool:
        return self._fd is not None

    def liberar(self) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd = None

    def __exit__(self, *exc) -> None:
        self.liberar()


def huella_de_manifiestos(raiz_dmc: Path) -> tuple[str, int]:
    """(huella agregada de §7.4, número de manifiestos), con el alias «DMC/…» de extraccion."""
    lista = extraccion.listar_manifiestos(raiz_dmc)
    return (extraccion.huella_agregada_manifiestos(lista, lambda p: extraccion.alias_dmc(p, raiz_dmc)), len(lista))


def comprobar_c2(raiz_dmc: Path, linea_cierre: Path, *, aph: Path | None = None, commit_c1: str | None = None,
                 copias_c2: Path | None = None) -> EstadoC2:
    """Línea de cierre firmada y en git (E1-6, VER-1 y VER-2), progreso.json con phase «finished», status ∈
    {finished, finished_with_pending}, final_verification presente y la misma sha256, la copia de C2
    (VER-10) y la huella agregada de los manifiestos (para compararla al terminar de leer).

    Con ``aph`` se hace VER-2 (sin él, sólo las comprobaciones de contenido)."""
    motivos: list[str] = []
    raiz_dmc = Path(raiz_dmc)
    cierre = None
    try:
        cierre = leer_cierre(linea_cierre)
    except (OSError, ValueError, UnicodeDecodeError) as e:
        motivos.append(f"la línea de cierre de C2 no se puede usar: {e}")
    if cierre is not None and aph is not None:
        reg, extra = _registro_archivo(linea_cierre, aph, "la línea de cierre de C2", fecha=_fecha_ocho(cierre["fecha"]),
                                       archivo=ARCHIVO_CIERRE, declarado=cierre["commit"])
        motivos += extra
        if commit_c1 and _es_antecesor(aph, commit_c1, cierre["commit"]) is not True:
            motivos.append("el commit de C1 no es antecesor del commit de la línea de cierre (orden C1 → C3 → C2)")
    sha = None
    try:
        datos = (raiz_dmc / PROGRESO_DMC).read_bytes()
        sha = entorno.sha256_bytes(datos)
        progreso = json.loads(datos)
    except FileNotFoundError:
        motivos.append("falta DMC/progreso.json")
        progreso = None
    except (OSError, ValueError, UnicodeDecodeError):
        motivos.append("DMC/progreso.json no se puede leer como JSON")
        progreso = None
    if progreso is not None:
        if not isinstance(progreso, dict):
            motivos.append("DMC/progreso.json no es un objeto JSON")
        else:
            if progreso.get("phase") != PHASE_TERMINADA:
                motivos.append(f"progreso.json: phase = {progreso.get('phase')!r}, no «{PHASE_TERMINADA}»")
            if progreso.get("status") not in STATUS_ADMITIDOS:
                motivos.append(f"progreso.json: status = {progreso.get('status')!r}, no {' ni '.join(STATUS_ADMITIDOS)}")
            if progreso.get(CLAVE_VERIFICACION_FINAL) is None:
                motivos.append(f"progreso.json: falta {CLAVE_VERIFICACION_FINAL}")
    if cierre is not None and sha is not None and sha != cierre["progreso_sha256"]:
        motivos.append(f"la sha256 de progreso.json ({_corto(sha)}) no es la de la línea de cierre "
                       f"({_corto(cierre['progreso_sha256'])})")
    if copias_c2 is not None and sha is not None and _sha_o_none(Path(copias_c2) / PROGRESO_DMC) != sha:
        motivos.append("la copia de progreso.json de C2 (LOCAL/evidencia_vista/reloj_dmc/c2/) falta o difiere")
    huella, n = None, None
    if not motivos:
        try:
            huella, n = huella_de_manifiestos(raiz_dmc)
        except (OSError, extraccion.ErrorExtraccion) as e:
            motivos.append(f"no se pudo calcular la huella de los manifiestos: {type(e).__name__}")
    return EstadoC2(cumple=not motivos, motivos=tuple(motivos), progreso_sha256=sha, huella_manifiestos=huella,
                    n_manifiestos=n, cierre=cierre)


class _LecturaDMC:
    """VER-9: retiene el candado y, al terminar la lectura, recalcula las huellas de C2 y lo suelta."""

    def __init__(self, raiz_dmc: Path, estado: EstadoC2, candado: CandadoDMC):
        self.raiz_dmc, self.estado, self.candado = Path(raiz_dmc), estado, candado
        self.cerrada = False

    def cerrar(self) -> None:
        if self.cerrada:
            return
        if not self.candado.retenido:
            raise ErrorC2("el candado DMC no estuvo retenido durante toda la lectura")
        sha = _sha_o_none(self.raiz_dmc / PROGRESO_DMC)
        try:
            huella, _ = huella_de_manifiestos(self.raiz_dmc)
        except (OSError, extraccion.ErrorExtraccion):
            huella = None
        cambiaron = [n for n, a, b in (("progreso.json", sha, self.estado.progreso_sha256),
                                       ("la huella de los manifiestos", huella, self.estado.huella_manifiestos))
                     if a != b]
        if cambiaron:
            raise ErrorC2(f"al terminar la lectura cambiaron {' y '.join(cambiaron)}: la corrida aborta (§3.1)")
        self.cerrada = True
        self.candado.liberar()


# =========================================================================================================
# Cerrojo y avance
# =========================================================================================================
def _agregar_linea(ruta: Path, linea: bytes | Callable[[bytes], bytes]) -> None:
    """Agrega una línea (O_APPEND, fsync), con flock exclusivo. Si ``linea`` es una función, recibe el
    contenido actual, leído bajo el flock, y devuelve la línea (así se encadena sobre el final real)."""
    entorno.prohibido_volumes(ruta)
    entorno.prohibido_repositorios(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(ruta, os.O_RDWR | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        if callable(linea):
            with open(ruta, "rb") as f:
                linea = linea(f.read())
        os.write(fd, linea)
        os.fsync(fd)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


class Cerrojo:
    """intentos_aplicar.jsonl: sólo agregar; nunca reescribir.

    Cada línea es JSON canónico con «schema», «evento», «intento», «fecha_utc» y «previa_sha256» (la sha256 de
    todo lo anterior): una línea borrada o cambiada rompe la cadena y el cerrojo deja de aceptar intentos.
    Eventos: «intento» (con las huellas de los argumentos), «rechazo», «errata», «corrida_confirmatoria» (con
    «reemplaza» si reemplaza a una sin sellar, VER-7), «reanudacion» y «fin» (resultado «sellada», «detenida» o
    «abortada»). Cada registro relee el archivo bajo su flock (VER-16): las líneas que otro proceso agregó se
    aceptan si la cadena calza y lo ya leído sigue igual al principio."""

    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        self.lineas: list[dict] = []
        self._h = hashlib.sha256()
        self._n_bytes = 0
        self.releer()

    def _leer(self) -> bytes:
        if not (self.ruta.exists() or self.ruta.is_symlink()):
            return b""
        if self.ruta.is_symlink() or not self.ruta.is_file():
            raise ErrorCerrojo("intentos_aplicar.jsonl no es un archivo regular")
        return self.ruta.read_bytes()

    def _adoptar(self, datos: bytes) -> tuple[list[dict], Any]:
        """Verifica ``datos`` y que empiecen con lo ya leído; devuelve (líneas, sha256 acumulada)."""
        if len(datos) < self._n_bytes or hashlib.sha256(datos[:self._n_bytes]).hexdigest() != self._h.hexdigest():
            raise ErrorCerrojo("intentos_aplicar.jsonl cambió desde que se leyó: se borraron o cambiaron líneas")
        return self._verificar(datos)

    def releer(self) -> None:
        """Relee el archivo (por ejemplo, después de tomar el candado propio de --aplicar)."""
        datos = self._leer()
        self.lineas, self._h = self._adoptar(datos)
        self._n_bytes = len(datos)

    @staticmethod
    def _verificar(datos: bytes) -> tuple[list[dict], Any]:
        """Lee y verifica la cadena; devuelve las líneas y la sha256 acumulada (objeto hashlib)."""
        h = hashlib.sha256()
        lineas = []
        if datos and not datos.endswith(b"\n"):
            raise ErrorCerrojo("intentos_aplicar.jsonl termina en una línea incompleta")
        for crudo in datos.splitlines(keepends=True):
            try:
                obj = json.loads(crudo)
            except ValueError:
                raise ErrorCerrojo("intentos_aplicar.jsonl tiene una línea ilegible") from None
            if not isinstance(obj, dict) or obj.get("schema") != ESQUEMA_CERROJO or obj.get("previa_sha256") != h.hexdigest():
                raise ErrorCerrojo("intentos_aplicar.jsonl fue reescrito: la cadena de huellas no calza")
            lineas.append(obj)
            h.update(crudo)
        return lineas, h

    def _de(self, evento: str) -> list[dict]:
        return [ln for ln in self.lineas if ln.get("evento") == evento]

    def hay_corrida_confirmatoria(self) -> bool:
        return bool(self._de("corrida_confirmatoria"))

    def errata_confirmada(self) -> int | None:
        """Número de la errata confirmada y sellada (§10) que habilita una nueva corrida, o None."""
        usadas = {ln.get("errata") for ln in self._de("corrida_confirmatoria")}
        libres = sorted({int(ln["n"]) for ln in self._de("errata")} - usadas)
        return libres[-1] if libres else None

    def selladas(self) -> set[str]:
        return {ln.get("etiqueta") for ln in self._de("fin") if ln.get("resultado") == "sellada"}

    def reemplazadas(self) -> set[str]:
        """Etiquetas de corridas sin sellar que reemplazó la corrida de una errata (VER-7)."""
        return {ln["reemplaza"] for ln in self._de("corrida_confirmatoria") if ln.get("reemplaza")}

    def sin_sellar(self) -> dict | None:
        """La última corrida confirmatoria cuya carpeta no se selló ni se reemplazó (para --reanudar), o None."""
        cerradas = self.selladas() | self.reemplazadas()
        pendientes = [ln for ln in self._de("corrida_confirmatoria") if ln.get("etiqueta") not in cerradas]
        return pendientes[-1] if pendientes else None

    def erratas_usadas(self) -> set[int]:
        return {int(ln["errata"]) for ln in self._de("corrida_confirmatoria") if ln.get("errata") is not None}

    def errata_registrada(self, n: int, sha256: str) -> bool:
        return any(int(ln["n"]) == n and ln.get("documento", {}).get("sha256") == sha256 for ln in self._de("errata"))

    def siguiente_intento(self) -> int:
        return len(self._de("intento")) + 1

    def registrar(self, intento: dict) -> dict:
        """Agrega una línea (nunca reescribe) y la devuelve. La encadena sobre el final real del archivo, leído
        bajo el flock; un «intento» con «intento» = None recibe ahí su número. Falla (ErrorCerrojo) si la
        cadena no calza o si lo ya leído cambió; ValueError si la línea lleva datos privados."""
        if not isinstance(intento, Mapping) or not isinstance(intento.get("evento"), str):
            raise ValueError("cada registro del cerrojo es un objeto con «evento»")
        base = {k: v for k, v in dict(intento).items() if k not in ("schema", "previa_sha256")}
        escrito: dict[str, Any] = {}

        def construir(actual: bytes) -> bytes:
            lineas, h = self._adoptar(actual)
            obj = dict(base)
            if obj["evento"] == "intento" and obj.get("intento") is None:
                obj["intento"] = sum(1 for ln in lineas if ln.get("evento") == "intento") + 1
            obj.update(schema=ESQUEMA_CERROJO, previa_sha256=h.hexdigest())
            linea = entorno.json_canonico(_a_json(obj)) + b"\n"
            if not entorno.sin_datos_privados(linea.decode("utf-8")):
                raise ValueError("el registro del cerrojo lleva «/Users/», «@» o la carpeta personal")
            escrito.update(lineas=lineas, h=h, linea=linea, n=len(actual))
            return linea

        _agregar_linea(self.ruta, construir)
        linea = escrito["linea"]
        escrito["h"].update(linea)
        self.lineas, self._h, self._n_bytes = escrito["lineas"] + [json.loads(linea)], escrito["h"], \
            escrito["n"] + len(linea)
        return self.lineas[-1]


class Avance:
    """avance.jsonl: huellas de entrada y salida por unidad; al reanudar se saltan las iguales (§9).

    Sólo huellas y estado: {"unidad", "entrada", "salida", "estado": "hecho"}. Una línea incompleta (un corte a
    mitad de escritura) se ignora y su unidad se rehace."""

    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        self._hechos: dict[str, tuple[str, str]] = {}
        self.ignoradas = 0
        if self.ruta.exists():
            if self.ruta.is_symlink() or not self.ruta.is_file():
                raise ValueError("avance.jsonl no es un archivo regular")
            for crudo in self.ruta.read_bytes().splitlines():
                try:
                    obj = json.loads(crudo)
                    unidad, entrada, salida = obj["unidad"], obj["entrada"], obj["salida"]
                    if obj.get("estado") != "hecho" or not _SHA.fullmatch(entrada) or not _SHA.fullmatch(salida):
                        raise ValueError
                except (ValueError, KeyError, TypeError):
                    self.ignoradas += 1
                    continue
                self._hechos[unidad] = (entrada, salida)

    def hecho(self, unidad: str, huella_entrada: str) -> bool:
        return self._hechos.get(unidad, (None, None))[0] == huella_entrada

    def registrar(self, unidad: str, huella_entrada: str, huella_salida: str) -> None:
        if not isinstance(unidad, str) or not _UNIDAD_AVANCE.fullmatch(unidad):
            raise ValueError(f"unidad de avance inválida: {unidad!r}")
        for h in (huella_entrada, huella_salida):
            if not isinstance(h, str) or not _SHA.fullmatch(h):
                raise ValueError("avance.jsonl sólo admite huellas sha256")
        linea = entorno.json_canonico({"unidad": unidad, "entrada": huella_entrada, "salida": huella_salida,
                                       "estado": "hecho"}) + b"\n"
        if self.ruta.exists() and self.ruta.stat().st_size:
            with open(self.ruta, "rb") as f:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    linea = b"\n" + linea          # deja aislada la línea incompleta de un corte
        _agregar_linea(self.ruta, linea)
        self._hechos[unidad] = (huella_entrada, huella_salida)


class _CandadoAplicar:
    """VER-16: candado propio de --aplicar en LOCAL/…/v1/.aplicar.lock (lo crea si falta; nunca en /Volumes ni
    en los repositorios), con flock exclusivo sin bloqueo retenido hasta salir. ``tomado`` dice si se tomó."""

    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        self.tomado = False
        self._fd: int | None = None

    def __enter__(self) -> "_CandadoAplicar":
        entorno.prohibido_volumes(self.ruta)
        entorno.prohibido_repositorios(self.ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.ruta, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o644)
        except OSError:
            return self
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return self
        self._fd, self.tomado = fd, True
        return self

    def __exit__(self, *exc) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd, self.tomado = None, False


# =========================================================================================================
# Consola, carpeta y registro de accesos
# =========================================================================================================
def consola(fase: str, hechos: int, total: int) -> None:
    """Sólo conteos de avance (nunca veredictos) hasta el sello (§5.2). ``fase`` es un identificador del código
    (sin espacios); a lo más PASOS_CONSOLA líneas por fase, y siempre la primera y la última."""
    if not isinstance(fase, str) or not _FASE_CONSOLA.fullmatch(fase):
        raise ValueError("consola: la fase debe ser un identificador sin espacios")
    for x in (hechos, total):
        if isinstance(x, bool) or not isinstance(x, (int, np.integer)):
            raise ValueError("consola: sólo conteos enteros")
    hechos, total = int(hechos), int(total)
    paso = max(1, total // PASOS_CONSOLA) if total > 0 else 1
    if total <= 0 or hechos in (0, 1, total) or hechos % paso == 0:
        print(f"[reloj_dmc] {fase}: {hechos}/{total}", flush=True)


def carpeta_corrida(corridas: Path, fecha_utc: str, errata: int | None) -> Path:
    """LOCAL/…/v1/HUMAN<AAAAMMDD>_RELOJ_DMC_1, con «_ERRATA<n>» si la corrida es la de una errata (§7.1, §10)."""
    fecha = _fecha_ocho(fecha_utc)
    if fecha is None:
        raise ValueError(f"fecha UTC inválida: {fecha_utc!r}")
    nombre = ETIQUETA_CORRIDA.format(fecha=fecha)
    if errata is not None:
        if isinstance(errata, bool) or not isinstance(errata, int) or errata < 1:
            raise ValueError("el número de errata es un entero ≥ 1")
        nombre += SUFIJO_ERRATA.format(n=errata)
    return Path(corridas) / nombre


_EVENTOS_DE_RUTA = frozenset({
    "open", "os.listdir", "os.scandir", "os.chdir", "os.mkdir", "os.rename", "os.remove", "os.rmdir",
    "os.symlink", "os.link", "os.truncate", "os.utime", "os.chmod", "os.chown", "os.listxattr", "os.getxattr",
    "glob.glob", "shutil.copyfile", "shutil.copytree", "shutil.rmtree", "shutil.move"})
_GANCHO: dict[str, Any] = {"instalado": False, "activos": [], "stat": os.stat, "lstat": os.lstat}


def _ver_en_registros(evento: str, ruta) -> None:
    """VER-14: los registros activos, del más interior al más exterior. Anotan el acceso hasta el primero que
    bloquea, que lo niega antes de que ocurra; los de afuera lo anotan en ``negados_dentro``."""
    activos = list(_GANCHO["activos"])
    if not activos:
        return
    try:
        texto = os.path.normpath(os.path.abspath(os.fsdecode(ruta)))
    except (TypeError, ValueError):
        return
    clave = texto.casefold()
    negado = False
    for registro in reversed(activos):
        if not registro._vigila(clave):
            continue
        if negado:
            registro.negados_dentro.append((evento, texto))
            continue
        registro.accesos.append((evento, texto))
        negado = registro.bloquear
    if negado:
        raise PermissionError(f"acceso prohibido bajo una carpeta vigilada ({evento})")


def _gancho_auditoria(evento: str, args: tuple) -> None:
    if not _GANCHO["activos"] or evento not in _EVENTOS_DE_RUTA:
        return
    for a in args[:2]:
        if isinstance(a, (str, bytes, os.PathLike)):
            _ver_en_registros(evento, a)


def _envoltorio(nombre: str):
    original = _GANCHO[nombre]

    def envoltorio(path, *a, **k):
        if _GANCHO["activos"] and isinstance(path, (str, bytes, os.PathLike)):
            _ver_en_registros(f"os.{nombre}", path)
        return original(path, *a, **k)
    envoltorio.__wrapped__ = original
    return envoltorio


class RegistroAccesos:
    """Registro de accesos bajo unas carpetas (§8, prueba 27; VER-14): «open» y los listados por un gancho de
    auditoría (sys.addaudithook; se instala una vez y queda inerte fuera del contexto) y os.stat / os.lstat
    con envoltorios mientras dura. Con ``bloquear`` un acceso lanza PermissionError antes de ocurrir (falla
    cerrado). ``accesos``: los que vio y no negó antes un registro más interior; ``negados_dentro``: los que
    negó un registro más interior (no llegaron al disco)."""

    def __init__(self, vigiladas: Iterable[Path | str], *, bloquear: bool = False):
        self.vigiladas = tuple(os.path.normcase(os.path.normpath(os.path.abspath(os.fspath(v)))).casefold()
                               for v in vigiladas)
        self.bloquear = bloquear
        self.accesos: list[tuple[str, str]] = []
        self.negados_dentro: list[tuple[str, str]] = []

    def _vigila(self, clave: str) -> bool:
        return any(clave == v or clave.startswith(v.rstrip(os.sep) + os.sep) for v in self.vigiladas)

    def __enter__(self) -> "RegistroAccesos":
        if not _GANCHO["instalado"]:
            sys.addaudithook(_gancho_auditoria)     # no se puede quitar: queda inerte sin registros activos
            _GANCHO["instalado"] = True
        if not _GANCHO["activos"]:
            os.stat, os.lstat = _envoltorio("stat"), _envoltorio("lstat")
        _GANCHO["activos"].append(self)
        return self

    def __exit__(self, *exc) -> None:
        _GANCHO["activos"].remove(self)
        if not _GANCHO["activos"]:
            os.stat, os.lstat = _GANCHO["stat"], _GANCHO["lstat"]


# =========================================================================================================
# --sintetico (C1)
# =========================================================================================================
def _texto_redactado(texto: str) -> str:
    return "\n".join(salidas.redactar(linea) for linea in texto.splitlines()) + "\n"


def correr_pruebas(paquete: Path, patron: str = PATRON_PRUEBAS) -> tuple[unittest.TestResult, str]:
    """unittest discover sobre tests/ del paquete (grupos A a D de §8 y C1), con su salida en texto."""
    paquete = Path(paquete)
    suite = unittest.TestLoader().discover(start_dir=str(paquete / "tests"), pattern=patron,
                                           top_level_dir=str(paquete.parent))
    flujo = io.StringIO()
    resultado = unittest.TextTestRunner(stream=flujo, verbosity=2).run(suite)
    return resultado, flujo.getvalue()


def _resumen_pruebas(r: unittest.TestResult, patron: str) -> dict:
    """Conteos de unittest. «aprobadas» sólo si corrió alguna y no hubo fallas, errores, omitidas, fallas
    esperadas ni éxitos inesperados (VER-15: wasSuccessful() da por buenas las omitidas y las esperadas)."""
    conteos = {"corridas": r.testsRun, "fallas": len(r.failures), "errores": len(r.errors), "omitidas": len(r.skipped),
               "fallas_esperadas": len(r.expectedFailures), "exitos_inesperados": len(r.unexpectedSuccesses)}
    aprobadas = conteos["corridas"] > 0 and not any(v for k, v in conteos.items() if k != "corridas")
    return {"patron": patron, "completa": patron == PATRON_PRUEBAS, **conteos, "aprobadas": aprobadas}


_MOTIVOS_PRUEBAS = (("fallas", "fallas"), ("errores", "errores"), ("omitidas", "omitidas (no se dan por aprobadas)"),
                    ("fallas_esperadas", "fallas esperadas (pruebas de §8 que no pasan)"),
                    ("exitos_inesperados", "éxitos inesperados"))


def _motivos_c1(estado: Mapping, *, con_bateria: bool) -> list[str]:
    """VER-15: por qué la corrida no aprueba C1 ([] si aprueba). Sólo conteos y textos fijos."""
    p = estado["pruebas"]
    motivos = []
    if not p["completa"]:
        motivos.append(f"patrón parcial ({p['patron']}): C1 corre todas las pruebas de tests/")
    if p["corridas"] == 0:
        motivos.append("no corrió ninguna prueba")
    motivos += [f"{p[clave]} {texto}" for clave, texto in _MOTIVOS_PRUEBAS if p[clave]]
    if not con_bateria:
        motivos.append("sin --bateria: falta el grupo D (§10, C1: «grupos A a D»)")
    elif not estado["bateria"]["pasa"]:
        motivos.append("la batería no aprueba (criterios de §8.D o §8.F)")
    if estado["ceguera"]["accesos"]:
        motivos.append(f"{estado['ceguera']['accesos']} accesos bajo las carpetas vigiladas, negados (§8, prueba 27)")
    return motivos


def _correr_bateria(salida: Path, U, bateria: ModuleType, reloj: Callable[[], datetime]
                    ) -> tuple[dict[str, str], bool, dict]:
    """§8.D y §8.F (VER-15): medición, tabla, ajuste y criterios, con las salidas que escribe bateria;
    devuelve (huellas, pasa, resumen)."""
    def avance(k, n):
        consola("bateria", k, n)

    tabla = bateria.tabla_bateria()
    tiempos: dict = {}
    res0, h0 = bateria.correr_bateria(tabla, U, avance=avance, tiempos=tiempos)
    tiempo = bateria.tiempo_bateria(float(h0), tabla, U, tiempos=tiempos)      # la primera medición (§8.D)
    reduccion = bateria.replicas_por_tiempo(float(h0), U)
    corridas = 1
    if reduccion is not None:
        tabla = bateria.tabla_bateria(reduccion)
        res0, _ = bateria.correr_bateria(tabla, U, avance=avance)
        corridas += 1
    guardadas = {U.huella(): res0}
    ultimos: dict[str, Any] = {}

    def correr(u):
        nonlocal corridas
        res = guardadas.pop(u.huella(), None)
        if res is None:
            res, _ = bateria.correr_bateria(tabla, u, avance=avance)
            corridas += 1
        ultimos.update(resultados=res, umbrales=u)
        return res

    ruta_registro = Path(salida) / bateria.ARCHIVO_REGISTRO_8F
    entorno.prohibido_volumes(ruta_registro)
    entorno.prohibido_repositorios(ruta_registro)
    registro = bateria.ajustar_umbrales(U, correr, tabla, ruta_registro=ruta_registro, reloj=reloj)
    resultados = registro.resultados if registro.resultados is not None else ultimos.get("resultados", res0)
    criterios = registro.criterios
    if criterios is None:
        criterios = bateria.criterios_por_celda(resultados, tabla, registro.umbrales_finales
                                                or ultimos.get("umbrales", U))
    huellas = dict(bateria.escribir_salidas(salida, tabla, resultados, criterios, tiempo))
    huellas[bateria.ARCHIVO_REGISTRO_8F] = entorno.sha256_archivo(ruta_registro)
    pasa = bool(criterios.pasa) and not bool(registro.c1_falla)
    return huellas, pasa, {"pasa": pasa, "c1_falla": bool(registro.c1_falla), "iteraciones": len(registro.iteraciones),
                           "corridas": corridas, "replicas_d2_d3": reduccion}


def _modulo_bateria() -> ModuleType:
    """reloj_dmc.bateria, importado al usarlo (se implementa aparte; las pruebas lo simulan)."""
    return importlib.import_module("reloj_dmc.bateria")


def _escribir_carpeta(salida: Path, contenidos: Callable[[], dict[str, str]], conocidos: Sequence[str]) -> dict[str, str]:
    """Como C3-13: borra el sha256.json previo, escribe, borra los archivos conocidos que no se rehicieron y
    deja sha256.json al final."""
    salida = Path(salida)
    for r in (salida / ARCHIVO_HUELLAS,):
        entorno.prohibido_volumes(r)
        entorno.prohibido_repositorios(r)
        if r.exists():
            r.unlink()
    huellas = contenidos()
    for nombre in conocidos:
        if nombre not in huellas and (salida / nombre).is_file():
            (salida / nombre).unlink()
    entorno.escribir_atomico(salida / ARCHIVO_HUELLAS, entorno.json_canonico(dict(sorted(huellas.items()))))
    return huellas


def modo_sintetico(args: argparse.Namespace) -> int:
    """Grupos A a C (unittest de tests/), batería D si --bateria (con medición de tiempo y §8.F), y su
    salida guardada fuera de los repositorios (R-32), con el registro de accesos bajo /Volumes (prueba 27)."""
    cfg = _configuracion(args)
    salida = Path(args.salida) if args.salida else cfg.rutas.corridas / CARPETA_C1
    entorno.prohibido_volumes(salida)
    entorno.prohibido_repositorios(salida)
    try:
        interprete = {k: v for k, v in entorno.comprobar_interprete().items() if k != "interprete"}
    except RuntimeError as e:
        _aviso(f"C1 no corre: {e}")
        return SALIDA_RECHAZO
    estado: dict[str, Any] = {"interprete": interprete}

    def contenidos() -> dict[str, str]:
        huellas = {}
        # VER-14: en bloqueo (nada llega a /Volumes); cuenta lo que no negó antes un registro de las pruebas.
        with RegistroAccesos(cfg.vigiladas_c1, bloquear=True) as registro:
            resultado, texto = correr_pruebas(cfg.paquete, args.patron)
            huellas[ARCHIVO_PRUEBAS] = entorno.escribir_atomico(salida / ARCHIVO_PRUEBAS,
                                                                _texto_redactado(texto).encode("utf-8"))
            estado["pruebas"] = _resumen_pruebas(resultado, args.patron)
            if args.bateria:
                U = mod_umbrales.cargar_c0(cfg.rutas.aph)
                hb, pasa, resumen = _correr_bateria(salida, U, _modulo_bateria(), cfg.reloj)
                huellas.update(hb)
                estado["bateria"] = resumen
        estado["ceguera"] = {"vigiladas": [str(v) for v in cfg.vigiladas_c1], "accesos": len(registro.accesos),
                             "eventos": sorted({e for e, _ in registro.accesos}),
                             "negados_por_las_pruebas": len(registro.negados_dentro)}
        motivos = _motivos_c1(estado, con_bateria=bool(args.bateria))
        estado.update(motivos=motivos, exito=not motivos)
        resumen = {"schema": ESQUEMA_RESUMEN_C1, **estado}
        huellas[ARCHIVO_RESUMEN_C1] = entorno.escribir_atomico(salida / ARCHIVO_RESUMEN_C1,
                                                               entorno.json_canonico(_a_json(resumen)))
        return huellas

    _escribir_carpeta(salida, contenidos, ARCHIVOS_C1)
    p = estado["pruebas"]
    consola("pruebas_C1", p["corridas"], p["corridas"])
    _aviso(f"C1: {p['corridas']} pruebas, {p['fallas']} fallas, {p['errores']} errores, {p['omitidas']} omitidas, "
           f"{p['fallas_esperadas']} fallas esperadas, {p['exitos_inesperados']} éxitos inesperados; accesos bajo "
           f"las carpetas vigiladas: {estado['ceguera']['accesos']}; salida en {_alias(salida, cfg.rutas)}")
    _aviso("C1 aprobado (VER-15)" if estado["exito"] else "C1 no aprobado: " + "; ".join(estado["motivos"]))
    return SALIDA_OK if estado["exito"] else SALIDA_FALLA


# =========================================================================================================
# --control-era5 (C3)
# =========================================================================================================
def cargar_meteo_guard(ap_codigo: Path) -> ModuleType:
    """El guardián fijado de la descarga (``_meteo_guard.py``, 06e59f13…), cargado por ruta y huella."""
    return fijados.cargar_por_ruta(Path(ap_codigo) / RUTA_METEO_GUARD, fijados.SHA_METEO_GUARD, MODULO_METEO_GUARD)


def descargas_activas(cfg: Configuracion) -> list[dict]:
    """VER-12: procesos productores de datos, según ``_meteo_guard.data_producers`` (sin tocar la DMC)."""
    guardian = cargar_meteo_guard(cfg.ap_codigo)
    procesos = guardian.parse_processes(cfg.procesos())
    activas = guardian.data_producers(procesos, allowed_pids=(os.getpid(),))
    return [{"pid": int(p["pid"]), "script": str(p.get("script") or "?"), "tipo": str(p.get("kind"))} for p in activas]


def _huellas_codigo(paquete: Path) -> dict[str, str]:
    """sha256 de cada .py del paquete (sin tests/), como en las huellas del informe de C4."""
    return {f"reloj_dmc/{n}": entorno.sha256_archivo(p) for n, p in _codigo_del_paquete(paquete).items() if "/" not in n}


def _umbrales_c3(args: argparse.Namespace, cfg: Configuracion) -> tuple[Any, dict]:
    """VER-13: los umbrales de la lista cerrada del addendum de C1, comprobada con las raíces de ``cfg``."""
    if args.addendum is None:
        raise ValueError("C3 va después de C1 (§10): falta --addendum")
    motivos = comprobar_lista_cerrada(Path(args.addendum), rutas=cfg.rutas, exigidos=_exigidos(cfg))
    if motivos:
        raise ValueError("; ".join(motivos))
    datos = leer_addendum(Path(args.addendum))
    U = mod_umbrales.cargar_umbrales(resolver_alias(datos["configuracion"]["ruta"], cfg.rutas),
                                     resolver_alias(datos["texto_v1_1"]["ruta"], cfg.rutas),
                                     sha256_json=datos["configuracion"]["sha256"])
    fuente = {"fuente": "addendum_c1", "sha256_json": U.sha256_json, "texto_v1_1": datos["texto_v1_1"],
              "addendum_c1": {"ruta": _alias(Path(args.addendum), cfg.rutas),
                              "sha256": entorno.sha256_archivo(Path(args.addendum)), "commit_c1": datos["commit_c1"]}}
    return U, fuente


def modo_control_era5(args: argparse.Namespace) -> int:
    """C3a, C3b y C3c; comprueba antes (y después) que no haya descargas activas, sin tocar la DMC.

    La lista cerrada se comprueba con las raíces de la configuración; --salida cambia sólo dónde se escribe."""
    cfg = _configuracion(args)
    rutas = cfg.rutas if not args.salida else replace(cfg.rutas, local=Path(args.salida))
    if cfg.nice:
        os.nice(cfg.nice)
    with RegistroAccesos((rutas.dmc,), bloquear=True):
        activas = descargas_activas(cfg)
        if activas:
            _aviso(f"C3 no corre: hay {len(activas)} descargas activas ("
                   + ", ".join(sorted({a['script'] for a in activas})[:MAX_EJEMPLOS]) + ") (§8.E)")
            return SALIDA_RECHAZO
        try:
            U, fuente = _umbrales_c3(args, cfg)
        except (OSError, ValueError, mod_umbrales.ErrorUmbrales) as e:
            _aviso(f"C3 no corre: umbrales no verificables: {e}")
            return SALIDA_RECHAZO
        consola("C3_preparacion", 0, 1)
        catalogo = extraccion.leer_catalogo_pixeles(cfg.catalogo_pixeles, cfg.sha_catalogo_pixeles)
        validos = extraccion.pixeles_validos(rutas.era5l, U)
        mz = fijados.macrozona_region(cfg.ap_codigo)
        calendario = mod_tablas.cargar_tablas()
        adaptador = fijados.cargar_adaptador(cfg.ap_codigo)
        avance = Avance(rutas.corridas / controles_era5.CARPETA_EXTRACTOS_C3 / AVANCE)
        consola("C3_preparacion", 1, 1)
        resultados, huellas = controles_era5.correr_c3(rutas, catalogo, validos, mz, U, tablas_calendario=calendario,
                                                       avance=consola, hecho=avance.hecho, registrar=avance.registrar,
                                                       adaptador=adaptador)
        despues = descargas_activas(cfg)
    carpeta = controles_era5.carpeta_c3(rutas)
    registro = {"schema": ESQUEMA_REGISTRO_C3, "umbrales": fuente, "codigo": _huellas_codigo(cfg.paquete),
                "descargas_activas_antes": 0, "descargas_activas_despues": len(despues),
                "sha256_json": _sha_o_none(carpeta / controles_era5.NOMBRE_HUELLAS),
                "controles": {r.control: bool(r.pasa) for r in resultados}, "archivos": dict(sorted(huellas.items()))}
    entorno.escribir_atomico(rutas.corridas / ARCHIVO_REGISTRO_C3, entorno.json_canonico(_a_json(registro)))
    for r in resultados:
        _aviso(f"{r.control}: {'pasa' if r.pasa else 'no pasa'}")
    if despues:
        _aviso(f"durante C3 empezó una descarga ({len(despues)}): C3 no vale (§8.E)")
        return SALIDA_FALLA
    return SALIDA_OK if all(r.pasa for r in resultados) else SALIDA_FALLA


# =========================================================================================================
# --aplicar (C4)
# =========================================================================================================
@dataclass
class _Corrida:
    """Estado de un intento de --aplicar (para el cerrojo y los mensajes)."""
    cfg: Configuracion
    args: argparse.Namespace
    cerrojo: Cerrojo
    intento: int
    fecha: str
    addendum: dict | None = None
    errata: int | None = None
    errata_doc: dict | None = None
    enmienda4: dict = field(default_factory=dict)
    reanuda: dict | None = None
    reemplaza: str | None = None           # etiqueta de la corrida sin sellar que reemplaza una errata (VER-7)
    etiqueta: str | None = None
    carpeta: Path | None = None
    fase: str = FASE_C2
    confirmatoria: bool = False
    solo_fin: bool = False                 # --reanudar de una corrida sellada sin «fin» en el cerrojo (VER-16)

    def registrar(self, evento: str, **datos) -> None:
        self.cerrojo.registrar({"evento": evento, "intento": self.intento, "fecha_utc": self.fecha, **datos})

    def registrar_o_avisar(self, evento: str, **datos) -> bool:
        """VER-11: registra; si el cerrojo falla, avisa sólo el tipo del error (sin relanzarlo) y da False."""
        try:
            self.registrar(evento, **datos)
        except Exception as e:      # noqa: BLE001 (el mensaje puede traer contenido de la corrida)
            _aviso(f"no se pudo registrar «{evento}» en intentos_aplicar.jsonl ({type(e).__name__})")
            return False
        return True


ARGUMENTOS_CON_ARCHIVO = ("addendum", "linea_cierre", "errata", "enmienda4")


def _argumentos_por_alias(args: argparse.Namespace, rutas: entorno.Rutas) -> dict:
    salida = {"reanudar": bool(args.reanudar)}
    for clave in ARGUMENTOS_CON_ARCHIVO:
        valor = getattr(args, clave, None)
        salida[clave] = None if valor is None else _alias(Path(valor), rutas)
    return salida


def _huellas_argumentos(args: argparse.Namespace, rutas: entorno.Rutas) -> dict:
    """§7.1 y VER-16: sha256 de los archivos pasados por argumento (None si no se pasó, falta o no está en APH:
    nada fuera de APH se lee aquí, y la DMC nunca)."""
    salida: dict[str, str | None] = {}
    for clave in ARGUMENTOS_CON_ARCHIVO:
        valor = getattr(args, clave, None)
        ruta = None if valor is None else _lexica(valor)
        salida[clave] = _sha_o_none(ruta) if ruta is not None and _alias(ruta, rutas).startswith("APH/") else None
    return salida


def _rechazos_sin_dmc(c: _Corrida) -> list[str]:
    """VER-5: lista cerrada, git, cerrojo, entorno y carpeta; nada bajo DMC."""
    cfg, args, rutas = c.cfg, c.args, c.cfg.rutas
    motivos: list[str] = []
    try:
        entorno.comprobar_interprete()
    except RuntimeError as e:
        motivos.append(str(e))
    motivos += _comprobar_codigo_fijado(cfg.ap_codigo)
    # 1. Lista cerrada del addendum (y su registro en git, E1-6).
    motivos += comprobar_lista_cerrada(Path(args.addendum), rutas=rutas, exigidos=_exigidos(cfg))
    try:
        c.addendum = leer_addendum(Path(args.addendum))
    except (OSError, ValueError, UnicodeDecodeError):
        c.addendum = None
    rutas_protocolo = list(cfg.rutas_protocolo)
    if c.addendum is not None:
        _, extra = _registro_archivo(Path(args.addendum), rutas.aph, "el addendum de C1",
                                     fecha=_fecha_ocho(c.addendum["fecha"]), archivo=ARCHIVO_ADDENDUM,
                                     declarado=c.addendum["commit_c1"])
        motivos += extra
        rutas_protocolo += [a for a in c.addendum["lista_cerrada"] if a.split("/", 1)[0] in ("AP", "APH")]
        rutas_protocolo += list(c.addendum.get("rutas_protocolo", []))
    for valor, carpeta in ((args.addendum, True), (args.linea_cierre, True), (args.errata, True),
                           (args.enmienda4, False)):
        if valor is not None:
            ruta = Path(valor).resolve()
            alias = _alias(ruta.parent if carpeta else ruta, rutas)
            if alias.startswith("APH/"):
                rutas_protocolo.append(alias)
    # 2. Git: árbol limpio en las rutas del protocolo y commit de C1 en origin/main.
    motivos += comprobar_git(rutas.ap, rutas.aph, sorted(set(rutas_protocolo)),
                             c.addendum["commit_c1"] if c.addendum else "")
    # 4. Cerrojo (y errata, VER-6 y VER-7).
    if args.errata is not None and args.reanudar:
        motivos.append("--errata y --reanudar no se combinan: una reanudación sigue con la errata de su corrida")
    elif args.errata is not None:
        try:
            doc = leer_errata(Path(args.errata))
        except (OSError, ValueError, UnicodeDecodeError) as e:
            motivos.append(f"la errata no se puede usar: {e}")
        else:
            reg, extra = _registro_archivo(Path(args.errata), rutas.aph, "la errata", fecha=_fecha_ocho(doc["fecha"]),
                                           archivo=PATRON_ERRATA)
            m = PATRON_ERRATA.fullmatch(Path(args.errata).name)
            if m is not None and m.group(1) != str(doc["n"]):
                extra.append("el número de la errata no es el de su archivo")
            for clave in ("prueba", "sello"):
                try:
                    ruta = resolver_alias(doc[clave]["ruta"], rutas)
                except ValueError:
                    extra.append(f"errata: «{clave}» fuera de AP, APH o LOCAL")
                    continue
                if _sha_o_none(ruta) != doc[clave]["sha256"]:
                    extra.append(f"errata: falta «{clave}» o su huella difiere (sellada con testigo externo, §10)")
            if extra:
                motivos += extra
            else:
                c.errata_doc = {"n": doc["n"], "documento": {"ruta": _alias(Path(args.errata), rutas),
                                                             "sha256": entorno.sha256_archivo(Path(args.errata)),
                                                             "commit": reg.commit}}
    pendiente = c.cerrojo.sin_sellar()
    if args.reanudar:
        if pendiente is None:
            motivos.append("--reanudar: no hay una corrida confirmatoria sin sellar")
        else:
            c.reanuda = pendiente
            c.errata = pendiente.get("errata")
    elif c.cerrojo.hay_corrida_confirmatoria():
        libre = c.cerrojo.errata_confirmada()
        nueva = c.errata_doc["n"] if c.errata_doc else None
        if nueva is not None and nueva in c.cerrojo.erratas_usadas():
            motivos.append(f"la errata {nueva} ya se usó en una corrida")
        elif pendiente is not None and nueva is None:
            motivos.append("intentos_aplicar.jsonl registra una corrida confirmatoria sin sellar: se retoma con "
                           "--reanudar, o se reemplaza con una errata sellada (--errata, VER-7)")
        elif libre is None and nueva is None:
            motivos.append(MOTIVO_CERROJO)
        else:
            c.errata = nueva if nueva is not None else libre
            c.reemplaza = pendiente["etiqueta"] if pendiente is not None else None     # VER-7
    elif c.errata_doc is not None:
        motivos.append("hay una errata, pero ninguna corrida confirmatoria que corregir")
    # Carpeta de la corrida.
    if c.reanuda is not None:
        c.etiqueta = c.reanuda["etiqueta"]
        c.carpeta = rutas.corridas / c.etiqueta
        if (c.carpeta / salidas.RECIBO).exists():
            if salidas.verificar_sello(c.carpeta):
                motivos.append("la carpeta de la corrida que se reanuda está sellada, pero su sello no verifica")
            else:
                c.solo_fin = True          # selló, pero su «fin» no quedó en el cerrojo (VER-16)
    else:
        c.carpeta = carpeta_corrida(rutas.corridas, c.fecha, c.errata)
        c.etiqueta = c.carpeta.name
        if (c.carpeta / salidas.RECIBO).exists():
            motivos.append(f"la carpeta {c.etiqueta} ya existe y está sellada")
        elif c.carpeta.exists():
            motivos.append(f"la carpeta {c.etiqueta} ya existe: una corrida sin sellar sólo se retoma con --reanudar")
    return motivos


def _enmienda4(args: argparse.Namespace, rutas: entorno.Rutas) -> dict:
    """VER-8."""
    if args.enmienda4 is None:
        return {"anclado": False, "motivo": "no se pasó --enmienda4"}
    ruta = Path(args.enmienda4)
    reg = registro_en_git(ruta, rutas.aph, "el punto 12 de la Enmienda 4")
    return {"anclado": not reg.motivos, "ruta": _alias(ruta, rutas), "sha256": _sha_o_none(ruta), "commit": reg.commit,
            "motivos": list(reg.motivos)}


def _huellas_entrada(c: _Corrida, U, calendario, estado: EstadoC2, sha_catalogo: str, controles_era5_: Mapping,
                     meses: pd.DataFrame, adaptador_sha: str) -> dict:
    cfg, rutas = c.cfg, c.cfg.rutas
    interprete = {k: v for k, v in entorno.comprobar_interprete().items() if k != "interprete"}
    return {
        "protocolo": dict(c.addendum["texto_v1_1"]),
        "configuracion": {"ruta": c.addendum["configuracion"]["ruta"], "sha256": U.sha256_json},
        "codigo": _huellas_codigo(cfg.paquete),
        "adaptador": {"sha256": adaptador_sha, "dmc_features_sha256": fijados.SHA_DMC_FEATURES,
                      "preflight_v3_sha256": fijados.SHA_PREFLIGHT_V3, "meteo_guard_sha256": fijados.SHA_METEO_GUARD},
        "interprete": interprete,
        "anexo_a": {"sha256": calendario.sha256_anexo_a}, "anexo_a2": {"sha256": calendario.sha256_anexo_a2},
        "manifiestos": {"huella_agregada": estado.huella_manifiestos, "n": int(len(meses))},
        "progreso": {"ruta": f"DMC/{PROGRESO_DMC}", "sha256": estado.progreso_sha256},
        "catalogo_dmc": {"ruta": f"DMC/{extraccion.NOMBRE_CATALOGO_DMC}", "sha256": sha_catalogo},
        "era5l": {m: (ctl.sha256 or None) for m, ctl in sorted(controles_era5_.items())},
        "copias_c2": {_alias(p, rutas): entorno.sha256_archivo(p) for p in _archivos_regulares(cfg.copias_c2)},
        "corrida": {"etiqueta": c.etiqueta, "errata": c.errata, "intento": None, "reemplaza": c.reemplaza},
        "addendum_c1": {"ruta": _alias(Path(c.args.addendum), rutas), "sha256": entorno.sha256_archivo(Path(c.args.addendum)),
                        "commit_c1": c.addendum["commit_c1"]},
        "cierre_c2": {"ruta": _alias(Path(c.args.linea_cierre), rutas),
                      "sha256": entorno.sha256_archivo(Path(c.args.linea_cierre)),
                      "commit": (estado.cierre or {}).get("commit")},
        "enmienda4_punto12": c.enmienda4,
        "versiones_admitidas": sorted(c.addendum["versiones_admitidas"]),
        "catalogo_pixeles": {"ruta": _alias(cfg.catalogo_pixeles, rutas), "sha256": cfg.sha_catalogo_pixeles},
    }


def _entradas_confirmatorias(c: _Corrida, estado: EstadoC2) -> dict:
    """Lo que debe ser igual para reanudar (VER-6)."""
    return {"addendum_sha256": entorno.sha256_archivo(Path(c.args.addendum)),
            "cierre_sha256": entorno.sha256_archivo(Path(c.args.linea_cierre)),
            "progreso_sha256": estado.progreso_sha256, "huella_manifiestos": estado.huella_manifiestos,
            "commit_c1": c.addendum["commit_c1"]}


def _retener_error(c: _Corrida, e: BaseException) -> str | None:
    """VER-11: el detalle del error (redactado) dentro de la carpeta; devuelve su nombre."""
    if c.carpeta is None or not c.carpeta.is_dir():
        return None
    try:
        detalle = getattr(e, "detalle", None) or "".join(traceback.format_exception(type(e), e, e.__traceback__))
        nombre = f"error_retenido_{c.intento}.json"
        entorno.escribir_atomico(c.carpeta / nombre, entorno.json_canonico(
            {"intento": c.intento, "fase": c.fase, "tipo": type(e).__name__, "detalle": salidas.redactar(detalle)}))
    except Exception:          # el registro del cerrojo va igual; el detalle se pierde
        return None
    return nombre


def _correr_confirmatoria(c: _Corrida, candado: CandadoDMC, estado: EstadoC2, U, calendario) -> dict:
    """Fases 2 a 11 de §5.2 dentro del candado; devuelve el resumen de salidas.escribir_corrida."""
    cfg, rutas, carpeta = c.cfg, c.cfg.rutas, c.carpeta
    lectura = _LecturaDMC(rutas.dmc, estado, candado)
    carpeta.mkdir(parents=True, exist_ok=True)
    avance = Avance(carpeta / AVANCE)
    catalogo_dmc, sha_catalogo = extraccion.leer_catalogo_dmc(rutas.dmc / extraccion.NOMBRE_CATALOGO_DMC)
    consola(FASE_C2, 1, 1)

    # Fase 2: ERA5-Land (y A1, antes de leer la DMC: §5.4).
    c.fase = FASE_ERA5
    catalogo_pixeles = extraccion.leer_catalogo_pixeles(cfg.catalogo_pixeles, cfg.sha_catalogo_pixeles)
    validos = extraccion.pixeles_validos(rutas.era5l, U)
    enlaces = extraccion.enlazar_pixeles(catalogo_dmc, catalogo_pixeles, validos, U)
    pixel_ids = sorted({e.pixel_id for e in enlaces.values() if e.pixel_id is not None})
    serie, ctl_era5 = extraccion.extraer_era5land(rutas.era5l, pixel_ids, carpeta, hecho=avance.hecho,
                                                  registrar=avance.registrar,
                                                  avance=lambda k, n: consola(FASE_ERA5, k, n), validos=validos,
                                                  catalogo_sha256=cfg.sha_catalogo_pixeles)
    a1 = red.a1(True, ctl_era5)
    if not a1.pasa:
        return {"detenida": "A1", "detalle": _a_json(a1.detalle)}
    medias_sp = {p: serie.media(p, "sp") for p in pixel_ids}

    # Fase 3: extracción DMC (el primer artefacto se lee aquí).
    c.fase = FASE_DMC
    adaptador = fijados.cargar_adaptador(cfg.ap_codigo)
    versiones = set(c.addendum["versiones_admitidas"])
    resumen_dmc = extraccion.extraer_dmc(rutas.dmc, adaptador, versiones, U, carpeta, hecho=avance.hecho,
                                         registrar=avance.registrar, avance=lambda k, n: consola(FASE_DMC, k, n))
    if resumen_dmc.huella_manifiestos != estado.huella_manifiestos:
        raise ErrorC2("los manifiestos que leyó la extracción no son los de C2: la corrida aborta (§3.1)")
    meses = extraccion.leer_meses(carpeta)
    conjuntos = extraccion.leer_conjuntos(cfg.lista_v, cfg.lista_v2)
    mz = fijados.macrozona_region(cfg.ap_codigo)
    extra = sorted(set(meses["codigo"]) - set(catalogo_dmc["codigo"]))
    infos = extraccion.info_estaciones(catalogo_dmc, catalogo_pixeles, enlaces, medias_sp, conjuntos, mz, U,
                                       codigos_extra=extra)
    infos, fabrica = orquestacion.entradas_desde_extraccion(carpeta, catalogo_dmc, infos, U)

    # Fases 4 a 10 (orquestacion.evaluar_red; la política se arma en salidas con las huellas reales, ORQ-9).
    c.fase = FASE_ESTADOS
    resultado = orquestacion.evaluar_red(fabrica, serie, calendario, U,
                                         orquestacion.OpcionesCorrida(lineas_activas=cfg.lineas_activas),
                                         avance=consola)
    copias = _archivos_regulares(cfg.copias_c2)
    resultado.controles["A1"] = a1
    resultado.controles["A2"] = red.a2(calendario.sha256_anexo_a, calendario.sha256_anexo_a2,
                                       calendario.sha256_anexo_a3)          # Anexo A3: Enmienda 3, E3-2
    resultado.controles["G-dup"] = red.g_dup(copias, calendario, zs_de={k: i.zs for k, i in infos.items()})
    # Las desviaciones automáticas (SAL-21 y SAL-22, también «lineas_sin_cv» de ORQ-3f) las agrega salidas.informe.
    desviaciones: list[str] = []
    huellas = _huellas_entrada(c, U, calendario, estado, sha_catalogo, ctl_era5, meses, fijados.SHA_ADAPTADOR)
    huellas["corrida"]["intento"] = c.reanuda["intento"] if c.reanuda else c.intento
    huellas_politica = mod_politica.HuellasPolitica(
        protocolo_sha256=c.addendum["texto_v1_1"]["sha256"], commit_ap=_commit_ap(rutas.ap),
        configuracion_sha256=U.sha256_json, informe_sha256=salidas.SHA_INFORME_PROVISIONAL,
        artefactos_evaluados_sha256=salidas.SHA_INFORME_PROVISIONAL, adaptador_sha256=fijados.SHA_ADAPTADOR,
        python=platform.python_version(), tzdata=mod_tablas.version_de_base(),
        transiciones_sha256=calendario.sha256_anexo_a)

    # Fase 10 (§7.3, la última lectura de la DMC) y fase 11 (sello), en el orden de «Ola 4a cerrada».
    c.fase = FASE_POLITICA
    verificar = None
    if resultado.consecuencias.a5_alto:
        lectura.cerrar()
    else:
        preflight = fijados.cargar_preflight(cfg.ap_codigo)
        verificador = orquestacion.verificador_7_3(resultado, carpeta, rutas.dmc, adaptador=adaptador,
                                                   preflight=preflight,
                                                   dmc_features=sys.modules[fijados.MODULO_DMC_FEATURES],
                                                   tablas=calendario)

        def verificar(ruta: Path):
            fallas, no_normalizables = verificador(ruta)
            lectura.cerrar()
            return fallas, no_normalizables

    resumen = salidas.escribir_corrida(
        resultado, carpeta, artefactos=extraccion.leer_artefactos_evaluados(carpeta), huellas_entrada=huellas,
        huellas_politica=huellas_politica, desviaciones=desviaciones,
        leer_extracto=lambda codigo: extraccion.leer_extracto(carpeta, codigo), semilla=int(U.f("SEMILLA")),
        n_control=int(constantes.valor("EXPEDIENTES_CONTROL_N")), verificar=verificar, meses=meses,
        modo_sintetico=False, errata_post_c4=c.errata is not None)
    c.fase = FASE_SELLO
    if not lectura.cerrada:          # no debería pasar: verificar corre siempre que hay política
        raise ErrorC2("la lectura de la DMC no se cerró antes del sello")
    consola(FASE_SELLO, 1, 1)
    return resumen


def _commit_ap(ap: Path) -> str:
    r = _git(ap, "rev-parse", "HEAD")
    commit = r.stdout.decode("ascii", errors="replace").strip()
    if r.returncode != 0 or not _COMMIT.fullmatch(commit):
        raise RuntimeError("no se pudo leer el commit de AP")
    return commit


def _rechazar(c: _Corrida, motivos: Sequence[str]) -> int:
    """Registra el rechazo (si el cerrojo falla, sólo avisa su tipo) y avisa cada motivo; SALIDA_RECHAZO."""
    c.registrar_o_avisar("rechazo", motivos=[salidas.redactar(m) for m in motivos])
    for m in motivos:
        _aviso(f"C4 rechazado: {m}")
    return SALIDA_RECHAZO


def _abortada(c: _Corrida, e: BaseException) -> int:
    """VER-11: una corrida confirmatoria abortada. Sólo la fase y el tipo a la vista; nada se relanza con el error
    original encadenado (una interrupción se relanza sin contexto)."""
    retenido = _retener_error(c, e)
    visible = isinstance(e, ErrorC2)
    c.registrar_o_avisar("fin", resultado="abortada", etiqueta=c.etiqueta, fase=c.fase, error=type(e).__name__,
                         mensaje=salidas.redactar(str(e)) if visible else None, detalle_retenido=retenido)
    _aviso(f"corrida abortada en la fase {c.fase} ({type(e).__name__})"
           + (f": {e}" if visible else "; el detalle queda retenido en la carpeta hasta el sello"))
    if isinstance(e, KeyboardInterrupt):
        raise KeyboardInterrupt from None
    if isinstance(e, SystemExit):
        raise SystemExit(SALIDA_FALLA) from None
    return SALIDA_FALLA


def _registrar_fin_recuperado(c: _Corrida) -> int:
    """VER-16: la corrida que se reanuda ya selló su carpeta (el sello verifica) pero no pudo registrar su
    «fin»: se registra ahora, sin tocar la DMC ni la carpeta."""
    recibo = c.carpeta / salidas.RECIBO
    total = json.loads(recibo.read_bytes())["total_sha256"]
    ok = c.registrar_o_avisar("fin", resultado="sellada", etiqueta=c.etiqueta, total_sha256=total,
                              recibo_sha256=entorno.sha256_archivo(recibo), recuperado=True,
                              intento_corrida=c.reanuda.get("intento"))
    _aviso(f"la corrida {c.etiqueta} ya estaba sellada: se registra su fin (VER-16)")
    return SALIDA_OK if ok else SALIDA_FALLA


def modo_aplicar(args: argparse.Namespace) -> int:
    """C4: rechazos de §10, C2 con candado retenido, fases de §5.2 en orden, comprobaciones de §7.3 y sello.

    El intento se registra primero (con su número asignado bajo el flock del cerrojo); luego se toma el candado
    propio de --aplicar, que se retiene hasta el final (VER-16)."""
    cfg = _configuracion(args)
    rutas = cfg.rutas
    try:
        cerrojo = Cerrojo(rutas.corridas / CERROJO)
    except (ErrorCerrojo, OSError) as e:
        _aviso(f"C4 no corre: {e}")
        return SALIDA_RECHAZO
    fecha = cfg.reloj().astimezone(timezone.utc).date().isoformat()
    try:
        linea = cerrojo.registrar({"evento": "intento", "intento": None, "fecha_utc": fecha, "modo": "aplicar",
                                   "argumentos": _argumentos_por_alias(args, rutas),
                                   "huellas": _huellas_argumentos(args, rutas)})
    except (ErrorCerrojo, OSError, ValueError) as e:
        _aviso(f"C4 no corre: no se pudo registrar el intento en el cerrojo ({type(e).__name__}): {e}")
        return SALIDA_RECHAZO
    c = _Corrida(cfg=cfg, args=args, cerrojo=cerrojo, intento=int(linea["intento"]), fecha=fecha)
    ruta_candado = rutas.corridas / CANDADO_APLICAR
    with _CandadoAplicar(ruta_candado) as propio:
        if not propio.tomado:
            return _rechazar(c, [f"otro --aplicar está en curso: el candado {_alias(ruta_candado, rutas)} está tomado "
                                 "(VER-16)"])
        return _aplicar_con_candado(c)


def _aplicar_con_candado(c: _Corrida) -> int:
    cfg, args, rutas, cerrojo = c.cfg, c.args, c.cfg.rutas, c.cerrojo
    try:
        cerrojo.releer()            # lo que otro --aplicar alcanzó a registrar antes de soltar su candado
        motivos = _rechazos_sin_dmc(c)
        if motivos:
            return _rechazar(c, motivos)
        if c.solo_fin:
            return _registrar_fin_recuperado(c)
        c.enmienda4 = _enmienda4(args, rutas)
        if cfg.nice:
            os.nice(cfg.nice)
        with CandadoDMC(rutas.dmc / CANDADO_DMC) as candado:
            # 3. C2 con el candado tomado (VER-5): el candado antes que progreso.json y los manifiestos.
            motivos = [] if candado.estado == TOMADO else [f"no se pudo tomar el candado DMC/{CANDADO_DMC}: "
                                                           f"«{candado.estado}» (§3.1)"]
            estado = comprobar_c2(rutas.dmc, Path(args.linea_cierre), aph=rutas.aph, commit_c1=c.addendum["commit_c1"],
                                  copias_c2=cfg.copias_c2) if not motivos else None
            if estado is not None:
                motivos += list(estado.motivos)
            if not motivos and c.reanuda is not None and c.reanuda.get("entradas") != _entradas_confirmatorias(c, estado):
                motivos.append("--reanudar: las entradas cambiaron desde la corrida que se reanuda (VER-6)")
            if motivos:
                return _rechazar(c, motivos)
            # A2 antes de leer (§5.4).
            calendario = mod_tablas.cargar_tablas(verificar=False)
            a2 = red.a2(calendario.sha256_anexo_a, calendario.sha256_anexo_a2,
                        calendario.sha256_anexo_a3)                      # Anexo A3: Enmienda 3, E3-2
            if not a2.pasa:
                c.registrar_o_avisar("fin", resultado="detenida", control="A2", detalle=_a_json(a2.detalle))
                _aviso("A2 falla: la corrida no lee ningún artefacto (§5.4)")
                return SALIDA_FALLA
            U = mod_umbrales.cargar_umbrales(resolver_alias(c.addendum["configuracion"]["ruta"], rutas),
                                             resolver_alias(c.addendum["texto_v1_1"]["ruta"], rutas),
                                             sha256_json=c.addendum["configuracion"]["sha256"])
            # Corrida confirmatoria (VER-6): se registra antes de crear la carpeta.
            if c.errata_doc is not None and not cerrojo.errata_registrada(c.errata_doc["n"],
                                                                          c.errata_doc["documento"]["sha256"]):
                c.registrar("errata", **c.errata_doc)
            if c.reanuda is None:
                c.registrar("corrida_confirmatoria", etiqueta=c.etiqueta, errata=c.errata, reemplaza=c.reemplaza,
                            entradas=_entradas_confirmatorias(c, estado), enmienda4_punto12=c.enmienda4)
            else:
                c.registrar("reanudacion", etiqueta=c.etiqueta, enmienda4_punto12=c.enmienda4)
            c.confirmatoria = True
            try:
                resumen = _correr_confirmatoria(c, candado, estado, U, calendario)
            except BaseException as e:
                return _abortada(c, e)
            if "detenida" in resumen:
                c.registrar_o_avisar("fin", resultado="detenida", etiqueta=c.etiqueta, control=resumen["detenida"],
                                     detalle=resumen["detalle"])
                _aviso(f"{resumen['detenida']} falla: la corrida no lee ningún artefacto (§5.4); se retoma con --reanudar")
                return SALIDA_FALLA
            ok = c.registrar_o_avisar("fin", resultado="sellada", etiqueta=c.etiqueta,
                                      total_sha256=resumen["total_sha256"], recibo_sha256=resumen[salidas.RECIBO])
            _aviso(f"corrida sellada: {_alias(c.carpeta, rutas)} (total {_corto(resumen['total_sha256'])}…)"
                   + ("" if ok else "; su fin no quedó en el cerrojo: --reanudar lo registra (VER-16)"))
            return SALIDA_OK if ok else SALIDA_FALLA
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:
        if c.confirmatoria:         # VER-11: después de registrar la corrida, sólo la fase y el tipo
            _aviso(f"corrida abortada en la fase {c.fase} ({type(e).__name__})")
            return SALIDA_FALLA
        # Antes de la corrida confirmatoria no existe ningún veredicto todavía.
        c.registrar_o_avisar("fin", resultado="abortada", fase=c.fase, error=type(e).__name__,
                             mensaje=salidas.redactar(str(e)))
        _aviso(f"C4 abortado antes de la corrida confirmatoria ({type(e).__name__}): {e}")
        return SALIDA_FALLA


# =========================================================================================================
# Línea de comandos
# =========================================================================================================
def analizar_argumentos(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="verificar_reloj_dmc.py",
                                description="Procedimiento para confirmar el reloj de las horas DMC (§9).")
    modo = p.add_mutually_exclusive_group(required=True)
    modo.add_argument("--sintetico", action="store_true", help="C1: pruebas de §8 (y la batería con --bateria)")
    modo.add_argument("--control-era5", action="store_true", dest="control_era5", help="C3: controles con ERA5-Land")
    modo.add_argument("--aplicar", action="store_true", help="C4: la corrida confirmatoria única")
    p.add_argument("--bateria", action="store_true", help="con --sintetico: batería D, tiempo y §8.F")
    p.add_argument("--patron", default=PATRON_PRUEBAS, help="con --sintetico: archivos de pruebas (por omisión, todos)")
    p.add_argument("--salida", default=None, help="con --sintetico o --control-era5: carpeta de salida (fuera de los "
                                                   "repositorios)")
    p.add_argument("--addendum", default=None, help="addendum_c1.json (APH/auditoria/<fecha C1>/reloj_dmc/)")
    p.add_argument("--linea-cierre", default=None, dest="linea_cierre",
                   help="con --aplicar: cierre_descarga.json (APH/auditoria/<fecha C2>/reloj_dmc/)")
    p.add_argument("--reanudar", action="store_true", help="con --aplicar: retoma la corrida confirmatoria sin sellar")
    p.add_argument("--errata", default=None, help="con --aplicar: errata_<n>.json, sellada con testigo externo (§10)")
    p.add_argument("--enmienda4", default=None, help="con --aplicar: el punto 12 de la Enmienda 4, si está anclado")
    args = p.parse_args(argv)
    if args.bateria and not args.sintetico:
        p.error("--bateria va sólo con --sintetico")
    if args.patron != PATRON_PRUEBAS and not args.sintetico:
        p.error("--patron va sólo con --sintetico")
    if args.salida and args.aplicar:
        p.error("--aplicar escribe sólo en LOCAL/…/v1/ (§7.1): no admite --salida")
    if args.aplicar and (args.addendum is None or args.linea_cierre is None):
        p.error("--aplicar exige --addendum y --linea-cierre (E1-6)")
    if not args.aplicar and (args.linea_cierre or args.reanudar or args.errata or args.enmienda4):
        p.error("--linea-cierre, --reanudar, --errata y --enmienda4 van sólo con --aplicar")
    if args.sintetico and args.addendum:
        p.error("--addendum no va con --sintetico")
    if args.control_era5 and args.addendum is None:
        p.error("--control-era5 exige --addendum: C3 va después de C1 y usa sus umbrales (§10; VER-13)")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = analizar_argumentos(argv)
    if args.sintetico:
        return modo_sintetico(args)
    if args.control_era5:
        return modo_control_era5(args)
    return modo_aplicar(args)


if __name__ == "__main__":
    # VER-14: un solo ejemplar del módulo. Las pruebas que corre --sintetico importan
    # reloj_dmc.verificar_reloj_dmc; si el registro de accesos viviera en este __main__, serían dos registros
    # con dos ganchos que no se ven entre sí.
    from reloj_dmc import verificar_reloj_dmc as _paquete
    raise SystemExit(_paquete.main())
