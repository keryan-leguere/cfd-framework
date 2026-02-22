"""Main CLI entry-point for slurm-utils.

Usage::

    slurm-utils <subcommand> [options]

Subcommands
-----------
queue (sq)      Show the job queue (default: current user).
info  (si)      Show partition / node summary.
myjobs          Shortcut for ``queue --me``.
prio            Show priority breakdown for pending jobs.
cancel          Cancel one or more jobs (with confirmation).
hold            Hold a pending job.
release         Release a held job.
recommend       Recommend the best partition for a new job.
"""

from __future__ import annotations

import argparse
import sys

from slurm_utils.display import console, print_error


def _add_queue_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("queue", aliases=["sq"], help="Show job queue (squeue wrapper)")
    p.add_argument("-u", "--user", default=None, help="Filter by user (default: $USER)")
    p.add_argument("-p", "--partition", default=None, help="Filter by partition")
    p.add_argument("-j", "--job", default=None, help="Show a specific job ID")
    p.add_argument("-a", "--all", action="store_true", help="Show all users' jobs")
    p.set_defaults(func=_cmd_queue)


def _add_myjobs_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("myjobs", help="Show only your own jobs")
    p.set_defaults(func=_cmd_myjobs)


def _add_info_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("info", aliases=["si"], help="Show partition summary (sinfo wrapper)")
    p.add_argument("-p", "--partition", default=None, help="Filter by partition")
    p.add_argument("-N", "--nodes", action="store_true", help="Node-centric view")
    p.set_defaults(func=_cmd_info)


def _add_prio_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("prio", aliases=["priority"], help="Show priority breakdown (sprio wrapper)")
    p.add_argument("-j", "--job", default=None, help="Specific job ID")
    p.add_argument("-u", "--user", default=None, help="Filter by user (default: $USER)")
    p.add_argument("--no-explain", action="store_true", help="Hide the explanation panel")
    p.set_defaults(func=_cmd_prio)


def _add_cancel_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("cancel", help="Cancel job(s) (scancel wrapper)")
    p.add_argument("jobids", nargs="+", help="Job ID(s) to cancel")
    p.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    p.set_defaults(func=_cmd_cancel)


def _add_hold_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("hold", help="Hold a pending job")
    p.add_argument("jobid", help="Job ID to hold")
    p.set_defaults(func=_cmd_hold)


def _add_release_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("release", help="Release a held job")
    p.add_argument("jobid", help="Job ID to release")
    p.set_defaults(func=_cmd_release)


def _add_recommend_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("recommend", help="Recommend best partition for a job")
    p.add_argument("-n", "--ntasks", type=int, required=True, help="Number of tasks / cores")
    p.add_argument("-m", "--mem", default=None, help="Memory requirement (e.g. '4G', '4096M')")
    p.add_argument("-t", "--time", required=True, dest="walltime", help="Wall-clock time (e.g. '4:00:00')")
    p.add_argument("-p", "--partition", nargs="*", default=None, help="Restrict to these partitions")
    p.add_argument("--exclude", nargs="*", default=None, help="Exclude these partitions")
    p.set_defaults(func=_cmd_recommend)


# -----------------------------------------------------------------------
# Subcommand implementations
# -----------------------------------------------------------------------

def _cmd_queue(args: argparse.Namespace) -> None:
    from slurm_utils.parsers import SQUEUE_FORMAT, parse_squeue
    from slurm_utils.runner import SlurmCommandError, current_user, run_slurm
    from slurm_utils.display import print_jobs

    argv = ["squeue", "-o", SQUEUE_FORMAT]
    if args.job:
        argv += ["-j", args.job]
    elif not args.all:
        argv += ["-u", args.user or current_user()]
    if args.partition:
        argv += ["-p", args.partition]

    try:
        res = run_slurm(argv)
    except SlurmCommandError as exc:
        print_error(str(exc))
        raise SystemExit(1) from exc

    jobs = parse_squeue(res.stdout)
    title = "Job Queue"
    if not args.all and not args.job:
        title += f" ({args.user or current_user()})"
    print_jobs(jobs, title=title)


def _cmd_myjobs(args: argparse.Namespace) -> None:
    args.user = None
    args.partition = None
    args.job = None
    args.all = False
    _cmd_queue(args)


def _cmd_info(args: argparse.Namespace) -> None:
    from slurm_utils.parsers import SINFO_FORMAT, parse_sinfo
    from slurm_utils.runner import SlurmCommandError, run_slurm
    from slurm_utils.display import print_partitions

    argv = ["sinfo", "-o", SINFO_FORMAT]
    if args.partition:
        argv += ["-p", args.partition]
    if args.nodes:
        argv.append("-N")

    try:
        res = run_slurm(argv)
    except SlurmCommandError as exc:
        print_error(str(exc))
        raise SystemExit(1) from exc

    parts = parse_sinfo(res.stdout)
    print_partitions(parts)


def _cmd_prio(args: argparse.Namespace) -> None:
    from slurm_utils.parsers import SPRIO_FORMAT, parse_sprio
    from slurm_utils.runner import SlurmCommandError, current_user, run_slurm
    from slurm_utils.display import print_priority

    argv = ["sprio", "-o", SPRIO_FORMAT]
    if args.job:
        argv += ["-j", args.job]
    else:
        argv += ["-u", args.user or current_user()]

    try:
        res = run_slurm(argv)
    except SlurmCommandError as exc:
        print_error(str(exc))
        raise SystemExit(1) from exc

    records = parse_sprio(res.stdout)
    print_priority(records, explain=not args.no_explain)


def _cmd_cancel(args: argparse.Namespace) -> None:
    from slurm_utils.runner import SlurmCommandError, run_slurm

    ids_str = ", ".join(args.jobids)
    if not args.yes:
        console.print(f"[bold yellow]Cancel job(s): {ids_str}?[/bold yellow]")
        answer = console.input("[bold]Confirm (y/N): [/bold]").strip().lower()
        if answer not in ("y", "yes"):
            console.print("[dim]Cancelled.[/dim]")
            return

    try:
        run_slurm(["scancel", *args.jobids])
    except SlurmCommandError as exc:
        print_error(str(exc))
        raise SystemExit(1) from exc

    console.print(f"[green]Cancelled:[/green] {ids_str}")


def _cmd_hold(args: argparse.Namespace) -> None:
    from slurm_utils.runner import SlurmCommandError, run_slurm

    try:
        run_slurm(["scontrol", "hold", args.jobid])
    except SlurmCommandError as exc:
        print_error(str(exc))
        raise SystemExit(1) from exc

    console.print(f"[green]Held:[/green] {args.jobid}")


def _cmd_release(args: argparse.Namespace) -> None:
    from slurm_utils.runner import SlurmCommandError, run_slurm

    try:
        run_slurm(["scontrol", "release", args.jobid])
    except SlurmCommandError as exc:
        print_error(str(exc))
        raise SystemExit(1) from exc

    console.print(f"[green]Released:[/green] {args.jobid}")


def _cmd_recommend(args: argparse.Namespace) -> None:
    from slurm_utils.recommend import recommend_partition

    recommend_partition(
        ntasks=args.ntasks,
        mem_spec=args.mem,
        walltime=args.walltime,
        partitions=args.partition,
        exclude=args.exclude,
    )


# -----------------------------------------------------------------------
# Entry-point
# -----------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="slurm-utils",
        description="Slurm aliases, priority explorer, and queue recommender",
    )
    sub = parser.add_subparsers(dest="command")

    _add_queue_parser(sub)
    _add_myjobs_parser(sub)
    _add_info_parser(sub)
    _add_prio_parser(sub)
    _add_cancel_parser(sub)
    _add_hold_parser(sub)
    _add_release_parser(sub)
    _add_recommend_parser(sub)

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
