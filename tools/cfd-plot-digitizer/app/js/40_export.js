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

  Export.FORMATS = ['csv-long', 'csv-large', 'csv-grille', 'json', 'python',
                    'matlab', 'colonnes'];

  Export.DEFAUTS = {
    separateur: ',',
    decimales: 6,
    entetes: true,
    nomX: 'x',
    nomY: 'y',
    /* Ré-échantillonnage sur une grille X commune (format « csv-grille »). */
    grillePoints: 200,
    grilleEspacement: 'lineaire',   /* 'lineaire' | 'log' */
    grilleDomaine: 'intersection'   /* 'intersection' | 'union' */
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

  /* --- Grille X commune --------------------------------------------- */

  /*
   * Interpolation linéaire de (xs, ys) en x. Les tableaux sont supposés triés
   * par x croissant. Rend null hors du domaine : extrapoler une courbe
   * digitalisée serait inventer des données que l'image ne contient pas.
   */
  function interpoler(xs, ys, x) {
    var n = xs.length;
    if (x < xs[0] || x > xs[n - 1]) { return null; }
    var lo = 0, hi = n - 1;
    while (hi - lo > 1) {
      var mid = (lo + hi) >> 1;
      if (xs[mid] <= x) { lo = mid; } else { hi = mid; }
    }
    var largeur = xs[hi] - xs[lo];
    if (largeur === 0) { return ys[lo]; }
    return ys[lo] + (x - xs[lo]) * (ys[hi] - ys[lo]) / largeur;
  }

  /*
   * Une série est-elle une fonction de x ?
   *
   * Question loin d'être formelle : une POLAIRE Cz(Cx) est un arc couché, où un
   * même Cx porte deux Cz. La ré-échantillonner en x reviendrait à écraser ses
   * deux branches l'une sur l'autre — silencieusement, et le tableau produit
   * aurait l'air parfaitement normal.
   *
   * Compter les changements de sens en x ne suffit pas : une courbe repliée
   * proprement n'en compte qu'UN, qu'une tolérance au bruit avalerait. Ce qui
   * distingue les deux cas est la LONGUEUR des passages monotones. Le bruit de
   * détection produit une nuée d'allers-retours d'une fraction de pixel ; un
   * vrai repli produit deux parcours étendus, chacun couvrant une bonne part
   * de l'étendue en x.
   *
   * On mesure donc l'étendue de chaque passage monotone et l'on compte ceux qui
   * pèsent au moins 5 % de l'étendue totale. Deux passages significatifs ou
   * plus : la courbe est repliée.
   */
  function estFonctionDeX(points) {
    var minX = Infinity, maxX = -Infinity;
    var i;
    for (i = 0; i < points.length; i++) {
      if (points[i].x < minX) { minX = points[i].x; }
      if (points[i].x > maxX) { maxX = points[i].x; }
    }
    var etendue = maxX - minX;
    if (!(etendue > 0)) { return { passages: 0, fonction: false }; }

    var passages = [];
    var sens = 0;
    var depart = points[0].x;
    var dernier = points[0].x;

    for (i = 1; i < points.length; i++) {
      var d = points[i].x - points[i - 1].x;
      if (d === 0) { continue; }
      var s = (d > 0) ? 1 : -1;
      if (sens === 0) {
        sens = s;
      } else if (s !== sens) {
        passages.push(Math.abs(dernier - depart));
        depart = points[i - 1].x;
        sens = s;
      }
      dernier = points[i].x;
    }
    passages.push(Math.abs(dernier - depart));

    var significatifs = 0;
    for (i = 0; i < passages.length; i++) {
      if (passages[i] >= etendue * 0.05) { significatifs++; }
    }
    return { passages: significatifs, fonction: significatifs <= 1 };
  }

  /* Trie par x croissant et fond les abscisses identiques en leur moyenne. */
  function preparer(points) {
    var tri = points.slice().sort(function (a, b) { return a.x - b.x; });
    var xs = [], ys = [];
    var i = 0;
    while (i < tri.length) {
      var x = tri[i].x, somme = 0, n = 0;
      while (i < tri.length && tri[i].x === x) { somme += tri[i].y; n++; i++; }
      xs.push(x); ys.push(somme / n);
    }
    return { xs: xs, ys: ys };
  }

  /*
   * Ramène toutes les séries sur une seule grille d'abscisses.
   *
   * Retourne {x, colonnes: [{nom, y}], bornes, avertissements}. Les valeurs
   * hors du domaine propre d'une série valent null — jamais une extrapolation.
   */
  Export.reechantillonner = function (series, options) {
    var o = fusionner(options);
    var avertissements = [];
    var preparees = [];
    var i;

    for (i = 0; i < series.length; i++) {
      var s = series[i];
      var points = (s.points || []).filter(function (p) {
        return Base.estFini(p.x) && Base.estFini(p.y);
      });
      if (points.length < 2) {
        avertissements.push('« ' + s.nom + ' » : moins de deux points, série écartée.');
        continue;
      }
      var forme = estFonctionDeX(points);
      if (!forme.fonction) {
        avertissements.push('« ' + s.nom + ' » : courbe repliée en x ('
          + forme.passages + ' passages monotones) — un même x y porte '
          + 'plusieurs y, elle ne peut pas être ré-échantillonnée en x. '
          + 'Série écartée.');
        continue;
      }
      var pret = preparer(points);
      preparees.push({ nom: s.nom, xs: pret.xs, ys: pret.ys });
    }

    if (!preparees.length) {
      return { x: [], colonnes: [], bornes: null, avertissements: avertissements };
    }

    var bas, haut;
    if (o.grilleDomaine === 'union') {
      bas = Infinity; haut = -Infinity;
      for (i = 0; i < preparees.length; i++) {
        bas = Math.min(bas, preparees[i].xs[0]);
        haut = Math.max(haut, preparees[i].xs[preparees[i].xs.length - 1]);
      }
    } else {
      bas = -Infinity; haut = Infinity;
      for (i = 0; i < preparees.length; i++) {
        bas = Math.max(bas, preparees[i].xs[0]);
        haut = Math.min(haut, preparees[i].xs[preparees[i].xs.length - 1]);
      }
      if (bas >= haut) {
        avertissements.push('Les séries ne se recouvrent pas en x : '
          + 'aucune grille commune possible. Essayer le domaine « union ».');
        return { x: [], colonnes: [], bornes: null, avertissements: avertissements };
      }
    }

    var log = (o.grilleEspacement === 'log');
    if (log && bas <= 0) {
      avertissements.push('Grille logarithmique impossible avec des abscisses '
        + '≤ 0 : espacement linéaire utilisé.');
      log = false;
    }

    var nb = Math.max(2, Math.round(o.grillePoints));
    var x = [];
    var a = log ? Math.log(bas) / Math.LN10 : bas;
    var b = log ? Math.log(haut) / Math.LN10 : haut;
    for (i = 0; i < nb; i++) {
      var u = a + (b - a) * i / (nb - 1);
      x.push(log ? Math.pow(10, u) : u);
    }

    var colonnes = [];
    for (i = 0; i < preparees.length; i++) {
      var y = [];
      for (var k = 0; k < x.length; k++) {
        y.push(interpoler(preparees[i].xs, preparees[i].ys, x[k]));
      }
      colonnes.push({ nom: preparees[i].nom, y: y });
    }

    return {
      x: x, colonnes: colonnes,
      bornes: { bas: bas, haut: haut, log: log },
      avertissements: avertissements
    };
  };

  /*
   * CSV à abscisse partagée : une colonne x, puis une colonne par série.
   * C'est la forme qu'attend un tableur pour superposer des courbes, et celle
   * qu'il faut pour retrancher deux courbes l'une de l'autre — impossible tant
   * que chacune a ses propres abscisses.
   */
  Export.versCSVGrille = function (series, options) {
    var o = fusionner(options);
    var grille = Export.reechantillonner(series, options);
    var lignes = [];
    var i, k;

    if (o.entetes) {
      var entete = [o.nomX];
      for (i = 0; i < grille.colonnes.length; i++) {
        entete.push(champCSV(grille.colonnes[i].nom, o.separateur));
      }
      lignes.push(entete.join(o.separateur));
    }

    for (k = 0; k < grille.x.length; k++) {
      var cellules = [Base.formaterNombre(grille.x[k], o.decimales)];
      for (i = 0; i < grille.colonnes.length; i++) {
        var v = grille.colonnes[i].y[k];
        cellules.push(v === null ? '' : Base.formaterNombre(v, o.decimales));
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

  /* --- Description des formats ---------------------------------------
   *
   * Le choix du format est le seul endroit de l'outil où l'utilisateur doit
   * deviner ce qu'il va obtenir. Ces fiches — un résumé, ce à quoi ça sert, et
   * trois lignes du rendu réel — vivent ici plutôt que dans le HTML : c'est le
   * module qui sait ce qu'il produit, et l'exemple reste ainsi à côté du code
   * qui l'écrit.
   *
   *   separateur / decimales : le réglage s'applique-t-il à ce format ?
   *     Les masquer ailleurs évite de faire tourner un bouton sans effet.
   */
  Export.DESCRIPTIONS = {
    'csv-long': {
      titre: 'CSV — format long',
      resume: 'Une ligne par point, le nom de la série en première colonne.',
      usage: 'Le format à donner à pandas ou R. Seul à accepter sans trou des '
        + 'séries de longueurs différentes.',
      exemple: 'serie,x,y\nCz(alpha),0.5,0.128\nCz(alpha),1.0,0.214',
      extension: 'csv', separateur: true, decimales: true
    },
    'csv-large': {
      titre: 'CSV — colonnes par série',
      resume: 'Deux colonnes (x, y) par série, côte à côte.',
      usage: 'À ouvrir dans un tableur pour tracer directement. Les séries '
        + 'courtes laissent des cellules vides en bas.',
      exemple: 'Cz_x,Cz_y,Cx_x,Cx_y\n0.5,0.128,0.5,0.011\n1.0,0.214,1.0,0.013',
      extension: 'csv', separateur: true, decimales: true
    },
    'csv-grille': {
      titre: 'CSV — grille X commune',
      resume: 'Toutes les séries interpolées sur une seule abscisse.',
      usage: 'La forme qu’il faut pour superposer ou soustraire deux courbes '
        + 'digitalisées séparément — elles ne partagent jamais leurs abscisses.',
      exemple: 'x,Cz,Cx\n0.50,0.128,0.011\n0.75,0.171,0.012',
      extension: 'csv', separateur: true, decimales: true
    },
    colonnes: {
      titre: 'Texte — deux colonnes',
      resume: 'x et y séparés par une tabulation, un bloc par série.',
      usage: 'À coller tel quel dans un tableur ou un fichier d’entrée de '
        + 'solveur. Aucun en-tête à retirer.',
      exemple: '# Cz(alpha)\n0.5\t0.128\n1.0\t0.214',
      extension: 'txt', separateur: false, decimales: true
    },
    json: {
      titre: 'JSON',
      resume: 'Structure complète : nom, couleur et points de chaque série.',
      usage: 'Pour un script qui relit les séries en gardant leurs noms.',
      exemple: '{\n  "series": [\n    {"nom": "Cz", "points": [[0.5, 0.128]]}',
      extension: 'json', separateur: false, decimales: true
    },
    python: {
      titre: 'Python / NumPy',
      resume: 'Un tableau np.array par série, prêt à coller.',
      usage: 'Pour un notebook ou un script de tracé. Les noms de séries sont '
        + 'transformés en identifiants valides.',
      exemple: 'import numpy as np\n\ncz_x = np.array([0.5, 1.0])\ncz_y = np.array([0.128, 0.214])',
      extension: 'py', separateur: false, decimales: true
    },
    matlab: {
      titre: 'MATLAB / Octave',
      resume: 'Un vecteur ligne par série.',
      usage: 'À coller dans un script .m ou directement dans la console.',
      exemple: '% Cz(alpha)\ncz_x = [0.5 1.0];\ncz_y = [0.128 0.214];',
      extension: 'm', separateur: false, decimales: true
    }
  };

  Export.description = function (format) {
    return Object.prototype.hasOwnProperty.call(Export.DESCRIPTIONS, format)
      ? Export.DESCRIPTIONS[format] : null;
  };

  /*
   * Ce que l'export contiendra, avant de le produire : de quoi vérifier d'un
   * coup d'œil qu'on exporte bien ce qu'on croit — la bonne étendue, le bon
   * nombre de séries — plutôt que de le découvrir dans le fichier écrit.
   */
  Export.bilan = function (series) {
    var nbPoints = 0;
    var xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity;
    for (var i = 0; i < (series || []).length; i++) {
      var pts = series[i].points || [];
      nbPoints += pts.length;
      for (var j = 0; j < pts.length; j++) {
        if (pts[j].x < xMin) { xMin = pts[j].x; }
        if (pts[j].x > xMax) { xMax = pts[j].x; }
        if (pts[j].y < yMin) { yMin = pts[j].y; }
        if (pts[j].y > yMax) { yMax = pts[j].y; }
      }
    }
    return {
      nbSeries: (series || []).length,
      nbPoints: nbPoints,
      x: nbPoints ? { min: xMin, max: xMax } : null,
      y: nbPoints ? { min: yMin, max: yMax } : null
    };
  };

  Export.rendre = function (format, series, options) {
    switch (format) {
      case 'csv-long': return Export.versCSVLong(series, options);
      case 'csv-large': return Export.versCSVLarge(series, options);
      case 'csv-grille': return Export.versCSVGrille(series, options);
      case 'json': return Export.versJSON(series, options);
      case 'python': return Export.versPython(series, options);
      case 'matlab': return Export.versMatlab(series, options);
      case 'colonnes': return Export.versColonnes(series, options);
      default: throw new Error('Format inconnu : ' + format);
    }
  };

  Export.extension = function (format) {
    var d = Export.description(format);
    return d ? d.extension : 'txt';
  };

  CFDD.Export = Export;
  if (typeof module !== 'undefined' && module.exports) { module.exports = Export; }
})(typeof globalThis !== 'undefined' ? globalThis : this);
