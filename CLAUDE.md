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
Core framework code is Bash; several standalone Python tools live under `tools/` and
`scripts/post/plot/`. Comments, docs, and CLI messages are largely in French; code identifiers mix
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

- **`tools/cfd-perf/`** — CPU scaling estimator for steady RANS CFD runs (`cfd-perf` CLI,
  `src/cfd_perf/`: mesh analysis, benchmarking, strong-scaling models, optimizer).
- **`tools/cfd-stats/`** — automatic convergence analysis/statistics for CFD time-series (`cfd-stats` CLI).
- **`tools/slurm-utils/`** — Slurm command aliases, priority explorer, queue recommender (`slurm-utils` CLI).
- **`tools/paraview/`** — ParaView automation scripts (state replay + snapshotting, VTM/VTI conversion).
- **`scripts/post/plot/`** — a Matplotlib wrapper package (`plotting/`) providing styled figure helpers
  (`use_style`, `plot_line`, `plot_with_band`, `plot_bar`, `save_figure`, etc.) across three profiles
  (`notebook`/`slides`/`paper`), plus a dict-driven `batch.py` for multi-source curve comparisons
  (CFD/analytics/experimental data across flight points) and a `dispersion/` submodule.

Each has its own `pyproject.toml` (setuptools, Python ≥3.12) with a `dev` extra (`pytest`, `ruff`,
`mypy`/`pytest-cov`). Install and test one in isolation, e.g.:

```bash
cd tools/cfd-perf && pip install -e ".[dev]" && pytest
cd scripts/post/plot && pip install -e ".[dev]" && pytest
```

`scripts/post/plot` also has an end-to-end fixture/example generator at
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
