Reemplazos exactos al código y a las pruebas selladas de la v2. Cada sección da la huella del archivo de origen y la del resultado; cada reemplazo, el texto actual (aparece una sola vez) y el nuevo. Se aplican en orden, sobre los archivos con la huella de origen; nada aquí está aplicado.

## `scripts_modelo_1km/v2/_rutas_v2.py`

- **Origen:** sha256 `eb8a92d233d6f9f07fefd02ed7b25950d5f768771d10e356cb545ccfa86e3103`.
- **Resultado:** sha256 `b18e66eff345185d7938886c3e5354f25df0445853bb97353ccd5f2caec17517`.
- **Motivo:** R11 y R13: la v2 lee el panel red 2 y el manifiesto de pliegues de la red 2 (única fuente) de la raíz v2; el derivado SINCA v1 queda entre las raíces de sólo lectura; los dos manifiestos de pliegues comparten el candado «pliegues».

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
    def nunca_escribibles(self) -> tuple[Path, ...]:
        """Raíces de sólo lectura (defensa en profundidad, con la comparación amplia)."""
        return (self.raiz_v1, self.datos, _resolver(VOLUMEN_DATOS))
```

Texto nuevo:

```python
    def nunca_escribibles(self) -> tuple[Path, ...]:
        """Raíces de sólo lectura (defensa en profundidad, con la comparación amplia), con el derivado SINCA v1
        (Enmienda 2, §3: la red 2 escribe su derivado en ``SINCA/v1_red2``)."""
        return (self.raiz_v1, self.datos, _resolver(VOLUMEN_DATOS),
                _resolver(self.datos.parent / "derived" / "modelado" / "SINCA" / "v1"))
```

### Reemplazo 2

Texto actual (aparece una sola vez):

```python
    def panel(self, pol: str) -> Path:
        return self.raiz_v1 / "paneles" / f"panel_{pol}.parquet"

```

Texto nuevo:

```python
    def panel(self, pol: str) -> Path:
        """Panel de la red ampliada, en la raíz v2 (Enmienda 2, bloque de la red ampliada, R11): lo arma
        ``panel_red2_v2``. Los paneles v1 (``panel_v1``) quedan intactos y la v2 ya no los lee."""
        return self.raiz_v2 / "paneles" / f"panel_{pol}_red2.parquet"

    def panel_v1(self, pol: str) -> Path:
        """Panel v1: referencia histórica congelada (R12); la v2 no lo lee desde la Enmienda 2."""
        return self.raiz_v1 / "paneles" / f"panel_{pol}.parquet"

```

### Reemplazo 3

Texto actual (aparece una sola vez):

```python
    def manifiesto_pliegues(self) -> Path:
        return self.raiz_v2 / "pliegues_v2.json"

```

Texto nuevo:

```python
    def manifiesto_pliegues(self) -> Path:
        """Manifiesto de pliegues vigente. Desde la Enmienda 2 (bloque de la red ampliada, R13) es el de la red 2,
        ``pliegues_v2_red2.json``: lo fija ``pliegues_red2_v2`` y es la única fuente de pliegues, pesos, E2 y bloque
        más influyente. El de la red original queda intacto como ``pliegues_v2_reemplazado_<marca>.json``."""
        return self.raiz_v2 / "pliegues_v2_red2.json"

```

### Reemplazo 4

Texto actual (aparece una sola vez):

```python
    ("raiz_v2", _regla(r"pliegues_v2(?:_reemplazado_[^/]+)?\.json"), "pliegues"),
```

Texto nuevo:

```python
    ("raiz_v2", _regla(r"pliegues_v2(?:_red2)?(?:_reemplazado_[^/]+)?\.json"), "pliegues"),
```

### Reemplazo 5

Texto actual (aparece una sola vez):

```python
        return {"raiz": None, "ruta": r.name}
```

Texto nuevo:

```python
        return {"raiz": None, "ruta": r.name}


class RutasRedOriginal(RutasV2):
    """Rutas de la red original, las de antes de la Enmienda 2: panel v1, ``calidad_<pol>.parquet`` y
    ``pliegues_v2.json``. Sirven para reproducir la bandera y los pliegues de la red original (``calidad_v2`` y
    ``pliegues_v2`` con la configuración sin el nodo ``red_de_monitores``) y a sus pruebas; la v2 usa ``RutasV2``."""

    def panel(self, pol: str) -> Path:
        return self.panel_v1(pol)

    manifiesto_pliegues = property(lambda self: self.raiz_v2 / "pliegues_v2.json",
                                   doc="Manifiesto de pliegues de la red original.")
```

## `scripts_modelo_1km/v2/calidad_v2.py`

- **Origen:** sha256 `5f34bf2d3e0f6a91f0d5284c00805b92cb55dcff1e9e3f258f910bdb385a46d7`.
- **Resultado:** sha256 `87bc4818dfba96ff544790c64274e86e019ab6a5197e68e670807fe9d33dd0e4`.
- **Motivo:** R5 y R11 (y la segunda revisión, menor 8): cargar_bandera compara la bandera con el calidad_sha256 que declara el json del panel, obligatorio con el panel de la red 2. La bandera de la red 2 la escribe panel_red2_v2 junto al panel, alineada 1 a 1 y con las mismas columnas; los lectores (correr_v2, piloto_v2) la leen por ruta_calidad. Este programa reproduce la bandera de la red original y se detiene bajo el contrato con la red ampliada, también sin escribir (el mensaje ya no sugiere --no-escribir, que también terminaba en SystemExit).

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
    r = r or rutas_v2()
    df = pd.read_parquet(ruta_calidad(r, pol), columns=COLUMNAS)
```

Texto nuevo:

```python
    r = r or rutas_v2()
    # Enmienda 2: con el panel de la red 2 la bandera tiene que ser la que declara su json (calidad_sha256)
    declarado = (leer_json(r.panel_meta(pol)) or {}).get("calidad_sha256")
    if declarado is None and r.panel(pol).name.endswith("_red2.parquet"):
        raise SystemExit(f"{pol}: el json del panel de la red 2 no declara calidad_sha256")
    if declarado is not None and sha256_archivo(ruta_calidad(r, pol)) != declarado:
        raise SystemExit(f"{ruta_calidad(r, pol).name} no es la bandera que declara el json del panel (calidad_sha256)")
    df = pd.read_parquet(ruta_calidad(r, pol), columns=COLUMNAS)
```

### Reemplazo 2

Texto actual (aparece una sola vez):

```python
def ruta_calidad(r: RutasV2, pol: str) -> Path:
    return r.raiz_v2 / "paneles" / f"calidad_{pol}.parquet"
```

Texto nuevo:

```python
def ruta_calidad(r: RutasV2, pol: str) -> Path:
    """Bandera del panel en uso, en la raíz v2: ``calidad_<pol>_red2.parquet`` para el panel de la red ampliada
    (Enmienda 2, R5 y R11: la escribe ``panel_red2_v2`` junto al panel, alineada 1 a 1 y con estas mismas columnas) y
    ``calidad_<pol>.parquet`` para el de la red original (``RutasRedOriginal``), que queda como estaba."""
    return r.raiz_v2 / "paneles" / ("calidad_" + r.panel(pol).name.removeprefix("panel_"))
```

### Reemplazo 3

Texto actual (aparece una sola vez):

```python
    hilos_cfg = int(cfg["operacion"]["hilos_maximos"])
    fijar_hilos(hilos_cfg)
    raiz_der = Path(raiz_der).resolve() if raiz_der is not None else raiz_derivados(r)
```

Texto nuevo:

```python
    if "red_de_monitores" in cfg:
        raise SystemExit("Con la Enmienda 2 (red ampliada, R5 y R11) la bandera de calidad de la red 2 la escribe "
                         "panel_red2_v2 al armar el panel (paneles/calidad_<pol>_red2.parquet, con su sha256 en el "
                         "json del panel). Este programa reproduce la bandera de la red original y no corre bajo el "
                         "contrato con la red ampliada, tampoco sin escribir.")
    hilos_cfg = int(cfg["operacion"]["hilos_maximos"])
    fijar_hilos(hilos_cfg)
    raiz_der = Path(raiz_der).resolve() if raiz_der is not None else raiz_derivados(r)
```

## `scripts_modelo_1km/v2/pliegues_v2.py`

- **Origen:** sha256 `05cac03f33492a102deea2abb6f76f3f2dfa3b2430350a3f25a93e049ca29615`.
- **Resultado:** sha256 `26207bf4542c987a751493ff99e4590c524a204cd5f88d3e3ed3674150a535e3`.
- **Motivo:** R13 a R16 (revisión M1): una sola fuente de pliegues y pesos para la red ampliada, pliegues_red2_v2.py → pliegues_v2_red2.json. Este programa calcula los de la red original y se detiene bajo el contrato con la red ampliada (también con --no-escribir y --refijar), así no hay un segundo camino con otra huella. anotar_bitacora sigue igual: anota los recortes del piloto en el manifiesto vigente.

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
    if reemplazar and refijar:
        raise SystemExit("--reemplazar y --refijar no van juntos: --refijar no cambia los pliegues")
```

Texto nuevo:

```python
    if "red_de_monitores" in cfg:
        raise SystemExit("Con la Enmienda 2 (red ampliada, R13 a R16) los pliegues, los pesos, la E2 y el bloque más "
                         "influyente los fija pliegues_red2_v2.py en pliegues_v2_red2.json, la única fuente; este "
                         "programa calcula los de la red original y no corre bajo el contrato con la red ampliada")
    if reemplazar and refijar:
        raise SystemExit("--reemplazar y --refijar no van juntos: --refijar no cambia los pliegues")
```

## `scripts_modelo_1km/v2/validar_vecindario_v2.py`

- **Origen:** sha256 `2465a31f502900975222287088eb340d586660ae7d87b7faae14c20e1d8c4790`.
- **Resultado:** sha256 `0046df3dd4d166f5c86f70be8b729f132c2ff368e16b613aefe73132795a475a`.
- **Motivo:** R11 y R12: con la red ampliada, la reproducción (a2) en float64 lee las observaciones que escribió panel_red2_v2 (por su sha256) en lugar de reconstruir las de la v1; antes se detenía siempre, porque el json del panel red 2 no declara la configuración v1. Su resultado va en a2_fuente_red2_float64, no en a2_fuente_v1_float64.

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
def alinear_con_panel(vec: Vecindario, o: pd.DataFrame, obs32: np.ndarray) -> tuple[np.ndarray, dict]:
```

Texto nuevo:

```python
def observaciones_red2_float64(pol: str, r: RutasV2, meta: dict) -> tuple[pd.DataFrame, dict]:
    """Con la red ampliada (Enmienda 2, R11 y R12), las observaciones float64 del panel red 2 son las que escribió
    ``panel_red2_v2`` al armarlo (``paneles/observaciones_<pol>_red2.parquet``), leídas por su sha256; no se reconstruye
    la v1. Antes comprueba que el json del panel declara el esquema, el período y las rachas del armado."""
    import panel_red2_v2 as pr

    esperado = {"schema": pr.SCHEMA, "desde": pr.DESDE, "hasta": pr.HASTA, "qc_racha_minima": pr.QC_RACHA}
    dif = {k: meta.get(k) for k, v in esperado.items() if meta.get(k) != v}
    if dif:
        raise SystemExit(f"{pol}: el panel de la red 2 declara otra configuración que la de su armado: {dif}")
    o, info = pr.observaciones_float64(pol, r, meta)
    info["qc_nota"] = ("Red ampliada (Enmienda 2): observaciones float64 del armado, verificadas por su sha256; los "
                       "conteos del QC son los del json del panel (horas antes de las rachas y horas en racha).")
    return o, info


def alinear_con_panel(vec: Vecindario, o: pd.DataFrame, obs32: np.ndarray) -> tuple[np.ndarray, dict]:
```

### Reemplazo 2

Texto actual (aparece una sola vez):

```python
    if fuentes_v1:
        esperado = {"desde": DESDE, "hasta": HASTA, "qc_racha_minima": QC_RACHA, "reloj_sinca": "UTC-4 fijo; etiqueta=fin",
                    "redes": ["sinca", "snifa"]}
        dif = {k: meta.get(k) for k, v in esperado.items() if meta.get(k) != v}
        if dif:
            raise SystemExit(f"{pol}: el panel v1 declara otra configuración que la replicada: {dif}")
        t1 = time.perf_counter()
        o, info = observaciones_v1_float64(pol, r)
        qc = meta.get("qc_descriptivo", {})
        info["qc_del_panel_frente_a_la_reconstruccion"] = {k: {"reconstruccion": info[k], "panel": qc.get(k)}
                                                           for k in ("filas_validas", "filas_en_racha", "estaciones_con_racha")}
        info["qc_nota"] = ("El QC descriptivo del panel (qc_descriptivo) cuenta sólo SINCA; la reconstrucción suma la red "
                           "SNIFA en NO2 (como el panel y el vecindario de la v1). En PM2,5 deben coincidir; en NO2 la "
                           "reconstrucción tiene además las filas SNIFA (el mapa v1 da 39.071 filas en racha con SNIFA).")
        obs64, alin = alinear_con_panel(vec, o, panel["obs"].to_numpy())
```

Texto nuevo:

```python
    red2 = "red_de_monitores" in cfg                     # Enmienda 2: el panel es el de la red ampliada
    if fuentes_v1 and red2:
        t1 = time.perf_counter()
        o, info = observaciones_red2_float64(pol, r, meta)
    elif fuentes_v1:
        esperado = {"desde": DESDE, "hasta": HASTA, "qc_racha_minima": QC_RACHA, "reloj_sinca": "UTC-4 fijo; etiqueta=fin",
                    "redes": ["sinca", "snifa"]}
        dif = {k: meta.get(k) for k, v in esperado.items() if meta.get(k) != v}
        if dif:
            raise SystemExit(f"{pol}: el panel v1 declara otra configuración que la replicada: {dif}")
        t1 = time.perf_counter()
        o, info = observaciones_v1_float64(pol, r)
        qc = meta.get("qc_descriptivo", {})
        info["qc_del_panel_frente_a_la_reconstruccion"] = {k: {"reconstruccion": info[k], "panel": qc.get(k)}
                                                           for k in ("filas_validas", "filas_en_racha", "estaciones_con_racha")}
        info["qc_nota"] = ("El QC descriptivo del panel (qc_descriptivo) cuenta sólo SINCA; la reconstrucción suma la red "
                           "SNIFA en NO2 (como el panel y el vecindario de la v1). En PM2,5 deben coincidir; en NO2 la "
                           "reconstrucción tiene además las filas SNIFA (el mapa v1 da 39.071 filas en racha con SNIFA).")
    if fuentes_v1:
        obs64, alin = alinear_con_panel(vec, o, panel["obs"].to_numpy())
```

### Reemplazo 3

Texto actual (aparece una sola vez):

```python
        insumos_extra = {"catalogo_sinca": r.catalogo_sinca, "snifa": r.snifa,
                         **{f"grilla_{Path(nm).stem}": r.grilla_v1 / nm for nm in pv.INSUMOS_GRILLA}}
```

Texto nuevo:

```python
        insumos_extra = ({f"observaciones_{pol}_red2": r.raiz_v2 / "paneles" / f"observaciones_{pol}_red2.parquet"}
                         if red2 else
                         {"catalogo_sinca": r.catalogo_sinca, "snifa": r.snifa,
                          **{f"grilla_{Path(nm).stem}": r.grilla_v1 / nm for nm in pv.INSUMOS_GRILLA}})
```

### Reemplazo 4

Texto actual (aparece una sola vez):

```python
        res["a2_fuente_v1_float64"] = a2
```

Texto nuevo:

```python
        clave_a2 = "a2_fuente_red2_float64" if red2 else "a2_fuente_v1_float64"   # Enmienda 2: la del armado
        res[clave_a2] = a2
```

### Reemplazo 5

Texto actual (aparece una sola vez):

```python
        res["a2_fuente_v1_float64"]["reconstruccion"]["insumos_extra"] = sorted(insumos_extra)
```

Texto nuevo:

```python
        res[clave_a2]["reconstruccion"]["insumos_extra"] = sorted(insumos_extra)
```

### Reemplazo 6

Texto actual (aparece una sola vez):

```python
        if "a2_fuente_v1_float64" in res:
            a2 = res["a2_fuente_v1_float64"]
            v["a2_bit_a_bit"] = all(a2[c]["bit_a_bit"] == a2[c]["filas"] - a2[c]["nan"] and a2[c]["nan_iguales"] for c in VARIABLES)
```

Texto nuevo:

```python
        clave_a2 = next((k for k in ("a2_fuente_v1_float64", "a2_fuente_red2_float64") if k in res), None)
        if clave_a2 is not None:
            a2 = res[clave_a2]
            v["a2_bit_a_bit"] = all(a2[c]["bit_a_bit"] == a2[c]["filas"] - a2[c]["nan"] and a2[c]["nan_iguales"] for c in VARIABLES)
```

### Reemplazo 7

Texto actual (aparece una sola vez):

```python
        if "a2_fuente_v1_float64" in res:
            a2 = res["a2_fuente_v1_float64"]
            for c in VARIABLES:
```

Texto nuevo:

```python
        clave_a2 = next((k for k in ("a2_fuente_v1_float64", "a2_fuente_red2_float64") if k in res), None)
        if clave_a2 is not None:
            a2 = res[clave_a2]
            for c in VARIABLES:
```

## `scripts_modelo_1km/v2/vecindario_v2.py`

- **Origen:** sha256 `0121a6c49a2d84471f60114cbf3a4c4001642fb78a61f9b7b2241ae6fcdf6181`.
- **Resultado:** sha256 `08f0a5a3b8249ec5987b9416a145b2e04b426245d9b504d9c15fdcf1f9b0bb12`.
- **Motivo:** R11: el vecindario se arma sobre el panel en uso (el de la red 2); el mensaje ya no lo llama «panel v1».

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
            raise SystemExit(f"Falta el panel v1 {r.relativa(ruta)}")
```

Texto nuevo:

```python
            raise SystemExit(f"Falta el panel {r.relativa(ruta)} (desde la Enmienda 2, el de la red ampliada)")
```

## `scripts_modelo_1km/v2/correr_v2.py`

- **Origen:** sha256 `534e484b66ed9575f36a2ec5fc75052a9a2544656cf3e4a80077b90f96c69b07`.
- **Resultado:** sha256 `1423ef3f7a8d7bc35d8ee1802187de95129e46afe276241e29a0c7e486f6445d`.
- **Motivo:** R22, paso 4 (revisión M1): ningún ajuste (piloto de tiempos ni corrida) antes del anexo «Registro de la red v2»: Contexto.desde_disco, por donde pasan correr_v2 y piloto_v2, exige que el manifiesto de pliegues sea el registrado (con los recortes del piloto anotados después, si los hay). R10: la desagregación descriptiva por propietario entra como estrato de las métricas (Nivel.estratos, que metricas_v2 ya informa sin ponderar y que no entra en el §9), sin tocar metricas_v2. Con la red 2 la bandera de calidad es obligatoria (segunda revisión, menor 8), también con con_calidad=False, y la consola rechaza --sin-calidad (tercera revisión, menor 27). decidir exige el registro del anexo y que el bloque más influyente de cada evidencia sea el de la configuración (R16; tercera revisión, menor 26). R15 (ronda 4 de la traducción, menor 14, corregido en la ronda 5, mayor 1): «la evaluabilidad de E2 se calcula sobre el panel de R11, con los mismos umbrales, antes de cualquier ajuste», así que rige la registrada en pliegues_v2_red2.json, que devuelve exigir_registro: decidir entrega a decision_v2 (condición 3), por protocolo, una copia de la evidencia con el «evaluable» registrado en vez del que la evidencia calculó sobre los pares de la decisión (pliegues_red2_v2.evaluabilidad_e2_que_rige), y deja el de la decisión sólo como registro en decision.json, con la huella de la evidencia consolidada (reemplazo 7); si la registrada es evaluable y la evidencia no tiene pares E2, se detiene como defecto de la corrida. No hay ninguna parada que deje la elección al autor.

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
            if ruta_qc.exists():
                calidad = calidad_v2.cargar_bandera(pol, panel[["estacion", "ts_utc"]], r)["qc"].to_numpy(dtype=object)
                insumos[f"calidad_{pol}"] = ruta_qc
            else:
```

Texto nuevo:

```python
            if ruta_qc.exists():
                calidad = calidad_v2.cargar_bandera(pol, panel[["estacion", "ts_utc"]], r)["qc"].to_numpy(dtype=object)
                insumos[f"calidad_{pol}"] = ruta_qc
            elif "red_de_monitores" in cfg:                   # Enmienda 2: la bandera es obligatoria
                raise SystemExit(f"{pol}: con la red ampliada la bandera de calidad es obligatoria "
                                 f"({r.relativa(ruta_qc)['ruta']}, la escribe panel_red2_v2)")
            else:
```

### Reemplazo 2

Texto actual (aparece una sola vez):

```python
def estratos_fila_a_fila(ctx: Contexto) -> tuple[dict, dict]:
    """Régimen de predictores fila a fila del contexto (``regimen_de_panel``) como estrato de las métricas."""
    if ctx.regimen_fila_a_fila is None:
        return {}, {"estado": "el panel no trae ninguna columna de las familias del régimen fila a fila"}
    cod, etiquetas, info = ctx.regimen_fila_a_fila
    return {"regimen_fila_a_fila": (np.asarray(cod, dtype="int64"), etiquetas)}, info
```

Texto nuevo:

```python
def estratos_fila_a_fila(ctx: Contexto) -> tuple[dict, dict]:
    """Régimen de predictores fila a fila del contexto (``regimen_de_panel``) como estrato de las métricas y, con la
    red ampliada (Enmienda 2, R10), el propietario de la estación de cada fila (descriptivo; no entra en el §9)."""
    if ctx.regimen_fila_a_fila is None:
        estratos, info = {}, {"estado": "el panel no trae ninguna columna de las familias del régimen fila a fila"}
    else:
        cod, etiquetas, info = ctx.regimen_fila_a_fila
        estratos = {"regimen_fila_a_fila": (np.asarray(cod, dtype="int64"), etiquetas)}
    if "red_de_monitores" in ctx.cfg:
        import panel_red2_v2
        cod, etiquetas, info_p = panel_red2_v2.estrato_propietario(ctx.rutas, ctx.pol, ctx.vec.estaciones, ctx.vec.js)
        estratos["propietario"] = (cod, etiquetas)
        info = {**info, "propietario": info_p}
    return estratos, info
```

### Reemplazo 3

Texto actual (aparece una sola vez):

```python
        man = leer_json(r.manifiesto_pliegues)
        if man is None:
            raise SystemExit(f"Falta el manifiesto de pliegues {r.relativa(r.manifiesto_pliegues)}")
        vec = Vecindario.desde_panel(pol, r, manifiesto=man, cfg=cfg, hilos=h)
```

Texto nuevo:

```python
        man = leer_json(r.manifiesto_pliegues)
        if man is None:
            raise SystemExit(f"Falta el manifiesto de pliegues {r.relativa(r.manifiesto_pliegues)}")
        if "red_de_monitores" in cfg:                     # Enmienda 2, R22 paso 4: el que registró el anexo
            import pliegues_red2_v2
            man = pliegues_red2_v2.exigir_registro(r, cfg, r.manifiesto_pliegues)
        vec = Vecindario.desde_panel(pol, r, manifiesto=man, cfg=cfg, hilos=h)
```

### Reemplazo 4

Texto actual (aparece una sola vez):

```python
        h = int(cfg["operacion"]["hilos_maximos"]) if hilos is None else int(hilos)
```

Texto nuevo:

```python
        h = int(cfg["operacion"]["hilos_maximos"]) if hilos is None else int(hilos)
        if "red_de_monitores" in cfg and not con_calidad:   # Enmienda 2: la bandera es obligatoria, sin excepción
            raise SystemExit(f"{pol}: con la red ampliada la bandera de calidad es obligatoria: no se corre sin "
                             f"calidad (--sin-calidad)")
```

### Reemplazo 5

Texto actual (aparece una sola vez):

```python
    regla = dc.regla_de_config(cfg)
    evidencias, insumos = {}, {}
    for prot in regla.protocolos:
        ruta = ruta_evidencia(r, etiqueta, pol, prot)
        ev = leer_json(ruta)
        if ev is None:
            raise Incompleto(f"{pol} {prot}: falta {NOMBRE_EVIDENCIA}; consolida antes el protocolo")
        evidencias[prot] = ev
```

Texto nuevo:

```python
    regla = dc.regla_de_config(cfg)
    e2_red2 = {}
    if "red_de_monitores" in cfg:                         # Enmienda 2, R22 paso 4 (y R16 y R17): el anexo
        import pliegues_red2_v2
        manifiesto_red2 = pliegues_red2_v2.exigir_registro(r, cfg)
    evidencias, insumos = {}, {}
    for prot in regla.protocolos:
        ruta = ruta_evidencia(r, etiqueta, pol, prot)
        ev = leer_json(ruta)
        if ev is None:
            raise Incompleto(f"{pol} {prot}: falta {NOMBRE_EVIDENCIA}; consolida antes el protocolo")
        if "red_de_monitores" in cfg and ev.get("bloque_mas_influyente") != regla.bloque_mas_influyente.get(prot):
            raise SystemExit(f"{pol} {prot}: la evidencia se consolidó con el bloque más influyente "
                             f"{ev.get('bloque_mas_influyente')!r} y la configuración dice "
                             f"{regla.bloque_mas_influyente.get(prot)!r} (R16): consolida de nuevo")
        if "red_de_monitores" in cfg:                     # R15: rige la E2 registrada antes del ajuste
            ev, e2_red2[prot] = pliegues_red2_v2.evaluabilidad_e2_que_rige(ev, manifiesto_red2, pol, prot)
        evidencias[prot] = ev
```

### Reemplazo 6

Texto actual (aparece una sola vez):

```python
    r = rutas_v2()
    cfg = cargar_config(r)
    recetas = mv.recetas_de(cfg, args.hilos)
```

Texto nuevo:

```python
    r = rutas_v2()
    cfg = cargar_config(r)
    if "red_de_monitores" in cfg and args.sin_calidad:   # Enmienda 2: la bandera es obligatoria con la red 2
        raise SystemExit("--sin-calidad no se admite con la red ampliada: la bandera de calidad es obligatoria "
                         "(Enmienda 2, segunda revisión, menor 8)")
    recetas = mv.recetas_de(cfg, args.hilos)
```

### Reemplazo 7

Texto actual (aparece una sola vez):

```python
    if forzado is not None:
        registro["replicas_bootstrap_forzadas"] = dict(forzado)
```

Texto nuevo:

```python
    if forzado is not None:
        registro["replicas_bootstrap_forzadas"] = dict(forzado)
    if e2_red2:                                           # Enmienda 2, R15: la E2 que rige y la de la decisión (registro)
        registro["evaluabilidad_E2_red2"] = e2_red2
```

## `scripts_modelo_1km/v2/piloto_v2.py`

- **Origen:** sha256 `60cfaba9e217b200db19fc68bb4d4cfe27e4d8f9ae5d951e88b6072a608d5336`.
- **Resultado:** sha256 `e7a90fb88e3743dba848978d62b1fff6f39b7a83f8f6340a74484be49901ad12`.
- **Motivo:** R18: si después de los cuatro recortes el plan sigue sobre unas 120 h, se corre igual y se registra; no hay quinto recorte. El texto anterior lo dejaba «para el autor (enmienda)». Con la red 2 la bandera de calidad es obligatoria también al estimar el plan (tercera revisión, menor 44): sin ella, el plan saldría sin las variantes de calidad que después exige correr_v2.

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
los cuatro se llega, el orden enmendado no prevé otro: se aplican los cuatro y el exceso queda para el autor
(enmienda). La decisión usa la estimación medida (conservadora) y el plan dice si alguna sensibilidad la
```

Texto nuevo:

```python
los cuatro se llega, se aplican los cuatro, se corre igual y queda en la bitácora: no hay quinto recorte
(Enmienda 2, R18). La decisión usa la estimación medida (conservadora) y el plan dice si alguna sensibilidad la
```

### Reemplazo 2

Texto actual (aparece una sola vez):

```python
    bitácora de cada paso. Si ni con todos se llega, se aplican todos y el exceso queda para el autor."""
```

Texto nuevo:

```python
    bitácora de cada paso. Si ni con todos se llega, se aplican todos y se corre igual: no hay quinto recorte
    (Enmienda 2, R18)."""
```

### Reemplazo 3

Texto actual (aparece una sola vez):

```python
            paso["accion"] = (f"supera el umbral aun con los {ultimo} recortes: el orden de la Enmienda 1 (punto 12) no "
                              f"prevé otro; se corre con los {ultimo} y el exceso queda para el autor (enmienda)")
```

Texto nuevo:

```python
            paso["accion"] = (f"supera el umbral aun con los {ultimo} recortes: se corre igual con los {ultimo} y "
                              f"queda registrado; no hay quinto recorte (Enmienda 2, R18)")
```

### Reemplazo 4

Texto actual (aparece una sola vez):

```python
        plan["pendiente_del_autor"] = (
            f"Con los {n} recortes del orden enmendado (Enmienda 1, punto 12) la estimación sigue en "
            f"{est['por_recorte'][str(n)]['horas']} h de máquina (umbral: unas {umbral:g} h). El orden no prevé otro "
            f"recorte: correr igual o reducir por enmienda fechada es decisión del autor. Los componentes que más "
            f"pesan están en estimacion['{n}']['componentes_horas'].")
```

Texto nuevo:

```python
        plan["sobre_el_umbral_tras_los_recortes"] = (
            f"Con los {n} recortes del orden enmendado (Enmienda 1, punto 12) la estimación sigue en "
            f"{est['por_recorte'][str(n)]['horas']} h de máquina (umbral: unas {umbral:g} h). Se corre igual y queda "
            f"registrado; no hay quinto recorte (Enmienda 2, R18). Los componentes que más pesan están en "
            f"estimacion['{n}']['componentes_horas'].")
```

### Reemplazo 5

Texto actual (aparece una sola vez):

```python
    contaminantes = tuple(contaminantes)
    recetas = mv.recetas_de(cfg, hilos)
```

Texto nuevo:

```python
    contaminantes = tuple(contaminantes)
    if "red_de_monitores" in cfg:                       # Enmienda 2: con la red 2 la bandera es obligatoria
        import calidad_v2
        sin_bandera = [pol for pol in contaminantes if not calidad_v2.ruta_calidad(r, pol).exists()]
        if sin_bandera:
            raise SystemExit(f"con la red ampliada la bandera de calidad es obligatoria y falta en {sin_bandera}: el "
                             f"plan no se estima sin sus variantes de calidad")
    recetas = mv.recetas_de(cfg, hilos)
```

## `scripts_modelo_1km/v2/factibilidad_v2.py`

- **Origen:** sha256 `2229bd95eed76c37ccb55d3d853280785dd2752131eb624aae9e5a67d00a764f`.
- **Resultado:** sha256 `a428cf1aa19ef70562715c3d208e3a7e76440cddeff9e29a33592d1d37b82f63`.
- **Motivo:** R19 y R17 (cuarta revisión, menor 9): la factibilidad no se vuelve a medir con la red 2 (R19: «la regla y su medición no cambian») y sus fechas quedan fijadas por el régimen 2019-2024 de la Enmienda 1. El anexo reemplaza criterio.valor por los tramos comunes calculados (R17) y deja los de la Enmienda 1 en criterio.valor_red_original (pliegues_red2_v2.con_el_anexo); sin el reemplazo 1, fechas_de_medicion (y la prueba sellada FechasTests.test_fechas_fijadas_por_calendario) se detendría con «la configuración no tiene el régimen de predictores 2019-2024» en cuanto ningún tramo calculado sea exactamente 2019-2024. Quinta revisión, menores 13 y 24: la lectura «no se vuelve a medir» no la hacía cumplir nada; con el reemplazo 2 del código sellado de _rutas_v2, filas_de_produccion leería el panel de la red 2, y publicar reescribiría factibilidad_produccion.json, que correr_v2.decidir lee. Los reemplazos 2 y 3 (exigir_sin_red_ampliada) detienen medir y publicar, y con ellos sus órdenes de consola, cuando la configuración trae red_de_monitores, antes de leer o escribir nada («R19, la medición no se revisa»).

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
def fechas_de_medicion(cfg: dict) -> dict[str, date]:
    """Las 3 fechas de la medición, fijadas por regla de calendario y sin mirar ningún dato: el día 15 del mes central
    de cada estación (enero, abril y julio) del año del día central del régimen 2019-2024 (2022)."""
    reg = {r["id"]: r for r in regimenes_de(cfg)}
```

Texto nuevo:

```python
def fechas_de_medicion(cfg: dict) -> dict[str, date]:
    """Las 3 fechas de la medición, fijadas por regla de calendario y sin mirar ningún dato: el día 15 del mes central
    de cada estación (enero, abril y julio) del año del día central del régimen 2019-2024 (2022) de la Enmienda 1.
    Con la red ampliada (Enmienda 2), el anexo reemplaza los tramos de ``criterio`` por los calculados (R17) y deja los
    de la Enmienda 1 en ``criterio.valor_red_original``: las fechas siguen saliendo de esos, porque la factibilidad no
    se revisa (R19) y los regímenes no alteran el §9."""
    crit = cfg["metricas"]["desagregaciones"]["regimen_de_predictores"]["criterio"]
    if "valor_red_original" in crit:
        reg = {str(r["id"]): {"id": str(r["id"]), "anios": [int(r["anios"][0]), int(r["anios"][1])]}
               for r in crit["valor_red_original"]}
    else:
        reg = {r["id"]: r for r in regimenes_de(cfg)}
```

### Reemplazo 2

Texto actual (aparece una sola vez):

```python
    temporal (modelos y matrices) al terminar, salvo ``conservar_temporal``."""
    fact = cfg["decision"]["factibilidad"]
```

Texto nuevo:

```python
    temporal (modelos y matrices) al terminar, salvo ``conservar_temporal``. Con la red ampliada (Enmienda 2) no mide:
    la medición no se revisa (R19, ``exigir_sin_red_ampliada``)."""
    exigir_sin_red_ampliada(cfg, "medir")
    fact = cfg["decision"]["factibilidad"]
```

### Reemplazo 3

Texto actual (aparece una sola vez):

```python
def publicar(r: RutasV2, cfg: dict) -> dict:
    """Escribe ``factibilidad_produccion.json`` (candado ``factibilidad``); el resumen del punto 11 se respalda."""
    with candado_escritura(CANDADO, r):
```

Texto nuevo:

```python
def exigir_sin_red_ampliada(cfg: dict, accion: str) -> None:
    """Enmienda 2, R19 («la regla y su medición no cambian»; lectura de la traducción: no se vuelve a medir con la red
    2): con el nodo ``red_de_monitores`` la medición de la factibilidad no se revisa. ``medir`` no vuelve a medir (con la
    red 2, ``filas_de_produccion`` leería el panel de la red 2) y ``publicar`` no rehace ``factibilidad_produccion.json``,
    que ``correr_v2.decidir`` lee tal como quedó (Complemento, punto 3). Se detiene antes de leer o escribir nada."""
    if "red_de_monitores" in cfg:
        raise SystemExit(f"R19, la medición no se revisa: con la red ampliada (red_de_monitores en la configuración) "
                         f"factibilidad_v2 no vuelve a {accion}; rige la medición del Complemento (punto 3)")


def publicar(r: RutasV2, cfg: dict) -> dict:
    """Escribe ``factibilidad_produccion.json`` (candado ``factibilidad``); el resumen del punto 11 se respalda. Con la
    red ampliada se detiene antes (R19, ``exigir_sin_red_ampliada``)."""
    exigir_sin_red_ampliada(cfg, "publicar")
    with candado_escritura(CANDADO, r):
```

## `scripts_modelo_1km/v2/tests/_sintetico_v2.py`

- **Origen:** sha256 `c9cd550f3fb9500c69accabab916ecad26dc1a41b5301c66575f2e9b96f1631e`.
- **Resultado:** sha256 `10e9faa5e5dec08101e326ca2064e7d0bf689feba42f23a047813de4e904c7dc`.
- **Motivo:** la configuración sintética describe las nueve estaciones de las pruebas, no la red ampliada: sin el nodo red_de_monitores, correr_v2 no exige el anexo y calidad_v2 y pliegues_v2 corren sobre la red de prueba. anexo_de_la_red (tercera revisión, mayor 7 y menor 30) da a las pruebas selladas que fijaban los valores de la Enmienda 1 los que rigen después del anexo: los tramos comunes de regimenes_red2.json y el bloque más influyente de pliegues_v2_red2.json, comprobados por las huellas del anexo.

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
                                  "xgboost": [500, n_comun, 2400, "todas"], "random_forest": [500, n_comun, 2400]}
    return cfg
```

Texto nuevo:

```python
                                  "xgboost": [500, n_comun, 2400, "todas"], "random_forest": [500, n_comun, 2400]}
    cfg.pop("red_de_monitores", None)              # la red de estas pruebas es la sintética (Enmienda 2, R2 a R22)
    return cfg


def anexo_de_la_red(cfg: dict) -> dict | None:
    """Enmienda 2, R16, R17 y R22 paso 4: si el anexo «Registro de la red v2» ya llenó
    ``red_de_monitores.registro_de_la_red``, lo que rige después de él: los tramos comunes de
    ``paneles/regimenes_red2.json`` y el bloque más influyente de ``pliegues_v2_red2.json`` (de la raíz v2,
    comprobados por las huellas del anexo). Sin el anexo, None: rigen los valores de la Enmienda 1."""
    import hashlib
    import unittest

    reg = (cfg.get("red_de_monitores") or {}).get("registro_de_la_red") or {}
    sha_reg = (reg.get("regimenes") or {}).get("sha256")
    if not sha_reg:
        return None
    raiz = rv.RutasV2.desde_entorno().raiz_v2
    ruta_reg, ruta_pl = raiz / "paneles" / "regimenes_red2.json", raiz / "pliegues_v2_red2.json"
    if not (ruta_reg.exists() and ruta_pl.exists()):
        raise unittest.SkipTest("el anexo está escrito, pero falta la raíz v2 con sus artefactos")
    if hashlib.sha256(ruta_reg.read_bytes()).hexdigest() != sha_reg:
        raise AssertionError("regimenes_red2.json no es el que registró el anexo")
    m = json.loads(ruta_pl.read_text(encoding="utf-8"))
    if m.get("huella_pliegues") != (reg.get("pliegues") or {}).get("huella_pliegues"):
        raise AssertionError("pliegues_v2_red2.json no es el que registró el anexo")
    return {"tramos": json.loads(ruta_reg.read_text(encoding="utf-8"))["comunes"]["tramos"],
            "bloque": {p: m["bloque_mas_influyente"][p]["grupo"] for p in ("LRO", "BLQ-75")}}
```

## `scripts_modelo_1km/v2/tests/test_rutas_v2.py`

- **Origen:** sha256 `968b5b51bec1150f3888301cbbcf46956fe4d658c0dd75b9cf7adaafa4bdbf15`.
- **Resultado:** sha256 `5ed83039f5393a7ab102682f8f7632d61fa365301a5fd485f3e24d5b68e98159`.
- **Motivo:** R11 y R13: el panel y el manifiesto de pliegues vigentes son los de la red 2; el panel v1 queda en panel_v1; el derivado SINCA v1 es de sólo lectura; los dos manifiestos comparten el candado.

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
        self.assertEqual(r.manifiesto_pliegues.name, "pliegues_v2.json")
```

Texto nuevo:

```python
        self.assertEqual(r.manifiesto_pliegues.name, "pliegues_v2_red2.json")     # Enmienda 2, R13
```

### Reemplazo 2

Texto actual (aparece una sola vez):

```python
        self.assertEqual(r.panel("pm25"), self.base / "v1" / "paneles" / "panel_pm25.parquet")
```

Texto nuevo:

```python
        self.assertEqual(r.panel("pm25"), self.base / "otra" / "paneles" / "panel_pm25_red2.parquet")  # R11
        self.assertEqual(r.panel_v1("pm25"), self.base / "v1" / "paneles" / "panel_pm25.parquet")
        derivado = (self.base / "derived" / "modelado" / "SINCA").resolve()
        self.assertIn(derivado / "v1", r.nunca_escribibles)
        self.assertNotIn(derivado / "v1_red2", r.nunca_escribibles)
```

### Reemplazo 3

Texto actual (aparece una sola vez):

```python
            r / "pliegues_v2_reemplazado_20261013T050000Z.json": "pliegues",
```

Texto nuevo:

```python
            r / "pliegues_v2_reemplazado_20261013T050000Z.json": "pliegues",
            r / "pliegues_v2_red2.json": "pliegues",
            r / "pliegues_v2_red2_reemplazado_20261101T000000Z.json": "pliegues",
```

## `scripts_modelo_1km/v2/tests/test_manifiesto_v2.py`

- **Origen:** sha256 `267b9707591dbdfb7047d12e2426f0488677972ff2a662acf794bb6a9a2bf2ce`.
- **Resultado:** sha256 `079aa5894108bdfc70bf8cb92ac58aa114c517a32d2b8ab29288a504a0fda325`.
- **Motivo:** R13: con la red ampliada el manifiesto vigente es pliegues_v2_red2.json; su panel declara «sha256_declarado» (el del json del panel red 2) y los conteos y el ejemplo de 3,7 km de la Enmienda 1 describen la red original. Se agrega la prueba de la fuente única.

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
        # Lo que la Enmienda 1 constató al escribirla: 10 de 34 bloques de PM2,5 (6 de 18 en NO2) a <= 10 km.
        self.assertEqual(len(M["contaminantes"]["pm25"]["diagnosticos"]["blq75_amortiguador"]
```

Texto nuevo:

```python
        if "schema_red2" in M:
            return                                  # Enmienda 2, R13: los conteos de la Enmienda 1 son de la red original
        # Lo que la Enmienda 1 constató al escribirla: 10 de 34 bloques de PM2,5 (6 de 18 en NO2) a <= 10 km.
        self.assertEqual(len(M["contaminantes"]["pm25"]["diagnosticos"]["blq75_amortiguador"]
```

### Reemplazo 2

Texto actual (aparece una sola vez):

```python
        diam = max(c["diametro_km"] for c in M["contaminantes"]["pm25"]["diagnosticos"]["conglomerados_encadenados"])
        self.assertAlmostEqual(diam, 3.7, delta=0.05)
```

Texto nuevo:

```python
        if "schema_red2" not in M:                  # Enmienda 2, R13: el ejemplo de 3,7 km es de la red original
            diam = max(c["diametro_km"] for c in M["contaminantes"]["pm25"]["diagnosticos"]["conglomerados_encadenados"])
            self.assertAlmostEqual(diam, 3.7, delta=0.05)
```

### Reemplazo 3

Texto actual (aparece una sola vez):

```python
            self.assertEqual(panel["sha256"], panel["sha256_declarado_v1"])
```

Texto nuevo:

```python
            # red original: «sha256_declarado_v1»; red 2 (Enmienda 2): «sha256_declarado», el del json del panel
            self.assertEqual(panel["sha256"], panel.get("sha256_declarado_v1", panel.get("sha256_declarado")))
```

### Reemplazo 4

Texto actual (aparece una sola vez):

```python
    def test_lro_y_lpo_como_la_v1(self):
```

Texto nuevo:

```python
    def test_red_ampliada_una_sola_fuente(self):
        """Enmienda 2, R13 a R16: pliegues, pesos, E2 y bloque más influyente en un solo archivo, con sus dos huellas,
        y la bitácora empieza con el reemplazo del manifiesto de la red original, intacto como respaldo."""
        if "schema_red2" not in M:
            self.skipTest("el manifiesto vigente es el de la red original")
        import hashlib
        import pliegues_red2_v2 as plr
        self.assertEqual(RUTA.name, plr.NOMBRE)
        for clave in ("pesos", "bloque_mas_influyente", "huella_pesos"):
            self.assertIn(clave, M)
        self.assertEqual(plr.huella_pesos(M), M["huella_pesos"])
        for pol in ("pm25", "no2"):
            self.assertIn("evaluabilidad_e2", M["pesos"][pol])
        e = M["bitacora"][0]
        self.assertEqual((e["evento"], e["regla"]), ("reemplazo", "R13"))
        respaldo = RUTA.parent / e["respaldo"]["ruta"]
        self.assertTrue(respaldo.name.startswith("pliegues_v2_reemplazado_"))
        self.assertEqual(hashlib.sha256(respaldo.read_bytes()).hexdigest(), e["respaldo"]["sha256"])

    def test_lro_y_lpo_como_la_v1(self):
```

## `scripts_modelo_1km/v2/tests/test_factibilidad_v2.py`

- **Origen:** sha256 `4fcd0613edb0e70b85958661841f7e6df89fb34dd753a7d00043869d5f34be0b`.
- **Resultado:** sha256 `9ab3d8410af87be36cfe6783513e68274297f8d1806cd1ee488cb7b73a08f98c`.
- **Motivo:** R11: el panel vive en la raíz v2 (paneles/panel_<pol>_red2.parquet); la prueba creaba la carpeta de la v1 (la medición sintética corre con la configuración sin el nodo, la de _sintetico_v2.config_pequena). R19 y R17 (cuarta revisión, menor 9): con el anexo, las fechas de la medición salen de criterio.valor_red_original (los regímenes de la Enmienda 1); la prueba sin el régimen 2019-2024 lo quita también de ahí, y una prueba nueva fija las fechas con los tramos calculados en criterio.valor. Quinta revisión, menores 13 y 24: una prueba nueva (reemplazo 3) exige que, con el nodo red_de_monitores, medir y publicar (también desde la consola) se detengan con «R19» antes de armar ninguna matriz ni escribir nada; falla sin los reemplazos 2 y 3 de factibilidad_v2.py. Ronda 4 de la traducción, mayores 2, 3 y 5: test_publicar_rechaza_un_resumen_con_metricas llamaba a publicar con la configuración real, que con el nodo red_de_monitores se detiene antes por R19 (SystemExit en vez de RuntimeError); el reemplazo 4 prueba la parada por métricas con la configuración real sin ese nodo (la red original) y afirma la de R19 con la configuración real, sin que quede archivo en ninguno de los dos casos.

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
            (r.raiz_v1 / "paneles").mkdir(parents=True, exist_ok=True)
            for pol in ("pm25", "no2"):
                PANEL.to_parquet(r.panel(pol), index=False)
```

Texto nuevo:

```python
            for pol in ("pm25", "no2"):
                r.panel(pol).parent.mkdir(parents=True, exist_ok=True)       # panel red 2 (Enmienda 2, R11)
                PANEL.to_parquet(r.panel(pol), index=False)
```

### Reemplazo 2

Texto actual (aparece una sola vez):

```python
        crit[clave] = [r for r in crit[clave] if r["id"] != "2019-2024"]
        with self.assertRaises(ValueError):
            fv.fechas_de_medicion(cfg)
```

Texto nuevo:

```python
        crit[clave] = [r for r in crit[clave] if r["id"] != "2019-2024"]
        crit.pop("valor_red_original", None)            # Enmienda 2: tampoco en los de la Enmienda 1 guardados
        with self.assertRaises(ValueError):
            fv.fechas_de_medicion(cfg)

    def test_con_el_anexo_las_fechas_de_la_enmienda_1(self):
        """Enmienda 2, R17 y R19: con el anexo, criterio trae los tramos calculados (ninguno es 2019-2024) y los de la
        Enmienda 1 quedan en valor_red_original; las fechas de la medición no cambian."""
        cfg = copy.deepcopy(CFG_REAL)
        crit = cfg["metricas"]["desagregaciones"]["regimen_de_predictores"]["criterio"]
        clave = "valor" if rv.estado_vigente(crit) == "ratificado" else "provisional"
        crit.setdefault("valor_red_original", copy.deepcopy(crit[clave]))
        crit[clave] = [{"id": i, "anios": a, "disponibilidad": "tramo calculado"}
                       for i, a in (("2000-2002", [2000, 2002]), ("2003-2017", [2003, 2017]), ("2018", [2018, 2018]),
                                    ("2019-2022", [2019, 2022]), ("2023-2026", [2023, 2026]))]
        self.assertEqual(fv.fechas_de_medicion(cfg), FECHAS)
        crit.pop("valor_red_original")
        with self.assertRaises(ValueError):                 # sin los de la Enmienda 1, no hay fechas que fijar
            fv.fechas_de_medicion(cfg)
```

### Reemplazo 3

Texto actual (aparece una sola vez):

```python
if __name__ == "__main__":
    unittest.main()
```

Texto nuevo:

```python
class RedAmpliadaR19Tests(unittest.TestCase):
    """Enmienda 2, R19 («la regla y su medición no cambian»): con el nodo red_de_monitores, factibilidad_v2 no vuelve a
    medir (leería el panel de la red 2) ni a publicar factibilidad_produccion.json, que decidir lee tal como quedó; se
    detiene antes de leer o escribir nada, también desde la consola."""

    def test_con_la_red_ampliada_no_se_vuelve_a_medir(self):
        cfg = {**config_pequena(), "red_de_monitores": {}}
        prohibido = mock.Mock(side_effect=AssertionError("se armaron las matrices de la medición"))
        with sx.raices_temporales("v2-factibilidad-r19-") as r:
            with self.assertRaises(SystemExit) as e:
                fv.medir(r, cfg, ["pm25"], hilos_ajuste=2, hilos_prediccion=2, armar=prohibido, esperar=False)
            self.assertIn("R19", str(e.exception))
            with self.assertRaises(SystemExit) as e:
                fv.publicar(r, cfg)
            self.assertIn("R19", str(e.exception))
            with mock.patch.object(fv, "rutas_v2", lambda: r), mock.patch.object(fv, "cargar_config", lambda r_: cfg):
                for argv in (["medir", "--hilos", "2", "--hilos-prediccion", "2", "--sin-esperar"], ["publicar"]):
                    with self.subTest(argv=argv), self.assertRaises(SystemExit) as e:
                        fv.main(argv)
                    self.assertIn("R19", str(e.exception))
            escritos = [q for q in Path(r.raiz_v2).rglob("*") if q.is_file()] if Path(r.raiz_v2).exists() else []
            self.assertEqual(escritos, [])                      # ni el candado ni las mediciones
        prohibido.assert_not_called()


if __name__ == "__main__":
    unittest.main()
```

### Reemplazo 4

Texto actual (aparece una sola vez):

```python
                with self.assertRaises(RuntimeError):
                    fv.publicar(r, CFG_REAL)
            self.assertFalse(fv.ruta_resumen(r).exists())
```

Texto nuevo:

```python
                with self.assertRaises(RuntimeError):           # la parada por métricas, con la red original
                    fv.publicar(r, {k: v for k, v in copy.deepcopy(CFG_REAL).items() if k != "red_de_monitores"})
                with self.assertRaises(SystemExit) as e:        # Enmienda 2, R19: con la red 2 se detiene antes
                    fv.publicar(r, CFG_REAL)
                self.assertIn("R19", str(e.exception))
            self.assertFalse(fv.ruta_resumen(r).exists())
```

## `scripts_modelo_1km/v2/tests/test_calidad_artefacto_v2.py`

- **Origen:** sha256 `f3268c6e8f7f787f248f742799297e0510993e37ec40c23c56b20cf0298e4b81`.
- **Resultado:** sha256 `564e46d60f45c213938b1817053833ddecd2a06fa2cb84e9b17a892e179a559b`.
- **Motivo:** R11: con RutasV2, ruta_calidad y panel apuntan a la red 2 y esta prueba se saltaría para siempre; sigue mirando la bandera real de la red original (calidad_<pol>.parquet con el panel v1), que queda intacta, con RutasRedOriginal. La de la red 2 la verifica su armado (calidad_sha256 en el json del panel).

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
R = rv.RutasV2.desde_entorno()
```

Texto nuevo:

```python
R = rv.RutasRedOriginal.desde_entorno()          # la bandera de la red original (Enmienda 2: queda intacta)
```

## `scripts_modelo_1km/v2/tests/test_calidad_v2.py`

- **Origen:** sha256 `fe1f7bd11cd752e52f11506654749cda6c643c608df37a42f818f54c6afaf020`.
- **Resultado:** sha256 `b771a2f5d6e09b95c62fdc518679706cd1c04d48a70e9ae22959e164203f0a50`.
- **Motivo:** el ciclo sintético prueba la réplica de la red original: corre con RutasRedOriginal (panel v1, calidad_<pol>.parquet, pliegues_v2.json) y con la configuración sin el nodo red_de_monitores; se agrega la prueba de que con el nodo el programa se detiene, también sin escribir.

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
        self.r = rv.RutasV2(raiz_v2=base / "v2", raiz_v1=base / "v1", datos=base / "datos", repo=self.repo,
```

Texto nuevo:

```python
        # la red original (Enmienda 2): panel v1, calidad_<pol>.parquet y pliegues_v2.json
        self.r = rv.RutasRedOriginal(raiz_v2=base / "v2", raiz_v1=base / "v1", datos=base / "datos", repo=self.repo,
```

### Reemplazo 2

Texto actual (aparece una sola vez):

```python
        return cv.ejecutar(self.m.r, rv.cargar_config(self.m.r), **kw)
```

Texto nuevo:

```python
        cfg = rv.cargar_config(self.m.r)
        cfg.pop("red_de_monitores", None)          # la réplica de la red original (Enmienda 2: ver la prueba siguiente)
        return cv.ejecutar(self.m.r, cfg, **kw)

    def test_con_la_red_ampliada_no_corre(self):
        """Enmienda 2: la bandera de la red 2 la escribe panel_red2_v2; este programa se detiene, también sin escribir."""
        cfg = rv.cargar_config(self.m.r)
        cfg.setdefault("red_de_monitores", {})
        for escribir in (True, False):
            with self.subTest(escribir=escribir), self.assertRaises(SystemExit) as e:
                cv.ejecutar(self.m.r, cfg, escribir=escribir, raiz_der=self.m.raiz_der, auditoria=self.m.auditoria)
            self.assertIn("panel_red2_v2", str(e.exception))
            self.assertNotIn("--no-escribir", str(e.exception))
        self.assertFalse(self.m.r.raiz_v2.exists())

    def test_la_bandera_sigue_al_panel(self):
        """Enmienda 2: con RutasV2 la bandera es la de la red 2 (calidad_<pol>_red2.parquet, junto a su panel)."""
        red2 = rv.RutasV2(raiz_v2=self.m.r.raiz_v2, raiz_v1=self.m.r.raiz_v1, datos=self.m.r.datos,
                          repo=self.m.r.repo, scripts_v2=self.m.r.scripts_v2)
        self.assertEqual(cv.ruta_calidad(red2, "pm25"), red2.raiz_v2 / "paneles" / "calidad_pm25_red2.parquet")
        self.assertEqual(cv.ruta_calidad(self.m.r, "pm25"), self.m.r.raiz_v2 / "paneles" / "calidad_pm25.parquet")

    def test_la_bandera_de_la_red_2_por_su_huella(self):
        """Enmienda 2: con el panel de la red 2, cargar_bandera exige el calidad_sha256 de su json y que calce."""
        red2 = rv.RutasV2(raiz_v2=self.m.r.raiz_v2, raiz_v1=self.m.r.raiz_v1, datos=self.m.r.datos,
                          repo=self.m.r.repo, scripts_v2=self.m.r.scripts_v2)
        ruta = cv.ruta_calidad(red2, "pm25")
        ruta.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({c: ["x"] for c in cv.COLUMNAS}).to_parquet(ruta, index=False)
        with self.assertRaises(SystemExit):                                  # el json no la declara
            cv.cargar_bandera("pm25", r=red2)
        red2.panel_meta("pm25").write_text(json.dumps({"calidad_sha256": "0" * 64}), encoding="utf-8")
        with self.assertRaises(SystemExit):                                  # no calza
            cv.cargar_bandera("pm25", r=red2)
        sha = hashlib.sha256(ruta.read_bytes()).hexdigest()
        red2.panel_meta("pm25").write_text(json.dumps({"calidad_sha256": sha}), encoding="utf-8")
        self.assertEqual(len(cv.cargar_bandera("pm25", r=red2)), 1)
```

## `scripts_modelo_1km/v2/tests/test_pliegues_v2.py`

- **Origen:** sha256 `21e1c1e338677948771e7358e08a1984a82b5e495ac0e68375d216d67d7b3711`.
- **Resultado:** sha256 `c703601345aeea193393167c04fd46e0157e76a67bc82af56f76c343da0d3a7b`.
- **Motivo:** el ciclo sintético prueba los pliegues de la red original: corre con RutasRedOriginal y con la configuración sin el nodo red_de_monitores; se agrega la prueba de que con el nodo el programa se detiene (única fuente: pliegues_red2_v2).

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
        self.r = rv.RutasV2(raiz_v2=b / "v2", raiz_v1=b / "v1", datos=b / "datos", repo=self.repo, scripts_v2=scripts)
```

Texto nuevo:

```python
        # la red original (Enmienda 2): panel v1 y pliegues_v2.json
        self.r = rv.RutasRedOriginal(raiz_v2=b / "v2", raiz_v1=b / "v1", datos=b / "datos", repo=self.repo,
                                     scripts_v2=scripts)
```

### Reemplazo 2

Texto actual (aparece una sola vez):

```python
    def ejecutar(self, **kw):
        return pv.ejecutar(self.r, rv.cargar_config(self.r), **kw)
```

Texto nuevo:

```python
    def ejecutar(self, **kw):
        cfg = rv.cargar_config(self.r)
        cfg.pop("red_de_monitores", None)          # los pliegues de la red original (Enmienda 2: ver la prueba siguiente)
        return pv.ejecutar(self.r, cfg, **kw)

    def test_con_la_red_ampliada_no_corre(self):
        """Enmienda 2, R13: los pliegues de la red 2 los fija pliegues_red2_v2 (única fuente); este programa se
        detiene, también sin escribir y al volver a fijar."""
        cfg = rv.cargar_config(self.r)
        cfg.setdefault("red_de_monitores", {})
        for kw in ({}, {"escribir": False}, {"refijar": True}):
            with self.subTest(**kw), self.assertRaises(SystemExit) as e:
                pv.ejecutar(self.r, cfg, **kw)
            self.assertIn("pliegues_red2_v2", str(e.exception))
        self.assertFalse(self.r.raiz_v2.exists())
```

## `scripts_modelo_1km/v2/tests/test_correr_v2.py`

- **Origen:** sha256 `59bbe7997f17fab70685c48fa73d6d7715afea8be1e6816a4b56b5eb2f8112a7`.
- **Resultado:** sha256 `b066ba45f815ffb96557fe7bd0b2af14ef27180095bb22f81b6acbf11146d984`.
- **Motivo:** R10: con el nodo red_de_monitores, el estrato de propietario se suma al del régimen fila a fila; sin el nodo, nada cambia. R15 (ronda 4 de la traducción, menor 14, corregido en la ronda 5, mayor 1): en decidir rige la evaluabilidad de E2 registrada antes del ajuste; con la evidencia en «no evaluable» (0,49) y la registrada en «evaluable» (0,51), decision_v2 recibe la registrada y la de la evidencia queda sólo en el registro; con la registrada evaluable y una evidencia sin pares E2, decidir se detiene (defecto de la corrida). Las piezas nuevas de correr_v2 con el nodo (tercera revisión, menores 26, 27, 29 y 44): Contexto.desde_disco se detiene sin el registro del anexo, sin la bandera o sin calidad, y corre con el registro y la bandera; decidir exige el anexo y el bloque de la evidencia; la consola rechaza --sin-calidad. La parada «sin el registro del anexo» se afirma por su mensaje y con un manifiesto que calza con el panel en disco, para que sea la única causa posible (cuarta revisión, menor 12). R16 y R17 (cuarta revisión, mayor 7 abierto, mayor 1): config_pequena copia de la configuración real el bloque más influyente y los regímenes, que el anexo reemplaza por los calculados; tres aserciones selladas fijaban los de la Enmienda 1 y ahora comparan con lo que rige: el bloque de dc.regla_de_config(CFG) y los ids de mt.regimenes_de_config(CFG).

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
if __name__ == "__main__":
    unittest.main()
```

Texto nuevo:

```python
class EstratoPropietarioTests(unittest.TestCase):
    """Enmienda 2, R10: el propietario de la estación de cada fila entra como estrato descriptivo de las métricas."""

    def test_con_y_sin_la_red_ampliada(self):
        from types import SimpleNamespace
        import panel_red2_v2 as pr
        with sx.raices_temporales("v2-estrato-") as r:
            (r.raiz_v2 / "paneles").mkdir(parents=True)
            ruta = r.raiz_v2 / "paneles" / pr.NOMBRE_ESTACIONES
            pd.DataFrame({"estacion": ["A", "B"], "tipo_propietario": ["pública", "empresa"]}).to_parquet(ruta, index=False)
            meta = r.raiz_v2 / "paneles" / pr.NOMBRE_PANEL.format(pol="no2").replace(".parquet", ".json")
            meta.write_text(json.dumps({"estaciones": {"sha256": pr.sha256_de(ruta)}}), encoding="utf-8")
            vec = SimpleNamespace(estaciones=np.array(["A", "B"]), js=np.array([0, 1, 1]))
            ctx = SimpleNamespace(cfg={}, rutas=r, pol="no2", vec=vec, regimen_fila_a_fila=None)
            self.assertEqual(cr.estratos_fila_a_fila(ctx)[0], {})                       # sin el nodo, como antes
            estratos, info = cr.estratos_fila_a_fila(SimpleNamespace(**{**vars(ctx), "cfg": {"red_de_monitores": {}}}))
            cod, etiquetas = estratos["propietario"]
            self.assertEqual((cod.tolist(), etiquetas[:2]), ([0, 1, 1], ["pública", "empresa"]))
            self.assertIn("propietario", info)


class RedAmpliadaTests(unittest.TestCase):
    """Enmienda 2: con el nodo red_de_monitores, Contexto.desde_disco exige el registro del anexo (R22, paso 4) y la
    bandera de calidad; decidir exige el anexo y que el bloque de cada evidencia sea el de la configuración (R16); la
    consola no admite --sin-calidad."""
    CFG_RED2 = {**CFG, "red_de_monitores": {}}

    def test_desde_disco_exige_el_anexo_y_la_bandera(self):
        import hashlib
        import calidad_v2
        import pliegues_red2_v2
        import pliegues_v2
        with sx.raices_temporales("v2-red2-disco-") as r:
            panel = sx.panel_sintetico()
            r.panel("pm25").parent.mkdir(parents=True, exist_ok=True)
            panel.to_parquet(r.panel("pm25"), index=False)
            man = sx.manifiesto_sintetico(panel)
            # el manifiesto calza con el panel en disco: la falta del registro del anexo es la única causa de la parada
            man["contaminantes"]["pm25"]["panel"]["sha256"] = hashlib.sha256(r.panel("pm25").read_bytes()).hexdigest()
            man["huella_pliegues"] = pliegues_v2.huella_pliegues(man)
            r.manifiesto_pliegues.write_text(json.dumps(man), encoding="utf-8")
            with self.assertRaises(SystemExit) as e:                         # sin el registro del anexo
                cr.Contexto.desde_disco("pm25", r, self.CFG_RED2, hilos=1)
            self.assertIn("anexo", str(e.exception))
            visto = {}

            def desde_tablas(pol, panel_, man_, cfg_, r_, etiqueta, h, calidad=None, vec=None, identidad_panel=None,
                             insumos=None):
                visto.update(calidad=calidad, insumos=insumos)
                return "contexto"
            with mock.patch.object(pliegues_red2_v2, "exigir_registro", lambda r_, cfg_, ruta=None: man), \
                    mock.patch.object(cr.Vecindario, "desde_panel", lambda *a, **k: "vecindario"), \
                    mock.patch.object(cr.Contexto, "desde_tablas", desde_tablas):
                with self.assertRaises(SystemExit):                          # con el registro, sin la bandera
                    cr.Contexto.desde_disco("pm25", r, self.CFG_RED2, hilos=1)
                with self.assertRaises(SystemExit):                          # sin calidad, tampoco
                    cr.Contexto.desde_disco("pm25", r, self.CFG_RED2, hilos=1, con_calidad=False)
                pd.DataFrame({"estacion": panel["estacion"], "ts_utc": panel["ts_utc"], "qc": "validado",
                              "fuente": "sinca"}).to_parquet(calidad_v2.ruta_calidad(r, "pm25"), index=False)
                bandera = lambda pol, claves, r_: pd.DataFrame({"qc": ["validado"] * len(claves)})   # noqa: E731
                with mock.patch.object(calidad_v2, "cargar_bandera", bandera):
                    self.assertEqual(cr.Contexto.desde_disco("pm25", r, self.CFG_RED2, hilos=1), "contexto")
                self.assertIn("calidad_pm25", visto["insumos"])
                self.assertEqual(len(visto["calidad"]), len(panel))

    def test_decidir_exige_el_anexo_y_el_bloque(self):
        import pliegues_red2_v2
        with sx.raices_temporales("v2-red2-decidir-") as r:
            with self.assertRaises(SystemExit):                              # sin el registro del anexo
                cr.decidir(r, self.CFG_RED2, "pm25", factibilidad={}, escribir=False)
            regla = dc.regla_de_config(self.CFG_RED2)
            for prot in regla.protocolos:
                ruta = cr.ruta_evidencia(r, cr.ETIQUETA, "pm25", prot)
                ruta.parent.mkdir(parents=True, exist_ok=True)
                ruta.write_text(json.dumps({"bloque_mas_influyente": "otro"}), encoding="utf-8")
            with mock.patch.object(pliegues_red2_v2, "exigir_registro", lambda r_, cfg_, ruta=None: {}):
                with self.assertRaises(SystemExit) as e:                     # evidencia con otro bloque (R16)
                    cr.decidir(r, self.CFG_RED2, "pm25", factibilidad={}, escribir=False)
                self.assertIn("R16", str(e.exception))

    def test_decidir_usa_la_evaluabilidad_registrada_de_e2(self):
        """Enmienda 2, R15 («se calcula sobre el panel de R11, con los mismos umbrales, antes de cualquier ajuste»): en
        decidir rige la evaluabilidad de E2 registrada en pliegues_v2_red2.json. Con la evidencia en «no evaluable»
        (0,49) y la registrada en «evaluable» (0,51), decision_v2 recibe la registrada (la condición 3 se exige) y la de
        la evidencia queda sólo en el registro de decision.json, con la huella de la evidencia consolidada; con la
        registrada evaluable y una evidencia sin pares E2, decidir se detiene (defecto de la corrida)."""
        import pliegues_red2_v2
        regla = dc.regla_de_config(self.CFG_RED2)
        registrada = {"evaluable": True, "fraccion_del_peso": 0.51, "grupos_con_E2": 5, "peso_E1": 10.0, "peso_E2": 5.1}
        man = {"pesos": {"pm25": {"evaluabilidad_e2": {"por_protocolo": {p: dict(registrada) for p in regla.protocolos}}}}}
        de_la_evidencia = {**registrada, "evaluable": False, "fraccion_del_peso": 0.49}

        def evidencias(r, vistas):
            for prot in regla.protocolos:
                ruta = cr.ruta_evidencia(r, cr.ETIQUETA, "pm25", prot)
                ruta.parent.mkdir(parents=True, exist_ok=True)
                ruta.write_text(json.dumps({"bloque_mas_influyente": regla.bloque_mas_influyente.get(prot),
                                            "semilla_bootstrap": 1, "semilla_salvaje": 2, "vistas": vistas,
                                            "evaluabilidad_E2": de_la_evidencia}), encoding="utf-8")
        recibidas = {}

        def decidir_motor(ev, f, **k):
            recibidas.update(ev)
            return pd.DataFrame(), {"decision": "prueba"}
        with sx.raices_temporales("v2-red2-decidir-e2-") as r, \
                mock.patch.object(pliegues_red2_v2, "exigir_registro", lambda r_, cfg_, ruta=None: man):
            evidencias(r, {})                                                # sin pares E2
            with self.assertRaises(SystemExit) as e:
                cr.decidir(r, self.CFG_RED2, "pm25", factibilidad={}, escribir=False)
            self.assertIn("R15", str(e.exception))
            self.assertIn("defecto de la corrida", str(e.exception))
            evidencias(r, {dc.V_E2: {}})                                     # con pares E2
            with mock.patch.object(dc, "decidir_motor", decidir_motor):
                res = cr.decidir(r, self.CFG_RED2, "pm25", factibilidad={}, escribir=False)
        self.assertEqual(sorted(recibidas), sorted(regla.protocolos))
        e2 = res["registro"]["evaluabilidad_E2_red2"]
        self.assertEqual(sorted(e2), sorted(regla.protocolos))
        for prot in regla.protocolos:
            self.assertTrue(recibidas[prot]["evaluabilidad_E2"]["evaluable"])       # la registrada, no la de la evidencia
            self.assertEqual(recibidas[prot]["evaluabilidad_E2"]["fraccion_del_peso"], 0.51)
            self.assertEqual((e2[prot]["rige"], e2[prot]["coinciden"]), (registrada, False))
            self.assertEqual(e2[prot]["de_la_decision"]["fraccion_del_peso"], 0.49)
            self.assertRegex(e2[prot]["evidencia_consolidada_sha256"], r"^[0-9a-f]{64}$")

    def test_la_consola_no_admite_sin_calidad(self):
        with sx.raices_temporales() as r, mock.patch.object(cr, "rutas_v2", lambda: r), \
                mock.patch.object(cr, "cargar_config", lambda r_: self.CFG_RED2):
            for accion in ("piloto", "correr", "consolidar"):
                with self.subTest(accion), self.assertRaises(SystemExit) as e:
                    cr.main([accion, "--sin-calidad"])
                self.assertIn("--sin-calidad", str(e.exception))


if __name__ == "__main__":
    unittest.main()
```

### Reemplazo 2

Texto actual (aparece una sola vez):

```python
        self.assertEqual((b["LRO"]["bloque_mas_influyente"], b["BLQ-75"]["bloque_mas_influyente"]), ("RM", "E004N083"))
```

Texto nuevo:

```python
        # el bloque que rige: el de la configuración (Enmienda 1: RM y E004N083; después del anexo de la Enmienda 2, el
        # calculado, R16)
        bloque = dc.regla_de_config(CFG).bloque_mas_influyente
        self.assertEqual((b["LRO"]["bloque_mas_influyente"], b["BLQ-75"]["bloque_mas_influyente"]),
                         (bloque["LRO"], bloque["BLQ-75"]))
```

### Reemplazo 3

Texto actual (aparece una sola vez):

```python
        self.assertEqual(f["bloque_influyente"], "RM")
        self.assertTrue(pd.isna(f["robusta_sin_bloque"]))                     # el LRO sintético no tiene RM
```

Texto nuevo:

```python
        self.assertEqual(f["bloque_influyente"], dc.regla_de_config(CFG).bloque_mas_influyente["LRO"])   # R16
        self.assertTrue(pd.isna(f["robusta_sin_bloque"]))                     # el LRO sintético no tiene ese bloque
```

### Reemplazo 4

Texto actual (aparece una sola vez):

```python
        ids = {x["id"] for x in mt.REGIMENES}
```

Texto nuevo:

```python
        ids = {x["id"] for x in mt.regimenes_de_config(CFG)}                 # los que rigen (R17, Enmienda 2)
```

## `scripts_modelo_1km/v2/tests/test_piloto_v2.py`

- **Origen:** sha256 `26f921ccebb275d22e9ec70c20ea50daeecbd3bf72a7dd543d6b798160c90fc8`.
- **Resultado:** sha256 `3b92a4ba91e343fb5be64b760552428d38757add48be037f0f717053047e3e21`.
- **Motivo:** R18: sobre el umbral tras los cuatro recortes se corre igual y queda registrado; ya no hay «pendiente_del_autor» ni «el exceso queda para el autor (enmienda)». Con el nodo red_de_monitores y sin la bandera de calidad, el piloto no estima el plan (tercera revisión, menor 44).

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
        self.assertIn("enmienda", d["bitacora"][-1]["accion"])
```

Texto nuevo:

```python
        self.assertIn("no hay quinto recorte (Enmienda 2, R18)", d["bitacora"][-1]["accion"])
```

### Reemplazo 2

Texto actual (aparece una sola vez):

```python
            self.assertIn("pendiente_del_autor", plan)
            self.assertIn("4 recortes", plan["pendiente_del_autor"])
```

Texto nuevo:

```python
            self.assertNotIn("pendiente_del_autor", plan)                   # Enmienda 2, R18: se corre igual
            self.assertIn("4 recortes", plan["sobre_el_umbral_tras_los_recortes"])
            self.assertIn("R18", plan["sobre_el_umbral_tras_los_recortes"])
            self.assertIn("R18", plan["bitacora_de_recortes"][-1]["accion"])
```

### Reemplazo 3

Texto actual (aparece una sola vez):

```python
    def test_incompleto_no_escribe_plan(self):
```

Texto nuevo:

```python
    def test_con_la_red_ampliada_exige_la_bandera(self):
        """Enmienda 2: con el nodo red_de_monitores, sin la bandera de calidad el piloto no estima el plan."""
        with sx.raices_temporales() as r:
            with self.assertRaises(SystemExit) as e:
                pv.estimar_y_publicar(r, {**CFG, "red_de_monitores": {}}, 2, contaminantes=["pm25"])
            self.assertIn("bandera de calidad", str(e.exception))
            self.assertFalse((r.raiz_v2 / pv.NOMBRE_PLAN).exists())

    def test_incompleto_no_escribe_plan(self):
```

## `scripts_modelo_1km/v2/tests/test_vecindario_v2.py`

- **Origen:** sha256 `b21d5315d060a97cb5b572bdeb6d5e57c460c48a58e9b9460477480b86e40d41`.
- **Resultado:** sha256 `f3ee3b5d960e70eebe3ab340b576663b63890c001c5fcde64314c777a581edbc`.
- **Motivo:** R11 y R13: las pruebas con datos reales leen el panel red 2 y su manifiesto, que se arman en el paso 3 de R22 (hasta entonces se saltan, con el motivo correcto); se agrega la prueba de la lectura float64 de la validación con la red ampliada.

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
HAY_REAL, "faltan el panel v1 o el manifiesto de pliegues")
```

Texto nuevo:

```python
HAY_REAL, "faltan el panel de la red 2 o su manifiesto de pliegues (pliegues_v2_red2.json): se arman "
                           "en el paso 3 de R22")
```

### Reemplazo 2

Texto actual (aparece una sola vez):

```python


# ---------------------------------------------------------------------------
# Datos reales (sólo lectura)
```

Texto nuevo:

```python


class ValidacionRed2Tests(unittest.TestCase):
    """Enmienda 2: con la red ampliada, la reproducción (a2) de validar_vecindario_v2 lee las observaciones float64 que
    escribió panel_red2_v2, por su sha256, y exige la configuración de su armado."""

    def test_lee_las_del_armado_y_exige_su_configuracion(self):
        import panel_red2_v2 as pr
        import validar_vecindario_v2 as vval
        sys.path.insert(0, str(V2 / "tests"))
        from _sintetico_v2 import raices_temporales
        with raices_temporales("v2-vecindario-red2-") as r:
            (r.raiz_v2 / "paneles").mkdir(parents=True)
            o = pd.DataFrame({"estacion": ["A"], "ts_utc": pd.to_datetime(["2020-01-01 03:00"]), "obs": [1.0000000001]})
            ruta = r.raiz_v2 / "paneles" / pr.NOMBRE_OBS.format(pol="pm25")
            o.to_parquet(ruta, index=False)
            meta = {"schema": pr.SCHEMA, "desde": pr.DESDE, "hasta": pr.HASTA, "qc_racha_minima": pr.QC_RACHA,
                    "observaciones_sha256": {"pm25": hashlib.sha256(ruta.read_bytes()).hexdigest()},
                    "qc": {"horas_totales": 1, "horas_en_racha": 0, "estaciones_con_racha": 0}}
            leido, info = vval.observaciones_red2_float64("pm25", r, meta)
            self.assertEqual(leido["obs"].iloc[0], 1.0000000001)
            self.assertIn("Enmienda 2", info["qc_nota"])
            for clave, valor in (("hasta", "2026-09-13"), ("schema", "otro")):
                with self.subTest(clave=clave), self.assertRaises(SystemExit):
                    vval.observaciones_red2_float64("pm25", r, {**meta, clave: valor})


# ---------------------------------------------------------------------------
# Datos reales (sólo lectura)
```

## `scripts_modelo_1km/v2/tests/test_config_v2.py`

- **Origen:** sha256 `c7f4b4f64cd19c0e4a52620567f39353a51a794de6c46237add858d8b3523066`.
- **Resultado:** sha256 `186d590ba0d2269f492a2b8d55ba342597503075bc11766bb2f38ba69d49084e`.
- **Motivo:** la prueba sellada supone que el Complemento llega hasta el final del contrato y que hay dos enmiendas; con el bloque, el Complemento termina donde empieza la Enmienda 2 y su huella sigue siendo 5d879a05…. Se agrega la prueba de la entrada del bloque (con las decisiones de traducción T1 a T13, T11, T12 y T13 con su marca [delegada], y T8 igual en el código y en la configuración) y la desagregación por propietario (R10). Las pruebas de los cinco regímenes y del bloque más influyente leen lo que rige después del anexo (R16 y R17; tercera revisión, mayor 7 y menor 30): con el anexo, los tramos comunes de regimenes_red2.json y el bloque de pliegues_v2_red2.json; sin él, los valores de la Enmienda 1.

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
_INICIO_COMPLEMENTO = CONTRATO.find(ENCABEZADO_COMPLEMENTO)
# La Enmienda 1 va desde su encabezado hasta el del Complemento; el Complemento, hasta el final del contrato.
ENMIENDA_1 = CONTRATO[_INICIO_E1:_INICIO_COMPLEMENTO] if 0 <= _INICIO_E1 < _INICIO_COMPLEMENTO else ""
COMPLEMENTO = CONTRATO[_INICIO_COMPLEMENTO:] if _INICIO_COMPLEMENTO >= 0 else ""
```

Texto nuevo:

```python
_INICIO_COMPLEMENTO = CONTRATO.find(ENCABEZADO_COMPLEMENTO)
ENCABEZADO_BLOQUE_RED2 = "### Enmienda 2 ambiental — bloque «Red ampliada e insumos de hoy» ("
_INICIO_BLOQUE_RED2 = CONTRATO.find(ENCABEZADO_BLOQUE_RED2)
_FIN_COMPLEMENTO = _INICIO_BLOQUE_RED2 if _INICIO_BLOQUE_RED2 >= 0 else len(CONTRATO)
# La Enmienda 1 va desde su encabezado hasta el del Complemento; el Complemento, hasta el bloque de la red ampliada de
# la Enmienda 2 (o hasta el final del contrato, si no está).
ENMIENDA_1 = CONTRATO[_INICIO_E1:_INICIO_COMPLEMENTO] if 0 <= _INICIO_E1 < _INICIO_COMPLEMENTO else ""
COMPLEMENTO = CONTRATO[_INICIO_COMPLEMENTO:_FIN_COMPLEMENTO] if _INICIO_COMPLEMENTO >= 0 else ""
BLOQUE_RED2 = CONTRATO[_INICIO_BLOQUE_RED2:] if _INICIO_BLOQUE_RED2 >= 0 else ""
# Texto del contrato tal como quedó con el Complemento, antes del bloque de la red ampliada.
TEXTO_CON_EL_COMPLEMENTO = CONTRATO[:_FIN_COMPLEMENTO].rstrip("\n") + "\n"
```

### Reemplazo 2

Texto actual (aparece una sola vez):

```python
SHA_ENMIENDA_1 = "05218686b3f1808d5379b095789ada4ea69ba02362be8063330a2c2f9f5a5e17"    # texto con la Enmienda 1

```

Texto nuevo:

```python
SHA_ENMIENDA_1 = "05218686b3f1808d5379b095789ada4ea69ba02362be8063330a2c2f9f5a5e17"    # texto con la Enmienda 1
SHA_COMPLEMENTO = "5d879a05179a3e980d01e25e12bb4f3492d4fe6b4142f7be6daa2509df4c39b0"   # texto con el Complemento
SHA_BLOQUE_RED2 = "274ebae06bee8eeeb7470a650ce0539af751577d292513b8198cdec7c159094b"   # bloque anclado en APH (f2c6cfc)
SHA_DECISIONES_TRADUCCION = "a0b970d2fbbf08a11c28d24c075ca1dd81ef2509d2093d243c1fc7a95dad3920"  # T1 a T13 (T11 a T13 [delegadas], ratificadas el 2026-10-26)

```

### Reemplazo 3

Texto actual (aparece una sola vez):

```python
        self.assertEqual([e["id"] for e in enm], ["Enmienda 1", "Complemento de la Enmienda 1"])
```

Texto nuevo:

```python
        self.assertEqual([e["id"] for e in enm], ["Enmienda 1", "Complemento de la Enmienda 1",
                                                  "Enmienda 2, bloque de la red ampliada"])
```

### Reemplazo 4

Texto actual (aparece una sola vez):

```python
        self.assertEqual((e["id"], e["fecha"], e["sha256"]), ("Complemento de la Enmienda 1", "2026-10-13",
                                                              CFG["contrato"]["sha256"]))
```

Texto nuevo:

```python
        self.assertEqual((e["id"], e["fecha"], e["sha256"]), ("Complemento de la Enmienda 1", "2026-10-13",
                                                              SHA_COMPLEMENTO))
        # su sha256 es el del texto tal como quedó con él: el contrato vigente sin el bloque de la red ampliada
        self.assertEqual(hashlib.sha256(TEXTO_CON_EL_COMPLEMENTO.encode("utf-8")).hexdigest(), SHA_COMPLEMENTO)
```

### Reemplazo 5

Texto actual (aparece una sola vez):

```python
    def test_entrada_del_complemento(self):
```

Texto nuevo:

```python
    def test_entrada_del_bloque_red_ampliada(self):
        e = CFG["contrato"]["enmiendas"][2]
        self.assertEqual((e["id"], e["fecha"], e["sha256"]), ("Enmienda 2, bloque de la red ampliada", "2026-10-25",
                                                              CFG["contrato"]["sha256"]))
        self.assertEqual(e["texto_del_bloque"]["sha256"], SHA_BLOQUE_RED2)
        self.assertEqual(e["decisiones_de_traduccion"]["sha256"], SHA_DECISIONES_TRADUCCION)
        self.assertIn(SHA_BLOQUE_RED2, BLOQUE_RED2)
        self.assertIsNone(e["commit"])
        self.assertEqual([p["punto"] for p in e["puntos"]], [f"R{k}" for k in range(2, 23)])
        for p in e["puntos"]:
            self.assertIn(f"##### {p['punto']}. ", BLOQUE_RED2)
            for ruta in p["config"]:
                with self.subTest(punto=p["punto"], ruta=ruta):
                    obtener(ruta)                                # existe
        self.assertEqual(CFG["red_de_monitores"]["red_resultante"]["no2"]["total"], 71)
        reg = CFG["red_de_monitores"]["registro_de_la_red"]
        self.assertEqual(reg["pliegues"]["archivo"], "pliegues_v2_red2.json")
        self.assertEqual((reg["reloj"]["regla"], reg["catalogo_maiac"]["regla"]),
                         ("T4 con la unidad de T9", "T5"))                    # los llena el anexo
        self.assertTrue(reg["tropomi_por_fecha"]["regla"].startswith("T11 [delegada]"))
        if reg["pliegues"]["sha256"] is None:                   # antes del anexo (R22, paso 4), todo vacío
            self.assertIsNone(reg["regimenes"]["sha256"])
            self.assertIsNone(reg["reloj"]["veredictos_sha256"])
        else:                                                    # después, el anexo completo
            self.assertTrue(reg["regimenes"]["sha256"] and reg["reloj"]["veredictos_sha256"])
        dec = e["decisiones_de_traduccion"]
        self.assertTrue(all(dec[k] for k in ("T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12", "T13")))
        for k in ("T11", "T12", "T13"):                          # las delegadas, ratificadas el 2026-10-26 (T13)
            self.assertTrue(dec[k].startswith("[delegada]"))
        # T8: la huella de afg_lib.py y su procedencia, iguales en el código y en la configuración
        import derivado_red2_v2 as dr
        afg = CFG["red_de_monitores"]["calidad"]["derivado"]["afg_lib"]
        self.assertEqual(afg["sha256"], dr.SHA_AFG)
        self.assertEqual({k: {"python": v["python"], "ranking_ast_sha256": v["ranking"],
                              "parser_ast_sha256": v["analizador"]} for k, v in afg["procedencia_ast"].items()},
                         dr.PROCEDENCIA_AST_AFG)

    def test_entrada_del_complemento(self):
```

### Reemplazo 6

Texto actual (aparece una sola vez):

```python
        self.assertEqual(set(self.m["desagregaciones"]), {"macrozona", "estacion", "regimen_de_predictores",
                                                          "estrato_de_soporte", "ponderado_por_poblacion"})
```

Texto nuevo:

```python
        self.assertEqual(set(self.m["desagregaciones"]), {"macrozona", "estacion", "regimen_de_predictores",
                                                          "estrato_de_soporte", "ponderado_por_poblacion",
                                                          "propietario"})
```

### Reemplazo 7

Texto actual (aparece una sola vez):

```python
    def test_cinco_regimenes_contiguos(self):
        r = self.m["desagregaciones"]["regimen_de_predictores"]
        reg = valor(r["criterio"])
        self.assertEqual([x["id"] for x in reg], ["2000-2002", "2003-2018", "2019-2024", "2025", "2026"])
```

Texto nuevo:

```python
    def test_cinco_regimenes_contiguos(self):
        r = self.m["desagregaciones"]["regimen_de_predictores"]
        reg = valor(r["criterio"])
        sys.path.insert(0, str(V2 / "tests"))
        from _sintetico_v2 import anexo_de_la_red
        anexo = anexo_de_la_red(CFG)            # Enmienda 2, R17: después del anexo rigen los tramos calculados
        if anexo is None:
            self.assertEqual([x["id"] for x in reg], ["2000-2002", "2003-2018", "2019-2024", "2025", "2026"])
        else:
            self.assertEqual([(x["id"], list(x["anios"]), x["disponibilidad"]) for x in reg],
                             [(x["id"], list(x["anios"]), x["disponibilidad"]) for x in anexo["tramos"]])
```

### Reemplazo 8

Texto actual (aparece una sola vez):

```python
        t = seccion(10)
        for x in reg:
            self.assertIn(x["disponibilidad"], t)
```

Texto nuevo:

```python
        t = seccion(10)
        for x in (reg if anexo is None else []):                # los rótulos del §10 son los de la Enmienda 1
            self.assertIn(x["disponibilidad"], t)
```

### Reemplazo 9

Texto actual (aparece una sola vez):

```python
        inf = self.i["influencia"]
        self.assertEqual(inf["bloque_mas_influyente"], {"LRO": "RM", "BLQ-75": "E004N083"})
```

Texto nuevo:

```python
        inf = self.i["influencia"]
        sys.path.insert(0, str(V2 / "tests"))
        from _sintetico_v2 import anexo_de_la_red
        anexo = anexo_de_la_red(CFG)            # Enmienda 2, R16: después del anexo rige el bloque calculado
        self.assertEqual(inf["bloque_mas_influyente"],
                         {"LRO": "RM", "BLQ-75": "E004N083"} if anexo is None else anexo["bloque"])
```

## `scripts_modelo_1km/v2/tests/test_metricas_v2.py`

- **Origen:** sha256 `2ae7a194513bc280fcc5ccef5a10ec98b2b729e754da02e827325fa29e398b26`.
- **Resultado:** sha256 `17ca2affac3f08bb23b4a04e4c5b5821725df85865dc79703f4e394616992015`.
- **Motivo:** R17 (tercera revisión, mayor 7 y menor 30): el anexo escribe en criterio.valor los tramos comunes calculados para la red 2; la prueba compara la configuración con ellos (anexo_de_la_red) y, sin anexo, con los cinco regímenes de la Enmienda 1. Lo demás de la prueba sigue sobre REGIMENES, la constante de la Enmienda 1 del código.

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
    def test_cinco_regimenes_iguales_a_la_configuracion(self):
        self.assertEqual(mt.regimenes_de_config(CFG), mt._normalizar_regimenes(mt.REGIMENES))
```

Texto nuevo:

```python
    def test_cinco_regimenes_iguales_a_la_configuracion(self):
        sys.path.insert(0, str(V2 / "tests"))
        from _sintetico_v2 import anexo_de_la_red
        anexo = anexo_de_la_red(CFG)            # Enmienda 2, R17: después del anexo rigen los tramos calculados
        self.assertEqual(mt.regimenes_de_config(CFG),
                         mt._normalizar_regimenes(mt.REGIMENES if anexo is None else anexo["tramos"]))
```

## `scripts_modelo_1km/v2/tests/test_decision_v2.py`

- **Origen:** sha256 `2be67aec4e1ef43ce8d07ae7ae5e4d84f766267c00cf4097f1ed44657946b370`.
- **Resultado:** sha256 `c6b413c7108a1bb80a2065586a3d1ed668727b6928275b24c2d4c02340956d6a`.
- **Motivo:** R16 (tercera revisión, mayor 7 y menor 30): el anexo escribe en inferencia_diferencias.influencia el bloque más influyente calculado para la red 2; la regla leída de la configuración es la de ReglaDecision con ese bloque (anexo_de_la_red) y, sin anexo, con el de la Enmienda 1 (RM y E004N083).

### Reemplazo 1

Texto actual (aparece una sola vez):

```python
        regla = dc.regla_de_config(CFG)
        self.assertEqual(regla, dc.ReglaDecision())
```

Texto nuevo:

```python
        regla = dc.regla_de_config(CFG)
        import dataclasses
        sys.path.insert(0, str(V2 / "tests"))
        from _sintetico_v2 import anexo_de_la_red
        anexo = anexo_de_la_red(CFG)            # Enmienda 2, R16: después del anexo rige el bloque calculado
        bloque = {"LRO": "RM", "BLQ-75": "E004N083"} if anexo is None else anexo["bloque"]
        self.assertEqual(regla, dataclasses.replace(dc.ReglaDecision(), bloque_mas_influyente=bloque))
```

### Reemplazo 2

Texto actual (aparece una sola vez):

```python
        self.assertEqual(regla.bloque_mas_influyente, {"LRO": "RM", "BLQ-75": "E004N083"})
```

Texto nuevo:

```python
        self.assertEqual(regla.bloque_mas_influyente, bloque)
```
