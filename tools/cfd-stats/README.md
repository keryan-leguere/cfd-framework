# cfd-stats

Automatic convergence analysis and statistics for CFD time-series data.

## Features

- **Convergence detection** – CUSUM-based transient removal, Cauchy criterion, sliding-window statistics
- **Periodicity analysis** – FFT and autocorrelation with cross-validation, phase-locked cycle extraction
- **Statistical moments** – up to order 4, robust statistics (MAD, IQR, trimmed / winsorised means), bootstrap confidence intervals
- **Goodness-of-fit** – Shapiro-Wilk, Anderson-Darling, Kolmogorov-Smirnov, Jarque-Bera
- **Automatic pipeline** – `AutomaticDetector` runs everything in one call per coefficient, classifies regime and emits expert recommendations
- **Family comparison** – compare turbulence models, meshes, etc.
- **Reports** – Rich console, plain text, JSON, standalone HTML
- **CLI** – `cfd-stats analyze`, `cfd-stats compare`, `cfd-stats report`

## Installation

```bash
cd tools/cfd-stats
pip install -e .

# With dev tools
pip install -e ".[dev]"
```

## Quick start

### CLI

```bash
# Full analysis
cfd-stats analyze simulation.pickle --output-dir results/ --format json --format html

# Only one family
cfd-stats analyze data.pickle --family "RANS-SST"

# Compare families
cfd-stats compare data.pickle --families "RANS-SST,LES,DES" --metric Cl

# Generate reports (no interactive console output)
cfd-stats report data.pickle -o reports/ -f txt -f json -f html
```

### Python API

```python
import cfd_stats

df = cfd_stats.load_dataframe("simulation.pickle")

detector = cfd_stats.AutomaticDetector(df, ["Cl", "Cd", "Cm"], iter_col="iter")
results = detector.run_full_analysis()

reporter = cfd_stats.ConsoleReporter()
reporter.print_full_report(results)
```

### Manual per-coefficient analysis

```python
import cfd_stats

df = cfd_stats.load_dataframe("simulation.pickle")

analyzer = cfd_stats.ConvergenceAnalyzer(df, iter_col="iter")
regime = analyzer.detect_regime("Cl")

pdet = cfd_stats.PeriodicityDetector(df["Cl"].values, df["iter"].values)
pval = pdet.validate_periodicity()

steady = df[df["iter"] >= regime["transient_end_iter"]]["Cl"].values
mc = cfd_stats.MomentCalculator(steady)
moments = mc.compute_all_moments()
ci = mc.compute_confidence_intervals()
gof = mc.goodness_of_fit()
```

## Configuration

Settings can be passed as a YAML file (see `examples/example_config.yaml`):

```bash
cfd-stats analyze data.pickle --config my_config.yaml
```

## Data format

Input is a **pickle** file containing a `pandas.DataFrame` with:

- An iteration / time column (auto-detected or set with `--iter-col`)
- One or more numeric coefficient columns (e.g. `Cl`, `Cd`, `Cm`)
- Optionally a `family` column for cross-model comparisons

## Testing

```bash
cd tools/cfd-stats
pip install -e ".[dev]"
pytest -v
```

## Project layout

```
cfd-stats/
├── pyproject.toml
├── src/cfd_stats/
│   ├── cli.py                # Typer CLI
│   ├── config.py             # AnalysisConfig dataclass + YAML
│   ├── core/
│   │   ├── convergence.py    # ConvergenceAnalyzer
│   │   ├── periodicity.py    # PeriodicityDetector
│   │   ├── moments.py        # MomentCalculator
│   │   └── quality.py        # Data-quality metrics
│   ├── analysis/
│   │   ├── detector.py       # AutomaticDetector (full pipeline)
│   │   ├── phase_average.py  # Phase-locked averaging
│   │   └── family_compare.py # Cross-family comparison
│   ├── reports/
│   │   ├── console.py        # Rich console reporter
│   │   ├── summary.py        # JSON / plain-text export
│   │   └── html.py           # Standalone HTML report
│   └── utils/
│       ├── dataframe.py      # Pickle loader, column detection
│       └── validation.py     # Input validation helpers
├── tests/
└── examples/
```
