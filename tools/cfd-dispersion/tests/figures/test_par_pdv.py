"""Le parcours des points de vol : arborescence, plafond de tirages, nominaux."""

from __future__ import annotations

import pickle
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import matplotlib
import pandas as pd
import pytest

from cfd_dispersion.core.convention import convention
from cfd_dispersion.core.lois import JeuDeLois, charger_lois
from cfd_dispersion.core.tirage import tirage_neutre, tirer_lot
from cfd_dispersion.figures.par_pdv import (
    MAX_TIRAGES_DEFAUT,
    _init_ouvrier,
    _main_rejouable,
    _nominaux_du_point,
    _Travail,
    chemin_du_point_de_vol,
    etiquette_du_point_de_vol,
    figures_tirage_par_pdv,
)

#: Deux coefficients seulement : chaque figure coûte une demi-seconde à écrire.
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
        "Biais_Type": 3,
        "Biais_M": 0.0,
        "Biais_ET": 0.0015,
        "FE_Type": 4,
        "FE_M": 1.0,
        "FE_ET": 0.06,
    },
}

#: Deux points de vol, une seule altitude : de quoi vérifier qu'une clé qui ne
#: varie pas ne crée pas de dossier.
NOMINAUX = {0.70: {"CN": 0.78, "CA": 0.0295}, 0.85: {"CN": 0.85, "CA": 0.0320}}


@pytest.fixture(scope="module")
def lois_deux() -> JeuDeLois:
    return charger_lois(TABLE)


@pytest.fixture(scope="module")
def tableau(lois_deux: JeuDeLois) -> pd.DataFrame:
    """La sortie d'un modèle : 2 points de vol × 3 tirages, le même lot partout."""
    lot = tirer_lot(lois_deux, 3, graine=42)
    lignes: list[dict[str, Any]] = []
    for mach, nominaux in NOMINAUX.items():
        for tirage in lot:
            disperses = tirage.appliquer(nominaux)
            lignes.append(
                {
                    "Mach": mach,
                    "Altitude_m": 10_000.0,
                    "cas": f"M{mach}",
                    **{coeff: float(valeur) for coeff, valeur in disperses.items()},
                    "DICT_LAW_DISPERSION": TABLE,
                    "DICT_TIRAGE": tirage.vers_dict(),
                    "tirage": tirage.numero,
                }
            )
    return pd.DataFrame(lignes)


@pytest.fixture(scope="module")
def reference(lois_deux: JeuDeLois) -> pd.DataFrame:
    """Le même modèle, tirage neutre : une ligne par point de vol."""
    neutre = tirage_neutre(lois_deux)
    return pd.DataFrame(
        [
            {
                "Mach": mach,
                "Altitude_m": 10_000.0,
                **{coeff: float(valeur) for coeff, valeur in neutre.appliquer(nominaux).items()},
                "DICT_LAW_DISPERSION": TABLE,
                "DICT_TIRAGE": neutre.vers_dict(),
                "tirage": 0,
            }
            for mach, nominaux in NOMINAUX.items()
        ]
    )


#: Le parcours le plus court qui prouve quelque chose : une matrice par point
#: de vol, et rien d'autre.
LEGER: dict[str, Any] = {"par_coefficient": False, "max_tirages": 1}


class TestArborescence:
    def test_un_dossier_par_cle_qui_varie(self, tableau: pd.DataFrame, tmp_path: Path) -> None:
        """L'altitude est unique ici : elle n'ajoute pas de niveau."""
        figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.70, 0.85], "Altitude_m": [10_000.0]},
            racine=tmp_path,
            **LEGER,
        )
        assert (tmp_path / "MACH_0.7" / "tirage_000" / "matrice.svg").is_file()
        assert (tmp_path / "MACH_0.85" / "tirage_000" / "matrice.svg").is_file()

    def test_le_nom_court_vient_du_save_name(self, tableau: pd.DataFrame, tmp_path: Path) -> None:
        figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": {"values": [0.85], "save_name": "M"}},
            racine=tmp_path,
            **LEGER,
        )
        assert (tmp_path / "tirage_000" / "matrice.svg").is_file()

    def test_les_valeurs_absentes_sont_decouvertes(
        self, tableau: pd.DataFrame, tmp_path: Path
    ) -> None:
        """Sans ``values``, ce sont celles du tableau — comme dans batch_plot."""
        inventaire = figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": {"save_name": "M"}},
            racine=tmp_path,
            **LEGER,
        )
        assert sorted(inventaire["Mach"].unique()) == [0.70, 0.85]

    def test_chemin_du_point_de_vol(self) -> None:
        chemin = chemin_du_point_de_vol(
            "SORTIE",
            {"Mach": 0.85, "Altitude_m": 10_000.0},
            {"Mach": {"save_name": "M"}, "Altitude_m": {"save_name": "Z"}},
            ["Mach", "Altitude_m"],
        )
        assert chemin == Path("SORTIE/M_0.85/Z_10000")

    def test_l_etiquette_situe_la_figure(self) -> None:
        etiquette = etiquette_du_point_de_vol(
            {"Mach": 0.85, "Altitude_m": 10_000.0},
            {"Mach": {"label": "M"}, "Altitude_m": {"label": "Z", "unit": " m"}},
        )
        assert etiquette == "M = 0.85 · Z = 10000 m"


class TestPlafondDeTirages:
    def test_seuls_les_premiers_tirages_sont_traces(
        self, tableau: pd.DataFrame, tmp_path: Path
    ) -> None:
        """Cent tirages font cent figures que personne ne regardera."""
        inventaire = figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.70, 0.85]},
            racine=tmp_path,
            par_coefficient=False,
            max_tirages=2,
        )
        assert sorted(inventaire["tirage"].unique()) == [0, 1]
        assert len(inventaire) == 4  # 2 points de vol × 2 tirages

    def test_le_plafond_par_defaut_est_quinze(self) -> None:
        assert MAX_TIRAGES_DEFAUT == 15

    def test_sans_plafond_tous_les_tirages_passent(
        self, tableau: pd.DataFrame, tmp_path: Path
    ) -> None:
        inventaire = figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            par_coefficient=False,
            max_tirages=None,
        )
        assert sorted(inventaire["tirage"].unique()) == [0, 1, 2]


class TestInventaire:
    def test_il_dit_ce_qui_a_ete_ecrit(self, tableau: pd.DataFrame, tmp_path: Path) -> None:
        inventaire = figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            max_tirages=1,
        )
        assert list(inventaire.columns) == [
            "Mach",
            "tirage",
            "figure",
            "fichier",
            "calcul",
            "modele",
            "ecart",
            "accord",
        ]
        assert sorted(inventaire["figure"]) == ["CA", "CN", "matrice"]
        assert all(Path(chemin).is_file() for chemin in inventaire["fichier"])

    def test_la_matrice_peut_etre_seule(self, tableau: pd.DataFrame, tmp_path: Path) -> None:
        inventaire = figures_tirage_par_pdv(
            tableau, points_de_vol={"Mach": [0.85]}, racine=tmp_path, **LEGER
        )
        assert list(inventaire["figure"]) == ["matrice"]

    def test_les_coefficients_peuvent_etre_seuls(
        self, tableau: pd.DataFrame, tmp_path: Path
    ) -> None:
        inventaire = figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            matrice=False,
            max_tirages=1,
        )
        assert sorted(inventaire["figure"]) == ["CA", "CN"]

    def test_les_formats_se_choisissent(self, tableau: pd.DataFrame, tmp_path: Path) -> None:
        inventaire = figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            formats=("png",),
            **LEGER,
        )
        assert Path(inventaire["fichier"].iloc[0]).suffix == ".png"


class TestValeursNominales:
    def test_la_reference_donne_le_nominal(self) -> None:
        """Le modèle tourné une fois avec un tirage neutre."""
        lignes = pd.DataFrame({"CN": [0.83, 0.87]})
        reference = pd.DataFrame({"CN": [0.85]})
        assert _nominaux_du_point(lignes, ["CN"], None, reference) == {"CN": 0.85}

    def test_la_colonne_du_coefficient_n_est_pas_un_nominal(self) -> None:
        """C'est la sortie dispersée : la prendre centrerait la loi sur elle."""
        lignes = pd.DataFrame({"CN": [0.85, 0.85]})
        assert _nominaux_du_point(lignes, ["CN"], None, None) == {}

    def test_une_colonne_nominale_explicite_sert_de_repli(self) -> None:
        lignes = pd.DataFrame({"CN": [0.83, 0.87], "CN_nominal": [0.85, 0.85]})
        assert _nominaux_du_point(lignes, ["CN"], None, None) == {"CN": 0.85}

    def test_sans_rien_il_n_y_a_pas_de_nominal(self) -> None:
        """Le troisième panneau le dira plutôt que d'en inventer un."""
        lignes = pd.DataFrame({"autre": [1.0, 2.0]})
        assert _nominaux_du_point(lignes, ["CN"], None, None) == {}

    def test_l_appelant_peut_imposer(self) -> None:
        lignes = pd.DataFrame({"CN": [0.85, 0.85]})
        reference = pd.DataFrame({"CN": [0.80]})
        assert _nominaux_du_point(lignes, ["CN"], {"CN": 1.0}, reference) == {"CN": 1.0}

    def test_un_nominal_impose_traverse_le_parcours(
        self, tableau: pd.DataFrame, tmp_path: Path
    ) -> None:
        inventaire = figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            nominaux={"CN": 1.0, "CA": 0.05},
            **LEGER,
        )
        assert len(inventaire) == 1


class TestAccordAvecLeModele:
    """Le seul contrôle du paquet qui porte sur le modèle, pas sur le tirage."""

    def test_l_inventaire_porte_le_verdict(
        self, tableau: pd.DataFrame, reference: pd.DataFrame, tmp_path: Path
    ) -> None:
        inventaire = figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            reference=reference,
            max_tirages=1,
        )
        coefficients = inventaire[inventaire["figure"] != "matrice"]
        assert coefficients["accord"].all()
        assert coefficients["ecart"].abs().max() < 1e-12

    def test_un_modele_qui_derape_est_repere(
        self, tableau: pd.DataFrame, reference: pd.DataFrame, tmp_path: Path
    ) -> None:
        """Une convention différente de part et d'autre, et rien ne le dirait."""
        faux = tableau.copy()
        faux["CN"] = faux["CN"] * 1.01
        inventaire = figures_tirage_par_pdv(
            faux,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            reference=reference,
            max_tirages=1,
        )
        verdicts = inventaire.set_index("figure")["accord"]
        assert not verdicts["CN"]
        assert verdicts["CA"]

    def test_sans_nominal_il_n_y_a_pas_de_verdict(
        self, tableau: pd.DataFrame, tmp_path: Path
    ) -> None:
        """Rien à recalculer, donc rien à confronter."""
        inventaire = figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            max_tirages=1,
        )
        coefficients = inventaire[inventaire["figure"] != "matrice"]
        assert coefficients["accord"].isna().all()


def _renommer_dans_les_dicts(table: pd.DataFrame, ancien: str, nouveau: str) -> pd.DataFrame:
    """Rebaptise un coefficient dans les lois et les tirages, pas les colonnes."""
    copie = table.copy()
    for colonne in ("DICT_LAW_DISPERSION", "DICT_TIRAGE"):
        copie[colonne] = pd.Series(
            [
                {(nouveau if cle == ancien else cle): valeur for cle, valeur in dico.items()}
                for dico in table[colonne]
            ],
            index=copie.index,
            dtype=object,
        )
    return copie


class TestLoisEtSortiesDecalees:
    """Les lois dispersent ce que le modèle consomme, pas ce qu'il rend.

    Un coefficient interne — ``CX0`` — a des lois mais aucune colonne de
    sortie ; le coefficient rendu — ``CA`` — a une colonne mais aucune loi. Les
    deux listes ne coïncident pas, et c'est le cas courant.
    """

    @pytest.fixture
    def decale(self, tableau: pd.DataFrame) -> pd.DataFrame:
        return _renommer_dans_les_dicts(tableau, "CA", "CX0")

    @pytest.fixture
    def decale_reference(self, reference: pd.DataFrame) -> pd.DataFrame:
        return _renommer_dans_les_dicts(reference, "CA", "CX0")

    def test_un_coefficient_sans_sortie_garde_ses_deux_premiers_panneaux(
        self, decale: pd.DataFrame, decale_reference: pd.DataFrame, tmp_path: Path
    ) -> None:
        """Les lois de ses composantes ne dépendent d'aucun nominal."""
        inventaire = figures_tirage_par_pdv(
            decale,
            points_de_vol={"Mach": [0.85], "Altitude_m": [10_000.0]},
            racine=tmp_path,
            reference=decale_reference,
            max_tirages=1,
        )
        assert "CX0" in set(inventaire["figure"])
        assert (tmp_path / "tirage_000" / "CX0.svg").is_file()

    def test_il_n_a_ni_nominal_ni_verdict(
        self, decale: pd.DataFrame, decale_reference: pd.DataFrame, tmp_path: Path
    ) -> None:
        """Pas de colonne de sortie : rien à comparer, et la figure le dit."""
        inventaire = figures_tirage_par_pdv(
            decale,
            points_de_vol={"Mach": [0.85], "Altitude_m": [10_000.0]},
            racine=tmp_path,
            reference=decale_reference,
            max_tirages=1,
        ).set_index("figure")
        assert pd.isna(inventaire.loc["CX0", "accord"])
        # Les autres, eux, sont bien confrontés au modèle.
        assert inventaire.loc["CN", "accord"]

    def test_un_coefficient_de_sortie_sans_lois_n_est_pas_trace(
        self, decale: pd.DataFrame, decale_reference: pd.DataFrame, tmp_path: Path
    ) -> None:
        """Sans biais ni FE, il n'y a pas de figure de tirage à faire."""
        inventaire = figures_tirage_par_pdv(
            decale,
            points_de_vol={"Mach": [0.85], "Altitude_m": [10_000.0]},
            racine=tmp_path,
            reference=decale_reference,
            max_tirages=1,
        )
        assert "CA" not in set(inventaire["figure"])

    def test_le_demander_explicitement_le_trace_sans_loi(
        self, decale: pd.DataFrame, decale_reference: pd.DataFrame, tmp_path: Path
    ) -> None:
        """Sans loi il n'y a pas de tirage — mais il reste un nominal et une valeur."""
        inventaire = figures_tirage_par_pdv(
            decale,
            points_de_vol={"Mach": [0.85], "Altitude_m": [10_000.0]},
            racine=tmp_path,
            reference=decale_reference,
            coefficients=["CA"],
            matrice=False,
            max_tirages=1,
        )
        assert list(inventaire["figure"]) == ["CA"]
        assert (tmp_path / "tirage_000" / "CA.svg").is_file()

    def test_un_coefficient_inconnu_partout_est_refuse(self, decale: pd.DataFrame) -> None:
        """Ni loi ni colonne : il n'y a rien à en dire, et le refus le nomme."""
        with pytest.raises(ValueError, match="ni loi"):
            figures_tirage_par_pdv(
                decale,
                points_de_vol={"Mach": [0.85]},
                racine="/tmp/x",
                coefficients=["CL"],
            )


class TestReferenceAmbigue:
    def test_deux_nominaux_pour_un_point_de_vol_sont_refuses(
        self, tableau: pd.DataFrame, tmp_path: Path
    ) -> None:
        """Le point de vol est sous-défini : le dire, plutôt qu'en choisir un."""
        double = pd.DataFrame(
            [
                {"Mach": 0.85, "Altitude_m": 0.0, "CN": 0.80, "CA": 0.03},
                {"Mach": 0.85, "Altitude_m": 10_000.0, "CN": 0.87, "CA": 0.03},
            ]
        )
        with pytest.raises(ValueError, match="2 valeurs de 'CN'"):
            figures_tirage_par_pdv(
                tableau,
                points_de_vol={"Mach": [0.85]},
                racine=tmp_path,
                reference=double,
                max_tirages=1,
            )

    def test_le_message_nomme_les_cles_qui_manquent(
        self, tableau: pd.DataFrame, tmp_path: Path
    ) -> None:
        double = pd.DataFrame(
            [
                {"Mach": 0.85, "Altitude_m": 0.0, "CN": 0.80},
                {"Mach": 0.85, "Altitude_m": 10_000.0, "CN": 0.87},
            ]
        )
        with pytest.raises(ValueError, match="Altitude_m"):
            figures_tirage_par_pdv(
                tableau,
                points_de_vol={"Mach": [0.85]},
                racine=tmp_path,
                reference=double,
                max_tirages=1,
            )


class TestFormesDeTableau:
    def test_le_tableau_large_est_relu(self, tableau: pd.DataFrame, tmp_path: Path) -> None:
        """Les lois viennent du tableau : personne n'a redonné la table."""
        inventaire = figures_tirage_par_pdv(
            tableau, points_de_vol={"Mach": [0.85]}, racine=tmp_path, **LEGER
        )
        assert len(inventaire) == 1

    def test_la_numerotation_du_modele_est_gardee(
        self, tableau: pd.DataFrame, tmp_path: Path
    ) -> None:
        """Le dossier « tirage_007 » doit être le tirage 7 du tableau."""
        decale = tableau.copy()
        decale["tirage"] = decale["tirage"] + 100
        inventaire = figures_tirage_par_pdv(
            decale,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            par_coefficient=False,
            max_tirages=2,
        )
        assert sorted(inventaire["tirage"].unique()) == [100, 101]
        assert (tmp_path / "tirage_100" / "matrice.svg").is_file()

    def test_un_tableau_a_plat_demande_ses_lois(
        self, tableau: pd.DataFrame, lois_deux: JeuDeLois, tmp_path: Path
    ) -> None:
        plat = tableau.drop(columns=["DICT_LAW_DISPERSION", "DICT_TIRAGE"])
        plat = plat.assign(CN_Biais=0.001, CN_FE=1.01, CA_Biais=0.0001, CA_FE=0.99)
        inventaire = figures_tirage_par_pdv(
            plat,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            lois=lois_deux,
            **LEGER,
        )
        assert len(inventaire) == 1

    def test_un_tableau_a_plat_sans_lois_est_refuse(self, tableau: pd.DataFrame) -> None:
        plat = tableau.drop(columns=["DICT_LAW_DISPERSION", "DICT_TIRAGE"])
        with pytest.raises(ValueError, match="lois introuvables"):
            figures_tirage_par_pdv(plat, points_de_vol={"Mach": [0.85]}, racine="/tmp/x")


class TestRefus:
    def test_un_points_de_vol_vide_est_refuse(self, tableau: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="points_de_vol est vide"):
            figures_tirage_par_pdv(tableau, points_de_vol={}, racine="/tmp/x")

    def test_une_colonne_absente_est_refusee(self, tableau: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="Reynolds"):
            figures_tirage_par_pdv(tableau, points_de_vol={"Reynolds": [6e6]}, racine="/tmp/x")

    def test_un_point_de_vol_sans_ligne_est_refuse(self, tableau: pd.DataFrame) -> None:
        """Se taire ferait croire à un parcours réussi et vide."""
        with pytest.raises(ValueError, match="aucun point de vol"):
            figures_tirage_par_pdv(tableau, points_de_vol={"Mach": [0.95]}, racine="/tmp/x")

    def test_un_coefficient_inconnu_est_refuse(self, tableau: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="ni loi"):
            figures_tirage_par_pdv(
                tableau,
                points_de_vol={"Mach": [0.85]},
                racine="/tmp/x",
                coefficients=["CL"],
            )


class TestParallelisme:
    def test_le_travail_se_serialise(self, tableau: pd.DataFrame, tmp_path: Path) -> None:
        """Sans quoi ``n_jobs`` retomberait à un seul cœur, en silence."""
        travail = _Travail(
            point={"Mach": 0.85},
            numero=0,
            tirage=tirer_lot(charger_lois(TABLE), 1, graine=1)[0],
            lois=charger_lois(TABLE),
            coefficients=("CN",),
            nominaux={"CN": 0.85},
            disperses_modele={"CN": 0.83},
            dossier=tmp_path,
            etiquette="M = 0.85",
            formats=("svg",),
            par_coefficient=True,
            matrice=False,
            convention=convention(),
            sigmas=(1, 2, 3),
            max_par_figure=4,
            tolerance=1e-6,
            profil="notebook",
        )
        assert pickle.loads(pickle.dumps(travail)).numero == 0

    def test_deux_processus_donnent_le_meme_inventaire(
        self, tableau: pd.DataFrame, tmp_path: Path
    ) -> None:
        commun: dict[str, Any] = {"points_de_vol": {"Mach": [0.70, 0.85]}, **LEGER}
        seul = figures_tirage_par_pdv(tableau, racine=tmp_path / "a", **commun)
        deux = figures_tirage_par_pdv(tableau, racine=tmp_path / "b", n_jobs=2, **commun)
        assert list(seul["figure"]) == list(deux["figure"])
        assert list(seul["tirage"]) == list(deux["tirage"])

    def test_le_main_de_l_appelant_n_est_pas_rejoue(self, tmp_path: Path) -> None:
        """La régression qui a motivé l'abandon de ``forkserver``.

        ``forkserver`` emporte les données de préparation de ``spawn`` : chaque
        ouvrier réexécutait le script appelant. Selon le point d'entrée, cela
        allait du travail refait n fois au ``BrokenProcessPool`` sans rapport
        visible avec la cause. Le témoin est une ligne écrite au niveau module :
        il doit y en avoir **une**, quel que soit le nombre d'ouvriers.
        """
        temoin = tmp_path / "temoin.txt"
        script = tmp_path / "appelant.py"
        script.write_text(
            textwrap.dedent(f"""
            import os
            import numpy as np, pandas as pd

            with open({str(temoin)!r}, "a") as fichier:
                fichier.write(f"{{os.getpid()}}\\n")

            from cfd_dispersion import charger_lois, tirer_tableau
            from cfd_dispersion.figures.par_pdv import figures_tirage_par_pdv

            TABLE = {TABLE!r}

            def main():
                lois = charger_lois(TABLE)
                lot = tirer_tableau(lois, 2, graine=1)
                lot["CN"] = 0.85 + lot["CN_Biais"] + (lot["CN_FE"] - 1) * 0.85
                lot["CA"] = 0.03 + lot["CA_Biais"] + (lot["CA_FE"] - 1) * 0.03
                lot["Mach"] = 0.85
                lot["tirage"] = np.arange(2)
                reference = pd.DataFrame({{"Mach": [0.85], "CN": [0.85], "CA": [0.03]}})
                figures_tirage_par_pdv(
                    lot,
                    points_de_vol={{"Mach": [0.85]}},
                    racine={str(tmp_path / "FIGURES")!r},
                    lois=lois,
                    reference=reference,
                    coefficients=["CN"],
                    matrice=False,
                    n_jobs=2,
                )

            if __name__ == "__main__":
                main()
            """)
        )
        acheve = subprocess.run(
            [sys.executable, str(script)], capture_output=True, text=True, timeout=600
        )
        assert acheve.returncode == 0, acheve.stderr
        executions = temoin.read_text().splitlines()
        assert len(executions) == 1, f"__main__ rejoué {len(executions)} fois : {executions}"

    def test_l_ouvrier_dessine_sans_fenetre(self) -> None:
        """Un ouvrier n'a pas d'affichage ; le backend hérité peut en vouloir un."""
        avant = matplotlib.get_backend()
        try:
            _init_ouvrier()
            assert matplotlib.get_backend().lower() == "agg"
        finally:
            matplotlib.use(avant)

    def test_le_backend_de_l_appelant_survit_au_parcours(
        self, tableau: pd.DataFrame, tmp_path: Path
    ) -> None:
        """L'initializer ne tourne que dans les ouvriers, jamais ici.

        Un ``matplotlib.use("Agg")`` posé dans la fonction de travail tournerait
        aussi en direct à ``n_jobs=1`` et casserait le tracé interactif de
        l'appelant pour tout ce qu'il ferait ensuite.
        """
        avant = matplotlib.get_backend()
        figures_tirage_par_pdv(tableau, points_de_vol={"Mach": [0.85]}, racine=tmp_path, **LEGER)
        assert matplotlib.get_backend() == avant


class TestMainRejouable:
    """Le garde-fou des plateformes où le démarrage n'est pas ``fork``."""

    def test_sous_fork_il_n_y_a_rien_a_verifier(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import multiprocessing

        monkeypatch.setattr(multiprocessing, "get_start_method", lambda **_: "fork")
        assert _main_rejouable() is None

    def test_un_main_qui_n_est_pas_un_fichier_est_refuse(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import multiprocessing
        import types

        monkeypatch.setattr(multiprocessing, "get_start_method", lambda **_: "forkserver")
        faux = types.ModuleType("__main__")
        faux.__file__ = "<stdin>"
        faux.__spec__ = None
        monkeypatch.setitem(sys.modules, "__main__", faux)
        motif = _main_rejouable()
        assert motif is not None
        assert "<stdin>" in motif
        assert "n_jobs=1" in motif

    def test_un_vrai_script_passe(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        import multiprocessing
        import types

        script = tmp_path / "appelant.py"
        script.write_text("pass\n")
        monkeypatch.setattr(multiprocessing, "get_start_method", lambda **_: "spawn")
        faux = types.ModuleType("__main__")
        faux.__file__ = str(script)
        faux.__spec__ = None
        monkeypatch.setitem(sys.modules, "__main__", faux)
        assert _main_rejouable() is None

    def test_python_m_paquet_passe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``python -m`` : l'ouvrier réimporte le module par son nom."""
        import multiprocessing
        import types

        monkeypatch.setattr(multiprocessing, "get_start_method", lambda **_: "spawn")
        faux = types.ModuleType("__main__")
        faux.__file__ = "<stdin>"
        faux.__spec__ = types.SimpleNamespace(name="mon_paquet.__main__")  # type: ignore[assignment]
        monkeypatch.setitem(sys.modules, "__main__", faux)
        assert _main_rejouable() is None


class TestNettoyage:
    def test_il_efface_les_figures_d_avant(self, tableau: pd.DataFrame, tmp_path: Path) -> None:
        vieille = tmp_path / "MACH_0.7" / "tirage_000" / "vieille.svg"
        vieille.parent.mkdir(parents=True)
        vieille.write_text("<svg/>")
        figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            nettoyer=True,
            **LEGER,
        )
        assert not vieille.exists()


# ---------------------------------------------------------------------------
# La liste des coefficients
# ---------------------------------------------------------------------------


class TestCoefficientsEnPlus:
    """``coefficients=`` remplace la liste par défaut ; ``en_plus`` s'y ajoute."""

    def test_par_defaut_ce_sont_les_lois(self, tableau: pd.DataFrame, tmp_path: Path) -> None:
        inventaire = figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            matrice=False,
            max_tirages=1,
            a_blanc=True,
            rapport=False,
        )
        assert sorted(set(inventaire["figure"])) == ["CA", "CN"]

    def test_coefficients_remplace(self, tableau: pd.DataFrame, tmp_path: Path) -> None:
        inventaire = figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            coefficients=["CN"],
            matrice=False,
            max_tirages=1,
            a_blanc=True,
            rapport=False,
        )
        assert sorted(set(inventaire["figure"])) == ["CN"]

    def test_en_plus_s_ajoute_au_defaut(self, tableau: pd.DataFrame, tmp_path: Path) -> None:
        """Le cas d'usage : une colonne de sortie de plus, sans réécrire la liste."""
        avec_colonne = tableau.assign(CY=0.004)
        inventaire = figures_tirage_par_pdv(
            avec_colonne,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            coefficients_en_plus=["CY"],
            matrice=False,
            max_tirages=1,
            a_blanc=True,
            rapport=False,
        )
        assert sorted(set(inventaire["figure"])) == ["CA", "CN", "CY"]

    def test_en_plus_s_ajoute_aussi_a_une_liste_donnee(
        self, tableau: pd.DataFrame, tmp_path: Path
    ) -> None:
        inventaire = figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            coefficients=["CN"],
            coefficients_en_plus=["CA"],
            matrice=False,
            max_tirages=1,
            a_blanc=True,
            rapport=False,
        )
        assert list(inventaire["figure"]) == ["CN", "CA"]

    def test_un_doublon_ne_double_pas_la_figure(
        self, tableau: pd.DataFrame, tmp_path: Path
    ) -> None:
        inventaire = figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            coefficients_en_plus=["CN"],
            matrice=False,
            max_tirages=1,
            a_blanc=True,
            rapport=False,
        )
        assert list(inventaire["figure"]) == ["CN", "CA"]


# ---------------------------------------------------------------------------
# Les relations
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tableau_relations(lois_deux: JeuDeLois) -> pd.DataFrame:
    """Un modèle qui rend ``CT = CN + CA``, sans loi ni colonne de composantes."""
    return _avec_cible(_tableau_module(lois_deux))


@pytest.fixture(scope="module")
def reference_relations(lois_deux: JeuDeLois) -> pd.DataFrame:
    return _avec_cible(_reference_module(lois_deux))


def _tableau_module(lois_deux: JeuDeLois) -> pd.DataFrame:
    lot = tirer_lot(lois_deux, 2, graine=42)
    return pd.DataFrame(
        [
            {
                "Mach": mach,
                **{coeff: float(v) for coeff, v in tirage.appliquer(nominaux).items()},
                "DICT_LAW_DISPERSION": TABLE,
                "DICT_TIRAGE": tirage.vers_dict(),
                "tirage": tirage.numero,
            }
            for mach, nominaux in NOMINAUX.items()
            for tirage in lot
        ]
    )


def _reference_module(lois_deux: JeuDeLois) -> pd.DataFrame:
    neutre = tirage_neutre(lois_deux)
    return pd.DataFrame(
        [
            {
                "Mach": mach,
                **{coeff: float(v) for coeff, v in neutre.appliquer(nominaux).items()},
                "DICT_LAW_DISPERSION": TABLE,
                "DICT_TIRAGE": neutre.vers_dict(),
                "tirage": 0,
            }
            for mach, nominaux in NOMINAUX.items()
        ]
    )


def _avec_cible(table: pd.DataFrame) -> pd.DataFrame:
    return table.assign(CT=table["CN"] + table["CA"])


class TestRelations:
    def test_la_cible_rejoint_la_liste_par_defaut(
        self, tableau_relations: pd.DataFrame, reference_relations: pd.DataFrame, tmp_path: Path
    ) -> None:
        inventaire = figures_tirage_par_pdv(
            tableau_relations,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            reference=reference_relations,
            relations={"CT": "CN + CA"},
            matrice=False,
            max_tirages=1,
            a_blanc=True,
            rapport=False,
        )
        assert sorted(set(inventaire["figure"])) == ["CA", "CN", "CT"]

    def test_la_cible_est_tracee_et_confrontee_au_modele(
        self, tableau_relations: pd.DataFrame, reference_relations: pd.DataFrame, tmp_path: Path
    ) -> None:
        """Le contrôle porte alors sur la RELATION : les composantes viennent
        de la dérivation, la valeur vient du modèle."""
        inventaire = figures_tirage_par_pdv(
            tableau_relations,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            reference=reference_relations,
            relations={"CT": "CN + CA"},
            coefficients=["CT"],
            matrice=False,
            max_tirages=1,
            rapport=False,
        )
        ligne = inventaire.iloc[0]
        assert ligne["figure"] == "CT"
        assert bool(ligne["accord"]) is True
        assert Path(str(ligne["fichier"])).exists()

    def test_une_relation_fausse_est_refusee(
        self, tableau_relations: pd.DataFrame, reference_relations: pd.DataFrame, tmp_path: Path
    ) -> None:
        """La référence porte CT ; une relation qui en donne une autre valeur
        rendrait toutes les lois dérivées fausses sans que rien ne le dise."""
        with pytest.raises(ValueError, match="n'est pas celle qu'applique le modèle"):
            figures_tirage_par_pdv(
                tableau_relations,
                points_de_vol={"Mach": [0.85]},
                racine=tmp_path,
                reference=reference_relations,
                relations={"CT": "CN - CA"},
                coefficients=["CT"],
                matrice=False,
                max_tirages=1,
                rapport=False,
            )

    def test_le_point_de_vol_est_nomme_dans_le_refus(
        self, tableau_relations: pd.DataFrame, tmp_path: Path
    ) -> None:
        """Sans référence, les nominaux des sources manquent — et on le dit."""
        with pytest.raises(ValueError, match=r"Mach = 0\.85"):
            figures_tirage_par_pdv(
                tableau_relations,
                points_de_vol={"Mach": [0.85]},
                racine=tmp_path,
                relations={"CT": "CN + CA"},
                coefficients=["CT"],
                matrice=False,
                max_tirages=1,
                rapport=False,
            )

    def test_une_cible_absente_du_tableau_reste_tracable(
        self, tableau_relations: pd.DataFrame, reference_relations: pd.DataFrame, tmp_path: Path
    ) -> None:
        """Une cible que le modèle ne rend pas garde ses deux premiers panneaux."""
        inventaire = figures_tirage_par_pdv(
            tableau_relations,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            reference=reference_relations,
            relations={"CU": "2*CN"},
            coefficients=["CU"],
            matrice=False,
            max_tirages=1,
            rapport=False,
        )
        assert list(inventaire["figure"]) == ["CU"]
        assert pd.isna(inventaire.iloc[0]["accord"])


# ---------------------------------------------------------------------------
# Le rendu terminal
# ---------------------------------------------------------------------------


class TestRenduTerminal:
    """Les trois arguments repris de ``batch_plot`` : verbose/report/dry_run."""

    def test_a_blanc_n_ecrit_rien(self, tableau: pd.DataFrame, tmp_path: Path) -> None:
        inventaire = figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            a_blanc=True,
            rapport=False,
            **LEGER,
        )
        assert not inventaire.empty
        assert not any(Path(str(chemin)).exists() for chemin in inventaire["fichier"])

    def test_a_blanc_enumere_ce_qui_serait_ecrit(
        self, tableau: pd.DataFrame, tmp_path: Path
    ) -> None:
        """L'énumération et l'exécution doivent composer les mêmes noms."""
        commun: dict[str, Any] = {
            "points_de_vol": {"Mach": [0.85]},
            "racine": tmp_path,
            "max_tirages": 1,
            "rapport": False,
        }
        prevus = figures_tirage_par_pdv(tableau, a_blanc=True, **commun)
        ecrits = figures_tirage_par_pdv(tableau, **commun)
        assert list(prevus["fichier"]) == list(ecrits["fichier"])

    def test_a_blanc_ne_nettoie_pas(self, tableau: pd.DataFrame, tmp_path: Path) -> None:
        vieille = tmp_path / "MACH_0.85" / "vieille.svg"
        vieille.parent.mkdir(parents=True)
        vieille.write_text("<svg/>")
        figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            nettoyer=True,
            a_blanc=True,
            rapport=False,
            **LEGER,
        )
        assert vieille.exists()

    def test_verbeux_imprime_le_plan(
        self, tableau: pd.DataFrame, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            verbeux=True,
            a_blanc=True,
            rapport=False,
            **LEGER,
        )
        sortie = capsys.readouterr().out
        assert "Plan du parcours" in sortie
        assert "Coefficients" in sortie

    def test_le_plan_nomme_les_relations(
        self,
        tableau_relations: pd.DataFrame,
        reference_relations: pd.DataFrame,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        figures_tirage_par_pdv(
            tableau_relations,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            reference=reference_relations,
            relations={"CT": "CN + CA"},
            verbeux=True,
            a_blanc=True,
            rapport=False,
            **LEGER,
        )
        assert "CT = CN + CA" in capsys.readouterr().out

    def test_le_rapport_liste_les_fichiers(
        self, tableau: pd.DataFrame, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            rapport=True,
            **LEGER,
        )
        sortie = capsys.readouterr().out
        assert "matrice" in sortie
        assert "ko" in sortie

    def test_le_rapport_se_tait_quand_on_le_lui_demande(
        self, tableau: pd.DataFrame, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        figures_tirage_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            rapport=False,
            **LEGER,
        )
        assert capsys.readouterr().out == ""
