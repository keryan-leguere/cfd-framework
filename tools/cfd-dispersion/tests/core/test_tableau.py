"""Le plan d'appels croisé, et le tableau large que rend un vrai modèle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from cfd_dispersion import (
    aplatir_tirage,
    charger_lois,
    lire_dict,
    lire_sortie_modele,
    lois_depuis_tableau,
    plan_croise,
    tirer,
    valider_lot,
)

TABLE: dict[str, dict[str, float]] = {
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
}


def _sortie_modele(*, n: int = 60, alphas: tuple[float, ...] = (0.0, 2.0, 4.0)) -> pd.DataFrame:
    """Un tableau à la forme d'un modèle d'établissement appelé en croisé."""
    lois = charger_lois(TABLE)
    lignes = []
    for indice in range(n):
        tirage = tirer(lois, graine=1000 + indice)
        for pdv in plan_croise(Mach=[0.7, 0.85], Altitude_m=[5000.0], alpha=list(alphas)):
            lignes.append(
                {
                    **pdv,
                    "CN": 0.11 * pdv["alpha"],
                    "CA": 0.03,
                    "version_fortran": "v3.1",
                    "convergence": True,
                    "DICT_LAW_DISPERSION": TABLE,
                    "DICT_TIRAGE": dict(tirage),
                }
            )
    return pd.DataFrame(lignes)


class TestPlanCroise:
    def test_le_produit_cartesien_suit_l_ordre_des_axes(self) -> None:
        plan = plan_croise(Mach=[0.7, 0.8], alpha=[0.0, 2.0])
        assert plan == [
            {"Mach": 0.7, "alpha": 0.0},
            {"Mach": 0.7, "alpha": 2.0},
            {"Mach": 0.8, "alpha": 0.0},
            {"Mach": 0.8, "alpha": 2.0},
        ]

    def test_la_taille_est_le_produit_des_longueurs(self) -> None:
        plan = plan_croise(Mach=[0.7, 0.8, 0.9], Altitude_m=[0.0, 5000.0], alpha=range(13))
        assert len(plan) == 3 * 2 * 13

    def test_un_axe_vide_est_refuse(self) -> None:
        """Un plan vide ne se remarquerait qu'au moment de tracer."""
        with pytest.raises(ValueError, match=r"axe.*vide"):
            plan_croise(Mach=[0.7], alpha=[])

    def test_sans_axe_du_tout(self) -> None:
        with pytest.raises(ValueError, match="aucun axe"):
            plan_croise()

    def test_le_plan_se_met_en_dataframe(self) -> None:
        df = pd.DataFrame(plan_croise(Mach=[0.7, 0.8], alpha=[0.0]))
        assert list(df.columns) == ["Mach", "alpha"]
        assert len(df) == 2


class TestLireDict:
    def test_un_dict_passe_tel_quel(self) -> None:
        assert lire_dict({"CN": {"Biais": 1.0}}) == {"CN": {"Biais": 1.0}}

    def test_le_json_est_lu(self) -> None:
        assert lire_dict('{"CN": {"Biais": 1.0}}') == {"CN": {"Biais": 1.0}}

    def test_le_repr_python_est_lu(self) -> None:
        """C'est sous cette forme qu'un dict revient d'un CSV écrit par pandas."""
        assert lire_dict("{'CN': {'Biais': 1.0}}") == {"CN": {"Biais": 1.0}}

    def test_une_chaine_illisible_est_refusee(self) -> None:
        with pytest.raises(ValueError, match="illisible"):
            lire_dict("CN=1.0")

    def test_une_valeur_qui_n_est_pas_un_dictionnaire(self) -> None:
        with pytest.raises(ValueError, match="dictionnaire"):
            lire_dict(3.14)

    def test_le_message_ne_recopie_pas_toute_la_valeur(self) -> None:
        with pytest.raises(ValueError, match="…"):
            lire_dict("x" * 500)


class TestAplatirTirage:
    def test_les_colonnes_creees_sont_celles_du_contrat(self) -> None:
        df = _sortie_modele(n=5)
        plat = aplatir_tirage(df)
        assert {"CN_Biais", "CN_FE", "CA_Biais", "CA_FE"} <= set(plat.columns)

    def test_le_tableau_d_origine_n_est_pas_modifie(self) -> None:
        df = _sortie_modele(n=5)
        colonnes = list(df.columns)
        aplatir_tirage(df)
        assert list(df.columns) == colonnes

    def test_les_metadonnees_voyagent(self) -> None:
        """Le paquet ne lit que les colonnes qu'il nomme."""
        plat = aplatir_tirage(_sortie_modele(n=5))
        assert {"version_fortran", "convergence"} <= set(plat.columns)

    def test_le_numero_compte_les_tirages_distincts_et_non_les_lignes(self) -> None:
        """Sur un appel croisé, un même tirage revient à chaque point."""
        plat = aplatir_tirage(_sortie_modele(n=7, alphas=(0.0, 2.0, 4.0)))
        assert len(plat) == 7 * 2 * 3
        assert plat["tirage"].nunique() == 7

    def test_le_meme_tirage_porte_le_meme_numero_partout(self) -> None:
        plat = aplatir_tirage(_sortie_modele(n=4))
        for _, groupe in plat.groupby("tirage"):
            assert groupe["CN_Biais"].nunique() == 1

    def test_les_composantes_sont_reconnues_a_la_casse_pres(self) -> None:
        df = pd.DataFrame({"DICT_TIRAGE": [{"CN": {"biais": 0.1, "fe": 1.02}}]})
        plat = aplatir_tirage(df)
        assert plat["CN_Biais"].iloc[0] == pytest.approx(0.1)
        assert plat["CN_FE"].iloc[0] == pytest.approx(1.02)

    def test_une_composante_inconnue_nomme_la_ligne_et_l_attendu(self) -> None:
        df = pd.DataFrame({"DICT_TIRAGE": [{"CN": {"Biais": 0.1, "Offset": 2.0}}]})
        with pytest.raises(ValueError, match=r"ligne 0.*'Offset' inconnue"):
            aplatir_tirage(df)

    def test_des_lignes_qui_ne_portent_pas_les_memes_composantes(self) -> None:
        df = pd.DataFrame(
            {
                "DICT_TIRAGE": [
                    {"CN": {"Biais": 0.1, "FE": 1.0}},
                    {"CA": {"Biais": 0.1, "FE": 1.0}},
                ]
            }
        )
        with pytest.raises(ValueError, match="ligne 1"):
            aplatir_tirage(df)

    def test_une_colonne_absente_liste_celles_qui_sont_la(self) -> None:
        df = pd.DataFrame({"Mach": [0.8]})
        with pytest.raises(ValueError, match=r"'DICT_TIRAGE' absente.*\['Mach'\]"):
            aplatir_tirage(df)

    def test_ecraser_une_colonne_du_modele_est_refuse(self) -> None:
        df = pd.DataFrame({"DICT_TIRAGE": [{"CN": {"Biais": 0.1, "FE": 1.0}}], "CN_Biais": [9.9]})
        with pytest.raises(ValueError, match="existe déjà"):
            aplatir_tirage(df)

    def test_un_numero_deja_pris_est_refuse(self) -> None:
        df = pd.DataFrame({"DICT_TIRAGE": [{"CN": {"Biais": 0.1, "FE": 1.0}}], "tirage": ["abc"]})
        with pytest.raises(ValueError, match="numero="):
            aplatir_tirage(df)

    def test_on_peut_ne_pas_numeroter(self) -> None:
        plat = aplatir_tirage(_sortie_modele(n=3), numero=None)
        assert "tirage" not in plat.columns


class TestLoisDepuisTableau:
    def test_la_table_est_relue_depuis_le_tableau(self) -> None:
        lois = lois_depuis_tableau(_sortie_modele(n=3))
        assert list(lois) == ["CN", "CA"]
        assert lois["CN"].biais.ET == pytest.approx(0.02)

    def test_deux_tables_differentes_sont_refusees(self) -> None:
        """Valider une étude contre deux tables n'a pas de sens."""
        df = _sortie_modele(n=2)
        autre = {"CN": dict(TABLE["CN"], Biais_ET=0.99), "CA": TABLE["CA"]}
        tables = list(df["DICT_LAW_DISPERSION"])
        tables[-1] = autre
        df["DICT_LAW_DISPERSION"] = tables
        with pytest.raises(ValueError, match="diffère de celle de la ligne 0"):
            lois_depuis_tableau(df)

    def test_la_correlation_reste_une_hypothese_de_tirage(self) -> None:
        lois = lois_depuis_tableau(_sortie_modele(n=2), correlation={("CN", "CA"): 0.5})
        assert not lois.independantes

    def test_un_tableau_vide(self) -> None:
        with pytest.raises(ValueError, match="vide"):
            lois_depuis_tableau(pd.DataFrame({"DICT_LAW_DISPERSION": []}))


class TestLireSortieModele:
    def test_la_chaine_complete(self) -> None:
        resultats, lois = lire_sortie_modele(_sortie_modele(n=40))
        verdicts = valider_lot(resultats, lois, par=("Mach", "Altitude_m"), unique_par=("tirage",))
        assert set(verdicts["n"]) == {40}
        assert verdicts["valide"].all()

    def test_un_aller_retour_par_csv(self, tmp_path: Path) -> None:
        """Les dictionnaires reviennent d'un CSV en chaînes ; ça doit passer."""
        df = _sortie_modele(n=10)
        chemin = tmp_path / "sortie.csv"
        df.to_csv(chemin, index=False)

        direct, _ = lire_sortie_modele(df)
        relu, lois = lire_sortie_modele(pd.read_csv(chemin))
        assert list(lois) == ["CN", "CA"]
        assert relu["CN_Biais"].to_numpy() == pytest.approx(direct["CN_Biais"].to_numpy())
        assert relu["tirage"].to_list() == direct["tirage"].to_list()

    def test_un_aller_retour_par_json(self, tmp_path: Path) -> None:
        df = _sortie_modele(n=5)
        df["DICT_TIRAGE"] = [json.dumps(t) for t in df["DICT_TIRAGE"]]
        df["DICT_LAW_DISPERSION"] = [json.dumps(t) for t in df["DICT_LAW_DISPERSION"]]
        resultats, lois = lire_sortie_modele(df)
        assert "CN_Biais" in resultats.columns
        assert list(lois) == ["CN", "CA"]

    def test_les_noms_de_colonnes_sont_reglables(self) -> None:
        df = _sortie_modele(n=3).rename(
            columns={"DICT_TIRAGE": "draw", "DICT_LAW_DISPERSION": "laws"}
        )
        resultats, lois = lire_sortie_modele(df, tirage="draw", lois="laws", numero="n_tirage")
        assert "n_tirage" in resultats.columns
        assert list(lois) == ["CN", "CA"]


class TestPiegeDuCroisement:
    """Un tirage croisé non dédoublonné est refusé, pas jugé de travers."""

    def test_sans_dedoublonnage_la_validation_refuse_et_nomme_le_remede(self) -> None:
        resultats, lois = lire_sortie_modele(_sortie_modele(n=40, alphas=(0.0, 2.0, 4.0)))
        with pytest.raises(ValueError, match=r"unique_par"):
            valider_lot(resultats, lois, par=("Mach", "Altitude_m"))

    def test_avec_dedoublonnage_l_effectif_est_le_nombre_de_tirages(self) -> None:
        resultats, lois = lire_sortie_modele(_sortie_modele(n=40, alphas=(0.0, 2.0, 4.0)))
        verdicts = valider_lot(resultats, lois, par=("Mach", "Altitude_m"), unique_par=("tirage",))
        # 40 tirages, et non 40 × 3 incidences.
        assert set(verdicts["n"]) == {40}

    def test_le_croisement_ne_change_pas_D_mais_gonfle_l_effectif(self) -> None:
        """La preuve chiffrée : même D, effectif multiplié, seuil resserré."""
        import numpy as np

        from cfd_dispersion import LoiDispersion, valider

        loi = LoiDispersion(6, 1.0, 0.08)
        tirages = loi.tirer(500, graine=7)

        seul = valider(tirages, loi)
        croise = valider(np.repeat(tirages, 13), loi)

        assert croise.ks_D == pytest.approx(seul.ks_D)
        assert croise.n == 13 * seul.n
        assert seul.valide and not croise.valide

    def test_une_colonne_d_identifiant_inconnue_est_signalee(self) -> None:
        resultats, lois = lire_sortie_modele(_sortie_modele(n=3))
        with pytest.raises(ValueError, match="identifiant de tirage absente"):
            valider_lot(resultats, lois, unique_par=("numero_absent",))

    def test_le_controle_se_desactive(self) -> None:
        resultats, lois = lire_sortie_modele(_sortie_modele(n=40))
        verdicts = valider_lot(resultats, lois, par=("Mach",), redondance_max=1.0)
        assert set(verdicts["n"]) == {40 * 3}

    def test_une_loi_degeneree_echappe_au_controle(self) -> None:
        """Une constante n'a que des doublons, par construction."""
        resultats, lois = lire_sortie_modele(_sortie_modele(n=40))
        verdicts = valider_lot(resultats, lois, par=("Mach",), unique_par=("tirage",))
        constante = verdicts.loc[
            (verdicts["coefficient"] == "CA") & (verdicts["composante"] == "Biais")
        ]
        assert constante["valide"].all()


class TestFiguresSurUnTableauCroise:
    def test_les_figures_dedoublonnent_aussi(self) -> None:
        import matplotlib.pyplot as plt

        from cfd_dispersion import figures_par_pdv

        resultats, lois = lire_sortie_modele(_sortie_modele(n=40))
        produites = 0
        for _, _, figure in figures_par_pdv(
            resultats, lois, par=("Mach",), unique_par=("tirage",), coefficients=["CN"]
        ):
            produites += 1
            plt.close(figure)
        assert produites == 2

    def test_les_courbes_se_regroupent_par_numero_de_tirage(self) -> None:
        from cfd_dispersion import courbes_par_tirage

        resultats, _ = lire_sortie_modele(_sortie_modele(n=12, alphas=(0.0, 2.0, 4.0, 6.0)))
        # Une polaire se lit à point de vol figé : le balayage est en alpha.
        un_pdv = resultats.loc[resultats["Mach"] == 0.85]
        x, courbes = courbes_par_tirage(un_pdv, x="alpha", y="CN", par=["tirage"])
        assert x.tolist() == [0.0, 2.0, 4.0, 6.0]
        assert courbes.shape == (12, 4)


def _lois_de(table: dict[str, dict[str, Any]]) -> Any:
    return charger_lois(table)
