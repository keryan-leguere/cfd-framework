"""Why a ridge is not the sum of its two steps.

Reproduces the observation of AGARD-AG-264 §4.3.2.1: superposing a forward and
a rearward step underestimates the measured square-ridge drag by about half at
low Mach number, and the deficit has gone by M = 2.8.

    ${CFD_AQ_PYTHON:-python3} 02_arete_contre_deux_marches.py
"""

from __future__ import annotations

from cfd_aq import interference_arete, ratio_marche_descendante, ratio_marche_montante

H_PLUS = 1000.0

print(f"h⁺ = {H_PLUS:g}\n")
print(
    f"{'M':>5} {'montante':>10} {'descendante':>12} {'somme':>8} {'arête':>8} {'somme/arête':>12}"
)
for mach in (0.2, 0.5, 0.8, 1.0, 1.2, 1.4, 1.7, 2.0, 2.2, 2.8):
    arete, somme, rapport = interference_arete(H_PLUS, mach)
    print(
        f"{mach:5.1f} {ratio_marche_montante(H_PLUS, mach):10.1f} "
        f"{ratio_marche_descendante(H_PLUS, mach):12.1f} {somme:8.1f} {arete:8.1f} "
        f"{rapport:12.3f}"
    )
print(
    "\nLa colonne de droite est la traînée d'interférence : à bas Mach, le bulbe de "
    "recirculation\nde la face amont n'a pas recollé quand il rencontre la face aval, "
    "et l'interférence\npèse autant que les deux marches réunies."
)
