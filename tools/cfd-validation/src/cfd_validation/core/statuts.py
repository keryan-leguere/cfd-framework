"""Statuts d'une comparaison, du plus favorable au plus grave.

Un statut est un entier : l'ordre *est* la gravité, si bien que le statut d'une
ligne est le maximum de ceux de ses sorties, et celui d'une étude le maximum de
ceux de ses lignes. Les trois premiers qualifient une **valeur** ; les suivants
une **ligne** entière, qu'on n'a pas pu (ou pas dû) comparer sortie par sortie.
"""

from __future__ import annotations

__all__ = [
    "ABSENTE",
    "ECART",
    "ENTREES_DIVERGENTES",
    "EN_TROP",
    "IDENTIQUE",
    "LIBELLES",
    "LIBELLES_COURTS",
    "NOMS",
    "NON_FINI",
    "TOLERE",
    "est_echec",
]

#: Bit pour bit égal (deux NaN, ou deux infinis de même signe, comptent comme égaux).
IDENTIQUE = 0
#: Différent, mais dans la tolérance déclarée.
TOLERE = 1
#: Hors tolérance.
ECART = 2
#: Fini d'un côté, NaN ou infini de l'autre (ou deux infinis opposés).
NON_FINI = 3
#: Ligne appariée par position dont les entrées diffèrent : comparer ses sorties n'aurait pas de sens.
ENTREES_DIVERGENTES = 4
#: Ligne de la référence sans correspondant dans le test (cas non calculé, plantage…).
ABSENTE = 5
#: Ligne du test sans correspondant dans la référence.
EN_TROP = 6

#: Identifiant stable (fichiers CSV/JSON).
NOMS: dict[int, str] = {
    IDENTIQUE: "IDENTIQUE",
    TOLERE: "TOLERE",
    ECART: "ECART",
    NON_FINI: "NON_FINI",
    ENTREES_DIVERGENTES: "ENTREES_DIVERGENTES",
    ABSENTE: "ABSENTE",
    EN_TROP: "EN_TROP",
}

#: Libellé lisible (terminal, journal, figures).
LIBELLES: dict[int, str] = {
    IDENTIQUE: "identique",
    TOLERE: "dans la tolérance",
    ECART: "hors tolérance",
    NON_FINI: "non fini divergent",
    ENTREES_DIVERGENTES: "entrées divergentes",
    ABSENTE: "absente du test",
    EN_TROP: "en trop dans le test",
}


#: Libellé de colonne étroite (table ligne à ligne au terminal).
LIBELLES_COURTS: dict[int, str] = {
    IDENTIQUE: "identique",
    TOLERE: "tolérée",
    ECART: "hors tol.",
    NON_FINI: "non fini",
    ENTREES_DIVERGENTES: "divergente",
    ABSENTE: "absente",
    EN_TROP: "en trop",
}


def est_echec(statut: int) -> bool:
    """Vrai pour tout statut qui rend l'étude non conforme."""
    return statut >= ECART
