"""Pruebas de ceguera.py (§0.4 y §1.9 del texto; S7 y S10).

Dueño: I4 (olas 1, 2 y 4). Las que llevan «sNN» son la prueba NN de §9 del texto. Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
Datos sólo sintéticos, en carpetas temporales. Ninguna prueba deja llegar un acceso a /Volumes (tampoco por
/System/Volumes/Data, CEG-21): allí sólo se prueba en bloqueo (el gancho niega antes del acceso) o con un espía de
os.lstat que niega antes de llamar al original. La red se
prueba con 127.0.0.1 dentro de ``SinRed``, que niega antes de conectar. Los textos con la ruta de la carpeta de
usuario y la arroba se arman en tiempo de ejecución (privacidad del paquete). Cada evasión que halló la revisión
independiente de la ola 1 (sondas ``sonda_vocabulario.py`` y ``sonda_registro.py``, hallazgos H1 a H9) es una prueba
negativa aquí.
Ola 2: la quinta clase, «documento» (D13; CEG-18), con un texto sintético cuya huella se pone en lugar de la vigente
(``mock.patch.object``) y, si está, con el texto vigente de APH, que es un documento y no un dato (como en
``test_constantes``); la clase que fija la ruta (D3, D13 y D14; CEG-19); y los enteros no negativos de D12 (CEG-11).
Ola 4: las clases de P42 y P43 que fija la ruta (D53; CEG-20) y los estáticos de C de las celdas (``z_e5l``, TIP-22)
en la lista de esquemas que sólo pasan como insumo; tras la revisión independiente, las carpetas ancladas al comienzo
del nombre relativo a la corrida (H5), las claves en minúsculas (H15), ``qc/no_normalizables.csv`` (H16) y el volumen
de datos de macOS (H6, CEG-21).
"""
import sys

sys.dont_write_bytecode = True

import contextlib  # noqa: E402
import glob  # noqa: E402
import gzip  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import socket  # noqa: E402
import struct  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from meteo_combinada import ceguera, constantes, tipos, umbrales  # noqa: E402
from meteo_combinada.ceguera import RegistroAccesos, SalidaProhibida  # noqa: E402
from reloj_dmc import verificar_reloj_dmc as V  # noqa: E402   (sólo para la paridad, antes de todo registro)

PROHIBIDA = "/Volumes/meteo_combinada_prueba_inexistente"
VOLUMEN_DE_DATOS = "/System/Volumes/Data"          # macOS: /System/Volumes/Data/x es /x (CEG-21)
USUARIO = "/" + "Users" + "/alguien/x.json"
ARROBA = "autor" + chr(64) + "dominio"
SHA = "156587f195f77009fe49bfa9497fd4a334d6b4bbe14064b46b8f3d3bca5e488a"
CLASES_VOCABULARIO = ("metrica", "resumen")
_APH = _RAIZ.parent.parent / "Air-Pollution-Health-Chile"
_VIGENTE = _APH / umbrales.TEXTO_VIGENTE
_ALIAS_VIGENTE = "APH/" + umbrales.TEXTO_VIGENTE
# Un texto sintético que cita el vocabulario de S7 y números en las formas del texto (CEG-18). Lleva la versión del
# texto vigente (hoy el v2.4), porque los documentos citan su ruta (``_ALIAS_VIGENTE``) y la versión es un número.
TEXTO_SINTETICO = (
    "# Producto sintético, texto v2.4\n"
    "§5.7: «el fondo ERA5-Land reescalado … las cotas de TF1 son 0,05/0,15 K, con ≥ 10 estaciones en 2000-2009».\n"
    "La corrección R_T no se resume y «sin DMC» no se estima. A 2.500 m; el 10⁻⁶ de A; «½·σ²»; ≈ 2,0·10¹¹ "
    "celda-horas; 1e-9 en S14; semilla 20261023.\n")
SHA_SINTETICO = hashlib.sha256(TEXTO_SINTETICO.encode("utf-8")).hexdigest()
FUENTE = "AP/scripts_modelo_1km/meteo_combinada/lecturas_sinteticas.py"
LECTURA = "CEG-40. Tope de 40 enlaces; con 15 m, QFE se mueve ≈ 1,4 hPa."


def _referencia(fuentes=None) -> "ceguera.ReferenciaDocumento":
    """Referencia del texto sintético, con su huella en lugar de la vigente."""
    with mock.patch.object(ceguera, "SHA_TEXTO_VIGENTE", SHA_SINTETICO):
        return ceguera.ReferenciaDocumento(TEXTO_SINTETICO, SHA_SINTETICO, fuentes=fuentes)


def _dato() -> str:
    """Un decimal que no está en ninguna fuente (ni en este archivo): se arma al correr."""
    return "0," + str(8317 * 3)


def _parquet(df: pd.DataFrame, metadatos: dict | None = None) -> bytes:
    tabla = pa.Table.from_pandas(df)
    if metadatos:
        tabla = tabla.replace_schema_metadata({**(tabla.schema.metadata or {}),
                                               **{k.encode(): v.encode() for k, v in metadatos.items()}})
    flujo = io.BytesIO()
    pq.write_table(tabla, flujo)
    return flujo.getvalue()


def _netcdf(nombre_variable: str, valores, formato: str = "NETCDF4", atributos=None, grupo=None) -> bytes:
    import netCDF4
    ds = netCDF4.Dataset("memoria.nc", "w", memory=1024, format=formato)
    ds.createDimension("x", len(valores))
    v = ds.createVariable(nombre_variable, "f4", ("x",))
    for k, valor in (atributos or {}).items():
        v.setncattr(k, valor)
    v[:] = np.asarray(valores, dtype="f4")
    if grupo:
        g = ds.createGroup(grupo)
        g.createDimension("y", 1)
        g.createVariable("S", "f4", ("y",))[:] = [0.7]
    return bytes(ds.close())


def _bajo_volumes(texto: str) -> bool:
    """/Volumes, también por el volumen de datos de macOS (CEG-21), en cualquier mayúscula."""
    return texto.casefold().startswith(("/volumes", VOLUMEN_DE_DATOS.casefold() + "/volumes"))


@contextlib.contextmanager
def _deja_os_como_estaba():
    """El registro del reloj, al salir, repone el ``os.stat`` y el ``os.lstat`` de cuando se importó, y con eso
    borraría los envoltorios de un registro exterior (el de la batería): se deja lo que había (CEG-22)."""
    antes = (os.stat, os.lstat)
    try:
        yield
    finally:
        os.stat, os.lstat = antes


def _espia_de_lstat(consultadas: list):
    real = os.lstat

    def espia(ruta, *a, **k):
        texto = os.fsdecode(os.fspath(ruta))
        consultadas.append(texto)
        if _bajo_volumes(texto):
            raise AssertionError(f"se consultó {texto}")
        return real(ruta, *a, **k)
    return espia


class PruebasS7(unittest.TestCase):
    """D3 del autor (MC-02): la guarda del vocabulario por clase de salida."""

    def test_s07_vocabulario_prohibido_en_metricas_y_resumenes(self):
        """«fondo», «era5l», «sin_dmc», «correccion» y «R_», y los nombres propios del fondo y del residuo, se rechazan
        en métricas y resúmenes: en el nombre, las columnas, las claves y todo valor de texto, también con espacios
        (H1), en el CSV, el parquet (también sus metadatos, H5) y el NetCDF (atributos y grupos, H5)."""
        limpia = pd.DataFrame({"uso": ["ambiental"], "candidato": ["AB"], "variable": ["T"], "S": [0.8]})
        malos = {
            "columna": ("validacion/puntajes.parquet", pd.DataFrame({"rmse_fondo": [1.0]})),
            "columna_era5": ("validacion/puntajes.parquet", pd.DataFrame({"S_ERA5-Land": [1.0]})),
            "rotulo": ("validacion/puntajes.parquet", pd.DataFrame({"candidato": ["sin_dmc"], "S": [1.0]})),
            "clave": ("decision.json", {"uso": {"S_era5l": 1.2}}),
            "valor": ("decision.json", {"ganador": "correccion_B"}),
            "R_": ("tendencias/resumen_tf.parquet", pd.DataFrame({"R_T": [0.1]})),
            "R_dentro": ("decision.json", {"mse_R_p": 0.1}),
            "texto": ("consola.txt", "la Corrección media fue 0,3 K"),
            "texto_sin_dmc": ("consola.txt", "S con y sin DMC"),
            "texto_era5": ("notas.md", "ERA5 Land da 1,2 K"),      # informe.md es documento (CEG-20)
            "csv": ("validacion/x.csv", b"uso,R_T\nagudo,0.1\n"),
            "csv_celda": ("validacion/x.csv", b"sujeto,rmse\nfondo ERA5-Land,1.4\n"),
            "json_bytes": ("resumen_qc.json", json.dumps({"fondo": 1}).encode()),
            "jsonl": ("x.jsonl", b'{"a": 1}\n{"fondo_T": 2}\n'),
            "gzip": ("decision.json.gz", gzip.compress(json.dumps({"era5l": 1}).encode())),
            "parquet": ("validacion/x.parquet", _parquet(pd.DataFrame({"fondo_T": [1.0]}))),
            "netcdf": ("validacion/x.nc", _netcdf("era5l_T", [1.0])),
            "nombre": ("validacion/fondo_puntajes.parquet", limpia),
            "carpeta": ("ERA5L/validacion/puntajes.parquet", limpia),
            "binario": ("validacion/x.bin", b"\xff\xfe\x00\x01"),
            # H1: textos con espacios y privacidad en todos los textos.
            "H1_valor_con_espacios": ("validacion/x.json", {"candidato": "fondo ERA5-Land", "S": 1.2}),
            "H1_sin_dmc": ("validacion/x.json", {"variante": "sin DMC", "rmse": 0.9}),
            "H1_R_T_medio": ("decision.json", {"sujeto": "R_T medio", "media": 0.4}),
            "H1_celda_con_espacios": ("validacion/x.parquet", pd.DataFrame({"sujeto": ["fondo ERA5-Land"],
                                                                            "rmse": [1.4]})),
            "H1_privacidad": ("decision.json", {"nota": "ver " + USUARIO}),
            "H1_arroba": ("decision.json", {"nota": "aviso a " + ARROBA}),
            # H2: una ruta por alias no es procedencia en una métrica.
            "H2_celda_ruta": ("validacion/x.parquet", pd.DataFrame({"sujeto": ["ERA5L/t2m"], "rmse": [1.4]})),
            "H2_clave_ruta_texto": ("decision.json", {"ERA5L/rmse_fondo_T": "1.234"}),
            "H2_clave_ruta_entero": ("decision.json", {"ERA5L/rmse_fondo_T_x1000": 1234}),
            "H2_columna_ruta": ("validacion/x.parquet", pd.DataFrame({"ERA5L/x": [1.0]})),
            "H2_decimal_en_huellas": ("decision.json", {"huellas": {"ERA5L/mensual/x.nc": 1.5}}),
            "H2_otra_clave_en_huellas": ("decision.json", {"huellas": {"ERA5L/mensual/x.nc": {"sha256": SHA,
                                                                                                "rmse": 1.37}}}),
            "H2_ruta_relativa_en_huellas": ("decision.json", {"huellas": {"mensual/x.nc": SHA}}),
            "H2_huella_mal_formada": ("decision.json", {"huellas": {"ERA5L/mensual/x.nc": "1.37"}}),
            "H2_ruta_en_la_consola": ("consola.txt", "leído ERA5L/mensual/era5land_202401_chile_pixeles.nc"),
            # H3: dmc_R_* sólo como nombres listados, nunca con valores ni con otro sufijo.
            "H3_resumido": ("tendencias/resumen.json", {"media": {"dmc_R_T": 0.31}, "p95": {"dmc_R_T": 0.9}}),
            "H3_columna": ("validacion/medias.parquet", pd.DataFrame({"estadistico": ["media"], "dmc_R_T": [0.31]})),
            "H3_sufijo": ("decision.json", {"columnas_D": ["dmc_R_RMSE"]}),
            "H3_sesgo": ("decision.json", {"columnas_D": ["dmc_R_sesgo"]}),
            "H3_lista_sin_clave_de_columnas": ("decision.json", {"lista": ["dmc_R_T"]}),
            # H5: metadatos de parquet, atributos de variables y grupos de NetCDF.
            "H5_metadatos_parquet": ("validacion/x.parquet", _parquet(pd.DataFrame({"S": [1.0]}),
                                                                      {"rmse_fondo": "1.23"})),
            "H5_valor_de_metadato": ("validacion/x.parquet", _parquet(pd.DataFrame({"S": [1.0]}),
                                                                      {"nota": "rmse del fondo"})),
            "H5_atributo_netcdf": ("validacion/x.nc", _netcdf("S", [1.3], atributos={"long_name": "fondo"})),
            "H5_atributo_con_espacios": ("validacion/x.nc", _netcdf("S", [1.3], atributos={
                "sujeto": "rmse del fondo ERA5-Land"})),
            "H5_grupo_netcdf": ("validacion/x.nc", _netcdf("S", [1.3], grupo="era5l_fondo")),
            # H6: nombres propios del fondo y del residuo, y mayúsculas intercaladas.
            "H6_camel": ("validacion/x.json", {"rmseFondo": 1.1, "sesgoEra5l": 0.2}),
            "H6_T_F": ("validacion/x.json", {"rmse_T_F": 1.1}),
            "H6_fe": ("validacion/x.json", {"sesgo_fe_t2m": 0.3}),
            "H6_E5L": ("validacion/x.json", {"rmse_E5L": 0.8}),
            "H6_residuo": ("validacion/x.json", {"mediana_r_T": 0.1}),
            "H6_rt": ("validacion/x.json", {"sesgo": {"rt_Td": 0.1}}),
            "H6_rbar": ("validacion/x.json", {"rbar": 0.1}),
            "H6_amp_TF": ("validacion/x.json", {"amp_TF": 0.1}),
        }
        for clase in CLASES_VOCABULARIO:
            ceguera.vigilar_salida("validacion/puntajes.parquet", limpia, clase=clase)
            ceguera.vigilar_salida("consola.txt", "S de AB: 0,8 K; ganador A", clase=clase)
            ceguera.vigilar_salida("resumen_qc.json", {"nota": "sin estadísticas del residuo", "marcas": {"5": 3}},
                                   clase=clase)
            for caso, (nombre, contenido) in malos.items():
                with self.subTest(clase=clase, caso=caso), self.assertRaises(SalidaProhibida):
                    ceguera.vigilar_salida(nombre, contenido, clase=clase)

    def test_s07_esquemas_de_tipos(self):
        """Los esquemas de métricas y resúmenes de tipos pasan como métrica; los de insumo con nombres del fondo o
        del residuo (CEG-10) sólo pasan como insumo: los estáticos de las estaciones («sin_fondo»), la altitud de los
        píxeles (z_e5l), el fondo en las estaciones (T_F…), los residuos (r_T…), las climatologías de A (rbar), la
        tabla lateral D (fe_* y dmc_R_* con valores) y los estáticos de C de las celdas (z_e5l, TIP-22), que se toman
        de ``tipos.ESQUEMA_ESTATICAS_CELDA_C`` mientras no estén en ``tipos.ESQUEMAS``."""
        celda_c = tipos.ESQUEMA_ESTATICAS_CELDA_C
        esquemas = dict(tipos.ESQUEMAS)
        esquemas.setdefault(celda_c.nombre, celda_c)       # cuando el coordinador la pase a ESQUEMAS, ya estará
        self.assertEqual(dict(esquemas[celda_c.nombre]), dict(celda_c))
        fallan = []
        for esquema in esquemas.values():
            tabla = tipos.tabla_vacia(esquema)
            ceguera.vigilar_salida(f"{esquema.nombre}.parquet", tabla, clase="insumo")
            try:
                ceguera.vigilar_salida(f"{esquema.nombre}.parquet", tabla, clase="metrica")
            except SalidaProhibida:
                fallan.append(esquema.nombre)
        self.assertEqual(sorted(fallan), sorted(["estaciones_mc", "ze5l", "puntos_e5l", "residuos", "clima_a",
                                                 "lateral_d", "estaticas_celda_c"]))
        # Sólo por «z_e5l»: sin ella (ESQUEMA_ESTATICAS_CELDA) pasa como métrica. Donde se escribe (TIP-22), en
        # estaticas/celdas.parquet, la ruta fija insumo (D14) y otra clase declarada se rechaza.
        tabla = tipos.tabla_vacia(celda_c)
        self.assertEqual(set(celda_c) - set(tipos.ESQUEMA_ESTATICAS_CELDA), {tipos.COLUMNA_Z_E5L})
        with self.assertRaises(SalidaProhibida) as e:
            ceguera.vigilar_salida("celdas.parquet", tabla, clase="metrica")
        self.assertIn("«E5L»", str(e.exception))
        ceguera.vigilar_salida("estaticas/celdas.parquet", tabla, clase="insumo")
        with self.assertRaises(SalidaProhibida):
            ceguera.vigilar_salida("estaticas/celdas.parquet", tabla, clase="metrica")

    def test_s07_huellas_dentro_de_un_resumen(self):
        """CEG-15: decision.json cita las entradas que usó sólo bajo «huellas», {ruta por alias: sha256} o
        {ruta por alias: {sha256, bytes}}."""
        decision = {"ganador": "A", "S": {"A": 0.8},
                    "huellas": {"ERA5L/mensual/era5land_202401_chile_pixeles.nc": {"sha256": SHA, "bytes": 123},
                                "APH/auditoria/x.md": SHA},
                    "huellas_m5": {"LOCAL/meteo_combinada/v1/x/decision.json": {"sha256": SHA}}}
        for clase in CLASES_VOCABULARIO:
            ceguera.vigilar_salida("decision.json", decision, clase=clase)
            ceguera.vigilar_salida("decision.json", json.dumps(decision).encode(), clase=clase)
            ceguera.vigilar_salida("consola.txt", f"escrito LOCAL/meteo_combinada/v1/m1/resumen_m1.json {SHA[:8]}…",
                                   clase=clase)

    def test_s07_exentos(self):
        """CEG-16 (H3): los cinco nombres de D, sólo listados bajo «columnas…» o «predictores…»; la tabla de RR06 pasa
        por su sujeto «lluvia_producto» (CEG-17), no por una exención: con «era5l» se rechaza."""
        self.assertEqual(ceguera.COLUMNAS_R_D, tipos.COLUMNAS_R_D)
        rr06 = pd.DataFrame({"sujeto": ["lluvia_producto"], "macrozona": ["centro"], "estacion_del_anio": ["DEF"],
                             "sesgo_total_mm": [0.1], "frecuencia_1mm": [0.2], "correlacion": [0.7]})
        for clase in CLASES_VOCABULARIO:
            ceguera.vigilar_salida("m6/decision_m6.json", {"columnas_D": list(tipos.COLUMNAS_R_D),
                                                           "predictores_D": ["fecha"] + list(tipos.COLUMNAS_R_D)},
                                   clase=clase)
            ceguera.vigilar_salida("qc/rr06_lluvia_producto.parquet", rr06, clase=clase)
            for malo in ({"dmc_R_T_media": 0.1}, {"columnas": ["dmc_R_T", "R_T"]}, {"dmc_R_": 1},
                         {"columnas_D": "dmc_R_T"}, pd.DataFrame({c: [0.0] for c in tipos.COLUMNAS_R_D}),
                         rr06.rename(columns={"sesgo_total_mm": "sesgo_era5l_mm"}),
                         rr06.assign(sujeto="lluvia de ERA5-Land")):
                with self.subTest(clase=clase, malo=str(malo)[:40]), self.assertRaises(SalidaProhibida):
                    ceguera.vigilar_salida("x.json", malo, clase=clase)

    def test_s07_insumo_permitido(self):
        """D3: un insumo pasa con cualquier sujeto."""
        insumo = pd.DataFrame({"h": np.array([0], dtype="int32"), "T_F": [1.0], "fondo_T": [1.0], "R_T": [0.0]})
        ceguera.vigilar_salida("insumos/puntos_estacion/330020.parquet", insumo, clase="insumo")
        ceguera.vigilar_salida("producto/residuos/330020.parquet", b"\xff\x00binario", clase="insumo")

    def test_s07_procedencia_esquema_cerrado(self):
        """CEG-11 (H4): sólo rutas, huellas, fechas, versiones e identificadores, y enteros bajo CLAVES_ENTERAS; ningún
        decimal, ningún texto que sea un número, ninguna tabla y nada privado."""
        buenas = {
            "huellas.json": {"ERA5L/mensual/era5land_202401_chile_pixeles.nc": {"sha256": SHA, "bytes": 123},
                             "fondo_en_estaciones": ["insumos/puntos_estacion/330020.parquet"], "procesos": 8,
                             "completa": True, "errata": None},
            "recibo_corrida.json": {"entorno": {"python": "3.11.16", "pandas": "2.3.3", "tzdata": "2026.3",
                                                "iana": "2026c", "interprete": "~/micromamba/envs/amb_v2/bin/python"},
                                    "commit": "4b50b0d027d7652843e34de3ea68c386b693be4e",
                                    "inicio_utc": "2026-10-26T06:00:00Z", "etiqueta": "HUMAN20261026_METEO_COMB_1"},
            "sha256.json": json.dumps({"insumos/clima_estado.parquet": SHA}).encode(),
            "SHA256SUMS": f"{SHA}  ERA5L/mensual/era5land_202401_chile_pixeles.nc\n{SHA} *era5land_202402.nc\n",
            "avance.jsonl": b'{"unidad": "fondo_estaciones/330020", "estado": "hecha", "filas": 12}\n',
            "recibo.json.gz": gzip.compress(json.dumps({"era5l": ["ERA5L/mensual/x.nc"]}).encode()),
        }
        for nombre, contenido in buenas.items():
            with self.subTest(buena=nombre):
                ceguera.vigilar_salida(nombre, contenido, clase="procedencia")
        malas = {
            # las cuatro evasiones de la sonda
            "H4_metrica_bajo_ruta": {"ERA5L/mensual/era5land_202401.nc": {"sha256": "ab" * 32,
                                                                          "rmse_frente_a_obs": 1.37}},
            "H4_decimal_bajo_ruta": {"ERA5L/mensual/era5land_202401.nc": 1.37},
            "H4_linea_con_numero": "rmse ERA5L/mensual/era5land_202401.nc 1,37\n",
            "H4_metrica_sin_vocabulario": {"metricas": {"T": {"A": 1.23, "B": 1.10}}},
            # y las demás formas
            "decimal_sin_vocabulario": {"duracion_s": 12.5},
            "entero_fuera_de_la_lista": {"n": 3},
            "decimal_bajo_clave_entera": {"filas": 1.0},
            "D12_entero_negativo": {"bytes": -1},
            "D12_entero_negativo_en_lista": {"filas": [3, -2]},
            "numero_como_texto": {"x": "1.37"},
            "decimal_en_un_identificador": {"x": "rmse_1.37"},
            "texto_libre": {"nota": "una nota con espacios"},
            "salida_de_unittest": "test_s05_fondo_exacto ... ok\nRan 300 tests in 12.345s\n",
            "tabla": pd.DataFrame({"a": [1]}),
            "csv": b"a,b\n1,2\n",
            "parquet": _parquet(pd.DataFrame({"a": ["x"]})),
            "usuario": {"ruta": USUARIO},
            "arroba": f"{SHA}  {ARROBA}\n",
            "no_finito": {"x": float("nan")},
        }
        for nombre, contenido in malas.items():
            with self.subTest(mala=nombre), self.assertRaises(SalidaProhibida):
                archivo = "x.csv" if nombre == "csv" else "recibo_corrida.json"
                ceguera.vigilar_salida(archivo, contenido, clase="procedencia")
        with self.assertRaises(ValueError):
            ceguera.vigilar_salida("x.json", {}, clase="otra")
        self.assertEqual(ceguera.CLASES_SALIDA, ("metrica", "resumen", "insumo", "procedencia", "documento"))
        self.assertEqual(ceguera.VOCABULARIO_PROHIBIDO, ("fondo", "era5l", "sin_dmc", "correccion", "R_"))

    def test_s07_vocabulario_en(self):
        """CEG-9 y CEG-10, texto por texto."""
        casos = {"fondo_T": "fondo", "rmse_fondos": "fondo", "correccion_a": "correccion", "Corrección": "correccion",
                 "era5land_t2m": "era5l", "ERA5-Land": "era5l", "ERA5 Land": "era5l", "ERA5L": "era5l",
                 "ERA5L/mensual/x.nc": "era5l", "sin_dmc": "sin_dmc", "sin DMC": "sin_dmc", "sinDMC": "sin_dmc",
                 "R_T": "R_", "mse_R_p": "R_", "dmc_R_T": "R_", "R_T medio": "R_", "rmseFondo": "fondo",
                 "sesgoEra5l": "era5l", "T_F": "T_F", "p_F": "T_F", "amp_TF": "amp_TF", "fe_t2m": "fe_",
                 "z_e5l": "E5L", "r_T": "r_", "rt_Td": "r_", "rbar": "rbar", "era5_blh": None, "T_menos_Td": None,
                 "lluvia_producto": None, "trasfondo": None, "residuo": None, "error_T": None, "td_final": None,
                 SHA: None}
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(ceguera.vocabulario_en(texto), esperado)

    def test_s07_guarda_del_residuo(self):
        """§0.4.6: los centinelas inyectados en la mediana y el MAD se encuentran en una salida como texto, float32 y
        float64 (los dos órdenes), en parquet, en NetCDF (también clásico, big-endian) y en gzip; una salida limpia no
        los trae."""
        g = ceguera.GuardaResiduo()
        mediana, mad = g.centinela("mediana"), g.centinela("mad")
        self.assertNotEqual(mediana, mad)
        self.assertEqual(g.centinela("mediana"), mediana)
        self.assertEqual(set(g.centinelas), {"mediana", "mad"})
        f32 = struct.unpack("<f", struct.pack("<f", mediana))[0]
        salidas = {
            "json": json.dumps({"x": mediana}).encode(),
            "texto6": f"mad = {mad:.6g}".encode(),
            "csv32": f"a\n{np.float32(mediana)}\n".encode(),
            "f8<": struct.pack("<d", mad), "f8>": struct.pack(">d", mad),
            "f4<": struct.pack("<f", mediana), "f4>": struct.pack(">f", mediana),
            "parquet32": _parquet(pd.DataFrame({"a": np.array([1.0, mediana], dtype="float32")})),
            "parquet64": _parquet(pd.DataFrame({"a": [1.0, mad]})),
            "parquet_de_float32": _parquet(pd.DataFrame({"a": [1.0, f32]})),
            "netcdf4": _netcdf("v", [1.0, mediana]),
            "netcdf3": _netcdf("v", [mediana, 2.0], "NETCDF3_CLASSIC"),
            "gzip": gzip.compress(json.dumps([mad]).encode()),
        }
        for nombre, datos in salidas.items():
            with self.subTest(salida=nombre):
                self.assertTrue(g.buscar(datos, nombre=nombre), nombre)
                with self.assertRaises(SalidaProhibida):
                    g.comprobar(datos, nombre=nombre)
        for contenido in (pd.DataFrame({"a": np.array([mediana], dtype="float32")}), {"mad": mad}, [1.0, mad],
                          np.array([mediana])):
            self.assertTrue(g.buscar(contenido))
        limpias = (json.dumps({"x": 91.5, "y": 1.0}).encode(), _parquet(pd.DataFrame({"a": [1.0, 2.0]})),
                   b"S = 0,8 K", pd.DataFrame({"a": [0.5]}))
        for limpia in limpias:
            self.assertEqual(g.buscar(limpia), [])
            g.comprobar(limpia)
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp)
            (carpeta / "sub").mkdir()
            (carpeta / "limpio.json").write_text("{}", encoding="utf-8")
            g.comprobar(carpeta)
            (carpeta / "sub" / "x.parquet").write_bytes(salidas["parquet64"])
            hallados = g.buscar_en(carpeta)
            self.assertTrue(hallados)
            self.assertEqual({h[0] for h in hallados}, {"sub/x.parquet"})
            with self.assertRaises(SalidaProhibida):
                g.comprobar(carpeta)
        for malo in (0.0, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                g.registrar("x", malo)


class PruebasS7Documento(unittest.TestCase):
    """D13 del autor [delegada]: la quinta clase, «documento» (CEG-18), y la clase que fija la ruta (D3, D13 y D14;
    CEG-19)."""

    def _md(self, *lineas: str) -> str:
        return "\n".join((f"# Addendum de M1 (sintético)\n\nTexto vigente: `{SHA_SINTETICO}`.", *lineas)) + "\n"

    def test_s07_documento_positivos(self):
        """Un documento cita el texto con el vocabulario de S7 y sus números (coma o punto decimal, miles con punto,
        «2,0·10¹¹», «10⁻⁶», «1e-9», «½»), las lecturas de una fuente, rutas, huellas, fechas, versiones, secciones e
        identificadores; en Markdown, JSON, bytes y gzip."""
        ref = _referencia({FUENTE: LECTURA})
        md = self._md(
            f"Texto: `{_ALIAS_VIGENTE}`, con su sha256 `{SHA_SINTETICO}`.",
            "- §5.7, «el fondo ERA5-Land reescalado … las cotas de TF1 son 0,05/0,15 K, con ≥ 10 estaciones en "
            "2000-2009». La corrección R_T no se resume; «sin DMC» no se estima.",
            "- CEG-40 (lectura de I4, `ceguera.py` en 4b50b0d): tope de 40 enlaces; con 15 m, ≈ 1,4 hPa.",
            "- Deriva: B pasa y AB falla (`LOCAL/meteo_combinada/v1/m1/deriva_s6.json`, sha256 " + SHA + ").",
            "- Recorte «mod23». Corrida HUMAN20261026_METEO_COMB_1, 2026-10-26T06:00:00Z, Python 3.11.16.",
            "", "| id | valor |", "|---|---|", "| A_TOL | 10⁻⁶ |", "| S_PAR | ½·σ² |", "| Z | 2.500 m |",
            "| CELDAS | 2,0·10¹¹ |", "| S14 | 1e-9 |", "| SEMILLA | 20261023 |")
        addendum = {
            "schema": "addendum_m1/1", "texto_sha256": SHA_SINTETICO,
            "lista_cerrada": {_ALIAS_VIGENTE: {"sha256": SHA_SINTETICO, "bytes": 123457},
                              "LOCAL/meteo_combinada/v1/m1/deriva_s6.json": SHA},
            "commit_m1": {"AP": "4b50b0d027d7652843e34de3ea68c386b693be4e"}, "recorte": "mod23",
            "deriva": {"B": "pasa", "AB": "falla"}, "entorno": {"python": "3.11", "tzdata": "2026.3"},
            "anexo_a2": [{"id": "TF1_COTAS", "valor": [0.05, 0.15], "seccion": "§5.7",
                          "fragmento": "las cotas de TF1 son 0,05/0,15 K"},
                         {"id": "TOL", "valor": 1e-06}, {"id": "MEDIO", "valor": 0.5}, {"id": "Z", "valor": 2500},
                         {"id": "CELDAS", "valor": 2.0e11}, {"id": "S14", "valor": 1e-9}, {"id": "N", "valor": 10}],
            "lecturas": [LECTURA], "completa": True, "errata": None}
        casos = {
            "APH/auditoria/20261026/meteo_combinada/m1/addendum_m1.md": md,
            "APH/auditoria/20261026/meteo_combinada/m1/addendum_m1.json": addendum,
            "addendum_m1.json": json.dumps(addendum, ensure_ascii=False).encode("utf-8"),
            "addendum_m1.md.gz": gzip.compress(md.encode("utf-8")),
            "anexo_a2.json": json.dumps(addendum["anexo_a2"] + [{"texto_sha256": SHA_SINTETICO}]),
            "informe.html": f"<p>Texto {SHA_SINTETICO}: «0,05/0,15 K», «2.500 m».</p>",
            "pruebas_m1.txt": f"{SHA_SINTETICO}\nRan 478 tests in 123.456s\n\nOK (skipped=114)\n",
            "otra_batería.txt": f"{SHA_SINTETICO}\nRan 1 test in 0.001s\nFAILED (failures=1, errors=2, skipped=3)\n",
        }
        for nombre, contenido in casos.items():
            with self.subTest(nombre=nombre):
                ceguera.vigilar_salida(nombre, contenido, clase="documento", referencia=ref)
        self.assertEqual(ref.fuentes, ((FUENTE, hashlib.sha256(LECTURA.encode("utf-8")).hexdigest()),))
        self.assertEqual(ref.sha256_texto, SHA_SINTETICO)

    def test_s07_documento_negativos(self):
        """Un documento con un número de datos se rechaza (suelto, pegado a una unidad, dentro de un nombre o de una
        ruta, en notación científica, con superíndice, en fracción, con cifras anchas, como número o clave de un
        JSON), y también uno sin la huella completa del texto, una tabla, un NetCDF, un binario o datos privados. El
        mensaje no repite el número."""
        ref = _referencia({FUENTE: LECTURA})
        md = self._md
        malos = {
            "decimal_con_coma": ("informe.md", md("S de AB: 0,83 K.")),
            "decimal_con_punto": ("informe.md", md("S de AB: 0.83 K.")),
            "entero_suelto": ("informe.md", md("Hay 137 estaciones evaluables.")),
            "pegado_a_la_unidad": ("informe.md", md("S de AB: 0,83K.")),
            "con_igual": ("informe.md", md("S=0.83")),
            "en_un_identificador": ("informe.md", md("rmse_0.83")),
            "en_una_ruta": ("informe.md", md("ver LOCAL/meteo_combinada/v1/m1/S_0.83.json")),
            "en_un_archivo": ("informe.md", md("ver S_0,83.json")),
            "potencia": ("informe.md", md("S = 8,3·10⁻¹")),
            "cientifica": ("informe.md", md("S = 8.3e-1")),
            "fraccion": ("informe.md", md("⅝ de las horas")),
            "seccion_inventada": ("informe.md", md("ver §0.83")),
            "cifras_anchas": ("informe.md", md("S = ０,８３")),
            "resumen_de_unittest_en_una_frase": ("pruebas_m1.txt", md("S = Ran 3 tests in 0.83s")),
            "resumen_de_unittest_con_cola": ("pruebas_m1.txt", md("OK (skipped=3) 0,83")),
            "version_corta_fuera_de_su_clave": ("addendum_m1.json", {"texto_sha256": SHA_SINTETICO,
                                                                     "nota": "2026.3"}),
            "json_decimal": ("addendum_m1.json", {"texto_sha256": SHA_SINTETICO, "S": 0.83}),
            "json_decimal_en_lista": ("addendum_m1.json", {"texto_sha256": SHA_SINTETICO, "valor": [0.05, 0.83]}),
            "json_entero": ("addendum_m1.json", {"texto_sha256": SHA_SINTETICO, "n_estaciones": 137}),
            "json_decimal_bajo_clave_entera": ("addendum_m1.json", {"texto_sha256": SHA_SINTETICO, "filas": 0.83}),
            "json_texto": ("addendum_m1.json", {"texto_sha256": SHA_SINTETICO, "nota": "S = 0,83 K"}),
            "json_clave": ("addendum_m1.json", {"texto_sha256": SHA_SINTETICO, "0.83": "S"}),
            "json_bytes": ("addendum_m1.json", json.dumps({"texto_sha256": SHA_SINTETICO, "S": 0.83}).encode()),
            "json_gzip": ("addendum_m1.json.gz", gzip.compress(json.dumps({"x": SHA_SINTETICO, "S": 0.83}).encode())),
            "json_no_finito": ("addendum_m1.json", {"texto_sha256": SHA_SINTETICO, "x": float("nan")}),
            "json_tipo": ("addendum_m1.json", {"texto_sha256": SHA_SINTETICO, "x": {1, 2}}),
            "sin_huella": ("informe.md", "# Informe\n§5.7: 0,05/0,15 K\n"),
            "huella_abreviada": ("informe.md", f"Texto {SHA_SINTETICO[:8]}…\n"),
            "huella_de_otro_texto": ("informe.md", f"Texto {SHA}\n"),
            "json_sin_huella": ("addendum_m1.json", {"lecturas": [LECTURA]}),
            "tabla": ("informe.md", pd.DataFrame({"texto": [SHA_SINTETICO]})),
            "csv": ("informe.csv", f"texto\n{SHA_SINTETICO}\n"),
            "parquet": ("informe.md", _parquet(pd.DataFrame({"texto": [SHA_SINTETICO]}))),
            "netcdf": ("informe.md", _netcdf("S", [0.05])),
            "binario": ("informe.md", b"\xff\xfe\x00\x01"),
            "usuario": ("informe.md", md("ver " + USUARIO)),
            "arroba": ("informe.md", md("aviso a " + ARROBA)),
            "json_usuario": ("addendum_m1.json", {"texto_sha256": SHA_SINTETICO, "ruta": USUARIO}),
            "nombre_privado": ("informe" + chr(64) + ".md", md("nada")),
        }
        for caso, (nombre, contenido) in malos.items():
            with self.subTest(caso=caso):
                with self.assertRaises(SalidaProhibida) as e:
                    ceguera.vigilar_salida(nombre, contenido, clase="documento", referencia=ref)
                for numero in ("0,83", "0.83", "137", "83"):
                    self.assertNotIn(numero, str(e.exception))
        ceguera.vigilar_salida("informe.md", md("Tope de 40 enlaces; ≈ 1,4 hPa."), clase="documento", referencia=ref)
        with self.assertRaises(SalidaProhibida):         # sin la fuente, «1,4» y «40» no salen del texto
            ceguera.vigilar_salida("informe.md", md("Tope de 40 enlaces; ≈ 1,4 hPa."), clase="documento",
                                   referencia=_referencia())

    def test_s07_documento_referencia(self):
        """La referencia exige el texto vigente con su huella y fuentes del paquete o de la auditoría del producto;
        sólo un documento la lleva, y un documento no se vigila sin ella."""
        with self.assertRaises(ValueError):                                     # no es el vigente
            ceguera.ReferenciaDocumento(TEXTO_SINTETICO, SHA_SINTETICO)
        with mock.patch.object(ceguera, "SHA_TEXTO_VIGENTE", SHA_SINTETICO):
            for texto, sha in ((TEXTO_SINTETICO + " ", SHA_SINTETICO), (TEXTO_SINTETICO, SHA_SINTETICO[:8]),
                               (TEXTO_SINTETICO, SHA_SINTETICO.upper()), (TEXTO_SINTETICO.encode(), SHA_SINTETICO)):
                with self.subTest(sha=sha[:8], tipo=type(texto).__name__), self.assertRaises(ValueError):
                    ceguera.ReferenciaDocumento(texto, sha)
            malas = ("LOCAL/meteo_combinada/v1/m1/resumen_m1.json", "DMC/2024/330020.html", "APH/docs/paper.qmd",
                     "AP/scripts_modelo_1km/v2/decision_v2.py", "meteo_combinada/ceguera.py",
                     "AP/scripts_modelo_1km/meteo_combinada/../v2/x.py", "AP/scripts_modelo_1km/meteo_combinada",
                     "APH/auditoria/meteo_combinada", "APH/auditoria/20261023/reloj_dmc/x.md",
                     "AP/scripts_modelo_1km/meteo_combinada/" + ARROBA + ".md")
            for ruta in malas:
                with self.subTest(fuente=ruta), self.assertRaises(ValueError):
                    ceguera.ReferenciaDocumento(TEXTO_SINTETICO, SHA_SINTETICO, fuentes={ruta: LECTURA})
            with self.assertRaises(ValueError):
                ceguera.ReferenciaDocumento(TEXTO_SINTETICO, SHA_SINTETICO, fuentes={FUENTE: b"\xff\xfe"})
            buenas = {"APH/auditoria/20261026/meteo_combinada/m1/decisiones_autor_m1_20261026.md": "D13",
                      "AP/scripts_modelo_1km/meteo_combinada/tests/test_x.py": LECTURA.encode("utf-8")}
            ref = ceguera.ReferenciaDocumento(TEXTO_SINTETICO, SHA_SINTETICO, fuentes=buenas)
        self.assertEqual([r for r, _ in ref.fuentes], sorted(buenas))
        with self.assertRaises(ValueError):
            ceguera.vigilar_salida("informe.md", self._md(), clase="documento")
        with self.assertRaises(ValueError):
            ceguera.vigilar_salida("informe.md", self._md(), clase="documento", referencia=SHA_SINTETICO)
        for clase in ("metrica", "resumen", "insumo", "procedencia"):
            with self.subTest(clase=clase), self.assertRaises(ValueError):
                ceguera.vigilar_salida("x.json", {}, clase=clase, referencia=ref)

    def test_s07_documento_pruebas_m1(self):
        """La salida de unittest (verbosidad 2: nombres, la primera línea de cada docstring, omitidas y resumen),
        con la huella del texto en su primera línea y este archivo como fuente, pasa como ``pruebas_m1.txt``; con un
        número de datos en una línea, o pegado al resumen, no."""

        class Mini(unittest.TestCase):
            def test_viento(self):
                """S11: DD 270 con 10 kt da u = +5,144 m/s."""

            @unittest.skip("por implementar (ola 3)")
            def test_pendiente(self):
                pass

            def test_con_subtest(self):
                with self.subTest(clase="metrica"):
                    pass

        flujo = io.StringIO()
        resultado = unittest.TextTestRunner(stream=flujo, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(Mini))
        self.assertTrue(resultado.wasSuccessful())
        ref = _referencia({"AP/scripts_modelo_1km/meteo_combinada/tests/test_ceguera.py":
                           Path(__file__).read_text(encoding="utf-8")})
        consola = ceguera.ConsolaDocumento(ref)
        salida = consola.encabezado() + "\n" + flujo.getvalue()
        self.assertIn("Ran 3 tests in ", salida)
        self.assertIn("OK (skipped=1)", salida)
        ceguera.vigilar_salida("LOCAL/meteo_combinada/v1/m1/pruebas_m1.txt", salida, clase="documento", referencia=ref)
        resumen = next(l for l in salida.splitlines() if l.startswith("Ran "))
        for mala in (salida + f"S de AB: {_dato()} K\n", salida.replace(resumen, f"{resumen} S = {_dato()}"),
                     flujo.getvalue()):
            with self.subTest(mala=mala[-40:]), self.assertRaises(SalidaProhibida):
                ceguera.vigilar_salida("pruebas_m1.txt", mala, clase="documento", referencia=ref)

    def test_s07_documento_consola(self):
        """La consola es un documento por líneas: el encabezado cita la huella y va primero; cada línea, sin números
        de datos ni datos privados, se devuelve tal cual."""
        ref = _referencia()
        with self.assertRaises(ValueError):
            ceguera.ConsolaDocumento(SHA_SINTETICO)
        consola = ceguera.ConsolaDocumento(ref)
        with self.assertRaises(SalidaProhibida):
            consola.linea("antes del encabezado")
        encabezado = consola.encabezado()
        self.assertIn(SHA_SINTETICO, encabezado)
        linea = "leído ERA5L/mensual/era5land_202401_chile_pixeles.nc; el fondo ERA5-Land, cotas 0,05/0,15 K"
        self.assertEqual(consola.linea(linea), linea)
        self.assertEqual(consola.linea("Ran 12 tests in 3.210s"), "Ran 12 tests in 3.210s")
        for mala in ("S de AB: 0,83 K", "ver " + USUARIO, "aviso a " + ARROBA, "137 estaciones", b"0,05"):
            with self.subTest(mala=str(mala)[:20]), self.assertRaises(SalidaProhibida):
                consola.linea(mala)
        ceguera.vigilar_salida("consola", f"{encabezado}\n{linea}\n", clase="documento", referencia=ref)

    def test_s07_documento_con_el_texto_vigente(self):
        """Con el texto vigente de APH: ``anexo_a2.json`` (de ``constantes.anexo_a2``) pasa con ``constantes.py``
        como fuente; un fragmento literal del texto pasa y, con un número que el texto no trae, no; las lecturas de
        este módulo pasan con ``ceguera.py`` como fuente."""
        self.assertEqual(ceguera.SHA_TEXTO_VIGENTE, umbrales.SHA_TEXTO_VIGENTE)
        if not _VIGENTE.is_file():
            self.skipTest(f"falta el texto vigente {_ALIAS_VIGENTE}: el documento no se puede comprobar contra él")
        texto = _VIGENTE.read_text(encoding="utf-8")
        if hashlib.sha256(texto.encode("utf-8")).hexdigest() != umbrales.SHA_TEXTO_VIGENTE:
            self.skipTest("el texto vigente de APH no tiene la huella anclada")
        with self.assertRaises(ValueError):
            ceguera.ReferenciaDocumento(texto + "\n", umbrales.SHA_TEXTO_VIGENTE)
        paquete = _RAIZ / "meteo_combinada"
        ref = ceguera.ReferenciaDocumento(texto, umbrales.SHA_TEXTO_VIGENTE, fuentes={
            "AP/scripts_modelo_1km/meteo_combinada/constantes.py": (paquete / "constantes.py").read_text(encoding="utf-8"),
            "AP/scripts_modelo_1km/meteo_combinada/ceguera.py": (paquete / "ceguera.py").read_text(encoding="utf-8")})
        a2 = constantes.anexo_a2(texto, umbrales.SHA_TEXTO_VIGENTE)
        ceguera.vigilar_salida("LOCAL/meteo_combinada/v1/m1/anexo_a2.json", a2, clase="documento", referencia=ref)
        ceguera.vigilar_salida("anexo_a2.json", json.dumps(a2, ensure_ascii=False).encode("utf-8"), clase="documento",
                               referencia=ref)
        solo_texto = ceguera.ReferenciaDocumento(texto, umbrales.SHA_TEXTO_VIGENTE)
        fragmento = next(l for l in texto.splitlines() if "Compuerta de deriva" in l and "0,3 K" in l)
        documento = f"Texto vigente {umbrales.SHA_TEXTO_VIGENTE}.\n\n> {fragmento}\n\nVer §0.4.3, §2.5 y §5.7.\n"
        ceguera.vigilar_salida("informe.md", documento, clase="documento", referencia=solo_texto)
        self.assertNotIn("8317", texto)
        with self.assertRaises(SalidaProhibida):
            ceguera.vigilar_salida("informe.md", documento + "TF2 de B: 0,8317 K\n", clase="documento",
                                   referencia=solo_texto)
        lecturas = f"# Lecturas de ceguera\n\nTexto vigente {umbrales.SHA_TEXTO_VIGENTE}.\n\n{ceguera.__doc__}"
        ceguera.vigilar_salida("addendum_m1.md", lecturas, clase="documento", referencia=ref)

    def test_s07_clase_fijada_por_la_ruta(self):
        """CEG-19: la clase de cada salida que nombran D3, D13 y D14, por archivo (sin «.gz», sin distinguir
        mayúsculas) o por la carpeta al comienzo del nombre (CEG-20); el archivo manda; métrica y resumen valen una
        por otra; otra clase declarada se rechaza; sin clase fijada rige la declarada."""
        casos = {
            "decision.json": "metrica", "LOCAL/meteo_combinada/v1/HUMAN20261026_METEO_COMB_1/decision.json": "metrica",
            "AP/config/meteorologia/meteo_combinada/v1/decision.json": "metrica", "decision.json.gz": "metrica",
            "Decision.JSON": "metrica", "qc/resumen_qc.json": "resumen", "m6/decision_m6.json": "resumen",
            "validacion/puntajes.parquet": "metrica", "tendencias/resumen_tf.parquet": "resumen",
            "insumos/puntos_estacion/330020.parquet": "insumo", "producto/residuos/330020.parquet": "insumo",
            "ambiental/lateral_d_pm25.parquet": "insumo", "estaticas/estaciones.parquet": "insumo",
            "qc/estaciones/330020.parquet": "insumo", "producto_01deg/202401.nc": "insumo",
            "salud/civil/2024.parquet": "insumo", "salud/s6/x.parquet": "insumo",
            "producto/clima_a.parquet": "insumo", "producto/tramos_homogeneos.parquet": "insumo",
            "avance.jsonl": "procedencia", "recibo_corrida.json": "procedencia", "sha256.json": "procedencia",
            "intentos_aplicar.jsonl": "procedencia", "m6/intentos_m6.jsonl": "procedencia",
            "validacion/sha256.json": "procedencia", "salud/validacion/x.parquet": "insumo",     # H5: CEG-20
            "LOCAL/meteo_combinada/v1/m1/anexo_a2.json": "documento", "pruebas_m1.txt": "documento",
            "APH/auditoria/20261026/meteo_combinada/m1/addendum_m1.json": "documento",
            "APH/auditoria/20261026/meteo_combinada/m1/addendum_m1.md": "documento",
        }
        for ruta, clase in casos.items():
            with self.subTest(ruta=ruta):
                self.assertEqual(ceguera.clase_de_ruta(ruta), clase)
        # Las de P42 y P43, que antes estaban aquí, tienen clase desde CEG-20 (PruebasS7ClasesP42).
        for ruta in ("consola.txt", "notas.md", "x.json", "clima_a.parquet", "tramos_homogeneos.parquet",
                     "estaticas", "qc/rr06_lluvia_producto.parquet", "producto/x.parquet", "",
                     "AP/scripts_modelo_1km/meteo_combinada/estaticas_nasadem.py"):
            with self.subTest(sin_clase=ruta):
                self.assertIsNone(ceguera.clase_de_ruta(ruta))
        ref = _referencia()
        documento = {"texto_sha256": SHA_SINTETICO}
        mal_declaradas = (("decision.json", {"ganador": "A"}, "insumo"),
                          ("estaticas/estaciones.parquet", pd.DataFrame({"z_s": [1.0]}), "metrica"),
                          ("avance.jsonl", b'{"unidad": "x", "estado": "hecha"}\n', "insumo"),
                          ("anexo_a2.json", documento, "resumen"),
                          ("pruebas_m1.txt", "Ran 3 tests in 0.1s", "procedencia"),
                          ("m6/decision_m6.json", {"ganador": "I"}, "insumo"),
                          ("qc/estaciones/330020.parquet", pd.DataFrame({"h": [0]}), "procedencia"))
        for nombre, contenido, clase in mal_declaradas:
            with self.subTest(nombre=nombre, clase=clase):
                with self.assertRaises(SalidaProhibida) as e:
                    ceguera.vigilar_salida(nombre, contenido, clase=clase)
                self.assertIn(f"«{ceguera.clase_de_ruta(nombre)}»", str(e.exception))
        with self.assertRaises(SalidaProhibida):
            ceguera.vigilar_salida("intentos_aplicar.jsonl", documento, clase="documento", referencia=ref)
        ceguera.vigilar_salida("m6/decision_m6.json", {"ganador": "I"}, clase="metrica")
        ceguera.vigilar_salida("validacion/x.parquet", pd.DataFrame({"S": [0.8]}), clase="resumen")
        ceguera.vigilar_salida("anexo_a2.json", documento, clase="documento", referencia=ref)
        ceguera.vigilar_salida("estaticas/estaciones.parquet", pd.DataFrame({"sin_fondo": [True]}), clase="insumo")
        ceguera.vigilar_salida("notas.md", {"S": 0.8}, clase="resumen")        # sin clase fijada: la declarada


class PruebasS7ClasesP42(unittest.TestCase):
    """D53 del autor (P42 y P43; A22): las clases que la ruta fija para las salidas que D3, D13 y D14 no nombraban
    (CEG-20)."""

    CORRIDA = "LOCAL/meteo_combinada/v1/HUMAN20261101_METEO_COMB_1"
    M1 = "LOCAL/meteo_combinada/v1/m1"

    def test_s07_clases_de_p42_y_p43(self):
        """CEG-20: cada ruta nueva da su clase (por el archivo, con o sin alias, sin «.gz» y sin distinguir
        mayúsculas); el archivo manda sobre la carpeta; ``m6/`` fija resumen salvo lo que fija su archivo o una
        carpeta fijada justo después; ``politicas/`` no fija clase, y la política fuera de ella tampoco la tiene;
        ``qc/no_normalizables.csv`` es resumen (H16)."""
        c, m1 = self.CORRIDA, self.M1
        casos = {
            # resumen (H16)
            "qc/no_normalizables.csv": "resumen", f"{c}/qc/no_normalizables.csv.gz": "resumen",
            "QC/No_Normalizables.CSV": "resumen",
            # resumen (P42)
            "resumen_m1.json": "resumen", f"{m1}/resumen_m1.json": "resumen", f"{m1}/resumen_m1.json.gz": "resumen",
            "costo_m1.json": "resumen", f"{m1}/costo_m1.json": "resumen", "COSTO_M1.Json": "resumen",
            "deriva_s6.json": "resumen", f"{m1}/deriva_s6.json": "resumen",
            "registro_m2a.json": "resumen", "LOCAL/meteo_combinada/v1/m2a/registro_m2a.json": "resumen",
            "registro_m34.json": "resumen", f"{c}/registro_m34.json": "resumen", "Registro_M34.JSON.GZ": "resumen",
            "m6/tf_contaminantes_pm25.json": "resumen", f"{c}/m6/tf_contaminantes_o3.json.gz": "resumen",
            "M6/TF_Contaminantes_NO2.json": "resumen",
            # resumen y documento (P43)
            "informe.json": "resumen", f"{c}/informe.json": "resumen", "informe.json.gz": "resumen",
            "informe.md": "documento", f"{c}/informe.md": "documento", "informe.md.gz": "documento",
            "Informe.MD": "documento",
            # insumo (P42), sólo con su carpeta
            "politicas/politicas_meteo_v1.json": "insumo", f"{c}/politicas/politicas_meteo_v1.json": "insumo",
            "Politicas/POLITICAS_METEO_V1.json.gz": "insumo",
            # la carpeta m6 (la lectura más estricta) y lo que fija su archivo o una carpeta justo después de «m6/»
            "m6/decision_m6.json": "resumen", f"{c}/m6/intentos_m6.jsonl": "procedencia",
            "m6/sha256.json": "procedencia", "m6/otro.json": "resumen", f"{c}/m6/registro.json": "resumen",
            "m6/muestra_tf.parquet": "resumen", "m6/tf_contaminantes_pm25.jsonl": "resumen",
            "m6/ambiental/lateral_d_pm25.parquet": "insumo", f"{c}/m6/ambiental/operador.json": "insumo",
            "m6/salud/s6/x.parquet": "insumo", "m6/otra/ambiental/x.parquet": "resumen",
            "m6/ambiental/tf_contaminantes_no2.json": "insumo", "m6/politicas/politicas_meteo_v1.json": "resumen",
            # el archivo sin «/» manda sobre la carpeta
            "validacion/informe.md": "documento", "insumos/resumen_m1.json": "resumen",
            "estaticas/costo_m1.json": "resumen", "producto/residuos/deriva_s6.json": "resumen",
            "m6/informe.md": "documento", "salud/registro_m2a.json": "resumen",
        }
        for ruta, clase in casos.items():
            with self.subTest(ruta=ruta):
                self.assertEqual(ceguera.clase_de_ruta(ruta), clase)
        for ruta in ("politicas_meteo_v1.json", "politicas/otra.json", "otra/politicas_meteo_v1.json",
                     f"{c}/politicas_meteo_v1.json", "tf_contaminantes_pm25.json", "otra/tf_contaminantes_pm25.json",
                     "m6", "informe.html", "informe.txt", "informe_m1.json", "resumen_m2a.json", f"{m1}/notas.md",
                     "LOCAL/meteo_combinada/v1/m2a/x.json", "registro_m5.json", "no_normalizables.csv",
                     "otra/qc/no_normalizables.csv", "qc/no_normalizables.parquet"):
            with self.subTest(sin_clase=ruta):
                self.assertIsNone(ceguera.clase_de_ruta(ruta))

    def test_s07_carpetas_ancladas_al_comienzo(self):
        """CEG-20 (H5): una carpeta fija la clase sólo al comienzo del nombre relativo a la corrida (o justo después
        de «m6/»); una subcarpeta de insumo dentro de ``validacion/`` o ``tendencias/`` no saca la salida de la guarda
        del vocabulario. El nombre relativo se toma también de una ruta por alias o absoluta con
        «meteo_combinada/v1/», y de la publicación. Las claves se comparan en minúsculas (H15)."""
        c = self.CORRIDA
        casos = {
            # H5: lo que señaló el revisor
            "validacion/ambiental/puntajes.parquet": "metrica", "tendencias/salud/tf.json": "resumen",
            "validacion/insumos/x.json": "metrica", "validacion/producto/residuos/x.parquet": "metrica",
            "tendencias/estaticas/x.parquet": "resumen", "validacion/m6/x.json": "metrica",
            # y un patrón de archivo con «/» dentro de otra carpeta toma la clase de ésa
            "validacion/producto/clima_a.parquet": "metrica", "validacion/politicas/politicas_meteo_v1.json": "metrica",
            "tendencias/qc/no_normalizables.csv": "resumen", "insumos/m6/tf_contaminantes_x.json": "insumo",
            # una subcarpeta más adentro no cambia la clase, tampoco la de un insumo
            "salud/validacion/x.parquet": "insumo", "insumos/m6/x.parquet": "insumo",
            "ambiental/m6/operador.json": "insumo", "estaticas/tendencias/x.json": "insumo",
            # «m6/» es el único prefijo admitido
            "m6/validacion/x.parquet": "metrica", "m6/insumos/x.parquet": "insumo",
            # el nombre relativo, desde una ruta por alias, absoluta o de la publicación
            f"{c}/validacion/ambiental/puntajes.parquet": "metrica",
            f"{c}_ERRATA1/salud/validacion/x.parquet": "insumo",
            "LOCAL/meteo_combinada/v1/validacion/puntajes.parquet": "metrica",
            "LOCAL/meteo_combinada/v1/m2a/estaticas/celdas.parquet": "insumo",
            "/datos/LOCAL/meteo_combinada/v1/HUMAN20261101_METEO_COMB_1/tendencias/salud/x.json": "resumen",
            "AP/config/meteorologia/meteo_combinada/v1/tendencias/resumen_tf.parquet": "resumen",
            "AP/config/meteorologia/meteo_combinada/v1/decision.json": "metrica",
            "local/METEO_COMBINADA/V1/HUMAN20261101_METEO_COMB_1/Validacion/x.parquet": "metrica",
        }
        for ruta, clase in casos.items():
            with self.subTest(ruta=ruta):
                self.assertEqual(ceguera.clase_de_ruta(ruta), clase)
        for ruta in ("otra/validacion/x.parquet", "x/insumos/y.json", "ERA5L/validacion/puntajes.parquet",
                     "/tmp/x/validacion/y.parquet", "LOCAL/meteo_combinada/v1/m2a/sub/estaticas/celdas.parquet",
                     f"{c}/otra/validacion/x.parquet", "LOCAL/meteo_combinada/v2/validacion/x.parquet",
                     "AP/config/meteorologia/reloj_dmc/v1/validacion/x.json"):
            with self.subTest(sin_clase=ruta):
                self.assertIsNone(ceguera.clase_de_ruta(ruta))
        # H5 en la guarda: una métrica en una subcarpeta de insumo no se puede declarar insumo.
        with self.assertRaises(SalidaProhibida) as e:
            ceguera.vigilar_salida("validacion/ambiental/puntajes.parquet", pd.DataFrame({"rmse_fondo": [1.0]}),
                                   clase="insumo")
        self.assertIn("«metrica»", str(e.exception))
        with self.assertRaises(SalidaProhibida):
            ceguera.vigilar_salida("tendencias/salud/tf.json", {"sujeto": "fondo ERA5-Land"}, clase="resumen")
        # H15: las claves de CLASE_DE_CARPETA (y de CLASE_DE_ARCHIVO) se comparan en minúsculas.
        with mock.patch.dict(ceguera.CLASE_DE_CARPETA, {"Carpeta_Mayus/Sub": "metrica"}):
            for ruta in ("carpeta_mayus/sub/x.json", "CARPETA_MAYUS/SUB/x.json", "m6/Carpeta_Mayus/Sub/x.json"):
                with self.subTest(mayusculas=ruta):
                    self.assertEqual(ceguera.clase_de_ruta(ruta), "metrica")
        with mock.patch.dict(ceguera.CLASE_DE_ARCHIVO, {"Otra/Salida_*.JSON": "resumen", "Suelta.TXT": "resumen"}):
            self.assertEqual(ceguera.clase_de_ruta("otra/salida_x.json"), "resumen")
            self.assertEqual(ceguera.clase_de_ruta("validacion/suelta.txt"), "resumen")

    def test_s07_recibos_archivados(self):
        """CEG-20 (PED-6 de I17; SLD-10): un recibo archivado es procedencia en la raíz de la corrida
        (``recibos/recibo_<n>.json``) y en la de M6 (``m6/recibos/…``), con o sin alias, sin «.gz» y sin distinguir
        mayúsculas; la carpeta ``recibos/`` no fija clase y ningún otro prefijo vale. Como procedencia pasa un recibo
        y no uno con un decimal, y otra clase declarada se rechaza."""
        c = self.CORRIDA
        casos = {
            "recibos/recibo_1.json": "procedencia", f"{c}/recibos/recibo_12.json": "procedencia",
            "m6/recibos/recibo_1.json": "procedencia", f"{c}/m6/recibos/recibo_2.json.gz": "procedencia",
            "RECIBOS/Recibo_3.JSON": "procedencia", "M6/Recibos/RECIBO_4.json": "procedencia",
            "recibos/recibo_corrida.json": "procedencia",          # también calza con recibo_corrida.json
            # un recibo archivado fuera de su lugar toma la clase de la carpeta (CEG-20)
            "validacion/recibos/recibo_1.json": "metrica", "m6/otra/recibos/recibo_1.json": "resumen",
            "m6/ambiental/recibos/recibo_1.json": "insumo", "m6/recibos/otro.json": "resumen",
        }
        for ruta, clase in casos.items():
            with self.subTest(ruta=ruta):
                self.assertEqual(ceguera.clase_de_ruta(ruta), clase)
        for ruta in ("recibos/otro.json", "recibos/recibo_1.parquet", "recibo_1.json", "otra/recibos/recibo_1.json",
                     "recibos/sub/recibo_1.json", f"{c}/otra/recibos/recibo_1.json"):
            with self.subTest(sin_clase=ruta):
                self.assertIsNone(ceguera.clase_de_ruta(ruta))
        for patron in ("recibos/recibo_*.json", "m6/recibos/recibo_*.json"):
            self.assertEqual(ceguera.CLASE_DE_ARCHIVO[patron], "procedencia")
            partes = ceguera._partes_de_salida(patron.replace("*", "7"))
            self.assertEqual([q for q in ceguera.CLASE_DE_ARCHIVO if ceguera._calza(partes, q)], [patron])
        recibo = {"esquema": "meteo-combinada-recibo/1", "commit": "4b50b0d027d7652843e34de3ea68c386b693be4e",
                  "inicio_utc": "2026-10-26T06:00:00Z", "procesos": 8, "completa": True,
                  "huellas": {f"{c}/sha256.json": {"sha256": SHA, "bytes": 123},
                              f"{c}/recibos/recibo_1.json": SHA}}
        ref = _referencia()
        for nombre in ("recibos/recibo_2.json", "m6/recibos/recibo_1.json", f"{c}/m6/recibos/recibo_1.json"):
            with self.subTest(nombre=nombre):
                ceguera.vigilar_salida(nombre, recibo, clase="procedencia")
                ceguera.vigilar_salida(nombre, json.dumps(recibo).encode("utf-8"), clase="procedencia")
                ceguera.vigilar_salida(nombre + ".gz", gzip.compress(json.dumps(recibo).encode("utf-8")),
                                       clase="procedencia")
                with self.assertRaises(SalidaProhibida):
                    ceguera.vigilar_salida(nombre, {**recibo, "duracion_s": 12.5}, clase="procedencia")
                for clase, contenido, kw in (("resumen", recibo, {}), ("metrica", recibo, {}), ("insumo", recibo, {}),
                                             ("documento", {"texto_sha256": SHA_SINTETICO}, {"referencia": ref})):
                    with self.assertRaises(SalidaProhibida) as e:
                        ceguera.vigilar_salida(nombre, contenido, clase=clase, **kw)
                    self.assertIn("«procedencia»", str(e.exception))

    def test_s07_patrones_sin_choques(self):
        """CEG-20: ningún nombre calza con dos patrones de archivo (el orden de búsqueda no cambia la clase); un patrón
        sin «/» manda dentro de toda carpeta fijada, y uno con «/» sólo calza con el nombre entero (dentro de otra
        carpeta rige ésa); entre dos carpetas manda la del comienzo, salvo «m6/»; y si dos patrones de clases
        distintas calzaran, ``clase_de_ruta`` lanza ValueError en vez de elegir uno."""
        archivo, carpeta = ceguera.CLASE_DE_ARCHIVO, ceguera.CLASE_DE_CARPETA
        for patron, clase in archivo.items():
            instancia = patron.replace("*", "pm25")
            with self.subTest(patron=patron):
                partes = ceguera._partes_de_salida(instancia)
                self.assertEqual([q for q in archivo if ceguera._calza(partes, q)], [patron])
                self.assertEqual(ceguera.clase_de_ruta(instancia), clase)
                self.assertEqual(ceguera.clase_de_ruta(f"{self.CORRIDA}/{instancia}"), clase)
                for c, clase_c in carpeta.items():
                    # dentro de otra carpeta, a lo más otro patrón calza con el nombre entero (m6/recibos/…)
                    compuesto = ceguera._partes_de_salida(f"{c}/{instancia}")
                    propios = [q for q in archivo if ceguera._calza(compuesto, q)]
                    self.assertLessEqual(len(propios), 1, c)
                    esperada = archivo[propios[0]] if propios else (clase if "/" not in patron else clase_c)
                    self.assertEqual(ceguera.clase_de_ruta(f"{self.CORRIDA}/{c}/{instancia}"), esperada, c)
        for c, clase in carpeta.items():
            with self.subTest(carpeta=c):
                self.assertEqual(ceguera.clase_de_ruta(f"{self.CORRIDA}/{c}/otro.json"), clase)
                self.assertIsNone(ceguera.clase_de_ruta(f"otra/{c}/otro.json"))
                for otra, clase_otra in carpeta.items():
                    esperada = clase_otra if c == "m6" else clase
                    self.assertEqual(ceguera.clase_de_ruta(f"{c}/{otra}/otro.json"), esperada, otra)
                    self.assertEqual(ceguera.clase_de_ruta(f"m6/{c}/{otra}/otro.json"), clase, otra)
        with mock.patch.dict(ceguera.CLASE_DE_ARCHIVO, {"resumen_*.json": "resumen"}):
            self.assertEqual(ceguera.clase_de_ruta("resumen_m1.json"), "resumen")       # calzan dos, de la misma
        with mock.patch.dict(ceguera.CLASE_DE_ARCHIVO, {"resumen_*.json": "insumo"}):
            with self.assertRaises(ValueError):
                ceguera.clase_de_ruta("resumen_m1.json")
            with self.assertRaises(ValueError):
                ceguera.vigilar_salida("resumen_m1.json", {"S": 0.8}, clase="resumen")
        self.assertNotIn("resumen_*.json", ceguera.CLASE_DE_ARCHIVO)

    def test_s07_vigilar_con_las_clases_de_p42_y_p43(self):
        """Con las clases de CEG-20, ``vigilar_salida`` acepta un resumen válido de cada ruta nueva (como resumen o
        como métrica, que aplican la misma regla; en memoria, en bytes y en gzip) y lo rechaza con el vocabulario
        prohibido como sujeto; la política pasa como insumo con cualquier contenido; el informe pasa como documento
        con la referencia y no con un número de datos; ``qc/no_normalizables.csv`` pasa como resumen sin el
        vocabulario (H16); y cada ruta rechaza otra clase declarada, aunque el contenido valga para ésa."""
        c, m1 = self.CORRIDA, self.M1
        validos = {
            f"{m1}/resumen_m1.json": {"pruebas": {"s05": "pasa", "s06": "pasa", "s07": "pasa"}, "omitidas": 0,
                                      "huellas": {f"{m1}/pruebas_m1.txt": SHA}},
            f"{m1}/costo_m1.json": {"m34_h": 18.5, "m5_h": 9.0, "carga": 1.4, "procesos": 8, "recorte": "mod23"},
            f"{m1}/deriva_s6.json": {"deriva_k_decada": 0.3, "compuerta": {"B": "falla", "AB": "pasa"},
                                     "tf2": {"B": {"media": 0.12, "p95": 0.31}, "AB": {"media": 0.05, "p95": 0.12}}},
            "LOCAL/meteo_combinada/v1/m2a/registro_m2a.json": {
                "estaciones": 40, "celdas_pobladas": 100,
                "huellas": {"ERA5L/mensual/era5land_202401_chile_pixeles.nc": {"sha256": SHA, "bytes": 123}}},
            f"{c}/registro_m34.json": {"red_v2": "registrada", "pliegues": 5,
                                       "huellas_m2a": {"LOCAL/meteo_combinada/v1/m2a/registro_m2a.json": SHA}},
            f"{c}/m6/tf_contaminantes_pm25.json": {"contaminante": "pm25", "I": "pasa", "D": "falla",
                                                   "lotes_de_meses": 1},
            f"{c}/informe.json": {"area_de_aplicabilidad": {"ambiental": {
                "candidato": "C", "fraccion_poblacion_fuera_de_rango": 0.042}}},      # P43: la fracción de §4.6
        }
        malos = {       # el vocabulario de S7 (y los nombres propios de CEG-10) como sujeto, o en una clave
            "fondo": {"sujeto": "fondo ERA5-Land", "rmse": 1.4},
            "era5l": {"sujeto": "era5land_t2m", "sesgo": 0.2},
            "sin_dmc": {"candidato": "AB sin DMC", "S": 0.9},
            "correccion": {"sujeto": "corrección de A", "p95": 0.3},
            "R_": {"sujeto": "R_T", "media": 0.1},
            "T_F": {"sujeto": "T_F", "sesgo": 0.2},
            "E5L": {"sujeto": "z_e5l", "media": 1.0},
            "clave": {"rmse_fondo": 1.1},
        }
        ref = _referencia()
        documento = {"texto_sha256": SHA_SINTETICO}
        procedencia = {"filas": 3}
        for nombre, valido in validos.items():
            self.assertEqual(ceguera.clase_de_ruta(nombre), "resumen")
            for clase in CLASES_VOCABULARIO:
                with self.subTest(nombre=nombre, clase=clase):
                    ceguera.vigilar_salida(nombre, valido, clase=clase)
                    ceguera.vigilar_salida(nombre, json.dumps(valido).encode("utf-8"), clase=clase)
                    ceguera.vigilar_salida(nombre + ".gz", gzip.compress(json.dumps(valido).encode("utf-8")),
                                           clase=clase)
                for caso, malo in malos.items():
                    for contenido in ({**valido, **malo}, json.dumps({**valido, **malo}).encode("utf-8")):
                        with self.subTest(nombre=nombre, clase=clase, caso=caso, tipo=type(contenido).__name__):
                            with self.assertRaises(SalidaProhibida):
                                ceguera.vigilar_salida(nombre, contenido, clase=clase)
            for clase, contenido, kw in (("insumo", valido, {}), ("procedencia", procedencia, {}),
                                         ("documento", documento, {"referencia": ref})):
                with self.subTest(nombre=nombre, mal_declarada=clase):
                    with self.assertRaises(SalidaProhibida) as e:
                        ceguera.vigilar_salida(nombre, contenido, clase=clase, **kw)
                    self.assertIn("«resumen»", str(e.exception))
        # La política es insumo: pasa sin mirar el contenido, y ninguna otra clase vale.
        politica = {"reglas": {"T": {"fondo_T": "marca 13", "R_T": 0.1}}, "nota": "sin DMC no se estima"}
        for nombre in ("politicas/politicas_meteo_v1.json", f"{c}/politicas/politicas_meteo_v1.json"):
            ceguera.vigilar_salida(nombre, politica, clase="insumo")
            ceguera.vigilar_salida(nombre, b"\xff\x00binario", clase="insumo")
            for clase, contenido, kw in (("resumen", {"S": 0.8}, {}), ("metrica", {"S": 0.8}, {}),
                                         ("procedencia", procedencia, {}),
                                         ("documento", documento, {"referencia": ref})):
                with self.subTest(nombre=nombre, mal_declarada=clase):
                    with self.assertRaises(SalidaProhibida) as e:
                        ceguera.vigilar_salida(nombre, contenido, clase=clase, **kw)
                    self.assertIn("«insumo»", str(e.exception))
        ceguera.vigilar_salida("politicas_meteo_v1.json", {"S": 0.8}, clase="resumen")    # sin su carpeta: la
        with self.assertRaises(SalidaProhibida):                                         # declarada
            ceguera.vigilar_salida("politicas_meteo_v1.json", politica, clase="resumen")
        # El informe es documento (P43): cita su resumen por la ruta y la huella, con el veredicto.
        informe = (f"# Informe (sintético)\n\nTexto vigente: `{SHA_SINTETICO}`.\n\n"
                   f"El área de aplicabilidad de C está en `{c}/informe.json` (sha256 {SHA}): «pasa». "
                   "El fondo ERA5-Land y la corrección R_T no se informan; «sin DMC» no se estima.\n")
        for nombre in ("informe.md", f"{c}/informe.md"):
            ceguera.vigilar_salida(nombre, informe, clase="documento", referencia=ref)
            ceguera.vigilar_salida(nombre + ".gz", gzip.compress(informe.encode("utf-8")), clase="documento",
                                   referencia=ref)
            with self.assertRaises(SalidaProhibida):
                ceguera.vigilar_salida(nombre, informe + f"Fracción: {_dato()}\n", clase="documento", referencia=ref)
            for clase, contenido in (("resumen", {"S": 0.8}), ("metrica", {"S": 0.8}), ("insumo", informe),
                                     ("procedencia", procedencia)):
                with self.subTest(nombre=nombre, mal_declarada=clase):
                    with self.assertRaises(SalidaProhibida) as e:
                        ceguera.vigilar_salida(nombre, contenido, clase=clase)
                    self.assertIn("«documento»", str(e.exception))
        # qc/no_normalizables.csv es resumen (H16): motivos y conteos por artefacto, sin valores.
        nn = tipos.tabla_vacia(tipos.ESQUEMA_NO_NORMALIZABLES)
        csv = ",".join(tipos.ESQUEMA_NO_NORMALIZABLES) + "\n7,330020,2024,1,centro,red_1,sin_observaciones,datos\n"
        for nombre in ("qc/no_normalizables.csv", f"{c}/qc/no_normalizables.csv"):
            for clase in CLASES_VOCABULARIO:
                with self.subTest(nombre=nombre, clase=clase):
                    ceguera.vigilar_salida(nombre, nn, clase=clase)
                    ceguera.vigilar_salida(nombre, csv.encode("utf-8"), clase=clase)
                    for malo in (csv.replace("sin_observaciones", "fondo_sin_datos"),
                                 csv.replace("origen", "origen_era5l")):
                        with self.assertRaises(SalidaProhibida):
                            ceguera.vigilar_salida(nombre, malo.encode("utf-8"), clase=clase)
            with self.subTest(nombre=nombre, mal_declarada="insumo"):
                with self.assertRaises(SalidaProhibida) as e:
                    ceguera.vigilar_salida(nombre, nn, clase="insumo")
                self.assertIn("«resumen»", str(e.exception))


class PruebasS10Ceguera(unittest.TestCase):
    """S10: nada se escribe ni se lee bajo lo vigilado, sin red y sin procesos vivos."""

    def _acciones_bajo_volumes(self):
        return (lambda: open(PROHIBIDA + "/x.json", "rb"), lambda: open(PROHIBIDA + "/y.json", "w"),
                lambda: os.stat(PROHIBIDA), lambda: os.lstat(PROHIBIDA + "/y"), lambda: os.listdir(PROHIBIDA),
                lambda: os.scandir(PROHIBIDA), lambda: Path(PROHIBIDA, "z").exists(),
                lambda: Path(PROHIBIDA).is_symlink(), lambda: os.access(PROHIBIDA, os.R_OK),
                lambda: os.mkdir(PROHIBIDA + "/d"), lambda: glob.glob(PROHIBIDA + "/*"),
                lambda: Path("/volumes/meteo_combinada_prueba_inexistente/x").exists())

    def test_s10_registro_bloquea_volumes(self):
        """En bloqueo, cada acceso bajo /Volumes falla ANTES de ocurrir (también en minúsculas); al salir se
        restituyen os.stat, os.lstat y os.access y el gancho queda inerte."""
        antes = (os.stat, os.lstat, os.access)
        acciones = self._acciones_bajo_volumes()
        with RegistroAccesos((PROHIBIDA,), bloquear=True) as r:
            for i, accion in enumerate(acciones):
                with self.subTest(accion=i), self.assertRaises(PermissionError):
                    accion()
            open(os.devnull, "rb").close()
            os.stat(os.devnull)
        self.assertEqual(len(r.accesos), len(acciones))
        self.assertTrue({"open", "os.stat", "os.lstat", "os.listdir", "os.scandir", "os.access", "os.mkdir",
                         "glob.glob"} <= {e for e, _ in r.accesos})
        self.assertEqual((r.por_enlace, r.negados_dentro, r.lecturas_permitidas), ([], [], []))
        self.assertEqual((os.stat, os.lstat, os.access), antes)
        with tempfile.TemporaryDirectory() as tmp:
            vigilada = Path(tmp).resolve()
            r2 = RegistroAccesos((vigilada,), bloquear=True)
            with r2:
                pass
            (vigilada / "despues.txt").write_text("x", encoding="utf-8")     # fuera del contexto: inerte
            self.assertEqual(r2.accesos, [])

    def test_s10_ruta_lexica_antes_de_resolver(self):
        """CEG-1: un enlace en una carpeta temporal que lleva a una vigilada se niega (``por_enlace``); uno que lleva
        bajo /Volumes se niega sin consultar /Volumes (un espía de os.lstat lo comprueba), y una ruta no vigilada bajo
        /Volumes no se recorre consultando."""
        consultadas = []
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp).resolve()
            vigilada, afuera = raiz / "vigilada", raiz / "afuera"
            vigilada.mkdir()
            afuera.mkdir()
            (vigilada / "dato.txt").write_text("x", encoding="utf-8")
            (afuera / "a_vigilada").symlink_to(vigilada)
            (afuera / "a_volumes").symlink_to(PROHIBIDA + "/dato.txt")
            (afuera / "relativo").symlink_to(Path("..") / "vigilada" / "dato.txt")
            with mock.patch.object(os, "lstat", _espia_de_lstat(consultadas)):
                with RegistroAccesos((vigilada, PROHIBIDA), bloquear=True) as r:
                    for accion in (lambda: open(afuera / "a_vigilada" / "dato.txt", "rb"),
                                   lambda: (afuera / "a_vigilada").stat(), lambda: open(afuera / "relativo"),
                                   lambda: open(afuera / "a_volumes", "rb"), lambda: os.stat(afuera / "a_volumes")):
                        with self.assertRaises(PermissionError):
                            accion()
                    os.lstat(afuera / "a_vigilada")       # lstat no sigue el último enlace: no es acceso
                    (afuera / "otro.txt").write_text("y", encoding="utf-8")
                # Bajo /Volumes y no vigilada: el recorrido sigue léxico y no la toca. Se mira el recorrido mismo y no
                # se anuncia un acceso, que para un registro exterior sobre /Volumes (la batería) sí lo sería (CEG-22).
                r3 = RegistroAccesos((vigilada,), bloquear=True)
                fuera = "/" + "Volumes/otro_inexistente_meteo_combinada/x"
                self.assertEqual(ceguera._recorrer(fuera, r3._vigiladas, seguir_final=True), (fuera, []))
            self.assertEqual(len(r.por_enlace), 5)
            self.assertTrue(all(o.casefold().startswith((str(vigilada).casefold(), PROHIBIDA.casefold()))
                                for _, _, o in r.por_enlace))
            self.assertEqual([e for e, _ in r.accesos], ["open", "os.stat", "open", "open", "os.stat"])
        self.assertEqual([c for c in consultadas if c.casefold().startswith("/volumes")], [])

    def test_s10_enlace_seguido_de_punto_punto(self):
        """H7 (CEG-1): «afuera/L/../secreto.txt», con L → VIGILADA/sub, llega a VIGILADA/secreto.txt (el sistema sigue
        el enlace antes del «..»): se niega y no se lee. Lo mismo con una ruta que pasa por la vigilada y vuelve
        («VIGILADA/sub/../../afuera/x») y con una que pasa por /Volumes y vuelve, sin consultar /Volumes."""
        consultadas = []
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp).resolve()
            vigilada, afuera = raiz / "VIGILADA", raiz / "afuera"
            (vigilada / "sub").mkdir(parents=True)
            (vigilada / "secreto.txt").write_text("dato vigilado", encoding="utf-8")
            afuera.mkdir()
            (afuera / "x.txt").write_text("libre", encoding="utf-8")
            (afuera / "L").symlink_to(vigilada / "sub")
            evasion = str(afuera / "L") + "/../secreto.txt"
            relativa = os.path.relpath(afuera / "L", Path.cwd()) + "/../secreto.txt"     # relpath no resuelve
            por_volumes = PROHIBIDA + "/../.." + str(afuera / "x.txt")
            with mock.patch.object(os, "lstat", _espia_de_lstat(consultadas)):
                with RegistroAccesos((vigilada, PROHIBIDA), bloquear=True) as r:
                    for accion in (lambda: open(evasion, encoding="utf-8").read(), lambda: os.stat(evasion),
                                   lambda: Path(evasion).exists(), lambda: open(relativa, encoding="utf-8"),
                                   lambda: open(str(vigilada / "sub") + "/../../afuera/x.txt"),
                                   lambda: open(por_volumes)):
                        with self.assertRaises(PermissionError):
                            accion()
                    self.assertEqual((afuera / "x.txt").read_text(encoding="utf-8"), "libre")
            self.assertEqual(len(r.accesos), 6)
            self.assertTrue(all(o.casefold().startswith((str(vigilada).casefold(), PROHIBIDA.casefold()))
                                for _, o in r.accesos))
        self.assertEqual([c for c in consultadas if c.casefold().startswith("/volumes")], [])

    def test_s10_construir_sin_consultar_volumes(self):
        """H8 (CEG-2): una vigilada o una permitida que es un enlace hacia /Volumes se guarda recorrida sin consultar
        /Volumes, y lo que hay detrás del enlace queda vigilado."""
        consultadas = []
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp).resolve()
            (raiz / "a_volumes").symlink_to(PROHIBIDA)
            (raiz / "permitida").symlink_to(PROHIBIDA + "/permitido.nc")
            with mock.patch.object(os, "lstat", _espia_de_lstat(consultadas)):
                r = RegistroAccesos((raiz / "a_volumes",), bloquear=True, permitidas=(raiz / "permitida",))
                with r:
                    with self.assertRaises(PermissionError):
                        os.stat(PROHIBIDA + "/x")
            self.assertIn(PROHIBIDA.casefold(), r._vigiladas)
            self.assertIn((PROHIBIDA + "/permitido.nc").casefold(), r._permitidas)
        self.assertEqual([c for c in consultadas if c.casefold().startswith("/volumes")], [])

    def test_s10_volumen_de_datos(self):
        """H6 (CEG-21): en macOS, /System/Volumes/Data/x es /x. En bloqueo, todo acceso a lo vigilado por ese prefijo
        se niega antes de ocurrir (en cualquier mayúscula, repetido, tras un «..» o por un enlace), sin consultar
        /Volumes por ninguna de sus dos formas; una vigilada o una permitida dadas con el prefijo valen por la forma
        corta; y el prefijo no vuelve vigilado lo que no lo está."""
        largo = VOLUMEN_DE_DATOS + PROHIBIDA
        for texto, esperado in ((largo + "/x", PROHIBIDA + "/x"), (VOLUMEN_DE_DATOS, "/"),
                                (VOLUMEN_DE_DATOS + "/", "/"),
                                ("/system/VOLUMES/data/private/var", "/private/var"),
                                (VOLUMEN_DE_DATOS * 2 + "/private/var", "/private/var"),
                                ("/System/Volumes/Preboot/x", "/System/Volumes/Preboot/x"),
                                ("/System/Volumes/DataX/y", "/System/Volumes/DataX/y"),
                                ("/x" + VOLUMEN_DE_DATOS + "/y", "/x" + VOLUMEN_DE_DATOS + "/y"),
                                ("relativa/x", "relativa/x")):
            with self.subTest(texto=texto):
                self.assertEqual(ceguera._sin_volumen_de_datos(texto), esperado)
        consultadas = []
        resto = PROHIBIDA[len("/Volumes"):]
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp).resolve()
            vigilada = raiz / "vigilada"
            vigilada.mkdir()
            permitida = vigilada / "permitida.txt"
            permitida.write_text("x", encoding="utf-8")
            (raiz / "a_datos").symlink_to(largo + "/x.nc")
            (raiz / "a_volumenes").symlink_to(VOLUMEN_DE_DATOS + "/Volumes")
            (raiz / "a_private").symlink_to(VOLUMEN_DE_DATOS + "/private")
            firmes = os.path.isdir(VOLUMEN_DE_DATOS + str(raiz))       # macOS: la misma carpeta por las dos formas
            acciones = (lambda: os.lstat(largo + "/y"), lambda: os.stat(largo), lambda: open(largo + "/x.json", "rb"),
                        lambda: os.listdir(largo.lower()), lambda: open("/SYSTEM/volumes/DATA" + PROHIBIDA + "/z"),
                        lambda: open(VOLUMEN_DE_DATOS * 2 + PROHIBIDA + "/w", "w"),
                        lambda: open(VOLUMEN_DE_DATOS + "/../Data/Volumes" + resto + "/v"),
                        lambda: open(raiz / "a_datos", "rb"), lambda: os.stat(str(raiz / "a_volumenes") + resto),
                        lambda: open(str(raiz / "a_private") + "/../Volumes" + resto + "/u"))
            with mock.patch.object(os, "lstat", _espia_de_lstat(consultadas)):
                with RegistroAccesos((PROHIBIDA,), bloquear=True) as r:
                    for i, accion in enumerate(acciones):
                        with self.subTest(accion=i), self.assertRaises(PermissionError):
                            accion()
                    if firmes:
                        os.stat(VOLUMEN_DE_DATOS + str(raiz))           # no vigilada: pasa
                r2 = RegistroAccesos((largo,), bloquear=True)
                with r2:
                    with self.assertRaises(PermissionError):
                        os.stat(PROHIBIDA + "/w")
                with RegistroAccesos((vigilada,), bloquear=True, permitidas=(VOLUMEN_DE_DATOS + str(permitida),)) as r3:
                    self.assertEqual(permitida.read_text(encoding="utf-8"), "x")
                    with self.assertRaises(PermissionError):
                        open(VOLUMEN_DE_DATOS + str(vigilada / "otra.txt"), "w")
                    if firmes:
                        self.assertEqual(Path(VOLUMEN_DE_DATOS + str(permitida)).read_text(encoding="utf-8"), "x")
            self.assertFalse((vigilada / "otra.txt").exists())
        self.assertEqual(len(r.accesos), len(acciones))
        self.assertEqual(len(r.por_enlace), 3)
        self.assertTrue(all(o.casefold().startswith(PROHIBIDA.casefold()) for _, o in r.accesos))
        self.assertIn(PROHIBIDA.casefold(), r2._vigiladas)
        self.assertFalse(any(v.startswith("/system/") for v in r2._vigiladas + r3._permitidas))
        self.assertEqual(len(r3.accesos), 1)
        self.assertEqual({e for e, _ in r3.lecturas_permitidas}, {"open"})
        self.assertEqual([c for c in consultadas if _bajo_volumes(c)], [])

    def test_s10_crear_un_enlace_no_es_acceso(self):
        """CEG-22: crear un enlace hacia /Volumes o hacia una vigilada (absoluto, relativo o por el volumen de datos)
        no es un acceso, porque no toca su destino; seguirlo después sí, por ``por_enlace``; crearlo dentro de una
        vigilada, también por un enlace a ella, es una escritura que se niega; ``os.lstat`` del enlace no lo sigue. El
        registro del reloj, en cambio, cuenta el destino (diferencia documentada)."""
        consultadas = []
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp).resolve()
            vigilada, afuera = raiz / "vigilada", raiz / "afuera"
            vigilada.mkdir()
            afuera.mkdir()
            (vigilada / "dato.txt").write_text("x", encoding="utf-8")
            (afuera / "a_vigilada").symlink_to(vigilada)
            with mock.patch.object(os, "lstat", _espia_de_lstat(consultadas)):
                with RegistroAccesos(("/" + "Volumes", vigilada), bloquear=True) as r:
                    (afuera / "e1").symlink_to(PROHIBIDA + "/x.nc")
                    os.symlink(vigilada / "dato.txt", afuera / "e2")
                    (afuera / "e3").symlink_to(VOLUMEN_DE_DATOS + PROHIBIDA)
                    os.symlink(Path("..") / "vigilada", afuera / "e4")
                    os.lstat(afuera / "e1")
                    self.assertEqual(r.accesos, [])
                    for i, accion in enumerate((lambda: open(afuera / "e1", "rb"), lambda: open(afuera / "e2", "rb"),
                                                lambda: os.stat(afuera / "e3"), lambda: os.listdir(afuera / "e4"),
                                                lambda: (vigilada / "l1").symlink_to(afuera),
                                                lambda: os.symlink(afuera, afuera / "a_vigilada" / "l2"))):
                        with self.subTest(accion=i), self.assertRaises(PermissionError):
                            accion()
            self.assertTrue(all((afuera / e).is_symlink() for e in ("e1", "e2", "e3", "e4")))
            self.assertFalse((vigilada / "l1").is_symlink() or (vigilada / "l2").is_symlink())
            self.assertEqual([e for e, _ in r.accesos], ["open", "open", "os.stat", "os.listdir", "os.symlink",
                                                         "os.symlink"])
            self.assertEqual(len(r.por_enlace), 5)
            self.assertTrue(all(o.casefold().startswith(("/volumes", str(vigilada).casefold())) for _, o in r.accesos))
            with _deja_os_como_estaba(), V.RegistroAccesos((vigilada,)) as del_reloj:   # sin bloqueo: es temporal
                os.symlink(vigilada / "dato.txt", afuera / "e5")
            self.assertEqual(len(del_reloj.accesos), 1, "el reloj ya no cuenta el destino: actualizar CEG-22")
        self.assertEqual([c for c in consultadas if _bajo_volumes(c)], [])

    def test_s10_anidados_por_volumes(self):
        """CEG-22 (VER-14): una ruta que pasa por «/Volumes/..» la juzga cada registro por dónde lo toca. Si el
        interior la niega, el exterior que vigila /Volumes la anota en ``negados_dentro`` y no en ``accesos``; si el
        interior sólo anota, queda en los dos y la niega el exterior; un acceso que el interior no vigila queda sólo en
        el exterior. Nada se consulta bajo /Volumes y nada llega al disco."""
        consultadas = []
        volumes = "/" + "Volumes"
        with tempfile.TemporaryDirectory() as tmp:
            afuera = Path(tmp).resolve() / "afuera"
            afuera.mkdir()
            (afuera / "x.txt").write_text("libre", encoding="utf-8")
            (afuera / "a_prohibida").symlink_to(PROHIBIDA)
            por_volumes = PROHIBIDA + "/../.." + str(afuera / "x.txt")
            por_enlace = str(afuera / "a_prohibida" / "y.nc")
            with mock.patch.object(os, "lstat", _espia_de_lstat(consultadas)):
                with RegistroAccesos((volumes,), bloquear=True) as exterior:
                    with RegistroAccesos((PROHIBIDA,), bloquear=True) as interior:
                        for accion in (lambda: open(por_volumes, encoding="utf-8"), lambda: os.stat(por_enlace),
                                       lambda: os.stat(PROHIBIDA + "/z")):
                            with self.assertRaises(PermissionError):
                                accion()
                        with self.assertRaises(PermissionError):
                            os.stat(volumes + "/otro_meteo_combinada_inexistente/x")
                with RegistroAccesos((volumes,), bloquear=True) as exterior2:
                    with RegistroAccesos((PROHIBIDA,)) as interior2:
                        with self.assertRaises(PermissionError):
                            open(por_volumes, encoding="utf-8")
            self.assertEqual((afuera / "x.txt").read_text(encoding="utf-8"), "libre")
        self.assertEqual(interior.accesos, [("open", PROHIBIDA), ("os.stat", PROHIBIDA + "/y.nc"),
                                            ("os.stat", PROHIBIDA + "/z")])
        self.assertEqual([p[0] for p in interior.por_enlace], ["open", "os.stat"])
        self.assertEqual([e for e, _ in exterior.negados_dentro], ["open", "os.stat", "os.stat"])
        self.assertEqual(exterior.accesos, [("os.stat", volumes + "/otro_meteo_combinada_inexistente/x")])
        self.assertEqual((interior2.accesos, exterior2.accesos), ([("open", PROHIBIDA)], [("open", volumes)]))
        self.assertEqual(exterior2.negados_dentro, [])
        self.assertEqual([c for c in consultadas if _bajo_volumes(c)], [])

    def test_s10_las_ocho_bajo_un_registro_exterior(self):
        """CEG-22 (PED-4 de I22): las ocho pruebas que crean enlaces hacia /Volumes o hacia AP, o que abren
        «/Volumes/..» dentro de su propio registro, pasan bajo un registro exterior como el de la batería (en bloqueo
        sobre /Volumes y los dos repositorios, que deja leerlos, con el directorio actual en la carpeta temporal del
        sistema, VER-18), y éste no anota ningún acceso: lo que negó el registro de una prueba queda en
        ``negados_dentro``, una sola vez aunque el espía de ``os.lstat`` quede entre dos registros, como queda una
        prueba con su espía bajo la batería. Nada se consulta bajo /Volumes. Corren también la paridad con el reloj (el
        recorrido no se cuenta en el registro del reloj) y la de crear enlaces, y al terminar ``os.stat``,
        ``os.lstat`` y ``os.access`` siguen envueltos."""
        import importlib
        de_aqui = ("test_s10_construir_sin_consultar_volumes", "test_s10_ruta_lexica_antes_de_resolver",
                   "test_s10_volumen_de_datos", "test_s10_enlace_seguido_de_punto_punto",
                   "test_s10_paridad_con_el_reloj", "test_s10_crear_un_enlace_no_es_acceso")
        ajenas = (("test_entorno", "PruebasGuardasSinVolumes", ("test_enlace_a_un_repositorio_se_detecta",
                                                                "test_enlace_a_volumes_se_detecta_sin_consultarlo")),
                  ("test_salidas", "PruebasS10Salidas", ("test_s10_nada_bajo_volumes",
                                                         "test_s10_nada_en_los_repositorios")))
        suite = unittest.TestSuite(type(self)(n) for n in de_aqui)
        for modulo, clase, nombres in ajenas:
            prueba = getattr(importlib.import_module(f"meteo_combinada.tests.{modulo}"), clase)
            suite.addTests(prueba(n) for n in nombres)
        repos = (str(_RAIZ.parent), str(_APH))
        consultadas = []
        previo = os.getcwd()
        os.chdir(tempfile.gettempdir())     # como la batería (VER-18): shutil.rmtree borra con nombres relativos
        vigiladas = ("/" + "Volumes", *repos)
        try:     # dos registros con el espía entre ellos: así queda una prueba con su espía bajo la batería
            with RegistroAccesos(vigiladas, bloquear=True, permitidas=repos) as bateria, \
                    mock.patch.object(os, "lstat", _espia_de_lstat(consultadas)):
                with RegistroAccesos(vigiladas, bloquear=True, permitidas=repos) as exterior:
                    resultado = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
                    envueltas = [ceguera._es_envoltorio(getattr(os, n)) for n in ("stat", "lstat", "access")]
        finally:
            os.chdir(previo)
        self.assertEqual(resultado.testsRun, len(de_aqui) + sum(len(n) for _, _, n in ajenas))
        self.assertEqual([t.id() for t, _ in resultado.failures + resultado.errors], [])
        self.assertEqual(envueltas, [True, True, True])
        self.assertEqual((exterior.accesos, bateria.accesos), ([], []))
        self.assertTrue(exterior.negados_dentro)
        self.assertEqual(len(bateria.negados_dentro), len(exterior.negados_dentro))     # una vez cada uno
        self.assertEqual([c for c in consultadas if _bajo_volumes(c)], [])

    def test_s10_permitidas_y_anidados(self):
        """CEG-3: dentro de una vigilada, una permitida se puede leer, no escribir; VER-14: el registro más interior
        que bloquea niega y los de afuera lo anotan aparte."""
        with tempfile.TemporaryDirectory() as tmp:
            vigilada = Path(tmp).resolve() / "vigilada"
            vigilada.mkdir()
            permitida = vigilada / "permitida.txt"
            permitida.write_text("x", encoding="utf-8")
            (vigilada / "otra.txt").write_text("y", encoding="utf-8")
            with RegistroAccesos((vigilada,), bloquear=True, permitidas=(permitida,)) as r:
                self.assertEqual(permitida.read_text(encoding="utf-8"), "x")
                os.stat(permitida)
                for accion in (lambda: open(permitida, "a"), lambda: os.remove(permitida),
                               lambda: open(vigilada / "otra.txt", "rb")):
                    with self.assertRaises(PermissionError):
                        accion()
            self.assertEqual({e for e, _ in r.lecturas_permitidas}, {"open", "os.stat"})
            self.assertEqual(len(r.accesos), 3)
            self.assertTrue(permitida.exists())
            with RegistroAccesos((PROHIBIDA,)) as afuera:
                with RegistroAccesos((PROHIBIDA,), bloquear=True) as adentro:
                    with self.assertRaises(PermissionError):
                        os.lstat(PROHIBIDA + "/x")
            self.assertEqual(([e for e, _ in adentro.accesos], afuera.accesos), (["os.lstat"], []))
            self.assertEqual([e for e, _ in afuera.negados_dentro], ["os.lstat"])
            with RegistroAccesos((PROHIBIDA,), bloquear=True) as afuera:
                with RegistroAccesos((PROHIBIDA,)) as adentro:
                    with self.assertRaises(PermissionError):
                        os.stat(PROHIBIDA + "/z")
            self.assertEqual(([e for e, _ in adentro.accesos], [e for e, _ in afuera.accesos]),
                             (["os.stat"], ["os.stat"]))

    def test_s10_paridad_con_el_reloj(self):
        """El registro anota lo mismo que el del reloj sobre los mismos accesos (sin bloqueo, en una carpeta
        temporal), en los eventos que el del reloj mira.

        Diferencia documentada (H7): con «enlace/..» el del reloj, que juzga sólo la ruta normalizada, no ve el acceso
        y éste sí. El reloj no se toca desde aquí; si se corrige, la última comprobación falla y esta nota se
        actualiza (aviso en COORDINACION_M1.md). Otra diferencia (H6 de la ola 4, CEG-21): éste quita el prefijo
        /System/Volumes/Data y el del reloj no; no se compara aquí, porque probarlo en el del reloj, que no bloquea
        esa forma, dejaría llegar el acceso a /Volumes. En la carpeta temporal el prefijo no aparece."""
        eventos_reloj = set(V._EVENTOS_DE_RUTA) | {"os.stat", "os.lstat"}

        def accesos(clase, vigilada: Path) -> list:
            (vigilada / "a.txt").write_text("a", encoding="utf-8")
            if (vigilada / "d").exists():
                shutil.rmtree(vigilada / "d")
            with clase((vigilada,)) as r:
                open(vigilada / "a.txt", "rb").close()
                os.stat(vigilada)
                os.lstat(vigilada / "a.txt")
                os.listdir(vigilada)
                with os.scandir(vigilada) as it:
                    list(it)
                Path(vigilada, "no_existe").exists()
                os.mkdir(vigilada / "d")
                shutil.copyfile(vigilada / "a.txt", vigilada / "d" / "b.txt")
                os.rename(vigilada / "d" / "b.txt", vigilada / "d" / "c.txt")
                os.remove(vigilada / "d" / "c.txt")
                glob.glob(str(vigilada / "*.txt"))
            return [a for a in r.accesos if a[0] in eventos_reloj]

        def con_punto_punto(clase, vigilada: Path, enlace: Path) -> list:
            with clase((vigilada,)) as r:
                open(str(enlace) + "/../a.txt", "rb").close()
            return r.accesos

        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp).resolve()
            vigilada = raiz / "vigilada"
            (vigilada / "sub").mkdir(parents=True)
            nuestros = accesos(RegistroAccesos, vigilada)
            with _deja_os_como_estaba():
                del_reloj = accesos(V.RegistroAccesos, vigilada)
            (raiz / "L").symlink_to(vigilada / "sub")
            nuestros_pp = con_punto_punto(RegistroAccesos, vigilada, raiz / "L")
            with _deja_os_como_estaba():
                del_reloj_pp = con_punto_punto(V.RegistroAccesos, vigilada, raiz / "L")
        self.assertTrue(nuestros)
        self.assertEqual(nuestros, del_reloj)
        self.assertEqual(len(nuestros_pp), 1)
        self.assertEqual(del_reloj_pp, [], "el reloj ya ve «enlace/..»: actualizar la nota de esta prueba")

    def test_s10_sin_red(self):
        """CEG-6: dentro de SinRed, conectar a 127.0.0.1, resolver un nombre o abrir una URL fallan antes de ocurrir;
        AF_UNIX sigue (comunicación local)."""
        import urllib.request
        with ceguera.SinRed() as afuera, ceguera.SinRed() as red:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                with self.assertRaises(ceguera.RedProhibida):
                    s.connect(("127.0.0.1", 9))
                with self.assertRaises(ceguera.RedProhibida):
                    s.bind(("127.0.0.1", 0))
            finally:
                s.close()
            u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                with self.assertRaises(ceguera.RedProhibida):
                    u.sendto(b"x", ("127.0.0.1", 9))
            finally:
                u.close()
            for accion in (lambda: socket.getaddrinfo("localhost", 80), lambda: socket.gethostbyname("localhost"),
                           lambda: urllib.request.urlopen("http://127.0.0.1:9/", timeout=1)):
                with self.assertRaises(ceguera.RedProhibida):
                    accion()
            with tempfile.TemporaryDirectory() as tmp:
                unix = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                try:
                    with self.assertRaises(FileNotFoundError):
                        unix.connect(str(Path(tmp) / "no_existe.sock"))
                finally:
                    unix.close()
        eventos = [e for e, _ in red.intentos]
        self.assertEqual(eventos[:3], ["socket.connect", "socket.bind", "socket.sendto"])
        self.assertIn("socket.getaddrinfo", eventos)
        self.assertIn("urllib.Request", eventos)
        self.assertEqual(afuera.intentos, red.intentos)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).close()     # fuera del contexto: inerte (sin conectar)

    def test_s10_sin_procesos_vivos(self):
        """CEG-7: un hijo vivo aparece; terminado y esperado, ya no; ps no se cuenta a sí mismo."""
        hijo = subprocess.Popen(["sleep", "30"])
        try:
            vivos = ceguera.procesos_hijos_vivos()
            self.assertIn(hijo.pid, vivos)
            self.assertNotIn(os.getpid(), vivos)
        finally:
            hijo.terminate()
            hijo.wait(timeout=60)
        self.assertNotIn(hijo.pid, ceguera.procesos_hijos_vivos())

    def test_s10_nieto_huerfano_por_su_grupo(self):
        """H9 (CEG-7): un nieto huérfano (sh -c "sleep 20 & …", en un grupo propio) no cuelga de este proceso; se ve
        al vigilar su grupo."""
        sh = subprocess.Popen(["/bin/sh", "-c", "sleep 20 & echo $!"], stdout=subprocess.PIPE, text=True,
                              process_group=0)
        nieto = int(sh.stdout.readline().strip())
        sh.wait(timeout=60)
        sh.stdout.close()
        try:
            for _ in range(50):          # el sistema tarda un instante en volver huérfano al nieto
                if nieto not in ceguera.procesos_hijos_vivos():
                    break
                time.sleep(0.1)
            self.assertNotIn(nieto, ceguera.procesos_hijos_vivos())
            self.assertIn(nieto, ceguera.procesos_hijos_vivos(grupos=(sh.pid,)))
        finally:
            os.kill(nieto, 15)
        for _ in range(50):
            if nieto not in ceguera.procesos_hijos_vivos(grupos=(sh.pid,)):
                break
            time.sleep(0.1)
        self.assertNotIn(nieto, ceguera.procesos_hijos_vivos(grupos=(sh.pid,)))


class PruebasCeguera(unittest.TestCase):
    def test_permitido_de_reloj(self):
        """§1.9 y MC-19 (CEG-13): la política, artefactos_evaluados y el registro de C5; la fuente de K2 sólo con
        k2=True; nada más de RELOJ, y ninguna ruta ajena."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            publicada = raiz / "AP" / "config" / "meteorologia" / "reloj_dmc" / "v1"
            corrida = raiz / "LOCAL" / "modelado_1km" / "verificacion_reloj_dmc" / "v1" / "HUMAN20261101_RELOJ_DMC_1"
            registro = raiz / "APH" / "auditoria" / "20261101" / "meteo_combinada" / "registro_politica_reloj.json"
            si = (publicada / "politica_reloj_dmc.json", publicada / "artefactos_evaluados.json.gz", registro,
                  Path(str(publicada / "POLITICA_RELOJ_DMC.JSON")))
            solo_k2 = (publicada / "informe_reloj_dmc.json", corrida / "pixeles_dmc.parquet")
            no = (publicada / "informe_reloj_dmc.md", corrida / "evidencia_estacion_anio.parquet",
                  corrida / "politica_reloj_dmc.json", corrida / "informe_reloj_dmc.json",
                  corrida / "resumen_c1.json", publicada / "pixeles_dmc.parquet",
                  raiz / "otra" / "politica_reloj_dmc.json", raiz / "APH" / "registro_politica_reloj.json",
                  raiz / "LOCAL" / "meteo_combinada" / "v1" / "m1" / "resumen_m1.json")
            for ruta in si:
                with self.subTest(si=ruta.name):
                    self.assertTrue(ceguera.permitido_de_reloj(ruta))
                    self.assertTrue(ceguera.permitido_de_reloj(ruta, k2=True))
                    self.assertTrue(ceguera.es_de_reloj(ruta))
            for ruta in solo_k2:
                with self.subTest(k2=ruta.name):
                    self.assertFalse(ceguera.permitido_de_reloj(ruta))
                    self.assertTrue(ceguera.permitido_de_reloj(ruta, k2=True))
            for ruta in no:
                with self.subTest(no=str(ruta.relative_to(raiz))):
                    self.assertFalse(ceguera.permitido_de_reloj(ruta, k2=True))
            self.assertTrue(ceguera.es_de_reloj(corrida / "resumen_c1.json"))
            self.assertFalse(ceguera.es_de_reloj(raiz / "LOCAL" / "meteo_combinada" / "x.json"))
            self.assertEqual(list(raiz.iterdir()), [])             # todo léxico: nada se creó ni se consultó
        self.assertTrue(ceguera.permitido_de_reloj("AP/config/meteorologia/reloj_dmc/v1/politica_reloj_dmc.json"))

    def test_es_procedencia(self):
        for texto in ("ERA5L/mensual/x.nc", "LOCAL/meteo_combinada/v1/m1/x.json", SHA, SHA[:8] + "…", "4b50b0d",
                      "sha256:" + SHA, f"«{SHA[:8]}…»"):
            self.assertTrue(ceguera.es_procedencia(texto), texto)
        for texto in ("ERA5L", "fondo_T", "20261023", "x/ERA5L/y", "LOCALES/x"):
            self.assertFalse(ceguera.es_procedencia(texto), texto)

    def test_importar_ceguera_no_carga_numpy_ni_reloj_politica(self):
        """ceguera acepta tablas sin importar pandas al cargarse."""
        codigo = ("import sys; sys.path.insert(0, sys.argv[1]); from meteo_combinada import ceguera; "
                  "print([m for m in ('numpy', 'pandas', 'pyarrow', 'netCDF4', 'reloj_dmc.politica') "
                  "if m in sys.modules])")
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run([sys.executable, "-B", "-I", "-c", codigo, str(_RAIZ)], cwd=tmp, capture_output=True,
                               text=True, timeout=120, check=True)
        self.assertEqual(r.stdout.strip().splitlines()[-1], "[]")


if __name__ == "__main__":
    unittest.main()
