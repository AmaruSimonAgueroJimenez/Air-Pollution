# -*- coding: utf-8 -*-
"""Pruebas de ``verificar_componentes_compartidos.py``.

Arman dos repositorios de juguete (``Air-Pollution`` y ``Air-Pollution-Health-Chile``) en una carpeta temporal y
nunca tocan los repositorios reales. Sólo biblioteca estándar::

    python -B -m unittest discover -s others_scripts/tests -v
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
CARPETA_SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CARPETA_SCRIPTS))
import verificar_componentes_compartidos as vcc  # noqa: E402

RUTA = vcc.RUTA_MANIFIESTO
SCRIPT = CARPETA_SCRIPTS / "verificar_componentes_compartidos.py"
ADAPTADO = "others_scripts/generar_indice_docs.py"


def escribir(raiz: Path, rel: str, contenido: str = "x\n") -> Path:
    ruta = raiz.joinpath(*rel.split("/"))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


def grupo(man: dict, nombre: str) -> dict:
    return next(g for g in man["grupos"] if g["nombre"] == nombre)


class Base(unittest.TestCase):
    """Dos repositorios coherentes, con basura excluida y carpetas propias sólo en un lado."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="vcc_prueba_")
        self._bloqueados: list[tuple[Path, int]] = []
        self.addCleanup(self._limpiar)
        self.base = Path(self._tmp.name).resolve()
        self.c = self.base / "Air-Pollution"
        self.e = self.base / "Air-Pollution-Health-Chile"
        comunes = {
            "scripts_pipeline/a.py": "print('a')\n",
            "scripts_pipeline/sub/b.py": "B = 1\n",
            "scripts_superficie/s.py": "S = 1\n",
            "scripts_estacion/comun.py": "E = 1\n",
            "scripts_modelo_1km/_comun_modelo.py": "X = 1\n",
            "scripts_modelo_1km/produccion.py": "# comentario\nQC_RACHA = 24\n",
            "scripts_modelo_1km/lanzar.sh": "echo hola\n",
            "config/sinca/c.json": "{}\n",
            "docs/modelo_1km_horario.qmd": "---\ntitle: modelo\n---\n",
            "docs/_tablas_compactas.html": "<style></style>\n",
            "docs/NOTA_PIPELINE.md": "nota\n",
            "others_scripts/aligerar_html.py": "pass\n",
            "output_files/modelo_1km/eval_niveles_pm25.csv": "a,b\n1,2\n",
            "output_files/modelo_1km_smoke/.etapa_ok": "",
            "output_files/figures/f.png": "png",
            "output_files/resumen.csv": "x\n",
        }
        for raiz in (self.c, self.e):
            for rel, contenido in comunes.items():
                escribir(raiz, rel, contenido)
        codigo = vcc.hash_codigo(self.c)
        documento = hashlib.sha256((self.c / "docs/modelo_1km_horario.qmd").read_bytes()).hexdigest()[:16]
        for raiz in (self.c, self.e):
            escribir(raiz, "docs/modelo_1km_horario.html",
                     f"<p>código <code>{codigo}</code> · documento <code>{documento}</code></p>\n")
        # propios y basura: no deben contar
        escribir(self.c, "README.md", "AP\n")
        escribir(self.e, "README.md", "APH\n")
        escribir(self.e, "scripts_pipeline/__pycache__/a.cpython-312.pyc", "x")
        escribir(self.e, "scripts_pipeline/.DS_Store", "x")
        escribir(self.e, "output_files/modelo_1km/fig 2.png", "")
        escribir(self.c, "output_files/modelo_1km/corrida.log", "log\n")
        escribir(self.e, "output_files/paper/figura.png", "png")
        escribir(self.e, "scripts_riesgo_agudo/panel.py", "pass\n")

    def _limpiar(self):
        for ruta, modo in reversed(self._bloqueados):
            with contextlib.suppress(OSError):
                os.chmod(ruta, modo)
        self._tmp.cleanup()

    def bloquear(self, ruta: Path) -> None:
        """Permisos 000 (se restauran al terminar la prueba)."""
        self._bloqueados.append((ruta, stat.S_IMODE(ruta.stat().st_mode)))
        os.chmod(ruta, 0)

    def correr(self, *args: str) -> tuple[int, str, str]:
        argv = ["--canonico", str(self.c), "--espejo", str(self.e), *args]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                codigo = vcc.main(argv)
            except SystemExit as exc:  # errores de uso de argparse
                codigo = exc.code
        return codigo, out.getvalue(), err.getvalue()

    def generar_y_copiar(self) -> None:
        codigo, out, err = self.correr("--generar", "--forzar")
        self.assertEqual(codigo, 0, out + err)
        shutil.copy2(self.c / RUTA, self.e / RUTA)

    def manifiesto(self) -> dict:
        return json.loads((self.c / RUTA).read_text(encoding="utf-8"))

    def guardar_manifiesto(self, man: dict, en_espejo: bool = True) -> None:
        texto = json.dumps(man, ensure_ascii=False, indent=2) + "\n"
        escribir(self.c, RUTA, texto)
        if en_espejo:
            escribir(self.e, RUTA, texto)


class Coherencia(Base):
    def test_coherente_sale_0(self):
        self.generar_y_copiar()
        codigo, out, err = self.correr()
        self.assertEqual(codigo, 0, out + err)
        self.assertIn("COHERENTE", out)
        self.assertNotIn("DIVERGE", out)
        for ajeno in ("__pycache__", ".DS_Store", "fig 2.png", "corrida.log", "output_files/paper",
                      "README.md", "scripts_riesgo_agudo"):
            self.assertNotIn(ajeno, out)

    def test_manifiesto_generado_sin_rutas_absolutas_y_con_lo_esperado(self):
        self.generar_y_copiar()
        texto = (self.c / RUTA).read_text(encoding="utf-8")
        self.assertNotIn(str(self.base), texto)
        self.assertNotIn(str(Path.home()), texto)
        man = json.loads(texto)
        self.assertEqual(man["esquema"], "componentes-compartidos/v1")
        self.assertEqual(man["direccion"], "canonico->espejo")
        self.assertIn("scripts_pipeline/sub/b.py", grupo(man, "pipeline")["sha256"])
        self.assertIn("output_files/modelo_1km_smoke/.etapa_ok", grupo(man, "salidas_modelo")["sha256"])
        self.assertNotIn(RUTA, grupo(man, "config")["sha256"])
        todos = {r for g in man["grupos"] if g["modo"] == "identico" for r in g["sha256"]}
        for ajeno in ("output_files/modelo_1km/corrida.log", "output_files/paper/figura.png", "README.md"):
            self.assertNotIn(ajeno, todos)
        self.assertEqual(man["hash_codigo"]["esperado"], vcc.hash_codigo(self.c))
        self.assertEqual(man["hash_codigo"]["observado"]["Air-Pollution-Health-Chile"], vcc.hash_codigo(self.e))
        self.assertEqual(man["hash_codigo"]["declarado_en_informe"]["codigo"], [vcc.hash_codigo(self.c)])


class Divergencias(Base):
    def setUp(self):
        super().setUp()
        self.generar_y_copiar()

    def test_archivo_distinto_en_el_espejo_sale_1(self):
        escribir(self.e, "scripts_pipeline/sub/b.py", "B = 2\n")
        codigo, out, _ = self.correr()
        self.assertEqual(codigo, 1, out)
        self.assertIn("DIVERGE [pipeline] scripts_pipeline/sub/b.py: distinto en el espejo", out)

    def test_archivo_que_sobra_en_el_espejo_sale_1(self):
        escribir(self.e, "config/sinca/extra.json", "{}\n")
        codigo, out, _ = self.correr()
        self.assertEqual(codigo, 1, out)
        self.assertIn("DIVERGE [config] config/sinca/extra.json: sobra en el espejo", out)

    def test_archivo_que_falta_en_el_espejo_sale_1(self):
        (self.e / "output_files/modelo_1km/eval_niveles_pm25.csv").unlink()
        codigo, out, _ = self.correr()
        self.assertEqual(codigo, 1, out)
        self.assertIn("DIVERGE [salidas_modelo] output_files/modelo_1km/eval_niveles_pm25.csv: falta en el espejo",
                      out)

    def test_canonico_cambiado_desde_el_manifiesto_sale_1(self):
        for raiz in (self.c, self.e):  # iguales entre sí, distintos de lo manifestado
            escribir(raiz, "scripts_pipeline/a.py", "print('cambiado')\n")
        codigo, out, _ = self.correr()
        self.assertEqual(codigo, 1, out)
        self.assertIn("scripts_pipeline/a.py: el canónico cambió desde el manifiesto", out)
        self.assertNotIn("distinto en el espejo", out)

    def test_archivo_nuevo_en_los_dos_sin_regenerar_sale_1(self):
        for raiz in (self.c, self.e):
            escribir(raiz, "scripts_superficie/nuevo.py", "pass\n")
        codigo, out, _ = self.correr()
        self.assertEqual(codigo, 1, out)
        self.assertIn("scripts_superficie/nuevo.py: nuevo en el canónico y no declarado", out)

    def test_archivo_borrado_de_los_dos_sin_regenerar_sale_1(self):
        for raiz in (self.c, self.e):
            (raiz / "scripts_estacion/comun.py").unlink()
        codigo, out, _ = self.correr()
        self.assertEqual(codigo, 1, out)
        self.assertIn("scripts_estacion/comun.py: declarado en el manifiesto y ausente del canónico", out)

    def test_regenerar_y_copiar_vuelve_a_0(self):
        escribir(self.c, "scripts_pipeline/a.py", "print('v2')\n")
        self.assertEqual(self.correr()[0], 1)
        shutil.copy2(self.c / "scripts_pipeline/a.py", self.e / "scripts_pipeline/a.py")
        self.generar_y_copiar()
        codigo, out, _ = self.correr()
        self.assertEqual(codigo, 0, out)

    def test_copia_del_manifiesto_distinta_sale_1(self):
        with open(self.e / RUTA, "a", encoding="utf-8") as fh:
            fh.write("\n")
        codigo, out, _ = self.correr()
        self.assertEqual(codigo, 1, out)
        self.assertIn(f"DIVERGE [manifiesto] {RUTA}: la copia del espejo es distinta", out)

    def test_enlace_simbolico_dentro_de_un_grupo_sale_1(self):
        os.symlink("a.py", self.e / "scripts_pipeline" / "enlace.py")
        codigo, out, _ = self.correr()
        self.assertEqual(codigo, 1, out)
        self.assertIn("scripts_pipeline/enlace.py: enlace simbólico en el espejo", out)

    def test_espejo_inexistente_sale_2(self):
        codigo, _, err = self.correr("--espejo", str(self.base / "no_existe"))
        self.assertEqual(codigo, 2, err)


class ManifiestoInvalido(Base):
    def setUp(self):
        super().setUp()
        self.generar_y_copiar()
        self.valido = self.manifiesto()

    def variante(self, cambio) -> str:
        man = json.loads(json.dumps(self.valido))
        cambio(man)
        return json.dumps(man, ensure_ascii=False)

    def test_variantes_invalidas_salen_2(self):
        cero, uno = "0" * 64, "1" * 64
        casos = {
            "no es JSON": "{esto no es json",
            "raíz que no es un objeto": "[]",
            "esquema desconocido": self.variante(lambda m: m.update(esquema="componentes-compartidos/v9")),
            "dirección invertida": self.variante(lambda m: m.update(direccion="espejo->canonico")),
            "dos espejos": self.variante(lambda m: m["espejos"].append({"repo": "Otro"})),
            "modo desconocido": self.variante(lambda m: grupo(m, "pipeline").update(modo="parecido")),
            "grupo repetido": self.variante(lambda m: m["grupos"].append(dict(grupo(m, "config")))),
            "sha256 no hexadecimal": self.variante(
                lambda m: grupo(m, "pipeline")["sha256"].update({"scripts_pipeline/a.py": "zzz"})),
            "patrón absoluto": self.variante(lambda m: grupo(m, "pipeline").update(incluir=["/etc/**"])),
            "patrón con ..": self.variante(lambda m: grupo(m, "pipeline").update(incluir=["../otro/**"])),
            "ruta prohibida declarada": self.variante(
                lambda m: grupo(m, "pipeline")["sha256"].update({"scripts_pipeline/datos_privado.py": cero})),
            "ruta fuera de los patrones del grupo": self.variante(
                lambda m: grupo(m, "pipeline")["sha256"].update({"config/otro.json": cero})),
            "adaptado sin motivo": self.variante(lambda m: grupo(m, "adaptados")["archivos"].update(
                {"others_scripts/x.py": {"plan": "p", "sha256_canonico": cero, "sha256_espejo": uno}})),
            "adaptado que también está en un grupo idéntico": self.variante(
                lambda m: grupo(m, "adaptados")["archivos"].update({"scripts_pipeline/a.py": {
                    "motivo": "m", "plan": "p", "sha256_canonico": cero, "sha256_espejo": uno}})),
            "hash_codigo sin observado": self.variante(lambda m: m["hash_codigo"].pop("observado")),
            "excepción sin plan": self.variante(
                lambda m: m["hash_codigo"].update(excepcion={"vigente": True, "motivo": "m"})),
            "huellas del informe que no son objeto": self.variante(
                lambda m: m["hash_codigo"].update(declarado_en_informe="abc")),
            "huellas del informe no hexadecimales": self.variante(
                lambda m: m["hash_codigo"].update(declarado_en_informe={"codigo": ["zz"], "documento": []})),
        }
        for nombre, texto in casos.items():
            with self.subTest(nombre):
                escribir(self.c, RUTA, texto)
                codigo, out, err = self.correr()
                self.assertEqual(codigo, 2, f"{nombre}: {out}{err}")
                self.assertIn("ERROR", err)

    def test_manifiesto_ausente_sale_2(self):
        (self.c / RUTA).unlink()
        codigo, _, err = self.correr()
        self.assertEqual(codigo, 2, err)

    def test_generar_sobre_un_manifiesto_invalido_sale_2_y_no_lo_toca(self):
        escribir(self.c, RUTA, "{roto")
        codigo, _, err = self.correr("--generar", "--forzar")
        self.assertEqual(codigo, 2, err)
        self.assertEqual((self.c / RUTA).read_text(encoding="utf-8"), "{roto")


class RutasProhibidas(Base):
    def test_nunca_abre_ni_lista_rutas_privadas(self):
        bloqueadas = [
            escribir(self.c, "scripts_pipeline/datos_privado/registro.csv", "1\n").parent,
            escribir(self.e, "scripts_pipeline/datos_privado/registro.csv", "1\n").parent,
            escribir(self.c, "config/sinca/lista_PRIVADO.json", "{}\n"),  # sólo en el canónico
            escribir(self.e, "output_files/modelo_1km/MNI1_cohorte/a.csv", "1\n").parent,  # sólo en el espejo
            escribir(self.c, "docs/notas_mni1.md", "x\n"),  # cae dentro de docs/*.md
            escribir(self.e, "others_scripts/privado_util.py", "x\n"),
        ]
        for ruta in bloqueadas:
            self.bloquear(ruta)
        vistos: list[str] = []
        listar, abrir = vcc._listar_directorio, vcc._abrir_lectura

        def listar_espia(carpeta):
            vistos.append(str(carpeta))
            return listar(carpeta)

        def abrir_espia(ruta):
            vistos.append(str(ruta))
            return abrir(ruta)

        with mock.patch.object(vcc, "_listar_directorio", listar_espia), \
                mock.patch.object(vcc, "_abrir_lectura", abrir_espia):
            codigo, out, err = self.correr("--generar", "--forzar")
            self.assertEqual(codigo, 0, out + err)
            shutil.copy2(self.c / RUTA, self.e / RUTA)
            for extra in ((), ("--plan",)):
                codigo, out, err = self.correr(*extra)
                self.assertEqual(codigo, 0, out + err)
                self.assertIn("COHERENTE", out)
        self.assertTrue(vistos)
        tocadas = [v for v in vistos if vcc.prohibida(os.path.relpath(v, self.base))]
        self.assertEqual(tocadas, [])
        texto = (self.c / RUTA).read_text(encoding="utf-8").lower()
        for nombre in ("datos_privado", "lista_privado", "mni1_cohorte", "notas_mni1", "privado_util"):
            self.assertNotIn(nombre, texto)

    def test_control_un_archivo_ilegible_sin_nombre_prohibido_sale_2(self):
        """Sin la poda por nombre, la prueba anterior fallaría así."""
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root lee archivos con permisos 000")
        self.generar_y_copiar()
        self.bloquear(self.e / "scripts_pipeline" / "a.py")
        codigo, out, err = self.correr()
        self.assertEqual(codigo, 2, out + err)
        self.assertIn("scripts_pipeline/a.py", err)


class HashCodigo(Base):
    def test_replica_de_la_definicion(self):
        h = hashlib.sha256()
        carpeta = self.c / "scripts_modelo_1km"
        for ruta in [*sorted(carpeta.glob("*.py")), self.c / "docs" / "modelo_1km_horario.qmd"]:
            h.update(ruta.name.encode())
            h.update(hashlib.sha256(ruta.read_bytes()).digest())
        self.assertEqual(vcc.hash_codigo(self.c), h.hexdigest()[:16])
        self.assertIsNone(vcc.hash_codigo(self.base))

    def test_como_el_original_no_aplica_exclusiones(self):
        antes = vcc.hash_codigo(self.c)
        escribir(self.c, "scripts_modelo_1km/copia 2.py", "X = 1\n")  # el modelo también la contaría
        self.assertNotEqual(vcc.hash_codigo(self.c), antes)
        escribir(self.e, "scripts_modelo_1km/lanzar_otro.sh", "echo\n")  # no es .py: no cuenta
        self.assertEqual(vcc.hash_codigo(self.e), antes)

    def test_diferencia_con_excepcion_vigente_sale_0(self):
        escribir(self.e, "scripts_modelo_1km/produccion.py", "# otro comentario\nQC_RACHA = 24\n")
        self.generar_y_copiar()
        codigo, out, _ = self.correr()
        self.assertEqual(codigo, 1, out)
        self.assertIn("scripts_modelo_1km/produccion.py: distinto en el espejo", out)
        self.assertIn("sin excepción vigente", out)

        man = self.manifiesto()
        grupo(man, "adaptados")["archivos"]["scripts_modelo_1km/produccion.py"] = {
            "tipo": "comentario", "motivo": "comentario propio del espejo", "plan": "copiar del canónico"}
        man["hash_codigo"]["excepcion"] = {"vigente": True, "motivo": "el espejo tiene otro comentario",
                                           "plan": "copiar del canónico y regenerar"}
        self.guardar_manifiesto(man, en_espejo=False)
        self.generar_y_copiar()
        codigo, out, _ = self.correr()
        self.assertEqual(codigo, 0, out)
        self.assertIn("excepción vigente", out)
        observado = self.manifiesto()["hash_codigo"]["observado"]
        self.assertNotEqual(observado["Air-Pollution"], observado["Air-Pollution-Health-Chile"])

        man = self.manifiesto()
        man["hash_codigo"]["excepcion"]["vigente"] = False
        self.guardar_manifiesto(man)
        codigo, out, _ = self.correr()
        self.assertEqual(codigo, 1, out)
        self.assertIn("sin excepción vigente", out)

    def test_informe_que_estampa_otra_huella_exige_excepcion(self):
        for raiz in (self.c, self.e):
            escribir(raiz, "docs/modelo_1km_horario.html", "<li>Código <code>0123456789abcdef</code></li>\n")
        self.generar_y_copiar()
        codigo, out, _ = self.correr()
        self.assertEqual(codigo, 1, out)
        self.assertIn("el informe estampa 0123456789abcdef", out)

    def test_excepcion_sobrante_se_quita_al_regenerar(self):
        self.generar_y_copiar()
        man = self.manifiesto()
        man["hash_codigo"]["excepcion"] = {"vigente": True, "motivo": "m", "plan": "p"}
        self.guardar_manifiesto(man)
        codigo, out, _ = self.correr()
        self.assertEqual(codigo, 0, out)
        self.assertIn("AVISO hash_codigo: canónico, espejo e informe coinciden", out)
        codigo, out, _ = self.correr("--generar", "--forzar")
        self.assertEqual(codigo, 0, out)
        self.assertIn("la excepción ya no hace falta", out)
        self.assertNotIn("excepcion", self.manifiesto()["hash_codigo"])


class Adaptados(Base):
    def setUp(self):
        super().setUp()
        escribir(self.c, ADAPTADO, "VIGENTES = []\n")
        escribir(self.e, ADAPTADO, "VIGENTES = ['salud']\n")
        man = vcc.plantilla()
        grupo(man, "adaptados")["archivos"][ADAPTADO] = {
            "tipo": "catalogo", "motivo": "catálogo de documentos propio de cada repositorio",
            "plan": "sacar el catálogo a un archivo propio"}
        self.guardar_manifiesto(man, en_espejo=False)
        self.generar_y_copiar()

    def test_adaptado_declarado_sale_0(self):
        codigo, out, _ = self.correr()
        self.assertEqual(codigo, 0, out)
        self.assertIn("ok  adaptados: 1 diferencia declarada", out)
        self.assertNotIn(ADAPTADO, grupo(self.manifiesto(), "utilitarios")["sha256"])

    def test_adaptado_cambiado_en_el_espejo_sale_1_y_no_entra_en_el_plan(self):
        escribir(self.e, ADAPTADO, "VIGENTES = ['salud', 'neuro']\n")
        codigo, out, _ = self.correr("--plan")
        self.assertEqual(codigo, 1, out)
        self.assertIn(f"{ADAPTADO}: el espejo cambió", out)
        self.assertIn("# Nada que copiar", out)
        self.assertIn(f"#   {ADAPTADO}", out)

    def test_adaptado_cambiado_en_el_canonico_sale_1(self):
        escribir(self.c, ADAPTADO, "VIGENTES = ['otro']\n")
        codigo, out, _ = self.correr()
        self.assertEqual(codigo, 1, out)
        self.assertIn(f"{ADAPTADO}: el canónico cambió", out)

    def test_adaptado_ya_igual_sale_1_y_al_regenerar_pasa_al_grupo_identico(self):
        shutil.copy2(self.c / ADAPTADO, self.e / ADAPTADO)
        codigo, out, _ = self.correr()
        self.assertEqual(codigo, 1, out)
        self.assertIn("ya es igual en los dos lados", out)
        codigo, out, _ = self.correr("--generar", "--forzar")
        self.assertEqual(codigo, 0, out)
        self.assertIn("sale de «adaptado»", out)
        shutil.copy2(self.c / RUTA, self.e / RUTA)
        man = self.manifiesto()
        self.assertEqual(grupo(man, "adaptados")["archivos"], {})
        self.assertIn(ADAPTADO, grupo(man, "utilitarios")["sha256"])
        self.assertEqual(self.correr()[0], 0)


class Plan(Base):
    def setUp(self):
        super().setUp()
        self.generar_y_copiar()

    @staticmethod
    def orden_y_lista(out: str) -> tuple[str, list[str]]:
        lineas = out.splitlines()
        i = next(i for i, linea in enumerate(lineas) if linea.startswith("rsync "))
        return lineas[i], lineas[i + 1:lineas.index("LISTA", i)]

    def foto(self, raiz: Path) -> dict[str, bytes]:
        return {p.relative_to(raiz).as_posix(): p.read_bytes() for p in raiz.rglob("*") if p.is_file()}

    def test_plan_imprime_rsync_sin_ejecutarlo(self):
        (self.e / "config/sinca/c.json").unlink()
        escribir(self.e, "scripts_pipeline/a.py", "print('viejo')\n")
        escribir(self.e, "scripts_pipeline/sobra.py", "pass\n")
        antes = self.foto(self.e)
        codigo, out, _ = self.correr("--plan")
        self.assertEqual(codigo, 1, out)
        orden, lista = self.orden_y_lista(out)
        for opcion in ("rsync -a", "--checksum", "--dry-run", "--files-from=-"):
            self.assertIn(opcion, orden)
        self.assertNotIn("--delete", orden)
        self.assertEqual(lista, ["config/sinca/c.json", "scripts_pipeline/a.py"])
        self.assertIn("#   scripts_pipeline/sobra.py", out)
        self.assertEqual(self.foto(self.e), antes)

        rsync, bash = shutil.which("rsync"), shutil.which("bash")
        if rsync and bash:  # la orden impresa (con --dry-run) es válida y no cambia nada
            guion = "\n".join(out.splitlines()[out.splitlines().index(orden):])
            r = subprocess.run([bash, "-c", guion], cwd=os.getcwd(), capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("scripts_pipeline/a.py", r.stdout)
            self.assertEqual(self.foto(self.e), antes)

    def test_plan_sin_divergencias(self):
        codigo, out, _ = self.correr("--plan")
        self.assertEqual(codigo, 0, out)
        self.assertIn("# Nada que copiar", out)
        self.assertNotIn("rsync ", out)


class Generar(Base):
    def test_no_sobrescribe_sin_forzar(self):
        self.generar_y_copiar()
        antes = (self.c / RUTA).read_bytes()
        escribir(self.c, "scripts_pipeline/a.py", "print('nuevo')\n")
        codigo, out, _ = self.correr("--generar")
        self.assertEqual(codigo, 1, out)
        self.assertIn("CAMBIA [pipeline] scripts_pipeline/a.py: sha256", out)
        self.assertIn("--forzar", out)
        self.assertEqual((self.c / RUTA).read_bytes(), antes)
        codigo, out, _ = self.correr("--generar", "--forzar")
        self.assertEqual(codigo, 0, out)
        self.assertNotEqual((self.c / RUTA).read_bytes(), antes)

    def test_sin_cambios_no_reescribe(self):
        self.generar_y_copiar()
        antes = (self.c / RUTA).read_bytes()
        codigo, out, _ = self.correr("--generar")
        self.assertEqual(codigo, 0, out)
        self.assertIn("Sin cambios", out)
        self.assertEqual((self.c / RUTA).read_bytes(), antes)

    def test_conserva_descripciones_y_motivos(self):
        man = vcc.plantilla()
        grupo(man, "pipeline")["descripcion"] = "texto escrito a mano"
        man["versiones_modelo"] = [{"etiqueta": "", "raiz": "LOCAL/AirPollution/modelado_1km"}]
        self.guardar_manifiesto(man, en_espejo=False)
        self.generar_y_copiar()
        nuevo = self.manifiesto()
        self.assertEqual(grupo(nuevo, "pipeline")["descripcion"], "texto escrito a mano")
        self.assertEqual(nuevo["versiones_modelo"], man["versiones_modelo"])

    def test_forzar_sin_generar_es_error_de_uso(self):
        self.assertEqual(self.correr("--forzar")[0], 2)


class Inferencia(Base):
    def test_carpetas_hermanas_por_omision(self):
        for raiz in (self.c, self.e):
            shutil.copy2(SCRIPT, raiz / "others_scripts" / SCRIPT.name)
        self.generar_y_copiar()
        for raiz in (self.c, self.e):
            r = subprocess.run([sys.executable, "-B", str(raiz / "others_scripts" / SCRIPT.name)], cwd=raiz,
                               capture_output=True, text=True, timeout=300)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("COHERENTE", r.stdout)


class Registro(Base):
    def test_registrar_anade_lineas_sin_rutas_absolutas(self):
        self.generar_y_copiar()
        registro = self.base / "registro.jsonl"
        for n in (1, 2):
            codigo, out, err = self.correr("--registrar", str(registro))
            self.assertEqual(codigo, 0, out + err)
            lineas = registro.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lineas), n)
        dato = json.loads(lineas[-1])
        self.assertEqual(dato["resultado"], "coherente")
        self.assertEqual(dato["divergencias"], 0)
        self.assertEqual(dato["hash_codigo"]["canonico"], vcc.hash_codigo(self.c))
        self.assertEqual(dato["manifiesto"]["sha256"], hashlib.sha256((self.c / RUTA).read_bytes()).hexdigest())
        self.assertNotIn(str(self.base), lineas[-1])

    def test_registra_las_divergencias(self):
        self.generar_y_copiar()
        escribir(self.e, "scripts_pipeline/a.py", "print('otro')\n")
        registro = self.base / "registro.jsonl"
        codigo, _, _ = self.correr("--registrar", str(registro))
        self.assertEqual(codigo, 1)
        dato = json.loads(registro.read_text(encoding="utf-8"))
        self.assertEqual(dato["resultado"], "divergente")
        self.assertEqual(dato["divergencias_por_grupo"], {"pipeline": 1})


class ActualizacionAcotada(Base):
    """Git y archivos exclusivamente de juguete; ningún commit de fixture acredita producción."""
    REL = "scripts_pipeline/a.py"

    def git(self, repo, *args):
        entorno = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        entorno.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_AUTHOR_NAME="Prueba", GIT_AUTHOR_EMAIL="prueba@example.invalid",
                       GIT_COMMITTER_NAME="Prueba", GIT_COMMITTER_EMAIL="prueba@example.invalid")
        return subprocess.check_output(["git", "--no-optional-locks", "-c", "core.hooksPath=" + os.devnull,
                                        "-C", str(repo), *args], env=entorno, stderr=subprocess.PIPE)

    def confirmar(self, repo):
        self.git(repo, "add", "--", ".")
        self.git(repo, "commit", "-qm", "fixture sintético")

    def setUp(self):
        super().setUp()
        self.generar_y_copiar()
        self.original = self.manifiesto()
        self.archivo_base = self.base / "base.json"
        self.archivo_base.write_bytes((self.c / RUTA).read_bytes())
        self.salida = self.base / "candidata.json"
        self.commits_base = {}
        for repo in (self.c, self.e):
            self.git(repo, "init", "-q")
            self.confirmar(repo)
            self.commits_base[repo] = self.git(repo, "rev-parse", "HEAD").decode().strip()
            escribir(repo, self.REL, "print('nuevo confirmado')\n")
            self.confirmar(repo)

    def actualizar(self, *args):
        return self.correr("--actualizar-ruta", self.REL, "--base", str(self.archivo_base),
                           "--salida", str(self.salida), *args)

    def test_preview_no_escribe_ni_declara_coherencia(self):
        codigo, out, err = self.actualizar()
        self.assertEqual(codigo, 1, out + err)
        self.assertFalse(self.salida.exists())
        self.assertIn("verificación global no ejecutada", out)
        self.assertNotIn("COHERENTE", out)
        self.assertEqual(self.manifiesto(), self.original)

    def test_solo_sha_y_procedencia_con_idempotencia(self):
        codigo, out, err = self.actualizar("--forzar")
        self.assertEqual(codigo, 0, out + err)
        nuevo = json.loads(self.salida.read_bytes())
        registro = nuevo.pop("actualizaciones_acotadas")[0]
        self.assertEqual(registro["base"]["sha256"], hashlib.sha256(self.archivo_base.read_bytes()).hexdigest())
        self.assertEqual(registro["verificacion_global"], "no_ejecutada")
        self.assertEqual(len(registro["seleccion"]), 1)
        self.assertEqual(len(registro["cambios"]), 1)
        grupo(nuevo, "pipeline")["sha256"][self.REL] = grupo(self.original, "pipeline")["sha256"][self.REL]
        self.assertEqual(nuevo, self.original)
        antes, fecha = self.salida.read_bytes(), self.salida.stat().st_mtime_ns
        codigo, out, err = self.actualizar("--forzar")
        self.assertEqual(codigo, 0, out + err)
        self.assertIn("Sin cambios", out)
        self.assertEqual((self.salida.read_bytes(), self.salida.stat().st_mtime_ns), (antes, fecha))

    def test_no_abre_fuentes_ajenas_ni_funciones_globales(self):
        permitidos = {self.archivo_base.resolve(), self.salida.resolve(), SCRIPT.resolve(),
                      (self.c / self.REL).resolve(), (self.e / self.REL).resolve()}
        abrir = vcc._abrir_lectura
        def espia(p):
            self.assertIn(Path(p).resolve(), permitidos)
            return abrir(p)
        with contextlib.ExitStack() as pila:
            for nombre in ("expandir", "hash_codigo", "_huellas_informe", "construir_manifiesto", "_estado_git"):
                pila.enter_context(mock.patch.object(vcc, nombre, side_effect=AssertionError(nombre)))
            pila.enter_context(mock.patch.object(vcc, "_abrir_lectura", espia))
            codigo, out, err = self.actualizar("--forzar")
        self.assertEqual(codigo, 0, out + err)

    def test_alta_y_divergencias_ajenas_permanecen(self):
        rel = "scripts_pipeline/nuevo.py"
        for repo in (self.c, self.e):
            escribir(repo, rel, "N = 1\n")
            escribir(repo, "scripts_superficie/s.py", "S = 999\n")
            self.confirmar(repo)
        codigo, out, err = self.actualizar("--actualizar-ruta", rel, "--forzar")
        self.assertEqual(codigo, 0, out + err)
        man = json.loads(self.salida.read_bytes())
        self.assertEqual(len(man["actualizaciones_acotadas"][0]["cambios"]), 2)
        self.assertIsNone(man["actualizaciones_acotadas"][0]["cambios"][1]["anterior"])
        self.guardar_manifiesto(man)
        codigo, out, err = self.correr()
        self.assertEqual(codigo, 1, out + err)
        self.assertIn("scripts_superficie/s.py: el canónico cambió", out)
        self.assertNotIn(self.REL + ": el canónico cambió", out)

    def test_rechaza_sin_rastrear_staged_unstaged_y_borrados(self):
        for variante in ("sin_rastrear", "staged", "unstaged", "borrado"):
            with self.subTest(variante=variante):
                repo = self.e
                if variante == "sin_rastrear":
                    self.git(repo, "rm", "--cached", "--", self.REL)
                elif variante == "borrado":
                    (repo / self.REL).unlink()
                else:
                    escribir(repo, self.REL, "cambio\n")
                    if variante == "staged":
                        self.git(repo, "add", "--", self.REL)
                codigo, _, _ = self.actualizar("--forzar")
                self.assertEqual(codigo, 2)
                self.assertFalse(self.salida.exists())
                # Restauración exclusivamente en el repositorio temporal de prueba.
                self.git(repo, "restore", "--source=HEAD", "--staged", "--worktree", "--", self.REL)

    def test_rechaza_estados_ocultos_y_bytes_aun_si_status_omite(self):
        for flag, deshacer in (("--assume-unchanged", "--no-assume-unchanged"),
                               ("--skip-worktree", "--no-skip-worktree")):
            with self.subTest(flag=flag):
                self.git(self.e, "update-index", flag, "--", self.REL)
                escribir(self.e, self.REL, "oculto\n")
                self.assertEqual(self.actualizar("--forzar")[0], 2)
                self.git(self.e, "update-index", deshacer, "--", self.REL)
                self.git(self.e, "restore", "--", self.REL)
        git = vcc._git_acotado
        def estado_oculto(repo, *args):
            return b"" if args[0] == "status" else git(repo, *args)
        escribir(self.e, self.REL, "diferencia sin status\n")
        with mock.patch.object(vcc, "_git_acotado", estado_oculto):
            self.assertEqual(self.actualizar("--forzar")[0], 2)

    def test_rechaza_fuentes_confirmadas_distintas(self):
        escribir(self.e, self.REL, "distinto confirmado\n")
        self.confirmar(self.e)
        self.assertEqual(self.actualizar("--forzar")[0], 2)
        self.assertFalse(self.salida.exists())

    def test_rechaza_rutas_peligrosas_antes_de_leerlas(self):
        for rel in ("../a.py", "/tmp/a.py", "scripts_pipeline/*.py", "scripts_pipeline/a[1].py",
                    "scripts_pipeline/privado/a.py", "scripts_pipeline/MNI1.py", "scripts_pipeline/.git/config",
                    "scripts_pipeline/.env", "scripts_pipeline/credentials.json", "scripts_pipeline/__pycache__/a.py",
                    "scripts_pipeline/a 2.py", "config/token.json", RUTA):
            with self.subTest(rel=rel):
                with self.assertRaises(vcc.ManifiestoInvalido):
                    vcc._ruta_acotada(rel)

    def test_rechaza_excluido_propio_adaptado_y_grupo_ambiguo(self):
        for variante in ("excluido", "propio", "adaptado", "ambiguo"):
            man = json.loads(json.dumps(self.original))
            if variante == "excluido":
                grupo(man, "pipeline")["excluir"] = [self.REL]
            elif variante == "propio":
                man["propios"][self.e.name].append(self.REL)
            elif variante == "adaptado":
                grupo(man, "adaptados")["archivos"][self.REL] = {}
            else:
                man["grupos"].append({"nombre": "solapado", "modo": "identico", "incluir": [self.REL], "sha256": {}})
            with self.subTest(variante=variante), self.assertRaises(vcc.ManifiestoInvalido):
                vcc._grupo_acotado(man, self.REL)

    def test_rechaza_enlaces_de_archivo_y_directorio(self):
        (self.e / self.REL).unlink()
        os.symlink(self.c / self.REL, self.e / self.REL)
        self.assertEqual(self.actualizar("--forzar")[0], 2)
        with self.assertRaises(vcc.ErrorLectura):
            vcc._capturar_acotado(self.e, [self.REL])
        (self.e / self.REL).unlink()
        self.git(self.e, "restore", "--", self.REL)
        original = self.e / "scripts_pipeline"
        original.rename(self.e / "movido")
        os.symlink(self.e / "movido", original)
        self.assertEqual(self.actualizar("--forzar")[0], 2)

    def test_base_no_confirmada_activos_y_mismo_repo_bloquean(self):
        self.assertEqual(self.actualizar("--salida", str(self.c / RUTA), "--forzar")[0], 2)
        self.assertEqual(self.actualizar("--espejo", str(self.c), "--forzar")[0], 2)
        man = json.loads(self.archivo_base.read_bytes())
        man["descripcion"] += " no confirmada"
        self.archivo_base.write_text(json.dumps(man), encoding="utf-8")
        self.assertEqual(self.actualizar("--forzar")[0], 2)
        self.assertFalse(self.salida.exists())

    def test_commits_base_explicitos_reales_y_rechazo_revision_falsa(self):
        args = ("--commit-base-canonico", self.commits_base[self.c],
                "--commit-base-espejo", self.commits_base[self.e])
        self.assertEqual(self.actualizar(*args, "--forzar")[0], 0)
        self.assertEqual(self.actualizar("--commit-base-canonico", "HEAD", "--forzar")[0], 2)

    def test_no_acepta_commit_huerfano_como_historia_confirmada_de_base(self):
        arbol = self.git(self.c, "rev-parse", "HEAD^{tree}").decode().strip()
        huerfano = self.git(self.c, "commit-tree", arbol, "-m", "huérfano sintético, no procedencia real").decode().strip()
        self.assertEqual(self.actualizar("--commit-base-canonico", huerfano, "--forzar")[0], 2)
        self.assertFalse(self.salida.exists())

    def test_error_git_y_carreras_no_dejan_escritura_parcial(self):
        self.salida.write_text("candidata anterior", encoding="utf-8")
        antes = self.salida.read_bytes()
        with mock.patch.object(vcc, "_git_acotado", side_effect=vcc.ErrorLectura("fallo simulado")):
            self.assertEqual(self.actualizar("--forzar")[0], 2)
        self.assertEqual(self.salida.read_bytes(), antes)
        capturar = vcc._capturar_acotado
        llamadas = 0
        def carrera(repo, rutas):
            nonlocal llamadas
            llamadas += 1
            if llamadas == 3:
                escribir(self.e, self.REL, "cambio concurrente\n")
            return capturar(repo, rutas)
        with mock.patch.object(vcc, "_capturar_acotado", carrera):
            self.assertEqual(self.actualizar("--forzar")[0], 2)
        self.assertEqual(self.salida.read_bytes(), antes)

    def test_base_concurrente_y_head_concurrente_bloquean(self):
        construir = vcc.construir_actualizacion_acotada
        for objetivo in ("base", "head"):
            original = self.archivo_base.read_bytes()
            def carrera(*args, **kwargs):
                nuevo = construir(*args, **kwargs)
                if objetivo == "base":
                    self.archivo_base.write_bytes(original + b" ")
                else:
                    self.git(self.c, "commit", "--allow-empty", "-qm", "HEAD concurrente de juguete")
                return nuevo
            with self.subTest(objetivo=objetivo), mock.patch.object(vcc, "construir_actualizacion_acotada", carrera):
                self.assertEqual(self.actualizar("--forzar")[0], 2)
                self.assertFalse(self.salida.exists())
            self.archivo_base.write_bytes(original)

    def test_valida_procedencia_y_rechaza_coherencia_global_falsa(self):
        self.assertEqual(self.actualizar("--forzar")[0], 0)
        man = json.loads(self.salida.read_bytes())
        vcc.validar_manifiesto(man)
        for clave, valor in (("verificacion_global", "coherente"), ("fecha_utc", "ayer"), ("seleccion", []),
                             ("cambios", []), ("base", {}), ("fuentes", {}), ("actualizador", {})):
            variante = json.loads(json.dumps(man))
            variante["actualizaciones_acotadas"][0][clave] = valor
            with self.subTest(clave=clave), self.assertRaises(vcc.ManifiestoInvalido):
                vcc.validar_manifiesto(variante)

    def test_preserva_adaptados_excepcion_versiones_y_metadatos(self):
        man = json.loads(self.archivo_base.read_bytes())
        rel = "others_scripts/adaptado.py"
        lados = {}
        for repo, texto in ((self.c, "canónico\n"), (self.e, "espejo\n")):
            escribir(repo, rel, texto)
            lados[repo] = hashlib.sha256((repo / rel).read_bytes()).hexdigest()
        grupo(man, "adaptados")["archivos"][rel] = {
            "motivo": "diferencia sintética histórica", "plan": "conservar pendiente",
            "sha256_canonico": lados[self.c], "sha256_espejo": lados[self.e]}
        man["hash_codigo"]["excepcion"] = {"vigente": True, "motivo": "historia", "plan": "no refrescar"}
        man["versiones_modelo"] = [{"etiqueta": "histórica sintética"}]
        self.guardar_manifiesto(man)
        self.archivo_base.write_bytes((self.c / RUTA).read_bytes())
        for repo in (self.c, self.e):
            self.confirmar(repo)
        escribir(self.e, rel, "divergencia externa posterior\n")
        self.assertEqual(self.actualizar("--forzar")[0], 0)
        nuevo = json.loads(self.salida.read_bytes())
        for clave in ("hash_codigo", "versiones_modelo", "canonico", "generador", "generado", "propios"):
            self.assertEqual(nuevo[clave], man[clave])
        self.assertEqual(grupo(nuevo, "adaptados"), grupo(man, "adaptados"))
        self.guardar_manifiesto(nuevo)
        codigo, out, err = self.correr()
        self.assertEqual(codigo, 1, out + err)
        self.assertIn(rel + ": el espejo cambió", out)

    def test_reemplazo_final_revalida_y_elimina_temporal_si_hay_carrera(self):
        escribir_atomico = vcc._escribir_atomico
        def carrera(ruta, texto, antes_reemplazar=None, crear_exclusivo=False):
            self.archivo_base.write_bytes(self.archivo_base.read_bytes() + b" ")
            escribir_atomico(ruta, texto, antes_reemplazar=antes_reemplazar, crear_exclusivo=crear_exclusivo)
        with mock.patch.object(vcc, "_escribir_atomico", carrera):
            self.assertEqual(self.actualizar("--forzar")[0], 2)
        self.assertFalse(self.salida.exists())
        self.assertEqual(list(self.base.glob(".candidata.json.*.tmp")), [])

    def test_error_de_creacion_atomica_no_publica_y_limpia_temporal(self):
        with mock.patch.object(vcc.os, "link", side_effect=OSError("fallo simulado")):
            self.assertEqual(self.actualizar("--forzar")[0], 2)
        self.assertFalse(self.salida.exists())
        self.assertEqual(list(self.base.glob(".candidata.json.*.tmp")), [])

    def test_candidata_concurrente_no_se_sobrescribe(self):
        construir = vcc.construir_actualizacion_acotada
        def carrera(*args, **kwargs):
            nuevo = construir(*args, **kwargs)
            self.salida.write_bytes(b"trabajo concurrente")
            return nuevo
        with mock.patch.object(vcc, "construir_actualizacion_acotada", carrera):
            self.assertEqual(self.actualizar("--forzar")[0], 2)
        self.assertEqual(self.salida.read_bytes(), b"trabajo concurrente")

    def test_rechaza_candidata_invalida_incluso_forzada_y_no_escribe_si_no_cambia(self):
        self.salida.write_bytes(b"candidata invalida")
        self.assertEqual(self.actualizar()[0], 2)
        self.assertEqual(self.salida.read_bytes(), b"candidata invalida")
        self.assertEqual(self.actualizar("--forzar")[0], 2)
        self.assertEqual(self.salida.read_bytes(), b"candidata invalida")
        self.salida.unlink()
        for repo in (self.c, self.e):
            escribir(repo, RUTA, self.archivo_base.read_text(encoding="utf-8"))
            escribir(repo, self.REL, "print('a')\n")
            self.confirmar(repo)
        codigo, out, err = self.actualizar("--forzar")
        self.assertEqual(codigo, 0, out + err)
        self.assertIn("Sin cambios de huellas", out)
        self.assertFalse(self.salida.exists())

    def test_no_sigue_enlace_en_padre_de_candidata_ni_abre_env(self):
        destino = self.base / "destino"
        destino.mkdir()
        enlace = self.base / "enlace"
        os.symlink(destino, enlace)
        self.assertEqual(self.actualizar("--salida", str(enlace / "candidata.json"), "--forzar")[0], 2)
        with mock.patch.object(vcc, "_abrir_lectura", side_effect=AssertionError("no debe abrir .env")):
            self.assertEqual(self.actualizar("--base", str(self.base / ".env"), "--forzar")[0], 2)

    def test_indice_concurrente_bloquea_aunque_bytes_de_trabajo_sean_iguales(self):
        construir = vcc.construir_actualizacion_acotada
        def carrera(*args, **kwargs):
            nuevo = construir(*args, **kwargs)
            original = (self.e / self.REL).read_bytes()
            escribir(self.e, self.REL, "sólo en índice\n")
            self.git(self.e, "add", "--", self.REL)
            (self.e / self.REL).write_bytes(original)
            return nuevo
        with mock.patch.object(vcc, "construir_actualizacion_acotada", carrera):
            self.assertEqual(self.actualizar("--forzar")[0], 2)
        self.assertFalse(self.salida.exists())

    def test_salida_rechaza_alias_casefold_de_base_y_ambos_repositorios(self):
        protegidas = [self.archivo_base, self.c / RUTA, self.e / RUTA, self.c / self.REL, self.e / self.REL]
        antes = {p: p.read_bytes() for p in protegidas}
        salidas = [self.archivo_base.with_name(self.archivo_base.name.upper()),
                   self.c / "config/COMPONENTES_COMPARTIDOS.JSON", self.e / "config/COMPONENTES_COMPARTIDOS.JSON",
                   self.c / self.REL, self.e / self.REL, self.c / "candidata_externa.json",
                   self.c.with_name(self.c.name.upper()) / "CONFIG/COMPONENTES_COMPARTIDOS.JSON",
                   self.e.with_name(self.e.name.upper()) / "CANDIDATA.JSON"]
        for salida in salidas:
            with self.subTest(salida=salida):
                self.assertEqual(self.actualizar("--salida", str(salida), "--forzar")[0], 2)
                self.assertEqual({p: p.read_bytes() for p in protegidas}, antes)
        self.assertFalse((self.c / "candidata_externa.json").exists())

    def test_salida_hardlink_de_base_activos_o_fuentes_no_se_abre_ni_escribe(self):
        abrir = vcc._abrir_lectura
        def espia(p):
            self.assertNotEqual(Path(p), self.salida)
            return abrir(p)
        for protegida in (self.archivo_base, self.c / RUTA, self.e / RUTA, self.c / self.REL, self.e / self.REL):
            with self.subTest(protegida=protegida):
                antes = protegida.read_bytes()
                os.link(protegida, self.salida)
                with mock.patch.object(vcc, "_abrir_lectura", espia):
                    self.assertEqual(self.actualizar("--forzar")[0], 2)
                self.assertEqual(protegida.read_bytes(), antes)
                self.salida.unlink()

    def test_solo_acepta_candidata_existente_identica_de_la_misma_operacion(self):
        self.assertEqual(self.actualizar("--forzar")[0], 0)
        antes = self.salida.read_bytes()
        self.assertEqual(self.actualizar("--actualizar-ruta", "scripts_superficie/s.py", "--forzar")[0], 2)
        self.assertEqual(self.salida.read_bytes(), antes)
        man = json.loads(antes)
        man["descripcion"] += " cambio ajeno"
        self.salida.write_text(json.dumps(man), encoding="utf-8")
        cambiado = self.salida.read_bytes()
        self.assertEqual(self.actualizar("--forzar")[0], 2)
        self.assertEqual(self.salida.read_bytes(), cambiado)

    def test_creacion_exclusiva_no_sobrescribe_si_archivo_aparece_al_publicar(self):
        enlazar = os.link
        def carrera(origen, destino, **kwargs):
            self.salida.write_bytes(b"trabajo tardio ajeno")
            return enlazar(origen, destino, **kwargs)
        with mock.patch.object(vcc.os, "link", carrera):
            self.assertEqual(self.actualizar("--forzar")[0], 2)
        self.assertEqual(self.salida.read_bytes(), b"trabajo tardio ajeno")
        self.assertEqual(list(self.base.glob(".candidata.json.*.tmp")), [])

    def test_revalida_identidad_de_fuente_justo_antes_de_publicar(self):
        atomico = vcc._escribir_atomico
        original = (self.c / self.REL).read_bytes()
        def carrera(ruta, texto, **kwargs):
            os.link(self.c / self.REL, ruta)
            return atomico(ruta, texto, **kwargs)
        with mock.patch.object(vcc, "_escribir_atomico", carrera):
            self.assertEqual(self.actualizar("--forzar")[0], 2)
        self.assertEqual((self.c / self.REL).read_bytes(), original)
        self.assertEqual(self.salida.read_bytes(), original)
        self.assertEqual(list(self.base.glob(".candidata.json.*.tmp")), [])

    def test_refs_replace_de_blob_no_acreditan_bytes_de_sustituto(self):
        texto = b"contenido sustituto, nunca fuente real\n"
        sustituto = self.base / "sustituto.py"
        sustituto.write_bytes(texto)
        for repo in (self.c, self.e):
            blob = self.git(repo, "rev-parse", "HEAD:" + self.REL).decode().strip()
            otro = self.git(repo, "hash-object", "-w", str(sustituto)).decode().strip()
            self.git(repo, "replace", blob, otro)
            (repo / self.REL).write_bytes(texto)
            self.assertEqual(self.git(repo, "show", "HEAD:" + self.REL), texto)
            self.assertNotEqual(vcc._git_acotado(repo, "show", "HEAD:" + self.REL), texto)
        self.assertEqual(self.actualizar("--forzar")[0], 2)
        self.assertFalse(self.salida.exists())

    def test_refs_replace_de_head_acreditan_solo_arbol_y_bytes_reales(self):
        originales = {}
        for repo in (self.c, self.e):
            head = self.git(repo, "rev-parse", "HEAD").decode().strip()
            padre = self.git(repo, "rev-parse", "HEAD^").decode().strip()
            originales[repo] = (head, (repo / self.REL).read_bytes())
            escribir(repo, self.REL, "arbol de sustitucion\n")
            self.git(repo, "add", "--", self.REL)
            arbol = self.git(repo, "write-tree").decode().strip()
            sustituto = self.git(repo, "commit-tree", arbol, "-p", padre, "-m", "sustitución sintética").decode().strip()
            self.git(repo, "restore", "--source=HEAD", "--staged", "--worktree", "--", self.REL)
            self.git(repo, "replace", head, sustituto)
            self.assertNotEqual(self.git(repo, "show", "HEAD:" + self.REL), originales[repo][1])
            self.assertEqual(vcc._git_acotado(repo, "show", "HEAD:" + self.REL), originales[repo][1])
        codigo, out, err = self.actualizar("--forzar")
        self.assertEqual(codigo, 0, out + err)
        registro = json.loads(self.salida.read_bytes())["actualizaciones_acotadas"][0]
        for lado, repo in (("canonico", self.c), ("espejo", self.e)):
            self.assertEqual(registro["fuentes"][lado]["commit"], originales[repo][0])
        self.assertEqual(registro["seleccion"][0]["sha256"], hashlib.sha256(originales[self.c][1]).hexdigest())

    def test_info_grafts_no_convierte_base_huerfana_en_ancestro_real(self):
        arbol = self.git(self.c, "rev-parse", "HEAD^{tree}").decode().strip()
        huerfano = self.git(self.c, "commit-tree", arbol, "-m", "base huérfana de juguete").decode().strip()
        head = self.git(self.c, "rev-parse", "HEAD").decode().strip()
        escribir(self.c, ".git/info/grafts", head + " " + huerfano + "\n")
        self.git(self.c, "merge-base", "--is-ancestor", huerfano, head)  # Demuestra la historia injertada.
        self.assertEqual(self.actualizar("--commit-base-canonico", huerfano, "--forzar")[0], 2)
        self.assertFalse(self.salida.exists())

    def test_cli_acotada_exige_base_salida_y_no_registro_global(self):
        for args in (("--actualizar-ruta", self.REL), ("--base", str(self.archivo_base)),
                     ("--actualizar-ruta", self.REL, "--base", str(self.archivo_base), "--salida", str(self.salida),
                      "--registrar", str(self.base / "registro.jsonl"))):
            self.assertEqual(self.correr(*args)[0], 2)

    def test_integracion_r22_con_funciones_reales_y_rutas_de_juguete(self):
        # Extraer sólo funciones de guardas: no importar módulos científicos ni ejecutar su nivel global.
        import ast
        import types
        fuente = CARPETA_SCRIPTS.parent / "scripts_modelo_1km/v2/red_ampliada_v2.py"
        arbol = ast.parse(fuente.read_text(encoding="utf-8"))
        nombres = {"estado_git", "par_de_repositorios", "verificar_espejo", "verificar_componentes",
                   "exigir_traduccion_confirmada"}
        nodos = [n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name in nombres]
        self.assertEqual({n.name for n in nodos}, nombres)
        espacio = {"Path": Path, "json": json, "sha256_archivo": lambda p: hashlib.sha256(p.read_bytes()).hexdigest(),
                   "ARCHIVOS_TRADUCCION": (self.REL, RUTA), "MANIFIESTO_COMPONENTES": RUTA,
                   "ARCHIVOS_DEL_ESPEJO": {}, "NOMBRE_CANONICO": self.c.name, "NOMBRE_ESPEJO": self.e.name}
        exec(compile(ast.Module(body=nodos, type_ignores=[]), str(fuente), "exec"), espacio)
        def guarda(desde):
            return espacio["exigir_traduccion_confirmada"](types.SimpleNamespace(repo=desde),
                                                          cfg={"red_de_monitores": {}}, ratificacion=False)
        with mock.patch.dict(sys.modules, {"_rutas_v2": types.ModuleType("_rutas_v2")}):
            with self.assertRaises(SystemExit):
                guarda(self.c)  # base confirmada, huella vieja
            self.assertEqual(self.actualizar("--forzar")[0], 0)
            for repo in (self.c, self.e):
                escribir(repo, RUTA, self.salida.read_text(encoding="utf-8"))
            with self.assertRaises(SystemExit):
                guarda(self.e)  # manifiestos aún sin confirmar
            for repo in (self.c, self.e):
                self.confirmar(repo)
            self.assertEqual(set(guarda(self.c)), {self.REL, RUTA})
            self.assertEqual(set(guarda(self.e)), {self.REL, RUTA})
            escribir(self.e, self.REL, "diferente\n")
            with self.assertRaises(SystemExit):
                guarda(self.c)


if __name__ == "__main__":
    unittest.main()
