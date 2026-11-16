"""Régénère les scénarios d'exemple : trajectoires (CSV) et événements (CSV).

Tout est fabriqué avec ``cfd_trajcast.core.manoeuvres`` (point matériel piloté par
segments) : aucune donnée extérieure. La maquette est la CAO de l'exemple
(``../MAQUETTE/Aim9.stl``), y compris pour les trajectoires d'avion. Lancer depuis
n'importe où ::

    python generer_scenarios.py

Scénarios :

* ``avion_manoeuvres`` — roulage, décollage, montée, virage à 60°, boucle, tonneau,
  descente en virage, palier ;
* ``avion_panne``      — croisière à 4 000 m, panne moteur, plané, grand virage,
  perte de contrôle et spirale jusqu'à 150 m (fictif) ;
* ``fusee_bi_etage``   — fusée à deux étages : virage gravitaire, deux combustions,
  apogée à 15 km.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from cfd_trajcast.core.manoeuvres import Conditions, Mobile, Segment, Simulation, simuler

ICI = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------------------------
# Scénarios
# ---------------------------------------------------------------------------------------------
def avion_manoeuvres() -> Simulation:
    return simuler(Conditions(cap=0.0), [
        Segment(25, "Mise en puissance", vitesse=85, pente=0, inclinaison=0, au_sol=True),
        Segment(18, "Rotation", vitesse=130, pente=12),
        Segment(30, "Montée", vitesse=190, pente=15),
        Segment(8, "Palier", vitesse=210, pente=0),
        Segment(22, "Virage à 60°", inclinaison=60),
        Segment(6, "Ailes à plat", inclinaison=0),
        Segment(33, "Boucle", vitesse=230, facteur_charge=4.5, taux_roulis=0),
        Segment(5, "Rétablissement", pente=0, inclinaison=0),
        Segment(3, "Tonneau", taux_roulis=120, facteur_charge=1.0),
        Segment(5, "Stabilisation", inclinaison=0, pente=0),
        Segment(25, "Descente en virage", vitesse=170, pente=-8, inclinaison=30),
        Segment(10, "Palier final", pente=0, inclinaison=0),
    ])


def avion_panne() -> Simulation:
    return simuler(Conditions(position=(0.0, 0.0, 4000.0), vitesse=150.0, cap=0.0), [
        Segment(15, "Croisière", vitesse=150, pente=0, inclinaison=0),
        Segment(20, "Panne moteur", poussee=0, pente=-5),
        Segment(40, "Grand virage", pente=-7, inclinaison=45),
        Segment(6, "Perte de contrôle", facteur_charge=0.8, inclinaison=70),
        Segment(90, "Spirale", facteur_charge=1.8, inclinaison=82),
    ], arret_sous=150.0)


def fusee_bi_etage() -> Simulation:
    return simuler(Conditions(vitesse=1.0, cap=30.0, pente=84.0, facteur_charge=0.0), [
        Segment(3, "Allumage étage 1", poussee=110, facteur_charge=0, taux_roulis=60),
        Segment(2, "Séparation", poussee=0),
        Segment(8, "Allumage étage 2", poussee=45),
        Segment(62, "Fin de propulsion", poussee=0),
    ], Mobile.fusee())


def ecrire(nom: str, sim: Simulation, description: str) -> None:
    q, p, d = sim.attitudes, sim.positions, sim.donnees
    df = pd.DataFrame({"t": sim.t, "x": p[:, 0], "y": p[:, 1], "z": p[:, 2],
                       "qw": q[:, 0], "qx": q[:, 1], "qy": q[:, 2], "qz": q[:, 3],
                       "V": d["V"], "mach": d["mach"], "n": d["n"], "inclinaison": d["inclinaison"],
                       "pente": d["pente"], "cap": d["cap"], "incidence": d["incidence"]})
    with open(ICI / f"{nom}.csv", "w", encoding="utf-8") as f:
        f.write(f"# {description} — généré par generer_scenarios.py (cfd_trajcast.core.manoeuvres)\n")
        df.to_csv(f, index=False, float_format="%.8g")
    evts = pd.DataFrame({"t": [t for t, _ in sim.evenements], "nom": [n for _, n in sim.evenements]})
    k = int(np.argmax(p[:, 2]))
    if 0 < k < len(p) - 1:
        evts = pd.concat([evts, pd.DataFrame({"t": [sim.t[k]], "nom": ["Point culminant"]})])
    evts.sort_values("t").to_csv(ICI / f"{nom}_evenements.csv", index=False, float_format="%.3f")
    print(f"{nom}.csv : {len(df)} lignes, {sim.t[-1]:.1f} s, altitude {p[:, 2].min():.0f} → {p[:, 2].max():.0f} m")


def main() -> None:
    ecrire("avion_manoeuvres", avion_manoeuvres(), "avion : décollage, montée, virage, boucle, tonneau")
    ecrire("avion_panne", avion_panne(), "avion : panne moteur, grand virage, spirale (fictif)")
    ecrire("fusee_bi_etage", fusee_bi_etage(), "fusée à deux étages, virage gravitaire")


if __name__ == "__main__":
    main()
