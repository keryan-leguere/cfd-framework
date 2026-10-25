"""Regenerate the figures the README embeds.

    python 00_DOC/generer_figures.py

Writes into ``00_DOC/FIGURES/``. These are the package's own correlations,
drawn by :mod:`cfd_aq.report.figures` through ``cfd-plot``. They are committed
so the README renders on a machine that has not installed anything — which
also means they can go stale: regenerate after touching
:mod:`cfd_aq.core.donnees`.

The *other* check — superposing these curves on the scans of the report
itself — is ``00_DOC/verifier_numerisation.py``, and that one needs the PDF.
"""

from __future__ import annotations

import sys
from pathlib import Path

from cfd_aq.report import figures

SORTIE = Path(__file__).resolve().parent / "FIGURES"

#: Assez pour un README, quatre fois moins que le profil « paper » de cfd-plot.
DPI = 140

PLANCHES = (
    ("01_geometries.png", figures.tracer_geometries),
    ("02_rapports_h_plus.png", figures.tracer_rapports),
    ("03_effet_mach.png", figures.tracer_effet_mach),
    ("04_corrections.png", figures.tracer_corrections),
)


def main() -> int:
    print(f"tracé via {figures.sortie_graphique()}")
    for nom, fabrique in PLANCHES:
        chemin = figures.enregistrer(fabrique(), SORTIE / nom, dpi=DPI)
        print(f"  {chemin}  ({chemin.stat().st_size // 1024} ko)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
