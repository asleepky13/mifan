"""Closed-circuit track model and two fictional circuits. Lengths in metres."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    """One piece of track. ``radius_m=None`` designates a straight.

    ``direction`` is +1 for a left (counter-clockwise) corner and -1 for a right
    corner; the speed simulation ignores it, the track geometry uses it.
    """

    length_m: float
    radius_m: float | None = None
    grip_multiplier: float = 1.0
    label: str = ""
    direction: int = 1

    def __post_init__(self) -> None:
        if not (math.isfinite(self.length_m) and self.length_m > 0):
            raise ValueError(f"length_m must be positive and finite, got {self.length_m!r}")
        if self.radius_m is not None and not (math.isfinite(self.radius_m) and self.radius_m > 0):
            raise ValueError(f"radius_m must be positive and finite or None, got {self.radius_m!r}")
        if not (math.isfinite(self.grip_multiplier) and self.grip_multiplier > 0):
            raise ValueError(f"grip_multiplier must be positive and finite, got {self.grip_multiplier!r}")
        if self.direction not in (1, -1):
            raise ValueError(f"direction must be 1 (left) or -1 (right), got {self.direction!r}")

    @property
    def is_straight(self) -> bool:
        return self.radius_m is None


@dataclass(frozen=True)
class Track:
    """Ordered segments of a closed loop: the last segment joins the first."""

    name: str
    segments: tuple[Segment, ...]
    width_m: float = 12.0

    def __post_init__(self) -> None:
        if not self.segments:
            raise ValueError("a track needs at least one segment")
        if not (math.isfinite(self.width_m) and self.width_m > 0):
            raise ValueError(f"width_m must be positive and finite, got {self.width_m!r}")

    @property
    def total_length_m(self) -> float:
        return sum(s.length_m for s in self.segments)


def _corner(radius_m: float, degrees: float, direction: int, **kwargs) -> Segment:
    return Segment(radius_m * math.radians(degrees), radius_m, direction=direction, **kwargs)


LEFT, RIGHT = 1, -1

# Both layouts close exactly as loops (see racelab.geometry); straights are in metres.
TECHNICAL_CIRCUIT = Track(
    "Harrow Bend (technical)",
    (
        Segment(300, label="Main straight"),
        _corner(25, 90, LEFT, label="T1"),
        Segment(80),
        _corner(30, 90, LEFT, label="T2"),
        Segment(60),
        _corner(20, 90, RIGHT, label="T3"),
        Segment(120),
        _corner(22, 180, LEFT, grip_multiplier=0.9, label="T4 dusty hairpin"),
        Segment(140),
        _corner(35, 90, RIGHT, label="T5"),
        Segment(146),
        _corner(30, 90, LEFT, label="T6"),
        Segment(30),
        _corner(40, 90, LEFT, label="Final corner"),
    ),
    width_m=10.0,
)

HIGH_SPEED_CIRCUIT = Track(
    "Longreach Raceway (high-speed)",
    (
        Segment(900, label="Main straight"),
        _corner(150, 90, LEFT, label="T1"),
        Segment(600),
        _corner(300, 70, LEFT, label="T2 fast sweeper"),
        Segment(1268.7, label="Back straight"),
        _corner(90, 110, LEFT, label="T3"),
        Segment(400),
        _corner(220, 30, RIGHT, grip_multiplier=0.95, label="T4 bumpy kink"),
        Segment(313.2),
        _corner(400, 120, LEFT, label="T5"),
        Segment(300),
    ),
    width_m=14.0,
)
