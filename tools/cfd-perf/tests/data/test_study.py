"""Tests for study-file loading and validation."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from cfd_perf.data.study import StudyError, load_study, parse_study
from cfd_perf.engine.recommend import Strategy

EXAMPLE = Path(__file__).resolve().parents[2] / "01_EXEMPLE" / "ONERA_M6_CRUISE.yaml"

MINIMAL = {
    "study": {"name": "t", "n_iterations": 1000},
    "mesh": {"num_cells": 1_000_000},
    "pilot": [
        {"cores": 48, "time_per_iter_s": 3.9},
        {"cores": 96, "time_per_iter_s": 2.2},
        {"cores": 192, "time_per_iter_s": 1.4},
    ],
}


class TestShippedExample:
    def test_example_file_exists(self):
        assert EXAMPLE.is_file(), "the shipped example must be present"

    def test_example_loads_and_is_complete(self):
        study = load_study(EXAMPLE)
        assert study.mesh.num_cells == 20_000_000
        assert len(study.pilot.points) == 7
        assert study.machine.cores_per_node == 48
        assert study.objective.strategy is Strategy.EFFICIENCY

    def test_example_infers_memory_from_the_pilot(self):
        study = load_study(EXAMPLE)
        assert study.mesh.mem_source == "measured (pilot)"
        assert study.mesh.total_ram_gb == pytest.approx(148.0, rel=1e-6)


class TestMinimalStudy:
    def test_optional_sections_may_be_omitted(self):
        study = parse_study(MINIMAL)
        assert study.machine.cores_per_node == 1
        assert study.objective.strategy is Strategy.EFFICIENCY

    def test_memory_unknown_without_ram_or_override(self):
        study = parse_study(MINIMAL)
        assert study.mesh.total_ram_gb is None
        assert study.mesh.mem_source == "unknown"

    def test_explicit_mem_per_cell_wins_over_pilot(self):
        data = {**MINIMAL, "mesh": {"num_cells": 1_000_000, "mem_per_cell_bytes": 8000}}
        study = parse_study(data)
        assert study.mesh.mem_source == "user"
        assert study.mesh.mem_per_cell_bytes == 8000


class TestErrors:
    def test_missing_pilot_section(self):
        data = {k: v for k, v in MINIMAL.items() if k != "pilot"}
        with pytest.raises(StudyError, match="« pilot » est requise"):
            parse_study(data)

    def test_missing_n_iterations(self):
        data = {**MINIMAL, "study": {"name": "t"}}
        with pytest.raises(StudyError, match="clé requise « n_iterations »"):
            parse_study(data)

    def test_missing_num_cells(self):
        data = {**MINIMAL, "mesh": {}}
        with pytest.raises(StudyError, match="clé requise « num_cells »"):
            parse_study(data)

    def test_unknown_top_level_section_is_caught(self):
        data = {**MINIMAL, "objectives": {}}
        with pytest.raises(StudyError, match="niveau supérieur inconnue"):
            parse_study(data)

    def test_unknown_strategy_lists_the_valid_ones(self):
        data = {**MINIMAL, "objective": {"strategy": "cheapest"}}
        with pytest.raises(StudyError, match="efficiency, deadline, fastest"):
            parse_study(data)

    def test_deadline_strategy_without_deadline_hours(self):
        data = {**MINIMAL, "objective": {"strategy": "deadline"}}
        with pytest.raises(StudyError, match="deadline_hours n'est pas défini"):
            parse_study(data)

    def test_section_must_be_a_mapping(self):
        data = {**MINIMAL, "machine": ["cluster-a"]}
        with pytest.raises(StudyError, match="doit être une table"):
            parse_study(data)

    def test_pilot_must_be_a_list(self):
        data = {**MINIMAL, "pilot": {"cores": 48}}
        with pytest.raises(StudyError, match="doit être une liste"):
            parse_study(data)

    def test_bad_pilot_values_surface_as_study_errors(self):
        data = {**MINIMAL, "pilot": [{"cores": 48, "time_per_iter_s": -1.0}]}
        with pytest.raises(StudyError, match="time_per_iter_s"):
            parse_study(data)

    def test_missing_file_names_the_path(self, tmp_path):
        target = tmp_path / "nope.yaml"
        with pytest.raises(StudyError, match="fichier introuvable"):
            load_study(target)

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.yaml"
        f.write_text("")
        with pytest.raises(StudyError, match="fichier vide"):
            load_study(f)

    def test_invalid_yaml_reports_the_path(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text("study: {\n  unbalanced")
        with pytest.raises(StudyError, match="YAML invalide"):
            load_study(f)

    def test_error_message_includes_the_file_path(self, tmp_path):
        f = tmp_path / "s.yaml"
        f.write_text(
            textwrap.dedent(
                """
                study: {name: t, n_iterations: 100}
                mesh: {}
                pilot:
                  - {cores: 48, time_per_iter_s: 1.0}
                """
            )
        )
        with pytest.raises(StudyError, match=str(f)):
            load_study(f)
