"""Tous les exemples, de bout en bout : un cas par trajectoire, symétrie et jeu de variables.

Pour chaque fichier de remplissage (la fusée, puis ``CAS/``) :

1. ``cfd-doe remplir`` : rapport, ``doe.csv`` du plan retenu, figures (domaine,
   chaque plan, comparaisons) dans ``SORTIE/<cas>/DOE/`` ;
2. ``reconstruire_tables.py`` : calculs factices, une table par coefficient
   pour le plan retenu, erreurs de chaque méthode, figures de précision et de
   coupes, dans ``SORTIE/<cas>/RECONSTRUCTION/`` ;

puis un bilan d'une ligne par cas. ::

    python executer_exemples.py                       # tout (quelques minutes)
    python executer_exemples.py --rapide              # krigeage multi-sorties, sans figures
    python executer_exemples.py --cas MISSILE OBUS    # un sous-ensemble (nom contenu)

=========================  ===========================  ==================  =====================
cas                        trajectoire                  géométrie           ce qu'il montre
=========================  ===========================  ==================  =====================
REMPLISSAGE_FUSEE          6DOF, moteur continu         cruciforme (D2)     tous les plans
MISSILE_3DOF               3DOF tangage, coiffe         double symétrie     2 variables, discret
AVION_5DOF                 5DOF, volets discrets        plan vertical       α non symétrique
OBUS_3DOF                  3DOF masse ponctuelle, spin  révolution          cartésien forcé
DRONE_4DOF                 4DOF, hélice continue        quelconque          aucune symétrie
FUSEE_3AILETTES            6DOF                         3 ailettes          N impair : miroir V
=========================  ===========================  ==================  =====================
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from rich import box
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reconstruire_tables import _pct
from reconstruire_tables import principal as reconstruire

from cfd_doe.cli.main import main as cfd_doe

ICI = Path(__file__).resolve().parent
console = Console(highlight=False)


def fichiers_de_remplissage() -> list[Path]:
    """La fusée, puis les cas de ``CAS/``."""
    return [ICI / "REMPLISSAGE_FUSEE.yaml", *sorted((ICI / "CAS").glob("REMPLISSAGE_*.yaml"))]


def nom_du_cas(chemin: Path) -> str:
    return chemin.stem.removeprefix("REMPLISSAGE_")


def executer(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sortie", default="EXEMPLES", help="dossier de sortie")
    parser.add_argument("--cas", nargs="+", help="cas à traiter (une partie du nom suffit)")
    parser.add_argument(
        "--rapide", action="store_true", help="sans figures, krigeage multi-sorties"
    )
    args = parser.parse_args(argv)

    cas = fichiers_de_remplissage()
    if args.cas:
        cas = [f for f in cas if any(c.upper() in f.stem.upper() for c in args.cas)]
    sortie = Path(args.sortie)

    bilan = Table(title="Bilan des exemples", box=box.SIMPLE_HEAD, title_justify="left")
    for titre in ("cas", "trajectoire", "groupe", "plans", "retenu", "calculs", "RMS"):
        bilan.add_column(
            titre,
            no_wrap=True,
            justify="right" if titre in ("plans", "calculs", "RMS") else "left",
            max_width=16 if titre == "cas" else None,
            min_width={"retenu": 9, "RMS": 9}.get(titre),
            overflow="ellipsis",
        )
    echecs = 0
    for chemin in cas:
        nom = nom_du_cas(chemin)
        dossier = sortie / nom
        console.rule(f"[bold]{nom}")
        debut = time.perf_counter()
        # 1. cfd-doe remplir (rapport muet ici : il est dans le fichier journal)
        journal = io.StringIO()
        options = ["remplir", str(chemin), "--sortie", str(dossier / "DOE")]
        if args.rapide:
            options.append("--sans-figures")
        with contextlib.redirect_stdout(journal):
            code = cfd_doe(options)
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "remplir.txt").write_text(journal.getvalue(), encoding="utf-8")
        if code != 0:
            console.print(
                f"[red]cfd-doe remplir a échoué ({code})[/] : voir {dossier / 'remplir.txt'}"
            )
            echecs += 1
            continue
        console.print(f"[dim]remplir : {dossier / 'DOE'} (rapport dans remplir.txt)[/]")
        # 2. reconstruction
        options = [str(chemin), "--sortie", str(dossier / "RECONSTRUCTION"), "--lots", "2"]
        if args.rapide:
            options += ["--rapide", "--sans-figures"]
        bilans = reconstruire(options)
        nom_retenu = _retenu(chemin)
        retenu = next(b for b in bilans if b.plan.nom == nom_retenu)
        etude = _etude(chemin)
        bilan.add_row(
            nom,
            etude[0],
            etude[1],
            str(len(bilans)),
            nom_retenu,
            f"{retenu.calculs:,}".replace(",", " "),
            _pct(retenu.pire),
        )
        console.print(f"[dim]{nom} : {time.perf_counter() - debut:.0f} s[/]")
    console.print(bilan)
    console.print(f"[dim]sorties : {sortie.resolve()}[/]")
    return 1 if echecs else 0


def _retenu(chemin: Path) -> str:
    from cfd_doe.data.remplissage import charger_remplissage

    return charger_remplissage(chemin).retenu


def _etude(chemin: Path) -> tuple[str, str]:
    from cfd_doe.data.remplissage import charger_remplissage
    from cfd_doe.engine.reduction import reduire

    remplissage = charger_remplissage(chemin)
    reduction = reduire(remplissage.etude.avec(repere="cartesien"))
    trajectoire = remplissage.etude.trajectoire.nom.replace("_MASSE_PONCTUELLE", " MP")
    return trajectoire, str(reduction.groupe)


if __name__ == "__main__":
    sys.exit(executer())
