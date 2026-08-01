"""Vector field plotting for 2D CFD data.

Provides quiver and streamplot helpers with built-in subsampling,
magnitude colouring, and consistent validation.
"""

from __future__ import annotations

import numpy as np

from ._grid import add_colorbar, ensure_1d_coords, normalize_vector_coords


def compute_speed(u, v):
    """Compute velocity magnitude from vector components.

    Parameters
    ----------
    u, v : array-like
        Velocity components (any compatible shape).

    Returns
    -------
    speed : ndarray
        ``sqrt(u**2 + v**2)``
    """
    return np.hypot(
        np.asarray(u, dtype=float),
        np.asarray(v, dtype=float),
    )


def subsample_vectors(x, y, u, v, *, stride=None, target=25):
    """Subsample a vector field for readable quiver plots.

    Parameters
    ----------
    x, y : array-like
        1D or 2D coordinate arrays.
    u, v : array-like
        2D vector components with shape ``(ny, nx)``.
    stride : int or tuple of int, optional
        Step size ``(sy, sx)`` or a single ``int`` applied to both axes.
        Overrides *target* when given.
    target : int
        Approximate number of arrows per axis direction when *stride*
        is ``None``.

    Returns
    -------
    xs, ys, us, vs : ndarray
        Subsampled 2D arrays.
    """
    X, Y, U, V = normalize_vector_coords(x, y, u, v)
    ny, nx = U.shape

    if stride is not None:
        if isinstance(stride, (tuple, list)):
            sy, sx = int(stride[0]), int(stride[1])
        else:
            sy = sx = int(stride)
    else:
        sy = max(1, ny // target)
        sx = max(1, nx // target)

    return X[::sy, ::sx], Y[::sy, ::sx], U[::sy, ::sx], V[::sy, ::sx]


def plot_quiver(
    ax,
    x,
    y,
    u,
    v,
    *,
    color=None,
    scale=None,
    pivot="mid",
    stride=None,
    magnitude_color=False,
    cmap="viridis",
    colorbar=False,
    cbar_label=None,
    aspect="equal",
    **kwargs,
):
    """Draw a quiver (arrow) plot of a 2D vector field.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    x, y : array-like
        1D vectors or 2D meshgrid arrays.
    u, v : array-like
        2D vector components.
    color : str or array-like, optional
        Arrow colour.  Ignored when *magnitude_color* is ``True``.
    scale : float, optional
        Quiver scaling factor (larger value = shorter arrows).
    pivot : str
        Arrow pivot point (``"mid"``, ``"tip"``, ``"tail"``).
    stride : int or tuple of int, optional
        Subsample step ``(sy, sx)`` for readability on dense grids.
    magnitude_color : bool
        Colour arrows by velocity magnitude.
    cmap : str or Colormap
        Colormap used when *magnitude_color* is ``True``.
    colorbar : bool
    cbar_label : str, optional
    aspect : str, float, or None
    **kwargs
        Forwarded to ``ax.quiver``.

    Returns
    -------
    q : Quiver
    cbar : Colorbar or None
    """
    X, Y, U, V = normalize_vector_coords(x, y, u, v)

    if stride is not None:
        X, Y, U, V = subsample_vectors(X, Y, U, V, stride=stride)

    kw = dict(pivot=pivot, **kwargs)
    if scale is not None:
        kw["scale"] = scale

    if magnitude_color:
        speed = compute_speed(U, V)
        kw["cmap"] = cmap
        q = ax.quiver(X, Y, U, V, speed, **kw)
    else:
        if color is not None:
            kw["color"] = color
        q = ax.quiver(X, Y, U, V, **kw)

    if aspect is not None:
        ax.set_aspect(aspect)

    cbar = None
    if colorbar:
        cbar = add_colorbar(q, ax, cbar_label)

    return q, cbar


def plot_streamplot(
    ax,
    x,
    y,
    u,
    v,
    *,
    density=1.2,
    color=None,
    linewidth=None,
    cmap="viridis",
    norm=None,
    colorbar=False,
    cbar_label=None,
    aspect="equal",
    **kwargs,
):
    """Draw streamlines of a 2D vector field.

    Best for showing flow topology, separations, and recirculation.
    Requires a structured grid with monotonic 1D coordinates.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    x, y : array-like
        1D monotonic coordinate vectors or 2D meshgrid arrays
        (the first row / column is extracted automatically).
    u, v : array-like
        2D vector components with shape ``(ny, nx)``.
    density : float or tuple of float
        Streamline density.
    color : str or array-like, optional
        Scalar colour or a 2D array for per-point colouring (e.g. speed).
    linewidth : float or array-like, optional
        Constant or 2D array for per-point width.
    cmap : str or Colormap
    norm : Normalize, optional
    colorbar : bool
    cbar_label : str, optional
    aspect : str, float, or None
    **kwargs
        Forwarded to ``ax.streamplot``.

    Returns
    -------
    sp : StreamplotSet
    cbar : Colorbar or None
    """
    u = np.asarray(u, dtype=float)
    v = np.asarray(v, dtype=float)
    x1d, y1d = ensure_1d_coords(x, y)

    expected = (len(y1d), len(x1d))
    if u.shape != expected:
        raise ValueError(
            f"u shape {u.shape} does not match grid {expected}"
        )
    if v.shape != expected:
        raise ValueError(
            f"v shape {v.shape} does not match grid {expected}"
        )

    kw = dict(density=density, **kwargs)
    if color is not None:
        kw["color"] = np.asarray(color) if not isinstance(color, str) else color
    if linewidth is not None:
        kw["linewidth"] = (
            np.asarray(linewidth)
            if not isinstance(linewidth, (int, float))
            else linewidth
        )
    if cmap is not None:
        kw["cmap"] = cmap
    if norm is not None:
        kw["norm"] = norm

    sp = ax.streamplot(x1d, y1d, u, v, **kw)

    if aspect is not None:
        ax.set_aspect(aspect)

    cbar = None
    if colorbar and hasattr(sp, "lines"):
        cbar = add_colorbar(sp.lines, ax, cbar_label)

    return sp, cbar
