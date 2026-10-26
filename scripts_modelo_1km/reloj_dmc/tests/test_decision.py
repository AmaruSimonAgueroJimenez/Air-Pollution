"""Pruebas de decision.py (§5.1, §5.3, tabla de §5.5, reglas vencidas y expedientes de control).

Las que llevan «pNN» son el punto NN de §8 (grupos A, B y C); aquí son las versiones unitarias de los
casos de decisión (la integral, con datos fabricados, va en test_orquestacion). Las tablas de estados se
construyen a mano con ESQUEMA_ESTADOS (estados.filas_estado). Los umbrales son los anclados en C0
(umbrales.cargar_c0); si faltan el texto o el JSON, las pruebas se omiten y no se dan por aprobadas.
``lineas_fisicas.e3p_anual`` (otro dueño) se simula en las pruebas de los pasos con la regla de §4.3.4 (variante
R de la Enmienda 3), para no depender de lineas_fisicas; la de §8.21 (PruebasP21) usa la función real.
Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .
"""
import sys

sys.dont_write_bytecode = True

import unittest  # noqa: E402
from dataclasses import replace  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from reloj_dmc import constantes, decision, estados, lineas_fisicas, tablas, umbrales  # noqa: E402
from reloj_dmc.estados import ErrorFusion  # noqa: E402
from reloj_dmc.tipos import (ESQUEMA_ESTADOS, ESQUEMA_EVENTOS, ESQUEMA_GUARDAS, ESQUEMA_HORAS,  # noqa: E402
                             ESQUEMA_MARCAS, ESQUEMA_MES, ESQUEMA_METRICAS_E2, ESQUEMA_METRICAS_E3,
                             ESQUEMA_METRICAS_E4, ESQUEMA_RACHAS, Conjunto, ConsecuenciasRed, DecisionAnio,
                             Estado, EvidenciaEstacion, InfoEstacion, Linea, ModoE3t, MotivoAnio,
                             MotivoSinInfo, Nivel, Regimen, Regla, ResultadoGuarda, Territorio, Veredicto,
                             tabla_vacia, validar_esquema)

_APH = Path(umbrales.__file__).resolve().parents[2].parent / "Air-Pollution-Health-Chile"
U = None


def setUpModule():
    global U
    for ruta in (_APH / umbrales.PROTOCOLO_C0, _APH / umbrales.JSON_C0):
        if not ruta.is_file():
            raise unittest.SkipTest(f"falta {ruta.name} anclado en C0; la prueba no se da por aprobada")
    U = umbrales.cargar_c0(_APH)


C, I, D, S = Estado.COMPATIBLE, Estado.INCOMPATIBLE, Estado.DUDOSA, Estado.SIN_INFORMACION
COD = "330020"
F0, F3, F4, F5, F6 = "F(0)", "F(-3)", "F(-4)", "F(-5)", "F(-6)"
CS, CE = "C(Santiago)", "C(Pacific/Easter)"
P_CONT = (F0, F3, F4, CS)
ZS_CONT = ("America/Santiago",)
P_PASCUA = (F0, F3, F4, F5, F6, CE, CS)
ZS_PASCUA = ("Pacific/Easter", "America/Santiago")
DOS_REGIMENES = ((-3,), (-4,))       # Santiago: R0 verano (UTC−3), R1 invierno (UTC−4)
UN_REGIMEN = ((-3,),)                # 2015, o un año con datos sólo de verano
PASCUA_REGIMENES = ((-5, -3), (-6, -4))
DOCE = range(1, 13)


# ---------------------------------------------------------------------------------------------
# Simulación de lineas_fisicas.e3p_anual (§4.3.4), mientras I8 no la entregue.
LLAMADAS_E3P = []


def _e3p_anual_simulada(gruesa, fina, fina_activa):
    """Incompatible por la gruesa según §4.0 (estados.anual_por_partes) o por la fina activa; compatible si
    no es incompatible y es compatible por la fina o por la gruesa en todos sus años-régimen informativos
    (al menos uno; R-52 por año-régimen, variante R); anómalo por la gruesa o por la fina activa."""
    LLAMADAS_E3P.append(fina_activa)
    salida = estados.anual_por_partes(gruesa, linea=Linea.E3P, regla=Regla.GRUESA)
    reg = lambda df: df[df["nivel"] == str(Nivel.REGIMEN)]  # noqa: E731
    g, f = reg(gruesa), reg(fina) if fina_activa else reg(fina).iloc[0:0]
    for i in salida.index[salida["nivel"] == str(Nivel.ANIO)]:
        anio, h = salida.at[i, "anio"], salida.at[i, "H"]
        por_r_g = {u: e for u, e, hh, a in zip(g["unidad"], g["estado"], g["H"], g["anio"]) if hh == h and a == anio}
        por_r_f = {u: e for u, e, hh, a in zip(f["unidad"], f["estado"], f["H"], f["anio"]) if hh == h and a == anio}
        if any(e == I for e in por_r_f.values()):
            salida.at[i, "estado"] = str(I)
        if bool(f.loc[f["anio"] == anio, "reloj_anomalo"].any()):
            salida.at[i, "reloj_anomalo"] = True
        if salida.at[i, "estado"] != str(I):
            # variante R (LF-17): informativo por año-régimen, con cualquier H compatible o incompatible
            inf = (str(C), str(I))
            info = ({u for u, e, a in zip(g["unidad"], g["estado"], g["anio"]) if a == anio and e in inf}
                    | {u for u, e, a in zip(f["unidad"], f["estado"], f["anio"]) if a == anio and e in inf})
            if info and all(str(C) in (por_r_f.get(r), por_r_g.get(r)) for r in info):
                salida.at[i, "estado"] = str(C)
    return salida.astype(ESQUEMA_ESTADOS)


class _ConE3pSimulada(unittest.TestCase):
    def setUp(self):
        LLAMADAS_E3P.clear()
        parche = mock.patch.object(lineas_fisicas, "e3p_anual", side_effect=_e3p_anual_simulada)
        parche.start()
        self.addCleanup(parche.stop)


# ---------------------------------------------------------------------------------------------
# Constructores de datos sintéticos
def _info(P=P_CONT, zs=ZS_CONT, territorio=Territorio.CONTINENTAL, macrozona="centro", codigo=COD):
    return InfoEstacion(codigo=codigo, nombre="sintetica", lat=-33.4, lon=-70.6, alt_m=500.0, coordenadas_validas=True,
                        coordenadas_inconsistentes=False, territorio=territorio, region=13, macrozona=macrozona,
                        zs=zs, P=tablas.hipotesis_de_P(P), pixel_id=1, distancia_km=0.0, costera=False, z_pix=500.0,
                        dz=0.0, conjunto=Conjunto.V)


def _clases(anio, vectores=DOS_REGIMENES, P=P_CONT, zs=ZS_CONT):
    regimenes = [Regimen(anio, f"R{i}", v) for i, v in enumerate(vectores)]
    return tablas.fusionar(tablas.hipotesis_de_P(P), regimenes, zs)


class _Estados:
    """Filas de ESQUEMA_ESTADOS de una estación, armadas con estados.filas_estado."""

    def __init__(self, codigo=COD):
        self.codigo, self.marcos = codigo, []

    def fila(self, anio, linea, nivel, unidad, por_h, *, regla=Regla.UNICA, anomalo=False, discordante=False,
             motivo=None):
        self.marcos.append(estados.filas_estado(self.codigo, anio, linea, nivel, unidad, por_h, regla=regla,
                                                reloj_anomalo=anomalo, discordante=discordante, motivo=motivo))
        return self

    def anual(self, anio, linea, por_h, **kw):
        return self.fila(anio, linea, Nivel.ANIO, f"{anio:04d}", por_h, **kw)

    def partes(self, anio, linea, por_h, meses=DOCE, **kw):
        for m in meses:
            self.fila(anio, linea, Nivel.PARTE, f"{anio:04d}-{m:02d}-1", por_h, **kw)
        return self

    def e3p(self, anio, regimenes, partes=None, meses=DOCE, fina=None, anomalas=()):
        """E3p: regla gruesa por año-régimen y por parte; regla fina por año-régimen."""
        for r, por_h in regimenes.items():
            self.fila(anio, Linea.E3P, Nivel.REGIMEN, r, por_h, regla=Regla.GRUESA)
        for m in meses:
            unidad = f"{anio:04d}-{m:02d}-1"
            por_h = (partes or {}).get(unidad, (partes or {}).get("*"))
            if por_h:
                self.fila(anio, Linea.E3P, Nivel.PARTE, unidad, por_h, regla=Regla.GRUESA, anomalo=unidad in anomalas)
        for r, por_h in (fina or {}).items():
            self.fila(anio, Linea.E3P, Nivel.REGIMEN, r, por_h, regla=Regla.FINA)
        return self

    def tabla(self):
        if not self.marcos:
            return tabla_vacia(ESQUEMA_ESTADOS)
        return pd.concat(self.marcos, ignore_index=True).astype(ESQUEMA_ESTADOS)


def _tabla(filas, esquema):
    return pd.DataFrame(filas, columns=list(esquema)).astype(esquema) if filas else tabla_vacia(esquema)


def _guardas(filas, codigo=COD):
    """filas: (año, guarda, H, unidad, resultado)."""
    return _tabla([{"codigo": codigo, "anio": a, "guarda": str(g), "H": h, "unidad": u, "resultado": str(r),
                    "detalle": None} for a, g, h, u, r in filas], ESQUEMA_GUARDAS)


def _marcas(filas, codigo=COD):
    """filas: (año, marca, H, valor)."""
    return _tabla([{"codigo": codigo, "anio": a, "marca": m, "H": h, "valor": v} for a, m, h, v in filas],
                  ESQUEMA_MARCAS)


def _mes(anio, m):
    return f"{anio:04d}-{m:02d}"


def _meses(meses, codigo=COD, fuera=()):
    filas = []
    for i, texto in enumerate(meses):
        anio, m = (int(x) for x in texto.split("-"))
        filas.append({"codigo": codigo, "anio": anio, "mes": m, "manifiesto": f"DMC/estaciones/{codigo}/{texto}.manifest.json",
                      "manifiesto_sha256": "0" * 64, "artefacto_sha256": "1" * 64, "id_artefacto": i,
                      "script_sha256": "2" * 64, "entra": texto not in fuera,
                      "motivo_exclusion": "version_no_admitida" if texto in fuera else None, "row_count": 24,
                      "source_empty_slots": 0, "expected_hour_slots": 744, "n_available_hours": 744,
                      "duplicate_display_rows_removed": 0, "source_sha256": "3" * 64, "requested_start": None,
                      "requested_end": None, "campos_faltantes": [], "p_ts": 1, "p_qfe": 1, "lat_txt": None,
                      "lon_txt": None, "alt_txt": None})
    return _tabla(filas, ESQUEMA_MES)


def _meses_de(anios, meses=DOCE):
    return [_mes(a, m) for a in anios for m in meses]


def _evidencia(est, *, guardas=(), marcas=(), meses=(), info=None, fuera=()):
    return EvidenciaEstacion(info=info or _info(), estados=est.tabla(), metricas_e2=tabla_vacia(ESQUEMA_METRICAS_E2),
                             metricas_e3=tabla_vacia(ESQUEMA_METRICAS_E3), metricas_e4=tabla_vacia(ESQUEMA_METRICAS_E4),
                             eventos=tabla_vacia(ESQUEMA_EVENTOS), guardas=_guardas(guardas), marcas=_marcas(marcas),
                             meses=_meses(meses, fuera=fuera), horas=tabla_vacia(ESQUEMA_HORAS))


def _consecuencias(*, a3_pais=False, a3_macro=(), modo="restringido", a4=False, macrozona="centro"):
    return ConsecuenciasRed(a3_falla_pais=a3_pais, a3_fallan_macrozonas=frozenset(a3_macro), a5_alto=False,
                            modo_e3t={macrozona: ModoE3t(modo)}, a4_restringe=a4)


# Perfiles de año continental. E2 y E4p: (anual, parte); E3p: (regímenes, partes, fina); E1a: anual.
_R2 = ("R0", "R1")
PERFILES = {
    F0: {  # estación en UTC con QFE
        Linea.E2: ({F0: C, F3: C, F4: I, CS: I}, {F0: C, F3: C, F4: I, CS: S}),
        Linea.E3P: ({r: {F0: C, F3: I, F4: I, CS: I} for r in _R2}, {"*": {F0: C, F3: I, F4: I, CS: I}}, None),
        Linea.E4P: ({F0: C, F3: I, F4: I, CS: I}, {F0: C, F3: I, F4: I, CS: I}),
    },
    F4: {  # reloj fijo UTC−4: lo separan E2 y la regla fina
        Linea.E2: ({F0: I, F3: I, F4: C, CS: I}, {F0: I, F3: I, F4: C, CS: S}),
        Linea.E3P: ({"R0": {F0: I, F3: S, F4: C, CS: S}, "R1": {F0: I, F3: S, F4: C, CS: C}},
                    {"*": {F0: I, F3: S, F4: C, CS: S}},
                    {r: {F0: I, F3: I, F4: C, CS: I} for r in _R2}),
        Linea.E4P: ({F0: I, F3: C, F4: C, CS: C}, {F0: I, F3: C, F4: C, CS: C}),
    },
    CS: {  # hora civil de Santiago, dos regímenes
        Linea.E1A: ({F0: I, F3: I, F4: I, CS: C}, None),
        Linea.E2: ({F0: I, F3: I, F4: I, CS: C}, {F0: S, F3: S, F4: S, CS: C}),
        Linea.E3P: ({"R0": {F0: I, F3: C, F4: S, CS: C}, "R1": {F0: I, F3: S, F4: C, CS: C}},
                    {"*": {F0: I, F3: S, F4: S, CS: C}},
                    {"R0": {F0: I, F3: C, F4: I, CS: C}, "R1": {F0: I, F3: I, F4: C, CS: C}}),
        Linea.E4P: ({F0: I, F3: C, F4: C, CS: C}, {F0: I, F3: C, F4: C, CS: C}),
    },
    "2015": {  # 2015 continental: un solo régimen, C(Santiago) ≡ F(−3)
        Linea.E1A: ({F0: S, F3: S, F4: S, CS: S}, None),
        Linea.E2: ({F0: C, F3: C, F4: I, CS: C}, {F0: C, F3: C, F4: I, CS: C}),
        Linea.E3P: ({"R0": {F0: I, F3: C, F4: S, CS: C}}, {"*": {F0: I, F3: C, F4: S, CS: C}},
                    {"R0": {F0: I, F3: C, F4: I, CS: C}}),
        Linea.E4P: ({F0: I, F3: C, F4: C, CS: C}, {F0: I, F3: C, F4: C, CS: C}),
    },
    "2018": {  # F(−4) hasta junio y F(0) desde el 2018-07-01
        Linea.E2: ({F0: I, F3: I, F4: I, CS: I}, None),
        Linea.E3P: ({r: {F0: S, F3: S, F4: S, CS: S} for r in _R2},
                    {**{f"2018-{m:02d}-1": {F0: I, F3: S, F4: C, CS: S} for m in range(1, 7)},
                     **{f"2018-{m:02d}-1": {F0: C, F3: I, F4: I, CS: I} for m in range(7, 13)}}, None),
        Linea.E4P: ({F0: S, F3: S, F4: S, CS: S}, None),
    },
}


def _perfil(est, anio, reloj, *, meses=DOCE, sin=()):
    for linea, valores in PERFILES[reloj].items():
        if linea in sin:
            continue
        if linea == Linea.E3P:
            regimenes, partes, fina = valores
            est.e3p(anio, regimenes, partes, meses=meses, fina=fina)
            continue
        anual, parte = valores
        est.anual(anio, linea, anual)
        if parte is not None:
            est.partes(anio, linea, parte, meses=meses)
    return est


def _decidir(evidencia, anio, clases, consecuencias=None):
    return decision.decidir_anio(evidencia, anio, consecuencias or _consecuencias(), U, clases=clases)


def _anio_simple(reloj=F0, anio=2019, *, sin=(), meses=DOCE, guardas=(), marcas=(), consecuencias=None,
                 vectores=DOS_REGIMENES, extra=None):
    est = _perfil(_Estados(), anio, reloj, meses=meses, sin=sin)
    if extra:
        extra(est)
    ev = _evidencia(est, guardas=guardas, marcas=marcas, meses=[_mes(anio, m) for m in meses])
    return _decidir(ev, anio, _clases(anio, vectores), consecuencias)


# ---------------------------------------------------------------------------------------------
class PruebasPasos(_ConE3pSimulada):
    def test_paso1_insumos_por_clase(self):
        """P, clases (2015 fusionado), estados por clase, meses con datos y consecuencias de A3."""
        est = _perfil(_Estados(), 2015, "2015")
        ev = _evidencia(est, meses=_meses_de([2015]), fuera=("2015-04",))
        ins = decision.insumos_anio(ev, 2015, _consecuencias(), U, clases=_clases(2015, UN_REGIMEN))
        self.assertEqual(ins.P, P_CONT)
        self.assertEqual([c.id for c in ins.clases], [F0, f"{F3}|{CS}", F4])
        self.assertEqual(len(ins.meses_con_datos), 11)
        self.assertNotIn("2015-04", ins.meses_con_datos)
        a = ins.estados_anuales
        fila = a[(a["linea"] == "E2") & (a["clase"] == f"{F3}|{CS}")]
        self.assertEqual(fila["estado"].tolist(), ["compatible"])
        self.assertEqual(set(a.columns), set(decision.COLUMNAS_ANUALES))
        self.assertTrue(a.loc[a["linea"] == "E4p", "excluye"].all())
        self.assertFalse(a.loc[a["linea"] == "E3t", "excluye"].any())
        self.assertEqual(LLAMADAS_E3P, [True])
        # Donde falla A3: E4p no excluye ni es Q y la fina se apaga.
        ins = decision.insumos_anio(ev, 2015, _consecuencias(a3_macro=("centro",)), U, clases=_clases(2015, UN_REGIMEN))
        e4p = ins.estados_anuales[ins.estados_anuales["linea"] == "E4p"]
        self.assertFalse(e4p["excluye"].any() or e4p["cuantitativa"].any())
        self.assertFalse(ins.e4p_activa or ins.fina_activa)
        self.assertEqual(LLAMADAS_E3P[-1], False)

    def test_paso1_apagado_de_la_fina(self):
        """Una fila de la fina con nivel estación y motivo «apagada» apaga la fina aunque A3 pase."""
        est = _perfil(_Estados(), 2019, F4)
        est.fila(2019, Linea.E3P, Nivel.ESTACION, "*", {F4: S}, regla=Regla.FINA, motivo=str(MotivoSinInfo.APAGADA))
        ev = _evidencia(est, meses=_meses_de([2019]))
        ins = decision.insumos_anio(ev, 2019, _consecuencias(), U, clases=_clases(2019))
        self.assertFalse(ins.fina_activa)
        self.assertEqual(LLAMADAS_E3P, [False])
        # Sin la fina, F(−4) no se separa de F(−3) ni de C(Santiago) por E3p; E2 sigue excluyéndolas.
        d = _decidir(ev, 2019, _clases(2019))
        self.assertEqual(d.veredicto, Veredicto.INSUFICIENTE)
        self.assertEqual(d.motivo, MotivoAnio.APOYO)

    def test_paso1_errores_de_interfaz(self):
        """Sin clases, con clases que no parten P, o con miembros de una clase con estados distintos."""
        est = _perfil(_Estados(), 2015, "2015")
        ev = _evidencia(est, meses=_meses_de([2015]))
        with self.assertRaises(ValueError):
            decision.insumos_anio(ev, 2015, _consecuencias(), U)
        with self.assertRaises(ValueError):
            decision.insumos_anio(ev, 2015, _consecuencias(), U, clases=_clases(2015)[:3])
        est.anual(2015, Linea.E6, {F3: C, CS: S})
        ev = _evidencia(est, meses=_meses_de([2015]))
        with self.assertRaises(ErrorFusion):
            decision.insumos_anio(ev, 2015, _consecuencias(), U, clases=_clases(2015, UN_REGIMEN))
        malo = replace(ev, estados=ev.estados.astype({"anio": "int32"}))
        with self.assertRaises(ValueError):
            decision.insumos_anio(malo, 2015, _consecuencias(), U, clases=_clases(2015, UN_REGIMEN))

    def test_paso1_clases_desde_la_evidencia(self):
        """EvidenciaEstacion.clases (año → clases) basta sin ``clases=``; si llegan las dos, manda el argumento."""
        est = _perfil(_Estados(), 2015, "2015")
        ev = _evidencia(est, meses=_meses_de([2015]))
        self.assertIsNone(ev.clases)                                   # valor por omisión compatible
        fusionadas, separadas = _clases(2015, UN_REGIMEN), _clases(2015)
        con_clases = replace(ev, clases={2015: fusionadas})
        por_argumento = decision.insumos_anio(ev, 2015, _consecuencias(), U, clases=fusionadas)
        por_evidencia = decision.insumos_anio(con_clases, 2015, _consecuencias(), U)
        self.assertEqual([c.id for c in por_evidencia.clases], [c.id for c in por_argumento.clases])
        pd.testing.assert_frame_equal(por_evidencia.estados_anuales, por_argumento.estados_anuales)
        manda = decision.insumos_anio(replace(ev, clases={2015: separadas}), 2015, _consecuencias(), U,
                                      clases=fusionadas)
        self.assertEqual([c.id for c in manda.clases], [c.id for c in por_argumento.clases])
        self.assertEqual(decision.decidir_anio(con_clases, 2015, _consecuencias(), U),
                         decision.decidir_anio(ev, 2015, _consecuencias(), U, clases=fusionadas))
        with self.assertRaises(ValueError):                            # el año no está en la evidencia
            decision.insumos_anio(replace(ev, clases={2016: fusionadas}), 2015, _consecuencias(), U)

    def test_sin_datos(self):
        """Un año sin meses evaluados es «sin_datos»."""
        est = _perfil(_Estados(), 2019, F0)
        ev = _evidencia(est, meses=_meses_de([2020]))
        d = _decidir(ev, 2019, _clases(2019))
        self.assertEqual(d.veredicto, Veredicto.SIN_DATOS)

    def test_paso2_anomalo_y_g_version(self):
        """Discrepante por una línea que decide con reloj anómalo, o por G-versión; E3t no cuenta."""
        d = _anio_simple(F0, extra=lambda e: e.anual(2019, Linea.E6, {F0: S, F3: S, F4: S, CS: S}, anomalo=True))
        self.assertEqual((d.veredicto, d.motivo), (Veredicto.DISCREPANTE, MotivoAnio.RELOJ_ANOMALO))
        self.assertIn("E6", d.detalle)
        d = _anio_simple(F0, extra=lambda e: e.anual(2019, Linea.E3T, {F0: C, F3: I, F4: I, CS: I}, anomalo=True,
                                                     regla=Regla.GRUESA))
        self.assertEqual(d.veredicto, Veredicto.CONFIRMADO)
        d = _anio_simple(F0, guardas=[(2019, Linea.G_VERSION, "*", "2019", ResultadoGuarda.FALLA)])
        self.assertEqual((d.veredicto, d.motivo), (Veredicto.DISCREPANTE, MotivoAnio.G_VERSION))
        self.assertEqual(d.guardas["G-version"], "falla")
        # Una sola parte anómala no basta (es discordante); dos dejan el año anómalo (§4.0).
        uno = lambda e: e.e3p(2019, {}, {"2019-05-1": {F0: S, F3: S, F4: S, CS: S}}, meses=[5],  # noqa: E731
                              anomalas=("2019-05-1",))
        d = _anio_simple(F0, sin=(Linea.E3P,), extra=lambda e: (_perfil_e3p_sin(e, (5,)), uno(e)))
        self.assertEqual(d.veredicto, Veredicto.CONFIRMADO)
        self.assertEqual(d.partes_discordantes, ("2019-05-1",))
        dos = lambda e: e.e3p(2019, {}, {u: {F0: S, F3: S, F4: S, CS: S} for u in ("2019-05-1", "2019-08-1")},  # noqa: E731
                              meses=[5, 8], anomalas=("2019-05-1", "2019-08-1"))
        d = _anio_simple(F0, sin=(Linea.E3P,), extra=lambda e: (_perfil_e3p_sin(e, (5, 8)), dos(e)))
        self.assertEqual((d.veredicto, d.motivo), (Veredicto.DISCREPANTE, MotivoAnio.RELOJ_ANOMALO))

    def test_paso3_e3t_nunca_excluye(self):
        """Sólo líneas no térmicas excluyen; E4p deja de excluir donde falla A3."""
        e3t = lambda e: e.anual(2019, Linea.E3T, {F0: I, F3: C, F4: I, CS: I}, regla=Regla.GRUESA)  # noqa: E731
        d = _anio_simple(F0, extra=e3t, consecuencias=_consecuencias(modo="completo"))
        self.assertNotIn(F0, d.excluidas)
        self.assertEqual(d.veredicto, Veredicto.CONFIRMADO)
        self.assertNotIn("E3t", d.excluidas[F3])
        # E4p como única línea que excluye a F(−3): con A3 fallando, F(−3) queda en K.
        sin_e3p = lambda e: e.e3p(2019, {r: {F0: C, F3: S, F4: I, CS: I} for r in _R2},  # noqa: E731
                                  {"*": {F0: C, F3: S, F4: I, CS: I}})
        d = _anio_simple(F0, sin=(Linea.E3P,), extra=sin_e3p)
        self.assertEqual(d.K, (F0,))
        self.assertEqual(d.excluidas[F3], ("E4p",))
        d = _anio_simple(F0, sin=(Linea.E3P,), extra=sin_e3p, consecuencias=_consecuencias(a3_pais=True))
        self.assertEqual(d.K, (F0, F3))
        self.assertEqual((d.veredicto, d.motivo), (Veredicto.INSUFICIENTE, MotivoAnio.NO_DISTINGUE))

    def test_paso4_k_vacio_y_k_multiple(self):
        """Discrepante con exclusiones listadas; insuficiente «no distingue»."""
        d = _anio_simple(F4, sin=(Linea.E2, Linea.E3P), extra=_sin_fina)
        self.assertEqual((d.veredicto, d.motivo), (Veredicto.INSUFICIENTE, MotivoAnio.NO_DISTINGUE))
        self.assertEqual(d.K, (F3, F4, CS))
        self.assertIn("no distingue entre F(-3), F(-4), C(Santiago)", d.detalle)
        d = _anio_simple(F0, extra=lambda e: e.anual(2019, Linea.E1A, {F0: I, F3: C, F4: C, CS: C}))
        self.assertEqual((d.veredicto, d.motivo), (Veredicto.DISCREPANTE, MotivoAnio.LINEAS_EN_CONFLICTO))
        self.assertEqual(d.K, ())
        self.assertEqual(d.excluidas[F0], ("E1a",))
        self.assertIn("F(0): E1a", d.detalle)

    def test_paso5_guardas(self):
        """E3d, P7, T-P o E4t fallan → discrepante; T-P sólo con E3p compatible con H."""
        for guarda, motivo in decision.MOTIVO_GUARDA.items():
            d = _anio_simple(F0, guardas=[(2019, guarda, F0, "R1", ResultadoGuarda.FALLA),
                                          (2019, guarda, F0, "R0", ResultadoGuarda.PASA)])
            self.assertEqual((d.veredicto, d.motivo), (Veredicto.DISCREPANTE, motivo), guarda)
        # La falla de otra H no afecta; «*» vale para toda H.
        d = _anio_simple(F0, guardas=[(2019, Linea.E3D, F4, "2019", ResultadoGuarda.FALLA),
                                      (2019, Linea.P7, "*", "2019", ResultadoGuarda.PASA)])
        self.assertEqual(d.veredicto, Veredicto.CONFIRMADO)
        self.assertEqual((d.guardas["E3d"], d.guardas["P7"], d.guardas["E4t"]), ("no_evaluable", "pasa", "no_evaluable"))
        d = _anio_simple(F0, guardas=[(2019, Linea.P7, "*", "2019", ResultadoGuarda.FALLA)])
        self.assertEqual(d.motivo, MotivoAnio.GUARDA_P7)
        # T-P no se evalúa si E3p no es compatible con H: queda «no_evaluable» (lo que cuenta A4).
        e3p_mudo = lambda e: e.e3p(2019, {r: {F0: S, F3: I, F4: I, CS: I} for r in _R2})  # noqa: E731
        d = _anio_simple(F0, sin=(Linea.E3P,), extra=e3p_mudo,
                         guardas=[(2019, Linea.TP, F0, "R0", ResultadoGuarda.FALLA)])
        self.assertEqual(d.guardas["T-P"], "no_evaluable")
        self.assertNotEqual(d.veredicto, Veredicto.DISCREPANTE)
        # Miembros de una clase con resultados distintos: error de implementación.
        est = _perfil(_Estados(), 2015, "2015")
        ev = _evidencia(est, meses=_meses_de([2015]), guardas=[(2015, Linea.E4T, F3, "R0", ResultadoGuarda.FALLA),
                                                               (2015, Linea.E4T, CS, "R0", ResultadoGuarda.PASA)])
        with self.assertRaises(ErrorFusion):
            _decidir(ev, 2015, _clases(2015, UN_REGIMEN))

    def test_paso7_apoyo_discriminante(self):
        """≥ 2 líneas, ≥ 2 familias, ≥ 1 Q contra R_min(H); E3t sólo en modo completo."""
        d = _anio_simple(F0)
        self.assertEqual(d.veredicto, Veredicto.CONFIRMADO)
        self.assertEqual(d.clase_confirmada, F0)
        self.assertEqual(d.lineas_apoyo, ("E3p", "E4p"))          # E2 no separa F(0) de F(−3) (R_min)
        self.assertEqual(d.familias_apoyo, ("presion_reanalisis", "presion_marea"))
        self.assertEqual(d.n_lineas_q, 2)
        self.assertEqual(d.modo_e3t, ModoE3t.RESTRINGIDO)
        # Dos líneas de una misma familia (registro) y ninguna Q.
        registro = lambda e: (e.anual(2019, Linea.E1A, {F0: S, F3: C, F4: C, CS: I}),  # noqa: E731
                              e.e3p(2019, {r: {F0: I, F3: S, F4: C, CS: S} for r in _R2},
                                    {"*": {F0: I, F3: S, F4: C, CS: S}}))
        d = _anio_simple(F4, sin=(Linea.E3P,), extra=registro)
        self.assertEqual(d.K, (F4,))
        self.assertEqual((d.veredicto, d.motivo), (Veredicto.INSUFICIENTE, MotivoAnio.APOYO))
        self.assertEqual((d.lineas_apoyo, d.familias_apoyo, d.n_lineas_q), (("E1a", "E2"), ("registro",), 0))
        # Aeródromo sin E4p: sólo E3p; con E3t en modo completo, E3p + E3t.
        e3t = lambda e: e.anual(2019, Linea.E3T, {F0: C, F3: I, F4: I, CS: I}, regla=Regla.GRUESA)  # noqa: E731
        d = _anio_simple(F0, sin=(Linea.E4P,), extra=e3t)
        self.assertEqual((d.veredicto, d.motivo), (Veredicto.INSUFICIENTE, MotivoAnio.APOYO))
        d = _anio_simple(F0, sin=(Linea.E4P,), extra=e3t, consecuencias=_consecuencias(modo="completo"))
        self.assertEqual(d.veredicto, Veredicto.CONFIRMADO)
        self.assertEqual((d.lineas_apoyo, d.n_lineas_q), (("E3t", "E3p"), 2))
        # A4 restringe E3t en todo el país.
        d = _anio_simple(F0, sin=(Linea.E4P,), extra=e3t, consecuencias=_consecuencias(modo="completo", a4=True))
        self.assertEqual(d.motivo, MotivoAnio.APOYO)

    def test_paso7_desfase_termico_local(self):
        """§5.5: E3t contra E3p sin forma de reloj → marca y E3t no apoya ese año (si T-P pasó)."""
        e3t = lambda e: e.anual(2019, Linea.E3T, {F0: C, F3: I, F4: I, CS: I}, regla=Regla.GRUESA)  # noqa: E731
        completo = _consecuencias(modo="completo")
        tp_pasa = [(2019, Linea.TP, F0, "R0", ResultadoGuarda.PASA)]
        marca = decision.MARCA_DESFASE_TERMICO_LOCAL
        d = _anio_simple(F0, sin=(Linea.E4P,), extra=e3t, consecuencias=completo, guardas=tp_pasa,
                         marcas=[(2019, marca, F0, 2.5)])
        self.assertEqual((d.veredicto, d.motivo), (Veredicto.INSUFICIENTE, MotivoAnio.APOYO))
        self.assertTrue(d.marcas[marca])
        d = _anio_simple(F0, sin=(Linea.E4P,), extra=e3t, consecuencias=completo, guardas=tp_pasa,
                         marcas=[(2019, marca, F0, -1.5), (2019, "G-HR", F0, True)])
        self.assertEqual(d.veredicto, Veredicto.CONFIRMADO)
        self.assertEqual(d.marcas, {"G-HR": True, marca: False})
        # Sin T-P evaluada, la marca no rige; NaN no marca.
        d = _anio_simple(F0, sin=(Linea.E4P,), extra=e3t, consecuencias=completo, marcas=[(2019, marca, F0, 2.5)])
        self.assertEqual(d.veredicto, Veredicto.CONFIRMADO)
        d = _anio_simple(F0, sin=(Linea.E4P,), extra=e3t, consecuencias=completo, guardas=tp_pasa,
                         marcas=[(2019, marca, F0, float("nan"))])
        self.assertEqual(d.veredicto, Veredicto.CONFIRMADO)

    def test_paso8_cobertura(self):
        """mín(3, meses con datos) meses con apoyo propio; sólo cuentan las líneas de apoyo."""
        pocas = lambda e: (e.e3p(2019, {r: {F0: C, F3: I, F4: I, CS: I} for r in _R2},  # noqa: E731
                                 {"*": {F0: C, F3: I, F4: I, CS: I}}, meses=(3, 4)),
                           e.anual(2019, Linea.E4P, {F0: C, F3: I, F4: I, CS: I}),
                           e.partes(2019, Linea.E4P, {F0: S, F3: S, F4: S, CS: S}))
        d = _anio_simple(F0, sin=(Linea.E3P, Linea.E4P), extra=pocas)
        self.assertEqual((d.veredicto, d.motivo), (Veredicto.INSUFICIENTE, MotivoAnio.COBERTURA))
        self.assertEqual(d.meses_con_apoyo, ("2019-03", "2019-04"))   # E2 es compatible en todo, pero no apoya
        d = _anio_simple(F0, sin=(Linea.E3P, Linea.E4P), extra=pocas, meses=(3, 4))
        self.assertEqual(d.veredicto, Veredicto.CONFIRMADO)
        self.assertEqual(len(d.meses_con_datos), 2)
        # E6 aporta por mes.
        e6 = lambda e: (pocas(e), e.anual(2019, Linea.E6, {F0: C, F3: I, F4: I, CS: I}),  # noqa: E731
                        e.fila(2019, Linea.E6, Nivel.MES, "2019-09", {F0: C, F3: I, F4: I, CS: I}))
        d = _anio_simple(F0, sin=(Linea.E3P, Linea.E4P), extra=e6)
        self.assertEqual(d.veredicto, Veredicto.CONFIRMADO)
        self.assertEqual(d.meses_con_apoyo, ("2019-03", "2019-04", "2019-09"))

    def test_p16_estacion_utc(self):
        """Estación de 24 h con QFE: F(0). Aeródromo sin E4p: insuficiente salvo E3t completo o E6."""
        self.assertEqual(_anio_simple(F0).clase_confirmada, F0)
        self.assertEqual(_anio_simple(F0, sin=(Linea.E4P,)).motivo, MotivoAnio.APOYO)
        e6 = lambda e: e.anual(2019, Linea.E6, {F0: C, F3: I, F4: I, CS: I})  # noqa: E731
        d = _anio_simple(F0, sin=(Linea.E4P,), extra=e6)
        self.assertEqual((d.veredicto, d.lineas_apoyo), (Veredicto.CONFIRMADO, ("E3p", "E6")))

    def test_p17_f_menos4_fija(self):
        """F(−4): con E2 o E1a más la regla fina, confirmado; sin ellas, insuficiente."""
        d = _anio_simple(F4)
        self.assertEqual((d.veredicto, d.clase_confirmada), (Veredicto.CONFIRMADO, F4))
        self.assertEqual(d.lineas_apoyo, ("E2", "E3p"))
        e1a = lambda e: e.anual(2019, Linea.E1A, {F0: C, F3: C, F4: C, CS: I})  # noqa: E731
        d = _anio_simple(F4, sin=(Linea.E2,), extra=e1a)
        self.assertEqual((d.veredicto, d.lineas_apoyo), (Veredicto.CONFIRMADO, ("E1a", "E3p")))
        d = _anio_simple(F4, sin=(Linea.E2, Linea.E3P), extra=_sin_fina)
        self.assertEqual(d.veredicto, Veredicto.INSUFICIENTE)

    def test_p19_presion_en_0_y_rr_en_clase_2(self):
        """E2 excluye F(0) y E3p excluye F(−4): discrepante."""
        rr_clase_2 = lambda e: e.anual(2019, Linea.E2, {F0: I, F3: I, F4: C, CS: I})  # noqa: E731
        d = _anio_simple(F0, sin=(Linea.E2,), extra=rr_clase_2)
        self.assertEqual((d.veredicto, d.motivo), (Veredicto.DISCREPANTE, MotivoAnio.LINEAS_EN_CONFLICTO))
        self.assertEqual(d.excluidas[F0], ("E2",))
        self.assertIn("E3p", d.excluidas[F4])

    def test_parte_discordante_con_anio_regimen_compatible(self):
        """§4.0 (no es el punto 21 de §8, que va en PruebasP21): con los dos años-régimen compatibles con F(0)
        por la gruesa, una parte con −4 fuerte queda discordante y su mes sin regla, y el año se confirma; con
        dos partes, discrepante. No distingue cómo se lee «informativo» en E3p anual (por año-régimen, R, o por
        H): R0 y R1 son compatibles con F(0) en las dos lecturas."""
        una = {"*": {F0: C, F3: I, F4: I, CS: I}, "2019-05-1": {F0: I, F3: S, F4: C, CS: S}}
        d = _anio_simple(F0, sin=(Linea.E3P,), extra=lambda e: e.e3p(2019, PERFILES[F0][Linea.E3P][0], una))
        self.assertEqual(d.veredicto, Veredicto.CONFIRMADO)
        self.assertEqual(d.partes_discordantes, ("2019-05-1",))
        r = decision.rachas([d], _meses(_meses_de([2019])), frozenset(), U)
        self.assertNotIn("2019-05", r.meses_con_regla)
        self.assertEqual(len(r.meses_con_regla), 11)
        dos = {**una, "2019-08-1": una["2019-05-1"]}
        d = _anio_simple(F0, sin=(Linea.E3P,), extra=lambda e: e.e3p(2019, PERFILES[F0][Linea.E3P][0], dos))
        self.assertEqual((d.veredicto, d.motivo), (Veredicto.DISCREPANTE, MotivoAnio.LINEAS_EN_CONFLICTO))
        self.assertIn("E3p", d.excluidas[F0])

    def test_p22_solo_termica_no_se_confirma(self):
        """Una estación sólo con Ts (E3t y E2): ni restringida ni completa la confirman (E3t no excluye)."""
        def solo_ts(e):
            e.anual(2019, Linea.E3T, {F0: C, F3: I, F4: I, CS: I}, regla=Regla.GRUESA)
            e.anual(2019, Linea.E2, {F0: C, F3: C, F4: I, CS: I})
        for modo in ("restringido", "completo"):
            d = _anio_simple(F0, sin=(Linea.E2, Linea.E3P, Linea.E4P), extra=solo_ts,
                             consecuencias=_consecuencias(modo=modo))
            self.assertEqual(d.veredicto, Veredicto.INSUFICIENTE, modo)

    def test_p23_pascua_utc_sin_pixel(self):
        """Pascua en UTC sin E3: sin E6 insuficiente (E4p sola); con E6 FM-12, F(0)."""
        info = _info(P=P_PASCUA, zs=ZS_PASCUA, territorio=Territorio.PASCUA_SALA_Y_GOMEZ, macrozona="insular")
        clases = _clases(2019, PASCUA_REGIMENES, P=P_PASCUA, zs=ZS_PASCUA)
        e4p = {F0: C, F3: I, F4: I, F5: I, F6: I, CE: I, CS: I}

        def pascua(con_e6):
            est = _Estados()
            est.anual(2019, Linea.E2, {F0: C, F3: C, F4: I, F5: I, F6: C, CE: I, CS: I})
            est.anual(2019, Linea.E4P, e4p).partes(2019, Linea.E4P, e4p)
            if con_e6:
                est.anual(2019, Linea.E6, e4p)
            ev = _evidencia(est, info=info, meses=_meses_de([2019]))
            return decision.decidir_anio(ev, 2019, _consecuencias(macrozona="insular"), U, clases=clases)
        d = pascua(False)
        self.assertEqual((d.K, d.veredicto, d.motivo), ((F0,), Veredicto.INSUFICIENTE, MotivoAnio.APOYO))
        d = pascua(True)
        self.assertEqual((d.veredicto, d.clase_confirmada, d.familias_apoyo),
                         (Veredicto.CONFIRMADO, F0, ("presion_marea", "externa")))

    def test_a3_quita_q_a_e4p(self):
        """E4p puede apoyar sin ser Q (lectura R-27)."""
        a3 = _consecuencias(a3_pais=True)
        d = _anio_simple(F0, consecuencias=a3)
        self.assertEqual((d.veredicto, d.n_lineas_q, d.lineas_apoyo), (Veredicto.CONFIRMADO, 1, ("E3p", "E4p")))
        # E1b + E4p: con A3 bien, una Q; con A3 fallando, ninguna (y E4p ya no excluye a F(−3)).
        e1b = lambda e: e.anual(2019, Linea.E1B, {F0: C, F3: I, F4: I, CS: I})  # noqa: E731
        d = _anio_simple(F0, sin=(Linea.E2, Linea.E3P), extra=e1b)
        self.assertEqual((d.veredicto, d.lineas_apoyo, d.n_lineas_q), (Veredicto.CONFIRMADO, ("E1b", "E4p"), 1))
        d = _anio_simple(F0, sin=(Linea.E2, Linea.E3P), extra=e1b, consecuencias=a3)
        self.assertEqual((d.veredicto, d.motivo, d.n_lineas_q), (Veredicto.INSUFICIENTE, MotivoAnio.APOYO, 0))

    def test_tabla_5_5(self):
        """Casos de la tabla de discrepancias de §5.5 que decide este módulo."""
        # E1a presente y patrón civil en E2, el mismo año.
        def e1a_y_civil(e):
            e.anual(2019, Linea.E1A, {F0: C, F3: C, F4: C, CS: I})
            e.anual(2019, Linea.E2, {F0: I, F3: I, F4: I, CS: C})
        d = _anio_simple(CS, sin=(Linea.E1A, Linea.E2), extra=e1a_y_civil)
        self.assertEqual((d.veredicto, d.motivo), (Veredicto.DISCREPANTE, MotivoAnio.LINEAS_EN_CONFLICTO))
        # T-P con forma de reloj.
        d = _anio_simple(F0, guardas=[(2019, Linea.TP, F0, "R1", ResultadoGuarda.FALLA)])
        self.assertEqual((d.veredicto, d.motivo), (Veredicto.DISCREPANTE, MotivoAnio.GUARDA_TP))
        # Hora civil de dos regímenes: tres líneas de apoyo contra F(−3) y F(−4).
        d = _anio_simple(CS)
        self.assertEqual((d.veredicto, d.lineas_apoyo), (Veredicto.CONFIRMADO, ("E1a", "E2", "E3p")))

    def test_decidir_anio_exige_a4(self):
        """Las dos pasadas: la segunda exige A4; la primera deja el confirmado provisional."""
        est = _perfil(_Estados(), 2019, F0)
        ev = _evidencia(est, meses=_meses_de([2019]))
        sin_a4 = replace(_consecuencias(), a4_restringe=None)
        with self.assertRaises(ValueError):
            decision.decidir_anio(ev, 2019, sin_a4, U, clases=_clases(2019))
        ins = decision.insumos_anio(ev, 2019, sin_a4, U, clases=_clases(2019))
        parcial = decision.pasos_1_a_6(ins, U)
        self.assertEqual((parcial.veredicto, parcial.clase_confirmada, parcial.modo_e3t),
                         (Veredicto.CONFIRMADO, None, None))
        with self.assertRaises(ValueError):
            decision.pasos_7_a_9(parcial, ins, sin_a4, U)
        final = decision.pasos_7_a_9(parcial, ins, _consecuencias(), U)
        self.assertEqual(final.clase_confirmada, F0)


def _e3p_como_lineas_fisicas(est, anio, regimenes, partes):
    """E3p gruesa como la entrega lineas_fisicas.e3: los años-régimen y las partes pasan por
    estados.anual_por_partes (§4.0), que agrega las filas anuales (sólo incompatible y anómalo) y marca las
    partes discordantes. Así la decisión lee las partes discordantes sin la simulación de e3p_anual."""
    crudo = _Estados(est.codigo).e3p(anio, regimenes, partes).tabla()
    est.marcos.append(estados.anual_por_partes(crudo, linea=Linea.E3P, regla=Regla.GRUESA,
                                               min_partes=constantes.valor("ANUAL_MIN_PARTES")))
    return est


class PruebasP21(unittest.TestCase):
    """§8.21 con la Enmienda 3 (E3-2, opción R; LF-17), con lineas_fisicas.e3p_anual real (sin simulación)."""

    # Año UTC 2019 con dos regímenes: la gruesa de R0, el año-régimen de la parte, deja a F(0) residual y da
    # incompatibles a las rivales; la de R1 es compatible con F(0) (§8.21: «es informativo y no es compatible
    # con F(0)»). Las partes son las de una sinóptica en UTC; marzo (y noviembre) traen el −4 fuerte.
    REGIMENES = {"R0": {F0: S, F3: I, F4: I, CS: I}, "R1": {F0: C, F3: I, F4: I, CS: I}}
    PARTE_MENOS4 = {F0: I, F3: S, F4: C, CS: S}
    UNA = {"*": {F0: C, F3: I, F4: I, CS: I}, "2019-03-1": PARTE_MENOS4}
    DOS = {**UNA, "2019-11-1": PARTE_MENOS4}
    E6 = {F0: C, F3: I, F4: I, CS: I}

    def _anio(self, partes, con_e6):
        def extra(e):
            _e3p_como_lineas_fisicas(e, 2019, self.REGIMENES, partes)
            if con_e6:
                e.anual(2019, Linea.E6, self.E6)
        return _anio_simple(F0, sin=(Linea.E3P,), extra=extra)

    def test_p21_parte_menos4_en_anio_utc(self):
        """§8.21 [Enmienda 3, E3-2, R], la versión unitaria (la integral, con datos fabricados, es
        test_orquestacion.test_p21_parte_menos4_en_anio_utc):
        - con una parte, R0 es informativo y no es compatible con F(0): E3p anual no apoya a F(0) (residual);
        - sin E6, el año queda insuficiente («apoyo») y ningún mes recibe regla;
        - con E6, el año se confirma F(0) con E4p y E6, y marzo queda sin regla;
        - dos partes dejan el año discrepante, con o sin E6.
        Con la lectura anterior (por H, R-52 [D]) R0 no contaba para F(0), E3p anual era compatible y el año se
        confirmaba sin E6 con E3p y E4p: la prueba falla con esa lectura."""
        meses = _meses(_meses_de([2019]))
        d = self._anio(self.UNA, con_e6=False)
        self.assertEqual((d.veredicto, d.motivo), (Veredicto.INSUFICIENTE, MotivoAnio.APOYO))
        self.assertNotIn("E3p", d.lineas_apoyo)
        self.assertEqual(d.K, (F0,))
        self.assertEqual(decision.rachas([d], meses, frozenset(), U).meses_con_regla, {})
        d6 = self._anio(self.UNA, con_e6=True)
        self.assertEqual((d6.veredicto, d6.clase_confirmada, d6.lineas_apoyo),
                         (Veredicto.CONFIRMADO, F0, ("E4p", "E6")))
        self.assertEqual(d6.partes_discordantes, ("2019-03-1",))
        con_regla = decision.rachas([d6], meses, frozenset(), U).meses_con_regla
        self.assertNotIn("2019-03", con_regla)
        self.assertEqual(sorted(con_regla), [f"2019-{m:02d}" for m in DOCE if m != 3])
        for con_e6 in (False, True):
            dos = self._anio(self.DOS, con_e6=con_e6)
            self.assertEqual((dos.veredicto, dos.motivo), (Veredicto.DISCREPANTE, MotivoAnio.LINEAS_EN_CONFLICTO),
                             con_e6)
            self.assertIn("E3p", dos.excluidas[F0])
        # La causa es la de §4.3.4 con R: F(0) queda residual en E3p anual, no incompatible.
        e3p = lineas_fisicas.e3p_anual(_e3p_como_lineas_fisicas(_Estados(), 2019, self.REGIMENES, self.UNA).tabla(),
                                       tabla_vacia(ESQUEMA_ESTADOS), True)
        fila = e3p[e3p["H"] == F0].iloc[0]
        self.assertEqual((fila["estado"], fila["motivo"]), (str(S), str(MotivoSinInfo.RESIDUAL)))


def _perfil_e3p_sin(est, meses_fuera):
    """E3p del perfil F(0) sin partes en ``meses_fuera`` (las pone la prueba)."""
    regimenes, partes, _ = PERFILES[F0][Linea.E3P]
    est.e3p(2019, regimenes, partes, meses=[m for m in DOCE if m not in meses_fuera])


def _sin_fina(est):
    """E3p del perfil F(−4) sin la regla fina."""
    regimenes, partes, _ = PERFILES[F4][Linea.E3P]
    est.e3p(2019, regimenes, partes)


# ---------------------------------------------------------------------------------------------
def _dec(anio, veredicto, clase=None, *, meses_apoyo=None, reglas_vencidas=False, discordantes=(), codigo=COD):
    confirmado = veredicto == Veredicto.CONFIRMADO
    return DecisionAnio(codigo=codigo, anio=anio, P=P_CONT, clases=(F0, F3, F4, CS), excluidas={},
                        K=(clase,) if clase else (), veredicto=veredicto, clase_confirmada=clase if confirmado else None,
                        meses_con_apoyo=tuple(meses_apoyo if meses_apoyo is not None else _meses_de([anio]))
                        if confirmado else (),
                        meses_con_datos=tuple(_meses_de([anio])), partes_discordantes=tuple(discordantes),
                        reglas_vencidas=reglas_vencidas)


def _serie(tramos):
    """tramos: [(desde, hasta, veredicto, clase)] → decisiones año a año."""
    return [_dec(a, v, c) for desde, hasta, v, c in tramos for a in range(desde, hasta + 1)]


CONF, DISC, INSUF = Veredicto.CONFIRMADO, Veredicto.DISCREPANTE, Veredicto.INSUFICIENTE


class PruebasRachas(_ConE3pSimulada):
    def test_p20_cambio_2018_dos_rachas_y_cuarentena(self):
        """Unitaria sobre decisiones hechas a mano: 2018 discrepante, dos rachas y cuarentena."""
        decs = _serie([(2010, 2017, CONF, F4), (2018, 2018, DISC, None), (2019, 2022, CONF, F0)])
        r = decision.rachas(decs, _meses(_meses_de(range(2010, 2023))), frozenset(), U)
        validar_esquema(r.rachas, ESQUEMA_RACHAS, nombre="rachas")
        self.assertEqual(r.rachas[["anio_desde", "anio_hasta", "clase", "aceptada"]].values.tolist(),
                         [[2010, 2017, F4, True], [2019, 2022, F0, True]])
        self.assertEqual(r.cambios, [(2017, 2019)])
        self.assertEqual(r.cuarentena, frozenset({"2017-12", "2019-01"}))
        self.assertFalse(r.inestable)
        self.assertEqual(len(r.meses_con_regla), 13 * 12 - 12 - 2)
        self.assertEqual((r.meses_con_regla["2017-11"], r.meses_con_regla["2019-02"]), (F4, F0))
        self.assertFalse(any(m.startswith("2018") for m in r.meses_con_regla))
        self.assertEqual([d.veredicto for d in r.decisiones], [d.veredicto for d in decs])

    def test_p20_cambio_2018_desde_los_estados(self):
        """El mismo cambio desde tablas de estados: F(−4) 2016-2017, el cambio el 2018-07-01, F(0) 2019-2020."""
        est = _Estados()
        for anio, reloj in ((2016, F4), (2017, F4), (2018, "2018"), (2019, F0), (2020, F0)):
            _perfil(est, anio, reloj)
        ev = _evidencia(est, meses=_meses_de(range(2016, 2021)))
        decs = [_decidir(ev, a, _clases(a)) for a in range(2016, 2021)]
        self.assertEqual([d.veredicto for d in decs], [CONF, CONF, DISC, CONF, CONF])
        self.assertEqual(decs[2].motivo, MotivoAnio.LINEAS_EN_CONFLICTO)
        r = decision.rachas(decs, ev.meses, frozenset(), U)
        self.assertEqual(r.rachas["clase"].tolist(), [F4, F0])
        self.assertEqual(r.cambios, [(2017, 2019)])
        self.assertEqual(r.cuarentena, frozenset({"2017-12", "2019-01"}))
        self.assertEqual(len(r.meses_con_regla), 4 * 12 - 2)

    def test_rachas_por_interseccion_2015(self):
        """2014 C(Santiago), 2015 {F(−3), C(Santiago)}, 2016 C(Santiago): una racha."""
        est = _Estados()
        for anio, reloj in ((2014, CS), (2015, "2015"), (2016, CS)):
            _perfil(est, anio, reloj)
        ev = _evidencia(est, meses=_meses_de(range(2014, 2017)))
        clases = {2014: _clases(2014), 2015: _clases(2015, UN_REGIMEN), 2016: _clases(2016)}
        decs = [_decidir(ev, a, clases[a]) for a in range(2014, 2017)]
        self.assertEqual([d.clase_confirmada for d in decs], [CS, f"{F3}|{CS}", CS])
        r = decision.rachas(decs, ev.meses, frozenset(), U)
        self.assertEqual(r.rachas[["anio_desde", "anio_hasta", "clase", "n_confirmados"]].values.tolist(),
                         [[2014, 2016, CS, 3]])
        self.assertEqual(r.cambios, [])
        self.assertEqual(r.meses_con_regla["2015-06"], f"{F3}|{CS}")
        self.assertEqual(len(r.meses_con_regla), 36)
        # La intersección es acumulada: F(−3) 2014, el 2015 fusionado y C(Santiago) 2016 son dos rachas.
        decs = [_dec(2014, CONF, F3), _dec(2015, CONF, f"{F3}|{CS}"), _dec(2016, CONF, CS)]
        r = decision.rachas(decs, ev.meses, frozenset(), U)
        self.assertEqual(r.rachas[["anio_desde", "anio_hasta", "clase", "aceptada"]].values.tolist(),
                         [[2014, 2015, F3, True], [2016, 2016, CS, False]])
        self.assertEqual(r.cambios, [(2015, 2016)])
        self.assertEqual(r.decisiones[2].motivo, MotivoAnio.CAMBIO_SIN_RESPALDO)

    def test_anios_sin_datos_no_cortan(self):
        """Un año sin datos no corta la racha; uno insuficiente sí (sin cambio si la clase sigue)."""
        decs = _serie([(2010, 2011, CONF, F0), (2012, 2012, Veredicto.SIN_DATOS, None), (2013, 2014, CONF, F0)])
        r = decision.rachas(decs, _meses(_meses_de([2010, 2011, 2013, 2014])), frozenset(), U)
        self.assertEqual(r.rachas[["anio_desde", "anio_hasta", "n_confirmados"]].values.tolist(), [[2010, 2014, 4]])
        decs = _serie([(2010, 2011, CONF, F0), (2012, 2012, INSUF, None), (2013, 2014, CONF, F0)])
        r = decision.rachas(decs, _meses(_meses_de(range(2010, 2015))), frozenset(), U)
        self.assertEqual(len(r.rachas), 2)
        self.assertEqual(r.cambios, [])
        self.assertEqual(r.cuarentena, frozenset())

    def test_a6_corta_la_racha_como_insuficiente(self):
        """R-47: un año sin confirmar por A6 corta la racha."""
        decs = _serie([(2010, 2012, CONF, F0), (2014, 2016, CONF, F4)])
        decs.insert(3, replace(_dec(2013, Veredicto.SIN_CONFIRMAR), motivo=MotivoAnio.DOCUMENTAL_A6))
        r = decision.rachas(decs, _meses(_meses_de(range(2010, 2017))), frozenset(), U)
        self.assertEqual(r.rachas["clase"].tolist(), [F0, F4])
        self.assertEqual(r.cambios, [(2012, 2014)])
        self.assertEqual(r.cuarentena, frozenset({"2012-12", "2014-01"}))
        self.assertEqual(r.decisiones[3].motivo, MotivoAnio.DOCUMENTAL_A6)

    def test_inestable_por_discrepantes_o_regreso(self):
        """≥ 3 y > 20 %; H1 → H2 → H1; ≥ 3 relojes."""
        def con_discrepantes(n_anios, discrepantes):
            decs = [_dec(a, DISC if a in discrepantes else CONF, None if a in discrepantes else F0)
                    for a in range(2000, 2000 + n_anios)]
            return decision.rachas(decs, _meses(_meses_de(range(2000, 2000 + n_anios))), frozenset(), U)
        r = con_discrepantes(14, {2003, 2007, 2011})
        self.assertTrue(r.inestable)                                    # 3 de 14 = 21 %
        self.assertTrue(all(d.veredicto != CONF for d in r.decisiones))
        self.assertEqual({d.motivo for d in r.decisiones if d.anio not in {2003, 2007, 2011}}, {MotivoAnio.INESTABLE})
        self.assertEqual(r.meses_con_regla, {})
        self.assertFalse(r.rachas["aceptada"].any())
        self.assertFalse(con_discrepantes(15, {2003, 2007, 2011}).inestable)   # 3 de 15 = 20 %, no «más de»
        self.assertFalse(con_discrepantes(5, {2001, 2003}).inestable)          # menos de 3
        meses = _meses(_meses_de(range(2000, 2012)))
        r = decision.rachas(_serie([(2000, 2003, CONF, F0), (2004, 2007, CONF, F4), (2008, 2011, CONF, F0)]), meses,
                            frozenset(), U)
        self.assertTrue(r.inestable)
        self.assertIn("vuelve a un reloj anterior", r.motivos_inestable)
        r = decision.rachas(_serie([(2000, 2003, CONF, F0), (2004, 2007, CONF, F4), (2008, 2011, CONF, CS)]), meses,
                            frozenset(), U)
        self.assertTrue(r.inestable)
        self.assertIn("3 relojes distintos", r.motivos_inestable)
        # El mismo reloj a ambos lados de un discrepante no es un cambio ni un regreso.
        r = decision.rachas(_serie([(2000, 2005, CONF, F0), (2006, 2006, DISC, None), (2007, 2011, CONF, F0)]), meses,
                            frozenset(), U)
        self.assertFalse(r.inestable)
        self.assertEqual((len(r.rachas), r.cambios), (2, []))
        self.assertEqual(r.cuarentena, frozenset({"2005-12", "2007-01"}))

    def test_cambio_sin_respaldo(self):
        """Una racha de un año junto a un cambio queda sin confirmar; sin cambio, se acepta."""
        meses = _meses(_meses_de(range(2010, 2016)))
        r = decision.rachas(_serie([(2010, 2014, CONF, F4), (2015, 2015, CONF, F0)]), meses, frozenset(), U)
        self.assertEqual(r.rachas["aceptada"].tolist(), [True, False])
        self.assertEqual(r.rachas["motivo"].tolist()[1], "cambio_sin_respaldo")
        self.assertEqual((r.decisiones[-1].veredicto, r.decisiones[-1].motivo),
                         (Veredicto.SIN_CONFIRMAR, MotivoAnio.CAMBIO_SIN_RESPALDO))
        self.assertFalse(any(m.startswith("2015") for m in r.meses_con_regla))
        self.assertEqual(r.cuarentena, frozenset({"2014-12", "2015-01"}))
        r = decision.rachas([_dec(2015, CONF, F0)], meses, frozenset(), U)
        self.assertTrue(r.rachas["aceptada"].all())
        self.assertEqual(len(r.meses_con_regla), 12)

    def test_mes_con_regla_cinco_condiciones(self):
        """Confirmado, racha aceptada, sin cuarentena, sin parte discordante, ≤ 6 meses de apoyo propio."""
        decs = [_dec(2018, DISC), _dec(2019, CONF, F0, meses_apoyo=["2019-02"], discordantes=["2019-03-1"])]
        meses = _meses(_meses_de([2018, 2019]), fuera=("2019-05",))
        r = decision.rachas(decs, meses, frozenset({"2019-07-2"}), U)
        self.assertEqual(r.cuarentena, frozenset({"2017-12", "2019-01"} & set(_meses_de([2018, 2019]))))
        # 2019-01: cuarentena; 03 y 07: discordantes; 05: sin artefacto evaluado; 09-12: a más de 6 meses de 02.
        self.assertEqual(sorted(r.meses_con_regla), ["2019-02", "2019-04", "2019-06", "2019-08"])
        self.assertEqual(set(r.meses_con_regla.values()), {F0})
        # No se presta evidencia entre años: sin apoyo propio en el año, ningún mes recibe regla.
        r = decision.rachas([_dec(2019, CONF, F0, meses_apoyo=[])], meses, frozenset(), U)
        self.assertEqual(r.meses_con_regla, {})

    def test_rachas_validaciones(self):
        """Una sola estación, años sin repetir; no modifica las decisiones de entrada."""
        meses = _meses(_meses_de([2019]))
        with self.assertRaises(ValueError):
            decision.rachas([_dec(2019, CONF, F0), _dec(2019, CONF, F0)], meses, frozenset(), U)
        with self.assertRaises(ValueError):
            decision.rachas([_dec(2019, CONF, F0), _dec(2020, CONF, F0, codigo="330021")], meses, frozenset(), U)
        decs = _serie([(2010, 2014, CONF, F4), (2015, 2015, CONF, F0)])
        decision.rachas(decs, meses, frozenset(), U)
        self.assertEqual(decs[-1].veredicto, CONF)
        vacio = decision.rachas([], meses, frozenset(), U)
        validar_esquema(vacio.rachas, ESQUEMA_RACHAS, nombre="rachas")

    def test_p08_diagnostico_reglas_vencidas(self):
        """K = {Cv}: marca y no cuenta para la inestabilidad (E1-4 de la Enmienda 1)."""
        def estados_cv(*, cv_excluida=False, anomalo=False):
            est = _Estados()
            est.anual(2012, Linea.E1A, {F0: S, F3: S, F4: S, CS: I, "Cv(Santiago)": I if cv_excluida else C})
            est.anual(2012, Linea.E2, {F0: I, F3: I, F4: I, CS: C, "Cv(Santiago)": C}, anomalo=anomalo)
            return est.tabla()
        disc = replace(_dec(2012, DISC), clases=(F0, F3, F4, CS))
        self.assertTrue(decision.marca_reglas_vencidas(disc, estados_cv(), U))
        self.assertFalse(decision.marca_reglas_vencidas(disc, estados_cv(cv_excluida=True), U))
        self.assertFalse(decision.marca_reglas_vencidas(disc, estados_cv(anomalo=True), U))
        self.assertFalse(decision.marca_reglas_vencidas(_dec(2012, CONF, CS), estados_cv(), U))
        sin_cv = _Estados().anual(2012, Linea.E2, {F0: I, F3: I, F4: I, CS: C}).tabla()
        self.assertFalse(decision.marca_reglas_vencidas(disc, sin_cv, U))
        g_version = replace(disc, guardas={"G-version": "falla"})
        self.assertFalse(decision.marca_reglas_vencidas(g_version, estados_cv(), U))
        # Tres discrepantes en 14 años: inestable sin la marca, estable si uno la lleva.
        decs = [_dec(a, DISC if a in (2003, 2007, 2011) else CONF, None if a in (2003, 2007, 2011) else F0)
                for a in range(2000, 2014)]
        meses = _meses(_meses_de(range(2000, 2014)))
        self.assertTrue(decision.rachas(decs, meses, frozenset(), U).inestable)
        decs[7] = replace(decs[7], reglas_vencidas=True)
        r = decision.rachas(decs, meses, frozenset(), U)
        self.assertFalse(r.inestable)
        self.assertEqual(r.decisiones[7].veredicto, DISC)                        # sigue discrepante y sin regla
        self.assertTrue({"2006-12", "2008-01"} <= r.cuarentena)

    def test_enmienda_3_patron_de_reglas_vencidas_deja_la_estacion_inestable(self):
        """Enmienda 3, E3-2 (opción A′): §5.3, punto 1, tercera condición. Una racha F(−4) sin
        discrepantes, que sola es estable, queda inestable con el patrón de regla vencida (motivo «civil
        con reglas vencidas») y sus años confirmados quedan sin confirmar y sin meses con regla."""
        decs = _serie([(2011, 2019, CONF, F4)])
        meses = _meses(_meses_de(range(2011, 2020)))
        sin = decision.rachas(decs, meses, frozenset(), U)
        self.assertFalse(sin.inestable)
        self.assertEqual(sin.motivos_inestable, ())
        con = decision.rachas(decs, meses, frozenset(), U, patron_regla_vencida=True)
        self.assertTrue(con.inestable)
        self.assertEqual(con.motivos_inestable, (decision.MOTIVO_INESTABLE_REGLAS_VENCIDAS,))
        self.assertEqual(decision.MOTIVO_INESTABLE_REGLAS_VENCIDAS, "civil con reglas vencidas")
        self.assertEqual({d.veredicto for d in con.decisiones}, {Veredicto.SIN_CONFIRMAR})
        self.assertEqual({d.motivo for d in con.decisiones}, {MotivoAnio.INESTABLE})
        self.assertEqual(con.meses_con_regla, {})
        self.assertFalse(con.rachas["aceptada"].any())
        # Con otro motivo, los dos se informan.
        mixta = _serie([(2011, 2013, CONF, F4), (2014, 2016, CONF, F0), (2017, 2019, CONF, F4)])
        r = decision.rachas(mixta, meses, frozenset(), U, patron_regla_vencida=True)
        self.assertEqual(r.motivos_inestable, ("vuelve a un reloj anterior", decision.MOTIVO_INESTABLE_REGLAS_VENCIDAS))

    def test_muestra_de_expedientes_de_control(self):
        """20 con la semilla sobre la lista ordenada; con menos, todas."""
        semilla, n = U.f("SEMILLA"), constantes.valor("EXPEDIENTES_CONTROL_N")
        codigos = [f"{330000 + 7 * i:06d}" for i in range(45, 0, -1)] + ["330007"]
        muestra = decision.muestra_expedientes_control(codigos, semilla, n)
        ordenados = sorted(set(codigos))
        esperada = np.random.Generator(np.random.PCG64(semilla)).choice(np.array(ordenados), size=n, replace=False)
        self.assertEqual(muestra, esperada.tolist())
        self.assertEqual(len(set(muestra)), n)
        self.assertEqual(decision.muestra_expedientes_control(codigos, semilla, n),
                         decision.muestra_expedientes_control(list(reversed(codigos)), semilla, n))
        self.assertEqual(decision.muestra_expedientes_control(codigos[:5], semilla, n), sorted(codigos[:5]))
        with self.assertRaises(ValueError):
            decision.muestra_expedientes_control(codigos, semilla, -1)


if __name__ == "__main__":
    unittest.main()
