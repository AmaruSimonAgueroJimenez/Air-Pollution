"""Fixtures sintéticos con identidades reales del diagnóstico 404, sin red.

Origen de los cuatro pares de identificadores/nombres y fechas:
logs/comprobacion_http_404_historicos_20260914T2018.json.
Los tests no leen ese archivo, credenciales ni datos científicos externos.
"""
from __future__ import annotations

import copy
import itertools
import json
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _producciones_modis import seleccionar_produccion_nativa  # noqa: E402


class Granulo(dict):
    def __init__(self, cid, filename, *, revision=1, produccion=None,
                 inicio=None, fin=None, plataforma=None, producto=None):
        super().__init__(meta={"concept-id": cid, "revision-id": revision})
        self.enlaces = ["https://data.example.test/archivo/" + filename]
        umm = {}
        if produccion:
            umm["DataGranule"] = {"ProductionDateTime": produccion}
        if inicio:
            umm["TemporalExtent"] = {"RangeDateTime": {
                "BeginningDateTime": inicio, "EndingDateTime": fin}}
        if plataforma:
            umm["Platforms"] = [{"ShortName": plataforma}]
        if producto:
            umm["CollectionReference"] = {"ShortName": producto, "Version": "6.1"}
        if umm:
            self["umm"] = umm

    def data_links(self):
        return list(self.enlaces)


def terra():
    comun = {"inicio": "2022-10-24T14:15:00.000Z",
             "fin": "2022-10-24T14:20:00.000Z",
             "plataforma": "Terra", "producto": "MOD04_3K"}
    viejo = Granulo(
        "G2529349969-LAADS",
        "MOD04_3K.A2022297.1415.061.2022302120305.hdf",
        produccion="2022-10-29T12:03:05.000Z", **comun)
    nuevo = Granulo(
        "G2556079151-LAADS",
        "MOD04_3K.A2022297.1415.061.2022333212822.hdf",
        revision=2, produccion="2022-11-29T21:28:22.000Z", **comun)
    return viejo, nuevo


def maiac():
    comun = {"inicio": "2003-08-16T12:20:00.000Z",
             "fin": "2003-08-16T15:45:00.000Z",
             "producto": "MCD19A2"}
    viejo = Granulo(
        "G2393113417-LPCLOUD",
        "MCD19A2.A2003228.h14v14.061.2022210095449.hdf",
        produccion="2022-07-29T09:54:49.000Z", **comun)
    nuevo = Granulo(
        "G2424950770-LPCLOUD",
        "MCD19A2.A2003228.h14v14.061.2022239181311.hdf",
        produccion="2022-08-27T18:13:11.000Z", **comun)
    return viejo, nuevo


def elegir(gs, **kwargs):
    args = {"producto": "MOD04_3K", "coleccion": "6.1", "fecha": "2022-10-24"}
    args.update(kwargs)
    return seleccionar_produccion_nativa(gs, **args)


class SeleccionProduccionesTests(unittest.TestCase):
    def setUp(self):
        # Una regresión no puede convertir este selector puro en una descarga.
        self.red = patch("socket.socket", side_effect=AssertionError("red prohibida"))
        self.red.start()
        self.addCleanup(self.red.stop)

    def test_fixture_real_terra_elige_produccion_no_revision_cmr(self):
        viejo, nuevo = terra()
        viejo["meta"].update({"revision-id": 999, "revision-date": "2099-01-01T00:00:00Z"})
        gs, audit = elegir([nuevo, viejo])
        self.assertEqual(gs, [nuevo])
        self.assertIs(gs[0], nuevo)
        grupo = audit["grupos"][0]
        self.assertEqual(grupo["elegido"], "G2556079151-LAADS")
        self.assertEqual(grupo["superseded"][0]["concept_id"], "G2529349969-LAADS")
        self.assertEqual(audit["superseded"], 1)
        self.assertFalse(audit["politica"]["fallback_produccion_anterior"])

    def test_fixture_real_maiac_elige_produccion_diaria_multiorbita(self):
        viejo, nuevo = maiac()
        gs, audit = elegir([viejo, nuevo], producto="MCD19A2", coleccion="061",
                           fecha=date(2003, 8, 16))
        self.assertEqual(gs, [nuevo])
        self.assertEqual(audit["grupos"][0]["identidad_nativa"]["tipo"],
                         "tile_diario_multiorbita")
        self.assertTrue(audit["politica"]["equivalencia_orbitas_maiac_no_demostrada"])

    def test_invariancia_orden_y_preserva_horas_distintas(self):
        viejo, nuevo = terra()
        otro = Granulo("G999-LAADS", "MOD04_3K.A2022297.1515.061.2022333212822.hdf")
        esperado = None
        for orden in itertools.permutations([viejo, nuevo, otro]):
            gs, audit = elegir(orden)
            resultado = ([g["meta"]["concept-id"] for g in gs],
                         json.dumps(audit, sort_keys=True))
            if esperado is None:
                esperado = resultado
            self.assertEqual(resultado, esperado)
        self.assertEqual(esperado[0], ["G2556079151-LAADS", "G999-LAADS"])

    def test_preserva_tiles_distintos(self):
        viejo, nuevo = maiac()
        otro = Granulo("G999-LPCLOUD", "MCD19A2.A2003228.h13v14.061.2022239181311.hdf")
        gs, audit = elegir([nuevo, otro, viejo], producto="MCD19A2",
                           coleccion="061", fecha="2003-08-16")
        self.assertEqual(len(gs), 2)
        self.assertEqual([g["identidad_nativa"]["unidad"] for g in audit["grupos"]],
                         ["h13v14", "h14v14"])

    def test_aqua_seleccionable_pero_no_se_mezclan_sensores(self):
        aqua = Granulo("G12-LAADS", "MYD04_3K.A2022297.1415.061.2022333212822.hdf",
                       plataforma="Aqua", producto="MYD04_3K")
        self.assertEqual(elegir([aqua], producto="MYD04_3K")[0], [aqua])
        with self.assertRaisesRegex(ValueError, "producto o sensor"):
            elegir([terra()[0], aqua])

    def test_duplicados_bbox_identicos_no_mutan_entradas(self):
        viejo, nuevo = terra()
        antes = [copy.deepcopy(g) for g in (viejo, nuevo)]
        gs, audit = elegir([viejo, nuevo, viejo, copy.deepcopy(nuevo)])
        self.assertEqual(gs, [nuevo])
        self.assertEqual(audit["granulos_entrada"], 4)
        self.assertEqual(audit["candidatos_unicos"], 2)
        self.assertEqual(audit["duplicados_bbox"], 2)
        self.assertEqual([c["ocurrencias_bbox"] for c in audit["grupos"][0]["candidatos"]],
                         [2, 2])
        self.assertEqual([viejo, nuevo], antes)

    def test_mismo_concepto_con_revisiones_o_filename_diferentes_falla(self):
        viejo, _ = terra()
        copia = copy.deepcopy(viejo)
        copia["meta"]["revision-id"] = 2
        with self.assertRaisesRegex(ValueError, "contradictorios"):
            elegir([viejo, copia])

    def test_empate_entre_ids_distintos_falla_incluso_si_hay_otra_mas_nueva(self):
        viejo, nuevo = terra()
        empate = copy.deepcopy(viejo)
        empate["meta"]["concept-id"] = "G888-LAADS"
        for gs in ([viejo, empate], [viejo, empate, nuevo]):
            with self.assertRaisesRegex(ValueError, "empate"):
                elegir(gs)

    def test_vacio_y_alias_coleccion(self):
        gs, audit = elegir([], coleccion="061")
        self.assertEqual(gs, [])
        self.assertEqual(audit["grupos"], [])
        self.assertEqual(audit["seleccionados"], 0)
        self.assertEqual(elegir(terra(), coleccion="6.1")[1],
                         elegir(terra(), coleccion="061")[1])

    def test_rechaza_fechas_diferentes_y_argumentos_invalidos(self):
        for fecha in ("2022-10-25", "20221024", "2022-02-30", datetime(2022, 10, 24), None):
            with self.subTest(fecha=fecha), self.assertRaises(ValueError):
                elegir([terra()[0]], fecha=fecha)
        for kwargs in ({"producto": "OTRO"}, {"coleccion": "006"}, {"coleccion": None}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                elegir([], **kwargs)

    def test_identidad_cmr_desconocida_falla(self):
        for cambio in ({"concept-id": ""}, {"concept-id": "https://example.test/?token=secreto"},
                       {"revision-id": None}, {"revision-id": True}, {"revision-id": 0}):
            g = terra()[0]
            g["meta"].update(cambio)
            with self.subTest(cambio=cambio), self.assertRaises(ValueError):
                elegir([g])
        with self.assertRaises(ValueError):
            elegir([object()])

    def test_filename_y_calendarios_invalidos(self):
        nombres = [
            "MOD04_3K.A2022366.1415.061.2023001000000.hdf",
            "MOD04_3K.A2022297.2460.061.2022333212822.hdf",
            "MOD04_3K.A2022297.1415.006.2022333212822.hdf",
            "MOD04_3K.A2022297.1415.061.2022366212822.hdf",
            "MOD04_3K.A2022297.1415.061.2022333252822.hdf",
            "MOD04_3K.A2022297.1415.061.2022333212860.hdf",
            "MOD04_3K.A2022297.1415.061.2022296000000.hdf",
            "MOD04_3K.A2022297.h14v14.061.2022333212822.hdf",
            "MOD04_3K.A2022297.1415.061.test.hdf",
        ]
        for nombre in nombres:
            with self.subTest(nombre=nombre), self.assertRaises(ValueError):
                elegir([Granulo("G1-LAADS", nombre)])

    def test_bisiesto_valido_y_tiles_invalidos(self):
        g = Granulo("G1-LAADS", "MOD04_3K.A2020366.2355.061.2021001000000.hdf")
        self.assertEqual(elegir([g], fecha="2020-12-31")[0], [g])
        for tile in ("h36v14", "h14v18", "1415"):
            g = Granulo("G1-LPCLOUD", f"MCD19A2.A2003228.{tile}.061.2022239181311.hdf")
            with self.subTest(tile=tile), self.assertRaises(ValueError):
                elegir([g], producto="MCD19A2", fecha="2003-08-16")

    def test_urls_firmadas_no_aparecen_en_auditoria(self):
        viejo, nuevo = terra()
        for g in (viejo, nuevo):
            g.enlaces = [g.enlaces[0] + "?token=MUY_SECRETO#fragmento",
                         g.enlaces[0].replace("https://", "s3://") + "?otra=CLAVE"]
        _, audit = elegir([nuevo, viejo])
        texto = json.dumps(audit)
        for secreto in ("MUY_SECRETO", "CLAVE", "token=", "?", "data.example.test"):
            self.assertNotIn(secreto, texto)

    def test_links_ausentes_distintos_o_credenciales_embebidas_fallan(self):
        viejo, nuevo = terra()
        for enlaces in ([], [viejo.enlaces[0], nuevo.enlaces[0]],
                        [viejo.enlaces[0].replace("https://", "https://usuario:secreto@")],
                        ["https://example.test/incorrecto?token=NO_MOSTRAR"]):
            g = copy.deepcopy(viejo)
            g.enlaces = enlaces
            with self.subTest(enlaces=len(enlaces)), self.assertRaises(ValueError) as ctx:
                elegir([g])
            self.assertNotIn("NO_MOSTRAR", str(ctx.exception))
            self.assertNotIn("secreto", str(ctx.exception))

    def test_production_datetime_debe_concordar_con_filename(self):
        for pdt in ("2022-10-30T12:03:05Z", "2022-10-29T12:03:05", "inválido"):
            g = terra()[0]
            g["umm"]["DataGranule"]["ProductionDateTime"] = pdt
            with self.subTest(pdt=pdt), self.assertRaises(ValueError):
                elegir([g])

    def test_metadata_producto_coleccion_plataforma_deben_concordar(self):
        for campo, valor in (("CollectionReference", {"ShortName": "MYD04_3K", "Version": "6.1"}),
                             ("CollectionReference", {"ShortName": "MOD04_3K", "Version": "006"}),
                             ("Platforms", [{"ShortName": "Aqua"}]),
                             ("DataGranule", None), ("TemporalExtent", None)):
            g = terra()[0]
            g["umm"][campo] = valor
            with self.subTest(campo=campo, valor=valor), self.assertRaises(ValueError):
                elegir([g])

    def test_footprint_y_temporalidad_diferentes_no_se_fusionan(self):
        viejo, nuevo = terra()
        viejo["umm"]["SpatialExtent"] = {"HorizontalSpatialDomain": {"Geometry": {"p": 1}}}
        nuevo["umm"]["SpatialExtent"] = {"HorizontalSpatialDomain": {"Geometry": {"p": 2}}}
        with self.assertRaisesRegex(ValueError, "identidad UMM diferente"):
            elegir([viejo, nuevo])
        viejo, nuevo = terra()
        nuevo["umm"]["TemporalExtent"]["RangeDateTime"]["EndingDateTime"] = "2022-10-24T14:21:00Z"
        with self.assertRaisesRegex(ValueError, "identidad UMM diferente"):
            elegir([viejo, nuevo])
        nuevo["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"] = "2022-10-24T14:16:00Z"
        with self.assertRaisesRegex(ValueError, "contradice"):
            elegir([nuevo])

    @staticmethod
    def _espacio(g, lon=-114.965039, lat=-66.311682):
        g["umm"]["SpatialExtent"] = {"HorizontalSpatialDomain": {"Geometry": {
            "GPolygons": [{"Boundary": {"Points": [
                {"Longitude": lon, "Latitude": lat},
                {"Longitude": -49.228411, "Latitude": -76.305629},
            ]}}]}}}

    def test_redondeo_espacial_real_borde_es_auditable_e_invariante(self):
        viejo, nuevo = terra()
        self._espacio(viejo)
        self._espacio(nuevo, -114.965038, -66.311681)
        original = copy.deepcopy([viejo, nuevo])
        salida, audit = elegir([viejo, nuevo])
        self.assertEqual(salida, [nuevo])
        self.assertEqual(audit, elegir([nuevo, viejo])[1])
        self.assertEqual([viejo, nuevo], original)
        grupo = audit["grupos"][0]
        espacial = grupo["compatibilidad_metadata"]["espacial"]
        self.assertEqual(espacial["delta_maximo_grados"], 0.000001)
        self.assertEqual(espacial["tolerancia_grados"], 0.000001)
        self.assertNotEqual(grupo["candidatos"][0]["spatial_extent_sha256"],
                            grupo["candidatos"][1]["spatial_extent_sha256"])
        self.assertEqual(audit["politica"]["version"], "1.1.0")

    def test_redondeo_tres_candidatos_compara_rango_completo(self):
        viejo, nuevo = terra()
        intermedio = Granulo("G3-LAADS", "MOD04_3K.A2022297.1415.061.2022320120000.hdf",
                            produccion="2022-11-16T12:00:00Z",
                            inicio="2022-10-24T14:15:00Z", fin="2022-10-24T14:20:00Z",
                            plataforma="Terra", producto="MOD04_3K")
        for g, lon in ((viejo, -70.000001), (intermedio, -70.0), (nuevo, -69.999999)):
            self._espacio(g, lon)
        for orden in itertools.permutations([intermedio, viejo, nuevo]):
            with self.assertRaisesRegex(ValueError, "delta espacial"):
                elegir(orden)
        for g, lon in ((viejo, -70.000001), (intermedio, -70.0000005), (nuevo, -70.0)):
            self._espacio(g, lon)
        referencia = elegir([viejo, intermedio, nuevo])[1]
        for orden in itertools.permutations([intermedio, viejo, nuevo]):
            self.assertEqual(elegir(orden)[1], referencia)

    def test_fuera_tolerancia_estructura_orden_y_campos_extra_fallan(self):
        for tipo in ("delta", "estructura", "orden", "otro", "cadena", "booleano"):
            viejo, nuevo = terra()
            self._espacio(viejo)
            self._espacio(nuevo)
            espacio = nuevo["umm"]["SpatialExtent"]
            puntos = espacio["HorizontalSpatialDomain"]["Geometry"]["GPolygons"][0]["Boundary"]["Points"]
            if tipo == "delta":
                puntos[0]["Longitude"] = -114.965037999999
            elif tipo == "estructura":
                puntos.append(dict(puntos[0]))
            elif tipo == "orden":
                puntos.reverse()
            elif tipo == "otro":
                espacio["otro"] = 1
            elif tipo == "cadena":
                puntos[0]["Longitude"] = "-114.965039"
            else:
                puntos[0]["Longitude"] = False
            with self.subTest(tipo=tipo), self.assertRaisesRegex(ValueError, "identidad UMM diferente"):
                elegir([viejo, nuevo])

    def test_no_deduplica_entre_proveedores_ni_colecciones_cmr(self):
        viejo, nuevo = terra()
        nuevo["meta"]["concept-id"] = "G2556079151-OTRO"
        with self.assertRaisesRegex(ValueError, "proveedor"):
            elegir([viejo, nuevo])
        viejo, nuevo = terra()
        viejo["meta"]["collection-concept-id"] = "C1-LAADS"
        nuevo["meta"]["collection-concept-id"] = "C2-LAADS"
        with self.assertRaisesRegex(ValueError, "colección-concepto"):
            elegir([viejo, nuevo])

    def test_metadata_ausente_se_declara_y_mezcla_presente_ausente_falla(self):
        g = Granulo("G1-LAADS", "MOD04_3K.A2022297.1415.061.2022333212822.hdf")
        _, audit = elegir([g])
        self.assertFalse(any(audit["grupos"][0]["candidatos"][0]["validaciones_metadata"].values()))
        with self.assertRaisesRegex(ValueError, "identidad UMM diferente"):
            elegir([terra()[0], g])


if __name__ == "__main__":
    unittest.main()
