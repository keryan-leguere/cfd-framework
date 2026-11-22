"""cfd-validation — utilitaires de vérification de code (Fortran 77, C), tracés et documentés.

Premier contrôle : le **test d'intégration**. Le même code, exécuté dans deux
environnements, produit-il les mêmes sorties ? ::

    from cfd_validation import valider_integration

    resultat = valider_integration(
        reference, test,
        entrees=["Mach", "alpha", "beta"],
        sorties=["CN", "CA", "Cm"],
        tolerances={"Cm": {"rtol": 1e-6, "justification": "sommation réordonnée"}},
        sortie="VALIDATION_INTEGRATION",
    )
    resultat.conforme

Deuxième contrôle : le **test de lecture de table**. Le code, appelé sur chaque
nœud de chaque table, rend-il la valeur de la table ? ::

    from cfd_validation import TableReference, valider_lecture_tables

    res = valider_lecture_tables(tables, evaluer=modele.calcul_aero_elementaire, defauts={...})

Troisième contrôle : le **test des bornes de table**. Appelé au-delà des bornes,
le code sature-t-il ou extrapole-t-il comme la consigne de chaque axe le demande ? ::

    from cfd_validation import valider_bornes_tables

    res = valider_bornes_tables(tables, evaluer=modele.calcul_aero_elementaire, defauts={...})

Quatrième contrôle : le **test d'interpolation de table**. Entre les nœuds, le
code rend-il l'interpolation multilinéaire de la table ? Il trace aussi les
**polaires** (``cfd_plot.batch_plot``), qui montrent les trois tests de table
d'un coup d'œil ::

    from cfd_validation import valider_interpolation_tables
    res = valider_interpolation_tables(tables, evaluer=modele.calcul_aero_elementaire, defauts={...})
"""

from __future__ import annotations

__version__ = "0.1.0"

from cfd_validation.core.tolerance import Tolerance
from cfd_validation.data.specification import (
    ErreurSpecification,
    Specification,
    construire_specification,
)
from cfd_validation.engine.integration import ResultatIntegration, comparer
from cfd_validation.bornes_tables import valider_bornes_tables
from cfd_validation.data.tables import ErreurTable, TableReference
from cfd_validation.engine.bornes_tables import BilanBornes, ResultatBornesTables, verifier_bornes
from cfd_validation.engine.lecture_tables import BilanTable, ResultatLectureTables, relire_tables
from cfd_validation.data.polaires import Polaires
from cfd_validation.engine.interpolation_tables import (
    BilanInterpolation,
    ResultatInterpolationTables,
    verifier_interpolation,
)
from cfd_validation.integration import valider_integration
from cfd_validation.interpolation_tables import valider_interpolation_tables
from cfd_validation.lecture_tables import valider_lecture_tables
from cfd_validation.polaires import tracer_polaires_tables

__all__ = [
    "__version__",
    "BilanBornes",
    "BilanInterpolation",
    "BilanTable",
    "ErreurSpecification",
    "ErreurTable",
    "ResultatBornesTables",
    "Polaires",
    "ResultatIntegration",
    "ResultatInterpolationTables",
    "ResultatLectureTables",
    "Specification",
    "TableReference",
    "Tolerance",
    "comparer",
    "construire_specification",
    "relire_tables",
    "tracer_polaires_tables",
    "valider_bornes_tables",
    "valider_integration",
    "valider_interpolation_tables",
    "valider_lecture_tables",
    "verifier_bornes",
    "verifier_interpolation",
]
