(function () {
  'use strict';
  var CFDD = globalThis.CFDD;
  var T = CFDD.Tests;

  /*
   * Cette suite exerce la chaîne complète sur de VRAIES figures matplotlib
   * (exemples/), avec les valeurs qui ont servi à les tracer comme référence.
   * Elle mesure donc l'erreur de digitalisation de bout en bout : détection
   * couleur -> centre du trait -> calibration -> unités physiques.
   *
   * Elle a besoin de lire des fichiers : le lanceur node fournit
   * CFDD.Tests.ressources ; dans le navigateur, la suite est simplement absente.
   */
  if (!T.ressources) { return; }

  var R = T.ressources;

  /* Rectangle de tracé réel, arrondi vers l'intérieur pour rester sur les axes. */
  function zoneTrace(figure) {
    var c = R.reference[figure].cadres.trace;
    return { x0: Math.ceil(c.x0) + 1, y0: Math.ceil(c.y0) + 1,
             x1: Math.floor(c.x1) - 1, y1: Math.floor(c.y1) - 1 };
  }

  /* Boîte de légende réelle, élargie d'un pixel pour couvrir son cadre. */
  function boiteLegende(figure) {
    var c = R.reference[figure].cadres.legende;
    return { x0: Math.floor(c.x0) - 1, y0: Math.floor(c.y0) - 1,
             x1: Math.ceil(c.x1) + 1, y1: Math.ceil(c.y1) + 1 };
  }

  /*
   * Erreur de digitalisation, mesurée comme la DISTANCE d'un point extrait à la
   * courbe de référence, dans un repère normalisé par l'étendue des axes.
   *
   * Comparer « y obtenu vs y attendu au même x » serait trompeur : là où la
   * courbe est raide, un écart horizontal de moins d'un pixel se traduit par un
   * écart vertical énorme, et l'on mesurerait la pente au lieu de mesurer
   * l'outil. La distance au tracé est, elle, la grandeur que l'utilisateur
   * constate réellement.
   *
   * Normalisation : chaque axe est ramené à [0, 1] sur ses bornes, en
   * logarithme quand l'axe l'est. Le résultat s'exprime donc en fraction de
   * l'étendue du graphique.
   */
  function normaliseur(figure) {
    var lim = R.reference[figure].cadres.limites;
    function fabrique(bornes, log) {
      var a = log ? Math.log(bornes[0]) / Math.LN10 : bornes[0];
      var b = log ? Math.log(bornes[1]) / Math.LN10 : bornes[1];
      return function (v) {
        var u = log ? (Math.log(v) / Math.LN10) : v;
        return (u - a) / (b - a);
      };
    }
    return { x: fabrique(lim.x, lim.logX), y: fabrique(lim.y, lim.logY) };
  }

  /* Distance d'un point à un segment, en coordonnées normalisées. */
  function distanceSegment(px, py, ax, ay, bx, by) {
    var vx = bx - ax, vy = by - ay;
    var wx = px - ax, wy = py - ay;
    var n2 = vx * vx + vy * vy;
    var t = (n2 === 0) ? 0 : Math.max(0, Math.min(1, (wx * vx + wy * vy) / n2));
    var dx = wx - t * vx, dy = wy - t * vy;
    return Math.sqrt(dx * dx + dy * dy);
  }

  /*
   * Extrait une courbe et rend l'erreur maximale et médiane, en fraction de
   * l'étendue du graphique.
   */
  function mesurer(figure, nomCourbe, options) {
    var meta = R.reference[figure];
    var norme = normaliseur(figure);
    var cible = CFDD.Couleur.hexVersRgb(meta.couleurs[nomCourbe]);
    var cal = CFDD.Calibration.creer(meta.calibration);

    var res = CFDD.Detection.detecter(R.images[figure], cible, options);

    /*
     * On écarte la bande de deux pixels le long du cadre. Là, le tracé est
     * rogné par la borne de l'axe : la courbe de référence continue au-delà de
     * ce que l'image contient, et l'écart mesuré serait un artefact de la
     * figure, pas de la détection.
     */
    var z = options.zone;
    var dedans = [];
    for (var b = 0; b < res.points.length; b++) {
      var q = res.points[b];
      if (q.px > z.x0 + 2 && q.px < z.x1 - 2 && q.py > z.y0 + 2 && q.py < z.y1 - 2) {
        dedans.push(q);
      }
    }
    var pts = CFDD.Projet.seriesEnDonnees([{ nom: nomCourbe, points: dedans }], cal)[0].points;

    /* Référence normalisée, ramenée à un polyligne. */
    var ref = meta.courbes[nomCourbe];
    var rx = [], ry = [];
    for (var k = 0; k < ref.x.length; k++) {
      rx.push(norme.x(ref.x[k]));
      ry.push(norme.y(ref.y[k]));
    }

    var distances = [];
    for (var i = 0; i < pts.length; i++) {
      var nx = norme.x(pts[i].x), ny = norme.y(pts[i].y);
      var meilleur = Infinity;
      for (var j = 0; j < rx.length - 1; j++) {
        /* Écarte d'emblée les segments manifestement trop loin. */
        if (Math.abs(rx[j] - nx) > 0.2 && Math.abs(rx[j + 1] - nx) > 0.2) { continue; }
        meilleur = Math.min(meilleur,
          distanceSegment(nx, ny, rx[j], ry[j], rx[j + 1], ry[j + 1]));
      }
      if (meilleur !== Infinity) { distances.push(meilleur); }
    }
    distances.sort(function (a, b) { return a - b; });

    return {
      n: pts.length,
      comparees: distances.length,
      max: distances.length ? distances[distances.length - 1] : NaN,
      mediane: distances.length ? distances[Math.floor(distances.length / 2)] : NaN
    };
  }

  T.suite('Intégration — figures matplotlib réelles', function (test) {

    test('polaire : extrait les trois courbes au sous-pixel près', function (a) {
      /*
       * Une polaire est un arc couché : Cx est fonction de Cz, pas l'inverse.
       * D'où le balayage en LIGNES — en colonnes, le mode « moyenne » réduirait
       * les deux branches à leur milieu.
       */
      var noms = ['Re = 3e6', 'Re = 6e6', 'Re = 9e6'];
      for (var i = 0; i < noms.length; i++) {
        var m = mesurer('exemple_polaire.png', noms[i], {
          tolChroma: 22, tolLum: 32, mode: 'moyenne', orientation: 'lignes',
          zone: zoneTrace('exemple_polaire.png'),
          zonesExclues: [boiteLegende('exemple_polaire.png')]
        });
        a.ok(m.n > 200, noms[i] + ' : ' + m.n + ' points');
        var resume = noms[i] + ' : écart max ' + (m.max * 100).toFixed(3)
          + ' %, médian ' + (m.mediane * 100).toFixed(3) + ' %';
        /*
         * Deux seuils, parce qu'ils mesurent deux choses. La MÉDIANE dit
         * l'exactitude courante ; le MAXIMUM garde le pire cas sous contrôle.
         * Repère : 0.1 % de l'étendue vaut environ un demi-pixel sur une
         * figure de 530 x 385.
         *
         * Le pire cas se situe systématiquement là où la courbe devient
         * PARALLÈLE à la direction de balayage — ici le haut de la polaire, où
         * dCx/dCz est grand et où une ligne traverse un long segment de trait.
         * Le milieu de ce segment n'est plus tout à fait le point de la courbe.
         * C'est la limite propre au balayage aligné sur les axes ; la parade
         * est de changer d'orientation. Voir 00_DOC/02_DETECTION_COULEUR.md.
         *
         * S'y ajoute, aux bornes de l'axe, le rognage du tracé par le cadre :
         * le trait y est coupé, et le milieu de ce qu'il en reste n'est plus
         * celui de la courbe. D'où un seuil de pire cas nettement plus lâche
         * que la médiane — il n'est là que pour attraper une régression franche.
         */
        a.ok(m.mediane < 0.0015, resume);
        a.ok(m.max < 0.005, resume);
      }
    });

    test('polaire : la couleur d’une courbe ne capte pas les autres', function (a) {
      /* Les trois teintes sont franchement distinctes : une tolérance serrée
         doit isoler chacune. Si le rouge ramassait le bleu, l'erreur exploserait
         — ce que le test précédent verrait déjà, mais on le vérifie ici sur le
         nombre de pixels retenus, plus direct. */
      var meta = R.reference['exemple_polaire.png'];
      var image = R.images['exemple_polaire.png'];
      var options = {
        tolChroma: 22, tolLum: 32,
        zone: zoneTrace('exemple_polaire.png'),
        zonesExclues: [boiteLegende('exemple_polaire.png')]
      };
      var noms = ['Re = 3e6', 'Re = 6e6', 'Re = 9e6'];

      /*
       * Vérification directe : aucun pixel retenu pour une couleur ne doit
       * l'être pour une autre. Comparer des effectifs serait ambigu — les trois
       * courbes n'ont pas la même longueur visible, l'une étant tronquée par la
       * borne droite de l'axe. Le recouvrement, lui, est sans appel.
       */
      var masques = [];
      for (var i = 0; i < noms.length; i++) {
        masques.push(CFDD.Detection.construireMasque(
          image, CFDD.Couleur.hexVersRgb(meta.couleurs[noms[i]]), options));
      }
      var ambigus = 0, retenus = 0;
      for (var p = 0; p < masques[0].masque.length; p++) {
        var compte = 0;
        for (var q = 0; q < masques.length; q++) { compte += masques[q].masque[p]; }
        if (compte >= 1) { retenus++; }
        if (compte > 1) { ambigus++; }
      }
      /*
       * Zéro pixel ambigu serait irréaliste : là où deux courbes se frôlent,
       * l'anticrénelage crée des pixels réellement intermédiaires, que deux
       * cibles peuvent légitimement revendiquer. Ce qui compte est que cela
       * reste marginal — sinon une couleur ramasse la courbe voisine.
       */
      a.ok(ambigus < retenus * 0.02,
        ambigus + ' pixels ambigus sur ' + retenus + ' retenus');
      var effectifs = masques.map(function (m) { return m.nbRetenus; });
      a.ok(Math.min.apply(null, effectifs) > 300,
        'chaque courbe est bien captée (' + effectifs.join(', ') + ')');
    });

    test('convergence : axe Y logarithmique sur six décades', function (a) {
      var noms = ['continuite', 'Ux', 'k'];
      for (var i = 0; i < noms.length; i++) {
        var m = mesurer('exemple_convergence.png', noms[i], {
          tolChroma: 22, tolLum: 32, mode: 'moyenne',
          zone: zoneTrace('exemple_convergence.png'),
          zonesExclues: [boiteLegende('exemple_convergence.png')]
        });
        a.ok(m.n > 300, noms[i] + ' : ' + m.n + ' points');
        var resume = noms[i] + ' : écart max ' + (m.max * 100).toFixed(3)
          + ' %, médian ' + (m.mediane * 100).toFixed(3) + ' %';
        /*
         * Le repère normalisé absorbe le logarithme : 0.1 % de l'étendue vaut
         * ici 0.008 décade, soit 0.4 pixel sur les 385 de hauteur. L'écart
         * maximal se produit au coude où la décroissance rejoint son palier.
         */
        a.ok(m.mediane < 0.001, resume);
        /* Même effet qu'en polaire, ici sur le départ très raide de la
           décroissance exponentielle : 99 % des points restent sous 0.15 %. */
        a.ok(m.max < 0.005, resume);
      }
    });

    test('convergence : la palette propose les trois couleurs tracées', function (a) {
      var meta = R.reference['exemple_convergence.png'];
      var palette = CFDD.Detection.couleursDominantes(R.images['exemple_convergence.png'], {
        zone: zoneTrace('exemple_convergence.png'), maxCouleurs: 8
      });
      a.ok(palette.length >= 3, palette.length + ' couleurs proposées');

      var noms = ['continuite', 'Ux', 'k'];
      for (var i = 0; i < noms.length; i++) {
        var cible = CFDD.Couleur.hexVersRgb(meta.couleurs[noms[i]]);
        var labCible = CFDD.Couleur.rgbVersLab(cible.r, cible.g, cible.b);
        var trouve = false;
        for (var j = 0; j < palette.length; j++) {
          if (CFDD.Couleur.deltaE(palette[j].lab, labCible) < 20) { trouve = true; }
        }
        a.ok(trouve, noms[i] + ' proposé (palette : '
          + palette.map(function (c) { return c.hex; }).join(' ') + ')');
      }
    });

    test('traits : reconnaît le tracé de chaque courbe monochrome', function (a) {
      /*
       * Trois courbes rigoureusement de la même couleur, distinguées par leur
       * seul tracé. On isole chacune par le filtre de type de trait, puis on
       * vérifie que le style mesuré est bien celui attendu.
       */
      var figure = 'exemple_traits.png';
      var image = R.images[figure];
      var options = {
        tolChroma: 25, tolLum: 45,
        zone: zoneTrace(figure), zonesExclues: [boiteLegende(figure)]
      };
      var noir = { r: 16, g: 16, b: 16 };

      /* Sans tri, le masque contient les trois : le style global est continu. */
      var tout = CFDD.Detection.detecter(image, noir, options);
      a.egal(tout.statistiques.trait.style, CFDD.Trait.STYLES.continu,
        'la courbe pleine domine le masque complet');

      options.filtreTrait = 'discontinu';
      var discontinu = CFDD.Detection.detecter(image, noir, options);
      a.ok(discontinu.statistiques.trait.nbComposantes > 20,
        discontinu.statistiques.trait.nbComposantes + ' tronçons');
      a.ok(discontinu.statistiques.trait.style !== CFDD.Trait.STYLES.continu,
        'style mesuré : ' + discontinu.statistiques.trait.style);
      a.ok(discontinu.points.length < tout.points.length,
        'le tri retire bien des points');
    });

    test('traits : le tri isole la courbe pleine des autres', function (a) {
      var figure = 'exemple_traits.png';
      var meta = R.reference[figure];
      var m = mesurer(figure, 'continu', {
        tolChroma: 25, tolLum: 45, mode: 'moyenne', filtreTrait: 'continu',
        zone: zoneTrace(figure), zonesExclues: [boiteLegende(figure)]
      });
      a.ok(m.n > 400, m.n + ' points');
      var resume = 'écart max ' + (m.max * 100).toFixed(3)
        + ' %, médian ' + (m.mediane * 100).toFixed(3) + ' %';
      /*
       * Le tri n'écarte que des composantes entières : là où la courbe pleine
       * touche une courbe en tirets, les deux fusionnent et la pleine emporte
       * le tronçon. D'où un pire cas plus lâche que sur une figure en couleurs.
       */
      a.ok(m.mediane < 0.0025, resume);
      a.ok(m.max < 0.02, resume);
    });

    test('traits : chaque tracé isole SA courbe, à couleur identique', function (a) {
      /*
       * Le test qui justifie toute la fonction : trois courbes rigoureusement
       * de la même couleur, séparées par leur seul tracé. On vérifie non
       * seulement l'exactitude, mais l'ATTRIBUTION — que les points extraits
       * appartiennent bien à la courbe visée et pas à sa voisine.
       */
      var figure = 'exemple_traits.png';
      var meta = R.reference[figure];
      var norme = normaliseur(figure);
      var cal = CFDD.Calibration.creer(meta.calibration);
      var noms = ['continu', 'tirets', 'pointille'];

      function polyligne(nom) {
        var c = meta.courbes[nom], xs = [], ys = [];
        for (var i = 0; i < c.x.length; i++) { xs.push(norme.x(c.x[i])); ys.push(norme.y(c.y[i])); }
        return { xs: xs, ys: ys };
      }
      var polylignes = {};
      for (var n = 0; n < noms.length; n++) { polylignes[noms[n]] = polyligne(noms[n]); }

      function ecart(pt, poly) {
        var X = norme.x(pt.x), Y = norme.y(pt.y), meilleur = Infinity;
        for (var j = 0; j < poly.xs.length - 1; j++) {
          meilleur = Math.min(meilleur, distanceSegment(X, Y,
            poly.xs[j], poly.ys[j], poly.xs[j + 1], poly.ys[j + 1]));
        }
        return meilleur;
      }

      var filtres = { continu: 'continu', tirets: 'tirets', pointille: 'pointillé' };
      for (var k = 0; k < noms.length; k++) {
        var vise = noms[k];
        var res = CFDD.Detection.detecter(R.images[figure], { r: 16, g: 16, b: 16 }, {
          tolChroma: 25, tolLum: 45, mode: 'moyenne', filtreTrait: filtres[vise],
          zone: zoneTrace(figure), zonesExclues: [boiteLegende(figure)]
        });
        var pts = CFDD.Projet.seriesEnDonnees([{ nom: vise, points: res.points }], cal)[0].points;
        a.ok(pts.length > 150, vise + ' : seulement ' + pts.length + ' points');

        var bons = 0, distances = [];
        for (var i = 0; i < pts.length; i++) {
          var meilleurNom = null, meilleure = Infinity;
          for (var m = 0; m < noms.length; m++) {
            var d = ecart(pts[i], polylignes[noms[m]]);
            if (d < meilleure) { meilleure = d; meilleurNom = noms[m]; }
          }
          if (meilleurNom === vise) { bons++; }
          distances.push(ecart(pts[i], polylignes[vise]));
        }
        distances.sort(function (x, y) { return x - y; });
        var mediane = distances[Math.floor(distances.length / 2)];

        a.ok(bons > pts.length * 0.97, vise + ' : ' + bons + '/' + pts.length
          + ' points attribués à la bonne courbe');
        a.ok(mediane < 0.002, vise + ' : écart médian '
          + (mediane * 100).toFixed(3) + ' % de l’étendue');
      }
    });

    test('traits : combler les lacunes densifie sans dévier', function (a) {
      var figure = 'exemple_traits.png';
      var options = {
        tolChroma: 25, tolLum: 45, mode: 'moyenne', filtreTrait: 'discontinu',
        zone: zoneTrace(figure), zonesExclues: [boiteLegende(figure)]
      };
      var sans = CFDD.Detection.detecter(R.images[figure], { r: 16, g: 16, b: 16 }, options);
      options.comblerLacunes = 14;
      var avec = CFDD.Detection.detecter(R.images[figure], { r: 16, g: 16, b: 16 }, options);

      a.ok(avec.points.length > sans.points.length,
        sans.points.length + ' points, ' + avec.points.length + ' après comblement');
      a.egal(avec.statistiques.pointsBruts, sans.statistiques.pointsBruts,
        'les points bruts sont inchangés');
    });

    test('la grille et les axes gris ne sont jamais captés', function (a) {
      /* La grille matplotlib est en #cccccc, les axes en noir : sur une cible
         rouge vif, aucun des deux ne doit passer le double critère. */
      var zone = zoneTrace('exemple_polaire.png');
      var m = CFDD.Detection.construireMasque(
        R.images['exemple_polaire.png'], { r: 193, g: 18, b: 31 },
        { tolChroma: 22, tolLum: 32, zone: zone });
      var img = R.images['exemple_polaire.png'];
      var grisCaptes = 0;
      for (var y = zone.y0; y <= zone.y1; y++) {
        for (var x = zone.x0; x <= zone.x1; x++) {
          if (!m.masque[(y - m.zone.y0) * m.largeurZone + (x - m.zone.x0)]) { continue; }
          var i = (y * img.width + x) * 4;
          var r = img.data[i], g = img.data[i + 1], b = img.data[i + 2];
          /* Un pixel « gris » : ses trois canaux sont proches. */
          if (Math.max(r, g, b) - Math.min(r, g, b) < 25) { grisCaptes++; }
        }
      }
      a.egal(grisCaptes, 0, grisCaptes + ' pixels gris captés à tort');
    });

    test('sans zone d’analyse, la légende pollue le résultat', function (a) {
      /* Justifie l'existence de la zone : la légende contient un segment de la
         couleur exacte de la courbe, en bas à droite de la figure. Sans
         restriction, il crée des points aberrants. */
      var meta = R.reference['exemple_polaire.png'];
      var cible = CFDD.Couleur.hexVersRgb(meta.couleurs['Re = 3e6']);
      var options = { tolChroma: 22, tolLum: 32, mode: 'tous' };

      options.zone = zoneTrace('exemple_polaire.png');
      var avecLegende = CFDD.Detection.detecter(R.images['exemple_polaire.png'], cible, options);
      options.zonesExclues = [boiteLegende('exemple_polaire.png')];
      var sansLegende = CFDD.Detection.detecter(R.images['exemple_polaire.png'], cible, options);

      a.ok(avecLegende.points.length > sansLegende.points.length,
        'la légende ajoute des points parasites ('
        + avecLegende.points.length + ' contre ' + sansLegende.points.length + ')');

      /* Ces points parasites sont bien DANS la boîte de légende. */
      var boite = boiteLegende('exemple_polaire.png');
      var dedans = 0;
      for (var i = 0; i < avecLegende.points.length; i++) {
        var pt = avecLegende.points[i];
        if (pt.px >= boite.x0 && pt.px <= boite.x1
            && pt.py >= boite.y0 && pt.py <= boite.y1) { dedans++; }
      }
      a.ok(dedans > 0, 'le trait de légende est bien capté sans exclusion');
      for (var j = 0; j < sansLegende.points.length; j++) {
        var q = sansLegende.points[j];
        a.ok(!(q.px >= boite.x0 && q.px <= boite.x1
               && q.py >= boite.y0 && q.py <= boite.y1),
          'aucun point ne subsiste dans la légende exclue');
      }
    });
  });
})();
