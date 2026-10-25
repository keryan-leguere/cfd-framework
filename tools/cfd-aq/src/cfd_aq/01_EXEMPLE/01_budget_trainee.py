"""Drag budget of a panel-joint pattern, and what smoothing it is worth.

Answers the question a manufacturing tolerance discussion actually turns on:
*how many counts of drag does this step buy or cost?* Run it with::

    ${CFD_AQ_PYTHON:-python3} 01_budget_trainee.py
"""

from __future__ import annotations

from cfd_aq import (
    Asperite,
    CoucheLimite,
    EtatLocal,
    TypeAsperite,
    calculer_trainee,
)

# Croisière FL360, conditions LOCALES sur l'extrados.
#
# EtatLocal.atmosphere passe par le paquet frère cfd-atm : on pourrait tout
# aussi bien écrire vitesse_conventionnelle=140.4 au lieu du Mach, ou
# delta_isa=15 pour une journée chaude, ou type_altitude="pression".
ETAT = EtatLocal.atmosphere(altitude=11000.0, mach=0.88)
COUCHE = CoucheLimite.plaque_plane(ETAT, distance_bord_attaque=8.5)
# plaque_plane renseigne toujours δ ; l'assertion le dit au typeur.
assert COUCHE.epaisseur is not None

SURFACE_REFERENCE = 122.6  # m²
ENVERGURE_JOINT = 11.0  # m
NOMBRE_DE_JOINTS = 6

print(
    f"q_e = {ETAT.pression_dynamique:,.0f} Pa, C_fe = {COUCHE.cf:.6f}, "
    f"τ_w = {COUCHE.cisaillement_paroi:.2f} Pa, δ = {COUCHE.epaisseur * 1e3:.0f} mm"
)
print()
print(f"{'h [mm]':>8} {'h+':>7} {'CDe/Cfe':>9} {'ΔD [N]':>9} {'ΔCx [cts]':>11}")

for hauteur_mm in (0.2, 0.5, 1.0, 1.5, 2.0, 3.0):
    asperite = Asperite(
        type_asperite=TypeAsperite.MONTANTE,
        hauteur=hauteur_mm * 1e-3,
        envergure=ENVERGURE_JOINT,
    )
    resultat = calculer_trainee(asperite, ETAT, COUCHE, surface_reference=SURFACE_REFERENCE)
    # 1 « count » de traînée = 1e-4 en coefficient.
    counts = NOMBRE_DE_JOINTS * (resultat.delta_cx or 0.0) * 1e4
    print(
        f"{hauteur_mm:8.1f} {resultat.h_plus:7.0f} {resultat.cde_sur_cfe:9.1f} "
        f"{NOMBRE_DE_JOINTS * resultat.trainee:9.1f} {counts:11.3f}"
    )

print()
print("Un joint vif contre un joint cassé à 30°, h = 1,5 mm :")
for angle in (90.0, 45.0, 30.0, 15.0):
    asperite = Asperite(
        type_asperite=TypeAsperite.MONTANTE,
        hauteur=1.5e-3,
        envergure=ENVERGURE_JOINT,
        angle_chanfrein=angle,
    )
    resultat = calculer_trainee(asperite, ETAT, COUCHE, surface_reference=SURFACE_REFERENCE)
    print(
        f"  θ = {angle:4.0f}°  facteur {resultat.facteur_forme:.3f}  ΔD = {resultat.trainee:6.2f} N"
    )
