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

    res = valider_lecture_tables(tables, evaluer=modele.calculer_df, defauts={...})
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
from cfd_validation.data.tables import ErreurTable, TableReference
from cfd_validation.engine.lecture_tables import BilanTable, ResultatLectureTables, relire_tables
from cfd_validation.integration import valider_integration
from cfd_validation.lecture_tables import valider_lecture_tables

__all__ = [
    "__version__",
    "BilanTable",
    "ErreurSpecification",
    "ErreurTable",
    "ResultatIntegration",
    "ResultatLectureTables",
    "Specification",
    "TableReference",
    "Tolerance",
    "comparer",
    "construire_specification",
    "relire_tables",
    "valider_integration",
    "valider_lecture_tables",
]
