from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

import pyvista as pv

from ..filters.subset import crop_to_bounds, save_subset


console = Console()


def cmd_crop(args: argparse.Namespace) -> None:
    ds = pv.read(args.data)
    subset = crop_to_bounds(
        ds,
        args.xmin,
        args.xmax,
        args.ymin,
        args.ymax,
        args.zmin,
        args.zmax,
    )
    save_subset(subset, args.output)
    console.print(f"[green]Saved subset:[/] {Path(args.output).resolve()}")


def add_subcommands(subparsers: argparse._SubParsersAction) -> None:
    p_crop = subparsers.add_parser("crop", help="Crop dataset to bounds and save")
    p_crop.add_argument("data", help="Input dataset")
    p_crop.add_argument("output", help="Output dataset path")
    p_crop.add_argument("--xmin", type=float, required=True)
    p_crop.add_argument("--xmax", type=float, required=True)
    p_crop.add_argument("--ymin", type=float, required=True)
    p_crop.add_argument("--ymax", type=float, required=True)
    p_crop.add_argument("--zmin", type=float, required=True)
    p_crop.add_argument("--zmax", type=float, required=True)
    p_crop.set_defaults(func=cmd_crop)

