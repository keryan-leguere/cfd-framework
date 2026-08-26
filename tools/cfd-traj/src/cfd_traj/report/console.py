"""Rapports Rich, en français.

Règle de composition commune aux cinq rapports : **la réponse d'abord**, les
réserves ensuite, la justification en dernier. Un ingénieur qui lance
``cfd-traj doe`` veut savoir combien de calculs et pour quel coût ; le détail
bande par bande l'intéresse une fois qu'il a ce chiffre, pas avant.

Les nombres sont formatés à la française — virgule décimale, espace fine comme
séparateur de milliers. C'est le seul endroit où cela se fait : les fichiers
écrits par :mod:`cfd_traj.data.plan_io` gardent le point décimal machine.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cfd_traj._compat import zip_strict
from cfd_traj.core.symmetry import CalcConfig, SymmetryGroup, SymmetrySpec, azimuth_levels
from cfd_traj.data.columns import ColumnSpec, Role
from cfd_traj.data.study import Study
from cfd_traj.engine.coverage import CoverageResult
from cfd_traj.engine.doe import DoePlan
from cfd_traj.engine.envelope import Envelope
from cfd_traj.engine.inspect import Inspection

console = Console()

#: Ligne d'un tableau, quel que soit le tableau : « _truncate » ne regarde que
#: le nombre de lignes.
_Row = TypeVar("_Row")

#: Au-delà, les tableaux sont tronqués hors mode verbeux.
MAX_ROWS = 12

#: Espace fine insécable (U+202F) : le séparateur de milliers français. Nommée
#: parce qu'elle est invisible dans le source et indistinguable d'une espace
#: ordinaire à l'œil.
THIN_SPACE = " "

_ROLE_STYLE: dict[Role, str] = {
    Role.PRINCIPAL: "bold cyan",
    Role.CONDITIONNEL: "cyan",
    Role.DISCRET: "magenta",
    Role.MECANIQUE: "yellow",
    Role.IGNORE: "dim",
}

_CONFIG_LABEL: dict[CalcConfig, str] = {
    CalcConfig.AXI_2D: "axisymétrique 2D",
    CalcConfig.SECTEUR_45: "secteur 45°",
    CalcConfig.QUART_90: "quart 90° cyclique",
    CalcConfig.DEMI: "demi-configuration",
    CalcConfig.COMPLETE: "configuration complète",
}

_GROUP_MEANING: dict[SymmetryGroup, str] = {
    SymmetryGroup.CINFV: "corps de révolution : tout plan méridien est un miroir",
    SymmetryGroup.C4V: "cruciforme : axe d'ordre 4 et quatre plans de miroir",
    SymmetryGroup.C4: "axe d'ordre 4 seul : aucun miroir ne survit",
    SymmetryGroup.CS: "un unique plan de miroir",
    SymmetryGroup.C1: "aucune symétrie",
}


def fr(value: float, decimals: int = 2) -> str:
    """Nombre à la française : virgule décimale, espace fine pour les milliers."""
    if value != value:  # NaN
        return "—"
    if value in (float("inf"), float("-inf")):
        return "∞" if value > 0 else "−∞"
    text = f"{value:,.{decimals}f}"
    return text.replace(",", THIN_SPACE).replace(".", ",")


def fr_int(value: float) -> str:
    """Entier à la française."""
    return fr(value, 0)


def pct(value: float, decimals: int = 2) -> str:
    """Pourcentage à la française."""
    return f"{fr(100.0 * value, decimals)} %"


def compact(value: float) -> str:
    """Nombre court, pour les cellules de tableau.

    Un Reynolds à huit chiffres écrit en toutes lettres fait déborder la
    colonne et rend le tableau d'enveloppe illisible ; la notation exposant
    tient sur place et suffit à comparer deux bornes.
    """
    if value != value:
        return "—"
    magnitude = abs(value)
    if magnitude >= 1e5 or (0 < magnitude < 1e-3):
        mantissa, _, exponent = f"{value:.2e}".partition("e")
        return f"{mantissa.replace('.', ',')}e{int(exponent)}"
    return fr(value, 2)


def _notes_panel(notes: Sequence[str], *, title: str = "Avertissements") -> Panel | None:
    """Un panneau jaune, ou rien du tout s'il n'y a rien à dire."""
    if not notes:
        return None
    body = Text()
    for note in notes:
        body.append("• ", style="yellow")
        body.append(f"{note}\n")
    return Panel(body, title=f"[bold yellow]{title}[/]", border_style="yellow")


def _truncate(rows: Sequence[_Row], verbose: bool) -> tuple[Sequence[_Row], int]:
    """Limite un tableau hors mode verbeux, et dit combien de lignes sont cachées."""
    if verbose or len(rows) <= MAX_ROWS:
        return rows, 0
    return rows[:MAX_ROWS], len(rows) - MAX_ROWS


# --- inspection ------------------------------------------------------------


def render_inspection(
    inspection: Inspection, specs: Sequence[ColumnSpec], *, verbose: bool = False
) -> RenderableType:
    """Rapport de la commande ``inspecter``."""
    head = Text()
    head.append(f"{fr_int(inspection.n_shots)} tirs", style="bold")
    head.append(f", {fr_int(inspection.n_rows)} points de vol\n")
    head.append("Mach ", style="dim")
    head.append(f"{fr(inspection.mach_range[0])} → {fr(inspection.mach_range[1])}")
    head.append("     temps ", style="dim")
    head.append(f"{fr(inspection.time_span[0], 1)} → {fr(inspection.time_span[1], 1)} s")
    if inspection.n_dropped_rows:
        head.append(f"\n{fr_int(inspection.n_dropped_rows)} ligne(s) supprimée(s)", style="yellow")

    blocks: list[RenderableType] = [Panel(head, title="[bold]Lot[/]", border_style="blue")]

    table = Table(title="Variables", title_justify="left", header_style="bold")
    for column in ("variable", "rôle", "n", "min", "médiane", "max", "manquantes"):
        table.add_column(column, justify="right" if column != "variable" else "left")
    rows, hidden = _truncate([s for s in inspection.stats if s.role is not Role.IGNORE], verbose)
    for stat in rows:
        table.add_row(
            stat.name,
            Text(str(stat.role), style=_ROLE_STYLE[stat.role]),
            fr_int(stat.count),
            fr(stat.minimum, 3),
            fr(stat.median, 3),
            fr(stat.maximum, 3),
            fr_int(stat.n_nan) if stat.n_nan else "—",
        )
    if hidden:
        table.add_row(Text(f"… et {hidden} autre(s)", style="dim"), *[""] * 6)
    blocks.append(table)

    if inspection.pca is not None:
        pca = inspection.pca
        body = Text()
        body.append("dimension intrinsèque ", style="dim")
        body.append(f"{pca.intrinsic_dimension}", style="bold")
        body.append(f" sur {pca.n_used} variables actives")
        body.append(f"  (seuil {pct(pca.threshold, 0)} de variance)\n", style="dim")
        for i, (ratio, cumulative) in enumerate(
            zip_strict(pca.explained_variance_ratio, pca.cumulative)
        ):
            if i >= 5 and not verbose:
                break
            body.append(
                f"  CP{i + 1} : {pct(float(ratio), 1):>8}   cumulé {pct(float(cumulative), 1)}\n"
            )
        if inspection.dimension_is_reduced:
            body.append(
                "\nLe nuage occupe moins de directions qu'il n'a de variables : "
                "le conditionnement au Mach capture bien les corrélations dominantes.",
                style="green",
            )
        else:
            body.append(
                "\nLa dimension intrinsèque égale le nombre de variables : une corrélation "
                "forte échappe au conditionnement au Mach.",
                style="yellow",
            )
        blocks.append(
            Panel(body, title="[bold]Analyse en composantes principales[/]", border_style="blue")
        )

    pairs = inspection.strongest_pairs(5 if not verbose else 12)
    if pairs:
        table = Table(
            title="Corrélations les plus fortes", title_justify="left", header_style="bold"
        )
        table.add_column("variable")
        table.add_column("variable")
        table.add_column("ρ", justify="right")
        for left, right, rho in pairs:
            table.add_row(left, right, fr(rho, 3))
        blocks.append(table)

    auto = [s for s in specs if s.auto and s.is_active]
    if auto:
        body = Text()
        body.append(
            "Rôles déduits des valeurs, pas déclarés. Vérifiez-les et figez-les "
            "dans la section « parametres » de l'étude :\n\n",
            style="yellow",
        )
        for spec in auto:
            body.append(f"  {spec.name}", style="bold")
            body.append(f" → {spec.role}", style=_ROLE_STYLE[spec.role])
            body.append(f"   {spec.detection}\n", style="dim")
        blocks.append(
            Panel(body, title="[bold yellow]Rôles auto-détectés[/]", border_style="yellow")
        )

    panel = _notes_panel(inspection.consistency, title="Cohérence du lot")
    if panel is not None:
        blocks.append(panel)

    return Group(*blocks)


def suggest_parameters_block(specs: Sequence[ColumnSpec]) -> str:
    """Le bloc ``parametres:`` prêt à coller dans l'étude."""
    lines = ["parametres:"]
    for spec in specs:
        if not spec.is_active:
            continue
        if spec.name == "phi_fold":
            # Ses niveaux viennent du groupe de symétrie, pas d'un choix libre.
            lines.append(
                f"  {spec.name}: {{ role: {spec.role} }}   # niveaux imposés par le groupe"
            )
            continue
        bits = [f"role: {spec.role}", f"niveaux: {spec.n_levels}"]
        if spec.log_scaled:
            bits.append("echelle: log")
        if spec.mechanical_range is not None:
            low, high = spec.mechanical_range
            bits.append(f"plage: [{low:g}, {high:g}]")
        lines.append(f"  {spec.name}: {{ {', '.join(bits)} }}")
    return "\n".join(lines)


# --- symétrie --------------------------------------------------------------


def render_symmetry(symmetry: SymmetrySpec) -> RenderableType:
    """Ce que le groupe déclaré implique — affiché en évidence, car le code ne
    peut pas détecter un groupe déclaré à tort et l'erreur ampute le plan."""
    low, high = symmetry.fundamental_domain_deg
    closing = "]" if symmetry.domain_is_closed else "["
    levels = azimuth_levels(symmetry)

    body = Text()
    body.append(f"groupe {symmetry.group}", style="bold")
    body.append(f"   {_GROUP_MEANING[symmetry.group]}\n\n", style="dim")
    body.append("domaine de φ         ", style="dim")
    body.append(f"[{fr(low, 1)}° , {fr(high, 1)}°{closing}\n")
    body.append("azimuts calculés     ", style="dim")
    body.append(", ".join(f"{fr(x, 1)}°" for x in levels) + "\n")
    body.append("composantes stockées ", style="dim")
    if symmetry.has_mirror:
        body.append("CA, CN, Cm sur les plans de miroir ; les six ailleurs")
    else:
        body.append("les six partout : aucun miroir n'annule les composantes hors plan")
    return Panel(body, title="[bold]Symétrie[/]", border_style="blue")


# --- enveloppe -------------------------------------------------------------


def render_envelope(envelope: Envelope, *, verbose: bool = False) -> RenderableType:
    """Rapport de la commande ``analyser``."""
    blocks: list[RenderableType] = []

    head = Text()
    head.append(f"{len(envelope.bands)} bandes de Mach", style="bold")
    head.append(f"   {'découpage automatique' if envelope.band_set.auto else 'bornes déclarées'}\n")
    head.append("quantiles ", style="dim")
    head.append(f"{pct(envelope.spec.q_low, 1)} / {pct(envelope.spec.q_high, 1)}")
    head.append("     marge ", style="dim")
    head.append(pct(envelope.spec.margin, 0))
    head.append(
        "\n\nLes bornes sont conditionnelles à la bande : c'est ce qui remplace\n", style="dim"
    )
    head.append("l'hyperrectangle min/max par le tube réellement balayé.", style="dim")

    # Les variables mécaniques valent la même chose dans toutes les bandes :
    # les répéter ligne après ligne noierait le tableau qui compte.
    mechanical = [s for s in envelope.specs if s.role is Role.MECANIQUE]
    if mechanical:
        head.append("\n\nplages mécaniques ", style="dim")
        head.append(
            "   ".join(
                f"{s.name} {fr(s.mechanical_range[0], 1)} … {fr(s.mechanical_range[1], 1)}"
                for s in mechanical
                if s.mechanical_range is not None
            )
        )
        head.append("\n(indépendantes de la trajectoire, par construction)", style="dim")
    blocks.append(Panel(head, title="[bold]Enveloppe conditionnelle[/]", border_style="blue"))

    grid_names = [
        s.name
        for s in envelope.specs
        if s.is_active and s.role not in (Role.IGNORE, Role.MECANIQUE)
    ]
    shown = grid_names if verbose else grid_names[:6]

    table = Table(title="Domaine par bande", title_justify="left", header_style="bold")
    table.add_column("bande")
    table.add_column("n", justify="right")
    for name in shown:
        table.add_column(name, justify="right")
    for band in envelope.bands:
        cells = []
        for name in shown:
            variable = band.get(name)
            if variable is None:
                cells.append("—")
            else:
                cells.append(f"{compact(variable.bounds.low)} … {compact(variable.bounds.high)}")
        table.add_row(band.band.label, fr_int(band.n_points), *cells)
    blocks.append(table)

    if len(grid_names) > len(shown):
        blocks.append(
            Text(
                f"… et {len(grid_names) - len(shown)} variable(s) de plus (-v pour tout voir)",
                style="dim",
            )
        )

    warnings = [w for band in envelope.bands for w in band.warnings]
    panel = _notes_panel([*envelope.notes, *warnings])
    if panel is not None:
        blocks.append(panel)

    return Group(*blocks)


# --- plan ------------------------------------------------------------------


def render_plan(plan: DoePlan, *, verbose: bool = False) -> RenderableType:
    """Rapport de la commande ``doe``. La réponse d'abord : combien, à quel coût."""
    head = Text()
    head.append(f"{fr_int(plan.n_nodes)} cas de calcul", style="bold green")
    head.append(f"   méthode « {plan.method} »\n\n", style="dim")
    head.append("coût total           ", style="dim")
    head.append(f"{fr(plan.total_cost, 1)} équivalents configuration complète\n", style="bold")
    head.append("sans les symétries   ", style="dim")
    head.append(f"{fr(plan.naive_cost, 1)}\n")
    head.append("économie             ", style="dim")
    head.append(pct(plan.saving, 1), style="bold green")
    blocks: list[RenderableType] = [
        Panel(head, title="[bold]Plan d'expériences[/]", border_style="green")
    ]

    table = Table(title="Configurations de calcul", title_justify="left", header_style="bold")
    table.add_column("configuration")
    table.add_column("cas", justify="right")
    table.add_column("coût", justify="right")
    breakdown = plan.cost_by_config()
    for config in CalcConfig:
        if config not in breakdown:
            continue
        count, cost = breakdown[config]
        table.add_row(_CONFIG_LABEL[config], fr_int(count), fr(cost, 1))
    blocks.append(table)

    corners = sum(1 for n in plan.nodes if n.is_corner)
    detail = Table(title="Répartition par bande", title_justify="left", header_style="bold")
    for column in ("bande", "Mach", "cas", "coût"):
        detail.add_column(column, justify="right" if column != "bande" else "left")
    rows, hidden = _truncate(plan.envelope.bands, verbose)
    for band in rows:
        nodes = plan.nodes_of_band(band.band.index)
        detail.add_row(
            str(band.band.index),
            band.band.label,
            fr_int(len(nodes)),
            fr(sum(n.relative_cost for n in nodes), 1),
        )
    if hidden:
        detail.add_row(Text(f"… et {hidden} bande(s)", style="dim"), "", "", "")
    blocks.append(detail)

    foot = Text()
    foot.append(f"{fr_int(corners)} nœud(s) sur les coins du domaine conditionnel", style="dim")
    foot.append(
        "\nCe sont eux qui séparent l'interpolation stricte de l'extrapolation "
        "sur les cas dimensionnants.",
        style="dim",
    )
    blocks.append(foot)

    panel = _notes_panel(plan.notes)
    if panel is not None:
        blocks.append(panel)

    return Group(*blocks)


# --- couverture ------------------------------------------------------------


def render_coverage(
    result: CoverageResult, *, worst: int = 10, verbose: bool = False
) -> RenderableType:
    """Rapport de la commande ``couverture``."""
    complete = result.is_complete
    head = Text()
    head.append(pct(result.rate, 2), style="bold green" if complete else "bold yellow")
    head.append(" des points de vol en interpolation stricte\n")
    head.append(f"{fr_int(result.n_inside)} sur {fr_int(result.n_points)} points\n", style="dim")
    if result.n_out_of_bands:
        head.append(
            f"{fr_int(result.n_out_of_bands)} point(s) hors des bandes de Mach\n", style="yellow"
        )
    if result.n_skipped_nan:
        head.append(f"{fr_int(result.n_skipped_nan)} point(s) à valeurs manquantes\n", style="dim")
    if not complete:
        head.append(
            "\nChaque point manquant est un point que la base devra extrapoler.",
            style="yellow",
        )

    blocks: list[RenderableType] = [
        Panel(
            head,
            title="[bold]Couverture[/]",
            border_style="green" if complete else "yellow",
        )
    ]

    table = Table(title="Par bande", title_justify="left", header_style="bold")
    for column in ("bande", "points", "couverts", "taux"):
        table.add_column(column, justify="right" if column != "bande" else "left")
    rows, hidden = _truncate(result.bands, verbose)
    for band in rows:
        table.add_row(
            band.band.label,
            fr_int(band.n_points),
            fr_int(band.n_inside),
            Text(pct(band.rate, 2), style="green" if band.rate >= 1.0 else "yellow"),
        )
    if hidden:
        table.add_row(Text(f"… et {hidden} bande(s)", style="dim"), "", "", "")
    blocks.append(table)

    failures = result.failures_by_variable()
    if failures:
        table = Table(title="Variables fautives", title_justify="left", header_style="bold")
        table.add_column("variable")
        table.add_column("points hors bornes", justify="right")
        for name, count in failures.items():
            table.add_row(name, fr_int(count))
        blocks.append(table)

    if result.offenders:
        shown = min(worst, len(result.offenders))
        heading = (
            "Le point le plus éloigné" if shown == 1 else f"Les {shown} points les plus éloignés"
        )
        table = Table(title=heading, title_justify="left", header_style="bold")
        for column in ("tir", "temps", "Mach", "variable", "valeur", "borne", "côté", "excès"):
            table.add_column(
                column, justify="right" if column not in ("tir", "variable", "côté") else "left"
            )
        for offender in result.offenders[:worst]:
            table.add_row(
                offender.shot,
                fr(offender.time, 1),
                fr(offender.mach, 3),
                offender.variable,
                fr(offender.value, 4),
                fr(offender.bound, 4),
                offender.side,
                fr(offender.excess, 3),
            )
        blocks.append(table)

    if result.mechanical_violations:
        body = Text()
        body.append(
            "Des valeurs de trajectoire sortent de la plage mécanique déclarée. "
            "C'est une erreur du fichier d'étude, pas un défaut de couverture :\n\n",
            style="red",
        )
        for violation in result.mechanical_violations[:worst]:
            body.append(
                f"  {violation.variable} = {fr(violation.value, 3)} "
                f"hors de la borne {fr(violation.bound, 3)} ({violation.shot})\n"
            )
        blocks.append(Panel(body, title="[bold red]Plages mécaniques[/]", border_style="red"))

    panel = _notes_panel(result.notes)
    if panel is not None:
        blocks.append(panel)

    return Group(*blocks)


# --- étude -----------------------------------------------------------------


def render_study(study: Study) -> RenderableType:
    """Résumé d'une étude chargée."""
    body = Text()
    body.append(f"{study.name}\n", style="bold")
    body.append("source               ", style="dim")
    body.append(f"{study.resolved_source()}\n")
    body.append("longueur de référence", style="dim")
    body.append(f" {fr(study.reference.length_m, 3)} m\n")
    body.append("symétrie             ", style="dim")
    body.append(f"{study.symmetry.group}\n")
    if study.delta_t_k:
        body.append("atmosphère           ", style="dim")
        body.append(f"ISA {study.delta_t_k:+g} K\n")
    return Panel(body, title="[bold]Étude[/]", border_style="blue")


def print_report(renderable: RenderableType, *, con: Console | None = None) -> None:
    """Affiche un rapport."""
    (con or console).print(renderable)
