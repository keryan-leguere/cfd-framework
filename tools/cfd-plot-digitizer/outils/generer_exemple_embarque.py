#!/usr/bin/env python3
"""Régénère app/js/80_exemple.js à partir de exemples/.

L'image de démonstration est embarquée en data URL dans un fichier JavaScript
plutôt que chargée depuis exemples/ : sur une page ouverte en file://, Firefox
donne au document une origine opaque, si bien qu'une image lue depuis un
fichier voisin « teinte » le canevas et interdit getImageData — donc toute
détection. Une data URL est de même origine et échappe à cette règle.

    python3 outils/generer_exemple_embarque.py

Bibliothèque standard uniquement.
"""
import base64
import io
import json
import pathlib

RACINE = pathlib.Path(__file__).resolve().parent.parent
FIGURE = "exemple_polaire.png"

GABARIT = '''/*
 * 80_exemple.js — figure de démonstration embarquée.
 *
 * L'image est inscrite en data URL plutôt que chargée depuis exemples/ : sur
 * une page ouverte en file://, Firefox attribue une origine opaque au document,
 * si bien qu'une image chargée depuis un fichier voisin « teinte » le canevas
 * et rend getImageData impossible — donc toute détection impossible. Une data
 * URL est de même origine et échappe à cette règle.
 *
 * Fichier ENGENDRÉ — ne pas modifier à la main. Régénérer avec :
 *     python3 outils/generer_exemple_embarque.py
 */
(function (racine) {
  'use strict';

  var CFDD = racine.CFDD || (racine.CFDD = {});

  var BASE64 =
%(bloc)s;

  CFDD.Exemple = {
    nom: '%(nom)s',
    dataURL: 'data:image/png;base64,' + BASE64,

    /*
     * Pré-remplit calibration, zone et exclusion de légende, pour que le bouton
     * « Exemple » donne un cas complet à explorer plutôt qu'une image nue.
     * Les repères viennent des coordonnées exactes de matplotlib : la
     * calibration est donc parfaite, et l'écart observé ne mesure que l'outil.
     */
    appliquer: function (etat, rafraichir) {
      var reperes = %(reperes)s;
      Object.keys(reperes).forEach(function (cle) {
        etat.reperes[cle] = { px: reperes[cle].px, py: reperes[cle].py };
        etat.valeurs[cle] = String(reperes[cle].valeur);
      });
      etat.logX = false;
      etat.logY = false;
      etat.zone = %(zone)s;
      etat.exclusions = [%(legende)s];
      etat.detection.couleur = '%(couleur)s';
      etat.detection.orientation = 'lignes';   /* polaire : Cx est fonction de Cz */

      var champLogX = document.getElementById('log-x');
      var champLogY = document.getElementById('log-y');
      if (champLogX) { champLogX.checked = false; }
      if (champLogY) { champLogY.checked = false; }
      var champCouleur = document.getElementById('couleur-cible');
      if (champCouleur) { champCouleur.value = '%(couleur)s'; }
      var champOrientation = document.getElementById('orientation');
      if (champOrientation) { champOrientation.value = 'lignes'; }

      if (rafraichir) { rafraichir(); }
    }
  };
})(typeof globalThis !== 'undefined' ? globalThis : this);
'''


def main():
    png = (RACINE / "exemples" / FIGURE).read_bytes()
    with open(RACINE / "exemples" / "reference.json", encoding="utf-8") as f:
        ref = json.load(f)[FIGURE]

    b64 = base64.b64encode(png).decode("ascii")
    # Lignes courtes : un fichier engendré reste lisible et diffable.
    lignes = [b64[i:i + 96] for i in range(0, len(b64), 96)]
    bloc = "\n".join("    '%s' +" % ligne for ligne in lignes).rstrip(" +")

    cadres = ref["cadres"]
    reperes = {
        cle: {"px": round(v["px"], 2), "py": round(v["py"], 2), "valeur": v["valeur"]}
        for cle, v in ref["calibration"]["reperes"].items()
    }
    zone = {"x0": int(cadres["trace"]["x0"]) + 2, "y0": int(cadres["trace"]["y0"]) + 2,
            "x1": int(cadres["trace"]["x1"]) - 2, "y1": int(cadres["trace"]["y1"]) - 2}
    legende = {"x0": int(cadres["legende"]["x0"]) - 2, "y0": int(cadres["legende"]["y0"]) - 2,
               "x1": int(cadres["legende"]["x1"]) + 2, "y1": int(cadres["legende"]["y1"]) + 2}

    source = GABARIT % {
        "bloc": bloc,
        "nom": FIGURE,
        "reperes": json.dumps(reperes, ensure_ascii=False),
        "zone": json.dumps(zone),
        "legende": json.dumps(legende),
        "couleur": list(ref["couleurs"].values())[0],
    }
    cible = RACINE / "app" / "js" / "80_exemple.js"
    with io.open(cible, "w", encoding="utf-8") as f:
        f.write(source)
    print("%s écrit (%.0f ko)" % (cible.relative_to(RACINE), len(source) / 1024))


if __name__ == "__main__":
    main()
