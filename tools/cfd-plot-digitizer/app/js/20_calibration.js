/*
 * 20_calibration.js — passage pixels <-> coordonnées données.
 *
 * MODÈLE (démonstration complète dans 00_DOC/01_CALIBRATION.md)
 *
 * On cherche une application AFFINE du plan pixel vers le plan données :
 *
 *     u = gx . p + cx          (u = x, ou log10(x) si axe logarithmique)
 *     v = gy . p + cy
 *
 * avec p = (px, py) le pixel, gx et gy deux gradients (vecteurs 2D).
 * L'affine — et non une simple mise à l'échelle par axe — est ce qui permet
 * de traiter une image scannée de travers ou un tracé légèrement cisaillé.
 *
 * L'utilisateur ne fournit que 4 repères : deux sur l'axe X (dont il ne connaît
 * que la valeur x) et deux sur l'axe Y (dont il ne connaît que la valeur y).
 * Cela fait 2 équations par gradient alors qu'un gradient en compte 3 : le
 * système est sous-déterminé d'un degré. On le ferme avec l'hypothèse
 * géométrique qui définit ce qu'est un repère cartésien :
 *
 *     « x est constant le long de l'axe Y, y est constant le long de l'axe X »
 *
 * soit, en notant ux = X2 - X1 et uy = Y2 - Y1 (vecteurs pixel) :
 *
 *     gx . uy = 0        et      gx . ux = u2 - u1
 *     gy . ux = 0        et      gy . uy = v2 - v1
 *
 * Deux systèmes 2x2 indépendants, réguliers dès que les deux axes ne sont pas
 * parallèles. Aucune hypothèse d'orthogonalité des axes À L'ÉCRAN n'est faite :
 * seule leur indépendance compte.
 */
(function (racine) {
  'use strict';

  var CFDD = racine.CFDD || (racine.CFDD = {});
  var Base = CFDD.Base;
  var Calibration = {};

  Calibration.ORDRE = ['x1', 'x2', 'y1', 'y2'];

  Calibration.LIBELLES = {
    x1: 'X1 — premier repère sur l’axe X',
    x2: 'X2 — second repère sur l’axe X',
    y1: 'Y1 — premier repère sur l’axe Y',
    y2: 'Y2 — second repère sur l’axe Y'
  };

  /*
   * Vérifie un jeu de repères avant résolution et renvoie la liste des
   * problèmes (vide si tout va bien). Séparé de `creer` pour que l'interface
   * puisse afficher les erreurs au fil de la saisie sans lever d'exception.
   */
  Calibration.verifier = function (reperes, logX, logY) {
    var soucis = [];
    var i, cle, p;

    for (i = 0; i < Calibration.ORDRE.length; i++) {
      cle = Calibration.ORDRE[i];
      p = reperes ? reperes[cle] : null;
      if (!p) {
        soucis.push('Repère ' + cle.toUpperCase() + ' non placé.');
        continue;
      }
      if (!Base.estFini(p.px) || !Base.estFini(p.py)) {
        soucis.push('Repère ' + cle.toUpperCase() + ' : position pixel invalide.');
      }
      if (!Base.estFini(p.valeur)) {
        soucis.push('Repère ' + cle.toUpperCase() + ' : valeur non renseignée.');
      }
    }
    if (soucis.length) { return soucis; }

    if (logX && (reperes.x1.valeur <= 0 || reperes.x2.valeur <= 0)) {
      soucis.push('Axe X logarithmique : les valeurs X1 et X2 doivent être > 0.');
    }
    if (logY && (reperes.y1.valeur <= 0 || reperes.y2.valeur <= 0)) {
      soucis.push('Axe Y logarithmique : les valeurs Y1 et Y2 doivent être > 0.');
    }
    if (reperes.x1.valeur === reperes.x2.valeur) {
      soucis.push('X1 et X2 doivent porter deux valeurs différentes.');
    }
    if (reperes.y1.valeur === reperes.y2.valeur) {
      soucis.push('Y1 et Y2 doivent porter deux valeurs différentes.');
    }

    var uxx = reperes.x2.px - reperes.x1.px, uxy = reperes.x2.py - reperes.x1.py;
    var uyx = reperes.y2.px - reperes.y1.px, uyy = reperes.y2.py - reperes.y1.py;
    if (Math.abs(uxx) < 1e-9 && Math.abs(uxy) < 1e-9) {
      soucis.push('X1 et X2 sont confondus à l’écran.');
    }
    if (Math.abs(uyx) < 1e-9 && Math.abs(uyy) < 1e-9) {
      soucis.push('Y1 et Y2 sont confondus à l’écran.');
    }
    if (soucis.length) { return soucis; }

    /*
     * Sinus de l'angle entre les deux axes, normalisé : mesure directement le
     * conditionnement du problème. Sous ~5° les deux axes sont quasi colinéaires
     * et l'inversion amplifie démesurément l'erreur de pointage.
     */
    var det = uxx * uyy - uxy * uyx;
    var sinus = Math.abs(det) / (Math.hypot(uxx, uxy) * Math.hypot(uyx, uyy));
    if (sinus < 0.0872) {   /* sin(5°) */
      soucis.push('Les axes X et Y sont presque parallèles à l’écran ('
        + (Math.asin(Math.min(1, sinus)) * 180 / Math.PI).toFixed(1)
        + '°) : la calibration serait très imprécise.');
    }
    return soucis;
  };

  /*
   * Construit la calibration. Lève une Error si les repères sont invalides
   * (utiliser `verifier` en amont pour un message doux).
   */
  Calibration.creer = function (config) {
    var reperes = config.reperes;
    var logX = !!config.logX;
    var logY = !!config.logY;

    var soucis = Calibration.verifier(reperes, logX, logY);
    if (soucis.length) { throw new Error(soucis.join(' ')); }

    function versInterne(valeur, log) { return log ? Math.log(valeur) / Math.LN10 : valeur; }

    var u1 = versInterne(reperes.x1.valeur, logX);
    var u2 = versInterne(reperes.x2.valeur, logX);
    var v1 = versInterne(reperes.y1.valeur, logY);
    var v2 = versInterne(reperes.y2.valeur, logY);

    var ux = [reperes.x2.px - reperes.x1.px, reperes.x2.py - reperes.x1.py];
    var uy = [reperes.y2.px - reperes.y1.px, reperes.y2.py - reperes.y1.py];

    /* gx . uy = 0 ; gx . ux = u2 - u1 */
    var gx = Base.resoudre([uy, ux], [0, u2 - u1]);
    /* gy . ux = 0 ; gy . uy = v2 - v1 */
    var gy = Base.resoudre([ux, uy], [0, v2 - v1]);

    if (!gx || !gy) { throw new Error('Repères dégénérés : axes colinéaires.'); }

    var cx = u1 - (gx[0] * reperes.x1.px + gx[1] * reperes.x1.py);
    var cy = v1 - (gy[0] * reperes.y1.px + gy[1] * reperes.y1.py);

    /* Matrice directe A = [gx ; gy] et son décalage c. */
    var A = [[gx[0], gx[1]], [gy[0], gy[1]]];
    var c = [cx, cy];

    var cal = {
      A: A,
      c: c,
      logX: logX,
      logY: logY,
      reperes: reperes,

      /* Pixel -> données. */
      versDonnees: function (px, py) {
        var u = A[0][0] * px + A[0][1] * py + c[0];
        var v = A[1][0] * px + A[1][1] * py + c[1];
        return {
          x: logX ? Math.pow(10, u) : u,
          y: logY ? Math.pow(10, v) : v
        };
      },

      /* Données -> pixel (inversion analytique de la 2x2). */
      versPixels: function (x, y) {
        var u = logX ? (Math.log(x) / Math.LN10) : x;
        var v = logY ? (Math.log(y) / Math.LN10) : y;
        var sol = Base.resoudre(A, [u - c[0], v - c[1]]);
        if (!sol) { return null; }
        return { px: sol[0], py: sol[1] };
      }
    };

    return cal;
  };

  /*
   * Longueur, en unités de données, d'un pixel au voisinage de (px, py).
   * Sert à afficher une incertitude honnête : sur un axe log, un pixel ne vaut
   * pas la même chose en bas et en haut de l'échelle.
   */
  Calibration.resolutionLocale = function (cal, px, py) {
    var o = cal.versDonnees(px, py);
    var dx = cal.versDonnees(px + 1, py);
    var dy = cal.versDonnees(px, py + 1);
    return {
      x: Math.max(Math.abs(dx.x - o.x), Math.abs(dy.x - o.x)),
      y: Math.max(Math.abs(dx.y - o.y), Math.abs(dy.y - o.y))
    };
  };

  CFDD.Calibration = Calibration;
  if (typeof module !== 'undefined' && module.exports) { module.exports = Calibration; }
})(typeof globalThis !== 'undefined' ? globalThis : this);
