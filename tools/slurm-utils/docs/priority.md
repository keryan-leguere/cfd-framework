# Understanding Slurm Job Priority

## Overview

Slurm uses a **multifactor priority plugin** to assign a single numeric
priority to every pending job.  Higher priority means the job will be
scheduled sooner.  The priority score is a weighted sum of several
independent factors, each normalised to 0.0 -- 1.0:

```
Job_priority =
      PriorityWeightAge        * age_factor
    + PriorityWeightAssoc      * assoc_factor
    + PriorityWeightFairshare  * fairshare_factor
    + PriorityWeightJobSize    * job_size_factor
    + PriorityWeightPartition  * partition_factor
    + PriorityWeightQOS        * qos_factor
    + SUM( TRES_weight_i * TRES_factor_i )
    - nice_factor
    + site_factor
```

The **weights** (unsigned 32-bit integers) are set by the cluster
administrator in `slurm.conf` or via `sacctmgr`.

## Factor descriptions

| Factor        | What it measures                                                 |
|---------------|------------------------------------------------------------------|
| **Age**       | Time the job has been waiting.  Grows linearly up to `PriorityMaxAge`. |
| **Association** | Per-user / per-account association priority.                   |
| **Fair-share** | How much of your group's allocation you have recently consumed. Under-users get a boost; heavy users are penalised. |
| **Job Size**  | Number of requested resources (CPUs, nodes).  Larger jobs may receive higher priority so they are not starved by many small jobs. |
| **Nice**      | User-adjustable penalty (like Unix nice).  Default 0; positive values lower priority. |
| **Partition**  | Administrator-assigned weight per partition.                    |
| **QOS**       | Quality-of-Service tier weight.                                  |
| **TRES**      | Trackable Resources (GPU count, memory, licenses, ...).          |
| **Site**      | Arbitrary site-specific plugin value.                            |

## Backfill scheduling

Even if your job has lower priority, the scheduler can **backfill** it
into idle resources as long as it finishes before the next higher-priority
job is expected to start.  Therefore:

- **Accurate `--time` estimates** help the scheduler backfill your job.
- Short, small jobs benefit most from backfill.

## Useful Slurm commands

| Command              | Purpose                                             |
|----------------------|-----------------------------------------------------|
| `sprio`              | Show your pending jobs' priority breakdown.          |
| `sprio -w`           | Show the priority weights configured on the cluster. |
| `sprio -l`           | Long (detailed) priority output.                     |
| `sshare -l`          | Show fair-share values for your account.             |
| `sacctmgr show qos`  | List QOS tiers.                                     |

Or use the `slurm-utils` wrapper:

```bash
slurm-utils prio            # your pending jobs
slurm-utils prio -j 12345   # specific job
```
