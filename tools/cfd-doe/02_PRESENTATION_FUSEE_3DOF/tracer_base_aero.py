"""Tracés d'une base aéro 3DOF tangage, prêts pour la présentation, avec cfd-plot.

Entrées : deux DataFrames, et rien d'autre (aucune dépendance au modèle qui les a produits).

- **tables carrées** : une ligne par nœud Mach × α × DM, une colonne par coefficient
  (CA, CN, Cm) — ce que ``cfd-doe`` reconstruit, complété par symétrie ;
- **table d'incrément** : ΔzCA(Mach, altitude), ajouté au CA lu dans la table.

Les noms de colonnes sont des paramètres (:data:`COLONNES`, :data:`COLONNES_INCREMENT`).

Ce qui est tracé, et avec quelle fonctionnalité de cfd-plot :

=====================  ===========================================  ==================================
Figures                 Contenu                                      cfd-plot
=====================  ===========================================  ==================================
``COURBES/``           CA, CN, Cm selon α (un Mach par figure) et   ``batch_plot`` : une source par
                       selon Mach (α épinglé), une courbe par DM    braquage, deux balayages, zoom,
                                                                    feuilles repliées (``FoldSpec``) :
                                                                    les 4 Mach sur une feuille, les 3
                                                                    coefficients sur une feuille
``CARTES/``            CA, CN, Cm dans le plan (α, DM), un          ``batch_carto`` : échelle partagée,
                       panneau par Mach ; Cm = 0 = équilibre        sous-dict ``CARTO`` par grandeur
``INCREMENT/``         ΔzCA(Mach) par altitude ; CA total lu comme  ``batch_plot`` + zoom en médaillon
                       le simulateur (saturation, interpolation)    sur le transsonique
``EQUILIBRE/``         α et CN d'équilibre selon DM, par Mach       ``batch_plot`` sur des tables
``DERIVEES/``          CNα, Cmα, CNδ, Cmδ, marge statique / Mach    dérivées, feuille repliée ``y``
=====================  ===========================================  ==================================

Les **nœuds non convergés** — tous les coefficients à 0, règle remplaçable par
``Options.non_converge`` — sont écartés : leurs coefficients passent à NaN, si bien qu'une
courbe s'interrompt, qu'une carte hachure la cellule « non convergé », et que dérivées et
équilibre ne sont jamais calculés sur un faux zéro. Leur liste est écrite dans
``non_converges.csv`` (``--garder-zeros`` pour tout garder).

Toutes les figures passent par un même crochet (:class:`Habillage`, picklable donc
compatible ``n_jobs``) : zone α < 0 hachurée « déduit par symétrie », trait y = 0,
bande de marge statique usuelle, légende hors des courbes. Les feuilles utiles à la
présentation sont recopiées sous des noms stables dans ``PLANCHES/``
(:data:`PLANCHES_ATTENDUES`) ; les chiffres cités sur les planches dans
``chiffres_tables.json``.

Usage ::

    python tracer_base_aero.py DONNEES/tables_carrees.csv DONNEES/increment_dzca.csv
    python tracer_base_aero.py T.csv I.csv --col mach=Mach alpha=ALPHA dm=DM_EQ \\
        --col-increment altitude=Z increment=DCA_Z --sortie SORTIE/FIGURES --planches PLANCHES

ou depuis Python ::

    from tracer_base_aero import tracer_base_aero
    planches = tracer_base_aero(df_tables, df_increment, "SORTIE/FIGURES",
                                colonnes={"mach": "Mach", "alpha": "ALPHA"})
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from cfd_plot import (
    CartoSpec,
    FoldSpec,
    ZoomSpec,
    add_reference_lines,
    batch_carto,
    batch_plot,
)

#: Noms des colonnes des tables carrées : clé interne → nom dans votre DataFrame.
COLONNES: dict[str, str] = {
    "mach": "mach",
    "alpha": "alpha",  # degrés
    "dm": "DM",  # braquage équivalent, degrés
    "CA": "CA",
    "CN": "CN",
    "Cm": "Cm",
}
#: Noms des colonnes de la table d'incrément.
COLONNES_INCREMENT: dict[str, str] = {
    "mach": "mach",
    "altitude": "altitude",  # m
    "increment": "DZCA",
}

#: Planche (nom stable dans PLANCHES/) → (dossier relatif, nom de fichier sans extension).
PLANCHES_ATTENDUES: dict[str, tuple[str, str]] = {
    "CN_alpha_4mach": ("COURBES/ALPHA_POLAR/FOLD", "CN_vs_alpha_by_M"),
    "Cm_alpha_4mach": ("COURBES/ALPHA_POLAR/FOLD", "Cm_vs_alpha_by_M"),
    "CA_alpha_4mach": ("COURBES/ALPHA_POLAR/FOLD", "CA_vs_alpha_by_M"),
    "CA_mach_4alpha": ("COURBES/MACH_POLAR/FOLD", "CA_vs_mach_by_ALPHA"),
    "carte_Cm": ("CARTES/ALPHA_DM_CARTO", "Cm_vs_alpha_DM"),
    "carte_CN": ("CARTES/ALPHA_DM_CARTO", "CN_vs_alpha_DM"),
    "dzca_mach": ("INCREMENT/MACH_POLAR", "DZCA_vs_mach"),
    "CA_total_mach": ("INCREMENT/MACH_POLAR", "CA_TOTAL_vs_mach"),
    "equilibre": ("EQUILIBRE/DM_POLAR", "FOLD_Y_vs_DM"),
    "derivees": ("DERIVEES/MACH_POLAR", "FOLD_Y_vs_mach"),
}

SYMBOLES = {"CA": r"$C_A$", "CN": r"$C_N$", "Cm": r"$C_m$"}
NOMS = {"CA": "Force axiale", "CN": "Force normale", "Cm": "Moment de tangage"}
NOIR, GRIS = "#222222", "#7F8C8D"


# ---------------------------------------------------------------------------
# Entrées
# ---------------------------------------------------------------------------


def normaliser(
    df: pd.DataFrame, colonnes: Mapping[str, str], defaut: Mapping[str, str], quoi: str
) -> pd.DataFrame:
    """Renomme vers les clés internes ; refuse une colonne absente en la nommant."""
    noms = {**defaut, **colonnes}
    inconnues = set(colonnes) - set(defaut)
    if inconnues:
        raise KeyError(f"{quoi} : clé(s) inconnue(s) {sorted(inconnues)}, admises {sorted(defaut)}")
    absentes = [v for v in noms.values() if v not in df.columns]
    if absentes:
        raise KeyError(
            f"{quoi} : colonne(s) absente(s) {absentes} ; colonnes lues : {list(df.columns)}"
        )
    return df.rename(columns={v: k for k, v in noms.items()})[list(noms)].astype(float)


COEFFICIENTS = ("CA", "CN", "Cm")


def non_converges_tous_nuls(t: pd.DataFrame) -> pd.Series:
    """Règle par défaut : un nœud est non convergé si **tous** ses coefficients valent 0.

    Pas « un coefficient nul » : CN = Cm = 0 est la valeur *attendue* en α = 0, DM = 0
    (symétrie), et CN ou Cm passent par zéro sur chaque courbe. CA, lui, ne s'annule jamais
    sur une fusée : trois zéros ensemble ne sont pas de la physique.
    """
    return (t[list(COEFFICIENTS)] == 0).all(axis=1)


def ecarter_non_converges(
    t: pd.DataFrame, regle: Callable[[pd.DataFrame], pd.Series] | None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Passe à NaN les coefficients des nœuds non convergés ; renvoie (table, nœuds écartés).

    Les lignes restent : la table reste carrée (lecture multilinéaire, cartes), et un NaN
    est ce que chaque tracé sait déjà ne pas dessiner — une courbe s'interrompt, une carte
    hachure la cellule « non convergé », une dérivée ou un équilibre qui en dépend vaut NaN
    au lieu d'être calculé sur un faux zéro.
    """
    if regle is None:
        return t, t.iloc[0:0]
    masque = pd.Series(regle(t), index=t.index).astype(bool)
    ecartes = t.loc[masque, ["mach", "alpha", "dm"]].copy()
    t = t.copy()
    t.loc[masque, list(COEFFICIENTS)] = np.nan
    return t, ecartes


def verifier_carree(t: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Les trois axes ; refuse une table qui n'est pas un produit complet.

    Des coefficients vides (NaN : nœuds non convergés écartés) sont admis : c'est la grille
    qui doit être complète, pas les valeurs.
    """
    axes = tuple(np.sort(t[c].unique()) for c in ("mach", "alpha", "dm"))
    attendu = math.prod(len(a) for a in axes)
    if len(t) != attendu or t.duplicated(["mach", "alpha", "dm"]).any():
        raise ValueError(
            f"table non carrée : {len(t)} lignes pour {' × '.join(str(len(a)) for a in axes)} "
            f"= {attendu} nœuds (doublons ou nœuds manquants)"
        )
    return axes


class Table3D:
    """Lecture multilinéaire en (Mach, α, DM), saturée aux bornes — comme le simulateur.

    Un nœud vide (NaN) rend vide toute lecture dans les mailles qui le touchent, sauf si
    son poids est nul : sur un nœud voisin, la valeur lue reste celle du nœud.
    """

    def __init__(self, t: pd.DataFrame, coef: str) -> None:
        self.axes = verifier_carree(t)
        cube = t.sort_values(["mach", "alpha", "dm"])[coef].to_numpy()
        self.valeurs = cube.reshape(tuple(len(a) for a in self.axes))

    def __call__(self, mach, alpha, dm) -> np.ndarray:
        q = np.broadcast_arrays(*(np.asarray(v, float) for v in (mach, alpha, dm)))
        idx, poids = [], []
        for axe, v in zip(self.axes, q):
            v = np.clip(v, axe[0], axe[-1])
            i = np.clip(np.searchsorted(axe, v, side="right") - 1, 0, len(axe) - 2)
            idx.append(i)
            poids.append((v - axe[i]) / (axe[i + 1] - axe[i]))
        sortie = np.zeros(q[0].shape)
        for coin in np.ndindex(2, 2, 2):
            w = np.ones(q[0].shape)
            for k, b in enumerate(coin):
                w = w * (poids[k] if b else 1 - poids[k])
            v = self.valeurs[idx[0] + coin[0], idx[1] + coin[1], idx[2] + coin[2]]
            sortie += np.where(w == 0, 0.0, w * v)  # 0 × NaN donnerait NaN
        return sortie


def lire_increment(inc: pd.DataFrame, mach, altitude) -> np.ndarray:
    """ΔzCA bilinéaire en (Mach, altitude), saturé aux bornes de la table d'incrément."""
    piv = inc.pivot_table(index="mach", columns="altitude", values="increment")
    if piv.isna().any().any():
        raise ValueError("table d'incrément non carrée en (Mach, altitude)")
    m_ax, z_ax = piv.index.to_numpy(), piv.columns.to_numpy()
    mach, altitude = np.broadcast_arrays(np.asarray(mach, float), np.asarray(altitude, float))
    par_z = np.array([np.interp(mach, m_ax, piv[z].to_numpy()) for z in z_ax])
    sortie = np.empty(mach.shape)
    for i in np.ndindex(mach.shape):
        sortie[i] = np.interp(altitude[i], z_ax, par_z[(slice(None), *i)])
    return sortie


# ---------------------------------------------------------------------------
# Tables dérivées
# ---------------------------------------------------------------------------


def equilibre(t: pd.DataFrame) -> pd.DataFrame:
    """α et CN d'équilibre (Cm = 0) pour chaque (Mach, DM), interpolés linéairement en α.

    Retient la racine stable (dCm/dα < 0) la plus proche de α = 0 ; ``n_racines`` compte
    les passages par zéro, pour repérer un équilibre multiple. Les nœuds vides sont sautés
    (l'interpolation relie alors les nœuds valides qui les encadrent) et comptés dans
    ``noeuds_vides`` : une racine trouvée à travers un trou est à regarder de près.
    """
    lignes = []
    for (m, d), g in t.groupby(["mach", "dm"]):
        vides = int(g[["CN", "Cm"]].isna().any(axis=1).sum())
        g = g.dropna(subset=["CN", "Cm"]).sort_values("alpha")
        a, cm, cn = g["alpha"].to_numpy(), g["Cm"].to_numpy(), g["CN"].to_numpy()
        racines = []
        for i in range(len(a) - 1):
            if cm[i] == 0 or cm[i] * cm[i + 1] < 0:
                s = 0.0 if cm[i] == 0 else cm[i] / (cm[i] - cm[i + 1])
                if cm[i + 1] - cm[i] <= 0:  # stable
                    racines.append((a[i] + s * (a[i + 1] - a[i]), cn[i] + s * (cn[i + 1] - cn[i])))
        racine = min(racines, key=lambda r: abs(r[0])) if racines else (np.nan, np.nan)
        lignes.append(
            {
                "mach": m,
                "dm": d,
                "alpha_eq": racine[0],
                "CN_eq": racine[1],
                "n_racines": len(racines),
                "noeuds_vides": vides,
            }
        )
    return pd.DataFrame(lignes)


def _indice_zero(axe: np.ndarray) -> int | None:
    trouves = np.flatnonzero(np.isclose(axe, 0.0, atol=1e-9))
    return int(trouves[0]) if trouves.size else None


def _pente(axe: np.ndarray, i0: int | None, f) -> tuple[float, str]:
    """Pente de ``f`` (fonction de l'indice) en ``axe[i0]`` = 0, par radian.

    Centrée si 0 est un nœud intérieur ; décentrée (ordre 1, vers le seul voisin) s'il est
    une borne — typiquement une table en α ≥ 0 non complétée par symétrie ; NaN si 0 n'est
    pas un nœud ou s'il n'a pas de voisin.
    """
    if i0 is None or len(axe) < 2:
        return math.nan, "absent"
    if 0 < i0 < len(axe) - 1:
        bas, haut, schema = i0 - 1, i0 + 1, "centré"
    elif i0 == 0:
        bas, haut, schema = 0, 1, "décentré"
    else:
        bas, haut, schema = i0 - 1, i0, "décentré"
    return (f(haut) - f(bas)) / math.radians(axe[haut] - axe[bas]), schema


def derivees(t: pd.DataFrame) -> pd.DataFrame:
    """CNα, Cmα, CNδ, Cmδ (/rad) en α = 0, DM = 0, et marge statique −Cmα/CNα.

    Différences centrées quand α = 0 et DM = 0 sont des nœuds intérieurs, décentrées quand
    ils sont une borne de la table, NaN quand ils n'en sont pas un nœud : le reste des
    figures est produit quoi qu'il arrive. Le schéma retenu est dans ``attrs["schemas"]``.
    La marge est en longueurs de référence de Cm (calibres si Lréf = D). Un nœud vide
    parmi ceux de la différence donne NaN, jamais une dérivée calculée sur un faux zéro.
    """
    lignes, schemas = [], set()
    for m, g in t.groupby("mach"):
        a, d = np.sort(g["alpha"].unique()), np.sort(g["dm"].unique())
        ia, idd = _indice_zero(a), _indice_zero(d)

        def val(c, i, j, g=g, a=a, d=d):
            sel = g.loc[np.isclose(g["alpha"], a[i]) & np.isclose(g["dm"], d[j]), c]
            return float(sel.iloc[0]) if len(sel) else math.nan

        # Pente en α à DM = 0, pente en DM à α = 0 ; sans l'un des deux nœuds, NaN.
        def en_alpha(c, j=idd, val=val):
            return lambda i: val(c, i, j)

        def en_dm(c, i=ia, val=val):
            return lambda j: val(c, i, j)

        ia_ok = ia if idd is not None else None
        idd_ok = idd if ia is not None else None
        cna, sa = _pente(a, ia_ok, en_alpha("CN"))
        cma, _ = _pente(a, ia_ok, en_alpha("Cm"))
        cnd, sd = _pente(d, idd_ok, en_dm("CN"))
        cmd, _ = _pente(d, idd_ok, en_dm("Cm"))
        schemas |= {("α", sa), ("DM", sd)}
        lignes.append(
            {
                "mach": m,
                "CNa": cna,
                "Cma": cma,
                "CNd": cnd,
                "Cmd": cmd,
                "marge": -cma / cna if cna else math.nan,
                "CA0": val("CA", ia, idd) if ia is not None and idd is not None else math.nan,
            }
        )
    der = pd.DataFrame(lignes)
    der.attrs["schemas"] = sorted(schemas)
    return der


# ---------------------------------------------------------------------------
# Habillage commun (crochet on_before_save)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Habillage:
    """Crochet commun à toutes les figures. Classe de module : picklable, ``n_jobs`` garde
    son pool (une lambda ferait retomber batch_plot sur un seul cœur)."""

    symetrie: bool = True
    marge_usuelle: tuple[float, float] | None = (1.0, 2.0)
    legende_dehors: bool = True
    #: Feuilles repliées : leur en-tête (« CN vs. α / M folded ») est ôté, la planche de la
    #: présentation porte son propre titre ; les panneaux gardent le leur (« M=0.6 »).
    entete_feuilles: bool = False

    def __call__(self, fig, ax, context) -> None:
        if context.fold_kind is not None and not self.entete_feuilles and fig._suptitle:
            fig._suptitle.set_text("")
        if self.symetrie and context.sweep_key == "alpha" and context.y_key in SYMBOLES:
            gauche, droite = ax.get_xlim()
            if gauche < 0:
                ax.axvspan(
                    gauche, 0, facecolor="#EEEEEE", hatch="///", edgecolor="#C8C8C8", lw=0, zorder=0
                )
                ax.axvline(0, color=GRIS, lw=0.8, ls="--", zorder=1)
                ax.text(
                    0.02,
                    0.97,
                    "déduit par\nsymétrie",
                    transform=ax.transAxes,
                    va="top",
                    fontsize=7,
                    color=GRIS,
                )
                ax.set_xlim(gauche, droite)
        if context.y_key in ("CN", "Cm", "alpha_eq", "CN_eq"):
            add_reference_lines(ax, hlines=[0.0])
        if context.y_key == "marge" and self.marge_usuelle:
            ax.axhspan(*self.marge_usuelle, color="#DFF0D8", zorder=0, lw=0)
            ax.text(
                0.02, 0.04, "plage usuelle", transform=ax.transAxes, fontsize=7, color="#3C763D"
            )
        leg = ax.get_legend()
        nombreuse = leg is not None and len(leg.get_texts()) > 4
        if self.legende_dehors and nombreuse and context.panel_index in (None, 0):
            ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=7, frameon=False)


# ---------------------------------------------------------------------------
# Dictionnaires cfd-plot
# ---------------------------------------------------------------------------


def _fr(x: float, n: int = 1) -> str:
    return f"{x:.{n}f}".replace(".", ",").replace("-", "−")


def couleurs_braquage(n: int) -> list:
    """Divergente, DM = 0 en noir : le signe du braquage se lit à la couleur."""
    carte = plt.get_cmap("RdBu_r")
    cols = [carte(0.06 + 0.88 * i / max(n - 1, 1)) for i in range(n)]
    if n % 2:
        cols[n // 2] = NOIR
    return cols


def y_axes(coefs: Sequence[str]) -> dict:
    return {
        c: {
            "col_name": c,
            "literal_name": NOMS[c],
            "symbol": SYMBOLES[c],
            "unit": "-",
            "y_save_name": c,
        }
        for c in coefs
    }


SWEEP_ALPHA = {
    "col_name": "alpha",
    "literal_name": "Incidence",
    "symbol": r"$\alpha$",
    "unit": "°",
    "x_save_name": "alpha",
    "polar_prefix": "ALPHA_POLAR",
    "label": r"$\alpha$",
    "save_name": "ALPHA",
}
SWEEP_MACH = {
    "col_name": "mach",
    "literal_name": "Mach",
    "symbol": "M",
    "unit": "-",
    "x_save_name": "mach",
    "polar_prefix": "MACH_POLAR",
    "label": "M",
    "save_name": "M",
}
SWEEP_DM = {
    "col_name": "dm",
    "literal_name": "Braquage équivalent",
    "symbol": "DM",
    "unit": "°",
    "x_save_name": "DM",
    "polar_prefix": "DM_POLAR",
    "label": "DM",
    "save_name": "DM",
}


@dataclass
class Options:
    """Réglages des tracés (tous facultatifs)."""

    formats: tuple[str, ...] = ("png", "svg")
    profil: str = "paper"
    #: DM = facteur · δ physique (√2 pour un X) : ajoute δ aux légendes ; None pour l'omettre.
    facteur_braquage: float | None = math.sqrt(2.0)
    #: α épinglés pour les courbes selon Mach (None : 4 valeurs réparties sur la table).
    alphas_epingles: Sequence[float] | None = None
    #: Zone de l'incidence agrandie dans une figure à part (« zone linéaire »).
    zoom_alpha: tuple[float, float] | None = (0.0, 10.0)
    #: Altitudes tracées pour l'incrément (None : toutes).
    altitudes: Sequence[float] | None = None
    #: (α, DM) du CA total lu comme le simulateur.
    point_ca_total: tuple[float, float] = (0.0, 0.0)
    #: Plage de Mach du médaillon sur le CA total (là où les altitudes se séparent).
    zoom_mach: tuple[float, float] | None = (0.6, 0.9)
    symetrie: bool = True
    #: Repère les nœuds non convergés, écartés des tracés (None : tout garder).
    non_converge: Callable[[pd.DataFrame], pd.Series] | None = non_converges_tous_nuls
    n_jobs: int = 1
    habillage: Habillage = field(default_factory=Habillage)


def _batch(clean: bool = True, **kw) -> list[Path]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return list(batch_plot(report=False, clean=clean, **kw))


def tracer_courbes(t: pd.DataFrame, sortie: Path, o: Options) -> list[Path]:
    niveaux = np.sort(t["dm"].unique())
    alphas = np.sort(t["alpha"].unique())
    epingles = o.alphas_epingles
    if epingles is None:
        positifs = alphas[alphas >= 0]
        epingles = positifs[np.linspace(0, len(positifs) - 1, 4).round().astype(int)]
    config = {}
    for d, c in zip(niveaux, couleurs_braquage(len(niveaux))):
        label = f"DM = {_fr(d)}°"
        if o.facteur_braquage:
            label += f" (δ = {_fr(d / o.facteur_braquage)}°)"
        config[f"DM_{d:+.3f}"] = {
            "name": label,
            "label": label,
            "df": t[t["dm"] == d],
            "color": c,
            "marker": "o",
            "ms": 2.5,
            "lw": 1.3,
        }
    alpha = dict(SWEEP_ALPHA, values=list(epingles))
    if o.zoom_alpha:
        alpha["zoom"] = ZoomSpec(
            xlim=o.zoom_alpha, mode="figure", name="lineaire", label="zone linéaire"
        )
    return _batch(
        configuration_dict=config,
        y_axis_dict=y_axes(("CA", "CN", "Cm")),
        sweep_dict={
            "alpha": alpha,
            "mach": dict(SWEEP_MACH, values=list(np.sort(t["mach"].unique()))),
        },
        flight_point_dict={},
        output_base=sortie / "COURBES",
        style_profile=o.profil,
        formats=o.formats,
        on_before_save=o.habillage,
        n_jobs=o.n_jobs,
        fold=[
            FoldSpec(kind="y"),
            FoldSpec(kind="context", over=("mach",), max_cols=2),
            FoldSpec(kind="context", over=("alpha",), max_cols=2),
        ],
    )


def tracer_cartes(t: pd.DataFrame, sortie: Path, o: Options) -> list[Path]:
    config = {
        f"M_{m:.2f}": {"name": f"M{m}", "label": f"Mach {_fr(m, 2)}", "df": t[t["mach"] == m]}
        for m in np.sort(t["mach"].unique())
    }
    y = y_axes(("CA", "CN", "Cm"))
    for c in ("CN", "Cm"):
        lim = float(np.abs(t[c]).max())
        y[c]["CARTO"] = {
            "cmap": "RdBu_r",
            "levels": list(np.linspace(-lim, lim, 21)),
            "line_levels": [0.0] if c == "Cm" else 7,
            "line_width": 1.6 if c == "Cm" else 0.6,
            # « %.0s » : clabel formate avec %, la valeur (0) n'est pas réécrite.
            "clabel_fmt": "Cm = 0 (équilibre)%.0s" if c == "Cm" else "%.3g",
        }
    y["CA"]["CARTO"] = {"cmap": "viridis", "levels": 15, "line_levels": 6}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return list(
            batch_carto(
                configuration_dict=config,
                y_axis_dict=y,
                sweep_dict={"alpha": SWEEP_ALPHA, "dm": SWEEP_DM},
                flight_point_dict={},
                pairs=[("alpha", "dm")],
                output_base=sortie / "CARTES",
                carto=CartoSpec(
                    max_cols=2,
                    panel_size=(3.3, 2.5),
                    missing={"message": "non convergé"},
                    suptitle="{qoi_symbol} dans le plan (α, DM)",
                ),
                style_profile=o.profil,
                formats=o.formats,
                report=False,
                clean=True,
                n_jobs=o.n_jobs,
            )
        )


def tracer_increment(t: pd.DataFrame, inc: pd.DataFrame, sortie: Path, o: Options) -> list[Path]:
    if o.altitudes is None:  # au plus 5 altitudes réparties sur la table
        toutes = np.sort(inc["altitude"].unique())
        altitudes = toutes[np.unique(np.linspace(0, len(toutes) - 1, 5).round().astype(int))]
    else:
        altitudes = np.asarray(o.altitudes, float)
    teintes = plt.get_cmap("Blues")(np.linspace(0.35, 1.0, len(altitudes)))
    ca = Table3D(t, "CA")
    # Les Mach des deux tables : la lecture est linéaire entre eux, rien à voir entre deux.
    machs = np.unique(np.concatenate([inc["mach"].to_numpy(), t["mach"].to_numpy()]))
    machs = machs[machs <= max(inc["mach"].max(), t["mach"].max())]
    a0, d0 = o.point_ca_total
    config = {}
    for z, c in zip(altitudes, teintes):
        # Une seule grille de Mach pour les deux grandeurs : l'incrément y est lu comme le
        # lit le simulateur (bilinéaire, saturé), le CA total y montre la saturation M < Mmin.
        df = pd.DataFrame({"mach": machs, "altitude": z})
        df["increment"] = lire_increment(inc, machs, z)
        df["CA_TOTAL"] = ca(machs, a0, d0) + df["increment"]
        config[f"Z_{z:.0f}"] = {
            "name": f"z = {z:.0f} m",
            "label": f"z = {z:.0f} m",
            "df": df,
            "color": tuple(c),
            "lw": 1.6,
            "marker": "o",
            "ms": 2.5,
        }
    mach_zoom = dict(SWEEP_MACH)
    if o.zoom_mach:  # l'écart entre altitudes, invisible à l'échelle du saut transsonique
        mach_zoom["zoom"] = ZoomSpec(
            xlim=o.zoom_mach, mode="inset", label="effet de l'altitude", size=(0.42, 0.42)
        )
    y = {
        "DZCA": {
            "col_name": "increment",
            "literal_name": "Incrément d'altitude",
            "symbol": r"$\Delta_z C_A$",
            "unit": "-",
            "y_save_name": "DZCA",
        },
        "CA_TOTAL": {
            "col_name": "CA_TOTAL",
            "literal_name": "CA lu par le simulateur",
            "symbol": rf"$C_A$ ($\alpha$ = {a0:g}°, DM = {d0:g}°)",
            "unit": "-",
            "y_save_name": "CA_TOTAL",
        },
    }
    commun = {
        "configuration_dict": config,
        "flight_point_dict": {},
        "style_profile": o.profil,
        "output_base": sortie / "INCREMENT",
        "formats": o.formats,
        "on_before_save": o.habillage,
        "n_jobs": o.n_jobs,
    }
    return _batch(
        y_axis_dict={"DZCA": y["DZCA"]}, sweep_dict={"mach": SWEEP_MACH}, **commun
    ) + _batch(
        y_axis_dict={"CA_TOTAL": y["CA_TOTAL"]},
        sweep_dict={"mach": mach_zoom},
        clean=False,
        **commun,
    )


def tracer_derivees(eq: pd.DataFrame, der: pd.DataFrame, sortie: Path, o: Options) -> list[Path]:
    machs = np.sort(eq["mach"].unique())
    teintes = plt.get_cmap("Blues")(np.linspace(0.4, 1.0, len(machs)))
    config_eq = {
        f"M_{m:.2f}": {
            "name": f"Mach {_fr(m, 2)}",
            "label": f"Mach {_fr(m, 2)}",
            "df": eq[eq["mach"] == m],
            "color": tuple(c),
            "marker": "o",
            "ms": 3,
        }
        for m, c in zip(machs, teintes)
    }
    y_eq = {
        "alpha_eq": {
            "col_name": "alpha_eq",
            "literal_name": "Incidence d'équilibre",
            "symbol": r"$\alpha_{eq}$",
            "unit": "°",
            "y_save_name": "alpha_eq",
        },
        "CN_eq": {
            "col_name": "CN_eq",
            "literal_name": "CN à l'équilibre",
            "symbol": r"$C_{N,eq}$",
            "unit": "-",
            "y_save_name": "CN_eq",
        },
    }
    sortie_eq = _batch(
        configuration_dict=config_eq,
        y_axis_dict=y_eq,
        sweep_dict={"dm": SWEEP_DM},
        flight_point_dict={},
        output_base=sortie / "EQUILIBRE",
        style_profile=o.profil,
        formats=o.formats,
        on_before_save=o.habillage,
        n_jobs=o.n_jobs,
        fold=FoldSpec(kind="y"),
    )
    y_der = {
        "CNa": {
            "col_name": "CNa",
            "literal_name": "Gradient de portance",
            "symbol": r"$C_{N\alpha}$",
            "unit": "/rad",
            "y_save_name": "CNa",
        },
        "Cma": {
            "col_name": "Cma",
            "literal_name": "Stabilité statique",
            "symbol": r"$C_{m\alpha}$",
            "unit": "/rad",
            "y_save_name": "Cma",
        },
        "CNd": {
            "col_name": "CNd",
            "literal_name": "Efficacité en force",
            "symbol": r"$C_{N\delta}$",
            "unit": "/rad",
            "y_save_name": "CNd",
        },
        "Cmd": {
            "col_name": "Cmd",
            "literal_name": "Efficacité en moment",
            "symbol": r"$C_{m\delta}$",
            "unit": "/rad",
            "y_save_name": "Cmd",
        },
        "marge": {
            "col_name": "marge",
            "literal_name": "Marge statique",
            "symbol": r"$-C_{m\alpha}/C_{N\alpha}$",
            "unit": "cal.",
            "y_save_name": "marge",
        },
    }
    config_der = {
        "BASE": {
            "name": "base",
            "label": "table",
            "df": der,
            "color": "#0B3C5D",
            "marker": "o",
            "ms": 4,
        }
    }
    sortie_der = _batch(
        configuration_dict=config_der,
        y_axis_dict=y_der,
        sweep_dict={"mach": SWEEP_MACH},
        flight_point_dict={},
        output_base=sortie / "DERIVEES",
        style_profile=o.profil,
        formats=o.formats,
        on_before_save=o.habillage,
        n_jobs=o.n_jobs,
        fold=FoldSpec(kind="y"),
    )
    return sortie_eq + sortie_der


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------


def tracer_base_aero(
    df_tables: pd.DataFrame,
    df_increment: pd.DataFrame,
    sortie: str | Path,
    *,
    colonnes: Mapping[str, str] | None = None,
    colonnes_increment: Mapping[str, str] | None = None,
    planches: str | Path | None = None,
    options: Options | None = None,
) -> dict[str, Path]:
    """Toutes les figures sous ``sortie`` ; les planches de la présentation sous ``planches``.

    Renvoie planche → fichier PNG copié (vide si ``planches`` est None). Écrit aussi
    ``chiffres_tables.json`` (dérivées, marge, équilibre) à côté des planches.
    """
    o = options or Options()
    sortie = Path(sortie)
    t = normaliser(df_tables, colonnes or {}, COLONNES, "tables carrées")
    inc = normaliser(df_increment, colonnes_increment or {}, COLONNES_INCREMENT, "incrément")
    verifier_carree(t)
    t, ecartes = ecarter_non_converges(t, o.non_converge)
    sortie.mkdir(parents=True, exist_ok=True)
    noms = {**COLONNES, **(colonnes or {})}
    ecartes.rename(columns={k: noms[k] for k in ("mach", "alpha", "dm")}).to_csv(
        sortie / "non_converges.csv", index=False
    )
    if len(ecartes):
        print(
            f"{len(ecartes)} nœud(s) non convergé(s) écarté(s) des tracés "
            f"(liste : {sortie / 'non_converges.csv'})"
        )
    if not o.symetrie:
        o.habillage = Habillage(symetrie=False, marge_usuelle=o.habillage.marge_usuelle)
    # Les coefficients d'abord : ce sont les figures qui doivent sortir quoi qu'il arrive.
    tracer_courbes(t, sortie, o)
    tracer_cartes(t, sortie, o)
    tracer_increment(t, inc, sortie, o)
    # Les grandeurs dérivées ensuite : un échec y est signalé, il n'arrête rien.
    eq = der = None
    try:
        eq, der = equilibre(t), derivees(t)
        for axe, schema in der.attrs["schemas"]:
            if schema == "décentré":
                print(
                    f"dérivées en {axe} : 0 est une borne de la table, différence décentrée (ordre 1)"
                )
            elif schema == "absent":
                print(
                    f"dérivées en {axe} : 0 n'est pas un nœud de la table, dérivées non calculées"
                )
        tracer_derivees(eq, der, sortie, o)
    except Exception as erreur:  # n'empêche pas les figures des coefficients
        print(f"équilibre et dérivées ignorés : {type(erreur).__name__}: {erreur}")
    if planches is None:
        return {}
    planches = Path(planches)
    planches.mkdir(parents=True, exist_ok=True)
    copiees = {}
    for nom, (dossier, fichier) in PLANCHES_ATTENDUES.items():
        source = sortie / dossier / f"{fichier}.png"
        if source.is_file():
            copiees[nom] = Path(shutil.copy(source, planches / f"{nom}.png"))
        else:
            print(f"planche {nom} non produite ({source.relative_to(sortie)} absent)")
    machs = np.sort(t["mach"].unique())
    butee = t["dm"].abs().max()

    def lire(df, colonne, **filtre) -> float:
        """Une valeur de ``df`` ; NaN si la ligne n'existe pas (nœud absent de la grille)."""
        sel = np.ones(len(df), bool)
        for c, v in filtre.items():
            sel &= np.isclose(df[c], v)
        return float(df.loc[sel, colonne].iloc[0]) if sel.any() else math.nan

    chiffres = {
        "machs": [float(m) for m in machs],
        "derivees": der.to_dict(orient="list") if der is not None else None,
        "alpha_eq_butee": [lire(eq, "alpha_eq", mach=m, dm=-butee) for m in machs]
        if eq is not None
        else None,
        "racines_par_courbe": sorted({int(n) for n in eq["n_racines"]}) if eq is not None else None,
        "courbes_equilibre": len(eq) if eq is not None else 0,
        "CN_butee_alpha0": [lire(t, "CN", mach=m, alpha=0.0, dm=butee) for m in machs],
        "CA_max_braquage": max(
            lire(t, "CA", mach=m, alpha=0.0, dm=butee) - lire(t, "CA", mach=m, alpha=0.0, dm=0.0)
            for m in machs
        ),
        "noeuds": len(t),
        "non_converges": len(ecartes),
        "dm_niveaux": [float(d) for d in np.sort(t["dm"].unique())],
    }
    # NaN n'est pas du JSON : une grandeur rendue indéfinie par un nœud écarté devient null.
    (planches / "chiffres_tables.json").write_text(
        json.dumps(_sans_nan(chiffres), indent=2, allow_nan=False)
    )
    return copiees


def _sans_nan(x):
    if isinstance(x, dict):
        return {k: _sans_nan(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_sans_nan(v) for v in x]
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def _paires(textes: Sequence[str] | None, quoi: str) -> dict[str, str]:
    sortie = {}
    for texte in textes or ():
        cle, _, nom = texte.partition("=")
        if not nom:
            raise SystemExit(f"{quoi} : « {texte} » attendu sous la forme cle=nom_de_colonne")
        sortie[cle] = nom
    return sortie


def principal(argv: Sequence[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("tables", help="tables carrées (CSV ; séparateur détecté)")
    p.add_argument("increment", help="table d'incrément ΔzCA(Mach, altitude)")
    p.add_argument("--sortie", default="SORTIE/FIGURES")
    p.add_argument("--planches", default="PLANCHES")
    p.add_argument(
        "--col",
        nargs="+",
        metavar="CLE=NOM",
        help=f"colonnes des tables ; clés : {', '.join(COLONNES)}",
    )
    p.add_argument(
        "--col-increment",
        nargs="+",
        metavar="CLE=NOM",
        help=f"colonnes de l'incrément ; clés : {', '.join(COLONNES_INCREMENT)}",
    )
    p.add_argument("--formats", nargs="+", default=["png", "svg"])
    p.add_argument("--profil", default="paper", choices=("paper", "notebook", "slides"))
    p.add_argument(
        "--facteur-braquage",
        type=float,
        default=math.sqrt(2.0),
        help="DM = facteur · δ physique (0 : ne pas afficher δ)",
    )
    p.add_argument("--sans-symetrie", action="store_true", help="ne pas hachurer α < 0")
    p.add_argument(
        "--garder-zeros",
        action="store_true",
        help="ne pas écarter les nœuds dont tous les coefficients valent 0 (non convergés)",
    )
    p.add_argument("--jobs", type=int, default=1)
    a = p.parse_args(argv)
    lire = lambda f: pd.read_csv(f, sep=None, engine="python")  # noqa: E731
    options = Options(
        formats=tuple(a.formats),
        profil=a.profil,
        facteur_braquage=a.facteur_braquage or None,
        symetrie=not a.sans_symetrie,
        non_converge=None if a.garder_zeros else non_converges_tous_nuls,
        n_jobs=a.jobs,
    )
    planches = tracer_base_aero(
        lire(a.tables),
        lire(a.increment),
        a.sortie,
        colonnes=_paires(a.col, "--col"),
        colonnes_increment=_paires(a.col_increment, "--col-increment"),
        planches=a.planches,
        options=options,
    )
    figures = sum(1 for f in Path(a.sortie).rglob("*") if f.suffix[1:] in a.formats)
    print(f"{figures} fichiers sous {a.sortie} ; {len(planches)} planches dans {a.planches}")


if __name__ == "__main__":
    principal()
