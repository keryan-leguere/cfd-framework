"""Internal grid validation and normalization helpers for 2D plotting."""

from __future__ import annotations

import numpy as np


def _float_array(a):
    """Convert *a* to a float array, preserving ``np.ma.MaskedArray``."""
    if isinstance(a, np.ma.MaskedArray):
        return a.astype(float, copy=False)
    return np.asarray(a, dtype=float)


def normalize_coords(x, y, z):
    """Normalize coordinate inputs to validated 2D arrays.

    Accepts either 1D coordinate vectors ``x(nx,)``, ``y(ny,)`` with
    ``z(ny, nx)`` **or** 2D meshgrid arrays all sharing the same shape.

    Masked arrays (``numpy.ma.MaskedArray``) are preserved on *z* so that
    Matplotlib can skip masked regions automatically.

    Returns ``(X, Y, Z)`` where *X* and *Y* are 2D.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    z = _float_array(z)

    if z.ndim != 2:
        raise ValueError(f"z must be 2D, got shape {z.shape}")

    ny, nx = z.shape

    if x.ndim == 1 and y.ndim == 1:
        if x.shape[0] != nx:
            raise ValueError(
                f"x has {x.shape[0]} elements but z has {nx} columns"
            )
        if y.shape[0] != ny:
            raise ValueError(
                f"y has {y.shape[0]} elements but z has {ny} rows"
            )
        X, Y = np.meshgrid(x, y, indexing="xy")
    elif x.ndim == 2 and y.ndim == 2:
        if x.shape != z.shape:
            raise ValueError(
                f"x shape {x.shape} does not match z shape {z.shape}"
            )
        if y.shape != z.shape:
            raise ValueError(
                f"y shape {y.shape} does not match z shape {z.shape}"
            )
        X, Y = x, y
    else:
        raise ValueError(
            f"x and y must both be 1D or both 2D, "
            f"got ndim=({x.ndim}, {y.ndim})"
        )

    return X, Y, z


def normalize_vector_coords(x, y, u, v):
    """Normalize coordinates for a vector field.

    Validates that *u* and *v* have compatible 2D shapes, then delegates
    to :func:`normalize_coords` for the spatial grid.
    """
    u = np.asarray(u, dtype=float)
    v = np.asarray(v, dtype=float)

    if u.ndim != 2:
        raise ValueError(f"u must be 2D, got shape {u.shape}")
    if v.ndim != 2:
        raise ValueError(f"v must be 2D, got shape {v.shape}")
    if u.shape != v.shape:
        raise ValueError(f"u shape {u.shape} != v shape {v.shape}")

    X, Y, U = normalize_coords(x, y, u)
    return X, Y, U, v


def ensure_1d_coords(x, y):
    """Extract 1D monotonic coordinates from 1D or 2D arrays.

    ``ax.streamplot`` requires strictly 1D *x* and *y*.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    if x.ndim == 2:
        x = x[0, :]
    if y.ndim == 2:
        y = y[:, 0]

    if x.ndim != 1 or y.ndim != 1:
        raise ValueError("Could not extract 1D coordinates")

    return x, y


def prepare_cmap(cmap, bad_color):
    """Return a colormap copy with *bad_color* set for masked/NaN cells.

    If *bad_color* is ``None``, return *cmap* unchanged (may be a string).
    """
    if bad_color is None:
        return cmap
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    if isinstance(cmap, str):
        cmap = plt.get_cmap(cmap).copy()
    else:
        cmap = cmap.copy()
    cmap.set_bad(color=mcolors.to_rgba(bad_color))
    return cmap


def add_colorbar(mappable, ax, label=None):
    """Add a colorbar to *ax* with an optional label."""
    import matplotlib.pyplot as plt

    cbar = plt.colorbar(mappable, ax=ax)
    if label:
        cbar.set_label(label)
    return cbar
