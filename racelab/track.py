"""Closed-circuit track model and two fictional circuits. Lengths in metres."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    """One piece of track. ``radius_m=None`` designates a straight."""

    length_m: float
    radius_m: float | None = None
    grip_multiplier: float = 1.0
    label: str = ""

    def __post_init__(self) -> None:
        if not (math.isfinite(self.length_m) and self.length_m > 0):
            raise ValueError(f"length_m must be positive and finite, got {self.length_m!r}")
        if self.radius_m is not None and not (math.isfinite(self.radius_m) and self.radius_m > 0):
            raise ValueError(f"radius_m must be positive and finite or None, got {self.radius_m!r}")
        if not (math.isfinite(self.grip_multiplier) and self.grip_multiplier > 0):
            raise ValueError(f"grip_multiplier must be positive and finite, got {self.grip_multiplier!r}")

    @property
    def is_straight(self) -> bool:
        return self.radius_m is None


@dataclass(frozen=True)
class Track:
    """Ordered segments of a closed loop: the last segment joins the first."""

    name: str
    segments: tuple[Segment, ...]

    def __post_init__(self) -> None:
        if not self.segments:
            raise ValueError("a track needs at least one segment")

    @property
    def total_length_m(self) -> float:
        return sum(s.length_m for s in self.segments)


TECHNICAL_CIRCUIT = Track(
    "Harrow Bend (technical)",
    (
        Segment(250, label="Main straight"),
        Segment(40, 25, label="T1 hairpin"),
        Segment(120),
        Segment(70, 45, label="T2"),
        Segment(80),
        Segment(35, 18, grip_multiplier=0.9, label="T3 dusty hairpin"),
        Segment(200),
        Segment(90, 60, label="T4 sweeper"),
        Segment(60),
        Segment(50, 30, label="T5"),
        Segment(150),
        Segment(40, 22, label="T6"),
        Segment(180),
        Segment(60, 40, label="T7"),
        Segment(100),
        Segment(55, 35, label="Final corner"),
    ),
)

HIGH_SPEED_CIRCUIT = Track(
    "Longreach Raceway (high-speed)",
    (
        Segment(900, label="Main straight"),
        Segment(200, 150, label="T1"),
        Segment(600),
        Segment(350, 300, label="T2 fast sweeper"),
        Segment(1100, label="Back straight"),
        Segment(140, 90, label="T3"),
        Segment(400),
        Segment(300, 220, grip_multiplier=0.95, label="T4 bumpy"),
        Segment(700),
        Segment(450, 400, label="T5 banking-free curve"),
    ),
)
