"""Les relations entre coefficients tirés et coefficients rendus.

Trois familles de contrôles :

* la **lecture** — ce que les quatre écritures admises donnent, et ce qui est
  refusé ;
* la **dérivation** — les poids, les familles, et surtout le contrôle numérique
  qui confronte la loi dérivée à la relation d'origine ;
* les **refus**, qui comptent autant : une loi dérivée fausse ressemble trait
  pour trait à une loi dérivée juste.
"""

from __future__ import annotations

import pickle

import numpy as np
import pytest

from cfd_dispersion.core.convention import CONVENTIONS, Convention, convention
from cfd_dispersion.core.loi import LoiDispersion
from cfd_dispersion.core.lois import JeuDeLois, charger_lois
from cfd_dispersion.core.relation import (
    LoiDerivee,
    Relation,
    charger_relations,
    composantes_derivees,
    loi_derivee,
    lois_avec_relations,
    poids_derives,
)
from cfd_dispersion.core.tirage import tirer_lot

#: Trois coefficients dispersés, de familles différentes — pour qu'une somme
#: en sorte, et qu'on voie qu'elle n'appartient plus à aucune.
TABLE: dict[str, dict[str, float]] = {
    "CZ": {
        "Biais_Type": 5,
        "Biais_M": 0.0,
        "Biais_ET": 0.02,
        "FE_Type": 6,
        "FE_M": 1.0,
        "FE_ET": 0.08,
    },
    "CX1": {
        "Biais_Type": 3,
        "Biais_M": 0.0,
        "Biais_ET": 0.0008,
        "FE_Type": 6,
        "FE_M": 1.0,
        "FE_ET": 0.10,
    },
    "CX2": {
        "Biais_Type": 5,
        "Biais_M": 0.0,
        "Biais_ET": 0.0004,
        "FE_Type": 5,
        "FE_M": 1.0,
        "FE_ET": 0.06,
    },
}

NOMINAUX = {"CZ": -0.905, "CX1": 0.0228, "CX2": 0.0146}


@pytest.fixture
def jeu() -> JeuDeLois:
    return charger_lois(TABLE)


def cube_du_fe(c: object, biais: object, fe: object) -> np.ndarray:
    """Une relation non affine — fonction de module, donc sérialisable."""
    return np.asarray(
        np.asarray(biais, dtype=float) + np.asarray(fe, dtype=float) ** 3 * np.asarray(c, float),
        dtype=float,
    )


TORDUE = Convention(nom="tordue", formule="biais + FE³ · c", appliquer=cube_du_fe)


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------


class TestLecture:
    @pytest.mark.parametrize(
        ("texte", "termes", "constante"),
        [
            ("CN = -CZ", (("CZ", -1.0),), 0.0),
            ("CA = CX1 + CX2", (("CX1", 1.0), ("CX2", 1.0)), 0.0),
            ("CA = 2*CX1 - CX2", (("CX1", 2.0), ("CX2", -1.0)), 0.0),
            ("CA = 2 CX1", (("CX1", 2.0),), 0.0),
            ("CA = CX1*3", (("CX1", 3.0),), 0.0),
            ("CN = CZ/2", (("CZ", 0.5),), 0.0),
            ("CN = -CZ + 0.02", (("CZ", -1.0),), 0.02),
            ("CN = 0.02 - CZ", (("CZ", -1.0),), 0.02),
            ("Cm = 1e-2*Cm0", (("Cm0", 0.01),), 0.0),
        ],
    )
    def test_les_ecritures_admises(
        self, texte: str, termes: tuple[tuple[str, float], ...], constante: float
    ) -> None:
        lue = Relation.depuis_texte(texte)
        assert lue.termes == termes
        assert lue.constante == pytest.approx(constante)

    def test_les_quatre_formes_donnent_la_meme_relation(self) -> None:
        attendue = Relation(cible="CN", termes=(("CZ", -1.0),))
        assert charger_relations({"CN": "-CZ"}) == {"CN": attendue}
        assert charger_relations(["CN = -CZ"]) == {"CN": attendue}
        assert charger_relations({"CN": {"CZ": -1.0}}) == {"CN": attendue}
        assert charger_relations(attendue) == {"CN": attendue}
        assert charger_relations("CN = -CZ") == {"CN": attendue}

    def test_rien_donne_rien(self) -> None:
        assert charger_relations(None) == {}

    def test_la_relation_se_relit(self) -> None:
        assert str(Relation.depuis_texte("CA = CX1 + CX2")) == "CA = CX1 + CX2"
        assert str(Relation.depuis_texte("CN = -CZ")) == "CN = -CZ"
        assert str(Relation.depuis_texte("Cm = 0.5*Cm0 - 2*Cm1 + 0.01")) == (
            "Cm = 0.5*Cm0 - 2*Cm1 + 0.01"
        )

    def test_elle_s_applique_a_des_valeurs(self) -> None:
        lien = Relation.depuis_texte("CA = CX1 + CX2 + 0.001")
        assert float(lien.appliquer({"CX1": 0.02, "CX2": 0.01})) == pytest.approx(0.031)

    def test_elle_s_applique_a_des_tableaux(self) -> None:
        """Un balayage entier se combine d'un coup, comme partout ailleurs."""
        lien = Relation.depuis_texte("CN = -CZ")
        obtenu = lien.appliquer({"CZ": np.array([0.1, 0.2, 0.3])})
        assert np.allclose(obtenu, [-0.1, -0.2, -0.3])

    @pytest.mark.parametrize(
        ("mauvais", "motif"),
        [
            ("CN = CZ*CX", "linéaire"),
            ("CN = CZ CX", "linéaire"),
            ("CN = CZ/CX", "linéaire"),
            ("CN = ", "vide"),
            ("CN = CZ +", "opérateur"),
            ("CN = *CZ", "opérateur"),
            ("CN = @", "caractère inattendu"),
            ("CN = CZ/0", "division par zéro"),
        ],
    )
    def test_les_ecritures_refusees(self, mauvais: str, motif: str) -> None:
        with pytest.raises(ValueError, match=motif):
            Relation.depuis_texte(mauvais)

    def test_une_relation_sans_cible_est_refusee(self) -> None:
        with pytest.raises(ValueError, match="sans cible"):
            Relation.depuis_texte("CX1 + CX2")

    def test_une_cible_qui_se_refere_a_elle_meme_est_refusee(self) -> None:
        with pytest.raises(ValueError, match="elle-même"):
            Relation.depuis_texte("CA = CA + CX1")

    def test_une_source_nommee_deux_fois_est_refusee(self) -> None:
        with pytest.raises(ValueError, match="deux fois"):
            Relation.depuis_texte("CA = CX1 + CX1")

    def test_une_relation_sans_terme_est_refusee(self) -> None:
        with pytest.raises(ValueError, match="aucun terme"):
            Relation(cible="CA", termes=())

    def test_deux_relations_pour_la_meme_cible_sont_refusees(self) -> None:
        with pytest.raises(ValueError, match="deux relations"):
            charger_relations(["CA = CX1", "CA = CX2"])


# ---------------------------------------------------------------------------
# Dérivation
# ---------------------------------------------------------------------------


class TestDerivationSimple:
    """``cible = a·source`` : le cas qui reste dans sa famille."""

    def test_la_loi_reste_du_meme_type(self, jeu: JeuDeLois) -> None:
        source = jeu["CZ"].biais
        assert isinstance(source, LoiDispersion)
        derivee = loi_derivee(Relation.depuis_texte("CN = -CZ"), jeu)
        assert isinstance(derivee.biais, LoiDispersion)
        assert derivee.biais.type_loi == source.type_loi
        assert derivee.biais.ET == pytest.approx(source.ET)
        assert derivee.biais.M == pytest.approx(0.0)

    def test_le_facteur_d_echelle_est_inchange(self, jeu: JeuDeLois) -> None:
        """``a·(biais + FE·c) = a·biais + FE·(a·c)`` : seul le biais suit *a*."""
        derivee = loi_derivee(Relation.depuis_texte("CN = -CZ"), jeu)
        assert derivee.fe == jeu["CZ"].fe

    def test_un_facteur_deux_double_l_etendue_du_biais(self, jeu: JeuDeLois) -> None:
        derivee = loi_derivee(Relation.depuis_texte("CN = 2*CZ"), jeu)
        assert derivee.biais.ET == pytest.approx(2.0 * jeu["CZ"].biais.ET)

    def test_elle_se_derive_sans_les_nominaux(self, jeu: JeuDeLois) -> None:
        """C'est tout l'intérêt du cas simple : aucun point de vol en jeu."""
        assert loi_derivee(Relation.depuis_texte("CN = -CZ"), jeu) is not None

    def test_une_loi_nulle_reste_nulle(self) -> None:
        jeu = charger_lois(
            {
                "CZ": {
                    "Biais_Type": 1,
                    "Biais_M": 0.0,
                    "Biais_ET": 0.0,
                    "FE_Type": 2,
                    "FE_M": 1.0,
                    "FE_ET": 0.0,
                }
            }
        )
        derivee = loi_derivee(Relation.depuis_texte("CN = -CZ"), jeu)
        assert derivee.biais.est_degeneree
        assert derivee.biais.M_theorique == pytest.approx(0.0)


class TestDerivationCombinee:
    """``cible = Σ aᵢ·sourceᵢ`` : le cas qui sort des six familles."""

    def test_la_loi_n_est_plus_d_une_famille(self, jeu: JeuDeLois) -> None:
        derivee = loi_derivee(Relation.depuis_texte("CA = CX1 + CX2"), jeu, nominaux=NOMINAUX)
        assert isinstance(derivee.biais, LoiDerivee)
        assert derivee.biais.label == "dérivée"
        assert "CX1_Biais" in derivee.biais.expression

    def test_le_biais_est_la_somme_des_biais(self, jeu: JeuDeLois) -> None:
        derivee = loi_derivee(Relation.depuis_texte("CA = CX1 + CX2"), jeu, nominaux=NOMINAUX)
        variance = jeu["CX1"].biais.ET_theorique ** 2 + jeu["CX2"].biais.ET_theorique ** 2
        assert derivee.biais.ET_theorique == pytest.approx(variance**0.5, rel=1e-6)

    def test_les_poids_du_facteur_sont_des_parts(self, jeu: JeuDeLois) -> None:
        """Chaque FE pèse ce que pèse sa contribution dans la cible."""
        _, poids_fe, decalage = poids_derives(
            Relation.depuis_texte("CA = CX1 + CX2"), nominaux=NOMINAUX
        )
        total = NOMINAUX["CX1"] + NOMINAUX["CX2"]
        assert poids_fe["CX1"] == pytest.approx(NOMINAUX["CX1"] / total)
        assert poids_fe["CX2"] == pytest.approx(NOMINAUX["CX2"] / total)
        assert sum(poids_fe.values()) == pytest.approx(1.0)
        assert decalage == 0.0

    def test_les_parts_suivent_le_point_de_vol(self, jeu: JeuDeLois) -> None:
        """La loi dérivée change de point de vol en point de vol — c'est voulu."""
        lien = Relation.depuis_texte("CA = CX1 + CX2")
        ici = loi_derivee(lien, jeu, nominaux={"CX1": 0.02, "CX2": 0.01})
        ailleurs = loi_derivee(lien, jeu, nominaux={"CX1": 0.02, "CX2": 0.02})
        assert ici.fe.ET_theorique != pytest.approx(ailleurs.fe.ET_theorique)

    def test_le_facteur_derive_est_plus_resserre_que_ses_sources(self, jeu: JeuDeLois) -> None:
        """Une moyenne pondérée de deux tirages indépendants disperse moins."""
        derivee = loi_derivee(Relation.depuis_texte("CA = CX1 + CX2"), jeu, nominaux=NOMINAUX)
        assert derivee.fe.ET_theorique < jeu["CX1"].fe.ET_theorique
        assert derivee.fe.ET_theorique < jeu["CX2"].fe.ET_theorique


class TestExactitude:
    """La dérivation redonne-t-elle la relation, tirage par tirage ?"""

    @pytest.mark.parametrize("nom_convention", sorted(CONVENTIONS))
    @pytest.mark.parametrize("texte", ["CN = -CZ", "CA = CX1 + CX2", "CA = CX1 + CX2 + 0.005"])
    def test_le_coefficient_reconstruit_est_le_meme(
        self, jeu: JeuDeLois, nom_convention: str, texte: str
    ) -> None:
        """Le contrôle central : ``conv(cible_nom, B, F)`` doit valoir la
        combinaison des sources reconstruites, à l'erreur d'arrondi près."""
        lien = Relation.depuis_texte(texte)
        relation = convention(nom_convention)
        cible = float(np.asarray(lien.appliquer(NOMINAUX), dtype=float).reshape(-1)[0])

        for tirage in tirer_lot(jeu, 25, graine=3, convention_=relation):
            attendu = float(
                np.asarray(
                    lien.appliquer(
                        {
                            nom: relation(NOMINAUX[nom], tirage[nom]["Biais"], tirage[nom]["FE"])
                            for nom in lien.sources
                        }
                    ),
                    dtype=float,
                ).reshape(-1)[0]
            )
            composantes = composantes_derivees(
                lien, tirage, nominaux=NOMINAUX, convention_=relation
            )
            obtenu = float(
                np.asarray(
                    relation(cible, composantes["Biais"], composantes["FE"]), dtype=float
                ).reshape(-1)[0]
            )
            assert obtenu == pytest.approx(attendu, abs=1e-12, rel=1e-12)

    def test_la_loi_derivee_predit_les_moments_realises(self, jeu: JeuDeLois) -> None:
        """Vérification statistique : la loi du biais dérivé est bien la sienne."""
        lien = Relation.depuis_texte("CA = CX1 + CX2")
        derivee = loi_derivee(lien, jeu, nominaux=NOMINAUX)
        lot = tirer_lot(jeu, 20_000, graine=5)
        realises = np.array(
            [composantes_derivees(lien, tirage, nominaux=NOMINAUX)["Biais"] for tirage in lot]
        )
        assert realises.mean() == pytest.approx(derivee.biais.M_theorique, abs=2e-5)
        assert realises.std() == pytest.approx(derivee.biais.ET_theorique, rel=0.03)

    def test_le_tirage_neutre_reste_neutre(self, jeu: JeuDeLois) -> None:
        """Un tirage qui ne disperse rien ne doit rien disperser sur la cible."""
        from cfd_dispersion.core.tirage import tirage_neutre

        lien = Relation.depuis_texte("CA = CX1 + CX2 + 0.005")
        neutre = tirage_neutre(jeu)
        composantes = composantes_derivees(lien, neutre, nominaux=NOMINAUX)
        assert composantes["Biais"] == pytest.approx(0.0)
        assert composantes["FE"] == pytest.approx(neutre["CX1"]["FE"])


# ---------------------------------------------------------------------------
# La loi dérivée en tant qu'objet
# ---------------------------------------------------------------------------


class TestLoiDerivee:
    @pytest.fixture
    def derivee(self, jeu: JeuDeLois) -> LoiDerivee:
        loi = loi_derivee(Relation.depuis_texte("CA = CX1 + CX2"), jeu, nominaux=NOMINAUX)
        assert isinstance(loi.biais, LoiDerivee)
        return loi.biais

    def test_elle_expose_l_interface_d_une_loi(self, derivee: LoiDerivee) -> None:
        from cfd_dispersion.core.loi import LoiComposante

        assert isinstance(derivee, LoiComposante)

    def test_ET_est_deux_sigmas(self, derivee: LoiDerivee) -> None:
        """La convention du paquet, appliquée à l'envers : ``σ = ET/2``."""
        assert derivee.ET == pytest.approx(2.0 * derivee.ET_theorique)

    def test_la_densite_integre_a_un(self, derivee: LoiDerivee) -> None:
        bas, haut = derivee.plage_utile()
        grille = np.linspace(bas, haut, 4001)
        assert np.trapezoid(derivee.pdf(grille), grille) == pytest.approx(1.0, abs=1e-3)

    def test_les_quantiles_encadrent_la_moyenne(self, derivee: LoiDerivee) -> None:
        bas, haut = derivee.quantile([0.01, 0.99])
        assert bas < derivee.M_theorique < haut

    def test_le_support_est_celui_de_la_somme(self, derivee: LoiDerivee) -> None:
        bas, haut = derivee.support()
        assert bas == pytest.approx(-(0.0008 + 0.0004 * 1.5))
        assert haut == pytest.approx(0.0008 + 0.0004 * 1.5)

    def test_elle_tire(self, derivee: LoiDerivee) -> None:
        valeurs = derivee.tirer(500, graine=1)
        assert valeurs.shape == (500,)
        assert valeurs.mean() == pytest.approx(derivee.M_theorique, abs=1e-4)

    def test_elle_se_serialise(self, derivee: LoiDerivee) -> None:
        """Un parcours parallèle l'envoie dans un processus ouvrier."""
        relue = pickle.loads(pickle.dumps(derivee))
        assert relue.ET_theorique == pytest.approx(derivee.ET_theorique)

    def test_elle_ne_se_reecrit_pas_dans_une_table(self, jeu: JeuDeLois) -> None:
        """Une combinaison n'a pas de (Type, M, ET) : c'est la relation qui voyage."""
        derivee = loi_derivee(Relation.depuis_texte("CA = CX1 + CX2"), jeu, nominaux=NOMINAUX)
        with pytest.raises(TypeError, match="ne se réécrit"):
            derivee.en_table()

    def test_une_loi_declaree_se_reecrit(self, jeu: JeuDeLois) -> None:
        assert jeu["CZ"].en_table() == TABLE["CZ"]


# ---------------------------------------------------------------------------
# Le jeu augmenté
# ---------------------------------------------------------------------------


class TestJeuAugmente:
    def test_les_cibles_s_ajoutent_a_la_suite(self, jeu: JeuDeLois) -> None:
        augmente = lois_avec_relations(jeu, {"CN": "-CZ", "CA": "CX1 + CX2"}, nominaux=NOMINAUX)
        assert list(augmente) == ["CZ", "CX1", "CX2", "CN", "CA"]

    def test_les_lois_d_origine_sont_intactes(self, jeu: JeuDeLois) -> None:
        augmente = lois_avec_relations(jeu, {"CN": "-CZ"})
        assert augmente["CZ"] == jeu["CZ"]

    def test_sans_relation_le_jeu_est_rendu_tel_quel(self, jeu: JeuDeLois) -> None:
        assert lois_avec_relations(jeu, None) is jeu

    def test_une_cible_qui_a_deja_ses_lois_est_refusee(self, jeu: JeuDeLois) -> None:
        with pytest.raises(ValueError, match="a déjà ses lois"):
            lois_avec_relations(jeu, {"CX1": "CX2"})


# ---------------------------------------------------------------------------
# Refus
# ---------------------------------------------------------------------------


class TestRefus:
    def test_une_source_absente_du_jeu(self, jeu: JeuDeLois) -> None:
        with pytest.raises(ValueError, match=r"absent\(s\) du jeu de lois"):
            loi_derivee(Relation.depuis_texte("CN = -CL"), jeu)

    def test_une_combinaison_sans_nominaux(self, jeu: JeuDeLois) -> None:
        with pytest.raises(ValueError, match="valeurs nominales"):
            loi_derivee(Relation.depuis_texte("CA = CX1 + CX2"), jeu)

    def test_un_terme_unique_avec_constante_sans_nominaux(self, jeu: JeuDeLois) -> None:
        """La constante casse le raccourci : la part n'est plus 1."""
        with pytest.raises(ValueError, match="valeurs nominales"):
            loi_derivee(Relation.depuis_texte("CN = -CZ + 0.01"), jeu)

    def test_une_convention_non_affine(self, jeu: JeuDeLois) -> None:
        with pytest.raises(ValueError, match="affine"):
            loi_derivee(
                Relation.depuis_texte("CA = CX1 + CX2"),
                jeu,
                nominaux=NOMINAUX,
                convention_=TORDUE,
            )

    def test_un_jeu_correle(self) -> None:
        """La loi d'une somme de composantes dépendantes n'est pas leur combinaison."""
        correle = charger_lois(TABLE, correlation={("CX1", "CX2"): 0.6})
        with pytest.raises(ValueError, match="corrélé"):
            loi_derivee(Relation.depuis_texte("CA = CX1 + CX2"), correle, nominaux=NOMINAUX)

    def test_un_nominal_nul_sous_la_convention_pourcentage(self, jeu: JeuDeLois) -> None:
        """``β(c) = c/100`` s'annule en zéro : la part n'y est pas définie."""
        with pytest.raises(ValueError, match="annule une composante"):
            loi_derivee(
                Relation.depuis_texte("CA = CX1 - CX1v"),
                charger_lois({**TABLE, "CX1v": TABLE["CX1"]}),
                nominaux={"CX1": 0.02, "CX1v": 0.02},
                convention_="pourcentage",
            )

    def test_un_tirage_sans_les_sources(self, jeu: JeuDeLois) -> None:
        with pytest.raises(ValueError, match="absent"):
            composantes_derivees(
                Relation.depuis_texte("CA = CX1 + CX2"),
                {"CX1": {"Biais": 0.0, "FE": 1.0}},
                nominaux=NOMINAUX,
            )
