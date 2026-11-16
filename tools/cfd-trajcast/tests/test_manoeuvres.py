"""Simulateur de manœuvres : cohérence physique minimale de chaque manœuvre."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_trajcast.core import rotations as rot
from cfd_trajcast.core.atmosphere import G0
from cfd_trajcast.core.manoeuvres import Conditions, Mobile, Segment, simuler


def _palier(**kw) -> Conditions:  # type: ignore[no-untyped-def]
    return Conditions(position=(0.0, 0.0, 2000.0), vitesse=200.0, **kw)


def test_palier_rectiligne() -> None:
    s = simuler(_palier(), [Segment(20, "Palier", vitesse=200, pente=0, inclinaison=0)])
    assert abs(s.positions[-1, 2] - 2000) < 1.0 and abs(s.positions[-1, 1] - 4000) < 5
    np.testing.assert_allclose(s.donnees["n"], 1.0, atol=1e-3)
    assert s.evenements == ((0.0, "Palier"),) and s.t[0] == 0.0


def test_virage_coordonne() -> None:
    """Inclinaison 60° en palier : n = 1/cos 60° = 2, taux de virage g·tan μ / V."""
    s = simuler(_palier(), [Segment(40, inclinaison=60, pente=0, vitesse=200)])
    fin = s.t > 20
    assert np.allclose(s.donnees["n"][fin], 2.0, atol=0.05)
    cap = np.unwrap(np.radians(s.donnees["cap"][fin]))
    taux = np.polyfit(s.t[fin], cap, 1)[0]
    assert taux == pytest.approx(G0 * np.tan(np.radians(60)) / 200, rel=0.03)
    assert abs(s.positions[fin, 2] - 2000).max() < 30          # tient l'altitude
    # Le roulis d'Euler de l'attitude est l'inclinaison (à l'incidence près).
    q_ned = rot.produit(rot.depuis_matrice(np.array([[0, 1, 0], [1, 0, 0], [0, 0, -1.0]])), s.attitudes[fin])
    assert np.degrees(rot.vers_euler(q_ned, "ZYX")[:, 2]).mean() == pytest.approx(60, abs=2)


def test_boucle_fermee() -> None:
    s = simuler(_palier(), [Segment(34, facteur_charge=4.5, vitesse=230, taux_roulis=0),
                            Segment(6, pente=0, inclinaison=0)])
    assert s.donnees["pente"].max() > 80 and s.donnees["pente"].min() < -60
    assert abs(s.donnees["pente"][-1]) < 3 and s.positions[:, 2].max() > 2500
    assert abs(s.positions[-1, 0]) < 50                         # reste dans son plan


def test_fusee_balistique() -> None:
    s = simuler(Conditions(vitesse=1, pente=80, facteur_charge=0),
                [Segment(3, poussee=100, facteur_charge=0), Segment(30, poussee=0)], Mobile.fusee())
    np.testing.assert_allclose(s.donnees["n"], 0.0, atol=1e-9)
    nez = rot.tourner(s.attitudes, np.array([1.0, 0, 0]))
    v = s.vitesses / np.linalg.norm(s.vitesses, axis=1, keepdims=True)
    assert np.max(np.degrees(np.arccos(np.clip(np.sum(nez * v, axis=1), -1, 1)))) < 1e-4  # incidence nulle


def test_sol_et_arret() -> None:
    s = simuler(Conditions(vitesse=1), [Segment(10, vitesse=60, au_sol=True)])
    assert np.all(s.positions[:, 2] == 0) and s.donnees["V"][-1] == pytest.approx(60, rel=0.1)
    chute = simuler(_palier(), [Segment(200, facteur_charge=0.0)], arret_sous=500)
    assert chute.positions[-1, 2] < 500 and chute.t[-1] < 200


@pytest.mark.parametrize("champs", [{"vitesse": 1, "poussee": 1}, {"pente": 0, "facteur_charge": 1},
                                    {"cap": 0, "inclinaison": 0}, {}])
def test_segment_invalide(champs: dict) -> None:  # type: ignore[type-arg]
    with pytest.raises(ValueError):
        Segment(0 if not champs else 1, **champs)
