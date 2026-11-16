"""Lecture : le même vol, écrit sous toutes les conventions, donne la même trajectoire."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from conftest import VOL, T, dataframe_enu_quaternion, dataframe_ned_euler, q_ned

from cfd_trajcast.core import reperes
from cfd_trajcast.core import rotations as rot
from cfd_trajcast.data.trajectoire import (
    DeclarationAttitude,
    ErreurAttitude,
    ErreurTrajectoire,
    Evenement,
    Trajectoire,
)

COLS_NED = {"x": "n", "y": "e", "z": "d"}


def _verifier_exacte(traj: Trajectoire) -> None:
    np.testing.assert_allclose(traj.positions, VOL.position(traj.t), atol=1e-9)
    assert np.all(rot.angle_entre(traj.attitude, VOL.quaternion(traj.t)) < 1e-7)


def test_enu_quaternion() -> None:
    traj = Trajectoire.depuis_dataframe(dataframe_enu_quaternion(), repere="ENU", attitude="quaternion")
    _verifier_exacte(traj)
    assert traj.declaration.attitude.colonnes == ("q0", "q1", "q2", "q3")


def test_ned_euler() -> None:
    traj = Trajectoire.depuis_dataframe(
        dataframe_ned_euler(), repere="NED", colonnes=COLS_NED,
        attitude={"type": "euler", "sequence": "ZYX"},
    )
    _verifier_exacte(traj)


def test_ned_euler_extrinseque_equivalente() -> None:
    df = dataframe_ned_euler().rename(columns={"lacet": "a3", "roulis": "a1", "tangage": "a2"})
    traj = Trajectoire.depuis_dataframe(
        df, repere="NED", colonnes=COLS_NED,
        attitude={"type": "euler", "sequence": "xyz", "colonnes": ["a1", "a2", "a3"]},
    )
    _verifier_exacte(traj)


def test_xyzw_et_reference_vers_corps() -> None:
    q = rot.conjugue(VOL.quaternion(T))
    p = VOL.position(T)
    df = pd.DataFrame({"temps": T * 1e3, "E": p[:, 0] / 1e3, "N": p[:, 1] / 1e3, "U": p[:, 2] / 1e3,
                       "qx": q[:, 1], "qy": q[:, 2], "qz": q[:, 3], "qw": q[:, 0]})
    traj = Trajectoire.depuis_dataframe(
        df, repere="ENU", colonnes={"t": "temps", "x": "E", "y": "N", "z": "U"},
        unites={"temps": "ms", "longueur": "km"},
        attitude={"type": "quaternion", "colonnes": ["qx", "qy", "qz", "qw"], "ordre": "xyzw",
                  "sens": "reference_vers_corps"},
    )
    _verifier_exacte(traj)


def test_corps_flu() -> None:
    # Le même vol avec un corps FLU : q_FLU→ref = q_FRD→ref ⊗ q_FLU→FRD (demi-tour en x).
    q = rot.produit(q_ned(), [0.0, 1.0, 0.0, 0.0])
    p = VOL.position(T) @ reperes.matrice_vers_enu("NED")
    df = pd.DataFrame({"t": T, "n": p[:, 0], "e": p[:, 1], "d": p[:, 2],
                       "q0": q[:, 0], "q1": q[:, 1], "q2": q[:, 2], "q3": q[:, 3]})
    traj = Trajectoire.depuis_dataframe(
        df, repere="NED", colonnes=COLS_NED, attitude={"type": "quaternion", "corps": "FLU"}
    )
    _verifier_exacte(traj)


def test_csv(tmp_path: Path) -> None:
    chemin = tmp_path / "vol.csv"
    with open(chemin, "w", encoding="utf-8") as f:
        f.write("# commentaire\n")
        dataframe_enu_quaternion().to_csv(f, index=False, sep=";", float_format="%.12g")
    _verifier_exacte(Trajectoire.depuis_csv(chemin, repere="ENU", attitude="quaternion"))


def test_radians() -> None:
    df = dataframe_ned_euler()
    df[["lacet", "tangage", "roulis"]] = np.radians(df[["lacet", "tangage", "roulis"]])
    traj = Trajectoire.depuis_dataframe(
        df, repere="NED", colonnes=COLS_NED, unites={"angle": "rad"}, attitude="euler"
    )
    _verifier_exacte(traj)


def test_sans_attitude_refuse() -> None:
    df = dataframe_enu_quaternion().drop(columns=["q0", "q1", "q2", "q3"])
    with pytest.raises(ErreurAttitude, match="jamais déduite de la vitesse"):
        Trajectoire.depuis_dataframe(df, repere="ENU")
    with pytest.raises(ErreurAttitude, match="aucun des jeux connus"):
        Trajectoire.depuis_dataframe(df, repere="ENU", attitude="quaternion")


def test_attitude_ambigue() -> None:
    df = dataframe_enu_quaternion()
    df[["qw", "qx", "qy", "qz"]] = df[["q0", "q1", "q2", "q3"]].to_numpy()
    with pytest.raises(ErreurAttitude, match="plusieurs jeux"):
        Trajectoire.depuis_dataframe(df, repere="ENU", attitude="quaternion")


def test_repere_obligatoire() -> None:
    with pytest.raises(ErreurTrajectoire, match="repère non déclaré"):
        Trajectoire.depuis_dataframe(dataframe_enu_quaternion(), attitude="quaternion")


def test_colonne_absente() -> None:
    with pytest.raises(ErreurTrajectoire, match="'altitude' absente"):
        Trajectoire.depuis_dataframe(
            dataframe_enu_quaternion(), repere="ENU", attitude="quaternion", colonnes={"z": "altitude"}
        )


def test_temps_duplique() -> None:
    df = dataframe_enu_quaternion()
    df.loc[5, "t"] = df.loc[4, "t"]
    with pytest.raises(ErreurTrajectoire, match="dupliqué"):
        Trajectoire.depuis_dataframe(df, repere="ENU", attitude="quaternion")


def test_valeur_manquante() -> None:
    df = dataframe_enu_quaternion()
    df.loc[7, "x"] = np.nan
    with pytest.raises(ErreurTrajectoire, match="ligne de données 8"):
        Trajectoire.depuis_dataframe(df, repere="ENU", attitude="quaternion")


def test_norme_renormalisee_avec_alerte() -> None:
    df = dataframe_enu_quaternion()
    df[["q0", "q1", "q2", "q3"]] *= 1.001
    traj = Trajectoire.depuis_dataframe(df, repere="ENU", attitude="quaternion")
    assert [c.code for c in traj.constats] == ["norme_quaternion"]
    _verifier_exacte(traj)


def test_norme_refusee() -> None:
    df = dataframe_enu_quaternion()
    df[["q0", "q1", "q2", "q3"]] *= 1.1
    with pytest.raises(ErreurTrajectoire, match="pas des quaternions unitaires"):
        Trajectoire.depuis_dataframe(df, repere="ENU", attitude="quaternion")


def test_hemisphere_corrige() -> None:
    df = dataframe_enu_quaternion()
    df.loc[10:20, ["q0", "q1", "q2", "q3"]] *= -1
    traj = Trajectoire.depuis_dataframe(df, repere="ENU", attitude="quaternion")
    assert any(c.code == "hemisphere" and "2 changement" in c.message for c in traj.constats)
    assert np.all(np.sum(traj.attitude[1:] * traj.attitude[:-1], axis=1) > 0)


def test_blocage_cardan_signale() -> None:
    df = dataframe_ned_euler()
    df.loc[3, "tangage"] = 89.6
    traj = Trajectoire.depuis_dataframe(df, repere="NED", colonnes=COLS_NED, attitude="euler")
    assert any(c.code == "blocage_cardan" for c in traj.constats)


def test_etat_interpole() -> None:
    traj = Trajectoire.depuis_dataframe(dataframe_enu_quaternion(), repere="ENU", attitude="quaternion")
    tn = np.array([1.234, 20.0, 37.77])
    p, q = traj.etat(tn)
    np.testing.assert_allclose(p, VOL.position(tn), rtol=1e-5, atol=1e-3)
    assert np.all(np.degrees(rot.angle_entre(q, VOL.quaternion(tn))) < 0.05)


def test_grandeurs_derivees() -> None:
    traj = Trajectoire.depuis_dataframe(dataframe_enu_quaternion(), repere="ENU", attitude="quaternion")
    # Loin des bords et de la coupure de poussée (accélération discontinue).
    k = (traj.t > 0.3) & (traj.t < traj.t[-1] - 0.3) & (np.abs(traj.t - VOL.duree_propulsion) > 0.15)
    np.testing.assert_allclose(traj.vitesse[k], VOL.vitesse(traj.t)[k], atol=1e-6)
    assert traj.apogee[0] == pytest.approx(VOL.t_apogee, abs=0.05)
    np.testing.assert_allclose(traj.mach[k], VOL.mach(traj.t)[k], atol=2e-3)


def test_colonnes_en_plus_conservees_et_evenements() -> None:
    df = dataframe_enu_quaternion()
    df["poussee"] = 1.0
    traj = Trajectoire.depuis_dataframe(
        df, repere="ENU", attitude="quaternion", evenements=[Evenement(999.0, "trop tard")]
    )
    assert "poussee" in traj.donnees
    assert any(c.code == "evenement_hors_vol" for c in traj.constats)


def test_declaration_attitude_controlee() -> None:
    with pytest.raises(ErreurTrajectoire, match="3 colonnes attendues"):
        DeclarationAttitude(type="euler", colonnes=("a", "b"))
    with pytest.raises(ErreurTrajectoire, match="ordre"):
        DeclarationAttitude(type="quaternion", ordre="zyxw")
    with pytest.raises(ErreurTrajectoire, match="clés inconnues"):
        DeclarationAttitude.depuis({"type": "euler", "seq": "ZYX"})
