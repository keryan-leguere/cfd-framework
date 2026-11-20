"""
timeline — which physical instant each frame shows.

:func:`animate_sweep` animates by *index*: point *i* of the data on frame *i*.
That is right for a convergence history and wrong for anything that happens in
time — a trajectory sampled every 1 ms during the burn and every 100 ms in
coast would race through the burn and crawl through the coast. A physical
process is animated by *time*: frame *k* shows the state at ``t0 + k·speed/fps``,
interpolated between samples, whatever the sampling.

    tl = timeline(t[0], t[-1], fps=25, duration=12.0, holds={t_apogee: 1.5})
    for t_now, hold in tl:
        path.update(t_now)
        anim.capture(hold=hold)

``holds`` freezes the animation on chosen instants (an event, a regime change).
Each is inserted into the grid **exactly** — snapping it to the nearest frame
would show the state up to half a frame step away from the instant being
pointed at, which is visible on a fast event.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

__all__ = ["Timeline", "timeline"]


@dataclass(frozen=True)
class Timeline:
    """Physical instant and extra hold (s of video) of every captured frame."""

    times: NDArray[np.float64]
    holds: NDArray[np.float64]
    fps: int

    def __iter__(self) -> Iterator[tuple[float, float]]:
        return zip(self.times.tolist(), self.holds.tolist())

    def __len__(self) -> int:
        return len(self.times)

    @property
    def duration_s(self) -> float:
        """Playback time, holds included."""
        return len(self.times) / self.fps + float(self.holds.sum())


def timeline(
    t_start: float,
    t_end: float,
    *,
    fps: int,
    duration: float | None = None,
    speed: float | None = None,
    holds: Mapping[float, float] | None = None,
) -> Timeline:
    """Frame instants from *t_start* to *t_end* (both shown).

    Parameters
    ----------
    fps : int
        Video frame rate.
    duration : float, optional
        Seconds of video for the whole span (holds not included).
    speed : float, optional
        Physical seconds per second of video. Give *duration* or *speed*, not
        both; with neither, real time (``speed=1``).
    holds : mapping, optional
        ``{instant: seconds}`` — linger that long on that exact instant.
        Instants outside ``[t_start, t_end]`` are ignored.
    """
    if not t_end > t_start:
        raise ValueError(f"t_end must be after t_start, got [{t_start}, {t_end}]")
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    if duration is not None and speed is not None:
        raise ValueError("give duration or speed, not both")
    span = float(t_end - t_start)
    if duration is not None:
        if not duration > 0:
            raise ValueError(f"duration must be positive, got {duration}")
        speed = span / duration
    elif speed is None:
        speed = 1.0
    if not speed > 0:
        raise ValueError(f"speed must be positive, got {speed}")

    n = max(2, round(span / speed * fps) + 1)
    times = np.linspace(float(t_start), float(t_end), n)
    hold = np.zeros(n)
    for instant, seconds in sorted((holds or {}).items()):
        if seconds < 0:
            raise ValueError(f"hold at t = {instant} is negative ({seconds} s)")
        if not t_start <= instant <= t_end:
            continue
        i = int(np.searchsorted(times, instant))
        if i < len(times) and np.isclose(times[i], instant, rtol=0.0, atol=1e-9 * max(1.0, span)):
            hold[i] += seconds
            continue
        times = np.insert(times, i, instant)
        hold = np.insert(hold, i, seconds)
    return Timeline(times=times, holds=hold, fps=int(fps))
