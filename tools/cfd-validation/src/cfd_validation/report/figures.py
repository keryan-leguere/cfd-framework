"""Figures justificatives du test d'intégration, tracées avec ``cfd-plot`` (profil « paper »).

Chaque figure est écrite en PNG (300 dpi) et en PDF vectoriel, prête pour un
rapport. Toutes tracent la **marge** — l'écart signé en unités de tolérance,
``(test − réf) / (atol + rtol·|réf|)`` — sur un axe *symlog* linéaire dans
[−1, 1] : la bande d'acceptation a la même hauteur pour toutes les sorties, un
bruit d'arrondi s'y lit à l'échelle, une régression au-delà sur une échelle
logarithmique. Les figures :

- ``01_synthese_sorties`` : une ligne par sortie, |marge| de la médiane au
  maximum (99e centile marqué), part identique et nombre d'échecs à droite. La
  seule vue qui reste lisible à 15, 30 ou 50 sorties : c'est la pièce de tête ;
- ``02_marges_par_sortie`` : marge contre valeur de référence, un panneau par
  sortie (12 par page). Montre si l'écart dépend du niveau de la sortie et où
  sont les points hors tolérance ;
- ``03_repartition_marges`` : fonction de répartition de |marge|, une courbe
  par sortie, 7 par page pour qu'aucune couleur ne serve deux fois. La part
  identique bit pour bit en est l'ordonnée à l'origine ;
- ``04_marges_<k>_<sortie>`` : marge contre chaque entrée, pour une sortie,
  l'entrée la plus liée aux échecs en premier. Par défaut pour les seules
  sorties en échec (``par_entree``) : c'est là qu'une régression localisée se
  voit, et 15 sorties conformes × 10 entrées feraient des dizaines de pages
  sans information. ``<k>`` est le rang de la sortie : ``CN`` et ``Cn``
  donneraient sinon le même fichier sur un disque insensible à la casse
  (Windows, macOS) ;
- ``05_taux_echec_par_entree`` : taux de lignes en échec par niveau de chaque
  entrée, les plus liées d'abord, absentes empilées, taux global en tireté ;
- ``06_liaison_entrees_sorties`` : V de Cramér entrée × sortie (si échec).

Couleurs Okabe-Ito, lisibles en cas de daltonisme ; les statuts se
distinguent aussi par la forme du marqueur, donc en niveaux de gris.

``cfd-plot`` est un paquet frère de ce dépôt, pas une dépendance : sans lui,
:func:`tracer_figures` lève :class:`FiguresIndisponibles` et le reste du
contrôle (terminal, journal, CSV, JSON) n'est pas affecté. ::

    pip install -e ../cfd-plot
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import numpy as np
import pandas as pd

from cfd_validation.core import statuts as st
from cfd_validation.core.format import formater, pourcentage
from cfd_validation.engine.integration import AttributionEntree, BilanSortie, ResultatIntegration

__all__ = [
    "FORMATS",
    "PAR_ENTREE",
    "FiguresIndisponibles",
    "figure_liaison",
    "figure_marges_entrees",
    "figure_marges_sorties",
    "figure_repartition",
    "figure_synthese",
    "figure_taux_echec",
    "tracer_figures",
]

PROFIL = "paper"
DPI = 300
FORMATS: tuple[str, ...] = ("png", "pdf")
#: Largeur utile d'une page de rapport (pouces).
PAGE = 7.0
#: Hauteur d'une rangée de panneaux (pouces).
RANGEE = 2.2
#: Panneaux par figure avant pagination (``_01``, ``_02``…) : 3 × 4 tiennent sur une page A4.
PANNEAUX_MAX = 12
COLONNES = 3
#: Courbes par figure de répartition : une couleur Okabe-Ito chacune, jamais deux fois la même.
COURBES_MAX = 7
#: Sorties par page de synthèse.
SORTIES_PAR_SYNTHESE = 30
#: ``par_entree`` : figures 04 pour les sorties en échec, pour toutes, ou pour aucune.
PAR_ENTREE = ("echecs", "toutes", "aucune")

# Okabe-Ito.
BLEU, ORANGE, VERT, VERMILLON, CIEL, POURPRE, JAUNE = (
    "#0072B2", "#E69F00", "#009E73", "#D55E00", "#56B4E9", "#CC79A7", "#F0E442",
)
GRIS = "0.55"
BANDE = "#E3EEF7"
COULEURS_SERIES = (BLEU, VERMILLON, VERT, ORANGE, POURPRE, CIEL, "0.25")

#: Apparence de chaque statut de valeur : (couleur, marqueur, taille, libellé).
_STYLE = {
    st.IDENTIQUE: (GRIS, ".", 4, "identique"),
    st.TOLERE: (BLEU, "o", 9, "dans la tolérance"),
    st.ECART: (VERMILLON, "D", 14, "hors tolérance"),
    st.NON_FINI: ("k", "x", 22, "non fini divergent"),
}
_CODE = {v: k for k, v in st.NOMS.items()}


class FiguresIndisponibles(RuntimeError):
    """``cfd-plot`` (ou Matplotlib) n'est pas installé."""


@lru_cache(maxsize=1)
def _cfd_plot() -> ModuleType:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import cfd_plot
    except ImportError as erreur:
        raise FiguresIndisponibles(
            f"figures indisponibles ({erreur.name} manquant) : pip install -e ../cfd-plot"
        ) from None
    return cast(ModuleType, cfd_plot)


@contextmanager
def _style() -> Iterator[ModuleType]:
    """Profil « paper » de cfd-plot, titres en maigre, tailles d'article."""
    import matplotlib as mpl

    cp = _cfd_plot()
    reglages: dict[str, Any] = {
        "axes.titleweight": "normal",
        "axes.titlesize": 9.0,
        "axes.labelsize": 8.5,
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
        "legend.fontsize": 7.5,
        "figure.dpi": 100,
        "savefig.dpi": DPI,
    }
    with cp.style_context(PROFIL), mpl.rc_context(reglages):  # type: ignore[arg-type]
        yield cp


def _fichier(nom: str) -> str:
    # Pas de point : save_figure compose les extensions avec Path.with_suffix,
    # et « Cm_M0.8 » y perdrait son « .8 ».
    return re.sub(r"[^0-9A-Za-z_-]+", "_", nom).strip("_") or "sortie"


def _enregistrer(fig: Any, chemin: Path, formats: Sequence[str]) -> list[Path]:
    import matplotlib.pyplot as plt

    fichiers = _cfd_plot().save_figure(fig, chemin, formats=tuple(formats), dpi=DPI)
    plt.close(fig)
    return [Path(f) for f in fichiers]


def _paginer(elements: Sequence[Any], taille: int = PANNEAUX_MAX) -> list[Sequence[Any]]:
    return [elements[i : i + taille] for i in range(0, len(elements), taille)] or [[]]


def _suffixe(page: int, n_pages: int) -> str:
    return f"_{page + 1:02d}" if n_pages > 1 else ""


def _grille(cp: ModuleType, n: int, *, hauteur: float = RANGEE) -> tuple[Any, list[Any]]:
    ncols = min(COLONNES, max(n, 1))
    nrows = max(1, math.ceil(n / ncols))
    fig, axes = cp.new_figure(nrows, ncols, figsize=(PAGE, hauteur * nrows + 0.5), squeeze=False, layout="constrained")
    plats = list(np.asarray(axes).ravel())
    for ax in plats[n:]:
        ax.set_visible(False)
    return fig, plats[:n]


# ---------------------------------------------------------------------------
# Échelle des marges
# ---------------------------------------------------------------------------


def _etiquette_marge(v: float, _pos: Any = None) -> str:
    """``0``, ``±1``, ``10³``, ``−10⁵``.

    Les exposants passent par mathtext, et la chaîne n'est **que** du mathtext :
    la police du corps (TeX Gyre Termes) n'a pas les chiffres en exposant
    Unicode, et mêler texte et ``$…$`` réclamerait ses glyphes à la police
    mathématique.
    """
    if v == 0:
        return "$0$"
    e = round(math.log10(abs(v)))
    signe = "-" if v < 0 else ""
    return f"${signe}1$" if e == 0 else f"${signe}10^{{{e}}}$"


def _axe_marge(ax: Any, marges: np.ndarray) -> None:
    """Axe y symlog (linéaire dans [−1, 1]), bande d'acceptation, au plus ~5 décades par côté."""
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

    ax.set_yscale("symlog", linthresh=1.0, linscale=1.0)
    finies = np.abs(marges[np.isfinite(marges)])
    haut = max(2.0, float(finies.max()) * 2.0) if finies.size else 2.0
    ax.set_ylim(-haut, haut)
    decade_max = max(1, math.ceil(math.log10(haut)))
    pas = max(1, math.ceil(decade_max / 5))
    decades = [10.0**e for e in range(pas, decade_max + 1, pas) if 10.0**e <= haut]
    ax.yaxis.set_major_locator(FixedLocator([-d for d in reversed(decades)] + [-1.0, 0.0, 1.0] + decades))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_major_formatter(FuncFormatter(_etiquette_marge))
    ax.axhspan(-1.0, 1.0, color=BANDE, zorder=0, lw=0)
    _cfd_plot().add_reference_lines(ax, hlines=[-1.0, 1.0], color=BLEU, linewidth=0.7, linestyle="--", zorder=1)
    ax.axhline(0.0, color="0.3", lw=0.5, zorder=1)


def _points(ax: Any, x: np.ndarray, marges: np.ndarray, codes: np.ndarray, *, legende: bool) -> None:
    """Un nuage par statut ; les non finis épinglés en haut du panneau."""
    from matplotlib.transforms import blended_transform_factory

    for code in (st.IDENTIQUE, st.TOLERE, st.ECART):
        dans = codes == code
        if dans.any():
            couleur, marqueur, taille, libelle = _STYLE[code]
            ax.scatter(
                x[dans], marges[dans], s=taille, marker=marqueur, color=couleur,
                edgecolors="none" if marqueur in ".x" else "white", linewidths=0.3,
                label=f"{libelle} ({int(dans.sum())})" if legende else None, zorder=2 + code,
            )
    nf = codes == st.NON_FINI
    if nf.any():
        couleur, marqueur, taille, libelle = _STYLE[st.NON_FINI]
        trans = blended_transform_factory(ax.transData, ax.transAxes)
        xs = np.where(np.isfinite(x[nf]), x[nf], np.nan)
        ax.scatter(xs, np.full(xs.shape, 0.97), s=taille, marker=marqueur, color=couleur, transform=trans, clip_on=False,
                   label=f"{libelle} ({int(nf.sum())})" if legende else None, zorder=6)


def _titre_panneau(cp: ModuleType, ax: Any, texte: str) -> None:
    """Titre d'un panneau d'un tiers de page : réduit au-delà de ~28 caractères pour ne pas déborder."""
    cp.set_title(ax, texte, fontsize=9.0 if len(texte) <= 28 else 7.5 if len(texte) <= 36 else 6.5)


def _sous_titre(b: BilanSortie) -> str:
    """Une ligne qui tient sous un panneau d'un tiers de page (~45 caractères)."""
    return f"{b.n} valeurs · {pourcentage(b.n_identiques, b.n)} identiques · {b.n_echecs} en échec"


def _donnees_sortie(res: ResultatIntegration, nom: str) -> pd.DataFrame:
    df = res.ecarts[res.ecarts["sortie"] == nom]
    return df.assign(_code=df["statut"].map(_CODE).to_numpy())


def _numeriques(res: ResultatIntegration) -> list[BilanSortie]:
    return [b for b in res.sorties if b.presente and b.numerique and b.n]


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def _stats_marge(m: np.ndarray) -> tuple[float, float, float] | None:
    """Médiane, 99e centile et maximum de |marge| sur les valeurs non identiques et finies."""
    pos = m[np.isfinite(m) & (m > 0)]
    if not pos.size:
        return None
    return float(np.median(pos)), float(np.quantile(pos, 0.99)), float(pos.max())


def figure_synthese(res: ResultatIntegration, chemin: Path, formats: Sequence[str] = FORMATS) -> list[Path]:
    """Une ligne par sortie : |marge| de la médiane au maximum, sur une même échelle log."""
    from matplotlib.lines import Line2D
    from matplotlib.transforms import blended_transform_factory

    bilans = _numeriques(res)
    pages = _paginer(bilans, SORTIES_PAR_SYNTHESE)
    fichiers: list[Path] = []
    for p, page in enumerate(pages):
        if not page:
            break
        marges = {b.nom: np.abs(_donnees_sortie(res, b.nom)["marge"].to_numpy(dtype=float)) for b in page}
        stats = {nom: _stats_marge(m) for nom, m in marges.items()}
        minima = [st_[0] for st_ in stats.values() if st_ is not None]
        maxima = [st_[2] for st_ in stats.values() if st_ is not None]
        bas = min(min(minima) / 5 if minima else 1e-3, 1e-1)
        haut = max(max(maxima) * 5 if maxima else 10.0, 10.0)
        n = len(page)
        with _style() as cp:
            fig, ax = cp.new_figure(figsize=(PAGE, 1.3 + 0.24 * n), layout="constrained")
            ax.axvspan(bas, 1.0, color=BANDE, zorder=0, lw=0)
            cp.add_reference_lines(ax, vlines=[1.0], color=BLEU, linewidth=0.9)
            bord = blended_transform_factory(ax.transAxes, ax.transData)
            for i, b in enumerate(page):
                y = n - 1 - i
                couleur = VERMILLON if b.n_echecs else BLEU
                ax.axhline(y, color="0.92", lw=0.5, zorder=0)
                st_ = stats[b.nom]
                if st_ is None:  # tout identique (ou tout non fini)
                    ax.scatter([bas * 1.6], [y], s=16, marker="o", facecolors="white", edgecolors=GRIS, zorder=3)
                else:
                    mediane, p99, maximum = st_
                    ax.hlines(y, mediane, maximum, color=couleur, lw=1.6, zorder=2)
                    ax.plot([p99], [y], marker="|", ms=7, mew=1.2, color=couleur, zorder=3)
                    ax.scatter([maximum], [y], s=20, marker="D" if b.n_ecarts else "o", color=couleur,
                               edgecolors="white", linewidths=0.3, zorder=4)
                if b.n_non_finis:
                    ax.plot([0.985], [y], marker="x", ms=5, mew=1.3, color="k", transform=bord, clip_on=False, zorder=5)
                ax.annotate(
                    f"{pourcentage(b.n_identiques, b.n)} ident. · {b.n_echecs} échec{'s' if b.n_echecs > 1 else ''}",
                    xy=(1.0, y), xycoords=bord, xytext=(5, 0), textcoords="offset points",
                    ha="left", va="center", fontsize=6.5, color=VERMILLON if b.n_echecs else "0.3",
                )
            ax.set_xscale("log")
            ax.set_xlim(bas, haut)
            ax.set_ylim(-0.7, n - 0.3)
            ax.set_yticks(range(n), [b.nom for b in reversed(page)])
            ax.tick_params(axis="y", length=0)
            ax.set_xlabel("|marge| = |Δ| / tolérance   (≤ 1 : accepté)")
            cp.set_title(ax, f"{res.identifiant} — synthèse par sortie" + (f" ({p + 1}/{len(pages)})" if len(pages) > 1 else ""))
            poignees = [
                Line2D([], [], color=BLEU, lw=1.6, label="médiane → maximum"),
                Line2D([], [], color=BLEU, marker="|", ms=7, mew=1.2, ls="", label="99e centile"),
                Line2D([], [], color=VERMILLON, marker="D", ms=4.5, ls="", label="maximum hors tolérance"),
                Line2D([], [], color="k", marker="x", ms=5, mew=1.3, ls="", label="non fini"),
                Line2D([], [], color=GRIS, marker="o", mfc="white", ms=4.5, ls="", label="tout identique"),
            ]
            _legende_sous(fig, poignees, ncol=5)
            fichiers += _enregistrer(fig, chemin.with_name(chemin.name + _suffixe(p, len(pages))), formats)
    return fichiers


def _legende_sous(fig: Any, poignees: Sequence[Any], *, ncol: int) -> None:
    libelles = [h.get_label() for h in poignees]
    try:  # Matplotlib ≥ 3.7 : la mise en page contrainte lui réserve sa place
        fig.legend(poignees, libelles, loc="outside lower center", ncol=ncol, frameon=False)
    except ValueError:
        fig.legend(poignees, libelles, loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=ncol, frameon=False)


def figure_marges_sorties(res: ResultatIntegration, chemin: Path, formats: Sequence[str] = FORMATS) -> list[Path]:
    """Marge contre valeur de référence, un panneau par sortie."""
    bilans = _numeriques(res)
    pages = _paginer(bilans)
    fichiers: list[Path] = []
    for p, page in enumerate(pages):
        if not page:
            break
        with _style() as cp:
            fig, axes = _grille(cp, len(page))
            for i, (ax, b) in enumerate(zip(axes, page)):
                df = _donnees_sortie(res, b.nom)
                marges = df["marge"].to_numpy(dtype=float)
                _axe_marge(ax, marges)
                _points(ax, df["reference"].to_numpy(dtype=float), marges, df["_code"].to_numpy(), legende=True)
                cp.set_title(ax, f"{b.nom} :  {b.tolerance.decrire()}", fontsize=8.5)
                cp.set_subtitle(ax, _sous_titre(b), fontsize=6.5)
                ax.set_xlabel(f"{b.nom} de référence")
                if i % COLONNES == 0:
                    ax.set_ylabel("marge = Δ / tolérance")
            _legende_figure(fig, axes)
            cp.set_suptitle(fig, f"{res.identifiant} — écart de chaque valeur, en unités de tolérance (bande : accepté)", fontsize=9.5)
            fichiers += _enregistrer(fig, chemin.with_name(chemin.name + _suffixe(p, len(pages))), formats)
    return fichiers


def _legende_figure(fig: Any, axes: Sequence[Any]) -> None:
    """Une légende commune, sous la figure, sans doublons de statut."""
    vus: dict[str, Any] = {}
    for ax in axes:
        for poignee, libelle in zip(*ax.get_legend_handles_labels()):
            cle = libelle.split(" (")[0]
            vus.setdefault(cle, poignee)
    if not vus:
        return
    options = {"ncol": len(vus), "frameon": False, "markerscale": 1.5}
    try:  # Matplotlib ≥ 3.7 : la mise en page contrainte lui réserve sa place
        fig.legend(list(vus.values()), list(vus.keys()), loc="outside lower center", **options)
    except ValueError:  # plus ancien : sous la figure, bbox_inches="tight" l'englobe
        fig.legend(list(vus.values()), list(vus.keys()), loc="upper center", bbox_to_anchor=(0.5, 0.0), **options)


def figure_repartition(res: ResultatIntegration, chemin: Path, formats: Sequence[str] = FORMATS) -> list[Path]:
    """Fonction de répartition de |marge|, une courbe par sortie, ``COURBES_MAX`` par page."""
    pages = _paginer(_numeriques(res), COURBES_MAX)
    fichiers: list[Path] = []
    for p, page in enumerate(pages):
        if page:
            fichiers += _repartition_page(res, page, chemin.with_name(chemin.name + _suffixe(p, len(pages))), formats)
    return fichiers


def _repartition_page(res: ResultatIntegration, bilans: Sequence[BilanSortie], chemin: Path, formats: Sequence[str]) -> list[Path]:
    with _style() as cp:
        fig, ax = cp.new_figure(figsize=(PAGE * 0.7, 3.4), layout="constrained")
        positives = [np.abs(_donnees_sortie(res, b.nom)["marge"].to_numpy(dtype=float)) for b in bilans]
        toutes = np.concatenate([m[np.isfinite(m) & (m > 0)] for m in positives] or [np.array([])])
        bas = float(toutes.min()) / 3 if toutes.size else 1e-3
        haut = max(float(toutes.max()) * 3 if toutes.size else 10.0, 10.0)
        bas = min(bas, 1e-1)
        for k, (b, m) in enumerate(zip(bilans, positives)):
            n = m.size
            finies = np.sort(m[np.isfinite(m)])
            part0 = float((finies == 0).sum()) / n
            pos = finies[finies > 0]
            x = np.concatenate([[bas], pos, [haut]])
            y = np.concatenate([[part0], part0 + np.arange(1, pos.size + 1) / n, [(part0 * n + pos.size) / n]])
            libelle = f"{b.nom} — {pourcentage(b.n_identiques, b.n)} identiques"
            if b.n_non_finis:
                libelle += f", {b.n_non_finis} non fini(s)"
            ax.step(x, y, where="post", color=COULEURS_SERIES[k % len(COULEURS_SERIES)], lw=1.3, label=libelle)
        ax.set_xscale("log")
        ax.set_xlim(bas, haut)
        ax.set_ylim(-0.02, 1.04)
        ax.axvspan(bas, 1.0, color=BANDE, zorder=0, lw=0)
        cp.add_reference_lines(ax, vlines=[1.0], color=BLEU, linewidth=0.9)
        ax.text(0.97, 0.03, "accepté ", color=BLEU, fontsize=7, ha="right", va="bottom", transform=ax.get_xaxis_transform())
        ax.text(1.03, 0.03, " refusé", color=VERMILLON, fontsize=7, ha="left", va="bottom", transform=ax.get_xaxis_transform())
        ax.set_xlabel("|marge| = |Δ| / tolérance")
        ax.set_ylabel("part des valeurs ≤ |marge|")
        cp.set_title(ax, f"{res.identifiant} — répartition des écarts")
        cp.set_subtitle(ax, "ordonnée à l'origine : part identique bit pour bit ; palier final < 1 : valeurs non finies", fontsize=7)
        _legende_sous(fig, ax.get_legend_handles_labels()[0], ncol=2)
        return _enregistrer(fig, chemin, formats)


def _abscisse_entree(valeurs: pd.Series) -> tuple[np.ndarray, list[str] | None]:
    if pd.api.types.is_numeric_dtype(valeurs) and not pd.api.types.is_bool_dtype(valeurs):
        return valeurs.to_numpy(dtype=float, na_value=np.nan), None
    textes = valeurs.astype(str)
    niveaux = sorted(textes.unique())
    rang = {n: i for i, n in enumerate(niveaux)}
    return textes.map(rang).to_numpy(dtype=float), niveaux


def figure_marges_entrees(res: ResultatIntegration, b: BilanSortie, chemin: Path, formats: Sequence[str] = FORMATS) -> list[Path]:
    """Marge d'une sortie contre chacune des entrées."""
    df = _donnees_sortie(res, b.nom)
    entrees = res.entrees_par_pertinence(b.nom)
    pages = _paginer(entrees)
    marges = df["marge"].to_numpy(dtype=float)
    codes = df["_code"].to_numpy()
    v_par_entree = {a.entree: a.v_par_sortie.get(b.nom, math.nan) for a in res.attributions}
    fichiers: list[Path] = []
    for p, page in enumerate(pages):
        with _style() as cp:
            fig, axes = _grille(cp, len(page))
            for i, (ax, entree) in enumerate(zip(axes, page)):
                x, niveaux = _abscisse_entree(df[entree])
                # Léger étalement horizontal des niveaux discrets : sans lui, cent points superposés n'en font qu'un.
                if niveaux is not None:
                    x = x + np.random.default_rng(0).uniform(-0.18, 0.18, x.size)
                _axe_marge(ax, marges)
                _points(ax, x, marges, codes, legende=True)
                if niveaux is not None:
                    ax.set_xticks(range(len(niveaux)), niveaux, rotation=30 if len(niveaux) > 4 else 0)
                v = v_par_entree.get(entree, math.nan)
                titre = entree if math.isnan(v) else f"{entree}   (V = {formater(v, 2)})"
                _titre_panneau(cp, ax, titre)
                ax.set_xlabel(entree)
                if i % COLONNES == 0:
                    ax.set_ylabel(f"marge de {b.nom}")
            _legende_figure(fig, axes)
            cp.set_suptitle(fig, f"{res.identifiant} — {b.nom} : écart en unités de tolérance selon chaque entrée", fontsize=9.5)
            fichiers += _enregistrer(fig, chemin.with_name(chemin.name + _suffixe(p, len(pages))), formats)
    return fichiers


def figure_taux_echec(res: ResultatIntegration, chemin: Path, formats: Sequence[str] = FORMATS) -> list[Path]:
    """Taux de lignes de référence en échec par niveau de chaque entrée."""
    par_nom = {a.entree: a for a in res.attributions}
    attributions = [par_nom[n] for n in res.entrees_par_pertinence()]
    pages = _paginer(attributions)
    taux_global = res.taux_echec
    fichiers: list[Path] = []
    for p, page in enumerate(pages):
        with _style() as cp:
            fig, axes = _grille(cp, len(page), hauteur=RANGEE + 0.2)
            for i, (ax, a) in enumerate(zip(axes, page)):
                _barres_niveaux(cp, ax, a, taux_global)
                if i % COLONNES == 0:
                    ax.set_ylabel("lignes en échec (%)")
            _legende_figure(fig, axes)
            cp.set_suptitle(
                fig,
                f"{res.identifiant} — taux d'échec par niveau d'entrée (global : {pourcentage(res.n_lignes_echec, res.structure.n_ref)})",
                fontsize=9.5,
            )
            fichiers += _enregistrer(fig, chemin.with_name(chemin.name + _suffixe(p, len(pages))), formats)
    return fichiers


def _barres_niveaux(cp: ModuleType, ax: Any, a: AttributionEntree, taux_global: float) -> None:
    n = np.array([niv.n for niv in a.niveaux], dtype=float)
    absentes = np.array([niv.n_absentes for niv in a.niveaux], dtype=float)
    echecs = np.array([niv.n_echecs for niv in a.niveaux], dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        t_abs = np.where(n > 0, 100 * absentes / n, 0.0)
        t_cmp = np.where(n > 0, 100 * (echecs - absentes) / n, 0.0)
    pos = np.arange(len(a.niveaux))
    cp.plot_bar(ax, pos, t_cmp, color=VERMILLON, label="hors tolérance / non fini", width=0.72)
    cp.plot_bar(ax, pos, t_abs, bottom=t_cmp, color=ORANGE, label="absente du test", width=0.72, hatch="///")
    if math.isfinite(taux_global) and taux_global > 0:
        cp.add_reference_lines(ax, hlines=[100 * taux_global], color="0.2", linewidth=0.8, label="taux global")
    ax.set_ylim(0, 105)
    # Un panneau d'un tiers de page loge ~30 caractères à plat.
    tourner = sum(len(niv.libelle) + 1 for niv in a.niveaux) > 30
    ax.set_xticks(pos, [niv.libelle for niv in a.niveaux], rotation=35 if tourner else 0,
                  ha="right" if tourner else "center", fontsize=6.5 if tourner else 7.5)
    titre = a.entree if math.isnan(a.v) else f"{a.entree}   (V = {formater(a.v, 2)})"
    _titre_panneau(cp, ax, titre)


def figure_liaison(res: ResultatIntegration, chemin: Path, formats: Sequence[str] = FORMATS) -> list[Path]:
    """V de Cramér entrée × sortie, annoté."""
    presentes = [b.nom for b in res.sorties if b.presente]
    if not presentes or res.n_lignes_echec == 0:
        return []
    par_nom = {a.entree: a for a in res.attributions}
    entrees = res.entrees_par_pertinence()
    z = np.array([[par_nom[e].v_par_sortie.get(s, math.nan) for s in presentes] for e in entrees], dtype=float)
    n_col = len(presentes)
    long_nom = max(len(s) for s in presentes)
    tourner = n_col > 6 or long_nom > 6
    police = 7.5 if n_col <= 8 else 6.0 if n_col <= 15 else 5.0
    with _style() as cp:
        largeur = min(PAGE, 1.8 + 0.5 * n_col + 0.05 * max(len(e) for e in entrees))
        hauteur = 1.0 + 0.3 * len(entrees) + (0.06 * long_nom if tourner else 0.0)
        fig, ax = cp.new_figure(figsize=(largeur, hauteur), layout="constrained")
        image = ax.imshow(np.ma.masked_invalid(z), cmap="Reds", vmin=0.0, vmax=1.0, aspect="auto")
        for (i, j), v in np.ndenumerate(z):
            texte = "—" if math.isnan(v) else f"{v:.2f}"
            ax.text(j, i, texte, ha="center", va="center", fontsize=police, color="white" if (not math.isnan(v) and v > 0.6) else "0.15")
        ax.set_xticks(range(n_col), presentes, rotation=45 if tourner else 0, ha="right" if tourner else "center",
                      rotation_mode="anchor" if tourner else "default")
        ax.set_yticks(range(len(entrees)), entrees)
        ax.tick_params(length=0)
        barre = fig.colorbar(image, ax=ax, shrink=0.9)
        barre.set_label("V de Cramér")
        cp.set_title(ax, f"{res.identifiant} — liaison entrée × échec de la sortie")
        return _enregistrer(fig, chemin, formats)


def tracer_figures(
    res: ResultatIntegration,
    dossier: str | Path,
    *,
    formats: Sequence[str] = FORMATS,
    par_entree: str = "echecs",
) -> list[Path]:
    """Toutes les figures du test dans ``dossier`` ; renvoie les fichiers écrits.

    ``par_entree`` : figures « marge contre chaque entrée » (04) pour les sorties
    en échec (``"echecs"``, défaut), pour toutes (``"toutes"``) ou pour aucune.
    """
    if par_entree not in PAR_ENTREE:
        raise ValueError(f"par_entree={par_entree!r} : attendu {', '.join(PAR_ENTREE)}")
    _cfd_plot()  # échoue tôt, avant de créer quoi que ce soit
    d = Path(dossier)
    d.mkdir(parents=True, exist_ok=True)
    fichiers = figure_synthese(res, d / "01_synthese_sorties", formats)
    fichiers += figure_marges_sorties(res, d / "02_marges_par_sortie", formats)
    fichiers += figure_repartition(res, d / "03_repartition_marges", formats)
    if not res.specification.entrees:  # 04 à 06 croisent les sorties avec les entrées
        return fichiers
    rang = {b.nom: k + 1 for k, b in enumerate(res.sorties)}
    for b in _numeriques(res):
        if par_entree == "toutes" or (par_entree == "echecs" and b.n_echecs):
            fichiers += figure_marges_entrees(res, b, d / f"04_marges_{rang[b.nom]:02d}_{_fichier(b.nom)}", formats)
    fichiers += figure_taux_echec(res, d / "05_taux_echec_par_entree", formats)
    fichiers += figure_liaison(res, d / "06_liaison_entrees_sorties", formats)
    return fichiers
