// =====================================================================
//  Video de Avance 1 — AFG 1 · Proyecto Air-Pollution (Magíster en
//  Ciencia de Datos UC). Deck con evidencia (DOIs a pie de página),
//  flujograma de datos y QR del repositorio.
// =====================================================================
const pptxgen = require('pptxgenjs');
const path = require('path');

const A = p => path.join(__dirname, 'assets', p);

// ---------- paleta (UC + sistema del proyecto) ----------
const NAVY   = '0D366B';   // dominante
const NAVY2  = '173F8A';   // azul UC
const BLUE   = '2A78D6';
const ICE    = 'EAF2FD';
const GOLD   = 'FEC60D';   // acento UC (uso puntual)
const INK    = '0B0B0B';
const INK2   = '52514E';
const MUTED  = '898781';
const CARD   = 'F4F7FC';
const WHITE  = 'FFFFFF';
const ORANGE = 'B24E1C';
const AQUA   = '0F7D57';

const FONT = 'Arial';

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE';           // 13.33 x 7.5
pres.author = 'Equipo AFG — MCD UC';
pres.title  = 'Video de Avance 1 · Estimación multi-contaminante de calidad del aire en Chile';

const W = 13.33, H = 7.5;

// ---------- referencias (verificadas) ----------
const REFS = {
  gbd:    'GBD 2021 Risk Factors Collaborators (Brauer M. et al.). Global burden and strength of evidence for 88 risk factors. The Lancet 403 (2024). doi:10.1016/S0140-6736(24)00933-4',
  who:    'Organización Mundial de la Salud. WHO global air quality guidelines: PM, O3, NO2, SO2 y CO. Ginebra (2021). ISBN 978-92-4-003422-8',
  villa:  'Villalobos A.M. et al. Wood burning pollution in southern Chile: PM2.5 source apportionment using CMB and molecular markers. Environmental Pollution 225 (2017). doi:10.1016/j.envpol.2017.02.069',
  barraza:'Barraza F. et al. Temporal evolution of main ambient PM2.5 sources in Santiago, Chile, from 1998 to 2012. Atmos. Chem. Phys. 17 (2017). doi:10.5194/acp-17-10093-2017',
  vand:   'van Donkelaar A. et al. Monthly global estimates of fine particulate matter and their uncertainty. Environ. Sci. Technol. 55 (2021). doi:10.1021/acs.est.1c05309',
  larkin: 'Larkin A. et al. Global land use regression model for nitrogen dioxide air pollution. Environ. Sci. Technol. 51 (2017). doi:10.1021/acs.est.7b01148',
  wei:    'Wei J. et al. Ground-level NO2 surveillance from space across China using interpretable spatiotemporally weighted artificial intelligence. Environ. Sci. Technol. 56 (2022). doi:10.1021/acs.est.2c03834',
  anen:   'Anenberg S.C. et al. Long-term trends in urban NO2 concentrations and associated paediatric asthma incidence. The Lancet Planetary Health 6 (2022). doi:10.1016/S2542-5196(21)00255-2',
  turner: 'Turner M.C. et al. Long-term ozone exposure and mortality in a large prospective study. Am. J. Respir. Crit. Care Med. 193 (2016). doi:10.1164/rccm.201508-1633OC',
  tropomi:'Veefkind J.P. et al. TROPOMI on the ESA Sentinel-5 Precursor. Remote Sensing of Environment 120 (2012). doi:10.1016/j.rse.2011.09.027',
  omi:    'Levelt P.F. et al. The Ozone Monitoring Instrument. IEEE Trans. Geosci. Remote Sens. 44 (2006). doi:10.1109/TGRS.2006.872333',
  mopitt: 'Deeter M.N. et al. The MOPITT Version 9 CO product. Atmos. Meas. Tech. 15 (2022). doi:10.5194/amt-15-2325-2022',
  cams:   'Inness A. et al. The CAMS reanalysis of atmospheric composition. Atmos. Chem. Phys. 19 (2019). doi:10.5194/acp-19-3515-2019',
  geoscf: 'Keller C.A. et al. Description of the NASA GEOS Composition Forecast Modeling System GEOS-CF v1.0. JAMES 13 (2021). doi:10.1029/2020MS002413',
  merra2: 'Gelaro R. et al. The Modern-Era Retrospective Analysis for Research and Applications, Version 2 (MERRA-2). J. Climate 30 (2017). doi:10.1175/JCLI-D-16-0758.1',
  era5:   'Hersbach H. et al. The ERA5 global reanalysis. Q. J. R. Meteorol. Soc. 146 (2020). doi:10.1002/qj.3803',
  maiac:  'Lyapustin A. et al. MODIS Collection 6 MAIAC algorithm. Atmos. Meas. Tech. 11 (2018). doi:10.5194/amt-11-5741-2018',
  norma:  'Ministerio del Medio Ambiente, Chile. D.S. N.º 12/2011 — Norma primaria de calidad ambiental para MP2,5 (20 µg/m³ anual).',
};
const SUP = ['¹','²','³','⁴','⁵','⁶','⁷','⁸','⁹','¹⁰','¹¹','¹²','¹³','¹⁴','¹⁵'];

// pie de página de referencias por diapositiva
function footnotes(slide, keys, opts = {}) {
  const n = keys.length;
  const lh = 0.148;
  const hBox = Math.min(0.20 + n * lh, 1.55);
  const y = (opts.y !== undefined) ? opts.y : (H - 0.28 - hBox + 0.10);
  const items = keys.map((k, i) => ({
    text: `${SUP[i]} ${REFS[k]}`,
    options: { breakLine: true },
  }));
  slide.addText(items, {
    x: 0.55, y, w: W - 1.1, h: hBox,
    fontFace: FONT, fontSize: 7.3, color: opts.color || MUTED,
    align: 'left', valign: 'top', margin: 0, lineSpacing: 9.4,
  });
}

function footer(slide, page, dark = false) {
  slide.addText(
    'Video de Avance N.º 1 · Actividad Final de Graduación 1 · Magíster en Ciencia de Datos UC',
    { x: 0.55, y: H - 0.32, w: 8.6, h: 0.24, fontFace: FONT, fontSize: 8,
      color: dark ? 'AFC6E9' : MUTED, margin: 0, valign: 'middle' });
  slide.addText(String(page),
    { x: W - 0.95, y: H - 0.32, w: 0.4, h: 0.24, fontFace: FONT, fontSize: 8,
      color: dark ? 'AFC6E9' : MUTED, align: 'right', margin: 0, valign: 'middle' });
}

function titulo(slide, texto, sub = null) {
  slide.addText(texto, { x: 0.55, y: 0.34, w: W - 1.1, h: 0.62,
    fontFace: FONT, fontSize: 27, bold: true, color: NAVY, margin: 0, valign: 'middle' });
  if (sub) slide.addText(sub, { x: 0.55, y: 0.94, w: W - 1.1, h: 0.34,
    fontFace: FONT, fontSize: 13, color: INK2, margin: 0, valign: 'middle' });
}

function iconCircle(slide, icon, x, y, d, circColor) {
  slide.addShape('ellipse', { x, y, w: d, h: d, fill: { color: circColor }, line: { type: 'none' } });
  const pad = d * 0.22;
  slide.addImage({ path: A(`icons/${icon}_w.png`), x: x + pad, y: y + pad, w: d - 2 * pad, h: d - 2 * pad });
}

// =====================================================================
// 1 · PORTADA
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: NAVY };

  // banda superior con logo UC sobre tarjeta blanca
  s.addShape('roundRect', { x: 0.55, y: 0.5, w: 3.55, h: 1.06, rectRadius: 0.09,
    fill: { color: WHITE }, line: { type: 'none' } });
  s.addImage({ path: A('logo_uc.png'), x: 0.78, y: 0.67, w: 1.264 * 1.156, h: 0.73 });

  s.addText('ACTIVIDAD FINAL DE GRADUACIÓN 1  ·  MDS3050', {
    x: 0.55, y: 1.98, w: 9.5, h: 0.3, fontFace: FONT, fontSize: 12.5,
    color: GOLD, bold: true, charSpacing: 2, margin: 0 });

  s.addText('Estimación multi-contaminante de la\ncalidad del aire en Chile', {
    x: 0.55, y: 2.30, w: 11.4, h: 1.72, fontFace: FONT, fontSize: 39, bold: true,
    color: WHITE, margin: 0, valign: 'middle', lineSpacingMultiple: 1.04 });

  s.addText('Superficies de exposición comuna × hora para PM₂.₅ · PM₁₀ · NO₂ · O₃ · SO₂ · CO,\npara todo el territorio nacional y por macrozona, validadas contra la red SINCA', {
    x: 0.55, y: 4.10, w: 11.2, h: 0.78, fontFace: FONT, fontSize: 15.5,
    color: 'CDE2FB', margin: 0, valign: 'top', lineSpacingMultiple: 1.12 });

  s.addText('VIDEO DE AVANCE N.º 1  —  DEFINICIÓN DEL PROBLEMA', {
    x: 0.55, y: 5.06, w: 9.0, h: 0.3, fontFace: FONT, fontSize: 12,
    color: 'AFC6E9', bold: true, charSpacing: 1.5, margin: 0 });

  // equipo
  const equipo = [
    'José Jesús Romero Fuenmayor',
    'Roberto Ignacio Ávila Escobar',
    'Amaru Simón Agüero Jiménez',
  ];
  equipo.forEach((n, i) => {
    const x = 0.55 + i * 3.62;
    s.addShape('roundRect', { x, y: 5.62, w: 3.42, h: 0.86, rectRadius: 0.08,
      fill: { color: '12437F' }, line: { color: '2A5CA8', width: 0.75 } });
    s.addText(n, { x: x + 0.16, y: 5.62, w: 3.1, h: 0.86, fontFace: FONT,
      fontSize: 13, bold: true, color: WHITE, margin: 0, valign: 'middle' });
  });
  s.addText('Equipo 2 (Team2)  ·  agosto de 2026', {
    x: 0.55, y: 6.72, w: 6.0, h: 0.28, fontFace: FONT, fontSize: 11,
    color: 'AFC6E9', margin: 0 });

  // QR discreto en portada
  s.addShape('roundRect', { x: W - 1.98, y: 5.62, w: 1.43, h: 1.43, rectRadius: 0.08,
    fill: { color: WHITE }, line: { type: 'none' } });
  s.addImage({ path: A('qr_repo.png'), x: W - 1.87, y: 5.73, w: 1.21, h: 1.21 });
  s.addText('Repositorio', { x: W - 2.02, y: 7.08, w: 1.5, h: 0.24, fontFace: FONT,
    fontSize: 8.5, color: 'AFC6E9', align: 'center', margin: 0 });
}

// =====================================================================
// 2 · POR QUÉ IMPORTA (contexto y motivación)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  titulo(s, '¿Por qué importa? El aire que se respira mata — y se mide poco',
    'Contexto y relevancia del problema');

  // tres stats
  const stats = [
    { big: '≈ 8 millones', small: 'de muertes al año se atribuyen a la contaminación del aire en el mundo (GBD 2021)¹', icon: 'health', c: NAVY },
    { big: '4 de 6', small: 'contaminantes normados endurecieron su guía OMS 2021² — p. ej. NO₂ anual: de 40 a 10 µg/m³', icon: 'warning', c: BLUE },
    { big: '4 ×', small: 'la norma anual chilena de PM₂.₅ cuadruplica la guía OMS vigente² ³ (20 frente a 5 µg/m³)', icon: 'map', c: AQUA },
  ];
  stats.forEach((st, i) => {
    const x = 0.55 + i * 4.15, y = 1.55, w = 3.95, h = 2.28;
    s.addShape('roundRect', { x, y, w, h, rectRadius: 0.1, fill: { color: CARD }, line: { type: 'none' } });
    iconCircle(s, st.icon, x + 0.25, y + 0.28, 0.62, st.c);
    s.addText(st.big, { x: x + 1.02, y: y + 0.2, w: w - 1.2, h: 0.78,
      fontFace: FONT, fontSize: 30, bold: true, color: st.c, margin: 0, valign: 'middle' });
    s.addText(st.small, { x: x + 0.28, y: y + 1.06, w: w - 0.56, h: 1.1,
      fontFace: FONT, fontSize: 11.5, color: INK2, margin: 0, valign: 'top', lineSpacingMultiple: 1.08 });
  });

  // Chile en dos frentes
  s.addText('En Chile el problema tiene dos caras bien documentadas', {
    x: 0.55, y: 4.06, w: 12.0, h: 0.32, fontFace: FONT, fontSize: 15, bold: true, color: NAVY, margin: 0 });

  const caras = [
    { t: 'Centro-sur: leña residencial', d: 'La quema de leña domina el PM₂.₅ invernal en ciudades como Temuco; el problema es de partículas y de los gases que las acompañan.⁴', c: ORANGE },
    { t: 'Santiago y zonas industriales', d: 'Fuentes vehiculares e industriales sostienen episodios de PM₂.₅, NO₂ y SO₂; su composición cambió durante 15 años de gestión.⁵', c: BLUE },
  ];
  caras.forEach((cc, i) => {
    const x = 0.55 + i * 6.25, y = 4.46, w = 6.05, h = 1.32;
    s.addShape('roundRect', { x, y, w, h, rectRadius: 0.1, fill: { color: WHITE },
      line: { color: 'D8DEE9', width: 1 } });
    s.addText(cc.t, { x: x + 0.24, y: y + 0.12, w: w - 0.48, h: 0.3,
      fontFace: FONT, fontSize: 13, bold: true, color: cc.c, margin: 0 });
    s.addText(cc.d, { x: x + 0.24, y: y + 0.44, w: w - 0.48, h: 0.82,
      fontFace: FONT, fontSize: 11, color: INK2, margin: 0, valign: 'top', lineSpacingMultiple: 1.06 });
  });

  footnotes(s, ['gbd', 'who', 'norma', 'villa', 'barraza'], { y: 5.98 });
  footer(s, 2);
}

// =====================================================================
// 3 · EL PROBLEMA
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  s.addText('El problema: los gases casi no se vigilan\nfuera de las grandes ciudades', { x: 0.55, y: 0.3, w: W - 1.1, h: 1.06,
    fontFace: FONT, fontSize: 27, bold: true, color: NAVY, margin: 0, valign: 'middle', lineSpacingMultiple: 1.0 });
  s.addText('Definición del problema del proyecto', { x: 0.55, y: 1.4, w: W - 1.1, h: 0.3,
    fontFace: FONT, fontSize: 13, color: INK2, margin: 0, valign: 'middle' });

  // formulación (caja destacada)
  s.addShape('roundRect', { x: 0.55, y: 1.86, w: 7.5, h: 3.0, rectRadius: 0.1,
    fill: { color: ICE }, line: { color: BLUE, width: 1.25 } });
  s.addText('Formulación', { x: 0.83, y: 2.04, w: 3.0, h: 0.3, fontFace: FONT,
    fontSize: 12, bold: true, color: NAVY, margin: 0, charSpacing: 1 });
  s.addText(
    'La vigilancia de calidad del aire en Chile descansa en ~109 estaciones SINCA concentradas en centros urbanos; para los gases (NO₂, O₃, SO₂, CO) la cobertura es aún menor que para el material particulado. No existe una superficie pública, continua y validada de estos contaminantes para todo el territorio. Proponemos estimarla a resolución comuna × hora / día combinando satélites, reanálisis y predictores locales, con la red SINCA como única verdad-terreno, y reportarla a escala nacional y por macrozona.',
    { x: 0.83, y: 2.36, w: 6.95, h: 2.36, fontFace: FONT, fontSize: 12.5,
      color: INK, margin: 0, valign: 'top', lineSpacingMultiple: 1.13 });

  // tarjetas laterales: unidad/horizonte/alcance
  const lat = [
    { t: 'Unidad de análisis', d: 'comuna × hora (y día), 345 comunas; agregación por macrozona', icon: 'map' },
    { t: 'Horizonte temporal', d: 'según fuente: MOPITT 2000+ · OMI 2004+ · CAMS 2003+ · TROPOMI/GEOS-CF 2018+', icon: 'calendar' },
    { t: 'Alcance acotado', d: 'estimar bien y validar contra SINCA; sin validación epidemiológica (recomendación docente)', icon: 'target' },
  ];
  lat.forEach((l, i) => {
    const x = 8.35, y = 1.86 + i * 1.04, w = 4.43, h = 0.92;
    s.addShape('roundRect', { x, y, w, h, rectRadius: 0.09, fill: { color: CARD }, line: { type: 'none' } });
    iconCircle(s, l.icon, x + 0.14, y + 0.17, 0.56, NAVY);
    s.addText(l.t, { x: x + 0.84, y: y + 0.08, w: w - 0.95, h: 0.28,
      fontFace: FONT, fontSize: 11.5, bold: true, color: NAVY, margin: 0 });
    s.addText(l.d, { x: x + 0.84, y: y + 0.34, w: w - 0.95, h: 0.56,
      fontFace: FONT, fontSize: 9.6, color: INK2, margin: 0, valign: 'top', lineSpacingMultiple: 1.02 });
  });

  // por qué nosotros / continuidad
  s.addShape('roundRect', { x: 0.55, y: 5.12, w: 12.23, h: 1.28, rectRadius: 0.1,
    fill: { color: WHITE }, line: { color: 'D8DEE9', width: 1 } });
  iconCircle(s, 'science', 0.82, 5.4, 0.72, AQUA);
  s.addText([
    { text: 'Extensión natural de un trabajo ya construido. ', options: { bold: true, color: INK } },
    { text: 'El equipo parte de un modelo horario gap-free de PM₂.₅ (comuna × hora, percepción remota + reanálisis) desarrollado y validado previamente para Chile; este proyecto extiende ese pipeline a los gases y al PM₁₀, con estimación robusta para todo Chile y por macrozona.', options: { color: INK2 } },
  ], { x: 1.72, y: 5.26, w: 10.9, h: 1.04, fontFace: FONT, fontSize: 11.5,
      margin: 0, valign: 'middle', lineSpacingMultiple: 1.08 });

  footer(s, 3);
}

// =====================================================================
// 4 · EVIDENCIA: SE PUEDE HACER (precedentes)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  titulo(s, 'La evidencia dice que se puede: precedentes internacionales',
    'Estimación satelital de contaminantes de superficie, publicada y validada');

  const cards = [
    { t: 'PM₂.₅ global mensual', d: 'Estimaciones globales de PM₂.₅ con incertidumbre, combinando satélite + modelo + estaciones (base del producto ACAG que usamos).¹', tag: 'van Donkelaar 2021' },
    { t: 'NO₂ global (LUR)', d: 'Modelo global de regresión de uso de suelo para NO₂ anual — el precedente de escalar gases a territorio completo.²', tag: 'Larkin 2017' },
    { t: 'NO₂ diario con IA', d: 'NO₂ de superficie sin huecos para toda China con IA espaciotemporal interpretable — el estándar técnico al que apuntamos.³', tag: 'Wei 2022' },
    { t: 'Gases → decisiones', d: 'Con esas superficies se estiman impactos: tendencias urbanas de NO₂ y asma pediátrica⁴; el O₃ de largo plazo se asocia a mortalidad.⁵', tag: 'Anenberg 2022 · Turner 2016' },
  ];
  cards.forEach((c, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = 0.55 + col * 6.25, y = 1.62 + row * 1.78, w = 6.05, h = 1.6;
    s.addShape('roundRect', { x, y, w, h, rectRadius: 0.1, fill: { color: CARD }, line: { type: 'none' } });
    s.addText(c.t, { x: x + 0.26, y: y + 0.14, w: w - 2.2, h: 0.32,
      fontFace: FONT, fontSize: 14.5, bold: true, color: NAVY, margin: 0 });
    s.addShape('roundRect', { x: x + w - 2.12, y: y + 0.16, w: 1.9, h: 0.3, rectRadius: 0.06,
      fill: { color: ICE }, line: { type: 'none' } });
    s.addText(c.tag, { x: x + w - 2.12, y: y + 0.16, w: 1.9, h: 0.3, fontFace: FONT,
      fontSize: 8.4, bold: true, color: NAVY, align: 'center', valign: 'middle', margin: 0 });
    s.addText(c.d, { x: x + 0.26, y: y + 0.5, w: w - 0.52, h: 1.18,
      fontFace: FONT, fontSize: 11.3, color: INK2, margin: 0, valign: 'top', lineSpacingMultiple: 1.08 });
  });

  s.addText([
    { text: 'Brecha que abordamos: ', options: { bold: true, color: NAVY } },
    { text: 'para Chile no existe un producto multi-gas continuo, público y validado por estación; los precedentes existen para PM₂.₅ global y para gases en el hemisferio norte.', options: { color: INK2 } },
  ], { x: 0.55, y: 5.24, w: 12.23, h: 0.42, fontFace: FONT, fontSize: 12, margin: 0, valign: 'middle' });

  footnotes(s, ['vand', 'larkin', 'wei', 'anen', 'turner'], { y: 5.92 });
  footer(s, 4);
}

// =====================================================================
// 5 · OBJETIVOS
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  titulo(s, 'Objetivo general y objetivos específicos');

  // objetivo general
  s.addShape('roundRect', { x: 0.55, y: 1.35, w: 12.23, h: 1.42, rectRadius: 0.1,
    fill: { color: NAVY }, line: { type: 'none' } });
  iconCircle(s, 'target', 0.87, 1.63, 0.85, BLUE);
  s.addText([
    { text: 'OBJETIVO GENERAL — ', options: { bold: true, color: GOLD } },
    { text: 'Generar y validar superficies de exposición de PM₂.₅, PM₁₀, NO₂, O₃, SO₂ y CO a resolución comuna × hora / día para todo Chile, agregadas por macrozona, mediante un pipeline reproducible que integra satélites, reanálisis y predictores locales, evaluado contra la red SINCA.', options: { color: WHITE } },
  ], { x: 1.95, y: 1.5, w: 10.6, h: 1.14, fontFace: FONT, fontSize: 13.5,
      margin: 0, valign: 'middle', lineSpacingMultiple: 1.1 });

  const oes = [
    { n: 'OE1', t: 'Consolidar el pipeline de descarga y procesamiento multi-fuente (10 productos satelitales / reanálisis + SINCA), con recorte a Chile y agregación comunal.', icon: 'download' },
    { n: 'OE2', t: 'Construir paneles de modelamiento por contaminante uniendo predictores satelitales, meteorológicos y estáticos con las observaciones SINCA.', icon: 'storage' },
    { n: 'OE3', t: 'Entrenar y comparar motores de estimación (GWR, gradient boosting, kriging) con validación cruzada dejando una estación fuera (LOSO).', icon: 'science' },
    { n: 'OE4', t: 'Producir las superficies comuna × hora / día y reportar métricas (R², RMSE, sesgo) por contaminante, estación y macrozona.', icon: 'map' },
    { n: 'OE5', t: 'Publicar el proyecto como repositorio abierto y reproducible (scripts, credenciales de ejemplo, sitio de documentación).', icon: 'checklist' },
  ];
  oes.forEach((o, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = 0.55 + col * 6.25, y = 3.02 + row * 1.28, w = 6.05, h = 1.14;
    s.addShape('roundRect', { x, y, w, h, rectRadius: 0.09, fill: { color: CARD }, line: { type: 'none' } });
    iconCircle(s, o.icon, x + 0.16, y + 0.26, 0.62, BLUE);
    s.addText(o.n, { x: x + 0.9, y: y + 0.1, w: 0.75, h: 0.3, fontFace: FONT,
      fontSize: 12.5, bold: true, color: NAVY, margin: 0 });
    s.addText(o.t, { x: x + 0.9, y: y + 0.36, w: w - 1.1, h: 0.74,
      fontFace: FONT, fontSize: 10.3, color: INK2, margin: 0, valign: 'top', lineSpacingMultiple: 1.04 });
  });

  s.addText([
    { text: 'Hipótesis de trabajo: ', options: { bold: true, italic: true, color: NAVY } },
    { text: 'los predictores satelitales y de reanálisis permiten estimar los gases de superficie con desempeño comparable al reportado internacionalmente, incluso en macrozonas con pocas estaciones.', options: { italic: true, color: INK2 } },
  ], { x: 6.8, y: 5.72, w: 5.98, h: 1.1, fontFace: FONT, fontSize: 11, margin: 0, valign: 'top', lineSpacingMultiple: 1.1 });

  footer(s, 5);
}

// =====================================================================
// 6 · FLUJOGRAMA
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  titulo(s, 'Flujograma: de dónde salen los datos y cómo se transforman');
  // figura 3696x2001 → ratio 1.847; w=12.23 → h=6.62 (no cabe). w=11.6 → h=6.28. Área útil ~5.9
  const w = 10.9, h = w / (3696 / 2001);
  s.addImage({ path: A('flujograma_datos.png'), x: (W - w) / 2, y: 1.28, w, h });
  footer(s, 6);
}

// =====================================================================
// 7 · FUENTES POR CONTAMINANTE (tabla)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  titulo(s, 'Fuentes de datos por contaminante',
    'Identificadores de producto verificados en los catálogos oficiales (CMR / ADS / S3); SINCA como verdad-terreno en los 6 contaminantes');

  const hdr = { fill: { color: NAVY }, color: WHITE, bold: true, fontSize: 11.5, valign: 'middle' };
  const cell = { fontSize: 10.6, color: INK, valign: 'middle' };
  const alt = { fill: { color: CARD } };

  const rows = [
    [
      { text: 'Contaminante', options: hdr },
      { text: 'Satélite (columna / L2–L3)', options: hdr },
      { text: 'Reanálisis / superficie', options: hdr },
      { text: 'Cobertura', options: hdr },
    ],
    [
      { text: 'PM₂.₅', options: { ...cell, bold: true } },
      { text: 'MAIAC AOD¹ · MODIS AOD 3K (predictores)', options: cell },
      { text: 'ACAG superficie² · MERRA-2³ · CAMS⁴ · GEOS-CF⁵', options: cell },
      { text: '2000+', options: cell },
    ],
    [
      { text: 'PM₁₀', options: { ...cell, bold: true, ...alt } },
      { text: 'MODIS AOD (predictor)', options: { ...cell, ...alt } },
      { text: 'CAMS⁴ · MERRA-2 (polvo)³', options: { ...cell, ...alt } },
      { text: '2003+', options: { ...cell, ...alt } },
    ],
    [
      { text: 'NO₂', options: { ...cell, bold: true } },
      { text: 'TROPOMI⁶ · OMI⁷', options: cell },
      { text: 'CAMS⁴ · GEOS-CF⁵', options: cell },
      { text: '2004+', options: cell },
    ],
    [
      { text: 'O₃', options: { ...cell, bold: true, ...alt } },
      { text: 'TROPOMI⁶ · OMI⁷', options: { ...cell, ...alt } },
      { text: 'MERRA-2³ · CAMS⁴ · GEOS-CF⁵', options: { ...cell, ...alt } },
      { text: '2004+', options: { ...cell, ...alt } },
    ],
    [
      { text: 'SO₂', options: { ...cell, bold: true } },
      { text: 'TROPOMI⁶ · OMI⁷', options: cell },
      { text: 'CAMS⁴ · GEOS-CF⁵', options: cell },
      { text: '2004+', options: cell },
    ],
    [
      { text: 'CO', options: { ...cell, bold: true, ...alt } },
      { text: 'TROPOMI⁶ · MOPITT⁸', options: { ...cell, ...alt } },
      { text: 'CAMS⁴ · GEOS-CF⁵', options: { ...cell, ...alt } },
      { text: '2000+', options: { ...cell, ...alt } },
    ],
  ];

  s.addTable(rows, {
    x: 0.55, y: 1.62, w: 12.23,
    colW: [1.55, 4.6, 4.53, 1.55],
    border: { type: 'solid', color: 'D8DEE9', pt: 0.75 },
    rowH: 0.42, margin: 0.06, fontFace: FONT,
  });

  s.addText([
    { text: 'Predictores comunes a los 6: ', options: { bold: true, color: NAVY } },
    { text: 'meteorología ERA5 / ERA5-Land⁹ y MERRA-2³, uso de suelo ESA CCI, red vial OSM, altitud NASADEM, luces nocturnas VIIRS y censo (población, leña).', options: { color: INK2 } },
  ], { x: 0.55, y: 4.92, w: 12.23, h: 0.55, fontFace: FONT, fontSize: 11.5, margin: 0, valign: 'top' });

  footnotes(s, ['maiac', 'vand', 'merra2', 'cams', 'geoscf', 'tropomi', 'omi', 'mopitt', 'era5'], { y: 5.5 });
  footer(s, 7);
}

// =====================================================================
// 8 · AVANCES DE LA SEMANA / DESAFÍOS / PRÓXIMOS PASOS
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  titulo(s, 'Semana 1–2: qué hicimos, qué costó y qué viene');

  const cols = [
    { t: 'Objetivos de la semana', icon: 'checklist', c: NAVY, items: [
      'Plantear la problemática real como proyecto de ciencia de datos',
      'Delimitar objetivo general y específicos',
      'Dejar operativa la obtención de datos multi-fuente',
    ]},
    { t: 'Tareas realizadas', icon: 'download', c: BLUE, items: [
      'Repositorio público montado, con estructura reproducible y bibliografía APA',
      'Descargadores por contaminante con IDs verificados en CMR / ADS / S3',
      'Recorte a Chile «al vuelo» (~5 % del volumen global) y agregación comunal',
      'Config SINCA: 109 estaciones, 6 contaminantes, exportador automatizado',
    ]},
    { t: 'Desafíos', icon: 'warning', c: ORANGE, items: [
      'Volumen: TROPOMI sin recorte ≈ 13 TB; MERRA-2 ≈ 1 TB',
      'Credenciales y cuotas (Earthdata, Copernicus ADS) y reintentos ante caídas',
      'Cobertura temporal heterogénea entre sensores (2000+ / 2004+ / 2018+)',
    ]},
    { t: 'Próxima semana', icon: 'calendar', c: AQUA, items: [
      'Revisión de literatura por contaminante (video de avance N.º 2)',
      'Definir métricas objetivo y líneas base por macrozona',
      'Preparar la defensa de tema (semana 4)',
    ]},
  ];
  cols.forEach((c, i) => {
    const x = 0.55 + i * 3.14, y = 1.5, w = 2.98, h = 4.55;
    s.addShape('roundRect', { x, y, w, h, rectRadius: 0.1, fill: { color: CARD }, line: { type: 'none' } });
    iconCircle(s, c.icon, x + 0.2, y + 0.2, 0.6, c.c);
    s.addText(c.t, { x: x + 0.92, y: y + 0.24, w: w - 1.05, h: 0.56, fontFace: FONT,
      fontSize: 13, bold: true, color: c.c, margin: 0, valign: 'middle' });
    s.addText(c.items.map((it, k) => ({
      text: it, options: { bullet: { characterCode: '2022', indent: 8 }, breakLine: k < c.items.length - 1 },
    })), { x: x + 0.22, y: y + 0.95, w: w - 0.44, h: h - 1.1, fontFace: FONT,
      fontSize: 10.2, color: INK2, margin: 0, valign: 'top', paraSpaceAfter: 6, lineSpacingMultiple: 1.05 });
  });

  footer(s, 8);
}

// =====================================================================
// 9 · CIERRE + QR
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: NAVY };

  s.addText('Todo el proyecto vive aquí — abierto y reproducible', {
    x: 0.7, y: 0.75, w: 8.3, h: 1.3, fontFace: FONT, fontSize: 30, bold: true,
    color: WHITE, margin: 0, valign: 'middle', lineSpacingMultiple: 1.05 });

  const bullets = [
    'scripts_pipeline/ — descarga y procesamiento por contaminante (con --dry-run y reintentos)',
    'scripts_superficie/ — modelos, validación LOSO y figuras por contaminante',
    'docs/ — sitio Quarto bilingüe con bibliografía APA consolidada',
    'Datos pesados regenerables con credenciales propias (Earthdata / ADS); resultados y figuras versionados',
  ];
  s.addText(bullets.map((b, k) => ({
    text: b, options: { bullet: { characterCode: '2022', indent: 10 }, breakLine: k < bullets.length - 1 },
  })), { x: 0.7, y: 2.25, w: 7.9, h: 2.6, fontFace: FONT, fontSize: 13.5,
    color: 'CDE2FB', margin: 0, valign: 'top', paraSpaceAfter: 10, lineSpacingMultiple: 1.1 });

  s.addShape('roundRect', { x: 0.7, y: 4.95, w: 7.9, h: 0.78, rectRadius: 0.09,
    fill: { color: '12437F' }, line: { color: '2A5CA8', width: 0.75 } });
  s.addImage({ path: A('icons/github_w.png'), x: 0.95, y: 5.13, w: 0.42, h: 0.42 });
  s.addText('github.com/AmaruSimonAgueroJimenez/Air-Pollution', {
    x: 1.5, y: 4.95, w: 7.0, h: 0.78, fontFace: FONT, fontSize: 15.5, bold: true,
    color: WHITE, margin: 0, valign: 'middle' });

  // QR grande
  s.addShape('roundRect', { x: 9.35, y: 1.55, w: 3.3, h: 3.86, rectRadius: 0.12,
    fill: { color: WHITE }, line: { type: 'none' } });
  s.addImage({ path: A('qr_repo.png'), x: 9.63, y: 1.83, w: 2.74, h: 2.74 });
  s.addText('Escanea para ver el repositorio,\nel pipeline y la documentación', {
    x: 9.5, y: 4.62, w: 3.0, h: 0.68, fontFace: FONT, fontSize: 10.5, color: NAVY,
    align: 'center', margin: 0, valign: 'top', lineSpacingMultiple: 1.05 });

  s.addText('Equipo 2 — José J. Romero · Roberto I. Ávila · Amaru S. Agüero        ¡Gracias!', {
    x: 0.7, y: 6.65, w: 12.0, h: 0.35, fontFace: FONT, fontSize: 12.5,
    color: 'AFC6E9', margin: 0 });

  footer(s, 9, true);
}

pres.writeFile({ fileName: path.join(__dirname, 'AFG1_Video1_Presentacion.pptx') })
  .then(() => console.log('deck ok'));
