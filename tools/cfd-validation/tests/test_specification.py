from __future__ import annotations

import pytest

from cfd_validation.core.tolerance import ORIGINE_DECLAREE, ORIGINE_DEFAUT, Tolerance
from cfd_validation.data.specification import (
    ErreurSpecification,
    construire_specification,
    specification_depuis_dict,
)


def test_chaines_et_listes() -> None:
    s = construire_specification("Mach, alpha", ["CN"])
    assert s.entrees == ("Mach", "alpha")
    assert s.sorties == ("CN",)


def test_tolerance_par_defaut_signalee() -> None:
    s = construire_specification(["a"], ["x", "y"])
    assert all(t.origine == ORIGINE_DEFAUT for t in s.tolerances.values())


def test_tolerances_propres_heritent_de_la_commune() -> None:
    s = construire_specification(
        ["a"], ["x", "y", "z"],
        tolerances={"x": {"rtol": 1e-6}, "y": (1e-3, 0.0), "z": Tolerance(0.0, 1.0, "j")},
        rtol=1e-9, atol=1e-12, justification="commune",
    )
    assert s.tolerance("x") == Tolerance(1e-6, 1e-12, "commune", ORIGINE_DECLAREE)
    assert s.tolerance("y").rtol == 1e-3 and s.tolerance("y").atol == 0.0
    assert s.tolerance("z").justification == "j"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"entrees": ["a"], "sorties": ["a"]}, "à la fois entrée et sortie"),
        ({"entrees": [], "sorties": ["x"]}, "aucune colonne d'entrée"),
        ({"entrees": ["a", "a"], "sorties": ["x"]}, "deux fois"),
        ({"entrees": ["a"], "sorties": ["x"], "tolerances": {"y": (1, 1)}}, "pas une sortie"),
        ({"entrees": ["a"], "sorties": ["x"], "tolerances": {"x": {"rtl": 1}}}, "inconnue"),
        ({"entrees": ["a"], "sorties": ["x"], "tolerances": {"x": {"rtol": -1}}}, "positif"),
        ({"entrees": ["a"], "sorties": ["x"], "alignement": "index"}, "alignement inconnu"),
        ({"entrees": ["a"], "sorties": ["x"], "chiffres_cle": 0}, "chiffres_cle"),
    ],
)
def test_refus(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ErreurSpecification, match=message):
        construire_specification(**kwargs)  # type: ignore[arg-type]


def test_depuis_yaml_lit_les_nombres_ecrits_en_texte() -> None:
    spec, desc = specification_depuis_dict(
        {
            "identifiant": "INT-07",
            "entrees": ["a"],
            "sorties": ["x", "y"],
            "tolerances": {"defaut": {"rtol": "1e-9"}, "sorties": {"y": {"atol": "1e-3", "justification": "J"}}},
            "metadonnees": {"commit": 123},
        }
    )
    assert spec.tolerance("x").rtol == 1e-9
    assert spec.tolerance("y").atol == 1e-3
    assert desc["identifiant"] == "INT-07"
    assert desc["metadonnees"] == {"commit": "123"}


@pytest.mark.parametrize(
    ("contenu", "message"),
    [
        ({"entrees": ["a"]}, "sorties"),
        ({"entrees": ["a"], "sorties": ["x"], "sortie": ["y"]}, "inconnue"),
        ({"entrees": ["a"], "sorties": ["x"], "tolerances": {"default": {}}}, "inconnue"),
        ({"entrees": ["a"], "sorties": ["x"], "tolerances": {"defaut": {"tol": 1}}}, "inconnue"),
    ],
)
def test_depuis_yaml_refus(contenu: dict[str, object], message: str) -> None:
    with pytest.raises(ErreurSpecification, match=message):
        specification_depuis_dict(contenu)
