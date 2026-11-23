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
  (GIF/MP4 — an MP4-only animation is **streamed** as raw RGBA into ffmpeg, `Mp4Stream`, no PNG per
  frame; ffmpeg found via `$CFD_PLOT_FFMPEG` → `PATH` → the `imageio-ffmpeg` wheel; time-driven pieces
  `timeline` (frame instants from duration/speed, holds inserted *exactly*), `PathReveal` (ghost/trail/
  interpolated head, 2-D or 3-D) and the `animate_path` one-liner with events and a 3-D orbit), a
  `cfd_plot.axes3d` module (`true_proportions`, `tidy_axes3d` — no minor ticks, white panes, ticks
  ∝ side length — and `fit_box3d`/`bbox3d`, because Matplotlib draws any 3-D box in a *square* and
  `bbox_inches="tight"` returns that whole square; `bbox3d` skips labels of out-of-view ticks, which
  3-D leaves at astronomical positions, measures each `Text3D` at its *projected* position — outside
  `draw` it holds its data x, y as its 2-D position, metres read as pixels — and skips those
  `axlim_clip` hides) and a `cfd_plot.pdf` one (multipage reports, contact sheets; clickable outline needs the
  optional `pypdf`). `batch_plot` also takes `clean=` (wipe the generated tree first —
  `cfd_plot.cleanup`, which refuses `/`, `$HOME`, a top-level dir and a repo root) and `fold=`
  (bonus sheets gathering siblings: `FoldSpec(kind="y")` puts every Y of one condition on one
  sheet beside them, `kind="context"` puts one Y across conditions under `<POLAR>/FOLD/` as
  panels or, `layout="overlay"`, on one axes under `FOLD_OVERLAY/` where colour reads the
  condition and marker/linestyle the source; families larger than `max_panels` split into
  numbered sheets rather than shrinking).
  **`values` in `flight_point_dict` / `sweep_dict` restrict the loops** — they were
  informational before, and the enumeration always walked every value in the table, so a model
  called finely for a smooth polar turned each of its hundred alphas into a directory on every
  *other* polar. A key in both dicts is handled by the sweep machinery but keeps the `values`
  written on the flight-point entry; on a sweep they say where it is **pinned**, never what the
  abscissa shows. A declared value no row holds is named in a warning rather than costing a
  directory that silently never appears.
  `batch_compare_flight_points` syncs its panels by default (`sync_axes="both"`, `None` to opt
  out) — only the panels carrying data, and *before* `on_before_save`, like a folded sheet, so a
  hook's own limits are the last word. `on_before_save` takes one callable **or a sequence**
  (`HookChain`, a frozen dataclass so it pickles whenever its hooks do), run in order on every
  figure — the same on `batch_carto` and the compare figures.
  `cfd_plot.carto` (`batch_carto`, `CartoSpec`) is the same loop one dimension wider: one
  figure per **pair** of sweeps (every other sweep pinned as a directory, like `batch_plot`),
  one panel per configuration, drawn as `plot_contourf` + black `plot_contour` + `clabel`.
  Panels share their level *values* by default, so a band means the same thing in every panel —
  and must then agree on `cmap`/`levels`, since one colorbar cannot describe two (it raises,
  naming `shared_scale=False` as the way out). A `"CARTO"` sub-dict on a `y_axis_dict` or
  `configuration_dict` entry overrides the drawing options; it is metadata, so the same
  `configuration_dict` still drives `batch_plot`. Rows are pivoted, never interpolated: an
  unrun cell stays a hole, and two rows in one cell is an error naming the unpinned column.
  With exactly two configurations, `delta=True` / `"relative"` (`DeltaSpec`) adds a third panel,
  `conf2 - conf1` (the first entry is the reference): diverging colormap, scale symmetric about
  zero with an odd level count so a boundary lands on zero, its own colorbar (the field's spans
  the field panels only), `bound=` to pin the range across a study. Both sources are
  interpolated onto one fine grid over the sweep range they *share* — the intersection, never
  the union — before subtracting, so different steps still compare (`grid="exact"` restores the
  cell-by-cell subtraction and its refusal); interpolation and subtraction commute, so the
  smoothing invents nothing, but a hole widens by one coarse cell. A zero reference in relative
  mode is a hole, not an infinity.
  A blank cell says *which* blank it is (`RegionSpec`, `EquilibreSpec`): an `Equilibre` column
  reading `NON` is picked up without being asked, hatched under a "non équilibrable" message and
  dropped from the field — so it leaves the colour scale and the delta too — while cells the
  study never ran are outlined and hatched with a message of your own — crossed against
  dotted, never a mirror image. Whole cells, not the half-cells a contour at 0.5 would give,
  since `contourf` blanks a cell on one missing corner (drawn with `corner_mask=False` so the
  fill agrees); a seam cell touching both zones goes to the un-trimmable one, never to both;
  the zones sit *behind* the field with only the message on top; and the delta panel carries
  both zones (either source's un-trimmable nodes, resampled) and is padded to the field
  panels' extent like they pad each other. Turning the zones on also pads short panels to the
  figure's extent, so two maps of one quantity always share their axes. `panel_title` / `suptitle` / `subtitle` (and `DeltaSpec.title`)
  take a template or a callable; a panel's template can name any key of its `configuration_dict`
  entry (`{masse}`, `{CDG}`), an unknown field is left verbatim so LaTeX braces survive, and the
  resolution happens in the parent so a lambda costs no worker.
  `cfd_plot.domains` (`plot_domains`) shades and names the regions a curve crosses from a
  per-point integer column (`iDomain`): runs of equal consecutive values, cut halfway between
  the samples that disagree, a hole in the column left blank rather than shaded through, and
  palette colours keyed on the *value* so a regime keeps its colour on a figure where a
  neighbouring regime is absent. Names that would collide are **measured and staggered**
  (`label_overlap="stagger"`, or `"hide"` / `"ignore"`): the widest regions keep the first
  row, the narrow ones climb with a leader (an annotation pinned in points, so it survives
  the layout engine), and the title pad is remembered on the axes so `cfd_plot.set_title`
  called *after* `plot_domains` still clears the rows — `ax.set_title` resets its pad.
  A configuration entry may also carry the caller's own keys (`masse`, `maillage`): only
  keywords Matplotlib recognises (asked of `ArtistInspector(Line2D)`) reach `plot_line`, with
  `style` as the never-filtered escape hatch. Matplotlib parses a whole string as **mathtext**
  as soon as it holds one `$`, so a heading mixing `×`/`−`/`Δ` with a `$C_N$` asks the *math*
  font for those glyphs and dies on a stack that lacks them (the Spyder/IDE case, where
  `batch_plot` still works): `mathtext_safe` renders a probe once per font stack and falls back
  to ASCII, `CFD_PLOT_ASCII_TEXT` forces either way. Layout calls go through `cfd_plot._compat`
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
    - **`hook_dispersion_tableau(df_disperse)` is the short way onto `batch_plot`**: the
      `configuration_dict` carries the *reference* table (the model run once with a neutral draw),
      the hook carries the *dispersed* one, and nothing is pre-shaped. Per figure it reads the
      flight point and the quantity off the `BatchPlotContext` (`y_spec["col_name"]`, not the key)
      and slices the dispersed table **with `batch_plot`'s own filter** — strict equality on the
      flight-point keys and the fixed sweeps — so the subset provably matches the drawn curve, with
      no tolerance to tune. The nominal is read back off the axes and handed to
      `superposer_depuis_tableau` as a two-column DataFrame, so `nominal_depuis_tableau` checks the
      band sits on the draws' abscissa rather than beside it. Three deliberate refusals: a missing
      flight-point *column* (every figure would otherwise get every draw), and a flight point absent
      from the dispersed table — raised on the *first* figure, because two hundred undecorated
      figures read as a model without dispersion (`absent="ignorer"` for a deliberately partial
      study); several labelled curves with no `serie=`. Fold sheets (`fold=`) follow one rule —
      **panels are decorated, overlays are not**: `kind="context"` (one panel per flight point)
      and `kind="y"` (one panel per quantity) each give the hook its own axes and its own
      context per panel, so they slice exactly like an ordinary figure, while
      `layout="overlay"` stacks the whole family on one axes under relabelled curves and is
      left untouched. Compare panels are decorated one call each, for the same reason. On a
      sheet `batch_plot` legends only the first panel when they share labels, so the hook
      passes `legende_=False` where there is no legend to refresh — each panel still carries
      its own parameter box, which is where its own numbers live.
      `lois=` adds the prescribed band over the obtained cloud, which is the only place a model
      dispersing more than asked shows up. `01_EXEMPLE/09_batch_plot_dispersion.py` is the runnable
      version, and README §10.1 the documented one.
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
      `n_jobs` (process pool on the **default** start method — `fork` on Linux, like
      `batch_plot`; picklability checked up front like `batch_plot`'s hook) because a
      single figure costs ~0.5 s to write — the house font is vectorised glyph by glyph.
      `01_EXEMPLE/sortie_modele.py` is a **hard-coded example of the model output table** (4 flight
      points × 100 draws = 400 rows, one lot replayed at every flight point) that later examples
      build on.
    - **Both walkers take `batch_plot`'s three CLI arguments**, transliterated: `verbeux`
      (`verbose` — the plan panel, the flight-point loop tables, then a Rich progress bar naming
      the flight point and draw in flight), `rapport` (`report`, default **True** — the files
      written, grouped by flight point, with sizes) and `a_blanc` (`dry_run` — enumerate and write
      nothing, cleaning included). The rendering lives in `report/parcours.py`, and the dry run
      composes filenames through the same `_Travail.fichiers_prevus()` the real run uses, so
      `a_blanc=True` provably says what a real run would write (asserted).
    - **`relations={"CN": "-CZ", "CA": "CX1 + CX2"}` gives a law to an output the model does not
      disperse** (`core/relation.py`). The law table covers what the model *consumes*, the output
      table what it *produces*; when the gap is linear, each target gets **both** its laws, derived
      from its sources', plus its drawn components, derived from the row's draw — so it is plotted
      like a declared coefficient, and the model-vs-calcul check then covers the **relation
      itself**. The split differs between the two components: at a fixed nominal a convention is
      `α·Biais + β·FE + cst` (measured, via `decomposition_affine`), so the bias weights are the
      `aᵢ` and the scale-factor weights are **shares**, `aᵢ·cᵢ/c_cible` — hence laws derived **per
      flight point**, from the sources' nominals read out of `reference=`. One term and no constant
      (`CN = -CZ`) is the exception: shares are 1, no nominal is needed, and the law **stays in its
      family** (a `LoiDispersion` with the same type and `ET`); several terms leave the six
      families for a `LoiDerivee` over `ot.LinearCombinationDistribution`. The constant offset is
      chosen so a **neutral draw stays neutral**, and the whole derivation is replayed against the
      relation on fictitious draws before use. Three refusals: a multi-term relation without its
      sources' nominals; a relation that disagrees with the reference's own target column (every
      derived law of that flight point would be wrong, silently); a non-affine convention or a
      correlated law set. `LoiComposante` (a Protocol in `core/loi.py`) is what lets figures,
      validation and the terminal report treat both kinds alike; `LoiCoefficient.en_table()` is the
      inverse of `charger_lois` and **refuses** a derived law, since no `(type, M, ET)` describes a
      combination. In the histogram walker the target's components — which the model never returns
      — are **recomposed** from its sources' with the same weights. `coefficients=` replaces the
      default list (laws + relation targets), `coefficients_en_plus=` adds to it.
      `01_EXEMPLE/sortie_modele_relations.py` + `10_relations.py` are the runnable version.
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
    - **The polar utilities are table-first too.** `superposer_depuis_tableau(ax, df, x=, y=,
      reference=)` does the grouping (`courbes_par_tirage`), reads the reference curve from a
      DataFrame of the same shape (`nominal_depuis_tableau`, which refuses an abscissa that is not
      the draws') and calls `superposer_dispersion` — fan, min/max fill, darker dispersed mean,
      ±kσ labelled on the curve. Omitting `reference` falls back to the mean of the draws, which is
      right only while the laws are centred: the band then centres on itself and the bias vanishes,
      so it is documented as a trap rather than a default. The band actually drawn now comes back in
      `artistes["objet_bande"]` whether it is theoretical or built from the cloud
      (`bande_depuis_courbes`, in `core/bande.py`, which takes curves you already have), and
      `resume_dispersion` reduces any band to the four numbers a report copies — largest envelope
      and where, max σ, mean-vs-nominal gap. Those three lines are in the parameter box, and the
      fill's legend label carries the headline percentage.
    - **`figures_histogramme_par_pdv` (`figures/histogramme.py`) is the ensemble view**: one figure
      per (flight point × coefficient) over **all** the draws — the realised histogram of the biais,
      of the FE, and of the coefficient the model returned, each against the law that prescribed it
      (the third panel against the *combined* law, which is where a model dispersing more than asked
      shows up). It shares the flight-point plumbing with `figures_tirage_par_pdv` (`_repartir` now
      takes the worker function) and the density panel with `figure_comparaison`
      (`figures/densite.py::tracer_densite_realisee`, law optional). It is also where the
      laws-vs-outputs mismatch pays off: a coefficient with **no laws but an output column still
      gets its histogram**, which the per-draw figure cannot do. It refuses a **crossed** table —
      several rows per draw would mix the sweep into the histogram — naming the column that
      discriminates the duplicated rows.
    - **The law table and the output columns need not name the same coefficients**, and the two
      directions differ. A `CX0` the model *consumes* has laws but no output column: it keeps its
      two component panels — those laws depend on no nominal — and its third says what is missing.
      A `CA` the model *returns* without laws is not plotted by default (the walk follows the laws);
      named in `coefficients=` it still gets a figure — no law means no draw, but there remains a
      nominal and the value the model returned, hence an écart to read. Only a name that is neither
      a law nor a column is refused. An **ambiguous reference** — two `CN`
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

- **`tools/cfd-validation/`** — code-verification helpers (Fortran 77 / C) whose output is
  *traceable evidence*, not just "tests pass": Rich FR terminal report (no bold,
  `CFD_VALIDATION_GRAS=1`), full text log, CSV/JSON, `cfd-plot` paper figures. Restarted from
  scratch on 2026-11-14 (the former f2py table-readback package is gone from the working tree,
  still in git at `ffa03b60`). Report rigour targets DO-178C / ECSS-E-ST-40C & Q-ST-80C /
  NASA-STD-7009A / IEEE 29119-3; `00_DOC/01_PRINCIPE.md` maps each requirement to the piece that
  answers it (section numbers only where certain — DO-178C §11.13–11.16). Layers `core` (NumPy
  only) → `data` → `engine` → `report` → `cli`, AST-enforced (`tests/test_architecture.py`);
  `integration.py` is the façade outside the layers. mypy strict. First control (then table reading, table bounds and table interpolation, below):
    - **Integration test** — `valider_integration(reference, test, entrees=, sorties=, …)` /
      `cfd-validation integration REF TEST --config X.yaml` (exit 0 conform, 1 input error,
      2 non-conform). Rows are paired **on input values** by default (order may differ;
      missing/extra rows reported; duplicated keys paired in order and flagged), or by position
      with inputs *checked* (diverging pairs are not compared); with no inputs declared (outputs
      only) position is the only mode — unchecked, warned about, no attribution nor figures 04–06. Criterion
      `|t − r| ≤ atol + rtol·|r|`, reference is the oracle; NaN==NaN is identical, NaN vs number
      is `NON_FINI` with **infinite margin**. Per value: Δ, rel, **ULP** (`core/ecarts.py` maps
      floats to `2⁶³ ± magnitude` so −0/+0 share a key), **margin = Δ/tolerance**. Every
      tolerance carries origin (default/declared) + justification; defaults are flagged as
      unjustified. **Attribution**: per input, failure rate per level (≤ 12 distinct values, else
      8 quantile bins) + Cramér's V; rows missing from the test count as failures (a crash is the
      most localised failure). Pieces: `integration.log` (complete, written last with SHA-256 of
      every other piece, trailing spaces stripped), `resume.json`, `lignes.csv`, `ecarts.csv`,
      `FIGURES/` (`01_synthese_sorties` one row per output, `02` 12 panels/page, `03` CDF 7
      curves/page, `04_marges_<k>_<sortie>` only for failing outputs by default — `<k>` is the
      output rank so CN/Cn don't collide on case-insensitive disks —, `05`/`06` inputs sorted by
      `ResultatIntegration.entrees_par_pertinence()`; margin on symlog axis linear in [−1, 1];
      tick labels are *pure* mathtext
      because TeX Gyre Termes lacks Unicode superscripts — tests run figures with
      `UserWarning` as error to catch missing glyphs — deprecations excluded, since
      pyparsing ≥ 3.3's `PyparsingDeprecationWarning` is *also* a `UserWarning` and matplotlib 3.9,
      the last on Python 3.9, raises it on every mathtext render). Scales to 10 inputs × 15 outputs
      (`tests/test_grande_table.py`): the terminal row table keeps the inputs that fit, most
      failure-linked first, and names the hidden ones; the log widens itself
      (`largeur_journal`) so nothing is cropped. Content SHA-256 of both tables via
      `pd.util.hash_pandas_object`. CSV read back exactly (`float_precision="round_trip"`
      before pandas 3, default after). Example: `01_EXEMPLE/01_test_integration.py` (dummy aero
      model, 462 cases, scenarios identique / arrondi / regression), `02_grande_table.py`
      (10 inputs × 15 outputs incl. CN/Cn and CM/Cm, 3 000 cases, regression tied to
      `braquage_profondeur ≥ 15`), `INTEGRATION.yaml`,
      `RUN_EXEMPLE.sh` (uses `python -m cfd_validation`).
    - **Table-reading test** (second control) — `valider_lecture_tables(tables, evaluer, defauts,
      combinaisons=…, sortie=…)` (`00_DOC/03_LECTURE_TABLES.md`): calls the code on every node of
      every table (1D…5D) and compares the value it read — a **probe** written in the Fortran right
      after each table lookup — to the table itself (the oracle, read from the COMMON the BLOCK DATA
      fills, never a separate copy). `TableReference(nom, valeurs, axes={col: grille}, sonde,
      vers_entrees=, fixes=, rtol/atol/justification)`; default criterion bit-for-bit (weights are
      exactly 0/1 on a node), declared tolerances flagged as such. **Orientation = declaration order**
      (axes in Fortran index order, shape checked, a permutation suggested on mismatch — a *square*
      table cannot be checked by shape, the values reveal a transposition). Nodes walked in Fortran
      memory order (first index fastest = `DATA` order). Point built as `defauts` → `fixes` → table
      columns (directly when named like an input, else `vers_entrees(df_axes) -> {input: values}`,
      the inverse relation; an axis that is not an input without it is refused). `combinaisons`:
      every node replayed for the product of the values of inputs the table neither drives nor
      fixes (combination 0 = defaults); `BilanTable.dependances()` names the input whose failure rate varies across its values (over the full product, combination 0 excluded — a default outside the combined values would otherwise get a rate of its own), else "lecture fausse". Proven on the real compiled code with 3 injected Fortran faults (wrong grid for CY; CX probe after the propulsion increment — passes at defaults, caught only by combinations as « dépend de ipropu »; DM/DN swapped at the 5D call). A NaN probe = NON_FINI.
      Layers: `core/noeuds.py`, `data/tables.py`, `engine/lecture_tables.py`,
      `report/lecture_tables.py` (coordinates of a failing point in **one** column so 5D fits 80
      cols; one justification footnote per distinct tolerance), `report/figures_tables.py` (one
      panel per table, 6/page: x = node rank, y = value, blue dots = table, vermilion crosses = code
      for all combinations, ring = out of tolerance, triangle = probe not reached, thin lines at
      changes of the slowest axis; crosses always on top and smaller than the dots so each keeps a blue
      rim — user request: the crosses must stay visible on dense tables —, only distinct (node, value)
      pairs drawn, > 2000 markers rasterized; **SVG only** by default, `FORMATS_TABLES`, user request),
      façade `lecture_tables.py`. Pieces: `TABLES/`, `RESULTATS/` (`valeur_TAB`, `valeur_CODE`,
      `ecart`, `ulp`, `marge`, `statut`, `conforme`, `%.17g`), `FIGURES/`, `resume.json`,
      `lecture_tables.log` (SHA-256 of the others). Tests: `tests/test_lecture_tables.py` (fake
      Python "code", no compiler, incl. 5D).
    - **Table-bounds test** (third control) — `valider_bornes_tables(tables, evaluer, defauts, ecart=0.10,
      ecarts=, consigne_defaut="sature")` (`00_DOC/04_BORNES_TABLES.md`): beyond each table's bounds,
      does the code saturate or extrapolate as the declared **consigne** says? Consigne lives in
      `TableReference(bornes={"alpha": "extrapole", "alphat": ("inatteignable", "extrapole")})`
      (`sature` / `extrapole` / `inatteignable` — a side no input can reach, e.g. alphaT < 0 from
      acos, declared, not tested, reported), so one declaration serves both table tests. Points: one
      **face** per axis and side (user decisions: faces only, no corners; no IERR-flag check), the axis
      at `ecart × (max − min)` beyond the bound (fraction of the *span*: « 10 % of the bound » means
      nothing for α ∈ [−20, 20]), the other axes on all their nodes. Oracle `core/bornes.interpoler`:
      multilinear with a per-axis-per-side rule (t clamped or left outside [0, 1]), checked against an
      exact multilinear function. Every face is also compared to *both* consignes → **observé**
      (sature / extrapole / indiscernable when the last cell is flat / ni l'un ni l'autre / sonde non
      atteinte): failures read « attendu sature, observé extrapole ». Default tolerance: bit-for-bit
      on saturated faces, rtol 1e-12 on extrapolated ones (oracle may order operations differently);
      a table's declared tolerance wins. `engine/injection.py` (`piloter`: defaults → fixes → table
      columns / `vers_entrees`) is now shared with the reading test; `report/lecture_tables.
      ecrire_journal_rich` is the shared journal writer. Layers: `core/bornes.py`,
      `engine/bornes_tables.py`, `report/bornes_tables.py`, `report/figures_bornes.py` (x = points face
      after face, face labels `alpha+ E` in vermilion when failing; blue = expected, grey rings = the
      *other* consigne, crosses on top — crosses landing on grey rings = wrong consigne), façade
      `bornes_tables.py`. Pieces: `RESULTATS/` (`valeur_ATTENDUE/SATURATION/EXTRAPOLATION/CODE`),
      `FIGURES/synthese_bornes*.svg`, `resume.json` (recap-compatible `tables[]` keys),
      `bornes_tables.log`. Proven on the real code with an injected `CHERCH` fault (upper side ignores
      the consigne): the 7 extrapolated upper faces fail « observé sature » while the reading test
      stays conforme. Tests: `tests/test_bornes_tables.py`.
    - **Table-interpolation test** (fourth control) + **polars** — `valider_interpolation_tables(tables,
      evaluer, defauts, fractions=(¼,½,¾), centres=True, polaires=, libelles=, superposer=True, n_jobs=)`
      (`00_DOC/05_INTERPOLATION_TABLES.md`): between nodes, does the code return the table's
      **multilinear** interpolation? Groups: one per axis (axis at each fraction of each cell, other
      axes on all nodes) + `centres` (every cell centre, all axes at ½ — the only place a missing cross
      term shows: a sum of 1D interpolations is exact whenever one axis sits on its lower node). CSV
      carries `maille` in 1-based Fortran indices (`3-4`, centres `2-3 4-5`). Oracle =
      `core/bornes.interpoler`; **observé** = linéaire / palier (code equals a cell corner) /
      indiscernable / ni l'un ni l'autre / sonde non atteinte; default tolerance rtol 1e-12. The
      evaluator call is now shared by all table tests (`engine/injection.appeler`). **Polars** (user
      request, qualitative, no verdict — they show all three table tests at once): per table and
      abscissa, the code called densely (`core/mailles.abscisses_polaire`: nodes, 7 pts/cell, 10 %
      beyond each bound except `inatteignable` sides) for every condition (other axes on nodes),
      drawn by **`cfd_plot.batch_plot`** (`report/figures_polaires.py`): sources `code` (vermilion
      line) and `table` (blue dots), abscissa in `sweep_dict`, other axes in `flight_point_dict`
      (1D tables get a dummy constant key, batch_plot needs one), `fold` overlay (`FoldSpec(kind=
      "context", layout="overlay", over=(axis,), folder="SUPERPOSITION")`) for the superposed sheet;
      hook `HabillagePolaire` (frozen dataclass → picklable, `n_jobs` keeps its pool) greys the
      out-of-bounds zones with the declared consigne (« Saturé » / « Extrapolé », under the curves), draws a light major + dotted minor grid, rebuilds legends and French titles (capitalised — user request, also on the 01/02 synthesis figures; header on every polar = bold black title « X vs. Y » + grey non-bold subtitle with the conditions — user preference for all figure titles); call
      wrapped in `mpl.rc_context()` since batch_plot's `use_style` is global. `data/polaires.Polaires`
      (abscisses, noeuds kept when the axis is a condition, superposer) restricts them; > 200 curves
      is refused (a 5D table at defaults would be 3 125). `tracer_polaires_tables` draws them alone.
      Proven on the real code with two injected Fortran faults: `CHERCH` T = 0 in-grid (palier) —
      2D/1D tables pass tests 1–2, only test 3 catches them (DCMG caught everywhere: the polar
      round trip lands just under nodes); `INTE2D` without cross term — CL passes tests 1–2, fails
      32/36 centres. Tests: `tests/test_interpolation_tables.py`.
    - **`01_EXEMPLE/MODELE_AERO/`** — a real Fortran 77 code wrapped for Python, the bench
      the validation runs on (package data, explicit globs in `pyproject.toml`; the built `*.so`
      and `VALIDATION/SORTIE/` are never shipped nor copied by `cfd-validation exemple`).
      `SOURCES/`: `aero_dim.inc` (COMMON /AERTAB/ — six square 7×7 tables, two indirect-read 2D tables (user request, `DOC/01_SOURCES.md` §4.4: `TDCZR` ΔCZ(Mach, α in **radians**) read with `ALPHA / DEG`, declared on axis `alpha_rad` with `vers_entrees=radians_vers_degres` and a justified rtol 1e-12 since ~9 % of angles miss the deg→rad round trip by 1 ULP; `TDCXB` ΔCX(Mach, **|β|**) read with `ABS(BETA)`, declared **twice**, `DCXB`/`DCXB_NEG`, same probe, min side `inatteignable` — a missing ABS passes the positive one, proven by `test_lecture_indirecte_faute_detectee` on two faulty Fortran builds; 11 declarations, integration REFERENCE CSVs regenerated) + 1D propulsion ΔCX(Mach)
      on a deliberately narrower grid — and /AERTB5/ — 5D ΔCm of control surfaces in polar angles,
      `TDCMG(Mach, alphaT, phiA, DM, DN)`, 5⁵ nodes, independent of phiA at alphaT = 0 since atan2
      returns 0 there), `aero_probe.inc` (COMMON /PROBE/ `VALID_TAB_<TABLE>`, hard-coded Fortran by
      user decision, always active), `aero_tables.f` (BLOCK DATA, **generated** by
      `OUTILS/generer_tables.py`, `--verifier` = drift check), `aero_interp.f` (bilinear and 32-corner
      `INTE5D`, weights written `(1−T)`/`T` so nodes come back bit-exact; saturation → IERR 2),
      per-axis out-of-grid consigne in `CHERCH(…, IEXT, …)` (`ISATU`/`IEXTR` in `aero_dim.inc`;
      user request: mixed behaviour — Mach/DM/DN/propulsion saturate, α/β/alphaT extrapolate,
      IERR 2 either way),
      `aero_modele.f` (`SUBROUTINE AERO` with `ENTRY AERINI(XREF,YREF,ZREF,LREF)` — the init
      carries the user's constants, kept in SAVE; **init entries have no return code** (user
      assumption: a refused init leaves INIT false → AERCAL IERR 1) —, `ENTRY AERCFG(BIAICX)` (bias
      added to CX after the probes, before moment transport; validation gives it a constant
      `DEFAUTS["biaicx"] = 0.005`; exercises several init phases, `PHASES_INIT = ("aerini", "aercfg")`,
      all re-called in order when any of their args changes) and `ENTRY AERCAL(MACH…IPROPU, DM, DN, CX…CN,
      IERR)`; alphaT/phiA computed from α, β; each table value copied to its probe *before*
      propulsion/control/transport; `Cf2py intent(in/out)` lines right after each ENTRY). Sources
      must stay **ASCII** (f2py fails on one accent). User decisions: no Makefile, no Fortran
      tests — verification goes through Python. `CMakeLists.txt` (user request, `LANGUAGES NONE`, ≥ 3.17) is
      only a front door over the bash/Python scripts: targets `modele` (ALL, custom command on the `.so`,
      rebuilt when `SOURCES/*` change), `exemple`, `validation`, `lecture`/`bornes`/`interpolation`,
      `verifier_tables`/`tables`, `nettoyer`/`nettoyer_tout` (`OUTILS/nettoyer.cmake`), `aide`; ctest
      with a `modele` fixture; in-source build refused; `CMakePresets.json` (`defaut`, `o3`);
      `gitignore.exemple` is a template, not active. `PYTHON/`: `construire.sh` (plain bash, user request — `bash construire.sh [NOM [DOSSIER]]`,
      `FFLAGS`/`FC` env; one `python -m numpy.f2py -c` call in a temp dir with **no `--backend`**
      (user request: `--backend meson` failed on their machine) — f2py picks distutils while
      `numpy.distutils` exists (then `FFLAGS` goes through `--opt`, since as an env var
      numpy.distutils would also drop `-fPIC`), else meson (needs meson+ninja = extra `[f2py]`, reads
      `FFLAGS` env); writes `<NOM>.compilation.log` next to the `.so`, also on failure (machine, CPU,
      `-march=native` target, compilers, backend, SHA-256 of sources and module, the *actual*
      compiler flags per source from meson's `compile_commands.json` — meson's release buildtype
      puts `-O3` before `FFLAGS` —, then the raw f2py output); `PYTHON/README.md` « Options de
      compilation » holds measured flag suggestions (`-O3 -march=native` 1.6× over `-O2`, validation
      still 100 %); `cmake.sh` (front door: configures `build/` when `CMakeCache.txt` is missing,
      then `cmake --build`, from any cwd — « build is not a directory » was a skipped `cmake -B
      build`); the interpreter's bin dir prepended to PATH; sources are a
      **directory** (`DOSSIER_SOURCES` + `MOTIFS` `*.f *.F *.for *.f90 *.F90`, user request — every
      matching file is compiled), `INCLUDES` a list of dirs; refuses non-ASCII sources and includes; a module's name is baked into the binary, so two builds to compare get two names and
      load side by side with separate Fortran state), `modele_f2py.py` (`ModeleF2py`, generic, **holds no argument value** — user request, no
      `CONSTANTES`: argument names parsed from each phase's f2py `__doc__`; `calcul_elementaire(df)`
      needs one column per argument, init args included, and re-calls the init phases only when a
      row changes their values — last init tracked per library at module level, since Fortran SAVE
      state is process-global; `calcul_point(**point)`; `SONDES` = COMMON blocks reset to NaN before
      each call and returned as columns; `lire("bloc.var")` copies any COMMON variable),
      `modele_aero.py` (`ModeleAero`, the model's overlay, user design: `__init__()` takes no model
      argument; `calcul_aero_elementaire(df)` = the Fortran args as is — **what validation calls** — except init-phase args (`xref…lref`, `biaicx`), which are optional and take `DEFAUTS` when absent/empty (`completer_init`, user request; the generic `calcul_elementaire` still has no defaults); probes are optional (user request: a code not yet probed): `sondes=None` reads the `SONDES` blocks present and warns about absent ones (`sondes_absentes`), `True` requires them (validation's `charger_modele`), `False` reads none; `DEFAUTS_CALCUL` (user request) gives every AERCAL argument a value the model **never computes with** — the validation's "argument not driven by the table" point; `VALIDATION*/tables_modele.DEFAUTS = ModeleAero.defauts_complets()` (no longer written there; `charger_modele` exits 1 if an argument lacks one; keys outside their phase refused at construction; the mechanism — `DEFAUTS`, `DEFAUTS_CALCUL`, `defauts_complets`, `defauts`, `completer_init` — lives in generic `ModeleF2py` with empty class defaults); validation's `biaicx` is now the model's 0.0 (probes precede the bias; `generer_reference.py` pins 0.005, the value of the shipped CSVs);
      `calcul_aero(df)` = standard `PARAMETRES` (CDG in mm body FLU, `propulsion` bool, `xref…lref`
      optional from `DEFAUTS`) → `vers_elementaire` → elementary → `completer_sorties` (`etat`,
      `modele`, `version`, `bibliotheque` — where extra output columns go); Fortran-convention
      columns mixed into standard ones are refused; a default column left empty on some rows takes
      its default). `csv=` on `calcul_elementaire` / `calcul_aero_elementaire` / `calcul_aero`
      (user request) writes the returned frame too (`ecrire_csv`: pandas' default `repr` floats —
      shortest exact, no `0.80000000000000004` —, named index kept, dir created). `calcul_yaml.py
      FILE.yaml [--sortie CSV]` (user request) runs flight points from YAML (`exemple_pdv.yaml`):
      `fonction`, `sortie` (relative to the YAML), `sondes` (bool, default false — true adds the `valid_tab_*` columns and *requires* the probe COMMON, false never reads it), `commun`, `pdv` = one block or a list, each block
      the cross product of its keys (last fastest), a key = scalar / list / `{de, a, pas}` (bounds
      included) / `{de, a, n}`; errors name the spot (`pdv[0].alpha`), exit 1; CMake target `pdv`. `VALIDATION_PRODUCTION/` (user request) is the **deliverable copy** of `VALIDATION/` with no fault option (`--defaut`, `cm_faussee`, `consigne_cx_alpha`, `cm_en_palier` absent; `declarer_tables(modele)` only); an unknown option exits **1** (`tables_modele.analyseur`), never 2, so it cannot read as « non conforme »; `recapituler.py` byte-identical and `RUN_VALIDATION.sh` identical outside comments — both asserted, as are identical tables/tolerances from the two declarations; CMake target `validation_production`; kept in sync by hand. `VALIDATION/04_INTEGRATION/` (user request, VAL-INT-04): `REFERENCE/*.csv` stand for results from another environment (here the same Fortran built `-O3 -ffast-math -march=native` by `generer_reference.py`, demo only, under two foreign header conventions `Alpha (deg)` / `ALPHA [deg]`, propulsion ON/OFF; ≤ 1 ULP mostly, 64 ULP on Cm near zero); `04_integration.py` holds the small helper `normaliser_colonnes` (`nom_type`: strip unit in ()/[], lower, `_`, then `ALIAS`; unknown/duplicate columns refused), reads with the new package function `lire_dossier(dir, renommer=, colonne_fichier="campagne")` (same columns required across files, `attrs["fichiers"]` = SHA-256, also exported: `lire_table`, `ErreurLecture`), replays the inputs through `calcul_aero_elementaire` and calls `valider_integration` with `campagne` as an input (failures attributable to a file), rtol 1e-12/atol 1e-14 justified, `ierr` exact; `--defaut` shifts Cm by 1e-9 at |DM| = 20 → attributed to dm (V = 1). Production copy has the CSVs byte-identical, no generator. `recapituler.py` now reads integration `resume.json` (`k/n sorties, N lignes`, %). Package changes made for it: integration report gives each distinct justification once as a numbered note; per-input figures (04/05/06) drop inputs with a single level; integration figure titles bold (`axes.titleweight`/`figure.titleweight`), subtitles grey, legends capitalised; long category tick labels rotated. `VALIDATION/` holds **one directory per
      test** (user request) + `RUN_VALIDATION.sh` (explicit `TESTS=(dir|script|options)` list; script
      contract: accepts `--sortie DIR`, writes `resume.json`, exits 0/2; extra options forwarded;
      outputs in `VALIDATION/SORTIE/`) + `tables_modele.py` (the model's 10 tables, 11 declarations, declared once —
      values/grids read from the COMMON, probes, inversion, `bornes` consignes — imported by every
      test; the file to rewrite for another code) + `recapituler.py` (stdlib; `SORTIE/RECAP.txt`, one line per
      test, % of conforming values never rounded up to 100, « TOUT EST À 100 % »; exit 0/1).
      `02_BORNES_TABLES/`, `03_INTERPOLATION_TABLES/` (polars of every table, DCMG restricted in
      `tables_modele.POLAIRES`, mathtext axis labels in `LIBELLES`; `--defaut` simulates in Python a
      CM read with alpha snapped to the nearest node → « observé palier », staircase polar; `--jobs`).
      `01_LECTURE_TABLES/01_lecture_tables.py`: the 8
      tables declared from the COMMON, DCXP with `fixes={"ipropu": 1}`, DCMG with the polar inverse
      and a justified `rtol=1e-12` (round trip lands within ~13 ULP); `--combinaisons`, `--defaut`
      (one CM value falsified → exit 2). Tests in `tests/test_modele_aero.py` (build into tmp at -O0
      and -O3 -ffast-math; probes, `lire`, and the three script scenarios; skipped without
      gfortran/meson/ninja).
- **`tools/cfd-doe/`** — CFD design of experiments. Phase 1 (done): reduce the input domain
  (`alpha, beta, DL, DM, DN`, degrees) to the **sub-domains actually worth computing**, from the
  trajectory type and the vehicle's symmetries; phase 2 (done): fill them — `cfd-doe remplir`. CLI `cfd-doe domaine ETUDE.yaml | --traj … --sym … --alpha
  BAS HAUT … [--verbose]`, `remplir REMPLISSAGE.yaml`, `check`, `exemple`. Theory in `00_DOC/01_BASE_AERO.md` (strict conversion of
  `BASE.txt`, kept alongside). Layout `src/cfd_doe/{core,data,engine,report,cli}/`, layer rule
  enforced by `tests/test_architecture.py`; `01_EXEMPLE/` is package data. Rich FR, no bold
  (`CFD_DOE_GRAS=1`), table laid out to fit 80 columns. Key points:
    - **Trajectory types (Freeman)** in `data/trajectoires.py`: a variable is active iff the type
      consumes the effort it drives (N←α, Y←β, m←δm, n←δn, l←δl); inactive ones pinned to 0.
      `3DOF_MASSE_PONCTUELLE` and `3DOF_TANGAGE` are distinct types.
    - **Frame choice** (`repere: auto`): polar (αt, φa) with mixed-frame deflections
      (DMB, DNB) when the geometry has rotation order ≥ 3 or is a body of revolution and both
      α, β are active; Cartesian otherwise (only V/H mirrors and 180° rotation are expressible
      there, and a forced Cartesian cruciform reports what it loses).
    - **Fundamental domain as strata** (`core/domaine_fondamental.py`): sign-flip groups split
      recursively on the first flipped variable (`v > 0` with the sub-group, `v = 0` with the
      whole group); in polar, φa arcs are folded into the D_N sector, mirror planes halve
      (δl, δnB), and the αt = 0 axis gets D_N acting on body-frame deflections (a `Secteur`
      constraint for N ≥ 3). Open bounds matter: `]0;20]` keeps plane points from being counted
      twice. All cartesian sign conventions live in `data/geometries.py` — the one file to edit if
      the user's deflection conventions differ.
    - **`--verbose`** prints the *démarche* (trajectory → frame → group → stratification tree →
      gluing) before the table, each leaf ending `→ #k`. It is written *during* `reduire`
      (`engine/demarche.py`, `Reduction.demarche`) from the optional `journal=` of
      `stratifier_signes` / `fusionner` — never recomputed — and `numeroteur` raises if a leaf
      does not fall in exactly one sub-domain, so story and table cannot drift silently.
    - **Plane flight in polar** (`2DOF`/`3DOF_TANGAGE`/`4DOF`, or a custom yaw type): `auto`
      stays Cartesian, but `--repere polaire` is accepted (user request: a downstream code that
      tabulates in (αt, φa) to use the cruciform rotation). φa takes only the flight-plane
      directions (`engine/reduction.py::vol_plan`, `_polaire_plan`), each folded into the sector
      (`representant_phia`: α < 0 → φa = 0 by the 180° rotation for a cruciform, → φa = 60° for 3
      fins). Only symmetries that keep the plane act, so `ordre_groupe` is the Cartesian group seen
      on the free variables (2, not 8). On the axis with one free lateral deflection, only the
      line-preserving elements act (`_apex_plan`). It yields the **same points** as Cartesian,
      renamed — `tests/test_reduction.py::test_vol_plan_polaire_un_representant_par_orbite`.
      `core/symetrie.restreindre` now joins merged names (`miroir H ≡ rotation 180°`).
    - **`cfd-doe domaine --figures [DIR]`** (`report/figures_domaine.py`): two qualitative paper
      figures, the study reduced in **both** frames whatever it retains, Cartesian row above polar:
      `domaine_reperes` (plane (α, β): computed part hatched, deduced grey, symmetry planes dashed,
      lettered pieces with a key saying *all* deflections inside vs *only part* on planes/axis) and
      `domaine_braquages` (deflection plane per letter, convex clipping of box ∩ disk ∩ sector, all
      vector). **SVG by default** (`FORMATS_DOMAINE`, `--formats` overrides). The figure font lacks `∈`: texts say « dans ». A test asserts no missing glyph.
    - **`01_EXEMPLE/completer_table.py`** (package data, copied by `cfd-doe exemple`) is a
      *standalone* script — pandas/numpy/yaml/rich, **no `cfd_doe` import** (enforced in
      `test_architecture.py`) — that fills a results DataFrame up to a full product grid
      ("square" table) by symmetry: each missing node takes `s_g · C(g·x)` from a computed
      image. The group and the coefficient signs come from the export's `symetries` key
      (`engine/reduction.py::symetries_exportees`, signs in `data/geometries.py`:
      `COEFFICIENT_DE`, `COEFFICIENTS_HORS_PAV`), so no sign convention is duplicated. Polar
      αt = 0 is special: φa is a convention there, so nodes are brought back to φa = 0 by
      rotating deflections and (CN, CY)/(Cm, Cn) (§3.2) and bilinearly — or, at the disk rim,
      triangularly — interpolated when the image falls between nodes (flagged in `origine`).
      `domaine=` widens the target beyond the sub-domains' envelope. `exemple_completion.py`
      builds a dummy DOE from a symmetric analytic model and validates every deduced row
      against it (`tests/test_completion.py`). Needs the `[table]` extra (pandas).
    - **`00_DOC/02_REMPLISSAGE.md`** documents phase 2 before any code exists: filling methods
      from full factorial to adaptive/multi-fidelity designs, each with its *hypothesis* and its
      run count on one worked example (double symmetry, 5 angles, 8 Mach, one 3-level engine
      parameter: 81 000 raw → 20 688 full factorial in the sub-domains → 624 order-1 build-up →
      ~360 space-filling). Exact counts are **orbit counts** produced by
      `00_DOC/compter_remplissage.py`, which asserts they equal the grid nodes falling in
      cfd-doe's sub-domains; the space-filling/adaptive figures are flagged as rules of thumb.
      Its six figures (`00_DOC/FIGURES/remplissage_*.png`) come from `00_DOC/generer_figures.py`,
      drawn through `cfd_plot` (install it editable first — it is not a cfd-doe dependency) and
      reading their numbers from `compter_remplissage.py`, never hard-coded.
    - **`cfd-doe remplir REMPLISSAGE.yaml [-v] [--retenu P] [--repere R] [--sortie D]`** fills
      the sub-domains. The file names any number of plans (`type:` factoriel, etoile,
      decomposition, composite_centre, box_behnken, grille_creuse, lhs, halton, adaptatif,
      multi_fidelite), all built and compared; `retenu` goes to `doe.csv` (**tab-separated**,
      columns id/role/table/sous_domaine/[fidelite]/mach/params/variables, plus engine-frame
      alpha/beta/DM/DN in polar). Layers: `core/plans.py` (pure generators on the unit box),
      `core/expression.py` (AST-whitelisted `exclure` conditions, no `eval`),
      `data/remplissage.py` (YAML → `Remplissage`, unknown keys refused), `engine/remplissage.py`
      (`remplir` → `PlanDOE` with role calcul/controle/test, tables and the *démarche*),
      `report/remplissage.py` (Rich) and `report/figures.py` (cfd-plot, optional: without it the
      report and CSV are still written). Three placement rules, each tested: grid plans **filter**
      nodes outside the sub-domains (their images are other grid nodes); structured plans **fold**
      each point onto its representative (`Contexte.replier`) — a half-fraction composite design
      is *not* closed under the vehicle's symmetries because the engine factor never flips, and
      filtering it silently dropped a third of the design; drawn plans sample inside the strata
      with rejection on the disk constraint. A structured plan's deflection box is inscribed in
      the disk. One file serves both frames: other-frame `niveaux` are ignored with a note,
      effect names are aliased (DM ↔ DMB), and `exclure` sees both frames' variables. Grid counts
      reproduce `00_DOC/02_REMPLISSAGE.md` exactly (`tests/test_remplissage.py`).
      Plan types also include `sobol` (Joe–Kuo directions, Gray order, digital shift — prefer
      powers of 2) and `krigeage`: each point placed where the *prior* kriging variance is
      largest given the points already placed **and all their symmetry images** (fixed
      `portee`, so buildable before any run; candidates filtered by `exclure` per condition).
    - **Figures are paper-ready** (`report/figures.py`, cfd-plot `paper` profile, PNG 300 dpi
      + PDF, `sortie.formats`): every panel carries the zone background — computed (blue),
      deduced by symmetry (hatched, labelled with the symmetry on exact slices), out of domain
      (cross-hatched), symmetry planes dashed, planes that are sub-domains on their own drawn
      thick. Hatching is baked into an up-sampled raster, **not** `contourf(hatches=…)`, which
      draws wrong polygons for holed masks (square minus disk). The zone raster is a vectorised
      re-implementation of `Contexte.placer`/`replier` — same order (images, then the αt = 0
      axis rule on each image) — and a test checks it node-for-node against the engine in both
      frames.
    - **`engine/reconstruction.py`** turns a plan's CFD results into **one square table per
      coefficient** on the reference grid over the full (symmetric) domain: grid plans read
      nodes + images (multilinear between coarser levels); star/decomposition sum anchored
      terms `± C(x restricted to the term's factors)` stored in `PlanDOE.termes`
      (cut-HDMR); composite/Box-Behnken a degree-2 Legendre LS; sparse grid the exact Smolyak
      polynomial space; drawn plans ordinary kriging (`core/metamodeles.py`, Matérn 5/2,
      anisotropic ML ranges, smallest nugget that factorises; `portees_communes=True` shares
      ranges across coefficients, ~6× faster); multi-fidelity BF kriging + kriged HF − BF gap.
      Every model sees each run's images (sign-flipped coefficients), so tables are exactly
      symmetric; nodes removed by `exclure` stay NaN for every method. `controle`/`test`
      points give `Tables.ecarts`, the only error measurable for real. `lot_suivant` proposes
      the next adaptive batch (max variance, ranges re-estimated on results). Cartesian only.
    - **`01_EXEMPLE/reconstruire_tables.py`** runs the whole chain with a fictitious CFD (an
      aero model *averaged over the study's symmetry group*, so exactly symmetric whatever the
      geometry): results file written and re-read, tables per plan, error at check points vs
      true error on the grid, simulated adaptive batches, `precision_cout` and `coupes_<COEF>`
      figures. `executer_exemples.py` runs it on the rocket and on `01_EXEMPLE/CAS/` (missile
      3DOF pitch, aircraft 5DOF single plane, shell of revolution forced Cartesian, drone with
      no symmetry, 3-fin rocket). Findings worth knowing: order-1 check points predict the
      table error; metamodel test points are optimistic (×2–4, they avoid the borders);
      structured plans break under `exclure` (rank-deficient polynomial, reported); the
      kriging design beats LHS at ~70 % of the runs. `00_DOC/02_REMPLISSAGE.md` §11 reports
      these numbers; `generer_figures.py` regenerates figures 7–8 through the script.
    - The **orbit test** (`tests/test_reduction.py`) is the guarantee: every grid point's full
      orbit has exactly one image in the sub-domains (polar N = 1, 2, 3, 4, 6; Cartesian over all
      trajectories × geometries). The document's counts (45/78/144/265 §5.3, 63/33 §5.4, 4 200
      §7.4) are reproduced.
- **`tools/cfd-trajcast/`** — rocket flight simulation (trajectory + attitude) + CAD → conference
  video (3D render with chase camera, animated telemetry, titles, MP4). **Linux only**, pip only
  (no Blender app), Python ≥ 3.9 (verified on 3.9, 3.12 and 3.13 + bpy). Built milestone by milestone (J0–J6, all done);
  **each milestone ends with a qualitative review**: `python 02_CONTROLE/generer_controle.py
  --jalon Jn` writes images to `02_CONTROLE/Jn/` (git-ignored except `MANIFESTE.txt`). Done: J0
  (offscreen spike, `00_DOC/04_RENDU_HORS_ECRAN.md`), J1 (conventions, reading, `check`), J2
  (first MP4: `Film`, chase camera, `rendre`/`image`/`diagnostic`) and J3 (multi-view layouts and
  sequence, `sol`/`embarquee` cameras, telemetry panel, titles/banners/logo —
  `00_DOC/03_CAMERA_ET_VIDEO.md`, example `01_EXEMPLE/CONFIG_MULTIVUES.yaml`).
  Layers `core` (NumPy only) → `data` → `engine` → `report` → `cli`, AST-enforced; heavy libs
  confined to one module each (`tests/test_architecture.py`: pyvista → `engine/rendu/pyvista_.py`,
  matplotlib → `engine/telemetrie.py`, trimesh/cascadio → `data/maquette.py`, imageio_ffmpeg/PIL →
  `engine/encodage.py`, PIL also → `engine/montage.py`). mypy strict. Key points:
    - **One internal convention, applied at read time**: ENU local (m), body FRD, Hamilton
      quaternion `(w,x,y,z)` body→ENU. Inputs *declare* theirs (`repere` ENU/NED, quaternion
      `ordre`/`sens`, Euler `sequence` — upper = intrinsic, lower = extrinsic, all 12 —, body
      FRD/FLU, units). **Attitude is mandatory** (quaternion or Euler): no attitude →
      `ErreurAttitude`; it is never derived from velocity (user decision).
    - **Default checks assume no flight profile** (user decision: some trajectories have no
      ascent) — no "it must climb", no ground. The nose/velocity coherence check is **opt-in**
      (`check --coherence`, `verifier(..., coherence=True)`): median nose/velocity angle on the
      ascent > 20° → alert, and the conversion is *replayed* under the other conventions
      (`convertir(brut, decl)`) to name the one that would make the flight coherent.
    - `core/vol_reference.py` is an **analytic** flight (straight powered line, then ballistic;
      nose along velocity, 90°/s roll) — the example ships it as ENU+quaternion and NED+Euler,
      and every reader must land on the exact values.
    - **CAD** (`data/maquette.py`): STEP via cascadio (extra `[step]`), which converts to metres
      — `unite` is then only a check against the STEP's own `LENGTH_UNIT`; meshes need `unite`.
      `axe_nez`/`axe_haut` map CAD axes to FRD; `origine` (base, centre_volume, or a point in the
      file's unit) is the point the trajectory tracks. `longueur_imposee` scales a reduced model
      (the shipped `01_EXEMPLE/MAQUETTE/Aim9.stp` is 38.1 mm long, nose at x = 0 → `axe_nez: "-X"`).
    - **Rendering** (`engine/`): `planifier` turns trajectory + `ConfigVideo` + view into a
      `Plan` (one row per frame: flight time, pose, camera); `Scene` holds what doesn't change;
      a `Moteur` (Protocol; `MoteurPyVista` today, bpy later) only draws. **Floating origin**:
      every frame is translated so the rocket sits at (0,0,0) — a camera is just an offset.
      The chase camera follows the *route* (smoothed horizontal velocity), never the attitude,
      so roll doesn't spin the image. `Film.image(t)` plans from t0 to t because the camera
      smoothing depends on history. The geometric test (`tests/test_rendu.py`) compares the
      rendered silhouette bbox with the pinhole projection of the vertices (±2.5 px, GPU or
      llvmpipe alike) — it fails on a conjugated quaternion.
    - **Multi-view** (J3): `core/disposition.py` turns a `Disposition` (unique / incrustation /
      grille / libre, plus a `telemetrie` strip) into ordered pixel `Case`s with even sizes; each
      view is rendered at its case size (`MoteurPyVista` keeps one Plotter per size). The `Plan`
      carries one camera track per view, one layout per `sequence` step and per-frame crossfade
      weights; `_Atelier` (engine/pipeline.py) composes: views → telemetry → paste → blend →
      `Habillage` overlays (Pillow text drawn once as RGBA layers, opacity varied per frame).
      `Film.image(t)` must use the **full** video's duration and flight range for overlays and
      the panel axis, and `recaler` recomputes camera tracks after snapping the last frame to t.
      Telemetry acceleration is *kinematic* (1 g in free fall), documented as such. The panel
      shows **any** quantity (`data/configuration.Grandeur`, 1–8 rows): a computed one
      (`CALCULEES`: altitude, vitesse, mach, acceleration, incidence_totale) or any numeric column
      of the trajectory (`Trajectoire.donnees` keeps *all* of them, attitude included) with
      label/unit text/factor/decimals/colour/axis range. Labels are shown verbatim and shrunk to
      the space the widest value of their row leaves.
    - **`ensemble` view** (user request): a fixed-camera "macro" view of the whole flight in a
      graduated **NED** box (Nord/Est/Bas, Bas negative above ground) — grey full path, orange
      flown path, ground track, named events, and the rocket **enlarged** (factor printed in the
      view, `echelle_ensemble`). It does not use the floating origin (absolute NED coords; no
      `PisteCamera`, `Plan.ensembles` instead). `cadre_ensemble` fits the 8 corners of the
      *rounded* tick box exactly, not a bounding sphere. True proportions are kept: a near-
      vertical flight gets a tall cell (`01_EXEMPLE/CONFIG_ENSEMBLE.yaml`), never stretched axes.
      Title defaults to the **top** (`montage.position_titre`) — centred, it hid the rocket —
      and is centred on the main view, not on the whole frame.
    - **J4**: `style` section with presets (`sobre` = the J2–J3 look and the default, so old
      files render unchanged; `conference` = sky gradient, procedural seamless terrain texture
      (`engine/textures.py`, FFT-filtered noise), sun light, PBR-ish rocket, smoke trail). The
      trail is a tube from the nozzle whose last point is the *current* instant (the path is
      sampled at 60 Hz, i.e. metres behind at 300 m/s), widening and fading with age;
      `trainee.jusqu_a` takes a time or an **event name**. Depth peeling is enabled with a trail:
      PBR + translucency otherwise leaves ghost fins. Cameras `orbite` (world-frame azimuth,
      °/s of video) and `images_cles` (route-frame, smoothstep between keys, shortest-arc azimuth).
      Slow motion (`video.ralentis`, `core/temps.py`): playback speed per *flight* interval with
      linear ramps, flight time integrated frame by frame. `01_EXEMPLE/vol_virage.csv` (70° turn)
      is what actually exercises route smoothing (`test_poursuite_lisse_le_virage`).
    - **J4b (user feedback: flared jets, several phases, colour, genericity)**: `propulsion` section
      — nozzles (FRD), radius, **phases** bounded by times or event names, each with a `Jet`
      (flame and/or smoke; presets `JETS`: fusee_poudre, fusee_liquide, postcombustion, reacteur,
      panne…). Geometry is NumPy in `engine/jets.py`: flame = unlit surface of revolution that
      flares then closes, white core, Mach diamonds, deterministic flicker; smoke = world-frame
      tube whose radius grows with **distance behind the nozzle** (cone) and age, fades in behind
      the flame, keeps the jet of its *emission* phase. `style.trainee` is legacy (converted to a
      smoke-only phase) and no longer on in `conference`. `core/manoeuvres.py` is a point-mass
      flight generator (lift n·g, thrust, V² drag, bank/heading/slope controllers) used by
      `01_EXEMPLE/SCENARIOS/generer_scenarios.py` (aircraft STL built by hand — trimesh's convex
      hull and fix_normals need SciPy, which is not a dependency). Genericity: cameras frame
      `Maquette.taille` (max of length/span), `style.sol.altitude`, aircraft telemetry
      (facteur_de_charge, cap, pente, Euler angles), events from a CSV, event names in
      `sequence`. Under EGL only SSAA anti-aliases (FXAA silently falls back, MSAA does nothing);
      Phong material by default because PBR without an environment map goes black when backlit.
    - **J5**: `trajectoire: {source: rocketpy, script, fonction}` runs the user's script (cwd =
      its folder) and reads the returned `Flight` by **attribute access only** (`data/rocketpy_.py`
      never imports RocketPy, which needs Python ≥ 3.10; extra `[rocketpy]` is marker-gated).
      RocketPy conventions, verified on a real sim: ENU, `z` is ASL (minus `env.elevation`),
      quaternion e0..e3 body→inertial, body `z` = nose → FRD by cyclic permutation
      (x_FRD=z, y_FRD=x, z_FRD=y). Events: rail exit, burnout, apogee, parachutes, impact; Flight
      Functions sampled as columns under their RocketPy names. Disk cache (`data/cache.py`,
      `.npz` keyed by SHA-256 of every input + lib versions, `$CFD_TRAJCAST_CACHE`, `0` disables)
      for STEP tessellation and RocketPy flights (key includes input files of the script's folder;
      `--sans-cache` otherwise). **Parallel render** (`-j`, `Film.rendre(processus=)`): the plan is
      computed once, frames depend only on their index, so contiguous chunks are rendered+encoded
      in `spawn` worker processes (EGL does not survive fork) and joined with ffmpeg concat
      `-c copy` (`encodage.concatener`); test compares serial vs parallel frame by frame. On this
      8-core iGPU laptop the gain is modest (CPU-bound: x264 `medium` ≈ 140 ms·core per 1080p
      frame) — numbers in `00_DOC/06_ROCKETPY_ET_PERFORMANCE.md`. Also `video.de`/`video.a`
      (time or event name), `cfd-trajcast exporter` (trajectory → CSV in internal conventions).
      User decision: examples and scenarios always use the supplied Aim9 CAD, aircraft
      trajectories included (the procedural aircraft STL is gone).
    - **J6** (`00_DOC/07_4K_NUIT_BLENDER.md`): 4K works unchanged (every overlay is sized in
      fractions of the image height). `nuit` style preset: stars, bloom (`lueur`), flame light
      (`eclairage.jets`), dark overview. Stars use a **transparent render + NumPy sky composite**
      (`engine/effets.composer_ciel`; alpha is premultiplied coverage) — depth-buffer readback was
      126 ms/frame at 4K and does not mark the background. Optional **Blender engine**
      (`moteur: {type: blender, rendu: eevee|cycles}`, `engine/rendu/blender.py`, factory
      `engine/rendu/creer_moteur`): bpy wheels pin one Python (bpy 5.x = 3.13 only, extra
      `[blender]`); the wheel's TBB must be preloaded (`RTLD_GLOBAL`) or `import bpy` fails on a
      TBB symbol from the older system lib. Blender renders the 3D on a transparent film and
      shares sky/stars/bloom with PyVista; `ensemble` views stay on PyVista. Event banners now
      move below the title while it shows (`Habillage._eviter_titre`). `00_DOC/02_CONFIGURATION.md`
      is the full YAML key reference, enforced by `tests/test_doc_configuration.py` (AST of every
      `_cles(...)` set). CI: `cfd-trajcast` job in `.github/workflows/ci.yml` (3.9 + 3.12, EGL
      then xvfb fallback, `diagnostic` must pass so render tests cannot silently skip, preview
      MP4 artefact).
    - **Standalone overview** (user request: the `ensemble` view on its own): `VueEnsemble`
      (`engine/ensemble.py`, exported at top level; `cfd-trajcast ensemble CONFIG [--video]`,
      example `01_EXEMPLE/vue_ensemble.py`). `.svg()` writes the whole flight as an **SVG with no
      3D engine** (`engine/schema_ensemble.py`, pure NumPy + SVG text, ~0.1 s): same camera
      (`cadre_ensemble`), same graded box (`core/camera.boite_ensemble`, now shared with the
      PyVista engine) and colours (`scene.THEMES_ENSEMBLE`); `core/camera.projeter` is tested
      against VTK's `WorldToDisplay` (< 0.01 px). Rocket drawn by painter's algorithm (STL
      winding is not trusted), poses default to events thinned on screen, image cropped to its
      content (true proportions). `.rendre()` is a one-view `Film` over the **whole** flight
      (`video.de/a` ignored), telemetry as a right band; a right-corner logo moves left there.
    - **Paper figure and render-free video of the overview** (`engine/figure_ensemble.py`, the only
      module importing `cfd_plot`/`mpl_toolkits`; `VueEnsemble.figure()` / `.animer()`;
      `cfd-trajcast ensemble CONFIG` now writes PDF+SVG+PNG, `--video --sans-rendu` the animated
      figure, `--schema` the old dependency-free SVG — also the automatic fallback without
      cfd-plot). Plotted as x = Est, y = Nord, z = Bas with z **inverted**: (Est, Nord, Haut)
      displayed is right-handed — Nord on x would mirror the flight (tested). Ortho by default,
      true proportions, `--largeur-cm` is the final width *including* the legend (3 passes of
      `fit_box3d` + `bbox3d`). Events get an Okabe-Ito colour + marker shape and live in the
      legend with their instant; default poses closer than one model length are dropped; numbers
      French (thin space, U+2212, decimal comma); no title (the terminal prints a proposed
      caption). The animation reuses `instants_de_vol` (video config, ralentis) and
      `fit_box3d(ax)` zoom-only since the frame size is imposed. `00_DOC/08_FIGURE_ET_ANIMATION.md`.
    - **`repere: ned | ned_local`** on an `ensemble` view: `ned_local` shifts only the vertical
      origin to the start point (Bas = 0 at departure, N/E untouched), axes stay classic NED
      ("Bas local (m)"). `core/camera.origine_ensemble` / `ned_ensemble` /
      `boite_ensemble(origine=)`; honoured by PyVista, the SVG schema and the figure.
    - **Interactive GUI** (`cfd-trajcast gui [CONFIG]`, `00_DOC/09_INTERFACE.md`, milestones G0–G6,
      control `02_CONTROLE/generer_controle.py --jalon G`): PyQt5 (wheel; PyQt4 is impossible on
      Python 3.9), extra `[gui]` = PyQt5 + pyvistaqt (+ local cfd-plot). New layer `gui/` (same level as
      `cli`, the only one importing PyQt5/qtpy; `cli` may import it, lazily). All logic is Qt-free and
      tested headless: `core/reperes_locaux.py` (FRD, NED local, aero frame with α = atan2(w,u),
      β = asin(v/V) from v_air = v_ground − wind, kinematic frame), `data/vent.py` + `data/cdg.py`
      (YAML sections `vent` — `vz: haut|bas` **mandatory**, `sens: vers|depuis` — and `cdg` — 1 column
      along the axis or 3 in CAD axes, `reference: nez|culot|origine`), `engine/etat_vol.py`
      (`EtatVol`: every CSV column + computed series; a CSV column named like a computed one gets
      the key `"<nom> (fichier)"`; trajectory positions **are** the CDG: vertices placed by
      `pos + R·e·(s − cdg)`), `engine/vue3d_mpl.py` (`VueMpl`, any `Figure`), `engine/courbes.py`,
      `engine/rendu/pyvista_interactif.py` (`VueVtk`, double-click to seek). **Zoom** (`zoomer`,
      `cadrer_engin`, `vue_entiere`, `suivre_engin`, same contract on both views): in Matplotlib it
      narrows the axis *limits* — longest side first, so a near-vertical flight seen up close gets a
      cubic box (refit via `fit_box3d`, cached per box shape) — keeping one scale on all axes; the wheel zooms
      toward the flight point under the cursor and one least-squares step keeps it there exactly
      (ortho is linear); Matplotlib's own right-drag zoom is disabled (it can stretch one axis);
      overflow is clipped with `axlim_clip` on Matplotlib ≥ 3.10 only, the ground polygon by hand. Hard-won traps:
      (1) an OpenFOAM `LD_LIBRARY_PATH` makes the loader mix system Qt with the wheel's Qt
      (abort) → `gui/_qt.preparer_qt()` preloads the wheel's Qt libs with RTLD_GLOBAL before any
      PyQt5 import; (2) with PyQt5 installed, **pyplot picks the Qt backend by itself** and
      loaded Qt into figure/video commands → `engine` never uses pyplot (`Figure` +
      `FigureCanvasAgg`), the CLI sets `MPLBACKEND=Agg` except for `gui`, `tests/conftest.py`
      too; (3) VTK in Qt under XWayland ran at 2 fps until `vblank_mode=0`. VTK is only offered
      after a subprocess probe (`python -m cfd_trajcast.gui.sonde_vtk`; broken OpenGL kills the
      process), video export runs in a subprocess (`gui/tache_video.py` via QProcess, cancel =
      kill). Qt tests run `offscreen` with QSettings redirected (NativeFormat too — otherwise
      they write to the user's `~/.config`; asserted). mypy: three PyQt5-stub error codes are
      disabled for `cfd_trajcast.gui.*` only.
    - J0 findings that bind later milestones: OSMesa is **not** in the VTK wheel (crashes) → EGL,
      then EGL llvmpipe, then xvfb (without `DISPLAY` the engine sets
      `VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow` itself — `WAYLAND_DISPLAY` must not count,
      VTK only speaks X or EGL); imageio-ffmpeg silently resizes
      1080 → 1088 unless `macro_block_size=1`; encoding, not rendering, is the bottleneck.

- **`tools/installation/installer_lanceurs.py`** — not a package: a stdlib-only (3.9+) script run
  after every `pip install` with the same `python3`. It rewrites every `tools/*` console script
  to `#!/usr/bin/env python3` (pip bakes `sys.executable` and has no option or post-install hook;
  setuptools rewrites any hand-written `#!…python` too), but only when the `python3` on `PATH`
  imports the package (`--forcer` overrides), and never touches a non-pip script. It also
  generates **static** bash completion: each CLI's argparse parser is captured by intercepting
  `parse_args` (run with `--help`, since `cfd-stats` prints help on an empty line without parsing)
  and turned into `~/.local/share/cfd-framework/completion.bash`, sourced from one marked
  `~/.bashrc` line. Tests: `pytest tools/installation` (real bash runs the completion).

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
