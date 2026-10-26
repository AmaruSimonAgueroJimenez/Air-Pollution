"""Pruebas de tablas.py (Anexos A y A2, territorio, partes y fusiones).

Las que llevan «pNN» son el punto NN de §8 (grupos A, B y C). Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .
No abren datos DMC ni /Volumes. Leen sólo código y anexos ya anclados (c0/, verificar_reloj_sinca.py,
_comun_modelo.py, el texto del protocolo); si falta un archivo, la prueba se omite con el motivo.
El catálogo de píxeles es sintético (celdas de 0,1° con cod_comuna fabricado).
"""
import sys

sys.dont_write_bytecode = True

import ast  # noqa: E402
import builtins  # noqa: E402
import copy  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import sysconfig  # noqa: E402
import unittest  # noqa: E402
import zoneinfo  # noqa: E402
from dataclasses import replace  # noqa: E402
from datetime import date, datetime, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from reloj_dmc import tablas  # noqa: E402
from reloj_dmc.tipos import ESQUEMA_ANOTACION, Conjunto, Hipotesis, InfoEstacion, Territorio  # noqa: E402

_AP = _RAIZ.parent
_APH = _AP.parent / "Air-Pollution-Health-Chile"
_AUDITORIA = _APH / "auditoria" / "20261023" / "reloj_dmc"
_C0 = _AUDITORIA / "c0"
_PROTOCOLO = _AUDITORIA / "PROTOCOLO_RELOJ_DMC_v1_propuesta.md"
_SINCA = _RAIZ / "verificar_reloj_sinca.py"
_SINCA_LINEAS = (47, 73)                      # §1.10: `verificar_reloj_sinca.transiciones` (`:47-73`)
_COMUN = _RAIZ / "_comun_modelo.py"
_SHA_COMUN = "a83c0384266554e16ab397749544759ae1cf161f138361eefa7d1ad3e29aa6f4"

SANTIAGO, COYHAIQUE, PUNTA_ARENAS, PASCUA = ("America/Santiago", "America/Coyhaique",
                                            "America/Punta_Arenas", "Pacific/Easter")
H = timedelta(hours=1)

_TABLAS = None


def setUpModule():
    # §9 y §8.A.2: sólo el paquete tzdata del intérprete.
    zoneinfo.reset_tzpath(to=[])
    zoneinfo.ZoneInfo.clear_cache()


def _tablas():
    global _TABLAS
    if _TABLAS is None:
        _TABLAS = tablas.cargar_tablas()
    return _TABLAS


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _P(territorio):
    zs, ids = tablas.ZS_Y_P[territorio]
    return zs, tablas.hipotesis_de_P(ids)


def _clases(territorio, anio, solo=None):
    """Clases del año con todos sus regímenes con datos (o sólo los ids de ``solo``)."""
    zs, P = _P(territorio)
    regs = [r for r in tablas.regimenes_del_anio(zs, anio, _tablas()) if solo is None or r.id in solo]
    return tablas.fusionar(P, regs, zs)


def _ids(clases):
    return {c.id for c in clases}


def _por_id(clases, ident):
    return next(c for c in clases if ident in c.ids_miembros)


def _info(zs, territorio=Territorio.CONTINENTAL):
    return InfoEstacion(codigo="999001", nombre=None, lat=None, lon=None, alt_m=None, coordenadas_validas=True,
                        coordenadas_inconsistentes=False, territorio=territorio, region=None, macrozona="x",
                        zs=tuple(zs), P=(), pixel_id=None, distancia_km=None, costera=False, z_pix=None, dz=None,
                        conjunto=Conjunto.N)


def _extracto(etiquetas):
    return pd.DataFrame({"L": pd.to_datetime(etiquetas).astype("datetime64[ns]"),
                         "ts": [float(i) for i in range(len(etiquetas))]})


def _horas(desde: datetime, hasta: datetime):
    salida, t = [], desde
    while t <= hasta:
        salida.append(t)
        t += H
    return salida


def _macrozona_region():
    """MACROZONA_REGION copiada de _comun_modelo.py leyendo su fuente (sin importarlo), como §3.3."""
    if not _COMUN.is_file():
        raise unittest.SkipTest(f"falta {_COMUN.name}")
    datos = _COMUN.read_bytes()
    if _sha(datos) != _SHA_COMUN:
        raise AssertionError(f"{_COMUN.name} no tiene la huella a83c0384…")
    for nodo in ast.parse(datos.decode("utf-8")).body:
        if isinstance(nodo, ast.Assign) and [getattr(t, "id", None) for t in nodo.targets] == ["MACROZONA_REGION"]:
            return ast.literal_eval(nodo.value)
    raise AssertionError("MACROZONA_REGION no está en _comun_modelo.py")


def _celda(pixel_id, lat, lon, cod_comuna, paso=0.1):
    return {"pixel_id": pixel_id, "latitude": lat, "longitude": lon, "cell_west": lon - paso / 2,
            "cell_east": lon + paso / 2, "cell_south": lat - paso / 2, "cell_north": lat + paso / 2,
            "cod_comuna": cod_comuna}


_CATALOGO = pd.DataFrame([
    _celda(1, -33.45, -70.65, 13101),     # Santiago: continental (región 13)
    _celda(2, -45.55, -72.05, 11101),     # Coyhaique: Aysén
    _celda(3, -53.15, -70.95, 12101),     # Punta Arenas: Magallanes
    _celda(4, -30.05, -71.55, 0),         # celda sin demarcación: incierto
    _celda(5, -62.15, -58.95, 12201),     # una celda antártica: la latitud manda antes que la celda
    _celda(6, -27.15, -109.45, 5201),     # Pascua: la longitud manda antes que la celda
    _celda(7, -33.65, -78.85, 5104),      # Juan Fernández
    _celda(8, -33.5, -76.75, 5101, paso=0.5),   # borde oeste exacto en −77: al este de −77 se mira la celda
])


def _transiciones_sinca():
    """``verificar_reloj_sinca.transiciones`` extraída del código fuente por AST, sin ejecutar el módulo."""
    if not _SINCA.is_file():
        raise unittest.SkipTest(f"falta {_SINCA.name}")
    fuente = _SINCA.read_text(encoding="utf-8")
    nodos = [n for n in ast.parse(fuente).body if isinstance(n, ast.FunctionDef) and n.name == "transiciones"]
    if len(nodos) != 1:
        raise AssertionError("verificar_reloj_sinca.py no trae una sola función «transiciones»")
    nodo = nodos[0]
    if (nodo.lineno, nodo.end_lineno) != _SINCA_LINEAS:
        raise AssertionError(f"«transiciones» ya no está en :47-73 (está en {nodo.lineno}-{nodo.end_lineno})")
    espacio = {"__builtins__": builtins, "date": date, "datetime": datetime, "timedelta": timedelta,
               "ZoneInfo": zoneinfo.ZoneInfo}
    exec(compile(ast.Module(body=[nodo], type_ignores=[]), str(_SINCA), "exec"), espacio)  # noqa: S102
    return espacio["transiciones"]


class PruebasGrupoA2(unittest.TestCase):
    def test_p02_anexo_a_con_tzdata_del_interprete(self):
        """reset_tzpath(to=[]) y clear_cache: sha256 8ea58b78…; 52/32/48/52 cambios."""
        zoneinfo.reset_tzpath(to=[])
        zoneinfo.ZoneInfo.clear_cache()
        tabla = tablas.transiciones_utc("tzdata")
        self.assertEqual(zoneinfo.TZPATH, ())
        self.assertEqual({z: len(v) for z, v in tabla.items()}, tablas.CAMBIOS_POR_ZONA_ANEXO_A)
        datos = tablas.serializar_anexo_a(tabla)
        self.assertEqual(_sha(datos), tablas.SHA_ANEXO_A)
        self.assertFalse(datos.endswith(b"\n"))
        anclado = _C0 / "anexo_a_cambios_hora.json"
        if anclado.is_file():
            self.assertEqual(datos, anclado.read_bytes())

    def test_p02_anexo_a_con_la_base_del_sistema(self):
        """La base del sistema da la misma huella."""
        if not tablas.CARPETA_BASE_SISTEMA.is_dir():
            self.skipTest("este sistema no trae /usr/share/zoneinfo")
        tabla = tablas.transiciones_utc("sistema")
        self.assertEqual(_sha(tablas.serializar_anexo_a(tabla)), tablas.SHA_ANEXO_A,
                         f"base del sistema {tablas.version_de_base('sistema')}")
        self.assertEqual(zoneinfo.TZPATH, (), "leer la base del sistema no debe cambiar TZPATH")
        # La base que el intérprete traería por omisión (su TZPATH compilado) también.
        for carpeta in (sysconfig.get_config_var("TZPATH") or "").split(os.pathsep):
            if carpeta and all((Path(carpeta) / z).is_file() for z in tablas.ZONAS_ANEXO_A):
                with self.subTest(base=carpeta):
                    self.assertEqual(_sha(tablas.serializar_anexo_a(tablas.transiciones_utc(carpeta))),
                                     tablas.SHA_ANEXO_A, f"versión {tablas.version_de_base(carpeta)}")

    def test_p02_tabla_alterada_da_a2(self):
        """Una fila cambiada no reproduce la huella: ErrorTablas (→ A2)."""
        t = _tablas()
        anexo_a = {z: [list(f) for f in filas] for z, filas in t.anexo_a.items()}
        anexo_a2 = list(t.anexo_a2)
        self.assertEqual(tablas.verificar_tablas(anexo_a, anexo_a2), (tablas.SHA_ANEXO_A, tablas.SHA_ANEXO_A2))
        self.assertEqual((t.sha256_anexo_a, t.sha256_anexo_a2), (tablas.SHA_ANEXO_A, tablas.SHA_ANEXO_A2))

        alterada = copy.deepcopy(anexo_a)
        fila = next(f for f in alterada[SANTIAGO] if f[0] == "2019-09-08T04:00Z")
        fila[0] = "2019-09-08T05:00Z"
        with self.assertRaises(tablas.ErrorTablas):
            tablas.verificar_tablas(alterada, anexo_a2)
        sin_fila = copy.deepcopy(anexo_a)
        del sin_fila[PASCUA][-1]
        with self.assertRaisesRegex(tablas.ErrorTablas, "cambios por zona"):
            tablas.verificar_tablas(sin_fila, anexo_a2)
        a2_alterada = list(anexo_a2)
        a2_alterada[0] = tablas.FilaA2(2008, "atraso", date(2008, 3, 29), "marzo, domingo ≥ 9", (date(2008, 3, 1),))
        with self.assertRaisesRegex(tablas.ErrorTablas, "Anexo A2"):
            tablas.verificar_tablas(anexo_a, a2_alterada)
        # La tabla alterada sigue siendo consultable sin verificar (cargar_tablas(verificar=False)).
        self.assertNotEqual(tablas.TablasCalendario(alterada, anexo_a2).sha256_anexo_a, tablas.SHA_ANEXO_A)

    def test_p02_anexo_a2_desde_sus_reglas(self):
        """reglas_anteriores() serializada da b0727bee…."""
        filas = tablas.reglas_anteriores()
        datos = tablas.serializar_anexo_a2(filas)
        self.assertEqual(_sha(datos), tablas.SHA_ANEXO_A2)
        self.assertEqual(len(filas), 13)
        anclado = _C0 / "anexo_a2_reglas_anteriores.json"
        if anclado.is_file():
            self.assertEqual(datos, anclado.read_bytes())

    def test_anexo_a2_se_calcula_de_las_reglas_y_del_anexo_a(self):
        """Las fechas placebo salen de «<mes>, domingo ≥ d»; la fecha real, del Anexo A."""
        self.assertEqual(tablas.fechas_de_regla(2008, "atraso", "marzo, domingo ≥ 9"), (date(2008, 3, 8),))
        self.assertEqual(tablas.fechas_de_regla(2011, "adelanto", "octubre, domingo ≥ 9"), (date(2011, 10, 9),))
        self.assertEqual(tablas.fechas_de_regla(2012, "atraso", "marzo, domingo ≥ 9; y la de 2011, mayo, domingo ≥ 2"),
                         (date(2012, 3, 10), date(2012, 5, 5)))
        self.assertEqual(tablas.fechas_de_regla(2015, "sin atraso", "abril, domingo ≥ 23"), (date(2015, 4, 25),))
        with self.assertRaises(ValueError):
            tablas.fechas_de_regla(2015, "atraso", "abril, lunes ≥ 23")
        # Con otro Anexo A, la fecha real cambia: no se copia del texto.
        anexo_a = {z: [list(f) for f in filas] for z, filas in _tablas().anexo_a.items()}
        next(f for f in anexo_a[SANTIAGO] if f[0] == "2019-09-08T04:00Z")[0] = "2019-09-15T04:00Z"
        fila = next(f for f in tablas.reglas_anteriores(anexo_a) if (f.anio, f.cambio) == (2019, "adelanto"))
        self.assertEqual(fila.fecha_real, date(2019, 9, 15))
        self.assertEqual(fila.fechas_placebo, (date(2019, 8, 11),))

    def test_anexo_a_coincide_con_las_fechas_del_texto(self):
        """Sábados de atraso, domingos de adelanto, 2015 sin cambios y horas de Pascua del Anexo A."""
        if not _PROTOCOLO.is_file():
            self.skipTest(f"falta {_PROTOCOLO.name}")
        texto = _PROTOCOLO.read_text(encoding="utf-8")
        anexo = texto[texto.index("## Anexo A. "):texto.index("## Anexo A2.")]

        def fechas(rotulo):
            linea = next(x for x in anexo.splitlines() if x.startswith(f"- **{rotulo}:**"))
            return [date.fromisoformat(f) for f in re.findall(r"\d{4}-\d{2}-\d{2}", linea)]

        t = _tablas()
        atrasos = [c for c in t.cambios(SANTIAGO) if c.tipo == "atraso"]
        adelantos = [c for c in t.cambios(SANTIAGO) if c.tipo == "adelanto"]
        self.assertEqual([c.fecha_D for c in atrasos], fechas("Sábados de atraso"))
        self.assertEqual([c.fecha_D for c in adelantos], fechas("Domingos de adelanto"))
        self.assertEqual(t.cambios(SANTIAGO, 2015), ())
        for c in t.cambios(SANTIAGO):
            esperado = (5, 23) if c.tipo == "atraso" else (6, 0)      # sábado 23:00 / domingo 00:00
            self.assertEqual((c.etiqueta.weekday(), c.etiqueta.hour), esperado, c)
            self.assertEqual(c.u.hour, 3 if c.tipo == "atraso" else 4)
        for c in t.cambios(PASCUA):
            self.assertEqual((c.etiqueta.weekday(), c.etiqueta.hour), (5, 21) if c.tipo == "atraso" else (5, 22), c)
        self.assertEqual([c.u for c in t.cambios(PASCUA)], [c.u for c in t.cambios(SANTIAGO)])
        self.assertEqual(t.cambios(PUNTA_ARENAS)[-1].fecha_D, date(2016, 8, 14))
        self.assertEqual(t.cambios(COYHAIQUE)[-1].fecha_D, date(2024, 9, 8))
        self.assertEqual([c.u for c in t.cambios(COYHAIQUE)], [c.u for c in t.cambios(SANTIAGO)][:48])


class PruebasGrupoA3(unittest.TestCase):
    def test_p03_precedente_sinca_difiere_como_dice_1_10(self):
        """transiciones_sinca da inexistente 01:00 y repetida 00:00 del domingo; transiciones_utc, 00:00 y 23:00 del sábado."""
        antes = set(sys.modules)
        sinca = _transiciones_sinca()
        self.assertFalse({"_comun_modelo", "_common"} & set(sys.modules))
        self.assertFalse({m for m in set(sys.modules) - antes if "sinca" in m})
        t = _tablas()
        # El caso que cita §1.10, Santiago 2019.
        self.assertEqual(sinca(SANTIAGO, 2019), [(date(2019, 4, 7), "ambigua", 0), (date(2019, 9, 8), "inexistente", 1)])
        repetidas, inexistentes = t.etiquetas_especiales(SANTIAGO, 2019)
        self.assertEqual(repetidas, {datetime(2019, 4, 6, 23)})
        self.assertEqual(inexistentes, {datetime(2019, 9, 8, 0)})
        # Y la diferencia exacta, una hora tarde, en cada cambio de las cuatro zonas de 2000 a 2026.
        n = 0
        for zona in tablas.ZONAS_ANEXO_A:
            for anio in range(tablas.ANIOS_ANEXO_A[0], tablas.ANIOS_ANEXO_A[1] + 1):
                esperado = [((c.etiqueta + H).date(), "inexistente" if c.tipo == "adelanto" else "ambigua",
                             (c.etiqueta + H).hour) for c in t.cambios(zona, anio)]
                with self.subTest(zona=zona, anio=anio):
                    self.assertEqual(sinca(zona, anio), esperado)
                n += len(esperado)
        self.assertEqual(n, sum(tablas.CAMBIOS_POR_ZONA_ANEXO_A.values()))


class PruebasGrupoA4(unittest.TestCase):
    def test_p04_fusiones_por_calendario(self):
        """2015: C(Santiago) ≡ F(−3), C(Pacific/Easter) ≡ F(−5); desde 2017 C(Punta_Arenas) ≡ F(−3); desde 2025 C(Coyhaique) ≡ F(−3)."""
        self.assertEqual(_ids(_clases(Territorio.CONTINENTAL, 2015)), {"F(0)", "F(-3)|C(Santiago)", "F(-4)"})
        self.assertEqual(_ids(_clases(Territorio.PASCUA_SALA_Y_GOMEZ, 2015)),
                         {"F(0)", "F(-3)|C(Santiago)", "F(-4)", "F(-5)|C(Pacific/Easter)", "F(-6)"})
        for anio in range(2017, tablas.ANIOS_ANEXO_A[1] + 1):
            with self.subTest(anio=anio):
                clases = _clases(Territorio.MAGALLANES, anio)
                self.assertIn("F(-3)|C(Punta_Arenas)", _ids(clases))
                self.assertIn("C(Santiago)", _ids(clases))
        self.assertNotIn("F(-3)|C(Punta_Arenas)", _ids(_clases(Territorio.MAGALLANES, 2016)))
        for anio in (2025, 2026):
            self.assertEqual(_ids(_clases(Territorio.AYSEN, anio)),
                             {"F(0)", "F(-3)|C(Coyhaique)", "F(-4)", "C(Santiago)"})
        self.assertNotIn("F(-3)|C(Coyhaique)", _ids(_clases(Territorio.AYSEN, 2024)))
        # Fuera de 2015, en el continente con ambos regímenes nada se fusiona.
        self.assertEqual(_ids(_clases(Territorio.CONTINENTAL, 2019)), {"F(0)", "F(-3)", "F(-4)", "C(Santiago)"})

    def test_p04_fusiones_por_datos(self):
        """Año sólo de verano: C(Santiago) ≡ F(−3); sólo de invierno: ≡ F(−4)."""
        zs, P = _P(Territorio.CONTINENTAL)
        t = _tablas()
        for meses, esperada in (((1, 2), "F(-3)|C(Santiago)"), ((6, 7), "F(-4)|C(Santiago)")):
            etiquetas = [e for m in meses for e in _horas(datetime(2019, m, 1), datetime(2019, m, 28, 23))]
            anotado = tablas.anotar_partes(_extracto(etiquetas), _info(zs), t)
            con_datos = set(anotado.loc[~anotado["especial"], "regimen"].dropna())
            regs = [r for r in tablas.regimenes_del_anio(zs, 2019, t) if r.id in con_datos]
            with self.subTest(meses=meses):
                self.assertEqual(len(regs), 1)
                self.assertIn(esperada, _ids(tablas.fusionar(P, regs, zs)))
        # Una sola etiqueta especial con datos no hace «régimen con datos» (R-30).
        anotado = tablas.anotar_partes(_extracto([datetime(2019, 4, 6, 23)]), _info(zs), t)
        self.assertTrue(anotado["especial"].all())
        self.assertEqual(anotado["regimen"].dropna().tolist(), [])

    def test_fusiones_por_la_regla_general(self):
        """C(Coyhaique) ≡ C(Santiago) hasta 2024; C(Punta_Arenas) ≡ C(Santiago) hasta 2016 (R-30)."""
        for anio in range(tablas.ANIOS_ANEXO_A[0], 2025):
            with self.subTest(zona="Coyhaique", anio=anio):
                esperada = "F(-3)|C(Santiago)|C(Coyhaique)" if anio == 2015 else "C(Santiago)|C(Coyhaique)"
                self.assertIn(esperada, _ids(_clases(Territorio.AYSEN, anio)))
        for anio in range(tablas.ANIOS_ANEXO_A[0], 2017):
            with self.subTest(zona="Punta_Arenas", anio=anio):
                esperada = "F(-3)|C(Santiago)|C(Punta_Arenas)" if anio == 2015 else "C(Santiago)|C(Punta_Arenas)"
                self.assertIn(esperada, _ids(_clases(Territorio.MAGALLANES, anio)))
        # Territorio incierto en 2017: Punta_Arenas ya es fija y Coyhaique sigue a Santiago.
        self.assertEqual(_ids(_clases(Territorio.INCIERTO, 2017)),
                         {"F(0)", "F(-3)|C(Punta_Arenas)", "F(-4)", "C(Santiago)|C(Coyhaique)"})

    def test_rivales_mas_cercanas_y_d_estrella(self):
        """R_min(F(0)) = {F(−3)}; R_min(F(−4)) = {F(−3), C(Santiago)}."""
        clases = _clases(Territorio.CONTINENTAL, 2019)
        f0, f3, f4, cs = (_por_id(clases, i) for i in ("F(0)", "F(-3)", "F(-4)", "C(Santiago)"))
        self.assertEqual(_ids(tablas.rivales_mas_cercanas(f0, clases)), {"F(-3)"})
        self.assertEqual(_ids(tablas.rivales_mas_cercanas(f4, clases)), {"F(-3)", "C(Santiago)"})
        self.assertEqual(_ids(tablas.rivales_mas_cercanas(cs, clases)), {"F(-3)", "F(-4)"})
        self.assertEqual((tablas.d_estrella(f0, f3), tablas.d_estrella(f0, cs), tablas.d_estrella(f4, cs)), (3, 4, 1))
        self.assertEqual(cs.desfases, {"R0": -3, "R1": -4})
        # Las rivales de una clase fusionada excluyen a sus miembros (2015).
        clases = _clases(Territorio.CONTINENTAL, 2015)
        fusionada = _por_id(clases, "C(Santiago)")
        self.assertEqual(_ids(tablas.rivales_mas_cercanas(fusionada, clases)), {"F(-4)"})
        self.assertEqual(_ids(tablas.rivales_mas_cercanas(_por_id(clases, "F(0)"), clases)), {"F(-3)|C(Santiago)"})


class PruebasGrupoA5Territorio(unittest.TestCase):
    CASOS = {   # (lat, lon) → (territorio, región, macrozona)
        "continental": ((-33.45, -70.66), Territorio.CONTINENTAL, 13, "centro"),
        "aysen": ((-45.57, -72.07), Territorio.AYSEN, 11, "austral"),
        "magallanes": ((-53.16, -70.93), Territorio.MAGALLANES, 12, "austral"),
        "antartica": ((-62.19, -58.98), Territorio.ANTARTICA, 12, "austral"),
        "pascua": ((-27.16, -109.43), Territorio.PASCUA_SALA_Y_GOMEZ, None, "insular"),
        "juan_fernandez": ((-33.64, -78.83), Territorio.JUAN_FERNANDEZ_DESVENTURADAS, None, "insular"),
        "desventuradas": ((-26.31, -79.95), Territorio.JUAN_FERNANDEZ_DESVENTURADAS, None, "insular"),
        "incierto": ((-40.0, -73.0), Territorio.INCIERTO, None, "sin_region"),
    }
    P_ESPERADO = {
        Territorio.CONTINENTAL: ((SANTIAGO,), ("F(0)", "F(-3)", "F(-4)", "C(Santiago)")),
        Territorio.JUAN_FERNANDEZ_DESVENTURADAS: ((SANTIAGO,), ("F(0)", "F(-3)", "F(-4)", "C(Santiago)")),
        Territorio.AYSEN: ((COYHAIQUE, SANTIAGO), ("F(0)", "F(-3)", "F(-4)", "C(Coyhaique)", "C(Santiago)")),
        Territorio.MAGALLANES: ((PUNTA_ARENAS, SANTIAGO), ("F(0)", "F(-3)", "F(-4)", "C(Punta_Arenas)", "C(Santiago)")),
        Territorio.ANTARTICA: ((PUNTA_ARENAS, SANTIAGO), ("F(0)", "F(-3)", "F(-4)", "C(Punta_Arenas)", "C(Santiago)")),
        Territorio.PASCUA_SALA_Y_GOMEZ: ((PASCUA, SANTIAGO), ("F(0)", "F(-3)", "F(-4)", "F(-5)", "F(-6)",
                                                            "C(Pacific/Easter)", "C(Santiago)")),
        Territorio.INCIERTO: ((SANTIAGO, COYHAIQUE, PUNTA_ARENAS),
                              ("F(0)", "F(-3)", "F(-4)", "C(Santiago)", "C(Coyhaique)", "C(Punta_Arenas)")),
    }

    def _tyP(self, lat, lon):
        return tablas.territorio_y_P(lat, lon, _CATALOGO, _macrozona_region())

    def test_p05_cada_territorio_recibe_su_P(self):
        """Las cinco filas de §2.2."""
        vistos = set()
        for nombre, ((lat, lon), territorio, region, macro) in self.CASOS.items():
            with self.subTest(caso=nombre):
                t, r, m, zs, P = self._tyP(lat, lon)
                self.assertEqual((t, r, m), (territorio, region, macro))
                self.assertEqual((zs, tuple(h.id for h in P)), self.P_ESPERADO[t])
                vistos.add(t)
        self.assertEqual(vistos, set(Territorio))

    def test_p05_cod_comuna_cero_da_territorio_incierto(self):
        """Y sin celda que la contenga, también."""
        for lat, lon in ((-30.05, -71.55), (-40.0, -73.0)):
            with self.subTest(lat=lat, lon=lon):
                t, r, m, zs, P = self._tyP(lat, lon)
                self.assertEqual((t, r, m), (Territorio.INCIERTO, None, "sin_region"))
                self.assertEqual((zs, tuple(h.id for h in P)), self.P_ESPERADO[Territorio.INCIERTO])
        # La latitud no decide: una estación sin celda a la latitud de Aysén o de Magallanes sigue incierta.
        for lat in (-45.9, -53.9):
            self.assertEqual(self._tyP(lat, -71.5)[0], Territorio.INCIERTO)

    def test_p05_antartica_pascua_y_juan_fernandez_por_coordenadas(self):
        """lat < −60; lon < −100; −100 ≤ lon < −77."""
        self.assertEqual(self._tyP(-62.15, -58.95)[0], Territorio.ANTARTICA)          # aunque haya celda
        self.assertEqual(self._tyP(-60.0, -58.95)[0], Territorio.INCIERTO)            # −60 no es < −60; sin celda
        self.assertEqual(self._tyP(-60.001, -58.95)[0], Territorio.ANTARTICA)
        self.assertEqual(self._tyP(-27.15, -100.001)[0], Territorio.PASCUA_SALA_Y_GOMEZ)
        self.assertEqual(self._tyP(-27.15, -100.0)[0], Territorio.JUAN_FERNANDEZ_DESVENTURADAS)
        self.assertEqual(self._tyP(-33.45, -77.001)[0], Territorio.JUAN_FERNANDEZ_DESVENTURADAS)
        self.assertEqual(self._tyP(-33.45, -77.0)[0], Territorio.CONTINENTAL)         # −77 ya no: celda 8
        # Fuera de −90 ≤ lat ≤ −17 y −110 ≤ lon ≤ −55, o sin coordenadas: incierto (nunca se invierte un signo).
        for lat, lon in ((33.45, -70.66), (-33.45, 70.66), (-27.15, -110.5), (-10.0, -70.0), (None, -70.66),
                         (-33.45, None), (float("nan"), -70.66)):
            with self.subTest(lat=lat, lon=lon):
                t, r, m, _, _ = self._tyP(lat, lon)
                self.assertEqual((t, r, m), (Territorio.INCIERTO, None, "sin_region"))
                self.assertFalse(tablas.coordenadas_en_rango(lat, lon))
        self.assertTrue(tablas.coordenadas_en_rango(-90.0, -110.0))
        self.assertTrue(tablas.coordenadas_en_rango(-17.0, -55.0))

    def test_coordenadas_decimal_coma_y_sexagesimal(self):
        """Punto, coma, grados-minutos-segundos con signo o S/W; nunca invierte un signo."""
        casos = [
            ("-33.445", "lat", -33.445), ("-33,445", "lat", -33.445), (" -70.682777 ", "lon", -70.682777),
            ("−33.445", "lat", -33.445), ("33.445", "lat", 33.445), ("+33.445", "lat", 33.445),
            ("33°27'S", "lat", -33.45), ("33° 27' 00\" S", "lat", -33.45), ("33º27′00″S", "lat", -33.45),
            ("-33°27'", "lat", -33.45), ("-33 27 00", "lat", -33.45), ("70°40'30\"W", "lon", -70.675),
            ("70 40 30 W", "lon", -70.675), ("33°27,5'S", "lat", -(33 + 27.5 / 60)), ("-33°27'S", "lat", -33.45),
            ("33°27'N", "lat", 33.45), ("33°27'", "lat", 33.45), ("70°40'E", "lon", 70 + 40 / 60),
            ("521", "alt", 521.0), ("521,5", "alt", 521.5), ("-3.5", "alt", -3.5),
        ]
        for texto, eje, esperado in casos:
            with self.subTest(texto=texto, eje=eje):
                self.assertAlmostEqual(tablas.interpretar_coordenada(texto, eje), esperado, places=9)
        for texto, eje in (("", "lat"), ("   ", "lat"), (None, "lat"), ("s/d", "lat"), ("abc", "lon"),
                           ("+33°27'S", "lat"), ("-70°40'E", "lon"), ("33°27'W", "lat"), ("70°40'S", "lon"),
                           ("33°61'S", "lat"), ("33°27'75\"S", "lat"), ("33,5°27'S", "lat"), ("1.234,5", "alt"),
                           ("521 m", "alt"), ("33°27'S", "alt"), ("70°40'O", "lon"), ("nan", "lat")):
            with self.subTest(texto=texto, eje=eje):
                self.assertIsNone(tablas.interpretar_coordenada(texto, eje))
        with self.assertRaises(ValueError):
            tablas.interpretar_coordenada("-33.4", "latitud")

    def test_macrozona_islas_e_incierto(self):
        """Islas → «insular»; incierto → «sin_region»."""
        mr = _macrozona_region()
        self.assertEqual(tablas.macrozona(Territorio.PASCUA_SALA_Y_GOMEZ, None, mr), "insular")
        self.assertEqual(tablas.macrozona(Territorio.JUAN_FERNANDEZ_DESVENTURADAS, None, mr), "insular")
        self.assertEqual(tablas.macrozona(Territorio.INCIERTO, None, mr), "sin_region")
        self.assertEqual(tablas.macrozona(Territorio.ANTARTICA, None, mr), "austral")       # R-38
        self.assertEqual(tablas.macrozona(Territorio.AYSEN, 11, mr), "austral")
        self.assertEqual(tablas.macrozona(Territorio.CONTINENTAL, 13, mr), "centro")
        self.assertEqual(tablas.macrozona(Territorio.CONTINENTAL, 2, mr), "norte_grande")
        with self.assertRaises(KeyError):
            tablas.macrozona(Territorio.CONTINENTAL, 99, mr)

    def test_celda_en_borde_comun(self):
        """Dos celdas vecinas que comparten borde: gana la semiabierta [oeste, este) × [sur, norte)."""
        borde = {"cell_south": -33.5, "cell_north": -33.25, "latitude": -33.375, "cod_comuna": 13101}
        cat = pd.DataFrame([{"pixel_id": 20, "cell_west": -70.75, "cell_east": -70.5, "longitude": -70.625, **borde},
                            {"pixel_id": 10, "cell_west": -70.5, "cell_east": -70.25, "longitude": -70.375, **borde}])
        self.assertEqual(tablas.celda_que_contiene(-33.375, -70.5, cat), 10)     # borde común: la del este
        self.assertEqual(tablas.celda_que_contiene(-33.375, -70.6, cat), 20)
        self.assertEqual(tablas.celda_que_contiene(-33.375, -70.75, cat), 20)    # borde oeste cerrado
        self.assertEqual(tablas.celda_que_contiene(-33.25, -70.25, cat), 10)     # esquina noreste cerrada
        self.assertIsNone(tablas.celda_que_contiene(-33.375, -70.76, cat))
        repetida = pd.concat([cat.iloc[[1]].assign(pixel_id=7), cat.iloc[[1]].assign(pixel_id=3)])
        self.assertEqual(tablas.celda_que_contiene(-33.375, -70.4, repetida), 3)  # empate: menor pixel_id
        with self.assertRaises(KeyError):
            tablas.celda_que_contiene(-33.375, -70.6, cat.drop(columns="cod_comuna"))


class PruebasRegimenesYPartes(unittest.TestCase):
    def test_regimenes_r0_r1_y_2015(self):
        """R0 contiene el 1 de enero; 2015 tiene un solo régimen."""
        t = _tablas()
        tuplas = lambda zs, anio: [(r.id, r.desfases_zs) for r in tablas.regimenes_del_anio(zs, anio, t)]  # noqa: E731
        self.assertEqual(tuplas((SANTIAGO,), 2019), [("R0", (-3,)), ("R1", (-4,))])
        self.assertEqual(tuplas((SANTIAGO,), 2015), [("R0", (-3,))])
        self.assertEqual(tuplas((PASCUA, SANTIAGO), 2015), [("R0", (-5, -3))])
        self.assertEqual(tuplas((PASCUA, SANTIAGO), 2019), [("R0", (-5, -3)), ("R1", (-6, -4))])   # sin astillas
        self.assertEqual(tuplas((COYHAIQUE, SANTIAGO), 2025), [("R0", (-3, -3)), ("R1", (-3, -4))])
        self.assertEqual(tuplas((SANTIAGO, COYHAIQUE, PUNTA_ARENAS), 2017), [("R0", (-3, -3, -3)), ("R1", (-4, -4, -3))])
        # En 2016 el verano de enero se retoma en agosto: siguen siendo dos años-régimen.
        self.assertEqual(tuplas((PUNTA_ARENAS, SANTIAGO), 2016), [("R0", (-3, -3)), ("R1", (-4, -4))])
        for zs, _ in tablas.ZS_Y_P.values():
            for anio in range(tablas.ANIOS_ANEXO_A[0], tablas.ANIOS_ANEXO_A[1] + 1):
                regs = tablas.regimenes_del_anio(zs, anio, t)
                self.assertEqual(regs[0].desfases_zs, tuple(t.desfase_civil(z, datetime(anio, 1, 1)) for z in zs))
                self.assertIn(len(regs), (1, 2))
        with self.assertRaises(ValueError):
            tablas.regimenes_del_anio((SANTIAGO,), 1999, t)

    def test_partes_cortadas_en_etiquetas_civiles(self):
        """Santiago 2019-09: «2019-09-1» hasta el sábado 23:00, «2019-09-2» desde el domingo 01:00."""
        t = _tablas()
        resumen = lambda partes: [(p.id, p.n, p.desde, p.hasta, p.regimen) for p in partes]  # noqa: E731
        self.assertEqual(resumen(tablas.partes_del_mes((SANTIAGO,), 2019, 9, t)), [
            ("2019-09-1", 1, datetime(2019, 9, 1), datetime(2019, 9, 7, 23), "R1"),
            ("2019-09-2", 2, datetime(2019, 9, 8, 1), datetime(2019, 9, 30, 23), "R0")])
        self.assertEqual(resumen(tablas.partes_del_mes((SANTIAGO,), 2019, 4, t)), [
            ("2019-04-1", 1, datetime(2019, 4, 1), datetime(2019, 4, 6, 22), "R0"),
            ("2019-04-2", 2, datetime(2019, 4, 7), datetime(2019, 4, 30, 23), "R1")])
        self.assertEqual(resumen(tablas.partes_del_mes((SANTIAGO,), 2019, 6, t)), [
            ("2019-06-1", 1, datetime(2019, 6, 1), datetime(2019, 6, 30, 23), "R1")])
        self.assertEqual(resumen(tablas.partes_del_mes((SANTIAGO,), 2015, 9, t)), [
            ("2015-09-1", 1, datetime(2015, 9, 1), datetime(2015, 9, 30, 23), "R0")])
        self.assertEqual(resumen(tablas.partes_del_mes((SANTIAGO,), 2019, 12, t))[-1][3], datetime(2019, 12, 31, 23))
        # Aysén antes de 2024: ambas zonas cortan en la misma etiqueta, una sola vez.
        self.assertEqual(len(tablas.partes_del_mes((COYHAIQUE, SANTIAGO), 2019, 9, t)), 2)
        # En toda zona y año, las partes de cada mes cubren todas las etiquetas no especiales y nada más.
        for zs, _ in tablas.ZS_Y_P.values():
            for anio in (2008, 2015, 2016, 2019, 2024, 2025):
                especiales = set().union(*(s for z in zs for s in t.etiquetas_especiales(z, anio)))
                cubiertas = set()
                for mes in range(1, 13):
                    for p in tablas.partes_del_mes(zs, anio, mes, t):
                        cubiertas.update(_horas(p.desde, p.hasta))
                self.assertEqual(cubiertas | especiales, set(_horas(datetime(anio, 1, 1), datetime(anio, 12, 31, 23))))
                self.assertFalse(cubiertas & especiales)

    def test_astillas_de_borde_en_pascua(self):
        """Entre las etiquetas especiales de Pacific/Easter y de Santiago: régimen None (R-08)."""
        t = _tablas()
        zs = (PASCUA, SANTIAGO)
        abril = tablas.partes_del_mes(zs, 2019, 4, t)
        self.assertEqual([(p.id, p.desde, p.hasta, p.regimen) for p in abril], [
            ("2019-04-1", datetime(2019, 4, 1), datetime(2019, 4, 6, 20), "R0"),
            ("2019-04-2", datetime(2019, 4, 6, 22), datetime(2019, 4, 6, 22), None),
            ("2019-04-3", datetime(2019, 4, 7), datetime(2019, 4, 30, 23), "R1")])
        septiembre = tablas.partes_del_mes(zs, 2019, 9, t)
        self.assertEqual([(p.id, p.desde, p.hasta, p.regimen) for p in septiembre], [
            ("2019-09-1", datetime(2019, 9, 1), datetime(2019, 9, 7, 21), "R1"),
            ("2019-09-2", datetime(2019, 9, 7, 23), datetime(2019, 9, 7, 23), None),
            ("2019-09-3", datetime(2019, 9, 8, 1), datetime(2019, 9, 30, 23), "R0")])
        # En el extracto anotado: la astilla tiene parte y no régimen; las especiales, ninguna de las dos.
        etiquetas = _horas(datetime(2019, 4, 6, 19), datetime(2019, 4, 7, 1))
        anotado = tablas.anotar_partes(_extracto(etiquetas), _info(zs, Territorio.PASCUA_SALA_Y_GOMEZ), t)
        filas = [(r.L.to_pydatetime(), None if pd.isna(r.parte) else r.parte,
                  None if pd.isna(r.regimen) else r.regimen, bool(r.especial)) for r in anotado.itertuples()]
        self.assertEqual(filas, [
            (datetime(2019, 4, 6, 19), "2019-04-1", "R0", False),
            (datetime(2019, 4, 6, 20), "2019-04-1", "R0", False),
            (datetime(2019, 4, 6, 21), None, None, True),          # repetida de Pacific/Easter
            (datetime(2019, 4, 6, 22), "2019-04-2", None, False),  # astilla: (−6, −3)
            (datetime(2019, 4, 6, 23), None, None, True),          # repetida de Santiago
            (datetime(2019, 4, 7, 0), "2019-04-3", "R1", False),
            (datetime(2019, 4, 7, 1), "2019-04-3", "R1", False)])

    def test_etiquetas_especiales_por_zona(self):
        """Santiago: sábado 23:00 repetida, domingo 00:00 inexistente; Pascua: sábado 21:00 y 22:00."""
        t = _tablas()
        self.assertEqual(t.etiquetas_especiales(SANTIAGO, 2019), ({datetime(2019, 4, 6, 23)}, {datetime(2019, 9, 8, 0)}))
        self.assertEqual(t.etiquetas_especiales(PASCUA, 2019), ({datetime(2019, 4, 6, 21)}, {datetime(2019, 9, 7, 22)}))
        self.assertEqual(t.etiquetas_especiales(PUNTA_ARENAS, 2016),
                         ({datetime(2016, 5, 14, 23)}, {datetime(2016, 8, 14, 0)}))
        self.assertEqual(t.etiquetas_especiales(COYHAIQUE, 2024), ({datetime(2024, 4, 6, 23)}, {datetime(2024, 9, 8, 0)}))
        for zona, anio in ((SANTIAGO, 2015), (PASCUA, 2015), (COYHAIQUE, 2025), (PUNTA_ARENAS, 2017)):
            self.assertEqual(t.etiquetas_especiales(zona, anio), (frozenset(), frozenset()))
        # Coinciden con zoneinfo: repetida ⇔ dos instantes UTC; inexistente ⇔ ninguno (prueba independiente).
        for zona in tablas.ZONAS_ANEXO_A:
            z = zoneinfo.ZoneInfo(zona)
            for anio in (2008, 2012, 2019, 2024):
                repetidas, inexistentes = t.etiquetas_especiales(zona, anio)
                for L in repetidas:
                    a, b = L.replace(tzinfo=z, fold=0), L.replace(tzinfo=z, fold=1)
                    self.assertNotEqual(a.utcoffset(), b.utcoffset())
                for L in inexistentes:
                    ida = L.replace(tzinfo=z).astimezone(timezone.utc).astimezone(z).replace(tzinfo=None)
                    self.assertNotEqual(ida, L)

    def test_campos_de_cada_cambio(self):
        """u, minutos, tipo, etiqueta, fecha D y domingo (E1a, E1b, Anexo A2)."""
        t = _tablas()
        atraso, adelanto = t.cambios(SANTIAGO, 2019)
        self.assertEqual((atraso.u, atraso.antes_min, atraso.despues_min, atraso.tipo),
                         (datetime(2019, 4, 7, 3, tzinfo=timezone.utc), -180, -240, "atraso"))
        self.assertEqual((atraso.etiqueta, atraso.fecha_D, atraso.domingo),
                         (datetime(2019, 4, 6, 23), date(2019, 4, 6), date(2019, 4, 7)))
        self.assertEqual((adelanto.u, adelanto.tipo, adelanto.etiqueta, adelanto.fecha_D, adelanto.domingo),
                         (datetime(2019, 9, 8, 4, tzinfo=timezone.utc), "adelanto", datetime(2019, 9, 8),
                          date(2019, 9, 8), date(2019, 9, 8)))
        pascua = t.cambios(PASCUA, 2019)[1]
        self.assertEqual((pascua.etiqueta, pascua.fecha_D, pascua.domingo, pascua.antes_min, pascua.despues_min),
                         (datetime(2019, 9, 7, 22), date(2019, 9, 7), date(2019, 9, 8), -360, -300))
        self.assertEqual(len(t.cambios(SANTIAGO)), 52)
        with self.assertRaises(KeyError):
            t.cambios("America/Easter")

    def test_anotar_partes_esquema_y_bordes_de_mes(self):
        """Columnas de ESQUEMA_ANOTACION al final, con sus tipos; copia sin reordenar; varios meses."""
        t = _tablas()
        zs = (SANTIAGO,)
        etiquetas = [datetime(2019, 10, 3, 5), datetime(2019, 9, 8, 0), datetime(2019, 9, 7, 23),
                     datetime(2019, 9, 8, 1), datetime(2019, 8, 31, 23)]
        extracto = _extracto(etiquetas)
        extracto.index = [10, 11, 12, 13, 14]
        anotado = tablas.anotar_partes(extracto, _info(zs), t)
        self.assertEqual(list(anotado.columns), ["L", "ts", *ESQUEMA_ANOTACION])
        self.assertEqual({c: str(anotado[c].dtype) for c in ESQUEMA_ANOTACION}, dict(ESQUEMA_ANOTACION))
        self.assertEqual(list(anotado.index), [10, 11, 12, 13, 14])
        self.assertEqual(anotado["parte"].tolist()[:1] + anotado["parte"].tolist()[2:],
                         ["2019-10-1", "2019-09-1", "2019-09-2", "2019-08-1"])
        self.assertTrue(pd.isna(anotado["parte"].iloc[1]))
        self.assertEqual(anotado["especial"].tolist(), [False, True, False, False, False])
        self.assertEqual(list(extracto.columns), ["L", "ts"])            # no toca la entrada
        with self.assertRaises(ValueError):
            tablas.anotar_partes(anotado, _info(zs), t)
        vacio = tablas.anotar_partes(_extracto([]), _info(zs), t)
        self.assertEqual((len(vacio), list(vacio.columns)), (0, ["L", "ts", *ESQUEMA_ANOTACION]))
        con_zona = _extracto(etiquetas)
        con_zona["L"] = con_zona["L"].dt.tz_localize("UTC")
        with self.assertRaises(ValueError):
            tablas.anotar_partes(con_zona, _info(zs), t)
        with self.assertRaises(ValueError):
            tablas.anotar_partes(_extracto([datetime(1999, 12, 31, 23)]), _info(zs), t)

    def test_desfases_por_regimen_y_por_etiqueta(self):
        """c_H(R) y c_H(L), con None en las especiales bajo C(Z)."""
        t = _tablas()
        f4, cs = Hipotesis("F", -4, None), Hipotesis("C", None, SANTIAGO)
        r0, r1 = tablas.regimenes_del_anio((COYHAIQUE, SANTIAGO), 2025, t)
        self.assertEqual(tablas.desfase(f4, r0, (COYHAIQUE, SANTIAGO)), -4)
        self.assertEqual(tablas.desfase(cs, r1, (COYHAIQUE, SANTIAGO)), -4)
        self.assertEqual(tablas.desfase(Hipotesis("C", None, COYHAIQUE), r1, (COYHAIQUE, SANTIAGO)), -3)
        with self.assertRaises(ValueError):
            tablas.desfase(Hipotesis("C", None, PASCUA), r0, (COYHAIQUE, SANTIAGO))
        with self.assertRaises(ValueError):
            tablas.desfase(Hipotesis("Cv", None, SANTIAGO), r0, (COYHAIQUE, SANTIAGO))
        casos = {datetime(2019, 4, 6, 22): -3, datetime(2019, 4, 6, 23): None, datetime(2019, 4, 7, 0): -4,
                 datetime(2019, 9, 7, 23): -4, datetime(2019, 9, 8, 0): None, datetime(2019, 9, 8, 1): -3}
        for L, c in casos.items():
            with self.subTest(L=L):
                self.assertEqual(tablas.desfase_en_etiqueta(cs, L, t), c)
                self.assertEqual(tablas.desfase_en_etiqueta(cs, pd.Timestamp(L), t), c)
                self.assertEqual(tablas.desfase_en_etiqueta(f4, L, t), -4)
        # El desfase civil coincide con zoneinfo en toda etiqueta no especial (prueba independiente).
        z = zoneinfo.ZoneInfo(PASCUA)
        for L in _horas(datetime(2016, 4, 1), datetime(2016, 9, 30, 23)):
            c = t.desfase_civil(PASCUA, L)
            if c is not None:
                self.assertEqual(c * 3600, L.replace(tzinfo=z).utcoffset().total_seconds(), L)
        self.assertEqual(t.desfase_civil_utc(SANTIAGO, datetime(2019, 9, 8, 4, tzinfo=timezone.utc)), -3)
        self.assertEqual(t.desfase_civil_utc(SANTIAGO, datetime(2019, 9, 8, 3, 59)), -4)

    def test_reglas_vencidas_y_placebos_del_anexo_a2(self):
        """Cv(Z, y) cambia en las fechas del Anexo A2 (§4.1.4); los placebos de 2015 en Pascua, a las 22:00."""
        t = _tablas()
        resumen = lambda cambios: [(c.tipo, c.etiqueta) for c in cambios]  # noqa: E731
        self.assertEqual(resumen(t.cambios_reglas_vencidas(SANTIAGO, 2019)),
                         [("atraso", datetime(2019, 5, 11, 23)), ("adelanto", datetime(2019, 8, 11, 0))])
        self.assertEqual(resumen(t.cambios_reglas_vencidas(PASCUA, 2019)),
                         [("atraso", datetime(2019, 5, 11, 21)), ("adelanto", datetime(2019, 8, 10, 22))])
        self.assertEqual(resumen(t.cambios_reglas_vencidas(SANTIAGO, 2015)),
                         [("atraso", datetime(2015, 4, 25, 23)), ("adelanto", datetime(2015, 9, 6, 0))])
        self.assertEqual(resumen(t.cambios_reglas_vencidas(SANTIAGO, 2022)),       # el atraso real se queda
                         [("atraso", datetime(2022, 4, 2, 23)), ("adelanto", datetime(2022, 9, 4, 0))])
        self.assertEqual(resumen(t.cambios_reglas_vencidas(SANTIAGO, 2012)),       # primera regla (R-09)
                         [("atraso", datetime(2012, 3, 10, 23)), ("adelanto", datetime(2012, 10, 14, 0))])
        self.assertEqual(t.cambios_reglas_vencidas(PUNTA_ARENAS, 2019), ())        # sin cambios reales que cambiar
        with self.assertRaises(ValueError):
            t.cambios_reglas_vencidas(SANTIAGO, 2018)
        cv = Hipotesis("Cv", None, SANTIAGO)
        casos = {datetime(2019, 4, 6, 23): -3, datetime(2019, 5, 11, 23): None, datetime(2019, 5, 12, 0): -4,
                 datetime(2019, 8, 11, 0): None, datetime(2019, 8, 11, 1): -3, datetime(2019, 9, 8, 0): -3,
                 datetime(2015, 6, 1): -4, datetime(2015, 2, 1): -3}
        for L, c in casos.items():
            with self.subTest(L=L):
                self.assertEqual(tablas.desfase_en_etiqueta(cv, L, t), c)
        self.assertEqual([c.etiqueta for c in t.placebos_a2(PASCUA, 2015)],
                         [datetime(2015, 4, 25, 21), datetime(2015, 9, 5, 22)])
        self.assertEqual([c.etiqueta for c in t.placebos_a2(SANTIAGO, 2012)],
                         [datetime(2012, 3, 10, 23), datetime(2012, 5, 5, 23), datetime(2012, 8, 19, 0),
                          datetime(2012, 10, 14, 0)])
        self.assertEqual(t.placebos_a2(SANTIAGO, 2018), ())

    def test_enmienda_3_anexo_a3_eventos_de_regla_vencida(self):
        """Enmienda 3, E3-2 (opción A′): el Anexo A3 sale de la regla anterior a 2008 («octubre, domingo ≥ 9»,
        en los años en que no coincide con el Anexo A) y de las fechas de adelanto del Anexo A2, cada evento
        con UNA regla vencida (el patrón va por regla). Por zona, h0 es el domingo 00:00 (en Pascua, el sábado
        22:00) y existe bajo la vigente. La serialización única es por zona, con h0 y regla, y su huella se
        exige en verificar_tablas y entra al control A2 de red."""
        t = _tablas()
        filas = tablas.fechas_reglas_vencidas(t.anexo_a, t.anexo_a2)
        self.assertEqual(filas, t.reglas_vencidas)
        self.assertEqual(len(filas), 21)
        octubre = [f for f, r, _ in filas if r == tablas.REGLA_ANTERIOR_2008_ADELANTO]
        self.assertEqual([f.year for f in octubre], list(range(2011, 2027)))   # 2000-2010 coinciden
        self.assertTrue(all(f.month == 10 and 9 <= f.day <= 15 and f.weekday() == 6 for f in octubre))
        self.assertEqual({f: r for f, r, _ in filas if r != tablas.REGLA_ANTERIOR_2008_ADELANTO},
                         {date(2012, 8, 19): "agosto, domingo ≥ 16", date(2015, 9, 6): "septiembre, domingo ≥ 2",
                          date(2016, 9, 4): "septiembre, domingo ≥ 2", date(2019, 8, 11): "agosto, domingo ≥ 9",
                          date(2022, 9, 4): "septiembre, domingo ≥ 2"})
        self.assertEqual(sorted({r for _, r, _ in filas}), ["agosto, domingo ≥ 16", "agosto, domingo ≥ 9",
                                                           "octubre, domingo ≥ 9", "septiembre, domingo ≥ 2"])
        dobles = {f for f, _, o in filas if o == (tablas.ORIGEN_REGLA_ANTERIOR_2008, tablas.ORIGEN_ANEXO_A2)}
        self.assertEqual(dobles, {date(2011, 10, 9), date(2012, 10, 14)})
        # h0 por zona; sólo las que existen bajo la vigente.
        def h0(zona, anio):
            return [(c.etiqueta, r) for c, r in t.eventos_reglas_vencidas(zona, anio)]
        self.assertEqual(h0(SANTIAGO, 2019), [(datetime(2019, 8, 11, 0), "agosto, domingo ≥ 9"),
                                             (datetime(2019, 10, 13, 0), "octubre, domingo ≥ 9")])
        self.assertEqual(h0(PASCUA, 2016), [(datetime(2016, 9, 3, 22), "septiembre, domingo ≥ 2"),
                                           (datetime(2016, 10, 8, 22), "octubre, domingo ≥ 9")])
        self.assertEqual(h0(SANTIAGO, 2015), [(datetime(2015, 9, 6, 0), "septiembre, domingo ≥ 2"),
                                             (datetime(2015, 10, 11, 0), "octubre, domingo ≥ 9")])
        self.assertEqual(h0(PUNTA_ARENAS, 2019), [(datetime(2019, 10, 13, 0), "octubre, domingo ≥ 9")])
        self.assertEqual(h0(COYHAIQUE, 2026), [(datetime(2026, 10, 11, 0), "octubre, domingo ≥ 9")])
        for zona in (SANTIAGO, PASCUA, COYHAIQUE, PUNTA_ARENAS):
            for anio in (2008, 2009, 2010):
                self.assertEqual(h0(zona, anio), [], (zona, anio))
            for anio in range(2008, 2027):
                for c, _ in t.eventos_reglas_vencidas(zona, anio):
                    self.assertIsNotNone(t.desfase_civil(zona, c.etiqueta), (zona, c.etiqueta))
        # Las fechas del A2 son las mismas etiquetas que sus placebos.
        self.assertIn(datetime(2012, 8, 19, 0), {c.etiqueta for c in t.placebos_a2(SANTIAGO, 2012)})
        # La tabla por zona y su serialización única: {zona: [[h0, regla], …]}, claves ordenadas.
        a3 = tablas.anexo_a3(t)
        self.assertEqual(list(a3), list(tablas.ZONAS_ANEXO_A))
        self.assertEqual({z: len(e) for z, e in a3.items()},
                         {SANTIAGO: 21, PUNTA_ARENAS: 19, COYHAIQUE: 21, PASCUA: 21})
        crudo = tablas.serializar_anexo_a3(a3)
        objeto = json.loads(crudo)
        self.assertEqual(list(objeto), sorted(tablas.ZONAS_ANEXO_A))
        self.assertEqual(objeto[PASCUA][0], ["2011-10-08T22:00", "octubre, domingo ≥ 9"])
        self.assertEqual(objeto[SANTIAGO][1], ["2012-08-19T00:00", "agosto, domingo ≥ 16"])
        self.assertFalse(crudo.endswith(b"\n"))
        self.assertEqual(crudo, json.dumps(objeto, ensure_ascii=False, sort_keys=True,
                                           separators=(",", ":")).encode("utf-8"))
        self.assertEqual(hashlib.sha256(crudo).hexdigest(), tablas.SHA_ANEXO_A3)
        self.assertEqual(t.sha256_anexo_a3, tablas.SHA_ANEXO_A3)
        # Dos reglas para un mismo domingo no se admiten (el patrón va por regla).
        malo = [replace(f, regla="octubre, domingo ≥ 9; y la de 2011, octubre, domingo ≥ 14",
                        fechas_placebo=(date(2012, 10, 14), date(2012, 10, 14)))
                if f.anio == 2012 and f.cambio == "adelanto" else f for f in t.anexo_a2]
        with self.assertRaisesRegex(tablas.ErrorTablas, "dos reglas vencidas"):
            tablas.fechas_reglas_vencidas(t.anexo_a, malo)
        # La huella se exige: con otra anclada, ErrorTablas (→ A2), y red.a2 la informa siempre.
        anexo_a = {z: [list(f) for f in fs] for z, fs in t.anexo_a.items()}
        self.assertEqual(tablas.verificar_tablas(anexo_a, list(t.anexo_a2)), (tablas.SHA_ANEXO_A, tablas.SHA_ANEXO_A2))
        original = tablas.SHA_ANEXO_A3
        try:
            tablas.SHA_ANEXO_A3 = "0" * 64
            with self.assertRaisesRegex(tablas.ErrorTablas, "Anexo A3"):
                tablas.verificar_tablas(anexo_a, list(t.anexo_a2))
        finally:
            tablas.SHA_ANEXO_A3 = original
        from reloj_dmc import red
        ok = red.a2(t.sha256_anexo_a, t.sha256_anexo_a2, t.sha256_anexo_a3)
        self.assertTrue(ok.pasa)
        self.assertEqual(ok.detalle["anexo_a3"], {"calculada": tablas.SHA_ANEXO_A3, "anclada": tablas.SHA_ANEXO_A3,
                                                  "reproduce": True})
        self.assertFalse(red.a2(t.sha256_anexo_a, t.sha256_anexo_a2, "0" * 64).pasa)

    def test_con_cortes_en_las_etiquetas_de_cv(self):
        """Interfaz pública de la ola 4b (ORQ-3b): las partes se cortan además en las etiquetas especiales de
        Cv(Z, y), que quedan especiales; desfases, cambios y regímenes no cambian y el calendario base tampoco."""
        t = _tablas()
        antes = tablas.partes_del_mes((SANTIAGO,), 2019, 5, t)
        cortado = t.con_cortes_reglas_vencidas([SANTIAGO], [2019])
        self.assertIsInstance(cortado, tablas.TablasCalendario)
        self.assertIsNot(cortado, t)
        # Cv(Santiago, 2019): atraso con la 23:00 del 2019-05-11 repetida; adelanto con h0 el 2019-08-11 00:00.
        intervalos = [tablas.intervalo_especial(c) for c in t.cambios_reglas_vencidas(SANTIAGO, 2019)]
        self.assertEqual(intervalos, [(datetime(2019, 5, 11, 23), datetime(2019, 5, 12, 0)),
                                      (datetime(2019, 8, 11, 0), datetime(2019, 8, 11, 1))])
        partes = tablas.partes_del_mes((SANTIAGO,), 2019, 5, cortado)
        self.assertEqual([(p.desde, p.hasta) for p in partes],
                         [(datetime(2019, 5, 1), datetime(2019, 5, 11, 22)),
                          (datetime(2019, 5, 12), datetime(2019, 5, 31, 23))])
        self.assertEqual(len(antes), 1)
        self.assertEqual(tablas.partes_del_mes((SANTIAGO,), 2019, 5, t), antes)       # el base no cambia
        self.assertEqual(cortado.con_cortes({}).cambios(SANTIAGO), t.cambios(SANTIAGO))
        anotado = tablas.anotar_partes(_extracto(_horas(datetime(2019, 8, 10, 22), datetime(2019, 8, 11, 2))),
                                       _info((SANTIAGO,)), cortado)
        self.assertEqual(list(anotado["especial"]), [False, False, True, False, False])
        self.assertEqual(list(anotado["parte"].astype(object).where(anotado["parte"].notna(), None)),
                         ["2019-08-1", "2019-08-1", None, "2019-08-2", "2019-08-2"])
        for anio in (2018, 2019, 2020):
            self.assertEqual(tablas.regimenes_del_anio((SANTIAGO,), anio, cortado),
                             tablas.regimenes_del_anio((SANTIAGO,), anio, t))
        for L in _horas(datetime(2019, 5, 11, 20), datetime(2019, 5, 12, 2)):
            self.assertEqual(cortado.desfase_civil(SANTIAGO, L), t.desfase_civil(SANTIAGO, L), L)
        self.assertEqual(cortado.sha256_anexo_a, t.sha256_anexo_a)
        # Errores: año fuera del Anexo A2, zona sin Anexo A y corte vacío.
        with self.assertRaises(ValueError):
            t.con_cortes_reglas_vencidas([SANTIAGO], [2018])
        with self.assertRaises(KeyError):
            t.con_cortes({"America/Easter": [(datetime(2019, 1, 1), datetime(2019, 1, 1, 1))]})
        with self.assertRaises(ValueError):
            t.con_cortes({SANTIAGO: [(datetime(2019, 1, 1, 1), datetime(2019, 1, 1, 1))]})


if __name__ == "__main__":
    unittest.main()
