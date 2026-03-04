#!/usr/bin/env python3
"""
Load a ParaView state file (.pvsm), set custom data filenames, and export a snapshot.

Usage (run with pvpython):
  pvpython run_state_and_snapshot.py STATE.pvsm OUTPUT.png [FILE1 [FILE2 ...]]

Or use data directory (ParaView will search for files by basename):
  pvpython run_state_and_snapshot.py STATE.pvsm OUTPUT.png --data-dir /path/to/data

Requires: ParaView's pvpython (or pvbatch for parallel).
"""

from __future__ import print_function
import argparse
import os
import sys
import xml.etree.ElementTree as ET


def _parse_pvsm_readers(state_path):
    """
    Parse a .pvsm file and return a list of (proxy_group, proxy_id, prop_name) for
    each reader that has FileName or FileNames. Order matches the state file.
    """
    tree = ET.parse(state_path)
    root = tree.getroot()
    readers = []
    for proxy in root.iter("Proxy"):
        group = proxy.get("group")
        proxy_id = proxy.get("id")
        if not proxy_id:
            continue
        for prop in proxy.findall(".//Property"):
            pname = prop.get("name")
            if pname in ("FileName", "FileNames"):
                readers.append((group, proxy_id, pname))
                break
    return readers


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

    # Import ParaView (must be run with pvpython)
    try:
        from paraview.simple import (
            GetActiveView,
            GetSources,
            LoadState,
            Render,
            ResetCamera,
            SaveScreenshot,
        )
    except ImportError:
        print(
            "Error: run this script with ParaView's pvpython, e.g.:",
            "  pvpython run_state_and_snapshot.py ...",
            file=sys.stderr,
        )
        sys.exit(1)

    # Build LoadState options
    use_custom_files = bool(args.data_files)
    use_data_dir = args.data_dir is not None

    if use_custom_files and use_data_dir:
        print("Error: use either positional data files or --data-dir, not both.", file=sys.stderr)
        sys.exit(1)

    if use_data_dir:
        data_dir = os.path.abspath(args.data_dir)
        if not os.path.isdir(data_dir):
            print("Error: data directory not found:", data_dir, file=sys.stderr)
            sys.exit(1)
        LoadState(
            state_path,
            data_directory=data_dir,
            restrict_to_data_directory=False,
        )
    elif use_custom_files:
        readers = _parse_pvsm_readers(state_path)
        if len(readers) != len(args.data_files):
            print(
                "Warning: state has {} file slot(s), you provided {} file(s).".format(
                    len(readers), len(args.data_files)
                ),
                file=sys.stderr,
            )
        filenames_spec = []
        for i, (group, proxy_id, prop_name) in enumerate(readers):
            if i >= len(args.data_files):
                break
            path = os.path.abspath(args.data_files[i])
            if not os.path.isfile(path):
                print("Warning: data file not found:", path, file=sys.stderr)
            filenames_spec.append({"id": proxy_id, prop_name: path})
        try:
            # ParaView 5.4+ LoadState can take filenames as list of dicts
            LoadState(state_path, filenames=filenames_spec)
        except (TypeError, AttributeError):
            # Older ParaView: load state then set reader file names by order
            LoadState(state_path)
            try:
                pxm = __import__("paraview.servermanager", fromlist=["ProxyManager"]).ProxyManager()
            except Exception:
                pxm = None
            for i, (group, proxy_id, prop_name) in enumerate(readers):
                if i >= len(args.data_files):
                    break
                path = os.path.abspath(args.data_files[i])
                proxy = None
                if pxm is not None:
                    try:
                        proxy = pxm.GetProxy(group or "sources", proxy_id)
                    except Exception:
                        pass
                if proxy is None:
                    sources = GetSources()
                    for (_name, _id), p in sources.items():
                        if _id == proxy_id and (hasattr(p, "FileName") or hasattr(p, "FileNames")):
                            proxy = p
                            break
                if proxy is not None:
                    if prop_name == "FileName":
                        proxy.FileName = path
                    else:
                        proxy.FileNames = [path]
    else:
        # Use paths from state file (must exist)
        LoadState(state_path)

    view = GetActiveView()
    if view is None:
        print("Error: no active view after loading state.", file=sys.stderr)
        sys.exit(1)

    Render()
    ResetCamera()
    Render()

    out_path = os.path.abspath(args.output_image)
    out_dir = os.path.dirname(out_path)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    save_kw = {}
    if args.resolution:
        save_kw["ImageResolution"] = tuple(args.resolution)
    SaveScreenshot(out_path, **save_kw)
    print("Saved snapshot:", out_path)


if __name__ == "__main__":
    main()
