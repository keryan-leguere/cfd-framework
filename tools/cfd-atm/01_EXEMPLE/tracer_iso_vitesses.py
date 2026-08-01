#!/usr/bin/env python3
"""Exemple cfd-atm : tracer les iso-Vc (et iso-TAS) via le package `cfd_plot`.

Produit trois figures dans ``SORTIE/`` :

1. ``diagramme_A_isoVc_altitude_geometrique`` — iso-Vc sur Mach vs altitude
   géométrique ; les modèles ISA / ISA+35 / ISA−35 / custom **divergent** car la
   pression à altitude géométrique fixée dépend du profil de température.
2. ``diagramme_B_isoVc_isoTAS_altitude_pression`` — sur Mach vs altitude-pression,
   les iso-Vc (indépendantes de T°) sont tracées une fois, tandis que les iso-TAS
   se séparent selon le modèle.
3. ``profils_temperature`` — les profils T(z) des quatre modèles.

Le style maison vient du paquet `cfd-plot` (``pip install -e tools/cfd-plot``).
S'il n'est pas installé, on retombe sur Matplotlib brut.
"""

from __future__ import annotations

from pathlib import Path

from cfd_atm.core.atmosphere import AtmosphereModel, temperature_profile_from_table
from cfd_atm.report.figures import generer_diagrammes

ICI = Path(__file__).resolve().parent


def _charger_profil_custom() -> AtmosphereModel:
    import yaml

    data = yaml.safe_load((ICI / "profil_T_custom.yaml").read_text(encoding="utf-8"))
    rows = data["profil"]
    h = [float(r["altitude_m"]) for r in rows]
    t = [float(r["temperature_K"]) for r in rows]
    return AtmosphereModel.custom(temperature_profile_from_table(h, t), label=str(data["nom"]).split(" —")[0])


def main() -> None:
    custom = _charger_profil_custom()
    sortie = ICI / "SORTIE"
    written = generer_diagrammes(sortie, custom=custom, delta_plus=35.0, delta_moins=-35.0)
    print(f"{len(written)} fichiers écrits dans {sortie} :")
    for path in written:
        print(f"  - {path.name}")


if __name__ == "__main__":
    main()
