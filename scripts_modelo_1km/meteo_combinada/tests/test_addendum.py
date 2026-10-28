"""Pruebas de addendum.py (§10; MC-54, P44, A33, P122).

Dueño: I22 (ola 6; corregido tras la revisión independiente). Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
Leen, sin escribir, el código y los documentos del paquete, el código fijado y la clausura del reloj (sólo código) y
los textos y las decisiones anclados de APH; si falta el texto vigente, se omiten con el motivo y no se dan por
aprobadas. Lo que se escribe va a carpetas temporales. Ninguna prueba abre DMC, la meteorología SINCA real, NASADEM
real, GHS-POP real, la política publicada del reloj ni sus corridas.
"""
import sys

sys.dont_write_bytecode = True

import hashlib  # noqa: E402
import json  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import addendum, ceguera, constantes, entorno, fijados, orquestacion, salidas  # noqa: E402
from meteo_combinada import umbrales  # noqa: E402

_REALES = entorno.rutas_reales()
_SHA_FALSO = "ab" * 32
_SUB = "20261028T150000Z"
_M1 = f"LOCAL/meteo_combinada/v1/m1/{_SUB}"
_TOPE = int(constantes.valor("PROCESOS"))
# D59 (A39): los procesos por fase de un costo medido, con las fases de orquestacion.FASES_REPARTO
_PPF = {c: {f: _TOPE if i % 2 == 0 else _TOPE // 2 for i, f in enumerate(fases)}
        for c, fases in orquestacion.FASES_REPARTO.items()}


def _exigir_textos():
    ruta = Path(_REALES.aph) / umbrales.TEXTO_VIGENTE
    if not ruta.is_file():
        raise unittest.SkipTest(f"falta {ruta.name}; la prueba no se da por aprobada")


def _numero_ajeno() -> str:
    """Un número que no está en ninguna fuente (se arma al correr, para que no aparezca en este archivo)."""
    return f"{(2 ** 0.5) * 98765.4321:.6f}".replace(".", ",")


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


class _ConFuentes(unittest.TestCase):
    """Las fuentes reales, leídas una vez (sólo lectura)."""
    fuentes = lecturas = lista = ref = None

    @classmethod
    def setUpClass(cls):
        _exigir_textos()
        cls.fuentes = addendum.fuentes_documento(_REALES)
        cls.lecturas = addendum.lecturas_m1(_REALES, fuentes=cls.fuentes)
        cls.lista = addendum.lista_cerrada(_REALES)
        cls.ref = addendum.referencia(_REALES, fuentes=cls.fuentes)

    def _contenido(self, **cambios):
        args = {"lista": self.lista,
                "anexo_a2": {"ruta": f"{_M1}/anexo_a2.json", "sha256": _SHA_FALSO},
                "deriva": {"ruta": f"{_M1}/deriva_s6.json", "sha256": _SHA_FALSO, "pasa": {"B": False, "AB": True}},
                "recorte": None,
                "costo": {"ruta": f"{_M1}/costo_m1.json", "sha256": _SHA_FALSO, "recorte": "mod11",
                          "procesos_por_fase": _PPF},
                "lecturas": self.lecturas, "commits": {"ap": addendum.PENDIENTE, "aph": addendum.PENDIENTE},
                "bateria": {"carpeta": _M1, "resumen": {"ruta": f"{_M1}/resumen_m1.json", "sha256": _SHA_FALSO},
                            "aprobada": False}}
        args.update(cambios)
        return addendum.addendum_m1(args["lista"], args["anexo_a2"], args["deriva"], args["recorte"], args["costo"],
                                    args["lecturas"], args["commits"], fecha="2026-10-28", bateria=args["bateria"])


class PruebasAddendum(_ConFuentes):
    def test_lista_cerrada_por_alias(self):
        """{ruta por alias: sha256}, sin rutas de la carpeta de usuario: los textos, el JSON, el código del paquete y
        sus pruebas, los dos documentos del paquete (P-ADD-1), el código fijado y la clausura del reloj con sus
        huellas fijadas (ADD-1)."""
        lista = self.lista
        for a, s in lista.items():
            with self.subTest(alias=a):
                self.assertTrue(ceguera.es_ruta_por_alias(a) and a.split("/")[0] in ("AP", "APH"))
                self.assertTrue(entorno.sin_datos_privados(a))
                self.assertRegex(s, r"^[0-9a-f]{64}$")
        self.assertEqual(lista[f"APH/{umbrales.TEXTO_VIGENTE}"], umbrales.SHA_TEXTO_VIGENTE)
        self.assertEqual(lista[f"APH/{umbrales.JSON_M0}"], umbrales.SHA_JSON_M0)
        self.assertEqual(lista[f"APH/{umbrales.TEXTO_M0}"], umbrales.SHA_TEXTO_M0)
        for rel in addendum.DECISIONES:
            self.assertIn(f"APH/{rel}", lista)
        for repo, rel, sha, _ in fijados.HUELLAS_CODIGO:
            self.assertEqual(lista[f"{repo}/{rel}"], sha, rel)
        for m in fijados.ARCHIVOS_CLAUSURA:
            self.assertEqual(lista[f"AP/{fijados.RUTA_RELOJ}/{m}.py"], fijados.HUELLAS_CLAUSURA[m], m)
        paquete = Path(__file__).resolve().parents[1]
        codigo = [*paquete.glob("*.py"), *paquete.glob("tests/*.py")]
        for p in codigo:
            rel = p.relative_to(paquete).as_posix()
            self.assertEqual(lista[f"AP/{addendum.CARPETA_PAQUETE}/{rel}"], _sha(p), rel)
        for nombre in (addendum.COORDINACION, addendum.DISENO):
            self.assertEqual(lista[f"AP/{addendum.CARPETA_PAQUETE}/{nombre}"], _sha(paquete / nombre), nombre)
        self.assertEqual(list(lista), sorted(lista))
        self.assertEqual(sorted(lista), addendum.claves_lista_cerrada(_REALES))
        self.assertEqual(addendum.huellas_fijadas(), {a: lista[a] for a in addendum.huellas_fijadas()})

    def test_lista_cerrada_con_la_salida_de_la_bateria(self):
        """ADD-2: la salida de la batería entra con su huella del disco, en una sola subcarpeta de m1; otra huella,
        otro nombre, un archivo que falta, otra carpeta o dos subcarpetas no entran."""
        with tempfile.TemporaryDirectory() as tmp:
            sint = entorno.rutas_sinteticas(tmp)
            for sub in (_SUB, "otra"):
                carpeta = entorno.carpeta_salida(sint, "m1", sub)
                carpeta.mkdir(parents=True)
                (carpeta / "resumen_m1.json").write_text("{}\n", encoding="utf-8")
            m1 = entorno.carpeta_salida(sint, "m1", _SUB)
            bateria = {f"{_M1}/resumen_m1.json": _sha(m1 / "resumen_m1.json")}
            lista = addendum.lista_cerrada(_REALES, bateria=bateria, rutas_bateria=sint)
            self.assertEqual(lista[f"{_M1}/resumen_m1.json"], bateria[f"{_M1}/resumen_m1.json"])
            self.assertIn(f"{_M1}/sha256.json", addendum.claves_lista_cerrada(_REALES, carpeta_bateria_=_M1))
            sin_sub = "LOCAL/meteo_combinada/v1/m1"
            for malo in ({f"{_M1}/resumen_m1.json": _SHA_FALSO}, {f"{_M1}/otro.json": _SHA_FALSO},
                         {f"{_M1}/pruebas_m1.txt": _SHA_FALSO}, {f"{sin_sub}/resumen_m1.json": _SHA_FALSO},
                         {**bateria, f"{sin_sub}/otra/resumen_m1.json": bateria[f"{_M1}/resumen_m1.json"]}):
                with self.subTest(malo=sorted(malo)), self.assertRaises(addendum.ErrorAddendum):
                    addendum.lista_cerrada(_REALES, bateria=malo, rutas_bateria=sint)
            for malo in (sin_sub, f"{sin_sub}/../m2a", "LOCAL/meteo_combinada/v1/m2a/x"):
                with self.subTest(carpeta=malo), self.assertRaises(addendum.ErrorAddendum):
                    addendum.carpeta_bateria(malo)

    def test_lista_cerrada_exige_las_huellas_fijadas(self):
        """§9.3 del diseño: si el código fijado o la clausura no dan su huella fijada, la lista no se arma."""
        repo, rel, sha, origen = fijados.HUELLAS_CODIGO[0]
        otra = (repo, rel, _SHA_FALSO, origen)
        with mock.patch.object(fijados, "HUELLAS_CODIGO", (otra, *fijados.HUELLAS_CODIGO[1:])):
            with self.assertRaises(addendum.ErrorAddendum):
                addendum.lista_cerrada(_REALES)
        m = fijados.ARCHIVOS_CLAUSURA[0]
        with mock.patch.object(fijados, "HUELLAS_CLAUSURA", {**fijados.HUELLAS_CLAUSURA, m: _SHA_FALSO}):
            with self.assertRaises(addendum.ErrorAddendum):
                addendum.lista_cerrada(_REALES)

    def test_addendum_m1_campos(self):
        """Las claves de ADD-10 en su orden; lista, anexo A2, deriva, recorte, costo, lecturas y commits (MC-54, P44);
        las MC del diseño (D5), las decisiones de D1 en adelante, S6-1 a S6-6, las diferencias, las preguntas abiertas y
        las respondidas con su
        decisión y su texto (por la columna de la pregunta: P28 es D52), los acuerdos (marcados si se revisaron), la
        declaración sobre el C4 de RELOJ (P122), las fuentes con su huella y la batería con su subcarpeta."""
        c = self._contenido()
        self.assertEqual(list(c), list(addendum.CLAVES))
        self.assertEqual(c["esquema"], addendum.ESQUEMA)
        self.assertEqual(c["texto_vigente"], {"ruta": f"APH/{umbrales.TEXTO_VIGENTE}",
                                              "sha256": umbrales.SHA_TEXTO_VIGENTE})
        self.assertEqual(c["lista_cerrada"], self.lista)
        self.assertEqual(c["anexo_a2"]["sha256"], _SHA_FALSO)
        self.assertEqual(c["deriva"]["veredicto"], {"B": "falla", "AB": "pasa"})
        self.assertEqual([p["id"] for p in c["deriva"]["parametros"]], [f"S6-{n}" for n in range(1, 7)])
        self.assertEqual((c["recorte"], c["costo"]["veredicto"]), ("mod11", "mod11"))
        self.assertEqual(c["costo"], {"ruta": f"{_M1}/costo_m1.json", "sha256": _SHA_FALSO, "veredicto": "mod11",
                                      "procesos_por_fase": _PPF})
        self.assertEqual(c["commits"], {"ap": "pendiente", "aph": "pendiente"})
        ids = {(Path(x["modulo"]).name, x["id"]) for x in c["lecturas"]}
        for modulo, ident in (("orquestacion.py", "ORQ-1"), ("ceguera.py", "CEG-18"), ("salud.py", "SAL-13"),
                              ("verificar_meteo_combinada.py", "VER-1"), ("addendum.py", "ADD-1"),
                              ("test_integracion.py", "INT-3"), ("addendum.py", "P-ADD-1"),
                              ("verificar_meteo_combinada.py", "P-VER-5"), ("verificar_meteo_combinada.py", "PED-5")):
            self.assertIn((modulo, ident), ids)
        # las preguntas en prosa («Preguntas para el autor (P-XXX-n…): P-XXX-1 …; P-XXX-2 …»)
        for modulo, ident in (("orquestacion.py", "P-ORQ-1"), ("costo.py", "P-COS-1")):
            self.assertIn((modulo, ident), ids)
        prosa = next(x for x in c["lecturas"] if x["id"] == "P-ORQ-1")
        self.assertEqual(prosa["tipo"], "pregunta")
        self.assertTrue(prosa["texto"].startswith("P-ORQ-1"))
        # las MC-n del diseño (D5), con su marca
        mc = {x["id"]: x for x in c["lecturas_diseno"]}
        self.assertTrue({f"MC-{n:02d}" for n in range(1, 55)} <= set(mc))
        self.assertEqual(mc["MC-09"]["marca"], "D")
        self.assertTrue(all(x["seccion"].startswith("7") for x in c["lecturas_diseno"]))
        ids_d = [d["id"] for d in c["decisiones"]]
        self.assertEqual(ids_d, [f"D{n}" for n in range(1, len(ids_d) + 1)])
        self.assertIn("D61", ids_d)
        numeros = [int(d["numero"]) for d in c["diferencias"] if d["numero"]]
        self.assertTrue(set(range(1, 34)) <= set(numeros), "faltan diferencias con el diseño")
        abiertas = [p["id"] for p in c["preguntas_abiertas"]]
        resueltas = {p["id"]: p for p in c["preguntas_respondidas"]}
        coordinacion = self.fuentes[f"AP/{addendum.CARPETA_PAQUETE}/{addendum.COORDINACION}"]
        todas = {p["id"] for p in addendum.secciones_coordinacion(coordinacion)["preguntas"]}
        self.assertEqual(set(abiertas) | set(resueltas), todas)
        self.assertFalse(set(abiertas) & set(resueltas))
        self.assertTrue({f"P{n}" for n in range(1, 146)} <= set(resueltas), "D58, D59 y D60 cierran P79 a P145")
        for p, d in (("P1", "D11"), ("P28", "D52"), ("P33", "D43"), ("P41", "D53"), ("P47", "D56"),
                     ("P78", "D53"), ("P79", "D58"), ("P122", "D60"), ("P145", "D59")):
            self.assertEqual(resueltas[p]["decision"], d, p)
        self.assertTrue(resueltas["P28"]["texto"].startswith("**P28."))
        acuerdos = {i for a in c["acuerdos"] for i in a["ids"]}
        self.assertTrue({f"A{n}" for n in range(1, 34)} <= acuerdos)
        self.assertTrue(any(a["revisado"] for a in c["acuerdos"]))
        self.assertTrue(all(a["revisado"] == ("revisad" in a["seccion"].casefold()) for a in c["acuerdos"]))
        self.assertEqual(c["declaracion_c4_reloj"], dict(addendum.DECLARACION_C4))
        for clave, parte in (("hecho", "4e16614"), ("item_prospectivo", "ítem prospectivo de §1.9"),
                             ("olas", "olas 0 a 3"), ("olas", "Después: las olas 4 a 6"),
                             ("lectura_propuesta", "post_hoc = true"), ("pregunta", "P122")):
            self.assertIn(parte, c["declaracion_c4_reloj"][clave])
        fuentes = {f["ruta"]: f["sha256"] for f in c["fuentes"]}
        paquete = Path(__file__).resolve().parents[1]
        for nombre in (addendum.COORDINACION, addendum.DISENO):
            self.assertEqual(fuentes[f"AP/{addendum.CARPETA_PAQUETE}/{nombre}"], _sha(paquete / nombre))
        for rel in addendum.DECISIONES:
            self.assertEqual(fuentes[f"APH/{rel}"], _sha(Path(_REALES.aph) / rel))
        self.assertEqual(c["bateria"], {"carpeta": _M1, "resumen": {"ruta": f"{_M1}/resumen_m1.json",
                                                                    "sha256": _SHA_FALSO}, "aprobada": False})

    def test_addendum_pasa_la_guarda_del_documento(self):
        """ADD-8 (CEG-18): el JSON y el .md pasan ``vigilar_salida`` como documento y cita la huella del texto; un
        número que no sale del texto ni de las fuentes los hace fallar; se escriben por ``salidas``; los títulos no
        llevan rangos fijos."""
        c = self._contenido()
        ceguera.vigilar_salida(addendum.NOMBRE_JSON, c, clase="documento", referencia=self.ref)
        md = addendum.addendum_md(c)
        self.assertIn(umbrales.SHA_TEXTO_VIGENTE, md.splitlines()[2])
        ceguera.vigilar_salida(addendum.NOMBRE_MD, md, clase="documento", referencia=self.ref)
        for parte in ("## Lista cerrada", "## Lecturas de implementación", "## Lecturas del diseño",
                      "## Decisiones del autor", "## Preguntas abiertas", "## Preguntas ya respondidas",
                      "## Acuerdos de interfaces", "## Declaración sobre el C4 de RELOJ", "B falla, AB pasa", "P122",
                      "procesos por fase:", addendum.DECLARACION_D59):
            self.assertIn(parte, md)
        for titulo in (ln for ln in md.splitlines() if ln.startswith("## ")):
            self.assertNotRegex(titulo, r"\b[ADP]\d+-[ADP]?\d+\b", "un título con un rango fijo")
        numero = _numero_ajeno()
        malo = json.loads(json.dumps(c))
        malo["diferencias"][0]["texto"] += f" Medido: {numero} K."
        with self.assertRaises(ceguera.SalidaProhibida):
            ceguera.vigilar_salida(addendum.NOMBRE_JSON, malo, clase="documento", referencia=self.ref)
        with self.assertRaises(ceguera.SalidaProhibida):
            ceguera.vigilar_salida(addendum.NOMBRE_MD, md + f"\nTotal medido: {numero} horas.\n", clase="documento",
                                   referencia=self.ref)
        with tempfile.TemporaryDirectory() as tmp:
            m1 = entorno.carpeta_salida(entorno.rutas_sinteticas(tmp), "m1", _SUB)
            sha = salidas.escribir(addendum.NOMBRE_JSON, c, clase="documento", raiz=m1, referencia=self.ref)
            self.assertEqual(_sha(m1 / addendum.NOMBRE_JSON), sha)
            salidas.escribir(addendum.NOMBRE_MD, md, clase="documento", raiz=m1, referencia=self.ref)
            self.assertEqual(ceguera.clase_de_ruta(f"{_M1}/{addendum.NOMBRE_JSON}"), "documento")

    def test_lo_que_falta_queda_pendiente(self):
        """ADD-6 y ADD-7: sin anexo, deriva, recorte, costo ni batería, todo «pendiente»; el recorte del costo manda;
        una forma mala no se acepta."""
        c = self._contenido(anexo_a2=None, deriva=None, costo=None, bateria=None)
        self.assertEqual((c["anexo_a2"], c["recorte"], c["costo"], c["deriva"]["estado"], c["bateria"]),
                         ("pendiente",) * 5)
        self.assertEqual(len(c["deriva"]["parametros"]), 6)
        ceguera.vigilar_salida(addendum.NOMBRE_JSON, c, clase="documento", referencia=self.ref)
        self.assertEqual(self._contenido(recorte="mod11")["recorte"], "mod11")
        resumen = {"ruta": f"{_M1}/resumen_m1.json", "sha256": _SHA_FALSO}
        for cambios in ({"recorte": "mod23"},                                  # distinto del costo
                        {"commits": {"ap": "abc", "aph": addendum.PENDIENTE}},
                        {"commits": {"ap": addendum.PENDIENTE}},
                        {"deriva": {"ruta": f"{_M1}/deriva_s6.json", "sha256": _SHA_FALSO, "pasa": {"B": False}}},
                        {"anexo_a2": {"ruta": "/tmp/anexo_a2.json", "sha256": _SHA_FALSO}},
                        {"bateria": {"carpeta": _M1, "resumen": resumen}},
                        {"bateria": {"carpeta": "LOCAL/meteo_combinada/v1/m1", "resumen": resumen, "aprobada": True}},
                        {"lista": {k: v for k, v in self.lista.items() if "PROTOCOLO_METEO_COMBINADA_v2.3" not in k}}):
            with self.subTest(cambios=list(cambios)), self.assertRaises(addendum.ErrorAddendum):
                self._contenido(**cambios)
        self.assertEqual(addendum.deriva_de_veredicto(addendum.veredicto_deriva({"B": True, "AB": False})),
                         {"B": True, "AB": False})

    def test_procesos_por_fase(self):
        """ADD-12 (D59; A39): el costo del addendum es {ruta, sha256, veredicto, procesos_por_fase}, con cada n un
        entero (no bool) de 1 a PROCESOS (todos pasan la guarda del documento); el .md los muestra en la línea del costo
        con la declaración de D59; addendum valida la forma y no los nombres; con el recorte del costo «pendiente», el
        recorte y el costo quedan «pendiente», sin error."""
        costo = {"ruta": f"{_M1}/costo_m1.json", "sha256": _SHA_FALSO, "recorte": "mod11"}
        for n in range(1, _TOPE + 1):
            ppf = {k: {f: n for f in fs} for k, fs in orquestacion.FASES_REPARTO.items()}
            c = self._contenido(costo={**costo, "procesos_por_fase": ppf})
            self.assertEqual(c["costo"]["procesos_por_fase"], ppf)
            ceguera.vigilar_salida(addendum.NOMBRE_JSON, c, clase="documento", referencia=self.ref)
            md = addendum.addendum_md(c)
            ceguera.vigilar_salida(addendum.NOMBRE_MD, md, clase="documento", referencia=self.ref)
            linea = next(ln for ln in md.splitlines() if ln.startswith("- Costo: "))
            self.assertTrue(all(f"{f} {n}" in linea for fs in orquestacion.FASES_REPARTO.values() for f in fs))
        self.assertIn(addendum.DECLARACION_D59, md)
        # la pared que se vuelve a proyectar decide el recorte de §4.9 (§8), así que D59 no cambia bits sólo por sí
        # mismo (P147)
        for parte in ("por sí mismo (S9)", "§4.9", "desde la proyección", "costo_m1.json", "P147", "P146"):
            self.assertIn(parte, addendum.DECLARACION_D59)
        self.assertNotIn("sólo la duración", addendum.DECLARACION_D59)
        primera = orquestacion.FASES_REPARTO["m34"][0]
        for malo in (None, {}, [], {"m34": {}}, {"m 34": {primera: 1}}, {"m34": {primera: 0}},
                     {"m34": {primera: _TOPE + 1}}, {"m34": {primera: True}}, {"m34": {primera: 1.0}},
                     {"m34": {primera: "1"}}, {"m34": [1]}):
            with self.subTest(procesos=repr(malo)), self.assertRaises(addendum.ErrorAddendum):
                self._contenido(costo={**costo, "procesos_por_fase": malo})
        otra = {"m6": {"anual": 1}}                      # la forma, no los nombres: los coteja verificar
        self.assertEqual(self._contenido(costo={**costo, "procesos_por_fase": otra})["costo"]["procesos_por_fase"], otra)
        # costo medido con el recorte «pendiente» (una fase que no cabe ni con 1): recorte y costo «pendiente»
        pendiente = {**costo, "recorte": addendum.PENDIENTE, "procesos_por_fase": {"m34": {primera: 0}}}
        c = self._contenido(costo=pendiente)
        self.assertEqual((c["recorte"], c["costo"]), (addendum.PENDIENTE, addendum.PENDIENTE))
        self.assertEqual(self._contenido(costo=pendiente, recorte=addendum.PENDIENTE)["recorte"], addendum.PENDIENTE)
        ceguera.vigilar_salida(addendum.NOMBRE_JSON, c, clase="documento", referencia=self.ref)
        self.assertIn("- Costo: pendiente.", addendum.addendum_md(c))
        self.assertEqual(self._contenido(costo=None, recorte=addendum.PENDIENTE)["recorte"], addendum.PENDIENTE)
        for cambios in ({"costo": pendiente, "recorte": "mod11"}, {"costo": {**costo, "recorte": "otro"}},
                        {"costo": {k: v for k, v in costo.items() if k != "sha256"}}):
            with self.subTest(cambios=repr(cambios)[:60]), self.assertRaises(addendum.ErrorAddendum):
                self._contenido(**cambios)

    def test_anexo_a2_del_texto_vigente(self):
        """A32: ``anexo_a2.json`` sale de ``constantes.anexo_a2`` sobre el v2.3 y pasa la guarda del documento."""
        a2 = addendum.anexo_a2(_REALES)
        self.assertEqual(a2["texto_sha256"], umbrales.SHA_TEXTO_VIGENTE)
        ceguera.vigilar_salida("anexo_a2.json", a2, clase="documento", referencia=self.ref)


class PruebasExtraccion(unittest.TestCase):
    """ADD-3 a ADD-5 y ADD-9 con textos hechos a mano."""

    def test_lecturas_del_encabezado(self):
        fuente = ('"""Encabezado.\n\nLecturas propias (XYZ-n):\n- XYZ-1. **Una.** Primera línea\n  sigue aquí\n'
                  '  - una viñeta interna\n- XYZ-2. Dos.\n  - XYZ-9. sangrada: es parte de la XYZ-2\nTexto suelto.\n'
                  '- P-XYZ-1. Una pregunta.\n- PED-4 (I1). Un pedido.\n- Otra viñeta sin identificador.\n'
                  'Preguntas para el autor (P-QRS-n; rige la más estricta): P-QRS-1, la primera\n'
                  'con su continuación; P-QRS-2, la segunda.\nPedidos: ninguno.\n"""\n'
                  'x = 1\n"""- XYZ-3. no es el encabezado"""\n')
        lecturas = addendum.extraer_lecturas({"AP/scripts_modelo_1km/meteo_combinada/x.py": fuente,
                                              "AP/scripts_modelo_1km/meteo_combinada/x.md": "- XYZ-4. no"})
        self.assertEqual([(x["id"], x["tipo"]) for x in lecturas],
                         [("XYZ-1", "lectura"), ("XYZ-2", "lectura"), ("P-XYZ-1", "pregunta"), ("PED-4", "pedido"),
                          ("P-QRS-1", "pregunta"), ("P-QRS-2", "pregunta")])
        self.assertEqual(lecturas[0]["texto"], "XYZ-1. **Una.** Primera línea\nsigue aquí\n- una viñeta interna")
        self.assertIn("XYZ-9", lecturas[1]["texto"])
        self.assertEqual(lecturas[4]["texto"], "P-QRS-1, la primera con su continuación")
        self.assertEqual(lecturas[5]["texto"], "P-QRS-2, la segunda.")

    def test_lecturas_del_diseno(self):
        """ADD-9 (D5): las viñetas «- **MC-nn …**» de las secciones de §7, con su marca [E], [D] o [M]."""
        diseno = ("## 6. Otra\n- **MC-90 [D] fuera de §7.**\n## 7. Lecturas\n### 7.1 Datos\n"
                  "- **MC-01 [E] Una.** texto\n  sigue\n- **MC-02.** sin marca\n### 7.2 Más\n"
                  "- **MC-03 [D, revisada] Otra.**\n## 8. Después\n- **MC-91 [M] fuera.**\n")
        mc = addendum.extraer_mc(diseno)
        self.assertEqual([(x["id"], x["marca"], x["seccion"]) for x in mc],
                         [("MC-01", "E", "7.1 Datos"), ("MC-02", None, "7.1 Datos"), ("MC-03", "D", "7.2 Más")])
        self.assertEqual(mc[0]["texto"], "**MC-01 [E] Una.** texto\nsigue")
        with self.assertRaises(addendum.ErrorAddendum):
            addendum.extraer_mc("## 7. Lecturas\nnada\n")

    def test_decisiones_y_preguntas_respondidas(self):
        """ADD-4: la pregunta se toma de la segunda columna (no de una mención en la decisión); «Pn queda descartada»
        cuenta en cualquier columna; si dos filas nombran la misma pregunta, rige la última."""
        a = ("| D | Pregunta |\n|---|---|\n| D1 | P1: una | «Sí», como en P9 |\n"
             "| D2 | P10 a P12, en bloque | Sí; P78 queda descartada |\n")
        b = "- **D1:** una mención, no una decisión.\n| D3 | sin pregunta | — |\n| D4 | P11, de nuevo | otra |\n"
        dec = addendum.decisiones_del_autor({"APH/a.md": a, "APH/b.md": b})
        self.assertEqual([d["id"] for d in dec], ["D1", "D2", "D3", "D4"])
        self.assertEqual(dec[0]["texto"], "D1 | P1: una | «Sí», como en P9")
        self.assertEqual(dec[0]["pregunta"], "P1: una")
        self.assertEqual(addendum.respondidas(dec),
                         {"P1": "D1", "P10": "D2", "P11": "D4", "P12": "D2", "P78": "D2"})
        with self.assertRaises(addendum.ErrorAddendum):
            addendum.decisiones_del_autor({"APH/a.md": a, "APH/b.md": "| D4 | hueco |\n"})
        with self.assertRaises(addendum.ErrorAddendum):
            addendum.decisiones_del_autor({"APH/a.md": a, "APH/b.md": "| D2 | repetida |\n| D3 | x |\n"})

    def test_secciones_de_la_coordinacion(self):
        texto = ("## Ola 1 cerrada\n\n**Diferencias con el diseño que se anotan** (nota):\n- NUM-8: una.\n"
                 "- SIN-9: dos,\n  que sigue.\n\n**Pendientes:**\n- no es una diferencia.\n\n"
                 "## Ola 2\n### Acuerdos de interfaces\n- **A1. Uno.** texto\n- **A2 y A3.** dos y tres\n"
                 "### Diferencias con el diseño (para el addendum de M1)\n1. **Primera** x\n- **11.** once\n"
                 "- sin número\n### Preguntas para el autor (ola 2)\n**Salud (I18).**\n- **P5. Una.** Cita: x.\n"
                 "- **P6. Otra.**\n### D15: los parámetros de S6, fijados antes de correrla\n- **S6-1. La red.** 20\n"
                 "### Preguntas para el autor (cierre)\n- **P5. Una, revisada.**\n"
                 "### Acuerdos revisados en la ola 3\n- **A2.** dos, revisado\n")
        s = addendum.secciones_coordinacion(texto)
        self.assertEqual([(d["numero"], d["texto"][:6]) for d in s["diferencias"]],
                         [(None, "NUM-8:"), (None, "SIN-9:"), ("1", "1. **P"), ("11", "**11.*"), (None, "sin nú")])
        self.assertEqual(s["diferencias"][1]["texto"], "SIN-9: dos,\nque sigue.")
        self.assertEqual([p["id"] for p in s["preguntas"]], ["P5", "P6", "P5"])
        self.assertEqual([(a["ids"], a["revisado"]) for a in s["acuerdos"]],
                         [(["A1"], False), (["A2", "A3"], False), (["A2"], True)])
        self.assertEqual([p["id"] for p in s["parametros_s6"]], ["S6-1"])
        self.assertEqual(s["acuerdos"][0]["seccion"], "Ola 2 › Acuerdos de interfaces")
        with self.assertRaises(addendum.ErrorAddendum):                  # A2 sin A1
            addendum.secciones_coordinacion(texto.replace("- **A1. Uno.** texto\n", ""))


if __name__ == "__main__":
    unittest.main()
