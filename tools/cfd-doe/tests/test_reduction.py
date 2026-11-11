"""Réduction de bout en bout : choix du repère, décomptes du document, orbites."""

from __future__ import annotations

import itertools
import math
from typing import Any, ClassVar

import pytest

from cfd_doe.core.angles import normaliser_angle, vers_alphat_phia
from cfd_doe.core.domaine_fondamental import Secteur
from cfd_doe.core.symetrie import engendrer, restreindre
from cfd_doe.data.etude import ErreurEtude, Etude, etude_depuis_dict
from cfd_doe.data.variables import VARIABLES
from cfd_doe.engine.reduction import Reduction, SousDomaine, reduire, vers_dict

PLEIN = {"alpha": [-20, 20], "beta": [-5, 5], "DL": [-20, 20], "DM": [-20, 20], "DN": [-20, 20]}


def _etude(traj: str = "6DOF", geo: Any = "cruciforme", **extra: Any) -> Etude:
    donnees: dict[str, Any] = {"trajectoire": traj, "geometrie": geo, "variables": dict(PLEIN)}
    variables = extra.pop("variables", None)
    if variables is not None:
        donnees["variables"] = variables
    donnees.update(extra)
    return etude_depuis_dict(donnees)


def _compte(reduction: Reduction, grille: dict[str, list[float]]) -> int:
    """Nœuds d'une grille contenus dans un sous-domaine (le disque des braquages ignoré).

    Le document compte sur la grille 5 × 5 en (δmB, δnB), coins compris
    (§7.4, §7.6) : on garde les secteurs, pas le disque.
    """
    noms = list(grille)
    total = 0
    for valeurs in itertools.product(*grille.values()):
        point = dict(zip(noms, valeurs))
        for sd in reduction.sous_domaines:
            secteurs = [c for c in sd.contraintes if isinstance(c, Secteur)]
            if all(sd.bornes[v].contient(point[v]) for v in noms) and all(
                c.contient(point) for c in secteurs
            ):
                total += 1
    return total


class TestRepere:
    def test_cruciforme_6dof_passe_en_polaire(self) -> None:
        r = reduire(_etude())
        assert r.repere == "polaire"
        assert r.ordre_groupe == 8

    def test_plan_vertical_reste_cartesien(self) -> None:
        assert reduire(_etude(geo="plan_vertical")).repere == "cartesien"

    def test_vol_plan_reste_cartesien_meme_cruciforme(self) -> None:
        assert reduire(_etude(traj="3DOF_TANGAGE")).repere == "cartesien"

    def test_cartesien_force_signale_les_symetries_perdues(self) -> None:
        r = reduire(_etude(repere="cartesien"))
        assert r.repere == "cartesien"
        assert any("rotation de 90°" in a for a in r.avertissements)

    def test_polaire_impossible_en_vol_plan(self) -> None:
        with pytest.raises(ErreurEtude, match="polaire impossible"):
            reduire(_etude(traj="2DOF", repere="polaire"))

    def test_revolution_ne_garde_que_alphat(self) -> None:
        r = reduire(_etude(traj="3DOF_MASSE_PONCTUELLE", geo="revolution"))
        (sd,) = r.sous_domaines
        assert sd.bornes["phia"].est_point
        assert sd.bornes["alphat"].haut == pytest.approx(20.59, abs=0.01)

    def test_revolution_refuse_les_braquages(self) -> None:
        with pytest.raises(ErreurEtude, match="révolution"):
            reduire(_etude(geo="revolution"))


class TestDomaineActif:
    def test_variables_inactives_fixees_a_zero_avec_avertissement(self) -> None:
        r = reduire(_etude(traj="3DOF_TANGAGE"))
        assert r.domaine_entree["beta"].est_nul
        assert any("beta" in a and "inactive" in a for a in r.avertissements)

    def test_plage_manquante_pour_une_active(self) -> None:
        with pytest.raises(ErreurEtude, match="plage manquante pour DN"):
            reduire(_etude(variables={k: v for k, v in PLEIN.items() if k != "DN"}))

    def test_plage_asymetrique_etendue(self) -> None:
        r = reduire(_etude(geo="plan_vertical", variables={**PLEIN, "beta": [-2, 5]}))
        assert any("étendue" in a for a in r.avertissements)
        assert r.sous_domaines[0].bornes["beta"].haut == 5.0


class TestDecomptesDuDocument:
    """Les décomptes des §5.3, §5.4 et §7.4, retrouvés sur les sous-domaines."""

    COURONNES: ClassVar[list[float]] = [float(a) for a in range(0, 23, 2)]

    @pytest.mark.parametrize(
        ("geo", "attendu"),
        [("quelconque", 265), ("plan_vertical", 144), ("double_symetrie", 78), ("cruciforme", 45)],
    )
    def test_section_5_3_sans_braquage(self, geo: str, attendu: int) -> None:
        r = reduire(
            _etude(
                traj="3DOF_MASSE_PONCTUELLE",
                geo=geo,
                repere="polaire",
                variables={"alpha": [-22, 22], "beta": [-1, 1]},
            )
        )
        grille = {"alphat": self.COURONNES, "phia": [float(p) for p in range(0, 360, 15)]}
        # Au point αt = 0, φa est fixé à 0 : il ne compte qu'une fois.
        assert _compte(r, grille) == attendu

    def test_section_5_4_cartesien_plan_vertical(self) -> None:
        r = reduire(_etude(traj="3DOF_MASSE_PONCTUELLE", geo="plan_vertical"))
        grille = {"alpha": [float(a) for a in range(-20, 21, 2)], "beta": [-5, -2.5, 0, 2.5, 5]}
        assert _compte(r, grille) == 63

    def test_section_5_4_cartesien_double_symetrie(self) -> None:
        r = reduire(_etude(traj="3DOF_MASSE_PONCTUELLE", geo="double_symetrie"))
        grille = {"alpha": [float(a) for a in range(-20, 21, 2)], "beta": [-5, -2.5, 0, 2.5, 5]}
        assert _compte(r, grille) == 33

    def test_section_7_4_factoriel_complet_cruciforme(self) -> None:
        r = reduire(_etude(variables={**PLEIN, "alpha": [-22, 22], "beta": [-1, 1]}))
        braquages = [-20.0, -10.0, 0.0, 10.0, 20.0]
        grille = {
            "alphat": self.COURONNES,
            "phia": [0.0, 15.0, 30.0, 45.0],
            "DMB": braquages,
            "DNB": braquages,
            "DL": braquages,
        }
        assert _compte(r, grille) == 2750 + 1430 + 20


# ---------------------------------------------------------------------------
# Orbites, de bout en bout
# ---------------------------------------------------------------------------


def _action_polaire(n: int) -> list[Any]:
    """Les 2N éléments de D_N agissant sur un point (αt, φa, δmB, δnB, δl)."""

    def rotation(k: int) -> Any:
        def agir(p: dict[str, float]) -> dict[str, float]:
            if p["alphat"] == 0.0:
                t = math.radians(k * 360.0 / n)
                c, s = math.cos(t), math.sin(t)
                return {**p, "DMB": c * p["DMB"] - s * p["DNB"], "DNB": s * p["DMB"] + c * p["DNB"]}
            return {**p, "phia": normaliser_angle(p["phia"] + k * 360.0 / n)}

        return agir

    def miroir(k: int) -> Any:
        phis = k * 180.0 / n

        def agir(p: dict[str, float]) -> dict[str, float]:
            if p["alphat"] == 0.0:
                t = math.radians(2 * phis)
                c, s = math.cos(t), math.sin(t)
                return {
                    **p,
                    "DMB": c * p["DMB"] + s * p["DNB"],
                    "DNB": s * p["DMB"] - c * p["DNB"],
                    "DL": -p["DL"],
                }
            return {
                **p,
                "phia": normaliser_angle(2 * phis - p["phia"]),
                "DNB": -p["DNB"],
                "DL": -p["DL"],
            }

        return agir

    return [rotation(k) for k in range(n)] + [miroir(k) for k in range(n)]


def _dans(sous_domaines: tuple[SousDomaine, ...], point: dict[str, float]) -> bool:
    return any(sd.contient(point, tol=1e-7) for sd in sous_domaines)


@pytest.mark.parametrize("n", [1, 2, 3, 4, 6])
def test_polaire_un_representant_par_orbite(n: int) -> None:
    geo = {"type": "n_ailettes", "n_ailettes": n}
    r = reduire(_etude(geo=geo, repere="polaire"))
    actions = _action_polaire(n)
    grille = range(-20, 21, 10)
    for alphat in (0.0, 4.0, 20.0):
        phis = [0.0] if alphat == 0.0 else [7.5 * k for k in range(48)]
        for phia, dm, dn, dl in itertools.product(phis, grille, grille, grille):
            if math.hypot(dm, dn) > 20.0:
                continue  # hors de la limite en disque
            point = {"alphat": alphat, "phia": phia, "DMB": dm, "DNB": dn, "DL": dl}
            images = {
                tuple(round(x, 6) + 0.0 for x in (q["phia"], q["DMB"], q["DNB"], q["DL"])): q
                for q in (a(point) for a in actions)
            }
            n_rep = sum(_dans(r.sous_domaines, q) for q in images.values())
            assert n_rep == 1, (n, point, n_rep)


@pytest.mark.parametrize("geo", ["quelconque", "plan_vertical", "double_symetrie", "cruciforme"])
@pytest.mark.parametrize("traj", ["2DOF", "3DOF_TANGAGE", "4DOF", "5DOF", "6DOF"])
def test_cartesien_un_representant_par_orbite(geo: str, traj: str) -> None:
    variables = {v: [-2, 2] for v in VARIABLES}
    r = reduire(_etude(traj=traj, geo=geo, repere="cartesien", variables=variables))
    groupe = restreindre(
        engendrer(r.etude.geometrie.generateurs_cartesiens()), r.etude.trajectoire.actives
    )
    actives = r.etude.trajectoire.actives
    for valeurs in itertools.product(range(-2, 3), repeat=len(actives)):
        point = {v: 0.0 for v in VARIABLES}
        point.update(zip(actives, map(float, valeurs)))
        images = {tuple(g.agit(point).values()): g.agit(point) for g in groupe}
        assert sum(_dans(r.sous_domaines, q) for q in images.values()) == 1, point


def test_polaire_couvre_un_rectangle_hors_origine() -> None:
    """α ∈ [5, 20] : pas d'axe αt = 0, et tout point du rectangle a son représentant."""
    r = reduire(
        _etude(
            traj="3DOF_MASSE_PONCTUELLE",
            repere="polaire",
            variables={"alpha": [5, 20], "beta": [-3, 8]},
        )
    )
    assert all(sd.nom != "axe" for sd in r.sous_domaines)
    actions = _action_polaire(4)
    for a, b in itertools.product(range(5, 21), range(-3, 9)):
        alphat, phia = vers_alphat_phia(a, b)
        point = {"alphat": alphat, "phia": phia, "DMB": 0.0, "DNB": 0.0, "DL": 0.0}
        images = {round(q["phia"], 6): q for q in (f(point) for f in actions)}
        assert sum(_dans(r.sous_domaines, q) for q in images.values()) == 1, (a, b)


def test_export_serialisable() -> None:
    import json

    donnees = vers_dict(reduire(_etude()))
    texte = json.dumps(donnees)
    assert donnees["repere"] == "polaire"
    assert len(donnees["sous_domaines"]) == 8
    assert "disque" in texte and "secteur" in texte
