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

import gzip  # noqa: E402
import hashlib  # noqa: E402
import importlib.util  # noqa: E402
import subprocess  # noqa: E402
import json  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import addendum, ceguera, constantes, entorno, fijados, orquestacion, salidas  # noqa: E402
from meteo_combinada import umbrales, verificar_meteo_combinada as V  # noqa: E402

_REALES = entorno.rutas_reales()
_SHA_FALSO = "ab" * 32
_SUB = "20261028T150000Z"
_M1 = f"LOCAL/meteo_combinada/v1/m1/{_SUB}"
_TOPE = int(constantes.valor("PROCESOS"))
# D59 (A39): los procesos por fase de un costo medido, con las fases de orquestacion.FASES_REPARTO
_PPF = {c: {f: _TOPE if i % 2 == 0 else _TOPE // 2 for i, f in enumerate(fases)}
        for c, fases in orquestacion.FASES_REPARTO.items()}


def _exigir_textos():
    for rel in addendum.TEXTOS_PRODUCTO:
        ruta = Path(_REALES.aph) / rel
        if not ruta.is_file():
            raise unittest.SkipTest(f"falta {ruta.name}; la prueba no se da por aprobada")


def _numero_ajeno() -> str:
    """Un número que no está en ninguna fuente (se arma al correr, para que no aparezca en este archivo)."""
    return f"{(2 ** 0.5) * 98765.4321:.6f}".replace(".", ",")


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _armar_contenido(lista, lecturas, /, **cambios):
    args = {"lista": lista,
            "anexo_a2": {"ruta": f"{_M1}/anexo_a2.json", "sha256": _SHA_FALSO},
            "deriva": {"ruta": f"{_M1}/deriva_s6.json", "sha256": _SHA_FALSO, "pasa": {"B": False, "AB": True}},
            "recorte": None,
            "costo": {"ruta": f"{_M1}/costo_m1.json", "sha256": _SHA_FALSO, "recorte": "mod11",
                      "procesos_por_fase": _PPF},
            "lecturas": lecturas, "commits": {"ap": addendum.PENDIENTE, "aph": addendum.PENDIENTE},
            "bateria": {"carpeta": _M1, "resumen": {"ruta": f"{_M1}/resumen_m1.json", "sha256": _SHA_FALSO},
                        "aprobada": False}}
    args.update(cambios)
    return addendum.addendum_m1(args["lista"], args["anexo_a2"], args["deriva"], args["recorte"], args["costo"],
                                args["lecturas"], args["commits"], fecha="2026-10-28", bateria=args["bateria"])


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
        return _armar_contenido(self.lista, self.lecturas, **cambios)


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
        self.assertEqual(lista[f"APH/{addendum.TEXTO_V2_4}"], addendum.SHA_TEXTO_V2_4)
        self.assertEqual(lista[f"APH/{addendum.TEXTO_V2_5}"], addendum.SHA_TEXTO_V2_5)
        for rel in (f"{addendum.CARPETA_PRODUCTO}/enmienda4/ENMIENDA_4.md",
                    f"{addendum.CARPETA_PRODUCTO}/enmienda4/generar_v2_5.py",
                    f"{addendum.CARPETA_PRODUCTO}/enmienda4/decisiones_autor_20261031.md",
                    f"{addendum.CARPETA_PRODUCTO}/enmienda5/ENMIENDA_5.md",
                    f"{addendum.CARPETA_PRODUCTO}/enmienda5/generar_v2_6.py",
                    f"{addendum.CARPETA_PRODUCTO}/enmienda5/decisiones_autor_20261031.md"):
            self.assertIn(f"APH/{rel}", addendum.claves_lista_cerrada(_REALES))
            self.assertEqual(lista[f"APH/{rel}"], _sha(Path(_REALES.aph) / rel))
        self.assertEqual(lista[f"APH/{umbrales.JSON_M0}"], umbrales.SHA_JSON_M0)
        self.assertEqual(lista[f"APH/{umbrales.TEXTO_M0}"], umbrales.SHA_TEXTO_M0)
        for rel in addendum.DECISIONES:
            self.assertIn(f"APH/{rel}", lista)
        borrador = f"APH/{addendum.CARPETA_PRODUCTO}/enmienda3_borrador/BORRADOR_ENMIENDA_3_PROCESOS.md"
        self.assertIn(borrador, addendum.claves_lista_cerrada(_REALES))
        self.assertEqual(lista[borrador], "3f38021d5a110ae450b79aa6c9aa16652be35f7025ce735c7a8a1cebb3bfed90")
        nota = f"APH/{addendum.CARPETA_PRODUCTO}/enmienda3/NOTA_FIRMAS_RECIBOS.md"
        self.assertIn(nota, addendum.claves_lista_cerrada(_REALES))
        self.assertEqual(lista[nota], "3fadd2244b83e77414c0752eb4ed301057928c87379998ad9f7310f49a918e0b")
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
        self.assertEqual(ids_d, [f"D{n}" for n in range(1, 70)])
        self.assertEqual(c["preguntas_abiertas"], [])
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
                     ("P78", "D53"), ("P79", "D58"), ("P122", "D60"), ("P145", "D59"),
                     ("P146", "D63"), ("P147", "D64")):
            self.assertEqual(resueltas[p]["decision"], d, p)
        self.assertTrue(resueltas["P28"]["texto"].startswith("**P28."))
        acuerdos = {i for a in c["acuerdos"] for i in a["ids"]}
        self.assertTrue({f"A{n}" for n in range(1, 34)} <= acuerdos)
        self.assertTrue(any(a["revisado"] for a in c["acuerdos"]))
        self.assertTrue(all(a["revisado"] == ("revisad" in a["seccion"].casefold()) for a in c["acuerdos"]))
        self.assertEqual(c["declaracion_c4_reloj"], dict(addendum.DECLARACION_C4))
        for clave, parte in (("hecho", "4e16614"), ("item_prospectivo", "ítem prospectivo de §1.9"),
                             ("olas", "olas 0 a 3"), ("olas", "Después: las olas 4 a 6"),
                             ("lectura_propuesta", "post_hoc = true"), ("lectura_propuesta", "D65"), ("pregunta", "P122")):
            self.assertIn(parte, c["declaracion_c4_reloj"][clave])
        self.assertEqual(c["esquema"], "meteo-combinada-addendum-m1/4")
        em = c["enmienda_operativa"]
        self.assertEqual(em, dict(addendum.ENMIENDA_OPERATIVA))
        self.assertIs(em["post_hoc"], True)
        self.assertEqual((em["id"], em["decision"], em["sha256_anclado"], em["sha256_enmendado"]),
                         ("EMC3", "D65", fijados.SHA_TEXTO_V2_3, addendum.SHA_TEXTO_V2_4))
        self.assertIn("sin costo final", em["lo_visto"].casefold())
        self.assertIn("No se abrieron informes ni tablas de evidencia", em["lo_visto"])
        self.assertIn("sí es enmienda", c["declaracion_c4_reloj"]["lectura_propuesta"])
        self.assertNotIn("no es errata ni enmienda", c["declaracion_c4_reloj"]["lectura_propuesta"])
        self.assertEqual(em["texto_enmendado"], f"APH/{addendum.TEXTO_V2_4}")
        carga = c["enmienda_carga"]
        self.assertEqual(carga, dict(addendum.ENMIENDA_CARGA))
        self.assertIs(carga["post_hoc"], True)
        self.assertEqual((carga["id"], carga["fecha"], carga["decision"]), ("EMC4", "2026-10-31", "D68"))
        self.assertEqual((carga["texto_anclado"], carga["sha256_anclado"]),
                         (f"APH/{addendum.TEXTO_V2_4}", addendum.SHA_TEXTO_V2_4))
        self.assertEqual((carga["texto_enmendado"], carga["sha256_enmendado"]),
                         (f"APH/{addendum.TEXTO_V2_5}", addendum.SHA_TEXTO_V2_5))
        self.assertTrue(carga["texto_enmendado"].endswith("enmienda4/PROTOCOLO_METEO_COMBINADA_v2.5.md"))
        self.assertEqual(carga["fuente"], f"APH/{addendum.CARPETA_PRODUCTO}/enmienda4/decisiones_autor_20261031.md")
        self.assertEqual(carga["enmienda"], f"APH/{addendum.CARPETA_PRODUCTO}/enmienda4/ENMIENDA_4.md")
        for parte in ("máquina libre", "carga < 2"):
            self.assertIn(parte, carga["regla_anclada"])
        for parte in ("sólo informativa", "sin veto al inicio", "durante", "proyección efectiva", "recorte"):
            self.assertIn(parte, carga["regla_enmendada"])
        for parte in ("bruta", "ajena", "no finitos", "sin falsear", "libre real"):
            self.assertIn(parte, carga["registro"])
        for parte in ("ErrorCosto", "costo_no_medido", "2026-10-30", "940", "938", "2 omitidas",
                      "13.0928", "3.3511", "compatibles", "no una causa interna demostrada"):
            self.assertIn(parte, carga["lo_visto"])
        for parte in ("D64", "pueden cambiar", "comparativo confirmatorio"):
            self.assertIn(parte, carga["consecuencias"])
        self.assertIn("D68", c["declaracion_c4_reloj"]["lectura_propuesta"])
        memoria = c["enmienda_memoria"]
        self.assertEqual(memoria, dict(addendum.ENMIENDA_MEMORIA))
        self.assertIs(memoria["post_hoc"], True)
        self.assertEqual((memoria["id"], memoria["fecha"], memoria["decision"]), ("EMC5", "2026-10-31", "D69"))
        self.assertEqual((memoria["texto_anclado"], memoria["sha256_anclado"]),
                         (f"APH/{addendum.TEXTO_V2_5}", addendum.SHA_TEXTO_V2_5))
        self.assertEqual((memoria["texto_enmendado"], memoria["sha256_enmendado"]),
                         (f"APH/{umbrales.TEXTO_VIGENTE}", umbrales.SHA_TEXTO_VIGENTE))
        self.assertTrue(memoria["texto_enmendado"].endswith("enmienda5/PROTOCOLO_METEO_COMBINADA_v2.6.md"))
        self.assertEqual(memoria["orden_humana"], "borra limites neceisot que se ejcute todo para empesara ver los modelos")
        for parte in ("sin tope individual de 8 GB", "memoria_trabajador", "memoria_principal", "memoria_fisica",
                      "finitas y positivas", "Hasta 8 procesos", "si no cabe ni 1", "pendiente"):
            self.assertIn(parte, memoria["regla_enmendada"])
        for parte in ("costo completo", "único motivo", "recorte_pendiente", "9.42", "12.63", "11.28",
                      "8 GB entonces vigente", "Sin resultados del reloj DMC", "competencia meteorológica real"):
            self.assertIn(parte, memoria["lo_visto"])
        for parte in ("no se arregla ni aprueba retroactivamente", "[delegada, para ratificar]", "exactamente",
                      "código original", "origen", "SHA-256", "fecha", "íntegra la suite vigente"):
            self.assertIn(parte, memoria["consecuencias"])
        for parte in ("36 h", "métodos", "carga sólo informativa", "guardas", "política C5"):
            self.assertIn(parte, memoria["limite"])
        self.assertIn("D69", c["declaracion_c4_reloj"]["lectura_propuesta"])
        self.assertIn("no por la política C5", c["declaracion_c4_reloj"]["lectura_propuesta"])
        self.assertTrue(any(t["ruta"].endswith("v2.3.md") for t in c["textos_anteriores"]))
        self.assertIn({"ruta": f"APH/{addendum.TEXTO_V2_4}", "sha256": addendum.SHA_TEXTO_V2_4},
                      c["textos_anteriores"])
        self.assertIn({"ruta": f"APH/{addendum.TEXTO_V2_5}", "sha256": addendum.SHA_TEXTO_V2_5},
                      c["textos_anteriores"])
        self.assertEqual(c["decisiones"][-1]["id"], "D69")
        self.assertEqual(c["decisiones"][-1]["fuente"], "APH/" + addendum.DECISIONES[-1])
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
                      "procesos por fase:", addendum.DECLARACION_D59, "## Enmienda de carga del producto (D68; §10)",
                      addendum.ENMIENDA_CARGA["lo_visto"], addendum.ENMIENDA_CARGA["consecuencias"],
                      "## Enmienda de memoria del producto (D69; §10)", addendum.ENMIENDA_MEMORIA["lo_visto"],
                      addendum.ENMIENDA_MEMORIA["consecuencias"]):
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
            publicado = json.loads((m1 / addendum.NOMBRE_JSON).read_bytes())
            self.assertEqual(publicado["enmienda_operativa"], dict(addendum.ENMIENDA_OPERATIVA))
            self.assertIs(publicado["enmienda_operativa"]["post_hoc"], True)
            self.assertEqual(publicado["enmienda_carga"], dict(addendum.ENMIENDA_CARGA))
            self.assertIs(publicado["enmienda_carga"]["post_hoc"], True)
            self.assertEqual(publicado["enmienda_memoria"], dict(addendum.ENMIENDA_MEMORIA))
            self.assertIs(publicado["enmienda_memoria"]["post_hoc"], True)
            self.assertEqual(publicado["enmienda_carga"]["sha256_enmendado"], addendum.SHA_TEXTO_V2_5)
            self.assertEqual(publicado["enmienda_operativa"]["sha256_enmendado"], addendum.SHA_TEXTO_V2_4)
            self.assertEqual(publicado["declaracion_c4_reloj"], dict(addendum.DECLARACION_C4))
            self.assertEqual(len(publicado["decisiones"]), 69)
            self.assertEqual(publicado["preguntas_abiertas"], [])
            publicado_md = (m1 / addendum.NOMBRE_MD).read_text()
            self.assertIn("post_hoc: true", publicado_md)
            self.assertIn(addendum.ENMIENDA_OPERATIVA["lo_visto"], publicado_md)
            for nombre, datos in ((addendum.NOMBRE_JSON, entorno.json_canonico(c)),
                                  (addendum.NOMBRE_MD, md.encode())):
                salidas.escribir(nombre + ".gz", gzip.compress(datos), clase="documento", raiz=m1, referencia=self.ref)
                self.assertEqual(gzip.decompress((m1 / (nombre + ".gz")).read_bytes()), datos)
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
                        {"lista": {k: v for k, v in self.lista.items() if k != f"APH/{umbrales.TEXTO_VIGENTE}"}}):
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
        self.assertIn("post_hoc: true", md)
        self.assertIn(addendum.ENMIENDA_OPERATIVA["lo_visto"], md)
        # la pared que se vuelve a proyectar decide el recorte de §4.9 (§8), así que D59 no cambia bits sólo por sí
        # mismo (P147)
        for parte in ("por sí mismo (S9)", "§4.9", "desde la proyección", "costo_m1.json", "P147", "P146", "D65", "post_hoc = true"):
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
        """A32: ``anexo_a2.json`` sale de ``constantes.anexo_a2`` sobre el v2.6 y pasa la guarda del documento."""
        a2 = addendum.anexo_a2(_REALES)
        self.assertEqual(a2["texto_sha256"], umbrales.SHA_TEXTO_VIGENTE)
        ceguera.vigilar_salida("anexo_a2.json", a2, clase="documento", referencia=self.ref)


class PruebasDeclaraciones(unittest.TestCase):
    """Negativas independientes: no leen documentos normativos ni salidas reales."""

    def _contenido(self, **cambios):
        lista = {f"APH/{umbrales.TEXTO_VIGENTE}": umbrales.SHA_TEXTO_VIGENTE,
                 f"APH/{addendum.TEXTO_V2_4}": addendum.SHA_TEXTO_V2_4,
                 f"APH/{addendum.TEXTO_V2_5}": addendum.SHA_TEXTO_V2_5}
        lecturas = {k: [] for k in ("parametros_s6", "lecturas", "lecturas_diseno", "decisiones", "diferencias",
                                    "preguntas_abiertas", "preguntas_respondidas", "acuerdos")}
        lecturas["fuentes"] = {}
        return _armar_contenido(lista, lecturas, **cambios)

    def test_constructor_exige_post_hoc_booleano_y_validacion_propia(self):
        for atributo in ("ENMIENDA_OPERATIVA", "ENMIENDA_CARGA", "ENMIENDA_MEMORIA"):
            for falso in (False, 1, 1.0, "true", None, []):
                enmienda = {**getattr(addendum, atributo), "post_hoc": falso}
                with self.subTest(enmienda=atributo, post_hoc=repr(falso)), \
                        mock.patch.object(addendum, atributo, enmienda), self.assertRaises(addendum.ErrorAddendum):
                    self._contenido()
        with mock.patch.object(addendum, "_validar_declaraciones", side_effect=addendum.ErrorAddendum("prueba")) \
                as validar, self.assertRaises(addendum.ErrorAddendum):
            self._contenido()
        validar.assert_called_once()

    def test_emc3_y_emc4_conservan_identidades_historicas(self):
        self.assertEqual(addendum.SHA_TEXTO_V2_4,
                         "eaedb10998e1a3f37f83f036c478afb5cf3fd3ccb5262477bd394dc220b1908b")
        self.assertEqual(addendum.SHA_TEXTO_V2_5,
                         "7771e830c526d8a0da93453e7e2d821896ba797147d14803969907ce5749589d")
        for enmienda, texto, sha, sha_declaracion in (
                (addendum.ENMIENDA_OPERATIVA, addendum.TEXTO_V2_4, addendum.SHA_TEXTO_V2_4,
                 "a4122722077dd0a831203cb80283b471748b88cda3da9871b0c9acc53ad26880"),
                (addendum.ENMIENDA_CARGA, addendum.TEXTO_V2_5, addendum.SHA_TEXTO_V2_5,
                 "fc6165551bf9a5a6998096e03817a445e7e7a55bc10e46e36710a7dd0b021734")):
            self.assertEqual((enmienda["texto_enmendado"], enmienda["sha256_enmendado"]), (f"APH/{texto}", sha))
            self.assertNotEqual(enmienda["texto_enmendado"], f"APH/{umbrales.TEXTO_VIGENTE}")
            datos = json.dumps(dict(enmienda), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
            self.assertEqual(hashlib.sha256(datos).hexdigest(), sha_declaracion,
                             "la declaración histórica completa debe permanecer exacta")

    def test_declaraciones_rechazadas_por_lector_formato_y_publicacion(self):
        """EMC3, EMC4 y EMC5: cada vía rechaza declaraciones falsas aun sin guarda genérica; no deja salidas."""
        c = self._contenido()
        md = addendum.addendum_md(c)
        casos = []

        def cambiar_md(titulo, antes, despues):
            inicio = md.index(titulo)
            fin = md.index("\n## ", inicio + 1)
            bloque = md[inicio:fin]
            self.assertIn(antes, bloque)
            return md[:inicio] + bloque.replace(antes, despues, 1) + md[fin:]

        for clave, enmienda, titulo in (
                ("enmienda_operativa", addendum.ENMIENDA_OPERATIVA, "## Enmienda operativa del producto (D65; §10)"),
                ("enmienda_carga", addendum.ENMIENDA_CARGA, "## Enmienda de carga del producto (D68; §10)"),
                ("enmienda_memoria", addendum.ENMIENDA_MEMORIA, "## Enmienda de memoria del producto (D69; §10)")):
            for falso in (False, 1, 1.0, "true", None, []):
                malo = json.loads(json.dumps(c))
                malo[clave]["post_hoc"] = falso
                casos.append((f"{clave}: post_hoc={falso!r}", malo,
                              cambiar_md(titulo, "- post_hoc: true", f"- post_hoc: {falso!r}")))
            malo = json.loads(json.dumps(c)); del malo[clave]["post_hoc"]
            casos.append((f"{clave}: sin post_hoc", malo, cambiar_md(titulo, "- post_hoc: true\n", "")))
            malo = json.loads(json.dumps(c)); del malo[clave]
            casos.append((f"sin {clave}", malo, md.replace(titulo, "", 1)))
            for campo, valor in enmienda.items():
                if campo == "post_hoc":
                    continue
                falso = "Declaración alterada."
                malo = json.loads(json.dumps(c)); malo[clave][campo] = falso
                casos.append((f"{clave}: {campo} falso", malo,
                              cambiar_md(titulo, f"- {campo}: {valor}", f"- {campo}: {falso}")))
            malo = json.loads(json.dumps(c)); malo[clave]["extra"] = "No autorizado."
            casos.append((f"{clave}: campo adicional", malo,
                          cambiar_md(titulo, titulo, titulo + "\n- extra: No autorizado.")))
        malo = json.loads(json.dumps(c)); malo["declaracion_c4_reloj"]["lectura_propuesta"] = "No es enmienda."
        casos.append(("C4 incompatible", malo, md.replace(addendum.DECLARACION_C4["lectura_propuesta"], "No es enmienda.")))
        malo = json.loads(json.dumps(c)); malo["esquema"] = "meteo-combinada-addendum-m1/3"
        casos.append(("esquema anterior", malo, None))
        with tempfile.TemporaryDirectory() as tmp:
            rutas = entorno.rutas_sinteticas(tmp)
            raiz = entorno.carpeta_salida(rutas, "m1", _SUB)
            raiz.mkdir(parents=True)
            alias_ = f"{_M1}/{addendum.NOMBRE_JSON}"
            fichero = raiz / addendum.NOMBRE_JSON
            for nombre, malo, md_malo in casos:
                with self.subTest(caso=nombre):
                    with self.assertRaises(addendum.ErrorAddendum):
                        addendum.addendum_md(malo)
                    datos = entorno.json_canonico(malo)
                    fichero.write_bytes(datos)  # sólo datos fabricados: prueba del lector
                    with self.assertRaises(V.ErrorConfiguracion):
                        V.leer_addendum(alias_, rutas)
                    fichero.unlink()
                    publicaciones = [(addendum.NOMBRE_JSON, malo), (addendum.NOMBRE_JSON, datos),
                                     (addendum.NOMBRE_JSON + ".gz", gzip.compress(datos))]
                    if md_malo is not None:
                        publicaciones += [(addendum.NOMBRE_MD, md_malo),
                                          (addendum.NOMBRE_MD + ".gz", gzip.compress(md_malo.encode()))]
                    for ruta, contenido in publicaciones:
                        # La validación especializada debe bastar incluso sin la guarda documental genérica.
                        with self.subTest(ruta=ruta), mock.patch.object(ceguera, "vigilar_salida"), \
                                self.assertRaises(ceguera.SalidaProhibida):
                            salidas.escribir(ruta, contenido, clase="documento", raiz=raiz, referencia=None)
                        self.assertFalse((raiz / ruta).exists())
            # Orden de claves ajeno al de construcción: la declaración válida se formatea siempre igual.
            ordenado = json.loads(entorno.json_canonico(c))
            md_ordenado = addendum.addendum_md(ordenado)
            inicio = "## Declaración sobre el C4 de RELOJ (§10; P122)"
            fin = "## Lista cerrada de huellas (§10, M1)"
            self.assertEqual(md_ordenado[md_ordenado.index(inicio):md_ordenado.index(fin)],
                             md[md.index(inicio):md.index(fin)])
            with mock.patch.object(ceguera, "vigilar_salida"):
                salidas.escribir(addendum.NOMBRE_JSON, c, clase="documento", raiz=raiz, referencia=None)
                self.assertEqual(V.leer_addendum(alias_, rutas)[0], c)
                salidas.escribir(addendum.NOMBRE_MD, md, clase="documento", raiz=raiz, referencia=None)
                for nombre, datos in ((addendum.NOMBRE_JSON, entorno.json_canonico(c)),
                                      (addendum.NOMBRE_MD, md.encode())):
                    comprimido = gzip.compress(datos)
                    salidas.escribir(nombre + ".gz", comprimido, clase="documento", raiz=raiz, referencia=None)
                    self.assertEqual(gzip.decompress((raiz / (nombre + ".gz")).read_bytes()), datos)


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


class PruebasEnmienda3(unittest.TestCase):
    """Sólo documentos y generación temporal: nunca ejecuta costo, S6 ni una batería."""

    def test_fuentes_ausentes_no_se_dan_por_aprobadas(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch(__name__ + "._REALES", new=mock.Mock(aph=Path(tmp) / "APH_ausente")):
                with self.assertRaises(unittest.SkipTest):
                    self.test_generador_con_y_sin_optimizacion()

    def test_generador_con_y_sin_optimizacion(self):
        carpeta = Path(_REALES.aph) / addendum.CARPETA_PRODUCTO
        fuentes = (carpeta / "enmienda3/generar_v2_4.py", carpeta / "enmienda3/decisiones_autor_20261028.md",
                   carpeta / "enmienda3_borrador/BORRADOR_ENMIENDA_3_PROCESOS.md",
                   carpeta / "enmienda2/PROTOCOLO_METEO_COMBINADA_v2.3.md",
                   carpeta / "enmienda3/PROTOCOLO_METEO_COMBINADA_v2.4.md")
        if any(not f.is_file() for f in fuentes):
            self.skipTest("faltan fuentes EMC3; la prueba no se da por aprobada")
        gen = Path(_REALES.aph) / addendum.CARPETA_PRODUCTO / "enmienda3/generar_v2_4.py"
        texto = gen.with_name("PROTOCOLO_METEO_COMBINADA_v2.4.md").read_bytes()
        self.assertEqual(hashlib.sha256(texto).hexdigest(), addendum.SHA_TEXTO_V2_4)
        codigo = r'''import importlib.util, pathlib, sys, tempfile
spec = importlib.util.spec_from_file_location("gen", sys.argv[1])
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
def rechaza(accion):
    try:
        accion()
    except SystemExit:
        return
    raise RuntimeError("la comprobación dejó pasar una mutación")
if g.generar() != pathlib.Path(sys.argv[1]).with_name("PROTOCOLO_METEO_COMBINADA_v2.4.md").read_bytes():
    raise RuntimeError("los bytes no coinciden")
with tempfile.TemporaryDirectory(prefix="m1_emc3_") as tmp:
    g.DESTINO = pathlib.Path(tmp) / "v24.md"
    g.main()
    rechaza(g.main)
original = g.SHA_ORIGEN
g.SHA_ORIGEN = "0" * 64
rechaza(g.generar)
g.SHA_ORIGEN = original
original = g.REEMPLAZOS
g.REEMPLAZOS = original + (("de RELOJ para lo que M1 cambie después de él.", "de RELOJ sin frontera."),)
rechaza(g.generar)
g.REEMPLAZOS = original
for atributo in ("REGISTRO", "MEMORIA_NUEVA", "CAB_NUEVA"):
    previo = getattr(g, atributo)
    setattr(g, atributo, previo.replace("post_hoc = true", "post_hoc = false") if "post_hoc = true" in previo
            else previo.replace("≤ 8 GB", "≤ 9 GB"))
    g.REEMPLAZOS = tuple((a, getattr(g, atributo) if b == previo else b) for a, b in original)
    rechaza(g.generar)
    setattr(g, atributo, previo)
    g.REEMPLAZOS = original
print("comprobaciones activas")
'''
        for flags in ([], ["-O"]):
            with self.subTest(flags=flags):
                r = subprocess.run([sys.executable, "-B", "-I", *flags, "-c", codigo, str(gen)], capture_output=True,
                                   text=True, timeout=60, check=False)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("comprobaciones activas", r.stdout)


class _GeneradorEnmienda:
    """Comprobaciones comunes de EMC4 y EMC5, sin leer salidas operativas ni repetir costo."""

    def test_fuentes_ausentes_no_se_dan_por_aprobadas(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch(__name__ + "._REALES", new=mock.Mock(aph=Path(tmp) / "APH_ausente")):
                with self.assertRaises(unittest.SkipTest):
                    self.test_generador_con_y_sin_optimizacion()

    def test_generador_con_y_sin_optimizacion(self):
        carpeta = Path(_REALES.aph) / addendum.CARPETA_PRODUCTO
        origen = carpeta / self.texto_origen
        destino = carpeta / self.texto_destino
        gen = destino.with_name(self.generador)
        fuentes = (gen, destino, origen, destino.with_name("decisiones_autor_20261031.md"),
                   destino.with_name(f"ENMIENDA_{self.enmienda}.md"))
        if any(not f.is_file() for f in fuentes):
            self.skipTest(f"faltan fuentes EMC{self.enmienda}; la prueba no se da por aprobada")
        self.assertEqual(_sha(origen), self.sha_origen)
        self.assertEqual(_sha(destino), self.sha_destino)
        codigo = r'''import hashlib, importlib.util, json, pathlib, sys, tempfile
spec = importlib.util.spec_from_file_location("gen", sys.argv[1])
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
atributos_post_hoc, mutaciones, fuentes_fijadas = json.loads(sys.argv[5])
for atributo in ("generar", "main", "ORIGEN", "DESTINO", "SHA_ORIGEN", "REEMPLAZOS", *fuentes_fijadas):
    if not hasattr(g, atributo):
        raise RuntimeError("falta la interfaz requerida: " + atributo)
def rechaza(accion):
    try:
        accion()
    except SystemExit:
        return
    raise RuntimeError("la comprobación dejó pasar una mutación")
esperado = pathlib.Path(sys.argv[1]).with_name(sys.argv[4]).read_bytes()
if g.SHA_ORIGEN != sys.argv[2]:
    raise RuntimeError("no se conserva el anclaje histórico")
if hashlib.sha256(esperado).hexdigest() != sys.argv[3]:
    raise RuntimeError("el destino no tiene la huella esperada")
if g.generar() != esperado:
    raise RuntimeError("los bytes no coinciden")
with tempfile.TemporaryDirectory(prefix="m1_enmienda_") as tmp:
    g.DESTINO = pathlib.Path(tmp) / "protocolo.md"
    g.main()
    if g.DESTINO.read_bytes() != esperado:
        raise RuntimeError("main no conserva los bytes de generar")
    rechaza(g.main)
    for atributo in ("ORIGEN", *fuentes_fijadas):
        original = getattr(g, atributo)
        alterado = pathlib.Path(tmp) / (atributo + "_alterado.md")
        alterado.write_bytes(original.read_bytes() + b"\nCambio ajeno\n")
        setattr(g, atributo, alterado)
        rechaza(g.generar)
        setattr(g, atributo, original)
original = g.SHA_ORIGEN
g.SHA_ORIGEN = "0" * 64
rechaza(g.generar)
g.SHA_ORIGEN = original
original = g.REEMPLAZOS
g.REEMPLAZOS = original + (("de RELOJ para lo que M1 cambie después de él.", "de RELOJ sin frontera."),)
rechaza(g.generar)
g.REEMPLAZOS = original + (original[0],)
rechaza(g.generar)
g.REEMPLAZOS = original[:-1]
rechaza(g.generar)
g.REEMPLAZOS = original
for atributo in atributos_post_hoc:
    previo = getattr(g, atributo)
    alterado = previo.replace("post_hoc = true", "post_hoc = false")
    if alterado == previo:
        raise RuntimeError("falta la declaración post_hoc en " + atributo)
    setattr(g, atributo, alterado)
    g.REEMPLAZOS = tuple((a, b.replace(previo, alterado)) for a, b in original)
    rechaza(g.generar)
    setattr(g, atributo, previo)
    g.REEMPLAZOS = original
for antes, despues in mutaciones:
    alterados = tuple((a, b.replace(antes, despues)) for a, b in original)
    if alterados == original:
        raise RuntimeError("falta la regla esperada: " + antes)
    g.REEMPLAZOS = alterados
    rechaza(g.generar)
    g.REEMPLAZOS = original
if g.generar() != esperado:
    raise RuntimeError("las comprobaciones alteraron el generador")
print("comprobaciones activas")
'''
        opciones = json.dumps((self.atributos_post_hoc, self.mutaciones, self.fuentes_fijadas))
        for flags in ([], ["-O"]):
            with self.subTest(flags=flags):
                r = subprocess.run([sys.executable, "-B", "-I", *flags, "-c", codigo, str(gen), self.sha_origen,
                                    self.sha_destino, destino.name, opciones], capture_output=True, text=True,
                                   timeout=60, check=False)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("comprobaciones activas", r.stdout)


class PruebasEnmienda4(_GeneradorEnmienda, unittest.TestCase):
    """EMC4/D68 histórica: jamás compara su destino v2.5 con la identidad vigente v2.6."""
    enmienda = 4
    texto_origen = addendum.TEXTO_V2_4.removeprefix(addendum.CARPETA_PRODUCTO + "/")
    texto_destino = addendum.TEXTO_V2_5.removeprefix(addendum.CARPETA_PRODUCTO + "/")
    generador = "generar_v2_5.py"
    sha_origen, sha_destino = addendum.SHA_TEXTO_V2_4, addendum.SHA_TEXTO_V2_5
    atributos_post_hoc = ("REGISTRO", "CAB_NUEVA", "OPERACION")
    mutaciones = (("sólo informativa", "excluyente"),)
    fuentes_fijadas = ()


class PruebasEnmienda5(_GeneradorEnmienda, unittest.TestCase):
    """EMC5/D69: generación temporal y negativas documentales, también con -O."""
    enmienda = 5
    texto_origen = addendum.TEXTO_V2_5.removeprefix(addendum.CARPETA_PRODUCTO + "/")
    texto_destino = umbrales.TEXTO_VIGENTE.removeprefix(addendum.CARPETA_PRODUCTO + "/")
    generador = "generar_v2_6.py"
    sha_origen, sha_destino = addendum.SHA_TEXTO_V2_5, umbrales.SHA_TEXTO_VIGENTE
    atributos_post_hoc = ("REGISTRO",)
    mutaciones = (("sin tope individual fijo", "con tope individual fijo"),
                  ("finitos y positivos", "no finitos ni positivos"),
                  ("hasta 8 procesos", "hasta 9 procesos"),
                  ("[delegada, para ratificar] Reutilización técnica", "Reutilización incondicional"))
    fuentes_fijadas = ("DECISIONES", "DECLARACION")


if __name__ == "__main__":
    unittest.main()
