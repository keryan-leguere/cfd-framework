"""Façade du test des bornes de table : calcul, rapport, pièces.

    from cfd_validation import TableReference, valider_bornes_tables

    res = valider_bornes_tables(
        [TableReference("CX", modele.lire("aertab.tcx"),
                        {"mach": modele.lire("aertab.tmach"), "alpha": modele.lire("aertab.talpha")},
                        sonde="valid_tab_cx", bornes={"mach": "sature", "alpha": "extrapole"})],
        evaluer=modele.calculer_df,
        defauts={"mach": 0.8, "alpha": 0.0, ...},
        sortie="BORNES_TABLES",
    )

Pièces dans ``sortie`` :

- ``RESULTATS/<NOM>.csv`` : un appel par ligne — face, point, consigne, colonnes
  de la table, entrées injectées, ``valeur_ATTENDUE``, ``valeur_SATURATION``,
  ``valeur_EXTRAPOLATION``, ``valeur_CODE``, ``ecart``, ``ulp``, ``marge``,
  ``statut``, ``conforme`` ;
- ``FIGURES/synthese_bornes*.svg`` (cfd-plot ; ``formats=`` pour PNG/PDF) ;
- ``resume.json`` ; ``bornes_tables.log``, le rapport complet, écrit en dernier
  avec le SHA-256 de chaque autre pièce.
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from rich.console import Console

from cfd_validation.core.bornes import SATURE
from cfd_validation.data.tables import TableReference
from cfd_validation.engine.bornes_tables import (
    ECART_DEFAUT,
    IDENTIFIANT_DEFAUT,
    ResultatBornesTables,
    verifier_bornes,
)
from cfd_validation.engine.lecture_tables import Evaluateur
from cfd_validation.integration import _vider
from cfd_validation.report.bornes_tables import ecrire_journal_bornes, rendre_bornes_tables
from cfd_validation.report.console import rendre_fichiers
from cfd_validation.report.figures import FiguresIndisponibles, _fichier
from cfd_validation.report.figures_bornes import tracer_figures_bornes
from cfd_validation.report.figures_tables import FORMATS_TABLES
from cfd_validation.report.lecture_tables import LIGNES_MAX_TERMINAL

__all__ = ["NOM_JOURNAL", "valider_bornes_tables"]

NOM_JOURNAL = "bornes_tables.log"


def valider_bornes_tables(
    tables: Sequence[TableReference],
    evaluer: Evaluateur,
    defauts: Mapping[str, Any],
    *,
    ecart: float = ECART_DEFAUT,
    ecarts: Mapping[str, float] | None = None,
    consigne_defaut: str = SATURE,
    identifiant: str = IDENTIFIANT_DEFAUT,
    description: str | None = None,
    metadonnees: Mapping[str, Any] | None = None,
    sortie: str | Path | None = "BORNES_TABLES",
    figures: bool = True,
    formats: Sequence[str] = FORMATS_TABLES,
    afficher: bool = True,
    console: Console | None = None,
    lignes_max: int | None = LIGNES_MAX_TERMINAL,
    nettoyer: bool = False,
) -> ResultatBornesTables:
    """Appelle le code au-delà des bornes de chaque table et vérifie la consigne de chaque face.

    Parameters
    ----------
    tables
        Les :class:`TableReference` ; leur ``bornes`` donne la consigne de chaque
        axe (``sature``, ``extrapole``, ``inatteignable``), par côté au besoin.
    evaluer, defauts
        Comme pour :func:`valider_lecture_tables`.
    ecart, ecarts
        Distance des points hors bornes, en fraction de l'étendue de l'axe
        (0.10 par défaut) ; ``ecarts`` l'ajuste par nom d'axe.
    consigne_defaut
        Consigne d'un axe que la table ne déclare pas ; marquée « défaut » au rapport.
    identifiant, description, metadonnees, sortie, figures, formats, afficher, console, lignes_max, nettoyer
        Comme pour :func:`valider_lecture_tables`.
    """
    res = verifier_bornes(
        tables, evaluer, defauts, ecart=ecart, ecarts=ecarts, consigne_defaut=consigne_defaut,
        identifiant=identifiant, description=description, metadonnees=metadonnees,
    )
    console = console or Console(highlight=False)
    if afficher:
        rendre_bornes_tables(console, res, lignes_max=lignes_max)
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
    if figures:
        try:
            pieces += tracer_figures_bornes(res, dossier / "FIGURES", formats=formats)
        except FiguresIndisponibles as erreur:
            warnings.warn(str(erreur), stacklevel=2)
            if afficher:
                console.print(f"[yellow]{erreur}[/] — rapport, journal et CSV sont écrits quand même.")

    resume = dossier / "resume.json"
    journal = dossier / NOM_JOURNAL
    res = replace(res, fichiers=(*pieces, resume, journal))
    resume.write_text(json.dumps(res.resume(), ensure_ascii=False, indent=2), encoding="utf-8")
    ecrire_journal_bornes(res, journal, pieces=[*pieces, resume], racine=dossier)
    if afficher:
        rendre_fichiers(console, res.fichiers, racine=dossier)
    return res
