"""Closed-circuit track model and two fictional circuits. Lengths in metres."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace


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

    def in_weather(self, weather: Weather) -> Track:
        """Same layout with every segment's surface grip scaled by the weather."""
        return replace(
            self,
            segments=tuple(replace(s, grip_multiplier=s.grip_multiplier * weather.grip_multiplier) for s in self.segments),
        )


@dataclass(frozen=True)
class Weather:
    """Track-wide conditions.

    ``grip_multiplier`` scales the surface grip of every segment (the engine's
    existing grip hook). ``rain_intensity`` (0-1) is used by the renderer only.
    The factors are illustrative, not calibrated against real tire data.
    """

    name: str
    grip_multiplier: float
    rain_intensity: float = 0.0

    def __post_init__(self) -> None:
        if not (math.isfinite(self.grip_multiplier) and self.grip_multiplier > 0):
            raise ValueError(f"grip_multiplier must be positive and finite, got {self.grip_multiplier!r}")
        if not 0 <= self.rain_intensity <= 1:
            raise ValueError(f"rain_intensity must be in [0, 1], got {self.rain_intensity!r}")


WEATHER = (
    Weather("Dry", 1.0),
    Weather("Damp", 0.85, 0.25),
    Weather("Wet", 0.7, 0.6),
    Weather("Heavy rain", 0.55, 1.0),
)


def _corner(radius_m: float, degrees: float, direction: int, **kwargs) -> Segment:
    return Segment(radius_m * math.radians(degrees), radius_m, direction=direction, **kwargs)


LEFT, RIGHT = 1, -1

# Simplified layouts inspired by real F1 circuits: the corner sequence, turn
# directions and lap length follow the originals; exact shapes, radii and
# elevation do not. Each closes as a loop (see racelab.geometry).
MONZA = Track(
    "Monza (Italy)",
    (
        Segment(1226.7, label="Main straight"),
        _corner(17.5, 79.7, RIGHT, label="Rettifilo"),
        _corner(17.5, 70.3, LEFT),
        Segment(283.1),
        _corner(348, 39.9, RIGHT, label="Curva Grande"),
        Segment(455.5),
        _corner(23, 49.2, LEFT, label="Roggia"),
        _corner(23, 60.8, RIGHT),
        Segment(315.4),
        _corner(69.5, 80.9, RIGHT, label="Lesmo 1"),
        Segment(223.0),
        _corner(58, 80.7, RIGHT, label="Lesmo 2"),
        Segment(795.6, label="Serraglio"),
        _corner(58, 40.1, LEFT, label="Ascari"),
        _corner(69.5, 69.9, RIGHT),
        _corner(93, 70.3, LEFT),
        Segment(1199.2, label="Back straight"),
        _corner(174, 178, RIGHT, label="Parabolica"),
    ),
    width_m=14.0,
)

MONACO = Track(
    "Monaco (street circuit)",
    (
        Segment(601.0, label="Start"),
        _corner(24.5, 82.3, RIGHT, label="Sainte Devote"),
        Segment(455.9, label="Beau Rivage"),
        _corner(81.5, 70.3, LEFT, label="Massenet"),
        _corner(41, 71.1, RIGHT, label="Casino"),
        Segment(169.9),
        _corner(20.5, 113.6, RIGHT, label="Mirabeau"),
        Segment(88.7),
        _corner(12.5, 176.8, LEFT, label="Grand Hotel hairpin"),
        Segment(86.7),
        _corner(20.5, 94.3, RIGHT, label="Mirabeau Bas"),
        Segment(90.7),
        _corner(27, 95.3, RIGHT, label="Portier"),
        _corner(381.5, 51.2, RIGHT, label="Tunnel"),
        Segment(201.0),
        _corner(16.5, 51.1, LEFT, label="Nouvelle chicane"),
        _corner(16.5, 48.5, RIGHT),
        Segment(344.1),
        _corner(47.5, 66.4, LEFT, label="Tabac"),
        Segment(110.4),
        _corner(34, 37.2, LEFT, label="Piscine"),
        _corner(34, 21.8, RIGHT),
        Segment(76.3),
        _corner(34, 21.3, RIGHT),
        _corner(34, 38.1, LEFT),
        Segment(141.6),
        _corner(19, 140.2, RIGHT, label="La Rascasse"),
        Segment(57.2),
        _corner(27, 60.3, RIGHT, label="Anthony Noghes"),
    ),
    width_m=9.0,
)

SPA = Track(
    "Spa-Francorchamps (Belgium)",
    (
        Segment(367.5, label="Start"),
        _corner(16.5, 146.3, RIGHT, label="La Source"),
        Segment(430.0),
        _corner(65.5, 52.2, LEFT, label="Eau Rouge"),
        _corner(76.5, 68.1, RIGHT, label="Raidillon"),
        _corner(163.5, 31.6, LEFT),
        Segment(2025.2, label="Kemmel straight"),
        _corner(27.5, 84, RIGHT, label="Les Combes"),
        _corner(27.5, 55.8, LEFT),
        Segment(261.2),
        _corner(49, 74.9, RIGHT, label="Malmedy"),
        Segment(221.8),
        _corner(22, 115.1, RIGHT, label="Rivage"),
        Segment(344.0),
        _corner(54.5, 35.9, LEFT),
        Segment(337.3),
        _corner(120, 66.8, LEFT, label="Pouhon"),
        Segment(328.5),
        _corner(43.5, 62.9, RIGHT, label="Fagnes"),
        _corner(43.5, 47, LEFT),
        Segment(284.1),
        _corner(65.5, 82.7, RIGHT, label="Stavelot"),
        Segment(720.1),
        _corner(436.5, 19.4, LEFT, label="Blanchimont"),
        Segment(696.1),
        _corner(16.5, 67.4, RIGHT, label="Bus Stop"),
        _corner(16.5, 32.7, LEFT),
    ),
    width_m=13.0,
)

CIRCUITS = (MONZA, MONACO, SPA)

# Phase 1 names, kept for existing callers.
TECHNICAL_CIRCUIT = MONACO
HIGH_SPEED_CIRCUIT = MONZA
