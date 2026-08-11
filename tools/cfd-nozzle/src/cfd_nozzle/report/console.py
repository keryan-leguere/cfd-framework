"""Rich terminal reports, in French.

The audience is a CFD engineer sizing a nozzle or setting up a case, not a
Python developer: the reports lead with the answer (the regime, the thrust) and
keep the intermediate ratios in dim columns beside it.
"""

from __future__ import annotations

import math

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cfd_nozzle.core.gas import GasModel
from cfd_nozzle.core.geometry import NozzleContour
from cfd_nozzle.core.isentropic import IsentropicState
from cfd_nozzle.core.moc import MOCResult
from cfd_nozzle.core.nozzle import CriticalRatios, Nozzle, NozzleState
from cfd_nozzle.core.shocks import NormalShockState, ObliqueShockState, prandtl_meyer
from cfd_nozzle.report import theme

__all__ = [
    "print_contour_report",
    "print_gas_line",
    "print_isentropic_report",
    "print_moc_report",
    "print_normal_shock_report",
    "print_nozzle_report",
    "print_oblique_shock_report",
    "print_prandtl_meyer_report",
]


def _table(title: str) -> Table:
    table = Table(title=title, title_style=theme.TITRE, header_style=theme.ENTETE)
    table.add_column("Grandeur")
    table.add_column("Valeur", justify="right")
    table.add_column("", justify="left")
    return table


def _row(table: Table, name: str, value: str, note: str = "") -> None:
    table.add_row(name, value, f"[{theme.DISCRET}]{note}[/]" if note else "")


def print_gas_line(console: Console, gas: GasModel) -> None:
    """One dim line recalling which gas the numbers rest on."""
    console.print(
        f"[{theme.DISCRET}]Gaz : {gas.name} — γ = {gas.gamma:.4f}, "
        f"R = {gas.r:.2f} J/(kg·K), cp = {gas.cp:.1f} J/(kg·K), "
        f"Γ(γ) = {gas.vandenkerckhove:.5f}[/]"
    )


# --- elementary relations -------------------------------------------------


def print_isentropic_report(console: Console, state: IsentropicState) -> None:
    """Report every isentropic ratio at one Mach number."""
    console.print(
        Panel(
            f"M = [{theme.ACCENT}]{state.mach:.4f}[/]   γ = {state.gamma:.4f}",
            title=f"[{theme.TITRE}]Relations isentropiques[/]",
            border_style="cyan",
        )
    )
    table = _table("Rapports")
    _row(table, "T/T₀", f"{state.t_over_t0:.6f}", f"T₀/T = {1 / state.t_over_t0:.6f}")
    _row(table, "p/p₀", f"{state.p_over_p0:.6e}", f"p₀/p = {1 / state.p_over_p0:.6f}")
    _row(table, "ρ/ρ₀", f"{state.rho_over_rho0:.6f}", f"ρ₀/ρ = {1 / state.rho_over_rho0:.6f}")
    _row(table, "A/A*", f"{state.area_ratio:.6f}", "section sonique de référence")
    _row(table, "M* = V/a*", f"{state.mach_star:.6f}", "reste fini quand M → ∞")
    if state.mu_deg is not None and state.nu_deg is not None:
        _row(table, "μ (angle de Mach)", f"{state.mu_deg:.4f} °", "asin(1/M)")
        _row(table, "ν (Prandtl-Meyer)", f"{state.nu_deg:.4f} °", "détente depuis M = 1")
    console.print(table)


def print_normal_shock_report(
    console: Console, state: NormalShockState, entropy_rise: float | None = None
) -> None:
    """Report the jumps across a normal shock."""
    console.print(
        Panel(
            f"M₁ = [{theme.ACCENT}]{state.m1:.4f}[/]   →   M₂ = "
            f"[{theme.ACCENT}]{state.m2:.4f}[/]   (γ = {state.gamma:.4f})",
            title=f"[{theme.TITRE}]Choc droit[/]",
            border_style="cyan",
        )
    )
    table = _table("Sauts à travers le choc")
    _row(table, "p₂/p₁", f"{state.p_ratio:.6f}", "pression statique")
    _row(table, "ρ₂/ρ₁", f"{state.rho_ratio:.6f}", "borné par (γ+1)/(γ−1)")
    _row(table, "T₂/T₁", f"{state.t_ratio:.6f}", "T₀ est conservée")
    _row(table, "p₀₂/p₀₁", f"{state.p0_ratio:.6f}", "perte de pression d'arrêt")
    if entropy_rise is not None:
        _row(table, "Δs", f"{entropy_rise:.3f} J/(kg·K)", "−R·ln(p₀₂/p₀₁)")
    console.print(table)


def print_oblique_shock_report(
    console: Console, state: ObliqueShockState, theta_max_deg: float
) -> None:
    """Report an attached oblique shock and the detachment margin."""
    console.print(
        Panel(
            f"M₁ = {state.m1:.4f}, déviation θ = {state.theta_deg:.3f}° "
            f"→ choc à β = [{theme.ACCENT}]{state.beta_deg:.3f}°[/] "
            f"(solution {state.solution_label})",
            title=f"[{theme.TITRE}]Choc oblique[/]",
            border_style="cyan",
        )
    )
    table = _table("Choc oblique")
    _row(table, "β (angle du choc)", f"{state.beta_deg:.4f} °")
    _row(table, "θ_max (détachement)", f"{theta_max_deg:.4f} °", f"marge {theta_max_deg - state.theta_deg:.3f} °")
    _row(table, "Mn₁", f"{state.mn1:.6f}", "composante normale amont")
    _row(table, "Mn₂", f"{state.mn2:.6f}", "composante normale aval")
    _row(table, "M₂", f"{state.m2:.6f}", "Mach aval")
    _row(table, "p₂/p₁", f"{state.p_ratio:.6f}")
    _row(table, "ρ₂/ρ₁", f"{state.rho_ratio:.6f}")
    _row(table, "T₂/T₁", f"{state.t_ratio:.6f}")
    _row(table, "p₀₂/p₀₁", f"{state.p0_ratio:.6f}")
    console.print(table)


def print_prandtl_meyer_report(
    console: Console, mach: float, nu_deg: float, mu_deg: float, nu_max_deg: float, gamma: float
) -> None:
    """Report a Prandtl-Meyer expansion state."""
    console.print(
        Panel(
            f"M = [{theme.ACCENT}]{mach:.4f}[/]   ν = [{theme.ACCENT}]{nu_deg:.4f}°[/]   "
            f"(γ = {gamma:.4f})",
            title=f"[{theme.TITRE}]Détente de Prandtl-Meyer[/]",
            border_style="cyan",
        )
    )
    table = _table("Détente")
    _row(table, "ν(M)", f"{nu_deg:.4f} °", "angle de détente depuis M = 1")
    _row(table, "μ(M)", f"{mu_deg:.4f} °", "angle de Mach")
    _row(table, "ν_max", f"{nu_max_deg:.4f} °", "détente vers le vide (M → ∞)")
    _row(table, "marge restante", f"{nu_max_deg - nu_deg:.4f} °")
    console.print(table)


# --- nozzle ---------------------------------------------------------------


def _critical_table(critical: CriticalRatios) -> Table:
    table = Table(
        title="NPR critiques (p₀/pa)", title_style=theme.TITRE, header_style=theme.ENTETE
    )
    table.add_column("Seuil")
    table.add_column("NPR", justify="right")
    table.add_column("Signification")
    table.add_row(
        "NPR₁",
        f"{critical.npr_choked:.4f}",
        f"[{theme.DISCRET}]amorçage du col, sortie subsonique "
        f"(Me = {critical.mach_exit_sub:.4f})[/]",
    )
    table.add_row(
        "NPR₂",
        f"{critical.npr_shock_at_exit:.4f}",
        f"[{theme.DISCRET}]choc droit pile dans le plan de sortie[/]",
    )
    table.add_row(
        "NPR₃",
        f"{critical.npr_design:.4f}",
        f"[{theme.DISCRET}]adaptation, pe = pa (Me = {critical.mach_exit_sup:.4f})[/]",
    )
    return table


def print_nozzle_report(
    console: Console,
    nozzle: Nozzle,
    state: NozzleState,
    *,
    contour: NozzleContour | None = None,
) -> None:
    """Print the full operating-point report of a nozzle."""
    style = theme.STYLE_REGIME.get(state.regime.value, theme.VALEUR)
    console.print(
        Panel(
            f"[{style}]{state.regime.label}[/]\n\n"
            f"[{theme.DISCRET}]NPR = p₀/pa = {state.npr:.4f}   ·   "
            f"col {'sonique' if state.choked else 'NON sonique'}   ·   "
            f"pe/pa = {state.pressure_ratio_exit:.4f}[/]",
            title=f"[{theme.TITRE}]cfd-nozzle — point de fonctionnement[/]",
            border_style="cyan",
        )
    )
    print_gas_line(console, nozzle.gas)

    geometry = _table("Géométrie")
    _row(geometry, "A_col", f"{nozzle.throat_area:.6e} m²", f"D_col = {nozzle.throat_diameter * 1e3:.2f} mm")
    _row(geometry, "A_sortie", f"{nozzle.exit_area:.6e} m²", f"D_e = {nozzle.exit_diameter * 1e3:.2f} mm")
    _row(geometry, "ε = Ae/At", f"{nozzle.eps:.4f}", f"ε optimal ici : {state.area_ratio_opt:.4f}")
    _row(geometry, "η_c*", f"{nozzle.eta_cstar:.4f}", "rendement de combustion")
    _row(geometry, "λ", f"{nozzle.lambda_div:.4f}", "perte par divergence")
    if contour is not None:
        _row(geometry, "contour", contour.label, f"L_divergent = {contour.divergent_length * 1e3:.1f} mm")
    console.print(geometry)

    console.print(_critical_table(nozzle.critical_ratios()))

    if state.mach_shock is not None and state.area_ratio_shock is not None:
        console.print(
            f"[{theme.ATTENTION}]Choc droit interne[/] : M = {state.mach_shock:.4f} "
            f"à A/A_col = {state.area_ratio_shock:.4f}"
        )

    exit_table = _table("État en sortie")
    _row(exit_table, "Mach Me", f"{state.mach_exit:.4f}")
    _row(exit_table, "pression pe", f"{state.p_exit:.1f} Pa", f"{state.p_exit * 1e-5:.4f} bar")
    _row(exit_table, "température Te", f"{state.t_exit:.2f} K")
    _row(exit_table, "masse volumique ρe", f"{state.rho_exit:.5f} kg/m³")
    _row(exit_table, "vitesse Ve", f"{state.v_exit:.2f} m/s", "vitesse gaz-dynamique locale")
    console.print(exit_table)

    perf = _table("Performances")
    _row(perf, "débit ṁ", f"{state.mdot:.5f} kg/s", "= p₀·At/c*")
    _row(perf, "poussée F", f"{state.thrust:.2f} N", f"{state.thrust * 1e-3:.3f} kN")
    _row(perf, "coefficient Cf", f"{state.cf:.4f}", "= F/(p₀·At)")
    _row(perf, "impulsion Isp", f"{state.isp:.2f} s", "= Cf·c*/g₀")
    _row(perf, "vitesse caract. c*", f"{state.c_star:.2f} m/s", "= η_c*·√(R·T₀)/Γ")
    _row(perf, "vitesse éjection éq.", f"{state.v_effective:.2f} m/s", "= F/ṁ")
    console.print(perf)

    for warning in state.warnings:
        console.print(f"[{theme.ATTENTION}]![/] [{theme.DISCRET}]{warning}[/]")


def print_contour_report(console: Console, contour: NozzleContour) -> None:
    """Print the geometric summary of a generated contour."""
    table = Table(
        title=f"Contour — {contour.label}", title_style=theme.TITRE, header_style=theme.ENTETE_ALT
    )
    table.add_column("Grandeur")
    table.add_column("Valeur", justify="right")
    table.add_row("R_col", f"{contour.throat_radius * 1e3:.3f} mm")
    table.add_row("R_sortie", f"{contour.exit_radius * 1e3:.3f} mm")
    table.add_row("ε = Ae/At", f"{contour.area_ratio:.4f}")
    table.add_row("L_divergent", f"{contour.divergent_length * 1e3:.3f} mm")
    table.add_row("λ (divergence)", f"{contour.divergence_lambda:.4f}")
    if contour.theta_n_deg is not None and contour.theta_e_deg is not None:
        table.add_row("θn / θe", f"{contour.theta_n_deg:.2f}° / {contour.theta_e_deg:.2f}°")
    console.print(table)


def print_moc_report(console: Console, result: MOCResult) -> None:
    """Print the summary of a method-of-characteristics design."""
    error_pct = 100.0 * result.area_ratio_error
    style = theme.OK if error_pct < 0.5 else theme.ATTENTION
    console.print(
        Panel(
            f"Tuyère [{theme.ACCENT}]{result.label}[/] à longueur minimale — "
            f"M_sortie = [{theme.ACCENT}]{result.mach_exit:.4f}[/]",
            title=f"[{theme.TITRE}]Méthode des caractéristiques[/]",
            border_style="cyan",
        )
    )
    table = _table("Résultat")
    nu_half_deg = 0.5 * math.degrees(prandtl_meyer(result.mach_exit, result.gamma))
    _row(table, "θ_max au col", f"{result.theta_max_deg:.4f} °", "détente centrée au coin")
    _row(
        table,
        "ν_e / 2",
        f"{nu_half_deg:.4f} °",
        "θ_max exact en plan" if not result.axisymmetric else "borne haute (valeur plane)",
    )
    _row(table, "caractéristiques", f"{result.n_char}", f"{result.n_transition} lignes de redressement")
    _row(table, "y_col", f"{result.y_throat:.6f}", "unité de longueur")
    _row(table, "y_sortie", f"{result.y_exit:.6f}")
    _row(table, "longueur", f"{result.length:.6f}", "en unités de y_col")
    _row(table, "ε obtenu", f"{result.area_ratio:.6f}")
    _row(table, "ε théorique", f"{result.area_ratio_theory:.6f}", "A/A*(M_sortie)")
    console.print(table)
    console.print(
        f"[{style}]Écart au ε théorique : {error_pct:.3f} %[/] "
        f"[{theme.DISCRET}]— c'est le contrôle de cohérence du tracé.[/]"
    )
