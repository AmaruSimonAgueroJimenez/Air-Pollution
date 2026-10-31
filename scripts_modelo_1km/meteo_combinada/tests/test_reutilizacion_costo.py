"""Quince pruebas ligeras: sólo JSON sintético y biblioteca estándar.

Ejecución aislada, sin importar costo ni ejecutar mediciones o baterías:
``python -I -B scripts_modelo_1km/meteo_combinada/tests/test_reutilizacion_costo.py``
con el intérprete del entorno ``amb_v2``.
No demuestra equivalencia con la proyección histórica; eso queda al principal.
"""

import builtins
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


_RUTA_MODULO = Path(__file__).resolve().parents[1] / "reutilizacion_costo.py"
_SHA_V25 = "7771e830c526d8a0da93453e7e2d821896ba797147d14803969907ce5749589d"
_PUNTOS = ("qc", "pliegue", "tf", "m5", "grilla", "mes_real", "contencion")


def _importar():
    especificacion = importlib.util.spec_from_file_location("reutilizacion_costo_sintetica", _RUTA_MODULO)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


modulo = _importar()


def _umbrales(valor=36):
    # El nuevo texto vigente NO tiene que ser el del costo histórico.
    return SimpleNamespace(sha256_json="a" * 64, sha256_texto="b" * 64,
                           sha256_texto_vigente="d" * 64, a=lambda ident: valor)


def _fixture():
    """Resultado sintético de medir y su resumen; jamás se importa su productor real."""
    reloj = {"pared_s": 1.25, "cpu_s": 1.0}
    tamanos = {"residuos": 64, "campos_estaciones": 128, "filas_c": 32,
               "clima_a": 16, "clima_estaciones": 24, "cache_series": 8,
               "estaticos_celdas": 64, "filas_estaticos": 4,
               "clima_pixeles": 32, "filas_clima_pixeles": 12}
    carga = {"lecturas": 2, "propios": 1, "bruta": [1.2, 1.4], "ajena": [0.2, 0.4],
             "maxima_bruta": 1.4, "maxima_ajena": 0.4, "no_finitas": 0, "libre": True}
    puntos = {
        "qc": {"artefactos": 60, "estaciones": 5, "horas_dato": 48, "horas_estacion": 24,
               "filas_anchas": 48, "fabricar_s": 0.1, "estaciones_t": [dict(reloj)],
               "pared_s": 1.25, "cpu_s": 1.0, "ms_por_hora": 2.0,
               "memoria_antes_unidades_gb": 0.1, "memoria_unidades_gb": 0.2,
               "memoria_por_meses": {"6": 100, "12": 200},
               "anchas_tablas": {"codificar_s_por_fila": 0.001, "releer_s_por_fila": 0.002}},
        "pliegue": {"estaciones": 3, "horas": 48, "horas_dato": 48,
                    "filas_residuos": 48, "pliegues_p1": 2, "pliegues_p2": 2,
                    "prueba": 1, "prueba_p1": 2, "prueba_max_p1": 2, "entrenamiento": 2,
                    "selecciones": 3, "evaluaciones": 4, "residuos_s": 0.1,
                    "en_horas_residuos_s": 0.1, "clima_a_s": 0.1, "filas_c_s": 0.1,
                    "residuos_tablas": {"codificar_s_por_fila": 0.001},
                    "representatividad_s": 0.1, "pliegue": dict(reloj),
                    "pliegue_tibio": dict(reloj), "pliegue_p1": dict(reloj),
                    "por_estacion_prueba_s": 0.1, "memoria_tras_fabricar_gb": 0.1,
                    "bytes": dict(tamanos), "filas_campos_estaciones": {"guardado": 48, "entero": 144}},
        "tf": {"celdas": 4, "pixeles": 2, "fabricar_meses_s": 0.1,
               "pasadas": {pasada: {"armar": dict(reloj), "meses": [
                   {"mes": "201701", "horas": 24, "redes": 2, "finitud_e0": 1, **reloj},
                   {"mes": "201702", "horas": 24, "redes": 2, "finitud_e0": 1, **reloj}],
                   "configuraciones": 1, "variables": ["T"], "e0": 1,
                   "redes": {"historica": 3, "constante": 2, "entrenamiento": 3, "regla": "sintetica"}}
                   for pasada in ("ambiental", "salud")},
               "bytes": dict(tamanos), "horas_dato": 48, "estaciones": 3,
               "memoria_tras_fabricar_gb": 0.1},
        "m5": {"pixeles": 2, "celdas_salud": 4, "horas": 24,
               "pixeles_producto": {"base": dict(reloj)}, "pixeles_netcdf": dict(reloj),
               "salud": {uso: {"base": dict(reloj)} for uso in ("agudo", "cronico")},
               "lluvia": dict(reloj),
               "operador_salud": {"real": False, "celdas": 4, "bytes": 64,
                                  "estaticos_bytes": 32, **reloj},
               "bytes_netcdf": 512, "bytes": dict(tamanos), "horas_dato": 48, "estaciones": 3},
        "grilla": {"celdas": 4, "celdas_medidas": 4, "horas": 24, "lote": 2, "pixeles": 2,
                   "configuraciones": {"base": {"operador": dict(reloj), "operador_bytes": 64,
                       "variantes": {variante: dict(reloj) for variante in ("I", "D")}}},
                   "operador_mayor": {"bytes": 64, **reloj},
                   "bytes": dict(tamanos), "horas_dato": 48, "estaciones": 3},
        "mes_real": {"bytes": 4096, "pixeles": 2, "horas": 24,
                     "huella": dict(reloj), "lectura": dict(reloj),
                     "huellas_lecturas_reales": {"mes_sintetico": {"sha256": "c" * 64, "bytes": 4096}}},
        "contencion": {"procesos": 7, "solo_s": 1.0, "copias_s": [1.25] * 7,
                       "factor": 1.25, "memoria_pico_gb": 0.2, "celdas": 4},
    }
    for nombre in _PUNTOS[:-1]:
        puntos[nombre].update(total=dict(reloj), memoria_inicio_gb=0.1,
                              memoria_pico_gb=0.2, lecturas_reales=["geometria_sintetica"],
                              carga=copy.deepcopy(carga))
    escala = {"nombre": "fixture_sintetica", "estaciones": 3, "desde": "2016-01-01", "horas": 48,
              "cobertura": None, "lat_norte": -32.6, "lat_sur": -35.4,
              "qc_estaciones": 5, "qc_meses": 12, "celdas_tf": 4,
              "meses_tf": ["201701", "201702"], "mes_m5": "201707", "celdas_salud": 4,
              "celdas_grilla": 4, "lote_grilla": 2, "lotes_grilla": 2}
    originales = {"esquema": "meteo-combinada-costo-mediciones/1", "escala": escala,
                  "a_escala": True, "fallas_escala": [], "real_era5": True, "aislada": True,
                  "procesos": 7, "puntos": puntos,
                  "sistema": {"memoria_fisica_bytes": 16_000_000_000, "nucleos": 8},
                  "carga": {"inicio": 0.5, "inicio_libre": True, "maxima_ajena": 0.4, "libre": True}}
    # Inversión independiente de las tres transformaciones del productor.
    persistidos = {
        nombre: {("insumos_bytes" if clave == "bytes" else clave): copy.deepcopy(valor)
                 for clave, valor in punto.items()}
        for nombre, punto in puntos.items()
    }
    fases = {"m34": {"artefactos": 7, "seleccion_y_prediccion": 7, "tendencias_y_finitud": 7},
             "m5": {"representatividad": 7, "anual": 7}}
    resumen = {"esquema": "meteo-combinada-costo/1", "escala": copy.deepcopy(escala),
               "a_escala": True, "fallas_escala": [], "mes_real_leido": True, "aislada": True,
               "sistema": copy.deepcopy(originales["sistema"]), "carga": copy.deepcopy(originales["carga"]),
               "carga_referencia_historica": 2.0, "carga_es_excluyente": False,
               "mediciones": persistidos, "proyeccion": {"procesos": 7, "procesos_por_fase": fases,
                   "m34": {"pared_h": 12.0, "completa": True}, "sin_medir": {}},
               "veredicto": {"decide": False, "motivos": ["histórico sintético"], "notas": []},
               "recorte": "pendiente", "recorte_pendiente": True, "procesos_por_fase": fases,
               "umbral_recorte_h": 36.0, "lecturas": ["COS-1", "COS-2"],
               "umbrales": {"sha256_json": "a" * 64, "sha256_texto": "b" * 64,
                            "sha256_texto_vigente": _SHA_V25}}
    return originales, resumen


def _serializar(contenido):
    return json.dumps(contenido, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


class TestReutilizacionCosto(unittest.TestCase):
    def setUp(self):
        carpeta = tempfile.TemporaryDirectory(prefix="reutilizacion_costo_sintetica_")
        self.addCleanup(carpeta.cleanup)
        self.carpeta = Path(carpeta.name)
        self.ruta = self.carpeta / "costo_sintetico.json"
        self.originales, self.resumen = _fixture()
        self.U = _umbrales()

    def guardar(self, contenido=None, *, datos=None):
        if datos is None:
            datos = _serializar(self.resumen if contenido is None else contenido)
        self.ruta.write_bytes(datos)
        return hashlib.sha256(datos).hexdigest()

    def cargar(self, contenido=None, *, datos=None, umbrales=None):
        huella = self.guardar(contenido, datos=datos)
        return modulo.cargar(self.ruta, sha256=huella, umbrales=self.U if umbrales is None else umbrales)

    def test_verificacion_recibe_contenido_de_una_sola_lectura(self):
        huella = self.guardar()
        leidas = []
        def verificar(mediciones, original):
            self.assertEqual(original, self.resumen)
            self.assertEqual(mediciones, self.originales)
            leidas.append(True)
            self.ruta.unlink()
            self.ruta.symlink_to(self.carpeta / "no_abrir")
        modulo.cargar(self.ruta, sha256=huella, umbrales=self.U, verificar=verificar)
        self.assertEqual(leidas, [True])

    def test_error_de_verificacion_no_se_ignora(self):
        huella = self.guardar()
        def verificar(mediciones, original):
            raise ValueError("reproducción distinta")
        with self.assertRaisesRegex(ValueError, "reproducción distinta"):
            modulo.cargar(self.ruta, sha256=huella, umbrales=self.U, verificar=verificar)

    def test_01_reconstruccion_exacta_fixture_y_procedencia(self):
        datos = _serializar(self.resumen)
        mediciones, procedencia = self.cargar(datos=datos)
        self.assertEqual(mediciones, self.originales)
        self.assertEqual(set(mediciones["puntos"]), set(_PUNTOS))
        self.assertEqual(mediciones["puntos"]["mes_real"]["bytes"], 4096)
        self.assertIsInstance(mediciones["puntos"]["tf"]["bytes"], dict)
        self.assertEqual(mediciones["puntos"]["grilla"]["operador_mayor"]["bytes"], 64)
        self.assertEqual(procedencia["sha256"], hashlib.sha256(datos).hexdigest())
        self.assertEqual(procedencia["bytes"], len(datos))
        self.assertEqual(procedencia["alias"], "costo_m1_persistido")
        self.assertEqual(procedencia["umbrales_historicos"], self.resumen["umbrales"])
        self.assertNotIn(str(self.carpeta), json.dumps(procedencia))
        self.assertNotIn(self.ruta.name, json.dumps(procedencia))
        self.assertEqual(self.ruta.read_bytes(), datos)

    def test_02_procesos_medidos_no_salen_de_la_proyeccion(self):
        self.resumen["proyeccion"]["procesos"] = 3
        mediciones, procedencia = self.cargar()
        self.assertEqual(mediciones["procesos"], 7)
        self.assertEqual(procedencia["procesos_proyeccion_historica"], 3)

    def test_03_none_carga_no_libre_y_recorte_pendiente_se_conservan(self):
        self.resumen["carga"] = {"inicio": None, "inicio_libre": False,
                                 "maxima_ajena": None, "libre": False}
        carga = self.resumen["mediciones"]["qc"]["carga"]
        carga.update(bruta=[None, 5.0], ajena=[None, 4.0], libre=False, no_finitas=1)
        # Tampoco se inventa un cero/factor válido donde se persistió null.
        self.resumen["mediciones"]["contencion"]["factor"] = None
        mediciones, procedencia = self.cargar()
        self.assertEqual(mediciones["carga"], self.resumen["carga"])
        self.assertEqual(mediciones["puntos"]["qc"]["carga"], carga)
        self.assertIsNone(mediciones["puntos"]["contencion"]["factor"])
        self.assertTrue(procedencia["recorte_pendiente_historico"])
        self.assertEqual(procedencia["recorte_historico"], "pendiente")
        self.assertFalse(mediciones["carga"]["libre"])

    def test_04_no_aprueba_ni_reutiliza_veredicto_historico(self):
        self.resumen["umbrales"]["ruta_interna_no_publicable"] = str(self.carpeta)
        for decide in (True, False):
            with self.subTest(decide=decide):
                self.resumen["veredicto"]["decide"] = decide
                self.resumen["recorte"] = "mod11" if decide else "pendiente"
                self.resumen["recorte_pendiente"] = not decide
                mediciones, procedencia = self.cargar()
                self.assertNotIn("veredicto", mediciones)
                self.assertNotIn("proyeccion", mediciones)
                self.assertFalse(procedencia["nueva_medicion"])
                self.assertEqual(procedencia["comparacion_proyeccion_original"], "pendiente")
                self.assertIn("No es una medición nueva", procedencia["advertencia"])
                self.assertIn("suite", procedencia["advertencia"])
                self.assertNotIn(str(self.carpeta), json.dumps(procedencia))

    def test_05_sha_externo_obligatorio_y_canonico_antes_de_leer(self):
        with self.assertRaises(TypeError):
            modulo.cargar(self.ruta, umbrales=self.U)
        with self.assertRaises(TypeError):
            modulo.cargar(self.ruta, "a" * 64, umbrales=self.U)
        for sha in (None, "", "a" * 63, "a" * 65, "g" * 64, "A" * 64, " a" + "a" * 63,
                    "a" * 64 + "\n", 123, {"sha256": "a" * 64}):
            with self.subTest(sha=sha), mock.patch.object(modulo, "_leer_regular") as leer:
                with self.assertRaises(modulo.ErrorReutilizacionCosto):
                    modulo.cargar(self.ruta, sha256=sha, umbrales=self.U)
                leer.assert_not_called()

    def test_06_sha_incorrecto_rechaza_antes_de_interpretar_json(self):
        huella = self.guardar()
        incorrecta = ("0" if huella[0] != "0" else "1") + huella[1:]
        with mock.patch.object(modulo, "_json_estricto") as interpretar:
            with self.assertRaisesRegex(modulo.ErrorReutilizacionCosto, "no coincide"):
                modulo.cargar(self.ruta, sha256=incorrecta, umbrales=self.U)
            interpretar.assert_not_called()

    def test_07_solo_archivo_regular_sin_enlaces_fifo_o_zip(self):
        huella = self.guardar()
        enlace = self.carpeta / "enlace.json"
        enlace.symlink_to(self.ruta)
        fifo = self.carpeta / "tuberia.json"
        os.mkfifo(fifo)
        zip_falso = self.carpeta / "archivo.ZIP"
        zip_falso.write_bytes(self.ruta.read_bytes())
        for ruta in (enlace, fifo, self.carpeta, self.carpeta / "ausente.json", zip_falso):
            with self.subTest(tipo=ruta.name):
                with self.assertRaises(modulo.ErrorReutilizacionCosto) as error:
                    modulo.cargar(ruta, sha256=huella, umbrales=self.U)
                self.assertNotIn(str(self.carpeta), str(error.exception))

    def test_08_sustitucion_entre_lstat_y_open_no_bloquea_ni_sigue_enlace(self):
        original_lstat = Path.lstat
        for sustitucion in ("fifo", "enlace"):
            with self.subTest(sustitucion=sustitucion):
                if self.ruta.is_symlink() or self.ruta.exists():
                    self.ruta.unlink()
                huella = self.guardar()
                destino = self.carpeta / "destino.json"
                destino.write_bytes(self.ruta.read_bytes())

                def sustituir(ruta, *args, **kwargs):
                    estado = original_lstat(ruta, *args, **kwargs)
                    ruta.unlink()
                    if sustitucion == "fifo":
                        os.mkfifo(ruta)
                    else:
                        ruta.symlink_to(destino)
                    return estado

                with mock.patch.object(Path, "lstat", sustituir):
                    with self.assertRaises(modulo.ErrorReutilizacionCosto):
                        modulo.cargar(self.ruta, sha256=huella, umbrales=self.U)

    def test_09_json_estricto_incluye_duplicados_anidados_y_overflow(self):
        correcto = _serializar(self.resumen)
        casos = [b'{"esquema":1,"esquema":2}', b'{"a":{"x":1,"x":2}}',
                 b'{"a":NaN}', b'{"a":Infinity}', b'{"a":-Infinity}', b'{"a":1e9999}',
                 b'{"a":-1e9999}', b'{"a":1,}', b'[]', b'null', b'"texto"',
                 b'\xff', b'PK\x03\x04contenido_zip', b'\xef\xbb\xbf' + correcto, correcto + b'{}']
        for numero, datos in enumerate(casos):
            with self.subTest(caso=numero):
                with self.assertRaises(modulo.ErrorReutilizacionCosto):
                    self.cargar(datos=datos)

    def test_10_esquema_y_claves_principales_cerrados(self):
        for clave in self.resumen:
            with self.subTest(falta=clave):
                copia = copy.deepcopy(self.resumen)
                del copia[clave]
                with self.assertRaises(modulo.ErrorReutilizacionCosto):
                    self.cargar(copia)
        for cambio in ({"esquema": "meteo-combinada-costo/2"}, {"sha256": "e" * 64}):
            with self.subTest(cambio=cambio):
                copia = copy.deepcopy(self.resumen)
                copia.update(cambio)
                with self.assertRaises(modulo.ErrorReutilizacionCosto):
                    self.cargar(copia)
        for clave in ("escala", "sistema", "carga", "proyeccion", "procesos_por_fase", "veredicto"):
            for vacio in ({}, None, []):
                with self.subTest(clave=clave, vacio=vacio):
                    copia = copy.deepcopy(self.resumen)
                    copia[clave] = vacio
                    with self.assertRaises(modulo.ErrorReutilizacionCosto):
                        self.cargar(copia)

    def test_11_precondiciones_escala_aislamiento_mes_y_carga_no_excluyente(self):
        for clave in ("a_escala", "aislada", "mes_real_leido"):
            for valor in (False, 1, "True", None):
                with self.subTest(clave=clave, valor=valor):
                    copia = copy.deepcopy(self.resumen)
                    copia[clave] = valor
                    with self.assertRaises(modulo.ErrorReutilizacionCosto):
                        self.cargar(copia)
        for clave, valor in (("fallas_escala", ["falla"]), ("fallas_escala", {}),
                             ("carga_es_excluyente", True), ("carga_es_excluyente", 0),
                             ("carga_referencia_historica", 3), ("carga_referencia_historica", True)):
            with self.subTest(clave=clave, valor=valor):
                copia = copy.deepcopy(self.resumen)
                copia[clave] = valor
                with self.assertRaises(modulo.ErrorReutilizacionCosto):
                    self.cargar(copia)

    def test_12_huellas_m0_coinciden_con_u_y_texto_anterior_fijo(self):
        for clave in ("sha256_json", "sha256_texto", "sha256_texto_vigente"):
            for valor in ("e" * 64, "", None):
                with self.subTest(clave=clave, valor=valor):
                    copia = copy.deepcopy(self.resumen)
                    copia["umbrales"][clave] = valor
                    with self.assertRaises(modulo.ErrorReutilizacionCosto):
                        self.cargar(copia)
        for clave in ("sha256_json", "sha256_texto", "a"):
            with self.subTest(falta_en_u=clave):
                incompletos = _umbrales()
                delattr(incompletos, clave)
                with self.assertRaises(modulo.ErrorReutilizacionCosto):
                    self.cargar(umbrales=incompletos)
        self.assertNotEqual(self.U.sha256_texto_vigente, _SHA_V25)
        self.cargar()  # U nuevo, M0 idéntico, texto histórico v2.5: permitido.

    def test_13_umbral_recorte_exige_36_en_documento_y_u(self):
        for valor in (35, 37, True, "36", None):
            with self.subTest(documento=valor):
                copia = copy.deepcopy(self.resumen)
                copia["umbral_recorte_h"] = valor
                with self.assertRaises(modulo.ErrorReutilizacionCosto):
                    self.cargar(copia)
        for valor in (35, 37, True, "36", None, math.nan, math.inf):
            with self.subTest(u=valor):
                with self.assertRaises(modulo.ErrorReutilizacionCosto):
                    self.cargar(umbrales=_umbrales(valor))

    def test_14_siete_puntos_campos_obvios_y_alias_sin_colisiones(self):
        for nombre in _PUNTOS:
            for variante in ("falta", "vacio", "sin_medir", "pendiente", "bytes", "pid"):
                with self.subTest(punto=nombre, variante=variante):
                    copia = copy.deepcopy(self.resumen)
                    punto = copia["mediciones"][nombre]
                    if variante == "falta":
                        del copia["mediciones"][nombre]
                    elif variante == "vacio":
                        copia["mediciones"][nombre] = {}
                    elif variante in ("sin_medir", "pendiente"):
                        punto["estado"] = variante
                    else:
                        punto[variante] = 123
                    with self.assertRaises(modulo.ErrorReutilizacionCosto):
                        self.cargar(copia)
        copia = copy.deepcopy(self.resumen)
        copia["mediciones"]["otro"] = {"factor": 1.0}
        with self.assertRaises(modulo.ErrorReutilizacionCosto):
            self.cargar(copia)
        for nombre, campo in (("qc", "ms_por_hora"), ("pliegue", "insumos_bytes"),
                              ("tf", "pasadas"), ("m5", "operador_salud"),
                              ("grilla", "configuraciones"), ("mes_real", "lectura"),
                              ("contencion", "factor")):
            with self.subTest(falta_en_punto=nombre, campo=campo):
                copia = copy.deepcopy(self.resumen)
                del copia["mediciones"][nombre][campo]
                with self.assertRaises(modulo.ErrorReutilizacionCosto):
                    self.cargar(copia)
        for punto_procesos in ("contencion", "proyeccion"):
            for valor in (0, -1, True, "7", None):
                with self.subTest(procesos_en=punto_procesos, valor=valor):
                    copia = copy.deepcopy(self.resumen)
                    objeto = (copia["proyeccion"] if punto_procesos == "proyeccion"
                              else copia["mediciones"]["contencion"])
                    objeto["procesos"] = valor
                    with self.assertRaises(modulo.ErrorReutilizacionCosto):
                        self.cargar(copia)
        for nombre in ("pliegue", "tf", "m5", "grilla"):
            with self.subTest(insumos_no_diccionario=nombre):
                copia = copy.deepcopy(self.resumen)
                copia["mediciones"][nombre]["insumos_bytes"] = 4096
                with self.assertRaises(modulo.ErrorReutilizacionCosto):
                    self.cargar(copia)
        for valor in ({}, True, None):
            with self.subTest(bytes_mes=valor):
                copia = copy.deepcopy(self.resumen)
                copia["mediciones"]["mes_real"]["insumos_bytes"] = valor
                with self.assertRaises(modulo.ErrorReutilizacionCosto):
                    self.cargar(copia)

    def test_15_importacion_solo_stdlib_y_sin_apertura_de_datos(self):
        importar_original = builtins.__import__
        importados = []

        def solo_stdlib(nombre, *args, **kwargs):
            importados.append(nombre)
            if nombre.partition(".")[0] not in sys.stdlib_module_names:
                raise AssertionError(f"importación no permitida: {nombre}")
            return importar_original(nombre, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=solo_stdlib), \
                mock.patch("builtins.open", side_effect=AssertionError("lectura al importar")), \
                mock.patch("os.open", side_effect=AssertionError("lectura al importar")), \
                mock.patch.object(Path, "open", side_effect=AssertionError("lectura al importar")):
            nuevo = _importar()
        self.assertTrue(callable(nuevo.cargar))
        self.assertFalse(any("costo" in nombre or nombre.startswith(("numpy", "pytest", "pandas"))
                             for nombre in importados))


if __name__ == "__main__":
    unittest.main(verbosity=2)
