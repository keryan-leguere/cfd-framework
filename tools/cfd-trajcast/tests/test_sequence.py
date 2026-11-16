"""Séquence de dispositions : bonne étape à chaque image, fondus."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from conftest import dataframe_enu_quaternion

from cfd_trajcast.core.camera import ParametresPoursuite, ParametresSol
from cfd_trajcast.core.disposition import Disposition
from cfd_trajcast.data.configuration import ConfigVideo, EtapeSequence
from cfd_trajcast.data.maquette import Maquette
from cfd_trajcast.data.trajectoire import Trajectoire
from cfd_trajcast.engine.scene import planifier

VUES = (("a", ParametresPoursuite()), ("b", ParametresSol(position=(500.0, 0.0, 2.0))))


@pytest.fixture
def traj() -> Trajectoire:
    return Trajectoire.depuis_dataframe(dataframe_enu_quaternion(), repere="ENU", attitude="quaternion")


@pytest.fixture
def maquette(exemple: Path) -> Maquette:
    return Maquette.depuis_fichier(exemple / "MAQUETTE" / "Aim9.stl", unite="mm", axe_nez="-X", axe_haut="+Z")


def test_etapes_et_fondu(traj: Trajectoire, maquette: Maquette) -> None:
    seq = (EtapeSequence(2.0, Disposition(type="unique", principale="b"), "fondu"),
           EtapeSequence(4.0, Disposition(type="unique", principale="a"), "coupe"))
    plan = planifier(traj, maquette, ConfigVideo(resolution=(64, 36), ips=10), VUES,
                     Disposition(type="unique", principale="a"), seq, fondu=0.5, de=0.0, a=6.0)
    assert set(plan.cameras) == {"a", "b"}
    np.testing.assert_array_equal(plan.etape, np.where(plan.t_vol < 2, 0, np.where(plan.t_vol < 4, 1, 2)))
    k = int(np.argmax(plan.etape == 1))
    # Fondu de 5 images : poids de l'agencement précédent décroissant, puis nul.
    np.testing.assert_allclose(plan.fondu[k:k + 6], [5 / 6, 4 / 6, 3 / 6, 2 / 6, 1 / 6, 0])
    assert np.all(plan.etape_prec[k:k + 5] == 0)
    k2 = int(np.argmax(plan.etape == 2))
    assert plan.fondu[k2] == 0  # coupe franche
    assert {c.nom for c in plan.vues_utiles(k)} == {"a", "b"}
