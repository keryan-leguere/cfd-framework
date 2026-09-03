"""Synthèse : combien de points de vol passent, lesquels échouent, et pourquoi.

C'est le cas d'usage 2.2. Une fois :func:`cfd_dispersion.core.validation.valider_lot`
passé sur toute la sortie du modèle, on dispose d'un verdict par (point de vol
× coefficient × composante). Reste à en faire quelque chose de lisible :

- :func:`tableau_par_pdv` — le damier : une ligne par point de vol, une colonne
  par composante, le verdict dans la case ;
- :func:`synthese` — le taux de validation par composante, et la répartition
  des motifs de rejet ;
- :func:`pdv_rejetes` — la liste des points de vol fautifs, à repasser telle
  quelle à :func:`cfd_dispersion.figures.monte_carlo.figures_par_pdv` pour ne
  tracer que ceux-là.

Ce dernier point est l'essentiel du cas d'usage : sur cinquante points de vol
et six composantes, on ne regarde pas trois cents figures — on regarde les
quatre qui ont échoué.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from ..core.validation import Verdict
from ..report.theme import COULEUR_VERDICT
from ._base import PROFIL_DEFAUT, nouvelle_figure, style, surtitre

__all__ = [
    "colonnes_pdv",
    "figure_synthese",
    "pdv_rejetes",
    "synthese",
    "tableau_par_pdv",
]

#: Les champs que porte un :class:`~cfd_dispersion.core.validation.Verdict`.
_CHAMPS_VERDICT: frozenset[str] = frozenset(Verdict.__dataclass_fields__)


def colonnes_pdv(verdicts: pd.DataFrame) -> list[str]:
    """Les colonnes de *verdicts* qui décrivent le point de vol.

    Tout ce qui n'est pas un champ de :class:`Verdict` : c'est ainsi qu'on
    retrouve les clés de groupement sans que l'appelant ait à les redonner.
    """
    return [colonne for colonne in verdicts.columns if colonne not in _CHAMPS_VERDICT]


def _verifier(verdicts: pd.DataFrame) -> None:
    manquantes = sorted({"coefficient", "composante", "valide", "motif"} - set(verdicts.columns))
    if manquantes:
        raise ValueError(
            f"colonne(s) absente(s) du tableau de verdicts : {manquantes} ; "
            "attendu la sortie de valider_lot()"
        )


def tableau_par_pdv(verdicts: pd.DataFrame) -> pd.DataFrame:
    """Le damier : une ligne par point de vol, une colonne par composante.

    La case porte ``"VALIDÉ"`` ou le motif du rejet, ce qui rend le tableau
    lisible d'un coup d'œil tout en disant *pourquoi* quand ça échoue.

    Returns
    -------
    pandas.DataFrame
        Indexé par les colonnes de point de vol ; colonnes
        ``"<coefficient>_<composante>"``.
    """
    _verifier(verdicts)
    if verdicts.empty:
        return pd.DataFrame()

    table = verdicts.copy()
    table["_case"] = np.where(table["valide"], "VALIDÉ", table["motif"])
    table["_colonne"] = table["coefficient"] + "_" + table["composante"]

    cles = colonnes_pdv(verdicts)
    if not cles:
        return table.set_index("_colonne")[["_case"]].T.rename(index={"_case": "tout"})

    damier = table.pivot_table(index=cles, columns="_colonne", values="_case", aggfunc="first")
    # `pivot_table` trie ; on rétablit l'ordre des composantes tel qu'écrit.
    ordre = list(dict.fromkeys(table["_colonne"]))
    return damier.reindex(columns=ordre)


def synthese(verdicts: pd.DataFrame) -> pd.DataFrame:
    """Le taux de validation par composante, et les motifs de rejet.

    Returns
    -------
    pandas.DataFrame
        Une ligne par (coefficient, composante), avec ``n_pdv``, ``n_valides``,
        ``n_rejetes``, ``taux_validation`` (en %), ``taux_rejet`` (en %) et
        ``motifs`` (le détail des causes, ``""`` si tout passe).
    """
    _verifier(verdicts)
    if verdicts.empty:
        return pd.DataFrame(
            columns=[
                "coefficient",
                "composante",
                "n_pdv",
                "n_valides",
                "n_rejetes",
                "taux_validation",
                "taux_rejet",
                "motifs",
            ]
        )

    lignes: list[dict[str, Any]] = []
    for (coeff, composante), groupe in verdicts.groupby(["coefficient", "composante"], sort=False):
        n = len(groupe)
        n_valides = int(groupe["valide"].sum())
        motifs = groupe.loc[~groupe["valide"], "motif"].value_counts()
        lignes.append(
            {
                "coefficient": coeff,
                "composante": composante,
                "n_pdv": n,
                "n_valides": n_valides,
                "n_rejetes": n - n_valides,
                "taux_validation": 100.0 * n_valides / n,
                "taux_rejet": 100.0 * (n - n_valides) / n,
                "motifs": ", ".join(f"{motif} ×{compte}" for motif, compte in motifs.items()),
            }
        )
    return pd.DataFrame(lignes)


def pdv_rejetes(
    verdicts: pd.DataFrame,
    *,
    coefficient: str | None = None,
    composante: str | None = None,
) -> list[dict[str, Any]]:
    """Les points de vol dont au moins une composante est rejetée.

    Le résultat se passe tel quel au paramètre ``seulement`` de
    :func:`cfd_dispersion.figures.monte_carlo.figures_par_pdv`, qui ne trace
    alors que ces cas-là.

    Parameters
    ----------
    coefficient, composante:
        Restreindre aux rejets d'un coefficient ou d'une composante donnés.

    Returns
    -------
    list of dict
        Un dictionnaire de clés de point de vol par cas rejeté, sans doublon
        et dans l'ordre de première apparition.
    """
    _verifier(verdicts)
    if verdicts.empty:
        return []

    rejets = verdicts.loc[~verdicts["valide"]]
    if coefficient is not None:
        rejets = rejets.loc[rejets["coefficient"] == coefficient]
    if composante is not None:
        rejets = rejets.loc[rejets["composante"] == composante]

    cles = colonnes_pdv(verdicts)
    if not cles:
        return [{}] if len(rejets) else []

    vus: list[dict[str, Any]] = []
    for brut in rejets[cles].to_dict("records"):
        # `to_dict` type ses clés en Hashable ; ce sont des noms de colonnes.
        enregistrement = {str(cle): valeur for cle, valeur in brut.items()}
        if enregistrement not in vus:
            vus.append(enregistrement)
    return vus


def figure_synthese(
    verdicts: pd.DataFrame,
    *,
    titre_: str = "Synthèse de validation",
    profil: str = PROFIL_DEFAUT,
    figsize: tuple[float, float] | None = None,
) -> tuple[Figure, Any]:
    """Le damier des verdicts, en tableau coloré.

    Vert pour validé, rouge pour rejeté, le motif écrit dans la case. Une ligne
    de synthèse en pied donne le taux de validation de chaque composante.

    Returns
    -------
    (Figure, Axes)
    """
    _verifier(verdicts)
    damier = tableau_par_pdv(verdicts)
    if damier.empty:
        raise ValueError("aucun verdict à représenter")

    resume = synthese(verdicts).set_index(["coefficient", "composante"])
    taux = [
        f"{resume.loc[tuple(colonne.rsplit('_', 1)), 'taux_validation']:.0f} %"
        if tuple(colonne.rsplit("_", 1)) in resume.index
        else "—"
        for colonne in damier.columns
    ]

    etiquettes_lignes = [
        " · ".join(f"{cle}={_format(valeur)}" for cle, valeur in zip(damier.index.names, ligne))
        if isinstance(ligne, tuple)
        else f"{damier.index.names[0]}={_format(ligne)}"
        for ligne in damier.index
    ]

    n_lignes, n_colonnes = damier.shape
    with style(profil):
        # La hauteur suit le nombre de lignes ; sans cela un damier de quatre
        # points de vol flotte au milieu d'une figure taillée pour vingt.
        figure, ax = nouvelle_figure(
            figsize=figsize or (2.0 + 1.5 * n_colonnes, 0.7 + 0.30 * (n_lignes + 2))
        )
        ax.set_axis_off()

        cellules = [[str(valeur) for valeur in ligne] for ligne in damier.to_numpy()]
        cellules.append(taux)
        lignes = [*etiquettes_lignes, "taux de validation"]

        table = ax.table(
            cellText=cellules,
            rowLabels=lignes,
            colLabels=list(damier.columns),
            cellLoc="center",
            loc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(7.5)
        table.scale(1.0, 1.35)

        for (ligne, colonne), cellule in table.get_celld().items():
            cellule.set_edgecolor("0.8")
            if ligne == 0 or colonne == -1:
                cellule.set_text_props(color="0.15")
                cellule.set_facecolor("0.93")
                continue
            if ligne == n_lignes + 1:  # la ligne de synthèse
                cellule.set_facecolor("0.97")
                continue
            valide = cellule.get_text().get_text() == "VALIDÉ"
            cellule.set_facecolor("#e6f2e9" if valide else "#fbe6e6")
            cellule.set_text_props(color=COULEUR_VERDICT[valide])

        surtitre(figure, titre_, fontsize=11)

    return figure, ax


def _format(valeur: Any) -> str:
    """Met en forme une valeur de point de vol pour une étiquette."""
    if isinstance(valeur, float):
        return f"{valeur:g}"
    return str(valeur)


def table_rich(verdicts: pd.DataFrame, *, titre_: str = "Synthèse de validation") -> Any:
    """La synthèse en table Rich, pour le terminal.

    Rendue plutôt qu'affichée : l'appelant l'imprime sur la ``Console`` de son
    choix, y compris celle d'un script englobant.
    """
    from rich.table import Table

    from ..report import theme

    resume = synthese(verdicts)
    table = Table(title=titre_, title_style=theme.TITRE, header_style=theme.ENTETE)
    for colonne in ("coefficient", "composante"):
        table.add_column(colonne)
    table.add_column("n PDV", justify="right")
    table.add_column("validés", justify="right")
    table.add_column("rejetés", justify="right")
    table.add_column("taux", justify="right")
    table.add_column("motifs", style=theme.DISCRET)

    # Les colonnes sont lues avec leur type explicite plutôt que par
    # `itertuples`, dont les stubs pandas typent chaque champ comme une union
    # si large qu'aucune conversion n'y passe.
    lignes = zip(
        resume["coefficient"].astype(str),
        resume["composante"].astype(str),
        resume["n_pdv"].astype(int),
        resume["n_valides"].astype(int),
        resume["n_rejetes"].astype(int),
        resume["taux_validation"].astype(float),
        resume["motifs"].astype(str),
    )
    for coefficient, composante, n_pdv, n_valides, n_rejetes, taux, motifs in lignes:
        style_taux = theme.OK if n_rejetes == 0 else theme.ERREUR
        table.add_row(
            coefficient,
            composante,
            str(n_pdv),
            str(n_valides),
            str(n_rejetes),
            f"[{style_taux}]{taux:.0f} %[/]",
            motifs or "—",
        )
    return table


__all__.append("table_rich")
