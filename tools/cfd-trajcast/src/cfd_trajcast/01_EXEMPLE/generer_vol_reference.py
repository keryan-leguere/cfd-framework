"""Régénère les CSV d'exemple : le vol de référence (deux conventions) et un vol à virage.

* ``vol_reference.csv``       : ENU, quaternion ``qw qx qy qz`` corps FRD → ENU, plus deux
  grandeurs d'intérêt à afficher en télémétrie : ``q0`` (pression dynamique, Pa, ISA)
  et ``roulis`` (°) ;
* ``vol_reference_euler.csv`` : NED, angles d'Euler ZYX (lacet, tangage, roulis) en degrés.

Le vol est analytique (``cfd_trajcast.core.vol_reference``) : propulsion rectiligne
4 s à 100 m/s², puis balistique ; nez dans la vitesse, roulis de 90 °/s.

* ``vol_virage.csv`` : le même vol dont la route horizontale tourne de 70° vers la
  droite entre 6 et 20 s (de quoi éprouver le lissage des caméras). Vitesse intégrée
  au pas de 1 ms ; attitude **construite** pour ce fichier d'exemple (nez dans la
  vitesse, même roulis) — le paquet, lui, ne déduit jamais l'attitude.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from cfd_trajcast.core import rotations as rot
from cfd_trajcast.core.atmosphere import masse_volumique
from cfd_trajcast.core.reperes import matrice_vers_enu, quaternion_vers_enu
from cfd_trajcast.core.vol_reference import VolReference

ICI = Path(__file__).resolve().parent
FREQUENCE = 20.0  # Hz
APRES_APOGEE = 15.0  # s


def main() -> None:
    vol = VolReference()
    t = np.round(np.arange(0.0, vol.t_apogee + APRES_APOGEE, 1 / FREQUENCE), 6)
    p = vol.position(t)
    q = vol.quaternion(t)
    e = np.degrees(vol.euler_ned(t))
    enu = pd.DataFrame({"t": t, "x": p[:, 0], "y": p[:, 1], "z": p[:, 2],
                        "qw": q[:, 0], "qx": q[:, 1], "qy": q[:, 2], "qz": q[:, 3],
                        "q0": vol.pression_dynamique(t), "roulis": e[:, 2]})
    ned = p @ matrice_vers_enu("NED")  # M orthogonale et symétrique : p_NED = M.T p_ENU
    euler = pd.DataFrame({"t": t, "n": ned[:, 0], "e": ned[:, 1], "d": ned[:, 2],
                          "lacet": e[:, 0], "tangage": e[:, 1], "roulis": e[:, 2]})
    entete = (f"# vol de référence analytique — fin de propulsion {vol.duree_propulsion:g} s, "
              f"Mach 1 à {vol.t_mach_1:.3f} s, apogée à {vol.t_apogee:.3f} s\n")
    for nom, df in (("vol_reference.csv", enu), ("vol_reference_euler.csv", euler)):
        with open(ICI / nom, "w", encoding="utf-8") as f:
            f.write(entete)
            df.to_csv(f, index=False, float_format="%.10g")
        print(f"{nom} : {len(df)} lignes")
    ecrire_virage(vol)


#: Virage : +70° de route entre 6 et 20 s de vol, profil en douceur.
VIRAGE_DEBUT, VIRAGE_FIN, VIRAGE_ANGLE = 6.0, 20.0, 70.0


def ecrire_virage(vol: VolReference) -> None:
    pas = 1e-3
    t_fin = vol.t_apogee + APRES_APOGEE
    t = np.arange(0.0, t_fin + pas / 2, pas)
    u = np.clip((t - VIRAGE_DEBUT) / (VIRAGE_FIN - VIRAGE_DEBUT), 0, 1)
    dpsi = np.radians(VIRAGE_ANGLE) * u * u * (3 - 2 * u)
    v_ref = vol.vitesse(t)
    # Route tournée vers la droite (sens horaire vu du dessus) : rotation de −Δψ autour de z.
    c, s_ = np.cos(-dpsi), np.sin(-dpsi)
    v = np.stack([c * v_ref[:, 0] - s_ * v_ref[:, 1], s_ * v_ref[:, 0] + c * v_ref[:, 1], v_ref[:, 2]], axis=1)
    p = np.concatenate([np.zeros((1, 3)), np.cumsum((v[1:] + v[:-1]) / 2 * pas, axis=0)])
    # Attitude : nez dans la vitesse (direction de rampe tant que la vitesse est nulle), roulis 90 °/s.
    lacet = np.arctan2(v[:, 0], v[:, 1])
    tangage = np.arctan2(v[:, 2], np.hypot(v[:, 0], v[:, 1]))
    depart = np.linalg.norm(v, axis=1) < 1e-9
    lacet[depart], tangage[depart] = vol.euler_ned(t[depart])[:, 0], vol.euler_ned(t[depart])[:, 1]
    roulis = (np.radians(vol.vitesse_roulis) * t + np.pi) % (2 * np.pi) - np.pi
    euler = np.stack([lacet, tangage, roulis], axis=1)
    q, _ = rot.continuite_hemisphere(quaternion_vers_enu(rot.depuis_euler(euler, "ZYX"), "NED"))
    garde = np.arange(0, len(t), round(1 / (FREQUENCE * pas)))
    q0 = 0.5 * masse_volumique(p[:, 2]) * np.sum(v**2, axis=1)
    df = pd.DataFrame({"t": np.round(t[garde], 6), "x": p[garde, 0], "y": p[garde, 1], "z": p[garde, 2],
                       "qw": q[garde, 0], "qx": q[garde, 1], "qy": q[garde, 2], "qz": q[garde, 3],
                       "q0": q0[garde], "roulis": np.degrees(roulis[garde]),
                       "route": np.degrees(np.arctan2(v[garde, 0], v[garde, 1]))})
    with open(ICI / "vol_virage.csv", "w", encoding="utf-8") as f:
        f.write(f"# vol à virage : route +{VIRAGE_ANGLE:g}° entre {VIRAGE_DEBUT:g} et {VIRAGE_FIN:g} s ; "
                f"apogée à {vol.t_apogee:.3f} s\n")
        df.to_csv(f, index=False, float_format="%.10g")
    print(f"vol_virage.csv : {len(df)} lignes")


if __name__ == "__main__":
    main()
