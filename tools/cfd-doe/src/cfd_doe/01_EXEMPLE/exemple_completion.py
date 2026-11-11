"""Exemple : compléter par symétrie une table de résultats issue d'un plan cfd-doe.

Tout est factice et prêt à l'emploi :

1. le plan : ``ETUDE_FUSEE.yaml`` réduit par cfd-doe et exporté (``SD_*.yaml``) ;
2. la discrétisation : une grille régulière sur le **domaine d'entrée** (φa sur
   le tour complet, α de −20° à 20°…) ;
3. « la CFD » : on ne garde que les nœuds qui tombent dans un sous-domaine —
   c'est ce qu'un plan cfd-doe fait calculer — et on les évalue avec un modèle
   aéro factice qui **respecte les symétries de l'engin** ;
4. :func:`completer_table` reconstruit la table carrée ;
5. validation : chaque ligne déduite est comparée au modèle factice au même
   nœud. Une ligne déduite par symétrie doit coïncider à la précision machine ;
   une ligne interpolée sur l'axe αt = 0 porte l'erreur de l'interpolation.

::

    python exemple_completion.py                 # polaire : secteur φa ∈ [0 ; 45°]
    python exemple_completion.py --cartesien     # cartésien : α ≥ 0, β ≥ 0
    python exemple_completion.py --cartesien --beta-positif   # lecteur β ≥ 0, α complet
    python exemple_completion.py --csv SORTIE    # écrire les tables (calculée, complète)

Depuis Python : ``table_factice("polaire")`` rend le DataFrame d'entrée et le
plan, à passer tels quels à ``completer_table``.
"""

from __future__ import annotations

import argparse
import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from completer_table import Plan, completer_table, lire_plan

ICI = Path(__file__).resolve().parent

#: Discrétisation factice du domaine d'entrée (degrés), par repère.
GRILLES: dict[str, dict[str, list[float]]] = {
    "polaire": {
        "ALPHAT": [0.0, 5.0, 10.0, 15.0, 20.0],
        "PHIA": [float(x) for x in range(0, 360, 15)],
        "DMB": [-20.0, -10.0, 0.0, 10.0, 20.0],
        "DNB": [-20.0, -10.0, 0.0, 10.0, 20.0],
        "DL": [-10.0, 0.0, 10.0],
    },
    "cartesien": {
        "ALPHA": [-20.0, -10.0, 0.0, 10.0, 20.0],
        "BETA": [-5.0, -2.5, 0.0, 2.5, 5.0],
        "DM": [-20.0, -10.0, 0.0, 10.0, 20.0],
        "DN": [-20.0, -10.0, 0.0, 10.0, 20.0],
        "DL": [-10.0, 0.0, 10.0],
    },
}

#: Conditions de vol : une table indépendante par Mach.
MACHS = (0.8, 1.5)

#: Variable du plan → colonne, et coefficient → colonne : les noms « maison »
#: de l'exemple, pour montrer l'adaptation.
COLONNES = {
    "polaire": {"alphat": "ALPHAT", "phia": "PHIA", "DMB": "DMB", "DNB": "DNB", "DL": "DL"},
    "cartesien": {"alpha": "ALPHA", "beta": "BETA", "DM": "DM", "DN": "DN", "DL": "DL"},
}
COEFFICIENTS = {
    "polaire": {"CA": "CAB", "CN": "CNB", "CY": "CYB", "Cl": "ClB", "Cm": "CmB", "Cn": "CnB"},
    "cartesien": {"CA": "CA", "CN": "CN", "CY": "CY", "Cl": "Cl", "Cm": "Cm", "Cn": "Cn"},
}


# ---------------------------------------------------------------------------
# Modèles aéro factices, symétriques par construction
# ---------------------------------------------------------------------------


def modele_polaire(df: pd.DataFrame) -> pd.DataFrame:
    """Cruciforme en repère mixte : invariant par φa → φa + 90°, et par les miroirs.

    φa n'y entre que par cos 4φa (pair) et sin 4φa (impair) ; CY, Cl, Cn sont
    impairs en (δnB, δl, sin 4φa) ; à αt = 0, (CN, CY) et (Cm, Cn) suivent
    (δmB, δnB) avec un même gain : le modèle ne dépend pas du φa conventionnel.
    """
    at, phi = df["ALPHAT"].to_numpy(), np.radians(df["PHIA"].to_numpy())
    dm, dn, dl = df["DMB"].to_numpy(), df["DNB"].to_numpy(), df["DL"].to_numpy()
    k = 1.0 + 0.3 * (df["MACH"].to_numpy() - 0.8)
    c4, s4 = np.cos(4 * phi), np.sin(4 * phi)
    return pd.DataFrame(
        {
            "CAB": 0.30 * k + 1e-3 * at**2 + 4e-4 * (dm**2 + dn**2) + 2e-4 * dl**2,
            "CNB": 0.12 * k * at * (1 + 0.05 * c4) + 0.020 * dm + 1e-3 * at * dm,
            "CYB": 0.010 * at * s4 + 0.020 * dn + 1e-3 * at * dn,
            "ClB": 1e-3 * at * s4 + 0.020 * dl + 5e-4 * at * dn,
            "CmB": -0.050 * k * at * (1 + 0.04 * c4) - 0.030 * dm,
            "CnB": -2e-3 * at * s4 - 0.030 * dn,
        },
        index=df.index,
    )


def modele_cartesien(df: pd.DataFrame) -> pd.DataFrame:
    """Double symétrie en repère engin : CN, Cm impairs en α ; CY, Cn impairs en β ; Cl, les deux."""
    a, b = df["ALPHA"].to_numpy(), df["BETA"].to_numpy()
    dm, dn, dl = df["DM"].to_numpy(), df["DN"].to_numpy(), df["DL"].to_numpy()
    k = 1.0 + 0.3 * (df["MACH"].to_numpy() - 0.8)
    return pd.DataFrame(
        {
            "CA": 0.30 * k + 1e-3 * (a**2 + b**2) + 4e-4 * (dm**2 + dn**2) + 2e-4 * dl**2,
            "CN": 0.12 * k * a + 0.020 * dm + 4e-4 * a * b**2,
            "CY": -0.09 * b + 0.015 * dn,
            "Cl": 0.020 * dl + 6e-4 * a * b,
            "Cm": -0.050 * k * a - 0.030 * dm,
            "Cn": 0.040 * b - 0.030 * dn,
        },
        index=df.index,
    )


MODELES = {"polaire": modele_polaire, "cartesien": modele_cartesien}


# ---------------------------------------------------------------------------
# Le plan et la table « calculée »
# ---------------------------------------------------------------------------


def exporter_plan(repere: str, destination: Path) -> Path:
    """Réduit ``ETUDE_FUSEE.yaml`` avec cfd-doe et exporte le plan (``cfd-doe domaine --export``)."""
    from cfd_doe.data.etude import charger_etude
    from cfd_doe.engine.reduction import reduire, vers_dict

    etude = charger_etude(ICI / "ETUDE_FUSEE.yaml").avec(repere=repere)
    donnees = vers_dict(reduire(etude))
    destination.write_text(
        yaml.safe_dump(donnees, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return destination


def table_factice(repere: str = "polaire", plan: Path | None = None) -> tuple[pd.DataFrame, Plan]:
    """La table d'entrée : la grille factice filtrée par le plan, évaluée par le modèle factice."""
    if plan is None:
        plan = exporter_plan(repere, Path.cwd() / f"SD_FUSEE_{repere.upper()}.yaml")
    lu = lire_plan(plan)
    colonnes = COLONNES[repere]
    grille = GRILLES[repere]
    noms = list(grille)
    vers_plan = {col: v for v, col in colonnes.items()}
    lignes = []
    for mach in MACHS:
        for valeurs in product(*grille.values()):
            point = {vers_plan[c]: x for c, x in zip(noms, valeurs)}
            if lu.dans_le_plan(point):
                lignes.append({"MACH": mach, **dict(zip(noms, valeurs))})
    df = pd.DataFrame(lignes)
    df = pd.concat([df, MODELES[repere](df)], axis=1)
    df["RESIDU"] = 1e-6  # une colonne « autre » : recopiée telle quelle
    return df, lu


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def apercu(df: pd.DataFrame, n: int = 4) -> Table:
    """Les premières lignes d'une table, en colonnes alignées."""
    table = Table(box=box.SIMPLE_HEAD, header_style="cyan", pad_edge=False)
    for col in df.columns:
        table.add_column(col, justify="right")
    for _, ligne in df.head(n).iterrows():
        table.add_row(*(f"{x + 0.0:.4g}" if isinstance(x, float) else str(x) for x in ligne))
    return table


def _e(x: float) -> str:
    return "0" if x == 0.0 else f"{x:.1e}".replace("-", "−").replace(".", ",")


def valider(complet: pd.DataFrame, repere: str) -> Table:
    """Écart de chaque ligne au modèle factice, par origine."""
    roles = list(COEFFICIENTS[repere].values())
    connu = complet.dropna(subset=roles)
    ecart = (connu[roles] - MODELES[repere](connu)[roles]).abs().max(axis=1)
    categorie = connu["origine"].str.split(" : ").str[0]
    categorie = categorie.where(~connu["origine"].str.startswith("trou"), connu["origine"])

    table = Table(
        title=Text("Validation contre le modèle factice", style="cyan"),
        title_justify="left",
        box=box.SIMPLE_HEAD,
        header_style="cyan",
        pad_edge=False,
    )
    table.add_column("origine")
    table.add_column("lignes", justify="right")
    table.add_column("écart max |C − modèle|", justify="right")
    if categorie.str.contains("interpolé").any():
        table.caption = Text(
            "CA est quadratique en braquages dans le modèle factice : l'écart des lignes "
            "interpolées est celui de l'interpolation",
            style="dim",
        )
        table.caption_justify = "left"
    for nom, groupe in ecart.groupby(categorie, sort=False):
        maxi = float(groupe.max())
        style = "green" if maxi < 1e-12 else "yellow"
        table.add_row(str(nom), str(len(groupe)), Text(_e(maxi), style=style))
    return table


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--cartesien", action="store_true", help="plan en (α, β) au lieu de (αt, φa)"
    )
    parser.add_argument(
        "--beta-positif",
        action="store_true",
        help="cartésien : table cible β ≥ 0 mais α complet (domaine={'alpha': (-20, 20)})",
    )
    parser.add_argument("--plan", type=Path, help="un plan déjà exporté (sinon : ETUDE_FUSEE.yaml)")
    parser.add_argument("--csv", type=Path, metavar="DOSSIER", help="écrire les tables en CSV")
    args = parser.parse_args(argv)
    repere = "cartesien" if args.cartesien else "polaire"
    console = Console(highlight=False)

    df, plan = table_factice(repere, args.plan)
    console.print(
        Text.assemble(
            ("Table « calculée » : ", "dim"),
            (f"{len(df)} lignes", "green"),
            (f" ({', '.join(df.columns)})", "dim"),
        )
    )
    console.print(apercu(df))
    console.print()

    complet = completer_table(
        df,
        plan,
        cles=["MACH"],
        domaine={"alpha": (-20.0, 20.0)} if args.beta_positif and args.cartesien else None,
        colonnes=COLONNES[repere],
        coefficients=COEFFICIENTS[repere],
        console=console,
    )
    console.print()
    console.print(valider(complet, repere))

    if args.csv is not None:
        args.csv.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.csv / f"TABLE_CALCULEE_{repere.upper()}.csv", index=False)
        complet.to_csv(args.csv / f"TABLE_COMPLETE_{repere.upper()}.csv", index=False)
        console.print(
            f"[green]écrit :[/] {args.csv}/TABLE_{{CALCULEE,COMPLETE}}_{repere.upper()}.csv"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
