"""Smoke tests for dispersion.plots — each function must run without error."""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest

from cfd_plot.dispersion import (
    DispersionSpec,
    QuantityDispersion,
    plot_dispersion_cdf,
    plot_dispersion_dashboard,
    plot_dispersion_matrix,
    plot_dispersion_pdf,
    plot_dispersion_type,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

RNG = np.random.default_rng(0)


@pytest.fixture()
def qty_gaussian():
    return QuantityDispersion(
        name="Cm_alpha",
        nominal=-2.5,
        bias=DispersionSpec(disp_type=5, moy=0.0, var=0.015),
        scale=DispersionSpec(disp_type=6, moy=0.0, var=0.10),
    )


@pytest.fixture()
def qty_uniform():
    return QuantityDispersion(
        name="CL",
        nominal=0.8,
        bias=DispersionSpec(disp_type=3, moy=0.0, var=0.02),
        scale=DispersionSpec(disp_type=3, moy=0.0, var=0.05),
    )


@pytest.fixture()
def qty_list(qty_gaussian, qty_uniform):
    qty3 = QuantityDispersion(
        name="CD",
        nominal=0.05,
        bias=DispersionSpec(disp_type=4, moy=0.0, var=0.005),
        scale=DispersionSpec(disp_type=2, moy=0.0, var=0.0),
    )
    return [qty_gaussian, qty_uniform, qty3]


# ---------------------------------------------------------------------------
# plot_dispersion_type
# ---------------------------------------------------------------------------

class TestPlotDispersionType:
    @pytest.mark.parametrize("disp_type", [1, 2, 3, 4, 5, 6])
    def test_all_types_create_figure(self, disp_type):
        spec = DispersionSpec(disp_type=disp_type, moy=0.0, var=1.0)
        fig, ax = plot_dispersion_type(spec)
        assert fig is not None
        assert ax is not None
        plt.close(fig)

    def test_external_ax(self):
        spec = DispersionSpec(disp_type=4, moy=1.0, var=0.5)
        fig_ext, ax_ext = plt.subplots()
        fig_ret, ax_ret = plot_dispersion_type(spec, ax=ax_ext)
        assert ax_ret is ax_ext
        assert fig_ret is fig_ext
        plt.close(fig_ext)

    def test_color_kwarg(self):
        spec = DispersionSpec(disp_type=3, moy=0.0, var=1.0)
        fig, ax = plot_dispersion_type(spec, color="red")
        plt.close(fig)

    def test_type1_null_zero_moy(self):
        spec = DispersionSpec(disp_type=1, moy=0.0, var=0.0)
        fig, ax = plot_dispersion_type(spec)
        plt.close(fig)

    def test_type3_var_zero(self):
        spec = DispersionSpec(disp_type=3, moy=2.0, var=0.0)
        fig, ax = plot_dispersion_type(spec)
        plt.close(fig)

    def test_type5_var_zero(self):
        spec = DispersionSpec(disp_type=5, moy=0.0, var=0.0)
        fig, ax = plot_dispersion_type(spec)
        plt.close(fig)


# ---------------------------------------------------------------------------
# plot_dispersion_pdf
# ---------------------------------------------------------------------------

class TestPlotDispersionPdf:
    def test_returns_fig_ax(self, qty_gaussian):
        fig, ax = plot_dispersion_pdf(qty_gaussian, n=200, rng=RNG)
        assert fig is not None
        plt.close(fig)

    def test_external_ax(self, qty_uniform):
        fig_ext, ax_ext = plt.subplots()
        fig_ret, ax_ret = plot_dispersion_pdf(qty_uniform, n=200, ax=ax_ext, rng=RNG)
        assert ax_ret is ax_ext
        plt.close(fig_ext)

    def test_custom_color(self, qty_gaussian):
        fig, ax = plot_dispersion_pdf(qty_gaussian, n=200, color="green", rng=RNG)
        plt.close(fig)

    def test_constant_spec_no_crash(self):
        qty = QuantityDispersion(
            name="const",
            nominal=1.0,
            bias=DispersionSpec(disp_type=2, moy=0.0, var=0.0),
            scale=DispersionSpec(disp_type=1, moy=0.0, var=0.0),
        )
        fig, ax = plot_dispersion_pdf(qty, n=200, rng=RNG)
        plt.close(fig)


# ---------------------------------------------------------------------------
# plot_dispersion_cdf
# ---------------------------------------------------------------------------

class TestPlotDispersionCdf:
    def test_returns_fig_ax(self, qty_gaussian):
        fig, ax = plot_dispersion_cdf(qty_gaussian, n=300, rng=RNG)
        assert fig is not None
        plt.close(fig)

    def test_external_ax(self, qty_uniform):
        fig_ext, ax_ext = plt.subplots()
        fig_ret, ax_ret = plot_dispersion_cdf(qty_uniform, n=300, ax=ax_ext, rng=RNG)
        assert ax_ret is ax_ext
        plt.close(fig_ext)

    def test_custom_color(self, qty_gaussian):
        fig, ax = plot_dispersion_cdf(qty_gaussian, n=300, color="purple", rng=RNG)
        plt.close(fig)


# ---------------------------------------------------------------------------
# plot_dispersion_dashboard
# ---------------------------------------------------------------------------

class TestPlotDispersionDashboard:
    def test_returns_fig_axes(self, qty_gaussian):
        fig, axes = plot_dispersion_dashboard(qty_gaussian, n=200, rng=RNG)
        assert fig is not None
        assert axes.shape == (3,)
        plt.close(fig)

    def test_savefig_idiom(self, qty_gaussian, tmp_path):
        fig, _ = plot_dispersion_dashboard(qty_gaussian, n=200, rng=RNG)
        out = tmp_path / "dash.png"
        fig.savefig(str(out))
        assert out.exists()
        plt.close(fig)


# ---------------------------------------------------------------------------
# plot_dispersion_matrix
# ---------------------------------------------------------------------------

class TestPlotDispersionMatrix:
    def test_returns_fig_axes(self, qty_list):
        fig, axes = plot_dispersion_matrix(qty_list, n=200, rng=RNG)
        assert fig is not None
        plt.close(fig)

    def test_ncols_kwarg(self, qty_list):
        fig, axes = plot_dispersion_matrix(qty_list, n=200, ncols=2, rng=RNG)
        assert axes.shape[1] == 2
        plt.close(fig)

    def test_share_x_false(self, qty_list):
        fig, axes = plot_dispersion_matrix(qty_list, n=200, share_x=False, rng=RNG)
        plt.close(fig)

    def test_single_qty(self, qty_gaussian):
        fig, axes = plot_dispersion_matrix([qty_gaussian], n=200, rng=RNG)
        plt.close(fig)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            plot_dispersion_matrix([], n=200)
