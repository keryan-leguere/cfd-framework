"""Les deux bouts du modèle : le plan d'appels, et le tableau qu'il rend.

Un modèle d'établissement ne ressemble pas au squelette minimal du paquet. Il
reçoit des **listes d'axes** — ``L_MACH``, ``L_ALPHA``, ``L_ALTITUDE`` — qu'il
croise, et il rend un tableau large où chaque ligne porte le point de vol, les
coefficients, une quantité de métadonnées, et **les dictionnaires eux-mêmes** :
la table de lois employée et le tirage appliqué. C'est la bonne façon de faire :
un tableau qui porte ses propres lois se relit dans six mois.

Ce module fait la traduction, dans les deux sens.

    from cfd_dispersion import plan_croise, lire_sortie_modele

    pdv = plan_croise(Mach=L_MACH, Altitude_m=L_ALTITUDE, alpha=L_ALPHA)
    df = mon_modele(pdv, DICT_LAW_DISPERSION, ...)
    resultats, lois = lire_sortie_modele(df)

:func:`lire_sortie_modele` rend un tableau que le reste du paquet lit
directement — colonnes ``<coeff>_Biais`` et ``<coeff>_FE`` à plat — et les lois
relues depuis le tableau, sans que personne ait à les redonner à la main.

Le piège du croisement
----------------------
Un appel croisé applique **le même tirage** à tous les points du balayage : sur
treize incidences, chaque valeur tirée apparaît treize fois. Valider ce tableau
tel quel triple presque la statistique : la fonction de répartition empirique
est inchangée, donc *D* aussi, mais l'effectif est treize fois trop grand et le
seuil se resserre d'un facteur √13. Mesuré : cinq cents tirages conformes
passent à p = 0.61, et rejetés à p = 8·10⁻⁷ une fois croisés.

D'où le numéro de tirage que pose :func:`aplatir_tirage`, et l'argument
``unique_par=("tirage",)`` de ``valider_lot`` et ``figures_par_pdv``. L'oubli
n'est pas silencieux : la validation refuse un échantillon massivement
redondant en nommant le remède.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Iterable, Mapping, Sequence
from itertools import product
from typing import Any

import pandas as pd

from .lois import COMPOSANTES, Correlation, JeuDeLois, charger_lois

__all__ = [
    "COLONNE_LOIS",
    "COLONNE_NUMERO",
    "COLONNE_TIRAGE",
    "aplatir_tirage",
    "lire_dict",
    "lire_sortie_modele",
    "lois_depuis_tableau",
    "plan_croise",
]

#: Nom par défaut de la colonne portant le tirage appliqué à la ligne.
COLONNE_TIRAGE = "DICT_TIRAGE"

#: Nom par défaut de la colonne portant la table de lois de l'étude.
COLONNE_LOIS = "DICT_LAW_DISPERSION"

#: Nom de la colonne d'identifiant de tirage ajoutée à l'aplatissement.
COLONNE_NUMERO = "tirage"


# ---------------------------------------------------------------------------
# En entrée : le plan d'appels
# ---------------------------------------------------------------------------


def plan_croise(**axes: Iterable[Any]) -> list[dict[str, Any]]:
    """Le produit cartésien des axes, dans l'ordre où ils sont donnés.

    C'est le plan d'appels d'un modèle croisé : une entrée par combinaison,
    le dernier axe variant le plus vite.

    Parameters
    ----------
    axes:
        Une liste de valeurs par variable — ``Mach=L_MACH, alpha=L_ALPHA``.

    Returns
    -------
    list of dict
        ``[{"Mach": 0.7, "alpha": 0.0}, {"Mach": 0.7, "alpha": 2.0}, …]``.
        Se passe tel quel à un modèle, ou à ``pd.DataFrame`` pour le tableau.

    Raises
    ------
    ValueError
        Si aucun axe n'est donné, ou si l'un d'eux est vide — le produit
        serait alors vide, et un plan vide se remarque bien plus tard.

    Examples
    --------
    >>> plan_croise(Mach=[0.7, 0.8], alpha=[0.0, 2.0])[:3]
    [{'Mach': 0.7, 'alpha': 0.0}, {'Mach': 0.7, 'alpha': 2.0}, {'Mach': 0.8, 'alpha': 0.0}]
    """
    if not axes:
        raise ValueError("aucun axe : passer au moins une liste, p. ex. plan_croise(Mach=L_MACH)")

    valeurs = {nom: list(liste) for nom, liste in axes.items()}
    vides = [nom for nom, liste in valeurs.items() if not liste]
    if vides:
        raise ValueError(
            f"axe(s) vide(s) : {vides} ; le produit cartésien serait vide, "
            "et un plan vide ne se remarque qu'au moment de tracer"
        )

    noms = list(valeurs)
    return [dict(zip(noms, combinaison)) for combinaison in product(*valeurs.values())]


# ---------------------------------------------------------------------------
# En sortie : les colonnes dictionnaires
# ---------------------------------------------------------------------------


def lire_dict(valeur: Any) -> dict[str, Any]:
    """Rend un dictionnaire, qu'il soit déjà un dict ou une chaîne.

    Un ``DataFrame`` qui porte un dictionnaire par ligne perd le dictionnaire
    dès qu'il passe par un CSV : il en revient sous forme de chaîne, en JSON
    (guillemets doubles) ou en ``repr`` Python (guillemets simples) selon
    l'écrivain. Les deux sont acceptés, pour que le tableau relu d'un fichier
    se traite comme celui qui sort du modèle.

    Raises
    ------
    ValueError
        Si la valeur n'est ni un dictionnaire ni une chaîne qui en décrit un.
    """
    if isinstance(valeur, Mapping):
        return dict(valeur)

    if isinstance(valeur, str):
        texte = valeur.strip()
        for lecteur in (json.loads, ast.literal_eval):
            try:
                lu = lecteur(texte)
            except (ValueError, SyntaxError):
                continue
            if isinstance(lu, Mapping):
                return dict(lu)
        raise ValueError(
            f"chaîne illisible comme dictionnaire : {_extrait(texte)} ; "
            "attendu du JSON ou un repr Python"
        )

    raise ValueError(
        f"attendu un dictionnaire ou une chaîne en décrivant un, reçu un "
        f"{type(valeur).__name__} : {_extrait(str(valeur))}"
    )


def _extrait(texte: str, taille: int = 60) -> str:
    """Un extrait citable d'une valeur fautive, sans noyer le message."""
    return repr(texte if len(texte) <= taille else texte[:taille] + "…")


def _composante(nom: str) -> str | None:
    """Le nom canonique d'une composante, à la casse près."""
    for canonique in COMPOSANTES:
        if str(nom).strip().lower() == canonique.lower():
            return canonique
    return None


def aplatir_tirage(
    df: pd.DataFrame,
    *,
    colonne: str = COLONNE_TIRAGE,
    numero: str | None = COLONNE_NUMERO,
) -> pd.DataFrame:
    """Étale la colonne de tirages en colonnes ``<coeff>_Biais`` / ``<coeff>_FE``.

    C'est la traduction entre le tableau que rend un modèle — un dictionnaire
    de tirage par ligne — et le contrat de colonnes que lisent ``valider_lot``
    et ``figures_par_pdv``.

    Parameters
    ----------
    df:
        La sortie du modèle. N'est jamais modifiée : une copie est rendue.
    colonne:
        La colonne portant ``{coeff: {"Biais": …, "FE": …}}``, en dict ou en
        chaîne. Les noms de composantes sont reconnus à la casse près.
    numero:
        Nom de la colonne d'identifiant de tirage à ajouter — un entier par
        tirage **distinct**, numéroté dans l'ordre d'apparition. C'est lui qui
        permet de dédoublonner un appel croisé (``unique_par=``) et de
        regrouper les courbes (``courbes_par_tirage(par=[…])``). None pour ne
        pas l'ajouter.

    Returns
    -------
    pandas.DataFrame
        Le tableau d'origine, plus une colonne par composante et le numéro.

    Raises
    ------
    ValueError
        Si la colonne manque, si une ligne est illisible, si les lignes ne
        portent pas les mêmes coefficients, ou si une colonne à créer existe
        déjà — écraser une colonne du modèle serait pire que refuser.
    """
    if colonne not in df.columns:
        raise ValueError(
            f"colonne de tirage {colonne!r} absente ; le tableau porte {sorted(df.columns)}"
        )
    if numero is not None and numero in df.columns:
        raise ValueError(
            f"la colonne {numero!r} existe déjà ; passer numero='autre_nom' pour "
            "l'identifiant de tirage, ou numero=None pour ne pas en ajouter"
        )

    tirages = [lire_dict(valeur) for valeur in df[colonne]]
    if not tirages:
        return df.copy()

    # Normalisés une fois : les valeurs sont ensuite lues sur ces
    # dictionnaires-là, et non sur les bruts — dont les composantes peuvent
    # s'écrire « biais » ou « FE » selon le modèle.
    plats = [_normaliser_tirage(tirage, ligne=indice) for indice, tirage in enumerate(tirages)]
    colonnes = _colonnes_de_tirage(plats)

    resultat = df.copy()
    for cle, nom in colonnes.items():
        if nom in resultat.columns:
            raise ValueError(
                f"la colonne {nom!r} existe déjà dans le tableau du modèle ; "
                "elle serait écrasée par l'aplatissement du tirage"
            )
        resultat[nom] = [plat[cle] for plat in plats]

    if numero is not None:
        resultat[numero] = _numeroter(plats)
    return resultat


def _colonnes_de_tirage(
    plats: Sequence[Mapping[tuple[str, str], float]],
) -> dict[tuple[str, str], str]:
    """Les colonnes à créer, après vérification que toutes les lignes concordent."""
    reference = plats[0]
    for indice, courant in enumerate(plats[1:], start=1):
        if set(courant) != set(reference):
            manquants = sorted(set(reference) - set(courant))
            surnumeraires = sorted(set(courant) - set(reference))
            raise ValueError(
                f"ligne {indice} : le tirage ne porte pas les mêmes composantes que la "
                f"ligne 0 ; manquante(s) {manquants}, en trop {surnumeraires}"
            )
    return {cle: f"{cle[0]}_{cle[1]}" for cle in reference}


def _normaliser_tirage(tirage: Mapping[str, Any], *, ligne: int) -> dict[tuple[str, str], float]:
    """``{coeff: {"Biais": …}}`` -> ``{(coeff, "Biais"): valeur}``."""
    plat: dict[tuple[str, str], float] = {}
    for coefficient, composantes in tirage.items():
        if not isinstance(composantes, Mapping):
            raise ValueError(
                f"ligne {ligne}, coefficient {coefficient!r} : attendu "
                f"{{'Biais': …, 'FE': …}}, reçu un {type(composantes).__name__}"
            )
        for nom, valeur in composantes.items():
            canonique = _composante(nom)
            if canonique is None:
                raise ValueError(
                    f"ligne {ligne}, coefficient {coefficient!r} : composante {nom!r} "
                    f"inconnue ; attendu {list(COMPOSANTES)} (la casse est indifférente)"
                )
            plat[(str(coefficient), canonique)] = float(valeur)
    return plat


def _numeroter(plats: Sequence[Mapping[tuple[str, str], float]]) -> list[int]:
    """Un entier par tirage distinct, dans l'ordre de première apparition.

    Par **contenu** et non par ordre de ligne : c'est tout l'intérêt sur un
    appel croisé, où le même tirage revient à chaque point du balayage et doit
    porter le même numéro partout.
    """
    vus: dict[str, int] = {}
    numeros = []
    for plat in plats:
        empreinte = json.dumps(
            {
                f"{coefficient}_{composante}": valeur
                for (coefficient, composante), valeur in plat.items()
            },
            sort_keys=True,
        )
        numeros.append(vus.setdefault(empreinte, len(vus)))
    return numeros


def lois_depuis_tableau(
    df: pd.DataFrame,
    *,
    colonne: str = COLONNE_LOIS,
    correlation: Correlation = None,
) -> JeuDeLois:
    """Relit la table de lois portée par le tableau du modèle.

    Un tableau qui porte ses propres lois n'a pas besoin qu'on lui redonne le
    fichier YAML de l'époque — et ne peut pas être validé contre les lois d'une
    autre étude.

    Raises
    ------
    ValueError
        Si la colonne manque, si une ligne est illisible, ou si les lignes ne
        décrivent pas toutes la même table : le message nomme la première
        ligne divergente, car valider une étude contre deux tables différentes
        n'a pas de sens.
    """
    if colonne not in df.columns:
        raise ValueError(
            f"colonne de lois {colonne!r} absente ; le tableau porte {sorted(df.columns)}"
        )
    if df.empty:
        raise ValueError(f"tableau vide : rien à lire dans {colonne!r}")

    tables = [lire_dict(valeur) for valeur in df[colonne]]
    reference = json.dumps(tables[0], sort_keys=True, default=str)
    for indice, table in enumerate(tables[1:], start=1):
        if json.dumps(table, sort_keys=True, default=str) != reference:
            raise ValueError(
                f"la table de lois de la ligne {indice} diffère de celle de la ligne 0 ; "
                "une étude se valide contre une seule table — découper le tableau "
                "par groupe et appeler lois_depuis_tableau sur chaque morceau"
            )
    return charger_lois(tables[0], correlation=correlation)


def lire_sortie_modele(
    df: pd.DataFrame,
    *,
    tirage: str = COLONNE_TIRAGE,
    lois: str = COLONNE_LOIS,
    numero: str | None = COLONNE_NUMERO,
    correlation: Correlation = None,
) -> tuple[pd.DataFrame, JeuDeLois]:
    """Traduit la sortie d'un modèle en (tableau exploitable, lois).

    Une seule ligne entre le modèle et tout le reste du paquet :

        resultats, lois = lire_sortie_modele(df)
        verdicts = valider_lot(resultats, lois, par=("Mach", "Altitude_m"),
                               unique_par=("tirage",))

    Les métadonnées du tableau sont conservées telles quelles : le paquet ne
    lit que les colonnes qu'il nomme, les autres voyagent sans le gêner.

    Parameters
    ----------
    df:
        La sortie du modèle, une ligne par appel.
    tirage, lois:
        Les colonnes portant les deux dictionnaires.
    numero:
        Nom de la colonne d'identifiant de tirage à ajouter. Voir
        :func:`aplatir_tirage`.
    correlation:
        Transmise à :func:`cfd_dispersion.charger_lois` — la corrélation n'est
        pas dans la table de lois, c'est une hypothèse de tirage.

    Returns
    -------
    (pandas.DataFrame, JeuDeLois)
    """
    return aplatir_tirage(df, colonne=tirage, numero=numero), lois_depuis_tableau(
        df, colonne=lois, correlation=correlation
    )
