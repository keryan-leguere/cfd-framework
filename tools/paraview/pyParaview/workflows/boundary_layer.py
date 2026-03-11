from __future__ import annotations

from pathlib import Path
from typing import Sequence

from rich.console import Console
from rich.table import Table

from ..aero.boundary_layer import extract_boundary_layer
from ..export.tabular import export_surface_tables


console = Console()


def export_boundary_layer_bundle(
    data_path: str | Path,
    fields: Sequence[str],
    basename: str | Path,
    block_name: str = "boundary_layer",
    fmt: str = "parquet",
) -> None:
    """
    Extract the boundary-layer block and export it as a single-table bundle.
    """
    console.print(f"[bold cyan]Extracting boundary layer from[/] {data_path}")
    df = extract_boundary_layer(data_path, fields, block_name=block_name)
    written = export_surface_tables({block_name: df}, basename, fmt=fmt)

    table = Table(title="Boundary-layer export")
    table.add_column("Block")
    table.add_column("Path")
    for name, path in written.items():
        table.add_row(name, str(path))
    console.print(table)

