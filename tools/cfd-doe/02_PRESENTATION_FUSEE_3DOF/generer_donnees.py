"""Données FACTICES de la présentation : DOE réel, « CFD » inventée, tables carrées.

Ce que ferait l'étude réelle, la CFD remplacée par un modèle aéro analytique :

1. ``cfd-doe remplir`` construit le DOE (``SORTIE/DOE/doe.csv``, 344 calculs) ;
2. **la « CFD »** : chaque ligne du DOE reçoit CA, CN, Cm d'un modèle de fusée inventé
   (corps élancé + écoulement transverse + gouvernes en X), écrit comme le ferait un
   post-traitement (``SORTIE/RESULTATS/doe_resultats.csv``) ;
3. ``lire_mesures`` + ``reconstruire`` complètent la table par symétrie : une **table
   carrée** (Mach × α × DM) par coefficient, réunies dans ``DONNEES/tables_carrees.csv`` ;
4. la **table d'incrément** ΔzCA(Mach, altitude), semi-empirique (frottement turbulent,
   atmosphère standard de cfd-atm) : ``DONNEES/increment_dzca.csv`` ;
5. les figures qui ne viennent pas des tables (domaine de vol, convergence d'un calcul,
   précision des plans, pic transsonique manqué) vont dans ``PLANCHES/`` ; les chiffres
   du DOE dans ``DONNEES/chiffres_doe.json``.

Les tracés des tables sont faits ensuite par ``tracer_base_aero.py``, qui ne sait rien
de ce modèle : il ne lit que les deux DataFrames.

    python generer_donnees.py
"""

from __future__ import annotations

import json
import math
import shutil
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import cfd_plot
import numpy as np
import pandas as pd
from cfd_atm.core.altitudes import geopotential_from_geometric
from cfd_atm.core.isa import isa_density, isa_temperature
from cfd_atm.core.thermo import speed_of_sound, viscosity_sutherland

from cfd_doe.cli.main import main as cfd_doe
from cfd_doe.data.remplissage import charger_remplissage
from cfd_doe.engine.reconstruction import lire_mesures, reconstruire
from cfd_doe.engine.remplissage import remplir
from cfd_doe.paths import EXEMPLE_DIR

ICI = Path(__file__).resolve().parent
SORTIE = ICI / "SORTIE"
DONNEES = ICI / "DONNEES"
PLANCHES = ICI / "PLANCHES"
REMPLISSAGE = ICI / "REMPLISSAGE_3DOF.yaml"

# ---------------------------------------------------------------- géométrie factice
L, D = 1.80, 0.10  # m
XCG = 1.15  # m depuis le nez : point de réduction de Cm
SREF = math.pi * D**2 / 4
K_MOUILLE = (0.95 * math.pi * D * L + 4 * 2 * 0.012) / SREF  # Smouillée / Sréf ≈ 80,6


# ---------------------------------------------------------------- modèle aéro factice
def ca0(m: np.ndarray | float) -> np.ndarray:
    """CA à α = 0, DM = 0, z = 0 : subsonique, montée transsonique, lente décroissance."""
    m = np.asarray(m, float)
    return 0.45 + 0.38 / (1 + np.exp(-(m - 1.0) / 0.05)) - 0.08 * np.maximum(m - 1.1, 0)


def aero(m, alpha_deg, dm_deg):
    """CA, CN, Cm (Cm au CDG, longueur de référence D). DM > 0 → Cm < 0 (piqueur).

    Exactement symétrique : CA(−α, −DM) = CA, CN et Cm changent de signe.
    """
    m = np.asarray(m, float)
    a, d = np.radians(alpha_deg), np.radians(dm_deg)
    k_gouv = np.interp(m, [0.6, 0.9, 1.2, 1.5], [8.0, 9.2, 8.4, 6.8])  # /rad, réf. Sréf
    x_gouv = np.interp(m, [0.6, 0.9, 1.2, 1.5], [1.68, 1.69, 1.72, 1.73])  # m
    cn_lin = 2.0 * np.sin(a) * np.cos(a)  # corps élancé, Xcp vers l'ogive
    cn_tr = 0.65 * 1.2 * (4 * L / (math.pi * D)) * np.sin(a) * np.abs(np.sin(a))  # transverse
    x = a + 0.62 * d  # incidence locale des gouvernes
    cn_g = k_gouv * np.sin(x) * np.sqrt(np.abs(np.cos(x)))  # perte d'efficacité aux grands angles
    cn = cn_lin + cn_tr + cn_g
    cm = (cn_lin * (XCG - 0.30) + cn_tr * (XCG - 1.12) - cn_g * (x_gouv - XCG)) / D
    ca = ca0(m) * (1 - 0.35 * np.sin(a) ** 2) + 0.18 * d**2 + 0.06 * np.sin(a) * d
    return ca, cn, cm


# ---------------------------------------------------------------- ΔzCA semi-empirique
def reynolds(m, z):
    h = geopotential_from_geometric(z)
    t = isa_temperature(h)
    return isa_density(h) * m * speed_of_sound(t) * L / viscosity_sutherland(t)


def cf_turbulent(m, z):
    """Prandtl-Schlichting, corrigé de la compressibilité."""
    return 0.455 / np.log10(reynolds(m, z)) ** 2.58 / (1 + 0.144 * np.asarray(m) ** 2) ** 0.65


def dzca(m, z, z_ref: float = 0.0):
    """Écart de CA de frottement entre l'altitude z et celle des calculs CFD."""
    return K_MOUILLE * (cf_turbulent(m, z) - cf_turbulent(m, z_ref))


# ---------------------------------------------------------------- 1-4 : DOE → tables
def tables_et_increment() -> dict:
    SORTIE.mkdir(exist_ok=True)
    DONNEES.mkdir(exist_ok=True)
    if cfd_doe(["remplir", str(REMPLISSAGE), "--sortie", str(SORTIE / "DOE")]) != 0:
        sys.exit("cfd-doe remplir a échoué")
    doe = pd.read_csv(SORTIE / "DOE" / "doe.csv", sep="\t")

    # La « CFD » : une colonne par coefficient ajoutée au DOE, comme un post-traitement.
    doe["CA"], doe["CN"], doe["Cm"] = aero(doe["mach"], doe["alpha"], doe["DM"])
    (SORTIE / "RESULTATS").mkdir(exist_ok=True)
    chemin = SORTIE / "RESULTATS" / "doe_resultats.csv"
    doe.to_csv(chemin, sep="\t", index=False, float_format="%.17g")

    resultat = remplir(charger_remplissage(REMPLISSAGE), seulement=["complet"])
    contexte, plan = resultat.contexte, resultat.plan("complet")
    tables = reconstruire(plan, contexte, lire_mesures(chemin, contexte))
    if tables.trous:
        sys.exit(f"table trouée : {tables.notes}")
    grille = tables.grille.points()
    df = pd.DataFrame(grille, columns=list(tables.grille.colonnes))
    for coef, valeurs in tables.valeurs.items():
        df[coef] = valeurs
    df.to_csv(DONNEES / "tables_carrees.csv", sep="\t", index=False, float_format="%.12g")

    machs = np.round(np.arange(0.1, 1.5001, 0.05), 2)
    altitudes = np.arange(0.0, 2000.1, 250.0)
    mm, zz = np.meshgrid(machs, altitudes, indexing="ij")
    inc = pd.DataFrame({"mach": mm.ravel(), "altitude": zz.ravel(), "DZCA": dzca(mm, zz).ravel()})
    inc.to_csv(DONNEES / "increment_dzca.csv", sep="\t", index=False, float_format="%.6g")

    # Contrôle : la moitié déduite par symétrie est bien celle du modèle.
    vrai = aero(df["mach"], df["alpha"], df["DM"])
    ecart = max(float(np.max(np.abs(df[c] - v))) for c, v in zip(("CA", "CN", "Cm"), vrai))
    machs_doe = sorted(doe["mach"].unique())
    par_mach = int((doe["mach"] == machs_doe[0]).sum())
    a0 = int(((doe["mach"] == machs_doe[0]) & (doe["alpha"] == 0)).sum())
    return {
        "calculs": len(doe),
        "par_mach": par_mach,
        "plan_alpha0": a0,
        "general": par_mach - a0,
        "machs": machs_doe,
        "n_alpha_calc": int(doe.loc[doe["alpha"] > 0, "alpha"].nunique()),
        "n_dm": int(df["DM"].nunique()),
        "n_alpha_table": int(df["alpha"].nunique()),
        "noeuds_table": len(df),
        "ecart_symetrie": ecart,
    }


# ---------------------------------------------------------------- 5 : planches hors tables
def comparaison_plans() -> list[dict]:
    """Les plans du fichier de remplissage, rejoués par 01_EXEMPLE/reconstruire_tables.py."""
    sys.path.insert(0, str(EXEMPLE_DIR))
    import reconstruire_tables as rt

    bilans = rt.principal(
        [str(REMPLISSAGE), "--sortie", str(SORTIE / "RECONSTRUCTION"), "--tables", "aucun"]
    )
    shutil.copy(SORTIE / "RECONSTRUCTION" / "FIGURES" / "precision_cout.png", PLANCHES)
    return [
        {
            "plan": b.plan.nom,
            "calculs": b.calculs,
            "rms": b.pire,
            "max": b.pire_max,
            "verification": b.verification,
        }
        for b in bilans
    ]


def figure_domaine_vol() -> None:
    import matplotlib.pyplot as plt

    fig, ax = cfd_plot.new_figure(figsize=(6.4, 3.9))
    mm, zz = np.meshgrid(np.linspace(0.02, 1.5, 200), np.linspace(0, 2000, 120))
    cs = ax.contour(
        mm, zz, reynolds(mm, zz) / 1e6, levels=[2, 5, 10, 20, 40], colors="#9AA8B1", linewidths=1
    )
    ax.clabel(cs, fmt=lambda v: f"Re = {v:g} M", fontsize=9)
    ax.add_patch(plt.Rectangle((0, 0), 1.5, 2000, fill=False, ec="#0B3C5D", lw=2.5))
    ax.add_patch(plt.Rectangle((0, 0), 0.6, 2000, color="#E8EEF2", zorder=0))
    for m in (0.6, 0.9, 1.2, 1.5):
        ax.plot([m, m], [0, 2000], color="#E07A1F", lw=2.2)
        ax.text(
            m,
            2040,
            f"M = {m:.1f}".replace(".", ","),
            ha="center",
            va="bottom",
            color="#C0620F",
            fontsize=10,
        )
    ax.text(
        0.3,
        1700,
        "M < 0,6 :\ntable saturée\n(incompressible)",
        ha="center",
        va="center",
        fontsize=11,
        color="#3F5563",
    )
    ax.plot([0, 1.5], [0, 0], color="#0B3C5D", lw=4)
    ax.text(1.48, 80, "altitude de référence CFD (0 m)", ha="right", fontsize=10, color="#0B3C5D")
    ax.set_xlim(-0.03, 1.58)
    ax.set_ylim(-60, 2200)
    ax.set_xlabel("Mach")
    ax.set_ylabel("Altitude (m)")
    ax.grid(False)
    cfd_plot.save_figure(fig, PLANCHES / "domaine_vol", formats=("png",))


def figure_convergence() -> None:
    """Historique inventé d'un calcul (Mach 0,9, α = 20°, DM = 0)."""
    rng = np.random.default_rng(3)
    it = np.arange(3001)
    fig, axs = cfd_plot.new_figure(1, 2, figsize=(8.6, 3.0))
    couleurs = ["#0B3C5D", "#3F7E9E", "#E07A1F", "#7F8C8D"]
    noms = ["continuité", "quantité de mvt", "énergie", "k–ω"]
    for nom, c, k0, plancher in zip(
        noms, couleurs, (1.0, 0.6, 0.8, 0.5), (2e-6, 6e-7, 1.5e-6, 3e-6)
    ):
        r = (k0 * np.exp(-it / 240) + plancher) * np.exp(0.12 * rng.standard_normal(it.size))
        axs[0].semilogy(it, r, color=c, lw=0.9, label=nom)
    axs[0].axhline(1e-5, color="k", lw=0.6, ls=":")
    axs[0].set_xlabel("itération")
    axs[0].set_ylabel("résidu normalisé")
    cfd_plot.make_legend(axs[0], fontsize=8)
    _, cn20, cm20 = aero(0.9, 20.0, 0.0)
    for val, c, nom, phase in ((cn20, "#0B3C5D", "CN", 0.0), (cm20, "#E07A1F", "Cm", 1.3)):
        h = val * (1 - 0.6 * np.exp(-it / 260) * np.cos(it / 70 + phase))
        h = h + 0.004 * abs(val) * rng.standard_normal(it.size) * np.exp(-it / 800)
        axs[1].plot(it, h / val, color=c, lw=1.0, label=nom)
    axs[1].axhspan(0.995, 1.005, color="#DFF0D8", zorder=0)
    axs[1].axvspan(2500, 3000, color="#EEEEEE", zorder=0)
    axs[1].text(2520, 1.25, "moyenne\nsur 500 it.", fontsize=8, color="#7F8C8D")
    axs[1].set_ylim(0.4, 1.4)
    axs[1].set_xlabel("itération")
    axs[1].set_ylabel("coefficient / valeur finale")
    cfd_plot.make_legend(axs[1], loc="lower right")
    cfd_plot.save_figure(fig, PLANCHES / "convergence", formats=("png",))


def figure_pic_transsonique(tables: pd.DataFrame) -> float:
    """Ce que la table voit du CA(M) avec 4 Mach, contre le comportement du modèle."""
    noeuds = tables[(tables["alpha"] == 0) & (tables["DM"] == 0)].sort_values("mach")
    fig, ax = cfd_plot.new_figure(figsize=(5.6, 3.4))
    mf = np.linspace(0.6, 1.5, 200)
    ax.plot(mf, ca0(mf), color="#7F8C8D", lw=1.4, ls="--", label="comportement attendu (factice)")
    ax.plot(
        noeuds["mach"],
        noeuds["CA"],
        "-",
        color="#0B3C5D",
        lw=1.8,
        label="table : interpolation linéaire",
    )
    ax.plot(noeuds["mach"], noeuds["CA"], "o", color="#E07A1F", ms=7, label="calculs CFD", zorder=5)
    ax.plot(
        [1.05],
        [ca0(1.05)],
        "D",
        mfc="white",
        mec="#E07A1F",
        mew=1.6,
        ms=7,
        label="Mach 1,05 proposé",
        zorder=6,
    )
    lu = float(np.interp(1.05, noeuds["mach"], noeuds["CA"]))
    ecart = float(ca0(1.05)) - lu
    ax.annotate(
        f"écart de la table à M = 1,05 : {ecart:.2f}".replace(".", ","),
        xy=(1.05, lu),
        xytext=(1.1, 0.5),
        fontsize=8,
        color="#0B3C5D",
        arrowprops={"arrowstyle": "->", "color": "#0B3C5D", "lw": 0.8},
    )
    ax.set_xlabel("Mach")
    ax.set_ylabel("CA à α = 0, DM = 0 (z = 0 m)")
    cfd_plot.make_legend(ax, loc="upper left", fontsize=8)
    cfd_plot.save_figure(fig, PLANCHES / "CA_pic_transsonique", formats=("png",))
    return ecart


def main() -> None:
    PLANCHES.mkdir(exist_ok=True)
    cfd_plot.use_style("paper")
    chiffres = tables_et_increment()
    shutil.copy(SORTIE / "DOE" / "FIGURES" / "domaine.png", PLANCHES / "domaine.png")
    figure_domaine_vol()
    figure_convergence()
    tables = pd.read_csv(DONNEES / "tables_carrees.csv", sep="\t")
    chiffres["ecart_CA_M105"] = figure_pic_transsonique(tables)
    chiffres["ca0_m105"] = float(ca0(1.05))
    chiffres["plans"] = comparaison_plans()
    chiffres["dzca_table"] = {
        str(m): [float(dzca(m, z)) for z in (0, 500, 1000, 1500, 2000)]
        for m in (0.6, 0.9, 1.2, 1.5)
    }
    chiffres["ca_frottement_z0"] = {
        str(m): float(K_MOUILLE * cf_turbulent(m, 0.0)) for m in (0.6, 0.9, 1.2, 1.5)
    }
    chiffres["k_mouille"] = K_MOUILLE
    (DONNEES / "chiffres_doe.json").write_text(json.dumps(chiffres, indent=2, ensure_ascii=False))
    print(
        f"{chiffres['calculs']} calculs · table {chiffres['noeuds_table']} nœuds · "
        f"écart symétrie {chiffres['ecart_symetrie']:.1e}"
    )


if __name__ == "__main__":
    main()
