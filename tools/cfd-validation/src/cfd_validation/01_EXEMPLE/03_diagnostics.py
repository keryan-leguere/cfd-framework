"""3 — Les motifs de panne, un par un.

Le paquet livre un générateur de pannes (`cfd_validation.wrap.factice`) qui
sait reproduire à volonté chacune des erreurs de lecture qu'un code à tables
commet réellement. Ce script les rejoue toutes et montre que le diagnostic
nomme la bonne — c'est la démonstration que les détecteurs font ce qu'ils
annoncent, sur des cas et non sur un raisonnement.

    python3 03_diagnostics.py
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from cfd_validation import charger_fichier, charger_tables, valider_tables
from cfd_validation.wrap.factice import BUGS, ModeleFactice, module_factice

console = Console()
module = module_factice()
specs = charger_fichier("TABLES.yaml")

recap = Table(title="Une panne, un motif", title_style="cyan", header_style="cyan")
recap.add_column("panne injectée")
recap.add_column("motif attendu")
recap.add_column("motif trouvé en tête")
recap.add_column("points fautifs", justify="right")
recap.add_column("")

for panne, attendu in BUGS.items():
    rapport = valider_tables(module, specs, modele=ModeleFactice(module, bug=panne))
    grandeur = rapport["CN"].grandeur("CN")
    trouve = grandeur.motifs[0].nom if grandeur.motifs else "—"
    juste = trouve == attendu
    recap.add_row(
        panne,
        attendu,
        f"[{'green' if juste else 'red'}]{trouve}[/]",
        str(grandeur.ecart.n_fautifs),
        "[green]✓[/]" if juste else "[red]✗[/]",
    )

# La huitième panne n'est pas dans le modèle mais dans la **déclaration** :
# oublier « lignes » fait comparer le modèle aux lignes de remplissage.
sans_lignes = charger_tables(
    {
        "CN": {
            "bloc": "tab_cn",
            "colonnes": ["mach", "alpha", "delta", "CN"],
            "qoi": ["CN"],
        }
    }
)
rapport = valider_tables(module, sans_lignes, modele=ModeleFactice(module))
grandeur = rapport["CN"].grandeur("CN")
trouve = grandeur.motifs[0].nom if grandeur.motifs else "—"
juste = trouve == "queue_non_renseignee"
recap.add_row(
    "« lignes » omis",
    "queue_non_renseignee",
    f"[{'green' if juste else 'red'}]{trouve}[/]",
    str(grandeur.ecart.n_fautifs),
    "[green]✓[/]" if juste else "[red]✗[/]",
)

console.print(recap)

# Et le rapport complet d'une de ces pannes, pour voir à quoi il ressemble.
console.print("\n[cyan]Le rapport complet, sur la panne « ecretage » :[/]\n")
from cfd_validation.report.console import rapport_tables  # noqa: E402

console.print(
    rapport_tables(valider_tables(module, specs, modele=ModeleFactice(module, bug="ecretage")))
)
