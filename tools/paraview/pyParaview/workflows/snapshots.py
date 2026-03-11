from __future__ import annotations

from pathlib import Path

from rich.console import Console

from ..paraview.state import render_snapshot


console = Console()


def render_snapshot_from_state(
    state_file: str | Path,
    output_image: str | Path,
    data_files: list[str] | None = None,
    data_dir: str | Path | None = None,
    resolution: tuple[int, int] | None = None,
) -> None:
    """
    High-level wrapper to render a snapshot from a ParaView state file.
    """
    console.print(f"[bold cyan]Rendering snapshot from state[/] {state_file}")
    render_snapshot(
        state_file=state_file,
        output_image=output_image,
        data_files=data_files,
        data_dir=data_dir,
        resolution=resolution,
    )
    console.print(f"[green]Saved snapshot:[/] {Path(output_image).resolve()}")

