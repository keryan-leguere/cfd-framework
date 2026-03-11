from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Sequence

import numpy as np
import pandas as pd
import pyvista as pv

from ..io.vtk import get_block, read_dataset
from .sections import sample_line


def get_boundary_layer_block(
    dataset: pv.DataSet,
    name: str = "boundary_layer",
) -> pv.DataSet:
    """
    Return the dedicated boundary-layer block from a multiblock dataset.
    """
    block = get_block(dataset, name)
    if block is None:
        raise KeyError(f"Boundary-layer block '{name}' not found")
    return block


def extract_boundary_layer(
    path: str | Path,
    fields: Sequence[str],
    block_name: str = "boundary_layer",
) -> pd.DataFrame:
    """
    Extract all boundary-layer cells as a flat table.
    """
    ds = read_dataset(path)
    bl = get_boundary_layer_block(ds, block_name)
    pts = bl.points
    data: Dict[str, object] = {
        "x": pts[:, 0],
        "y": pts[:, 1],
        "z": pts[:, 2],
        "block": block_name,
    }
    for name in fields:
        if name in bl.point_data:
            data[name] = bl.point_data[name]
        elif name in bl.cell_data:
            data[name] = bl.cell_data[name]
    return pd.DataFrame(data)


def clip_boundary_layer(
    dataset: pv.DataSet,
    origin: Sequence[float],
    normal: Sequence[float],
    invert: bool = False,
) -> pv.DataSet:
    """
    Clip the boundary-layer region with a plane.
    """
    return dataset.clip(origin=origin, normal=normal, invert=invert)


def boundary_layer_thickness(
    profile: pd.DataFrame,
    velocity_col: str,
    y_col: str,
    threshold: float = 0.99,
) -> float:
    """
    Estimate boundary-layer thickness from a 1D velocity profile.
    """
    u = np.asarray(profile[velocity_col])
    y = np.asarray(profile[y_col])

    if u.size == 0:
        raise ValueError("Empty profile")

    u_inf = u[-1]
    target = threshold * u_inf
    idx = np.where(u >= target)[0]
    if idx.size == 0:
        return float(y[-1])
    return float(y[idx[0]])


def displacement_thickness(
    profile: pd.DataFrame,
    velocity_col: str,
    y_col: str,
) -> float:
    """
    Displacement thickness by trapezoidal integration.
    """
    u = np.asarray(profile[velocity_col])
    y = np.asarray(profile[y_col])
    if u.size < 2:
        return 0.0
    u_inf = u[-1]
    integrand = 1.0 - u / u_inf
    return float(np.trapz(integrand, y))


def momentum_thickness(
    profile: pd.DataFrame,
    velocity_col: str,
    y_col: str,
) -> float:
    """
    Momentum thickness by trapezoidal integration.
    """
    u = np.asarray(profile[velocity_col])
    y = np.asarray(profile[y_col])
    if u.size < 2:
        return 0.0
    u_inf = u[-1]
    integrand = (u / u_inf) * (1.0 - u / u_inf)
    return float(np.trapz(integrand, y))


def shape_factor(
    profile: pd.DataFrame,
    velocity_col: str,
    y_col: str,
) -> float:
    """
    Shape factor H = delta* / theta.
    """
    theta = momentum_thickness(profile, velocity_col, y_col)
    if theta == 0.0:
        return 0.0
    delta_star = displacement_thickness(profile, velocity_col, y_col)
    return float(delta_star / theta)

