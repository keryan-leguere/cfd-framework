"""Géométrie des jets : flamme évasée, cœur, disques de Mach ; fumée par phase d'émission."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_trajcast.data.configuration import JETS, Flamme, Fumee, Jet
from cfd_trajcast.engine.jets import Phase, coques_flamme, fumee, phase_active, scintillement


def test_flamme_s_evase_puis_se_referme() -> None:
    f = Flamme(longueur=10, evasement=15, coeur=0.4, diamants=3)
    coques = coques_flamme(f, r0=0.5)
    enveloppe = coques[0]
    x, r = -enveloppe.points[:, 0], np.hypot(enveloppe.points[:, 1], enveloppe.points[:, 2])
    assert x.min() == pytest.approx(0) and x.max() == pytest.approx(5.0)
    milieu = (x > 1.5) & (x < 2.0)
    assert r[milieu].max() > 0.5 + 1.5 * np.tan(np.radians(15)) * 0.9   # plus large que la tuyère
    assert r[x > 4.99].max() < 1e-6                                        # refermée au bout
    alpha = enveloppe.rgba[:, 3].astype(float)
    assert alpha[x < 0.1].mean() > alpha[x > 4.0].mean()                  # s'efface vers le bout
    assert len(coques) == 1 + 1 + 3                                        # enveloppe, cœur, disques


def test_scintillement_et_phases() -> None:
    assert scintillement(1.0, 0.0) == 1.0
    k = np.array([scintillement(t, 0.1) for t in np.linspace(0, 5, 500)])
    assert 0.85 < k.min() < 1 < k.max() < 1.15
    phases = [Phase(0, 10, JETS["fusee_poudre"]), Phase(10, 20, JETS["fusee_liquide"])]
    assert phase_active(5.0, phases, 0.4) == [(0, 1.0)]
    actives = dict(phase_active(10.0, phases, 0.4))                       # fondu croisé
    assert set(actives) == {0, 1} and actives[0] == pytest.approx(0.5)
    assert phase_active(30.0, phases, 0.4) == []


def _vol(n: int = 600) -> tuple[np.ndarray, ...]:
    t = np.linspace(0, 10, n)
    pos = np.stack([np.zeros(n), np.zeros(n), 100.0 * t], axis=1)          # monte à 100 m/s
    att = np.tile([np.cos(np.pi / 4), 0, -np.sin(np.pi / 4), 0], (n, 1))     # nez vers le haut
    return t, pos, att


def test_fumee_s_ouvre_et_apparait_derriere_la_flamme() -> None:
    t, pos, att = _vol()
    f = Fumee(rayon=1.0, evasement=10, expansion=0.0, turbulence=0.0, duree=5.0, opacite=1.0)
    phases = [Phase(0, 10, Jet(Flamme(longueur=10), f))]
    k = 400
    pts, rayons, rgba = fumee(t[k], t, pos, att, np.zeros(3), 0.2, phases, 0.0, pos[k], att[k])
    d = np.linalg.norm(pts - pts[-1], axis=1)
    assert rgba[-1, 3] == 0                                              # rien à la tuyère
    loin = d > 50
    assert rgba[loin, 3].max() > 100                                     # visible plus loin
    np.testing.assert_allclose(rayons[loin], 0.2 + d[loin] * np.tan(np.radians(10)), rtol=0.05)
    assert d.max() == pytest.approx(500, rel=0.02)                       # 5 s de fumée à 100 m/s


def test_fumee_garde_la_phase_d_emission() -> None:
    t, pos, att = _vol()
    noire = Fumee(couleur_debut="#000000", couleur_fin="#000000", duree=8.0, turbulence=0.0)
    blanche = Fumee(couleur_debut="#ffffff", couleur_fin="#ffffff", duree=8.0, turbulence=0.0)
    phases = [Phase(0, 4, Jet(None, noire)), Phase(4, 10, Jet(None, blanche))]
    k = 500                                                              # t ≈ 8,3 s
    pts, _, rgba = fumee(t[k], t, pos, att, np.zeros(3), 0.2, phases, 0.0, pos[k], att[k])
    z = pts[:, 2] + pos[k, 2]                                            # altitude d'émission
    visibles = rgba[:, 3] > 0
    assert np.all(rgba[visibles & (z < 380), :3] < 30)                   # émise avant 4 s : noire
    assert np.all(rgba[visibles & (z > 420), :3] > 225)                  # après : blanche


def test_sans_fumee() -> None:
    t, pos, att = _vol()
    assert fumee(5.0, t, pos, att, np.zeros(3), 0.2, [Phase(0, 10, JETS["postcombustion"])], 0.3,
                 pos[300], att[300]) is None
