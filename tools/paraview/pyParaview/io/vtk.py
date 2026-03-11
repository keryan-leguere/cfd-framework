from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pyvista as pv


def read_dataset(path: str | Path) -> pv.DataSet:
    """
    Read a VTK-family dataset (including VTM multiblock files) with PyVista.
    """
    return pv.read(str(path))


def list_blocks(dataset: pv.DataSet) -> list[str]:
    """
    List block names for a multiblock dataset.
    Returns an empty list for non-multiblock datasets.
    """
    if not isinstance(dataset, pv.MultiBlock):
        return []
    names: list[str] = []
    for i in range(len(dataset)):
        name = dataset.get_block_name(i)
        if name is None:
            name = str(i)
        names.append(name)
    return names


def get_block(dataset: pv.DataSet, name: str):
    """
    Return a block from a multiblock dataset by name or index.
    Falls back to integer index if `name` is digits.
    """
    if isinstance(dataset, pv.MultiBlock):
        if name.isdigit():
            idx = int(name)
            return dataset[idx]
        try:
            return dataset.get_block(name)
        except (KeyError, IndexError):
            return None
    return None


def list_arrays(mesh: pv.DataSet, location: str = "all") -> list[str]:
    """
    List array names on a mesh.

    Parameters
    ----------
    mesh:
        Any PyVista dataset.
    location:
        "point", "cell", or "all".
    """
    names: set[str] = set()
    if location in ("point", "all"):
        names.update(mesh.point_data.keys())
    if location in ("cell", "all"):
        names.update(mesh.cell_data.keys())
    return sorted(names)


def to_surface(mesh: pv.DataSet) -> pv.PolyData:
    """
    Extract a surface representation from a volume dataset.
    """
    if isinstance(mesh, pv.PolyData):
        return mesh
    return mesh.extract_surface()


def merge_point_and_cell_arrays(mesh: pv.DataSet) -> pv.DataSet:
    """
    Ensure all arrays are accessible at point level by promoting cell arrays
    when possible (simple copy).
    """
    if not mesh.cell_data:
        return mesh

    surf = mesh.copy()
    for name in mesh.cell_data.keys():
        if name in surf.point_data:
            continue
        data = mesh.cell_data[name]
        if data is None:
            continue
        surf.point_data[name] = data
    return surf


def ensure_array(mesh: pv.DataSet, name: str):
    """
    Return a data array by name, searching point_data then cell_data.
    """
    if name in mesh.point_data:
        return mesh.point_data[name]
    if name in mesh.cell_data:
        return mesh.cell_data[name]
    raise KeyError(f"Array '{name}' not found in dataset")

