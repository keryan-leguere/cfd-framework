"""Vol RocketPy de l'exemple : une fusée-sonde amateur générique (moteur à poudre, deux parachutes).

Tout est dans ce fichier pour tourner hors ligne : atmosphère standard (pas de
téléchargement météo), courbe de poussée donnée point par point, traînée constante.
Les valeurs sont celles d'une petite fusée de club, sans prétention de réalisme ; la
maquette affichée (CONFIG_ROCKETPY.yaml) est la CAO de l'exemple, sans lien avec ce vol.

``cfd-trajcast`` appelle ``simuler()`` et lit le ``Flight`` renvoyé. Lancé seul, le
script affiche quelques instants clés ::

    python vol_rocketpy.py
"""

from __future__ import annotations

from typing import Any


def simuler() -> Any:
    from rocketpy import Environment, Flight, Rocket, SolidMotor

    env = Environment(latitude=43.6, longitude=1.44, elevation=150)
    env.set_atmospheric_model(type="standard_atmosphere")
    moteur = SolidMotor(
        thrust_source=[[0.0, 0.0], [0.1, 2200.0], [3.5, 1800.0], [3.9, 0.0]],
        dry_mass=1.8, dry_inertia=(0.125, 0.125, 0.002), nozzle_radius=0.033,
        grain_number=5, grain_density=1815, grain_outer_radius=0.033,
        grain_initial_inner_radius=0.015, grain_initial_height=0.12, grain_separation=0.005,
        grains_center_of_mass_position=0.397, center_of_dry_mass_position=0.317,
        nozzle_position=0, burn_time=3.9, throat_radius=0.011,
        coordinate_system_orientation="nozzle_to_combustion_chamber",
    )
    fusee = Rocket(radius=0.0635, mass=14.4, inertia=(6.3, 6.3, 0.034), power_off_drag=0.5,
                   power_on_drag=0.5, center_of_mass_without_motor=0,
                   coordinate_system_orientation="tail_to_nose")
    fusee.add_motor(moteur, position=-1.255)
    fusee.add_nose(length=0.558, kind="vonKarman", position=1.278)
    fusee.add_trapezoidal_fins(n=4, root_chord=0.120, tip_chord=0.060, span=0.110,
                               position=-1.050, cant_angle=0.5)
    fusee.add_tail(top_radius=0.0635, bottom_radius=0.0435, length=0.060, position=-1.195)
    fusee.set_rail_buttons(upper_button_position=0.082, lower_button_position=-0.618, angular_position=45)
    fusee.add_parachute("Extracteur", cd_s=1.0, trigger="apogee", sampling_rate=105, lag=1.5)
    fusee.add_parachute("Principal", cd_s=10.0, trigger=800, sampling_rate=105, lag=1.5)
    return Flight(rocket=fusee, environment=env, rail_length=5.2, inclination=85, heading=30,
                  terminate_on_apogee=False, name="Fusée-sonde de l'exemple")


if __name__ == "__main__":
    vol = simuler()
    print(f"sortie de rampe {vol.out_of_rail_time:.2f} s, apogée {vol.apogee_time:.1f} s, "
          f"fin {vol.t_final:.1f} s")
