/*
 * 70_vignettes.js — illustrations des réglages de détection.
 *
 * « Pas », « épaisseur min. », « suivi de continuité » : les intitulés des
 * réglages sont exacts mais opaques tant qu'on n'a pas vu ce qu'ils font. Une
 * vignette de quarante pixels de haut le dit d'un coup d'œil, et ce module ne
 * fait que cela — rendre des chaînes SVG, sans toucher au DOM, ce qui les rend
 * vérifiables comme n'importe quelle autre fonction.
 *
 * SVG et non canvas, pour trois raisons : le dessin reste net à toute échelle
 * et sur écran HiDPI, il tient dans le fichier autonome sans image binaire, et
 * il se relit et se corrige à la main.
 */
(function (racine) {
  'use strict';

  var CFDD = racine.CFDD || (racine.CFDD = {});
  var Vignettes = {};

  Vignettes.LARGEUR = 72;
  Vignettes.HAUTEUR = 48;

  var GRIS = '#b6bcc6';
  var ENCRE = '#3d4450';
  var ACCENT = '#1b6ec2';
  var CHAUD = '#e8590c';
  var MAGENTA = '#d6249f';

  /* Courbe témoin, en ligne brisée : connaître ses sommets exactement permet
     de poser les points de balayage dessus sans approximation. */
  var COURBE = 'M8 40 L16 34 L24 24 L32 16 L40 12 L48 12 L56 16 L64 24';
  /* Courbe repliée : deux ordonnées pour une même abscisse — le cas où le
     balayage en colonnes ment et où il faut passer en lignes. */
  var REPLIEE = 'M20 8 L32 14 L28 22 L16 30 L22 40';

  function trait(d, couleur, largeur, tirets) {
    return '<path d="' + d + '" fill="none" stroke="' + couleur
      + '" stroke-width="' + largeur + '" stroke-linecap="round" stroke-linejoin="round"'
      + (tirets ? ' stroke-dasharray="' + tirets + '"' : '') + '/>';
  }

  function point(x, y, couleur, r) {
    return '<circle cx="' + x + '" cy="' + y + '" r="' + (r || 2)
      + '" fill="' + couleur + '"/>';
  }

  function anneau(x, y, couleur, r) {
    return '<circle cx="' + x + '" cy="' + y + '" r="' + (r || 2)
      + '" fill="#fff" stroke="' + couleur + '" stroke-width="1.2"/>';
  }

  function barre(x0, y0, x1, y1) {
    return '<path d="M' + x0 + ' ' + y0 + ' L' + x1 + ' ' + y1
      + '" stroke="' + GRIS + '" stroke-width="1" stroke-dasharray="2 2"/>';
  }

  function refus(x, y) {
    var r = 5;
    return '<path d="M' + (x - r) + ' ' + (y - r) + ' L' + (x + r) + ' ' + (y + r)
      + ' M' + (x + r) + ' ' + (y - r) + ' L' + (x - r) + ' ' + (y + r)
      + '" stroke="' + CHAUD + '" stroke-width="1.6" stroke-linecap="round"/>';
  }

  function disques(couleurs, retenus) {
    var s = '', i;
    for (i = 0; i < couleurs.length; i++) {
      var x = 10 + i * 13;
      s += '<circle cx="' + x + '" cy="24" r="5.5" fill="' + couleurs[i] + '"'
        + (retenus > i ? ' stroke="' + ENCRE + '" stroke-width="1.6"' : '') + '/>';
    }
    return s;
  }

  /* Corps de chaque vignette, sans la balise <svg> englobante. */
  var DESSINS = {

    /* --- Sens de balayage --- */
    'orientation:colonnes':
      barre(16, 6, 16, 42) + barre(32, 6, 32, 42) + barre(48, 6, 48, 42) + barre(64, 6, 64, 42)
      + trait(COURBE, GRIS, 3)
      + point(16, 34, ACCENT) + point(32, 16, ACCENT)
      + point(48, 12, ACCENT) + point(64, 24, ACCENT),

    'orientation:lignes':
      barre(6, 12, 66, 12) + barre(6, 20, 66, 20) + barre(6, 28, 66, 28) + barre(6, 36, 66, 36)
      + trait(REPLIEE, GRIS, 3)
      + point(28, 12, ACCENT) + point(29, 20, ACCENT)
      + point(19, 28, ACCENT) + point(19.6, 36, ACCENT),

    /* --- Mode d'extraction --- */
    'mode:moyenne':
      trait(COURBE, GRIS, 6)
      + point(16, 34, ACCENT, 1.7) + point(24, 24, ACCENT, 1.7) + point(32, 16, ACCENT, 1.7)
      + point(40, 12, ACCENT, 1.7) + point(48, 12, ACCENT, 1.7) + point(56, 16, ACCENT, 1.7),

    'mode:tous':
      '<ellipse cx="36" cy="24" rx="22" ry="14" fill="none" stroke="' + GRIS + '" stroke-width="3"/>'
      + point(24, 12.3, ACCENT, 1.7) + point(24, 35.7, ACCENT, 1.7)
      + point(36, 10, ACCENT, 1.7) + point(36, 38, ACCENT, 1.7)
      + point(48, 12.3, ACCENT, 1.7) + point(48, 35.7, ACCENT, 1.7),

    'mode:suivi':
      trait('M8 10 L64 38', GRIS, 3)
      + trait('M8 38 L64 10', GRIS, 3)
      + point(12, 36, ACCENT, 1.7) + point(20, 32, ACCENT, 1.7) + point(28, 28, ACCENT, 1.7)
      + point(36, 24, ACCENT, 1.7) + point(44, 20, ACCENT, 1.7) + point(52, 16, ACCENT, 1.7)
      + point(60, 12, ACCENT, 1.7),

    /* --- Type de trait --- */
    'filtreTrait:tous':
      trait('M8 14 H64', ACCENT, 2.6)
      + trait('M8 24 H64', ACCENT, 2.6, '8 5')
      + trait('M8 34 H64', ACCENT, 2.6, '1.5 4'),

    'filtreTrait:continu':
      trait('M8 14 H64', ACCENT, 2.6)
      + trait('M8 24 H64', GRIS, 2.6, '8 5')
      + trait('M8 34 H64', GRIS, 2.6, '1.5 4'),

    'filtreTrait:tirets':
      trait('M8 14 H64', GRIS, 2.6)
      + trait('M8 24 H64', ACCENT, 2.6, '8 5')
      + trait('M8 34 H64', GRIS, 2.6, '1.5 4'),

    'filtreTrait:pointillé':
      trait('M8 14 H64', GRIS, 2.6)
      + trait('M8 24 H64', GRIS, 2.6, '8 5')
      + trait('M8 34 H64', ACCENT, 2.6, '1.5 4'),

    'filtreTrait:discontinu':
      trait('M8 14 H64', GRIS, 2.6)
      + trait('M8 24 H64', ACCENT, 2.6, '8 5')
      + trait('M8 34 H64', ACCENT, 2.6, '1.5 4'),

    /* --- Rendu de l'aperçu --- */
    'apercuMode:surbrillance':
      trait('M8 36 L28 30 L44 34 L64 28', '#8aa0b8', 2)
      + trait(COURBE, MAGENTA, 4),

    'apercuMode:isoler':
      trait('M8 36 L28 30 L44 34 L64 28', '#8aa0b8', 2)
      + trait(COURBE, '#c1121f', 3)
      + '<rect x="1" y="1" width="70" height="46" fill="#fff" opacity="0.72"/>'
      + trait(COURBE, '#c1121f', 3),

    'apercuMode:les-deux':
      trait('M8 36 L28 30 L44 34 L64 28', '#8aa0b8', 2)
      + trait(COURBE, '#c1121f', 3)
      + '<rect x="1" y="1" width="70" height="46" fill="#fff" opacity="0.72"/>'
      + trait(COURBE, MAGENTA, 4),

    /* --- Réglages numériques --- */
    'pas':
      trait('M8 16 H64', GRIS, 2.5)
      + point(8, 16, ACCENT, 1.4) + point(14, 16, ACCENT, 1.4) + point(20, 16, ACCENT, 1.4)
      + point(26, 16, ACCENT, 1.4) + point(32, 16, ACCENT, 1.4) + point(38, 16, ACCENT, 1.4)
      + point(44, 16, ACCENT, 1.4) + point(50, 16, ACCENT, 1.4) + point(56, 16, ACCENT, 1.4)
      + point(62, 16, ACCENT, 1.4)
      + trait('M8 34 H64', GRIS, 2.5)
      + point(8, 34, ACCENT, 2.2) + point(26, 34, ACCENT, 2.2)
      + point(44, 34, ACCENT, 2.2) + point(62, 34, ACCENT, 2.2),

    /* Le segment retenu à gauche, l'écarté à droite : c'est le contraste des
       deux qui dit ce que le réglage rejette, pas le seul survivant. */
    'epaisseur-min':
      trait('M18 14 L18 34', ACCENT, 5)
      + point(50, 15, GRIS, 1.8) + point(50, 24, GRIS, 1.8) + point(50, 33, GRIS, 1.8)
      + refus(50, 24),

    'epaisseur-max':
      trait('M18 14 L18 34', ACCENT, 2.5)
      + '<rect x="41" y="11" width="18" height="26" rx="3" fill="' + GRIS + '"/>'
      + refus(50, 24),

    'allegement':
      trait('M8 16 L24 10 L40 18 L64 12', GRIS, 2)
      + point(8, 16, ACCENT, 1.3) + point(12, 14.5, ACCENT, 1.3) + point(16, 13, ACCENT, 1.3)
      + point(20, 11.5, ACCENT, 1.3) + point(24, 10, ACCENT, 1.3) + point(30, 13, ACCENT, 1.3)
      + point(36, 16, ACCENT, 1.3) + point(40, 18, ACCENT, 1.3) + point(48, 16, ACCENT, 1.3)
      + point(56, 14, ACCENT, 1.3) + point(64, 12, ACCENT, 1.3)
      + trait('M8 40 L24 34 L40 42 L64 36', GRIS, 2)
      + point(8, 40, ACCENT, 2.2) + point(24, 34, ACCENT, 2.2)
      + point(40, 42, ACCENT, 2.2) + point(64, 36, ACCENT, 2.2),

    'combler':
      trait('M8 24 H64', GRIS, 3, '9 7')
      + point(11, 24, ACCENT, 1.8) + point(15, 24, ACCENT, 1.8)
      + anneau(20, 24, CHAUD, 1.8) + anneau(24, 24, CHAUD, 1.8)
      + point(28, 24, ACCENT, 1.8) + point(32, 24, ACCENT, 1.8)
      + anneau(37, 24, CHAUD, 1.8) + anneau(41, 24, CHAUD, 1.8)
      + point(45, 24, ACCENT, 1.8) + point(49, 24, ACCENT, 1.8)
      + anneau(54, 24, CHAUD, 1.8) + anneau(58, 24, CHAUD, 1.8)
      + point(62, 24, ACCENT, 1.8),

    'tol-chroma':
      disques(['#1b6ec2', '#445799', '#6e4070', '#972947', '#c1121f'], 3),

    'tol-lum':
      disques(['#1b6ec2', '#5496d9', '#8db7e8', '#c6dbf3', '#f2f7fd'], 3)
  };

  /* Légendes des vignettes des réglages numériques (les autres sont libellées
     par l'option de liste déroulante qu'elles illustrent). */
  Vignettes.NUMERIQUES = [
    { cle: 'pas', titre: 'Pas',
      texte: 'Une ligne de balayage sur N. Pas = 1 échantillonne chaque pixel ; '
        + 'l’augmenter allège la série sans rien changer à la forme.' },
    { cle: 'epaisseur-min', titre: 'Épaisseur min.',
      texte: 'Longueur minimale d’un segment retenu, le long de la ligne de '
        + 'balayage. Écarte les pixels isolés : anticrénelage, grain du scan, '
        + 'poussière.' },
    { cle: 'epaisseur-max', titre: 'Épaisseur max.',
      texte: 'Longueur maximale. 0 = sans limite. Écarte les aplats : zone '
        + 'colorée, symbole plein, texte de la même couleur que la courbe.' },
    { cle: 'allegement', titre: 'Allègement',
      texte: 'Supprime les points qui n’apportent rien à la forme, à la '
        + 'tolérance donnée près (en pixels). Une courbe lisse passe de mille '
        + 'points à quelques dizaines, sans déformation visible.' },
    { cle: 'combler', titre: 'Combler les lacunes',
      texte: 'Relie par interpolation les tronçons d’un trait discontinu. Les '
        + 'points ajoutés sont comptés à part : ils sont déduits, pas mesurés.' },
    { cle: 'tol-chroma', titre: 'Tolérance de teinte',
      texte: 'Écart de couleur admis dans le plan a*b*. C’est elle qui sépare '
        + 'deux courbes de couleurs différentes.' },
    { cle: 'tol-lum', titre: 'Tolérance de clarté',
      texte: 'Écart admis sur L*. L’anticrénelage éclaircit fortement les bords '
        + 'du trait sans en changer la teinte : c’est cette tolérance qui les '
        + 'rattrape — et la seule qui discrimine une courbe noire ou grise.' }
  ];

  Vignettes.existe = function (cle) {
    return Object.prototype.hasOwnProperty.call(DESSINS, cle);
  };

  Vignettes.cles = function () { return Object.keys(DESSINS); };

  /*
   * Rend la vignette `cle`, ou null si elle n'existe pas — un réglage sans
   * illustration ne doit pas casser le panneau, juste ne rien afficher.
   * `titre` alimente le <title> SVG, lu par les lecteurs d'écran.
   */
  Vignettes.svg = function (cle, titre) {
    if (!Vignettes.existe(cle)) { return null; }
    return '<svg viewBox="0 0 ' + Vignettes.LARGEUR + ' ' + Vignettes.HAUTEUR + '"'
      + ' width="' + Vignettes.LARGEUR + '" height="' + Vignettes.HAUTEUR + '"'
      + ' role="img" aria-label="' + echapper(titre || cle) + '">'
      + '<title>' + echapper(titre || cle) + '</title>'
      + '<rect x="0.5" y="0.5" width="' + (Vignettes.LARGEUR - 1) + '" height="'
      + (Vignettes.HAUTEUR - 1) + '" rx="3" fill="#ffffff" stroke="#d6d9de"/>'
      + DESSINS[cle] + '</svg>';
  };

  function echapper(texte) {
    return String(texte).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  CFDD.Vignettes = Vignettes;
  if (typeof module !== 'undefined' && module.exports) { module.exports = Vignettes; }
})(typeof globalThis !== 'undefined' ? globalThis : this);
