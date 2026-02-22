# slurm-utils

Slurm command aliases, priority explorer, and queue recommender -- all with
**Rich**-formatted terminal output.

## Installation

```bash
cd tools/slurm-utils
pip install -e .
# or with dev extras:
pip install -e ".[dev]"
```

After installation the `slurm-utils` command is available on your `PATH`.

## Quick start

```bash
# Show your jobs in a Rich table
slurm-utils queue          # or: slurm-utils sq
slurm-utils myjobs         # shortcut for queue --me

# Partition / node overview
slurm-utils info            # or: slurm-utils si

# Priority breakdown for your pending jobs
slurm-utils prio

# Cancel a job (with confirmation)
slurm-utils cancel 12345

# Hold / release a pending job
slurm-utils hold 12345
slurm-utils release 12345

# Recommend the best partition for a new job
slurm-utils recommend -n 128 -t 6:00:00
slurm-utils recommend -n 64 -m 4G -t 12:00:00
slurm-utils recommend -n 256 -t 4:00:00 --exclude debug
```

## Subcommands

| Command     | Alias    | Description                                  |
|-------------|----------|----------------------------------------------|
| `queue`     | `sq`     | Show the job queue (`squeue` wrapper)         |
| `myjobs`    |          | Show only your own jobs                       |
| `info`      | `si`     | Partition / node summary (`sinfo` wrapper)    |
| `prio`      | `priority` | Priority breakdown (`sprio` wrapper)        |
| `cancel`    |          | Cancel job(s) with confirmation               |
| `hold`      |          | Hold a pending job                            |
| `release`   |          | Release a held job                            |
| `recommend` |          | Recommend best partition + wait-time estimate |

## Queue recommender

The `recommend` subcommand queries `sinfo` and `squeue` in real time, filters
eligible partitions, and ranks them by estimated wait time.

```
slurm-utils recommend -n <ntasks> -t <walltime> [-m <memory>]
```

**Example output:**

```
┌─────────────── Requested Resources ───────────────┐
│ CPUs:     128                                      │
│ Memory:   any                                      │
│ Walltime: 6:00:00                                  │
└───────────────────────────────────────────────────-┘

        Eligible Partitions (3)
┌───────────┬───────┬──────────┬──────────┬─────────┬─────────┬──────────┬────────────┬─────────┐
│ PARTITION │ NODES │ TOTAL .. │ IDLE ..  │ RUNNING │ PENDING │ EST.WAIT │ CONFIDENCE │         │
├───────────┼───────┼──────────┼──────────┼─────────┼─────────┼──────────┼────────────┼─────────┤
│ compute   │    20 │     960  │     256  │      12 │       3 │  < 1 min │ medium     │ <-- best│
│ large     │    10 │    1280  │      64  │       8 │       7 │   ~2.3 h │ medium     │         │
│ gpu       │     4 │     192  │     128  │       1 │       0 │  < 1 min │ high       │         │
└───────────┴───────┴──────────┴──────────┴─────────┴─────────┴──────────┴────────────┴─────────┘

┌─────────────────── Recommendation ────────────────────┐
│ Partition:      compute                                │
│ Est. wait:      < 1 min  (medium confidence)           │
│ Idle CPUs:      256 / 960                              │
│ Pending ahead:  3 jobs                                 │
└───────────────────────────────────────────────────────-┘
```

See [docs/assumptions.md](docs/assumptions.md) for the wait-time heuristic and
its assumptions.

## Understanding priority

Slurm assigns a numeric priority to every pending job based on age,
fair-share, partition weight, QOS, job size, and more.  The `prio` subcommand
prints a Rich table of `sprio` output together with a short explanation.

See [docs/priority.md](docs/priority.md) for a full description of the
multifactor priority formula.

## Shell aliases (optional)

If you want short aliases in your shell, add to your `~/.bashrc`:

```bash
alias sq='slurm-utils queue'
alias si='slurm-utils info'
alias myjobs='slurm-utils myjobs'
alias spri='slurm-utils prio'
alias scanc='slurm-utils cancel'
```

## Requirements

- Python >= 3.12
- `rich`
- A working Slurm installation (the tool calls `squeue`, `sinfo`, `sprio`,
  `scancel`, `scontrol` via `subprocess`).

## Development

```bash
pip install -e ".[dev]"
ruff check src/
pytest
```
