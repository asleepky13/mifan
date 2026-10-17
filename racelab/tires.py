"""Tyre compounds, tyre wear and pit stops over a multi-lap race.

Model:
- A compound scales grip (Soft > Medium > Hard) and sets how fast it wears.
- Wear grows with the work the tyres do: each lap's tyre work is
  ``sum((|a_long| + a_lat) * ds) / g`` in g-km, the distance driven weighted by
  how hard the tyres are pushed (``a_lat = v^2 * |curvature|``). Wear per lap =
  compound rate x tyre work, so tight circuits and fast cars wear tyres faster.
- Grip falls linearly with wear: 15% less grip on a fully worn tyre.
- Wear is held at its start-of-lap value for the whole lap, so each lap is a
  separate flying lap with that grip.
- When wear reaches the pit threshold the car pits at the end of that lap: it
  loses a fixed pit time and leaves on fresh tyres of the pit compound.

The rates and the pit loss are illustrative, not calibrated tyre data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from racelab.car import Car
from racelab.geometry import TrackGeometry
from racelab.physics import GRAVITY_MPS2
from racelab.simulation import LapResult, simulate_lap
from racelab.track import Track

GRIP_LOSS_WHEN_WORN = 0.15
PIT_THRESHOLD = 0.8
"""Pit once wear reaches this share (20% of the tyre left)."""
PIT_LOSS_S = 22.0
"""Pit-lane drive plus the stop, versus staying out."""


@dataclass(frozen=True)
class Compound:
    name: str
    grip_multiplier: float
    wear_per_g_km: float
    """Wear (share of the tyre, 0-1) per g-km of tyre work."""

    def __post_init__(self) -> None:
        for field in ("grip_multiplier", "wear_per_g_km"):
            value = getattr(self, field)
            if not (math.isfinite(value) and value > 0):
                raise ValueError(f"{field} must be positive and finite, got {value!r}")


COMPOUNDS = (
    Compound("Soft", 1.08, 0.045),
    Compound("Medium", 1.00, 0.025),
    Compound("Hard", 0.93, 0.015),
)
COMPOUNDS_BY_NAME = {c.name: c for c in COMPOUNDS}


def grip_factor(wear: float) -> float:
    """Grip left on a tyre with ``wear`` (0 = new, 1 = fully worn)."""
    if not 0 <= wear <= 1:
        raise ValueError(f"wear must be in [0, 1], got {wear!r}")
    return 1 - GRIP_LOSS_WHEN_WORN * wear


def tyre_work_g_km(lap: LapResult, geometry: TrackGeometry) -> float:
    """``sum((|a_long| + v^2 |k|) * ds) / g / 1000`` over one lap (g-km)."""
    if len(geometry.curvature_per_m) != len(lap.speed_mps):
        raise ValueError("geometry must be built at the lap's step")
    lateral = lap.speed_mps**2 * np.abs(geometry.curvature_per_m)
    return float(np.sum((np.abs(lap.acceleration_mps2) + lateral) * lap.step_m) / GRAVITY_MPS2 / 1000)


@dataclass(frozen=True)
class RaceLap:
    lap: int
    compound: str
    wear_start: float
    wear_end: float
    lap_time_s: float
    pit_after: bool
    """True if the car pits at the end of this lap (its pit loss is in ``pit_time_s``)."""
    pit_time_s: float


@dataclass(frozen=True)
class RaceResult:
    laps: tuple[RaceLap, ...]
    pit_loss_s: float

    @property
    def total_time_s(self) -> float:
        return sum(l.lap_time_s + l.pit_time_s for l in self.laps)

    @property
    def pit_stops(self) -> int:
        return sum(l.pit_after for l in self.laps)


def simulate_race(
    car: Car,
    track: Track,
    geometry: TrackGeometry,
    laps: int,
    start: Compound,
    pit_to: Compound,
    step_m: float = 2.0,
    pit_threshold: float = PIT_THRESHOLD,
    pit_loss_s: float = PIT_LOSS_S,
) -> RaceResult:
    """Run ``laps`` laps, pitting for ``pit_to`` tyres whenever wear reaches ``pit_threshold``.

    No stop is made after the final lap. Wear is capped at 1 (a fully worn tyre).
    """
    if not (isinstance(laps, int) and laps >= 1):
        raise ValueError(f"laps must be a positive integer, got {laps!r}")
    if not 0 < pit_threshold <= 1:
        raise ValueError(f"pit_threshold must be in (0, 1], got {pit_threshold!r}")
    if not (math.isfinite(pit_loss_s) and pit_loss_s >= 0):
        raise ValueError(f"pit_loss_s must be finite and >= 0, got {pit_loss_s!r}")

    cache: dict[float, LapResult] = {}  # same grip -> same lap; avoids re-simulating
    compound, wear, out = start, 0.0, []
    for number in range(1, laps + 1):
        mu = round(car.tire_friction * compound.grip_multiplier * grip_factor(wear), 6)
        if mu not in cache:
            cache[mu] = simulate_lap(replace(car, tire_friction=mu), track, step_m)
        lap = cache[mu]
        wear_end = min(1.0, wear + compound.wear_per_g_km * tyre_work_g_km(lap, geometry))
        pit = wear_end >= pit_threshold and number < laps
        out.append(RaceLap(number, compound.name, wear, wear_end, lap.lap_time_s, pit, pit_loss_s if pit else 0.0))
        compound, wear = (pit_to, 0.0) if pit else (compound, wear_end)
    return RaceResult(tuple(out), pit_loss_s)
