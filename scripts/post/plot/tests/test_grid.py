"""Tests for _grid internal helpers."""

import numpy as np
import pytest

from plotting._grid import (
    add_colorbar,
    ensure_1d_coords,
    normalize_coords,
    normalize_vector_coords,
)


# ---------------------------------------------------------------------------
# normalize_coords
# ---------------------------------------------------------------------------

class TestNormalizeCoords:
    """Shape validation and 1D / 2D coordinate normalisation."""

    def test_1d_coords(self):
        x = np.arange(5, dtype=float)
        y = np.arange(3, dtype=float)
        z = np.ones((3, 5))
        X, Y, Z = normalize_coords(x, y, z)
        assert X.shape == (3, 5)
        assert Y.shape == (3, 5)
        assert np.array_equal(Z, z)

    def test_2d_coords(self):
        x = np.arange(5, dtype=float)
        y = np.arange(3, dtype=float)
        X0, Y0 = np.meshgrid(x, y, indexing="xy")
        z = np.ones((3, 5))
        X, Y, Z = normalize_coords(X0, Y0, z)
        assert np.array_equal(X, X0)
        assert np.array_equal(Y, Y0)

    def test_z_not_2d(self):
        with pytest.raises(ValueError, match="z must be 2D"):
            normalize_coords([1, 2], [1, 2], np.arange(6))

    def test_x_shape_mismatch(self):
        with pytest.raises(ValueError, match="x has .* elements"):
            normalize_coords(np.arange(4), np.arange(3), np.ones((3, 5)))

    def test_y_shape_mismatch(self):
        with pytest.raises(ValueError, match="y has .* elements"):
            normalize_coords(np.arange(5), np.arange(2), np.ones((3, 5)))

    def test_2d_x_shape_mismatch(self):
        z = np.ones((3, 5))
        with pytest.raises(ValueError, match="x shape"):
            normalize_coords(np.ones((4, 5)), np.ones((3, 5)), z)

    def test_2d_y_shape_mismatch(self):
        z = np.ones((3, 5))
        with pytest.raises(ValueError, match="y shape"):
            normalize_coords(np.ones((3, 5)), np.ones((4, 5)), z)

    def test_mixed_dims(self):
        with pytest.raises(ValueError, match="both be 1D or both 2D"):
            normalize_coords(np.arange(5), np.ones((3, 5)), np.ones((3, 5)))


# ---------------------------------------------------------------------------
# normalize_vector_coords
# ---------------------------------------------------------------------------

class TestNormalizeVectorCoords:
    def test_valid(self):
        x = np.arange(4, dtype=float)
        y = np.arange(3, dtype=float)
        u = np.ones((3, 4))
        v = np.ones((3, 4))
        X, Y, U, V = normalize_vector_coords(x, y, u, v)
        assert X.shape == (3, 4)
        assert np.array_equal(V, v)

    def test_u_not_2d(self):
        with pytest.raises(ValueError, match="u must be 2D"):
            normalize_vector_coords([1, 2], [1], np.arange(4), np.ones((2, 2)))

    def test_v_not_2d(self):
        with pytest.raises(ValueError, match="v must be 2D"):
            normalize_vector_coords([1, 2], [1], np.ones((1, 2)), np.arange(4))

    def test_uv_shape_mismatch(self):
        with pytest.raises(ValueError, match="u shape .* != v shape"):
            normalize_vector_coords(
                [1, 2, 3], [1, 2],
                np.ones((2, 3)), np.ones((3, 2)),
            )


# ---------------------------------------------------------------------------
# ensure_1d_coords
# ---------------------------------------------------------------------------

class TestEnsure1dCoords:
    def test_from_1d(self):
        x, y = ensure_1d_coords(np.arange(5), np.arange(3))
        assert x.shape == (5,)
        assert y.shape == (3,)

    def test_from_2d(self):
        X, Y = np.meshgrid(np.arange(5), np.arange(3), indexing="xy")
        x, y = ensure_1d_coords(X, Y)
        assert x.shape == (5,)
        assert y.shape == (3,)


# ---------------------------------------------------------------------------
# add_colorbar
# ---------------------------------------------------------------------------

class TestMaskedArrayPreservation:
    """normalize_coords must not strip np.ma.MaskedArray masks."""

    def test_masked_z_preserved_1d(self):
        x = np.arange(5, dtype=float)
        y = np.arange(3, dtype=float)
        z = np.ma.masked_where(
            np.ones((3, 5)) > 0.5,
            np.ones((3, 5)),
        )
        _, _, Z = normalize_coords(x, y, z)
        assert isinstance(Z, np.ma.MaskedArray)
        assert Z.mask.any()

    def test_masked_z_preserved_2d(self):
        X, Y = np.meshgrid(np.arange(5.0), np.arange(3.0), indexing="xy")
        z = np.ma.array(np.ones((3, 5)), mask=X > 2)
        _, _, Z = normalize_coords(X, Y, z)
        assert isinstance(Z, np.ma.MaskedArray)
        assert Z.mask.sum() == (X > 2).sum()

    def test_plain_z_stays_plain(self):
        x = np.arange(5, dtype=float)
        y = np.arange(3, dtype=float)
        z = np.ones((3, 5))
        _, _, Z = normalize_coords(x, y, z)
        assert not isinstance(Z, np.ma.MaskedArray)


class TestAddColorbar:
    def test_creates_colorbar(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        im = ax.imshow(np.ones((3, 3)))
        cbar = add_colorbar(im, ax, label="test")
        assert cbar is not None
        plt.close(fig)
