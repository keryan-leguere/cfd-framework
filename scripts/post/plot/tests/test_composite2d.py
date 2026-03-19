"""Tests for composite2d combined plots."""

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest

from plotting import plot_contour_quiver


@pytest.fixture()
def scalar_vector_field():
    x = np.linspace(-1, 1, 41)
    y = np.linspace(-1, 1, 31)
    X, Y = np.meshgrid(x, y, indexing="xy")
    Z = np.exp(-(X**2 + Y**2))
    U = -Y
    V = X
    return x, y, Z, U, V


class TestPlotContourQuiver:
    def test_contourf(self, scalar_vector_field):
        x, y, Z, U, V = scalar_vector_field
        fig, ax = plt.subplots()
        artist, q, cbar = plot_contour_quiver(
            ax, x, y, Z, U, V,
            scalar_kind="contourf",
            quiver_stride=4,
            cbar_label="Scalar",
        )
        assert artist is not None
        assert q is not None
        assert cbar is not None
        plt.close(fig)

    def test_pcolormesh(self, scalar_vector_field):
        x, y, Z, U, V = scalar_vector_field
        fig, ax = plt.subplots()
        artist, q, cbar = plot_contour_quiver(
            ax, x, y, Z, U, V,
            scalar_kind="pcolormesh",
            quiver_stride=3,
        )
        plt.close(fig)

    def test_contour(self, scalar_vector_field):
        x, y, Z, U, V = scalar_vector_field
        fig, ax = plt.subplots()
        artist, q, cbar = plot_contour_quiver(
            ax, x, y, Z, U, V,
            scalar_kind="contour",
            quiver_stride=5,
            quiver_color="red",
        )
        plt.close(fig)

    def test_invalid_scalar_kind(self, scalar_vector_field):
        x, y, Z, U, V = scalar_vector_field
        fig, ax = plt.subplots()
        with pytest.raises(ValueError, match="scalar_kind"):
            plot_contour_quiver(ax, x, y, Z, U, V, scalar_kind="imshow")
        plt.close(fig)
