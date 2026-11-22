"""Test d'interpolation de table et polaires, sans compilateur : un « code » Python interpole.

L'oracle est vérifié sur une fonction **multilinéaire** connue, que
l'interpolation multilinéaire reproduit exactement entre les nœuds. Les faux
codes commettent les fautes que le test doit nommer : un palier (plus proche
nœud bas), une somme d'interpolations 1D sans terme croisé, une sonde muette.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from conftest import glyphes_manquants_en_erreur
from rich.console import Console

from cfd_validation import (
    ErreurTable,
    Polaires,
    TableReference,
    tracer_polaires_tables,
    valider_interpolation_tables,
    verifier_interpolation,
)
from cfd_validation.core.bornes import interpoler
from cfd_validation.core.mailles import abscisses_polaire, points_mailles, verifier_fractions
from cfd_validation.engine.interpolation_tables import TOLERANCE_INTERPOLATION
from cfd_validation.engine.polaires import calculer_polaires
from cfd_validation.report.interpolation_tables import rendre_interpolation_tables

GX = np.array([0.0, 1.0, 3.0])
GY = np.array([-10.0, 0.0, 10.0, 20.0])


def f(x: Any, y: Any) -> Any:
    return 2.0 + 0.5 * x - 0.03 * y + 0.01 * x * y


V = f(GX[:, None], GY[None, :])
DEFAUTS = {"x": 1.0, "y": 0.0, "z": 0}


def table(**kw: Any) -> TableReference:
    return TableReference("T", V, {"x": GX, "y": GY}, sonde="s", **kw)


def code(faute: str | None = None) -> Callable[[pd.DataFrame], pd.DataFrame]:
    """Le code juste (la fonction exacte), ou fautif : palier, sans terme croisé, muet."""

    def evaluer(df: pd.DataFrame) -> pd.DataFrame:
        x, y = df["x"].to_numpy(), df["y"].to_numpy()
        if faute == "palier":  # nœud bas de la maille, le dernier nœud reste lui-même
            i = np.clip(np.searchsorted(GX, x, side="right") - 1, 0, len(GX) - 1)
            j = np.clip(np.searchsorted(GY, y, side="right") - 1, 0, len(GY) - 1)
            s = V[i, j]
        elif faute == "croise":  # somme d'interpolations 1D autour du coin bas
            i = np.clip(np.searchsorted(GX, x, side="right") - 1, 0, len(GX) - 2)
            j = np.clip(np.searchsorted(GY, y, side="right") - 1, 0, len(GY) - 2)
            t = (x - GX[i]) / (GX[i + 1] - GX[i])
            u = (y - GY[j]) / (GY[j + 1] - GY[j])
            s = V[i, j] + t * (V[i + 1, j] - V[i, j]) + u * (V[i, j + 1] - V[i, j])
        elif faute == "muet":
            s = np.full(len(df), np.nan)
        else:
            s = f(x, y)
        return df.assign(s=s)

    return evaluer


# --------------------------------------------------------------------------
# core
# --------------------------------------------------------------------------


def test_points_mailles() -> None:
    x, i, t = points_mailles(GX, (0.5, 0.25))
    assert x.tolist() == [0.25, 0.5, 1.5, 2.0] and i.tolist() == [0, 0, 1, 1] and t.tolist() == [0.25, 0.5] * 2
    for mauvaises in ((), (0.0,), (1.0, 0.5), (1.2,)):
        with pytest.raises(ValueError):
            verifier_fractions(mauvaises)


def test_abscisses_polaire() -> None:
    x = abscisses_polaire(GY, subdivisions=4, ecart_min=0.1, ecart_max=0.0, points_hors=3)
    assert set(GY) <= set(x) and x[0] == pytest.approx(-13.0) and x[-1] == 20.0
    assert len(x) == 4 + 3 * 3 + 3 and np.all(np.diff(x) > 0)


# --------------------------------------------------------------------------
# moteur
# --------------------------------------------------------------------------


def test_conforme_groupes_et_mailles() -> None:
    res = verifier_interpolation([table()], code(), DEFAUTS)
    b = res.tables[0]
    assert res.conforme and [g.groupe.nom for g in b.groupes] == ["x", "y", "centres"]
    assert [g.n_points for g in b.groupes] == [2 * 3 * 4, 3 * 3 * 3, 2 * 3]
    assert [g.n_mailles for g in b.groupes] == [2, 3, 6] and {g.observe for g in b.groupes} == {"linéaire"}
    r = b.resultats
    premier = r.iloc[0]  # ordre Fortran : x d'abord, maille 1-2, t = ¼
    assert (premier["groupe"], premier["maille"], premier["fraction"], premier["x"], premier["y"]) == \
        ("x", "1-2", 0.25, 0.25, -10.0)
    assert r.loc[r["groupe"] == "centres", "maille"].iloc[-1] == "2-3 3-4"
    np.testing.assert_allclose(r["valeur_ATTENDUE"], f(r["x"], r["y"]), rtol=1e-14)


def test_palier_nomme() -> None:
    res = verifier_interpolation([table()], code("palier"), DEFAUTS)
    obs = {g.groupe.nom: g.observe for g in res.tables[0].groupes}
    assert obs == {"x": "palier", "y": "palier", "centres": "palier"}
    assert res.motifs_non_conformite[0].startswith("T x : attendu linéaire, observé palier (24/24")


def test_terme_croise_seulement_aux_centres() -> None:
    """Le long d'un axe, l'autre sur un nœud bas, une somme 1D est juste ; au centre, non."""
    res = verifier_interpolation([table()], code("croise"), DEFAUTS)
    groupes = {g.groupe.nom: g for g in res.tables[0].groupes}
    assert groupes["centres"].observe == "ni l'un ni l'autre" and groupes["centres"].n_echecs == 6
    # Les groupes par axe ne voient la faute que sur le dernier nœud de l'autre axe (u = 1).
    assert set(groupes["x"].mailles_en_echec) == {"1-2", "2-3"}
    assert (res.tables[0].echecs().query("groupe == 'x'")["y"] == GY[-1]).all()


def test_sonde_non_atteinte_et_indiscernable() -> None:
    muet = verifier_interpolation([table()], code("muet"), DEFAUTS)
    assert {g.observe for g in muet.tables[0].groupes} == {"sonde non atteinte"}
    plate = TableReference("P", np.ones((3, 4)), {"x": GX, "y": GY}, sonde="s")
    res = verifier_interpolation([plate], lambda df: df.assign(s=1.0), DEFAUTS)
    assert res.conforme and {g.observe for g in res.tables[0].groupes} == {"indiscernable"}


def test_tolerances_fractions_centres() -> None:
    res = verifier_interpolation([table()], code(), DEFAUTS, fractions=[0.5], centres=False)
    b = res.tables[0]
    assert [g.groupe.nom for g in b.groupes] == ["x", "y"] and b.n_valeurs == 2 * 4 + 3 * 3
    assert b.groupes[0].tolerance == TOLERANCE_INTERPOLATION
    declaree = verifier_interpolation([table(rtol=1e-9, justification="j")], code(), DEFAUTS)
    assert declaree.tables[0].groupes[0].tolerance.justification == "j"
    with pytest.raises(ErreurTable, match="strictement entre 0 et 1"):
        verifier_interpolation([table()], code(), DEFAUTS, fractions=[0.0, 0.5])


def test_une_dimension_et_inversion() -> None:
    t1 = TableReference("U", GY * 2.0, {"r": GY}, sonde="s", fixes={"z": 1}, vers_entrees=lambda df: {"y": df["r"]})
    res = verifier_interpolation([t1], lambda df: df.assign(s=np.where(df["z"] == 1, 2.0 * df["y"], np.nan)),
                                 DEFAUTS)
    b = res.tables[0]
    assert res.conforme and [g.groupe.nom for g in b.groupes] == ["r"] and b.entrees_pilotees == ("y",)


# --------------------------------------------------------------------------
# 5D, rapport, façade
# --------------------------------------------------------------------------

G5 = [np.linspace(0.0, 1.0, 3) * (k + 1) for k in range(5)]
V5 = np.random.default_rng(3).normal(size=(3,) * 5)
AXES5 = dict(zip("abcde", G5))
DEFAUTS5 = {**{k: 0.0 for k in AXES5}, "z": 0}


def code_5d(df: pd.DataFrame) -> pd.DataFrame:
    return df.assign(s5=interpoler(V5, G5, df[list(AXES5)].to_numpy(), [("sature", "sature")] * 5))


def table_5d() -> TableReference:
    return TableReference("G5", V5, AXES5, sonde="s5", bornes={"a": ("inatteignable", "sature")})


def test_rapport_5d_en_80_colonnes() -> None:
    res = verifier_interpolation([table(), table_5d()], lambda df: code("palier")(code_5d(df)), {**DEFAUTS, **DEFAUTS5})
    assert res.tables[1].conforme and res.tables[1].groupes[-1].n_points == 2**5
    console = Console(width=80, record=True, color_system=None)
    rendre_interpolation_tables(console, res)
    texte = console.export_text()
    assert all(len(ligne) <= 80 for ligne in texte.splitlines())
    assert "x : attendu linéaire, observé palier" in texte and "NON CONFORME" in texte


def test_valider_ecrit_les_pieces(tmp_path: Path) -> None:
    res = valider_interpolation_tables([table_5d()], code_5d, DEFAUTS5, sortie=tmp_path, figures=False,
                                       afficher=False, metadonnees={"code": "factice"})
    assert res.conforme and res.n_appels == 5 * 2 * 3 * 3**4 + 2**5
    noms = sorted(str(p.relative_to(tmp_path)) for p in res.fichiers)
    assert noms == ["RESULTATS/G5.csv", "interpolation_tables.log", "resume.json"]
    relu = pd.read_csv(tmp_path / "RESULTATS" / "G5.csv")
    assert {"groupe", "maille", "fraction", "valeur_ATTENDUE", "valeur_CODE", "ecart", "conforme"} <= set(relu.columns)
    resume = json.loads((tmp_path / "resume.json").read_text())
    t = resume["tables"][0]  # les clés que lit le récapitulatif de VALIDATION/
    assert {"nom", "appels", "echecs", "conforme"} <= set(t) and resume["polaires"] == []
    journal = (tmp_path / "interpolation_tables.log").read_text()
    assert "5D 3×3×3×3×3" in journal and "factice" in journal and "centres" in journal
    assert all(ligne == ligne.rstrip() for ligne in journal.splitlines())


# --------------------------------------------------------------------------
# polaires
# --------------------------------------------------------------------------


def test_polaires_calculees() -> None:
    t = table(bornes={"x": ("inatteignable", "sature")})
    px, py = calculer_polaires([t], code(), DEFAUTS, ecart=0.1)
    assert (px.axe, px.conditions, px.superpose, px.n_courbes) == ("x", ("y",), "y", 4)
    assert px.prolongements == (0.0, 0.1) and px.code["x"].min() == 0.0  # rien sous un côté inatteignable
    assert py.prolongements == (0.1, 0.1) and py.code["y"].min() == pytest.approx(-13.0)
    np.testing.assert_allclose(py.code["valeur"], f(py.code["x"], py.code["y"]), rtol=1e-14)
    assert py.noeuds["valeur"].tolist() == V.ravel(order="C").tolist()  # x lent, y rapide : nœuds de chaque x


def test_polaires_restreintes_et_refusees() -> None:
    (p5,) = calculer_polaires([table_5d()], code_5d, DEFAUTS5,
                              {"G5": Polaires(abscisses=["b"], noeuds={"a": [0.0], "c": [0.0, 1.5], "d": [0.0]},
                                              superposer="e")})
    assert p5.n_courbes == 1 * 2 * 1 * 3 and p5.superpose == "e"
    with pytest.raises(ErreurTable, match="courbes"):
        calculer_polaires([table_5d()], code_5d, DEFAUTS5, courbes_max=100)
    for spec, motif in ((Polaires(abscisses=["q"]), "n'est pas un axe"), (Polaires(noeuds={"a": [0.3]}), "pas un nœud")):
        with pytest.raises(ErreurTable, match=motif):
            calculer_polaires([table_5d()], code_5d, DEFAUTS5, {"G5": spec})
    with pytest.raises(ErreurTable, match="pas une table testée"):
        calculer_polaires([table()], code(), DEFAUTS, {"Z": Polaires()})


def test_polaires_svg_batch_plot(tmp_path: Path) -> None:
    pytest.importorskip("cfd_plot")
    t1 = TableReference("U", GY * 2.0, {"y": GY}, sonde="s", bornes={"y": "sature"})
    with glyphes_manquants_en_erreur():
        fichiers = tracer_polaires_tables(
            [table(bornes={"x": "sature", "y": "extrapole"}), t1],
            code(), DEFAUTS, tmp_path,
            libelles={"y": (r"$\beta$", "°"), "T": "$C_X$"},
        )
    noms = sorted(str(p.relative_to(tmp_path)) for p in fichiers)
    assert "T/POLAIRE_X/Y_-10/T_vs_x.svg" in noms and "T/POLAIRE_Y/X_0/T_vs_y.svg" in noms
    assert "T/POLAIRE_Y/SUPERPOSITION/T_vs_y_by_X.svg" in noms and "U/POLAIRE_Y/U_vs_y.svg" in noms
    assert len(noms) == 4 + 3 + 2 + 1 and all(n.endswith(".svg") for n in noms)


def test_valider_avec_polaires(tmp_path: Path) -> None:
    pytest.importorskip("cfd_plot")
    with glyphes_manquants_en_erreur():
        res = valider_interpolation_tables([table()], code("palier"), DEFAUTS, sortie=tmp_path, afficher=False,
                                           superposer=False)
    assert not res.conforme
    polaires = [p for p in res.fichiers if "POLAIRES" in p.parts]
    assert len(polaires) == 4 + 3 and not any("SUPERPOSITION" in p.parts for p in polaires)
    resume = json.loads((tmp_path / "resume.json").read_text())
    assert [p["abscisse"] for p in resume["polaires"]] == ["x", "y"]
