"""Le contrôle de bout en bout : lire, appeler, comparer, diagnostiquer.

L'invariant central du paquet tient en une phrase : **un modèle qui relit
exactement sa table sort zéro point fautif**, à la tolérance la plus serrée
qu'on puisse écrire. Tout le reste en découle — si ce n'était pas vrai, aucun
écart rapporté ne voudrait rien dire.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from cfd_validation.data.entrees import ErreurModele
from cfd_validation.data.spec import SpecTable, charger_tables
from cfd_validation.engine.controle import Controle
from cfd_validation.engine.tables import ControleTables, valider_tables
from cfd_validation.wrap.factice import BUGS, ModeleFactice, ModuleFactice


class TestModeleJuste:
    def test_un_modele_qui_relit_exactement_sort_zero_point_fautif(
        self, module: ModuleFactice, specs: dict[str, SpecTable], modele: ModeleFactice
    ) -> None:
        """L'invariant central. Une interpolation vaut la valeur tabulée à ses nœuds."""
        rapport = valider_tables(module, specs, modele=modele)
        assert rapport.conforme
        assert rapport.n_fautifs == 0
        assert rapport.n_points == 336

    def test_meme_a_la_tolerance_la_plus_serree(
        self, module: ModuleFactice, declarations: dict[str, dict[str, Any]], modele: ModeleFactice
    ) -> None:
        serrees = {
            nom: {**contenu, "rtol": 0.0, "atol": 0.0} for nom, contenu in declarations.items()
        }
        assert valider_tables(module, serrees, modele=modele).conforme

    def test_aucun_motif_n_est_produit_quand_tout_va_bien(
        self, module: ModuleFactice, specs: dict[str, SpecTable], modele: ModeleFactice
    ) -> None:
        rapport = valider_tables(module, specs, modele=modele)
        assert rapport["CN"].grandeur("CN").motifs == ()


class TestPannes:
    @pytest.mark.parametrize("panne,attendu", sorted(BUGS.items()))
    def test_chaque_panne_sort_avec_son_motif_en_tete(
        self,
        panne: str,
        attendu: str,
        module: ModuleFactice,
        specs: dict[str, SpecTable],
    ) -> None:
        """La promesse du rapport : nommer le motif, pas seulement compter."""
        rapport = valider_tables(module, specs, modele=ModeleFactice(module, bug=panne))
        grandeur = rapport["CN"].grandeur("CN")
        assert not grandeur.conforme
        assert grandeur.motif_principal is not None
        assert grandeur.motif_principal.nom == attendu

    def test_oublier_la_cle_lignes_donne_le_motif_qui_nomme_le_remede(
        self, module: ModuleFactice, spec_cn: SpecTable, modele: ModeleFactice
    ) -> None:
        """La panne n'est pas dans le modèle mais dans la déclaration."""
        rapport = valider_tables(module, {"CN": replace(spec_cn, lignes=None)}, modele=modele)
        grandeur = rapport["CN"].grandeur("CN")
        assert grandeur.motif_principal is not None
        assert grandeur.motif_principal.nom == "queue_non_renseignee"
        assert "lignes" in grandeur.motif_principal.message


class TestContratDuModele:
    def test_un_modele_qui_ne_rend_pas_de_dataframe_est_refuse(
        self, module: ModuleFactice, specs: dict[str, SpecTable]
    ) -> None:
        with pytest.raises(ErreurModele, match="DataFrame"):
            valider_tables(module, specs, modele=lambda df: None)

    def test_un_modele_qui_trie_ses_lignes_est_refuse(
        self, module: ModuleFactice, specs: dict[str, SpecTable], modele: ModeleFactice
    ) -> None:
        """Et non rapporté comme un écart : ce serait accuser un modèle juste."""

        def trieur(df: pd.DataFrame) -> pd.DataFrame:
            rendu = modele(df)
            return rendu.sort_values(list(df.columns)[::-1]).reset_index(drop=True)

        with pytest.raises(ErreurModele, match="dans l'ordre reçu"):
            valider_tables(module, specs, modele=trieur)

    def test_le_modele_ne_recoit_jamais_la_qoi(
        self, module: ModuleFactice, specs: dict[str, SpecTable], modele: ModeleFactice
    ) -> None:
        vues: list[list[str]] = []

        def espion(df: pd.DataFrame) -> pd.DataFrame:
            vues.append(list(df.columns))
            return modele(df)

        valider_tables(module, specs, modele=espion)
        assert vues == [["mach", "alpha", "delta"], ["mach", "alpha"]]


class TestRapport:
    def test_les_cadres_sont_pretes_a_tracer(
        self, module: ModuleFactice, specs: dict[str, SpecTable], modele: ModeleFactice
    ) -> None:
        """Mêmes colonnes des deux côtés : c'est ce que ``batch_plot`` consomme."""
        resultat = valider_tables(module, specs, modele=modele)["CN"]
        assert list(resultat.cadre_table.columns) == list(resultat.cadre_modele.columns)
        assert len(resultat.cadre_table) == len(resultat.table)

    def test_une_table_inconnue_est_refusee_en_listant_les_controlees(
        self, module: ModuleFactice, specs: dict[str, SpecTable], modele: ModeleFactice
    ) -> None:
        rapport = valider_tables(module, specs, modele=modele)
        with pytest.raises(KeyError, match="CN"):
            rapport["CY"]

    def test_une_grandeur_inconnue_est_refusee_de_meme(
        self, module: ModuleFactice, specs: dict[str, SpecTable], modele: ModeleFactice
    ) -> None:
        rapport = valider_tables(module, specs, modele=modele)
        with pytest.raises(KeyError, match="CN"):
            rapport["CN"].grandeur("CY")

    def test_le_rapport_s_itere_et_se_compte(
        self, module: ModuleFactice, specs: dict[str, SpecTable], modele: ModeleFactice
    ) -> None:
        rapport = valider_tables(module, specs, modele=modele)
        assert len(rapport) == 2
        assert [resultat.nom for resultat in rapport] == ["CN", "CA"]


class TestPlusieursQoi:
    def test_chaque_qoi_est_comparee_avec_sa_propre_tolerance(self) -> None:
        class Bloc:
            # Quatre lignes, trois colonnes : non carré, donc l'orientation
            # s'infère sans déclaration (cf. wrap/test_bloc.py).
            tab = np.array([[0.0, 1.0, 10.0], [1.0, 2.0, 20.0], [2.0, 3.0, 30.0], [3.0, 4.0, 40.0]])

        class Faux:
            bloc = Bloc()

        specs = charger_tables(
            {
                "T": {
                    "bloc": "bloc",
                    "tableau": "tab",
                    "colonnes": ["x", "A", "B"],
                    "qoi": ["A", "B"],
                    "rtol": 1e-12,
                    "tolerances": {"B": {"rtol": 1e-1}},
                }
            }
        )

        def modele(df: pd.DataFrame) -> pd.DataFrame:
            # A est juste ; B dévie de 5 %, ce que sa tolérance large accepte.
            return df.assign(A=[1.0, 2.0, 3.0, 4.0], B=[10.5, 21.0, 31.5, 42.0])

        resultat = valider_tables(Faux(), specs, modele=modele)["T"]
        assert resultat.grandeur("A").conforme
        assert resultat.grandeur("B").conforme

    def test_un_verdict_est_produit_par_grandeur(self) -> None:
        class Bloc:
            tab = np.array([[0.0, 1.0, 10.0], [1.0, 2.0, 20.0]])

        class Faux:
            bloc = Bloc()

        specs = charger_tables(
            {
                "T": {
                    "bloc": "bloc",
                    "tableau": "tab",
                    "colonnes": ["x", "A", "B"],
                    "qoi": ["A", "B"],
                }
            }
        )
        rapport = valider_tables(
            Faux(), specs, modele=lambda df: df.assign(A=[1.0, 2.0], B=[10.0, 20.0])
        )
        verdicts = rapport.verdicts()
        assert [verdict.grandeur for verdict in verdicts] == ["A", "B"]
        assert all(verdict.conforme for verdict in verdicts)


class TestControle:
    def test_le_controle_respecte_le_protocole(
        self, module: ModuleFactice, specs: dict[str, SpecTable], modele: ModeleFactice
    ) -> None:
        controle = ControleTables(module=module, specs=specs, modele=modele)
        assert isinstance(controle, Controle)
        assert controle.nom == "relecture de tables"

    def test_executer_rend_un_verdict_par_grandeur(
        self, module: ModuleFactice, specs: dict[str, SpecTable], modele: ModeleFactice
    ) -> None:
        verdicts = ControleTables(module=module, specs=specs, modele=modele).executer()
        assert [verdict.sujet for verdict in verdicts] == ["CN", "CA"]

    def test_une_declaration_brute_est_acceptee_comme_une_validee(
        self,
        module: ModuleFactice,
        declarations: dict[str, dict[str, Any]],
        specs: dict[str, SpecTable],
        modele: ModeleFactice,
    ) -> None:
        depuis_brut = valider_tables(module, declarations, modele=modele)
        depuis_specs = valider_tables(module, specs, modele=modele)
        assert depuis_brut.n_points == depuis_specs.n_points
