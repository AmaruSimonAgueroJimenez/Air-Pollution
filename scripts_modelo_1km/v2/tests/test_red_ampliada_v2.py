"""Pruebas de ``red_ampliada_v2`` (R2, R3, R8 y R10) y de las guardas del bloque sobre la v1.

Las sintéticas cubren la lista cerrada, los maestros, el propietario y la red resultante. Las de datos reales leen sólo
cabeceras, columnas de identidad y conteos (y huellas de archivos), nunca valores ni métricas; se saltan sin el disco.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

import pandas as pd

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import _rutas_v2 as rv  # noqa: E402
import red_ampliada_v2 as ra  # noqa: E402
import unidades_v2 as uv  # noqa: E402

REPO = V2.parents[1]
MODULOS_NUEVOS = ("reloj_sinca_v2.py", "unidades_v2.py", "contraste_unidades_v2.py", "duplicados_v2.py",
                  "red_ampliada_v2.py", "derivado_red2_v2.py", "panel_red2_v2.py", "pliegues_red2_v2.py",
                  "tests/test_reloj_sinca_v2.py", "tests/test_unidades_v2.py", "tests/test_duplicados_v2.py",
                  "tests/test_red_ampliada_v2.py", "tests/test_contraste_unidades_v2.py",
                  "tests/test_derivado_red2_v2.py", "tests/test_panel_red2_v2.py", "tests/test_pliegues_red2_v2.py")
# Huellas de la v1 y del contrato sellado que el bloque no toca (§5 del bloque y c7c47e8).
SELLADOS = {
    "scripts_modelo_1km/v2/DISENO_AMBIENTAL_V2.md": "5d879a05179a3e980d01e25e12bb4f3492d4fe6b4142f7be6daa2509df4c39b0",
    "scripts_modelo_1km/v2/config_v2.json": "232c75b3376b6fd7c4f73c885c812e170abff7c1a8817d1ac64cc76c68b0534c",
    "scripts_modelo_1km/verificar_reloj_sinca.py": "a93a1eab928d032b1d83c0e32702f2f2b73fa6d9a0b228b47ef9abb3f632d446",
    "scripts_modelo_1km/_comun_modelo.py": "a83c0384266554e16ab397749544759ae1cf161f138361eefa7d1ad3e29aa6f4",
    "scripts_modelo_1km/_red_adicional.py": "f7ab850b4784afa648e7e579294dee8f9e1a34c400b20a766a10e590a395941c",
    "scripts_pipeline/preparar_sinca_modelado.py": "95f1ecd3c9071f3877e858e0b822b4e525b00b49ab4aced8f0490a71d0a65401",
    "scripts_pipeline/actualizar_geometria_sinca.py": "24355ab65692f82ddca550d04e9540f8b8b2cad02e4c02564960ed2a451bbde5",
    "scripts_pipeline/geometria_sinca_ampliacion.py": "c1153b6396e965fa3f52697121fb2edb7f39241517e881daec94a3570532c76b",
    # el descargador de la ampliación (v1.1.0, §5 del bloque) y el módulo que importa y cuya huella registra
    "scripts_pipeline/descargar_sinca_ampliacion.py": "d77247232ed4857941d8a4616193d805ed612af20a816949b44b6b1c9cb63c62",
    "scripts_pipeline/descargar_sinca_meteorologia.py": "0942c4d071cefffb95da76d2b010c981ef126858ea7b3c028ef3c7c23a51b145",
    "config/sinca/politica_temporal.json": "41018e4c066d9e30b5ba0b1ff92d47eeb47bab1984b5b8c45a778939359ac61c",
}
CONTRATO, CONFIG = "scripts_modelo_1km/v2/DISENO_AMBIENTAL_V2.md", "scripts_modelo_1km/v2/config_v2.json"
PROPUESTA = REPO / ra.CARPETA_PROPUESTA
ESPEJO = V2.parents[2] / ra.NOMBRE_ESPEJO
DECISIONES = ESPEJO / "auditoria" / "20261024" / "sinca_al_modelo" / "decisiones_autor_traduccion_20261025.md"


def config_con_la_red() -> dict:
    """La configuración con el nodo de la red: la aplicada si ya está; si no, la propuesta."""
    cfg = json.loads((REPO / CONFIG).read_text(encoding="utf-8"))
    if "red_de_monitores" not in cfg:
        cfg = json.loads((PROPUESTA / "config_v2.propuesto.json").read_text(encoding="utf-8"))
    return cfg
# El contrato con el bloque transcrito (propuesta_red_ampliada/DISENO_AMBIENTAL_V2.propuesto.md).
CONTRATO_PROPUESTO = "5140306eae85f854e17748b1119300ce35f9239685487bff3806b285ca397670"
SELLADOS_V1_LOCAL = {
    "grilla_1km/celdas.parquet": "42b4b19613c7de343c856473af64e2c0a6353351f1884c8dba145361292108c3",
    "grilla_1km/estaciones_enlaces.parquet": "372a6415ad5e88b1a2a820db0149baab04cd13f87e2cdd67e01e4b3ef99060d4",
    "grilla_1km/estaciones_enlaces_adicional.parquet": "4f4edef9611cb34e4588e8a1a210f2f345d56851b2d6e3eb20aa6cfb37d2b688",
    "paneles/panel_no2.json": "ea7c058e21d42cf263f5782b95d49152f04cbdbe49d9c354be8af8ebb5d857e4",
    "paneles/panel_pm25.json": "2a6cda8e42a6938d0e41d015a4c0e13e439955e55d6265dc7e13673ba7ebc3a5",
}


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# Una ratificación de juguete (T13 [delegada]): la del commit posterior a la ratificación, con otra huella del archivo
# de decisiones (la de antes de ratificar es ra.DECISIONES_SIN_RATIFICAR).
HUELLA_RATIFICADA = "e" * 64
RATIFICACION = {"fecha": "2026-10-27", "decisiones_sha256": HUELLA_RATIFICADA,
                **{k: "ratificada" for k in ra.RATIFICABLES}}


def textos_ratificados(textos: dict, ratificacion) -> dict:
    """T11, T12 y T13 como quedan en el commit de la ratificación (ronda 5, menor 21): sin la marca de pendiente y con
    «<estado> por el autor el <fecha>» (``ra.MARCA_DE_RATIFICACION``)."""
    rat = ratificacion if isinstance(ratificacion, dict) else {}
    out = {}
    for k in ra.DECISIONES_DELEGADAS:
        marca = ra.MARCA_DE_RATIFICACION.format(estado=rat.get(k, "ratificada"), fecha=rat.get("fecha"))
        texto = textos[k]
        for pendiente in ra.MARCAS_DE_PENDIENTE:
            texto = texto.replace(pendiente, marca)
        out[k] = texto
    return out


def con_la_ratificacion(ratificacion=RATIFICACION, huella=HUELLA_RATIFICADA, textos: bool = True):
    """El código como queda después del commit posterior a la ratificación: la constante llena, la huella nueva del
    archivo de decisiones en DECISIONES_TRADUCCION y, con ``textos``, T11 a T13 ya sin la marca de pendiente."""
    import contextlib
    from unittest import mock
    pila = contextlib.ExitStack()
    pila.enter_context(mock.patch.object(ra, "RATIFICACION_T11_T13", ratificacion))
    nuevos = textos_ratificados(ra.DECISIONES_TRADUCCION, ratificacion) if textos else {}
    pila.enter_context(mock.patch.dict(ra.DECISIONES_TRADUCCION, {"sha256": huella, **nuevos}))
    return pila


def cfg_ratificada(ratificacion=RATIFICACION, textos: bool = True) -> dict:
    """La configuración del commit posterior a la ratificación: la repite y, con ``textos``, trae T11 a T13 de
    ``contrato.enmiendas[2].decisiones_de_traduccion`` sin la marca de pendiente."""
    dec = dict(config_con_la_red()["contrato"]["enmiendas"][2]["decisiones_de_traduccion"])
    if textos:
        dec.update(textos_ratificados(dec, ratificacion))
    return {"red_de_monitores": {"ratificacion_t11_t13": {"valor": ratificacion}},
            "contrato": {"enmiendas": [{}, {}, {"decisiones_de_traduccion": dec}]}}


# Un correo (usuario, arroba, dominio con punto); la arroba se arma con chr(64) para que este archivo no la lleve. Los
# decoradores del código sellado (la arroba al comienzo de una línea) no calzan: no tienen un usuario pegado antes.
CORREO = __import__("re").compile(r"[A-Za-z0-9._%+-]+" + chr(64) + r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


class GuardasTests(unittest.TestCase):
    def test_la_v1_y_el_contrato_sellado_no_cambian(self):
        """La v1 no cambia nunca. El contrato y la configuración son los sellados (c7c47e8) hasta que se aplique la
        propuesta (T2); después, el contrato es el propuesto y la configuración lo declara con el nodo de la red."""
        aplicada = sha(REPO / CONTRATO) != SELLADOS[CONTRATO]
        for rel, esperado in SELLADOS.items():
            if aplicada and rel in (CONTRATO, CONFIG):
                continue
            with self.subTest(archivo=rel):
                self.assertEqual(sha(REPO / rel), esperado)
        if aplicada:
            self.assertEqual(sha(REPO / CONTRATO), CONTRATO_PROPUESTO)
            cfg = json.loads((REPO / CONFIG).read_text(encoding="utf-8"))
            self.assertEqual(cfg["contrato"]["sha256"], CONTRATO_PROPUESTO)
            self.assertIn("red_de_monitores", cfg)

    def test_grilla_y_json_de_los_paneles_v1_intactos(self):
        """Huellas de la grilla v1 y de los json de sus paneles (los parquet de los paneles no se leen aquí)."""
        raiz = rv.RutasV2.desde_entorno().raiz_v1
        if not (raiz / "paneles" / "panel_no2.json").exists():
            self.skipTest("sin la raíz v1 local")
        for rel, esperado in SELLADOS_V1_LOCAL.items():
            with self.subTest(archivo=rel):
                self.assertEqual(sha(raiz / rel), esperado)

    def test_sin_rutas_personales_ni_arrobas(self):
        carpeta_propuesta = V2 / "propuesta_red_ampliada"
        archivos = [V2 / m for m in MODULOS_NUEVOS] + sorted(p for p in carpeta_propuesta.glob("*") if p.is_file())
        for p in archivos:
            if not p.exists():
                continue
            texto = p.read_text(encoding="utf-8")
            with self.subTest(archivo=p.name):
                self.assertNotIn("/" + "Users/", texto)
                self.assertNotIn(chr(64), texto)

    def test_el_maestro_del_24_no_se_usa(self):
        """El maestro del 2026-10-24 de la ampliación (c5eb0806…) no se usa: los maestros de R8 son el sellado y el
        corregido de geometria_20261025, y ningún módulo de la red 2 lo nombra. (``load_inputs`` del preparador sí lee
        su geojson, y ``derivado_red2_v2`` lo reemplaza por el corregido: lo prueba ``test_derivado_red2_v2``.)"""
        self.assertTrue(ra.MAESTRO_NUEVAS.startswith(ra.GEO + "/"))
        self.assertTrue(ra.GEOJSON_NUEVAS.startswith(ra.GEO + "/"))
        for rel in ra.NO_SE_USAN:
            self.assertNotIn(rel, ra.LISTA_CERRADA)
        literal = "sinca_ampliacion_20261024/estaciones_georreferenciadas"
        for m in ("derivado_red2_v2.py", "panel_red2_v2.py", "pliegues_red2_v2.py", "contraste_unidades_v2.py"):
            self.assertNotIn(literal, (V2 / m).read_text(encoding="utf-8"))


class GuardaR22Tests(unittest.TestCase):
    """Nada de la red 2 escribe antes de que la traducción esté confirmada en git (R22, paso 2)."""

    def setUp(self):
        import types
        self.r = types.SimpleNamespace(repo=REPO)
        self.cfg = {"red_de_monitores": {}}

    def todo(self, valor):
        return lambda repo, rutas: {k: valor for k in rutas}

    def test_sin_el_nodo_se_detiene(self):
        with self.assertRaises(SystemExit):
            ra.exigir_traduccion_confirmada(self.r, {}, self.todo("rastreado"))

    def test_con_cambios_sin_confirmar_se_detiene(self):
        for estado in ("modificado", "sin_rastrear", "desconocido"):
            with self.subTest(estado=estado), self.assertRaises(SystemExit):
                ra.exigir_traduccion_confirmada(self.r, self.cfg, self.todo(estado))

    def test_confirmada_sigue(self):
        est = ra.exigir_traduccion_confirmada(self.r, self.cfg, self.todo("rastreado"))
        self.assertEqual(set(est), set(ra.ARCHIVOS_TRADUCCION))

    def test_sin_ratificacion_el_armado_no_empieza(self):
        """T13 [delegada] (ronda 4, mayor 6): «el paso 2 de §11 (armado) no empieza hasta que el autor ratifique T11,
        T12 y T13». La compuerta, que sólo llaman los programas del armado, lo exige: con la traducción confirmada en
        git, se detiene mientras RATIFICACION_T11_T13 esté vacía, si le falta una decisión o una lectura (también la
        §8.17, ronda 5, menores 7 y 26), si cita el archivo de decisiones de antes de ratificar u otro que el de
        DECISIONES_TRADUCCION, si la configuración no la repite o (ronda 5, menor 21) si los textos de T11 a T13 siguen
        diciendo que están pendientes, en el código o en la configuración; con la ratificación completa, sigue. No
        depende del valor de hoy de la constante (ronda 5, menor 25): cada caso la fija."""
        confirmada = self.todo("rastreado")
        with con_la_ratificacion(None, ra.DECISIONES_SIN_RATIFICAR, textos=False), self.assertRaises(SystemExit) as e:
            ra.exigir_traduccion_confirmada(self.r, cfg_ratificada(None, textos=False), confirmada, ratificacion=True)
        self.assertIn("T13", str(e.exception))
        self.assertIn("RATIFICACION_T11_T13 está vacía", str(e.exception))
        sin_t12 = {k: v for k, v in RATIFICACION.items() if k != "T12"}
        sin_lectura = {k: v for k, v in RATIFICACION.items() if k != "§8.14"}
        sin_r15 = {k: v for k, v in RATIFICACION.items() if k != "§8.17"}
        antes = {**RATIFICACION, "decisiones_sha256": ra.DECISIONES_SIN_RATIFICAR}
        self.assertIn("§8.17", ra.RATIFICABLES)
        for nombre, rat, huella, cfg, mensaje in (
                ("sin T12", sin_t12, HUELLA_RATIFICADA, cfg_ratificada(sin_t12), "T12"),
                ("sin la lectura §8.14", sin_lectura, HUELLA_RATIFICADA, cfg_ratificada(sin_lectura), "§8.14"),
                ("sin la lectura §8.17", sin_r15, HUELLA_RATIFICADA, cfg_ratificada(sin_r15), "§8.17"),
                ("la configuración con T11 a T13 pendientes", RATIFICACION, HUELLA_RATIFICADA,
                 cfg_ratificada(textos=False), "contrato.enmiendas[2]"),
                ("otro estado", {**RATIFICACION, "T11": "quizá"}, HUELLA_RATIFICADA,
                 cfg_ratificada({**RATIFICACION, "T11": "quizá"}), "T11"),
                ("el archivo de antes", antes, ra.DECISIONES_SIN_RATIFICAR, cfg_ratificada(antes), "de antes"),
                ("otro archivo", RATIFICACION, "d" * 64, cfg_ratificada(), "DECISIONES_TRADUCCION"),
                ("la configuración no la repite", RATIFICACION, HUELLA_RATIFICADA, {"red_de_monitores": {}},
                 "no repite")):
            with self.subTest(nombre), con_la_ratificacion(rat, huella), self.assertRaises(SystemExit) as e:
                ra.exigir_traduccion_confirmada(self.r, cfg, confirmada, ratificacion=True)
            self.assertIn(mensaje, str(e.exception))
        # el código con T11 a T13 pendientes (la configuración, al día)
        with con_la_ratificacion(textos=False), self.assertRaises(SystemExit) as e:
            ra.exigir_traduccion_confirmada(self.r, cfg_ratificada(), confirmada, ratificacion=True)
        for k in ra.DECISIONES_DELEGADAS:
            self.assertIn(f"{k} en red_ampliada_v2.DECISIONES_TRADUCCION", str(e.exception))
        self.assertIn("dejar de decir que están pendientes", str(e.exception))
        # el estado del texto tiene que ser el de la ratificación: «cambiada» no es «ratificada»
        cambiada = {**RATIFICACION, "T11": "cambiada"}
        cfg = cfg_ratificada()                                               # los textos dicen «ratificada»
        cfg["red_de_monitores"]["ratificacion_t11_t13"]["valor"] = cambiada
        with con_la_ratificacion(cambiada), self.assertRaises(SystemExit) as e:
            ra.exigir_traduccion_confirmada(self.r, cfg, confirmada, ratificacion=True)
        self.assertIn("T11 en contrato.enmiendas[2]", str(e.exception))
        self.assertNotIn("T11 en red_ampliada_v2", str(e.exception))
        with con_la_ratificacion():
            self.assertEqual(set(ra.exigir_traduccion_confirmada(self.r, cfg_ratificada(), confirmada,
                                                                 ratificacion=True)), set(ra.ARCHIVOS_TRADUCCION))
            self.assertEqual(ra.exigir_ratificacion(cfg_ratificada()), RATIFICACION)
        # con git real (estado por omisión) la compuerta la exige siempre: la llaman sólo programas del armado
        import inspect
        fuente = inspect.getsource(ra.exigir_traduccion_confirmada)
        self.assertIn("if ratificacion if ratificacion is not None else estado is None:", fuente)

    def test_hoy_no_esta_confirmada(self):
        """Mientras la traducción no esté en git, la guarda se detiene en el repositorio real (sólo lee git). Después
        del commit de la traducción esta prueba se salta: la guarda queda probada con los estados simulados."""
        pendientes = {k: v for k, v in ra.estado_git(REPO, ra.ARCHIVOS_TRADUCCION).items() if v != "rastreado"}
        if not pendientes:
            self.skipTest("la traducción ya está confirmada en git en AP")
        with self.assertRaises(SystemExit):
            ra.exigir_traduccion_confirmada(self.r, self.cfg)

    def test_el_espejo_tambien(self):
        """R22: la traducción también confirmada en el espejo, con los mismos bytes, y en él los textos de la auditoría
        que cita la configuración, con su sha256 (cuarta revisión, menores 15, 31 y 36)."""
        with tempfile.TemporaryDirectory() as tmp:
            ap, aph = Path(tmp) / "ap", Path(tmp) / "aph"
            for base in (ap, aph):
                (base / "x").mkdir(parents=True)
                (base / "x" / "a.py").write_text("uno", encoding="utf-8")
            (aph / "auditoria").mkdir()
            (aph / "auditoria" / "dec.md").write_text("decisiones", encoding="utf-8")
            del_espejo = {"auditoria/dec.md": hashlib.sha256(b"decisiones").hexdigest()}
            r = types.SimpleNamespace(repo=ap)
            rutas = ("x/a.py",)
            self.assertEqual(ra.verificar_espejo(ap, aph, rutas, self.todo("rastreado"), del_espejo),
                             {"x/a.py": "rastreado", "auditoria/dec.md": "rastreado"})
            with self.assertRaises(SystemExit):                              # sin confirmar en el espejo
                ra.verificar_espejo(ap, aph, rutas, self.todo("modificado"), del_espejo)
            with self.assertRaises(SystemExit):                              # las decisiones sin rastrear
                ra.verificar_espejo(ap, aph, rutas, lambda repo, rr: {k: "rastreado" if k == "x/a.py" else "sin_rastrear"
                                                                     for k in rr}, del_espejo)
            with self.assertRaises(SystemExit) as e:                         # otra huella de las decisiones
                ra.verificar_espejo(ap, aph, rutas, self.todo("rastreado"), {"auditoria/dec.md": "0" * 64})
            self.assertIn("auditoría", str(e.exception))
            with self.assertRaises(SystemExit):                              # por omisión, los tres textos de verdad
                ra.verificar_espejo(ap, aph, rutas, self.todo("rastreado"))
            with self.assertRaises(SystemExit) as e:                         # el espejo no puede ser el mismo
                ra.verificar_espejo(ap, ap, rutas, self.todo("rastreado"), {})
            self.assertIn("mismo repositorio", str(e.exception))
            (aph / "x" / "a.py").write_text("dos", encoding="utf-8")
            with self.assertRaises(SystemExit):                              # bytes distintos
                ra.verificar_espejo(ap, aph, rutas, self.todo("rastreado"), del_espejo)
            with self.assertRaises(SystemExit):                              # sin espejo
                ra.verificar_espejo(ap, Path(tmp) / "no", rutas, self.todo("rastreado"), del_espejo)
            with self.assertRaises(SystemExit):                              # la guarda completa revisa el espejo
                ra.exigir_traduccion_confirmada(r, self.cfg, self.todo("rastreado"), espejo=aph)

    def test_el_par_no_depende_de_donde_se_lanza(self):
        """Cuarta revisión, mayor 2: desde AP, el espejo es su hermano Air-Pollution-Health-Chile; desde el espejo, el
        canónico es su hermano Air-Pollution. El par es el mismo."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            ap, aph = base / ra.NOMBRE_CANONICO, base / ra.NOMBRE_ESPEJO
            self.assertEqual(ra.par_de_repositorios(ap), (ap, aph))
            self.assertEqual(ra.par_de_repositorios(aph), (ap, aph))
            self.assertEqual(ra.par_de_repositorios(REPO), (REPO.resolve(), REPO.resolve().parent / ra.NOMBRE_ESPEJO)
                             if REPO.name != ra.NOMBRE_ESPEJO else (REPO.resolve().parent / ra.NOMBRE_CANONICO,
                                                                    REPO.resolve()))

    def test_archivos_de_la_traduccion(self):
        """R22, paso 2: la compuerta ve todo lo que entra en el commit de la traducción: los módulos y las pruebas
        nuevas, el contrato y la configuración, cada archivo sellado (código y pruebas) que cambia
        CAMBIOS_AL_CODIGO_SELLADO.md, la carpeta de la propuesta (cuarta revisión, mayor 3 y menor 27: esta prueba la
        lee, así que entra en el commit), el envoltorio de geometría y su descargador con sus pruebas (y el módulo que
        importa el descargador) y config/componentes_compartidos.json."""
        import re
        self.assertTrue(set(ra.ARCHIVOS_PROPUESTA) <= set(ra.ARCHIVOS_TRADUCCION))
        cambios = (REPO / ra.CARPETA_PROPUESTA / "CAMBIOS_AL_CODIGO_SELLADO.md").read_text(encoding="utf-8")
        rutas_cambios = re.findall(r"^## `([^`]+)`", cambios, flags=re.M)
        self.assertGreaterEqual(len(rutas_cambios), 21)
        exigidas = {*(f"scripts_modelo_1km/v2/{m}" for m in MODULOS_NUEVOS), CONTRATO, CONFIG, *rutas_cambios,
                    *ra.ARCHIVOS_PROPUESTA,
                    "scripts_pipeline/geometria_sinca_ampliacion.py", "scripts_pipeline/descargar_sinca_ampliacion.py",
                    "scripts_pipeline/tests/test_geometria_sinca_ampliacion.py",
                    "scripts_pipeline/tests/test_descargar_sinca_ampliacion.py",
                    "scripts_pipeline/descargar_sinca_meteorologia.py",
                    "scripts_pipeline/tests/test_descargar_sinca_meteorologia.py", "config/componentes_compartidos.json"}
        self.assertEqual(sorted(exigidas - set(ra.ARCHIVOS_TRADUCCION)), [])
        self.assertEqual(len(ra.ARCHIVOS_TRADUCCION), len(set(ra.ARCHIVOS_TRADUCCION)))
        for rel in ra.ARCHIVOS_TRADUCCION:
            with self.subTest(rel=rel):
                self.assertTrue((REPO / rel).is_file())
                texto = (REPO / rel).read_text(encoding="utf-8")
                # quinta revisión, menor 18: el repositorio es público; ningún correo en ningún archivo de la traducción
                # (también el módulo meteorológico, su prueba y config/componentes_compartidos.json)
                self.assertEqual(CORREO.findall(texto), [])
                # las pruebas selladas que cambia CAMBIOS nombran las rutas personales como texto prohibido; el código
                # sellado que cambia, no: sólo se saltan las de tests/
                if rel in rutas_cambios and rel.startswith("scripts_modelo_1km/v2/tests/"):
                    continue
                self.assertNotIn("/" + "Users/", texto)

    def test_huellas_del_codigo_nuevo_declaradas(self):
        """Menor 43: red_de_monitores.codigo (en la configuración aplicada o en la propuesta) es la huella de cada
        módulo nuevo; se vuelve a fijar en cuanto el código cambia."""
        codigo = {k: v for k, v in config_con_la_red()["red_de_monitores"]["codigo"].items() if k != "nota"}
        self.assertEqual(sorted(codigo), sorted(f"scripts_modelo_1km/v2/{m}" for m in MODULOS_NUEVOS
                                                if not m.startswith("tests/")))
        for rel, esperado in codigo.items():
            with self.subTest(rel=rel):
                self.assertEqual(sha(REPO / rel), esperado)

    def test_la_configuracion_repite_las_constantes_del_codigo(self):
        """Cuarta revisión, menor 25: los nodos de red_de_monitores (en la configuración aplicada o en la propuesta) que
        repiten valores que el código toma de sus constantes son iguales a esas constantes."""
        import duplicados_v2 as dv
        import panel_red2_v2 as pr
        import reloj_sinca_v2 as rs
        red = config_con_la_red()["red_de_monitores"]
        self.assertEqual((red["lista_cerrada"]["archivos"], red["lista_cerrada"]["no_se_usan"]),
                         (ra.LISTA_CERRADA, ra.NO_SE_USAN))
        self.assertEqual(red["estaciones_nuevas"], {p: {u: list(c) for u, c in d.items()} for p, d in ra.NUEVAS.items()})
        self.assertEqual(red["red_resultante"], ra.RED_ESPERADA)
        self.assertEqual(red["fuera_por_coordenadas"]["series"][:2], list(reversed(ra.FUERA_POR_COORDENADAS)))
        self.assertTrue(red["fuera_por_coordenadas"]["clausula_518"].startswith(ra.CLAUSULA_518))
        self.assertIn(ra.CAMINO_518, red["fuera_por_coordenadas"]["clausula_518"])
        self.assertEqual((red["periodo"]["desde"], red["periodo"]["hasta"], red["periodo"]["sin_datos_nuevos"]),
                         (pr.DESDE, pr.HASTA, list(ra.SIN_DATOS_NUEVOS)))
        self.assertEqual({p: [float(x) for x in v] for p, v in red["calidad"]["rango_despues_de_convertir"].items()},
                         {p: list(v) for p, v in pr.RANGO.items()})
        self.assertEqual(red["ratificacion_t11_t13"]["valor"], ra.RATIFICACION_T11_T13)      # T13 (ronda 4, mayor 6)
        for k in ra.RATIFICABLES:
            self.assertIn(k, red["ratificacion_t11_t13"]["regla"])
        u = red["unidades"]
        self.assertEqual((u["vm_l_mol"], u["masas_molares"]), (uv.VM_25C_L_MOL, uv.MASA_MOLAR))
        self.assertEqual(u["snifa"], {k: round(v, 4) for k, v in uv.factores_snifa().items()})
        self.assertEqual(u["contraste_primera_corrida"]["sha256"], uv.SHA_CONTRASTE_PRIMERA)
        d = red["duplicados"]
        self.assertEqual((d["radio_km"], d["coincidencia"], d["minimo_horas_comunes"], d["tolerancia_relativa"]),
                         (dv.RADIO_KM, dv.COINCIDENCIA, dv.MINIMO_HORAS_COMUNES, dv.RTOL))
        ins = red["insumos_de_hoy"]
        self.assertEqual(ins["corte_utc"], pr.CORTE_INSUMOS_UTC)
        (copia,) = pr.COPIAS_DE_CORTE.values()
        c = ins["copias_de_corte"]["merra2_202610"]
        self.assertEqual((c["sha256"], c["sha256_manifiesto"], c["sha256_SHA256SUMS"]),
                         (copia["sha256"], copia["sha256_manifiesto"], copia["sha256_sumas"]))
        self.assertIsNone(pr.TROPOMI_MTIME_ANIOS)
        self.assertIn("None", ins["tropomi_por_fecha"]["parametro"])
        self.assertEqual(red["reloj"]["politica_temporal_sha256"], rs.SHA_POLITICA)
        self.assertEqual((red["coordenadas"]["actuales"]["sha256"], red["coordenadas"]["nuevas"]["sha256"]),
                         (ra.LISTA_CERRADA[ra.MAESTRO_ACTUALES], ra.LISTA_CERRADA[ra.MAESTRO_NUEVAS]))
        # quinta revisión, menor 22: versiones, huellas y lo que produjo cada una; el estado lo registra el anexo
        # (registro_de_la_red.procedencia_descarga), así que «estado» no se compara
        def sin_estado(d):
            return {**{k: v for k, v in d.items() if k != "versiones"},
                    "versiones": [{k: v for k, v in x.items() if k != "estado"} for x in d["versiones"]]}
        self.assertEqual(sin_estado(red["procedencia_descarga"]), sin_estado(ra.PROCEDENCIA_DESCARGA))
        self.assertIn("procedencia_descarga", red["registro_de_la_red"])
        # quinta revisión, menor 4: el límite de R7, declarado con sus años y regiones
        for texto in ("2015", "2017 a 2026", "2025 y 2026", "todo el año", "sin_transiciones_junto_a_civil"):
            self.assertIn(texto, red["reloj"]["limite"])
        self.assertIn(rs.HORAS_ESPECIALES["sha256"], red["reloj"]["convencion_de_la_etiqueta"]["zonas_horarias"])

    def test_decisiones_de_la_traduccion_citadas(self):
        """T1 a T13 (T11, T12 y T13 con su marca [delegada]; mientras no se ratifiquen, «ratifique»), con la huella del
        archivo de decisiones que cita el código (DECISIONES_TRADUCCION), la misma en la configuración y en el espejo.
        La huella no se fija a mano aquí (ronda 4, menor 24): el commit posterior a la ratificación la cambia en el
        código y en la configuración, y esta prueba la compara con el archivo."""
        for k in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12", "T13"):
            self.assertIn(k, ra.DECISIONES_TRADUCCION)
        for k in ("T11", "T12", "T13"):
            self.assertTrue(ra.DECISIONES_TRADUCCION[k].startswith("[delegada]"))
            if ra.RATIFICACION_T11_T13 is None:
                self.assertIn("ratifique", ra.DECISIONES_TRADUCCION[k])
        self.assertRegex(ra.DECISIONES_TRADUCCION["sha256"], r"^[0-9a-f]{64}$")
        if ra.RATIFICACION_T11_T13 is None:                                   # antes de ratificar, la de hoy
            self.assertEqual(ra.DECISIONES_TRADUCCION["sha256"], ra.DECISIONES_SIN_RATIFICAR)
        self.assertIn("contaminante", ra.DECISIONES_TRADUCCION["T4"])         # la unidad de T9
        enm = config_con_la_red()["contrato"]["enmiendas"][2]
        dec = enm["decisiones_de_traduccion"]
        self.assertEqual(dec["sha256"], ra.DECISIONES_TRADUCCION["sha256"])
        for k in ("T11", "T12", "T13"):
            self.assertTrue(dec[k].startswith("[delegada]"))
        self.assertIn("518", ra.CLAUSULA_518)
        # los textos que la compuerta exige en el espejo son los que cita la configuración
        citados = {enm["texto_del_bloque"]["archivo"]: enm["texto_del_bloque"]["sha256"],
                   enm["decisiones_del_autor"]["archivo"]: enm["decisiones_del_autor"]["sha256"],
                   dec["archivo"]: dec["sha256"]}
        self.assertEqual(citados, ra.ARCHIVOS_DEL_ESPEJO)
        if not DECISIONES.exists():
            self.skipTest("sin el repositorio de salud")
        for rel, esperado in ra.ARCHIVOS_DEL_ESPEJO.items():
            with self.subTest(rel=rel):
                self.assertEqual(sha(ESPEJO / rel), esperado)
        self.assertEqual(sha(DECISIONES), ra.DECISIONES_TRADUCCION["sha256"])
        texto = DECISIONES.read_text(encoding="utf-8")
        for k in ("T11", "T12", "T13"):
            self.assertIn(f"| {k} |", texto)
        self.assertIn("[delegada]", texto)


    def test_decisiones_iguales_en_el_codigo_y_en_la_configuracion(self):
        """Quinta revisión, menores 8 y 17: cada Tn del código (DECISIONES_TRADUCCION, que se copia en el json de cada
        panel) dice lo esencial que dice la configuración (contrato.enmiendas[2].decisiones_de_traduccion); en T8, que
        el derivado corre en amb_v2 y la huella de afg_lib.py; y están las trece, T2 incluida. T7 con su alcance literal
        (línea 22 del archivo de decisiones) y T12 y T13 [delegadas]."""
        esencial = {"T1": ("R16", "1e-6", "R9", "R10", "R11"), "T2": ("revisión independiente", "espejo", "commit local"),
                    "T3": ("MERRA-2 2026-10", "disco interno"), "T4": ("una sola", "todo SINCA", "inicio_mas_1h", "T9"),
                    "T5": ("MAIAC", "sha256", "antes del armado"), "T6": ("232 GB", "disco interno"),
                    "T7": ("T4 y T5", "§3 del bloque", "R21", "pliegues_v2_red2.json", "programas propios para la red 2",
                           "catalogo_sinca", "metricas_v2", "§8.6", "§9.4"),
                    "T8": ("afg_lib.py", "4391787a", "amb_v2", "procedencia"),
                    "T9": ("R7", "estación × contaminante × año local"),
                    "T10": ("reloj_sinca_v2.convertir", "preparar_sinca_modelado.py", "§3"),
                    "T11": ("[delegada]", "146", "138 OFFL 02.08.00", "8 RPRO 02.06.00", "TROPOMI_MTIME_ANIOS", "3.826"),
                    "T12": ("[delegada]", "al cerrar el panel", "R22.3", "v1_red2", "nodos hermanos", "destino_por_omision",
                            "§8.8 a §8.13", "47,998", "produccion.observaciones", "produccion.py"),
                    "T13": ("[delegada]", "T11, T12 y T13", "paso 0", "armado", "escritura única")}
        dec = config_con_la_red()["contrato"]["enmiendas"][2]["decisiones_de_traduccion"]
        self.assertEqual(sorted(k for k in ra.DECISIONES_TRADUCCION if k.startswith("T")),
                         sorted(k for k in dec if k.startswith("T")))
        self.assertEqual(sorted(esencial), sorted(k for k in dec if k.startswith("T")))
        for k, partes in esencial.items():
            codigo = ra.DECISIONES_TRADUCCION[k]
            codigo = " ".join(codigo) if isinstance(codigo, list) else codigo
            for parte in partes:
                with self.subTest(decision=k, parte=parte):
                    self.assertIn(parte, codigo)
                    self.assertIn(parte, dec[k])


class TrazaRed2Tests(unittest.TestCase):
    """Quinta revisión, mayores 1 y 2: la procedencia de cada artefacto de la red 2 (§0 del contrato)."""

    def test_trae_lo_que_pide_el_contrato(self):
        sys.path.insert(0, str(V2 / "tests"))
        from _sintetico_v2 import raices_temporales
        with raices_temporales("v2-traza-") as r:
            insumo = r.datos / "x.csv"
            insumo.write_text("a\n", encoding="utf-8")
            compuerta = {k: "rastreado" for k in ra.ARCHIVOS_TRADUCCION}
            t = ra.traza_red2(r, compuerta, {"x": insumo}, {"semilla": 42}, 1, programa="prueba")
        for clave in ("git", "codigo", "contrato", "config", "insumos", "bibliotecas", "python", "hilos", "semillas",
                      "programa_red2", "codigo_red2", "traduccion"):
            self.assertIn(clave, t)
        self.assertEqual(t["insumos"]["x"]["sha256"], hashlib.sha256(b"a\n").hexdigest())
        self.assertEqual(t["codigo_red2"], {f"scripts_modelo_1km/v2/{m}": sha(V2 / m) for m in ra.MODULOS_RED2})
        self.assertEqual(sorted(t["codigo_red2"]), sorted(config_con_la_red()["red_de_monitores"]["codigo"].keys() -
                                                        {"nota"}))
        tr = t["traduccion"]
        self.assertEqual((tr["commit"], tr["commit_espejo"]), ("desconocido", "desconocido"))     # sin git
        self.assertEqual(tr["ratificacion"], ra.RATIFICACION_T11_T13)       # ronda 5, menor 21: con qué ratificación
        with con_la_ratificacion():
            self.assertEqual(ra.traduccion_de(types.SimpleNamespace(repo=REPO), None)["ratificacion"], RATIFICACION)
        self.assertEqual(tr["compuerta"], {"archivos": len(ra.ARCHIVOS_TRADUCCION), "confirmada": True})
        self.assertNotIn("/" + "Users/", json.dumps(t, ensure_ascii=False))


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """git en un repositorio de prueba, con una identidad de juguete y sin ganchos ni firmas."""
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=prueba", "-c", "user.email=prueba", "-c",
                           "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "-c", "init.defaultBranch=main",
                           *args], capture_output=True, text=True, timeout=60, check=True)


class CompuertaConGitTests(unittest.TestCase):
    """Cuarta revisión, mayores 2 y 29 y menores 15, 26, 31 y 36: la compuerta de R22 con git real, en dos repositorios
    temporales hermanos (Air-Pollution y Air-Pollution-Health-Chile): la rama «modificado» de estado_git, el par fijo
    sin importar desde dónde se lanza, los textos de la auditoría del espejo y config/componentes_compartidos.json."""
    RUTAS = ("x/a.py", "config/componentes_compartidos.json")

    def setUp(self):
        if shutil.which("git") is None:
            self.skipTest("sin git")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.ap, self.aph = base / ra.NOMBRE_CANONICO, base / ra.NOMBRE_ESPEJO
        self.del_espejo = {"auditoria/dec.md": hashlib.sha256(b"decisiones").hexdigest()}
        for repo in (self.ap, self.aph):
            repo.mkdir()
            git(repo, "init", "-q")
            self.escribir(repo, "uno")
        (self.aph / "auditoria").mkdir()
        (self.aph / "auditoria" / "dec.md").write_text("decisiones", encoding="utf-8")
        for repo in (self.ap, self.aph):
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "--no-verify", "-m", "traducción")

    def escribir(self, repo: Path, texto: str, componentes: str | None = None) -> None:
        (repo / "x").mkdir(exist_ok=True)
        (repo / "x" / "a.py").write_text(texto, encoding="utf-8")
        (repo / "config").mkdir(exist_ok=True)
        registrado = hashlib.sha256((componentes or texto).encode()).hexdigest()
        (repo / "config" / "componentes_compartidos.json").write_text(json.dumps(
            {"grupos": [{"nombre": "x", "modo": "identico", "sha256": {"x/a.py": registrado}}]}), encoding="utf-8")

    def guarda(self, desde: Path, ratificacion: bool | None = False, cfg: dict | None = None) -> dict:
        """La compuerta con git real; la ratificación (T13) se prueba aparte (``test_con_git_exige_la_ratificacion``)."""
        return ra.exigir_traduccion_confirmada(types.SimpleNamespace(repo=desde), cfg or {"red_de_monitores": {}},
                                               rutas=self.RUTAS, del_espejo=self.del_espejo, ratificacion=ratificacion)

    def test_con_git_exige_la_ratificacion(self):
        """T13 [delegada] (ronda 4, mayor 6): con git real y la traducción confirmada en los dos, la compuerta (que
        llaman sólo los programas del armado) se detiene sin la ratificación de T11, T12 y T13, se lance desde AP o
        desde el espejo, y sigue con ella."""
        for desde in (self.ap, self.aph):
            with self.subTest(desde=desde.name), self.assertRaises(SystemExit) as e:
                self.guarda(desde, ratificacion=None)
            self.assertIn("T13", str(e.exception))
            with self.subTest(desde=desde.name, ratificada=True), con_la_ratificacion():
                self.assertEqual(self.guarda(desde, ratificacion=None, cfg=cfg_ratificada()),
                                 {k: "rastreado" for k in self.RUTAS})

    def test_confirmada_en_los_dos_desde_los_dos(self):
        for desde in (self.ap, self.aph):
            with self.subTest(desde=desde.name):
                self.assertEqual(self.guarda(desde), {k: "rastreado" for k in self.RUTAS})

    def test_un_cambio_en_ap_detiene_desde_los_dos_lados(self):
        """El caso del revisor: todo confirmado más un cambio sin confirmar en un archivo de AP; lanzada desde AP o desde
        el espejo, la compuerta se detiene («modificado»)."""
        (self.ap / "x" / "a.py").write_text("uno, cambiado", encoding="utf-8")
        self.assertEqual(ra.estado_git(self.ap, ["x/a.py"]), {"x/a.py": "modificado"})
        for desde in (self.ap, self.aph):
            with self.subTest(desde=desde.name), self.assertRaises(SystemExit) as e:
                self.guarda(desde)
            self.assertIn("modificado", str(e.exception))

    def test_un_cambio_en_el_espejo_detiene_desde_los_dos_lados(self):
        for repo in (self.ap, self.aph):
            self.escribir(repo, "dos")
        git(self.ap, "commit", "-q", "--no-verify", "-am", "dos")            # confirmado sólo en AP
        self.assertEqual(ra.estado_git(self.aph, ["x/a.py"]), {"x/a.py": "modificado"})
        for desde in (self.ap, self.aph):
            with self.subTest(desde=desde.name), self.assertRaises(SystemExit) as e:
                self.guarda(desde)
            self.assertIn("modificado", str(e.exception))

    def test_las_decisiones_sin_rastrear_en_el_espejo(self):
        (self.aph / "auditoria" / "nuevas.md").write_text("ratificación", encoding="utf-8")
        self.del_espejo["auditoria/nuevas.md"] = hashlib.sha256("ratificación".encode()).hexdigest()
        for desde in (self.ap, self.aph):
            with self.subTest(desde=desde.name), self.assertRaises(SystemExit) as e:
                self.guarda(desde)
            self.assertIn("sin_rastrear", str(e.exception))

    def test_componentes_sin_regenerar(self):
        for repo in (self.ap, self.aph):
            self.escribir(repo, "dos", componentes="uno")                    # el manifiesto quedó con la huella vieja
            git(repo, "commit", "-q", "--no-verify", "-am", "dos")
        with self.assertRaises(SystemExit) as e:
            self.guarda(self.ap)
        self.assertIn("componentes_compartidos.json", str(e.exception))
        for repo in (self.ap, self.aph):
            self.escribir(repo, "dos")
            git(repo, "commit", "-q", "--no-verify", "-am", "regenerado")
        self.assertEqual(ra.verificar_componentes(self.ap, self.RUTAS), {"x/a.py": hashlib.sha256(b"dos").hexdigest()})
        self.assertEqual(self.guarda(self.aph), {k: "rastreado" for k in self.RUTAS})


    def test_la_configuracion_confirmada_en_los_dos(self):
        """Quinta revisión, menor 12: exigir_config_confirmada (que llama exigir_registro antes de cualquier ajuste)
        exige config_v2.json rastreado y sin cambios en AP y, con los mismos bytes, en el espejo, desde los dos lados."""
        rel = "scripts_modelo_1km/v2/config_v2.json"
        for repo in (self.ap, self.aph):
            (repo / rel).parent.mkdir(parents=True)
            (repo / rel).write_text('{"red_de_monitores": {}}', encoding="utf-8")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "--no-verify", "-m", "anexo")
        r = lambda desde: types.SimpleNamespace(repo=desde, config=desde / rel)        # noqa: E731
        for desde in (self.ap, self.aph):
            with self.subTest(desde=desde.name):
                self.assertEqual(ra.exigir_config_confirmada(r(desde)), {rel: "rastreado"})
        (self.aph / rel).write_text('{"red_de_monitores": {"registro_de_la_red": {}}}', encoding="utf-8")   # pegado
        for desde in (self.ap, self.aph):
            with self.subTest(desde=desde.name, cambio="espejo"), self.assertRaises(SystemExit) as e:
                ra.exigir_config_confirmada(r(desde))
            self.assertIn("confirmado en git", str(e.exception))
        for repo in (self.ap, self.aph):
            (repo / rel).write_text('{"red_de_monitores": {"registro_de_la_red": {}}}', encoding="utf-8")
        with self.assertRaises(SystemExit) as e:                             # los dos iguales, sin confirmar
            ra.exigir_config_confirmada(r(self.ap))
        self.assertIn("modificado", str(e.exception))
        for repo in (self.ap, self.aph):
            git(repo, "commit", "-q", "--no-verify", "-am", "anexo confirmado")
        self.assertEqual(ra.exigir_config_confirmada(r(self.aph)), {rel: "rastreado"})
        (self.aph / rel).write_text('{"red_de_monitores": {"registro_de_la_red": {"x": 1}}}', encoding="utf-8")
        git(self.aph, "commit", "-q", "--no-verify", "-am", "otro anexo, confirmado sólo en el espejo")
        for desde in (self.ap, self.aph):                                    # confirmados en los dos, pero distintos
            with self.subTest(desde=desde.name, cambio="otros bytes"), self.assertRaises(SystemExit) as e:
                ra.exigir_config_confirmada(r(desde))
            self.assertIn("no es el mismo en el espejo", str(e.exception))

    def test_la_traduccion_de_cada_artefacto(self):
        """Quinta revisión, mayor 2: traduccion_de da el último commit que tocó los archivos de la traducción en AP y en
        el espejo (no cambia si otro frente confirma otra cosa) y los HEAD de los dos."""
        from unittest import mock
        with mock.patch.object(ra, "ARCHIVOS_TRADUCCION", self.RUTAS), \
                mock.patch.object(ra, "ARCHIVOS_DEL_ESPEJO", self.del_espejo):
            antes = ra.traduccion_de(types.SimpleNamespace(repo=self.ap), self.guarda(self.ap))
            cabeza = git(self.ap, "rev-parse", "HEAD").stdout.strip()
            self.assertEqual((antes["commit"], antes["head"], antes["commit_espejo"]),
                             (cabeza, cabeza, git(self.aph, "rev-parse", "HEAD").stdout.strip()))
            (self.ap / "otro.txt").write_text("de otro frente", encoding="utf-8")
            git(self.ap, "add", "otro.txt")
            git(self.ap, "commit", "-q", "--no-verify", "-m", "otro frente")
            despues = ra.traduccion_de(types.SimpleNamespace(repo=self.aph), None)
            self.assertEqual((despues["commit"], despues["huella_archivos"]), (antes["commit"], antes["huella_archivos"]))
            self.assertNotEqual(despues["head"], antes["head"])
            self.escribir(self.ap, "tres")
            git(self.ap, "commit", "-q", "--no-verify", "-am", "traducción nueva")
            self.assertNotEqual(ra.traduccion_de(types.SimpleNamespace(repo=self.ap), None)["commit"], antes["commit"])


class ListaCerradaTests(unittest.TestCase):
    def test_falla_cerrado(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "a").mkdir()
            (d / "a" / "x.csv").write_text("1\n")
            lista = {"a/x.csv": hashlib.sha256(b"1\n").hexdigest()}
            self.assertEqual(ra.verificar_lista_cerrada(d, lista), lista)
            (d / "a" / "x.csv").write_text("2\n")
            with self.assertRaises(SystemExit):
                ra.verificar_lista_cerrada(d, lista)
            with self.assertRaises(SystemExit):
                ra.verificar_lista_cerrada(d, {"a/falta.csv": "0" * 64})

    def test_huellas_completas(self):
        for rel, h in ra.LISTA_CERRADA.items():
            with self.subTest(archivo=rel):
                self.assertRegex(h, r"^[0-9a-f]{64}$")
                self.assertFalse(rel.startswith("/"))


class MaestrosTests(unittest.TestCase):
    def maestro(self, codigos, grupo):
        return pd.DataFrame({"estacion": codigos, "nombre": codigos, "region_sinca": "RM", "lat": -33.0, "lon": -70.6,
                             "cod_comuna": pd.array([13101] * len(codigos), dtype="Int64"), "qc_comuna": "coincide",
                             "grupo": grupo, "red": "sinca"})

    def test_codigos_unicos(self):
        m = ra.combinar_maestros(self.maestro(["801", "802"], "actual"), self.maestro(["N1"], "nueva"))
        self.assertEqual(list(m["estacion"]), ["801", "802", "N1"])
        with self.assertRaises(ValueError):
            ra.combinar_maestros(self.maestro(["801"], "actual"), self.maestro(["801"], "nueva"))

    def test_propietario(self):
        self.assertEqual(ra.tipo_propietario("Ministerio del Medio Ambiente", "sin calificación publicada"), "pública")
        self.assertEqual(ra.tipo_propietario("Sub Secretaría del Medio Ambiente", None), "pública")
        self.assertEqual(ra.tipo_propietario("ENAP", "no definida"), "empresa")
        self.assertEqual(ra.tipo_propietario("Ministerio del Medio Ambiente", "Privada"), "empresa")
        self.assertEqual(ra.tipo_propietario("NO INFORMADO", None), "no informado")

    def test_no_informado_explicado(self):
        """Las fichas sin calificación ni propietario («NO INFORMADO») no las alcanza T1(3): quedan aparte y el módulo
        lo explica (R10 sólo pide registrar los campos de la ficha)."""
        self.assertEqual(ra.tipo_propietario("NO INFORMADO", "sin calificación publicada"), "no informado")
        self.assertIn("T1(3)", ra.__doc__)
        self.assertIn("nunca entra al §9", ra.__doc__)

    def test_series_esperadas_de_la_red_2(self):
        """Mayor 1 y 10: la red 2 que tiene que traer el derivado es la de los manifiestos, restringida a las
        estaciones con coordenada usable en los maestros de R8; la diferencia se muestra."""
        sys.path.insert(0, str(V2 / "tests"))
        from test_reloj_sinca_v2 import RELOJES, datos_red2
        with tempfile.TemporaryDirectory() as tmp:
            datos = datos_red2(Path(tmp) / "datos")
            esperadas = ra.series_esperadas_red2(datos)
            self.assertEqual(esperadas, set(RELOJES))
            sin_i1 = ra.combinar_maestros(ra.maestro_red2(datos).query("estacion != 'I1'"),
                                          ra.maestro_red2(datos).iloc[0:0])
            self.assertEqual(ra.series_esperadas_red2(datos, sin_i1), set(RELOJES) - {("I1", "o3")})
        self.assertEqual(ra.exigir_la_red_2(set(RELOJES), set(RELOJES), "x")["series"], 4)
        with self.assertRaises(SystemExit) as e:
            ra.exigir_la_red_2({("F1", "pm25"), ("Z9", "no2")}, set(RELOJES), "prueba")
        self.assertIn("faltan 3", str(e.exception))
        self.assertIn("Z9:no2", str(e.exception))

    def test_red_resultante(self):
        series = pd.DataFrame({"estacion": ["801", "802", "N1", "N2", "N3"], "contaminante": "no2"})
        unidades = pd.DataFrame({"estacion": ["801", "802", "N1", "N2", "N3"], "contaminante": "no2",
                                 "entra": [True, False, True, True, False]})
        maestro = ra.combinar_maestros(self.maestro(["801", "802"], "actual"), self.maestro(["N1", "N3"], "nueva"))
        r = ra.red_resultante(series, unidades, maestro, snifa_no2=3)["no2"]
        self.assertEqual((r["actuales"], r["nuevas"], r["snifa"], r["total"]), (1, 1, 3, 5))
        self.assertEqual(r["fuera_por_unidad"], ["802", "N3"])
        self.assertEqual(r["fuera_por_coordenadas"], ["N2"])


class DatosRealesTests(unittest.TestCase):
    """Cabeceras, identidades, conteos y huellas: ningún valor de concentración."""

    def setUp(self):
        self.datos = rv.RutasV2.desde_entorno().datos
        if not (self.datos / ra.MANIFIESTO_NUEVAS).exists():
            self.skipTest("sin el disco de datos")

    def test_lista_cerrada(self):
        ra.verificar_lista_cerrada(self.datos)

    def test_maestros_de_r8(self):
        m = ra.maestro_red2(self.datos)
        self.assertEqual(m["grupo"].value_counts().to_dict(), {"actual": 109, "nueva": 106})
        for e in ra.FUERA_POR_COORDENADAS:
            self.assertNotIn(e, set(m["estacion"]))
        self.assertIn("207", set(m["estacion"]))
        f = ra.fichas_red2(self.datos)
        sin_codigo = pd.read_csv(self.datos / ra.FICHAS, dtype=str, usecols=["id_sinca", "estacion"])
        self.assertEqual(sorted(sin_codigo.loc[sin_codigo["estacion"].isna(), "id_sinca"]), list(ra.FICHAS_SIN_CODIGO))
        conf = f[f["configurada"] == "si"]["tipo_propietario"].value_counts().to_dict()
        self.assertEqual(conf, {"pública": 71, "empresa": 38})

    def test_series_y_estaciones_nuevas(self):
        s = ra.series_contrato(self.datos)
        n = s[s["grupo"] == "nueva"]
        for pol, por_unidad in ra.NUEVAS.items():
            todas = sorted(c for v in por_unidad.values() for c in v)
            with self.subTest(contaminante=pol):
                self.assertEqual(sorted(n.loc[n["contaminante"] == pol, "estacion"]), todas)
        nuevas = pd.read_csv(self.datos / ra.MANIFIESTO_NUEVAS, dtype=str, usecols=["estacion", "contaminante",
                                                                                     "unidad_ficha"])
        for pol in ("no2", "o3"):
            u = nuevas[nuevas["contaminante"] == pol].set_index("estacion")["unidad_ficha"].map(uv.normalizar_unidad)
            for clave, rot in (("ppb", "ppb"), ("µg/m³N", "µg/m³N"), ("sin", "(sin unidad)")):
                with self.subTest(contaminante=pol, rotulo=clave):
                    self.assertEqual(sorted(u[u == rot].index), sorted(ra.NUEVAS[pol][clave]))
        act = set(s.loc[s["origen"] == "actualizacion", "estacion"])
        sell = set(s.loc[s["origen"] == "sellado", "estacion"])
        self.assertEqual(sorted(sell - act), sorted(ra.SIN_DATOS_NUEVOS))
        self.assertLessEqual(s.loc[s["origen"] == "actualizacion", "hasta"].max(), "2026-10-24")

    def test_series_esperadas_reales(self):
        """La red 2 que tiene que traer el derivado: 262 series (109 de PM2,5, 79 de NO2 y 74 de O3), sin la 518; es
        el plan de derivado_red2_v2 (comprobado el 2026-10-26, sólo identidades)."""
        e = ra.series_esperadas_red2(self.datos)
        por = {p: sum(1 for _, q in e if q == p) for p in ra.CONTAMINANTES}
        self.assertEqual((len(e), por), (262, {"pm25": 109, "no2": 79, "o3": 74}))
        self.assertNotIn("518", {x for x, _ in e})

    def test_procedencia_de_la_descarga(self):
        """Cuarta revisión, menores 24, 30 y 35: la versión y la huella del descargador que produjo cada archivo de la
        lista cerrada que la registra (sólo las columnas y los campos script_*; ningún valor)."""
        for v in ra.PROCEDENCIA_DESCARGA["versiones"]:
            for rel, n in v["produjo"].items():
                with self.subTest(rel=rel):
                    self.assertIn(rel, ra.LISTA_CERRADA)
                    if rel.endswith(".json"):
                        c = json.loads((self.datos / rel).read_text(encoding="utf-8"))
                        self.assertEqual((c["script_version"], c["script_sha256"]),
                                         (v["script_version"], v["script_sha256"]))
                    else:
                        m = pd.read_csv(self.datos / rel, dtype=str, usecols=["script_version", "script_sha256"])
                        self.assertEqual(m.groupby(["script_version", "script_sha256"]).size().to_dict(),
                                         {(v["script_version"], v["script_sha256"]): n})
        hoy = next(v for v in ra.PROCEDENCIA_DESCARGA["versiones"] if v["script_version"] == "1.1.0")
        self.assertEqual(hoy["script_sha256"], SELLADOS["scripts_pipeline/descargar_sinca_ampliacion.py"])

    def test_red_resultante_del_bloque(self):
        contraste = Path(os.environ.get(
            "AIR_POLLUTION_CONTRASTE_UNIDADES",
            V2.parents[2] / "Air-Pollution-Health-Chile" / "auditoria" / "20261024" / "sinca_al_modelo" /
            "contraste_unidades_cams.csv"))
        if not contraste.exists():
            self.skipTest("sin la primera corrida del contraste")
        un, _ = uv.unidades_red2(self.datos, contraste, uv.SHA_CONTRASTE_PRIMERA)
        red = ra.red_resultante(ra.series_contrato(self.datos), un, ra.maestro_red2(self.datos))
        for pol, esperado in ra.RED_ESPERADA.items():
            with self.subTest(contaminante=pol):
                self.assertEqual({k: red[pol][k] for k in esperado}, esperado)


if __name__ == "__main__":
    unittest.main()
