"""Le test d'intégration de bout en bout : comparer, afficher, archiver.

:func:`valider_integration` est la fonction qu'on appelle. Elle enchaîne

1. :func:`cfd_validation.engine.integration.comparer` — le calcul ;
2. le rapport au terminal (lignes en échec seulement) ;
3. les pièces, dans le dossier ``sortie`` ::

       sortie/
       ├── integration.log       le rapport complet, toutes les lignes, en texte
       ├── resume.json           verdict, bilans et paramètres, pour une chaîne qui agrège
       ├── lignes.csv            une ligne par cas : statut, sortie la pire, marge
       ├── ecarts.csv            une ligne par (cas × sortie) : réf, test, Δ, ULP, marge
       └── FIGURES/              figures cfd-plot, PNG 300 dpi + PDF

Le journal est écrit en dernier : il liste les autres pièces avec leur
SHA-256, de sorte qu'une figure jointe à un rapport se rattache à cette
exécution et pas à une autre.
"""

from __future__ import annotations

import json
import shutil
import warnings
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd
from rich.console import Console

from cfd_validation.data.specification import (
    Specification,
    SpecTolerance,
    construire_specification,
)
from cfd_validation.engine.integration import IDENTIFIANT_DEFAUT, ResultatIntegration, comparer
from cfd_validation.report.console import LIGNES_MAX_TERMINAL, rendre_fichiers, rendre_integration
from cfd_validation.report.figures import FORMATS, FiguresIndisponibles, tracer_figures
from cfd_validation.report.journal import ecrire_journal

__all__ = ["NOM_JOURNAL", "valider_integration"]

NOM_JOURNAL = "integration.log"


def valider_integration(
    reference: pd.DataFrame,
    test: pd.DataFrame,
    entrees: str | Iterable[str] | None = None,
    sorties: str | Iterable[str] | None = None,
    *,
    specification: Specification | None = None,
    tolerances: Mapping[str, SpecTolerance] | None = None,
    rtol: float | None = None,
    atol: float | None = None,
    justification: str | None = None,
    alignement: str | None = None,
    chiffres_cle: int | None = None,
    renommage_test: Mapping[str, str] | None = None,
    identifiant: str = IDENTIFIANT_DEFAUT,
    description: str | None = None,
    metadonnees: Mapping[str, Any] | None = None,
    sortie: str | Path | None = "VALIDATION_INTEGRATION",
    figures: bool = True,
    formats: Sequence[str] = FORMATS,
    figures_par_entree: str = "echecs",
    afficher: bool = True,
    console: Console | None = None,
    lignes_max: int | None = LIGNES_MAX_TERMINAL,
    nettoyer: bool = False,
) -> ResultatIntegration:
    """Compare ``test`` à ``reference`` ; affiche le rapport et écrit les pièces.

    Parameters
    ----------
    reference, test
        Les deux tables, entrées et sorties en colonnes, une ligne par cas.
    entrees, sorties
        Les colonnes d'entrée (qui identifient un cas) et de sortie (qu'on
        compare). Liste, ou chaîne séparée par des virgules. ``entrees`` peut
        être vide (``None`` ou ``[]``) : les lignes sont alors appariées dans
        l'ordre, la i-ème contre la i-ème.
    specification
        Une :class:`Specification` déjà construite, à la place des arguments
        ``entrees`` … ``renommage_test``.
    tolerances
        Tolérance propre à certaines sorties :
        ``{"Cm": {"rtol": 1e-6, "atol": 1e-10, "justification": "…"}}``.
    rtol, atol, justification
        Tolérance commune des autres sorties (défaut : ``1e-9``, ``1e-12``,
        signalée comme non justifiée).
    alignement
        ``"entrees"`` : apparier les lignes sur leurs entrées (l'ordre peut
        différer ; défaut s'il y a des entrées) ; ``"position"`` : par rang,
        entrées vérifiées (défaut sans entrées).
    chiffres_cle
        Arrondir les entrées à ce nombre de chiffres significatifs avant appariement.
    renommage_test
        ``{nom dans le test: nom dans la référence}``.
    identifiant, description, metadonnees
        Traçabilité : l'exigence vérifiée et ce qui identifie le code testé
        (version, commit, compilateur, options…), repris en tête de rapport.
    sortie
        Dossier des pièces ; ``None`` n'écrit rien.
    figures, formats
        Tracer les figures (cfd-plot requis), et en quels formats.
    figures_par_entree
        Figures « marge contre chaque entrée », une par sortie : pour les sorties
        en échec (``"echecs"``, défaut), pour ``"toutes"``, ou ``"aucune"``.
    afficher, console, lignes_max
        Rapport au terminal ; ``lignes_max`` plafonne la liste des lignes en
        échec (``None`` : toutes). Le journal, lui, liste toujours tout.
    nettoyer
        Vider ``sortie`` avant d'écrire (sinon les pièces sont remplacées une à une).

    Returns
    -------
    ResultatIntegration
        ``.conforme``, ``.verdict``, les bilans, ``.lignes`` et ``.ecarts``
        (DataFrames), ``.fichiers``.
    """
    if specification is None:
        if sorties is None:
            raise TypeError("sorties est requis (ou specification=)")
        specification = construire_specification(
            entrees,
            sorties,
            tolerances=tolerances,
            rtol=rtol,
            atol=atol,
            justification=justification,
            alignement=alignement,
            chiffres_cle=chiffres_cle,
            renommage_test=renommage_test,
        )
    res = comparer(
        reference,
        test,
        specification,
        identifiant=identifiant,
        description=description,
        metadonnees=metadonnees,
    )
    console = console or Console(highlight=False)
    if afficher:
        rendre_integration(console, res, lignes_max=lignes_max)

    if sortie is None:
        return res

    dossier = Path(sortie)
    if nettoyer and dossier.exists():
        _vider(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    pieces: list[Path] = []
    if figures:
        try:
            pieces += tracer_figures(res, dossier / "FIGURES", formats=formats, par_entree=figures_par_entree)
        except FiguresIndisponibles as erreur:
            warnings.warn(str(erreur), stacklevel=2)
            if afficher:
                console.print(f"[yellow]{erreur}[/] — rapport, journal et CSV sont écrits quand même.")

    lignes_csv = dossier / "lignes.csv"
    res.lignes.to_csv(lignes_csv, index=False)
    ecarts_csv = dossier / "ecarts.csv"
    res.ecarts.to_csv(ecarts_csv, index=False)
    pieces += [lignes_csv, ecarts_csv]

    journal = dossier / NOM_JOURNAL
    resume = dossier / "resume.json"
    res = replace(res, fichiers=(*pieces, resume, journal))
    resume.write_text(json.dumps(res.resume(), ensure_ascii=False, indent=2), encoding="utf-8")
    ecrire_journal(res, journal, pieces=[*pieces, resume], racine=dossier)

    if afficher:
        rendre_fichiers(console, res.fichiers, racine=dossier)
    return res


def _vider(dossier: Path) -> None:
    """Vide un dossier de sortie — et refuse ce qui n'en est manifestement pas un."""
    d = dossier.resolve()
    if d == Path(d.anchor) or d == Path.home() or len(d.parts) < 3 or (d / ".git").exists():
        raise ValueError(f"refus de vider {d} : ce n'est pas un dossier de sortie")
    for enfant in d.iterdir():
        if enfant.is_dir() and not enfant.is_symlink():
            shutil.rmtree(enfant)
        else:
            enfant.unlink()
