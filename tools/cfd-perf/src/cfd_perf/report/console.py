"""Rapport terminal Rich (en français).

Le rapport est ordonné comme un lecteur en a besoin : la réponse d'abord, puis
les réserves qui la qualifient, puis les détails qui la justifient. Un outil de
dimensionnement qui enterre sa recommandation sous un mur de lignes candidates
fait faire le travail deux fois.
"""

from __future__ import annotations

from rich.box import ROUNDED, SIMPLE_HEAD
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from cfd_perf.core.model import ScalingModel
from cfd_perf.data.pilot import PilotSeries
from cfd_perf.data.study import Study
from cfd_perf.engine.recommend import Candidate, Recommendation, Strategy

console = Console()

_QUALITY_STYLE = {
    "excellent": "bold green",
    "good": "green",
    "marginal": "yellow",
    "poor": "bold red",
}

_VERDICT_FR = {
    "excellent": "excellent",
    "good": "bon",
    "marginal": "limite",
    "poor": "mauvais",
}

_STRATEGY_FR = {
    Strategy.EFFICIENCY: "efficacité",
    Strategy.DEADLINE: "échéance",
    Strategy.FASTEST: "le plus rapide",
}

_STRATEGY_BLURB = {
    Strategy.EFFICIENCY: "le plus de cœurs sans gaspiller l'allocation",
    Strategy.DEADLINE: "le moins de cœurs qui tiennent l'échéance",
    Strategy.FASTEST: "durée minimale, coût ignoré",
}

_VIOLATION_LABEL = {
    "cells_per_core": "trop peu de mailles/cœur",
    "ram_per_core": "RAM/cœur insuffisante",
    "node_ram": "dépasse la RAM du nœud",
    "max_nodes": "dépasse la limite de nœuds",
    "walltime": "dépasse la limite de temps",
    "core_hours": "dépasse le budget h·cœur",
}

_MEM_SOURCE_FR = {
    "measured (pilot)": "mesurée (pilote)",
    "user": "utilisateur",
    "unknown": "inconnue",
}


# ---------------------------------------------------------------------------
# Formatage français des nombres
# ---------------------------------------------------------------------------


def _fr(x: float, decimals: int = 1) -> str:
    """Nombre au format français : virgule décimale, espace pour les milliers."""
    s = f"{x:,.{decimals}f}"
    int_part, _, dec_part = s.partition(".")
    int_part = int_part.replace(",", " ")
    return f"{int_part},{dec_part}" if dec_part else int_part


def _fr_int(x: float) -> str:
    return f"{round(x):,}".replace(",", " ")


def _pct(frac: float, decimals: int = 0) -> str:
    return f"{_fr(frac * 100, decimals)} %"


def format_duration(hours: float) -> str:
    """Durée lisible : '18 s', '30 min', '6,4 h', '2 j 3 h'."""
    if hours < 1 / 60:
        return f"{hours * 3600:.0f} s"
    if hours < 1:
        return f"{hours * 60:.0f} min"
    if hours < 48:
        return f"{_fr(hours, 1)} h"
    days = int(hours // 24)
    rest = hours - days * 24
    return f"{days} j {rest:.0f} h"


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def render_answer(rec: Recommendation) -> Panel:
    """L'essentiel : le nombre de cœurs à utiliser, et ce qu'il coûte."""
    if rec.choice is None:
        return Panel(
            Text.from_markup(
                "[bold red]Aucune configuration réalisable.[/]\n\n"
                "Tous les nombres de cœurs de la plage de recherche violent une "
                "contrainte matérielle. Le tableau ci-dessous indique laquelle ; "
                "relâchez la contrainte bloquante ou élargissez la recherche.",
            ),
            title="[bold]Réponse[/]",
            border_style="red",
            box=ROUNDED,
        )

    c = rec.choice
    cpn = rec.machine.cores_per_node

    headline = Text()
    headline.append("Lancer sur ", style="dim")
    headline.append(f"{c.cores} cœurs", style="bold green")
    if cpn > 1:
        headline.append(f"  =  {c.nodes} nœuds de {cpn} cœurs", style="green")

    facts = Table.grid(padding=(0, 2))
    facts.add_column(style="dim", justify="right")
    facts.add_column()
    facts.add_row("Durée", f"[bold]{format_duration(c.runtime_hours)}[/]")
    facts.add_row("Coût", f"{_fr_int(c.core_hours)} h·cœur")
    facts.add_row("Accélération", f"{_fr(c.speedup, 1)}× vs {rec.model.ref_cores} cœurs")
    facts.add_row("Efficacité", f"{_pct(c.efficiency)}  ({_pct(c.efficiency_loss)} perdu)")
    facts.add_row("Charge", f"{_fr_int(c.cells_per_core)} mailles/cœur")
    if c.ram_per_core_gb is not None:
        facts.add_row("Mémoire", f"{_fr(c.ram_per_core_gb, 2)} Go/cœur")

    body = Group(headline, Text(), facts)
    return Panel(
        body,
        title=f"[bold]Réponse[/]  [dim]({_STRATEGY_FR[rec.strategy]} : "
        f"{_STRATEGY_BLURB[rec.strategy]})[/]",
        border_style="green",
        box=ROUNDED,
    )


def render_notes(rec: Recommendation) -> Panel | None:
    """Réserves qui qualifient la réponse. Juste sous elle, jamais enterrées."""
    items = list(rec.notes)
    if not items:
        return None
    body = Text()
    for i, note in enumerate(items):
        if i:
            body.append("\n")
        body.append("! ", style="bold yellow")
        body.append(note)
    return Panel(body, title="[bold]À lire[/]", border_style="yellow", box=ROUNDED)


def render_alternatives(rec: Recommendation) -> Table | None:
    """Ce que les autres stratégies auraient choisi, pour comparaison."""
    if rec.choice is None:
        return None

    rows: list[tuple[str, Candidate]] = []
    seen = {rec.choice.cores}
    for label, cand in (("le plus rapide", rec.fastest), ("le moins cher", rec.cheapest)):
        if cand is not None and cand.cores not in seen:
            rows.append((label, cand))
            seen.add(cand.cores)
    if not rows:
        return None

    table = Table(
        title="[bold]Alternatives[/]",
        box=SIMPLE_HEAD,
        header_style="bold cyan",
        title_justify="left",
        pad_edge=False,
    )
    table.add_column("Option")
    table.add_column("Cœurs", justify="right")
    table.add_column("Durée", justify="right")
    table.add_column("Coût", justify="right")
    table.add_column("Eff.", justify="right")
    table.add_column("vs recommandé", justify="left")

    ref = rec.choice
    table.add_row(
        "[bold green]recommandé[/]",
        str(ref.cores),
        format_duration(ref.runtime_hours),
        f"{_fr_int(ref.core_hours)} h·cœur",
        _pct(ref.efficiency),
        "[dim]--[/]",
    )
    for label, cand in rows:
        time_delta = (cand.runtime_hours - ref.runtime_hours) / ref.runtime_hours
        cost_delta = (cand.core_hours - ref.core_hours) / ref.core_hours
        table.add_row(
            label,
            str(cand.cores),
            format_duration(cand.runtime_hours),
            f"{_fr_int(cand.core_hours)} h·cœur",
            _pct(cand.efficiency),
            f"{_signed(time_delta)} durée, {_signed(cost_delta)} coût",
        )
    return table


def _signed(frac: float) -> str:
    if abs(frac) < 0.005:
        return "[dim]identique[/]"
    style = "red" if frac > 0 else "green"
    sign = "+" if frac > 0 else "−"
    return f"[{style}]{sign}{_fr(abs(frac) * 100, 0)} %[/]"


def render_model(model: ScalingModel, pilot: PilotSeries) -> Panel:
    """Le modèle ajusté et, surtout, à quel point il colle au pilote."""
    q = model.quality
    style = _QUALITY_STYLE[q.verdict]

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim", justify="right")
    grid.add_column()
    grid.add_row("Forme", model.kind.value)
    grid.add_row("Ajustée", f"[cyan]{model.describe()}[/]")
    grid.add_row(
        "Qualité",
        f"[{style}]{_VERDICT_FR[q.verdict]}[/]  ({_fr(q.max_rel_err_pct, 1)} % d'erreur max)",
    )
    grid.add_row("R²", f"{_fr(q.r_squared, 4)}")
    grid.add_row(
        "Pilote", f"{q.n_points} points, {pilot.core_range[0]}-{pilot.core_range[1]} cœurs"
    )

    breakdown = Table(box=SIMPLE_HEAD, header_style="bold cyan", pad_edge=False)
    breakdown.add_column("Terme")
    breakdown.add_column("Signification", style="dim")
    breakdown.add_column("Valeur", justify="right")
    breakdown.add_row("t_serial", "jamais parallélisé", f"{model.t_serial:.4g} s")
    breakdown.add_row("t_parallel / Nc", "se divise entre les cœurs", f"{model.t_parallel:.4g} s")
    if model.t_comm > 0:
        breakdown.add_row(
            f"t_comm * Nc^{model.gamma:.2f}",
            "coût MPI, croît avec les cœurs",
            f"{model.t_comm:.3g} s",
        )

    return Panel(
        Group(grid, Text(), breakdown),
        title="[bold]Modèle de scalabilité[/]",
        border_style="cyan",
        box=ROUNDED,
    )


def render_pilot_check(model: ScalingModel, pilot: PilotSeries) -> Table:
    """Mesuré vs prédit, point par point.

    Ce tableau est la traçabilité de l'outil : si la courbe ne suit pas les
    mesures pilotes, cela se voit ici en chiffres avant même d'ouvrir une figure.
    """
    table = Table(
        title="[bold]Modèle vs mesures pilotes[/]",
        box=SIMPLE_HEAD,
        header_style="bold magenta",
        title_justify="left",
        pad_edge=False,
    )
    table.add_column("Cœurs", justify="right")
    table.add_column("Mesuré", justify="right")
    table.add_column("Prédit", justify="right")
    table.add_column("Erreur", justify="right")
    table.add_column("", justify="left")

    for p in pilot.points:
        pred = model.time_per_iter(p.cores)
        err = (pred - p.time_per_iter_s) / p.time_per_iter_s
        mag = abs(err) * 100
        style = "green" if mag <= 2 else "yellow" if mag <= 5 else "red"
        bar = "#" * max(1, min(20, round(mag * 2)))
        sign = "+" if err >= 0 else "−"
        table.add_row(
            str(p.cores),
            f"{_fr(p.time_per_iter_s, 3)} s",
            f"{_fr(pred, 3)} s",
            f"[{style}]{sign}{_fr(abs(err) * 100, 1)} %[/]",
            f"[{style}]{bar}[/]",
        )
    return table


def render_curve(rec: Recommendation, *, max_rows: int = 14) -> Table:
    """La courbe de scalabilité en tableau, sous-échantillonnée pour rester lisible."""
    cands = list(rec.candidates)
    if len(cands) > max_rows:
        step = len(cands) / max_rows
        picked = {int(i * step) for i in range(max_rows)}
        if rec.choice is not None:
            for i, c in enumerate(cands):
                if c.cores == rec.choice.cores:
                    picked.add(i)
        cands = [cands[i] for i in sorted(picked)]

    table = Table(
        title=f"[bold]Courbe de scalabilité[/] [dim]({len(rec.candidates)} candidats évalués, "
        f"{len(rec.feasible)} réalisables)[/]",
        box=SIMPLE_HEAD,
        header_style="bold cyan",
        title_justify="left",
        pad_edge=False,
    )
    table.add_column("Cœurs", justify="right")
    if rec.machine.cores_per_node > 1:
        table.add_column("Nœuds", justify="right")
    table.add_column("Durée", justify="right")
    table.add_column("Coût", justify="right")
    table.add_column("Eff.", justify="right")
    table.add_column("État")

    for c in cands:
        is_choice = rec.choice is not None and c.cores == rec.choice.cores
        if is_choice:
            status = "[bold green]← recommandé[/]"
        elif c.is_feasible:
            status = "[dim]ok[/]"
        else:
            labels = [_VIOLATION_LABEL.get(v.code, v.code) for v in c.violations]
            status = f"[red]{', '.join(labels)}[/]"

        row = [f"[bold]{c.cores}[/]" if is_choice else str(c.cores)]
        if rec.machine.cores_per_node > 1:
            row.append(str(c.nodes))
        row.extend(
            [
                format_duration(c.runtime_hours),
                _fr_int(c.core_hours),
                _pct(c.efficiency),
                status,
            ]
        )
        table.add_row(*row)
    return table


def render_inputs(study: Study) -> Panel:
    """Rappelle les entrées, pour qu'un rapport partagé soit autonome."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim", justify="right")
    grid.add_column()

    mesh = study.mesh
    grid.add_row("Étude", f"[bold]{study.name}[/]")
    grid.add_row("Maillage", f"{_fr_int(mesh.num_cells)} mailles")
    if mesh.total_ram_gb is not None:
        source = _MEM_SOURCE_FR.get(mesh.mem_source, mesh.mem_source)
        grid.add_row("RAM (totale)", f"{_fr(mesh.total_ram_gb, 0)} Go  [dim]({source})[/]")
    grid.add_row("Itérations", f"{_fr_int(study.pilot.n_iterations)}")

    m = study.machine
    if m.cores_per_node > 1 or m.name != "generic":
        details = [f"{m.cores_per_node} cœurs/nœud"]
        if m.ram_per_node_gb is not None:
            details.append(f"{m.ram_per_node_gb:g} Go/nœud")
        if m.max_nodes is not None:
            details.append(f"max {m.max_nodes} nœuds")
        grid.add_row("Machine", f"{m.name}  [dim]({', '.join(details)})[/]")

    return Panel(grid, title="[bold]Données d'entrée[/]", border_style="blue", box=ROUNDED)


def render_pilot_warnings(pilot: PilotSeries) -> Panel | None:
    issues = pilot.warnings()
    if not issues:
        return None
    body = Text()
    for i, issue in enumerate(issues):
        if i:
            body.append("\n")
        body.append("- ", style="dim")
        body.append(issue)
    return Panel(
        body, title="[bold]Qualité des données pilotes[/]", border_style="yellow", box=ROUNDED
    )


# ---------------------------------------------------------------------------
# Rapport complet
# ---------------------------------------------------------------------------


def print_report(
    rec: Recommendation,
    study: Study,
    *,
    verbose: bool = False,
    con: Console | None = None,
) -> None:
    """Affiche le rapport complet : la réponse d'abord, les détails ensuite."""
    out = con or console

    out.print()
    out.print(render_answer(rec))

    notes = render_notes(rec)
    if notes is not None:
        out.print(notes)

    alts = render_alternatives(rec)
    if alts is not None:
        out.print()
        out.print(alts)

    out.print()
    out.print(Rule("[dim]justification[/]", style="dim"))
    out.print()
    out.print(render_inputs(study))
    out.print(render_model(rec.model, rec.pilot))
    out.print()
    out.print(render_pilot_check(rec.model, rec.pilot))

    pilot_warn = render_pilot_warnings(rec.pilot)
    if pilot_warn is not None:
        out.print()
        out.print(pilot_warn)

    if verbose:
        out.print()
        out.print(render_curve(rec))
    out.print()
