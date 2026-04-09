"""Input validation helpers."""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd


class ValidationError(Exception):
    """Raised when input data fails validation checks."""


def validate_dataframe(
    df: pd.DataFrame,
    required_cols: Sequence[str] | None = None,
    *,
    min_rows: int = 10,
) -> list[str]:
    """Return a list of issues found in *df* (empty list means valid).

    Parameters
    ----------
    df : pd.DataFrame
        The input data.
    required_cols : sequence of str, optional
        Columns that must exist.
    min_rows : int
        Minimum acceptable row count.
    """
    issues: list[str] = []

    if df.empty:
        issues.append("DataFrame is empty")
        return issues

    if len(df) < min_rows:
        issues.append(f"Too few rows ({len(df)}) – need at least {min_rows}")

    if required_cols:
        missing = set(required_cols) - set(df.columns)
        if missing:
            issues.append(f"Missing columns: {sorted(missing)}")

    return issues


def validate_numeric_column(df: pd.DataFrame, col: str) -> list[str]:
    """Validate that *col* is numeric and report NaN / Inf counts."""
    issues: list[str] = []
    if col not in df.columns:
        issues.append(f"Column '{col}' not found")
        return issues

    s = df[col]
    if not np.issubdtype(s.dtype, np.number):
        issues.append(f"Column '{col}' is not numeric (dtype={s.dtype})")
        return issues

    n_nan = int(s.isna().sum())
    n_inf = int(np.isinf(s.to_numpy(dtype=float, na_value=0.0)).sum())
    if n_nan:
        issues.append(f"Column '{col}' has {n_nan} NaN values")
    if n_inf:
        issues.append(f"Column '{col}' has {n_inf} Inf values")

    return issues


def validate_1d_array(arr: np.ndarray, *, name: str = "array", min_length: int = 10) -> list[str]:
    """Basic checks on a 1-D numeric array."""
    issues: list[str] = []
    if arr.ndim != 1:
        issues.append(f"{name} must be 1-D (got ndim={arr.ndim})")
        return issues
    if arr.size < min_length:
        issues.append(f"{name} too short ({arr.size}) – need at least {min_length}")
    n_nan = int(np.isnan(arr).sum())
    if n_nan:
        issues.append(f"{name} contains {n_nan} NaN values")
    return issues


def clean_signal(arr: np.ndarray) -> np.ndarray:
    """Return *arr* with NaN/Inf replaced by linear interpolation."""
    out = arr.copy().astype(float)
    bad = ~np.isfinite(out)
    if not bad.any():
        return out
    good = np.where(~bad)[0]
    if good.size < 2:
        return np.zeros_like(out)
    out[bad] = np.interp(np.where(bad)[0], good, out[good])
    return out
