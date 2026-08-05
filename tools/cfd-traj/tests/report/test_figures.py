"""Figures Matplotlib.

Le backend Agg est forcé par ``tests/conftest.py``. Chaque figure est vérifiée
deux fois : avec ``cfd_plot`` tel qu'il est installé, et avec le shim forcé à
None — le paquet doit rester utilisable sans son voisin optionnel.
"""

from __future__ import annotations

import pytest

from cfd_traj.core.symmetry import SymmetryGroup, SymmetrySpec
from cfd_traj.data.columns import build_specs
from cfd_traj.data.study import BandSpec, DoeMethod, DoeSpec, EnvelopeSpec
from cfd_traj.engine.bands import build_bands
from cfd_traj.engine.coverage import check_coverage
from cfd_traj.engine.doe import build_plan
from cfd_traj.engine.envelope import build_envelope
from cfd_traj.engine.inspect import inspect
from cfd_traj.report import figures
from cfd_traj.report._plotting_lib import HAS_PLOTTING

C4V = SymmetrySpec(group=SymmetryGroup.C4V)

#: En dessous, le fichier écrit n'est pas une vraie figure.
MIN_BYTES = 10_000


@pytest.fixture
def contexte(dataset_realiste):
    """Enveloppe, plan, couverture et inspection d'un lot réaliste."""
    specs, _ = build_specs(dataset_realiste.columns, dataset_realiste.column_values(), {})
    bands = build_bands(dataset_realiste.values("Mach"), BandSpec(n_bands=4, min_points=50))
    envelope = build_envelope(
        dataset_realiste, band_set=bands, specs=specs, spec=EnvelopeSpec(), symmetry=C4V
    )
    plan = build_plan(
        envelope,
        doe=DoeSpec(method=DoeMethod.LHS, n_lhs_per_band=5, max_nodes=100_000),
        symmetry=C4V,
        ds=dataset_realiste,
    )
    return {
        "ds": dataset_realiste,
        "envelope": envelope,
        "plan": plan,
        "coverage": check_coverage(dataset_realiste, envelope=envelope),
        "inspection": inspect(dataset_realiste, specs=specs),
    }


@pytest.fixture
def sans_cfd_plot(monkeypatch):
    """Force le repli sur Matplotlib nu."""
    monkeypatch.setattr(figures, "get_plotting", lambda: None)


def _write(fig, path):
    target = figures.save_figure(fig, path)
    assert target.exists()
    assert target.stat().st_size > MIN_BYTES
    return target


class TestEnvelopeFigure:
    def test_it_writes_a_real_file(self, contexte, tmp_path):
        fig = figures.plot_envelope(contexte["ds"], contexte["envelope"], title="essai")

        _write(fig, tmp_path / "env.png")

    def test_it_works_without_cfd_plot(self, contexte, tmp_path, sans_cfd_plot):
        _write(figures.plot_envelope(contexte["ds"], contexte["envelope"]), tmp_path / "env.png")

    def test_the_ordinate_can_be_chosen(self, contexte, tmp_path):
        _write(
            figures.plot_envelope(contexte["ds"], contexte["envelope"], ordinate="alpha_tot"),
            tmp_path / "env.png",
        )

    def test_a_lot_without_generic_columns_falls_back_to_the_incidence(self, make_lot, tmp_path):
        from cfd_traj.core.adim import Reference
        from cfd_traj.data.dataset import load_dataset
        from cfd_traj.data.derive import add_derived_columns

        ds = add_derived_columns(
            load_dataset(make_lot(n_shots=2, extra=())),
            reference=Reference(length_m=2.5),
            symmetry=C4V,
        )
        specs, _ = build_specs(ds.columns, ds.column_values(), {})
        bands = build_bands(ds.values("Mach"), BandSpec(n_bands=2, min_points=10))
        envelope = build_envelope(
            ds, band_set=bands, specs=specs, spec=EnvelopeSpec(), symmetry=C4V
        )

        _write(figures.plot_envelope(ds, envelope), tmp_path / "env.png")


class TestInspectionFigure:
    def test_it_writes_a_real_file(self, contexte, tmp_path):
        _write(figures.plot_inspection(contexte["inspection"], title="essai"), tmp_path / "acp.png")

    def test_it_works_without_cfd_plot(self, contexte, tmp_path, sans_cfd_plot):
        _write(figures.plot_inspection(contexte["inspection"]), tmp_path / "acp.png")

    def test_a_missing_analysis_is_drawn_as_a_message(self, dataset_realiste, tmp_path):
        specs, _ = build_specs(dataset_realiste.columns, dataset_realiste.column_values(), {})
        inspection = inspect(dataset_realiste, specs=specs, with_pca=False)

        assert inspection.pca is None
        _write(figures.plot_inspection(inspection), tmp_path / "acp.png")


class TestPlanFigure:
    def test_it_writes_a_real_file(self, contexte, tmp_path):
        _write(
            figures.plot_plan(contexte["plan"], contexte["ds"], title="essai"),
            tmp_path / "plan.png",
        )

    def test_it_works_without_the_cloud(self, contexte, tmp_path):
        _write(figures.plot_plan(contexte["plan"]), tmp_path / "plan.png")

    def test_it_works_without_cfd_plot(self, contexte, tmp_path, sans_cfd_plot):
        _write(figures.plot_plan(contexte["plan"], contexte["ds"]), tmp_path / "plan.png")


class TestCoverageFigure:
    def test_it_writes_a_real_file(self, contexte, tmp_path):
        _write(figures.plot_coverage(contexte["coverage"], title="essai"), tmp_path / "cov.png")

    def test_it_works_without_cfd_plot(self, contexte, tmp_path, sans_cfd_plot):
        _write(figures.plot_coverage(contexte["coverage"]), tmp_path / "cov.png")

    def test_a_complete_coverage_draws_the_reassuring_message(
        self, dataset_realiste, envelope_exacte, tmp_path
    ):
        result = check_coverage(dataset_realiste, envelope=envelope_exacte)

        assert result.is_complete
        _write(figures.plot_coverage(result), tmp_path / "cov.png")


class TestSaving:
    @pytest.mark.parametrize("suffix", [".png", ".pdf", ".svg"])
    def test_the_usual_formats_are_accepted(self, contexte, tmp_path, suffix):
        fig = figures.plot_coverage(contexte["coverage"])

        target = figures.save_figure(fig, tmp_path / f"cov{suffix}")

        assert target.exists()

    def test_a_missing_directory_is_created(self, contexte, tmp_path):
        fig = figures.plot_coverage(contexte["coverage"])

        target = figures.save_figure(fig, tmp_path / "a" / "b" / "cov.png")

        assert target.exists()


@pytest.mark.skipif(not HAS_PLOTTING, reason="cfd-plot n'est pas installé")
class TestWithCfdPlot:
    def test_every_figure_renders_through_cfd_plot(self, contexte, tmp_path):
        _write(figures.plot_envelope(contexte["ds"], contexte["envelope"]), tmp_path / "a.png")
        _write(figures.plot_inspection(contexte["inspection"]), tmp_path / "b.png")
        _write(figures.plot_plan(contexte["plan"], contexte["ds"]), tmp_path / "c.png")
        _write(figures.plot_coverage(contexte["coverage"]), tmp_path / "d.png")
