"""Remplissage des sous-domaines : plans, décomptes, fichier DOE, commande ``remplir``.

L'exemple est celui de 00_DOC/02_REMPLISSAGE.md (double symétrie, 8 Mach, un
paramètre moteur à 3 niveaux) : les plans sur grille doivent retrouver ses
décomptes exacts.
"""

from __future__ import annotations

import csv
import importlib.util
import math
from pathlib import Path
from typing import Any

import pytest
import yaml
from rich.console import Console

from cfd_doe.cli.main import main
from cfd_doe.core import plans as generateurs
from cfd_doe.core.expression import compiler
from cfd_doe.core.intervalle import Intervalle
from cfd_doe.data.remplissage import (
    TYPES,
    ErreurRemplissage,
    remplissage_depuis_dict,
    resoudre_niveaux,
)
from cfd_doe.engine.remplissage import PlanDOE, Resultat, code_table, ecrire_csv, remplir
from cfd_doe.paths import EXEMPLE_DIR
from cfd_doe.report.remplissage import rapport_remplissage

CFD_PLOT = importlib.util.find_spec("cfd_plot") is not None

MACH = [0.6, 0.8, 0.95, 1.05, 1.2, 1.5, 2.0, 3.0]
PLAGES = {"alpha": [-20, 20], "beta": [-5, 5], "DL": [-10, 10], "DM": [-20, 20], "DN": [-20, 20]}
NIVEAUX_CARTESIENS = {
    "alpha": {"pas": 5},
    "beta": {"pas": 2.5},
    "DM": {"pas": 10},
    "DN": {"pas": 10},
    "DL": {"pas": 10},
}
NIVEAUX_POLAIRES = {
    "alphat": {"pas": 5},
    "phia": {"pas": 15},
    "DMB": {"pas": 10},
    "DNB": {"pas": 10},
    "DL": {"pas": 10},
}


def _donnees(
    plans: dict[str, Any], geometrie: str = "double_symetrie", **extra: Any
) -> dict[str, Any]:
    donnees: dict[str, Any] = {
        "etude": {
            "etude": {"nom": "DOC"},
            "trajectoire": "6DOF",
            "geometrie": geometrie,
            "variables": PLAGES,
        },
        "mach": MACH,
        "parametres": {"moteur": {"niveaux": [0, 0.5, 1], "nominal": 0}},
        "niveaux": {**NIVEAUX_CARTESIENS, **NIVEAUX_POLAIRES},
        "plans": plans,
    }
    donnees.update(extra)
    return donnees


def _remplir(plans: dict[str, Any], geometrie: str = "double_symetrie", **extra: Any) -> Resultat:
    return remplir(remplissage_depuis_dict(_donnees(plans, geometrie, **extra)))


def _un(definition: Any, geometrie: str = "double_symetrie", **extra: Any) -> PlanDOE:
    return _remplir({"p": definition}, geometrie, **extra).plan("p")


def _cles(plan: PlanDOE, colonnes: tuple[str, ...]) -> list[tuple[Any, ...]]:
    return [(p.fidelite, *(round(p.valeurs[c], 9) for c in colonnes)) for p in plan.points]


# ---------------------------------------------------------------------------
# core : générateurs et expressions
# ---------------------------------------------------------------------------


class TestGenerateurs:
    @pytest.mark.parametrize("k", [2, 5, 6])
    def test_composite_centre(self, k: int) -> None:
        assert len(generateurs.composite_centre(k)) == 2**k + 2 * k + 1
        demi = generateurs.composite_centre(k, fraction=1) if k > 2 else []
        if demi:
            assert len(demi) == 2 ** (k - 1) + 2 * k + 1
            assert all(math.prod(p[:-1]) == p[-1] for p in demi[: 2 ** (k - 1)])

    def test_box_behnken_sans_sommet(self) -> None:
        points = generateurs.box_behnken(6)
        assert len(points) == 4 * 15 + 1
        assert all(sum(x != 0 for x in p) <= 2 for p in points)

    @pytest.mark.parametrize(
        ("d", "attendus"), [(5, (11, 61, 241)), (6, (13, 85, 389)), (7, (15, 113, 589))]
    )
    def test_grille_creuse_formules(self, d: int, attendus: tuple[int, ...]) -> None:
        assert tuple(len(generateurs.grille_creuse(d, n)) for n in (1, 2, 3)) == attendus

    def test_grilles_creuses_emboitees(self) -> None:
        assert set(generateurs.grille_creuse(4, 2)) <= set(generateurs.grille_creuse(4, 3))

    def test_hypercube_latin_une_fois_par_tranche(self) -> None:
        n, k = 17, 4
        points = generateurs.hypercube_latin(n, k, graine=3)
        for j in range(k):
            assert sorted(int(p[j] * n) for p in points) == list(range(n))
        assert points == generateurs.hypercube_latin(n, k, graine=3)
        assert points != generateurs.hypercube_latin(n, k, graine=4)

    def test_halton_extensible(self) -> None:
        longue = generateurs.halton(20, 3)
        assert generateurs.halton(8, 3) == longue[:8]
        assert generateurs.halton(12, 3, depart=9) == longue[8:]
        assert all(0 < x < 1 for p in longue for x in p)

    def test_sous_ensemble_maximin(self) -> None:
        points = [(float(i), 0.0) for i in range(11)]
        choisis = generateurs.sous_ensemble_maximin(points, 3)
        assert sorted(choisis) == [0, 5, 10]
        assert generateurs.sous_ensemble_maximin(points, 99) == list(range(11))


class TestExpression:
    NOMS = frozenset({"mach", "alpha", "moteur"})

    @pytest.mark.parametrize(
        ("texte", "point", "attendu"),
        [
            ("mach >= 2 and abs(alpha) > 15", {"mach": 2.0, "alpha": -20.0, "moteur": 0.0}, True),
            ("mach >= 2 and abs(alpha) > 15", {"mach": 1.5, "alpha": -20.0, "moteur": 0.0}, False),
            (
                "not (0 < alpha <= 10) or moteur == 1",
                {"mach": 1.0, "alpha": 5.0, "moteur": 1.0},
                True,
            ),
            ("alpha * 2 + 1 > max(mach, 10)", {"mach": 1.0, "alpha": 5.0, "moteur": 0.0}, True),
        ],
    )
    def test_evaluation(self, texte: str, point: dict[str, float], attendu: bool) -> None:
        assert compiler(texte, self.NOMS)(point) is attendu

    @pytest.mark.parametrize(
        "texte",
        [
            "beta > 0",  # nom inconnu
            "__import__('os').system('ls')",
            "alpha.real > 0",
            "alpha[0] > 0",
            "mach > 'a'",
            "alpha >",
            "~alpha > 0",
            "lambda: 1",
        ],
    )
    def test_refus(self, texte: str) -> None:
        with pytest.raises(ValueError, match=r"«|illisible"):
            compiler(texte, self.NOMS)


# ---------------------------------------------------------------------------
# data : fichier de remplissage
# ---------------------------------------------------------------------------


class TestFichier:
    def test_plans_par_defaut_tous_les_types(self) -> None:
        donnees = _donnees({})
        del donnees["plans"]
        r = remplissage_depuis_dict(donnees)
        assert tuple(p.type for p in r.plans) == TYPES
        assert r.retenu == "decomposition"

    @pytest.mark.parametrize(
        ("modification", "motif"),
        [
            ({"plan": 1}, "clé\\(s\\) inconnue\\(s\\) plan"),
            ({"plans": {"p": {"type": "monte_carlo"}}}, "type « monte_carlo » inconnu"),
            ({"plans": {"p": {"type": "lhs", "regles": 30}}}, "regles"),
            ({"retenu": "absent"}, "n'est pas un des plans"),
            ({"parametres": {"mach": [0, 1]}}, "nom réservé"),
            ({"parametres": {"mon param": [0, 1]}}, "identifiant"),
            ({"parametres": {"p": {"niveaux": [0, 1], "nominal": 0.5}}}, "nominal"),
            ({"niveaux": {"gamma": [0, 1]}}, "gamma"),
            ({"mach": [-1]}, "négatives"),
            ({"sortie": {"dossiers": "X"}}, "dossiers"),
        ],
    )
    def test_refus(self, modification: dict[str, Any], motif: str) -> None:
        with pytest.raises(ErreurRemplissage, match=motif):
            remplissage_depuis_dict({**_donnees({"p": "factoriel"}), **modification})

    def test_etude_par_chemin_relatif(self, tmp_path: Path) -> None:
        (tmp_path / "E.yaml").write_text(
            yaml.safe_dump(_donnees({})["etude"], allow_unicode=True), encoding="utf-8"
        )
        fichier = tmp_path / "R.yaml"
        fichier.write_text("etude: E.yaml\nmach: [0.8]\nplans: {p: etoile}\n", encoding="utf-8")
        from cfd_doe.data.remplissage import charger_remplissage

        assert charger_remplissage(fichier).etude.nom == "DOC"

    def test_niveaux(self) -> None:
        boite = Intervalle(-20.0, 20.0)
        assert resoudre_niveaux("a", {"pas": 10}, boite, symetrique=True, reference=0.0)[0] == (
            -20.0, -10.0, 0.0, 10.0, 20.0,
        )  # fmt: skip
        assert resoudre_niveaux("a", {"n": 3}, boite, symetrique=True, reference=0.0)[0] == (
            -20.0, 0.0, 20.0,
        )  # fmt: skip
        niveaux, notes = resoudre_niveaux("a", [5, 10], boite, symetrique=True, reference=0.0)
        assert niveaux == (-10.0, -5.0, 0.0, 5.0, 10.0)
        assert len(notes) == 2  # opposés ajoutés, puis la référence
        with pytest.raises(ErreurRemplissage, match="hors du domaine"):
            resoudre_niveaux("a", [25], boite, symetrique=False, reference=0.0)
        with pytest.raises(ErreurRemplissage, match="une seule clé"):
            resoudre_niveaux("a", {"pas": 1, "n": 2}, boite, symetrique=False, reference=0.0)


# ---------------------------------------------------------------------------
# engine : décomptes du document
# ---------------------------------------------------------------------------

REDUIT = {"beta": [-5, 0, 5], "DM": [-20, 0, 20], "DN": [-20, 0, 20]}
ORDRE_2 = {
    "type": "decomposition",
    "ordre": 2,
    "couplages": [["DM", "DN"], ["moteur", "DM"]],
    "controle": False,
}


@pytest.fixture(scope="module")
def document() -> Resultat:
    return _remplir(
        {
            "complet": "factoriel",
            "reduit": {"type": "factoriel", "niveaux": REDUIT},
            "etoile": "etoile",
            "ordre1": {"type": "decomposition", "controle": False},
            "ordre2": ORDRE_2,
            "composite": {"type": "composite_centre", "test": 0},
            "behnken": {"type": "box_behnken", "test": 0},
            "creuse2": {"type": "grille_creuse", "test": 0},
            "creuse3": {"type": "grille_creuse", "niveau": 3, "test": 0},
        }
    )


class TestDecomptesDuDocument:
    @pytest.mark.parametrize(
        ("plan", "total"),
        [
            ("complet", 20_688),
            ("reduit", 4_608),
            ("etoile", 112),
            ("ordre1", 624),
            ("ordre2", 1_952),
            ("composite", 192),
            ("behnken", 184),
            ("creuse2", 296),
            ("creuse3", 1_112),
        ],
    )
    def test_total(self, document: Resultat, plan: str, total: int) -> None:
        assert document.plan(plan).compter() == total

    def test_tables_de_l_ordre_1(self, document: Resultat) -> None:
        tables = {b.nom: n // len(MACH) for b, n in document.plan("ordre1").par_bloc()}
        assert tables == {"base": 15, "Δδm": 18, "Δδn": 10, "Δδl": 5, "Δmoteur": 30}

    def test_tables_de_l_ordre_2(self, document: Resultat) -> None:
        tables = {b.nom: n // len(MACH) for b, n in document.plan("ordre2").par_bloc()}
        assert tables == {
            "base": 15,
            "Δδm": 54,
            "Δδn": 50,
            "Δδl": 23,
            "Δmoteur": 30,
            "Δδm×δn": 36,
            "Δmoteur×δm": 36,
        }

    def test_chaque_point_dans_son_sous_domaine_une_fois(self, document: Resultat) -> None:
        c = document.contexte
        for plan in document.plans:
            cles = _cles(plan, c.colonnes)
            assert len(cles) == len(set(cles)), plan.nom
            for p in plan.points:
                dedans = [sd.numero for sd in c.sous_domaines if sd.contient(p.valeurs)]
                assert dedans == [p.sous_domaine], plan.nom

    def test_factoriel_un_representant_par_orbite(self, document: Resultat) -> None:
        """Replier toute la grille sur les sous-domaines redonne exactement le plan factoriel."""
        c = document.contexte
        mach0 = [p for p in document.plan("complet").points if p.valeurs["mach"] == MACH[0]]
        calcules = {
            tuple(round(p.valeurs[v], 9) for v in c.variables)
            for p in mach0
            if p.valeurs["moteur"] == 0
        }
        replies = set()
        import itertools

        for noeud in itertools.product(*(c.niveaux[v] for v in c.variables)):
            ramene = c.replier(dict(zip(c.variables, noeud)))
            assert ramene is not None
            replies.add(tuple(round(ramene[0][v], 9) + 0.0 for v in c.variables))
        assert replies == calcules
        assert len(calcules) == 862


# ---------------------------------------------------------------------------
# engine : chaque méthode
# ---------------------------------------------------------------------------


class TestDecomposition:
    def test_controles_hors_du_plan_et_croises(self) -> None:
        plan = _un({"type": "decomposition", "controle": {"fraction": 0.15, "graine": 3}})
        calculs = {
            k
            for k, p in zip(_cles(plan, ("mach", "moteur", *PLAGES)), plan.points)
            if p.role == "calcul"
        }
        controles = [p for p in plan.points if p.role == "controle"]
        assert len(controles) == len(MACH) * math.ceil(0.15 * 78)
        for p in controles:
            actifs = sum(p.valeurs[e] != 0 for e in ("DM", "DN", "DL", "moteur"))
            assert actifs >= 2
            assert p.valeurs["alpha"] % 5 == 0 and p.valeurs["DM"] % 10 == 0
        assert not calculs & {
            k
            for k, p in zip(_cles(plan, ("mach", "moteur", *PLAGES)), plan.points)
            if p.role == "controle"
        }
        assert any("controle" in etape for etape in plan.demarche)

    def test_sans_controle_la_demarche_le_dit(self) -> None:
        plan = _un({"type": "decomposition", "controle": False})
        assert plan.compter("controle") == 0
        assert any("Aucun point de contrôle" in etape for etape in plan.demarche)

    def test_options_d_increments(self) -> None:
        """Faire dépendre Δδm de (α, β) : la table passe de 18 à 54 points par Mach."""
        plan = _un(
            {"type": "decomposition", "controle": False, "increments": {"DM": ["alpha", "beta"]}}
        )
        tables = {b.nom: n // len(MACH) for b, n in plan.par_bloc()}
        assert tables["Δδm"] == 54 and tables["Δδn"] == 10

    def test_croiser_un_parametre(self) -> None:
        """Un paramètre croisé multiplie tout le plan au lieu d'être un incrément."""
        plan = _un({"type": "decomposition", "controle": False, "croiser": ["moteur"]})
        assert plan.compter() == (15 + 18 + 10 + 5) * 3 * len(MACH)
        assert "Δmoteur" not in {b.nom for b in plan.blocs}

    def test_couplages_tous_par_defaut_a_l_ordre_2(self) -> None:
        plan = _un({"type": "decomposition", "ordre": 2, "controle": False})
        assert sum(b.nom.count("×") for b in plan.blocs) == 6  # 4 effets, 6 paires

    @pytest.mark.parametrize(
        ("options", "motif"),
        [
            ({"ordre": 3}, "ordre 1 ou 2"),
            ({"couplages": [["DM", "XX"]]}, "XX"),
            ({"couplages": [["DM"]]}, "paires"),
            ({"primaires": ["gamma"]}, "gamma"),
            ({"controle": {"fractions": 0.1}}, "controle"),
        ],
    )
    def test_refus(self, options: dict[str, Any], motif: str) -> None:
        with pytest.raises(ErreurRemplissage, match=motif):
            _un({"type": "decomposition", **options})


class TestTirages:
    @pytest.mark.parametrize("genre", ["lhs", "halton"])
    def test_regle_et_repartition(self, genre: str) -> None:
        """30·d / 4 = 45 points par Mach, dont un quart sur les plans de symétrie."""
        plan = _un({"type": genre, "test": 0.2})
        assert plan.compter("calcul") == 45 * len(MACH)
        assert plan.compter("test") == math.ceil(0.2 * 45) * len(MACH)
        par_sd = plan.par_sous_domaine()
        sur_plans = sum(n for k, n in par_sd.items() if k != 1)
        calculs_sur_plans = sum(p.sous_domaine != 1 for p in plan.points if p.role == "calcul")
        assert calculs_sur_plans == round(0.25 * 45) * len(MACH)
        assert sur_plans >= calculs_sur_plans
        assert plan.facteurs == ("alpha", "beta", "DM", "DN", "DL", "moteur")

    def test_reproductible_et_decale_par_mach(self) -> None:
        a, b = _un({"type": "lhs", "graine": 5}), _un({"type": "lhs", "graine": 5})
        assert [p.valeurs for p in a.points] == [p.valeurs for p in b.points]
        autre = _un({"type": "lhs", "graine": 6})
        assert [p.valeurs for p in a.points] != [p.valeurs for p in autre.points]

        def alphas(plan: PlanDOE, mach: float) -> list[float]:
            return sorted(p.valeurs["alpha"] for p in plan.points if p.valeurs["mach"] == mach)

        assert alphas(a, 0.6) != alphas(a, 0.8)
        fige = _un({"type": "lhs", "graine": 5, "decale_par_mach": False})
        assert alphas(fige, 0.6) == alphas(fige, 0.8)

    def test_points_imposes(self) -> None:
        plan = _un({"type": "lhs", "points_par_mach": 20, "part_plans": 0, "test": 0})
        assert plan.compter() == 20 * len(MACH)
        assert set(plan.par_sous_domaine()) == {1}

    def test_adaptatif_lot_initial(self) -> None:
        plan = _un({"type": "adaptatif", "test": 0})
        assert plan.compter() == math.ceil(10 * 6 / 4) * len(MACH)
        assert any("lot initial" in etape for etape in plan.demarche)

    def test_multi_fidelite_emboitee(self) -> None:
        plan = _un({"type": "multi_fidelite", "test": 0})
        colonnes = ("mach", "moteur", *PLAGES)
        bf = {k[1:] for k, p in zip(_cles(plan, colonnes), plan.points) if p.fidelite == "BF"}
        hf = {k[1:] for k, p in zip(_cles(plan, colonnes), plan.points) if p.fidelite == "HF"}
        assert len(bf) == 45 * len(MACH) and len(hf) == math.ceil(8 * 6 / 4) * len(MACH)
        assert hf <= bf
        assert plan.fidelites == ("BF", "HF")

    def test_disque_respecte_en_polaire(self) -> None:
        plan = _un({"type": "lhs", "points_par_mach": 60}, "cruciforme")
        assert all(math.hypot(p.valeurs["DMB"], p.valeurs["DNB"]) <= 20 + 1e-9 for p in plan.points)
        assert all(0 <= p.valeurs["phia"] <= 45 for p in plan.points)


class TestPlansStructures:
    def test_demi_fraction_repliee_et_non_ecartee(self) -> None:
        """La demi-fraction n'est pas stable par symétrie : ses points sont repliés, pas écartés.

        Écarter ceux qui tombent hors des sous-domaines n'en laisserait que 16
        par Mach. Repliés, ils en donnent 24 — autant que le plan complet : avec
        les symétries, la fraction n'économise rien.
        """
        plan = _un({"type": "composite_centre", "test": 0})
        assert plan.compter() == 24 * len(MACH)
        complet = _un({"type": "composite_centre", "fraction": 0, "test": 0})
        colonnes = ("mach", "moteur", *PLAGES)
        assert set(_cles(complet, colonnes)) == set(_cles(plan, colonnes))

    def test_pave_inscrit_dans_le_disque(self) -> None:
        plan = _un({"type": "composite_centre", "test": 0}, "cruciforme")
        cote = 20 / math.sqrt(2)
        hors_axe = [p for p in plan.points if p.valeurs["alphat"] > 0]
        assert max(abs(p.valeurs["DMB"]) for p in hors_axe) == pytest.approx(cote)
        # Sur l'axe, les braquages ramenés à φa = 0 tournent, mais restent dans le disque.
        assert all(math.hypot(p.valeurs["DMB"], p.valeurs["DNB"]) <= 20 + 1e-9 for p in plan.points)
        assert any("inscrit dans le disque" in a for a in plan.avertissements)
        assert not any("incomplet" in a for a in plan.avertissements)

    def test_parametre_discret_croise(self) -> None:
        """Un paramètre discret n'est pas un facteur : le plan est répété à chaque niveau."""
        continu = _un({"type": "grille_creuse", "test": 0})
        discret = _un(
            {"type": "grille_creuse", "test": 0},
            parametres={"moteur": {"niveaux": [0, 1], "discret": True}},
        )
        assert "moteur" in continu.facteurs and "moteur" not in discret.facteurs
        assert {p.valeurs["moteur"] for p in discret.points} == {0.0, 1.0}


class TestConditions:
    def test_exclusion_indifferente_au_repere(self) -> None:
        exclure = ["mach >= 2 and abs(alpha) > 15"]
        for geometrie in ("double_symetrie", "cruciforme"):
            plan = _un("factoriel", geometrie, exclure=exclure)
            assert plan.exclus > 0
            assert any("exclure" in a for a in plan.avertissements)
            libre = _un("factoriel", geometrie)
            assert plan.compter() == libre.compter() - plan.exclus
            assert plan.par_mach()[0.6] == libre.par_mach()[0.6]
            assert plan.par_mach()[3.0] < libre.par_mach()[3.0]

    def test_exclusion_inconnue_refusee(self) -> None:
        with pytest.raises(ErreurRemplissage, match="gamma"):
            _un("factoriel", exclure=["gamma > 0"])

    def test_sans_mach_ni_parametre(self) -> None:
        donnees = _donnees({"p": "factoriel"})
        del donnees["mach"], donnees["parametres"]
        resultat = remplir(remplissage_depuis_dict(donnees))
        assert resultat.plan("p").compter() == 862
        assert "mach" not in resultat.contexte.colonnes

    def test_deux_parametres(self) -> None:
        parametres = {"moteur": [0, 0.5, 1], "aerofrein": {"niveaux": [0, 1], "discret": True}}
        plan = _un({"type": "decomposition", "controle": False}, parametres=parametres)
        assert plan.compter() == (48 + 15 * 2 + 15 * 1) * len(MACH)
        assert _un("factoriel", parametres=parametres).compter() == 862 * 3 * 2 * len(MACH)

    def test_noms_de_l_autre_repere(self) -> None:
        """En polaire, DM désigne δmB ; les niveaux cartésiens sont ignorés, et signalés."""
        resultat = _remplir(
            {"p": {"type": "decomposition", "couplages": [["DM", "DN"]], "controle": False}},
            "cruciforme",
        )
        assert "ΔδmB×δnB" in {b.nom for b in resultat.plan("p").blocs}
        assert any("ignorés" in n for n in resultat.contexte.notes)

    def test_revolution_une_seule_variable(self) -> None:
        donnees = _donnees(
            {"p": "factoriel", "q": {"type": "lhs", "points_par_mach": 6, "test": 0}}
        )
        donnees["etude"] = {
            "trajectoire": "3DOF_MASSE_PONCTUELLE",
            "geometrie": "revolution",
            "variables": {"alpha": [-20, 20], "beta": [-5, 5]},
        }
        del donnees["parametres"]
        resultat = remplir(remplissage_depuis_dict(donnees))
        assert resultat.contexte.libres == ("alphat",)
        assert resultat.plan("p").compter() == 5 * len(MACH)
        assert resultat.plan("q").compter() == 6 * len(MACH)


# ---------------------------------------------------------------------------
# Fichier DOE, rapport, commande
# ---------------------------------------------------------------------------


def test_code_table() -> None:
    assert code_table("Δδm×δn") == "d_DM_x_DN"
    assert code_table("ΔδmB") == "d_DMB"
    assert code_table("contrôle croisé") == "controle_croise"
    assert code_table("balayage αt") == "balayage_alphat"
    assert code_table("Δmoteur") == "d_moteur"


def _lire(chemin: Path) -> list[dict[str, str]]:
    with chemin.open(encoding="utf-8", newline="") as fichier:
        return list(csv.DictReader(fichier, delimiter="\t"))


def test_csv_cartesien(tmp_path: Path) -> None:
    resultat = _remplir({"p": "decomposition"})
    chemin = tmp_path / "sous" / "doe.csv"
    n = ecrire_csv(resultat.plan("p"), resultat.contexte, chemin)
    lignes = _lire(chemin)
    assert n == len(lignes) == resultat.plan("p").compter()
    assert list(lignes[0]) == [
        "id", "role", "table", "sous_domaine", "mach", "moteur", "alpha", "beta", "DM", "DN", "DL",
    ]  # fmt: skip
    assert [ligne["id"] for ligne in lignes] == [str(i) for i in range(1, n + 1)]
    roles = [ligne["role"] for ligne in lignes]
    assert roles == sorted(roles)  # calcul avant controle
    assert {ligne["table"] for ligne in lignes} == {
        "base", "d_DM", "d_DN", "d_DL", "d_moteur", "controle_croise",
    }  # fmt: skip
    assert "\t" in chemin.read_text(encoding="utf-8").splitlines()[0]


def test_csv_polaire_donne_le_repere_engin(tmp_path: Path) -> None:
    from cfd_doe.core.angles import braquages_mixtes, vers_alphat_phia

    resultat = _remplir(
        {"p": {"type": "lhs", "points_par_mach": 12}, "m": "multi_fidelite"}, "cruciforme"
    )
    chemin = tmp_path / "doe.csv"
    ecrire_csv(resultat.plan("p"), resultat.contexte, chemin)
    for ligne in _lire(chemin):
        x = {k: float(v) for k, v in ligne.items() if k not in ("role", "table")}
        alphat, phia = vers_alphat_phia(x["alpha"], x["beta"])
        assert alphat == pytest.approx(x["alphat"], abs=1e-6)
        assert phia == pytest.approx(x["phia"], abs=1e-5)
        dmb, dnb = braquages_mixtes(x["DM"], x["DN"], x["phia"])
        assert (dmb, dnb) == pytest.approx((x["DMB"], x["DNB"]), abs=1e-6)
    ecrire_csv(resultat.plan("m"), resultat.contexte, chemin)
    assert {ligne["fidelite"] for ligne in _lire(chemin)} == {"BF", "HF"}


def test_rapport_en_80_colonnes(document: Resultat) -> None:
    for verbeux in (False, True):
        console = Console(width=80, record=True, color_system=None)
        console.print(rapport_remplissage(document, verbeux=verbeux))
        texte = console.export_text()
        assert "Grille de référence" in texte and "Comparaison des plans (9)" in texte
        assert "Démarche" in texte
        assert "20" + chr(0x202F) + "688" in texte
        assert max(len(ligne.rstrip()) for ligne in texte.splitlines()) <= 80
    assert "par sous-domaine" in texte  # le détail n'est donné qu'en verbeux


@pytest.fixture
def exemple(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    assert main(["exemple", str(tmp_path / "ex")]) == 0
    monkeypatch.chdir(tmp_path / "ex")
    return tmp_path / "ex"


def test_exemple_livre_valide() -> None:
    from cfd_doe.data.remplissage import charger_remplissage

    remplissage = charger_remplissage(EXEMPLE_DIR / "REMPLISSAGE_FUSEE.yaml")
    assert remplissage.retenu == "ordre_1"
    assert {p.type for p in remplissage.plans} >= {"factoriel", "decomposition", "lhs"}


def test_commande_remplir(exemple: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["remplir", "REMPLISSAGE_FUSEE.yaml", "--sans-figures"]) == 0
    sortie = capsys.readouterr().out
    assert "Plan retenu : ordre_1" in sortie and "écrit :" in sortie
    lignes = _lire(exemple / "DOE" / "doe.csv")
    assert {ligne["role"] for ligne in lignes} == {"calcul", "controle"}
    assert not any(float(x["mach"]) >= 2 and abs(float(x["alpha"])) > 15 for x in lignes)
    assert not (exemple / "DOE" / "FIGURES").exists()


def test_commande_options(exemple: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["remplir", "REMPLISSAGE_FUSEE.yaml", "--retenu", "lhs", "--repere", "polaire",
         "--sortie", "AUTRE", "--sans-figures", "--verbose"]
    )  # fmt: skip
    assert code == 0
    sortie = capsys.readouterr().out
    assert "Plan retenu : lhs" in sortie and "par sous-domaine" in sortie
    lignes = _lire(exemple / "AUTRE" / "doe.csv")
    assert {"alphat", "phia", "alpha", "beta"} <= set(lignes[0])
    assert {ligne["role"] for ligne in lignes} == {"calcul", "test"}
    assert main(["remplir", "REMPLISSAGE_FUSEE.yaml", "--sans-csv", "--sans-figures"]) == 0
    assert not (exemple / "DOE").exists()


def test_commande_erreurs(exemple: Path, capsys: pytest.CaptureFixture[str]) -> None:
    for arguments in (
        ["remplir", "ABSENT.yaml"],
        ["remplir", "REMPLISSAGE_FUSEE.yaml", "--retenu", "x"],
    ):
        with pytest.raises(SystemExit) as sortie:
            main(arguments)
        assert sortie.value.code == 1
        assert "erreur" in capsys.readouterr().err


def test_tous_les_csv(exemple: Path) -> None:
    donnees = yaml.safe_load((exemple / "REMPLISSAGE_FUSEE.yaml").read_text(encoding="utf-8"))
    donnees["plans"] = {"a": "etoile", "b": {"type": "lhs", "points_par_mach": 5}}
    donnees["retenu"] = "a"
    donnees["sortie"] = {"dossier": "D", "csv": "plan.tsv", "figures": False, "tous_les_csv": True}
    (exemple / "R.yaml").write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    assert main(["remplir", "R.yaml"]) == 0
    assert sorted(p.name for p in (exemple / "D").iterdir()) == [
        "plan.tsv",
        "plan_a.tsv",
        "plan_b.tsv",
    ]


@pytest.mark.skipif(not CFD_PLOT, reason="cfd-plot non installé")
def test_figures(exemple: Path, capsys: pytest.CaptureFixture[str]) -> None:
    donnees = yaml.safe_load((exemple / "REMPLISSAGE_FUSEE.yaml").read_text(encoding="utf-8"))
    donnees["mach"] = [0.8, 2.0]
    donnees["plans"] = {
        "ordre_1": "decomposition",
        "lhs": {"type": "lhs", "points_par_mach": 12},
        "mf": {"type": "multi_fidelite", "points_par_mach": 12},
    }
    (exemple / "R.yaml").write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    for repere in ("cartesien", "polaire"):
        assert main(["remplir", "R.yaml", "--repere", repere, "--sortie", repere]) == 0
        figures = sorted(p.name for p in (exemple / repere / "FIGURES").iterdir())
        noms = [
            "comparaison_calculs",
            "comparaison_plans",
            "domaine",
            "plan_lhs",
            "plan_mf",
            "plan_ordre_1",
        ]
        # PNG pour l'écran, PDF vectoriel pour un rapport.
        assert figures == sorted(f"{n}.{ext}" for n in noms for ext in ("pdf", "png"))
        assert all((exemple / repere / "FIGURES" / f).stat().st_size > 10_000 for f in figures)
    assert "Glyph" not in capsys.readouterr().err


def test_sans_cfd_plot_le_reste_fonctionne(
    exemple: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from cfd_doe.report import figures

    def absent() -> None:
        raise figures.FiguresIndisponibles("figures indisponibles (cfd_plot manquant)")

    monkeypatch.setattr(figures, "_cfd_plot", absent)
    assert main(["remplir", "REMPLISSAGE_FUSEE.yaml"]) == 0
    assert "figures indisponibles" in capsys.readouterr().out
    assert (exemple / "DOE" / "doe.csv").is_file()
