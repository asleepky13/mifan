"""Tyre durability and tyre changes over a run of laps.

Model:
- New tyres have 100% durability. Each lap uses some up, in proportion to the
  work the tyres do: tyre work is ``sum((|a_long| + a_lat) * ds) / g`` in g-km,
  the distance driven weighted by how hard the tyres are pushed
  (``a_lat = v^2 * |curvature|``). Durability lost per lap = ``WEAR_PER_G_KM`` x
  tyre work, so tight circuits and fast cars use tyres up faster.
- Grip falls linearly as durability falls: 15% less grip on a fully worn tyre.
  Grip is held at its start-of-lap value for the whole lap.
- When durability is at or below 20% at the end of a lap, the car stops at the
  line for ``TYRE_CHANGE_S`` and leaves on new tyres. The lap into the stop
  brakes to a standstill at the line and the lap after it starts from one.
  Wear is counted on the flying version of each lap.

The rates are illustrative, not calibrated tyre data.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from racelab.car import Car
from racelab.geometry import RacingLine
from racelab.physics import GRAVITY_MPS2
from racelab.simulation import LapResult, simulate_lap
from racelab.track import Track

WEAR_PER_G_KM = 0.025
"""Durability (share of a new tyre) used per g-km of tyre work."""
GRIP_LOSS_WHEN_WORN = 0.15
CHANGE_AT_DURABILITY = 0.2
TYRE_CHANGE_S = 2.0
"""Standstill time at the line while the tyres are changed."""
MAX_STINT_LAPS = 60
"""Tyres are changed after this many laps even if durability is left."""


def grip_factor(durability: float) -> float:
    """Grip left on a tyre with ``durability`` (1 = new, 0 = fully worn)."""
    if not 0 <= durability <= 1:
        raise ValueError(f"durability must be in [0, 1], got {durability!r}")
    return 1 - GRIP_LOSS_WHEN_WORN * (1 - durability)


def tyre_work_g_km(lap: LapResult) -> float:
    """``sum((|a_long| + v^2 |k|) * ds) / g / 1000`` over one lap, along the path driven (g-km)."""
    lateral = lap.speed_mps**2 * np.abs(lap.curvature_per_m)
    return float(np.sum((np.abs(lap.acceleration_mps2) + lateral) * lap.step_length_m) / GRAVITY_MPS2 / 1000)


@dataclass(frozen=True)
class StintLap:
    lap: int
    durability_start: float
    durability_end: float
    result: LapResult
    """The lap as driven: from a standing start on lap 1, stopping at the line on the last lap."""


@dataclass(frozen=True)
class TyreStint:
    """Laps on one set of tyres, then the change. The next stint is identical, so it repeats."""

    laps: tuple[StintLap, ...]
    change_s: float

    @property
    def cycle_time_s(self) -> float:
        return sum(l.result.lap_time_s for l in self.laps) + self.change_s


def tyre_stint(
    car: Car,
    track: Track,
    step_m: float = 2.0,
    racing_line: RacingLine | None = None,
    change_at: float = CHANGE_AT_DURABILITY,
    change_s: float = TYRE_CHANGE_S,
) -> TyreStint:
    """Drive on new tyres from a standing start until durability reaches ``change_at``, then stop."""
    if not 0 < change_at < 1:
        raise ValueError(f"change_at must be in (0, 1), got {change_at!r}")
    if not (np.isfinite(change_s) and change_s >= 0):
        raise ValueError(f"change_s must be finite and >= 0, got {change_s!r}")

    def lap(mu: float, **kwargs) -> LapResult:
        return simulate_lap(replace(car, tire_friction=mu), track, step_m, racing_line=racing_line, **kwargs)

    flying: dict[float, LapResult] = {}  # same grip -> same lap
    durability, out = 1.0, []
    for number in range(1, MAX_STINT_LAPS + 1):
        mu = round(car.tire_friction * grip_factor(durability), 6)
        if mu not in flying:
            flying[mu] = lap(mu)
        end = max(0.0, durability - WEAR_PER_G_KM * tyre_work_g_km(flying[mu]))
        first, last = number == 1, end <= change_at or number == MAX_STINT_LAPS
        driven = lap(mu, standing_start=first, stop_at_finish=last) if first or last else flying[mu]
        out.append(StintLap(number, durability, end, driven))
        if last:
            break
        durability = end
    return TyreStint(tuple(out), change_s)
