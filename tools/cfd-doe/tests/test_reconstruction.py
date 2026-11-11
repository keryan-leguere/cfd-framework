"""Sobol, krigeage, plans à variance maximale, reconstruction des tables, figures et exemples.

L'oracle des reconstructions est le modèle factice de
``01_EXEMPLE/reconstruire_tables.py``, symétrisé sur le groupe de l'étude :
une table exacte doit le reproduire au nœud près, une table approchée s'en
écarter de moins que ce que sa méthode promet.
"""

from __future__ import annotations

import csv
import dataclasses
import importlib.util
import itertools
import math
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from cfd_doe.cli.main import main
from cfd_doe.core import plans as generateurs
from cfd_doe.core.metamodeles import (
    Krigeage,
    Polynome,
    indices_degre_total,
    indices_smolyak,
    matern52,
    plan_variance_maximale,
)
from cfd_doe.data.etude import ErreurEtude
from cfd_doe.data.remplissage import (
    ErreurRemplissage,
    charger_remplissage,
    remplissage_depuis_dict,
)
from cfd_doe.engine.reconstruction import (
    Mesures,
    ecrire_mesures,
    ecrire_tables,
    grille_carree,
    lire_mesures,
    lot_suivant,
    reconstruire,
)
from cfd_doe.engine.remplissage import Contexte, PlanDOE, Resultat, remplir
from cfd_doe.paths import EXEMPLE_DIR
from cfd_doe.report import figures

sys.path.insert(0, str(EXEMPLE_DIR))
import reconstruire_tables as rt

CFD_PLOT = importlib.util.find_spec("cfd_plot") is not None
PLAGES = {"alpha": [-20, 20], "beta": [-5, 5], "DL": [-10, 10], "DM": [-20, 20], "DN": [-20, 20]}
NIVEAUX = {"alpha": {"pas": 5}, "beta": {"pas": 2.5}, "DM": {"pas": 10}, "DN": {"pas": 10}}


def _donnees(plans: dict[str, Any], **extra: Any) -> dict[str, Any]:
    donnees: dict[str, Any] = {
        "etude": {
            "etude": {"nom": "T"},
            "trajectoire": "6DOF",
            "geometrie": "double_symetrie",
            "variables": PLAGES,
        },
        "mach": [0.8, 2.0],
        "parametres": {"moteur": {"niveaux": [0, 0.5, 1], "nominal": 0}},
        "niveaux": {**NIVEAUX, "DL": {"pas": 10}},
        "plans": plans,
    }
    donnees.update(extra)
    return donnees


def _remplir(plans: dict[str, Any], **extra: Any) -> Resultat:
    return remplir(remplissage_depuis_dict(_donnees(plans, **extra)))


def _vraie(c: Contexte) -> dict[str, np.ndarray]:
    grille = grille_carree(c)
    points = grille.points()
    colonnes = list(grille.colonnes)
    valeurs = {
        col: points[:, colonnes.index(col)]
        if col in colonnes
        else np.full(len(points), c.reference[col])
        for col in c.colonnes
    }
    return rt.verite(c, valeurs)


def _erreur(tables: Any, vraie: Mapping[str, np.ndarray]) -> float:
    """Erreur RMS du pire coefficient, en % de son étendue."""
    return max(
        100
        * float(np.sqrt(np.nanmean((tables.valeurs[c] - vraie[c]) ** 2)))
        / float(np.ptp(vraie[c]) or 1.0)
        for c in vraie
    )


def _tables(plan: PlanDOE, c: Contexte, **options: Any) -> Any:
    return reconstruire(plan, c, rt.calculer(plan.points, c), **options)


# ---------------------------------------------------------------------------
# core : Sobol
# ---------------------------------------------------------------------------


class TestSobol:
    def test_premiers_points(self) -> None:
        # Ordre de Gray, suite brute : les valeurs de référence (Joe et Kuo, SciPy non brouillé).
        assert generateurs.sobol(4, 3, None) == [
            (0.0, 0.0, 0.0),
            (0.5, 0.5, 0.5),
            (0.75, 0.25, 0.25),
            (0.25, 0.75, 0.75),
        ]

    @pytest.mark.parametrize("k", [1, 2, 5, 16])
    @pytest.mark.parametrize("graine", [None, 0, 7])
    def test_chaque_axe_stratifie(self, k: int, graine: int | None) -> None:
        for m in range(1, 8):
            for depart in (0, 2**m):
                points = np.array(generateurs.sobol(2**m, k, graine, depart))
                for j in range(k):
                    assert sorted((points[:, j] * 2**m).astype(int)) == list(range(2**m))

    def test_net_en_deux_dimensions(self) -> None:
        points = generateurs.sobol(64, 2, None)
        for a in range(7):
            cases = {(int(x * 2**a), int(y * 2 ** (6 - a))) for x, y in points}
            assert len(cases) == 64  # chaque pavé élémentaire d'aire 1/64 reçoit un point

    def test_extensible_et_decale(self) -> None:
        longue = generateurs.sobol(40, 4, 3)
        assert generateurs.sobol(16, 4, 3) == longue[:16]
        assert generateurs.sobol(8, 4, 3, depart=16) == longue[16:24]
        assert (0.0, 0.0, 0.0, 0.0) not in longue  # le décalage digital retire l'origine

    def test_trop_de_facteurs(self) -> None:
        with pytest.raises(ValueError, match="au plus 16"):
            generateurs.sobol(4, 17)


# ---------------------------------------------------------------------------
# core : métamodèles
# ---------------------------------------------------------------------------


class TestKrigeage:
    def test_noyau(self) -> None:
        rng = np.random.default_rng(0)
        x, y, p = rng.random((20, 3)), rng.random((7, 3)), np.array([0.3, 1.0, 2.0])
        d = (x[:, None, :] - y[None, :, :]) / p
        r = np.sqrt((d * d).sum(-1)) * math.sqrt(5)
        assert np.allclose(matern52(x, y, p), (1 + r + r * r / 3) * np.exp(-r), atol=1e-12)

    def test_interpole_et_ecart_type_nul_aux_points(self) -> None:
        x = np.array(generateurs.sobol(32, 2, 1))
        y = np.sin(3 * x[:, 0]) + x[:, 1] ** 2
        k = Krigeage().ajuster(x, y)
        moyenne, ecart = k.predire(x, ecart_type=True)
        assert np.allclose(moyenne, y, atol=1e-4)
        assert np.all(ecart < 1e-3 * np.ptp(y))
        test = np.random.default_rng(1).random((500, 2))
        vrai = np.sin(3 * test[:, 0]) + test[:, 1] ** 2
        assert np.sqrt(np.mean((np.asarray(k.predire(test)) - vrai) ** 2)) < 0.01

    def test_sortie_constante(self) -> None:
        x = np.random.default_rng(0).random((10, 2))
        k = Krigeage().ajuster(x, np.zeros(10))
        assert np.allclose(k.predire(np.random.default_rng(1).random((5, 2))), 0.0)

    def test_multi_sorties_a_portees_fixees(self) -> None:
        rng = np.random.default_rng(2)
        x, y = rng.random((25, 3)), rng.random((25, 2))
        commun = Krigeage(portees=np.array([0.4, 0.5, 0.6])).ajuster(x, y)
        seuls = [Krigeage(portees=np.array([0.4, 0.5, 0.6])).ajuster(x, y[:, j]) for j in (0, 1)]
        q = rng.random((9, 3))
        attendu = np.column_stack([np.asarray(s.predire(q)) for s in seuls])
        assert np.allclose(commun.predire(q), attendu)


class TestPolynome:
    @pytest.mark.parametrize("k", [1, 2, 3, 4, 5])
    @pytest.mark.parametrize("niveau", [0, 1, 2, 3])
    def test_espace_smolyak_de_la_taille_de_la_grille(self, k: int, niveau: int) -> None:
        assert len(indices_smolyak(k, niveau)) == len(generateurs.grille_creuse(k, niveau))

    def test_smolyak_interpole_sur_sa_grille(self) -> None:
        grille = np.array(generateurs.grille_creuse(3, 2))
        y = np.exp(grille[:, 0]) * np.cos(grille[:, 1]) + grille[:, 2]
        p = Polynome(indices_smolyak(3, 2)).ajuster(grille, y)
        assert p.rang == len(grille)
        assert np.allclose(p.predire(grille), y, atol=1e-10)

    def test_quadratique_exacte_sur_un_composite(self) -> None:
        points = np.array(generateurs.composite_centre(4))
        f = 1 + points[:, 0] - 2 * points[:, 1] ** 2 + 0.5 * points[:, 2] * points[:, 3]
        p = Polynome(indices_degre_total(4, 2)).ajuster(points, f)
        q = np.random.default_rng(0).uniform(-1, 1, (50, 4))
        attendu = 1 + q[:, 0] - 2 * q[:, 1] ** 2 + 0.5 * q[:, 2] * q[:, 3]
        assert np.allclose(p.predire(q), attendu, atol=1e-10)


class TestPlanVarianceMaximale:
    @staticmethod
    def _orbites(n: int) -> list[np.ndarray]:
        """Candidats dans x ≥ 0,5, image par le miroir x → 1 − x."""
        rng = np.random.default_rng(3)
        return [np.array([[0.5 + x / 2, y], [0.5 - x / 2, y]]) for x, y in rng.random((n, 2))]

    def test_distincts_et_nombre(self) -> None:
        choisis = plan_variance_maximale(self._orbites(200), 12, 0.3)
        assert len(choisis) == len(set(choisis)) == 12

    def test_les_points_connus_repoussent(self) -> None:
        orbites = self._orbites(300)
        connu = np.array([[0.75, 0.5], [0.25, 0.5]])
        libre = plan_variance_maximale(orbites, 1, 0.3)
        contraint = plan_variance_maximale(orbites, 1, 0.3, connus=connu)
        distance = [float(np.hypot(*(orbites[i][0] - connu[0]))) for i in (*libre, *contraint)]
        assert distance[1] > 0.25 and distance[1] >= distance[0] - 1e-12

    def test_les_images_comptent(self) -> None:
        # Le krigeage de la table voit chaque calcul et son image : un plan choisi en le
        # sachant laisse moins d'incertitude sur le domaine complet qu'un plan qui l'ignore.
        orbites = self._orbites(400)
        avec = plan_variance_maximale(orbites, 8, 0.25)
        sans = plan_variance_maximale([o[:1] for o in orbites], 8, 0.25)
        tout = np.random.default_rng(9).random((2000, 2))

        def variance_max(choisis: list[int]) -> float:
            vus = np.vstack([orbites[i] for i in choisis])
            k = matern52(vus, vus, np.full(2, 0.25)) + 1e-10 * np.eye(len(vus))
            r = matern52(tout, vus, np.full(2, 0.25))
            return float((1 - np.einsum("ij,ji->i", r, np.linalg.solve(k, r.T))).max())

        assert variance_max(avec) < variance_max(sans)


# ---------------------------------------------------------------------------
# engine : les nouveaux plans
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def nouveaux() -> Resultat:
    return _remplir(
        {
            "sobol": {"type": "sobol", "points_par_mach": 16, "test": 0},
            "krig": {"type": "krigeage", "points_par_mach": 14, "test": 0, "portee": 0.3},
        }
    )


class TestNouveauxPlans:
    @pytest.mark.parametrize("nom", ["sobol", "krig"])
    def test_points_dans_les_sous_domaines(self, nouveaux: Resultat, nom: str) -> None:
        c, plan = nouveaux.contexte, nouveaux.plan(nom)
        assert plan.reconstruction == "krigeage"
        assert all(c.placer(p.valeurs) == p.sous_domaine for p in plan.points)
        for mach in c.machs:
            assert sum(p.valeurs["mach"] == mach for p in plan.points) == plan.par_mach()[mach]

    def test_krigeage_un_point_par_tirage_et_par_mach(self, nouveaux: Resultat) -> None:
        assert set(nouveaux.plan("krig").par_mach().values()) == {14}

    def test_krigeage_place_ses_points_hors_des_exclusions(self) -> None:
        plan = _remplir(
            {"krig": {"type": "krigeage", "points_par_mach": 10, "test": 0}},
            exclure=["mach >= 2 and abs(alpha) > 10"],
        ).plan("krig")
        # Les candidats exclus sont retirés avant le choix : aucun point perdu ensuite.
        assert plan.exclus == 0
        assert set(plan.par_mach().values()) == {10}

    def test_options_refusees(self) -> None:
        with pytest.raises(ErreurRemplissage, match="portee"):
            _remplir({"k": {"type": "krigeage", "portee": 50}})


# ---------------------------------------------------------------------------
# engine : reconstruction
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def resultat() -> Resultat:
    return _remplir(
        {
            "complet": "factoriel",
            "inegal": {"type": "factoriel", "niveaux": {"alpha": {"pas": 10}}},
            "ordre1": {"type": "decomposition", "controle": {"fraction": 0.3}},
            "ordre2": {
                "type": "decomposition",
                "ordre": 2,
                "couplages": [["DM", "DN"], {"paire": ["moteur", "DM"]}, ["moteur", "DL"]],
                "controle": {"fraction": 0.3},
            },
            "etoile": "etoile",
            "composite": "composite_centre",
            "lhs": {"type": "lhs", "points_par_mach": 60},
            "mf": {"type": "multi_fidelite", "points_par_mach": 60, "points_hf_par_mach": 20},
        }
    )


@pytest.fixture(scope="module")
def vraie(resultat: Resultat) -> dict[str, np.ndarray]:
    return _vraie(resultat.contexte)


class TestReconstruction:
    def test_grille_carree(self, resultat: Resultat) -> None:
        c = resultat.contexte
        grille = grille_carree(c)
        assert grille.colonnes == ("mach", "moteur", *c.libres)
        assert grille.taille == 2 * 3 * 9 * 5 * 5 * 5 * 3 == len(grille.points())
        # Le domaine complet : la table du simulateur couvre aussi ce que les symétries déduisent.
        assert grille.axes["alpha"] == (-20, -15, -10, -5, 0, 5, 10, 15, 20)

    def test_factoriel_exact(self, resultat: Resultat, vraie: dict[str, np.ndarray]) -> None:
        tables = _tables(resultat.plan("complet"), resultat.contexte)
        assert tables.trous == 0
        for c, valeurs in vraie.items():
            assert np.allclose(tables.valeurs[c], valeurs, atol=1e-12), c

    def test_factoriel_allege_interpole(
        self, resultat: Resultat, vraie: dict[str, np.ndarray]
    ) -> None:
        tables = _tables(resultat.plan("inegal"), resultat.contexte)
        assert tables.trous == 0
        assert 0.1 < _erreur(tables, vraie) < 5.0
        # Aux nœuds communs aux deux grilles, la valeur est lue, pas interpolée.
        alpha = tables.grille.points()[:, tables.grille.colonnes.index("alpha")]
        communs = np.isin(alpha, (-20, -10, 0, 10, 20))
        assert np.allclose(tables.valeurs["CN"][communs], vraie["CN"][communs], atol=1e-12)

    def test_decomposition_ordre_1_et_son_controle(
        self, resultat: Resultat, vraie: dict[str, np.ndarray]
    ) -> None:
        tables = _tables(resultat.plan("ordre1"), resultat.contexte)
        erreur = _erreur(tables, vraie)
        assert erreur > 1.0  # le modèle a des interactions que l'ordre 1 ignore
        # Les points de contrôle le voient : c'est ce qu'ils sont là pour faire.
        controle = max(
            100 * float(np.sqrt(np.mean(e**2))) / float(np.ptp(vraie[c]))
            for c, e in tables.ecarts["controle"].items()
        )
        assert controle > 1.0

    def test_decomposition_ordre_2_avec_les_bons_couplages_exacte(
        self, resultat: Resultat, vraie: dict[str, np.ndarray]
    ) -> None:
        tables = _tables(resultat.plan("ordre2"), resultat.contexte)
        assert _erreur(tables, vraie) < 1e-9
        assert all(np.abs(e).max() < 1e-9 for e in tables.ecarts["controle"].values())

    def test_somme_de_l_etoile(self, resultat: Resultat) -> None:
        plan = resultat.plan("etoile")
        assert sum(s for s, _ in plan.termes) == 1  # C0 + Σ (C_v − C0) : un seul C0 net
        c = resultat.contexte

        # Un modèle exactement additif est reproduit par l'étoile.
        def additif(points: Any) -> Mesures:
            y = {
                "CA": np.array(
                    [
                        1 + p.valeurs["alpha"] ** 2 + p.valeurs["DM"] ** 2 + p.valeurs["moteur"]
                        for p in points
                    ]
                )
            }
            return Mesures(tuple(points), y)

        tables = reconstruire(plan, c, additif(plan.points))
        grille = tables.grille.points()
        col = list(tables.grille.colonnes)
        attendu = (
            1
            + grille[:, col.index("alpha")] ** 2
            + grille[:, col.index("DM")] ** 2
            + grille[:, col.index("moteur")]
        )
        assert np.allclose(tables.valeurs["CA"], attendu)

    def test_composite_exact_sur_une_quadratique_symetrique(self, resultat: Resultat) -> None:
        plan, c = resultat.plan("composite"), resultat.contexte

        def quadratique(points: Any) -> Mesures:
            a = np.array([p.valeurs["alpha"] for p in points])
            dm = np.array([p.valeurs["DM"] for p in points])
            m = np.array([p.valeurs["moteur"] for p in points])
            # CA pair en α, δm ; CN impair en (α, δm) ensemble : compatibles avec les miroirs.
            return Mesures(
                tuple(points), {"CA": 1 + a**2 + 0.1 * dm**2 + m, "CN": a + 0.5 * dm + a * m}
            )

        tables = reconstruire(plan, c, quadratique(plan.points))
        grille = tables.grille.points()
        col = list(tables.grille.colonnes)
        a, dm, m = (grille[:, col.index(n)] for n in ("alpha", "DM", "moteur"))
        assert np.allclose(tables.valeurs["CA"], 1 + a**2 + 0.1 * dm**2 + m, atol=1e-8)
        assert np.allclose(tables.valeurs["CN"], a + 0.5 * dm + a * m, atol=1e-8)

    def test_krigeage_et_co_krigeage(
        self, resultat: Resultat, vraie: dict[str, np.ndarray]
    ) -> None:
        c = resultat.contexte
        lhs = _tables(resultat.plan("lhs"), c, portees_communes=True)
        assert _erreur(lhs, vraie) < 3.0
        assert "test" in lhs.ecarts
        mf = _tables(resultat.plan("mf"), c, portees_communes=True)
        assert _erreur(mf, vraie) < 5.0
        # Sans la correction HF, la BF seule porterait son biais (≈ 10 % de l'étendue).
        bf = dataclasses.replace(resultat.plan("mf"), reconstruction="krigeage")
        seule = reconstruire(
            bf,
            c,
            rt.calculer(bf.points, c).selection(lambda p: p.fidelite == "BF"),
            portees_communes=True,
        )
        assert _erreur(seule, vraie) > 2 * _erreur(mf, vraie)

    def test_les_symetries_sont_exactes_dans_la_table(self, resultat: Resultat) -> None:
        # Le krigeage voit les images : la table respecte les symétries au bruit près.
        c = resultat.contexte
        tables = _tables(resultat.plan("lhs"), c, portees_communes=True)
        grille = tables.grille.points()
        col = list(tables.grille.colonnes)
        index = {tuple(np.round(ligne, 9)): i for i, ligne in enumerate(grille)}
        miroir_h = next(s for s in c.symetries if s["nom"] == "miroir H")
        ecarts = []
        for i, ligne in enumerate(grille[:500]):
            image = ligne.copy()
            for v in miroir_h["variables"]:
                if v in col:
                    image[col.index(v)] *= -1
            j = index[tuple(np.round(image, 9))]
            ecarts.append(tables.valeurs["CN"][i] + tables.valeurs["CN"][j])  # CN impair
        assert np.abs(ecarts).max() < 1e-6

    def test_exclusions_laissees_vides(self) -> None:
        resultat = _remplir(
            {"complet": "factoriel", "lhs": {"type": "lhs", "points_par_mach": 40}},
            exclure=["mach >= 2 and abs(alpha) > 15"],
        )
        c = resultat.contexte
        attendu = 3 * 2 * 5 * 5 * 5 * 3  # Mach 2 × moteur × α = ±20 × β × δm × δn × δl
        for nom in ("complet", "lhs"):
            tables = _tables(resultat.plan(nom), c, portees_communes=True)
            assert tables.exclus == attendu
            assert tables.trous == attendu

    def test_aller_retour_des_resultats(self, resultat: Resultat, tmp_path: Path) -> None:
        c, plan = resultat.contexte, resultat.plan("ordre1")
        mesures = rt.calculer(plan.points, c)
        chemin = ecrire_mesures(mesures, c, tmp_path / "resultats.csv")
        relues = lire_mesures(chemin, c)
        assert relues.noms == mesures.noms
        assert [p.role for p in relues.points] == [p.role for p in mesures.points]
        for nom in mesures.noms:
            assert np.allclose(relues.coefficients[nom], mesures.coefficients[nom], atol=1e-9)
        # Relues ou non, la même table.
        a = reconstruire(plan, c, mesures).valeurs["Cm"]
        b = reconstruire(plan, c, relues).valeurs["Cm"]
        assert np.allclose(a, b, atol=1e-8)

    def test_une_table_par_coefficient_carree(self, resultat: Resultat, tmp_path: Path) -> None:
        c = resultat.contexte
        tables = _tables(resultat.plan("complet"), c)
        fichiers = ecrire_tables(tables, tmp_path)
        assert sorted(f.name for f in fichiers) == sorted(
            f"{x}.csv" for x in c.reduction.etude.trajectoire.coefficients
        )
        with fichiers[0].open(encoding="utf-8") as f:
            lignes = list(csv.reader(f, delimiter="\t"))
        assert lignes[0] == [*tables.grille.colonnes, fichiers[0].stem]
        noeuds = {tuple(ligne[:-1]) for ligne in lignes[1:]}
        assert len(lignes) - 1 == len(noeuds) == tables.grille.taille

    def test_polaire_refuse(self) -> None:
        donnees = _donnees({"lhs": {"type": "lhs", "points_par_mach": 10}})
        donnees["repere"] = "polaire"
        resultat = remplir(remplissage_depuis_dict(donnees))
        plan = resultat.plan("lhs")
        mesures = Mesures(plan.points, {"CA": np.zeros(len(plan.points))})
        with pytest.raises(ErreurRemplissage, match="cartésien seulement"):
            reconstruire(plan, resultat.contexte, mesures)

    def test_enrichissement_adaptatif(self) -> None:
        resultat = _remplir({"a": {"type": "adaptatif", "points_par_mach": 12}})
        c, plan = resultat.contexte, resultat.plan("a")
        vraie = _vraie(c)
        mesures = rt.calculer(plan.points, c)
        avant = _erreur(reconstruire(plan, c, mesures, portees_communes=True), vraie)
        for k in range(2):
            lot = lot_suivant(plan, c, mesures, 12, graine=k)
            assert len(lot) == 12 * len(c.machs) * 1
            assert all(c.placer(p.valeurs) is not None for p in lot)
            deja = {tuple(round(p.valeurs[x], 9) for x in c.colonnes) for p in mesures.points}
            assert not any(tuple(round(p.valeurs[x], 9) for x in c.colonnes) in deja for p in lot)
            mesures = mesures + rt.calculer(lot, c)
        apres = _erreur(reconstruire(plan, c, mesures, portees_communes=True), vraie)
        assert apres < 0.6 * avant


# ---------------------------------------------------------------------------
# report : zones des figures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("repere", ["cartesien", "polaire"])
def test_zones_vectorisees_comme_le_moteur(repere: str) -> None:
    """Le fond des figures dit exactement ce que le moteur ferait de chaque nœud."""
    remplissage = charger_remplissage(EXEMPLE_DIR / "REMPLISSAGE_FUSEE.yaml")
    remplissage = dataclasses.replace(remplissage, etude=remplissage.etude.avec(repere=repere))
    from cfd_doe.engine.remplissage import preparer

    c = preparer(remplissage)
    noms = list(c.variables)
    niveaux = [figures._niveaux_affiches(c, v) for v in noms]
    points = np.array(list(itertools.product(*niveaux)))
    zone, _ = figures._zones(c, {v: points[:, i] for i, v in enumerate(noms)})
    attendu = [
        1 if c.placer(dict(zip(noms, p))) is not None else 2 if c.replier(dict(zip(noms, p))) else 0
        for p in points
    ]
    assert zone.tolist() == attendu
    assert {0, 1, 2} >= set(zone.tolist()) and 2 in zone


# ---------------------------------------------------------------------------
# Les exemples
# ---------------------------------------------------------------------------

CAS = sorted((EXEMPLE_DIR / "CAS").glob("REMPLISSAGE_*.yaml"))


def test_les_cas_couvrent_trajectoires_et_symetries() -> None:
    etudes = [charger_remplissage(f).etude for f in CAS]
    assert len({e.trajectoire.nom for e in etudes}) >= 5
    assert len({e.geometrie.nom for e in etudes}) >= 5
    assert any(p.discret for f in CAS for p in charger_remplissage(f).parametres)


@pytest.mark.parametrize("chemin", CAS, ids=lambda p: p.stem)
@pytest.mark.parametrize("repere", ["cartesien", "polaire"])
def test_chaque_cas_se_remplit(chemin: Path, repere: str, tmp_path: Path) -> None:
    remplissage = charger_remplissage(chemin)
    actives = remplissage.etude.trajectoire.actives
    if repere == "polaire" and not {"alpha", "beta"} <= set(actives):
        # Le polaire demande α et β : refusé, avec un message qui le dit.
        with pytest.raises(ErreurEtude, match="polaire impossible"):
            remplir(dataclasses.replace(remplissage, etude=remplissage.etude.avec(repere=repere)))
        return
    remplissage = dataclasses.replace(remplissage, etude=remplissage.etude.avec(repere=repere))
    resultat = remplir(remplissage)
    assert all(plan.points for plan in resultat.plans)
    assert resultat.retenu.compter() > 0


def test_reconstruire_tables_sur_le_missile(tmp_path: Path) -> None:
    bilans = rt.principal(
        [
            str(EXEMPLE_DIR / "CAS" / "REMPLISSAGE_MISSILE_3DOF.yaml"),
            "--sortie",
            str(tmp_path),
            "--rapide",
            "--sans-figures",
            "--tables",
            "tous",
        ]
    )
    par_nom = {b.plan.nom: b for b in bilans}
    # Factoriel complet : exact, aux 10 chiffres significatifs du fichier de résultats près.
    assert par_nom["complet"].pire < 1e-6
    assert par_nom["krigeage"].pire < 2.0
    for nom in par_nom:
        assert sorted(p.name for p in (tmp_path / "TABLES" / nom).iterdir()) == [
            "CA.csv",
            "CN.csv",
            "Cm.csv",
        ]
        assert (tmp_path / "RESULTATS" / f"{nom}.csv").is_file()


def test_executer_exemples(tmp_path: Path) -> None:
    import executer_exemples

    assert executer_exemples.executer(["--rapide", "--cas", "OBUS", "--sortie", str(tmp_path)]) == 0
    assert (tmp_path / "OBUS_3DOF" / "DOE" / "doe.csv").is_file()
    assert any((tmp_path / "OBUS_3DOF" / "RECONSTRUCTION" / "TABLES").iterdir())


def test_exemple_copie_les_cas(tmp_path: Path) -> None:
    assert main(["exemple", str(tmp_path / "ex")]) == 0
    for nom in ("reconstruire_tables.py", "executer_exemples.py"):
        assert (tmp_path / "ex" / nom).is_file()
    assert len(list((tmp_path / "ex" / "CAS").glob("*.yaml"))) == 2 * len(CAS)


def test_formats_de_figures() -> None:
    donnees = _donnees({"p": "etoile"}, sortie={"formats": ["svg"]})
    assert remplissage_depuis_dict(donnees).sortie.formats == ("svg",)
    with pytest.raises(ErreurRemplissage, match="tiff"):
        remplissage_depuis_dict(_donnees({"p": "etoile"}, sortie={"formats": ["png", "tiff"]}))


@pytest.mark.skipif(not CFD_PLOT, reason="cfd-plot absent")
def test_figures_de_reconstruction(tmp_path: Path) -> None:
    resultat = _remplir({"complet": "factoriel", "ordre1": "decomposition"})
    c = resultat.contexte
    vraie = _vraie(c)
    tables = [_tables(p, c) for p in resultat.plans]
    precision = figures.figure_precision(
        [figures.Precision(t.plan, t.plan.compter(), _erreur(t, vraie)) for t in tables],
        tmp_path,
        formats=("png",),
    )
    coupes = figures.figure_coupes(
        c, tables, "CN", tmp_path, reference=vraie["CN"], formats=("png", "pdf")
    )
    assert precision.stat().st_size > 10_000 and coupes.stat().st_size > 10_000
    assert coupes.with_suffix(".pdf").is_file()


@pytest.mark.skipif(not CFD_PLOT, reason="cfd-plot absent")
@pytest.mark.parametrize(
    "chemin",
    [
        EXEMPLE_DIR / "CAS" / "REMPLISSAGE_DRONE_4DOF.yaml",
        EXEMPLE_DIR / "CAS" / "REMPLISSAGE_MISSILE_3DOF.yaml",
    ],
    ids=lambda p: p.stem,
)
def test_figures_sans_symetrie_ou_a_deux_variables(chemin: Path, tmp_path: Path) -> None:
    donnees = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    remplissage = remplissage_depuis_dict(donnees, source=chemin)
    fichiers = figures.tracer_figures(remplir(remplissage), tmp_path, ("png",))
    assert len(fichiers) == 1 + len(remplissage.plans) + 2
