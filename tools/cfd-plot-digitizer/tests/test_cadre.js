/*
 * test_cadre.js — détection automatique du cadre du tracé.
 *
 * Les figures de test sont construites ici plutôt que lues sur disque : on
 * maîtrise ainsi la position EXACTE des axes, donc l'erreur attendue, et la
 * suite tourne aussi dans le navigateur.
 */
(function (racine) {
  'use strict';
  var CFDD = racine.CFDD;
  var Tests = CFDD.Tests;
  var Cadre = CFDD.Cadre;

  var NOIR = { r: 20, g: 20, b: 20 };
  var ROUGE = { r: 193, g: 18, b: 31 };
  var GRIS = { r: 140, g: 140, b: 140 };

  function ligneH(image, y, x0, x1, rgb) {
    for (var x = x0; x <= x1; x++) { Tests.poser(image, x, y, rgb || NOIR); }
  }
  function ligneV(image, x, y0, y1, rgb) {
    for (var y = y0; y <= y1; y++) { Tests.poser(image, x, y, rgb || NOIR); }
  }

  /* Planche encadrée : les quatre côtés sont tracés, comme une figure
     matplotlib par défaut. */
  function plancheEncadree() {
    var image = Tests.imageVide(200, 150);
    ligneV(image, 30, 20, 120);
    ligneV(image, 180, 20, 120);
    ligneH(image, 20, 30, 180);
    ligneH(image, 120, 30, 180);
    /* Une courbe à l'intérieur, et des « étiquettes » sous l'axe : ce sont
       elles qui débordent du cadre et piègent une boîte englobante. */
    Tests.tracerCourbe(image, function (x) { return 100 - (x - 30) * 0.4; },
      ROUGE, { x0: 32, x1: 178, epaisseur: 2 });
    ligneH(image, 132, 34, 46, GRIS);
    ligneH(image, 134, 34, 46, GRIS);
    ligneH(image, 132, 170, 186, GRIS);
    return image;
  }

  /* Planche à deux axes seulement (gauche et bas) : le bord droit et le bord
     haut ne se lisent que sur l'étendue des traits trouvés. */
  function plancheDeuxAxes() {
    var image = Tests.imageVide(200, 150);
    ligneV(image, 30, 20, 120);
    ligneH(image, 120, 30, 180);
    Tests.tracerCourbe(image, function (x) { return 100 - (x - 30) * 0.4; },
      ROUGE, { x0: 32, x1: 178, epaisseur: 2 });
    ligneH(image, 134, 34, 46, GRIS);
    return image;
  }

  Tests.suite('Cadre — couleur de fond', function (test) {

    test('reconnaît le blanc du papier', function (A) {
      var fond = Cadre.couleurFond(plancheEncadree());
      A.egal(fond.r, 255, 'rouge du fond');
      A.egal(fond.g, 255, 'vert du fond');
      A.egal(fond.b, 255, 'bleu du fond');
    });

    test('reconnaît un fond non blanc', function (A) {
      var image = Tests.imageVide(80, 60, { r: 240, g: 236, b: 220 });
      ligneV(image, 20, 5, 55);
      var fond = Cadre.couleurFond(image);
      A.egal(fond.r, 240, 'rouge');
      A.egal(fond.b, 220, 'bleu');
    });
  });

  Tests.suite('Cadre — regroupement des pics', function (test) {

    test('deux indices voisins ne font qu’un seul trait', function (A) {
      /* Un axe tracé à 1,5 px couvre deux colonnes : les compter séparément
         donnerait deux bords là où il n'y en a qu'un. */
      var traits = Cadre.traits([0, 0, 9, 9, 0, 0, 0, 8, 0], 5);
      A.egal(traits.length, 2, 'nombre de traits');
      A.proche(traits[0].centre, 2.5, 1e-9, 'centre du trait large');
      A.egal(traits[1].centre, 7, 'centre du trait fin');
    });

    test('un profil sous le seuil ne donne aucun trait', function (A) {
      A.egal(Cadre.traits([1, 2, 3, 2, 1], 5).length, 0);
    });
  });

  Tests.suite('Cadre — détection', function (test) {

    test('retrouve les quatre bords d’une planche encadrée', function (A) {
      var res = Cadre.detecter(plancheEncadree());
      A.ok(res, 'un cadre est trouvé');
      A.egal(res.cadre.x0, 30, 'bord gauche');
      A.egal(res.cadre.x1, 180, 'bord droit');
      A.egal(res.cadre.y0, 20, 'bord haut');
      A.egal(res.cadre.y1, 120, 'bord bas');
      A.egal(res.confiance, 1, 'les quatre côtés sont de vrais traits');
    });

    test('les étiquettes hors cadre ne déplacent pas les bords', function (A) {
      /* La boîte englobante de l'encre descend à y = 134 à cause des
         graduations ; le cadre, lui, s'arrête à 120. C'est toute la raison
         d'être de la méthode par profils. */
      var res = Cadre.detecter(plancheEncadree());
      A.egal(res.cadre.y1, 120, 'bord bas malgré les étiquettes');
    });

    test('une planche à deux axes se referme sur l’étendue des traits', function (A) {
      var res = Cadre.detecter(plancheDeuxAxes());
      A.ok(res, 'un cadre est trouvé');
      A.egal(res.cadre.x0, 30, 'bord gauche (trait)');
      A.egal(res.cadre.y1, 120, 'bord bas (trait)');
      A.egal(res.cadre.x1, 180, 'bord droit déduit de l’étendue de l’axe bas');
      A.egal(res.cadre.y0, 20, 'bord haut déduit de l’étendue de l’axe gauche');
      A.egal(res.sources.droite, 'etendue', 'origine du bord droit');
      A.ok(res.confiance < 1, 'confiance moindre qu’un cadre fermé');
    });

    test('une image vierge ne produit pas de cadre', function (A) {
      A.egal(Cadre.detecter(Tests.imageVide(60, 40)), null);
    });

    test('un nuage de points nu ne se voit pas promu en cadre', function (A) {
      /*
       * Sans la condition de couverture, la colonne la plus dense d'un nuage
       * suffirait à passer pour un axe : le cadre serait alors tracé sur une
       * ligne de points, sans que rien ne le signale.
       */
      var image = Tests.imageVide(200, 150);
      for (var k = 0; k < 60; k++) {
        var x = 30 + (k * 37) % 140;
        var y = 20 + (k * 53) % 100;
        Tests.poser(image, x, y, ROUGE);
        Tests.poser(image, x + 1, y, ROUGE);
      }
      var res = Cadre.detecter(image);
      A.ok(res, 'un cadre de repli est tout de même proposé');
      A.egal(res.confiance, 0, 'mais annoncé sans confiance');
      A.egal(res.sources.gauche, 'boite', 'issu de la boîte englobante');
    });

    test('la zone d’analyse restreint la recherche', function (A) {
      var image = plancheEncadree();
      var res = Cadre.detecter(image, { zone: { x0: 25, y0: 15, x1: 190, y1: 125 } });
      A.egal(res.cadre.x0, 30, 'bord gauche inchangé');
      A.egal(res.cadre.y1, 120, 'bord bas inchangé');
    });
  });

  Tests.suite('Cadre — repères déduits', function (test) {

    test('X1 et Y1 tombent sur le même coin', function (A) {
      var r = Cadre.reperes({ x0: 30, y0: 20, x1: 180, y1: 120 });
      A.egal(r.x1.px, 30, 'X1 en x'); A.egal(r.x1.py, 120, 'X1 en y');
      A.egal(r.y1.px, 30, 'Y1 en x'); A.egal(r.y1.py, 120, 'Y1 en y');
      A.egal(r.x2.px, 180, 'X2 à droite');
      A.egal(r.y2.py, 20, 'Y2 en haut');
    });

    test('les repères déduits recalibrent l’image d’origine', function (A) {
      /*
       * Le test qui compte vraiment : un cadre détecté puis converti en
       * repères doit rendre une calibration exacte. Une détection juste au
       * pixel près mais mal orientée passerait tous les tests précédents.
       */
      var res = Cadre.detecter(plancheEncadree());
      var r = Cadre.reperes(res.cadre);
      var cal = CFDD.Calibration.creer({
        reperes: {
          x1: { px: r.x1.px, py: r.x1.py, valeur: 0 },
          x2: { px: r.x2.px, py: r.x2.py, valeur: 10 },
          y1: { px: r.y1.px, py: r.y1.py, valeur: 0 },
          y2: { px: r.y2.px, py: r.y2.py, valeur: 5 }
        }, logX: false, logY: false
      });
      var coin = cal.versDonnees(180, 20);
      A.proche(coin.x, 10, 1e-9, 'x du coin haut-droit');
      A.proche(coin.y, 5, 1e-9, 'y du coin haut-droit');
      var milieu = cal.versDonnees(105, 70);
      A.proche(milieu.x, 5, 1e-9, 'x du centre');
      A.proche(milieu.y, 2.5, 1e-9, 'y du centre');
    });
  });

})(typeof globalThis !== 'undefined' ? globalThis : this);
