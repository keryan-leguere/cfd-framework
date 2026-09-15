"""cfd-validation — valider un code Fortran/C depuis Python.

Envelopper le code compilé, écrire des contrôles, les exécuter, en sortir un
rapport. Le premier contrôle livré répond à une question précise :

    **mon modèle relit-il correctement ses propres tables ?**

Une table interpolée vaut *exactement* la valeur tabulée à chacun de ses
nœuds. Évaluer le modèle sur les nœuds de sa propre table et retrouver autre
chose signifie donc, sans discussion possible, qu'il ne lit pas la table qu'on
croit — axes transposés, indice décalé, facteur d'unité, axe ignoré, indice
saturé au bord, queue de tableau jamais renseignée. Aucune de ces pannes ne se
voit sur une courbe : une courbe fausse est lisse elle aussi.

En cinq lignes ::

    from cfd_validation import valider_tables, imprimer_rapport

    rapport = valider_tables(mon_module, TABLES, modele=mon_modele)
    raise SystemExit(imprimer_rapport(rapport))

Le contrôle n'exige du module qu'un accès par attribut
``module.<bloc>.<tableau>`` — ce que f2py produit pour un COMMON block, et
qu'un objet Python quelconque peut imiter. C'est pourquoi tout le paquet se
teste sans compilateur.
"""

from __future__ import annotations

__version__ = "1.0.0"

# --- Déclaration des tables -------------------------------------------------
from cfd_validation.data.spec import (
    CLES_ADMISES,
    ErreurSpec,
    SpecTable,
    charger_fichier,
    charger_tables,
)

# --- Entrées et sorties du modèle -------------------------------------------
from cfd_validation.data.entrees import (
    ErreurModele,
    cadre_modele,
    cadre_table,
    entrees,
    verifier_sortie,
)

# --- Enveloppe du code compilé ----------------------------------------------
from cfd_validation.wrap.bloc import ErreurBloc, blocs_exposes, lire_table, lire_tableau
from cfd_validation.wrap.construire import ErreurConstruction, charger_module, construire
from cfd_validation.wrap.f2py_module import ErreurResolution, resoudre_module, resoudre_objet
from cfd_validation.wrap.toolchain import Toolchain, inspecter_toolchain

# --- Comparaison et motifs de panne -----------------------------------------
from cfd_validation.core.ecart import ATOL_DEFAUT, RTOL_DEFAUT, Ecart, comparer
from cfd_validation.core.motifs import Contexte, Motif, detecter

# --- Contrôles et suite -----------------------------------------------------
from cfd_validation.engine.controle import Controle, Verdict
from cfd_validation.engine.diagnostic import diagnostiquer
from cfd_validation.engine.suite import Rapport, Suite
from cfd_validation.engine.tables import (
    ControleTables,
    RapportTables,
    ResultatQOI,
    ResultatTable,
    valider_tables,
)

# --- Rapport et figures -----------------------------------------------------
from cfd_validation.paths import EXEMPLE_DIR, FORTRAN_DIR
from cfd_validation.report.console import imprimer_rapport, panneau_erreur, rapport_tables

__all__ = [
    "__version__",
    # déclaration
    "SpecTable",
    "charger_tables",
    "charger_fichier",
    "CLES_ADMISES",
    "ErreurSpec",
    # entrées / sorties du modèle
    "entrees",
    "cadre_table",
    "cadre_modele",
    "verifier_sortie",
    "ErreurModele",
    # enveloppe
    "lire_table",
    "lire_tableau",
    "blocs_exposes",
    "ErreurBloc",
    "construire",
    "charger_module",
    "ErreurConstruction",
    "resoudre_module",
    "resoudre_objet",
    "ErreurResolution",
    "inspecter_toolchain",
    "Toolchain",
    # comparaison
    "comparer",
    "Ecart",
    "RTOL_DEFAUT",
    "ATOL_DEFAUT",
    "detecter",
    "Contexte",
    "Motif",
    # contrôles
    "valider_tables",
    "ControleTables",
    "RapportTables",
    "ResultatTable",
    "ResultatQOI",
    "diagnostiquer",
    "Suite",
    "Rapport",
    "Verdict",
    "Controle",
    # rapport
    "imprimer_rapport",
    "rapport_tables",
    "panneau_erreur",
    "EXEMPLE_DIR",
    "FORTRAN_DIR",
]
