"""L'indicateur : le tirage réalisé suit-il la loi prescrite ?"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pandas as pd
import pytest

from cfd_dispersion.core.loi import LoiDispersion
from cfd_dispersion.core.lois import JeuDeLois
from cfd_dispersion.core.tirage import tirer_tableau
from cfd_dispersion.core.validation import MOTIFS, Verdict, valider, valider_lot


class TestTirageConforme:
    @pytest.mark.parametrize("type_loi", [3, 4, 5, 6])
    def test_un_tirage_correct_est_valide(self, type_loi: int) -> None:
        loi = LoiDispersion(type_loi, M=0.0, ET=0.10)
        verdict = valider(loi.tirer(1000, graine=type_loi), loi)
        assert verdict.valide
        assert verdict.motif == ""

    @pytest.mark.parametrize("n", [20, 50, 200, 1000, 20_000])
    def test_un_tirage_correct_passe_a_tout_effectif(self, n: int) -> None:
        """Le seuil absorbe le bruit d'échantillonnage : pas de faux rejet."""
        loi = LoiDispersion(6, 0.0, 0.10)
        assert valider(loi.tirer(n, graine=2), loi).valide

    @pytest.mark.parametrize("graine", range(8))
    def test_pas_de_faux_rejet_sur_plusieurs_graines(self, graine: int) -> None:
        loi = LoiDispersion(5, 0.0, 0.02)
        assert valider(loi.tirer(1000, graine=graine), loi).valide

    def test_les_moments_theoriques_viennent_de_la_loi(self) -> None:
        loi = LoiDispersion(6, 0.0, 0.10)
        verdict = valider(loi.tirer(1000, graine=1), loi)
        assert verdict.M_theorique == pytest.approx(loi.M_theorique)
        assert verdict.ET_theorique == pytest.approx(loi.ET_theorique)


class TestCalibration:
    """Le taux de faux rejet doit valoir alpha, ni plus ni moins.

    C'est la propriété qui rend l'indicateur utilisable : un test trop sévère
    peint en rouge des tirages corrects, un test trop laxiste laisse passer
    l'erreur qu'on le paie pour trouver.
    """

    def test_le_taux_de_faux_rejet_vaut_alpha(self) -> None:
        loi = LoiDispersion(6, M=1.0, ET=0.08)
        rejets = sum(
            not valider(loi.tirer(400, graine=1000 + graine), loi).valide for graine in range(200)
        )
        # 200 répétitions à alpha = 5 % : l'écart-type binomial vaut 1.5 %,
        # d'où une fourchette large mais qui exclut un test déréglé.
        assert 0.01 <= rejets / 200 <= 0.12

    def test_la_correction_de_multiplicite_nettoie_le_tableau(self) -> None:
        """Sans elle, un tableau conforme sort presque toujours taché.

        Douze points de vol et quatre composantes font 48 tests : à 5 % par
        test, une étude entièrement correcte affiche en moyenne deux cases
        rouges de pur hasard, dans un livrable dont tout l'intérêt est qu'on
        ne regarde que les cases rouges.
        """
        import pandas as pd

        from cfd_dispersion.core.lois import charger_lois

        lois = charger_lois(
            {
                "A": {
                    "Biais_Type": 5,
                    "Biais_M": 0.0,
                    "Biais_ET": 0.02,
                    "FE_Type": 6,
                    "FE_M": 1.0,
                    "FE_ET": 0.08,
                },
                "B": {
                    "Biais_Type": 3,
                    "Biais_M": 0.0,
                    "Biais_ET": 0.02,
                    "FE_Type": 4,
                    "FE_M": 1.0,
                    "FE_ET": 0.08,
                },
            }
        )
        propres_avec = propres_sans = 0
        for etude in range(8):
            morceaux = []
            for point in range(12):
                lot = tirer_tableau(lois, 400, graine=5000 + 100 * etude + point)
                lot["Mach"] = 0.6 + 0.03 * point
                morceaux.append(lot)
            resultats = pd.concat(morceaux, ignore_index=True)
            propres_avec += bool(valider_lot(resultats, lois, par=("Mach",))["valide"].all())
            propres_sans += bool(
                valider_lot(resultats, lois, par=("Mach",), correction=None)["valide"].all()
            )
        assert propres_avec > propres_sans
        assert propres_avec >= 6  # ~95 % des études doivent sortir intactes

    def test_la_correction_ne_masque_pas_une_vraie_erreur(self) -> None:
        import pandas as pd

        from cfd_dispersion.core.lois import charger_lois

        prescrit = charger_lois(
            {
                "A": {
                    "Biais_Type": 5,
                    "Biais_M": 0.0,
                    "Biais_ET": 0.02,
                    "FE_Type": 6,
                    "FE_M": 1.0,
                    "FE_ET": 0.08,
                }
            }
        )
        realise = charger_lois(
            {
                "A": {
                    "Biais_Type": 5,
                    "Biais_M": 0.0,
                    "Biais_ET": 0.02,
                    "FE_Type": 6,
                    "FE_M": 1.0,
                    "FE_ET": 0.16,
                }
            }
        )
        morceaux = []
        for point in range(12):
            source = realise if point == 5 else prescrit
            lot = tirer_tableau(source, 400, graine=9000 + point)
            lot["Mach"] = 0.6 + 0.03 * point
            morceaux.append(lot)

        verdicts = valider_lot(pd.concat(morceaux, ignore_index=True), prescrit, par=("Mach",))
        rejets = verdicts.loc[~verdicts["valide"]]
        assert len(rejets) == 1
        assert rejets.iloc[0]["composante"] == "FE"


class TestErreurDeFacteurDeux:
    """La confusion demi-étendue / écart-type, dans les deux sens."""

    @pytest.mark.parametrize("n", [50, 200, 1000, 20_000])
    def test_ET_double_sur_loi_bornee_est_rejete(self, n: int) -> None:
        prescrit = LoiDispersion(6, 0.0, 0.10)
        realise = LoiDispersion(6, 0.0, 0.20)
        assert not valider(realise.tirer(n, graine=1), prescrit).valide

    @pytest.mark.parametrize("n", [50, 200, 1000, 20_000])
    def test_ET_double_sur_loi_non_bornee_est_rejete(self, n: int) -> None:
        """Ici le support ne peut rien : c'est l'écart-type qui tranche."""
        prescrit = LoiDispersion(4, 0.0, 0.10)
        realise = LoiDispersion(4, 0.0, 0.20)
        verdict = valider(realise.tirer(n, graine=1), prescrit)
        assert not verdict.valide
        assert verdict.motif == "écart-type"
        assert verdict.hors_support == 0

    def test_ET_moitie_est_rejete(self) -> None:
        prescrit = LoiDispersion(4, 0.0, 0.20)
        realise = LoiDispersion(4, 0.0, 0.10)
        assert valider(realise.tirer(1000, graine=1), prescrit).motif == "écart-type"


class TestLesQuatreMotifs:
    """Chaque contrôle attrape quelque chose que les autres laissent passer."""

    def test_support_attrape_la_troncature_ignoree(self) -> None:
        """Une loi tronquée tirée comme une gaussienne pleine.

        Le test de Kolmogorov–Smirnov passerait : sur mille points, la queue
        fautive en compte quelques dizaines et la p-valeur reste au-dessus du
        seuil. C'est la justification du contrôle de support, et de sa place
        en premier.
        """
        prescrit = LoiDispersion(6, 0.0, 0.10)
        realise = LoiDispersion(4, 0.0, 0.10)
        verdict = valider(realise.tirer(1000, graine=3), prescrit)

        assert verdict.motif == "support"
        assert verdict.hors_support > 0
        assert verdict.ks_p > 0.05  # KS seul aurait validé

    def test_moyenne_attrape_un_biais_decale(self) -> None:
        prescrit = LoiDispersion(4, 0.0, 0.10)
        realise = LoiDispersion(4, 0.05, 0.10)
        verdict = valider(realise.tirer(1000, graine=4), prescrit)
        assert verdict.motif == "moyenne"
        assert verdict.ecart_M == pytest.approx(1.0, abs=0.15)

    def test_forme_attrape_ce_que_les_moments_laissent_passer(self) -> None:
        """Même moyenne, même écart-type, même support — mais bimodal."""
        cible = LoiDispersion(3, 0.0, 0.10)
        rng = np.random.default_rng(0)
        bimodal = np.where(rng.random(3000) < 0.5, -cible.ET_theorique, cible.ET_theorique)

        verdict = valider(bimodal, cible)
        assert verdict.motif == "forme"
        assert verdict.hors_support == 0
        assert verdict.ecart_M < 0.05
        assert verdict.ecart_ET < 0.05

    def test_effectif_trop_court(self) -> None:
        loi = LoiDispersion(4, 0.0, 0.10)
        verdict = valider(loi.tirer(5, graine=1), loi)
        assert verdict.motif == "effectif"
        assert not verdict.valide
        assert math.isnan(verdict.ks_p)

    def test_n_min_est_reglable(self) -> None:
        loi = LoiDispersion(4, 0.0, 0.10)
        assert valider(loi.tirer(10, graine=1), loi, n_min=5).motif != "effectif"

    def test_tous_les_motifs_sont_declares(self) -> None:
        assert set(MOTIFS) == {"effectif", "support", "moyenne", "écart-type", "forme"}


class TestOrdreDesControles:
    def test_le_support_prime_sur_les_moments(self) -> None:
        """Un point hors bornes est rédhibitoire même si tout le reste colle."""
        loi = LoiDispersion(6, 0.0, 0.10)
        echantillon = loi.tirer(1000, graine=1)
        echantillon[0] = 0.5  # loin hors du support ±0.10

        verdict = valider(echantillon, loi)
        assert verdict.motif == "support"
        assert verdict.hors_support == 1


class TestLoiDegeneree:
    def test_une_constante_exacte_est_validee(self) -> None:
        assert valider(np.full(100, 0.7), LoiDispersion(2, 0.7)).valide

    def test_une_constante_decalee_est_rejetee(self) -> None:
        assert not valider(np.full(100, 0.8), LoiDispersion(2, 0.7)).valide

    def test_le_test_ks_n_est_pas_applique(self) -> None:
        """Kolmogorov–Smirnov n'est défini que pour une loi continue."""
        verdict = valider(np.zeros(100), LoiDispersion(1))
        assert math.isnan(verdict.ks_D)
        assert math.isnan(verdict.ks_p)
        assert verdict.valide

    def test_ET_nul_est_traite_comme_degenere(self) -> None:
        assert valider(np.full(50, 2.0), LoiDispersion(4, 2.0, 0.0)).valide


class TestVerdict:
    def test_vers_dict_porte_tous_les_champs(self) -> None:
        loi = LoiDispersion(4, 0.0, 0.1)
        d = valider(loi.tirer(100, graine=1), loi, coefficient="CN", composante="Biais").vers_dict()
        assert d["coefficient"] == "CN"
        assert d["composante"] == "Biais"
        assert set(d) >= {"valide", "motif", "ks_p", "ecart_M", "ecart_ET", "hors_support"}

    def test_le_resume_dit_le_verdict(self) -> None:
        loi = LoiDispersion(4, 0.0, 0.1)
        assert "VALIDÉ" in valider(loi.tirer(500, graine=1), loi).resume

    def test_le_resume_dit_le_motif_en_cas_de_rejet(self) -> None:
        verdict = valider(
            LoiDispersion(4, 0.0, 0.2).tirer(500, graine=1), LoiDispersion(4, 0.0, 0.1)
        )
        assert "REJETÉ" in verdict.resume and "écart-type" in verdict.resume

    def test_le_verdict_est_gele(self) -> None:
        loi = LoiDispersion(4, 0.0, 0.1)
        verdict = valider(loi.tirer(100, graine=1), loi)
        with pytest.raises(Exception):  # noqa: B017 - FrozenInstanceError
            verdict.valide = False  # type: ignore[misc]

    def test_type(self) -> None:
        loi = LoiDispersion(4, 0.0, 0.1)
        assert isinstance(valider(loi.tirer(100, graine=1), loi), Verdict)


class TestValiderLot:
    def _sortie_modele(
        self,
        lois: JeuDeLois,
        n: int = 400,
        points: Sequence[tuple[float, float]] = ((0.7, 5000.0), (0.85, 10000.0)),
    ) -> pd.DataFrame:
        """Simule une sortie de modèle : n tirages par point de vol."""
        morceaux = []
        for i, (mach, altitude) in enumerate(points):
            lot = tirer_tableau(lois, n, graine=100 + i)
            lot["Mach"] = mach
            lot["Altitude_m"] = altitude
            morceaux.append(lot)
        return pd.concat(morceaux, ignore_index=True)

    def test_une_ligne_par_point_de_vol_coefficient_et_composante(self, lois: JeuDeLois) -> None:
        table = valider_lot(self._sortie_modele(lois), lois, par=("Mach", "Altitude_m"))
        assert len(table) == 2 * len(lois) * 2
        assert set(table.columns) >= {"Mach", "Altitude_m", "coefficient", "composante", "valide"}

    def test_un_tirage_conforme_valide_partout(self, lois: JeuDeLois) -> None:
        table = valider_lot(self._sortie_modele(lois), lois, par=("Mach", "Altitude_m"))
        assert table["valide"].all()

    def test_un_coefficient_mal_tire_est_isole(
        self, lois: JeuDeLois, table: dict[str, dict[str, float]]
    ) -> None:
        """Seule la composante fautive doit être rejetée."""
        from cfd_dispersion.core.lois import charger_lois

        faux = {c: dict(s) for c, s in table.items()}
        faux["Cn_beta"]["FE_ET"] = 0.16  # le double du prescrit
        sortie = self._sortie_modele(charger_lois(faux))

        resultat = valider_lot(sortie, lois, par=("Mach", "Altitude_m"))
        rejetes = resultat.loc[~resultat["valide"], ["coefficient", "composante"]]
        assert set(map(tuple, rejetes.to_numpy())) == {("Cn_beta", "FE")}

    def test_sans_groupement_tout_le_tableau_est_valide_d_un_bloc(self, lois: JeuDeLois) -> None:
        table = valider_lot(self._sortie_modele(lois), lois)
        assert len(table) == len(lois) * 2

    def test_l_ordre_des_points_de_vol_est_conserve(self, lois: JeuDeLois) -> None:
        sortie = self._sortie_modele(lois, points=((0.85, 10000.0), (0.7, 5000.0)))
        table = valider_lot(sortie, lois, par=("Mach",))
        assert list(dict.fromkeys(table["Mach"])) == [0.85, 0.7]

    def test_une_colonne_absente_est_nommee(self, lois: JeuDeLois) -> None:
        sortie = self._sortie_modele(lois).drop(columns=["Cm_alpha_FE"])
        with pytest.raises(ValueError, match="Cm_alpha_FE"):
            valider_lot(sortie, lois, par=("Mach",))

    def test_une_colonne_de_groupement_absente_est_nommee(self, lois: JeuDeLois) -> None:
        with pytest.raises(ValueError, match="Regime"):
            valider_lot(self._sortie_modele(lois), lois, par=("Regime",))

    def test_une_correspondance_de_colonnes_sur_mesure(self, lois: JeuDeLois) -> None:
        sortie = self._sortie_modele(lois).rename(columns={"Cm_alpha_Biais": "biais_cma"})
        resultat = valider_lot(
            sortie, lois, par=("Mach",), colonnes={("Cm_alpha", "Biais"): "biais_cma"}
        )
        assert resultat["valide"].all()

    def test_un_groupe_trop_court_est_marque_effectif(self, lois: JeuDeLois) -> None:
        table = valider_lot(self._sortie_modele(lois, n=5), lois, par=("Mach",))
        assert (table["motif"] == "effectif").all()
