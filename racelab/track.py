"""Closed-circuit track model and four F1-inspired circuits. Lengths in metres."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace


ENVIRONMENTS = ("parkland", "harbour", "forest", "desert")


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
    environment: str = "parkland"
    """Landscape the renderer draws around the track: one of ``ENVIRONMENTS``."""
    seafront_m: tuple[float, float] | None = None
    """Start and end distance (m) of the stretch with the sea on its outside; drawing only."""

    def __post_init__(self) -> None:
        if not self.segments:
            raise ValueError("a track needs at least one segment")
        if self.seafront_m is not None and not 0 <= self.seafront_m[0] < self.seafront_m[1] <= self.total_length_m:
            raise ValueError(f"seafront_m must be (start, end) within the lap, got {self.seafront_m!r}")
        if self.environment not in ENVIRONMENTS:
            raise ValueError(f"environment must be one of {ENVIRONMENTS}, got {self.environment!r}")
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

    ``grip_multiplier`` is the grip left on slick tyres; ``Track.in_weather`` applies it
    to every segment. ``water`` measures standing water: 1 is the point where
    intermediates become faster than slicks (see ``racelab.tires``). ``rain_intensity``
    (0-1) is used by the renderer only.
    """

    name: str
    grip_multiplier: float
    rain_intensity: float = 0.0

    @property
    def water(self) -> float:
        return (1 - self.grip_multiplier) / SLICK_GRIP_LOSS_PER_WATER

    def __post_init__(self) -> None:
        if not (math.isfinite(self.grip_multiplier) and self.grip_multiplier > 0):
            raise ValueError(f"grip_multiplier must be positive and finite, got {self.grip_multiplier!r}")
        if not 0 <= self.rain_intensity <= 1:
            raise ValueError(f"rain_intensity must be in [0, 1], got {self.rain_intensity!r}")


SLICK_GRIP_LOSS_PER_WATER = 0.328
"""Calibrated so slicks lap 111% of their dry time at water 1, Pirelli's slick-to-intermediate crossover."""

# Water 0.5: slicks still fastest; 1.5: between the two Pirelli crossovers, intermediates
# fastest; 2.5: past the intermediate-to-wet crossover, full wets fastest.
WEATHER = (
    Weather("Dry", 1.0),
    Weather("Damp", 1 - 0.5 * SLICK_GRIP_LOSS_PER_WATER, 0.25),
    Weather("Wet", 1 - 1.5 * SLICK_GRIP_LOSS_PER_WATER, 0.6),
    Weather("Heavy rain", 1 - 2.5 * SLICK_GRIP_LOSS_PER_WATER, 1.0),
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
    environment="parkland",
)

MONACO = Track(
    "Monaco (street circuit)",
    (
        Segment(347.0, label="Start"),
        _corner(23.5, 73, RIGHT, label="Sainte Devote"),
        Segment(114.4),
        _corner(469, 14.9, LEFT, label="Beau Rivage"),
        Segment(223.9),
        _corner(64.5, 94.7, LEFT, label="Massenet"),
        Segment(49.6),
        _corner(33, 77.8, RIGHT, label="Casino"),
        Segment(118.4),
        _corner(141, 7.6, LEFT),
        Segment(80.4),
        _corner(19, 118.6, RIGHT, label="Mirabeau"),
        Segment(73.8),
        _corner(10.5, 181.8, LEFT, label="Grand Hotel hairpin"),
        Segment(63.1),
        _corner(19, 89.3, RIGHT, label="Mirabeau Bas"),
        Segment(69.5),
        _corner(26, 105.7, RIGHT, label="Portier"),
        Segment(64.5),
        _corner(352, 74.5, RIGHT, label="Tunnel"),
        Segment(244.4),
        _corner(17.5, 54.1, LEFT, label="Nouvelle chicane"),
        _corner(17.5, 55.3, RIGHT),
        Segment(243.7),
        _corner(53, 44.3, LEFT, label="Tabac"),
        Segment(113.8),
        _corner(41, 36, LEFT, label="Piscine"),
        _corner(41, 22.5, RIGHT),
        Segment(75.8),
        _corner(23.5, 31.6, RIGHT),
        _corner(23.5, 48.3, LEFT),
        Segment(121.0),
        _corner(16.5, 129.1, RIGHT, label="La Rascasse"),
        Segment(50.2),
        _corner(21, 64.3, RIGHT, label="Anthony Noghes"),
        Segment(146.6),
    ),
    width_m=9.0,
    environment="harbour",
    seafront_m=(1565.0, 3120.0),  # Portier, along the tunnel, chicane, Tabac and the pool, to La Rascasse
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
    environment="forest",
)

BAHRAIN = Track(
    "Bahrain (Sakhir)",
    (
        Segment(1821.8, label="Main straight"),
        _corner(21.5, 101.1, RIGHT, label="Turn 1"),
        _corner(48, 38.7, LEFT, label="Turn 2"),
        _corner(143.5, 51.1, RIGHT, label="Turn 3"),
        Segment(361.9),
        _corner(36, 92, RIGHT, label="Turn 4"),
        Segment(226.8),
        _corner(72, 48.6, LEFT, label="Turn 5"),
        _corner(72, 61, RIGHT, label="Turn 6"),
        _corner(72, 39, LEFT, label="Turn 7"),
        Segment(253.0),
        _corner(18, 160.1, RIGHT, label="Turn 8 hairpin"),
        Segment(200.2),
        _corner(48, 59.7, LEFT, label="Turn 9"),
        _corner(30, 99.7, LEFT, label="Turn 10"),
        Segment(452.2, label="Back straight"),
        _corner(60, 71, LEFT, label="Turn 11"),
        Segment(244.8),
        _corner(179.5, 68.7, RIGHT, label="Turn 12"),
        Segment(209.7),
        _corner(48, 68.6, RIGHT, label="Turn 13"),
        Segment(612.0),
        _corner(36, 87, RIGHT, label="Turn 14"),
        _corner(72, 27.1, RIGHT, label="Turn 15"),
    ),
    width_m=15.0,
    environment="desert",
)

CIRCUITS = (MONZA, MONACO, SPA, BAHRAIN)

# Phase 1 names, kept for existing callers.
TECHNICAL_CIRCUIT = MONACO
HIGH_SPEED_CIRCUIT = MONZA
