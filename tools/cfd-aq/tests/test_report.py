"""Terminal report and figures."""

from __future__ import annotations

import importlib
import io
import os
from collections.abc import Callable
from pathlib import Path

import matplotlib.pyplot as plt
import pytest
from matplotlib.figure import Figure
from rich.console import Console

from cfd_aq.core.couche_limite import CoucheLimite, EtatLocal
from cfd_aq.core.marches import TypeAsperite, verifier_domaine
from cfd_aq.core.trainee import Asperite, calculer_trainee
from cfd_aq.report import console as rapport
from cfd_aq.report import figures, theme


def _console() -> tuple[Console, io.StringIO]:
    """A Console writing into a buffer, so the report can be read back."""
    tampon = io.StringIO()
    return Console(file=tampon, width=100, force_terminal=False), tampon


def test_rapport_complet_mentionne_la_reponse(
    etat_croisiere: EtatLocal, couche_croisiere: CoucheLimite
) -> None:
    console, tampon = _console()
    asperite = Asperite(TypeAsperite.ARETE, 1e-3, 2.0, t_sur_h=2.0, angle_derapage=70.0)
    resultat = calculer_trainee(asperite, etat_croisiere, couche_croisiere, 100.0)

    rapport.afficher_ecoulement(console, etat_croisiere)
    rapport.afficher_couche_limite(console, couche_croisiere)
    rapport.afficher_asperite(console, "Test", asperite, resultat)
    rapport.afficher_bilan(console, [("Test", resultat)], 100.0)

    texte = tampon.getvalue()
    for attendu in (
        "q_e",
        "C_fe",
        "u_τ",
        "h⁺",
        "CDe/Cfe",
        "forme",
        "ΔD",
        "ΔCx",
        "Total",
        "t/h",
    ):
        assert attendu in texte, attendu


def test_le_facteur_de_forme_nomme_ses_causes(
    etat_croisiere: EtatLocal, couche_croisiere: CoucheLimite
) -> None:
    console, tampon = _console()
    asperite = Asperite(TypeAsperite.MONTANTE, 1e-3, 2.0, angle_chanfrein=30.0)
    resultat = calculer_trainee(asperite, etat_croisiere, couche_croisiere)
    rapport.afficher_asperite(console, "Chanfreinée", asperite, resultat)
    assert "θ = 30" in tampon.getvalue()


def test_avertissements_affiches() -> None:
    console, tampon = _console()
    rapport.afficher_avertissements(console, verifier_domaine(TypeAsperite.MONTANTE, 5000.0, 0.8))
    texte = tampon.getvalue()
    assert "Hors du domaine" in texte
    assert "extrapolée" in texte


def test_pas_de_panneau_sans_avertissement() -> None:
    console, tampon = _console()
    rapport.afficher_avertissements(console, [])
    assert tampon.getvalue() == ""


def test_bilan_vide_n_affiche_rien() -> None:
    console, tampon = _console()
    rapport.afficher_bilan(console, [])
    assert tampon.getvalue() == ""


# --- thème ----------------------------------------------------------------


def test_le_gras_est_absent_par_defaut(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bold is rendered as a bright colour by many terminals; see theme.py."""
    monkeypatch.delenv(theme.ENV_GRAS, raising=False)
    recharge = importlib.reload(theme)
    assert not recharge.gras_actif()
    assert "bold" not in recharge.TITRE
    assert "bold" not in recharge.ACCENT


def test_la_variable_d_environnement_retablit_le_gras(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(theme.ENV_GRAS, "1")
    recharge = importlib.reload(theme)
    assert recharge.gras_actif()
    assert recharge.TITRE.startswith("bold ")
    monkeypatch.delenv(theme.ENV_GRAS, raising=False)
    importlib.reload(theme)


def test_le_theme_laisse_le_discret_sans_gras() -> None:
    assert theme.DISCRET == "dim"
    assert os.environ.get(theme.ENV_GRAS) is None


# --- figures --------------------------------------------------------------


def test_la_ligne_de_provenance_nomme_les_paquets_freres() -> None:
    """The same command has different capabilities on two machines; say which."""
    console, tampon = _console()
    rapport.afficher_paquets(console)
    texte = tampon.getvalue()
    assert "atmosphère" in texte
    assert "figures" in texte
    assert ("cfd-atm" in texte) or ("repli" in texte)


@pytest.mark.parametrize(
    ("fabrique", "nom"),
    [
        (figures.tracer_geometries, "geometries.png"),
        (figures.tracer_rapports, "rapports.png"),
        (figures.tracer_effet_mach, "mach.png"),
        (figures.tracer_corrections, "corrections.png"),
    ],
)
def test_les_figures_s_ecrivent(tmp_path: Path, fabrique: Callable[[], Figure], nom: str) -> None:
    chemin = figures.enregistrer(fabrique(), tmp_path / "sous" / nom)
    assert chemin.exists()
    assert chemin.stat().st_size > 10_000


def test_la_figure_mach_porte_les_trois_formes_et_la_somme() -> None:
    figure = figures.tracer_effet_mach(500.0)
    axe = figure.axes[0]
    etiquettes = [ligne.get_label() for ligne in axe.lines]
    assert "Marche montante" in etiquettes
    assert "Marche descendante" in etiquettes
    assert "Arête carrée" in etiquettes
    assert "Somme des deux marches" in etiquettes
    plt.close(figure)


def test_la_sortie_graphique_se_nomme() -> None:
    assert figures.sortie_graphique() in ("cfd-plot", "matplotlib")


def test_la_figure_des_geometries_a_six_panneaux() -> None:
    """Three shapes on top, three corrections below."""
    figure = figures.tracer_geometries()
    assert len(figure.axes) == 6
    titres = " ".join(axe.get_title() for axe in figure.axes)
    for attendu in (
        "Marche montante",
        "Marche descendante",
        "Arête",
        "Arrondi",
        "Chanfrein",
        "Dérapage",
    ):
        assert attendu in titres, attendu
    plt.close(figure)


def test_la_figure_rapports_a_un_panneau_par_forme() -> None:
    figure = figures.tracer_rapports((0.2, 0.8))
    assert len(figure.axes) == 3
    titres = [axe.get_title() for axe in figure.axes]
    assert titres == ["Marche montante", "Marche descendante", "Arête carrée (t = h)"]
    plt.close(figure)


def test_assez_de_couleurs_pour_toutes_les_familles() -> None:
    """Every Mach curve of every family must get its own colour.

    ``zip`` is silent when the colour list runs short: the last curves would
    simply vanish from the figure, and nothing would say so.
    """
    from cfd_aq.core import donnees

    familles = (
        donnees.MARCHE_MONTANTE,
        donnees.MARCHE_DESCENDANTE,
        donnees.ARETE_CARREE,
        donnees.ARRONDI_MONTANTE,
        donnees.CHANFREIN_MONTANTE,
        donnees.CHANFREIN_DESCENDANTE,
    )
    assert len(figures._COULEURS) >= max(len(famille) for famille in familles)


def test_la_planche_des_corrections_montre_tous_les_mach() -> None:
    from cfd_aq.core import donnees

    figure = figures.tracer_corrections()
    axe_chanfrein_aval = figure.axes[2]
    assert len(axe_chanfrein_aval.lines) >= len(donnees.CHANFREIN_DESCENDANTE)
    plt.close(figure)
