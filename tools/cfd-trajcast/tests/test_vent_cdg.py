"""Vent et CDG variable : conventions déclarées, conversion, placement de la maquette."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from conftest import dataframe_enu_quaternion

from cfd_trajcast.data.cdg import DeclarationCdg, ErreurCdg, cdg_corps, point_reference
from cfd_trajcast.data.configuration import ErreurConfiguration, charger_configuration
from cfd_trajcast.data.maquette import Maquette
from cfd_trajcast.data.trajectoire import Trajectoire
from cfd_trajcast.data.vent import DeclarationVent, ErreurVent, vent_enu
from cfd_trajcast.engine.etat_vol import EtatVol


@pytest.fixture
def maquette(exemple: Path) -> Maquette:
    return Maquette.depuis_fichier(exemple / "MAQUETTE" / "Aim9.stl", unite="mm", axe_nez="-X",
                                   axe_haut="+Z", origine=(19.05, 0, 0), longueur_imposee=2.87)


@pytest.fixture
def traj() -> Trajectoire:
    df = dataframe_enu_quaternion()
    n = len(df)
    df = df.assign(VN=np.full(n, 3.0), VE=np.full(n, 4.0), VZ=np.full(n, 1.0),
                   Xcg=np.linspace(1.6, 1.4, n), Xmm=np.linspace(1600.0, 1400.0, n),
                   Ycg=np.zeros(n), Zcg=np.full(n, 0.01))
    return Trajectoire.depuis_dataframe(df, repere="ENU", attitude="quaternion")


# -- vent -------------------------------------------------------------------------------------
@pytest.mark.parametrize(("vz", "sens", "unite", "attendu"), [
    ("haut", "vers", "m/s", [4.0, 3.0, 1.0]),
    ("bas", "vers", "m/s", [4.0, 3.0, -1.0]),
    ("haut", "depuis", "m/s", [-4.0, -3.0, -1.0]),
    ("haut", "vers", "km/h", [4 / 3.6, 3 / 3.6, 1 / 3.6]),
])
def test_vent_conventions(traj: Trajectoire, vz: str, sens: str, unite: str, attendu: list[float]) -> None:
    v = vent_enu(traj, DeclarationVent(("VN", "VE", "VZ"), vz=vz, sens=sens, unite=unite))
    np.testing.assert_allclose(v[0], attendu)


def test_vent_refus(traj: Trajectoire) -> None:
    with pytest.raises(ErreurVent, match="absente"):
        vent_enu(traj, DeclarationVent(("VN", "VE", "W"), vz="haut"))
    with pytest.raises(ErreurVent, match="vz"):
        DeclarationVent(("VN", "VE", "VZ"), vz="monte")
    with pytest.raises(ErreurVent, match="obligatoire"):
        DeclarationVent.depuis_dict({"colonnes": ["VN", "VE", "VZ"]})


# -- CDG ----------------------------------------------------------------------------------------
def test_cdg_une_colonne(traj: Trajectoire, maquette: Maquette) -> None:
    nez = point_reference(maquette, "nez")
    c = cdg_corps(traj, maquette, DeclarationCdg(("Xcg",)))
    np.testing.assert_allclose(c[0], nez - [1.6, 0, 0])
    np.testing.assert_allclose(c[-1], nez - [1.4, 0, 0])
    mm = cdg_corps(traj, maquette, DeclarationCdg(("Xmm",), unite="mm"))
    np.testing.assert_allclose(mm, c)
    culot = cdg_corps(traj, maquette, DeclarationCdg(("Xcg",), reference="culot", axe="vers_nez"))
    np.testing.assert_allclose(culot[0], point_reference(maquette, "culot") + np.array([1.6, 0, 0]))


def test_cdg_trois_colonnes_axes_cao(traj: Trajectoire, maquette: Maquette) -> None:
    # CAO : axe_nez = −X, axe_haut = +Z → x_corps = −X_cao, z_corps (bas) = −Z_cao.
    c = cdg_corps(traj, maquette, DeclarationCdg(("Xcg", "Ycg", "Zcg"), reference="origine"))
    np.testing.assert_allclose(c[0], [-1.6, 0.0, -0.01], atol=1e-12)


def test_cdg_refus(traj: Trajectoire, maquette: Maquette) -> None:
    with pytest.raises(ErreurCdg, match="absente"):
        cdg_corps(traj, maquette, DeclarationCdg(("xcg",)))
    with pytest.raises(ErreurCdg, match="une colonne"):
        DeclarationCdg(("a", "b"))


def test_la_maquette_glisse_mais_le_cdg_suit_la_trajectoire(traj: Trajectoire, maquette: Maquette) -> None:
    decl = DeclarationCdg(("Xcg",))
    etat = EtatVol(traj, maquette, cdg=decl)
    for t in (0.0, 2.0, 30.0):
        cdg = etat.a(t).cdg_corps
        assert cdg is not None
        # Le point CDG de la maquette, placé, tombe sur la trajectoire, même agrandi.
        place = etat.placer(cdg[None, :], t, echelle=200.0)[0]
        np.testing.assert_allclose(place, traj.etat(np.array([t]))[0][0], atol=1e-9)
    # Le nez, lui, se rapproche du CDG quand le CDG avance (Xcg diminue).
    nez = point_reference(maquette, "nez")[None, :]
    d0 = np.linalg.norm(etat.placer(nez, 0.0) - traj.etat(np.array([0.0]))[0])
    d1 = np.linalg.norm(etat.placer(nez, float(traj.t[-1])) - traj.etat(traj.t[-1:])[0])
    assert d0 == pytest.approx(1.6) and d1 == pytest.approx(1.4)


# -- YAML ----------------------------------------------------------------------------------------
def test_sections_yaml(exemple: Path, tmp_path: Path) -> None:
    cfg = charger_configuration(exemple / "CONFIG_GUI.yaml")
    assert cfg.vent == DeclarationVent(("VN", "VE", "VZ"), vz="haut", sens="vers", unite="m/s")
    assert cfg.cdg == DeclarationCdg(("Xcg",), unite="m", reference="nez", axe="vers_culot")
    d = yaml.safe_load((exemple / "CONFIG_GUI.yaml").read_text(encoding="utf-8"))
    d["trajectoire"]["fichier"] = str(exemple / "vol_vent_cdg.csv")
    d["maquette"]["fichier"] = str(exemple / "MAQUETTE" / "Aim9.stl")
    for cle, valeur, motif in (("vent", {"colonnes": ["VN", "VE", "VZ"]}, "vz"),
                               ("vent", {"colonnes": ["VN", "VE", "VZ"], "vz": "haut", "rafale": 1}, "rafale"),
                               ("cdg", {"colonnes": ["Xcg"], "reference": "milieu"}, "reference")):
        f = tmp_path / "c.yaml"
        f.write_text(yaml.safe_dump({**d, cle: valeur}, allow_unicode=True), encoding="utf-8")
        with pytest.raises(ErreurConfiguration, match=motif):
            charger_configuration(f)


def test_vol_d_exemple_regenere(exemple: Path) -> None:
    df = pd.read_csv(exemple / "vol_vent_cdg.csv", comment="#")
    assert {"VN", "VE", "VZ", "Xcg", "masse", "poussee"} <= set(df.columns)
    ref = pd.read_csv(exemple / "vol_reference.csv", comment="#")
    np.testing.assert_allclose(df[["x", "y", "z"]].to_numpy(), ref[["x", "y", "z"]].to_numpy())
