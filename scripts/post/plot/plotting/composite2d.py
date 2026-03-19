"""Combined scalar + vector field plots for 2D CFD data.

High-level helpers that layer a scalar background with a vector
overlay in a single call.
"""

from __future__ import annotations

from .field2d import plot_contour, plot_contourf, plot_pcolormesh
from .vector2d import plot_quiver


def plot_contour_quiver(
    ax,
    x,
    y,
    z,
    u,
    v,
    *,
    scalar_kind="contourf",
    levels=20,
    cmap="viridis",
    cbar_label=None,
    quiver_stride=4,
    quiver_color="k",
    quiver_scale=None,
    aspect="equal",
    **kwargs,
):
    """Draw a scalar field background with a quiver overlay.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    x, y : array-like
        1D vectors or 2D meshgrid arrays.
    z : array-like
        2D scalar field.
    u, v : array-like
        2D vector components on the same grid.
    scalar_kind : str
        ``"contourf"``, ``"contour"``, or ``"pcolormesh"``.
    levels : int or array-like
        Contour levels (ignored for ``"pcolormesh"``).
    cmap : str or Colormap
    cbar_label : str, optional
    quiver_stride : int or tuple of int
        Subsample step for arrows.
    quiver_color : str
    quiver_scale : float, optional
    aspect : str, float, or None
    **kwargs
        Forwarded to the scalar plotting function.

    Returns
    -------
    scalar_artist : contour set or QuadMesh
    q : Quiver
    cbar : Colorbar or None
    """
    scalar_funcs = {
        "contourf": plot_contourf,
        "contour": plot_contour,
        "pcolormesh": plot_pcolormesh,
    }
    if scalar_kind not in scalar_funcs:
        raise ValueError(
            f"scalar_kind={scalar_kind!r} not in {list(scalar_funcs)}"
        )

    plot_scalar = scalar_funcs[scalar_kind]

    scalar_kw = dict(
        cmap=cmap,
        cbar_label=cbar_label,
        colorbar=True,
        aspect=aspect,
        **kwargs,
    )
    if scalar_kind != "pcolormesh":
        scalar_kw["levels"] = levels

    artist, cbar = plot_scalar(ax, x, y, z, **scalar_kw)

    q, _ = plot_quiver(
        ax,
        x,
        y,
        u,
        v,
        stride=quiver_stride,
        color=quiver_color,
        scale=quiver_scale,
        aspect=None,
    )

    return artist, q, cbar
