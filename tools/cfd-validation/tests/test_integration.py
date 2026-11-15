"""Le moteur du test d'intégration, sur des échecs connus d'avance."""

from __future__ import annotations

import json
import math
from types import ModuleType

import numpy as np
import pandas as pd
import pytest

from cfd_validation.core import statuts as st
from cfd_validation.data.specification import ErreurSpecification, construire_specification
from cfd_validation.engine.integration import comparer

ENTREES = ["Mach", "alpha", "conf"]
SORTIES = ["CN", "Cm", "regime"]


def _comparer(ref: pd.DataFrame, test: pd.DataFrame, **kw: object):  # type: ignore[no-untyped-def]
    spec = construire_specification(kw.pop("entrees", ENTREES), kw.pop("sorties", SORTIES), **kw)  # type: ignore[arg-type]
    return comparer(ref, test, spec)


def test_identique_dans_le_desordre(reference: pd.DataFrame) -> None:
    res = _comparer(reference, reference.sample(frac=1.0, random_state=4))
    assert res.conforme and res.bit_identique
    assert res.verdict == "CONFORME — identique bit pour bit"
    assert not res.structure.meme_ordre
    assert all(b.n_identiques == len(reference) for b in res.sorties)
    assert res.n_lignes_echec == 0


def test_bruit_dans_la_tolerance(reference: pd.DataFrame) -> None:
    test = reference.copy()
    test["CN"] = np.nextafter(test["CN"].to_numpy(), np.inf)
    res = _comparer(reference, test)
    assert res.conforme and not res.bit_identique
    cn = next(b for b in res.sorties if b.nom == "CN")
    assert cn.n_toleres == len(reference) - int((reference["CN"] == np.nextafter(reference["CN"], np.inf)).sum())
    assert cn.max_ulp == 1


def test_regression_localisee_attribuee_a_la_bonne_entree(reference: pd.DataFrame) -> None:
    test = reference.copy()
    test.loc[test["Mach"] == 2.0, "Cm"] *= 1.01
    res = _comparer(reference, test, rtol=1e-9, atol=1e-12)
    assert not res.conforme
    cm = next(b for b in res.sorties if b.nom == "Cm")
    assert cm.n_ecarts == 10
    assert cm.pire is not None and cm.pire.entrees["Mach"] == 2.0
    attrib = {a.entree: a for a in res.attributions}
    assert attrib["Mach"].v == pytest.approx(1.0)
    assert attrib["Mach"].v > attrib["alpha"].v and attrib["Mach"].v > attrib["conf"].v
    en_cause = attrib["Mach"].niveaux_en_cause(res.taux_echec)
    assert [n.libelle for n in en_cause] == ["2"]
    assert en_cause[0].taux == 1.0


def test_lignes_absentes_en_trop_et_non_fini(reference: pd.DataFrame) -> None:
    test = reference.drop(index=[0, 1]).copy()
    test.loc[5, "CN"] = np.nan
    extra = reference.iloc[[2]].assign(Mach=9.9)
    test = pd.concat([test, extra], ignore_index=True)
    res = _comparer(reference, test)
    s = res.structure
    assert (s.n_absentes, s.n_en_trop, s.n_comparees) == (2, 1, len(reference) - 2)
    codes = res.lignes.set_index("ligne_ref")["code"]
    assert codes.loc[0] == codes.loc[1] == st.ABSENTE
    assert codes.loc[5] == st.NON_FINI
    assert res.lignes["code"].iloc[-1] == st.EN_TROP
    assert pd.isna(res.lignes["ligne_ref"].iloc[-1])
    assert len(res.motifs_non_conformite) == 3
    # une ligne absente compte comme un échec dans l'attribution
    mach = next(a for a in res.attributions if a.entree == "Mach")
    assert next(n for n in mach.niveaux if n.libelle == "0.5").n_absentes == 2


def test_sortie_absente_du_test(reference: pd.DataFrame) -> None:
    res = _comparer(reference, reference.drop(columns=["Cm"]))
    assert not res.conforme
    assert res.structure.sorties_absentes == ("Cm",)
    assert next(b for b in res.sorties if b.nom == "Cm").statut == st.ABSENTE


def test_renommage_test(reference: pd.DataFrame) -> None:
    test = reference.rename(columns={"CN": "cn", "Mach": "M"})
    res = _comparer(reference, test, renommage_test={"cn": "CN", "M": "Mach"})
    assert res.bit_identique


def test_sortie_texte_comparee_exactement(reference: pd.DataFrame) -> None:
    test = reference.copy()
    test.loc[3, "regime"] = "trans"
    res = _comparer(reference, test)
    regime = next(b for b in res.sorties if b.nom == "regime")
    assert not regime.numerique and regime.n_ecarts == 1
    assert math.isnan(regime.marge_max)


def test_position_divergentes_non_comparees(reference: pd.DataFrame) -> None:
    test = reference.copy()
    test.loc[4, "alpha"] = 50.0
    test.loc[4, "CN"] = 123.0
    res = _comparer(reference, test, alignement="position")
    assert res.structure.n_divergentes == 1
    assert res.structure.n_comparees == len(reference) - 1
    assert all(b.n_ecarts == 0 for b in res.sorties)  # le CN faux n'est pas comparé
    assert not res.conforme


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda r, t: (r.iloc[:0], t), "vide"),
        (lambda r, t: (r, t.drop(columns=["alpha"])), "entrée.*absente.*du test"),
        (lambda r, t: (r.drop(columns=["Cm"]), t), "absente.*de la référence"),
    ],
)
def test_refus(reference: pd.DataFrame, mutation, message: str) -> None:  # type: ignore[no-untyped-def]
    ref, test = mutation(reference, reference.copy())
    with pytest.raises(ErreurSpecification, match=message):
        _comparer(ref, test)


def test_colonnes_en_double_refusees(reference: pd.DataFrame) -> None:
    test = pd.concat([reference, reference[["CN"]]], axis=1)
    with pytest.raises(ErreurSpecification, match="en double"):
        _comparer(reference, test)


def test_tables_produites(reference: pd.DataFrame) -> None:
    res = _comparer(reference, reference)
    assert len(res.lignes) == len(reference)
    assert len(res.ecarts) == len(reference) * len(SORTIES)
    assert list(res.lignes.columns[:5]) == ["ligne_ref", "ligne_test", *ENTREES]
    assert {"reference", "test", "ecart", "ulp", "seuil", "marge", "statut"} <= set(res.ecarts.columns)


def test_resume_serialisable_json(reference: pd.DataFrame) -> None:
    test = reference.copy()
    test.loc[0, "CN"] = np.nan
    res = _comparer(reference, test)
    texte = json.dumps(res.resume(), allow_nan=False)
    resume = json.loads(texte)
    assert resume["conforme"] is False
    assert resume["donnees"]["reference"]["sha256"] == res.empreinte_ref.sha256
    assert next(s for s in resume["sorties"] if s["nom"] == "CN")["marge_max"] == "inf"


def test_empreinte_sensible_a_un_ulp(reference: pd.DataFrame) -> None:
    from cfd_validation.engine.environnement import empreinte_table

    autre = reference.copy()
    autre.loc[0, "CN"] = np.nextafter(autre.loc[0, "CN"], np.inf)
    assert empreinte_table(reference).sha256 != empreinte_table(autre).sha256
    assert empreinte_table(reference).sha256 == empreinte_table(reference.copy()).sha256


@pytest.mark.parametrize(
    ("scenario", "conforme", "bit_identique"),
    [("identique", True, True), ("arrondi", True, False), ("regression", False, False)],
)
def test_scenarios_de_l_exemple(exemple: ModuleType, scenario: str, conforme: bool, bit_identique: bool) -> None:
    ref = exemple.modele_aero(exemple.plan_de_calcul())
    test = exemple.SCENARIOS[scenario][0](ref)
    spec = construire_specification(exemple.ENTREES, exemple.SORTIES, tolerances=exemple.TOLERANCES,
                                    rtol=exemple.RTOL, atol=exemple.ATOL, justification=exemple.JUSTIFICATION)
    res = comparer(ref, test, spec)
    assert (res.conforme, res.bit_identique) == (conforme, bit_identique)
    if scenario == "arrondi":
        assert max(b.max_ulp for b in res.sorties if b.numerique) <= 4
    if scenario == "regression":
        assert res.structure.n_absentes == 3
        tete = max(res.attributions, key=lambda a: a.v)
        assert tete.entree == "Mach" and tete.v > 0.9


def test_exemple_grande_table(exemple_grand: ModuleType) -> None:
    ref = exemple_grand.modele_aero(exemple_grand.plan_de_calcul())
    test = exemple_grand.test_integre(ref)
    spec = construire_specification(exemple_grand.ENTREES, exemple_grand.SORTIES, tolerances=exemple_grand.TOLERANCES,
                                    rtol=exemple_grand.RTOL, atol=exemple_grand.ATOL, justification="J")
    res = comparer(ref, test, spec)
    assert not res.conforme
    assert res.structure.n_absentes == 20
    en_echec = sorted(b.nom for b in res.sorties if b.n_echecs)
    assert en_echec == ["Cm", "Cm_alpha"]  # CM (casse différente) n'est pas touché
    assert res.entrees_par_pertinence()[0] == "braquage_profondeur"
    tete = next(a for a in res.attributions if a.entree == "braquage_profondeur")
    assert tete.v > 0.9
    assert [n.libelle for n in tete.niveaux_en_cause(res.taux_echec)] == ["15", "20"]
