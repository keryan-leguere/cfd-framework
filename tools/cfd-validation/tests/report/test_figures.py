"""Les planches, et ce qui les rend fiables.

Trois invariants qu'aucune inspection visuelle n'attraperait :

* le hook est **picklable** — sinon ``batch_plot`` retombe silencieusement sur
  un seul cœur, avec un simple ``UserWarning`` noyé dans la sortie ;
* le tracé **à blanc** annonce exactement ce qu'un vrai tracé écrirait ;
* les deux cadres partagent leurs abscisses, donc aucune courbe ne disparaît
  du filtre par égalité stricte de ``batch_plot``.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from cfd_validation.engine.tables import valider_tables
from cfd_validation.report._plotting_lib import cfd_plot_disponible
from cfd_validation.report.figures import (
    COL_GRANDEUR,
    COL_MODELE,
    COL_RELATIF,
    COL_TABLE,
    HookEcarts,
    dictionnaires,
    planches_prevues,
    points_fautifs,
    tracer_rapport,
    tracer_table,
)
from cfd_validation.wrap.factice import ModeleFactice

from ..conftest import FauxContexte, textes_de

sans_cfd_plot = pytest.mark.skipif(
    not cfd_plot_disponible(), reason="cfd-plot absent : pip install -e ../cfd-plot"
)


@pytest.fixture
def rapport_ko(module: Any, specs: Any) -> Any:
    return valider_tables(module, specs, modele=ModeleFactice(module, bug="ecretage"))


@pytest.fixture
def rapport_ok(module: Any, specs: Any, modele: Any) -> Any:
    return valider_tables(module, specs, modele=modele)


class TestPointsFautifs:
    def test_une_ligne_par_couple_noeud_grandeur_fautif(self, rapport_ko: Any) -> None:
        fautifs = points_fautifs(rapport_ko["CN"])
        assert len(fautifs) == rapport_ko["CN"].grandeur("CN").ecart.n_fautifs
        assert set(fautifs[COL_GRANDEUR]) == {"CN"}

    def test_les_coordonnees_et_les_deux_valeurs_y_sont(self, rapport_ko: Any) -> None:
        fautifs = points_fautifs(rapport_ko["CN"])
        for colonne in ("mach", "alpha", "delta", COL_TABLE, COL_MODELE, COL_RELATIF):
            assert colonne in fautifs.columns

    def test_une_table_conforme_donne_un_cadre_vide_mais_colonne(self, rapport_ok: Any) -> None:
        """Vide et sans colonnes, le hook planterait au lieu de ne rien faire."""
        fautifs = points_fautifs(rapport_ok["CN"])
        assert fautifs.empty
        assert COL_GRANDEUR in fautifs.columns


class TestDictionnaires:
    def test_deux_configurations_la_table_et_le_modele(self, rapport_ko: Any) -> None:
        dicts = dictionnaires(rapport_ko["CN"])
        assert set(dicts["configuration_dict"]) == {"TABLE", "MODELE"}

    def test_une_polaire_par_variable_independante(self, rapport_ko: Any) -> None:
        dicts = dictionnaires(rapport_ko["CN"])
        assert list(dicts["sweep_dict"]) == ["mach", "alpha", "delta"]

    def test_une_figure_par_qoi(self, rapport_ko: Any) -> None:
        assert list(dictionnaires(rapport_ko["CN"])["y_axis_dict"]) == ["CN"]

    def test_les_valeurs_epinglees_sont_echantillonnees(self, rapport_ko: Any) -> None:
        """Une table 6×7×7 donnerait sinon des centaines de planches par polaire."""
        dicts = dictionnaires(rapport_ko["CN"], max_valeurs=3)
        for spec in dicts["flight_point_dict"].values():
            assert len(spec["values"]) <= 3

    def test_l_echantillon_garde_les_bornes(self, rapport_ko: Any) -> None:
        """Les bords sont là où les pannes d'indexation se voient."""
        table = rapport_ko["CN"].cadre_table
        dicts = dictionnaires(rapport_ko["CN"], max_valeurs=3)
        valeurs = dicts["flight_point_dict"]["mach"]["values"]
        assert valeurs[0] == table["mach"].min()
        assert valeurs[-1] == table["mach"].max()

    def test_les_valeurs_epinglees_existent_dans_les_donnees(self, rapport_ko: Any) -> None:
        """``batch_plot`` avertit sur une valeur qu'aucune ligne ne porte."""
        table = rapport_ko["CN"].cadre_table
        dicts = dictionnaires(rapport_ko["CN"], max_valeurs=4)
        for colonne, spec in dicts["flight_point_dict"].items():
            presentes = set(table[colonne].to_numpy())
            assert set(spec["values"]) <= presentes

    def test_sans_plafond_toutes_les_valeurs_sont_retenues(self, rapport_ko: Any) -> None:
        dicts = dictionnaires(rapport_ko["CN"], max_valeurs=None)
        assert len(dicts["flight_point_dict"]["alpha"]["values"]) == 7

    def test_le_libelle_ne_repete_pas_le_symbole(self, rapport_ko: Any) -> None:
        """cfd-plot compose « littéral, symbole (unité) » : « CN, CN (-) » sinon."""
        dicts = dictionnaires(rapport_ko["CN"])
        assert dicts["y_axis_dict"]["CN"]["literal_name"] == ""
        assert dicts["sweep_dict"]["mach"]["symbol"] == "Mach"

    def test_les_deux_cadres_ont_les_memes_abscisses(self, rapport_ko: Any) -> None:
        """L'invariant qui empêche une courbe de disparaître du filtre strict."""
        dicts = dictionnaires(rapport_ko["CN"])
        table = dicts["configuration_dict"]["TABLE"]["df"]
        modele = dicts["configuration_dict"]["MODELE"]["df"]
        for colonne in ("mach", "alpha", "delta"):
            assert np.array_equal(table[colonne].to_numpy(), modele[colonne].to_numpy())


class TestHook:
    def test_le_hook_est_picklable(self, rapport_ko: Any) -> None:
        """Sinon ``batch_plot`` retombe sur un seul cœur, sans le dire vraiment."""
        hook = HookEcarts(points_fautifs(rapport_ko["CN"]))
        rejoue = pickle.loads(pickle.dumps(hook))
        assert len(rejoue.fautifs) == len(hook.fautifs)

    def test_le_sous_tableau_se_filtre_comme_batch_plot(self, rapport_ko: Any) -> None:
        """Égalité stricte, la même que ``_filter_df_by_context``."""
        hook = HookEcarts(points_fautifs(rapport_ko["CN"]))
        contexte = FauxContexte(flight_point={"alpha": 0.0}, fixed_sweeps={"delta": 0.0})
        sous = hook.sous_tableau(contexte, "CN")
        assert not sous.empty
        assert set(sous["alpha"]) == {0.0}
        assert set(sous["delta"]) == {0.0}

    def test_une_grandeur_absente_rend_un_sous_tableau_vide(self, rapport_ko: Any) -> None:
        hook = HookEcarts(points_fautifs(rapport_ko["CN"]))
        assert hook.sous_tableau(FauxContexte(), "CY").empty


class TestComptage:
    def test_les_planches_prevues_valent_ce_qui_est_ecrit(
        self, rapport_ko: Any, tmp_path: Path
    ) -> None:
        prevu = planches_prevues(rapport_ko, max_valeurs=3)
        if not cfd_plot_disponible():
            pytest.skip("cfd-plot absent")
        ecrits = tracer_rapport(
            rapport_ko,
            sortie=tmp_path,
            max_valeurs=3,
            a_blanc=True,
            compte_rendu=False,
        )
        assert sum(len(fichiers) for fichiers in ecrits.values()) == prevu


@sans_cfd_plot
class TestTrace:
    def test_le_trace_a_blanc_annonce_exactement_ce_qui_serait_ecrit(
        self, rapport_ko: Any, tmp_path: Path
    ) -> None:
        """Sans quoi ``--a-blanc`` ne servirait à rien : il doit être fiable."""
        prevu = tracer_rapport(
            rapport_ko, sortie=tmp_path, max_valeurs=2, a_blanc=True, compte_rendu=False
        )
        assert not list(tmp_path.rglob("*.png"))

        ecrit = tracer_rapport(rapport_ko, sortie=tmp_path, max_valeurs=2, compte_rendu=False)
        assert {nom: sorted(map(str, f)) for nom, f in prevu.items()} == {
            nom: sorted(map(str, f)) for nom, f in ecrit.items()
        }

    def test_les_fichiers_sont_reellement_ecrits(self, rapport_ko: Any, tmp_path: Path) -> None:
        ecrits = tracer_table(
            rapport_ko["CN"], sortie=tmp_path, max_valeurs=2, options={"report": False}
        )
        assert ecrits
        assert all(chemin.exists() for chemin in ecrits)

    def test_une_planche_fautive_porte_le_marquage(self, rapport_ko: Any, tmp_path: Path) -> None:
        """Ce qui rend la panne visible ; une courbe fausse reste lisse."""
        import matplotlib.pyplot as plt

        from cfd_validation.report.figures import HookEcarts, points_fautifs

        figure, axes = plt.subplots()
        axes.plot([0.3, 0.5, 0.95], [1.0, 2.0, 3.0], label="table")
        contexte = FauxContexte(flight_point={"alpha": 0.0}, fixed_sweeps={"delta": 0.0})

        HookEcarts(points_fautifs(rapport_ko["CN"]))(figure, axes, contexte)
        assert any("hors tolérance" in texte for texte in textes_de(figure))
        plt.close(figure)

    def test_le_marquage_se_tait_sur_une_planche_conforme(
        self, rapport_ok: Any, tmp_path: Path
    ) -> None:
        import matplotlib.pyplot as plt

        figure, axes = plt.subplots()
        avant = len(axes.collections)

        HookEcarts(points_fautifs(rapport_ok["CN"]))(figure, axes, FauxContexte())
        assert len(axes.collections) == avant
        plt.close(figure)

    def test_une_planche_repliee_en_superposition_n_est_pas_marquee(self, rapport_ko: Any) -> None:
        """Les courbes y sont réétiquetées et empilées : le marquage n'y dirait rien."""
        import matplotlib.pyplot as plt

        figure, axes = plt.subplots()
        contexte = FauxContexte(fold_kind="context", fold_layout="overlay")

        HookEcarts(points_fautifs(rapport_ko["CN"]))(figure, axes, contexte)
        assert not axes.collections
        plt.close(figure)

    def test_seulement_fautives_saute_les_tables_conformes(
        self, module: Any, specs: Any, tmp_path: Path
    ) -> None:
        def moitie(df: Any) -> Any:
            """CN est cassé, CA est juste."""
            if "delta" in df.columns:
                return ModeleFactice(module, bug="echelle")(df)
            return ModeleFactice(module)(df)

        rapport = valider_tables(module, specs, modele=moitie)
        ecrits = tracer_rapport(
            rapport,
            sortie=tmp_path,
            max_valeurs=2,
            a_blanc=True,
            compte_rendu=False,
            seulement_fautives=True,
        )
        assert set(ecrits) == {"CN"}


class TestSansCfdPlot:
    def test_l_erreur_dit_quoi_taper(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Le calcul tourne sans cfd-plot ; les figures, non — et ça doit se dire."""
        from cfd_validation.report import _plotting_lib

        monkeypatch.setattr(_plotting_lib, "_importer", lambda: None)
        with pytest.raises(ImportError, match="pip install -e tools/cfd-plot"):
            _plotting_lib.get_plotting()
