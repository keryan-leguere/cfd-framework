"""Le vol de référence est cohérent avec lui-même."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_trajcast.core import rotations as rot
from cfd_trajcast.core.vol_reference import VolReference


def test_vitesse_derivee_de_la_position(vol: VolReference) -> None:
    t = np.linspace(0.1, vol.t_apogee + 5, 300)
    h = 1e-5
    np.testing.assert_allclose(
        (vol.position(t + h) - vol.position(t - h)) / (2 * h), vol.vitesse(t), atol=1e-4
    )


def test_continuite_fin_de_propulsion(vol: VolReference) -> None:
    tp, e = vol.duree_propulsion, 1e-9
    np.testing.assert_allclose(vol.position(tp - e), vol.position(tp + e), atol=1e-6)
    np.testing.assert_allclose(vol.vitesse(tp - e), vol.vitesse(tp + e), atol=1e-6)


def test_nez_dans_la_vitesse(vol: VolReference) -> None:
    t = np.linspace(0.05, vol.t_apogee + 10, 500)
    v = vol.vitesse(t)
    nez = rot.tourner(vol.quaternion(t), [1.0, 0.0, 0.0])
    np.testing.assert_allclose(nez, v / np.linalg.norm(v, axis=1, keepdims=True), atol=1e-12)


def test_roulis(vol: VolReference) -> None:
    roulis = vol.euler_ned(np.array([0.0, 1.0]))[:, 2]
    assert np.degrees(roulis[1] - roulis[0]) == pytest.approx(vol.vitesse_roulis)


def test_apogee_et_mach(vol: VolReference) -> None:
    assert vol.vitesse(vol.t_apogee)[0, 2] == pytest.approx(0.0, abs=1e-9)
    assert vol.mach(vol.t_mach_1)[0] == pytest.approx(1.0, abs=1e-4)
    assert 0 < vol.t_mach_1 < vol.t_apogee
