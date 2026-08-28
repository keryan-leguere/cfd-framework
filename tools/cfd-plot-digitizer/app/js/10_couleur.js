/*
 * 10_couleur.js — conversions sRGB → CIE L*a*b* et critère de correspondance.
 *
 * Pourquoi Lab et pas une distance RGB : sur une courbe tracée, l'anticrénelage
 * fait varier la LUMINANCE des pixels de bord beaucoup plus que leur TEINTE.
 * Une distance RGB unique force donc un compromis : trop serrée elle ne garde
 * que le cœur du trait, trop large elle avale le fond.
 *
 * On sépare donc les deux tolérances (cf. 00_DOC/02_DETECTION_COULEUR.md) :
 *   - tolChroma : distance dans le plan (a*, b*)  → « la même teinte »
 *   - tolLum    : écart sur L*                     → « la même clarté »
 * Un pixel correspond si les DEUX critères passent. Ce découpage traite aussi
 * le cas dégénéré des courbes noires/grises sur fond blanc, où a* et b* sont
 * tous deux nuls et où seule L* discrimine.
 */
(function (racine) {
  'use strict';

  var CFDD = racine.CFDD || (racine.CFDD = {});
  var Couleur = {};

  /* --- Conversions élémentaires ------------------------------------- */

  Couleur.hexVersRgb = function (hex) {
    if (typeof hex !== 'string') { return null; }
    var t = hex.trim().replace(/^#/, '');
    if (t.length === 3) {
      t = t[0] + t[0] + t[1] + t[1] + t[2] + t[2];
    }
    if (!/^[0-9a-fA-F]{6}$/.test(t)) { return null; }
    return {
      r: parseInt(t.slice(0, 2), 16),
      g: parseInt(t.slice(2, 4), 16),
      b: parseInt(t.slice(4, 6), 16)
    };
  };

  Couleur.rgbVersHex = function (rgb) {
    function deux(v) {
      var n = Math.round(CFDD.Base.borner(v, 0, 255));
      return (n < 16 ? '0' : '') + n.toString(16);
    }
    return '#' + deux(rgb.r) + deux(rgb.g) + deux(rgb.b);
  };

  /* sRGB 8 bits → composante linéaire [0,1] (décodage gamma IEC 61966-2-1). */
  function delineariser(c) {
    var v = c / 255;
    return (v <= 0.04045) ? (v / 12.92) : Math.pow((v + 0.055) / 1.055, 2.4);
  }

  /* Blanc de référence D65, observateur 2°. */
  var BLANC = { X: 0.95047, Y: 1.0, Z: 1.08883 };

  function fLab(t) {
    /* Seuil (6/29)^3 ; branche linéaire pour éviter la dérivée infinie en 0. */
    return (t > 0.008856451679035631)
      ? Math.pow(t, 1 / 3)
      : (t * 7.787037037037035 + 16 / 116);
  }

  /*
   * sRGB (0-255) vers L*a*b*. L* dans [0,100], a* et b* typiquement [-128,127].
   */
  Couleur.rgbVersLab = function (r, g, b) {
    var rl = delineariser(r), gl = delineariser(g), bl = delineariser(b);

    var X = (rl * 0.4124564 + gl * 0.3575761 + bl * 0.1804375) / BLANC.X;
    var Y = (rl * 0.2126729 + gl * 0.7151522 + bl * 0.0721750) / BLANC.Y;
    var Z = (rl * 0.0193339 + gl * 0.1191920 + bl * 0.9503041) / BLANC.Z;

    var fx = fLab(X), fy = fLab(Y), fz = fLab(Z);
    return {
      L: 116 * fy - 16,
      a: 500 * (fx - fy),
      b: 200 * (fy - fz)
    };
  };

  /* Distance CIE76 complète, utile pour classer des candidats. */
  Couleur.deltaE = function (lab1, lab2) {
    var dL = lab1.L - lab2.L, da = lab1.a - lab2.a, db = lab1.b - lab2.b;
    return Math.sqrt(dL * dL + da * da + db * db);
  };

  /* --- Critère de correspondance ------------------------------------ */

  /*
   * Construit un test de correspondance autour d'une couleur cible.
   *
   * cible    : {r,g,b} 0-255
   * options  : {tolChroma, tolLum}
   *
   * Retourne un objet exposant :
   *   correspond(r,g,b) -> bool
   *   ecart(r,g,b)      -> {chroma, lum}  (pour le diagnostic / l'aperçu)
   *
   * Le test travaille sur des carrés de distance : pas de racine dans la
   * boucle chaude, qui tourne une fois par pixel de l'image.
   */
  Couleur.creerCorrespondance = function (cible, options) {
    options = options || {};
    var tolChroma = (options.tolChroma === undefined) ? 20 : options.tolChroma;
    var tolLum = (options.tolLum === undefined) ? 30 : options.tolLum;

    var labCible = Couleur.rgbVersLab(cible.r, cible.g, cible.b);
    var seuilChroma2 = tolChroma * tolChroma;

    /*
     * Cache RGB → Lab. Une image de tracé n'utilise en pratique que quelques
     * milliers de couleurs distinctes sur des millions de pixels : le cache
     * transforme la conversion en une simple recherche de table.
     */
    var cache = new Map();
    function labDe(r, g, b) {
      var cle = (r << 16) | (g << 8) | b;
      var lab = cache.get(cle);
      if (lab === undefined) {
        lab = Couleur.rgbVersLab(r, g, b);
        cache.set(cle, lab);
      }
      return lab;
    }

    return {
      labCible: labCible,
      tolChroma: tolChroma,
      tolLum: tolLum,

      correspond: function (r, g, b) {
        var lab = labDe(r, g, b);
        var dL = lab.L - labCible.L;
        if (dL < 0) { dL = -dL; }
        if (dL > tolLum) { return false; }
        var da = lab.a - labCible.a, db = lab.b - labCible.b;
        return (da * da + db * db) <= seuilChroma2;
      },

      ecart: function (r, g, b) {
        var lab = labDe(r, g, b);
        var da = lab.a - labCible.a, db = lab.b - labCible.b;
        return {
          lum: Math.abs(lab.L - labCible.L),
          chroma: Math.sqrt(da * da + db * db)
        };
      }
    };
  };

  /*
   * Couleur moyenne d'une fenêtre carrée centrée sur (cx, cy).
   * La pipette ne doit jamais échantillonner un seul pixel : sur un trait fin
   * anticrénelé, un pixel isolé est presque toujours un pixel de bord, donc un
   * mélange trait/fond qui fausse la cible.
   *
   * `image` : {data: Uint8ClampedArray RGBA, width, height}
   */
  Couleur.echantillonner = function (image, cx, cy, rayon) {
    rayon = (rayon === undefined) ? 1 : rayon;
    var w = image.width, h = image.height, d = image.data;
    var sr = 0, sg = 0, sb = 0, n = 0;

    for (var y = cy - rayon; y <= cy + rayon; y++) {
      if (y < 0 || y >= h) { continue; }
      for (var x = cx - rayon; x <= cx + rayon; x++) {
        if (x < 0 || x >= w) { continue; }
        var i = (y * w + x) * 4;
        if (d[i + 3] === 0) { continue; }   /* pixel transparent : ignoré */
        sr += d[i]; sg += d[i + 1]; sb += d[i + 2];
        n++;
      }
    }
    if (n === 0) { return null; }
    return { r: Math.round(sr / n), g: Math.round(sg / n), b: Math.round(sb / n) };
  };

  /*
   * Couleur la plus « saturée / éloignée du fond » dans la fenêtre.
   * Complément de `echantillonner` : quand l'utilisateur clique à côté du trait,
   * la moyenne tire vers le fond alors que ce mode retrouve la couleur du trait.
   */
  Couleur.echantillonnerDominante = function (image, cx, cy, rayon) {
    rayon = (rayon === undefined) ? 2 : rayon;
    var w = image.width, h = image.height, d = image.data;

    /* Le fond est estimé par la couleur la plus claire de la fenêtre. */
    var meilleur = null, meilleurScore = -1, plusClair = -1;
    var pixels = [];

    for (var y = cy - rayon; y <= cy + rayon; y++) {
      if (y < 0 || y >= h) { continue; }
      for (var x = cx - rayon; x <= cx + rayon; x++) {
        if (x < 0 || x >= w) { continue; }
        var i = (y * w + x) * 4;
        if (d[i + 3] === 0) { continue; }
        var lab = Couleur.rgbVersLab(d[i], d[i + 1], d[i + 2]);
        pixels.push({ rgb: { r: d[i], g: d[i + 1], b: d[i + 2] }, lab: lab });
        if (lab.L > plusClair) { plusClair = lab.L; }
      }
    }
    if (!pixels.length) { return null; }

    for (var k = 0; k < pixels.length; k++) {
      var p = pixels[k];
      /* Score = chroma + écart de clarté au fond supposé. */
      var chroma = Math.sqrt(p.lab.a * p.lab.a + p.lab.b * p.lab.b);
      var score = chroma + (plusClair - p.lab.L);
      if (score > meilleurScore) { meilleurScore = score; meilleur = p.rgb; }
    }
    return meilleur;
  };

  CFDD.Couleur = Couleur;
  if (typeof module !== 'undefined' && module.exports) { module.exports = Couleur; }
})(typeof globalThis !== 'undefined' ? globalThis : this);
