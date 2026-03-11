from __future__ import annotations

from pathlib import Path
from typing import Sequence, Tuple

import pyvista as pv


def clip_box(dataset: pv.DataSet, bounds: Sequence[float]) -> pv.DataSet:
    """
    Clip a dataset to an axis-aligned box.

    bounds = (xmin, xmax, ymin, ymax, zmin, zmax)
    """
    return dataset.clip_box(bounds)


def clip_plane(
    dataset: pv.DataSet,
    origin: Sequence[float],
    normal: Sequence[float],
    invert: bool = False,
) -> pv.DataSet:
    """
    Clip a dataset with a plane.
    """
    return dataset.clip(origin=origin, normal=normal, invert=invert)


def crop_to_bounds(
    dataset: pv.DataSet,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    zmin: float,
    zmax: float,
) -> pv.DataSet:
    """
    Convenience wrapper to crop a dataset to given bounds.
    """
    return clip_box(dataset, (xmin, xmax, ymin, ymax, zmin, zmax))


def threshold_by_array(
    dataset: pv.DataSet,
    array_name: str,
    lower: float | None = None,
    upper: float | None = None,
) -> pv.DataSet:
    """
    Threshold cells based on a scalar array.
    """
    return dataset.threshold(scalars=array_name, lower=lower, upper=upper)


def extract_largest_region(dataset: pv.DataSet) -> pv.DataSet:
    """
    Keep only the largest connected region.
    """
    return dataset.extract_largest()


def save_subset(dataset: pv.DataSet, output_path: str | Path) -> None:
    """
    Save a subset dataset to disk.
    """
    dataset.save(str(output_path))

