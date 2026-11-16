"""Temps vidéo → temps de vol : vitesse constante et ralentis."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_trajcast.core.temps import Ralenti, instants_de_vol, vitesse_de_lecture


def test_sans_ralenti_inchange() -> None:
    t = instants_de_vol(1.0, 2.0, 10, 1.0)
    np.testing.assert_allclose(t, 1.0 + np.arange(10) / 10)


def test_ralenti_vitesse_et_duree() -> None:
    r = (Ralenti(2.0, 4.0, 0.25),)
    t = instants_de_vol(0.0, 6.0, 30, 1.0, r, transition=0.0)
    pas = np.diff(t) * 30                       # vitesse de lecture image par image
    assert np.all(pas > 0) and t[-1] == pytest.approx(6.0)
    np.testing.assert_allclose(pas[(t[:-1] > 2.05) & (t[:-1] < 3.95)], 0.25)
    np.testing.assert_allclose(pas[(t[:-1] < 1.95)], 1.0)
    # 4 s de vol en temps réel + 2 s à ×4 = 4 + 8 = 12 s de vidéo.
    assert len(t) / 30 == pytest.approx(12.0, abs=0.1)


def test_rampes() -> None:
    r = (Ralenti(2.0, 4.0, 0.2),)
    v = vitesse_de_lecture(np.array([1.0, 1.75, 2.0, 3.0, 4.25, 5.0]), 1.0, r, transition=0.5)
    np.testing.assert_allclose(v, [1.0, 0.6, 0.2, 0.2, 0.6, 1.0])


@pytest.mark.parametrize(("de", "a", "v"), [(2.0, 1.0, 0.5), (0.0, 1.0, 0.0)])
def test_ralenti_invalide(de: float, a: float, v: float) -> None:
    with pytest.raises(ValueError):
        Ralenti(de, a, v)
