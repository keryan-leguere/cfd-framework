#!/usr/bin/env python3
"""Generate synthetic post-processed CSV fixtures for batch-plot E2E tests."""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent

HEADER = [
    "Mach",
    "Altitude_m",
    "alpha",
    "beta",
    "DL",
    "DM",
    "DN",
    "PP1",
    "CA",
    "CY",
    "CN",
    "QOI1",
    "QOI2",
    "whatever",
    "scheme",
]

MACH_VALUES = [0.70, 0.80, 0.85]
ALTITUDE_VALUES = [5000, 8000, 10000]
BETA_VALUES = [0.0, 2.0]
ALPHA_VALUES = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]

SOURCES = {
    "kw.csv": ("KW", 0.100, 0.0200, 0.050, 0.010, 0.000),
    "sa.csv": ("SA", 0.120, 0.0190, 0.048, 0.011, 0.002),
    "exp.csv": ("EXP", 0.110, 0.0205, 0.049, 0.0105, 0.001),
}


def _coefficients(
    mach: float,
    altitude: float,
    beta: float,
    alpha: float,
    cn_base: float,
    cn_slope: float,
    ca_base: float,
    cy_base: float,
    source_bias: float,
) -> tuple[float, float, float]:
    mach_effect = 0.03 * (mach - 0.80)
    alt_effect = 2.0e-5 * (altitude - 8000)
    beta_effect = 0.004 * beta
    cn = cn_base + cn_slope * alpha + mach_effect + alt_effect + beta_effect + source_bias
    ca = ca_base + 0.002 * alpha + 0.5 * beta_effect + source_bias
    cy = cy_base + 0.0015 * alpha + 0.3 * beta_effect + source_bias
    return cn, ca, cy


def _build_rows(scheme: str, cn_base: float, cn_slope: float, ca_base: float, cy_base: float, source_bias: float):
    rows = []
    for mach in MACH_VALUES:
        for altitude in ALTITUDE_VALUES:
            for beta in BETA_VALUES:
                for alpha in ALPHA_VALUES:
                    cn, ca, cy = _coefficients(
                        mach,
                        altitude,
                        beta,
                        alpha,
                        cn_base,
                        cn_slope,
                        ca_base,
                        cy_base,
                        source_bias,
                    )
                    rows.append(
                        [
                            mach,
                            altitude,
                            alpha,
                            beta,
                            0.0,
                            0.0,
                            0.0,
                            1.0,
                            round(ca, 6),
                            round(cy, 6),
                            round(cn, 6),
                            round(cn * 1.1, 6),
                            round(cn * 0.9, 6),
                            "dummy",
                            scheme,
                        ]
                    )
    return rows


def main() -> None:
    for filename, (scheme, cn_base, cn_slope, ca_base, cy_base, source_bias) in SOURCES.items():
        rows = _build_rows(scheme, cn_base, cn_slope, ca_base, cy_base, source_bias)
        path = HERE / filename
        with path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(HEADER)
            writer.writerows(rows)
        print(f"Wrote {path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
