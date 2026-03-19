"""Scalar field plotting for 2D CFD data.

Provides thin wrappers around Matplotlib's contour, contourf,
pcolormesh, and imshow with consistent validation, colorbar handling,
and CFD-friendly defaults (equal aspect ratio, ``origin="lower"``).
"""

from __future__ import annotations

import numpy as np

from ._grid import add_colorbar, normalize_coords


def plot_contour(
    ax,
    x,
    y,
    z,
    *,
    levels=15,
    colors=None,
    cmap=None,
    linewidths=1.0,
    colorbar=False,
    cbar_label=None,
    vmin=None,
    vmax=None,
    norm=None,
    aspect="equal",
    **kwargs,
):
    """Draw contour lines on a 2D scalar field.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Target axes.
    x, y : array-like
        1D coordinate vectors or 2D meshgrid arrays.
    z : array-like
        2D scalar field with shape ``(ny, nx)``.
    levels : int or array-like
        Number of contour levels or explicit level values.
    colors : str or sequence, optional
        Line colors (overrides *cmap*).
    cmap : str or Colormap, optional
        Colormap when *colors* is not set.
    linewidths : float or sequence
        Contour line widths.
    colorbar : bool
        Add a colorbar linked to the contour set.
    cbar_label : str, optional
        Colorbar label text.
    vmin, vmax : float, optional
        Clipping limits for the color mapping.
    norm : matplotlib.colors.Normalize, optional
        Explicit normalization instance.
    aspect : str, float, or None
        Axes aspect ratio (default ``"equal"``).
    **kwargs
        Forwarded to ``ax.contour``.

    Returns
    -------
    cs : QuadContourSet
    cbar : Colorbar or None
    """
    X, Y, Z = normalize_coords(x, y, z)

    kw = dict(levels=levels, linewidths=linewidths, **kwargs)
    if colors is not None:
        kw["colors"] = colors
    if cmap is not None:
        kw["cmap"] = cmap
    if vmin is not None:
        kw["vmin"] = vmin
    if vmax is not None:
        kw["vmax"] = vmax
    if norm is not None:
        kw["norm"] = norm

    cs = ax.contour(X, Y, Z, **kw)

    if aspect is not None:
        ax.set_aspect(aspect)

    cbar = None
    if colorbar:
        cbar = add_colorbar(cs, ax, cbar_label)

    return cs, cbar


def plot_contourf(
    ax,
    x,
    y,
    z,
    *,
    levels=20,
    cmap="viridis",
    colorbar=True,
    cbar_label=None,
    vmin=None,
    vmax=None,
    norm=None,
    extend="neither",
    aspect="equal",
    **kwargs,
):
    """Draw filled contours on a 2D scalar field.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    x, y : array-like
        1D vectors or 2D meshgrid arrays.
    z : array-like
        2D scalar field with shape ``(ny, nx)``.
    levels : int or array-like
        Number of levels or explicit level values.
    cmap : str or Colormap
    colorbar : bool
    cbar_label : str, optional
    vmin, vmax : float, optional
    norm : Normalize, optional
    extend : str
        Extend colorbar beyond data range (``"neither"``, ``"both"``,
        ``"min"``, ``"max"``).
    aspect : str, float, or None
    **kwargs
        Forwarded to ``ax.contourf``.

    Returns
    -------
    cf : QuadContourSet
    cbar : Colorbar or None
    """
    X, Y, Z = normalize_coords(x, y, z)

    kw = dict(levels=levels, cmap=cmap, extend=extend, **kwargs)
    if vmin is not None:
        kw["vmin"] = vmin
    if vmax is not None:
        kw["vmax"] = vmax
    if norm is not None:
        kw["norm"] = norm

    cf = ax.contourf(X, Y, Z, **kw)

    if aspect is not None:
        ax.set_aspect(aspect)

    cbar = None
    if colorbar:
        cbar = add_colorbar(cf, ax, cbar_label)

    return cf, cbar


def plot_pcolormesh(
    ax,
    x,
    y,
    z,
    *,
    cmap="viridis",
    shading="auto",
    colorbar=True,
    cbar_label=None,
    vmin=None,
    vmax=None,
    norm=None,
    rasterized=None,
    aspect="equal",
    **kwargs,
):
    """Draw a pseudocolor mesh on a 2D scalar field.

    Best default for large structured CFD fields.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    x, y : array-like
        1D vectors or 2D meshgrid arrays.
    z : array-like
        2D scalar field.
    cmap : str or Colormap
    shading : str
        ``"auto"``, ``"flat"``, ``"nearest"``, or ``"gouraud"``.
    colorbar : bool
    cbar_label : str, optional
    vmin, vmax : float, optional
    norm : Normalize, optional
    rasterized : bool, optional
        Rasterize the mesh for lighter vector output (SVG/PDF).
    aspect : str, float, or None
    **kwargs
        Forwarded to ``ax.pcolormesh``.

    Returns
    -------
    qm : QuadMesh
    cbar : Colorbar or None
    """
    X, Y, Z = normalize_coords(x, y, z)

    kw = dict(cmap=cmap, shading=shading, **kwargs)
    if vmin is not None:
        kw["vmin"] = vmin
    if vmax is not None:
        kw["vmax"] = vmax
    if norm is not None:
        kw["norm"] = norm
    if rasterized is not None:
        kw["rasterized"] = rasterized

    qm = ax.pcolormesh(X, Y, Z, **kw)

    if aspect is not None:
        ax.set_aspect(aspect)

    cbar = None
    if colorbar:
        cbar = add_colorbar(qm, ax, cbar_label)

    return qm, cbar


def plot_imshow(
    ax,
    z,
    *,
    extent=None,
    origin="lower",
    cmap="viridis",
    colorbar=True,
    cbar_label=None,
    vmin=None,
    vmax=None,
    norm=None,
    aspect="equal",
    interpolation="nearest",
    **kwargs,
):
    """Display a 2D scalar field as an image.

    Best for uniformly spaced Cartesian grids.  Always provide *extent*
    to map pixel indices to physical coordinates.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    z : array-like
        2D scalar field.
    extent : tuple, optional
        ``(xmin, xmax, ymin, ymax)`` in data coordinates.
    origin : str
        ``"lower"`` (default) for Cartesian CFD views.
    cmap : str or Colormap
    colorbar : bool
    cbar_label : str, optional
    vmin, vmax : float, optional
    norm : Normalize, optional
    aspect : str, float, or None
    interpolation : str
    **kwargs
        Forwarded to ``ax.imshow``.

    Returns
    -------
    im : AxesImage
    cbar : Colorbar or None
    """
    z = np.asarray(z, dtype=float)
    if z.ndim != 2:
        raise ValueError(f"z must be 2D, got shape {z.shape}")

    kw = dict(origin=origin, cmap=cmap, interpolation=interpolation, **kwargs)
    if extent is not None:
        kw["extent"] = extent
    if vmin is not None:
        kw["vmin"] = vmin
    if vmax is not None:
        kw["vmax"] = vmax
    if norm is not None:
        kw["norm"] = norm

    im = ax.imshow(z, **kw)

    if aspect is not None:
        ax.set_aspect(aspect)

    cbar = None
    if colorbar:
        cbar = add_colorbar(im, ax, cbar_label)

    return im, cbar
