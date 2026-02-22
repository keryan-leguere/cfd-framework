"""Tests for CLI parsing helpers."""

import pytest

from cfd_perf.cli.parsing import parse_duration_hours


class TestParseDurationHours:
    def test_hours(self) -> None:
        assert parse_duration_hours("6h") == pytest.approx(6.0)

    def test_minutes(self) -> None:
        assert parse_duration_hours("90m") == pytest.approx(1.5)

    def test_seconds(self) -> None:
        assert parse_duration_hours("3600s") == pytest.approx(1.0)

    def test_fractional(self) -> None:
        assert parse_duration_hours("1.5h") == pytest.approx(1.5)

    def test_case_insensitive(self) -> None:
        assert parse_duration_hours("6H") == pytest.approx(6.0)
        assert parse_duration_hours("90M") == pytest.approx(1.5)

    def test_whitespace(self) -> None:
        assert parse_duration_hours("  6h  ") == pytest.approx(6.0)

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration_hours("six hours")

    def test_no_unit_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration_hours("6")
