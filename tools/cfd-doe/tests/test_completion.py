"""Le script 01_EXEMPLE/completer_table.py : compléter une table de résultats par symétrie.

L'oracle est le modèle factice de ``exemple_completion.py``, symétrique par
construction : une ligne déduite doit valoir le modèle au même nœud.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml

from cfd_doe.data.etude import etude_depuis_dict
from cfd_doe.engine.reduction import reduire, vers_dict
from cfd_doe.paths import EXEMPLE_DIR

sys.path.insert(0, str(EXEMPLE_DIR))
import completer_table as ct
import exemple_completion as ex

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture(scope="module")
def plans(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    dossier = tmp_path_factory.mktemp("plans")
    return {r: ex.exporter_plan(r, dossier / f"SD_{r}.yaml") for r in ("polaire", "cartesien")}


def _completer(repere: str, df: pd.DataFrame, plan: Path, **options: Any) -> Any:
    return ct.completer_table(
        df,
        plan,
        cles=["MACH"],
        colonnes=ex.COLONNES[repere],
        coefficients=ex.COEFFICIENTS[repere],
        rapport=False,
        **options,
    )


def _ecarts(complet: pd.DataFrame, repere: str) -> pd.DataFrame:
    roles = list(ex.COEFFICIENTS[repere].values())
    connu = complet.dropna(subset=roles)
    return (connu[roles] - ex.MODELES[repere](connu)[roles]).abs().assign(origine=connu["origine"])


# ---------------------------------------------------------------------------
# Polaire : secteur φa ∈ [0 ; 45°], plans, axe αt = 0
# ---------------------------------------------------------------------------


class TestPolaire:
    @pytest.fixture(scope="class")
    def resultat(self, plans: dict[str, Path]) -> tuple[pd.DataFrame, pd.DataFrame, Any]:
        df, _ = ex.table_factice("polaire", plans["polaire"])
        complet, bilan = _completer("polaire", df, plans["polaire"], retour_bilan=True)
        return df, complet, bilan

    def test_table_carree(self, resultat: Any) -> None:
        """Une ligne par nœud de la grille produit, ni plus ni moins, pour chaque Mach."""
        _, complet, bilan = resultat
        variables = list(ex.COLONNES["polaire"].values())
        attendu = math.prod(len(v) for v in bilan.grille.values())
        assert attendu == 5 * 4 * 5 * 5 * 3
        assert len(complet) == len(ex.MACHS) * attendu
        assert not complet.duplicated(["MACH", *variables]).any()
        assert sorted(complet["PHIA"].unique()) == [0.0, 15.0, 30.0, 45.0]

    def test_lignes_calculees_reprises_telles_quelles(self, resultat: Any) -> None:
        df, complet, _ = resultat
        calcul = complet[complet["origine"] == "calcul"].drop(columns="origine")
        cle = ["MACH", *ex.COLONNES["polaire"].values()]
        fusion = df.merge(calcul, on=cle, suffixes=("", "_c"))
        assert len(fusion) == len(df)
        for col in [*ex.COEFFICIENTS["polaire"].values(), "RESIDU"]:
            assert (fusion[col] == fusion[f"{col}_c"]).all()

    def test_lignes_deduites_exactes(self, resultat: Any) -> None:
        """Symétrie et changement de repère à αt = 0 : à la précision machine."""
        _, complet, _ = resultat
        ecarts = _ecarts(complet, "polaire")
        exactes = ecarts[~ecarts["origine"].str.contains("interpolé")]
        assert exactes["origine"].str.startswith("symétrie").sum() > 0
        assert exactes["origine"].str.startswith("αt = 0, repère").sum() > 0
        assert exactes.drop(columns="origine").to_numpy().max() < 1e-12

    def test_interpolation_exacte_sur_ce_qui_est_lineaire(self, resultat: Any) -> None:
        """Bilinéaire et triangles reproduisent exactement un champ linéaire en braquages.

        Seul CA est quadratique dans le modèle : son écart est celui de l'interpolation.
        """
        _, complet, _ = resultat
        ecarts = _ecarts(complet, "polaire")
        interpolees = ecarts[ecarts["origine"] == "αt = 0, interpolé"]
        assert len(interpolees) > 0
        lineaires = ["CNB", "CYB", "ClB", "CmB", "CnB"]
        assert interpolees[lineaires].to_numpy().max() < 1e-12
        assert 0 < interpolees["CAB"].max() < 0.03

    def test_trous_hors_disque_et_bord_de_l_axe_seulement(self, resultat: Any) -> None:
        _, complet, bilan = resultat
        trous = complet[complet["origine"].str.startswith("trou")]
        assert set(trous["origine"]) == {"trou : hors disque", "trou : αt = 0, maille incomplète"}
        hors = trous[trous["origine"] == "trou : hors disque"]
        assert (hors["DMB"] ** 2 + hors["DNB"] ** 2 > 20.0**2).all()
        assert (trous[trous["origine"].str.contains("maille")]["ALPHAT"] == 0).all()
        assert trous[list(ex.COEFFICIENTS["polaire"].values())].isna().all().all()
        dans_disque = complet[complet["DMB"] ** 2 + complet["DNB"] ** 2 <= 400.0]
        assert not dans_disque[dans_disque["ALPHAT"] > 0]["CNB"].isna().any()
        assert bilan.origines["trou : sans image calculée"] == 0

    def test_coherence_nulle_sur_un_modele_symetrique(self, resultat: Any) -> None:
        _, _, bilan = resultat
        assert bilan.coherence
        assert max(e for _, e in bilan.coherence.values()) < 1e-12

    def test_sans_interpolation_l_axe_garde_ses_trous(self, plans: dict[str, Path]) -> None:
        df, _ = ex.table_factice("polaire", plans["polaire"])
        complet = _completer("polaire", df, plans["polaire"], interpoler_axe=False)
        assert "αt = 0, interpolé" not in set(complet["origine"])
        assert (complet["origine"] == "trou : αt = 0, non interpolé").sum() > 0

    def test_omettre_les_trous(self, plans: dict[str, Path]) -> None:
        df, _ = ex.table_factice("polaire", plans["polaire"])
        complet = _completer("polaire", df, plans["polaire"], trous="omettre")
        assert not complet["origine"].str.startswith("trou").any()
        assert not complet["CNB"].isna().any()

    def test_idempotente(self, resultat: Any, plans: dict[str, Path]) -> None:
        """Compléter une table déjà complète n'ajoute rien et ne change rien."""
        _, complet, _ = resultat
        roles = list(ex.COEFFICIENTS["polaire"].values())
        deja = complet.dropna(subset=roles).drop(columns="origine")
        encore = _completer("polaire", deja, plans["polaire"], trous="omettre")
        assert len(encore) == len(deja)
        assert (encore["origine"] == "calcul").all()

    def test_point_manquant_signale(self, plans: dict[str, Path]) -> None:
        """Une ligne du plan absente de la table : son orbite n'a plus de représentant."""
        df, _ = ex.table_factice("polaire", plans["polaire"])
        sur_le_plan = (df["PHIA"] == 0) & (df["ALPHAT"] == 10) & (df["DNB"] == 10)
        complet, bilan = _completer(
            "polaire", df.drop(index=df.index[sur_le_plan][:1]), plans["polaire"], retour_bilan=True
        )
        assert bilan.origines["trou : sans image calculée"] == 2  # le point et son miroir
        assert (complet["origine"] == "trou : sans image calculée").sum() == 2


# ---------------------------------------------------------------------------
# Cartésien : α ≥ 0, β ≥ 0
# ---------------------------------------------------------------------------


class TestCartesien:
    def test_complete_et_exacte(self, plans: dict[str, Path]) -> None:
        df, _ = ex.table_factice("cartesien", plans["cartesien"])
        complet = _completer("cartesien", df, plans["cartesien"])
        assert len(complet) == len(ex.MACHS) * 3 * 3 * 5 * 5 * 3
        assert not complet["origine"].str.startswith("trou").any()
        assert _ecarts(complet, "cartesien").drop(columns="origine").to_numpy().max() < 1e-12
        assert {"symétrie : miroir V", "symétrie : miroir H"} <= set(complet["origine"])

    def test_domaine_impose_beta_positif(self, plans: dict[str, Path]) -> None:
        """Un lecteur qui n'exploite que β ≥ 0 veut α complet : le miroir H le donne."""
        df, _ = ex.table_factice("cartesien", plans["cartesien"])
        complet = _completer("cartesien", df, plans["cartesien"], domaine={"alpha": (-20.0, 20.0)})
        assert sorted(complet["ALPHA"].unique()) == [-20.0, -10.0, 0.0, 10.0, 20.0]
        assert (complet["BETA"] >= 0).all()
        assert not complet["origine"].str.startswith("trou").any()
        assert _ecarts(complet, "cartesien").drop(columns="origine").to_numpy().max() < 1e-12

    def test_convention_de_signe_fausse_detectee(self, plans: dict[str, Path]) -> None:
        """CY pair en β (signe oublié) : le contrôle le voit sur les points fixes du miroir V."""
        df, _ = ex.table_factice("cartesien", plans["cartesien"])
        df["CY"] = df["CY"] + 0.01
        _, bilan = _completer("cartesien", df, plans["cartesien"], retour_bilan=True)
        assert bilan.coherence["CY"][1] == pytest.approx(0.02)
        assert bilan.coherence["CN"][1] < 1e-12


# ---------------------------------------------------------------------------
# Entrées, refus, rapport, ligne de commande
# ---------------------------------------------------------------------------


def test_variables_fixees_peuvent_manquer(tmp_path: Path) -> None:
    """Sans braquage, δmB, δnB et δl sont nuls partout : le DataFrame peut s'en passer."""
    etude = etude_depuis_dict(
        {
            "trajectoire": "3DOF_MASSE_PONCTUELLE",
            "geometrie": "cruciforme",
            "variables": {"alpha": [-20, 20], "beta": [-5, 5]},
        }
    )
    plan = vers_dict(reduire(etude))
    df = pd.DataFrame(
        [
            {"alphat": at, "phia": phi, "CA": 0.3, "CN": 0.1 * at, "CY": 0.0}
            for at in (5.0, 10.0)
            for phi in (0.0, 15.0, 30.0, 45.0)
        ]
    )
    complet = ct.completer_table(df, plan, rapport=False)
    assert list(complet.columns) == ["alphat", "phia", "CA", "CN", "CY", "origine"]
    assert (complet["origine"] == "calcul").all()


@pytest.mark.parametrize(
    ("modifier", "motif"),
    [
        (lambda df, plan: (df.drop(columns="DNB"), plan), "DNB"),
        (lambda df, plan: (df.drop(columns="CYB"), plan), "CN sans CY"),
        (lambda df, plan: (df, {k: v for k, v in plan.items() if k != "symetries"}), "symetries"),
    ],
)
def test_refus_explicites(plans: dict[str, Path], modifier: Any, motif: str) -> None:
    df, _ = ex.table_factice("polaire", plans["polaire"])
    donnees = yaml.safe_load(plans["polaire"].read_text(encoding="utf-8"))
    df, donnees = modifier(df, donnees)
    with pytest.raises(ValueError, match=motif):
        ct.completer_table(
            df,
            donnees,
            colonnes=ex.COLONNES["polaire"],
            coefficients=ex.COEFFICIENTS["polaire"],
            rapport=False,
        )


def test_domaine_sur_une_variable_inconnue(plans: dict[str, Path]) -> None:
    df, _ = ex.table_factice("cartesien", plans["cartesien"])
    with pytest.raises(ValueError, match="phia"):
        _completer("cartesien", df, plans["cartesien"], domaine={"phia": (0, 90)})


def test_rapport_lisible_en_80_colonnes(plans: dict[str, Path]) -> None:
    from rich.console import Console

    df, _ = ex.table_factice("polaire", plans["polaire"])
    console = Console(width=80, record=True, color_system=None)
    ct.completer_table(
        df,
        plans["polaire"],
        cles=["MACH"],
        colonnes=ex.COLONNES["polaire"],
        coefficients=ex.COEFFICIENTS["polaire"],
        console=console,
    )
    texte = console.export_text()
    for attendu in ("Grille cible", "Lignes de la table complète", "Contrôle des symétries"):
        assert attendu in texte
    assert "3\u202f000 lignes" in texte
    assert max(len(ligne.rstrip()) for ligne in texte.splitlines()) <= 80


def test_ligne_de_commande(plans: dict[str, Path], tmp_path: Path) -> None:
    df, _ = ex.table_factice("cartesien", plans["cartesien"])
    df = df.rename(columns={"ALPHA": "alpha", "BETA": "beta"})
    entree, sortie = tmp_path / "res.csv", tmp_path / "complet.csv"
    df.rename(columns={"DM": "DM", "DN": "DN"}).to_csv(entree, index=False)
    assert ct.main([str(plans["cartesien"]), str(entree), "-o", str(sortie), "--cles", "MACH"]) == 0
    complet = pd.read_csv(sortie)
    assert len(complet) == len(ex.MACHS) * 3 * 3 * 5 * 5 * 3


def test_exemple_s_execute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert ex.main(["--csv", str(tmp_path / "SORTIE")]) == 0
    assert (tmp_path / "SORTIE" / "TABLE_COMPLETE_POLAIRE.csv").is_file()
    assert ex.main(["--cartesien", "--beta-positif"]) == 0


def test_export_porte_le_groupe() -> None:
    etude = etude_depuis_dict(
        {
            "trajectoire": "6DOF",
            "geometrie": "double_symetrie",
            "variables": {
                "alpha": [-20, 20],
                "beta": [-5, 5],
                "DL": [-5, 5],
                "DM": [-5, 5],
                "DN": [-5, 5],
            },
        }
    )
    symetries = {s["nom"]: s for s in vers_dict(reduire(etude))["symetries"]}
    assert symetries["miroir V"]["coefficients"] == ["CY", "Cl", "Cn"]
    assert symetries["miroir H"]["coefficients"] == ["CN", "Cl", "Cm"]
    assert symetries["rotation 180°"]["coefficients"] == ["CN", "CY", "Cm", "Cn"]


def test_ligne_de_commande_noms_et_erreur(
    plans: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    df, _ = ex.table_factice("polaire", plans["polaire"])
    entree, sortie = tmp_path / "res.csv", tmp_path / "complet.csv"
    df.to_csv(entree, index=False)
    assert ct.main([str(plans["polaire"]), str(entree)]) == 1
    assert "ALPHAT" not in capsys.readouterr().out.split("erreur")[0]
    noms = [f"{v}={c}" for v, c in {**ex.COLONNES["polaire"], **ex.COEFFICIENTS["polaire"]}.items()]
    code = ct.main(
        [str(plans["polaire"]), str(entree), "-o", str(sortie), "--cles", "MACH", "--noms", *noms]
    )
    assert code == 0
    assert len(pd.read_csv(sortie)) == 3000
