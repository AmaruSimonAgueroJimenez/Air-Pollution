// Guion del video de avance N.º 2 en formato Word
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  LevelFormat, convertInchesToTwip,
} = require('docx');
const fs = require('fs');

const AZUL = '184F95';
const NARANJA = 'B24E1C';
const GRIS = '898781';
const TINTA2 = '52514E';

const F = 'Calibri';

function p(children, opts = {}) { return new Paragraph({ children, ...opts }); }
function r(text, opts = {}) { return new TextRun({ text, font: F, size: 22, ...opts }); }

function diapoHeader(tag, titulo, tiempo) {
  return new Paragraph({
    spacing: { before: 260, after: 60 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: AZUL } },
    children: [
      new TextRun({ text: ` ${tag} `, font: F, size: 20, bold: true, color: 'FFFFFF', shading: { type: ShadingType.CLEAR, fill: AZUL } }),
      new TextRun({ text: `  ${titulo}`, font: F, size: 23, bold: true, color: AZUL }),
      new TextRun({ text: `   ·   ${tiempo}`, font: F, size: 20, color: GRIS }),
    ],
  });
}

function paso(n) {
  return new TextRun({ text: ` PASO ${n} `, font: F, size: 18, bold: true, color: 'FFFFFF', shading: { type: ShadingType.CLEAR, fill: NARANJA } });
}
function acot(t) {
  return new TextRun({ text: `[${t}]`, font: F, size: 21, italics: true, color: GRIS });
}
function cuerpo(parts) {
  return new Paragraph({ spacing: { after: 140 }, alignment: AlignmentType.JUSTIFIED, children: parts });
}
function habla(t) { return r(t, { size: 22 }); }

const fichaRows = [
  ['Material', 'AFG1_Video2_Presentacion_UC.pptx (10 diapositivas)'],
  ['Duración objetivo', '4:40 (máximo permitido: 5:00)'],
  ['Quién graba', 'Un integrante distinto del que grabó el video 1. Cada estudiante debe participar en al menos uno de los videos del curso.'],
  ['Estructura oficial', 'Cubre los 5 pasos exigidos: 1 presentación, 2 objetivos de la semana, 3 cómo se abordaron y tareas realizadas, 4 desafíos, 5 tareas de la próxima semana.'],
];

const ficha = new Table({
  width: { size: convertInchesToTwip(6.7), type: WidthType.DXA },
  columnWidths: [convertInchesToTwip(1.7), convertInchesToTwip(5.0)],
  rows: fichaRows.map(([a, b], i) => new TableRow({
    children: [
      new TableCell({
        width: { size: convertInchesToTwip(1.7), type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill: 'EAF2FD' },
        margins: { top: 80, bottom: 80, left: 110, right: 110 },
        children: [p([r(a, { bold: true, size: 20, color: AZUL })])],
      }),
      new TableCell({
        width: { size: convertInchesToTwip(5.0), type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill: i % 2 ? 'F7FAFE' : 'FFFFFF' },
        margins: { top: 80, bottom: 80, left: 110, right: 110 },
        children: [p([r(b, { size: 20, color: '1A1A1A' })])],
      }),
    ],
  })),
});

const D = [];

D.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { after: 40 },
  children: [r('Guion del video de avance N.º 2', { size: 40, bold: true, color: AZUL })],
}));
D.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { after: 40 },
  children: [r('Definición del problema + trabajos relacionados', { size: 26, color: '1A1A1A' })],
}));
D.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { after: 30 },
  children: [r('Actividad Final de Graduación 1 · MDS3050 · Equipo 2 (Team2)', { size: 21, color: TINTA2 })],
}));
D.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { after: 240 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: AZUL } },
  children: [r('José Jesús Romero Fuenmayor · Roberto Ignacio Ávila Escobar · Amaru Simón Agüero Jiménez · Esteban Adolfo González Rodríguez', { size: 18, color: GRIS })],
}));

D.push(ficha);
D.push(p([]));
D.push(cuerpo([
  r('Indicaciones de grabación. ', { bold: true }),
  habla('Usen el puntero o láser de PowerPoint para guiar la vista hacia lo que se está explicando, especialmente en la figura de la brecha y en las tablas. Todo lo metodológicamente relevante que aparece en pantalla se dice también en voz alta. Si prefieren relevos, los cortes naturales son el inicio de la diapositiva 5 y el inicio de la diapositiva 9. Las indicaciones entre corchetes no se leen en voz alta.'),
]));

D.push(new Paragraph({ spacing: { before: 160, after: 80 }, children: [r('Guion por diapositiva', { size: 28, bold: true, color: AZUL })], heading: HeadingLevel.HEADING_1 }));

D.push(diapoHeader('D1', 'Portada', '0:00 a 0:20'));
D.push(cuerpo([paso(1), habla(' Hola, mi nombre es '), acot('nombre de quien graba'), habla(', integrante del Equipo 2 junto a '), acot('nombrar a los otros tres'), habla('. Este es nuestro segundo video de avance. En el video anterior definimos el problema; hoy lo presentamos completo: medimos la brecha con datos y lo posicionamos en la literatura internacional y chilena.')]));

D.push(diapoHeader('D2', 'El problema', '0:20 a 0:50'));
D.push(cuerpo([paso(2), habla(' Los objetivos de la semana fueron tres: profundizar la definición del problema, hacer la revisión de literatura y cuantificar la brecha de monitoreo. Partamos por el relato del proyecto, en una sola cadena: hay contaminación atmosférica; necesitamos conocer la exposición de las personas; existe una red de monitoreo, SINCA; esa red tiene una brecha de cobertura; eso produce una brecha de información; y nuestra propuesta de ciencia de datos busca cerrarla. Distinguimos tres cosas: el problema es que hay lugares y horas sin medición directa; importa por sus efectos en salud y decisiones; y ocurre por cómo está distribuida la red, las fuentes y el territorio. El proyecto no busca resolver las fuentes: busca estimar concentraciones donde no se miden.')]));

D.push(diapoHeader('D3', 'Conceptos clave', '0:50 a 1:10'));
D.push(cuerpo([habla('Antes de seguir, seis términos en simple. SINCA es el sistema nacional que concentra la información de las estaciones de calidad del aire. Un contaminante normado es uno con límites legales en Chile. Un reanálisis reconstruye la atmósfera pasada combinando modelo y observaciones. Una columna satelital es el total del gas en la vertical, no la concentración en superficie. L2 y L3 son niveles de procesamiento del satélite. Y a las estaciones las llamaremos mediciones de referencia para entrenar y validar.')]));

D.push(diapoHeader('D4', 'La brecha de monitoreo', '1:10 a 1:45'));
D.push(cuerpo([paso(3), habla(' Ahora la brecha, medida con los números de la propia red. '), acot('señalar el mapa'), habla(' A la izquierda, dónde está cada estación sobre el mapa de Chile: se concentran en el centro y sur. '), acot('señalar el panel central'), habla(' Al centro, estaciones por región: tres regiones, Biobío, Valparaíso y Metropolitana, concentran la mitad de las ciento nueve estaciones; Tarapacá y Magallanes tienen una cada una. '), acot('señalar el panel derecho'), habla(' Y a la derecha, la cobertura por contaminante: el material particulado se mide en casi toda la red, pero los gases solo en la mitad. En síntesis: doscientas ochenta y cuatro de las trescientas cuarenta y cinco comunas no tienen ninguna estación. La brecha es espacial y se ve espacialmente.')]));

D.push(diapoHeader('D5', 'Trabajos relacionados en el mundo', '1:45 a 2:10'));
D.push(cuerpo([habla('En el mundo el camino ya existe. Para el particulado fino hay superficies globales mensuales y productos diarios a un kilómetro, con R cuadrado del orden de cero coma ocho en validación cruzada. Para los gases hay productos diarios sin huecos en China, y el punto clave: fuera de estación el desempeño cae a cero coma seis a cero coma siete. Cuatro familias de métodos se repiten: regresión de uso de suelo, geoestadística, aprendizaje automático e híbridos físico-estadísticos.')]));

D.push(diapoHeader('D6', 'Trabajos relacionados en Chile', '2:10 a 2:45'));
D.push(cuerpo([habla('Y en Chile, ¿qué había? Esta tabla resume los trabajos nacionales con su limitación principal. '), acot('recorrer la tabla con el puntero'), habla(' Desde el año dos mil hay redes neuronales prediciendo material particulado en Santiago, y trabajos más recientes con deep learning en Santiago y Coyhaique. Todos comparten un patrón: son pronósticos temporales en estaciones que ya existen, para una ciudad. El único intento espacio-temporal reporta que el desempeño cae fuerte al alejarse de lo observado, y el estudio satelital de dos mil catorce mostró que el AOD por sí solo no basta en Santiago. Existen trabajos que resuelven el pronóstico local y las fuentes; no encontramos ninguno que cubra una superficie continua, multi-contaminante y validada para todo el territorio. Esa es exactamente la contribución de este proyecto.')]));

D.push(diapoHeader('D7', 'Hipótesis y tipo de problema', '2:45 a 3:15'));
D.push(cuerpo([habla('Nuestra hipótesis de trabajo, y vale la pena detenerse en ella: las variables satelitales, meteorológicas, territoriales y de reanálisis contienen información suficiente para estimar las concentraciones de superficie que observan las estaciones. Los objetivos dicen qué haremos; la hipótesis explica por qué creemos que el problema es resoluble con los datos disponibles. Y definimos el tipo de problema: es una regresión espacio-temporal predictiva, no explicativa ni causal. La variable objetivo es la concentración de superficie por contaminante, en microgramos por metro cúbico, a resolución de comuna por hora y día, con un modelo por contaminante.')]));

D.push(diapoHeader('D8', 'Validación por escenarios', '3:15 a 3:45'));
D.push(cuerpo([habla('La validación la elegimos pensando en el uso real. Una validación aleatoria engaña, porque la contaminación tiene autocorrelación espacial y temporal, y la red no es uniforme. Por eso: dejar una estación fuera como primera aproximación, y además bloques espaciales, macrozonas completas fuera, bloques temporales y validación hacia adelante. Y cada métrica que reportemos declarará su escenario: si predice una nueva hora, una estación nunca vista o un territorio donde nunca hubo estación.')]));

D.push(diapoHeader('D9', 'Semana 3', '3:45 a 4:10'));
D.push(cuerpo([paso(3), habla(' En resumen, esta semana medimos la brecha con los datos del repositorio, construimos la tabla de trabajos chilenos con identificadores verificados y dejamos definidos hipótesis, problema predictivo y plan de validación. '), paso(4), habla(' Los desafíos: la literatura chilena está centrada en pronóstico temporal y no en superficies, las métricas entre estudios no siempre son comparables, y definir escenarios de validación honestos exige disciplina. '), paso(5), habla(' La próxima semana viene la defensa de tema, con el documento de una plana, congelamos el diseño metodológico e iniciamos los paneles de modelamiento.')]));

D.push(diapoHeader('D10', 'Cierre', '4:10 a 4:40'));
D.push(cuerpo([habla('Cierro con la idea completa. Hay comunas y horas sin medición directa; la red cubre sesenta y una de las trescientas cuarenta y cinco comunas, y para los gases solo la mitad de las estaciones; el mundo ya resolvió problemas análogos con satélites y modelos, mientras que en Chile solo hay pronósticos por estación; creemos que los predictores disponibles contienen la información para estimar la superficie; y lo haremos con tres motores comparados y validación por bloques. Todo el detalle, con cada referencia y su identificador digital, está en el repositorio; pueden escanear el código. Muchas gracias.')]));

D.push(new Paragraph({ spacing: { before: 200, after: 80 }, children: [r('Notas de grabación', { size: 28, bold: true, color: AZUL })], heading: HeadingLevel.HEADING_1 }));
D.push(cuerpo([habla('Ensayen con cronómetro; si se pasan de 4:50, recorten primero en las diapositivas 5 y 6. Usen el modo presentador con láser en las diapositivas 4 y 6. Suban el video a OneDrive con el correo UC y verifiquen el enlace en una ventana de incógnito antes de publicarlo en Coursera.')]));
D.push(new Paragraph({ spacing: { before: 120 }, children: [r('Guion de apoyo para el Equipo 2 sobre AFG1_Video2_Presentacion_UC.pptx. Cumple la estructura oficial de 5 pasos y la duración máxima de 5 minutos.', { size: 18, color: GRIS })] }));

const doc = new Document({
  styles: { default: { document: { run: { font: F, size: 22 } } } },
  sections: [{
    properties: {
      page: { margin: { top: convertInchesToTwip(0.8), bottom: convertInchesToTwip(0.8), left: convertInchesToTwip(0.9), right: convertInchesToTwip(0.9) } },
    },
    children: D,
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync('guion_video_2.docx', buf);
  console.log('ok guion_video_2.docx');
});
