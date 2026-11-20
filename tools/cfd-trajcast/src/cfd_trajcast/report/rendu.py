"""Rapport terminal du rendu et du diagnostic."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeRemainingColumn
from rich.table import Table
from rich.text import Text

from cfd_trajcast.engine.diagnostic import Sonde, cause_probable
from cfd_trajcast.engine.pipeline import Progression, ResultatRendu
from cfd_trajcast.engine.schema_ensemble import Schema
from cfd_trajcast.report import theme

__all__ = ["barre_progression", "rapport_diagnostic", "rapport_rendu", "rapport_schema"]


@contextmanager
def barre_progression(console: Console, libelle: str) -> Iterator[Progression]:
    """Barre Rich ; renvoie le rappel à passer à ``Film.rendre``."""
    progres = Progress(
        TextColumn(libelle, style=theme.DISCRET), BarColumn(complete_style=theme.ACCENT),
        MofNCompleteColumn(), TimeRemainingColumn(), console=console, transient=True,
    )
    tache = progres.add_task(libelle, total=None)
    with progres:
        def rappel(fait: int, total: int) -> None:
            progres.update(tache, completed=fait, total=total)

        yield rappel


def rapport_rendu(r: ResultatRendu) -> Panel:
    """Ce qui a été écrit, et en combien de temps."""
    table = Table(box=None, show_header=False, padding=(0, 2))
    table.add_column(style=theme.DISCRET)
    table.add_column(style=theme.VALEUR)
    table.add_row("fichier", str(r.chemin))
    table.add_row("format", f"{r.largeur}×{r.hauteur}, {r.ips:g} ips, H.264")
    table.add_row("durée", f"{r.duree_video:.2f} s de vidéo ({r.n_images} images)")
    table.add_row("vol montré", f"{r.t_vol[0]:.2f} → {r.t_vol[1]:.2f} s")
    debit = f"{r.secondes:.1f} s ({r.ms_par_image:.0f} ms/image, {1000 / max(r.ms_par_image, 1e-9):.1f} images/s)"
    table.add_row("rendu", debit)
    if r.processus > 1:
        table.add_row("parallèle", f"{r.processus} processus, {r.troncons} tronçons recollés")
    return Panel(table, title=Text("cfd-trajcast · rendre", style=theme.TITRE), title_align="left",
                 border_style=theme.DISCRET, box=box.ROUNDED)


def rapport_schema(s: Schema) -> Panel:
    """Le schéma SVG écrit."""
    table = Table(box=None, show_header=False, padding=(0, 2))
    table.add_column(style=theme.DISCRET)
    table.add_column(style=theme.VALEUR)
    table.add_row("fichier", str(s.chemin))
    table.add_row("format", f"SVG {s.largeur}×{s.hauteur}, {len(s.svg.encode('utf-8')) / 1000:.0f} ko")
    poses = ", ".join(f"{t:.1f} s" for t in s.poses) or "aucune"
    table.add_row("maquette", f"agrandie × {s.echelle:.0f}, posée à {poses} ({s.faces} faces)")
    return Panel(table, title=Text("cfd-trajcast · ensemble", style=theme.TITRE), title_align="left",
                 border_style=theme.DISCRET, box=box.ROUNDED)


def rapport_diagnostic(sondes: Sequence[Sonde]) -> Panel:
    """Une ligne par essai ; le verdict dit si le rendu est possible, sinon ce qu'il faut corriger.

    Les erreurs complètes des essais ratés suivent le tableau : sur une machine
    air-gap, c'est souvent tout ce que l'utilisateur pourra recopier.
    """
    from rich.console import Group

    table = Table(box=box.SIMPLE_HEAD, header_style=theme.ENTETE)
    table.add_column("élément")
    table.add_column("état", no_wrap=True)
    table.add_column("détail", style=theme.DISCRET)
    precedente = None
    for s in sondes:
        if precedente is not None and s.categorie != precedente:
            table.add_section()
        precedente = s.categorie
        # Text, pas str : « extra [step] » serait lu comme une balise Rich et disparaîtrait.
        table.add_row(Text(s.nom), Text("ok" if s.ok else "non", style=theme.OK if s.ok else theme.ATTENTION),
                      Text(s.detail))
    fenetres = [s for s in sondes if s.categorie == "fenetre"]
    rendu = next((s for s in sondes if s.categorie == "rendu"), None)
    reussies = [s for s in fenetres if s.ok]
    vieilles = [s for s in sondes if s.categorie == "version" and not s.ok]
    morceaux: list[Any] = [table]
    if reussies and (rendu is None or rendu.ok):
        morceaux.append(Text(f"rendu possible : {reussies[0].nom} — {reussies[0].detail}", style=theme.OK))
    elif reussies and rendu is not None:
        morceaux.append(Text(f"rendu possible, mais pas avec la fenêtre par défaut : {rendu.detail}",
                             style=theme.ATTENTION))
    else:
        cause = cause_probable(sondes)
        morceaux.append(Text("aucune fenêtre de rendu ne fonctionne.", style=theme.ERREUR))
        morceaux.append(Text("cause probable : " + cause if cause else
                             "installer libEGL + Mesa, ou lancer sous xvfb-run", style=theme.ERREUR))
    if vieilles and reussies:
        morceaux.append(Text("versions hors minimum : " + ", ".join(s.nom for s in vieilles)
                             + " — non pris en charge, même si l'essai passe.", style=theme.ATTENTION))
    traces = [s for s in fenetres if not s.ok and s.trace]
    if traces:
        morceaux.append(Text("\nerreurs complètes des essais ratés", style=theme.ENTETE))
        for s in traces:
            morceaux.append(Text(f"── {s.nom}", style=theme.ATTENTION))
            morceaux.append(Text(s.trace, style=theme.DISCRET))
    return Panel(Group(*morceaux), title=Text("cfd-trajcast · diagnostic", style=theme.TITRE),
                 title_align="left", border_style=theme.DISCRET, box=box.ROUNDED)
