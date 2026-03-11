from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console
from rich.progress import track

from ..workflows.surfaces import export_surfaces_from_case


console = Console()


def cmd_extract(args: argparse.Namespace) -> None:
    surfaces = args.surfaces
    fields = args.fields

    export_surfaces_from_case(
        data_path=args.data,
        surfaces=surfaces,
        fields=fields,
        basename=args.basename,
        fmt=args.format,
    )


def add_subcommands(subparsers: argparse._SubParsersAction) -> None:
    p_extract = subparsers.add_parser("extract", help="Extract and export surfaces")
    p_extract.add_argument("data", help="Input VTM/VTK/VTU file")
    p_extract.add_argument(
        "--surfaces",
        nargs="+",
        required=True,
        help="Surface block names",
    )
    p_extract.add_argument(
        "--fields",
        nargs="+",
        required=True,
        help="Variables to extract",
    )
    p_extract.add_argument(
        "--basename",
        default="output",
        help="Output filename prefix",
    )
    p_extract.add_argument(
        "--format",
        default="parquet",
        choices=["csv", "parquet"],
        help="Output format",
    )
    p_extract.set_defaults(func=cmd_extract)

