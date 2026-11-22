"""Test des bornes de table, sans compilateur : un « code » Python sature ou extrapole.

L'oracle (``core/bornes.interpoler``) est vérifié sur une fonction
**multilinéaire** connue : l'interpolation bilinéaire la reproduit exactement
dans la grille, l'extrapolation linéaire aussi au-delà. Le faux code applique
ses propres règles de bord, codées ici indépendamment de l'oracle, pour qu'on
puisse lui faire commettre les fautes que le test doit nommer.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from conftest import glyphes_manquants_en_erreur
from rich.console import Console

from cfd_validation import ErreurTable, TableReference, valider_bornes_tables, verifier_bornes
from cfd_validation.core.bornes import interpoler, point_hors_bornes
from cfd_validation.report.bornes_tables import rendre_bornes_tables

GX = np.array([0.0, 1.0, 3.0])
GY = np.array([-10.0, 0.0, 10.0, 20.0])


def f(x: Any, y: Any) -> Any:
    """Multilinéaire : la bilinéaire la reproduit exactement, en dedans comme au-delà."""
    return 2.0 + 0.5 * x - 0.03 * y + 0.01 * x * y


V = f(GX[:, None], GY[None, :])
DEFAUTS = {"x": 1.0, "y": 0.0, "z": 0}


# --------------------------------------------------------------------------
# core
# --------------------------------------------------------------------------


def test_point_hors_bornes() -> None:
    assert point_hors_bornes(GY, "min", 0.1) == pytest.approx(-13.0)  # 10 % de l'étendue 30
    assert point_hors_bornes(GY, "max", 0.1) == pytest.approx(23.0)
    for args in ((GY, "milieu", 0.1), (GY, "min", 0.0), (np.array([1.0]), "max", 0.1)):
        with pytest.raises(ValueError):
            point_hors_bornes(*args)  # type: ignore[arg-type]


def test_oracle_multilineaire() -> None:
    pts = np.array([[0.5, 5.0], [3.6, 12.0], [-0.3, -13.0], [1.0, 23.0], [3.0, 20.0], [0.0, -10.0]])
    ext = interpoler(V, [GX, GY], pts, [("extrapole", "extrapole")] * 2)
    np.testing.assert_allclose(ext, f(pts[:, 0], pts[:, 1]), rtol=1e-14)
    sat = interpoler(V, [GX, GY], pts, [("sature", "sature")] * 2)
    np.testing.assert_allclose(sat, f(np.clip(pts[:, 0], 0, 3), np.clip(pts[:, 1], -10, 20)), rtol=1e-14)
    noeuds = interpoler(V, [GX, GY], pts[-2:], [("sature", "sature")] * 2)
    assert noeuds.tolist() == [V[2, 3], V[0, 0]]  # bit pour bit sur un nœud, bords compris


def test_oracle_regle_par_cote() -> None:
    pts = np.array([[1.0, -13.0], [1.0, 23.0]])
    v = interpoler(V, [GX, GY], pts, [("sature", "sature"), ("sature", "extrapole")])
    np.testing.assert_allclose(v, [f(1.0, -10.0), f(1.0, 23.0)], rtol=1e-14)


# --------------------------------------------------------------------------
# un faux code, indépendant de l'oracle
# --------------------------------------------------------------------------


def _maille(g: np.ndarray, x: float, regle: str) -> tuple[int, float]:
    i = min(max(int(np.searchsorted(g, x, side="right")) - 1, 0), len(g) - 2)
    t = (x - g[i]) / (g[i + 1] - g[i])
    if regle == "sature":
        t = min(max(t, 0.0), 1.0)
    return i, t


def code(regles: Mapping[str, str], *, valeurs: np.ndarray = V, sonde: str = "s",
         decale: Callable[[pd.DataFrame], np.ndarray] | None = None) -> Callable[[pd.DataFrame], pd.DataFrame]:
    """Bilinéaire avec, par axe, ``sature`` ou ``extrapole`` des deux côtés."""
    def evaluer(df: pd.DataFrame) -> pd.DataFrame:
        lu = []
        for x, y in zip(df["x"], df["y"]):
            i, t = _maille(GX, x, regles["x"])
            j, u = _maille(GY, y, regles["y"])
            lu.append((1 - t) * (1 - u) * valeurs[i, j] + t * (1 - u) * valeurs[i + 1, j]
                      + (1 - t) * u * valeurs[i, j + 1] + t * u * valeurs[i + 1, j + 1])
        out = np.array(lu)
        if decale is not None:
            out = out + decale(df)
        return df.assign(**{sonde: out})
    return evaluer


def table(**options: Any) -> TableReference:
    return TableReference("T", options.pop("valeurs", V), {"x": GX, "y": GY}, sonde="s", **options)


SAT_EXT = {"x": "sature", "y": "extrapole"}


# --------------------------------------------------------------------------
# data : la déclaration des consignes
# --------------------------------------------------------------------------


def test_bornes_declarees() -> None:
    t = table(bornes={"x": "sature", "y": ("inatteignable", "extrapole")})
    assert t.bornes == {"x": ("sature", "sature"), "y": ("inatteignable", "extrapole")}


@pytest.mark.parametrize(("bornes", "motif"), [
    ({"q": "sature"}, "q n'est pas un axe"),
    ({"x": "borne"}, "attendu une consigne"),
    ({"x": ("sature",)}, "attendu une consigne"),
])
def test_bornes_refusees(bornes: dict[str, Any], motif: str) -> None:
    with pytest.raises(ErreurTable, match=motif):
        table(bornes=bornes)


# --------------------------------------------------------------------------
# engine
# --------------------------------------------------------------------------


def test_conforme_et_faces() -> None:
    res = verifier_bornes([table(bornes=SAT_EXT)], code(SAT_EXT), DEFAUTS)
    b = res.tables[0]
    assert res.conforme
    assert [f.face.nom for f in b.faces] == ["x−", "x+", "y−", "y+"]
    assert [f.n_points for f in b.faces] == [4, 4, 3, 3]  # une face = tous les nœuds des autres axes
    assert [f.observe for f in b.faces] == ["sature", "sature", "extrapole", "extrapole"]
    assert [f.face.valeur for f in b.faces] == pytest.approx([-0.3, 3.3, -13.0, 23.0])
    y_moins = b.resultats[b.resultats["face"] == "y−"]
    assert y_moins["x"].tolist() == GX.tolist() and (y_moins["y"] == -13.0).all()
    assert (y_moins["z"] == 0).all()  # défauts injectés
    np.testing.assert_allclose(y_moins["valeur_ATTENDUE"], f(GX, -13.0), rtol=1e-14)


def test_consigne_non_respectee_nommee() -> None:
    """Le code sature en y alors qu'on lui demande d'extrapoler : échec, et l'observé le dit."""
    res = verifier_bornes([table(bornes=SAT_EXT)], code({"x": "sature", "y": "sature"}), DEFAUTS)
    b = res.tables[0]
    faces = {f.face.nom: f for f in b.faces}
    assert not res.conforme and faces["x−"].conforme
    # La pente de f en y vaut −0.03 + 0.01·x : nulle en x = 3, où saturer et extrapoler
    # coïncident. Ce point-là passe, à juste titre ; les deux autres échouent.
    assert not faces["y+"].conforme and faces["y+"].observe == "sature" and faces["y+"].n_echecs == 2
    assert "T y+ : attendu extrapole, observé sature (2/3 hors tolérance)" in res.motifs_non_conformite


def test_ni_l_un_ni_l_autre_et_nan() -> None:
    faux = code(SAT_EXT, decale=lambda df: np.where(df["x"] > 3, 0.5, 0.0))
    faces = {f.face.nom: f for f in verifier_bornes([table(bornes=SAT_EXT)], faux, DEFAUTS).tables[0].faces}
    assert faces["x+"].observe == "ni l'un ni l'autre" and faces["x−"].observe == "sature"
    nan = verifier_bornes([table(bornes=SAT_EXT)], lambda df: df.assign(s=np.nan), DEFAUTS).tables[0]
    assert {f.observe for f in nan.faces} == {"sonde non atteinte"} and nan.n_echecs == 14


def test_indiscernable() -> None:
    """Dernière maille plate en x : saturer ou extrapoler donnent la même valeur."""
    plat = V.copy()
    plat[2, :] = plat[1, :]
    res = verifier_bornes([table(valeurs=plat, bornes=SAT_EXT)], code(SAT_EXT, valeurs=plat), DEFAUTS)
    faces = {f.face.nom: f for f in res.tables[0].faces}
    assert res.conforme and faces["x+"].observe == "indiscernable" and faces["x−"].observe == "sature"


def test_inatteignable_non_teste() -> None:
    res = verifier_bornes([table(bornes={"x": ("inatteignable", "sature"), "y": "extrapole"})],
                          code(SAT_EXT), DEFAUTS)
    b = res.tables[0]
    assert [f.nom for f in b.non_testees] == ["x−"] and "x−" not in [f.face.nom for f in b.faces]
    with pytest.raises(ErreurTable, match="toutes les faces sont inatteignables"):
        verifier_bornes([table(bornes={"x": "inatteignable", "y": "inatteignable"})], code(SAT_EXT), DEFAUTS)


def test_consigne_par_defaut_et_ecarts() -> None:
    res = verifier_bornes([table(bornes={"y": "extrapole"})], code(SAT_EXT), DEFAUTS, ecart=0.2, ecarts={"y": 0.5})
    faces = {f.face.nom: f.face for f in res.tables[0].faces}
    assert faces["x−"].consigne == "sature" and faces["x−"].origine == "defaut"
    assert faces["y+"].origine == "declaree"
    assert faces["x+"].valeur == pytest.approx(3.6) and faces["y+"].valeur == pytest.approx(35.0)
    with pytest.raises(ErreurTable, match="consigne par défaut"):
        verifier_bornes([table()], code(SAT_EXT), DEFAUTS, consigne_defaut="borne")
    with pytest.raises(ErreurTable, match="écart"):
        verifier_bornes([table()], code(SAT_EXT), DEFAUTS, ecart=0.0)


def test_tolerances() -> None:
    """Saturé : bit pour bit ; extrapolé : quelques ULP admis ; déclarée : celle de la table."""
    bruit = code(SAT_EXT, decale=lambda df: np.full(len(df), 1e-14))
    faces = {f.face.nom: f for f in verifier_bornes([table(bornes=SAT_EXT)], bruit, DEFAUTS).tables[0].faces}
    assert not faces["x−"].conforme and faces["x−"].tolerance.exacte
    assert faces["y+"].conforme and faces["y+"].tolerance.rtol == 1e-12
    declaree = verifier_bornes([table(bornes=SAT_EXT, atol=1e-13, justification="j")], bruit, DEFAUTS)
    assert declaree.conforme and {f.tolerance.justification for f in declaree.tables[0].faces} == {"j"}


def test_fixes_et_inversion() -> None:
    """Colonnes (r, x) : y = r reconstruit par vers_entrees ; z fixé à 1 pour que la table soit lue."""
    t = TableReference("R", V, {"x": GX, "r": GY}, sonde="s", fixes={"z": 1},
                       vers_entrees=lambda df: {"y": df["r"]}, bornes={"x": "sature", "r": "extrapole"})
    lu_si_z = code(SAT_EXT, decale=lambda df: np.where(df["z"] == 1, 0.0, np.nan))
    res = verifier_bornes([t], lu_si_z, DEFAUTS)
    assert res.conforme and res.tables[0].entrees_pilotees == ("x", "y")
    with pytest.raises(ErreurTable, match="r n'est pas une entrée"):
        verifier_bornes([TableReference("R", V, {"x": GX, "r": GY}, sonde="s")], lu_si_z, DEFAUTS)


# --------------------------------------------------------------------------
# façade, rapport, figure — dont une table 5D
# --------------------------------------------------------------------------

G5 = [np.linspace(0.0, 1.0, 4) * (k + 1) for k in range(5)]
V5 = np.random.default_rng(5).normal(size=(4,) * 5)
AXES5 = dict(zip("abcde", G5))
REGLES5 = [("sature", "sature"), ("extrapole", "extrapole"), ("sature", "sature"), ("sature", "sature"),
           ("sature", "sature")]


def code_5d(faute: bool = False) -> Callable[[pd.DataFrame], pd.DataFrame]:
    """Code 5D (l'oracle lui-même, ce n'est pas lui qu'on teste ici) ; faute : b saturé au lieu d'extrapolé."""
    regles = [("sature", "sature")] * 5 if faute else REGLES5
    return lambda df: df.assign(s5=interpoler(V5, G5, df[list(AXES5)].to_numpy(), regles))


def table_5d() -> TableReference:
    return TableReference("G5", V5, AXES5, sonde="s5", bornes={"b": "extrapole", "a": ("inatteignable", "sature")})


DEFAUTS5 = {**{k: 0.0 for k in AXES5}, "z": 0}


def test_valider_ecrit_les_pieces(tmp_path: Path) -> None:
    res = valider_bornes_tables([table_5d()], code_5d(), DEFAUTS5, sortie=tmp_path, figures=False, afficher=False,
                                metadonnees={"code": "factice"})
    assert res.conforme and res.n_appels == 9 * 4**4
    noms = sorted(str(p.relative_to(tmp_path)) for p in res.fichiers)
    assert noms == ["RESULTATS/G5.csv", "bornes_tables.log", "resume.json"]
    relu = pd.read_csv(tmp_path / "RESULTATS" / "G5.csv")
    assert {"face", "consigne", "valeur_ATTENDUE", "valeur_SATURATION", "valeur_EXTRAPOLATION", "valeur_CODE",
            "ecart", "conforme"} <= set(relu.columns)
    resume = json.loads((tmp_path / "resume.json").read_text())
    t = resume["tables"][0]  # les clés que lit le récapitulatif de VALIDATION/
    assert {"nom", "appels", "echecs", "conforme"} <= set(t) and t["non_testees"][0]["face"] == "a−"
    journal = (tmp_path / "bornes_tables.log").read_text()
    assert "5D 4×4×4×4×4" in journal and "factice" in journal and "inatteignable" in journal
    assert all(ligne == ligne.rstrip() for ligne in journal.splitlines())


def test_rapport_5d_en_80_colonnes() -> None:
    res = verifier_bornes([table(bornes=SAT_EXT), table_5d()], lambda df: code(SAT_EXT)(code_5d(True)(df)),
                          {**DEFAUTS, **DEFAUTS5})
    console = Console(width=80, record=True, color_system=None)
    rendre_bornes_tables(console, res)
    texte = console.export_text()
    assert all(len(ligne) <= 80 for ligne in texte.splitlines())
    assert "b− : attendu extrapole, observé sature" in texte and "NON CONFORME" in texte
    assert "Non testées (inatteignables) : G5 a−" in texte


def test_figure_svg(tmp_path: Path) -> None:
    pytest.importorskip("cfd_plot")
    with glyphes_manquants_en_erreur():
        res = valider_bornes_tables([table(bornes=SAT_EXT), table_5d()],
                                    lambda df: code({"x": "sature", "y": "sature"})(code_5d(True)(df)),
                                    {**DEFAUTS, **DEFAUTS5}, sortie=tmp_path, afficher=False)
    assert not res.conforme
    figures = [p.name for p in res.fichiers if p.parent.name == "FIGURES"]
    assert figures == ["synthese_bornes.svg"]
