"""Le contrat d'un moteur de rendu 3D."""

from __future__ import annotations

from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.engine.scene import Plan, Scene

__all__ = ["Moteur"]


class Moteur(Protocol):
    """Dessine les images d'un :class:`Plan` dans une :class:`Scene`.

    S'utilise comme gestionnaire de contexte ; ``image(k, vue, taille)`` rend l'image
    ``k`` du plan vue par la caméra ``vue``, en RGB ``uint8`` ``(hauteur, largeur, 3)``.
    """

    def __init__(self, scene: Scene, plan: Plan) -> None: ...

    def image(self, k: int, vue: str | None = None, taille: tuple[int, int] | None = None) -> NDArray[np.uint8]: ...

    def fermer(self) -> None: ...

    def __enter__(self) -> Moteur: ...

    def __exit__(self, *exc: object) -> None: ...
