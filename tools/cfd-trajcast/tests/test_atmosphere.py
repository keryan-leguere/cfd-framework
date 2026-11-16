"""Atmosphère standard : valeurs tabulées US 1976."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_trajcast.core.atmosphere import celerite_son, mach, temperature


@pytest.mark.parametrize(
    ("z", "t_attendue", "a_attendue"),
    [(0.0, 288.15, 340.294), (11_019.1, 216.65, 295.070), (20_000.0, 216.65, 295.070),
     (32_161.9, 228.65, 303.131), (47_350.1, 270.65, 329.799)],
)
def test_valeurs_tabulees(z: float, t_attendue: float, a_attendue: float) -> None:
    assert temperature(z)[()] == pytest.approx(t_attendue, abs=0.02)
    assert celerite_son(z)[()] == pytest.approx(a_attendue, abs=0.02)


def test_mach_vectorise() -> None:
    np.testing.assert_allclose(mach([340.294, 0.0], [0.0, 5000.0]), [1.0, 0.0], atol=1e-5)


@pytest.mark.parametrize(
    ("z", "p_attendue", "rho_attendue"),
    [(0.0, 101_325.0, 1.2250), (11_019.1, 22_632.1, 0.36392), (20_063.1, 5_474.89, 0.088035),
     (32_161.9, 868.019, 0.013225)],
)
def test_pression_et_masse_volumique(z: float, p_attendue: float, rho_attendue: float) -> None:
    from cfd_trajcast.core.atmosphere import masse_volumique, pression

    assert pression(z)[()] == pytest.approx(p_attendue, rel=2e-5)
    assert masse_volumique(z)[()] == pytest.approx(rho_attendue, rel=2e-4)
