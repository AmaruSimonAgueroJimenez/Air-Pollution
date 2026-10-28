"""Pruebas de umbrales.py (Anexo A, §4.3 del diseño) y el detector de literales (§4.5).

Dueño: I2 (ola 1). Leen, sin escribir, el texto de M0 (v2.1), el vigente (v2.3), el JSON de umbrales y
``m0/preparar_m0.py`` de APH, cada uno con su sha256, y el Anexo P de ``DISENO_IMPLEMENTACION_M1.md``; si falta un
archivo, se omiten con el motivo y no se dan por aprobadas. Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
"""
import sys

sys.dont_write_bytecode = True

import ast  # noqa: E402
import copy  # noqa: E402
import dataclasses  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import io  # noqa: E402
import re  # noqa: E402
import tokenize  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import constantes, umbrales  # noqa: E402
from meteo_combinada.umbrales import ErrorUmbrales  # noqa: E402

_PAQUETE = Path(umbrales.__file__).resolve().parent
_APH = _RAIZ.parent.parent / "Air-Pollution-Health-Chile"
_TEXTO_M0 = _APH / umbrales.TEXTO_M0
_VIGENTE = _APH / umbrales.TEXTO_VIGENTE
_JSON = _APH / umbrales.JSON_M0
_PREPARAR = _APH / umbrales.PREPARAR_M0
_DISENO = _PAQUETE / "DISENO_IMPLEMENTACION_M1.md"


class _ConM0(unittest.TestCase):
    """Base: textos, JSON y preparar_m0 de APH, leídos una vez y comprobados por sha256."""

    @classmethod
    def setUpClass(cls):
        for ruta in (_TEXTO_M0, _VIGENTE, _JSON, _PREPARAR):
            if not ruta.is_file():
                raise unittest.SkipTest(f"falta {ruta.name}; la prueba no se da por aprobada")
        cls.bytes_m0 = _TEXTO_M0.read_bytes()
        cls.bytes_vigente = _VIGENTE.read_bytes()
        cls.bytes_json = _JSON.read_bytes()
        cls.texto_m0 = cls.bytes_m0.decode("utf-8")
        cls.vigente = cls.bytes_vigente.decode("utf-8")
        cls.publicado = json.loads(cls.bytes_json.decode("utf-8"))
        cls.U = umbrales.cargar_m0(_APH)

    def regenerado(self, texto=None, nombre=None):
        texto = self.texto_m0 if texto is None else texto
        return umbrales.regenerar_desde_texto(texto, nombre or _TEXTO_M0.name,
                                              hashlib.sha256(texto.encode("utf-8")).hexdigest(),
                                              self.publicado["opciones_m0"])


def _anexo_p() -> dict[str, list[str]]:
    """Grupo → ids del Anexo P del diseño, en orden y sin repetir."""
    if not _DISENO.is_file():
        raise unittest.SkipTest("falta DISENO_IMPLEMENTACION_M1.md")
    texto = _DISENO.read_text(encoding="utf-8")
    seccion = texto[texto.index("## Anexo P."):]
    salida = {}
    for linea in seccion.splitlines():
        if linea.startswith("| ") and not linea.startswith("| Grupo"):
            celdas = [c.strip() for c in re.split(r"(?<!\\)\|", linea)[1:-1]]
            ids = []
            for i in re.findall(r"`([A-Z][A-Z0-9_]*)`", celdas[1]):
                if i not in ids:
                    ids.append(i)
            salida[celdas[0]] = ids
    return salida


class PruebasM1Umbrales(_ConM0):
    def test_json_regenerado_byte_a_byte(self):
        """§4.3, punto 1: desde el v2.1 (su fuente declarada) el JSON sale igual byte a byte (156587f1…); m-8: el
        Anexo A del texto vigente (v2.3) es idéntico, y regenerar desde él sólo cambia generado_desde."""
        self.assertEqual(hashlib.sha256(self.bytes_json).hexdigest(), umbrales.SHA_JSON_M0)
        regenerado = self.regenerado()
        self.assertEqual(umbrales.serializar(regenerado), self.bytes_json)
        self.assertEqual(umbrales.seccion_anexo_a(self.vigente), umbrales.seccion_anexo_a(self.texto_m0))
        desde_vigente = self.regenerado(self.vigente, _VIGENTE.name)
        self.assertEqual(desde_vigente["anexo_a"], regenerado["anexo_a"])
        self.assertEqual(desde_vigente["generado_desde"],
                         {"archivo": _VIGENTE.name, "sha256": umbrales.SHA_TEXTO_VIGENTE})
        self.assertEqual(len(regenerado["anexo_a"]), 27)
        with self.assertRaises(ErrorUmbrales):        # la huella que se declara debe ser la del texto
            umbrales.regenerar_desde_texto(self.texto_m0, _TEXTO_M0.name, "0" * 64, {})

    def test_opciones_m0_por_ast(self):
        """§4.3, punto 2 (MC-35): opciones_m0 no sale del Anexo A; es OPCIONES_M0 de m0/preparar_m0.py (49503a3a…),
        leído por AST. D2 = 8 son los procesos de orquestacion (§8, constantes.PROCESOS)."""
        from meteo_combinada import fijados
        self.assertEqual(hashlib.sha256(_PREPARAR.read_bytes()).hexdigest(), umbrales.SHA_PREPARAR_M0)
        self.assertEqual(umbrales.SHA_PREPARAR_M0, fijados.SHA_PREPARAR_M0)      # la misma huella en los dos módulos
        opciones = fijados.opciones_m0(_APH)
        self.assertEqual(opciones, self.publicado["opciones_m0"])
        self.assertEqual(list(opciones), list(self.publicado["opciones_m0"]))
        self.assertEqual(dict(self.U.opciones_m0), opciones)
        self.assertEqual(self.U.opciones_m0["D2"], 8)
        self.assertEqual(self.U.opciones_m0["D2"], constantes.valor("PROCESOS"))

    def test_comparar_estricto(self):
        """§4.3, punto 3: comparar(publicado, regenerado) == []; tipos, orden de claves, claves de más y filas faltantes
        hacen fallar la comparación."""
        regenerado = self.regenerado()
        self.assertEqual(umbrales.comparar(self.publicado, regenerado), [])
        casos = []
        a = copy.deepcopy(self.publicado)
        a["opciones_m0"]["D2"] = 8.0                                 # int → float
        casos.append((a, "tipo"))
        a = copy.deepcopy(self.publicado)
        a["opciones_m0"] = dict(reversed(list(a["opciones_m0"].items())))
        casos.append((a, "orden"))
        a = copy.deepcopy(self.publicado)
        a["otra"] = 1
        casos.append((a, "sólo en el publicado"))
        a = copy.deepcopy(self.publicado)
        del a["anexo_a"][-1]
        casos.append((a, "elementos"))
        a = copy.deepcopy(self.publicado)
        a["anexo_a"][0]["texto"] = a["anexo_a"][0]["texto"].replace("−39", "−38")
        casos.append((a, "anexo_a[0].texto"))
        for alterado, señal in casos:
            with self.subTest(señal=señal):
                difs = umbrales.comparar(alterado, regenerado)
                self.assertTrue(any(señal in d for d in difs), difs)
        texto = self.texto_m0.replace("| Centinelas | Ts −40,0;", "| Centinelas | Ts −41,0;")
        self.assertNotEqual(texto, self.texto_m0)
        self.assertTrue(umbrales.comparar(self.publicado, self.regenerado(texto)))

    def test_traducir_todos_los_ids_del_anexo_p(self):
        """§4.3, punto 4: traducir da todos los ids del Anexo P, grupo por grupo y en orden, y cada valor es el del
        texto (con su tipo)."""
        anexo_p = _anexo_p()
        self.assertEqual(list(anexo_p), list(umbrales.PLANTILLAS))
        for grupo, plantilla in umbrales.PLANTILLAS.items():
            ids = []
            for ident, _ in umbrales._ids_de_plantilla(plantilla):
                if ident not in ids:
                    ids.append(ident)
            with self.subTest(grupo=grupo):
                self.assertEqual(ids, anexo_p[grupo])
        valores = umbrales.traducir(self.publicado["anexo_a"])
        self.assertEqual(tuple(valores), umbrales.IDS)
        self.assertEqual(len(valores), 150)
        esperados = {"QTS_MIN": -39, "QTS_MAX": 50, "QQFE_BAJO": -80, "QQFE_ALTO": 50, "QQFF_MAX": 1065,
                     "CENT_TS": -40.0, "CENT_TOL": 0.05, "HR_SAT": 100, "HR_RECORTE_MAX": 103, "F_23H": 1.5,
                     "INCOH_TD": 2.0, "EG_MAD_K": 1.4826, "RHO_MIN_KM": 0.1, "K4_T2B_HPA": 1.2, "K4_COINC_FRAC": 0.3,
                     "HOM_TD": 1.0, "Q2_DESDE": 2000, "Q2_HASTA": 2009, "GAMMA_K_KM": -6.5,
                     "NUC_L": (10, 25, 50, 100, 200), "NUC_LAMBDA": (0, 50, 150), "NUC_KAPPA": (0.05, 0.2, 0.5, 1.0),
                     "C_ALFAS": (0.1, 1, 10, 100, 1000), "C_FILAS": 4000, "SEMILLA": 20261023, "SEL_MOD": 11,
                     "SEL_RESTO": 3, "SEL_MOD_RECORTE": 23, "SEL_UMBRAL_H": 36, "MIN_HORAS": 2000,
                     "BANDAS_KM": (10, 25, 50), "BOOT_REPLICAS": 1999, "CD_MULT": 1.1, "EX_HR": 2.0,
                     "NIVEL_MULT": 1.15, "FMT_RELLENO": -32768, "FMT_ESC_P": 0.02, "FMT_DESP_P": 800,
                     "M6_N": 750000, "M6_NMB_PP": 1, "M6_TF_DESDE": 2015, "M6_TF_HASTA": 2024}
        for ident, valor in esperados.items():
            with self.subTest(ident=ident):
                self.assertEqual(valores[ident], valor)
                self.assertIs(type(valores[ident]), type(valor))
                if isinstance(valor, tuple):
                    self.assertEqual([type(x) for x in valores[ident]], [type(x) for x in valor])
        self.assertEqual(dict(self.U.valores), valores)

    def test_constantes_contra_texto_y_completitud(self):
        """§4.3, punto 5: constantes.verificar_contra_texto(texto) == [] y completitud(texto) == [], y cada repetición
        del cuerpo vale lo que su id del Anexo A."""
        self.assertEqual(constantes.verificar_contra_texto(self.vigente), [])
        self.assertEqual(constantes.completitud(self.vigente), [])
        self.assertEqual(constantes.verificar_repeticiones(self.U.valores), [])

    def test_huellas_y_cargar_exige_sha(self):
        """§4.3, punto 6: las huellas del JSON y de los textos van al addendum; cargar_umbrales exige la del JSON."""
        self.assertEqual(hashlib.sha256(self.bytes_m0).hexdigest(), umbrales.SHA_TEXTO_M0)
        self.assertEqual(hashlib.sha256(self.bytes_vigente).hexdigest(), umbrales.SHA_TEXTO_VIGENTE)
        self.assertEqual((self.U.sha256_json, self.U.sha256_texto, self.U.sha256_texto_vigente),
                         (umbrales.SHA_JSON_M0, umbrales.SHA_TEXTO_M0, umbrales.SHA_TEXTO_VIGENTE))
        self.assertEqual(self.publicado["generado_desde"], {"archivo": _TEXTO_M0.name, "sha256": umbrales.SHA_TEXTO_M0})
        with self.assertRaises(ErrorUmbrales):
            umbrales.cargar_umbrales(_JSON, _TEXTO_M0, sha256_json="0" * 64)
        U = umbrales.cargar_umbrales(_JSON, _TEXTO_M0, sha256_json=umbrales.SHA_JSON_M0)
        self.assertEqual(U.huella(), umbrales.Umbrales(self.U.valores, opciones_m0=self.U.opciones_m0).huella())
        with self.assertRaises(ErrorUmbrales):       # con el vigente cambia generado_desde: el JSON no es el suyo
            umbrales.cargar_umbrales(_JSON, _VIGENTE)


class PruebasUmbrales(_ConM0):
    def test_numero_del_texto(self):
        f = umbrales.numero_del_texto
        self.assertEqual((f("−39"), f("+50"), f("1.065"), f("0,05"), f("1.000"), f("20261023"), f("−32768")),
                         (-39, 50, 1065, 0.05, 1000, 20261023, -32768))
        self.assertIs(type(f("1,0")), float)
        self.assertIs(type(f("750.000")), int)
        for malo in ("-39", "1,065.0", "1 000", "", "1.06", "0.5", 1):
            with self.subTest(malo=malo), self.assertRaises(ErrorUmbrales):
                f(malo)
        self.assertEqual(umbrales._lista_del_texto("{0,1; 1; 10; 100; 1.000}"), (0.1, 1, 10, 100, 1000))
        with self.assertRaises(ErrorUmbrales):
            umbrales._lista_del_texto("{0,05, 0,2}")       # decimales con «, »: ambiguo
        with self.assertRaises(ErrorUmbrales):
            umbrales._lista_del_texto("{0; 50; 150}")      # enteros con «; » (UMB-10)

    def test_plantillas_coherentes(self):
        """27 grupos en el orden del Anexo A; las listas sin índice; BANDAS_KM armado por índice (UMB-2)."""
        self.assertEqual(list(umbrales.PLANTILLAS), [f["grupo"] for f in self.publicado["anexo_a"]])
        self.assertEqual(len(umbrales.IDS), len(set(umbrales.IDS)))
        self.assertEqual(umbrales.traducir(self.publicado["anexo_a"])["BANDAS_KM"], (10, 25, 50))
        self.assertEqual(umbrales.PLANTILLAS["Decisión"], self.publicado["anexo_a"][24]["texto"])
        valores = self.U.valores
        self.assertEqual({i: len(valores[i]) for i in umbrales.IDS_LISTA}, umbrales.LARGO_LISTAS)
        self.assertEqual(sorted(i for i, v in valores.items() if not isinstance(v, tuple) and v < 0),
                         sorted(umbrales.IDS_NEGATIVOS))              # UMB-9: los ids con «−» son los negativos

    def test_traduccion_no_se_desvia(self):
        """Si una fila cambia fuera de los números, o un id repetido vale distinto en dos lugares, traducir falla."""
        filas = self.publicado["anexo_a"]
        cambios = [(2, "≥ 4 reportes", "≥ 4 reportes como mínimo"),       # texto nuevo
                   (2, "HR = 100 y calma", "HR = 99 y calma"),              # HR_SAT distinto dentro del grupo
                   (4, "HR (100, 103] → 100", "HR (100, 103] → 101"),       # HR_SAT distinto entre grupos
                   (22, "semilla 20261023", "semilla 20261024"),            # SEMILLA distinta entre grupos
                   (20, "0-10, 10-25", "0-10, 11-25"),                      # BANDAS_KM[0] distinto
                   (13, "{0,05; 0,2; 0,5; 1,0}", "{0,05, 0,2, 0,5, 1,0}"),  # separador de decimales
                   (0, "−39", "-39"),                                      # signo ASCII
                   (24, "menor S en E1", "menor S en E0"),                  # la fila sin ids
                   (0, "−80/+50", "−80/50"),                                # UMB-9: QQFE_ALTO exige «+»
                   (8, "12 + 12 meses", "12 + +12 meses"),                   # sin signo donde el texto no lo trae
                   (12, "Γ = −6,5 K/km", "Γ = +6,5 K/km"),                   # GAMMA exige «−»
                   (12, "Γ = −6,5 K/km", "Γ = 6,5 K/km"),
                   (23, "+ 0,05 hPa", "+0,05 hPa"),
                   (13, "λ {0, 50, 150}", "λ {0; 50; 150}"),                 # UMB-10: enteros con «, »
                   (13, "κ {0,05; 0,2; 0,5; 1,0}", "κ {0,05; 0,2; 0,5}")]   # UMB-10: largo de la lista
        for i, viejo, nuevo in cambios:
            alteradas = copy.deepcopy(filas)
            self.assertIn(viejo, alteradas[i]["texto"], (i, viejo))
            alteradas[i]["texto"] = alteradas[i]["texto"].replace(viejo, nuevo)
            with self.subTest(cambio=nuevo), self.assertRaises(ErrorUmbrales):
                umbrales.traducir(alteradas)
        with self.assertRaises(ErrorUmbrales):
            umbrales.traducir(filas[1:] + filas[:1])
        with self.assertRaises(ErrorUmbrales):
            umbrales.traducir(filas[:-1])

    def test_regeneracion_estricta(self):
        """Filas mal formadas y marcadores repetidos no se ignoran (UMB-8)."""
        fila = "| RR06 | s/p = 0; válido en [0, 200] mm |"
        self.assertIn(fila, self.texto_m0)
        for texto in (self.texto_m0.replace(fila, fila + "\n" + fila),
                      self.texto_m0.replace(fila, "| RR06 | s/p = 0 | válido en [0, 200] mm |"),
                      self.texto_m0.replace(fila, "| RR06 |"),
                      self.texto_m0 + "\n## Anexo A. Otra\n"):
            self.assertNotEqual(texto, self.texto_m0)
            with self.assertRaises(ErrorUmbrales):
                self.regenerado(texto)

    def test_umbrales_inmutable_y_ids(self):
        U = self.U
        with self.assertRaises(dataclasses.FrozenInstanceError):
            U.sha256_json = "x"
        with self.assertRaises(TypeError):
            U.valores["QTS_MIN"] = 0
        with self.assertRaises(ErrorUmbrales):
            U.a("NO_EXISTE")
        with self.assertRaises(ErrorUmbrales):
            umbrales.Umbrales({"QTS_MIN": -39})
        malos = dict(U.valores)
        malos["QTS_MIN"] = True
        with self.assertRaises(ErrorUmbrales):
            umbrales.Umbrales(malos)
        self.assertIsInstance(U.a("NUC_L"), tuple)

    def test_frac_solo_para_pct(self):
        self.assertEqual(self.U.frac("Q1_PCT"), 0.1)
        self.assertEqual(self.U.frac("SOPORTE_PCT"), 0.5)
        pct = [i for i in umbrales.IDS if i.endswith("_PCT")]
        self.assertGreater(len(pct), 10)
        with self.assertRaises(ErrorUmbrales):
            self.U.frac("QTS_MIN")
        with self.assertRaisesRegex(ErrorUmbrales, "puntos de porcentaje"):      # UMB-12
            self.U.frac("SECO_HR_PCT")
        self.assertEqual(self.U.a("SECO_HR_PCT"), 2)

    def test_vigentes_y_huella(self):
        v = self.U.vigentes()
        self.assertEqual(v["valores"]["NUC_L"], [10, 25, 50, 100, 200])
        self.assertEqual(json.loads(json.dumps(v)), v)
        self.assertEqual(len(self.U.huella()), 64)


# ---------------------------------------------------------------------------------------------
# Detector de literales (§4.5 del diseño; heurístico). La lista se revisa en la revisión de M1.

LISTA_BLANCA = (0, 1, 2, 12, 24, 60, 3600, 100, 1000, math.pi)
MIN_ARCHIVOS = 25               # el paquete tiene 28 módulos y __init__ (§1 del diseño); se revisan todos menos 3
EXCLUIDOS = {
    "umbrales.py": "fuente de los umbrales del Anexo A",
    "constantes.py": "fijos del cuerpo y del Anexo B (A2) y definiciones, verificados contra el texto",
    "sintetico.py": "generadores independientes (no importa el paquete)",
}
_MARCA = re.compile(r"#\s*no-umbral:\s*\S.{2,}")

# (archivo, línea sin sangría) → motivo. Se vacía antes de sellar M1 (§4.5 del diseño). Sólo se agregan entradas del
# código del coordinador; lo de otros dueños se informa y lo corrige su dueño o el coordinador al integrar.
TOLERADOS: dict[tuple[str, str], str] = {}


def _valores_de_umbral(U) -> set:
    """Los valores del Anexo A y del A2; además, la forma de fracción (v/100) de los ``*_PCT`` (salvo los que no son
    fracciones, UMB-12) y el valor absoluto de los negativos («x − 6.5*dz», «ts + 39»)."""
    valores, pct = set(), []
    for ident, v in U.valores.items():
        partes = v if isinstance(v, tuple) else (v,)
        valores.update(partes)
        if ident.endswith("_PCT") and ident not in umbrales.PCT_NO_FRACCION:
            pct.extend(partes)
    for c in constantes.CONSTANTES:
        partes = [x for x in constantes._aplanar(c.valor) if not isinstance(x, str)]
        valores.update(partes)
        if c.nombre.endswith("_PCT"):
            pct.extend(partes)
    valores.update(x / 100 for x in pct)
    valores.update(-x for x in list(valores) if x < 0)
    return valores


def _comentarios(fuente: str) -> dict[int, str]:
    """Línea → texto de su comentario (tokenize): la marca «no-umbral» vale sólo en un comentario, no en una cadena."""
    salida: dict[int, str] = {}
    for tok in tokenize.generate_tokens(io.StringIO(fuente).readline):
        if tok.type == tokenize.COMMENT:
            salida[tok.start[0]] = tok.string
    return salida


def _literales_de_umbral(fuente: str, valores) -> list[tuple[int, Any, str]]:
    """(línea, valor, texto de la línea) de cada literal numérico (con su signo) que coincide con un valor del Anexo A
    o del A2, no está en la lista blanca y cuya línea no lleva, en un comentario, «# no-umbral: <motivo>»."""
    arbol = ast.parse(fuente)
    lineas = fuente.splitlines()
    comentarios = _comentarios(fuente)
    con_signo, salida = {}, []
    for nodo in ast.walk(arbol):
        if (isinstance(nodo, ast.UnaryOp) and isinstance(nodo.op, (ast.USub, ast.UAdd))
                and isinstance(nodo.operand, ast.Constant)):
            con_signo[id(nodo.operand)] = nodo
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Constant) or isinstance(nodo.value, bool):
            continue
        if not isinstance(nodo.value, (int, float)):
            continue
        valor = nodo.value
        if id(nodo) in con_signo and isinstance(con_signo[id(nodo)].op, ast.USub):
            valor = -valor
        if valor not in valores or any(valor == b for b in LISTA_BLANCA):
            continue
        texto = lineas[nodo.lineno - 1]
        if _MARCA.search(comentarios.get(nodo.lineno, "")):
            continue
        salida.append((nodo.lineno, valor, texto.strip()))
    return sorted(salida, key=lambda x: (x[0], str(x[1])))



class PruebasLiterales(_ConM0):
    def _hallados(self):
        valores = _valores_de_umbral(self.U)
        salida, revisados = [], []
        for ruta in sorted(_PAQUETE.glob("*.py")):
            if ruta.name in EXCLUIDOS:
                continue
            revisados.append(ruta.name)
            for linea, valor, texto in _literales_de_umbral(ruta.read_text(encoding="utf-8"), valores):
                salida.append((ruta.name, linea, valor, texto))
        todos = list(_PAQUETE.glob("*.py"))
        self.assertEqual(len(revisados), len(todos) - len(EXCLUIDOS))
        self.assertGreaterEqual(len(revisados), MIN_ARCHIVOS)
        self.assertTrue(all((_PAQUETE / e).is_file() for e in EXCLUIDOS))
        return salida

    def test_literales(self):
        """§4.5: ningún valor del Anexo A ni del A2 aparece como literal fuera de umbrales, constantes y sintetico (AST;
        lista blanca explícita; marca «# no-umbral: <motivo>»; TOLERADOS con su motivo)."""
        hallados = [f"{a}:{n}: {v!r} en «{t}»" for a, n, v, t in self._hallados() if (a, t) not in TOLERADOS]
        self.assertEqual(hallados, [], "literales que coinciden con el Anexo A o el A2; use U.a/U.frac o constantes, "
                                       "o marque la línea con «# no-umbral: <motivo>»:\n" + "\n".join(hallados))

    def test_tolerados_vigentes(self):
        """Cada entrada de TOLERADOS corresponde a un literal que el detector todavía encuentra, y tiene motivo."""
        vistos = {(a, t) for a, _, _, t in self._hallados()}
        self.assertEqual(sorted(set(TOLERADOS) - vistos), [], "entradas de TOLERADOS que ya no hacen falta")
        self.assertTrue(all(m.strip() for m in TOLERADOS.values()))

    def test_detector_de_literales(self):
        """El detector ve signos y flotantes, ignora la lista blanca, los booleanos y los textos, y acepta la marca
        con motivo (no sin él)."""
        valores = _valores_de_umbral(self.U)
        fuente = ("a = 0.95\nb = -39\nc = 60\nd = 24\ne = 16  # no-umbral: radio de otra cosa\n"
                  "f = 16  # no-umbral:\ng = True\nh = 'texto 0.05'\ni = 7.25\nj = 1000\nk = -6.5\nl = 3\n"
                  "m = x - 6.5 * dz\nn = ts + 39\no = frac >= 0.99\np = (x, 'no-umbral: inventado'); q = 48\n")
        hallados = [(linea, valor) for linea, valor, _ in _literales_de_umbral(fuente, valores)]
        self.assertEqual(hallados, [(1, 0.95), (2, -39), (6, 16), (11, -6.5), (12, 3), (13, 6.5), (14, 39), (15, 0.99),
                                    (16, 48)])
        self.assertIn(0.05, valores)        # del Anexo A (CENT_TOL) …
        self.assertIn(1e-06, valores)       # … y del A2 (TF_CERO_TOL)
        self.assertIn(0.95, valores)        # ZE5L_NASADEM_PCT como fracción
        for ident in umbrales.IDS:
            if ident.endswith("_PCT") and ident not in umbrales.PCT_NO_FRACCION:
                self.assertIn(self.U.a(ident) / 100, valores, ident)
        for v in list(valores):
            if v < 0:
                self.assertIn(-v, valores)


if __name__ == "__main__":
    unittest.main()
