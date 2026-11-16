"""Lecture de la CAO : axes, unités, origine, mise à l'échelle."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cfd_trajcast.data.maquette import ErreurMaquette, Maquette, unite_step

L_MODELE = 0.0381011  # m, l'Aim9 en mm


@pytest.fixture
def stl(exemple: Path) -> Path:
    return exemple / "MAQUETTE" / "Aim9.stl"


@pytest.fixture
def stp(exemple: Path) -> Path:
    return exemple / "MAQUETTE" / "Aim9.stp"


def test_stl_axes_et_base(stl: Path) -> None:
    m = Maquette.depuis_fichier(stl, unite="mm", axe_nez="-X", axe_haut="+Z")
    assert m.longueur == pytest.approx(L_MODELE, rel=1e-5)
    assert m.sommets[:, 0].min() == pytest.approx(0.0, abs=1e-12)  # culot à l'origine
    # Le dôme (petit rayon) est vers +x corps, l'empennage (grand) vers le culot.
    r = np.hypot(m.sommets[:, 1], m.sommets[:, 2])
    x = m.sommets[:, 0] / m.longueur
    assert r[x > 0.95].max() < 0.3 * r[x < 0.1].max()


def test_stl_sans_unite_refuse(stl: Path) -> None:
    with pytest.raises(ErreurMaquette, match="n'a pas d'unité"):
        Maquette.depuis_fichier(stl, axe_nez="-X", axe_haut="+Z")


def test_longueur_attendue_nomme_la_confusion(stl: Path) -> None:
    with pytest.raises(ErreurMaquette, match="mm pris pour des m"):
        Maquette.depuis_fichier(stl, unite="m", axe_nez="-X", axe_haut="+Z", longueur_attendue=0.0381)
    m = Maquette.depuis_fichier(stl, unite="mm", axe_nez="-X", axe_haut="+Z", longueur_attendue=0.038)
    assert m.longueur == pytest.approx(L_MODELE, rel=1e-5)


def test_longueur_imposee_et_origine_point(stl: Path) -> None:
    m = Maquette.depuis_fichier(stl, unite="mm", axe_nez="-X", axe_haut="+Z",
                                origine=(19.05, 0, 0), longueur_imposee=2.87)
    assert m.longueur == pytest.approx(2.87)
    assert m.sommets[:, 0].min() == pytest.approx(-1.435, abs=2e-3)  # milieu → origine
    assert m.echelle == pytest.approx(2.87 / 38.1011, rel=1e-5)


def test_axe_nez_mal_choisi_signale(stl: Path) -> None:
    m = Maquette.depuis_fichier(stl, unite="mm", axe_nez="+Y", axe_haut="+Z")
    assert any(c.code == "axe_nez_court" for c in m.constats)


def test_format_inconnu(tmp_path: Path) -> None:
    f = tmp_path / "fusee.dwg"
    f.write_bytes(b"x")
    with pytest.raises(ErreurMaquette, match="non pris en charge"):
        Maquette.depuis_fichier(f, unite="mm", axe_nez="+X", axe_haut="+Z")


def test_declaration_controlee(stl: Path) -> None:
    with pytest.raises(ErreurMaquette, match="perpendiculaire"):
        Maquette.depuis_fichier(stl, unite="mm", axe_nez="+X", axe_haut="-X")
    with pytest.raises(ErreurMaquette, match="s'excluent"):
        Maquette.depuis_fichier(stl, unite="mm", axe_nez="-X", axe_haut="+Z",
                                longueur_attendue=1.0, longueur_imposee=2.0)


def test_unite_step() -> None:
    assert unite_step("#1 = ( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) );") == "mm"
    assert unite_step("#1 = ( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT($,.METRE.) );") == "m"
    assert unite_step("CONVERSION_BASED_UNIT('INCH',#5)") == "in"
    assert unite_step("rien") is None


def test_step_egal_au_stl(stl: Path, stp: Path) -> None:
    pytest.importorskip("cascadio")
    a = Maquette.depuis_fichier(stl, unite="mm", axe_nez="-X", axe_haut="+Z")
    b = Maquette.depuis_fichier(stp, axe_nez="-X", axe_haut="+Z")
    np.testing.assert_allclose(b.sommets.min(axis=0), a.sommets.min(axis=0), atol=1e-6)
    np.testing.assert_allclose(b.sommets.max(axis=0), a.sommets.max(axis=0), atol=1e-6)
    assert any(c.code == "unite_step" and "mm" in c.message for c in b.constats)


def test_step_unite_contradictoire(stp: Path) -> None:
    pytest.importorskip("cascadio")
    with pytest.raises(ErreurMaquette, match="déclare des mm"):
        Maquette.depuis_fichier(stp, unite="m", axe_nez="-X", axe_haut="+Z")
