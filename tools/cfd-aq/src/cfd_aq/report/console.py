"""Rich terminal reports, in French.

The audience is a CFD or structures engineer costing a manufacturing
tolerance, not a Python developer: the reports lead with the answer — the drag
increment — and keep h⁺, the drag ratio and the shape factors in dim columns
beside it, because those are what one checks when the answer looks wrong.

Extrapolations outside the measured domain are printed as a panel, not hidden
in a footnote: a correlation held constant past M = 2.8 still returns a
number, and the number is only as good as the reader's awareness of that.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cfd_aq.core.couche_limite import CoucheLimite, EtatLocal
from cfd_aq.core.marches import Avertissement, TypeAsperite
from cfd_aq.core.trainee import Asperite, ResultatTrainee
from cfd_aq.report import theme

__all__ = [
    "afficher_asperite",
    "afficher_avertissements",
    "afficher_bilan",
    "afficher_couche_limite",
    "afficher_ecoulement",
    "afficher_paquets",
    "afficher_ratios",
]

_LIBELLE_TYPE = {
    TypeAsperite.MONTANTE: "marche montante",
    TypeAsperite.DESCENDANTE: "marche descendante",
    TypeAsperite.ARETE: "arête",
}


def _tableau(titre: str, entete: str | None = None) -> Table:
    table = Table(
        title=titre,
        title_style=theme.TITRE,
        header_style=entete or theme.ENTETE,
    )
    table.add_column("Grandeur")
    table.add_column("Valeur", justify="right")
    table.add_column("", justify="left")
    return table


def _ligne(table: Table, nom: str, valeur: str, note: str = "") -> None:
    table.add_row(nom, valeur, f"[{theme.DISCRET}]{note}[/]" if note else "")


def afficher_paquets(console: Console) -> None:
    """One dim line naming the sibling packages actually in use.

    cfd-aq degrades gracefully without ``cfd-atm`` and ``cfd-plot``, which
    means the same command can produce slightly different capability sets on
    two machines. Saying so costs one line and removes the doubt.
    """
    from cfd_aq.core.atmosphere import HAS_CFD_ATM
    from cfd_aq.report._plotting_lib import HAS_PLOTTING

    morceaux = [
        f"atmosphère : {'cfd-atm' if HAS_CFD_ATM else 'ISA de repli (cfd-atm absent)'}",
        f"figures : {'cfd-plot' if HAS_PLOTTING else 'matplotlib (cfd-plot absent)'}",
    ]
    console.print(f"[{theme.DISCRET}]{'   —   '.join(morceaux)}[/]")


def afficher_ecoulement(console: Console, etat: EtatLocal) -> None:
    """The local flow state the correlations are evaluated at."""
    console.print(
        Panel(
            f"M = [{theme.ACCENT}]{etat.mach:.4f}[/]   "
            f"T = {etat.temperature:.2f} K   p = {etat.pression:.1f} Pa",
            title=f"[{theme.TITRE}]Écoulement local (bord de couche limite)[/]",
            border_style="cyan",
        )
    )
    table = _tableau("Conditions")
    _ligne(table, "u_e", f"{etat.vitesse:.2f} m/s", f"a = {etat.celerite:.2f} m/s")
    _ligne(table, "ρ_e", f"{etat.masse_volumique:.5f} kg/m³")
    _ligne(table, "q_e", f"{etat.pression_dynamique:.1f} Pa", "½ρ_e·u_e²")
    _ligne(table, "μ_e", f"{etat.viscosite:.4e} Pa·s", "Sutherland")
    console.print(table)


def afficher_couche_limite(console: Console, couche_limite: CoucheLimite) -> None:
    """The undisturbed boundary layer the excrescence is immersed in."""
    table = _tableau("Couche limite non perturbée", theme.ENTETE_ALT)
    _ligne(table, "C_fe", f"{couche_limite.cf:.6f}", "τ_w/q_e")
    _ligne(table, "τ_w", f"{couche_limite.cisaillement_paroi:.3f} Pa")
    _ligne(table, "u_τ", f"{couche_limite.vitesse_frottement:.3f} m/s", "√(τ_w/ρ_w)")
    _ligne(table, "T_w", f"{couche_limite.temperature_paroi:.2f} K", "paroi adiabatique par défaut")
    _ligne(table, "ν_w", f"{couche_limite.viscosite_cinematique_paroi:.4e} m²/s")
    if couche_limite.epaisseur is not None:
        _ligne(table, "δ", f"{couche_limite.epaisseur * 1e3:.2f} mm", "plaque plane, 1/7")
    console.print(table)


def afficher_asperite(
    console: Console,
    nom: str,
    asperite: Asperite,
    resultat: ResultatTrainee,
) -> None:
    """One excrescence: geometry, correlation, drag."""
    console.print(
        Panel(
            f"ΔD = [{theme.ACCENT}]{resultat.trainee:.3f} N[/]"
            + (
                f"   ΔCx = [{theme.ACCENT}]{resultat.delta_cx:.4e}[/]"
                if resultat.delta_cx is not None
                else ""
            ),
            title=f"[{theme.TITRE}]{nom} — {_LIBELLE_TYPE[asperite.type_asperite]}[/]",
            border_style="cyan",
        )
    )
    table = _tableau("Géométrie et corrélation")
    _ligne(table, "h", f"{asperite.hauteur * 1e3:.3f} mm")
    _ligne(table, "b", f"{asperite.envergure:.3f} m", f"f_e = {asperite.aire_frontale:.4e} m²")
    if asperite.type_asperite is TypeAsperite.ARETE:
        _ligne(table, "t/h", f"{asperite.t_sur_h:.3f}", "épaisseur de l'arête")
    _ligne(table, "h⁺", f"{resultat.h_plus:.1f}", "u_τ·h/ν_w")
    if resultat.immersion is not None:
        _ligne(table, "h/δ", f"{resultat.immersion:.4f}", "immersion dans la couche limite")
    _ligne(table, "CDe/Cfe", f"{resultat.cde_sur_cfe:.1f}", "AGARD-AG-264, §4.3")
    if resultat.facteur_forme != 1.0:
        notes: list[str] = []
        if asperite.rayon_sur_h > 0.0:
            notes.append(f"r/h = {asperite.rayon_sur_h:g}")
        if asperite.angle_chanfrein < 90.0:
            notes.append(f"θ = {asperite.angle_chanfrein:g}°")
        if asperite.angle_derapage < 90.0:
            notes.append(f"α = {asperite.angle_derapage:g}°")
        _ligne(table, "facteur de forme", f"{resultat.facteur_forme:.4f}", ", ".join(notes))
    _ligne(table, "CDe", f"{resultat.cde:.5f}", "ΔD/(q_e·f_e)")
    _ligne(table, "ΔD", f"{resultat.trainee:.4f} N")
    if resultat.delta_cx is not None:
        _ligne(
            table,
            "ΔCx",
            f"{resultat.delta_cx:.4e}",
            f"sur S_ref = {resultat.surface_reference:g} m²",
        )
    console.print(table)
    afficher_avertissements(console, resultat.avertissements)


def afficher_avertissements(console: Console, avertissements: Sequence[Avertissement]) -> None:
    """Print the extrapolations, or nothing when there are none."""
    if not avertissements:
        return
    corps = "\n".join(f"• {a.message}" for a in avertissements)
    console.print(
        Panel(
            corps,
            title=f"[{theme.ATTENTION}]Hors du domaine mesuré[/]",
            border_style="yellow",
        )
    )


def afficher_bilan(
    console: Console,
    resultats: Iterable[tuple[str, ResultatTrainee]],
    surface_reference: float | None = None,
) -> None:
    """Totals over every excrescence of a case."""
    lignes = list(resultats)
    if not lignes:
        return
    table = Table(
        title="Bilan",
        title_style=theme.TITRE,
        header_style=theme.ENTETE,
    )
    table.add_column("Aspérité")
    table.add_column("h⁺", justify="right")
    table.add_column("CDe/Cfe", justify="right")
    table.add_column("forme", justify="right")
    table.add_column("ΔD [N]", justify="right")
    if surface_reference is not None:
        table.add_column("ΔCx", justify="right")

    total = 0.0
    for nom, resultat in lignes:
        total += resultat.trainee
        valeurs = [
            nom,
            f"{resultat.h_plus:.0f}",
            f"{resultat.cde_sur_cfe:.1f}",
            f"{resultat.facteur_forme:.3f}",
            f"{resultat.trainee:.3f}",
        ]
        if surface_reference is not None:
            valeurs.append(f"{resultat.delta_cx:.3e}" if resultat.delta_cx is not None else "—")
        table.add_row(*valeurs)

    totaux = ["Total", "", "", "", f"[{theme.ACCENT}]{total:.3f}[/]"]
    if surface_reference is not None:
        cx_total = sum(r.delta_cx or 0.0 for _, r in lignes)
        totaux.append(f"[{theme.ACCENT}]{cx_total:.3e}[/]")
    table.add_section()
    table.add_row(*totaux)
    console.print(table)


def afficher_ratios(
    console: Console,
    h_plus: float,
    mach: float,
    ratios: Sequence[tuple[str, float]],
) -> None:
    """Bare drag ratios at one (h⁺, M) point, for the ``ratio`` subcommand."""
    console.print(
        Panel(
            f"h⁺ = [{theme.ACCENT}]{h_plus:g}[/]   M = [{theme.ACCENT}]{mach:g}[/]",
            title=f"[{theme.TITRE}]Rapport de traînée CDe/Cfe[/]",
            border_style="cyan",
        )
    )
    table = _tableau("Aspérités")
    for nom, valeur in ratios:
        _ligne(table, nom, f"{valeur:.1f}")
    console.print(table)
