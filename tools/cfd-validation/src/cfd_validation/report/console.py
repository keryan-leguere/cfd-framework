"""Le rapport terminal : ce qui a été contrôlé, et ce qui cloche.

Les fonctions **rendent** un objet Rich plutôt que de l'imprimer : l'appelant
choisit sa ``Console`` — y compris celle d'un script englobant — et les tests
inspectent le résultat sans capturer une sortie standard. C'est l'inverse de
:mod:`cfd_validation.report.parcours`, qui imprime parce qu'un parcours est une
commande et non une valeur.

Le public visé est l'ingénieur qui a écrit le Fortran, pas le développeur qui
déboguerait cet outil : une erreur d'entrée sort en panneau rouge nommant le
fichier et le remède, jamais en trace d'appels.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table

from cfd_validation.core.motifs import Motif
from cfd_validation.engine.controle import Verdict
from cfd_validation.engine.tables import RapportTables, ResultatQOI, ResultatTable
from cfd_validation.report import theme

__all__ = [
    "imprimer_rapport",
    "panneau_erreur",
    "panneau_toolchain",
    "panneau_verdict",
    "rapport_tables",
    "tableau_blocs",
    "tableau_motifs",
    "tableau_tables",
    "tableau_verdicts",
]

#: Ce qu'on écrit là où il n'y a rien à écrire.
RIEN = "—"


def panneau_erreur(message: str, *, indice: str = "") -> Panel:
    """Un message d'erreur encadré, plutôt qu'une trace d'exécution."""
    corps = message if not indice else f"{message}\n\n[{theme.DISCRET}]{indice}[/]"
    return Panel(corps, border_style=theme.ERREUR, title="Erreur", title_align="left")


def panneau_verdict(rapport: RapportTables) -> Panel:
    """Le verdict d'ensemble, en trois lignes.

    C'est la seule chose que beaucoup de lecteurs liront : elle doit répondre
    seule à « est-ce que mon code lit ses tables ? ».
    """
    style = theme.STYLE_VERDICT[rapport.conforme]
    etat = (
        "toutes les tables sont relues correctement"
        if rapport.conforme
        else "des écarts subsistent"
    )
    lignes = [
        f"[{theme.DISCRET}]verdict     :[/] [{style}]{etat}[/]",
        f"[{theme.DISCRET}]tables      :[/] {len(rapport)}",
        f"[{theme.DISCRET}]nœuds       :[/] {rapport.n_points}",
        f"[{theme.DISCRET}]hors tol.   :[/] "
        + (
            f"[{theme.OK}]aucun[/]"
            if rapport.n_fautifs == 0
            else f"[{theme.ERREUR}]{rapport.n_fautifs}[/]"
        ),
    ]
    return Panel(
        "\n".join(lignes),
        border_style=theme.TITRE,
        title="Relecture de tables",
        title_align="left",
    )


def tableau_tables(rapport: RapportTables) -> Table:
    """Une ligne par grandeur contrôlée : le récapitulatif."""
    table = Table(
        title="Contrôle table par table",
        title_style=theme.TITRE,
        header_style=theme.ENTETE,
    )
    table.add_column("table")
    table.add_column("grandeur")
    table.add_column("nœuds", justify="right")
    table.add_column("hors tol.", justify="right")
    table.add_column("écart abs. max", justify="right")
    table.add_column("écart rel. max", justify="right")
    table.add_column("motif / verdict")

    for resultat in rapport:
        for grandeur in resultat.grandeurs:
            style = theme.STYLE_VERDICT[grandeur.conforme]
            table.add_row(
                resultat.nom,
                grandeur.qoi,
                str(grandeur.ecart.n),
                _fautifs(grandeur),
                _nombre(grandeur.ecart.absolu_max),
                _nombre(grandeur.ecart.relatif_max),
                f"[{style}]{_verdict_court(grandeur)}[/]",
            )
    return table


def tableau_motifs(resultat: ResultatTable) -> Table | None:
    """Les motifs de panne d'une table, du plus explicatif au moins.

    ``None`` quand la table est conforme : il n'y a rien à diagnostiquer, et un
    tableau vide ferait croire le contraire.
    """
    if resultat.conforme:
        return None
    table = Table(
        title=f"Diagnostic — table « {resultat.nom} »",
        title_style=theme.ENTETE_ALT,
        header_style=theme.ENTETE_ALT,
    )
    table.add_column("grandeur")
    table.add_column("motif")
    table.add_column("explique", justify="right")
    table.add_column("ce que cela veut dire")

    for grandeur in resultat.grandeurs:
        if grandeur.conforme:
            continue
        for rang, motif in enumerate(grandeur.motifs):
            table.add_row(
                grandeur.qoi if rang == 0 else "",
                _nom_motif(motif, premier=rang == 0),
                _part(motif),
                motif.message,
            )
    table.caption = "le motif le plus explicatif est en tête ; à part égale, le plus précis"
    table.caption_style = theme.DISCRET
    return table


def rapport_tables(rapport: RapportTables) -> Group:
    """Le rapport complet : verdict, récapitulatif, puis un diagnostic par table fautive."""
    morceaux: list[RenderableType] = [panneau_verdict(rapport), tableau_tables(rapport)]
    for resultat in rapport:
        diagnostic = tableau_motifs(resultat)
        if diagnostic is not None:
            morceaux.append(diagnostic)
    return Group(*morceaux)


def imprimer_rapport(rapport: RapportTables, console: Any | None = None) -> int:
    """Imprime le rapport complet et rend le code de retour qui va avec.

    Le raccourci en une ligne pour un script d'utilisateur ::

        rapport = valider_tables(module, TABLES, modele=mon_modele)
        raise SystemExit(imprimer_rapport(rapport))

    ``0`` si tout est conforme, ``2`` sinon — la commande a abouti, c'est son
    résultat qui exige une action.
    """
    from rich.console import Console

    (console or Console()).print(rapport_tables(rapport))
    return 0 if rapport.conforme else 2


def tableau_verdicts(verdicts: Iterable[Verdict]) -> Table:
    """Le récapitulatif d'une suite, tous contrôles confondus."""
    table = Table(
        title="Suite de validation",
        title_style=theme.TITRE,
        header_style=theme.ENTETE,
    )
    table.add_column("contrôle")
    table.add_column("sujet")
    table.add_column("grandeur")
    table.add_column("points", justify="right")
    table.add_column("hors tol.", justify="right")
    table.add_column("verdict")

    for verdict in verdicts:
        style = theme.STYLE_VERDICT[verdict.conforme]
        table.add_row(
            verdict.controle,
            verdict.sujet,
            verdict.grandeur,
            str(verdict.total),
            f"[{style}]{verdict.fautifs}[/]" if verdict.fautifs else f"[{theme.OK}]0[/]",
            f"[{style}]{verdict.message}[/]",
        )
    return table


def tableau_blocs(blocs: Mapping[str, Iterable[str]]) -> Table:
    """Ce qu'un module expose : ses COMMON blocks et leurs tableaux.

    La première chose à regarder devant un module inconnu — et l'antidote au
    « bloc introuvable » qu'on obtient sinon en devinant les noms.
    """
    table = Table(
        title="COMMON blocks exposés",
        title_style=theme.TITRE,
        header_style=theme.ENTETE,
    )
    table.add_column("bloc")
    table.add_column("tableaux")
    if not blocs:
        table.add_row(f"[{theme.ATTENTION}]{RIEN}[/]", "aucun COMMON block détecté")
        return table
    for nom, membres in blocs.items():
        table.add_row(nom, ", ".join(sorted(membres)) or RIEN)
    return table


def panneau_toolchain(chaine: Any) -> Panel:
    """L'état de la chaîne de compilation, et le remède s'il en manque un morceau."""
    style = theme.STYLE_VERDICT[bool(chaine.pret)]
    lignes = [
        f"[{theme.DISCRET}]NumPy        :[/] {chaine.numpy}",
        f"[{theme.DISCRET}]moteur f2py  :[/] {chaine.backend}",
        f"[{theme.DISCRET}]gfortran     :[/] {chaine.gfortran or RIEN}",
        f"[{theme.DISCRET}]gcc          :[/] {chaine.gcc or RIEN}",
        f"[{theme.DISCRET}]meson        :[/] {chaine.meson or RIEN}",
        f"[{theme.DISCRET}]ninja        :[/] {chaine.ninja or RIEN}",
        "",
        f"[{style}]{'prête à compiler' if chaine.pret else 'manque : ' + ', '.join(chaine.manques)}[/]",
    ]
    if not chaine.pret:
        lignes.append(f"[{theme.DISCRET}]remède : {chaine.remede}[/]")
    return Panel(
        "\n".join(lignes),
        border_style=theme.TITRE if chaine.pret else theme.ERREUR,
        title="Chaîne de compilation",
        title_align="left",
    )


# ---------------------------------------------------------------------------
# Mise en forme
# ---------------------------------------------------------------------------


def _nombre(valeur: float) -> str:
    """Un nombre de rapport : trois chiffres, et un tiret pour ce qui n'existe pas."""
    if valeur != valeur:  # NaN
        return f"[{theme.ERREUR}]NaN[/]"
    return f"{valeur:.3g}"


def _fautifs(grandeur: ResultatQOI) -> str:
    if grandeur.conforme:
        return f"[{theme.OK}]0[/]"
    return f"[{theme.ERREUR}]{grandeur.ecart.n_fautifs}[/]"


def _verdict_court(grandeur: ResultatQOI) -> str:
    if grandeur.conforme:
        return "conforme"
    principal = grandeur.motif_principal
    if principal is None or principal.nom == "diffus":
        return "écart diffus"
    return principal.nom.replace("_", " ")


def _nom_motif(motif: Motif, *, premier: bool) -> str:
    nom = motif.nom.replace("_", " ")
    return f"[{theme.ERREUR}]{nom}[/]" if premier else f"[{theme.DISCRET}]{nom}[/]"


def _part(motif: Motif) -> str:
    """Un motif purement descriptif n'explique rien, et on l'écrit ainsi."""
    if motif.part_expliquee <= 0.0:
        return f"[{theme.DISCRET}]{RIEN}[/]"
    return f"{motif.part_expliquee:.0%}"
