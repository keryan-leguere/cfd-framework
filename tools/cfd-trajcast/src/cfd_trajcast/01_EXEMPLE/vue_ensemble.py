"""La vue d'ensemble depuis Python : figure paper du vol entier, schéma SVG, puis vidéo MP4.

::

    python vue_ensemble.py               # figure + SVG + vidéo d'aperçu rendue en 3D (540p, 15 ips)
    python vue_ensemble.py --sans-rendu  # … vidéo = la figure animée (ni OpenGL ni GPU)
    python vue_ensemble.py --complet     # vidéo en pleine résolution (1080p, 30 ips)
    python vue_ensemble.py --svg-seul    # figures seulement, pas de vidéo

Équivalent en ligne de commande : ``cfd-trajcast ensemble CONFIG_ENSEMBLE.yaml --video
[--sans-rendu]``. La figure paper et l'animation demandent cfd-plot (``tools/cfd-plot``).
Tout ce qui est écrit va dans ``SORTIE_ENSEMBLE/``, à côté de ce script.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cfd_trajcast import VueEnsemble
from cfd_trajcast.engine.figure_ensemble import cfd_plot_disponible

ICI = Path(__file__).resolve().parent
SORTIE = ICI / "SORTIE_ENSEMBLE"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--complet", action="store_true", help="vidéo en pleine résolution")
    parser.add_argument("--svg-seul", action="store_true", help="pas de vidéo")
    parser.add_argument("--sans-rendu", action="store_true", help="vidéo = la figure animée, sans rendu 3D")
    args = parser.parse_args()
    SORTIE.mkdir(exist_ok=True)

    # 1. Charger : n'importe quel fichier de configuration convient. Les réglages de la vue
    #    (azimut, élévation, agrandissement de la maquette) sont ceux de sa vue `mode: ensemble`
    #    s'il en a une — ici `ensemble` dans CONFIG_ENSEMBLE.yaml —, sinon ceux par défaut.
    vue = VueEnsemble.depuis_yaml(ICI / "CONFIG_ENSEMBLE.yaml")
    #    Sans fichier YAML, depuis des objets déjà construits :
    #      VueEnsemble(trajectoire, maquette, parametres=ParametresEnsemble(azimut=200, elevation=25))

    # 2. La figure paper (Matplotlib + style `paper` de cfd-plot) : PDF, SVG et PNG 300 dpi, 12 cm
    #    de large, NED classique (ou local avec `repere: ned_local` dans la vue), proportions
    #    vraies, projection orthographique. Le titre va dans la légende de l'article : la
    #    légende proposée est rendue avec la figure.
    if cfd_plot_disponible():
        figure = vue.figure(SORTIE / "vol_ensemble_figure", largeur_cm=12.0)
        print(f"{', '.join(p.name for p in figure.fichiers)} : {figure.taille_cm[0]:.1f} × "
              f"{figure.taille_cm[1]:.1f} cm\n  légende : {figure.legende}")
        #    Variante : une colonne d'article, perspective, PDF seul.
        vue.figure(SORTIE / "vol_ensemble_colonne", largeur_cm=8.5, projection="persp", formats=("pdf",))
    else:
        print("cfd-plot absent : pas de figure paper (pip install tools/cfd-plot)")

    # 3. Le schéma SVG maison du vol entier — aucune dépendance, une fraction de seconde. Par défaut, la
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

    def progression(fait: int, total: int) -> None:
        print(f"\r  {fait}/{total} images", end="", flush=True)

    # 4a. Sans rendu 3D : la figure animée — le vol se trace, la maquette le parcourt avec son
    #     attitude, les événements s'allument ; cadence, durée et ralentis viennent de `video`.
    if args.sans_rendu:
        animation = vue.animer(SORTIE / "vol_ensemble_anime.mp4", apercu=not args.complet,
                               progression=progression)
        print(f"\n{animation.chemin} : {animation.taille[0]}×{animation.taille[1]}, {animation.duree:.1f} s")
        return

    # 4b. La vidéo MP4 rendue en 3D (PyVista), tout le vol : format, titres, bandeaux d'événements et
    #    télémétrie (bande à droite) sont repris du fichier ; `telemetrie=False` l'enlève.
    resultat = vue.rendre(SORTIE / "vol_ensemble.mp4", apercu=not args.complet, progression=progression)
    print(f"\n{resultat.chemin} : {resultat.largeur}×{resultat.hauteur}, {resultat.duree_video:.1f} s de vidéo, "
          f"rendue en {resultat.secondes:.0f} s")

    #    Variantes : sans télémétrie, en 20 s de vidéo, format portrait (vol presque vertical) ;
    #    ou une seule image, pour régler la caméra avant de lancer la vidéo.
    vue.image(40.565, SORTIE / "apogee.png", telemetrie=False, resolution=(1080, 1920))
    # vue.rendre(SORTIE / "vol_portrait.mp4", telemetrie=False, duree=20, resolution=(1080, 1920))


if __name__ == "__main__":
    main()
