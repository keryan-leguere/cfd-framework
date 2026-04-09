"""Rich console reporter for professional terminal output."""

from __future__ import annotations

from typing import Any, Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


_REGIME_STYLE = {
    "converged": "bold green",
    "periodic": "bold cyan",
    "transient": "bold yellow",
    "diverging": "bold red",
}

_QUALITY_STYLE = {
    "excellent": "green",
    "good": "cyan",
    "acceptable": "yellow",
    "poor": "red",
    "insufficient": "bold red",
}


class ConsoleReporter:
    """Generate professional terminal reports using Rich."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    # ------------------------------------------------------------------
    # Summary table
    # ------------------------------------------------------------------

    def print_summary_table(self, results: dict) -> None:
        """Print the top-level summary table.

        Parameters
        ----------
        results : dict
            Full output of :meth:`AutomaticDetector.run_full_analysis`.
        """
        table = Table(
            title="CFD Statistics Summary",
            title_style="bold white",
            show_lines=True,
            header_style="bold magenta",
        )
        table.add_column("Coefficient", style="bold")
        table.add_column("Regime", justify="center")
        table.add_column("Mean", justify="right")
        table.add_column("Std", justify="right")
        table.add_column("Min", justify="right")
        table.add_column("Max", justify="right")
        table.add_column("Quality", justify="center")

        per_coeff = results.get("per_coefficient", {})
        for name, data in per_coeff.items():
            regime = data.get("regime", {}).get("regime", "?")
            regime_text = Text(regime, style=_REGIME_STYLE.get(regime, ""))
            moments = data.get("moments", {})
            quality = data.get("regime", {}).get("quality_score", 0.0)

            table.add_row(
                name,
                regime_text,
                _fmt(moments.get("mean")),
                _fmt(moments.get("std")),
                _fmt(moments.get("min", moments.get("q25", ""))),
                _fmt(moments.get("max", moments.get("q99", ""))),
                _quality_text(quality),
            )

        self.console.print(table)

    # ------------------------------------------------------------------
    # Convergence panel
    # ------------------------------------------------------------------

    def print_convergence_panel(self, conv_data: dict) -> None:
        """Print a detailed convergence panel with colour-coded status."""
        is_conv = conv_data.get("is_converged", False)
        status_style = "green" if is_conv else "yellow"
        status_label = "CONVERGED" if is_conv else "NOT CONVERGED"

        lines = [
            f"[{status_style}]Status: {status_label}[/]",
            f"Convergence rate    : {conv_data.get('convergence_rate', '?')}",
            f"Plateau iterations  : {conv_data.get('plateau_iterations', '?')}",
            f"Final variance      : {_fmt(conv_data.get('final_variance'))}",
            f"Cauchy criterion    : {_fmt(conv_data.get('cauchy_criterion'))}",
        ]

        self.console.print(Panel("\n".join(lines), title="Convergence", border_style="blue"))

    # ------------------------------------------------------------------
    # Periodicity
    # ------------------------------------------------------------------

    def print_periodicity_analysis(self, period_data: dict) -> None:
        """Print periodicity analysis results."""
        detected = period_data.get("detected", False)
        flag = period_data.get("quality_flag", "?")
        style = _QUALITY_STYLE.get(flag, "")

        lines = [
            f"Detected : {'Yes' if detected else 'No'}",
            f"Period   : {_fmt(period_data.get('period'))}",
            f"Frequency: {_fmt(period_data.get('frequency'))}",
            f"N periods: {period_data.get('n_periods', '?')}",
            f"Quality  : [{style}]{flag}[/]",
            f"Method   : {period_data.get('method', '?')}",
        ]

        self.console.print(Panel("\n".join(lines), title="Periodicity", border_style="cyan"))

    # ------------------------------------------------------------------
    # Moments
    # ------------------------------------------------------------------

    def print_moments_detailed(self, moments: dict) -> None:
        """Print moments table with robust statistics and CI."""
        table = Table(title="Statistical Moments", show_lines=True, header_style="bold magenta")
        table.add_column("Statistic", style="bold")
        table.add_column("Value", justify="right")

        basic = [
            ("Mean", moments.get("mean")),
            ("Std", moments.get("std")),
            ("Variance", moments.get("variance")),
            ("Skewness", moments.get("skewness")),
            ("Kurtosis", moments.get("kurtosis")),
            ("Excess Kurtosis", moments.get("excess_kurtosis")),
        ]
        for label, val in basic:
            if val is not None:
                table.add_row(label, _fmt(val))

        robust = [
            ("Median", moments.get("median")),
            ("MAD", moments.get("mad")),
            ("IQR", moments.get("iqr")),
            ("Q25", moments.get("q25")),
            ("Q75", moments.get("q75")),
            ("Q95", moments.get("q95")),
            ("Trimmed Mean (5%)", moments.get("trimmed_mean_5")),
        ]
        for label, val in robust:
            if val is not None:
                table.add_row(label, _fmt(val))

        ci = moments.get("confidence_intervals", {})
        for key, ci_val in ci.items():
            if isinstance(ci_val, (tuple, list)) and len(ci_val) == 2:
                table.add_row(f"CI {key}", f"[{_fmt(ci_val[0])}, {_fmt(ci_val[1])}]")

        self.console.print(table)

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def print_recommendations(self, recommendations: str | Sequence[str]) -> None:
        """Print expert recommendations with colour coding."""
        if isinstance(recommendations, str):
            recommendations = [recommendations]

        lines: list[str] = []
        for rec in recommendations:
            lower = rec.lower()
            if any(w in lower for w in ("diverging", "error", "fail")):
                lines.append(f"[bold red]✗[/] {rec}")
            elif any(w in lower for w in ("transient", "caution", "low", "moderate")):
                lines.append(f"[bold yellow]![/] {rec}")
            else:
                lines.append(f"[bold green]✓[/] {rec}")

        self.console.print(Panel("\n".join(lines), title="Recommendations", border_style="green"))

    # ------------------------------------------------------------------
    # Full report
    # ------------------------------------------------------------------

    def print_full_report(self, results: dict) -> None:
        """Print the complete analysis report."""
        self.print_summary_table(results)
        self.console.print()

        for name, data in results.get("per_coefficient", {}).items():
            self.console.rule(f"[bold]{name}[/]")
            self.print_convergence_panel(data.get("convergence", {}))
            self.print_periodicity_analysis(data.get("periodicity", {}))
            if data.get("moments"):
                self.print_moments_detailed(data["moments"])
            self.console.print()

        ga = results.get("global_assessment", {})
        rec = ga.get("recommendation", "")
        if rec:
            self.print_recommendations(rec)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _fmt(val: Any) -> str:
    if val is None:
        return "—"
    if isinstance(val, float):
        if abs(val) < 1e-3 or abs(val) > 1e6:
            return f"{val:.6e}"
        return f"{val:.6f}"
    return str(val)


def _quality_text(score: float) -> Text:
    if score >= 90:
        return Text(f"{score:.1f}", style="bold green")
    if score >= 70:
        return Text(f"{score:.1f}", style="cyan")
    if score >= 50:
        return Text(f"{score:.1f}", style="yellow")
    return Text(f"{score:.1f}", style="red")
