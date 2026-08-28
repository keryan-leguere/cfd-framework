/*
 * png.js — décodeur PNG minimal (node uniquement), pour les tests d'intégration.
 *
 * Objectif : lire les figures de exemples/ sans dépendance externe, afin que la
 * suite tourne sur une machine sans accès réseau. zlib est fourni par node.
 *
 * Couvre ce que produit un traceur usuel : 8 bits par canal, non entrelacé,
 * types couleur 0 (gris), 2 (RVB), 3 (palette), 4 (gris+alpha), 6 (RVBA).
 * Tout le reste lève une erreur explicite plutôt que de rendre des pixels faux.
 */
'use strict';

var fs = require('fs');
var zlib = require('zlib');

/* Prédicteur de Paeth (filtre 4 de la spécification PNG). */
function paeth(gauche, haut, hautGauche) {
  var p = gauche + haut - hautGauche;
  var pa = Math.abs(p - gauche), pb = Math.abs(p - haut), pc = Math.abs(p - hautGauche);
  if (pa <= pb && pa <= pc) { return gauche; }
  return (pb <= pc) ? haut : hautGauche;
}

function lirePNG(chemin) {
  var buf = fs.readFileSync(chemin);
  var signature = [137, 80, 78, 71, 13, 10, 26, 10];
  for (var s = 0; s < 8; s++) {
    if (buf[s] !== signature[s]) { throw new Error(chemin + ' : signature PNG absente.'); }
  }

  var pos = 8;
  var largeur = 0, hauteur = 0, profondeur = 0, typeCouleur = 0, entrelacement = 0;
  var morceaux = [];
  var palette = null, alphaPalette = null;

  while (pos < buf.length) {
    var taille = buf.readUInt32BE(pos);
    var type = buf.toString('ascii', pos + 4, pos + 8);
    var donnees = buf.slice(pos + 8, pos + 8 + taille);
    pos += 12 + taille;                       /* 4 taille + 4 type + data + 4 CRC */

    if (type === 'IHDR') {
      largeur = donnees.readUInt32BE(0);
      hauteur = donnees.readUInt32BE(4);
      profondeur = donnees[8];
      typeCouleur = donnees[9];
      entrelacement = donnees[12];
    } else if (type === 'PLTE') {
      palette = donnees;
    } else if (type === 'tRNS') {
      alphaPalette = donnees;
    } else if (type === 'IDAT') {
      morceaux.push(donnees);
    } else if (type === 'IEND') {
      break;
    }
  }

  if (profondeur !== 8) {
    throw new Error(chemin + ' : profondeur ' + profondeur + ' bits non gérée (8 attendus).');
  }
  if (entrelacement !== 0) {
    throw new Error(chemin + ' : PNG entrelacé (Adam7) non géré.');
  }

  var CANAUX = { 0: 1, 2: 3, 3: 1, 4: 2, 6: 4 };
  var canaux = CANAUX[typeCouleur];
  if (!canaux) { throw new Error(chemin + ' : type couleur ' + typeCouleur + ' non géré.'); }

  var brut = zlib.inflateSync(Buffer.concat(morceaux));
  var bpp = canaux;                            /* octets par pixel (8 bits/canal) */
  var pasLigne = largeur * bpp;
  var lignes = Buffer.alloc(hauteur * pasLigne);

  var offset = 0;
  for (var y = 0; y < hauteur; y++) {
    var filtre = brut[offset++];
    var debut = y * pasLigne;
    var debutPrec = (y - 1) * pasLigne;
    for (var i = 0; i < pasLigne; i++) {
      var x = brut[offset + i];
      var gauche = (i >= bpp) ? lignes[debut + i - bpp] : 0;
      var haut = (y > 0) ? lignes[debutPrec + i] : 0;
      var hautGauche = (y > 0 && i >= bpp) ? lignes[debutPrec + i - bpp] : 0;
      var valeur;
      switch (filtre) {
        case 0: valeur = x; break;
        case 1: valeur = x + gauche; break;
        case 2: valeur = x + haut; break;
        case 3: valeur = x + ((gauche + haut) >> 1); break;
        case 4: valeur = x + paeth(gauche, haut, hautGauche); break;
        default: throw new Error(chemin + ' : filtre PNG ' + filtre + ' inconnu.');
      }
      lignes[debut + i] = valeur & 0xff;
    }
    offset += pasLigne;
  }

  /* Normalisation en RGBA, l'unique format manipulé par l'application. */
  var data = new Uint8ClampedArray(largeur * hauteur * 4);
  for (var p = 0; p < largeur * hauteur; p++) {
    var src = p * bpp, dst = p * 4;
    var r, g, b, a = 255;
    if (typeCouleur === 0) {
      r = g = b = lignes[src];
    } else if (typeCouleur === 4) {
      r = g = b = lignes[src]; a = lignes[src + 1];
    } else if (typeCouleur === 2) {
      r = lignes[src]; g = lignes[src + 1]; b = lignes[src + 2];
    } else if (typeCouleur === 6) {
      r = lignes[src]; g = lignes[src + 1]; b = lignes[src + 2]; a = lignes[src + 3];
    } else {                                   /* palette */
      var idx = lignes[src];
      r = palette[idx * 3]; g = palette[idx * 3 + 1]; b = palette[idx * 3 + 2];
      if (alphaPalette && idx < alphaPalette.length) { a = alphaPalette[idx]; }
    }
    data[dst] = r; data[dst + 1] = g; data[dst + 2] = b; data[dst + 3] = a;
  }

  return { data: data, width: largeur, height: hauteur };
}

module.exports = { lirePNG: lirePNG };
