"""Rich terminal report for a single atmospheric point, in French.

Aeronautical units lead (feet, knots), with the SI value shown in a dim column
beside them. The audience is a flight-mechanics / CFD engineer.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cfd_atm.core.airspeed import AirspeedSet
from cfd_atm.core.atmosphere import AtmosphereState
from cfd_atm.report import units


def _alt_row(table: Table, name: str, metres: float) -> None:
    table.add_row(
        name,
        f"{units.metres_to_feet(metres):,.0f} ft",
        f"[dim]{metres:,.1f} m[/]",
    )


def _speed_row(table: Table, name: str, mps: float) -> None:
    table.add_row(
        name,
        f"{units.mps_to_knots(mps):,.1f} kt",
        f"[dim]{mps:,.2f} m/s[/]",
    )


def print_point_report(
    console: Console,
    state: AtmosphereState,
    *,
    model_label: str,
    entry: str,
    speeds: AirspeedSet | None = None,
) -> None:
    """Print the full report for a resolved atmospheric point."""
    console.print(
        Panel(
            f"Modèle [bold]{model_label}[/] — entrée : [bold]{entry}[/]",
            title="[bold cyan]cfd-atm — point atmosphérique[/]",
            border_style="cyan",
        )
    )

    alt = Table(title="Altitudes équivalentes", title_style="bold", show_edge=True)
    alt.add_column("Nature")
    alt.add_column("Aéro", justify="right")
    alt.add_column("SI", justify="right")
    _alt_row(alt, "géométrique z", state.z)
    _alt_row(alt, "géopotentielle H", state.h)
    _alt_row(alt, "pression zp", state.zp)
    _alt_row(alt, "densité zρ", state.zrho)
    console.print(alt)

    air = Table(title="Conditions de l'air et grandeurs dérivées", title_style="bold")
    air.add_column("Grandeur")
    air.add_column("Valeur", justify="right")
    air.add_row("température T", f"{state.t:,.2f} K  [dim]({state.t - 273.15:,.2f} °C)[/]")
    air.add_row("pression p", f"{state.p:,.1f} Pa  [dim]({state.p / 100:,.2f} hPa)[/]")
    air.add_row("densité ρ", f"{state.rho:,.4f} kg/m³")
    air.add_row("vitesse du son a", f"{state.a:,.2f} m/s  [dim]({units.mps_to_knots(state.a):,.1f} kt)[/]")
    air.add_row("viscosité dyn. μ", f"{state.mu:,.3e} Pa·s")
    air.add_row("viscosité cin. ν", f"{state.nu:,.3e} m²/s")
    air.add_row("θ = T/T₀", f"{state.theta:,.4f}")
    air.add_row("δ = p/p₀", f"{state.delta:,.4f}")
    air.add_row("σ = ρ/ρ₀", f"{state.sigma:,.4f}")
    console.print(air)

    if speeds is not None:
        spd = Table(title="Grandeurs de vitesse", title_style="bold")
        spd.add_column("Grandeur")
        spd.add_column("Aéro", justify="right")
        spd.add_column("SI", justify="right")
        spd.add_row("Mach M", f"{speeds.mach:,.4f}", "[dim]–[/]")
        _speed_row(spd, "conventionnelle Vc", speeds.cas)
        _speed_row(spd, "équivalente EAS", speeds.eas)
        _speed_row(spd, "vraie TAS", speeds.tas)
        spd.add_row("pression dyn. q", f"{speeds.q / 100:,.2f} hPa", f"[dim]{speeds.q:,.1f} Pa[/]")
        regime = "supersonique" if speeds.mach > 1.0 else "subsonique"
        console.print(spd)
        console.print(f"[dim]Régime : {regime}.[/]")
