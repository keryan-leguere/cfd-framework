(function () {
  'use strict';
  var T = globalThis.CFDD.Tests, V = globalThis.CFDD.Vue;

  T.suite('Vue — cadrage et zoom', function (test) {

    test('fait l’aller-retour écran <-> image', function (a) {
      var vue = { echelle: 2.5, dx: 30, dy: -12 };
      var e = V.versEcran(vue, 100, 200);
      a.proche(e.cx, 280, 1e-12); a.proche(e.cy, 488, 1e-12);
      var r = V.versImage(vue, e.cx, e.cy);
      a.proche(r.px, 100, 1e-12); a.proche(r.py, 200, 1e-12);
    });

    test('ajuste et centre une image large', function (a) {
      /* Image 800x400 dans un canevas 400x400 : c'est la largeur qui contraint. */
      var vue = V.ajuster(800, 400, 400, 400, 0);
      a.proche(vue.echelle, 0.5, 1e-12);
      a.proche(vue.dx, 0, 1e-12);
      a.proche(vue.dy, 100, 1e-12, 'centrée verticalement');
    });

    test('ajuste en tenant compte de la marge', function (a) {
      var vue = V.ajuster(100, 100, 200, 200, 20);
      a.proche(vue.echelle, 1.6, 1e-12);
      a.proche(vue.dx, 20, 1e-12);
    });

    test('le zoom laisse immobile le pixel sous le curseur', function (a) {
      var vue = { echelle: 1, dx: 0, dy: 0 };
      var avant = V.versImage(vue, 300, 150);
      var apres = V.zoomerAutour(vue, 300, 150, 2.5);
      var e = V.versEcran(apres, avant.px, avant.py);
      a.proche(e.cx, 300, 1e-9);
      a.proche(e.cy, 150, 1e-9);
      a.proche(apres.echelle, 2.5, 1e-12);
    });

    test('le zoom reste dans les bornes', function (a) {
      var vue = { echelle: V.ECHELLE_MAX, dx: 0, dy: 0 };
      var apres = V.zoomerAutour(vue, 10, 10, 4);
      a.egal(apres.echelle, V.ECHELLE_MAX, 'saturé en haut');
      /* Saturé, la vue ne doit pas non plus se décaler. */
      a.egal(apres.dx, 0); a.egal(apres.dy, 0);

      var bas = V.zoomerAutour({ echelle: V.ECHELLE_MIN, dx: 5, dy: 5 }, 10, 10, 0.1);
      a.egal(bas.echelle, V.ECHELLE_MIN);
      a.egal(bas.dx, 5);
    });

    test('zoomer puis dézoomer d’autant revient au point de départ', function (a) {
      var vue = { echelle: 1.3, dx: 17, dy: -4 };
      var aller = V.zoomerAutour(vue, 220, 90, 2);
      var retour = V.zoomerAutour(aller, 220, 90, 0.5);
      a.proche(retour.echelle, vue.echelle, 1e-12);
      a.proche(retour.dx, vue.dx, 1e-9);
      a.proche(retour.dy, vue.dy, 1e-9);
    });

    test('le déplacement est une translation pure', function (a) {
      var vue = V.deplacer({ echelle: 3, dx: 10, dy: 20 }, -5, 7);
      a.egal(vue.echelle, 3); a.egal(vue.dx, 5); a.egal(vue.dy, 27);
    });

    test('la contrainte garde toujours l’image visible', function (a) {
      /* Image 100x100 à l'échelle 1, canevas 500x500, poussée très loin. */
      var vue = V.contraindre({ echelle: 1, dx: 100000, dy: -100000 },
        100, 100, 500, 500, 40);
      a.egal(vue.dx, 460, 'bloquée avant de sortir par la droite');
      a.egal(vue.dy, -60, 'bloquée avant de sortir par le haut');

      /* Une vue déjà correcte n'est pas touchée. */
      var libre = V.contraindre({ echelle: 1, dx: 50, dy: 50 }, 100, 100, 500, 500, 40);
      a.egal(libre.dx, 50); a.egal(libre.dy, 50);
    });

    /*
     * Faux canevas : on ne vérifie ici que la géométrie et le remplissage du
     * calque, pas le rendu, qui relève du navigateur.
     */
    function fauxCanevas() {
      var pose = null;
      var fabriquer = function (l, h) {
        return {
          width: l, height: h,
          getContext: function () {
            return {
              createImageData: function (w, hh) {
                return { data: new Uint8ClampedArray(w * hh * 4), width: w, height: hh };
              },
              putImageData: function (img) { pose = img; }
            };
          }
        };
      };
      fabriquer.pose = function () { return pose; };
      return fabriquer;
    }

    /* Masque 3x2 : deux pixels retenus, aux deux coins opposés. */
    function infoTest() {
      return {
        largeurZone: 3, hauteurZone: 2,
        masque: new Uint8Array([1, 0, 0, 0, 0, 1])
      };
    }

    test('construit un calque de masque aux bonnes dimensions', function (a) {
      var fabriquer = fauxCanevas();
      var c = V.calqueMasque(infoTest(), { couleur: { r: 255, g: 0, b: 0 } }, fabriquer);
      a.egal(c.width, 3); a.egal(c.height, 2);
      var d = fabriquer.pose().data;
      a.egal(d[3], 255, 'premier pixel opaque');
      a.egal(d[0], 255, 'peint dans la couleur demandée');
      a.egal(d[7], 0, 'deuxième pixel transparent');
      a.egal(d[5 * 4 + 3], 255, 'dernier pixel opaque');
    });

    test('le mode « isoler » voile les pixels écartés et non les retenus', function (a) {
      var fabriquer = fauxCanevas();
      V.calqueMasque(infoTest(),
        { mode: V.MODES_MASQUE.isoler, voile: { r: 10, g: 20, b: 30 }, opaciteVoile: 200 },
        fabriquer);
      var d = fabriquer.pose().data;
      /* Retenu : transparent, pour laisser voir sa vraie couleur. */
      a.egal(d[3], 0, 'pixel retenu laissé transparent');
      /* Écarté : voilé. */
      a.egal(d[1 * 4 + 3], 200, 'pixel écarté voilé');
      a.egal(d[1 * 4], 10, 'couleur du voile');
    });

    test('le mode « les-deux » peint les retenus et voile le reste', function (a) {
      var fabriquer = fauxCanevas();
      V.calqueMasque(infoTest(),
        { mode: V.MODES_MASQUE.lesDeux, couleur: { r: 0, g: 255, b: 0 }, opaciteVoile: 150 },
        fabriquer);
      var d = fabriquer.pose().data;
      a.egal(d[3], 255, 'retenu peint');
      a.egal(d[1], 255, 'en vert');
      a.egal(d[1 * 4 + 3], 150, 'écarté voilé');
    });

    test('l’épaississement rend visible un trait d’un pixel', function (a) {
      /*
       * À l'échelle 0,4 un trait d'un pixel ne couvre plus un pixel d'écran et
       * l'aperçu paraît troué alors que le masque est intact. La dilatation ne
       * touche que l'affichage.
       */
      var fabriquer = fauxCanevas();
      var info = { largeurZone: 3, hauteurZone: 3, masque: new Uint8Array([0, 0, 0, 0, 1, 0, 0, 0, 0]) };
      V.calqueMasque(info, { couleur: { r: 255, g: 0, b: 255 }, epaissir: 1 }, fabriquer);
      var d = fabriquer.pose().data;
      /* Le centre et ses quatre voisins directs sont peints, les coins non. */
      a.egal(d[4 * 4 + 3], 255, 'centre');
      a.egal(d[1 * 4 + 3], 255, 'voisin du haut');
      a.egal(d[3 * 4 + 3], 255, 'voisin de gauche');
      a.egal(d[5 * 4 + 3], 255, 'voisin de droite');
      a.egal(d[7 * 4 + 3], 255, 'voisin du bas');
      a.egal(d[0 * 4 + 3], 0, 'coin non peint (dilatation en 4-connexité)');
    });

    test('sans épaississement, seuls les pixels du masque sont peints', function (a) {
      var fabriquer = fauxCanevas();
      var info = { largeurZone: 3, hauteurZone: 3, masque: new Uint8Array([0, 0, 0, 0, 1, 0, 0, 0, 0]) };
      V.calqueMasque(info, { couleur: { r: 255, g: 0, b: 255 } }, fabriquer);
      var d = fabriquer.pose().data;
      a.egal(d[4 * 4 + 3], 255);
      a.egal(d[1 * 4 + 3], 0);
    });

  });
})();
