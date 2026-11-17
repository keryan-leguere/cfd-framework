from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cfd_validation.cli.main import EXIT_ERREUR_ENTREE, EXIT_NON_CONFORME, EXIT_OK, main
from cfd_validation.paths import EXEMPLE_DIR


@pytest.fixture
def fichiers(reference: pd.DataFrame, tmp_path: Path) -> tuple[Path, Path, Path]:
    ref = tmp_path / "ref.csv"
    bon = tmp_path / "bon.csv"
    mauvais = tmp_path / "mauvais.csv"
    reference.to_csv(ref, index=False)
    reference.sample(frac=1.0, random_state=0).to_csv(bon, index=False)
    faux = reference.copy()
    faux.loc[0, "CN"] += 1.0
    faux.to_csv(mauvais, index=False)
    return ref, bon, mauvais


ARGS = ["--entrees", "Mach,alpha,conf", "--sorties", "CN,Cm,regime", "--sans-figures"]


def test_codes_de_retour(fichiers: tuple[Path, Path, Path], tmp_path: Path) -> None:
    ref, bon, mauvais = fichiers
    assert main(["integration", str(ref), str(bon), *ARGS, "-o", str(tmp_path / "a")]) == EXIT_OK
    assert main(["integration", str(ref), str(mauvais), *ARGS, "-o", str(tmp_path / "b")]) == EXIT_NON_CONFORME
    assert (tmp_path / "b" / "integration.log").is_file()


def test_csv_relu_au_bit_pres(tmp_path: Path) -> None:
    ref = pd.DataFrame({"a": np.arange(50.0), "x": np.random.default_rng(0).normal(size=50) / 3})
    chemin = tmp_path / "r.csv"
    ref.to_csv(chemin, index=False)
    code = main(["integration", str(chemin), str(chemin), "-e", "a", "-s", "x", "--rtol", "0", "--atol", "0",
                 "--sans-figures", "-o", str(tmp_path / "o")])
    assert code == EXIT_OK  # tolérance nulle : la relecture n'a pas perdu un ULP


def test_sorties_seules(tmp_path: Path) -> None:
    ref = pd.DataFrame({"x": np.arange(10.0), "y": np.arange(10.0) ** 2})
    chemin = tmp_path / "r.csv"
    ref.to_csv(chemin, index=False)
    faux = tmp_path / "f.csv"
    ref.iloc[::-1].to_csv(faux, index=False)
    base = ["-s", "x,y", "--sans-figures"]
    assert main(["integration", str(chemin), str(chemin), *base, "-o", str(tmp_path / "a")]) == EXIT_OK
    assert main(["integration", str(chemin), str(faux), *base, "-o", str(tmp_path / "b")]) == EXIT_NON_CONFORME


def test_config_yaml_et_surcharge(fichiers: tuple[Path, Path, Path], tmp_path: Path) -> None:
    ref, _, mauvais = fichiers
    config = tmp_path / "c.yaml"
    config.write_text("entrees: [Mach, alpha, conf]\nsorties: [CN, Cm, regime]\nidentifiant: INT-09\n", encoding="utf-8")
    sortie = tmp_path / "o"
    assert main(["integration", str(ref), str(mauvais), "-c", str(config), "--sans-figures", "-o", str(sortie)]) == EXIT_NON_CONFORME
    # une tolérance énorme passée en option rend le test conforme
    assert main(["integration", str(ref), str(mauvais), "-c", str(config), "--rtol", "1000", "--sans-figures", "-o", str(sortie)]) == EXIT_OK
    assert "INT-09" in (sortie / "integration.log").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "args",
    [
        ["integration", "{ref}", "{ref}", "--sans-figures"],  # aucune sortie
        ["integration", "{ref}", "absent.csv", *ARGS],
        ["integration", "{ref}", "{ref}", "-e", "Mach", "-s", "inconnue", "--sans-figures"],
    ],
)
def test_erreurs_d_entree(fichiers: tuple[Path, Path, Path], tmp_path: Path, args: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    ref = fichiers[0]
    with pytest.raises(SystemExit) as fin:
        main([a.format(ref=ref) for a in args] + ["-o", str(tmp_path / "o")])
    assert fin.value.code == EXIT_ERREUR_ENTREE
    assert "Erreur" in capsys.readouterr().err


def test_exemple(tmp_path: Path) -> None:
    dest = tmp_path / "ex"
    assert main(["exemple", str(dest)]) == EXIT_OK
    assert {p.name for p in dest.iterdir()} >= {"01_test_integration.py", "02_grande_table.py", "INTEGRATION.yaml", "RUN_EXEMPLE.sh", "README.md"}
    with pytest.raises(SystemExit):
        main(["exemple", str(dest)])  # rien n'est écrasé


def test_exemple_yaml_valide() -> None:
    from cfd_validation.data.lecture import lire_yaml
    from cfd_validation.data.specification import specification_depuis_dict

    spec, desc = specification_depuis_dict(lire_yaml(EXEMPLE_DIR / "INTEGRATION.yaml"))
    assert spec.tolerance("CY").atol == 1e-14
    assert desc["identifiant"] == "INT-01"
