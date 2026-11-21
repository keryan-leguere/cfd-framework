"""Façade du test de lecture de table : calcul, rapport, pièces.

    from cfd_validation import TableReference, valider_lecture_tables

    res = valider_lecture_tables(
        [TableReference("CX", modele.lire("aertab.tcx"),
                        {"mach": modele.lire("aertab.tmach"), "alpha": modele.lire("aertab.talpha")},
                        sonde="valid_tab_cx")],
        evaluer=modele.calculer_df,
        defauts={"mach": 0.8, "alpha": 0.0, "beta": 0.0, ...},
        sortie="LECTURE_TABLES",
    )
    res.conforme

Pièces dans ``sortie`` :

- ``TABLES/<NOM>.csv`` : chaque table de référence à plat (axes, ``valeur``), en ordre de lecture ;
- ``RESULTATS/<NOM>.csv`` : un appel par ligne — nœud, combinaison, colonnes de
  la table, entrées injectées, ``valeur_TAB``, ``valeur_CODE``, ``ecart``,
  ``ulp``, ``marge``, ``statut``, ``conforme`` ;
- ``FIGURES/synthese_tables*.svg`` (cfd-plot ; ``formats=`` pour PNG/PDF) ;
- ``resume.json`` ; ``lecture_tables.log``, le rapport complet, écrit en dernier
  avec le SHA-256 de chaque autre pièce.
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from rich.console import Console

from cfd_validation.data.tables import TableReference
from cfd_validation.engine.lecture_tables import (
    IDENTIFIANT_DEFAUT,
    Evaluateur,
    ResultatLectureTables,
    relire_tables,
)
from cfd_validation.integration import _vider
from cfd_validation.report.console import rendre_fichiers
from cfd_validation.report.figures import FiguresIndisponibles, _fichier
from cfd_validation.report.figures_tables import FORMATS_TABLES, tracer_figures_tables
from cfd_validation.report.lecture_tables import (
    LIGNES_MAX_TERMINAL,
    ecrire_journal_tables,
    rendre_lecture_tables,
)

__all__ = ["NOM_JOURNAL", "valider_lecture_tables"]

NOM_JOURNAL = "lecture_tables.log"


def valider_lecture_tables(
    tables: Sequence[TableReference],
    evaluer: Evaluateur,
    defauts: Mapping[str, Any],
    *,
    combinaisons: Mapping[str, Iterable[Any]] | None = None,
    identifiant: str = IDENTIFIANT_DEFAUT,
    description: str | None = None,
    metadonnees: Mapping[str, Any] | None = None,
    sortie: str | Path | None = "LECTURE_TABLES",
    figures: bool = True,
    formats: Sequence[str] = FORMATS_TABLES,
    afficher: bool = True,
    console: Console | None = None,
    lignes_max: int | None = LIGNES_MAX_TERMINAL,
    nettoyer: bool = False,
) -> ResultatLectureTables:
    """Appelle le code sur chaque nœud de chaque table et compare à la table.

    Parameters
    ----------
    tables
        Les :class:`TableReference` à relire.
    evaluer
        ``f(df) -> df`` : un point d'entrée du modèle par ligne (colonnes = les
        clés de ``defauts``), rendu dans le même ordre avec la colonne de sonde
        de chaque table. Pour un code f2py : ``ModeleF2py.calculer_df``.
    defauts
        La valeur de **chaque** entrée du modèle hors colonnes de la table ;
        ses clés sont la liste des entrées.
    combinaisons
        ``{entrée: valeurs}`` : rejouer chaque nœud pour toutes les combinaisons
        de ces valeurs (entrées non pilotées par la table ni fixées), pour
        vérifier que la lecture n'en dépend pas.
    identifiant, description, metadonnees
        Traçabilité : l'exigence vérifiée, et ce qui identifie le code (version,
        compilateur, options…), repris en tête du rapport.
    sortie
        Dossier des pièces ; ``None`` n'écrit rien.
    figures, formats
        Figure de synthèse (cfd-plot requis), et ses formats : SVG seul par défaut.
    afficher, console, lignes_max
        Rapport au terminal ; ``lignes_max`` points en échec par table au plus.
    nettoyer
        Vider ``sortie`` avant d'écrire.
    """
    res = relire_tables(
        tables, evaluer, defauts, combinaisons=combinaisons,
        identifiant=identifiant, description=description, metadonnees=metadonnees,
    )
    console = console or Console(highlight=False)
    if afficher:
        rendre_lecture_tables(console, res, lignes_max=lignes_max)
    if sortie is None:
        return res

    dossier = Path(sortie)
    if nettoyer and dossier.exists():
        _vider(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    pieces: list[Path] = []
    for sous, quoi in (("TABLES", "table"), ("RESULTATS", "resultats")):
        (dossier / sous).mkdir(exist_ok=True)
        for b in res.tables:
            chemin = dossier / sous / f"{_fichier(b.nom)}.csv"
            df = b.table.table_plate() if quoi == "table" else b.resultats
            df.to_csv(chemin, index=False, float_format="%.17g")
            pieces.append(chemin)
    if figures:
        try:
            pieces += tracer_figures_tables(res, dossier / "FIGURES", formats=formats)
        except FiguresIndisponibles as erreur:
            warnings.warn(str(erreur), stacklevel=2)
            if afficher:
                console.print(f"[yellow]{erreur}[/] — rapport, journal et CSV sont écrits quand même.")

    resume = dossier / "resume.json"
    journal = dossier / NOM_JOURNAL
    res = replace(res, fichiers=(*pieces, resume, journal))
    resume.write_text(json.dumps(res.resume(), ensure_ascii=False, indent=2), encoding="utf-8")
    ecrire_journal_tables(res, journal, pieces=[*pieces, resume], racine=dossier)
    if afficher:
        rendre_fichiers(console, res.fichiers, racine=dossier)
    return res
