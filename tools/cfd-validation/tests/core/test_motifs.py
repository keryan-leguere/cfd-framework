"""Les détecteurs de motifs, un par un puis tous ensemble.

Deux exigences, et la seconde compte autant que la première :

* devant la panne qu'il vise, un détecteur sort **en tête** ;
* devant les autres pannes, il ne sort **pas** en tête. Un détecteur qui
  explique tout n'explique rien, et un rapport qui propose huit hypothèses à
  chaque échec ne vaut pas mieux que pas de rapport du tout.

Les cas sont bâtis à la main sur de petites grilles : on veut savoir que le
détecteur voit la signature, pas qu'il s'accorde avec le modèle factice.
"""

from __future__ import annotations

import numpy as np
import pytest

from cfd_validation.core.motifs import (
    DETECTEURS,
    ORDRE_SPECIFICITE,
    Contexte,
    axe_ignore,
    axes_transposes,
    decalage_constant,
    decalage_indice,
    detecter,
    diffus,
    ecretage,
    facteur_echelle,
    queue_non_renseignee,
)

from ..conftest import contexte_de_tableaux, grille

#: Une grille carrée : les deux axes partagent leurs valeurs, donc une
#: transposition tombe toujours sur un nœud existant.
AXE = (0.0, 1.0, 2.0, 3.0)


def _reference(noeuds: np.ndarray) -> np.ndarray:
    """Une fonction qui dépend vraiment des deux axes, et sans symétrie."""
    return 1.0 + 2.0 * noeuds[:, 0] + 0.5 * noeuds[:, 1] + 0.1 * noeuds[:, 0] ** 2


@pytest.fixture
def noeuds() -> np.ndarray:
    return grille(AXE, AXE)


@pytest.fixture
def reference(noeuds: np.ndarray) -> np.ndarray:
    return _reference(noeuds)


def _index(noeuds: np.ndarray) -> dict[tuple[float, ...], int]:
    return {tuple(ligne.tolist()): rang for rang, ligne in enumerate(noeuds)}


# ---------------------------------------------------------------------------
# Chaque détecteur, devant sa propre panne
# ---------------------------------------------------------------------------


class TestChaqueMotifVoitSaPanne:
    def test_queue_non_renseignee(self) -> None:
        noeuds = grille(AXE, AXE)
        reference = _reference(noeuds)
        reference[-5:] = -999.0  # la queue jamais écrite
        obtenu = reference.copy()
        obtenu[-5:] = 0.0  # le modèle ne connaît pas ces nœuds

        motif = queue_non_renseignee(contexte_de_tableaux(noeuds, reference, obtenu))
        assert motif is not None
        assert motif.part_expliquee == 1.0
        assert "lignes" in motif.message
        assert motif.preuve["queue_constante"] is True

    def test_facteur_echelle_nomme_la_conversion_quand_il_la_reconnait(
        self, noeuds: np.ndarray, reference: np.ndarray
    ) -> None:
        motif = facteur_echelle(
            contexte_de_tableaux(noeuds, reference, reference * (np.pi / 180.0))
        )
        assert motif is not None
        assert motif.part_expliquee == 1.0
        assert motif.preuve["conversion"] == "des degrés lus comme des radians"

    def test_facteur_echelle_rapporte_un_facteur_inconnu_sans_le_nommer(
        self, noeuds: np.ndarray, reference: np.ndarray
    ) -> None:
        motif = facteur_echelle(contexte_de_tableaux(noeuds, reference, reference * 1.37))
        assert motif is not None
        assert motif.preuve["facteur"] == pytest.approx(1.37)
        assert motif.preuve["conversion"] == "—"

    def test_decalage_constant(self, noeuds: np.ndarray, reference: np.ndarray) -> None:
        motif = decalage_constant(contexte_de_tableaux(noeuds, reference, reference + 0.25))
        assert motif is not None
        assert motif.preuve["decalage"] == pytest.approx(0.25)

    def test_axes_transposes(self, noeuds: np.ndarray, reference: np.ndarray) -> None:
        index = _index(noeuds)
        obtenu = np.array([reference[index[(ligne[1], ligne[0])]] for ligne in noeuds], dtype=float)
        motif = axes_transposes(contexte_de_tableaux(noeuds, reference, obtenu))
        assert motif is not None
        assert motif.preuve["axes"] == ("x", "y")

    def test_axe_ignore(self, noeuds: np.ndarray, reference: np.ndarray) -> None:
        """Le modèle rend la même valeur quand seul le second axe change."""
        index = _index(noeuds)
        obtenu = np.array([reference[index[(ligne[0], AXE[0])]] for ligne in noeuds], dtype=float)
        motif = axe_ignore(contexte_de_tableaux(noeuds, reference, obtenu))
        assert motif is not None
        assert motif.preuve["axe"] == "y"

    def test_decalage_indice(self, noeuds: np.ndarray, reference: np.ndarray) -> None:
        index = _index(noeuds)
        obtenu = np.array(
            [
                reference[index.get((ligne[0], ligne[1] + 1.0), index[tuple(ligne.tolist())])]
                for ligne in noeuds
            ],
            dtype=float,
        )
        motif = decalage_indice(contexte_de_tableaux(noeuds, reference, obtenu))
        assert motif is not None
        assert motif.preuve["axe"] == "y"
        assert motif.preuve["sens"] == 1

    def test_ecretage(self, noeuds: np.ndarray, reference: np.ndarray) -> None:
        """Le décalage confiné aux bords : un indice saturé, pas une base fausse."""
        index = _index(noeuds)
        obtenu = reference.copy()
        for rang, ligne in enumerate(noeuds):
            if ligne[0] == AXE[0]:
                obtenu[rang] = reference[index[(AXE[1], ligne[1])]]
            elif ligne[0] == AXE[-1]:
                obtenu[rang] = reference[index[(AXE[-2], ligne[1])]]
        motif = ecretage(contexte_de_tableaux(noeuds, reference, obtenu))
        assert motif is not None
        assert motif.preuve["axe"] == "x"

    def test_diffus_donne_le_pire_point_et_ses_coordonnees(
        self, noeuds: np.ndarray, reference: np.ndarray
    ) -> None:
        generateur = np.random.default_rng(0)
        obtenu = reference + generateur.normal(0.0, 0.3, size=reference.shape)
        motif = diffus(contexte_de_tableaux(noeuds, reference, obtenu))
        assert motif is not None
        assert motif.part_expliquee == 0.0
        assert "x=" in motif.message and "y=" in motif.message


# ---------------------------------------------------------------------------
# Et devant les autres pannes
# ---------------------------------------------------------------------------


def _cas(noeuds: np.ndarray, reference: np.ndarray) -> dict[str, np.ndarray]:
    """Un obtenu par panne, sur la même grille."""
    index = _index(noeuds)
    transpose = np.array([reference[index[(noeud[1], noeud[0])]] for noeud in noeuds], dtype=float)
    ignore = np.array([reference[index[(noeud[0], AXE[0])]] for noeud in noeuds], dtype=float)
    decale = np.array(
        [
            reference[index.get((noeud[0], noeud[1] + 1.0), index[tuple(noeud.tolist())])]
            for noeud in noeuds
        ],
        dtype=float,
    )
    ecrete = reference.copy()
    for rang, ligne in enumerate(noeuds):
        if ligne[0] == AXE[0]:
            ecrete[rang] = reference[index[(AXE[1], ligne[1])]]
        elif ligne[0] == AXE[-1]:
            ecrete[rang] = reference[index[(AXE[-2], ligne[1])]]
    return {
        "facteur_echelle": reference * (np.pi / 180.0),
        "decalage_constant": reference + 0.25,
        "axes_transposes": transpose,
        "axe_ignore": ignore,
        "decalage_indice": decale,
        "ecretage": ecrete,
    }


class TestChaquePanneNommeSonMotif:
    """Le classement complet : la bonne hypothèse en tête, sur chaque panne."""

    @pytest.mark.parametrize(
        "panne",
        [
            "facteur_echelle",
            "decalage_constant",
            "axes_transposes",
            "axe_ignore",
            "decalage_indice",
            "ecretage",
        ],
    )
    def test_le_motif_attendu_sort_en_tete(
        self, panne: str, noeuds: np.ndarray, reference: np.ndarray
    ) -> None:
        obtenu = _cas(noeuds, reference)[panne]
        motifs = detecter(contexte_de_tableaux(noeuds, reference, obtenu))
        assert motifs, f"aucun motif détecté pour « {panne} »"
        assert motifs[0].nom == panne

    def test_un_modele_juste_ne_declenche_aucun_motif(
        self, noeuds: np.ndarray, reference: np.ndarray
    ) -> None:
        assert detecter(contexte_de_tableaux(noeuds, reference, reference)) == ()

    def test_le_bruit_ne_declenche_que_le_motif_descriptif(
        self, noeuds: np.ndarray, reference: np.ndarray
    ) -> None:
        """Aucune hypothèse structurelle ne doit se déclencher sur du bruit."""
        generateur = np.random.default_rng(7)
        obtenu = reference + generateur.normal(0.0, 0.5, size=reference.shape)
        motifs = detecter(contexte_de_tableaux(noeuds, reference, obtenu))
        assert [motif.nom for motif in motifs] == ["diffus"]


class TestClassement:
    def test_a_part_egale_le_plus_specifique_passe_devant(
        self, noeuds: np.ndarray, reference: np.ndarray
    ) -> None:
        """L'écrêtage et le décalage d'indice décrivent le même symptôme au bord.

        Le correctif, lui, diffère : une borne à reprendre plutôt qu'une base
        d'indexation. C'est le plus précis des deux qui doit parler en premier.
        """
        obtenu = _cas(noeuds, reference)["ecretage"]
        motifs = detecter(contexte_de_tableaux(noeuds, reference, obtenu))
        noms = [motif.nom for motif in motifs]
        assert noms[0] == "ecretage"
        assert "decalage_indice" in noms  # il voit bien quelque chose, mais moins

    def test_le_motif_descriptif_est_toujours_dernier(
        self, noeuds: np.ndarray, reference: np.ndarray
    ) -> None:
        obtenu = _cas(noeuds, reference)["facteur_echelle"]
        motifs = detecter(contexte_de_tableaux(noeuds, reference, obtenu))
        assert motifs[-1].nom == "diffus"

    def test_tous_les_detecteurs_figurent_dans_l_ordre_de_specificite(self) -> None:
        """Sans quoi un motif nouveau se classerait au hasard des égalités."""
        noms = {detecteur.__name__ for detecteur in DETECTEURS}
        assert noms == set(ORDRE_SPECIFICITE)


class TestContexte:
    def test_un_contexte_mal_dimensionne_est_refuse(self) -> None:
        with pytest.raises(ValueError, match="lignes"):
            contexte_de_tableaux([[0.0, 0.0], [1.0, 1.0]], [1.0], [1.0])

    def test_un_nombre_de_noms_incoherent_est_refuse(self) -> None:
        with pytest.raises(ValueError, match="noms de colonne"):
            contexte_de_tableaux([[0.0, 0.0]], [1.0], [1.0], noms=("x",))

    def test_les_noeuds_doivent_etre_un_tableau_2d(self) -> None:
        with pytest.raises(ValueError, match="2-D"):
            Contexte(
                noeuds=np.zeros(3),
                ecart=contexte_de_tableaux([[0.0, 0.0]], [1.0], [1.0]).ecart,
                noms=("x",),
            )
