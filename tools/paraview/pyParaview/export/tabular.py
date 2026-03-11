from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Mapping

import pandas as pd


def export_surface_tables(
    tables: Mapping[str, pd.DataFrame],
    basename: str | Path,
    fmt: str = "parquet",
    compression: str = "zstd",
) -> Dict[str, Path]:
    """
    Export a mapping of surface_name -> DataFrame to files.
    """
    basename = Path(basename)
    written: Dict[str, Path] = {}

    for surface, df in tables.items():
        filename = basename.parent / f"{basename.name}_{surface}.{fmt}"
        if fmt == "csv":
            df.to_csv(filename, index=False)
        elif fmt == "parquet":
            df.to_parquet(filename, compression=compression, index=False)
        else:
            raise ValueError("fmt must be 'csv' or 'parquet'")
        written[surface] = filename

    return written


def load_surface_tables(
    basename: str | Path,
    surfaces: Iterable[str],
    fmt: str = "parquet",
) -> Dict[str, pd.DataFrame]:
    """
    Load previously exported surface tables.
    """
    basename = Path(basename)
    tables: Dict[str, pd.DataFrame] = {}

    for surface in surfaces:
        filename = basename.parent / f"{basename.name}_{surface}.{fmt}"
        if fmt == "csv":
            df = pd.read_csv(filename)
        elif fmt == "parquet":
            df = pd.read_parquet(filename)
        else:
            raise ValueError("fmt must be 'csv' or 'parquet'")
        tables[surface] = df

    return tables

