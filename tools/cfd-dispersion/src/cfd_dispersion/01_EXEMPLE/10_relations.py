#!/usr/bin/env python3
"""Les lois d'un coefficient que le modèle ne disperse pas, mais qu'il rend.

    python 10_relations.py [--sortie SORTIE] [-n 200] [--jobs -1]

Le décalage entre ce qu'on disperse et ce qu'on publie
------------------------------------------------------
La table de lois porte sur ce que le modèle **consomme** ; le tableau de sortie
sur ce qu'il **produit**. Ici, les deux ne parlent pas des mêmes coefficients :

    lois       CZ                  CX1, CX2            Cm_alpha
    sorties    CN                  CA                  Cm_alpha

Sans rien de plus, `CN` et `CA` sont des colonnes sans loi : leur histogramme
se trace, mais rien ne dit ce qu'il aurait dû être — donc rien ne se valide.

Or le lien est simple, et c'est presque toujours le cas :

    CN = -CZ                changement de repère
    CA = CX1 + CX2          frottement + pression

C'est ce qu'on écrit en `relations=`, et le paquet en **déduit les lois** de
`CN` et de `CA` — puis les leur applique comme si elles avaient été déclarées.

Ce que le script montre, dans l'ordre
-------------------------------------
  1. le problème : sans relation, deux sorties sans loi ;
  2. la dérivation à la main : `loi_derivee`, et ce qu'elle rend ;
  3. le parcours des tirages avec `relations=`, en mode bavard ;
  4. le contrôle qui vient en prime : l'accord modèle / calcul porte
     désormais sur la **relation elle-même** ;
  5. les histogrammes : la loi dérivée contre ce qui a été réalisé ;
  6. `coefficients_en_plus=` : ajouter une sortie sans réécrire la liste ;
  7. les trois refus, et ce qu'ils disent.

Sorties, dans SORTIE/RELATIONS/ :

    TIRAGES/M_0.85/Z_10000/tirage_000/CA.svg   la loi dérivée et le tirage
    HISTO/M_0.92/Z_10000/CA.svg                la loi dérivée et les n tirages
    INVENTAIRE_RELATIONS.csv                   ce qui a été écrit

Chez vous
---------
Deux lignes à écrire, et deux seulement :

    RELATIONS = {"CN": "-CZ", "CA": "CX1 + CX2"}
    figures_tirage_par_pdv(df, ..., relations=RELATIONS)

Le reste — les lois dérivées, les composantes dérivées, la loi combinée, le
contrôle — en découle.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

# Agg = « dessine dans un fichier, n'ouvre pas de fenêtre ». À poser AVANT
# d'importer pyplot : sur une machine de calcul sans écran, il échoue sinon.
matplotlib.use("Agg")

from rich.console import Console

from cfd_dispersion import (
    JeuDeLois,
    Relation,
    charger_lois,
    charger_relations,
    loi_derivee,
    poids_derives,
)
from cfd_dispersion.figures.histogramme import figures_histogramme_par_pdv
from cfd_dispersion.figures.par_pdv import figures_tirage_par_pdv
from cfd_dispersion.report.console import table_lois

ICI = Path(__file__).resolve().parent

# `sortie_modele_relations.py` est le fichier d'à côté, pas un paquet installé.
# Chez vous, c'est votre modèle qu'on importe ici — ou rien du tout, si vous
# relisez un CSV déjà écrit.
sys.path.insert(0, str(ICI))

from sortie_modele_relations import (  # noqa: E402
    DICT_LAW_DISPERSION,
    POINTS_DE_VOL,
    RELATIONS,
    sortie_modele,
    sortie_modele_reference,
)

#: Le dictionnaire de points de vol, forme du `flight_point_dict` de
#: `cfd_plot.batch_plot` — la même que dans les exemples 06 et 07.
POINTS_DE_VOL_DICT = {
    "Mach": {
        "values": sorted({point["Mach"] for point in POINTS_DE_VOL}),
        "label": "M",
        "save_name": "M",
    },
    "Altitude_m": {
        "values": sorted({point["Altitude_m"] for point in POINTS_DE_VOL}),
        "label": "Z",
        "save_name": "Z",
        "unit": " m",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sortie", type=Path, default=ICI / "SORTIE")
    parser.add_argument("-n", type=int, default=200, help="tirages par point de vol")
    parser.add_argument("--max-tirages", type=int, default=3, help="tirages tracés par PDV")
    parser.add_argument("--jobs", type=int, default=-1, help="processus (-1 = tous les cœurs)")
    args = parser.parse_args()

    console = Console()
    racine = args.sortie / "RELATIONS"
    racine.mkdir(parents=True, exist_ok=True)

    df = sortie_modele(args.n)
    reference = sortie_modele_reference()

    # --- 1. le problème --------------------------------------------------
    #
    # Les lois portent sur CZ, CX1, CX2 et Cm_alpha ; le modèle rend CN, CA et
    # Cm_alpha. Deux des trois sorties n'ont donc aucune loi qui les décrive.
    console.print("[bold]1. Le décalage[/]")
    console.print(f"  lois sur       : {list(DICT_LAW_DISPERSION)}")
    console.print("  sorties        : ['CN', 'CA', 'Cm_alpha', 'CY']")
    console.print(
        "  sans relation  : [yellow]CN et CA n'ont pas de loi[/] — "
        "leur histogramme se trace, mais rien ne dit ce qu'il aurait dû être"
    )

    # --- 2. la dérivation, à la main -------------------------------------
    #
    # `charger_relations` lit les trois écritures admises ; ici la plus
    # courante, {cible: expression}. `loi_derivee` en tire les DEUX lois de la
    # cible — celle du biais et celle du facteur d'échelle.
    #
    # Les deux relations ne se dérivent pas de la même façon, et c'est tout
    # l'objet de cette section :
    #
    #   CN = -CZ          UN terme, pas de constante. Multiplier un coefficient
    #                     par -1 multiplie son biais par -1 et laisse son
    #                     facteur d'échelle intact, quel que soit le nominal.
    #                     La loi dérivée reste DANS SA FAMILLE : une gaussienne
    #                     ±3σ reste une gaussienne ±3σ, avec le même ET.
    #
    #   CA = CX1 + CX2    DEUX termes. Le facteur d'échelle de CA est une
    #                     moyenne PONDÉRÉE de ceux de CX1 et CX2, au prorata de
    #                     ce que chacun pèse dans CA — donc les nominaux sont
    #                     nécessaires, et la loi change d'un point de vol à
    #                     l'autre. Elle n'appartient plus à aucune des six
    #                     familles : c'est une combinaison, calculée par
    #                     OpenTURNS.
    console.print("\n[bold]2. Les lois dérivées[/]")
    lois = charger_lois(DICT_LAW_DISPERSION)
    liens = charger_relations(RELATIONS)
    for lien in liens.values():
        console.print(f"  {lien}")

    # Le point de vol transsonique, où CX2 pèse le plus lourd.
    ligne_ref = dict(reference[reference["Mach"] == 0.92].iloc[0])
    nominaux = {nom: float(ligne_ref[nom]) for nom in ("CZ", "CX1", "CX2")}
    console.print(f"  nominaux (M = 0.92) : {nominaux}")

    derivees = {cible: loi_derivee(lien, lois, nominaux=nominaux) for cible, lien in liens.items()}
    # `table_lois` attend un jeu de lois ; un dict de LoiCoefficient en tient
    # lieu pour l'affichage, via le même chemin que les lois déclarées.
    console.print(table_lois(JeuDeLois(derivees), titre="Lois dérivées"))
    console.print(
        "  CN : [green]même famille, même ET[/] que CZ — un seul terme, pas de nominal en jeu\n"
        "  CA : [green]une combinaison[/] — ni uniforme ni gaussienne, et ses poids de FE "
        f"valent {_parts(liens['CA'], nominaux)}"
    )

    # --- 3. le parcours des tirages --------------------------------------
    #
    # `relations=` suffit. Les cibles rejoignent la liste par défaut des
    # coefficients — celle des lois — et sont tracées comme les autres : deux
    # panneaux de composantes sur leur loi dérivée, et le troisième sur la loi
    # combinée.
    #
    # `verbeux=True` imprime le plan puis une barre de progression ;
    # `rapport=True` (le défaut) imprime le bilan des fichiers écrits. Ce sont
    # les `verbose` / `report` / `dry_run` de `cfd_plot.batch_plot`, aux mêmes
    # places et pour les mêmes raisons.
    console.print("\n[bold]3. Le parcours, avec les relations[/]")
    inventaire = figures_tirage_par_pdv(
        df,
        points_de_vol=POINTS_DE_VOL_DICT,
        racine=racine / "TIRAGES",
        reference=reference,
        relations=RELATIONS,
        coefficients=["CN", "CA", "Cm_alpha"],
        max_tirages=args.max_tirages,
        nettoyer=True,
        n_jobs=args.jobs,
        verbeux=True,
    )

    # --- 4. le contrôle qui vient en prime -------------------------------
    #
    # Le paquet recalcule convention(nominal, biais, FE) et le confronte à la
    # colonne du modèle. Pour un coefficient déclaré, cela contrôle la
    # convention. Pour une CIBLE, cela contrôle en plus la RELATION : le biais
    # et le FE viennent de la dérivation, la valeur vient du modèle, et les
    # deux ne tombent sur le même nombre que si le modèle applique bien la
    # relation qu'on lui a prêtée.
    verdicts = inventaire["accord"].dropna()
    console.print(
        f"\n[bold]4. Accord modèle / calcul[/] : "
        f"{int(verdicts.sum())}/{len(verdicts)} coefficients"
        + ("" if verdicts.all() else "  [red]— voir les figures en rouge[/]")
    )
    console.print(
        "  sur CN et CA, ce contrôle porte sur la relation : biais et FE viennent\n"
        "  de la dérivation, la valeur vient du modèle. Ils ne coïncident que si\n"
        "  le modèle applique bien la relation déclarée."
    )

    chemin = args.sortie / "INVENTAIRE_RELATIONS.csv"
    inventaire.to_csv(chemin, index=False)
    console.print(f"[green]écrit :[/] {chemin}")

    # --- 5. les histogrammes ---------------------------------------------
    #
    # Le modèle ne rend pas CA_Biais ni CA_FE — il ne rend que CA. Le parcours
    # les RECOMPOSE depuis ceux de CX1 et CX2, avec les poids de la
    # dérivation : les deux premiers panneaux confrontent donc pour de bon la
    # loi dérivée à ce qui a été réalisé, sur les n tirages.
    console.print("\n[bold]5. Les histogrammes[/]")
    inventaire_histo = figures_histogramme_par_pdv(
        df,
        points_de_vol=POINTS_DE_VOL_DICT,
        racine=racine / "HISTO",
        reference=reference,
        relations=RELATIONS,
        coefficients=["CN", "CA"],
        nettoyer=True,
        n_jobs=args.jobs,
        rapport=False,
    )
    console.print(f"  {len(inventaire_histo)} figures dans {racine / 'HISTO'}")
    console.print(
        "  à regarder : le panneau « CA — Biais », dont la loi dérivée n'est ni\n"
        "  uniforme ni gaussienne mais la somme des deux — un plateau à épaules"
    )

    # --- 6. ajouter un coefficient à la liste par défaut ------------------
    #
    # Sans rien préciser, le parcours trace ce qui est dispersé : les lois,
    # plus les cibles des relations. Pour en tracer un DE PLUS — une colonne de
    # sortie qui n'a ni loi ni relation, mais qu'on veut voir — il n'y a pas à
    # réécrire la liste : `coefficients_en_plus=` s'y ajoute.
    #
    #   coefficients=          REMPLACE la liste par défaut
    #   coefficients_en_plus=  S'Y AJOUTE
    #
    # Ici on ajoute CY : le modèle la rend, mais aucune loi et aucune relation
    # ne la décrit — elle n'est donc pas dispersée, et n'a pas à figurer par
    # défaut. Sa figure garde ce qu'il reste à en dire : le nominal, la valeur
    # rendue et leur écart.
    console.print("\n[bold]6. Un coefficient de plus[/]")
    en_plus = figures_tirage_par_pdv(
        df,
        points_de_vol={"Mach": [0.92], "Altitude_m": [10_000.0]},
        racine=racine / "EN_PLUS",
        reference=reference,
        relations=RELATIONS,
        coefficients_en_plus=["CY"],
        max_tirages=1,
        matrice=False,
        nettoyer=True,
        n_jobs=1,
        rapport=False,
    )
    console.print(f"  par défaut : {list(DICT_LAW_DISPERSION)} + {list(RELATIONS)}")
    console.print(f"  tracé      : {sorted(set(en_plus['figure']))}")
    console.print(
        "  CY n'a ni loi ni relation : ses deux premiers panneaux le disent, et\n"
        "  le troisième garde le nominal, la valeur rendue et leur écart."
    )

    # --- 7. les refus ----------------------------------------------------
    #
    # Trois, et chacun dit ce qu'il faut faire. Ils comptent autant que la
    # fonctionnalité : une loi dérivée fausse ressemble trait pour trait à une
    # loi dérivée juste.
    console.print("\n[bold]7. Ce que le paquet refuse[/]")

    # (a) une relation à plusieurs termes sans les nominaux de ses sources :
    #     les poids du facteur d'échelle sont des parts, et une part ne se
    #     devine pas.
    try:
        loi_derivee(liens["CA"], lois)
    except ValueError as erreur:
        console.print(f"  [red]sans nominaux[/] : {erreur}")

    # (b) une relation qui n'est pas celle du modèle. La référence porte CA ;
    #     la relation en donne une autre valeur ; toutes les lois dérivées de
    #     ce point de vol seraient fausses sans que rien ne le dise.
    try:
        figures_tirage_par_pdv(
            df,
            points_de_vol={"Mach": [0.92], "Altitude_m": [10_000.0]},
            racine=racine / "REFUS",
            reference=reference,
            relations={"CA": "CX1 - CX2"},  # le modèle fait une somme, pas une différence
            coefficients=["CA"],
            max_tirages=1,
            n_jobs=1,
            rapport=False,
        )
    except ValueError as erreur:
        console.print(f"  [red]relation fausse[/] : {erreur}")

    # (c) une relation non linéaire. Une loi dérivée n'aurait alors plus de
    #     sens : ce n'est plus une combinaison de lois.
    try:
        charger_relations({"CA": "CX1 * CX2"})
    except ValueError as erreur:
        console.print(f"  [red]non linéaire[/] : {erreur}")

    console.print(f"\n[green]figures :[/] {racine}")
    return 0


def _parts(lien: Relation, nominaux: dict[str, float]) -> str:
    """Les poids du facteur d'échelle, en pourcentages lisibles."""
    _, poids_fe, _ = poids_derives(lien, nominaux=nominaux)
    return " et ".join(f"{100 * part:.0f} % ({nom})" for nom, part in poids_fe.items())


if __name__ == "__main__":
    raise SystemExit(main())
