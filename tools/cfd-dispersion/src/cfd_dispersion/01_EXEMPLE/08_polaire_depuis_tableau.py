#!/usr/bin/env python3
"""Une polaire dispersée, à partir du tableau qu'on a sous la main.

    python 08_polaire_depuis_tableau.py [--sortie SORTIE] [-n 100]

La situation : vous avez isolé une polaire dans un tableau à plat —

    Mach   alpha   CN      CA     Cm_alpha   tirage
    0.80    0.0    0.021   0.031   -2.50        0
    0.80    1.0    0.171   0.031   -2.50        0
    …                                           …

soit **une ligne par (tirage × incidence)** : cent tirages sur treize
incidences font 1300 lignes. Et vous avez, à côté, la polaire de **référence**
— le même modèle tourné une fois sans dispersion.

La figure est la vôtre
----------------------
Tout ce qui la construit vient de **cfd-plot**, appelé directement : le style,
les axes, la courbe de référence, les libellés, le titre, l'export.

    import cfd_plot as cplt

    with cplt.style_context("notebook"):
        figure, ax = cplt.new_figure(figsize=(8.0, 5.0))
        cplt.plot_line(ax, alpha, cn_reference, label="CN", color="C0")
        cplt.set_title(ax, "CN — M = 0.80")

cfd-dispersion n'ajoute qu'une chose, sur des axes qui existent déjà :

    superposer_depuis_tableau(ax, df_disperse, x="alpha", y="CN",
                              reference=df_reference, serie="CN")

et cette ligne pose, dans cet ordre :

  * les **cent courbes** obtenues, en teinte claire au fond ;
  * le **faisceau min/max**, rempli dans la teinte de la série ;
  * la **moyenne dispersée**, dans la même teinte en plus sombre ;
  * les lignes **±1σ, ±2σ, ±3σ**, étiquetées *sur* la courbe ;
  * la **boîte** qui chiffre tout cela, et le chiffre de tête en légende.

Elle appelle elle-même ``cfd_plot.make_legend`` pour refaire la légende : les
artistes qu'elle vient d'ajouter y seraient sinon absents.

> La même chose, automatisée sur toute une campagne, c'est
> ``cfd_plot.batch_plot`` avec le hook du script 03. Ici la figure est montée à
> la main, parce que c'est comme cela qu'on prépare une planche pour un dossier.

Ce que le script montre :

  1. le tableau de départ, et sa référence ;
  2. la figure complète, en une ligne ;
  3. les variantes : sans référence, en percentile, sans les tirages ;
  4. les trois coefficients sur une figure ;
  5. les chiffres seuls, sans figure — pour un compte rendu.

Sorties, dans SORTIE/ :

    polaire_CN.svg              la figure complète
    polaire_variantes.svg       trois réglages côte à côte
    polaire_trois_coeffs.svg    les trois coefficients, chacun sa teinte
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import cfd_plot as cplt
import matplotlib
import numpy as np
from rich.console import Console

# Agg : on dessine dans des fichiers, pas dans des fenêtres. À poser avant
# d'importer pyplot.
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from cfd_dispersion import (
    bande_depuis_courbes,
    charger_lois_yaml,
    courbes_par_tirage,
    enregistrer,
    resume_dispersion,
    superposer_depuis_tableau,
    tirage_neutre,
)

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))

from modele import appeler_modele_polaire  # noqa: E402

#: Le balayage : treize incidences, de 0 à 12 degrés.
ALPHA = np.linspace(0.0, 12.0, 13)

#: Les libellés d'axes, montés par cfd-plot à partir du nom, du symbole et de
#: l'unité — la même mise en forme que sur les figures de `batch_plot`.
LIBELLE_ALPHA = cplt.format_axis_label(
    {"literal_name": "incidence", "symbol": "α", "unit": "°"}, "alpha"
)
LIBELLE_CN = cplt.format_axis_label({"literal_name": "coefficient normal", "symbol": "$C_N$"}, "CN")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sortie", type=Path, default=ICI / "SORTIE")
    parser.add_argument("--lois", type=Path, default=ICI / "LOIS.yaml")
    parser.add_argument("-n", type=int, default=100, help="nombre de tirages")
    args = parser.parse_args()

    console = Console()
    args.sortie.mkdir(parents=True, exist_ok=True)
    lois = charger_lois_yaml(args.lois)

    # --- 1. le tableau de départ, et sa référence -----------------------
    #
    # `appeler_modele_polaire` est le modèle jouet : il tire n fois et applique
    # chaque tirage à toute la polaire — le cas *corrélé*, celui d'une erreur
    # de recalage, et le cas physique usuel.
    #
    # La référence, elle, est le même modèle avec un tirage NEUTRE : biais 0 et
    # FE 1 pour la convention linéaire. `tirage_neutre` résout ce facteur
    # depuis la convention plutôt que de le coder en dur.
    df_disperse = appeler_modele_polaire(lois, ALPHA, n=args.n)
    df_reference = appeler_modele_polaire(lois, ALPHA, tirages=[tirage_neutre(lois)])

    console.print(
        f"[bold]Tableau dispersé[/] : {len(df_disperse)} lignes "
        f"({args.n} tirages × {ALPHA.size} incidences)"
    )
    console.print(f"  colonnes : {sorted(df_disperse.columns)}")
    console.print(f"[bold]Référence[/] : {len(df_reference)} lignes, une par incidence")

    alpha = df_reference["alpha"].to_numpy()

    # --- 2. la figure ---------------------------------------------------
    #
    # La figure est montée **avec cfd-plot** : `style_context` pose le profil
    # (police, marges, palette) sans toucher aux rcParams globaux de personne,
    # `new_figure` crée les axes au gabarit, `plot_line` trace la référence, et
    # `set_title` emploie la police de titre du framework.
    #
    # Puis cfd-dispersion pose la dispersion dessus. `serie="CN"` va chercher
    # la couleur de la courbe intitulée ainsi : le faisceau et le remplissage la
    # reprennent, la moyenne dispersée la reprend en plus sombre. La dispersion
    # se lit alors comme appartenant à cette courbe-là, sans légende
    # supplémentaire — ce qui compte dès qu'il y a trois séries sur la figure.
    with cplt.style_context("notebook"):
        figure, ax = cplt.new_figure(figsize=(8.0, 5.0))
        cplt.plot_line(
            ax,
            alpha,
            df_reference["CN"].to_numpy(),
            label="CN",
            color="C0",
            marker="o",
        )
        ax.set_xlabel(LIBELLE_ALPHA)
        ax.set_ylabel(LIBELLE_CN)
        cplt.set_title(ax, "Polaire dispersée — M = 0.80")

        artistes = superposer_depuis_tableau(
            ax,
            df_disperse,
            x="alpha",
            y="CN",
            reference=df_reference,  # un DataFrame de même forme
            serie="CN",  # reprendre la couleur de la courbe "CN"
        )

        # `enregistrer` est `cfd_plot.save_figure` plus un garde-fou : ce
        # dernier compose son fichier avec `Path.with_suffix`, qui remplace
        # tout ce qui suit le dernier point — un nom aussi banal que
        # « polaire_M0.85 » y perdrait son « .85 », et toute une série de
        # points de vol s'écraserait dans un seul fichier.
        (chemin,) = enregistrer(figure, args.sortie / "polaire_CN", formats=("svg",))
        plt.close(figure)

    # `artistes` rend ce qui a été créé : le remplissage, la moyenne, les
    # courbes par tirage, les lignes σ, la boîte, et la bande elle-même.
    console.print(f"\n[green]écrit :[/] {chemin}")
    console.print(f"  artistes rendus : {sorted(artistes)}")

    # --- 3. les variantes ------------------------------------------------
    #
    # Trois réglages, côte à côte, pour voir ce que chacun change :
    #
    #   * sans `reference=` : la MOYENNE des tirages tient lieu de nominal.
    #     Correct tant que les lois sont centrées, faux dès qu'elles ne le sont
    #     pas — la bande se centre alors sur elle-même et le biais devient
    #     invisible. Le chiffre « écart moyen/nominal » tombe à zéro, et c'est
    #     ainsi qu'on s'en aperçoit ;
    #   * `remplissage="percentile"` : l'enveloppe à 95 % au lieu du min/max,
    #     qui ne dépend pas des deux tirages les plus extrêmes ;
    #   * `max_tirages=0` : le faisceau sans les courbes, quand elles
    #     noircissent la figure.
    #
    # `new_figure(1, 3)` rend une grille d'axes, comme `plt.subplots`.
    with cplt.style_context("notebook"):
        figure, grille = cplt.new_figure(1, 3, figsize=(15.0, 4.2))
        variantes: tuple[tuple[str, dict[str, Any]], ...] = (
            ("sans référence", {"reference": None}),
            ("percentile 95 %", {"remplissage": "percentile", "couverture": 0.95}),
            ("sans les tirages", {"max_tirages": 0}),
        )
        for panneau, (nom, options) in zip(np.ravel(grille), variantes):
            cplt.plot_line(
                panneau,
                alpha,
                df_reference["CN"].to_numpy(),
                label="CN",
                color="C0",
                marker="",
            )
            # `reference=df_reference` sauf quand la variante dit le contraire.
            reglages: dict[str, Any] = {"reference": df_reference, **options}
            superposer_depuis_tableau(
                panneau, df_disperse, x="alpha", y="CN", serie="CN", **reglages
            )
            cplt.set_title(panneau, nom)
            panneau.set_xlabel(LIBELLE_ALPHA)
        np.ravel(grille)[0].set_ylabel(LIBELLE_CN)

        (chemin,) = enregistrer(figure, args.sortie / "polaire_variantes", formats=("svg",))
        plt.close(figure)
    console.print(f"[green]écrit :[/] {chemin}")

    # --- 4. les trois coefficients sur une figure ------------------------
    #
    # Chaque coefficient garde sa teinte : `serie=` suffit, et il n'y a rien à
    # accorder à la main.
    with cplt.style_context("notebook"):
        figure, ax = cplt.new_figure(figsize=(8.0, 5.0))
        for indice, coefficient in enumerate(("CN", "CA", "Cm_alpha")):
            cplt.plot_line(
                ax,
                alpha,
                df_reference[coefficient].to_numpy(),
                label=coefficient,
                color=f"C{indice}",
                marker="",
            )
            superposer_depuis_tableau(
                ax,
                df_disperse,
                x="alpha",
                y=coefficient,
                reference=df_reference,
                serie=coefficient,
                # Une seule boîte suffirait pour trois coefficients : on la
                # coupe, et le chiffre de tête reste en légende.
                boite_parametres=False,
                etiquettes_sigma=False,
                max_tirages=40,
                label=coefficient,
            )
        ax.set_xlabel(LIBELLE_ALPHA)
        ax.set_ylabel("coefficient")
        cplt.set_title(ax, "Trois coefficients dispersés — M = 0.80")

        (chemin,) = enregistrer(figure, args.sortie / "polaire_trois_coeffs", formats=("svg",))
        plt.close(figure)
    console.print(f"[green]écrit :[/] {chemin}")

    # --- 5. les chiffres seuls -------------------------------------------
    #
    # Pour un compte rendu, la figure ne suffit pas : il faut les nombres.
    # `courbes_par_tirage` remet le tableau en forme (une ligne par tirage),
    # `bande_depuis_courbes` en fait une bande — sans rien retirer, les courbes
    # venant du modèle — et `resume_dispersion` la réduit à ce qu'on recopie.
    console.print("\n[bold]Les chiffres, sans figure[/]")
    for coefficient in ("CN", "CA", "Cm_alpha"):
        abscisse, courbes = courbes_par_tirage(
            df_disperse, x="alpha", y=coefficient, par=["tirage"]
        )
        bande = bande_depuis_courbes(
            abscisse,
            df_reference[coefficient].to_numpy(),
            courbes,
        )
        resume = resume_dispersion(bande)
        console.print(f"  {coefficient:<9} {resume.resume}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
