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
- **`tools/cfd-plot-digitizer/`** — **not a Python package**: a dependency-free browser app that
  recovers numeric data from a picture of a plot (paper figure, scanned report, vendor chart). Runs by
  opening `index.html` in a browser — no server, no install, no network — because the target is an
  air-gapped workstation. `cfd-plot-digitizer.html` at the root is the same app inlined into one
  254 ko file (built by `outils/construire_autonome.py`) and is **committed**, so it can be copied
  to a stick with nothing else — which also means it can go stale: rebuild after touching any
  source, and `construire_autonome.py --verifier` exits 1 when it has drifted. Layout mirrors the other tools:
  `00_DOC/` (FR docs — `01_CALIBRATION.md`, `02_DETECTION_COULEUR.md`, `03_EXPORT_ET_PROJET.md`),
  `app/js/` (`00_base` → `70_vignettes` are DOM-free and unit-tested, `90_main` holds all UI wiring),
  `exemples/`, `outils/`, `tests/`. UI, comments and docs are French, like cfd-perf/atm/nozzle.
    - **No ES modules anywhere.** Firefox gives a `file://` page an opaque origin and refuses
      `import`, so scripts load as classic `<script>` tags onto a `CFDD` namespace. Same reason the
      demo figure is embedded as a data URL in the generated `app/js/80_exemple.js` (regenerate with
      `outils/generer_exemple_embarque.py`): an `<img>` read from a sibling file taints the canvas and
      kills `getImageData`, hence all detection.
    - **Headline feature — pick a colour, get the curve.** Matching uses CIE L\*a\*b\* with *two*
      tolerances, chroma and lightness, kept separate on purpose: anti-aliasing moves lightness far
      more than hue, and for a black/grey curve a\* and b\* are zero on both sides so only lightness
      discriminates. Then a scan of the mask takes the *centre* of each contiguous run.
    - **Line-type filtering** (`25_trait.js`) separates curves that share a colour — the black-and-white
      plate case, where nothing else can. It is structural, not colorimetric: connected components
      (8-connectivity, or an oblique 1 px line fragments into one component per pixel and reads as
      dotted), sorted into continu/tirets/pointillé. Both thresholds are *relative*: "continuous"
      is judged against the tracé's total span — never against the longest component present, or a
      dotted-only plate would crown its longest dot a solid line — and the dot/dash frontier scales
      with the measured stroke thickness. `comblerLacunes` then bridges a dashed curve's gaps by
      interpolation, capped so a real interruption is never spanned; stats keep detected and
      interpolated points distinct.
    - **Axis calibration is half-automated.** `15_cadre.js` finds the plot frame from ink
      profiles: an axis line dominates its column/row profile, a curve contributes one or two
      pixels per column. Thresholds are doubled — dominate the profile *and* cover 35 % of the
      inked extent — so a bare scatter cannot crown its densest column a border. A plate with only
      two spines gives one peak per direction, and *which* border it is cannot be assumed (calling
      the x-axis the top edge folds the frame onto a line): its position within the ink decides,
      and the found line's own extent supplies the opposite border. Measured against the three
      matplotlib fixtures: all four sides within 2 px, and the calibration derived from them within
      0.6 % of the perfect one. X1 and Y1 are linked to the origin corner by default (three markers
      to place, not four) and every marker position is typeable as well as clickable.
    - **Every detection setting carries an SVG thumbnail** (`70_vignettes.js` — DOM-free strings,
      so they are unit-tested like anything else). The `<select>` stays the source of truth: the
      thumbnail sets it and dispatches `change`, since assigning `.value` fires nothing on its own;
      duplicating each setting's logic across both controls would have guaranteed drift. Tests
      assert every option in `index.html` has a drawing, and that no SVG contains `</script`, which
      would break the single-file build.
    - **Per-series marker** — shape and size, not only colour — and a **drag-select eraser**. The
      hollow shapes (ring, cross, plus) exist because a filled 2 px dot on a 2 px trace is
      invisible, precisely where you are aiming.
    - **Export is a card list**, each card carrying a summary, a use and three lines of real output,
      all in `40_export.js` (`DESCRIPTIONS`) — the module knows what it emits. The `separateur`
      flag that hides the irrelevant control is *verified*, by rendering every format twice with
      two separators, not merely declared.
    - **`csv-grille` export** resamples every series onto one shared x by linear interpolation, since
      separately digitized curves never share abscissae. It never extrapolates (blank outside a
      series' own range) and it *refuses* folded curves — a polar has two y per x, and interpolating
      it would silently average its branches. The test for foldedness is the length of monotone runs,
      not the count of direction reversals: a clean fold has exactly one reversal, which any
      noise tolerance would swallow.
    - Three traps, all documented and tested: a **polar** `Cz(Cx)` is a lying arc, so column scanning
      averages its two branches into a wrong curve — switch `orientation` to rows; a **legend**
      contains segments of the exact curve colour that no tolerance can reject — hence rectangular
      **exclusion zones** (forgetting one moved the log-plot error from 0.03 % to 1.9 decades); and
      where the curve runs *parallel* to the scan direction the error rises to 1–2 px instead of
      0.1–0.5 px.
    - Series points are stored in **pixel** coordinates, never physical units, so fixing a mistyped
      axis value re-derives every series without re-picking anything.
    - Tests: `node tests/executer.js` (172, about a second) **or** open `tests/index.html` in a
      browser — same files, and the 14 file-reading integration tests disable themselves there. Ten
      of them digitize real matplotlib figures and compare against the data that drew them, measuring
      distance to the reference curve in axis-normalised coordinates (a vertical gap would just be
      measuring the local slope). `outils/verifier_navigateur.sh` screenshots a real browser.
- **`tools/cfd-stats/`** — automatic convergence analysis/statistics for CFD time-series (`cfd-stats` CLI).
- **`tools/slurm-utils/`** — Slurm command aliases, priority explorer, queue recommender (`slurm-utils` CLI).
- **`tools/paraview/`** — ParaView automation scripts (state replay + snapshotting, VTM/VTI conversion).
- **`tools/cfd-plot/`** — a Matplotlib wrapper package (import name `cfd_plot`) providing styled
  figure helpers (`use_style`, `plot_line`, `plot_with_band`, `plot_bar`, `save_figure`, etc.) across
  three profiles (`notebook`/`slides`/`paper`), a dict-driven `batch.py` for multi-source curve
  comparisons (CFD/analytics/experimental data across flight points), a `cfd_plot.anim` submodule
  (GIF/MP4) and a `cfd_plot.pdf` one (multipage reports, contact sheets; clickable outline needs the
  optional `pypdf`). `batch_plot` also takes `clean=` (wipe the generated tree first —
  `cfd_plot.cleanup`, which refuses `/`, `$HOME`, a top-level dir and a repo root) and `fold=`
  (bonus sheets gathering siblings: `FoldSpec(kind="y")` puts every Y of one condition on one
  sheet beside them, `kind="context"` puts one Y across conditions under `<POLAR>/FOLD/` as
  panels or, `layout="overlay"`, on one axes under `FOLD_OVERLAY/` where colour reads the
  condition and marker/linestyle the source; families larger than `max_panels` split into
  numbered sheets rather than shrinking).
  `cfd_plot.domains` (`plot_domains`) shades and names the regions a curve crosses from a
  per-point integer column (`iDomain`): runs of equal consecutive values, cut halfway between
  the samples that disagree, a hole in the column left blank rather than shaded through, and
  palette colours keyed on the *value* so a regime keeps its colour on a figure where a
  neighbouring regime is absent.
  A configuration entry may also carry the caller's own keys (`masse`, `maillage`): only
  keywords Matplotlib recognises (asked of `ArtistInspector(Line2D)`) reach `plot_line`, with
  `style` as the never-filtered escape hatch. Layout calls go through `cfd_plot._compat`
  (`figure_set_layout_pad` / `figure_disable_layout`), which also speaks the pre-3.6 Matplotlib
  API — a cluster often *provides* a Matplotlib older than the declared floor.
  SciPy is optional (`.[interp]`) and now only serves `interpolate_field2d`.
  `cfd-perf`, `cfd-atm` and `cfd-nozzle` import it *optionally* via their
  `report/_plotting_lib.py` and fall back to plain Matplotlib when it is absent, so they stay
  deployable on their own; `cfd-dispersion` **requires** it for every figure (its calculation
  still runs without it). Note: pandas is a hard dependency (`__init__` re-exports `batch`).
  mypy runs here at `check_untyped_defs` level, not `strict` like the other packages — see TODO.md.
  The former `cfd_plot.dispersion` submodule was extracted into `tools/cfd-dispersion` and rebuilt
  on OpenTURNS; it is gone from here, with no shim.
- **`tools/cfd-dispersion/`** — dispersion laws, Monte-Carlo draws, validation and dispersed polars,
  built on **OpenTURNS** (no SciPy). Input is your law table, `{coeff: {Biais_Type, Biais_M,
  Biais_ET, FE_Type, FE_M, FE_ET}}`. French API and docs, like cfd-perf/atm/nozzle. Layout:
  `00_DOC/` (FR docs 01–05 + `generer_figures.py`), `src/cfd_dispersion/{core,report,figures,cli}/`,
  `batch.py`, and `01_EXEMPLE/` shipped as package data (located via `paths.py`, with its own
  README and five runnable scripts covering every feature). `00_DOC/05_BRANCHER_SON_MODELE.md` is
  the practical one: the law dict, the model function skeleton, the output **column contract**
  (`<coeff>_Biais` / `<coeff>_FE` / `<coeff>`, or a `colonnes=` mapping), the `tirages` dict keyed
  by `(y_key, sweep_key)`, and `batch_plot`'s four dictionaries spelled out key by key.
    - **Two model shapes are accepted** (`core/tableau.py`). Flat columns, or the shape a real
      house model actually has: `plan_croise(Mach=L_MACH, alpha=L_ALPHA, …)` for the crossed call
      plan, and one wide table back carrying flight point, coefficients, arbitrary metadata and the
      **dicts themselves** — `DICT_TIRAGE`, `DICT_LAW_DISPERSION`. `lire_sortie_modele(df)` flattens
      the draw, numbers *distinct* draws by content, and re-reads the laws from the table (refusing
      a table whose rows disagree). Dict columns survive a CSV round-trip: they come back as JSON or
      Python `repr` strings and both are parsed.
    - **The crossing trap, guarded.** A crossed call applies the same draw at every sweep point, so
      each drawn value appears once per alpha. Validating that as-is leaves *D* unchanged but
      inflates n by the sweep length, tightening the threshold by √k: 500 conforming draws pass at
      p = 0.61 and are rejected at p = 8e-7 once crossed over 13 points. Hence
      `unique_par=("tirage",)` on `valider_lot` / `figures_par_pdv`, and
      `validation.verifier_redondance`, which *refuses* a massively redundant group and names the
      remedy — the symptom of the mistake is a rejection, i.e. exactly what the user came for and
      has no reason to doubt. It tests the full component tuple, so a degenerate law (constant by
      construction) never trips it.
    - **`ET` is a half-range, not a standard deviation** — `σ = ET/2` for the Gaussian families.
      This is the single most expensive mistake the model allows, it is invisible on a curve, and
      it is what `core/validation.py` exists to catch. The six families map onto `ot.Dirac`,
      `ot.Uniform`, `ot.Normal` and `ot.TruncatedNormal`; a test pins them against 400 000 draws of
      the old SciPy implementation so the port cannot have quietly changed the physics.
    - **Two OpenTURNS traps, both handled**: `Normal.getRange()` returns a *finite* numerical range
      (≈ M ± 7.65 σ), not the support — so `support()` returns ±inf for type 4, and `plage_utile()`
      is what figures use; and `getSample(n)` returns `(n, 1)`, which broadcasts against a `(npts,)`
      sweep into a plausible-looking wrong `(n, npts)`. One helper, `core/alea.vers_numpy`, flattens
      *and* copies (the raw view is read-only).
    - **Reproducibility is global.** OpenTURNS has no per-call generator, so there is no `rng=` but a
      `graine=`; `core/alea.graine_temporaire` restores the prior state so a seed never costs the
      caller theirs.
    - **Validation is three ordered checks** — support, then moments (against OpenTURNS' *exact*
      truncated moments, not `ET/2`), then Kolmogorov–Smirnov. Each catches what the others miss: a
      truncated law drawn as a full Gaussian passes KS at p = 0.13 but fails support; a bimodal law
      with identical moments and support fails only KS. `valider_lot` corrects for multiplicity
      (Šidák): without it a wholly conforming 12-point × 4-component study comes out clean 3 times
      in 20, with it 19 times in 20.
    - **`superposer_dispersion`** overlays a theoretical band, the per-draw curves, a min/max fill in
      the series' own tint, ±1/2/3σ lines labelled *on* the curve, and a box naming the law. The σ
      labels compute their angle in *display* coordinates and must be placed last, after anything
      that can move the limits. `batch.py`'s `HookDispersion` plugs all of it into
      `cfd_plot.batch_plot`'s `on_before_save`; it is a module-level class, not a closure, because
      `batch_plot` silently drops to `n_jobs=1` when its hook is not picklable.
    - **`tirer_lot` returns `list[Tirage]`**, not a DataFrame — the shape a model consumes, one
      `DICT_DISP_DRAWN` per element, so the caller just loops. `tableau_des_tirages(lot)` flattens
      it back to the `<coeff>_Biais` / `<coeff>_FE` table (and `tirer_tableau` does both at once),
      which is what CSV, `describe()` and `valider_lot` want. Each draw carries its `numero` in the
      lot, the lot's `graine` and the plan; a lone `tirer()` has `numero=None`. Drawing the lot in
      one go is the only thing a declared correlation and the LHS/Sobol plans can act on — a loop
      over `tirer(lois, graine=graine + i)` gives n independent MC draws and nothing more.
    - **The law of the dispersed coefficient** (`core/combinaison.py`, `loi_combinee`) is what the
      third panel of every draw figure now shows — a computed density, not a histogram. Exact
      whenever the reconstruction relation is affine in (biais, FE) at a fixed nominal
      (`ot.LinearCombinationDistribution` over the two component laws, whatever their families);
      otherwise a 20 000-point LHS smoothed by `ot.KernelSmoothing`. Affinity is **measured**, not
      assumed — three evaluations to extract `(a, b, cst)`, three more to check they hold — so a
      non-affine house convention falls back instead of producing an "exact" law that is exactly
      wrong. Degenerate components fold into the constant rather than entering as Dirac masses.
      A combined law exists **at one point only** (FE multiplies the nominal), so a swept nominal
      is reduced to one abscissa and the figure says which.
    - **`figures_tirage_par_pdv` (`figures/par_pdv.py`) walks the flight points** of a model output
      table and writes, per flight point and per draw, one figure per coefficient plus the matrix —
      returning an *inventory* DataFrame (flight point, draw, figure, file) and closing figures as
      it goes. It reuses `batch_plot`'s **conventions** — the `flight_point_dict` shape, one
      directory per *varying* key, `save_name`/`label`/`unit` — but not the function: its
      `on_before_save` hook fires on a figure it has already built (one axes, one curve per source,
      a sweep on x), and draw figures have no sweep, no curve and three panels. Three deliberate
      behaviours: `max_tirages=15` per flight point (400 draws would mean 400 figures nobody
      reads); the nominal is looked up in the column named like the coefficient, then
      `<coeff>_nominal`, and only if **constant** over the flight point — a varying column is a
      dispersed output, and taking it would centre the law on the draw it is meant to judge; and
      `n_jobs` (forkserver pool, picklability checked up front like `batch_plot`'s hook) because a
      single figure costs ~0.5 s to write — the house font is vectorised glyph by glyph.
      `01_EXEMPLE/sortie_modele.py` is a **hard-coded example of the model output table** (4 flight
      points × 100 draws = 400 rows, one lot replayed at every flight point) that later examples
      build on.
    - **The nominal comes from a second table, and the model gets checked.** `reference=` on the
      walker is the same model run once with a neutral draw (`tirage_neutre` — `FE = 1` for
      `biais + FE·c`, `FE = 0` for the percentage form, *resolved* from the relation rather than
      hard-coded, since one-versus-zero would null or double a whole study's baseline); its
      `<coeff>` columns are the nominals. The main table's `<coeff>` is therefore the model's
      **dispersed output**, and `figure_tirage(disperse_modele=…)` marks it beside the value the
      package recomputes as `convention(nominal, biais, FE)`, stating whether they agree
      (`comparer_au_modele` / `AccordModele`, relative tolerance 1e-6 against the nominal's scale;
      the parameter box turns red on disagreement, and the walker's inventory carries `calcul`,
      `modele`, `ecart`, `accord`). It is the only check in the package aimed at the *model* rather
      than the draw, and it catches the three silent ones: a different convention on either side,
      a reference the model never saw, dispersion applied somewhere else than assumed.
    - **The law table and the output columns need not name the same coefficients**, and the two
      directions differ. A `CX0` the model *consumes* has laws but no output column: it keeps its
      two component panels — those laws depend on no nominal — and its third says what is missing.
      A `CA` the model *returns* without laws is not plotted at all (no draw, no draw figure), and
      asking for it in `coefficients=` is refused by name. An **ambiguous reference** — two `CN`
      values for what `points_de_vol` calls one flight point — also raises, naming the columns that
      would disambiguate, rather than picking one or silently dropping the nominal.
    - **The built-in `CONVENTIONS` are module-level functions, not lambdas**, so a `Tirage` — and
      anything carrying one — survives `pickle`. Before that, `pickle.dumps(tirer_lot(...))` failed,
      which quietly cost a `multiprocessing.Pool` the draws it was being handed and dropped
      `batch_plot` to one core.
    - **The draw figures draw and write in one call.** `figure_tirage(..., chemin=)` and
      `figure_tirage_matrice(..., chemin=)` save through `enregistrer` — **SVG** by default — and
      return `FigureTirage` (`figure`, `axes`, `fichiers`, `coefficients`); the matrix returns a
      *list*, paginating at `MAX_COEFFICIENTS_PAR_FIGURE` = 4 coefficients and numbering files
      `_01`, `_02`… beyond that. Every density panel carries ±1/2/3 σ reference lines
      (`cfd_plot.add_reference_lines`, wrapped as `lignes_reference`) drawn at the law's *exact* σ
      and only where they fall inside the axis, labelled at the foot of the line because the top of
      the panel belongs to the parameter box and the legend; the coefficient panel adds a secondary
      top axis in **% deviation from nominal**. `figure_comparaison`'s third panel overlays the same
      prescribed combined law on the realised histogram, which is where an ET-vs-σ error becomes
      visible on the delivered quantity (±15 % prescribed against ±30 % obtained).
    - **Every figure goes through cfd-plot**, primitive by primitive (`figures/_base.py`, asserted
      by `test_base.py::TestToutPasseParCfdPlot`) — the format of a deliverable is defined there and
      nowhere else. Hence the exported `style` / `nouvelle_figure` / `tracer_ligne` / `enregistrer`.
      `enregistrer` exists because `cfd_plot.save_figure` composes filenames with
      `Path.with_suffix`: a base name as ordinary as `CN_Mach0.85` loses its `.85`, and a whole
      series of flight points silently overwrites one file. It appends a dummy suffix first.

Each of these (except `cfd-plot-digitizer`, which is a browser app with no build step at all) has
its own `pyproject.toml` (setuptools, `src/` layout, Python ≥3.9) with a `dev` extra
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
