(function () {
  'use strict';
  var T = globalThis.CFDD.Tests, Tr = globalThis.CFDD.Trait, D = globalThis.CFDD.Detection;

  var NOIR = { r: 20, g: 20, b: 20 };

  /*
   * Trace y = f(x) avec un motif [marque, espace] le long de x ; motif null
   * donne un trait plein. Épaisseur 3 px, sans anticrénelage : on teste ici la
   * structure du masque, pas la colorimétrie.
   */
  function tracer(image, f, motif, rgb) {
    for (var x = 0; x < image.width; x++) {
      if (motif) {
        var phase = x % (motif[0] + motif[1]);
        if (phase >= motif[0]) { continue; }
      }
      for (var d = -1; d <= 1; d++) { T.poser(image, x, Math.round(f(x)) + d, rgb || NOIR); }
    }
  }

  function masqueDe(image, cible) {
    return D.construireMasque(image, cible || NOIR, { tolChroma: 30, tolLum: 40 });
  }

  T.suite('Trait — nature du tracé', function (test) {

    test('étiquette une droite pleine en une seule composante', function (a) {
      var img = T.imageVide(300, 150, { r: 255, g: 255, b: 255 });
      tracer(img, function (x) { return 40 + 0.2 * x; }, null);
      var c = Tr.composantes(masqueDe(img));
      a.egal(c.liste.length, 1);
      a.egal(c.liste[0].x0, 0);
      a.egal(c.liste[0].x1, 299);
    });

    test('la 8-connexité ne fragmente pas une oblique fine', function (a) {
      /* Un trait d'un pixel en escalier : les pixels ne se touchent que par les
         coins. En 4-connexité il deviendrait 150 composantes, donc du
         « pointillé » — c'est le piège que la 8-connexité évite. */
      var img = T.imageVide(200, 200, { r: 255, g: 255, b: 255 });
      for (var x = 0; x < 150; x++) { T.poser(img, x, 20 + x, NOIR); }
      var c = Tr.composantes(masqueDe(img));
      a.egal(c.liste.length, 1);
      a.egal(c.liste[0].taille, 150);
    });

    test('sépare des composantes disjointes et borne chacune', function (a) {
      var img = T.imageVide(100, 100, { r: 255, g: 255, b: 255 });
      T.poser(img, 10, 10, NOIR);
      T.poser(img, 50, 60, NOIR);
      T.poser(img, 51, 60, NOIR);
      var c = Tr.composantes(masqueDe(img));
      a.egal(c.liste.length, 2);
      var tailles = c.liste.map(function (k) { return k.taille; }).sort();
      a.egalProfond(tailles, [1, 2]);
    });

    test('reconnaît un trait continu', function (a) {
      var img = T.imageVide(300, 150, { r: 255, g: 255, b: 255 });
      tracer(img, function (x) { return 40 + 0.2 * x; }, null);
      var m = Tr.mesurer(Tr.composantes(masqueDe(img)), 'colonnes');
      a.egal(m.style, Tr.STYLES.continu);
      a.egal(m.nbComposantes, 1);
      a.proche(m.couverture, 1, 1e-9);
    });

    test('reconnaît des tirets et mesure marque et espace', function (a) {
      var img = T.imageVide(400, 150, { r: 255, g: 255, b: 255 });
      tracer(img, function (x) { return 40 + 0.2 * x; }, [12, 6]);
      var m = Tr.mesurer(Tr.composantes(masqueDe(img)), 'colonnes');
      a.egal(m.style, Tr.STYLES.tirets);
      a.proche(m.marque, 12, 1, 'longueur de marque');
      a.proche(m.espace, 6, 1, 'longueur d’espace');
      a.ok(m.nbComposantes > 15, m.nbComposantes + ' composantes');
    });

    test('reconnaît un pointillé', function (a) {
      var img = T.imageVide(400, 150, { r: 255, g: 255, b: 255 });
      tracer(img, function (x) { return 40 + 0.2 * x; }, [2, 4]);
      var m = Tr.mesurer(Tr.composantes(masqueDe(img)), 'colonnes');
      a.egal(m.style, Tr.STYLES.pointille);
      a.ok(m.marque <= 3, 'marques courtes : ' + m.marque);
    });

    test('reconnaît un tiret-point à l’alternance des longueurs', function (a) {
      var img = T.imageVide(400, 150, { r: 255, g: 255, b: 255 });
      /* Motif 14-5-2-5 : marques longues et courtes en alternance. */
      for (var x = 0; x < 400; x++) {
        var phase = x % 26;
        var peint = (phase < 14) || (phase >= 19 && phase < 21);
        if (!peint) { continue; }
        for (var d = -1; d <= 1; d++) { T.poser(img, x, Math.round(40 + 0.2 * x) + d, NOIR); }
      }
      var m = Tr.mesurer(Tr.composantes(masqueDe(img)), 'colonnes');
      a.egal(m.style, Tr.STYLES.tiretPoint);
    });

    test('rend « inconnu » sur un masque vide', function (a) {
      var img = T.imageVide(50, 50, { r: 255, g: 255, b: 255 });
      var m = Tr.mesurer(Tr.composantes(masqueDe(img)), 'colonnes');
      a.egal(m.style, Tr.STYLES.inconnu);
      a.egal(m.nbComposantes, 0);
    });

    test('mesure le long de l’axe de balayage demandé', function (a) {
      /* Tirets VERTICAUX : continus vus en colonnes (chaque colonne touchée est
         pleine), discontinus vus en lignes. L'orientation change la réponse. */
      var img = T.imageVide(150, 400, { r: 255, g: 255, b: 255 });
      for (var y = 0; y < 400; y++) {
        if (y % 18 >= 12) { continue; }
        for (var d = -1; d <= 1; d++) { T.poser(img, 75 + d, y, NOIR); }
      }
      var comp = Tr.composantes(masqueDe(img));
      a.egal(Tr.mesurer(comp, 'lignes').style, Tr.STYLES.tirets);
      a.proche(Tr.mesurer(comp, 'lignes').marque, 12, 1);
    });

    test('le filtre « continu » isole la courbe pleine', function (a) {
      var img = T.imageVide(400, 200, { r: 255, g: 255, b: 255 });
      tracer(img, function (x) { return 40 + 0.1 * x; }, null);
      tracer(img, function (x) { return 160 - 0.1 * x; }, [12, 6]);

      var info = masqueDe(img);
      var comp = Tr.composantes(info);
      var filtre = Tr.filtrer(info, comp, Tr.FILTRES.continu, 'colonnes');

      a.ok(filtre.nbRetenus < info.nbRetenus, 'des pixels ont été écartés');
      a.egal(Tr.mesurer(Tr.composantes(filtre), 'colonnes').style, Tr.STYLES.continu);
    });

    test('le filtre « discontinu » isole la courbe en tirets', function (a) {
      var img = T.imageVide(400, 200, { r: 255, g: 255, b: 255 });
      var pleine = function (x) { return 40 + 0.1 * x; };
      var pointilles = function (x) { return 160 - 0.1 * x; };
      tracer(img, pleine, null);
      tracer(img, pointilles, [12, 6]);

      var info = masqueDe(img);
      var filtre = Tr.filtrer(info, Tr.composantes(info), Tr.FILTRES.discontinu, 'colonnes');

      /* Plus aucun pixel ne doit rester sur la courbe pleine. */
      var surPleine = 0, surTirets = 0;
      for (var y = 0; y < filtre.hauteurZone; y++) {
        for (var x = 0; x < filtre.largeurZone; x++) {
          if (!filtre.masque[y * filtre.largeurZone + x]) { continue; }
          if (Math.abs(y - pleine(x)) <= 2) { surPleine++; }
          if (Math.abs(y - pointilles(x)) <= 2) { surTirets++; }
        }
      }
      a.egal(surPleine, 0, 'la courbe pleine est entièrement écartée');
      a.ok(surTirets > 500, surTirets + ' pixels conservés sur les tirets');
    });

    test('distingue les tirets du pointillé sur la même figure', function (a) {
      /*
       * Trois courbes de la même couleur, trois tracés. Le seuil séparant un
       * point d'un tiret se cale sur l'ÉPAISSEUR mesurée du trait, jamais sur
       * une valeur en pixels : il suit donc la résolution de l'image.
       */
      /* Largeur 396 : les périodes 18 (tirets) et 6 (points) la pavent
         exactement, sans marque tronquée au bord qui passerait pour un point. */
      var img = T.imageVide(396, 240, { r: 255, g: 255, b: 255 });
      var pleine = function (x) { return 40 + 0.1 * x; };
      var tirets = function (x) { return 120; };
      var points = function (x) { return 200; };
      tracer(img, pleine, null);
      tracer(img, tirets, [12, 6]);
      tracer(img, points, [2, 4]);

      var info = masqueDe(img);
      var comp = Tr.composantes(info);

      function bandes(filtre) {
        var f = Tr.filtrer(info, comp, filtre, 'colonnes');
        var compte = { pleine: 0, tirets: 0, points: 0 };
        for (var y = 0; y < f.hauteurZone; y++) {
          for (var x = 0; x < f.largeurZone; x++) {
            if (!f.masque[y * f.largeurZone + x]) { continue; }
            if (Math.abs(y - pleine(x)) <= 2) { compte.pleine++; }
            else if (Math.abs(y - tirets(x)) <= 2) { compte.tirets++; }
            else if (Math.abs(y - points(x)) <= 2) { compte.points++; }
          }
        }
        return compte;
      }

      var t = bandes(Tr.FILTRES.tirets);
      a.egal(t.pleine, 0, 'les tirets excluent la courbe pleine');
      a.egal(t.points, 0, 'les tirets excluent le pointillé');
      a.ok(t.tirets > 400, t.tirets + ' pixels de tirets retenus');

      var p = bandes(Tr.FILTRES.pointille);
      a.egal(p.pleine, 0, 'le pointillé exclut la courbe pleine');
      a.egal(p.tirets, 0, 'le pointillé exclut les tirets');
      a.ok(p.points > 100, p.points + ' pixels de pointillé retenus');

      var c = bandes(Tr.FILTRES.continu);
      a.ok(c.pleine > 800, 'le filtre continu garde la courbe pleine');
      a.egal(c.tirets + c.points, 0, 'et rien d’autre');
    });

    test('le seuil point/tiret suit l’épaisseur du trait', function (a) {
      /*
       * Même motif tracé deux fois plus épais et deux fois plus grand : la
       * classification ne doit pas basculer. Un seuil en pixels absolus, lui,
       * prendrait ces gros points pour des tirets.
       */
      function figure(echelle) {
        var img = T.imageVide(400, 200, { r: 255, g: 255, b: 255 });
        for (var x = 0; x < 400; x++) {
          if (x % (5 * echelle) >= 2 * echelle) { continue; }
          for (var d = -echelle; d <= echelle; d++) { T.poser(img, x, 100 + d, NOIR); }
        }
        var info = masqueDe(img);
        return Tr.filtrer(info, Tr.composantes(info), Tr.FILTRES.pointille, 'colonnes');
      }
      a.ok(figure(1).nbRetenus > 0, 'points fins reconnus');
      a.ok(figure(3).nbRetenus > 0, 'points épais reconnus aussi');
    });

    test('le filtre « tous » rend le masque inchangé', function (a) {
      var img = T.imageVide(200, 100, { r: 255, g: 255, b: 255 });
      tracer(img, function (x) { return 50; }, [10, 5]);
      var info = masqueDe(img);
      var meme = Tr.filtrer(info, Tr.composantes(info), Tr.FILTRES.tous, 'colonnes');
      a.egal(meme, info, 'le même objet est renvoyé, sans copie inutile');
    });
  });
})();
