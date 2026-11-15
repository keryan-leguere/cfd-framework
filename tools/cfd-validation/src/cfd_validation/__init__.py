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
from cfd_validation.integration import valider_integration

__all__ = [
    "__version__",
    "ErreurSpecification",
    "ResultatIntegration",
    "Specification",
    "Tolerance",
    "comparer",
    "construire_specification",
    "valider_integration",
]
