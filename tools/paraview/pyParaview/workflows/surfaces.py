from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from rich.console import Console
from rich.table import Table

from ..export.tabular import export_surface_tables
from ..surfaces import extract_surfaces


console = Console()


def export_surfaces_from_case(
    data_path: str | Path,
    surfaces: Sequence[str],
    fields: Sequence[str],
    basename: str | Path,
    fmt: str = "parquet",
) -> None:
    """
    High-level helper to extract and export multiple surfaces from a dataset.
    """
    console.print(f"[bold cyan]Extracting surfaces from[/] {data_path}")
    tables = extract_surfaces(data_path, surfaces, fields)
    written = export_surface_tables(tables, basename, fmt=fmt)

    table = Table(title="Exported surfaces")
    table.add_column("Surface")
    table.add_column("Path")
    for name, path in written.items():
        table.add_row(name, str(path))
    console.print(table)

