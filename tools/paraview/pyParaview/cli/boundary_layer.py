from __future__ import annotations

import argparse

from ..workflows.boundary_layer import export_boundary_layer_bundle


def cmd_extract(args: argparse.Namespace) -> None:
    export_boundary_layer_bundle(
        data_path=args.data,
        fields=args.fields,
        basename=args.basename,
        block_name=args.block,
        fmt=args.format,
    )


def add_subcommands(subparsers: argparse._SubParsersAction) -> None:
    p_extract = subparsers.add_parser(
        "extract", help="Extract and export boundary-layer bundle"
    )
    p_extract.add_argument("data", help="Input VTM/VTK/VTU file")
    p_extract.add_argument(
        "--fields",
        nargs="+",
        required=True,
        help="Variables to extract",
    )
    p_extract.add_argument(
        "--basename",
        default="boundary_layer",
        help="Output filename prefix",
    )
    p_extract.add_argument(
        "--block",
        default="boundary_layer",
        help="Boundary-layer block name",
    )
    p_extract.add_argument(
        "--format",
        default="parquet",
        choices=["csv", "parquet"],
        help="Output format",
    )
    p_extract.set_defaults(func=cmd_extract)

