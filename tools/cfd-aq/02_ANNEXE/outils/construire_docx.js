/*
 * Construit ANNEXE_TRAINEE_MARCHES.docx.
 *
 *   npm install docx            (une fois, où vous voulez)
 *   NODE_PATH=<chemin>/node_modules node outils/construire_docx.js
 *
 * Les images viennent de 02_ANNEXE/FIGURES/, produites par
 * outils/extraire_figures.py. Le texte est ici.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, WidthType, BorderStyle, ShadingType,
  PageBreak, LevelFormat, convertMillimetersToTwip, TableOfContents, Footer,
  PageNumber, VerticalAlign,
} = require("docx");

const RACINE = path.resolve(__dirname, "..");
const FIGURES = path.join(RACINE, "FIGURES");
const SORTIE = path.join(RACINE, "ANNEXE_TRAINEE_MARCHES.docx");

/* --- mise en page ------------------------------------------------------ */
const MARGE = convertMillimetersToTwip(22);          // A4, marges 22 mm
const LARGEUR_TEXTE_DXA = 11906 - 2 * MARGE;         // A4 = 11906 dxa
const LARGEUR_IMAGE_PX = 600;                        // ~15,9 cm à 96 dpi

const POLICE = "Calibri";
const POLICE_FORMULE = "Cambria";
const GRIS = "595959";
const ACCENT = "1F4E79";

/* --- utilitaires ------------------------------------------------------- */

/** Dimensions d'un PNG, lues dans le chunk IHDR. */
function dimensionsPng(fichier) {
  const tampon = fs.readFileSync(fichier);
  return { largeur: tampon.readUInt32BE(16), hauteur: tampon.readUInt32BE(20) };
}

let compteurFigure = 0;

/** Une figure centrée, mise à l'échelle de la largeur du texte. */
function figure(nom, legende, largeurMax = LARGEUR_IMAGE_PX, hauteurMax = 760) {
  const fichier = path.join(FIGURES, nom);
  const { largeur, hauteur } = dimensionsPng(fichier);
  let l = Math.min(largeurMax, largeur);
  let h = Math.round((hauteur * l) / largeur);
  if (h > hauteurMax) { h = hauteurMax; l = Math.round((largeur * h) / hauteur); }
  compteurFigure += 1;
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 220, after: 60 },
      keepNext: true,
      children: [new ImageRun({
        type: "png",
        data: fs.readFileSync(fichier),
        transformation: { width: l, height: h },
      })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 240 },
      children: [new TextRun({
        text: `Figure A.${compteurFigure} — ${legende}`,
        font: POLICE, size: 17, italics: true, color: GRIS,
      })],
    }),
  ];
}

/** Paragraphe de corps de texte. */
function p(...morceaux) {
  const enfants = morceaux.map((m) =>
    typeof m === "string"
      ? new TextRun({ text: m, font: POLICE, size: 21 })
      : new TextRun({ font: POLICE, size: 21, ...m }));
  return new Paragraph({
    children: enfants,
    spacing: { after: 140, line: 276 },
    alignment: AlignmentType.JUSTIFIED,
  });
}

/** Formule centrée. */
function formule(texte, reference) {
  const enfants = [new TextRun({ text: texte, font: POLICE_FORMULE, size: 22 })];
  if (reference) {
    enfants.push(new TextRun({
      text: `          ${reference}`, font: POLICE, size: 18, color: GRIS,
    }));
  }
  return new Paragraph({
    children: enfants,
    alignment: AlignmentType.CENTER,
    spacing: { before: 160, after: 160 },
  });
}

function titre(texte, niveau) {
  return new Paragraph({
    text: texte,
    heading: niveau,
    spacing: { before: niveau === HeadingLevel.HEADING_1 ? 360 : 280, after: 140 },
  });
}

function puce(...morceaux) {
  const enfants = morceaux.map((m) =>
    typeof m === "string"
      ? new TextRun({ text: m, font: POLICE, size: 21 })
      : new TextRun({ font: POLICE, size: 21, ...m }));
  return new Paragraph({
    children: enfants,
    numbering: { reference: "puces", level: 0 },
    spacing: { after: 90, line: 276 },
    alignment: AlignmentType.JUSTIFIED,
  });
}

/** Tableau simple : en-tête + lignes, largeurs en fractions. */
function tableau(entetes, lignes, fractions, alignements) {
  if (fractions.length !== entetes.length) {
    throw new Error(
      `tableau « ${entetes[0]} » : ${entetes.length} colonnes mais `
      + `${fractions.length} largeurs.`);
  }
  for (const ligne of lignes) {
    if (ligne.length !== entetes.length) {
      throw new Error(
        `tableau « ${entetes[0]} » : ligne « ${ligne[0]} » a ${ligne.length} `
        + `cellules pour ${entetes.length} colonnes.`);
    }
  }
  const largeurs = fractions.map((f) => Math.round(f * LARGEUR_TEXTE_DXA));
  largeurs[largeurs.length - 1] =
    LARGEUR_TEXTE_DXA - largeurs.slice(0, -1).reduce((a, b) => a + b, 0);
  const align = alignements
    || entetes.map((_, i) => (i === 0 ? AlignmentType.LEFT : AlignmentType.CENTER));

  const cellule = (texte, i, enTete) => new TableCell({
    width: { size: largeurs[i], type: WidthType.DXA },
    margins: { top: 60, bottom: 60, left: 90, right: 90 },
    verticalAlign: VerticalAlign.CENTER,
    shading: enTete
      ? { type: ShadingType.CLEAR, fill: "DEEAF6", color: "auto" }
      : undefined,
    children: [new Paragraph({
      alignment: align[i],
      spacing: { after: 0 },
      children: [new TextRun({
        text: String(texte), font: POLICE, size: 19, color: enTete ? ACCENT : "000000",
      })],
    })],
  });

  return new Table({
    columnWidths: largeurs,
    width: { size: LARGEUR_TEXTE_DXA, type: WidthType.DXA },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 4, color: "8EAADB" },
      bottom: { style: BorderStyle.SINGLE, size: 4, color: "8EAADB" },
      left: { style: BorderStyle.SINGLE, size: 4, color: "8EAADB" },
      right: { style: BorderStyle.SINGLE, size: 4, color: "8EAADB" },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: "BDD6EE" },
      insideVertical: { style: BorderStyle.SINGLE, size: 2, color: "BDD6EE" },
    },
    rows: [
      new TableRow({
        tableHeader: true,
        cantSplit: true,
        children: entetes.map((t, i) => cellule(t, i, true)),
      }),
      ...lignes.map((ligne) => new TableRow({
        cantSplit: true,
        children: ligne.map((t, i) => cellule(t, i, false)),
      })),
    ],
  });
}

function espace(apres = 160) {
  return new Paragraph({ text: "", spacing: { after: apres } });
}

/** Encadré « à retenir ». */
function encadre(titreTexte, lignes) {
  const contenu = [
    new Paragraph({
      spacing: { after: 80 },
      children: [new TextRun({
        text: titreTexte, font: POLICE, size: 20, color: ACCENT, allCaps: true,
      })],
    }),
    ...lignes.map((l) => new Paragraph({
      spacing: { after: 60, line: 264 },
      alignment: AlignmentType.JUSTIFIED,
      children: [new TextRun({ text: l, font: POLICE, size: 20 })],
    })),
  ];
  return new Table({
    columnWidths: [LARGEUR_TEXTE_DXA],
    width: { size: LARGEUR_TEXTE_DXA, type: WidthType.DXA },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 6, color: ACCENT },
      bottom: { style: BorderStyle.SINGLE, size: 6, color: ACCENT },
      left: { style: BorderStyle.SINGLE, size: 6, color: ACCENT },
      right: { style: BorderStyle.SINGLE, size: 6, color: ACCENT },
    },
    rows: [new TableRow({
      children: [new TableCell({
        width: { size: LARGEUR_TEXTE_DXA, type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill: "F2F7FC", color: "auto" },
        margins: { top: 140, bottom: 140, left: 180, right: 180 },
        children: contenu,
      })],
    })],
  });
}

function sautDePage() {
  return new Paragraph({ children: [new PageBreak()] });
}

/* ======================================================================= *
 *  CONTENU
 * ======================================================================= */

const corps = [];
const A = (...x) => corps.push(...x.flat());

/* --- page de titre ----------------------------------------------------- */
A(
  new Paragraph({
    spacing: { before: 1200, after: 120 },
    children: [new TextRun({
      text: "ANNEXE", font: POLICE, size: 26, color: GRIS, allCaps: true,
    })],
  }),
  new Paragraph({
    spacing: { after: 160 },
    children: [new TextRun({
      text: "Traînée des aspérités de surface", font: POLICE, size: 52, color: ACCENT,
    })],
  }),
  new Paragraph({
    spacing: { after: 420 },
    children: [new TextRun({
      text: "Marche montante, marche descendante et arête",
      font: POLICE, size: 30, color: GRIS,
    })],
  }),
  p({ text: "Méthode de calcul du supplément de traînée engendré par une " +
         "discontinuité de surface, d’après l’AGARDograph AGARD-AG-264, " },
    { text: "Aircraft Excrescence Drag", italics: true },
    { text: " (A. D. Young et J. H. Paterson, AGARD/OTAN, juillet 1981), § 4.3." }),
  p("Pour chaque géométrie, cette annexe donne la planche d’origine du " +
    "rapport, les valeurs qui en ont été extraites, et les formules " +
    "effectivement appliquées. Le calcul est implémenté dans un script " +
    "Python autonome livré avec l’annexe (§ A.10)."),
  espace(320),
  new Paragraph({
    spacing: { after: 120 },
    children: [new TextRun({ text: "Sommaire", font: POLICE, size: 26, color: ACCENT })],
  }),
  new TableOfContents("Sommaire", { hyperlink: true, headingStyleRange: "1-2" }),
  sautDePage(),
);

/* ======================= A.1 OBJET ===================================== */
A(
  titre("A.1  Objet et principe", HeadingLevel.HEADING_1),

  p("Une surface aérodynamique n’est jamais parfaitement lisse. Un panneau " +
    "ne se repose pas exactement à fleur, une trappe dépasse de quelques " +
    "dixièmes de millimètre, un couvre-joint est rapporté par-dessus la " +
    "peau. Chacune de ces discontinuités coûte de la traînée, et la " +
    "question posée en bureau d’études est toujours la même : combien ?"),

  p("On traite ici les aspérités dites « bidimensionnelles », c’est-à-dire " +
    "longues devant leur hauteur et orientées en travers de l’écoulement. " +
    "Elles se rangent en trois familles, qui n’ont ni le même niveau de " +
    "traînée ni le même comportement en Mach :"),

  figure("schema_geometries.png",
         "Les trois géométries traitées (ligne du haut) et les trois " +
         "corrections de forme (ligne du bas), avec les notations employées.",
         600, 420),

  puce({ text: "La marche montante", bold: false, color: ACCENT },
       " : l’écoulement arrive sur une surface qui monte. C’est le cas le " +
       "plus pénalisant des deux marches."),
  puce({ text: "La marche descendante", color: ACCENT },
       " : l’écoulement quitte une surface qui descend. À bas Mach, elle " +
       "traîne deux à trois fois moins qu’une marche montante de même hauteur."),
  puce({ text: "L’arête", color: ACCENT },
       " : une marche montante suivie de près d’une marche descendante. " +
       "Ce n’est pas la somme des deux : voir § A.6.4."),

  p("La grandeur recherchée est l’incrément de traînée ", { text: "ΔD", italics: true },
    " en newtons, que l’on convertit ensuite en incrément de coefficient " +
    "de traînée ", { text: "ΔCx", italics: true }, " sur la surface de " +
    "référence de l’avion."),
);

/* ======================= A.2 SOURCE ==================================== */
A(
  titre("A.2  Source et domaine de validité", HeadingLevel.HEADING_1),

  p("Toutes les corrélations proviennent du § 4.3 de l’AGARDograph " +
    "AGARD-AG-264. Les essais sous-jacents sont ceux du RAE (Gaudet et " +
    "Winter) et de l’ARA (Pallister), complétés par des mesures plus " +
    "anciennes de Wieghardt et de Tillmann. Le rapport est en diffusion " +
    "publique."),

  p("Les essais ont été conduits sur plaque plane, en couche limite " +
    "turbulente, avec des marches très peu immergées. Le domaine de " +
    "validité qui en découle est le suivant."),

  tableau(
    ["Grandeur", "Domaine", "Origine"],
    [
      ["h⁺ = u_τ·h/ν_w", "25 à 2 000", "axes des Figures 4.23, 4.28 et 4.34"],
      ["h⁺, marche montante subsonique", "≥ 55", "les tiretés de la Figure 4.23 ne descendent pas plus bas"],
      ["h/δ (immersion)", "≤ 0,03", "§ 4.3.1.1.1, essais RAE"],
      ["Mach local, marche montante", "0,2 à 1,4", "tables"],
      ["Mach local, descendante et arête", "0,2 à 2,8", "tables"],
      ["Couche limite", "turbulente, 2-D, gradient de pression nul", "toutes les données du § 4.3"],
    ],
    [0.30, 0.22, 0.48],
  ),
  espace(),

  p("La borne basse sur h⁺ mérite un mot. Les axes des figures commencent à " +
    "10, mais les ajustements droits ne survivent pas jusque-là : la droite " +
    "de l’arête carrée à M = 0,2, dont les coefficients sont pourtant " +
    "imprimés dans le rapport, s’annule à h⁺ = 18,5. En dessous de 25, la " +
    "forme retenue prédit une traînée nulle ou négative ; le rapport ne l’a " +
    "jamais destinée à descendre là."),

  encadre("Hors du domaine", [
    "Le script livré renvoie quand même un nombre — la courbe la plus " +
    "proche est maintenue, la droite est prolongée — mais il émet un " +
    "avertissement par grandeur sortie du domaine. Un résultat accompagné " +
    "d’un avertissement doit être cité avec sa réserve, pas corrigé en " +
    "silence.",
  ]),
);

/* ======================= A.3 PRINCIPE ================================== */
A(
  sautDePage(),
  titre("A.3  Comment le calcul est mené", HeadingLevel.HEADING_1),

  titre("A.3.1  Pourquoi un nombre de Reynolds de rugosité", HeadingLevel.HEADING_2),

  p("Une aspérité suffisamment petite ne « voit » pas la couche limite " +
    "entière. Elle est noyée dans la région interne, celle où le profil de " +
    "vitesse ne dépend que de deux choses : le frottement à la paroi et la " +
    "viscosité. Sa traînée doit donc se corréler sur ces deux grandeurs " +
    "seulement, et pas sur l’épaisseur de la couche limite ni sur le " +
    "Reynolds de la voilure."),

  p("C’est le raisonnement qu’ont suivi Gaudet et Winter. Ils ont défini un " +
    "nombre de Reynolds bâti sur la hauteur de la marche et sur les " +
    "grandeurs pariétales, appelé nombre de Reynolds de rugosité :"),

  formule("h⁺ = u_τ · h / ν_w          avec   u_τ = √(τ_w / ρ_w)", "éq. 4(25)"),

  p("puis un rapport sans dimension entre la traînée de l’aspérité, " +
    "rapportée à son aire frontale, et le frottement local :"),

  formule("CDe = ΔD / (q_e · f_e)          Cfe = τ_w / q_e"),

  p("où ", { text: "f_e = h · b", italics: true }, " est l’aire frontale de " +
    "l’aspérité (hauteur × envergure) et ", { text: "q_e", italics: true },
    " la pression dynamique au bord de la couche limite. Tracé sous la " +
    "forme CDe/Cfe en fonction de h⁺, le nuage des essais se range " +
    "effectivement sur des droites — une par nombre de Mach — dès lors que " +
    "l’abscisse est logarithmique :"),

  formule("CDe / Cfe = A · log₁₀(h⁺) + B", "éq. 4(37)"),

  p("Les coefficients A et B sont donnés géométrie par géométrie aux " +
    "paragraphes A.4 à A.6. C’est le cœur de la méthode : tout le reste " +
    "n’est que la façon d’alimenter cette relation et d’en tirer une force."),

  titre("A.3.2  La relation de travail", HeadingLevel.HEADING_2),

  p("En remplaçant CDe et Cfe par leurs définitions, la pression dynamique " +
    "se simplifie. Il reste une relation remarquablement sobre :"),

  formule("ΔD = (CDe/Cfe) × f_forme × m_d × τ_w × f_e"),

  p("Autrement dit, le supplément de traînée est le produit de quatre " +
    "choses : un rapport lu dans une corrélation, un facteur de forme qui " +
    "tient compte des arêtes cassées et du biais, un éventuel facteur " +
    "d’amplification dû au gradient de pression (§ A.8), et la force de " +
    "frottement qui s’exercerait sur l’aire frontale de l’aspérité si elle " +
    "était plaquée au mur."),

  p("La pression dynamique a disparu. On n’a donc besoin que de deux " +
    "grandeurs issues de l’écoulement : le cisaillement pariétal ",
    { text: "τ_w", italics: true }, " et le nombre de Reynolds de rugosité ",
    { text: "h⁺", italics: true }, ". Le ΔCx s’en déduit si l’on veut " +
    "exprimer le résultat en coefficient :"),

  formule("ΔCx = ΔD / (q_∞ · S_réf)"),

  titre("A.3.3  Obtenir τ_w et h⁺", HeadingLevel.HEADING_2),

  p("Trois entrées sont possibles, par ordre de qualité décroissante."),

  tableau(
    ["Entrée", "Quand l’utiliser", "Qualité"],
    [
      ["τ_w mesuré ou calculé", "vous disposez d’un calcul RANS ou d’une mesure sur la configuration lisse", "exacte"],
      ["C_fe local", "vous disposez du coefficient de frottement local", "exacte"],
      ["distance x au bord d’attaque", "avant-projet : seule la géométrie est connue", "corrélation"],
    ],
    [0.26, 0.56, 0.18],
  ),
  espace(),

  p("La troisième voie passe par une corrélation de plaque plane. Le script " +
    "utilise la loi en 1/7 évaluée à la température de référence d’Eckert, " +
    "ce qui est la façon habituelle de porter une loi incompressible en " +
    "compressible :"),

  formule("T* / T_e = 0,5 · (1 + T_w/T_e) + 0,22 · r · (γ−1)/2 · M²"),
  formule("C_fe = 0,0592 · Re*ₓ^(−0,2) · ρ*/ρ_e          δ = 0,37 · x · Re*ₓ^(−0,2)"),

  p("avec r = Pr^(1/3) le facteur de récupération turbulent et T_w la " +
    "température de paroi, prise adiabatique par défaut :"),

  formule("T_w = T_e · ( 1 + r · (γ−1)/2 · M² )"),

  p("Les grandeurs pariétales qui entrent dans h⁺ se déduisent ensuite de " +
    "T_w, la pression étant constante à travers la couche limite :"),

  formule("ρ_w = p_e / (R · T_w)          ν_w = μ(T_w) / ρ_w"),

  p("où μ(T) est donnée par la loi de Sutherland. Cette troisième voie " +
    "suppose une couche limite turbulente depuis le bord d’attaque, sans " +
    "gradient de pression. Sur un profil réel, aucune des deux hypothèses " +
    "n’est exacte : si un calcul CFD est disponible, il faut lui prendre " +
    "τ_w directement."),

  titre("A.3.4  Le déroulé, étape par étape", HeadingLevel.HEADING_2),

  p("Récapitulé sous forme de recette, le calcul tient en six étapes."),

  tableau(
    ["", "Étape", "Ce qu’on obtient"],
    [
      ["1", "Établir les conditions LOCALES au bord de couche limite, à l’abscisse de l’aspérité : M, T_e, p_e", "u_e, ρ_e, q_e"],
      ["2", "Obtenir le cisaillement pariétal de la configuration lisse (mesure, CFD, ou corrélation § A.3.3)", "τ_w, C_fe, δ"],
      ["3", "En déduire les grandeurs pariétales et le nombre de Reynolds de rugosité", "u_τ, ν_w, h⁺ = u_τ·h/ν_w"],
      ["4", "Lire le rapport de traînée de la géométrie concernée (§ A.4, A.5 ou A.6)", "CDe/Cfe"],
      ["5", "Appliquer les corrections de forme : arrondi, chanfrein, épaisseur, biais", "f_forme"],
      ["6", "Multiplier et, si besoin, amplifier (§ A.8)", "ΔD, puis ΔCx"],
    ],
    [0.05, 0.63, 0.32],
    [AlignmentType.CENTER, AlignmentType.LEFT, AlignmentType.LEFT],
  ),
  espace(),

  encadre("Le piège principal", [
    "Les conditions demandées à l’étape 1 sont LOCALES : le nombre de Mach, " +
    "la température et la pression au bord de la couche limite, à " +
    "l’abscisse de l’aspérité — pas ceux de l’infini amont. Sur un extrados " +
    "en croisière, le Mach local dépasse couramment M∞ de 0,05 à 0,10, et " +
    "prendre M∞ sous-estime la traînée d’un bon tiers. C’est, de loin, la " +
    "première source d’erreur, devant toute l’incertitude des corrélations " +
    "elles-mêmes.",
  ]),
);

/* ======================= A.4 MARCHE MONTANTE =========================== */
A(
  sautDePage(),
  titre("A.4  Marche montante", HeadingLevel.HEADING_1),

  p("L’écoulement arrive sur une surface qui monte : panneau posé en " +
    "recouvrement dans le mauvais sens, bord de trappe qui dépasse, " +
    "couvre-joint rapporté. Le fluide est freiné devant la face amont, " +
    "décolle à l’arête et recolle plus loin sur la surface haute. C’est la " +
    "plus pénalisante des deux marches."),

  titre("A.4.1  La planche d’origine", HeadingLevel.HEADING_2),

  figure("orig_4_23.png",
    "Figure 4.23 du rapport AGARD-AG-264, reproduite telle quelle : traînée " +
    "des marches montantes 2-D normales à l’écoulement. En abscisse h⁺ en " +
    "échelle logarithmique, en ordonnée CDe/Cfe."),

  p("Trois droites sont tracées sur cette planche : deux en tiretés pour le " +
    "subsonique (M = 0,2 et M = 0,8) et une en trait plein marquée « M > 1 », " +
    "qui vaut pour tout le supersonique. Le rapport le dit explicitement au " +
    "§ 4.3.1.1.1 : au-delà de M = 1,4, toutes les mesures se rangent sur une " +
    "seule et même droite. La traînée de la marche montante croît donc avec " +
    "le Mach jusqu’à 1,4, puis plafonne."),

  p("Les droites subsoniques ne sont pas tracées en dessous de h⁺ ≈ 55 : il " +
    "n’y a pas de point de mesure là. C’est ce qui justifie la borne " +
    "particulière du § A.2."),

  titre("A.4.2  Ce qui en a été extrait", HeadingLevel.HEADING_2),

  p("Les trois droites ont été relevées par traitement d’image sur le scan " +
    "du rapport : isolement du tracé, puis ajustement par transformée de " +
    "Hough. La figure suivante superpose le résultat, en tiretés de couleur, " +
    "à la planche d’origine — le trait du rapport reste visible dessous."),

  figure("verif_4_23.png",
    "Vérification de l’extraction : en tiretés, les droites retenues ; en " +
    "trait plein noir, celles du rapport. Vert M = 0,2, bleu M = 0,8, " +
    "rouge M ≥ 1,4."),

  figure("ext_4_23.png",
    "L’extraction seule, redessinée depuis les coefficients du tableau " +
    "ci-dessous. C’est ce que le script calcule.", 560),

  p("Les coefficients retenus sont les suivants. Ils sont issus d’une " +
    "lecture de figure : l’incertitude de numérisation est de l’ordre de " +
    "± 3 sur CDe/Cfe, à quoi s’ajoute la dispersion expérimentale, bien " +
    "visible sur la planche d’origine."),

  tableau(
    ["Mach local", "A", "B", "CDe/Cfe à h⁺ = 100", "à h⁺ = 1 000"],
    [
      ["0,2", "60,0", "−79,0", "41,0", "101,0"],
      ["0,8", "61,5", "−74,0", "49,0", "110,5"],
      ["≥ 1,4", "76,8", "−59,5", "94,1", "170,9"],
    ],
    [0.22, 0.16, 0.16, 0.24, 0.22],
  ),
  espace(),

  titre("A.4.3  Les formules appliquées", HeadingLevel.HEADING_2),

  p("Hors de la plage transsonique, on lit directement la droite du Mach " +
    "considéré, en interpolant linéairement en Mach entre les droites " +
    "tabulées :"),

  formule("CDe/Cfe = A(M) · log₁₀(h⁺) + B(M)          M ≤ 0,8  ou  M ≥ 1,4", "éq. 4(26)"),

  p("L’interpolation porte sur le rapport de traînée, pas sur les " +
    "coefficients A et B pris séparément : B est une ordonnée à l’origine en " +
    "h⁺ = 1, une décade sous tout ce qui a été mesuré, et interpoler B seul " +
    "n’aurait pas de sens physique."),

  titre("A.4.4  Le transsonique", HeadingLevel.HEADING_2),

  p("Entre M = 0,8 et M = 1,4, on n’interpole pas linéairement. Le rapport " +
    "fournit un facteur de mélange mesuré, noté PC₁, qui pondère les deux " +
    "droites encadrantes :"),

  formule("(CDe/Cfe)_M = (CDe/Cfe)_{M=0,8} + PC₁ · [ (CDe/Cfe)_{M=1,4} − (CDe/Cfe)_{M=0,8} ]",
          "éq. 4(27)"),

  figure("orig_4_25.png",
    "Figure 4.25 du rapport : le facteur PC₁ en fonction du Mach. Par " +
    "construction PC₁(0,8) = 0 et PC₁(1,4) = 1.", 440),

  figure("ext_4_25.png",
    "Extraction de PC₁. Les cercles sont les symboles de mesure relevés un " +
    "à un sur la planche ; le trait est l’interpolation linéaire par " +
    "morceaux utilisée par le script.", 520),

  tableau(
    ["M", "0,80", "0,85", "0,90", "0,95", "1,00", "1,05", "1,10", "1,15", "1,20", "1,30", "1,40"],
    [["PC₁", "0,000", "0,022", "0,052", "0,094", "0,193", "0,399", "0,567", "0,615", "0,720", "0,871", "1,000"]],
    [0.10, 0.0818, 0.0818, 0.0818, 0.0818, 0.0818, 0.0818, 0.0818, 0.0818,
     0.0818, 0.0818, 0.0818],
  ),
  espace(),

  titre("A.4.5  Arête adoucie : arrondi et chanfrein", HeadingLevel.HEADING_2),

  p("Casser ou arrondir l’arête amont réduit la traînée, parfois beaucoup. " +
    "Le rapport donne deux familles de courbes, une par traitement, chacune " +
    "indexée par le Mach."),

  figure("orig_4_26a.png",
    "Figure 4.26(a) du rapport : réduction relative E due à l’arrondi de " +
    "l’arête amont, en fonction de r/h.", 540),

  figure("orig_4_26b.png",
    "Figure 4.26(b) : réduction relative E due au chanfrein, en fonction de " +
    "l’angle θ. θ = 90° est la marche vive, θ = 0 le carénage complet.", 540),

  figure("ext_4_26.png",
    "Extraction des deux familles. Incertitude de numérisation ± 0,03 sur " +
    "l’arrondi, ± 0,04 sur le chanfrein."),

  p("Les deux corrections s’appliquent en facteur multiplicatif sur le " +
    "rapport de traînée de la marche vive :"),

  formule("(CDe/Cfe)_r = (CDe/Cfe)_{r=0} × [ 1 − E(r/h, M) ]", "éq. 4(28)"),
  formule("(CDe/Cfe)_θ = (CDe/Cfe)_{θ=90°} × [ 1 − E(θ, M) ]", "éq. 4(29)"),

  p("Quelques ordres de grandeur, qui donnent la mesure de ce qu’on peut " +
    "attendre d’un geste de fabrication :"),

  tableau(
    ["Geste", "M = 0,8", "M = 2,0"],
    [
      ["arrondi r/h = 0,4", "facteur 0,39  (−61 %)", "facteur 0,95  (−5 %)"],
      ["chanfrein θ = 45°", "facteur 0,48  (−52 %)", "facteur 0,89  (−11 %)"],
      ["chanfrein θ = 30°", "facteur 0,29  (−71 %)", "facteur 0,82  (−18 %)"],
      ["chanfrein θ = 15°", "facteur 0,16  (−84 %)", "facteur 0,64  (−36 %)"],
    ],
    [0.34, 0.33, 0.33],
  ),
  espace(),

  encadre("À retenir", [
    "Le bénéfice d’une arête adoucie s’effondre avec le Mach. Ce qui fait " +
    "gagner 60 à 70 % en subsonique n’en fait plus gagner que 5 à 35 % à " +
    "M = 2. Un chanfrein se justifie sur un avion de transport ; il ne se " +
    "justifie plus de la même façon sur un engin supersonique.",
  ]),
);

/* ======================= A.5 MARCHE DESCENDANTE ======================== */
A(
  sautDePage(),
  titre("A.5  Marche descendante", HeadingLevel.HEADING_1),

  p("L’écoulement quitte une surface qui descend : décrochement vers " +
    "l’arrière, aval d’un joint de panneau, lèvre d’une trappe affleurante. " +
    "Le fluide décolle à l’arête, forme un bulbe de recirculation dans le " +
    "creux, et recolle quelques hauteurs de marche plus loin. Le mécanisme " +
    "est moins coûteux que celui de la marche montante."),

  titre("A.5.1  La planche d’origine", HeadingLevel.HEADING_2),

  figure("orig_4_28.png",
    "Figure 4.28 du rapport : traînée des marches descendantes vives. Sept " +
    "droites, de M = 0,2 à M = 2,8."),

  p("Le rapport prévient lui-même, au § 4.3.1.2.1, que la dispersion est ici " +
    "nettement plus forte que pour la marche montante, et il en donne deux " +
    "raisons : la couche limite amont des essais ARA était « rugueuse-" +
    "turbulente » plutôt que lisse, et la correction de flottabilité de la " +
    "balance pesait une part plus grande de l’effort mesuré."),

  titre("A.5.2  Ce qui en a été extrait", HeadingLevel.HEADING_2),

  p("Les sept droites ont été extraites une à une, par transformée de Hough " +
    "à pente sélective : on cherche la pente avant de chercher la position, " +
    "sinon les droites les plus serrées se confondent. L’ordre des courbes " +
    "supersoniques, qui se croisent au voisinage de M = 2, a été fixé par la " +
    "phrase du rapport imposant une traînée décroissante au-delà de M = 1,4."),

  figure("verif_4_28.png",
    "Vérification de l’extraction sur la planche d’origine. Vert M = 0,2, " +
    "bleu M = 0,8, rouge M = 1,4, orange M = 1,7, magenta M = 2,0, " +
    "cyan M = 2,2, brun M = 2,8."),

  figure("ext_4_28.png", "L’extraction seule.", 560),

  tableau(
    ["Mach local", "A", "B", "CDe/Cfe à h⁺ = 100", "à h⁺ = 1 000"],
    [
      ["0,2", "16,0", "−7,5", "24,5", "40,5"],
      ["0,8", "20,0", "−13,0", "27,0", "47,0"],
      ["1,4", "49,0", "−21,2", "76,8", "125,8"],
      ["1,7", "52,0", "−35,2", "68,8", "120,8"],
      ["2,0", "44,0", "−19,2", "68,8", "112,8"],
      ["2,2", "33,0", "+4,8", "70,8", "103,8"],
      ["2,8", "36,0", "−15,8", "56,2", "92,2"],
    ],
    [0.22, 0.16, 0.16, 0.24, 0.22],
  ),
  espace(),

  p("Incertitude de numérisation : ± 4 sur CDe/Cfe. Les formules sont les " +
    "mêmes qu’au § A.4.3, avec cette table."),

  titre("A.5.3  Le transsonique : un maximum, pas un plateau", HeadingLevel.HEADING_2),

  p("C’est la différence la plus importante avec la marche montante. La " +
    "traînée de la marche descendante ne plafonne pas : elle passe par un " +
    "maximum vers M ≈ 1,15, au-dessus de sa propre valeur à M = 1,4, puis " +
    "redescend. Le facteur de mélange PC₂ dépasse donc 1 — ce n’est pas une " +
    "extrapolation, c’est la mesure (Figure 4.29 du rapport)."),

  formule("(CDe/Cfe)_M = (CDe/Cfe)_{M=0,8} + PC₂ · [ (CDe/Cfe)_{M=1,4} − (CDe/Cfe)_{M=0,8} ]",
          "éq. 4(32)"),

  figure("orig_4_30.png", "Figure 4.30 du rapport : le facteur PC₂.", 420),
  figure("ext_4_30.png",
    "Extraction de PC₂. Le maximum relevé vaut 1,275 à M = 1,15.", 520),

  tableau(
    ["M", "0,80", "0,90", "0,95", "1,00", "1,05", "1,10", "1,15", "1,20", "1,30", "1,40"],
    [["PC₂", "0,000", "0,065", "0,110", "0,400", "1,030", "1,210", "1,275", "1,260", "1,140", "1,000"]],
    [0.10, 0.09, 0.09, 0.09, 0.09, 0.09, 0.09, 0.09, 0.09, 0.09, 0.09],
  ),
  espace(),

  titre("A.5.4  Arête adoucie : deux contre-intuitions", HeadingLevel.HEADING_2),

  p("Les deux traitements qui aident sur une marche montante ne se " +
    "comportent pas du tout de la même façon sur une marche descendante. Il " +
    "faut le savoir avant de prescrire quoi que ce soit."),

  p({ text: "Premièrement, arrondir l’arête aval augmente la traînée.", bold: false,
      color: ACCENT },
    " Le rapport le constate sans l’expliquer (Figure 4.32) et en tire une " +
    "relation unique, indépendante du Mach :"),

  formule("(CDe/Cfe)_r = [ 1 + 1,43 · (r/h) ] × (CDe/Cfe)_{r=0}", "éq. 4(34)"),

  p("Soit + 47 % pour r/h = 0,33 et + 72 % pour r/h = 0,5. Un bord cassé " +
    "par l’usure, côté aval, coûte donc de la traînée au lieu d’en faire " +
    "gagner."),

  p({ text: "Deuxièmement, chanfreiner ne sert à rien jusqu’à 45°", color: ACCENT },
    ", et entre 12° et 45° cela aggrave légèrement les choses au " +
    "transsonique et au supersonique. La chute n’arrive qu’en dessous de " +
    "12°, comme l’écrit le § 4.3.1.2.2."),

  formule("(CDe/Cfe)_θ = (CDe/Cfe)_{θ=90°} × [ 1 − G(θ, M) ]", "éq. 4(33)"),

  figure("orig_4_33.png",
    "Figure 4.33 du rapport : le facteur G en fonction de l’angle de " +
    "chanfrein. Sept courbes dans un cadre de quatre centimètres, qui se " +
    "croisent toutes au voisinage de G = 0.", 460),

  figure("ext_4_33.png",
    "Extraction de G. Les valeurs négatives entre 12° et 45° pour M ≥ 1,2 " +
    "traduisent une augmentation de traînée.", 520),

  tableau(
    ["Angle θ", "M = 0,8", "M = 1,4"],
    [
      ["45° et au-delà", "facteur 1,00  (sans effet)", "facteur 1,00  (sans effet)"],
      ["30°", "facteur 0,59", "facteur 1,14  (+ 14 %)"],
      ["20°", "facteur 0,31", "facteur 1,17  (+ 17 %)"],
      ["12°", "facteur 0,17", "facteur 0,99"],
      ["5°", "facteur 0,08", "facteur 0,48"],
    ],
    [0.30, 0.35, 0.35],
  ),
  espace(),

  encadre("Réserve sur cette correction", [
    "La Figure 4.33 est la planche la moins lisible du rapport : sept " +
    "courbes serrées, leurs repères et leurs lignes de rappel dans un très " +
    "petit cadre. L’incertitude de numérisation y est de ± 0,05, contre " +
    "± 0,02 à ± 0,04 ailleurs. Le texte du § 4.3.1.2.2 est ici plus net que " +
    "le tracé et l’extraction le respecte. Si une conclusion dépend de " +
    "cette correction à mieux que ± 10 %, il faut revenir à la planche " +
    "originale.",
  ]),
);

/* ======================= A.6 ARETE ===================================== */
A(
  sautDePage(),
  titre("A.6  Arête", HeadingLevel.HEADING_1),

  p("Une marche montante suivie de près d’une marche descendante : " +
    "couvre-joint, cordon de mastic, bande de protection, plaque rapportée. " +
    "Le paramètre supplémentaire est l’épaisseur t, mesurée dans le sens de " +
    "l’écoulement."),

  titre("A.6.1  La planche d’origine", HeadingLevel.HEADING_2),

  figure("orig_4_34.png",
    "Figure 4.34 du rapport : traînée des arêtes à faces verticales. La " +
    "planche porte à la fois les arêtes carrées (t = h) et les arêtes " +
    "rectangulaires d’épaisseur t = 2h, d’où le nombre de traits."),

  p("Cas particulier agréable : pour les arêtes, les coefficients A et B " +
    "ne sont pas à relever sur la figure, ils sont ", { text: "imprimés", bold: false,
    color: ACCENT }, " dans le corps du rapport, page 91, sous l’équation " +
    "4(37). La table ci-dessous est donc une transcription exacte, pas une " +
    "lecture."),

  tableau(
    ["Mach local", "A", "B", "CDe/Cfe à h⁺ = 100", "à h⁺ = 1 000"],
    [
      ["0,2", "150", "−190", "110,0", "260,0"],
      ["0,8", "150", "−160", "140,0", "290,0"],
      ["1,4", "160", "−125", "195,0", "355,0"],
      ["2,2", "110", "−42", "178,0", "288,0"],
      ["2,8", "100", "−44", "156,0", "256,0"],
    ],
    [0.22, 0.16, 0.16, 0.24, 0.22],
  ),
  espace(),

  titre("A.6.2  Ce qui en a été extrait", HeadingLevel.HEADING_2),

  p("La superposition ne sert donc pas ici à valider une lecture, mais à " +
    "contrôler la transcription — et au passage l’étalonnage en pixels " +
    "utilisé pour les deux planches précédentes."),

  figure("verif_4_34.png",
    "Vérification sur la planche d’origine. Les traits noirs sans tireté " +
    "coloré correspondant sont les arêtes rectangulaires t = 2h, qui " +
    "figurent aussi sur la planche."),

  figure("ext_4_34.png",
    "L’extraction seule, avec en tiretés gris la droite t = 2h à M = 0,2 " +
    "issue de sa table dédiée.", 560),

  titre("A.6.3  Transsonique et épaisseur", HeadingLevel.HEADING_2),

  p("Le mélange transsonique suit la même forme que pour les marches, avec " +
    "son propre facteur PC₃ :"),

  formule("(CDe/Cfe)_M = (CDe/Cfe)_{M=0,8} + PC₃ · [ (CDe/Cfe)_{M=1,4} − (CDe/Cfe)_{M=0,8} ]",
          "éq. 4(38)"),

  p("PC₃ est de loin le plus marqué des trois : il culmine à 1,58 vers " +
    "M = 1,03. Autrement dit, la traînée d’une arête passe par un pic " +
    "transsonique environ 50 % au-dessus de son niveau subsonique avant de " +
    "redescendre."),

  figure("orig_4_38.png", "Figure 4.38 du rapport : le facteur PC₃.", 460),
  figure("ext_4_38.png", "Extraction de PC₃, relevée en continu le long du tracé.", 520),

  p("L’effet de l’épaisseur se traite par un facteur multiplicatif T(t/h), " +
    "normalisé sur l’arête carrée :"),

  formule("(CDe/Cfe)_{t/h} = T(t/h) × (CDe/Cfe)_{t/h = 1}", "éq. 4(39)"),

  figure("orig_4_40.png", "Figure 4.40 du rapport : le facteur d’épaisseur T.", 460),
  figure("ext_4_40.png", "Extraction de T(t/h).", 520),

  tableau(
    ["t/h", "0", "0,25", "0,5", "1", "2", "3", "4", "≥ 5"],
    [["T", "1,07", "1,07", "1,06", "1,00", "0,79", "0,63", "0,58", "0,58"]],
    [0.12, 0.11, 0.11, 0.11, 0.11, 0.11, 0.11, 0.11, 0.11],
  ),
  espace(),

  p("La courbe mérite un commentaire. Elle est légèrement supérieure à 1 " +
    "pour les arêtes minces : une bande fine traîne un peu plus qu’une " +
    "arête carrée de même hauteur. Puis elle s’effondre vers un plateau à " +
    "0,58 au-delà de t/h ≈ 4 : à cette distance, l’écoulement a le temps de " +
    "recoller entre les deux faces, et l’aspérité cesse de se comporter " +
    "comme un objet unique."),

  encadre("Une contradiction du rapport, signalée telle quelle", [
    "Pour une arête d’épaisseur exactement t = 2h, AGARD-AG-264 donne deux " +
    "routes incompatibles : une table dédiée sous l’équation 4(37), et le " +
    "produit générique T(2) × (arête carrée) de l’équation 4(39). La " +
    "première croise la droite de l’arête carrée vers h⁺ ≈ 1 000, ce que " +
    "décrit le § 4.3.2.1 ; la seconde reste 21 % en dessous à tout h⁺. " +
    "L’écart atteint 80 % à h⁺ = 100.",
    "La raison est dans le rapport : la courbe T vient des essais " +
    "Wieghardt, tous à h/δ supérieur à 3 %, alors que le croisement " +
    "carrée/rectangulaire se situe entre h/δ = 0,02 et 0,03. Le script " +
    "suit la route générique, seule définie pour toute épaisseur, et " +
    "expose la table dédiée séparément.",
  ]),

  titre("A.6.4  Une arête n’est pas la somme de ses deux marches", HeadingLevel.HEADING_2),

  p("C’est l’enseignement le plus utile du § 4.3.2.1, et celui qu’il faut " +
    "retenir si l’on ne retient qu’une chose de cette annexe. Additionner " +
    "une marche montante et une marche descendante de même hauteur donne, " +
    "à bas Mach, environ la moitié de la traînée réellement mesurée sur " +
    "une arête carrée."),

  p("L’explication est physique : le bulbe de recirculation né sur la face " +
    "amont n’a pas eu le temps de recoller quand il rencontre la face aval. " +
    "L’interférence entre les deux faces pèse autant que les deux faces " +
    "réunies. Cet écart se résorbe à mesure que le Mach monte, et il a " +
    "disparu à M = 2,8 — ce que le rapport écrit noir sur blanc."),

  tableau(
    ["Mach", "montante", "descendante", "somme", "arête", "somme / arête"],
    [
      ["0,2", "101,0", "40,5", "141,5", "260,0", "0,544"],
      ["0,8", "110,5", "47,0", "157,5", "290,0", "0,543"],
      ["1,4", "170,9", "125,8", "296,7", "355,0", "0,836"],
      ["2,2", "170,9", "103,8", "274,7", "288,0", "0,954"],
      ["2,8", "170,9", "92,2", "263,1", "256,0", "1,028"],
    ],
    [0.14, 0.17, 0.19, 0.15, 0.15, 0.20],
  ),
  espace(60),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 240 },
    children: [new TextRun({
      text: "Valeurs de CDe/Cfe à h⁺ = 1 000.",
      font: POLICE, size: 17, italics: true, color: GRIS,
    })],
  }),

  p("Ce tableau sert aussi de contrôle croisé de la numérisation : les " +
    "droites des deux marches ont été relevées sur des planches scannées, " +
    "tandis que les coefficients de l’arête sont imprimés. Le rapport fixe " +
    "la relation entre les trois en annonçant « about 50 % below » à bas " +
    "Mach et un écart « not present in the M = 2.8 data ». On retrouve " +
    "0,544 et 1,028 sans avoir rien ajusté : une erreur de lecture de plus " +
    "de 5 % sur l’une ou l’autre droite casserait cet accord."),
);

/* ======================= A.7 DERAPAGE ================================== */
A(
  sautDePage(),
  titre("A.7  Aspérité en biais", HeadingLevel.HEADING_1),

  p("Une aspérité qui n’est pas perpendiculaire à l’écoulement ne voit que " +
    "la composante normale de la vitesse. Comme le coefficient de traînée " +
    "est normalisé sur le carré de la vitesse, la réduction va comme le " +
    "carré du sinus de l’angle."),

  formule("(CDe)_α = (CDe)_{α = 90°} × sin²α", "éq. 4(30), 4(35), 4(41)"),

  p("α est l’angle entre l’écoulement et l’axe de l’aspérité : 90° quand " +
    "elle est en travers du flux, 0 quand elle lui est parallèle."),

  figure("orig_4_45.png",
    "Figure 4.45 du rapport : le rapport mesuré comparé à sin²α, sur les " +
    "données de Wieghardt et de Kovalenko.", 480),

  figure("ext_4_45.png", "La loi retenue, sin²α.", 480),

  p("Deux précisions. D’une part, la loi n’est établie que sur des arêtes " +
    "(§ 4.3.2.3) ; l’appliquer aux marches est une hypothèse explicite du " +
    "rapport, pas une mesure. D’autre part, elle suppose que la traînée est " +
    "rapportée à l’aire frontale projetée — c’est bien la convention " +
    "retenue ici."),
);

/* ======================= A.8 GRADIENT DE PRESSION ====================== */
A(
  titre("A.8  Gradient de pression : le facteur de Nash et Bradshaw", HeadingLevel.HEADING_1),

  p("Toutes les données du § 4.3 proviennent d’essais sur plaque plane, à " +
    "gradient de pression nul. Sur un profil, l’histoire de la couche " +
    "limite en aval de l’aspérité change le résultat, et pas marginalement."),

  p("Nash et Bradshaw ont montré en 1967 que ce que l’aspérité ajoute à " +
    "l’épaisseur de quantité de mouvement est transporté jusqu’au bord de " +
    "fuite, et amplifié en chemin. L’hypothèse naïve — la traînée est " +
    "simplement proportionnelle à la pression dynamique locale — peut " +
    "sous-estimer largement l’incrément réel. Le § 5.1 du rapport en tire " +
    "un facteur d’amplification :"),

  formule("m_d = (u_eo/V₀)^4,2 × (V₀/u_eT) × (θ_o/θ_T)^(1/5)", "éq. 5(5)"),

  p("où l’indice o désigne la position de l’aspérité, l’indice T le bord de " +
    "fuite, V₀ la vitesse amont non perturbée et θ l’épaisseur de quantité " +
    "de mouvement. Sur plaque plane, tout vaut 1 et m_d vaut exactement 1."),

  p("À titre d’exemple, une aspérité placée sur un pic de survitesse avec " +
    "u_eo/V₀ = 1,25, u_eT/V₀ = 0,95 et θ_o/θ_T = 0,4 donne m_d = 2,24, " +
    "là où la proportionnalité naïve aurait donné 1,25² = 1,56."),

  encadre("Pourquoi ce facteur n’est pas appliqué d’office", [
    "m_d demande des grandeurs au bord de fuite — vitesse et épaisseur de " +
    "quantité de mouvement — que le calcul d’une marche isolée n’a aucun " +
    "moyen de deviner. Le script l’expose en fonction séparée et le " +
    "multiplie seulement si on le lui fournit. Un ΔD obtenu sans lui doit " +
    "être lu comme une valeur de plaque plane.",
    "Les hypothèses du facteur sont par ailleurs à garder en tête : " +
    "écoulement incompressible, profil turbulent en 1/7, petite " +
    "perturbation. La version compressible de Cook sous-estimait les " +
    "incréments mesurés d’environ 10 % en subcritique.",
  ]),
);

/* ======================= A.9 EXEMPLE =================================== */
A(
  sautDePage(),
  titre("A.9  Exemple numérique complet", HeadingLevel.HEADING_1),

  p("On déroule la recette du § A.3.4 sur un cas de croisière : un avion de " +
    "transport au niveau de vol 360, une aspérité située à 10 m du bord " +
    "d’attaque sur l’extrados, et un nombre de Mach local de 0,82."),

  titre("A.9.1  Étapes 1 et 2 — l’écoulement et la couche limite", HeadingLevel.HEADING_2),

  tableau(
    ["Grandeur", "Valeur", "Provenance"],
    [
      ["Altitude", "11 000 m", "donnée"],
      ["Mach local", "0,82", "donnée (bord de couche limite)"],
      ["T_e", "216,77 K", "ISA"],
      ["p_e", "22 700 Pa", "ISA"],
      ["u_e", "242,0 m/s", "M · √(γ R T_e)"],
      ["ρ_e", "0,3648 kg/m³", "p_e / (R T_e)"],
      ["q_e", "10 684 Pa", "½ ρ_e u_e²"],
      ["T_w", "242,9 K", "paroi adiabatique"],
      ["C_fe", "0,001 552", "plaque plane, x = 10 m"],
      ["τ_w", "16,58 Pa", "C_fe · q_e"],
      ["u_τ", "7,136 m/s", "√(τ_w / ρ_w)"],
      ["ν_w", "4,80 × 10⁻⁵ m²/s", "μ(T_w) / ρ_w"],
      ["δ", "105 mm", "0,37 · x · Re*ₓ^(−0,2)"],
    ],
    [0.22, 0.26, 0.52],
  ),
  espace(),

  titre("A.9.2  Étapes 3 à 6 — les trois géométries", HeadingLevel.HEADING_2),

  p("On compare trois aspérités de même hauteur, 1,5 mm, courant sur 2,4 m " +
    "d’envergure. La surface de référence de l’avion est prise à 122,6 m²."),

  p("Pour toutes les trois, l’étape 3 donne le même nombre de Reynolds de " +
    "rugosité :"),

  formule("h⁺ = 7,136 × 0,0015 / 4,80·10⁻⁵ = 223          h/δ = 0,014"),

  p("ce qui est confortablement dans le domaine : h⁺ entre 25 et 2 000, " +
    "h/δ bien en dessous de 0,03. Aucun avertissement n’est émis."),

  tableau(
    ["Géométrie", "CDe/Cfe", "f_forme", "ΔD [N]", "ΔCx"],
    [
      ["Marche montante", "70,9", "1,00", "4,23", "3,23 × 10⁻⁶"],
      ["Marche descendante", "34,7", "1,00", "2,07", "1,58 × 10⁻⁶"],
      ["Arête carrée (t = h)", "197,0", "1,00", "11,76", "8,98 × 10⁻⁶"],
    ],
    [0.30, 0.16, 0.16, 0.16, 0.22],
  ),
  espace(),

  p("Le détail du calcul pour la marche montante, étape par étape :"),

  formule("CDe/Cfe = 61,5 · log₁₀(223) − 74,0 = 70,9          (M = 0,82 ≈ 0,8)"),
  formule("f_e = 0,0015 × 2,4 = 3,60 × 10⁻³ m²"),
  formule("ΔD = 70,9 × 1,00 × 16,58 × 3,60·10⁻³ = 4,23 N"),
  formule("ΔCx = 4,23 / (10 684 × 122,6) = 3,23 × 10⁻⁶"),

  titre("A.9.3  Ce que rapporte un chanfrein", HeadingLevel.HEADING_2),

  p("Même marche montante de 1,5 mm, arête cassée :"),

  tableau(
    ["Angle θ", "f_forme", "ΔD [N]", "Gain"],
    [
      ["90° (vive)", "1,000", "4,23", "—"],
      ["45°", "0,493", "2,08", "−51 %"],
      ["30°", "0,302", "1,28", "−70 %"],
      ["15°", "0,168", "0,71", "−83 %"],
    ],
    [0.26, 0.24, 0.24, 0.26],
  ),
  espace(),

  titre("A.9.4  Sensibilité à la hauteur", HeadingLevel.HEADING_2),

  p("Même configuration, marche montante, par mètre d’envergure. La traînée " +
    "croît plus vite que la hauteur : doubler h fait plus que doubler ΔD, " +
    "parce que CDe/Cfe grandit lui aussi avec log(h⁺)."),

  tableau(
    ["h", "h⁺", "h/δ", "CDe/Cfe", "ΔD par mètre"],
    [
      ["0,5 mm", "74", "0,005", "41,5", "0,34 N"],
      ["1,0 mm", "149", "0,009", "60,0", "1,00 N"],
      ["1,5 mm", "223", "0,014", "70,9", "1,76 N"],
      ["2,0 mm", "297", "0,019", "78,6", "2,61 N"],
      ["3,0 mm", "446", "0,029", "89,4", "4,45 N"],
    ],
    [0.18, 0.16, 0.16, 0.22, 0.28],
  ),
  espace(),
);

/* ======================= A.10 LE SCRIPT ================================ */
A(
  sautDePage(),
  titre("A.10  Mise en œuvre : le script livré", HeadingLevel.HEADING_1),

  p("Le calcul est implémenté dans un fichier Python unique, ",
    { text: "trainee_marches.py", font: "Consolas", size: 20 },
    ", livré avec cette annexe. Tout y est : les tables extraites, " +
    "l’atmosphère, la couche limite, les corrélations, les corrections et " +
    "l’assemblage. Il n’a besoin que de NumPy."),

  p("Deux bibliothèques maison sont utilisées si elles sont présentes, et " +
    "seulement si elles le sont : ",
    { text: "cfd-atm", font: "Consolas", size: 20 },
    " pour l’atmosphère — ce qui donne accès à l’ISA décalée d’un ΔT, aux " +
    "altitudes pression et géopotentielle, et aux conversions Vc / EAS / " +
    "TAS vers le Mach — et ",
    { text: "cfd-plot", font: "Consolas", size: 20 },
    " pour le style des figures. En leur absence, le script retombe sur une " +
    "ISA interne limitée à l’altitude géométrique et sur Matplotlib nu ; " +
    "ce qu’il ne sait pas faire, il le refuse en le disant, plutôt que de " +
    "rendre un nombre faux."),

  titre("A.10.1  Usage", HeadingLevel.HEADING_2),

  new Paragraph({
    spacing: { before: 80, after: 200 },
    shading: { type: ShadingType.CLEAR, fill: "F2F2F2", color: "auto" },
    border: {
      top: { style: BorderStyle.SINGLE, size: 2, color: "BFBFBF" },
      bottom: { style: BorderStyle.SINGLE, size: 2, color: "BFBFBF" },
      left: { style: BorderStyle.SINGLE, size: 2, color: "BFBFBF" },
      right: { style: BorderStyle.SINGLE, size: 2, color: "BFBFBF" },
    },
    children: [
      new TextRun({ text: "  python3 trainee_marches.py", font: "Consolas", size: 19 }),
      new TextRun({ break: 1, text: "  python3 trainee_marches.py --figures ./FIGURES",
                    font: "Consolas", size: 19 }),
    ],
  }),

  p("La première commande déroule l’exemple du § A.9 et l’affiche étape par " +
    "étape. La seconde écrit en plus les planches d’extraction reproduites " +
    "dans cette annexe — ce sont donc bien les tables du fichier livré qui " +
    "ont servi à les tracer."),

  titre("A.10.2  En bibliothèque", HeadingLevel.HEADING_2),

  new Paragraph({
    spacing: { before: 80, after: 200 },
    shading: { type: ShadingType.CLEAR, fill: "F2F2F2", color: "auto" },
    border: {
      top: { style: BorderStyle.SINGLE, size: 2, color: "BFBFBF" },
      bottom: { style: BorderStyle.SINGLE, size: 2, color: "BFBFBF" },
      left: { style: BorderStyle.SINGLE, size: 2, color: "BFBFBF" },
      right: { style: BorderStyle.SINGLE, size: 2, color: "BFBFBF" },
    },
    children: [
      "from trainee_marches import (",
      "    EtatLocal, CoucheLimite, Asperite, calculer_trainee, MONTANTE)",
      "",
      "# 1-2. ecoulement LOCAL et couche limite non perturbee",
      "etat   = EtatLocal.atmosphere(altitude=11000.0, mach=0.82)",
      "couche = CoucheLimite.plaque_plane(etat, x=10.0)",
      "#      ou, si tau_w vient d'un calcul RANS :",
      "# couche = CoucheLimite.depuis_cisaillement(etat, tau_w=16.58)",
      "",
      "# 3-6. la marche, puis la trainee",
      "marche = Asperite(MONTANTE, hauteur=1.5e-3, envergure=2.4)",
      "r = calculer_trainee(marche, etat, couche, surface_reference=122.6)",
      "",
      "print(r.h_plus, r.cde_sur_cfe, r.trainee, r.delta_cx)",
      "for message in r.avertissements:",
      "    print('attention :', message)",
    ].map((ligne, i) => new TextRun({
      text: "  " + ligne, font: "Consolas", size: 19, break: i === 0 ? 0 : 1,
    })),
  }),

  titre("A.10.3  Fonctions principales", HeadingLevel.HEADING_2),

  tableau(
    ["Fonction", "Rôle"],
    [
      ["EtatLocal.atmosphere(...)", "conditions locales depuis une altitude et une vitesse (Mach, Vc, TAS ou EAS)"],
      ["CoucheLimite.depuis_cisaillement(...)", "couche limite depuis un τ_w mesuré ou calculé — la voie exacte"],
      ["CoucheLimite.plaque_plane(...)", "couche limite depuis la distance au bord d’attaque — avant-projet"],
      ["ratio_marche_montante(h⁺, M)", "CDe/Cfe, § A.4"],
      ["ratio_marche_descendante(h⁺, M)", "CDe/Cfe, § A.5"],
      ["ratio_arete(h⁺, M, t_sur_h)", "CDe/Cfe, § A.6"],
      ["interference_arete(h⁺, M)", "arête, somme des deux marches, et leur rapport"],
      ["facteur_arrondi_montante / _descendante", "corrections d’arrondi, § A.4.5 et A.5.4"],
      ["facteur_chanfrein_montante / _descendante", "corrections de chanfrein"],
      ["facteur_derapage(α)", "sin²α, § A.7"],
      ["facteur_amplification_nash_bradshaw(...)", "m_d, § A.8"],
      ["calculer_trainee(...)", "ΔD, ΔCx et les avertissements de domaine"],
      ["tracer_extractions(rep)", "les planches d’extraction de cette annexe"],
    ],
    [0.44, 0.56],
    [AlignmentType.LEFT, AlignmentType.LEFT],
  ),
  espace(),
);

/* ======================= A.11 REFERENCES =============================== */
A(
  titre("A.11  Références", HeadingLevel.HEADING_1),

  p({ text: "[1]  " },
    { text: "YOUNG A. D., PATERSON J. H.", bold: false },
    { text: "  Aircraft Excrescence Drag", italics: true },
    ". AGARDograph n° 264, AGARD/OTAN, juillet 1981. ISBN 92-835-1392-4. " +
    "Diffusion publique (AD-A106030). Le § 4.3 est celui utilisé ici ; le " +
    "§ 5.1 fournit le facteur de Nash et Bradshaw."),

  p({ text: "[2]  " },
    { text: "GAUDET L., WINTER K. G.", bold: false },
    "  Measurements of the Drag of Some Characteristic Aircraft " +
    "Excrescences Immersed in Turbulent Boundary Layers. RAE, référence " +
    "4.5 du rapport [1] — source principale des Figures 4.23, 4.28 et 4.34."),

  p({ text: "[3]  " },
    { text: "PALLISTER K. C.", bold: false },
    "  Référence 4.15 du rapport [1] — essais ARA dans le domaine " +
    "transsonique, source des facteurs PC₁, PC₂ et PC₃."),

  p({ text: "[4]  " },
    { text: "NASH J. F., BRADSHAW P.", bold: false },
    "  The magnification of roughness drag by pressure gradients. " +
    "Journal of the Royal Aeronautical Society, 1967. Référence 5.2 du " +
    "rapport [1]."),

  titre("Ce que cette annexe ne couvre pas", HeadingLevel.HEADING_2),

  p("Le rapport [1] va bien au-delà des marches et des arêtes. Les sujets " +
    "suivants relèvent d’autres paragraphes et ne sont pas traités ici :"),

  puce("rivets, vis, cylindres, trous, antennes — § 4.2 ;"),
  puce("jeux et rainures — § 4.3.3 ; ondulations de surface — § 4.3.4 ;"),
  puce("rugosité distribuée et grain de sable équivalent — § 3 et § 5.5 ;"),
  puce("transition déclenchée par l’aspérité (hauteurs critiques) — § 2.2 ;"),
  puce("effet sur le CL maximal — § 5.3 ;"),
  puce("entrées et sorties d’air auxiliaires, fuites — § 6 ;"),
  puce("arêtes arrondies ou chanfreinées, Figures 4.41 à 4.44 — § 4.3.2.2."),

  p("Un point mérite une mise en garde particulière : les arêtes multiples " +
    "en série (§ 4.3.2.4). Plusieurs arêtes rapprochées ne s’additionnent " +
    "pas. La Figure 4.46 du rapport montre un espacement critique, vers " +
    "s ≈ 10 h, où la traînée totale passe par un maximum. Sommer les " +
    "contributions individuelles de joints régulièrement espacés est " +
    "optimiste dans cette zone."),
);

/* ======================= DOCUMENT ====================================== */

const document = new Document({
  creator: "cfd-aq",
  title: "Annexe — Traînée des aspérités de surface",
  description: "Marche montante, marche descendante et arête, d'après AGARD-AG-264 § 4.3",
  numbering: {
    config: [{
      reference: "puces",
      levels: [{
        level: 0,
        format: LevelFormat.BULLET,
        text: "•",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 420, hanging: 220 } } },
      }],
    }],
  },
  styles: {
    default: {
      document: { run: { font: POLICE, size: 21 } },
      heading1: {
        run: { font: POLICE, size: 30, color: ACCENT, bold: false },
        paragraph: { spacing: { before: 360, after: 160 } },
      },
      heading2: {
        run: { font: POLICE, size: 24, color: ACCENT, bold: false },
        paragraph: { spacing: { before: 280, after: 120 } },
      },
    },
  },
  sections: [{
    properties: { page: { margin: { top: MARGE, bottom: MARGE, left: MARGE, right: MARGE } } },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: "Annexe — Traînée des aspérités de surface   ·   ",
                          font: POLICE, size: 16, color: GRIS }),
            new TextRun({ children: [PageNumber.CURRENT], font: POLICE, size: 16, color: GRIS }),
          ],
        })],
      }),
    },
    children: corps,
  }],
});

Packer.toBuffer(document).then((tampon) => {
  fs.writeFileSync(SORTIE, tampon);
  const ko = Math.round(fs.statSync(SORTIE).size / 1024);
  console.log(`${SORTIE}  (${ko} ko, ${compteurFigure} figures)`);
});
