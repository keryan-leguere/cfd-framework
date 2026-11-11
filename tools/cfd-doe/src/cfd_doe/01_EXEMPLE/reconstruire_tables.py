"""De bout en bout : DOE → « CFD » factice → une table par coefficient, pour chaque méthode.

Ce que ferait une étude réelle, avec un modèle aéro factice à la place du solveur :

1. ``cfd-doe remplir`` construit les plans (ici :func:`cfd_doe.engine.remplissage.remplir`) ;
2. **la CFD** : chaque point du plan est « calculé » par un modèle analytique
   qui respecte exactement les symétries de l'engin (il est moyenné sur le
   groupe de l'étude). On écrit le DOE complété de ses résultats,
   ``RESULTATS/<plan>.csv`` — le fichier que votre post-traitement produirait —
   puis on le **relit** (:func:`lire_mesures`), comme vous le feriez ;
3. **la table** : :func:`reconstruire` passe des calculs à la grille carrée que
   lit le simulateur, selon la méthode du plan (lecture + symétries, somme
   d'incréments, polynôme, krigeage, co-krigeage), puis :func:`ecrire_tables`
   écrit ``TABLES/<plan>/<COEF>.csv`` : **une table par coefficient** ;
4. **la vérification**, celle de la démarche de chaque plan : écart aux points
   de contrôle (décomposition) ou de test (métamodèles) ; et, parce qu'ici la
   vérité est connue, l'erreur sur toute la grille ;
5. pour le plan **adaptatif**, les lots d'enrichissement sont simulés
   (:func:`lot_suivant`) : chaque lot est écrit (``LOTS/``), « calculé », et
   la table recalculée, jusqu'à ``--lots`` lots.

::

    python reconstruire_tables.py                                   # la fusée, tous les plans
    python reconstruire_tables.py CAS/REMPLISSAGE_MISSILE_3DOF.yaml
    python reconstruire_tables.py --plans ordre_1 ordre_2 lhs --tables tous
    python reconstruire_tables.py --rapide                          # krigeage multi-sorties
    python reconstruire_tables.py --sortie /tmp/RECONSTRUCTION --sans-figures

Le repère est forcé en cartésien (la reconstruction ne traite pas le polaire).
Pour brancher vos vrais résultats : sauter l'étape 2, et donner à
:func:`lire_mesures` votre ``doe.csv`` complété d'une colonne par coefficient.
"""

from __future__ import annotations

import argparse
import dataclasses
import math
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
from rich import box
from rich.console import Console
from rich.table import Table

from cfd_doe.data.remplissage import Remplissage, charger_remplissage
from cfd_doe.engine.reconstruction import (
    Mesures,
    Tables,
    ecrire_mesures,
    ecrire_tables,
    grille_carree,
    lire_mesures,
    lot_suivant,
    reconstruire,
)
from cfd_doe.engine.remplissage import Contexte, PlanDOE, PointDOE, ecrire_csv, remplir

ICI = Path(__file__).resolve().parent
console = Console(highlight=False)


# ---------------------------------------------------------------------------
# 1. Le modèle aéro factice
# ---------------------------------------------------------------------------


def modele_brut(valeurs: Mapping[str, np.ndarray], contexte: Contexte) -> dict[str, np.ndarray]:
    """Six coefficients plausibles, en repère engin, avant symétrisation.

    Non-linéarités et interactions volontaires, pour que les méthodes se
    distinguent : portance tourbillonnaire en α|α|, efficacité de gouverne qui
    sature (tanh), couplages δm × δn², β² × δn, paramètres × gouverne, bosse
    transsonique en Mach. Les paramètres de l'étude, quels qu'ils soient,
    entrent par leur valeur réduite dans [0, 1].
    """
    n = len(next(iter(valeurs.values())))

    def v(nom: str) -> np.ndarray:
        return np.asarray(valeurs.get(nom, np.zeros(n)), dtype=float)

    a, b, dm, dn, dl = v("alpha"), v("beta"), v("DM"), v("DN"), v("DL")
    mach = v("mach") if "mach" in valeurs else np.full(n, 0.8)
    k = 1.0 + 0.4 * np.exp(-(((mach - 1.0) / 0.15) ** 2))
    p = np.zeros(n)
    for param in contexte.parametres:
        plage = param.plage
        p += (v(param.nom) - plage.bas) / (plage.largeur or 1.0)
    p /= max(1, len(contexte.parametres))
    gm, gn = np.tanh(dm / 20.0), np.tanh(dn / 20.0)
    return {
        "CA": 0.30 * k + 1e-3 * (a**2 + b**2) + 4e-4 * (dm**2 + dn**2) + 2e-4 * dl**2 - 0.08 * p,
        "CN": k * (0.10 * a + 0.0025 * a * np.abs(a))
        + 0.40 * gm
        + 8e-4 * a * dm
        + 0.10 * p * a / 10
        + 2.5e-5 * dm * dn**2
        + 0.004,  # dissymétrie : ne survit que sans miroir H
        "CY": -0.09 * b + 0.30 * gn + 3e-4 * b**2 * dn,
        "Cl": 0.02 * dl + 6e-4 * a * b - 0.01 * p * dl / 10,
        "Cm": -0.05 * k * a - 0.60 * gm * (1 - 0.25 * p) - 4e-5 * dm * dn**2,
        "Cn": 0.04 * b - 0.60 * gn - 6e-4 * b**2 * dn,
    }


def verite(contexte: Contexte, valeurs: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Le modèle moyenné sur le groupe de symétrie de l'étude : exactement symétrique.

    C(x) = (1/|G|) Σ_g s_g · C_brut(g·x), avec les signes de l'export : le
    même que la réduction suppose. Seuls les coefficients de la trajectoire.
    """
    noms = list(contexte.reduction.etude.trajectoire.coefficients)
    total = {c: modele_brut(valeurs, contexte)[c].copy() for c in noms}
    for s in contexte.symetries:
        image = {k: (-x if k in s["variables"] else x) for k, x in valeurs.items()}
        brut = modele_brut(image, contexte)
        for c in noms:
            total[c] += (-1.0 if c in s["coefficients"] else 1.0) * brut[c]
    return {c: x / (1 + len(contexte.symetries)) for c, x in total.items()}


def basse_fidelite(y: np.ndarray) -> np.ndarray:
    """Un solveur moins fidèle : biais lisse, fonction impaire de C (symétries conservées)."""
    return 0.9 * y + 0.03 * y**3


def calculer(points: Sequence[PointDOE], contexte: Contexte) -> Mesures:
    """« Lance la CFD » sur ces points."""
    valeurs = {c: np.array([p.valeurs[c] for p in points]) for c in contexte.colonnes}
    y = verite(contexte, valeurs)
    bf = np.array([p.fidelite == "BF" for p in points])
    if bf.any():
        y = {c: np.where(bf, basse_fidelite(x), x) for c, x in y.items()}
    return Mesures(tuple(points), y)


# ---------------------------------------------------------------------------
# 2. Erreurs
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Bilan:
    """Ce qu'un plan a coûté et ce qu'il donne."""

    plan: PlanDOE
    calculs: int
    tables: Tables
    rms: dict[str, float]  # % de l'étendue du coefficient, sur la grille
    maxi: dict[str, float]
    verification: dict[str, float]  # rôle → RMS du pire coefficient aux points de ce rôle (%)
    duree: float
    lots: int = 0

    @property
    def pire(self) -> float:
        return max(self.rms.values())

    @property
    def pire_max(self) -> float:
        return max(self.maxi.values())


def _etendue(x: np.ndarray) -> float:
    e = float(np.nanmax(x) - np.nanmin(x))
    return e if e > 1e-12 else 1.0


def evaluer(
    plan: PlanDOE, tables: Tables, vraie: Mapping[str, np.ndarray], calculs: int, duree: float
) -> Bilan:
    rms, maxi = {}, {}
    for c, t in tables.valeurs.items():
        e = t - vraie[c]
        echelle = _etendue(vraie[c])
        rms[c] = 100 * float(np.sqrt(np.nanmean(e**2))) / echelle
        maxi[c] = 100 * float(np.nanmax(np.abs(e))) / echelle
    verification = {
        role: max(
            100 * float(np.sqrt(np.mean(e**2))) / _etendue(vraie[c]) for c, e in ecarts.items()
        )
        for role, ecarts in tables.ecarts.items()
    }
    return Bilan(plan, calculs, tables, rms, maxi, verification, duree)


# ---------------------------------------------------------------------------
# 3. Un plan, de bout en bout
# ---------------------------------------------------------------------------


def traiter(
    plan: PlanDOE,
    contexte: Contexte,
    vraie: Mapping[str, np.ndarray],
    sortie: Path,
    *,
    lots: int,
    rapide: bool,
) -> Bilan:
    debut = time.perf_counter()
    # La CFD, puis le fichier de résultats qu'on relit comme un vrai.
    resultats = ecrire_mesures(
        calculer(plan.points, contexte), contexte, sortie / "RESULTATS" / f"{plan.nom}.csv"
    )
    mesures = lire_mesures(resultats, contexte)
    tables = reconstruire(plan, contexte, mesures, portees_communes=rapide)
    calculs = len(mesures.points)

    faits = 0
    if plan.spec.type == "adaptatif" and lots > 0:
        par_lot = max(
            4,
            math.ceil(
                sum(p.role == "calcul" for p in plan.points)
                / max(1, len(contexte.machs or (0,)))
                / 2
            ),
        )
        for k in range(1, lots + 1):
            lot = lot_suivant(plan, contexte, mesures, par_lot, graine=k)
            if not lot:
                break
            lot_plan = dataclasses.replace(plan, points=tuple(lot))
            ecrire_csv(lot_plan, contexte, sortie / "LOTS" / f"{plan.nom}_lot_{k}.csv")
            mesures = mesures + calculer(lot, contexte)
            tables = reconstruire(plan, contexte, mesures, portees_communes=rapide)
            faits = k
        calculs = len(mesures.points)
    bilan = evaluer(plan, tables, vraie, calculs, time.perf_counter() - debut)
    bilan.lots = faits
    return bilan


# ---------------------------------------------------------------------------
# 4. Rapport
# ---------------------------------------------------------------------------


def _pct(x: float | None) -> str:
    if x is None:
        return "·"
    if x < 1e-6:
        return "exact"
    if x < 1e-3:
        return "< 0,001 %"
    if x >= 100:
        return "> 100 %"
    return f"{x:.2g} %".replace(".", ",")


_COURT = {"polynome": "poly. 2", "co-krigeage": "co-krig."}


def rapport(bilans: Sequence[Bilan], contexte: Contexte, retenu: str) -> None:
    grille = grille_carree(contexte)
    tableau = Table(
        title=f"Tables reconstruites : {grille.taille:,} nœuds par coefficient".replace(",", " "),
        box=box.SIMPLE_HEAD,
        title_justify="left",
        padding=(0, 1),
        pad_edge=False,
    )
    tableau.add_column("plan", no_wrap=True, max_width=15, overflow="ellipsis")
    tableau.add_column("modèle", no_wrap=True)
    for titre in ("calculs", "contrôle", "test", "RMS", "max"):
        tableau.add_column(titre, justify="right", no_wrap=True)
    for b in bilans:
        nom = ("▸ " if b.plan.nom == retenu else "  ") + b.plan.nom
        methode = _COURT.get(b.plan.reconstruction, b.plan.reconstruction)
        tableau.add_row(
            nom,
            methode,
            f"{b.calculs:,}".replace(",", " "),
            _pct(b.verification.get("controle")),
            _pct(b.verification.get("test")),
            _pct(b.pire),
            _pct(b.pire_max),
        )
    console.print(tableau)
    console.print(
        "    ▸ plan retenu · erreurs en % de l'étendue du coefficient (le pire) · "
        "contrôle, test : écart RMS aux points de vérification du plan, ce qu'on mesure "
        "en vrai · RMS, max : sur toute la grille, ce que seule la vérité factice permet",
        style="dim",
    )
    exclus = {b.tables.exclus for b in bilans}
    if exclus != {0}:
        console.print(
            f"    {max(exclus):,} nœuds écartés par « exclure » : laissés vides dans toutes "
            "les tables, hors des erreurs".replace(",", " "),
            style="dim",
        )
    for b in bilans:
        if b.lots:
            console.print(
                f"    {b.plan.nom} : lot initial + {b.lots} lots d'enrichissement simulés "
                f"({b.calculs} calculs en tout)",
                style="dim",
            )
        for note in b.tables.notes:
            console.print(f"    {b.plan.nom} : {note}", style="dim")


# ---------------------------------------------------------------------------
# 5. Programme
# ---------------------------------------------------------------------------


def preparer_remplissage(chemin: Path) -> Remplissage:
    remplissage = charger_remplissage(chemin)
    if remplissage.etude.repere != "cartesien":
        console.print(
            f"[dim]repère {remplissage.etude.repere} → cartésien (reconstruction cartésienne)[/]"
        )
        remplissage = dataclasses.replace(
            remplissage, etude=remplissage.etude.avec(repere="cartesien")
        )
    return remplissage


def principal(argv: Sequence[str] | None = None) -> list[Bilan]:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("remplissage", nargs="?", default=str(ICI / "REMPLISSAGE_FUSEE.yaml"))
    parser.add_argument("--plans", nargs="+", help="plans à traiter (défaut : tous)")
    parser.add_argument("--sortie", default="RECONSTRUCTION", help="dossier de sortie")
    parser.add_argument(
        "--tables",
        choices=("retenu", "tous", "aucun"),
        default="retenu",
        help="plans dont on écrit les tables (défaut : le plan retenu)",
    )
    parser.add_argument("--lots", type=int, default=3, help="lots d'enrichissement (adaptatif)")
    parser.add_argument(
        "--rapide", action="store_true", help="krigeage à portées communes aux coefficients"
    )
    parser.add_argument("--sans-figures", action="store_true")
    args = parser.parse_args(argv)

    remplissage = preparer_remplissage(Path(args.remplissage))
    sortie = Path(args.sortie)
    resultat = remplir(remplissage, seulement=args.plans)
    c = resultat.contexte
    grille = grille_carree(c)
    points = grille.points()
    colonnes = list(grille.colonnes)
    valeurs = {
        col: points[:, colonnes.index(col)]
        if col in colonnes
        else np.full(len(points), c.reference[col])
        for col in c.colonnes
    }
    vraie = verite(c, valeurs)
    console.print(
        f"[bold]{remplissage.nom}[/] · {c.reduction.etude.trajectoire.nom}, "
        f"{c.reduction.etude.geometrie.nom}, groupe {c.reduction.groupe} · "
        f"coefficients {', '.join(vraie)} · grille {' × '.join(str(len(a)) for a in grille.axes.values())} "
        f"({', '.join(grille.colonnes)})"
    )

    bilans = []
    for plan in resultat.plans:
        with console.status(f"{plan.nom} : calcul, reconstruction…"):
            bilan = traiter(plan, c, vraie, sortie, lots=args.lots, rapide=args.rapide)
        bilans.append(bilan)
        console.print(
            f"  {plan.nom:<16} {bilan.calculs:>6} calculs  {bilan.duree:5.1f} s", style="dim"
        )
        if args.tables == "tous" or (args.tables == "retenu" and plan.nom == remplissage.retenu):
            fichiers = ecrire_tables(bilan.tables, sortie / "TABLES" / plan.nom)
            verifier_carree(fichiers[0], grille.taille)
            console.print(
                f"    tables : {len(fichiers)} fichiers ({', '.join(f.name for f in fichiers)}) "
                f"dans {fichiers[0].parent}",
                style="dim",
            )
    rapport(bilans, c, remplissage.retenu)

    if not args.sans_figures:
        from cfd_doe.report.figures import (
            FiguresIndisponibles,
            Precision,
            figure_coupes,
            figure_precision,
        )

        try:
            dossier = sortie / "FIGURES"
            figure_precision(
                [Precision(b.plan, b.calculs, b.pire, b.pire_max) for b in bilans],
                dossier,
                titre=f"{c.reduction.etude.nom} : précision contre coût",
            )
            for coef in vraie:
                figure_coupes(c, [b.tables for b in bilans], coef, dossier, reference=vraie[coef])
            console.print(f"figures : {dossier}", style="dim")
        except FiguresIndisponibles as erreur:
            console.print(f"[dim]figures ignorées : {erreur}[/]")
    return bilans


def verifier_carree(chemin: Path, attendu: int) -> None:
    """Une table du simulateur est carrée : une ligne par nœud, aucun en double."""
    with chemin.open(encoding="utf-8") as fichier:
        lignes = fichier.read().splitlines()[1:]
    cles = {tuple(ligne.split("\t")[:-1]) for ligne in lignes}
    if len(lignes) != attendu or len(cles) != attendu:
        raise RuntimeError(
            f"{chemin} : {len(lignes)} lignes, {len(cles)} nœuds, {attendu} attendus"
        )


if __name__ == "__main__":
    from cfd_doe.data.etude import ErreurEtude

    try:
        principal()
    except ErreurEtude as erreur:
        console.print(f"[red]erreur :[/] {erreur}")
        sys.exit(1)
