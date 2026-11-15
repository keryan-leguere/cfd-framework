from __future__ import annotations

import numpy as np
import pandas as pd

from cfd_validation.engine.appariement import apparier


def test_ordre_quelconque(reference: pd.DataFrame) -> None:
    test = reference.sample(frac=1.0, random_state=0).reset_index(drop=True)
    app = apparier(reference, test, ["Mach", "alpha", "conf"])
    assert app.ref.tolist() == list(range(len(reference)))
    assert (test.loc[app.test, "CN"].to_numpy() == reference["CN"].to_numpy()).all()
    assert not app.meme_ordre
    assert app.absentes.size == app.en_trop.size == 0


def test_absentes_et_en_trop(reference: pd.DataFrame) -> None:
    test = reference.drop(index=[3, 7]).copy()
    test.loc[len(reference) + 1] = [9.0, 0.0, "A", 0.0, 0.0, "x"]
    app = apparier(reference, test.reset_index(drop=True), ["Mach", "alpha", "conf"])
    assert app.absentes.tolist() == [3, 7]
    assert app.en_trop.tolist() == [len(test) - 1]


def test_entier_apparie_flottant_et_zero_signe() -> None:
    ref = pd.DataFrame({"a": [1, 0, 2], "x": [1.0, 2.0, 3.0]})
    test = pd.DataFrame({"a": [2.0, -0.0, 1.0], "x": [3.0, 2.0, 1.0]})
    app = apparier(ref, test, ["a"])
    assert app.test.tolist() == [2, 1, 0]


def test_chiffres_cle() -> None:
    ref = pd.DataFrame({"a": [0.1 + 0.2, 1 / 3]})
    test = pd.DataFrame({"a": [0.333333, 0.3]})
    assert apparier(ref, test, ["a"]).absentes.size == 2
    assert apparier(ref, test, ["a"], chiffres_cle=6).test.tolist() == [1, 0]


def test_doublons_apparies_dans_l_ordre() -> None:
    ref = pd.DataFrame({"a": [1.0, 1.0, 2.0], "x": [10.0, 11.0, 12.0]})
    test = pd.DataFrame({"a": [2.0, 1.0, 1.0], "x": [12.0, 10.0, 11.0]})
    app = apparier(ref, test, ["a"])
    assert app.n_cles_dupliquees == 1
    assert app.test.tolist() == [1, 2, 0]


def test_nan_en_entree_apparie() -> None:
    ref = pd.DataFrame({"a": [np.nan, 1.0]})
    test = pd.DataFrame({"a": [1.0, np.nan]})
    assert apparier(ref, test, ["a"]).test.tolist() == [1, 0]


def test_position_entrees_divergentes(reference: pd.DataFrame) -> None:
    test = reference.copy()
    test.loc[5, "alpha"] = 99.0
    test = test.iloc[:-2]
    app = apparier(reference, test, ["Mach", "alpha", "conf"], alignement="position")
    assert np.flatnonzero(app.divergentes).tolist() == [5]
    assert app.absentes.tolist() == [len(reference) - 2, len(reference) - 1]


def test_types_incompatibles_apparies_en_texte() -> None:
    ref = pd.DataFrame({"a": ["1", "2"]})
    test = pd.DataFrame({"a": [2, 1]})
    app = apparier(ref, test, ["a"])
    assert app.entrees_en_texte == ("a",)
    assert app.test.tolist() == [1, 0]
