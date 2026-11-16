"""ENU/NED, corps FRD/FLU, axes de la CAO."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_trajcast.core import reperes
from cfd_trajcast.core import rotations as rot


def test_ned_vers_enu() -> None:
    np.testing.assert_allclose(reperes.positions_vers_enu([[1.0, 2.0, 3.0]], "NED"), [[2.0, 1.0, -3.0]])


def test_quaternion_ned_vers_enu() -> None:
    # Nez au Nord, horizontal, ventre en bas : FRD = NED.
    q = reperes.quaternion_vers_enu([1.0, 0, 0, 0], "NED")
    np.testing.assert_allclose(rot.tourner(q, [1.0, 0, 0]), [0, 1, 0], atol=1e-15)  # nez → Nord
    np.testing.assert_allclose(rot.tourner(q, [0, 0, 1.0]), [0, 0, -1], atol=1e-15)  # ventre → bas


def test_flu_vers_frd() -> None:
    # Un corps FLU aligné sur ENU : nez à l'Est, gauche au Nord, haut en haut.
    q = reperes.quaternion_corps_vers_frd([1.0, 0, 0, 0], "FLU")
    np.testing.assert_allclose(rot.tourner(q, [1.0, 0, 0]), [1, 0, 0], atol=1e-15)
    np.testing.assert_allclose(rot.tourner(q, [0, 1.0, 0]), [0, -1, 0], atol=1e-15)  # droite = Sud
    np.testing.assert_allclose(rot.tourner(q, [0, 0, 1.0]), [0, 0, -1], atol=1e-15)  # bas


def test_cao_vers_corps() -> None:
    r = reperes.matrice_cao_vers_corps("-X", "+Z")
    np.testing.assert_allclose(r @ [-1.0, 0, 0], [1, 0, 0])
    np.testing.assert_allclose(r @ [0, 0, 1.0], [0, 0, -1])
    assert np.linalg.det(r) == pytest.approx(1.0)


@pytest.mark.parametrize("nez", ["+X", "-X", "+Y", "-Y", "+Z", "-Z"])
@pytest.mark.parametrize("haut", ["+X", "-X", "+Y", "-Y", "+Z", "-Z"])
def test_cao_toujours_directe(nez: str, haut: str) -> None:
    if nez[1] == haut[1]:
        with pytest.raises(ValueError, match="perpendiculaire"):
            reperes.matrice_cao_vers_corps(nez, haut)
    else:
        assert np.linalg.det(reperes.matrice_cao_vers_corps(nez, haut)) == pytest.approx(1.0)


@pytest.mark.parametrize("mauvais", ["X+", "+W", "", "++X"])
def test_axe_invalide(mauvais: str) -> None:
    with pytest.raises(ValueError, match="axe"):
        reperes.vecteur_axe(mauvais)


def test_repere_inconnu() -> None:
    with pytest.raises(ValueError, match="ENU, NED"):
        reperes.matrice_vers_enu("NWU")
