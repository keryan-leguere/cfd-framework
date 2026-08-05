"""cfd-traj — réduire un lot de trajectoires dispersées à un plan de calcul CFD minimal.

Trois questions, dans l'ordre :

1. **Comprendre.** Qu'y a-t-il dans ces fichiers ? Combien de directions le
   nuage occupe-t-il vraiment ? (:func:`~cfd_traj.engine.inspect.inspect`)
2. **Analyser.** Quel domaine l'engin balaie-t-il réellement, par opposition à
   l'hyperrectangle min/max qui le contient ?
   (:func:`~cfd_traj.engine.envelope.build_envelope`)
3. **Réduire.** Quel plan de calcul minimal couvre ce domaine, et que coûte-t-il
   une fois les symétries exploitées ?
   (:func:`~cfd_traj.engine.doe.build_plan`)

Le tout se vérifie en rejouant les trajectoires à travers le résultat
(:func:`~cfd_traj.engine.coverage.check_coverage`).

Les colonnes de paramètres des fichiers d'entrée sont **génériques** : autant
qu'on veut, sous n'importe quels noms. Rien ici ne reconnaît une colonne
autrement que par ses valeurs, ou par ce que le fichier d'étude en déclare.

Utilisation en ligne de commande :

    cfd-traj generer | inspecter | analyser | doe | couverture | example
"""

from __future__ import annotations

from cfd_traj.core.adim import FlowState, Reference, flow_state, nondimensionalise
from cfd_traj.core.angles import from_aeroballistic, to_aeroballistic
from cfd_traj.core.sampling import corner_points, maximin_lhs, place_levels
from cfd_traj.core.stats import Bounds, PcaResult, pca, quantile_bounds
from cfd_traj.core.symmetry import (
    CalcConfig,
    DeflectionSymmetry,
    SymmetryGroup,
    SymmetrySpec,
    azimuth_levels,
    calc_config,
    classify_deflection,
    fold_phi,
    zero_components,
)
from cfd_traj.data.columns import ColumnSpec, Role, Scale, build_specs, detect_role
from cfd_traj.data.dataset import DatasetError, Shot, TrajectoryDataset, load_dataset
from cfd_traj.data.derive import add_derived_columns
from cfd_traj.data.study import (
    BandSpec,
    DeflectionSet,
    DoeMethod,
    DoeSpec,
    EnvelopeSpec,
    Study,
    StudyError,
    default_study,
    load_study,
    write_study,
)
from cfd_traj.engine.bands import Band, BandSet, build_bands
from cfd_traj.engine.coverage import CoverageResult, Offender, check_coverage
from cfd_traj.engine.doe import DoeNode, DoePlan, PlanTooLarge, build_plan
from cfd_traj.engine.envelope import BandEnvelope, Envelope, VariableEnvelope, build_envelope
from cfd_traj.engine.inspect import ColumnStats, Inspection, inspect

__version__ = "1.0.0"

__all__ = [
    "Band",
    "BandEnvelope",
    "BandSet",
    "BandSpec",
    "Bounds",
    "CalcConfig",
    "ColumnSpec",
    "ColumnStats",
    "CoverageResult",
    "DatasetError",
    "DeflectionSet",
    "DeflectionSymmetry",
    "DoeMethod",
    "DoeNode",
    "DoePlan",
    "DoeSpec",
    "Envelope",
    "EnvelopeSpec",
    "FlowState",
    "Inspection",
    "Offender",
    "PcaResult",
    "PlanTooLarge",
    "Reference",
    "Role",
    "Scale",
    "Shot",
    "Study",
    "StudyError",
    "SymmetryGroup",
    "SymmetrySpec",
    "TrajectoryDataset",
    "VariableEnvelope",
    "add_derived_columns",
    "azimuth_levels",
    "build_bands",
    "build_envelope",
    "build_plan",
    "build_specs",
    "calc_config",
    "check_coverage",
    "classify_deflection",
    "corner_points",
    "default_study",
    "detect_role",
    "flow_state",
    "fold_phi",
    "from_aeroballistic",
    "inspect",
    "load_dataset",
    "load_study",
    "maximin_lhs",
    "nondimensionalise",
    "pca",
    "place_levels",
    "quantile_bounds",
    "to_aeroballistic",
    "write_study",
    "zero_components",
]
