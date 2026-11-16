"""Rapport terminal du rendu et du diagnostic."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeRemainingColumn
from rich.table import Table
from rich.text import Text

from cfd_trajcast.engine.diagnostic import Sonde
from cfd_trajcast.engine.pipeline import Progression, ResultatRendu
from cfd_trajcast.report import theme

__all__ = ["barre_progression", "rapport_diagnostic", "rapport_rendu"]


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


def rapport_diagnostic(sondes: Sequence[Sonde]) -> Panel:
    """Une ligne par essai ; le verdict dit si le rendu est possible."""
    table = Table(box=box.SIMPLE_HEAD, header_style=theme.ENTETE)
    table.add_column("élément")
    table.add_column("état", no_wrap=True)
    table.add_column("détail", style=theme.DISCRET)
    for s in sondes:
        table.add_row(s.nom, Text("ok" if s.ok else "non", style=theme.OK if s.ok else theme.ATTENTION), s.detail)
    rendu = [s for s in sondes if s.ok and ("EGL" in s.nom or "X11" in s.nom)]
    verdict = (
        Text(f"rendu possible : {rendu[0].nom} — {rendu[0].detail}", style=theme.OK)
        if rendu
        else Text("aucune fenêtre de rendu ne fonctionne : installer libEGL + Mesa, ou lancer "
                  "sous xvfb-run", style=theme.ERREUR)
    )
    from rich.console import Group

    return Panel(Group(table, verdict), title=Text("cfd-trajcast · diagnostic", style=theme.TITRE),
                 title_align="left", border_style=theme.DISCRET, box=box.ROUNDED)
