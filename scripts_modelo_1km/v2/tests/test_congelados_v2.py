"""Artefactos del piloto congelados por la Enmienda 1 (sólo lectura).

La Enmienda 1 deja congelados ``plan_corrida_v2.json`` (sha256 7385414e…) y ``piloto_tiempos/mediciones.json``
(aea002f6…), con el sha256 completo en ``config_v2.json`` → ``contrato.enmiendas[Enmienda 1].artefactos_congelados``.
Como el piloto se vuelve a medir y el plan se rehace (Complemento, punto 8), en la raíz v2 quedan copias con el
sufijo ``_congelado_enmienda1`` (``cp -p``). Estas pruebas comprueban que existen con ese sha256 (se saltan si la raíz
v2 del entorno no las tiene) y que el respaldo que dejan ``piloto_v2`` y ``pliegues_v2`` antes de sobrescribir nunca
usa ese sufijo.
"""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import _rutas_v2 as rv  # noqa: E402

SUFIJO = "_congelado_enmienda1"
CFG = json.loads((V2 / rv.NOMBRE_CONFIG).read_text(encoding="utf-8"))
ENMIENDA_1 = next(e for e in CFG["contrato"]["enmiendas"] if e["id"] == "Enmienda 1")
CONGELADOS = {k: v for k, v in ENMIENDA_1["artefactos_congelados"].items()
              if k in ("plan_corrida_v2.json", "piloto_tiempos/mediciones.json")}
R = rv.RutasV2.desde_entorno()


def copia_congelada(relativa: str) -> Path:
    p = R.raiz_v2 / relativa
    return p.with_name(f"{p.stem}{SUFIJO}{p.suffix}")


class CongeladosTests(unittest.TestCase):
    def test_la_enmienda_cita_los_dos_artefactos(self):
        self.assertEqual(sorted(CONGELADOS), ["piloto_tiempos/mediciones.json", "plan_corrida_v2.json"])
        contrato = (V2 / rv.NOMBRE_CONTRATO).read_text(encoding="utf-8")
        for relativa, sha in CONGELADOS.items():
            with self.subTest(artefacto=relativa):
                self.assertRegex(sha, r"^[0-9a-f]{64}$")
                self.assertIn(f"{sha[:8]}…", contrato)                  # el prefijo que cita la Enmienda 1

    def test_copias_congeladas_con_el_sha256_de_la_enmienda(self):
        faltan = [r for r in CONGELADOS if not copia_congelada(r).exists()]
        if faltan:
            self.skipTest(f"la raíz v2 {R.raiz_v2} no tiene las copias congeladas de {faltan}")
        for relativa, sha in CONGELADOS.items():
            with self.subTest(artefacto=relativa):
                copia = copia_congelada(relativa)
                self.assertEqual(hashlib.sha256(copia.read_bytes()).hexdigest(), sha)
                self.assertEqual(json.loads(copia.read_text(encoding="utf-8")).get("schema") is not None, True)

    def test_los_respaldos_no_pisan_las_copias_congeladas(self):
        """Los nombres de los respaldos de piloto_v2 (mediciones: «respaldo» y, con --rehacer, «reemplazado»; plan:
        «reemplazado») no son los de las copias congeladas y caen en el candado del artefacto que respaldan."""
        etiquetas = {"piloto_tiempos/mediciones.json": ("respaldo", "reemplazado"),
                     "plan_corrida_v2.json": ("reemplazado",)}
        for relativa in CONGELADOS:
            for etiqueta in etiquetas[relativa]:
                with self.subTest(artefacto=relativa, etiqueta=etiqueta):
                    destino = rv.ruta_de_respaldo(R.raiz_v2 / relativa, etiqueta)
                    self.assertNotIn(SUFIJO, destino.name)
                    self.assertNotEqual(destino, copia_congelada(relativa))
                    self.assertEqual(rv.candado_de(destino, R), rv.candado_de(R.raiz_v2 / relativa, R))


if __name__ == "__main__":
    unittest.main()
