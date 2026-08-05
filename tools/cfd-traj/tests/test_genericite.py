"""Le filet anti-codage en dur.

L'exigence centrale du besoin : les colonnes de paramètres sont génériques —
n'importe quel nombre, n'importe quels noms — et rien dans le paquet ne doit
les reconnaître autrement que par leurs valeurs. Cette exigence a son propre
fichier de tests parce qu'elle se casse silencieusement : un plan construit sur
une colonne mal identifiée reste un plan d'apparence correcte.

Le second balayage porte sur le vocabulaire : l'outil traite de trajectoires,
et aucun terme emprunté à un phénomène physique particulier ne doit y subsister.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cfd_traj.cli.main import EXIT_OK, main
from cfd_traj.core.adim import Reference
from cfd_traj.core.symmetry import SymmetryGroup, SymmetrySpec
from cfd_traj.data.columns import build_specs
from cfd_traj.data.dataset import load_dataset
from cfd_traj.data.derive import add_derived_columns
from cfd_traj.data.study import BandSpec, DoeMethod, DoeSpec, EnvelopeSpec
from cfd_traj.engine.bands import build_bands
from cfd_traj.engine.coverage import check_coverage
from cfd_traj.engine.doe import build_plan
from cfd_traj.engine.envelope import build_envelope

RACINE = Path(__file__).resolve().parents[1]
C4V = SymmetrySpec(group=SymmetryGroup.C4V)

#: Vocabulaire proscrit dans tout le paquet.
#:
#: Recherché sur des mots entiers : « jet » comme sous-chaîne se retrouve dans
#: « rejeté », « objet », « trajet », « projet », qui sont du français ordinaire.
FORBIDDEN_WORDS = ("jet", "jets", "tuyere", "tuyère", "panache", "npr", "p0j", "gaz froid")

#: Motif partagé, à frontières de mots.
FORBIDDEN_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in FORBIDDEN_WORDS) + r")\b", re.IGNORECASE
)

#: Répertoires balayés par les contrôles de vocabulaire.
SCANNED = ("src", "tests", "00_DOC", "01_EXEMPLE")

#: Fichiers dont le contenu n'est pas du texte relu par un humain.
SKIP_SUFFIXES = {".png", ".svg", ".pdf", ".pyc", ".csv"}

#: Les deux fichiers qui *déclarent* la liste des mots proscrits la contiennent
#: forcément ; les exclure évite un test tautologiquement en échec.
SELF_REFERENTIAL = {
    Path("tests/test_genericite.py"),
    Path("tests/report/test_console.py"),
}

#: Modules où « PARA » ne peut apparaître que comme préfixe par défaut du
#: générateur, ou comme exemple dans une docstring ou une aide de commande.
PARA_IS_DOCUMENTED = {
    Path("src/cfd_traj/synth/parametres.py"),
    Path("src/cfd_traj/synth/lot.py"),
    Path("src/cfd_traj/cli/main.py"),
    Path("src/cfd_traj/data/columns.py"),
    Path("src/cfd_traj/data/study.py"),
}


def _text_files() -> list[Path]:
    """Tous les fichiers texte du paquet."""
    out: list[Path] = []
    for name in SCANNED:
        root = RACINE / name
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix in SKIP_SUFFIXES:
                continue
            if "__pycache__" in path.parts or ".venv" in path.parts:
                continue
            out.append(path)
    out.extend(p for p in (RACINE / "README.md", RACINE / "pyproject.toml") if p.exists())
    return out


def _pipeline(directory: Path, tmp_path: Path, tag: str) -> dict:
    """Enveloppe, plan et couverture d'un lot, tous réglages fixés."""
    ds = add_derived_columns(
        load_dataset(directory), reference=Reference(length_m=2.5), symmetry=C4V
    )
    specs, _ = build_specs(ds.columns, ds.column_values(), {})
    bands = build_bands(ds.values("Mach"), BandSpec(n_bands=3, min_points=10))
    envelope = build_envelope(ds, band_set=bands, specs=specs, spec=EnvelopeSpec(), symmetry=C4V)
    plan = build_plan(
        envelope,
        doe=DoeSpec(method=DoeMethod.LHS, n_lhs_per_band=6, seed=99, max_nodes=100_000),
        symmetry=C4V,
        ds=ds,
    )
    coverage = check_coverage(ds, envelope=envelope)
    return {
        "n_nodes": plan.n_nodes,
        "cout": round(plan.total_cost, 6),
        "couverture": round(coverage.rate, 9),
        "configurations": sorted({str(n.calc_config) for n in plan.nodes}),
        "n_variables": len(plan.variable_names),
    }


class TestNamesDoNotMatter:
    def test_renaming_every_generic_column_changes_nothing(self, make_lot, tmp_path):
        """Le test décisif : mêmes valeurs, noms exotiques, plan identique."""
        conventional = make_lot(
            n_shots=4, extra=("PARA1", "PARA2", "PARA3", "PARA4"), name="A", seed=7
        )
        exotic = make_lot(
            n_shots=4, extra=("Z", "alpha_bis", "TEMP 42", "ratio_1"), name="B", seed=7
        )

        left = _pipeline(conventional, tmp_path, "A")
        right = _pipeline(exotic, tmp_path, "B")

        assert left == right

    @pytest.mark.parametrize(
        "name", ["Z", "TEMP 42", "é_àccentué", "1er", "x.y", "COL-1", "π_1", "MiXeD"]
    )
    def test_a_single_exotic_name_goes_through_the_whole_chain(self, make_lot, tmp_path, name):
        directory = make_lot(n_shots=3, extra=(name,))

        result = _pipeline(directory, tmp_path, "x")

        assert result["n_nodes"] > 0

    def test_the_column_order_does_not_matter(self, make_lot, tmp_path):
        directory = make_lot(n_shots=3, extra=("A", "B", "C"), name="ORDER")
        shuffled = tmp_path / "SHUFFLED"
        shuffled.mkdir()
        for path in sorted(directory.glob("*.csv")):
            frame = pd.read_csv(path)
            columns = [c for c in frame.columns if c not in ("A", "B", "C")] + ["C", "A", "B"]
            frame[columns].to_csv(shuffled / path.name, index=False)

        left = _pipeline(directory, tmp_path, "a")
        right = _pipeline(shuffled, tmp_path, "b")

        assert left["n_nodes"] == right["n_nodes"]
        assert left["couverture"] == pytest.approx(right["couverture"])
        assert left["n_variables"] == right["n_variables"]


class TestNamesAreNotMatchedLoosely:
    def test_a_column_named_like_mach_is_not_confused_with_mach(self, make_lot, tmp_path):
        directory = make_lot(n_shots=3, extra=("Mach_bis",))

        ds = add_derived_columns(
            load_dataset(directory), reference=Reference(length_m=2.5), symmetry=C4V
        )
        specs, _ = build_specs(ds.columns, ds.column_values(), {})

        mach = next(s for s in specs if s.name == "Mach")
        other = next(s for s in specs if s.name == "Mach_bis")
        assert other.auto
        assert other.detection != mach.detection

    def test_a_column_named_like_time_is_not_ignored(self, make_lot, tmp_path):
        directory = make_lot(n_shots=3, extra=("time_2",))

        ds = add_derived_columns(
            load_dataset(directory), reference=Reference(length_m=2.5), symmetry=C4V
        )
        specs, _ = build_specs(ds.columns, ds.column_values(), {})

        assert next(s for s in specs if s.name == "time_2").is_active
        assert not next(s for s in specs if s.name == "time").is_active

    def test_a_column_named_like_a_deflection_is_not_treated_as_one(self, make_lot, tmp_path):
        directory = make_lot(n_shots=3, extra=("dl2",))

        ds = add_derived_columns(
            load_dataset(directory), reference=Reference(length_m=2.5), symmetry=C4V
        )
        specs, _ = build_specs(ds.columns, ds.column_values(), {})

        assert next(s for s in specs if s.name == "dl2").mechanical_range is None


class TestCounts:
    @pytest.mark.parametrize("n_extra", [0, 1, 2, 12])
    def test_any_number_of_generic_columns_produces_a_plan(self, make_lot, tmp_path, n_extra):
        directory = make_lot(n_shots=3, extra=tuple(f"C{i}" for i in range(n_extra)))

        result = _pipeline(directory, tmp_path, "n")

        assert result["n_nodes"] > 0

    def test_adding_a_thirteenth_column_adds_exactly_one(self, make_lot, tmp_path):
        twelve = make_lot(n_shots=2, extra=tuple(f"C{i}" for i in range(12)), name="A")
        thirteen = make_lot(n_shots=2, extra=tuple(f"C{i}" for i in range(13)), name="B")

        assert len(load_dataset(twelve).extra_columns) == 12
        assert len(load_dataset(thirteen).extra_columns) == 13

    def test_thirty_generic_columns_still_go_through_the_cli(self, tmp_path, capsys):
        traj = tmp_path / "TRAJ"
        assert (
            main(
                [
                    "generer",
                    "--sortie",
                    str(traj),
                    "--n-tirs",
                    "3",
                    "--n-parametres",
                    "30",
                ]
            )
            == EXIT_OK
        )
        study = traj / "ETUDE.yaml"
        study.write_text(study.read_text().replace("noeuds_max: 2000", "noeuds_max: 100000"))

        assert main(["inspecter", str(traj)]) == EXIT_OK
        assert main(["doe", str(study), "--methode", "lhs"]) == EXIT_OK
        capsys.readouterr()

        assert len(load_dataset(traj).extra_columns) == 30


class TestSourceVocabulary:
    def test_no_source_file_uses_the_forbidden_vocabulary(self):
        offenders: list[str] = []

        for path in _text_files():
            relative = path.relative_to(RACINE)
            if relative in SELF_REFERENTIAL:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if FORBIDDEN_PATTERN.search(line):
                    offenders.append(f"{path.relative_to(RACINE)}:{number}: {line.strip()}")

        assert not offenders, "vocabulaire proscrit :\n" + "\n".join(offenders)

    def test_no_file_name_uses_the_forbidden_vocabulary(self):
        offenders = [
            str(path.relative_to(RACINE))
            for path in RACINE.rglob("*")
            if path.is_file()
            and ".venv" not in path.parts
            and "__pycache__" not in path.parts
            and FORBIDDEN_PATTERN.search(path.name)
        ]

        assert not offenders

    def test_the_analysis_never_mentions_the_default_column_prefix(self):
        """Là où un codage en dur ferait vraiment des dégâts, « PARA » est absent.

        Le préfixe apparaît légitimement dans le générateur (c'est sa valeur par
        défaut), dans l'aide de la commande et dans les exemples de schéma. Mais
        les couches qui *décident* — maths, moteur, rendu, entrées-sorties — ne
        doivent jamais reconnaître une colonne à son nom.
        """
        offenders: list[str] = []

        for path in (RACINE / "src").rglob("*.py"):
            if path.relative_to(RACINE) in PARA_IS_DOCUMENTED:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "PARA" in line:
                    offenders.append(f"{path.relative_to(RACINE)}:{number}: {line.strip()}")

        assert not offenders, "« PARA » codé en dur :\n" + "\n".join(offenders)

    def test_no_module_compares_a_column_name_to_the_default_prefix(self):
        """Même dans les modules autorisés, « PARA » ne sert jamais de test."""
        comparison = re.compile(r"(==|!=|startswith|in\s+\(|\bmatch\b).{0,20}PARA")
        offenders: list[str] = []

        for path in (RACINE / "src").rglob("*.py"):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if comparison.search(line):
                    offenders.append(f"{path.relative_to(RACINE)}:{number}: {line.strip()}")

        assert not offenders, "« PARA » utilisé comme condition :\n" + "\n".join(offenders)


class TestValuesDecideRoles:
    def test_the_same_values_always_get_the_same_role(self, make_lot, tmp_path):
        rng = np.random.default_rng(4)
        shared = None

        roles = []
        for name in ("PARA1", "QUELCONQUE", "x"):
            directory = make_lot(n_shots=2, extra=(name,), name=f"L{name}", seed=11)
            ds = add_derived_columns(
                load_dataset(directory), reference=Reference(length_m=2.5), symmetry=C4V
            )
            specs, _ = build_specs(ds.columns, ds.column_values(), {})
            spec = next(s for s in specs if s.name == name)
            roles.append((spec.role, spec.scale))
            values = ds.values(name)
            if shared is None:
                shared = values
            else:
                assert np.allclose(values, shared)
        assert rng is not None

        assert len(set(roles)) == 1
