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
      a.egal(E.extension('json'), 'json');
      a.egal(E.extension('python'), 'py');
      a.egal(E.extension('matlab'), 'm');
      a.egal(E.extension('colonnes'), 'txt');
    });
  });
})();
