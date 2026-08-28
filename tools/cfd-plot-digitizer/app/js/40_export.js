/*
 * 40_export.js — mise en forme des séries extraites.
 *
 * Une « série » ici : {nom, couleurHex, points: [{x, y}]} en unités physiques.
 * Aucun accès au DOM : ce module produit des chaînes, l'interface se charge de
 * les télécharger ou de les copier.
 */
(function (racine) {
  'use strict';

  var CFDD = racine.CFDD || (racine.CFDD = {});
  var Base = CFDD.Base;
  var Export = {};

  Export.FORMATS = ['csv-long', 'csv-large', 'json', 'python', 'matlab', 'colonnes'];

  Export.DEFAUTS = {
    separateur: ',',
    decimales: 6,
    entetes: true,
    nomX: 'x',
    nomY: 'y'
  };

  function fusionner(options) {
    var o = {};
    for (var cle in Export.DEFAUTS) {
      if (Object.prototype.hasOwnProperty.call(Export.DEFAUTS, cle)) {
        o[cle] = (options && options[cle] !== undefined) ? options[cle] : Export.DEFAUTS[cle];
      }
    }
    return o;
  }

  /*
   * Échappement CSV (RFC 4180) : nécessaire dès que le nom d'une série contient
   * le séparateur, un guillemet ou un retour à la ligne.
   */
  function champCSV(texte, separateur) {
    var t = String(texte);
    if (t.indexOf(separateur) === -1 && t.indexOf('"') === -1
        && t.indexOf('\n') === -1 && t.indexOf('\r') === -1) {
      return t;
    }
    return '"' + t.replace(/"/g, '""') + '"';
  }

  /*
   * Format long : une ligne par point, colonne « serie » en tête.
   * C'est le format à privilégier pour pandas / R : il supporte des séries de
   * longueurs différentes sans trou.
   */
  Export.versCSVLong = function (series, options) {
    var o = fusionner(options);
    var lignes = [];
    if (o.entetes) {
      lignes.push([champCSV('serie', o.separateur), o.nomX, o.nomY].join(o.separateur));
    }
    for (var i = 0; i < series.length; i++) {
      var s = series[i];
      for (var j = 0; j < s.points.length; j++) {
        lignes.push([
          champCSV(s.nom, o.separateur),
          Base.formaterNombre(s.points[j].x, o.decimales),
          Base.formaterNombre(s.points[j].y, o.decimales)
        ].join(o.separateur));
      }
    }
    return lignes.join('\n') + '\n';
  };

  /*
   * Format large : deux colonnes (x, y) par série, côte à côte.
   * Les séries plus courtes sont complétées par des champs vides.
   */
  Export.versCSVLarge = function (series, options) {
    var o = fusionner(options);
    var i, j;
    var maxPoints = 0;
    for (i = 0; i < series.length; i++) {
      maxPoints = Math.max(maxPoints, series[i].points.length);
    }

    var lignes = [];
    if (o.entetes) {
      var entete = [];
      for (i = 0; i < series.length; i++) {
        entete.push(champCSV(series[i].nom + '_' + o.nomX, o.separateur));
        entete.push(champCSV(series[i].nom + '_' + o.nomY, o.separateur));
      }
      lignes.push(entete.join(o.separateur));
    }

    for (j = 0; j < maxPoints; j++) {
      var cellules = [];
      for (i = 0; i < series.length; i++) {
        var p = series[i].points[j];
        cellules.push(p ? Base.formaterNombre(p.x, o.decimales) : '');
        cellules.push(p ? Base.formaterNombre(p.y, o.decimales) : '');
      }
      lignes.push(cellules.join(o.separateur));
    }
    return lignes.join('\n') + '\n';
  };

  Export.versJSON = function (series, options) {
    var o = fusionner(options);
    var sortie = {
      outil: 'cfd-plot-digitizer',
      version: CFDD.VERSION,
      series: series.map(function (s) {
        return {
          nom: s.nom,
          couleur: s.couleurHex || null,
          points: s.points.map(function (p) {
            return [
              Number(Base.formaterNombre(p.x, o.decimales)),
              Number(Base.formaterNombre(p.y, o.decimales))
            ];
          })
        };
      })
    };
    return JSON.stringify(sortie, null, 2) + '\n';
  };

  /* Identifiant Python/MATLAB valide derive du nom de serie. */
  function identifiant(nom, defaut) {
    var t = String(nom === undefined || nom === null ? '' : nom);
    /* Decomposition NFD puis suppression des diacritiques : « debit » plutot
       que « d_bit ». String.normalize existe partout depuis ES6. */
    if (t.normalize) {
      t = t.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    }
    t = t.replace(/[^A-Za-z0-9_]/g, '_').replace(/_+/g, '_').replace(/^_+|_+$/g, '');
    if (!t || /^[0-9]/.test(t)) { t = defaut + (t ? '_' + t : ''); }
    return t;
  }

  Export.versPython = function (series, options) {
    var o = fusionner(options);
    var lignes = ['import numpy as np', ''];
    var utilises = {};
    for (var i = 0; i < series.length; i++) {
      var nom = identifiant(series[i].nom, 'serie_' + (i + 1));
      /* Deux séries peuvent porter le même nom : on désambiguïse. */
      while (utilises[nom]) { nom = nom + '_'; }
      utilises[nom] = true;

      var x = [], y = [];
      for (var j = 0; j < series[i].points.length; j++) {
        x.push(Base.formaterNombre(series[i].points[j].x, o.decimales));
        y.push(Base.formaterNombre(series[i].points[j].y, o.decimales));
      }
      lignes.push('# ' + series[i].nom + ' (' + series[i].points.length + (series[i].points.length > 1 ? ' points)' : ' point)'));
      lignes.push(nom + '_x = np.array([' + x.join(', ') + '])');
      lignes.push(nom + '_y = np.array([' + y.join(', ') + '])');
      lignes.push('');
    }
    return lignes.join('\n');
  };

  Export.versMatlab = function (series, options) {
    var o = fusionner(options);
    var lignes = [];
    var utilises = {};
    for (var i = 0; i < series.length; i++) {
      var nom = identifiant(series[i].nom, 'serie_' + (i + 1));
      while (utilises[nom]) { nom = nom + '_'; }
      utilises[nom] = true;

      var x = [], y = [];
      for (var j = 0; j < series[i].points.length; j++) {
        x.push(Base.formaterNombre(series[i].points[j].x, o.decimales));
        y.push(Base.formaterNombre(series[i].points[j].y, o.decimales));
      }
      lignes.push('% ' + series[i].nom + ' (' + series[i].points.length + (series[i].points.length > 1 ? ' points)' : ' point)'));
      lignes.push(nom + '_x = [' + x.join(' ') + '];');
      lignes.push(nom + '_y = [' + y.join(' ') + '];');
      lignes.push('');
    }
    return lignes.join('\n');
  };

  /* Deux colonnes séparées par une tabulation : à coller dans un tableur. */
  Export.versColonnes = function (series, options) {
    var o = fusionner(options);
    var blocs = [];
    for (var i = 0; i < series.length; i++) {
      var lignes = [];
      if (series.length > 1) { lignes.push('# ' + series[i].nom); }
      for (var j = 0; j < series[i].points.length; j++) {
        lignes.push(Base.formaterNombre(series[i].points[j].x, o.decimales)
          + '\t' + Base.formaterNombre(series[i].points[j].y, o.decimales));
      }
      blocs.push(lignes.join('\n'));
    }
    return blocs.join('\n\n') + '\n';
  };

  Export.rendre = function (format, series, options) {
    switch (format) {
      case 'csv-long': return Export.versCSVLong(series, options);
      case 'csv-large': return Export.versCSVLarge(series, options);
      case 'json': return Export.versJSON(series, options);
      case 'python': return Export.versPython(series, options);
      case 'matlab': return Export.versMatlab(series, options);
      case 'colonnes': return Export.versColonnes(series, options);
      default: throw new Error('Format inconnu : ' + format);
    }
  };

  Export.extension = function (format) {
    switch (format) {
      case 'csv-long': case 'csv-large': return 'csv';
      case 'json': return 'json';
      case 'python': return 'py';
      case 'matlab': return 'm';
      default: return 'txt';
    }
  };

  CFDD.Export = Export;
  if (typeof module !== 'undefined' && module.exports) { module.exports = Export; }
})(typeof globalThis !== 'undefined' ? globalThis : this);
