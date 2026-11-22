"""Façade des polaires de table : la courbe du code le long de chaque axe, les nœuds par-dessus.

    from cfd_validation import Polaires, tracer_polaires_tables

    fichiers = tracer_polaires_tables(
        tables, evaluer=modele.calcul_aero_elementaire, defauts={...}, sortie="POLAIRES",
        polaires={"DCMG": Polaires(abscisses=["alphat"], noeuds={"mach": [1.0], "dn": [0.0]})},
        libelles={"alpha": ("α", "°")},
    )

Le test d'interpolation les trace aussi (``valider_interpolation_tables``) ;
cette fonction sert à les obtenir seules, sans verdict.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from cfd_validation.data.polaires import COURBES_MAX, Polaires
from cfd_validation.data.tables import TableReference
from cfd_validation.engine.lecture_tables import Evaluateur
from cfd_validation.engine.polaires import calculer_polaires
from cfd_validation.report.figures_polaires import Libelles, tracer_polaires
from cfd_validation.report.figures_tables import FORMATS_TABLES

__all__ = ["tracer_polaires_tables"]


def tracer_polaires_tables(
    tables: Sequence[TableReference],
    evaluer: Evaluateur,
    defauts: Mapping[str, Any],
    sortie: str | Path,
    *,
    polaires: Mapping[str, Polaires] | None = None,
    libelles: Libelles | None = None,
    ecart: float = 0.10,
    superposer: bool = True,
    courbes_max: int = COURBES_MAX,
    formats: Sequence[str] = FORMATS_TABLES,
    n_jobs: int = 1,
) -> list[Path]:
    """Appelle le code le long de chaque axe et trace les polaires sous ``sortie/<TABLE>/``.

    ``polaires`` : par nom de table, les abscisses et les nœuds retenus (défaut :
    tous) ; ``libelles`` : nom affiché et unité de chaque axe ou table ;
    ``ecart`` : prolongement au-delà des bornes, en fraction de l'étendue ;
    ``superposer`` : ajoute la figure de toutes les conditions d'un axe
    (``fold`` « overlay » de ``batch_plot``) ; ``n_jobs`` : processus de tracé.
    """
    calculees = calculer_polaires(tables, evaluer, defauts, polaires, ecart=ecart, courbes_max=courbes_max)
    return tracer_polaires(calculees, sortie, libelles=libelles, superposer=superposer, formats=formats, n_jobs=n_jobs)
