"""La greffe sur ``cfd_plot.batch_plot``."""

from __future__ import annotations

import pickle
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from cfd_dispersion.batch import HookDispersion, cle_par_defaut, hook_dispersion
from cfd_dispersion.core.lois import JeuDeLois
from cfd_dispersion.figures._base import nouvelle_figure, tracer_ligne

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
    ) -> None:
        self.y_key = y_key
        self.sweep_key = sweep_key
        self.compare_name = compare_name
        self.flight_point = {"Mach": 0.8}
        self.fixed_sweeps: dict[str, float] = {}


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
        moyenne = [
            ligne
            for ligne in ax.get_lines()
            if ligne not in artistes_avant and "moyenne" in str(ligne.get_label())
        ]
        assert moyenne
        assert moyenne[0].get_xdata() == pytest.approx(artistes_avant[0].get_xdata())

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
        faibles = [ligne for ligne in ax.get_lines() if (ligne.get_alpha() or 1.0) < 0.2]
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
