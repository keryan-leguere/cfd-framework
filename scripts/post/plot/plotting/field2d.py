"""Scalar field plotting for 2D CFD data.

Provides thin wrappers around Matplotlib's contour, contourf,
pcolormesh, and imshow with consistent validation, colorbar handling,
and CFD-friendly defaults (equal aspect ratio, ``origin="lower"``).
"""

from __future__ import annotations

import numpy as np

from ._grid import add_colorbar, ensure_1d_coords, normalize_coords, prepare_cmap


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
    bad_color=None,
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
    bad_color : str or color, optional
        Colour used for masked / ``NaN`` cells (e.g. ``"black"``).
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
        kw["cmap"] = prepare_cmap(cmap, bad_color)
    elif bad_color is not None:
        kw["cmap"] = prepare_cmap("viridis", bad_color)
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
    bad_color=None,
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
    bad_color : str or color, optional
        Colour used for masked / ``NaN`` cells (e.g. ``"black"``).
    aspect : str, float, or None
    **kwargs
        Forwarded to ``ax.contourf``.

    Returns
    -------
    cf : QuadContourSet
    cbar : Colorbar or None
    """
    X, Y, Z = normalize_coords(x, y, z)

    kw = dict(levels=levels, cmap=prepare_cmap(cmap, bad_color), extend=extend, **kwargs)
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
    bad_color=None,
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
    bad_color : str or color, optional
        Colour used for masked / ``NaN`` cells (e.g. ``"black"``).
    aspect : str, float, or None
    **kwargs
        Forwarded to ``ax.pcolormesh``.

    Returns
    -------
    qm : QuadMesh
    cbar : Colorbar or None
    """
    X, Y, Z = normalize_coords(x, y, z)

    kw = dict(cmap=prepare_cmap(cmap, bad_color), shading=shading, **kwargs)
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
    bad_color=None,
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
    bad_color : str or color, optional
        Colour used for masked / ``NaN`` cells (e.g. ``"black"``).
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

    kw = dict(origin=origin, cmap=prepare_cmap(cmap, bad_color), interpolation=interpolation, **kwargs)
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


# ---------------------------------------------------------------------------
# Interpolation helpers (SciPy required)
# ---------------------------------------------------------------------------


def interpolate_field2d(x, y, z, *, factor=2, method="cubic"):
    """Interpolate a 2D structured scalar field onto a denser grid.

    Useful when nodal CFD data is plotted with ``pcolormesh`` and the
    per-cell colouring appears blocky.  Interpolation onto a finer grid
    produces a smooth visual result.

    Parameters
    ----------
    x, y : array-like
        1D coordinate vectors or 2D meshgrid arrays.  Must be
        monotonic along their respective axis.
    z : array-like
        2D scalar field with shape ``(ny, nx)``.
    factor : int
        Refinement factor per axis (``2`` doubles the resolution).
    method : str
        ``"linear"`` or ``"cubic"`` (default).  ``"cubic"`` uses a
        ``RectBivariateSpline`` of order 3; ``"linear"`` uses order 1.

    Returns
    -------
    xi : ndarray
        1D refined x coordinates.
    yi : ndarray
        1D refined y coordinates.
    zi : ndarray
        Interpolated 2D field with shape
        ``(ny * factor, nx * factor)``.

    Raises
    ------
    ImportError
        If SciPy is not installed.
    ValueError
        If coordinates are not monotonic or *method* is unknown.
    """
    from scipy.interpolate import RectBivariateSpline

    z = np.asarray(z, dtype=float)
    if z.ndim != 2:
        raise ValueError(f"z must be 2D, got shape {z.shape}")

    x1d, y1d = ensure_1d_coords(x, y)
    ny, nx = z.shape

    if len(x1d) != nx:
        raise ValueError(
            f"x has {len(x1d)} elements but z has {nx} columns"
        )
    if len(y1d) != ny:
        raise ValueError(
            f"y has {len(y1d)} elements but z has {ny} rows"
        )

    _order_map = {"linear": 1, "cubic": 3}
    if method not in _order_map:
        raise ValueError(
            f"method={method!r} not supported; use 'linear' or 'cubic'"
        )
    kx = ky = _order_map[method]

    spline = RectBivariateSpline(y1d, x1d, z, kx=kx, ky=ky)

    xi = np.linspace(x1d[0], x1d[-1], nx * factor)
    yi = np.linspace(y1d[0], y1d[-1], ny * factor)
    zi = spline(yi, xi)

    return xi, yi, zi


def plot_pcolormesh_interp(
    ax,
    x,
    y,
    z,
    *,
    factor=2,
    method="cubic",
    cmap="viridis",
    shading="auto",
    colorbar=True,
    cbar_label=None,
    vmin=None,
    vmax=None,
    norm=None,
    rasterized=None,
    bad_color=None,
    aspect="equal",
    **kwargs,
):
    """Interpolate a nodal field then draw it with ``pcolormesh``.

    Combines :func:`interpolate_field2d` and :func:`plot_pcolormesh`
    into a single call.  Returns the interpolated grid for reuse.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    x, y : array-like
        1D coordinate vectors or 2D meshgrid arrays.
    z : array-like
        2D nodal scalar field.
    factor : int
        Interpolation refinement factor per axis.
    method : str
        ``"linear"`` or ``"cubic"``.
    cmap, shading, colorbar, cbar_label, vmin, vmax, norm, rasterized,
    bad_color, aspect, **kwargs
        Forwarded to :func:`plot_pcolormesh`.

    Returns
    -------
    qm : QuadMesh
    cbar : Colorbar or None
    interp : tuple
        ``(xi, yi, zi)`` — the refined coordinates and interpolated
        field, usable for further analysis.
    """
    xi, yi, zi = interpolate_field2d(x, y, z, factor=factor, method=method)

    qm, cbar = plot_pcolormesh(
        ax,
        xi,
        yi,
        zi,
        cmap=cmap,
        shading=shading,
        colorbar=colorbar,
        cbar_label=cbar_label,
        vmin=vmin,
        vmax=vmax,
        norm=norm,
        rasterized=rasterized,
        bad_color=bad_color,
        aspect=aspect,
        **kwargs,
    )

    return qm, cbar, (xi, yi, zi)
