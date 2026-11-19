"""La vue d'ensemble depuis Python : schéma SVG du vol entier, puis sa vidéo MP4.

::

    python vue_ensemble.py             # SVG (instantané) + vidéo d'aperçu (540p, 15 ips)
    python vue_ensemble.py --complet   # vidéo en pleine résolution (1080p, 30 ips)
    python vue_ensemble.py --svg-seul  # sans rendu 3D du tout

Équivalent en ligne de commande : ``cfd-trajcast ensemble CONFIG_ENSEMBLE.yaml --video``.
Tout ce qui est écrit va dans ``SORTIE_ENSEMBLE/``, à côté de ce script.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cfd_trajcast import VueEnsemble

ICI = Path(__file__).resolve().parent
SORTIE = ICI / "SORTIE_ENSEMBLE"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--complet", action="store_true", help="vidéo en pleine résolution")
    parser.add_argument("--svg-seul", action="store_true", help="pas de vidéo")
    args = parser.parse_args()
    SORTIE.mkdir(exist_ok=True)

    # 1. Charger : n'importe quel fichier de configuration convient. Les réglages de la vue
    #    (azimut, élévation, agrandissement de la maquette) sont ceux de sa vue `mode: ensemble`
    #    s'il en a une — ici `ensemble` dans CONFIG_ENSEMBLE.yaml —, sinon ceux par défaut.
    vue = VueEnsemble.depuis_yaml(ICI / "CONFIG_ENSEMBLE.yaml")
    #    Sans fichier YAML, depuis des objets déjà construits :
    #      VueEnsemble(trajectoire, maquette, parametres=ParametresEnsemble(azimut=200, elevation=25))

    # 2. Le schéma SVG du vol entier — aucun moteur 3D, une fraction de seconde. Par défaut, la
    #    maquette est posée à chaque événement (sauf deux trop proches à l'écran).
    schema = vue.svg(SORTIE / "vol_ensemble.svg")
    print(f"{schema.chemin} : {schema.largeur}×{schema.hauteur} px, maquette × {schema.echelle:.0f} "
          f"posée à {', '.join(f'{t:.1f} s' for t in schema.poses)}")

    #    Variantes : thème sombre, maquette à des instants choisis (secondes ou noms d'événements),
    #    sans titre, plus petit.
    vue.svg(SORTIE / "vol_ensemble_sombre.svg", theme="sombre", poses=[10.0, 25.0, "Apogée", 52.0],
            titre="", sous_titre="", taille=900)
    #    Le texte SVG est aussi disponible sans rien écrire (pour l'insérer dans un rapport HTML…) :
    texte_svg = vue.schema(poses=0).svg
    print(f"schéma sans maquette : {len(texte_svg) / 1000:.0f} ko de SVG en mémoire")

    if args.svg_seul:
        return

    # 3. La vidéo MP4 de la vue d'ensemble, tout le vol : format, titres, bandeaux d'événements et
    #    télémétrie (bande à droite) sont repris du fichier ; `telemetrie=False` l'enlève.
    def progression(fait: int, total: int) -> None:
        print(f"\r  rendu {fait}/{total} images", end="", flush=True)

    resultat = vue.rendre(SORTIE / "vol_ensemble.mp4", apercu=not args.complet, progression=progression)
    print(f"\n{resultat.chemin} : {resultat.largeur}×{resultat.hauteur}, {resultat.duree_video:.1f} s de vidéo, "
          f"rendue en {resultat.secondes:.0f} s")

    #    Variantes : sans télémétrie, en 20 s de vidéo, format portrait (vol presque vertical) ;
    #    ou une seule image, pour régler la caméra avant de lancer la vidéo.
    vue.image(40.565, SORTIE / "apogee.png", telemetrie=False, resolution=(1080, 1920))
    # vue.rendre(SORTIE / "vol_portrait.mp4", telemetrie=False, duree=20, resolution=(1080, 1920))


if __name__ == "__main__":
    main()
