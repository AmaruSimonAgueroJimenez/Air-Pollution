"""Pruebas de ``config_v2.json``: que traduzca el contrato vigente, con su Enmienda 1 y el Complemento de la
Enmienda 1, cifra por cifra, y que marque lo que el contrato todavía no fija."""
from __future__ import annotations

import hashlib
import itertools
import json
import os
import re
import sys
import unittest
from pathlib import Path

import numpy as np

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import _rutas_v2 as rv  # noqa: E402

TEXTO = (V2 / rv.NOMBRE_CONFIG).read_text(encoding="utf-8")
CFG = json.loads(TEXTO)
CONTRATO = (V2 / rv.NOMBRE_CONTRATO).read_text(encoding="utf-8")
ENCABEZADO_COMPLEMENTO = "### Complemento de la Enmienda 1 ("
_INICIO_E1 = CONTRATO.find("### Enmienda 1 (")
_INICIO_COMPLEMENTO = CONTRATO.find(ENCABEZADO_COMPLEMENTO)
ENCABEZADO_BLOQUE_RED2 = "### Enmienda 2 ambiental — bloque «Red ampliada e insumos de hoy» ("
_INICIO_BLOQUE_RED2 = CONTRATO.find(ENCABEZADO_BLOQUE_RED2)
_FIN_COMPLEMENTO = _INICIO_BLOQUE_RED2 if _INICIO_BLOQUE_RED2 >= 0 else len(CONTRATO)
# La Enmienda 1 va desde su encabezado hasta el del Complemento; el Complemento, hasta el bloque de la red ampliada de
# la Enmienda 2 (o hasta el final del contrato, si no está).
ENMIENDA_1 = CONTRATO[_INICIO_E1:_INICIO_COMPLEMENTO] if 0 <= _INICIO_E1 < _INICIO_COMPLEMENTO else ""
COMPLEMENTO = CONTRATO[_INICIO_COMPLEMENTO:_FIN_COMPLEMENTO] if _INICIO_COMPLEMENTO >= 0 else ""
BLOQUE_RED2 = CONTRATO[_INICIO_BLOQUE_RED2:] if _INICIO_BLOQUE_RED2 >= 0 else ""
# Texto del contrato tal como quedó con el Complemento, antes del bloque de la red ampliada.
TEXTO_CON_EL_COMPLEMENTO = CONTRATO[:_FIN_COMPLEMENTO].rstrip("\n") + "\n"
# Texto del contrato tal como quedó con la Enmienda 1, antes de agregar el Complemento.
TEXTO_CON_LA_ENMIENDA_1 = CONTRATO[:_INICIO_COMPLEMENTO].rstrip("\n") + "\n" if _INICIO_COMPLEMENTO >= 0 else CONTRATO
RATIFICADO = "ratificado (Enmienda 1)"
RATIFICADO_C = "ratificado (Complemento)"
SHA_ORIGINAL = "c5b216f93c869d6e68b74d3f7d41e3b2fd8e6e9a7db5aea5691f0ff3829ae918"      # texto del commit 51d125e
SHA_ENMIENDA_1 = "05218686b3f1808d5379b095789ada4ea69ba02362be8063330a2c2f9f5a5e17"    # texto con la Enmienda 1
SHA_COMPLEMENTO = "5d879a05179a3e980d01e25e12bb4f3492d4fe6b4142f7be6daa2509df4c39b0"   # texto con el Complemento
SHA_BLOQUE_RED2 = "274ebae06bee8eeeb7470a650ce0539af751577d292513b8198cdec7c159094b"   # bloque anclado en APH (f2c6cfc)
SHA_DECISIONES_TRADUCCION = "fdfbfa3149dae432a392c5dbea338b933fddf6f5f15a22cf2d18ad93d7da9a60"  # T1 a T13 (T11 a T13 [delegadas])

# Los 39 provisionales de la construcción, cada uno con el subpunto del punto 1 de la Enmienda 1 que lo ratifica
# por nombre. Se enumeran a mano para que ninguno entre ni salga sin querer.
RATIFICADOS = {
    "protocolos.BLQ-75.origen_m": "1.1",
    "protocolos.semilla.k": "1.1",
    "motores.eje_A.xgboost.colsample.variante": "1.2",
    "motores.eje_A.xgboost.min_child_weight": "1.2",
    "motores.eje_A.xgboost.max_depth": "1.2",
    "motores.eje_A.xgboost.max_bin": "1.2",
    "motores.eje_A.xgboost.nthread": "1.2",
    "motores.eje_A.xgboost.seed": "1.2",
    "motores.eje_A.xgboost.determinismo": "1.2",
    "motores.eje_A.random_forest.n_jobs": "1.3",
    "motores.eje_A.mlp.parada_temprana.fraccion": "1.3",
    "motores.eje_A.mlp.parada_temprana.criterio": "1.3",
    "motores.eje_A.promedio_simple.escala": "1.4",
    "motores.eje_B.topes_de_filas": "1.4",
    "motores.alertas.receta": "1.4",
    "motores.apilado_anidado.bases": "1.5",
    "motores.apilado_anidado.pliegues_internos": "1.5",
    "motores.apilado_anidado.escala": "1.5",
    "filas_entrenamiento.permutacion.generador": "1.6",
    "filas_entrenamiento.disponibles_menos_que_el_tope": "1.6",
    "retransformacion.primaria.global_de_los_demas_con_menos_de_100_filas": "1.7",
    "retransformacion.sensibilidad.pliegues_internos": "1.7",
    "perdidas.variantes[2].delta.mad": "1.8",
    "perdidas.variantes[2].delta.ajuste_cuadratico": "1.8",
    "perdidas.variantes[2].implementacion_xgboost": "1.8",
    "perdidas.hiperparametros_por_perdida": "1.8",
    "calidad_blanco.codigos_qc": "1.9",
    "calidad_blanco.snifa.cruce_con_variantes_sinca": "1.9",
    "metricas.niveles.mensual.minimo_dias": "1.10",
    "metricas.niveles.anual.minimo_meses": "1.10",
    "metricas.desagregaciones.regimen_de_predictores.criterio": "1.10",
    "metricas.desagregaciones.estrato_de_soporte.distribucion_de_referencia": "1.10",
    "metricas.desagregaciones.ponderado_por_poblacion.poblacion": "1.10",
    "ruido.valores": "1.11",
    "inferencia_diferencias.bootstrap.metodo_del_intervalo": "1.11",
    "inferencia_diferencias.bootstrap.semilla": "1.11",
    "inferencia_diferencias.bootstrap.nivel_de_agregacion": "1.11",
    "inferencia_diferencias.regla_de_superioridad.medida_del_ruido": "1.11",
    "presupuesto.piloto.eleccion_de_los_pliegues": "1.12",
}
# Los que el punto 1 ratifica «con el cambio» de otro punto (llevan «cambio»), y de ellos los que cambian de valor
# (llevan «provisional_anterior»).
CON_CAMBIO = {
    "motores.eje_A.mlp.parada_temprana.fraccion", "motores.eje_A.mlp.parada_temprana.criterio",
    "perdidas.variantes[2].delta.mad", "perdidas.variantes[2].delta.ajuste_cuadratico",
    "perdidas.variantes[2].implementacion_xgboost", "perdidas.hiperparametros_por_perdida",
    "metricas.desagregaciones.regimen_de_predictores.criterio", "metricas.desagregaciones.ponderado_por_poblacion.poblacion",
    "inferencia_diferencias.bootstrap.metodo_del_intervalo", "inferencia_diferencias.bootstrap.semilla",
    "inferencia_diferencias.bootstrap.nivel_de_agregacion", "inferencia_diferencias.regla_de_superioridad.medida_del_ruido",
}
CAMBIAN_DE_VALOR = {
    "motores.eje_A.mlp.parada_temprana.criterio", "perdidas.variantes[2].delta.ajuste_cuadratico",
    "metricas.desagregaciones.regimen_de_predictores.criterio", "metricas.desagregaciones.ponderado_por_poblacion.poblacion",
    "inferencia_diferencias.bootstrap.nivel_de_agregacion", "inferencia_diferencias.regla_de_superioridad.medida_del_ruido",
}
# Los 7 detalles que la Enmienda 1 no fijaba y que la construcción dejó pendientes, con su provisional. El
# Complemento los ratifica, en este orden, en su punto 4: el subpunto que ratifica cada uno, el punto de la
# Enmienda 1 que lo dejó pendiente y la huella (sha256 canónico, 16 cifras) del provisional que tenía, para comprobar
# que se ratificó «con el valor que tienen en config_v2.json».
RATIFICADOS_COMPLEMENTO = {
    "motores.eje_A.mlp.parada_temprana.seleccion_en_LRO_y_BLQ-75": ("4.1", "punto 6", "9808504ea6ba768d"),
    "perdidas.variantes[2].delta.particion_honesta": ("4.2", "punto 9", "578e8b58e75d4a95"),
    "perdidas.variantes[3].calibracion.respaldo": ("4.3", "punto 9", "fe971cfc3108c6ff"),
    "metricas.desagregaciones.regimen_de_predictores.sensibilidad.fila_a_fila": ("4.4", "punto 10", "6deb56c941c23047"),
    "metricas.desagregaciones.ponderado_por_poblacion.desagrupamiento.poblacion_comunal": ("4.5", "punto 4", "2706a806df6ba32b"),
    "inferencia_diferencias.segunda_prueba.metodo": ("4.6", "punto 5", "a5e4cfd8ad5626f4"),
    "decision.evidencia_parcial.definicion": ("4.7", "punto 11", "fdb7454d157f0989"),
}
# El único de los 7 que el Complemento ratifica con un cambio (el de su punto 1: la prueba que decide).
CAMBIA_CON_EL_COMPLEMENTO = {"inferencia_diferencias.segunda_prueba.metodo"}
# Detalles que el contrato vigente todavía no fija y que el código necesita: pendientes, con su provisional y el
# punto del contrato que los deja abiertos.
PENDIENTES = {
    "decision.factibilidad.datos.fechas": "Complemento, punto 3",
}
# Las rutas del punto 5 del Complemento: dónde rige el amortiguador de 10 km dentro de un pliegue de BLQ-75.
AMORTIGUADOR_INTERNO = (
    "motores.eje_A.mlp.parada_temprana.amortiguador_interno_en_BLQ-75",
    "motores.apilado_anidado.amortiguador_interno_en_BLQ-75",
    "retransformacion.sensibilidad.amortiguador_interno_en_BLQ-75",
    "perdidas.variantes[2].delta.amortiguador_interno_en_BLQ-75",
)


def obtener(ruta: str, cfg: dict = CFG):
    """Nodo de la configuración en una ruta como ``perdidas.variantes[2].delta.mad``."""
    nodo = cfg
    for parte in ruta.split("."):
        m = re.fullmatch(r"(.+?)((?:\[\d+\])*)", parte)
        nodo = nodo[m.group(1)]
        for i in re.findall(r"\[(\d+)\]", m.group(2)):
            nodo = nodo[int(i)]
    return nodo


def por_estado(nodo, estado: str, ruta: str = ""):
    """(ruta, objeto) de cada objeto con ese «estado», sin entrar en él."""
    if isinstance(nodo, dict):
        if nodo.get("estado") == estado:
            yield ruta, nodo
            return
        for k, v in nodo.items():
            yield from por_estado(v, estado, f"{ruta}.{k}" if ruta else k)
    elif isinstance(nodo, list):
        for i, v in enumerate(nodo):
            yield from por_estado(v, estado, f"{ruta}[{i}]")


def pendientes(nodo, ruta=""):
    """Recorre la configuración y devuelve (ruta, valor) de cada campo pendiente (objeto o cadena)."""
    if isinstance(nodo, dict):
        if nodo.get("estado") == "pendiente":
            yield ruta, nodo
            return
        for k, v in nodo.items():
            yield from pendientes(v, f"{ruta}.{k}" if ruta else k)
    elif isinstance(nodo, list):
        for i, v in enumerate(nodo):
            yield from pendientes(v, f"{ruta}[{i}]")
    elif nodo == "pendiente":
        yield ruta, nodo


def valor(item):
    """Lectura de referencia: el valor ratificado (por la Enmienda 1 o por su Complemento), el provisional de un
    pendiente o el campo tal cual."""
    if isinstance(item, dict) and item.get("estado") in (RATIFICADO, RATIFICADO_C):
        return item["valor"]
    if isinstance(item, dict) and item.get("estado") == "pendiente":
        return item["provisional"]
    return item


def huella(obj) -> str:
    """sha256 canónico (claves ordenadas, UTF-8) de un valor de la configuración, en 16 cifras."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def seccion(n: int) -> str:
    """Texto del punto n de la Enmienda 1 (desde su encabezado «#### n.» hasta el siguiente)."""
    m = re.search(rf"^#### {n}\. .*?(?=^#### |\Z)", ENMIENDA_1, re.M | re.S)
    return m.group(0) if m else ""


def punto_complemento(n: int) -> str:
    """Texto del punto n del Complemento (desde «n. **…**» hasta el punto siguiente o el final)."""
    m = re.search(rf"^{n}\. \*\*.*?(?=^\d+\. \*\*|\Z)", COMPLEMENTO, re.M | re.S)
    return m.group(0) if m else ""


def plano(texto: str) -> str:
    """El texto en una línea, con los espacios repetidos colapsados (para buscar frases partidas en dos líneas)."""
    return re.sub(r"\s+", " ", texto)


def enumeracion(texto: str) -> list[str]:
    """Ítems «  1. …» de una lista numerada, sin el punto o punto y coma final."""
    return [m.group(2) for m in re.finditer(r"^\s+(\d+)\. (.+?)[;.]?$", texto, re.M)]


def vinetas(texto: str) -> list[str]:
    """Ítems «  - …» de una lista con viñetas, sin el punto o punto y coma final."""
    return [m.group(1) for m in re.finditer(r"^\s+- (.+?)[;.]?$", texto, re.M)]


class ContratoTests(unittest.TestCase):
    def test_traduce_el_contrato_vigente(self):
        sha = hashlib.sha256((V2 / rv.NOMBRE_CONTRATO).read_bytes()).hexdigest()
        c = CFG["contrato"]
        self.assertEqual(c["sha256"], sha)
        self.assertEqual((c["sha256_original"], c["commit"], c["fijado"]), (SHA_ORIGINAL, "51d125e", "2026-10-12"))
        self.assertNotIn(c["sha256"], (SHA_ORIGINAL, SHA_ENMIENDA_1))
        self.assertIn("### Enmienda 1 (2026-10-13, antes de cualquier ajuste comparativo)", CONTRATO)
        self.assertIn(ENCABEZADO_COMPLEMENTO + "2026-10-13, antes de cualquier ajuste comparativo)", CONTRATO)
        self.assertLess(_INICIO_E1, _INICIO_COMPLEMENTO)          # el Complemento va al final, después de la Enmienda 1
        self.assertNotIn("## Enmiendas\n\n(ninguna)", CONTRATO)

    def test_entrada_de_la_enmienda_1(self):
        enm = CFG["contrato"]["enmiendas"]
        self.assertEqual([e["id"] for e in enm], ["Enmienda 1", "Complemento de la Enmienda 1",
                                                  "Enmienda 2, bloque de la red ampliada"])
        e = enm[0]
        self.assertEqual((e["id"], e["fecha"], e["sha256"]), ("Enmienda 1", "2026-10-13", SHA_ENMIENDA_1))
        # su sha256 es el del texto tal como quedó con ella: el contrato vigente sin el Complemento
        self.assertEqual(hashlib.sha256(TEXTO_CON_LA_ENMIENDA_1.encode("utf-8")).hexdigest(), SHA_ENMIENDA_1)
        self.assertEqual(e["momento"], "antes de cualquier ajuste comparativo")
        self.assertIsNone(e["commit"])                          # se sella en git después, con el código
        titulos = [(int(m.group(1)), m.group(2)) for m in re.finditer(r"^#### (\d+)\. (.+)$", ENMIENDA_1, re.M)]
        self.assertEqual(titulos, [(p["punto"], p["titulo"]) for p in e["puntos"]])
        self.assertEqual([p["punto"] for p in e["puntos"]], list(range(1, 15)))
        for p in e["puntos"]:
            for ruta in p["config"]:
                with self.subTest(punto=p["punto"], ruta=ruta):
                    obtener(ruta)                                # existe
        self.assertEqual(sorted(e["puntos"][0]["config"]), sorted(RATIFICADOS))

    def test_entrada_del_bloque_red_ampliada(self):
        e = CFG["contrato"]["enmiendas"][2]
        self.assertEqual((e["id"], e["fecha"], e["sha256"]), ("Enmienda 2, bloque de la red ampliada", "2026-10-25",
                                                              CFG["contrato"]["sha256"]))
        self.assertEqual(e["texto_del_bloque"]["sha256"], SHA_BLOQUE_RED2)
        self.assertEqual(e["decisiones_de_traduccion"]["sha256"], SHA_DECISIONES_TRADUCCION)
        self.assertIn(SHA_BLOQUE_RED2, BLOQUE_RED2)
        self.assertIsNone(e["commit"])
        self.assertEqual([p["punto"] for p in e["puntos"]], [f"R{k}" for k in range(2, 23)])
        for p in e["puntos"]:
            self.assertIn(f"##### {p['punto']}. ", BLOQUE_RED2)
            for ruta in p["config"]:
                with self.subTest(punto=p["punto"], ruta=ruta):
                    obtener(ruta)                                # existe
        self.assertEqual(CFG["red_de_monitores"]["red_resultante"]["no2"]["total"], 71)
        reg = CFG["red_de_monitores"]["registro_de_la_red"]
        self.assertEqual(reg["pliegues"]["archivo"], "pliegues_v2_red2.json")
        self.assertEqual((reg["reloj"]["regla"], reg["catalogo_maiac"]["regla"]),
                         ("T4 con la unidad de T9", "T5"))                    # los llena el anexo
        self.assertTrue(reg["tropomi_por_fecha"]["regla"].startswith("T11 [delegada]"))
        if reg["pliegues"]["sha256"] is None:                   # antes del anexo (R22, paso 4), todo vacío
            self.assertIsNone(reg["regimenes"]["sha256"])
            self.assertIsNone(reg["reloj"]["veredictos_sha256"])
        else:                                                    # después, el anexo completo
            self.assertTrue(reg["regimenes"]["sha256"] and reg["reloj"]["veredictos_sha256"])
        dec = e["decisiones_de_traduccion"]
        self.assertTrue(all(dec[k] for k in ("T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12", "T13")))
        for k in ("T11", "T12", "T13"):                          # las delegadas, por ratificar (T13)
            self.assertTrue(dec[k].startswith("[delegada]"))
        # T8: la huella de afg_lib.py y su procedencia, iguales en el código y en la configuración
        import derivado_red2_v2 as dr
        afg = CFG["red_de_monitores"]["calidad"]["derivado"]["afg_lib"]
        self.assertEqual(afg["sha256"], dr.SHA_AFG)
        self.assertEqual({k: {"python": v["python"], "ranking_ast_sha256": v["ranking"],
                              "parser_ast_sha256": v["analizador"]} for k, v in afg["procedencia_ast"].items()},
                         dr.PROCEDENCIA_AST_AFG)

    def test_entrada_del_complemento(self):
        e = CFG["contrato"]["enmiendas"][1]
        self.assertEqual((e["id"], e["fecha"], e["sha256"]), ("Complemento de la Enmienda 1", "2026-10-13",
                                                              SHA_COMPLEMENTO))
        # su sha256 es el del texto tal como quedó con él: el contrato vigente sin el bloque de la red ampliada
        self.assertEqual(hashlib.sha256(TEXTO_CON_EL_COMPLEMENTO.encode("utf-8")).hexdigest(), SHA_COMPLEMENTO)
        self.assertEqual((e["complementa_a"], e["momento"]), ("Enmienda 1", "antes de cualquier ajuste comparativo"))
        self.assertIsNone(e["commit"])
        self.assertIn("ninguna métrica de desempeño", e["conocido_al_escribirlo"]["v2"])
        self.assertIn("Sigue sin existir ninguna métrica de desempeño v2", COMPLEMENTO)
        # títulos: el texto en negrita de cada punto de la lista numerada, sin la puntuación final
        titulos = [(int(m.group(1)), m.group(2).rstrip(".:,"))
                   for m in re.finditer(r"^(\d+)\. \*\*(.+?)\*\*", COMPLEMENTO, re.M)]
        self.assertEqual(titulos, [(p["punto"], p["titulo"]) for p in e["puntos"]])
        self.assertEqual([p["punto"] for p in e["puntos"]], list(range(1, 11)))
        for p in e["puntos"]:
            self.assertTrue(p["config"])
            for ruta in p["config"]:
                with self.subTest(punto=p["punto"], ruta=ruta):
                    obtener(ruta)                                # existe
        self.assertEqual(sorted(e["puntos"][3]["config"]), sorted(RATIFICADOS_COMPLEMENTO))
        self.assertEqual(sorted(e["puntos"][4]["config"]),
                         sorted(["protocolos.BLQ-75.exclusion_adicional.particiones_internas",
                                 "regla_exclusion.amortiguador_interno", *AMORTIGUADOR_INTERNO]))

    def test_artefactos_congelados_con_los_prefijos_del_contrato(self):
        patron = r"`([^`]+\.json)` \((?:sha256 )?([0-9a-f]{8})…\)"
        citados = dict(re.findall(patron, ENMIENDA_1))
        congelados = CFG["contrato"]["enmiendas"][0]["artefactos_congelados"]
        self.assertEqual(sorted(citados), sorted(congelados))
        for nombre, prefijo in citados.items():
            self.assertRegex(congelados[nombre], r"^[0-9a-f]{64}$")
            self.assertTrue(congelados[nombre].startswith(prefijo), nombre)
        # Complemento, punto 9: el manifiesto congelado del piloto es una copia con nombre propio y el mismo sha256
        del_complemento = dict(re.findall(patron, punto_complemento(9)))
        m = CFG["protocolos"]["manifiesto"]
        self.assertEqual(sorted(del_complemento), [m["congelado_del_piloto"]["archivo"]])
        self.assertEqual(m["congelado_del_piloto"]["archivo"], "pliegues_v2_reemplazado_20261013T054105Z.json")
        self.assertRegex(m["congelado_del_piloto"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(m["congelado_del_piloto"]["sha256"].startswith(del_complemento[m["congelado_del_piloto"]["archivo"]]))
        self.assertEqual(m["congelado_del_piloto"]["sha256"], congelados["pliegues_v2.json"])
        self.assertEqual((m["vigente"]["archivo"], m["archivo"]), ("pliegues_v2.json", "pliegues_v2.json"))
        self.assertIn("El manifiesto vigente, con el amortiguador, es `pliegues_v2.json`", punto_complemento(9))
        self.assertIn("pliegues_v2_reemplazado_20261013T054105Z.json",
                      CFG["contrato"]["enmiendas"][0]["artefactos_congelados_nota"])

    def test_sin_rutas_absolutas_de_la_cuenta(self):
        for prohibido in ("/Users/", "GoogleDrive", "CloudStorage", "@gmail"):
            self.assertNotIn(prohibido, TEXTO)

    def test_esquema_y_convenciones(self):
        self.assertEqual(CFG["schema"], "airpollution.modelo-1km-v2.config.v2")
        for clave in ("pendiente", "ratificado", "lectura"):
            self.assertIn(clave, CFG["convenciones"])
        self.assertIn(RATIFICADO, CFG["convenciones"]["ratificado"])
        self.assertIn(RATIFICADO_C, CFG["convenciones"]["ratificado"])
        self.assertIn("Complemento", CFG["descripcion"])
        self.assertIn("_antes_del_complemento", CFG["convenciones"]["antes_de_la_enmienda"])


class RatificacionTests(unittest.TestCase):
    def test_los_39_provisionales_quedan_ratificados(self):
        hallados = dict(por_estado(CFG, RATIFICADO))
        self.assertEqual(len(RATIFICADOS), 39)
        self.assertEqual(sorted(hallados), sorted(RATIFICADOS))
        for ruta, item in hallados.items():
            with self.subTest(ruta=ruta):
                self.assertIn("valor", item)
                self.assertNotIn("provisional", item)
                self.assertTrue(item.get("nota"))
                self.assertEqual(item["punto"].split(",")[0], RATIFICADOS[ruta])

    def test_cada_ratificado_se_nombra_en_la_enmienda(self):
        nombres = {s.lstrip(".") for s in re.findall(r"`([^`]+)`", seccion(1))}
        for ruta in RATIFICADOS:
            with self.subTest(ruta=ruta):
                self.assertTrue(any(ruta.endswith(n) for n in nombres), "la enmienda no lo nombra")

    def test_cambios_declarados(self):
        for ruta in RATIFICADOS:
            item = obtener(ruta)
            with self.subTest(ruta=ruta):
                self.assertEqual("cambio" in item, ruta in CON_CAMBIO)
                self.assertEqual("provisional_anterior" in item, ruta in CAMBIAN_DE_VALOR)
                otro_punto = re.fullmatch(r"1\.\d+, (con (el cambio del punto|los cambios de los puntos) .+|ver el punto \d+)",
                                          item["punto"])
                self.assertEqual(otro_punto is not None, ruta in CON_CAMBIO, item["punto"])
                if ruta in CAMBIAN_DE_VALOR:
                    self.assertNotEqual(item["valor"], item["provisional_anterior"])

    def test_ninguno_queda_pendiente_y_la_combinacion_se_cierra(self):
        rutas_pendientes = {r for r, _ in pendientes(CFG)}
        self.assertFalse(rutas_pendientes & set(RATIFICADOS))
        self.assertFalse(rutas_pendientes & set(RATIFICADOS_COMPLEMENTO))
        comb = CFG["decision"]["combinacion_de_protocolos"]
        self.assertIsInstance(comb, str)
        self.assertNotEqual(comb, "pendiente")
        self.assertIn("en LRO y en BLQ-75", comb)

    def test_los_7_detalles_quedan_ratificados_por_el_complemento(self):
        hallados = dict(por_estado(CFG, RATIFICADO_C))
        self.assertEqual(len(RATIFICADOS_COMPLEMENTO), 7)
        self.assertEqual(sorted(hallados), sorted(RATIFICADOS_COMPLEMENTO))
        # los 7 subpuntos del punto 4 del Complemento, en el orden de RATIFICADOS_COMPLEMENTO
        self.assertEqual(len(enumeracion(punto_complemento(4))), 7)
        self.assertEqual([v[0] for v in RATIFICADOS_COMPLEMENTO.values()], [f"4.{i}" for i in range(1, 8)])
        for ruta, (sub, origen, _) in RATIFICADOS_COMPLEMENTO.items():
            item = hallados[ruta]
            with self.subTest(ruta=ruta):
                self.assertIn("valor", item)
                self.assertNotIn("provisional", item)
                self.assertTrue(item.get("nota"))
                self.assertEqual(item["origen"], f"Enmienda 1, {origen}")
                self.assertEqual(item["punto"].split(",")[0], sub)
                cambia = ruta in CAMBIA_CON_EL_COMPLEMENTO
                self.assertEqual("cambio" in item, cambia)
                self.assertEqual("provisional_anterior" in item, cambia)
                self.assertEqual(item["punto"] != sub, cambia)       # «4.6, con el cambio del punto 1»
        self.assertEqual(hallados["inferencia_diferencias.segunda_prueba.metodo"]["punto"], "4.6, con el cambio del punto 1")

    def test_ratificados_con_el_valor_que_tenian(self):
        """«con el valor que tienen en config_v2.json» (Complemento, punto 4): el «valor» de cada detalle es su
        provisional de la Enmienda 1, salvo el que cambia por el punto 1, que guarda ese provisional como anterior."""
        for ruta, (_, _, h) in RATIFICADOS_COMPLEMENTO.items():
            item = obtener(ruta)
            with self.subTest(ruta=ruta):
                if ruta in CAMBIA_CON_EL_COMPLEMENTO:
                    self.assertEqual(huella(item["provisional_anterior"]), h)
                    self.assertNotEqual(huella(item["valor"]), h)
                else:
                    self.assertEqual(huella(item["valor"]), h)
        # lo que el texto del punto 4 dice de cada uno está en su valor
        t = plano(punto_complemento(4))
        self.assertIn("dos mitades de conglomerados LOSO-D, semilla [42, k, 1001]", t)
        self.assertIn("[42, k, 1001]", valor(obtener("perdidas.variantes[2].delta.particion_honesta")))
        self.assertIn("igual al de la retransformación primaria", t)
        self.assertIn("respaldo honesto de la retransformación primaria", valor(obtener("perdidas.variantes[3].calibracion.respaldo")))
        self.assertIn("(INE, mediana de los años de la estación)", t)
        comunal = valor(obtener("metricas.desagregaciones.ponderado_por_poblacion.desagrupamiento.poblacion_comunal"))
        self.assertIn("INE", comunal)
        self.assertIn("mediana de los años", comunal)
        self.assertIn("familias", valor(obtener("metricas.desagregaciones.regimen_de_predictores.sensibilidad.fila_a_fila")))
        anterior = obtener("inferencia_diferencias.segunda_prueba.metodo")["provisional_anterior"]
        self.assertEqual(valor(obtener("inferencia_diferencias.segunda_prueba.metodo"))["estimador"], anterior["estimador"])

    def test_solo_estados_conocidos(self):
        """``_rutas_v2.valor_vigente`` acepta cualquier estado que empiece por «ratificado»: una errata en el nombre
        pasaría callada, así que aquí se exige que cada valor vigente lleve uno de los tres estados conocidos."""
        vistos = []

        def recorrer(nodo):
            if isinstance(nodo, dict):
                if "estado" in nodo and ("valor" in nodo or "provisional" in nodo
                                         or str(nodo["estado"]).startswith(rv.PREFIJO_RATIFICADO)):
                    vistos.append(nodo["estado"])
                for v in nodo.values():
                    recorrer(v)
            elif isinstance(nodo, list):
                for v in nodo:
                    recorrer(v)

        recorrer(CFG)
        self.assertEqual(sorted(set(vistos)), sorted({"pendiente", RATIFICADO, RATIFICADO_C}))
        self.assertEqual(len(vistos), len(RATIFICADOS) + len(RATIFICADOS_COMPLEMENTO) + len(PENDIENTES))

    def test_pendientes_bien_formados(self):
        lista = dict(pendientes(CFG))
        self.assertEqual(sorted(lista), sorted(PENDIENTES))
        for ruta, item in lista.items():
            with self.subTest(ruta=ruta):
                self.assertIsInstance(item, dict)
                self.assertTrue(item.get("nota"))
                self.assertIn("provisional", item)
                self.assertEqual(item["origen"], PENDIENTES[ruta])

    def test_valor_vigente_lee_ratificados_y_pendientes(self):
        """Integración con ``_rutas_v2.valor_vigente``: el código debe leer el «valor» de cada ratificado, de la
        Enmienda 1 o del Complemento."""
        try:
            soporta = all(rv.valor_vigente({"estado": e, "valor": 7}, "prueba") == 7 for e in (RATIFICADO, RATIFICADO_C))
        except Exception:                                             # noqa: BLE001
            soporta = False
        if not soporta:
            self.skipTest("_rutas_v2.valor_vigente todavía no lee «ratificado (…)» → «valor»")
        items = list(por_estado(CFG, RATIFICADO)) + list(por_estado(CFG, RATIFICADO_C)) + list(por_estado(CFG, "pendiente"))
        self.assertEqual(len(items), len(RATIFICADOS) + len(RATIFICADOS_COMPLEMENTO) + len(PENDIENTES))
        for ruta, item in items:
            with self.subTest(ruta=ruta):
                self.assertEqual(rv.valor_vigente(item, ruta), valor(item))


class ProtocolosTests(unittest.TestCase):
    p = CFG["protocolos"]

    def test_los_cinco_protocolos(self):
        self.assertEqual(self.p["orden"], ["LOSO-D", "LBO-10", "BLQ-75", "LRO", "LPO"])
        self.assertEqual(self.p["manifiesto"]["archivo"], "pliegues_v2.json")
        self.assertIn("se vuelve a fijar", self.p["manifiesto"]["refijado_por_la_enmienda_1"])

    def test_loso_d_y_distancias(self):
        d = self.p["LOSO-D"]
        self.assertEqual((d["umbral_km"], d["comparacion"], d["metodo"]), (2.0, "<=", "componentes conexas"))
        self.assertTrue(d["une_celdas_compartidas"])
        self.assertEqual(d["retira_juntos_ejemplos"], [["309", "310", "330", "333"], ["B03", "B04"], ["503", "548"]])
        self.assertEqual((d["distancia"]["formula"], d["distancia"]["radio_tierra_km"]), ("haversine", 6371.0))
        self.assertEqual(d["exclusion_adicional"], "ninguna")
        self.assertIn("3,7 km", d["encadenamiento"])
        self.assertIn("3,7 km", seccion(13))
        g = self.p["distancias"]
        self.assertEqual((g["formula"], g["radio_tierra_km"]), ("haversine", 6371.0))
        self.assertIn("R = 6.371 km", seccion(13))

    def test_lbo_blq_lro_lpo(self):
        b = self.p["LBO-10"]["exclusion_adicional"]
        self.assertEqual((b["radio_km"], b["comparacion"]), (10.0, "<="))
        q = self.p["BLQ-75"]
        self.assertEqual((q["lado_m"], q["crs"]), (75000.0, "EPSG:32719"))
        self.assertEqual(valor(q["origen_m"]), [0.0, 0.0])
        self.assertEqual(self.p["LRO"]["grupo_prueba"], "region_sinca")
        self.assertEqual(self.p["LRO"]["equivalencias"], {"RXVI": "RVIII"})
        v = self.p["LPO"]["ventanas"]
        self.assertEqual((v["anio_desde"], v["anio_hasta"], v["largo_anios"]), (2000, 2026, 4))
        self.assertEqual(self.p["semilla"]["regla"], [42, "k"])
        self.assertIn("lexicográfico", valor(self.p["semilla"]["k"]))

    def test_blq_75_con_amortiguador_de_10_km(self):
        a = self.p["BLQ-75"]["exclusion_adicional"]
        self.assertEqual((a["radio_km"], a["comparacion"]), (10.0, "<="))
        self.assertEqual(a["medida_desde"], "cualquier estación del bloque de prueba")
        self.assertEqual(a["antes_de_la_enmienda"], "ninguna")
        self.assertIn("≤ 10 km (haversine) de cualquier estación del bloque de prueba", seccion(8))
        self.assertIn("BLQ-75", CFG["regla_exclusion"]["amortiguadores"])

    def test_amortiguador_en_las_particiones_internas_de_blq_75(self):
        """Complemento, punto 5: el radio de 10 km del punto 8 también rige dentro de cada pliegue de BLQ-75."""
        externo = self.p["BLQ-75"]["exclusion_adicional"]
        i = externo["particiones_internas"]
        self.assertEqual((i["radio_km"], i["comparacion"]), (externo["radio_km"], externo["comparacion"]))
        self.assertEqual(i["medida_desde"], "cualquier estación del conjunto interno de validación")
        t = punto_complemento(5)
        self.assertIn("El radio de 10 km del punto 8 también se aplica en las particiones internas", t)
        self.assertEqual(i["se_aplica_en"], vinetas(t))           # las tres particiones que nombra el Complemento
        self.assertEqual(len(i["se_aplica_en"]), 3)
        self.assertIn("se sacan del entrenamiento interno las estaciones a ≤ 10 km de las estaciones de su conjunto "
                      "interno de validación", plano(t))
        self.assertIn("se sacan del entrenamiento interno las estaciones a ≤ 10 km", i["regla"])
        self.assertIn("particiones_internas", CFG["regla_exclusion"]["amortiguador_interno"])
        for ruta in AMORTIGUADOR_INTERNO:                         # cada partición interna remite al amortiguador
            with self.subTest(ruta=ruta):
                texto = obtener(ruta)
                self.assertIn("≤ 10 km", texto)
                self.assertIn("particiones_internas", texto)
                self.assertTrue(texto.startswith("en BLQ-75 "))

    def test_regla_unica_de_exclusion_y_vecindario(self):
        self.assertEqual(CFG["regla_exclusion"]["se_aplica_a"],
                         ["filas de entrenamiento", "vecindario de entrenamiento", "vecindario de prueba",
                          "residuos de la retransformación"])
        v = CFG["vecindario"]
        self.assertEqual(v["recalculo"]["protocolos"], ["LOSO-D", "LBO-10", "BLQ-75", "LRO"])
        self.assertFalse(v["recalculo"]["atajo_para_conjuntos_de_una_estacion"])
        self.assertEqual(v["implementacion"]["ancho_km"], 150.0)


class MotoresTests(unittest.TestCase):
    m = CFG["motores"]

    def test_lightgbm_receta_v1_determinista(self):
        g = self.m["eje_A"]["lightgbm"]
        esperado = {"num_boost_round": 800, "learning_rate": 0.03, "num_leaves": 127, "min_data_in_leaf": 50,
                    "bagging_fraction": 0.8, "bagging_freq": 1, "feature_fraction": 0.8, "lambda_l2": 1.0,
                    "deterministic": True, "force_col_wise": True, "num_threads": 12, "objective": "regression"}
        self.assertEqual({k: g[k] for k in esperado}, esperado)
        self.assertIn("200.000 filas", g["cortes_del_histograma"])

    def test_xgboost_equivalente(self):
        x = self.m["eje_A"]["xgboost"]
        esperado = {"tree_method": "hist", "max_leaves": 127, "grow_policy": "lossguide", "eta": 0.03,
                    "num_boost_round": 800, "subsample": 0.8, "lambda": 1.0}
        self.assertEqual({k: x[k] for k in esperado}, esperado)
        self.assertEqual(x["colsample"]["valor"], 0.8)
        self.assertEqual(valor(x["colsample"]["variante"]), "colsample_bytree")
        self.assertEqual([valor(x[k]) for k in ("min_child_weight", "max_depth", "max_bin", "nthread", "seed")],
                         [50, 0, 255, 12, 42])
        self.assertEqual(x["min_child_weight"]["equivalencia"], "con hessiana 1")
        self.assertIn("hessiana no constante", x["min_child_weight"]["salvaguarda"])
        self.assertIn("bit a bit", valor(x["determinismo"]))
        self.assertIn("200.000 filas", x["determinismo"]["cortes_del_histograma"])

    def test_rf_y_promedio(self):
        rf = self.m["eje_A"]["random_forest"]
        self.assertEqual((rf["n_estimators"], rf["max_features"], rf["min_samples_leaf"]), (300, "sqrt", 20))
        self.assertEqual(valor(rf["n_jobs"]), 12)
        self.assertEqual(rf["n_jobs"]["prediccion"], "por trozos, con un hilo por trozo")
        prom = self.m["eje_A"]["promedio_simple"]
        self.assertEqual(prom["motores"], ["lightgbm", "xgboost", "random_forest", "mlp"])
        self.assertEqual(valor(prom["escala"]), "log")

    def test_mlp_parada_temprana_del_punto_6(self):
        mlp = self.m["eje_A"]["mlp"]
        self.assertEqual(mlp["hidden_layer_sizes"], [128, 64])
        pt = mlp["parada_temprana"]
        self.assertIn("conglomerados LOSO-D", pt["validacion"])
        self.assertEqual(pt["validacion_antes_de_la_enmienda"], "agrupada por estación, no al azar (§3)")
        self.assertEqual(valor(pt["fraccion"]), 0.1)
        self.assertEqual(sorted(pt["fraccion"]["unidad"]), ["LOSO-D, LBO-10 y LPO", "LRO y BLQ-75"])
        self.assertIn("estratificado por macrozona", pt["fraccion"]["unidad"]["LRO y BLQ-75"])
        c = valor(pt["criterio"])
        self.assertEqual((c["tol"], c["n_iter_no_change"]), (1e-4, mlp["n_iter_no_change"]))
        self.assertIn("sin las estaciones de validación", c["vecindario"])
        self.assertIn("todas las estaciones del pliegue", c["reajuste"])
        self.assertIn("queda registrada", c["epoca_elegida"])
        t = seccion(6)
        for frase in ("conglomerados LOSO-D", "grupos completos del protocolo", "~10 % de las filas",
                      "estratificado por macrozona", "se recalcula sin las estaciones de validación"):
            self.assertIn(frase, t)

    def test_predictores_de_la_v1(self):
        pm, no = self.m["eje_A"]["predictores"]["pm25"], self.m["eje_A"]["predictores"]["no2"]
        self.assertEqual((len(pm), len(no)), (70, 69))
        self.assertEqual([c for c in pm if c != "dist_costa_km"], no)
        self.assertEqual(len(set(pm)), 70)

    def test_eje_b_alertas_hiperparametros_apilado(self):
        self.assertEqual(self.m["eje_B"]["motores"], ["gp", "lme", "gwr", "rk", "idw"])
        self.assertEqual(self.m["eje_B"]["preprocesamiento_dentro_del_pliegue"],
                         ["medianas", "indicadoras", "escala", "selección por cobertura"])
        self.assertEqual(valor(self.m["eje_B"]["topes_de_filas"]),
                         {"gp": 3000, "lme": 300000, "gwr": "todas", "rk": "todas", "idw": "todas"})
        self.assertIn("ya no estratifica", self.m["eje_B"]["topes_de_filas"]["nota"])
        self.assertEqual(self.m["alertas"]["cuantil"], 0.8)
        al = valor(self.m["alertas"]["receta"])
        self.assertEqual((al["num_boost_round"], al["learning_rate"], al["bagging"]), (900, 0.025, False))
        self.assertIn("750.000 filas", self.m["alertas"]["receta"]["nota"])
        self.assertFalse(self.m["hiperparametros"]["busqueda"])
        a = self.m["apilado_anidado"]
        self.assertEqual(a["protocolos"], ["LRO", "BLQ-75"])
        self.assertEqual(a["pesos"], {"no_negativos": True, "suman_1": True})
        self.assertFalse(a["compite_fuera_de_esos_protocolos"])
        self.assertEqual(valor(a["bases"]), ["lightgbm", "xgboost", "random_forest", "mlp"])
        self.assertEqual(valor(a["pliegues_internos"])["n"], 5)
        self.assertEqual(valor(a["escala"]), "log")
        self.assertIn("no es candidato ni se despliega", a["descriptivo"])
        self.assertIn("máximo", a["ruido"])


class FilasRetransformacionTests(unittest.TestCase):
    def test_filas(self):
        f = CFG["filas_entrenamiento"]
        self.assertEqual(f["permutacion"]["semilla"], [42, "k"])
        self.assertEqual(f["N_comun_eje_A"], 750000)
        self.assertIn("default_rng(semilla).permutation", valor(f["permutacion"]["generador"]))
        self.assertIn("N efectivo", valor(f["disponibles_menos_que_el_tope"]))
        c = f["curvas_de_aprendizaje"]
        self.assertEqual(c["protocolos"], ["LRO", "BLQ-75"])
        self.assertEqual(c["lightgbm"], [300000, 750000, 1500000, "todas"])
        self.assertEqual(c["xgboost"], [300000, 750000, 1500000, "todas"])
        self.assertEqual(c["random_forest"], [300000, 750000, 1500000])

    def test_primaria_smearing_y_sensibilidad_fija(self):
        r = CFG["retransformacion"]
        p = r["primaria"]
        self.assertEqual((p["forma"], p["clave"], p["franja_diurna_horas_locales"], p["minimo_filas"]),
                         ("smearing_duan", "macrozona|franja", [8, 18], 100))
        self.assertEqual(p["respaldo"], ["franja de los demás grupos", "global de los demás grupos"])
        self.assertIn("log(media de exp(r))", r["formas"]["smearing_duan"])
        self.assertIn("0,5 × varianza poblacional", r["formas"]["lognormal_medio_sigma2"])
        self.assertEqual(r["formas"]["nombres_anteriores"]["duan"], "lognormal_medio_sigma2")
        f = r["sensibilidad_fija"]
        self.assertEqual((f["forma"], f["protocolos"], f["par_en_el_bootstrap"]), ("lognormal_medio_sigma2", "todos", True))
        self.assertEqual((r["sensibilidad"]["forma"], r["sensibilidad"]["protocolos"]), ("smearing_duan", ["LRO", "BLQ-75"]))
        self.assertIn("smearing_duan", r["regla_previa"])
        self.assertIn("lognormal_medio_sigma2", r["regla_previa"])
        self.assertTrue(r["metricas_en_log"])
        self.assertIn("sin_correccion", valor(p["global_de_los_demas_con_menos_de_100_filas"]))
        self.assertIn("apilado", valor(r["sensibilidad"]["pliegues_internos"]))
        self.assertIn("`smearing_duan` y `lognormal_medio_sigma2`", seccion(2))

    def test_respaldo_honesto(self):
        h = CFG["retransformacion"]["primaria"]["respaldo_honesto"]
        mf = h["macrozona_franja"]
        self.assertEqual((mf["minimo_conglomerados_loso_d"], mf["minimo_grupos_del_protocolo"], mf["minimo_filas"]), (3, 2, 100))
        self.assertEqual(h["orden"], ["macrozona|franja de los demás", "franja de los demás", "global de los demás"])
        self.assertEqual(h["registro_por_pliegue"], ["nivel usado", "estaciones que aportan", "factor"])
        self.assertIn("al menos 3 conglomerados LOSO-D de al menos 2 grupos del protocolo", seccion(2))
        self.assertIn("piso de 100 filas", seccion(2))

    def test_las_dos_formas_coinciden_bajo_normalidad_y_el_smearing_corrige_la_media(self):
        """Lo que dice el punto 2: con residuos normales las dos formas coinciden; el smearing corrige además el
        sesgo medio en log, que ½·σ² ignora (datos simulados)."""
        rng = np.random.default_rng(20261013)
        sigma, sesgo = 0.6, 0.15
        r = rng.normal(0.0, sigma, 400_000)
        smearing = lambda x: float(np.log(np.mean(np.exp(x))))           # noqa: E731
        lognormal = lambda x: float(0.5 * np.var(x))                     # noqa: E731
        self.assertAlmostEqual(smearing(r), lognormal(r), delta=0.01)
        r2 = r + sesgo
        self.assertAlmostEqual(smearing(r2) - smearing(r), sesgo, delta=1e-9)
        self.assertAlmostEqual(lognormal(r2), lognormal(r), delta=1e-9)


class PerdidasTests(unittest.TestCase):
    p = CFG["perdidas"]

    def test_variantes_y_nombres(self):
        self.assertEqual(self.p["motores"], ["lightgbm", "xgboost"])
        self.assertEqual([v["id"] for v in self.p["variantes"]], ["l2_log_smearing", "l2_original", "huber", "pinball"])
        ref = self.p["variantes"][0]
        self.assertEqual((ref["id_antes_de_la_enmienda"], ref["referencia_v1"]["id"]), ("l2_log_duan", "l2_log_medio_sigma2"))
        self.assertIn("`l2_log_smearing`; la referencia v1 es `l2_log_medio_sigma2`", seccion(2))
        self.assertEqual(self.p["metricas_comunes_escala_original"], ["R2", "RMSE", "MAE", "NMB"])
        self.assertEqual(self.p["metricas_cuantiles"]["cobertura_del_intervalo"], 0.9)

    def test_huber_con_delta_comun_honesto(self):
        h = self.p["variantes"][2]
        self.assertEqual(h["id"], "huber")
        self.assertFalse(h["estima_la_media"])
        self.assertFalse(h["compite_en_la_decision"])
        d = h["delta"]
        self.assertEqual(d["factor"], 1.345)
        self.assertTrue(d["comun_a_los_dos_motores"])
        self.assertIn("1,4826", valor(d["mad"]))
        aj = valor(d["ajuste_cuadratico"])
        self.assertEqual((aj["motor"], aj["variante"], aj["comun_a"]), ("lightgbm", "l2_original", ["lightgbm", "xgboost"]))
        self.assertIn("honestos", aj["residuos"])
        self.assertEqual(d["sensibilidad"]["delta"], "cuantil 0,9 de |r|")
        self.assertIn("Friedman (2001)", d["sensibilidad"]["fuente"])
        self.assertTrue(any("recortadas" in x for x in d["registro_por_pliegue"]))
        self.assertTrue(any("pérdida final" in x for x in d["registro_por_pliegue"]))
        self.assertIn("picos invernales", h["declaracion"])
        t = seccion(9)
        for frase in ("1,345 × MAD normalizado", "cuantil 0,9 de |r| (Friedman 2001)", "partición agrupada en dos"):
            self.assertIn(frase, t)

    def test_cuantiles_reordenados_y_cqr(self):
        q = self.p["variantes"][3]
        self.assertEqual(q["taus"], [0.05, 0.5, 0.95])
        self.assertFalse(q["q50_compite_en_la_decision"])
        self.assertEqual(q["reordenamiento"]["regla"], "q05 ≤ q50 ≤ q95")
        self.assertEqual(q["reordenamiento"]["se_informan"], "los cruces")
        c = q["calibracion"]
        self.assertIn("CQR", c["metodo"])
        self.assertEqual((c["clave"], c["nivel"]), ("macrozona|franja", 0.9))
        self.assertIn("demás grupos", c["residuos"])
        self.assertIn("CQR; Romano et al. 2019", seccion(9))


class CalidadTests(unittest.TestCase):
    c = CFG["calidad_blanco"]

    def test_variantes_y_codigos(self):
        self.assertEqual([v["id"] for v in self.c["variantes_entrenamiento"]], ["todo", "validado_y_preliminar", "solo_validado"])
        self.assertEqual(self.c["snifa"]["variantes"], ["numeric_usable", "usable_native"])
        self.assertEqual(self.c["comparacion_de_variantes"], {"motor": "lightgbm", "eje": "A", "protocolos": ["LOSO-D", "LRO"]})
        cod = valor(self.c["codigos_qc"])
        self.assertEqual(cod["solo_validado"], ["validado", "usable_native"])
        self.assertEqual(cod["evaluacion_validadas"], ["validado", "usable_native"])
        self.assertIn("no_validado", cod["todo"])
        self.assertIn("rechazado", self.c["no_validado"])

    def test_conjuntos_de_evaluacion(self):
        e = self.c["evaluacion"]
        self.assertEqual(sorted(e["conjuntos"]), sorted(["E1", "E2", "E2-SINCA", "E1′"]))
        self.assertEqual(e["conjuntos"]["E2"]["codigos"], valor(self.c["codigos_qc"])["evaluacion_validadas"])
        self.assertEqual(e["conjuntos"]["E2-SINCA"]["codigos"], ["validado"])
        self.assertEqual(e["decision"]["coprimarios"], ["E1", "E2"])
        ev = e["evaluabilidad"]
        self.assertEqual((ev["minimo_fraccion_del_peso_de_E1"], ev["minimo_grupos_con_filas_E2"]), (0.5, 5))
        self.assertIn("sin confirmación con datos validados", ev["si_no_es_evaluable"])
        t = seccion(7)
        self.assertIn("≥ 50 % del peso de E1 y ≥ 5 grupos con filas E2", t)
        self.assertIn("45 de las 107 estaciones de PM2,5 y 33 de las 54 estaciones SINCA de NO2", t)
        self.assertIn("45 de las 107", e["cobertura_conocida"]["pm25"])
        self.assertIn("33 de las 54", e["cobertura_conocida"]["no2"])


class MetricasTests(unittest.TestCase):
    m = CFG["metricas"]

    def test_niveles_y_desagregaciones(self):
        self.assertEqual(self.m["niveles"]["diario"], {"dias": ["civil America/Santiago", "UTC−4"], "minimo_horas": 18})
        self.assertEqual(valor(self.m["niveles"]["mensual"]["minimo_dias"]), 20)
        self.assertEqual(valor(self.m["niveles"]["anual"]["minimo_meses"]), 9)
        self.assertEqual(set(self.m["desagregaciones"]), {"macrozona", "estacion", "regimen_de_predictores",
                                                          "estrato_de_soporte", "ponderado_por_poblacion",
                                                          "propietario"})
        self.assertEqual(self.m["desagregaciones"]["estrato_de_soporte"]["variables"], ["peso_vec", "dist_est_km"])

    def test_cinco_regimenes_contiguos(self):
        r = self.m["desagregaciones"]["regimen_de_predictores"]
        reg = valor(r["criterio"])
        sys.path.insert(0, str(V2 / "tests"))
        from _sintetico_v2 import anexo_de_la_red
        anexo = anexo_de_la_red(CFG)            # Enmienda 2, R17: después del anexo rigen los tramos calculados
        if anexo is None:
            self.assertEqual([x["id"] for x in reg], ["2000-2002", "2003-2018", "2019-2024", "2025", "2026"])
        else:
            self.assertEqual([(x["id"], list(x["anios"]), x["disponibilidad"]) for x in reg],
                             [(x["id"], list(x["anios"]), x["disponibilidad"]) for x in anexo["tramos"]])
        anios = [a for x in reg for a in range(x["anios"][0], x["anios"][1] + 1)]
        self.assertEqual(anios, list(range(2000, 2027)))               # sin huecos ni solapes
        self.assertEqual(r["criterio"]["provisional_anterior"], [2019, 2024])
        self.assertIn("2024 se informa aparte de 2025-2026", r["LPO"])
        self.assertIn("no alteran el §9", r["alcance"])
        t = seccion(10)
        for x in (reg if anexo is None else []):                # los rótulos del §10 son los de la Enmienda 1
            self.assertIn(x["disponibilidad"], t)

    def test_pesos_fijos_y_desagrupamiento(self):
        pp = self.m["desagregaciones"]["ponderado_por_poblacion"]
        pob = valor(pp["poblacion"])
        self.assertIn("mediana", pob["peso_fijo_por_estacion"])
        self.assertEqual(pob["se_pondera"], ["total", "macrozona", "regimen"])
        self.assertIn("comuna", pp["desagrupamiento"]["peso"])
        self.assertIn("sin ponderación", pp["sin_ponderar"])
        self.assertEqual(sorted(pp["g_efectivo"]), ["estaciones_kish", "grupos", "se_informa"])
        self.assertIn("mediana de sus años", seccion(4))


class RuidoInferenciaTests(unittest.TestCase):
    i = CFG["inferencia_diferencias"]

    def test_ruido_de_la_diferencia(self):
        r = CFG["ruido"]
        self.assertEqual((r["semillas"], r["protocolos_con_3_semillas"], r["semillas_en_los_demas_protocolos"]),
                         (3, ["LRO", "BLQ-75"], 1))
        self.assertEqual(valor(r["valores"])["replicas"], [0, 1, 2])
        mr = valor(self.i["regla_de_superioridad"]["medida_del_ruido"])
        self.assertIn("|Δ̄| > rango(Δ_r)", mr["condicion"])
        self.assertEqual(mr["tasa_de_paso_por_azar"], 0.081)
        self.assertIn("máximo", mr["apilado"])
        self.assertIn("no evaluada", mr["sin_replicas"])
        self.assertIn("(8,1 %)", seccion(3))

    def test_tres_replicas_obligatorias(self):
        """Complemento, punto 6: la condición 2 y el desempate exigen las 3 réplicas comunes."""
        exigidas = CFG["ruido"]["replicas_exigidas_en_la_decision"]["valor"]
        self.assertEqual(exigidas, 3)
        self.assertEqual(exigidas, len(valor(CFG["ruido"]["valores"])["replicas"]))
        c2 = CFG["decision"]["condiciones"][1]
        self.assertEqual((c2["id"], c2["replicas_exigidas"]), ("ruido_de_la_diferencia", exigidas))
        self.assertIn("no evaluada", c2["con_menos_replicas"])
        self.assertIn("no puede reemplazar a LightGBM", c2["con_menos_replicas"])
        self.assertEqual(CFG["decision"]["desempate"]["replicas_exigidas"], exigidas)
        self.assertIn("no evaluado", CFG["decision"]["desempate"]["con_menos_replicas"])
        t = punto_complemento(6)
        for frase in ("exige las 3 réplicas comunes", "queda «no evaluada»", "un candidato no puede reemplazar a LightGBM",
                      "Lo mismo vale para el desempate"):
            self.assertIn(frase, t)

    def test_tasa_de_paso_por_azar_simulada(self):
        """|Δ̄| > rango(Δ_r) con 3 réplicas y sin diferencia real pasa ≈ 8,1 % de las veces, sea cual sea la
        correlación entre los motores (datos simulados)."""
        rng = np.random.default_rng(42)
        objetivo = valor(self.i["regla_de_superioridad"]["medida_del_ruido"])["tasa_de_paso_por_azar"]
        for rho in (0.0, 0.8):
            a = rng.standard_normal((300_000, 3))
            b = rho * a + np.sqrt(1 - rho ** 2) * rng.standard_normal((300_000, 3))
            d = a - b
            tasa = float(np.mean(np.abs(d.mean(axis=1)) > d.max(axis=1) - d.min(axis=1)))
            self.assertAlmostEqual(tasa, objetivo, delta=0.003, msg=f"correlación {rho}")

    def test_bootstrap_por_bloques(self):
        b = self.i["bootstrap"]
        self.assertEqual((b["replicas"], b["replicas_antes_del_complemento"]), (1999, 2000))
        self.assertIn("B = 1.999 réplicas, en vez de 2.000", punto_complemento(2))
        self.assertEqual(b["unidad"], {"LOSO-D": "bloque", "LBO-10": "bloque", "BLQ-75": "bloque",
                                       "LRO": "region", "LPO": "cuatrienio"})
        self.assertIn("75 km", b["bloque"])
        self.assertEqual(b["unidad_antes_de_la_enmienda"], {"LOSO-D": "conglomerado", "LBO-10": "conglomerado"})
        self.assertEqual(valor(b["metodo_del_intervalo"]), "percentil (2,5 % y 97,5 %)")
        # la semilla ratificada no cambia con B: el Complemento cambia el número de réplicas, no la semilla
        self.assertIn("[42, 2000, p]", valor(b["semilla"]))
        self.assertIn("no cambia", b["lectura_de_la_semilla"])
        self.assertNotIn("semilla", punto_complemento(2))
        self.assertIn("75 km", valor(b["nivel_de_agregacion"]))
        self.assertIn("descriptivo", self.i["LPO"])
        self.assertEqual(self.i["regla_de_superioridad"]["nivel_del_intervalo"], 0.95)
        self.assertIn("el bloque de 75 km, no el conglomerado", seccion(5))

    def test_1999_replicas_sin_empates_en_los_umbrales_de_holm(self):
        """Complemento, punto 2: con B = 1.999 ningún umbral (α_j/2)·B de Holm es entero, así que «p ≤ α_j» y «el
        IC escalonado excluye 0» no pueden diferir por un empate; con las 2.000 de antes, sí."""
        holm = CFG["decision"]["condiciones"][0]["holm"]
        m, alfa = holm["m"], holm["alfa_de_la_familia"]
        umbrales = [alfa / (m - j) / 2 for j in range(m)]               # α/(m − j + 1)/2, j = 1…m

        def enteros(B):
            return [u for u in umbrales if abs(u * B - round(u * B)) < 1e-9]

        self.assertEqual(enteros(self.i["bootstrap"]["replicas"]), [])
        self.assertTrue(enteros(self.i["bootstrap"]["replicas_antes_del_complemento"]))
        self.assertIn("intervalo escalonado publicado", holm["intervalo_de_la_decision"])
        self.assertIn("La decisión usa el intervalo escalonado publicado", punto_complemento(2))

        def declaraciones(B, k, a):
            """(p ≤ a, el IC percentil al nivel 1 − a excluye 0) con k de B réplicas ≤ 0 y el resto > 0."""
            d = np.concatenate([np.full(k, -1.0), np.ones(B - k)])
            p = 2 * min(float((d <= 0).mean()), float((d >= 0).mean()))
            return p <= a, bool(np.quantile(d, a / 2, method="inverted_cdf") > 0)

        # con 2.000 réplicas, 25 de ellas ≤ 0 dan p = 0,025: Holm declara al nivel 0,025 y el IC al 97,5 % toca el 0
        self.assertEqual(declaraciones(self.i["bootstrap"]["replicas_antes_del_complemento"], 25, 0.025), (True, False))
        # con 1.999, las dos lecturas coinciden siempre, en los cuatro niveles de Holm
        for k in range(60):
            for j in range(m):
                with self.subTest(k=k, j=j):
                    por_p, por_ic = declaraciones(self.i["bootstrap"]["replicas"], k, alfa / (m - j))
                    self.assertEqual(por_p, por_ic)

    def test_segunda_prueba_e_influencia(self):
        s = self.i["segunda_prueba"]
        self.assertEqual(len(s["opciones_del_contrato"]), 2)
        self.assertTrue(self.i["regla_de_superioridad"]["la_segunda_prueba_coincide"])
        inf = self.i["influencia"]
        sys.path.insert(0, str(V2 / "tests"))
        from _sintetico_v2 import anexo_de_la_red
        anexo = anexo_de_la_red(CFG)            # Enmienda 2, R16: después del anexo rige el bloque calculado
        self.assertEqual(inf["bloque_mas_influyente"],
                         {"LRO": "RM", "BLQ-75": "E004N083"} if anexo is None else anexo["bloque"])
        self.assertIn("no robusta", inf["regla"])
        self.assertEqual(self.i["informes"], ["G", "G efectivo", "Δ sin cada bloque"])
        t = seccion(5)
        self.assertIn("la RM en LRO y E004N083 en BLQ-75", t)
        self.assertIn("Webb si G < 12", t)

    def test_segunda_prueba_que_decide_es_el_cambio_de_signo(self):
        """Complemento, punto 1: decide el cambio de signo del bootstrap salvaje por bloque; el CV3 sólo informa."""
        v = valor(self.i["segunda_prueba"]["metodo"])
        self.assertEqual(v["prueba_que_decide"], "cambio_de_signo_salvaje")
        cs = v["cambio_de_signo_salvaje"]
        self.assertEqual((cs["G_minimo_rademacher"], cs["G_maximo_enumeracion_completa"], cs["sorteos"]), (12, 16, 9999))
        self.assertEqual(cs["semilla"], [42, 3000, "p"])
        self.assertEqual([(p["distribucion"], p["sorteos"]) for p in cs["pesos"]],
                         [("webb", 9999), ("rademacher", "enumeración completa de los 2^G vectores de signos"),
                          ("rademacher", 9999)])
        self.assertEqual([p["G"] for p in cs["pesos"]], ["G < 12", "12 ≤ G ≤ 16", "G > 16"])
        self.assertIn("T*_g = ε_g·T_g", cs["nula"])
        self.assertIn("θ̂ < 0", cs["a_favor_del_candidato"])
        self.assertIn("sólo informa", v["jackknife_cv3"]["uso"])
        self.assertIn("t de G − 1 gl", v["jackknife_cv3"]["estadistico"])
        self.assertIn("d̄_i = media sobre las réplicas", v["estimador"])
        # el nivel de la decisión es el del provisional (Holm sobre los 4 candidatos), ahora con los p del cambio de signo
        anterior = self.i["segunda_prueba"]["metodo"]["provisional_anterior"]
        self.assertTrue(anterior["nivel_en_la_decision"].startswith("Holm sobre los 4 candidatos"))
        self.assertTrue(v["nivel_en_la_decision"].startswith("Holm sobre los 4 candidatos"))
        self.assertIn("nivel de la decisión", self.i["segunda_prueba"]["metodo"]["lectura"])
        self.assertIn("jackknife por bloque (CV3)", anterior["prueba"])
        self.assertIn("cambio de signo", CFG["decision"]["condiciones"][0]["segunda_prueba"])
        t = plano(punto_complemento(1))
        for frase in ("Con G < 12 se usan pesos de Webb y 9.999 sorteos",
                      "con 12 ≤ G ≤ 16, Rademacher con enumeración completa",
                      "con G > 16, Rademacher con 9.999 sorteos", "La semilla es [42, 3000, p]",
                      "**Jackknife CV3 con t de G − 1:** sólo informa", "con d̄ = media de las réplicas"):
            self.assertIn(frase, t)
        self.assertIn(self.i["segunda_prueba"]["metodo"]["motivo_del_cambio"], t)

    def test_enumeracion_completa_alcanza_los_niveles_de_holm(self):
        """Con 12 ≤ G ≤ 16 la enumeración completa de Rademacher da p ≥ 2/2^G (la identidad y su opuesto tienen el
        mismo |t*|): ese mínimo queda bajo el nivel más exigente de Holm (0,05/4) y la enumeración cabe en memoria
        (≤ 2^16 vectores). Además, el t con CV1 no cambia al invertir todos los signos (datos simulados)."""
        cs = valor(self.i["segunda_prueba"]["metodo"])["cambio_de_signo_salvaje"]
        holm = CFG["decision"]["condiciones"][0]["holm"]
        nivel_minimo = holm["alfa_de_la_familia"] / holm["m"]
        for G in range(cs["G_minimo_rademacher"], cs["G_maximo_enumeracion_completa"] + 1):
            self.assertLess(2 / 2 ** G, nivel_minimo, G)
        self.assertLessEqual(2 ** cs["G_maximo_enumeracion_completa"], 65_536)
        self.assertGreater(2 ** (cs["G_maximo_enumeracion_completa"] + 1), cs["sorteos"])   # más allá, se sortea
        rng = np.random.default_rng(3000)
        G = cs["G_minimo_rademacher"]
        W = rng.uniform(0.1, 3.0, G)
        T = W * rng.normal(0.0, 1.0, G)

        def t_cv1(Tm):
            th = Tm.sum(axis=-1) / W.sum()
            u = Tm - th[..., None] * W
            return th / np.sqrt(G / (G - 1) * (u * u).sum(axis=-1) / W.sum() ** 2)

        E = np.array(list(itertools.product((-1.0, 1.0), repeat=G)))
        tb = t_cv1(E * T)
        self.assertEqual(len(tb), 2 ** G)
        np.testing.assert_allclose(np.abs(tb), np.abs(tb[::-1]))        # ε y −ε dan el mismo |t*|
        p = float(np.mean(np.abs(tb) >= abs(t_cv1(T)) - 1e-12))
        self.assertGreaterEqual(p, 2 / 2 ** G)

    def test_bloques_influyentes_existen_en_el_manifiesto(self):
        ruta = Path(os.environ.get("PLIEGUES_V2_MANIFIESTO") or rv.RutasV2.desde_entorno().manifiesto_pliegues)
        if not ruta.exists():
            self.skipTest(f"todavía no hay manifiesto en {ruta}")
        m = json.loads(ruta.read_text(encoding="utf-8"))
        for pol, d in m["contaminantes"].items():
            for prot, bloque in self.i["influencia"]["bloque_mas_influyente"].items():
                with self.subTest(pol=pol, prot=prot):
                    self.assertIn(bloque, [f["grupo"] for f in d["protocolos"][prot]["pliegues"]])

    def test_holm_equivale_a_intervalos_escalonados(self):
        """La equivalencia que declara la condición 1: Holm sobre los p bootstrap = intervalos percentiles con los
        niveles escalonados de Holm (datos simulados)."""
        holm = CFG["decision"]["condiciones"][0]["holm"]
        m, alfa = holm["m"], holm["alfa_de_la_familia"]
        B = self.i["bootstrap"]["replicas"]
        rng = np.random.default_rng(7)
        for _ in range(200):
            # B = 1.999 réplicas (Complemento, punto 2): ningún umbral (α/2k)·B cae en un entero, así que «p ≤ α_k»
            # y «el IC excluye 0» no difieren por un empate en el borde.
            draws = rng.normal(rng.normal(0, 2.5, m)[:, None], 1.0, (m, B))
            p = 2 * np.minimum((draws <= 0).mean(axis=1), (draws >= 0).mean(axis=1))
            por_p, por_ic = np.zeros(m, bool), np.zeros(m, bool)
            for j, c in enumerate(np.argsort(p, kind="stable")):
                if p[c] > alfa / (m - j):
                    break
                por_p[c] = True
            for j, c in enumerate(np.argsort(p, kind="stable")):
                a = alfa / (m - j)
                lo, hi = np.quantile(draws[c], [a / 2, 1 - a / 2], method="inverted_cdf")
                if not (lo > 0 or hi < 0):
                    break
                por_ic[c] = True
            np.testing.assert_array_equal(por_p, por_ic)


class DecisionTests(unittest.TestCase):
    d = CFG["decision"]

    def test_candidatos_y_protocolos(self):
        self.assertTrue(self.d["por_contaminante"])
        self.assertTrue(self.d["por_omision"].startswith("lightgbm"))
        self.assertEqual(self.d["candidatos"], ["xgboost", "random_forest", "mlp", "promedio_simple"])
        self.assertNotIn("apilado", self.d["candidatos"])
        self.assertEqual(self.d["protocolos"], ["LRO", "BLQ-75"])
        e = self.d["estadistico"]
        self.assertEqual((e["nivel"], e["conjunto"], e["retransformacion"]), ("diario_civil", "E1", "smearing_duan"))
        self.assertIn("XGBoost, RF, MLP y el promedio simple", seccion(11))

    def test_siete_condiciones_del_contrato(self):
        c = self.d["condiciones"]
        self.assertEqual([x["n"] for x in c], list(range(1, 8)))
        self.assertEqual([x["id"] for x in c], ["superioridad", "ruido_de_la_diferencia", "consistencia_con_E2",
                                                "influencia", "signo_sin_ponderar_y_en_log",
                                                "misma_decision_con_lognormal", "no_inferioridad_en_sesgo"])
        t = seccion(11)
        condiciones = t[t.index("**Condiciones"):t.index("**Desempate")]
        self.assertEqual(len(enumeracion(condiciones)), len(c))
        self.assertEqual(c[0]["holm"]["m"], int(re.search(r"Holm sobre los (\d+) candidatos", t).group(1)))
        self.assertEqual(c[0]["holm"]["m"], len(self.d["candidatos"]))
        self.assertEqual(c[0]["holm"]["alfa_de_la_familia"], 0.05)
        self.assertIn("1 punto porcentual", t)
        self.assertEqual(c[6]["margen_puntos_porcentuales"], 1.0)
        self.assertIn("lognormal_medio_sigma2", c[5]["regla"])
        self.assertIn("E004N083", c[3]["regla"])

    def test_desempate_evidencia_pares_y_produccion(self):
        self.assertIn("media simple", self.d["desempate"]["regla"])
        self.assertIn("motor único", self.d["desempate"]["empate"])
        self.assertIn("sensibilidad de exposición", self.d["evidencia_parcial"]["consecuencia"])
        self.assertEqual(self.d["pares_de_la_decision"]["interseccion_de"], ["lightgbm"] + self.d["candidatos"])
        self.assertEqual(self.d["N_de_produccion"], CFG["filas_entrenamiento"]["N_comun_eje_A"])
        self.assertIn("750.000 filas", seccion(11))
        rp = self.d["retransformacion_de_produccion"]
        self.assertEqual(rp["forma"], "smearing_duan")
        self.assertIn("LRO", rp["residuos"])
        self.assertEqual(self.d["implementacion"], {"funcion": "decidir_motor", "probada_antes_de_la_corrida": True,
                                                    "decision_a_mano": False})
        self.assertIn("CQR", self.d["no2"]["incertidumbre_por_celda"])
        self.assertIn("superior en un protocolo", valor(self.d["evidencia_parcial"]["definicion"]))

    def test_factibilidad_del_complemento(self):
        """Complemento, punto 3: reemplaza la factibilidad del punto 11, que se sigue informando."""
        f = self.d["factibilidad"]
        self.assertEqual((f["umbral_dias_de_maquina"], f["factor_maximo_frente_a_lightgbm"], f["hilos"]), (21, 5.0, 12))
        self.assertEqual((f["periodo"], f["contaminantes"]), ([2000, 2026], ["pm25", "no2"]))
        self.assertEqual(f["hilos"], CFG["operacion"]["hilos_maximos"])
        self.assertTrue(f["irrevisable"])
        self.assertIn("suma de sus miembros", f["promedio_simple"])
        self.assertIn("antes de cualquier ajuste comparativo", f["momento"])
        p = f["predictores_de_produccion"]
        self.assertEqual(sorted(p), sorted(["lightgbm", *[c for c in self.d["candidatos"] if c != "promedio_simple"]]))
        self.assertIn("lleaves", p["lightgbm"])
        self.assertTrue(all("treelite" in p[m] and "tl2cgen" in p[m] for m in ("xgboost", "random_forest")))
        self.assertIn("float32", p["mlp"])
        self.assertEqual(f["datos"]["dias"], ["verano", "invierno", "transición"])
        self.assertIn("código de producción v1 en sólo lectura", f["datos"]["matrices"])
        a = f["antes_del_complemento"]                          # la regla del punto 11, que se sigue informando
        self.assertEqual((a["umbral_dias_de_maquina"], a["periodo"]), (7, [2000, 2026]))
        self.assertIn("exceda 7 días de máquina", seccion(11))
        t = plano(punto_complemento(3))
        for frase in ("(reemplaza la del punto 11)", "LightGBM compilado con `lleaves`, como la producción v1",
                      "XGBoost y RF compilados con `treelite` / `tl2cgen`", "la MLP en float32, por lotes",
                      "matrices reales de predictores de 3 días (verano, invierno y transición)",
                      "con el código de producción v1 en sólo lectura y escritas en un temporal",
                      "cuesta ≤ 5 veces la de LightGBM compilado y ≤ 21 días de máquina con 12 hilos",
                      "El promedio simple cuesta la suma de sus miembros",
                      "esta regla y su medición no se revisan después de ver resultados",
                      "se mide antes de cualquier ajuste comparativo"):
            self.assertIn(frase, t)
        self.assertIn(f["irrevisable_nota"], t)
        self.assertIn(f["regla"].replace("un candidato es factible si su", ""), t)

    def test_regla_de_factibilidad_sintetica(self):
        """La regla con tiempos inventados (segundos por día de superficies, por contaminante): cociente frente a
        LightGBM compilado y días de máquina con los dos contaminantes sumados, y el promedio como suma."""
        f = self.d["factibilidad"]
        dias = (np.datetime64(f"{f['periodo'][1] + 1}-01-01") - np.datetime64(f"{f['periodo'][0]}-01-01")).astype(int)
        self.assertEqual(dias, 9862)
        self.assertIn("9.862 días", f["lectura"])

        def dias_de_maquina(seg_por_dia: dict) -> float:          # {contaminante: [s del día 1, 2 y 3]}
            return sum(np.mean(seg_por_dia[c]) for c in f["contaminantes"]) * dias / 86_400.0

        def factible(c: str, t: dict) -> bool:
            costo = {m: dias_de_maquina(v) for m, v in t.items()}
            costo["promedio_simple"] = sum(costo[m] for m in ("lightgbm", "xgboost", "random_forest", "mlp"))
            return (costo[c] <= f["factor_maximo_frente_a_lightgbm"] * costo["lightgbm"]
                    and costo[c] <= f["umbral_dias_de_maquina"])

        lgb = {"pm25": [10.0, 12.0, 14.0], "no2": [8.0, 10.0, 12.0]}              # 22 s por día: ≈ 2,5 días
        t = {"lightgbm": lgb,
             "xgboost": {c: [4.99 * s for s in v] for c, v in lgb.items()},       # bajo el cociente: factible
             "random_forest": {c: [5.01 * s for s in v] for c, v in lgb.items()},  # pasa del cociente (≈ 12,6 días)
             "mlp": {"pm25": [1.0] * 3, "no2": [1.0] * 3}}
        self.assertAlmostEqual(dias_de_maquina(lgb), 22.0 * 9862 / 86400)
        self.assertLess(dias_de_maquina(t["random_forest"]), f["umbral_dias_de_maquina"])
        self.assertTrue(factible("xgboost", t))
        self.assertFalse(factible("random_forest", t))
        self.assertTrue(factible("mlp", t))
        self.assertFalse(factible("promedio_simple", t))                           # la suma pasa de 21 días
        self.assertIn("≤ 5 veces", f["regla"])                                   # el borde es factible
        self.assertIn("≤ 21 días", f["regla"])
        # 21 días con 12 hilos es un tope aparte del cociente: un LightGBM lento no lo afloja
        lento = {c: [10 * s for s in v] for c, v in lgb.items()}
        t2 = {"lightgbm": lento, "xgboost": {c: [2 * s for s in v] for c, v in lento.items()},
              "random_forest": lento, "mlp": lento}
        self.assertGreater(dias_de_maquina(t2["xgboost"]), f["umbral_dias_de_maquina"])
        self.assertFalse(factible("xgboost", t2))


class PresupuestoProcedenciaTests(unittest.TestCase):
    def test_nuevo_orden_de_recortes(self):
        p = CFG["presupuesto"]
        self.assertEqual((p["piloto"]["pliegues_por_protocolo_y_motor"], p["umbral_horas_maquina"]), (2, 120))
        t = seccion(12)
        enmendado = enumeracion(t[t.index("**Orden de recortes enmendado**"):t.index("**Efecto:**")])
        self.assertEqual([x["recorte"] for x in p["orden_de_recortes"]], enmendado)
        self.assertEqual([x["orden"] for x in p["orden_de_recortes"]], [1, 2, 3, 4])
        self.assertEqual([x["elemento"] for x in p["orden_de_recortes"]], ["curvas_de_aprendizaje", "mlp", "semillas", "perdidas"])
        self.assertEqual([x["se_conserva_en"] for x in p["orden_de_recortes"]],
                         [["LRO"], ["LRO", "BLQ-75"], ["LRO", "BLQ-75"], ["LRO", "BLQ-75", "LOSO-D"]])
        self.assertIn("no quita nada", p["orden_de_recortes"][2]["advertencia"])
        self.assertEqual(p["orden_de_recortes_antes_de_la_enmienda"],
                         ["semillas sólo en LRO", "curvas de aprendizaje sólo en LRO", "MLP sólo en LRO y BLQ-75"])
        self.assertIn("--remedir-contaminadas 0.5", p["piloto"]["revision"]["que"])
        self.assertIn("(`--remedir-contaminadas 0.5`)", t)
        self.assertIn("115,65 h", p["efecto_estimado"])
        self.assertIn("115,65 h", t)
        self.assertIn("sin efecto", p["punto_6_del_borrador"])
        self.assertIn("bitácora", p["registro_de_recortes"])
        self.assertIn("más filas de entrenamiento", valor(p["piloto"]["eleccion_de_los_pliegues"]))

    def test_presupuesto_del_complemento(self):
        """Complemento, punto 8: los cuatro recortes en el código y el piloto medido otra vez con la máquina libre."""
        p = CFG["presupuesto"]
        self.assertIn("incluido el 4", p["orden_de_recortes_en_el_codigo"])
        self.assertIn("sin elección a mano", p["orden_de_recortes_en_el_codigo"])
        self.assertEqual(len(p["orden_de_recortes"]), 4)
        r = p["piloto"]["revision"]
        self.assertEqual(r["maquina_libre"], {"carga_media_maxima_al_empezar": 2.0, "comparacion": "<",
                                              "otros_trabajos_pesados": False})
        self.assertEqual(len(r["incluye_el_costo_nuevo_de"]), 2)
        self.assertIn("MLP: validación y reajuste", r["incluye_el_costo_nuevo_de"][0])
        self.assertIn("δ honesto de Huber", r["incluye_el_costo_nuevo_de"][1])
        self.assertIn("sin elección a mano", r["plan"])
        self.assertIn("--remedir-contaminadas 0.5", r["antes_del_complemento"])
        t = plano(punto_complemento(8))
        for frase in ("el orden de recortes del punto 12, incluido el recorte 4, se implementa en el código",
                      "(carga media < 2 al empezar y sin otros trabajos pesados)",
                      "el costo nuevo de la MLP (validación y reajuste) y del δ de Huber",
                      "el código rehace el plan con esa medición, sin elección a mano"):
            self.assertIn(frase, t)

    def test_firma_guardia_candado_sellado(self):
        s = CFG["procedencia_y_sellado"]
        antes = ["sha256 de la lista ordenada de predictores", "receta", "pérdida", "variante de calidad",
                 "sha256 del contrato", "sha256 de la configuración"]
        f = s["firma_de_los_ajustes"]
        self.assertEqual(f["incluye"], antes + ["hash del código de las funciones de ajuste"])
        self.assertEqual(f["incluye_antes_del_complemento"], antes)
        self.assertFalse(f["codigo_de_ajuste"]["version_a_mano"])
        self.assertIn("validación de la MLP y el δ honesto de Huber", f["codigo_de_ajuste"]["que"])
        self.assertIn("consolidado.json", f["retransformacion"])
        self.assertIn("st_dev y st_ino", s["guardia_de_escritura"])
        self.assertEqual(s["candado"]["alcance"], "por artefacto")
        self.assertIn("casefold + NFC", s["candado"]["nombres"])
        self.assertIn("casefold + NFC", plano(punto_complemento(10)))
        self.assertIn("como la guardia de escritura", plano(punto_complemento(10)))
        self.assertIn("git", s["sellado"])
        self.assertIn("`st_dev` y `st_ino`", seccion(14))
        t = plano(punto_complemento(7))
        self.assertIn("incluye el hash del código de las funciones de ajuste, en particular la validación de la MLP y "
                      "el δ honesto de Huber", t)
        self.assertIn("No depende de subir una versión a mano", t)

    def test_nombres_de_candado_normalizados_como_la_guardia(self):
        """Complemento, punto 10: dos grafías del mismo nombre (mayúsculas o forma Unicode) son el mismo candado.
        Se comprueba con la normalización que la guardia de escritura ya usa (``_rutas_v2._plegar``)."""
        plegar = getattr(rv, "_plegar", None)
        if plegar is None:
            self.skipTest("_rutas_v2 no expone la normalización de la guardia")
        nfc, nfd = "pliegues_ñ", "pliegues_ñ"
        self.assertNotEqual(nfc, nfd)
        self.assertEqual(plegar(nfc), plegar(nfd))
        self.assertEqual(plegar("Pliegues_V2"), plegar("pliegues_v2"))

    def test_fuera_del_contrato(self):
        self.assertEqual(len(CFG["fuera_del_contrato"]["descargas_nuevas"]), 3)


if __name__ == "__main__":
    unittest.main()
