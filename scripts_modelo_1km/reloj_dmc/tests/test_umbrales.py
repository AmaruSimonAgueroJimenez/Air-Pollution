"""Pruebas de umbrales.py (Anexo B, constantes del texto y §8.F).

Leen, sin escribir, el texto y el JSON anclados en C0 (APH/auditoria/20261023/reloj_dmc/); si faltan,
se omiten con el motivo y no se dan por aprobadas. Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .
"""
import sys

sys.dont_write_bytecode = True

import ast  # noqa: E402
import copy  # noqa: E402
import dataclasses  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from reloj_dmc import constantes, umbrales  # noqa: E402
from reloj_dmc.umbrales import ErrorUmbrales  # noqa: E402

_PAQUETE = Path(umbrales.__file__).resolve().parent
_APH = _PAQUETE.parents[1].parent / "Air-Pollution-Health-Chile"
_PROTOCOLO = _APH / umbrales.PROTOCOLO_C0
_JSON = _APH / umbrales.JSON_C0


class _ConC0(unittest.TestCase):
    """Base: texto y JSON de C0, leídos una vez y comprobados por sha256."""

    @classmethod
    def setUpClass(cls):
        for ruta in (_PROTOCOLO, _JSON):
            if not ruta.is_file():
                raise unittest.SkipTest(f"falta {ruta.name} anclado en C0; la prueba no se da por aprobada")
        cls.bytes_texto = _PROTOCOLO.read_bytes()
        cls.bytes_json = _JSON.read_bytes()
        cls.texto = cls.bytes_texto.decode("utf-8")
        cls.publicado = json.loads(cls.bytes_json.decode("utf-8"))
        cls.U = umbrales.cargar_c0(_APH)

    def regenerado(self, texto=None):
        return umbrales.regenerar_desde_texto(self.texto if texto is None else texto, _PROTOCOLO.name)


class PruebasC1Umbrales(_ConC0):
    def test_c1_huellas_de_c0(self):
        """El texto y el JSON leídos son los anclados en C0."""
        self.assertEqual(hashlib.sha256(self.bytes_texto).hexdigest(), umbrales.SHA_PROTOCOLO_C0)
        self.assertEqual(hashlib.sha256(self.bytes_json).hexdigest(), umbrales.SHA_JSON_C0)
        self.assertEqual(self.U.sha256_json, umbrales.SHA_JSON_C0)

    def test_c1_json_regenerado_coincide_con_anexo_b(self):
        """regenerar_desde_texto(texto) == reloj_dmc_v1.json salvo claves ajenas."""
        regenerado = self.regenerado()
        self.assertEqual(umbrales.comparar(self.publicado, regenerado), [])
        # Mismo algoritmo que c0/preparar_c0: el JSON sale igual byte a byte.
        self.assertEqual((json.dumps(regenerado, ensure_ascii=False, indent=1) + "\n").encode("utf-8"),
                         self.bytes_json)
        # «bateria» (R-04) no entra en la comparación; cualquier otra clave sí.
        self.assertEqual(umbrales.comparar({**self.publicado, "bateria": {"archivo": "x", "sha256": "0" * 64}},
                                           regenerado), [])
        self.assertTrue(umbrales.comparar({**self.publicado, "otra": 1}, regenerado))

    def test_c1_texto_o_json_alterados_fallan(self):
        """Cualquier cambio del Anexo B o del JSON hace fallar la comparación de C1."""
        texto = self.texto.replace("| E3p | E3P_MU | 0,03 → 0,05 → 0,08 |", "| E3p | E3P_MU | 0,04 → 0,05 → 0,08 |")
        self.assertNotEqual(texto, self.texto)
        difs = umbrales.comparar(self.publicado, self.regenerado(texto))
        self.assertTrue(any("E3P_MU.anclado" in d for d in difs), difs)
        texto = self.texto.replace("- A4: 10 %.", "- A4: 15 %.")
        difs = umbrales.comparar(self.publicado, self.regenerado(texto))
        self.assertTrue(any("fijos_texto[28]" in d for d in difs), difs)

        alterado = copy.deepcopy(self.publicado)
        alterado["ajustables"]["E4P_A2_EE"]["anclado"] = 3.0          # int → float
        self.assertTrue(any("tipo" in d for d in umbrales.comparar(alterado, self.regenerado())))
        alterado = copy.deepcopy(self.publicado)
        alterado["ajustables"] = dict(reversed(list(alterado["ajustables"].items())))
        self.assertTrue(any("orden" in d for d in umbrales.comparar(alterado, self.regenerado())))
        alterado = copy.deepcopy(self.publicado)
        del alterado["fijos_texto"][-1]
        self.assertTrue(umbrales.comparar(alterado, self.regenerado()))

    def test_c1_regeneracion_estricta(self):
        """Filas mal formadas, filas repetidas o líneas sueltas en «Fijos» no se ignoran."""
        fila = "| E3p | E3P_MU | 0,03 → 0,05 → 0,08 |"
        for texto in (self.texto.replace(fila, fila + "\n" + fila),
                      self.texto.replace(fila, "| E3p | E3P_MU | 0,03 → 0,05 → 0,08 | x |"),
                      self.texto.replace(fila, "| E3p | E3P_MU | 0,03 o 0,04 → 0,05 → 0,08 |"),
                      self.texto.replace("- **Red:**\n", "- **Red:**\nTexto suelto con 0,5.\n"),
                      self.texto.replace("**Fijos** (no se ajustan).", "**Fijos** (no se ajustan). **Fijos**")):
            self.assertNotEqual(texto, self.texto)
            with self.assertRaises(ErrorUmbrales):
                self.regenerado(texto)

    def test_c1_cargar_exige_huella_y_coincidencia(self):
        with self.assertRaises(ErrorUmbrales):
            umbrales.cargar_umbrales(_JSON, _PROTOCOLO, sha256_json="0" * 64)
        U = umbrales.cargar_umbrales(_JSON, _PROTOCOLO, sha256_json=umbrales.SHA_JSON_C0)
        self.assertEqual(U.huella(), self.U.huella())

    def test_c1_fijos_calzan_linea_a_linea(self):
        """Las 33 líneas calzan con PLANTILLAS_FIJOS y dan 124 valores."""
        fijos = umbrales.traducir_fijos(self.publicado["fijos_texto"])
        self.assertEqual(len(self.publicado["fijos_texto"]), 33)
        self.assertEqual(len(fijos), 124)
        self.assertEqual(tuple(fijos), umbrales.IDS_FIJOS)
        esperados = {"TS_CENTINELA": -40.0, "TS_MIN": -60, "QFE_MAX": 1100, "COORD_TOL_GRADOS": 0.0005,
                     "PIXEL_MES_VALIDEZ_1": 200001, "E3D_DZ_TS_M": 1000, "SEMILLA": 20261022,
                     "E4P_S2_FASE_H": 9.75, "E4_EE_FACTOR": 2, "E3_VENTANA": 9, "A4_PCT": 10,
                     "E4T_VENTANA_HASTA_H": 19.0, "BAT_HORAS_MAX": 48, "CUARENTENA_MESES": 1}
        for ident, valor in esperados.items():
            self.assertEqual(fijos[ident], valor, ident)
            self.assertIs(type(fijos[ident]), type(valor), ident)
        self.assertEqual(dict(self.U.fijos), fijos)

    def test_c1_fijos_no_se_desvian(self):
        """Si el texto cambia fuera de los números, o un número se escribe distinto, la traducción falla."""
        lineas = self.publicado["fijos_texto"]
        cambios = [(1, "racha de 12 h.", "racha de 12 horas."), (1, "−40,0", "-40,0"),
                   (2, "1.100", "1100.0"), (28, "10 %", "10%"), (0, "Datos", "Datos ")]
        for i, viejo, nuevo in cambios:
            alteradas = list(lineas)
            self.assertIn(viejo, alteradas[i])
            alteradas[i] = alteradas[i].replace(viejo, nuevo)
            with self.assertRaises(ErrorUmbrales, msg=nuevo):
                umbrales.traducir_fijos(alteradas)
        with self.assertRaises(ErrorUmbrales):
            umbrales.traducir_fijos(lineas[:-1])
        with self.assertRaises(ErrorUmbrales):
            umbrales.traducir_fijos(lineas[1:] + lineas[:1])

    def test_c1_plantillas_coherentes(self):
        """Ids únicos, sin cruce con los ajustables; un id es *_PCT si y sólo si lo sigue « %»."""
        ids = [i for p in umbrales.PLANTILLAS_FIJOS for i in re.findall(r"\{([A-Z0-9_]+)\}", p)]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertFalse(set(ids) & set(umbrales.IDS_AJUSTABLES))
        for p in umbrales.PLANTILLAS_FIJOS:
            for m in re.finditer(r"\{([A-Z0-9_]+)\}", p):
                self.assertEqual(m.group(1).endswith("_PCT"), p[m.end():].startswith(" %"), m.group(1))

    def test_numero_del_texto(self):
        """«−40,0», «1.100», «0,0005», «200001»."""
        casos = {"−40,0": -40.0, "1.100": 1100, "0,0005": 0.0005, "200001": 200001, "1.013,25": 1013.25,
                 "0,30": 0.3, "3": 3}
        for token, esperado in casos.items():
            obtenido = umbrales.numero_del_texto(token)
            self.assertEqual(obtenido, esperado, token)
            self.assertIs(type(obtenido), type(esperado), token)
        for malo in ("-40,0", "1,100.5", "1.10", "", "12 h", "+3", "0.5", " 3"):
            with self.assertRaises(ErrorUmbrales, msg=malo):
                umbrales.numero_del_texto(malo)

    def test_ajustables_valores_y_pares(self):
        """E3P_MU = 0.03; E1B_PATRON = (0.75, 2); E6_I12 = (0.6, 5)."""
        U = self.U
        self.assertEqual(U.a("E3P_MU"), 0.03)
        self.assertEqual(U.a("E1B_PATRON"), (0.75, 2))
        self.assertEqual(U.a("E6_I12"), (0.6, 5))
        self.assertEqual(U.a("E6_I15"), (0.8, 2))
        self.assertIs(type(U.a("E4P_A2_EE")), int)
        self.assertIs(type(U.a("E3T_TAU")), float)
        self.assertEqual(tuple(U.ajustables), umbrales.IDS_AJUSTABLES)
        self.assertEqual(set(U.pasos.values()), {0})
        with self.assertRaises(ErrorUmbrales):
            U.a("TS_MIN")
        with self.assertRaises(ErrorUmbrales):
            U.f("E3P_MU")
        with self.assertRaises(ErrorUmbrales):
            U.f("NO_EXISTE")

    def test_umbrales_inmutable(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            self.U.pasos = {}
        with self.assertRaises(TypeError):
            self.U.pasos["E3P_MU"] = 2
        with self.assertRaises(TypeError):
            self.U.fijos["TS_MIN"] = 0
        with self.assertRaises(TypeError):
            self.U.ajustables["E3P_MU"]["anclado"] = 0.5

    def test_frac_solo_para_pct(self):
        """U.frac('A4_PCT') == 0.10; U.frac('E3P_MU') lanza."""
        self.assertEqual(self.U.frac("A4_PCT"), 0.10)
        self.assertEqual(self.U.frac("C3B_RECUP_PCT"), 0.95)
        for ident in ("E3P_MU", "TS_MIN", "E2_OBSERVADOR"):
            with self.assertRaises(ErrorUmbrales, msg=ident):
                self.U.frac(ident)

    def test_lineas_conocidas_coinciden_con_tipos(self):
        """Las líneas de §8.F (con y sin filas) son exactamente tipos.Linea."""
        from reloj_dmc import tipos
        self.assertEqual(set(umbrales.FILAS_POR_LINEA) | set(umbrales.LINEAS_SIN_FILAS), {l.value for l in tipos.Linea})
        self.assertFalse(set(umbrales.FILAS_POR_LINEA) & set(umbrales.LINEAS_SIN_FILAS))

    def test_constantes_del_texto_citadas_literalmente(self):
        """constantes.verificar_contra_texto(texto de C0, version="v1") == [] (contra cada versión del texto,
        y en particular la vigente, en PruebasConstantesPorVersion)."""
        self.assertEqual(constantes.verificar_contra_texto(self.texto, version="v1"), [])
        self.assertEqual(constantes.valor("E3_CCONT_MAX"), 8)
        self.assertEqual(constantes.valor("SPENCER")[3], -0.032077)
        with self.assertRaises(KeyError):
            constantes.valor("NO_EXISTE")
        # Todos los fragmentos son del cuerpo del texto, no de los anexos.
        cuerpo = self.texto[:self.texto.index("## Anexo A.")]
        for c in constantes.CONSTANTES:
            self.assertTrue(c.seccion.startswith("§"), c.nombre)
            if c.fragmento_en("v1") is not None:
                self.assertIn(c.fragmento_en("v1"), cuerpo, c.nombre)

    def test_constantes_detecta_desvios(self):
        """Valor, fragmento, sección, números sobrantes o versión distintos del texto dan un problema."""
        base = constantes.POR_NOMBRE["E3_CCONT_MAX"]
        malas = [dataclasses.replace(base, valor=9),
                 dataclasses.replace(base, fragmento="Se define sólo si |ĉ| ≤ 9."),
                 dataclasses.replace(base, seccion="§4.3.2"),
                 dataclasses.replace(base, seccion="§99.1"),
                 dataclasses.replace(base, desde="v9"),
                 dataclasses.replace(base, fragmento_anterior="Se define sólo si |ĉ| ≤ 8."),
                 dataclasses.replace(constantes.POR_NOMBRE["GRADOS_POR_HORA"], ajenos=(60,)),
                 dataclasses.replace(constantes.POR_NOMBRE["SPENCER"], valor=(229.18, 0.000075, 0.001868, 0.032077,
                                                                              -0.014615, -0.040849)),
                 dataclasses.replace(constantes.POR_NOMBRE["E6_PALABRAS"], valor=("AEROPUERTOS",)),
                 dataclasses.replace(constantes.POR_NOMBRE["COORD_LAT"], valor=(-17, -90))]
        for mala in malas:
            with mock.patch.object(constantes, "CONSTANTES", (mala,)):
                self.assertEqual(len(constantes.verificar_contra_texto(self.texto, version="v1")), 1, mala)
        with mock.patch.object(constantes, "CONSTANTES", (base, base)):
            self.assertTrue(any("repetido" in p for p in constantes.verificar_contra_texto(self.texto, version="v1")))
        with self.assertRaises(ValueError):
            constantes.verificar_contra_texto(self.texto, version="v1.3")

    def test_numeros_del_fragmento(self):
        f = constantes.numeros_del_fragmento
        self.assertEqual(f("z_pix = 44.330,8·[1 − (sp̄/1.013,25)^0,190263] m"), [44330.8, 1, 1013.25, 0.190263])
        self.assertEqual(f("con k ∈ {−24, 0, +24}"), [-24, 0, 24])
        self.assertEqual(f("con A1(Ts) ≥ 1 °C, E3p, t2m, κ3, 2π y cos 2B"), [1])
        self.assertEqual(f("Bloques: 00-05 y 2008-2026"), [0, 5, 2008, 2026])
        self.assertEqual(f("0,001868 cos B − 0,032077 sen B"), [0.001868, -0.032077])

    def test_sin_literales_de_umbral_en_modulos(self):
        """AST: ningún valor del Anexo B aparece como literal fuera de umbrales.py (lista blanca explícita)."""
        valores = _valores_del_anexo_b(self.U)
        hallados = []
        for ruta in sorted(_PAQUETE.glob("*.py")):
            if ruta.name in EXCLUIDOS:
                continue
            for linea, valor, texto in _literales_de_umbral(ruta.read_text(encoding="utf-8"), valores):
                if (ruta.name, texto) not in TOLERADOS:
                    hallados.append(f"{ruta.name}:{linea}: {valor!r} en «{texto}»")
        self.assertEqual(hallados, [], "literales que coinciden con el Anexo B; use U.a/U.f/U.frac o constantes, "
                                       "o marque la línea con «# no-umbral: <motivo>»:\n" + "\n".join(hallados))

    def test_tolerados_vigentes(self):
        """Cada entrada de TOLERADOS corresponde a un literal que el detector todavía encuentra."""
        valores = _valores_del_anexo_b(self.U)
        vistos = set()
        for ruta in sorted(_PAQUETE.glob("*.py")):
            if ruta.name not in EXCLUIDOS:
                vistos.update((ruta.name, texto)
                              for _, _, texto in _literales_de_umbral(ruta.read_text(encoding="utf-8"), valores))
        self.assertEqual(sorted(set(TOLERADOS) - vistos), [], "entradas de TOLERADOS que ya no hacen falta")

    def test_detector_de_literales(self):
        """El detector ve signos, ignora la lista blanca y acepta la marca con motivo."""
        valores = _valores_del_anexo_b(self.U)
        fuente = ("a = 0.95\nb = -60\nc = 60\nd = 24\ne = x[:8]  # no-umbral: abreviatura de huella\n"
                  "f = 8  # no-umbral:\ng = True\nh = 'texto 0.95'\ni = 7\n")
        hallados = [(linea, valor) for linea, valor, _ in _literales_de_umbral(fuente, valores)]
        self.assertEqual(hallados, [(1, 0.95), (2, -60), (6, 8)])

    def test_pearson_minimo_con_nombre_y_sin_tolerados_pendientes(self):
        """PEN-4 de C1: el mínimo de pares de Pearson es la definición numerico.PEARSON_MIN_PARES (= 3), marcada
        «no-umbral», y no un literal tolerado; ninguna entrada de TOLERADOS queda «PENDIENTE»."""
        import numpy as np
        from reloj_dmc import numerico
        self.assertEqual(numerico.PEARSON_MIN_PARES, 3)
        self.assertTrue(math.isnan(numerico.pearson(np.array([1.0, 2.0]), np.array([2.0, 1.0]))))
        x, y = np.array([1.0, 2.0, 3.0]), np.array([2.0, 4.0, 6.5])
        self.assertAlmostEqual(numerico.pearson(x, y), float(np.corrcoef(x, y)[0, 1]), places=12)
        fuente = Path(numerico.__file__).read_text(encoding="utf-8")
        (linea,) = [l for l in fuente.splitlines() if l.startswith("PEARSON_MIN_PARES = ")]
        self.assertRegex(linea, _MARCA)
        self.assertIn("n < PEARSON_MIN_PARES", fuente)
        self.assertEqual([k for k, motivo in TOLERADOS.items() if motivo.startswith("PENDIENTE")], [])


class PruebasConstantesPorVersion(_ConC0):
    """Anexo B, «Fijos del cuerpo» [Enmienda 1, E1-5]: cada fragmento debe estar tal cual en el texto VIGENTE
    (constantes.VERSION_VIGENTE, hoy el v1.0.5 de la Enmienda 5), no sólo en el de C0. Se leen, sin escribir,
    las seis versiones de constantes.TEXTOS_PROTOCOLO, cada una con su sha256; si falta alguna, se omite
    y no se da por aprobada."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.textos = {}
        for version, ruta, sha in constantes.TEXTOS_PROTOCOLO:
            if not (_APH / ruta).is_file():
                raise unittest.SkipTest(f"falta el texto {version} ({ruta}); la prueba no se da por aprobada")
            datos = (_APH / ruta).read_bytes()
            cls.textos[version] = (hashlib.sha256(datos).hexdigest(), datos.decode("utf-8"))

    def test_versiones_del_texto_con_su_huella(self):
        """La primera versión es la de C0 (misma ruta y huella que umbrales); cada texto da su sha256; la
        vigente es la última; toda constante nace en una versión conocida."""
        self.assertEqual(constantes.TEXTOS_PROTOCOLO[0], ("v1", umbrales.PROTOCOLO_C0, umbrales.SHA_PROTOCOLO_C0))
        for version, _, sha in constantes.TEXTOS_PROTOCOLO:
            self.assertEqual(self.textos[version][0], sha, version)
        self.assertEqual(constantes.VERSION_VIGENTE, constantes.TEXTOS_PROTOCOLO[-1][0])
        self.assertEqual(len(set(constantes.VERSIONES_TEXTO)), len(constantes.VERSIONES_TEXTO))
        for c in constantes.CONSTANTES:
            constantes.indice_version(c.desde)
        with self.assertRaises(ValueError):
            constantes.indice_version("v1.3")

    def test_version_de_c1_v1_2(self):
        """PEN-9 de C1, con la Enmienda 5: el texto consolidado de C1 (§10) es ahora el v1.2 (el v1.0.5 con el
        cierre nuevo de C1), una versión conocida, posterior a la vigente y con sus mismos fragmentos. El v1.1, el
        del primer cierre, ya no es una versión de este código. Su sha256 no está aquí: el v1.2 cita la salida de
        la corrida de C1, que corre este código, así que su huella la fija el addendum de C1."""
        self.assertEqual(constantes.VERSION_VIGENTE, "v1.0.5")
        self.assertEqual(constantes.VERSION_C1, "v1.2")
        self.assertNotIn(constantes.VERSION_C1, constantes.VERSIONES_TEXTO)
        self.assertEqual(constantes.indice_version("v1.2"), constantes.indice_version(constantes.VERSION_VIGENTE) + 1)
        with self.assertRaises(ValueError):
            constantes.indice_version("v1.1")
        for c in constantes.CONSTANTES:
            self.assertEqual(c.fragmento_en("v1.2"), c.fragmento_en(constantes.VERSION_VIGENTE), c.nombre)
        vigente = self.textos[constantes.VERSION_VIGENTE][1]
        self.assertEqual(constantes.verificar_contra_texto(vigente, version="v1.2"), [])

    def test_c1_regenerar_desde_textos_con_fijos_del_cuerpo(self):
        """PEN-1 de C1: desde la Enmienda 1 (E1-5) el Anexo B cierra con «**Fijos del cuerpo** …», que no es una
        línea de fijos. regenerar_desde_texto lo corta como c0/preparar_c0.anexo_b: de cada versión sale el JSON
        de C0 (salvo «generado_desde»), y cargar_umbrales carga ese JSON con su texto y da la huella de C0. El
        párrafo repetido, una línea de fijos después de él o el párrafo pegado a otra línea se rechazan."""
        nombre, rotulo = "PROTOCOLO_RELOJ_DMC_v1.1.md", "**Fijos del cuerpo**"
        for version, (_, texto) in self.textos.items():
            with self.subTest(version=version):
                self.assertEqual(rotulo in texto, version != "v1")
                regenerado = umbrales.regenerar_desde_texto(texto, nombre)
                publicado = {**self.publicado, "generado_desde": regenerado["generado_desde"]}
                self.assertEqual(umbrales.comparar(publicado, regenerado), [])
                self.assertEqual(regenerado["fijos_texto"], self.publicado["fijos_texto"])
        vigente = self.textos[constantes.VERSION_VIGENTE][1]
        with tempfile.TemporaryDirectory() as carpeta:
            ruta_texto = Path(carpeta) / nombre
            ruta_texto.write_bytes(vigente.encode("utf-8"))
            datos = (json.dumps({**umbrales.regenerar_desde_texto(vigente, nombre),
                                 "bateria": {"archivo": "bateria_v1.csv", "sha256": "0" * 64}},
                                ensure_ascii=False, indent=1) + "\n").encode("utf-8")
            ruta_json = Path(carpeta) / "reloj_dmc_v1.json"
            ruta_json.write_bytes(datos)
            U = umbrales.cargar_umbrales(ruta_json, ruta_texto, sha256_json=hashlib.sha256(datos).hexdigest())
            self.assertEqual(U.huella(), self.U.huella())
        self.assertEqual(umbrales.FIJOS_DEL_CUERPO, rotulo)
        parrafo = vigente[vigente.index(rotulo):vigente.index("\n", vigente.index(rotulo))]
        for malo in (vigente.replace(parrafo, parrafo + "\n\n" + parrafo),
                     vigente.replace(parrafo, parrafo + "\n- Batería: 48 h."),
                     vigente.replace("\n" + parrafo, " " + parrafo)):
            self.assertNotEqual(malo, vigente)
            with self.assertRaises(ErrorUmbrales):
                umbrales.regenerar_desde_texto(malo, nombre)

    def test_constantes_contra_cada_version_y_la_vigente(self):
        """verificar_contra_texto(texto, version) == [] en las seis versiones; en cada una los fragmentos
        son del cuerpo. Con el fragmento de C0, SUBH_LAT_MAX no está en el v1.0.3 ni después (E3-5
        reescribió la frase). Las Enmiendas 4 y 5 no cambian ningún fragmento: los del v1.0.3 son los del v1.0.4
        y los del v1.0.5."""
        for version, (_, texto) in self.textos.items():
            self.assertEqual(constantes.verificar_contra_texto(texto, version=version), [], version)
            cuerpo = texto[:texto.index("## Anexo A.")]
            for c in constantes.CONSTANTES:
                if c.fragmento_en(version) is not None:
                    self.assertIn(c.fragmento_en(version), cuerpo, (version, c.nombre))
        vigente = self.textos[constantes.VERSION_VIGENTE][1]
        self.assertEqual(constantes.verificar_contra_texto(vigente), [])            # por omisión, la vigente
        problemas = constantes.verificar_contra_texto(vigente, version="v1.0.2")   # texto y versión cruzados
        self.assertEqual([p.split(":")[0] for p in problemas], ["SUBH_LAT_MAX"])
        subh = constantes.POR_NOMBRE["SUBH_LAT_MAX"]
        self.assertEqual(subh.fragmento_en("v1.0.2"), "de los años confirmados con |lat| ≤ 50° y ĉ^f_cont definido")
        self.assertEqual(subh.fragmento_en("v1.0.3"),
                         "en todos los años-régimen de la estación con |lat| ≤ 50° y ĉ^f_cont definido")
        self.assertIsNone(constantes.POR_NOMBRE["DIURNOS_DIA_MIN_VALORES"].fragmento_en("v1.0.2"))
        # Enmiendas 4 y 5: ningún fragmento cambia ni nace en el v1.0.4 ni en el v1.0.5.
        for previa, nueva in (("v1.0.3", "v1.0.4"), ("v1.0.4", "v1.0.5")):
            self.assertEqual([c.nombre for c in constantes.CONSTANTES
                              if c.fragmento_en(previa) != c.fragmento_en(nueva)], [], nueva)
            self.assertFalse([c.nombre for c in constantes.CONSTANTES if c.desde == nueva], nueva)
        # E5-2 reescribe la viñeta de P7, pero el fragmento de P7_PRESENCIA sigue tal cual en ella.
        p7 = next(l for l in vigente.splitlines() if l.startswith("- **P7, continuidad**"))
        self.assertIn("[Enmienda 5, E5-2]", p7)
        self.assertIn(constantes.POR_NOMBRE["P7_PRESENCIA"].fragmento, p7)

    def test_e5_texto_vigente(self):
        """Enmienda 5 en el texto vigente (v1.0.5): E5-1 en §8.E (C3b), E5-2 en §4.7 (P7), E5-3 en §5.4 y §6; el
        Anexo B es el del v1.0.4, byte a byte."""
        vigente = self.textos["v1.0.5"][1]
        anterior = self.textos["v1.0.4"][1]
        self.assertEqual(set(re.findall(r"\[Enmienda 5, (E5-\d)", vigente)), {"E5-1", "E5-2", "E5-3"})
        self.assertIn("- **Magallanes** [Enmienda 5, E5-3]. Al sur de 50° S no tiene regla fina", vigente)
        self.assertNotIn("F(0) puede confirmarse con E3p y E4p", vigente)
        self.assertIn("    - **Se espera** [Enmienda 5, E5-3;", vigente)
        self.assertIn("  - **Controles de red** [Enmienda 5, E5-1]. La red de C3b calcula A3", vigente)
        self.assertIn("  - **Referencia.** En una estación no costera que cumple las condiciones de E3d en Ts", vigente)

        def anexo_b(t):
            return t[t.index("## Anexo B."):t.index("## Anexo C.")]
        self.assertEqual(anexo_b(vigente), anexo_b(anterior))

    def test_repeticiones_de_umbrales_coinciden(self):
        """Las frases que la Enmienda 3 reescribió repiten umbrales de otras secciones; los módulos leen los
        originales, así que deben coincidir (si una enmienda cambia sólo uno, esta prueba falla)."""
        v = constantes.valor
        # §4.1.1, patrón de regla vencida: «con los umbrales del patrón civil(Z)».
        self.assertEqual(v("E1A_RV_MIN_AUSENTES"), v("E1A_PATRON_MIN_AUSENTES"))
        self.assertEqual(v("E1A_RV_AUSENTES_PCT"), v("E1A_PATRON_AUSENTES_PCT"))
        self.assertEqual(constantes.POR_NOMBRE["E1A_RV_MIN_AUSENTES"].ajenos, (self.U.a("E1A_P0"),))
        self.assertEqual(constantes.POR_NOMBRE["E1A_RV_AUSENTES_PCT"].ajenos, (self.U.a("E1A_PLACEBO"),))
        # §4.3.5, ρ: «el estadístico m de A5» (período 1 h, intervalo [−0,5; 0,5)).
        periodo, intervalo = v("SUBH_MEDIA_CIRCULAR")
        self.assertEqual(intervalo, v("A5_ENVOLVER"))
        self.assertEqual(periodo, v("A5_ENVOLVER")[1] - v("A5_ENVOLVER")[0])
        # §5.5 (fila de la parte con −4) y el «≥ 2 partes» de §4.0.
        self.assertEqual(v("DISCREPANCIAS_PARTES"), v("ANUAL_MIN_PARTES"))
        # §6 y §8.16 (E3-4) repiten los días de ≥ 20 valores de §4.3.3 y §4.4.
        self.assertEqual({v("DIURNOS_DIA_MIN_VALORES"), v("C16_DIA_MIN_VALORES"), v("E4_DIA_MIN_VALORES")},
                         {v("E3T_DIA_MIN_VALORES")})


class PruebasAjuste8F(_ConC0):
    def test_un_paso_hacia_lo_conservador(self):
        """ajustado('E3P_MU') da 0.05 y después 0.08."""
        U1 = self.U.ajustado("E3P_MU")
        self.assertEqual(U1.a("E3P_MU"), 0.05)
        self.assertEqual(U1.ajustado("E3P_MU").a("E3P_MU"), 0.08)
        self.assertEqual(self.U.a("E3P_MU"), 0.03)            # el original no cambia
        self.assertEqual(U1.pasos["E3P_MU"], 1)
        self.assertNotEqual(U1.huella(), self.U.huella())
        self.assertEqual(self.U.ajustado("E3P_TAU").a("E3P_TAU"), 0.4)      # aquí lo conservador es bajar
        self.assertEqual(self.U.ajustado("E1B_PATRON").a("E1B_PATRON"), (0.85, 3))
        # Sólo cambia el umbral movido.
        self.assertEqual({i: U1.a(i) for i in umbrales.IDS_AJUSTABLES if i != "E3P_MU"},
                         {i: self.U.a(i) for i in umbrales.IDS_AJUSTABLES if i != "E3P_MU"})

    def test_lista_agotada_lanza(self):
        """Tras 0.08, otro paso en E3P_MU lanza ErrorUmbrales."""
        U2 = self.U.ajustado("E3P_MU").ajustado("E3P_MU")
        self.assertTrue(U2.agotado("E3P_MU"))
        with self.assertRaises(ErrorUmbrales):
            U2.ajustado("E3P_MU")
        with self.assertRaises(ErrorUmbrales):
            self.U.ajustado("TS_MIN")             # los fijos no se ajustan

    def test_siguiente_ajuste_en_orden_de_filas(self):
        """E3p: E3P_MU antes que E3P_CONF; línea sin filas → None."""
        self.assertEqual(umbrales.siguiente_ajuste(self.U, "E3p"), "E3P_MU")
        U2 = self.U.ajustado("E3P_MU").ajustado("E3P_MU")
        self.assertEqual(umbrales.siguiente_ajuste(U2, "E3p"), "E3P_CONF")
        for linea in ("E3d", "P7", "E4t", "G-version"):
            self.assertIsNone(umbrales.siguiente_ajuste(self.U, linea))
        self.assertIsNone(umbrales.siguiente_ajuste(self.U.ajustado("E1B_PATRON"), "E1b"))
        self.assertEqual(umbrales.siguiente_ajuste(self.U, "T-P"), "TP_VENTANA")
        with self.assertRaises(ErrorUmbrales):
            umbrales.siguiente_ajuste(self.U, "E3P")

    def test_listas_y_pasos_solo_hacia_lo_conservador(self):
        """Una lista del Anexo B que vuelve atrás, o pasos fuera de la lista, se rechazan."""
        ajustables = copy.deepcopy(self.publicado["ajustables"])
        ajustables["E3P_TAU"]["lista_conservadora"] = [0.4, 0.6]
        with self.assertRaises(ErrorUmbrales):
            umbrales.Umbrales(ajustables=ajustables, fijos=self.U.fijos, pasos={}, sha256_json="")
        ajustables = copy.deepcopy(self.publicado["ajustables"])
        ajustables["E6_I12"]["lista_conservadora"] = [[0.7, 4]]
        with self.assertRaises(ErrorUmbrales):
            umbrales.Umbrales(ajustables=ajustables, fijos=self.U.fijos, pasos={}, sha256_json="")
        for pasos in ({"E3P_MU": 3}, {"E3P_MU": -1}, {"TS_MIN": 1}, {"E3P_MU": True}):
            with self.assertRaises(ErrorUmbrales, msg=pasos):
                umbrales.Umbrales(ajustables=self.publicado["ajustables"], fijos=self.U.fijos, pasos=pasos,
                                  sha256_json="")
        self.assertEqual(set(umbrales.SENTIDO_CONSERVADOR), set(umbrales.IDS_AJUSTABLES))


# ---------------------------------------------------------------------------------------------
# Detector de literales (heurístico, §4 del diseño). La lista se revisa en la revisión de C1.

LISTA_BLANCA = (0, 1, 2, 12, 24, 60, 3600, math.pi)
EXCLUIDOS = {
    "umbrales.py": "fuente de los umbrales del Anexo B",
    "constantes.py": "constantes del cuerpo, verificadas contra el texto (verificar_contra_texto)",
    "sintetico.py": "generadores independientes (§8, reglas comunes): no importa el paquete",
}
_MARCA = re.compile(r"#\s*no-umbral:\s*\S.{2,}")

# (archivo, línea sin sangría) → motivo. Sólo lo hallado en el código de otros dueños al cerrar esta
# parte (2026-10-23). «PENDIENTE» = el dueño debe cambiarlo; el resto no es un umbral.
TOLERADOS = {
    ("entorno.py", "_BLOQUE_LECTURA = 1 << 20"): "tamaño de bloque de lectura, no es umbral",
    ("fijados.py", 'modulo = cargar_por_ruta(Path(ap) / RUTA_DESCARGADOR, sha256, f"_reloj_dmc_descargador_{sha256[:8]}")'):
        "abreviatura de una huella en un nombre de módulo, no es umbral",
    ("fijados.py", 'raise ValueError(f"La huella de {ruta.name} no coincide con la fijada ({sha256[:8]}…)")'):
        "abreviatura de una huella en un mensaje, no es umbral",
    ("tablas.py", '"America/Coyhaique": 48, "Pacific/Easter": 52}'):
        "conteo de cambios del Anexo A (48 en Coyhaique), no es umbral",
    ("tipos.py", 'CODIGOS_DESCARTE = {0: "valido", 1: "ausente", 2: "centinela", 3: "rango", 4: "mediana", 5: "racha"}'):
        "códigos de descarte del extracto, no son umbrales",
}
# Ola 3 (integración, 2026-10-24): salieron de la lista «return hora % 3» (lineas_registro usa E2_MODULO),
# la ventana ±9 de numerico (numerico.desfases_ventana lee U.f("E3_VENTANA")), digest()[:8] (SEMILLA_BYTES)
# y DIVISOR_REGION = 1000 (REGION_DIVISOR). test_tolerados_vigentes impide que vuelvan a quedar entradas muertas.
# Cierre de C1 (2026-10-25, PEN-4): salió «if n < 3» de Pearson, que ahora es numerico.PEARSON_MIN_PARES, marcada
# «no-umbral» (test_pearson_minimo_con_nombre_y_sin_tolerados_pendientes).


def _valores_del_anexo_b(U):
    """Todos los valores del Anexo B: los 124 fijos y los ajustables con toda su lista."""
    valores = set(U.fijos.values())
    for ident in umbrales.IDS_AJUSTABLES:
        entrada = U.ajustables[ident]
        for v in (entrada["anclado"], *entrada["lista_conservadora"]):
            valores.update(v if isinstance(v, tuple) else (v,))
    return valores


def _literales_de_umbral(fuente, valores):
    """(línea, valor, texto de la línea) de cada literal numérico (con su signo) que coincide con un valor
    del Anexo B, no está en la lista blanca y cuya línea no lleva «# no-umbral: <motivo>»."""
    arbol = ast.parse(fuente)
    lineas = fuente.splitlines()
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
        if _MARCA.search(texto):
            continue
        salida.append((nodo.lineno, valor, texto.strip()))
    return sorted(salida)


if __name__ == "__main__":
    unittest.main()
