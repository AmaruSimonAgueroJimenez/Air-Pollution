"""Conecta la interpolación bilineal a la producción de superficies.

El defecto que repara: `produccion.py` arma su propio contexto con `<producto>_pixel` y llama a
`FuentesHorarias.extraer` directo, sin pasar por `ensamblar_horario`, así que `MODELO_1KM_INTERPOLAR`
era inerte allí. Un modelo calibrado sobre predictores interpolados habría recibido en producción
predictores de vecino más cercano: desviación silenciosa de 0,2 a 0,67 desviaciones estándar por
variable, sin aviso ni error.

Para que no vuelva a separarse, el promedio ponderado de los cuatro nodos queda en **una sola
función** de `_features.py` que usan los dos caminos.

    python parche_produccion_interp.py          # aplica
"""
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent     # el repositorio donde vive este script


def editar(ruta, pares):
    p = RAIZ / ruta
    s = p.read_text()
    for viejo, nuevo in pares:
        if nuevo in s:
            print(f"  ya aplicado: {ruta} :: {viejo.strip().splitlines()[0][:60]}")
            continue
        if viejo not in s:
            raise SystemExit(f"NO ENCONTRADO en {ruta}:\n{viejo[:300]}")
        s = s.replace(viejo, nuevo, 1)
    p.write_text(s)
    print(f"  {ruta}")


# ---------------------------------------------------------------- _features.py
editar("scripts_modelo_1km/_features.py", [(
'''def _extraer_interpolado(producto, ts, celdas, fuentes) -> dict[str, np.ndarray]:
    """Media ponderada de los cuatro nodos que rodean a cada celda.

    Los pesos se renormalizan sobre los nodos con dato en esa hora, de modo que un vecino sin archivo no
    arrastra el valor hacia abajo: con un solo nodo presente el resultado es ese nodo, como antes.
    """
    w = enlaces_interpolacion()
    pix = [w.loc[celdas, f"{producto}_pix{k}"].to_numpy("int64") for k in range(4)]
    pes = [w.loc[celdas, f"{producto}_w{k}"].to_numpy("float64") for k in range(4)]
    cols = list(FEATURES_HORARIAS[producto].values())
    num = {c: np.zeros(len(ts), "float64") for c in cols}
    den = {c: np.zeros(len(ts), "float64") for c in cols}
    for k in range(4):
        usa = pes[k] > 0
        if not usa.any():
            continue
        seguro = np.where(usa, pix[k], pix[0])            # índice válido donde el peso es nulo
        for col, arr in fuentes.extraer(producto, ts, seguro).items():
            ok = usa & np.isfinite(arr)
            num[col][ok] += pes[k][ok] * arr[ok]
            den[col][ok] += pes[k][ok]
    return {c: np.where(den[c] > 1e-12, num[c] / np.maximum(den[c], 1e-12), np.nan).astype("float32")
            for c in cols}''',
'''def estencil(producto: str, celdas) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Píxeles y pesos de los cuatro nodos, como arreglos alineados con ``celdas``.

    Se calcula una vez y se reutiliza: hacer el ``.loc`` dentro del bucle horario era el grueso del
    sobrecosto de la interpolación.
    """
    w = enlaces_interpolacion()
    if f"{producto}_w0" not in w.columns:
        raise KeyError(f"{producto} no tiene pesos en enlaces_interpolacion.parquet")
    sub = w.loc[celdas]
    return ([sub[f"{producto}_pix{k}"].to_numpy("int64") for k in range(4)],
            [sub[f"{producto}_w{k}"].to_numpy("float64") for k in range(4)])


def combinar_nodos(producto, ts, pix, pes, fuentes) -> dict[str, np.ndarray]:
    """Media ponderada de los cuatro nodos que rodean a cada celda.

    Única implementación: la usan el panel de calibración y la producción de superficies, para que no
    puedan separarse. Los pesos se renormalizan sobre los nodos **con dato en esa hora**, de modo que un
    vecino sin archivo no arrastra el valor hacia abajo: con un solo nodo presente el resultado es ese
    nodo, como en el camino de siempre. Sin ningún nodo con dato, NaN, que es lo que el motor espera.
    """
    cols = list(FEATURES_HORARIAS[producto].values())
    num = {c: np.zeros(len(ts), "float64") for c in cols}
    den = {c: np.zeros(len(ts), "float64") for c in cols}
    for k in range(4):
        usa = pes[k] > 0
        if not usa.any():
            continue
        # donde el peso es cero el índice no se usa, pero igual tiene que ser legible: se sustituye por
        # cualquier píxel válido de la misma fila, nunca por -1
        respaldo = np.where(pix[0] >= 0, pix[0], np.maximum(pix[k], 0))
        seguro = np.where(usa & (pix[k] >= 0), pix[k], respaldo)
        for col, arr in fuentes.extraer(producto, ts, seguro).items():
            ok = usa & np.isfinite(arr)
            num[col][ok] += pes[k][ok] * arr[ok]
            den[col][ok] += pes[k][ok]
    return {c: np.where(den[c] > 1e-12, num[c] / np.maximum(den[c], 1e-12), np.nan).astype("float32")
            for c in cols}


def _extraer_interpolado(producto, ts, celdas, fuentes) -> dict[str, np.ndarray]:
    pix, pes = estencil(producto, celdas)
    return combinar_nodos(producto, ts, pix, pes, fuentes)'''
), (
'''        if producto in interp and f"{producto}_w0" in enlaces_interpolacion().columns:
            vals = _extraer_interpolado(producto, ts, df["celda"], fuentes)
        else:''',
'''        if producto in interp:
            if f"{producto}_w0" not in enlaces_interpolacion().columns:
                raise KeyError(f"MODELO_1KM_INTERPOLAR nombra '{producto}' pero no tiene pesos en "
                               "enlaces_interpolacion.parquet; corre enlaces_interpolacion.py --forzar. "
                               "Caer al vecino más cercano en silencio dejaría un panel mitad "
                               "interpolado y la comparación no mediría el diseño que dice medir.")
            vals = _extraer_interpolado(producto, ts, df["celda"], fuentes)
        else:'''
)])

# --------------------------------------------------------------- produccion.py
editar("scripts_modelo_1km/produccion.py", [(
'''from _features import (AcagMensual, FuentesHorarias, SatelitesDiarios, VecindarioFijo, cargar_estaticas,
                       derivadas_horarias, unir_estaticas)''',
'''from _features import (AcagMensual, FuentesHorarias, SatelitesDiarios, VecindarioFijo, cargar_estaticas,
                       combinar_nodos, derivadas_horarias, estencil, productos_interpolados,
                       unir_estaticas)'''
), (
'''        self.pix = {p: self.enlaces[f"{p}_pixel"].to_numpy(dtype="int64") for p in self.fuentes.productos
                    if f"{p}_pixel" in self.enlaces.columns}''',
'''        self.pix = {p: self.enlaces[f"{p}_pixel"].to_numpy(dtype="int64") for p in self.fuentes.productos
                    if f"{p}_pixel" in self.enlaces.columns}
        # Los mismos pesos bilineales con que se calibró. Si el modelo se ajustó con interpolación y la
        # producción no la aplicara, el motor recibiría predictores escalonados que nunca vio.
        self.interp = {p: estencil(p, self.celdas["celda"]) for p in productos_interpolados()
                       if p in self.pix}
        if self.interp:
            log.info("%s: interpolación bilineal en %s", pol, ", ".join(sorted(self.interp)))'''
), (
'''            for producto, pixel in self.pix.items():
                for col, arr in self.fuentes.extraer(producto, ts_vec, pixel).items():
                    df[col] = arr''',
'''            for producto, pixel in self.pix.items():
                if producto in self.interp:
                    pix4, pes4 = self.interp[producto]
                    vals = combinar_nodos(producto, ts_vec, pix4, pes4, self.fuentes)
                else:
                    vals = self.fuentes.extraer(producto, ts_vec, pixel)
                for col, arr in vals.items():
                    df[col] = arr'''
), (
'''            if reg.get("bytes") == nc_path.stat().st_size and reg.get("modelo_sha256") == self.modelo.sha \\
                    and reg.get("enlaces_sha256") == self.e.enlaces_sha256 and reg.get("celdas") == int(self.n) \\
                    and reg.get("retransformacion") == self.modelo.retransformacion:''',
'''            if reg.get("bytes") == nc_path.stat().st_size and reg.get("modelo_sha256") == self.modelo.sha \\
                    and reg.get("enlaces_sha256") == self.e.enlaces_sha256 and reg.get("celdas") == int(self.n) \\
                    and reg.get("retransformacion") == self.modelo.retransformacion \\
                    and reg.get("interpolacion", "") == self.firma_interpolacion:'''
), (
'''                     "retransformacion": self.modelo.retransformacion, "celdas": int(self.n),''',
'''                     "retransformacion": self.modelo.retransformacion, "celdas": int(self.n),
                     "interpolacion": self.firma_interpolacion,'''
), (
'''                       "retransformacion": self.modelo.retransformacion, "celdas": int(self.n), "fraccion_nan": float(np.mean(~np.isfinite(salida))),''',
'''                       "retransformacion": self.modelo.retransformacion, "celdas": int(self.n),
                       "interpolacion": self.firma_interpolacion,
                       "fraccion_nan": float(np.mean(~np.isfinite(salida))),'''
)])

# la firma como propiedad, junto al resto del contexto
editar("scripts_modelo_1km/produccion.py", [(
'''    def reiniciar_ventana_satelital(self) -> None:''',
'''    @property
    def firma_interpolacion(self) -> str:
        """Qué productos se interpolaron, para que un día producido con un diseño no se dé por bueno
        bajo otro: el guardián por día sólo miraba bytes, modelo, enlaces, celdas y retransformación."""
        return ",".join(sorted(self.interp))

    def reiniciar_ventana_satelital(self) -> None:'''
)])

print("\nlisto")
