/*
 * 00_cadre.js — micro-cadre de test, sans dépendance.
 *
 * Les mêmes fichiers de test tournent sous node (tests/executer.js) et dans un
 * navigateur (tests/index.html). Sur une machine coupée du réseau, pouvoir
 * lancer la suite en ouvrant une page est précieux : node n'est pas toujours là.
 */
(function (racine) {
  'use strict';

  var CFDD = racine.CFDD || (racine.CFDD = {});
  var Tests = CFDD.Tests || (CFDD.Tests = {});

  Tests.suites = Tests.suites || [];

  Tests.suite = function (nom, corps) {
    var cas = [];
    corps(function (titre, fn) { cas.push({ titre: titre, fn: fn }); });
    Tests.suites.push({ nom: nom, cas: cas });
  };

  function decrire(v) {
    if (typeof v === 'number') { return String(v); }
    try { return JSON.stringify(v); } catch (e) { return String(v); }
  }

  var A = {};

  A.ok = function (valeur, message) {
    if (!valeur) { throw new Error((message || 'attendu vrai') + ' (obtenu ' + decrire(valeur) + ')'); }
  };

  A.egal = function (obtenu, attendu, message) {
    if (obtenu !== attendu) {
      throw new Error((message || 'égalité') + ' : attendu ' + decrire(attendu)
        + ', obtenu ' + decrire(obtenu));
    }
  };

  A.proche = function (obtenu, attendu, tolerance, message) {
    tolerance = (tolerance === undefined) ? 1e-9 : tolerance;
    if (typeof obtenu !== 'number' || !isFinite(obtenu) || Math.abs(obtenu - attendu) > tolerance) {
      throw new Error((message || 'proximité') + ' : attendu ' + attendu
        + ' ± ' + tolerance + ', obtenu ' + decrire(obtenu));
    }
  };

  A.egalProfond = function (obtenu, attendu, message) {
    var a = JSON.stringify(obtenu), b = JSON.stringify(attendu);
    if (a !== b) {
      throw new Error((message || 'structures') + ' : attendu ' + b + ', obtenu ' + a);
    }
  };

  A.leve = function (fn, motif, message) {
    var leve = false, msg = '';
    try { fn(); } catch (e) { leve = true; msg = e.message; }
    if (!leve) { throw new Error((message || 'exception attendue') + ' : rien n’a été levé'); }
    if (motif && msg.indexOf(motif) === -1) {
      throw new Error((message || 'exception') + ' : message « ' + msg
        + ' » ne contient pas « ' + motif + ' »');
    }
  };

  Tests.assert = A;

  /*
   * Exécute toutes les suites. `rapporter(evenement)` reçoit des objets
   * {type: 'suite'|'ok'|'echec'|'bilan', ...}. Retourne {total, echecs}.
   */
  Tests.executer = function (rapporter) {
    var total = 0, echecs = 0;
    for (var i = 0; i < Tests.suites.length; i++) {
      var suite = Tests.suites[i];
      rapporter({ type: 'suite', nom: suite.nom });
      for (var j = 0; j < suite.cas.length; j++) {
        var c = suite.cas[j];
        total++;
        try {
          c.fn(A);
          rapporter({ type: 'ok', titre: c.titre });
        } catch (e) {
          echecs++;
          rapporter({ type: 'echec', titre: c.titre, erreur: e });
        }
      }
    }
    rapporter({ type: 'bilan', total: total, echecs: echecs });
    return { total: total, echecs: echecs };
  };

  /* --- Fabriques d'images synthétiques ------------------------------ */

  /*
   * Crée une image RGBA remplie d'une couleur de fond.
   * Interface volontairement identique à un ImageData du canvas, pour que les
   * tests exercent exactement le code utilisé en production.
   */
  Tests.imageVide = function (largeur, hauteur, fond) {
    fond = fond || { r: 255, g: 255, b: 255 };
    var data = new Uint8ClampedArray(largeur * hauteur * 4);
    for (var i = 0; i < largeur * hauteur; i++) {
      data[i * 4] = fond.r; data[i * 4 + 1] = fond.g;
      data[i * 4 + 2] = fond.b; data[i * 4 + 3] = 255;
    }
    return { data: data, width: largeur, height: hauteur };
  };

  Tests.poser = function (image, x, y, rgb, alpha) {
    x = Math.round(x); y = Math.round(y);
    if (x < 0 || y < 0 || x >= image.width || y >= image.height) { return; }
    var i = (y * image.width + x) * 4;
    if (alpha === undefined || alpha >= 1) {
      image.data[i] = rgb.r; image.data[i + 1] = rgb.g; image.data[i + 2] = rgb.b;
    } else {
      /* Mélange alpha sur le fond existant : simule l'anticrénelage. */
      image.data[i] = Math.round(image.data[i] * (1 - alpha) + rgb.r * alpha);
      image.data[i + 1] = Math.round(image.data[i + 1] * (1 - alpha) + rgb.g * alpha);
      image.data[i + 2] = Math.round(image.data[i + 2] * (1 - alpha) + rgb.b * alpha);
    }
    image.data[i + 3] = 255;
  };

  /*
   * Trace y = f(x) en pixels, avec une épaisseur et un anticrénelage vertical.
   * Le rendu imite ce que produit un vrai traceur : cœur opaque, bords fondus.
   */
  Tests.tracerCourbe = function (image, f, rgb, options) {
    options = options || {};
    var epaisseur = options.epaisseur || 3;
    var x0 = (options.x0 === undefined) ? 0 : options.x0;
    var x1 = (options.x1 === undefined) ? image.width - 1 : options.x1;
    var demi = epaisseur / 2;

    for (var x = x0; x <= x1; x++) {
      var yc = f(x);
      if (!isFinite(yc)) { continue; }
      var yMin = Math.floor(yc - demi - 1), yMax = Math.ceil(yc + demi + 1);
      for (var y = yMin; y <= yMax; y++) {
        /* Couverture du pixel [y, y+1] par la bande [yc-demi, yc+demi]. */
        var haut = Math.max(y - 0.5, yc - demi);
        var bas = Math.min(y + 0.5, yc + demi);
        var couverture = bas - haut;
        if (couverture > 0) {
          Tests.poser(image, x, y, rgb, Math.min(1, couverture));
        }
      }
    }
  };

  if (typeof module !== 'undefined' && module.exports) { module.exports = Tests; }
})(typeof globalThis !== 'undefined' ? globalThis : this);
