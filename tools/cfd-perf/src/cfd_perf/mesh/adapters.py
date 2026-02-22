"""Mesh adapter interface and implementations."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from cfd_perf.mesh.models import MeshStatsRaw


class MeshAdapter(ABC):
    """Base class for all mesh format adapters."""

    @abstractmethod
    def read(self, path: Path) -> MeshStatsRaw:
        """Read mesh metadata from *path* and return raw stats."""
        ...

    @staticmethod
    def can_handle(path: Path) -> bool:  # noqa: ARG004
        """Return True if this adapter recognizes the file extension/format."""
        return False


class JsonMeshAdapter(MeshAdapter):
    """Read mesh metadata from a hand-written JSON file.

    Expected schema::

        {
            "num_cells": 5000000,
            "num_faces": 15000000,
            "cell_type_distribution": {"hex": 0.85, "tet": 0.15}
        }
    """

    @staticmethod
    def can_handle(path: Path) -> bool:
        return path.suffix.lower() == ".json"

    def read(self, path: Path) -> MeshStatsRaw:
        data: dict[str, Any] = json.loads(path.read_text())
        return MeshStatsRaw(
            num_cells=int(data["num_cells"]),
            num_faces=int(data["num_faces"]),
            cell_type_distribution=data.get("cell_type_distribution", {}),
        )


_ADAPTER_REGISTRY: list[type[MeshAdapter]] = [JsonMeshAdapter]


def get_adapter(path: Path, adapter_name: str | None = None) -> MeshAdapter:
    """Resolve an adapter for *path*, optionally forcing *adapter_name*."""
    if adapter_name == "json":
        return JsonMeshAdapter()

    for adapter_cls in _ADAPTER_REGISTRY:
        if adapter_cls.can_handle(path):
            return adapter_cls()

    raise ValueError(f"No mesh adapter found for {path}. Use --adapter json with a JSON metadata file.")
