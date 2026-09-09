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

import os
import pickle
import sys
import warnings
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..core.combinaison import TOLERANCE_ACCORD, AccordModele
from ..core.convention import Convention, ConventionArg, convention
from ..core.lois import JeuDeLois
from ..core.relation import Relation, RelationArg, charger_relations, composantes_derivees
from ..core.relation import lois_avec_relations as _lois_avec_relations
from ..core.tableau import COLONNE_LOIS, COLONNE_NUMERO, COLONNE_TIRAGE, tirage_depuis_ligne
from ..core.tableau import lire_sortie_modele as _lire_sortie_modele
from ..core.tirage import Tirage
from ..report.parcours import imprimer_bilan, imprimer_note, imprimer_plan, progression
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
    "resoudre_coefficients",
    "verifier_coefficients",
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

    def fichiers_prevus(self) -> list[dict[str, Any]]:
        """L'inventaire que ce travail écrirait, sans rien tracer.

        C'est ce qui rend le mode « à blanc » possible : les noms de fichiers
        sont composés ici et par ``_executer`` de la même façon, si bien qu'une
        énumération dit exactement ce qu'une exécution écrirait.
        """
        commun: dict[str, Any] = {**self.point, "tirage": self.numero}
        sans_verdict = {"calcul": None, "modele": None, "ecart": None, "accord": None}
        lignes: list[dict[str, Any]] = []

        if self.par_coefficient:
            for nom in self.coefficients:
                lignes.extend(
                    {
                        **commun,
                        "figure": nom,
                        "fichier": self.dossier / f"{nom}.{extension}",
                        **sans_verdict,
                    }
                    for extension in self.formats
                )

        if self.matrice:
            total = max(1, -(-len(self.coefficients) // self.max_par_figure))
            for numero in range(1, total + 1):
                base = NOM_MATRICE if total == 1 else f"{NOM_MATRICE}_{numero:02d}"
                lignes.extend(
                    {**commun, "figure": NOM_MATRICE, "fichier": self.dossier / f"{base}.{ext}"}
                    for ext in self.formats
                )

        return lignes

    @property
    def description(self) -> str:
        """Ce qu'affiche la barre de progression pendant ce travail."""
        return f"{self.etiquette} · tirage {self.numero}"


def _executer(travail: _Travail) -> list[dict[str, Any]]:
    """Trace et écrit les figures d'un tirage ; rend leur inventaire.

    Fonction de module, et non fermeture : c'est ce qui la rend sérialisable,
    donc utilisable telle quelle dans un processus ouvrier.

    Le backend graphique n'est pas forcé ici : cette fonction tourne aussi en
    direct quand ``n_jobs=1``, et y basculer Matplotlib en Agg casserait le
    tracé interactif de l'appelant. C'est le rôle de :func:`_init_ouvrier`, qui
    ne tourne que dans les processus de travail.
    """
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
    *,
    verbeux: bool = False,
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

    La méthode de démarrage est celle **par défaut** — ``fork`` sous Linux —
    comme ``cfd_plot.batch_plot``, et non ``forkserver`` : voir
    :func:`_main_rejouable` pour ce que ce dernier coûtait. Deux conséquences
    assumées, l'une bonne et l'autre non :

    * une ``Convention`` ou une fonction définie dans le script de l'appelant
      marche telle quelle dans les ouvriers, alors que ``forkserver`` et
      ``spawn`` exigeraient qu'elle vive dans un module importable ;
    * ``fork`` depuis un processus qui a déjà des fils — et NumPy en ouvre huit
      dès qu'on importe pandas — reste théoriquement à risque, et Python 3.12
      le signale par un ``DeprecationWarning``. L'avertissement est laissé
      visible ; ``n_jobs=1`` est la sortie de secours.
    """
    if not travaux:
        return []
    if executer is None:
        executer = _executer

    if n_jobs != 1:
        motif = _pourquoi_pas_en_parallele(travaux[0])
        if motif is not None:
            warnings.warn(
                f"parcours ramené à un seul processus : {motif}",
                UserWarning,
                stacklevel=3,
            )
            n_jobs = 1

    if n_jobs == 1:
        return _consommer(travaux, (executer(travail) for travail in travaux), verbeux, "séquence")

    ouvriers = None if n_jobs < 0 else n_jobs
    with ProcessPoolExecutor(max_workers=ouvriers, initializer=_init_ouvrier) as pool:
        # `map` conserve l'ordre : l'inventaire ne dépend pas de l'ordonnancement.
        return _consommer(
            travaux, pool.map(executer, travaux), verbeux, f"{_nombre_ouvriers(n_jobs)} processus"
        )


def _nombre_ouvriers(n_jobs: int) -> int:
    """Le nombre de processus qu'emploiera le parcours, ``-1`` résolu."""
    if n_jobs >= 1:
        return int(n_jobs)
    return os.cpu_count() or 1


def _consommer(
    travaux: Sequence[Any],
    lots: Any,
    verbeux: bool,
    mode: str,
) -> list[dict[str, Any]]:
    """Vide l'itérateur de résultats, avec ou sans barre de progression.

    La description est mise à jour **avant** d'attendre le lot suivant, et non
    après : ce qui s'affiche est ce que le parcours est en train de faire, pas
    ce qu'il vient de finir.
    """
    barre = progression(len(travaux)) if verbeux else None
    if barre is None:
        return [ligne for lot in lots for ligne in lot]

    lignes: list[dict[str, Any]] = []
    iterateur = iter(lots)
    with barre:
        tache = barre.add_task(f"parcours ({mode})", total=len(travaux))
        for travail in travaux:
            description = getattr(travail, "description", None)
            if description is not None:
                barre.update(tache, description=str(description))
            lignes.extend(next(iterateur))
            barre.advance(tache)
    return lignes


def _init_ouvrier() -> None:
    """Impose un backend sans fenêtre dans un processus de travail.

    Passée en ``initializer`` du pool, cette fonction tourne une fois par
    ouvrier au démarrage, et **jamais dans le processus appelant**. C'est ce
    qui la distingue d'un ``matplotlib.use("Agg")`` posé dans la fonction de
    travail : celle-ci tourne aussi en direct quand ``n_jobs=1``, et y changer
    le backend global casserait le tracé interactif de l'appelant pour tout ce
    qu'il fera ensuite.

    Un ouvrier n'a pas d'affichage à lui. Sous ``fork``, il hérite pourtant du
    backend du parent — ``tkagg`` ou ``qtagg`` si personne ne l'a forcé — donc
    d'une connexion graphique à demi initialisée, ce qui est précisément le
    montage qui se fige ou plante dans un processus fils.
    """
    import matplotlib

    matplotlib.use("Agg")


def _pourquoi_pas_en_parallele(travail: Any) -> str | None:
    """Ce qui interdit le rendu parallèle, en une phrase, ou None.

    Deux causes, et les deux valent mieux dites qu'un lot à mi-chemin : un
    travail qui ne se sérialise pas, et une méthode de démarrage qui rejouerait
    le script appelant alors qu'il n'est pas rejouable.
    """
    try:
        pickle.dumps(travail)
    except Exception as erreur:  # pragma: no cover - dépend de l'appelant
        return (
            f"le travail ne se sérialise pas ({erreur}). Une Convention écrite en "
            "lambda en est la cause la plus fréquente ; une fonction de module passe."
        )
    return _main_rejouable()


def _main_rejouable() -> str | None:
    """Dit si le ``__main__`` de l'appelant survivrait à une réexécution.

    Pourquoi la question se pose
    ----------------------------
    Ce module a longtemps forcé le contexte ``forkserver``, pour éviter un
    ``fork`` nu depuis un processus qui a déjà des fils. C'était un mauvais
    marché : ``forkserver`` emporte les données de préparation de ``spawn``,
    et **chaque ouvrier réexécute le script de l'appelant** (``spawn.py``,
    ``_fixup_main_from_path``). Cela se voyait de trois façons, toutes
    dépendantes de la machine et du point d'entrée :

    * un script non protégé par ``if __name__ == "__main__":`` relançait le
      parcours entier dans chaque ouvrier ;
    * un ``__main__`` qui n'est pas un fichier — entrée standard, notebook —
      donnait un ``FileNotFoundError`` dans l'ouvrier, remonté en
      ``BrokenProcessPool`` sans rapport visible avec la cause ;
    * un script qui travaille au niveau module refaisait ce travail n fois.

    ``cfd_plot.batch_plot`` n'a jamais eu le problème : il prend la méthode de
    démarrage par défaut — ``fork`` sous Linux, qui ne rejoue rien — et neutralise
    le backend graphique par un ``initializer``. C'est ce que fait ce module
    désormais, et :func:`_init_ouvrier` est cet initializer.

    Reste le cas des plateformes où le défaut n'est pas ``fork`` (macOS,
    Windows, et Linux à partir de Python 3.14) : la réexécution y revient, et
    cette fonction la refuse quand elle ne peut pas aboutir, plutôt que de
    laisser tomber un ``BrokenProcessPool``.
    """
    import multiprocessing

    methode = multiprocessing.get_start_method(allow_none=False)
    if methode == "fork":
        return None

    principal = sys.modules.get("__main__")
    if principal is None or getattr(principal, "__spec__", None) is not None:
        # `python -m paquet` : l'ouvrier réimporte le module par son nom.
        return None
    chemin = getattr(principal, "__file__", None)
    if chemin is None:
        # `python -c` : il n'y a pas de script à rejouer, donc rien à craindre.
        return None
    if not Path(chemin).is_file():
        return (
            f"la méthode de démarrage « {methode} » réexécute le script appelant dans "
            f"chaque ouvrier, et celui-ci n'en est pas un ({chemin!r}) — entrée standard "
            "ou notebook. Lancer le parcours depuis un fichier .py protégé par "
            '`if __name__ == "__main__":`, ou garder n_jobs=1.'
        )
    return None


def figures_tirage_par_pdv(
    df: pd.DataFrame,
    *,
    points_de_vol: Mapping[str, Any],
    racine: Any,
    lois: JeuDeLois | None = None,
    reference: pd.DataFrame | None = None,
    coefficients: Sequence[str] | None = None,
    coefficients_en_plus: Sequence[str] | None = None,
    relations: RelationArg = None,
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
    verbeux: bool = False,
    rapport: bool = True,
    a_blanc: bool = False,
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
        jeu de lois — plus les cibles de *relations*. Un nom absent des lois est
        admis s'il est une colonne du tableau : sa figure montre alors le
        nominal et la valeur du modèle, en disant qu'aucune loi ne le décrit.
        Le donner **remplace** la liste par défaut.
    coefficients_en_plus:
        Les coefficients à tracer **en plus** de ceux que le défaut retient.
        C'est la façon d'ajouter une colonne de sortie sans avoir à réécrire la
        liste complète des coefficients dispersés ::

            coefficients_en_plus=["CA", "Cn_beta"]

        Les doublons sont ignorés, et l'ordre d'écriture est conservé.
    relations:
        Les coefficients de sortie qui se **déduisent** de ceux qu'on tire ::

            relations={"CN": "-CZ", "CA": "CX1 + CX2"}

        Chaque cible reçoit alors ses lois, dérivées de celles de ses sources
        (:func:`cfd_dispersion.loi_derivee`), et ses valeurs tirées, dérivées du
        tirage de la ligne : elle est tracée comme un coefficient dispersé
        ordinaire, avec ses deux panneaux de composantes, sa loi combinée et
        l'accord entre le calcul et ce que le modèle a rendu — lequel contrôle
        du coup la relation elle-même.

        Les poids du facteur d'échelle sont des **parts**, donc les lois sont
        dérivées **point de vol par point de vol**, à partir des valeurs
        nominales des sources : celles-ci doivent être dans *reference* (ou
        dans *nominaux*) dès que la relation a plus d'un terme. Une relation à
        un seul terme, ``CN = -CZ``, s'en passe.
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
    verbeux, rapport, a_blanc:
        Le rendu terminal, repris de ``cfd_plot.batch_plot`` avec les mêmes
        rôles que ses ``verbose`` / ``report`` / ``dry_run`` :

        ``verbeux``
            imprime le **plan** — coefficients, relations, boucles de points de
            vol, nombre de fichiers attendus — puis une barre de progression
            nommant le point de vol et le tirage en cours.
        ``rapport``
            imprime, après coup, le **bilan** des fichiers écrits, groupé par
            point de vol, avec leur taille. Vrai par défaut, comme là-bas.
        ``a_blanc``
            énumère ce qui serait écrit et **n'écrit rien** — ni figure, ni
            nettoyage. L'inventaire rendu a la même forme, colonnes de verdict
            comprises, mais celles-ci sont vides : aucune figure n'a été tracée,
            donc aucun calcul n'a été confronté au modèle.

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
    liens = charger_relations(relations)
    noms = resoudre_coefficients(jeu, coefficients, coefficients_en_plus, liens)
    # Un coefficient sans loi n'est pas une erreur s'il est une colonne du
    # tableau : il n'est simplement pas dispersé, et sa figure montrera le
    # nominal et ce que le modèle a rendu. Sans loi *ni* colonne *ni* relation,
    # en revanche, il n'y a rien à en dire — et le refus le nomme.
    verifier_coefficients(noms, jeu, liens, tableau)
    liens = {cible: lien for cible, lien in liens.items() if cible in noms}

    # Les sources d'une relation sont tirées même si personne ne les trace :
    # c'est d'elles que se déduisent les composantes de la cible.
    tires = _sans_doublons(
        [nom for nom in noms if nom in jeu],
        [source for lien in liens.values() for source in lien.sources],
    )
    # Les nominaux des sources, de même, sont nécessaires à la dérivation des
    # lois — mais on ne trace pas ces coefficients pour autant.
    a_chiffrer = _sans_doublons(noms, tires)

    specs = _specifications(points_de_vol, tableau)
    variables = [cle for cle, spec in specs.items() if len(spec["values"]) > 1]

    base = Path(racine)
    if nettoyer:
        if a_blanc:
            imprimer_note(f"à blanc : {base} n'est pas vidée")
        else:
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
            a_chiffrer,
            nominaux,
            _selectionner(reference, point) if reference is not None else None,
            point=point,
        )
        jeu_du_point, valeurs_nominales = _deduire(
            jeu, liens, valeurs_nominales, relation, etiquette
        )

        for numero, ligne in _tirages_du_point(lignes, colonne_tirage, max_tirages):
            travaux.append(
                _Travail(
                    point=point,
                    numero=numero,
                    # Seuls les coefficients qui ont des lois ont été tirés :
                    # demander les autres au tirage le ferait échouer, alors
                    # qu'ils sont simplement ailleurs.
                    tirage=_tirage_du_point(
                        ligne, tires, liens, valeurs_nominales, relation, numero
                    ),
                    lois=jeu_du_point,
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

    if not travaux:
        raise ValueError(
            "aucun point de vol demandé n'a de ligne dans le tableau ; "
            f"colonnes lues : {list(specs)} — vérifier les valeurs demandées"
        )

    if verbeux:
        _plan(
            travaux=travaux,
            noms=noms,
            liens=liens,
            specs=specs,
            base=base,
            formats=formats,
            profil=profil,
            n_jobs=n_jobs,
            nettoyer=nettoyer,
            a_blanc=a_blanc,
            avec_reference=reference is not None,
        )

    if a_blanc:
        inventaire = [ligne for travail in travaux for ligne in travail.fichiers_prevus()]
    else:
        inventaire = _repartir(travaux, n_jobs, verbeux=verbeux)

    colonnes = [*specs, "tirage", "figure", "fichier", "calcul", "modele", "ecart", "accord"]
    resultat = pd.DataFrame(inventaire, columns=colonnes if inventaire else None)

    if rapport:
        imprimer_bilan(
            resultat,
            cles_pdv=list(specs),
            colonne_groupe="tirage",
            titre_groupe="tirage",
            racine=base,
            a_blanc=a_blanc,
            specs=specs,
        )
    return resultat


# ---------------------------------------------------------------------------
# Coefficients, relations et lois dérivées
# ---------------------------------------------------------------------------


def resoudre_coefficients(
    jeu: Mapping[str, Any],
    demandes: Sequence[str] | None,
    en_plus: Sequence[str] | None,
    liens: Mapping[str, Relation],
) -> list[str]:
    """La liste des coefficients à tracer, dans l'ordre.

    Trois apports, dans cet ordre :

    1. **le défaut** — tous ceux du jeu de lois, puis les cibles des relations.
       C'est ce qu'on obtient sans rien préciser, et c'est presque toujours ce
       qu'on veut : le parcours suit ce qui est dispersé ;
    2. ``coefficients=`` **remplace** ce défaut, pour n'en tracer qu'une partie
       ou en changer l'ordre ;
    3. ``coefficients_en_plus=`` **s'y ajoute**, ce qui évite de réécrire toute
       la liste pour une colonne de sortie de plus.

    Les doublons sont écartés en gardant la première occurrence.
    """
    defaut = [*jeu, *(cible for cible in liens if cible not in jeu)]
    retenus = list(demandes) if demandes is not None else defaut
    return _sans_doublons(retenus, list(en_plus or ()))


def verifier_coefficients(
    noms: Sequence[str],
    jeu: Mapping[str, Any],
    liens: Mapping[str, Relation],
    tableau: pd.DataFrame,
) -> None:
    """Refuse un coefficient dont rien ne parle, en le nommant."""
    inconnus = sorted(
        nom for nom in noms if nom not in jeu and nom not in liens and nom not in tableau.columns
    )
    if inconnus:
        raise ValueError(
            f"coefficient(s) {inconnus} : ni loi, ni relation, ni colonne dans le tableau — "
            "rien à tracer d'eux"
        )


def _sans_doublons(*listes: Sequence[str]) -> list[str]:
    """Les noms de plusieurs listes, dans l'ordre, sans répétition."""
    vus: dict[str, None] = {}
    for liste in listes:
        for nom in liste:
            vus.setdefault(nom, None)
    return list(vus)


def _deduire(
    jeu: JeuDeLois,
    liens: Mapping[str, Relation],
    valeurs_nominales: dict[str, Any],
    relation: Convention,
    etiquette: str,
) -> tuple[JeuDeLois, dict[str, Any]]:
    """Les lois du point de vol, augmentées de celles que les relations déduisent.

    Les poids du facteur d'échelle sont des parts des valeurs nominales : les
    lois dérivées **changent donc d'un point de vol à l'autre**, et c'est ici
    qu'elles sont calculées, une fois par point.

    La valeur nominale de la cible en découle aussi. Quand la référence la
    porte déjà, les deux doivent tomber sur le même nombre : sinon la relation
    n'est pas celle que le modèle applique, et toutes les lois dérivées de ce
    point de vol seraient fausses sans que rien ne le dise.
    """
    if not liens:
        return jeu, valeurs_nominales

    try:
        augmente = _lois_avec_relations(
            jeu, liens, nominaux=valeurs_nominales, convention_=relation
        )
    except ValueError as erreur:
        raise ValueError(f"point de vol {etiquette} : {erreur}") from None

    nominaux = dict(valeurs_nominales)
    for cible, lien in liens.items():
        if any(source not in nominaux for source in lien.sources):
            continue
        calcule = float(np.asarray(lien.appliquer(nominaux), dtype=float).reshape(-1)[0])
        connu = nominaux.get(cible)
        if connu is None:
            nominaux[cible] = calcule
            continue
        echelle = abs(float(connu)) or 1.0
        if abs(float(connu) - calcule) > TOLERANCE_ACCORD * echelle:
            raise ValueError(
                f"point de vol {etiquette} : la relation « {lien} » donne "
                f"{cible} = {calcule:.6g}, là où la référence porte {float(connu):.6g}. "
                "La relation n'est pas celle qu'applique le modèle — les lois qu'on en "
                f"déduirait pour {cible!r} seraient fausses."
            )
    return augmente, nominaux


def _tirage_du_point(
    ligne: Mapping[str, Any],
    tires: Sequence[str],
    liens: Mapping[str, Relation],
    nominaux: Mapping[str, Any],
    relation: Convention,
    numero: int,
) -> Tirage:
    """Le tirage de la ligne, augmenté des composantes que les relations déduisent.

    Sans cela, une cible aurait sa loi mais aucune valeur à y situer : ses deux
    premiers panneaux montreraient une densité sans son trait vertical, et le
    contrôle modèle / calcul n'aurait rien à recalculer.
    """
    tirage = tirage_depuis_ligne(ligne, list(tires), convention_=relation, numero=numero)
    if not liens:
        return tirage

    valeurs = dict(tirage.valeurs)
    for cible, lien in liens.items():
        if any(source not in valeurs for source in lien.sources):
            continue
        valeurs[cible] = composantes_derivees(
            lien, valeurs, nominaux=nominaux, convention_=relation
        )
    return Tirage(
        valeurs=valeurs,
        convention=tirage.convention,
        graine=tirage.graine,
        methode=tirage.methode,
        numero=tirage.numero,
    )


# ---------------------------------------------------------------------------
# Le plan
# ---------------------------------------------------------------------------


def _plan(
    *,
    travaux: Sequence[_Travail],
    noms: Sequence[str],
    liens: Mapping[str, Relation],
    specs: Mapping[str, Mapping[str, Any]],
    base: Path,
    formats: Sequence[str],
    profil: str,
    n_jobs: int,
    nettoyer: bool,
    a_blanc: bool,
    avec_reference: bool,
) -> None:
    """Imprime ce que le parcours va faire, avant qu'il le fasse."""
    fichiers = sum(len(travail.fichiers_prevus()) for travail in travaux)
    points = {travail.etiquette: 0 for travail in travaux}
    figures = dict.fromkeys(points, 0)
    for travail in travaux:
        points[travail.etiquette] += 1
        figures[travail.etiquette] += len(travail.fichiers_prevus())

    apercu = [
        ("Coefficients", f"{', '.join(noms)}  ({len(noms)})"),
    ]
    if liens:
        apercu.append(("Relations", "  ·  ".join(str(lien) for lien in liens.values())))
    apercu.extend(
        [
            ("Points de vol", f"{', '.join(specs)}  ({len(points)} retenu(s))"),
            ("Racine", str(base)),
            ("Formats", ", ".join(formats)),
            ("Style", profil),
            ("Référence", "oui" if avec_reference else "non (nominaux imposés ou absents)"),
            ("Mode", "à blanc (rien n'est écrit)" if a_blanc else "écriture"),
            ("Parallèle", _note_parallele(n_jobs, travaux, a_blanc)),
            ("Nettoyage", _note_nettoyage(nettoyer, a_blanc)),
            ("Figures", f"{len(travaux)} tirage(s)  →  {fichiers} fichier(s)"),
        ]
    )
    imprimer_plan(
        titre="Plan du parcours des tirages",
        apercu=apercu,
        specs=specs,
        par_point=[(etiquette, points[etiquette], figures[etiquette]) for etiquette in points],
        entete_par_point=("point de vol", "tirages", "fichiers"),
    )


def _note_nettoyage(nettoyer: bool, a_blanc: bool) -> str:
    """Ce que le parcours fera de *nettoyer* — rien, à blanc."""
    if not nettoyer:
        return "non"
    return "demandé, mais sauté (à blanc)" if a_blanc else "oui"


def _note_parallele(n_jobs: int, travaux: Sequence[Any], a_blanc: bool) -> str:
    """Ce que le parcours fera de *n_jobs*, contrôle de sérialisabilité compris."""
    if a_blanc:
        return "sans objet (rien n'est tracé)"
    if n_jobs == 1:
        return "séquence (n_jobs=1)"
    motif = _pourquoi_pas_en_parallele(travaux[0]) if travaux else None
    if motif is not None:
        return f"demandé {n_jobs}, ramené à la séquence — {motif}"
    return f"{_nombre_ouvriers(n_jobs)} processus"


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
