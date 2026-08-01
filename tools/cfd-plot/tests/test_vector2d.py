"""Tests for vector2d plotting and utility functions."""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest

from cfd_plot import compute_speed, plot_quiver, plot_streamplot, subsample_vectors


@pytest.fixture()
def rotation_field():
    """Solid-body rotation on an 81 x 61 grid."""
    x = np.linspace(-1, 1, 81)
    y = np.linspace(-1, 1, 61)
    X, Y = np.meshgrid(x, y, indexing="xy")
    U = -Y
    V = X
    return x, y, X, Y, U, V


# ---------------------------------------------------------------------------
# compute_speed
# ---------------------------------------------------------------------------

class TestComputeSpeed:
    def test_basic(self):
        u = np.array([[3.0, 0.0], [0.0, 1.0]])
        v = np.array([[4.0, 1.0], [0.0, 0.0]])
        s = compute_speed(u, v)
        np.testing.assert_allclose(s, [[5.0, 1.0], [0.0, 1.0]])

    def test_shape_preserved(self, rotation_field):
        _, _, _, _, U, V = rotation_field
        s = compute_speed(U, V)
        assert s.shape == U.shape


# ---------------------------------------------------------------------------
# subsample_vectors
# ---------------------------------------------------------------------------

class TestSubsampleVectors:
    def test_stride_int(self, rotation_field):
        _, _, X, Y, U, V = rotation_field
        Xs, Ys, Us, Vs = subsample_vectors(X, Y, U, V, stride=5)
        assert Xs.shape[0] < X.shape[0]
        assert Xs.shape[1] < X.shape[1]

    def test_stride_tuple(self, rotation_field):
        _, _, X, Y, U, V = rotation_field
        Xs, Ys, Us, Vs = subsample_vectors(X, Y, U, V, stride=(4, 8))
        assert Xs.shape[0] == len(range(0, 61, 4))
        assert Xs.shape[1] == len(range(0, 81, 8))

    def test_target(self, rotation_field):
        _, _, X, Y, U, V = rotation_field
        Xs, Ys, Us, Vs = subsample_vectors(X, Y, U, V, target=10)
        assert Xs.shape[0] <= 12
        assert Xs.shape[1] <= 12

    def test_1d_coords(self, rotation_field):
        x, y, _, _, U, V = rotation_field
        Xs, Ys, Us, Vs = subsample_vectors(x, y, U, V, stride=3)
        assert Xs.ndim == 2


# ---------------------------------------------------------------------------
# plot_quiver
# ---------------------------------------------------------------------------

class TestPlotQuiver:
    def test_basic(self, rotation_field):
        x, y, _, _, U, V = rotation_field
        fig, ax = plt.subplots()
        q, cbar = plot_quiver(ax, x, y, U, V, stride=5, color="k")
        assert q is not None
        assert cbar is None
        plt.close(fig)

    def test_magnitude_color(self, rotation_field):
        x, y, _, _, U, V = rotation_field
        fig, ax = plt.subplots()
        q, cbar = plot_quiver(
            ax, x, y, U, V,
            stride=4,
            magnitude_color=True,
            colorbar=True,
            cbar_label="|V|",
        )
        assert cbar is not None
        plt.close(fig)

    def test_no_stride(self, rotation_field):
        x, y, _, _, U, V = rotation_field
        fig, ax = plt.subplots()
        q, _ = plot_quiver(ax, x, y, U, V, color="b")
        plt.close(fig)


# ---------------------------------------------------------------------------
# plot_streamplot
# ---------------------------------------------------------------------------

class TestPlotStreamplot:
    def test_basic(self, rotation_field):
        x, y, _, _, U, V = rotation_field
        fig, ax = plt.subplots()
        sp, cbar = plot_streamplot(ax, x, y, U, V, density=1.0)
        assert sp is not None
        plt.close(fig)

    def test_colored_by_speed(self, rotation_field):
        x, y, _, _, U, V = rotation_field
        speed = compute_speed(U, V)
        fig, ax = plt.subplots()
        sp, cbar = plot_streamplot(
            ax, x, y, U, V,
            color=speed,
            cmap="plasma",
            colorbar=True,
            cbar_label="Speed",
        )
        assert cbar is not None
        plt.close(fig)

    def test_2d_coords(self, rotation_field):
        _, _, X, Y, U, V = rotation_field
        fig, ax = plt.subplots()
        sp, _ = plot_streamplot(ax, X, Y, U, V, density=0.8)
        plt.close(fig)

    def test_shape_mismatch(self, rotation_field):
        x, y, _, _, U, V = rotation_field
        fig, ax = plt.subplots()
        with pytest.raises(ValueError, match="does not match grid"):
            plot_streamplot(ax, x, y, U.T, V.T)
        plt.close(fig)
