"""Parcourir les points de vol d'une sortie de modèle, et tracer ses tirages.

Le tableau que rend un modèle porte une ligne par (point de vol × tirage) :
quatre points de vol et cent tirages font quatre cents lignes. Les figures du
tirage, elles, parlent d'**un** tirage à la fois. Ce module fait le pont : il
découpe le tableau par point de vol, et écrit pour chacun les figures de ses
premiers tirages.

    figures_tirage_par_pdv(
        df,
        points_de_vol={"Mach": [0.70, 0.85], "Altitude_m": [0, 10_000]},
        racine=sortie / "TIRAGES",
    )

Pourquoi ne pas se greffer sur ``batch_plot``
---------------------------------------------
``cfd_plot.batch_plot`` fait déjà ce parcours, et c'est de lui que viennent ici
la forme du ``points_de_vol`` — le ``flight_point_dict``, avec ses ``values``,
``label`` et ``save_name`` — et l'arborescence de sortie, un dossier par clé de
point de vol **qui varie**.

Mais son point de greffe, ``on_before_save(fig, ax, context)``, arrive sur une
figure **qu'il a déjà construite** : un axe, une courbe par source, un balayage
en abscisse. Nos figures n'ont ni balayage, ni courbe, ni axe unique — trois
panneaux de densité par coefficient. S'y greffer supposerait de lui faire
tracer des courbes pour les effacer aussitôt, et de lui inventer un
``sweep_dict`` qui n'existe pas. C'est donc la **logique de parcours** qui est
reprise, pas la fonction : les conventions sont les siennes, le tracé est le
nôtre.

Ce qu'il faut savoir
--------------------
**La valeur nominale se cherche dans la colonne du même nom** que le
coefficient — et peut manquer. Sans elle, les deux panneaux de composantes sont
tracés quand même et le troisième dit ce qui lui manque (voir
:func:`cfd_dispersion.figures.tirage.figure_tirage`). Une colonne qui *varie* à
l'intérieur d'un point de vol n'est pas une valeur nominale mais une sortie
dispersée : elle est ignorée, sans quoi la loi serait centrée sur le tirage
qu'elle est censée juger. À défaut, ``"<coeff>_nominal"`` est essayée —
c'est ainsi qu'un modèle qui sort les deux se lit sans rien avoir à déclarer.

**Seuls les premiers tirages sont tracés.** Cent tirages sur quatre points de
vol font quatre cents figures par coefficient, que personne ne regardera :
``max_tirages`` en garde quinze par point de vol. Ce sont les premiers dans
l'ordre des numéros, et non un échantillon au hasard — pour qu'une deuxième
exécution donne les mêmes.
"""

from __future__ import annotations

import pickle
import warnings
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

from ..core.convention import Convention, ConventionArg, convention
from ..core.lois import JeuDeLois
from ..core.tableau import COLONNE_LOIS, COLONNE_NUMERO, COLONNE_TIRAGE, tirage_depuis_ligne
from ..core.tableau import lire_sortie_modele as _lire_sortie_modele
from ..core.tirage import Tirage
from ._base import PROFIL_DEFAUT
from .tirage import (
    FORMATS_DEFAUT,
    MAX_COEFFICIENTS_PAR_FIGURE,
    SIGMAS_DEFAUT,
    figure_tirage,
    figure_tirage_matrice,
)

__all__ = [
    "MAX_TIRAGES_DEFAUT",
    "chemin_du_point_de_vol",
    "etiquette_du_point_de_vol",
    "figures_tirage_par_pdv",
]

#: Nombre de tirages tracés par point de vol, faute d'instruction contraire.
MAX_TIRAGES_DEFAUT: int = 15

#: Nom du dossier d'un tirage, sous celui de son point de vol.
_MOTIF_DOSSIER_TIRAGE = "tirage_{numero:03d}"

#: Nom de la figure empilant tous les coefficients d'un tirage.
_NOM_MATRICE = "matrice"


@dataclass(frozen=True)
class _Travail:
    """Un tirage à tracer : tout ce qu'il faut, et rien qui ne se sérialise pas.

    C'est l'unité de travail du parcours. Elle est volontairement close sur
    elle-même — des lois, un tirage, des nombres et un chemin — pour qu'un
    processus ouvrier puisse la recevoir telle quelle.
    """

    point: dict[str, Any]
    numero: int
    tirage: Tirage
    lois: JeuDeLois
    coefficients: tuple[str, ...]
    nominaux: dict[str, Any]
    dossier: Path
    etiquette: str
    formats: tuple[str, ...]
    par_coefficient: bool
    matrice: bool
    convention: Convention
    sigmas: tuple[int, ...] | None
    max_par_figure: int
    profil: str


def _executer(travail: _Travail) -> list[dict[str, Any]]:
    """Trace et écrit les figures d'un tirage ; rend leur inventaire.

    Fonction de module, et non fermeture : c'est ce qui la rend sérialisable,
    donc utilisable telle quelle dans un processus ouvrier.
    """
    import matplotlib

    matplotlib.use("Agg")

    inventaire: list[dict[str, Any]] = []
    commun = {**travail.point, "tirage": travail.numero}

    if travail.par_coefficient:
        for nom in travail.coefficients:
            rendue = figure_tirage(
                nom,
                travail.lois[nom],
                travail.tirage,
                nominal=travail.nominaux.get(nom),
                chemin=travail.dossier / nom,
                formats=travail.formats,
                convention_=travail.convention,
                etiquette=travail.etiquette,
                sigmas=travail.sigmas,
                profil=travail.profil,
            )
            plt.close(rendue.figure)
            inventaire.extend(
                {**commun, "figure": nom, "fichier": fichier} for fichier in rendue.fichiers
            )

    if travail.matrice:
        pages = figure_tirage_matrice(
            travail.lois,
            travail.tirage,
            nominaux=travail.nominaux,
            coefficients=list(travail.coefficients),
            chemin=travail.dossier / _NOM_MATRICE,
            formats=travail.formats,
            convention_=travail.convention,
            etiquette=travail.etiquette,
            sigmas=travail.sigmas,
            max_par_figure=travail.max_par_figure,
            profil=travail.profil,
        )
        for page in pages:
            plt.close(page.figure)
            inventaire.extend(
                {**commun, "figure": _NOM_MATRICE, "fichier": fichier} for fichier in page.fichiers
            )

    return inventaire


def _repartir(travaux: Sequence[_Travail], n_jobs: int) -> list[dict[str, Any]]:
    """Exécute les travaux, en séquence ou sur plusieurs processus.

    Une figure coûte une demi-seconde à écrire — la police du gabarit est
    vectorisée glyphe par glyphe — et un parcours en écrit des centaines. D'où
    ``n_jobs``, et d'où le contrôle de sérialisabilité qui le précède : une
    convention maison écrite en ``lambda`` ne passerait pas, et le parcours
    repasse alors en séquence **en le disant**, plutôt que d'échouer à
    mi-chemin.
    """
    if not travaux:
        return []

    if n_jobs != 1:
        try:
            pickle.dumps(travaux[0])
        except Exception as erreur:  # pragma: no cover - dépend de l'appelant
            warnings.warn(
                f"parcours ramené à un seul processus : le travail ne se sérialise pas "
                f"({erreur}). Une Convention écrite en lambda en est la cause la plus "
                "fréquente ; une fonction de module passe.",
                UserWarning,
                stacklevel=3,
            )
            n_jobs = 1

    if n_jobs == 1:
        return [ligne for travail in travaux for ligne in _executer(travail)]

    ouvriers = None if n_jobs < 0 else n_jobs
    with ProcessPoolExecutor(max_workers=ouvriers, mp_context=_contexte()) as pool:
        # `map` conserve l'ordre : l'inventaire ne dépend pas de l'ordonnancement.
        return [ligne for lot in pool.map(_executer, travaux) for ligne in lot]


def _contexte() -> Any:
    """Le contexte multiprocessus, ``forkserver`` de préférence.

    Un ``fork`` nu depuis un processus qui a déjà des fils — Matplotlib, un
    pilote graphique, un pytest — peut se figer, et Python 3.12 le signale.
    ``forkserver`` part d'un processus propre ; le module est préchargé pour
    que les ouvriers démarrent chauds plutôt que de réimporter Matplotlib un
    par un.
    """
    import multiprocessing

    if "forkserver" not in multiprocessing.get_all_start_methods():  # pragma: no cover
        return None
    contexte = multiprocessing.get_context("forkserver")
    contexte.set_forkserver_preload(["cfd_dispersion.figures.par_pdv"])
    return contexte


def figures_tirage_par_pdv(
    df: pd.DataFrame,
    *,
    points_de_vol: Mapping[str, Any],
    racine: Any,
    lois: JeuDeLois | None = None,
    coefficients: Sequence[str] | None = None,
    nominaux: Mapping[str, Any] | None = None,
    colonne_tirage: str = COLONNE_NUMERO,
    max_tirages: int | None = MAX_TIRAGES_DEFAUT,
    formats: Sequence[str] = FORMATS_DEFAUT,
    par_coefficient: bool = True,
    matrice: bool = True,
    convention_: ConventionArg = None,
    sigmas: Sequence[int] | None = SIGMAS_DEFAUT,
    max_par_figure: int = MAX_COEFFICIENTS_PAR_FIGURE,
    nettoyer: bool = False,
    n_jobs: int = 1,
    profil: str = PROFIL_DEFAUT,
) -> pd.DataFrame:
    """Écrit les figures de tirage, point de vol par point de vol.

    Pour chaque point de vol et chacun de ses premiers tirages : une figure par
    coefficient (:func:`~cfd_dispersion.figures.tirage.figure_tirage`) et une
    figure les empilant (:func:`~cfd_dispersion.figures.tirage.figure_tirage_matrice`,
    paginée au-delà de quatre coefficients).

    Les figures sont **fermées au fur et à mesure** : un parcours complet en
    produit des centaines, et les garder ouvertes ferait grossir la mémoire
    sans que personne les regarde. Ce qui est rendu est leur inventaire.

    Parameters
    ----------
    df:
        La sortie du modèle. Les deux formes sont acceptées : les colonnes à
        plat ``"<coeff>_Biais"`` / ``"<coeff>_FE"``, ou le tableau large à
        colonnes dictionnaires (``DICT_TIRAGE``, ``DICT_LAW_DISPERSION``), qui
        est alors relu par
        :func:`~cfd_dispersion.core.tableau.lire_sortie_modele`.
    points_de_vol:
        ``{colonne: valeurs}`` — la forme du ``flight_point_dict`` de
        ``cfd_plot.batch_plot``. Chaque entrée est une liste de valeurs, ou un
        dictionnaire ``{"values": [...], "label": …, "save_name": …}``. Une
        liste vide, ou ``values`` absent, fait prendre **toutes** les valeurs
        présentes dans le tableau. Le produit cartésien des valeurs donne les
        points de vol ; ceux qu'aucune ligne ne porte sont sautés.
    racine:
        Le dossier de sortie. L'arborescence s'y déploie.
    lois:
        Les lois prescrites. Par défaut, relues du tableau s'il porte sa
        colonne ``DICT_LAW_DISPERSION``.
    coefficients:
        Les coefficients à tracer, dans l'ordre voulu. Par défaut, tous ceux du
        jeu de lois.
    nominaux:
        ``{coefficient: valeur}``, pour imposer les valeurs nominales. Par
        défaut, chacune est cherchée dans la colonne du même nom que le
        coefficient, puis dans ``"<coeff>_nominal"`` — voir le docstring du
        module.
    colonne_tirage:
        La colonne numérotant les tirages. C'est elle qui décide de l'ordre et
        du nom des dossiers.
    max_tirages:
        Nombre de tirages tracés par point de vol, les premiers dans l'ordre
        des numéros. None pour tous — quatre cents figures, donc.
    formats:
        Les formats d'écriture. SVG par défaut.
    par_coefficient, matrice:
        Lesquelles des deux familles de figures écrire.
    n_jobs:
        Nombre de processus employés à écrire les figures. 1 (défaut) reste en
        séquence ; -1 prend tous les cœurs. Une figure coûte une demi-seconde
        à écrire, et un parcours en écrit des centaines. Comme
        ``batch_plot``, le parcours **repasse en séquence en le disant** si le
        travail ne se sérialise pas — le cas d'une ``Convention`` écrite en
        ``lambda``.
    nettoyer:
        Vide l'arborescence de *racine* avant d'écrire, par
        ``cfd_plot.clean_figure_dir`` — qui refuse la racine du disque, le
        dossier personnel, un dossier de premier niveau et une racine de dépôt.

    Returns
    -------
    pandas.DataFrame
        L'inventaire de ce qui a été écrit : les colonnes de point de vol, le
        numéro de tirage, la figure (le nom du coefficient, ou ``"matrice"``)
        et le fichier. Vide si rien n'a été demandé.

    Raises
    ------
    ValueError
        Si *points_de_vol* est vide, si une colonne de point de vol manque au
        tableau, si aucun point de vol demandé n'a de ligne, ou si les lois ne
        peuvent être ni relues ni devinées.

    See Also
    --------
    cfd_dispersion.figures.monte_carlo.figures_par_pdv : la comparaison loi
        prescrite / loi réalisée, sur *tous* les tirages d'un point de vol.
    """
    if not points_de_vol:
        raise ValueError("points_de_vol est vide : aucun point de vol à parcourir")

    tableau, jeu = _preparer(df, lois, colonne_tirage)
    noms = list(coefficients) if coefficients is not None else list(jeu)
    manquants = sorted(set(noms) - set(jeu))
    if manquants:
        raise ValueError(f"coefficient(s) {manquants} absent(s) du jeu de lois")

    specs = _specifications(points_de_vol, tableau)
    variables = [cle for cle, spec in specs.items() if len(spec["values"]) > 1]

    base = Path(racine)
    if nettoyer:
        _nettoyer(base)

    travaux: list[_Travail] = []
    relation = convention(convention_)

    for combinaison in product(*(specs[cle]["values"] for cle in specs)):
        point = dict(zip(specs, combinaison))
        lignes = _selectionner(tableau, point)
        if lignes.empty:
            continue

        dossier = chemin_du_point_de_vol(base, point, specs, variables)
        etiquette = etiquette_du_point_de_vol(point, specs)
        valeurs_nominales = _nominaux_du_point(lignes, noms, nominaux)

        for numero, ligne in _tirages_du_point(lignes, colonne_tirage, max_tirages):
            travaux.append(
                _Travail(
                    point=point,
                    numero=numero,
                    tirage=tirage_depuis_ligne(ligne, noms, convention_=relation, numero=numero),
                    lois=jeu,
                    coefficients=tuple(noms),
                    nominaux=valeurs_nominales,
                    dossier=dossier / _MOTIF_DOSSIER_TIRAGE.format(numero=numero),
                    etiquette=etiquette,
                    formats=tuple(formats),
                    par_coefficient=par_coefficient,
                    matrice=matrice,
                    convention=relation,
                    sigmas=None if sigmas is None else tuple(sigmas),
                    max_par_figure=max_par_figure,
                    profil=profil,
                )
            )

    rencontres = len({tuple(travail.point.items()) for travail in travaux})
    inventaire = _repartir(travaux, n_jobs)

    if rencontres == 0:
        raise ValueError(
            "aucun point de vol demandé n'a de ligne dans le tableau ; "
            f"colonnes lues : {list(specs)} — vérifier les valeurs demandées"
        )

    return pd.DataFrame(
        inventaire, columns=[*specs, "tirage", "figure", "fichier"] if inventaire else None
    )


# ---------------------------------------------------------------------------
# Chemins
# ---------------------------------------------------------------------------


def chemin_du_point_de_vol(
    racine: Any,
    point: Mapping[str, Any],
    specs: Mapping[str, Mapping[str, Any]] | None = None,
    cles_variables: Sequence[str] | None = None,
) -> Path:
    """Le dossier d'un point de vol : ``racine/M_0.85/Z_10000``.

    Un niveau par clé **qui varie** — une clé à valeur unique n'apprend rien et
    n'ajoute qu'un dossier à traverser. C'est la règle de
    ``cfd_plot.build_output_path``, et le nom court vient du même endroit :
    ``save_name``, à défaut la clé en majuscules.
    """
    parts: list[Any] = [Path(racine)]
    cles = list(cles_variables) if cles_variables is not None else list(point)
    for cle in cles:
        court = (specs or {}).get(cle, {}).get("save_name", cle.upper())
        parts.append(f"{court}_{_valeur_pour_chemin(point[cle])}")
    return Path(*parts)


def etiquette_du_point_de_vol(
    point: Mapping[str, Any],
    specs: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    """Le point de vol en clair : ``M = 0.85 · Altitude_m = 10000 m``.

    Elle finit dans le titre de chaque figure. Un SVG se transmet seul, sorti
    de l'arborescence qui disait de quel point de vol il venait : sans cette
    ligne, plus rien ne le dit.
    """
    morceaux = []
    for cle, valeur in point.items():
        spec = (specs or {}).get(cle, {})
        unite = spec.get("unit", "")
        libelle = spec.get("label", cle)
        morceaux.append(f"{libelle} = {_valeur_pour_chemin(valeur)}{unite}")
    return " · ".join(morceaux)


def _valeur_pour_chemin(valeur: Any) -> str:
    """Un nombre lisible dans un nom de dossier : ``0.85``, ``10000``.

    Même règle que ``cfd_plot`` : un flottant entier perd sa décimale, les
    autres sont arrondis au centième et débarrassés de leurs zéros.
    """
    if isinstance(valeur, float):
        if valeur.is_integer():
            return str(int(valeur))
        return f"{valeur:.2f}".rstrip("0").rstrip(".")
    return str(valeur)


# ---------------------------------------------------------------------------
# Lecture du tableau
# ---------------------------------------------------------------------------


def _preparer(
    df: pd.DataFrame,
    lois: JeuDeLois | None,
    colonne_tirage: str,
) -> tuple[pd.DataFrame, JeuDeLois]:
    """Met le tableau à plat et retrouve les lois, quelle que soit sa forme.

    Le modèle numérote souvent ses tirages lui-même. Sa numérotation est alors
    gardée telle quelle : la réécrire ferait diverger les dossiers de figures
    de ce que le tableau, lui, appelle « tirage 7 ».
    """
    if COLONNE_TIRAGE in df.columns or COLONNE_LOIS in df.columns:
        deja_numerote = colonne_tirage in df.columns
        tableau, relues = _lire_sortie_modele(df, numero=None if deja_numerote else colonne_tirage)
        return tableau, lois if lois is not None else relues

    if lois is None:
        raise ValueError(
            "lois introuvables : le tableau ne porte pas de colonne "
            f"{COLONNE_LOIS!r} — passer lois=charger_lois(...)"
        )
    return df, lois


def _specifications(
    points_de_vol: Mapping[str, Any],
    tableau: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    """Normalise le ``points_de_vol`` à la façon du ``flight_point_dict``."""
    specs: dict[str, dict[str, Any]] = {}
    for cle, brut in points_de_vol.items():
        if cle not in tableau.columns:
            raise ValueError(
                f"colonne de point de vol {cle!r} absente du tableau ; "
                f"il porte {sorted(tableau.columns)}"
            )

        if isinstance(brut, Mapping):
            valeurs = list(brut.get("values", brut.get("list", [])) or [])
            spec = {
                "values": valeurs,
                "label": brut.get("label", cle),
                "save_name": brut.get("save_name", cle.upper()),
            }
            if "unit" in brut:
                spec["unit"] = brut["unit"]
        elif isinstance(brut, Iterable) and not isinstance(brut, (str, bytes)):
            spec = {"values": list(brut), "label": cle, "save_name": cle.upper()}
        else:
            spec = {"values": [brut], "label": cle, "save_name": cle.upper()}

        if not spec["values"]:
            # Valeurs non données : celles du tableau, triées, comme le fait
            # `discover_flight_point_values` de cfd-plot.
            spec["values"] = sorted(tableau[cle].dropna().unique().tolist())
        specs[cle] = spec
    return specs


def _selectionner(tableau: pd.DataFrame, point: Mapping[str, Any]) -> pd.DataFrame:
    """Les lignes d'un point de vol."""
    masque = pd.Series(True, index=tableau.index)
    for cle, valeur in point.items():
        masque &= tableau[cle] == valeur
    return tableau[masque]


def _tirages_du_point(
    lignes: pd.DataFrame,
    colonne: str,
    maximum: int | None,
) -> list[tuple[int, dict[str, Any]]]:
    """Les premiers tirages d'un point de vol, numéro et ligne.

    Un tirage peut occuper plusieurs lignes — un appel croisé le rejoue à
    chaque point du balayage — d'où la première ligne de chaque numéro, et non
    toutes : le tirage y est le même, seul le balayage change.
    """
    if colonne not in lignes.columns:
        raise ValueError(
            f"colonne de tirage {colonne!r} absente du tableau ; il porte {sorted(lignes.columns)}"
        )

    numeros = sorted(int(valeur) for valeur in lignes[colonne].dropna().unique())
    if maximum is not None:
        numeros = numeros[:maximum]

    premieres = []
    for numero in numeros:
        correspondantes = lignes[lignes[colonne] == numero]
        premieres.append((numero, dict(correspondantes.iloc[0])))
    return premieres


def _nominaux_du_point(
    lignes: pd.DataFrame,
    coefficients: Sequence[str],
    imposes: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Les valeurs nominales d'un point de vol, ou rien quand elles manquent.

    La règle, dans l'ordre : ce que l'appelant impose ; sinon la colonne du
    même nom que le coefficient ; sinon ``"<coeff>_nominal"``. Dans les deux
    derniers cas, **la colonne doit être constante** sur le point de vol : une
    colonne qui varie d'un tirage à l'autre est un coefficient dispersé, pas
    une valeur nominale, et la retenir centrerait la loi sur le tirage qu'elle
    doit juger.
    """
    valeurs: dict[str, Any] = {}
    for nom in coefficients:
        if imposes is not None and nom in imposes:
            valeurs[nom] = imposes[nom]
            continue
        for candidate in (nom, f"{nom}_nominal"):
            constante = _valeur_constante(lignes, candidate)
            if constante is not None:
                valeurs[nom] = constante
                break
    return valeurs


def _valeur_constante(lignes: pd.DataFrame, colonne: str) -> float | None:
    """La valeur d'une colonne si elle en a une seule sur le point de vol."""
    if colonne not in lignes.columns:
        return None
    valeurs = lignes[colonne].dropna()
    if valeurs.empty or valeurs.nunique() != 1:
        return None
    return float(valeurs.iloc[0])


def _nettoyer(racine: Path) -> None:
    """Vide l'arborescence avant d'écrire, par le nettoyeur de cfd-plot."""
    from ..report._plotting_lib import get_plotting

    get_plotting().clean_figure_dir(racine, mode="figures")
