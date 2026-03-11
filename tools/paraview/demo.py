#!/usr/bin/env python3
"""
Demo script for the pyParaview package.

Run with a VTM/VTK file to exercise extraction and subsetting:
  python demo.py [path/to/data.vtm]

Without arguments, uses a small synthetic multiblock to demonstrate the API.
"""

from pathlib import Path
import sys

import pandas as pd
import pyvista as pv

# Ensure package is importable when run from tools/paraview
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pyParaview import (
    read_dataset,
    list_blocks,
    get_block,
    extract_surfaces,
    extract_boundary_layer,
    crop_to_bounds,
    add_cp_column,
    add_cf_column,
    slice_plane,
    sample_line,
)
from pyParaview.export.tabular import export_surface_tables
from pyParaview.filters.subset import save_subset

console = Console()


def make_demo_dataset():
    """Build a minimal multiblock for demo when no file is provided."""
    # Simple quad as "wing" surface
    wing = pv.Plane(i_size=2, j_size=1, i_resolution=3, j_resolution=2)
    wing.point_data["p"] = [101325.0] * wing.n_points
    wing.point_data["wallShearStress"] = [[0.1, 0.0, 0.0]] * wing.n_points

    # Another block as "fuselage"
    fuselage = pv.Cylinder(radius=0.5, height=2.0, resolution=6)
    fuselage.point_data["p"] = [101320.0] * fuselage.n_points

    # Boundary-layer style block (prism layer)
    bl = pv.Box(bounds=(0, 1, 0, 1, 0, 0.2))
    bl.point_data["U"] = [[0.5 * (z / 0.2), 0, 0] for z in bl.points[:, 2]]

    mb = pv.MultiBlock()
    mb["wing"] = wing
    mb["fuselage"] = fuselage
    mb["boundary_layer"] = bl
    return mb


def run_demo(data_path: str | Path | None = None) -> None:
    if data_path is not None:
        path = Path(data_path)
        if not path.is_file():
            console.print(f"[red]File not found:[/] {path}")
            return
        console.print(Panel(f"Using data file: [bold]{path}[/]", title="pyParaview demo"))
        ds = read_dataset(path)
        is_synthetic = False
    else:
        console.print(Panel("No file provided — using [bold]synthetic multiblock[/]", title="pyParaview demo"))
        ds = make_demo_dataset()
        is_synthetic = True

    # --- IO: list blocks ---
    blocks = list_blocks(ds)
    table = Table(title="Blocks in dataset")
    table.add_column("Block")
    for name in blocks:
        table.add_row(name)
    if not blocks:
        table.add_row("(single block or empty)")
    console.print(table)

    # --- Surface extraction ---
    if blocks:
        surface_names = [b for b in blocks if b != "boundary_layer"][:2]
        if surface_names:
            console.print("\n[bold cyan]Surface extraction[/]")
            fields = ["p"]
            if is_synthetic:
                fields = ["p", "wallShearStress"]
            if data_path is not None:
                tables = extract_surfaces(data_path, surface_names, fields)
            else:
                # Synthetic: build tables from multiblock by hand
                tables = {}
                for name in surface_names:
                    block = get_block(ds, name)
                    if block is not None:
                        pts = block.points
                        data = {"x": pts[:, 0], "y": pts[:, 1], "z": pts[:, 2]}
                        for f in fields:
                            if f in block.point_data:
                                data[f] = block.point_data[f]
                        tables[name] = pd.DataFrame(data)
            if tables:
                out_dir = Path("/tmp/pyparaview_demo") if data_path is None else Path(data_path).parent
                out_dir.mkdir(parents=True, exist_ok=True)
                basename = out_dir / "demo_surfaces"
                written = export_surface_tables(tables, basename, fmt="parquet")
                for name, p in written.items():
                    console.print(f"  [green]Exported[/] {name} → {p}")

    # --- Cp / Cf on a table ---
    console.print("\n[bold cyan]Cp / Cf helpers[/]")
    df = pd.DataFrame({"x": [0.0], "y": [0.0], "z": [0.0], "p": [101325.0]})
    df = add_cp_column(df, p_ref=101325.0, q_ref=500.0)
    console.print("  add_cp_column(table, p_ref=101325, q_ref=500) → Cp column added")
    df["tau_w"] = 0.5
    df = add_cf_column(df, rho_ref=1.2, u_ref=25.0)
    console.print("  add_cf_column(table, rho_ref=1.2, u_ref=25) → Cf column added")

    # --- Slices and sampling (on first available 3D block) ---
    console.print("\n[bold cyan]Slices and sampling[/]")
    if is_synthetic:
        mesh = ds["boundary_layer"] if "boundary_layer" in list_blocks(ds) else ds[0]
    else:
        mesh = ds[0] if isinstance(ds, pv.MultiBlock) and len(ds) else ds
    try:
        sl = slice_plane(mesh, origin=[0.5, 0.5, 0.1], normal=[0, 0, 1])
        console.print(f"  slice_plane(origin=[0.5,0.5,0.1], normal=[0,0,1]) → {sl.n_points} points")
    except Exception as e:
        console.print(f"  slice_plane: [yellow]{e}[/]")
    try:
        line_df = sample_line(mesh, [0, 0, 0], [1, 1, 0.1], n_points=5)
        console.print(f"  sample_line([0,0,0], [1,1,0.1], n_points=5) → {len(line_df)} rows")
    except Exception as e:
        console.print(f"  sample_line: [yellow]{e}[/]")

    # --- Crop to bounds ---
    console.print("\n[bold cyan]Subset (crop to bounds)[/]")
    try:
        subset = crop_to_bounds(mesh, 0.0, 1.0, 0.0, 1.0, 0.0, 0.2)
        out_subset = Path("/tmp/pyparaview_demo/subset.vtk") if data_path is None else Path(data_path).parent / "demo_subset.vtk"
        out_subset.parent.mkdir(parents=True, exist_ok=True)
        save_subset(subset, out_subset)
        console.print(f"  crop_to_bounds(...) → saved to {out_subset}")
    except Exception as e:
        console.print(f"  crop_to_bounds: [yellow]{e}[/]")

    # --- Boundary layer (only if block exists) ---
    if "boundary_layer" in list_blocks(ds):
        console.print("\n[bold cyan]Boundary-layer extraction[/]")
        if data_path is not None:
            bl_df = extract_boundary_layer(data_path, ["U"], block_name="boundary_layer")
        else:
            bl = get_block(ds, "boundary_layer")
            pts = bl.points
            data = {"x": pts[:, 0], "y": pts[:, 1], "z": pts[:, 2], "block": "boundary_layer"}
            if "U" in bl.point_data:
                U = bl.point_data["U"]
                data["Ux"], data["Uy"], data["Uz"] = U[:, 0], U[:, 1], U[:, 2]
            bl_df = pd.DataFrame(data)
        console.print(f"  extract_boundary_layer(..., block_name='boundary_layer') → {len(bl_df)} rows")

    console.print("\n[dim]Snapshot rendering: use pvpython run_state_and_snapshot.py STATE.pvsm out.png [files][/]")
    console.print("[dim]CLI: pyparaview surfaces extract <file> --surfaces ... --fields ...[/]")


def main() -> None:
    data_path = sys.argv[1] if len(sys.argv) > 1 else None
    run_demo(data_path)


if __name__ == "__main__":
    main()
