"""Case-file loading and validation.

Every rejection must name the offending key: the message is shown to the user
verbatim by the CLI.
"""

from __future__ import annotations

import math
import textwrap
from pathlib import Path

import pytest

from cfd_nozzle.core.nozzle import Regime
from cfd_nozzle.data.case import CaseError, load_case
from cfd_nozzle.paths import EXEMPLE_DIR

VALID = """
tuyere:
  nom: "TEST"
  gaz: lox_rp1
  diametre_col: 0.20
  rapport_section: 16.0
  eta_cstar: 0.96
  lambda_divergence: null
fonctionnement:
  p0: 100.0e+5
  t0: 3500.0
  pa: 1.013e+5
geometrie:
  type: bell
  pourcentage_longueur: 80.0
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "cas.yaml"
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


def test_loads_a_valid_case(tmp_path: Path) -> None:
    case = load_case(write(tmp_path, VALID))
    assert case.name == "TEST"
    assert case.gas.gamma == pytest.approx(1.22)
    assert case.throat_area == pytest.approx(0.25 * math.pi * 0.20**2)
    assert case.area_ratio == 16.0
    assert case.eta_cstar == 0.96
    assert case.lambda_div is None
    assert case.contour_kind == "bell"


def test_builds_a_working_nozzle(tmp_path: Path) -> None:
    case = load_case(write(tmp_path, VALID))
    contour = case.build_contour()
    nozzle = case.build_nozzle(contour)
    # λ was left null, so it must come from the contour.
    assert nozzle.lambda_div == pytest.approx(contour.divergence_lambda)
    state = nozzle.solve(case.p0, case.t0, case.pa)
    assert state.regime is Regime.OVEREXPANDED


def test_shipped_example_is_valid() -> None:
    case = load_case(EXEMPLE_DIR / "CAS_MOTEUR.yaml")
    nozzle = case.build_nozzle()
    assert nozzle.solve(case.p0, case.t0, case.pa).thrust > 0.0


def test_accepts_unsigned_exponents(tmp_path: Path) -> None:
    """YAML 1.1 reads 100.0e5 as a string; that must not be a user's problem."""
    case = load_case(write(tmp_path, VALID.replace("100.0e+5", "100.0e5")))
    assert case.p0 == pytest.approx(100e5)


def test_area_may_replace_the_diameter(tmp_path: Path) -> None:
    case = load_case(write(tmp_path, VALID.replace("diametre_col: 0.20", "aire_col: 0.0314159")))
    assert case.throat_area == pytest.approx(0.0314159)


def test_explicit_gas_overrides_the_library(tmp_path: Path) -> None:
    case = load_case(write(tmp_path, VALID.replace("gaz: lox_rp1", "gamma: 1.3\n  r: 400.0")))
    assert case.gas.gamma == 1.3
    assert case.gas.r == 400.0


def test_conical_geometry(tmp_path: Path) -> None:
    case = load_case(write(tmp_path, VALID.replace("type: bell", "type: conique\n  demi_angle: 18.0")))
    assert case.contour_kind == "conique"
    assert case.half_angle_deg == 18.0
    assert "conique" in case.build_contour().label


def test_geometry_section_is_optional(tmp_path: Path) -> None:
    case = load_case(write(tmp_path, VALID.split("geometrie:")[0]))
    assert case.contour_kind == "bell"
    assert case.pct_length == 80.0


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("REMOVE_TUYERE", "tuyere"),
        ("REMOVE_FONCTIONNEMENT", "fonctionnement"),
    ],
)
def test_missing_sections_are_named(tmp_path: Path, mutation: str, message: str) -> None:
    section = mutation.removeprefix("REMOVE_").lower()
    text = VALID.replace(f"{section}:", f"{section}_absente:")
    with pytest.raises(CaseError, match=message):
        load_case(write(tmp_path, text))


def test_missing_key_is_named(tmp_path: Path) -> None:
    with pytest.raises(CaseError, match=r"fonctionnement\.t0"):
        load_case(write(tmp_path, VALID.replace("t0: 3500.0", "")))


def test_rejects_unknown_gas(tmp_path: Path) -> None:
    with pytest.raises(CaseError, match="gaz inconnu"):
        load_case(write(tmp_path, VALID.replace("gaz: lox_rp1", "gaz: kerosene")))


def test_rejects_missing_gas_definition(tmp_path: Path) -> None:
    with pytest.raises(CaseError, match=r"tuyere\.gaz"):
        load_case(write(tmp_path, VALID.replace("gaz: lox_rp1", "")))


def test_rejects_both_area_and_diameter(tmp_path: Path) -> None:
    with pytest.raises(CaseError, match="pas les deux"):
        load_case(write(tmp_path, VALID.replace("diametre_col: 0.20", "diametre_col: 0.20\n  aire_col: 0.03")))


def test_rejects_neither_area_nor_diameter(tmp_path: Path) -> None:
    with pytest.raises(CaseError, match="aire_col"):
        load_case(write(tmp_path, VALID.replace("diametre_col: 0.20", "")))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("rapport_section: 0.5", "rapport_section"),
        ("eta_cstar: 1.5", "eta_cstar"),
        ("lambda_divergence: 2.0", "lambda_divergence"),
    ],
)
def test_rejects_out_of_range_values(tmp_path: Path, mutation: str, message: str) -> None:
    key = mutation.split(":")[0]
    text = "\n".join(
        # Keep the original indentation, or the key would leave its section.
        line[: len(line) - len(line.lstrip())] + mutation
        if line.strip().startswith(f"{key}:")
        else line
        for line in VALID.splitlines()
    )
    with pytest.raises(CaseError, match=message):
        load_case(write(tmp_path, text))


def test_rejects_negative_pressure(tmp_path: Path) -> None:
    with pytest.raises(CaseError, match=r"fonctionnement\.p0"):
        load_case(write(tmp_path, VALID.replace("p0: 100.0e+5", "p0: -1.0")))


def test_rejects_non_numeric_value(tmp_path: Path) -> None:
    with pytest.raises(CaseError, match=r"fonctionnement\.t0"):
        load_case(write(tmp_path, VALID.replace("t0: 3500.0", "t0: chaud")))


def test_rejects_bad_geometry_type(tmp_path: Path) -> None:
    with pytest.raises(CaseError, match=r"geometrie\.type"):
        load_case(write(tmp_path, VALID.replace("type: bell", "type: aerospike")))


def test_rejects_broken_yaml(tmp_path: Path) -> None:
    with pytest.raises(CaseError, match="YAML invalide"):
        load_case(write(tmp_path, "tuyere: [unclosed"))


def test_rejects_a_non_mapping_file(tmp_path: Path) -> None:
    with pytest.raises(CaseError, match="dictionnaire"):
        load_case(write(tmp_path, "- juste\n- une\n- liste\n"))


def test_rejects_a_scalar_section(tmp_path: Path) -> None:
    with pytest.raises(CaseError, match="bloc de clés"):
        load_case(write(tmp_path, "tuyere: 3\nfonctionnement:\n  p0: 1.0\n"))


def test_rejects_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CaseError, match="illisible"):
        load_case(tmp_path / "absent.yaml")


def test_impossible_geometry_is_reported_as_a_case_error(tmp_path: Path) -> None:
    text = VALID.replace("pourcentage_longueur: 80.0", "pourcentage_longueur: 1.0")
    case = load_case(write(tmp_path, text))
    with pytest.raises(CaseError, match="géométrie irréalisable"):
        case.build_contour()
