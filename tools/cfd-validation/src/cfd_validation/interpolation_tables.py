"""Façade du test d'interpolation de table : calcul, polaires, rapport, pièces.

    from cfd_validation import Polaires, valider_interpolation_tables

    res = valider_interpolation_tables(
        tables, evaluer=modele.calculer_df, defauts={...},
        polaires={"DCMG": Polaires(abscisses=["alphat"], noeuds={"mach": [1.0]})},
        libelles={"alpha": ("α", "°")},
        sortie="INTERPOLATION_TABLES",
    )

Pièces dans ``sortie`` :

- ``RESULTATS/<NOM>.csv`` : un appel par ligne — groupe, point, maille (base 1,
  comme le Fortran), fraction, colonnes de la table, entrées injectées,
  ``valeur_ATTENDUE``, ``valeur_CODE``, ``ecart``, ``ulp``, ``marge``,
  ``statut``, ``conforme`` ;
- ``POLAIRES/<NOM>/POLAIRE_<AXE>/…`` : les polaires (``cfd_plot.batch_plot``, SVG),
  et leurs superpositions sous ``SUPERPOSITION/`` ;
- ``resume.json`` ; ``interpolation_tables.log``, le rapport complet, écrit en
  dernier avec le SHA-256 de chaque autre pièce.
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from rich.console import Console

from cfd_validation.data.polaires import COURBES_MAX, Polaires
from cfd_validation.data.tables import TableReference
from cfd_validation.engine.interpolation_tables import (
    FRACTIONS_DEFAUT,
    IDENTIFIANT_DEFAUT,
    ResultatInterpolationTables,
    verifier_interpolation,
)
from cfd_validation.engine.lecture_tables import Evaluateur
from cfd_validation.engine.polaires import Polaire, calculer_polaires
from cfd_validation.integration import _vider
from cfd_validation.report.console import rendre_fichiers
from cfd_validation.report.figures import FiguresIndisponibles, _fichier
from cfd_validation.report.figures_polaires import Libelles, tracer_polaires
from cfd_validation.report.figures_tables import FORMATS_TABLES
from cfd_validation.report.interpolation_tables import (
    ecrire_journal_interpolation,
    rendre_interpolation_tables,
)
from cfd_validation.report.lecture_tables import LIGNES_MAX_TERMINAL

__all__ = ["NOM_JOURNAL", "valider_interpolation_tables"]

NOM_JOURNAL = "interpolation_tables.log"


def valider_interpolation_tables(
    tables: Sequence[TableReference],
    evaluer: Evaluateur,
    defauts: Mapping[str, Any],
    *,
    fractions: Sequence[float] = FRACTIONS_DEFAUT,
    centres: bool = True,
    polaires: Mapping[str, Polaires] | None = None,
    libelles: Libelles | None = None,
    ecart: float = 0.10,
    superposer: bool = True,
    courbes_max: int = COURBES_MAX,
    n_jobs: int = 1,
    identifiant: str = IDENTIFIANT_DEFAUT,
    description: str | None = None,
    metadonnees: Mapping[str, Any] | None = None,
    sortie: str | Path | None = "INTERPOLATION_TABLES",
    figures: bool = True,
    formats: Sequence[str] = FORMATS_TABLES,
    afficher: bool = True,
    console: Console | None = None,
    lignes_max: int | None = LIGNES_MAX_TERMINAL,
    nettoyer: bool = False,
) -> ResultatInterpolationTables:
    """Appelle le code entre les nœuds de chaque table, vérifie l'interpolation, trace les polaires.

    Parameters
    ----------
    tables, evaluer, defauts
        Comme pour :func:`valider_lecture_tables`.
    fractions
        Positions des points dans chaque maille, pour les groupes par axe (¼, ½, ¾).
    centres
        Ajoute le groupe des centres de maille (couplage entre axes).
    polaires, libelles, ecart, superposer, courbes_max, n_jobs
        Les polaires (voir :func:`tracer_polaires_tables`) ; tracées si ``figures``.
        ``ecart`` est leur prolongement au-delà des bornes.
    identifiant, description, metadonnees, sortie, figures, formats, afficher, console, lignes_max, nettoyer
        Comme pour :func:`valider_lecture_tables`.
    """
    res = verifier_interpolation(
        tables, evaluer, defauts, fractions=fractions, centres=centres,
        identifiant=identifiant, description=description, metadonnees=metadonnees,
    )
    calculees: tuple[Polaire, ...] = ()
    if figures and sortie is not None:
        calculees = calculer_polaires(tables, evaluer, defauts, polaires, ecart=ecart, courbes_max=courbes_max)
    console = console or Console(highlight=False)
    if afficher:
        rendre_interpolation_tables(console, res, polaires=calculees, lignes_max=lignes_max)
    if sortie is None:
        return res

    dossier = Path(sortie)
    if nettoyer and dossier.exists():
        _vider(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    pieces: list[Path] = []
    (dossier / "RESULTATS").mkdir(exist_ok=True)
    for b in res.tables:
        chemin = dossier / "RESULTATS" / f"{_fichier(b.nom)}.csv"
        b.resultats.to_csv(chemin, index=False, float_format="%.17g")
        pieces.append(chemin)
    if calculees:
        try:
            pieces += tracer_polaires(calculees, dossier / "POLAIRES", libelles=libelles, superposer=superposer,
                                      formats=formats, n_jobs=n_jobs)
        except FiguresIndisponibles as erreur:
            warnings.warn(str(erreur), stacklevel=2)
            if afficher:
                console.print(f"[yellow]{erreur}[/] — rapport, journal et CSV sont écrits quand même.")

    resume = dossier / "resume.json"
    journal = dossier / NOM_JOURNAL
    res = replace(res, fichiers=(*pieces, resume, journal))
    contenu = res.resume()
    contenu["polaires"] = [
        {"table": p.nom, "abscisse": p.axe, "conditions": list(p.conditions), "courbes": p.n_courbes,
         "superpose": p.superpose, "appels": p.n_appels, "prolongements": list(p.prolongements)}
        for p in calculees
    ]
    resume.write_text(json.dumps(contenu, ensure_ascii=False, indent=2), encoding="utf-8")
    ecrire_journal_interpolation(res, journal, polaires=calculees, pieces=[*pieces, resume], racine=dossier)
    if afficher:
        # Au terminal, les polaires se résument : une centaine de SVG noierait le reste (le journal les liste).
        figures_polaires = [f for f in res.fichiers if dossier / "POLAIRES" in f.parents]
        rendre_fichiers(console, [f for f in res.fichiers if f not in figures_polaires], racine=dossier)
        if figures_polaires:
            console.print(f"  POLAIRES/ : {len(figures_polaires)} figures "
                          f"({len(calculees)} polaires, {len({p.nom for p in calculees})} tables)")
    return res
