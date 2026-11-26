"""Le vent le long du vol depuis Python : roses Nord/Est + profil vertical, puis leur vidéo.

::

    python figures_vent.py              # figures + vidéo d'aperçu (540p, 15 ips)
    python figures_vent.py --complet    # vidéo en pleine résolution (1080p, 30 ips)
    python figures_vent.py --sans-video # figures seulement

Équivalent en ligne de commande : ``cfd-trajcast vent CONFIG_GUI.yaml --video --apercu``.
Demande cfd-plot (``tools/cfd-plot``). Tout ce qui est écrit va dans ``SORTIE_VENT/``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cfd_trajcast import VueVent

ICI = Path(__file__).resolve().parent
SORTIE = ICI / "SORTIE_VENT"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--complet", action="store_true", help="vidéo en pleine résolution")
    parser.add_argument("--sans-video", action="store_true", help="pas de vidéo")
    args = parser.parse_args()
    SORTIE.mkdir(exist_ok=True)

    # 1. Charger : le fichier doit déclarer une section `vent` (colonnes VN, VE, VZ et leurs
    #    conventions). CONFIG_GUI.yaml lit vol_vent_cdg.csv : un vent qui tourne avec
    #    l'altitude et un ascendant vers 2 500 m.
    vue = VueVent.depuis_yaml(ICI / "CONFIG_GUI.yaml")
    #    Sans YAML : VueVent(trajectoire, DeclarationVent(colonnes=("VN", "VE", "VZ"), vz="haut"))

    # 2. Figure par défaut : une rose par événement (Mach 1, fin de propulsion, apogée) sous le
    #    profil altitude(t), flèche = où va l'air. PDF, SVG et PNG 300 dpi, 16 cm de large.
    f = vue.figure(SORTIE / "vent_evenements")
    print(f"{', '.join(p.name for p in f.fichiers)} : {f.taille_cm[0]:.1f} × {f.taille_cm[1]:.1f} cm\n"
          f"  légende : {f.legende}")

    # 3. Huit instants répartis sur le vol, en convention météo (d'où vient le vent) : deux
    #    rangées de quatre roses à 16 cm, toutes au même rayon.
    f = vue.figure(SORTIE / "vent_8_instants", instants=8, sens="depuis", formats=("pdf", "png"))
    print(f"{', '.join(p.name for p in f.fichiers)} : rayon commun {f.rayon:g} m/s")

    # 4. Des instants choisis, événements compris par leur nom.
    vue.figure(SORTIE / "vent_choisis", instants=[2.0, 10.0, "Apogée"], formats=("svg",))

    # 5. La vidéo : rose et profil animés ensemble, sans rendu 3D (ni OpenGL ni GPU). Cadence,
    #    résolution et ralentis viennent de la section `video` du fichier.
    if not args.sans_video:
        a = vue.animer(SORTIE / "vent_anime.mp4", apercu=not args.complet, duree=20.0)
        print(f"{a.chemin.name} : {a.taille[0]}×{a.taille[1]}, {a.images} images, {a.duree:.1f} s")


if __name__ == "__main__":
    main()
