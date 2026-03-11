from __future__ import annotations

from typing import Iterable, Sequence, Tuple

import numpy as np
import pandas as pd
import pyvista as pv


def slice_plane(
    dataset: pv.DataSet,
    origin: Sequence[float],
    normal: Sequence[float],
) -> pv.PolyData:
    """
    Slice a dataset with a plane.
    """
    return dataset.slice(origin=origin, normal=normal)


def sample_line(
    dataset: pv.DataSet,
    point_a: Sequence[float],
    point_b: Sequence[float],
    n_points: int,
) -> pd.DataFrame:
    """
    Sample a line between two points and return a DataFrame.
    """
    line = pv.Line(point_a, point_b, resolution=max(n_points - 1, 1))
    sampled = dataset.sample(line)
    pts = sampled.points
    data = {
        "x": pts[:, 0],
        "y": pts[:, 1],
        "z": pts[:, 2],
    }
    for name, arr in sampled.point_data.items():
        data[name] = arr
    return pd.DataFrame(data)

