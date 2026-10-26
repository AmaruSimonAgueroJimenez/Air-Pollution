# Propuesta de Enmienda 3 del procedimiento para confirmar el reloj de las horas DMC (borrador, 2026-10-24)

**Estado.** Borrador para que el autor decida antes de C4. No está adoptado, anclado ni aplicado. No cambia el código: las
pruebas que lo documentan describen el comportamiento del texto anclado.

**Texto de referencia.** El v1.0.1 (Enmienda 1). La Enmienda 2 no toca ninguna de estas frases.

**A ciegas.** Todo lo de aquí sale de datos sintéticos: el generador `sintetico.py`, las atmósferas propias de
`test_lineas_fisicas.py` y de `test_guardas.py`, y redes pequeñas en memoria. No se abrió nada bajo DMC ni bajo /Volumes, no se
corrió la batería completa ni C3 sobre ERA5-Land real.

**Origen.** Son los cuatro riesgos de «Ola 4a cerrada» (`COORDINACION_C1.md`). Cada uno se contrastó con el texto, con el
código y con el generador. Ninguno resultó ser un error del código ni del generador: los cuatro son propiedades del texto
anclado. Al revisar el tercero apareció un caso más grave, que se suma aquí (E3-2).

| Punto | Qué | ¿Hace fallar C1? | Qué se recomienda |
|---|---|---|---|
| E3-1 | La regla fina se corre en las estaciones con ventana diurna | No por sí solo: da pérdidas (tipos c y d) y un riesgo real en C4 | adoptar |
| E3-2 | Una automática con reglas de cambio vencidas se confirma F(−4) | **Sí**: la celda «Cv × tipo a» de D1 y el criterio «sin cruces» | adoptar (opción A′) |
| E3-3 | T-P falla en F(0) con un desfase térmico de 2,5 h | No: sólo pérdidas en celdas de D2 | no cambiar |
| E3-4 | El aeródromo de 11 a 23 h nunca pasa el filtro de E3t (ORQ-10) | No | aclarar el texto |

---

## E3-1. Filtro de 24 h de la regla fina con una ventana diurna (§4.3.1)

**Texto anclado** (§4.3.1, «Series filtradas»):
> En cada parte y en cada año-régimen se quita a QFE su propio armónico de 24 h, ajustado en hora de etiqueta, y a sp el
> suyo, ajustado en hora UTC (mínimos cuadrados con constante, coseno y seno de período 24 h).
> - No se supone ningún reloj.
> - Con ellas se calculan, igual que arriba, r^f(c), ĉ^f y ĉ^f_cont.

**Texto nuevo:**
> En cada parte y en cada año-régimen se quita a QFE su propio armónico de 24 h, ajustado en hora de etiqueta sobre las
> etiquetas de la unidad. A sp se le quita, para cada c de la ventana, su armónico de 24 h ajustado en hora UTC sobre los
> instantes que ese c empareja con la unidad, {L − c, L − c − p : L ∈ M} (mínimos cuadrados con constante, coseno y seno
> de período 24 h) [Enmienda 3, E3-1].
> - No se supone ningún reloj: todos los c reciben el mismo trato, y con c = c_H los dos ajustes usan los mismos instantes.
> - Con ellas se calculan, igual que arriba, r^f(c), ĉ^f y ĉ^f_cont.

**Por qué.**
- La frase da un solo armónico para sp («el suyo»). La lectura del diseño (R-23, y LF-2 en `lineas_fisicas`) lo ajusta
  sobre todas las horas UTC que usa la unidad. En una estación de 24 h, esas son las mismas horas que las de QFE, y el
  filtro quita lo mismo de las dos series.
- En una estación con ventana diurna, como el aeródromo de 11 a 23 h de §8.D o los reales de §1 (Copiapó, de 12 a 00 h;
  Vallenar, de 12 a 22 h), QFE trae 13 horas por día y sp trae las 24. Sobre 13 horas, un armónico de 24 h absorbe parte de
  la marea S2, y sobre 24 horas no. Los residuos ya no son comparables, y el máximo de r^f(c) se corre.
- El corrimiento depende de dónde cae la ventana (se repite cada 6 h) y de cuánto pesa la marea en las diferencias horarias
  de presión. En el generador de la batería llega a ±1,7 h. Una regla fina corrida 1 h queda fina, porque es estable y está
  cerca de un entero, y entonces excluye al reloj verdadero o señala reloj anómalo.
- No es un error del código: el código hace lo que dice la frase anclada con la única lectura que da un solo armónico. El
  código del cambio iría en `lineas_fisicas._series_unidad`, unas 15 líneas (el arnés de la traza 1 lo implementa tal cual).

**Efecto medido** (datos sintéticos; trazas 1 a 3 al final):
- **Sesgo de ĉ^f_cont** con una ventana de 13 h, según la hora h0 de su primera etiqueta. Es una automática del generador
  recortada, 2019, a 33,4° S, con los relojes F(0), F(−4) y C(Santiago) en R0 y R1:

  | h0 (mód 6) | 0 | 1 | 2 | 3 | 4 | 5 |
  |---|---|---|---|---|---|---|
  | texto anclado, F(0) R0 | +0,46 | +1,20 | +1,26 | −1,32 | −1,08 | −0,35 |
  | texto nuevo, F(0) R0 | +0,13 | +0,28 | +0,12 | −0,16 | −0,23 | −0,07 |

  En las 144 unidades (24 ventanas, 3 relojes, 2 años-régimen):
  - con el texto anclado, |sesgo| máximo de 1,68 h; 52 unidades quedan finas y **las 52 tienen ĉ^f errado**;
  - con el texto nuevo, |sesgo| máximo de 0,34 h; 121 quedan finas y ninguna tiene ĉ^f errado.
- **Con la atmósfera propia de `test_lineas_fisicas`** (ruido sinóptico AR(1) de 0,06 hPa):
  - con el texto anclado, el sesgo llega a ±1,7 h, y las ventanas con h0 ≡ 1 (mód 3) quedan finas con ĉ^f = ±1;
  - con el texto nuevo, todas quedan finas y exactas, con |sesgo| ≤ 0,21 h.
  - Con el ruido de 0,25 hPa que trae por omisión, el texto anclado deja el sesgo en ±0,18 h. El sesgo crece cuanto más pesa
    la marea en las diferencias horarias. En la red real no se conoce antes de C4.
- **Aeródromos de la batería, 2008-2026** (una réplica, datos completos, relojes F(0), F(−3), F(−4) y C(Santiago)):
  - **tipo c**, con el texto anclado: los 76 estación-años quedan insuficientes, porque ĉ^f_cont queda a 0,35-0,55 h
    del entero y no es fina;
  - **tipo d**, con el texto anclado: 38 discrepantes («líneas en conflicto» o reloj anómalo), 38 insuficientes, y las cuatro
    estaciones quedan inestables. La causa no es el cambio administrativo: con la ventana corrida a 09-21 h civil, 2017
    falla igual sin ningún cambio. Por eso falla `test_orquestacion.test_ida_y_vuelta_aerodromo_tipo_d`;
  - con el texto nuevo, en los dos tipos: F(−3), F(−4) y C(Santiago) quedan confirmados con el reloj verdadero en los 19 años
    (114 estación-años), y F(0) queda insuficiente en los 19, como espera el punto 16 de §8 sin E3t ni E6.
  - No hubo confirmaciones erróneas con ningún texto, ni en «faltante30» ni en «ralo2008» con el anclado.
- **Estaciones de 24 h:** el efecto es nulo en las pruebas. Con el texto nuevo, las 109 pruebas de lineas_fisicas, guardas,
  red, decision y orquestacion (traza 3) dan dos cambios, ambos esperados:
  - deja de cumplirse `test_regla_fina_sesgada_en_ventana_parcial_texto_anclado`, que fija el texto anclado;
  - `test_ida_y_vuelta_aerodromo_tipo_d` pasa, ida y vuelta incluida.
  Todo lo demás sigue igual: C.16 a C.23, B.12 con el S1 local y las calibraciones.
- **Otros usos de ĉ^f_cont** que se corrigen también: la tolerancia τ de la regla gruesa en E3p, A3, A5 y el diagnóstico
  subhorario. Con el texto anclado, los aeródromos entran a la muestra de A5 con ĉ^f_cont corridos.
- **Costo:** +7 % en `orquestacion.evaluar_red`: 39,9 s → 42,7 s para 8 estaciones × 19 años. Son 19 ajustes de 3
  coeficientes por unidad en vez de uno.

**Alternativa conservadora** (no recomendada). Agregar una séptima condición al año-régimen fino de §4.3.4: «las etiquetas de
la unidad cubren el día (n_h ≥ 20)». Los aeródromos pierden la regla fina y quedan insuficientes. Además, A5 tendría que
excluirlos de su muestra.

**Lo que no cambia:** ningún umbral, ni la regla gruesa, ni la definición de M o de r(c) sin filtrar.

---

## E3-2. Reglas de cambio vencidas en una estación sin observador (§2.2, §4.1.1, §4.1.4, §5.3)

**Texto anclado:**
- §2.2: «**Reloj anómalo:** un reloj fuera de P que la evidencia señala con fuerza (§4.2, §4.3.2 y §4.3.4). Un reloj anómalo
  deja el año discrepante. Dos ejemplos: […] un sistema con reglas de cambio vencidas da hora civil con fechas antiguas
  (§4.1.4).»
- §4.1.1, «Placebos»: «en las fechas de la regla anterior del Anexo A2, que incluye la de 2015 […]».
- §4.1.4: «**Marca.** Si el año es discrepante y, con las mismas reglas, agregar C_venc(Z, y) a P dejaría K = {C_venc}, el año
  lleva la marca […]».

**Qué pasa con el texto anclado.** En una estación con QFE y sin observador (como el tipo a de §8.D), nada deja discrepante
una hora civil con la regla anterior a 2008. El generador cumple §8.D (traza 4):
- E2 queda sin información, porque se exige observador en ≥ 50 % de las filas con RR.
- E1a ve «presente» la 00:00 del adelanto real, porque bajo la regla vieja esa etiqueta existe. Eso excluye C(Santiago) y
  deja compatibles las fijas.
- La regla fina ve R1 (el invierno de Santiago) todo en −4, porque el invierno viejo, de marzo a octubre, lo contiene. Da
  R1 fino (|ĉ^f_cont − ĉ^f| ≈ 0,02 h, estabilidad 1,00), excluye F(−3) y deja compatible F(−4). R0 mezcla −3 y −4 y no es
  fino, así que nada excluye F(−4).
- E3p gruesa y E4p sólo separan a 2 h o más. E1c no forma patrón, porque la casilla de menos cae en octubre y no en el mes
  del adelanto de Z.
- Resultado: K = {F(−4)}, con apoyo de E1a (registro) y E3p (Q). El año se confirma F(−4), y de enero a marzo y de octubre a
  diciembre (−3) reciben una regla de −240.

**Medido** (una réplica, 2008-2026, celda «Cv(America/Santiago)» de D1):
- **tipo a:**
  - con datos completos: 13 años confirmados F(−4) de 19, todos erróneos, y 6 insuficientes. En otra estación de la
    misma celda (otro ruido) son 15 de 19: todos los de 2011 a 2026 salvo 2015;
  - en «faltante30»: 3 erróneas;
  - en «ralo2008»: 13 erróneas;
  - un solo año (2019): también se confirma F(−4).
- **Tipos b, c, d y f:** la estación queda inestable. **Tipo e:** insuficiente. En ninguno hay confirmaciones.
- **Otros relojes fuera de P**, con datos completos: F(+1), F(−1), F(−2) y F(−5) en los tipos a-f, el cambio de F(−4) a F(0)
  y el tipo g. No hubo ninguna confirmación errónea.
- **Por qué hace fallar C1.** §8.D cuenta como errónea toda confirmación cuando el verdadero está fuera de P, y es además un
  cruce (un civil confirmado como fijo). §8.F tendría que mover los umbrales de las líneas de apoyo, E1a y E3p, pero no tiene
  ninguno que sirva:
  - «presente» no depende de umbrales ajustables;
  - R1 queda fino para cualquier valor de las listas de E3P_FINA_TAU, E3P_FINA_ESTAB y E3P_FINA_APAGADO.
  Las listas se agotan y C1 falla.
- **Riesgo 3 de la coordinación** (2010). En 2008 y en 2010, la regla anterior y la vigente difieren sólo en el atraso:
  504 horas, del 2008-03-09 a las 03Z al 2008-03-30 a las 03Z, y del 2010-03-14 a las 03Z al 2010-04-04 a las 03Z. En 2009
  coinciden.
  - Una sinóptica con un solo año de datos (2010 o 2008) se confirma C(Santiago), y esas tres semanas quedan con 1 h de
    error. Pasa porque E2 no es informativo ni en la parte de marzo ni en R0 (κ3 < 0,95), y R0 queda fino en −3 (ĉ^f_cont
    −3,16).
  - En la batería no aparece: con 2008-2026, la sinóptica Cv queda inestable.
  - Ninguna regla basada en datos lo evita en 2008-2010, salvo E2 en la parte del atraso, porque en esos años el adelanto
    viejo coincide con el real.

**Texto nuevo** (opción A′, recomendada):
- §4.1.1, una viñeta nueva después de «Placebos»:
  > **Eventos de regla vencida** [Enmienda 3, E3-2]. Son las etiquetas h0 que serían inexistentes bajo una regla de cambio
  > anterior y no lo son bajo la vigente: el adelanto de la regla anterior a 2008 (octubre, domingo ≥ 9; en Pascua, la 22:00
  > del sábado anterior) en cada año en que no coincide con el Anexo A, y las fechas de adelanto del Anexo A2. En cada una
  > se aplican, en la misma hora, las reglas «presente» y «ausente» de esta sección.
  > - **Patrón de reglas vencidas(Z):** ≥ 2 eventos de regla vencida ausentes, con P0 ≤ 0,01; los ausentes son ≥ 80 % de los
  >   eventos de regla vencida evaluables; y la tasa de ausentes en los placebos del mismo día de la semana es ≤ 0,10.
  > - **Consecuencia:** con ese patrón, cada año con un evento de regla vencida ausente señala reloj anómalo (§2.2) y queda
  >   discrepante, y la estación queda inestable (§5.3, punto 1), con el motivo «civil con reglas vencidas».
- §5.3, punto 1: se agrega una tercera condición, «o tiene el patrón de reglas vencidas de §4.1.1».
- La tabla de esas fechas se genera desde la regla y desde el Anexo A2, como el A2, y su huella va al anclaje.

**Por qué así.**
- Usa la maquinaria y los umbrales que E1a ya tiene: E1A_P, E1A_P0, E1A_PLACEBO, el día habitual y el 80 % de los
  evaluables. **No agrega ningún umbral.**
- Lleva a la práctica lo que §2.2 ya dice: un sistema con reglas vencidas es un reloj anómalo.
- Los placebos del A2 no cuentan para el patrón de reglas vencidas, porque sería circular: ahí son eventos. Para el patrón
  civil siguen como están.
- Dejar inestable la estación cubre 2008 y 2010, porque toda estación de la batería cubre 2008-2026. Se pierden años en que
  la regla vieja coincide con la vigente (2009), que serían correctos. Es el lado conservador.

**Efecto esperado.** No se midió de punta a punta, porque exige implementar E1a nuevo en lineas_registro, la tabla en
tablas y la consecuencia en decision (traza 5). El indicador se midió en las etiquetas del adelanto viejo (la 00:00 del
segundo domingo de octubre, de 2011 a 2025):
- con F(0), F(−3), F(−4) y C(Santiago), en los tipos a, b y e: hay fila medida en 15 de 15 (datos completos) y en los 9
  evaluables de 9 («faltante30»; los faltantes son días enteros y quedan «sin evidencia»);
- con Cv: falta h0 y están sus dos vecinas en 15 de 15 y en 9 de 9.

Se espera:
- en las celdas Cv de los tipos a, b y e, el patrón, la estación inestable y ninguna confirmación (hoy, el tipo a da 13
  erróneas);
- en los tipos c, d y f, que no tienen la 00:00 en su horario, ningún cambio (ya quedan inestables o insuficientes);
- en las celdas de P, ningún cambio.

**Alternativas:**
- **A.** La misma detección, pero los años con evento ausente quedan discrepantes con la marca, sin contar para la
  inestabilidad (como §4.1.4). Además, en una estación con el patrón, quedan sin confirmar los años en que la regla vencida
  difiere de la vigente sólo en el atraso. Es más fina y más larga de escribir y de implementar.
- **C.** Una regla fina por parte (mes), con un mínimo de pares propio. Separaría los meses en −3 de los en −4 en cualquier
  reloj, pero agrega un umbral nuevo y su tasa de discordancias falsas habría que medirla en la batería. No se recomienda
  antes de C1.

**Riesgo residual (cualquier opción).**
- Una estación con datos sólo en 2008-2010, o de un solo año, no forma patrón.
- Un sistema que perdió sólo el decreto de un año (las fechas del A2) en una automática:
  - en un registro de un solo año, se confirma el reloj fijo vecino;
  - en registros largos queda inestable (H1 → H2 → H1). Así pasó en la traza con la regla 2016-2018 aplicada en 2019.

---

## E3-3. T-P con un desfase térmico de 2,5 h (§4.7)

**Texto anclado** (§4.7, T-P): «**Falla sólo ante una discrepancia con forma de reloj:** en algún año-régimen existe
k ∈ D_R con |δt_R − k| ≤ 0,75 h y r_t(c_H(R) + k) − r_t(c_H(R)) ≥ 0,10.»

**Qué pasa.**
- Un corrimiento de fase de 2,5 h entre Ts y t2m da δt ≈ −2,5 h bajo cualquier reloj. Puede ser el sesgo de la referencia
  de +2,5 h de §8.D2, o el desfase físico de la estación de −2,5 h, también de D2.
- Bajo F(0), D_R = {−3, −4}: |δt − (−3)| = 0,5 ≤ 0,75 y Δr ≈ +0,24 ≥ 0,10. T-P falla.
- Bajo F(−3), F(−4) y C(Santiago), D_R está a +3 o +4: T-P pasa, y queda sólo la marca «desfase térmico local».
- La regla hace eso: el código y el generador cumplen el texto.

**Medido** (traza 6). Red de prueba con sesgo +2,5 h: 3 automáticas F(0) de 2010-2019 y 8 estaciones de los tipos a y b con
los cuatro relojes de P, 2018-2019.
- **A4:** fallan T-P 34 de los 46 estación-años evaluados, y A4 restringe E3t.
- **Calibración:** n = 46, todos con |δt| > 1 h, así que E3t queda restringida.
- **Veredictos:** todos los años F(0) quedan discrepantes por T-P (δt_R de −2,42 a −2,58 h; Δr de +0,23 a +0,25). Los de
  F(−3), F(−4) y C(Santiago) quedan confirmados con el reloj verdadero.
- `test_guardas.test_tp_falla_en_f0_con_fase_termica_corrida_2_5h_texto_anclado` lo fija.

**Por qué no hace fallar C1.** Son años falsamente discrepantes, que §8.D sólo informa como pérdidas. Esas celdas de D2 no
entran a la sensibilidad, que pide celdas sin perturbación, ni al 90 % de confirmación correcta, que pide |sesgo| ≤ 1 h. No
hay confirmaciones erróneas.

**Recomendación: no cambiar la regla.**
- El resultado es conservador.
- En la red real, C3a acota la fase absoluta de t2m (φ1 entre 12,5 y 16,0 h solares), pero no su fase relativa a las
  estaciones. Si las estaciones DMC y ERA5-Land difirieran en 2,25-3,75 h, los años F(0) con Ts y QFE quedarían
  discrepantes: se pierde rendimiento en C4, no exactitud.
- Corregir δt por la mediana de la calibración, la alternativa obvia, escondería un desajuste de reloj entre Ts y QFE común a
  toda la red (un tipo g generalizado), que es justo lo que T-P vigila. No se recomienda.
- **Para §8.F:** la lista de TP_VENTANA (0,75 → 1,0) ensancha la banda vulnerable a 2,0-4,0 h. Con 1,0, también fallarían
  F(−3) y el R0 de C(Santiago) en la red de sesgo −2 h (δt = +2,0; k = +3).

---

## E3-4. Aeródromo de 11 a 23 h y el filtro de E3t (§8, punto 16; §4.3.3; ORQ-10)

**Texto anclado:**
- §8, punto 16: «Un aeródromo UTC, sin E4p, queda insuficiente, salvo con E3t en modo completo o con E6.»
- §4.3.3: «Para Ts se usan los días de etiqueta con ≥ 20 valores (o completos si p > 1); para t2m, los días UTC.»

**Qué pasa.**
- Un aeródromo de 11 a 23 h (el tipo c de §8.D; Copiapó y Vallenar en §1) tiene 13 valores por día y nunca tiene días
  válidos. La correlación diaria queda indefinida y el filtro no pasa.
- Con eso, E3t y T-P quedan sin información, aun en modo completo. También E4t y G-HR, porque la anomalía de §4.4 usa el
  mismo mínimo.
- El código cumple el texto (`test_lineas_fisicas.test_filtro_e3t_sin_dias_de_20_valores_en_ventana_de_13h`). La prueba
  C.16 muestra el rescate con un aeródromo de 20 h.
- No hace fallar C1: la batería no pide confirmar el tipo c.

**Texto nuevo** (aclaración, sin efecto en los veredictos):
- §8, punto 16: «Un aeródromo UTC con días de ≥ 20 valores, sin E4p, queda insuficiente, salvo con E3t en modo completo o con
  E6. Uno con menos horas por día, como el tipo (c) de §8.D, queda insuficiente salvo con E6, porque no pasa el filtro de
  §4.3.3.»
- §6, «Aeródromos diurnos»: se agrega «Con menos de 20 valores por día, E3t, T-P, E4t y G-HR quedan sin información (§4.3.3
  y §4.4).»

**Alternativa sustantiva** (no recomendada antes de C1). Que el filtro y la anomalía usen «los días con todas sus etiquetas
habituales» en vez de «≥ 20 valores». Abriría E3t a los aeródromos, pero E3t sin filtrar en una ventana parcial no se ha
medido, y E3-1 muestra que las ventanas parciales sesgan.

---

## Decisiones que se piden al autor

1. **E3-2** (bloquea C1). Adoptar la opción A′, la A o la C, o declarar la celda «Cv × tipo a» fuera del criterio con una
   enmienda. Esto último no se recomienda: un registrador con reglas viejas es plausible en la red real.
2. **E3-1.** Adoptarla como enmienda o, si el autor la considera sólo una lectura de «el suyo», como lectura de implementación
   en el addendum de C1 (R-23 es [D]). Mientras no se decida, `test_ida_y_vuelta_aerodromo_tipo_d` sigue como falla esperada.
3. **E3-3.** Confirmar que no se cambia (recomendado).
4. **E3-4.** Adoptar la aclaración.

Si se adoptan, van en un texto consolidado v1.0.3 generado como el v1.0.2 (cada reemplazo, una sola vez). Su implementación
es de C1 y entra al addendum.

---

## Trazas reproducibles

Todas con `~/micromamba/envs/amb_v2/bin/python -B`, desde `AP/scripts_modelo_1km`, con `zoneinfo.reset_tzpath(to=[])` y en
memoria.
1. **E3-1, el sesgo según la ventana.** `sintetico.caso_simple(código, reloj, "a", anios=(2019, 2019))`, con el extracto
   recortado a las etiquetas h0 … h0+12 (`transformar` de `orquestacion.EntradaEstacion`). Se leen `metricas_e3` de QFE a
   nivel régimen: `c_hat_f`, `c_hat_f_cont`, `fino`. El texto nuevo se mide reemplazando `lineas_fisicas._series_unidad` por
   esta variante, que cambia sólo la rama filtrada de sp:
   ```python
   def _series_unidad_por_c(u, b, pares, filtrada):
       sel = u.pares
       if not filtrada:
           return pares.dy[sel], pares.dx[:, sel]
       k = pares.dx.shape[0]
       if sel.size == 0:
           return np.empty(0), np.empty((k, 0))
       yf = np.full(len(b.L), np.nan)
       yf[u.filas] = numerico.quitar_armonico_24(LF._horas(b.L[u.filas]), b.y[u.filas])   # QFE: como hoy
       dyf = yf[pares.i[sel]] - yf[pares.j[sel]]
       dxf = np.empty((k, sel.size))
       for n in range(k):                                    # sp: un ajuste por c, sobre {L − c, L − c − p}
           inst = np.concatenate([pares.u[sel, n], pares.up[sel, n]])
           val = np.concatenate([pares.xu[sel, n], pares.xup[sel, n]])
           unicos, idx, inversa = np.unique(inst, return_index=True, return_inverse=True)
           xf = numerico.quitar_armonico_24(LF._horas(unicos), val[idx])[inversa]
           dxf[n] = xf[:sel.size] - xf[sel.size:]
       return dyf, dxf
   ```
2. **E3-1, los aeródromos de la batería.** Tipos c y d con los cuatro relojes de P, 2008-2026. Una red en memoria como
   `test_orquestacion._red(memoria=…)`, con los veredictos comparados con `sintetico.equivalentes_en_P`.
   `test_lineas_fisicas.test_regla_fina_sesgada_en_ventana_parcial_texto_anclado` fija el caso en la atmósfera propia.
3. **E3-1, efecto en las estaciones de 24 h.** Las pruebas de lineas_fisicas, guardas, red, decision y orquestacion, con la
   variante puesta.
4. **E3-2, el generador.** `test_sintetico.test_regla_anterior_difiere_de_la_vigente_solo_en_el_atraso_de_2008_y_2010`.
5. **E3-2, la decisión.** `test_sintetico.PruebasRiesgosC1.test_reglas_vencidas_en_automatica_no_se_confirman` es una falla
   esperada hasta que se adopte E3-2: confirma F(−4) en 2018, con apoyo de E1a y E3p. La celda completa sale de la misma red
   con `caso_simple(…, "Cv(America/Santiago)", t, escenario=e, anios=(2008, 2026))`. El indicador de A′ mira, en
   `entrada_en_memoria(caso)[0]`, si hay fila medida en la 00:00 del segundo domingo de octubre y en sus vecinas.
6. **E3-3.** La red de la prueba C.22 (`test_orquestacion.test_p22_sesgo_termico_2_5h`) más 8 estaciones de los tipos a y b,
   con `serie_era5_de_casos(casos, sesgo_termico_h=2.5)`. Se leen `controles["A4"]`, `controles["calibracion_e3t"]` y las
   filas «T-P» de `guardas`.
