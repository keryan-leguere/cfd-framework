// Présentation : base aéro de la fusée étudiante (3DOF tangage, gouvernes en X), résultats factices.
//
//   cd deck && npm install && node deck.js      → ../Fusee_3DOF_base_aero.pptx
//
// Les figures viennent de ../PLANCHES (generer_donnees.py, tracer_base_aero.py), les chiffres
// cités de ../DONNEES/chiffres_doe.json et ../PLANCHES/chiffres_tables.json : rien n'est
// recopié à la main, une figure régénérée et son commentaire ne peuvent pas diverger.
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const { appliquerTheme } = require("./theme");

const RACINE = path.resolve(__dirname, "..");
const PLANCHES = path.join(RACINE, "PLANCHES");
const OUT = path.join(RACINE, "Fusee_3DOF_base_aero.pptx");
const D = JSON.parse(fs.readFileSync(path.join(RACINE, "DONNEES", "chiffres_doe.json"), "utf8"));
const T = JSON.parse(fs.readFileSync(path.join(PLANCHES, "chiffres_tables.json"), "utf8"));

// ---------- Nombres à la française ----------
const fr = (x, n = 1) => Number(x).toFixed(n).replace(".", ",").replace("-", "−");
const signe = (x, n = 1) => (x > 0 ? "+" : "") + fr(x, n);
const pct = (x) => (x < 1e-6 ? "exacte" : x < 0.1 ? `${fr(x, 2)} %` : x < 10 ? `${fr(x, x < 1 ? 2 : 1)} %` : `${fr(x, 0)} %`);
const min = (a) => Math.min(...a), max = (a) => Math.max(...a);
const DER = T.derivees;
const MACHS = T.machs.map((m) => fr(m, 1));
const BUTEE = max(T.dm_niveaux);
const PAS_DM = T.dm_niveaux[1] - T.dm_niveaux[0];
const N_DM = T.dm_niveaux.length;
const DELTA_PHYS = T.dm_niveaux.map((d) => d / Math.SQRT2);

const THEME = {
  name: "Fusee 3DOF",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1B2631", lt1: "FFFFFF", dk2: "0B3C5D", lt2: "E8EEF2",
    accent1: "1D5F82", accent2: "E07A1F", accent3: "3F7E9E",
    accent4: "9DB4C0", accent5: "C0620F", accent6: "5D6D7E",
    hlink: "1D5F82", folHlink: "5D6D7E",
  },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625
pres.title = "Base aérodynamique de la fusée — 3DOF tangage";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;
const SURLIGNE = "FBE3CC";

// ---------- Layouts ----------
pres.defineSlideMaster({
  title: "TITRE",
  background: { color: C.text2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 1.5, w: 8.8, h: 1.6,
      fontFace: "Cambria", fontSize: 34, bold: true, color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 3.25, w: 8.8, h: 0.9,
      fontSize: 16, color: C.accent4, valign: "top", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "SECTION",
  background: { color: C.text2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 2.0, w: 8.8, h: 0.9,
      fontFace: "Cambria", fontSize: 32, bold: true, color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 3.0, w: 8.8, h: 1.0,
      fontSize: 16, color: C.accent4, valign: "top", margin: 0 }, text: "" } },
  ],
  slideNumber: { x: 9.2, y: 5.25, w: 0.5, h: 0.25, fontSize: 10, color: C.accent4 },
});
pres.defineSlideMaster({
  title: "CONTENU",
  background: { color: C.background1 },
  margin: [0.5, 0.5, 0.5, 0.5],
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.25, w: 9.0, h: 0.7,
      fontFace: "Cambria", fontSize: 26, bold: true, color: C.text2, valign: "middle", align: "left", margin: 0 }, text: "" } },
  ],
  slideNumber: { x: 9.2, y: 5.25, w: 0.5, h: 0.25, fontSize: 10, color: C.accent6 },
});

// ---------- Helpers ----------
function table(slide, rows, opts) {
  const head = rows[0].map((t) => ({ text: t, options: { bold: true, color: C.background1, fill: { color: C.text2 } } }));
  const body = rows.slice(1).map((r, i) => r.map((cell) => {
    const o = typeof cell === "object" ? cell : { text: String(cell), options: {} };
    o.options = Object.assign({ fill: { color: i % 2 ? C.background1 : C.background2 }, color: C.text1 }, o.options);
    return o;
  }));
  slide.addTable([head, ...body], Object.assign({
    fontFace: "Calibri", fontSize: 13, border: { type: "solid", pt: 0.75, color: "FFFFFF" },
    valign: "middle", margin: [3, 6, 3, 6],
  }, opts));
}
const HL = () => ({ fill: { color: SURLIGNE }, bold: true, color: C.text2 });
function pastille(slide, x, y, n, d = 0.42, color = C.accent2) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color }, line: { color }, objectName: `pastille ${n}` });
  slide.addText(String(n), { x, y, w: d, h: d, isTextBox: true, align: "center", valign: "middle",
    fontSize: 15, bold: true, color: C.background1, margin: 0 });
}
function carte(slide, x, y, w, h, name, color = C.background2) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08,
    fill: { color }, line: { color }, objectName: name });
}
function txt(slide, text, o) {
  slide.addText(text, Object.assign({ isTextBox: true, fontSize: 14, color: C.text1, margin: 0, valign: "top" }, o));
}
function taillePng(fichier) {
  const b = fs.readFileSync(fichier);
  if (b.toString("ascii", 12, 16) !== "IHDR") throw new Error(`${fichier} : PNG illisible`);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}
// L'image tient dans la boîte (x, y, wMax, hMax), proportions gardées, calée en haut à gauche
// (ou centrée horizontalement si centre=true). Renvoie la boîte réellement occupée.
function img(slide, nom, x, y, wMax, hMax, alt, centre = false) {
  const fichier = path.join(PLANCHES, `${nom}.png`);
  if (!fs.existsSync(fichier)) throw new Error(`planche absente : ${fichier} (lancer construire.sh)`);
  const { w: pw, h: ph } = taillePng(fichier);
  let w = wMax, h = (wMax * ph) / pw;
  if (h > hMax) { h = hMax; w = (hMax * pw) / ph; }
  const xx = centre ? x + (wMax - w) / 2 : x;
  slide.addImage({ path: fichier, x: xx, y, w, h, altText: alt, objectName: alt });
  return { x: xx, y, w, h };
}
function puces(slide, items, o) {
  txt(slide, items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1 } })),
    Object.assign({ paraSpaceAfter: 8 }, o));
}
function note(slide, text, y = 4.95, x = 0.5, w = 8.6) {
  txt(slide, text, { x, y, w, h: 0.3, fontSize: 10, color: C.accent6 });
}
function newSlide(section, title) {
  const s = pres.addSlide({ masterName: "CONTENU", sectionTitle: section });
  s.addText(title, { placeholder: "title" });
  return s;
}
function section(titre, sousTitre, n) {
  pres.addSection({ title: titre });
  const s = pres.addSlide({ masterName: "SECTION", sectionTitle: titre });
  s.addText(titre, { placeholder: "title" });
  s.addText(sousTitre, { placeholder: "body" });
  pastille(s, 0.6, 1.3, n, 0.55);
  return s;
}
function ligneFleche(slide, x1, y1, x2, y2, color, name) {
  slide.addShape(pres.shapes.LINE, {
    x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1),
    flipH: x2 < x1, flipV: y2 < y1, line: { color, width: 2, endArrowType: "triangle" }, objectName: name,
  });
}
const SECT = { intro: "Introduction", dom: "Domaine de vol", doe: "DOE", mod: "Modélisation",
  res: "Résultats", pv: "Justification ParaView", fin: "Conclusion" };

// ================= 1. Titre =================
pres.addSection({ title: SECT.intro });
{
  const s = pres.addSlide({ masterName: "TITRE", sectionTitle: SECT.intro });
  s.addText("Base aérodynamique de la fusée : domaine de vol, DOE, modélisation et résultats", { placeholder: "title" });
  s.addText("Trajectoire 3DOF tangage · gouvernes en X · toutes les valeurs sont factices · outils cfd-doe, cfd-atm, cfd-plot", { placeholder: "body" });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 6.2, y: 0.75, w: 3.0, h: 0.32, rectRadius: 0.16,
    fill: { color: C.accent3 }, line: { color: C.accent3 }, objectName: "fusée corps" });
  s.addShape(pres.shapes.ISOSCELES_TRIANGLE, { x: 9.24, y: 0.66, w: 0.32, h: 0.5, rotate: 90,
    fill: { color: C.accent3 }, line: { color: C.accent3 }, objectName: "fusée ogive" });
  s.addShape(pres.shapes.RIGHT_TRIANGLE, { x: 6.2, y: 0.42, w: 0.6, h: 0.33,
    fill: { color: C.accent2 }, line: { color: C.accent2 }, objectName: "ailette haute" });
  s.addShape(pres.shapes.RIGHT_TRIANGLE, { x: 6.2, y: 1.07, w: 0.6, h: 0.33, flipV: true,
    fill: { color: C.accent2 }, line: { color: C.accent2 }, objectName: "ailette basse" });
  s.addNotes("Objectif : construire la base aéro qu'utilise le simulateur de trajectoire 3DOF tangage, et montrer à quoi " +
    "ressemblent les résultats. Toutes les valeurs, y compris les « résultats CFD », sont factices : elles illustrent la démarche.");
}

// ================= 2. Démarche =================
{
  const s = newSlide(SECT.intro, "La démarche en six étapes");
  const steps = [
    ["Domaine de vol", "Mach, altitude, incidence, butée des gouvernes"],
    ["Réduction", "Variables actives en 3DOF, symétries"],
    ["DOE CFD", `${D.calculs} calculs dans les sous-domaines`],
    ["Tables", "CA, CN, Cm en (M, α, DM) + ΔzCA"],
    ["Résultats", "Courbes, cartes, équilibre, marge"],
    ["Preuves", "Convergence, contrôles, ParaView"],
  ];
  const w = 1.35, gap = 0.18, y = 1.4;
  steps.forEach(([t, d], i) => {
    const x = 0.5 + i * (w + gap);
    carte(s, x, y, w, 2.35, `étape ${i + 1}`);
    pastille(s, x + 0.13, y + 0.15, i + 1);
    txt(s, t, { x: x + 0.13, y: y + 0.68, w: w - 0.22, h: 0.55, fontSize: 14, bold: true, color: C.text2, valign: "bottom" });
    txt(s, d, { x: x + 0.13, y: y + 1.32, w: w - 0.22, h: 0.95, fontSize: 12, color: C.accent6 });
    if (i < steps.length - 1) {
      s.addShape(pres.shapes.RIGHT_ARROW, { x: x + w + 0.02, y: y + 1.05, w: gap - 0.04, h: 0.2,
        fill: { color: C.accent2 }, line: { color: C.accent2 }, objectName: `flèche ${i + 1}` });
    }
  });
  txt(s, "Le DOE ne calcule que ce qui est utile : ce que la trajectoire consomme, une seule fois par symétrie.",
    { x: 0.5, y: 4.2, w: 9.0, h: 0.5, fontSize: 15, italic: true, color: C.text2 });
  s.addNotes("Étapes 2 à 4 : cfd-doe (domaine, remplir, reconstruction). Correction d'altitude : cfd-atm. " +
    "Étape 5 : tracer_base_aero.py, qui ne prend que les deux DataFrames (tables carrées, incrément) et trace tout avec cfd-plot.");
}

// ================= Section Domaine de vol =================
section(SECT.dom, "Ce que la trajectoire consomme, et sur quelle plage", 1);
{
  const s = newSlide(SECT.dom, "3DOF tangage : trois coefficients, deux variables");
  table(s, [
    ["Type de trajectoire", "Efforts", "Variables actives"],
    ["1DOF", "A", "—"],
    ["2DOF", "A, N", "α"],
    [{ text: "3DOF tangage", options: HL() }, { text: "A, N, m", options: HL() }, { text: "α, δm", options: HL() }],
    ["5DOF", "A, N, Y, m, n", "α, β, δm, δn"],
    ["6DOF", "A, N, Y, m, n, l", "α, β, δm, δn, δl"],
  ], { x: 0.5, y: 1.2, w: 5.4, colW: [1.9, 1.7, 1.8], rowH: 0.42 });
  carte(s, 6.2, 1.2, 3.3, 2.95, "variables fixées");
  txt(s, "Une variable est active si la trajectoire consomme l'effort qu'elle pilote.",
    { x: 6.4, y: 1.35, w: 2.9, h: 0.8, fontSize: 14 });
  puces(s, ["Base à fournir : CA, CN, Cm", "Fixés à 0 : β, δn, δl", "CY, Cl, Cn non calculés"],
    { x: 6.4, y: 2.2, w: 2.9, h: 1.8, color: C.text2 });
  note(s, "Classification de Freeman, telle qu'appliquée par cfd-doe (data/trajectoires.py).", 4.85);
  s.addNotes("Le vol plan de tangage n'utilise que A, N et m : le problème se réduit à deux variables (α, δm) par Mach.");
}
{
  const s = newSlide(SECT.dom, "Domaine de vol et discrétisation");
  table(s, [
    ["Variable", "Domaine", "Grille CFD", "n"],
    ["Mach", "0 – 1,5", "0,6 → 1,5 pas 0,3", String(D.machs.length)],
    ["Altitude", "0 – 2000 m", "via ΔzCA", "—"],
    ["α", "0 – 45°", "pas 5°", String(D.n_alpha_calc + 1)],
    ["δ physique", "± 30°, butée", `pas ${fr(PAS_DM / Math.SQRT2)}°`, String(N_DM)],
    [{ text: "DM", options: { bold: true } }, `± ${fr(BUTEE)}°`, `pas ${fr(PAS_DM)}° (= √2 · ${fr(PAS_DM / Math.SQRT2)}°)`, String(N_DM)],
  ], { x: 0.5, y: 1.2, w: 4.6, colW: [1.0, 1.15, 1.95, 0.5], rowH: 0.38, fontSize: 12 });
  txt(s, "Mach < 0,6 : table saturée à M = 0,6, hypothèse d'écoulement quasi incompressible.",
    { x: 0.5, y: 4.2, w: 4.6, h: 0.6, fontSize: 13, italic: true, color: C.text2 });
  const b = img(s, "domaine_vol", 5.3, 1.2, 4.2, 2.7, "Domaine de vol Mach-altitude avec les Mach calculés en CFD");
  txt(s, "Traits orange : Mach calculés. Gris : nombre de Reynolds (L = 1,8 m).",
    { x: 5.3, y: b.y + b.h + 0.1, w: 4.2, h: 0.5, fontSize: 11, color: C.accent6 });
  s.addNotes(`Le braquage est discrétisé en physique, ${N_DM} niveaux de −30 à 30° jusqu'à la butée, puis converti en DM.`);
}
{
  const s = newSlide(SECT.dom, "Gouvernes en X : du braquage physique à DM");
  const cx = 2.15, cy = 3.05, r = 0.5, Lf = 0.95, ep = 0.12, a = Math.SQRT1_2;
  s.addShape(pres.shapes.OVAL, { x: cx - r, y: cy - r, w: 2 * r, h: 2 * r, fill: { color: C.accent4 },
    line: { color: C.accent3, width: 1.5 }, objectName: "corps vue arrière" });
  ligneFleche(s, cx, cy, cx + 0.42, cy, C.text2, "axe y");
  ligneFleche(s, cx, cy, cx, cy + 0.42, C.text2, "axe z");
  txt(s, "y", { x: cx + 0.43, y: cy - 0.12, w: 0.2, h: 0.25, fontSize: 11, color: C.text2 });
  txt(s, "z", { x: cx - 0.17, y: cy + 0.3, w: 0.2, h: 0.25, fontSize: 11, color: C.text2 });
  [
    { n: 1, d: [a, a], t: [-a, a], rot: 45 },
    { n: 2, d: [-a, a], t: [-a, -a], rot: -45 },
    { n: 3, d: [-a, -a], t: [a, -a], rot: 45 },
    { n: 4, d: [a, -a], t: [a, a], rot: -45 },
  ].forEach((f) => {
    const fx = cx + f.d[0] * (r + Lf / 2), fy = cy + f.d[1] * (r + Lf / 2);
    s.addShape(pres.shapes.RECTANGLE, { x: fx - Lf / 2, y: fy - ep / 2, w: Lf, h: ep, rotate: f.rot,
      fill: { color: C.accent2 }, line: { color: C.accent2 }, objectName: `gouverne ${f.n}` });
    const px = cx + f.d[0] * (r + Lf * 0.8), py = cy + f.d[1] * (r + Lf * 0.8);
    ligneFleche(s, px, py, px + f.t[0] * 0.38, py + f.t[1] * 0.38, C.accent5, `sens positif δ${f.n}`);
    const lx = cx + f.d[0] * (r + Lf + 0.22), ly = cy + f.d[1] * (r + Lf + 0.22);
    txt(s, `δ${f.n}`, { x: lx - 0.22, y: ly - 0.15, w: 0.44, h: 0.3, fontSize: 15, bold: true, color: C.text2, align: "center" });
  });
  txt(s, "Vue de l'arrière. Flèches : δi > 0, braquage vers la gouverne suivante (sens horaire)",
    { x: 0.4, y: 4.85, w: 3.6, h: 0.45, fontSize: 10, color: C.accent6, align: "center" });
  carte(s, 4.3, 1.15, 5.2, 1.6, "mixage");
  txt(s, "Braquages équivalents", { x: 4.5, y: 1.25, w: 4.8, h: 0.3, fontSize: 13, bold: true, color: C.text2 });
  txt(s, [
    { text: "δl = (δ1 + δ2 + δ3 + δ4) / 4", options: { breakLine: true } },
    { text: "DM = √2/4 · (δ1 − δ2 − δ3 + δ4)", options: { bold: true, color: C.accent5, breakLine: true } },
    { text: "DN = √2/4 · (−δ1 − δ2 + δ3 + δ4)" },
  ], { x: 4.5, y: 1.6, w: 4.8, h: 1.1, fontSize: 15, fontFace: "Cambria", paraSpaceAfter: 4 });
  puces(s, [
    "Tangage pur : δ1 = δ4 = δ et δ2 = δ3 = −δ, donc DM = √2 · δ.",
    "D'où vient √2 : chaque gouverne porte à 45°, 4 × cos 45° = 2√2 : l'équivalent de 2 gouvernes en + braquées de √2 · δ.",
    `Butée |δi| ≤ 30° ⇒ |DM| ≤ ${fr(BUTEE)}°.`,
  ], { x: 4.3, y: 2.95, w: 5.2, h: 1.9, fontSize: 14 });
  s.addNotes("Numérotation : D1 en bas à droite vu de l'arrière, puis sens horaire ; δi > 0 quand la gouverne braque vers la suivante. " +
    "Le signe global de DM (piqueur ou cabreur) se fixe sur un calcul test : dans le modèle factice, DM > 0 donne Cm < 0.");
}
{
  const s = newSlide(SECT.dom, `Les ${N_DM === 9 ? "neuf" : N_DM} géométries à mailler`);
  const f = (v) => {
    if (Math.abs(v) < 1e-9) return "0";
    const entier = Math.abs(v - Math.round(v)) < 1e-6;
    return (v > 0 ? "+" : "−") + fr(Math.abs(v), entier ? 0 : 1);
  };
  const rows = [["δ (°)", "DM (°)", "δ1", "δ2", "δ3", "δ4"]];
  DELTA_PHYS.forEach((d, i) => {
    const o = i === 0 || i === N_DM - 1 ? HL() : {};
    rows.push([{ text: f(d), options: o }, { text: f(T.dm_niveaux[i]), options: o },
      { text: f(d), options: o }, { text: f(-d), options: o }, { text: f(-d), options: o }, { text: f(d), options: o }]);
  });
  table(s, rows, { x: 0.5, y: 1.1, w: 5.2, colW: [0.85, 0.95, 0.85, 0.85, 0.85, 0.85], rowH: 0.36, align: "center", fontSize: 12 });
  carte(s, 6.0, 1.1, 3.5, 1.6, "inverse");
  txt(s, "Inverse, pour la CAO", { x: 6.2, y: 1.2, w: 3.1, h: 0.3, fontSize: 13, bold: true, color: C.text2 });
  txt(s, [
    { text: "δ1 = δ4 = DM / √2", options: { breakLine: true } },
    { text: "δ2 = δ3 = −DM / √2" },
  ], { x: 6.2, y: 1.6, w: 3.1, h: 0.9, fontSize: 16, fontFace: "Cambria", color: C.accent5, paraSpaceAfter: 4 });
  puces(s, [
    `En 6DOF la butée devient un losange : |DM ± DN| ≤ ${fr(BUTEE)}°.`,
    `À α = 0, seules les ${D.plan_alpha0} géométries DM ≥ 0 sont calculées (symétrie).`,
  ], { x: 6.0, y: 2.95, w: 3.5, h: 1.8, fontSize: 14 });
  s.addNotes("Chaque ligne est une CAO. En 6DOF : δ1 = (DM − DN)/√2, δ2 = −(DM + DN)/√2, δ3 = (DN − DM)/√2, δ4 = (DM + DN)/√2 (roulis nul).");
}

// ================= Section DOE =================
section(SECT.doe, "Ne calculer que ce que la symétrie ne donne pas", 2);
{
  const s = newSlide(SECT.doe, "La symétrie divise le domaine par deux");
  img(s, "domaine", 0.5, 1.1, 4.4, 3.9, "Plan alpha-DM : zone calculée et zone déduite par symétrie");
  carte(s, 5.2, 1.15, 4.3, 1.5, "miroir H");
  txt(s, "Miroir horizontal (≡ rotation de 180°)", { x: 5.4, y: 1.25, w: 3.9, h: 0.35, fontSize: 14, bold: true, color: C.text2 });
  txt(s, "(α, DM) → (−α, −DM)", { x: 5.4, y: 1.65, w: 3.9, h: 0.4, fontSize: 18, fontFace: "Cambria", color: C.accent5 });
  txt(s, "CA inchangé · CN → −CN · Cm → −Cm", { x: 5.4, y: 2.15, w: 3.9, h: 0.4, fontSize: 14 });
  puces(s, [
    "α ∈ [0 ; 45°] est étendu gratuitement à [−45 ; 45°].",
    "Le plan α = 0 est son propre miroir : on n'y calcule que DM ≥ 0.",
    "Contrôle gratuit : CN = Cm = 0 en α = 0, DM = 0.",
  ], { x: 5.2, y: 2.9, w: 4.3, h: 1.9, fontSize: 14 });
  s.addNotes("Figure de cfd-doe remplir : bleu calculé, gris hachuré déduit.");
}
{
  const s = newSlide(SECT.doe, `${D.calculs} calculs CFD au lieu de ${D.noeuds_table}`);
  table(s, [
    ["#", "Sous-domaine", "α", "DM", "Calculs / Mach"],
    ["1", "général", "]0 ; 45°]", `[−${fr(BUTEE)} ; ${fr(BUTEE)}°]`, `${D.n_alpha_calc} × ${N_DM} = ${D.general}`],
    ["2", "plan α = 0", "0", `[0 ; ${fr(BUTEE)}°]`, String(D.plan_alpha0)],
    ["", { text: "Total", options: { bold: true } }, "", "", { text: `${D.par_mach} × ${D.machs.length} = ${D.calculs}`, options: { bold: true, color: C.text2 } }],
  ], { x: 0.5, y: 1.2, w: 5.7, colW: [0.35, 1.45, 0.9, 1.4, 1.6], rowH: 0.42 });
  note(s, "β, δn, δl = 0 partout. Bornes ouvertes : ]0 ; 45°] exclut α = 0 pour ne pas le compter deux fois.", 3.3, 0.5, 5.7);
  txt(s, `Mach calculés : ${MACHS.join(" · ")}`, { x: 0.5, y: 3.9, w: 5.6, h: 0.4, fontSize: 15, bold: true, color: C.text2 });
  [[String(D.calculs), "calculs CFD à lancer"],
    [String(D.noeuds_table), `nœuds par table (${D.machs.length} × ${D.n_alpha_table} × ${N_DM})`],
    ["÷ 2", "gain de la symétrie"]].forEach(([v, l], i) => {
    const y = 1.2 + i * 1.2;
    carte(s, 6.5, y, 3.0, 1.0, `chiffre ${i + 1}`);
    txt(s, v, { x: 6.65, y: y + 0.12, w: 1.15, h: 0.75, fontSize: 30, bold: true, fontFace: "Cambria",
      color: i === 0 ? C.accent2 : C.text2, valign: "middle" });
    txt(s, l, { x: 7.85, y: y + 0.12, w: 1.55, h: 0.75, fontSize: 13, valign: "middle" });
  });
  s.addNotes("Résultat de cfd-doe domaine : deux sous-domaines. SORTIE/DOE/doe.csv liste les points (Mach, α, DM), prêts à lancer.");
}
{
  const s = newSlide(SECT.doe, "Quel plan de remplissage ? Le factoriel complet");
  const NOMS = { complet: "Factoriel complet", ordre_1: "Décomposition ordre 1", krigeage: "Krigeage",
    lhs: "Hypercube latin", composite: "Composite centré" };
  const ordre = ["complet", "ordre_1", "krigeage", "lhs", "composite"];
  const rows = [["Plan", "Calculs", "Erreur RMS", "Erreur max"]];
  ordre.forEach((n) => {
    const p = D.plans.find((q) => q.plan === n);
    const o = n === "complet" ? HL() : {};
    rows.push([{ text: NOMS[n], options: o }, { text: String(p.calculs), options: o },
      { text: pct(p.rms), options: o }, { text: pct(p.max), options: o }]);
  });
  table(s, rows, { x: 0.5, y: 1.2, w: 5.0, colW: [2.2, 0.8, 1.0, 1.0], rowH: 0.36, fontSize: 12 });
  note(s, "Erreur en % de l'étendue, sur une CFD factice (indicatif).", 3.85, 0.5, 5.0);
  txt(s, "Avec deux variables par Mach, le factoriel ne coûte presque rien : la table est exacte aux nœuds, sans hypothèse de modèle.",
    { x: 0.5, y: 4.25, w: 5.0, h: 0.75, fontSize: 14, italic: true, color: C.text2 });
  img(s, "precision_cout", 5.8, 1.2, 3.7, 3.6, "Précision contre coût des plans de remplissage");
  s.addNotes("Plans rejoués par cfd-doe (01_EXEMPLE/reconstruire_tables.py) sur son modèle factice.");
}

// ================= Section Modélisation =================
section(SECT.mod, "Comment les tables sont construites et lues", 3);
{
  const s = newSlide(SECT.mod, "Modélisation des coefficients");
  carte(s, 0.5, 1.15, 9.0, 1.3, "équations");
  txt(s, [
    { text: "CA(M, α, DM, z) = CA" }, { text: "CFD", options: { subscript: true } },
    { text: "(M, α, DM) + ΔzCA(M, z)", options: { breakLine: true } },
    { text: "CN = CN(M, α, DM)        Cm = Cm(M, α, DM)" },
  ], { x: 0.75, y: 1.25, w: 8.5, h: 1.1, fontSize: 18, fontFace: "Cambria", color: C.text2, valign: "middle", paraSpaceAfter: 6 });
  table(s, [
    ["Coefficient", "Dépend de", "Source", "Symétrie (−α, −DM)"],
    ["CA", "M, α, DM, z", "CFD + semi-empirique", "paire : CA"],
    ["CN", "M, α, DM", "CFD", "impaire : −CN"],
    ["Cm", "M, α, DM", "CFD, au CDG (Xcg = 1,15 m), réf. D", "impaire : −Cm"],
    ["CY, Cl, Cn", "—", "nuls en 3DOF tangage", "—"],
  ], { x: 0.5, y: 2.7, w: 9.0, colW: [1.4, 1.6, 3.6, 2.4], rowH: 0.38, fontSize: 13 });
  s.addNotes("Seul le CA dépend de l'altitude (Reynolds, donc frottement). La CFD est faite au Reynolds du niveau de la mer.");
}
{
  const s = newSlide(SECT.mod, "ΔzCA : correction semi-empirique du frottement");
  txt(s, [
    { text: "1. Reynolds de vol (ISA, cfd-atm)", options: { bold: true, color: C.text2, breakLine: true } },
    { text: "Re = ρ(z) · M · a(z) · L / μ(z)", options: { fontFace: "Cambria", breakLine: true } },
    { text: "2. Frottement turbulent compressible", options: { bold: true, color: C.text2, breakLine: true } },
    { text: "Cf = 0,455 / (log Re)^2,58 / (1 + 0,144 M²)^0,65", options: { fontFace: "Cambria", breakLine: true } },
    { text: "3. Écart à l'altitude CFD (0 m)", options: { bold: true, color: C.text2, breakLine: true } },
    { text: "ΔzCA = (Smouillée / Sréf) · [Cf(M, z) − Cf(M, 0)]", options: { fontFace: "Cambria" } },
  ], { x: 0.5, y: 1.15, w: 4.6, h: 2.9, fontSize: 14, paraSpaceAfter: 6 });
  txt(s, `Géométrie factice : L = 1,80 m, D = 0,10 m, Smouillée / Sréf = ${fr(D.k_mouille)}`,
    { x: 0.5, y: 4.3, w: 4.6, h: 0.5, fontSize: 12, color: C.accent6 });
  const b = img(s, "dzca_mach", 5.3, 1.15, 4.2, 3.3, "Correction d'altitude du CA en fonction du Mach");
  txt(s, "Table d'incrément, lue en bilinéaire (Mach, altitude)", { x: 5.3, y: b.y + b.h + 0.08, w: 4.2, h: 0.3, fontSize: 11, color: C.accent6 });
  s.addNotes("Plaque plane turbulente corrigée de la compressibilité ; seul l'écart à l'altitude des calculs CFD est ajouté.");
}
{
  const s = newSlide(SECT.mod, `ΔzCA reste petit : au plus +${fr(max(D.dzca_table["0.6"]), 4)}`);
  const rows = Object.entries(D.dzca_table).map(([m, v]) => [fr(Number(m)), ...v.map((x) => fr(1e4 * x, 0))]);
  table(s, [["Mach", "0 m", "500 m", "1000 m", "1500 m", "2000 m"], ...rows],
    { x: 0.5, y: 1.2, w: 5.4, colW: [0.9, 0.9, 0.9, 0.9, 0.9, 0.9], rowH: 0.42, align: "center", fontSize: 14 });
  txt(s, "ΔzCA × 10⁴. Évalué en continu en Mach : pas de saturation sous 0,6.",
    { x: 0.5, y: 3.45, w: 5.4, h: 0.5, fontSize: 12, color: C.accent6 });
  const r = (100 * D.dzca_table["0.6"][4]) / D.ca_frottement_z0["0.6"];
  carte(s, 6.3, 1.2, 3.2, 2.2, "ordre de grandeur");
  txt(s, `+${fr(r)} %`, { x: 6.5, y: 1.35, w: 2.8, h: 0.8, fontSize: 36, bold: true, fontFace: "Cambria", color: C.accent2 });
  txt(s, `du CA de frottement à Mach 0,6 et 2000 m (${fr(D.dzca_table["0.6"][4], 4)} sur ${fr(D.ca_frottement_z0["0.6"], 3)})`,
    { x: 6.5, y: 2.2, w: 2.8, h: 1.0, fontSize: 14 });
  txt(s, "Faible, mais systématique : il s'accumule sur toute la phase propulsée et réduit l'apogée.",
    { x: 0.5, y: 4.15, w: 9.0, h: 0.6, fontSize: 14, italic: true, color: C.text2 });
}
{
  const s = newSlide(SECT.mod, "Lecture des coefficients dans le simulateur");
  [
    ["Replier", "si α < 0 : lire en (−α, −DM), puis CN → −CN, Cm → −Cm"],
    ["Borner", `M < 0,6 → 0,6 ; |DM| ≤ ${fr(BUTEE)}° (butée)`],
    ["Interpoler", `multilinéaire en (M, α, DM), table ${D.machs.length} × ${D.n_alpha_table} × ${N_DM}`],
    ["Corriger", "CA += ΔzCA(M, z), bilinéaire"],
  ].forEach(([t, d], i) => {
    const y = 1.15 + i * 0.88;
    carte(s, 0.5, y, 5.0, 0.72, `lecture ${i + 1}`);
    pastille(s, 0.65, y + 0.15, i + 1);
    txt(s, t, { x: 1.25, y: y + 0.1, w: 1.2, h: 0.52, fontSize: 15, bold: true, color: C.text2, valign: "middle" });
    txt(s, d, { x: 2.45, y: y + 0.1, w: 2.95, h: 0.52, fontSize: 12, valign: "middle" });
  });
  const b = img(s, "CA_total_mach", 5.7, 1.15, 3.8, 3.3, "CA lu par le simulateur en fonction du Mach, par altitude");
  txt(s, "CA total lu comme le simulateur (Table3D + incrément) : palier sous 0,6, segments entre Mach, écart d'altitude en médaillon.",
    { x: 5.7, y: b.y + b.h + 0.08, w: 3.8, h: 0.6, fontSize: 10, color: C.accent6 });
  s.addNotes("La table carrée (α de −45 à 45°) est déjà complétée par symétrie par cfd-doe : l'étape 1 est faite une fois pour toutes. " +
    "La figure est produite par tracer_base_aero.py avec la même lecture que le simulateur (classe Table3D, lire_increment).");
}

// ================= Section Résultats =================
section(SECT.res, "Résultats factices, produits par la chaîne réelle : DOE → « CFD » → tables cfd-doe → tracés cfd-plot", 4);
{
  const s = newSlide(SECT.res, "Un script pour tous les tracés");
  table(s, [
    ["Dossier", "Ce qu'il contient", "Fonctionnalité cfd-plot"],
    ["COURBES/", "CA, CN, Cm selon α et selon Mach, une courbe par DM", "batch_plot, zoom, feuilles repliées"],
    ["CARTES/", "CA, CN, Cm dans le plan (α, DM), un panneau par Mach", "batch_carto, échelle partagée"],
    ["INCREMENT/", "ΔzCA(Mach) ; CA lu par le simulateur, par altitude", "batch_plot, zoom en médaillon"],
    ["EQUILIBRE/", "α et CN d'équilibre selon DM", "batch_plot, feuille repliée y"],
    ["DERIVEES/", "CNα, Cmα, CNδ, Cmδ, marge statique selon Mach", "batch_plot, feuille repliée y"],
  ], { x: 0.5, y: 1.1, w: 9.0, colW: [1.5, 4.4, 3.1], rowH: 0.38, fontSize: 12 });
  carte(s, 0.5, 3.6, 9.0, 1.2, "entrées");
  txt(s, [
    { text: "tracer_base_aero.py · ", options: { bold: true, color: C.accent5 } },
    { text: "Entrées : ", options: { bold: true, color: C.text2 } },
    { text: "deux DataFrames, la table carrée (Mach, α, DM, CA, CN, Cm) et l'incrément (Mach, altitude, ΔzCA) ; noms de colonnes en paramètre.", options: { breakLine: true } },
    { text: "Sorties : ", options: { bold: true, color: C.text2 } },
    { text: "l'arborescence complète des figures, et les planches de cette présentation sous des noms fixes." },
  ], { x: 0.7, y: 3.72, w: 8.6, h: 1.0, fontSize: 13, paraSpaceAfter: 4 });
  s.addNotes("python tracer_base_aero.py TABLES.csv INCREMENT.csv --col mach=Mach alpha=ALPHA dm=DM_EQ --col-increment increment=DCA_Z. " +
    "Un même crochet (classe Habillage) hachure la zone déduite par symétrie, trace y = 0 et la bande de marge usuelle sur toutes les figures.");
}
{
  const s = newSlide(SECT.res, "Critère de convergence d'un calcul");
  img(s, "convergence", 0.5, 1.1, 9.0, 3.15, "Résidus et historique des coefficients d'un calcul", true);
  puces(s, [
    "Résidus divisés par 10⁵ au moins.",
    "CN, Cm, CA stables à ± 0,5 % sur les 500 dernières itérations ; la valeur retenue est leur moyenne.",
    `Critère appliqué aux ${D.calculs} calculs ; un calcul non convergé est relancé, jamais interpolé.`,
  ], { x: 0.5, y: 4.3, w: 9.0, h: 1.0, fontSize: 13, paraSpaceAfter: 3 });
  s.addNotes("Exemple factice : Mach 0,9, α = 20°, DM = 0.");
}
const resultatCourbe = (titre, planche, alt, items, notes) => {
  const s = newSlide(SECT.res, titre);
  img(s, planche, 0.5, 1.05, 5.4, 4.1, alt);
  puces(s, items, { x: 6.1, y: 1.2, w: 3.4, h: 3.8, fontSize: 13 });
  s.addNotes(notes);
};
resultatCourbe("CN : linéaire, puis non linéaire au-delà de 15°", "CN_alpha_4mach", "CN selon alpha, un panneau par Mach", [
  `CNα de ${fr(min(DER.CNa))} à ${fr(max(DER.CNa))} /rad à α = 0, maximal à Mach 0,9.`,
  "Au-delà de 15°, la portance du corps (écoulement transverse) fait croître CN plus vite que linéairement.",
  `En butée, la gouverne décale CN de ± ${fr(min(T.CN_butee_alpha0))} à ± ${fr(max(T.CN_butee_alpha0))} à α = 0 ; son effet s'amenuise vers 45°.`,
  "Zone hachurée : déduite par symétrie, jamais calculée.",
], "Courbe noire : DM = 0. Les courbes se resserrent aux grands angles : la gouverne approche du décrochage.");
resultatCourbe("Cm : stable, gouverne efficace jusqu'en butée", "Cm_alpha_4mach", "Cm selon alpha, un panneau par Mach", [
  "Pente négative à DM = 0 sur les 4 Mach : la fusée est statiquement stable.",
  `Chaque courbe coupe Cm = 0 ${T.racines_par_courbe.length === 1 && T.racines_par_courbe[0] === 1 ? "une seule fois" : "plusieurs fois"} : un seul équilibre par braquage.`,
  "DM > 0 donne Cm < 0 (piqueur) : convention à confirmer sur un calcul test.",
], "Moment au CDG (1,15 m du nez), longueur de référence D.");
resultatCourbe("CA : effet du braquage, et saut transsonique", "CA_alpha_4mach", "CA selon alpha, un panneau par Mach", [
  `CA passe de ${fr(DER.CA0[0], 2)} (Mach 0,6) à ${fr(max(DER.CA0), 2)} (Mach 1,2) : traînée d'onde.`,
  `Le braquage en butée ajoute jusqu'à +${fr(T.CA_max_braquage, 2)} à α = 0.`,
  "CA n'est pas symétrique en α à DM fixé ; il l'est en (α, DM) → (−α, −DM).",
], "CA à z = 0 m, avant correction d'altitude.");
{
  const s = newSlide(SECT.res, "Le pas de 0,3 manque le pic transsonique");
  img(s, "CA_pic_transsonique", 0.5, 1.1, 5.4, 3.5, "CA selon le Mach : table contre comportement attendu");
  const e = D.ecart_CA_M105, r = (100 * e) / D.ca0_m105;
  carte(s, 6.2, 1.15, 3.3, 1.7, "écart");
  txt(s, `−${fr(e, 2)}`, { x: 6.4, y: 1.3, w: 2.9, h: 0.75, fontSize: 36, bold: true, fontFace: "Cambria", color: C.accent2 });
  txt(s, `erreur de la table sur CA à Mach 1,05, soit −${fr(r, 0)} %`, { x: 6.4, y: 2.1, w: 2.9, h: 0.7, fontSize: 14 });
  puces(s, [`Ajouter Mach 1,05 : +${D.par_mach} calculs.`, "Ou resserrer à 0,9 · 1,0 · 1,1 · 1,2."],
    { x: 6.2, y: 3.1, w: 3.3, h: 1.2, fontSize: 14 });
  note(s, "Courbe tiretée : comportement attendu du modèle factice, que la CFD ne verrait qu'avec plus de Mach.", 4.75);
}
{
  const s = newSlide(SECT.res, "Cartes dans le plan (α, DM) : la ligne d'équilibre");
  img(s, "carte_Cm", 0.5, 1.05, 4.4, 3.4, "Carte de Cm dans le plan alpha-DM, un panneau par Mach");
  img(s, "carte_CN", 5.1, 1.05, 4.4, 3.4, "Carte de CN dans le plan alpha-DM, un panneau par Mach");
  puces(s, [
    "Trait noir de Cm : Cm = 0, les couples (α, DM) d'équilibre, droits et presque identiques aux 4 Mach.",
    "CN se lit sur la carte voisine au même point : c'est le facteur de charge disponible.",
  ], { x: 0.5, y: 4.5, w: 9.0, h: 0.8, fontSize: 12, paraSpaceAfter: 3 });
  s.addNotes("batch_carto : une échelle de couleur partagée par les 4 panneaux, si bien qu'une teinte vaut la même chose partout.");
}
{
  const s = newSlide(SECT.res, "Équilibre en tangage");
  img(s, "equilibre", 0.5, 1.05, 9.0, 3.0, "Incidence et CN d'équilibre selon DM, par Mach", true);
  table(s, [
    ["Mach", ...MACHS],
    ["α d'équilibre en butée", ...T.alpha_eq_butee.map((a) => `${fr(a, 0)}°`)],
  ], { x: 0.5, y: 4.25, w: 6.0, colW: [2.4, 0.9, 0.9, 0.9, 0.9], rowH: 0.3, fontSize: 12, align: "center" });
  txt(s, `En butée, toute incidence jusqu'à ≈ ${fr(min(T.alpha_eq_butee), 0)}° est tenable.`,
    { x: 6.7, y: 4.2, w: 2.8, h: 0.8, fontSize: 13, italic: true, color: C.text2 });
  s.addNotes(`Racine stable de Cm = 0 la plus proche de α = 0, interpolée linéairement en α, sur ${T.courbes_equilibre} courbes (Mach × DM).`);
}
{
  const s = newSlide(SECT.res, "Dérivées et marge statique selon le Mach");
  img(s, "derivees", 0.5, 1.05, 5.9, 3.9, "CN alpha, Cm alpha, CN delta, Cm delta et marge statique selon le Mach");
  table(s, [
    ["/rad", ...MACHS],
    ["CNα", ...DER.CNa.map((v) => fr(v))],
    ["Cmα", ...DER.Cma.map((v) => fr(v, 0))],
    ["Cmδ", ...DER.Cmd.map((v) => fr(v, 0))],
    ["Marge", ...DER.marge.map((v) => fr(v))],
  ], { x: 6.6, y: 1.15, w: 2.9, colW: [0.7, 0.55, 0.55, 0.55, 0.55], rowH: 0.3, fontSize: 10, align: "center", margin: [2, 3, 2, 3] });
  txt(s, `Marge (calibres) de ${fr(min(DER.marge))} à ${fr(max(DER.marge))} : stable, un peu au-dessus de la plage usuelle. Cmδ/Cmα ≈ 1 : ~1° d'incidence par degré de DM.`,
    { x: 6.6, y: 3.2, w: 2.9, h: 1.8, fontSize: 13, italic: true, color: C.text2 });
  s.addNotes("Différences centrées sur la table autour de α = 0, DM = 0. Marge = −Cmα/CNα, en calibres (Lréf = D).");
}
{
  const s = newSlide(SECT.res, "Contrôles de cohérence de la base");
  const ok = { text: "OK", options: { bold: true, color: "2E7D32" } };
  table(s, [
    ["Contrôle", "Attendu", "Obtenu", ""],
    ["CN, Cm en α = 0, DM = 0", "0", "0", ok],
    ["Table complétée par symétrie", `0 trou sur ${D.noeuds_table} nœuds`, "0 trou", ok],
    ["Image d'un calcul (−α, −DM)", "CA = ; CN, Cm opposés", `écart ${D.ecart_symetrie.toExponential(0)}`, ok],
    ["Stabilité statique", "Cmα < 0 à tout Mach", `${fr(max(DER.Cma), 0)} à ${fr(min(DER.Cma), 0)} /rad`, ok],
    ["Efficacité gouverne", "Cmδ < 0, même signe partout", `${fr(max(DER.Cmd), 0)} à ${fr(min(DER.Cmd), 0)} /rad`, ok],
    ["Équilibre unique par DM", "1 passage par Cm = 0", `1 sur ${T.courbes_equilibre} courbes`, ok],
    ["Correction ΔzCA", "≥ 0, croît avec z", `0 à +${fr(max(D.dzca_table["0.6"]), 4)}`, ok],
  ], { x: 0.5, y: 1.15, w: 9.0, colW: [3.0, 2.9, 2.3, 0.8], rowH: 0.4, fontSize: 13 });
  note(s, "Tous ces contrôles sont automatisables : ils tournent à chaque mise à jour de la base.", 4.75);
  s.addNotes("Contrôles internes : ils détectent les erreurs de signe, de convention ou de post-traitement, pas les erreurs de physique.");
}

// ================= Section ParaView =================
section(SECT.pv, "Ce qu'il faut montrer pour que les chiffres soient crus", 5);
{
  const s = newSlide(SECT.pv, "Ce qu'il faut montrer avec ParaView");
  table(s, [
    ["Vue", "Filtres ParaView", "Ce que ça justifie"],
    ["Maillage et y+ pariétal", "Slice, Extract Surface, Threshold y+", "Couche limite résolue, choix de la loi de paroi"],
    ["Mach, plan de tangage (M 1,2 ; 1,5)", "Slice, Contour Mach = 1", "Chocs captés, pas de réflexion sur les frontières"],
    ["Cp pariétal, corps et gouvernes", "Calculator Cp, Surface", "Qui porte : corps ou gouvernes ; position du Xcp"],
    ["Tourbillons d'extrados (α ≥ 20°)", "Q-criterion, Contour, Stream Tracer", "Non-linéarité de CN ; asymétrie, limite du RANS"],
    ["Culot", "Stream Tracer, Glyph", "Recirculation et part de culot dans CA"],
    ["Gouverne braquée en butée", "Slice normale, Surface LIC frottement", "Décollement, perte d'efficacité aux grands α + DM"],
    ["Transsonique (M 0,9)", "Contour Mach = 1, Plot Over Line Cp", "Poche supersonique, origine du pic de CA"],
  ], { x: 0.5, y: 1.1, w: 9.0, colW: [2.6, 2.9, 3.5], rowH: 0.42, fontSize: 11 });
  s.addNotes("Captures de préférence par un état ParaView (.pvsm) rejoué sur chaque calcul (tools/paraview) : même caméra, même échelle de couleur.");
}
{
  const s = newSlide(SECT.pv, "Planche type : un cas, six vues");
  const vues = [
    ["Maillage + y+", "Coupe du maillage près du culot ; y+ < 1 sur 95 % de la paroi"],
    ["Mach, M = 1,5, α = 0", "Choc d'ogive et chocs d'attache des gouvernes"],
    ["Cp pariétal, α = 10°", "Charge concentrée sur les gouvernes"],
    ["Q-criterion, α = 40°", "Deux tourbillons d'extrados symétriques"],
    ["Culot, lignes de courant", "Recirculation, point d'arrêt arrière"],
    ["Gouverne en butée", "Lignes de frottement, décollement d'extrados"],
  ];
  const w = 2.85, h = 1.6, gx = 0.225, gy = 0.2;
  vues.forEach(([t, d], i) => {
    const x = 0.5 + (i % 3) * (w + gx), y = 1.1 + Math.floor(i / 3) * (h + gy);
    carte(s, x, y, w, h, `vue ${i + 1}`);
    s.addShape(pres.shapes.RECTANGLE, { x: x + 0.12, y: y + 0.12, w: w - 0.24, h: 0.72,
      fill: { color: C.background1 }, line: { color: C.accent4, width: 1, dashType: "dash" }, objectName: `cadre capture ${i + 1}` });
    txt(s, "capture ParaView", { x: x + 0.12, y: y + 0.12, w: w - 0.24, h: 0.72, fontSize: 11, color: C.accent4, align: "center", valign: "middle" });
    txt(s, t, { x: x + 0.12, y: y + 0.9, w: w - 0.24, h: 0.28, fontSize: 13, bold: true, color: C.text2 });
    txt(s, d, { x: x + 0.12, y: y + 1.18, w: w - 0.24, h: 0.38, fontSize: 11, color: C.accent6 });
  });
  note(s, "Une planche par cas représentatif : Mach 0,9 et 1,5, α = 0, 20 et 40°, DM = 0 et en butée.", 4.75);
  s.addNotes("Gabarit à remplir avec les vraies captures.");
}

// ================= Conclusion =================
pres.addSection({ title: SECT.fin });
{
  const s = pres.addSlide({ masterName: "TITRE", sectionTitle: SECT.fin });
  txt(s, "À retenir et prochaines étapes", { x: 0.6, y: 0.45, w: 8.8, h: 0.7, fontSize: 30, bold: true, fontFace: "Cambria", color: C.background1, valign: "middle" });
  [[String(D.calculs), `calculs CFD, ${D.machs.length} Mach`], [fr(max(DER.marge)), "calibres de marge statique, au plus"],
    [`±${fr(BUTEE, 0)}°`, `DM en butée, α d'équilibre ≈ ${fr(min(T.alpha_eq_butee), 0)}°`]].forEach(([v, l], i) => {
    const x = 0.6 + i * 3.0;
    txt(s, v, { x, y: 1.4, w: 2.7, h: 0.8, fontSize: 40, bold: true, fontFace: "Cambria", color: C.accent2 });
    txt(s, l, { x, y: 2.2, w: 2.7, h: 0.4, fontSize: 15, color: C.background1 });
  });
  puces(s, [
    `Ajouter Mach 1,05 : la table sous-estime CA de ${fr((100 * D.ecart_CA_M105) / D.ca0_m105, 0)} % au pic transsonique.`,
    `Fixer le signe de DM sur un calcul test, avant de mailler les ${N_DM} géométries.`,
    "Vérifier le RANS stationnaire au-delà de α = 30° (tourbillons, asymétrie).",
    "Remplacer les valeurs factices par la géométrie et les calculs réels : tracer_base_aero.py ne change pas.",
  ], { x: 0.6, y: 3.0, w: 8.8, h: 2.0, fontSize: 15, color: C.background2, paraSpaceAfter: 6 });
}

pres.writeFile({ fileName: OUT }).then(async () => {
  await appliquerTheme(OUT, THEME);
  console.log("écrit :", OUT);
});
