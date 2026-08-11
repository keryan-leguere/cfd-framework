# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.


<!-- vim-markdown-toc GFM -->

* [NEW](#new)
* [What this is](#what-this-is)
* [Environment setup](#environment-setup)
* [Core CLI commands (`bin/`)](#core-cli-commands-bin)
* [Architecture](#architecture)
    * [Case directory convention](#case-directory-convention)
    * [`config.yaml` shape](#configyaml-shape)
* [Adding a new CFD solver adapter](#adding-a-new-cfd-solver-adapter)
* [Standalone Python subprojects](#standalone-python-subprojects)
* [Testing the Bash framework](#testing-the-bash-framework)
* [Documentation](#documentation)

<!-- vim-markdown-toc -->

## NEW
## What this is

A solver-agnostic Bash framework for managing, launching, and post-processing parametric CFD
(Computational Fluid Dynamics) studies (OpenFOAM today, mock adapter for testing, more solvers planned).
Core framework code is Bash; several standalone Python tools live under `tools/`.
Comments, docs, and CLI messages are largely in French; code identifiers mix
French (`cfd_charger`, `adapt_lancer_calcul`) and English.

## Environment setup

The framework is driven entirely through the `CFD_FRAMEWORK` env var and `bin/` on `PATH`:

```bash
export CFD_FRAMEWORK="$(pwd)"
export PATH="$CFD_FRAMEWORK/bin:$PATH"
```

All `bin/*` entry points self-resolve `CFD_FRAMEWORK` from their own path if the var isn't already set,
so they also work when invoked with an absolute/relative path without prior exports.

`gestion_config.sh` requires `yq` (`pip install yq`) to be installed — it hard-exits if missing.

## Core CLI commands (`bin/`)

- `cfd-creer --name CASE` — scaffold a new case from `templates/TEMPLATE_CASE_DEFAULT`, sets up a
  tmuxifier session (`tmuxifier-layouts/cfd-case.session.sh`). `--layout-only` reconnects to an existing case.
- `cfd-run --adaptateur {OF|mock} [--in-place] [--dry-run] [--name CASE]` — launch a single case
  through `scripts/lancement/wrapper_commande_lancement.sh`.
- `cfd-run-parametrique --config CONFIG` — drive a parametric study defined in `config.yaml`, via
  `scripts/lancement/lancement_parametrique_yaml.sh`.
- `cfd-run-parametrique` also has a strong-scaling sibling script:
  `scripts/lancement/lancement_scalabilite_forte.sh`.
- `cfd-archiver [--un-safe|--force|--append] SRC DEST` — archive/move a run's results.
- `cfd-archivage-cas` — archives an entire case directory (handles symlinks; see
  `scripts/archivage/archivage_cas.sh`).
- `cfd-clean-config [--force] DIR` — remove stale timestamped run directories under a config.
- `cfd-move` — relocate case/result directories.
- `cfd-post`, `cfd-post-parametrique` — post-processing entry points.
- `cfd-exec` — generic execution wrapper.

Adapter selection priority (highest to lowest): `--adaptateur` CLI flag → `$CFD_ADAPTATEUR` env var →
`adaptateur:` key in `config.yaml` → default `OF`.

## Architecture

Four layers, each only depending on the layer below:

```
bin/*                                   CLI entry points (thin wrappers, resolve CFD_FRAMEWORK, exec into scripts/)
  → scripts/lancement/, scripts/archivage/   orchestration ("wrapper" scripts: parse args, load config, drive the run)
      → lib/*.sh                            reusable Bash libraries (no solver knowledge)
      → adaptateurs/*.sh                    solver-specific adapters, invoked through a common interface
          → actual solver binaries (foamRun, mock, future SU2/Fluent/...)
```

- **`lib/format.sh`** — logging/UI primitives used everywhere: `_info/_warn/_error/_result/_debug/_note`,
  `die`, hierarchical headers (`h1`/`h2`/`h3`, auto-numbered, reset with `reset_counters`), progress bars
  (`progres_init`/`progres_update`/`progres_done`), tables (`tableau_init`/`tableau_add`/`tableau_print`),
  interactive prompts (`confirmer`, `choisir_option`). Auto-detects TTY for color; respects `VERBOSE`
  (0-2), `NO_COLOR`, `FORCE_COLOR`.
- **`lib/gestion_config.sh`** — loads/validates `config.yaml` (`cfg_charger`, `cfg_obtenir_valeur`,
  `cfg_obtenir_valeur_cascade` for cas→config→global fallback, `cfg_lister_cas`, `cfg_expander_cas` for
  parameter-loop expansion, `cfg_valider_schema`). Requires `yq`.
- **`lib/substitution_params.sh`** — substitutes `@param@`-style tags in `.org` template files
  (`param_substituer_tout`, `param_valider_template`).
- **`lib/gestion_timestamps.sh`** — generates/parses the `ADAPTER_VERSION_NAME_TIMESTAMP` run directory
  naming scheme (`ts_generer`, format `YYYYMMDD_HHMMSS`).
- **`lib/utils.sh`** — generic helpers (`util_copier_recursif`, `util_obtenir_taille`).
- **`adaptateurs/interface.sh`** — the contract every adapter implements: `adapt_nom`, `adapt_version`,
  `adapt_description`, `adapt_verifier_installation`, `adapt_preparer_entree`, `adapt_lancer_calcul`,
  `adapt_liste_elements_a_copier`. `adaptateurs/OF.sh` (OpenFOAM) and `adaptateurs/mock.sh` (no
  dependencies, for framework dev/CI) implement it; new solvers go here without touching callers.

### Case directory convention

Every case (created by `cfd-creer`) follows a fixed numbered layout that scripts assume exists:

```
CASE/
├── 01_MAILLAGE/            mesh files
├── 02_PARAMS/              config.yaml + per-configuration dirs, each with a template/ of .org files
├── 03_DECOMPOSITION/       domain decomposition
├── 04_CONDITION_INITIALE/  initial conditions
├── 08_RESULTAT/            archived results (mirrors 02_PARAMS/ structure)
├── 09_POST_TRAITEMENT/     DATA/ and FIGURE/ output of post-processing
└── 10_SCRIPT/              LANCEMENT_CALCUL/ and POST_TRAITEMENT/ custom scripts
```

A launched run creates a timestamped directory inside the relevant `02_PARAMS/<CONFIG>/`, named
`ADAPTER_VERSION_NAME_TIMESTAMP` (e.g. `OF_V13_ALPHA_5_20260131_143052`), containing `LOG/` and
`.metadata.yaml`. Never edit these run directories by hand — treat them as generated/append-only.

### `config.yaml` shape

```yaml
etude:
  nom: "STUDY_NAME"
adaptateur: "OF"          # or "mock"
configurations:
  BASELINE:
    cas:
      - nom: "CASE_1"
        parametres: { angle_attaque: 0.0, reynolds: 6e6 }
```

## Adding a new CFD solver adapter

Create `adaptateurs/<name>.sh` sourcing `adaptateurs/interface.sh` and implementing all `adapt_*`
functions from the interface (see `adaptateurs/OF.sh` / `mock.sh` for reference implementations). Do
not modify the common interface itself or hardcode paths inside an adapter.

## Standalone Python subprojects

These are independent packages (own `pyproject.toml`, own venv/deps) nested inside the repo — they are
not part of the Bash framework's runtime:

- **`tools/cfd-perf/`** — answers "how many CPUs should I launch on?" for steady RANS runs.
  `cfd-perf run STUDY.yaml [--figure F.png]`, plus `check` (validate a study), `example`
  (copy a runnable example), `shim` (see below), and `capture` (automate pilot capture — see
  below). One YAML file
  per study; the only real input is a set of pilot measurements. Layout: `00_DOC/` (illustrated
  docs, FR), `src/cfd_perf/{core,data,capture,engine,report,cli}/`, plus two **package-data**
  dirs shipped inside the package so a plain `pip install` is self-sufficient:
  `src/cfd_perf/01_EXEMPLE/` (ready-to-run example) and `src/cfd_perf/ADAPTATEUR/`
  (solver-agnostic bash capture adapters) — both located via `src/cfd_perf/paths.py`, never
  relative to the repo. Targets **Python 3.9+** (`src/cfd_perf/_compat.py` holds the only
  version shim); has no dependency on `$CFD_FRAMEWORK`. Terminal report and CLI are
  Rich **in French** and deliberately avoid bold (styles centralised in
  `src/cfd_perf/report/theme.py`, `CFD_PERF_GRAS=1` restores it); figures (also French)
  render via the `cfd-plot` package when installed, falling back to plain Matplotlib. See
  `tools/cfd-perf/00_DOC/01_MODELE.md`
  for the scaling model (`fit_model` → `ScalingModel`, `recommend` → `Recommendation`).
    - **Broken console script** (`cfd-perf shim`, `src/cfd_perf/cli/shim.py`, README §3.7):
      pip bakes `sys.executable` into the console script, which is wrong wherever that path
      isn't valid — Python served from an Apptainer/Singularity `.sif` via `module load`
      (pip runs *inside* the image and records a container-internal path), a moved venv, or
      an interpreter path over the kernel's 127-byte `#!` limit. `shim` writes an
      interpreter-free bash launcher (`exec "${CFD_PERF_PYTHON:-python3}" -m cfd_perf "$@"`)
      into `~/bin` and reports every `cfd-perf` on `$PATH` with its shebang status, since a
      dead script in `~/.local/bin` will shadow the launcher. `python -m cfd_perf` is always
      the zero-install equivalent; `01_EXEMPLE/RUN_EXEMPLE.sh` falls back to it on its own.
    - **Pilot capture** (`cfd-perf capture`, `00_DOC/05_CAPTURE_PILOTE.md`): two-phase
      submit→collect. `capture --coeurs "N…" --adaptateur X [--queue Q]` submits one run per
      core count via a bash adapter (a shipped one, a path to your own script, or
      `$CFD_PERF_ADAPTATEUR_DIR`; mirrors the framework
      `adaptateurs/` contract but self-contained — `interface.sh`/`mock.sh`/`OF.sh`); `capture
      --collect` reads finished runs, extracts time/iters/RAM (peak RAM = SLURM `MaxRSS ×
      NTasks`), auto-detects the machine (`hotes.yaml` fallback), writes a validated `ETUDE.yaml`,
      and recommends. Python side under `src/cfd_perf/capture/` (`BashAdapter`, `machine_detect`,
      `manifest`, `study_writer`, `orchestrator`). Test with `--adaptateur mock` (no solver/SLURM).
- **`tools/cfd-atm/`** — atmosphere model as a "block": maps an altitude (geometric/geopotential/
  pressure) + a temperature model (`ISA`, `ISA±ΔT`, custom `T(H)` profile) to the air state (p, T, ρ),
  derived quantities (speed of sound, Sutherland viscosity, θ/δ/σ ratios), every equivalent altitude,
  and — from one speed input — all flight-mechanics airspeeds (Mach, Vc/CAS, EAS, TAS) in subsonic
  **and** supersonic (Rayleigh pitot). `cfd-atm point …` (Rich FR report, aero units first with SI),
  `cfd-atm diagramme` (iso-Vc / iso-TAS figures), `cfd-atm example`. Layout mirrors cfd-perf:
  `00_DOC/` (FR docs — `01_MODELE_ATMOSPHERE.md`, `02_GRANDEURS_VITESSE.md`), `01_EXEMPLE/`
  (`tracer_iso_vitesses.py` + `profil_T_custom.yaml`), `src/cfd_atm/{core,report,cli}/`. Figures use
  the `cfd-plot` package when installed, else plain Matplotlib. Core is
  pure NumPy (no SciPy): custom profiles integrate hydrostatic equilibrium; the supersonic Mach
  inversion is a hand-rolled bisection. Key physics note documented in `02_GRANDEURS_VITESSE.md`:
  on a Mach–zp chart iso-Vc are temperature-invariant (only iso-TAS move with ΔT); the geometric-
  altitude diagram (A) is where the temperature model shifts the iso-Vc curves.
- **`tools/cfd-nozzle/`** — quasi-1D toolbox for convergent-divergent (de Laval) nozzles. Answers
  "which regime does this nozzle run in, what does it deliver, and what contour should I draw?".
  Layout mirrors cfd-atm: `00_DOC/` (FR docs `01_MODELE_QUASI_1D.md`, `02_CHOCS_ET_DETENTES.md`,
  `03_REGIMES_ET_PERFORMANCES.md`, `04_GEOMETRIES.md` + `generer_figures.py`),
  `src/cfd_nozzle/{core,data,report,cli}/`, and `src/cfd_nozzle/01_EXEMPLE/` shipped as
  **package data** (located via `paths.py`, copied by `cfd-nozzle example`). Dual CLI front-end:
  flag subcommands (`iso`, `choc`, `oblique`, `detente`, `tuyere`, `geometrie`, `moc`) plus
  `run`/`check` on a YAML case file (`data/case.py`). Core is pure NumPy (no SciPy):
  `core/numerics.py` holds the only root finder. Notable design points, all documented and tested:
    - **Performance uses the Sutton decomposition** (`00_DOC/03`): `c* = η_c*·√(R·T0)/Γ`,
      `ṁ = p0·At/c*`, `F = Cf·p0·At`, `Isp = Cf·c*/g0`. The original script applied η_c* twice
      contradictorily (ṁ×η *and* c*×η), breaking `c* ≡ p0·At/ṁ` by η²; the invariant is now a test.
    - **MOC** (`core/moc.py`) does planar **and** axisymmetric (δ = 0/1 source term), via the
      inverse method (kernel → exit characteristic → Goursat region → wall streamline). The
      expansion fan **must** be graded, `θ_i = θ_max·(i/n)^3` (`FAN_EXPONENT`): a uniform fan is
      singular at the sonic corner (x_axis ∝ θ^(1/3)) and refining it diverges outright in
      axisymmetric. Validated envelope: M_exit ≤ 4 axisymmetric, ≤ 5 planar (γ = 1.4), checked
      against ε = A/A*(M_exit) to < 0.03 %; outside it a RuntimeError says so.
    - `rao_angles` θe correction had an inherited sign error (a shorter bell must end *less*
      aligned, so θn and θe move together) — fixed and tested.
  Terminal report is Rich **in French** and avoids bold (`report/theme.py`, `CFD_NOZZLE_GRAS=1`
  restores it); figures use `cfd-plot` when installed, else plain Matplotlib.
- **`tools/cfd-stats/`** — automatic convergence analysis/statistics for CFD time-series (`cfd-stats` CLI).
- **`tools/slurm-utils/`** — Slurm command aliases, priority explorer, queue recommender (`slurm-utils` CLI).
- **`tools/paraview/`** — ParaView automation scripts (state replay + snapshotting, VTM/VTI conversion).
- **`tools/cfd-plot/`** — a Matplotlib wrapper package (import name `cfd_plot`) providing styled
  figure helpers (`use_style`, `plot_line`, `plot_with_band`, `plot_bar`, `save_figure`, etc.) across
  three profiles (`notebook`/`slides`/`paper`), plus a dict-driven `batch.py` for multi-source curve
  comparisons (CFD/analytics/experimental data across flight points) and a `cfd_plot.dispersion`
  submodule (needs SciPy — `.[dispersion]` extra). `cfd-perf` and `cfd-atm` import it *optionally*
  via their `report/_plotting_lib.py` and fall back to plain Matplotlib when it is absent, so they
  stay deployable on their own. Note: pandas is a hard dependency (`__init__` re-exports `batch`).
  mypy runs here at `check_untyped_defs` level, not `strict` like the other packages — see TODO.md.

Each has its own `pyproject.toml` (setuptools, `src/` layout, Python ≥3.12) with a `dev` extra
(`pytest`, `ruff`, `mypy`/`pytest-cov`). There is no workspace tool, no lockfile and no
`requirements.txt` anywhere: you `cd` into a package, install it editable into a venv, and run the
tools directly. Install and test one in isolation, e.g.:

```bash
cd tools/cfd-perf && pip install -e ".[dev]" && pytest
cd tools/cfd-plot && pip install -e ".[dev]" && pytest
```

`tools/cfd-plot` also has an end-to-end fixture/example generator at
`tests/E2E_MULTIPLE_PLOTTING/run_batch_plot.py`.

## Testing the Bash framework

Tests are plain Bash scripts under `tests/`, run directly (no test runner/framework) with
`CFD_FRAMEWORK` exported and `CFD_ADAPTATEUR=mock` so no real solver is needed:

```bash
export CFD_FRAMEWORK="$(pwd)"
bash tests/test_sprint1_2.sh          # end-to-end test
bash tests/lib/test_format.sh         # per-library tests (test_gestion_config.sh, test_utils.sh, ...)
```

`tests/exemple_cas/` and `tests/fixtures/` hold fixture case directories used by these scripts. The
`mock` adapter (`adaptateurs/mock.sh`) exists specifically to make these tests solver-independent —
use it for any new framework-level test rather than requiring a real OpenFOAM install.

## Documentation

Full docs (bilingual FR/EN, MkDocs Material) live in `docs/docs/`, built via `docs/mkdocs.yml`.
`docs/site/` is the generated static output (git-ignored upstream conventionally, though currently
tracked here) — don't hand-edit it, regenerate with `mkdocs build` from `docs/`. Source-of-truth pages:
`docs/docs/architecture/overview.md`, `docs/docs/adapters/overview.md`, `docs/docs/api/format.md`,
`docs/docs/guide/workflow.md`.
