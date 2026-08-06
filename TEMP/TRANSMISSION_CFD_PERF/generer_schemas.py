#!/usr/bin/env python3
"""Génère les schémas propres au document de transmission de connaissance.

    python generer_schemas.py

Écrit dans ``FIGURES/`` (06 à 09). Les figures 01 à 05 sont celles de la
documentation du paquet ; elles sont produites par
``tools/cfd-perf/00_DOC/generer_figures.py`` et recopiées ici.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

SORTIE = Path(__file__).resolve().parent / "FIGURES"

BLEU = "#0B6FA4"
BLEU_CLAIR = "#E3EEF5"
ROUGE = "#D1495B"
ROUGE_CLAIR = "#F8E7EA"
VERT = "#1B998B"
VERT_CLAIR = "#E2F2F0"
ORANGE = "#E8871E"
ORANGE_CLAIR = "#FCEEDC"
GRIS = "#5B6770"
GRIS_CLAIR = "#EFF1F3"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.15,
    }
)


def boite(ax, x, y, w, h, texte, *, bord, fond, titre=None, fs=8.5, fs_titre=9.5,
          align="center", rayon=0.012):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle=f"round,pad=0,rounding_size={rayon}",
            linewidth=1.4, edgecolor=bord, facecolor=fond, zorder=2,
        )
    )
    xt = x + w / 2 if align == "center" else x + 0.012
    ha = "center" if align == "center" else "left"
    if titre is not None:
        ax.text(xt, y + h - 0.030, titre, ha=ha, va="top", fontsize=fs_titre,
                fontweight="bold", color=bord, zorder=3)
        ax.text(xt, y + h - 0.030 - 0.042, texte, ha=ha, va="top", fontsize=fs,
                color="#22282C", zorder=3, linespacing=1.5)
    else:
        ax.text(xt, y + h / 2, texte, ha=ha, va="center", fontsize=fs,
                color="#22282C", zorder=3, linespacing=1.5)


def fleche(ax, xy_a, xy_b, *, couleur=GRIS, lw=1.6, style="-|>", rad=0.0):
    ax.add_patch(
        FancyArrowPatch(
            xy_a, xy_b, arrowstyle=style, mutation_scale=13,
            linewidth=lw, color=couleur, zorder=4,
            connectionstyle=f"arc3,rad={rad}",
        )
    )


def cadre_nu(figsize):
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


# --------------------------------------------------------------------------
def s1_entrees_sorties() -> None:
    fig, ax = cadre_nu((11.5, 6.2))

    ax.text(0.005, 0.985, "Entrées et sorties de la chaîne de dimensionnement",
            fontsize=14, fontweight="bold", color="#22282C", va="top")

    ax.text(0.115, 0.905, "ENTRÉES", ha="center", fontsize=10.5,
            fontweight="bold", color=GRIS)
    ax.text(0.50, 0.905, "TRAITEMENT", ha="center", fontsize=10.5,
            fontweight="bold", color=BLEU)
    ax.text(0.875, 0.905, "SORTIES", ha="center", fontsize=10.5,
            fontweight="bold", color=VERT)

    entrees = [
        ("Cas prêt à lancer",
         "maillage, conditions aux limites,\nréglages du solveur"),
        ("Mesures pilotes",
         "la seule donnée réelle : 4 à 6 nombres de\ncœurs, temps / itération, RAM crête totale"),
        ("Machine",
         "cœurs par nœud, RAM par nœud,\nnb max de nœuds, walltime max"),
        ("Contraintes et objectif",
         "mailles/cœur mini, budget h·cœur,\nstratégie, échéance"),
    ]
    h = 0.165
    y0 = 0.715
    for i, (titre, corps) in enumerate(entrees):
        y = y0 - i * (h + 0.032)
        boite(ax, 0.010, y, 0.290, h, corps, bord=GRIS, fond=GRIS_CLAIR,
              titre=titre, align="left", fs=8.2, fs_titre=9.0)
        fleche(ax, (0.302, y + h / 2), (0.352, y + h / 2))

    boite(ax, 0.355, 0.115, 0.290, 0.765, "", bord=BLEU, fond=BLEU_CLAIR)
    ax.text(0.500, 0.845, "cfd-perf", ha="center", va="top", fontsize=13,
            fontweight="bold", color=BLEU, zorder=3)
    etapes_int = [
        ("1", "Ajustement du modèle",
         r"$T(N_c)=t_{ser}+t_{par}/N_c+t_{comm}N_c^{\gamma}$"),
        ("2", "Contrôle de la qualité", "erreur max, R², point par point"),
        ("3", "Balayage des candidats", "durée, coût, efficacité, mémoire"),
        ("4", "Filtrage des contraintes", "mailles/cœur, RAM, nœuds, durée"),
        ("5", "Choix selon la stratégie", "efficacité / échéance / rapidité"),
    ]
    yb = 0.760
    for num, titre, detail in etapes_int:
        ax.add_patch(plt.Circle((0.393, yb - 0.032), 0.0145, color=BLEU, zorder=5))
        ax.text(0.393, yb - 0.032, num, ha="center", va="center", fontsize=7.5,
                color="white", fontweight="bold", zorder=6)
        ax.text(0.418, yb - 0.020, titre, ha="left", va="top", fontsize=9,
                fontweight="bold", color="#22282C", zorder=3)
        ax.text(0.418, yb - 0.058, detail, ha="left", va="top", fontsize=7.8,
                color=GRIS, zorder=3)
        yb -= 0.128

    sorties = [
        ("Réponse",
         "nombre de cœurs recommandé,\narrondi aux nœuds entiers"),
        ("Chiffres de décision",
         "durée, coût h·cœur, accélération,\nefficacité, mailles/cœur, Go/cœur"),
        ("Alternatives et réserves",
         "le plus rapide / le moins cher,\nextrapolation, qualité de l'ajustement"),
        ("Traces réutilisables",
         "ETUDE.yaml validé, figure PNG,\nrapport, code de sortie 0/1/2/3"),
    ]
    for i, (titre, corps) in enumerate(sorties):
        y = y0 - i * (h + 0.032)
        fleche(ax, (0.648, y + h / 2), (0.698, y + h / 2), couleur=VERT)
        boite(ax, 0.700, y, 0.290, h, corps, bord=VERT, fond=VERT_CLAIR,
              titre=titre, align="left", fs=8.2, fs_titre=9.0)

    ax.text(0.005, 0.045,
            "La qualité de la réponse est bornée par celle du pilote : "
            "tout le reste en découle.",
            fontsize=8.5, style="italic", color=GRIS)

    fig.savefig(SORTIE / "06_entrees_sorties.png")
    plt.close(fig)


# --------------------------------------------------------------------------
def s2_etapes() -> None:
    fig, ax = cadre_nu((11.5, 8.6))

    ax.text(0.005, 0.988, "Les grandes étapes, de la préparation à l'archivage",
            fontsize=14, fontweight="bold", color="#22282C", va="top")

    etapes = [
        ("ÉTAPE 0", "Préparer et vérifier",
         "Cas qui tourne déjà. Adaptateur disponible\n"
         "(OF.sh, mock.sh…), machine renseignée.",
         "source ADAPTATEUR/OF.sh && adapt_verifier_installation",
         "cas validé", BLEU),
        ("ÉTAPE 1", "Soumettre le pilote",
         "Un run court par nombre de cœurs, sur le VRAI cas.\n"
         "4 à 6 points couvrant un facteur ≥ 4.",
         'cfd-perf capture --coeurs "48 96 192 384 768"',
         "PILOTE/ + manifest.json", BLEU),
        ("ÉTAPE 2", "Collecter et écrire",
         "Temps/itération, itérations, RAM crête (MaxRSS×NTasks).\n"
         "Machine détectée automatiquement.",
         "cfd-perf capture --collect",
         "ETUDE.yaml validé", VERT),
        ("ÉTAPE 3", "Ajuster et contrôler",
         "Balayage de γ, moindres carrés pondérés en relatif.\n"  # noqa: RUF001
         "Erreur max, R², écart point par point.",
         "cfd-perf check ETUDE.yaml",
         "verdict de qualité", VERT),
        ("ÉTAPE 4", "Décider",
         "Candidats filtrés par les contraintes, puis stratégie :\n"
         "efficacité (défaut) / échéance / le plus rapide.",
         "cfd-perf run ETUDE.yaml --strategy efficiency",
         "nombre de cœurs + nœuds", ORANGE),
        ("ÉTAPE 5", "Documenter",
         "Rapport ordonné : réponse, réserves, alternatives,\n"
         "justification. Figure de scalabilité.",
         "cfd-perf run ETUDE.yaml --figure SORTIE/scal.png -v",
         "rapport + figure PNG", ORANGE),
        ("ÉTAPE 6", "Archiver",
         "ETUDE.yaml + manifeste + figure + rapport, versionnés\n"
         "à côté du cas. Un pilote par machine.",
         "git add ETUDE.yaml SORTIE/  •  cfd-archiver",
         "étude rejouable", ROUGE),
    ]

    h = 0.104
    ecart = 0.021
    ecart_file = 0.056          # gap élargi : l'attente en file s'y insère
    y = 0.830
    x_num, x_boite, w_boite = 0.008, 0.185, 0.520
    x_art = 0.730

    for i, (num, titre, corps, cmd, artefact, couleur) in enumerate(etapes):
        clair = {BLEU: BLEU_CLAIR, VERT: VERT_CLAIR, ORANGE: ORANGE_CLAIR,
                 ROUGE: ROUGE_CLAIR}[couleur]

        ax.text(x_num, y + h / 2 + 0.011, num, ha="left", va="center",
                fontsize=11, fontweight="bold", color=couleur)
        ax.text(x_num, y + h / 2 - 0.019, titre, ha="left", va="center",
                fontsize=8.6, color=GRIS)

        boite(ax, x_boite, y, w_boite, h, "", bord=couleur, fond=clair)
        ax.text(x_boite + 0.016, y + h - 0.017, corps, ha="left", va="top",
                fontsize=8.6, color="#22282C", zorder=3, linespacing=1.45)
        ax.text(x_boite + 0.016, y + 0.015, "$ " + cmd, ha="left", va="bottom",
                fontsize=8.0, family="DejaVu Sans Mono", color=couleur, zorder=3)

        fleche(ax, (x_boite + w_boite + 0.008, y + h / 2), (x_art - 0.008,
               y + h / 2), couleur=couleur, lw=1.2)
        ax.text(x_art, y + h / 2, artefact, ha="left", va="center",
                fontsize=8.4, color=couleur, fontweight="bold")

        gap = ecart_file if i == 1 else ecart
        if i < len(etapes) - 1:
            fleche(ax, (x_boite + 0.048, y - 0.003),
                   (x_boite + 0.048, y - gap + 0.003), couleur=GRIS, lw=1.4)
        if i == 1:
            y_att = y - gap / 2
            ax.add_patch(
                FancyBboxPatch(
                    (x_boite + 0.075, y_att - 0.015), 0.330, 0.030,
                    boxstyle="round,pad=0,rounding_size=0.015",
                    linewidth=1.0, edgecolor=GRIS, facecolor="white",
                    linestyle=(0, (4, 3)), zorder=5,
                )
            )
            ax.text(x_boite + 0.240, y_att,
                    "les jobs attendent en file  —  on rend la main",
                    ha="center", va="center", fontsize=8.0, style="italic",
                    color=GRIS, zorder=6)
        y -= h + gap

    ax.text(0.005, 0.018,
            "Les étapes 0 à 2 se font une fois par cas ET par machine ; "
            "les étapes 3 à 5 se rejouent à volonté sur le même ETUDE.yaml.",
            fontsize=8.5, style="italic", color=GRIS)

    fig.savefig(SORTIE / "07_etapes.png")
    plt.close(fig)


# --------------------------------------------------------------------------
def s3_archivage() -> None:
    fig, ax = cadre_nu((11.5, 6.0))

    ax.text(0.005, 0.985, "Ce que produit la chaîne, et ce qu'il faut archiver",
            fontsize=14, fontweight="bold", color="#22282C", va="top")

    lignes = [
        ("CAS_AILE_M6/", 0, "dossier", None),
        ("├── 01_MAILLAGE/  02_PARAMS/  …", 1, "cas", None),
        ("├── PILOTE/", 1, "dossier", None),
        ("│   ├── manifest.json", 2, "garder", "relie soumission et collecte"),
        ("│   ├── OF_48_20260805_101200/", 2, "run", None),
        ("│   │   └── LOG/  .metadata.yaml", 3, "run", "run pilote : log brut"),
        ("│   ├── OF_96_20260805_101204/", 2, "run", None),
        ("│   └── OF_192_20260805_101208/", 2, "run", None),
        ("├── ETUDE.yaml", 1, "garder", "l'entrée rejouable"),
        ("└── SORTIE/", 1, "dossier", None),
        ("    ├── scalabilite.png", 2, "garder", "figure du rapport"),
        ("    └── rapport.txt", 2, "garder", "réponse + justification datée"),
    ]

    x0, y0, dy = 0.030, 0.845, 0.0545
    for i, (texte, _prof, genre, note) in enumerate(lignes):
        y = y0 - i * dy
        couleur = {"garder": VERT, "run": GRIS, "cas": GRIS,
                   "dossier": "#22282C"}[genre]
        gras = "bold" if genre in ("garder", "dossier") else "normal"
        if genre == "garder":
            ax.add_patch(
                FancyBboxPatch(
                    (x0 - 0.010, y - 0.019), 0.400, 0.038,
                    boxstyle="round,pad=0,rounding_size=0.010",
                    linewidth=0, facecolor=VERT_CLAIR, zorder=1,
                )
            )
        ax.text(x0, y, texte, ha="left", va="center", fontsize=9.6,
                family="DejaVu Sans Mono", color=couleur, fontweight=gras,
                zorder=3)
        if note:
            ax.text(0.410, y, "◂ " + note, ha="left", va="center", fontsize=8.4,
                    color=couleur if genre == "garder" else GRIS,
                    style="italic", zorder=3)

    boite(ax, 0.700, 0.100, 0.295, 0.700, "", bord=BLEU, fond=BLEU_CLAIR)
    ax.text(0.847, 0.770, "Règle d'archivage", ha="center", va="top",
            fontsize=10.5, fontweight="bold", color=BLEU)
    ax.text(
        0.720, 0.700,
        "Le minimum rejouable tient\nen trois fichiers :\n\n"
        "   •  ETUDE.yaml\n"
        "   •  la figure\n"
        "   •  le rapport daté\n\n"
        "Les répertoires PILOTE/ sont\nvolumineux : on les archive\n"
        "avec le cas (cfd-archiver),\npas dans le dépôt.\n\n"
        "γ n'est pas transposable :\nune étude archivée vaut\npour UN cas sur UNE machine.",  # noqa: RUF001
        ha="left", va="top", fontsize=8.6, color="#22282C", linespacing=1.5)

    fig.savefig(SORTIE / "08_archivage.png")
    plt.close(fig)


# --------------------------------------------------------------------------
def s4_validation() -> None:
    fig, ax = cadre_nu((11.5, 5.0))

    ax.text(0.005, 0.985, "Comment on vérifie que l'outil fait ce qu'il annonce",
            fontsize=14, fontweight="bold", color="#22282C", va="top")

    niveaux = [
        ("NIVEAU 3", "Cas de la base de validation OpenFOAM",
         "Le vrai solveur, des cas de référence connus : on vérifie que la chaîne\n"
         "complète (soumission → collecte → recommandation) fonctionne de bout en\n"
         "bout et que les temps mesurés se comportent comme le modèle le prédit.",
         "chaîne réelle", ROUGE, ROUGE_CLAIR, 0.100, 0.800),
        ("NIVEAU 2", "Tests bout-en-bout de la ligne de commande",
         "Adaptateur mock : soumission et collecte enchaînées sans solveur ni SLURM.\n"
         "Vérifie les commandes, les surcharges, les codes de sortie et les messages.",
         "sans solveur", ORANGE, ORANGE_CLAIR, 0.062, 0.876),
        ("NIVEAU 1", "Tests unitaires du cœur de calcul",
         "Ajustement, contraintes, stratégies, lecture/écriture YAML, détection\n"
         "machine. 183 tests, exécutés à chaque modification (pytest, ruff, mypy).",
         "déterministe", VERT, VERT_CLAIR, 0.025, 0.950),
    ]

    y = 0.645
    h = 0.230
    for titre, nom, corps, etiquette, couleur, clair, marge, largeur in niveaux:
        boite(ax, marge, y, largeur, h, "", bord=couleur, fond=clair)
        ax.text(marge + 0.018, y + h - 0.030, titre, ha="left", va="top",
                fontsize=9.0, fontweight="bold", color=couleur)
        ax.text(marge + 0.100, y + h - 0.030, nom, ha="left", va="top",
                fontsize=10.0, fontweight="bold", color="#22282C")
        ax.text(marge + 0.018, y + h - 0.078, corps, ha="left", va="top",
                fontsize=8.5, color="#22282C", linespacing=1.5)
        ax.text(marge + largeur - 0.018, y + h - 0.030, etiquette, ha="right",
                va="top", fontsize=8.2, color=couleur, style="italic")
        y -= h + 0.040

    ax.annotate("", xy=(0.012, 0.890), xytext=(0.012, 0.075),
                arrowprops=dict(arrowstyle="-|>", color=GRIS, linewidth=1.6))
    ax.text(0.004, 0.480, "réalisme croissant", rotation=90, ha="center",
            va="center", fontsize=8.5, color=GRIS)

    ax.text(0.005, 0.020,
            "Les trois niveaux sont complémentaires : le niveau 1 protège les "
            "formules, le niveau 2 l'ergonomie, le niveau 3 l'accord avec le "
            "solveur réel.",
            fontsize=8.5, style="italic", color=GRIS)

    fig.savefig(SORTIE / "09_validation.png")
    plt.close(fig)


if __name__ == "__main__":
    s1_entrees_sorties()
    s2_etapes()
    s3_archivage()
    s4_validation()
    for f in sorted(SORTIE.glob("0[6-9]_*.png")):
        print(f.name, f.stat().st_size // 1024, "ko")
