from __future__ import annotations

import argparse

from rich.console import Console

from . import boundary_layer as cli_boundary_layer
from . import snapshots as cli_snapshots
from . import subset as cli_subset
from . import surfaces as cli_surfaces


console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pyparaview", description="pyParaview CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # surfaces
    p_surfaces = subparsers.add_parser("surfaces", help="Surface extraction commands")
    sp_surfaces = p_surfaces.add_subparsers(dest="subcommand", required=True)
    cli_surfaces.add_subcommands(sp_surfaces)

    # boundary-layer
    p_bl = subparsers.add_parser("boundary-layer", help="Boundary-layer commands")
    sp_bl = p_bl.add_subparsers(dest="subcommand", required=True)
    cli_boundary_layer.add_subcommands(sp_bl)

    # subset
    p_subset = subparsers.add_parser("subset", help="Dataset subsetting commands")
    sp_subset = p_subset.add_subparsers(dest="subcommand", required=True)
    cli_subset.add_subcommands(sp_subset)

    # snapshots
    p_snap = subparsers.add_parser("snapshot", help="Snapshot rendering commands")
    sp_snap = p_snap.add_subparsers(dest="subcommand", required=True)
    cli_snapshots.add_subcommands(sp_snap)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

