"""Tests for 2D structured interpolation and interpolated plotting."""

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest

from plotting import interpolate_field2d, plot_pcolormesh_interp, use_style


@pytest.fixture(autouse=True)
def _use_notebook_style():
    use_style("notebook")
    yield
    plt.close("all")


@pytest.fixture()
def coarse_field():
    """Coarse Gaussian on a 21 x 16 structured grid."""
    x = np.linspace(-2, 2, 21)
    y = np.linspace(-1.5, 1.5, 16)
    X, Y = np.meshgrid(x, y, indexing="xy")
    Z = np.exp(-(X**2 + Y**2))
    return x, y, X, Y, Z


# -----------------------------------------------------------------------
# interpolate_field2d — unit tests
# -----------------------------------------------------------------------
class TestInterpolateField2d:
    def test_output_shapes_factor2(self, coarse_field):
        x, y, _, _, Z = coarse_field
        xi, yi, zi = interpolate_field2d(x, y, Z, factor=2)
        assert xi.shape == (42,)
        assert yi.shape == (32,)
        assert zi.shape == (32, 42)

    def test_output_shapes_factor4(self, coarse_field):
        x, y, _, _, Z = coarse_field
        xi, yi, zi = interpolate_field2d(x, y, Z, factor=4)
        assert xi.shape == (84,)
        assert yi.shape == (64,)
        assert zi.shape == (64, 84)

    def test_linear_method(self, coarse_field):
        x, y, _, _, Z = coarse_field
        xi, yi, zi = interpolate_field2d(x, y, Z, factor=2, method="linear")
        assert zi.shape == (32, 42)

    def test_cubic_method(self, coarse_field):
        x, y, _, _, Z = coarse_field
        xi, yi, zi = interpolate_field2d(x, y, Z, factor=3, method="cubic")
        assert zi.shape == (48, 63)

    def test_2d_meshgrid_input(self, coarse_field):
        _, _, X, Y, Z = coarse_field
        xi, yi, zi = interpolate_field2d(X, Y, Z, factor=2)
        assert zi.shape == (32, 42)

    def test_coordinate_bounds_preserved(self, coarse_field):
        x, y, _, _, Z = coarse_field
        xi, yi, zi = interpolate_field2d(x, y, Z, factor=3)
        np.testing.assert_allclose(xi[0], x[0])
        np.testing.assert_allclose(xi[-1], x[-1])
        np.testing.assert_allclose(yi[0], y[0])
        np.testing.assert_allclose(yi[-1], y[-1])

    def test_monotonicity_preserved(self, coarse_field):
        x, y, _, _, Z = coarse_field
        xi, yi, _ = interpolate_field2d(x, y, Z, factor=5)
        assert np.all(np.diff(xi) > 0)
        assert np.all(np.diff(yi) > 0)

    def test_invalid_method_raises(self, coarse_field):
        x, y, _, _, Z = coarse_field
        with pytest.raises(ValueError, match="method=.*not supported"):
            interpolate_field2d(x, y, Z, method="quadratic")

    def test_1d_z_raises(self, coarse_field):
        x, y, _, _, _ = coarse_field
        with pytest.raises(ValueError, match="z must be 2D"):
            interpolate_field2d(x, y, np.ones(10))

    def test_shape_mismatch_raises(self):
        x = np.linspace(0, 1, 10)
        y = np.linspace(0, 1, 8)
        Z = np.ones((5, 5))
        with pytest.raises(ValueError):
            interpolate_field2d(x, y, Z)


# -----------------------------------------------------------------------
# plot_pcolormesh_interp — functional tests
# -----------------------------------------------------------------------
class TestPlotPcolormeshInterp:
    def test_returns_quadmesh_and_interp(self, coarse_field):
        x, y, _, _, Z = coarse_field
        fig, ax = plt.subplots()
        qm, cbar, (xi, yi, zi) = plot_pcolormesh_interp(
            ax, x, y, Z, factor=2,
        )
        assert qm is not None
        assert cbar is not None
        assert zi.shape == (32, 42)
        plt.close(fig)

    def test_no_colorbar(self, coarse_field):
        x, y, _, _, Z = coarse_field
        fig, ax = plt.subplots()
        qm, cbar, _ = plot_pcolormesh_interp(
            ax, x, y, Z, colorbar=False,
        )
        assert cbar is None
        plt.close(fig)

    def test_kwargs_forwarded(self, coarse_field):
        x, y, _, _, Z = coarse_field
        fig, ax = plt.subplots()
        qm, _, _ = plot_pcolormesh_interp(
            ax, x, y, Z, cmap="coolwarm", vmin=0, vmax=1, rasterized=True,
        )
        assert qm.get_rasterized() is True
        plt.close(fig)

    def test_linear_interp_plot(self, coarse_field):
        x, y, _, _, Z = coarse_field
        fig, ax = plt.subplots()
        qm, cbar, (xi, yi, zi) = plot_pcolormesh_interp(
            ax, x, y, Z, factor=3, method="linear",
        )
        assert zi.shape == (48, 63)
        plt.close(fig)
