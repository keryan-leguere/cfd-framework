"""Pandas DataFrame helpers for CFD data loading and manipulation."""

from __future__ import annotations

import pickle
from pathlib import Path

import pandas as pd


def load_dataframe(filepath: str | Path) -> pd.DataFrame:
    """Load a DataFrame from a pickle file.

    Parameters
    ----------
    filepath : str or Path
        Path to a ``.pickle`` file containing a serialised DataFrame.

    Returns
    -------
    pd.DataFrame

    Raises
    ------
    FileNotFoundError
        If *filepath* does not exist.
    ValueError
        If the file does not contain a DataFrame.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with open(path, "rb") as fh:
        obj = pickle.load(fh)  # noqa: S301

    if isinstance(obj, pd.DataFrame):
        return obj
    raise ValueError(f"Expected a DataFrame in {path}, got {type(obj).__name__}")


_META_COLUMNS = frozenset({"family", "Family", "FAMILY", "boundary", "surface", "zone", "patch"})


def detect_coeff_columns(df: pd.DataFrame, iter_col: str = "iter") -> list[str]:
    """Return numeric columns that are not the iteration/time or metadata columns."""
    numeric = df.select_dtypes(include="number").columns.tolist()
    skip = {iter_col} | _META_COLUMNS
    return [c for c in numeric if c not in skip]


def detect_family_column(df: pd.DataFrame) -> str | None:
    """Return the name of the family/surface column if present, else ``None``."""
    for name in ("family", "Family", "FAMILY", "boundary", "surface", "zone", "patch"):
        if name in df.columns:
            return name
    return None


def list_families(df: pd.DataFrame, family_col: str | None = None) -> list[str]:
    """Return sorted unique family names."""
    col = family_col or detect_family_column(df)
    if col is None or col not in df.columns:
        return []
    return sorted(df[col].dropna().unique().tolist())


def detect_iter_column(df: pd.DataFrame) -> str:
    """Heuristic to find the iteration / time column.

    Looks for common names, then falls back to the first monotonically
    increasing integer column.
    """
    candidates = ("iter", "iteration", "time", "t", "step", "timestep", "Time")
    for name in candidates:
        if name in df.columns:
            return name

    for col in df.columns:
        s = df[col]
        if s.dtype.kind in ("i", "u") and s.is_monotonic_increasing:
            return str(col)

    raise ValueError(
        "Cannot auto-detect iteration column. "
        f"Provide it explicitly.  Available columns: {list(df.columns)}"
    )


def trim_dataframe(df: pd.DataFrame, iter_col: str, start: int | None = None, end: int | None = None) -> pd.DataFrame:
    """Return rows where iter_col is between *start* and *end* (inclusive)."""
    out = df
    if start is not None:
        out = out[out[iter_col] >= start]
    if end is not None:
        out = out[out[iter_col] <= end]
    return out.reset_index(drop=True)
