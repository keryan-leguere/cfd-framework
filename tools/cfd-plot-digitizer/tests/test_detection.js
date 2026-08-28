(function () {
  'use strict';
  var T = globalThis.CFDD.Tests, D = globalThis.CFDD.Detection;

  var ROUGE = { r: 200, g: 30, b: 30 };
  var BLEU = { r: 30, g: 60, b: 200 };
  var GRILLE = { r: 220, g: 220, b: 220 };

  /*
   * Une parabole douce, entièrement contenue dans l'image (y de 60 à 310 sur
   * 400 px de haut) : une courbe qui sortirait du cadre fausserait la mesure
   * d'exactitude au lieu de la tester.
   */
  function parabole(x) { return 60 + 250 * Math.pow((x - 200) / 200, 2); }

  function imageAvecCourbe(options) {
    options = options || {};
    var img = T.imageVide(400, 400, { r: 255, g: 255, b: 255 });
    if (options.grille) {
      for (var g = 0; g < 400; g += 40) {
        for (var k = 0; k < 400; k++) {
          T.poser(img, g, k, GRILLE); T.poser(img, k, g, GRILLE);
        }
      }
    }
    T.tracerCourbe(img, parabole, ROUGE, { epaisseur: options.epaisseur || 3 });
    return img;
  }

  T.suite('Détection — extraction par couleur', function (test) {

    test('retrouve la courbe au sous-pixel près', function (a) {
      var img = imageAvecCourbe();
      var res = D.detecter(img, ROUGE, { tolChroma: 30, tolLum: 40, mode: 'moyenne' });

      a.ok(res.points.length > 380, 'presque toutes les colonnes sont trouvées');

      var erreurMax = 0, somme = 0;
      for (var i = 0; i < res.points.length; i++) {
        var attendu = parabole(res.points[i].px);
        var e = Math.abs(res.points[i].py - attendu);
        erreurMax = Math.max(erreurMax, e);
        somme += e;
      }
      var moyenne = somme / res.points.length;
      /* Le centre d'un segment anticrénelé retombe sur l'axe du trait :
         on attend nettement mieux que le demi-pixel. */
      a.ok(moyenne < 0.25, 'erreur moyenne ' + moyenne.toFixed(4) + ' px');
      a.ok(erreurMax < 0.8, 'erreur maximale ' + erreurMax.toFixed(4) + ' px');
    });

    test('reste exacte quand le trait est épais', function (a) {
      var img = imageAvecCourbe({ epaisseur: 9 });
      var res = D.detecter(img, ROUGE, { tolChroma: 30, tolLum: 40, mode: 'moyenne' });
      var erreurMax = 0;
      for (var i = 0; i < res.points.length; i++) {
        erreurMax = Math.max(erreurMax, Math.abs(res.points[i].py - parabole(res.points[i].px)));
      }
      a.ok(erreurMax < 1.0, 'le centre du trait épais reste sur l’axe (' + erreurMax.toFixed(3) + ' px)');
    });

    test('ignore une grille de fond de couleur voisine du blanc', function (a) {
      var img = imageAvecCourbe({ grille: true });
      var res = D.detecter(img, ROUGE, { tolChroma: 30, tolLum: 40, mode: 'moyenne' });
      var erreurMax = 0;
      for (var i = 0; i < res.points.length; i++) {
        erreurMax = Math.max(erreurMax, Math.abs(res.points[i].py - parabole(res.points[i].px)));
      }
      a.ok(erreurMax < 0.8, 'la grille grise ne perturbe pas (' + erreurMax.toFixed(3) + ' px)');
    });

    test('sépare deux courbes de couleurs différentes', function (a) {
      var img = T.imageVide(400, 400, { r: 255, g: 255, b: 255 });
      T.tracerCourbe(img, function (x) { return 100 + 0.1 * x; }, ROUGE, { epaisseur: 3 });
      T.tracerCourbe(img, function (x) { return 300 - 0.1 * x; }, BLEU, { epaisseur: 3 });

      var r = D.detecter(img, ROUGE, { tolChroma: 30, tolLum: 40, mode: 'moyenne' });
      var b = D.detecter(img, BLEU, { tolChroma: 30, tolLum: 40, mode: 'moyenne' });

      for (var i = 0; i < r.points.length; i++) {
        a.proche(r.points[i].py, 100 + 0.1 * r.points[i].px, 0.6, 'courbe rouge');
      }
      for (var j = 0; j < b.points.length; j++) {
        a.proche(b.points[j].py, 300 - 0.1 * b.points[j].px, 0.6, 'courbe bleue');
      }
    });

    test('mode « tous » rend les deux branches d’une courbe repliée', function (a) {
      var img = T.imageVide(400, 400, { r: 255, g: 255, b: 255 });
      /* Deux branches de même couleur : un cercle vu comme y = ±f(x). */
      T.tracerCourbe(img, function (x) { return 200 - Math.sqrt(Math.max(0, 10000 - (x - 200) * (x - 200))); }, ROUGE, { epaisseur: 3, x0: 105, x1: 295 });
      T.tracerCourbe(img, function (x) { return 200 + Math.sqrt(Math.max(0, 10000 - (x - 200) * (x - 200))); }, ROUGE, { epaisseur: 3, x0: 105, x1: 295 });

      var tous = D.detecter(img, ROUGE, { tolChroma: 30, tolLum: 40, mode: 'tous' });
      var moyenne = D.detecter(img, ROUGE, { tolChroma: 30, tolLum: 40, mode: 'moyenne' });

      a.ok(tous.points.length > moyenne.points.length * 1.8, 'deux points par colonne');
      /* En mode moyenne les deux branches se compensent : le résultat tombe
         au centre du cercle. C'est le piège que le mode « tous » évite. */
      var centre = moyenne.points[Math.floor(moyenne.points.length / 2)];
      a.proche(centre.py, 200, 3, 'la moyenne écrase la courbe repliée');
    });

    test('mode « suivi » ne saute pas sur une courbe voisine', function (a) {
      var img = T.imageVide(400, 400, { r: 255, g: 255, b: 255 });
      /* Deux droites de MÊME couleur qui se croisent : le suivi doit rester
         sur celle qu'il a amorcée au lieu de bifurquer au croisement. */
      T.tracerCourbe(img, function (x) { return 50 + 0.7 * x; }, ROUGE, { epaisseur: 3 });
      T.tracerCourbe(img, function (x) { return 330 - 0.7 * x; }, ROUGE, { epaisseur: 3 });

      var res = D.detecter(img, ROUGE, { tolChroma: 30, tolLum: 40, mode: 'suivi', sautMax: 4 });
      a.ok(res.points.length > 300, 'le suivi couvre la largeur');

      /* Les points doivent se répartir sur une seule des deux droites. */
      var surA = 0, surB = 0;
      for (var i = 0; i < res.points.length; i++) {
        var p = res.points[i];
        if (Math.abs(p.py - (50 + 0.7 * p.px)) < 3) { surA++; }
        if (Math.abs(p.py - (330 - 0.7 * p.px)) < 3) { surB++; }
      }
      a.ok(surA + surB > res.points.length * 0.9, 'les points sont sur les droites');
      a.ok(Math.min(surA, surB) < res.points.length * 0.15,
        'le suivi reste sur une branche (A=' + surA + ' B=' + surB + ')');
    });

    test('le balayage en lignes lit une courbe couchée x = f(y)', function (a) {
      /* Une polaire est un arc couché : deux y pour un même x. Balayée en
         colonnes, le mode « moyenne » la réduit à son axe — résultat faux.
         Balayée en lignes, elle redevient une fonction. */
      var img = T.imageVide(400, 400, { r: 255, g: 255, b: 255 });
      function arc(y) { return 60 + 0.004 * (y - 200) * (y - 200); }
      for (var y = 20; y < 380; y++) {
        for (var d = -1; d <= 1; d++) { T.poser(img, Math.round(arc(y)) + d, y, ROUGE); }
      }

      var lignes = D.detecter(img, ROUGE, {
        tolChroma: 30, tolLum: 40, mode: 'moyenne', orientation: 'lignes' });
      a.ok(lignes.points.length > 350, lignes.points.length + ' points');
      var pire = 0;
      for (var i = 0; i < lignes.points.length; i++) {
        pire = Math.max(pire, Math.abs(lignes.points[i].px - arc(lignes.points[i].py)));
      }
      a.ok(pire <= 0.6, 'erreur max ' + pire.toFixed(3) + ' px');

      var colonnes = D.detecter(img, ROUGE, {
        tolChroma: 30, tolLum: 40, mode: 'moyenne', orientation: 'colonnes' });
      var milieu = colonnes.points[Math.floor(colonnes.points.length / 2)];
      a.proche(milieu.py, 200, 5, 'le balayage en colonnes moyenne les deux branches');
    });

    test('respecte la zone d’analyse', function (a) {
      var img = imageAvecCourbe();
      var res = D.detecter(img, ROUGE, {
        tolChroma: 30, tolLum: 40, zone: { x0: 150, y0: 0, x1: 250, y1: 399 }
      });
      for (var i = 0; i < res.points.length; i++) {
        a.ok(res.points[i].px >= 150 && res.points[i].px <= 250, 'point hors zone');
      }
      a.ok(res.points.length <= 101);
    });

    test('ignore les rectangles exclus', function (a) {
      /* Cas de la légende : un motif de la couleur EXACTE de la courbe, qu'aucune
         tolérance ne peut distinguer. Seule l'exclusion géométrique y répond. */
      var img = imageAvecCourbe();
      for (var y = 10; y < 20; y++) {
        for (var x = 320; x < 380; x++) { T.poser(img, x, y, ROUGE); }
      }
      var boite = { x0: 315, y0: 5, x1: 385, y1: 25 };

      var sans = D.detecter(img, ROUGE, { tolChroma: 30, tolLum: 40, mode: 'tous' });
      var avec = D.detecter(img, ROUGE, {
        tolChroma: 30, tolLum: 40, mode: 'tous', zonesExclues: [boite] });

      function dansBoite(res) {
        var n = 0;
        for (var i = 0; i < res.points.length; i++) {
          var p = res.points[i];
          if (p.px >= boite.x0 && p.px <= boite.x1
              && p.py >= boite.y0 && p.py <= boite.y1) { n++; }
        }
        return n;
      }
      a.ok(dansBoite(sans) > 0, 'le motif est bien capté sans exclusion');
      a.egal(dansBoite(avec), 0, 'il disparaît avec exclusion');
      /* La courbe elle-même, hors de la boîte, est intacte. */
      a.ok(avec.points.length > sans.points.length - 80);
    });

    test('borne une zone débordant de l’image', function (a) {
      var img = imageAvecCourbe();
      var z = D.normaliserZone({ x0: -50, y0: 380, x1: 900, y1: -10 }, 400, 400);
      a.egalProfond(z, { x0: 0, x1: 399, y0: 0, y1: 380 },
        'les coins sont réordonnés puis bornés');
    });

    test('le pas de balayage espace les points sans les décaler', function (a) {
      var img = imageAvecCourbe();
      var res = D.detecter(img, ROUGE, { tolChroma: 30, tolLum: 40, pas: 10 });
      a.egal(res.points.length, 40);
      a.egal(res.points[1].px - res.points[0].px, 10);
      a.proche(res.points[5].py, parabole(res.points[5].px), 0.8);
    });

    test('la longueur minimale élimine le bruit isolé', function (a) {
      var img = imageAvecCourbe();
      /* Poussière rouge d'un pixel, loin de la courbe. */
      for (var x = 10; x < 60; x += 7) { T.poser(img, x, 20, ROUGE); }

      var sansFiltre = D.detecter(img, ROUGE, { tolChroma: 30, tolLum: 40, mode: 'tous', longueurMin: 1 });
      var avecFiltre = D.detecter(img, ROUGE, { tolChroma: 30, tolLum: 40, mode: 'tous', longueurMin: 2 });

      function bruit(res) {
        var n = 0;
        for (var i = 0; i < res.points.length; i++) { if (res.points[i].py < 40) { n++; } }
        return n;
      }
      a.ok(bruit(sansFiltre) > 0, 'le bruit est bien présent');
      a.egal(bruit(avecFiltre), 0, 'le filtre de longueur l’élimine');
    });

    test('la longueur maximale écarte les aplats', function (a) {
      var img = imageAvecCourbe();
      /* Bandeau plein rouge : une légende, pas une courbe. */
      for (var y = 0; y < 30; y++) {
        for (var x = 300; x < 360; x++) { T.poser(img, x, y, ROUGE); }
      }
      var res = D.detecter(img, ROUGE, {
        tolChroma: 30, tolLum: 40, mode: 'tous', longueurMax: 12
      });
      var dansBandeau = 0;
      for (var i = 0; i < res.points.length; i++) {
        if (res.points[i].py < 30 && res.points[i].px >= 300) { dansBandeau++; }
      }
      a.egal(dansBandeau, 0, 'le bandeau épais est ignoré');
    });

    test('la simplification réduit les points en gardant la forme', function (a) {
      var img = imageAvecCourbe();
      var brut = D.detecter(img, ROUGE, { tolChroma: 30, tolLum: 40 });
      var lisse = D.detecter(img, ROUGE, { tolChroma: 30, tolLum: 40, simplification: 0.5 });

      a.ok(lisse.points.length < brut.points.length / 3, 'nettement moins de points');
      a.ok(lisse.points.length > 3, 'la courbure impose plusieurs segments');
      a.egal(lisse.statistiques.pointsBruts, brut.points.length);

      /*
       * La forme est préservée : chaque point brut reste à moins d'epsilon du
       * polyligne simplifié. C'est bien la distance PERPENDICULAIRE qu'il faut
       * mesurer — la garantie de Douglas-Peucker porte sur elle. Un écart
       * vertical, lui, vaut la perpendiculaire divisée par le cosinus de la
       * pente, et dépasse donc epsilon sur les portions raides sans que
       * l'algorithme soit en défaut.
       */
      function distanceAuSegment(p, A, B) {
        var vx = B.px - A.px, vy = B.py - A.py;
        var wx = p.px - A.px, wy = p.py - A.py;
        var norme2 = vx * vx + vy * vy;
        var t = (norme2 === 0) ? 0 : Math.max(0, Math.min(1, (wx * vx + wy * vy) / norme2));
        var dx = wx - t * vx, dy = wy - t * vy;
        return Math.sqrt(dx * dx + dy * dy);
      }

      var pire = 0;
      for (var i = 0; i < brut.points.length; i++) {
        var meilleur = Infinity;
        for (var j = 0; j < lisse.points.length - 1; j++) {
          meilleur = Math.min(meilleur,
            distanceAuSegment(brut.points[i], lisse.points[j], lisse.points[j + 1]));
        }
        pire = Math.max(pire, meilleur);
      }
      a.ok(pire <= 0.5 + 1e-9,
        'écart maximal au polyligne simplifié : ' + pire.toFixed(4) + ' px (tolérance 0.5)');
    });

    test('rapporte le type de trait détecté', function (a) {
      var img = imageAvecCourbe();
      var res = D.detecter(img, ROUGE, { tolChroma: 30, tolLum: 40 });
      a.egal(res.statistiques.trait.style, globalThis.CFDD.Trait.STYLES.continu);
      a.egal(res.statistiques.trait.nbComposantes, 1);
    });

    test('sépare deux courbes de MÊME couleur par le type de trait', function (a) {
      /*
       * Le cas des planches en noir et blanc : deux courbes identiques en
       * couleur, distinguées par le seul tracé. Aucune tolérance colorimétrique
       * ne peut les séparer — seule la structure du masque le permet.
       */
      var img = T.imageVide(400, 200, { r: 255, g: 255, b: 255 });
      var pleine = function (x) { return 40 + 0.1 * x; };
      var tirets = function (x) { return 160 - 0.1 * x; };
      for (var x = 0; x < 400; x++) {
        for (var d = -1; d <= 1; d++) {
          T.poser(img, x, Math.round(pleine(x)) + d, ROUGE);
          if (x % 18 < 12) { T.poser(img, x, Math.round(tirets(x)) + d, ROUGE); }
        }
      }

      function repartition(filtre) {
        var res = D.detecter(img, ROUGE, {
          tolChroma: 30, tolLum: 40, mode: 'tous', filtreTrait: filtre });
        var surPleine = 0, surTirets = 0;
        for (var i = 0; i < res.points.length; i++) {
          var p = res.points[i];
          if (Math.abs(p.py - pleine(p.px)) < 3) { surPleine++; }
          if (Math.abs(p.py - tirets(p.px)) < 3) { surTirets++; }
        }
        return { surPleine: surPleine, surTirets: surTirets, res: res };
      }

      var discontinu = repartition('discontinu');
      a.egal(discontinu.surPleine, 0, 'la courbe pleine disparaît entièrement');
      a.ok(discontinu.surTirets > 200, discontinu.surTirets + ' points sur les tirets');

      var continu = repartition('continu');
      a.ok(continu.surPleine > 380, continu.surPleine + ' points sur la pleine');
      /*
       * Quelques points de tirets subsistent au croisement des deux courbes :
       * là elles se touchent et ne forment plus qu'une seule composante, que
       * rien ne permet de rattacher à l'une plutôt qu'à l'autre.
       */
      a.ok(continu.surTirets < 40, continu.surTirets + ' points résiduels au croisement');
    });

    test('comble les lacunes d’un trait en tirets', function (a) {
      var img = T.imageVide(400, 200, { r: 255, g: 255, b: 255 });
      var vraie = function (x) { return 60 + 0.2 * x; };
      for (var x = 0; x < 400; x++) {
        if (x % 18 >= 12) { continue; }
        for (var d = -1; d <= 1; d++) { T.poser(img, x, Math.round(vraie(x)) + d, ROUGE); }
      }

      var sans = D.detecter(img, ROUGE, { tolChroma: 30, tolLum: 40 });
      var avec = D.detecter(img, ROUGE, { tolChroma: 30, tolLum: 40, comblerLacunes: 12 });

      a.ok(avec.points.length > sans.points.length * 1.3,
        sans.points.length + ' points sans comblement, ' + avec.points.length + ' avec');
      a.egal(avec.statistiques.pointsBruts, sans.points.length,
        'les statistiques distinguent bruts et comblés');

      /* Les points ajoutés tombent sur la courbe, pas n’importe où. */
      var pire = 0;
      for (var i = 0; i < avec.points.length; i++) {
        pire = Math.max(pire, Math.abs(avec.points[i].py - vraie(avec.points[i].px)));
      }
      a.ok(pire < 1.5, 'écart maximal après comblement : ' + pire.toFixed(2) + ' px');
    });

    test('le comblement respecte son plafond', function (a) {
      /* Deux tronçons séparés par un large vide : une vraie interruption, que
         l'on ne doit pas relier — sans quoi on inventerait des données. */
      var points = [{ px: 0, py: 10 }, { px: 1, py: 11 }, { px: 80, py: 90 }];
      var serre = D.comblerLacunes(points, 1, 10, 'colonnes');
      a.egal(serre.length, 3, 'le vide de 79 px dépasse le plafond de 10');

      var large = D.comblerLacunes(points, 1, 100, 'colonnes');
      a.ok(large.length > 70, 'avec un plafond suffisant, le vide est comblé');
      a.proche(large[1].px, 1, 1e-9);
    });

    test('le comblement suit l’orientation du balayage', function (a) {
      var points = [{ px: 10, py: 0 }, { px: 20, py: 10 }];
      var enLignes = D.comblerLacunes(points, 1, 20, 'lignes');
      a.egal(enLignes.length, 11, 'interpolation le long de py');
      a.proche(enLignes[5].py, 5, 1e-9);
      a.proche(enLignes[5].px, 15, 1e-9);
    });

    test('ne trouve rien pour une couleur absente', function (a) {
      var img = imageAvecCourbe();
      var res = D.detecter(img, { r: 0, g: 200, b: 0 }, { tolChroma: 15, tolLum: 20 });
      a.egal(res.points.length, 0);
      a.egal(res.statistiques.pixelsRetenus, 0);
    });

    test('remonte des statistiques cohérentes', function (a) {
      var img = imageAvecCourbe();
      var res = D.detecter(img, ROUGE, { tolChroma: 30, tolLum: 40 });
      var s = res.statistiques;
      a.egal(s.pixelsZone, 400 * 400);
      a.ok(s.pixelsRetenus > 0 && s.pixelsRetenus < s.pixelsZone);
      a.egal(s.lignesVues, 400);
      a.egal(s.pointsFinaux, res.points.length);
      a.ok(s.lignesRetenues <= s.lignesVues);
    });

    test('propose les couleurs des courbes présentes', function (a) {
      var img = T.imageVide(400, 400, { r: 255, g: 255, b: 255 });
      T.tracerCourbe(img, function (x) { return 100 + 0.1 * x; }, ROUGE, { epaisseur: 5 });
      T.tracerCourbe(img, function (x) { return 300 - 0.1 * x; }, BLEU, { epaisseur: 5 });

      var palette = globalThis.CFDD.Detection.couleursDominantes(img, { maxCouleurs: 6 });
      a.ok(palette.length >= 2, 'au moins les deux courbes');

      function trouve(cible) {
        for (var i = 0; i < palette.length; i++) {
          var d = globalThis.CFDD.Couleur.deltaE(palette[i].lab,
            globalThis.CFDD.Couleur.rgbVersLab(cible.r, cible.g, cible.b));
          if (d < 25) { return true; }
        }
        return false;
      }
      a.ok(trouve(ROUGE), 'le rouge est proposé');
      a.ok(trouve(BLEU), 'le bleu est proposé');

      /* Le fond blanc, majoritaire, ne doit jamais être proposé. */
      a.ok(!trouve({ r: 255, g: 255, b: 255 }), 'le fond est écarté');
    });

    test('ne propose rien sur une image unie', function (a) {
      var img = T.imageVide(50, 50, { r: 255, g: 255, b: 255 });
      a.egal(globalThis.CFDD.Detection.couleursDominantes(img).length, 0);
    });
  });
})();
