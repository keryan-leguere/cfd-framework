"""CLI entry-point for cfd-perf."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cfd_perf.cli.parsing import parse_duration_hours


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cfd-perf",
        description="CFD Performance & Scaling Estimator (steady RANS)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- analyze ---
    p_analyze = sub.add_parser("analyze", help="Analyze mesh metadata")
    p_analyze.add_argument("mesh", type=Path, help="Path to mesh metadata file")
    p_analyze.add_argument("--adapter", default=None, help="Force adapter name (e.g. json)")
    p_analyze.add_argument("--pilot", type=Path, default=None, help="Optional pilot JSON for memory estimation")
    p_analyze.add_argument("--json", action="store_true", default=False, help="Raw JSON output (no Rich)")

    # --- fit ---
    p_fit = sub.add_parser("fit", help="Fit or display scaling model from pilot data")
    p_fit.add_argument("pilot", type=Path, help="Path to pilot JSON file")
    beta_grp = p_fit.add_mutually_exclusive_group()
    beta_grp.add_argument("--beta-fixed", type=float, default=None, help="Use a fixed beta value")
    beta_grp.add_argument("--beta-auto", action="store_true", default=False, help="Auto-fit beta from pilot points")
    p_fit.add_argument("--json", action="store_true", default=False, help="Raw JSON output (no Rich)")

    # --- optimize ---
    p_opt = sub.add_parser("optimize", help="Select optimal core count")
    p_opt.add_argument("--mesh", type=Path, required=True, help="Path to mesh metadata file")
    p_opt.add_argument("--pilot", type=Path, required=True, help="Path to pilot JSON file")
    p_opt.add_argument("--adapter", default=None, help="Force mesh adapter name")
    mode_grp = p_opt.add_mutually_exclusive_group(required=True)
    mode_grp.add_argument("--max-loss", type=float, help="Max efficiency loss (0-1)")
    mode_grp.add_argument("--deadline", type=str, help="Target wall-clock deadline (e.g. 6h, 90m)")
    p_opt.add_argument("--cores-max", type=int, default=4096, help="Maximum cores to consider")
    p_opt.add_argument("--stride", type=int, default=None, help="Core-count step size")
    p_opt.add_argument("--out-json", type=Path, default=None, help="Export results to JSON")
    p_opt.add_argument("--out-csv", type=Path, default=None, help="Export results to CSV")
    p_opt.add_argument("--out-plot", type=Path, default=None, help="Export scaling plot (PNG)")
    p_opt.add_argument("--out-slurm", type=Path, default=None, help="Export SLURM snippet")
    p_opt.add_argument("--min-cells-per-core", type=int, default=100_000)
    p_opt.add_argument("--min-ram-per-core-gb", type=float, default=2.0)
    p_opt.add_argument("--json", action="store_true", default=False, help="Raw JSON output (no Rich)")

    # --- plot ---
    p_plot = sub.add_parser("plot", help="Generate scaling plots from result JSON")
    p_plot_sub = p_plot.add_subparsers(dest="plot_type", required=True)
    p_scaling = p_plot_sub.add_parser("scaling", help="Strong-scaling curves")
    p_scaling.add_argument("--input", type=Path, required=True, help="Result JSON from optimize")
    p_scaling.add_argument("--out", type=Path, default=Path("scaling.png"), help="Output image path")

    return parser


def _cmd_analyze(args: argparse.Namespace) -> None:
    from cfd_perf.benchmark.ingest import load_pilot
    from cfd_perf.mesh.analyzer import analyze_mesh

    pilot_baseline = None
    if args.pilot:
        pilot = load_pilot(args.pilot)
        pilot_baseline = pilot.baseline

    stats = analyze_mesh(args.mesh, adapter_name=args.adapter, pilot_baseline=pilot_baseline)

    if args.json:
        print(json.dumps({
            "num_cells": stats.num_cells,
            "num_faces": stats.num_faces,
            "cell_type_distribution": stats.cell_type_distribution,
            "estimated_mem_per_cell_bytes": stats.estimated_mem_per_cell_bytes,
        }, indent=2))
    else:
        from cfd_perf.cli.console import print_mesh_stats
        print_mesh_stats(stats)


def _cmd_fit(args: argparse.Namespace) -> None:
    from cfd_perf.benchmark.ingest import load_pilot
    from cfd_perf.models.parameters import BETA_DEFAULT, BETA_MAX, BETA_MIN, ModelParameters
    from cfd_perf.models.strong_scaling import fit_beta

    pilot = load_pilot(args.pilot)

    if args.beta_fixed is not None:
        beta = max(BETA_MIN, min(BETA_MAX, args.beta_fixed))
        params = ModelParameters(beta=beta, beta_source="fixed")
    elif args.beta_auto:
        params = fit_beta(pilot)
    else:
        params = ModelParameters(beta=BETA_DEFAULT, beta_source="fixed")

    if args.json:
        print(json.dumps({
            "beta": params.beta,
            "beta_source": params.beta_source,
            "baseline_cores": pilot.baseline_cores,
            "baseline_time_per_iter_s": pilot.baseline_time_per_iter_s,
            "n_iterations": pilot.n_iterations,
            "pilot_points": len(pilot.points),
        }, indent=2))
    else:
        from cfd_perf.cli.console import print_fit_result
        print_fit_result(params, pilot)


def _cmd_optimize(args: argparse.Namespace) -> None:
    from cfd_perf.benchmark.ingest import load_pilot
    from cfd_perf.constraints.config import HardConstraints
    from cfd_perf.io.exporters import export_csv, export_json, result_to_dict
    from cfd_perf.io.plotting import plot_scaling
    from cfd_perf.io.slurm import export_slurm
    from cfd_perf.mesh.analyzer import analyze_mesh
    from cfd_perf.models.strong_scaling import fit_beta
    from cfd_perf.optimizer.selector import optimize

    pilot = load_pilot(args.pilot)
    mesh = analyze_mesh(args.mesh, adapter_name=args.adapter, pilot_baseline=pilot.baseline)
    params = fit_beta(pilot)

    if args.max_loss is not None:
        mode = "efficiency"
        max_loss = args.max_loss
        deadline_h = None
    else:
        mode = "deadline"
        max_loss = None
        deadline_h = parse_duration_hours(args.deadline)

    constraints = HardConstraints(
        min_cells_per_core=args.min_cells_per_core,
        min_ram_per_core_gb=args.min_ram_per_core_gb,
    )

    result = optimize(
        mesh,
        pilot,
        params,
        mode=mode,
        max_efficiency_loss=max_loss,
        deadline_hours=deadline_h,
        cores_max=args.cores_max,
        constraints=constraints,
        stride=args.stride,
    )

    if args.json:
        print(json.dumps(result_to_dict(result), indent=2))
    else:
        from cfd_perf.cli.console import print_export, print_optimization_result
        print_optimization_result(result)

    if args.out_json:
        export_json(result, args.out_json)
        if not args.json:
            from cfd_perf.cli.console import print_export
            print_export("JSON", str(args.out_json))
    if args.out_csv:
        export_csv(result, args.out_csv)
        if not args.json:
            from cfd_perf.cli.console import print_export
            print_export("CSV", str(args.out_csv))
    if args.out_plot:
        plot_scaling(result, args.out_plot)
        if not args.json:
            from cfd_perf.cli.console import print_export
            print_export("Plot", str(args.out_plot))
    if args.out_slurm:
        export_slurm(result, args.out_slurm)
        if not args.json:
            from cfd_perf.cli.console import print_export
            print_export("SLURM", str(args.out_slurm))


def _cmd_plot(args: argparse.Namespace) -> None:
    from cfd_perf.cli.console import console
    from cfd_perf.io.plotting import plot_scaling
    from cfd_perf.optimizer.models import CandidateConfig, OptimizationResult, RejectedConfig

    data = json.loads(args.input.read_text())

    accepted = tuple(CandidateConfig(**c) for c in data.get("accepted", []))
    rejected = tuple(
        RejectedConfig(cores=r["cores"], reasons=tuple(r["reasons"]))
        for r in data.get("rejected", [])
    )
    opt_data = data.get("optimal")
    optimal = CandidateConfig(**opt_data) if opt_data else None

    result = OptimizationResult(
        mode=data["mode"],
        optimal=optimal,
        accepted=accepted,
        rejected=rejected,
        metadata=data.get("metadata", {}),
    )

    out = plot_scaling(result, args.out)
    if out:
        console.print(f"  [bold cyan]Plot  [/bold cyan] -> {out}")
    else:
        console.print("[bold red]No accepted candidates to plot.[/bold red]")


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    handlers = {
        "analyze": _cmd_analyze,
        "fit": _cmd_fit,
        "optimize": _cmd_optimize,
        "plot": _cmd_plot,
    }

    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    handler(args)


if __name__ == "__main__":
    main()
