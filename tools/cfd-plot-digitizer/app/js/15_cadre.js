/*
 * 15_cadre.js — détection automatique du cadre du tracé.
 *
 * Placer les quatre repères de calibration à la main est le geste le plus
 * fastidieux de la digitalisation, et le plus facile à rater : un repère posé
 * trois pixels à côté de l'axe fausse TOUTES les valeurs exportées, sans que
 * rien ne le signale. Or la position des quatre bornes est presque toujours
 * lisible dans l'image elle-même : ce sont les traits d'axe.
 *
 * MÉTHODE
 *
 * 1. Couleur de fond = la couleur la plus fréquente de l'image (le papier).
 * 2. Masque d'encre = tout pixel qui s'en écarte.
 * 3. Profils : nombre de pixels d'encre par colonne, puis par ligne.
 *    Un axe est un trait plein d'un bord à l'autre du tracé : il domine son
 *    profil de très loin, alors qu'une courbe ne contribue qu'un ou deux
 *    pixels par colonne, et une étiquette de graduation guère plus.
 * 4. Les pics du profil sont regroupés en « traits » (deux colonnes voisines
 *    au-dessus du seuil appartiennent au même trait) ; le premier et le
 *    dernier donnent les deux bords.
 *
 * REPLI — les planches sans cadre fermé
 *
 * Beaucoup de figures ne tracent que deux axes (gauche et bas). Le profil ne
 * livre alors qu'un seul pic par direction. Le bord manquant se lit sur
 * l'ÉTENDUE du trait trouvé : la ligne d'axe du bas court exactement sur la
 * largeur du tracé, donc son premier et son dernier pixel donnent les bords
 * gauche et droit. C'est ce repli qui évite de retomber sur la boîte
 * englobante de l'encre — laquelle inclut le titre et les étiquettes, et
 * déborde donc largement du cadre.
 *
 * Le résultat reste une PROPOSITION : `confiance` dit combien des quatre côtés
 * ont été vus comme de vrais traits, et l'interface laisse déplacer chaque
 * repère. La détection ne lit pas les valeurs des graduations — aucune OCR
 * ici — elle ne place que les positions.
 */
(function (racine) {
  'use strict';

  var CFDD = racine.CFDD || (racine.CFDD = {});
  var Base = CFDD.Base;
  var Cadre = {};

  Cadre.DEFAUTS = {
    /* Écart canal maximal au fond au-delà duquel un pixel est « de l'encre ». */
    seuilEncre: 40,
    /* Fraction du pic de profil à partir de laquelle une ligne est un axe. */
    fractionPic: 0.6,
    /* Un axe doit couvrir au moins cette fraction de l'étendue encrée. */
    couvertureMin: 0.35,
    /* Sous-échantillonnage de l'histogramme du fond. */
    pasFond: 2
  };

  function fusionner(options) {
    var o = {}, cle;
    for (cle in Cadre.DEFAUTS) {
      if (Object.prototype.hasOwnProperty.call(Cadre.DEFAUTS, cle)) {
        o[cle] = (options && options[cle] !== undefined) ? options[cle] : Cadre.DEFAUTS[cle];
      }
    }
    return o;
  }

  /*
   * Couleur dominante de l'image, prise pour le fond. Les pixels sont comptés
   * exacts, sans quantification : le fond d'une figure vectorielle rendue en
   * PNG est un aplat rigoureusement uniforme, et quantifier n'y gagnerait rien
   * tout en risquant de fusionner le papier avec un aplat clair voisin.
   */
  Cadre.couleurFond = function (image, options) {
    var o = fusionner(options);
    var d = image.data, w = image.width, h = image.height;
    var compte = {};
    var meilleur = null, meilleurCompte = -1;

    for (var y = 0; y < h; y += o.pasFond) {
      for (var x = 0; x < w; x += o.pasFond) {
        var i = (y * w + x) * 4;
        if (d[i + 3] < 128) { continue; }
        var cle = (d[i] << 16) | (d[i + 1] << 8) | d[i + 2];
        var n = (compte[cle] || 0) + 1;
        compte[cle] = n;
        if (n > meilleurCompte) { meilleurCompte = n; meilleur = cle; }
      }
    }
    if (meilleur === null) { return { r: 255, g: 255, b: 255 }; }
    return { r: (meilleur >> 16) & 255, g: (meilleur >> 8) & 255, b: meilleur & 255 };
  };

  /*
   * Masque d'encre de la zone : 1 dès qu'un canal s'écarte du fond de plus de
   * `seuilEncre`. On compare canal par canal plutôt qu'en distance : un trait
   * rouge vif sur fond blanc et un trait gris foncé doivent tous deux compter,
   * et le maximum des écarts les attrape l'un comme l'autre.
   */
  Cadre.masqueEncre = function (image, fond, options) {
    var o = fusionner(options);
    var zone = normaliser(options && options.zone, image.width, image.height);
    var w = zone.x1 - zone.x0 + 1, h = zone.y1 - zone.y0 + 1;
    var encre = new Uint8Array(w * h);
    var d = image.data, iw = image.width;
    var total = 0;

    for (var y = 0; y < h; y++) {
      for (var x = 0; x < w; x++) {
        var i = ((y + zone.y0) * iw + (x + zone.x0)) * 4;
        if (d[i + 3] < 128) { continue; }
        var ecart = Math.max(Math.abs(d[i] - fond.r),
          Math.abs(d[i + 1] - fond.g), Math.abs(d[i + 2] - fond.b));
        if (ecart > o.seuilEncre) { encre[y * w + x] = 1; total++; }
      }
    }
    return { encre: encre, largeur: w, hauteur: h, zone: zone, total: total };
  };

  function normaliser(zone, largeur, hauteur) {
    if (!zone) { return { x0: 0, y0: 0, x1: largeur - 1, y1: hauteur - 1 }; }
    return {
      x0: Base.borner(Math.round(Math.min(zone.x0, zone.x1)), 0, largeur - 1),
      x1: Base.borner(Math.round(Math.max(zone.x0, zone.x1)), 0, largeur - 1),
      y0: Base.borner(Math.round(Math.min(zone.y0, zone.y1)), 0, hauteur - 1),
      y1: Base.borner(Math.round(Math.max(zone.y0, zone.y1)), 0, hauteur - 1)
    };
  }

  /*
   * Regroupe en « traits » les indices dont le profil dépasse `seuil`. Deux
   * indices voisins forment un seul trait : un axe tracé à 1,5 px de large
   * couvre deux colonnes, et les compter séparément donnerait deux bords là où
   * il n'y en a qu'un.
   */
  Cadre.traits = function (profil, seuil) {
    var sortie = [];
    var debut = -1;
    for (var i = 0; i <= profil.length; i++) {
      var fort = (i < profil.length) && (profil[i] >= seuil);
      if (fort && debut < 0) { debut = i; }
      if (!fort && debut >= 0) {
        var somme = 0, pic = 0;
        for (var k = debut; k < i; k++) { somme += profil[k]; pic = Math.max(pic, profil[k]); }
        sortie.push({
          debut: debut, fin: i - 1,
          centre: (debut + i - 1) / 2,
          pic: pic, somme: somme
        });
        debut = -1;
      }
    }
    return sortie;
  };

  /* Premier et dernier pixel d'encre d'une colonne (vertical) ou d'une ligne. */
  function etendue(masque, indice, vertical) {
    var w = masque.largeur, h = masque.hauteur, e = masque.encre;
    var n = vertical ? h : w;
    var debut = -1, fin = -1;
    for (var k = 0; k < n; k++) {
      var p = vertical ? (k * w + indice) : (indice * w + k);
      if (e[p]) { if (debut < 0) { debut = k; } fin = k; }
    }
    return (debut < 0) ? null : { debut: debut, fin: fin };
  }

  /*
   * Détecte le cadre. Renvoie null si l'image ne contient pas d'encre.
   *
   *   {cadre: {x0, y0, x1, y1},        coordonnées image
   *    sources: {gauche, droite, haut, bas},   'trait' | 'etendue' | 'boite'
   *    confiance: 0..1,
   *    fond: {r, g, b}}
   */
  Cadre.detecter = function (image, options) {
    var o = fusionner(options);
    var fond = (options && options.fond) || Cadre.couleurFond(image, options);
    var masque = Cadre.masqueEncre(image, fond, options);
    if (!masque.total) { return null; }

    var w = masque.largeur, h = masque.hauteur, e = masque.encre;
    var colonnes = new Int32Array(w), lignes = new Int32Array(h);
    var x, y;
    for (y = 0; y < h; y++) {
      for (x = 0; x < w; x++) {
        if (e[y * w + x]) { colonnes[x]++; lignes[y]++; }
      }
    }

    /* Boîte englobante de l'encre : dernier recours, et référence d'étendue. */
    var boite = { x0: -1, x1: -1, y0: -1, y1: -1 };
    for (x = 0; x < w; x++) { if (colonnes[x]) { if (boite.x0 < 0) { boite.x0 = x; } boite.x1 = x; } }
    for (y = 0; y < h; y++) { if (lignes[y]) { if (boite.y0 < 0) { boite.y0 = y; } boite.y1 = y; } }
    var etendueX = boite.x1 - boite.x0 + 1;
    var etendueY = boite.y1 - boite.y0 + 1;

    var picColonnes = 0, picLignes = 0;
    for (x = 0; x < w; x++) { picColonnes = Math.max(picColonnes, colonnes[x]); }
    for (y = 0; y < h; y++) { picLignes = Math.max(picLignes, lignes[y]); }

    /*
     * Double condition : dominer le profil ET couvrir une part réelle du
     * tracé. La première seule suffirait sur une figure encadrée ; la seconde
     * empêche une image sans le moindre axe — un nuage de points nu — de
     * promouvoir sa colonne la plus dense au rang de bord.
     */
    var seuilV = Math.max(o.fractionPic * picColonnes, o.couvertureMin * etendueY);
    var seuilH = Math.max(o.fractionPic * picLignes, o.couvertureMin * etendueX);
    var verticaux = Cadre.traits(colonnes, seuilV);
    var horizontaux = Cadre.traits(lignes, seuilH);

    var sources = { gauche: 'boite', droite: 'boite', haut: 'boite', bas: 'boite' };
    var bords = { gauche: boite.x0, droite: boite.x1, haut: boite.y0, bas: boite.y1 };

    /*
     * Deux traits : les deux bords. Un seul : encore faut-il savoir DUQUEL il
     * s'agit. Le prendre pour le premier serait faux une fois sur deux — une
     * planche à deux axes ne trace que l'ordonnée à gauche et l'abscisse en
     * BAS, et l'abscisse serait alors décrétée bord supérieur, ce qui replie
     * le cadre sur une ligne. Sa position dans l'encre tranche sans préjugé.
     */
    function assigner(traits, bordDebut, bordFin, milieu) {
      if (!traits.length) { return; }
      var premier = Math.round(traits[0].centre);
      var dernier = Math.round(traits[traits.length - 1].centre);
      if (traits.length > 1) {
        bords[bordDebut] = premier; sources[bordDebut] = 'trait';
        bords[bordFin] = dernier; sources[bordFin] = 'trait';
      } else if (premier <= milieu) {
        bords[bordDebut] = premier; sources[bordDebut] = 'trait';
      } else {
        bords[bordFin] = premier; sources[bordFin] = 'trait';
      }
    }
    assigner(verticaux, 'gauche', 'droite', (boite.x0 + boite.x1) / 2);
    assigner(horizontaux, 'haut', 'bas', (boite.y0 + boite.y1) / 2);

    /*
     * Repli : un trait d'axe court exactement sur la largeur (ou la hauteur)
     * du tracé. Son étendue livre donc les deux bords perpendiculaires, ce qui
     * rattrape les planches à deux axes seulement — sans retomber sur la boîte
     * englobante, qui engloberait aussi le titre et les graduations.
     */
    var ligneAxe = (sources.bas === 'trait') ? bords.bas
      : (sources.haut === 'trait') ? bords.haut : null;
    var colonneAxe = (sources.gauche === 'trait') ? bords.gauche
      : (sources.droite === 'trait') ? bords.droite : null;
    var span;

    if (ligneAxe !== null) {
      span = etendue(masque, ligneAxe, false);
      if (span) {
        if (sources.gauche !== 'trait') { bords.gauche = span.debut; sources.gauche = 'etendue'; }
        if (sources.droite !== 'trait') { bords.droite = span.fin; sources.droite = 'etendue'; }
      }
    }
    if (colonneAxe !== null) {
      span = etendue(masque, colonneAxe, true);
      if (span) {
        if (sources.haut !== 'trait') { bords.haut = span.debut; sources.haut = 'etendue'; }
        if (sources.bas !== 'trait') { bords.bas = span.fin; sources.bas = 'etendue'; }
      }
    }

    var confiance = 0;
    ['gauche', 'droite', 'haut', 'bas'].forEach(function (cle) {
      confiance += (sources[cle] === 'trait') ? 0.25 : (sources[cle] === 'etendue' ? 0.15 : 0);
    });

    var cadre = {
      x0: bords.gauche + masque.zone.x0,
      x1: bords.droite + masque.zone.x0,
      y0: bords.haut + masque.zone.y0,
      y1: bords.bas + masque.zone.y0
    };
    /* Un cadre plat ne sert à rien et rendrait la calibration dégénérée. */
    if (cadre.x1 - cadre.x0 < 8 || cadre.y1 - cadre.y0 < 8) { return null; }

    return { cadre: cadre, sources: sources, confiance: confiance, fond: fond };
  };

  /*
   * Positions de repères déduites d'un cadre. X1 et Y1 tombent volontairement
   * sur le MÊME pixel — le coin bas-gauche : c'est l'origine du tracé, et rien
   * n'oblige à la pointer deux fois.
   */
  Cadre.reperes = function (cadre) {
    return {
      x1: { px: cadre.x0, py: cadre.y1 },
      x2: { px: cadre.x1, py: cadre.y1 },
      y1: { px: cadre.x0, py: cadre.y1 },
      y2: { px: cadre.x0, py: cadre.y0 }
    };
  };

  CFDD.Cadre = Cadre;
  if (typeof module !== 'undefined' && module.exports) { module.exports = Cadre; }
})(typeof globalThis !== 'undefined' ? globalThis : this);
