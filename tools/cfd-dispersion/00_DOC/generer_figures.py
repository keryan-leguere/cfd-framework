#!/usr/bin/env python3
"""Génère les figures illustrant 00_DOC/ dans 00_DOC/FIGURES/.

    python 00_DOC/generer_figures.py

Les figures servent la documentation, pas le rapport : elles sont volontairement
autonomes du reste du paquet, à ceci près qu'elles emploient les mêmes
fonctions publiques que celles qu'elles illustrent.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from cfd_dispersion import (
    CONVENTIONS,
    LoiDispersion,
    bande_depuis_loi,
    charger_lois,
    tirer,
    tirer_tableau,
    valider_lot,
)
from cfd_dispersion.batch import hook_dispersion
from cfd_dispersion.figures._base import enregistrer, nouvelle_figure, style, tracer_ligne
from cfd_dispersion.figures.monte_carlo import figure_comparaison
from cfd_dispersion.figures.polaire import superposer_dispersion
from cfd_dispersion.figures.synthese import figure_synthese
from cfd_dispersion.figures.tirage import figure_tirage, tracer_loi

FIGURES = Path(__file__).resolve().parent / "FIGURES"
DPI = 130

#: La table de lois qui sert de fil rouge à toute la documentation.
TABLE = {
    "CN": {
        "Biais_Type": 5,
        "Biais_M": 0.0,
        "Biais_ET": 0.02,
        "FE_Type": 6,
        "FE_M": 1.0,
        "FE_ET": 0.08,
    },
    "CA": {
        "Biais_Type": 2,
        "Biais_M": 0.001,
        "Biais_ET": 0.0,
        "FE_Type": 3,
        "FE_M": 1.0,
        "FE_ET": 0.05,
    },
    "Cm_alpha": {
        "Biais_Type": 5,
        "Biais_M": 0.0,
        "Biais_ET": 0.015,
        "FE_Type": 4,
        "FE_M": 1.0,
        "FE_ET": 0.10,
    },
}


def _ecrire(figure: plt.Figure, nom: str) -> None:
    """Écrit une figure de doc, par le même chemin que les figures livrées.

    `enregistrer` passe par ``cfd_plot.save_figure`` : les illustrations de la
    documentation sortent donc au format du framework, comme celles que le
    paquet produit.
    """
    FIGURES.mkdir(parents=True, exist_ok=True)
    (chemin,) = enregistrer(figure, FIGURES / nom, formats=("png",), dpi=DPI)
    plt.close(figure)
    print(f"[ok] {chemin}")


# ---------------------------------------------------------------------------
# 01 — les six familles
# ---------------------------------------------------------------------------


def figure_types_de_lois() -> None:
    """Les six familles, à M et ET identiques."""
    with style():
        figure, grille = nouvelle_figure(2, 3, figsize=(12.0, 6.0))
        for type_loi, ax in zip(range(1, 7), np.ravel(grille)):
            loi = LoiDispersion(type_loi, M=0.0, ET=0.10)
            tracer_loi(ax, loi, couleur=f"C{type_loi - 1}")
            ax.set_title(f"{type_loi} — {loi.label}", fontsize=10)
            ax.set_xlim(-0.16, 0.16)
            ax.set_xlabel("valeur")
            support = (
                "dégénérée"
                if loi.est_degeneree
                else (f"support ±{loi.support()[1]:.3g}" if loi.est_bornee else "support non borné")
            )
            # De la place au-dessus de la courbe : sans cela l'annotation se
            # pose sur le sommet de la densité, là où elle gêne le plus.
            bas, haut = ax.get_ylim()
            ax.set_ylim(bas, haut * 1.30)
            ax.text(
                0.5,
                0.95,
                f"M = 0, ET = 0.10 · σ = {loi.ET_theorique:.4g}\n{support}",
                transform=ax.transAxes,
                ha="center",
                va="top",
                fontsize=7.5,
                color="0.35",
                bbox={
                    "boxstyle": "round",
                    "facecolor": "white",
                    "alpha": 0.85,
                    "edgecolor": "none",
                },
            )
        figure.suptitle(
            "Les six familles, aux mêmes M et ET — noter que σ n'est pas ET", fontsize=11
        )
    _ecrire(figure, "01_types_de_lois")


# ---------------------------------------------------------------------------
# 02 — ET n'est pas un écart-type
# ---------------------------------------------------------------------------


def figure_convention_et() -> None:
    """Le piège numéro un : lire ET comme un écart-type double la dispersion."""
    with style():
        figure, (gauche, droite) = nouvelle_figure(1, 2, figsize=(11.0, 4.0))

        juste = LoiDispersion(6, M=0.0, ET=0.10)  # σ = 0.05
        faux = LoiDispersion(6, M=0.0, ET=0.20)  # ET lu comme σ

        grille = np.linspace(-0.22, 0.22, 500)
        for ax in (gauche, droite):
            tracer_ligne(
                ax,
                grille,
                juste.pdf(grille),
                color="C0",
                marker="",
                label="ET = demi-étendue (correct)",
            )
            tracer_ligne(
                ax,
                grille,
                faux.pdf(grille),
                color="C3",
                ls="--",
                marker="",
                label="ET lu comme écart-type",
            )
            ax.set_xlabel("valeur")
            ax.set_ylabel("densité")
            ax.legend(fontsize=8)

        gauche.set_title("Deux fois plus large, et tout aussi crédible", fontsize=10)
        gauche.text(
            0.02,
            0.60,
            f"σ correct  = ET/2 = {juste.sigma_nominal:g}\n"
            f"σ si erreur = ET   = {faux.sigma_nominal:g}\n"
            f"support     ±{juste.support()[1]:g}  contre  ±{faux.support()[1]:g}",
            transform=gauche.transAxes,
            fontsize=8,
            va="top",
            bbox={"boxstyle": "round", "facecolor": "white", "edgecolor": "0.7"},
        )

        # Ce que la validation en dit.
        echantillon = faux.tirer(1000, graine=1)
        from cfd_dispersion import valider

        verdict = valider(echantillon, juste)
        droite.hist(
            echantillon, bins=50, density=True, color="C3", alpha=0.3, label="tirage fautif"
        )
        droite.set_title("Ce que la validation en dit", fontsize=10)
        droite.text(
            0.02,
            0.98,
            f"REJETÉ — motif : {verdict.motif}\n"
            f"hors support : {verdict.hors_support} / {verdict.n}\n"
            f"ET  {verdict.ET_empirique:.4g} / {verdict.ET_theorique:.4g}",
            transform=droite.transAxes,
            fontsize=8,
            va="top",
            color="#b2182b",
            bbox={"boxstyle": "round", "facecolor": "white", "edgecolor": "0.7"},
        )
        droite.legend(fontsize=8, loc="upper right")
    _ecrire(figure, "02_convention_ET")


# ---------------------------------------------------------------------------
# 03 — les trois conventions de reconstruction
# ---------------------------------------------------------------------------


def figure_conventions() -> None:
    """Les trois relations, sur le même biais et le même FE."""
    with style():
        figure, ax = nouvelle_figure(figsize=(7.5, 4.2))
        coefficient = np.linspace(0.0, 2.0, 100)
        biais, fe = 0.05, 1.08

        for indice, (nom, relation) in enumerate(CONVENTIONS.items()):
            valeur_fe = {"lineaire": fe, "pourcentage": 8.0, "relatif": 0.08}[nom]
            tracer_ligne(
                ax,
                coefficient,
                relation(coefficient, biais, valeur_fe),
                color=f"C{indice}",
                marker="",
                label=f"{nom} : {relation.formule}  (FE = {valeur_fe:g})",
            )
        tracer_ligne(
            ax, coefficient, coefficient, color="0.5", ls=":", marker="", label="non dispersé"
        )
        ax.set_xlabel("coefficient nominal")
        ax.set_ylabel("coefficient dispersé")
        ax.legend(fontsize=8, loc="upper left")
        ax.set_title(
            "Trois conventions, un même biais de 0.05 et une même échelle de +8 %", fontsize=10
        )
    _ecrire(figure, "03_conventions")


# ---------------------------------------------------------------------------
# 04 — le tirage, trois panneaux
# ---------------------------------------------------------------------------


def figure_tirage_trois_panneaux() -> None:
    lois = charger_lois(TABLE)
    tirage = tirer(lois, graine=42)
    rendue = figure_tirage("Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5)
    _ecrire(rendue.figure, "04_tirage_3_panneaux")


# ---------------------------------------------------------------------------
# 05 — loi prescrite contre loi réalisée
# ---------------------------------------------------------------------------


def figure_comparaison_mc() -> None:
    """Un cas conforme, puis le même coefficient mal tiré."""
    lois = charger_lois(TABLE)
    conforme = tirer_tableau(lois, 1000, graine=1)

    faux_table = {nom: dict(spec) for nom, spec in TABLE.items()}
    faux_table["Cm_alpha"]["FE_ET"] = 0.20
    fautif = tirer_tableau(charger_lois(faux_table), 1000, graine=1)

    for nom, lot in (("valide", conforme), ("rejete", fautif)):
        figure, _ = figure_comparaison(
            {"Biais": lot["Cm_alpha_Biais"], "FE": lot["Cm_alpha_FE"]},
            lois["Cm_alpha"],
            nominal=-2.5,
            pdv_label="M = 0.85, Z = 10 000 m",
        )
        _ecrire(figure, f"05_comparaison_{nom}")


# ---------------------------------------------------------------------------
# 06 — la synthèse
# ---------------------------------------------------------------------------


def figure_synthese_etude() -> None:
    """Quatre points de vol, dont un où le FE de Cm_alpha est mal tiré."""
    lois = charger_lois(TABLE)
    faux_table = {nom: dict(spec) for nom, spec in TABLE.items()}
    faux_table["Cm_alpha"]["FE_ET"] = 0.20
    fausses = charger_lois(faux_table)

    morceaux = []
    for indice, (mach, altitude) in enumerate(
        [(0.70, 5000.0), (0.80, 8000.0), (0.85, 10000.0), (0.90, 12000.0)]
    ):
        lot = tirer_tableau(fausses if indice == 2 else lois, 800, graine=indice)
        lot["Mach"] = mach
        lot["Altitude_m"] = altitude
        morceaux.append(lot)

    verdicts = valider_lot(pd.concat(morceaux, ignore_index=True), lois, par=("Mach", "Altitude_m"))
    figure, _ = figure_synthese(verdicts)
    _ecrire(figure, "06_synthese")


# ---------------------------------------------------------------------------
# 07 — la polaire dispersée
# ---------------------------------------------------------------------------


def _polaire() -> tuple[np.ndarray, np.ndarray]:
    alpha = np.linspace(0.0, 12.0, 25)
    return alpha, 0.11 * alpha + 0.0045 * alpha**2


def figure_polaire_dispersee() -> None:
    """La superposition complète, rattachée à une série existante."""
    lois = charger_lois(TABLE)
    alpha, CN = _polaire()

    lot = tirer_tableau(lois, 400, graine=7)
    nuage = np.array([b + f * CN for b, f in zip(lot["CN_Biais"], lot["CN_FE"])])

    with style():
        figure, ax = nouvelle_figure(figsize=(8.0, 5.2))
        tracer_ligne(ax, alpha, CN, label="CFD", color="C0")
        tracer_ligne(ax, alpha, 0.96 * CN, label="Essai", color="C1")
        superposer_dispersion(
            ax,
            alpha,
            CN,
            loi=lois["CN"],
            tirages=nuage,
            serie="CFD",
            n=6000,
            graine=1,
            label="CN",
        )
        ax.set_xlabel("incidence α (°)")
        ax.set_ylabel("$C_N$")
        ax.set_title("Dispersion de CN, rattachée à la série CFD", fontsize=10)
    _ecrire(figure, "07_polaire_dispersee")


# ---------------------------------------------------------------------------
# 08 — remplissages et lignes ±kσ
# ---------------------------------------------------------------------------


def figure_remplissages() -> None:
    """Les trois remplissages, et ce que chacun recouvre."""
    lois = charger_lois(TABLE)
    alpha, CN = _polaire()

    with style():
        figure, grille = nouvelle_figure(1, 3, figsize=(13.0, 4.0))
        for ax, remplissage in zip(np.ravel(grille), ("minmax", "percentile", "sigma")):
            tracer_ligne(ax, alpha, CN, label="CFD", color="C0")
            superposer_dispersion(
                ax,
                alpha,
                CN,
                loi=lois["CN"],
                serie="CFD",
                n=4000,
                graine=1,
                remplissage=remplissage,
                boite_parametres=False,
                sigmas=(1, 2, 3) if remplissage == "sigma" else (),
            )
            ax.set_xlabel("incidence α (°)")
            ax.set_ylabel("$C_N$")
            ax.set_title(f"remplissage = {remplissage!r}", fontsize=10)
        figure.suptitle(
            "min/max recouvre tout le nuage ; percentile en écarte les queues ; "
            "sigma suppose une forme",
            fontsize=10,
        )
    _ecrire(figure, "08_remplissages")


# ---------------------------------------------------------------------------
# 09 — corrélé ou indépendant
# ---------------------------------------------------------------------------


def figure_correle_ou_independant() -> None:
    """L'enveloppe est la même ; ce qu'il y a dedans, non."""
    lois = charger_lois(TABLE)
    alpha, CN = _polaire()

    with style():
        figure, grille = nouvelle_figure(1, 2, figsize=(11.0, 4.2))
        for ax, correle in zip(np.ravel(grille), (True, False)):
            bande = bande_depuis_loi(alpha, CN, loi=lois["CN"], n=4000, correle=correle, graine=3)
            for realisation in bande.echantillons[:40]:
                tracer_ligne(ax, alpha, realisation, color="C0", alpha=0.15, lw=0.6, marker="")
            tracer_ligne(ax, alpha, bande.bas, color="C0", lw=1.0, ls="--", marker="")
            tracer_ligne(ax, alpha, bande.haut, color="C0", lw=1.0, ls="--", marker="")
            tracer_ligne(ax, alpha, CN, color="0.2", lw=1.4, marker="", label="nominal")
            ax.set_xlabel("incidence α (°)")
            ax.set_ylabel("$C_N$")
            ax.set_title(
                "corrélé — une erreur par courbe"
                if correle
                else "indépendant — un bruit par point",
                fontsize=10,
            )
        figure.suptitle(
            "Deux enveloppes semblables ; seule celle de gauche se lit "
            "« la vraie courbe est là-dedans »",
            fontsize=10,
        )
    _ecrire(figure, "09_correle_ou_independant")


# ---------------------------------------------------------------------------
# 10 — deux coefficients issus du même recalage
# ---------------------------------------------------------------------------


def figure_correlation() -> None:
    """Nommer deux coefficients corrèle leurs composantes de même nature."""
    independantes = charger_lois(TABLE)
    liees = charger_lois(TABLE, correlation={("CN", "Cm_alpha"): 0.85})

    with style():
        figure, grille = nouvelle_figure(1, 2, figsize=(10.5, 4.4))
        for ax, jeu, nom in zip(
            np.ravel(grille), (independantes, liees), ("indépendants", "ρ = 0.85")
        ):
            lot = tirer_tableau(jeu, 1500, graine=5, methode="lhs")
            ax.scatter(lot["CN_Biais"], lot["Cm_alpha_Biais"], s=4, alpha=0.35, color="C0")
            mesure = float(np.corrcoef(lot["CN_Biais"], lot["Cm_alpha_Biais"])[0, 1])
            ax.set_xlabel("biais de CN")
            ax.set_ylabel("biais de Cm_alpha")
            ax.set_title(f"{nom} — corrélation mesurée {mesure:+.2f}", fontsize=10)
    _ecrire(figure, "10_correlation")


# ---------------------------------------------------------------------------
# 11 — la greffe sur batch_plot, telle qu'elle sort
# ---------------------------------------------------------------------------


def figure_batch_plot() -> None:
    """Une vraie sortie de ``batch_plot`` décorée par le hook.

    La figure n'est pas une imitation : elle est produite par ``batch_plot``
    avec ``on_before_save=hook_dispersion(...)``, puis renommée. Une
    illustration reconstituée à la main finirait par diverger de ce que la
    greffe produit vraiment.
    """
    from cfd_plot import batch_plot

    lois = charger_lois(TABLE)
    alpha, CN = _polaire()

    lot = tirer_tableau(lois, 300, graine=7)
    nuage = np.array([b + f * CN for b, f in zip(lot["CN_Biais"], lot["CN_FE"])])

    donnees = pd.DataFrame({"alpha": alpha, "Mach": 0.80, "Altitude_m": 8000.0, "CN": CN})
    temporaire = FIGURES / "_batch"
    ecrits = batch_plot(
        configuration_dict={
            "CFD": {"name": "CFD", "label": "CFD", "df": donnees, "color": "C0", "marker": "o"}
        },
        y_axis_dict={
            "CN": {
                "col_name": "CN",
                "literal_name": "Coefficient normal",
                "symbol": "$C_N$",
                "unit": "-",
                "y_save_name": "CN",
            }
        },
        sweep_dict={
            "alpha": {
                "col_name": "alpha",
                "literal_name": "Incidence",
                "symbol": r"$\alpha$",
                "unit": "°",
                "x_save_name": "alpha",
                "polar_prefix": "ALPHA_POLAR",
                "label": r"$\alpha$",
                "save_name": "ALPHA",
            }
        },
        flight_point_dict={
            "Mach": {"values": [0.80], "label": "M", "save_name": "M", "unit": "-"},
            "Altitude_m": {"values": [8000.0], "label": "Z", "save_name": "Z", "unit": "m"},
        },
        output_base=temporaire,
        style_profile="paper",
        formats=("png",),
        report=False,
        on_before_save=hook_dispersion(
            lois,
            serie="CFD",
            tirages={("CN", "alpha"): nuage},
            n=6000,
            graine=1,
            max_tirages=150,
        ),
    )

    cible = FIGURES / "11_batch_plot.png"
    shutil.copyfile(ecrits[0], cible)
    shutil.rmtree(temporaire, ignore_errors=True)
    print(f"[ok] {cible}")


def main() -> int:
    figure_types_de_lois()
    figure_convention_et()
    figure_conventions()
    figure_tirage_trois_panneaux()
    figure_comparaison_mc()
    figure_synthese_etude()
    figure_polaire_dispersee()
    figure_remplissages()
    figure_correle_ou_independant()
    figure_correlation()
    figure_batch_plot()
    return 0


if __name__ == "__main__":
    sys.exit(main())
