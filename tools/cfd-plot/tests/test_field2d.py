"""Tests for field2d scalar plotting functions."""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest

from cfd_plot import plot_contour, plot_contourf, plot_imshow, plot_pcolormesh
from cfd_plot.field2d import _draw_mask_outline


@pytest.fixture()
def gaussian_field():
    """Gaussian scalar field on a 41 x 31 grid."""
    x = np.linspace(-1, 1, 41)
    y = np.linspace(-1, 1, 31)
    X, Y = np.meshgrid(x, y, indexing="xy")
    Z = np.exp(-(X**2 + Y**2))
    return x, y, X, Y, Z


class TestPlotContour:
    def test_returns_contour_set(self, gaussian_field):
        x, y, _, _, Z = gaussian_field
        fig, ax = plt.subplots()
        cs, cbar = plot_contour(ax, x, y, Z, levels=8)
        assert cs is not None
        assert cbar is None
        plt.close(fig)

    def test_colorbar(self, gaussian_field):
        x, y, _, _, Z = gaussian_field
        fig, ax = plt.subplots()
        cs, cbar = plot_contour(ax, x, y, Z, colorbar=True, cbar_label="test")
        assert cbar is not None
        plt.close(fig)

    def test_2d_coords(self, gaussian_field):
        _, _, X, Y, Z = gaussian_field
        fig, ax = plt.subplots()
        cs, _ = plot_contour(ax, X, Y, Z, levels=5, colors="k")
        assert cs is not None
        plt.close(fig)


class TestPlotContourf:
    def test_default_colorbar(self, gaussian_field):
        x, y, _, _, Z = gaussian_field
        fig, ax = plt.subplots()
        cf, cbar = plot_contourf(ax, x, y, Z)
        assert cbar is not None
        plt.close(fig)

    def test_no_colorbar(self, gaussian_field):
        x, y, _, _, Z = gaussian_field
        fig, ax = plt.subplots()
        cf, cbar = plot_contourf(ax, x, y, Z, colorbar=False)
        assert cbar is None
        plt.close(fig)

    def test_custom_levels(self, gaussian_field):
        x, y, _, _, Z = gaussian_field
        fig, ax = plt.subplots()
        levels = np.linspace(0, 1, 11)
        cf, _ = plot_contourf(ax, x, y, Z, levels=levels, cmap="inferno")
        assert cf is not None
        plt.close(fig)

    def test_bad_color(self, gaussian_field):
        x, y, X, Y, Z = gaussian_field
        Z_masked = np.ma.masked_where(X**2 + Y**2 < 0.3, Z)
        fig, ax = plt.subplots()
        cf, _ = plot_contourf(ax, x, y, Z_masked, bad_color="black")
        assert cf is not None
        plt.close(fig)


class TestPlotPcolormesh:
    def test_default(self, gaussian_field):
        x, y, _, _, Z = gaussian_field
        fig, ax = plt.subplots()
        qm, cbar = plot_pcolormesh(ax, x, y, Z, cbar_label="Pressure")
        assert qm is not None
        assert cbar is not None
        plt.close(fig)

    def test_rasterized(self, gaussian_field):
        x, y, _, _, Z = gaussian_field
        fig, ax = plt.subplots()
        qm, _ = plot_pcolormesh(ax, x, y, Z, rasterized=True)
        assert qm.get_rasterized() is True
        plt.close(fig)

    def test_norm(self, gaussian_field):
        from matplotlib.colors import TwoSlopeNorm
        x, y, _, _, Z = gaussian_field
        norm = TwoSlopeNorm(vmin=0, vcenter=0.5, vmax=1)
        fig, ax = plt.subplots()
        qm, _ = plot_pcolormesh(ax, x, y, Z, norm=norm, cmap="RdBu_r")
        plt.close(fig)

    def test_nonuniform_grid(self):
        x = np.array([0, 0.1, 0.5, 1.0, 2.0])
        y = np.array([0, 0.2, 1.0])
        Z = np.random.RandomState(0).rand(3, 5)
        fig, ax = plt.subplots()
        qm, _ = plot_pcolormesh(ax, x, y, Z, shading="auto")
        plt.close(fig)

    def test_bad_color(self, gaussian_field):
        x, y, X, Y, Z = gaussian_field
        Z_masked = np.ma.masked_where(X > 0.5, Z)
        fig, ax = plt.subplots()
        qm, _ = plot_pcolormesh(ax, x, y, Z_masked, bad_color="black")
        cmap_used = qm.get_cmap()
        bad_rgba = cmap_used(np.ma.masked)
        assert bad_rgba == (0.0, 0.0, 0.0, 1.0)
        plt.close(fig)


class TestPlotImshow:
    def test_default(self, gaussian_field):
        _, _, _, _, Z = gaussian_field
        fig, ax = plt.subplots()
        im, cbar = plot_imshow(ax, Z, cbar_label="Field")
        assert im is not None
        assert cbar is not None
        plt.close(fig)

    def test_extent(self, gaussian_field):
        x, y, _, _, Z = gaussian_field
        fig, ax = plt.subplots()
        im, _ = plot_imshow(
            ax, Z,
            extent=(x.min(), x.max(), y.min(), y.max()),
        )
        plt.close(fig)

    def test_z_not_2d(self):
        fig, ax = plt.subplots()
        with pytest.raises(ValueError, match="z must be 2D"):
            plot_imshow(ax, np.arange(10))
        plt.close(fig)

    def test_aspect_none(self, gaussian_field):
        _, _, _, _, Z = gaussian_field
        fig, ax = plt.subplots()
        im, _ = plot_imshow(ax, Z, aspect=None)
        plt.close(fig)

    def test_bad_color(self, gaussian_field):
        _, _, _, _, Z = gaussian_field
        Z_nan = Z.copy()
        Z_nan[5:10, 5:10] = np.nan
        fig, ax = plt.subplots()
        im, _ = plot_imshow(ax, Z_nan, bad_color="red")
        cmap_used = im.get_cmap()
        bad_rgba = cmap_used(np.ma.masked)
        assert bad_rgba == (1.0, 0.0, 0.0, 1.0)
        plt.close(fig)


# ---------------------------------------------------------------------------
# Mask outline overlay
# ---------------------------------------------------------------------------

class TestMaskOutline:
    """Tests for the mask_outline overlay on plot_pcolormesh / plot_contourf."""

    @pytest.fixture()
    def masked_field(self):
        """Gaussian field with a circular solid region (IND=1)."""
        x = np.linspace(-1, 1, 41)
        y = np.linspace(-1, 1, 31)
        X, Y = np.meshgrid(x, y, indexing="xy")
        Z = np.exp(-(X**2 + Y**2))
        IND = (X**2 + Y**2 < 0.3).astype(float)
        fluid_mask = IND == 0
        Z_nan = Z.copy()
        Z_nan[~fluid_mask] = np.nan
        return x, y, X, Y, Z_nan, fluid_mask

    def test_pcolormesh_with_outline(self, masked_field):
        x, y, _, _, Z_nan, fluid_mask = masked_field
        fig, ax = plt.subplots()
        qm, cbar = plot_pcolormesh(
            ax, x, y, Z_nan,
            mask_outline=fluid_mask,
            mask_outline_color="k",
        )
        assert qm is not None
        contour_sets = [c for c in ax.collections
                        if hasattr(c, "get_paths") and c is not qm]
        assert len(contour_sets) > 0
        plt.close(fig)

    def test_contourf_with_outline(self, masked_field):
        x, y, _, _, Z_nan, fluid_mask = masked_field
        fig, ax = plt.subplots()
        cf, cbar = plot_contourf(
            ax, x, y, Z_nan,
            mask_outline=fluid_mask,
            mask_outline_width=2.0,
        )
        assert cf is not None
        plt.close(fig)

    def test_outline_shape_mismatch(self, masked_field):
        x, y, _, _, Z_nan, _ = masked_field
        wrong_shape = np.ones((5, 5), dtype=bool)
        fig, ax = plt.subplots()
        with pytest.raises(ValueError, match="mask_outline shape"):
            plot_pcolormesh(ax, x, y, Z_nan, mask_outline=wrong_shape)
        plt.close(fig)

    def test_no_outline_by_default(self, masked_field):
        """When mask_outline is None (default), no extra artists appear."""
        x, y, _, _, Z_nan, _ = masked_field
        fig, ax = plt.subplots()
        qm, _ = plot_pcolormesh(ax, x, y, Z_nan)
        n_collections = len(ax.collections)
        assert n_collections == 1
        plt.close(fig)

    def test_draw_mask_outline_directly(self, masked_field):
        """The internal helper draws a contour on existing axes."""
        _, _, X, Y, _, fluid_mask = masked_field
        fig, ax = plt.subplots()
        _draw_mask_outline(ax, X, Y, fluid_mask, color="red", linewidths=2.0)
        assert len(ax.collections) > 0
        plt.close(fig)
