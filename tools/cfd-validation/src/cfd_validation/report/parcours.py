"""Le plan avant, le bilan après — pour le parcours des tables et des planches.

Les fonctions **impriment**, contrairement à
:mod:`cfd_validation.report.console` qui rend des objets Rich : un parcours est
une commande, pas une valeur, et son plan doit paraître *avant* que le travail
commence. Deux mille planches se décident avant, pas après.

Les trois arguments sont ceux de ``cfd_plot.batch_plot``, transposés :

============  =======================  =================================
batch_plot    ici                      ce que cela fait
============  =======================  =================================
``verbose``   ``verbeux``              le plan, avant
``report``    ``compte_rendu``         le bilan des fichiers écrits, après
``dry_run``   ``a_blanc``              énumère sans rien écrire
============  =======================  =================================

Rich est **facultatif** ici : sans lui, les mêmes informations sortent en
lignes simples. Le plan est trop utile pour dépendre d'une bibliothèque
d'affichage.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

try:  # pragma: no cover - dépend de l'installation
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    _RICH = True
except ImportError:  # pragma: no cover - Rich absent
    _RICH = False
    Console = None  # type: ignore[misc, assignment]
    Panel = None  # type: ignore[misc, assignment]
    Table = None  # type: ignore[misc, assignment]

from cfd_validation.engine.tables import RapportTables
from cfd_validation.report import theme

__all__ = ["imprimer_bilan", "imprimer_note", "imprimer_plan", "resume_valeurs"]

#: Au-delà, une liste de valeurs est résumée : un plan illisible n'est pas un plan.
MAX_VALEURS = 6

_console: Any | None = Console() if _RICH else None


def _ecrire(quoi: Any) -> None:
    if _console is not None:
        _console.print(quoi)
    else:  # pragma: no cover - chemin sans Rich
        print(quoi)


def resume_valeurs(valeurs: Sequence[Any]) -> str:
    """Une liste, abrégée au-delà de :data:`MAX_VALEURS`.

    Les nombres sortent en ``%g`` — un plan lisible n'affiche pas
    ``0.30000000000000004`` — et tout le reste tel quel : la même fonction sert
    aux valeurs d'une variable et aux noms des variables.
    """
    if not len(valeurs):
        return "—"
    tete = ", ".join(_bref(valeur) for valeur in valeurs[:MAX_VALEURS])
    reste = len(valeurs) - MAX_VALEURS
    return tete if reste <= 0 else f"{tete}, … (+{reste})"


def _bref(valeur: Any) -> str:
    """Un élément de liste, tel qu'il se lit dans un plan."""
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return str(valeur)
    return f"{float(valeur):g}"


def imprimer_plan(
    rapport: RapportTables,
    *,
    sortie: Path | None = None,
    planches: int | None = None,
    max_valeurs: int | None = None,
    a_blanc: bool = False,
) -> None:
    """Ce que le parcours va faire, avant de le faire."""
    lignes = [
        f"tables        : {len(rapport)}",
        f"nœuds         : {rapport.n_points}",
        f"hors tolérance: {rapport.n_fautifs}",
    ]
    if sortie is not None:
        lignes.append(f"sortie        : {sortie}")
    if planches is not None:
        lignes.append(f"planches      : {planches}")
    if max_valeurs is not None:
        lignes.append(f"valeurs épinglées par variable : au plus {max_valeurs}")
    if a_blanc:
        lignes.append("à blanc       : rien ne sera écrit")

    if _RICH and Panel is not None:
        _ecrire(
            Panel(
                "\n".join(lignes),
                border_style=theme.TITRE,
                title="Plan du parcours",
                title_align="left",
            )
        )
        _ecrire(_tableau_tables(rapport, max_valeurs=max_valeurs))
        return
    for ligne in lignes:  # pragma: no cover - chemin sans Rich
        _ecrire(ligne)


def _tableau_tables(rapport: RapportTables, *, max_valeurs: int | None) -> Any:
    """Les boucles, table par table : ce qui balaie et ce qui s'épingle."""
    table = Table(
        title="Boucles",
        title_style=theme.TITRE,
        header_style=theme.ENTETE,
    )
    table.add_column("table")
    table.add_column("nœuds", justify="right")
    table.add_column("variables indépendantes")
    table.add_column("grandeurs")
    for resultat in rapport:
        table.add_row(
            resultat.nom,
            str(resultat.n_points),
            resume_valeurs(list(resultat.spec.independantes)),
            ", ".join(resultat.spec.qoi),
        )
    if max_valeurs is not None:
        table.caption = (
            f"l'abscisse montre tous ses points ; les autres variables sont "
            f"épinglées sur au plus {max_valeurs} valeurs"
        )
        table.caption_style = theme.DISCRET
    return table


def imprimer_bilan(ecrits: Mapping[str, Sequence[Path]], *, a_blanc: bool = False) -> None:
    """Les fichiers écrits, regroupés par table."""
    total = sum(len(fichiers) for fichiers in ecrits.values())
    verbe = "seraient écrits" if a_blanc else "écrits"
    if not _RICH or Table is None:  # pragma: no cover - chemin sans Rich
        _ecrire(f"{total} fichier(s) {verbe}")
        return

    table = Table(
        title=f"{total} fichier(s) {verbe}",
        title_style=theme.TITRE,
        header_style=theme.ENTETE,
    )
    table.add_column("table")
    table.add_column("planches", justify="right")
    table.add_column("répertoire")
    for nom, fichiers in ecrits.items():
        racine = _racine_commune(fichiers)
        table.add_row(nom, str(len(fichiers)), str(racine) if racine else "—")
    _ecrire(table)


def imprimer_note(message: str, *, style: str = "") -> None:
    """Une remarque isolée, dans le flux du parcours."""
    if _RICH:
        _ecrire(f"[{style or theme.DISCRET}]{message}[/]")
    else:  # pragma: no cover - chemin sans Rich
        _ecrire(message)


def _racine_commune(fichiers: Sequence[Path]) -> Path | None:
    """Le répertoire commun d'une liste de fichiers, s'il y en a un."""
    if not fichiers:
        return None
    dossiers = {fichier.parent for fichier in fichiers}
    if len(dossiers) == 1:
        return next(iter(dossiers))
    parties = [fichier.parent.parts for fichier in fichiers]
    commun: list[str] = []
    for morceaux in zip(*parties):
        if len(set(morceaux)) != 1:
            break
        commun.append(morceaux[0])
    return Path(*commun) if commun else None
