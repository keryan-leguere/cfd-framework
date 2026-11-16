"""PCHIP, SLERP en série, dérivées."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_trajcast.core import rotations as rot
from cfd_trajcast.core.interpolation import Pchip, deriver, slerp_serie

RNG = np.random.default_rng(2)


def test_pchip_passe_par_les_points() -> None:
    x = np.sort(RNG.uniform(0, 10, 30))
    y = RNG.normal(size=(30, 3))
    np.testing.assert_allclose(Pchip(x, y)(x), y, atol=1e-12)


def test_pchip_sans_depassement() -> None:
    x = np.arange(10.0)
    y = np.array([0, 0, 0, 1, 1, 1, 5, 5, 5, 5.0])
    yn = Pchip(x, y)(np.linspace(0, 9, 1000))
    assert yn.min() >= -1e-12 and yn.max() <= 5 + 1e-12
    assert np.all(np.diff(yn) >= -1e-12)  # monotone


def test_pchip_reproduit_une_droite_et_sa_derivee() -> None:
    x = np.sort(RNG.uniform(0, 5, 20))
    f = Pchip(x, 3 * x - 1)
    xn = np.linspace(x[0], x[-1], 50)
    np.testing.assert_allclose(f(xn), 3 * xn - 1, atol=1e-12)
    np.testing.assert_allclose(f(xn, derivee=1), 3.0, atol=1e-10)
    np.testing.assert_allclose(f(xn, derivee=2), 0.0, atol=1e-8)


def test_pchip_converge_sur_une_parabole() -> None:
    x = np.linspace(0, 10, 201)
    f = Pchip(x, -0.5 * 9.81 * x**2 + 100 * x)
    xn = np.linspace(0.5, 9.5, 77)
    np.testing.assert_allclose(f(xn), -0.5 * 9.81 * xn**2 + 100 * xn, rtol=1e-5)


def test_pas_d_extrapolation() -> None:
    f = Pchip([0.0, 1.0, 2.0], [0.0, 1.0, 4.0])
    with pytest.raises(ValueError, match="extrapolation"):
        f(2.5)


def test_abscisses_croissantes() -> None:
    with pytest.raises(ValueError, match="croissants"):
        Pchip([0.0, 1.0, 1.0], [0.0, 1.0, 2.0])


def test_slerp_serie() -> None:
    t = np.array([0.0, 1.0, 3.0])
    q = rot.elementaire("z", np.array([0.0, 1.0, 2.0]))
    q[1] *= -1  # signe arbitraire : même rotation
    qn = slerp_serie(t, q, [0.5, 2.0])
    assert rot.angle_entre(qn[0], rot.elementaire("z", 0.5)) < 1e-12
    assert rot.angle_entre(qn[1], rot.elementaire("z", 1.5)) < 1e-12


def test_deriver_ordre_2_pas_irregulier() -> None:
    x = np.sort(RNG.uniform(0, 1, 40))
    np.testing.assert_allclose(deriver(x, x**2), 2 * x, atol=1e-10)
