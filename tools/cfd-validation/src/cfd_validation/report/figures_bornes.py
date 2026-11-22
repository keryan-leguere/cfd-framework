"""Figure de synthèse du test des bornes de table (cfd-plot, profil « paper », SVG).

Un panneau par table, six par page. En abscisse, les points hors bornes, face
après face (``mach−``, ``mach+``, ``alpha−``…), chacune séparée par un trait et
étiquetée en tête par son nom et sa consigne (S : sature, E : extrapole) ; dans
une face, les autres axes parcourent leurs nœuds en ordre de lecture. En
ordonnée, la grandeur :

- points bleus : la valeur **attendue** selon la consigne ;
- cercles gris : la valeur de **l'autre** consigne — là où les croix tombent
  dessus, le code fait l'autre chose que ce qu'on lui demande ;
- croix vermillon : le code, au-dessus, plus petites que les points ;
- anneau noir : hors tolérance ; triangle au pied : sonde non atteinte.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from cfd_validation.core import statuts as st
from cfd_validation.core.bornes import SATURE
from cfd_validation.engine.bornes_tables import BilanBornes, ResultatBornesTables
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
from cfd_validation.report.figures_tables import (
    COLONNES_TABLES,
    FORMATS_TABLES,
    HAUTEUR_PANNEAU,
    PANNEAUX_PAR_PAGE,
    TRAME_AU_DELA,
    _tailles,
)

__all__ = ["figure_synthese_bornes", "tracer_figures_bornes"]

INITIALE = {"sature": "S", "extrapole": "E"}


def _panneau(cp: Any, ax: Any, b: BilanBornes) -> None:
    from matplotlib.ticker import MaxNLocator
    from matplotlib.transforms import blended_transform_factory

    r = b.resultats
    x = np.arange(len(r))
    s_tab, s_code, epaisseur = _tailles(max(f.n_points for f in b.faces))
    tramer = len(r) > TRAME_AU_DELA
    attendu = r["valeur_ATTENDUE"].to_numpy(dtype=float)
    autre = np.where(r["consigne"].to_numpy() == SATURE, r["valeur_EXTRAPOLATION"].to_numpy(dtype=float),
                     r["valeur_SATURATION"].to_numpy(dtype=float))
    code = r["valeur_CODE"].to_numpy(dtype=float)
    fini = np.isfinite(code)
    differe = ~np.isclose(autre, attendu, rtol=1e-12, atol=1e-15)  # l'autre consigne n'a de sens que si elle diffère
    dense = len(r) > 400
    ax.scatter(x[differe], autre[differe], s=s_tab * (0.5 if dense else 0.8), marker="o", facecolors="none",
               edgecolors=GRIS, linewidths=0.25 if dense else 0.5, zorder=1, rasterized=tramer)
    ax.scatter(x, attendu, s=s_tab, marker="o", color=BLEU, linewidths=0, zorder=2, rasterized=tramer)
    ax.scatter(x[fini], code[fini], s=s_code, marker="x", color=VERMILLON, linewidths=epaisseur, zorder=3,
               rasterized=tramer)
    hors = (~r["conforme"].to_numpy()) & fini
    if hors.any():
        rare = int(hors.sum()) <= 50
        ax.scatter(x[hors], code[hors], s=36 if rare else max(s_tab * 1.5, 4.0), marker="o", facecolors="none",
                   edgecolors="k", linewidths=0.8 if rare else 0.3, zorder=5, rasterized=tramer)
    nf = r["statut"].to_numpy() == st.NOMS[st.NON_FINI]
    trans = blended_transform_factory(ax.transData, ax.transAxes)
    if nf.any():
        ax.scatter(x[nf], np.full(int(nf.sum()), 0.02), s=10, marker="^", color="k", transform=trans,
                   clip_on=False, zorder=6)
    debut = 0
    for k, f in enumerate(b.faces):
        if k:
            ax.axvline(debut - 0.5, color="0.80", lw=0.5, zorder=0)
        couleur = "0.35" if f.conforme else VERMILLON
        ax.text(debut + f.n_points / 2 - 0.5, 1.0, f"{f.face.nom} {INITIALE[f.face.consigne]}", transform=trans,
                ha="center", va="bottom", fontsize=5.5 if len(b.faces) <= 8 else 4.8, color=couleur)
        debut += f.n_points
    n = len(r)
    ax.set_xlim(-0.5 - 0.01 * n, n - 0.5 + 0.01 * n)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))  # un rang de point : jamais 0.25
    ax.set_xlabel("Points hors bornes, face par face", fontsize=7)
    ax.set_ylabel(b.nom, fontsize=7.5)
    verdict = "Conforme" if b.conforme else f"NON CONFORME ({b.n_echecs})"
    cp.set_title(ax, f"{b.nom} — {b.table.decrire_forme}", fontsize=8.5)
    nt = f" · {len(b.non_testees)} inatteignable(s)" if b.non_testees else ""
    cp.set_subtitle(ax, f"{len(b.faces)} faces{nt} · {n} points · {verdict}", fontsize=6.5,
                    color=VERMILLON if not b.conforme else "0.3")


def figure_synthese_bornes(res: ResultatBornesTables, chemin: Path, formats: Sequence[str] = FORMATS_TABLES) -> list[Path]:
    """Valeur attendue, valeur de l'autre consigne et valeur lue par le code, face par face."""
    from matplotlib.lines import Line2D

    pages = _paginer(list(res.tables), PANNEAUX_PAR_PAGE)
    fichiers: list[Path] = []
    for p, page in enumerate(pages):
        if not page:
            break
        ncols = min(COLONNES_TABLES, len(page))
        nrows = math.ceil(len(page) / ncols)
        with _style() as cp:
            fig, axes = cp.new_figure(nrows, ncols, figsize=(PAGE, HAUTEUR_PANNEAU * nrows + 0.8),
                                      squeeze=False, layout="constrained")
            plats = list(np.asarray(axes).ravel())
            for ax in plats[len(page):]:
                ax.set_visible(False)
            for ax, b in zip(plats, page):
                _panneau(cp, ax, b)
            poignees = [
                Line2D([], [], color=BLEU, marker="o", ls="", ms=4, label="Attendu (consigne)"),
                Line2D([], [], color=GRIS, marker="o", mfc="none", ls="", ms=4, label="L'autre consigne"),
                Line2D([], [], color=VERMILLON, marker="x", ls="", ms=5, label="Code"),
            ]
            if any(not b.conforme for b in page):
                poignees.append(Line2D([], [], color="k", marker="o", mfc="none", ls="", ms=6, label="Hors tolérance"))
            if any((b.resultats["statut"] == st.NOMS[st.NON_FINI]).any() for b in page):
                poignees.append(Line2D([], [], color="k", marker="^", ls="", ms=4, label="Sonde non atteinte (NaN)"))
            _legende_sous(fig, poignees, ncol=len(poignees))
            titre = f"{res.identifiant} — Tables appelées hors bornes (S : saturé, E : extrapolé) : {res.verdict}"
            if len(pages) > 1:
                titre += f" ({p + 1}/{len(pages)})"
            cp.set_suptitle(fig, titre, fontsize=9.0)
            fichiers += _enregistrer(fig, chemin.with_name(chemin.name + _suffixe(p, len(pages))), formats)
    return fichiers


def tracer_figures_bornes(
    res: ResultatBornesTables, dossier: str | Path, *, formats: Sequence[str] = FORMATS_TABLES
) -> list[Path]:
    """Les figures du test dans ``dossier`` ; lève ``FiguresIndisponibles`` sans cfd-plot."""
    _cfd_plot()
    d = Path(dossier)
    d.mkdir(parents=True, exist_ok=True)
    return figure_synthese_bornes(res, d / "synthese_bornes", formats)
