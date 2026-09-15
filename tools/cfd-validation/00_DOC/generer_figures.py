"""Régénère les figures de la documentation.

    python3 00_DOC/generer_figures.py

Deux figures, toutes deux produites par le paquet lui-même — ce ne sont pas
des illustrations reconstituées :

``01_planche_ecretage.png``
    Une planche de ``cfd_plot.batch_plot`` telle que ``tracer_rapport`` l'écrit,
    sur la panne « indice saturé au bord ». C'est celle du README.

``02_galerie_des_pannes.png``
    La même polaire, une fois par panne injectée dans le modèle factice. Ce à
    quoi chaque motif ressemble avant qu'on l'ait nommé — et pourquoi une
    courbe seule ne suffit pas.

Nécessite cfd-plot.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import cfd_plot

from cfd_validation import valider_tables
from cfd_validation.report.figures import points_fautifs, tracer_table
from cfd_validation.report.theme import COULEUR_VERDICT
from cfd_validation.wrap.factice import BUGS, TABLES, ModeleFactice, module_factice

ICI = Path(__file__).resolve().parent
FIGURES = ICI / "FIGURES"

#: Le point de la polaire montrée dans la galerie.
ALPHA, DELTA = 4.0, 0.0


def planche_ecretage() -> Path:
    """La planche du README, sortie telle quelle de ``batch_plot``."""
    module = module_factice()
    rapport = valider_tables(module, TABLES, modele=ModeleFactice(module, bug="ecretage"))
    with tempfile.TemporaryDirectory() as atelier:
        ecrits = tracer_table(
            rapport["CN"], sortie=atelier, max_valeurs=None, options={"report": False}
        )
        cible = next(
            chemin
            for chemin in ecrits
            if "MACH_POLAR" in str(chemin)
            and f"ALPHA_{ALPHA:g}" in str(chemin)
            and f"DELTA_{DELTA:g}" in str(chemin)
        )
        destination = FIGURES / "01_planche_ecretage.png"
        shutil.copy(cible, destination)
    return destination


def galerie_des_pannes() -> Path:
    """Une polaire par panne : la table en bleu, le modèle en orange."""
    module = module_factice()
    pannes = [None, *BUGS]
    with cfd_plot.style_context("paper"):
        figure, grille = cfd_plot.new_figure(2, 4, figsize=(15.0, 6.6))
        axes = grille.ravel()
        for ax, panne in zip(axes, pannes):
            rapport = valider_tables(module, TABLES, modele=ModeleFactice(module, bug=panne))
            resultat = rapport["CN"]
            table = resultat.cadre_table
            modele = resultat.cadre_modele
            masque = (table["alpha"] == ALPHA) & (table["delta"] == DELTA)

            cfd_plot.plot_line(
                ax,
                table.loc[masque, "mach"],
                table.loc[masque, "CN"],
                label="table",
                color="C0",
                marker="o",
            )
            cfd_plot.plot_line(
                ax,
                modele.loc[masque, "mach"],
                modele.loc[masque, "CN"],
                label="modèle",
                color="C1",
                marker="x",
                linestyle="--",
            )
            fautifs = points_fautifs(resultat)
            fautifs = fautifs[(fautifs["alpha"] == ALPHA) & (fautifs["delta"] == DELTA)]
            if not fautifs.empty:
                ax.scatter(
                    fautifs["mach"],
                    fautifs["_modele"],
                    s=70,
                    facecolors="none",
                    edgecolors=COULEUR_VERDICT[False],
                    linewidths=1.3,
                    zorder=5,
                )
            grandeur = resultat.grandeur("CN")
            motif = grandeur.motif_principal
            titre = "lecture juste" if panne is None else f"panne « {panne} »"
            verdict = "conforme" if motif is None else motif.nom.replace("_", " ")
            cfd_plot.set_title(ax, f"{titre}\n→ {verdict}")
            ax.set_xlabel("Mach")
            ax.set_ylabel("CN")
        cfd_plot.make_legend(axes[0])
        cfd_plot.set_suptitle(
            figure,
            f"Ce que chaque panne fait à la polaire  (incidence {ALPHA:g}°, braquage {DELTA:g}°)",
        )
        ecrits = cfd_plot.save_figure(figure, FIGURES / "02_galerie_des_pannes", formats=("png",))
    return Path(ecrits[0])


if __name__ == "__main__":
    FIGURES.mkdir(exist_ok=True)
    for chemin in (planche_ecretage(), galerie_des_pannes()):
        print(f"écrit : {chemin.relative_to(ICI.parent)}")
