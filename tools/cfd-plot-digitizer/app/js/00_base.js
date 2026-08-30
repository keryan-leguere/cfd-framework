/*
 * 00_base.js — espace de noms, utilitaires numériques.
 *
 * Toutes les briques « logique » de cfd-plot-digitizer suivent le même motif :
 * un IIFE qui accroche son module sur `CFDD`. Aucun `import` / `export` ES :
 * les modules ES sont bloqués par la politique d'origine de Firefox sur
 * `file://`, or ouvrir index.html sans serveur est justement le but.
 */
(function (racine) {
  'use strict';

  var CFDD = racine.CFDD || (racine.CFDD = {});

  CFDD.VERSION = '1.0.0';

  var Base = {};

  /* Borne v dans [min, max]. */
  Base.borner = function (v, min, max) {
    return v < min ? min : (v > max ? max : v);
  };

  Base.estFini = function (v) {
    return typeof v === 'number' && isFinite(v);
  };

  /*
   * Résout A·x = b par élimination de Gauss avec pivot partiel.
   * A : tableau n×n (tableau de lignes), b : tableau n. Retourne x (longueur n)
   * ou null si la matrice est singulière au seuil `tol`.
   * Les systèmes manipulés ici sont 2×2 ou 3×3 : la lisibilité prime.
   */
  Base.resoudre = function (A, b, tol) {
    tol = (tol === undefined) ? 1e-12 : tol;
    var n = b.length;
    var i, j, k;

    /* Copie de travail : on ne modifie pas les entrées de l'appelant. */
    var M = [];
    for (i = 0; i < n; i++) {
      M.push(A[i].slice(0, n).concat([b[i]]));
    }

    for (k = 0; k < n; k++) {
      /* Pivot partiel. */
      var pivotLigne = k;
      var pivotVal = Math.abs(M[k][k]);
      for (i = k + 1; i < n; i++) {
        if (Math.abs(M[i][k]) > pivotVal) {
          pivotVal = Math.abs(M[i][k]);
          pivotLigne = i;
        }
      }
      if (pivotVal < tol) { return null; }
      if (pivotLigne !== k) {
        var tmp = M[k]; M[k] = M[pivotLigne]; M[pivotLigne] = tmp;
      }
      for (i = k + 1; i < n; i++) {
        var facteur = M[i][k] / M[k][k];
        if (facteur === 0) { continue; }
        for (j = k; j <= n; j++) {
          M[i][j] -= facteur * M[k][j];
        }
      }
    }

    var x = new Array(n);
    for (i = n - 1; i >= 0; i--) {
      var somme = M[i][n];
      for (j = i + 1; j < n; j++) { somme -= M[i][j] * x[j]; }
      x[i] = somme / M[i][i];
    }
    return x;
  };

  /*
   * Formatage d'un nombre avec un nombre de chiffres significatifs donné,
   * en évitant la notation exponentielle tant qu'elle n'est pas nécessaire
   * (un CSV lisible vaut mieux qu'un CSV « exact »).
   */
  Base.formaterNombre = function (v, chiffres) {
    if (v === null || v === undefined || !isFinite(v)) { return ''; }
    chiffres = chiffres || 6;
    if (v === 0) { return '0'; }
    var absolu = Math.abs(v);
    if (absolu >= 1e-4 && absolu < 1e9) {
      /* toPrecision peut basculer en exponentiel : on repasse par Number. */
      var texte = Number(v.toPrecision(chiffres)).toString();
      if (texte.indexOf('e') === -1) { return texte; }
    }
    return v.toExponential(chiffres - 1);
  };

  /*
   * Simplification Ramer–Douglas–Peucker : réduit un polyligne en conservant
   * sa forme à `epsilon` près. Utilisé pour dégraisser une courbe détectée
   * (une détection colonne par colonne produit un point par pixel).
   */
  Base.simplifier = function (points, epsilon) {
    if (!points || points.length < 3 || !(epsilon > 0)) {
      return points ? points.slice() : [];
    }

    var garder = new Uint8Array(points.length);
    garder[0] = 1;
    garder[points.length - 1] = 1;

    /* Pile explicite : une récursion profonde casserait sur 10^5 points. */
    var pile = [[0, points.length - 1]];
    while (pile.length) {
      var seg = pile.pop();
      var debut = seg[0], fin = seg[1];
      if (fin <= debut + 1) { continue; }

      var ax = points[debut].x, ay = points[debut].y;
      var bx = points[fin].x, by = points[fin].y;
      var dx = bx - ax, dy = by - ay;
      var norme = Math.sqrt(dx * dx + dy * dy);

      var distMax = -1, indexMax = -1;
      for (var i = debut + 1; i < fin; i++) {
        var px = points[i].x - ax, py = points[i].y - ay;
        var d;
        if (norme < 1e-15) {
          d = Math.sqrt(px * px + py * py);
        } else {
          d = Math.abs(px * dy - py * dx) / norme;
        }
        if (d > distMax) { distMax = d; indexMax = i; }
      }

      if (distMax > epsilon) {
        garder[indexMax] = 1;
        pile.push([debut, indexMax]);
        pile.push([indexMax, fin]);
      }
    }

    var sortie = [];
    for (var k = 0; k < points.length; k++) {
      if (garder[k]) { sortie.push(points[k]); }
    }
    return sortie;
  };

  /*
   * Rectangle {x0, y0, x1, y1} donné dans n'importe quel sens : normalise les
   * coins. Les rectangles de l'interface sont tracés à la souris, donc x1 peut
   * très bien être à gauche de x0.
   */
  Base.normaliserRectangle = function (rect) {
    return {
      x0: Math.min(rect.x0, rect.x1),
      y0: Math.min(rect.y0, rect.y1),
      x1: Math.max(rect.x0, rect.x1),
      y1: Math.max(rect.y0, rect.y1)
    };
  };

  Base.dansRectangle = function (point, rect) {
    var r = Base.normaliserRectangle(rect);
    return point.px >= r.x0 && point.px <= r.x1
        && point.py >= r.y0 && point.py <= r.y1;
  };

  /*
   * Retire d'un nuage les points tombant dans un rectangle, et dit combien.
   * C'est la gomme « en zone » : effacer point par point un artefact de
   * plusieurs centaines de pixels — une légende captée, une grille prise pour
   * une courbe — demande autant de clics que de points.
   */
  Base.retirerDansRectangle = function (points, rect) {
    var gardes = [], retires = 0;
    for (var i = 0; i < points.length; i++) {
      if (Base.dansRectangle(points[i], rect)) { retires++; }
      else { gardes.push(points[i]); }
    }
    return { points: gardes, retires: retires };
  };

  CFDD.Base = Base;

  /* Permet d'exécuter la même source sous node pour les tests. */
  if (typeof module !== 'undefined' && module.exports) { module.exports = Base; }
})(typeof globalThis !== 'undefined' ? globalThis : this);
