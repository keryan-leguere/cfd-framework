"""1 — Lire une table dans un COMMON block, et regarder ce qu'on a lu.

Avant tout contrôle : le paquet voit-il la bonne table ? C'est la première
chose à vérifier devant un module inconnu, et la première cause d'échec —
un nom de bloc approximatif, une orientation inversée, une queue de tableau
jamais renseignée.

    python3 01_lire_table.py
"""

from __future__ import annotations

from dataclasses import replace

from rich.console import Console

import aero_factice
from cfd_validation import blocs_exposes, charger_fichier, lire_table
from cfd_validation.report.console import tableau_blocs

console = Console()

# 1. Ce que le module expose réellement. Devant un vrai module f2py, c'est ici
#    qu'on découvre les noms — et f2py les met tous en minuscules.
console.print(tableau_blocs(blocs_exposes(aero_factice)))

# 2. La déclaration, validée. Une clé mal orthographiée serait refusée ici, en
#    nommant les clés admises, plutôt que de laisser passer une table fausse.
specs = charger_fichier("TABLES.yaml")
console.print(f"\n[cyan]{len(specs)} table(s) déclarée(s) :[/] {', '.join(specs)}\n")

# 3. La table elle-même, en cadre de données.
for nom, spec in specs.items():
    table = lire_table(aero_factice, spec)
    console.print(f"[cyan]{nom}[/] — {len(table)} nœuds, colonnes {list(table.columns)}")
    console.print(table.head(4).to_string(index=False))
    console.print(
        f"[dim]variables indépendantes : {list(spec.independantes)} — "
        f"grandeurs contrôlées : {list(spec.qoi)}[/]\n"
    )

# 4. La preuve que « lignes » sert à quelque chose : sans lui, la table
#    emporte les 26 lignes de remplissage que le Fortran n'a jamais écrites.
avec = specs["CN"]
sans = replace(avec, lignes=None)
brut = lire_table(aero_factice, sans)
console.print(
    f"[yellow]Sans la clé « lignes », la table CN ferait {len(brut)} lignes "
    f"au lieu de {len(lire_table(aero_factice, avec))}[/] — "
    "les dernières portent la valeur de remplissage :"
)
console.print(brut.tail(2).to_string(index=False))
