# ParaView state + snapshot from CLI

Run a ParaView state file (`.pvsm`) with custom data filenames and export a snapshot from the command line, without opening the GUI.

## Workflow (what you do in GUI once, then from CLI)

1. **In ParaView GUI**
   - Build your visualization (load data, apply filters, set view/camera, color maps, etc.).
   - Save state: **File → Save State** → choose a `.pvsm` file.
   - When saving, the state stores the paths of the data files you had open.

2. **From CLI (this tool)**
   - Load that same `.pvsm` and **replace** the data files with new paths (your new runs).
   - Render and **export a snapshot** (e.g. PNG) in one shot.

So: one state file, many datasets → same view and filters, different data and output images.

## Requirements

- ParaView installed and `pvpython` on your `PATH` (usually in the same `bin` directory as `paraview`).

## Usage

Run with **pvpython** (ParaView’s Python):

```bash
pvpython run_state_and_snapshot.py STATE.pvsm OUTPUT.png [FILE1 [FILE2 ...]]
```

Or use the shell wrapper (same arguments):

```bash
./run_state_snapshot.sh STATE.pvsm OUTPUT.png FILE1 FILE2 ...
```

- **STATE.pvsm** – Path to your saved state file.
- **OUTPUT.png** – Path for the exported image (extension sets format: `.png`, `.jpg`, `.tif`, etc.).
- **FILE1, FILE2, ...** – Data files to use **in the same order as “Choose File Names”** in the GUI when loading the state.  
  The script maps them to the readers in the state by order (first file → first reader, etc.).

### Alternative: search by directory

If you prefer to point ParaView to a directory and let it find files by **basename** (as in “Search files under specified directory”):

```bash
pvpython run_state_and_snapshot.py STATE.pvsm OUTPUT.png --data-dir /path/to/data
```

Files in that directory must have the same basenames as in the state (e.g. `result_001.vtk`).

### Optional: image resolution

```bash
pvpython run_state_and_snapshot.py STATE.pvsm OUTPUT.png FILE1 --resolution 1920 1080
```

## Examples

```bash
# One reader in state, one file
pvpython run_state_and_snapshot.py flow.pvsm frame.png /data/case/result.vtk

# Two readers (e.g. mesh + solution), two files
pvpython run_state_and_snapshot.py flow.pvsm frame.png mesh.vtk solution.vtk

# Use data directory (files named as in state)
pvpython run_state_and_snapshot.py flow.pvsm frame.png --data-dir /data/case/result

# High-res PNG
pvpython run_state_and_snapshot.py flow.pvsm frame.png data.vtk --resolution 2560 1440
```

## File order

The order of **FILE1, FILE2, ...** must match the order of the “custom filename” entries in the Load State dialog (same order as the readers in the state). If the state has 2 readers and you pass 2 files, the first file is assigned to the first reader, the second to the second reader.

## Batch / automation

You can loop over cases and export one snapshot per case:

```bash
for d in case_001 case_002 case_003; do
  pvpython run_state_and_snapshot.py my_state.pvsm "output_${d}.png" "${d}/result.vtk"
done
```

For parallel runs, use **pvbatch** instead of **pvpython** (e.g. with `mpirun`), and the same script and arguments.

## Integration with CFD_FRAMEWORK

From a post-processing script (e.g. in `10_SCRIPT/POST_TRAITEMENT/BASH/`), call the wrapper or pvpython:

```bash
pvpython "${CFD_FRAMEWORK}/tools/paraview/run_state_and_snapshot.py" \
  "${CASE_PATH}/state.pvsm" \
  "${CASE_PATH}/postProcessing/snapshot.png" \
  "${CASE_PATH}/result.vtk"
```

Or use `run_state_snapshot.sh` if the tools directory is on your path.
