"""Ce qu'on donne au modèle, et ce qu'on exige qu'il rende.

Deux décisions gouvernent tout ce module, et elles méritent d'être lues avant
le code.

**On retire les QOI des entrées.** Le modèle reçoit les colonnes indépendantes
de la table, plus les constantes déclarées, et rien d'autre. Un modèle à qui
l'on tend la réponse ne prouve rien ; c'est ce retrait qui fait du contrôle un
contrôle.

**On ignore les colonnes indépendantes que le modèle rend.** Le cadre sur
lequel on compare et on trace est bâti sur les colonnes *de la table*, avec la
seule QOI du modèle greffée dessus. Un aller-retour en simple précision côté
Fortran suffirait sinon à décaler les abscisses du dernier bit — et
``cfd_plot.batch_plot`` filtre ses points de vol par **égalité stricte**, si
bien qu'une courbe entière disparaîtrait de la planche sans une erreur.

Ces colonnes rendues ne sont pas ignorées en silence pour autant : elles
servent à vérifier que le modèle n'a pas **réordonné ses lignes**, ce qui
fabriquerait des écarts là où il n'y en a pas.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from cfd_validation.data.spec import SpecTable

__all__ = ["ErreurModele", "cadre_modele", "cadre_table", "entrees", "verifier_sortie"]

#: Tolérance du contrôle d'alignement des lignes. Lâche à dessein : elle doit
#: absorber un aller-retour en simple précision (≈ 1e-7 en relatif) sans rien
#: laisser passer d'un réordonnancement, qui déplace les valeurs en grand.
RTOL_ALIGNEMENT = 1e-5


class ErreurModele(ValueError):
    """Le modèle n'a pas respecté son contrat.

    Distinct d'un simple écart numérique : ici le contrôle ne peut pas conclure,
    alors qu'un écart *est* une conclusion.
    """


def entrees(table: pd.DataFrame, spec: SpecTable) -> pd.DataFrame:
    """Le cadre de données à passer au modèle.

    Colonnes indépendantes de la table, puis constantes déclarées — celles que
    le modèle réclame mais que cette table-ci ne balaie pas. L'index est celui
    de la table, pour que le rapport puisse désigner un point par son numéro de
    ligne dans le tableau Fortran.
    """
    manquantes = [colonne for colonne in spec.colonnes if colonne not in table.columns]
    if manquantes:
        raise ErreurModele(
            f"table « {spec.nom} » : colonne(s) {manquantes} absente(s) du cadre lu. "
            f"Colonnes présentes : {list(table.columns)}."
        )
    cadre = table.loc[:, list(spec.independantes)].copy()
    for colonne, valeur in spec.constantes.items():
        cadre[colonne] = float(valeur)
    return cadre


def verifier_sortie(demande: pd.DataFrame, rendu: object, spec: SpecTable) -> pd.DataFrame:
    """Vérifie le cadre rendu par le modèle, et le rend aligné sur *demande*.

    Refuse bruyamment plutôt que de conclure de travers : un mauvais nombre de
    lignes, une QOI absente, une colonne non numérique, ou des lignes
    réordonnées.

    Raises
    ------
    ErreurModele
        Avec, dans le message, ce que le modèle a effectivement rendu.
    """
    if not isinstance(rendu, pd.DataFrame):
        raise ErreurModele(
            f"table « {spec.nom} » : le modèle doit rendre un DataFrame pandas, "
            f"reçu {type(rendu).__name__}. "
            "Voir 00_DOC/03_BRANCHER_SON_MODELE.md pour le contrat."
        )
    if len(rendu) != len(demande):
        raise ErreurModele(
            f"table « {spec.nom} » : le modèle a reçu {len(demande)} points et en a rendu "
            f"{len(rendu)}. Il doit rendre une ligne par ligne reçue, dans le même ordre."
        )

    absentes = [grandeur for grandeur in spec.qoi if grandeur not in rendu.columns]
    if absentes:
        raise ErreurModele(
            f"table « {spec.nom} » : QOI {absentes} absente(s) du cadre rendu. "
            f"Colonnes rendues : {list(rendu.columns)}."
        )

    aligne = rendu.set_axis(demande.index, axis=0)
    _verifier_numerique(aligne, spec)
    _verifier_ordre(demande, aligne, spec)
    return aligne


def cadre_modele(table: pd.DataFrame, rendu: pd.DataFrame, spec: SpecTable) -> pd.DataFrame:
    """Le cadre « modèle » : la géométrie de la table, la QOI du modèle.

    Même colonnes et mêmes valeurs d'abscisse que le cadre « table », au bit
    près — c'est ce qui permet de les superposer sur une même planche.
    """
    cadre = entrees(table, spec)
    for grandeur in spec.qoi:
        cadre[grandeur] = pd.to_numeric(rendu[grandeur], errors="coerce").to_numpy(dtype=float)
    return cadre


def cadre_table(table: pd.DataFrame, spec: SpecTable) -> pd.DataFrame:
    """Le cadre « table » : la référence, dans la même forme que le modèle."""
    cadre = entrees(table, spec)
    for grandeur in spec.qoi:
        cadre[grandeur] = pd.to_numeric(table[grandeur], errors="coerce").to_numpy(dtype=float)
    return cadre


# ---------------------------------------------------------------------------
# Les refus
# ---------------------------------------------------------------------------


def _verifier_numerique(rendu: pd.DataFrame, spec: SpecTable) -> None:
    """Une QOI non numérique est une rupture de contrat, pas un écart."""
    for grandeur in spec.qoi:
        colonne = rendu[grandeur]
        if not pd.api.types.is_numeric_dtype(colonne):
            converti = pd.to_numeric(colonne, errors="coerce")
            if converti.isna().all():
                raise ErreurModele(
                    f"table « {spec.nom} » : la QOI « {grandeur} » rendue n'est pas numérique "
                    f"(type {colonne.dtype})."
                )


def _verifier_ordre(demande: pd.DataFrame, rendu: pd.DataFrame, spec: SpecTable) -> None:
    """Les colonnes d'entrée rendues doivent valoir celles qu'on a passées.

    C'est le seul usage qu'on fait des colonnes indépendantes rendues par le
    modèle, et il est indispensable : un ``groupby`` ou un tri glissé dans la
    chaîne d'appel réordonne les lignes sans rien dire, et chaque point se
    trouverait alors comparé au voisin. Le contrôle sortirait rouge sur un
    modèle juste.
    """
    for colonne in demande.columns:
        if colonne not in rendu.columns:
            continue
        attendu = pd.to_numeric(demande[colonne], errors="coerce").to_numpy(dtype=float)
        obtenu = pd.to_numeric(rendu[colonne], errors="coerce").to_numpy(dtype=float)
        proche = np.isclose(obtenu, attendu, rtol=RTOL_ALIGNEMENT, atol=1e-12, equal_nan=True)
        if bool(np.all(proche)):
            continue
        premiere = int(np.flatnonzero(~proche)[0])
        raise ErreurModele(
            f"table « {spec.nom} » : le modèle a rendu « {colonne} » = {obtenu[premiere]:g} "
            f"à la ligne {premiere}, là où on lui avait passé {attendu[premiere]:g}. "
            "Le modèle doit rendre ses lignes dans l'ordre reçu — un tri ou un regroupement "
            "dans la chaîne d'appel comparerait chaque point à son voisin."
        )
