"""Pruebas de bateria.py (batería D y §8.F).

Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .
Los criterios y §8.F se prueban con resultados fabricados a mano sobre filas reales de bateria_v1.csv;
una red pequeña (dos estaciones de la red s+0.0_r01) pasa de punta a punta por orquestacion.evaluar_red,
con extractos en memoria y la ida y vuelta del adaptador fijado. El camino único (bateria_c1) se prueba
con correr_bateria simulada. Nada se escribe fuera de carpetas
temporales y nada se lee bajo /Volumes. Si faltan los umbrales de C0 o el código fijado, la prueba se
omite con el motivo y no se da por aprobada. La batería completa no se corre aquí.
"""
import sys

sys.dont_write_bytecode = True

import dataclasses  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from reloj_dmc import bateria, constantes, fijados, sintetico, umbrales  # noqa: E402
from reloj_dmc.tipos import Veredicto, validar_esquema  # noqa: E402

B = bateria
AP = _RAIZ.parent
APH = AP.parent / "Air-Pollution-Health-Chile"
_ESTADO: dict = {}


def _tabla() -> pd.DataFrame:
    if "tabla" not in _ESTADO:
        _ESTADO["tabla"] = B.tabla_bateria()
    return _ESTADO["tabla"]


def _U():
    if "U" not in _ESTADO:
        for ruta in (APH / umbrales.PROTOCOLO_C0, APH / umbrales.JSON_C0):
            if not ruta.is_file():
                raise unittest.SkipTest(f"falta {ruta.name} anclado en C0; la prueba no se da por aprobada")
        _ESTADO["U"] = umbrales.cargar_c0(APH)
    return _ESTADO["U"]


def _fila_de(celda: str, replica: int = 1) -> dict:
    t = _tabla()
    sel = t[(t["celda"] == celda) & (t["replica"] == replica)]
    if len(sel) != 1:
        raise AssertionError(f"celda sin fila única: {celda} r{replica}")
    return sel.iloc[0].to_dict()


def _resultado(fila: dict, anio: int, veredicto: str, clase=None, verdad="", **otros) -> dict:
    """Una fila de ESQUEMA_RESULTADOS fabricada a mano (los campos de la tabla salen de ``fila``)."""
    base = {c: fila[c] for c in ("red", "caso", "bloque", "celda", "reloj_verdadero", "tipo", "escenario",
                                 "territorio", "perturbacion", "valor_perturbacion", "replica")}
    confirmado = veredicto == "confirmado"
    miembros = set(clase.split("|")) if clase else set()
    base.update({"anio": anio, "veredicto": veredicto, "motivo": None,
                 "clase_confirmada": clase if confirmado else None,
                 "verdad": verdad,
                 "correcta": bool(confirmado and fila["tipo"] != "g" and verdad and miembros <= set(verdad.split("|"))),
                 "erronea": False, "cruce": False, "clase_paso_9": clase, "erronea_paso_9": False,
                 "excluyen_verdad": "", "lineas_apoyo": "E3p|E4p" if confirmado else "", "guarda_tp": "pasa",
                 "n_partes_discordantes": 0, "meses_con_regla": 12 if confirmado else 0, "reglas_vencidas": False,
                 "modo_e3t": "restringido", "media_horaria": False, "inestable": False, "cambios": "",
                 "ida_y_vuelta": "ok", "fallas_ida_y_vuelta": 0, "a4_restringe": False, "a5_alto": False})
    base.update(otros)
    return base


def _marco(filas: list[dict]) -> pd.DataFrame:
    """Resultados con «correcta» y «erronea» recalculadas por el módulo (BAT-2 y BAT-6), como en correr_red."""
    df = pd.DataFrame(filas, columns=list(B.ESQUEMA_RESULTADOS)).astype(B.ESQUEMA_RESULTADOS)
    df["correcta"] = [B.es_confirmacion_correcta(f) for _, f in df.iterrows()]
    df["erronea"] = [B.es_confirmacion_erronea(f) for _, f in df.iterrows()]
    return df.astype(B.ESQUEMA_RESULTADOS)


ANIOS = range(2008, 2027)
REFERENCIA = [f"D1|{r}|{t}|completo|ninguna|" for r in B.RELOJES_REFERENCIA for t in ("a", "b")]
VERDAD = {"F(0)": "F(0)", "F(-3)": "F(-3)", "F(-4)": "F(-4)", "C(America/Santiago)": "C(Santiago)"}
CAMBIO_2018 = "D1|F(-4);F(0)@2018-07-01T00:00Z|a|completo|ninguna|"
# Excepción a §8.28 («las salidas no contienen “@”»), pendiente de que el autor decida si rige en C1: el
# «@» de la gramática de tramos de sintetico («F(-4);F(0)@2018-07-01T00:00Z»), siempre detrás del «)» de un
# reloj y delante de un instante UTC en horas enteras. Cualquier otro «@» en una salida hace fallar la prueba.
EXCEPCION_8_28 = re.compile(rb"\)@\d{4}-\d{2}-\d{2}T\d{2}:00Z")


def _referencia_correcta(no_confirmados: dict | None = None) -> list[dict]:
    """Las 8 celdas de referencia (réplica 1), confirmadas con el verdadero en todos sus años, salvo
    ``no_confirmados`` = {celda: n años insuficientes}."""
    filas = []
    for celda in REFERENCIA:
        f = _fila_de(celda)
        verdad = VERDAD[f["reloj_verdadero"]]
        malos = (no_confirmados or {}).get(celda, 0)
        for i, anio in enumerate(ANIOS):
            if i < malos:
                filas.append(_resultado(f, anio, "insuficiente", verdad=verdad))
            else:
                filas.append(_resultado(f, anio, "confirmado", verdad, verdad))
    return filas


_COMPARACION = re.compile(r"(?:[≥≤<>]|\bmenos de)\s*(?=[−+]?\s?\d)")
_ENTRE_COMILLAS = re.compile(r"«[^»]*»")


def _textos_del_protocolo() -> dict[str, str]:
    """Las versiones de constantes.TEXTOS_PROTOCOLO, comprobadas por sha256 (se omite si falta alguna)."""
    textos = {}
    for version, ruta, sha in constantes.TEXTOS_PROTOCOLO:
        if not (APH / ruta).is_file():
            raise unittest.SkipTest(f"falta el texto {version} ({ruta}); la prueba no se da por aprobada")
        datos = (APH / ruta).read_bytes()
        if hashlib.sha256(datos).hexdigest() != sha:
            raise AssertionError(f"sha256 del texto {version} distinta de la de constantes.TEXTOS_PROTOCOLO")
        textos[version] = datos.decode("utf-8")
    return textos


# Enmienda 5 (v1.0.5): comparaciones de las líneas nuevas que repiten un umbral que ya está (no son fijos nuevos del
# cuerpo), en el orden del texto: (frase, valor, «anexo_b» o «cuerpo», nombre). Lo comprueba
# test_fijos_nuevos_del_cuerpo_en_cada_version.
REPETICIONES_V1_0_5 = (
    ("con z_cat legible y |Δz| ≤ 1.000 m", 1000, "anexo_b", "E3D_DZ_TS_M"),       # E5-2, referencia de P7
    ("m_h ≥ 2·máx(1, s_h^x)", 2, "anexo_b", "P7_FACTOR"),                          # E5-2, salto
    ("y m_h ≥ 1,5 °C", 1.5, "anexo_b", "P7_SALTO_C"),                              # E5-2, salto
    ("no tiene regla fina (|lat| > 50°)", 50, "cuerpo", "FINA_LAT_MAX"),            # E5-3, §6
    ("con |Δz| > 400 m", 400, "anexo_b", "E3T_DZ_M"),                               # E5-3, §6
)


def _comparaciones_sin_constante(previo: str, nuevo: str, version: str) -> tuple[int, list[str]]:
    """Comparaciones numéricas (≥, ≤, <, > o «menos de» seguidos de un número; no las de un «…») de las
    líneas del cuerpo de ``nuevo`` que no están en ``previo``, y las que no caen dentro del fragmento, en
    ``version``, de ninguna constante del cuerpo (constantes.py o CONSTANTES_BATERIA)."""
    cuerpo = lambda t: t[:t.index("## Anexo A.")]  # noqa: E731
    viejas = set(cuerpo(previo).splitlines())
    fragmentos = [f for c in (*constantes.CONSTANTES, *B.CONSTANTES_BATERIA)
                  if (f := c.fragmento_en(version)) is not None]
    n, faltan = 0, []
    for linea in cuerpo(nuevo).splitlines():
        if linea in viejas:
            continue
        mascara = _ENTRE_COMILLAS.sub(lambda m: " " * len(m.group()), linea)
        for m in _COMPARACION.finditer(mascara):
            n += 1
            pos = m.end()
            if not any(i <= pos < i + len(f) for f in fragmentos
                       for i in (j for j in range(len(linea)) if linea.startswith(f, j))):
                faltan.append(linea[max(0, pos - 40):pos + 20])
    return n, faltan


class PruebasConstantesDelCuerpo(unittest.TestCase):
    def test_constantes_de_la_bateria_citadas_literalmente(self):
        """BAT-12: CONSTANTES_BATERIA con su fragmento, dentro de §8.D y con sus números, en cada versión del
        texto (C0, v1.0.1, v1.0.2, v1.0.3, v1.0.4 y el vigente v1.0.5), con la misma regla que
        constantes.verificar_contra_texto. BATERIA_CORRECTA_LAT_S nace en el v1.0.3 (E3-6) y cita el 90 % de
        BAT_CORRECTA_PCT."""
        for version, texto in _textos_del_protocolo().items():
            with mock.patch.object(constantes, "CONSTANTES", B.CONSTANTES_BATERIA):
                self.assertEqual(constantes.verificar_contra_texto(texto, version=version), [], version)
        nombres = {c.nombre for c in constantes.CONSTANTES}
        self.assertFalse(nombres & {c.nombre for c in B.CONSTANTES_BATERIA}, "nombres repetidos con constantes.py")
        lat = next(c for c in B.CONSTANTES_BATERIA if c.nombre == "BATERIA_CORRECTA_LAT_S")
        self.assertEqual((lat.valor, lat.desde, lat.ajenos), (50, "v1.0.3", (_U().f("BAT_CORRECTA_PCT"),)))

    def test_fijos_nuevos_del_cuerpo_en_cada_version(self):
        """Anexo B, «Fijos del cuerpo» [Enmienda 1, E1-5]: cada comparación numérica de las líneas del cuerpo
        que una versión agregó o cambió cae dentro del fragmento de alguna constante del cuerpo de esa
        versión. Con la Enmienda 3 (v1.0.2 → v1.0.3) son, además de las que ya estaban, el patrón de regla
        vencida (§4.1.1), ρ (§4.3.5), la fila de §5.5, §6, §8.16 y §8.D; los nombres de reglas entre «…»
        («octubre, domingo ≥ 9») no cuentan. La Enmienda 4 (v1.0.3 → v1.0.4) no agrega ninguna: cambia el
        encabezado, el Estado, la frase de lo indecidible de §8.D y el registro de revisión, sin números.

        La Enmienda 5 (v1.0.4 → v1.0.5) reescribe la viñeta de P7 (E5-2) y la de Magallanes (E5-3). Sus 7
        comparaciones no traen umbrales nuevos: las dos de la primera línea de P7 caen en el fragmento de
        P7_PRESENCIA y las otras cinco repiten un umbral que ya está, cada una con su valor (REPETICIONES_V1_0_5):
        cuatro del Anexo B y la latitud de la regla fina. Toda otra comparación sin constante hace fallar la
        prueba, igual que antes."""
        textos = _textos_del_protocolo()
        versiones = list(textos)
        U = _U()
        nuevas_por_version = {}
        for previa, nueva in zip(versiones, versiones[1:]):
            n, faltan = _comparaciones_sin_constante(textos[previa], textos[nueva], nueva)
            if nueva == "v1.0.5":
                self.assertEqual(len(faltan), len(REPETICIONES_V1_0_5), faltan)
                for contexto, (frase, valor, origen, nombre) in zip(faltan, REPETICIONES_V1_0_5):
                    self.assertIn(frase, contexto)
                    self.assertEqual(U.f(nombre) if origen == "anexo_b" else constantes.valor(nombre), valor, nombre)
            else:
                self.assertEqual(faltan, [], f"{previa} → {nueva}: comparaciones sin constante del cuerpo")
            nuevas_por_version[nueva] = n
        self.assertGreaterEqual(nuevas_por_version["v1.0.3"], 10)
        self.assertEqual(nuevas_por_version["v1.0.4"], 0)
        self.assertEqual(nuevas_por_version["v1.0.5"], 7)
        # El detector ve una comparación nueva fuera de toda constante.
        vigente = textos[constantes.VERSION_VIGENTE]
        cambiado = vigente.replace("a ≤ 50° S", "a ≤ 50° S y a ≤ 45° de longitud")
        self.assertNotEqual(cambiado, vigente)
        self.assertEqual(len(_comparaciones_sin_constante(vigente, cambiado, constantes.VERSION_VIGENTE)[1]), 1)


class PruebasBateria(unittest.TestCase):
    def test_d_tabla_determinista_y_su_sha256(self):
        """bateria_v1.csv igual en dos generaciones; la sha256 es la del archivo; se relee igual."""
        t1, t2 = B.tabla_bateria(), B.tabla_bateria()
        pd.testing.assert_frame_equal(t1, t2)
        self.assertEqual(tuple(t1.columns), B.COLUMNAS_BATERIA)
        self.assertEqual(len(t1), 7320)
        with tempfile.TemporaryDirectory() as carpeta:
            a, b = Path(carpeta) / "a" / B.ARCHIVO_TABLA, Path(carpeta) / "b" / B.ARCHIVO_TABLA
            sha_a, sha_b = B.escribir_bateria(t1, a), B.escribir_bateria(t2, b)
            self.assertEqual(sha_a, sha_b)
            self.assertEqual(sha_a, B.huella_tabla(t1))
            datos = a.read_bytes()
            self.assertEqual(datos, b.read_bytes())
            self.assertNotIn(b"\r", datos)
            self.assertTrue(datos.endswith(b"\n"))
            self.assertEqual(datos.decode("utf-8").splitlines()[0], ",".join(B.COLUMNAS_BATERIA))
            leida = B.leer_bateria(a)
            pd.testing.assert_frame_equal(leida, t1)
            # 1/6 (semántica de −10 min) vuelve exacto, y el caso se reconstruye igual desde el CSV.
            fila = leida[(leida["perturbacion"] == "semantica")].iloc[0]
            self.assertEqual(sintetico.caso_de_fila(fila.to_dict()),
                             sintetico.caso_de_fila(t1.loc[fila.name].to_dict()))
            with self.assertRaises(ValueError):
                B.escribir_bateria(t1[list(reversed(B.COLUMNAS_BATERIA))], Path(carpeta) / "c.csv")

    def test_d_arroba_solo_en_la_gramatica_de_tramos(self):
        """§8.28 en bateria_v1.csv (BAT-15, pendiente del autor): todo «@» es el de EXCEPCION_8_28, sólo en las
        columnas «reloj_verdadero» y «celda», uno por cambio de tramo y por columna (720 en la tabla)."""
        t = _tabla()
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / B.ARCHIVO_TABLA
            B.escribir_bateria(t, ruta)
            datos = ruta.read_bytes()
            texto = pd.read_csv(ruta, dtype=str, keep_default_na=False)
        self.assertEqual(datos.count(b"@"), len(EXCEPCION_8_28.findall(datos)))
        for columna in texto.columns:
            if columna not in ("reloj_verdadero", "celda"):
                self.assertFalse(texto[columna].str.contains("@", regex=False).any(), columna)
        cambios = sum(len(r.tramos) - 1 for reloj in t["reloj_verdadero"] for r in sintetico.relojes_desde_texto(reloj))
        self.assertEqual(datos.count(b"@"), 2 * cambios)
        self.assertEqual(datos.count(b"@"), 720)

    def test_d_factores_y_celdas(self):
        """D1 (20 réplicas), D2 (10), D3 (10); celda = factores sin la réplica; la reducción a 5 sólo en D2
        y D3."""
        t = _tabla()
        celdas = B.celdas(t)
        self.assertEqual(len(celdas), 237 + 252 + 6)
        por_bloque = t.groupby("bloque")["celda"].nunique().to_dict()
        self.assertEqual(por_bloque, {"D1": 237, "D2": 252, "D3": 6})
        self.assertEqual(t.groupby("bloque").size().to_dict(), {"D1": 4740, "D2": 2520, "D3": 60})
        for celda, filas in t.groupby("celda"):
            n = {"D1": 20, "D2": 10, "D3": 10}[filas["bloque"].iloc[0]]
            self.assertEqual(sorted(filas["replica"]), list(range(1, n + 1)), celda)
            self.assertEqual(filas[["bloque", "reloj_verdadero", "tipo", "escenario", "perturbacion"]]
                             .drop_duplicates().shape[0], 1, celda)
        for f in t.drop_duplicates("celda").itertuples(index=False):
            valor = "" if f.valor_perturbacion != f.valor_perturbacion else repr(float(f.valor_perturbacion))
            self.assertEqual(f.celda, "|".join((f.bloque, f.reloj_verdadero, f.tipo, f.escenario, f.perturbacion,
                                                valor)))
        self.assertEqual(t["semilla"].nunique(), len(t))
        # Celdas de referencia: 4 relojes × tipos a y b.
        ref = t[B._en(t, B.CELDAS_REFERENCIA)]
        self.assertEqual(sorted(ref["celda"].unique()), sorted(REFERENCIA))
        reducida = B.tabla_bateria(constantes.valor("BATERIA_REPLICAS_REDUCIDAS"))
        self.assertEqual(reducida.groupby("bloque").size().to_dict(), {"D1": 4740, "D2": 1260, "D3": 30})
        self.assertEqual(B.celdas(reducida), celdas)
        with self.assertRaises(ValueError):
            B.tabla_bateria(4)

    def test_d_redes_por_sesgo_y_replica(self):
        """50 redes (sesgo × réplica); calibración y A3 a A5 dentro de cada red: correr_bateria entrega a
        correr_red una red por llamada, en orden, y cada estación una sola vez."""
        t = _tabla()
        lista = list(B.redes(t))
        self.assertEqual(len(lista), 50)
        nombres = [r for r, _ in lista]
        self.assertEqual(nombres[:20], [f"s+0.0_r{i:02d}" for i in range(1, 21)])
        self.assertEqual(len(set(nombres)), 50)
        tamanos = sorted(len(f) for _, f in lista)
        self.assertEqual(tamanos, [12] * 30 + [237] * 10 + [459] * 10)
        for red, filas in lista:
            m = re.fullmatch(r"s([+-]\d\.\d)_r(\d{2})", red)
            self.assertIsNotNone(m, red)
            self.assertEqual(set(filas["replica"]), {int(m.group(2))})
            sesgo = float(m.group(1))
            if sesgo:
                self.assertEqual(set(filas["perturbacion"]), {"sesgo_termico_referencia"})
                self.assertEqual(set(filas["valor_perturbacion"]), {sesgo})
            else:
                self.assertNotIn("sesgo_termico_referencia", set(filas["perturbacion"]))
        d3 = t[t["bloque"] == "D3"]
        self.assertEqual(set(d3["red"]), {f"s+0.0_r{i:02d}" for i in range(1, 11)})
        # Una red grande arma sus píxeles y su referencia sin choques entre sitios (sin fabricar series).
        filas = dict(lista)["s+0.0_r01"]
        casos = [sintetico.caso_de_fila(f) for f in filas.to_dict("records")]
        pixeles = sintetico.catalogo_pixeles_sintetico(casos)
        self.assertGreater(len(pixeles), 0)
        sintetico.serie_era5_de_casos(casos)
        # correr_bateria: una red por llamada, en el orden de la tabla.
        vistas = []

        def falso(filas, U, *, contexto=None):
            vistas.append((filas["red"].iloc[0], len(filas)))
            return B.tabla_vacia(B.ESQUEMA_RESULTADOS)
        avance = []
        resultados, horas = B.correr_bateria(t, None, correr=falso, avance=lambda h, n: avance.append((h, n)))
        self.assertEqual([v for v, _ in vistas], nombres)
        self.assertEqual(sum(n for _, n in vistas), len(t))
        self.assertEqual(avance[-1], (len(t), len(t)))
        self.assertEqual(len(resultados), 0)
        self.assertGreaterEqual(horas, 0)

    def test_d_cero_confirmaciones_erroneas(self):
        """Distinto en alguna etiqueta, fuera de P o tipo (g)."""
        f0 = _fila_de("D1|F(0)|a|completo|ninguna|")
        g = _fila_de("D1|Ts:C(America/Santiago)|QFE:F(0)|g|completo|ninguna|")
        civil = _fila_de("D1|C(America/Santiago)|a|completo|ninguna|")
        casos = [
            (_resultado(f0, 2019, "confirmado", "F(0)", "F(0)"), False),
            (_resultado(f0, 2019, "confirmado", "F(-3)", "F(0)"), True),
            (_resultado(f0, 2019, "insuficiente", None, "F(0)"), False),
            (_resultado(f0, 2019, "sin_confirmar", None, "F(0)", clase_paso_9="F(-3)"), False),
            (_resultado(f0, 2018, "confirmado", "F(0)", ""), True),            # fuera de P ese año
            (_resultado(g, 2019, "confirmado", "C(Santiago)", ""), True),
            (_resultado(g, 2019, "confirmado", "F(0)", "F(0)"), True),         # en (g), toda confirmación
            (_resultado(civil, 2015, "confirmado", "F(-3)|C(Santiago)", "F(-3)|C(Santiago)"), False),
            (_resultado(civil, 2015, "confirmado", "F(-3)|C(Santiago)", "C(Santiago)"), True),   # BAT-2 estricta
        ]
        for fila, esperado in casos:
            with self.subTest(fila=(fila["caso"], fila["anio"], fila["clase_confirmada"], fila["verdad"])):
                self.assertEqual(B.es_confirmacion_erronea(pd.Series(fila)), esperado)
        U = _U()
        filas = _referencia_correcta()
        f1 = _fila_de("D1|F(+1)|a|completo|ninguna|")
        filas.append(_resultado(f1, 2019, "confirmado", "F(0)", "", lineas_apoyo="E3p|E4p"))
        res = _marco(filas)
        validar_esquema(res, B.ESQUEMA_RESULTADOS, nombre="prueba")
        c = B.criterios_por_celda(res, _tabla(), U)
        self.assertEqual(c.erroneas, 1)
        self.assertFalse(c.pasa)
        self.assertEqual(c.criterios["cero_erroneas"]["celdas"], [f1["celda"]])
        self.assertTrue(any("1 confirmaciones erróneas" in m for m in c.motivos))
        fila = c.por_celda.set_index("celda").loc[f1["celda"]]
        self.assertEqual((fila["erroneas"], fila["confirmados"], fila["n_estaciones"]), (1, 1, 1))
        self.assertEqual(B.lineas_responsables(res), {"E3p", "E4p"})
        # Sin la errónea, todos los criterios se cumplen.
        ok = B.criterios_por_celda(_marco(_referencia_correcta()), _tabla(), U)
        self.assertTrue(ok.pasa, ok.motivos)
        self.assertEqual(ok.motivos, [])

    def test_d_semanticas_de_media_hora(self):
        """Correcta sólo con la marca; ≥ 90 % de las confirmaciones de ±0,5 h; la de −10 min no cuenta."""
        U = _U()
        mas = "D2|F(0)|a|completo|semantica|0.5"
        menos = "D2|F(0)|b|completo|semantica|-0.5"
        diez = f"D2|F(0)|a|completo|semantica|{1 / 6!r}"

        def corrida(con_marca_mas: int, con_marca_menos: int):
            filas = _referencia_correcta()
            for celda, n_marca in ((mas, con_marca_mas), (menos, con_marca_menos)):
                for replica in range(1, 6):          # 5 estaciones × 1 año confirmado con el reloj entero
                    filas.append(_resultado(_fila_de(celda, replica), 2019, "confirmado", "F(0)", "F(0)",
                                            media_horaria=replica <= n_marca))
            for replica in range(1, 6):
                filas.append(_resultado(_fila_de(diez, replica), 2019, "confirmado", "F(0)", "F(0)"))
            return B.criterios_por_celda(_marco(filas), _tabla(), U)
        c = corrida(5, 4)                              # 9 de 10
        self.assertEqual(c.criterios["semanticas_media_hora"]["confirmaciones"], 10)
        self.assertTrue(c.criterios["semanticas_media_hora"]["pasa"])
        self.assertTrue(c.pasa, c.motivos)
        c = corrida(4, 4)                              # 8 de 10
        self.assertFalse(c.criterios["semanticas_media_hora"]["pasa"])
        self.assertFalse(c.pasa)
        self.assertEqual(c.erroneas, 0)               # sin la marca no es errónea (BAT-6)
        vacio = B.criterios_por_celda(_marco(_referencia_correcta()), _tabla(), U)
        self.assertEqual(vacio.criterios["semanticas_media_hora"]["confirmaciones"], 0)
        self.assertTrue(vacio.criterios["semanticas_media_hora"]["pasa"])

    def test_d_correcta_exige_la_marca_en_media_hora(self):
        """§8.D: en ±0,5 h, la confirmación del reloj entero sólo es correcta con la marca, también en la
        columna «correcta» y en la sensibilidad por celda (BAT-6); sin la marca no es errónea."""
        U = _U()
        mas = "D2|F(0)|a|completo|semantica|0.5"
        f = _fila_de(mas)
        sin = pd.Series(_resultado(f, 2019, "confirmado", "F(0)", "F(0)", media_horaria=False))
        con = pd.Series(_resultado(f, 2019, "confirmado", "F(0)", "F(0)", media_horaria=True))
        self.assertFalse(B.es_confirmacion_correcta(sin))
        self.assertTrue(B.es_confirmacion_correcta(con))
        self.assertFalse(B.es_confirmacion_erronea(sin))
        diez = _fila_de(f"D2|F(0)|a|completo|semantica|{1 / 6!r}")          # −10 min: no exige la marca
        self.assertTrue(B.es_confirmacion_correcta(pd.Series(_resultado(diez, 2019, "confirmado", "F(0)", "F(0)"))))
        filas = _referencia_correcta() + [_resultado(_fila_de(mas, k), 2019, "confirmado", "F(0)", "F(0)",
                                                     media_horaria=k <= 2) for k in range(1, 6)]
        c = B.criterios_por_celda(_marco(filas), _tabla(), U)
        fila = c.por_celda.set_index("celda").loc[mas]
        self.assertEqual((int(fila["correctos"]), int(fila["media_hora_confirmadas"]),
                          int(fila["media_hora_con_marca"])), (2, 5, 2))
        self.assertAlmostEqual(fila["sensibilidad"], 2 / 5)
        self.assertEqual(c.erroneas, 0)
        # Una columna «correcta» que no sigue la regla se rechaza en vez de contarse.
        malas = _marco(filas)
        malas.loc[malas["celda"] == mas, "correcta"] = True
        with self.assertRaises(ValueError):
            B.criterios_por_celda(malas, _tabla(), U)

    def test_d_sensibilidad_por_reloj(self):
        """≥ 0,80 y civil ≥ 0,8 × F(0) en las celdas de referencia; confirmación correcta ≥ 90 %."""
        U = _U()
        ok = B.criterios_por_celda(_marco(_referencia_correcta()), _tabla(), U)
        self.assertEqual(set(ok.sensibilidad), {"F(0)", "F(-3)", "F(-4)", "C(Santiago)", "razon_civil"})
        self.assertEqual(ok.sensibilidad["F(0)"], {"n": 38, "correctos": 38, "sensibilidad": 1.0})
        self.assertEqual(ok.sensibilidad["razon_civil"], 1.0)
        self.assertEqual(ok.criterios["confirmacion_correcta"]["n"], 8 * 19)
        # F(−4) con 8 de 38 años insuficientes: 30/38 < 0,80.
        bajo = {"D1|F(-4)|a|completo|ninguna|": 8}
        c = B.criterios_por_celda(_marco(_referencia_correcta(bajo)), _tabla(), U)
        self.assertAlmostEqual(c.sensibilidad["F(-4)"]["sensibilidad"], 30 / 38)
        self.assertEqual(c.criterios["sensibilidad_por_reloj"]["relojes"], ["F(-4)"])
        self.assertTrue(c.criterios["razon_civil"]["pasa"])
        self.assertFalse(c.pasa)
        # C(Santiago) con 7 de 38 años insuficientes: 31/38 ≥ 0,80, pero 31/38 < 0,8 × 1,0 no; con F(0)
        # perfecta la razón es 0,816 ≥ 0,8. Con 8 años: 0,789 < 0,80 y la razón también falla.
        civil = {"D1|C(America/Santiago)|a|completo|ninguna|": 8}
        c = B.criterios_por_celda(_marco(_referencia_correcta(civil)), _tabla(), U)
        self.assertFalse(c.criterios["razon_civil"]["pasa"])
        self.assertEqual(c.criterios["sensibilidad_por_reloj"]["relojes"], ["C(Santiago)"])
        # Confirmación correcta: 152 estación-años de referencia; con 16 insuficientes, 136/152 < 0,90.
        muchos = {celda: 2 for celda in REFERENCIA}
        c = B.criterios_por_celda(_marco(_referencia_correcta(muchos)), _tabla(), U)
        self.assertTrue(c.criterios["sensibilidad_por_reloj"]["pasa"])
        self.assertAlmostEqual(c.criterios["confirmacion_correcta"]["fraccion"], 136 / 152)
        self.assertFalse(c.criterios["confirmacion_correcta"]["pasa"])
        # Un sesgo de +1 h entra al denominador; uno de +2,5 h no.
        filas = _referencia_correcta()
        filas.append(_resultado(_fila_de("D2|F(0)|a|completo|sesgo_termico_referencia|1.0"), 2019,
                                "insuficiente", verdad="F(0)"))
        filas.append(_resultado(_fila_de("D2|F(0)|a|completo|sesgo_termico_referencia|2.5"), 2019,
                                "insuficiente", verdad="F(0)"))
        c = B.criterios_por_celda(_marco(filas), _tabla(), U)
        self.assertEqual(c.criterios["confirmacion_correcta"]["n"], 8 * 19 + 1)
        # Sin estación-años de referencia, la sensibilidad no es evaluable y C1 no aprueba.
        f0 = _fila_de("D1|F(0)|c|completo|ninguna|")
        c = B.criterios_por_celda(_marco([_resultado(f0, 2019, "confirmado", "F(0)", "F(0)")]), _tabla(), U)
        self.assertFalse(c.pasa)
        self.assertIsNone(c.sensibilidad["F(0)"]["sensibilidad"])

    def test_d_confirmacion_correcta_estrecha_a_50_S(self):
        """BAT-5 con la Enmienda 3 (decisión del autor, tomada viendo la batería sintética): decide la lectura
        estrecha a ≤ 50° S (tipos a y b, sin otra perturbación que el sesgo de la referencia con |sesgo| ≤ 1 h,
        completo o 30 % faltante, |lat| ≤ 50°: 52 celdas), por estación-año. Se informan al lado la literal
        (195 celdas) y la estrecha sin acotar la latitud (56 celdas: las 4 de C(Punta_Arenas) a 53° S de más)."""
        U = _U()
        t = _tabla().drop_duplicates("celda").copy()
        t["verdad"] = "x"                              # sólo la máscara de celdas; los años fuera de P van aparte
        literal, estrecha = B._celdas_correcta(t), B._celdas_correcta_estrecha(t)
        decide = B._celdas_correcta_estrecha_50(t)
        self.assertEqual((int(literal.sum()), int(estrecha.sum()), int(decide.sum())), (195, 56, 52))
        self.assertEqual(t[literal].groupby("bloque").size().to_dict(), {"D1": 48, "D2": 144, "D3": 3})
        self.assertEqual(t[decide].groupby("bloque").size().to_dict(), {"D1": 44, "D2": 8})
        self.assertFalse((estrecha & ~literal).any())
        self.assertFalse((decide & ~estrecha).any())
        self.assertEqual(set(t.loc[estrecha & ~decide, "reloj_verdadero"]), {"C(America/Punta_Arenas)"})
        self.assertTrue((t.loc[decide, "lat"].abs() <= B._CONSTANTES["BATERIA_CORRECTA_LAT_S"]).all())
        # Entran el desfase térmico y D3 tipo b a la literal; no entran el sesgo de −2 h, Juan Fernández,
        # ralo2008 ni el tipo e. A la que decide sólo entran el núcleo y el sesgo de ≤ 1 h, a ≤ 50° S.
        entra = {"D2|F(0)|a|completo|desfase_termico_estacion|-2.5": (True, False),
                 "D3|F(-4)|b|completo|isd_sintetico|": (True, False),
                 "D2|F(0)|a|completo|sesgo_termico_referencia|1.0": (True, True),
                 "D1|C(America/Punta_Arenas)|a|completo|ninguna|": (True, False),
                 "D1|C(America/Coyhaique)|b|faltante30|ninguna|": (True, True),
                 "D2|F(0)|b|completo|sesgo_termico_referencia|-2.0": (False, False),
                 "D2|F(-4)|b|completo|juan_fernandez|": (False, False),
                 "D1|F(0)|a|ralo2008|ninguna|": (False, False), "D2|F(0)|e|completo|semantica|0.5": (False, False)}
        for celda, (en_literal, en_decide) in entra.items():
            f = pd.DataFrame([{**_fila_de(celda), "verdad": "x"}])
            self.assertEqual((bool(B._celdas_correcta(f).iloc[0]), bool(B._celdas_correcta_estrecha_50(f).iloc[0])),
                             (en_literal, en_decide), celda)
        # Las referencias y dos años más: el de la literal no cuenta en la que decide; el del sesgo de 1 h, sí.
        filas = _referencia_correcta()
        for celda in ("D2|F(0)|a|completo|desfase_termico_estacion|-2.5", "D2|F(0)|a|completo|sesgo_termico_referencia|1.0"):
            f = _fila_de(celda)
            filas.append(_resultado(f, 2019, "insuficiente", verdad=VERDAD[f["reloj_verdadero"]]))
        c = B.criterios_por_celda(_marco(filas), _tabla(), U)
        cc = c.criterios["confirmacion_correcta"]
        self.assertEqual((cc["n"], cc["casos"], cc["unidad"], cc["lectura"]), (8 * 19 + 1, 8 + 1, "estacion_anios",
                                                                           "estrecha_50S"))
        self.assertEqual((cc["lectura_literal"]["n"], cc["lectura_literal"]["casos"]), (8 * 19 + 2, 8 + 2))
        self.assertEqual((cc["lectura_estrecha"]["n"], cc["lectura_estrecha"]["casos"]), (8 * 19 + 1, 8 + 1))
        self.assertAlmostEqual(cc["fraccion"], 152 / 153)
        self.assertTrue(cc["pasa"])
        # Con 19 años F(0) del desfase térmico de −2,5 h discrepantes, la literal falla y la que decide no.
        f = _fila_de("D2|F(0)|a|completo|desfase_termico_estacion|-2.5")
        filas = _referencia_correcta() + [_resultado(f, anio, "discrepante", verdad="F(0)") for anio in ANIOS]
        c = B.criterios_por_celda(_marco(filas), _tabla(), U)
        cc = c.criterios["confirmacion_correcta"]
        self.assertAlmostEqual(cc["lectura_literal"]["fraccion"], 152 / 171)
        self.assertFalse(cc["lectura_literal"]["pasa"])
        self.assertTrue(cc["pasa"])
        self.assertTrue(c.pasa, c.motivos)
        # C(Punta_Arenas) insuficiente en sus 19 años (sin regla fina a 53° S): falla la estrecha sin acotar
        # (152/171 < 0,90), no la que decide.
        f = _fila_de("D1|C(America/Punta_Arenas)|a|completo|ninguna|")
        filas = _referencia_correcta() + [_resultado(f, anio, "insuficiente", verdad="C(Punta_Arenas)") for anio in ANIOS]
        c = B.criterios_por_celda(_marco(filas), _tabla(), U)
        cc = c.criterios["confirmacion_correcta"]
        self.assertFalse(cc["lectura_estrecha"]["pasa"])
        self.assertEqual((cc["n"], cc["fraccion"]), (8 * 19, 1.0))
        self.assertTrue(cc["pasa"])
        # La que decide también puede fallar: 16 de los 152 años de referencia insuficientes (136/152 < 0,90).
        c = B.criterios_por_celda(_marco(_referencia_correcta({celda: 2 for celda in REFERENCIA})), _tabla(), U)
        self.assertFalse(c.criterios["confirmacion_correcta"]["pasa"])
        self.assertFalse(c.pasa)

    def test_d_confirmacion_correcta_lee_la_latitud_de_8D(self):
        """BAT-5 (E3-6): el límite «a ≤ 50° S» es el de la frase de §8.D (BATERIA_CORRECTA_LAT_S, verificada
        contra el v1.0.3), no el de la regla fina (FINA_LAT_MAX, §4.3.4). Si sólo cambia el de §8.D, cambian
        las celdas que deciden (salen las de 45,6° S y 49,5° S con 45°); si sólo cambia el de §4.3.4, no."""
        t = _tabla().drop_duplicates("celda").copy()
        t["verdad"] = "x"
        estrecha, decide = B._celdas_correcta_estrecha(t), B._celdas_correcta_estrecha_50(t)
        lat_8d = B._CONSTANTES["BATERIA_CORRECTA_LAT_S"]
        self.assertTrue(decide.equals(estrecha & (t["lat"].abs() <= lat_8d)))
        a_45 = estrecha & (t["lat"].abs() <= 45)
        self.assertLess(int(a_45.sum()), int(decide.sum()))
        with mock.patch.dict(B._CONSTANTES, {"BATERIA_CORRECTA_LAT_S": 45}):
            self.assertTrue(B._celdas_correcta_estrecha_50(t).equals(a_45))
        fina = constantes.POR_NOMBRE["FINA_LAT_MAX"]
        with mock.patch.dict(constantes.POR_NOMBRE, {"FINA_LAT_MAX": dataclasses.replace(fina, valor=45)}):
            self.assertTrue(B._celdas_correcta_estrecha_50(t).equals(decide))

    def test_d_sin_cruces_y_cambio_2018_ubicado(self):
        """Fijo/civil nunca cruzados; el cambio de 2018 en 2018; el tipo e, Pascua y Juan Fernández sin
        confirmar (el tipo f, en test_d_tipo_f_puede_confirmarse); la ida y vuelta debe pasar en cada estación."""
        U = _U()
        cambio = CAMBIO_2018
        self.assertEqual(B._anio_de_cambio(_fila_de(cambio)["reloj_verdadero"]), 2018)

        def con_cambio(anio_2018: str, cambios: str):
            filas = _referencia_correcta()
            f = _fila_de(cambio)
            for anio in ANIOS:
                verdad = "" if anio == 2018 else ("F(-4)" if anio < 2018 else "F(0)")
                if anio == 2018:
                    filas.append(_resultado(f, anio, anio_2018, "F(0)", verdad, cambios=cambios))
                else:
                    filas.append(_resultado(f, anio, "confirmado", verdad, verdad, cambios=cambios))
            return B.criterios_por_celda(_marco(filas), _tabla(), U)
        c = con_cambio("discrepante", "2017-2019")
        self.assertTrue(c.criterios["cambio_ubicado"]["pasa"], c.motivos)
        self.assertEqual(c.criterios["cambio_ubicado"]["estaciones"], 1)
        self.assertTrue(c.pasa, c.motivos)
        c = con_cambio("confirmado", "2018-2019")
        self.assertFalse(c.criterios["cambio_ubicado"]["pasa"])
        self.assertEqual(c.erroneas, 1)
        # Un cambio detectado que no deja 2018 entre las rachas también está mal ubicado.
        self.assertFalse(B._cambio_ubicado(_marco([_resultado(_fila_de(cambio), 2016, "confirmado", "F(-4)", "F(-4)",
                                                              cambios="2016-2017")]), 2018))
        # Cruce: un civil confirmado como fijo (y es errónea); una clase fusionada que contiene al civil no.
        civil = _fila_de("D1|C(America/Santiago)|b|completo|ninguna|", 2)
        filas = _referencia_correcta()
        filas.append(_resultado(civil, 2019, "confirmado", "F(-4)", "C(Santiago)", cruce=True))
        c = B.criterios_por_celda(_marco(filas), _tabla(), U)
        self.assertFalse(c.criterios["sin_cruces"]["pasa"])
        self.assertTrue(B._cruza("F(-4)", frozenset({"C"})))
        self.assertFalse(B._cruza("F(-3)|C(Santiago)", frozenset({"C"})))
        self.assertTrue(B._cruza("C(Santiago)", frozenset({"F"})))
        self.assertFalse(B._cruza("C(Santiago)", frozenset({"F", "C"})))
        # Lo indecidible: una confirmación correcta en el tipo e, en Pascua o en Juan Fernández falla el
        # criterio (BAT-7); en D3 (con E6) no.
        for celda, estrecho in (("D1|F(0)|e|completo|ninguna|", 1), ("D1|C(Pacific/Easter)|a|completo|ninguna|", 0),
                                ("D2|F(-4)|b|completo|juan_fernandez|", 0), ("D1|F0-Pascua|b|completo|ninguna|", 1)):
            f = _fila_de(celda)
            verdad = sintetico._id_tipos("F(0)" if f["reloj_verdadero"] == sintetico.PASCUA_PROPIO
                                         else f["reloj_verdadero"])
            filas = _referencia_correcta() + [_resultado(f, 2019, "confirmado", verdad, verdad)]
            c = B.criterios_por_celda(_marco(filas), _tabla(), U)
            with self.subTest(celda=celda):
                self.assertFalse(c.criterios["indecidible_sin_confirmar"]["pasa"])
                self.assertEqual(c.criterios["indecidible_sin_confirmar"]["indecidible_estrecho"], estrecho)
                self.assertEqual(c.erroneas, 0)
        d3 = _fila_de("D3|F(0)|e|completo|isd_sintetico|")
        c = B.criterios_por_celda(_marco(_referencia_correcta() + [_resultado(d3, 2019, "confirmado", "F(0)", "F(0)")]),
                                  _tabla(), U)
        self.assertTrue(c.criterios["indecidible_sin_confirmar"]["pasa"])
        # Ida y vuelta: una estación que falla o una red sin política (A5) no aprueban.
        for estado in ("falla", "sin_politica"):
            filas = _referencia_correcta()
            filas[0]["ida_y_vuelta"] = estado
            c = B.criterios_por_celda(_marco(filas), _tabla(), U)
            self.assertFalse(c.criterios["ida_y_vuelta"]["pasa"], estado)
        # Pérdidas por celda: años falsamente discrepantes y estaciones inestables.
        filas = _referencia_correcta()
        f = _fila_de("D1|F(0)|a|faltante30|ninguna|")
        filas += [_resultado(f, anio, "discrepante", verdad="F(0)", inestable=True) for anio in ANIOS]
        c = B.criterios_por_celda(_marco(filas), _tabla(), U)
        fila = c.por_celda.set_index("celda").loc[f["celda"]]
        self.assertEqual((fila["tasa_falsamente_discrepantes"], fila["perdida_inestabilidad"]), (1.0, 1.0))
        self.assertEqual(c.erroneas, 0)

    def test_d_tipo_f_puede_confirmarse(self):
        """BAT-7 con la Enmienda 4 (E4-1, v1.0.4): el tipo f sale de lo indecidible. Una confirmación correcta del
        tipo f no hace fallar el criterio (con el v1.0.3 sí: así falló la primera corrida de la batería completa,
        con 8 estación-años de C(Coyhaique) × f); una errónea sí cuenta, en «cero erróneas» (BAT-2); y el criterio
        informa las del tipo f aparte. El tipo e sigue en la lista, y el diagnóstico estrecho ya no mira el f."""
        U = _U()
        self.assertEqual(B.TIPOS_INDECIDIBLES, ("e",))
        coy = _fila_de("D1|C(America/Coyhaique)|f|completo|ninguna|")
        clase = "C(Santiago)|C(Coyhaique)"
        filas = _referencia_correcta() + [_resultado(coy, anio, "confirmado", clase, clase,
                                                     lineas_apoyo="E1c|E2|E3p") for anio in (2011, 2015, 2018)]
        c = B.criterios_por_celda(_marco(filas), _tabla(), U)
        ind = c.criterios["indecidible_sin_confirmar"]
        self.assertTrue(ind["pasa"], c.motivos)
        self.assertEqual((ind["confirmados"], ind["celdas"], ind["tipos"]), (0, [], ["e"]))
        self.assertEqual({k: ind["tipo_f"][k] for k in ("confirmados", "correctos", "erroneas")}, {
            "confirmados": 3, "correctos": 3, "erroneas": 0})
        self.assertEqual(ind["tipo_f"]["celdas_con_confirmados"], [coy["celda"]])
        self.assertEqual(c.erroneas, 0)
        self.assertTrue(c.pasa, c.motivos)
        # Con la lista del v1.0.3 («tipos e y f») el mismo resultado falla, como en la corrida de anoche.
        with mock.patch.object(B, "TIPOS_INDECIDIBLES", ("e", "f")):
            c3 = B.criterios_por_celda(_marco(filas), _tabla(), U)
        self.assertFalse(c3.criterios["indecidible_sin_confirmar"]["pasa"])
        self.assertEqual(c3.criterios["indecidible_sin_confirmar"]["confirmados"], 3)
        # Una confirmación errónea del tipo f: el criterio de lo indecidible pasa y «cero erróneas» falla.
        f0 = _fila_de("D1|F(0)|f|completo|ninguna|")
        filas = _referencia_correcta() + [_resultado(f0, 2019, "confirmado", "F(-3)", "F(0)")]
        c = B.criterios_por_celda(_marco(filas), _tabla(), U)
        self.assertTrue(c.criterios["indecidible_sin_confirmar"]["pasa"])
        self.assertEqual(c.criterios["indecidible_sin_confirmar"]["tipo_f"]["erroneas"], 1)
        self.assertEqual(c.erroneas, 1)
        self.assertFalse(c.criterios["cero_erroneas"]["pasa"])
        self.assertIn(f0["celda"], c.criterios["cero_erroneas"]["celdas"])
        self.assertFalse(c.pasa)
        # El tipo e sigue indecidible; F(0) del tipo f ya no entra al diagnóstico estrecho.
        for celda, pasa, estrecho in (("D1|F(0)|e|completo|ninguna|", False, 1),
                                      ("D1|F(0)|f|completo|ninguna|", True, 0)):
            fila = _fila_de(celda)
            c = B.criterios_por_celda(_marco(_referencia_correcta() + [_resultado(fila, 2019, "confirmado", "F(0)",
                                                                                  "F(0)")]), _tabla(), U)
            with self.subTest(celda=celda):
                self.assertEqual(c.criterios["indecidible_sin_confirmar"]["pasa"], pasa)
                self.assertEqual(c.criterios["indecidible_sin_confirmar"]["indecidible_estrecho"], estrecho)

    def test_d_lo_indecidible_es_la_frase_de_8D(self):
        """BAT-7: FRAGMENTO_INDECIDIBLE está una vez en §8.D del texto vigente (desde el v1.0.4) y nombra sólo los tipos de
        TIPOS_INDECIDIBLES; los textos anteriores (C0 a v1.0.3) traen la frase «tipos e y f», sin el fragmento.
        Si una enmienda vuelve a cambiar la frase, la prueba falla y obliga a revisar la lista."""
        textos = _textos_del_protocolo()
        self.assertGreaterEqual(constantes.indice_version(constantes.VERSION_VIGENTE),
                                constantes.indice_version("v1.0.4"))
        anterior = "lo indecidible (tipos e y f, Pascua y Juan Fernández) queda sin confirmar."
        for version, texto in textos.items():
            d8 = constantes.tramo_de_seccion(texto, "§8.D")
            nuevo = constantes.indice_version(version) >= constantes.indice_version("v1.0.4")
            with self.subTest(version=version):
                self.assertIsNotNone(d8)
                self.assertEqual(d8.count(B.FRAGMENTO_INDECIDIBLE), int(nuevo))
                self.assertEqual(texto.count(B.FRAGMENTO_INDECIDIBLE), int(nuevo))
                self.assertEqual(d8.count(anterior), int(not nuevo))
        tipos = re.match(r"lo indecidible \(tipos? ([a-g](?:(?:, | y )[a-g])*), Pascua", B.FRAGMENTO_INDECIDIBLE)
        self.assertIsNotNone(tipos)
        self.assertEqual(tuple(re.split(r", | y ", tipos.group(1))), B.TIPOS_INDECIDIBLES)
        self.assertIn(f"el tipo {B.TIPO_SEIS_HORAS} puede confirmarse", B.FRAGMENTO_INDECIDIBLE)
        self.assertNotIn(B.TIPO_SEIS_HORAS, B.TIPOS_INDECIDIBLES)

    def test_d_cambio_2018_sin_error_de_ubicacion(self):
        """BAT-8 «sin error de ubicación» (decisión del autor; afloja la lectura estricta anterior): 2018 sin
        confirmar, ningún año erróneo, y cada cambio detectado contiene 2018 sin años confirmados dentro. La
        estricta (2018, el único año con datos entre las rachas) se informa al lado. Sin cambio detectado no hay
        error de ubicación, pero la estación se cuenta y se nombra."""
        U = _U()
        f = _fila_de(CAMBIO_2018)

        def estacion(veredictos: dict, cambios: str) -> pd.DataFrame:
            filas = []
            for anio in ANIOS:
                verdad = "" if anio == 2018 else ("F(-4)" if anio < 2018 else "F(0)")
                v = veredictos.get(anio, "discrepante" if anio == 2018 else "confirmado")
                clase = verdad if v == "confirmado" else None
                filas.append(_resultado(f, anio, v, clase, verdad, cambios=cambios))
            return _marco(filas)
        self.assertTrue(B._cambio_ubicado(estacion({2019: "insuficiente"}, "2017-2020"), 2018))
        self.assertTrue(B._cambio_ubicado(estacion({2019: "discrepante"}, "2017-2020"), 2018))
        self.assertTrue(B._cambio_ubicado(estacion({2019: "sin_datos"}, "2017-2020"), 2018))
        self.assertTrue(B._cambio_ubicado(estacion({}, "2017-2019"), 2018))
        # 904340 de la réplica 1: 2015-2017 insuficientes y el cambio detectado entre 2014 y 2019.
        ancho = estacion({a: "insuficiente" for a in (2015, 2016, 2017)}, "2014-2019")
        self.assertTrue(B._cambio_ubicado(ancho, 2018))
        self.assertFalse(B._cambio_ubicado_estricto(ancho, 2018))
        # Errores de ubicación: un cambio que no contiene 2018, un año confirmado dentro, 2018 confirmado o
        # un año erróneo.
        self.assertFalse(B._cambio_ubicado(estacion({}, "2016-2017"), 2018))
        self.assertFalse(B._cambio_ubicado(estacion({2015: "insuficiente", 2017: "insuficiente"}, "2014-2019"), 2018))
        dos = estacion({2019: "insuficiente"}, "2017-2020;2010-2011")
        self.assertFalse(B._cambio_ubicado(dos, 2018))
        self.assertFalse(B._cambio_ubicado(estacion({2018: "insuficiente"}, "2017-2019")
                                           .assign(veredicto=lambda d: d["veredicto"].where(d["anio"] != 2018,
                                                                                            "confirmado")), 2018))
        malo = estacion({}, "2017-2019")
        malo.loc[malo["anio"] == 2016, "erronea"] = True
        self.assertFalse(B._cambio_ubicado(malo, 2018))
        # En el criterio: pasa con el cambio en (2017, 2020) y la estricta lo nombra aparte.
        res = pd.concat([_marco(_referencia_correcta()), estacion({2019: "insuficiente"}, "2017-2020")],
                        ignore_index=True)
        c = B.criterios_por_celda(res.astype(B.ESQUEMA_RESULTADOS), _tabla(), U)
        cu = c.criterios["cambio_ubicado"]
        self.assertTrue(cu["pasa"], c.motivos)
        self.assertEqual((cu["mal_ubicadas"], cu["mal_ubicadas_lectura_estricta"], cu["lectura"]),
                         ([], [f["caso"]], "sin_error_de_ubicacion"))
        res = pd.concat([_marco(_referencia_correcta()), estacion({}, "2016-2017")], ignore_index=True)
        c = B.criterios_por_celda(res.astype(B.ESQUEMA_RESULTADOS), _tabla(), U)
        self.assertFalse(c.criterios["cambio_ubicado"]["pasa"])
        self.assertEqual(c.criterios["cambio_ubicado"]["mal_ubicadas"], [f["caso"]])
        # F(0) nunca confirmado después de 2018: una sola racha, sin cambio detectado.
        filas = [_resultado(f, anio, "confirmado" if anio < 2018 else "insuficiente", "F(-4)" if anio < 2018 else None,
                            "" if anio == 2018 else ("F(-4)" if anio < 2018 else "F(0)")) for anio in ANIOS]
        c = B.criterios_por_celda(_marco(_referencia_correcta() + filas), _tabla(), U)
        cu = c.criterios["cambio_ubicado"]
        self.assertTrue(cu["pasa"])
        self.assertEqual((cu["sin_cambio_detectado"], cu["sin_cambio_detectado_casos"]), (1, [f["caso"]]))

    def test_d_medicion_de_tiempo_y_reduccion(self):
        """> 48 h → D2 y D3 a 5 réplicas; el núcleo nunca. Proyección proporcional a los estación-años."""
        U = _U()
        tope = U.f("BAT_HORAS_MAX")
        self.assertIsNone(B.replicas_por_tiempo(tope, U))
        self.assertEqual(B.replicas_por_tiempo(tope + 0.01, U), constantes.valor("BATERIA_REPLICAS_REDUCIDAS"))
        with self.assertRaises(ValueError):
            B.replicas_por_tiempo(float("nan"), U)
        t = _tabla()
        self.assertAlmostEqual(B.proyectar_horas(3600.0, 19, t), len(t))       # 1 h por estación-año medido
        reducida = B.tabla_bateria(B.replicas_por_tiempo(tope + 1, U))
        self.assertEqual(int((reducida["bloque"] == "D1").sum()), int((t["bloque"] == "D1").sum()))
        tiempos = {}
        _, horas = B.correr_bateria(t.head(3), U,
                                    correr=lambda f, U, contexto=None: B.tabla_vacia(B.ESQUEMA_RESULTADOS),
                                    tiempos=tiempos)
        self.assertEqual(set(tiempos), {"segundos", "segundos_cpu", "redes", "cpu_por_red", "detalle_por_red",
                                        "estaciones", "estacion_anios", "carga_1min_inicio", "carga_1min_fin",
                                        "rss_pico_mib"})
        self.assertAlmostEqual(horas, tiempos["segundos"] / 3600)
        self.assertGreaterEqual(tiempos["segundos_cpu"], 0)
        self.assertGreater(tiempos["rss_pico_mib"], 0)
        info = B.tiempo_bateria(horas, t, U, tiempos=tiempos)
        self.assertIsNone(info["reduce_d2_d3_a"])
        self.assertEqual(info["tope_horas"], tope)
        self.assertEqual(info["medida"], B.MEDIDA_TIEMPO)
        self.assertAlmostEqual(info["horas_cpu"], tiempos["segundos_cpu"] / 3600)
        self.assertEqual(info["replicas_d2_d3"], 10)
        json.dumps(info, allow_nan=False)
        self.assertEqual(B.tiempo_bateria(tope * 2, t, U, proyectadas=True)["reduce_d2_d3_a"], 5)
        # BAT-13: con la máquina cargada el reloj de pared puede pasar el tope y el tiempo de CPU no; queda a la
        # vista para el autor, que decide cuál es «cómputo».
        cargada = B.tiempo_bateria(tope + 1, t, U, tiempos={"segundos_cpu": (tope - 1) * 3600})
        self.assertEqual((cargada["reduce_d2_d3_a"], cargada["reduce_d2_d3_a_por_cpu"]), (5, None))
        self.assertTrue(cargada["reduccion_depende_de_la_medida"])
        self.assertFalse(info["reduccion_depende_de_la_medida"])
        self.assertEqual(B.tiempo_bateria(1.0, reducida, U)["replicas_d2_d3"], 5)


class PruebasRedPequena(unittest.TestCase):
    """Dos estaciones de la red s+0.0_r01 de punta a punta: F(0) automática y F(+1) (fuera de P)."""

    @classmethod
    def setUpClass(cls):
        U = _U()
        for ruta in (AP / fijados.RUTA_ADAPTADOR, AP / fijados.RUTA_COMUN_MODELO):
            if not ruta.is_file():
                raise unittest.SkipTest(f"falta el código fijado {ruta.name}; la prueba no se da por aprobada")
        t = _tabla()
        celdas = ["D1|F(0)|a|completo|ninguna|", "D1|F(+1)|a|completo|ninguna|"]
        cls.filas = t[(t["red"] == "s+0.0_r01") & t["celda"].isin(celdas)].reset_index(drop=True)
        cls.U = U
        cls.tiempos = {}
        cls.resultados = B.correr_red(cls.filas, U, contexto=B.contexto_bateria(AP), tiempos=cls.tiempos)

    def test_esquema_verdad_y_ida_y_vuelta(self):
        r = self.resultados
        validar_esquema(r, B.ESQUEMA_RESULTADOS, nombre="red pequeña")
        self.assertEqual(sorted(set(r["caso"])), sorted(self.filas["caso"]))
        self.assertEqual(len(r), 2 * 19)
        por = {c: g.set_index("anio") for c, g in r.groupby("caso")}
        f0, f1 = (por[c] for c in self.filas["caso"])
        self.assertEqual(set(f0["verdad"]), {"F(0)"})
        self.assertEqual(set(f1["verdad"]), {""})                  # F(+1) está fuera de P todos los años
        self.assertEqual(list(r["erronea"]), [B.es_confirmacion_erronea(f) for _, f in r.iterrows()])
        self.assertEqual(set(r["ida_y_vuelta"]), {"ok"})
        self.assertFalse(r["a5_alto"].any())
        self.assertEqual(r["correcta"].sum(), (f0["veredicto"] == "confirmado").sum())
        # Una confirmación de F(+1) sería errónea por estar fuera de P (§8.D).
        self.assertTrue(all(e == (v == "confirmado") for e, v in zip(f1["erronea"], f1["veredicto"])))
        c = B.criterios_por_celda(r, _tabla(), self.U)
        self.assertEqual(c.erroneas, int(r["erronea"].sum()))
        self.assertTrue(c.criterios["ida_y_vuelta"]["pasa"])
        self.assertEqual(c.sensibilidad["F(0)"]["n"], 19)
        json.dumps(B.criterios_a_json(c), allow_nan=False)
        self.assertEqual(set(self.tiempos), {"preparacion", "evaluar_red", "ida_y_vuelta", "total", "estaciones",
                                             "estacion_anios"})
        self.assertEqual((self.tiempos["estaciones"], self.tiempos["estacion_anios"]), (2, 2 * 19))

    def test_salidas_en_una_carpeta_temporal(self):
        c = B.criterios_por_celda(self.resultados, _tabla(), self.U)
        with tempfile.TemporaryDirectory() as carpeta:
            huellas = B.escribir_salidas(Path(carpeta) / B.CARPETA_C1, _tabla(), self.resultados, c,
                                         B.tiempo_bateria(0.1, _tabla(), self.U))
            self.assertEqual(set(huellas), {B.ARCHIVO_TABLA, B.ARCHIVO_RESULTADOS, B.ARCHIVO_CRITERIOS,
                                            B.ARCHIVO_TIEMPO})
            releidos = pd.read_parquet(Path(carpeta) / B.CARPETA_C1 / B.ARCHIVO_RESULTADOS)
            for nombre, sha in huellas.items():
                datos = (Path(carpeta) / B.CARPETA_C1 / nombre).read_bytes()
                self.assertEqual(sha, B.entorno.sha256_bytes(datos), nombre)
                if nombre == B.ARCHIVO_RESULTADOS:          # binario: se mira el contenido decodificado
                    datos = releidos.to_csv(index=False).encode("utf-8")
                self.assertNotIn(b"/Users/", datos)
                # §8.28: el único «@» admitido es la excepción nombrada EXCEPCION_8_28 (pendiente del autor).
                self.assertEqual(datos.count(b"@"), len(EXCEPCION_8_28.findall(datos)), nombre)
            self.assertEqual(len(releidos), len(self.resultados))
            self.assertEqual(huellas[B.ARCHIVO_TABLA], B.huella_tabla(_tabla()))


class PruebasAjuste(unittest.TestCase):
    """§8.F con una «batería» fabricada: ``correr(U)`` devuelve resultados según los pasos de U."""

    def _correr(self, erroneas_si):
        """erroneas_si(U) → lista de filas erróneas extra; las de referencia siempre son correctas."""
        llamadas = []

        def correr(U):
            llamadas.append(dict(U.pasos))
            return _marco(_referencia_correcta() + erroneas_si(U))
        return correr, llamadas

    def test_f_solo_hacia_lo_conservador(self):
        """Cada iteración mueve un paso por línea responsable; nunca hacia atrás."""
        U = _U()
        f1 = _fila_de("D1|F(+1)|a|completo|ninguna|")
        g = _fila_de("D1|Ts:C(America/Santiago)|QFE:F(0)|g|completo|ninguna|")

        def erroneas(U):
            filas = []
            if U.pasos["E3P_MU"] < 2:            # fuera de P: responsables las líneas de apoyo
                filas.append(_resultado(f1, 2019, "confirmado", "F(0)", "", lineas_apoyo="E3p|E4p"))
            if U.pasos["TP_VENTANA"] < 1:        # tipo g: T-P
                filas.append(_resultado(g, 2019, "confirmado", "F(0)", ""))
            return filas
        correr, llamadas = self._correr(erroneas)
        reg = B.ajustar_umbrales(U, correr, _tabla(), reloj=lambda: datetime(2026, 10, 24, 12, tzinfo=timezone.utc))
        self.assertFalse(reg.c1_falla, reg.motivo)
        self.assertEqual(len(reg.iteraciones), 3)
        self.assertEqual([i["fin"] for i in reg.iteraciones], [None, None, "aprobado"])
        primero = reg.iteraciones[0]
        # La de (g) suma sus líneas de apoyo a T-P (BAT-3 acumulativa): E3p y E4p responden de las dos.
        self.assertEqual(primero["lineas_responsables"], {"E3p": 2, "E4p": 2, "T-P": 1})
        self.assertEqual([(m["id"], m["de"], m["a"]) for m in primero["umbrales_movidos"]],
                         [("E3P_MU", 0.03, 0.05), ("E4P_COMPAT", 1.0, 0.75), ("TP_VENTANA", 0.75, 1.0)])
        self.assertEqual([(m["id"], m["de"], m["a"]) for m in reg.iteraciones[1]["umbrales_movidos"]],
                         [("E3P_MU", 0.05, 0.08), ("E4P_COMPAT", 0.75, 0.5)])
        self.assertEqual({i: p for i, p in reg.umbrales_finales.pasos.items() if p},
                         {"E3P_MU": 2, "E4P_COMPAT": 2, "TP_VENTANA": 1})
        for anterior, siguiente in zip(llamadas, llamadas[1:]):
            self.assertTrue(all(siguiente[i] >= anterior[i] for i in anterior))
        for m in (m for it in reg.iteraciones for m in it["umbrales_movidos"]):
            sentido = umbrales.SENTIDO_CONSERVADOR[m["id"]]
            self.assertGreater((m["a"] - m["de"]) * sentido, 0, m)
        self.assertEqual(reg.umbrales_finales.a("E3P_MU"), 0.08)
        self.assertEqual(reg.criterios.erroneas, 0)                     # la última corrida, para las salidas
        self.assertEqual(B.huella_resultados(reg.resultados), reg.iteraciones[-1]["salida_sha256"])

    def test_f_lista_agotada_o_sensibilidad_c1_falla(self):
        """Lista agotada, línea sin filas, errónea sin responsable o sensibilidad no cumplida → C1 falla."""
        U = _U()
        f0 = _fila_de("D1|F(0)|b|faltante30|ninguna|")
        # E1c tiene una sola fila (E1C_COMPLETO, un paso): la segunda vez está agotada.
        correr, llamadas = self._correr(lambda U: [_resultado(f0, 2019, "confirmado", "F(-3)", "F(0)",
                                                              excluyen_verdad="E1c")])
        reg = B.ajustar_umbrales(U, correr, _tabla())
        self.assertTrue(reg.c1_falla)
        self.assertIsNone(reg.umbrales_finales)
        self.assertEqual(len(reg.iteraciones), 2)
        self.assertEqual(reg.iteraciones[0]["umbrales_movidos"][0]["id"], "E1C_COMPLETO")
        self.assertIn("agotada", reg.motivo)
        self.assertEqual(reg.iteraciones[-1]["fin"], "c1_falla")
        # Una línea sin filas en el Anexo B (P7) está agotada desde el principio.
        correr, _ = self._correr(lambda U: [_resultado(f0, 2019, "confirmado", "F(-3)", "F(0)", excluyen_verdad="P7")])
        reg = B.ajustar_umbrales(U, correr, _tabla())
        self.assertTrue(reg.c1_falla)
        self.assertEqual(len(reg.iteraciones), 1)
        self.assertIn("P7", reg.motivo)
        # Una errónea sin línea responsable en la traza (BAT-3).
        correr, _ = self._correr(lambda U: [_resultado(f0, 2019, "confirmado", "F(0)|F(-3)", "F(0)")])
        reg = B.ajustar_umbrales(U, correr, _tabla())
        self.assertTrue(reg.c1_falla)
        self.assertIn("sin línea responsable", reg.motivo)
        # Con cero errores, una sensibilidad no cumplida hace fallar C1 sin mover nada.
        bajo = {"D1|F(-3)|b|completo|ninguna|": 10}
        reg = B.ajustar_umbrales(U, lambda U: _marco(_referencia_correcta(bajo)), _tabla())
        self.assertTrue(reg.c1_falla)
        self.assertEqual(len(reg.iteraciones), 1)
        self.assertEqual(reg.iteraciones[0]["umbrales_movidos"], [])
        self.assertIn("sensibilidad", reg.motivo)

    def test_f_registro_de_iteraciones(self):
        """Fecha, motivo, umbral y salida, en registro_8F.jsonl (reescrito de forma atómica)."""
        U = _U()
        f0 = _fila_de("D1|F(0)|b|completo|ninguna|", 3)
        erronea = _resultado(f0, 2019, "confirmado", "F(-3)", "F(0)", excluyen_verdad="E2|E3p")

        def correr(U):
            return _marco(_referencia_correcta() + ([erronea] if U.pasos["E2_KAPPA"] == 0 else []))
        fechas = iter([datetime(2026, 10, 24, 1, tzinfo=timezone.utc), datetime(2026, 10, 24, 2, tzinfo=timezone.utc)])
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / B.ARCHIVO_REGISTRO_8F
            reg = B.ajustar_umbrales(U, correr, _tabla(), ruta_registro=ruta, reloj=lambda: next(fechas))
            lineas = ruta.read_text(encoding="utf-8").splitlines()
        self.assertFalse(reg.c1_falla)
        self.assertEqual(len(lineas), 2)
        registros = [json.loads(x) for x in lineas]
        self.assertEqual(registros, json.loads(json.dumps(reg.iteraciones)))
        uno, dos = registros
        self.assertEqual(uno["fecha_utc"], "2026-10-24T01:00:00Z")
        self.assertEqual(uno["erroneas"], 1)
        self.assertEqual(uno["erroneas_por_celda"], {f0["celda"]: 1})
        self.assertEqual(uno["lineas_responsables"], {"E2": 1, "E3p": 1})
        self.assertEqual([m["id"] for m in uno["umbrales_movidos"]], ["E2_KAPPA", "E3P_MU"])
        self.assertIn("confirmaciones erróneas", uno["motivo"])
        self.assertEqual(uno["salida_sha256"], B.huella_resultados(correr(U)))
        self.assertEqual(uno["umbrales_sha256"], U.huella())
        self.assertEqual(dos["pasos"], {"E2_KAPPA": 1, "E3P_MU": 1})
        self.assertEqual((dos["fin"], dos["erroneas"]), ("aprobado", 0))
        self.assertNotEqual(dos["salida_sha256"], uno["salida_sha256"])
        self.assertTrue(all(isinstance(v, (int, float)) and math.isfinite(v)
                            for r in registros for m in r["umbrales_movidos"] for v in (m["de"], m["a"])))

    def test_f_responsables_acumulativos(self):
        """BAT-3: los tres puntos de §8.F se suman. En (g), T-P y, como el verdadero no está en P, las líneas de
        apoyo; fuera de P, las de apoyo; con la verdad en P, sólo las que la excluyeron."""
        g = _fila_de("D1|Ts:C(America/Santiago)|QFE:F(0)|g|completo|ninguna|")
        f1 = _fila_de("D1|F(+1)|a|completo|ninguna|")
        f0 = _fila_de("D1|F(0)|b|completo|ninguna|")
        casos = [(_resultado(g, 2019, "confirmado", "F(0)", "", lineas_apoyo="E3p|E4p|E2"),
                  {"E2", "E3p", "E4p", "T-P"}),
                 (_resultado(f1, 2019, "confirmado", "F(0)", "", lineas_apoyo="E3p|E4p"), {"E3p", "E4p"}),
                 (_resultado(f0, 2019, "confirmado", "F(-3)", "F(0)", lineas_apoyo="E3p", excluyen_verdad="E2"),
                  {"E2"})]
        for fila, esperado in casos:
            with self.subTest(caso=fila["celda"]):
                self.assertEqual(B.lineas_responsables(_marco([fila])), esperado)

    def test_f_primera_corrida_con_el_anexo_b(self):
        """§8.F: «Se corre la batería con los valores del Anexo B»; unos umbrales ya movidos se rechazan."""
        U = _U()
        llamadas = []

        def correr(Ux):
            llamadas.append(Ux)
            return _marco(_referencia_correcta())
        with self.assertRaises(ValueError):
            B.ajustar_umbrales(U.ajustado("E3P_MU"), correr, _tabla())
        self.assertEqual(llamadas, [])

    def test_f_la_salida_del_registro_es_un_archivo(self):
        """La «salida de la batería» de cada iteración es un parquet escrito junto al registro, con la sha256
        que guarda el registro; resultados_bateria.parquet es el de la última, y escribir_salidas devuelve
        también registro_8F.jsonl y los parquet de las iteraciones."""
        U = _U()
        f0 = _fila_de("D1|F(0)|b|completo|ninguna|", 3)
        erronea = _resultado(f0, 2019, "confirmado", "F(-3)", "F(0)", excluyen_verdad="E2")

        def correr(Ux):
            return _marco(_referencia_correcta() + ([erronea] if Ux.pasos["E2_KAPPA"] == 0 else []))
        tiempo = B.tiempo_bateria(0.1, _tabla(), U)
        with tempfile.TemporaryDirectory() as carpeta:
            c1 = Path(carpeta) / B.CARPETA_C1
            reg = B.ajustar_umbrales(U, correr, _tabla(), ruta_registro=c1 / B.ARCHIVO_REGISTRO_8F)
            self.assertEqual(len(reg.iteraciones), 2)
            archivos = [it["salida_archivo"] for it in reg.iteraciones]
            self.assertEqual(archivos, ["resultados_bateria_iter01.parquet", "resultados_bateria_iter02.parquet"])
            for it in reg.iteraciones:
                self.assertEqual(it["salida_sha256"], B.entorno.sha256_bytes((c1 / it["salida_archivo"]).read_bytes()))
            self.assertEqual(len(pd.read_parquet(c1 / archivos[0])), 8 * 19 + 1)
            registro = (c1 / B.ARCHIVO_REGISTRO_8F).read_bytes()
            self.assertEqual(reg.huellas, {B.ARCHIVO_REGISTRO_8F: B.entorno.sha256_bytes(registro),
                                           archivos[0]: reg.iteraciones[0]["salida_sha256"],
                                           archivos[1]: reg.iteraciones[1]["salida_sha256"]})
            huellas = B.escribir_salidas(c1, _tabla(), reg.resultados, reg.criterios, tiempo, registro=reg)
            self.assertEqual(huellas[B.ARCHIVO_RESULTADOS], reg.iteraciones[-1]["salida_sha256"])
            self.assertEqual(huellas[B.ARCHIVO_RESULTADOS],
                             B.entorno.sha256_bytes((c1 / B.ARCHIVO_RESULTADOS).read_bytes()))
            self.assertLessEqual(set(reg.huellas.items()), set(huellas.items()))
            # Otros resultados que no son los de la última iteración no se escriben con su registro.
            with self.assertRaises(ValueError):
                B.escribir_salidas(c1, _tabla(), correr(U), reg.criterios, tiempo, registro=reg)
            # Un parquet de iteración alterado tampoco.
            (c1 / archivos[0]).write_bytes(b"alterado")
            with self.assertRaises(ValueError):
                B.escribir_salidas(c1, _tabla(), reg.resultados, reg.criterios, tiempo, registro=reg)
        # Sin carpeta de registro, la huella es la del mismo parquet (huella_resultados).
        sin = B.ajustar_umbrales(U, correr, _tabla())
        self.assertEqual([it["salida_sha256"] for it in sin.iteraciones],
                         [it["salida_sha256"] for it in reg.iteraciones])
        self.assertEqual([it["salida_archivo"] for it in sin.iteraciones], [None, None])
        self.assertEqual(sin.huellas, {})
        self.assertEqual(B.huella_resultados(sin.resultados), sin.iteraciones[-1]["salida_sha256"])


class PruebasCaminoC1(unittest.TestCase):
    """bateria_c1: el camino único de --sintetico --bateria (con correr_bateria simulada)."""

    def _falsa(self, horas_por_llamada: list[float]):
        U0 = _U()
        f0 = _fila_de("D1|F(0)|b|completo|ninguna|", 3)
        erronea = _resultado(f0, 2019, "confirmado", "F(-3)", "F(0)", excluyen_verdad="E2")
        llamadas = []

        def correr_bateria(tabla, U, *, avance=None, contexto=None, tiempos=None, correr=None):
            llamadas.append({"estaciones": len(tabla), "pasos": {i: p for i, p in U.pasos.items() if p},
                             "medida": tiempos is not None})
            horas = horas_por_llamada[len(llamadas) - 1]
            if tiempos is not None:
                tiempos.update({"segundos": horas * 3600, "segundos_cpu": horas * 3600, "redes": {},
                                "cpu_por_red": {}, "detalle_por_red": {}, "estaciones": len(tabla),
                                "estacion_anios": 8 * 19, "carga_1min_inicio": None, "carga_1min_fin": None,
                                "rss_pico_mib": 1.0})
            return _marco(_referencia_correcta() + ([erronea] if U.pasos["E2_KAPPA"] == 0 else [])), horas
        return U0, correr_bateria, llamadas

    def test_mide_antes_de_8f_ajusta_y_escribe_todo(self):
        for horas, n_reducida in (([2.0, 2.0], None), ([49.0, 30.0, 30.0], 6030)):
            U, falsa, llamadas = self._falsa(horas)
            with self.subTest(horas=horas[0]), tempfile.TemporaryDirectory() as carpeta, \
                    mock.patch.object(B, "correr_bateria", falsa):
                c1 = Path(carpeta) / B.CARPETA_C1
                r = B.bateria_c1(c1, U, contexto=object(),
                                 reloj=lambda: datetime(2026, 10, 24, 12, tzinfo=timezone.utc))
                # La corrida medida es la primera de §8.F (no se repite); con la reducción, se mide otra vez.
                medidas = [ll for ll in llamadas if ll["medida"]]
                self.assertEqual([ll["pasos"] for ll in medidas], [{}] * len(medidas))
                self.assertEqual(len(llamadas), len(medidas) + 1)
                self.assertEqual(llamadas[-1]["pasos"], {"E2_KAPPA": 1})
                self.assertEqual(llamadas[-1]["estaciones"], n_reducida or 7320)
                self.assertTrue(r.pasa)
                self.assertFalse(r.registro.c1_falla)
                self.assertEqual(len(r.registro.iteraciones), 2)
                self.assertEqual(set(r.huellas), {B.ARCHIVO_TABLA, B.ARCHIVO_RESULTADOS, B.ARCHIVO_CRITERIOS,
                                                  B.ARCHIVO_TIEMPO, B.ARCHIVO_REGISTRO_8F,
                                                  "resultados_bateria_iter01.parquet",
                                                  "resultados_bateria_iter02.parquet"})
                for nombre, sha in r.huellas.items():
                    self.assertEqual(sha, B.entorno.sha256_bytes((c1 / nombre).read_bytes()), nombre)
                criterios = json.loads((c1 / B.ARCHIVO_CRITERIOS).read_bytes())
                self.assertIn("ida_y_vuelta", criterios["criterios"])
                self.assertTrue(criterios["pasa"])
                tiempo = json.loads((c1 / B.ARCHIVO_TIEMPO).read_bytes())
                self.assertEqual(tiempo["horas"], horas[len(medidas) - 1])
                self.assertEqual(tiempo["replicas_d2_d3"], 5 if n_reducida else 10)
                if n_reducida:
                    self.assertEqual(len(r.tabla), n_reducida)
                    self.assertEqual([p["horas"] for p in tiempo["mediciones_previas"]], [49.0])
                    self.assertEqual(tiempo["mediciones_previas"][0]["reduce_d2_d3_a"], 5)
                else:
                    self.assertEqual(tiempo["mediciones_previas"], [])
                self.assertEqual(r.huellas[B.ARCHIVO_TABLA], B.huella_tabla(r.tabla))


if __name__ == "__main__":
    unittest.main()
