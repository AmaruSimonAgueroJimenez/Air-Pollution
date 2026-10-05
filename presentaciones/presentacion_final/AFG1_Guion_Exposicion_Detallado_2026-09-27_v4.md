# Guion de exposición - Actividad Final de Graduación 1

Equipo 2 | 27 de septiembre de 2026

Alcance del proyecto: PM₂.₅, dióxido de nitrógeno y los otros contaminantes.

## Antes de comenzar

El guion principal comprende las diapositivas 1 a 28 y tiene 1,431 palabras. A 150 palabras por minuto, la lectura requiere aproximadamente 9.5 minutos, sin pausas ni cambios de diapositiva. El video admite hasta 10 minutos: ensaya la exposición completa con cronómetro. Los anexos no forman parte de esa duración.

PM₂.₅ se lee «pe eme dos coma cinco». Las cifras del relato están escritas para facilitar la lectura. Las notas de PowerPoint incluyen apoyo adicional y fuentes, separados del texto que debes relatar.

## 01. Presentación del proyecto

El proyecto busca reconstruir la calidad del aire en Chile. Consideramos PM dos coma cinco, material particulado fino de hasta dos coma cinco micrómetros de diámetro, dióxido de nitrógeno y los otros contaminantes. Presentamos la metodología propuesta y la caracterización de sus datos.

## 02. Introducción: el problema de cobertura

Incluimos cuatro gases: dióxido de nitrógeno, ozono, dióxido de azufre y monóxido de carbono; y dos fracciones de partículas. PM diez incluye partículas de hasta diez micrómetros, también las finas. SINCA es el Sistema de Información Nacional de Calidad del Aire. Sus estaciones miden en puntos específicos. El mapa muestra esa distribución. Buscamos reconstruir concentraciones en territorios poco monitoreados, explicando su incertidumbre.

## 03. Antecedentes internacionales

Los antecedentes internacionales muestran cómo combinar fuentes. Van Donkelaar integra satélites, modelos atmosféricos y estaciones para estimar partículas finas. Di combina modelos, lo que se denomina ensamble, y obtiene estimaciones diarias a un kilómetro. Estos trabajos orientan el diseño, pero su desempeño no se traslada automáticamente a Chile, a frecuencia horaria ni a otros contaminantes.

## 04. Antecedentes en Chile e hipótesis

En Chile, Pérez y Gramsch estudiaron el pronóstico horario en Cerro Navia. Peralta usó una red neuronal recurrente LSTM, que aprende relaciones temporales, para predicción espacial en Santiago. Nuestra hipótesis es que integrar fuentes reducirá el error para PM dos coma cinco, dióxido de nitrógeno y los otros contaminantes frente a interpolar estaciones vecinas. Proponemos RMSE, la raíz del error cuadrático medio, que penaliza especialmente los errores grandes.

## 05. Pregunta de investigación

La pregunta compara ambas estrategias en lugares excluidos del entrenamiento. Interpolar significa estimar un lugar a partir de estaciones cercanas. Evaluaremos qué aporta agregar información ambiental, para cada contaminante por separado y sobre las mismas observaciones reservadas.

## 06. Objetivo general

El objetivo es desarrollar esa metodología para PM dos coma cinco, dióxido de nitrógeno y los otros contaminantes en Chile. Buscamos una reconstrucción horaria sobre una grilla de cero coma cero uno grados, aproximadamente un kilómetro, evaluada en sitios reservados.

## 07. Objetivos específicos

Los objetivos organizan el trabajo. Integrar supone reunir datos con calidad y procedencia conocidas. Comparar establece qué aporta cada método frente a la interpolación. Evaluar la generalización significa comprobar cómo funciona en lugares y periodos nuevos para el modelo. Definir el producto territorial incluye su cobertura y limitaciones.

## 08. Qué se pretende estimar

Buscamos una concentración por celda, hora y contaminante, entre dos mil y septiembre de dos mil veintiséis. Usamos UTC, tiempo universal coordinado, como reloj común. Las unidades dependen de la sustancia: microgramos por metro cúbico para partículas y partes por mil millones, o ppb, para el dióxido de nitrógeno mostrado. La disponibilidad varía entre series. Las unidades de cada serie deben verificarse antes de integrarla.

## 09. Flujo de los datos

El flujo conecta datos y producto. Conservamos los originales y revisamos calidad, unidades y fechas. Describimos cada fuente con mapas y series. La siguiente etapa enlazará ubicaciones y tiempos en una tabla común, conservando faltantes y documentando pérdidas. Sobre esa integración compararemos métodos y generaremos superficies de PM dos coma cinco, dióxido de nitrógeno y los otros contaminantes.

## 10. Estaciones y productos satelitales

Las estaciones aportan la referencia superficial. SNIFA, el Sistema Nacional de Información de Fiscalización Ambiental, complementa algunas series. MAIAC aporta AOD, el espesor óptico de aerosoles: cuánto atenúan la luz las partículas de la columna atmosférica. TROPOMI es un instrumento que observa gases atmosféricos. ACAG, el Grupo de Análisis de la Composición Atmosférica, estima partículas finas. La tabla muestra periodos distintos, que pueden contener vacíos.

## 11. Meteorología y composición atmosférica

Los reanálisis combinan observaciones y modelos para describir el pasado. ERA5 y su producto terrestre, ERA5-Land, aportan meteorología. MERRA dos es otro reanálisis. CAMS es el Servicio de Monitoreo de la Atmósfera de Copernicus. GEOS-CF es un producto del modelo de composición atmosférica de NASA. Estas entradas conservan su resolución nativa aunque se lleven a una grilla más fina.

## 12. Territorio y calendario

El territorio aporta información. La cobertura de suelo procede de la iniciativa climática de la Agencia Espacial Europea, identificada como ESA CCI. La población caracteriza cada área y OpenStreetMap, u OSM, aporta cartografía vial. Reutilizar años disponibles, como el suelo de dos mil veintidós, exige identificar esas sustituciones para distinguirlas de observaciones nuevas.

## 13. Formatos y clave de integración

Los archivos tienen funciones distintas: CSV y Parquet almacenan tablas; NetCDF organiza variables por espacio y tiempo. Las capas geográficas representan el territorio. La clave común combina celda y hora. Los registros de entrenamiento conservan además la estación de origen, para rastrear su procedencia y evitar mezclar registros incompatibles. Los originales se conservan separados de los archivos preparados para el análisis.

## 14. Alineación temporal y espacial

La integración respeta la frecuencia original. CAMS aporta bloques de tres horas; los satélites se resumen por día y ACAG aporta valores mensuales. Compartir un valor mensual entre horas entrega contexto, pero no crea variación horaria observada. Debemos registrar la distancia entre celda y píxel asociado, y las pérdidas de cada unión.

## 15. Familias de métodos

Compararemos diez enfoques por contaminante. Los métodos flexibles, como bosques aleatorios y redes neuronales, representan relaciones complejas. Los espaciales consideran semejanzas entre lugares cercanos. Los ensambles combinan estimaciones; las alertas abordan valores altos y requieren criterios propios. Además del error, examinaremos qué variables aportan información, cuánto cuesta cada método y dónde falla.

## 16. Validación fuera del entrenamiento

La evaluación debe representar el uso del producto. Reservaremos sitios, entornos de diez kilómetros, regiones y bloques de cuatro años para examinar lugares y periodos nuevos. Ajustes, imputación y escalamiento usarán solo el entrenamiento, con particiones internas para seleccionar modelos; conservaremos una prueba externa. Junto con RMSE proponemos MAE, el error absoluto medio, que resume la magnitud de los errores, y sesgo, que indica sobreestimación o subestimación. También evaluaremos extremos e incertidumbre territorial.

## 17. Agregación comunal

Para cada contaminante y hora proponemos resumir una comuna ponderando cada celda por el área que ocupa dentro de ella. Mayor superficie implica mayor aporte al promedio. Usaremos solo áreas con estimación e informaremos qué proporción de la comuna representan. Sin estimaciones, queda sin dato. Esta medida describe concentración territorial, no exposición individual. La cobertura mínima aún debe acordarse antes de publicar.

## 18. Consideraciones éticas

Comunidades y municipios podrían utilizar estos mapas. Una zona con pocos monitores puede tener mayor incertidumbre, aunque se vea igual de detallada. Debemos informar cobertura y límites, distinguir observaciones de estimaciones y evaluar episodios extremos. Conservar la procedencia permite revisar cómo se obtuvo cada resultado. El objetivo es evitar una falsa sensación de precisión territorial.

## 19. Cobertura de las estaciones

El inventario contiene ciento siete estaciones y cuatrocientas tres series. Cada serie corresponde a una estación y un contaminante; una estación puede aportar varias. El gráfico muestra diferencias de disponibilidad entre partículas y gases. Estos conteos no equivalen al porcentaje de Chile cubierto.

## 20. Calidad y datos faltantes

El volumen no equivale a información utilizable. De noventa y cuatro coma tres millones de filas, el cuarenta y cinco coma veintiocho por ciento tiene medición. El resto son faltantes explícitos. Las mediciones tienen distintos estados de validación. Estos porcentajes describen el inventario seleccionado, no las pérdidas al integrar fuentes. Usar estas mediciones en modelos requiere una regla de calidad explícita.

## 21. Descriptivos de PM₂.₅

Este es el ejemplo de PM dos coma cinco. Cada punto es una estación; el color resume su concentración media observada. Hay noventa y siete estaciones después de los filtros. El detalle central ayuda a ubicarlas. Son observaciones puntuales del periodo mostrado, que termina parcialmente en septiembre.

## 22. Descriptivos de dióxido de nitrógeno

Para dióxido de nitrógeno quedan cuarenta y una estaciones, lo que plantea otro desafío de reconstrucción. El mapa tiene su propia unidad y escala de colores. Debemos interpretar cada contaminante con su muestra y unidades, sin comparar directamente los colores entre mapas.

## 23. Temperatura: ERA5-Land

ERA5-Land aporta temperatura a dos metros. Los mapas resumen los años seleccionados y las curvas muestran la variación anual por macrozona. El gradiente territorial y la estacionalidad aportan contexto meteorológico a la reconstrucción de la calidad del aire.

## 24. Aerosoles: MAIAC

MAIAC describe aerosoles a partir de observaciones satelitales. Los mapas y curvas muestran su variación espacial y temporal. Esta señal complementa las mediciones superficiales, pero no equivale a su concentración. Los vacíos satelitales deben considerarse en la integración.

## 25. Columna de dióxido de nitrógeno: TROPOMI

TROPOMI muestra la cantidad de dióxido de nitrógeno a lo largo de una columna de la parte baja de la atmósfera. Los mapas y curvas describen su variación territorial y temporal. Ese contenido vertical es distinto de la concentración junto al suelo. Debemos relacionarlo con mediciones superficiales y otras variables.

## 26. Estimación externa de PM₂.₅: ACAG

ACAG aporta una estimación externa mensual de PM dos coma cinco, construida con satélites, modelos y monitores. Su patrón espacial y variación mensual sirven como entrada. Revisaremos los posibles artefactos del extremo sur y los monitores usados en su construcción, para evaluar su independencia respecto de nuestra prueba.

## 27. Cierre y próximos pasos

Tenemos fuentes complementarias, con coberturas y calidades desiguales. Debemos cerrar la integración y fijar el protocolo antes de comparar modelos. Buscamos reconstruir PM dos coma cinco, dióxido de nitrógeno y los otros contaminantes, con resultados territoriales cuya precisión y límites podamos explicar.

## 28. Referencias

Estas son las referencias que sustentan los antecedentes y la evaluación propuesta. Muchas gracias.

# Anexos de apoyo

Estos textos son opcionales para consultas o ensayo. Las diapositivas 29 a 36 conservan su condición de ocultas.

## 29. Cobertura de bosque

Este anexo muestra la fracción de bosque obtenida de la cobertura de suelo. Una fracción indica qué parte de cada celda corresponde a bosque y no tiene unidades. El producto nativo tiene trescientos metros de resolución y se resume en la grilla del proyecto. Los datos disponibles llegan a dos mil veintidós; por eso el panel rotulado dos mil veinticuatro reutiliza esa cobertura. Es una sustitución identificada, no una observación nueva.

## 30. Aerosoles: MERRA-2

MERRA dos aporta otro ejemplo de espesor óptico de aerosoles, esta vez procedente de un reanálisis. Los bloques visibles corresponden a su resolución espacial original, más gruesa que la grilla objetivo. Los mapas resumen cada año seleccionado y las curvas describen la variación diaria suavizada por macrozona. Esta entrada complementa el contexto atmosférico; sus valores no equivalen directamente a concentraciones superficiales de partículas.

## 31. Altura de la capa límite: ERA5

ERA5 aporta la altura de la capa límite atmosférica, expresada en metros. Esta es la zona inferior de la atmósfera donde el contacto con la superficie influye en la mezcla del aire. Su profundidad ayuda a caracterizar condiciones de dispersión de contaminantes. Los mapas y curvas describen esta variable meteorológica de entrada; todavía no muestran el efecto estimado por nuestros modelos.

## 32. PM₂.₅ externo: CAMS

CAMS aporta una estimación externa de PM dos coma cinco superficial, disponible cada tres horas y en una grilla de cero coma setenta y cinco grados. La serie local comienza en dos mil tres. El ejemplo muestra patrones a escala regional; llevarlo a una grilla más fina no crea detalle medido adicional. Se utilizará como una entrada cuyo aporte debe evaluarse frente a las estaciones.

## 33. Dióxido de nitrógeno externo: GEOS-CF

GEOS-CF aporta este ejemplo de dióxido de nitrógeno superficial procedente de un modelo atmosférico de NASA. Se expresa en partes por mil millones y tiene frecuencia horaria. Los archivos locales cubren desde dos mil diecinueve hasta dos mil veinticuatro. Los mapas anuales y las curvas muestran su comportamiento espacial y temporal. Es información externa de entrada, no un resultado entrenado por el equipo.

## 34. Población

La densidad de población expresa cuántos habitantes corresponden a cada kilómetro cuadrado. Se obtiene de información comunal distribuida sobre la grilla. Su función es caracterizar el territorio. El periodo de la fuente incluye estimaciones y proyecciones, por lo que no equivale a censos observados en todos los años. Para dos mil y dos mil uno se reutiliza la información de dos mil dos.

## 35. Selección, métricas e incertidumbre

La selección de configuraciones del modelo utilizará particiones internas y dejará una prueba externa para la evaluación final. Para cada contaminante, compararemos los modelos sobre las mismas observaciones reservadas. Los extremos y los grupos territoriales se definirán antes de revisar esa prueba. Debemos distinguir la incertidumbre de una métrica de error de la incertidumbre de una concentración estimada: necesitan procedimientos específicos y no son intercambiables. El método de los intervalos predictivos todavía debe definirse.

## 36. Corte del inventario

Este resumen utiliza una instantánea auditada al quince de septiembre de dos mil veintiséis. SINCA reúne ciento siete estaciones y cuatrocientas tres series de estación y contaminante. MERRA dos meteorológico contiene trescientos diecisiete meses completos, entre enero de dos mil y mayo de dos mil veintiséis. El derivado de precipitación de ERA5-Land tiene trescientos veinte meses completos y septiembre parcial, con doscientas dieciséis horas. Estos conteos corresponden a ese corte y no al estado de las descargas de hoy.
