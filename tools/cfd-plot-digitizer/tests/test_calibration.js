(function () {
  'use strict';
  var T = globalThis.CFDD.Tests, K = globalThis.CFDD.Calibration;

  function reperesDroits() {
    return {
      x1: { px: 100, py: 500, valeur: 0 },
      x2: { px: 600, py: 500, valeur: 10 },
      y1: { px: 100, py: 500, valeur: 0 },
      y2: { px: 100, py: 100, valeur: 5 }
    };
  }

  T.suite('Calibration — pixels vers données', function (test) {

    test('mappe un repère orthonormé droit', function (a) {
      var c = K.creer({ reperes: reperesDroits() });
      var m = c.versDonnees(350, 300);
      a.proche(m.x, 5, 1e-9); a.proche(m.y, 2.5, 1e-9);
      /* Les repères eux-mêmes doivent retomber sur leurs valeurs. */
      a.proche(c.versDonnees(100, 500).x, 0, 1e-9);
      a.proche(c.versDonnees(600, 500).x, 10, 1e-9);
      a.proche(c.versDonnees(100, 100).y, 5, 1e-9);
    });

    test('inverse exactement la transformation', function (a) {
      var c = K.creer({ reperes: reperesDroits() });
      var p = c.versPixels(7.3, 1.8);
      a.proche(p.px, 465, 1e-8); a.proche(p.py, 356, 1e-8);
      var retour = c.versDonnees(p.px, p.py);
      a.proche(retour.x, 7.3, 1e-9); a.proche(retour.y, 1.8, 1e-9);
    });

    test('gère un axe X logarithmique', function (a) {
      var r = reperesDroits();
      r.x1.valeur = 1; r.x2.valeur = 1000;
      /* 3 décades sur 500 px : une décade tous les 166.67 px. */
      var c = K.creer({ reperes: r, logX: true });
      a.proche(c.versDonnees(100, 500).x, 1, 1e-9);
      a.proche(c.versDonnees(100 + 500 / 3, 500).x, 10, 1e-9);
      a.proche(c.versDonnees(100 + 1000 / 3, 500).x, 100, 1e-9);
      a.proche(c.versDonnees(600, 500).x, 1000, 1e-9);
    });

    test('gère deux axes logarithmiques', function (a) {
      var r = reperesDroits();
      r.x1.valeur = 1; r.x2.valeur = 100;
      r.y1.valeur = 0.01; r.y2.valeur = 1;
      var c = K.creer({ reperes: r, logX: true, logY: true });
      var m = c.versDonnees(350, 300);
      a.proche(m.x, 10, 1e-9);
      a.proche(m.y, 0.1, 1e-9);
      var p = c.versPixels(10, 0.1);
      a.proche(p.px, 350, 1e-8); a.proche(p.py, 300, 1e-8);
    });

    test('reste exacte sur des axes tournés de 30 degrés', function (a) {
      /* Un scan de travers : c'est le cas que le modèle affine doit absorber. */
      var t = Math.PI / 6;
      function R(x, y) {
        return { px: 100 + x * Math.cos(t) - y * Math.sin(t),
                 py: 500 + x * Math.sin(t) + y * Math.cos(t) };
      }
      var o = R(0, 0), fx = R(500, 0), fy = R(0, -400), milieu = R(250, -200);
      var c = K.creer({ reperes: {
        x1: { px: o.px, py: o.py, valeur: 0 },
        x2: { px: fx.px, py: fx.py, valeur: 10 },
        y1: { px: o.px, py: o.py, valeur: 0 },
        y2: { px: fy.px, py: fy.py, valeur: 5 }
      } });
      var m = c.versDonnees(milieu.px, milieu.py);
      a.proche(m.x, 5, 1e-9); a.proche(m.y, 2.5, 1e-9);
    });

    test('absorbe un cisaillement (axes non orthogonaux à l’écran)', function (a) {
      /* Axe Y penché de 20° par rapport à la verticale, axe X horizontal.
         Aucune hypothèse d'orthogonalité n'est faite : x doit rester constant
         le long de l'axe Y, ce que vérifie le second point de contrôle. */
      var c = K.creer({ reperes: {
        x1: { px: 100, py: 500, valeur: 0 },
        x2: { px: 600, py: 500, valeur: 10 },
        y1: { px: 100, py: 500, valeur: 0 },
        y2: { px: 100 + 400 * Math.tan(20 * Math.PI / 180), py: 100, valeur: 5 }
      } });
      a.proche(c.versDonnees(100, 500).x, 0, 1e-9);
      var haut = c.versDonnees(100 + 400 * Math.tan(20 * Math.PI / 180), 100);
      a.proche(haut.x, 0, 1e-9, 'x reste nul le long de l’axe Y incliné');
      a.proche(haut.y, 5, 1e-9);
    });

    test('refuse des repères incomplets ou non numériques', function (a) {
      a.ok(K.verifier(null, false, false).length >= 4);
      var r = reperesDroits();
      r.x2.valeur = NaN;
      a.ok(K.verifier(r, false, false).join(' ').indexOf('valeur non renseignée') !== -1);
    });

    test('refuse des valeurs négatives sur un axe logarithmique', function (a) {
      var r = reperesDroits();
      r.x1.valeur = -1; r.x2.valeur = 10;
      var soucis = K.verifier(r, true, false);
      a.ok(soucis.join(' ').indexOf('doivent être > 0') !== -1);
    });

    test('refuse deux repères de même valeur', function (a) {
      var r = reperesDroits();
      r.x2.valeur = 0;
      a.ok(K.verifier(r, false, false).join(' ').indexOf('deux valeurs différentes') !== -1);
    });

    test('refuse des repères confondus à l’écran', function (a) {
      var r = reperesDroits();
      r.x2.px = 100; r.x2.py = 500;
      a.ok(K.verifier(r, false, false).join(' ').indexOf('confondus') !== -1);
    });

    test('signale des axes quasi parallèles', function (a) {
      var soucis = K.verifier({
        x1: { px: 0, py: 0, valeur: 0 }, x2: { px: 100, py: 0, valeur: 1 },
        y1: { px: 0, py: 0, valeur: 0 }, y2: { px: 100, py: 1, valeur: 1 }
      }, false, false);
      a.ok(soucis.join(' ').indexOf('presque parallèles') !== -1);
    });

    test('creer lève quand les repères sont invalides', function (a) {
      a.leve(function () { K.creer({ reperes: {} }); }, 'non placé');
    });

    test('donne une résolution locale croissante sur un axe log', function (a) {
      var r = reperesDroits();
      r.x1.valeur = 1; r.x2.valeur = 1000;
      var c = K.creer({ reperes: r, logX: true });
      var bas = K.resolutionLocale(c, 110, 300);
      var haut = K.resolutionLocale(c, 590, 300);
      a.ok(haut.x > bas.x * 100, 'un pixel vaut bien plus cher en haut de l’échelle');
    });
  });
})();
