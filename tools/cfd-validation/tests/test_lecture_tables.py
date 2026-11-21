"""Test de lecture de table, sans compilateur : un « code » Python lit des tables numpy.

L'évaluateur factice fait ce que fait un code instrumenté : il retrouve le nœud
le plus proche de chaque point dans la table qu'il *croit* lire, et rend la
valeur comme sonde. On lui fait commettre les fautes que le test doit voir —
valeur fausse, sonde non atteinte, lecture qui dépend d'une entrée qu'elle ne
devrait pas regarder.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from conftest import glyphes_manquants_en_erreur
from rich.console import Console

from cfd_validation import ErreurTable, TableReference, relire_tables, valider_lecture_tables
from cfd_validation.core.noeuds import (
    coordonnees_noeuds,
    decrire_forme,
    verifier_forme,
    verifier_grille,
)
from cfd_validation.report.lecture_tables import rendre_lecture_tables

GX = np.array([0.0, 1.0, 2.0])
GY = np.array([10.0, 20.0])
V2 = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])  # V2[i, j] = table(GX[i], GY[j])
DEFAUTS = {"x": 0.0, "y": 10.0, "z": 0, "w": 0.5}


def _indice(grille: np.ndarray, x: np.ndarray) -> np.ndarray:
    return np.abs(grille[None, :] - np.asarray(x, dtype=float)[:, None]).argmin(axis=1)


def code_2d(valeurs: np.ndarray = V2, *, sonde: str = "s", decale: Callable[[pd.DataFrame], np.ndarray] | None = None,
            ) -> Callable[[pd.DataFrame], pd.DataFrame]:
    """Un code qui lit ``valeurs`` au nœud le plus proche de (x, y)."""
    def evaluer(df: pd.DataFrame) -> pd.DataFrame:
        lu = valeurs[_indice(GX, df["x"]), _indice(GY, df["y"])]
        if decale is not None:
            lu = lu + decale(df)
        return df.assign(**{sonde: lu})
    return evaluer


def table_2d(**options: Any) -> TableReference:
    return TableReference("T", V2, {"x": GX, "y": GY}, sonde="s", **options)


def relire(tables: list[TableReference], evaluer: Any, **options: Any) -> Any:
    return relire_tables(tables, evaluer, options.pop("defauts", DEFAUTS), **options)


# --------------------------------------------------------------------------
# core : forme, ordre de lecture
# --------------------------------------------------------------------------


def test_ordre_de_lecture_fortran() -> None:
    indices, coords = coordonnees_noeuds([GX, GY])
    assert indices.tolist() == [[0, 0], [1, 0], [2, 0], [0, 1], [1, 1], [2, 1]]  # premier indice le plus rapide
    assert coords[:, 0].tolist() == [0, 1, 2, 0, 1, 2]
    assert V2.ravel(order="F").tolist() == [V2[i, j] for i, j in indices]


def test_forme_et_permutation_suggeree() -> None:
    verifier_forme("T", (3, 2), {"x": 3, "y": 2})
    with pytest.raises(ValueError, match=r"essayer \(y, x\)"):
        verifier_forme("T", (2, 3), {"x": 3, "y": 2})
    with pytest.raises(ValueError, match="3 dimensions contre 2 axes"):
        verifier_forme("T", (3, 2, 1), {"x": 3, "y": 2})
    with pytest.raises(ValueError, match="aucun ordre"):
        verifier_forme("T", (4, 2), {"x": 3, "y": 2})
    assert decrire_forme((5, 5, 5, 5, 5)) == "5D 5×5×5×5×5"


@pytest.mark.parametrize("grille", [np.array([0.0, 0.0, 1.0]), np.array([1.0, 0.0]), np.array([]), np.array([0.0, np.nan])])
def test_grille_refusee(grille: np.ndarray) -> None:
    with pytest.raises(ValueError):
        verifier_grille("g", grille)


# --------------------------------------------------------------------------
# data : déclaration
# --------------------------------------------------------------------------


def test_table_declaree() -> None:
    v = V2.copy()
    t = TableReference("T", v, {"x": GX, "y": GY}, sonde="s")
    v[0, 0] = 99.0
    assert t.valeurs[0, 0] == 1.0  # copie : la table déclarée ne bouge plus
    assert t.forme == (3, 2) and t.n_noeuds == 6 and t.decrire_forme == "2D 3×2"
    assert t.tolerance.exacte and t.tolerance.origine == "defaut" and t.tolerance.justification
    plate = t.table_plate()
    assert list(plate.columns) == ["x", "y", "valeur"] and plate["valeur"].tolist() == [1, 3, 5, 2, 4, 6]
    assert table_2d(rtol=1e-9, justification="j").tolerance.rtol == 1e-9


@pytest.mark.parametrize(("args", "motif"), [
    ({"valeurs": V2.T}, "essayer"),
    ({"axes": {}}, "aucun axe"),
    ({"sonde": ""}, "sonde"),
    ({"nom": " "}, "sans nom"),
    ({"rtol": -1.0}, "rtol"),
    ({"axes": {"x": GX[::-1], "y": GY}}, "croissante"),
])
def test_declaration_refusee(args: dict[str, Any], motif: str) -> None:
    base: dict[str, Any] = {"nom": "T", "valeurs": V2, "axes": {"x": GX, "y": GY}, "sonde": "s"}
    with pytest.raises(ErreurTable, match=motif):
        TableReference(**{**base, **args})


# --------------------------------------------------------------------------
# engine
# --------------------------------------------------------------------------


def test_lecture_exacte() -> None:
    res = relire([table_2d()], code_2d())
    b = res.tables[0]
    assert res.conforme and res.bit_identique and b.n_valeurs == 6 and b.n_identiques == 6
    assert b.resultats["valeur_TAB"].tolist() == [1, 3, 5, 2, 4, 6]
    assert set(b.resultats.columns) >= {"noeud", "combinaison", "x", "y", "z", "w", "valeur_TAB", "valeur_CODE",
                                        "ecart", "ulp", "marge", "statut", "conforme"}
    assert (b.resultats["z"] == 0).all() and (b.resultats["w"] == 0.5).all()  # défauts injectés


def test_valeur_fausse_nommee() -> None:
    faux = V2.copy()
    faux[2, 1] += 1e-3  # le code lit une autre valeur au nœud (x=2, y=20) : rang 5
    res = relire([table_2d()], code_2d(faux))
    b = res.tables[0]
    assert not res.conforme and b.n_echecs == 1
    ligne = b.echecs().iloc[0]
    assert (ligne["noeud"], ligne["x"], ligne["y"]) == (5, 2.0, 20.0)
    assert ligne["ecart"] == pytest.approx(1e-3) and ligne["statut"] == "ECART"
    assert "T : 1 valeur(s) sur 6" in res.motifs_non_conformite[0]


def test_tolerance_declaree() -> None:
    bruit = code_2d(decale=lambda df: np.full(len(df), 1e-14))
    assert not relire([table_2d()], bruit).conforme
    res = relire([table_2d(atol=1e-13, justification="arrondi")], bruit)
    assert res.conforme and not res.bit_identique and res.tables[0].n_toleres == 6


def test_sonde_non_atteinte() -> None:
    res = relire([table_2d()], lambda df: df.assign(s=np.nan))
    b = res.tables[0]
    assert b.n_echecs == 6 and b.n_non_finis == 6 and "NaN" in res.motifs_non_conformite[0]


def test_fixes() -> None:
    """Une table lue seulement pour z = 1 (propulsion allumée) : sans fixes, sonde NaN."""
    lu_si_z = code_2d(decale=lambda df: np.where(df["z"] == 1, 0.0, np.nan))
    assert relire([table_2d()], lu_si_z).tables[0].n_non_finis == 6
    res = relire([table_2d(fixes={"z": 1})], lu_si_z)
    assert res.conforme and (res.tables[0].resultats["z"] == 1).all()


def test_inversion() -> None:
    """Axes (r, t) qui ne sont pas des entrées : le code calcule r, t depuis (x, y)."""
    gr, gt = np.array([1.0, 2.0, 3.0]), np.array([0.0, 30.0, 60.0, 90.0])
    v = np.arange(12.0).reshape(3, 4) / 7.0

    def code(df: pd.DataFrame) -> pd.DataFrame:
        r = np.hypot(df["x"], df["y"])
        t = np.degrees(np.arctan2(df["y"], df["x"]))
        return df.assign(s=v[_indice(gr, r), _indice(gt, t)])

    def vers_entrees(df: pd.DataFrame) -> Mapping[str, Any]:
        t = np.radians(df["t"])
        return {"x": df["r"] * np.cos(t), "y": df["r"] * np.sin(t)}

    t = TableReference("P", v, {"r": gr, "t": gt}, sonde="s", vers_entrees=vers_entrees)
    res = relire([t], code)
    assert res.conforme and res.tables[0].entrees_pilotees == ("x", "y")
    with pytest.raises(ErreurTable, match=r"r, t n.est pas une entrée du modèle .* vers_entrees"):
        relire([TableReference("P", v, {"r": gr, "t": gt}, sonde="s")], code)


def test_simple_inversion_constante() -> None:
    """La variante (mach, alphat) → alpha = alphat, beta = 0 : un scalaire est diffusé."""
    t = TableReference("A", V2, {"at": GX, "y": GY}, sonde="s", vers_entrees=lambda df: {"x": df["at"], "w": 0.0})
    res = relire([t], code_2d())
    assert res.conforme and (res.tables[0].resultats["w"] == 0.0).all()


def test_combinaisons_revelent_une_dependance() -> None:
    """La lecture ne doit pas dépendre de w ; ce code-ci en dépend pour w = 1."""
    code = code_2d(decale=lambda df: np.where(df["w"] == 1.0, 1e-6, 0.0))
    assert relire([table_2d()], code).conforme  # aux défauts, rien ne se voit
    res = relire([table_2d()], code, combinaisons={"w": [0.5, 1.0], "z": [0, 1], "x": [0.0, 9.0]})
    b = res.tables[0]
    assert len(b.combinaisons) == 4  # le produit (w, z) complet, (0.5, 0) = les défauts en tête
    assert b.combinaisons[0] == {"w": 0.5, "z": 0} and not b.defauts_hors_produit
    assert b.combinaisons_ignorees == ("x",)  # pilotée par la table
    assert not b.conforme and set(b.echecs_par_combinaison().index) == {2, 3}
    assert b.decrire_combinaison(0) == "défauts (w=0.5, z=0)" and "w=1" in b.decrire_combinaison(2)
    deps = b.dependances()
    assert list(deps) == ["w"]  # z est combinée aussi, mais sans effet : pas citée
    assert deps["w"] == {0.5: (0, 12), 1.0: (12, 12)}


def test_lecture_fausse_sans_dependance() -> None:
    """Une valeur fausse échoue à toutes les combinaisons : aucune entrée n'est accusée.

    w = 0.5 par défaut n'est pas dans les valeurs combinées : la combinaison 0 est
    hors du produit et ne doit pas faire croire que w compte.
    """
    faux = V2.copy()
    faux[0, 0] += 1.0
    res = relire([table_2d()], code_2d(faux), combinaisons={"w": [0.0, 1.0], "z": [0, 1]})
    b = res.tables[0]
    assert b.defauts_hors_produit and len(b.combinaisons) == 5  # défauts + produit 2 × 2
    assert b.n_echecs == len(b.combinaisons) and b.dependances() == {}
    console = Console(width=80, record=True, color_system=None)
    rendre_lecture_tables(console, res)
    assert "lecture fausse, pas dépendance" in console.export_text()


@pytest.mark.parametrize(("table", "options", "motif"), [
    (table_2d(fixes={"q": 1}), {}, "fixes inconnues"),
    (table_2d(fixes={"x": 1.0}), {}, "fixée et pilotée"),
    (TableReference("T", V2, {"x": GX, "y": GY}, sonde="s", vers_entrees=lambda df: {"q": 1.0}), {}, "q, pas des entrées"),
    (table_2d(), {"combinaisons": {"q": [1]}}, "combinaisons : q"),
    (table_2d(), {"combinaisons": {"z": []}}, "aucune valeur"),
    (table_2d(), {"defauts": {}}, "défauts vide"),
])
def test_plan_refuse(table: TableReference, options: dict[str, Any], motif: str) -> None:
    with pytest.raises(ErreurTable, match=motif):
        relire([table], code_2d(), **options)


def test_evaluateur_refuse() -> None:
    with pytest.raises(ErreurTable, match="sonde « s » absente"):
        relire([table_2d()], lambda df: df)
    with pytest.raises(ErreurTable, match="lignes pour"):
        relire([table_2d()], lambda df: df.iloc[:2].assign(s=0.0))
    with pytest.raises(ErreurTable, match="deux tables"):
        relire([table_2d(), TableReference("t", V2, {"x": GX, "y": GY}, sonde="s")], code_2d())


# --------------------------------------------------------------------------
# façade, rapport, figures — y compris une table 5D
# --------------------------------------------------------------------------

G5 = [np.linspace(0.0, 1.0, 4) * (k + 1) for k in range(5)]
V5 = np.random.default_rng(3).normal(size=(4, 4, 4, 4, 4))
AXES5 = dict(zip(("a", "b", "c", "d", "e"), G5))


def code_5d(valeurs: np.ndarray = V5) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def evaluer(df: pd.DataFrame) -> pd.DataFrame:
        i = tuple(_indice(g, df[n]) for n, g in AXES5.items())
        return df.assign(s5=valeurs[i])
    return evaluer


def code_mixte(faux5: bool = False) -> Callable[[pd.DataFrame], pd.DataFrame]:
    v5 = V5.copy()
    if faux5:
        v5[1, 2, 3, 0, 2] += 0.5
    return lambda df: code_5d(v5)(code_2d()(df))


DEFAUTS_MIXTES = {**DEFAUTS, "a": 0.0, "b": 0.0, "c": 0.0, "d": 0.0, "e": 0.0}


def test_valider_ecrit_les_pieces(tmp_path: Path) -> None:
    tables = [table_2d(), TableReference("G5", V5, AXES5, sonde="s5")]
    res = valider_lecture_tables(tables, code_mixte(), DEFAUTS_MIXTES, sortie=tmp_path, figures=False,
                                 afficher=False, metadonnees={"code": "factice"})
    assert res.conforme and res.n_appels == 6 + 4**5
    noms = sorted(str(p.relative_to(tmp_path)) for p in res.fichiers)
    assert noms == ["RESULTATS/G5.csv", "RESULTATS/T.csv", "TABLES/G5.csv", "TABLES/T.csv",
                    "lecture_tables.log", "resume.json"]
    relu = pd.read_csv(tmp_path / "RESULTATS" / "G5.csv")
    assert np.array_equal(relu["valeur_CODE"].to_numpy(), V5.ravel(order="F"))  # 17 chiffres : relu exact
    resume = json.loads((tmp_path / "resume.json").read_text())
    assert resume["conforme"] and resume["tables"][1]["forme"] == [4, 4, 4, 4, 4]
    journal = (tmp_path / "lecture_tables.log").read_text()
    assert "5D 4×4×4×4×4" in journal and "TABLES/T.csv" in journal and "factice" in journal
    assert all(ligne == ligne.rstrip() for ligne in journal.splitlines())


def test_rapport_5d_en_80_colonnes() -> None:
    """Points en échec d'une table 5D : coordonnées dans une colonne, rien ne déborde de 80."""
    res = relire_tables([table_2d(), TableReference("G5", V5, AXES5, sonde="s5")], code_mixte(faux5=True),
                        DEFAUTS_MIXTES, combinaisons={"w": [0.5, 1.0]})
    console = Console(width=80, record=True, color_system=None)
    rendre_lecture_tables(console, res)
    texte = console.export_text()
    assert all(len(ligne) <= 80 for ligne in texte.splitlines())
    assert "a=0.333" in texte and "NON CONFORME" in texte  # le nœud fautif, nommé par ses 5 coordonnées
    assert "Échecs par combinaison" not in texte or "défauts" in texte


def test_figures(tmp_path: Path) -> None:
    pytest.importorskip("cfd_plot")
    tables = [table_2d(), TableReference("G5", V5, AXES5, sonde="s5"),
              TableReference("NAN", V2, {"x": GX, "y": GY}, sonde="absente")]
    evaluer = lambda df: code_mixte(faux5=True)(df).assign(absente=np.nan)  # noqa: E731
    with glyphes_manquants_en_erreur():
        res = valider_lecture_tables(tables, evaluer, DEFAUTS_MIXTES, sortie=tmp_path, formats=("png",),
                                     afficher=False, combinaisons={"w": [0.5, 1.0]})
    assert not res.conforme
    assert [p.name for p in res.fichiers if p.suffix == ".png"] == ["synthese_tables.png"]


def test_figures_paginees(tmp_path: Path) -> None:
    pytest.importorskip("cfd_plot")
    tables = [TableReference(f"T{k}", V2 + k, {"x": GX, "y": GY}, sonde=f"s{k}") for k in range(7)]

    def evaluer(df: pd.DataFrame) -> pd.DataFrame:
        lu = V2[_indice(GX, df["x"]), _indice(GY, df["y"])]
        return df.assign(**{f"s{k}": lu + k for k in range(7)})

    with glyphes_manquants_en_erreur():
        res = valider_lecture_tables(tables, evaluer, DEFAUTS, sortie=tmp_path, formats=("png",), afficher=False)
    assert sorted(p.name for p in res.fichiers if p.suffix == ".png") == ["synthese_tables_01.png", "synthese_tables_02.png"]


def test_nan_dans_le_json(tmp_path: Path) -> None:
    res = valider_lecture_tables([table_2d()], lambda df: df.assign(s=np.nan), DEFAUTS, sortie=tmp_path,
                                 figures=False, afficher=False)
    t = json.loads((tmp_path / "resume.json").read_text())["tables"][0]
    assert t["non_finis"] == 6 and t["max_ulp"] is None and t["marge_max"] == "inf"
    assert not res.conforme and math.isinf(res.tables[0].marge_max)


def test_figures_svg_par_defaut(tmp_path: Path) -> None:
    """SVG seul par défaut ; une lecture invariante ne trace qu'une croix par nœud."""
    pytest.importorskip("cfd_plot")
    with glyphes_manquants_en_erreur():
        res = valider_lecture_tables([table_2d()], code_2d(), DEFAUTS, sortie=tmp_path, afficher=False,
                                     combinaisons={"w": [0.0, 1.0], "z": [0, 1]})
    figures = [p for p in res.fichiers if p.parent.name == "FIGURES"]
    assert [p.name for p in figures] == ["synthese_tables.svg"]
    texte = figures[0].read_text()
    assert texte.lstrip().startswith("<?xml") and "<image" not in texte  # petit nuage : tout vectoriel
