#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Video de avance N.º 2, reconstruido según el feedback del video 1
(S. Contreras): narrativa ordenada, brecha cuantificada, conceptos definidos,
estado del arte chileno, hipótesis explicada, problema predictivo y validación
por escenarios. Menos cajas, más tablas y figuras."""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

NAVY = RGBColor(0x1F, 0x49, 0x7D)
UCBLUE = RGBColor(0x33, 0x66, 0xCC)
DARK = RGBColor(0x17, 0x37, 0x5D)
INK = RGBColor(0x1A, 0x1A, 0x1A)
INK2 = RGBColor(0x52, 0x51, 0x4E)
MUTED = RGBColor(0x89, 0x87, 0x81)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
CARD = RGBColor(0xF2, 0xF6, 0xFC)
ICE = RGBColor(0xEA, 0xF2, 0xFD)
GOLD = RGBColor(0xFF, 0xE2, 0x00)
ORANGE = RGBColor(0xB2, 0x4E, 0x1C)
AQUA = RGBColor(0x0F, 0x7D, 0x57)
LIGHTBLUE = RGBColor(0xCD, 0xE2, 0xFB)
BORDER = RGBColor(0xD8, 0xDE, 0xE9)
CREAM = RGBColor(0xFD, 0xF2, 0xEC)

F = 'Calibri'
A = lambda p: f'/home/claude/airppt/assets/{p}'

REFS = {
  'vd16':   'van Donkelaar A. et al. Global estimates of fine particulate matter using a combined geophysical-statistical method with information from satellites, models, and monitors. Environ. Sci. Technol. 50 (2016). doi:10.1021/acs.est.5b05833',
  'vand':   'van Donkelaar A. et al. Monthly global estimates of fine particulate matter and their uncertainty. Environ. Sci. Technol. 55 (2021). doi:10.1021/acs.est.1c05309',
  'di19':   'Di Q. et al. An ensemble-based model of PM2.5 concentration across the contiguous United States with high spatiotemporal resolution. Environment International (2019). doi:10.1016/j.envint.2019.104909',
  'larkin': 'Larkin A. et al. Global land use regression model for nitrogen dioxide air pollution. Environ. Sci. Technol. 51 (2017). doi:10.1021/acs.est.7b01148',
  'wei':    'Wei J. et al. Ground-level NO2 surveillance from space across China using interpretable spatiotemporally weighted artificial intelligence. Environ. Sci. Technol. 56 (2022). doi:10.1021/acs.est.2c03834',
  'wei23':  'Wei J. et al. Ground-level gaseous pollutants (NO2, SO2, and CO) in China: daily seamless mapping and spatiotemporal variations. Atmos. Chem. Phys. 23, 1511–1532 (2023). doi:10.5194/acp-23-1511-2023',
  'hoek':   'Hoek G. et al. A review of land-use regression models to assess spatial variation of outdoor air pollution. Atmospheric Environment 42 (2008). doi:10.1016/j.atmosenv.2008.05.057',
  'perez00':'Pérez P. et al. Prediction of PM2.5 concentrations several hours in advance using neural networks in Santiago, Chile. Atmospheric Environment 34 (2000). doi:10.1016/S1352-2310(99)00316-7',
  'perez16':'Pérez P. y Gramsch E. Forecasting hourly PM2.5 in Santiago de Chile with emphasis on night episodes. Atmospheric Environment 124 (2016). doi:10.1016/j.atmosenv.2015.11.016',
  'menares':'Menares C. et al. Forecasting PM2.5 levels in Santiago de Chile using deep learning neural networks. Urban Climate 38 (2021). doi:10.1016/j.uclim.2021.100906',
  'peralta':'Peralta B. et al. Space-time prediction of PM2.5 concentrations in Santiago de Chile using LSTM networks. Applied Sciences 12, 11317 (2022). doi:10.3390/app122211317',
  'perez20':'Pérez P. y Menares C. PM2.5 forecasting in Coyhaique, the most polluted city in the Americas. Urban Climate 32 (2020). doi:10.1016/j.uclim.2020.100608',
  'escrib': 'Escribano J. et al. Satellite retrievals of aerosol optical depth over a subtropical urban area: the role of stratification and surface reflectance. Aerosol and Air Quality Research 14 (2014). doi:10.4209/aaqr.2013.03.0082',
  'villa':  'Villalobos A.M. et al. Wood burning pollution in southern Chile: PM2.5 source apportionment using CMB and molecular markers. Environmental Pollution 225 (2017). doi:10.1016/j.envpol.2017.02.069',
  'barraza':'Barraza F. et al. Temporal evolution of main ambient PM2.5 sources in Santiago, Chile, 1998–2012. Atmos. Chem. Phys. 17 (2017). doi:10.5194/acp-17-10093-2017',
}
SUP = ['¹','²','³','⁴','⁵','⁶','⁷','⁸','⁹']

prs = Presentation('base11.pptx')
_sldIdLst = prs.slides._sldIdLst
_sldIdLst.remove(list(_sldIdLst)[9])  # sin diapositiva de síntesis: 10 en total
S = prs.slides


def no_line(shape):
    shape.line.fill.background()


def no_shadow(shape):
    el = shape._element.spPr
    if el.find(qn('a:effectLst')) is None:
        from lxml import etree
        el.append(etree.SubElement(el, qn('a:effectLst')))


def box(slide, x, y, w, h, fill, line=None, radius=0.10):
    sp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    sp.adjustments[0] = radius
    sp.fill.solid(); sp.fill.fore_color.rgb = fill
    if line is None:
        no_line(sp)
    else:
        sp.line.color.rgb = line; sp.line.width = Pt(1)
    no_shadow(sp)
    sp.text_frame.paragraphs[0].text = ''
    return sp


def text(slide, x, y, w, h, runs, size=10, color=INK, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, leading=1.0, space_after=0, wrap=True):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = wrap
    tf.vertical_anchor = anchor
    for m in ('margin_left', 'margin_right', 'margin_top', 'margin_bottom'):
        setattr(tf, m, 0)
    if isinstance(runs, str):
        runs = [[(runs, {})]]
    elif runs and isinstance(runs[0], tuple):
        runs = [runs]
    first = True
    for para in runs:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.alignment = align
        if leading != 1.0:
            p.line_spacing = leading
        if space_after:
            p.space_after = Pt(space_after)
        for t, ov in para:
            r = p.add_run(); r.text = t
            r.font.name = F
            r.font.size = Pt(ov.get('size', size))
            r.font.bold = ov.get('bold', bold)
            r.font.italic = ov.get('italic', False)
            r.font.color.rgb = ov.get('color', color)
    return tb


def bullets(slide, x, y, w, h, items, size=9, color=INK2, gap=4, leading=1.0):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True
    for m in ('margin_left', 'margin_right', 'margin_top', 'margin_bottom'):
        setattr(tf, m, 0)
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap)
        if leading != 1.0:
            p.line_spacing = leading
        r = p.add_run(); r.text = '• ' + it
        r.font.name = F; r.font.size = Pt(size); r.font.color.rgb = color
    return tb


def footnotes(slide, keys, y, w=9.0, x=0.5, size=6.0, two_cols=False):
    def block(ks, sup0, bx, bw):
        paras = [[(f'{SUP[sup0 + i]} {REFS[k]}', {})] for i, k in enumerate(ks)]
        text(slide, bx, y, bw, 5.35 - y, paras, size=size, color=MUTED, leading=1.0, space_after=1)
    if two_cols:
        mid = (len(keys) + 1) // 2
        block(keys[:mid], 0, x, 4.45)
        block(keys[mid:], mid, x + 4.6, 4.4)
    else:
        block(keys, 0, x, w)


def set_title(slide, texto, size=20):
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == 0 or 'Título' in ph.name or 'Title' in ph.name:
            tf = ph.text_frame
            tf.word_wrap = True
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = tf.paragraphs[0]
            r = p.add_run(); r.text = texto
            r.font.name = F; r.font.size = Pt(size); r.font.bold = True
            r.font.color.rgb = WHITE
            return ph


def drop_content_placeholders(slide):
    for ph in list(slide.placeholders):
        if 'contenido' in ph.name.lower():
            ph._element.getparent().remove(ph._element)


# =====================================================================
# S0: portada
# =====================================================================
s = S[0]
for ph in s.placeholders:
    if 'Título' in ph.name:
        tf = ph.text_frame; tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        r = p.add_run(); r.text = 'Estimación multi-contaminante de la calidad del aire en Chile'
        r.font.name = F; r.font.size = Pt(26); r.font.bold = True; r.font.color.rgb = DARK
    elif 'Subtítulo' in ph.name:
        ph.left = Inches(0.67); ph.width = Inches(8.5); ph.top = Inches(3.02); ph.height = Inches(1.2)
        tf = ph.text_frame; tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        r = p.add_run()
        r.text = ('El problema ordenado, la brecha de monitoreo cuantificada con la red SINCA y lo que dicen '
                  'la literatura internacional y chilena para estimar PM₂.₅ · PM₁₀ · NO₂ · O₃ · SO₂ · CO')
        r.font.name = F; r.font.size = Pt(13); r.font.color.rgb = INK2
text(s, 0.67, 1.30, 8.5, 0.3, [( 'ACTIVIDAD FINAL DE GRADUACIÓN 1  ·  MDS3050  ·  VIDEO DE AVANCE N.º 2: DEFINICIÓN DEL PROBLEMA + TRABAJOS RELACIONADOS', {})],
     size=9.5, color=UCBLUE, bold=True)
equipo = ['José Jesús Romero Fuenmayor', 'Roberto Ignacio Ávila Escobar',
          'Amaru Simón Agüero Jiménez', 'Esteban Adolfo González Rodríguez']
for i, n in enumerate(equipo):
    x = 0.67 + i * 2.20
    box(s, x, 4.32, 2.06, 0.44, ICE, radius=0.18)
    text(s, x + 0.08, 4.32, 1.90, 0.44, n, size=8.2, bold=True, color=DARK,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
text(s, 0.67, 4.88, 8.5, 0.26, 'Equipo 2 (Team2)  ·  agosto de 2026', size=9.5, color=MUTED)

# =====================================================================
# S1: el problema, ordenado (narrativa del feedback)
# =====================================================================
s = S[1]
set_title(s, 'El problema: de la contaminación a la propuesta', size=19)
drop_content_placeholders(s)
cadena = ['Contaminación atmosférica', 'Necesidad de conocer la exposición', 'Red de monitoreo SINCA',
          'Brecha de cobertura', 'Brecha de información', 'Propuesta de Ciencia de Datos']
bw, gap = 1.34, 0.192
for i, t in enumerate(cadena):
    x = 0.5 + i * (bw + gap)
    fill = DARK if i == len(cadena) - 1 else CARD
    col = WHITE if i == len(cadena) - 1 else NAVY
    box(s, x, 1.30, bw, 0.78, fill, radius=0.14)
    text(s, x + 0.06, 1.30, bw - 0.12, 0.78, t, size=8.2, bold=True, color=col,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, leading=0.9)
    if i < len(cadena) - 1:
        text(s, x + bw - 0.015, 1.30, gap + 0.03, 0.78, '→', size=12, bold=True, color=UCBLUE,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
sep = [
    ('El problema', 'Existen lugares y horas donde no conocemos directamente la concentración de ciertos contaminantes.'),
    ('Por qué importa', 'La contaminación tiene efectos sobre la salud, el ambiente y la toma de decisiones públicas.'),
    ('Por qué ocurre', 'Distribución de las estaciones, fuentes de emisión, características del territorio y meteorología.'),
]
for i, (t, d) in enumerate(sep):
    x = 0.5 + i * 3.07
    box(s, x, 2.42, 2.93, 1.22, WHITE, line=BORDER)
    text(s, x + 0.16, 2.54, 2.6, 0.24, t, size=10, bold=True, color=UCBLUE)
    text(s, x + 0.16, 2.82, 2.6, 0.76, d, size=8.6, color=INK2, leading=1.0)
box(s, 0.5, 3.90, 9.0, 0.66, ICE)
text(s, 0.68, 3.99, 8.65, 0.5,
     [(('Alcance: '), {'bold': True, 'color': NAVY}),
      (('el proyecto no busca resolver las fuentes de contaminación; busca estimar concentraciones en '
        'lugares y momentos donde no existe una medición directa, usando las estaciones como mediciones '
        'de referencia para entrenar y validar.'), {'color': INK2})],
     size=9.4, leading=1.0)

# =====================================================================
# S2: conceptos clave
# =====================================================================
s = S[2]
set_title(s, 'Conceptos clave en 30 segundos')
drop_content_placeholders(s)
defs = [
    ('SINCA', 'Sistema de Información Nacional de Calidad del Aire (MMA): concentra la información de las estaciones que monitorean el aire en Chile.'),
    ('Contaminante normado', 'Contaminante con norma de calidad ambiental vigente en Chile, es decir, con límites legales de concentración.'),
    ('Reanálisis', 'Reconstrucción retrospectiva de la atmósfera que combina un modelo físico con observaciones históricas (p. ej. CAMS, MERRA-2).'),
    ('Columna satelital', 'Cantidad total de un gas en la vertical que observa el satélite; no es la concentración a nivel de superficie.'),
    ('Nivel L2 / L3', 'L2: producto por pasada del satélite, en su grilla original. L3: producto regrillado y agregado en el tiempo, listo para análisis.'),
    ('Mediciones de referencia', 'Observaciones de las estaciones de monitoreo que se usan para entrenar los modelos y evaluar su desempeño.'),
]
for i, (t, d) in enumerate(defs):
    col, row = i % 3, i // 3
    x, y = 0.5 + col * 3.07, 1.30 + row * 1.62
    box(s, x, y, 2.93, 1.48, CARD)
    text(s, x + 0.16, y + 0.12, 2.6, 0.26, t, size=10.5, bold=True, color=NAVY)
    text(s, x + 0.16, y + 0.42, 2.62, 1.0, d, size=8.2, color=INK2, leading=0.98)

# =====================================================================
# S3: la brecha cuantificada
# =====================================================================
s = S[3]
set_title(s, 'La brecha de monitoreo: qué cubre la red SINCA', size=19)
drop_content_placeholders(s)
text(s, 0.5, 1.20, 9.0, 0.35,
     [(('284 de las 345 comunas no tienen ninguna estación; '), {'bold': True, 'color': NAVY}),
      (('y para los gases la red efectiva es cerca de la mitad que para el material particulado.'), {'color': INK2})],
     size=11)
from PIL import Image
iw, ih = Image.open(A('brecha_sinca.png')).size
ar = iw / ih
y0 = 1.62
w = min(9.2, (5.10 - y0) * ar)
h = w / ar
s.shapes.add_picture(A('brecha_sinca.png'), Inches((10 - w) / 2), Inches(y0), Inches(w), Inches(h))

# =====================================================================
# S4: qué se ha hecho afuera
# =====================================================================
s = S[4]
set_title(s, 'Trabajos relacionados (1): estado del arte internacional', size=19)
drop_content_placeholders(s)
rows = [
    ['Contaminante', 'Qué existe hoy', 'Desempeño reportado'],
    ['PM₂.₅', 'Superficies globales mensuales con incertidumbre¹ ² y EE. UU. diario a 1 km con ensambles de aprendizaje automático³', 'R² 0.81 en validación cruzada global²'],
    ['NO₂ y O₃', 'Regresión de uso de suelo global⁴ y productos diarios sin huecos para China con IA espaciotemporal⁵', 'R² ≈ 0.84 diario en CV⁶'],
    ['SO₂ y CO', 'Los menos estudiados: el primer mapeo diario continuo (China) apareció recién en 2023⁶', 'R² 0.80 a 0.84 en CV; 0.61 a 0.70 fuera de estación⁶'],
]
tw = [1.30, 5.10, 2.60]
tbl_shape = s.shapes.add_table(4, 3, Inches(0.5), Inches(1.24), Inches(9.0), Inches(2.20))
tbl = tbl_shape.table
tbl.first_row = True; tbl.horz_banding = True
for j, wcol in enumerate(tw):
    tbl.columns[j].width = Inches(wcol)
for i in range(4):
    tbl.rows[i].height = Inches(0.34 if i == 0 else 0.60)
    for j in range(3):
        c = tbl.cell(i, j)
        c.margin_left = Inches(0.07); c.margin_right = Inches(0.05)
        c.margin_top = Inches(0.03); c.margin_bottom = Inches(0.03)
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = c.text_frame.paragraphs[0]
        r = p.add_run(); r.text = rows[i][j]
        r.font.name = F
        if i == 0:
            r.font.size = Pt(9.5); r.font.bold = True; r.font.color.rgb = WHITE
            c.fill.solid(); c.fill.fore_color.rgb = NAVY
        else:
            r.font.size = Pt(8.6); r.font.color.rgb = INK
            r.font.bold = (j == 0)
            c.fill.solid()
            c.fill.fore_color.rgb = CARD if i % 2 == 0 else WHITE
box(s, 0.5, 3.70, 9.0, 0.60, ICE)
text(s, 0.68, 3.78, 8.65, 0.46,
     [(('Cuatro familias de métodos se repiten: '), {'bold': True, 'color': NAVY}),
      (('regresión de uso de suelo⁷, geoestadística (GWR y kriging)², aprendizaje automático³ ⁵ e híbridos '
        'físico-estadísticos¹ ². La validación estándar es espacial, dejando estaciones fuera.'), {'color': INK2})],
     size=9.0, leading=0.98)
footnotes(s, ['vd16', 'vand', 'di19', 'larkin', 'wei', 'wei23', 'hoek'], y=4.44, size=5.9, two_cols=True)

# =====================================================================
# S5: qué se ha hecho en Chile
# =====================================================================
s = S[5]
set_title(s, 'Trabajos relacionados (2): estado del arte en Chile', size=19)
drop_content_placeholders(s)
rows = [
    ['Trabajo', 'Contaminante', 'Zona', 'Datos', 'Método', 'Principal limitación'],
    ['Pérez 2000¹', 'PM₂.₅', 'Santiago', '1 estación, horario', 'red neuronal', 'pronóstico temporal en un punto'],
    ['Pérez y Gramsch 2016²', 'PM₂.₅', 'Santiago', 'estaciones + meteorología', 'red neuronal', 'episodios nocturnos; sin superficie espacial'],
    ['Menares 2021³', 'PM₂.₅', 'Santiago', '10 años, 3 zonas', 'LSTM / deep learning', 'solo zonas ya monitoreadas'],
    ['Peralta 2022⁴', 'PM₂.₅', 'Santiago', '7 estaciones', 'LSTM espacio-temporal', 'R² cae de 0.74 (1 h) a 0.38 (24 h)'],
    ['Pérez y Menares 2020⁵', 'PM₂.₅', 'Coyhaique', 'estaciones + meteorología', 'red neuronal', 'una ciudad; episodios de leña'],
    ['Escribano 2014⁶', 'AOD · PM', 'Santiago', 'MODIS + AERONET', 'modelo físico simple', 'el AOD solo no basta como proxy en Santiago'],
    ['Villalobos 2017⁷ · Barraza 2017⁸', 'PM₂.₅ (fuentes)', 'Temuco · Santiago', 'filtros, especiación', 'modelo receptor (CMB)', 'caracterizan fuentes; no estiman superficies'],
]
tw = [1.72, 1.02, 0.92, 1.52, 1.42, 2.40]
tbl_shape = s.shapes.add_table(8, 6, Inches(0.5), Inches(1.20), Inches(9.0), Inches(2.30))
tbl = tbl_shape.table
tbl.first_row = True; tbl.horz_banding = True
for j, wcol in enumerate(tw):
    tbl.columns[j].width = Inches(wcol)
for i in range(8):
    tbl.rows[i].height = Inches(0.30 if i == 0 else 0.27)
    for j in range(6):
        c = tbl.cell(i, j)
        c.margin_left = Inches(0.05); c.margin_right = Inches(0.03)
        c.margin_top = Inches(0.01); c.margin_bottom = Inches(0.01)
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = c.text_frame.paragraphs[0]
        r = p.add_run(); r.text = rows[i][j]
        r.font.name = F
        if i == 0:
            r.font.size = Pt(8.2); r.font.bold = True; r.font.color.rgb = WHITE
            c.fill.solid(); c.fill.fore_color.rgb = NAVY
        else:
            r.font.size = Pt(7.2); r.font.color.rgb = INK
            r.font.bold = (j == 0)
            c.fill.solid()
            c.fill.fore_color.rgb = CARD if i % 2 == 0 else WHITE
box(s, 0.5, 3.72, 9.0, 0.62, DARK)
text(s, 0.68, 3.80, 8.65, 0.48,
     [(('La contribución: '), {'bold': True, 'color': GOLD}),
      (('en Chile existen pronósticos temporales por estación y estudios de fuentes, pero no una superficie '
        'espacial continua, multi-contaminante y validada para todo el territorio. Eso es lo que este proyecto cubre.'), {'color': WHITE})],
     size=9.2, leading=0.98)
footnotes(s, ['perez00', 'perez16', 'menares', 'peralta', 'perez20', 'escrib', 'villa', 'barraza'],
          y=4.48, size=5.7, two_cols=True)

# =====================================================================
# S6: hipótesis y tipo de problema
# =====================================================================
s = S[6]
set_title(s, 'Hipótesis de trabajo y tipo de problema', size=19)
drop_content_placeholders(s)
box(s, 0.5, 1.22, 4.42, 2.68, DARK)
text(s, 0.70, 1.38, 4.0, 0.28, 'HIPÓTESIS DE TRABAJO', size=10, bold=True, color=GOLD)
text(s, 0.70, 1.72, 4.02, 2.05,
     [[('Las variables satelitales, meteorológicas, territoriales y de reanálisis contienen información '
        'suficiente para estimar las concentraciones de superficie que observan las estaciones.', {'color': WHITE})],
      [('Los objetivos dicen qué vamos a hacer; la hipótesis explica por qué creemos que el problema '
        'puede resolverse con los datos disponibles.', {'color': LIGHTBLUE})]],
     size=9.6, leading=1.05, space_after=8)
box(s, 5.08, 1.22, 4.42, 2.68, CARD)
text(s, 5.26, 1.34, 4.1, 0.26, 'El problema predictivo, bien definido', size=10.5, bold=True, color=NAVY)
filas = [
    ('Tipo', 'regresión espacio-temporal predictiva; no busca explicar causas ni evaluar intervenciones'),
    ('Variable objetivo', 'concentración de superficie por contaminante'),
    ('Unidad', 'µg/m³ (CO en mg/m³)'),
    ('Resolución', 'comuna × hora y día, todo Chile, agregable por macrozona'),
    ('Modelos', 'un modelo por contaminante; sin enfoque multiobjetivo'),
]
yy = 1.70
for t, d in filas:
    text(s, 5.26, yy, 1.35, 0.4, t, size=8.6, bold=True, color=UCBLUE)
    text(s, 6.66, yy, 2.74, 0.44, d, size=8.2, color=INK2, leading=0.94)
    yy += 0.435
box(s, 0.5, 4.10, 9.0, 0.54, ICE)
text(s, 0.68, 4.17, 8.65, 0.4,
     [(('La secuencia completa del proyecto: '), {'bold': True, 'color': NAVY}),
      (('problema → brecha → evidencia → hipótesis → objetivos → metodología.'), {'color': INK2})],
     size=9.6)

# =====================================================================
# S7: validación por escenarios
# =====================================================================
s = S[7]
set_title(s, 'Estrategia de validación por escenarios', size=19)
drop_content_placeholders(s)
box(s, 0.5, 1.22, 4.42, 2.55, WHITE, line=BORDER)
text(s, 0.68, 1.34, 4.1, 0.26, 'El desafío: dependencia espacial y temporal', size=10, bold=True, color=ORANGE)
bullets(s, 0.68, 1.68, 4.06, 2.0, [
    'La contaminación no es independiente entre lugares: hay autocorrelación espacial',
    'Horas consecutivas están fuertemente correlacionadas',
    'La red SINCA no es uniforme: 3 regiones concentran la mitad de las estaciones',
    'Mezclar observaciones cercanas infla las métricas',
], size=8.6, gap=4, leading=0.98)
box(s, 5.08, 1.22, 4.42, 2.55, CARD)
text(s, 5.26, 1.34, 4.1, 0.26, 'Nuestra estrategia, por bloques', size=10, bold=True, color=AQUA)
bullets(s, 5.26, 1.68, 4.06, 2.0, [
    'LOSO (dejar una estación fuera) como primera aproximación',
    'Bloques espaciales y macrozonas completas fuera',
    'Bloques temporales y validación hacia adelante',
    'Reporte de métricas por contaminante, estación y macrozona',
], size=8.6, gap=4, leading=0.98)
box(s, 0.5, 3.96, 9.0, 0.72, DARK)
text(s, 0.70, 4.05, 8.6, 0.56,
     [(('Cada métrica declarará su escenario: '), {'bold': True, 'color': GOLD}),
      (('¿predice una nueva hora en una estación conocida, una estación nunca vista o un territorio donde '
        'nunca hubo estación? Fuera de estación, la literatura reporta caídas a R² 0.6 a 0.7.¹'), {'color': WHITE})],
     size=9.4, leading=1.0)
footnotes(s, ['wei23'], y=4.86)

# =====================================================================
# S8: semana 3
# =====================================================================
s = S[8]
set_title(s, 'Semana 3: qué hicimos, qué costó y qué viene')
drop_content_placeholders(s)
colsx = [
    ('Objetivos de la semana', NAVY, [
        'Profundizar la definición del problema y su evidencia',
        'Revisión de literatura internacional y chilena',
        'Cuantificar la brecha con datos del repositorio']),
    ('Tareas realizadas', UCBLUE, [
        'Brecha medida: mapa SINCA, estaciones por región y cobertura por contaminante',
        'Tabla de trabajos chilenos con DOI verificado',
        'Hipótesis y problema predictivo definidos']),
    ('Desafíos', ORANGE, [
        'La literatura chilena es de pronóstico temporal, no de superficies',
        'Métricas no comparables entre estudios',
        'Definir escenarios de validación honestos']),
    ('Próxima semana', AQUA, [
        'Defensa de tema (semana 4): documento de una plana',
        'Congelar el diseño metodológico',
        'Iniciar los paneles de modelamiento']),
]
for i, (t, c, items) in enumerate(colsx):
    x = 0.5 + i * 2.32
    box(s, x, 1.22, 2.20, 2.86, CARD)
    text(s, x + 0.16, 1.36, 1.95, 0.5, t, size=9.8, bold=True, color=c, leading=0.9)
    bullets(s, x + 0.16, 1.92, 1.9, 2.1, items, size=7.8, gap=5, leading=0.96)

# =====================================================================
# S9: cierre con QR
# =====================================================================
s = S[9]
text(s, 0.55, 1.02, 5.9, 0.75, 'Todo el detalle vive\nen el repositorio', size=19, bold=True, color=WHITE, leading=1.0)
bullets(s, 0.55, 1.95, 5.9, 1.7, [
    'Bibliografía APA con cada DOI verificado',
    'Datos y scripts de la brecha SINCA (mapa y coberturas)',
    'Matriz contaminante × método y líneas base',
    'Pipeline reproducible de descarga y procesamiento',
], size=9.5, color=LIGHTBLUE, gap=5)
box(s, 0.55, 3.78, 5.9, 0.56, RGBColor(0x11, 0x3E, 0x8F))
s.shapes.add_picture(A('icons/github_w.png'), Inches(0.72), Inches(3.92), Inches(0.28), Inches(0.28))
text(s, 1.10, 3.78, 5.3, 0.56, 'github.com/AmaruSimonAgueroJimenez/Air-Pollution', size=11.5, bold=True, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
box(s, 6.95, 1.02, 2.55, 3.32, WHITE, radius=0.06)
s.shapes.add_picture(A('qr_repo.png'), Inches(7.17), Inches(1.24), Inches(2.11), Inches(2.11))
text(s, 7.05, 3.42, 2.35, 0.8, 'Escanea para ver la bibliografía, el pipeline y la documentación',
     size=8.5, color=DARK, align=PP_ALIGN.CENTER, leading=0.95)
text(s, 0.55, 4.80, 8.9, 0.3, 'Equipo 2: José J. Romero · Roberto I. Ávila · Amaru S. Agüero · Esteban A. González          ¡Gracias!',
     size=10, bold=False, color=LIGHTBLUE)

prs.save('AFG1_Video2_Presentacion_UC.pptx')
print('ok')
