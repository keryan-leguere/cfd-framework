(function () {
  'use strict';
  var T = globalThis.CFDD.Tests, B = globalThis.CFDD.Base;

  T.suite('Base — algèbre et utilitaires', function (test) {

    test('résout un système 2x2 régulier', function (a) {
      var x = B.resoudre([[2, 1], [1, 3]], [5, 10]);
      a.proche(x[0], 1, 1e-12); a.proche(x[1], 3, 1e-12);
    });

    test('résout un système 3x3 nécessitant un pivot', function (a) {
      /* Première ligne à pivot nul : sans échange, division par zéro. */
      var x = B.resoudre([[0, 2, 1], [1, 1, 1], [2, 1, 3]], [5, 6, 11]);
      a.proche(x[0], 3, 1e-10); a.proche(x[1], 2, 1e-10); a.proche(x[2], 1, 1e-10);
    });

    test('renvoie null sur une matrice singulière', function (a) {
      a.egal(B.resoudre([[1, 2], [2, 4]], [1, 2]), null);
    });

    test('ne modifie pas les matrices fournies', function (a) {
      var A = [[2, 1], [1, 3]], b = [5, 10];
      B.resoudre(A, b);
      a.egalProfond(A, [[2, 1], [1, 3]]);
      a.egalProfond(b, [5, 10]);
    });

    test('formate sans exponentielle dans la plage lisible', function (a) {
      a.egal(B.formaterNombre(1234.56789, 6), '1234.57');
      a.egal(B.formaterNombre(0, 4), '0');
      a.egal(B.formaterNombre(-0.001234, 3), '-0.00123');
    });

    test('bascule en exponentielle hors plage', function (a) {
      a.egal(B.formaterNombre(1e-9, 3), '1.00e-9');
      a.egal(B.formaterNombre(1.5e12, 3), '1.50e+12');
    });

    test('formate les non-nombres en chaîne vide', function (a) {
      a.egal(B.formaterNombre(NaN, 3), '');
      a.egal(B.formaterNombre(Infinity, 3), '');
      a.egal(B.formaterNombre(null, 3), '');
    });

    test('Douglas-Peucker garde les extrémités et les coudes', function (a) {
      var pts = [{ x: 0, y: 0 }, { x: 1, y: 0.01 }, { x: 2, y: 0 },
                 { x: 3, y: 5 }, { x: 4, y: 10 }];
      var s = B.simplifier(pts, 0.1);
      a.egal(s.length, 3, 'les points alignés disparaissent');
      a.egal(s[0].x, 0); a.egal(s[s.length - 1].x, 4);
    });

    test('Douglas-Peucker conserve tout à tolérance nulle', function (a) {
      var pts = [{ x: 0, y: 0 }, { x: 1, y: 0.01 }, { x: 2, y: 0 }];
      a.egal(B.simplifier(pts, 0).length, 3);
    });

    test('Douglas-Peucker tient sur un très grand nombre de points', function (a) {
      /*
       * Vérifie l'absence de récursion : des dents de scie forcent la
       * subdivision jusqu'au dernier point et feraient exploser la pile d'une
       * implémentation récursive. C'est aussi le pire cas en temps (aucun point
       * n'est éliminable, d'où le coût quadratique) — d'où une taille modeste :
       * une détection réelle produit au plus une colonne de pixels de points.
       */
      var pts = [];
      for (var i = 0; i < 20000; i++) { pts.push({ x: i, y: (i % 2) * 10 }); }
      var s = B.simplifier(pts, 0.5);
      a.egal(s.length, 20000, 'aucune dent n’est éliminable');
    });
  });
})();
