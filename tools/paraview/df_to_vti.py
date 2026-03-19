#!/usr/bin/env python
"""
Convert a CSV/DataFrame (columns: x, y, z, u, v, ro, ind) to a VTI file
(vtkImageData — cartesian rectilinear grid) readable in ParaView.

Compatible with Python 2 (pvpython) and Python 3.

Usage
-----
  # From pvpython or standard python with vtk installed:
  pvpython df_to_vti.py input.csv output.vti

  # As a library:
  from df_to_vti import dataframe_to_vti
  dataframe_to_vti(df, "output.vti")

The script infers grid dimensions, origin and spacing from the unique
sorted coordinate values found in the DataFrame.  Points are reordered
into VTK's Fortran (x-fastest) memory layout automatically.
"""
from __future__ import print_function

import csv
import os
import sys

import vtk
from vtk.util.numpy_support import numpy_to_vtk

import numpy as np


# ------------------------------------------------------------------ #
#  Core conversion
# ------------------------------------------------------------------ #

def _unique_sorted(arr, tol=1e-10):
    """Return sorted unique values from *arr* with a merge tolerance."""
    s = np.sort(arr)
    mask = np.concatenate(([True], np.abs(np.diff(s)) > tol))
    return s[mask]


def dataframe_to_imagedata(x, y, z, scalars):
    """
    Build a ``vtkImageData`` from coordinate arrays and scalar fields.

    Parameters
    ----------
    x, y, z : array-like, shape (N,)
        Point coordinates.  Must lie on a regular cartesian grid.
    scalars : dict
        ``{name: array}`` of point-data arrays, each of length N.

    Returns
    -------
    vtkImageData
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    z = np.asarray(z, dtype=np.float64)

    xu = _unique_sorted(x)
    yu = _unique_sorted(y)
    zu = _unique_sorted(z)

    nx, ny, nz = len(xu), len(yu), len(zu)
    n_points = nx * ny * nz
    if n_points != len(x):
        raise ValueError(
            "Grid is not complete: %d unique coords give %d expected points, "
            "but DataFrame has %d rows." % (nx * ny * nz, n_points, len(x))
        )

    dx = xu[1] - xu[0] if nx > 1 else 1.0
    dy = yu[1] - yu[0] if ny > 1 else 1.0
    dz = zu[1] - zu[0] if nz > 1 else 1.0

    img = vtk.vtkImageData()
    img.SetDimensions(nx, ny, nz)
    img.SetOrigin(xu[0], yu[0], zu[0])
    img.SetSpacing(dx, dy, dz)

    # Build index mapping: row in the DF -> flat VTK index (x fastest).
    # VTK flat index = ix + nx * (iy + ny * iz)
    ix = np.searchsorted(xu, x)
    iy = np.searchsorted(yu, y)
    iz = np.searchsorted(zu, z)
    vtk_idx = ix + nx * (iy + ny * iz)

    for name, arr in scalars.items():
        arr = np.asarray(arr, dtype=np.float64)
        ordered = np.empty(n_points, dtype=np.float64)
        ordered[vtk_idx] = arr
        vtk_arr = numpy_to_vtk(ordered, deep=True)
        vtk_arr.SetName(name)
        img.GetPointData().AddArray(vtk_arr)

    if scalars:
        first_name = list(scalars.keys())[0]
        img.GetPointData().SetActiveScalars(first_name)

    return img


def write_vti(imagedata, path):
    """Write a ``vtkImageData`` to a ``.vti`` XML file."""
    writer = vtk.vtkXMLImageDataWriter()
    writer.SetFileName(str(path))
    writer.SetInputData(imagedata)
    writer.SetDataModeToAppended()
    writer.SetEncodeAppendedData(False)
    writer.Write()
    print("Written: %s  (%d points)" % (path, imagedata.GetNumberOfPoints()))


# ------------------------------------------------------------------ #
#  DataFrame helper
# ------------------------------------------------------------------ #

def dataframe_to_vti(df, output_path,
                     coord_cols=("x", "y", "z"),
                     field_cols=("u", "v", "ro", "ind")):
    """
    One-call conversion: DataFrame -> .vti file.

    Parameters
    ----------
    df : pandas.DataFrame  (or dict of arrays)
        Must contain at least the columns listed in *coord_cols*.
    output_path : str
        Destination ``.vti`` file path.
    coord_cols : tuple
        Column names for (x, y, z) coordinates.
    field_cols : tuple
        Column names for the scalar fields to embed.
    """
    cx, cy, cz = coord_cols
    x = np.asarray(df[cx])
    y = np.asarray(df[cy])
    z = np.asarray(df[cz])

    scalars = {}
    for col in field_cols:
        if col in df:
            scalars[col] = np.asarray(df[col])

    img = dataframe_to_imagedata(x, y, z, scalars)
    write_vti(img, output_path)
    return img


# ------------------------------------------------------------------ #
#  CSV reader (no pandas dependency for pvpython environments)
# ------------------------------------------------------------------ #

def read_csv_to_arrays(path):
    """
    Read a CSV with header into a dict of numpy arrays.
    Works without pandas (useful inside pvpython).
    """
    columns = {}
    with open(path, "r") as fh:
        reader = csv.reader(fh)
        header = [h.strip() for h in next(reader)]
        for h in header:
            columns[h] = []
        for row in reader:
            for h, val in zip(header, row):
                columns[h].append(float(val))
    for h in header:
        columns[h] = np.array(columns[h], dtype=np.float64)
    return columns


# ------------------------------------------------------------------ #
#  CLI
# ------------------------------------------------------------------ #

def main():
    if len(sys.argv) < 3:
        print("Usage: %s INPUT.csv OUTPUT.vti" % os.path.basename(sys.argv[0]))
        print("")
        print("CSV must have a header row with at least: x, y, z")
        print("Recognised scalar columns: u, v, ro, ind (extras are ignored).")
        sys.exit(1)

    csv_path = sys.argv[1]
    vti_path = sys.argv[2]

    data = read_csv_to_arrays(csv_path)

    required = {"x", "y", "z"}
    missing = required - set(data.keys())
    if missing:
        print("ERROR: CSV is missing required columns: %s" % ", ".join(sorted(missing)))
        sys.exit(1)

    field_cols = [c for c in ("u", "v", "ro", "ind") if c in data]
    dataframe_to_vti(data, vti_path, field_cols=tuple(field_cols))


if __name__ == "__main__":
    main()
