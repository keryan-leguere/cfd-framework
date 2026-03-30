"""Data preparation utilities for 2D CFD plotting.

Handles reshaping flattened exports, pivoting DataFrames, extracting
2D slices from 3D arrays, and subsampling vector fields.
"""

from __future__ import annotations

import numpy as np


def reshape_structured2d(x, y, values, *, order="yx"):
    """Reshape flattened structured-grid data to 2D arrays.

    Detects grid dimensions from unique coordinate values, sorts by
    ``(y, x)`` (default) or ``(x, y)``, and reshapes into 2D arrays
    suitable for :func:`plot_pcolormesh` or :func:`plot_contourf`.

    Parameters
    ----------
    x, y : array-like
        Flattened 1D coordinate arrays of length *npts*.
    values : array-like or dict of array-like
        Flattened scalar field(s).  A single array or a ``dict`` mapping
        names to arrays.
    order : str
        Sort order: ``"yx"`` (default, y varies slowest) matches
        ``np.meshgrid(..., indexing="xy")``.

    Returns
    -------
    X, Y : ndarray
        2D coordinate arrays with shape ``(ny, nx)``.
    Z : ndarray or dict of ndarray
        Reshaped scalar field(s).

    Raises
    ------
    ValueError
        If the points do not form a complete structured grid.
    """
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    npts = len(x)

    x_unique = np.unique(x)
    y_unique = np.unique(y)
    nx = len(x_unique)
    ny = len(y_unique)

    if nx * ny != npts:
        raise ValueError(
            f"Cannot reshape: {nx} unique x * {ny} unique y = {nx * ny} "
            f"!= {npts} points.  Data may have duplicates or missing cells."
        )

    if order == "yx":
        sort_idx = np.lexsort((x, y))
    else:
        sort_idx = np.lexsort((y, x))

    X = x[sort_idx].reshape(ny, nx)
    Y = y[sort_idx].reshape(ny, nx)

    if isinstance(values, dict):
        Z = {}
        for name, v in values.items():
            v = np.asarray(v, dtype=float).ravel()
            if len(v) != npts:
                raise ValueError(
                    f"Field {name!r} has {len(v)} elements, expected {npts}"
                )
            Z[name] = v[sort_idx].reshape(ny, nx)
    else:
        values = np.asarray(values, dtype=float).ravel()
        if len(values) != npts:
            raise ValueError(
                f"values has {len(values)} elements, expected {npts}"
            )
        Z = values[sort_idx].reshape(ny, nx)

    return X, Y, Z


def dataframe_to_grid(df, *, x="x", y="y", values=None, sort=True):
    """Convert a pandas DataFrame to structured 2D grid arrays.

    Parameters
    ----------
    df : pandas.DataFrame
        Must contain columns named by *x* and *y*.
    x, y : str
        Column names for coordinates.
    values : str or list of str, optional
        Scalar column(s) to pivot.  If ``None``, all columns except
        *x* and *y* are included.
    sort : bool
        Sort coordinates before pivoting.

    Returns
    -------
    xg : ndarray
        1D sorted x coordinates.
    yg : ndarray
        1D sorted y coordinates.
    fields : ndarray or dict of ndarray
        2D array(s) with shape ``(ny, nx)``.  A single array when
        *values* is a string, otherwise a dict keyed by column name.

    Raises
    ------
    ValueError
        On duplicate ``(x, y)`` pairs or inconsistent field shapes.
    """
    if values is None:
        values = [c for c in df.columns if c not in (x, y)]
    single = isinstance(values, str)
    if single:
        values = [values]

    dupes = df.duplicated(subset=[x, y], keep=False)
    if dupes.any():
        raise ValueError(
            f"Found {int(dupes.sum())} duplicate (x, y) rows.  "
            "Clean the data or use pivot_table with an aggregation function."
        )

    fields = {}
    for col in values:
        grid = df.pivot(index=y, columns=x, values=col)
        if sort:
            grid = grid.sort_index(axis=0).sort_index(axis=1)
        fields[col] = grid.to_numpy()

    first = next(iter(fields.values()))
    for col, arr in fields.items():
        if arr.shape != first.shape:
            raise ValueError(
                f"Field {col!r} shape {arr.shape} != {first.shape}"
            )

    ref = df.pivot(index=y, columns=x, values=values[0])
    if sort:
        ref = ref.sort_index(axis=0).sort_index(axis=1)
    xg = ref.columns.to_numpy(dtype=float)
    yg = ref.index.to_numpy(dtype=float)

    if single:
        return xg, yg, fields[values[0]]
    return xg, yg, fields


def mask_field(z, condition, *, fill=None):
    """Mask a 2D field where *condition* is ``True``.

    Use this when you already have structured 2D arrays and want to
    hide certain regions (e.g. solid zones, cells where ``IND != 0``).

    Parameters
    ----------
    z : array-like
        2D scalar field with shape ``(ny, nx)``.
    condition : array-like of bool
        Boolean array with the same shape as *z*.  ``True`` marks
        positions to **exclude** (mask out / hide).
    fill : float, optional
        If given, return a plain ``ndarray`` with excluded positions
        replaced by *fill* (typically ``np.nan``).  If ``None``
        (default), return a ``numpy.ma.MaskedArray``.

    Returns
    -------
    z_out : MaskedArray or ndarray
        Masked (or NaN-filled) copy of *z*.
    """
    z = np.asarray(z, dtype=float)
    condition = np.asarray(condition, dtype=bool)
    if z.shape != condition.shape:
        raise ValueError(
            f"z shape {z.shape} != condition shape {condition.shape}"
        )
    if fill is not None:
        out = z.copy()
        out[condition] = fill
        return out
    return np.ma.masked_where(condition, z)


def dataframe_to_masked_grid(
    df,
    *,
    x="x",
    y="y",
    values=None,
    mask_column,
    mask_value,
    keep=True,
    fill=None,
    sort=True,
):
    """Pivot a DataFrame to structured 2D arrays with region masking.

    Builds the full structured grid from *all* rows (so the lattice
    topology is preserved), then masks scalar fields where the filter
    column does or does not equal *mask_value*.

    Parameters
    ----------
    df : pandas.DataFrame
        Must contain columns named by *x*, *y*, and *mask_column*.
    x, y : str
        Column names for coordinates.
    values : str or list of str, optional
        Scalar column(s) to pivot.  If ``None``, all columns except
        *x*, *y*, and *mask_column* are included.
    mask_column : str
        Column used for filtering (e.g. ``"IND"``).
    mask_value
        Value to compare against in *mask_column*.
    keep : bool
        If ``True`` (default), **keep** rows where
        ``mask_column == mask_value`` and mask the rest.
        If ``False``, **exclude** rows where
        ``mask_column == mask_value``.
    fill : float, optional
        If given, excluded positions are filled with *fill* (e.g.
        ``np.nan``) and plain ``ndarray`` objects are returned.  If
        ``None`` (default), ``numpy.ma.MaskedArray`` objects are
        returned.
    sort : bool
        Sort coordinates before pivoting.

    Returns
    -------
    xg : ndarray
        1D sorted x coordinates (full grid).
    yg : ndarray
        1D sorted y coordinates (full grid).
    fields : MaskedArray/ndarray or dict thereof
        2D masked (or NaN-filled) field(s) with shape ``(ny, nx)``.
    """
    if values is None:
        exclude = {x, y, mask_column}
        values = [c for c in df.columns if c not in exclude]
    single = isinstance(values, str)
    if single:
        values = [values]

    xg, yg, raw_fields = dataframe_to_grid(
        df, x=x, y=y, values=[mask_column, *values], sort=sort,
    )

    indicator = raw_fields[mask_column]
    if keep:
        condition = indicator != mask_value
    else:
        condition = indicator == mask_value

    masked = {}
    for col in values:
        masked[col] = mask_field(raw_fields[col], condition, fill=fill)

    if single:
        return xg, yg, masked[values[0]]
    return xg, yg, masked


def extract_slice2d(
    field,
    *,
    axis,
    index=None,
    coord=None,
    x=None,
    y=None,
    z=None,
):
    """Extract a 2D plane from a 3D scalar array.

    Assumes ``np.meshgrid(x, y, z, indexing="ij")`` ordering, i.e.
    ``field.shape == (nx, ny, nz)`` with axis 0 = x, axis 1 = y,
    axis 2 = z.

    Parameters
    ----------
    field : array-like
        3D array with shape ``(nx, ny, nz)``.
    axis : str
        Slicing axis: ``"x"`` (axis 0), ``"y"`` (axis 1), or ``"z"``
        (axis 2).
    index : int, optional
        Direct index along *axis*.  Mutually exclusive with *coord*.
    coord : float, optional
        Physical coordinate value; the nearest index is selected.
        Requires the corresponding 1D coordinate vector.
    x, y, z : array-like, optional
        1D coordinate vectors.  Required when *coord* is used, and used
        for building the returned 2D meshgrid arrays.

    Returns
    -------
    c1, c2 : ndarray or None
        2D coordinate arrays matching ``slice2d.shape``.  ``c1``
        corresponds to the first remaining axis, ``c2`` to the second.
        ``None`` when the coordinate vectors are not provided.
    slice2d : ndarray
        2D scalar field.
    """
    field = np.asarray(field, dtype=float)
    if field.ndim != 3:
        raise ValueError(f"field must be 3D, got shape {field.shape}")

    axis_map = {"x": 0, "y": 1, "z": 2}
    if axis not in axis_map:
        raise ValueError(f"axis must be 'x', 'y', or 'z', got {axis!r}")
    ax_idx = axis_map[axis]

    if index is not None and coord is not None:
        raise ValueError("Provide either index or coord, not both")

    if coord is not None:
        coord_arrays = {"x": x, "y": y, "z": z}
        c = coord_arrays.get(axis)
        if c is None:
            raise ValueError(
                f"Coordinate array for axis {axis!r} is required "
                "when using coord"
            )
        c = np.asarray(c, dtype=float).ravel()
        index = int(np.argmin(np.abs(c - coord)))

    if index is None:
        raise ValueError("Provide either index or coord")

    slice2d = np.take(field, index, axis=ax_idx)

    # Remaining axes after slicing (ij convention: x=0, y=1, z=2).
    # slice along x  -> slice2d shape (ny, nz), coords: (y, z)
    # slice along y  -> slice2d shape (nx, nz), coords: (x, z)
    # slice along z  -> slice2d shape (nx, ny), coords: (x, y)
    if axis == "x":
        c1_vec, c2_vec = y, z
    elif axis == "y":
        c1_vec, c2_vec = x, z
    else:
        c1_vec, c2_vec = x, y

    if c1_vec is not None and c2_vec is not None:
        c1 = np.asarray(c1_vec, dtype=float).ravel()
        c2 = np.asarray(c2_vec, dtype=float).ravel()
        C1, C2 = np.meshgrid(c1, c2, indexing="ij")
        return C1, C2, slice2d

    return None, None, slice2d
