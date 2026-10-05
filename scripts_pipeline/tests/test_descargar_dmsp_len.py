from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import descargar_dmsp_len as dmsp  # noqa: E402


class _Body(io.BytesIO):
    pass


class _NoExiste(Exception):
    def __init__(self):
        self.response = {"Error": {"Code": "NoSuchKey"}}


class _S3Falso:
    def __init__(self, objetos, heads):
        self.objetos = objetos
        self.heads = heads
        self.gets = []
        self.head_calls = []

    def get_object(self, *, Bucket, Key):
        if Bucket != dmsp.BUCKET or Key not in self.objetos:
            raise _NoExiste()
        self.gets.append(Key)
        datos = json.dumps(self.objetos[Key]).encode()
        return {"Body": _Body(datos), "ContentLength": len(datos)}

    def head_object(self, *, Bucket, Key):
        if Bucket != dmsp.BUCKET or Key not in self.heads:
            raise _NoExiste()
        self.head_calls.append(Key)
        return self.heads[Key]


def _head(size=1234, etag="abc"):
    return {
        "ContentLength": size,
        "ETag": f'"{etag}"',
        "LastModified": datetime(2020, 12, 3, tzinfo=timezone.utc),
    }


def _asset(banda: str, path: Path) -> dmsp.AssetFuente:
    return dmsp.AssetFuente(
        banda=banda, key=f"prueba/{path.name}", href=str(path),
        size=path.stat().st_size, etag=f"etag-{banda}",
        last_modified="2020-12-03T00:00:00Z",
    )


class RangoYStacTests(unittest.TestCase):
    def test_rango_se_recorta_a_brecha_pre_viirs(self):
        self.assertEqual(
            dmsp._rango("1999-01-01", "2026-12-31"),
            (dmsp.FECHA_INICIO, dmsp.FECHA_FIN),
        )
        self.assertEqual(
            dmsp._rango("2012-01-01", "2013-01-01"),
            (dmsp.date(2012, 1, 1), dmsp.FECHA_FIN),
        )
        self.assertIsNone(dmsp._rango("2012-01-19", "2013-01-01"))
        with self.assertRaisesRegex(ValueError, "posterior"):
            dmsp._rango("2001-01-02", "2001-01-01")

    def test_antimeridiano_alinea_ambas_convenciones(self):
        chile = (-109.5, -27.3, -66.3, -17.4)
        self.assertEqual(
            dmsp._desplazamiento_longitud((166.9, -61, 305.1, 75), chile),
            360.0,
        )
        self.assertEqual(
            dmsp._desplazamiento_longitud((-168.1, -61, -28.9, 75), chile),
            0.0,
        )
        self.assertIsNone(
            dmsp._desplazamiento_longitud((10, -10, 20, 10), chile))

    def test_keys_no_permiten_salir_del_bucket(self):
        self.assertEqual(
            dmsp._key_href(dmsp.HTTPS_ROOT + "F142000/item.json"),
            "F142000/item.json",
        )
        with self.assertRaises(ValueError):
            dmsp._key_href("https://example.org/robo.tif")
        with self.assertRaises(ValueError):
            dmsp._key_segura("../robo.tif")

    def test_cliente_es_s3_anonimo(self):
        from botocore import UNSIGNED
        cliente = dmsp.cliente_s3()
        try:
            self.assertEqual(cliente.meta.config.signature_version, UNSIGNED)
        finally:
            cliente.close()

    def test_dry_run_no_abre_red_ni_escribe(self):
        aois = tuple(dmsp.AOI(f"a{i}", f"t{i}", (-80, -40, -60, -20))
                     for i in range(5))
        salida = io.StringIO()
        with patch.object(dmsp, "seleccionar", return_value=aois), \
                patch.object(dmsp, "cliente_s3") as red, \
                patch.object(dmsp, "ensure_dir") as escritura, \
                patch.object(dmsp, "Manifiesto") as manifiesto, \
                redirect_stdout(salida):
            self.assertEqual(dmsp.main(["--dry-run"]), 0)
        red.assert_not_called()
        escritura.assert_not_called()
        manifiesto.assert_not_called()
        plan = json.loads(salida.getvalue())
        self.assertEqual(plan["estimacion_salida_final_gib"], "65-85")

    def test_inventario_stac_incluye_vis_flag_samples_y_luna(self):
        annual = "F142000/F142000_catalog.json"
        annual_f15 = "F152000/F152000_catalog.json"
        item_ok = "F142000/F14200001010256.night.OIS.vis.co.json"
        item_fuera = "F142000/F14200001010438.night.OIS.vis.co.json"
        vis = item_ok[:-5] + ".tif"
        raiz = {
            "links": [
                {"rel": "child", "href": dmsp._href(annual)},
                {"rel": "child", "href": dmsp._href(annual_f15)},
            ],
        }
        catalogo = {
            "links": [
                {"rel": "item", "href": "./" + Path(item_ok).name},
                {"rel": "item", "href": "./" + Path(item_fuera).name},
            ],
        }
        objetos = {
            dmsp.STAC_KEY: raiz,
            annual: catalogo,
            annual_f15: {"links": [{
                "rel": "item",
                "href": "./F15200001020000.night.OIS.vis.co.json",
            }]},
            item_ok: {
                "type": "Feature",
                "id": Path(item_ok).stem,
                "properties": {"datetime": "2000-01-01T02:56:00Z"},
                "bbox": [166.995, -61.004, 305.004, 75.004],
                "assets": {"image": {"href": dmsp._href(vis)}},
            },
            item_fuera: {
                "type": "Feature",
                "id": Path(item_fuera).stem,
                "properties": {"datetime": "2000-01-01T04:38:00Z"},
                "bbox": [10.0, -10.0, 20.0, 10.0],
                "assets": {"image": {"href": dmsp._href(item_fuera[:-5] + ".tif")}},
            },
        }
        base = vis[:-len(".vis.co.tif")]
        heads = {
            vis: _head(etag="vis"),
            base + ".flag.co.tif": _head(etag="flag"),
            base + ".samples.co.tif": _head(etag="samples"),
            base + ".li.co.tif": _head(etag="li"),
        }
        s3 = _S3Falso(objetos, heads)
        aois = (dmsp.AOI("chile", "chile", (-110, -56, -66, -17)),)
        items, auditoria = dmsp.inventariar(
            s3, inicio=dmsp.FECHA_INICIO, fin=dmsp.FECHA_INICIO,
            aois=aois, workers=1,
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].segment_start_utc, "2000-01-01T02:56:00Z")
        self.assertEqual(set(items[0].assets), {"vis", "flag", "samples", "li"})
        self.assertEqual(len(s3.head_calls), 4)
        self.assertEqual(len(auditoria), 2)
        self.assertTrue(all(x["recorrido_completo"] for x in auditoria))

    def test_inventario_completo_rechaza_catalogo_satelite_anio_faltante(self):
        s3 = _S3Falso({
            dmsp.STAC_KEY: {"links": [{
                "rel": "child",
                "href": dmsp._href("F142000/F142000_catalog.json"),
            }]},
        }, {})
        with self.assertRaisesRegex(ValueError, "faltan"):
            dmsp._catalogos_anuales(s3, dmsp.FECHA_INICIO, dmsp.FECHA_INICIO)

    def test_catalogos_esperados_son_21_mas_f15_f18_2012(self):
        hasta_2011 = dmsp._catalogos_esperados(
            dmsp.FECHA_INICIO, dmsp.date(2011, 12, 31))
        completos = dmsp._catalogos_esperados(dmsp.FECHA_INICIO, dmsp.FECHA_FIN)
        self.assertEqual(len(hasta_2011), 21)
        self.assertEqual(len(completos), 23)
        self.assertEqual(
            {(sat, year) for year, sat, _ in completos if year == 2012},
            {("F15", 2012), ("F18", 2012)},
        )

    def test_li_ausente_es_fallo_y_no_asset_opcional(self):
        with self.assertRaises(_NoExiste):
            dmsp._metadata_asset(
                _S3Falso({}, {}), "li", "F142000/falta.li.co.tif")

    def test_head_posterior_detecta_fuente_cambiada(self):
        key = "F142000/cambio.vis.co.tif"
        esperado = dmsp.AssetFuente(
            banda="vis", key=key, href=dmsp._href(key), size=1234,
            etag="anterior", last_modified="2020-12-03T00:00:00Z",
        )
        granulo = dmsp.Granulo(
            granule_id="F14200001010114.night.OIS.vis.co", satelite="F14",
            segment_start_utc="2000-01-01T01:14:00Z", item_key="item.json",
            bbox=(-80, -40, -60, -20), assets={"vis": esperado},
        )
        s3 = _S3Falso({}, {key: _head(etag="nuevo")})
        with self.assertRaisesRegex(RuntimeError, "fuente cambio"):
            dmsp._verificar_fuentes_sin_cambio(
                s3, dmsp.GrupoDia("F14", "2000-01-01", (granulo,)))

    def test_agrupar_conserva_todas_las_orbitas_del_dia(self):
        g1 = _granulo_vacio("F14200001010114", "2000-01-01T01:14:00Z")
        g2 = _granulo_vacio("F14200001010256", "2000-01-01T02:56:00Z")
        grupos = dmsp._agrupar_dias([g2, g1])
        self.assertEqual(len(grupos), 1)
        self.assertEqual([x.granule_id for x in grupos[0].granulos],
                         [g1.granule_id, g2.granule_id])


def _granulo_vacio(prefijo: str, tiempo: str) -> dmsp.Granulo:
    return dmsp.Granulo(
        granule_id=prefijo + ".night.OIS.vis.co",
        satelite=prefijo[:3], segment_start_utc=tiempo,
        item_key=prefijo[:7] + "/" + prefijo + ".night.OIS.vis.co.json",
        bbox=(-80, -40, -60, -20), assets={},
    )


@unittest.skipUnless(
    all(__import__(modulo) for modulo in ("rasterio", "geopandas", "pyarrow")),
    "requiere stack geoespacial",
)
class RecorteLocalTests(unittest.TestCase):
    def setUp(self):
        import geopandas as gpd
        from shapely.geometry import box

        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.aoi = dmsp.AOI(
            "prueba", "prueba", (-70.01, -30.07, -69.91, -29.99))
        # Dos comunas adyacentes: las celdas que cruzan la frontera deben
        # permanecer en el enlace muchos-a-muchos.
        self.comunas = gpd.GeoDataFrame(
            {"cod_comuna": [1, 2], "Comuna": ["A", "B"]},
            geometry=[
                box(-70.005, -30.065, -69.96, -29.995),
                box(-69.96, -30.065, -69.915, -29.995),
            ],
            crs="EPSG:4326",
        )
        self.catalogo = dmsp._construir_catalogo_aoi(self.aoi, self.comunas)

    def tearDown(self):
        self.tmp.cleanup()

    def _fuentes(self, *, dominio_360=False, lunar_fill=True,
                 sample_fuera=False):
        import rasterio
        from rasterio.transform import from_origin

        res = 0.00833333  # paso truncado como en los COG reales
        oeste = (289.995833335 if dominio_360 else -70.004166665)
        norte = -29.995833335
        transform = from_origin(oeste, norte, res, res)
        shape = (12, 12)
        vis = np.full(shape, 255, dtype="uint8")
        flag = np.full(shape, dmsp.FLAG_NO_DATA, dtype="uint16")
        samples = np.zeros(shape, dtype="uint16")
        lunar = np.full(shape, -999.3, dtype="float32")

        xs = self.catalogo.lon.to_numpy() + (360 if dominio_360 else 0)
        ys = self.catalogo.lat.to_numpy()
        rr, cc = rasterio.transform.rowcol(transform, xs, ys)
        usados = []
        for indice, (r, c) in enumerate(zip(rr, cc, strict=False)):
            if 0 <= r < shape[0] and 0 <= c < shape[1]:
                usados.append((r, c))
                vis[r, c] = np.uint8(10 + indice % 40)
                flag[r, c] = np.uint16(indice % 8)  # QA crudo no se filtra
                samples[r, c] = np.uint16(1 + indice)
                lunar[r, c] = np.float32(0.25 + indice / 100)
        self.assertGreaterEqual(len(usados), 4)
        # Fill visible y no-data se excluyen; fill lunar queda como nulo.
        vis[usados[0]] = 64
        flag[usados[1]] = dmsp.FLAG_NO_DATA
        samples[usados[2]] = 1466 if sample_fuera else 0
        if lunar_fill:
            lunar[usados[2]] = -999.3

        arrays = {"vis": vis, "flag": flag, "samples": samples, "li": lunar}
        dtypes = {"vis": "uint8", "flag": "uint16", "samples": "uint16",
                  "li": "float32"}
        assets = {}
        for banda, datos in arrays.items():
            path = self.root / f"{banda}_{'360' if dominio_360 else '180'}.tif"
            with rasterio.open(
                path, "w", driver="GTiff", width=shape[1], height=shape[0],
                count=1, dtype=dtypes[banda], crs="EPSG:4326",
                transform=transform,
            ) as dst:
                dst.write(datos, 1)
            assets[banda] = _asset(banda, path)
        return assets

    def _granulo(self, prefijo, tiempo, *, dominio_360=False,
                 sample_fuera=False):
        assets = self._fuentes(
            dominio_360=dominio_360, sample_fuera=sample_fuera)
        import rasterio
        with rasterio.open(assets["vis"].href) as src:
            bbox = tuple(src.bounds)
        return dmsp.Granulo(
            granule_id=prefijo + ".night.OIS.vis.co",
            satelite="F14", segment_start_utc=tiempo,
            item_key="F142000/" + prefijo + ".night.OIS.vis.co.json",
            bbox=bbox, assets=assets,
        )

    def test_recorte_preserva_qa_samples_luna_y_no_inventa_hora(self):
        granulo = self._granulo("F14200001010114", "2000-01-01T01:14:00Z")
        resultado = dmsp._extraer_granulo(
            granulo, (self.aoi,), {self.aoi.id: self.catalogo}, self.root)
        obs, stats = resultado[self.aoi.id]
        self.assertIsNotNone(obs)
        self.assertGreater(len(obs), 0)
        self.assertTrue(obs.vis_dn.between(0, 63).all())
        self.assertTrue(((obs.qa_flag.astype("uint16") & dmsp.FLAG_NO_DATA) == 0).all())
        self.assertEqual(str(obs.sample_position.dtype), "UInt16")
        self.assertGreaterEqual(obs.sample_position.isna().sum(), 1)
        self.assertTrue(obs.sample_position.dropna().between(1, 1465).all())
        self.assertEqual(len(obs), stats["pixeles_source_nonfill"])
        self.assertEqual(stats["samples_fill"], 1)
        self.assertGreaterEqual(obs.lunar_illuminance_lux.isna().sum(), 1)
        self.assertTrue(obs.orbit_id.eq(granulo.granule_id).all())
        self.assertTrue(obs.time_is_pixel_specific.eq(False).all())
        self.assertEqual(stats["vis_fill_o_fuera_rango"], 1)
        self.assertEqual(stats["flag_no_data"], 1)

    def test_longitudes_0_360_producen_los_mismos_pixel_id(self):
        g180 = self._granulo("F14200001010114", "2000-01-01T01:14:00Z")
        g360 = self._granulo(
            "F14200001010256", "2000-01-01T02:56:00Z", dominio_360=True)
        o180, _ = dmsp._extraer_granulo(
            g180, (self.aoi,), {self.aoi.id: self.catalogo}, self.root)[self.aoi.id]
        o360, _ = dmsp._extraer_granulo(
            g360, (self.aoi,), {self.aoi.id: self.catalogo}, self.root)[self.aoi.id]
        self.assertEqual(set(o180.pixel_id), set(o360.pixel_id))

    def test_sample_position_1466_se_rechaza(self):
        granulo = self._granulo(
            "F14200001010114", "2000-01-01T01:14:00Z", sample_fuera=True)
        with self.assertRaisesRegex(ValueError, "fuera de 0..1465"):
            dmsp._extraer_granulo(
                granulo, (self.aoi,), {self.aoi.id: self.catalogo}, self.root)

    def test_grilla_rechaza_desalineacion_mayor_a_un_decimo_de_pixel(self):
        import rasterio
        from rasterio.transform import from_origin

        path = self.root / "vis_desalineado.tif"
        paso = 0.00833333
        # 0,001 grados = 0,12 pixeles: el rtol predeterminado de NumPy lo
        # aceptaria por error al comparar una columna global de cinco cifras.
        transform = from_origin(-70.003166665, -29.995833335, paso, paso)
        with rasterio.open(
            path, "w", driver="GTiff", width=2, height=2, count=1,
            dtype="uint8", crs="EPSG:4326", transform=transform,
        ) as dst:
            dst.write(np.zeros((2, 2), dtype="uint8"), 1)
        with rasterio.open(path) as src:
            with self.assertRaisesRegex(ValueError, "no esta alineada"):
                dmsp._validar_grilla_fuente(src, "vis")

    def test_parquet_diario_conserva_solapes_de_orbitas_y_estado_idempotente(self):
        g1 = self._granulo("F14200001010114", "2000-01-01T01:14:00Z")
        g2 = self._granulo("F14200001010256", "2000-01-01T02:56:00Z")
        grupo = dmsp._agrupar_dias([g1, g2])[0]

        class Mani:
            def __init__(self):
                self.eventos = []

            def registrar(self, valor):
                self.eventos.append(valor)

        mani = Mani()
        base = self.root / "producto"
        trabajo = self.root / "trabajo"
        trabajo.mkdir()
        dmsp._procesar_grupo_dia(
            base, grupo, (self.aoi,), {self.aoi.id: self.catalogo},
            "mascara-prueba", mani, trabajo,
        )
        salida = dmsp._ruta_observacion(base, grupo, self.aoi)
        df = dmsp._validar_observaciones(
            salida, self.catalogo, grupo, self.aoi, con_lunar=True)
        self.assertEqual(df.orbit_id.nunique(), 2)
        self.assertTrue(df.duplicated("pixel_id").any())
        estado = dmsp._ruta_estado(base, grupo)
        self.assertTrue(dmsp._estado_valido(
            estado, base, grupo, (self.aoi,), {self.aoi.id: self.catalogo},
            "mascara-prueba"))
        datos_estado = json.loads(estado.read_text())
        datos_estado["processor_sha256"] = "codigo-anterior"
        dmsp._guardar_json_atomico(estado, datos_estado)
        self.assertFalse(dmsp._estado_valido(
            estado, base, grupo, (self.aoi,), {self.aoi.id: self.catalogo},
            "mascara-prueba"))

        # Una nueva transacción sin datos debe retirar el Parquet anterior.
        with patch.object(dmsp, "_extraer_granulo", return_value={
                self.aoi.id: (None, {
                    "estado": "sin_datos", "pixeles_catalogo": len(self.catalogo),
                })}):
            dmsp._procesar_grupo_dia(
                base, grupo, (self.aoi,), {self.aoi.id: self.catalogo},
                "mascara-prueba", mani, trabajo,
            )
        self.assertFalse(salida.exists())
        self.assertTrue(dmsp._estado_valido(
            estado, base, grupo, (self.aoi,), {self.aoi.id: self.catalogo},
            "mascara-prueba"))

    def test_commit_cinco_aoi_hace_rollback_sin_parquet_huerfano(self):
        granulo = self._granulo("F14200001010114", "2000-01-01T01:14:00Z")
        grupo = dmsp._agrupar_dias([granulo])[0]
        original, stats = dmsp._extraer_granulo(
            granulo, (self.aoi,), {self.aoi.id: self.catalogo}, self.root
        )[self.aoi.id]
        aois = tuple(dmsp.AOI(
            f"a{i}", f"territorio{i}", self.aoi.bbox) for i in range(5))
        catalogos = {a.id: self.catalogo.copy() for a in aois}
        resultados = {}
        for aoi in aois:
            obs = original.copy()
            obs["aoi_id"] = aoi.id
            resultados[aoi.id] = (obs, dict(stats))
        base = self.root / "producto_rollback"
        trabajo = self.root / "trabajo_rollback"
        final_fallido = dmsp._ruta_observacion(base, grupo, aois[1])
        for aoi in aois[2:]:
            anterior = dmsp._ruta_observacion(base, grupo, aoi)
            anterior.parent.mkdir(parents=True, exist_ok=True)
            anterior.write_bytes(b"version-anterior")
        estado_anterior = dmsp._ruta_estado(base, grupo)
        estado_anterior.parent.mkdir(parents=True, exist_ok=True)
        estado_anterior.write_text('{"estado":"anterior"}\n')
        mover_real = dmsp._mover_commit
        fallo = {"hecho": False}

        def mover_con_fallo(origen, destino):
            if Path(destino) == final_fallido and not fallo["hecho"]:
                fallo["hecho"] = True
                raise OSError("fallo commit simulado")
            mover_real(origen, destino)

        with patch.object(dmsp, "_extraer_granulo", return_value=resultados), \
                patch.object(dmsp, "_mover_commit", side_effect=mover_con_fallo):
            with self.assertRaisesRegex(OSError, "simulado"):
                dmsp._procesar_grupo_dia(
                    base, grupo, aois, catalogos, "mask", unittest.mock.Mock(),
                    trabajo,
                )
        self.assertTrue(fallo["hecho"])
        self.assertEqual(estado_anterior.read_text(), '{"estado":"anterior"}\n')
        self.assertFalse(dmsp._ruta_observacion(base, grupo, aois[0]).exists())
        self.assertFalse(dmsp._ruta_observacion(base, grupo, aois[1]).exists())
        for aoi in aois[2:]:
            self.assertEqual(
                dmsp._ruta_observacion(base, grupo, aoi).read_bytes(),
                b"version-anterior",
            )

    def test_catalogo_cacheado_truncado_no_se_reutiliza(self):
        base = self.root / "producto_catalogo"
        comunas_path = self.root / "solo_metadata.shp"
        catalogos = dmsp._cargar_o_publicar_catalogos(
            base, (self.aoi,), self.comunas, comunas_path, "mask")
        self.assertIn(self.aoi.id, catalogos)
        path = base / "catalogo_pixeles" / f"{self.aoi.id}.parquet"
        path.write_bytes(b"truncado")
        with self.assertRaises(Exception):
            dmsp._cargar_o_publicar_catalogos(
                base, (self.aoi,), self.comunas, comunas_path, "mask")

    def test_reserva_insuficiente_aborta_con_error_especifico(self):
        with patch.object(dmsp.shutil, "disk_usage", return_value=SimpleNamespace(
                free=99 * 2**30)):
            with self.assertRaises(dmsp.ReservaEspacioError):
                dmsp._exigir_reserva(self.root, 100, granule_id="F14_dia")

    def test_fallo_en_una_orbita_no_publica_dia_parcial(self):
        g1 = _granulo_vacio("F14200001010114", "2000-01-01T01:14:00Z")
        g2 = _granulo_vacio("F14200001010256", "2000-01-01T02:56:00Z")
        grupo = dmsp._agrupar_dias([g1, g2])[0]
        obs = np.array([1])  # marcador; el primer resultado no se publicara
        primero = {self.aoi.id: (obs, {"estado": "archivo"})}
        with patch.object(dmsp, "_extraer_granulo",
                          side_effect=[primero, RuntimeError("fuente incompleta")]):
            with self.assertRaisesRegex(RuntimeError, "incompleta"):
                dmsp._procesar_grupo_dia(
                    self.root / "producto_fallo", grupo, (self.aoi,),
                    {self.aoi.id: self.catalogo}, "mask", unittest.mock.Mock(),
                    self.root,
                )
        self.assertFalse(dmsp._ruta_estado(
            self.root / "producto_fallo", grupo).exists())

    def test_enlace_es_muchos_a_muchos_y_temporales_se_limpian(self):
        from crear_enlaces_pixeles import construir_enlace
        comunas_path = self.root / "comunas.shp"
        self.comunas.to_file(comunas_path)
        enlace = construir_enlace(
            self.catalogo.drop(columns=["cod_comuna"]), comunas_path)
        self.assertTrue(enlace.duplicated("pixel_id").any())
        residuo = self.root / "producto" / "sub" / "residuo.parquet.part"
        residuo.parent.mkdir(parents=True)
        residuo.write_bytes(b"incompleto")
        self.assertEqual(dmsp._limpiar_parts(self.root / "producto"), 1)
        self.assertFalse(residuo.exists())


if __name__ == "__main__":
    unittest.main()
