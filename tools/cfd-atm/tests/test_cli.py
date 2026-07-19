"""End-to-end CLI tests via ``main(argv)``."""

from __future__ import annotations

from pathlib import Path

import pytest

from cfd_atm.cli.main import main


class TestPoint:
    def test_basic_isa_point(self) -> None:
        assert main(["point", "--altitude", "35000", "--nature", "pression"]) == 0

    def test_offset_with_speed(self) -> None:
        rc = main(
            [
                "point", "--altitude", "35000", "--nature", "pression",
                "--modele", "ISA+X", "--dt", "10",
                "--vitesse", "280", "--grandeur", "cas", "--unite-vitesse", "kt",
            ]
        )
        assert rc == 0

    def test_geometric_metric_supersonic(self) -> None:
        rc = main(
            [
                "point", "--altitude", "12000", "--nature", "geometrique",
                "--unite-altitude", "m", "--vitesse", "1.6", "--grandeur", "mach",
            ]
        )
        assert rc == 0

    def test_custom_requires_profile(self) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["point", "--altitude", "10000", "--modele", "custom"])
        assert exc.value.code == 1


class TestExample:
    def test_copies_example(self, tmp_path: Path) -> None:
        dest = tmp_path / "exemple"
        assert main(["example", str(dest)]) == 0
        assert (dest / "tracer_iso_vitesses.py").is_file()
        assert (dest / "profil_T_custom.yaml").is_file()

    def test_refuses_nonempty(self, tmp_path: Path) -> None:
        dest = tmp_path / "exemple"
        dest.mkdir()
        (dest / "x.txt").write_text("hi")
        with pytest.raises(SystemExit) as exc:
            main(["example", str(dest)])
        assert exc.value.code == 1


class TestDiagramme:
    def test_generates_figures(self, tmp_path: Path) -> None:
        out = tmp_path / "SORTIE"
        assert main(["diagramme", "--sortie", str(out)]) == 0
        pngs = list(out.glob("*.png"))
        assert len(pngs) >= 3


class TestCustomProfileCli:
    def test_point_with_custom_profile(self, tmp_path: Path) -> None:
        profil = tmp_path / "p.yaml"
        profil.write_text(
            "nom: test\nprofil:\n"
            "  - {altitude_m: 0, temperature_K: 300}\n"
            "  - {altitude_m: 11000, temperature_K: 210}\n",
            encoding="utf-8",
        )
        rc = main(
            ["point", "--altitude", "10000", "--nature", "geopotentielle",
             "--unite-altitude", "m", "--modele", "custom", "--profil", str(profil)]
        )
        assert rc == 0
