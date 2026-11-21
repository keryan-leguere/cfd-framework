"""Repères locaux au CDG : orthonormés directs, et α/β sur des cas fermés."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_trajcast.core import reperes_locaux as rl
from cfd_trajcast.core import rotations as rot

NED_ZYX = "ZYX"


def _q(lacet: float, tangage: float, roulis: float) -> np.ndarray:
    """Attitude FRD → ENU depuis des angles d'Euler NED (degrés)."""
    from cfd_trajcast.core.reperes import quaternion_vers_enu

    q_ned = rot.depuis_euler(np.radians([[lacet, tangage, roulis]]), NED_ZYX)
    return np.asarray(quaternion_vers_enu(q_ned, "NED"))


def _direct(axes: np.ndarray) -> None:
    for a in axes:
        np.testing.assert_allclose(a.T @ a, np.eye(3), atol=1e-12)
        assert np.linalg.det(a) == pytest.approx(1.0)


def test_corps_et_ned_local() -> None:
    q = _q(30.0, 10.0, -20.0)
    _direct(rl.axes_corps(q))
    ned = rl.axes_ned_local(2)
    _direct(ned)
    np.testing.assert_allclose(ned[0][:, 0], [0, 1, 0])   # Nord = +y ENU
    np.testing.assert_allclose(ned[0][:, 2], [0, 0, -1])  # Bas = −z ENU
    # Nez au Nord, à plat : l'axe x du corps est le Nord, z le Bas.
    corps = rl.axes_corps(_q(0.0, 0.0, 0.0))[0]
    np.testing.assert_allclose(corps, ned[0], atol=1e-12)


def test_aero_sans_vent_dans_l_axe() -> None:
    q = _q(45.0, 20.0, 60.0)
    v = 300.0 * rl.axes_corps(q)[0][:, 0]  # vitesse air le long du nez
    alpha, beta, vv = rl.angles_aero(q, v)
    assert alpha[0] == pytest.approx(0.0, abs=1e-12) and beta[0] == pytest.approx(0.0, abs=1e-12)
    assert vv[0] == pytest.approx(300.0)
    np.testing.assert_allclose(rl.axes_aero(q, v)[0], rl.axes_corps(q)[0], atol=1e-12)


def test_incidence_et_derapage() -> None:
    q = _q(0.0, 0.0, 0.0)  # nez au Nord, à plat
    # Air venant d'en dessous du nez : composante w > 0 dans le corps → α > 0.
    corps = rl.axes_corps(q)[0]
    v = corps @ np.array([100.0, 0.0, 100.0 * np.tan(np.radians(8.0))])
    alpha, beta, _ = rl.angles_aero(q, v)
    assert np.degrees(alpha[0]) == pytest.approx(8.0) and beta[0] == pytest.approx(0.0, abs=1e-12)
    # Vent de travers pur venant de la gauche : l'air relatif va vers la droite → β > 0.
    v = corps @ np.array([100.0, 100.0 * np.tan(np.radians(5.0)), 0.0])
    alpha, beta, _ = rl.angles_aero(q, v)
    assert alpha[0] == pytest.approx(0.0, abs=1e-12)
    assert np.degrees(beta[0]) == pytest.approx(np.degrees(np.arctan(np.tan(np.radians(5.0)))), rel=1e-6)
    axes = rl.axes_aero(q, v)
    _direct(axes)
    np.testing.assert_allclose(axes[0][:, 0], v / np.linalg.norm(v), atol=1e-12)


def test_aero_indefini_a_vitesse_nulle() -> None:
    alpha, beta, _ = rl.angles_aero(_q(0, 0, 0), [0.0, 0.0, 0.1])
    assert np.isnan(alpha[0]) and np.isnan(beta[0])
    assert np.isnan(rl.axes_aero(_q(0, 0, 0), [0.0, 0.0, 0.1])).all()


def test_trajectoire() -> None:
    axes = rl.axes_trajectoire([[0.0, 100.0, 0.0], [100.0, 0.0, 50.0], [0.0, 0.0, 300.0]])
    _direct(axes)
    # Route au Nord : droite = Est, z vers le bas.
    np.testing.assert_allclose(axes[0][:, 1], [1, 0, 0], atol=1e-12)
    np.testing.assert_allclose(axes[0][:, 2], [0, 0, -1], atol=1e-12)
    # Route à l'Est, en montée : y à droite = Sud, horizontal.
    np.testing.assert_allclose(axes[1][:, 1], [0, -1, 0], atol=1e-12)
    # Vol vertical : y pris vers l'Est.
    np.testing.assert_allclose(axes[2][:, 1], [1, 0, 0], atol=1e-12)
    assert np.isnan(rl.axes_trajectoire([[0.0, 0.0, 0.1]])).all()
