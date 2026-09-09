"""Le rendu terminal d'un parcours par point de vol : plan, progression, bilan.

Les deux parcours du paquet — :func:`~cfd_dispersion.figures_tirage_par_pdv` et
:func:`~cfd_dispersion.figures_histogramme_par_pdv` — écrivent des centaines de
fichiers dans une arborescence profonde. Sans rien dire, ils passent plusieurs
minutes muets puis rendent un tableau : on ne sait ni ce qui va être fait, ni où
en est le travail, ni ce qui a été écrit.

``cfd_plot.batch_plot`` a résolu exactement ce problème, et ces parcours lui
reprennent déjà ses conventions — la forme du ``flight_point_dict``, un dossier
par clé qui varie. Ils lui reprennent donc aussi son rendu, et ses trois
arguments :

============  =======================  =================================
batch_plot    ici                      ce que cela fait
============  =======================  =================================
``verbose``   ``verbeux``              le plan avant, la barre pendant
``report``    ``rapport``              le bilan des fichiers écrits, après
``dry_run``   ``a_blanc``              énumère sans rien écrire
============  =======================  =================================

Les fonctions **impriment** plutôt que de rendre un objet Rich, contrairement à
:mod:`cfd_dispersion.report.console` : un parcours est une commande, pas une
valeur, et son plan doit paraître *avant* que le travail commence.

Rich est optionnel ici comme ailleurs : sans lui, tout retombe sur des lignes
de texte qui portent la même information.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from . import theme

try:  # pragma: no cover - dépend de l'installation
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )
    from rich.table import Table

    _RICH = True
except ImportError:  # pragma: no cover - Rich absent
    _RICH = False
    Console = None  # type: ignore[misc, assignment]
    Panel = None  # type: ignore[misc, assignment]
    Progress = None  # type: ignore[misc, assignment]
    Table = None  # type: ignore[misc, assignment]

__all__ = [
    "colonnes_progression",
    "imprimer_bilan",
    "imprimer_note",
    "imprimer_plan",
    "progression",
    "resume_valeurs",
]

_console = Console() if _RICH else None

#: Au-delà, les valeurs d'une boucle sont résumées plutôt qu'énumérées.
MAX_VALEURS = 6


def resume_valeurs(valeurs: Sequence[Any], maximum: int = MAX_VALEURS) -> str:
    """``0.7, 0.85`` — ou ``0.7, 0.75, … (+8)`` quand la liste est longue."""
    ecrites = [f"{valeur:g}" if isinstance(valeur, float) else str(valeur) for valeur in valeurs]
    if len(ecrites) <= maximum:
        return ", ".join(ecrites)
    tete = ", ".join(ecrites[: maximum - 1])
    return f"{tete}, … (+{len(ecrites) - (maximum - 1)})"


def imprimer_plan(
    *,
    titre: str,
    apercu: Sequence[tuple[str, str]],
    specs: Mapping[str, Mapping[str, Any]],
    par_point: Sequence[tuple[str, int, int]] = (),
    entete_par_point: tuple[str, str, str] = ("point de vol", "tirages", "figures"),
) -> None:
    """Le plan du parcours, avant qu'il commence.

    Parameters
    ----------
    titre:
        Le titre du panneau.
    apercu:
        ``(libellé, valeur)`` — les lignes du panneau, dans l'ordre.
    specs:
        Les points de vol normalisés, pour la table des boucles.
    par_point:
        ``(étiquette, effectif, figures)`` par point de vol retenu.
    entete_par_point:
        Les trois en-têtes de cette dernière table, qui ne disent pas la même
        chose d'un parcours à l'autre.
    """
    largeur = max((len(libelle) for libelle, _ in apercu), default=0)
    lignes = [f"{libelle.ljust(largeur)} : {valeur}" for libelle, valeur in apercu]

    if _RICH and _console is not None:
        _console.print(Panel("\n".join(lignes), title=titre, border_style=theme.TITRE))
        _console.print(_table_boucles(specs))
        if par_point:
            _console.print(_table_par_point(par_point, entete_par_point))
        return

    print(f"=== {titre} ===")
    for ligne in lignes:
        print(ligne)
    print("\nBoucles de points de vol :")
    for cle, spec in specs.items():
        valeurs = spec.get("values", [])
        print(f"  {cle}: n={len(valeurs)}  [{resume_valeurs(valeurs)}]")
    if par_point:
        print(f"\n{entete_par_point[0]} :")
        for etiquette, effectif, figures in par_point:
            print(f"  {etiquette}: {effectif} {entete_par_point[1]}, {figures} figures")


def _table_boucles(specs: Mapping[str, Mapping[str, Any]]) -> Any:
    """La table des clés de point de vol et de leurs valeurs."""
    table = Table(
        title="Boucles de points de vol", title_style=theme.TITRE, header_style=theme.ENTETE
    )
    table.add_column("colonne")
    table.add_column("n", justify="right", style=theme.ENTETE_ALT)
    table.add_column("valeurs")
    for cle, spec in specs.items():
        valeurs = list(spec.get("values", []))
        libelle = spec.get("label", cle)
        unite = str(spec.get("unit", "")).strip()
        nom = f"{cle}  [{libelle}{f' ({unite})' if unite else ''}]"
        table.add_row(nom, str(len(valeurs)), resume_valeurs(valeurs))
    return table


def _table_par_point(
    par_point: Sequence[tuple[str, int, int]],
    entete: tuple[str, str, str],
) -> Any:
    """La table des figures attendues, point de vol par point de vol."""
    table = Table(
        title="Figures par point de vol", title_style=theme.TITRE, header_style=theme.ENTETE
    )
    table.add_column(entete[0])
    table.add_column(entete[1], justify="right", style=theme.ENTETE_ALT)
    table.add_column(entete[2], justify="right", style=theme.ACCENT)
    for etiquette, effectif, figures in par_point:
        table.add_row(etiquette, str(effectif), str(figures))
    return table


def colonnes_progression() -> list[Any]:
    """Les colonnes de la barre de progression, celles de ``batch_plot``."""
    return [
        SpinnerColumn(),
        TextColumn(f"[{theme.TITRE}]{{task.description}}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TextColumn("reste"),
        TimeRemainingColumn(),
    ]


def progression(total: int) -> Any:
    """Une barre de progression prête à l'emploi, ou None sans Rich.

    Rendue plutôt qu'utilisée ici : le parcours en a besoin autour de sa
    boucle, et cette boucle n'a rien à faire dans un module de rapport.
    """
    if not (_RICH and Progress is not None and _console is not None) or total <= 0:
        return None
    return Progress(*colonnes_progression(), console=_console, transient=False)


def imprimer_bilan(
    inventaire: pd.DataFrame,
    *,
    cles_pdv: Sequence[str],
    colonne_groupe: str | None,
    titre_groupe: str = "tirage",
    racine: Any = None,
    a_blanc: bool = False,
    specs: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    """Le bilan des fichiers écrits, groupé par point de vol.

    Un listing à plat répète le même ``CN.svg`` une fois par point de vol et
    par tirage, ce qui les rend indiscernables — c'est la raison pour laquelle
    ``batch_plot`` groupe le sien, et celle pour laquelle celui-ci l'est aussi.

    *colonne_groupe* est la colonne qui distingue encore deux lignes dans un
    même point de vol : le numéro de tirage pour le parcours des tirages, rien
    pour celui des histogrammes, qui n'écrit qu'un jeu de figures par point.

    *specs* sert à nommer les points de vol comme le plan et les titres de
    figure les nomment — ``M = 0.85 · Z = 10000 m`` et non ``Mach = 0.85`` —
    pour qu'on retrouve dans le bilan ce qu'on a lu dans le plan.
    """
    if inventaire.empty:
        _note("aucune figure : aucun point de vol demandé n'a de ligne à tracer")
        return

    cles = [cle for cle in cles_pdv if cle in inventaire.columns]
    groupes = inventaire.groupby(cles, sort=False) if cles else [((), inventaire)]

    for valeurs, lignes in groupes:
        etiquette = _etiquette(cles, valeurs, specs)
        titre = f"{etiquette}  —  {len(lignes)} fichier(s)"
        if a_blanc:
            titre = f"{titre}  (à blanc)"
        if _RICH and _console is not None:
            _console.print(_table_bilan(lignes, colonne_groupe, titre_groupe, titre, a_blanc))
        else:
            print(f"\n{titre}")
            for fichier in lignes["fichier"]:
                print(f"    {fichier}")

    if racine is not None:
        _note(f"arborescence : {racine}")


def _table_bilan(
    lignes: pd.DataFrame,
    colonne_groupe: str | None,
    titre_groupe: str,
    titre: str,
    a_blanc: bool,
) -> Any:
    """Une table de bilan pour un point de vol."""
    table = Table(title=titre, title_style=theme.TITRE, header_style=theme.ENTETE)
    if colonne_groupe is not None and colonne_groupe in lignes.columns:
        table.add_column(titre_groupe, justify="right")
    table.add_column("figure")
    table.add_column("format", style=theme.ENTETE_ALT)
    table.add_column("taille", justify="right", style=theme.ACCENT)

    for _, ligne in lignes.iterrows():
        chemin = Path(str(ligne["fichier"]))
        cellules = []
        if colonne_groupe is not None and colonne_groupe in lignes.columns:
            cellules.append(str(ligne[colonne_groupe]))
        cellules.append(str(ligne["figure"]))
        cellules.append(chemin.suffix.lstrip(".").upper())
        cellules.append("—" if a_blanc else _taille(chemin))
        table.add_row(*cellules)
    return table


def _taille(chemin: Path) -> str:
    """La taille d'un fichier écrit, en kilo-octets."""
    try:
        return f"{chemin.stat().st_size / 1024:.1f} ko"
    except OSError:  # pragma: no cover - fichier disparu entre-temps
        return "—"


def _etiquette(
    cles: Sequence[str],
    valeurs: Any,
    specs: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    """``M = 0.85 · Z = 10000 m``, depuis une clé de groupby."""
    if not cles:
        return "(point de vol unique)"
    brutes = valeurs if isinstance(valeurs, tuple) else (valeurs,)
    morceaux = []
    for cle, valeur in zip(cles, brutes):
        spec = (specs or {}).get(cle, {})
        libelle = str(spec.get("label", cle))
        unite = str(spec.get("unit", ""))
        ecrite = f"{valeur:g}" if isinstance(valeur, float) else str(valeur)
        morceaux.append(f"{libelle} = {ecrite}{unite}")
    return " · ".join(morceaux)


def imprimer_note(texte: str, *, style: str = theme.DISCRET) -> None:
    """Une ligne de commentaire — nettoyage, repli en séquence, refus."""
    if _RICH and _console is not None:
        _console.print(f"[{style}]{texte}[/]")
    else:
        print(texte)


def _note(texte: str) -> None:
    imprimer_note(texte)
