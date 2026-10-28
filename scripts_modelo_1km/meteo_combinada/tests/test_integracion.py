"""Pruebas de integración entre los módulos de las olas 2 y 3 (acuerdos A1 a A16; hitos 1 y 2 de §6 del diseño).

Dueño: I0 (coordinador). Cada módulo prueba lo suyo con entradas hechas a mano; aquí se encadena la salida real de un
módulo con la entrada real del siguiente, como lo hará ``orquestacion`` (I20), para que un desajuste de interfaz
(nombres de columnas, tipos, unidades, convención de meses o de horas) no espere a la ola 5:
- A8 → A7 → A6: ``estaticas_nasadem.info_estaciones`` → ``politicas.tramos_de_lectura`` y ``politicas_de_lectura``;
- A4 → A5: ``homogeneidad.k4`` → ``politicas.politicas_efectivas``;
- A1 y A2 → A4: ``fondo_era5l.tabla_puntos`` y ``en_horas`` → ``homogeneidad.k4``;
- A9: ``estaticas_nasadem.nasadem_en_pixeles`` → ``fondo_era5l.z_e5l``;
- A11 (TIP-12, D43-D46): ``sintetico.tablas_metricas``, tal como sale, → ``tipos.EntradasDecision`` →
  ``decision.compuertas`` y ``decidir_combinacion`` → ``decision_json`` → ``ceguera.vigilar_salida``, en todos los
  casos de la regla, sin ningún rodeo ni omisión;
- hito 1 (ola 3): una estación sintética de punta a punta. Artefactos del descargador fijado (cliente falso) →
  política de RELOJ y registro de C5 sintéticos (``politicas.leer_registro_c5`` y ``leer_politica_reloj``) →
  ``estaticas_nasadem.info_estaciones`` → políticas de lectura → ``qc_dmc_meteo.normalizar_artefacto`` (el validador
  de RELOJ y ``cargar_dmc`` reales) → ``qc_estacion`` (envoltorio, K4, retirada y marca 14) → ``tabla_ancha`` →
  conteos, alarmas y ``resumen_qc`` (guarda de su clase) → RR06 por el píxel enlazado → residuos (A3) →
  ``candidatos.residuos_estacion``;
- hito 2 (ola 3): una red de 30 estaciones, con A, B, AB y C reales en P1 y P2 y una evaluación completa de lo
  ambiental de p. ``qc_estacion`` → residuos → ``tipos.DatosCompetencia`` → ``candidatos.seleccionar`` (con el
  objetivo armado con ``validacion``) y ``predecir_prueba`` → ``fondo_era5l.producto_desde`` →
  ``validacion.evaluacion``, ``tabla_evaluaciones``, ``bandas_de_pliegues``, π, ``estratos``, ``remuestreo``,
  ``tabla_descriptivos``, ``tabla_bandas`` y ``replica_n`` → ``decision.decidir_combinacion`` y ``decision_json``,
  con las guardas de cada clase de salida.
Lecturas de las pruebas (INT-n; revisión independiente tras el cierre de la ola 2):
- INT-1. **Las réplicas sintéticas separan D46 del ganador fijo** (hallazgo 1). La prueba de A11 sólo distingue D46
  (MC-34: el ganador de cada réplica, dentro del conjunto de la decisión) del ganador fijo si en algún caso hay réplicas
  cuyo ganador no es el de la decisión. Eso depende del ruido de ``sintetico._replicas``, que ninguna prueba vigilaba:
  con réplicas sin ruido la suite seguía en verde. Se exige aquí que el intervalo de D46, contado a mano, difiera del
  del ganador fijo en algún caso, y en particular en «empate» (S de A igual al de AB: con cualquier ruido, el ganador de
  la réplica alterna). No fija el valor del ruido (es de I5).
- INT-2. **Casos sin filas de macrozona, declarados hasta A13** (hallazgo 2). Mientras no se cumpla A13 (primero I5 e
  I14, después I10), ``decision`` acepta un grupo sin ninguna fila de macrozona (DEC-20) y MZ no rige sin aviso. Los
  casos de ``tablas_metricas`` que hoy llegan así quedan en ``_SIN_FILAS_DE_MZ_HASTA_A13`` (la familia «agu»); otro
  caso así falla, y en los demás cada variable de MZ del grupo debe traer sus filas y ``compuertas`` debe evaluar MZ
  (rija o no, con su motivo) para todo E0. Cuando I5 sume las macrozonas a la familia «agu», la prueba falla hasta que
  el conjunto quede vacío; con I10 exigiendo las cinco, se exige aquí ``tipos.MACROZONAS`` en cada variable de MZ.
Lecturas de los hitos 1 y 2 (cierre de la ola 3; van al addendum de M1):
- INT-3. **La tabla larga a escala.** El hito 2 no pasa por el descargador: 30 estaciones × 2 años son 720 artefactos y
  varios minutos. Su tabla larga la arma ``_larga_vectorizada`` (columnas ``tipos.COLUMNAS_LARGA_DMC`` e
  ``id_artefacto``), que el hito 1 compara bit a bit con la salida real de ``cargar_dmc`` de la misma estación (con sus
  políticas de lectura y el validador de RELOJ), y cuyas tablas anchas también salen iguales. Cubre lo que usa el
  hito 2: mediciones instantáneas con número, reloj y coordenadas confirmados, RR06 vacío o «s/p».
- INT-4. **Residuos desde la tabla ancha (A3), como lo hará I20.** La observación es Ts, ``td_final``, ``u_final``,
  ``v_final`` y QFE, con NaN donde ``valido_*`` es falso; el fondo, ``fondo_era5l.en_horas`` en las horas de la tabla;
  después ``fondo_era5l.residuos`` y ``candidatos.residuos_estacion``.
- INT-5. **El objetivo de la selección (PED-3; P-CAN-7 abierta).** Lo arma quien llama con ``validacion``: MSE_e =
  sse/n de cada estación de prueba interna, su banda con ``particiones.distancia_entrenamiento_km`` en el
  entrenamiento de su interno (estaciones con ≥ MIN_HORAS horas válidas de la variable) y ``validacion.bandas``, y un
  solo S (``validacion.puntaje``) sobre las estaciones de prueba de todos los internos, con el π del uso. Es la
  propuesta de P-CAN-7, que rige mientras no haya respuesta.
- INT-6. **Horas emparejadas comunes (VAL-15).** En cada evaluación entran las horas con observación válida y producto
  finito en todos los candidatos del uso que predicen en esa estación; la fracción sin soporte de A, B y AB se mide
  en esas horas. Una estación fuera de la grilla (D34) no tiene C: sus horas son las de A, B y AB, y ``validacion``
  la descarta y la cuenta. El texto no fija las horas comunes: es la pregunta P76 de COORDINACION_M1.md.
- INT-7. **El producto** es ``fondo_era5l.producto_desde`` con la R de ``predecir_prueba`` (p = p_F·exp(R_p), §4.1),
  y la presión se evalúa en hPa (§5.2).
- INT-8. **Lo simulado en el hito 2.** El fondo es analítico (``fondo_era5l.tabla_puntos``), no ``campos_fondo``; la
  TF (``tendencias``, ola 4) es la de ``sintetico.tablas_metricas("p_sin_ex")``, toda «pasa»; la deriva de S6 no saca a
  nadie de E0; π^pob usa la red activa en todos los años de PI_POB_PERIODO y π^mon ocho monitores sintéticos. Se
  evalúa lo ambiental de p porque es el único (uso, grupo) sin EX: EX exige ≥ EX_MIN_DIAS días válidos (900), y dos
  años dan 730. Lo de T queda probado aparte: A recupera b de T con la cadena real de qc (como S5).
- INT-9. **D46 con más de un candidato en el hito 2** (crítico de la ola 3). En la decisión del hito E1 = {C} y C gana
  cada réplica: ahí el intervalo de ΔS es el mismo con D46 y con el ganador fijo, y la prueba de la decisión no los
  separa. ``test_hito2_intervalo_de_d46_con_mas_de_un_candidato`` decide otra vez con las mismas tablas reales sin las
  filas de macrozona (DEC-20: MZ no rige), con E1 = E0. AB gana algunas réplicas, y el intervalo de D46 difiere del
  del ganador fijo. No es un caso del texto: sólo sirve para que el hito vea D46 con un conjunto de cuatro.
Sólo datos de ``sintetico`` en carpetas temporales o en memoria; ningún dato real. Leen, sin escribir, el código fijado
(descargador, adaptador y ``dmc_features``), la clausura del reloj y los textos anclados de APH; si falta uno o cambió
de huella, la prueba se omite con el motivo y no se da por aprobada. Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
"""
import sys

sys.dont_write_bytecode = True

import dataclasses  # noqa: E402
import gzip  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402
from functools import lru_cache  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import entorno  # noqa: E402,F401  (VAL-3: la base de zonas de tzdata antes de validacion)
from meteo_combinada import estaticas_nasadem as EN  # noqa: E402
from meteo_combinada import ceguera, constantes, decision, fijados, fondo_era5l, homogeneidad, numerico  # noqa: E402
from meteo_combinada import candidatos, particiones, politicas, tipos, umbrales, validacion  # noqa: E402
from meteo_combinada import qc_dmc_meteo as Q  # noqa: E402
from meteo_combinada import sintetico as S  # noqa: E402
from meteo_combinada.tipos import Candidato, Grupo, Marca, Uso  # noqa: E402

_AP = _RAIZ.parent
_APH = _AP.parent / "Air-Pollution-Health-Chile"
_SHA_CATALOGO = "c" * 64
_UTC_MENOS_4 = -240


def _umbrales():
    if not (_APH / umbrales.TEXTO_M0).is_file() or not (_APH / umbrales.TEXTO_VIGENTE).is_file():
        raise unittest.SkipTest("faltan los textos anclados en APH; la prueba no se da por aprobada")
    return umbrales.cargar_m0(_APH)


def _politica_reloj(raiz: Path, reglas: dict) -> dict:
    """La política de RELOJ sintética (SIN-5), leída como dict."""
    evaluados = {c: [hashlib.sha256(c.encode()).hexdigest()] for c in reglas}
    ruta = S.politica_reloj_sintetica(raiz, evaluados, reglas)
    return json.loads(ruta.read_text(encoding="utf-8"))


def _tramo_reloj(desde: str, hasta: str) -> dict:
    return {"tramo": "1.1", "valid_from": desde, "valid_to": hasta, "minutos": _UTC_MENOS_4, "veredicto": "F(-4)"}


def _meses(desde: int, hasta: int) -> set:
    return {(a, m) for a in range(desde, hasta + 1) for m in range(1, 13)}


def _lectura(pol, info, U, meses):
    tramos = politicas.tramos_de_lectura(pol, info.codigo, meses, politicas.marcas_g(pol, info.codigo), info=info,
                                         k2=frozenset())
    return politicas.politicas_de_lectura(pol, info, tramos, U, sha_protocolo=U.sha256_texto_vigente,
                                          sha_catalogo=_SHA_CATALOGO)


def _centro_de_celda(lat: float, lon: float) -> tuple[float, float]:
    """El centro de la celda de 0,01° que contiene el punto (bordes oeste y sur cerrados, NAS-5)."""
    return math.floor(lat * 100) / 100 + 0.005, math.floor(lon * 100) / 100 + 0.005


def _info_a_mano(codigo: str, z: float) -> tipos.InfoEstacion:
    nan = math.nan
    return tipos.InfoEstacion(
        codigo=codigo, nombre=codigo, conjunto="N", macrozona="centro", grupo=tipos.id_grupo([codigo]), omm=None,
        tipo=None, propietario=None, lat_txt="-33.45", lon_txt="-70.66", alt_txt=str(z), lat=-33.45, lon=-70.66,
        z_cat=z, rho_km=0.1, k3_pasa=True, z_s=z, z_s_fuente="catalogo", celda=None, utm_e=nan, utm_n=nan, bloque="",
        pix0=-1, pix1=-1, pix2=-1, pix3=-1, w0=nan, w1=nan, w2=nan, w3=nan, respaldo_16km=False, sin_fondo=True,
        excluida=False, motivo=None)


class PruebasIntegracionOla2(unittest.TestCase):
    def test_info_estaciones_de_m2a_en_las_politicas(self):
        """A8 → A7 → A6: la InfoEstacion que arma estaticas_nasadem entra tal cual a politicas. Con z_cat que pasa K3,
        QFE va de p_std(z_s) + QQFE_BAJO a p_std(z_s) + QQFE_ALTO; sin z_cat, coordenadas confirmadas y QFE sin
        regla; con K3 fallida, coordenadas sin confirmar («k3»). El JSON va y vuelve exacto."""
        U = _umbrales()
        oeste, norte = -70.70, -33.40
        with tempfile.TemporaryDirectory() as tmp:
            ruta = S.tesela_nasadem(Path(tmp) / "plano.tif", lambda la, lo: np.full(np.shape(la), 1000.0),
                                    oeste=oeste, norte=norte, filas=120, columnas=120)
            tesela = EN.leer_tesela(ruta, hashlib.sha256(ruta.read_bytes()).hexdigest())
            puntos = {"330001": (-33.412, -70.688, "1000"), "330002": (-33.414, -70.684, "s/i"),
                      "330003": (-33.416, -70.682, "1200")}
            catalogo = pd.DataFrame({"codigo": list(puntos), "nombre": [f"Estación {c}" for c in puntos],
                                     "lat_txt": [str(p[0]) for p in puntos.values()],
                                     "lon_txt": [str(p[1]) for p in puntos.values()],
                                     "alt_txt": [p[2] for p in puntos.values()]})
            centros = sorted({_centro_de_celda(p[0], p[1]) for p in puntos.values()})
            celdas = pd.DataFrame({
                "celda": np.arange(81001, 81001 + len(centros), dtype=np.int64), "lat": [c[0] for c in centros],
                "lon": [c[1] for c in centros], "cod_comuna": np.full(len(centros), 13101, np.int32),
                "aoi_id": pd.array(["continente"] * len(centros), dtype="string"),
                "macrozona": pd.array(["centro"] * len(centros), dtype="string"),
                "macrozona_cod": np.full(len(centros), S.MACROZONA_CODIGO["centro"], np.int8)})
            infos = EN.info_estaciones(catalogo, celdas, [tesela], U, macrozona_region=fijados.macrozona_region(_AP),
                                       conjuntos={})
            self.assertEqual({c: (i.k3_pasa, i.z_s_fuente, i.motivo) for c, i in infos.items()},
                             {"330001": (True, "catalogo", None), "330002": (True, "nasadem", None),
                              "330003": (False, "catalogo", tipos.MotivoExclusion.K3.value)})
            self.assertTrue(all(i.macrozona == "centro" and i.celda is not None for i in infos.values()))
            pol = _politica_reloj(Path(tmp) / "reloj", {c: [_tramo_reloj("2019-01-01T00:00:00",
                                                                         "2019-12-31T23:00:00")] for c in puntos})
            for codigo, info in infos.items():
                with self.subTest(codigo=codigo):
                    lectura = _lectura(pol, info, U, _meses(2019, 2019))
                    self.assertEqual(len(lectura), 1)
                    p = lectura[0]
                    self.assertEqual(politicas.de_json(politicas.a_json(lectura)), lectura)
                    coord = p["coordinates"]
                    self.assertEqual(coord["verified"], info.k3_pasa)
                    self.assertEqual((coord["latitude"], coord["longitude"]), (info.lat, info.lon))
                    if codigo == "330001":
                        z_p = float(numerico.p_std(info.z_s))
                        self.assertEqual((p["quality"]["QFE"]["minimum"], p["quality"]["QFE"]["maximum"]),
                                         (z_p + U.a("QQFE_BAJO"), z_p + U.a("QQFE_ALTO")))
                    else:
                        self.assertNotIn("QFE", p["quality"])            # sin z_cat o con K3 fallida (A7, MC-11)
                    if codigo == "330003":
                        self.assertTrue(coord["source"].endswith(" motivo=k3"), coord["source"])

    def test_k4_de_homogeneidad_en_la_politica_efectiva(self):
        """A4 → A5 (MC-53): el ResultadoK4 real de un traslado de 15 m parte la política de lectura en L_k = u_k − 4 h
        y deja sin coordenadas lo anterior al último traslado, con motivo «traslado»."""
        U = _umbrales()
        df = S.series_traslado("traslado", 500.0, semilla=U.a("SEMILLA"), magnitud=15.0)
        r = homogeneidad.k4(df, df["p_F"].to_numpy(), 500.0, U, codigo="330020")
        self.assertIsNotNone(r.ultimo_traslado)
        self.assertTrue(all(type(q.mes) is int for q in r.quiebres))
        with tempfile.TemporaryDirectory() as tmp:
            pol = _politica_reloj(Path(tmp) / "reloj", {"330020": [_tramo_reloj("2012-01-01T00:00:00",
                                                                                "2017-12-31T23:00:00")]})
            lectura = _lectura(pol, _info_a_mano("330020", 500.0), U, _meses(2012, 2017))
        efectivas = politicas.politicas_efectivas(lectura, {"330020": r})
        meses = sorted({q.mes for q in r.quiebres} | {r.ultimo_traslado})
        u = [datetime(2000 + k // 12, k % 12 + 1, 1) for k in meses]
        cortes = [x + timedelta(minutes=_UTC_MENOS_4) for x in u]
        self.assertEqual([p["valid_from"] for p in efectivas],
                         ["2012-01-01T00:00:00", *(c.isoformat() for c in cortes)])
        traslado = datetime(2000 + r.ultimo_traslado // 12, r.ultimo_traslado % 12 + 1, 1)
        for p, t in zip(efectivas, politicas.tramos_de_politicas(efectivas)):
            antes = datetime.fromisoformat(p["valid_to"]) - timedelta(minutes=_UTC_MENOS_4) < traslado
            self.assertEqual(p["coordinates"]["verified"], not antes, p["valid_to"])
            self.assertEqual(t.motivo, "traslado" if antes else None)

    def test_fondo_en_las_horas_de_la_estacion_alimenta_k4(self):
        """A1 y A2 → A4: el fondo guardado en float32 para todas las horas, alineado con las horas con reporte por
        en_horas, da a k4 el mismo resultado que el p_F redondeado a float32 a mano; una hora sin fondo es NaN."""
        U = _umbrales()
        df = S.series_traslado("barometro", 1000.0, semilla=U.a("SEMILLA"), magnitud=1.5)
        h = df["h"].to_numpy()
        todas = np.arange(h.min(), h.max() + 1, dtype=np.int64)
        p_F = np.interp(todas, h, df["p_F"].to_numpy())
        cero = np.zeros(todas.size)
        F = fondo_era5l.tabla_puntos(todas, {"T_F": cero + 10.0, "Td_F": cero, "p_F": p_F, "u_F": cero, "v_F": cero})
        con_reporte = df.iloc[::3].reset_index(drop=True)          # sólo algunas horas tienen reporte
        alineado = fondo_era5l.en_horas(F, con_reporte["h"].to_numpy())["p_F"]
        a_mano = np.interp(con_reporte["h"].to_numpy(), todas, p_F).astype(np.float32).astype(np.float64)
        np.testing.assert_array_equal(alineado, a_mano)
        r = homogeneidad.k4(con_reporte, alineado, 1000.0, U, codigo="330030")
        self.assertEqual(r, homogeneidad.k4(con_reporte, a_mano, 1000.0, U, codigo="330030"))
        self.assertIsNotNone(r.ultimo_barometro)
        self.assertTrue(np.isnan(fondo_era5l.en_horas(F, [int(todas.max()) + 1])["p_F"]).all())

    def test_nasadem_de_los_pixeles_en_z_e5l(self):
        """A9: la tabla de nasadem_en_pixeles entra tal cual a z_e5l; un píxel sin geopotencial toma la media NASADEM
        de su huella (frac = 1 ≥ 95 %), y los demás, el geopotencial."""
        U = _umbrales()
        cat = S.catalogo_pixeles(-33.4, -70.7, 2, 2)              # centros de la grilla global de 0,1°
        z_geo = np.array([800.0, np.nan, 850.0, 900.0])
        with tempfile.TemporaryDirectory() as tmp:
            ruta = S.tesela_nasadem(Path(tmp) / "plano.tif", lambda la, lo: np.full(np.shape(la), 1234.0),
                                    oeste=-70.75, norte=-33.35, filas=1000, columnas=1000)
            tesela = EN.leer_tesela(ruta, hashlib.sha256(ruta.read_bytes()).hexdigest())
            nasadem = EN.nasadem_en_pixeles(cat, [tesela])
            self.assertEqual(list(nasadem.columns), ["pixel_id", "z_nasadem", "frac_nasadem"])
            np.testing.assert_array_equal(nasadem["frac_nasadem"].to_numpy(), np.ones(len(cat)))
            geo = fondo_era5l.leer_geopotencial(S.geopotencial_sintetico(Path(tmp) / "geo", cat,
                                                                         z_geo)["geopotencial"])
            sp = pd.Series(numerico.p_std(np.full(len(cat), 1000.0)), index=cat["pixel_id"].to_numpy(np.int64))
            tabla = fondo_era5l.z_e5l(geo, cat, nasadem, sp, U, validos=cat["pixel_id"])
        por_pixel = tabla.set_index("pixel_id").loc[cat["pixel_id"].to_numpy(np.int64)]
        self.assertEqual(list(por_pixel["caso"]), ["geopotencial", "nasadem", "geopotencial", "geopotencial"])
        self.assertEqual(float(por_pixel["z_e5l"].iloc[1]), 1234.0)


_RUTA_PUNTAJES = "LOCAL/meteo_combinada/v1/validacion/puntajes.parquet"
# §6.2, paso 3: el orden fijo de desempate «A, AB, B, C» (C_est en lo crónico, en el lugar de C), escrito aquí aparte
# de decision y de sintetico.
_DESEMPATE = {"A": 0, "AB": 1, "B": 2, "C": 3, "C_est": 3}


def _percentil_sin_interpolar(x, q: float) -> float:
    """La menor x con F(x) ≥ q (el «inverted_cdf» de DEC-12), contada a mano."""
    orden = sorted(x)
    return orden[max(math.ceil(len(orden) * q), 1) - 1]


def _ic_con_ganador_por_replica(replicas: pd.DataFrame, conjunto, c: str, pct: float) -> tuple[float, float]:
    """D46 (MC-34): en cada réplica gana el de menor S de réplica dentro de ``conjunto`` (el de la decisión), con el
    desempate fijo; ΔS_c,r = S_c,r − S_ganador_r,r y su intervalo percentil sin interpolar."""
    por_replica: dict[int, dict[str, float]] = {}
    for r, cand, s in zip(replicas["replica"], replicas["candidato"], replicas["S"]):
        por_replica.setdefault(int(r), {})[str(cand)] = float(s)
    dif = []
    for r in sorted(por_replica):
        fila = por_replica[r]
        ganador = min(conjunto, key=lambda x: (fila[x], _DESEMPATE[x]))
        dif.append(fila[c] - fila[ganador])
    a = round((1 - pct / 100) / 2, 12)
    return _percentil_sin_interpolar(dif, a), _percentil_sin_interpolar(dif, 1 - a)


def _ganadores_por_replica(replicas: pd.DataFrame, conjunto) -> dict[int, str]:
    """D46: el ganador de cada réplica dentro de ``conjunto``, con el desempate fijo (INT-1)."""
    por_replica: dict[int, dict[str, float]] = {}
    for r, cand, s in zip(replicas["replica"], replicas["candidato"], replicas["S"]):
        por_replica.setdefault(int(r), {})[str(cand)] = float(s)
    return {r: min(conjunto, key=lambda x: (fila[x], _DESEMPATE[x])) for r, fila in sorted(por_replica.items())}


def _ic_con_ganador_fijo(replicas: pd.DataFrame, ganador: str, c: str, pct: float) -> tuple[float, float]:
    """La lectura de la ola 2 que D46 reemplazó: ΔS_c,r = S_c,r − S_ganador,r con el ganador de la decisión en todas
    las réplicas (INT-1). Sólo sirve para comprobar que los casos la distinguen de D46."""
    por_replica: dict[int, dict[str, float]] = {}
    for r, cand, s in zip(replicas["replica"], replicas["candidato"], replicas["S"]):
        por_replica.setdefault(int(r), {})[str(cand)] = float(s)
    dif = [fila[c] - fila[ganador] for _, fila in sorted(por_replica.items())]
    a = round((1 - pct / 100) / 2, 12)
    return _percentil_sin_interpolar(dif, a), _percentil_sin_interpolar(dif, 1 - a)


# INT-2 (A13 pendiente): los casos de tablas_metricas que hoy no traen ninguna fila de macrozona en un grupo donde MZ
# rige por §6.1 («MZ: en cada macrozona con ≥ 10 estaciones evaluables…»). Es la familia «agu» de sintetico. Al cumplirse
# A13 este conjunto queda vacío.
_SIN_FILAS_DE_MZ_HASTA_A13 = frozenset({"agudo_nivel", "falla_ex_hr_media"})


def _casos_de_la_regla() -> list[str]:
    return [c for c in S.CASOS_METRICAS if c != "soporte"]      # «soporte» es de la regla de soporte (I14)


def _macrozonas_por_variable(d: dict) -> dict[str, frozenset]:
    """Variable de MZ del (uso, grupo) (DEC-1) → valores de ``valor_estrato`` de sus filas de macrozona."""
    val = d["validacion"]
    mz = val[(val.estrato == tipos.Estrato.MACROZONA.value).to_numpy(dtype=bool)]
    variables = decision.VARIABLES[(tipos.Uso(d["uso"]), tipos.Grupo(d["grupo"]))].MZ
    return {v: frozenset(mz.valor_estrato[(mz.variable == v).to_numpy(dtype=bool)]) for v in variables}


class PruebasIntegracionDecision(unittest.TestCase):
    def test_replicas_separan_d46_del_ganador_fijo(self):
        """INT-1 (hallazgo 1 de la revisión tras la ola 2): la prueba de A11 compara el intervalo de ΔS con D46 contado
        a mano; sólo separa D46 del ganador fijo si en algún caso hay réplicas cuyo ganador, dentro de
        ``esperado["conjunto"]``, no es el de la decisión, y entonces los dos intervalos difieren. Se exige en algún caso
        y, en particular, en «empate» (S de A igual al de AB). Con réplicas sin ruido (S de réplica = S del caso), el
        ganador de cada réplica es siempre el de la decisión y esta prueba falla."""
        pct = constantes.valor("BOOT_IC_PCT")
        con_otro_ganador, intervalo_distinto = {}, set()
        for caso in _casos_de_la_regla():
            d = S.tablas_metricas(caso)
            e = d["esperado"]
            ganadores = _ganadores_por_replica(d["replicas"], e["conjunto"])
            self.assertTrue(set(ganadores.values()) <= set(e["conjunto"]), caso)
            otros = sum(g != e["ganador"] for g in ganadores.values())
            if otros:
                con_otro_ganador[caso] = otros
            for c in e["e0"]:
                if (_ic_con_ganador_por_replica(d["replicas"], e["conjunto"], c, pct)
                        != _ic_con_ganador_fijo(d["replicas"], e["ganador"], c, pct)):
                    intervalo_distinto.add((caso, c))
        self.assertTrue(con_otro_ganador, "ninguna réplica de ningún caso elige otro ganador: la prueba de A11 ya no "
                                          "separa D46 del ganador fijo")
        self.assertIn("empate", con_otro_ganador)
        self.assertTrue(intervalo_distinto, "en ningún caso el intervalo de D46 difiere del del ganador fijo")
        self.assertIn("empate", {caso for caso, _ in intervalo_distinto})
        self.assertTrue({caso for caso, _ in intervalo_distinto} <= set(con_otro_ganador))

    def test_mz_en_cada_variable_de_mz_hasta_a13(self):
        """INT-2 (hallazgo 2; A13 pendiente): los únicos casos sin filas de macrozona son los de
        ``_SIN_FILAS_DE_MZ_HASTA_A13`` (la familia «agu»), sin filas en ninguna variable de MZ, y en ellos
        ``compuertas`` no trae MZ: así queda a la vista que MZ no rige. En los demás, cada variable de MZ del grupo trae
        sus filas, sólo de macrozonas de ``tipos`` (DEC-19), y ``compuertas`` evalúa MZ (rija o no, con su motivo) en
        cada variable × macrozona para todo E0."""
        if not (_APH / umbrales.TEXTO_M0).is_file():
            self.skipTest("falta el texto anclado en M0; la prueba no se da por aprobada")
        U = umbrales.cargar_m0(_APH)
        sin_filas = set()
        for caso in _casos_de_la_regla():
            with self.subTest(caso=caso):
                d = S.tablas_metricas(caso)
                por_variable = _macrozonas_por_variable(d)
                self.assertTrue(por_variable, caso)                              # §6.1: MZ en todo (uso, grupo)
                vacias = {v for v, zs in por_variable.items() if not zs}
                entradas = tipos.EntradasDecision(tipos.Uso(d["uso"]), tipos.Grupo(d["grupo"]), d["validacion"],
                                                  d["tf"], d["replicas"], d["e0_excluidos"])
                tabla = decision.compuertas(d["uso"], d["grupo"], entradas, U)
                mz = tabla[(tabla.compuerta == tipos.Compuerta.MZ.value).to_numpy(dtype=bool)]
                if vacias:
                    sin_filas.add(caso)
                    self.assertEqual(vacias, set(por_variable), caso)            # DEC-20: o todas o ninguna
                    self.assertEqual(len(mz), 0, caso)
                    continue
                for v, zs in por_variable.items():
                    self.assertTrue(zs <= set(tipos.MACROZONAS) | set(tipos.MACROZONAS_NINGUNA), (v, zs))
                    for z in zs:
                        en = mz[((mz.variable == v) & (mz.ambito == z)).to_numpy(dtype=bool)]
                        self.assertEqual(sorted(en.candidato), sorted(d["esperado"]["e0"]), (v, z))
        self.assertEqual(sin_filas, set(_SIN_FILAS_DE_MZ_HASTA_A13),
                         "A13: si I5 ya sumó las macrozonas a la familia «agu», vaciar _SIN_FILAS_DE_MZ_HASTA_A13 y "
                         "exigir las cinco de tipos.MACROZONAS; si no, un caso nuevo quedó sin filas de MZ")

    def test_tablas_metricas_tal_cual_en_decidir_combinacion(self):
        """A11 (TIP-12) con D43-D46: cada caso de la regla de ``sintetico.tablas_metricas`` entra tal como sale, sin
        ningún cambio, en ``tipos.EntradasDecision`` y en ``decision``. Coinciden con su esperado las compuertas que
        falla cada candidato, E0, E1, el ganador (que sale de ``esperado["conjunto"]``), el S del grupo, ΔS y las notas.
        El intervalo de ΔS sigue D46: ganador por réplica dentro de ese conjunto, contado aquí aparte. ``decision.json``
        va y vuelve por JSON sin NaN y pasa la guarda de su clase (D3). Ningún caso se omite: un desajuste falla."""
        if not (_APH / umbrales.TEXTO_M0).is_file():
            self.skipTest("falta el texto anclado en M0; la prueba no se da por aprobada")
        U = umbrales.cargar_m0(_APH)
        pct = constantes.valor("BOOT_IC_PCT")
        self.assertEqual(S.ORDEN_NOTAS, decision.ORDEN_NOTAS[:len(S.ORDEN_NOTAS)])      # DEC-10, el mismo orden
        casos = [c for c in S.CASOS_METRICAS if c != "soporte"]      # «soporte» es de la regla de soporte (I14)
        self.assertNotIn("uso", S.tablas_metricas("soporte"))
        self.assertGreater(len(casos), 0)
        for caso in casos:
            with self.subTest(caso=caso):
                d = S.tablas_metricas(caso)
                e = d["esperado"]
                entradas = tipos.EntradasDecision(tipos.Uso(d["uso"]), tipos.Grupo(d["grupo"]), d["validacion"],
                                                  d["tf"], d["replicas"], d["e0_excluidos"])
                tipos.validar_esquema(entradas.validacion, tipos.ESQUEMA_VALIDACION_PUB, nombre="validacion")
                tipos.validar_esquema(entradas.tf, tipos.ESQUEMA_TF, nombre="tf")
                tipos.validar_esquema(entradas.replicas, tipos.ESQUEMA_REPLICAS, nombre="replicas")

                tabla = decision.compuertas(d["uso"], d["grupo"], entradas, U)
                fallidas: dict[str, set] = {}
                for c, compuerta, pasa in zip(tabla["candidato"], tabla["compuerta"], tabla["pasa"]):
                    if not bool(pasa):
                        fallidas.setdefault(str(c), set()).add(str(compuerta))
                self.assertEqual(fallidas, {c: set(x) for c, x in e["fallas"].items()})

                r = decision.decidir_combinacion(d["uso"], d["grupo"], entradas, umbrales=U)
                self.assertIsInstance(r, tipos.DecisionGrupo)
                self.assertEqual((r.uso, r.grupo), (entradas.uso, entradas.grupo))
                self.assertEqual((r.e0, r.e1, r.notas), (e["e0"], e["e1"], e["notas"]))
                self.assertEqual(r.S, e["S"])
                self.assertIn(r.ganador, e["conjunto"])
                self.assertEqual(r.ganador, e["ganador"])
                self.assertEqual(r.ganador, min(e["conjunto"], key=lambda c: (e["S"][c], _DESEMPATE[c])))
                self.assertEqual(r.delta_S, {c: e["S"][c] - e["S"][r.ganador] for c in e["e0"]})
                self.assertEqual(set(r.ic_delta_S), set(e["e0"]))
                for c in e["e0"]:
                    self.assertEqual(r.ic_delta_S[c], _ic_con_ganador_por_replica(d["replicas"], e["conjunto"], c, pct),
                                     c)
                self.assertGreaterEqual(r.ic_delta_S[r.ganador][0], 0.0)

                huellas = {_RUTA_PUNTAJES: hashlib.sha256(caso.encode()).hexdigest()}
                registro = decision.decision_json([r], {(d["uso"], d["grupo"]): {}}, huellas)
                self.assertEqual(json.loads(json.dumps(registro, ensure_ascii=False, allow_nan=False)), registro)
                clase = ceguera.clase_de_ruta("decision.json")
                ceguera.vigilar_salida("decision.json", registro, clase=clase)
                # decision_json acepta huellas vacías, pero la guarda no deja escribir un decision.json sin ellas
                # (CEG-15): quien lo escribe (I20) siempre pasa las de sus entradas (§8, «Cadena de huellas»).
                with self.assertRaises(ceguera.SalidaProhibida):
                    ceguera.vigilar_salida("decision.json", decision.decision_json(
                        [r], {(d["uso"], d["grupo"]): {}}, {}), clase=clase)
                x = registro["decisiones"][0]
                self.assertEqual((x["ganador"], x["e0"], x["e1"], x["notas"]),
                                 (e["ganador"], list(e["e0"]), list(e["e1"]), list(e["notas"])))
                self.assertEqual({c: tuple(v) for c, v in x["ic_delta_S"].items()}, dict(r.ic_delta_S))


# ---------------------------------------------------------------------------
# Hitos 1 y 2 de §6 del diseño (cierre de la ola 3): qc_dmc_meteo → candidatos → validacion → decision
# ---------------------------------------------------------------------------
_PORTAL = ("QFE", "QFF", "QNH", "RR06", "Td", "Ts", "relative_humidity", "wind_direction_instant",
           "wind_speed_instant")                    # el orden de las variables de una etiqueta en la tabla larga
_UNIDAD = {"Ts": "degC", "Td": "degC", "relative_humidity": "%", "wind_direction_instant": "degree",
           "wind_speed_instant": "m/s", "QFE": "hPa", "QFF": "hPa", "QNH": "hPa", "RR06": "mm"}
_INSTANTANEAS = ("Ts", "Td", "relative_humidity", "wind_speed_instant", "wind_direction_instant", "QFE", "QFF")
_NUMERO = r"[+-]?\d+(?:[.,]\d+)?"
_NUDO = 1852 / 3600
_COLUMNAS_LARGA = [*tipos.COLUMNAS_LARGA_DMC, "id_artefacto"]
_GRADIENTE = 0.0065                                 # K/m: sólo para fabricar un QFF coherente con QFE (no es del texto)
_CENTINELA_TS = -40.0                               # D11: el ejemplo del centinela de Ts
_LLUVIA_MM_H = 0.1
_PIXEL_LLUVIA = 3601234
_CELDA_H1 = 81001


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _codigo_fijado(prueba):
    """Descargador, adaptador y dmc_features con sus huellas de §9.3; si no, la prueba se omite con el motivo."""
    for ruta, sha in ((_AP / fijados.RUTA_DESCARGADOR, fijados.SHA_DESCARGADOR),
                      (_AP / fijados.RUTA_ADAPTADOR, fijados.SHA_ADAPTADOR),
                      (_AP / fijados.RUTA_DMC_FEATURES, fijados.SHA_DMC_FEATURES)):
        if not ruta.is_file() or _sha(ruta) != sha:
            prueba.skipTest(f"{ruta.name} falta o cambió de huella; no se da por aprobada")
    return fijados.cargar_descargador(_AP), fijados.cargar_adaptador(_AP), fijados.cargar_dmc_features(_AP)


def _validador(prueba):
    """``validar_regla_reloj_dmc`` con la clausura del reloj fijada, la de AP 1da0236 (MC-17, FIJ-1)."""
    esperadas = dict(fijados.HUELLAS_RELOJ)
    try:
        actuales = fijados.huellas_reloj(_AP)
    except (OSError, ValueError) as e:
        prueba.skipTest(f"no se puede leer la clausura del reloj ({e}); no se da por aprobada")
    if actuales != esperadas:
        prueba.skipTest("la clausura del reloj cambió respecto de la fijada (FIJ-1, AP 1da0236); no se da por aprobada")
    return fijados.cargar_validador_reloj(_AP, esperadas, permitir_cargados=True)


def _rango(U, variable: str, z_s: float) -> tuple[float, float]:
    if variable == "QFE":
        p0 = float(numerico.p_std(z_s))
        return p0 + U.a("QQFE_BAJO"), p0 + U.a("QQFE_ALTO")
    _, id_min, id_max, _ = politicas.CALIDAD[variable]
    return U.a(id_min), U.a(id_max)


def _larga_vectorizada(U, codigo: str, etiquetas, columnas: dict, *, z_s: float, minutos: int = _UTC_MENOS_4,
                       id_artefacto=0) -> pd.DataFrame:
    """INT-3: la tabla larga de ``cargar_dmc`` (``_COLUMNAS_LARGA``) de una estación con reloj y coordenadas
    confirmados, una regla de medición para cada instantánea y rangos de ``politicas.CALIDAD`` (QFE sobre p_std(z_s)).
    ``columnas``: variable del portal → valores (números como el portal, NaN o «» vacío; RR06 en texto)."""
    L = pd.DatetimeIndex(etiquetas)
    n = len(L)
    fuente = L.strftime("%Y-%m-%dT%H:%M:%S").to_numpy(dtype=object)
    utc = pd.DatetimeIndex(L - pd.Timedelta(minutes=minutos)).tz_localize("UTC").astype("datetime64[ns, UTC]")
    ida = np.broadcast_to(np.asarray(id_artefacto, dtype=np.int32), (n,))
    partes, listo, usable, valor = [], {}, {}, {}

    def parte(nombre, filas, **campos):
        base = {"station_code": codigo, "timestamp_source": fuente[filas], "timestamp_utc": utc[filas],
                "variable": nombre, "source_qc": None, "clock_verified": True, "coordinates_verified": True,
                "id_artefacto": ida[filas]}
        return pd.DataFrame({**base, **campos})

    todas = np.arange(n)
    for k, v in enumerate(_PORTAL):
        x = columnas.get(v)
        raw = (np.full(n, "", dtype=object) if x is None
               else np.array([S._texto_celda(y, S._FORMATO.get(v)) for y in x], dtype=object))
        es_num = pd.Series(raw, dtype=object).str.fullmatch(_NUMERO).to_numpy(dtype=bool)
        val = np.full(n, np.nan)
        if es_num.any():
            val[es_num] = pd.to_numeric(pd.Series(raw[es_num]).str.replace(",", ".", regex=False)).to_numpy(np.float64)
        if v == "wind_speed_instant":
            val = val * _NUDO
        estado = np.where(raw == "", "empty_source", np.where(es_num, "numeric", "literal_source")).astype(object)
        medida = v != "QNH"                                  # QNH sin regla de medición (POL-6)
        ok = es_num & medida & (v in _INSTANTANEAS)
        if v in _INSTANTANEAS:
            lo, hi = _rango(U, v, z_s)
            dentro = ok & (val >= lo) & (val <= hi)
            razon = np.where(~ok, "semantics_or_value_unavailable",
                             np.where(dentro, "documented_numeric_checks_unknown_source_qc",
                                      tipos.RAZON_FUERA_DE_RANGO)).astype(object)
        else:
            dentro = np.zeros(n, dtype=bool)
            razon = np.full(n, "semantics_or_value_unavailable", dtype=object)
        listo[v], usable[v], valor[v] = ok, dentro, val
        partes.append(parte(v, todas, value=val, unit=_UNIDAD[v], raw=raw, parse_status=estado,
                            measurement_verified=medida, model_ready=ok, usable=dentro, quality_reason=razon,
                            _orden=todas * (len(_PORTAL) + 2) + k))
    vel, rumbo = valor["wind_speed_instant"], valor["wind_direction_instant"]
    con = np.flatnonzero(np.isfinite(vel) & np.isfinite(rumbo))
    ok = listo["wind_speed_instant"][con] & listo["wind_direction_instant"][con]
    ok_qc = ok & usable["wind_speed_instant"][con] & usable["wind_direction_instant"][con]
    angulos = [math.radians(d) for d in rumbo[con]]
    componentes = (("wind_u", [-s * math.sin(a) for s, a in zip(vel[con], angulos)]),
                   ("wind_v", [-s * math.cos(a) for s, a in zip(vel[con], angulos)]))
    for k, (nombre, x) in enumerate(componentes):
        partes.append(parte(nombre, con, value=np.array(x, dtype=np.float64), unit="m/s", raw=None,
                            parse_status="derived", measurement_verified=ok, model_ready=ok, usable=ok_qc,
                            quality_reason=np.where(ok_qc, "derived_from_both_qc_components",
                                                    "derived_component_unavailable").astype(object),
                            _orden=con * (len(_PORTAL) + 2) + len(_PORTAL) + k))
    d = pd.concat(partes, ignore_index=True).sort_values("_orden", kind="stable")
    d = d.drop(columns="_orden").reset_index(drop=True)[_COLUMNAS_LARGA]
    d["value"] = d["value"].astype(np.float64)
    for c in ("clock_verified", "coordinates_verified", "measurement_verified", "model_ready", "usable"):
        d[c] = d[c].astype(bool)
    d["id_artefacto"] = d["id_artefacto"].astype(np.int32)
    return d


def _de_texto(valores, variable: str) -> np.ndarray:
    """El valor que lee el adaptador del texto del portal (float64), para comparar con la tabla ancha."""
    return np.array([float(S._texto_celda(x, S._FORMATO.get(variable))) for x in valores], dtype=np.float64)


def _h_de(etiquetas, minutos: int = _UTC_MENOS_4) -> np.ndarray:
    """La hora UTC (h) de cada etiqueta ingenua con el desfase fijo ``minutos``."""
    u = pd.DatetimeIndex(etiquetas) - pd.Timedelta(minutes=minutos)
    return ((u - pd.Timestamp("2000-01-01")) // pd.Timedelta(hours=1)).to_numpy(np.int64)


def _portal(Ts, p_F, r_p, z_s: float, h: np.ndarray, k: int) -> dict:
    """Los textos de una estación sintética limpia: Ts (°C) al décimo, Td bajo Ts, HR coherente por Magnus, viento sin
    rachas ni ceros, QFE = p_F·exp(r_p) y un QFF coherente con QFE; ninguna regla de §2.4 debería saltar."""
    i = np.arange(h.size)
    hora = h % numerico.PERIODO_DIA_H
    Ts = np.round(np.asarray(Ts, dtype=np.float64), 1)
    deficit = 4.5 + 2.0 * np.cos(2 * np.pi * (hora - 19) / 24) ** 2 + 0.3 * np.sin(i / 3.7 + k)
    Td = np.round(Ts - deficit, 1)
    HR = np.round(numerico.hr_desde(Ts, Td))
    QFE = np.round(np.asarray(p_F, dtype=np.float64) * np.exp(r_p), 1)
    t_media = Ts + constantes.valor("KELVIN") + _GRADIENTE * z_s / 2
    QFF = np.round(QFE * np.exp(constantes.valor("GRAVEDAD") * z_s / (constantes.valor("R_SECO") * t_media)), 1)
    return {"Ts": Ts, "Td": Td, "relative_humidity": HR, "wind_speed_instant": (4 + (i + k) % 9).astype(float),
            "wind_direction_instant": (((37 * i + 7 * k) % 36 + 1) * 10).astype(float), "QFE": QFE, "QFF": QFF}


def _con_valido(ancha: pd.DataFrame, columna: str, valido: str) -> np.ndarray:
    return np.where(ancha[valido].to_numpy(bool), ancha[columna].to_numpy(np.float64), np.nan)


def _residuos_de(codigo: str, ancha: pd.DataFrame, F: pd.DataFrame, U):
    """INT-4: (ESQUEMA_RESIDUOS, ESQUEMA_TRAMOS_HOMOGENEOS) de una estación desde su tabla ancha y su fondo (A1-A3)."""
    h = ancha["h"].to_numpy(np.int64)
    obs = {"T": _con_valido(ancha, "Ts", "valido_T"), "Td": _con_valido(ancha, "td_final", "valido_Td"),
           "u": _con_valido(ancha, "u_final", "valido_viento"), "v": _con_valido(ancha, "v_final", "valido_viento"),
           "QFE": _con_valido(ancha, "QFE", "valido_p")}
    r = fondo_era5l.residuos(obs, fondo_era5l.en_horas(F, h))
    return candidatos.residuos_estacion(codigo, h, {"T": r["r_T"], "Td": r["r_Td"], "u": r["r_u"], "v": r["r_v"],
                                                    "p": r["r_p"]}, U)


def _objetivo_de_validacion(infos, horas_validas: dict, pi: dict, U):
    """INT-5 (PED-3): el objetivo de ``candidatos.seleccionar`` armado con ``validacion``."""
    def objetivo(internos, sumas, *, candidato, variable, uso):
        clave = validacion.HORAS_DE[str(variable)]
        mse, banda = [], []
        for interno in internos:
            por = sumas[interno.id]
            d = particiones.distancia_entrenamiento_km(sorted(por), interno.entrenamiento, infos, horas_validas[clave],
                                                       U)
            for c in sorted(por):
                sse, n = por[c]
                if n > 0:
                    mse.append(sse / n)
                    banda.append(int(validacion.bandas([d[c]], U)[0]))
        if not mse:
            return math.nan
        return validacion.puntaje(np.array(mse), np.array(banda, dtype=np.int64), pi[clave], U)
    return objetivo


class PruebasHito1(unittest.TestCase):
    """Hito 1 de §6 del diseño: una estación sintética de punta a punta (artefacto → política → ``cargar_dmc`` →
    envoltorio → tabla ancha), con la ciencia simulada, y su paso a los residuos de ``candidatos``."""

    @classmethod
    def setUpClass(cls):
        cls.mundo = None

    def _mundo(self):
        """La descarga, la publicación de RELOJ, las políticas y el paso 1, en una carpeta temporal; sólo queda lo
        que está en memoria."""
        if PruebasHito1.mundo is not None:
            return PruebasHito1.mundo
        U = _umbrales()
        descargador, adaptador, dmc_features = _codigo_fijado(self)
        validar = _validador(self)
        L = pd.date_range("2010-01-01T00:00", "2010-03-31T23:00", freq="h")
        h = _h_de(L)
        z = 1000.0
        hora = h % numerico.PERIODO_DIA_H
        T_F = 15 + 6 * np.cos(2 * np.pi * (hora - 19) / 24) + 0.5 * np.sin(h / 53.0)
        p_F = float(numerico.p_std(z)) + 1.0 + 0.8 * np.cos(4 * np.pi * hora / 24) + 0.2 * np.sin(h / 97.0)
        columnas = _portal(T_F + 1.3 + 0.3 * np.sin(np.arange(h.size) / 5.3), p_F, 0.001, z, h, 0)
        centinela = 500
        columnas["Ts"][centinela] = _CENTINELA_TS
        rr06 = np.where(np.isin(hora, (0, 6, 12, 18)), "s/p", "")
        rr06 = np.where((hora == 12) & (np.arange(h.size) % 5 == 0), "2.5", rr06)
        columnas["RR06"] = list(rr06)
        dd = ["270"] * 24
        dd[5] = "990"                                            # el artefacto de 330102 no es normalizable
        estaciones = [S.estacion_sintetica("330101", -33.412, -70.688, z, L, **columnas),
                      S.estacion_sintetica("330102", -33.414, -70.684, z, L[:24], Ts=np.full(24, 15.0) + np.arange(24) * 0.1,
                                           wind_direction_instant=dd, wind_speed_instant=np.full(24, 8))]
        reglas = {"330101": [_tramo_reloj("2010-01-01T00:00:00", "2010-03-31T23:00:00")],
                  "330102": [_tramo_reloj("2010-01-01T00:00:00", "2010-01-01T23:00:00")]}
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            ruta = S.tesela_nasadem(tmp / "plano.tif", lambda la, lo: np.full(np.shape(la), z), oeste=-70.70,
                                    norte=-33.40, filas=120, columnas=120)
            tesela = EN.leer_tesela(ruta, _sha(ruta))
            catalogo = pd.DataFrame({"codigo": ["330101", "330102"], "nombre": ["E1", "E2"],
                                     "lat_txt": ["-33.412", "-33.414"], "lon_txt": ["-70.688", "-70.684"],
                                     "alt_txt": ["1000", "1000"]})
            lat_c, lon_c = _centro_de_celda(-33.412, -70.688)
            celdas = pd.DataFrame({"celda": np.array([_CELDA_H1], dtype=np.int64), "lat": [lat_c], "lon": [lon_c],
                                   "cod_comuna": np.array([13101], np.int32),
                                   "aoi_id": pd.array(["continente"], dtype="string"),
                                   "macrozona": pd.array(["centro"], dtype="string"),
                                   "macrozona_cod": np.array([S.MACROZONA_CODIGO["centro"]], np.int8)})
            infos = EN.info_estaciones(catalogo, celdas, [tesela], U, macrozona_region=fijados.macrozona_region(_AP),
                                       conjuntos={})
            dmc = S.fabricar_descarga(estaciones, tmp / "descarga", descargador, "2010-01-01", "2010-03-31")
            manifiestos = S.manifiestos_de(dmc)
            ruta_politica = S.politica_reloj_sintetica(tmp / "publicacion", S.artefactos_de_descarga(dmc), reglas)
            rutas = S.rutas_politica_sintetica(tmp / "publicacion")
            ap = tmp / "publicacion" / "AP"
            pol, artefactos = politicas.leer_politica_reloj(politicas.leer_registro_c5(rutas["registro"], ap=ap), ap=ap)
            # id_artefacto: el índice en artefactos_evaluados (QC-1; lo da quien llama, I20).
            lista = json.loads(gzip.decompress(rutas["artefactos"].read_bytes()))
            indice = {x["artefacto_sha256"]: k for k, x in enumerate(lista)}
            lecturas, resultados = {}, {}
            for codigo, rutas_m in manifiestos.items():
                evaluados = [m for m in rutas_m if json.loads(m.read_text(encoding="utf-8")).get("artifact_sha256")]
                meses = {tuple(int(x) for x in m.name[:7].split("-")) for m in evaluados}
                lecturas[codigo] = _lectura(pol, infos[codigo], U, meses)
                resultados[codigo] = [Q.normalizar_artefacto(
                    m, lecturas[codigo], adaptador=adaptador, dmc_features=dmc_features,
                    validar_regla=lambda r, s: validar(r, s, politica_ruta=ruta_politica),
                    sha_adaptador=fijados.SHA_ADAPTADOR,
                    id_artefacto=indice[json.loads(m.read_text(encoding="utf-8"))["artifact_sha256"]],
                    artefactos=artefactos) for m in evaluados]
        todas = np.arange(int(h.min()) - 24, int(h.max()) + 1, dtype=np.int64)
        hora_t = todas % numerico.PERIODO_DIA_H
        T_Ft = 15 + 6 * np.cos(2 * np.pi * (hora_t - 19) / 24) + 0.5 * np.sin(todas / 53.0)
        F = fondo_era5l.tabla_puntos(todas, {
            "T_F": T_Ft, "Td_F": T_Ft - 5.0,
            "p_F": float(numerico.p_std(z)) + 1.0 + 0.8 * np.cos(4 * np.pi * hora_t / 24) + 0.2 * np.sin(todas / 97.0),
            "u_F": np.full(todas.size, 1.0), "v_F": np.full(todas.size, -0.5)})
        PruebasHito1.mundo = {"U": U, "L": L, "h": h, "z": z, "columnas": columnas, "centinela": centinela,
                              "infos": infos, "lecturas": lecturas, "resultados": resultados, "lista": lista,
                              "F": F, "todas": todas}
        return PruebasHito1.mundo

    def test_hito1_artefactos_politicas_y_paso_1(self):
        """Paso 1 de §2.1 con el código fijado: ``info_estaciones`` da la estación con K3 y su celda; cada artefacto
        evaluado se normaliza con su índice en ``artefactos_evaluados``; el de DD 990 queda «no normalizable» por los
        datos y su estación no llega al envoltorio (``unir_largas`` lanza ``ValueError``: aviso a I20)."""
        m = self._mundo()
        info = m["infos"]["330101"]
        self.assertEqual((info.k3_pasa, info.excluida, info.celda, info.macrozona, info.z_s_fuente),
                         (True, False, _CELDA_H1, "centro", "catalogo"))
        buenos, malos = m["resultados"]["330101"], m["resultados"]["330102"]
        self.assertEqual([(r.anio, r.mes) for r in buenos], [(2010, 1), (2010, 2), (2010, 3)])
        self.assertTrue(all(r.normalizable and r.reglas_rechazadas == () for r in buenos))
        self.assertEqual(sorted(r.id_artefacto for r in [*buenos, *malos]), list(range(len(m["lista"]))))
        self.assertEqual([(r.normalizable, r.motivo, r.origen) for r in malos],
                         [(False, tipos.MotivoNoNormalizable.DD_FUERA_DE_DOMINIO, tipos.OrigenAborto.DATOS)])
        with self.assertRaises(ValueError):
            Q.unir_largas(malos)
        self.assertEqual([t.id for t in politicas.tramos_de_politicas(m["lecturas"]["330101"])], ["1.1/1"])

    def test_hito1_larga_vectorizada_igual_a_cargar_dmc(self):
        """INT-3: la tabla larga de ``_larga_vectorizada`` es la de ``cargar_dmc`` bit a bit (columnas que lee el
        envoltorio, tipos y valores), y las dos dan la misma tabla ancha."""
        m = self._mundo()
        U, info = m["U"], m["infos"]["330101"]
        real = Q.unir_largas(m["resultados"]["330101"])
        por_mes = {r.mes: r.id_artefacto for r in m["resultados"]["330101"]}
        mano = _larga_vectorizada(U, "330101", m["L"], m["columnas"], z_s=m["z"],
                                  id_artefacto=[por_mes[x.month] for x in m["L"]])
        a = real[_COLUMNAS_LARGA].sort_values(["timestamp_source", "variable"]).reset_index(drop=True)
        b = mano.sort_values(["timestamp_source", "variable"]).reset_index(drop=True)
        self.assertEqual({c: str(a[c].dtype) for c in _COLUMNAS_LARGA}, {c: str(b[c].dtype) for c in _COLUMNAS_LARGA})
        pd.testing.assert_frame_equal(a, b, check_exact=True)
        pols = m["lecturas"]["330101"]
        t_real = Q.tabla_ancha(Q.qc_estacion(real, info, m["F"], U, k2=frozenset(), politicas=pols)[0])
        t_mano = Q.tabla_ancha(Q.qc_estacion(mano, info, m["F"], U, k2=frozenset(), politicas=pols)[0])
        pd.testing.assert_frame_equal(t_real, t_mano, check_exact=True)

    def test_hito1_envoltorio_k4_y_tabla_ancha(self):
        """Pasos 2 a 5 de §2.1: la tabla ancha tiene el esquema, una fila por hora UTC con reloj, los valores de la
        fuente en float32 y el tramo de la política efectiva (TIP-24); el centinela de Ts invalida Ts, Td y HR de su
        fila (D7, D11) y nada más salta; K4 no halla quiebres y la efectiva es la de lectura."""
        m = self._mundo()
        U, info = m["U"], m["infos"]["330101"]
        tabla, k4, efectivas = Q.qc_estacion(Q.unir_largas(m["resultados"]["330101"]), info, m["F"], U, k2=frozenset(),
                                             politicas=m["lecturas"]["330101"])
        ancha = Q.tabla_ancha(tabla)
        tipos.validar_esquema(ancha, tipos.ESQUEMA_QC_ESTACION, nombre="tabla ancha")
        self.assertEqual(ancha.attrs["esquema"], tipos.ESQUEMA_QC_ESTACION.version)
        np.testing.assert_array_equal(ancha["h"].to_numpy(np.int64), m["h"])
        self.assertEqual((k4.quiebres, k4.ultimo_traslado, k4.ultimo_barometro, k4.sin_prueba), ((), None, None, False))
        self.assertEqual(efectivas, m["lecturas"]["330101"])
        self.assertEqual(set(ancha["tramo"]), {t.id for t in politicas.tramos_marca_14(efectivas, "330101")})
        for col in ("Ts", "QFE", "QFF"):
            np.testing.assert_array_equal(ancha[col].to_numpy(), _de_texto(m["columnas"][col], col).astype(np.float32))
        c = m["centinela"]
        bits = {col: ancha[col].to_numpy(np.uint32) for col in ancha.columns if col.startswith("marcas_")}
        self.assertTrue(bits["marcas_Ts"][c] & Marca.CENTINELA.bit and bits["marcas_Ts"][c] & Marca.FUERA_DE_RANGO.bit)
        self.assertTrue(bits["marcas_Td"][c] & Marca.CENTINELA.bit and bits["marcas_HR"][c] & Marca.CENTINELA.bit)
        resto = np.arange(len(ancha)) != c
        self.assertEqual({col: int((b[resto] != 0).sum()) for col, b in bits.items()}, dict.fromkeys(bits, 0))
        self.assertEqual({col: int(b[c] != 0) for col, b in bits.items() if col not in ("marcas_Ts", "marcas_Td",
                                                                                       "marcas_HR")},
                         dict.fromkeys(("marcas_FF", "marcas_DD", "marcas_QFE", "marcas_QFF"), 0))
        for valido in ("valido_T", "valido_Td", "valido_HR"):
            self.assertEqual(np.flatnonzero(~ancha[valido].to_numpy(bool)).tolist(), [c], valido)
        self.assertTrue(ancha["valido_viento"].all() and ancha["valido_p"].all())
        rr = ancha["rr06_mm"].to_numpy(np.float64)
        con_reporte = np.isin(m["h"] % numerico.PERIODO_DIA_H, (0, 6, 12, 18))
        self.assertTrue(np.array_equal(ancha["rr06_valido"].to_numpy(bool), con_reporte))
        self.assertEqual(sorted(set(rr[con_reporte].tolist())), [0.0, 2.5])

    def test_hito1_conteos_alarmas_resumen_y_rr06(self):
        """§2.6 y §2.7: los conteos de la estación y de los artefactos; la única alarma es Q3 (un artefacto no
        normalizable de cuatro, 25 %), que detiene; ``resumen_qc`` y la validación de RR06 por el píxel enlazado (D27)
        pasan la guarda de su clase."""
        m = self._mundo()
        U, infos = m["U"], m["infos"]
        tabla = Q.qc_estacion(Q.unir_largas(m["resultados"]["330101"]), infos["330101"], m["F"], U, k2=frozenset(),
                              politicas=m["lecturas"]["330101"])[0]
        ancha = Q.tabla_ancha(tabla)
        todos = [*m["resultados"]["330101"], *m["resultados"]["330102"]]
        num, den = Q.conteos_estacion(tabla, infos["330101"])
        n3, d3 = Q.conteos_artefactos(todos, infos)
        for t in (num, den, n3, d3):
            tipos.validar_esquema(t, tipos.ESQUEMA_CONTEOS_QC, nombre="conteos")
        num, den = pd.concat([num, n3], ignore_index=True), pd.concat([den, d3], ignore_index=True)
        alarmas = Q.alarmas(num, den, U)
        self.assertEqual(alarmas, [{"alarma": "Q3", "regla": Q.REGLA_Q3, "variable": Q.VARIABLE_ARTEFACTO,
                                    "zona": Q.ZONA_NACIONAL, "tasa": 25.0}])
        lista = Q.lista_descriptiva(num, den, U)
        self.assertEqual(lista, [])
        nn = Q.tabla_no_normalizables(todos, infos)
        resumen = Q.resumen_qc(num, alarmas, nn, [], denominadores=den, lista=lista, umbrales=U)
        self.assertTrue(resumen["detener"])
        self.assertEqual(resumen["no_normalizables"]["total"], 1)
        ceguera.vigilar_salida("qc/resumen_qc.json", resumen, clase=ceguera.clase_de_ruta("qc/resumen_qc.json"))
        # RR06 (§2.6; D27): 0,1 mm/h en el píxel enlazado a la celda; la suma de 6 h es 0,6 mm en cada reporte.
        enlaces = pd.DataFrame({"celda": np.array([_CELDA_H1], np.int64),
                                "era5land_pixel": np.array([_PIXEL_LLUVIA], np.int64)})
        tp = np.full((m["todas"].size, 1), _LLUVIA_MM_H)
        sumas = Q.sumas_lluvia_rr06({"330101": ancha}, infos, enlaces, tp, h=m["todas"],
                                    pixel_ids=np.array([_PIXEL_LLUVIA], np.int64))
        rr06 = Q.validar_rr06({"330101": ancha}, sumas, infos, U)
        total = next(g for g in rr06["grupos"] if g["zona"] == Q.ZONA_NACIONAL and g["estacion_del_anio"] is None)
        reportes = int(ancha["rr06_valido"].sum())
        self.assertEqual((rr06["reportes_sin_enlace"], rr06["reportes_ventana_incompleta"]), (0, 0))
        self.assertEqual(total["n_periodos"], reportes)
        self.assertEqual(total["total_obs_mm"], float(ancha["rr06_mm"].sum()))
        self.assertAlmostEqual(total["total_lluvia_producto_mm"], 6 * _LLUVIA_MM_H * reportes, places=9)
        ceguera.vigilar_salida("validacion/rr06.json", rr06, clase=ceguera.clase_de_ruta("validacion/rr06.json"))

    def test_hito1_residuos_para_candidatos(self):
        """INT-4 (A1-A3): r = obs − F con los dos en float32 y r_p = ln(QFE/p_F); NaN donde la hora no es válida (el
        centinela); la tabla de ``candidatos`` tiene una fila por hora observada y δ = 0 sin quiebres."""
        m = self._mundo()
        U = m["U"]
        ancha = Q.tabla_ancha(Q.qc_estacion(Q.unir_largas(m["resultados"]["330101"]), m["infos"]["330101"], m["F"], U,
                                            k2=frozenset(), politicas=m["lecturas"]["330101"])[0])
        residuos, tramos = _residuos_de("330101", ancha, m["F"], U)
        tipos.validar_esquema(residuos, tipos.ESQUEMA_RESIDUOS, nombre="residuos")
        tipos.validar_esquema(tramos, tipos.ESQUEMA_TRAMOS_HOMOGENEOS, nombre="tramos")
        self.assertTrue(residuos["observada"].all() and len(residuos) == len(ancha))
        F = fondo_era5l.en_horas(m["F"], m["h"])
        f4 = np.float32
        ts, qfe = _de_texto(m["columnas"]["Ts"], "Ts"), _de_texto(m["columnas"]["QFE"], "QFE")
        r_T = (ts.astype(f4).astype(np.float64) - F["T_F"].astype(f4).astype(np.float64)).astype(f4)
        r_T[m["centinela"]] = np.nan
        np.testing.assert_array_equal(residuos["r_T"].to_numpy(), r_T)
        r_p = np.log(qfe.astype(f4).astype(np.float64) / F["p_F"].astype(f4).astype(np.float64))
        np.testing.assert_array_equal(residuos["r_p"].to_numpy(), r_p.astype(f4))
        self.assertTrue(np.isnan(residuos["r_Td"].to_numpy()[m["centinela"]]))
        self.assertEqual(set(tramos["delta"]), {0.0})


# --- Hito 2: la red de 30 estaciones ----------------------------------------------------------------------------
_N_LADO, _N_COLUMNAS, _PASO_GRADOS = 5, 6, 0.2
_SIN_COMUNA, _FUERA_DE_GRILLA = 13, 25           # índices de la red: celda con cod_comuna 0 (D9, D20) y sin celda (D34)
_DESDE_UTC, _HASTA_UTC = "2010-01-01T00", "2012-01-01T00"
_CANDIDATOS_P = validacion.CANDIDATOS_USO[Uso.AMBIENTAL]


def _sesgo_T(lat, lon, m, hora):
    """b(x, m, h) de T (como S5): suave en el espacio, con ciclo anual y diario."""
    return (1.0 + 0.8 * (np.asarray(lat) + 33.5) + 0.4 * np.cos(2 * np.pi * (m - 1) / 12)
            + 0.4 * np.cos(2 * np.pi * (hora - 15) / 24))


def _infos_hito2(U) -> dict:
    """30 estaciones a ≈ 22 km, una de ellas a ≈ 0,8 km de la primera (un grupo); 17 en «centro», 11 en «sur», una
    con celda de ``cod_comuna`` 0 (sin macrozona, D9 y D20) y una fuera de la grilla (D34). Grupo y bloque con
    ``particiones`` (A8, PAR-12)."""
    nan = math.nan
    puntos = []
    for i in range(_N_LADO):
        for j in range(_N_COLUMNAS):
            puntos.append((-33.0 - i * _PASO_GRADOS - 0.013 * ((i * 7 + j * 3) % 5),
                           -71.4 + j * _PASO_GRADOS + 0.011 * ((i * 3 + j * 5) % 4), 200.0 + 120.0 * j + 80.0 * i))
    puntos[-1] = (puntos[0][0] - 0.005, puntos[0][1] + 0.006, puntos[0][2] + 15.0)
    infos = {}
    for n, (lat, lon, z) in enumerate(puntos):
        codigo = f"{330200 + n:06d}"
        e, nn = (float(x[0]) for x in numerico.utm19s(np.array([lat, lat]), np.array([lon, lon])))
        macro = None if n in (_SIN_COMUNA, _FUERA_DE_GRILLA) else ("centro" if n < 18 else "sur")
        infos[codigo] = tipos.InfoEstacion(
            codigo=codigo, nombre=f"E{codigo}", conjunto="N" if n % 4 == 1 else "V", macrozona=macro,
            grupo=tipos.id_grupo([codigo]), omm=None, tipo=None, propietario=None, lat_txt=f"{lat:.4f}",
            lon_txt=f"{lon:.4f}", alt_txt=f"{z:.0f}", lat=lat, lon=lon, z_cat=z, rho_km=0.1, k3_pasa=True, z_s=z,
            z_s_fuente="catalogo", celda=None if n == _FUERA_DE_GRILLA else 1000 + n, utm_e=e, utm_n=nn, bloque="",
            pix0=0, pix1=-1, pix2=-1, pix3=-1, w0=1.0, w1=0.0, w2=0.0, w3=0.0, respaldo_16km=False, sin_fondo=False,
            excluida=False, motivo=None)
    codigos = sorted(infos)
    grupos = particiones.grupos_mismo_sitio(infos, U)
    bloques = particiones.bloque(np.array([infos[c].lat for c in codigos]), np.array([infos[c].lon for c in codigos]),
                                 U)
    return {c: dataclasses.replace(infos[c], grupo=grupos[c], bloque=str(b)) for c, b in zip(codigos, bloques)}


def _estaticos_hito2(infos, U) -> pd.DataFrame:
    """``tipos.ESQUEMA_ESTATICAS_CELDA_C`` de las celdas de la red (TIP-22): la celda con ``cod_comuna`` 0 lleva la
    macrozona heredada de la vecina (D22 (a)); la estación sin celda no tiene fila (D34)."""
    rng = np.random.default_rng(U.a("SEMILLA"))
    filas = []
    for n, c in enumerate(sorted(infos)):
        info = infos[c]
        if info.celda is None:
            continue
        fr = rng.dirichlet(np.ones(len(tipos.LULC)))
        filas.append({"celda": int(info.celda), "z_media": info.z_s, "z_poblada": info.z_s, "z_poblada_es_media": True,
                      "frac_dato": 1.0, "tpi1": float(rng.normal(0, 20)), "tpi5": float(rng.normal(0, 60)),
                      "tpi1_truncado": n % 7 == 3, "tpi5_truncado": False, "pendiente_deg": float(rng.uniform(1, 15)),
                      "log_dist_costa": float(np.log1p(80 + 90 * (info.lon + 71.4))),
                      **{col: float(fr[i]) for i, col in enumerate(tipos.LULC)}, "lat": info.lat,
                      "macrozona_cod": tipos.MACROZONA_COD[info.macrozona or "centro"],
                      "cod_comuna": 0 if n == _SIN_COMUNA else 13101,
                      tipos.COLUMNA_Z_E5L: info.z_s - 150.0 + 40.0 * math.sin(n)})
    df = pd.DataFrame(filas).astype(dict(tipos.ESQUEMA_ESTATICAS_CELDA_C))
    tipos.validar_esquema(df, tipos.ESQUEMA_ESTATICAS_CELDA_C, nombre="estáticos de C")
    return df


def _pi_hito2(infos, horas: dict, U) -> dict:
    """π de lo ambiental (§5.3): π^pob con 60 celdas pobladas y la red activa en todos los años de PI_POB_PERIODO, π^mon
    con ocho monitores de PM2,5 y NO2 (2010 y 2011) y su manifiesto, y ½ π^mon + ½ π^pob (INT-8)."""
    desde, hasta = constantes.valor("PI_POB_PERIODO")
    anios = range(desde, hasta + 1)
    rng = np.random.default_rng(U.a("SEMILLA"))
    puntos = [(-33.0 - rng.uniform(0, 1.3), -71.45 + rng.uniform(0, 1.4), float(rng.uniform(1, 100))) for _ in range(60)]
    celdas = pd.DataFrame([{"anio": y, "lat": la, "lon": lo, "w_ghs": w} for y in anios for la, lo, w in puntos])
    codigos = sorted(infos)
    tabla = pd.DataFrame({"codigo": codigos, "lat": [infos[c].lat for c in codigos],
                          "lon": [infos[c].lon for c in codigos], "horas": [horas[c] for c in codigos]})
    por_anio = {y: tabla for y in anios}
    pi_pob = validacion.pi_poblacion(celdas, por_anio, "p", U)
    monitores = [{"estacion": f"M{k:02d}", "lat": -33.1 - 0.15 * k, "lon": -71.2 + 0.1 * k} for k in range(8)]
    paneles = {}
    for pol in tipos.CONTAMINANTES_M6:
        paneles[pol] = {"tabla": pd.DataFrame({
            "estacion": [x["estacion"] for x in monitores for _ in range(2)],
            "ts_utc": pd.to_datetime(["2010-06-01T00:00Z", "2011-06-01T00:00Z"] * len(monitores)), "obs": 10.0}),
            "sha256": hashlib.sha256(pol.encode()).hexdigest()}
    red2 = {"estaciones": monitores,
            "contaminantes": {pol: {"panel": {"sha256": paneles[pol]["sha256"]}} for pol in tipos.CONTAMINANTES_M6}}
    pi_mon = validacion.pi_monitores(red2, paneles, por_anio, "p", U)
    return {"pob": pi_pob, "mon": pi_mon, "p": validacion.pi_uso(Uso.AMBIENTAL, pi_pob, pi_mon, umbrales=U)}


def _s_a_mano(mse: np.ndarray, banda: np.ndarray, pi, minimo: int) -> float:
    """§5.3 (VAL-10) escrito aparte de ``validacion``: S = √(Σ_g π_g · media_g(MSE_e)); mientras haya más de un grupo y
    alguno tenga < ``minimo`` evaluaciones, el primero de ellos desde la banda más cercana a 0 se une con la contigua
    más cercana a 0 (la primera, con la segunda)."""
    pi = np.asarray(pi, dtype=np.float64)
    grupos = [[k] for k in range(pi.size)]
    while len(grupos) > 1:
        chicos = [i for i, g in enumerate(grupos) if int(np.isin(banda, g).sum()) < minimo]
        if not chicos:
            break
        i = chicos[0]
        a, b = sorted((i, 1 if i == 0 else i - 1))
        grupos[a:b + 1] = [grupos[a] + grupos[b]]
    total = sum(float(pi[g].sum()) * float(np.mean(mse[np.isin(banda, g)])) for g in grupos if np.isin(banda, g).any())
    return math.sqrt(total)


def _hiper_json(h) -> dict:
    if isinstance(h, tuple):
        return {"A": dataclasses.asdict(h[0]), "phi_prima": dataclasses.asdict(h[1])}
    return dataclasses.asdict(h) if dataclasses.is_dataclass(h) else {"alfa": float(h)}


@lru_cache(maxsize=None)
def _red_hito2() -> dict:
    """La red del hito 2 de punta a punta, una vez por proceso (las pruebas sólo leen lo que devuelve)."""
    U = _umbrales()
    infos = _infos_hito2(U)
    codigos = sorted(infos)
    h = np.arange(_h_de([pd.Timestamp(_DESDE_UTC)], 0)[0], _h_de([pd.Timestamp(_HASTA_UTC)], 0)[0], dtype=np.int64)
    hora = h % numerico.PERIODO_DIA_H
    doy = (pd.Timestamp("2000-01-01") + pd.to_timedelta(h, unit="h")).dayofyear.to_numpy()
    F, campos = {}, {}
    for n, c in enumerate(codigos):
        z = infos[c].z_s
        T_F = (15 + 6 * np.cos(2 * np.pi * (doy - 20) / 365.25) + 5 * np.cos(2 * np.pi * (hora - 19) / 24)
               - 0.005 * z + 0.3 * n)
        campos[c] = {"T_F": T_F, "Td_F": T_F - 4 - 2 * np.cos(2 * np.pi * (hora - 19) / 24) ** 2,
                     "p_F": float(numerico.p_std(z)) + 2.0 * np.sin(2 * np.pi * doy / 365.25)
                     + 0.8 * np.cos(4 * np.pi * hora / 24),
                     "u_F": 1.5 * np.sin(2 * np.pi * hora / 24) + 0.1 * n, "v_F": 0.5 + 0.3 * np.cos(h / 41.0)}
        F[c] = fondo_era5l.tabla_puntos(h, campos[c])
    lat = np.array([infos[c].lat for c in codigos])
    v = S.verdad({"h": h, "lat": lat, "lon": np.array([infos[c].lon for c in codigos]),
                  "F": np.column_stack([F[c]["T_F"].to_numpy(np.float64) for c in codigos])},
                 _sesgo_T, "MC-50", semilla=U.a("SEMILLA"))
    b_p = 0.002 * (1 + 0.5 * (lat + 33.5))              # sesgo relativo de QFE (≈ 2 hPa), suave en el espacio
    etiquetas = pd.DatetimeIndex(pd.Timestamp("2000-01-01") + pd.to_timedelta(h, unit="h")) \
        + pd.Timedelta(minutes=_UTC_MENOS_4)
    with tempfile.TemporaryDirectory() as tmp:
        regla = [_tramo_reloj(etiquetas[0].isoformat(), etiquetas[-1].isoformat())]
        pol = _politica_reloj(Path(tmp) / "reloj", {c: regla for c in codigos})
    meses = {(x.year, x.month) for x in etiquetas}
    id_mes = {m: k for k, m in enumerate(sorted(meses))}
    ids = np.array([id_mes[(x.year, x.month)] for x in etiquetas], dtype=np.int32)
    anchas, k4s, efectivas, residuos, tramos, lecturas = {}, {}, {}, {}, [], {}
    for n, c in enumerate(codigos):
        info = infos[c]
        lecturas[c] = _lectura(pol, info, U, meses)
        r_p = b_p[n] + 0.0002 * v["a"][:, n] / 1.5
        larga = _larga_vectorizada(U, c, etiquetas, _portal(v["obs"][:, n], campos[c]["p_F"], r_p, info.z_s, h, n),
                                   z_s=info.z_s, id_artefacto=ids)
        tabla, k4s[c], efectivas[c] = Q.qc_estacion(larga, info, F[c], U, k2=frozenset(), politicas=lecturas[c])
        anchas[c] = Q.tabla_ancha(tabla)
        residuos[c], tr = _residuos_de(c, anchas[c], F[c], U)
        tramos.append(tr)
    horas = {k: {c: int(anchas[c][f"valido_{k}"].sum()) for c in codigos} for k in validacion.CLAVES_HORAS}
    pi = _pi_hito2(infos, horas["p"], U)
    pi_uso = {"p": pi["p"], "T": validacion.pi_uso(Uso.AGUDO, pi["pob"], umbrales=U)}
    grupos = {c: infos[c].grupo for c in codigos}
    pliegues = tuple(particiones.pliegues_p1(grupos, U) + particiones.pliegues_p2(infos, grupos, U))
    estaticos = _estaticos_hito2(infos, U)
    datos = tipos.DatosCompetencia(
        residuos=residuos, climatologias=candidatos.climatologias_a(residuos, U),
        tramos=pd.concat(tramos, ignore_index=True), filas_c={"C": candidatos.filas_c(residuos, estaticos, F, U,
                                                                                        infos=infos)},
        estaticos=estaticos, estaciones=infos, pliegues=pliegues, puntos_e5l=F, clima_estado={})
    objetivo = _objetivo_de_validacion(infos, horas, pi_uso, U)
    hiper, prediccion = {}, {}
    for ext in pliegues:
        sel = {}
        for cand in _CANDIDATOS_P:
            extra = {"hiper_a": sel[Candidato.A.value]} if cand == Candidato.AB.value else {}
            sel[cand] = candidatos.seleccionar(cand, "p", Uso.AMBIENTAL, ext, datos, U, objetivo=objetivo,
                                               recorte=False, **extra)
            prediccion[(ext.id, cand)] = candidatos.predecir_prueba(cand, "p", Uso.AMBIENTAL, sel[cand], ext, datos,
                                                                    umbrales=U)
        hiper[ext.id] = sel
    # A de T en P1 con la misma cadena (como S5): su R frente a b.
    error_a_T = []
    for ext in (p for p in pliegues if p.particion is tipos.Particion.P1):
        hiper_T = candidatos.seleccionar(Candidato.A, "T", Uso.AGUDO, ext, datos, U, objetivo=objetivo, recorte=False)
        pred = candidatos.predecir_prueba(Candidato.A, "T", Uso.AGUDO, hiper_T, ext, datos, umbrales=U)
        for c, g in pred.groupby("codigo"):
            error_a_T.append(g["correccion"].to_numpy() - v["b"][np.searchsorted(h, g["h"].to_numpy()),
                                                                codigos.index(c)])
    # Evaluaciones (INT-6, INT-7).
    filas, descriptivas, sin_corregir = [], [], {}
    for ext in pliegues:
        for c in ext.prueba:
            info, ancha = infos[c], anchas[c]
            hq = ancha["h"].to_numpy(np.int64)
            obs = _con_valido(ancha, "QFE", "valido_p")
            Fh = fondo_era5l.en_horas(F[c], hq)
            cands = [x for x in _CANDIDATOS_P
                     if not (tipos.fuera_de_la_grilla(info) and x in (Candidato.C.value, Candidato.C_EST.value))]
            producto, soporte = {}, {}
            for cand in cands:
                g = prediccion[(ext.id, cand)]
                g = g[(g["codigo"] == c).to_numpy(dtype=bool)]
                R = np.full(hq.size, np.nan)
                sop = np.zeros(hq.size, dtype=bool)
                pos = np.searchsorted(g["h"].to_numpy(np.int64), hq)
                pos_c = np.clip(pos, 0, max(len(g) - 1, 0))
                esta = (pos < len(g)) & (g["h"].to_numpy(np.int64)[pos_c] == hq) if len(g) else np.zeros(hq.size, bool)
                R[esta] = g["correccion"].to_numpy(np.float64)[pos_c[esta]]
                sop[esta] = g["soporte"].to_numpy(bool)[pos_c[esta]]
                cero = np.zeros(hq.size)
                producto[cand] = fondo_era5l.producto_desde(Fh, {"R_T": cero, "R_Td": cero, "R_u": cero, "R_v": cero,
                                                                 "R_p": R})["p"]
                soporte[cand] = sop
            comun = np.isfinite(obs) & np.logical_and.reduce([np.isfinite(producto[x]) for x in cands])
            sin_corregir[(c, ext.particion.value)] = float(np.mean((Fh["p_F"][comun] - obs[comun]) ** 2))
            for cand in cands:
                met = validacion.evaluacion(hq, np.where(comun, producto[cand], np.nan), obs, uso=Uso.AMBIENTAL,
                                            variable="p", umbrales=U)
                if met is None:
                    continue
                frac = float(1 - soporte[cand][comun].mean()) if cand in validacion.NUCLEO else math.nan
                filas.append(validacion.fila_evaluacion(met, codigo=c, particion=ext.particion.value, pliegue=ext.id,
                                                        candidato=cand, uso=Uso.AMBIENTAL, variable="p",
                                                        frac_sin_soporte=frac))
                descriptivas += validacion.filas_descriptivas(met, codigo=c, particion=ext.particion.value,
                                                              candidato=cand, uso=Uso.AMBIENTAL, variable="p")
    evaluaciones = validacion.tabla_evaluaciones(filas)
    banda = validacion.bandas_de_pliegues(pliegues, infos, horas, U)
    kw = {"uso": Uso.AMBIENTAL, "grupo": Grupo.P, "banda": banda, "pi": {"p": pi["p"]}}
    publicada = validacion.estratos(evaluaciones, infos, U, **kw)
    bloques = particiones.bloques_remuestreo(infos)
    replicas = validacion.remuestreo(evaluaciones, bloques, U, infos=infos, e0=_CANDIDATOS_P, **kw)
    tf = S.tablas_metricas("p_sin_ex")["tf"]
    entradas = tipos.EntradasDecision(Uso.AMBIENTAL, Grupo.P, publicada, tf, replicas, {})
    return {"U": U, "infos": infos, "codigos": codigos, "h": h, "F": F, "anchas": anchas, "k4": k4s,
            "efectivas": efectivas, "lecturas": lecturas, "residuos": residuos, "datos": datos, "pliegues": pliegues,
            "horas": horas, "pi": pi, "hiper": hiper, "prediccion": prediccion, "objetivo": objetivo,
            "error_a_T": np.concatenate(error_a_T), "evaluaciones": evaluaciones, "descriptivas": descriptivas,
            "sin_corregir": sin_corregir, "banda": banda, "kw": kw, "publicada": publicada, "bloques": bloques,
            "replicas": replicas, "tf": tf, "entradas": entradas,
            "decision": decision.decidir_combinacion(Uso.AMBIENTAL, Grupo.P, entradas, umbrales=U)}


class PruebasHito2(unittest.TestCase):
    """Hito 2 de §6 del diseño: una red de 30 estaciones con A y B reales (y AB y C), P1 y P2, y una evaluación
    completa (lo ambiental de p) hasta ``decision``. Las tablas largas son las de INT-3."""

    def test_hito2_qc_de_la_red(self):
        """El envoltorio, K4 y la marca 14 en las 30 estaciones: las series limpias no llevan ninguna marca, todas las
        horas son válidas, K4 no halla quiebres, la efectiva es la de lectura y la tabla de residuos de cada estación
        tiene una fila por hora."""
        r = _red_hito2()
        for c in r["codigos"]:
            ancha = r["anchas"][c]
            with self.subTest(codigo=c):
                tipos.validar_esquema(ancha, tipos.ESQUEMA_QC_ESTACION, nombre=c)
                np.testing.assert_array_equal(ancha["h"].to_numpy(np.int64), r["h"])
                self.assertEqual({col: int((ancha[col] != 0).sum()) for col in ancha.columns
                                  if col.startswith("marcas_")}, dict.fromkeys(tipos.COLUMNA_MARCAS.values(), 0))
                self.assertTrue(all(ancha[f"valido_{k}"].all() for k in validacion.CLAVES_HORAS))
                self.assertEqual(r["k4"][c].quiebres, ())
                self.assertEqual(r["efectivas"][c], r["lecturas"][c])
                self.assertEqual(len(r["residuos"][c]), len(ancha))
        self.assertTrue(np.isfinite(r["datos"].tramos["delta"].to_numpy()).all())

    def test_hito2_pliegues_seleccion_y_prediccion(self):
        """P1 y P2 (§5.1): cada estación es de prueba en un pliegue de cada partición; los hiperparámetros salen de las
        rejillas de §4.2 y §4.6; A, B y AB predicen finito en todas sus horas; C es NaN sólo en la estación sin celda
        (D34); una segunda corrida de un pliegue da lo mismo bit a bit."""
        r = _red_hito2()
        U = r["U"]
        for particion in tipos.Particion:
            prueba = [c for p in r["pliegues"] if p.particion is particion for c in p.prueba]
            self.assertEqual(sorted(prueba), r["codigos"], particion)
        nucleo = {(float(L), float(lam), float(k)) for L in U.a("NUC_L") for lam in U.a("NUC_LAMBDA")
                  for k in U.a("NUC_KAPPA")}
        fuera = [c for c in r["codigos"] if tipos.fuera_de_la_grilla(r["infos"][c])]
        self.assertEqual(len(fuera), 1)
        for ext in r["pliegues"]:
            sel = r["hiper"][ext.id]
            for cand in (Candidato.A.value, Candidato.B.value):
                self.assertIn((sel[cand].L_km, sel[cand].lam, sel[cand].kappa), nucleo)
            self.assertEqual(sel[Candidato.AB.value][0], sel[Candidato.A.value])
            self.assertIn(sel[Candidato.C.value], [float(a) for a in U.a("C_ALFAS")])
            for cand in _CANDIDATOS_P:
                pred = r["prediccion"][(ext.id, cand)]
                tipos.validar_esquema(pred, tipos.ESQUEMA_PREDICCION, nombre="prediccion")
                finita = np.isfinite(pred["correccion"].to_numpy())
                if cand == Candidato.C.value:
                    self.assertTrue(np.array_equal(~finita, pred["codigo"].isin(fuera).to_numpy(dtype=bool)), ext.id)
                else:
                    self.assertTrue(finita.all(), (ext.id, cand))
        ext = r["pliegues"][-1]
        otra = candidatos.seleccionar(Candidato.B, "p", Uso.AMBIENTAL, ext, r["datos"], U, objetivo=r["objetivo"],
                                      recorte=False)
        self.assertEqual(otra, r["hiper"][ext.id][Candidato.B.value])
        pd.testing.assert_frame_equal(
            candidatos.predecir_prueba(Candidato.B, "p", Uso.AMBIENTAL, otra, ext, r["datos"], umbrales=U),
            r["prediccion"][(ext.id, Candidato.B.value)], check_exact=True)

    def test_hito2_los_candidatos_corrigen_el_sesgo(self):
        """Con un sesgo de QFE de ≈ 2 hPa, suave en el espacio, cada candidato baja el MSE horario de p respecto del
        fondo sin corregir en todas las evaluaciones; y A recupera b de T con la cadena real de qc con RMSE < 0,3 K
        (S5)."""
        r = _red_hito2()
        ev = r["evaluaciones"]
        for cand in _CANDIDATOS_P:
            d = ev[(ev["candidato"] == cand).to_numpy(dtype=bool)]
            with self.subTest(candidato=cand):
                self.assertGreater(len(d), 0)
                peor = [r["sin_corregir"][(c, p)] for c, p in zip(d["codigo"], d["particion"])]
                self.assertTrue((d["mse_h"].to_numpy() < np.array(peor)).all())
        e = r["error_a_T"]
        self.assertTrue(np.isfinite(e).all())
        self.assertLess(float(np.sqrt(np.mean(e ** 2))), constantes.valor("S5_RMSE_A_K"))

    def test_hito2_evaluacion_completa_y_decision(self):
        """§5.2 a §5.5 y §6.2: 29 estaciones evaluables en P1 y P2 con los cuatro candidatos (la sin celda se descarta y
        se cuenta, D34; la sin macrozona sólo cuenta en lo nacional, D9); las cinco macrozonas en cada partición (A13),
        con MZ en «centro» y «sur»; el remuestreo de E0; y la decisión, cuyo S es el S nacional agregado publicado, con
        un ganador de E1 de menor S, ΔS y su intervalo (D46), que pasa por ``decision_json`` y la guarda."""
        r = _red_hito2()
        U, ev, pub, d = r["U"], r["evaluaciones"], r["publicada"], r["decision"]
        tipos.validar_esquema(ev, tipos.ESQUEMA_EVALUACIONES, nombre="evaluaciones")
        tipos.validar_esquema(pub, tipos.ESQUEMA_VALIDACION_PUB, nombre="publicada")
        tipos.validar_esquema(r["replicas"], tipos.ESQUEMA_REPLICAS, nombre="replicas")
        con_celda = [c for c in r["codigos"] if not tipos.fuera_de_la_grilla(r["infos"][c])]
        for cand in _CANDIDATOS_P:
            claves = set(zip(*[ev.loc[(ev["candidato"] == cand).to_numpy(dtype=bool), k] for k in ("codigo",
                                                                                                   "particion")]))
            esperadas = {(c, p.value) for c in (r["codigos"] if cand in validacion.NUCLEO else con_celda)
                         for p in tipos.Particion}
            self.assertEqual(claves, esperadas, cand)
        self.assertEqual({k: pub.attrs["declaraciones"][k] for k in ("fuera_de_la_grilla", "sin_macrozona")},
                         {"fuera_de_la_grilla": 1, "sin_macrozona": 1})
        nacional = pub[(pub["estrato"] == tipos.Estrato.NACIONAL.value).to_numpy(dtype=bool)]
        self.assertTrue(nacional["publicable"].all())
        self.assertEqual(set(nacional["n_estaciones"]), {len(con_celda)})
        # S nacional de cada candidato y partición, con las bandas de los pliegues y el π del uso, contado aparte.
        for cand in _CANDIDATOS_P:
            propias = ev[(ev["candidato"] == cand).to_numpy(dtype=bool) & ev["codigo"].isin(con_celda).to_numpy(bool)]
            for particion in (*(p.value for p in tipos.Particion), tipos.PARTICION_AGREGADO):
                sel = propias if particion == tipos.PARTICION_AGREGADO else propias[
                    (propias["particion"] == particion).to_numpy(dtype=bool)]
                b = np.array([r["banda"][(c, p, "p")] for c, p in zip(sel["codigo"], sel["particion"])])
                fila = nacional[((nacional["candidato"] == cand) & (nacional["particion"] == particion)).to_numpy(bool)]
                self.assertAlmostEqual(float(fila["S"].iloc[0]), _s_a_mano(sel["mse_h"].to_numpy(), b, r["pi"]["p"],
                                                                           U.a("BANDA_MIN_EVAL")), places=12)
        macro = pub[(pub["estrato"] == tipos.Estrato.MACROZONA.value).to_numpy(dtype=bool)]
        self.assertEqual(set(macro["valor_estrato"]), set(tipos.MACROZONAS))
        por_zona = {z: set(macro.loc[(macro["valor_estrato"] == z).to_numpy(dtype=bool), "n_estaciones"])
                    for z in tipos.MACROZONAS}
        self.assertEqual(por_zona, {**{z: {0} for z in tipos.MACROZONAS}, "centro": {17}, "sur": {11}})
        self.assertEqual(len(r["replicas"]), U.a("BOOT_REPLICAS") * len(_CANDIDATOS_P))
        self.assertTrue(np.isfinite(r["replicas"]["S"].to_numpy()).all())
        compuertas = decision.compuertas(Uso.AMBIENTAL, Grupo.P, r["entradas"], U)
        mz = compuertas[(compuertas["compuerta"] == tipos.Compuerta.MZ.value).to_numpy(dtype=bool)]
        self.assertEqual(set(mz.loc[mz["aplica"].to_numpy(dtype=bool), "ambito"]), {"centro", "sur"})
        self.assertEqual(d.e0, _CANDIDATOS_P)
        agregado = nacional[(nacional["particion"] == tipos.PARTICION_AGREGADO).to_numpy(dtype=bool)]
        self.assertEqual(dict(d.S), dict(zip(agregado["candidato"], agregado["S"].astype(float))))
        # Paso 3, o el 4 con E1 vacío (aquí toda la TF pasa: el conjunto del paso 4 es E0); intervalo de D46 a mano.
        conjunto = d.e1 or d.e0
        self.assertEqual(bool(d.e1), "regla sin ganador" not in " ".join(d.notas))
        self.assertIn(d.ganador, conjunto)
        self.assertEqual(d.ganador, min(conjunto, key=lambda c: (d.S[c], _DESEMPATE[c])))
        self.assertEqual(dict(d.delta_S), {c: d.S[c] - d.S[d.ganador] for c in d.e0})
        pct = constantes.valor("BOOT_IC_PCT")
        self.assertEqual(dict(d.ic_delta_S), {c: _ic_con_ganador_por_replica(r["replicas"], conjunto, c, pct)
                                              for c in d.e0})
        hiper = {(Uso.AMBIENTAL.value, Grupo.P.value): {c: _hiper_json(x) for c, x in
                                                        r["hiper"][r["pliegues"][0].id].items()}}
        registro = decision.decision_json([d], hiper, {_RUTA_PUNTAJES: hashlib.sha256(b"hito 2").hexdigest()})
        self.assertEqual(json.loads(json.dumps(registro, ensure_ascii=False, allow_nan=False)), registro)
        ceguera.vigilar_salida("decision.json", registro, clase=ceguera.clase_de_ruta("decision.json"))
        ceguera.vigilar_salida(_RUTA_PUNTAJES, pub, clase=ceguera.clase_de_ruta(_RUTA_PUNTAJES))

    def test_hito2_intervalo_de_d46_con_mas_de_un_candidato(self):
        """INT-9 (crítico de la ola 3): en la decisión del hito, E1 = {C} y C gana todas las réplicas, así que su
        intervalo de ΔS no separa D46 del ganador fijo. Con las mismas tablas reales sin las filas de macrozona (DEC-20:
        MZ no rige), E1 = E0: C sigue ganando, pero AB gana algunas réplicas, y el intervalo de D46 de la decisión,
        contado a mano con el ganador de cada réplica dentro de E1, difiere en algún candidato del del ganador fijo."""
        r = _red_hito2()
        pub = r["publicada"]
        sin_mz = pub[(pub["estrato"] != tipos.Estrato.MACROZONA.value).to_numpy(dtype=bool)].reset_index(drop=True)
        sin_mz.attrs = dict(pub.attrs)
        entradas = tipos.EntradasDecision(Uso.AMBIENTAL, Grupo.P, sin_mz, r["tf"], r["replicas"], {})
        d = decision.decidir_combinacion(Uso.AMBIENTAL, Grupo.P, entradas, umbrales=r["U"])
        self.assertEqual((d.e0, d.e1), (_CANDIDATOS_P, _CANDIDATOS_P))
        self.assertEqual(d.ganador, min(d.e1, key=lambda c: (d.S[c], _DESEMPATE[c])))
        self.assertEqual(d.ganador, r["decision"].ganador)
        ganadores = _ganadores_por_replica(r["replicas"], d.e1)
        self.assertTrue(set(ganadores.values()) - {d.ganador}, "todas las réplicas las gana el de la decisión")
        pct = constantes.valor("BOOT_IC_PCT")
        d46 = {c: _ic_con_ganador_por_replica(r["replicas"], d.e1, c, pct) for c in d.e0}
        fijo = {c: _ic_con_ganador_fijo(r["replicas"], d.ganador, c, pct) for c in d.e0}
        self.assertEqual(dict(d.ic_delta_S), d46)
        self.assertNotEqual(d46, fijo)

    def test_hito2_descriptivos_bandas_soporte_y_replica_n(self):
        """§5.2, §5.3, §5.5 y §5.8: los descriptivos (el cociente de amplitudes de p), la tabla de bandas, la de soporte
        y la réplica con N salen con los esquemas de ``tipos`` y pasan la guarda de su clase. Todo estrato con
        estaciones es publicable, así que la tabla de soporte trae sólo los estratos sin estaciones, que no se publican
        (entre ellos las macrozonas norte_grande, norte_chico y austral). En la réplica con N, las 7 estaciones de N con
        celda dan el mismo ganador que la red."""
        r = _red_hito2()
        U, ev, kw, d = r["U"], r["evaluaciones"], r["kw"], r["decision"]
        descriptivos = validacion.tabla_descriptivos(ev, r["descriptivas"], r["infos"], U, **kw)
        tipos.validar_esquema(descriptivos, tipos.ESQUEMA_DESCRIPTIVOS_PUB, nombre="descriptivos")
        self.assertEqual(set(descriptivos["descriptivo"]), {validacion.D_COCIENTE})
        self.assertTrue(np.isfinite(descriptivos["valor"].to_numpy()).all())
        bandas = validacion.tabla_bandas(ev, r["infos"], U, uso=kw["uso"], grupo=kw["grupo"], banda=kw["banda"],
                                         pi_pob={"p": r["pi"]["pob"]}, pi_mon={"p": r["pi"]["mon"]})
        tipos.validar_esquema(bandas, tipos.ESQUEMA_BANDAS_PUB, nombre="bandas")
        soporte = validacion.fracciones_sin_soporte(ev, r["infos"], U, **kw)
        tipos.validar_esquema(soporte, tipos.ESQUEMA_SOPORTE_PUB, nombre="soporte")
        pub = r["publicada"]
        self.assertTrue(pub.loc[(pub["n_estaciones"] > 0).to_numpy(dtype=bool), "publicable"].all())
        no_publicados = set(zip(*[pub.loc[~pub["publicable"].to_numpy(dtype=bool), k] for k in ("estrato",
                                                                                               "valor_estrato")]))
        self.assertEqual(set(zip(soporte["estrato"], soporte["valor_estrato"])), no_publicados)
        self.assertTrue({(tipos.Estrato.MACROZONA.value, z) for z in ("norte_grande", "norte_chico", "austral")}
                        <= no_publicados)
        for nombre, tabla in (("validacion/descriptivos.parquet", descriptivos), ("validacion/bandas.parquet", bandas),
                              ("validacion/soporte.parquet", soporte)):
            ceguera.vigilar_salida(nombre, tabla, clase=ceguera.clase_de_ruta(nombre))
        entradas = {(Uso.AMBIENTAL, Grupo.P): {"evaluaciones": ev, "banda": kw["banda"], "pi": kw["pi"],
                                               "bloques": r["bloques"], "tf": r["tf"], "motivos_e0": {},
                                               "ganador": d.ganador}}
        n = validacion.replica_n(entradas, r["infos"], U, decidir=decision.decidir_combinacion)
        clave = f"{Uso.AMBIENTAL.value}/{Grupo.P.value}"
        de_n = [c for c in r["codigos"] if r["infos"][c].conjunto == tipos.Conjunto.N.value
                and not tipos.fuera_de_la_grilla(r["infos"][c])]
        self.assertEqual(len(de_n), 7)
        self.assertEqual(n[clave], {"ganador": d.ganador, "ganador_n": Candidato.C.value, "mismo_ganador": True,
                                    "n_estaciones_n": len(de_n)})
        self.assertEqual(d.ganador, Candidato.C.value)


if __name__ == "__main__":
    unittest.main()
