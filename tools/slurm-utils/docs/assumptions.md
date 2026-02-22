# Wait-Time Estimation -- Assumptions & Methodology

## Why this is hard

Slurm's scheduler (with the `backfill` plugin) makes complex decisions based
on priority, fair-share, resource availability, reservations, QOS limits, and
more.  **Slurm does not expose an estimated start-time** for pending jobs via
any standard command.  Any wait-time number produced by this tool is therefore
a **heuristic estimate** -- useful for comparing partitions, but not a
guarantee.

## Heuristic algorithm

For each eligible partition, the tool performs the following steps:

### 1. Collect cluster state

```
sinfo  -o "%P|%a|%l|%D|%T|%c|%m|%f|%N|%C"   # partition summary
squeue -o "%i|%j|%P|%T|%u|%M|%l|%D|%C|%m|%r"  # all running + pending jobs
```

From `sinfo` we extract per-partition:

- Total nodes, CPUs per node, memory per node.
- Idle / allocated / other / total CPU counts (the `%C` field: `A/I/O/T`).
- Partition availability (`up` / `down`) and time limit.

From `squeue` we extract per-partition:

- Running jobs: CPU count, elapsed time (`%M`), time limit (`%l`).
- Pending job count.

### 2. Eligibility filter

A partition is eligible if **all** of the following hold:

| Condition | Check |
|-----------|-------|
| Partition is `up` | `sinfo AVAIL == "up"` |
| Enough total CPUs | `requested_cpus <= total_cpus` |
| Memory fits | `requested_mem <= memory_per_node * ceil(requested_cpus / cpus_per_node)` |
| Walltime fits | `requested_walltime <= partition_timelimit` |

### 3. Wait-time estimate

**Case A -- Immediate start (high confidence)**

If `idle_cpus >= requested_cpus` **and** `pending_jobs == 0`:

> Estimated wait = **0** (job can start immediately).

**Case B -- Idle CPUs available but pending queue is non-empty (medium confidence)**

If `idle_cpus >= requested_cpus` but `pending_jobs > 0`:

> Estimated wait = `pending_count * 60 s`
>
> (Assumes each pending job ahead delays you by ~1 minute on average due to
> scheduling overhead and priority ordering.  This is intentionally
> conservative.)

**Case C -- Must wait for running jobs to finish (medium confidence)**

If `idle_cpus < requested_cpus`:

1. Sort running jobs on this partition by **remaining time** ascending, where:
   ```
   remaining = time_limit - time_used
   ```
   (We use the job's full `--time` limit as a conservative upper bound.)

2. Accumulate freed CPUs, starting from idle CPUs:
   ```
   freed = idle_cpus
   for each job (ascending remaining time):
       freed += job.cpus
       if freed >= requested_cpus:
           wait = job.remaining_time
           break
   ```

3. Add a **pending-queue penalty**:
   ```
   median_remaining = median(remaining times of all running jobs)
   penalty = pending_count * median_remaining / total_nodes
   wait += penalty
   ```

**Case D -- Unknown**

If there is insufficient data (no running jobs, partition empty, etc.):

> Estimated wait = **unknown**, confidence = **low**.

### 4. Ranking

Eligible partitions are sorted by:

1. Estimated wait (ascending; `unknown` treated as infinity).
2. Pending job count (ascending).
3. Idle CPUs (descending).

The first partition in the sorted list is the **recommendation**.

## Key assumptions

1. **FIFO approximation**: We treat scheduling as roughly FIFO within a
   partition.  In practice, Slurm uses priority + backfill, so small jobs
   often start earlier than their FIFO position.

2. **Conservative remaining time**: We use `time_limit - time_used` as
   remaining time.  Many jobs finish well before their limit, so actual waits
   are often shorter.

3. **No reservation awareness**: We do not query `scontrol show reservation`.
   If the cluster has active reservations, the estimate may be off.

4. **No fair-share modelling**: We do not model the user's fair-share score.
   Users with high fair-share may start sooner than the estimate; users with
   low fair-share may wait longer.

5. **Single-partition jobs**: We assume the job targets a single partition.
   Multi-partition submissions (e.g. `--partition=a,b`) are not modelled.

6. **Pending penalty is coarse**: The `pending_count * median_remaining /
   total_nodes` formula is a rough proxy.  It does not account for
   heterogeneous job sizes or priorities in the pending queue.

7. **Site-specific**: Partition names, QOS tiers, and weights vary by cluster.
   The tool makes no assumptions about naming conventions.

## Improving the estimate

- **Accurate `--time`**: Always set `--time` as close to real runtime as
  possible.  This helps Slurm's backfill scheduler and makes the heuristic
  more useful.
- **Use `sprio`**: Check your priority with `slurm-utils prio`.  Higher
  priority means shorter actual wait.
- **Check `sshare`**: If your group's fair-share is depleted, expect longer
  waits regardless of the heuristic.
