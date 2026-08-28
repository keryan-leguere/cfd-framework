/*
 * 60_vue.js — cadrage, zoom et rendu du canevas.
 *
 * La partie « géométrie de la vue » (versEcran / versImage / ajuster /
 * zoomerAutour) est purement numérique et testée ; la partie « dessin » se
 * contente d'appeler un contexte 2D et reste volontairement mince.
 *
 * Convention unique dans tout le fichier :
 *   - coordonnées IMAGE  : (px, py), le pixel source, origine en haut à gauche ;
 *   - coordonnées ÉCRAN  : (cx, cy), le canevas affiché.
 * Le passage de l'une à l'autre est une similitude : cx = px * echelle + dx.
 */
(function (racine) {
  'use strict';

  var CFDD = racine.CFDD || (racine.CFDD = {});
  var Base = CFDD.Base;
  var Vue = {};

  Vue.ECHELLE_MIN = 0.05;
  Vue.ECHELLE_MAX = 64;

  Vue.creer = function () {
    return { echelle: 1, dx: 0, dy: 0 };
  };

  Vue.versEcran = function (vue, px, py) {
    return { cx: px * vue.echelle + vue.dx, cy: py * vue.echelle + vue.dy };
  };

  Vue.versImage = function (vue, cx, cy) {
    return { px: (cx - vue.dx) / vue.echelle, py: (cy - vue.dy) / vue.echelle };
  };

  /* Cadre l'image entière dans le canevas, centrée, avec une marge en pixels. */
  Vue.ajuster = function (largeurImage, hauteurImage, largeurCanvas, hauteurCanvas, marge) {
    marge = marge || 0;
    var utileL = Math.max(1, largeurCanvas - 2 * marge);
    var utileH = Math.max(1, hauteurCanvas - 2 * marge);
    var echelle = Math.min(utileL / largeurImage, utileH / hauteurImage);
    echelle = Base.borner(echelle, Vue.ECHELLE_MIN, Vue.ECHELLE_MAX);
    return {
      echelle: echelle,
      dx: (largeurCanvas - largeurImage * echelle) / 2,
      dy: (hauteurCanvas - hauteurImage * echelle) / 2
    };
  };

  /*
   * Zoom centré sur un point de l'écran : le pixel image sous le curseur ne
   * doit pas bouger. C'est ce qui rend le zoom à la molette naturel — sans
   * cela, l'image fuit sous la souris dès qu'on s'éloigne du centre.
   */
  Vue.zoomerAutour = function (vue, cx, cy, facteur) {
    var nouvelle = Base.borner(vue.echelle * facteur, Vue.ECHELLE_MIN, Vue.ECHELLE_MAX);
    if (nouvelle === vue.echelle) { return { echelle: vue.echelle, dx: vue.dx, dy: vue.dy }; }
    var avant = Vue.versImage(vue, cx, cy);
    return {
      echelle: nouvelle,
      dx: cx - avant.px * nouvelle,
      dy: cy - avant.py * nouvelle
    };
  };

  Vue.deplacer = function (vue, deltaX, deltaY) {
    return { echelle: vue.echelle, dx: vue.dx + deltaX, dy: vue.dy + deltaY };
  };

  /*
   * Empêche l'image de sortir entièrement du cadre : on impose qu'il en reste
   * toujours `garde` pixels visibles de chaque côté. Sans cette contrainte, un
   * glissement un peu vif fait disparaître l'image et l'utilisateur ne sait
   * plus où la retrouver.
   */
  Vue.contraindre = function (vue, largeurImage, hauteurImage, largeurCanvas, hauteurCanvas, garde) {
    garde = (garde === undefined) ? 40 : garde;
    var l = largeurImage * vue.echelle, h = hauteurImage * vue.echelle;
    return {
      echelle: vue.echelle,
      dx: Base.borner(vue.dx, garde - l, largeurCanvas - garde),
      dy: Base.borner(vue.dy, garde - h, hauteurCanvas - garde)
    };
  };

  /* --- Rendu -------------------------------------------------------- */

  Vue.RAYON_REPERE = 7;
  Vue.RAYON_POINT = 2.5;

  /*
   * Dessine l'image source. `lisser` doit être faux au-delà de 1:1 : à fort
   * zoom on veut voir les pixels tels quels pour viser le centre du trait,
   * pas une interpolation qui invente des positions intermédiaires.
   */
  Vue.dessinerImage = function (ctx, source, vue) {
    ctx.imageSmoothingEnabled = vue.echelle < 1;
    ctx.drawImage(source, vue.dx, vue.dy,
      source.width * vue.echelle, source.height * vue.echelle);
  };

  /* Croix de repère de calibration, avec son étiquette. */
  Vue.dessinerRepere = function (ctx, vue, repere, etiquette, couleur, actif) {
    var e = Vue.versEcran(vue, repere.px, repere.py);
    var r = Vue.RAYON_REPERE;

    ctx.save();
    ctx.lineWidth = actif ? 2.5 : 1.5;
    ctx.strokeStyle = couleur;
    ctx.beginPath();
    ctx.moveTo(e.cx - r, e.cy); ctx.lineTo(e.cx + r, e.cy);
    ctx.moveTo(e.cx, e.cy - r); ctx.lineTo(e.cx, e.cy + r);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(e.cx, e.cy, r * 0.55, 0, Math.PI * 2);
    ctx.stroke();

    ctx.font = '11px system-ui, sans-serif';
    ctx.textBaseline = 'bottom';
    var largeur = ctx.measureText(etiquette).width;
    /* Cartouche opaque : une étiquette posée sur un tracé dense est illisible. */
    ctx.fillStyle = 'rgba(255,255,255,0.85)';
    ctx.fillRect(e.cx + r + 1, e.cy - r - 13, largeur + 6, 14);
    ctx.fillStyle = couleur;
    ctx.fillText(etiquette, e.cx + r + 4, e.cy - r);
    ctx.restore();
  };

  /* Rectangle de zone : trait plein pour l'analyse, hachuré pour une exclusion. */
  Vue.dessinerRectangle = function (ctx, vue, zone, couleur, exclusion) {
    var a = Vue.versEcran(vue, zone.x0, zone.y0);
    var b = Vue.versEcran(vue, zone.x1, zone.y1);
    ctx.save();
    ctx.strokeStyle = couleur;
    ctx.lineWidth = 1.5;
    if (exclusion) { ctx.setLineDash([6, 4]); }
    ctx.strokeRect(Math.min(a.cx, b.cx), Math.min(a.cy, b.cy),
      Math.abs(b.cx - a.cx), Math.abs(b.cy - a.cy));
    ctx.restore();
  };

  /*
   * Nuage de points d'une série. Au-delà de quelques milliers de points le
   * tracé arc par arc devient le poste de coût dominant du rafraîchissement :
   * on bascule alors sur des carrés d'un pixel, visuellement équivalents à
   * cette densité.
   */
  Vue.dessinerPoints = function (ctx, vue, points, couleur, selection) {
    if (!points.length) { return; }
    ctx.save();
    ctx.fillStyle = couleur;

    var i, e;
    if (points.length > 4000) {
      for (i = 0; i < points.length; i++) {
        e = Vue.versEcran(vue, points[i].px, points[i].py);
        ctx.fillRect(e.cx - 0.5, e.cy - 0.5, 1.5, 1.5);
      }
    } else {
      for (i = 0; i < points.length; i++) {
        e = Vue.versEcran(vue, points[i].px, points[i].py);
        ctx.beginPath();
        ctx.arc(e.cx, e.cy, Vue.RAYON_POINT, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    if (selection !== undefined && selection !== null && points[selection]) {
      e = Vue.versEcran(vue, points[selection].px, points[selection].py);
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(e.cx, e.cy, Vue.RAYON_POINT + 3, 0, Math.PI * 2); ctx.stroke();
      ctx.strokeStyle = couleur;
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(e.cx, e.cy, Vue.RAYON_POINT + 3, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.restore();
  };

  /*
   * Surimpression du masque de détection : les pixels retenus sont teintés.
   * Construite une fois dans un canevas hors écran à la taille de la ZONE, puis
   * étirée — bien plus rapide que de repeindre pixel par pixel à chaque zoom.
   */
  Vue.calqueMasque = function (info, couleur, fabriquerCanvas) {
    var c = fabriquerCanvas(info.largeurZone, info.hauteurZone);
    var ctx = c.getContext('2d');
    var image = ctx.createImageData(info.largeurZone, info.hauteurZone);
    var d = image.data;
    for (var i = 0; i < info.masque.length; i++) {
      if (!info.masque[i]) { continue; }
      var j = i * 4;
      d[j] = couleur.r; d[j + 1] = couleur.g; d[j + 2] = couleur.b; d[j + 3] = 255;
    }
    ctx.putImageData(image, 0, 0);
    return c;
  };

  Vue.dessinerMasque = function (ctx, vue, calque, zone, opacite) {
    ctx.save();
    ctx.globalAlpha = (opacite === undefined) ? 0.55 : opacite;
    ctx.imageSmoothingEnabled = false;
    var a = Vue.versEcran(vue, zone.x0, zone.y0);
    ctx.drawImage(calque, a.cx, a.cy,
      calque.width * vue.echelle, calque.height * vue.echelle);
    ctx.restore();
  };

  /*
   * Loupe : fenêtre agrandie autour du curseur, avec réticule.
   * C'est l'outil qui rend le pointage manuel précis — sans elle, viser le
   * centre d'un trait de 2 px à l'échelle 1 relève de la devinette.
   */
  Vue.dessinerLoupe = function (ctx, source, px, py, taille, facteur, couleurReticule) {
    var etendue = taille / facteur;          /* côté de la zone source, en pixels image */
    ctx.save();
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, taille, taille);
    ctx.drawImage(source,
      px - etendue / 2, py - etendue / 2, etendue, etendue,
      0, 0, taille, taille);

    ctx.strokeStyle = couleurReticule || '#000000';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(taille / 2, 0); ctx.lineTo(taille / 2, taille);
    ctx.moveTo(0, taille / 2); ctx.lineTo(taille, taille / 2);
    ctx.stroke();
    /* Carré central : matérialise le pixel exactement sous le curseur. */
    ctx.strokeRect(taille / 2 - facteur / 2, taille / 2 - facteur / 2, facteur, facteur);
    ctx.restore();
  };

  CFDD.Vue = Vue;
  if (typeof module !== 'undefined' && module.exports) { module.exports = Vue; }
})(typeof globalThis !== 'undefined' ? globalThis : this);
