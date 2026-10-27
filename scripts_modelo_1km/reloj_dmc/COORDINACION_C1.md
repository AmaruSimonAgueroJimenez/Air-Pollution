# Coordinación de la implementación C1 (reloj DMC)

Notas que dejan los implementadores para las tandas siguientes y para el addendum de C1. Se agregan al final, por fecha.

## Pendientes de interfaces comunes

- `tipos.validar_esquema` y `tipos.tabla_vacia` siguen sin implementar y no tienen dueño en la ola 1. `estados.py` arma
  ESQUEMA_ESTADOS por su cuenta mientras tanto. Se asignan en la ola 2 y, al implementarlas, `estados.py` pasa a usarlas.
- `numerico.py` lee `constantes.POR_NOMBRE[...]`, porque `constantes.valor` está en implementación en la ola 1. Al cerrar la ola
  se unifica el acceso.
- La prueba AST de literales (dueño: `umbrales` y `constantes`) debe poner en su lista blanca los literales de definición de
  `numerico.py`: el 3 (n < 3 en Pearson), el 8 (bytes del sha256) y el 9 y el 10 de `DESFASES_VENTANA`.
- «λ/15» está escrito en `numerico.py` como 360°/24 h. Conviene pasarlo a `constantes.py` con su fragmento literal.

## Lecturas para el addendum de C1 (además de las de DISENO_IMPLEMENTACION.md §7.2)

- **`numerico` y `estados` (ola 1, 2026-10-23):**
  - en `anual_por_partes`, una H que no queda incompatible sale con fila anual «sin_informacion» sin motivo, y cada línea
    aplica después su regla de compatibilidad. En E6, el nivel ANIO es evidencia agregada y reemplaza la fila anual;
  - las partes incompatibles y las anómalas se cuentan por separado: una de cada una deja ambas discordantes, y el año no
    queda incompatible ni anómalo;
  - validaciones estrictas:
    - una estación, línea y regla por llamada;
    - `semilla` acepta sólo «Ts» o «QFE» y las unidades «AAAA-MM-n», «R0», «R1» y «V-<sha8>», con base entera;
    - `estado_de_clase` exige igualdad exacta;
  - la secuencia PCG64 de numpy 2.2.6 queda fijada en las pruebas, para notar si una versión nueva la cambia.
- **`entorno` y `fijados` (ola 1, 2026-10-23):**
  - **versiones del descargador:** las 6 admitidas en C0 y las 2 que encontró el inventario (`fc1f1bb6` y `975d9bf0`, en
    `APH/tmp/...`) dan la huella de ruta de etiqueta `af1b0e1b…`. Son admisibles por la regla mecánica de §3.1: 8 de 11.
    `VERSIONES_ADMITIDAS_C0` no cambia. El conjunto vigente sale de `fijados.versiones_admitidas()` o del addendum, y lo usan
    `extraccion` y `verificar_reloj_dmc`;
  - `transiciones_sinca` no lleva huella, porque el protocolo no la fija. La prueba comprueba las líneas 47-73 y el
    comportamiento de §1.10;
  - `06e46f83` se cita desde la copia de C0 en `LOCAL/evidencia_vista/reloj_dmc/descargador/...`, con la misma sha256;
  - `cargar_por_ruta` deja a `runner_v3` fijando a 2 los hilos de OMP, BLAS y pyarrow, un efecto conocido;
  - el registro C0 sobre la «base del sistema» se corrige en la Enmienda 1, punto E1-7.
- **Para `sintetico` (ola 2):** `run_download` importa `_meteo_http_parallel` sólo con `http_workers > 1` o con el
  calendario rápido. Con `http_workers=1` no hacen falta rutas de importación.
- **`umbrales` y `constantes` (ola 1, 2026-10-23):**
  - `regenerar_desde_texto` reproduce `c0/reloj_dmc_v1.json` byte a byte. `comparar` es estricto (tipos, orden de claves) y sólo
    deja fuera la clave `bateria`;
  - 23 ajustables del JSON y 124 fijos traducidos con 33 plantillas. Hay 73 constantes del cuerpo, cada una con su fragmento
    dentro de la sección citada;
  - `SENTIDO_CONSERVADOR` impide mover un umbral hacia lo menos conservador. `umbrales.cargar_c0(APH)` sirve para las pruebas;
  - **literales tolerados que deben corregir sus dueños** (la lista está en `test_umbrales.py`):
    - en `numerico.py`, `range(-9, 10)` debe ser `U.f("E3_VENTANA")` y `digest()[:8]` debe ser `SEMILLA_BYTES`;
    - en `lineas_registro.py`, `hora % 3` debe ser `E2_MODULO`;
    - en `tablas.py`, `DIVISOR_REGION = 1000` debe ser `REGION_DIVISOR`;
  - **ambigüedades del texto,** con la lectura implementada, para el addendum o la Enmienda 1:
    1. G-HR tiene dos fuentes para un mismo umbral: el fragmento `GHR_A1_TS_Y_EE` incluye «A1(HR) ≥ 5 puntos», que también es el
       ajustable `GHR_A1_HR`. Propuesta: `guardas` usa `U.f("GHR_A1_HR")`;
    2. en §8.F, «si una lista se agota, C1 falla» frente a «el primer umbral no agotado de su lista». Se implementó que C1 falla
       sólo si se agotan todas las filas de la línea;
    3. «A2/EE ≥ 3» y «K = 3» de C3a quedan como constantes fijas (`C3A_A2_EE`, `C3A_K`), no como el ajustable `E4P_A2_EE`;
    4. los «≥ 1.000 pares» de la calibración de E3t, la regla fina, T-P, A3 y A5 se leen como `U.f("E3_PARES_REGIMEN")`;
    5. los «|lat| ≤ 50°» de la regla fina, ρ, A5, C3a y C3b son constantes del cuerpo; sólo el de A3 está en el Anexo B.
- **`tipos.py`, cierre de la ola 1 (2026-10-24):**
  - quedaron implementados `Hipotesis.id`, `desde_id`, `orden` y `__post_init__` (valida tipo, desfase y zona),
    `ClaseH.id`, `ConsecuenciasRed.e4p_activa`, `fina_activa` y `modo_e3t_en`, `validar_esquema` y `tabla_vacia`. El diseño los
    asignaba a I3, pero el encargo de I3 no los incluía;
  - `modo_e3t_en` da restringido si A3 falla en el país o en la macrozona, si A4 restringe, o si la calibración no habilitó el
    modo completo;
  - la suite completa da 246 pruebas: 85 pasan, 161 omitidas y ningún fallo.
- **Ola 2, lanzada el 2026-10-24:** sintetico, extraccion, lineas_registro, lineas_fisicas, politica y decision. Después van
  guardas y red; luego orquestacion, salidas y C3; al final el ejecutable y la batería.

## Ola 2 cerrada (2026-10-24)

Seis módulos implementados: sintetico, extraccion, lineas_registro, lineas_fisicas, politica y decision. La suite da 290
pruebas: pasan todas las que corren y quedan 78 omitidas, de las olas 3 y 4. La Enmienda 1 quedó **adoptada y anclada** (APH
81bb100), así que ya no está pendiente lo que dependía de E1-1 a E1-7.

**Arreglos de integración (dueño: el agente de integración de la ola 3):**
1. `numerico.DESFASES_VENTANA = range(-9, 10)` debe leer `U.f("E3_VENTANA")`, y `digest()[:8]` debe usar `SEMILLA_BYTES`.
   `lineas_fisicas` ya pasa la ventana explícita.
2. `tablas.DIVISOR_REGION = 1000` debe usar `constantes.REGION_DIVISOR`.
3. En `tipos.ESQUEMA_MES`, `p_ts` y `p_qfe` pasan de Int8 a Int16: un paso mayor de 127 h no cabe.
4. En `test_umbrales.TOLERADOS` sobra la entrada `return hora % 3`, porque `lineas_registro` ya usa `E2_MODULO`. Quitar también
   las entradas que se arreglen en los puntos 1 y 2.
5. `tipos.EvidenciaEstacion` necesita un campo `clases` por año: `decision` lo lee si existe y, si no, lo recibe como argumento.
6. Unificar el paso nativo por mes. `lineas_fisicas.pasos_por_mes` repite `extraccion.paso_nativo`: dejar una sola regla.
7. `sintetico` no importa el paquete y copia los esquemas, con una prueba que los compara con `tipos`. Corregir la dependencia
   de §1 en DISENO_IMPLEMENTACION.md.

**Interfaces que deben respetar orquestacion, salidas, bateria y el ejecutable:**
- **decision:**
  - `insumos_anio` y `decidir_anio` reciben `clases=`;
  - `marca_reglas_vencidas` recibe `e4p_activa` y `fina_activa`;
  - hay campos nuevos `InsumosAnio.e4p_activa`, `InsumosAnio.fina_activa` y `ResultadoRachas.motivos_inestable`;
  - las guardas llevan `H = "*"` cuando no dependen de H;
  - la marca térmica es `"desfase_termico_local"`;
  - T-P queda `no_evaluable` cuando no se cumplen sus condiciones, y eso es lo que cuenta `red.a4`;
  - orquestación pone `reglas_vencidas` desde `marca_reglas_vencidas`.
- **politica:**
  - `tramos(clases=)` espera «AAAA» → (racha, clase confirmada);
  - `politica()` agrega `estaciones[código]["tramos"] = {id: veredicto}`, que va al addendum;
  - `ContextoVerificacion.no_normalizables`;
  - `artefactos_evaluados.json.gz` es una lista de objetos con al menos `artefacto_sha256` y `codigo`;
  - funciones nuevas: `veredictos_de` y `meses_muestra_lector_real`.
- **extraccion:**
  - extractos en `destino/extractos/dmc/` y `destino/extractos/era5/`;
  - después de `extraer_dmc` se llama a `marcar_coordenadas_inconsistentes(infos, catálogo, meses, U)`;
  - C2 recalcula la huella con `huella_agregada_manifiestos(listar_manifiestos(rutas.dmc), lambda p: entorno.alias(p, rutas))`.
- **lineas_fisicas:**
  - `cruce_isd(cat, isd, *, umbrales)`;
  - `ajustes_e4` acepta «HR», para G-HR;
  - `diagnostico_subhorario` existe, y `guardas.marca_media_horaria` puede delegar en ella;
  - `e3p_anual` devuelve filas con regla «unica»;
  - E4p usa «dudosa» cuando δ cae entre los dos umbrales.
- **lineas_registro:**
  - en E1b y E1c, la columna `resultado` usa textos propios;
  - `metricas` es None en E1;
  - el corte de las partes en las etiquetas de Cv le toca a `orquestacion`.
- **sintetico:**
  - `bateria.tabla_bateria` debe llamar a `sintetico.especificacion_bateria`, que genera 7.320 estaciones en 50 redes;
  - `correr_red` usa `caso_de_fila`, `serie_era5_de_casos` y los catálogos sintéticos;
  - el error «fuera de P» se juzga por año con `equivalentes_en_P`: Cv(Santiago) es igual a C(Santiago) en 2009 y en 2018
    ningún reloj de P coincide.

**Riesgos que requieren enmienda sólo si se activa la línea:**
- **E6 con reloj civil** (`lineas_fisicas`, punto 4): en un año con dos regímenes, la razón I12_H ≥ 5·I12_H′ frente a F(−3) o
  F(−4) nunca se cumple. E6 nunca podría apoyar un reloj civil. E6 está inactiva por omisión; si se activa, hace falta una
  enmienda antes de C4.

**Costos medidos:**
- ~6 ms por artefacto en extraccion;
- ~0,18 s por estación-año en lineas_fisicas;
- E1 + E2: ~0,2 s por estación;
- generación de la batería: ~0,65 s por estación (~1,3 h las 7.320 estaciones, sin el cálculo).

## Ola 3, integración (2026-10-24)

Hechos los siete arreglos de la lista «Arreglos de integración». La suite da 294 pruebas (4 nuevas): pasan todas las que
corren, quedan 78 omitidas y el detector de literales sigue en verde. No se tocaron `guardas.py`, `red.py` ni sus pruebas.

1. **`numerico`:**
   - la constante `DESFASES_VENTANA` desapareció. La ventana sale de `numerico.desfases_ventana(U)`, que lee
     `U.f("E3_VENTANA")`, y `lineas_fisicas.ventana` delega en ella;
   - `maximo_estricto(r, desfases)` e `interpolar_parabola(r, c_hat, desfases, c_max)` conservan nombres y orden, pero
     **la ventana ya no tiene valor por omisión**: si falta, Python lanza TypeError. Quien llame desde guardas, red o C3
     debe pasar `numerico.desfases_ventana(U)`;
   - la semilla toma sus bytes de `SEMILLA_BYTES`.
2. **`tablas.DIVISOR_REGION`** se lee de `REGION_DIVISOR`.
3. **`ESQUEMA_MES.p_ts` y `p_qfe` pasan a Int16:**
   - `extraccion._paso_para_meses` recorta con int16. Un mes con p de 128 a 743 h ahora guarda p en vez de <NA>; la
     consecuencia no cambia, porque p ∉ PASOS_NATIVOS;
   - **también se tocó `sintetico`**, lo mínimo: su copia de ESQUEMA_MES y el recorte de `_paso_nativo`. Sin ese cambio,
     `test_sintetico` falla al comparar los esquemas;
   - `lineas_fisicas` y `lineas_registro` no leen esas columnas: sólo validan el esquema;
   - prueba nueva: un paso de 168 h queda guardado.
4. **`test_umbrales.TOLERADOS`:**
   - salieron 4 entradas: `return hora % 3`, la ventana ±9, `digest()[:8]` y `DIVISOR_REGION = 1000`;
   - sigue pendiente `if n < 3` (Pearson), que no estaba en la lista;
   - prueba nueva, `test_tolerados_vigentes`: falla si queda una entrada que el detector ya no encuentra.
5. **`EvidenciaEstacion.clases`** (año → clases):
   - vale None por omisión;
   - `decision` lo lee cuando no recibe `clases=`, y si llegan los dos, manda el argumento;
   - `red` ya lo lee con `getattr` y es compatible;
   - **pendiente para `orquestacion`:** copiar ahí `ContextoEstacion.clases`.
6. **Paso nativo:**
   - la regla única es `numerico.paso_nativo`, con la definición de extraccion. `extraccion.paso_nativo` delega en ella, y
     `lineas_fisicas.pasos_por_mes` la aplica mes a mes y deja None si p ∉ PASOS_NATIVOS;
   - cambio en lineas_fisicas: las etiquetas que no son horas enteras ahora lanzan ValueError (antes daban None), y las
     repetidas se cuentan una vez. En extractos válidos el resultado es el mismo, porque extraccion exige HH:00 y el
     extracto no tiene duplicados;
   - la prueba nueva compara mes a mes los dos caminos y la regla anterior (en minutos) en 24 meses de Ts y QFE, con pasos
     de 1, 2, 3, 4, 6 y 168 h, empates, un solo valor, meses vacíos y huecos al azar.
7. **`DISENO_IMPLEMENTACION.md`:**
   - §1: `sintetico` no depende de nadie del paquete y queda fuera del grafo. Copia los esquemas, que `test_sintetico`
     compara con `tipos`, y recibe el descargador y el adaptador como argumento;
   - además se pusieron al día las firmas de `numerico` (`paso_nativo`, `desfases_ventana` y la ventana obligatoria), los
     campos de `EvidenciaEstacion` y la fila de `numerico` en §1.

**Pruebas nuevas:**
- `test_numerico.test_ventana_y_bytes_de_semilla_sin_literales`;
- `test_umbrales.test_tolerados_vigentes`;
- `test_decision.test_paso1_clases_desde_la_evidencia`;
- `test_lineas_fisicas.PruebasPasoNativo.test_paso_nativo_una_sola_regla`;
- además, aserciones nuevas en `test_extraccion.test_paso_nativo_y_empate`.

## Ola 3 cerrada (2026-10-24)

`guardas` y `red` quedaron implementados, y la integración también. La suite da 300 pruebas: pasan todas las que corren y
quedan 57 omitidas, de la ola 4 (orquestacion, salidas, controles_era5, verificar_reloj_dmc, bateria y la fachada).

**Texto vigente.** Las reglas son las del v1.0.1. La Enmienda 2 (`APH/auditoria/20261023/reloj_dmc/enmienda2/`) se ancla con
el M0 del producto meteorológico combinado. Sólo cambia una frase del texto propuesto en §7.5 para el punto 12 de la Enmienda
4 y el «Estado» del encabezado. No toca ningún umbral ni código.

**Interfaces de `guardas` que debe respetar orquestacion:**
- `desfase_termico_local(metricas_e3t, filtro_e3t, ctx)` es función aparte. `tp()` devuelve sólo las filas de guarda, y
  `marcas()` incluye la marca cuando T-P está activa. El valor de la marca es δt (la mediana de los δt_R) o None, y el umbral
  `DTL_DELTA_H` lo aplica `decision`.
- `g_hr(..., extracto=)` es obligatorio: cuenta las ≥ 1.000 horas con Ts y HR.
- `guardas()` y `marcas()` reciben `metricas` con las claves `"e3"`, `"e4"` y `"filtro_e3t"`. Lo que falte lo calculan con
  `lineas_fisicas`. Sólo corren lo que está en `ctx.lineas_activas`.
- G-versión toma el j* de `lineas_registro.e2` sobre los meses de cada versión, así que `resumen_por_version` exige el extracto
  anotado completo. **Dependencia nueva:** guardas → lineas_registro; hay que agregarla al §1 del diseño.
- Convenciones:
  - `H = "*"` en P7, G-versión y G-HR;
  - `unidad` «AAAA» en E3d, P7 y G-versión, y «R0»/«R1» en T-P y E4t;
  - T-P queda `no_evaluable` sin sus condiciones (filtro aprobado, ≥ 1.000 pares y ĉt_cont definido);
  - G-HR y G-viento toman True, False o None.
- Lecturas GU-1 a GU-9 en el encabezado del módulo. La que más pesa es GU-6b: G-versión compara dentro de cada año-régimen.
- **Para la batería y §8.F:** con las horas 00-03 corridas un día, E3d en Ts da Δr ≈ 0,07-0,16 frente al umbral de 0,10.
  Falló en las 12 semillas probadas (por Ts o por QFE), y P7 también, pero el margen es estrecho. E3d no tiene filas
  ajustables: si la batería exigiera moverlo, C1 falla.

**Interfaces de `red` que debe respetar orquestacion:**
- llamar a `fijar_a4` después de `a4`;
- pasar `meses_con_regla` a `describir_red`; sin eso nunca se afirma «Red en UTC»;
- no escribir la política si `a5_alto`;
- en `detalle["tablas"]` van DataFrames para los CSV; el resto del detalle es JSON sin NaN;
- argumentos opcionales nuevos:
  - `controles_red(..., calendario=None)` y `muestra_calibracion_e3t(..., calendario=None)`, para c_H(R) cuando la evidencia
    no trae `clases`;
  - `g_dup(..., zs_de=None)`;
  - `describir_red(..., meses_con_regla=None, sensibilidades_bateria=None)`;
- funciones nuevas `fijar_a4` y `a7`;
- esquemas propios en `red` (`ESQUEMA_MUESTRA_A3`, `ESQUEMA_MUESTRA_A5`, `ESQUEMA_CALIBRACION` y `ESQUEMA_GDUP`). Por la regla de
  §2 deberían vivir en `tipos`: queda para el integrador de la ola 4;
- lecturas RED-1 a RED-9 en el docstring.

**Pendientes que no tienen dueño todavía:**
- `red.predicciones` (§1.13): sus porcentajes (95, 90, 80, 10 y 1 %) no están en el Anexo B ni en `constantes`;
- el registro documental de C0 no trae `reloj_declarado` ni `alcance`, que A6 necesita para un D1. Hay que fijarlos antes de
  activar E5;
- el literal tolerado `if n < 3` de Pearson;
- `orquestacion` debe copiar `ContextoEstacion.clases` en `EvidenciaEstacion.clases`.

## Ola 4a cerrada (2026-10-24)

Se implementaron `orquestacion`, `salidas` y `controles_era5`. Cada uno pasó una revisión independiente que buscó refutar sus
hallazgos, y los arreglos aplicaron los que se sostenían: 4 mayores en salidas, 2 en orquestacion y 2 en controles_era5. La
suite da 355 pruebas: pasan todas las que corren, quedan 34 omitidas (del ejecutable, la batería y la fachada) y hay 1 falla
esperada (`test_ida_y_vuelta_aerodromo_tipo_d`, más abajo).

**Interfaces nuevas que debe respetar el ejecutable** (el detalle está en el encabezado de cada módulo):
- **orden:** `orquestacion.evaluar_red`, y luego `salidas.escribir_corrida(..., verificar=orquestacion.verificador_7_3(...))`.
  Así §7.3 y A7 quedan antes del informe y de `no_normalizables.csv`. `comprobar_politica` queda sólo para pruebas;
- **`escribir_corrida`** fuera del modo sintético recibe:
  - `meses = extraccion.leer_meses(destino)` y `artefactos = extraccion.leer_artefactos_evaluados(destino)`;
  - en `resultado.controles`, «A1» (`red.a1`), «A2» (`red.a2`) y «G-dup» (`red.g_dup`), que orquestacion no pone;
  - las huellas de entrada completas y sin None: `progreso`, `catalogo_dmc`, `era5l` y `copias_c2`;
  - `errata_post_c4=True` en una corrida `_ERRATA<n>`.
  Si falta algo, se niega a escribir. `modo_sintetico=True` va sólo con `--sintetico`, y queda declarado en el informe;
- **`orquestacion.FASES`:** «reglas_vencidas» pasa a ser «segunda_pasada». El avance ya no depende de los veredictos;
- **`OpcionesCorrida(conservar_etiquetas=True)`** para la batería;
- **controles_era5:**
  - `c3b` y `c3c` reciben `adaptador`, `huellas` y `fallas_era5`, arman la política en memoria y hacen la ida y vuelta;
  - `correr_c3` recibe `adaptador`;
  - el ejecutable comprueba, antes de C3, que no haya descargas activas, sin tocar nada bajo DMC;
  - C3 no se ha corrido sobre ERA5-Land real.

**Para la batería y §8.F (lo que más pesa para que C1 apruebe):**
1. **Falla esperada (tipo d):** con C(Santiago) en un aeródromo con cambio administrativo de horario (2016 y 2017), el año
   queda discrepante por «líneas en conflicto», porque la regla fina de E3p en R1 excluye al reloj verdadero. Puede ser un error
   de lineas_fisicas o del generador, o una propiedad del texto: hay que averiguarlo.
2. **T-P con el sesgo de referencia de +2,5 h:** falla en los 30 años F(0) con Ts y QFE, porque δt ≈ −2,5 h queda a 0,5 h de
   k = −3. A4 restringe, esos años quedan discrepantes y además entran al diagnóstico de reglas vencidas.
3. **Cv del generador** (regla anterior a 2008): 2010 difiere sólo del 14-mar al 3-abr, y la decisión confirma C(Santiago). Es
   una confirmación errónea por etiqueta, y el criterio de la batería exige cero.
4. **E3d:** margen estrecho (ola 3).
5. **Costo:** 0,25 s por estación-año de punta a punta, más ≈ 0,04 s de la segunda pasada. Una batería de 139.080
   estación-años lleva ≈ 11 h, bajo el tope de 48 h.

**Piden enmienda (no son errores de código):**
- **ORQ-10:** según el punto 16 de §8, un aeródromo UTC sin E4p se confirma con E3t completo. Pero el filtro de §4.3.3 exige
  días con ≥ 20 valores, y un aeródromo de 11 a 23 h nunca lo pasa. La prueba C.16b usa uno de 20 h.
- **ORQ-3f:** el diagnóstico de reglas vencidas no evalúa Cv en E6 (`lineas_fisicas.e6` no lo admite). Sólo importa si E6 se
  activa.

**Pendientes para el integrador de la ola 4b:**
- la fachada `reloj_dmc.py`;
- mover a `tipos` los esquemas propios de `red` y de `salidas`;
- las constantes de `red.predicciones` (§1.13);
- que `tablas` ofrezca como interfaz el corte de las partes en las etiquetas de Cv (hoy `_CalendarioConCortes` lee internos);
- compartir la regla del «reloj» de ORQ-7 entre orquestacion y salidas (SAL-11);
- llevar `controles["reglas_vencidas"]["lineas_sin_cv"]` a las desviaciones del informe;
- poner al día el Anexo F y el §1 del diseño (dependencias nuevas: orquestacion → extraccion y fijados; salidas → decision,
  politica y red; controles_era5 → fijados, politica y guardas).

## Ola 4b, integración (2026-10-24)

Hechos los siete puntos del encargo del integrador, en orden. Sólo se tocaron `reloj_dmc.py`, `tipos.py`, `red.py`,
`salidas.py`, `tablas.py`, `orquestacion.py`, `politica.py`, `constantes.py`, sus pruebas y estos dos documentos. No se
tocó `decision.py`: la regla del «reloj» quedó en `politica`.

**Suite completa:** 390 pruebas, OK, ninguna omitida y 2 fallas esperadas: `test_ida_y_vuelta_aerodromo_tipo_d` (ola 4a) y
`test_sintetico.test_reglas_vencidas_en_automatica_no_se_confirman` (de la investigación en paralelo). Tardó ≈ 11,6 min,
con otras suites corriendo a la vez. Una corrida anterior, mientras se editaba el ejecutable, dio 385 pruebas con 4 fallas:
tres de `test_verificar_reloj_dmc` y el detector de literales, por `verificar_reloj_dmc.py`. Ninguna era de esta ola, y en
la última no quedó ninguna. El detector de literales sigue en verde.

1. **Fachada `reloj_dmc.py`:**
   - perezosa: importarla no carga nada del paquete (ni numpy, pandas ni zoneinfo). Cada nombre se resuelve una vez con
     `importlib` y queda guardado; el objeto es el del módulo;
   - `NOMBRES_9` trae los 23 nombres en el orden de §9; `ALIAS_9 = {"e4": "e4p"}`; además `modulo_de(nombre)` y `__dir__`.
     Un nombre ajeno a §9 da AttributeError;
   - `test_reloj_dmc` lee los nombres de la viñeta «Código» de §9 del texto anclado en C0 (con su sha256), comprueba la
     identidad con cada módulo y prueba la pereza en un intérprete aparte (`-B -I`, que termina antes de seguir);
   - **índice de §8.** `test_indice_de_8_cada_punto_tiene_prueba` lee la numeración 1 a 28 de §8 en el texto y exige al
     menos una prueba «pNN» por punto (por AST de `tests/`, sin importar nada), y ninguna de un punto que §8 no tiene.
     `test_indice_de_8_sin_pruebas_por_implementar` exige que ningún punto dependa sólo de pruebas del esqueleto
     (`unittest.skip(POR_IMPLEMENTAR)`). Se omite, con la lista, mientras esos pendientes estén sólo en archivos de
     `EN_CURSO` (`test_verificar_reloj_dmc.py` y `test_bateria.py`); en otro archivo falla. **Al cerrar C1, `EN_CURSO`
     queda vacía.** En la última corrida p26 y p27 ya tenían pruebas y no se omitió;
   - en `test_tipos` se implementaron las cinco pruebas del esqueleto, más una de los esquemas movidos.
2. **Esquemas a `tipos`:**
   - llegaron `ESQUEMA_MUESTRA_A3`, `ESQUEMA_MUESTRA_A5`, `ESQUEMA_CALIBRACION`, `ESQUEMA_GDUP`, `ESQUEMA_EVIDENCIA_PARTE`,
     `ESQUEMA_EVIDENCIA_ANIO`, `ESQUEMA_NO_NORMALIZABLES` y `ESQUEMA_CALIBRACION_CSV`;
   - también los auxiliares de la evidencia por parte: `CLAVES_METRICAS`, `TIPO_CON_NULOS`, `VARIABLES_EVIDENCIA_E3`,
     `VARIABLES_EVIDENCIA_E4` y `COLUMNAS_EVIDENCIA_E2`, `_E3` y `_E4`;
   - `red` y `salidas` conservan los nombres como alias de los mismos objetos (`red.ESQUEMA_GDUP is tipos.ESQUEMA_GDUP`).
     El volcado JSON de los ocho esquemas antes y después es idéntico, byte a byte.
3. **`red.predicciones` (§1.13; lectura RED-10 en el encabezado de `red`):**
   - firma: `predicciones(evidencias, decisiones, *, consecuencias=None, calendario=None) -> dict`. Lo nuevo es de palabra
     clave, y orquestacion lo pasa (las consecuencias de la fase 7 y el calendario). Ya no hay `try/except
     NotImplementedError`;
   - siete constantes nuevas en `constantes.py`, con su fragmento literal y sección «§1». `tramo_de_seccion` no entiende
     «§1.13», porque §1 es una lista numerada. Son `PRED_E1A_PRESENTE_PCT` (95), `PRED_E2_CLASE_PCT` (95),
     `PRED_E3P_E4P_ANIOS_PCT` (90), `PRED_GUARDAS_FALLAS_PCT` (1), `PRED_F_MENOS4_PCT` (95, 95, 90), `PRED_CIVIL_E1A_PCT`
     (80) y `PRED_CIVIL_PLACEBOS_PCT` (10). Verificadas contra C0, v1.0.1 y v1.0.2; ahora son 80 constantes del cuerpo;
   - la clase de E2 y el ĉ esperados no se escriben: salen del reloj (j* = c_H(R) mód 3 con `lineas_registro.clase_mod3`, y
     ĉ = c_H(R)). Dependencia nueva: red → lineas_registro (también `id_evento` y `E1B_EVALUADO`);
   - salida: `{conjunto, nota, n_estaciones, n_estacion_anios, por_reloj}`, con un bloque por F(0), F(−4) y C(Santiago).
     Cada predicción trae `k`, `n`, `fraccion`, `minimo` o `maximo`, una `lectura` corta y su `resultado`: «cumplida»,
     «predicción no cumplida» o «sin_datos» (sin unidades evaluables). Va a `predicciones_1_13` del informe y nunca a las
     desviaciones;
   - el patrón civil de E1a no se recalcula: hay patrón si un evento ausente deja a C(Z) compatible en E1a, que
     `lineas_registro.e1a` sólo hace con el patrón (§4.1.1);
   - costo: ≈ 4 s para una red sintética de 579 estaciones × 19 años (0,36 ms por estación-año).
4. **Cortes en las etiquetas de Cv (`tablas`):**
   - interfaz pública: `TablasCalendario.con_cortes(cortes)`, `con_cortes_reglas_vencidas(zonas, anios)` y
     `tablas.intervalo_especial(cambio)`. El viejo `_intervalo` queda como alias;
   - `con_cortes` devuelve una copia del calendario y no lo toca. La copia tiene su propia memoria de regímenes, y sólo
     cambia `especiales_en`. Una zona sin Anexo A da KeyError, y un corte vacío, ValueError;
   - `orquestacion.diagnostico_reglas_vencidas` usa `con_cortes_reglas_vencidas`. `_CalendarioConCortes(base, cortes)`
     queda como función que delega en `con_cortes`, y `_intervalo_especial` es `tablas.intervalo_especial`. orquestacion
     ya no lee `_de` ni `_regimenes`;
   - **mismos resultados.** Un script comparó el envoltorio de la ola 4a, copiado tal cual, con la interfaz nueva en 238
     estación-años: los 7 territorios, cada año del Anexo A2 por separado y todos juntos, y el año anterior y el siguiente.
     Coinciden la anotación, los regímenes, las partes de cada mes y los desfases civiles. La prueba de orquestacion
     compara además las dos anotaciones.
5. **Regla del «reloj» (ORQ-7 y SAL-11):**
   - quedó en `politica.reloj_de_rachas(clases)`, porque es un campo de `estaciones` (§7.2) y allí viven los separadores.
     La usan `orquestacion._reloj_de_estacion` (las rachas con tramos) y `salidas._estacion_derivada` (las rachas
     aceptadas, sin política ni «estaciones»);
   - **cambio de comportamiento, sólo en ese caso de salidas.** Dos rachas aceptadas consecutivas que se intersectan daban
     «F(-3)|C(Santiago)→C(Santiago)» y ahora dan «C(Santiago)», como en ORQ-7. Los ids salen en orden canónico, y una clase
     con Cv o con miembros repetidos lanza ValueError. En orquestacion no cambia nada (las pruebas de ORQ-7 siguen igual).
6. **`lineas_sin_cv` a las desviaciones (SAL-22):**
   - `salidas.desviaciones_de_controles(controles)` da `DESVIACION_LINEAS_SIN_CV` si
     `controles["reglas_vencidas"]["lineas_sin_cv"]` no está vacía. `informe` la suma a las automáticas, después de las de
     SAL-21, y no repite una que ya trae el llamador con el mismo texto;
   - **choque con el ejecutable:** `verificar_reloj_dmc.py` (≈ l. 1488-1491) agrega su propia desviación, con otro texto.
     Con E6 activa saldría dos veces. Su dueño debe quitarla (salidas ya la agrega) o pasar
     `salidas.desviaciones_de_controles(resultado.controles)`.
7. **Diseño:**
   - §1: la tabla de módulos y el grafo con las dependencias reales, calculadas por AST de las importaciones `reloj_dmc.*`.
     Siete capas y ningún ciclo. `umbrales` no importa `entorno`, y `tablas` no importa `fijados`. salidas sólo nombra a
     orquestacion en anotaciones;
   - §3 y §5.2 al día. El Anexo F se regeneró por AST del código, y el script quedó en el propio anexo. Las notas de la ola
     3 pasaron al encabezado. `verificar_reloj_dmc`, `bateria`, `lineas_fisicas`, `sintetico` y `guardas` se editaban en
     paralelo: **al cerrar C1 hay que regenerar el anexo.**

**Pruebas nuevas o implementadas:**
- `test_reloj_dmc`: las cinco;
- `test_tipos`: las seis;
- `test_red.test_predicciones_1_13`, antes omitida;
- `test_tablas.test_con_cortes_en_las_etiquetas_de_cv`;
- `test_politica.test_reloj_de_rachas_regla_unica`;
- `test_salidas.test_h9_reloj_derivado_con_la_regla_de_orq7` y `test_h10_lineas_sin_cv_van_a_las_desviaciones`;
- aserciones nuevas en `test_orquestacion`: §1.13 de punta a punta en `test_p16_estacion_utc_da_f0_en_un_tramo` y la
  equivalencia de los cortes en `test_partes_cortadas_en_las_etiquetas_de_cv`.

**Lecturas para el addendum de C1:**
- RED-10, las predicciones de §1.13:
  - sólo N, y sólo los estación-años con veredicto distinto de «sin_datos»;
  - «E1a presente» cuenta los adelantos reales de todas las zonas de Zs;
  - «E3p con ĉ» exige ĉ = c_H(R) en todos los años-régimen con ĉ definido, y para F(0) además E4p anual compatible;
  - «aeródromo de operación civil» es una estación con algún cambio real de E1b evaluado con |δ| = 1;
  - las guardas son las de §5.1 y G-versión, precalculadas bajo H o «*»;
  - «placebos ≤ 10 %» se cuenta con los placebos de las estaciones evaluables, juntos;
  - la regla fina se mira sólo donde rige (A3 y apagado de estación);
  - **sin porcentaje en el texto** (E1b, la E2 civil y la fina), la predicción es universal: la cumplen todas las
    unidades evaluables. La otra lectura sería no juzgarlas. Ninguna tiene consecuencias.
- SAL-11, con la regla única del «reloj», y SAL-22, ya descritos.
- ORQ-3b ya no lee internos de tablas. La lectura no cambia.

**Pendientes (para sus dueños):**
- la desviación de `lineas_sin_cv` duplicada en el ejecutable (punto 6);
- BAT-12: `bateria.py` define tres constantes del cuerpo de §8.D en `CONSTANTES_BATERIA`, fuera de `constantes.py`. Si
  se mueven, `constantes.verificar_contra_texto` las cubre con las demás. Hay que coordinarlo con su dueño, para no
  duplicar nombres;
- siguen de la ola 3: `reloj_declarado` y `alcance` en el registro documental (A6, antes de activar E5) y el literal
  tolerado `if n < 3` de Pearson;
- regenerar el Anexo F al cerrar C1 y vaciar `EN_CURSO` en `test_reloj_dmc`.

## Ola 4b cerrada (2026-10-24)

El ejecutable, la batería, la fachada y la integración quedaron implementados, y la investigación de los riesgos terminó.
Cada parte pasó una revisión adversarial y su arreglo. La suite da 417 pruebas: OK, ninguna omitida y 1 falla esperada
(`test_ida_y_vuelta_aerodromo_tipo_d`, que depende de E3-1). El código de C1 está completo. **C1 no puede aprobar todavía.**

**Enmienda 2 del reloj (anclada con M0 del producto meteorológico, APH `e8141e4`; texto v1.0.2 `ee5dec6e…`):**
- E2-1 y E2-2 tocan textos (§7.5 y el encabezado);
- **E2-3:** sin política válida no hay producto, y rige §2.1 del producto;
- **E2-4:** en C5, la huella de la política va a `APH/auditoria/<fecha de C5>/meteo_combinada/registro_politica_reloj.json`
  (el sha256 de la política y de `artefactos_evaluados`, y el commit de C5), no a `insumos_tardios_v3.jsonl`. **El
  ejecutable o las salidas de C5 deben escribir ese archivo.**
- El addendum de C1 cita la huella del v1.0.2.

**Lo que impide aprobar C1** (detalle en `PROPUESTA_ENMIENDA_3.md`, que corrigió la revisión):
1. **E3-2:** una automática con hora civil y la regla anterior a 2008 se confirma F(−4), y C1 exige cero confirmaciones
   erróneas. §8.F no lo puede arreglar. Viene del texto **y** de la lectura R-52 [D] («informativo» por H en E3p anual).
   Opciones:
   - A′: eventos de regla vencida en E1a, sin umbrales nuevos, no medida de punta a punta;
   - R: «informativo» por año-régimen, medida: 15 errores → 0, pero C.21 queda insuficiente y §8.21 necesita enmienda;
   - C: regla fina por parte, con un umbral nuevo.
2. **E3-1:** en estaciones con ventana diurna (tipos c y d) la regla fina queda sesgada hasta ±1,7 h. Se arregla ajustando el
   armónico de sp para cada c (+7 % de costo). Es una enmienda o una lectura de R-23 [D]. De esto depende la falla esperada.
3. **E1c en Pascua:** con Zs de dos zonas cuyos adelantos caen en el mismo mes, todas las H quedan incompatibles, y
   C(Pacific/Easter) del tipo b queda discrepante en 18 de 19 años. La revisión dice que es la lectura R-10 aplicada zona por
   zona: basta corregir la lectura.
4. **BAT-5** (confirmación correcta ≥ 90 %): con la lectura literal (195 celdas, la que decide hoy) es probable que falle aunque
   las confirmaciones erróneas lleguen a cero.

**Lecturas que debe decidir el autor** (en el encabezado de cada módulo): VER-1 a VER-16 del ejecutable (formato del
addendum y de la línea de cierre, rutas del protocolo, corrida confirmatoria, errata, descargas activas y qué es C1 aprobado);
BAT-2 a BAT-13 de la batería; las predicciones de §1.13 sin porcentaje; E3-3 (no cambiar T-P) y E3-4 (aclarar el punto 16).

## Enmienda 3 implementada (2026-10-24)

El autor adoptó la Enmienda 3 del procedimiento el 2026-10-24
(`APH/auditoria/20261023/reloj_dmc/enmienda3/decisiones_autor_20261024.md`, la única autoridad). Este paso es **el
código**. El texto de la enmienda, el consolidado v1.0.3 y el `anexo_a3_reglas_vencidas.json` los escribe otro agente
en esa carpeta; aquí no se tocó ningún texto de APH. Texto vigente al implementar: v1.0.2 (`ee5dec6e…`). Todo se hizo
con datos sintéticos: nada bajo DMC ni bajo /Volumes, sin red, sin git que escriba y sin `__pycache__`.

**Qué se portó y de qué copia medida** (copias en el scratchpad de la sesión, `enmienda3/`; `diff -ru` contra `base`,
que era idéntica al paquete real):
- **E3-2, A′ con el patrón POR REGLA VENCIDA.** La copia `A_prima_mas_E3_1_y_Pascua` evalúa el patrón **por grupo**
  (regla anterior a 2008 y Anexo A2; tabla `32c6c311…`), no por regla. La partición por regla, que es la que eligió el
  autor, se tomó de la copia `A_prima` (la variante «por regla» medida sola). El juez midió que las dos particiones dan
  lo mismo en la batería. Las h0 por zona son las mismas de la copia combinada (comparadas zona por zona).
- **E3-1:** de `A_prima_mas_E3_1_y_Pascua` (`lineas_fisicas._series_unidad` y la serie filtrada una vez por unidad).
- **Pascua (E1c, R-10 por mes):** con la formulación de `E3_1_y_Pascua` (`MOTIVO_OTRA_ETIQUETA`: la H con otra etiqueta
  inexistente en el mes queda sin información), no con la de la combinada, que dejaba C_venc incompatible.
- **R:** de la copia `R` (`lineas_fisicas.e3p_anual`, y la simulación de `test_decision`).
- **B6:** de `juez/combo_B6`, pero sin los literales `1.0` y `−0.5` que traía: usa `numerico.media_circular_en` con el
  intervalo `A5_ENVOLVER`, la misma función que el m de A5 (`red._m_circular` delega en ella).
- **BAT-5 y BAT-8:** nuevos en `bateria`.

**Por módulo:**
- `tablas`: el **Anexo A3**. `fechas_reglas_vencidas` (domingos de America/Santiago desde la regla anterior a 2008 y
  las filas de adelanto del A2, una regla por domingo; dos reglas para un mismo domingo dan ErrorTablas),
  `TablasCalendario.eventos_reglas_vencidas(zona, año)` → `(Cambio, regla)`, `anexo_a3(cal)` (las cuatro zonas,
  2000-2026, en orden UTC), `serializar_anexo_a3` y `SHA_ANEXO_A3 = d7cd33e1363edb17f3fe5df9d59cf978bf6b522f218f9be82b59e73bb29ed092`
  (tzdata 2026c). `verificar_tablas` la exige y `TablasCalendario.sha256_anexo_a3` la calcula. 21 eventos en Santiago,
  Coyhaique y Pascua y 19 en Punta_Arenas, en 4 reglas; ninguno en 2008-2010.
- `red`: `a2(sha_a, sha_a2, sha_a3)`, con la huella del A3 obligatoria en el control A2 (`detalle["anexo_a3"]`);
  `verificar_reloj_dmc` la pasa en sus dos llamadas. En §1.13 los eventos «regla_vencida» no son placebos (RED-10).
- `tipos`: `ClaseEvento.REGLA_VENCIDA`.
- `lineas_registro`: E1a evalúa los eventos de regla vencida con «presente» y «ausente»; `_patrones_regla_vencida`
  (por regla, con los umbrales del patrón civil); reloj anómalo en las filas anuales de los años con un evento ausente de
  una regla con patrón; `patron_regla_vencida(estados)`. E1c con R-10 por mes (`_etiquetas_adelanto_del_mes`,
  `_estados_mes_e1c`).
- `decision`: `rachas(…, patron_regla_vencida=False)`, la tercera condición de §5.3.1 (motivo «civil con reglas
  vencidas»). `orquestacion` (ORQ-13) se la pasa.
- `lineas_fisicas`: E3-1 en `_series_unidad`; R en `e3p_anual`; B6 en `diagnostico_subhorario(metricas, ctx)`, que ya no
  recibe los años confirmados (tampoco `guardas.marca_media_horaria(metricas, ctx)`). `orquestacion` calcula la marca,
  como antes, sólo en estaciones con algún año confirmado.
- `numerico`: `media_circular_en(x, intervalo)`.
- `bateria`: **BAT-5** decide la lectura estrecha a ≤ 50° S, por estación-año (`_celdas_correcta_estrecha_50`: la
  estrecha y |lat| ≤ `FINA_LAT_MAX`, el límite de la regla fina; 52 celdas). Al lado informa `lectura_literal` (195
  celdas) y `lectura_estrecha` sin acotar (56). **BAT-8** «sin error de ubicación» (`_cambio_ubicado`): 2018 sin
  confirmar, ningún año erróneo y cada cambio detectado contiene 2018 sin años confirmados dentro; la estricta anterior
  se informa en `mal_ubicadas_lectura_estricta`.
- `DISENO_IMPLEMENTACION.md`: R-10 con la nota de E1c, R-23 y R-52 marcadas como reemplazadas por la enmienda (salen de
  las lecturas [D]) y el **Anexo F regenerado** con su propio script.

**Anexo A3: serialización y cómo se compara.** Una sola serialización: `{zona: [[h0 «AAAA-MM-DDTHH:MM», regla], …]}`,
con las zonas como claves ordenadas, los eventos de cada zona en orden UTC, separadores «,» y «:», `ensure_ascii=False`,
UTF-8 y sin salto final. Para comparar un archivo generado aparte, desde `scripts_modelo_1km`:

```
~/micromamba/envs/amb_v2/bin/python -B -c "import hashlib, json, sys; from reloj_dmc import tablas; \
b = tablas.serializar_anexo_a3(tablas.anexo_a3(tablas.cargar_tablas())); a = open(sys.argv[1], 'rb').read(); \
print(a.rstrip(b'\n') == b, json.loads(a) == json.loads(b), hashlib.sha256(b).hexdigest())" <ruta del json>
```

Los bytes (sin un salto final, si lo trae) deben ser idénticos y dar `d7cd33e1…`; si el archivo usa otro espaciado,
basta con que los dos `json.loads` den el mismo objeto, y la huella que se ancla es la de estos bytes.
**Comparado** el 2026-10-24 con `APH/auditoria/20261023/reloj_dmc/enmienda3/anexo_a3_reglas_vencidas.json` (del otro
agente, sólo leído): 3.890 bytes idénticos a los de `serializar_anexo_a3`, el mismo objeto JSON y la misma sha256
`d7cd33e1…`, que es también la que cita el v1.0.3 en §5.4 (A2) y en el Anexo A3.

**Lecturas nuevas en los encabezados** (para el addendum):
- `lineas_registro`, lectura 9 (A′: una etiqueta que ya es placebo va una vez; placebos de semana que caen en un evento
  no cuentan; reloj anómalo en todas las H; «patrón» = «E1a anómala en algún año»; sin marca de §4.1.4 en esos años) y
  lectura 10 (**E1c en Pascua**, R-10 por mes).
- `tablas`: h0 del Anexo A3 por zona (adelanto real movido o placebo del A2, y sólo si existe bajo la vigente).
- `lineas_fisicas`: LF-2 y LF-15 (E3-1), LF-17 (R; R-52 sale de las [D]) y LF-18 (B6, que el v1.0.3 llama E3-5).
- `orquestacion`: ORQ-6 (B6) y ORQ-13. `red`: RED-10 y RED-3 (la misma función que B6). `decision`: la tercera condición.
- `bateria`: BAT-5 (E3-6 del texto: estrecha a ≤ 50° S, por estación-año, decidida viendo la batería sintética, no datos DMC) y **BAT-8**
  («sin error de ubicación», decidida igual; afloja la lectura anterior). BAT-6 sigue igual (en vacío, n = 0).
- `guardas` (GU-10) y `sintetico`: notas al día (E3-3 sin cambio; el generador no cambia).

**Pruebas:**
- C.21 (`test_orquestacion.test_p21_parte_menos4_en_anio_utc`) con la expectativa nueva de §8.21: sin E6, insuficiente
  y ningún mes con regla; con E6, F(0) con marzo sin regla; con dos partes, discrepante.
- Testigos reemplazados: `test_reglas_vencidas_en_automatica_se_confirman_f_menos4_con_texto_anclado_y_r52` →
  `test_reglas_vencidas_en_automatica_no_se_confirman` (también con un solo año, donde basta R);
  `test_regla_fina_sesgada_en_ventana_parcial_texto_anclado` → `test_regla_fina_exacta_en_ventana_parcial_con_e3_1`.
- `test_ida_y_vuelta_aerodromo_tipo_d` **sin expectedFailure**. Ojo: con R, 2016 solo ya no se confirma (R1 corto y no
  fino, |ĉ^f_cont − ĉ^f| ≈ 0,3 h, cuenta para C(Santiago) y E3p no apoya): es el costo de R en los aeródromos que el juez
  midió. La prueba pasa a 2016-2018: 2016 y 2017 insuficientes («apoyo»), sin exclusiones del reloj verdadero; 2018
  confirmado C(Santiago); ida y vuelta.
- A′ por regla: `test_lineas_registro.test_p08_e1a_enmienda_3_eventos_y_patron_de_reglas_vencidas`,
  `test_decision.test_enmienda_3_patron_de_reglas_vencidas_deja_la_estacion_inestable`,
  `test_sintetico.test_reglas_vencidas_a_prima_patron_por_regla_y_estacion_inestable`, `test_tablas.test_enmienda_3_anexo_a3_eventos_de_regla_vencida`,
  la aserción de §1.13 en `test_red` y `test_orquestacion.test_reglas_vencidas_diagnostico_sin_marca_y_patron_de_regla_vencida`
  (antes `…marca_y_no_cuenta_para_la_inestabilidad`).
- R: `test_lineas_fisicas.test_e3p_anual_r52_informativo_por_h` y `test_e3p_anual_gruesa_y_fina`, C.21 y la prueba de
  reglas vencidas con un solo año.
- B6: `test_lineas_fisicas.test_diagnostico_subhorario_marca_con_6_anios_regimen` (circular, la misma función que A5),
  `test_guardas.test_p12_marca_posible_media_horaria` y, de punta a punta,
  `test_orquestacion.test_b6_marca_de_media_horaria_con_un_solo_anio_confirmado` (un solo año confirmado y la marca).
- Pascua: `test_lineas_registro.test_e1c_pascua_r10_mes_por_mes`.
- BAT-5 y BAT-8: `test_bateria.test_d_confirmacion_correcta_estrecha_a_50_S` y `test_d_cambio_2018_sin_error_de_ubicacion`.
- A2: `test_red.test_a2_desde_huellas` con la huella del A3.

**Umbrales:** ninguno nuevo ni escrito a mano. Los 50° de BAT-5 son `FINA_LAT_MAX`; los de B6, `SUBH_LAT_MAX`, `SUBH_RHO_H`
y `SUBH_MIN_REGIMENES`; el período y el intervalo, `A5_ENVOLVER`. `umbrales.py` y `constantes.py` no cambiaron.

**Suite completa** (`~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .`, desde
`scripts_modelo_1km`, un hilo numérico): **423 pruebas, OK**, en 277 s; ninguna falla, ninguna falla esperada y ninguna
omitida. El detector de literales (`test_umbrales.test_sin_literales_de_umbral_en_modulos` y `test_tolerados_vigentes`)
sigue en verde, sin entradas nuevas en TOLERADOS.

**Pendientes:**
- Antes de sellar C1, la batería completa con las réplicas 11 a 20 de D1 (decisión del autor); si aparece una
  confirmación errónea, rige §8.F. El riesgo que nombró el juez sigue: Cv × c y d con 30 % faltante, protegidas sólo por la
  primera condición de §5.3.1.
- Anclar `SHA_ANEXO_A3` con la enmienda (los bytes ya coinciden con el `anexo_a3_reglas_vencidas.json`; arriba).
- ~~Cuando las constantes se verifiquen contra el v1.0.3 (hoy se verifican contra el texto de C0 y el v1.0.1): comprobado
  con `constantes.verificar_contra_texto`, sólo el fragmento de `SUBH_LAT_MAX` («de los años confirmados con |lat| ≤ 50°
  y ĉ^f_cont definido», §4.3.5) deja de estar en el v1.0.3, por B6. Las de `CONSTANTES_BATERIA` siguen. No se cambió,
  porque el texto de C0 no trae la frase nueva.~~ Resuelto en «Revisión de la Enmienda 3: arreglos», abajo: las
  constantes se verifican contra las cuatro versiones y la vigente.
- La huella del A3 no está en las «huellas de entrada» de `salidas` (`CLAVES_HUELLAS`, §7): sólo en el control A2. Si el
  informe debe citarla, lo decide el dueño de salidas.
- `PROPUESTA_ENMIENDA_3.md` sigue diciendo «borrador»: es un registro; no se tocó.
- Siguen los pendientes de la ola 4b (EN_CURSO de `test_reloj_dmc`, la desviación duplicada de `lineas_sin_cv`, BAT-15).

## Revisión de la Enmienda 3: arreglos (2026-10-24)

Una revisión independiente del código de la Enmienda 3 dejó cuatro hallazgos menores. Se aplicaron los tres que se
sostienen, cada uno con una prueba que falla sin el arreglo, y se rechazó uno con su motivo. Para comprobar las
fallas se revirtió cada arreglo por separado en una copia del paquete en el scratchpad, con APH enlazado sólo para
leer: las cuatro pruebas fallan y la copia sin revertir pasa. La carpeta `APH/auditoria/20261023/reloj_dmc/enmienda3/`
sólo se leyó. Nada bajo DMC ni /Volumes, sin red, sin git que escriba y sin `__pycache__`.

**1. Constantes del cuerpo contra el texto vigente (aplicado).**
- **Hallazgo.** El fragmento de `SUBH_LAT_MAX` ya no está en el v1.0.3. Las constantes del cuerpo sólo se
  verificaban contra el texto de C0, y las de la batería contra C0 y el v1.0.1. Los fijos nuevos del cuerpo
  («≥ 20 valores» de §8.16, «a ≤ 50° S» de §8.D) no estaban en ninguna lista. Se sostiene: E1-5 (Anexo B) pide el
  texto vigente, y `ENMIENDA_3.md` pide regenerar el anexo B2 desde el v1.0.3.
- **`constantes`:**
  - `TEXTOS_PROTOCOLO` (versión, ruta en APH y sha256 de v1, v1.0.1, v1.0.2 y v1.0.3), `VERSIONES_TEXTO`,
    `VERSION_VIGENTE` (la última, v1.0.3) e `indice_version`;
  - `ConstanteTexto` tiene dos campos nuevos: `desde` (la primera versión con el fragmento) y `fragmento_anterior`,
    además del método `fragmento_en(version)`;
  - `verificar_contra_texto(texto, version=VERSION_VIGENTE)` busca cada constante con su fragmento de esa versión y
    salta las que nacen después. Una versión desconocida lanza ValueError;
  - `SUBH_LAT_MAX` lleva el fragmento del v1.0.3 («en todos los años-régimen de la estación con |lat| ≤ 50° y
    ĉ^f_cont definido»), con `desde="v1.0.3"` y el de antes para C0, v1.0.1 y v1.0.2;
  - seis constantes nuevas, con `desde="v1.0.3"`:
    - `E1A_RV_MIN_AUSENTES` y `E1A_RV_AUSENTES_PCT` (§4.1.1, patrón de regla vencida);
    - `SUBH_MEDIA_CIRCULAR` (§4.3.5: período 1 h e intervalo [−0,5; 0,5));
    - `DISCREPANCIAS_PARTES` (fila de §5.5), `DIURNOS_DIA_MIN_VALORES` (§6) y `C16_DIA_MIN_VALORES` (§8.16).

    Repiten umbrales de otras secciones y ningún módulo las lee. Una prueba exige que coincidan con los que sí se
    leen: los del patrón civil, con E1A_P0 y E1A_PLACEBO como ajenos; A5_ENVOLVER; ANUAL_MIN_PARTES;
    E3T_DIA_MIN_VALORES y E4_DIA_MIN_VALORES. Ahora son 86.
- **`bateria`:** `BATERIA_CORRECTA_LAT_S` = 50 (§8.D, «a ≤ 50° S», E3-6; el 90 % que cita es BAT_CORRECTA_PCT,
  como ajeno). BAT-5 lee este límite y ya no `FINA_LAT_MAX`. El valor y las 52 celdas no cambian, pero la frase que
  rige es la de §8.D.
- **Pruebas:**
  - `test_umbrales.PruebasConstantesPorVersion` (3): las huellas de las cuatro versiones (la primera es la de C0 de
    `umbrales`); `verificar_contra_texto` sin problemas en cada versión y en la vigente; las repeticiones coinciden;
  - `test_bateria.PruebasConstantesDelCuerpo`: `CONSTANTES_BATERIA` contra las cuatro versiones, y
    `test_fijos_nuevos_del_cuerpo_en_cada_version`. Ésta exige que cada comparación numérica de las líneas del cuerpo
    que una versión agregó o cambió caiga dentro del fragmento de alguna constante: ≥, ≤, <, > o «menos de» seguidos
    de un número, sin los nombres de reglas entre «…». Las Enmiendas 1 y 2 no dejaban ninguna fuera. La 3 dejaba
    10, y las cubren las constantes nuevas;
  - `test_bateria.test_d_confirmacion_correcta_lee_la_latitud_de_8D`: si sólo cambia el límite de §8.D, cambian las
    celdas que deciden; si sólo cambia `FINA_LAT_MAX`, no.
- **Huella del v1.0.3.** Durante este paso el otro agente reescribió la frase de §8.D: entran D1 sin perturbación y
  D2 con sólo el sesgo, y D3 no. La huella pasó de `9b9b08b0…` a `7a019348…`, que es la que hoy cita
  `ENMIENDA_3.md`, y `TEXTOS_PROTOCOLO` lleva esa. La aclaración coincide con lo que BAT-5 ya hacía. Si el texto
  cambia otra vez antes de anclarse, las pruebas fallan a propósito: hay que revisar los fragmentos y después poner
  la huella nueva.

**2. La prueba unitaria de §8.21 (aplicado).**
- **Hallazgo.** `test_decision.test_p21_parte_menos4_en_anio_utc` no distinguía R de la lectura por H: usaba la
  simulación de `e3p_anual` y años-régimen compatibles con F(0). Además esperaba lo que decía el v1.0.2. Se sostiene:
  con la simulación anterior (por H) también pasaba.
- **Arreglo:**
  - la prueba vieja pasa a llamarse `test_parte_discordante_con_anio_regimen_compatible` (§4.0, sin pNN). Su
    docstring dice por qué no distingue las lecturas;
  - la nueva es `test_decision.PruebasP21.test_p21_parte_menos4_en_anio_utc`:
    - usa `lineas_fisicas.e3p_anual` real, sin la simulación;
    - la gruesa pasa por `estados.anual_por_partes`, como la entrega `lineas_fisicas.e3`;
    - la premisa es la de §8.21: R0 residual para F(0) e incompatible para las rivales;
    - espera los cuatro casos del v1.0.3. Sin E6, el año queda insuficiente («apoyo») y sin meses con regla. Con
      E6, se confirma F(0) con E4p y E6, y marzo queda sin regla. Con dos partes, queda discrepante, con o sin E6;
  - con el `e3p_anual` de la copia anterior a la Enmienda 3 (por H), la prueba falla porque el año sale confirmado.
    La de §4.0 pasa con las dos lecturas. LF-17 y el índice del diseño (C.16-23) citan la prueba nueva.

**3. La marca «posible media horaria» sólo en estaciones con años confirmados (rechazado).**
- **Motivo.** No es una condición que el texto no ponga:
  - §7.2 lleva «marcas» sólo en las entradas «confirmada», que tienen tramos;
  - un tramo sale de meses con regla, y sólo los años confirmados los dan (`decision.rachas`, punto 5);
  - una estación sin años confirmados queda «sin_confirmar», sin «marcas», en la política, en el informe
    (`salidas._estaciones_informe`) y en la entrada derivada de SAL-11;
  - la batería lee False porque falta «marcas», con la condición o sin ella.

  El valor que la condición evita calcular no llega a ninguna salida, así que ninguna prueba puede distinguir los
  dos códigos. Tampoco es una lectura para el addendum. Se aclaró la redacción de ORQ-6, LF-18 y el comentario del
  código, sin cambiar el comportamiento.

**4. La cita de la lectura de E1c en Pascua (aplicado).**
- `test_e1c_pascua_r10_mes_por_mes` cita ahora la «Lectura 10».
- La prueba nueva es `test_lineas_registro.PruebasCitasDeLecturas.test_citas_de_lecturas_con_su_numero`. Cada
  «Lectura N (…)» de ese archivo, y cada «lineas_registro, lectura N» de las demás pruebas, debe nombrar una lectura
  del encabezado del módulo. Si la cita trae un paréntesis, su texto debe estar en esa lectura.

**Anexo F:** se regeneró con su script y sólo cambia `constantes`. En §1 del diseño, `constantes.py` ahora dice 86.

**Suite completa** (`~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .`, desde
`scripts_modelo_1km`, un hilo numérico): **430 pruebas, OK**, en ≈ 280 s, sin fallas, sin fallas esperadas y sin
omitidas. Son las 423 de antes y 7 nuevas: 3 de test_umbrales, 2 de test_bateria, 1 de test_decision y 1 de
test_lineas_registro. El detector de literales sigue en verde, sin entradas nuevas en TOLERADOS: el 50 y el 90 de
`BATERIA_CORRECTA_LAT_S` llevan la marca «no-umbral» con su motivo, como el 0,5 de `BATERIA_SEMANTICA_H`.

**Pendientes:**
- Al anclar la Enmienda 3, la huella del v1.0.3 en `constantes.TEXTOS_PROTOCOLO` debe ser la anclada.
- El anexo B2 del addendum (fijos del cuerpo, E1-5) se genera de `constantes.CONSTANTES` y
  `bateria.CONSTANTES_BATERIA` (86 + 4), con su fragmento en el v1.0.3. La prueba de completitud mira sólo las líneas
  que cambia cada enmienda. Aplicada al cuerpo entero del v1.0.3, su regla deja 113 de 175 comparaciones sin
  fragmento propio. Muchas repiten valores del Anexo B, que E1-5 no pide listar. Revisar el cuerpo entero queda
  para el addendum.
- Siguen BAT-12 (mover `CONSTANTES_BATERIA` a `constantes.py`) y los pendientes de la ola 4b y de la Enmienda 3: la
  batería completa con las réplicas 11 a 20 de D1, `EN_CURSO`, la desviación duplicada de `lineas_sin_cv` y BAT-15.

## Enmienda 4 y accesos a /Volumes (2026-10-25)

La primera corrida completa de `--sintetico --bateria` duró del 2026-10-24 a las 19:17 al 2026-10-25 a las 04:49, con el v1.0.3
y 430 pruebas aprobadas. No aprobó C1 por dos motivos:
- **«lo indecidible»:** 8 estación-años correctos del tipo f en C(Coyhaique);
- **7 accesos bajo /Volumes,** negados y fuera de las guardas propias de las pruebas.

Las salidas están en `LOCAL/modelado_1km/verificacion_reloj_dmc/v1/c1/` y la bitácora en
`~/Asesorias_Data_local/_herramientas/reloj_c1/bateria_c1_20261024.log`. Nada se hizo con datos DMC, con la red ni con git
que escriba, y nada se escribió en /Volumes.

**1. La Enmienda 4 del reloj (E4-1, texto v1.0.4; aplicado).** Es la cuarta del reloj, no la del prerregistro agudo.
- **Textos,** en `APH/auditoria/20261023/reloj_dmc/enmienda4/`:
  - `ENMIENDA_4.md`, con la decisión literal del autor («Enmendar §8.D (Recomendado)»), «a ciegas», huellas, motivo,
    efecto y la declaración de que se decidió viendo la batería sintética;
  - `generar_v1_0_4.py` (`3fb5c85f…`);
  - `PROTOCOLO_RELOJ_DMC_v1.0.4.md` (`d8f61cfc…`);
  - `texto_7_5.md` (`58362640…`, idéntico al del v1.0.3).
- **Texto nuevo de §8.D:** «lo indecidible (tipo e, Pascua y Juan Fernández) queda sin confirmar; el tipo f puede
  confirmarse, y toda confirmación errónea suya cuenta como tal [Enmienda 4, E4-1].»
- **El diff del v1.0.3 al v1.0.4** tiene 3 bloques: el encabezado y el Estado (2 líneas), la viñeta de §8.D y una entrada del
  registro de revisión. Los Anexos A, A2, A3, B y C son byte a byte los del v1.0.3: el Anexo B da `922208dd…` en los dos. Lo
  comprueba el generador y lo repetí con `diff` y `cmp`.
- **`bateria.py`:**
  - `TIPOS_INDECIDIBLES = ("e",)`;
  - `FRAGMENTO_INDECIDIBLE`, con la frase nueva;
  - `TIPO_SEIS_HORAS = "f"`;
  - el criterio 7 informa además `tipos` y `tipo_f` (estación-años, confirmados, correctos, erróneos y celdas);
  - BAT-7 reescrita; el diagnóstico estrecho usa la misma lista.
  - Las confirmaciones erróneas del tipo f siguen contando en «cero erróneas» (BAT-2), sin cambio de código.
- **`constantes.py`:** el v1.0.4 entra en `TEXTOS_PROTOCOLO` y es el vigente. Ningún fragmento de `CONSTANTES` ni de
  `CONSTANTES_BATERIA` cambia, porque la frase no tiene números.
- **Pruebas nuevas:**
  - `test_bateria.test_d_tipo_f_puede_confirmarse`. La correcta del tipo f pasa; con la lista del v1.0.3 falla. La errónea
    hace fallar «cero erróneas» y no lo indecidible. El tipo e sigue en la lista.
  - `test_bateria.test_d_lo_indecidible_es_la_frase_de_8D`. La frase está en §8.D del v1.0.4, y la anterior en C0 a v1.0.3.
- **Pruebas que fijaban el texto anterior:**
  - `test_bateria.test_fijos_nuevos_del_cuerpo_en_cada_version` exige ahora ≥ 10 comparaciones nuevas en el v1.0.3 y 0 en el
    v1.0.4 (antes, ≥ 10 en la vigente);
  - `test_umbrales.PruebasConstantesPorVersion` lee cinco versiones y comprueba que ningún fragmento cambie del v1.0.3 al
    v1.0.4;
  - `test_d_sin_cruces_y_cambio_2018_ubicado` no cambia de lógica: probaba e, Pascua y Juan Fernández; sólo cambia su
    docstring.
- **`DISENO_IMPLEMENTACION.md`:** la viñeta del criterio, en la lista de la batería.

**2. Los 7 accesos a /Volumes (aplicado).**
- **Rastreo.** Corrí la suite completa bajo `RegistroAccesos((/Volumes,), bloquear=True)`, como `--sintetico`, y anoté la
  ruta, la prueba y la pila de cada acceso. El guion está en el scratchpad de la sesión, fuera de los repositorios. Dio los
  mismos 7 accesos y los mismos 11 negados por las pruebas:

  | Prueba | Módulo | Accesos |
  |---|---|---|
  | `test_red.PruebasControles.test_g_dup_lista_casos` | `red._bajo_volumes` (desde `g_dup`) | `os.lstat` de /Volumes, /Volumes/Datos y /Volumes/Datos/progreso.json, y `os.stat` de …/progreso.json |
  | `test_sintetico.PruebasSintetico.test_formato_real_por_run_download` | `sintetico._exigir_destino_temporal` (desde `GuardaFalsa`) | `os.lstat` de /Volumes, /Volumes/Datos y /Volumes/Datos/x |

- **Causa.** Las dos guardas armaban la tupla (léxica, resuelta) antes de mirar la léxica, así que `Path.resolve` y
  `os.path.realpath` consultaban cada componente bajo /Volumes antes del rechazo. El registro de C1 los negó.
  `realpath` y `resolve` se tragan el `PermissionError` (es un `OSError`), y la guarda rechazaba igual por la léxica. Por eso
  las pruebas pasaban y sólo el registro los veía.
- **Arreglo.** Las dos miran primero la ruta léxica, sin tocar el disco, y sólo resuelven si la léxica pasa, como
  `entorno.prohibido_volumes`. En `red` los rechazos son los mismos. En `sintetico`, además, ya no se distinguen mayúsculas (`_en_volumes`):
  antes, «/volumes/x» pasaba la guarda y `realpath` consultaba /volumes, que en APFS es /Volumes. `RegistroAccesos`, VER-14,
  `_motivos_c1` y `test_p27_ceguera_en_modo_sintetico` no cambian.
- **Pruebas.**
  - Las dos pruebas corren su llamada bajo /Volumes con un registro propio en bloqueo. Exigen el rechazo propio de la guarda
    (por su mensaje) y `registro.accesos == []`.
  - **Nueva:** `test_verificar_reloj_dmc.PruebasGrupoC27.test_p27_guardas_de_volumes_rechazan_sin_consultar`. Llama a las 8
    guardas del paquete (`entorno.prohibido_volumes`, `escribir_atomico`, `rutas_sinteticas`, `red._bajo_volumes`, `g_dup`,
    `sintetico._exigir_destino_temporal`, `GuardaFalsa` y `GuardaFalsa.write_atomic_bytes`) con 4 rutas bajo /Volumes
    (también en minúsculas y con «..»). Exige el rechazo propio y ningún acceso. Una ruta temporal pasa sin accesos.
    - **Completitud.** Por AST, los detectores son las funciones del paquete con una constante «volumes» o «/Volumes»
      (`entorno.prohibido_volumes`, `red._bajo_volumes` y `sintetico._en_volumes`). Si aparece otro, la prueba falla hasta
      que se agregue.
  - **Comprobado.** Con las guardas viejas puestas en memoria, sin tocar archivos, las tres pruebas fallan (1, 1 y 20
    fallas); con las nuevas, pasan.
  - **Segundo rastreo,** con el código arreglado y la suite completa bajo el mismo registro en bloqueo: 433 pruebas,
    sin fallas ni errores ni omitidas, **0 accesos** y los mismos 11 negados por las propias pruebas (los de
    `/Volumes/reloj_dmc_prueba_inexistente`, de test_verificar_reloj_dmc).

**3. Diagnóstico con el criterio nuevo (sin volver a correr la batería).** Sobre `resultados_bateria.parquet` de anoche
(`110ddc0b…`, verificado contra `sha256.json`), con `criterios_por_celda` del código enmendado:
- pasan los 9 criterios;
- lo indecidible da 0 confirmados del tipo e, de Pascua o de Juan Fernández en D1 y D2. El tipo f da 8 confirmados de
  13.680, 8 correctos y 0 erróneos;
- los otros 8 criterios dan el mismo detalle que `criterios_bateria.json`: cero erróneas, sensibilidad de 1,000 y 0,974,
  razón civil de 0,974 y confirmación correcta de 9.921/10.640 = 0,932;
- `ajustar_umbrales`, con los resultados guardados, termina en la primera iteración: «aprobado»;
- por celda sólo cambia `indecidibles_confirmados` en las 2 celdas de C(Coyhaique) × f.

Con el v1.0.4 y sin los accesos, C1 aprobaría. Es sólo un diagnóstico: no reemplaza la corrida que relanza el autor.

**Suite completa** (`~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .`, desde
`scripts_modelo_1km`): **433 pruebas, OK**, en 292 s, sin fallas, sin fallas esperadas y sin omitidas.
Son las 430 de antes y 3 nuevas: 2 de test_bateria y 1 de test_verificar_reloj_dmc.

**Anexo F:** no cambia. Sólo se agregaron datos (`TIPO_SEIS_HORAS`, `FRAGMENTO_INDECIDIBLE`) y funciones privadas
(`sintetico._en_volumes` y `_exigir_fuera`), que el AST no lista.

**Pendientes:**
- **Anclar la Enmienda 4:** commit local en APH y sello OpenTimestamps de su línea en un archivo de anclajes propio. La huella
  de `TEXTOS_PROTOCOLO` es la que da el generador. Si el texto cambia antes, las pruebas fallan a propósito.
- **Relanzar la batería completa** con el v1.0.4 y el código arreglado (`--sintetico --bateria`), y comprobar en
  `resumen_c1.json` que `ceguera.accesos` sea 0.
- **Sugerencia, no aplicada:** `resumen_c1.json` cuenta los accesos, pero no da su ruta ni la prueba en curso. Agregarlas
  cambiaría el esquema `dmc-reloj-c1/1` y la redacción de §7.4, así que lo decide el autor.
- **El tipo f sólo está en D1:** la batería no mide sus confirmaciones con perturbaciones de D2 ni con E6. Va como riesgo en
  `ENMIENDA_4.md`.

## Cierre de C1: arreglos de P1 A (2026-10-25)

El autor respondió las 8 preguntas de C1 con la opción recomendada
(`APH/auditoria/20261025/reloj_dmc_c1/decisiones_autor_20261025.md`). P1 A pide arreglar PEN-1, PEN-3, PEN-4, PEN-5 y
PEN-9 (`lecturas_c1.md`, §6) y relanzar la batería completa con la salida por omisión `c1/`. Este paso es el código. Nada
se hizo con datos DMC, con la red ni con git que escriba; nada se escribió en /Volumes ni quedó `__pycache__`.

**Arreglos**, cada uno con una prueba que falla con el código anterior (comprobado sobre una copia intacta del paquete):
- **PEN-1 (impedía C3 y C4).** `umbrales.regenerar_desde_texto` corta la lista de fijos en el párrafo «**Fijos del
  cuerpo**» de la Enmienda 1 (E1-5), como `c0/preparar_c0.anexo_b`. Antes lo tomaba por una línea suelta, y
  `cargar_umbrales` no cargaba ningún texto posterior a la Enmienda 1, tampoco el v1.1. Constante `FIJOS_DEL_CUERPO`.
  Prueba: `test_umbrales.PruebasConstantesPorVersion.test_c1_regenerar_desde_textos_con_fijos_del_cuerpo`: cada versión
  da el JSON de C0, y `cargar_umbrales` carga un JSON del v1.0.4 con la huella de C0; con el código anterior falla con «línea
  suelta en «Fijos»».
- **PEN-3.** `test_reloj_dmc.EN_CURSO` queda vacía. Prueba: `PruebasCierreDeC1.test_en_curso_vacia_al_cerrar_c1`.
- **PEN-4.** `numerico.PEARSON_MIN_PARES = 3`, marcado «no-umbral», reemplaza el literal tolerado `if n < 3`; sale de
  `test_umbrales.TOLERADOS`. Prueba: `test_pearson_minimo_con_nombre_y_sin_tolerados_pendientes`.
- **PEN-5.** `decision.py` y `lineas_registro` (lectura 8) ya no dicen que la Enmienda 1 es un borrador sin adoptar.
  Prueba: `PruebasCierreDeC1.test_encabezados_sin_enmiendas_adoptadas_como_pendientes`, sobre todos los módulos y los
  docstrings de las pruebas.
- **PEN-9.** `constantes.VERSION_C1 = "v1.1"`: `indice_version` la pone después de la vigente, con sus mismos fragmentos.
  Su sha256 no va en `TEXTOS_PROTOCOLO`, porque el v1.1 cita la salida de la corrida de C1, que corre este código; la fija
  el addendum. Las dos pruebas que esperaban un error con «v1.1» lo esperan con «v1.2». Prueba: `test_version_de_c1_v1_1`.

**Ningún veredicto cambia.** Con el código anterior y con el arreglado, en el mismo entorno:
- una red pequeña de la batería (`s+0.0_r01`, 14 estaciones de D1, D2 y D3, con Cv, Pascua y el tipo g; 266
  estación-años) da el mismo `resultados` byte a byte;
- sobre `resultados_bateria.parquet` de `c1_corrida2_20261025/`, `criterios_por_celda` reproduce byte a byte su
  `criterios_bateria.json` (`2d522585…`), y `ajustar_umbrales` termina en la primera iteración, «aprobado»;
- la tabla de la batería sigue dando `c8442bb7…`, y la huella de los umbrales, `fad90d75…`.

**Carpetas.** `LOCAL/…/v1/c1/` (la corrida del v1.0.3) pasó a `c1_corrida1_20261024/` con `mv`, con sus 7 huellas
intactas. La próxima corrida (`--sintetico --bateria`, sin `--salida`) escribe en `c1/`.

**Anexo F:** no cambia (se regeneró con su script y sale igual): no cambia ninguna firma pública.

**Suite completa** (`~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .`, desde
`scripts_modelo_1km`, un hilo numérico): **438 pruebas, OK**, en 311 s, sin fallas, sin fallas esperadas y sin omitidas.
Son las 433 de antes y 5 nuevas: 3 de test_umbrales y 2 de test_reloj_dmc. El detector de literales sigue en verde, sin
entradas «PENDIENTE» en TOLERADOS.

## Enmienda 5 (2026-10-26)

C3 corrió el 2026-10-26 con AP `4b50b0d` y C3b no pasó: el norte recuperó 84 de 96 unidades, con cero confirmaciones
erróneas. El autor adoptó la Enmienda 5 del reloj, «Opción 2 (Recomendado)»
(`APH/auditoria/20261026/reloj_dmc_c3/decisiones_autor_20261026.md`): las erratas E-1 y E-2, E5-1, E5-2 con la
restricción de la revisión y E5-3, y que `C3b.json` guarde los controles de red. El texto es el v1.0.5
(`APH/auditoria/20261023/reloj_dmc/enmienda5/`, `ENMIENDA_5.md`, `generar_v1_0_5.py`). E5-4 no se adoptó. Nada se hizo
con datos DMC, con la red ni con git que escriba; nada se escribió en /Volumes ni quedó `__pycache__`.

**1. Erratas (§10; no cambian el texto).**
- **E-1, lectura ERR-1 (desempate por menor `pixel_id`).** `numerico.mas_cercano(distancias, ids)`: dos distancias que
  difieren en ≤ `numerico.EMPATE_DISTANCIA_KM` (1e-6 km, «no-umbral») empatan y decide el menor id. La usan
  `controles_era5.pixel_valido_mas_cercano` (C3-6), `controles_era5.parejas_c3c` (C3-9) y `extraccion.elegir_pixel`
  (§3.3, C4; lectura EXT-9). Antes, `np.lexsort` sobre distancias en coma flotante: los vecinos este y oeste a la misma
  latitud difieren en 1e-15 a 1e-12 km.
- **E-2, lectura ERR-2 (empates exactos del salto de P7).** `guardas.EMPATE_P7_C` (1e-9 °C, «no-umbral») en los dos «≥»
  del salto (`guardas._fallas_p7`), también en la P7 de E5-2. La caída sigue estricta.

**2. E5-1 (§8.E, C3b; lecturas C3-8, RED-11 y C3-17).**
- `orquestacion.OpcionesCorrida.a3_solo_pais` (False por omisión) llega a `red.controles_red(..., a3_solo_pais=…)` desde
  `evaluar_red`. Con True, A3 se calcula e informa entero («rige» = «pais» y «fallan_macrozonas_sin_consecuencia»), y las
  consecuencias, la muestra de la calibración de E3t y el modo de E3t reciben una lista vacía de macrozonas que fallan.
  La falla en el país rige igual.
- Sólo C3b la activa: `controles_era5._opciones(True, a3_solo_pais=True)`. C3c, C4 y la batería, no (lo comprueba
  `test_orquestacion.PruebasEnmienda5Opciones` por AST).
- `controles_era5.controles_red_c3(resultado)`: `C3b.json` guarda en «controles_red» A3, A5 y la calibración de E3t (modo y
  resumen por macrozona, y sus umbrales), sin las tablas. Con una red simulada que no los trae, la clave queda vacía.

**3. E5-2 (§4.7; lectura GU-3, con la restricción).**
- `guardas.p7(extracto, ctx, serie=None)`; `guardas.guardas` le pasa la serie. `guardas.p7_con_referencia(ctx, serie)`:
  no costera por §3.3 (`info.costera`, también en C3c, donde no se aplica la exclusión de E3t y T-P) y con las
  condiciones de E3d en Ts (`_motivo_e3d(ctx, serie, "Ts") is None`: coordenadas válidas y consistentes, píxel con
  serie, z_cat legible y |Δz| ≤ E3D_DZ_TS_M).
- Con referencia, una fila por H de P (como E3d); sin ella, la fila «*» de siempre (la P7 anterior). Por eso cambió la
  aserción de `test_guardas_reune_las_activas`, que esperaba «*» en P7.
- La referencia, x(L) = t2m(u_H(L)) del píxel en los mismos pares (L, L + 1 h) con x finito en los dos extremos
  (`_p7_relativa`, `_perfil_p7`, `_referencia_p7`), se calcula sólo en los años en que la P7 sin referencia falla: con
  s_h^x ≥ 1 y d_h^x ≥ 0 la de E5-2 no puede fallar donde aquélla pasa o no es evaluable (lo comprueba
  `test_e5_2_nunca_falla_donde_la_anterior_pasa`). Dos H con el mismo c_H(R) en todos los regímenes del año comparten el
  cálculo; así, en una clase fusionada sus miembros dan la misma fila (`decision._guarda_de_clase`).
- s_h^x vale 1 si su denominador es 0 o no está definido (el borrador lo midió como «no limita»; difieren sólo con una
  serie constante).

**4. E5-3.** Las lecturas RED-1 (`red.py`) y C3-8, C3-6 y C3-9 (`controles_era5.py`), EXT-9 (`extraccion.py`) y GU-3
(`guardas.py`) se reescribieron; son nuevas ERR-1, ERR-2, RED-11 y C3-17. La lista para el addendum está en
`APH/auditoria/20261023/reloj_dmc/enmienda5/lecturas_enmienda5.md` (reemplaza 6 de `lecturas_c1.md` y agrega 4).

**5. Versiones del texto (`constantes.py`).** El v1.0.5 entra en `TEXTOS_PROTOCOLO` con `21f1b469…` y es el vigente.
`VERSION_C1 = "v1.2"`: el cierre nuevo de C1 da el v1.2 (`enmienda5/generar_v1_2.py`); el v1.1 deja de ser una versión
del código. Ningún fragmento de `CONSTANTES` ni de `CONSTANTES_BATERIA` cambia.

**6. Pruebas.**
- **Nuevas (20), que fallan con el código anclado y pasan con el nuevo** (comprobado sobre una copia de AP `4b50b0d` con
  las pruebas nuevas: 6 fallan por aserción y 14 por error, porque la función, el argumento o el campo no existen):
  - E-1: `test_numerico.PruebasEnmienda5Empate.test_err1_mas_cercano_empate_con_tolerancia`,
    `test_extraccion.PruebasEnmienda5Empate.test_err1_elegir_pixel_celda_propia_no_valida_empate_menor_pixel_id`,
    `test_controles_era5.PruebasEnmienda5Empate.test_err1_estacion_de_prueba_c3b_empate_este_oeste_menor_pixel_id` y
    `test_err1_pareja_c3c_empate_menor_pixel_id`. Las dos primeras del borrador corren sobre las tres celdas reales de la
    fila 1399 del catálogo (49,9° S).
  - E-2: `test_guardas.PruebasEnmienda5P7.test_err2_salto_en_empate_exacto_falla` (la del borrador).
  - E5-1: `test_red.PruebasEnmienda5A3.test_e5_1_a3_rige_solo_en_el_pais` y `test_e5_1_la_falla_en_el_pais_rige_igual`;
    `test_orquestacion.PruebasEnmienda5Opciones.test_e5_1_evaluar_red_pasa_a3_solo_pais` y
    `test_e5_1_solo_c3b_activa_la_opcion`; `test_controles_era5.PruebasEnmienda5Controles.test_e5_1_c3b_a3_solo_en_el_pais_y_controles_en_el_json`
    y `test_e5_1_c3c_no_usa_la_opcion`.
  - E5-2: `test_guardas.PruebasEnmienda5P7.test_e5_2_falsa_alarma_de_reloj_civil_en_altura_desaparece`,
    `test_e5_2_sin_referencia_rige_la_p7_anterior` (costera, costera sin la exclusión, |Δz| > 1.000 m, sin píxel,
    coordenadas inconsistentes y sin z_cat), `test_e5_2_nunca_falla_donde_la_anterior_pasa` y
    `test_e5_2_prueba_14_sigue_fallando_con_referencia`.
  - E5-3 y lecturas: `test_red.PruebasEnmienda5A3.test_e5_3_lectura_red_1`,
    `test_controles_era5.PruebasEnmienda5Controles.test_e5_lecturas_de_c3` y
    `test_guardas.PruebasEnmienda5P7.test_e5_lecturas_gu3_y_err2`.
  - Texto: `test_umbrales.PruebasConstantesPorVersion.test_e5_texto_vigente` y `test_version_de_c1_v1_2` (antes
    `test_version_de_c1_v1_1`).
- **Que fijaban el texto anterior:** `test_guardas_reune_las_activas` (P7 por H), `test_fijos_nuevos_del_cuerpo_en_cada_version`
  (las 7 comparaciones de las líneas nuevas: 2 dentro de P7_PRESENCIA y 5 que repiten un umbral, declaradas en
  `REPETICIONES_V1_0_5` con su valor), `test_versiones_del_texto_con_su_huella` y `test_constantes_detecta_desvios`
  (la versión desconocida pasa a «v1.3»), y `test_constantes_contra_cada_version_y_la_vigente` (seis versiones; ningún
  fragmento cambia del v1.0.4 al v1.0.5).
- **Suite completa** (`~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .`, desde
  `scripts_modelo_1km`, un hilo numérico): **457 pruebas, OK**, en 280 s, sin fallas, sin fallas esperadas y sin omitidas.

**7. Anexo F:** se regeneró con su script. Cambian cinco firmas: `numerico.mas_cercano`, `guardas.p7` y
`guardas.p7_con_referencia`, `red.controles_red` y el campo `OpcionesCorrida.a3_solo_pais`, y `controles_era5.controles_red_c3`.

**8. C3b con el código nuevo** (copia temporal del paquete, sobre los extractos de C3 en sólo lectura, con las 19
columnas de las fuentes nuevas de E-1 extraídas de ERA5L a la carpeta temporal por `extraccion.extraer_era5land`, y los
umbrales de C0, huella `fad90d75…`; 0 accesos bajo la DMC): **pasa**. Norte 96 de 96, sur F(0) 6 de 6, 0
confirmaciones erróneas en el paso 9 y en los veredictos finales, ida y vuelta aprobada (1.039 reglas en 102
estaciones). A3 falla en norte_chico sólo por la mediana (−0,329 h) y no tiene consecuencia; E3t queda en modo completo
en las cinco macrozonas. `C3b.csv` y `C3b_anios.csv` (120 y 2.280 filas) son iguales a los de la variante `op1_pais` del
borrador.

**9. Submuestra de la batería** (sintética, desde las copias temporales del paquete, bajo un registro en bloqueo sobre
/Volumes, 0 accesos; unos 10 min). Las seis redes chicas completas `s+1.0_r01`, `s+2.5_r01`, `s-2.0_r01`, `s+1.0_r02`,
`s+2.5_r02` y `s-2.0_r02` (72 estaciones, 1.368 estación-años, con la ida y vuelta) dan, con el código nuevo, el mismo
`resultados` que la corrida aprobada de `LOCAL/…/v1/c1/` (`pandas.testing.assert_frame_equal`, 0 filas distintas). Una
subred de `s+0.0_r11` (una de cada cuatro estaciones: 60 y 1.140 estación-años) da la misma huella de resultados con el
código anclado y con el nuevo (`6e836533…`). En todas, 0 erróneas, 0 años con motivo «guarda P7» y 0 fallas de ida y
vuelta. No reemplaza la batería completa.

**10. Efecto fuera del reloj (no se tocó).** `constantes.py` es uno de los siete archivos de la clausura del reloj que fija
el producto meteorológico combinado (`meteo_combinada/fijados.py`, `HUELLAS_RELOJ_4B50B0D`): su huella pasa de
`10354281…` a la nueva; los otros seis no cambian. Las pruebas de M1 que cargan el validador del reloj con esas huellas
fallarán hasta que M1 recalcule la clausura con el commit de AP de esta enmienda (su lectura FIJ-1 lo prevé).

**Pendientes:**
- Commit en APH (la Enmienda 5 y la carpeta de C3) y en AP (este código), su sello y el envío de APH (E5-C).
- Pasar `LOCAL/…/v1/c1/` a `c1_corrida3_20261025/` y relanzar la batería completa sin `--salida` (unas 9,7 h).
- El cierre nuevo: `enmienda5/generar_v1_2.py` y `enmienda5/armar_addendum_c1_e5.py`, en
  `APH/auditoria/<fecha del cierre>/reloj_dmc/`; después C3 completo con el addendum nuevo.

## Revisión de la Enmienda 5: arreglos (2026-10-27)

Una revisión independiente concluyó «con cambios». En el código del paquete sólo pidió pruebas; el resto fue de los
textos y los generadores de APH (`enmienda5/`). El autor resolvió además la segunda tanda (E5-D a E5-G,
`APH/auditoria/20261026/reloj_dmc_c3/decisiones_autor_20261027.md`): nombres v1.0.5 y v1.2, traslado de las corridas
anteriores, la clausura de M1 tras el cierre nuevo de C1 y las tres lecturas de implementación de E5-2 (GU-3), que
entran al addendum como clase (ii).

**Pruebas nuevas (3), en `test_guardas.PruebasEnmienda5P7`,** que fallan con el código anclado (1 por aserción y 2 por
error) y pasan con el nuevo:
- `test_err2_minimo_de_1_5_con_tolerancia`: la tolerancia de ERR-2 vale también en «m_h ≥ 1,5 °C» (17,4 − 15,9 da
  1,4999999999999982 en coma flotante);
- `test_e5_2_no_evaluable_sigue_no_evaluable_con_referencia`: con Ts cada 3 h la P7 no es evaluable, y con referencia
  cada H lleva esa misma fila (la referencia nunca convierte un «no evaluable» en «falla»);
- `test_e5_2_referencia_con_x_finito_en_los_dos_extremos`: con la t2m del píxel borrada en 20 extremos de pares de la
  etiqueta 09, la referencia sigue viendo el salto y C(Santiago) pasa. Con una implementación que no filtra esos pares
  la prueba falla (comprobado con un reemplazo en memoria de `_p7_relativa`).

**Suite completa:** 460 pruebas (457 + 3), OK. Ningún archivo del paquete cambió fuera de `tests/test_guardas.py` y
este documento.

**Lo del procedimiento de la batería** (antes, `git status` vacío en el paquete y las huellas de los `.py` guardadas; al
terminar, las mismas huellas) está en `APH/auditoria/20261023/reloj_dmc/enmienda5/ENMIENDA_5.md`, §8;
`armar_addendum_c1_e5.py --final` lo comprueba contra el commit de AP y contra esas huellas.
