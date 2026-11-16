"""Rapport terminal de ``cfd-trajcast check`` (Rich, français, sans gras)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cfd_trajcast.data.configuration import Configuration
from cfd_trajcast.data.constats import ALERTE, ERREUR, INFO, Constat
from cfd_trajcast.data.maquette import Maquette
from cfd_trajcast.data.trajectoire import Trajectoire
from cfd_trajcast.report import theme

__all__ = ["panneau_erreur", "rapport_check"]

_STYLE_NIVEAU = {INFO: theme.DISCRET, ALERTE: theme.ATTENTION, ERREUR: theme.ERREUR}
_LIBELLE_NIVEAU = {INFO: "info", ALERTE: "alerte", ERREUR: "erreur"}


def panneau_erreur(message: str, *, indice: str = "") -> Panel:
    """Erreur d'entrée : un panneau rouge, jamais une trace d'appels."""
    contenu = Text(message, style=theme.ERREUR)
    if indice:
        contenu.append(f"\n{indice}", style=theme.DISCRET)
    return Panel(
        contenu,
        title=Text("cfd-trajcast · erreur", style=theme.ERREUR),
        title_align="left",
        border_style=theme.ERREUR,
        box=box.ROUNDED,
    )


def _court(chemin: str) -> str:
    """Chemin relatif au dossier courant quand c'est possible."""
    try:
        return str(Path(chemin).resolve().relative_to(Path.cwd()))
    except ValueError:
        return chemin


def _declarations(cfg: Configuration | None, traj: Trajectoire, maquette: Maquette | None) -> Table:
    table = Table(box=None, show_header=False, padding=(0, 2))
    table.add_column(style=theme.DISCRET)
    table.add_column(style=theme.VALEUR)
    table.add_row("trajectoire", _court(traj.source))
    for cle, valeur in traj.declaration.decrire():
        table.add_row(f"  {cle}", valeur)
    if maquette is not None:
        d = maquette.declaration
        origine = d.origine if isinstance(d.origine, str) else f"[{', '.join(f'{v:g}' for v in d.origine)}]"
        table.add_row("maquette", _court(str(d.fichier)))
        table.add_row("  axes", f"nez {d.axe_nez}, haut {d.axe_haut} (→ corps FRD)")
        table.add_row("  origine", origine)
        table.add_row("  échelle", f"× {maquette.echelle:.6g} de l'unité du fichier au mètre")
    if cfg is not None and cfg.a_venir:
        table.add_row("sections à venir", ", ".join(cfg.a_venir) + " (lues aux jalons suivants)")
    return table


def _constats(constats: Sequence[Constat]) -> Table:
    table = Table(box=box.SIMPLE_HEAD, header_style=theme.ENTETE, expand=False)
    table.add_column("niveau", no_wrap=True)
    table.add_column("constat")
    ordre = {ERREUR: 0, ALERTE: 1, INFO: 2}
    for c in sorted(constats, key=lambda c: ordre[c.niveau]):
        texte = Text(c.message)
        if c.indice:
            texte.append(f"\n{c.indice}", style=theme.DISCRET)
        table.add_row(Text(_LIBELLE_NIVEAU[c.niveau], style=_STYLE_NIVEAU[c.niveau]), texte)
    return table


def rapport_check(
    cfg: Configuration | None,
    traj: Trajectoire,
    maquette: Maquette | None,
    constats: Sequence[Constat],
) -> RenderableType:
    """Conventions retenues, constats, verdict."""
    n_err = sum(c.niveau == ERREUR for c in constats)
    n_alerte = sum(c.niveau == ALERTE for c in constats)
    if n_err:
        verdict = Text(f"{n_err} erreur(s), {n_alerte} alerte(s) : à corriger avant le rendu", style=theme.ERREUR)
    elif n_alerte:
        verdict = Text(f"{n_alerte} alerte(s) : à lire avant le rendu", style=theme.ATTENTION)
    else:
        verdict = Text("conforme", style=theme.OK)
    titre = "cfd-trajcast · check"
    if cfg is not None and cfg.chemin is not None:
        titre += f" · {cfg.chemin.name}"
    if cfg is not None and cfg.etude.titre:
        titre += f" · {cfg.etude.titre}"
    return Panel(
        Group(_declarations(cfg, traj, maquette), Text(""), _constats(constats), verdict),
        title=Text(titre, style=theme.TITRE),
        title_align="left",
        border_style=theme.DISCRET,
        box=box.ROUNDED,
    )
