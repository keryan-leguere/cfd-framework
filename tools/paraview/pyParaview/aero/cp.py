from __future__ import annotations

from typing import Hashable

import pandas as pd


def compute_qinf(rho_ref: float, u_ref: float) -> float:
    """
    Dynamic pressure q = 0.5 * rho * U^2.
    """
    return 0.5 * rho_ref * u_ref * u_ref


def compute_cp(pressure: float, p_ref: float, q_ref: float) -> float:
    """
    Classic incompressible Cp definition.
    """
    return (pressure - p_ref) / q_ref


def add_cp_column(
    table: pd.DataFrame,
    pressure_col: Hashable = "p",
    p_ref: float | None = None,
    q_ref: float | None = None,
    out_col: str = "Cp",
) -> pd.DataFrame:
    """
    Add a Cp column to a surface table.

    If p_ref or q_ref are None, they must be present in the table as
    scalar columns named 'p_ref' and 'q_ref' or similar.
    """
    df = table.copy()

    if p_ref is None:
        if "p_ref" not in df:
            raise ValueError("p_ref not provided and 'p_ref' column not found")
        p_ref = float(df["p_ref"].iloc[0])

    if q_ref is None:
        if "q_ref" not in df:
            raise ValueError("q_ref not provided and 'q_ref' column not found")
        q_ref = float(df["q_ref"].iloc[0])

    df[out_col] = (df[pressure_col] - p_ref) / q_ref
    return df

