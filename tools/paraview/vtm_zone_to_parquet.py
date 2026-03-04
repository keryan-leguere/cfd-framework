#!/usr/bin/env python3
"""
Load a surface .vtm (VTK multiblock) file, extract a named zone, and export
x, y, z, p to Parquet.

Usage:
  python vtm_zone_to_parquet.py surface.vtm output.parquet --zone NAME [--pressure-name p]

Requires: pyvista, pandas, pyarrow (pip install pyvista pandas pyarrow).
"""

from __future__ import print_function

import argparse
import os
import sys


def _find_pressure_array(block, preferred_name):
    """Return point data array for pressure: preferred name or first scalar."""
    pd = block.point_data
    if preferred_name in pd.keys():
        arr = pd[preferred_name]
        if arr.ndim == 1 or (arr.ndim == 2 and arr.shape[1] == 1):
            return arr.ravel() if arr.ndim == 2 else arr
        # vector -> use first component or magnitude; here we take first component
        return arr[:, 0] if arr.ndim == 2 else arr
    # Try common aliases
    for name in ("p", "Pressure", "p_rgh", "pressure"):
        if name in pd.keys():
            arr = pd[name]
            if arr.ndim == 1:
                return arr
            if arr.ndim == 2 and arr.shape[1] == 1:
                return arr.ravel()
            if arr.ndim == 2:
                return arr[:, 0]
            return arr
    # First scalar point array
    for name in pd.keys():
        arr = pd[name]
        if arr.ndim == 1 or (arr.ndim == 2 and arr.shape[1] == 1):
            return arr.ravel() if arr.ndim == 2 else arr
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Extract a named zone from a .vtm surface file to Parquet (x, y, z, p)."
    )
    parser.add_argument("vtm_file", help="Path to .vtm (VTK multiblock) file")
    parser.add_argument("output_parquet", help="Path for output .parquet file")
    parser.add_argument(
        "--zone",
        "-z",
        required=True,
        metavar="NAME",
        help="Name of the zone/block to extract (as in the VTM)",
    )
    parser.add_argument(
        "--pressure-name",
        "-p",
        default="p",
        metavar="NAME",
        help="Point data array name for pressure (default: p)",
    )
    parser.add_argument(
        "--list-zones",
        action="store_true",
        help="List block names in the VTM and exit (no output file)",
    )
    parser.add_argument(
        "--list-arrays",
        action="store_true",
        help="List point data arrays for the chosen zone and exit",
    )
    args = parser.parse_args()

    vtm_path = os.path.abspath(args.vtm_file)
    if not os.path.isfile(vtm_path):
        print("Error: VTM file not found:", vtm_path, file=sys.stderr)
        sys.exit(1)

    try:
        import pyvista as pv
    except ImportError:
        print("Error: pyvista is required. Install with: pip install pyvista", file=sys.stderr)
        sys.exit(1)
    try:
        import pandas as pd
    except ImportError:
        print("Error: pandas is required. Install with: pip install pandas", file=sys.stderr)
        sys.exit(1)
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        print("Error: pyarrow is required for Parquet. Install with: pip install pyarrow", file=sys.stderr)
        sys.exit(1)

    data = pv.read(vtm_path)
    if not hasattr(data, "get_block") and not hasattr(data, "keys"):
        print("Error: file is not a multiblock dataset (expected .vtm with multiple blocks).", file=sys.stderr)
        sys.exit(1)

    # MultiBlock: get_block(name) or [name]
    if args.list_zones:
        names = []
        if hasattr(data, "keys"):
            names = list(data.keys())
        else:
            for i in range(data.n_blocks):
                b = data.get_block(i)
                if b is not None and hasattr(b, "name"):
                    names.append(getattr(b, "name", str(i)))
                else:
                    names.append(str(i))
        if not names and hasattr(data, "n_blocks"):
            names = [str(i) for i in range(data.n_blocks)]
        print("Zones (block names) in", vtm_path)
        for n in names:
            print(" ", n)
        return

    try:
        block = data.get_block(args.zone) if hasattr(data, "get_block") else data[args.zone]
    except (KeyError, IndexError, TypeError):
        block = None
    if block is None:
        try:
            block = data[args.zone]
        except (KeyError, IndexError, TypeError):
            block = None
    if block is None:
        print("Error: zone '{}' not found in VTM. Use --list-zones to see available names.".format(args.zone), file=sys.stderr)
        sys.exit(1)

    pts = block.points
    if pts is None or len(pts) == 0:
        print("Error: zone '{}' has no points.".format(args.zone), file=sys.stderr)
        sys.exit(1)

    x = pts[:, 0]
    y = pts[:, 1]
    z = pts[:, 2] if pts.shape[1] >= 3 else 0.0

    if args.list_arrays:
        print("Point data arrays for zone '{}':".format(args.zone))
        for k in block.point_data.keys():
            arr = block.point_data[k]
            sh = getattr(arr, "shape", ())
            print(" ", k, sh)
        return

    p_arr = _find_pressure_array(block, args.pressure_name)
    if p_arr is None:
        print(
            "Error: no pressure-like point data (tried '{}'). Use --list-arrays to see available arrays.".format(
                args.pressure_name
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    n = len(x)
    if len(p_arr) != n:
        print(
            "Error: pressure array length {} does not match point count {}.".format(len(p_arr), n),
            file=sys.stderr,
        )
        sys.exit(1)

    df = pd.DataFrame({"x": x, "y": y, "z": z, "p": p_arr})
    out_path = os.path.abspath(args.output_parquet)
    out_dir = os.path.dirname(out_path)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print("Wrote {} rows (x, y, z, p) to {}.".format(len(df), out_path))


if __name__ == "__main__":
    main()
