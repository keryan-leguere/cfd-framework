"""Cross-family comparison utilities.

A *family* is a named group of rows in the DataFrame (e.g. different
turbulence models sharing the same mesh).  When the DataFrame has a
``family`` column, this module computes per-family statistics and
comparative tables.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

from cfd_stats.core.moments import MomentCalculator


def compare_families(
    df: pd.DataFrame,
    coeff_cols: Sequence[str],
    family_col: str = "family",
    iter_col: str = "iter",
) -> dict:
    """Produce per-family summary statistics for each coefficient.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain *family_col* plus the requested coefficient columns.
    coeff_cols : sequence of str
        Coefficient columns to compare.
    family_col : str
        Column that identifies the family.
    iter_col : str
        Iteration column (used for context, not grouped).

    Returns
    -------
    dict
        Keyed by family name; each value is a dict with per-coefficient
        ``mean``, ``std``, ``n_points``.
    """
    if family_col not in df.columns:
        raise ValueError(f"Column '{family_col}' not found in DataFrame")

    result: dict[str, dict] = {}
    for fam_name, grp in df.groupby(family_col, sort=True):
        fam_stats: dict[str, dict] = {"n_points": len(grp)}
        for col in coeff_cols:
            if col not in grp.columns:
                continue
            data = grp[col].dropna().to_numpy(dtype=float)
            if data.size == 0:
                continue
            mc = MomentCalculator(data)
            m = mc.compute_all_moments(max_order=2)
            fam_stats[col] = {
                "mean": m["mean"],
                "std": m["std"],
                "min": float(data.min()),
                "max": float(data.max()),
            }
        result[str(fam_name)] = fam_stats

    return result


def families_to_dataframe(comparison: dict) -> pd.DataFrame:
    """Flatten the output of :func:`compare_families` into a tidy DataFrame."""
    rows: list[dict] = []
    for fam, stats in comparison.items():
        n_pts = stats.get("n_points", 0)
        for key, val in stats.items():
            if key == "n_points":
                continue
            rows.append({"family": fam, "coefficient": key, "n_points": n_pts, **val})
    return pd.DataFrame(rows)
