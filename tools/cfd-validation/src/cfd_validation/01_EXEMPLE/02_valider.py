"""2 — Le contrôle lui-même, sur un modèle juste.

Trois lignes utiles : lire la déclaration, appeler `valider_tables`, imprimer.
Le reste de ce fichier est du commentaire.

    python3 02_valider.py        # sort en 0

Le contrôle évalue le modèle **sur les nœuds de sa propre table**. Une
interpolation y vaut exactement la valeur tabulée : tout écart est donc une
erreur de lecture, pas une imprécision.
"""

from __future__ import annotations

import sys

import mon_modele
from cfd_validation import charger_fichier, imprimer_rapport, valider_tables

import aero_factice

rapport = valider_tables(
    aero_factice,  # le module enveloppé
    charger_fichier("TABLES.yaml"),  # ce qu'il contient
    modele=mon_modele.appeler,  # comment l'appeler
)

# `imprimer_rapport` rend le code de retour : 0 conforme, 2 des écarts.
sys.exit(imprimer_rapport(rapport))
