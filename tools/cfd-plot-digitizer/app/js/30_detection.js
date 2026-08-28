/*
 * 30_detection.js — extraction automatique d'une courbe par sa couleur.
 *
 * Chaîne de traitement (détail et illustrations : 00_DOC/02_DETECTION_COULEUR.md)
 *
 *   1. MASQUE     : un booléen par pixel de la zone d'analyse, via le double
 *                   critère chroma/luminance de 10_couleur.js.
 *   2. SEGMENTS   : dans chaque colonne de pixels on repère les suites
 *                   verticales contiguës de pixels retenus. Un trait d'épaisseur
 *                   e traversant la colonne donne un segment de longueur ~e ;
 *                   son centre est le point recherché. Prendre le centre plutôt
 *                   que le premier pixel divise l'erreur par deux et supprime le
 *                   biais systématique vers le haut du trait.
 *   3. SÉLECTION  : trois politiques quand une colonne porte plusieurs segments
 *                   (courbe repliée, marqueurs, croisement) — cf. MODES.
 *   4. ALLÈGEMENT : Douglas-Peucker optionnel, pour ne pas exporter un point
 *                   par pixel là où la courbe est droite.
 *
 * Tout est en coordonnées PIXEL. La conversion en unités physiques est faite
 * par l'appelant via la calibration : garder les pixels permet de recalibrer
 * après coup sans repasser par la détection.
 */
(function (racine) {
  'use strict';

  var CFDD = racine.CFDD || (racine.CFDD = {});
  var Base = CFDD.Base;
  var Couleur = CFDD.Couleur;
  var Trait = CFDD.Trait;
  var Detection = {};

  Detection.MODES = {
    /* Tous les segments de chaque colonne : nuages, courbes repliées. */
    tous: 'tous',
    /* Un point par colonne, moyenne des segments : le mode « fonction ». */
    moyenne: 'moyenne',
    /* Suivi de continuité : la branche la plus proche du point précédent. */
    suivi: 'suivi'
  };

  Detection.DEFAUTS = {
    tolChroma: 20,
    tolLum: 30,
    pas: 1,
    longueurMin: 1,
    longueurMax: 0,        /* 0 = pas de limite */
    mode: 'moyenne',
    orientation: 'colonnes',
    sautMax: 0,            /* mode « suivi » : saut vertical max en pixels ; 0 = auto */
    simplification: 0,     /* tolérance Douglas-Peucker en pixels ; 0 = désactivé */
    filtreTrait: 'tous',   /* 'tous' | 'continu' | 'discontinu' (cf. 25_trait.js) */
    comblerLacunes: 0      /* comble les trous d'un trait discontinu, en pixels */
    /* Deux options rectangulaires viennent en plus, hors valeurs par défaut :
       `zone` (rectangle analysé) et `zonesExclues` (rectangles ignorés). */
  };

  /* Normalise et borne une zone d'analyse sur l'image. */
  Detection.normaliserZone = function (zone, largeur, hauteur) {
    if (!zone) { return { x0: 0, y0: 0, x1: largeur - 1, y1: hauteur - 1 }; }
    var x0 = Math.round(Math.min(zone.x0, zone.x1));
    var x1 = Math.round(Math.max(zone.x0, zone.x1));
    var y0 = Math.round(Math.min(zone.y0, zone.y1));
    var y1 = Math.round(Math.max(zone.y0, zone.y1));
    return {
      x0: Base.borner(x0, 0, largeur - 1),
      x1: Base.borner(x1, 0, largeur - 1),
      y0: Base.borner(y0, 0, hauteur - 1),
      y1: Base.borner(y1, 0, hauteur - 1)
    };
  };

  /*
   * Vrai si (x, y) tombe dans l'un des rectangles d'exclusion.
   *
   * L'exclusion répond au piège le plus courant de la digitalisation
   * automatique : la LÉGENDE. Elle contient des segments de la couleur exacte
   * des courbes, et aucun rectangle d'analyse simple ne peut à la fois couvrir
   * tout le tracé et l'éviter. Les tolérances de couleur, elles, n'y peuvent
   * rien : la couleur est identique.
   */
  function estExclu(exclusions, x, y) {
    for (var i = 0; i < exclusions.length; i++) {
      var e = exclusions[i];
      if (x >= e.x0 && x <= e.x1 && y >= e.y0 && y <= e.y1) { return true; }
    }
    return false;
  }

  Detection.normaliserExclusions = function (liste, largeur, hauteur) {
    if (!liste || !liste.length) { return []; }
    var sortie = [];
    for (var i = 0; i < liste.length; i++) {
      sortie.push(Detection.normaliserZone(liste[i], largeur, hauteur));
    }
    return sortie;
  };

  /*
   * Construit le masque binaire de la zone.
   * Retourne {masque: Uint8Array, zone, largeurZone, hauteurZone, nbRetenus}.
   * Le masque est indexé (y - zone.y0) * largeurZone + (x - zone.x0).
   */
  Detection.construireMasque = function (image, cible, options) {
    options = options || {};
    var zone = Detection.normaliserZone(options.zone, image.width, image.height);
    var exclusions = Detection.normaliserExclusions(
      options.zonesExclues, image.width, image.height);
    var correspondance = Couleur.creerCorrespondance(cible, {
      tolChroma: (options.tolChroma === undefined) ? Detection.DEFAUTS.tolChroma : options.tolChroma,
      tolLum: (options.tolLum === undefined) ? Detection.DEFAUTS.tolLum : options.tolLum
    });

    var largeurZone = zone.x1 - zone.x0 + 1;
    var hauteurZone = zone.y1 - zone.y0 + 1;
    var masque = new Uint8Array(largeurZone * hauteurZone);
    var d = image.data, w = image.width;
    var nbRetenus = 0;

    for (var y = zone.y0; y <= zone.y1; y++) {
      var baseLigne = (y - zone.y0) * largeurZone;
      for (var x = zone.x0; x <= zone.x1; x++) {
        if (exclusions.length && estExclu(exclusions, x, y)) { continue; }
        var i = (y * w + x) * 4;
        /* Un pixel transparent n'est pas une couleur : on l'écarte d'office. */
        if (d[i + 3] < 128) { continue; }
        if (correspondance.correspond(d[i], d[i + 1], d[i + 2])) {
          masque[baseLigne + (x - zone.x0)] = 1;
          nbRetenus++;
        }
      }
    }

    return {
      masque: masque,
      zone: zone,
      largeurZone: largeurZone,
      hauteurZone: hauteurZone,
      nbRetenus: nbRetenus
    };
  };

  Detection.ORIENTATIONS = {
    /* Balayage colonne par colonne : pour une courbe y = f(x). */
    colonnes: 'colonnes',
    /* Balayage ligne par ligne : pour une courbe x = f(y). */
    lignes: 'lignes'
  };

  /*
   * Segments contigus retenus le long d'une ligne de balayage du masque.
   *
   * L'orientation compte plus qu'il n'y paraît. Une polaire Cz(Cx) est un arc
   * couché : à un même Cx correspondent deux Cz. Balayée en colonnes, elle
   * donne deux segments par colonne que le mode « moyenne » réduit à leur
   * milieu — soit une courbe entièrement fausse. Balayée en LIGNES, elle
   * redevient une fonction à une seule valeur et se lit exactement.
   *
   * `indice` est le numéro de colonne (orientation colonnes) ou de ligne
   * (orientation lignes), en coordonnées image.
   */
  Detection.segments = function (info, indice, longueurMin, longueurMax, orientation) {
    var segments = [];
    var parLignes = (orientation === 'lignes');

    /* Repère local : u = axe de balayage, v = axe parcouru. */
    var u = indice - (parLignes ? info.zone.y0 : info.zone.x0);
    var nbV = parLignes ? info.largeurZone : info.hauteurZone;
    if (u < 0 || u >= (parLignes ? info.hauteurZone : info.largeurZone)) { return segments; }

    var origineV = parLignes ? info.zone.x0 : info.zone.y0;
    var debut = -1;

    for (var v = 0; v <= nbV; v++) {
      var actif = (v < nbV) && info.masque[
        parLignes ? (u * info.largeurZone + v) : (v * info.largeurZone + u)
      ] === 1;

      if (actif && debut === -1) {
        debut = v;
      } else if (!actif && debut !== -1) {
        var longueur = v - debut;
        var trop = (longueurMax > 0 && longueur > longueurMax);
        if (longueur >= longueurMin && !trop) {
          segments.push({
            debut: origineV + debut,
            fin: origineV + v - 1,
            longueur: longueur,
            /* Centre géométrique du segment, au centre du pixel. */
            centre: origineV + debut + (longueur - 1) / 2
          });
        }
        debut = -1;
      }
    }
    return segments;
  };

  /*
   * Comble les trous d'une série le long de l'axe de balayage.
   *
   * Un trait en tirets rend une suite de tronçons séparés par des vides ; la
   * courbe sous-jacente, elle, est continue. Interpoler les vides jusqu'à
   * `lacuneMax` restitue une série exploitable — c'est ce qui rend une courbe
   * en tirets utilisable au lieu d'un semis troué.
   *
   * Le plafond est essentiel : sans lui, on relierait aussi les deux bords
   * d'une véritable interruption (courbe masquée par un symbole, sortie du
   * cadre) et l'on inventerait des données. Régler `lacuneMax` un peu au-dessus
   * de la longueur d'espace mesurée par `Trait.mesurer`.
   */
  Detection.comblerLacunes = function (points, pas, lacuneMax, orientation) {
    if (!(lacuneMax > 0) || points.length < 2) { return points.slice(); }
    var parLignes = (orientation === 'lignes');
    var sortie = [points[0]];

    for (var i = 1; i < points.length; i++) {
      var a = points[i - 1], b = points[i];
      var uA = parLignes ? a.py : a.px;
      var uB = parLignes ? b.py : b.px;
      var vA = parLignes ? a.px : a.py;
      var vB = parLignes ? b.px : b.py;
      var ecart = uB - uA;

      if (ecart > pas && ecart <= lacuneMax) {
        var n = Math.max(2, Math.round(ecart / pas));
        for (var k = 1; k < n; k++) {
          var t = k / n;
          var u = uA + t * ecart;
          var v = vA + t * (vB - vA);
          sortie.push(parLignes ? { px: v, py: u } : { px: u, py: v });
        }
      }
      sortie.push(b);
    }
    return sortie;
  };

  /*
   * Détection complète.
   *
   * image   : {data: Uint8ClampedArray RGBA, width, height}
   * cible   : {r,g,b}
   * options : cf. Detection.DEFAUTS + {zone}
   *
   * Retourne {points: [{px,py}], masqueInfo, statistiques}.
   */
  Detection.detecter = function (image, cible, options) {
    var o = {};
    var cle;
    for (cle in Detection.DEFAUTS) {
      if (Object.prototype.hasOwnProperty.call(Detection.DEFAUTS, cle)) {
        o[cle] = (options && options[cle] !== undefined) ? options[cle] : Detection.DEFAUTS[cle];
      }
    }
    o.zone = options ? options.zone : null;
    o.zonesExclues = options ? options.zonesExclues : null;

    var parLignes = (o.orientation === 'lignes');
    var pas = Math.max(1, Math.round(o.pas));
    var info = Detection.construireMasque(image, cible, o);

    /*
     * Analyse du trait. Elle sert à deux choses : trier les composantes quand
     * l'utilisateur demande un type précis, et renseigner le style mesuré.
     * L'étiquetage coûte un parcours du masque, négligeable devant la
     * conversion colorimétrique déjà faite.
     */
    var composantes = Trait.composantes(info);
    if (o.filtreTrait && o.filtreTrait !== 'tous') {
      info = Trait.filtrer(info, composantes, o.filtreTrait, o.orientation);
      /* Le masque a changé : les composantes aussi, il faut les reprendre. */
      composantes = Trait.composantes(info);
    }
    var trait = Trait.mesurer(composantes, o.orientation);

    var points = [];
    var lignesVues = 0, lignesRetenues = 0;
    var precedent = null;
    var precedent2 = null;   /* avant-dernier point retenu : amorce la pente */
    var pente = 0;           /* dérivée locale, en pixels par pixel */

    /* Bornes de l'axe de balayage. */
    var debutU = parLignes ? info.zone.y0 : info.zone.x0;
    var finU = parLignes ? info.zone.y1 : info.zone.x1;

    /*
     * Saut maximal admis en mode « suivi ». Par défaut on autorise 5 % de
     * l'étendue perpendiculaire : assez pour une pente raide, trop peu pour
     * sauter sur une courbe voisine de même couleur.
     */
    var etendueV = parLignes ? info.largeurZone : info.hauteurZone;
    var sautMax = o.sautMax > 0 ? o.sautMax : Math.max(4, etendueV * 0.05);

    /* Assemble un point image à partir des coordonnées de balayage. */
    function pointDe(u, v) {
      return parLignes ? { px: v, py: u } : { px: u, py: v };
    }

    for (var u = debutU; u <= finU; u += pas) {
      lignesVues++;
      var segments = Detection.segments(info, u, o.longueurMin, o.longueurMax, o.orientation);
      if (!segments.length) { continue; }
      lignesRetenues++;

      var i;
      if (o.mode === 'tous') {
        for (i = 0; i < segments.length; i++) {
          points.push(pointDe(u, segments[i].centre));
        }

      } else if (o.mode === 'suivi') {
        var choisi = null;
        if (precedent === null) {
          /* Amorçage : le segment le plus épais, le plus probablement le trait. */
          choisi = segments[0];
          for (i = 1; i < segments.length; i++) {
            if (segments[i].longueur > choisi.longueur) { choisi = segments[i]; }
          }
        } else {
          /*
           * On compare à une PRÉDICTION (position + pente locale), pas à la
           * dernière position. À un croisement de deux courbes de même couleur,
           * les deux branches sont équidistantes du dernier point : seul le
           * prolongement de la pente permet de rester sur la bonne.
           */
          var predit = precedent + pente * pas;
          var meilleureDist = Infinity;
          for (i = 0; i < segments.length; i++) {
            var dist = Math.abs(segments[i].centre - predit);
            if (dist < meilleureDist) { meilleureDist = dist; choisi = segments[i]; }
          }
          /* Trop loin : c'est une autre courbe, on ne raccroche pas. */
          if (meilleureDist > sautMax) { choisi = null; }
        }
        if (choisi) {
          if (precedent !== null) {
            /*
             * Pente lissée (moyenne mobile exponentielle). Un lissage franc
             * évite qu'un segment fusionné au croisement ne fasse dérailler la
             * prédiction, tout en suivant les vraies inflexions.
             */
            var penteMesuree = (choisi.centre - precedent) / pas;
            pente = (precedent2 === null) ? penteMesuree
                                          : (0.6 * pente + 0.4 * penteMesuree);
            precedent2 = precedent;
          }
          points.push(pointDe(u, choisi.centre));
          precedent = choisi.centre;
        }

      } else {
        /* mode « moyenne » : barycentre des segments, pondéré par l'épaisseur. */
        var somme = 0, poids = 0;
        for (i = 0; i < segments.length; i++) {
          somme += segments[i].centre * segments[i].longueur;
          poids += segments[i].longueur;
        }
        points.push(pointDe(u, somme / poids));
      }
    }

    var pointsBruts = points.length;

    if (o.comblerLacunes > 0) {
      points = Detection.comblerLacunes(points, pas, o.comblerLacunes, o.orientation);
    }
    var pointsCombles = points.length;

    if (o.simplification > 0 && points.length > 2) {
      /* Douglas-Peucker travaille sur {x,y} : on adapte le nommage. */
      var enXY = points.map(function (p) { return { x: p.px, y: p.py }; });
      points = Base.simplifier(enXY, o.simplification)
        .map(function (p) { return { px: p.x, py: p.y }; });
    }

    return {
      points: points,
      masqueInfo: info,
      statistiques: {
        pixelsRetenus: info.nbRetenus,
        pixelsZone: info.largeurZone * info.hauteurZone,
        lignesVues: lignesVues,
        lignesRetenues: lignesRetenues,
        pointsBruts: pointsBruts,
        pointsCombles: pointsCombles,
        pointsFinaux: points.length,
        trait: trait
      }
    };
  };

  /*
   * Palette des couleurs dominantes de la zone, hors fond.
   * Sert au bouton « couleurs détectées » : proposer directement les teintes des
   * courbes présentes évite à l'utilisateur de chercher le bon pixel à cliquer.
   *
   * Quantification en cubes de 32 niveaux par canal, puis regroupement des
   * représentants trop proches en Lab pour ne pas proposer dix nuances du même
   * bleu.
   */
  Detection.couleursDominantes = function (image, options) {
    options = options || {};
    var zone = Detection.normaliserZone(options.zone, image.width, image.height);
    var exclusions = Detection.normaliserExclusions(
      options.zonesExclues, image.width, image.height);
    var maxCouleurs = options.maxCouleurs || 8;
    var seuilFusion = (options.seuilFusion === undefined) ? 20 : options.seuilFusion;
    var pas = Math.max(1, Math.round(options.pas || 1));

    var d = image.data, w = image.width;
    var seaux = new Map();
    var total = 0;

    for (var y = zone.y0; y <= zone.y1; y += pas) {
      for (var x = zone.x0; x <= zone.x1; x += pas) {
        if (exclusions.length && estExclu(exclusions, x, y)) { continue; }
        var i = (y * w + x) * 4;
        if (d[i + 3] < 128) { continue; }
        var cle = ((d[i] >> 3) << 10) | ((d[i + 1] >> 3) << 5) | (d[i + 2] >> 3);
        var s = seaux.get(cle);
        if (s) {
          s.n++; s.r += d[i]; s.g += d[i + 1]; s.b += d[i + 2];
        } else {
          seaux.set(cle, { n: 1, r: d[i], g: d[i + 1], b: d[i + 2] });
        }
        total++;
      }
    }
    if (!total) { return []; }

    var liste = [];
    seaux.forEach(function (s) {
      liste.push({
        rgb: { r: Math.round(s.r / s.n), g: Math.round(s.g / s.n), b: Math.round(s.b / s.n) },
        n: s.n
      });
    });
    liste.sort(function (a, b) { return b.n - a.n; });

    /*
     * Le seau le plus peuplé est le fond : il couvre l'essentiel de la surface.
     * On l'écarte, ainsi que tout ce qui lui ressemble.
     */
    var fond = liste[0];
    var labFond = Couleur.rgbVersLab(fond.rgb.r, fond.rgb.g, fond.rgb.b);

    var retenus = [];
    for (var k = 1; k < liste.length && retenus.length < maxCouleurs; k++) {
      var c = liste[k];
      /* Bruit : un seau qui pèse moins d'un millième de la zone. */
      if (c.n < total * 0.0005) { continue; }
      var lab = Couleur.rgbVersLab(c.rgb.r, c.rgb.g, c.rgb.b);
      if (Couleur.deltaE(lab, labFond) < seuilFusion) { continue; }

      var doublon = false;
      for (var j = 0; j < retenus.length; j++) {
        if (Couleur.deltaE(lab, retenus[j].lab) < seuilFusion) { doublon = true; break; }
      }
      if (doublon) { continue; }

      retenus.push({
        rgb: c.rgb,
        lab: lab,
        hex: Couleur.rgbVersHex(c.rgb),
        proportion: c.n / total
      });
    }

    return retenus;
  };

  CFDD.Detection = Detection;
  if (typeof module !== 'undefined' && module.exports) { module.exports = Detection; }
})(typeof globalThis !== 'undefined' ? globalThis : this);
