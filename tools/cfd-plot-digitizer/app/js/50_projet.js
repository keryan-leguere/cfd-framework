/*
 * 50_projet.js — sérialisation d'une session complète.
 *
 * Un projet est un fichier JSON autonome : il embarque l'image en data URL,
 * la calibration et les séries. On peut donc le poser sur une clé USB, le
 * rouvrir sur une machine hors réseau et retrouver exactement l'état de travail.
 *
 * Choix structurant : les points sont stockés en COORDONNÉES PIXEL, pas en
 * unités physiques. Si l'utilisateur s'aperçoit après coup qu'il a saisi 10 au
 * lieu de 100 sur un repère, il corrige la calibration et toutes les séries
 * suivent, sans avoir à repointer quoi que ce soit.
 */
(function (racine) {
  'use strict';

  var CFDD = racine.CFDD || (racine.CFDD = {});
  var Base = CFDD.Base;
  var Projet = {};

  Projet.FORMAT = 'cfd-plot-digitizer/projet';
  Projet.VERSION_FORMAT = 1;

  /*
   * etat : {
   *   image: {nom, dataURL, largeur, hauteur},
   *   calibration: {reperes, logX, logY},
   *   zone: {x0,y0,x1,y1} | null,
   *   series: [{nom, couleurHex, points:[{px,py}], detection:{...}}],
   *   notes: string
   * }
   */
  Projet.serialiser = function (etat, options) {
    options = options || {};
    var inclureImage = options.inclureImage !== false;

    var image = etat.image || null;
    return JSON.stringify({
      format: Projet.FORMAT,
      versionFormat: Projet.VERSION_FORMAT,
      versionOutil: CFDD.VERSION,
      cree: new Date().toISOString(),
      image: image ? {
        nom: image.nom || null,
        largeur: image.largeur,
        hauteur: image.hauteur,
        dataURL: inclureImage ? (image.dataURL || null) : null
      } : null,
      calibration: etat.calibration ? {
        reperes: etat.calibration.reperes || null,
        logX: !!etat.calibration.logX,
        logY: !!etat.calibration.logY
      } : null,
      zone: etat.zone || null,
      series: (etat.series || []).map(function (s) {
        return {
          nom: s.nom,
          couleurHex: s.couleurHex || null,
          /* Forme et taille du marqueur : purement visuel, mais c'est le
             réglage qui rend une planche à quatre séries relisible, et le
             reperdre à chaque réouverture serait pénible. */
          marqueur: s.marqueur || null,
          detection: s.detection || null,
          /* Arrondi au centième de pixel : bien au-delà du pointage humain,
             et divise par deux la taille du fichier. */
          points: (s.points || []).map(function (p) {
            return [Math.round(p.px * 100) / 100, Math.round(p.py * 100) / 100];
          })
        };
      }),
      notes: etat.notes || ''
    }, null, 2) + '\n';
  };

  /*
   * Relit un projet. Lève une Error explicite plutôt que de produire un état
   * à moitié valide : mieux vaut un message clair qu'une courbe fausse.
   */
  Projet.deserialiser = function (texte) {
    var brut;
    try {
      brut = (typeof texte === 'string') ? JSON.parse(texte) : texte;
    } catch (e) {
      throw new Error('Fichier illisible : ce n’est pas du JSON valide.');
    }
    if (!brut || typeof brut !== 'object') {
      throw new Error('Fichier illisible : contenu inattendu.');
    }
    if (brut.format !== Projet.FORMAT) {
      throw new Error('Ce fichier n’est pas un projet cfd-plot-digitizer.');
    }
    if (!(brut.versionFormat <= Projet.VERSION_FORMAT)) {
      throw new Error('Projet en version ' + brut.versionFormat
        + ', trop récent pour cette version de l’outil (max '
        + Projet.VERSION_FORMAT + ').');
    }

    var etat = {
      image: null,
      calibration: null,
      zone: brut.zone || null,
      series: [],
      notes: brut.notes || ''
    };

    if (brut.image) {
      etat.image = {
        nom: brut.image.nom || null,
        largeur: brut.image.largeur,
        hauteur: brut.image.hauteur,
        dataURL: brut.image.dataURL || null
      };
    }

    if (brut.calibration && brut.calibration.reperes) {
      etat.calibration = {
        reperes: brut.calibration.reperes,
        logX: !!brut.calibration.logX,
        logY: !!brut.calibration.logY
      };
    }

    var series = Array.isArray(brut.series) ? brut.series : [];
    for (var i = 0; i < series.length; i++) {
      var s = series[i];
      var points = [];
      var brutPoints = Array.isArray(s.points) ? s.points : [];
      for (var j = 0; j < brutPoints.length; j++) {
        var p = brutPoints[j];
        /* Tolère les deux écritures : [px, py] et {px, py}. */
        var px = Array.isArray(p) ? p[0] : p.px;
        var py = Array.isArray(p) ? p[1] : p.py;
        if (Base.estFini(px) && Base.estFini(py)) { points.push({ px: px, py: py }); }
      }
      etat.series.push({
        nom: s.nom || ('Série ' + (i + 1)),
        couleurHex: s.couleurHex || null,
        marqueur: s.marqueur || null,
        detection: s.detection || null,
        points: points
      });
    }

    return etat;
  };

  /*
   * Convertit les séries pixel en séries physiques via une calibration.
   * Les points hors domaine d'un axe logarithmique sont écartés : 10^u est
   * toujours défini, mais un point détecté au-dessus de l'axe n'a pas de sens.
   */
  Projet.seriesEnDonnees = function (series, cal) {
    return (series || []).map(function (s) {
      var points = [];
      for (var i = 0; i < s.points.length; i++) {
        var d = cal.versDonnees(s.points[i].px, s.points[i].py);
        if (Base.estFini(d.x) && Base.estFini(d.y)) { points.push(d); }
      }
      return { nom: s.nom, couleurHex: s.couleurHex, points: points };
    });
  };

  CFDD.Projet = Projet;
  if (typeof module !== 'undefined' && module.exports) { module.exports = Projet; }
})(typeof globalThis !== 'undefined' ? globalThis : this);
