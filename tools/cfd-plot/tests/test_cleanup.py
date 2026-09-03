"""Tests for ``clean_figure_dir`` — the pre-run wipe of a generated tree."""

from __future__ import annotations

from pathlib import Path

import pytest

from cfd_plot import FIGURE_SUFFIXES, clean_figure_dir
from cfd_plot.cleanup import CleanReport


def _tree(root: Path) -> Path:
    """A miniature batch output tree with one non-figure file in it."""
    (root / "ALPHA_POLAR" / "M_0.8" / "Z_8000").mkdir(parents=True)
    (root / "ALPHA_POLAR" / "M_0.8" / "Z_8000" / "CN_vs_alpha.svg").write_text("svg")
    (root / "ALPHA_POLAR" / "M_0.8" / "Z_8000" / "CA_vs_alpha.png").write_bytes(b"png")
    (root / "BETA_POLAR").mkdir()
    (root / "BETA_POLAR" / "CN_vs_beta.pdf").write_bytes(b"pdf")
    (root / "notes.md").write_text("kept")
    return root


class TestFiguresMode:
    def test_removes_figures_and_keeps_the_rest(self, tmp_path: Path) -> None:
        root = _tree(tmp_path / "FIGURE")
        report = clean_figure_dir(root)

        assert report.n_files == 3
        assert not list(root.rglob("*.svg"))
        assert (root / "notes.md").read_text() == "kept"
        assert [p.name for p in report.kept_files] == ["notes.md"]

    def test_prunes_the_directories_left_empty(self, tmp_path: Path) -> None:
        root = _tree(tmp_path / "FIGURE")
        report = clean_figure_dir(root)

        assert not (root / "ALPHA_POLAR").exists()
        assert not (root / "BETA_POLAR").exists()
        assert {p.name for p in report.removed_dirs} == {"ALPHA_POLAR", "M_0.8", "Z_8000", "BETA_POLAR"}

    def test_keeps_the_root_itself(self, tmp_path: Path) -> None:
        """The caller is about to write into it."""
        root = _tree(tmp_path / "FIGURE")
        (root / "notes.md").unlink()
        clean_figure_dir(root)
        assert root.is_dir()

    def test_keeps_a_directory_holding_a_non_figure(self, tmp_path: Path) -> None:
        root = _tree(tmp_path / "FIGURE")
        (root / "ALPHA_POLAR" / "M_0.8" / "Z_8000" / "raw.csv").write_text("x,y")
        clean_figure_dir(root)
        assert (root / "ALPHA_POLAR" / "M_0.8" / "Z_8000" / "raw.csv").exists()

    def test_custom_suffixes_leave_the_others_alone(self, tmp_path: Path) -> None:
        root = _tree(tmp_path / "FIGURE")
        report = clean_figure_dir(root, suffixes=["svg"])

        assert [p.suffix for p in report.removed_files] == [".svg"]
        assert (root / "ALPHA_POLAR" / "M_0.8" / "Z_8000" / "CA_vs_alpha.png").exists()

    def test_suffix_matching_ignores_case_and_leading_dot(self, tmp_path: Path) -> None:
        root = tmp_path / "FIGURE"
        root.mkdir()
        (root / "a.SVG").write_text("svg")
        report = clean_figure_dir(root, suffixes=[".svg"])
        assert report.n_files == 1

    def test_empty_suffixes_is_a_mistake(self, tmp_path: Path) -> None:
        root = tmp_path / "FIGURE"
        root.mkdir()
        with pytest.raises(ValueError, match="at least one extension"):
            clean_figure_dir(root, suffixes=[])


class TestDryRun:
    def test_reports_without_deleting(self, tmp_path: Path) -> None:
        root = _tree(tmp_path / "FIGURE")
        report = clean_figure_dir(root, dry_run=True)

        assert report.n_files == 3
        assert report.dry_run is True
        assert (root / "ALPHA_POLAR" / "M_0.8" / "Z_8000" / "CN_vs_alpha.svg").exists()

    def test_counts_directories_as_if_the_files_were_gone(self, tmp_path: Path) -> None:
        """A dry run that reported zero pruned directories would be a lie: the
        real run empties them."""
        root = _tree(tmp_path / "FIGURE")
        dry = clean_figure_dir(root, dry_run=True)
        wet = clean_figure_dir(root)

        assert {p.name for p in dry.removed_dirs} == {p.name for p in wet.removed_dirs}

    def test_all_mode_dry_run_keeps_the_tree(self, tmp_path: Path) -> None:
        root = _tree(tmp_path / "FIGURE")
        report = clean_figure_dir(root, mode="all", dry_run=True)
        assert root.exists()
        assert report.mode == "all"


class TestAllMode:
    def test_removes_the_whole_tree_including_non_figures(self, tmp_path: Path) -> None:
        root = _tree(tmp_path / "FIGURE")
        clean_figure_dir(root, mode="all")
        assert not root.exists()


class TestMissingAndOddTargets:
    def test_missing_directory_is_not_an_error(self, tmp_path: Path) -> None:
        report = clean_figure_dir(tmp_path / "nope")
        assert report.existed is False
        assert report.n_files == 0
        assert "does not exist" in report.summary()

    def test_a_file_target_is_refused(self, tmp_path: Path) -> None:
        target = tmp_path / "figure.svg"
        target.write_text("svg")
        with pytest.raises(NotADirectoryError):
            clean_figure_dir(target)


class TestGuards:
    """``output_base`` is usually assembled from variables; an empty one lands
    on ``/`` or ``$HOME``, where ``mode='all'`` is unrecoverable."""

    def test_refuses_the_filesystem_root(self) -> None:
        with pytest.raises(ValueError, match="filesystem root"):
            clean_figure_dir("/", mode="all")

    def test_refuses_the_home_directory(self) -> None:
        with pytest.raises(ValueError, match="home directory"):
            clean_figure_dir(Path.home(), mode="all")

    def test_refuses_a_top_level_directory(self) -> None:
        with pytest.raises(ValueError, match="top-level"):
            clean_figure_dir("/usr")

    def test_refuses_a_git_repository_root(self, tmp_path: Path) -> None:
        root = tmp_path / "project"
        (root / ".git").mkdir(parents=True)
        with pytest.raises(ValueError, match="git repository"):
            clean_figure_dir(root, mode="all")

    def test_a_figure_directory_inside_a_repo_is_fine(self, tmp_path: Path) -> None:
        repo = tmp_path / "project"
        (repo / ".git").mkdir(parents=True)
        figures = repo / "FIGURE"
        figures.mkdir()
        (figures / "a.svg").write_text("svg")
        assert clean_figure_dir(figures).n_files == 1


class TestModeArgument:
    def test_true_means_figures(self, tmp_path: Path) -> None:
        root = _tree(tmp_path / "FIGURE")
        assert clean_figure_dir(root, mode=True).mode == "figures"

    def test_false_is_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "FIGURE"
        root.mkdir()
        with pytest.raises(ValueError, match="do not call"):
            clean_figure_dir(root, mode=False)

    def test_unknown_mode_is_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "FIGURE"
        root.mkdir()
        with pytest.raises(ValueError, match="mode must be one of"):
            clean_figure_dir(root, mode="nuke")


class TestReport:
    def test_summary_mentions_the_counts(self, tmp_path: Path) -> None:
        root = _tree(tmp_path / "FIGURE")
        summary = clean_figure_dir(root).summary()
        assert "3 file(s)" in summary
        assert "4 empty directories" in summary
        assert "kept 1 non-figure file(s)" in summary

    def test_summary_says_directory_when_there_is_one(self, tmp_path: Path) -> None:
        root = tmp_path / "FIGURE"
        (root / "P").mkdir(parents=True)
        (root / "P" / "a.svg").write_text("svg")
        assert "1 empty directory" in clean_figure_dir(root).summary()

    def test_summary_says_would_remove_on_a_dry_run(self, tmp_path: Path) -> None:
        root = _tree(tmp_path / "FIGURE")
        assert "would remove" in clean_figure_dir(root, dry_run=True).summary()

    def test_report_is_a_frozen_dataclass(self, tmp_path: Path) -> None:
        root = _tree(tmp_path / "FIGURE")
        report = clean_figure_dir(root)
        assert isinstance(report, CleanReport)
        with pytest.raises(AttributeError):
            report.mode = "all"  # type: ignore[misc]


def test_every_save_figure_format_is_covered() -> None:
    """A format cfd-plot can write but cleanup does not know about is a file
    that survives the wipe and pollutes the next study."""
    assert {".png", ".svg", ".pdf", ".emf"} <= FIGURE_SUFFIXES
