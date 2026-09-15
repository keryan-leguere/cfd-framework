"""La lecture d'un COMMON block : résolution des noms, orientation, longueur utile.

Le contrat est un simple accès par attribut, et c'est ce qui rend ces tests
possibles sans compilateur. Les cas éprouvés ici sont ceux qu'un vrai module
f2py présente : noms en minuscules, tableau dimensionné large, compteur rangé
dans le bloc, tableau Fortran-contigu.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from cfd_validation.data.spec import SpecTable, charger_tables
from cfd_validation.wrap.bloc import ErreurBloc, blocs_exposes, lire_table, lire_tableau
from cfd_validation.wrap.factice import BlocCommun, ModuleFactice


def _spec(**surcharges: Any) -> SpecTable:
    base: dict[str, Any] = {"bloc": "bloc", "colonnes": ["x", "y", "V"]}
    base.update(surcharges)
    return charger_tables({"T": base})["T"]


def _module(**membres: Any) -> Any:
    class Faux:
        pass

    faux = Faux()
    faux.bloc = BlocCommun(**membres)  # type: ignore[attr-defined]
    return faux


#: Quatre points, trois colonnes. Volontairement **non carré** : un tableau
#: carré rend l'orientation ambiguë, ce qui est un cas à part, éprouvé plus bas.
LIGNES = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 2.0], [1.0, 0.0, 3.0], [1.0, 1.0, 4.0]])


class TestLecture:
    def test_un_tableau_en_lignes_se_lit_tel_quel(self) -> None:
        table = lire_table(_module(bloc=LIGNES), _spec())
        assert list(table.columns) == ["x", "y", "V"]
        assert table["V"].tolist() == [1.0, 2.0, 3.0, 4.0]

    def test_le_nom_du_tableau_prime_sur_celui_du_bloc(self) -> None:
        module = _module(donnees=LIGNES)
        assert len(lire_table(module, _spec(tableau="donnees"))) == 4

    def test_les_noms_se_resolvent_sans_tenir_compte_de_la_casse(self) -> None:
        """f2py met tout en minuscules ; le Fortran, lui, s'écrit en capitales."""
        table = lire_table(_module(bloc=LIGNES), _spec(bloc="BLOC", tableau="BLOC"))
        assert len(table) == 4

    def test_un_tableau_fortran_contigu_se_lit_comme_un_autre(self) -> None:
        """C'est la forme que f2py rend réellement."""
        module = _module(bloc=np.asfortranarray(LIGNES))
        assert lire_table(module, _spec())["V"].tolist() == [1.0, 2.0, 3.0, 4.0]


class TestOrientation:
    def test_l_orientation_s_infere_de_la_dimension_qui_correspond(self) -> None:
        """3 colonnes déclarées, un tableau 3×4 : il ne peut être qu'en colonnes."""
        assert lire_tableau(_module(bloc=LIGNES.T), _spec()).shape == (4, 3)

    def test_une_orientation_declaree_prime_sur_l_inference(self) -> None:
        module = _module(bloc=LIGNES.T)
        assert lire_tableau(module, _spec(orientation="colonnes")).shape == (4, 3)

    def test_un_tableau_carre_exige_une_orientation_declaree(self) -> None:
        """La deviner reviendrait à tirer au sort la lecture de toute la table."""
        module = _module(bloc=np.zeros((3, 3)))
        with pytest.raises(ErreurBloc, match="orientation"):
            lire_tableau(module, _spec())

    def test_un_tableau_dont_aucune_dimension_ne_correspond_est_refuse(self) -> None:
        module = _module(bloc=np.zeros((5, 4)))
        with pytest.raises(ErreurBloc, match="ni l'une ni l'autre"):
            lire_tableau(module, _spec())

    def test_un_tableau_a_trois_dimensions_est_refuse_avec_une_explication(self) -> None:
        module = _module(bloc=np.zeros((2, 3, 4)))
        with pytest.raises(ErreurBloc, match="table « longue »"):
            lire_tableau(module, _spec())

    def test_un_vecteur_est_refuse_en_disant_ce_qu_on_attendait(self) -> None:
        with pytest.raises(ErreurBloc, match="vecteur"):
            lire_tableau(_module(bloc=np.zeros(5)), _spec())


class TestLignesUtiles:
    def test_un_compteur_nomme_rogne_la_queue(self) -> None:
        tableau = np.full((9, 3), -999.0)
        tableau[:4] = LIGNES
        module = _module(bloc=tableau, npt=np.array(4))
        assert len(lire_table(module, _spec(lignes="npt"))) == 4

    def test_un_entier_litteral_rogne_aussi(self) -> None:
        tableau = np.full((9, 3), -999.0)
        tableau[:4] = LIGNES
        assert len(lire_table(_module(bloc=tableau), _spec(lignes=4))) == 4

    def test_sans_compteur_la_queue_reste_et_c_est_voulu(self) -> None:
        """Rogner les lignes nulles supprimerait un nœud légitimement nul.

        Le détecteur ``queue_non_renseignee`` rattrape le cas et nomme le remède.
        """
        tableau = np.full((9, 3), -999.0)
        tableau[:4] = LIGNES
        assert len(lire_table(_module(bloc=tableau), _spec())) == 9

    def test_un_compteur_plus_grand_que_le_tableau_est_refuse(self) -> None:
        with pytest.raises(ErreurBloc, match="n'en porte que"):
            lire_table(_module(bloc=LIGNES), _spec(lignes=99))

    def test_un_compteur_nul_est_refuse_en_suggerant_la_cause(self) -> None:
        module = _module(bloc=LIGNES, npt=np.array(0))
        with pytest.raises(ErreurBloc, match="initialisé"):
            lire_table(module, _spec(lignes="npt"))

    def test_un_compteur_introuvable_est_refuse(self) -> None:
        with pytest.raises(ErreurBloc, match="introuvable"):
            lire_table(_module(bloc=LIGNES), _spec(lignes="npt_absent"))


class TestMessages:
    def test_un_bloc_introuvable_liste_ce_que_le_module_expose(self) -> None:
        """La seule information utile à ce moment-là, et elle évite un aller-retour."""
        with pytest.raises(ErreurBloc) as capture:
            lire_table(_module(bloc=LIGNES), _spec(bloc="tab_absent"))
        assert "bloc" in str(capture.value)

    def test_un_tableau_introuvable_liste_les_membres_du_bloc(self) -> None:
        with pytest.raises(ErreurBloc) as capture:
            lire_table(_module(bloc=LIGNES, npt=np.array(3)), _spec(tableau="absent"))
        message = str(capture.value)
        assert "npt" in message and "bloc" in message

    def test_un_membre_qui_n_est_pas_un_tableau_est_refuse(self) -> None:
        with pytest.raises(ErreurBloc, match="n'est pas un tableau"):
            lire_table(_module(bloc="du texte"), _spec())


class TestInspection:
    def test_les_blocs_du_module_factice_sont_trouves(self, module: ModuleFactice) -> None:
        blocs = blocs_exposes(module)
        assert set(blocs) == {"tab_cn", "tab_ca"}
        assert set(blocs["tab_cn"]) == {"tab_cn", "npt_cn"}

    def test_un_objet_appelable_portant_des_tableaux_compte_comme_un_bloc(self) -> None:
        """Un COMMON block f2py **est** appelable — même type que les routines.

        Les distinguer là-dessus ferait disparaître tous les blocs d'un vrai
        module compilé ; ce qui les sépare est ce qu'ils portent.
        """

        class BlocAppelable:
            tab = np.zeros((2, 2))

            def __call__(self) -> None:  # pragma: no cover - jamais appelé
                ...

        class Faux:
            pass

        faux = Faux()
        faux.bloc = BlocAppelable()  # type: ignore[attr-defined]
        assert blocs_exposes(faux) == {"bloc": ("tab",)}

    def test_une_routine_ne_compte_pas_pour_un_bloc(self) -> None:
        """Une routine f2py ne porte qu'elle-même, jamais un tableau."""

        class Routine:
            def __call__(self) -> None:  # pragma: no cover - jamais appelé
                ...

        class Faux:
            pass

        faux = Faux()
        faux.eval_cn = Routine()  # type: ignore[attr-defined]
        assert blocs_exposes(faux) == {}
