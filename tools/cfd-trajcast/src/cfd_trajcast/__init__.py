"""cfd-trajcast : d'une simulation de vol de fusée à une vidéo de présentation.

Conventions internes (``00_DOC/01_REPERES.md``) : ENU local en mètres, corps FRD,
quaternion de Hamilton ``(w, x, y, z)`` corps → ENU.
"""

from __future__ import annotations

__version__ = "0.1.0"

from cfd_trajcast.data.configuration import Configuration, ErreurConfiguration, charger_configuration
from cfd_trajcast.data.constats import Constat
from cfd_trajcast.data.maquette import DeclarationMaquette, ErreurMaquette, Maquette
from cfd_trajcast.data.trajectoire import (
    DeclarationAttitude,
    DeclarationTrajectoire,
    ErreurAttitude,
    ErreurTrajectoire,
    Evenement,
    Trajectoire,
)
from cfd_trajcast.data.validation import verifier
from cfd_trajcast.engine.pipeline import Film, ResultatRendu
from cfd_trajcast.engine.ensemble import VueEnsemble
from cfd_trajcast.engine.schema_ensemble import Schema
from cfd_trajcast.engine.vue_vent import VueVent

__all__ = [
    "Configuration",
    "Constat",
    "DeclarationAttitude",
    "DeclarationMaquette",
    "DeclarationTrajectoire",
    "ErreurAttitude",
    "ErreurConfiguration",
    "ErreurMaquette",
    "ErreurTrajectoire",
    "Evenement",
    "Film",
    "Maquette",
    "ResultatRendu",
    "Schema",
    "Trajectoire",
    "VueEnsemble",
    "VueVent",
    "__version__",
    "charger_configuration",
    "verifier",
]
