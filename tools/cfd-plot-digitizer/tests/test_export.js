(function () {
  'use strict';
  var T = globalThis.CFDD.Tests, E = globalThis.CFDD.Export;

  function series() {
    return [
      { nom: 'Cp, extrados', couleurHex: '#cc0000',
        points: [{ x: 0, y: 1 }, { x: 0.5, y: -0.25 }, { x: 1, y: 0.13456789 }] },
      { nom: 'Cp intrados', couleurHex: '#0000cc', points: [{ x: 0, y: 1 }] }
    ];
  }

  T.suite('Export — mise en forme des séries', function (test) {

    test('CSV long : une ligne par point, nom échappé', function (a) {
      var lignes = E.versCSVLong(series()).trim().split('\n');
      a.egal(lignes[0], 'serie,x,y');
      a.egal(lignes[1], '"Cp, extrados",0,1', 'la virgule du nom force les guillemets');
      a.egal(lignes[4], 'Cp intrados,0,1');
      a.egal(lignes.length, 5);
    });

    test('CSV long : séparateur point-virgule sans échappement superflu', function (a) {
      var lignes = E.versCSVLong(series(), { separateur: ';' }).trim().split('\n');
      a.egal(lignes[0], 'serie;x;y');
      a.egal(lignes[1], 'Cp, extrados;0;1', 'la virgule n’est plus un séparateur');
    });

    test('CSV long : les guillemets internes sont doublés', function (a) {
      var s = [{ nom: 'essai "A"', points: [{ x: 1, y: 2 }] }];
      a.ok(E.versCSVLong(s).indexOf('"essai ""A"""') !== -1);
    });

    test('CSV large : les séries courtes sont complétées', function (a) {
      var lignes = E.versCSVLarge(series()).trim().split('\n');
      a.egal(lignes.length, 4, 'entête + 3 lignes');
      a.egal(lignes[2], '0.5,-0.25,,', 'la seconde série est vide au-delà du premier point');
    });

    test('sans entêtes, aucune ligne de titre', function (a) {
      var lignes = E.versCSVLong(series(), { entetes: false }).trim().split('\n');
      a.egal(lignes.length, 4);
      a.egal(lignes[0], '"Cp, extrados",0,1');
    });

    test('JSON : structure relisible et arrondie', function (a) {
      var o = JSON.parse(E.versJSON(series(), { decimales: 4 }));
      a.egal(o.outil, 'cfd-plot-digitizer');
      a.egal(o.series.length, 2);
      a.egal(o.series[0].couleur, '#cc0000');
      a.egalProfond(o.series[0].points[2], [1, 0.1346]);
    });

    test('Python : identifiants valides, accents translittérés', function (a) {
      var src = E.versPython([
        { nom: 'Débit à 20°C', points: [{ x: 1, y: 2 }] },
        { nom: 'Débit à 20°C', points: [{ x: 3, y: 4 }] },
        { nom: '3 séries', points: [] }
      ]);
      a.ok(src.indexOf('import numpy as np') === 0);
      a.ok(src.indexOf('Debit_a_20_C_x = np.array([1])') !== -1);
      a.ok(src.indexOf('Debit_a_20_C__x') !== -1, 'le doublon est désambiguïsé');
    });

    test('MATLAB : vecteurs séparés par des espaces', function (a) {
      var src = E.versMatlab(series());
      a.ok(src.indexOf('Cp_extrados_x = [0 0.5 1];') !== -1);
      a.ok(src.indexOf('Cp_extrados_y = [1 -0.25 0.134568];') !== -1);
    });

    test('accorde le pluriel du décompte de points', function (a) {
      var src = E.versPython([{ nom: 'un', points: [{ x: 1, y: 1 }] }]);
      a.ok(src.indexOf('(1 point)') !== -1);
      a.ok(src.indexOf('(1 points)') === -1);
    });

    test('colonnes : tabulation, un bloc par série', function (a) {
      var texte = E.versColonnes(series());
      a.ok(texte.indexOf('0\t1') !== -1);
      a.ok(texte.indexOf('# Cp, extrados') !== -1);
    });

    test('colonnes : série unique sans entête de bloc', function (a) {
      var texte = E.versColonnes([series()[0]]);
      a.ok(texte.indexOf('#') === -1);
    });

    test('grille : interpole les séries sur une abscisse commune', function (a) {
      var series = [
        { nom: 'A', points: [{ x: 0, y: 0 }, { x: 1, y: 10 }, { x: 2, y: 20 }] },
        { nom: 'B', points: [{ x: 0.5, y: 5 }, { x: 1.5, y: 15 }, { x: 3, y: 30 }] }
      ];
      var g = E.reechantillonner(series, { grillePoints: 5 });
      /* Intersection des domaines : [0.5, 2]. */
      a.proche(g.x[0], 0.5, 1e-12);
      a.proche(g.x[4], 2, 1e-12);
      a.egal(g.colonnes.length, 2);
      /* Les deux séries valent y = 10x sur le recouvrement. */
      for (var i = 0; i < g.x.length; i++) {
        a.proche(g.colonnes[0].y[i], 10 * g.x[i], 1e-9);
        a.proche(g.colonnes[1].y[i], 10 * g.x[i], 1e-9);
      }
      a.egalProfond(g.avertissements, []);
    });

    test('grille : le domaine « union » laisse des trous plutôt qu’extrapoler', function (a) {
      var series = [
        { nom: 'A', points: [{ x: 0, y: 0 }, { x: 2, y: 20 }] },
        { nom: 'B', points: [{ x: 1, y: 10 }, { x: 3, y: 30 }] }
      ];
      var g = E.reechantillonner(series, { grillePoints: 5, grilleDomaine: 'union' });
      a.proche(g.x[0], 0, 1e-12);
      a.proche(g.x[4], 3, 1e-12);
      /* Extrapoler inventerait des données que l'image ne contient pas. */
      a.egal(g.colonnes[1].y[0], null, 'B n’est pas définie en x = 0');
      a.egal(g.colonnes[0].y[4], null, 'A n’est pas définie en x = 3');
    });

    test('grille : espacement logarithmique', function (a) {
      var g = E.reechantillonner(
        [{ nom: 'L', points: [{ x: 1, y: 0 }, { x: 100, y: 2 }] }],
        { grillePoints: 3, grilleEspacement: 'log' });
      a.proche(g.x[0], 1, 1e-9);
      a.proche(g.x[1], 10, 1e-9);
      a.proche(g.x[2], 100, 1e-9);
    });

    test('grille : retombe en linéaire si le log est impossible', function (a) {
      var g = E.reechantillonner(
        [{ nom: 'L', points: [{ x: -1, y: 0 }, { x: 1, y: 2 }] }],
        { grillePoints: 3, grilleEspacement: 'log' });
      a.proche(g.x[1], 0, 1e-12);
      a.ok(g.avertissements.join(' ').indexOf('linéaire') !== -1);
    });

    test('grille : écarte une courbe repliée au lieu de l’écraser', function (a) {
      /*
       * Une polaire porte deux y pour un même x. L'interpoler en x fondrait ses
       * deux branches en une moyenne sans signification — et le tableau produit
       * n'aurait l'air de rien de suspect. Mieux vaut l'écarter en le disant.
       */
      var polaire = { nom: 'polaire', points: [] };
      for (var t = -1; t <= 1.0001; t += 0.05) {
        polaire.points.push({ x: 0.01 + t * t * 0.05, y: t });
      }
      var g = E.reechantillonner(
        [polaire, { nom: 'droite', points: [{ x: 0.01, y: 0 }, { x: 0.06, y: 1 }] }],
        { grillePoints: 4 });
      a.egal(g.colonnes.length, 1);
      a.egal(g.colonnes[0].nom, 'droite');
      a.ok(g.avertissements.join(' ').indexOf('repliée') !== -1, g.avertissements.join(' '));
    });

    test('grille : tolère le bruit d’une série monotone', function (a) {
      /* Le bruit de détection crée des micro-retours en x : ils ne doivent pas
         faire passer une fonction parfaitement valide pour une courbe repliée. */
      var bruitee = { nom: 'bruitee', points: [] };
      for (var i = 0; i < 200; i++) {
        bruitee.points.push({ x: i * 0.01 + (i % 3 === 0 ? -0.004 : 0.002), y: i });
      }
      var g = E.reechantillonner([bruitee], { grillePoints: 5 });
      a.egal(g.colonnes.length, 1);
      a.egalProfond(g.avertissements, []);
    });

    test('grille : signale des domaines disjoints', function (a) {
      var g = E.reechantillonner([
        { nom: 'a', points: [{ x: 0, y: 0 }, { x: 1, y: 1 }] },
        { nom: 'b', points: [{ x: 5, y: 0 }, { x: 6, y: 1 }] }
      ], {});
      a.egalProfond(g.colonnes, []);
      a.ok(g.avertissements.join(' ').indexOf('recouvrent pas') !== -1);
    });

    test('grille : écarte une série trop courte', function (a) {
      var g = E.reechantillonner([
        { nom: 'seul', points: [{ x: 1, y: 1 }] },
        { nom: 'bonne', points: [{ x: 0, y: 0 }, { x: 2, y: 2 }] }
      ], { grillePoints: 3 });
      a.egal(g.colonnes.length, 1);
      a.ok(g.avertissements.join(' ').indexOf('moins de deux points') !== -1);
    });

    test('grille : fond les abscisses en double', function (a) {
      var g = E.reechantillonner(
        [{ nom: 'D', points: [{ x: 0, y: 0 }, { x: 1, y: 10 }, { x: 1, y: 20 }, { x: 2, y: 40 }] }],
        { grillePoints: 3 });
      a.proche(g.colonnes[0].y[1], 15, 1e-9, 'moyenne des deux y en x = 1');
    });

    test('CSV grille : une colonne x, puis une par série', function (a) {
      var texte = E.versCSVGrille([
        { nom: 'A', points: [{ x: 0, y: 0 }, { x: 2, y: 20 }] },
        { nom: 'B', points: [{ x: 0, y: 1 }, { x: 2, y: 21 }] }
      ], { grillePoints: 3 });
      var lignes = texte.trim().split('\n');
      a.egal(lignes[0], 'x,A,B');
      a.egal(lignes[1], '0,0,1');
      a.egal(lignes[2], '1,10,11');
      a.egal(lignes[3], '2,20,21');
    });

    test('CSV grille : cellule vide hors du domaine d’une série', function (a) {
      var texte = E.versCSVGrille([
        { nom: 'A', points: [{ x: 0, y: 0 }, { x: 2, y: 20 }] },
        { nom: 'B', points: [{ x: 1, y: 10 }, { x: 2, y: 20 }] }
      ], { grillePoints: 3, grilleDomaine: 'union' });
      a.egal(texte.trim().split('\n')[1], '0,0,');
    });

    test('rendre couvre tous les formats annoncés', function (a) {
      for (var i = 0; i < E.FORMATS.length; i++) {
        var sortie = E.rendre(E.FORMATS[i], series());
        a.ok(typeof sortie === 'string' && sortie.length > 0, E.FORMATS[i]);
      }
      a.leve(function () { E.rendre('inconnu', series()); }, 'Format inconnu');
    });

    test('gère une liste de séries vide', function (a) {
      a.egal(E.versCSVLong([]).trim(), 'serie,x,y');
      a.egalProfond(JSON.parse(E.versJSON([])).series, []);
    });

    test('associe la bonne extension à chaque format', function (a) {
      a.egal(E.extension('csv-long'), 'csv');
      a.egal(E.extension('csv-large'), 'csv');
      a.egal(E.extension('csv-grille'), 'csv');
      a.egal(E.extension('json'), 'json');
      a.egal(E.extension('python'), 'py');
      a.egal(E.extension('matlab'), 'm');
      a.egal(E.extension('colonnes'), 'txt');
    });
  });
})();
