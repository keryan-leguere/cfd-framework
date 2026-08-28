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

    test('construit un calque de masque aux bonnes dimensions', function (a) {
      /* Faux canevas : on ne vérifie ici que la géométrie et le remplissage. */
      var pose = null;
      function fabriquer(l, h) {
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
      }
      var info = {
        largeurZone: 3, hauteurZone: 2,
        masque: new Uint8Array([1, 0, 0, 0, 0, 1])
      };
      var c = CFDD.Vue.calqueMasque(info, { r: 255, g: 0, b: 0 }, fabriquer);
      a.egal(c.width, 3); a.egal(c.height, 2);
      a.egal(pose.data[3], 255, 'premier pixel opaque');
      a.egal(pose.data[7], 0, 'deuxième pixel transparent');
      a.egal(pose.data[5 * 4 + 3], 255, 'dernier pixel opaque');
    });
  });
})();
