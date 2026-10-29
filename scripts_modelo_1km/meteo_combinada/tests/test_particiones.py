"""Pruebas de particiones.py (§2.5, §4.9, §5.1, §5.3 y §5.4): grupos, P1, P2, internos, días y bloques.

Dueño: I3 (ola 1). La prueba «s05» es la parte de S5 de §9 que toca a las particiones: las estaciones de prueba, su
grupo a ≤ 2 km y su amortiguador quedan fuera del entrenamiento, también en los pliegues internos. La red es sintética
y pequeña, hecha aquí (sin sintetico.py): estaciones puestas en UTM 19S y llevadas a latitud y longitud. Sólo se lee
la clave ``protocolos.BLQ-75.origen_m`` de ``v2/config_v2.json`` (con su huella vigente, la de D51). Correr desde
scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
"""
import sys

sys.dont_write_bytecode = True

import dataclasses  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

import numpy as np  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import constantes, numerico, particiones, tipos, umbrales  # noqa: E402
from meteo_combinada.tipos import Particion  # noqa: E402

_AP = _RAIZ.parent
_APH = _AP.parent / "Air-Pollution-Health-Chile"
_CONFIG_V2 = _AP / "scripts_modelo_1km/v2/config_v2.json"
# D51 (FIJ-10 de fijados): la vigente es la de AP 8542e61 (política operativa de espacio SINCA). La de M0
# (m0/huellas_m0.json; AP c7c47e8) se conserva como estado de M0; la de la ratificación está en AP 6c15981.
# protocolos.BLQ-75 no cambió. test_fijados compara la vigente y la de M0 con git y con fijados.
_SHA_CONFIG_V2 = "1bcb3ff49729ffa65cc89f646f1c711f01a2ecae1241db1cef91eace36aabaae"
_SHA_CONFIG_V2_M0 = "232c75b3376b6fd7c4f73c885c812e170abff7c1a8817d1ac64cc76c68b0534c"

# ---------------------------------------------------------------------------------------------------------------
# Umbrales: los anclados en M0 (umbrales.cargar_m0, con las huellas del JSON y del v2.1, y el Anexo A del texto
# vigente, el v2.4, idéntico). La red de prueba supone estos valores del Anexo A (filas «Selección anidada», «P1 / P2» y «Mínimos»);
# ``test_valores_que_supone_la_red_son_los_del_anexo_a`` lo comprueba. (Integración de la ola 1: se quitó el
# respaldo con valores de prueba que se usó mientras I2 escribía umbrales.)
VALORES_ANEXO_A = {"GRUPO_KM": 2, "P1_PLIEGUES": 10, "P2_BLOQUE_KM": 75, "P2_AMORT_KM": 25, "SEL_PLIEGUES": 5,
                   "SEL_BLOQUE_KM": 75, "SEL_AMORT_KM": 25, "SEL_MOD": 11, "SEL_RESTO": 3, "SEL_MOD_RECORTE": 23,
                   "SEMILLA": 20261023, "MIN_HORAS": 2000}
_U = None


def _umbrales():
    global _U
    if _U is None:
        texto = _APH / umbrales.TEXTO_M0
        if not texto.is_file():
            raise unittest.SkipTest(f"falta {texto.name} anclado en M0; la prueba no se da por aprobada")
        _U = umbrales.cargar_m0(_APH)
    return _U


_A_GEO = None


def _latlon(e, n):
    global _A_GEO
    if _A_GEO is None:
        from pyproj import Transformer
        _A_GEO = Transformer.from_crs("EPSG:32719", "EPSG:4326", always_xy=True)
    lon, lat = _A_GEO.transform(e, n)
    return float(lat), float(lon)


def _info(codigo, e, n, *, excluida=False):
    lat, lon = _latlon(e, n)
    nan = float("nan")
    return tipos.InfoEstacion(
        codigo=codigo, nombre=f"E{codigo}", conjunto="N", macrozona="centro", grupo=tipos.id_grupo([codigo]),
        omm=None, tipo=None, propietario=None, lat_txt=f"{lat:.4f}", lon_txt=f"{lon:.4f}", alt_txt=None, lat=lat,
        lon=lon, z_cat=500.0, rho_km=0.1, k3_pasa=not excluida, z_s=500.0, z_s_fuente="catalogo", celda=None,
        utm_e=float(e), utm_n=float(n), bloque="", pix0=-1, pix1=-1, pix2=-1, pix3=-1, w0=nan, w1=nan, w2=nan, w3=nan,
        respaldo_16km=False, sin_fondo=False, excluida=excluida, motivo="k3" if excluida else None)


# (código, E, N, excluida) en EPSG:32719. Bloques de 75 km: ie = ⌊E/75.000⌋, in = ⌊N/75.000⌋.
RED = (
    ("330001", 310000, 6260000, False),     # 4_83, grupo con 330002 (≈ 1,1 km)
    ("330002", 311000, 6260500, False),     # 4_83
    ("330003", 374500, 6250000, False),     # 4_83, grupo con 330004 (1,5 km), que cae en 5_83: el grupo va a 4_83
    ("330004", 376000, 6250000, False),     # 5_83 por sus coordenadas
    ("330005", 395000, 6250000, False),     # 5_83, a 19 km de 330004: amortiguador de P2-4_83
    ("330006", 420000, 6250000, False),     # 5_83, a 44 km de 330004: entrenamiento de P2-4_83
    ("330007", 330000, 6320000, False),     # 4_84
    ("330009", 501500, 6400000, True),      # excluida, a 1,5 km de 330010 y de 330011: no los une
    ("330010", 500000, 6400000, False),     # 6_85
    ("330011", 503000, 6400000, False),     # 6_85, a 3 km de 330010
    ("330013", 601000, 6501000, False),     # 8_86: cadena 330013-330014-330015 de 1,5 km
    ("330014", 602500, 6501000, False),
    ("330015", 604000, 6501000, False),
    ("330020", 700000, 6290000, False),     # 9_83: prueba de PAR-6
    ("330021", 700000, 6314500, False),     # 9_84, a 24,5 km de 330020; grupo con 330022
    ("330022", 700000, 6316000, False),     # 9_84, a 26 km de 330020
)


def _red():
    """infos con grupo y bloque, grupos y umbrales."""
    U = _umbrales()
    infos = {c: _info(c, e, n, excluida=x) for c, e, n, x in RED}
    grupos = particiones.grupos_mismo_sitio(infos, U)
    completas = {}
    for c, info in infos.items():
        b = str(particiones.bloque(info.lat, info.lon, U))
        completas[c] = dataclasses.replace(info, grupo=grupos.get(c, info.grupo), bloque=b)
    return completas, grupos, U


def _malla(n_lado=5, paso_m=30000):
    """Red de n_lado² estaciones en malla, todas en grupos propios (más lejos que 2 km)."""
    infos = {}
    for i in range(n_lado):
        for j in range(n_lado):
            codigo = f"34{i:02d}{j:02d}"
            infos[codigo] = _info(codigo, 300000 + i * paso_m, 6200000 + j * paso_m)
    U = _umbrales()
    grupos = particiones.grupos_mismo_sitio(infos, U)
    return {c: dataclasses.replace(v, grupo=grupos[c], bloque=str(particiones.bloque(v.lat, v.lon, U)))
            for c, v in infos.items()}, grupos, U


def _dist(infos, a, b):
    return float(numerico.haversine_km(infos[a].lat, infos[a].lon, infos[b].lat, infos[b].lon))


class PruebasUmbralesDePrueba(unittest.TestCase):
    def test_valores_que_supone_la_red_son_los_del_anexo_a(self):
        U = _umbrales()
        for ident, valor in VALORES_ANEXO_A.items():
            with self.subTest(ident=ident):
                self.assertEqual(U.a(ident), valor)


class PruebasS5Particiones(unittest.TestCase):
    def test_s05_prueba_grupo_y_amortiguador_fuera_del_entrenamiento(self):
        """§4.9 y S5: en P1 y P2, y en sus pliegues internos, las estaciones de prueba, todos los miembros de su grupo
        a ≤ 2 km y (en P2) las estaciones a ≤ 25 km de ellas quedan fuera del entrenamiento; los internos sólo usan el
        entrenamiento del externo y, en P2, llevan el mismo amortiguador."""
        infos, grupos, U = _red()
        miembros = {}
        for c, g in grupos.items():
            miembros.setdefault(g, set()).add(c)
        externos = particiones.pliegues_p1(grupos, U) + particiones.pliegues_p2(infos, grupos, U)
        self.assertTrue(externos)
        for ext in externos:
            internos = particiones.pliegues_internos(ext, infos, grupos, U)
            self.assertTrue(internos, ext.id)
            for p in (ext, *internos):
                with self.subTest(pliegue=p.id):
                    prueba, entr = set(p.prueba), set(p.entrenamiento)
                    self.assertFalse(prueba & entr)
                    self.assertFalse(set(p.excluidas) & (prueba | entr))
                    if p is ext:
                        for c in prueba:
                            self.assertTrue(miembros[grupos[c]] <= prueba, "el grupo entero va a prueba")
                    else:
                        self.assertTrue(prueba | entr | set(p.excluidas) <= set(ext.entrenamiento))
                        self.assertFalse(entr & (set(ext.prueba) | set(ext.excluidas)))
                        for c in prueba:
                            self.assertTrue(miembros[grupos[c]] & set(ext.entrenamiento) <= prueba,
                                            "el grupo entero va a la misma prueba interna")
                    if p.particion is Particion.P2:
                        radio = U.a("P2_AMORT_KM") if p is ext else U.a("SEL_AMORT_KM")
                        for c in entr:
                            self.assertTrue(all(_dist(infos, c, t) > radio for t in prueba), c)
                    else:
                        self.assertEqual(p.excluidas, ())


class PruebasParticiones(unittest.TestCase):
    def test_grupos_mismo_sitio(self):
        """§2.5 (PAR-1, PAR-2): componentes conexas a ≤ 2 km; id «G» + el menor código; una excluida no une."""
        infos, grupos, _ = _red()
        self.assertEqual(grupos["330001"], "G330001")
        self.assertEqual(grupos["330002"], "G330001")
        self.assertEqual(grupos["330004"], "G330003")
        self.assertEqual({grupos[c] for c in ("330013", "330014", "330015")}, {"G330013"})   # cadena: 3 km de punta
        self.assertGreater(_dist(infos, "330013", "330015"), 2.0)
        self.assertEqual(grupos["330010"], "G330010")
        self.assertEqual(grupos["330011"], "G330011")
        self.assertNotIn("330009", grupos)
        self.assertEqual(grupos["330021"], grupos["330022"])
        U = _umbrales()
        sin_coord = {"330099": dataclasses.replace(infos["330001"], codigo="330099", lat=float("nan"))}
        with self.assertRaises(ValueError):
            particiones.grupos_mismo_sitio(sin_coord, U)
        excluida = {"330099": dataclasses.replace(infos["330001"], codigo="330099", lat=float("nan"), excluida=True)}
        self.assertEqual(particiones.grupos_mismo_sitio(excluida, U), {})

    def test_bloque_y_origen_de_config_v2(self):
        """§5.1 (PAR-3): ⌊E/75 km⌋_⌊N/75 km⌋ en EPSG:32719, con el origen (0, 0) de protocolos.BLQ-75.origen_m; los
        bordes oeste y sur son del bloque."""
        U = _umbrales()
        if _CONFIG_V2.is_file():
            datos = _CONFIG_V2.read_bytes()
            self.assertEqual(hashlib.sha256(datos).hexdigest(), _SHA_CONFIG_V2)
            origen = json.loads(datos.decode("utf-8"))["protocolos"]["BLQ-75"]["origen_m"]["valor"]
            self.assertEqual(tuple(origen), particiones.ORIGEN_M)
        # H19: el origen sale de la constante del texto (§5.1), no está escrito a mano.
        self.assertEqual(particiones.ORIGEN_M, tuple(float(x) for x in constantes.valor("P2_ORIGEN_M")))
        for c, e, n, _ in RED:
            lat, lon = _latlon(e, n)
            self.assertEqual(str(particiones.bloque(lat, lon, U)), f"{e // 75000}_{n // 75000}", c)
        puntos = [_latlon(310000.0, 6260000.0), _latlon(420000.0, 6250000.0)]
        lat, lon = np.array([q[0] for q in puntos]), np.array([q[1] for q in puntos])
        self.assertEqual(list(particiones.bloque(lat, lon, U)), ["4_83", "5_83"])
        exactos = (np.array([450000.0, 449999.999]), np.array([6300000.0, 6299999.999]))
        with mock.patch.object(particiones.numerico, "utm19s", return_value=exactos):
            self.assertEqual(list(particiones.bloque(np.zeros(2), np.zeros(2), U)), ["6_84", "5_83"])
        with self.assertRaises(ValueError):
            particiones.bloque(float("nan"), -70.0, U)

    def test_p1_diez_pliegues_mc46(self):
        """MC-46 (PAR-5): grupos ordenados, permutados con la semilla y en rueda: 10 pliegues de tamaños que difieren a
        lo más en 1; cada grupo en un pliegue; sin amortiguador; determinista."""
        infos, grupos, U = _malla()
        pliegues = particiones.pliegues_p1(grupos, U)
        self.assertEqual([p.id for p in pliegues], [f"P1-{k}" for k in range(10)])
        tamanos = [len({grupos[c] for c in p.prueba}) for p in pliegues]
        self.assertLessEqual(max(tamanos) - min(tamanos), 1)
        self.assertEqual(sum(tamanos), len(set(grupos.values())))
        vistos = [c for p in pliegues for c in p.prueba]
        self.assertEqual(sorted(vistos), sorted(grupos))
        for p in pliegues:
            self.assertEqual(sorted(p.prueba + p.entrenamiento), sorted(grupos))
            self.assertEqual(p.excluidas, ())
        ids = sorted(set(grupos.values()))
        orden = [ids[i] for i in numerico.generador(U.a("SEMILLA"), "P1").permutation(len(ids))]
        self.assertEqual({grupos[c] for c in pliegues[3].prueba}, set(orden[3::10]))
        self.assertEqual(particiones.pliegues_p1(grupos, U), pliegues)
        # Un grupo de dos estaciones va entero a un pliegue.
        _, grupos_red, _ = _red()
        for p in particiones.pliegues_p1(grupos_red, U):
            self.assertEqual("330001" in p.prueba, "330002" in p.prueba)
        # Con menos grupos que pliegues, los vacíos no se devuelven (PAR-8).
        pocos = {"330001": "G330001", "330002": "G330001", "330003": "G330003"}
        self.assertEqual(len(particiones.pliegues_p1(pocos, U)), 2)

    def test_p2_bloques_y_amortiguador(self):
        """§5.1 (PAR-4, PAR-6): un pliegue por bloque con estaciones; el grupo va al bloque de su miembro de menor
        código; amortiguador de 25 km estación por estación."""
        infos, grupos, U = _red()
        pliegues = {p.id: p for p in particiones.pliegues_p2(infos, grupos, U)}
        self.assertEqual(list(pliegues), ["P2-4_83", "P2-4_84", "P2-5_83", "P2-6_85", "P2-8_86", "P2-9_83", "P2-9_84"])
        p = pliegues["P2-4_83"]
        self.assertEqual(p.prueba, ("330001", "330002", "330003", "330004"))
        self.assertIn("330005", p.excluidas)            # 19 km de 330004
        self.assertIn("330006", p.entrenamiento)        # 44 km
        self.assertIn("330007", p.entrenamiento)
        self.assertNotIn("330009", p.prueba + p.entrenamiento + p.excluidas)
        p = pliegues["P2-5_83"]
        self.assertEqual(p.prueba, ("330005", "330006"))
        self.assertEqual(p.excluidas, ("330003", "330004"))
        # PAR-6: el compañero de grupo de una estación del amortiguador sigue en el entrenamiento si está a > 25 km.
        p = pliegues["P2-9_83"]
        self.assertEqual(p.prueba, ("330020",))
        self.assertEqual(p.excluidas, ("330021",))
        self.assertIn("330022", p.entrenamiento)
        self.assertLessEqual(_dist(infos, "330020", "330021"), 25.0)
        self.assertGreater(_dist(infos, "330020", "330022"), 25.0)
        # PAR-12: un bloque de InfoEstacion distinto del de particiones.bloque es un error.
        malas = {**infos, "330006": dataclasses.replace(infos["330006"], bloque="4_83")}
        with self.assertRaises(ValueError):
            particiones.pliegues_p2(malas, grupos, U)

    def test_pliegues_internos(self):
        """§4.9 (PAR-7): bloques del entrenamiento en 5 pliegues al azar con la etiqueta «internos/<pliegue>»; en P2
        con amortiguador de 25 km y en P1 sin él; un grupo que cruza bloques va junto."""
        infos, grupos, U = _red()
        ext = next(p for p in particiones.pliegues_p2(infos, grupos, U) if p.id == "P2-9_83")
        internos = particiones.pliegues_internos(ext, infos, grupos, U)
        self.assertTrue(1 <= len(internos) <= 5)
        for i in internos:
            self.assertEqual(i.externo, ext.id)
            self.assertTrue(i.id.startswith(ext.id + "/i"))
            self.assertIsNotNone(tipos.PATRON_PLIEGUE.fullmatch(i.id))
            self.assertEqual(i.particion, Particion.P2)
        en_prueba = sorted(c for i in internos for c in i.prueba)
        self.assertEqual(en_prueba, sorted(ext.entrenamiento))          # cada estación de entrenamiento, una vez
        for i in internos:
            self.assertEqual("330003" in i.prueba, "330004" in i.prueba)    # el grupo 4_83/5_83 va junto
        de_bloque = {c: infos[grupos[c][1:]].bloque for c in ext.entrenamiento}
        self.assertEqual(de_bloque["330004"], "4_83")                    # 330004 va con 330003
        orden = sorted(set(de_bloque.values()))
        self.assertEqual(orden, ["4_83", "4_84", "5_83", "6_85", "8_86", "9_84"])
        perm = [orden[k] for k in numerico.generador(U.a("SEMILLA"), "internos", ext.id).permutation(len(orden))]
        esperado = {f"{ext.id}/i{j}": set(perm[j::5]) for j in range(5)}
        for i in internos:
            self.assertEqual({de_bloque[c] for c in i.prueba}, esperado[i.id])
            for c in i.entrenamiento:
                self.assertTrue(all(_dist(infos, c, t) > U.a("SEL_AMORT_KM") for t in i.prueba))
        p1 = particiones.pliegues_p1(grupos, U)[0]
        for i in particiones.pliegues_internos(p1, infos, grupos, U):
            self.assertEqual(i.excluidas, ())
            self.assertEqual(i.particion, Particion.P1)
        self.assertEqual(particiones.pliegues_internos(ext, infos, grupos, U), internos)

    def test_dias_de_seleccion_mc44(self):
        """MC-44 (PAR-9): días UTC con d2000 mód 11 = 3, o mód 23 = 3 con el recorte."""
        U = _umbrales()
        h = np.arange(24 * 50, dtype=np.int32)
        dias = sorted(set((h[particiones.dias_de_seleccion(h, U, recorte=False)] // 24).tolist()))
        self.assertEqual(dias, [3, 14, 25, 36, 47])
        self.assertEqual(int(particiones.dias_de_seleccion(h, U, recorte=False).sum()), 5 * 24)
        dias = sorted(set((h[particiones.dias_de_seleccion(h, U, recorte=True)] // 24).tolist()))
        self.assertEqual(dias, [3, 26, 49])
        self.assertEqual(len({d % 7 for d in (3, 14, 25, 36, 47)}), 5)   # rotan el día de la semana
        self.assertFalse(bool(particiones.dias_de_seleccion(np.array([-1]), U, recorte=False)[0]))
        with self.assertRaises(ValueError):
            particiones.dias_de_seleccion(np.array([1.5]), U, recorte=False)

    def test_distancia_entrenamiento_km(self):
        """§5.3 (PAR-10): a la de entrenamiento más cercana con ≥ 2.000 horas válidas de la variable."""
        infos, _, U = _red()
        horas = {"330006": 2500, "330007": 1999}
        d = particiones.distancia_entrenamiento_km(["330001"], ["330006", "330007"], infos, horas, U)
        self.assertAlmostEqual(d["330001"], _dist(infos, "330001", "330006"), places=9)
        horas["330007"] = 2000
        d = particiones.distancia_entrenamiento_km(["330001"], ["330006", "330007"], infos, horas, U)
        self.assertAlmostEqual(d["330001"], _dist(infos, "330001", "330007"), places=9)
        d = particiones.distancia_entrenamiento_km(["330001", "330002"], ["330006"], infos, {}, U)
        self.assertEqual(d, {"330001": math.inf, "330002": math.inf})
        self.assertEqual(particiones.distancia_entrenamiento_km([], ["330006"], infos, horas, U), {})

    def test_una_sola_fuente_del_grupo_par12_par13(self):
        """H20 (PAR-12, PAR-13): P2, los internos y el remuestreo usan el mismo grupo y el mismo bloque; si
        InfoEstacion y ``grupos`` difieren, o ``grupos`` no cubre exactamente las que entran, o un id de grupo no es el
        de su menor código, es un error."""
        infos, grupos, U = _red()
        p2 = particiones.pliegues_p2(infos, grupos, U)
        b = particiones.bloques_remuestreo(infos)
        for p in p2:
            for c in p.prueba:
                self.assertEqual(b[c], p.id.removeprefix("P2-"), c)     # cada estación, el bloque de su pliegue
        ext = p2[0]
        otro = {**infos, "330004": dataclasses.replace(infos["330004"], grupo="G330004")}
        for funcion in (lambda: particiones.pliegues_p2(otro, grupos, U),
                        lambda: particiones.pliegues_internos(ext, otro, grupos, U)):
            with self.assertRaisesRegex(ValueError, "PAR-12"):
                funcion()
        with self.assertRaises(ValueError):                      # el grupo declarado ya no es el de su menor código
            particiones.bloques_remuestreo({**infos, "330001": dataclasses.replace(infos["330001"], grupo="G330002"),
                                            "330002": dataclasses.replace(infos["330002"], grupo="G330002")})
        sin_bloque = {**infos, "330006": dataclasses.replace(infos["330006"], bloque="")}
        with self.assertRaisesRegex(ValueError, "PAR-12"):
            particiones.pliegues_p2(sin_bloque, grupos, U)
        falta = {c: g for c, g in grupos.items() if c != "330006"}
        sobra = {**grupos, "330009": "G330009"}
        for malos in (falta, sobra):
            with self.assertRaises(ValueError):
                particiones.pliegues_p2(infos, malos, U)
            with self.assertRaises(ValueError):
                particiones.pliegues_internos(ext, infos, malos, U)
        mal_id = {**grupos, "330001": "G330002", "330002": "G330002"}
        for funcion in (lambda: particiones.pliegues_p1(mal_id, U), lambda: particiones.pliegues_p2(infos, mal_id, U)):
            with self.assertRaisesRegex(ValueError, "menor código"):
                funcion()

    def test_bloques_remuestreo_mc34(self):
        """MC-34 (PAR-11): el bloque de P2 del grupo de cada estación, desde InfoEstacion; son los de P2 con estaciones."""
        infos, grupos, U = _red()
        b = particiones.bloques_remuestreo(infos)
        self.assertEqual(b["330004"], "4_83")
        self.assertNotIn("330009", b)
        self.assertEqual(b["330022"], "9_84")
        self.assertEqual({f"P2-{x}" for x in b.values()}, {p.id for p in particiones.pliegues_p2(infos, grupos, U)})
        malas = {**infos, "330003": dataclasses.replace(infos["330003"], bloque="")}
        with self.assertRaises(ValueError):
            particiones.bloques_remuestreo(malas)


if __name__ == "__main__":
    unittest.main()
