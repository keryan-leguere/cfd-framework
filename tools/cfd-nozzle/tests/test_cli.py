"""End-to-end CLI: every subcommand runs, reports, and fails cleanly.

A user-facing failure must be a short French panel and exit code 1 — never a
traceback.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from cfd_nozzle.cli.main import main
from cfd_nozzle.paths import EXEMPLE_DIR

CASE = EXEMPLE_DIR / "CAS_MOTEUR.yaml"


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = main(list(argv))
    return code, capsys.readouterr().out


def fails(capsys: pytest.CaptureFixture[str], *argv: str) -> str:
    with pytest.raises(SystemExit) as excinfo:
        main(list(argv))
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "Erreur" in captured.err
    return captured.err


# --- elementary relations -------------------------------------------------


def test_iso_from_mach(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "iso", "--mach", "2.0")
    assert code == 0
    assert "1.687500" in out  # A/A*
    assert "26.3798" in out  # ν


def test_iso_from_area_ratio_picks_the_branch(capsys: pytest.CaptureFixture[str]) -> None:
    _, subsonic = run(capsys, "iso", "--rapport-section", "4.0", "--branche", "sub")
    _, supersonic = run(capsys, "iso", "--rapport-section", "4.0", "--branche", "sup")
    assert "0.1465" in subsonic
    assert "2.9402" in supersonic


def test_iso_from_pressure_ratio(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "iso", "--p0-p", "7.824")
    assert code == 0
    assert "M = 2.0000" in out


def test_iso_needs_an_input(capsys: pytest.CaptureFixture[str]) -> None:
    assert "--mach" in fails(capsys, "iso")


def test_choc(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "choc", "--mach", "2.0")
    assert code == 0
    assert "4.500000" in out  # p2/p1
    assert "0.5774" in out  # M2


def test_choc_rejects_subsonic(capsys: pytest.CaptureFixture[str]) -> None:
    assert "M1" in fails(capsys, "choc", "--mach", "0.5")


def test_oblique(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "oblique", "--mach", "3.0", "--theta", "20")
    assert code == 0
    assert "37.76" in out
    assert "faible" in out


def test_oblique_strong_solution(capsys: pytest.CaptureFixture[str]) -> None:
    _, out = run(capsys, "oblique", "--mach", "3.0", "--theta", "20", "--forte")
    assert "forte" in out


def test_oblique_detached_is_explained(capsys: pytest.CaptureFixture[str]) -> None:
    assert "détaché" in fails(capsys, "oblique", "--mach", "2.0", "--theta", "40")


def test_detente_both_ways(capsys: pytest.CaptureFixture[str]) -> None:
    _, from_mach = run(capsys, "detente", "--mach", "2.0")
    assert "26.3798" in from_mach
    _, from_nu = run(capsys, "detente", "--nu", "26.3798")
    assert "M = 2.0000" in from_nu


def test_detente_needs_an_input(capsys: pytest.CaptureFixture[str]) -> None:
    assert "--mach" in fails(capsys, "detente")


def test_gas_selection_changes_the_numbers(capsys: pytest.CaptureFixture[str]) -> None:
    _, air = run(capsys, "iso", "--mach", "3.0", "--gaz", "air")
    _, helium = run(capsys, "iso", "--mach", "3.0", "--gaz", "he")
    assert "4.234568" in air
    assert "hélium" in helium
    assert "4.234568" not in helium


def test_explicit_gamma_overrides_the_library(capsys: pytest.CaptureFixture[str]) -> None:
    _, out = run(capsys, "iso", "--mach", "2.0", "--gaz", "air", "--gamma", "1.2")
    assert "γ = 1.2000" in out


# --- nozzle ---------------------------------------------------------------


def test_tuyere(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(
        capsys,
        "tuyere",
        "--p0", "100e5",
        "--t0", "3500",
        "--pa", "1.013e5",
        "--diametre-col", "0.2",
        "--eps", "16",
        "--gaz", "lox_rp1",
    )
    assert code == 0
    assert "sur-détendue" in out
    assert "NPR" in out
    assert "impulsion Isp" in out


def test_tuyere_needs_exactly_one_throat_size(capsys: pytest.CaptureFixture[str]) -> None:
    base = ["tuyere", "--p0", "100e5", "--t0", "3500", "--pa", "1e5", "--eps", "16"]
    assert "col" in fails(capsys, *base)
    assert "col" in fails(capsys, *base, "--diametre-col", "0.2", "--aire-col", "0.03")


def test_tuyere_reports_an_impossible_area_ratio(capsys: pytest.CaptureFixture[str]) -> None:
    assert "ε" in fails(
        capsys, "tuyere", "--p0", "1e6", "--t0", "300", "--pa", "1e5",
        "--diametre-col", "0.1", "--eps", "0.5",
    )


def test_run_and_check_the_shipped_case(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "check", str(CASE))
    assert code == 0
    assert "valide" in out
    code, out = run(capsys, "run", str(CASE))
    assert code == 0
    assert "MOTEUR_DEMO_LOX_RP1" in out
    assert "poussée F" in out


def test_run_rejects_a_broken_case(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("tuyere:\n  gaz: air\n", encoding="utf-8")
    message = fails(capsys, "run", str(bad))
    assert "fonctionnement" in message
    assert "cfd-nozzle example" in message  # the hint points at a valid schema


def test_check_rejects_a_missing_file(capsys: pytest.CaptureFixture[str]) -> None:
    assert "illisible" in fails(capsys, "check", "/nulle/part/cas.yaml")


# --- geometry and MOC -----------------------------------------------------


def test_geometrie_reports_and_exports(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    export = tmp_path / "contour.dat"
    code, out = run(
        capsys, "geometrie", "--rayon-col", "0.05", "--eps", "16", "--export", str(export)
    )
    assert code == 0
    assert "galbée Rao" in out
    assert export.exists()
    assert len(export.read_text().splitlines()) > 100


def test_geometrie_conical(capsys: pytest.CaptureFixture[str]) -> None:
    _, out = run(capsys, "geometrie", "--rayon-col", "0.05", "--eps", "16", "--type", "conique")
    assert "conique" in out


def test_geometrie_reports_impossible_input(capsys: pytest.CaptureFixture[str]) -> None:
    assert "ε" in fails(capsys, "geometrie", "--rayon-col", "0.05", "--eps", "0.2")


def test_moc_planar_and_axisymmetric(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    export = tmp_path / "moc.dat"
    code, planar = run(
        capsys, "moc", "--mach-sortie", "2.4", "--n", "15", "--export", str(export)
    )
    assert code == 0
    assert "plane" in planar
    assert export.exists()
    _, axi = run(capsys, "moc", "--mach-sortie", "2.4", "--n", "15", "--axisymetrique")
    assert "axisymétrique" in axi


def test_moc_reports_out_of_envelope(capsys: pytest.CaptureFixture[str]) -> None:
    assert "domaine validé" in fails(
        capsys, "moc", "--mach-sortie", "5.0", "--n", "20", "--axisymetrique"
    )


def test_moc_rejects_subsonic_target(capsys: pytest.CaptureFixture[str]) -> None:
    assert "M_sortie" in fails(capsys, "moc", "--mach-sortie", "0.8")


# --- example --------------------------------------------------------------


def test_example_copies_a_runnable_directory(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    destination = tmp_path / "exemple"
    code, out = run(capsys, "example", str(destination))
    assert code == 0
    assert "Exemple copié" in out
    assert (destination / "CAS_MOTEUR.yaml").exists()
    assert (destination / "RUN_EXEMPLE.sh").exists()
    # ...and the copy is itself a valid case.
    assert main(["check", str(destination / "CAS_MOTEUR.yaml")]) == 0


def test_example_refuses_to_overwrite(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    destination = tmp_path / "occupe"
    destination.mkdir()
    (destination / "fichier.txt").write_text("déjà là", encoding="utf-8")
    assert "existe déjà" in fails(capsys, "example", str(destination))


# --- figures --------------------------------------------------------------


def test_figures_are_written(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code, _ = run(capsys, "run", str(CASE), "--figure", str(tmp_path))
    assert code == 0
    assert (tmp_path / "champ_tuyere.png").exists()
    assert (tmp_path / "carte_performance.png").exists()


def test_moc_figure_is_written(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    run(capsys, "moc", "--mach-sortie", "2.0", "--n", "10", "--figure", str(tmp_path))
    assert (tmp_path / "moc.png").exists()


def test_geometry_figure_is_written(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    run(capsys, "geometrie", "--rayon-col", "0.05", "--eps", "16", "--figure", str(tmp_path))
    assert (tmp_path / "contour.png").exists()


def test_tuyere_figures_are_written(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    run(
        capsys, "tuyere", "--p0", "100e5", "--t0", "3500", "--pa", "1.013e5",
        "--diametre-col", "0.2", "--eps", "16", "--figure", str(tmp_path),
    )
    assert (tmp_path / "champ_tuyere.png").exists()


# --- plumbing -------------------------------------------------------------


def test_version() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0


def test_a_subcommand_is_required() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code == 2


def test_shock_in_divergent_is_reported(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    case = tmp_path / "choc.yaml"
    case.write_text(
        textwrap.dedent("""
            tuyere:
              nom: "CHOC_INTERNE"
              gaz: air
              diametre_col: 0.05
              rapport_section: 4.0
            fonctionnement:
              p0: 10.0e+5
              t0: 300.0
              pa: 6.0e+5
        """),
        encoding="utf-8",
    )
    code, out = run(capsys, "run", str(case))
    assert code == 0
    assert "Choc droit interne" in out
