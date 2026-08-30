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

  T.suite('Base — rectangles et gomme en zone', function (test) {

    test('normalise un rectangle tracé à l’envers', function (a) {
      var r = B.normaliserRectangle({ x0: 40, y0: 30, x1: 10, y1: 5 });
      a.egalProfond(r, { x0: 10, y0: 5, x1: 40, y1: 30 });
    });

    test('l’appartenance ignore le sens du tracé', function (a) {
      /* Le rectangle vient d'un glisser à la souris : rien ne garantit qu'il
         ait été tracé du coin haut-gauche vers le bas-droit. */
      var envers = { x0: 40, y0: 30, x1: 10, y1: 5 };
      a.ok(B.dansRectangle({ px: 20, py: 20 }, envers), 'point intérieur');
      a.ok(!B.dansRectangle({ px: 45, py: 20 }, envers), 'point extérieur');
    });

    test('les bords sont inclus', function (a) {
      var r = { x0: 0, y0: 0, x1: 10, y1: 10 };
      a.ok(B.dansRectangle({ px: 0, py: 0 }, r), 'coin haut-gauche');
      a.ok(B.dansRectangle({ px: 10, py: 10 }, r), 'coin bas-droit');
    });

    test('retire les points d’une zone et les compte', function (a) {
      var points = [{ px: 1, py: 1 }, { px: 5, py: 5 }, { px: 9, py: 9 },
                    { px: 20, py: 20 }];
      var res = B.retirerDansRectangle(points, { x0: 4, y0: 4, x1: 10, y1: 10 });
      a.egal(res.retires, 2, 'points retirés');
      a.egal(res.points.length, 2, 'points conservés');
      a.egal(res.points[0].px, 1, 'premier conservé');
      a.egal(res.points[1].px, 20, 'dernier conservé');
    });

    test('l’ordre des points survivants est conservé', function (a) {
      /* L'export doit rester monotone : réordonner la série en gommant
         produirait un tracé en zigzag à la relecture. */
      var points = [];
      for (var i = 0; i < 20; i++) { points.push({ px: i, py: 0 }); }
      var res = B.retirerDansRectangle(points, { x0: 5, y0: -1, x1: 8, y1: 1 });
      for (var k = 1; k < res.points.length; k++) {
        a.ok(res.points[k].px > res.points[k - 1].px, 'ordre croissant en x');
      }
    });

    test('une zone vide ne retire rien et ne recopie pas moins', function (a) {
      var points = [{ px: 1, py: 1 }, { px: 2, py: 2 }];
      var res = B.retirerDansRectangle(points, { x0: 50, y0: 50, x1: 60, y1: 60 });
      a.egal(res.retires, 0);
      a.egal(res.points.length, 2);
    });
  });
})();
