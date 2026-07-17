"""Tests de la génération du fichier d'étude à partir des points capturés."""

from __future__ import annotations

import pytest

from cfd_perf.capture.study_writer import (
    CapturedPoint,
    ObjectiveSpec,
    build_study_dict,
    write_study,
)
from cfd_perf.data.machine import Machine
from cfd_perf.data.study import StudyError, load_study
from cfd_perf.engine.recommend import Strategy

POINTS = [
    CapturedPoint(cores=8, time_per_iter_s=4.0, peak_ram_total_gb=10.0),
    CapturedPoint(cores=16, time_per_iter_s=2.2, peak_ram_total_gb=10.5),
    CapturedPoint(cores=32, time_per_iter_s=1.3, peak_ram_total_gb=11.0),
]

MACHINE = Machine(name="cluster-a", cores_per_node=8, ram_per_node_gb=64, max_nodes=16)


def _doc(**over):
    base = dict(title="AILE", n_iterations=5000, num_cells=2_000_000, machine=MACHINE, points=POINTS)
    base.update(over)
    return build_study_dict(**base)


class TestGeneratedStudy:
    def test_roundtrips_through_load_study(self, tmp_path):
        path = write_study(tmp_path / "ETUDE.yaml", _doc())
        study = load_study(path)
        assert study.name == "AILE"
        assert study.mesh.num_cells == 2_000_000
        assert study.pilot.n_iterations == 5000
        assert [p.cores for p in study.pilot.points] == [8, 16, 32]
        assert study.machine.cores_per_node == 8

    def test_memory_inferred_from_pilot(self, tmp_path):
        path = write_study(tmp_path / "ETUDE.yaml", _doc())
        study = load_study(path)
        assert study.mesh.mem_source == "measured (pilot)"

    def test_objective_written(self, tmp_path):
        doc = _doc(objective=ObjectiveSpec(strategy=Strategy.DEADLINE, deadline_hours=6.0))
        path = write_study(tmp_path / "ETUDE.yaml", doc)
        study = load_study(path)
        assert study.objective.strategy is Strategy.DEADLINE
        assert study.objective.deadline_hours == 6.0

    def test_header_comment_present(self, tmp_path):
        path = write_study(tmp_path / "ETUDE.yaml", _doc())
        assert "généré automatiquement" in path.read_text()


class TestDuplicateAveraging:
    def test_repeated_core_counts_are_averaged(self, tmp_path):
        points = [
            CapturedPoint(cores=8, time_per_iter_s=4.0, peak_ram_total_gb=10.0),
            CapturedPoint(cores=8, time_per_iter_s=6.0, peak_ram_total_gb=12.0),
            CapturedPoint(cores=16, time_per_iter_s=2.0, peak_ram_total_gb=None),
        ]
        path = write_study(tmp_path / "ETUDE.yaml", _doc(points=points))
        study = load_study(path)
        cores = [p.cores for p in study.pilot.points]
        assert cores == [8, 16]  # deduped
        pt8 = next(p for p in study.pilot.points if p.cores == 8)
        assert pt8.time_per_iter_s == pytest.approx(5.0)  # (4+6)/2
        assert pt8.peak_ram_total_gb == pytest.approx(11.0)  # (10+12)/2


class TestOptionalRam:
    def test_point_without_ram_omits_the_field(self, tmp_path):
        points = [
            CapturedPoint(cores=8, time_per_iter_s=4.0, peak_ram_total_gb=None),
            CapturedPoint(cores=16, time_per_iter_s=2.0, peak_ram_total_gb=None),
        ]
        doc = _doc(points=points)
        assert "peak_ram_total_gb" not in doc["pilot"][0]
        study = load_study(write_study(tmp_path / "ETUDE.yaml", doc))
        assert study.mesh.mem_source == "unknown"


class TestValidation:
    def test_invalid_num_cells_is_rejected_before_writing(self, tmp_path):
        target = tmp_path / "ETUDE.yaml"
        with pytest.raises((StudyError, ValueError)):
            write_study(target, _doc(num_cells=0))
        assert not target.exists()  # rien n'est écrit si invalide

    def test_machine_section_omits_unset_fields(self):
        doc = build_study_dict(
            title="X",
            n_iterations=100,
            num_cells=1000,
            machine=Machine(cores_per_node=4),
            points=POINTS,
        )
        assert "ram_per_node_gb" not in doc["machine"]
        assert "max_nodes" not in doc["machine"]
