"""Tests for the console report and figures.

These assert the report *says the right thing*, not that it looks a certain
way: the answer, the caveats, and the fit quality must all reach the user.
"""

from __future__ import annotations

import io
from pathlib import Path

import matplotlib
import pytest
from rich.console import Console

matplotlib.use("Agg")

from cfd_perf.core.constraints import Constraints
from cfd_perf.core.model import fit_model
from cfd_perf.data.study import load_study
from cfd_perf.engine.recommend import Strategy, recommend
from cfd_perf.report.console import format_duration, print_report
from cfd_perf.report.figures import plot_recommendation, save_recommendation_figure

EXAMPLE = Path(__file__).resolve().parents[2] / "01_EXEMPLE" / "ONERA_M6_CRUISE.yaml"


@pytest.fixture
def study():
    return load_study(EXAMPLE)


@pytest.fixture
def rec(study):
    model = fit_model(study.pilot)
    return recommend(
        model=model,
        mesh=study.mesh,
        pilot=study.pilot,
        machine=study.machine,
        constraints=study.constraints,
        strategy=study.objective.strategy,
        max_efficiency_loss=study.objective.max_efficiency_loss,
        cores_max=study.objective.cores_max,
    )


def render(rec, study, **kw) -> str:
    """Render the report to a string via Rich's recorder."""
    con = Console(file=io.StringIO(), record=True, width=100)
    print_report(rec, study, con=con, **kw)
    return con.export_text()


class TestDuration:
    @pytest.mark.parametrize(
        ("hours", "expected"),
        [
            (0.005, "18 s"),
            (0.5, "30 min"),
            (6.4, "6,4 h"),
            (50, "2 j 2 h"),
        ],
    )
    def test_formats(self, hours, expected):
        assert format_duration(hours) == expected


class TestReportContent:
    def test_reports_the_recommended_core_count(self, rec, study):
        text = render(rec, study)
        assert str(rec.choice.cores) in text
        assert "Réponse" in text

    def test_reports_nodes_on_a_node_based_machine(self, rec, study):
        text = render(rec, study)
        assert f"{rec.choice.nodes} nœuds de 48 cœurs" in text

    def test_shows_fit_quality(self, rec, study):
        from cfd_perf.report.console import _VERDICT_FR

        text = render(rec, study)
        assert "Qualité" in text
        assert _VERDICT_FR[rec.model.quality.verdict] in text

    def test_shows_measured_vs_predicted_for_every_pilot_point(self, rec, study):
        text = render(rec, study)
        assert "Modèle vs mesures pilotes" in text
        for p in study.pilot.points:
            assert str(p.cores) in text

    def test_verbose_adds_the_curve(self, rec, study):
        assert "Courbe de scalabilité" not in render(rec, study)
        assert "Courbe de scalabilité" in render(rec, study, verbose=True)

    def test_no_feasible_config_says_so_clearly(self, study):
        model = fit_model(study.pilot)
        empty = recommend(
            model=model,
            mesh=study.mesh,
            pilot=study.pilot,
            machine=study.machine,
            constraints=Constraints(max_core_hours=0.001),
            cores_max=200,
        )
        text = render(empty, study)
        assert "Aucune configuration réalisable" in text

    def test_alternatives_are_shown(self, rec, study):
        text = render(rec, study)
        assert "Alternatives" in text
        assert "recommandé" in text


class TestFigures:
    def test_figure_has_four_panels(self, rec):
        fig = plot_recommendation(rec)
        assert len(fig.axes) == 4

    def test_uses_the_in_house_plotting_library_when_available(self):
        """The figure is a deliverable: it must carry the house style."""
        from cfd_perf.report._plotting_lib import get_plotting

        assert get_plotting() is not None, "scripts/post/plot should be discoverable"

    def test_labels_are_in_french(self, rec):
        fig = plot_recommendation(rec)
        # Panel titles are set with loc="left", so get_title() must be asked
        # for that location rather than the centre default.
        titles = [ax.get_title(loc="left") for ax in fig.axes]
        assert "1. Combien de temps ?" in titles
        assert "4. Combien ça consomme ?" in titles

        ax = fig.axes[0]
        assert ax.get_xlabel() == "Cœurs"
        assert ax.get_ylabel() == "Durée totale (h)"
        assert "modèle" in {ln.get_label() for ln in ax.get_lines()}
        assert "pilote (mesuré)" in {c.get_label() for c in ax.collections}

    def test_no_english_left_in_the_figure_text(self, rec):
        fig = plot_recommendation(rec)
        parts = []
        for ax in fig.axes:
            parts += [ax.get_title(loc="left"), ax.get_xlabel(), ax.get_ylabel()]
            parts += [ln.get_label() for ln in ax.get_lines()]
        text = " ".join(parts).lower()
        for word in ("cores", "runtime", "speedup", "cost", "efficiency", "model", "pilot "):
            assert word not in text, f"English leaked into the figure: {word!r}"

    def test_saves_a_non_empty_png(self, rec, tmp_path):
        out = save_recommendation_figure(rec, tmp_path / "SUB" / "scaling.png")
        assert out.is_file()
        assert out.stat().st_size > 10_000

    def test_curve_passes_through_the_pilot_points(self, rec):
        """The plotted model line must pass through the measured markers.

        Read the plotted model line back out of the figure and assert it
        actually passes through each measured marker.
        """
        fig = plot_recommendation(rec)
        ax = fig.axes[0]
        model_line = next(ln for ln in ax.get_lines() if ln.get_label() == "modèle")
        xs, ys = model_line.get_xdata(), model_line.get_ydata()

        n_iter = rec.pilot.n_iterations
        for p in rec.pilot.points:
            idx = min(range(len(xs)), key=lambda i: abs(xs[i] - p.cores))
            measured_h = p.time_per_iter_s * n_iter / 3600
            rel = abs(ys[idx] - measured_h) / measured_h
            assert rel < 0.06, f"model line misses the {p.cores}-core pilot point by {rel:.1%}"

    def test_figure_renders_without_a_recommendation(self, study):
        model = fit_model(study.pilot)
        empty = recommend(
            model=model,
            mesh=study.mesh,
            pilot=study.pilot,
            machine=study.machine,
            constraints=Constraints(max_core_hours=0.001),
            cores_max=200,
        )
        assert len(plot_recommendation(empty).axes) == 4

    def test_fastest_strategy_figure(self, study):
        model = fit_model(study.pilot)
        r = recommend(
            model=model, mesh=study.mesh, pilot=study.pilot, machine=study.machine,
            strategy=Strategy.FASTEST, cores_max=1536,
        )
        assert len(plot_recommendation(r).axes) == 4
