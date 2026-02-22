# cfd-perf -- CFD Performance & Scaling Estimator

Solver-agnostic CPU scaling estimator for steady RANS CFD simulations.
Predicts runtime, parallel efficiency, and memory usage vs core count,
then selects an optimal launch configuration under efficiency-loss or
deadline constraints.

## Install

```bash
pip install -e ".[dev]"
```

## Quick start

```bash
# Analyze a mesh
cfd-perf analyze mesh.json

# Fit scaling model from pilot data
cfd-perf fit pilot.json

# Optimize core count (efficiency-driven)
cfd-perf optimize --mesh mesh.json --pilot pilot.json --max-loss 0.30

# Optimize core count (deadline-driven)
cfd-perf optimize --mesh mesh.json --pilot pilot.json --deadline 6h

# Plot scaling curves
cfd-perf plot scaling --input result.json --out scaling.png
```

## Dependencies

- **Required**: `numpy`, `matplotlib`
- **Dev**: `pytest`, `ruff`, `mypy`
