#!/usr/bin/env python3

import argparse
from pathlib import Path

from rich.console import Console
from rich.progress import track
from rich.table import Table

from pyParaview.surfaces import extract_surfaces
from pyParaview.export.tabular import export_surface_tables

console = Console()


# ------------------------------------------------------------
# Extraction
# ------------------------------------------------------------

def extract_surface_data(vtm_file, surface_names, variables):
    """
    Thin wrapper around pyParaview.extract_surfaces with rich progress.
    """
    console.print(f"[bold cyan]Loading VTM:[/] {vtm_file}")
    dfs = {}
    for name in track(surface_names, description="Extracting surfaces"):
        tables = extract_surfaces(vtm_file, [name], variables)
        if not tables:
            console.print(f"[red]Surface not found:[/] {name}")
            continue
        dfs[name] = tables[name]
    if not dfs:
        raise RuntimeError("No surfaces extracted")
    return dfs


# ------------------------------------------------------------
# Export
# ------------------------------------------------------------

def export_surfaces(dfs, basename, fmt="parquet", compression="zstd"):
    """
    Export each surface dataframe as

    basename_SURFACE.csv
    basename_SURFACE.parquet
    """
    written = export_surface_tables(dfs, basename, fmt=fmt, compression=compression)
    for surface, path in written.items():
        console.print(f"[green]Saved:[/] {path}")


# ------------------------------------------------------------
# Load
# ------------------------------------------------------------

def load_surfaces(basename, surfaces, fmt="parquet"):
    """
    Load previously exported surfaces.
    """

    dfs = {}

    for surface in surfaces:

        filename = f"{basename}_{surface}.{fmt}"

        if fmt == "csv":
            df = pd.read_csv(filename)

        elif fmt == "parquet":
            df = pd.read_parquet(filename)

        else:
            raise ValueError("fmt must be csv or parquet")

        dfs[surface] = df

        console.print(f"[cyan]Loaded:[/] {filename}")

    return dfs


# ------------------------------------------------------------
# Summary
# ------------------------------------------------------------

def show_summary(dfs):

    table = Table(title="Extraction summary")

    table.add_column("Surface")
    table.add_column("Rows")
    table.add_column("Columns")

    for name, df in dfs.items():

        table.add_row(
            name,
            str(len(df)),
            ", ".join(df.columns),
        )

    console.print(table)


# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description="Extract surface data from VTM file"
    )

    parser.add_argument(
        "vtm",
        help="Input VTM file",
    )

    parser.add_argument(
        "--surfaces",
        nargs="+",
        required=True,
        help="Surface block names",
    )

    parser.add_argument(
        "--vars",
        nargs="+",
        required=True,
        help="Variables to extract",
    )

    parser.add_argument(
        "--basename",
        default="output",
        help="Output filename prefix",
    )

    parser.add_argument(
        "--format",
        default="parquet",
        choices=["csv", "parquet"],
        help="Output format",
    )

    args = parser.parse_args()

    dfs = extract_surface_data(
        args.vtm,
        args.surfaces,
        args.vars,
    )

    show_summary(dfs)

    export_surfaces(
        dfs,
        args.basename,
        fmt=args.format,
    )


if __name__ == "__main__":
    main()

"""
Exemple de commande:
python extract_vtm_surfaces.py solution.vtm \
--surfaces wing fuselage tail \
--vars pressure wall_shear \
--basename caseA \
--format parquet

Sortie:
caseA_wing.parquet
caseA_fuselage.parquet
caseA_tail.parquet
"""