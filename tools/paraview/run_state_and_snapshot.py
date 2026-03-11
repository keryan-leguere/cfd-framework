#!/usr/bin/env python3
from __future__ import annotations, print_function
import argparse
import os
import sys
from pyParaview.paraview.state import parse_pvsm_readers, render_snapshot


def main():
    parser = argparse.ArgumentParser(
        description="Load ParaView state, set data files, export snapshot."
    )
    parser.add_argument("state_file", help="Path to .pvsm state file")
    parser.add_argument("output_image", help="Path for output snapshot (e.g. .png)")
    parser.add_argument(
        "data_files",
        nargs="*",
        help="Data files to use (same order as 'Choose File Names' in GUI)",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Search for data files in this directory (by basename from state)",
    )
    parser.add_argument(
        "--resolution",
        nargs=2,
        type=int,
        default=None,
        metavar=("W", "H"),
        help="Image resolution width height (default: view size)",
    )
    args = parser.parse_args()

    state_path = os.path.abspath(args.state_file)
    if not os.path.isfile(state_path):
        print("Error: state file not found:", state_path, file=sys.stderr)
        sys.exit(1)

    use_custom_files = bool(args.data_files)
    use_data_dir = args.data_dir is not None

    if use_custom_files and use_data_dir:
        print(
            "Error: use either positional data files or --data-dir, not both.",
            file=sys.stderr,
        )
        sys.exit(1)

    data_files = args.data_files if use_custom_files else None
    data_dir = args.data_dir if use_data_dir else None
    resolution = tuple(args.resolution) if args.resolution else None

    try:
        render_snapshot(
            state_file=state_path,
            output_image=args.output_image,
            data_files=data_files,
            data_dir=data_dir,
            resolution=resolution,
        )
    except Exception as exc:  # pragma: no cover - defensive path
        print(f"Error while rendering snapshot: {exc}", file=sys.stderr)
        sys.exit(1)
    else:
        print("Saved snapshot:", os.path.abspath(args.output_image))


if __name__ == "__main__":
    main()
