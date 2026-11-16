"""Cohérence attitude/vitesse : une convention fausse est détectée et nommée."""

from __future__ import annotations

import numpy as np
from conftest import dataframe_enu_quaternion, dataframe_ned_euler

from cfd_trajcast.data.constats import ALERTE, ERREUR, INFO
from cfd_trajcast.data.trajectoire import Trajectoire
from cfd_trajcast.data.validation import verifier as _verifier

COLS_NED = {"x": "n", "y": "e", "z": "d"}


def verifier(traj: Trajectoire) -> list:  # type: ignore[type-arg]
    return _verifier(traj, coherence=True)


def _constat(constats: list, code: str):  # type: ignore[no-untyped-def]
    return next(c for c in constats if c.code == code)


def test_vol_correct_coherent() -> None:
    constats = verifier(Trajectoire.depuis_dataframe(dataframe_enu_quaternion(), repere="ENU", attitude="quaternion"))
    assert _constat(constats, "coherence").niveau == INFO
    assert not any(c.niveau in (ALERTE, ERREUR) for c in constats)


def test_quaternion_conjugue_detecte() -> None:
    traj = Trajectoire.depuis_dataframe(
        dataframe_enu_quaternion(), repere="ENU",
        attitude={"type": "quaternion", "sens": "reference_vers_corps"},
    )
    c = _constat(verifier(traj), "coherence")
    assert c.niveau == ALERTE
    assert "sens corps vers reference → 0.0°" in c.indice


def test_ordre_xyzw_detecte() -> None:
    df = dataframe_enu_quaternion()
    df[["q0", "q1", "q2", "q3"]] = df[["q1", "q2", "q3", "q0"]].to_numpy()  # écrit en xyzw
    traj = Trajectoire.depuis_dataframe(df, repere="ENU", attitude="quaternion")  # lu en wxyz
    c = _constat(verifier(traj), "coherence")
    assert c.niveau == ALERTE and "ordre xyzw → 0.0°" in c.indice


def test_ned_declare_enu_sans_montee() -> None:
    traj = Trajectoire.depuis_dataframe(
        dataframe_ned_euler(), repere="ENU", colonnes=COLS_NED, attitude="euler"
    )
    assert _constat(verifier(traj), "coherence_non_faite").niveau == ALERTE


def test_par_defaut_aucune_hypothese_de_vol() -> None:
    """Une trajectoire qui ne fait que descendre n'est pas suspecte par défaut."""
    df = dataframe_enu_quaternion()
    df["z"] = -df["z"]
    constats = _verifier(Trajectoire.depuis_dataframe(df, repere="ENU", attitude="quaternion"))
    assert not any(c.niveau in (ALERTE, ERREUR) for c in constats)
    assert not any(c.code.startswith("coherence") for c in constats)


def test_sequence_extrinseque_lue_intrinseque() -> None:
    traj = Trajectoire.depuis_dataframe(
        dataframe_ned_euler(), repere="NED", colonnes=COLS_NED,
        attitude={"type": "euler", "sequence": "zyx"},
    )
    c = _constat(verifier(traj), "coherence")
    assert c.niveau == ALERTE and "séquence ZYX (intrinsèque) → 0.0°" in c.indice


def test_unite_longueur_suspecte() -> None:
    df = dataframe_enu_quaternion()
    df[["x", "y", "z"]] *= 1000  # des mm écrits comme des m
    constats = verifier(Trajectoire.depuis_dataframe(df, repere="ENU", attitude="quaternion"))
    assert _constat(constats, "etendue").niveau == ALERTE
    assert _constat(constats, "mach_eleve").niveau == ALERTE


def test_attitude_d_un_autre_vol() -> None:
    df = dataframe_enu_quaternion()
    q = df[["q0", "q1", "q2", "q3"]].to_numpy()
    df[["q0", "q1", "q2", "q3"]] = np.roll(q, len(q) // 2, axis=0)
    c = _constat(verifier(Trajectoire.depuis_dataframe(df, repere="ENU", attitude="quaternion")), "coherence")
    assert c.niveau == ALERTE
