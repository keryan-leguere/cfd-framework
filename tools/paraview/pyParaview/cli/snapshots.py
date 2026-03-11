from __future__ import annotations

import argparse

from ..workflows.snapshots import render_snapshot_from_state


def cmd_render(args: argparse.Namespace) -> None:
    resolution = None
    if args.resolution:
        resolution = (args.resolution[0], args.resolution[1])
    render_snapshot_from_state(
        state_file=args.state,
        output_image=args.output,
        data_files=args.data_files or None,
        data_dir=args.data_dir,
        resolution=resolution,
    )


def add_subcommands(subparsers: argparse._SubParsersAction) -> None:
    p_render = subparsers.add_parser(
        "render", help="Render snapshot from ParaView state file"
    )
    p_render.add_argument("state", help="Path to .pvsm state file")
    p_render.add_argument("output", help="Output image path")
    p_render.add_argument(
        "data_files",
        nargs="*",
        help="Optional data files (same order as in GUI)",
    )
    p_render.add_argument(
        "--data-dir",
        default=None,
        help="Search for data files in this directory (by basename)",
    )
    p_render.add_argument(
        "--resolution",
        nargs=2,
        type=int,
        metavar=("W", "H"),
        help="Image resolution width height",
    )
    p_render.set_defaults(func=cmd_render)

