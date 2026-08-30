(function () {
  'use strict';
  var T = globalThis.CFDD.Tests, P = globalThis.CFDD.Projet, K = globalThis.CFDD.Calibration;

  function etat() {
    return {
      image: { nom: 'polaire.png', dataURL: 'data:image/png;base64,AAAA', largeur: 800, hauteur: 600 },
      calibration: {
        reperes: {
          x1: { px: 100, py: 500, valeur: 0 }, x2: { px: 600, py: 500, valeur: 10 },
          y1: { px: 100, py: 500, valeur: 0 }, y2: { px: 100, py: 100, valeur: 5 }
        }, logX: false, logY: true
      },
      zone: { x0: 100, y0: 100, x1: 600, y1: 500 },
      series: [{ nom: 'Série A', couleurHex: '#cc0000',
                 points: [{ px: 1.23456, py: 9.87654 }, { px: 2, py: 3 }] }],
      notes: 'extrait de la figure 4'
    };
  }

  T.suite('Projet — sauvegarde et relecture', function (test) {

    test('fait l’aller-retour sans perte notable', function (a) {
      var r = P.deserialiser(P.serialiser(etat()));
      a.egal(r.image.nom, 'polaire.png');
      a.egal(r.image.largeur, 800);
      a.egal(r.calibration.logY, true);
      a.egal(r.calibration.logX, false);
      a.egalProfond(r.zone, { x0: 100, y0: 100, x1: 600, y1: 500 });
      a.egal(r.notes, 'extrait de la figure 4');
      a.egal(r.series.length, 1);
      a.egal(r.series[0].nom, 'Série A');
      a.egal(r.series[0].couleurHex, '#cc0000');
      /* Arrondi assumé au centième de pixel. */
      a.egalProfond(r.series[0].points[0], { px: 1.23, py: 9.88 });
    });

    test('peut omettre l’image pour un fichier léger', function (a) {
      var sansImage = P.deserialiser(P.serialiser(etat(), { inclureImage: false }));
      a.egal(sansImage.image.dataURL, null);
      a.egal(sansImage.image.largeur, 800, 'les dimensions restent');
    });

    test('rejette un fichier étranger', function (a) {
      a.leve(function () { P.deserialiser('{"format":"autre chose"}'); }, 'pas un projet');
    });

    test('rejette un JSON invalide', function (a) {
      a.leve(function () { P.deserialiser('ceci n’est pas du json'); }, 'illisible');
    });

    test('rejette une version de format future', function (a) {
      a.leve(function () {
        P.deserialiser(JSON.stringify({ format: P.FORMAT, versionFormat: 99 }));
      }, 'trop récent');
    });

    test('accepte un projet minimal sans image ni séries', function (a) {
      var r = P.deserialiser(JSON.stringify({ format: P.FORMAT, versionFormat: 1 }));
      a.egal(r.image, null);
      a.egal(r.calibration, null);
      a.egalProfond(r.series, []);
    });

    test('accepte les deux écritures de points et écarte les invalides', function (a) {
      var r = P.deserialiser(JSON.stringify({
        format: P.FORMAT, versionFormat: 1,
        series: [{ nom: 'S', points: [[1, 2], { px: 3, py: 4 }, [null, 5], ['a', 'b']] }]
      }));
      a.egalProfond(r.series[0].points, [{ px: 1, py: 2 }, { px: 3, py: 4 }]);
    });

    test('nomme les séries anonymes', function (a) {
      var r = P.deserialiser(JSON.stringify({
        format: P.FORMAT, versionFormat: 1, series: [{ points: [] }, { points: [] }]
      }));
      a.egal(r.series[0].nom, 'Série 1');
      a.egal(r.series[1].nom, 'Série 2');
    });

    test('convertit les séries pixel en unités physiques', function (a) {
      var e = etat();
      e.calibration.logY = false;
      var cal = K.creer(e.calibration);
      var series = P.seriesEnDonnees(
        [{ nom: 'S', points: [{ px: 350, py: 300 }, { px: 600, py: 500 }] }], cal);
      a.proche(series[0].points[0].x, 5, 1e-9);
      a.proche(series[0].points[0].y, 2.5, 1e-9);
      a.proche(series[0].points[1].x, 10, 1e-9);
      a.proche(series[0].points[1].y, 0, 1e-9);
    });

    test('recalibrer suffit à corriger toutes les séries', function (a) {
      /* Le point clé du stockage en pixels : une erreur de saisie sur un repère
         se corrige sans repointer la moindre courbe. */
      var e = etat();
      e.calibration.logY = false;
      var faux = K.creer(e.calibration);
      e.calibration.reperes.x2.valeur = 100;      /* 10 lu au lieu de 100 */
      var juste = K.creer(e.calibration);

      var pts = [{ px: 350, py: 300 }];
      a.proche(P.seriesEnDonnees([{ nom: 'S', points: pts }], faux)[0].points[0].x, 5, 1e-9);
      a.proche(P.seriesEnDonnees([{ nom: 'S', points: pts }], juste)[0].points[0].x, 50, 1e-9);
    });
  });

  T.suite('Projet — marqueur de série', function (test) {

    test('la forme et la taille survivent à l’aller-retour', function (a) {
      var texte = P.serialiser({
        series: [{ nom: 'A', couleurHex: '#123456',
                   marqueur: { forme: 'losange', taille: 4 },
                   points: [{ px: 1, py: 2 }] }]
      });
      var relu = P.deserialiser(texte);
      a.egal(relu.series[0].marqueur.forme, 'losange');
      a.egal(relu.series[0].marqueur.taille, 4);
    });

    test('un projet antérieur au marqueur se relit sans marqueur', function (a) {
      /* Les fichiers déjà enregistrés doivent rester lisibles : l'interface
         attribuera une forme par défaut, pas un plantage. */
      var texte = P.serialiser({
        series: [{ nom: 'A', couleurHex: '#123456', points: [{ px: 1, py: 2 }] }]
      });
      var brut = JSON.parse(texte);
      delete brut.series[0].marqueur;
      var relu = P.deserialiser(JSON.stringify(brut));
      a.egal(relu.series[0].marqueur, null);
      a.egal(relu.series[0].points.length, 1, 'les points sont intacts');
    });
  });
})();
