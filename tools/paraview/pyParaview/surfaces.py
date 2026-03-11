from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

import pandas as pd
import pyvista as pv

from .io.vtk import get_block, read_dataset, to_surface


def _surface_dataframe(mesh: pv.DataSet, fields: Sequence[str]) -> pd.DataFrame:
    """
    Build a DataFrame with x, y, z and selected fields.
    """
    pts = mesh.points
    data: Dict[str, object] = {
        "x": pts[:, 0],
        "y": pts[:, 1],
        "z": pts[:, 2],
    }

    for name in fields:
        if name in mesh.point_data:
            data[name] = mesh.point_data[name]
        elif name in mesh.cell_data:
            data[name] = mesh.cell_data[name]

    return pd.DataFrame(data)


def extract_surface_table(
    path: str | Path,
    surface_name: str,
    fields: Sequence[str],
) -> pd.DataFrame:
    """
    Extract a single surface as a DataFrame.
    """
    ds = read_dataset(path)
    block = get_block(ds, surface_name)
    if block is None:
        raise KeyError(f"Surface '{surface_name}' not found in {path}")
    surf = to_surface(block)
    return _surface_dataframe(surf, fields)


def extract_surfaces(
    path: str | Path,
    surface_names: Sequence[str],
    fields: Sequence[str],
) -> Dict[str, pd.DataFrame]:
    """
    Extract multiple named surfaces as DataFrames.
    """
    ds = read_dataset(path)
    tables: Dict[str, pd.DataFrame] = {}
    for name in surface_names:
        block = get_block(ds, name)
        if block is None:
            continue
        surf = to_surface(block)
        tables[name] = _surface_dataframe(surf, fields)
    return tables


def surface_area(mesh: pv.DataSet) -> float:
    """
    Compute the surface area of a mesh.
    """
    return float(to_surface(mesh).area)


def surface_centroid(mesh: pv.DataSet) -> tuple[float, float, float]:
    """
    Compute the centroid of a surface mesh.
    """
    surf = to_surface(mesh)
    return tuple(map(float, surf.center))

