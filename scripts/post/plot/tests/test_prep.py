"""Tests for prep data-preparation utilities."""

import numpy as np
import pandas as pd
import pytest

from plotting import dataframe_to_grid, extract_slice2d, reshape_structured2d


# ---------------------------------------------------------------------------
# reshape_structured2d
# ---------------------------------------------------------------------------

class TestReshapeStructured2d:
    def test_round_trip(self):
        x = np.linspace(0, 1, 21)
        y = np.linspace(0, 0.5, 11)
        X, Y = np.meshgrid(x, y, indexing="xy")
        Z = np.sin(np.pi * X) * np.cos(2 * np.pi * Y)
        X2, Y2, Z2 = reshape_structured2d(X.ravel(), Y.ravel(), Z.ravel())
        np.testing.assert_allclose(Z2, Z)
        np.testing.assert_allclose(X2, X)
        np.testing.assert_allclose(Y2, Y)

    def test_dict_values(self):
        x = np.arange(5, dtype=float)
        y = np.arange(3, dtype=float)
        X, Y = np.meshgrid(x, y, indexing="xy")
        A = X + Y
        B = X * Y
        X2, Y2, fields = reshape_structured2d(
            X.ravel(), Y.ravel(), {"a": A.ravel(), "b": B.ravel()}
        )
        np.testing.assert_allclose(fields["a"], A)
        np.testing.assert_allclose(fields["b"], B)

    def test_incomplete_grid(self):
        with pytest.raises(ValueError, match="Cannot reshape"):
            reshape_structured2d([0, 0, 1], [0, 1, 0], [1, 2, 3])

    def test_field_length_mismatch(self):
        with pytest.raises(ValueError, match="elements, expected"):
            reshape_structured2d(
                [0, 0, 1, 1], [0, 1, 0, 1], [10, 20, 30]
            )

    def test_dict_field_length_mismatch(self):
        with pytest.raises(ValueError, match="elements, expected"):
            reshape_structured2d(
                [0, 0, 1, 1], [0, 1, 0, 1],
                {"a": [10, 20, 30, 40], "b": [1, 2, 3]},
            )

    def test_shuffled_order(self):
        """Points arrive in random order but still reshape correctly."""
        rng = np.random.RandomState(42)
        x = np.arange(4, dtype=float)
        y = np.arange(3, dtype=float)
        X, Y = np.meshgrid(x, y, indexing="xy")
        Z = X + 10 * Y
        idx = rng.permutation(X.size)
        X2, Y2, Z2 = reshape_structured2d(
            X.ravel()[idx], Y.ravel()[idx], Z.ravel()[idx]
        )
        np.testing.assert_allclose(Z2, Z)


# ---------------------------------------------------------------------------
# dataframe_to_grid
# ---------------------------------------------------------------------------

class TestDataframeToGrid:
    def _make_df(self):
        x = np.arange(5, dtype=float)
        y = np.arange(3, dtype=float)
        X, Y = np.meshgrid(x, y, indexing="xy")
        P = X + Y
        U = -Y
        return pd.DataFrame({
            "x": X.ravel(), "y": Y.ravel(), "p": P.ravel(), "u": U.ravel()
        }), X, Y, P, U

    def test_single_field(self):
        df, _, _, P, _ = self._make_df()
        xg, yg, p = dataframe_to_grid(df, values="p")
        np.testing.assert_allclose(p, P)

    def test_multiple_fields(self):
        df, _, _, P, U = self._make_df()
        xg, yg, flds = dataframe_to_grid(df, values=["p", "u"])
        np.testing.assert_allclose(flds["p"], P)
        np.testing.assert_allclose(flds["u"], U)

    def test_auto_values(self):
        df, _, _, _, _ = self._make_df()
        xg, yg, flds = dataframe_to_grid(df)
        assert "p" in flds and "u" in flds

    def test_duplicates(self):
        df = pd.DataFrame({"x": [0, 0, 1], "y": [0, 0, 1], "p": [1, 2, 3]})
        with pytest.raises(ValueError, match="duplicate"):
            dataframe_to_grid(df, values="p")

    def test_sorted_output(self):
        df = pd.DataFrame({
            "x": [2.0, 1.0, 2.0, 1.0],
            "y": [1.0, 1.0, 0.0, 0.0],
            "v": [4.0, 3.0, 2.0, 1.0],
        })
        xg, yg, v = dataframe_to_grid(df, values="v")
        np.testing.assert_array_equal(xg, [1.0, 2.0])
        np.testing.assert_array_equal(yg, [0.0, 1.0])
        np.testing.assert_array_equal(v, [[1.0, 2.0], [3.0, 4.0]])


# ---------------------------------------------------------------------------
# extract_slice2d
# ---------------------------------------------------------------------------

class TestExtractSlice2d:
    @pytest.fixture()
    def field_3d(self):
        """3D Gaussian field in ij convention: shape (nx, ny, nz)."""
        x = np.linspace(-1, 1, 41)
        y = np.linspace(-1, 1, 51)
        z = np.linspace(0, 2, 31)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
        F = np.exp(-(X**2 + Y**2 + (Z - 1)**2))
        return x, y, z, F

    def test_slice_z_by_index(self, field_3d):
        x, y, z, F = field_3d
        C1, C2, s = extract_slice2d(F, axis="z", index=15, x=x, y=y, z=z)
        assert s.shape == (41, 51)
        assert C1.shape == s.shape
        np.testing.assert_allclose(s, F[:, :, 15])

    def test_slice_z_by_coord(self, field_3d):
        x, y, z, F = field_3d
        C1, C2, s = extract_slice2d(F, axis="z", coord=1.0, x=x, y=y, z=z)
        expected_idx = np.argmin(np.abs(z - 1.0))
        np.testing.assert_allclose(s, F[:, :, expected_idx])

    def test_slice_x(self, field_3d):
        x, y, z, F = field_3d
        C1, C2, s = extract_slice2d(F, axis="x", index=20, x=x, y=y, z=z)
        assert s.shape == (51, 31)
        np.testing.assert_allclose(s, F[20, :, :])

    def test_slice_y(self, field_3d):
        x, y, z, F = field_3d
        C1, C2, s = extract_slice2d(F, axis="y", coord=0.0, x=x, y=y, z=z)
        assert s.shape == (41, 31)

    def test_both_index_and_coord(self, field_3d):
        _, _, _, F = field_3d
        with pytest.raises(ValueError, match="either index or coord"):
            extract_slice2d(F, axis="x", index=0, coord=0.5, x=[0, 1])

    def test_neither_index_nor_coord(self, field_3d):
        _, _, _, F = field_3d
        with pytest.raises(ValueError, match="either index or coord"):
            extract_slice2d(F, axis="x")

    def test_bad_axis(self, field_3d):
        _, _, _, F = field_3d
        with pytest.raises(ValueError, match="'x', 'y', or 'z'"):
            extract_slice2d(F, axis="w", index=0)

    def test_not_3d(self):
        with pytest.raises(ValueError, match="must be 3D"):
            extract_slice2d(np.ones((3, 4)), axis="x", index=0)

    def test_coord_without_vector(self, field_3d):
        _, _, _, F = field_3d
        with pytest.raises(ValueError, match="Coordinate array"):
            extract_slice2d(F, axis="x", coord=0.5)

    def test_no_coords_returns_none(self, field_3d):
        _, _, _, F = field_3d
        C1, C2, s = extract_slice2d(F, axis="z", index=0)
        assert C1 is None
        assert C2 is None
        assert s.shape == (41, 51)

    def test_slice_plottable(self, field_3d):
        """Extracted slice + coordinate grids should be directly plottable."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from plotting import plot_pcolormesh

        x, y, z, F = field_3d
        C1, C2, s = extract_slice2d(F, axis="z", coord=1.0, x=x, y=y, z=z)
        fig, ax = plt.subplots()
        plot_pcolormesh(ax, C1, C2, s, cbar_label="test")
        plt.close(fig)
