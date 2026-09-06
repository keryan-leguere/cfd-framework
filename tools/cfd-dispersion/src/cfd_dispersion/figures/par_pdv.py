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
**La valeur nominale vient d'un second tableau**, ``reference=`` : le même
modèle, tourné une fois avec un tirage neutre (biais 0, FE 1 pour la convention
linéaire — voir :func:`cfd_dispersion.tirage_neutre`), donc des coefficients non
dispersés. Elle peut aussi être imposée (``nominaux=``) ou lue dans une colonne
``"<coeff>_nominal"``. Sans elle, les deux panneaux de composantes sont tracés
quand même et le troisième dit ce qui lui manque.

**La colonne ``<coeff>`` est la sortie dispersée du modèle**, pas un nominal.
Elle sert à autre chose, et c'est le seul contrôle du paquet qui porte sur le
modèle : le paquet recalcule ``convention(nominal, biais, FE)`` et confronte les
deux. Ils doivent tomber sur le même nombre ; quand ils n'y tombent pas, c'est
une convention différente de part et d'autre, une référence qui n'est pas celle
qu'a vue le modèle, ou un modèle qui n'applique pas la dispersion là où on
croit. Le verdict est écrit sur la figure et dans l'inventaire.

**Seuls les premiers tirages sont tracés.** Cent tirages sur quatre points de
vol font quatre cents figures par coefficient, que personne ne regardera :
``max_tirages`` en garde quinze par point de vol. Ce sont les premiers dans
l'ordre des numéros, et non un échantillon au hasard — pour qu'une deuxième
exécution donne les mêmes.
"""

from __future__ import annotations

import pickle
import warnings
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

from ..core.combinaison import TOLERANCE_ACCORD, AccordModele
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
NOM_MATRICE = "matrice"

#: Ancien nom, gardé pour l'usage interne du module.
_NOM_MATRICE = NOM_MATRICE


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
    disperses_modele: dict[str, Any]
    dossier: Path
    etiquette: str
    formats: tuple[str, ...]
    par_coefficient: bool
    matrice: bool
    convention: Convention
    sigmas: tuple[int, ...] | None
    max_par_figure: int
    tolerance: float
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
                travail.lois.get(nom),
                travail.tirage,
                nominal=travail.nominaux.get(nom),
                disperse_modele=travail.disperses_modele.get(nom),
                tolerance=travail.tolerance,
                chemin=travail.dossier / nom,
                formats=travail.formats,
                convention_=travail.convention,
                etiquette=travail.etiquette,
                sigmas=travail.sigmas,
                profil=travail.profil,
            )
            plt.close(rendue.figure)
            verdict = _colonnes_accord(rendue.accord)
            inventaire.extend(
                {**commun, "figure": nom, "fichier": fichier, **verdict}
                for fichier in rendue.fichiers
            )

    if travail.matrice:
        pages = figure_tirage_matrice(
            travail.lois,
            travail.tirage,
            nominaux=travail.nominaux,
            disperses_modele=travail.disperses_modele,
            tolerance=travail.tolerance,
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


def _colonnes_accord(accord: AccordModele | None) -> dict[str, Any]:
    """Le verdict d'un coefficient, en colonnes d'inventaire."""
    if accord is None:
        return {"calcul": None, "modele": None, "ecart": None, "accord": None}
    return {
        "calcul": accord.calcul,
        "modele": accord.modele,
        "ecart": accord.ecart,
        "accord": accord.accord,
    }


def _repartir(
    travaux: Sequence[Any],
    n_jobs: int,
    executer: Callable[[Any], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Exécute les travaux, en séquence ou sur plusieurs processus.

    Une figure coûte une demi-seconde à écrire — la police du gabarit est
    vectorisée glyphe par glyphe — et un parcours en écrit des centaines. D'où
    ``n_jobs``, et d'où le contrôle de sérialisabilité qui le précède : une
    convention maison écrite en ``lambda`` ne passerait pas, et le parcours
    repasse alors en séquence **en le disant**, plutôt que d'échouer à
    mi-chemin.

    *executer* est la fonction qui fait une unité de travail. Elle est passée
    plutôt que codée en dur pour que l'histogramme par point de vol
    (:mod:`cfd_dispersion.figures.histogramme`) partage cette plomberie ; elle
    doit être de niveau module, faute de quoi elle ne se sérialiserait pas.
    """
    if not travaux:
        return []
    if executer is None:
        executer = _executer

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
        return [ligne for travail in travaux for ligne in executer(travail)]

    ouvriers = None if n_jobs < 0 else n_jobs
    with ProcessPoolExecutor(max_workers=ouvriers, mp_context=_contexte()) as pool:
        # `map` conserve l'ordre : l'inventaire ne dépend pas de l'ordonnancement.
        return [ligne for lot in pool.map(executer, travaux) for ligne in lot]


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
    reference: pd.DataFrame | None = None,
    coefficients: Sequence[str] | None = None,
    nominaux: Mapping[str, Any] | None = None,
    tolerance: float = TOLERANCE_ACCORD,
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
    reference:
        La sortie du **même modèle**, tourné une fois avec un tirage neutre
        (biais 0, FE 1) : c'est de là que viennent les valeurs nominales, point
        de vol par point de vol, dans la colonne du nom de chaque coefficient.
        Même structure que *df* ; une ligne par point de vol suffit.
    coefficients:
        Les coefficients à tracer, dans l'ordre voulu. Par défaut, tous ceux du
        jeu de lois. Un nom absent des lois est admis s'il est une colonne du
        tableau : sa figure montre alors le nominal et la valeur du modèle, en
        disant qu'aucune loi ne le décrit.
    nominaux:
        ``{coefficient: valeur}``, pour imposer les valeurs nominales, quand
        ni *reference* ni le tableau ne les portent.
    tolerance:
        Tolérance **relative** de l'accord entre le coefficient recalculé et
        celui que le modèle a rendu.
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
        tableau, si aucun point de vol demandé n'a de ligne, si un coefficient
        demandé n'est ni dans les lois ni dans le tableau, ou si les lois ne
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
    # Un coefficient sans loi n'est pas une erreur s'il est une colonne du
    # tableau : il n'est simplement pas dispersé, et sa figure montrera le
    # nominal et ce que le modèle a rendu. Sans loi *ni* colonne, en revanche,
    # il n'y a rien à en dire — et le refus le nomme.
    inconnus = sorted(nom for nom in noms if nom not in jeu and nom not in tableau.columns)
    if inconnus:
        raise ValueError(
            f"coefficient(s) {inconnus} : ni loi ni colonne dans le tableau — rien à tracer d'eux"
        )

    tires = [nom for nom in noms if nom in jeu]

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
        valeurs_nominales = _nominaux_du_point(
            lignes,
            noms,
            nominaux,
            _selectionner(reference, point) if reference is not None else None,
            point=point,
        )

        for numero, ligne in _tirages_du_point(lignes, colonne_tirage, max_tirages):
            travaux.append(
                _Travail(
                    point=point,
                    numero=numero,
                    # Seuls les coefficients qui ont des lois ont été tirés :
                    # demander les autres au tirage le ferait échouer, alors
                    # qu'ils sont simplement ailleurs.
                    tirage=tirage_depuis_ligne(ligne, tires, convention_=relation, numero=numero),
                    lois=jeu,
                    coefficients=tuple(noms),
                    nominaux=valeurs_nominales,
                    disperses_modele={
                        nom: float(ligne[nom]) for nom in noms if _lisible(ligne.get(nom))
                    },
                    dossier=dossier / _MOTIF_DOSSIER_TIRAGE.format(numero=numero),
                    etiquette=etiquette,
                    formats=tuple(formats),
                    par_coefficient=par_coefficient,
                    matrice=matrice,
                    convention=relation,
                    sigmas=None if sigmas is None else tuple(sigmas),
                    max_par_figure=max_par_figure,
                    tolerance=tolerance,
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

    colonnes = [*specs, "tirage", "figure", "fichier", "calcul", "modele", "ecart", "accord"]
    return pd.DataFrame(inventaire, columns=colonnes if inventaire else None)


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
    reference: pd.DataFrame | None = None,
    *,
    point: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Les valeurs nominales d'un point de vol, ou rien quand elles manquent.

    La règle, dans l'ordre :

    1. ce que l'appelant impose (*imposes*) ;
    2. le tableau de **référence** — le modèle tourné une fois avec un tirage
       neutre — dans sa colonne ``<coeff>`` ;
    3. la colonne ``"<coeff>_nominal"`` du tableau lui-même.

    La colonne ``<coeff>`` du tableau principal n'est **pas** lue comme un
    nominal : c'est la sortie dispersée du modèle, celle à laquelle le calcul
    est confronté. La prendre pour un nominal centrerait la loi sur le tirage
    qu'elle doit juger.
    """
    valeurs: dict[str, Any] = {}
    for nom in coefficients:
        if imposes is not None and nom in imposes:
            valeurs[nom] = imposes[nom]
            continue
        if reference is not None and not reference.empty and nom in reference.columns:
            candidates = reference[nom].dropna()
            if candidates.nunique() > 1:
                # Deux nominaux pour ce qu'on appelle un point de vol : c'est
                # que le point de vol est sous-défini. Le dire, plutôt que de
                # choisir l'un des deux ou de tracer un panneau muet.
                raise ValueError(
                    f"la référence donne {candidates.nunique()} valeurs de {nom!r} "
                    f"pour le point de vol {dict(point or {})} ; préciser le point de vol "
                    f"(candidates : {_cles_discriminantes(reference, coefficients)}) "
                    "ou passer nominaux="
                )
            if not candidates.empty:
                valeurs[nom] = float(candidates.iloc[0])
                continue
        constante = _valeur_constante(lignes, f"{nom}_nominal")
        if constante is not None:
            valeurs[nom] = constante
    return valeurs


def _lisible(valeur: Any) -> bool:
    """Vrai si la valeur est un nombre exploitable."""
    if valeur is None:
        return False
    try:
        return bool(pd.notna(valeur)) and not isinstance(valeur, str)
    except (TypeError, ValueError):  # pragma: no cover - valeur exotique
        return False


def _cles_discriminantes(
    reference: pd.DataFrame,
    coefficients: Sequence[str],
) -> list[str]:
    """Les colonnes qui distinguent encore les lignes d'un point de vol.

    Ce sont elles qui manquent au ``points_de_vol`` quand une référence rend
    deux nominaux là où on en attendait un — et les nommer vaut mieux que de
    lister toutes les colonnes du tableau.
    """
    exclues = {*coefficients, COLONNE_TIRAGE, COLONNE_LOIS, COLONNE_NUMERO}
    variables = []
    for colonne in reference.columns:
        if colonne in exclues:
            continue
        try:
            if reference[colonne].nunique() > 1:
                variables.append(str(colonne))
        except TypeError:  # pragma: no cover - colonne non comparable
            continue
    return sorted(variables)


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
