"""Tests for prep data-preparation utilities."""

import numpy as np
import pandas as pd
import pytest

from cfd_plot import (
    dataframe_to_grid,
    dataframe_to_masked_grid,
    extract_slice2d,
    mask_field,
    reshape_structured2d,
)

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
# mask_field
# ---------------------------------------------------------------------------

class TestMaskField:
    def test_returns_masked_array_by_default(self):
        z = np.arange(12, dtype=float).reshape(3, 4)
        condition = z > 8
        out = mask_field(z, condition)
        assert isinstance(out, np.ma.MaskedArray)
        assert out.mask.sum() == (z > 8).sum()
        np.testing.assert_array_equal(out.data[~out.mask], z[~condition])

    def test_fill_returns_plain_array(self):
        z = np.ones((3, 4))
        condition = np.zeros((3, 4), dtype=bool)
        condition[0, 0] = True
        out = mask_field(z, condition, fill=np.nan)
        assert not isinstance(out, np.ma.MaskedArray)
        assert np.isnan(out[0, 0])
        assert out[1, 1] == 1.0

    def test_shape_mismatch(self):
        with pytest.raises(ValueError, match="shape"):
            mask_field(np.ones((3, 4)), np.ones((2, 4), dtype=bool))

    def test_no_masked_positions(self):
        z = np.ones((2, 3))
        out = mask_field(z, np.zeros((2, 3), dtype=bool))
        assert isinstance(out, np.ma.MaskedArray)
        assert not out.mask.any()


# ---------------------------------------------------------------------------
# dataframe_to_masked_grid
# ---------------------------------------------------------------------------

class TestDataframeToMaskedGrid:
    def _make_df_with_ind(self):
        """5x3 grid with IND=0 for fluid, IND=1 for solid."""
        x = np.arange(5, dtype=float)
        y = np.arange(3, dtype=float)
        X, Y = np.meshgrid(x, y, indexing="xy")
        P = X + Y
        IND = np.zeros_like(P)
        IND[X > 3] = 1.0
        return pd.DataFrame({
            "x": X.ravel(), "y": Y.ravel(),
            "p": P.ravel(), "IND": IND.ravel(),
        }), X, Y, P, IND

    def test_keep_mask_default(self):
        df, X, Y, P, IND = self._make_df_with_ind()
        xg, yg, p = dataframe_to_masked_grid(
            df, values="p", mask_column="IND", mask_value=0,
        )
        assert isinstance(p, np.ma.MaskedArray)
        n_solid = (IND != 0).sum()
        assert p.mask.sum() == n_solid
        np.testing.assert_array_equal(p.data[~p.mask], P[IND == 0])

    def test_keep_false(self):
        df, _, _, P, IND = self._make_df_with_ind()
        xg, yg, p = dataframe_to_masked_grid(
            df, values="p", mask_column="IND", mask_value=1, keep=False,
        )
        assert isinstance(p, np.ma.MaskedArray)
        n_solid = (IND == 1).sum()
        assert p.mask.sum() == n_solid

    def test_fill_nan(self):
        df, _, _, _, IND = self._make_df_with_ind()
        xg, yg, p = dataframe_to_masked_grid(
            df, values="p", mask_column="IND", mask_value=0,
            fill=np.nan,
        )
        assert not isinstance(p, np.ma.MaskedArray)
        assert np.isnan(p[IND != 0]).all()
        assert not np.isnan(p[IND == 0]).any()

    def test_multiple_fields(self):
        df, _, _, _, _ = self._make_df_with_ind()
        df["u"] = df["x"] * 2
        xg, yg, flds = dataframe_to_masked_grid(
            df, values=["p", "u"], mask_column="IND", mask_value=0,
        )
        assert "p" in flds and "u" in flds
        assert isinstance(flds["p"], np.ma.MaskedArray)
        assert isinstance(flds["u"], np.ma.MaskedArray)
        assert flds["p"].mask.sum() == flds["u"].mask.sum()

    def test_auto_values_excludes_mask_column(self):
        df, _, _, _, _ = self._make_df_with_ind()
        xg, yg, flds = dataframe_to_masked_grid(
            df, mask_column="IND", mask_value=0,
        )
        assert "p" in flds
        assert "IND" not in flds

    def test_grid_topology_preserved(self):
        """Full grid dimensions are kept even when many cells are masked."""
        df, X, Y, _, _ = self._make_df_with_ind()
        xg, yg, p = dataframe_to_masked_grid(
            df, values="p", mask_column="IND", mask_value=0,
        )
        assert len(xg) == 5
        assert len(yg) == 3
        assert p.shape == (3, 5)


# ---------------------------------------------------------------------------
# Masked plotting integration
# ---------------------------------------------------------------------------

class TestMaskedPlotting:
    """Masked arrays should flow through the plotting pipeline."""

    def test_pcolormesh_with_masked_field(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        from cfd_plot import plot_pcolormesh

        x = np.linspace(0, 1, 11)
        y = np.linspace(0, 1, 8)
        X, Y = np.meshgrid(x, y, indexing="xy")
        Z = np.ma.masked_where(X > 0.7, np.sin(X) * np.cos(Y))

        fig, ax = plt.subplots()
        qm, cbar = plot_pcolormesh(ax, x, y, Z, cbar_label="masked")
        assert qm is not None
        plt.close(fig)

    def test_contourf_with_masked_field(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        from cfd_plot import plot_contourf

        x = np.linspace(-1, 1, 41)
        y = np.linspace(-1, 1, 31)
        X, Y = np.meshgrid(x, y, indexing="xy")
        Z = np.ma.masked_where(X**2 + Y**2 > 0.8, np.exp(-(X**2 + Y**2)))

        fig, ax = plt.subplots()
        cf, cbar = plot_contourf(ax, x, y, Z, cbar_label="masked")
        assert cf is not None
        plt.close(fig)


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

        from cfd_plot import plot_pcolormesh

        x, y, z, F = field_3d
        C1, C2, s = extract_slice2d(F, axis="z", coord=1.0, x=x, y=y, z=z)
        fig, ax = plt.subplots()
        plot_pcolormesh(ax, C1, C2, s, cbar_label="test")
        plt.close(fig)
