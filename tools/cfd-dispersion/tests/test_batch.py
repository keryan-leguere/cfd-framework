"""La greffe sur ``cfd_plot.batch_plot``."""

from __future__ import annotations

import pickle
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.text import Text

from cfd_dispersion.batch import (
    HookDispersion,
    HookDispersionTableau,
    cle_par_defaut,
    hook_dispersion,
    hook_dispersion_tableau,
)
from cfd_dispersion.core.lois import JeuDeLois
from cfd_dispersion.figures._base import nouvelle_figure, tracer_ligne
from cfd_dispersion.figures.polaire import ALPHA_TIRAGES

cfd_plot = pytest.importorskip("cfd_plot", reason="cfd_dispersion.batch exige cfd-plot")


@pytest.fixture(autouse=True)
def _fermer_les_figures() -> Iterator[None]:
    yield
    plt.close("all")


@pytest.fixture
def donnees() -> pd.DataFrame:
    alpha = np.linspace(0.0, 12.0, 21)
    return pd.DataFrame(
        {
            "alpha": alpha,
            "beta": 0.0,
            "Mach": 0.8,
            "Altitude_m": 8000.0,
            "CN": 0.09 * alpha + 0.004 * alpha**2,
            "CA": 0.02 + 0.001 * alpha,
        }
    )


def _dictionnaires(donnees: pd.DataFrame) -> dict[str, Any]:
    return {
        "configuration_dict": {"KW": {"df": donnees, "label": "KW", "color": "C0"}},
        "y_axis_dict": {
            "CN": {"col_name": "CN", "symbol": "$C_N$", "unit": "-", "y_save_name": "CN"},
            "CA": {"col_name": "CA", "symbol": "$C_A$", "unit": "-", "y_save_name": "CA"},
        },
        "sweep_dict": {
            "alpha": {
                "col_name": "alpha",
                "symbol": r"$\alpha$",
                "unit": "°",
                "x_save_name": "alpha",
            }
        },
        "flight_point_dict": {
            "Mach": {"values": [0.8], "label": "M", "save_name": "M", "unit": "-"},
            "Altitude_m": {"values": [8000.0], "label": "Z", "save_name": "Z", "unit": "m"},
        },
    }


class _Contexte:
    """Un ``BatchPlotContext`` minimal, pour tester le hook sans batch_plot."""

    def __init__(
        self,
        y_key: str = "CN",
        sweep_key: str = "alpha",
        compare_name: str | None = None,
        *,
        flight_point: dict[str, float] | None = None,
        fixed_sweeps: dict[str, float] | None = None,
        y_col: str | None = None,
        fold_kind: str | None = None,
    ) -> None:
        self.y_key = y_key
        self.sweep_key = sweep_key
        self.compare_name = compare_name
        self.flight_point = {"Mach": 0.8} if flight_point is None else flight_point
        self.fixed_sweeps: dict[str, float] = fixed_sweeps or {}
        self.x_spec = {"col_name": sweep_key}
        self.y_spec = {"col_name": y_col or y_key}
        self.fold_kind = fold_kind


class TestSerialisation:
    def test_le_hook_est_serialisable(self, lois: JeuDeLois) -> None:
        """``batch_plot`` retombe silencieusement sur n_jobs=1 sinon."""
        hook = hook_dispersion(lois, serie="KW", n=500, graine=1)
        assert isinstance(pickle.loads(pickle.dumps(hook)), HookDispersion)

    def test_le_hook_reste_serialisable_avec_des_tirages(self, lois: JeuDeLois) -> None:
        hook = hook_dispersion(lois, serie="KW", tirages={("CN", "alpha"): np.zeros((3, 21))})
        recharge = pickle.loads(pickle.dumps(hook))
        assert recharge.tirages[("CN", "alpha")].shape == (3, 21)

    def test_une_convention_nommee_reste_serialisable(self, lois: JeuDeLois) -> None:
        """Une Convention maison bâtie sur une lambda ne le serait pas."""
        hook = hook_dispersion(lois, serie="KW", convention_="pourcentage")
        assert pickle.loads(pickle.dumps(hook)).convention_ == "pourcentage"


class TestSansCfdPlot:
    """Le module vit sans cfd-plot ; seule la fabrique le réclame."""

    def test_hook_dispersion_leve_une_erreur_explicite(
        self, lois: JeuDeLois, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L'échec doit tomber ici, pas au milieu d'un lot de 200 figures."""
        import builtins

        vrai_import = builtins.__import__

        def sans_cfd_plot(nom: str, *args: object, **kwargs: object) -> object:
            if nom == "cfd_plot":
                raise ImportError("No module named 'cfd_plot'")
            return vrai_import(nom, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "__import__", sans_cfd_plot)
        with pytest.raises(ImportError, match="pip install -e tools/cfd-plot"):
            hook_dispersion(lois, serie="KW")

    def test_la_classe_se_construit_sans_verification(self, lois: JeuDeLois) -> None:
        """La superposition, elle, retombe sur Matplotlib nu comme le reste."""
        assert HookDispersion(lois, serie="KW") is not None


class TestCorrespondanceDesCoefficients:
    def test_les_noms_qui_coincident_sont_reconnus(self, lois: JeuDeLois) -> None:
        hook = hook_dispersion(lois, serie="KW")
        assert hook.coefficient_pour("Cm_alpha") == "Cm_alpha"

    def test_une_grandeur_sans_loi_est_ignoree(self, lois: JeuDeLois) -> None:
        assert hook_dispersion(lois, serie="KW").coefficient_pour("CL") is None

    def test_une_correspondance_explicite(self, lois: JeuDeLois) -> None:
        hook = hook_dispersion(lois, serie="KW", coefficients={"CN": "Cn_beta"})
        assert hook.coefficient_pour("CN") == "Cn_beta"

    def test_cle_par_defaut(self) -> None:
        assert cle_par_defaut(_Contexte("CN", "alpha")) == ("CN", "alpha")


class TestAppelDirect:
    def _axes(self) -> tuple[Figure, Axes]:
        alpha = np.linspace(0.0, 12.0, 21)
        figure, ax = nouvelle_figure()
        tracer_ligne(ax, alpha, 0.09 * alpha, label="KW", color="C0")
        return figure, ax

    def test_decore_les_axes(self, lois: JeuDeLois) -> None:
        figure, ax = self._axes()
        avant = len(ax.get_lines())
        hook_dispersion(lois, serie="KW", n=300, graine=1)(
            figure, ax, _Contexte("Cm_alpha", "alpha")
        )
        assert len(ax.get_lines()) > avant

    def test_ne_touche_pas_une_grandeur_sans_loi(self, lois: JeuDeLois) -> None:
        figure, ax = self._axes()
        avant = len(ax.get_lines())
        hook_dispersion(lois, serie="KW", n=300, graine=1)(figure, ax, _Contexte("CL", "alpha"))
        assert len(ax.get_lines()) == avant

    def test_une_serie_absente_est_ignoree_sans_erreur(self, lois: JeuDeLois) -> None:
        """``include_curve`` peut légitimement retirer une série d'une figure."""
        figure, ax = nouvelle_figure()
        tracer_ligne(ax, [0, 1], [0, 1], label="SA", color="C1")
        hook_dispersion(lois, serie="KW", n=300, graine=1)(
            figure, ax, _Contexte("Cm_alpha", "alpha")
        )
        assert len(ax.get_lines()) == 1

    def test_le_nominal_est_lu_sur_la_courbe_tracee(self, lois: JeuDeLois) -> None:
        """Aucune donnée à redonner : une recopie divergente est impossible."""
        figure, ax = self._axes()
        artistes_avant = list(ax.get_lines())
        hook_dispersion(lois, serie="KW", n=300, graine=1)(
            figure, ax, _Contexte("Cm_alpha", "alpha")
        )
        # Les lignes ajoutées — les ±kσ — sont posées sur l'abscisse de la
        # courbe tracée : c'est d'elle que le hook a lu le nominal.
        ajoutees = [ligne for ligne in ax.get_lines() if ligne not in artistes_avant]
        assert ajoutees
        assert ajoutees[0].get_xdata() == pytest.approx(artistes_avant[0].get_xdata())

    def test_les_tirages_sont_retrouves_par_la_cle(self, lois: JeuDeLois) -> None:
        figure, ax = self._axes()
        nuage = np.tile(np.linspace(0.0, 1.0, 21), (12, 1))
        hook = hook_dispersion(
            lois,
            serie="KW",
            n=300,
            graine=1,
            tirages={("Cm_alpha", "alpha"): nuage},
            coefficients={"Cm_alpha": "Cm_alpha"},
            max_tirages=None,
        )
        hook(figure, ax, _Contexte("Cm_alpha", "alpha"))
        # Les courbes du faisceau sont les seules tracées à `ALPHA_TIRAGES`.
        faibles = [
            ligne for ligne in ax.get_lines() if ligne.get_alpha() == pytest.approx(ALPHA_TIRAGES)
        ]
        assert len(faibles) == 12

    def test_panneaux_restreint_le_mode_comparaison(self, lois: JeuDeLois) -> None:
        figure, ax = self._axes()
        avant = len(ax.get_lines())
        hook = hook_dispersion(lois, serie="KW", n=300, graine=1, panneaux=("design",))
        hook(figure, ax, _Contexte("Cm_alpha", "alpha", compare_name="off_design"))
        assert len(ax.get_lines()) == avant
        hook(figure, ax, _Contexte("Cm_alpha", "alpha", compare_name="design"))
        assert len(ax.get_lines()) > avant


class TestAvecBatchPlot:
    def test_les_figures_sont_produites_et_decorees(
        self, lois: JeuDeLois, donnees: pd.DataFrame, tmp_path: Path
    ) -> None:
        hook = hook_dispersion(lois, serie="KW", n=400, graine=1, coefficients={"CN": "Cn_beta"})
        ecrits = cfd_plot.batch_plot(
            **_dictionnaires(donnees),
            output_base=tmp_path,
            formats=("png",),
            report=False,
            on_before_save=hook,
        )
        assert len(ecrits) == 2
        assert all(chemin.exists() for chemin in ecrits)

    def test_le_hook_survit_au_rendu_parallele(
        self, lois: JeuDeLois, donnees: pd.DataFrame, tmp_path: Path
    ) -> None:
        """S'il n'était pas sérialisable, batch_plot retomberait sur n_jobs=1."""
        import warnings

        hook = hook_dispersion(lois, serie="KW", n=200, graine=1, coefficients={"CN": "Cn_beta"})
        with warnings.catch_warnings(record=True) as captures:
            warnings.simplefilter("always")
            cfd_plot.batch_plot(
                **_dictionnaires(donnees),
                output_base=tmp_path,
                formats=("png",),
                report=False,
                on_before_save=hook,
                n_jobs=2,
            )
        assert not [c for c in captures if "picklable" in str(c.message)]


# ---------------------------------------------------------------------------
# Le hook qui part du tableau dispersé
# ---------------------------------------------------------------------------

ALPHA_ESSAI = np.linspace(0.0, 12.0, 21)


def _tableau_disperse(
    n: int = 8,
    *,
    machs: Sequence[float] = (0.8,),
    colonne: str = "CN",
) -> pd.DataFrame:
    """Un tableau à plat : une ligne par (tirage × point du balayage × Mach)."""
    lignes = []
    for mach in machs:
        for tirage in range(n):
            lignes.append(
                pd.DataFrame(
                    {
                        "alpha": ALPHA_ESSAI,
                        "Mach": mach,
                        "Altitude_m": 8000.0,
                        "tirage": tirage,
                        colonne: 0.09 * ALPHA_ESSAI * (1.0 + 0.02 * (tirage - n / 2)) + mach,
                    }
                )
            )
    return pd.concat(lignes, ignore_index=True)


def _boite(ax: Axes) -> str:
    """Le texte de la boîte de paramètres posée sur des axes."""
    return "\n".join(
        texte.get_text()
        for texte in ax.findobj(match=lambda a: isinstance(a, Text))
        if isinstance(texte, Text) and "\n" in texte.get_text()
    )


def _axes_avec(label: str = "KW", mach: float = 0.8) -> tuple[Figure, Axes]:
    """Des axes portant la courbe nominale, comme batch_plot les laisse."""
    figure, ax = nouvelle_figure()
    tracer_ligne(ax, ALPHA_ESSAI, 0.09 * ALPHA_ESSAI + mach, label=label, color="C0")
    return figure, ax


class TestHookTableauDecoupage:
    def test_le_sous_tableau_suit_le_point_de_vol(self) -> None:
        df = _tableau_disperse(machs=(0.7, 0.8))
        hook = HookDispersionTableau(df)
        sous = hook.sous_tableau(_Contexte(flight_point={"Mach": 0.7}))
        assert set(sous["Mach"]) == {0.7}
        assert len(sous) == 8 * len(ALPHA_ESSAI)

    def test_les_balayages_figes_entrent_dans_le_filtre(self) -> None:
        """batch_plot filtre sur le point de vol ET les balayages figés."""
        df = _tableau_disperse()
        df.loc[df.index[: len(df) // 2], "Altitude_m"] = 0.0
        hook = HookDispersionTableau(df)
        sous = hook.sous_tableau(
            _Contexte(flight_point={"Mach": 0.8}, fixed_sweeps={"Altitude_m": 8000.0})
        )
        assert set(sous["Altitude_m"]) == {8000.0}

    def test_une_colonne_de_point_de_vol_absente_est_refusee(self) -> None:
        """Sans elle, toutes les figures recevraient tous les tirages."""
        df = _tableau_disperse().drop(columns=["Mach"])
        with pytest.raises(ValueError, match=r"colonnes de point de vol \['Mach'\]"):
            HookDispersionTableau(df).sous_tableau(_Contexte())

    def test_le_filtrage_se_supprime_explicitement(self) -> None:
        df = _tableau_disperse().drop(columns=["Mach"])
        hook = HookDispersionTableau(df, colonnes_point_de_vol=())
        assert len(hook.sous_tableau(_Contexte())) == len(df)

    def test_la_colonne_vient_du_col_name(self) -> None:
        hook = HookDispersionTableau(_tableau_disperse())
        assert hook.colonne_pour(_Contexte("CN_haut", y_col="CN")) == "CN"

    def test_une_correspondance_explicite_prime(self) -> None:
        hook = HookDispersionTableau(_tableau_disperse(), coefficients={"CN": "CA"})
        assert hook.colonne_pour(_Contexte("CN")) == "CA"


class TestHookTableauAppel:
    def test_decore_les_axes(self) -> None:
        figure, ax = _axes_avec()
        avant = len(ax.get_lines())
        HookDispersionTableau(_tableau_disperse())(figure, ax, _Contexte("CN"))
        assert len(ax.get_lines()) > avant

    def test_toutes_les_courbes_du_point_de_vol_sont_tracees(self) -> None:
        figure, ax = _axes_avec()
        HookDispersionTableau(_tableau_disperse(n=11, machs=(0.7, 0.8)))(
            figure, ax, _Contexte("CN")
        )
        faibles = [
            ligne for ligne in ax.get_lines() if ligne.get_alpha() == pytest.approx(ALPHA_TIRAGES)
        ]
        # Onze tirages au point de vol tracé, et pas les vingt-deux du tableau.
        assert len(faibles) == 11

    def test_une_grandeur_absente_du_tableau_laisse_la_figure_nue(self) -> None:
        figure, ax = _axes_avec()
        avant = len(ax.get_lines())
        HookDispersionTableau(_tableau_disperse())(figure, ax, _Contexte("CL"))
        assert len(ax.get_lines()) == avant

    def test_une_abscisse_absente_est_refusee(self) -> None:
        figure, ax = _axes_avec()
        with pytest.raises(ValueError, match="colonne de balayage 'beta'"):
            HookDispersionTableau(_tableau_disperse())(figure, ax, _Contexte("CN", "beta"))

    def test_un_point_de_vol_absent_leve_par_defaut(self) -> None:
        """Le lot entier sortirait muet, sinon."""
        figure, ax = _axes_avec()
        hook = HookDispersionTableau(_tableau_disperse())
        with pytest.raises(ValueError, match="aucun tirage"):
            hook(figure, ax, _Contexte("CN", flight_point={"Mach": 0.95}))

    def test_un_point_de_vol_absent_peut_etre_ignore(self) -> None:
        figure, ax = _axes_avec()
        avant = len(ax.get_lines())
        hook = HookDispersionTableau(_tableau_disperse(), absent="ignorer")
        hook(figure, ax, _Contexte("CN", flight_point={"Mach": 0.95}))
        assert len(ax.get_lines()) == avant

    def test_absent_est_valide_a_la_construction(self) -> None:
        with pytest.raises(ValueError, match="absent="):
            HookDispersionTableau(_tableau_disperse(), absent="peut-etre")

    def test_la_seule_courbe_des_axes_sert_de_serie(self) -> None:
        figure, ax = _axes_avec("CFD")
        avant = len(ax.get_lines())
        HookDispersionTableau(_tableau_disperse())(figure, ax, _Contexte("CN"))
        assert len(ax.get_lines()) > avant

    def test_plusieurs_courbes_reclament_une_serie(self) -> None:
        figure, ax = _axes_avec("CFD")
        tracer_ligne(ax, ALPHA_ESSAI, 0.08 * ALPHA_ESSAI, label="Essai", color="C1")
        with pytest.raises(ValueError, match="préciser laquelle"):
            HookDispersionTableau(_tableau_disperse())(figure, ax, _Contexte("CN"))
        HookDispersionTableau(_tableau_disperse(), serie="CFD")(figure, ax, _Contexte("CN"))

    def test_une_serie_absente_est_ignoree_sans_erreur(self) -> None:
        figure, ax = _axes_avec("CFD")
        avant = len(ax.get_lines())
        HookDispersionTableau(_tableau_disperse(), serie="KW")(figure, ax, _Contexte("CN"))
        assert len(ax.get_lines()) == avant

    def test_une_planche_repliee_n_est_pas_decoree(self) -> None:
        figure, ax = _axes_avec()
        avant = len(ax.get_lines())
        HookDispersionTableau(_tableau_disperse())(figure, ax, _Contexte("CN", fold_kind="context"))
        assert len(ax.get_lines()) == avant

    def test_une_abscisse_qui_ne_correspond_pas_est_refusee(self) -> None:
        """Une bande posée à côté de sa courbe se lit comme un biais."""
        figure, ax = nouvelle_figure()
        tracer_ligne(ax, ALPHA_ESSAI + 1.0, 0.09 * ALPHA_ESSAI, label="KW", color="C0")
        with pytest.raises(ValueError):
            HookDispersionTableau(_tableau_disperse())(figure, ax, _Contexte("CN"))

    def test_le_nominal_est_lu_sur_la_courbe_tracee(self) -> None:
        figure, ax = _axes_avec()
        artistes_avant = list(ax.get_lines())
        HookDispersionTableau(_tableau_disperse())(figure, ax, _Contexte("CN"))
        ajoutees = [ligne for ligne in ax.get_lines() if ligne not in artistes_avant]
        assert ajoutees
        assert ajoutees[0].get_xdata() == pytest.approx(artistes_avant[0].get_xdata())

    def test_la_legende_garde_une_entree_par_serie(self) -> None:
        """L'effectif complète l'entrée existante au lieu d'en créer une."""
        figure, ax = _axes_avec("CFD")
        HookDispersionTableau(_tableau_disperse(n=9))(figure, ax, _Contexte("CN"))
        libelles = [
            str(ligne.get_label())
            for ligne in ax.get_lines()
            if not str(ligne.get_label()).startswith("_")
        ]
        assert libelles == ["CFD (9 tirages · 9.2 %)"]

    def test_la_loi_ajoute_la_bande_theorique(self, lois: JeuDeLois) -> None:
        """Prescrit contre obtenu : l'intérêt est de les voir se recouvrir."""
        df = _tableau_disperse(colonne="CA")
        _, sans_loi = _axes_avec()
        HookDispersionTableau(df)(None, sans_loi, _Contexte("CA"))
        _, avec_loi = _axes_avec()
        HookDispersionTableau(df, lois=lois, n=400, graine=1)(None, avec_loi, _Contexte("CA"))
        # La bande devient théorique : la boîte de paramètres nomme alors les
        # deux lois tirées, ce que le seul nuage ne permet pas de dire.
        assert "FE :" in _boite(avec_loi)
        assert "FE :" not in _boite(sans_loi)

    def test_panneaux_restreint_le_mode_comparaison(self) -> None:
        figure, ax = _axes_avec()
        avant = len(ax.get_lines())
        hook = HookDispersionTableau(_tableau_disperse(), panneaux=("design",))
        hook(figure, ax, _Contexte("CN", compare_name="off_design"))
        assert len(ax.get_lines()) == avant
        hook(figure, ax, _Contexte("CN", compare_name="design"))
        assert len(ax.get_lines()) > avant


class TestHookTableauAvecBatchPlot:
    def test_le_hook_est_serialisable(self) -> None:
        hook = hook_dispersion_tableau(_tableau_disperse())
        assert isinstance(pickle.loads(pickle.dumps(hook)), HookDispersionTableau)

    def test_la_fabrique_exige_cfd_plot(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import builtins

        vrai_import = builtins.__import__

        def sans_cfd_plot(nom: str, *args: object, **kwargs: object) -> object:
            if nom == "cfd_plot":
                raise ImportError("No module named 'cfd_plot'")
            return vrai_import(nom, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "__import__", sans_cfd_plot)
        with pytest.raises(ImportError, match="pip install -e tools/cfd-plot"):
            hook_dispersion_tableau(_tableau_disperse())

    def test_les_figures_sont_produites_et_decorees(
        self, donnees: pd.DataFrame, tmp_path: Path
    ) -> None:
        """Le cas visé : le nominal dans config, le dispersé dans le hook."""
        disperse = _tableau_disperse(n=6)
        disperse["CA"] = 0.02 + 0.001 * disperse["alpha"] * (1.0 + 0.01 * disperse["tirage"])
        ecrits = cfd_plot.batch_plot(
            **_dictionnaires(donnees),
            output_base=tmp_path,
            formats=("png",),
            report=False,
            on_before_save=hook_dispersion_tableau(disperse, serie="KW"),
        )
        assert len(ecrits) == 2
        assert all(chemin.exists() and chemin.stat().st_size > 0 for chemin in ecrits)

    def test_le_hook_survit_au_rendu_parallele(self, donnees: pd.DataFrame, tmp_path: Path) -> None:
        import warnings

        disperse = _tableau_disperse(n=4)
        disperse["CA"] = 0.02 + 0.001 * disperse["alpha"]
        with warnings.catch_warnings(record=True) as captures:
            warnings.simplefilter("always")
            cfd_plot.batch_plot(
                **_dictionnaires(donnees),
                output_base=tmp_path,
                formats=("png",),
                report=False,
                on_before_save=hook_dispersion_tableau(disperse, serie="KW"),
                n_jobs=2,
            )
        assert not [c for c in captures if "picklable" in str(c.message)]
