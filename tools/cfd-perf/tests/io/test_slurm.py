"""Tests for SLURM snippet rendering."""

from cfd_perf.io.slurm import render_slurm_snippet
from cfd_perf.optimizer.models import CandidateConfig, OptimizationResult


def _make_result(cores: int = 128) -> OptimizationResult:
    opt = CandidateConfig(
        cores=cores, time_per_iter_s=0.625, runtime_hours=0.868,
        speedup=1.6, efficiency=0.8, efficiency_loss=0.2,
        ram_total_gb=32.0, ram_per_core_gb=0.25,
    )
    return OptimizationResult(mode="efficiency", optimal=opt, accepted=(opt,), rejected=())


class TestRenderSlurmSnippet:
    def test_contains_ntasks(self) -> None:
        snippet = render_slurm_snippet(_make_result(128))
        assert "#SBATCH --ntasks=128" in snippet

    def test_per_cpu_mem(self) -> None:
        snippet = render_slurm_snippet(_make_result(), mem_mode="per-cpu")
        assert "--mem-per-cpu=" in snippet

    def test_total_mem(self) -> None:
        snippet = render_slurm_snippet(_make_result(), mem_mode="total")
        assert "--mem=" in snippet
        assert "--mem-per-cpu" not in snippet

    def test_no_feasible(self) -> None:
        result = OptimizationResult(mode="deadline", optimal=None, accepted=(), rejected=())
        snippet = render_slurm_snippet(result)
        assert "No feasible" in snippet
