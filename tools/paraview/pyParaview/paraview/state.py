from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


def parse_pvsm_readers(state_file: str | Path) -> List[Tuple[str | None, str, str]]:
    """
    Parse a .pvsm file and return a list of (proxy_group, proxy_id, prop_name)
    for each reader that has FileName or FileNames.
    """
    tree = ET.parse(state_file)
    root = tree.getroot()
    readers: List[Tuple[str | None, str, str]] = []
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


def render_snapshot(
    state_file: str | Path,
    output_image: str | Path,
    data_files: Iterable[str] | None = None,
    data_dir: str | Path | None = None,
    resolution: tuple[int, int] | None = None,
) -> None:
    """
    Load a ParaView state, optionally rebind data sources, and save a snapshot.

    Must be run under pvpython / pvbatch.
    """
    from paraview.simple import (  # type: ignore[import-not-found]
        GetActiveView,
        GetSources,
        LoadState,
        Render,
        ResetCamera,
        SaveScreenshot,
    )

    state_path = os.path.abspath(str(state_file))
    out_path = os.path.abspath(str(output_image))

    use_custom_files = data_files is not None and len(list(data_files)) > 0
    use_data_dir = data_dir is not None

    if use_custom_files and use_data_dir:
        raise ValueError("Use either data_files or data_dir, not both")

    if use_data_dir:
        data_dir_abs = os.path.abspath(str(data_dir))
        if not os.path.isdir(data_dir_abs):
            raise FileNotFoundError(f"Data directory not found: {data_dir_abs}")
        LoadState(
            state_path,
            data_directory=data_dir_abs,
            restrict_to_data_directory=False,
        )
    elif use_custom_files:
        readers = parse_pvsm_readers(state_path)
        filenames_spec: List[Dict[str, object]] = []
        files_list = list(data_files or [])
        for i, (group, proxy_id, prop_name) in enumerate(readers):
            if i >= len(files_list):
                break
            path = os.path.abspath(files_list[i])
            filenames_spec.append({"id": proxy_id, prop_name: path})
        try:
            LoadState(state_path, filenames=filenames_spec)
        except (TypeError, AttributeError):
            LoadState(state_path)
            try:
                pxm = __import__(
                    "paraview.servermanager", fromlist=["ProxyManager"]
                ).ProxyManager()
            except Exception:
                pxm = None
            for i, (group, proxy_id, prop_name) in enumerate(readers):
                if i >= len(files_list):
                    break
                path = os.path.abspath(files_list[i])
                proxy = None
                if pxm is not None:
                    try:
                        proxy = pxm.GetProxy(group or "sources", proxy_id)
                    except Exception:
                        pass
                if proxy is None:
                    sources = GetSources()
                    for (_name, _id), p in sources.items():
                        if _id == proxy_id and (
                            hasattr(p, "FileName") or hasattr(p, "FileNames")
                        ):
                            proxy = p
                            break
                if proxy is not None:
                    if prop_name == "FileName":
                        proxy.FileName = path
                    else:
                        proxy.FileNames = [path]
    else:
        LoadState(state_path)

    view = GetActiveView()
    if view is None:
        raise RuntimeError("No active view after loading state")

    Render()
    ResetCamera()
    Render()

    out_dir = os.path.dirname(out_path)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    save_kw = {}
    if resolution is not None:
        save_kw["ImageResolution"] = resolution
    SaveScreenshot(out_path, **save_kw)

