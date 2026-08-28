(function () {
  'use strict';
  var T = globalThis.CFDD.Tests, C = globalThis.CFDD.Couleur;

  T.suite('Couleur — sRGB, Lab, correspondance', function (test) {

    test('convertit les primaires aux valeurs de référence CIE', function (a) {
      /* Références publiées pour sRGB / D65 / observateur 2°. */
      var blanc = C.rgbVersLab(255, 255, 255);
      a.proche(blanc.L, 100, 1e-4); a.proche(blanc.a, 0, 1e-3); a.proche(blanc.b, 0, 1e-3);

      var noir = C.rgbVersLab(0, 0, 0);
      a.proche(noir.L, 0, 1e-9);

      var rouge = C.rgbVersLab(255, 0, 0);
      a.proche(rouge.L, 53.2408, 1e-3);
      a.proche(rouge.a, 80.0925, 1e-3);
      a.proche(rouge.b, 67.2032, 1e-3);

      var bleu = C.rgbVersLab(0, 0, 255);
      a.proche(bleu.L, 32.2970, 1e-3);
      a.proche(bleu.a, 79.1875, 1e-3);
      a.proche(bleu.b, -107.8602, 1e-3);
    });

    test('lit les écritures hexadécimales usuelles', function (a) {
      a.egalProfond(C.hexVersRgb('#FF8000'), { r: 255, g: 128, b: 0 });
      a.egalProfond(C.hexVersRgb('ff8000'), { r: 255, g: 128, b: 0 });
      a.egalProfond(C.hexVersRgb('#abc'), { r: 170, g: 187, b: 204 });
      a.egal(C.hexVersRgb('#gg0000'), null);
      a.egal(C.hexVersRgb(''), null);
      a.egal(C.hexVersRgb(null), null);
    });

    test('fait l’aller-retour hex <-> rgb', function (a) {
      a.egal(C.rgbVersHex({ r: 255, g: 128, b: 0 }), '#ff8000');
      a.egal(C.rgbVersHex({ r: 0, g: 0, b: 0 }), '#000000');
      a.egal(C.rgbVersHex({ r: 300, g: -5, b: 12.4 }), '#ff000c', 'les valeurs hors plage sont bornées');
    });

    test('retient une teinte proche et rejette une autre teinte', function (a) {
      var m = C.creerCorrespondance({ r: 200, g: 30, b: 30 }, { tolChroma: 20, tolLum: 30 });
      a.ok(m.correspond(205, 40, 35), 'rouge légèrement différent');
      a.ok(!m.correspond(255, 255, 255), 'fond blanc');
      a.ok(!m.correspond(30, 30, 200), 'bleu');
    });

    test('sépare bien luminance et chroma', function (a) {
      /* Un gris moyen et un blanc ont la même chroma (nulle) : seule la
         tolérance de luminance peut les distinguer. C'est le cas qui rend
         indispensable le critère à deux composantes. */
      var serre = C.creerCorrespondance({ r: 128, g: 128, b: 128 }, { tolChroma: 10, tolLum: 10 });
      a.ok(!serre.correspond(255, 255, 255), 'blanc écarté par la luminance');
      a.ok(serre.correspond(130, 130, 130), 'gris voisin retenu');

      var large = C.creerCorrespondance({ r: 128, g: 128, b: 128 }, { tolChroma: 10, tolLum: 100 });
      a.ok(large.correspond(255, 255, 255), 'sans contrainte de luminance, le blanc passe');
    });

    test('tolère l’anticrénelage d’un trait coloré', function (a) {
      /* Pixel de bord : 60 % de rouge sur fond blanc. La teinte reste rouge,
         la clarté monte fortement — exactement ce que la double tolérance
         est censée absorber. */
      var m = C.creerCorrespondance({ r: 200, g: 30, b: 30 }, { tolChroma: 45, tolLum: 45 });
      var melange = { r: Math.round(200 * 0.6 + 255 * 0.4),
                      g: Math.round(30 * 0.6 + 255 * 0.4),
                      b: Math.round(30 * 0.6 + 255 * 0.4) };
      a.ok(m.correspond(melange.r, melange.g, melange.b));
    });

    test('échantillonne une fenêtre plutôt qu’un pixel', function (a) {
      var img = T.imageVide(9, 9, { r: 255, g: 255, b: 255 });
      T.poser(img, 4, 4, { r: 0, g: 0, b: 0 });
      var moyen = C.echantillonner(img, 4, 4, 1);   /* 9 pixels : 1 noir, 8 blancs */
      a.proche(moyen.r, Math.round(255 * 8 / 9), 1);
      var seul = C.echantillonner(img, 4, 4, 0);
      a.egalProfond(seul, { r: 0, g: 0, b: 0 });
    });

    test('l’échantillon dominant retrouve le trait malgré un clic décalé', function (a) {
      var img = T.imageVide(11, 11, { r: 255, g: 255, b: 255 });
      /* Trait rouge vertical en x=5, clic en x=4 : la moyenne tirerait vers
         le blanc, le mode dominant doit rendre le rouge. */
      for (var y = 0; y < 11; y++) { T.poser(img, 5, y, { r: 200, g: 20, b: 20 }); }
      var dom = C.echantillonnerDominante(img, 4, 5, 2);
      a.egalProfond(dom, { r: 200, g: 20, b: 20 });
    });

    test('choisit une surbrillance qui tranche sur la cible et sur le fond', function (a) {
      /* Un aperçu magenta sur une courbe magenta est invisible — or c'est
         justement là que l'utilisateur regarde. */
      var surMagenta = C.contrastee({ r: 255, g: 0, b: 255 });
      a.ok(C.deltaE(C.rgbVersLab(surMagenta.r, surMagenta.g, surMagenta.b),
                    C.rgbVersLab(255, 0, 255)) > 60, 'assez loin du magenta');

      var surBlanc = C.contrastee({ r: 250, g: 250, b: 250 });
      a.ok(C.deltaE(C.rgbVersLab(surBlanc.r, surBlanc.g, surBlanc.b),
                    C.rgbVersLab(255, 255, 255)) > 40, 'assez loin du blanc');
    });

    test('la surbrillance tranche aussi sur le fond donné', function (a) {
      /* Cible noire sur fond blanc : la surbrillance doit éviter les deux. */
      var c = C.contrastee({ r: 0, g: 0, b: 0 }, { r: 255, g: 255, b: 255 });
      var lab = C.rgbVersLab(c.r, c.g, c.b);
      a.ok(C.deltaE(lab, C.rgbVersLab(0, 0, 0)) > 40);
      a.ok(C.deltaE(lab, C.rgbVersLab(255, 255, 255)) > 40);
    });

    test('la surbrillance sort toujours de la palette prévue', function (a) {
      for (var i = 0; i < 12; i++) {
        var cible = { r: (i * 37) % 256, g: (i * 91) % 256, b: (i * 53) % 256 };
        var choisie = C.contrastee(cible);
        var dedans = false;
        for (var j = 0; j < C.PALETTE_SURBRILLANCE.length; j++) {
          var p = C.PALETTE_SURBRILLANCE[j];
          if (p.r === choisie.r && p.g === choisie.g && p.b === choisie.b) { dedans = true; }
        }
        a.ok(dedans, 'couleur hors palette pour ' + JSON.stringify(cible));
      }
    });

    test('ignore les pixels totalement transparents', function (a) {
      var img = T.imageVide(3, 3, { r: 255, g: 255, b: 255 });
      img.data[3] = 0;   /* pixel (0,0) transparent */
      var moyen = C.echantillonner(img, 0, 0, 0);
      a.egal(moyen, null);
    });
  });
})();
