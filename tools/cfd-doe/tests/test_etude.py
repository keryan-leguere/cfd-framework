"""Lecture et validation du fichier d'étude."""

from __future__ import annotations

from pathlib import Path

import pytest

from cfd_doe.data.etude import ErreurEtude, charger_etude, etude_depuis_dict
from cfd_doe.data.trajectoires import TRAJECTOIRES
from cfd_doe.paths import EXEMPLE_DIR

BASE = {"trajectoire": "6DOF", "geometrie": "cruciforme", "variables": {"alpha": [-10, 10]}}


def test_exemple_livre_se_charge() -> None:
    etude = charger_etude(EXEMPLE_DIR / "ETUDE_FUSEE.yaml")
    assert etude.trajectoire.nom == "6DOF"
    assert etude.geometrie.n_rotation == 4
    assert set(etude.plages) == {"alpha", "beta", "DL", "DM", "DN"}


@pytest.mark.parametrize(
    ("donnees", "motif"),
    [
        ({**BASE, "limite_braquages": "disque"}, "clés admises"),
        ({**BASE, "variables": {"gamma": [0, 1]}}, "variables admises"),
        ({**BASE, "variables": {"alpha": [10, -10]}}, "borne basse"),
        ({**BASE, "variables": {"alpha": [-95, 10]}}, "< 90"),
        ({**BASE, "trajectoire": "7DOF"}, "types admis"),
        ({**BASE, "geometrie": "triangle"}, "admises"),
        ({**BASE, "geometrie": {"type": "n_ailettes"}}, "n_ailettes"),
        ({**BASE, "repere": "spherique"}, "admis"),
        ({k: v for k, v in BASE.items() if k != "trajectoire"}, "manquante"),
    ],
)
def test_refus_explicites(donnees: dict[str, object], motif: str) -> None:
    with pytest.raises(ErreurEtude, match=motif):
        etude_depuis_dict(donnees)


def test_casse_du_type_de_trajectoire_ignoree() -> None:
    assert (
        etude_depuis_dict({**BASE, "trajectoire": "3dof_tangage"}).trajectoire.nom == "3DOF_TANGAGE"
    )


def test_valeur_seule_est_un_point() -> None:
    etude = etude_depuis_dict({**BASE, "variables": {"alpha": 4}})
    assert etude.plages["alpha"].est_point


def test_trajectoire_personnalisee_deduit_ses_variables() -> None:
    etude = etude_depuis_dict(
        {
            **BASE,
            "trajectoire": "ROULIS_SEUL",
            "trajectoires": {"ROULIS_SEUL": {"efforts": ["A", "l"]}},
        }
    )
    assert etude.trajectoire.actives == ("DL",)


def test_table_freeman() -> None:
    attendu = {
        "1DOF": (),
        "2DOF": ("alpha",),
        "3DOF_MASSE_PONCTUELLE": ("alpha", "beta"),
        "3DOF_TANGAGE": ("alpha", "DM"),
        "4DOF": ("alpha", "DM", "DL"),
        "5DOF": ("alpha", "beta", "DM", "DN"),
        "6DOF": ("alpha", "beta", "DM", "DN", "DL"),
    }
    assert {k: set(t.actives) for k, t in TRAJECTOIRES.items()} == {
        k: set(v) for k, v in attendu.items()
    }


def test_yaml_invalide(tmp_path: Path) -> None:
    chemin = tmp_path / "e.yaml"
    chemin.write_text("trajectoire: [6DOF\n", encoding="utf-8")
    with pytest.raises(ErreurEtude, match="YAML invalide"):
        charger_etude(chemin)
