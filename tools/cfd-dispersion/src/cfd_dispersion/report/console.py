"""Rapport terminal : ce qui a été tiré, ce qui a été validé.

Les fonctions **rendent** un objet Rich plutôt que de l'imprimer : l'appelant
choisit sa ``Console``, y compris celle d'un script englobant, et les tests
peuvent inspecter le résultat sans capturer une sortie standard.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from rich.panel import Panel
from rich.table import Table

from ..core.lois import JeuDeLois
from ..core.tirage import Tirage
from . import theme

__all__ = ["panneau_erreur", "table_lois", "table_tirage"]


def table_lois(lois: JeuDeLois, *, titre: str = "Lois de dispersion") -> Table:
    """Les lois chargées, une ligne par composante."""
    table = Table(title=titre, title_style=theme.TITRE, header_style=theme.ENTETE)
    table.add_column("coefficient")
    table.add_column("composante")
    table.add_column("loi")
    table.add_column("M", justify="right")
    table.add_column("ET", justify="right")
    table.add_column("σ exact", justify="right")
    table.add_column("support", justify="right", style=theme.DISCRET)

    for coefficient, composante, loi in lois.composantes():
        bas, haut = loi.support()
        support = (
            "—" if loi.est_degeneree else (f"[{bas:.4g}, {haut:.4g}]" if loi.est_bornee else "ℝ")
        )
        table.add_row(
            coefficient,
            composante,
            loi.label,
            f"{loi.M:g}",
            f"{loi.ET:g}",
            f"{loi.ET_theorique:.4g}",
            support,
        )

    if not lois.independantes:
        table.caption = "composantes corrélées"
        table.caption_style = theme.ATTENTION
    return table


def table_tirage(tirage: Tirage, *, titre: str = "Tirage") -> Table:
    """Les valeurs tirées, une ligne par coefficient."""
    table = Table(title=titre, title_style=theme.TITRE, header_style=theme.ENTETE)
    table.add_column("coefficient")
    table.add_column("Biais", justify="right", style=theme.VALEUR)
    table.add_column("FE", justify="right", style=theme.VALEUR)

    for coefficient, valeurs in tirage.items():
        table.add_row(coefficient, f"{valeurs['Biais']:.6g}", f"{valeurs['FE']:.6g}")

    table.caption = tirage.resume
    table.caption_style = theme.DISCRET
    return table


def table_verdicts(verdicts: pd.DataFrame, *, titre: str = "Verdicts") -> Table:
    """Le détail des verdicts, une ligne par (point de vol, composante)."""
    from ..figures.synthese import colonnes_pdv

    cles = colonnes_pdv(verdicts)
    table = Table(title=titre, title_style=theme.TITRE, header_style=theme.ENTETE)
    for cle in cles:
        table.add_column(cle, justify="right")
    table.add_column("coefficient")
    table.add_column("composante")
    table.add_column("n", justify="right")
    table.add_column("KS p", justify="right")
    table.add_column("verdict")

    # Colonnes lues avec leur type explicite : les stubs pandas typent les
    # champs d'`itertuples` en une union si large qu'aucune conversion n'y passe.
    colonnes = [verdicts[cle] for cle in cles] + [
        verdicts["coefficient"].astype(str),
        verdicts["composante"].astype(str),
        verdicts["n"].astype(int),
        verdicts["ks_p"].astype(float),
        verdicts["valide"].astype(bool),
        verdicts["motif"].astype(str),
    ]
    for brut in zip(*colonnes):
        *valeurs_pdv, coefficient, composante, n, ks_p, valide, motif = brut
        etat = "validé" if valide else f"rejeté — {motif}"
        table.add_row(
            *[_format(valeur) for valeur in valeurs_pdv],
            coefficient,
            composante,
            str(n),
            "—" if pd.isna(ks_p) else f"{ks_p:.3f}",
            f"[{theme.STYLE_VERDICT[bool(valide)]}]{etat}[/]",
        )
    return table


def panneau_erreur(message: str, *, indice: str = "") -> Panel:
    """Un message d'erreur encadré, plutôt qu'une trace d'exécution.

    Le public est un ingénieur qui disperse des coefficients, pas un
    développeur Python qui débogue cet outil.
    """
    corps = message if not indice else f"{message}\n\n[{theme.DISCRET}]{indice}[/]"
    return Panel(corps, border_style=theme.ERREUR, title="Erreur", title_align="left")


def _format(valeur: Any) -> str:
    if isinstance(valeur, float):
        return f"{valeur:g}"
    return str(valeur)


__all__.append("table_verdicts")
