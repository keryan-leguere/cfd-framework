/*
 * test_vignettes.js — illustrations SVG des réglages.
 *
 * Un dessin ne se teste pas au pixel près, mais trois choses le sont : que
 * chaque option de l'interface ait bien sa vignette (une manquante laisserait
 * un trou silencieux dans le panneau), que le SVG produit soit clos et sans
 * balise capable de casser le fichier autonome, et qu'une clé inconnue rende
 * null plutôt que de lever.
 */
(function (racine) {
  'use strict';
  var CFDD = racine.CFDD;
  var Tests = CFDD.Tests;
  var Vignettes = CFDD.Vignettes;

  /* Miroir des options offertes par index.html : si l'une est ajoutée là-bas
     sans dessin ici, ce test le dit. */
  var ATTENDUES = [
    'orientation:colonnes', 'orientation:lignes',
    'mode:moyenne', 'mode:tous', 'mode:suivi',
    'filtreTrait:tous', 'filtreTrait:continu', 'filtreTrait:tirets',
    'filtreTrait:pointillé', 'filtreTrait:discontinu',
    'apercuMode:surbrillance', 'apercuMode:isoler', 'apercuMode:les-deux'
  ];

  Tests.suite('Vignettes', function (test) {

    test('chaque option illustrée a son dessin', function (A) {
      ATTENDUES.forEach(function (cle) {
        A.ok(Vignettes.existe(cle), 'vignette manquante : ' + cle);
      });
    });

    test('chaque fiche numérique a son dessin', function (A) {
      A.ok(Vignettes.NUMERIQUES.length >= 5, 'au moins cinq fiches');
      Vignettes.NUMERIQUES.forEach(function (fiche) {
        A.ok(Vignettes.existe(fiche.cle), 'vignette manquante : ' + fiche.cle);
        A.ok(fiche.titre && fiche.texte, 'fiche ' + fiche.cle + ' sans texte');
      });
    });

    test('le SVG rendu est clos et dimensionné', function (A) {
      Vignettes.cles().forEach(function (cle) {
        var svg = Vignettes.svg(cle);
        A.ok(svg.indexOf('<svg ') === 0, cle + ' : ne commence pas par <svg');
        A.ok(svg.slice(-6) === '</svg>', cle + ' : non refermé');
        A.ok(svg.indexOf('viewBox="0 0 72 48"') !== -1, cle + ' : sans viewBox');
      });
    });

    test('aucune vignette ne casserait le fichier autonome', function (A) {
      /*
       * Le fichier d'un seul tenant incorpore ces chaînes dans un <script> :
       * un « </script » ou un « </style » à l'intérieur refermerait la balise
       * pour l'analyseur HTML et transformerait la suite du fichier en texte.
       */
      Vignettes.cles().forEach(function (cle) {
        var svg = Vignettes.svg(cle).toLowerCase();
        A.egal(svg.indexOf('</script'), -1, cle + ' contient </script');
        A.egal(svg.indexOf('</style'), -1, cle + ' contient </style');
      });
    });

    test('le titre est échappé', function (A) {
      var svg = Vignettes.svg('mode:suivi', 'a<b & "c"');
      A.ok(svg.indexOf('a&lt;b &amp; &quot;c&quot;') !== -1, 'titre échappé');
      A.egal(svg.indexOf('a<b'), -1, 'aucun chevron brut');
    });

    test('une clé inconnue rend null sans lever', function (A) {
      A.egal(Vignettes.svg('mode:inexistant'), null);
      A.egal(Vignettes.existe('mode:inexistant'), false);
    });
  });

})(typeof globalThis !== 'undefined' ? globalThis : this);
