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
   * Formes de marqueur. Une planche digitalisée porte souvent trois ou quatre
   * séries qui se croisent : la couleur seule ne suffit plus à savoir laquelle
   * on est en train de pointer, surtout imprimée en noir et blanc. La forme,
   * elle, reste lisible partout.
   */
  Vue.FORMES = ['cercle', 'anneau', 'carre', 'losange', 'triangle', 'croix', 'plus'];

  Vue.LIBELLES_FORME = {
    cercle: 'disque', anneau: 'anneau', carre: 'carré', losange: 'losange',
    triangle: 'triangle', croix: 'croix ×', plus: 'plus +'
  };

  Vue.STYLE_POINT = { couleur: '#c1121f', forme: 'cercle', taille: 2.5 };

  Vue.normaliserStyle = function (style) {
    /* Tolère une simple couleur : c'était la signature d'origine. */
    if (typeof style === 'string') { style = { couleur: style }; }
    style = style || {};
    var forme = style.forme;
    if (Vue.FORMES.indexOf(forme) === -1) { forme = Vue.STYLE_POINT.forme; }
    var taille = Number(style.taille);
    if (!isFinite(taille) || taille <= 0) { taille = Vue.STYLE_POINT.taille; }
    return {
      couleur: style.couleur || Vue.STYLE_POINT.couleur,
      forme: forme,
      taille: Base.borner(taille, 0.5, 20)
    };
  };

  /*
   * Trace une marque au rayon `r`. Les formes creuses (anneau, croix, plus)
   * sont tracées au trait : posées sur la courbe elles la laissent voir, ce
   * qui est précisément ce qu'on veut en pointant à la main.
   */
  Vue.tracerMarque = function (ctx, cx, cy, forme, r) {
    ctx.beginPath();
    switch (forme) {
      case 'carre':
        ctx.rect(cx - r, cy - r, 2 * r, 2 * r); ctx.fill(); break;
      case 'losange':
        ctx.moveTo(cx, cy - r * 1.25); ctx.lineTo(cx + r * 1.25, cy);
        ctx.lineTo(cx, cy + r * 1.25); ctx.lineTo(cx - r * 1.25, cy);
        ctx.closePath(); ctx.fill(); break;
      case 'triangle':
        ctx.moveTo(cx, cy - r * 1.3); ctx.lineTo(cx + r * 1.2, cy + r * 0.9);
        ctx.lineTo(cx - r * 1.2, cy + r * 0.9);
        ctx.closePath(); ctx.fill(); break;
      case 'anneau':
        ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke(); break;
      case 'croix':
        ctx.moveTo(cx - r, cy - r); ctx.lineTo(cx + r, cy + r);
        ctx.moveTo(cx + r, cy - r); ctx.lineTo(cx - r, cy + r);
        ctx.stroke(); break;
      case 'plus':
        ctx.moveTo(cx - r * 1.2, cy); ctx.lineTo(cx + r * 1.2, cy);
        ctx.moveTo(cx, cy - r * 1.2); ctx.lineTo(cx, cy + r * 1.2);
        ctx.stroke(); break;
      default:
        ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill(); break;
    }
  };

  /*
   * Nuage de points d'une série. `style` accepte une couleur seule ou
   * {couleur, forme, taille}.
   *
   * Au-delà de quelques milliers de points le tracé marque par marque devient
   * le poste de coût dominant du rafraîchissement : on bascule alors sur des
   * carrés pleins, visuellement équivalents à cette densité — et à cette
   * densité, la forme du marqueur ne se distingue plus de toute façon.
   */
  Vue.dessinerPoints = function (ctx, vue, points, style, selection) {
    if (!points.length) { return; }
    var s = Vue.normaliserStyle(style);
    ctx.save();
    ctx.fillStyle = s.couleur;
    ctx.strokeStyle = s.couleur;
    ctx.lineWidth = Math.max(1, s.taille * 0.6);

    var i, e;
    if (points.length > 4000) {
      var cote = Math.max(1.5, s.taille);
      for (i = 0; i < points.length; i++) {
        e = Vue.versEcran(vue, points[i].px, points[i].py);
        ctx.fillRect(e.cx - cote / 2, e.cy - cote / 2, cote, cote);
      }
    } else {
      for (i = 0; i < points.length; i++) {
        e = Vue.versEcran(vue, points[i].px, points[i].py);
        Vue.tracerMarque(ctx, e.cx, e.cy, s.forme, s.taille);
      }
    }

    if (selection !== undefined && selection !== null && points[selection]) {
      e = Vue.versEcran(vue, points[selection].px, points[selection].py);
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(e.cx, e.cy, s.taille + 3, 0, Math.PI * 2); ctx.stroke();
      ctx.strokeStyle = s.couleur;
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(e.cx, e.cy, s.taille + 3, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.restore();
  };

  Vue.MODES_MASQUE = {
    /* Les pixels retenus sont peints d'une couleur franche. */
    surbrillance: 'surbrillance',
    /* Les pixels ÉCARTÉS sont voilés : seuls les retenus gardent leurs couleurs. */
    isoler: 'isoler',
    /* Les deux à la fois : le plus lisible sur une figure chargée. */
    lesDeux: 'les-deux'
  };

  /*
   * Calque de l'aperçu du masque, construit une fois dans un canevas hors écran
   * à la taille de la ZONE, puis étiré — bien plus rapide que de repeindre
   * pixel par pixel à chaque zoom.
   *
   * options :
   *   couleur    {r,g,b} de surbrillance
   *   mode       'surbrillance' | 'isoler' | 'les-deux'
   *   epaissir   0 ou 1 : épaissit le rendu d'un pixel
   *   voile      {r,g,b} du voile appliqué aux pixels écartés
   *   opaciteVoile  0-255
   *
   * `epaissir` mérite un mot : un trait d'un pixel affiché à l'échelle 0,4 ne
   * couvre plus un pixel d'écran entier et disparaît par endroits — l'aperçu
   * donne alors l'impression d'un masque troué alors que le masque est intact.
   * La dilatation ne touche QUE l'affichage, jamais les points extraits.
   */
  Vue.calqueMasque = function (info, options, fabriquerCanvas) {
    options = options || {};
    var couleur = options.couleur || { r: 255, g: 0, b: 255 };
    var mode = options.mode || Vue.MODES_MASQUE.surbrillance;
    var voile = options.voile || { r: 255, g: 255, b: 255 };
    var opaciteVoile = (options.opaciteVoile === undefined) ? 190 : options.opaciteVoile;

    var w = info.largeurZone, h = info.hauteurZone;
    var source = info.masque;

    /* Dilatation d'affichage en 4-connexité. */
    var vu = source;
    if (options.epaissir) {
      vu = new Uint8Array(w * h);
      for (var y = 0; y < h; y++) {
        for (var x = 0; x < w; x++) {
          var i = y * w + x;
          if (source[i]
              || (x > 0 && source[i - 1]) || (x < w - 1 && source[i + 1])
              || (y > 0 && source[i - w]) || (y < h - 1 && source[i + w])) {
            vu[i] = 1;
          }
        }
      }
    }

    var c = fabriquerCanvas(w, h);
    var ctx = c.getContext('2d');
    var image = ctx.createImageData(w, h);
    var d = image.data;

    var peindre = (mode !== Vue.MODES_MASQUE.isoler);
    var voiler = (mode !== Vue.MODES_MASQUE.surbrillance);

    for (var p = 0; p < vu.length; p++) {
      var j = p * 4;
      if (vu[p]) {
        if (peindre) {
          d[j] = couleur.r; d[j + 1] = couleur.g; d[j + 2] = couleur.b; d[j + 3] = 255;
        }
        /* En mode « isoler » seul, le pixel retenu reste transparent : on veut
           voir sa vraie couleur, c'est tout l'intérêt. */
      } else if (voiler) {
        d[j] = voile.r; d[j + 1] = voile.g; d[j + 2] = voile.b; d[j + 3] = opaciteVoile;
      }
    }

    ctx.putImageData(image, 0, 0);
    return c;
  };

  Vue.dessinerMasque = function (ctx, vue, calque, zone, opacite) {
    ctx.save();
    ctx.globalAlpha = (opacite === undefined) ? 0.85 : opacite;
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
