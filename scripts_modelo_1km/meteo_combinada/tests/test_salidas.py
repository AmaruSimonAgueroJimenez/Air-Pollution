"""Pruebas de salidas.py (§8 del texto; S7, S9 y S10 en lo que toca a la escritura).

Dueño: I17 (ola 4; corregidas tras la revisión independiente de la ola 4, H1 a H17). Las que llevan «sNN» son la
prueba NN de §9 del texto. Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
Datos sólo sintéticos, en carpetas temporales (``tempfile.TemporaryDirectory``): ninguna prueba abre DMC, la
meteorología SINCA real, NASADEM real, GHS-POP real ni nada del reloj. Ninguna prueba escribe en AP, en APH ni en la
carpeta personal: la publicación de M5 va a una carpeta temporal (también el «AP real» de la regla de H11, que se
fabrica), y las pruebas de rechazo tienen dos redes de seguridad que actúan antes del disco:
``entorno.escribir_atomico`` cambiado por una función que falla y un ``ceguera.RegistroAccesos`` en bloqueo sobre
AP, APH, /Volumes o la carpeta de prueba bajo la personal, que niega toda escritura antes de que ocurra (y la prueba
exige que no haya ninguna). El alias ``/System/Volumes/Data`` de /Volumes se vigila con un espía de ``os.lstat`` que
niega antes de consultar. Los textos con la ruta de la carpeta de usuario y la arroba se arman al correr (privacidad
del paquete).
"""
import sys

sys.dont_write_bytecode = True

import bz2  # noqa: E402
import gzip  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import lzma  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import struct  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import unittest  # noqa: E402
import zipfile  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from meteo_combinada import ceguera, entorno, numerico, salidas, tipos  # noqa: E402
from meteo_combinada.ceguera import RegistroAccesos, SalidaProhibida  # noqa: E402

PROHIBIDA = "/Volumes/meteo_combinada_prueba_inexistente"
ALIAS_DATOS = "/System/Volumes/Data"
USUARIO = "/" + "Users" + "/alguien/x.json"
ARROBA = "autor" + chr(64) + "dominio"
SHA_A = hashlib.sha256(b"entrada sintetica A").hexdigest()
SHA_B = hashlib.sha256(b"entrada sintetica B").hexdigest()
ENTORNO = {"python": "3.11.16", "pandas": "2.3.3", "netCDF4": "1.7.4", "tzdata": "2026.3", "iana": "2026c",
           "procesos": 8}
ETIQUETA = "HUMAN20261027_METEO_COMB_1"
CASA_PRUEBA = "meteo_combinada_prueba_inexistente"
# Un texto sintético para los documentos (D13): cita el vocabulario de S7 y sus números; su huella reemplaza a la del
# texto vigente sólo al construir la referencia (como test_ceguera).
TEXTO_SINTETICO = ("# Producto sintético, texto v2.3\n"
                   "§5.7: «el fondo ERA5-Land reescalado … las cotas de TF1 son 0,05/0,15 K».\n"
                   "La corrección R_T no se resume y «sin DMC» no se estima.\n")
SHA_SINTETICO = hashlib.sha256(TEXTO_SINTETICO.encode("utf-8")).hexdigest()
QC, VAL, TF = tipos.ESQUEMA_QC_ESTACION, tipos.ESQUEMA_VALIDACION_PUB, tipos.ESQUEMA_TF
METADATOS_LATERAL = {"model_ready": True, "source_policy_verified": True, "policy_sha256": SHA_A, "variante": "I",
                     "columnas": ["mc_t2m", "mc_d2m"], "unidades": {"mc_t2m": "K"}}
PUBLICADAS = ["decision.json", "politicas/politicas_meteo_v1.json", "qc/resumen_qc.json", "registro_m34.json",
              "tendencias/resumen_tf.parquet", "sha256.json", "recibo_corrida.json"]


def _referencia() -> "ceguera.ReferenciaDocumento":
    with mock.patch.object(ceguera, "SHA_TEXTO_VIGENTE", SHA_SINTETICO):
        return ceguera.ReferenciaDocumento(TEXTO_SINTETICO, SHA_SINTETICO)


def _tabla(esquema, n: int = 2, **valores) -> pd.DataFrame:
    """Una tabla con exactamente las columnas y tipos del esquema (valores por omisión neutros)."""
    columnas = {}
    for c, t in esquema.items():
        if c in valores:
            v = valores[c]
        elif t == "string":
            v = [f"{c}{i}" for i in range(n)]
        elif t in ("bool", "boolean"):
            v = [False] * n
        elif t.startswith("datetime64"):
            columnas[c] = pd.Series(pd.date_range("2000-01-01", periods=n, freq="h", tz="UTC"))
            continue
        else:
            v = np.arange(n)
        columnas[c] = pd.Series(v, dtype=t)
    df = pd.DataFrame(columnas)
    tipos.validar_esquema(df, esquema, nombre="prueba")
    return df


def _netcdf(valores=(1.0, 2.0), atributos=None) -> bytes:
    import netCDF4
    ds = netCDF4.Dataset("memoria.nc", "w", memory=1024, format="NETCDF4")
    ds.createDimension("x", len(valores))
    v = ds.createVariable("T", "f4", ("x",))
    for k, valor in (atributos or {}).items():
        ds.setncattr(k, valor)
    v[:] = np.asarray(valores, dtype="f4")
    return bytes(ds.close())


def _zip(contenido: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("dentro.json", contenido)
    return buf.getvalue()


def _sin_escribir():
    """Red de seguridad de las pruebas de rechazo: si una guarda fallara, nada llega al disco."""
    return mock.patch.object(entorno, "escribir_atomico", side_effect=AssertionError("no debía escribir"))


def _espia_de_volumes():
    """Un espía de ``os.lstat`` que niega (y anota) toda consulta bajo /Volumes, también por ``/System/Volumes/Data``,
    antes de que ocurra."""
    real = os.lstat
    vistas: list[str] = []

    def espia(ruta, *a, **k):
        if isinstance(ruta, (str, bytes, os.PathLike)):
            t = os.path.normpath(os.path.abspath(os.fsdecode(os.fspath(ruta)))).casefold()
            alias = ALIAS_DATOS.casefold()
            while t == alias or t.startswith(alias + "/"):
                t = t[len(alias):] or "/"
            if t == "/volumes" or t.startswith("/volumes/"):
                vistas.append(t)
                raise PermissionError("espía: consulta bajo /Volumes")
        return real(ruta, *a, **k)

    return mock.patch("os.lstat", espia), vistas


def _archivos(carpeta: Path) -> list[str]:
    """Los archivos y los enlaces (de cualquier destino) bajo una carpeta, relativos a ella, sin seguir nunca un enlace:
    ``os.scandir`` con ``is_symlink`` primero y ``follow_symlinks=False``, así que el destino de un enlace (también uno
    hacia /Volumes) no se consulta, ni dentro de un registro exterior como el de la batería de M1."""
    salida, pendientes = [], [Path(carpeta)]
    while pendientes:
        with os.scandir(pendientes.pop()) as entradas:
            for e in entradas:
                if e.is_symlink() or e.is_file(follow_symlinks=False):
                    salida.append(Path(e.path).relative_to(carpeta).as_posix())
                elif e.is_dir(follow_symlinks=False):
                    pendientes.append(Path(e.path))
    return sorted(salida)


def _temporal(caso: unittest.TestCase) -> Path:
    td = tempfile.TemporaryDirectory()
    caso.addCleanup(td.cleanup)
    return Path(td.name)


def _fabricar_corrida(base: Path, *, sellar: bool = True) -> tuple["entorno.Rutas", Path]:
    """Una corrida mínima de M3-4 y M5 (sintética), escrita entera por salidas y, si se pide, sellada."""
    rutas = entorno.rutas_sinteticas(base / "rutas")
    carpeta = entorno.carpeta_salida(rutas, "m34", ETIQUETA)

    def e(ruta, contenido, clase, **k):
        return salidas.escribir(ruta, contenido, clase=clase, raiz=carpeta, **k)

    sha_qc = e("qc/estaciones/330020.parquet", _tabla(QC, 3), "insumo", esquema=QC)
    e("qc/resumen_qc.json", {"marcas": {"error_grueso": {"Ts": 1}}, "alarmas": [], "no_normalizables": 0}, "resumen")
    e("politicas/politicas_meteo_v1.json", {"politicas": [{"station_code": "330020", "verified": True}]}, "insumo")
    sha_val = e("validacion/puntajes.parquet", _tabla(VAL, 1), "metrica", esquema=VAL)
    e("tendencias/resumen_tf.parquet", _tabla(TF, 1), "resumen", esquema=TF)
    e("decision.json", {"ganador": {"agudo": {"T_Td": "A"}},
                        "huellas": {entorno.alias(carpeta / "validacion/puntajes.parquet", rutas): sha_val}}, "metrica")
    e("registro_m34.json", {"estaciones": 3, "declaraciones": ["D34"]}, "resumen")
    e("m6/decision_m6.json", {"rama": 1}, "resumen")
    e("producto_01deg/meteo_200001.nc", _netcdf(), "insumo")
    for sub in ("civil", "utc4", "regional", "representatividad"):
        e(f"salud/{sub}/meteo_2000.parquet", _tabla(tipos.ESQUEMA_METEO_DIARIA, 1), "insumo",
          esquema=tipos.ESQUEMA_METEO_DIARIA)
    e("salud/cronico/temperatura_anual.parquet", _tabla(tipos.ESQUEMA_CRONICO, 1), "insumo",
      esquema=tipos.ESQUEMA_CRONICO)
    e("ambiental/lateral_pm25_I.parquet", _tabla(tipos.ESQUEMA_LATERAL_I, 2), "insumo",
      esquema=tipos.ESQUEMA_LATERAL_I, metadatos=METADATOS_LATERAL)
    salidas.agregar_linea("avance.jsonl", {"unidad": "qc/estaciones/330020", "estado": "hecha", "sha256": sha_qc},
                          raiz=carpeta)
    salidas.agregar_linea("intentos_aplicar.jsonl", {"fecha": "2026-10-27T17:00:00Z", "resultado": "confirmatoria"},
                          raiz=carpeta)
    if sellar:
        salidas.sellar_corrida(carpeta, {"ERA5L/era5land_200001.nc": SHA_A}, ENTORNO, rutas=rutas)
    return rutas, carpeta


class _ConTemporal(unittest.TestCase):
    def setUp(self):
        self.raiz = _temporal(self)          # una carpeta temporal que hace de corrida (SLD-1)
        self.tmp = _temporal(self)           # otra, para lo demás


# =====================================================================================================
# S7: vocabulario por clases (D3, D12, D13, D14, D53) y centinelas del residuo (§0.4.6)
# =====================================================================================================
class PruebasS7Salidas(_ConTemporal):
    def test_s07_escribir_rechaza_vocabulario_prohibido(self):
        """Métrica y resumen rechazan «fondo», «era5l», «sin_dmc», «correccion» y «R_» como sujeto (y los nombres
        propios del fondo y del residuo, CEG-10), en claves, valores, textos, columnas y en el nombre del archivo;
        no queda nada escrito. Pasan ``dmc_R_*`` listadas bajo «columnas…», la tabla de RR06 por su sujeto
        «lluvia_producto» y las clases exentas: insumo (MC-02, D3), procedencia y documento (D13)."""
        malos = ({"rmse_fondo": 0.1}, {"sesgo": {"era5land_t2m": 0.2}}, {"modelo": "sin DMC"}, {"correccion_a": 1},
                 {"R_T": 0.0}, {"T_F": 1.0}, {"dmc_R_T_media": 0.1}, {"columnas": ["dmc_R_T", "R_T"]})
        with _sin_escribir():
            for clase, carpeta in (("metrica", "validacion"), ("resumen", "tendencias")):
                for malo in malos:
                    with self.subTest(clase=clase, malo=malo), self.assertRaises(SalidaProhibida):
                        salidas.escribir(f"{carpeta}/x.json", malo, clase=clase, raiz=self.raiz)
                with self.subTest(clase=clase, caso="texto"), self.assertRaises(SalidaProhibida):
                    salidas.escribir(f"{carpeta}/notas.txt", "el fondo ERA5-Land", clase=clase, raiz=self.raiz)
                with self.subTest(clase=clase, caso="nombre"), self.assertRaises(SalidaProhibida):
                    salidas.escribir(f"{carpeta}/fondo.json", {"a": 1}, clase=clase, raiz=self.raiz)
                for esquema in (tipos.ESQUEMA_RESIDUOS, tipos.ESQUEMA_LATERAL_D, tipos.ESQUEMA_PUNTOS_E5L):
                    with self.subTest(clase=clase, esquema=esquema.nombre), self.assertRaises(SalidaProhibida):
                        salidas.escribir(f"{carpeta}/{esquema.nombre}.parquet", _tabla(esquema), clase=clase,
                                         esquema=esquema, raiz=self.raiz)
        self.assertEqual(_archivos(self.raiz), [])
        # Lo que sí pasa.
        salidas.escribir("tendencias/columnas.json", {"columnas_D": list(tipos.COLUMNAS_R_D)}, clase="resumen",
                         raiz=self.raiz)
        salidas.escribir("m6/decision_m6.json", {"predictores_D": ["fecha", *tipos.COLUMNAS_R_D], "rama": 1},
                         clase="resumen", raiz=self.raiz)
        salidas.escribir("validacion/rr06.json", {"sujeto": "lluvia_producto", "correlacion": 0.7}, clase="metrica",
                         raiz=self.raiz)
        for ruta, esquema in (("ambiental/lateral_pm25_D.parquet", tipos.ESQUEMA_LATERAL_D),
                              ("insumos/puntos_estacion/330020.parquet", tipos.ESQUEMA_PUNTOS_E5L),
                              ("producto/residuos/330020.parquet", tipos.ESQUEMA_RESIDUOS),
                              ("estaticas/estaciones.parquet", tipos.ESQUEMA_ESTACIONES_MC),
                              ("estaticas/celdas.parquet", tipos.ESQUEMA_ESTATICAS_CELDA_C)):
            salidas.escribir(ruta, _tabla(esquema), clase="insumo", esquema=esquema, raiz=self.raiz)
        celdas = pd.read_parquet(self.raiz / "estaticas/celdas.parquet")
        self.assertIn(tipos.COLUMNA_Z_E5L, celdas.columns)
        self.assertEqual(celdas.attrs, {"esquema": tipos.ESQUEMA_ESTATICAS_CELDA_C.version})
        salidas.escribir("sha256.json", {"esquema": salidas.ESQUEMA_SHA256,
                                         "archivos": {"insumos/puntos_estacion/330020.parquet": {"sha256": SHA_A}}},
                         clase="procedencia", raiz=self.raiz)
        salidas.escribir("pruebas_m1.txt", f"{SHA_SINTETICO}\n§5.7: el fondo ERA5-Land; la corrección R_T no se "
                                           "resume.\nRan 3 tests in 0.010s\n\nOK\n", clase="documento",
                         referencia=_referencia(), raiz=self.raiz)

    def test_s07_ninguna_salida_contiene_mediana_ni_mad(self):
        """Corrida mínima con ``GuardaResiduo``: el residuo de una estación lleva inyectados los centinelas en su
        mediana y su MAD (``numerico.mediana_mad``), que marcan en memoria un error grueso; la corrida escribe por
        salidas su tabla ancha, el resumen del control, las métricas, la decisión, un mes del producto, el avance y el
        sello, y ninguna salida trae los centinelas (en ninguna forma de CEG-14). Toda salida que los traiga, de
        cualquier clase, se rechaza y no queda escrita."""
        g = ceguera.GuardaResiduo()
        m_inyectada, d_inyectado = g.centinela("mediana"), g.centinela("mad")
        z = np.tile(np.array([-2.0, -1.0, 0.0, 1.0, 2.0]), 24)        # mediana 0 y MAD 1, exactas
        r = m_inyectada + d_inyectado * z
        m, d = numerico.mediana_mad(r)
        self.assertEqual(m, m_inyectada)
        self.assertAlmostEqual(d, d_inyectado, places=9)
        g.registrar("mediana_calculada", m)
        g.registrar("mad_calculado", d)
        marca = np.abs(r - m) > 1.5 * d                              # sólo en memoria (§0.4.6)
        n = len(r)
        rutas = entorno.rutas_sinteticas(self.tmp / "rutas")
        carpeta = entorno.carpeta_salida(rutas, "m34", ETIQUETA)
        with salidas.corrida_en_curso(carpeta), salidas.vigilar_residuo(g):
            tabla = _tabla(QC, n, h=np.arange(n), Ts=(15.0 + z).astype("float32"),
                           marcas_Ts=np.where(marca, 1 << 13, 0), valido_T=~marca)
            sha_qc = salidas.escribir("qc/estaciones/330020.parquet", tabla, clase="insumo", esquema=QC)
            salidas.escribir("qc/resumen_qc.json", {"marcas": {"error_grueso": {"Ts": int(marca.sum())}},
                                                    "alarmas": []}, clase="resumen")
            sha_val = salidas.escribir("validacion/puntajes.parquet", _tabla(VAL, 1, S=[0.8]), clase="metrica",
                                       esquema=VAL)
            salidas.escribir("decision.json", {"ganador": {"agudo": {"T_Td": "A"}}, "huellas": {
                entorno.alias(carpeta / "validacion/puntajes.parquet", rutas): sha_val}}, clase="metrica")
            salidas.escribir("producto_01deg/meteo_200001.nc", _netcdf((15.0, 16.0)), clase="insumo")
            salidas.agregar_linea("avance.jsonl", {"unidad": "qc/estaciones/330020", "estado": "hecha",
                                                   "sha256": sha_qc})
            # Cada intento de guardar la mediana o el MAD se rechaza, en toda clase y forma.
            intentos = (
                ("qc/diagnostico.json", {"mediana_residuo": m}, "resumen", {}),
                ("qc/notas.txt", f"MAD del residuo {d:.6g}", "resumen", {}),
                ("insumos/puntos_estacion/330020.parquet",
                 _tabla(tipos.ESQUEMA_PUNTOS_E5L, 2, T_F=np.array([1.0, m], dtype="float32")), "insumo",
                 {"esquema": tipos.ESQUEMA_PUNTOS_E5L}),
                ("producto_01deg/meteo_200002.nc", _netcdf((d, 1.0)), "insumo", {}),
                ("insumos/binario.bin", struct.pack("<d", m), "insumo", {}),
                ("insumos/comprimido.json.gz", gzip.compress(json.dumps([d]).encode()), "insumo", {}),
            )
            for ruta, contenido, clase, extra in intentos:
                with self.subTest(ruta=ruta), self.assertRaises(SalidaProhibida):
                    salidas.escribir(ruta, contenido, clase=clase, **extra)
                self.assertFalse((carpeta / ruta).exists())
            with self.assertRaises(SalidaProhibida):
                salidas.agregar_linea("avance.jsonl", {"unidad": "x", "mad": d})
            salidas.sellar_corrida(carpeta, {"ERA5L/era5land_200001.nc": SHA_A}, ENTORNO, rutas=rutas)
        self.assertEqual(g.buscar_en(carpeta), [])
        g.comprobar(carpeta)
        self.assertIn("recibo_corrida.json", _archivos(carpeta))
        self.assertEqual(len((carpeta / "avance.jsonl").read_bytes().splitlines()), 1)

    def test_s07_la_guarda_rige_solo_en_su_contexto(self):
        """``vigilar_residuo`` activa la guarda en este proceso; dos guardas anidadas valen las dos; al salir del
        contexto la guarda deja de regir (los centinelas sólo existen en las pruebas)."""
        g1, g2 = ceguera.GuardaResiduo(), ceguera.GuardaResiduo()
        c1 = g1.centinela("mediana")
        g2.registrar("mad", 3.14159271)
        with salidas.vigilar_residuo(g1):
            with salidas.vigilar_residuo(g2):
                for valor in (c1, 3.14159271):
                    with self.assertRaises(SalidaProhibida):
                        salidas.escribir("insumos/x.json", {"v": valor}, clase="insumo", raiz=self.raiz)
            salidas.escribir("insumos/y.json", {"v": 3.14159271}, clase="insumo", raiz=self.raiz)
            with self.assertRaises(SalidaProhibida):
                salidas.escribir("insumos/x.json", {"v": c1}, clase="insumo", raiz=self.raiz)
        salidas.escribir("insumos/x.json", {"v": c1}, clase="insumo", raiz=self.raiz)
        with self.assertRaises(TypeError):
            with salidas.vigilar_residuo(object()):
                pass

    def test_s07_la_clase_la_fija_la_ruta(self):
        """La clase fijada por la ruta (``ceguera.clase_de_ruta``; D3, D13, D14, D53) manda; una declarada distinta
        se rechaza, también entre métrica y resumen (SLD-3). Las de P42 y P43, si ``ceguera`` ya las fija, son las de
        la propuesta. Una ruta que no fija clase sólo se declara métrica, resumen o documento, nunca insumo ni
        procedencia (H16). Una clase desconocida es un error."""
        with _sin_escribir():
            for ruta, contenido, declarada in (("decision.json", {"a": "A"}, "resumen"),
                                               ("tendencias/x.json", {"a": 1}, "metrica"),
                                               ("validacion/x.json", {"a": 1}, "resumen"),
                                               ("insumos/x.json", {"a": 1}, "metrica"),
                                               ("recibo_corrida.json", {"esquema": "x/1"}, "resumen"),
                                               ("pruebas_m1.txt", "OK", "resumen"),
                                               ("qc/resumen_qc.json", {"a": 1}, "insumo"),
                                               ("qc/sin_clase.json", {"a": 1}, "insumo"),
                                               ("qc/sin_clase.json", {"a": 1}, "procedencia"),
                                               ("notas/x.txt", "x", "insumo")):
                with self.subTest(ruta=ruta, declarada=declarada), self.assertRaises(SalidaProhibida):
                    salidas.escribir(ruta, contenido, clase=declarada, raiz=self.raiz)
            with self.assertRaises(ValueError):
                salidas.escribir("qc/x.json", {"a": 1}, clase="tabla", raiz=self.raiz)
        self.assertEqual(_archivos(self.raiz), [])
        for clase in ("metrica", "resumen"):
            salidas.escribir(f"qc/sin_clase_{clase}.json", {"a": 1}, clase=clase, raiz=self.raiz)
        p42 = {"resumen_m1.json": "resumen", "costo_m1.json": "resumen", "deriva_s6.json": "resumen",
               "registro_m2a.json": "resumen", "registro_m34.json": "resumen",
               "m6/tf_contaminantes_pm25.json": "resumen", "informe.json": "resumen",
               "politicas/politicas_meteo_v1.json": "insumo"}
        for nombre, clase in p42.items():
            with self.subTest(p42=nombre):
                fijada = ceguera.clase_de_ruta(nombre)
                self.assertIn(fijada, (None, clase))
                otra = "metrica" if clase == "resumen" else "resumen"
                if fijada is not None:
                    with _sin_escribir(), self.assertRaises(SalidaProhibida):
                        salidas.escribir(nombre, {"a": 1}, clase=otra, raiz=self.raiz)
                    salidas.escribir(nombre, {"a": 1}, clase=clase, raiz=self.raiz)
        self.assertIn(ceguera.clase_de_ruta("informe.md"), (None, "documento"))
        rutas = entorno.rutas_sinteticas(self.tmp / "rutas")
        m6 = entorno.carpeta_salida(rutas, "m6", ETIQUETA)
        with _sin_escribir(), self.assertRaises(SalidaProhibida):
            salidas.escribir("lateral.json", {"a": 1}, clase="insumo", raiz=m6)
        salidas.escribir("ramas.json", {"rama": 1}, clase="resumen", raiz=m6)
        salidas.agregar_linea("intentos_m6.jsonl", {"resultado": "rama_1"}, raiz=m6)
        self.assertEqual(sorted(p.name for p in m6.iterdir()), ["intentos_m6.jsonl", "ramas.json"])
        tabla = _tabla(tipos.ESQUEMA_NO_NORMALIZABLES, 1)
        salidas.escribir("qc/no_normalizables.csv", tabla, clase="resumen", esquema=tipos.ESQUEMA_NO_NORMALIZABLES,
                         raiz=self.raiz)
        with _sin_escribir(), self.assertRaises(SalidaProhibida):
            salidas.escribir("qc/no_normalizables.csv", tabla, clase="insumo", esquema=tipos.ESQUEMA_NO_NORMALIZABLES,
                             raiz=self.raiz)
        self.assertIn(salidas.clase_de_salida("qc/no_normalizables.csv"), (None, "resumen"))

    def test_s07_la_clase_no_depende_de_la_raiz(self):
        """H1: la clase sale del nombre relativo a la carpeta de la corrida (la hija de ``v1``, o la carpeta
        temporal que hace de corrida), no a la raíz que pasa quien llama; la raíz sólo puede tener una forma de ENT-4,
        y «m6» y la etiqueta se comparan sin distinguir mayúsculas."""
        rutas = entorno.rutas_sinteticas(self.tmp / "rutas")
        corrida = entorno.carpeta_salida(rutas, "m34", ETIQUETA)
        malo = {"rmse_fondo": 0.1}
        with _sin_escribir():
            for raiz in (corrida / "validacion", corrida / "tendencias", corrida / "qc", corrida / "M6" / "x",
                         corrida / "m6" / "validacion", rutas.salidas, rutas.local, rutas.salidas / "otra_cosa",
                         rutas.salidas / "m1" / "a" / "b", rutas.salidas / "HUMAN20261399_METEO_COMB_1",
                         self.raiz / "a" / "b"):
                with self.subTest(raiz=raiz.relative_to(raiz.parents[2]).as_posix()), \
                        self.assertRaises(PermissionError):
                    salidas.escribir("x.json", malo, clase="insumo", raiz=raiz)
            for m6 in ("M6", "m6"):
                for clase in ("insumo", "resumen"):
                    with self.subTest(m6=m6, clase=clase), self.assertRaises(SalidaProhibida):
                        salidas.escribir("x.json", malo, clase=clase, raiz=corrida / m6)
            with self.assertRaises(SalidaProhibida):
                salidas.escribir("validacion/x.json", malo, clase="insumo", raiz=rutas.salidas / ETIQUETA.lower())
            with self.assertRaises(SalidaProhibida):           # la carpeta temporal que hace de corrida, con una sub
                salidas.escribir("x.json", {"a": 1}, clase="insumo", raiz=self.raiz / "validacion")
            # Sin vocabulario y con una clase que se puede declarar sin ruta: sólo el nombre relativo a la corrida
            # («validacion/x.json», métrica; «m6/x.json», resumen) los rechaza.
            with self.assertRaises(SalidaProhibida):
                salidas.escribir("x.json", {"a": 1}, clase="resumen", raiz=self.raiz / "validacion")
            with self.assertRaises(SalidaProhibida):
                salidas.escribir("x.json", {"a": 1}, clase="metrica", raiz=corrida / "M6")
        self.assertFalse(corrida.exists())
        salidas.escribir("x.json", {"rama": 1}, clase="resumen", raiz=corrida / "M6")
        self.assertTrue((corrida / "M6" / "x.json").is_file())
        salidas.escribir("x.json", {"a": 1}, clase="metrica", raiz=self.raiz / "validacion")
        salidas.escribir("resumen_m1.json", {"a": 1}, clase="resumen",
                         raiz=entorno.carpeta_salida(rutas, "m1", "prueba"))
        salidas.escribir("registro_m2a.json", {"a": 1}, clase="resumen", raiz=entorno.carpeta_salida(rutas, "m2a"))

    def test_s07_documento_con_su_referencia(self):
        """D13: un documento se escribe con su ``ReferenciaDocumento`` y sólo él la lleva; un número de datos en un
        documento se rechaza."""
        ref = _referencia()
        texto = f"{SHA_SINTETICO}\nCotas de TF1: 0,05/0,15 K.\nRan 2 tests in 0.004s\n\nOK\n"
        salidas.escribir("pruebas_m1.txt", texto, clase="documento", referencia=ref, raiz=self.raiz)
        with _sin_escribir():
            with self.assertRaises(ValueError):
                salidas.escribir("informe_b.md", texto, clase="documento", raiz=self.raiz)
            with self.assertRaises(ValueError):
                salidas.escribir("qc/x.json", {"a": 1}, clase="resumen", referencia=ref, raiz=self.raiz)
            dato = "0," + str(8317 * 3)
            with self.assertRaises(SalidaProhibida):
                salidas.escribir("informe_b.md", f"{SHA_SINTETICO}\nS = {dato} K\n", clase="documento",
                                 referencia=ref, raiz=self.raiz)
            with self.assertRaises(SalidaProhibida):
                salidas.escribir("informe_b.md", "sin la huella del texto\n", clase="documento", referencia=ref,
                                 raiz=self.raiz)

    def test_s07_esquemas_de_tipos(self):
        """SLD-4: cada esquema de ``tipos.ESQUEMAS`` se escribe como insumo; como métrica pasan todos salvo los que
        nombran el fondo o el residuo (los de ``test_ceguera`` y, desde que está en ``ESQUEMAS``, los estáticos de C
        con ``z_e5l``). Una tabla sin esquema, con otro, con un esquema que sólo vive en memoria o fuera de
        ``ESQUEMAS``, o con ``attrs['esquema']`` distinto, se rechaza, cada una por su razón."""
        fallan = []
        for esquema in tipos.ESQUEMAS.values():
            tabla = tipos.tabla_vacia(esquema)
            salidas.escribir(f"insumos/{esquema.nombre}.parquet", tabla, clase="insumo", esquema=esquema,
                             raiz=self.raiz)
            try:
                with _sin_escribir():
                    salidas.escribir(f"validacion/{esquema.nombre}.parquet", tabla, clase="metrica", esquema=esquema,
                                     raiz=self.raiz)
            except SalidaProhibida:
                fallan.append(esquema.nombre)
            except AssertionError:      # pasó todas las guardas y llegó a la escritura (cambiada por la prueba)
                pass
        self.assertEqual(fallan, ["estaciones_mc", "ze5l", "puntos_e5l", "residuos", "clima_a", "lateral_d",
                                  "estaticas_celda_c"])
        tabla = _tabla(TF, 1)
        falso = tipos.Esquema("falso", "meteo-combinada-falso/1", dict(TF))        # las columnas calzan
        malos = [("sin esquema", {}, tabla), ("diccionario", {"esquema": dict(TF)}, tabla),
                 ("otro", {"esquema": VAL}, tabla),
                 ("en memoria", {"esquema": tipos.ESQUEMA_PREDICCION}, tipos.tabla_vacia(tipos.ESQUEMA_PREDICCION)),
                 ("fuera de ESQUEMAS", {"esquema": falso}, tabla)]
        with _sin_escribir():
            for caso, extra, t in malos:
                with self.subTest(caso=caso), self.assertRaises(ValueError):
                    salidas.escribir("tendencias/resumen_tf.parquet", t, clase="resumen", raiz=self.raiz, **extra)
            otra = tabla.copy()
            otra.attrs["esquema"] = "meteo-combinada-tf/0"
            with self.assertRaises(ValueError):
                salidas.escribir("tendencias/resumen_tf.parquet", otra, clase="resumen", esquema=TF, raiz=self.raiz)
            with self.assertRaises(ValueError):
                salidas.escribir("tendencias/resumen_tf.json", tabla, clase="resumen", esquema=TF, raiz=self.raiz)
            with self.assertRaises(ValueError):
                salidas.escribir("qc/resumen.json", {"a": 1}, clase="resumen", esquema=TF, raiz=self.raiz)
        con_attrs = tipos.tabla_vacia(TF)
        self.assertEqual(con_attrs.attrs["esquema"], TF.version)
        salidas.escribir("tendencias/vacia.parquet", con_attrs, clase="resumen", esquema=TF, raiz=self.raiz)
        self.assertEqual(pd.read_parquet(self.raiz / "tendencias/vacia.parquet").attrs, {"esquema": TF.version})

    def test_s07_clases_propias(self):
        """SLD-3: los recibos archivados (``recibos/recibo_<n>.json``) son procedencia; si ``ceguera`` ya los nombra,
        con la misma clase, y donde ``ceguera`` no da clase (otro prefijo) los fija ``CLASES_PROPIAS``. Manda
        ``ceguera``: si fija los de ``m6/`` (PED-6, resuelto por I4), volver a sellar M6 archiva el primer recibo con
        sus mismos bytes en ``m6/recibos/recibo_1.json`` y el nuevo recibo cita su huella; si no los fijara, volver a
        sellar M6 se negaría sin tocar el recibo."""
        self.assertIn(ceguera.clase_de_ruta("recibos/recibo_1.json"), (None, "procedencia"))
        self.assertEqual(salidas.clase_de_salida("recibos/recibo_12.json"), "procedencia")
        self.assertIsNone(salidas.clase_de_salida("recibos/otro.json"))
        self.assertEqual(salidas.clase_de_salida("prueba/recibos/recibo_1.json"),
                         ceguera.clase_de_ruta("prueba/recibos/recibo_1.json") or "procedencia")
        clases_m6 = {ceguera.clase_de_ruta(f"m6/recibos/{f}") for f in ("recibo_1.json", "recibo_1_sha256.json")}
        en_m6 = clases_m6.pop() if len(clases_m6) == 1 else None
        self.assertEqual(salidas.clase_de_salida("m6/recibos/recibo_1.json"), ceguera.clase_de_ruta(
            "m6/recibos/recibo_1.json"))
        rutas = entorno.rutas_sinteticas(self.tmp / "rutas")
        m6 = entorno.carpeta_salida(rutas, "m6", ETIQUETA)
        salidas.escribir("ramas.json", {"rama": 1}, clase="resumen", raiz=m6)
        primero = salidas.sellar_corrida(m6, {"ERA5L/era5land_200001.nc": SHA_A}, ENTORNO, rutas=rutas)
        datos_primero = (m6 / "recibo_corrida.json").read_bytes()
        inventario_primero = (m6 / "sha256.json").read_bytes()
        self.assertEqual(hashlib.sha256(datos_primero).hexdigest(), primero)
        if en_m6 == "procedencia":
            segundo = salidas.sellar_corrida(m6, {"ERA5L/era5land_200001.nc": SHA_A}, ENTORNO, rutas=rutas)
            self.assertNotEqual(segundo, primero)
            self.assertEqual((m6 / "recibos" / "recibo_1.json").read_bytes(), datos_primero)
            self.assertEqual((m6 / "recibos" / "recibo_1_sha256.json").read_bytes(), inventario_primero)
            nuevo = json.loads((m6 / "recibo_corrida.json").read_bytes())
            prefijo = f"LOCAL/meteo_combinada/v1/{ETIQUETA}/m6/recibos/"
            self.assertEqual(nuevo["huellas"][prefijo + "recibo_1.json"], primero)
            self.assertEqual(nuevo["huellas"][prefijo + "recibo_1_sha256.json"],
                             hashlib.sha256(inventario_primero).hexdigest())
            inventario = json.loads((m6 / "sha256.json").read_bytes())["archivos"]
            self.assertEqual(inventario["recibos/recibo_1.json"]["sha256"], primero)
            self.assertEqual(salidas.fallas_de_sello_archivado(m6, 1), [])
        else:
            with self.assertRaises(SalidaProhibida):
                salidas.sellar_corrida(m6, {"ERA5L/era5land_200001.nc": SHA_A}, ENTORNO, rutas=rutas)
            self.assertFalse((m6 / "recibos").exists())
            self.assertEqual((m6 / "recibo_corrida.json").read_bytes(), datos_primero)


# =====================================================================================================
# S10: nada bajo /Volumes ni en los repositorios, ni fuera de la carpeta de la corrida
# =====================================================================================================
class PruebasS10Salidas(_ConTemporal):
    def test_s10_nada_bajo_volumes(self):
        """Ni por la ruta léxica (también en mayúsculas y por ``/System/Volumes/Data``), ni por un enlace hacia
        /Volumes (también escrito con ese alias), ni con «..»; y nada bajo /Volumes se consulta: todo corre dentro de
        un ``RegistroAccesos`` en bloqueo sobre /Volumes y de un espía de ``os.lstat``, y ninguno ve un acceso. El
        alias hacia la carpeta temporal escribe donde debe."""
        os.symlink(PROHIBIDA, self.raiz / "enlace")
        os.symlink(ALIAS_DATOS + PROHIBIDA, self.raiz / "enlace_alias")
        os.symlink(PROHIBIDA + "/c", self.tmp / "raiz_enlace")
        os.symlink(PROHIBIDA, self.tmp / "ap_enlace")
        casos = (
            lambda: salidas.escribir("x.json", {"a": 1}, clase="resumen", raiz=PROHIBIDA + "/c"),
            lambda: salidas.escribir("x.json", {"a": 1}, clase="resumen", raiz="/VOLUMES/meteo_combinada_x/c"),
            lambda: salidas.escribir("x.json", {"a": 1}, clase="resumen", raiz=ALIAS_DATOS + PROHIBIDA + "/c"),
            lambda: salidas.escribir("x.json", {"a": 1}, clase="resumen",
                                     raiz=ALIAS_DATOS.upper() + "/VOLUMES/meteo_combinada_x/c"),
            lambda: salidas.escribir(PROHIBIDA + "/x.json", {"a": 1}, clase="resumen", raiz=self.raiz),
            lambda: salidas.escribir(ALIAS_DATOS + PROHIBIDA + "/x.json", {"a": 1}, clase="resumen", raiz=self.raiz),
            lambda: salidas.escribir("enlace/x.json", {"a": 1}, clase="resumen", raiz=self.raiz),
            lambda: salidas.escribir("enlace_alias/x.json", {"a": 1}, clase="resumen", raiz=self.raiz),
            lambda: salidas.escribir("x.json", {"a": 1}, clase="resumen", raiz=self.tmp / "raiz_enlace"),
            lambda: salidas.escribir("enlace/../x.json", {"a": 1}, clase="resumen", raiz=self.raiz),
            lambda: salidas.agregar_linea("enlace/avance.jsonl", {"estado": "hecha"}, raiz=self.raiz),
            lambda: salidas.agregar_linea("enlace_alias/avance.jsonl", {"estado": "hecha"}, raiz=self.raiz),
            lambda: salidas.inventario(PROHIBIDA),
            lambda: salidas.inventario(ALIAS_DATOS + PROHIBIDA),
            lambda: salidas.fallas_de_cierre(PROHIBIDA),
            lambda: salidas.carpeta_publicacion(PROHIBIDA),
            lambda: salidas.carpeta_publicacion(ALIAS_DATOS + PROHIBIDA),
            lambda: salidas.publicar_m5(self.raiz, self.tmp / "ap_enlace"),
            lambda: salidas.publicar_m5(self.raiz, PROHIBIDA),
        )
        with _sin_escribir(), RegistroAccesos(["/Volumes"], bloquear=True) as reg:
            espia, vistas = _espia_de_volumes()          # dentro del registro: el espía llama a su envoltorio
            with espia:
                for i, caso in enumerate(casos):
                    with self.subTest(caso=i), self.assertRaises(PermissionError):
                        caso()
        self.assertEqual(reg.accesos, [])
        self.assertEqual(reg.por_enlace, [])
        self.assertEqual(vistas, [])
        self.assertEqual(_archivos(self.raiz), ["enlace", "enlace_alias"])
        por_alias = ALIAS_DATOS + os.path.realpath(self.raiz)
        espia, vistas = _espia_de_volumes()
        with espia:
            salidas.escribir("alias.json", {"a": 1}, clase="resumen", raiz=por_alias)
        self.assertEqual(vistas, [])
        self.assertTrue((self.raiz / "alias.json").is_file())

    def test_s10_nada_en_los_repositorios(self):
        """Ni en AP ni en APH: por la ruta léxica, en mayúsculas distintas (APFS no las distingue), por
        ``/System/Volumes/Data``, por un enlace hacia un repositorio (también escrito en mayúsculas, que
        ``entorno.prohibido_repositorios`` no ve) ni por la publicación. Todo corre dentro de un ``RegistroAccesos``
        en bloqueo sobre AP y APH que deja leer pero niega toda escritura antes de que ocurra, y no ve ninguna."""
        reales = entorno.rutas_reales()
        ap, aph = reales.ap, reales.aph
        inexistente = "_prueba_salidas_inexistente"
        destinos = [ap / "config" / "meteorologia" / "meteo_combinada" / inexistente, aph / "auditoria" / inexistente,
                    Path(str(ap).upper()) / inexistente, ap / "scripts_modelo_1km" / "meteo_combinada" / inexistente,
                    Path(ALIAS_DATOS + str(ap)) / inexistente]
        os.symlink(destinos[3], self.raiz / "enlace_ap")
        os.symlink(str(destinos[3]).upper(), self.raiz / "enlace_mayusculas")
        os.symlink(ALIAS_DATOS + str(destinos[3]), self.raiz / "enlace_alias")
        with _sin_escribir(), RegistroAccesos([ap, aph], bloquear=True, permitidas=[ap, aph]) as reg:
            for i, destino in enumerate(destinos):
                with self.subTest(raiz=i), self.assertRaises(PermissionError):
                    salidas.escribir("x.json", {"a": 1}, clase="resumen", raiz=destino)
                with self.subTest(ruta=i), self.assertRaises(PermissionError):
                    salidas.escribir(destino / "x.json", {"a": 1}, clase="resumen", raiz=self.raiz)
            for enlace in ("enlace_ap", "enlace_mayusculas", "enlace_alias"):
                with self.subTest(enlace=enlace), self.assertRaises(PermissionError):
                    salidas.escribir(f"{enlace}/x.json", {"a": 1}, clase="resumen", raiz=self.raiz)
                with self.subTest(enlace=enlace, linea=True), self.assertRaises(PermissionError):
                    salidas.agregar_linea(f"{enlace}/avance.jsonl", {"estado": "hecha"}, raiz=self.raiz)
            for destino_ap in (aph, ap / "scripts_modelo_1km", Path(str(aph).upper()), Path(ALIAS_DATOS + str(aph))):
                with self.subTest(publicar=str(destino_ap.name)), self.assertRaises(PermissionError):
                    salidas.publicar_m5(self.raiz, destino_ap)
            with self.assertRaises(PermissionError):
                salidas.corrida_en_curso(ap / inexistente).__enter__()
        self.assertEqual(reg.accesos, [])
        for destino in destinos:
            self.assertFalse(destino.exists())
        self.assertFalse(salidas.hay_corrida_en_curso())
        self.assertEqual(salidas.carpeta_publicacion(ap), ap / "config" / "meteorologia" / "meteo_combinada" / "v1")
        self.assertTrue(salidas.es_ap_real(ap))
        self.assertTrue(salidas.es_ap_real(Path(str(ap).upper())))
        self.assertFalse(salidas.es_ap_real(self.tmp))

    def test_s10_nada_fuera_de_la_corrida(self):
        """Sólo dentro de la raíz que se indica, una forma de ENT-4 bajo LOCAL/meteo_combinada/v1 o la carpeta
        temporal: ni una ruta absoluta fuera de ella, ni «..», ni un enlace que salga, ni una raíz relativa, en la
        carpeta personal (con un registro en bloqueo sobre la carpeta de prueba) o la temporal misma, ni el sufijo
        «.part», ni sobre un «.part» que ya existe (interrumpido, plantado como enlace hacia afuera o como vínculo
        duro); sin raíz indicada, nada."""
        otra = self.tmp / "otra"
        otra.mkdir()
        (otra / "ajeno.txt").write_bytes(b"ajeno")
        os.symlink(otra, self.raiz / "enlace_afuera")
        (self.raiz / "adentro").mkdir()
        os.symlink(self.raiz / "adentro", self.raiz / "enlace_adentro")
        os.symlink(otra / "robado.json", self.raiz / "plantado.json.part")
        (self.raiz / "interrumpido.json.part").write_bytes(b"{")
        os.link(otra / "ajeno.txt", self.raiz / "duro.json.part")
        casa = Path.home() / CASA_PRUEBA
        casos = {
            "absoluta afuera": (lambda: salidas.escribir(otra / "x.json", {"a": 1}, clase="resumen",
                                                         raiz=self.raiz), PermissionError),
            "puntos": (lambda: salidas.escribir("../otra/x.json", {"a": 1}, clase="resumen", raiz=self.raiz),
                       PermissionError),
            "enlace afuera": (lambda: salidas.escribir("enlace_afuera/x.json", {"a": 1}, clase="resumen",
                                                       raiz=self.raiz), PermissionError),
            "raiz relativa": (lambda: salidas.escribir("x.json", {"a": 1}, clase="resumen", raiz="corrida"),
                              ValueError),
            "raiz con puntos": (lambda: salidas.escribir("x.json", {"a": 1}, clase="resumen",
                                                         raiz=self.tmp / "otra" / ".." / "corrida"), PermissionError),
            "carpeta personal": (lambda: salidas.escribir("x.json", {"a": 1}, clase="resumen", raiz=casa),
                                 PermissionError),
            "temporal misma": (lambda: salidas.escribir("x.json", {"a": 1}, clase="resumen",
                                                        raiz=tempfile.gettempdir()), PermissionError),
            "parcial": (lambda: salidas.escribir("x.json.part", b"x", clase="resumen", raiz=self.raiz), ValueError),
            "la raiz": (lambda: salidas.escribir(self.raiz, b"x", clase="resumen", raiz=self.raiz), PermissionError),
            "sin raiz": (lambda: salidas.escribir("x.json", {"a": 1}, clase="resumen"), ValueError),
            "parcial plantado": (lambda: salidas.escribir("plantado.json", {"a": 1}, clase="resumen",
                                                          raiz=self.raiz), PermissionError),
            "parcial interrumpido": (lambda: salidas.escribir("interrumpido.json", {"a": 1}, clase="resumen",
                                                              raiz=self.raiz), PermissionError),
            "parcial con vinculo": (lambda: salidas.escribir("duro.json", {"a": 1}, clase="resumen", raiz=self.raiz),
                                    PermissionError),
        }
        with _sin_escribir(), RegistroAccesos([casa], bloquear=True, permitidas=[casa]) as reg:
            for nombre, (caso, error) in casos.items():
                with self.subTest(caso=nombre), self.assertRaises(error):
                    caso()
        self.assertEqual(reg.accesos, [])
        self.assertFalse(casa.exists())
        self.assertEqual(sorted(p.name for p in otra.iterdir()), ["ajeno.txt"])
        self.assertEqual((otra / "ajeno.txt").read_bytes(), b"ajeno")
        salidas.escribir("enlace_adentro/x.json", {"a": 1}, clase="resumen", raiz=self.raiz)
        self.assertTrue((self.raiz / "adentro" / "x.json").is_file())


# =====================================================================================================
# Escritura, contenido, cadena de huellas y publicación (§8)
# =====================================================================================================
class PruebasSalidas(_ConTemporal):
    def test_escritura_atomica_y_privacidad(self):
        """La escritura es atómica (sin «.part» al terminar; si el renombre falla, queda el archivo anterior y no
        queda «.part») y devuelve el sha256 de lo escrito. Sin la ruta de la carpeta de usuario, la carpeta personal
        ni la arroba en el nombre ni en ningún texto, en toda clase: texto, JSON (también con la arroba escapada),
        celdas y metadatos de un parquet, atributos de un NetCDF, gzip y binario; lo comprimido de otra forma (bz2,
        xz, zip), por su contenido o su extensión, se rechaza (H7)."""
        sha = salidas.escribir("qc/resumen_qc.json", {"a": 1}, clase="resumen", raiz=self.raiz)
        destino = self.raiz / "qc" / "resumen_qc.json"
        self.assertEqual(sha, hashlib.sha256(destino.read_bytes()).hexdigest())
        self.assertEqual(destino.read_bytes(), b'{"a":1}')
        with mock.patch("os.replace", side_effect=OSError("renombre simulado")), self.assertRaises(OSError):
            salidas.escribir("qc/resumen_qc.json", {"a": 2}, clase="resumen", raiz=self.raiz)
        self.assertEqual(destino.read_bytes(), b'{"a":1}')
        self.assertEqual(_archivos(self.raiz), ["qc/resumen_qc.json"])
        casa = str(Path.home())
        privados = (
            ("qc/notas.txt", f"ver {USUARIO}", "resumen", {}),
            ("insumos/x.json", {"autor": ARROBA}, "insumo", {}),
            ("insumos/y.json", {"carpeta": casa + "/datos"}, "insumo", {}),
            ("insumos/" + ARROBA + ".json", {"a": 1}, "insumo", {}),
            ("insumos/no_normalizables.parquet", _tabla(tipos.ESQUEMA_NO_NORMALIZABLES, 1, codigo=[casa]), "insumo",
             {"esquema": tipos.ESQUEMA_NO_NORMALIZABLES}),
            ("ambiental/lateral_pm25_I.parquet", _tabla(tipos.ESQUEMA_LATERAL_I, 1), "insumo",
             {"esquema": tipos.ESQUEMA_LATERAL_I, "metadatos": {"fuente": USUARIO}}),
            ("producto_01deg/meteo_200001.nc", _netcdf(atributos={"autor": ARROBA}), "insumo", {}),
            ("insumos/z.json.gz", gzip.compress(json.dumps({"autor": ARROBA}).encode()), "insumo", {}),
            ("insumos/binario.bin", b"\xff\xfe" + USUARIO.encode() + b"\x00", "insumo", {}),
            ("insumos/escapada.json", b'{"autor": "x\\u0040y"}', "insumo", {}),          # la arroba escapada
            ("insumos/lineas.jsonl", b'{"a": 1}\n{"autor": "x\\u0040y"}\n', "insumo", {}),
            ("insumos/a.json.bz2", bz2.compress(b'{"a": 1}'), "insumo", {}),
            ("insumos/b.bin", bz2.compress(b'{"a": 1}'), "insumo", {}),
            ("insumos/c.bin", lzma.compress(b'{"a": 1}'), "insumo", {}),
            ("insumos/d.bin", _zip(b'{"a": 1}'), "insumo", {}),
            ("insumos/e.zip", b"texto plano", "insumo", {}),
            ("insumos/f.json.gz", gzip.compress(bz2.compress(b"{}")), "insumo", {}),
        )
        with _sin_escribir():
            for ruta, contenido, clase, extra in privados:
                with self.subTest(ruta=ruta), self.assertRaises(SalidaProhibida):
                    salidas.escribir(ruta, contenido, clase=clase, raiz=self.raiz, **extra)
        self.assertEqual(_archivos(self.raiz), ["qc/resumen_qc.json"])
        numeros = struct.pack("<dd", 2.0, 3.0)                       # 0x40 (la arroba) es un byte común en los números
        self.assertIn(chr(64).encode(), numeros)
        salidas.escribir("insumos/binario.bin", b"\xff\xfe" + numeros, clase="insumo", raiz=self.raiz)

    def test_s09_mismas_entradas_mismos_bytes(self):
        """S9 en lo de salidas: las mismas entradas dan los mismos bytes y las mismas huellas en dos carpetas (JSON
        canónico con las claves en otro orden; parquet y CSV de una tabla; líneas de un .jsonl); el parquet lleva la
        versión de su esquema y los metadatos, que ``pandas.read_parquet`` devuelve en ``attrs``."""
        n = 6
        tabla = _tabla(QC, n, Ts=np.linspace(-5, 30, n).astype("float32"), ts_fuente=[f"2000-01-01 0{i}:00"
                                                                                      for i in range(n)])
        huellas, raices = [], [_temporal(self), _temporal(self)]
        for raiz, orden in zip(raices, ({"b": 2.5, "a": [1, "x"], "c": {"z": None, "y": True}},
                                        {"c": {"y": True, "z": None}, "a": [1, "x"], "b": 2.5})):
            huellas.append((
                salidas.escribir("qc/resumen_qc.json", orden, clase="resumen", raiz=raiz),
                salidas.escribir("qc/estaciones/330020.parquet", tabla.copy(), clase="insumo", esquema=QC, raiz=raiz),
                salidas.escribir("qc/no_normalizables.csv", _tabla(tipos.ESQUEMA_NO_NORMALIZABLES, 3), clase="resumen",
                                 esquema=tipos.ESQUEMA_NO_NORMALIZABLES, raiz=raiz),
                salidas.escribir("ambiental/lateral_pm25_I.parquet", _tabla(tipos.ESQUEMA_LATERAL_I, 3),
                                 clase="insumo", esquema=tipos.ESQUEMA_LATERAL_I, metadatos=METADATOS_LATERAL,
                                 raiz=raiz),
                salidas.escribir("insumos/registros.jsonl", [{"b": 1, "a": 2}, {"c": 3}], clase="insumo", raiz=raiz),
            ))
        self.assertEqual(huellas[0], huellas[1])
        leida = pd.read_parquet(raices[0] / "qc/estaciones/330020.parquet")
        self.assertEqual(leida.attrs, {"esquema": QC.version})
        tipos.validar_esquema(leida, QC, nombre="releída")
        pd.testing.assert_frame_equal(leida, tabla, check_like=False)
        lateral = pd.read_parquet(raices[0] / "ambiental/lateral_pm25_I.parquet")
        self.assertEqual(lateral.attrs["metadatos"], METADATOS_LATERAL)
        self.assertEqual((raices[0] / "insumos/registros.jsonl").read_bytes(), b'{"a":2,"b":1}\n{"c":3}\n')
        self.assertTrue((raices[0] / "qc/no_normalizables.csv").read_text().startswith("id_artefacto,codigo,"))

    def test_formas_del_contenido(self):
        """SLD-4 y SLD-14: texto en UTF-8 y bytes tal cual; un diccionario sólo en .json, una lista de registros en
        .jsonl; un parquet sólo desde una tabla, también dentro de un gzip o con «.parquet.gz» (H8); sin NaN en un
        JSON; ``metadatos`` sólo en un parquet; un nombre con espacios o decimales no cabe en sha256.json (H12)."""
        self.assertEqual(salidas.escribir("informe_b.txt", "líneas\n", clase="resumen", raiz=self.raiz),
                         hashlib.sha256("líneas\n".encode("utf-8")).hexdigest())
        salidas.escribir("producto_01deg/crudo.nc", _netcdf(), clase="insumo", raiz=self.raiz)
        parquet = io.BytesIO()
        _tabla(TF, 1).to_parquet(parquet)
        with _sin_escribir():
            for contenido, ruta, error in (({"a": 1}, "insumos/x.md", ValueError),
                                           ("texto", "insumos/x.parquet", ValueError),
                                           (b"PAR1" + b"\x00" * 8, "insumos/x.bin", ValueError),
                                           (gzip.compress(parquet.getvalue()), "insumos/x.bin.gz", ValueError),
                                           (gzip.compress(b"{}"), "insumos/x.parquet.gz", ValueError),
                                           ({1, 2}, "insumos/x.json", TypeError),
                                           ({"a": 1}, "insumos/x.jsonl", ValueError),
                                           ({"a": float("nan")}, "insumos/x.json", ValueError),
                                           (3.5, "insumos/x.json", TypeError),
                                           ({"a": 1}, "insumos/con espacio.json", SalidaProhibida),
                                           ({"a": 1}, "insumos/v1.5/x.json", SalidaProhibida)):
                with self.subTest(ruta=ruta, contenido=repr(contenido)[:20]), self.assertRaises(error):
                    salidas.escribir(ruta, contenido, clase="insumo", raiz=self.raiz)
            with self.assertRaises(ValueError):
                salidas.escribir("qc/no_normalizables.csv", _tabla(tipos.ESQUEMA_NO_NORMALIZABLES, 1), clase="resumen",
                                 esquema=tipos.ESQUEMA_NO_NORMALIZABLES, metadatos={"a": 1}, raiz=self.raiz)
            with self.assertRaises(ValueError):
                salidas.escribir("insumos/x.json", {"a": 1}, clase="insumo", metadatos={"a": 1}, raiz=self.raiz)
            with self.assertRaises(SalidaProhibida):
                salidas.agregar_linea("con espacio/avance.jsonl", {"estado": "hecha"}, raiz=self.raiz)
        self.assertEqual(_archivos(self.raiz), ["informe_b.txt", "producto_01deg/crudo.nc"])

    def test_solo_agregado(self):
        """SLD-8: ``agregar_linea`` agrega líneas JSON canónicas a ``avance.jsonl`` e ``intentos_*.jsonl`` (clase
        procedencia, D12) y devuelve el sha256 de la línea; ``escribir`` sobre ellos exige conservar lo que hay; una
        última línea incompleta, un enlace, un vínculo duro (H3), un «.gz» (H8), otro archivo o un registro con
        decimales se rechazan."""
        linea = {"unidad": "qc/estaciones/330020", "estado": "hecha", "sha256": SHA_A}
        sha = salidas.agregar_linea("avance.jsonl", linea, raiz=self.raiz)
        self.assertEqual(sha, hashlib.sha256(entorno.json_canonico(linea) + b"\n").hexdigest())
        salidas.agregar_linea("avance.jsonl", {"unidad": "qc/estaciones/330021", "estado": "hecha"}, raiz=self.raiz)
        avance = self.raiz / "avance.jsonl"
        previo = avance.read_bytes()
        self.assertEqual(len(previo.splitlines()), 2)
        salidas.agregar_linea("intentos_aplicar.jsonl", {"fecha": "2026-10-27T17:00:00Z", "resultado": "abortado",
                                                         "intento": 1}, raiz=self.raiz)
        with _sin_escribir():
            with self.assertRaises(SalidaProhibida):
                salidas.escribir("avance.jsonl", b'{"estado":"hecha"}\n', clase="procedencia", raiz=self.raiz)
            for malo in ({"unidad": "x", "segundos": 1.5}, {"unidades": -1}, {"texto": "0.5"}):
                with self.subTest(malo=malo), self.assertRaises(SalidaProhibida):
                    salidas.agregar_linea("avance.jsonl", malo, raiz=self.raiz)
            with self.assertRaises(ValueError):
                salidas.agregar_linea("decision.json", {"a": "b"}, raiz=self.raiz)
            with self.assertRaises(ValueError):
                salidas.agregar_linea("avance.jsonl", ["no", "es", "un", "registro"], raiz=self.raiz)
            with self.assertRaises(SalidaProhibida):
                salidas.agregar_linea("avance.jsonl.gz", {"estado": "hecha"}, raiz=self.raiz)
            with self.assertRaises(SalidaProhibida):
                salidas.escribir("intentos_x.jsonl.gz", gzip.compress(b'{"estado":"hecha"}\n'), clase="procedencia",
                                 raiz=self.raiz)
        self.assertEqual(avance.read_bytes(), previo)
        salidas.escribir("avance.jsonl", previo + b'{"estado":"hecha","unidad":"m"}\n', clase="procedencia",
                         raiz=self.raiz)
        self.assertEqual(len(avance.read_bytes().splitlines()), 3)
        incompleta = self.raiz / "intentos_m6.jsonl"
        incompleta.write_bytes(b'{"resultado":"rama')                 # una escritura interrumpida (fabricada)
        with self.assertRaises(SalidaProhibida):
            salidas.agregar_linea("intentos_m6.jsonl", {"resultado": "rama_1"}, raiz=self.raiz)
        with self.assertRaises(SalidaProhibida):
            salidas.escribir("intentos_m6.jsonl", b'{"resultado":"rama_1"}\n', clase="procedencia", raiz=self.raiz)
        self.assertEqual(incompleta.read_bytes(), b'{"resultado":"rama')
        os.symlink(avance, self.raiz / "intentos_enlace.jsonl")
        with self.assertRaises(PermissionError):
            salidas.agregar_linea("intentos_enlace.jsonl", {"resultado": "x"}, raiz=self.raiz)
        ajeno = self.tmp / "ajeno.jsonl"
        ajeno.write_bytes(b'{"a":"b"}\n')
        os.link(ajeno, self.raiz / "intentos_duro.jsonl")             # un vínculo duro hacia afuera
        with self.assertRaises(PermissionError):
            salidas.agregar_linea("intentos_duro.jsonl", {"resultado": "x"}, raiz=self.raiz)
        with self.assertRaises(PermissionError):
            salidas.escribir("intentos_duro.jsonl", b'{"a":"b"}\n{"resultado":"x"}\n', clase="procedencia",
                             raiz=self.raiz)
        self.assertEqual(ajeno.read_bytes(), b'{"a":"b"}\n')

    def test_cerrojo_en_v1(self):
        """SLD-1 (PED-2 de I22; §10, P92): ``v1/cerrojo`` es una raíz admitida, sin subcarpetas, sólo para los
        ``intentos_*.jsonl`` (procedencia, sólo agregado): ``agregar_linea`` y ``escribir`` (conservando lo que hay)
        funcionan, también con «CERROJO»; cualquier otro archivo, una subcarpeta, un «.gz» o otra clase se niegan, y
        la raíz no puede pasar por un enlace (ni hacia otra carpeta ni hacia otra carpeta de ``v1``)."""
        rutas = entorno.rutas_sinteticas(self.tmp / "rutas")
        cerrojo = rutas.salidas / "cerrojo"
        linea = {"fecha": "2026-10-28T03:00:00Z", "resultado": "abortado", "intento": 1}
        sha = salidas.agregar_linea("intentos_aplicar.jsonl", linea, raiz=cerrojo)
        self.assertEqual(sha, hashlib.sha256(entorno.json_canonico(linea) + b"\n").hexdigest())
        salidas.agregar_linea("intentos_m6.jsonl", {"resultado": "rama_1"}, raiz=rutas.salidas / "CERROJO")
        previo = (cerrojo / "intentos_aplicar.jsonl").read_bytes()
        salidas.escribir("intentos_aplicar.jsonl", previo + b'{"resultado":"confirmatoria"}\n', clase="procedencia",
                         raiz=cerrojo)
        with salidas.corrida_en_curso(cerrojo):
            salidas.agregar_linea("intentos_aplicar.jsonl", {"resultado": "reanudada"})
        self.assertEqual(sorted(p.name for p in cerrojo.iterdir()), ["intentos_aplicar.jsonl", "intentos_m6.jsonl"])
        self.assertEqual(len((cerrojo / "intentos_aplicar.jsonl").read_bytes().splitlines()), 3)
        with _sin_escribir():
            for ruta, contenido, clase in (("avance.jsonl", b'{"estado":"hecha"}\n', "procedencia"),
                                           ("decision.json", {"ganador": "A"}, "metrica"),
                                           ("recibo_corrida.json", {"esquema": "x/1"}, "procedencia"),
                                           ("notas.txt", "x", "resumen"),
                                           ("sub/intentos_aplicar.jsonl", b'{"a":"b"}\n', "procedencia"),
                                           ("intentos_x.jsonl.gz", gzip.compress(b'{"a":"b"}\n'), "procedencia")):
                with self.subTest(ruta=ruta), self.assertRaises(SalidaProhibida):
                    salidas.escribir(ruta, contenido, clase=clase, raiz=cerrojo)
            for ruta in ("avance.jsonl", "sub/intentos_aplicar.jsonl"):
                with self.subTest(linea=ruta), self.assertRaises(SalidaProhibida):
                    salidas.agregar_linea(ruta, {"estado": "hecha"}, raiz=cerrojo)
            with self.assertRaises(SalidaProhibida):
                salidas.escribir_sha256(cerrojo)
            with self.assertRaises(PermissionError):
                salidas.agregar_linea("intentos_aplicar.jsonl", linea, raiz=cerrojo / "sub")
        self.assertEqual(sorted(p.name for p in cerrojo.iterdir()), ["intentos_aplicar.jsonl", "intentos_m6.jsonl"])
        # La raíz no pasa por un enlace: ni hacia otra carpeta ni hacia otra carpeta de v1.
        otras = entorno.rutas_sinteticas(self.tmp / "otras")
        otras.salidas.mkdir(parents=True)
        afuera = self.tmp / "afuera"
        afuera.mkdir()
        (otras.salidas / ETIQUETA).mkdir()
        os.symlink(afuera, otras.salidas / "cerrojo")
        os.symlink(afuera, otras.salidas / "HUMAN20261028_METEO_COMB_1")
        for raiz in (otras.salidas / "cerrojo", otras.salidas / "HUMAN20261028_METEO_COMB_1"):
            with self.subTest(raiz=raiz.name), self.assertRaises(PermissionError):
                salidas.agregar_linea("intentos_aplicar.jsonl", linea, raiz=raiz)
        rutas_enlace = entorno.rutas_sinteticas(self.tmp / "con_enlace")      # un cerrojo que es otra carpeta de v1
        rutas_enlace.salidas.mkdir(parents=True)
        os.symlink(otras.salidas / ETIQUETA, rutas_enlace.salidas / "cerrojo")
        with self.assertRaises(PermissionError):
            salidas.agregar_linea("intentos_aplicar.jsonl", linea, raiz=rutas_enlace.salidas / "cerrojo")
        self.assertEqual(list(afuera.iterdir()), [])
        self.assertEqual(list((otras.salidas / ETIQUETA).iterdir()), [])

    def test_recibo_corrida(self):
        """SLD-10: ``recibo_corrida.json`` lleva sólo rutas por alias con sha256 de 64 caracteres (o con sus bytes),
        las versiones y los enteros de la lista cerrada (D12), sin decimales, rutas absolutas, «~/» ni datos
        privados, y pasa la guarda de la procedencia. ``sellar_corrida`` escribe ``sha256.json`` y después el recibo,
        que cita su huella. Un recibo nunca se borra ni se sobrescribe (H4): al sellar de nuevo, el anterior pasa con
        sus mismos bytes a ``recibos/recibo_<n>.json``, que entra al nuevo ``sha256.json`` y el nuevo recibo cita."""
        huellas = {"ERA5L/era5land_200001.nc": {"sha256": SHA_A, "bytes": 1024}, "AP/scripts_modelo_1km/x.py": SHA_B}
        recibo = salidas.recibo_corrida(huellas, ENTORNO)
        self.assertEqual(recibo["esquema"], salidas.ESQUEMA_RECIBO)
        self.assertEqual(list(recibo["huellas"]), sorted(huellas))
        self.assertEqual(recibo["entorno"], ENTORNO)
        ceguera.vigilar_salida("recibo_corrida.json", recibo, clase="procedencia")
        self.assertEqual(salidas.recibo_corrida(dict(reversed(list(huellas.items()))), ENTORNO), recibo)
        malos = (
            ({}, ENTORNO), (huellas, {}),
            ({"ruta/relativa.json": SHA_A}, ENTORNO), ({"/tmp/x/y.json": SHA_A}, ENTORNO),
            ({"LOCAL/a/../b.json": SHA_A}, ENTORNO), ({"ERA5L/x.nc": SHA_A[:12]}, ENTORNO),
            ({"ERA5L/x.nc": {"sha256": SHA_A, "bytes": -1}}, ENTORNO),
            ({"ERA5L/x.nc": {"sha256": SHA_A, "bytes": 1.5}}, ENTORNO),
            ({"ERA5L/x.nc": {"sha256": SHA_A, "filas": 3}}, ENTORNO),
            ({"LOCAL/" + ARROBA + ".json": SHA_A}, ENTORNO),
            (huellas, {**ENTORNO, "segundos": 1.5}), (huellas, {**ENTORNO, "hilos": 1}),
            (huellas, {**ENTORNO, "interprete": "~/micromamba/envs/amb_v2/bin/python"}),
            (huellas, {**ENTORNO, "carpeta": "/tmp/corridas/x"}), (huellas, {**ENTORNO, "autor": ARROBA}),
            (huellas, {**ENTORNO, "fuente": USUARIO}),
        )
        for h, e in malos:
            with self.subTest(huellas=str(h)[:50], entorno=str(e)[-40:]), self.assertRaises(ValueError):
                salidas.recibo_corrida(h, e)
        rutas = entorno.rutas_sinteticas(self.tmp / "rutas")
        carpeta = entorno.carpeta_salida(rutas, "m34", ETIQUETA)
        prefijo = f"LOCAL/meteo_combinada/v1/{ETIQUETA}/"
        salidas.escribir("decision.json", {"ganador": "A"}, clase="metrica", raiz=carpeta)
        sha_1 = salidas.sellar_corrida(carpeta, huellas, ENTORNO, rutas=rutas)
        datos_1 = (carpeta / "recibo_corrida.json").read_bytes()
        self.assertEqual(sha_1, hashlib.sha256(datos_1).hexdigest())
        escrito = json.loads(datos_1)
        self.assertEqual(escrito["huellas"][prefijo + "sha256.json"],
                         hashlib.sha256((carpeta / "sha256.json").read_bytes()).hexdigest())
        self.assertEqual(datos_1, entorno.json_canonico(escrito))
        for propia in (prefijo + "sha256.json", prefijo + "recibos/recibo_1.json"):
            with self.subTest(propia=propia), self.assertRaises(ValueError):
                salidas.sellar_corrida(carpeta, {propia: SHA_A}, ENTORNO, rutas=rutas)
        with _sin_escribir(), self.assertRaises(SalidaProhibida):    # el recibo no se sobrescribe sin archivarlo
            salidas.escribir("recibo_corrida.json", salidas.recibo_corrida({**huellas, "ERA5L/otro.nc": SHA_A},
                                                                           ENTORNO), clase="procedencia", raiz=carpeta)
        self.assertEqual((carpeta / "recibo_corrida.json").read_bytes(), datos_1)
        # Volver a sellar: el recibo anterior pasa, con sus bytes, a recibos/recibo_1.json, y el sha256.json que cita a
        # recibos/recibo_1_sha256.json; el nuevo recibo cita los dos.
        inventario_1 = (carpeta / "sha256.json").read_bytes()
        sha_2 = salidas.sellar_corrida(carpeta, huellas, ENTORNO, rutas=rutas)
        self.assertNotEqual(sha_2, sha_1)
        self.assertEqual((carpeta / "recibos" / "recibo_1.json").read_bytes(), datos_1)
        self.assertEqual((carpeta / "recibos" / "recibo_1_sha256.json").read_bytes(), inventario_1)
        datos_2, inventario_2 = (carpeta / "recibo_corrida.json").read_bytes(), (carpeta / "sha256.json").read_bytes()
        nuevo = json.loads(datos_2)
        self.assertEqual(nuevo["huellas"][prefijo + "recibos/recibo_1.json"], sha_1)
        self.assertEqual(nuevo["huellas"][prefijo + "recibos/recibo_1_sha256.json"],
                         hashlib.sha256(inventario_1).hexdigest())
        inventario = json.loads(inventario_2)["archivos"]
        self.assertEqual(inventario["recibos/recibo_1.json"]["sha256"], sha_1)
        self.assertEqual(inventario["recibos/recibo_1_sha256.json"]["sha256"], hashlib.sha256(inventario_1).hexdigest())
        self.assertEqual(nuevo["huellas"][prefijo + "sha256.json"], hashlib.sha256(inventario_2).hexdigest())
        salidas.sellar_corrida(carpeta, huellas, ENTORNO, rutas=rutas)
        self.assertEqual((carpeta / "recibos" / "recibo_1.json").read_bytes(), datos_1)
        self.assertEqual((carpeta / "recibos" / "recibo_1_sha256.json").read_bytes(), inventario_1)
        self.assertEqual((carpeta / "recibos" / "recibo_2.json").read_bytes(), datos_2)
        self.assertEqual((carpeta / "recibos" / "recibo_2_sha256.json").read_bytes(), inventario_2)
        for n in (1, 2):
            self.assertEqual(salidas.fallas_de_sello_archivado(carpeta, n), [])
        with _sin_escribir():                                        # un archivo de recibos/ no cambia
            for nombre in ("recibos/recibo_1.json", "recibos/recibo_1_sha256.json"):
                with self.subTest(nombre=nombre), self.assertRaises(SalidaProhibida):
                    salidas.escribir(nombre, datos_2, clase="procedencia", raiz=carpeta)
        self.assertEqual(salidas.fallas_de_cierre(carpeta)[:1], ["falta politicas/politicas_meteo_v1.json"])

    def test_sello_archivado_verifica_la_carpeta_del_primer_sello(self):
        """SLD-10 (PED-6 de I20): sellar (M3-4), escribir más (M5: un archivo nuevo y una línea del avance) y volver
        a sellar. El recibo archivado y su ``sha256.json`` archivado verifican la carpeta tal como estaba al primer
        sello: el recibo cita la huella del inventario archivado y cada archivo que éste lista sigue con su huella
        (el avance, con la de lo que había); el recibo nuevo cita los dos y la corrida se publica con ellos. Un
        archivo que cambió, uno que falta o un avance recortado se informan; un par que no se verifica (un
        ``sha256.json`` cambiado después del recibo, un recibo que no lo cita, o sin ``sha256.json``) no se archiva."""
        rutas, carpeta = _fabricar_corrida(self.tmp / "m34")
        recibo_1, inventario_1 = (carpeta / "recibo_corrida.json").read_bytes(), (carpeta / "sha256.json").read_bytes()
        sellados_1 = json.loads(inventario_1)["archivos"]
        salidas.escribir("salud/civil/meteo_2001.parquet", _tabla(tipos.ESQUEMA_METEO_DIARIA, 1), clase="insumo",
                         esquema=tipos.ESQUEMA_METEO_DIARIA, raiz=carpeta)
        salidas.agregar_linea("avance.jsonl", {"unidad": "salud/civil/meteo_2001", "estado": "hecha"}, raiz=carpeta)
        salidas.sellar_corrida(carpeta, {"ERA5L/era5land_200001.nc": SHA_A}, ENTORNO, rutas=rutas)
        self.assertEqual((carpeta / "recibos" / "recibo_1.json").read_bytes(), recibo_1)
        self.assertEqual((carpeta / "recibos" / "recibo_1_sha256.json").read_bytes(), inventario_1)
        self.assertEqual(salidas.fallas_de_sello_archivado(carpeta, 1), [])
        alias = f"LOCAL/meteo_combinada/v1/{ETIQUETA}/"
        self.assertEqual(json.loads(recibo_1)["huellas"][alias + "sha256.json"],
                         hashlib.sha256(inventario_1).hexdigest())
        for relativo, valor in sellados_1.items():                     # lo que el primero listaba, con sus huellas
            datos = (carpeta / relativo).read_bytes()
            if relativo == "avance.jsonl":
                datos = datos[:valor["bytes"]]
            self.assertEqual(hashlib.sha256(datos).hexdigest(), valor["sha256"], relativo)
        nuevo = json.loads((carpeta / "recibo_corrida.json").read_bytes())
        self.assertEqual(nuevo["huellas"][alias + "recibos/recibo_1.json"], hashlib.sha256(recibo_1).hexdigest())
        self.assertEqual(nuevo["huellas"][alias + "recibos/recibo_1_sha256.json"],
                         hashlib.sha256(inventario_1).hexdigest())
        self.assertEqual(salidas.fallas_de_cierre(carpeta), [])
        publicadas = salidas.publicar_m5(carpeta, self.tmp / "ap")
        base = self.tmp / "ap" / salidas.SUBRUTA_PUBLICACION
        self.assertEqual(publicadas[-4:], [f"{salidas.SUBRUTA_PUBLICACION}/{n}" for n in (
            "recibos/recibo_1.json", "recibos/recibo_1_sha256.json", "sha256.json", "recibo_corrida.json")])
        self.assertEqual((base / "recibos" / "recibo_1_sha256.json").read_bytes(), inventario_1)
        # Lo que el sello archivado ya no verifica.
        (carpeta / "decision.json").write_bytes(b'{"ganador":"otro"}')
        (carpeta / "politicas" / "politicas_meteo_v1.json").unlink()
        avance = carpeta / "avance.jsonl"
        avance.write_bytes(avance.read_bytes()[:sellados_1["avance.jsonl"]["bytes"] - 2])
        fallas = salidas.fallas_de_sello_archivado(carpeta, 1)
        for esperada in ("cambió decision.json", "falta politicas/politicas_meteo_v1.json",
                         "cambió avance.jsonl (lo que había al sellar)"):
            self.assertIn(esperada, fallas)
        self.assertEqual(salidas.fallas_de_sello_archivado(carpeta, 2),
                         ["falta recibos/recibo_2.json", "falta recibos/recibo_2_sha256.json"])
        for malo in (0, -1, True, "1"):
            with self.subTest(n=malo), self.assertRaises(ValueError):
                salidas.fallas_de_sello_archivado(carpeta, malo)
        # Un par que no se verifica no se archiva, y nada cambia.
        def inventario_cambiado(c, r):
            salidas.escribir("insumos/nuevo.json", {"a": 1}, clase="insumo", raiz=c)
            salidas.escribir_sha256(c)                                 # un sha256.json que el recibo no cita

        def recibo_sin_cita(c, r):
            (c / "recibo_corrida.json").write_bytes(entorno.json_canonico(salidas.recibo_corrida(
                {"ERA5L/era5land_200001.nc": SHA_A}, ENTORNO)))

        def sin_inventario(c, r):
            (c / "sha256.json").unlink()

        for nombre, alterar in (("inventario", inventario_cambiado), ("cita", recibo_sin_cita),
                                ("sin_inventario", sin_inventario)):
            with self.subTest(caso=nombre):
                r, c = _fabricar_corrida(self.tmp / nombre)
                alterar(c, r)
                antes = (c / "recibo_corrida.json").read_bytes()
                with self.assertRaises(ValueError):
                    salidas.sellar_corrida(c, {"ERA5L/era5land_200001.nc": SHA_A}, ENTORNO, rutas=r)
                self.assertFalse((c / "recibos").exists())
                self.assertEqual((c / "recibo_corrida.json").read_bytes(), antes)

    def test_inventario_y_sha256_json(self):
        """SLD-9: ``sha256.json`` lista cada archivo regular de la carpeta con su sha256 y sus bytes, salvo
        ``sha256.json`` y el recibo de su raíz; un «.part» o un enlace detienen el inventario."""
        salidas.escribir("qc/resumen_qc.json", {"a": 1}, clase="resumen", raiz=self.raiz)
        salidas.escribir("m6/sha256.json", {"esquema": salidas.ESQUEMA_SHA256, "archivos": {}}, clase="procedencia",
                         raiz=self.raiz)
        salidas.agregar_linea("avance.jsonl", {"estado": "hecha"}, raiz=self.raiz)
        sha = salidas.escribir_sha256(self.raiz)
        contenido = json.loads((self.raiz / "sha256.json").read_bytes())
        self.assertEqual(sha, hashlib.sha256((self.raiz / "sha256.json").read_bytes()).hexdigest())
        self.assertEqual(contenido["esquema"], salidas.ESQUEMA_SHA256)
        self.assertEqual(sorted(contenido["archivos"]), ["avance.jsonl", "m6/sha256.json", "qc/resumen_qc.json"])
        datos = (self.raiz / "qc/resumen_qc.json").read_bytes()
        self.assertEqual(contenido["archivos"]["qc/resumen_qc.json"],
                         {"sha256": hashlib.sha256(datos).hexdigest(), "bytes": len(datos)})
        self.assertEqual(salidas.inventario(self.raiz), contenido["archivos"])
        (self.raiz / "qc" / "x.json.part").write_bytes(b"{")
        with self.assertRaises(ValueError):
            salidas.inventario(self.raiz)
        (self.raiz / "qc" / "x.json.part").unlink()
        os.symlink(self.raiz / "avance.jsonl", self.raiz / "enlace.jsonl")
        with self.assertRaises(ValueError):
            salidas.escribir_sha256(self.raiz)

    def test_corrida_en_curso_y_raiz_por_omision(self):
        """SLD-1 y H13: sin ``raiz`` y sin corrida en curso no se escribe; dentro de ``corrida_en_curso`` se escribe
        en la más interior de este hilo; otro hilo no hereda la corrida, pero mientras dure, ``publicar_m5`` se
        niega en todo el proceso; al salir, ya no hay corrida en curso."""
        with self.assertRaises(ValueError):
            salidas.escribir("x.json", {"a": 1}, clase="resumen")
        self.assertFalse(salidas.hay_corrida_en_curso())
        otra = _temporal(self)
        with salidas.corrida_en_curso(self.raiz) as c:
            self.assertEqual(c, self.raiz)
            self.assertTrue(salidas.hay_corrida_en_curso())
            salidas.escribir("a.json", {"a": 1}, clase="resumen")
            with salidas.corrida_en_curso(otra):
                salidas.escribir("b.json", {"b": 1}, clase="resumen")
                salidas.agregar_linea("avance.jsonl", {"estado": "hecha"})
            salidas.escribir("c.json", {"c": 1}, clase="resumen")
        self.assertFalse(salidas.hay_corrida_en_curso())
        self.assertEqual(_archivos(self.raiz), ["a.json", "c.json"])
        self.assertEqual(_archivos(otra), ["avance.jsonl", "b.json"])
        listo, fin, errores = threading.Event(), threading.Event(), []

        def en_otro_hilo():
            try:
                with salidas.corrida_en_curso(otra):
                    salidas.escribir("del_hilo.json", {"h": 1}, clase="resumen")
                    listo.set()
                    fin.wait(30)
            except Exception as e:      # noqa: BLE001 — se informa abajo
                errores.append(e)
                listo.set()

        hilo = threading.Thread(target=en_otro_hilo)
        hilo.start()
        try:
            self.assertTrue(listo.wait(30))
            self.assertTrue(salidas.hay_corrida_en_curso())
            with self.assertRaises(ValueError):                    # este hilo no hereda la corrida del otro
                salidas.escribir("x.json", {"a": 1}, clase="resumen")
            with self.assertRaises(RuntimeError):
                salidas.publicar_m5(self.raiz, self.tmp / "ap")
        finally:
            fin.set()
            hilo.join(30)
        self.assertEqual(errores, [])
        self.assertFalse(salidas.hay_corrida_en_curso())
        self.assertIn("del_hilo.json", _archivos(otra))
        with self.assertRaises(PermissionError):
            with salidas.corrida_en_curso(PROHIBIDA):
                pass
        self.assertFalse(salidas.hay_corrida_en_curso())

    def test_publicar_m5_paso_aparte(self):
        """Paso aparte (§8, SLD-11 a SLD-13): se niega dentro de una corrida; con una corrida cerrada copia byte a
        byte ``decision.json``, la política (H17), los resúmenes fuera de ``m6/`` y las huellas a
        ``config/meteorologia/meteo_combinada/v1/`` bajo ``destino_ap`` (aquí una carpeta temporal), con los sha256
        de ``sha256.json`` y sin rutas absolutas ni datos privados; deja en la corrida lo demás (métricas, productos,
        avance, ``m6/``); repetirla no escribe; una publicación interrumpida se completa; otra publicación, una
        carpeta de publicación que pasa por un enlace o un destino bajo la carpeta personal se niegan."""
        rutas, carpeta = _fabricar_corrida(self.tmp)
        destino_ap = self.tmp / "ap"
        base = destino_ap / salidas.SUBRUTA_PUBLICACION
        with salidas.corrida_en_curso(_temporal(self)), self.assertRaises(RuntimeError):
            salidas.publicar_m5(carpeta, destino_ap)
        self.assertFalse(destino_ap.exists())
        self.assertEqual(salidas.fallas_de_cierre(carpeta), [])
        publicadas = salidas.publicar_m5(carpeta, destino_ap)
        self.assertEqual(publicadas, [f"{salidas.SUBRUTA_PUBLICACION}/{n}" for n in PUBLICADAS])
        self.assertEqual(_archivos(base), sorted(PUBLICADAS))
        sellados = json.loads((carpeta / "sha256.json").read_bytes())["archivos"]
        for nombre in PUBLICADAS:
            datos = (base / nombre).read_bytes()
            self.assertEqual(datos, (carpeta / nombre).read_bytes())
            if nombre in sellados:
                self.assertEqual(hashlib.sha256(datos).hexdigest(), sellados[nombre]["sha256"])
            if nombre.endswith(".json"):
                texto = datos.decode("utf-8")
                self.assertTrue(entorno.sin_datos_privados(texto), nombre)
                self.assertNotIn(str(self.tmp), texto)
        self.assertIn("m6/decision_m6.json", sellados)
        self.assertFalse((base / "m6").exists())
        self.assertNotIn("validacion/puntajes.parquet", _archivos(base))
        self.assertTrue(all(not p.startswith("/") for p in publicadas))
        with mock.patch.object(salidas, "_escribir_publicacion", side_effect=AssertionError("no debía escribir")):
            self.assertEqual(salidas.publicar_m5(carpeta, destino_ap), publicadas)      # idéntica: no escribe
        (base / "sha256.json").unlink()                                                  # una publicación interrumpida
        (base / "qc" / "resumen_qc.json").unlink()
        self.assertEqual(salidas.publicar_m5(carpeta, destino_ap), publicadas)
        self.assertEqual(_archivos(base), sorted(PUBLICADAS))
        self.assertEqual((base / "sha256.json").read_bytes(), (carpeta / "sha256.json").read_bytes())
        (base / "extra.json").write_bytes(b"{}")
        with self.assertRaises(FileExistsError):
            salidas.publicar_m5(carpeta, destino_ap)
        (base / "extra.json").unlink()
        (base / "registro_m34.json").write_bytes(b'{"otra":"publicacion"}')
        with self.assertRaises(FileExistsError):
            salidas.publicar_m5(carpeta, destino_ap)
        with self.assertRaises(PermissionError):
            salidas.publicar_m5(carpeta, carpeta)
        # H10: la carpeta de publicación no pasa por un enlace (ni la de destino ni una subcarpeta).
        enlazado, lejos = self.tmp / "ap_enlazado", self.tmp / "lejos"
        (enlazado / "config" / "meteorologia" / "meteo_combinada").mkdir(parents=True)
        lejos.mkdir()
        os.symlink(lejos, enlazado / salidas.SUBRUTA_PUBLICACION)
        with self.assertRaises(PermissionError):
            salidas.publicar_m5(carpeta, enlazado)
        sub = self.tmp / "ap_sub" / salidas.SUBRUTA_PUBLICACION
        sub.mkdir(parents=True)
        os.symlink(lejos, sub / "qc")
        with self.assertRaises(PermissionError):
            salidas._escribir_publicacion(str(sub / "qc" / "resumen_qc.json"), b"{}", base=str(sub),
                                          base_fisica=os.path.realpath(sub))
        self.assertEqual(list(lejos.iterdir()), [])
        # H2: un destino bajo la carpeta personal se niega antes de cualquier escritura.
        casa = Path.home() / CASA_PRUEBA
        with RegistroAccesos([casa], bloquear=True, permitidas=[casa]) as reg, self.assertRaises(PermissionError):
            salidas.publicar_m5(carpeta, casa)
        self.assertEqual(reg.accesos, [])
        self.assertFalse(casa.exists())

    def test_publicar_m5_con_el_ap_real_exige_la_corrida_de_local(self):
        """H11: si ``destino_ap`` es el AP real, la corrida es una hija de LOCAL/meteo_combinada/v1, léxica y
        resuelta. Se prueba con un «AP real» y un LOCAL fabricados en la carpeta temporal (``entorno.rutas_reales``
        cambiado), nunca con el AP real."""
        _, otra = _fabricar_corrida(self.tmp / "otra")
        rutas, carpeta = _fabricar_corrida(self.tmp / "real")
        with mock.patch.object(entorno, "rutas_reales", return_value=rutas):
            self.assertTrue(salidas.es_ap_real(rutas.ap))
            self.assertFalse(salidas.es_ap_real(self.tmp / "ap"))
            with self.assertRaises(PermissionError):
                salidas.publicar_m5(otra, rutas.ap)
            self.assertFalse((rutas.ap / "config").exists())
            copia = rutas.salidas / "copias" / ETIQUETA
            shutil.copytree(carpeta, copia)
            with self.assertRaises(PermissionError):                  # no es hija directa de v1
                salidas.publicar_m5(copia, rutas.ap)
            publicadas = salidas.publicar_m5(carpeta, rutas.ap)
            self.assertEqual(_archivos(rutas.ap / salidas.SUBRUTA_PUBLICACION), sorted(PUBLICADAS))
            self.assertEqual(salidas.publicar_m5(otra, self.tmp / "ap"), publicadas)    # destino temporal: libre

    def test_publicar_m5_se_niega_con_una_corrida_no_cerrada(self):
        """SLD-11: no se publica una corrida sin sello, con «.part», con archivos que cambiaron, sobran o faltan
        respecto de ``sha256.json``, con ``sha256.json`` cambiado después del recibo, sin ``decision.json``, sin la
        política, sin los productos de M5, con un enlace, con otro nombre de carpeta, ni con un resumen que trae una
        ruta absoluta; y no se escribe nada en el destino."""
        def sin_sello(c):
            (c / "recibo_corrida.json").unlink()

        def parcial(c):
            (c / "qc" / "resumen_qc.json.part").write_bytes(b"{")

        def cambio(c):
            (c / "validacion" / "puntajes.parquet").write_bytes(b"otro")

        def sobra(c):
            (c / "insumos").mkdir()
            (c / "insumos" / "nuevo.json").write_bytes(b"{}")

        def falta(c):
            (c / "producto_01deg" / "meteo_200001.nc").unlink()

        def inventario_cambiado(c):
            ruta = c / "sha256.json"
            datos = json.loads(ruta.read_bytes())
            datos["archivos"].pop("registro_m34.json")
            ruta.write_bytes(entorno.json_canonico(datos))

        def enlace(c):
            os.symlink(c / "decision.json", c / "decision_enlace.json")

        def avance_tras_el_sello(c):
            with open(c / "avance.jsonl", "ab") as f:
                f.write(b'{"estado":"hecha","unidad":"tarde"}\n')

        casos = {
            "sin_sello": (sin_sello, "no está sellada"), "parcial": (parcial, "incompleta"),
            "cambio": (cambio, "cambió validacion/puntajes.parquet"), "sobra": (sobra, "sobra insumos/nuevo.json"),
            "falta": (falta, "falta producto_01deg/meteo_200001.nc"),
            "inventario": (inventario_cambiado, "sha256.json cambió después del recibo"),
            "enlace": (enlace, "enlace"), "avance": (avance_tras_el_sello, "cambió avance.jsonl"),
        }
        for nombre, (alterar, mensaje) in casos.items():
            with self.subTest(caso=nombre):
                base = self.tmp / nombre
                _, carpeta = _fabricar_corrida(base)
                alterar(carpeta)
                fallas = salidas.fallas_de_cierre(carpeta)
                self.assertTrue(any(mensaje in f for f in fallas), fallas)
                with self.assertRaises(PermissionError) as ctx:
                    salidas.publicar_m5(carpeta, base / "ap")
                self.assertNotIn(str(self.tmp), str(ctx.exception))
                self.assertFalse((base / "ap").exists())
        # Sin decision.json, sin la política ni salud/cronico/: la corrida se sella, pero no es una M5 cerrada.
        rutas, carpeta = _fabricar_corrida(self.tmp / "incompleta", sellar=False)
        (carpeta / "decision.json").unlink()
        (carpeta / "politicas" / "politicas_meteo_v1.json").unlink()
        shutil.rmtree(carpeta / "salud" / "cronico")
        salidas.sellar_corrida(carpeta, {"ERA5L/era5land_200001.nc": SHA_A}, ENTORNO, rutas=rutas)
        fallas = salidas.fallas_de_cierre(carpeta)
        for esperada in ("falta decision.json", "falta politicas/politicas_meteo_v1.json",
                         "faltan los productos de M5 en salud/cronico/"):
            self.assertIn(esperada, fallas)
        # Otro nombre de carpeta.
        copia = self.tmp / "incompleta" / "no_es_una_corrida"
        shutil.copytree(carpeta, copia)
        self.assertTrue(salidas.fallas_de_cierre(copia)[0].startswith("la carpeta no se llama"))
        # Un resumen con una ruta absoluta pasa la escritura (no es privada) pero no la publicación.
        rutas, carpeta = _fabricar_corrida(self.tmp / "absoluta", sellar=False)
        salidas.escribir("qc/resumen_qc.json", {"marcas": {}, "fuente": "/tmp/corridas/x"}, clase="resumen",
                         raiz=carpeta)
        salidas.sellar_corrida(carpeta, {"ERA5L/era5land_200001.nc": SHA_A}, ENTORNO, rutas=rutas)
        self.assertEqual(salidas.fallas_de_cierre(carpeta), [])
        with self.assertRaises(SalidaProhibida):
            salidas.publicar_m5(carpeta, self.tmp / "absoluta" / "ap")
        self.assertFalse((self.tmp / "absoluta" / "ap" / salidas.SUBRUTA_PUBLICACION / "decision.json").exists())


if __name__ == "__main__":
    unittest.main()
