/*
 * 25_trait.js — nature du trait : continu, tirets, pointillé, tiret-point.
 *
 * POURQUOI. Beaucoup de planches, surtout en noir et blanc, distinguent leurs
 * courbes non par la couleur mais par le TYPE DE TRAIT. La détection par
 * couleur y ramasse alors toutes les courbes d'un coup, et aucune tolérance ne
 * peut les séparer : elles ont exactement la même couleur.
 *
 * COMMENT. Un trait continu forme UNE composante connexe qui traverse le
 * graphique. Un trait discontinu en forme des dizaines, petites et alignées.
 * Cette différence de structure — et non de couleur — est ce qui permet de les
 * séparer. On étiquette donc les composantes connexes du masque, puis on les
 * trie sur leur étendue le long de l'axe de balayage.
 *
 * Le même étiquetage sert à RECONNAÎTRE le type de trait (longueur des marques
 * et des espaces), information reportée à l'utilisateur.
 *
 * Coordonnées locales à la zone d'analyse, comme le masque lui-même.
 */
(function (racine) {
  'use strict';

  var CFDD = racine.CFDD || (racine.CFDD = {});
  var Trait = {};

  Trait.STYLES = {
    continu: 'continu',
    tirets: 'tirets',
    pointille: 'pointillé',
    tiretPoint: 'tiret-point',
    inconnu: 'inconnu'
  };

  Trait.FILTRES = {
    /* Aucun tri : tout le masque est conservé. */
    tous: 'tous',
    /* Composantes longues : isole une courbe pleine. */
    continu: 'continu',
    /* Toutes les composantes courtes : tirets ET points confondus. */
    discontinu: 'discontinu',
    /* Composantes courtes mais nettement plus longues qu'épaisses. */
    tirets: 'tirets',
    /* Composantes aussi courtes qu'épaisses : des points. */
    pointille: 'pointillé'
  };

  /*
   * Étiquetage des composantes connexes du masque, en 8-connexité.
   *
   * La 8-connexité (diagonales comprises) n'est pas un détail : un trait
   * oblique d'un pixel d'épaisseur est une échelle de pixels qui ne se touchent
   * QUE par les coins. En 4-connexité, une seule droite inclinée se
   * fragmenterait en autant de composantes que de pixels, et passerait pour du
   * pointillé.
   *
   * Parcours en profondeur avec pile explicite : une zone de 600 x 400 tient
   * 240 000 pixels, largement de quoi faire déborder la pile d'appels.
   */
  Trait.composantes = function (info) {
    var w = info.largeurZone, h = info.hauteurZone;
    var masque = info.masque;
    var etiquettes = new Int32Array(w * h);
    etiquettes.fill(-1);

    var liste = [];
    var pile = [];

    for (var depart = 0; depart < masque.length; depart++) {
      if (!masque[depart] || etiquettes[depart] !== -1) { continue; }

      var id = liste.length;
      var comp = { id: id, taille: 0, x0: w, y0: h, x1: -1, y1: -1 };
      etiquettes[depart] = id;
      pile.push(depart);

      while (pile.length) {
        var p = pile.pop();
        var px = p % w;
        var py = (p - px) / w;
        comp.taille++;
        if (px < comp.x0) { comp.x0 = px; }
        if (px > comp.x1) { comp.x1 = px; }
        if (py < comp.y0) { comp.y0 = py; }
        if (py > comp.y1) { comp.y1 = py; }

        for (var dy = -1; dy <= 1; dy++) {
          var ny = py + dy;
          if (ny < 0 || ny >= h) { continue; }
          for (var dx = -1; dx <= 1; dx++) {
            if (dx === 0 && dy === 0) { continue; }
            var nx = px + dx;
            if (nx < 0 || nx >= w) { continue; }
            var q = ny * w + nx;
            if (masque[q] && etiquettes[q] === -1) {
              etiquettes[q] = id;
              pile.push(q);
            }
          }
        }
      }
      liste.push(comp);
    }

    return { etiquettes: etiquettes, liste: liste };
  };

  /* Étendue d'une composante perpendiculairement à l'axe de balayage. */
  function epaisseurDe(comp, parLignes) {
    return parLignes ? (comp.x1 - comp.x0 + 1) : (comp.y1 - comp.y0 + 1);
  }

  /* Étendue d'une composante le long de l'axe de balayage. */
  function etendue(comp, parLignes) {
    return parLignes ? (comp.y1 - comp.y0 + 1) : (comp.x1 - comp.x0 + 1);
  }

  function debut(comp, parLignes) { return parLignes ? comp.y0 : comp.x0; }
  function fin(comp, parLignes) { return parLignes ? comp.y1 : comp.x1; }

  function mediane(valeurs) {
    if (!valeurs.length) { return 0; }
    var tri = valeurs.slice().sort(function (a, b) { return a - b; });
    var milieu = Math.floor(tri.length / 2);
    return (tri.length % 2) ? tri[milieu] : (tri[milieu - 1] + tri[milieu]) / 2;
  }

  /*
   * Reconnaît le type de trait à partir des composantes.
   *
   * Retourne {style, marque, espace, periode, nbComposantes, couverture}
   * où `marque` et `espace` sont des longueurs médianes en pixels, et
   * `couverture` la fraction de l'étendue occupée qui est effectivement peinte.
   */
  Trait.mesurer = function (composantes, orientation) {
    var parLignes = (orientation === 'lignes');
    var liste = composantes.liste;

    var vide = {
      style: Trait.STYLES.inconnu, marque: 0, espace: 0, periode: 0,
      nbComposantes: 0, couverture: 0
    };
    if (!liste.length) { return vide; }

    /* Tri sur la position de départ le long de l'axe de balayage. */
    var ordonnees = liste.slice().sort(function (a, b) {
      return debut(a, parLignes) - debut(b, parLignes);
    });

    var etendues = [];
    var minGlobal = Infinity, maxGlobal = -Infinity;
    for (var i = 0; i < ordonnees.length; i++) {
      etendues.push(etendue(ordonnees[i], parLignes));
      minGlobal = Math.min(minGlobal, debut(ordonnees[i], parLignes));
      maxGlobal = Math.max(maxGlobal, fin(ordonnees[i], parLignes));
    }
    var portee = maxGlobal - minGlobal + 1;

    /*
     * Couverture : part de la portée réellement peinte. On la calcule sur
     * l'union des intervalles et non sur leur somme, sinon deux composantes qui
     * se chevauchent la gonfleraient au-delà de 1.
     */
    var occupe = 0, curseurFin = -Infinity;
    for (var j = 0; j < ordonnees.length; j++) {
      var d = debut(ordonnees[j], parLignes), f = fin(ordonnees[j], parLignes);
      if (d > curseurFin) {
        occupe += f - d + 1;
        curseurFin = f;
      } else if (f > curseurFin) {
        occupe += f - curseurFin;
        curseurFin = f;
      }
    }
    var couverture = portee > 0 ? (occupe / portee) : 0;

    /* Espaces entre composantes successives, chevauchements ignorés. */
    var espaces = [];
    var precedenteFin = fin(ordonnees[0], parLignes);
    for (var k = 1; k < ordonnees.length; k++) {
      var ecart = debut(ordonnees[k], parLignes) - precedenteFin - 1;
      if (ecart > 0) { espaces.push(ecart); }
      precedenteFin = Math.max(precedenteFin, fin(ordonnees[k], parLignes));
    }

    var marque = mediane(etendues);
    var espace = mediane(espaces);

    var style;
    if (liste.length === 1 || couverture >= 0.95 || !espaces.length) {
      style = Trait.STYLES.continu;
    } else if (marque <= 3) {
      /* Des marques de l'ordre de l'épaisseur du trait : ce sont des points. */
      style = Trait.STYLES.pointille;
    } else {
      /*
       * Tiret-point : les marques alternent entre deux longueurs nettement
       * différentes. On compare la médiane de la moitié haute à celle de la
       * moitié basse ; un rapport marqué signe l'alternance.
       */
      var tri = etendues.slice().sort(function (a, b) { return a - b; });
      var coupe = Math.floor(tri.length / 2);
      var basses = tri.slice(0, coupe);
      var hautes = tri.slice(tri.length - coupe);
      var rapport = (basses.length && mediane(basses) > 0)
        ? mediane(hautes) / mediane(basses) : 1;
      style = (tri.length >= 4 && rapport >= 2.2)
        ? Trait.STYLES.tiretPoint : Trait.STYLES.tirets;
    }

    return {
      style: style,
      marque: marque,
      espace: espace,
      periode: marque + espace,
      nbComposantes: liste.length,
      couverture: couverture
    };
  };

  /*
   * Reconstruit un masque ne gardant que les composantes du type demandé.
   *
   * Le seuil sépare « long » de « court » relativement à la composante la plus
   * étendue : une courbe pleine traverse le graphique, un tiret fait quelques
   * pixels. Un seuil relatif tient donc sans réglage quelle que soit la taille
   * de l'image, là où un seuil en pixels devrait être réajusté à chaque figure.
   *
   * Retourne un objet de même forme que `construireMasque`, réutilisable tel
   * quel par le balayage.
   */
  Trait.filtrer = function (info, composantes, filtre, orientation, seuilRelatif) {
    if (!filtre || filtre === Trait.FILTRES.tous) { return info; }

    var parLignes = (orientation === 'lignes');
    seuilRelatif = (seuilRelatif === undefined) ? 0.25 : seuilRelatif;

    var liste = composantes.liste;
    if (!liste.length) { return info; }

    var i;
    var epaisseurs = [];
    var minDebut = Infinity, maxFin = -Infinity;
    for (i = 0; i < liste.length; i++) {
      epaisseurs.push(epaisseurDe(liste[i], parLignes));
      minDebut = Math.min(minDebut, debut(liste[i], parLignes));
      maxFin = Math.max(maxFin, fin(liste[i], parLignes));
    }

    /*
     * Une composante est « continue » lorsqu'elle couvre une bonne part de
     * l'ÉTENDUE TOTALE du tracé — et non lorsqu'elle est la plus longue des
     * composantes présentes. La nuance est décisive : sur une planche ne
     * portant qu'une courbe en pointillé, le point le plus long resterait le
     * maximum et tous les points passeraient pour du trait plein. Rapporté à
     * l'étendue, un point reste un point, qu'il ait ou non un trait plein pour
     * voisin.
     */
    var portee = (maxFin >= minDebut) ? (maxFin - minDebut + 1) : 1;
    var seuilLong = portee * seuilRelatif;

    /*
     * Séparer les points des tirets demande une référence d'échelle, faute de
     * quoi le seuil dépendrait de la résolution de l'image. Cette référence est
     * l'ÉPAISSEUR du trait, que l'on mesure sur les composantes elles-mêmes :
     * un point est aussi long qu'épais, un tiret est bien plus long. Le seuil
     * suit donc automatiquement une planche fine ou une planche grossie.
     */
    var epaisseur = Math.max(1, mediane(epaisseurs));
    var seuilPoint = Math.max(3, epaisseur * 2);

    var garder = new Uint8Array(liste.length);
    for (i = 0; i < liste.length; i++) {
      var longueur = etendue(liste[i], parLignes);
      var longue = longueur >= seuilLong;
      var retenue;
      switch (filtre) {
        case Trait.FILTRES.continu:
          retenue = longue; break;
        case Trait.FILTRES.discontinu:
          retenue = !longue; break;
        case Trait.FILTRES.tirets:
          retenue = !longue && longueur > seuilPoint; break;
        case Trait.FILTRES.pointille:
          retenue = !longue && longueur <= seuilPoint; break;
        default:
          retenue = true;
      }
      garder[i] = retenue ? 1 : 0;
    }

    var masque = new Uint8Array(info.masque.length);
    var nbRetenus = 0;
    for (var p = 0; p < masque.length; p++) {
      var id = composantes.etiquettes[p];
      if (id >= 0 && garder[id]) { masque[p] = 1; nbRetenus++; }
    }

    return {
      masque: masque,
      zone: info.zone,
      largeurZone: info.largeurZone,
      hauteurZone: info.hauteurZone,
      nbRetenus: nbRetenus
    };
  };

  CFDD.Trait = Trait;
  if (typeof module !== 'undefined' && module.exports) { module.exports = Trait; }
})(typeof globalThis !== 'undefined' ? globalThis : this);
