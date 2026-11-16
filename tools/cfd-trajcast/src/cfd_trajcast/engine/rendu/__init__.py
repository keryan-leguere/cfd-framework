"""Moteurs de rendu 3D derrière une même interface (:class:`~.interface.Moteur`)."""

from __future__ import annotations

from typing import Any

from cfd_trajcast.data.configuration import ConfigMoteur
from cfd_trajcast.engine.scene import Plan, Scene

__all__ = ["creer_moteur"]


def creer_moteur(scene: Scene, plan: Plan, config: ConfigMoteur | None = None) -> Any:
    """Le moteur que demande ``config`` ; Blender n'est importé que s'il est demandé (bpy est lourd)."""
    if config is not None and config.type == "blender":
        from cfd_trajcast.engine.rendu.blender import MoteurBlender

        return MoteurBlender(scene, plan, config)
    from cfd_trajcast.engine.rendu.pyvista_ import MoteurPyVista

    return MoteurPyVista(scene, plan)
