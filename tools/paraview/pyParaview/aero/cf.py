from __future__ import annotations

from typing import Hashable

import numpy as np
import pandas as pd


def compute_cf(tau_w: float, rho_ref: float, u_ref: float) -> float:
    """
    Skin-friction coefficient based on wall shear stress.
    """
    q_ref = 0.5 * rho_ref * u_ref * u_ref
    return tau_w / q_ref


def wall_shear_magnitude(
    table: pd.DataFrame,
    shear_col: Hashable = "wallShearStress",
    out_col: str = "tau_w",
) -> pd.DataFrame:
    """
    Compute wall shear magnitude from a vector field stored in multiple columns
    or as an array-like column.
    """
    df = table.copy()

    if isinstance(shear_col, (list, tuple)):
        arr = np.sqrt(sum(np.asarray(df[c]) ** 2 for c in shear_col))
    else:
        data = df[shear_col]
        arr = np.linalg.norm(np.asarray(list(data)), axis=1)

    df[out_col] = arr
    return df


def add_cf_column(
    table: pd.DataFrame,
    tau_col: Hashable = "tau_w",
    rho_ref: float | None = None,
    u_ref: float | None = None,
    out_col: str = "Cf",
) -> pd.DataFrame:
    """
    Add a Cf column to a surface table.
    """
    df = table.copy()

    if rho_ref is None:
        if "rho_ref" not in df:
            raise ValueError("rho_ref not provided and 'rho_ref' column not found")
        rho_ref = float(df["rho_ref"].iloc[0])

    if u_ref is None:
        if "u_ref" not in df:
            raise ValueError("u_ref not provided and 'u_ref' column not found")
        u_ref = float(df["u_ref"].iloc[0])

    q_ref = 0.5 * rho_ref * u_ref * u_ref
    df[out_col] = df[tau_col] / q_ref
    return df

