"""Example: run cfd-stats analysis from Python."""

from __future__ import annotations

from pathlib import Path

import cfd_stats


def main() -> None:
    data_path = Path(__file__).parent / "example_data.pickle"
    if not data_path.exists():
        print("Run  python generate_example_data.py  first.")
        return

    df = cfd_stats.load_dataframe(data_path)
    coeff_cols = ["Cl", "Cd", "Cm"]

    # ── Full automatic pipeline ───────────────────────────────────
    detector = cfd_stats.AutomaticDetector(df, coeff_cols, iter_col="iter")
    results = detector.run_full_analysis()

    reporter = cfd_stats.ConsoleReporter()
    reporter.print_full_report(results)

    # ── Manual per-coefficient analysis ───────────────────────────
    analyzer = cfd_stats.ConvergenceAnalyzer(df, iter_col="iter")
    regime = analyzer.detect_regime("Cl")
    print(f"\nCl regime: {regime['regime']} (quality {regime['quality_score']})")

    pdet = cfd_stats.PeriodicityDetector(df["Cl"].values, df["iter"].values)
    pval = pdet.validate_periodicity()
    print(f"Cl periodicity: {pval['quality_flag']}  ({pval['n_periods_available']} periods)")

    # Moments on steady part
    te = regime["transient_end_iter"]
    steady = df[df["iter"] >= te]["Cl"].values
    mc = cfd_stats.MomentCalculator(steady)
    moments = mc.compute_all_moments()
    print(f"Cl mean = {moments['mean']:.6f} ± {moments['std']:.6f}")


if __name__ == "__main__":
    main()
