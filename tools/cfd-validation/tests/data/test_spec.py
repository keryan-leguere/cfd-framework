"""La déclaration des tables : ce qu'elle accepte, et surtout ce qu'elle refuse.

Les refus sont l'essentiel de ce module. Une déclaration fausse et silencieuse
fait passer une table fausse pour bonne — c'est le seul mode de défaillance qui
coûte plus cher que pas de contrôle du tout.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cfd_validation.data.spec import (
    CLES_ADMISES,
    ErreurSpec,
    SpecTable,
    charger_fichier,
    charger_tables,
)


def _minimale(**surcharges: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "bloc": "tab_cn",
        "colonnes": ["mach", "alpha", "CN"],
    }
    base.update(surcharges)
    return base


class TestValeursParDefaut:
    def test_la_derniere_colonne_est_la_qoi_par_defaut(self) -> None:
        """C'est ainsi qu'une table longue se range : la valeur après ses entrées."""
        spec = charger_tables({"CN": _minimale()})["CN"]
        assert spec.qoi == ("CN",)
        assert spec.independantes == ("mach", "alpha")

    def test_le_tableau_prend_le_nom_du_bloc_par_defaut(self) -> None:
        """Cas très fréquent : `COMMON /TAB_CN/ TAB_CN`."""
        assert charger_tables({"CN": _minimale()})["CN"].tableau == "tab_cn"

    def test_une_unite_absente_vaut_le_tiret_attendu_par_cfd_plot(self) -> None:
        spec = charger_tables({"CN": _minimale()})["CN"]
        assert spec.unite("mach") == "-"
        assert spec.libelle("mach") == "mach"

    def test_les_entrees_attendues_sont_les_independantes_puis_les_constantes(self) -> None:
        spec = charger_tables({"CN": _minimale(constantes={"beta": 0.0})})["CN"]
        assert spec.entrees_attendues == ("mach", "alpha", "beta")


class TestTolerances:
    def test_une_tolerance_par_qoi_prime_sur_la_tolerance_de_table(self) -> None:
        spec = charger_tables(
            {
                "T": {
                    "bloc": "b",
                    "colonnes": ["x", "A", "B"],
                    "qoi": ["A", "B"],
                    "rtol": 1e-9,
                    "tolerances": {"B": {"rtol": 1e-3}},
                }
            }
        )["T"]
        assert spec.tolerance("A") == (1e-9, spec.atol)
        assert spec.tolerance("B")[0] == 1e-3

    def test_une_tolerance_pour_une_non_qoi_est_refusee(self) -> None:
        with pytest.raises(ErreurSpec, match="qui n'est pas une QOI"):
            charger_tables({"T": _minimale(tolerances={"mach": {"rtol": 1e-3}})})


class TestRefus:
    def test_une_cle_inconnue_est_refusee_en_listant_les_cles_admises(self) -> None:
        """`rtl: 1e-3` laisserait sinon la tolérance par défaut, en silence."""
        with pytest.raises(ErreurSpec) as capture:
            charger_tables({"CN": _minimale(rtl=1e-3)})
        message = str(capture.value)
        assert "rtl" in message
        assert "rtol" in message  # les clés admises sont listées
        assert "CN" in message  # la table fautive est nommée

    def test_toutes_les_cles_admises_sont_effectivement_acceptees(self) -> None:
        """Le refus ne doit pas se retourner contre une déclaration complète."""
        complete = {
            "bloc": "b",
            "tableau": "t",
            "colonnes": ["x", "y", "A"],
            "qoi": ["A"],
            "lignes": 3,
            "constantes": {"z": 1.0},
            "orientation": "lignes",
            "rtol": 1e-8,
            "atol": 1e-11,
            "tolerances": {"A": {"rtol": 1e-6, "atol": 1e-9}},
            "libelles": {"x": "X"},
            "unites": {"x": "m"},
        }
        assert set(complete) == CLES_ADMISES
        charger_tables({"T": complete})

    def test_un_bloc_manquant_est_refuse(self) -> None:
        with pytest.raises(ErreurSpec, match="« bloc » est obligatoire"):
            charger_tables({"CN": {"colonnes": ["x", "y"]}})

    def test_des_colonnes_en_double_sont_refusees(self) -> None:
        with pytest.raises(ErreurSpec, match="en double"):
            charger_tables({"CN": _minimale(colonnes=["x", "x", "CN"])})

    def test_une_qoi_absente_des_colonnes_est_refusee(self) -> None:
        with pytest.raises(ErreurSpec, match="absente"):
            charger_tables({"CN": _minimale(qoi=["CY"])})

    def test_une_table_toute_en_qoi_est_refusee(self) -> None:
        """Sans variable indépendante, il n'y a pas de table, juste une liste."""
        with pytest.raises(ErreurSpec, match="au moins une"):
            charger_tables({"CN": _minimale(colonnes=["A", "B"], qoi=["A", "B"])})

    def test_une_constante_qui_double_une_colonne_est_refusee(self) -> None:
        """La table fait foi : laisser passer choisirait silencieusement l'autre."""
        with pytest.raises(ErreurSpec, match="à la fois une colonne"):
            charger_tables({"CN": _minimale(constantes={"mach": 0.8})})

    def test_une_orientation_inconnue_est_refusee(self) -> None:
        with pytest.raises(ErreurSpec, match="orientation"):
            charger_tables({"CN": _minimale(orientation="diagonale")})

    def test_un_nombre_de_lignes_nul_ou_negatif_est_refuse(self) -> None:
        with pytest.raises(ErreurSpec, match="strictement positif"):
            charger_tables({"CN": _minimale(lignes=0)})

    def test_un_booleen_n_est_pas_un_nombre_de_lignes(self) -> None:
        """`True` vaut 1 en Python ; l'accepter rendrait une table à une ligne."""
        with pytest.raises(ErreurSpec, match="booléen"):
            charger_tables({"CN": _minimale(lignes=True)})

    def test_une_tolerance_negative_est_refusee(self) -> None:
        with pytest.raises(ErreurSpec, match="positif"):
            charger_tables({"CN": _minimale(rtol=-1.0)})

    def test_un_libelle_pour_une_colonne_inconnue_est_refuse(self) -> None:
        with pytest.raises(ErreurSpec, match="ni une colonne ni une constante"):
            charger_tables({"CN": _minimale(libelles={"inexistante": "X"})})

    def test_un_dictionnaire_vide_est_refuse(self) -> None:
        with pytest.raises(ErreurSpec, match="vide"):
            charger_tables({})


class TestFichier:
    def test_un_fichier_a_racine_directe_se_charge(self, tmp_path: Path) -> None:
        chemin = tmp_path / "TABLES.yaml"
        chemin.write_text("CN:\n  bloc: b\n  colonnes: [x, CN]\n", encoding="utf-8")
        assert set(charger_fichier(chemin)) == {"CN"}

    def test_un_fichier_sous_la_cle_tables_se_charge_aussi(self, tmp_path: Path) -> None:
        chemin = tmp_path / "TABLES.yaml"
        chemin.write_text("tables:\n  CN:\n    bloc: b\n    colonnes: [x, CN]\n", encoding="utf-8")
        assert set(charger_fichier(chemin)) == {"CN"}

    def test_un_fichier_absent_sort_en_erreur_nommee(self, tmp_path: Path) -> None:
        with pytest.raises(ErreurSpec, match="introuvable"):
            charger_fichier(tmp_path / "nulle-part.yaml")

    def test_un_yaml_invalide_sort_en_erreur_nommee(self, tmp_path: Path) -> None:
        chemin = tmp_path / "TABLES.yaml"
        chemin.write_text("CN: [\n", encoding="utf-8")
        with pytest.raises(ErreurSpec, match="YAML"):
            charger_fichier(chemin)


class TestSpecLivree:
    def test_la_declaration_du_module_factice_est_valide(self, specs: dict[str, SpecTable]) -> None:
        """Ce que la documentation montre doit d'abord tenir debout."""
        assert set(specs) == {"CN", "CA"}
        assert specs["CN"].independantes == ("mach", "alpha", "delta")
        assert specs["CN"].lignes == "npt_cn"
