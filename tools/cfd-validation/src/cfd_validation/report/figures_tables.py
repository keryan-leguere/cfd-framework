"""Figure de synthèse du test de lecture de table (cfd-plot, profil « paper »).

Un panneau par table, six par page (``synthese_tables_01``, ``_02``…). En
abscisse le rang du nœud dans l'**ordre de lecture** (premier indice Fortran le
plus rapide, celui des ``DATA``), en ordonnée la grandeur :

- points bleus : la table ;
- croix vermillon : le code, pour **toutes** les combinaisons, au rang de leur
  nœud — une lecture invariante pose ses croix les unes sur les autres. Les
  croix sont toujours **au-dessus**, plus petites que les points : sur un nuage
  dense, chaque croix garde un halo bleu, et une croix sans halo s'écarte ;
- cercle noir : point hors tolérance ; triangle noir au pied du panneau : sonde
  non atteinte (NaN).

Une table à plusieurs dimensions est découpée par son axe le plus **lent** (le
dernier) : traits verticaux fins à chaque changement de sa valeur, étiquetés en
tête. Sur une table 5D de 3 125 nœuds, les marqueurs rapetissent et le nuage est
tramé (``rasterized``) pour que le fichier reste léger ; les axes et le texte,
eux, restent vectoriels. Format par défaut : SVG seul (``FORMATS_TABLES``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from cfd_validation.core import statuts as st
from cfd_validation.core.format import formater
from cfd_validation.engine.lecture_tables import BilanTable, ResultatLectureTables
from cfd_validation.report.figures import (
    BLEU,
    GRIS,
    PAGE,
    VERMILLON,
    _cfd_plot,
    _enregistrer,
    _legende_sous,
    _paginer,
    _style,
    _suffixe,
)

__all__ = ["FORMATS_TABLES", "PANNEAUX_PAR_PAGE", "figure_synthese_tables", "tracer_figures_tables"]

#: Format des figures du test de lecture de table : SVG seul (vectoriel, s'ouvre dans un navigateur).
FORMATS_TABLES: tuple[str, ...] = ("svg",)

PANNEAUX_PAR_PAGE = 6
COLONNES_TABLES = 2
HAUTEUR_PANNEAU = 2.3
#: Au-delà, nuage tramé dans le PDF.
TRAME_AU_DELA = 2000
#: Étiquettes de blocs (axe le plus lent) au plus.
BLOCS_ETIQUETES = 12


def _tailles(n: int) -> tuple[float, float, float]:
    """(taille des points de table, taille des croix, épaisseur des croix) selon le nombre de nœuds.

    La croix est toujours plus petite que le point qu'elle couvre : il en reste
    un halo bleu, si bien qu'on voit les deux même quand ils coïncident.
    """
    if n <= 60:
        return 30.0, 16.0, 0.8
    if n <= 400:
        return 14.0, 7.0, 0.6
    if n <= 2000:
        return 7.0, 3.0, 0.45
    return 4.0, 1.6, 0.35


def _blocs(ax: Any, b: BilanTable) -> None:
    """Traits aux changements de l'axe le plus lent, étiquetés par sa valeur."""
    from matplotlib.transforms import blended_transform_factory

    t = b.table
    if len(t.forme) < 2:
        return
    lent = t.noms_axes[-1]
    pas = int(np.prod(t.forme[:-1]))
    grille = t.grilles[-1]
    trans = blended_transform_factory(ax.transData, ax.transAxes)
    tous = len(grille) <= BLOCS_ETIQUETES
    for k, valeur in enumerate(grille):
        x0 = k * pas - 0.5
        if k:
            ax.axvline(x0, color="0.80", lw=0.5, zorder=0)
        if tous or k % math.ceil(len(grille) / BLOCS_ETIQUETES) == 0:
            ax.text(x0 + pas / 2, 1.0, formater(float(valeur)), transform=trans, ha="center", va="bottom", fontsize=5.5, color="0.35")
    ax.text(1.0, 1.0, f" {lent}", transform=ax.transAxes, ha="left", va="bottom", fontsize=5.5, color="0.35")


def _panneau(cp: Any, ax: Any, b: BilanTable) -> None:
    r = b.resultats
    n = b.table.n_noeuds
    # Une lecture invariante pose la même croix à chaque combinaison : on ne trace que
    # les couples (nœud, valeur lue) distincts — même dessin, 37 fois moins de marqueurs.
    traces = r.drop_duplicates(subset=["noeud", "valeur_CODE"])
    tramer = len(traces) > TRAME_AU_DELA
    s_tab, s_code, epaisseur = _tailles(n)
    base = r[r["combinaison"] == 0]
    x = base["noeud"].to_numpy()
    ax.scatter(x, base["valeur_TAB"].to_numpy(dtype=float), s=s_tab, marker="o", color=BLEU, linewidths=0,
               label="Table", zorder=2, rasterized=tramer)
    xc = traces["noeud"].to_numpy()
    code = traces["valeur_CODE"].to_numpy(dtype=float)
    fini = np.isfinite(code)
    ax.scatter(xc[fini], code[fini], s=s_code, marker="x", color=VERMILLON, linewidths=epaisseur,
               label="Code", zorder=3, rasterized=tramer)
    hors = (~traces["conforme"].to_numpy()) & fini
    if hors.any():
        # Quelques échecs : un cercle bien visible ; des milliers : un anneau fin, sinon une tache.
        rare = int(hors.sum()) <= 50
        ax.scatter(xc[hors], code[hors], s=36 if rare else max(s_tab * 1.5, 4.0), marker="o", facecolors="none",
                   edgecolors="k", linewidths=0.8 if rare else 0.3, label="Hors tolérance", zorder=5,
                   rasterized=tramer)
    nf = traces["statut"].to_numpy() == st.NOMS[st.NON_FINI]
    if nf.any():
        from matplotlib.transforms import blended_transform_factory

        trans = blended_transform_factory(ax.transData, ax.transAxes)
        ax.scatter(xc[nf], np.full(int(nf.sum()), 0.02), s=10, marker="^", color="k", transform=trans,
                   clip_on=False, label="Sonde non atteinte (NaN)", zorder=6)
    _blocs(ax, b)
    ax.set_xlim(-0.5 - 0.01 * n, n - 0.5 + 0.01 * n)
    from matplotlib.ticker import MaxNLocator

    ax.xaxis.set_major_locator(MaxNLocator(integer=True))  # un rang de nœud : jamais 0.25
    ax.set_xlabel("Rang du nœud (ordre de lecture)", fontsize=7)
    ax.set_ylabel(b.nom, fontsize=7.5)
    verdict = "Conforme" if b.conforme else f"NON CONFORME ({b.n_echecs})"
    cp.set_title(ax, f"{b.nom} — {b.table.decrire_forme}", fontsize=8.5)
    comb = f" · {len(b.combinaisons)} comb." if len(b.combinaisons) > 1 else ""
    cp.set_subtitle(ax, f"{n} nœuds{comb} · {verdict}", fontsize=6.5, color=VERMILLON if not b.conforme else "0.3")


def figure_synthese_tables(res: ResultatLectureTables, chemin: Path, formats: Sequence[str] = FORMATS_TABLES) -> list[Path]:
    """Valeur de la table et valeur lue par le code, nœud par nœud, un panneau par table."""
    from matplotlib.lines import Line2D

    pages = _paginer(list(res.tables), PANNEAUX_PAR_PAGE)
    fichiers: list[Path] = []
    for p, page in enumerate(pages):
        if not page:
            break
        ncols = min(COLONNES_TABLES, len(page))
        nrows = math.ceil(len(page) / ncols)
        with _style() as cp:
            fig, axes = cp.new_figure(nrows, ncols, figsize=(PAGE, HAUTEUR_PANNEAU * nrows + 0.7),
                                      squeeze=False, layout="constrained")
            plats = list(np.asarray(axes).ravel())
            for ax in plats[len(page):]:
                ax.set_visible(False)
            for ax, b in zip(plats, page):
                _panneau(cp, ax, b)
            combines = any(len(b.combinaisons) > 1 for b in page)
            poignees = [
                Line2D([], [], color=BLEU, marker="o", ls="", ms=4, label="Table"),
                Line2D([], [], color=VERMILLON, marker="x", ls="", ms=5,
                       label="Code (toutes combinaisons)" if combines else "Code"),
            ]
            if any((~b.resultats["conforme"]).any() for b in page):
                poignees.append(Line2D([], [], color="k", marker="o", mfc="none", ls="", ms=6, label="Hors tolérance"))
            if any(b.n_non_finis for b in page):
                poignees.append(Line2D([], [], color="k", marker="^", ls="", ms=4, label="Sonde non atteinte (NaN)"))
            if any(len(b.table.forme) > 1 for b in page):
                poignees.append(Line2D([], [], color=GRIS, lw=0.6, label="Blocs de l'axe le plus lent"))
            _legende_sous(fig, poignees, ncol=len(poignees))
            titre = f"{res.identifiant} — Lecture des tables sur leurs nœuds : {res.verdict}"
            if len(pages) > 1:
                titre += f" ({p + 1}/{len(pages)})"
            cp.set_suptitle(fig, titre, fontsize=9.5)
            fichiers += _enregistrer(fig, chemin.with_name(chemin.name + _suffixe(p, len(pages))), formats)
    return fichiers


def tracer_figures_tables(
    res: ResultatLectureTables, dossier: str | Path, *, formats: Sequence[str] = FORMATS_TABLES
) -> list[Path]:
    """Les figures du test dans ``dossier`` ; lève ``FiguresIndisponibles`` sans cfd-plot."""
    _cfd_plot()
    d = Path(dossier)
    d.mkdir(parents=True, exist_ok=True)
    return figure_synthese_tables(res, d / "synthese_tables", formats)
