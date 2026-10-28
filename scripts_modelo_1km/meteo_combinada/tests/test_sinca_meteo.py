"""Pruebas de sinca_meteo.py (§5.6; MC-10).

Dueño: I11 (ola 2). §9 del texto no tiene pruebas de la meteorología SINCA (§5.6 es descriptiva y no entra en §6), así
que ninguna prueba lleva «sNN». Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
Datos sólo sintéticos, en carpetas temporales (``sintetico.sinca_sintetico``; los defectos se fabrican cambiando esas
copias): ninguna prueba abre DMC, la meteorología SINCA real, NASADEM real ni GHS-POP real, ni las salidas del reloj
SINCA. Además del paquete se leen, como código y con su huella, los dos descargadores SINCA
(``scripts_pipeline/descargar_sinca_meteorologia.py`` y ``scripts_pipeline/descargar_sinca_ampliacion.py``) y
``v2/reloj_sinca_v2.py`` (sólo por AST o como texto, sin importarlos), y la configuración
``config/sinca/politica_temporal.json``. Si falta uno o cambió su huella, esa prueba se omite con su motivo y no se da
por aprobada; ``reloj_sinca_v2.py`` tiene desde D54 una huella fijada (``fijados.SHA_RELOJ_SINCA_V2``), y si cambió, la
prueba falla.
"""
import sys

sys.dont_write_bytecode = True

import ast  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from datetime import date, datetime, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import constantes, fijados, sinca_meteo as SM, sintetico as S, tipos, umbrales  # noqa: E402

_AP = _RAIZ.parent
_APH = _AP.parent / "Air-Pollution-Health-Chile"
_DESCARGADOR = _AP / "scripts_pipeline" / "descargar_sinca_meteorologia.py"
_SHA_DESCARGADOR = "0942c4d071cefffb95da76d2b010c981ef126858ea7b3c028ef3c7c23a51b145"     # el de test_sintetico (M0)
_AMPLIACION = _AP / "scripts_pipeline" / "descargar_sinca_ampliacion.py"
_SHA_AMPLIACION = "d77247232ed4857941d8a4616193d805ed612af20a816949b44b6b1c9cb63c62"      # leído el 2026-10-26
_RELOJ_SINCA = _AP / "scripts_modelo_1km" / "v2" / "reloj_sinca_v2.py"
# D54 (FIJ-10 de fijados): la huella fijada es la del commit en que entró a git, AP 889b972 (c1eb98c5…). Antes se
# releía a mano porque otro flujo lo editaba (27cc8585…, 30c64edf…, 743fb2e0…) y sus dos pruebas se omitían; desde D54
# una huella distinta es una falla, no una omisión. Sólo se omiten si falta el archivo.
_SHA_RELOJ_SINCA = fijados.SHA_RELOJ_SINCA_V2
_POLITICA = _AP / "config" / "sinca" / "politica_temporal.json"
# Copia del bloque «sinca» de la política anclada (41018e4c…); test_politica_temporal la compara con el archivo.
POLITICA_PRUEBA = {"sinca": {
    "reloj_fuente": "hora_local_civil_sinca_sin_offset",
    "utc_salida": "datetime_naive_que_representa_utc",
    "zona_iana_default": "America/Santiago",
    "zonas_iana_por_region": {"RXI": "America/Coyhaique", "RXII": "America/Punta_Arenas"},
    "hora_ambigua": "conservar_hora_local_asumir_ocurrencia_estandar_y_registrar_utc_alternativo",
    "hora_inexistente": "conservar_hora_local_desplazar_adelante_y_marcar_qc",
    "colision_misma_utc_en_panel": "media_con_conteo_y_bandera_manteniendo_el_lector_crudo_sin_agregar",
}}
_SHA_VEREDICTOS = hashlib.sha256(b"veredictos sinteticos del reloj SINCA").hexdigest()
_SHA_CONTENIDO = hashlib.sha256(b"contenido sintetico de los veredictos").hexdigest()
_EPOCA = datetime(2000, 1, 1)
_U = None


def _umbrales():
    global _U
    if _U is None:
        texto = _APH / umbrales.TEXTO_M0
        if not texto.is_file():
            raise unittest.SkipTest(f"falta {texto.name} anclado en M0; la prueba no se da por aprobada")
        _U = umbrales.cargar_m0(_APH)
    return _U


def _exigir_reloj_sinca(prueba: unittest.TestCase) -> None:
    """D54: ``v2/reloj_sinca_v2.py`` con la huella fijada (c1eb98c5…, AP 889b972). Si falta, la prueba se omite y no se
    da por aprobada; si cambió, falla: hay que volver a fijarla (nota de D51)."""
    if not _RELOJ_SINCA.is_file():
        prueba.skipTest("falta v2/reloj_sinca_v2.py; no se da por aprobada")
    prueba.assertEqual(_sha(_RELOJ_SINCA.read_bytes()), _SHA_RELOJ_SINCA,
                       "v2/reloj_sinca_v2.py cambió desde AP 889b972: volver a fijar su huella (D54, nota de D51)")


def _veredictos(convencion=None, civiles=()):
    return {"sha256": _SHA_VEREDICTOS, "huella_contenido": _SHA_CONTENIDO, "convencion": convencion,
            "hora_civil": tuple(civiles)}


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _huella_tabla(tabla: pd.DataFrame) -> str:
    """Camino propio: la fórmula de ``huella_veredictos_contenido`` de reloj_sinca_v2.py (la compara una prueba)."""
    return hashlib.sha256(tabla.to_csv(index=False).encode("utf-8")).hexdigest()


def _resumen(tabla: pd.DataFrame, elegida, sha: str) -> dict:
    """Un ``resumen.json`` sintético del reloj SINCA, con las claves que ata veredictos_civiles."""
    return {"schema": "airpollution.modelo-1km-v2.reloj-sinca-red2.v1", "politica_temporal_sha256":
            "41018e4c066d9e30b5ba0b1ff92d47eeb47bab1984b5b8c45a778939359ac61c",
            "huella_veredictos_contenido": _huella_tabla(tabla), "sha256_veredictos": sha,
            "convencion_civil": {"elegida": elegida}, "series": 0}


def _h(dt: datetime) -> int:
    return int((dt - _EPOCA) / timedelta(hours=1))


def _leer_csv(ruta: Path) -> pd.DataFrame:
    return pd.read_csv(ruta, dtype=str, keep_default_na=False)


def _reescribir_manifiesto(raiz: Path, sufijo: str, tabla: pd.DataFrame, *, sumas: bool = True) -> None:
    """Reescribe un manifiesto sintético (y, con ``sumas``, su SHA256SUMS) en la carpeta temporal, como lo haría el
    descargador."""
    buf = io.StringIO()
    tabla.to_csv(buf, index=False, lineterminator="\n")
    (raiz / f"manifiesto_descarga{sufijo}.csv").write_text(buf.getvalue(), encoding="utf-8")
    if sumas:
        lineas = sorted(f"{s}  {r}" for s, r in zip(tabla["sha256"], tabla["ruta_relativa"]))
        (raiz / f"SHA256SUMS{sufijo}.txt").write_text("\n".join(lineas) + "\n", encoding="utf-8")


def _marca(etiqueta: datetime) -> str:
    return f"{etiqueta:%y%m%d};{etiqueta:%H}00;"


def _con_otro_campo(texto: str, etiqueta: datetime, campo: str) -> str:
    """El texto de una serie con el campo de ``etiqueta`` cambiado (camino propio, por la marca AAMMDD;HH00;)."""
    lineas = texto.split("\n")
    k = next(i for i, x in enumerate(lineas) if x.startswith(_marca(etiqueta)))
    lineas[k] = _marca(etiqueta) + campo + ";"
    return "\n".join(lineas)


def _con_otro_valor(texto: str) -> str:
    """El texto de una serie con el último dígito del primer valor cambiado: los mismos conteos, otros bytes."""
    lineas = texto.split("\n")
    for i, x in enumerate(lineas[1:], start=1):
        partes = x.split(";")
        if len(partes) >= 3 and partes[2] and partes[2][-1].isdigit():
            partes[2] = partes[2][:-1] + str((int(partes[2][-1]) + 1) % 10)
            lineas[i] = ";".join(partes)
            return "\n".join(lineas)
    raise AssertionError("la serie no trae valores")


def _conteos_de_texto(texto: str) -> dict[str, str]:
    """Camino propio: los conteos del manifiesto de un texto de serie (filas, con observación y no numéricas)."""
    filas = sum(1 for x in texto.splitlines()[1:] if x.strip())
    valores = _valores_de_texto(texto).values()
    finitos = sum(1 for x in valores if math.isfinite(x))
    return {"filas": str(filas), "filas_con_observacion": str(finitos),
            "filas_no_numericas": str(len(valores) - finitos)}


def _fila_nueva(raiz: Path, fila: pd.Series, ruta: str, texto: str | None = None, **cambios) -> pd.Series:
    """Una serie nueva en ``ruta`` (carpeta temporal) y su fila de manifiesto: los bytes de ``fila`` con otro valor
    (mismos conteos), o ``texto``, con ``bytes``, ``sha256`` y los conteos recalculados por el camino propio."""
    if texto is None:
        texto = _con_otro_valor((raiz / fila["ruta_relativa"]).read_text(encoding="utf-8"))
    datos = texto.encode("utf-8")
    destino = raiz / ruta
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(datos)
    nueva = fila.copy()
    nueva["ruta_relativa"], nueva["bytes"], nueva["sha256"] = ruta, str(len(datos)), _sha(datos)
    for clave, valor in {**_conteos_de_texto(texto), **cambios}.items():
        nueva[clave] = valor
    return nueva


def _valores_de_texto(texto: str) -> dict[datetime, float]:
    """Camino propio de la prueba: {etiqueta local: valor} de las filas con campo no vacío (NaN si no es número)."""
    salida = {}
    for linea in texto.splitlines()[1:]:
        if not linea.strip():
            continue
        fecha, hora, campo = linea.split(";")[:3]
        if not campo.strip():
            continue
        etiqueta = datetime(2000 + int(fecha[:2]), int(fecha[2:4]), int(fecha[4:6]), int(hora[:2]))
        try:
            x = float(campo.replace(",", "."))
        except ValueError:
            x = math.nan
        salida[etiqueta] = x if math.isfinite(x) else math.nan
    return salida


def _mapa_civil(zona: str, desde: datetime, hasta: datetime) -> dict[datetime, list[tuple[datetime, bool]]]:
    """Camino propio: de cada hora UTC a su hora de pared (conversión hacia adelante, sin ambigüedad)."""
    tz = ZoneInfo(zona)
    salida: dict[datetime, list[tuple[datetime, bool]]] = {}
    u = desde.replace(tzinfo=timezone.utc)
    while u <= hasta.replace(tzinfo=timezone.utc):
        local = u.astimezone(tz)
        salida.setdefault(local.replace(tzinfo=None), []).append((u.replace(tzinfo=None), local.dst() != timedelta(0)))
        u += timedelta(hours=1)
    return salida


def _utc_de_pared(pared: datetime, mapa) -> tuple[datetime, str, datetime | None]:
    """(UTC, tipo, alternativa) de una hora de pared: única, repetida (la estándar) o inexistente (adelante)."""
    lista = mapa.get(pared, [])
    if len(lista) == 1:
        return lista[0][0], SM.TIPO_UNIVOCA, None
    if len(lista) == 2:
        estandar = [u for u, verano in lista if not verano]
        otra = [u for u, verano in lista if verano]
        return estandar[0], SM.TIPO_AMBIGUA, otra[0]
    siguiente = min(p for p in mapa if p > pared)
    return mapa[siguiente][0][0], SM.TIPO_INEXISTENTE, None


def _esperado_civil(etiquetas, zona: str, convencion: str) -> dict[datetime, tuple[int, str, int | None]]:
    mapa = _mapa_civil(zona, min(etiquetas) - timedelta(days=2), max(etiquetas) + timedelta(days=2))
    salida = {}
    for e in etiquetas:
        pared = e if convencion == "fin" else e - timedelta(hours=1)
        u, tipo, alt = _utc_de_pared(pared, mapa)
        extra = timedelta(0) if convencion == "fin" else timedelta(hours=1)
        salida[e] = (_h(u + extra), tipo, _h(alt + extra) if alt is not None else None)
    return salida


class _ConSintetico(unittest.TestCase):
    def setUp(self):
        self.U = _umbrales()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def sintetica(self, nombre="sinca_meteorologia", **kw) -> tuple[Path, dict]:
        raiz = S.sinca_sintetico(Path(self._tmp.name) / nombre, **kw)
        return raiz, S.huellas_sinca(raiz)

    def fuera(self, nombre: str) -> Path:
        """Una carpeta temporal fuera de toda raíz SINCA (para los enlaces simbólicos)."""
        carpeta = Path(self._tmp.name) / "fuera_de_la_raiz" / nombre
        carpeta.mkdir(parents=True, exist_ok=True)
        return carpeta


# ---------------------------------------------------------------------------------------------------------------
class PruebasManifiestos(_ConSintetico):
    def test_dos_manifiestos_con_huellas(self):
        """SNC-1: los dos manifiestos, con las seis huellas (también con el alias SINCA_MET/ de fijados), disjuntos por
        serie, con las columnas del descargador salvo los valores SINCA y el nombre de su archivo."""
        raiz, huellas = self.sintetica()
        m = SM.leer_manifiestos(raiz, huellas)
        self.assertEqual(tuple(m.columns), SM.COLUMNAS_MANIFIESTO)
        self.assertEqual(SM.COLUMNAS_MANIFIESTO,
                         (*(c for c in SM.CAMPOS_MANIFIESTO if c not in SM.CAMPOS_NO_EXPUESTOS), SM.COLUMNA_MANIFIESTO))
        self.assertEqual(set(SM.CAMPOS_NO_EXPUESTOS) & set(m.columns), set())
        self.assertEqual(set(SM.CAMPOS_NO_EXPUESTOS),
                         {"primera_observacion", "ultima_observacion", "minimo", "maximo"})
        self.assertTrue(all(str(t) == "string" for t in m.dtypes))
        primero, segundo = (_leer_csv(raiz / n) for n in SM.MANIFIESTOS)
        self.assertEqual(len(m), len(primero) + len(segundo))
        self.assertEqual(list(m[SM.COLUMNA_MANIFIESTO]), [SM.MANIFIESTOS[0]] * len(primero) + [SM.MANIFIESTOS[1]] * len(segundo))
        self.assertEqual(list(m["ruta_relativa"]), list(primero["ruta_relativa"]) + list(segundo["ruta_relativa"]))
        for c in SM.CAMPOS_LEIDOS:
            self.assertEqual(list(m[c]), list(primero[c]) + list(segundo[c]))
        uno, dos = (set(zip(*(m.loc[m[SM.COLUMNA_MANIFIESTO] == n, c] for c in SM.CLAVE_SERIE)))
                    for n in SM.MANIFIESTOS)
        self.assertTrue(uno and dos)
        self.assertFalse(uno & dos)
        con_alias = {SM.ALIAS + k: v for k, v in huellas.items()}
        con_alias["ERA5L/catalogo_pixeles.parquet"] = "f" * 64            # otras claves se ignoran
        pd.testing.assert_frame_equal(SM.leer_manifiestos(raiz, con_alias), m)

    def test_huellas_que_faltan_o_no_calzan(self):
        raiz, huellas = self.sintetica()
        for nombre in SM.ARCHIVOS_HUELLA:
            with self.subTest(falta=nombre):
                with self.assertRaises(SM.ErrorSinca):
                    SM.leer_manifiestos(raiz, {k: v for k, v in huellas.items() if k != nombre})
            with self.subTest(distinta=nombre):
                with self.assertRaises(SM.ErrorSinca):
                    SM.leer_manifiestos(raiz, {**huellas, nombre: "0" * 64})
        with self.assertRaises(SM.ErrorSinca):
            SM.leer_manifiestos(raiz, {**huellas, SM.ALIAS + SM.MANIFIESTOS[0]: "1" * 64})    # dos huellas
        with self.assertRaises(TypeError):
            SM.leer_manifiestos(raiz, list(huellas))

    def test_estacion_en_los_dos_manifiestos(self):
        """SNC-1: «disjuntos» es por serie. Una estación con series en los dos manifiestos (D11 con un TEMP y una PRES
        en el segundo) se lee, y la elección de MC-10, punto 4 corre sobre los dos juntos, en los dos sentidos."""
        for desde_el_primero in ("horario_010", "horario_002"):
            with self.subTest(pasa_al_segundo=desde_el_primero):
                raiz, _ = self.sintetica(nombre=f"compartida_{desde_el_primero}")
                primero, segundo = (_leer_csv(raiz / n) for n in SM.MANIFIESTOS)
                pasa = (primero.estacion == "D11") & (primero.parametro == "TEMP") & \
                       (primero.macro_ficha == desde_el_primero)
                self.assertEqual(int(pasa.sum()), 1)
                pres = segundo[segundo.parametro == "PRES"].iloc[0]
                d11 = primero[primero.estacion == "D11"].iloc[0]
                ruta_pres = f"PRES/RM_D11_PRES_horario_002_{pres['desde']}_{pres['hasta']}.csv"
                nueva = _fila_nueva(raiz, pres, ruta_pres, region="RM", estacion="D11", nombre=d11["nombre"])
                segundo = pd.concat([segundo, primero[pasa], nueva.to_frame().T], ignore_index=True)
                _reescribir_manifiesto(raiz, "", primero[~pasa])
                _reescribir_manifiesto(raiz, SM.SUFIJO_SEGUNDO, segundo)
                m = SM.leer_manifiestos(raiz, S.huellas_sinca(raiz))
                por = m.groupby(SM.COLUMNA_MANIFIESTO)["estacion"].agg(set)
                self.assertIn("D11", por[SM.MANIFIESTOS[0]] & por[SM.MANIFIESTOS[1]])
                e, d = SM.elegir_series(m, self.U), SM.series_descartadas(m, self.U)
                temp = e[(e.estacion == "D11") & (e.parametro == "TEMP")]
                self.assertEqual(len(temp), 1)
                self.assertIn("horario_002", temp.iloc[0].ruta_relativa)
                origen = SM.MANIFIESTOS[1] if desde_el_primero == "horario_002" else SM.MANIFIESTOS[0]
                self.assertEqual(temp.iloc[0][SM.COLUMNA_MANIFIESTO], origen)
                otra = d[(d.estacion == "D11") & (d.parametro == "TEMP")]
                self.assertEqual((list(otra.motivo), len(otra)), (["no_elegida"], 1))
                self.assertEqual(list(d.loc[d.ruta_relativa == ruta_pres, "motivo"]), ["variable_no_autorizada"])
                t = SM.series_horarias(raiz, e, POLITICA_PRUEBA, self.U, veredictos=_veredictos())
                self.assertEqual(set(t.loc[t.estacion == "D11", "variable"]), set(tipos.VARIABLES_SINCA))

    def test_manifiestos_que_no_son_disjuntos_por_serie(self):
        """SNC-1: una misma serie (estacion, parametro, macro_ficha), una misma ruta relativa o un mismo sha256 en los
        dos manifiestos detiene la lectura; una estación con dos regiones, también. Dentro de un manifiesto, dos
        rangos de fechas de una misma serie se aceptan (el segundo descargador los distingue por desde y hasta)."""
        def caso(nombre, armar):
            raiz, _ = self.sintetica(nombre=f"no_disjuntos_{nombre}")
            primero, segundo = (_leer_csv(raiz / n) for n in SM.MANIFIESTOS)
            base = primero[(primero.estacion == "D11") & (primero.parametro == "TEMP")
                           & (primero.macro_ficha == "horario_002")].iloc[0]
            primero, segundo = armar(raiz, primero, segundo, base)
            _reescribir_manifiesto(raiz, "", primero)
            _reescribir_manifiesto(raiz, SM.SUFIJO_SEGUNDO, segundo)
            return raiz

        def misma_serie(raiz, primero, segundo, base):
            otra = _fila_nueva(raiz, base, base["ruta_relativa"].replace(".csv", "_otro_rango.csv"))
            return primero, pd.concat([segundo, otra.to_frame().T], ignore_index=True)

        def misma_ruta(raiz, primero, segundo, base):
            otra = base.copy()
            otra["estacion"], otra["sha256"] = "D19", "a" * 64
            return primero, pd.concat([segundo, otra.to_frame().T], ignore_index=True)

        def mismo_sha(raiz, primero, segundo, base):
            texto = (raiz / base["ruta_relativa"]).read_text(encoding="utf-8")
            otra = _fila_nueva(raiz, base, "TEMP/RM_D19_TEMP_horario_002_copia.csv", texto=texto, estacion="D19")
            return primero, pd.concat([segundo, otra.to_frame().T], ignore_index=True)

        def dos_regiones(raiz, primero, segundo, base):
            otra = _fila_nueva(raiz, base, "TEMP/V_D11_TEMP_horario_003_x.csv", region="V", macro_ficha="horario_003")
            return primero, pd.concat([segundo, otra.to_frame().T], ignore_index=True)

        for nombre, armar, patron in (("serie", misma_serie, "disjuntos por serie.*clave de serie"),
                                      ("ruta", misma_ruta, "disjuntos por serie.*ruta_relativa"),
                                      ("sha", mismo_sha, "disjuntos por serie.*sha256"),
                                      ("region", dos_regiones, "dos regiones")):
            with self.subTest(caso=nombre):
                raiz = caso(nombre, armar)
                with self.assertRaisesRegex(SM.ErrorSinca, patron):
                    SM.leer_manifiestos(raiz, S.huellas_sinca(raiz))

        def dos_rangos(raiz, primero, segundo, base):
            otra = _fila_nueva(raiz, base, base["ruta_relativa"].replace(".csv", "_otro_rango.csv"))
            return pd.concat([primero, otra.to_frame().T], ignore_index=True), segundo

        raiz = caso("dos_rangos", dos_rangos)
        m = SM.leer_manifiestos(raiz, S.huellas_sinca(raiz))
        e = SM.elegir_series(m, self.U)
        self.assertEqual(len(e[(e.estacion == "D11") & (e.parametro == "TEMP")]), 1)

    def test_sumas_rutas_y_conteos(self):
        """SHA256SUMS lista las mismas series; rutas relativas sin «..»; conteos enteros; una región por estación."""
        casos = {
            "sumas": lambda t: t,
            "ruta": lambda t: t.assign(ruta_relativa=["../" + r for r in t["ruta_relativa"]]),
            "absoluta": lambda t: t.assign(ruta_relativa=["/" + r for r in t["ruta_relativa"]]),
            "conteo": lambda t: t.assign(filas=["7,5"] * len(t)),
            "sha": lambda t: t.assign(sha256=["X" * 64] * len(t)),
            "region": lambda t: t.assign(region=["RM"] + ["RV"] * (len(t) - 1)),
        }
        for caso, cambio in casos.items():
            with self.subTest(caso=caso):
                raiz, _ = self.sintetica(nombre=f"sinca_{caso}")
                primero = cambio(_leer_csv(raiz / SM.MANIFIESTOS[0]))
                _reescribir_manifiesto(raiz, "", primero)
                if caso == "sumas":
                    lineas = (raiz / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
                    (raiz / "SHA256SUMS.txt").write_text("\n".join(lineas[1:]) + "\n", encoding="utf-8")
                with self.assertRaises(SM.ErrorSinca):
                    SM.leer_manifiestos(raiz, S.huellas_sinca(raiz))

    def test_sha256_del_manifiesto_y_lineas_repetidas(self):
        """SNC-1, guardas propias: un sha256 inválido en una fila del manifiesto con su SHA256SUMS válido, y una línea
        repetida en SHA256SUMS (con el mismo conjunto de pares), detienen la lectura con su motivo."""
        raiz, _ = self.sintetica(nombre="sha_invalido")
        primero = _leer_csv(raiz / SM.MANIFIESTOS[0])
        primero.loc[0, "sha256"] = primero.loc[0, "sha256"].upper()
        _reescribir_manifiesto(raiz, "", primero, sumas=False)
        with self.assertRaisesRegex(SM.ErrorSinca, "sha256 inválido"):
            SM.leer_manifiestos(raiz, S.huellas_sinca(raiz))
        raiz, _ = self.sintetica(nombre="repetidas")
        sumas = raiz / "SHA256SUMS.txt"
        lineas = sumas.read_text(encoding="utf-8").splitlines()
        sumas.write_text("\n".join([*lineas, lineas[0]]) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(SM.ErrorSinca, "repetidas"):
            SM.leer_manifiestos(raiz, S.huellas_sinca(raiz))

    def test_columnas_del_manifiesto(self):
        raiz, _ = self.sintetica()
        primero = _leer_csv(raiz / SM.MANIFIESTOS[0]).drop(columns=["instrumento_ficha"])
        _reescribir_manifiesto(raiz, "", primero)
        with self.assertRaisesRegex(SM.ErrorSinca, "columnas"):
            SM.leer_manifiestos(raiz, S.huellas_sinca(raiz))

    def test_guarda_de_rutas_de_los_archivos_de_huella(self):
        """SNC-15: un archivo de huella que es un enlace simbólico (a una copia idéntica fuera de la raíz, sin permiso
        de lectura) se rechaza antes de leerlo; la raíz misma sí puede ser un enlace."""
        raiz, huellas = self.sintetica(nombre="enlace_manifiesto")
        for nombre in (SM.MANIFIESTOS[0], "SHA256SUMS_20261024b.txt"):
            with self.subTest(archivo=nombre):
                copia = self.fuera(nombre) / nombre
                copia.write_bytes((raiz / nombre).read_bytes())
                copia.chmod(0o000)
                self.addCleanup(copia.chmod, 0o600)
                original = (raiz / nombre).read_bytes()
                (raiz / nombre).unlink()
                (raiz / nombre).symlink_to(copia)
                with self.assertRaisesRegex(SM.ErrorSinca, "enlace simbólico"):
                    SM.leer_manifiestos(raiz, huellas)
                (raiz / nombre).unlink()
                (raiz / nombre).write_bytes(original)
        enlace = Path(self._tmp.name) / "raiz_enlazada"
        enlace.symlink_to(raiz, target_is_directory=True)
        pd.testing.assert_frame_equal(SM.leer_manifiestos(enlace, huellas), SM.leer_manifiestos(raiz, huellas))

    def test_como_el_descargador_y_fijados(self):
        """CAMPOS_MANIFIESTO, las unidades, la regla de las filas y las acciones son las del descargador (AST, con
        su huella); los nombres de las huellas son los de fijados.HUELLAS_DATOS y de sintetico."""
        from reloj_dmc import fijados as fijados_reloj
        self.assertEqual({SM.ALIAS + n for n in SM.ARCHIVOS_HUELLA} - set(fijados.HUELLAS_DATOS), set())
        self.assertEqual(SM.SHA_POLITICA_TEMPORAL, fijados.SHA_POLITICA_TEMPORAL)
        self.assertEqual(SM.SHA_POLITICA_TEMPORAL, S.POLITICA_TEMPORAL_SHA)
        self.assertEqual(SM.SUFIJO_SEGUNDO, S.SUFIJO_SEGUNDO_MANIFIESTO)
        if not _DESCARGADOR.is_file() or _sha(_DESCARGADOR.read_bytes()) != _SHA_DESCARGADOR:
            self.skipTest("descargar_sinca_meteorologia.py falta o no tiene la huella de M0; no se da por aprobada")
        codigo = fijados_reloj.extraer_por_ast(_DESCARGADOR, _SHA_DESCARGADOR,
                                               ("CAMPOS_MANIFIESTO", "PARAMETROS", "_RE_DATO"), {"re": re})
        self.assertEqual(SM.CAMPOS_MANIFIESTO, tuple(codigo["CAMPOS_MANIFIESTO"]))
        self.assertEqual(SM.UNIDADES, {p: u for p, (_, u) in codigo["PARAMETROS"].items()})
        self.assertEqual(tuple(SM.UNIDADES), tipos.VARIABLES_SINCA)
        self.assertEqual(SM._RE_DATO.pattern, codigo["_RE_DATO"].pattern)
        fuente = _DESCARGADOR.read_text(encoding="utf-8")
        self.assertEqual(set(SM.ACCIONES_PUBLICADAS), set(re.findall(r'\baccion = "([^"]+)"', fuente)))
        self.assertEqual(len(SM.ACCIONES_PUBLICADAS), len(set(SM.ACCIONES_PUBLICADAS)))

    def test_como_el_segundo_descargador(self):
        """El segundo manifiesto (descargar_sinca_ampliacion.py, con su huella): publica con las acciones de
        ``_obtener`` (las mismas de ACCIONES_PUBLICADAS), escribe con ``smet.CAMPOS_MANIFIESTO`` y deja fuera las
        series ya publicadas por (región, estación, parámetro, macro), no por estación (SNC-1)."""
        if not _AMPLIACION.is_file() or _sha(_AMPLIACION.read_bytes()) != _SHA_AMPLIACION:
            self.skipTest("descargar_sinca_ampliacion.py falta o cambió de huella; no se da por aprobada")
        fuente = _AMPLIACION.read_text(encoding="utf-8")
        obtener = next(n for n in ast.parse(fuente).body if isinstance(n, ast.FunctionDef) and n.name == "_obtener")
        acciones = set()
        for nodo in ast.walk(obtener):
            if isinstance(nodo, ast.Return) and isinstance(nodo.value, ast.Tuple) and len(nodo.value.elts) == 3:
                primero, ultimo = nodo.value.elts[0], nodo.value.elts[2]
                if not (isinstance(primero, ast.Constant) and primero.value is None):
                    self.assertIsInstance(ultimo, ast.Constant)
                    acciones.add(ultimo.value)
        self.assertEqual(acciones, set(SM.ACCIONES_PUBLICADAS))
        self.assertIn("escribir_csv_atomico(ruta_m, smet.CAMPOS_MANIFIESTO,", fuente)
        self.assertIn('claves.add((f["region"], f["estacion"], f["parametro"], f["macro_ficha"]))', fuente)
        self.assertEqual(SM.CLAVE_SERIE, ("estacion", "parametro", "macro_ficha"))


# ---------------------------------------------------------------------------------------------------------------
class PruebasEleccion(_ConSintetico):
    def test_eleccion_de_serie_mc10(self):
        """MC-10, punto 4: la de altura más cercana a 2 m (TEMP, RHUM) o 10 m (WSPD, WDIR); empate por filas con
        observación y luego por ruta. Una por estación × variable; cada serie elegida o descartada con su motivo."""
        raiz, huellas = self.sintetica()
        m = SM.leer_manifiestos(raiz, huellas)
        e = SM.elegir_series(m, self.U)
        d = SM.series_descartadas(m, self.U)
        self.assertEqual(tuple(e.columns), SM.COLUMNAS_ELEGIDAS)
        self.assertEqual(set(SM.CAMPOS_NO_EXPUESTOS) & set(e.columns), set())
        self.assertEqual(tuple(d.columns), SM.COLUMNAS_DESCARTE)
        self.assertEqual(str(e["altura_m"].dtype), "float64")
        self.assertEqual(sorted(list(e["ruta_relativa"]) + list(d["ruta_relativa"])), sorted(m["ruta_relativa"]))
        claves = list(zip(e["estacion"], e["parametro"]))
        self.assertEqual(len(set(claves)), len(claves))
        esperadas = [(est, p) for est in sorted(set(m["estacion"])) for p in tipos.VARIABLES_SINCA]
        self.assertEqual(claves, esperadas)
        self.assertEqual(set(d["motivo"]) - set(SM.MOTIVOS_DESCARTE), set())
        # D11: TEMP a 2 m y a 10 m → la de 2 m.
        d11 = e[(e.estacion == "D11") & (e.parametro == "TEMP")].iloc[0]
        self.assertEqual(float(d11.altura_m), float(constantes.valor("ALTURA_T_M")))
        self.assertIn("horario_002", d11.ruta_relativa)
        # D12: dos TEMP a 2 m → la de más filas con observación (la de huecos queda «no_elegida»).
        d12 = m[(m.estacion == "D12") & (m.parametro == "TEMP")]
        mas = d12.loc[d12["filas_con_observacion"].astype(int).idxmax(), "ruta_relativa"]
        self.assertEqual(e[(e.estacion == "D12") & (e.parametro == "TEMP")].iloc[0].ruta_relativa, mas)
        self.assertEqual(sorted(d.loc[d.motivo == "no_elegida", "estacion"]), ["D11", "D12"])
        # Viento a 10 m (con una sola serie por estación; la prueba que decide es test_altura_objetivo_por_variable).
        for p in ("WSPD", "WDIR"):
            self.assertTrue((e.loc[e.parametro == p, "altura_m"] == float(constantes.valor("ALTURA_VIENTO_M"))).all())
        # MC-10, punto 6: PRES, RAIN y GLOB no entran.
        self.assertEqual(sorted(d.loc[d.motivo == "variable_no_autorizada", "parametro"]), ["GLOB", "PRES", "RAIN"])
        # umbrales no interviene en la elección (SNC-4).
        pd.testing.assert_frame_equal(SM.elegir_series(m, None), e)

    def test_altura_objetivo_por_variable(self):
        """MC-10, punto 4 (SNC-4): el objetivo es 2 m en TEMP y RHUM y 10 m en WSPD y WDIR. Con dos series de una
        misma variable, la de la altura equivocada lleva más filas con observación y la menor ruta, así que sólo la
        distancia a su objetivo la deja fuera."""
        raiz, huellas = self.sintetica()
        m = SM.leer_manifiestos(raiz, huellas)
        t_m, viento_m = float(constantes.valor("ALTURA_T_M")), float(constantes.valor("ALTURA_VIENTO_M"))
        # (variable, altura que debe ganar, altura que debe perder): pares de alturas que dan elecciones distintas
        # con el objetivo de 2 m y con el de 10 m.
        pares = [("WSPD", viento_m, t_m), ("WDIR", viento_m, t_m), ("RHUM", t_m, viento_m), ("TEMP", t_m, viento_m),
                 ("WSPD", 12.0, 7.0), ("WDIR", 12.0, 7.0), ("RHUM", 1.0, 4.0), ("TEMP", 1.0, 4.0)]
        for variable, gana, pierde in pares:
            with self.subTest(variable=variable, gana=gana, pierde=pierde):
                base = m[(m.estacion == "D11") & (m.parametro == variable)].iloc[[0]]
                filas = pd.concat([base, base], ignore_index=True)
                filas["altura_ficha"] = [f"{gana:g}", f"{pierde:g}"]
                filas["macro_ficha"] = "horario_000"
                filas["filas_con_observacion"] = ["10", "20"]
                filas["ruta_relativa"] = [f"{variable}/z_gana.csv", f"{variable}/a_pierde.csv"]
                e = SM.elegir_series(filas, self.U)
                self.assertEqual(list(e["ruta_relativa"]), [f"{variable}/z_gana.csv"])
                self.assertEqual(float(e.iloc[0].altura_m), gana)
                d = SM.series_descartadas(filas, self.U)
                self.assertEqual(list(zip(d.ruta_relativa, d.motivo)), [(f"{variable}/a_pierde.csv", "no_elegida")])
        self.assertEqual(SM.OBJETIVO_ALTURA, {"TEMP": "ALTURA_T_M", "RHUM": "ALTURA_T_M", "WSPD": "ALTURA_VIENTO_M",
                                              "WDIR": "ALTURA_VIENTO_M"})

    def test_empates_por_distancia_filas_y_ruta(self):
        raiz, huellas = self.sintetica()
        m = SM.leer_manifiestos(raiz, huellas)
        base = m[(m.estacion == "D11") & (m.parametro == "TEMP")].copy()
        a, b = base.index
        # 1,5 m y 2,5 m: misma distancia a 2 m → gana la de más filas con observación.
        base.loc[a, ["altura_ficha", "macro_ficha", "filas_con_observacion"]] = ["1,5", "horario_000", "10"]
        base.loc[b, ["altura_ficha", "macro_ficha", "filas_con_observacion"]] = ["2.5 m", "horario_000", "11"]
        self.assertEqual(SM.elegir_series(base, self.U).iloc[0].ruta_relativa, base.loc[b, "ruta_relativa"])
        # Mismas filas → gana la de menor ruta relativa.
        base.loc[a, "filas_con_observacion"] = "11"
        menor = min(base.loc[a, "ruta_relativa"], base.loc[b, "ruta_relativa"])
        self.assertEqual(SM.elegir_series(base, self.U).iloc[0].ruta_relativa, menor)
        # El orden de las filas no cambia la elección.
        self.assertEqual(SM.elegir_series(base.iloc[::-1], self.U).iloc[0].ruta_relativa, menor)

    def test_altura_de(self):
        """SNC-3: altura_ficha primero, NNN de la macro después; discrepancia o sin dato → fuera."""
        casos = [("2", "horario_002", (2.0, "ficha")), ("2 m", "", (2.0, "ficha")), ("2,0 mts", "x", (2.0, "ficha")),
                 ("10 metros", "horario_010_spec", (10.0, "ficha")), ("", "horario_010", (10.0, "macro")),
                 ("s/i", "horario_002_b", (2.0, "macro")), ("", "horario_000", (None, "sin_altura")),
                 ("0", "horario_000", (None, "sin_altura")), ("2", "horario_010", (None, "altura_discrepante")),
                 ("", "", (None, "sin_altura"))]
        for ficha, macro, esperado in casos:
            with self.subTest(ficha=ficha, macro=macro):
                self.assertEqual(SM.altura_de(ficha, macro), esperado)

    def test_series_que_no_entran(self):
        """SNC-2 y SNC-3: una serie que no puede entrar no se elige aunque esté más cerca de la altura objetivo. Las dos
        acciones con que publican los descargadores («descargado» y «reutilizado_en_disco») sí entran."""
        raiz, huellas = self.sintetica()
        m = SM.leer_manifiestos(raiz, huellas)
        base = m[(m.estacion == "D11") & (m.parametro == "TEMP")].copy()
        cerca = base.index[base["altura_ficha"] == "2"][0]
        lejos = base.index[base["altura_ficha"] == "10"][0]
        cambios = {"unidad_distinta": ("unidad_ficha", "K"), "accion_no_publicada": ("accion", "omitido"),
                   "marca_temporal_distinta": ("marca_temporal", "utc"),
                   "politica_temporal_distinta": ("politica_temporal_sha256", "0" * 64),
                   "sin_altura": ("altura_ficha", ""), "altura_discrepante": ("altura_ficha", "3")}
        for motivo, (campo, valor) in cambios.items():
            with self.subTest(motivo=motivo):
                t = base.copy()
                t.loc[cerca, campo] = valor
                if motivo == "sin_altura":
                    t.loc[cerca, "macro_ficha"] = "horario_000"
                e, d = SM.elegir_series(t, self.U), SM.series_descartadas(t, self.U)
                self.assertEqual(list(e["ruta_relativa"]), [t.loc[lejos, "ruta_relativa"]])
                self.assertEqual(list(d["motivo"]), [motivo])
        for accion in SM.ACCIONES_PUBLICADAS:
            with self.subTest(accion=accion):
                t = base.copy()
                t.loc[cerca, "accion"] = accion
                t.loc[lejos, "accion"] = "descargado"
                e, d = SM.elegir_series(t, self.U), SM.series_descartadas(t, self.U)
                self.assertEqual(list(e["ruta_relativa"]), [t.loc[cerca, "ruta_relativa"]])
                self.assertEqual(list(d["motivo"]), ["no_elegida"])
        self.assertEqual(set(SM.ACCIONES_PUBLICADAS), {"descargado", "reutilizado_en_disco"})


# ---------------------------------------------------------------------------------------------------------------
class PruebasReloj(_ConSintetico):
    def _series(self, raiz, huellas, veredictos, cambio=None):
        m = SM.leer_manifiestos(raiz, huellas)
        e = SM.elegir_series(m, self.U)
        if cambio is not None:
            e = cambio(e)
        return e, SM.series_horarias(raiz, e, POLITICA_PRUEBA, self.U, veredictos=veredictos)

    def _esperado(self, raiz, e, estacion, variable, civil: dict | None):
        """Camino propio: {h: (valor, válido, n.º de etiquetas)} de una serie, con la regla general o la civil. El
        valor es la media de los válidos o, sin válidos, la de los finitos (NaN si no hay)."""
        fila = e[(e.estacion == estacion) & (e.parametro == variable)].iloc[0]
        valores = _valores_de_texto((raiz / fila.ruta_relativa).read_text(encoding="utf-8"))
        bajo, alto = (self.U.a(i) for i in SM.RANGO[variable])
        if civil is not None:
            mapa = _esperado_civil(sorted(valores), civil["zona"], civil["convencion"])
        por_h: dict[int, list[float]] = {}
        for etiqueta, x in valores.items():
            h = mapa[etiqueta][0] if civil is not None else _h(etiqueta + timedelta(hours=4))
            por_h.setdefault(h, []).append(x)
        salida = {}
        for h, xs in por_h.items():
            ok = [x for x in xs if math.isfinite(x) and bajo <= x <= alto]
            finitos = [x for x in xs if math.isfinite(x)]
            valor = float(np.mean(ok)) if ok else (float(np.mean(finitos)) if finitos else math.nan)
            salida[h] = (valor, bool(ok), len(xs))
        return salida

    def test_reloj_utc4_o_civil(self):
        """R7 (MC-10, punto 1): UTC−4 fijo con la etiqueta al fin (h = etiqueta + 4 h) salvo el estación-año con
        veredicto «hora_civil», que va con su zona IANA y la convención de T4. En el atraso de abril de 2019 la hora
        repetida toma la ocurrencia estándar y registra la otra; una estación sin veredicto sigue UTC−4."""
        raiz, huellas = self.sintetica(desde="2019-04-05", hasta="2019-04-08")
        for convencion in SM.CONVENCIONES:
            with self.subTest(convencion=convencion):
                e, t = self._series(raiz, huellas, _veredictos(convencion, [("D11", 2019), ("D11", 2018)]))
                for estacion in ("D11", "D12"):
                    civil = {"zona": "America/Santiago", "convencion": convencion} if estacion == "D11" else None
                    esperado = self._esperado(raiz, e, estacion, "TEMP", civil)
                    sub = t[(t.estacion == estacion) & (t.variable == "TEMP")]
                    self.assertEqual(list(sub["h"]), sorted(esperado))
                    np.testing.assert_allclose(sub["valor"].to_numpy(), [esperado[h][0] for h in sub["h"]])
                registro = {r["serie"]: r for r in t.attrs["registro_sinca"]["series"]}
                r11 = next(r for r in registro.values() if r["estacion"] == "D11" and r["variable"] == "TEMP")
                r12 = next(r for r in registro.values() if r["estacion"] == "D12" and r["variable"] == "TEMP")
                self.assertEqual((r11["anios_civiles"], r11["zona"], r11["etiquetas_ambiguas"]),
                                 ([2019], "America/Santiago", 1))
                self.assertEqual((r12["anios_civiles"], r12["etiquetas_ambiguas"], r12["alternativas"]), ([], 0, []))
                # La hora repetida (23:00 del sábado con «fin», 00:00 del domingo con «inicio_mas_1h»): estándar
                # (UTC−4) y alternativa de verano (UTC−3), una hora antes.
                repetida = datetime(2019, 4, 6, 23) if convencion == "fin" else datetime(2019, 4, 7, 0)
                fin = repetida + timedelta(hours=4)
                self.assertEqual(r11["alternativas"], [[_h(fin), _h(fin) - 1]])
        # Sin veredictos civiles: todo UTC−4, las dos estaciones iguales a la regla general.
        e, t = self._series(raiz, huellas, _veredictos())
        for estacion in ("D11", "D12"):
            esperado = self._esperado(raiz, e, estacion, "TEMP", None)
            self.assertEqual(list(t[(t.estacion == estacion) & (t.variable == "TEMP")]["h"]), sorted(esperado))
        primera = datetime(2019, 4, 5, 1)
        self.assertEqual(int(t["h"].min()), _h(primera + timedelta(hours=4)))

    def test_zona_iana_de_la_region(self):
        """MC-10, punto 1 (SNC-7): una estación civil va con la zona IANA de su región (zonas_iana_por_region), no con
        la de omisión. D11 en RXII (2019) o en RXI (2025), que no cambian de hora en abril de ese año, y D12 en RM,
        que sí; las h de D11 son las de su zona y distintas de las de America/Santiago."""
        casos = (("RXII", "America/Punta_Arenas", "2019-04-05", "2019-04-08", 2019),
                 ("RXI", "America/Coyhaique", "2025-04-04", "2025-04-07", 2025))
        for region, zona, desde, hasta, anio in casos:
            raiz, huellas = self.sintetica(nombre=f"zona_{region}", desde=desde, hasta=hasta)
            for convencion in SM.CONVENCIONES:
                with self.subTest(region=region, convencion=convencion):
                    def a_la_region(e):
                        e = e.copy()
                        e.loc[e.estacion == "D11", "region"] = region
                        return e
                    e, t = self._series(raiz, huellas, _veredictos(convencion, [("D11", anio), ("D12", anio)]),
                                        cambio=a_la_region)
                    for estacion, z in (("D11", zona), ("D12", "America/Santiago")):
                        esperado = self._esperado(raiz, e, estacion, "TEMP", {"zona": z, "convencion": convencion})
                        sub = t[(t.estacion == estacion) & (t.variable == "TEMP")]
                        self.assertEqual(list(sub["h"]), sorted(esperado))
                        np.testing.assert_allclose(sub["valor"].to_numpy(), [esperado[h][0] for h in sub["h"]])
                    santiago = self._esperado(raiz, e, "D11", "TEMP", {"zona": "America/Santiago",
                                                                       "convencion": convencion})
                    d11 = t[(t.estacion == "D11") & (t.variable == "TEMP")]
                    self.assertNotEqual(list(d11["h"]), sorted(santiago))
                    registro = {(r["estacion"], r["variable"]): r for r in t.attrs["registro_sinca"]["series"]}
                    for variable in tipos.VARIABLES_SINCA:
                        self.assertEqual((registro["D11", variable]["region"], registro["D11", variable]["zona"]),
                                         (region, zona))
                        self.assertEqual(registro["D12", variable]["zona"], "America/Santiago")
                    self.assertEqual(registro["D11", "TEMP"]["etiquetas_ambiguas"], 0)
                    self.assertEqual(registro["D12", "TEMP"]["etiquetas_ambiguas"], 1)

    def test_hora_inexistente_y_colision(self):
        """R7: en el adelanto de septiembre de 2019 la etiqueta inexistente se desplaza hacia adelante y cae en la
        misma hora UTC que la siguiente: se promedian los válidos, con conteo. En WDIR la hora queda inválida."""
        raiz, huellas = self.sintetica(desde="2019-09-06", hasta="2019-09-09")
        for convencion in SM.CONVENCIONES:
            with self.subTest(convencion=convencion):
                e, t = self._series(raiz, huellas, _veredictos(convencion, [("D11", 2019)]))
                civil = {"zona": "America/Santiago", "convencion": convencion}
                for variable in ("TEMP", "RHUM", "WSPD"):
                    esperado = self._esperado(raiz, e, "D11", variable, civil)
                    sub = t[(t.estacion == "D11") & (t.variable == variable)].set_index("h")
                    self.assertEqual(sorted(sub.index), sorted(esperado))
                    for h, (v, ok, n) in esperado.items():
                        self.assertEqual(bool(sub.loc[h, "valido"]), ok)
                        if ok:
                            self.assertAlmostEqual(float(sub.loc[h, "valor"]), v, places=12)
                    dobles = [[h, n] for h, (_, _, n) in sorted(esperado.items()) if n > 1]
                    self.assertEqual(len(dobles), 1)
                    registro = next(r for r in t.attrs["registro_sinca"]["series"]
                                    if r["estacion"] == "D11" and r["variable"] == variable)
                    self.assertEqual(registro["colisiones"], dobles)
                    self.assertEqual(registro["etiquetas_inexistentes"], 1)
                wdir = t[(t.estacion == "D11") & (t.variable == "WDIR")].set_index("h")
                h_doble = registro["colisiones"][0][0]
                self.assertFalse(bool(wdir.loc[h_doble, "valido"]))
                self.assertTrue(math.isnan(float(wdir.loc[h_doble, "valor"])))
                self.assertTrue(wdir.drop(index=h_doble)["valido"].all())

    def test_colision_con_validos_e_invalidos(self):
        """R7, punto 4 y SNC-8, en una serie: la etiqueta inexistente de septiembre trae un valor fuera de rango (TEMP),
        las dos etiquetas de la colisión vienen fuera de rango (RHUM) o la inexistente no es numérica (WSPD). Se
        promedian sólo los válidos; la hora es válida si alguno lo es; sin válidos, la media de los finitos, inválida."""
        for convencion in SM.CONVENCIONES:
            with self.subTest(convencion=convencion):
                raiz, _ = self.sintetica(nombre=f"colision_{convencion}", desde="2019-09-06", hasta="2019-09-09")
                primero = _leer_csv(raiz / SM.MANIFIESTOS[0])
                cambios = {}
                for variable in ("TEMP", "RHUM", "WSPD"):
                    k = primero.index[(primero.estacion == "D11") & (primero.parametro == variable)
                                      & (primero.altura_ficha == ("10" if variable == "WSPD" else "2"))][0]
                    ruta = raiz / primero.loc[k, "ruta_relativa"]
                    texto = ruta.read_text(encoding="utf-8")
                    mapa = _esperado_civil(sorted(_valores_de_texto(texto)), "America/Santiago", convencion)
                    inexistente = next(x for x, (_, tipo, _) in mapa.items() if tipo == SM.TIPO_INEXISTENTE)
                    otra = next(x for x, (h, _, _) in mapa.items() if h == mapa[inexistente][0] and x != inexistente)
                    alto = self.U.a(SM.RANGO[variable][1])
                    coma = lambda x: f"{x:.1f}".replace(".", ",")  # noqa: E731
                    if variable == "TEMP":
                        texto = _con_otro_campo(texto, inexistente, coma(alto + 10))
                    elif variable == "RHUM":
                        texto = _con_otro_campo(_con_otro_campo(texto, inexistente, coma(alto + 10)), otra,
                                                coma(alto + 20))
                    else:
                        texto = _con_otro_campo(texto, inexistente, "s/d")
                    nueva = _fila_nueva(raiz, primero.loc[k], primero.loc[k, "ruta_relativa"], texto=texto)
                    primero.loc[k] = nueva
                    cambios[variable] = (mapa[inexistente][0], _valores_de_texto(texto)[otra], alto)
                _reescribir_manifiesto(raiz, "", primero)
                e, t = self._series(raiz, S.huellas_sinca(raiz), _veredictos(convencion, [("D11", 2019)]))
                registro = {(r["estacion"], r["variable"]): r for r in t.attrs["registro_sinca"]["series"]}
                for variable, (h, valor_otra, alto) in cambios.items():
                    fila = t[(t.estacion == "D11") & (t.variable == variable) & (t.h == h)].iloc[0]
                    if variable == "RHUM":
                        self.assertFalse(bool(fila.valido))
                        self.assertAlmostEqual(float(fila.valor), alto + 15, places=9)
                    else:
                        self.assertTrue(bool(fila.valido))
                        self.assertEqual(float(fila.valor), valor_otra)
                    self.assertEqual(registro["D11", variable]["colisiones"], [[h, 2]])
                    esperado = self._esperado(raiz, e, "D11", variable, {"zona": "America/Santiago",
                                                                         "convencion": convencion})
                    sub = t[(t.estacion == "D11") & (t.variable == variable)]
                    np.testing.assert_allclose(sub["valor"].to_numpy(), [esperado[x][0] for x in sub["h"]])
                    self.assertEqual(list(sub["valido"]), [esperado[x][1] for x in sub["h"]])
                self.assertEqual([registro["D11", v]["fuera_de_rango"] for v in ("TEMP", "RHUM", "WSPD")], [1, 2, 0])
                self.assertEqual(registro["D11", "WSPD"]["filas_no_numericas"], 1)

    def test_unir_colisiones_a_mano(self):
        """SNC-8, caso por caso: válida más fuera de rango, todas fuera de rango, NaN más válida, sólo NaN, tres
        etiquetas y WDIR; sin colisión, la hora queda como viene. El orden de las etiquetas no cambia nada."""
        nan = math.nan
        casos = [
            ("válida y fuera de rango", "TEMP", [5, 5], [10.0, 99.0], [True, False], 10.0, True),
            ("todas fuera de rango", "TEMP", [5, 5], [99.0, 101.0], [False, False], 100.0, False),
            ("NaN y válida", "RHUM", [5, 5], [nan, 7.0], [False, True], 7.0, True),
            ("sólo NaN", "WSPD", [5, 5], [nan, nan], [False, False], nan, False),
            ("NaN y fuera de rango", "WSPD", [5, 5], [nan, 80.0], [False, False], 80.0, False),
            ("dos válidas y una fuera", "TEMP", [5, 5, 5], [10.0, 99.0, 12.0], [True, False, True], 11.0, True),
            ("WDIR", "WDIR", [5, 5], [350.0, 10.0], [True, True], nan, False),
        ]
        for nombre, variable, h, valor, valido, v_esperado, ok_esperado in casos:
            for invertir in (False, True):
                with self.subTest(caso=nombre, invertido=invertir):
                    hs, vs, oks = (np.array(x[::-1] if invertir else x) for x in (h, valor, valido))
                    hs = np.concatenate([hs, [3, 7]]).astype(np.int64)
                    vs = np.concatenate([vs, [1.0, 2.0]]).astype(np.float64)
                    oks = np.concatenate([oks, [True, False]]).astype(bool)
                    unicas, v_out, ok_out, colisiones = SM._unir_colisiones(hs, vs, oks, variable)
                    self.assertEqual(list(unicas), [3, 5, 7])
                    self.assertEqual(colisiones, [[5, len(h)]])
                    self.assertEqual(list(ok_out), [True, ok_esperado, False])
                    if math.isnan(v_esperado):
                        self.assertTrue(math.isnan(v_out[1]))
                    else:
                        self.assertAlmostEqual(float(v_out[1]), v_esperado, places=12)
                    self.assertEqual((float(v_out[0]), float(v_out[2])), (1.0, 2.0))

    def test_ano_local_de_la_etiqueta(self):
        """El veredicto es por año local de la etiqueta: con 2020 civil y 2019 fijo, la última etiqueta de 2019
        (UTC−4) y la primera de 2020 (verano, UTC−3) caen en la misma hora UTC."""
        raiz, huellas = self.sintetica(desde="2019-12-31", hasta="2020-01-01")
        e, t = self._series(raiz, huellas, _veredictos("fin", [("D11", 2020)]))
        registro = next(r for r in t.attrs["registro_sinca"]["series"] if r["estacion"] == "D11" and r["variable"] == "TEMP")
        u = datetime(2020, 1, 1, 3)
        self.assertEqual(registro["colisiones"], [[_h(u), 2]])
        self.assertEqual(registro["anios_civiles"], [2020])
        sub = t[(t.estacion == "D11") & (t.variable == "TEMP")]
        self.assertEqual(int(sub["h"].min()), _h(datetime(2019, 12, 31, 1) + timedelta(hours=4)))
        self.assertEqual(int(sub["h"].max()), _h(datetime(2020, 1, 1, 23) + timedelta(hours=3)))

    def test_horas_fin_utc_independiente(self):
        """horas_fin_utc contra el camino propio de la prueba, todo 2019 y 2016, en las tres zonas de la política
        (Magallanes sin cambio de hora desde 2016), con las dos convenciones."""
        for zona in ("America/Santiago", "America/Coyhaique", "America/Punta_Arenas"):
            for anio in (2016, 2019, 2025):
                etiquetas = [datetime(anio, 1, 1) + timedelta(hours=k) for k in range(1, 366 * 24)]
                etiquetas = [x for x in etiquetas if x.year == anio]
                for convencion in SM.CONVENCIONES:
                    with self.subTest(zona=zona, anio=anio, convencion=convencion):
                        r = SM.horas_fin_utc(np.array(etiquetas, dtype="datetime64[h]"), np.ones(len(etiquetas), bool),
                                             zona=zona, convencion=convencion)
                        esperado = _esperado_civil(etiquetas, zona, convencion)
                        self.assertEqual(list(r["h"]), [esperado[x][0] for x in etiquetas])
                        self.assertEqual(list(r["tipo"]), [esperado[x][1] for x in etiquetas])
                        alt = [None if pd.isna(v) else int(v) for v in r["h_alternativa"]]
                        self.assertEqual(alt, [esperado[x][2] for x in etiquetas])
        fijo = SM.horas_fin_utc(np.array([datetime(2019, 1, 1, 1)], dtype="datetime64[h]"), [False])
        self.assertEqual((int(fijo["h"][0]), fijo["tipo"][0]), (_h(datetime(2019, 1, 1, 5)), SM.TIPO_FIJO))
        self.assertEqual(str(fijo["h"].dtype), "int32")
        with self.assertRaises(SM.ErrorSinca):
            SM.horas_fin_utc(np.array([datetime(2019, 1, 1, 1)], dtype="datetime64[h]"), [True])

    def test_paridad_con_reloj_sinca_v2(self):
        """El paso a UTC civil es el de ``utc_civil`` de reloj_sinca_v2.py (R7; extraído por AST con su huella): su
        inicio + 1 h es nuestro fin; la alternativa y el tipo de hora coinciden."""
        from reloj_dmc import fijados as fijados_reloj
        _exigir_reloj_sinca(self)
        codigo = fijados_reloj.extraer_por_ast(_RELOJ_SINCA, _SHA_RELOJ_SINCA, ("CONVENCIONES", "utc_civil"),
                                               {"pd": pd, "ZoneInfo": ZoneInfo})
        self.assertEqual(tuple(codigo["CONVENCIONES"]), SM.CONVENCIONES)
        etiquetas = pd.date_range("2016-01-01 01:00", "2020-12-31 23:00", freq="h")
        for zona in ("America/Santiago", "America/Punta_Arenas"):
            for convencion in SM.CONVENCIONES:
                with self.subTest(zona=zona, convencion=convencion):
                    ref = codigo["utc_civil"](etiquetas, zona, convencion)
                    r = SM.horas_fin_utc(etiquetas.to_numpy().astype("datetime64[h]"), np.ones(len(etiquetas), bool),
                                         zona=zona, convencion=convencion)
                    inicio = ((ref["ts_utc"] - pd.Timestamp("2000-01-01")) // pd.Timedelta(hours=1)).to_numpy()
                    np.testing.assert_array_equal(r["h"].to_numpy(np.int64), inicio + 1)
                    alt = ref["ts_utc_alternativo"]
                    esperada = [None if pd.isna(a) else int((a - pd.Timestamp("2000-01-01")) // pd.Timedelta(hours=1)) + 1
                                for a in alt]
                    self.assertEqual([None if pd.isna(v) else int(v) for v in r["h_alternativa"]], esperada)
                    self.assertEqual(list(r["tipo"]), list(ref["qc_hora"]))

    def test_zona_de_y_politica_temporal(self):
        """SNC-12: zonas de la política; la copia de la prueba y POLITICA_SINCA son el bloque de la política anclada;
        un bloque que difiere en cualquier clave (también la zona por omisión o las zonas por región) o que trae una
        clave de más se rechaza en zona_de, leer_serie y series_horarias."""
        self.assertEqual(SM.zona_de("RXI", POLITICA_PRUEBA), "America/Coyhaique")
        self.assertEqual(SM.zona_de("RXII", POLITICA_PRUEBA["sinca"]), "America/Punta_Arenas")
        self.assertEqual(SM.zona_de("RM", POLITICA_PRUEBA), "America/Santiago")
        self.assertEqual(SM.POLITICA_SINCA, POLITICA_PRUEBA["sinca"])
        bloque = POLITICA_PRUEBA["sinca"]
        otras = {f"{clave}=otra_cosa": {**bloque, clave: "otra_cosa"} for clave in bloque}
        otras |= {"default_UTC": {**bloque, "zona_iana_default": "UTC"},
                  "sin_zonas": {k: v for k, v in bloque.items() if k != "zonas_iana_por_region"},
                  "sin_default": {k: v for k, v in bloque.items() if k != "zona_iana_default"},
                  "zonas_vacias": {**bloque, "zonas_iana_por_region": {}},
                  "RXII_santiago": {**bloque, "zonas_iana_por_region": {"RXI": "America/Coyhaique",
                                                                        "RXII": "America/Santiago"}},
                  "zona_de_mas": {**bloque, "zonas_iana_por_region": {**bloque["zonas_iana_por_region"],
                                                                      "RM": "UTC"}},
                  "clave_de_mas": {**bloque, "otra": "x"}}
        raiz, huellas = self.sintetica()
        e = SM.elegir_series(SM.leer_manifiestos(raiz, huellas), self.U)
        for nombre, otra in otras.items():
            with self.subTest(politica=nombre):
                with self.assertRaises(SM.ErrorSinca):
                    SM.zona_de("RM", {"sinca": otra})
                with self.assertRaises(SM.ErrorSinca):
                    SM.series_horarias(raiz, e, {"sinca": otra}, self.U, veredictos=_veredictos())
                with self.assertRaises(SM.ErrorSinca):
                    SM.leer_serie(raiz, e.iloc[0], otra, self.U, veredictos=_veredictos())
        t = SM.series_horarias(raiz, e, POLITICA_PRUEBA["sinca"], self.U, veredictos=_veredictos())
        self.assertEqual(t.attrs["registro_sinca"]["politica_temporal_sha256"], SM.SHA_POLITICA_TEMPORAL)
        if not _POLITICA.is_file():
            self.skipTest("falta config/sinca/politica_temporal.json; no se da por aprobada")
        real = SM.leer_politica_temporal(_POLITICA)
        self.assertEqual(real["sinca"], POLITICA_PRUEBA["sinca"])
        self.assertEqual(SM.POLITICA_SINCA, real["sinca"])
        self.assertEqual(SM.zona_de("RXII", real), "America/Punta_Arenas")
        with self.assertRaises(SM.ErrorSinca):
            SM.leer_politica_temporal(_POLITICA, sha256="0" * 64)

    def test_veredictos(self):
        """SNC-11: el argumento de los veredictos (A12) y su armado desde la tabla de reloj_sinca_v2 y su resumen:
        la huella del contenido, la del parquet, la política y la convención de T4 deben ser las del resumen."""
        tabla = pd.DataFrame({"estacion": ["D11", "D11", "D12", "D12"], "contaminante": ["pm25", "no2", "pm25", "o3"],
                              "anio": [2019, 2019, 2018, 2019],
                              "veredicto_fin": ["hora_civil", "reloj_fijo", "sin_evidencia", "hora_civil"],
                              "veredicto_inicio_mas_1h": ["reloj_fijo", "hora_civil", "hora_civil", "reloj_fijo"]})
        sha = _SHA_VEREDICTOS
        v = SM.veredictos_civiles(tabla, "fin", sha256=sha, resumen=_resumen(tabla, "fin", sha))
        self.assertEqual(v, {"sha256": sha, "huella_contenido": _huella_tabla(tabla), "convencion": "fin",
                             "hora_civil": (("D11", 2019), ("D12", 2019))})
        self.assertEqual(SM.huella_contenido(tabla), _huella_tabla(tabla))
        v = SM.veredictos_civiles(tabla, "inicio_mas_1h", sha256=sha, resumen=_resumen(tabla, "inicio_mas_1h", sha))
        self.assertEqual(v["hora_civil"], (("D11", 2019), ("D12", 2018)))
        sin_civil = tabla.assign(veredicto_fin="reloj_fijo", veredicto_inicio_mas_1h="sin_evidencia")
        self.assertEqual(SM.veredictos_civiles(sin_civil, "fin", sha256=sha,
                                               resumen=_resumen(sin_civil, "fin", sha))["hora_civil"], ())
        otra_celda = tabla.copy()
        otra_celda.loc[0, "veredicto_fin"] = "reloj_fijo"
        dup = pd.concat([tabla, tabla.iloc[:1]])
        malos = {
            "sin convención": (tabla, None, sha, _resumen(tabla, "fin", sha)),
            "convención desconocida": (tabla, "inicio", sha, _resumen(tabla, "inicio", sha)),
            "convención distinta de la de T4": (tabla, "fin", sha, _resumen(tabla, "inicio_mas_1h", sha)),
            "resumen sin elegida": (tabla, "fin", sha, {**_resumen(tabla, "fin", sha), "convencion_civil": {}}),
            "otro contenido": (otra_celda, "fin", sha, _resumen(tabla, "fin", sha)),
            "otro orden de columnas": (tabla[tabla.columns[::-1]], "fin", sha, _resumen(tabla, "fin", sha)),
            "otro sha256 del parquet": (tabla, "fin", "b" * 64, _resumen(tabla, "fin", sha)),
            "sha256 inválido": (tabla, "fin", "abc", _resumen(tabla, "fin", "abc")),
            "otro esquema": (tabla, "fin", sha, {**_resumen(tabla, "fin", sha), "schema": "otro"}),
            "otra política": (tabla, "fin", sha, {**_resumen(tabla, "fin", sha), "politica_temporal_sha256": "0" * 64}),
            "resumen incompleto": (tabla, "fin", sha, {k: v for k, v in _resumen(tabla, "fin", sha).items()
                                                       if k != "sha256_veredictos"}),
            "unidad repetida": (dup, "fin", sha, _resumen(dup, "fin", sha)),
        }
        for nombre, (t, conv, s, resumen) in malos.items():
            with self.subTest(caso=nombre):
                with self.assertRaises(SM.ErrorSinca):
                    SM.veredictos_civiles(t, conv, sha256=s, resumen=resumen)
        with self.assertRaises(TypeError):
            SM.veredictos_civiles(tabla, "fin", sha256=sha, resumen=None)
        raiz, huellas = self.sintetica()
        e = SM.elegir_series(SM.leer_manifiestos(raiz, huellas), self.U)
        t = SM.series_horarias(raiz, e, POLITICA_PRUEBA, self.U,
                               veredictos=SM.veredictos_civiles(tabla, "fin", sha256=sha,
                                                                resumen=_resumen(tabla, "fin", sha)))
        registro = t.attrs["registro_sinca"]
        self.assertEqual((registro["veredictos_sha256"], registro["veredictos_huella_contenido"],
                          registro["convencion"]), (sha, _huella_tabla(tabla), "fin"))
        malos = [{"sha256": _SHA_VEREDICTOS, "convencion": None}, {**_veredictos(), "otra": 1},
                 _veredictos(None, [("D11", 2019)]), _veredictos("fin", [("D11", "2019")]),
                 {**_veredictos(), "sha256": None}, {**_veredictos(), "huella_contenido": "abc"},
                 {k: v for k, v in _veredictos().items() if k != "huella_contenido"}, None]
        for malo in malos:
            with self.subTest(veredictos=malo):
                with self.assertRaises(SM.ErrorSinca):
                    SM.series_horarias(raiz, e, POLITICA_PRUEBA, self.U, veredictos=malo)
        with self.assertRaises(TypeError):
            SM.series_horarias(raiz, e, POLITICA_PRUEBA, self.U)      # sin veredictos no se supone UTC−4

    def test_veredictos_como_el_reloj(self):
        """SNC-11 contra reloj_sinca_v2.py (con su huella, por AST y como texto): su SCHEMA y su política; la huella
        del contenido es su fórmula; con la elección de su ``elegir_convencion`` (empate → inicio_mas_1h) se acepta
        esa convención y se rechaza la otra."""
        from reloj_dmc import fijados as fijados_reloj
        _exigir_reloj_sinca(self)
        nombres = ("SCHEMA", "SHA_POLITICA", "CONVENCIONES", "DESEMPATE", "DECISION_T4", "CIVIL", "elegir_convencion")
        codigo = fijados_reloj.extraer_por_ast(_RELOJ_SINCA, _SHA_RELOJ_SINCA, nombres, {"pd": pd})
        self.assertEqual(codigo["SCHEMA"], SM.SCHEMA_RELOJ_SINCA)
        self.assertEqual(codigo["SHA_POLITICA"], SM.SHA_POLITICA_TEMPORAL)
        self.assertEqual(codigo["CIVIL"], SM.VEREDICTO_CIVIL)
        fuente = _RELOJ_SINCA.read_text(encoding="utf-8")
        self.assertIn('"huella_veredictos_contenido": hashlib.sha256(tabla.to_csv(index=False).encode("utf-8"))'
                      '.hexdigest()', fuente)
        self.assertIn('resumen["sha256_veredictos"] = rv.publicar_parquet(tabla, destinos[0], r)', fuente)
        self.assertIn('"politica_temporal_sha256": sha_politica', fuente)
        self.assertEqual(set(SM.CLAVES_RESUMEN) - set(re.findall(r'"(\w+)":', fuente)) - {"sha256_veredictos"}, set())
        tabla = pd.DataFrame({"estacion": ["D11", "D12"], "contaminante": ["pm25", "o3"], "anio": [2019, 2019],
                              "veredicto_fin": ["hora_civil", "reloj_fijo"],
                              "veredicto_inicio_mas_1h": ["reloj_fijo", "hora_civil"]})
        eleccion = codigo["elegir_convencion"](tabla)
        self.assertEqual(eleccion["elegida"], codigo["DESEMPATE"])
        resumen = {**_resumen(tabla, None, _SHA_VEREDICTOS), "convencion_civil": eleccion}
        v = SM.veredictos_civiles(tabla, eleccion["elegida"], sha256=_SHA_VEREDICTOS, resumen=resumen)
        self.assertEqual(v["hora_civil"], (("D12", 2019),))
        otra = next(c for c in SM.CONVENCIONES if c != eleccion["elegida"])
        with self.assertRaises(SM.ErrorSinca):
            SM.veredictos_civiles(tabla, otra, sha256=_SHA_VEREDICTOS, resumen=resumen)


# ---------------------------------------------------------------------------------------------------------------
class PruebasControlMinimo(_ConSintetico):
    def test_control_minimo_por_rangos(self):
        """Rangos de §2.3 inclusivos (como cargar_dmc), el recorte de HR a 100 y los no numéricos (MC-10, punto 3)."""
        U = self.U
        bordes = {"TEMP": ("QTS_MIN", "QTS_MAX"), "RHUM": ("QHR_MIN", "QHR_MAX"), "WSPD": ("QFF_MIN", "QFF_MAX"),
                  "WDIR": ("QDD_MIN", "QDD_MAX")}
        self.assertEqual(SM.RANGO, bordes)
        self.assertEqual([U.a(i) for i in bordes["TEMP"]], [-39.0, 50.0])
        self.assertEqual([U.a(i) for i in bordes["RHUM"]], [1.0, 103.0])
        self.assertEqual([U.a(i) for i in bordes["WSPD"]], [0.0, 50.0])
        self.assertEqual([U.a(i) for i in bordes["WDIR"]], [0, 360])
        for variable, (bajo, alto) in bordes.items():
            with self.subTest(variable=variable):
                lo, hi = U.a(bajo), U.a(alto)
                v = np.array([lo, hi, lo - 0.1, hi + 0.1, np.nan, np.inf, -np.inf, (lo + hi) / 2])
                valor, valido, _ = SM.control_minimo(variable, v, U)
                self.assertEqual(list(valido), [True, True, False, False, False, False, False, True])
                self.assertEqual(valor[2], lo - 0.1)                 # la inválida conserva su número (SNC-10)
        self.assertFalse(SM.control_minimo("TEMP", [U.a("CENT_TS")], U)[1][0])     # el centinela de §2.4
        valor, valido, recortada = SM.control_minimo("RHUM", [99.9, 100.0, 100.5, 103.0, 103.1], U)
        self.assertEqual(list(valido), [True, True, True, True, False])
        self.assertEqual(list(recortada), [False, False, True, True, False])
        np.testing.assert_array_equal(valor, [99.9, 100.0, 100.0, 100.0, 103.1])
        with self.assertRaises(SM.ErrorSinca):
            SM.control_minimo("PRES", [950.0], U)

    def test_control_minimo_en_la_serie_sintetica(self):
        """D12: RHUM 105,0 y −1,0 fuera de rango y «s/d» no numérica; WDIR 400,0 fuera de rango. Todas en la tabla,
        inválidas, y contadas en el registro."""
        raiz, huellas = self.sintetica()
        e = SM.elegir_series(SM.leer_manifiestos(raiz, huellas), self.U)
        t = SM.series_horarias(raiz, e, POLITICA_PRUEBA, self.U, veredictos=_veredictos())
        inicio = datetime(2019, 1, 1, 1) + timedelta(hours=4)
        rhum = t[(t.estacion == "D12") & (t.variable == "RHUM")].set_index("h")
        for k, v in ((5, 105.0), (6, -1.0), (7, math.nan)):
            fila = rhum.loc[_h(inicio + timedelta(hours=k))]
            self.assertFalse(bool(fila["valido"]))
            self.assertTrue(math.isnan(fila["valor"]) if math.isnan(v) else fila["valor"] == v)
        self.assertEqual(int((~rhum["valido"]).sum()), 3)
        wdir = t[(t.estacion == "D12") & (t.variable == "WDIR")].set_index("h")
        self.assertFalse(bool(wdir.loc[_h(inicio + timedelta(hours=9)), "valido"]))
        self.assertEqual(int((~wdir["valido"]).sum()), 1)
        self.assertTrue(t[t.estacion != "D12"]["valido"].all())
        reg = {(r["estacion"], r["variable"]): r for r in t.attrs["registro_sinca"]["series"]}
        self.assertEqual((reg["D12", "RHUM"]["fuera_de_rango"], reg["D12", "RHUM"]["filas_no_numericas"]), (2, 1))
        self.assertEqual(reg["D12", "WDIR"]["fuera_de_rango"], 1)


# ---------------------------------------------------------------------------------------------------------------
class PruebasSeries(_ConSintetico):
    def test_esquema_orden_y_registro(self):
        """ESQUEMA_SINCA_HORA (A12), una fila por estación × variable × h, en orden; serie = ruta elegida."""
        raiz, huellas = self.sintetica()
        m = SM.leer_manifiestos(raiz, huellas)
        e = SM.elegir_series(m, self.U)
        antes = sorted((p.relative_to(raiz), p.stat().st_mtime_ns) for p in raiz.rglob("*"))
        t = SM.series_horarias(raiz, e.iloc[::-1], POLITICA_PRUEBA, self.U, veredictos=_veredictos())
        self.assertEqual(antes, sorted((p.relative_to(raiz), p.stat().st_mtime_ns) for p in raiz.rglob("*")))
        tipos.validar_esquema(t, tipos.ESQUEMA_SINCA_HORA, nombre="sinca")
        self.assertEqual(t.attrs["esquema"], tipos.ESQUEMA_SINCA_HORA.version)
        clave = list(zip(t["estacion"], [tipos.VARIABLES_SINCA.index(v) for v in t["variable"]], t["h"]))
        self.assertEqual(clave, sorted(clave))
        self.assertEqual(len(set(clave)), len(clave))
        elegida = dict(zip(zip(e["estacion"], e["parametro"]), e["ruta_relativa"]))
        for (est, var), sub in t.groupby(["estacion", "variable"]):
            self.assertEqual(set(sub["serie"]), {elegida[est, var]})
        registro = t.attrs["registro_sinca"]
        self.assertEqual((registro["politica_temporal_sha256"], registro["veredictos_sha256"],
                          registro["veredictos_huella_contenido"], registro["convencion"]),
                         (SM.SHA_POLITICA_TEMPORAL, _SHA_VEREDICTOS, _SHA_CONTENIDO, None))
        self.assertEqual(len(registro["series"]), len(e))
        for r in registro["series"]:
            fila = e[e.ruta_relativa == r["serie"]].iloc[0]
            self.assertEqual(r["filas"], int(fila.filas))
            self.assertEqual(r["horas"], int(fila.filas_con_observacion) + int(fila.filas_no_numericas))
        # Una fila de elegir_series sirve también suelta.
        tabla, reg = SM.leer_serie(raiz, e.iloc[0], POLITICA_PRUEBA, self.U, veredictos=_veredictos())
        pd.testing.assert_frame_equal(tabla.reset_index(drop=True),
                                      t[t.serie == e.iloc[0].ruta_relativa].reset_index(drop=True))
        vacia = SM.series_horarias(raiz, e.iloc[:0], POLITICA_PRUEBA, self.U, veredictos=_veredictos())
        tipos.validar_esquema(vacia, tipos.ESQUEMA_SINCA_HORA, nombre="vacía")
        self.assertEqual(len(vacia), 0)

    def test_una_serie_por_estacion_y_variable(self):
        raiz, huellas = self.sintetica()
        m = SM.leer_manifiestos(raiz, huellas)
        e = SM.elegir_series(m, self.U)
        with self.assertRaisesRegex(SM.ErrorSinca, "una sola serie"):
            SM.series_horarias(raiz, pd.concat([e, e.iloc[:1]]), POLITICA_PRUEBA, self.U, veredictos=_veredictos())
        pres = m[m.parametro == "PRES"].iloc[:1]
        with self.assertRaises(SM.ErrorSinca):
            SM.series_horarias(raiz, pres, POLITICA_PRUEBA, self.U, veredictos=_veredictos())

    def test_integridad_de_la_serie(self):
        """SNC-5: tamaño en disco y sha256 del manifiesto, cada uno con su guarda; los tres conteos de la serie, los
        del manifiesto, también cada uno con la suya."""
        raiz, huellas = self.sintetica()
        e = SM.elegir_series(SM.leer_manifiestos(raiz, huellas), self.U)
        fila = e[(e.estacion == "D12") & (e.parametro == "RHUM")].iloc[0]       # trae una fila no numérica
        self.assertEqual(int(fila.filas_no_numericas), 1)
        ruta = raiz / fila.ruta_relativa
        original = ruta.read_bytes()
        self.assertEqual(original[-2:], b";\n")
        otro_digito = b"1" if original[-3:-2] == b"0" else b"0"
        ruta.write_bytes(original[:-3] + otro_digito + b";\n")                  # mismo tamaño, otro sha256
        self.assertEqual(len(ruta.read_bytes()), len(original))
        with self.assertRaisesRegex(SM.ErrorSinca, "sha256 distinto"):
            SM.leer_serie(raiz, fila, POLITICA_PRUEBA, self.U, veredictos=_veredictos())
        ruta.write_bytes(original)
        SM.leer_serie(raiz, fila, POLITICA_PRUEBA, self.U, veredictos=_veredictos())
        otra = fila.copy()
        otra["bytes"] = str(int(fila.bytes) + 1)                                # sin tocar el archivo
        with self.assertRaisesRegex(SM.ErrorSinca, "tamaño"):
            SM.leer_serie(raiz, otra, POLITICA_PRUEBA, self.U, veredictos=_veredictos())
        for campo, cambio in (("filas", 1), ("filas_con_observacion", -1), ("filas_no_numericas", -1),
                              ("filas_no_numericas", 1)):
            with self.subTest(campo=campo, cambio=cambio):
                otra = fila.copy()
                otra[campo] = str(int(fila[campo]) + cambio)
                with self.assertRaisesRegex(SM.ErrorSinca, campo):
                    SM.leer_serie(raiz, otra, POLITICA_PRUEBA, self.U, veredictos=_veredictos())
        otra = fila.copy()
        otra["ruta_relativa"] = "../" + fila.ruta_relativa
        with self.assertRaises(SM.ErrorSinca):
            SM.leer_serie(raiz, otra, POLITICA_PRUEBA, self.U, veredictos=_veredictos())

    def test_guarda_de_rutas_de_las_series(self):
        """SNC-15 (regla 10 del diseño): una serie que es un enlace simbólico (a una copia idéntica fuera de la raíz,
        sin permiso de lectura, o a otra dentro), o bajo una carpeta que es un enlace, se rechaza antes de leer un
        byte; la raíz enlazada sí se lee."""
        raiz, huellas = self.sintetica()
        e = SM.elegir_series(SM.leer_manifiestos(raiz, huellas), self.U)
        fila = e.iloc[0]
        ruta = raiz / fila.ruta_relativa
        original = ruta.read_bytes()
        copia = self.fuera("serie") / ruta.name
        copia.write_bytes(original)
        copia.chmod(0o000)
        self.addCleanup(copia.chmod, 0o600)
        dentro = raiz / "copias" / ruta.name
        dentro.parent.mkdir()
        dentro.write_bytes(original)
        for nombre, destino in (("fuera de la raíz", copia), ("dentro de la raíz", dentro)):
            with self.subTest(enlace=nombre):
                ruta.unlink()
                ruta.symlink_to(destino)
                with self.assertRaisesRegex(SM.ErrorSinca, "enlace simbólico"):
                    SM.leer_serie(raiz, fila, POLITICA_PRUEBA, self.U, veredictos=_veredictos())
                ruta.unlink()
                ruta.write_bytes(original)
        carpeta = ruta.parent
        movida = self.fuera("carpeta") / carpeta.name
        carpeta.rename(movida)
        carpeta.symlink_to(movida, target_is_directory=True)
        with self.assertRaisesRegex(SM.ErrorSinca, "enlace simbólico"):
            SM.series_horarias(raiz, e, POLITICA_PRUEBA, self.U, veredictos=_veredictos())
        carpeta.unlink()
        movida.rename(carpeta)
        enlace = Path(self._tmp.name) / "raiz_enlazada"
        enlace.symlink_to(raiz, target_is_directory=True)
        pd.testing.assert_frame_equal(
            SM.series_horarias(enlace, e, POLITICA_PRUEBA, self.U, veredictos=_veredictos()),
            SM.series_horarias(raiz, e, POLITICA_PRUEBA, self.U, veredictos=_veredictos()))

    def test_formato_como_el_descargador(self):
        """SNC-5: los conteos de parsear_serie son los de analizar_respuesta del descargador (AST, con su huella),
        en las series sintéticas y en filas hechas a mano (vacías, «s/d», «nan», «inf», espacios y coma)."""
        from reloj_dmc import fijados as fijados_reloj
        if not _DESCARGADOR.is_file() or _sha(_DESCARGADOR.read_bytes()) != _SHA_DESCARGADOR:
            self.skipTest("descargar_sinca_meteorologia.py falta o no tiene la huella de M0; no se da por aprobada")
        codigo = fijados_reloj.extraer_por_ast(_DESCARGADOR, _SHA_DESCARGADOR,
                                               ("_RE_DATO", "_yymmdd", "analizar_respuesta"),
                                               {"re": re, "math": math, "date": date})
        raiz, huellas = self.sintetica(desde="2019-01-01", hasta="2019-01-02")
        m = SM.leer_manifiestos(raiz, huellas)
        a_mano = ("FECHA (YYMMDD);HORA (HHMM);REGISTRO;\n190101;0100;;\n190101;0200;s/d;\n190101;0300;nan;\n"
                  "190101;0400;inf;\n190101;0500; 2,5 ;\n190101;0600;-1,0;x;\n\n190101;0700;12;\n")
        textos = [(raiz / r).read_text(encoding="utf-8") for r in m["ruta_relativa"]] + [a_mano]
        for texto in textos:
            etiquetas, valores, conteos = SM.parsear_serie(texto)
            ref = codigo["analizar_respuesta"](texto, "2019-01-01", "2019-01-02")
            self.assertEqual(conteos, {k: ref[k] for k in conteos})
            self.assertEqual(len(etiquetas), conteos["filas_con_observacion"] + conteos["filas_no_numericas"])
        etiquetas, valores, _ = SM.parsear_serie(a_mano)
        self.assertEqual([str(x) for x in etiquetas], [f"2019-01-01T0{k}" for k in range(2, 8)])
        np.testing.assert_array_equal(valores, [np.nan, np.nan, np.nan, 2.5, -1.0, 12.0])

    def test_etiquetas_invalidas(self):
        """SNC-6: minutos distintos de 00, la hora 24, una fecha que no existe, sin encabezado o una fila con otro
        formato son ErrorSinca. El mensaje da el número de línea, no su contenido (SNC-5)."""
        encabezado = "FECHA (YYMMDD);HORA (HHMM);REGISTRO;\n"
        for fila in ("190101;0130;12,375;", "190101;2400;12,375;", "190231;0100;12,375;", "19010;0100;12,375;",
                     "x12,375", "190101;2400;;", "190231;0100;;"):
            with self.subTest(fila=fila):
                with self.assertRaisesRegex(SM.ErrorSinca, "línea 3") as error:
                    SM.parsear_serie(encabezado + "\n" + fila + "\n")
                self.assertNotIn("12,375", str(error.exception))
                self.assertNotIn(fila.split(";")[0], str(error.exception))
        with self.assertRaises(SM.ErrorSinca):
            SM.parsear_serie("190101;0100;1,0;\n")
        etiquetas, _, _ = SM.parsear_serie(encabezado + "000101;0000;1,0;\n681231;2300;2,0;\n")
        self.assertEqual([str(x) for x in etiquetas], ["2000-01-01T00", "2068-12-31T23"])

    def test_errores_sin_valores_de_la_serie(self):
        """SNC-5: un conteo del manifiesto que no calza o que no es entero se informa sin su valor."""
        raiz, huellas = self.sintetica()
        e = SM.elegir_series(SM.leer_manifiestos(raiz, huellas), self.U)
        fila = e.iloc[0].copy()
        fila["filas_con_observacion"] = "987654"
        with self.assertRaises(SM.ErrorSinca) as error:
            SM.leer_serie(raiz, fila, POLITICA_PRUEBA, self.U, veredictos=_veredictos())
        self.assertNotIn("987654", str(error.exception))
        self.assertNotIn(str(int(e.iloc[0].filas_con_observacion)), str(error.exception))
        fila["filas_con_observacion"] = "98,7654"
        with self.assertRaises(SM.ErrorSinca) as error:
            SM.leer_serie(raiz, fila, POLITICA_PRUEBA, self.U, veredictos=_veredictos())
        self.assertNotIn("98,7654", str(error.exception))


if __name__ == "__main__":
    unittest.main()
