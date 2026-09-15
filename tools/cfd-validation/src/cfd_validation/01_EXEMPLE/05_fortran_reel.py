"""5 — Le même contrôle, sur du Fortran réellement compilé.

Compile `MODELE_FORTRAN/aero.f` par f2py, charge le module produit, et lui fait
subir exactement le contrôle des scripts précédents. Le Fortran porte un
interrupteur `regler_bug(mode)` qui injecte une vraie erreur de lecture dans le
code compilé — pas une simulation en Python.

    python3 05_fortran_reel.py

Demande gfortran **et** le moteur de compilation de f2py. `cfd-validation
toolchain` dit ce qui manque et quoi taper. Sans cela, le script le dit et
s'arrête proprement : le reste de l'exemple tourne sans compilateur.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.table import Table

from cfd_validation import charger_fichier, inspecter_toolchain, valider_tables
from cfd_validation.report.console import panneau_toolchain
from cfd_validation.wrap.construire import ErreurConstruction, charger_module, construire

console = Console()

chaine = inspecter_toolchain()
console.print(panneau_toolchain(chaine))
if not chaine.pret:
    console.print(
        "[yellow]Compilation impossible ici ; le reste de l'exemple n'en a pas besoin.[/]"
    )
    sys.exit(0)

source = Path(__file__).parent / "MODELE_FORTRAN" / "aero.f"
build = Path("SORTIE") / "BUILD"
build.mkdir(parents=True, exist_ok=True)

try:
    produit = construire(source, nom_module="aero", destination=build)
except ErreurConstruction as erreur:
    console.print(f"[red]{erreur}[/]")
    sys.exit(1)

console.print(f"[green]compilé :[/] {produit}")

aero = charger_module(produit)
aero.init_tables()

specs = charger_fichier(Path(__file__).parent / "TABLES.yaml")


def appeler(entrees: pd.DataFrame) -> pd.DataFrame:
    """Le modèle, appelé par ses vraies routines Fortran."""
    rendu = entrees.copy()
    if "delta" in entrees.columns:
        rendu["CN"] = aero.eval_cn(
            entrees["mach"].to_numpy(),
            entrees["alpha"].to_numpy(),
            entrees["delta"].to_numpy(),
        )
    else:
        rendu["CA"] = aero.eval_ca(entrees["mach"].to_numpy(), entrees["alpha"].to_numpy())
    return rendu


#: Les pannes que le Fortran sait injecter, et le motif attendu.
PANNES = {
    0: ("lecture juste", None),
    1: ("degrés lus comme des radians", "facteur_echelle"),
    2: ("incidence et braquage permutés", "axes_transposes"),
    3: ("indice de Mach saturé aux bords", "ecretage"),
}

recap = Table(
    title="Fortran compilé — une panne, un motif", title_style="cyan", header_style="cyan"
)
recap.add_column("bug_mode", justify="right")
recap.add_column("panne dans le Fortran")
recap.add_column("motif trouvé")
recap.add_column("fautifs", justify="right")

for mode, (libelle, attendu) in PANNES.items():
    aero.regler_bug(mode)
    rapport = valider_tables(aero, specs, modele=appeler)
    grandeur = rapport["CN"].grandeur("CN")
    trouve = grandeur.motifs[0].nom if grandeur.motifs else "—"
    juste = trouve == (attendu or "—")
    recap.add_row(
        str(mode),
        libelle,
        f"[{'green' if juste else 'red'}]{trouve}[/]",
        str(grandeur.ecart.n_fautifs),
    )

console.print(recap)
aero.regler_bug(0)
