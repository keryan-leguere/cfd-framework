"""Smoke tests for scaling plot generation."""

import matplotlib

matplotlib.use("Agg")

from pathlib import Path

from cfd_perf.benchmark.models import PilotPoint, PilotSeries
from cfd_perf.io.plotting import plot_scaling
from cfd_perf.mesh.models import MeshStats
from cfd_perf.models.parameters import ModelParameters
from cfd_perf.optimizer.models import CandidateConfig, OptimizationResult, RejectedConfig

GB = 1 << 30


def _make_pilot() -> PilotSeries:
    return PilotSeries(
        points=(
            PilotPoint(cores=64, time_per_iter_s=1.0, peak_ram_total_gb=32.0),
            PilotPoint(cores=128, time_per_iter_s=0.625, peak_ram_total_gb=32.0),
        ),
        n_iterations=5000,
    )


def _make_mesh() -> MeshStats:
    return MeshStats(
        num_cells=2_000_000,
        num_faces=6_000_000,
        estimated_mem_per_cell_bytes=32.0 * GB / 2_000_000,
    )


def _make_params() -> ModelParameters:
    return ModelParameters(beta=0.25, beta_source="fixed")


def _make_result_efficiency() -> OptimizationResult:
    candidates = tuple(
        CandidateConfig(
            cores=nc,
            time_per_iter_s=1.0 / (nc / 64),
            runtime_hours=5000.0 / (nc / 64) / 3600,
            speedup=nc / 64,
            efficiency=1.0 - 0.001 * (nc - 64),
            efficiency_loss=0.001 * (nc - 64),
            ram_total_gb=32.0,
            ram_per_core_gb=32.0 / nc,
        )
        for nc in range(64, 257, 64)
    )
    rejected = (
        RejectedConfig(cores=320, reasons=("efficiency_loss",)),
        RejectedConfig(cores=384, reasons=("efficiency_loss",)),
    )
    return OptimizationResult(
        mode="efficiency",
        optimal=candidates[-1],
        accepted=candidates,
        rejected=rejected,
        metadata={"max_efficiency_loss": 0.25, "num_cells": 2_000_000, "n_iterations": 5000, "beta": 0.25},
    )


def _make_result_deadline() -> OptimizationResult:
    candidates = tuple(
        CandidateConfig(
            cores=nc,
            time_per_iter_s=1.0 / (nc / 64),
            runtime_hours=5000.0 / (nc / 64) / 3600,
            speedup=nc / 64,
            efficiency=1.0 - 0.001 * (nc - 64),
            efficiency_loss=0.001 * (nc - 64),
            ram_total_gb=32.0,
            ram_per_core_gb=32.0 / nc,
        )
        for nc in range(128, 257, 64)
    )
    rejected = (
        RejectedConfig(cores=64, reasons=("deadline",)),
    )
    return OptimizationResult(
        mode="deadline",
        optimal=candidates[0],
        accepted=candidates,
        rejected=rejected,
        metadata={"deadline_hours": 1.0, "num_cells": 2_000_000, "n_iterations": 5000, "beta": 0.25},
    )


class TestPlotScaling:
    def test_creates_file_with_pilot(self, tmp_path: Path) -> None:
        out = tmp_path / "scaling.png"
        path = plot_scaling(
            _make_result_efficiency(), out,
            pilot=_make_pilot(), mesh=_make_mesh(), params=_make_params(),
        )
        assert path is not None
        assert path.exists()

    def test_deadline_mode(self, tmp_path: Path) -> None:
        out = tmp_path / "scaling_dl.png"
        path = plot_scaling(
            _make_result_deadline(), out,
            pilot=_make_pilot(), mesh=_make_mesh(), params=_make_params(),
        )
        assert path is not None
        assert path.exists()

    def test_legacy_without_pilot(self, tmp_path: Path) -> None:
        out = tmp_path / "scaling_legacy.png"
        path = plot_scaling(_make_result_efficiency(), out)
        assert path is not None
        assert path.exists()

    def test_empty_returns_none(self) -> None:
        result = OptimizationResult(mode="deadline", optimal=None, accepted=(), rejected=())
        assert plot_scaling(result) is None
