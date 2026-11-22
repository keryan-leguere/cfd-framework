"""Le modèle aéro d'exemple (01_EXEMPLE/MODELE_AERO) et son encapsulation f2py.

Deux parties :

- la lecture des docstrings f2py (``Signature``), sans compilateur ;
- le modèle compilé dans un dossier temporaire (deux fois : -O0 et
  -O3 -ffast-math), appelé par ``ModeleAero`` — sauté sans gfortran, meson
  ou ninja. Ces tests vérifient aussi le Fortran lui-même : nœuds des tables
  au bit près, symétrie, transport des moments, propulsion, codes IERR.

La suite n'écrit jamais dans le paquet.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd
import pytest

from cfd_validation.paths import EXEMPLE_DIR

PROJET = EXEMPLE_DIR / "MODELE_AERO"
PYTHON = PROJET / "PYTHON"
BIN = str(Path(sys.executable).parent)
OUTILLAGE = all(
    shutil.which(o, path=os.pathsep.join([BIN, os.environ.get("PATH", "")])) for o in ("gfortran", "meson", "ninja")
)
avec_compilateur = pytest.mark.skipif(not OUTILLAGE, reason="gfortran, meson ou ninja absent")


def _charger(nom: str) -> ModuleType:
    """Les scripts de PYTHON/ s'importent entre eux par leur nom : même chose ici."""
    if nom in sys.modules:
        return sys.modules[nom]
    spec = importlib.util.spec_from_file_location(nom, PYTHON / f"{nom}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


mf = _charger("modele_f2py")
ma = _charger("modele_aero")


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------


def test_tables_a_jour() -> None:
    """aero_tables.f correspond à OUTILS/generer_tables.py."""
    res = subprocess.run(
        [sys.executable, str(PROJET / "OUTILS" / "generer_tables.py"), "--verifier"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr


def test_sources_format_fixe_et_ascii() -> None:
    """Colonne 72 tenue (au-delà, tronqué sans erreur) et ASCII pur (f2py refuse le reste)."""
    fichiers = [*PROJET.glob("SOURCES/*.f"), *PROJET.glob("SOURCES/*.inc")]
    assert len(fichiers) == 5
    for f in fichiers:
        texte = f.read_bytes()
        assert all(o < 128 for o in texte), f.name
        for i, ligne in enumerate(texte.decode().splitlines(), start=1):
            assert len(ligne) <= 72 or ligne[:1] in "Cc*!", f"{f.name}:{i}"


def test_une_directive_f2py_apres_chaque_entry() -> None:
    lignes = (PROJET / "SOURCES" / "aero_modele.f").read_text().splitlines()
    entrees = [i for i, ligne in enumerate(lignes) if ligne.lstrip().upper().startswith("ENTRY ")]
    assert len(entrees) == 2
    for i in entrees:
        suite = [ligne for ligne in lignes[i + 1 : i + 5] if ligne.upper().startswith("CF2PY")]
        assert any("INTENT(IN)" in s.upper() for s in suite), lignes[i]
        assert any("INTENT(OUT)" in s.upper() for s in suite), lignes[i]


# --------------------------------------------------------------------------
# Lecture des docstrings f2py (sans compilateur)
# --------------------------------------------------------------------------

DOC_AERCAL = """cx,cy,ierr = aercal(mach,alpha,ipropu)

Wrapper for ``aercal``.

Parameters
----------
mach : input float
alpha : input float
ipropu : input int

Returns
-------
cx : float
cy : float
ierr : int
"""

DOC_OPTIONNEL = """coef,ierr = phase(x,tab,[n,mode])

Wrapper for ``phase``.

Parameters
----------
x : input float
tab : input rank-1 array('d') with bounds (n)

Other Parameters
----------------
n : input int, optional
    Default: shape(tab, 0)
mode : input int, optional

Returns
-------
coef : rank-1 array('d') with bounds (6)
ierr : int
"""


def test_signature_scalaire() -> None:
    s = mf.Signature.depuis_doc(DOC_AERCAL)
    assert s.nom == "aercal"
    assert s.noms_entrees == ("mach", "alpha", "ipropu")
    assert s.noms_sorties == ("cx", "cy", "ierr")
    assert [a.reel for a in s.entrees] == [True, True, False]
    assert [a.entier for a in s.entrees] == [False, False, True]
    assert s.sorties[-1].entier
    assert str(s) == "cx, cy, ierr = aercal(mach, alpha, ipropu)"


def test_signature_optionnels_et_tableaux() -> None:
    s = mf.Signature.depuis_doc(DOC_OPTIONNEL)
    assert s.noms_entrees == ("x", "tab", "n", "mode")
    assert [a.optionnel for a in s.entrees] == [False, False, True, True]
    assert s.entrees[1].tableau and not s.entrees[1].reel
    assert s.entrees[2].entier
    assert s.sorties[0].tableau


def test_signature_sans_sortie() -> None:
    s = mf.Signature.depuis_doc("aero()\n\nWrapper for ``aero``.\n")
    assert s.noms_entrees == () and s.noms_sorties == ()


@pytest.mark.parametrize("doc", [None, "", "pas une signature"])
def test_signature_illisible(doc: str | None) -> None:
    with pytest.raises(mf.ErreurModele):
        mf.Signature.depuis_doc(doc, "x")


# --------------------------------------------------------------------------
# Modèle compilé
# --------------------------------------------------------------------------

POINT: dict[str, Any] = {"mach": 0.9, "alpha": 8.0, "beta": 3.0, "xg": 1.05, "yg": 0.004, "zg": -0.012,
                         "ipropu": 1, "dm": 5.0, "dn": 0.0}
NOMS = ("cx", "cy", "cz", "cl", "cm", "cn")
SONDES = tuple(f"valid_tab_{n}" for n in ("cx", "cz", "cm", "cy", "cl", "cn", "dcxp", "dcmg"))


def _construire(dossier: Path, nom: str, fflags: str) -> None:
    res = subprocess.run(
        ["bash", str(PYTHON / "construire.sh"), nom, str(dossier)], capture_output=True, text=True,
        env={**os.environ, "FFLAGS": fflags, "CFD_VALIDATION_PYTHON": sys.executable},
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "ierr = aerini(xref,yref,zref,lref)" in res.stdout
    assert "cx,cy,cz,cl,cm,cn,ierr = aercal(mach,alpha,beta,xg,yg,zg,ipropu,dm,dn)" in res.stdout


@pytest.fixture(scope="module")
def bibliotheques(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Deux compilations ; l'appel brut avant toute init est fait ici, une seule fois."""
    if not OUTILLAGE:
        pytest.skip("gfortran, meson ou ninja absent")
    dossier = tmp_path_factory.mktemp("f2py")
    _construire(dossier, "aerolib_t0", "-O0")
    _construire(dossier, "aerolib_t3", "-O3 -ffast-math")
    t0 = mf.importer_bibliotheque("aerolib_t0", dossier)
    t3 = mf.importer_bibliotheque("aerolib_t3", dossier)
    avant_init = t0.aercal(**POINT)
    return {"dossier": dossier, "t0": t0, "t3": t3, "avant_init": avant_init}


@pytest.fixture
def modele(bibliotheques: dict[str, Any]) -> Any:
    return ma.ModeleAero(bibliotheques["t0"])


@avec_compilateur
def test_aercal_avant_aerini(bibliotheques: dict[str, Any]) -> None:
    *coefs, ierr = bibliotheques["avant_init"]
    assert ierr == ma.IERR_NON_INITIALISE
    assert coefs == [0.0] * 6


@avec_compilateur
def test_noms_lus_dans_la_docstring(modele: Any) -> None:
    assert modele.arguments_init == ("xref", "yref", "zref", "lref")
    assert modele.arguments_calcul == ("mach", "alpha", "beta", "xg", "yg", "zg", "ipropu", "dm", "dn")
    assert tuple(modele.sondes) == SONDES
    assert modele.colonnes_entree == modele.arguments_init + modele.arguments_calcul
    assert modele.signature_calcul.noms_sorties == (*NOMS, "ierr")
    assert (modele.xref, modele.lref) == (1.2, 0.2)
    assert "aercal(mach, alpha" in modele.decrire()


@avec_compilateur
def test_constantes_et_refus(bibliotheques: dict[str, Any]) -> None:
    m = ma.ModeleAero(bibliotheques["t0"], lref=0.25)
    assert m.lref == 0.25 and m.xref == 1.2
    with pytest.raises(mf.ErreurModele, match="mach"):
        ma.ModeleAero(bibliotheques["t0"], mach=0.8)  # pas un argument d'init
    with pytest.raises(mf.ErreurModele, match="ierr = 12"):
        ma.ModeleAero(bibliotheques["t0"], lref=0.0)
    with pytest.raises(mf.ErreurModele, match="inconnu"):
        m.calculer(inconnu=1.0)


@avec_compilateur
def test_noeuds_au_bit_pres(modele: Any, bibliotheques: dict[str, Any]) -> None:
    """CDG au point de référence, sans propulsion ni gouverne : AERCAL rend les tables du COMMON."""
    tab = bibliotheques["t0"].aertab
    neutre = {"xg": 1.2, "yg": 0.0, "zg": 0.0, "ipropu": 0, "dm": 0.0, "dn": 0.0}
    for i, j in itertools.product(range(7), range(7)):
        r = modele.calculer(mach=tab.tmach[i], alpha=tab.talpha[j], beta=0.0, **neutre)
        assert r["ierr"] == ma.IERR_NOMINAL
        assert [r["cx"], r["cz"], r["cm"]] == [float(tab.tcx[i, j]), float(tab.tcz[i, j]), float(tab.tcm[i, j])]
        r = modele.calculer(mach=tab.tmach[i], alpha=0.0, beta=tab.tbeta[j], **neutre)
        assert [r["cy"], r["cl"], r["cn"]] == [float(tab.tcy[i, j]), float(tab.tcl[i, j]), float(tab.tcn[i, j])]


@avec_compilateur
def test_centre_de_maille(modele: Any, bibliotheques: dict[str, Any]) -> None:
    tab = bibliotheques["t0"].aertab
    m, a = 0.5 * (tab.tmach[2] + tab.tmach[3]), 0.5 * (tab.talpha[4] + tab.talpha[5])
    r = modele.calculer(mach=m, alpha=a, beta=0.0, xg=1.2, yg=0.0, zg=0.0, ipropu=0, dm=0.0, dn=0.0)
    assert r["cz"] == pytest.approx(tab.tcz[2:4, 4:6].mean(), abs=1e-15)


@avec_compilateur
def test_symetrie_en_beta(modele: Any) -> None:
    plus = modele.calculer(**{**POINT, "yg": 0.0})
    moins = modele.calculer(**{**POINT, "yg": 0.0, "beta": -POINT["beta"]})
    for n in ("cy", "cl", "cn"):
        assert plus[n] == pytest.approx(-moins[n], abs=1e-15)
    for n in ("cx", "cz", "cm"):
        assert plus[n] == pytest.approx(moins[n], abs=1e-15)


@avec_compilateur
def test_transport_des_moments(bibliotheques: dict[str, Any]) -> None:
    """M(G) = M(R) + (R − G) × F / LREF, avec un point de référence et une LREF non standard."""
    xref, yref, zref, lref = 1.1, 0.002, -0.003, 0.25
    m = ma.ModeleAero(bibliotheques["t0"], xref=xref, yref=yref, zref=zref, lref=lref)
    en_r = m.calculer(**{**POINT, "xg": xref, "yg": yref, "zg": zref})
    en_g = m.calculer(**POINT)
    for n in ("cx", "cy", "cz"):
        assert en_g[n] == en_r[n]
    rx, ry, rz = ((xref - POINT["xg"]) / lref, (yref - POINT["yg"]) / lref, (zref - POINT["zg"]) / lref)
    cx, cy, cz = en_r["cx"], en_r["cy"], en_r["cz"]
    assert en_g["cl"] == pytest.approx(en_r["cl"] + ry * cz - rz * cy, abs=1e-14)
    assert en_g["cm"] == pytest.approx(en_r["cm"] + rz * cx - rx * cz, abs=1e-14)
    assert en_g["cn"] == pytest.approx(en_r["cn"] + rx * cy - ry * cx, abs=1e-14)


@avec_compilateur
def test_propulsion(modele: Any, bibliotheques: dict[str, Any]) -> None:
    tab = bibliotheques["t0"].aertab
    sans = modele.calculer(**{**POINT, "ipropu": 0})
    avec = modele.calculer(**POINT)
    assert avec["cx"] - sans["cx"] == pytest.approx(np.interp(POINT["mach"], tab.tmachp, tab.tdcxp), abs=1e-14)
    assert (avec["cy"], avec["cz"]) == (sans["cy"], sans["cz"])


@avec_compilateur
def test_codes_ierr(modele: Any) -> None:
    assert modele.calculer(**{**POINT, "mach": 3.0})["ierr"] == ma.IERR_HORS_DOMAINE
    assert modele.calculer(**{**POINT, "alpha": -30.0})["ierr"] == ma.IERR_HORS_DOMAINE
    # grille propulsive (0.4…1.8) plus étroite que la grille aéro (0.3…2.0)
    assert modele.calculer(**{**POINT, "mach": 0.35, "ipropu": 0})["ierr"] == ma.IERR_NOMINAL
    assert modele.calculer(**{**POINT, "mach": 0.35, "ipropu": 1})["ierr"] == ma.IERR_HORS_DOMAINE
    r = modele.calculer(**{**POINT, "ipropu": 2})
    assert r["ierr"] == ma.IERR_IPROPU and [r[n] for n in NOMS] == [0.0] * 6
    sature = modele.calculer(**{**POINT, "mach": 3.0})
    bord = modele.calculer(**{**POINT, "mach": 2.0})
    assert [sature[n] for n in NOMS] == [bord[n] for n in NOMS]


@avec_compilateur
def test_etat_fortran_partage_entre_objets(bibliotheques: dict[str, Any]) -> None:
    """Deux objets, une bibliothèque, deux LREF : chacun retrouve la sienne."""
    a = ma.ModeleAero(bibliotheques["t0"], lref=0.1)
    seul = a.calculer(**POINT)
    b = ma.ModeleAero(bibliotheques["t0"], lref=0.4)  # réinitialise le Fortran
    assert b.calculer(**POINT)["cm"] != seul["cm"]
    assert a.calculer(**POINT) == seul


@avec_compilateur
def test_deux_compilations_cote_a_cote(bibliotheques: dict[str, Any]) -> None:
    """-O0 et -O3 -ffast-math chargées ensemble : états séparés, écarts de quelques ULP."""
    a = ma.ModeleAero(bibliotheques["t0"], lref=0.1)
    b = ma.ModeleAero(bibliotheques["t3"], lref=0.2)
    c = ma.ModeleAero(bibliotheques["t0"], lref=0.2)
    rb, rc = b.calculer(**POINT), c.calculer(**POINT)
    assert a.calculer(**POINT)["cm"] != rb["cm"]
    for n in NOMS:
        assert rb[n] == pytest.approx(rc[n], rel=1e-13, abs=1e-15)


# -- DataFrame --------------------------------------------------------------


def _plan() -> pd.DataFrame:
    lignes = [{"cas": f"C{i}", **POINT, "mach": m, "alpha": a, "ipropu": p}
              for i, (m, a, p) in enumerate(itertools.product((0.5, 1.2, 2.5), (-5.0, 0.0, 12.0), (0, 1)))]
    return pd.DataFrame(lignes)


@avec_compilateur
def test_calculer_df(modele: Any) -> None:
    df = _plan()
    sortie = modele.calculer_df(df)
    assert list(sortie.columns) == [*df.columns, *NOMS, "ierr", *SONDES]
    assert all(sortie[c].dtype == np.float64 for c in SONDES)
    pd.testing.assert_frame_equal(sortie[df.columns], df)  # entrées recopiées, cas compris
    assert sortie["ierr"].dtype == np.int64 and sortie["cx"].dtype == np.float64
    ligne = df.iloc[7]
    attendu = modele.calculer(**{n: ligne[n] for n in modele.arguments_calcul})
    assert {n: sortie.iloc[7][n] for n in attendu} == attendu
    assert set(sortie["ierr"]) == {0, 2}


@avec_compilateur
def test_calculer_df_index_conserve(modele: Any) -> None:
    df = _plan().set_index("cas")
    assert list(modele.calculer_df(df).index) == list(df.index)


@avec_compilateur
def test_calculer_df_constante_par_ligne(modele: Any) -> None:
    """Une colonne d'argument d'init : réinit à chaque changement, puis l'objet retrouve ses constantes."""
    df = pd.DataFrame([POINT] * 3).assign(lref=[0.1, 0.2, 0.1])
    sortie = modele.calculer_df(df)
    seul = {lref: ma.ModeleAero(modele.bibliotheque, lref=lref).calculer(**POINT)["cm"] for lref in (0.1, 0.2)}
    assert list(sortie["cm"]) == [seul[0.1], seul[0.2], seul[0.1]]
    assert modele.lref == 0.2
    assert modele.calculer(**POINT)["cm"] == seul[0.2]


@avec_compilateur
def test_calculer_df_refus(modele: Any) -> None:
    df = _plan()
    with pytest.raises(mf.ErreurModele, match=r"absente.*alpha"):
        modele.calculer_df(df.drop(columns="alpha"))
    with pytest.raises(mf.ErreurModele, match=r"déjà présentes.*cx"):
        modele.calculer_df(df.assign(cx=0.0))
    with pytest.raises(mf.ErreurModele, match=r"ipropu = 0.5"):
        modele.calculer_df(df.assign(ipropu=0.5))
    flottant = modele.calculer_df(df.assign(ipropu=1.0))["ierr"]
    entier = modele.calculer_df(df.assign(ipropu=1))["ierr"]
    assert list(flottant) == list(entier)


@avec_compilateur
def test_calculer_df_vide(modele: Any) -> None:
    sortie = modele.calculer_df(_plan().iloc[:0])
    assert len(sortie) == 0 and list(sortie.columns)[-15:] == [*NOMS, "ierr", *SONDES]


@avec_compilateur
def test_exemple_appel(bibliotheques: dict[str, Any], tmp_path: Path) -> None:
    """exemple_appel.py tourne sur un module construit ailleurs (copie de PYTHON/)."""
    copie = tmp_path / "PYTHON"
    shutil.copytree(PYTHON, copie, ignore=shutil.ignore_patterns("*.so", "__pycache__"))
    _construire(copie, "aerolib", "-O2")
    res = subprocess.run([sys.executable, "exemple_appel.py"], cwd=copie, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert "180 cas" in res.stdout


# -- sondes et lecture des COMMON ----------------------------------------------


@avec_compilateur
def test_sondes_lues_avant_toute_transformation(modele: Any) -> None:
    """Les sondes valent la lecture brute : propulsion, gouvernes et transport viennent après."""
    r = modele.calculer(**POINT)
    assert r["cx"] == pytest.approx(r["valid_tab_cx"] + r["valid_tab_dcxp"], abs=1e-15)
    assert r["valid_tab_dcmg"] != 0.0
    au_cdg_de_reference = modele.calculer(**{**POINT, "xg": 1.2, "yg": 0.0, "zg": 0.0})
    assert au_cdg_de_reference["cm"] == pytest.approx(r["valid_tab_cm"] + r["valid_tab_dcmg"], abs=1e-15)


@avec_compilateur
def test_sonde_non_atteinte_vaut_nan(modele: Any) -> None:
    """DCXP n'est lue que propulsion allumée : sinon NaN, jamais la valeur de l'appel précédent."""
    assert not math.isnan(modele.calculer(**POINT)["valid_tab_dcxp"])
    assert math.isnan(modele.calculer(**{**POINT, "ipropu": 0})["valid_tab_dcxp"])
    refus = modele.calculer(**{**POINT, "ipropu": 2})  # IERR 3 : retour avant toute lecture
    assert all(math.isnan(refus[s]) for s in SONDES)


@avec_compilateur
def test_lire_common(modele: Any, bibliotheques: dict[str, Any]) -> None:
    tcx = modele.lire("aertab.tcx")
    assert tcx.shape == (7, 7) and np.array_equal(tcx, bibliotheques["t0"].aertab.tcx)
    tcx[0, 0] = 99.0  # une copie : la table du code n'est pas touchée
    assert bibliotheques["t0"].aertab.tcx[0, 0] != 99.0
    assert modele.lire("AERTB5.TDCMG").shape == (5, 5, 5, 5, 5)
    with pytest.raises(mf.ErreurModele, match="aertab, aertb5, probe"):
        modele.lire("inconnu.x")
    with pytest.raises(mf.ErreurModele, match="tmach"):
        modele.lire("aertab.pas_la")


# -- test de lecture de table (VALIDATION/01_lecture_tables.py) ----------------

VALIDATION = PROJET / "VALIDATION"
LECTURE = VALIDATION / "01_LECTURE_TABLES" / "01_lecture_tables.py"


def _lecture(bibliotheques: dict[str, Any], sortie: Path, *options: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LECTURE), "--module", "aerolib_t0", "--dossier", str(bibliotheques["dossier"]),
         "--sortie", str(sortie), *options],
        capture_output=True, text=True, env={**os.environ, "COLUMNS": "100", "MPLBACKEND": "Agg"},
    )


@avec_compilateur
def test_lecture_tables_conforme(bibliotheques: dict[str, Any], tmp_path: Path) -> None:
    res = _lecture(bibliotheques, tmp_path / "L", "--sans-figures")
    assert res.returncode == 0, res.stdout + res.stderr
    resume = json.loads((tmp_path / "L" / "resume.json").read_text())
    tables = {t["nom"]: t for t in resume["tables"]}
    assert set(tables) == {"CX", "CZ", "CM", "CY", "CL", "CN", "DCXP", "DCMG"}
    assert all(t["conforme"] for t in tables.values())
    assert all(t["tolerees"] == 0 for n, t in tables.items() if n != "DCMG")  # bit pour bit hors inversion
    assert tables["DCMG"]["noeuds"] == 3125 and tables["DCMG"]["inversion"]
    resultats = pd.read_csv(tmp_path / "L" / "RESULTATS" / "CX.csv")
    assert {"valeur_TAB", "valeur_CODE", "ecart", "conforme"} <= set(resultats.columns)
    assert (tmp_path / "L" / "TABLES" / "DCMG.csv").exists()


@avec_compilateur
def test_lecture_tables_combinaisons(bibliotheques: dict[str, Any], tmp_path: Path) -> None:
    res = _lecture(bibliotheques, tmp_path / "C", "--combinaisons", "--sans-figures")
    assert res.returncode == 0, res.stdout + res.stderr
    tables = {t["nom"]: t for t in json.loads((tmp_path / "C" / "resume.json").read_text())["tables"]}
    assert tables["CX"]["combinaisons"] > 1 and "alpha" in tables["CX"]["combinaisons_ignorees"]
    assert "ipropu" in tables["DCXP"]["combinaisons_ignorees"]  # fixée


@avec_compilateur
def test_lecture_tables_defaut_detecte(bibliotheques: dict[str, Any], tmp_path: Path) -> None:
    res = _lecture(bibliotheques, tmp_path / "D")
    assert res.returncode == 0
    res = _lecture(bibliotheques, tmp_path / "D", "--defaut")
    assert res.returncode == 2, res.stdout + res.stderr
    tables = {t["nom"]: t for t in json.loads((tmp_path / "D" / "resume.json").read_text())["tables"]}
    assert tables["CM"]["echecs"] == 1 and all(t["conforme"] for n, t in tables.items() if n != "CM")
    assert sorted(p.name for p in (tmp_path / "D" / "FIGURES").iterdir()) == [
        "synthese_tables_01.svg", "synthese_tables_02.svg"]  # SVG seul


# -- VALIDATION/RUN_VALIDATION.sh et le récapitulatif ---------------------------


def _recap(sortie: Path, *tests: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(VALIDATION / "recapituler.py"), str(sortie), *tests],
                          capture_output=True, text=True)


def _resume(dossier: Path, conforme: bool, echecs: int = 0) -> None:
    dossier.mkdir(parents=True)
    tables = [{"nom": "CX", "appels": 49, "echecs": echecs, "conforme": conforme},
              {"nom": "CY", "appels": 51, "echecs": 0, "conforme": True}]
    (dossier / "resume.json").write_text(json.dumps({"conforme": conforme, "verdict": "…", "tables": tables}))


def test_recapitulatif(tmp_path: Path) -> None:
    _resume(tmp_path / "01_OK", True)
    res = _recap(tmp_path, "01_OK:0")
    assert res.returncode == 0 and "TOUT EST À 100 %" in res.stdout and "2/2 tables, 100 appels" in res.stdout
    assert (tmp_path / "RECAP.txt").read_text() == res.stdout

    _resume(tmp_path / "02_KO", False, echecs=1)
    res = _recap(tmp_path, "01_OK:0", "02_KO:2", "03_PLANTE:1")
    assert res.returncode == 1 and "1/3 tests conformes — À REPRENDRE" in res.stdout
    assert "99.0 %" in res.stdout and "✗ CX : 1/49 en échec" in res.stdout  # 99/100, jamais arrondi à 100
    assert "03_PLANTE                ERREUR" in res.stdout


@avec_compilateur
def test_run_validation(bibliotheques: dict[str, Any], tmp_path: Path) -> None:
    """Le script bash lance chaque test, transmet ses options et récapitule ; sortie dans une copie."""
    copie = tmp_path / "VALIDATION"
    shutil.copytree(VALIDATION, copie, ignore=shutil.ignore_patterns("SORTIE", "__pycache__"))
    (tmp_path / "PYTHON").symlink_to(PYTHON)  # ../../PYTHON depuis le script de test
    res = subprocess.run(
        ["bash", str(copie / "RUN_VALIDATION.sh"), "--module", "aerolib_t0", "--dossier", str(bibliotheques["dossier"]),
         "--sans-figures"],
        capture_output=True, text=True, env={**os.environ, "CFD_VALIDATION_PYTHON": sys.executable},
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "3/3 tests conformes — TOUT EST À 100 %" in res.stdout and "8/8 tables, 26888 appels" in res.stdout
    assert "02_BORNES_TABLES         CONFORME      8/8 tables, 4545 appels" in res.stdout
    assert "03_INTERPOLATION_TABLES  CONFORME      8/8 tables, 40270 appels" in res.stdout
    assert (copie / "SORTIE" / "RECAP.txt").exists()
    assert (copie / "SORTIE" / "01_LECTURE_TABLES" / "resume.json").exists()


def test_construire_refuse_source_absent_ou_non_ascii(tmp_path: Path) -> None:
    """Les deux refus de construire.sh, avant tout appel à f2py (sans compilateur)."""
    copie = tmp_path / "MODELE"
    shutil.copytree(PROJET, copie, ignore=shutil.ignore_patterns("*.so", "SORTIE", "__pycache__"))
    script = copie / "PYTHON" / "construire.sh"
    env = {**os.environ, "CFD_VALIDATION_PYTHON": sys.executable}
    source = copie / "SOURCES" / "aero_interp.f"
    source.write_text(source.read_text() + "C     é\n", encoding="utf-8")
    res = subprocess.run(["bash", str(script), "x", str(tmp_path)], capture_output=True, text=True, env=env)
    assert res.returncode == 1 and "non ASCII" in res.stderr
    source.unlink()
    res = subprocess.run(["bash", str(script), "x", str(tmp_path)], capture_output=True, text=True, env=env)
    assert res.returncode == 1 and "aero_interp.f" in res.stderr and "introuvable" in res.stderr


# -- consignes hors grille et test des bornes (VALIDATION/02_BORNES_TABLES) ------


@avec_compilateur
def test_consignes_hors_grille(modele: Any, bibliotheques: dict[str, Any]) -> None:
    """Le Fortran extrapole en alpha, sature en Mach, et lève IERR = 2 dans les deux cas."""
    tab = bibliotheques["t0"].aertab
    neutre = {"beta": 0.0, "xg": 1.2, "yg": 0.0, "zg": 0.0, "ipropu": 0, "dm": 0.0, "dn": 0.0}
    a, t = tab.talpha, tab.tcx
    r = modele.calculer(mach=float(tab.tmach[2]), alpha=26.0, **neutre)
    attendu = t[2, -1] + (26.0 - a[-1]) / (a[-1] - a[-2]) * (t[2, -1] - t[2, -2])
    assert r["valid_tab_cx"] == pytest.approx(attendu, abs=1e-15) and r["ierr"] == ma.IERR_HORS_DOMAINE
    r = modele.calculer(mach=2.5, alpha=float(a[3]), **neutre)
    assert r["valid_tab_cx"] == float(t[-1, 3]) and r["ierr"] == ma.IERR_HORS_DOMAINE


BORNES = VALIDATION / "02_BORNES_TABLES" / "02_bornes_tables.py"


def _bornes(bibliotheques: dict[str, Any], sortie: Path, *options: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BORNES), "--module", "aerolib_t0", "--dossier", str(bibliotheques["dossier"]),
         "--sortie", str(sortie), *options],
        capture_output=True, text=True, env={**os.environ, "COLUMNS": "100", "MPLBACKEND": "Agg"},
    )


@avec_compilateur
def test_bornes_tables_conforme(bibliotheques: dict[str, Any], tmp_path: Path) -> None:
    res = _bornes(bibliotheques, tmp_path / "B", "--sans-figures")
    assert res.returncode == 0, res.stdout + res.stderr
    tables = {t["nom"]: t for t in json.loads((tmp_path / "B" / "resume.json").read_text())["tables"]}
    assert set(tables) == {"CX", "CZ", "CM", "CY", "CL", "CN", "DCXP", "DCMG"}
    faces = {f["face"]: f for f in tables["CX"]["faces"]}
    assert faces["alpha+"]["observe"] == "extrapole" and faces["mach+"]["observe"] == "sature"
    dcmg = tables["DCMG"]
    assert sorted(f["face"] for f in dcmg["non_testees"]) == ["alphat−", "phia+", "phia−"]
    assert {f["face"]: f["observe"] for f in dcmg["faces"]}["alphat+"] == "extrapole"
    assert dcmg["appels"] == 7 * 625


@avec_compilateur
def test_bornes_tables_consigne_fausse_detectee(bibliotheques: dict[str, Any], tmp_path: Path) -> None:
    res = _bornes(bibliotheques, tmp_path / "D", "--defaut")
    assert res.returncode == 2, res.stdout + res.stderr
    resume = json.loads((tmp_path / "D" / "resume.json").read_text())
    assert resume["motifs_non_conformite"] == [
        "CX alpha− : attendu sature, observé extrapole (7/7 hors tolérance)",
        "CX alpha+ : attendu sature, observé extrapole (7/7 hors tolérance)",
    ]
    assert [p.name for p in sorted((tmp_path / "D" / "FIGURES").iterdir())] == [
        "synthese_bornes_01.svg", "synthese_bornes_02.svg"]


# -- interpolation et polaires (VALIDATION/03_INTERPOLATION_TABLES) -------------

INTERPOLATION = VALIDATION / "03_INTERPOLATION_TABLES" / "03_interpolation_tables.py"


def _interpolation(bibliotheques: dict[str, Any], sortie: Path, *options: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(INTERPOLATION), "--module", "aerolib_t0", "--dossier", str(bibliotheques["dossier"]),
         "--sortie", str(sortie), *options],
        capture_output=True, text=True, env={**os.environ, "COLUMNS": "100", "MPLBACKEND": "Agg"},
    )


@avec_compilateur
def test_interpolation_tables_conforme(bibliotheques: dict[str, Any], tmp_path: Path) -> None:
    res = _interpolation(bibliotheques, tmp_path / "I", "--sans-figures")
    assert res.returncode == 0, res.stdout + res.stderr
    resume = json.loads((tmp_path / "I" / "resume.json").read_text())
    tables = {t["nom"]: t for t in resume["tables"]}
    assert set(tables) == {"CX", "CZ", "CM", "CY", "CL", "CN", "DCXP", "DCMG"} and resume["appels"] == 40270
    assert {g["groupe"] for g in tables["DCMG"]["groupes"]} == {"mach", "alphat", "phia", "dm", "dn", "centres"}
    assert {g["observe"] for t in tables.values() for g in t["groupes"]} == {"linéaire"}


@avec_compilateur
def test_interpolation_palier_detecte_et_polaires(bibliotheques: dict[str, Any], tmp_path: Path) -> None:
    pytest.importorskip("cfd_plot")
    res = _interpolation(bibliotheques, tmp_path / "D", "--defaut", "--jobs", "2")
    assert res.returncode == 2, res.stdout + res.stderr
    resume = json.loads((tmp_path / "D" / "resume.json").read_text())
    assert resume["motifs_non_conformite"] == [
        "CM alpha : attendu linéaire, observé palier (126/126 hors tolérance, 6/6 maille(s))",
        "CM centres : attendu linéaire, observé ni l'un ni l'autre (36/36 hors tolérance, 36/36 maille(s))",
    ]
    polaires = tmp_path / "D" / "POLAIRES"
    assert (polaires / "CM" / "POLAIRE_ALPHA" / "MACH_0.8" / "CM_vs_alpha.svg").exists()
    assert (polaires / "CM" / "POLAIRE_ALPHA" / "SUPERPOSITION" / "CM_vs_alpha_by_MACH.svg").exists()
    assert (polaires / "DCMG" / "POLAIRE_ALPHAT" / "SUPERPOSITION" / "PHIA_90" / "DCMG_vs_alphat_by_DM.svg").exists()
    assert len(list(polaires.rglob("*.svg"))) == sum(p["courbes"] for p in resume["polaires"]) + 12 + 7  # superpositions : 2D, puis DCMG
