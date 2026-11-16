"""Quaternions, matrices et angles d'Euler."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_trajcast.core import rotations as rot

RNG = np.random.default_rng(1)


def _q_aleatoires(n: int) -> np.ndarray:
    return rot.normaliser(RNG.normal(size=(n, 4)))


def _meme_rotation(p: np.ndarray, q: np.ndarray, tol: float = 1e-10) -> bool:
    return bool(np.all(rot.angle_entre(p, q) < tol))


def test_produit_compose_les_matrices() -> None:
    p, q = _q_aleatoires(50), _q_aleatoires(50)
    np.testing.assert_allclose(
        rot.vers_matrice(rot.produit(p, q)), rot.vers_matrice(p) @ rot.vers_matrice(q), atol=1e-12
    )


def test_matrice_aller_retour() -> None:
    q = _q_aleatoires(500)
    assert _meme_rotation(rot.depuis_matrice(rot.vers_matrice(q)), q)


def test_matrice_est_une_rotation() -> None:
    r = rot.vers_matrice(_q_aleatoires(100))
    np.testing.assert_allclose(r @ np.swapaxes(r, -1, -2), np.broadcast_to(np.eye(3), r.shape), atol=1e-12)
    np.testing.assert_allclose(np.linalg.det(r), 1.0, atol=1e-12)


def test_rotation_active() -> None:
    # 90° autour de z : x corps → y référence.
    q = rot.elementaire("z", np.pi / 2)
    np.testing.assert_allclose(rot.tourner(q, [1.0, 0.0, 0.0]), [0.0, 1.0, 0.0], atol=1e-15)


@pytest.mark.parametrize("sequence", [*rot.SEQUENCES, *(s.lower() for s in rot.SEQUENCES)])
def test_euler_aller_retour(sequence: str) -> None:
    q = _q_aleatoires(400)
    angles = rot.vers_euler(q, sequence)
    assert _meme_rotation(rot.depuis_euler(angles, sequence), q, 1e-9)


@pytest.mark.parametrize("sequence", [*rot.SEQUENCES, *(s.lower() for s in rot.SEQUENCES)])
def test_euler_angles_retrouves(sequence: str) -> None:
    propre = sequence[0].lower() == sequence[2].lower()
    a = RNG.uniform(-3.0, 3.0, size=(300, 3))
    a[:, 1] = RNG.uniform(0.1, 3.0, 300) if propre else RNG.uniform(-1.5, 1.5, 300)
    np.testing.assert_allclose(rot.vers_euler(rot.depuis_euler(a, sequence), sequence), a, atol=1e-9)


@pytest.mark.parametrize("sequence", ["ZYX", "zyx", "ZXZ", "xzx"])
def test_euler_blocage_cardan_reproduit_la_rotation(sequence: str) -> None:
    propre = sequence[0].lower() == sequence[2].lower()
    a = np.array([[0.3, 0.0 if propre else np.pi / 2, -0.7], [1.1, np.pi if propre else -np.pi / 2, 0.2]])
    q = rot.depuis_euler(a, sequence)
    assert _meme_rotation(rot.depuis_euler(rot.vers_euler(q, sequence), sequence), q, 1e-7)


def test_intrinseque_egale_extrinseque_inversee() -> None:
    a = RNG.uniform(-1, 1, size=(20, 3))
    assert _meme_rotation(rot.depuis_euler(a, "ZYX"), rot.depuis_euler(a[:, ::-1], "xyz"))


def test_zyx_aeronautique() -> None:
    # Tangage de 90° nez haut en NED/FRD : x corps → -z NED (le haut).
    q = rot.depuis_euler([0.0, np.pi / 2, 0.0], "ZYX")
    np.testing.assert_allclose(rot.tourner(q, [1.0, 0.0, 0.0]), [0.0, 0.0, -1.0], atol=1e-15)


@pytest.mark.parametrize("mauvaise", ["ZZX", "Zyx", "XY", "abc", "XYZX"])
def test_sequence_invalide(mauvaise: str) -> None:
    with pytest.raises(ValueError, match="séquence"):
        rot.valider_sequence(mauvaise)


def test_continuite_hemisphere() -> None:
    q = rot.normaliser(np.cumsum(RNG.normal(scale=0.05, size=(200, 4)), axis=0) + np.array([1.0, 0, 0, 0]))
    signes = RNG.choice([-1.0, 1.0], size=200)
    corrige, n = rot.continuite_hemisphere(q * signes[:, None])
    assert np.all(np.sum(corrige[1:] * corrige[:-1], axis=1) >= 0)
    assert n == int(np.count_nonzero(signes[1:] != signes[:-1]))
    assert _meme_rotation(corrige, q)


def test_slerp_extremites_et_vitesse_constante() -> None:
    p, q = _q_aleatoires(1)[0], _q_aleatoires(1)[0]
    u = np.linspace(0, 1, 11)
    s = rot.slerp(p, q, u)
    assert _meme_rotation(s[0], p) and _meme_rotation(s[-1], q)
    np.testing.assert_allclose(np.linalg.norm(s, axis=1), 1.0)
    pas = rot.angle_entre(s[1:], s[:-1])
    np.testing.assert_allclose(pas, pas[0], atol=1e-9)
    assert pas.sum() == pytest.approx(rot.angle_entre(p, q)[()], abs=1e-9)


def test_slerp_petit_arc() -> None:
    p = np.array([1.0, 0, 0, 0])
    q = -rot.elementaire("z", 0.2)  # même rotation que +0.2 rad, signe opposé
    milieu = rot.slerp(p, q, 0.5)
    assert rot.angle_entre(milieu, rot.elementaire("z", 0.1)) < 1e-12


def test_quaternion_nul_refuse() -> None:
    with pytest.raises(ValueError, match="nul"):
        rot.normaliser([0.0, 0.0, 0.0, 0.0])
