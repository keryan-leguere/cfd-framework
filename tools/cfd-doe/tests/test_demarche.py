"""La démarche (``--verbose``) : elle raconte le découpage qui a tourné, et renvoie au tableau."""

from __future__ import annotations

from typing import Any

import pytest
from rich.console import Console

from cfd_doe.core.domaine_fondamental import (
    Coupe,
    Evenement,
    Feuille,
    Recollement,
    Strate,
    fusionner,
    stratifier_signes,
)
from cfd_doe.core.intervalle import Intervalle
from cfd_doe.core.symetrie import engendrer
from cfd_doe.data.etude import Etude, etude_depuis_dict
from cfd_doe.data.geometries import MIROIR_H, MIROIR_V, ROTATION_180
from cfd_doe.data.variables import VARIABLES_CARTESIENNES
from cfd_doe.engine.demarche import Etape, Noeud, numeroteur
from cfd_doe.engine.reduction import Reduction, reduire
from cfd_doe.report.console import demarche, rapport_reduction

PLEIN = {"alpha": [-20, 20], "beta": [-5, 5], "DL": [-20, 20], "DM": [-20, 20], "DN": [-20, 20]}


def _etude(traj: str = "6DOF", geo: Any = "cruciforme", **extra: Any) -> Etude:
    donnees: dict[str, Any] = {"trajectoire": traj, "geometrie": geo, "variables": dict(PLEIN)}
    donnees.update(extra)
    return etude_depuis_dict(donnees)


def _textes(noeuds: tuple[Noeud, ...]) -> list[str]:
    return [t for n in noeuds for t in (n.texte, *_textes(n.enfants))]


def _etape(reduction: Reduction, debut: str) -> Etape:
    (etape,) = [e for e in reduction.demarche if e.titre.startswith(debut)]
    return etape


#: Des études qui passent par toutes les branches du moteur.
CAS: list[dict[str, Any]] = [
    *(
        {"traj": t, "geo": g}
        for g in ("quelconque", "plan_vertical", "double_symetrie", "cruciforme")
        for t in ("2DOF", "3DOF_MASSE_PONCTUELLE", "3DOF_TANGAGE", "4DOF", "5DOF", "6DOF")
    ),
    *({"geo": {"type": "n_ailettes", "n_ailettes": n}} for n in (3, 5, 6)),
    {"traj": "3DOF_MASSE_PONCTUELLE", "geo": "revolution"},
    {"repere": "cartesien"},
    {"geo": "double_symetrie", "repere": "polaire"},
    {"geo": "plan_vertical", "repere": "polaire"},
    {"geo": "quelconque", "repere": "polaire"},
    {"limite_braquage": "carre"},
    {"geo": "double_symetrie", "repere": "polaire", "limite_braquage": "carre"},
    {"variables": {**PLEIN, "alpha": [0, 20], "beta": [2, 5], "DL": [-5, 10]}},
    {"geo": "plan_vertical", "variables": {**PLEIN, "DN": [0, 20]}},
    {
        "geo": {"type": "n_ailettes", "n_ailettes": 3},
        "variables": {**PLEIN, "alpha": [5, 20], "beta": [-5, 5]},
    },
]


@pytest.mark.parametrize("cas", CAS, ids=lambda c: "-".join(str(v) for v in c.values()))
def test_chaque_sous_domaine_est_atteint_par_le_recit(cas: dict[str, Any]) -> None:
    """Les feuilles numérotées couvrent exactement les lignes du tableau.

    Une feuille sans sous-domaine unique lèverait déjà dans ``reduire`` : le
    récit et le découpage ne peuvent pas diverger en silence.
    """
    cas = dict(cas)
    r = reduire(_etude(cas.pop("traj", "6DOF"), cas.pop("geo", "cruciforme"), **cas))
    numeros = {f.numero for e in r.demarche for f in e.feuilles()}
    assert numeros == set(range(1, len(r.sous_domaines) + 1))
    assert [e.titre for e in r.demarche] == [
        "Trajectoire → variables actives",
        "Choix du repère",
        "Groupe de symétries",
        "Découpage en domaine fondamental",
        "Recollement et numérotation",
    ]


class TestRecit:
    def test_variables_inactives_dites_nulles(self) -> None:
        r = reduire(_etude(traj="3DOF_TANGAGE", geo="double_symetrie"))
        textes = _textes(_etape(r, "Trajectoire").noeuds)
        assert "α active : pilote N (CN), α ∈ [−20 ; 20]°" in textes
        assert "β inactive : Y n'est pas consommé → β = 0" in textes

    def test_restriction_du_groupe_aux_variables_libres(self) -> None:
        """En vol plan, miroir H et rotation 180° agissent pareil sur (α, δm) : ordre 2."""
        r = reduire(_etude(traj="3DOF_TANGAGE", geo="double_symetrie"))
        textes = _textes(_etape(r, "Groupe").noeuds)
        assert any("ordre 2" in t and "se confondent" in t for t in textes)
        assert "miroir H (α, δm)" in textes

    def test_cruciforme_polaire_plans_et_axe(self) -> None:
        r = reduire(_etude())
        decoupage = _etape(r, "Découpage")
        couronnes, axe = decoupage.noeuds
        assert couronnes.texte.startswith("αt ∈ ]0 ; 20,59]°")
        assert [n.numero for n in couronnes.enfants] == [None, 1, None, None]
        plan_0 = couronnes.enfants[2]
        assert "δnB retourné par miroir du plan" in plan_0.texte
        assert [(n.texte.split(" :")[0], n.numero) for n in plan_0.enfants] == [
            ("δnB > 0", 2),
            ("δnB = 0", 3),
        ]
        assert axe.texte.startswith("αt = 0")
        assert [n.numero for n in axe.enfants] == [None, 6, 7, 8]

    def test_recollement_raconte(self) -> None:
        """Sans braquage, plan 0, secteur et plan 45 se recollent en φa ∈ [0 ; 45]."""
        r = reduire(_etude(traj="3DOF_MASSE_PONCTUELLE"))
        recollement = _textes(_etape(r, "Recollement").noeuds)
        assert any("recollés en φa ∈ [0 ; 45]" in t for t in recollement)
        couronnes = _etape(r, "Découpage").noeuds[0]
        assert [n.numero for n in couronnes.enfants if n.numero] == [1, 1, 1]

    def test_cartesien_force_dit_ce_qu_il_perd(self) -> None:
        r = reduire(_etude(repere="cartesien"))
        textes = _textes(_etape(r, "Groupe").noeuds)
        assert any(t.startswith("non exprimables en (α, β)") for t in textes)

    def test_plage_asymetrique_etendue(self) -> None:
        r = reduire(_etude(geo="plan_vertical", variables={**PLEIN, "DN": [0, 20]}))
        textes = _textes(_etape(r, "Groupe").noeuds)
        assert any(t.startswith("δn ∈ [0 ; 20] : asymétrique, étendu à [−20 ; 20]") for t in textes)

    def test_arc_partiel_et_plan_non_atteint(self) -> None:
        r = reduire(
            _etude(
                geo={"type": "n_ailettes", "n_ailettes": 3},
                variables={**PLEIN, "alpha": [0, 20], "beta": [2, 5]},
            )
        )
        textes = _textes(_etape(r, "Découpage").noeuds)
        assert any("atteint [5,83 ; 60]°" in t for t in textes)
        assert "φa = 0° : plan non atteint par l'arc, rien à calculer" in textes

    def test_sans_symetrie_une_seule_feuille(self) -> None:
        r = reduire(_etude(geo="quelconque"))
        (racine,) = _etape(r, "Découpage").noeuds
        assert racine.numero == 1
        assert "aucune symétrie n'agit" in racine.texte


class TestJournal:
    def test_le_journal_ne_change_pas_le_decoupage(self) -> None:
        bornes = {v: Intervalle(-10.0, 10.0) for v in VARIABLES_CARTESIENNES}
        groupe = engendrer((MIROIR_V, MIROIR_H, ROTATION_180))
        journal: list[Evenement] = []
        avec = stratifier_signes(bornes, groupe, VARIABLES_CARTESIENNES, journal=journal)
        assert avec == stratifier_signes(bornes, groupe, VARIABLES_CARTESIENNES)
        assert [e.strate for e in journal if isinstance(e, Feuille)] == avec
        racine = journal[0]
        assert isinstance(racine, Coupe)
        assert racine.chemin == ()
        assert racine.variable == "alpha"
        assert {e.nom for e in racine.retournent} == {"miroir H", "rotation 180°"}

    def test_journal_de_fusion(self) -> None:
        a = Strate({"x": Intervalle(0.0, 1.0, haut_inclus=False)}, nom="a")
        b = Strate({"x": Intervalle.point(1.0)}, nom="b")
        journal: list[Recollement] = []
        (union,) = fusionner([a, b], journal)
        (r,) = journal
        assert r.noms == ("a", "b")
        assert r.union == union.bornes["x"] == Intervalle(0.0, 1.0)

    def test_numeroteur_refuse_une_strate_orpheline(self) -> None:
        numero = numeroteur([Strate({"x": Intervalle(0.0, 1.0)})])
        assert numero(Strate({"x": Intervalle.point(0.5)})) == 1
        with pytest.raises(RuntimeError, match="0 sous-domaine"):
            numero(Strate({"x": Intervalle.point(2.0)}))


class TestRendu:
    @staticmethod
    def _rendu(objet: Any, largeur: int = 80) -> str:
        console = Console(width=largeur, record=True, color_system=None)
        console.print(objet)
        return console.export_text()

    def test_demarche_absente_par_defaut(self) -> None:
        r = reduire(_etude())
        assert "Démarche" not in self._rendu(rapport_reduction(r))
        assert "Démarche" in self._rendu(rapport_reduction(r, verbeux=True))

    def test_numeros_en_bout_de_ligne_et_dans_80_colonnes(self) -> None:
        texte = self._rendu(demarche(reduire(_etude())))
        assert "1. Trajectoire → variables actives" in texte
        assert "5. Recollement et numérotation" in texte
        for k in range(1, 9):
            assert f"→ #{k}" in texte
        assert max(len(ligne.rstrip()) for ligne in texte.splitlines()) <= 80
