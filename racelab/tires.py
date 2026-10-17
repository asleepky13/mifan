"""F1-style tyres (Pirelli Soft, Medium, Hard, Intermediate, Wet), durability and tyre changes.

Pirelli does not publish grip or wear coefficients, so each tyre is calibrated to
figures Pirelli and F1 coverage do publish (mean over the four circuits, default car,
racing line):
- Pace: about 0.8-1 s a lap between compounds on a ~90 s lap (Mario Isola, 2025
  Bahrain test), so Soft laps 1% faster than Medium and Hard 1% slower.
- Wet weather: slicks give way to intermediates at 110-112% of the dry lap time, and
  intermediates to full wets at about 118% (Pirelli). On a dry track intermediates
  cost 5-6 s a lap (Pirelli) and full wets 6-7 s more than intermediates.
- Life: Pirelli's 2025 Monza pit windows (53 laps): Medium first stint to laps 22-28,
  Hard first stint to laps 28-34, Soft last stint from laps 32-38. Midpoints: Soft 18,
  Medium 25, Hard 31 laps at Monza before the change. No wear figures exist for the
  wet tyres; they use the Medium's rate.
- Colours: the sidewall colours (red, yellow, white, green, blue).

Model:
- Grip = car grip x the tyre's dry grip x (1 - water grip loss x water), with water
  from ``Weather.water``.
- New tyres have 100% durability. Each lap uses some up, in proportion to the
  work the tyres do: tyre work is ``sum((|a_long| + a_lat) * ds) / g`` in g-km,
  the distance driven weighted by how hard the tyres are pushed
  (``a_lat = v^2 * |curvature|``). Durability lost per lap = the tyre's wear rate x
  tyre work, so tight circuits and fast cars use tyres up faster.
- Grip falls linearly as durability falls: 15% less grip on a fully worn tyre.
  Grip is held at its start-of-lap value for the whole lap.
- When durability is at or below 20% at the end of a lap, the car stops at the
  line for ``TYRE_CHANGE_S`` and leaves on new tyres. The lap into the stop
  brakes to a standstill at the line and the lap after it starts from one.
  Wear is counted on the flying version of each lap.

The car is not an F1 car, so the figures set the tyres' relative pace and life;
absolute lap times are the RaceLab car's.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from racelab.car import Car
from racelab.geometry import RacingLine
from racelab.physics import GRAVITY_MPS2
from racelab.simulation import LapResult, simulate_lap
from racelab.track import SLICK_GRIP_LOSS_PER_WATER, WEATHER, Track, Weather

GRIP_LOSS_WHEN_WORN = 0.15
CHANGE_AT_DURABILITY = 0.2
TYRE_CHANGE_S = 2.0
"""Standstill time at the line while the tyres are changed."""
MAX_STINT_LAPS = 60
"""Tyres are changed after this many laps even if durability is left."""


@dataclass(frozen=True)
class Tyre:
    name: str
    color_hex: str
    """Sidewall colour."""
    dry_grip: float
    """Grip on a dry track, relative to the car's base grip (the Medium is 1)."""
    water_grip_loss: float
    """Share of dry grip lost per unit of ``Weather.water``."""
    wear_per_g_km: float
    """Durability (share of a new tyre) used per g-km of tyre work."""

    def __post_init__(self) -> None:
        for field in ("dry_grip", "wear_per_g_km"):
            value = getattr(self, field)
            if not (math.isfinite(value) and value > 0):
                raise ValueError(f"{field} must be positive and finite, got {value!r}")
        if not 0 <= self.water_grip_loss < 1:
            raise ValueError(f"water_grip_loss must be in [0, 1), got {self.water_grip_loss!r}")

    def grip(self, weather: Weather) -> float:
        """Grip multiplier in ``weather``; never below 5% of dry grip."""
        return self.dry_grip * max(0.05, 1 - self.water_grip_loss * weather.water)


# Dry grip and water grip loss: fitted to the pace figures in the module docstring.
# Wear rates: fitted so the default car gets 18 / 25 / 31 laps per set at Monza.
SOFT = Tyre("Soft", "#DA291C", 1.050, SLICK_GRIP_LOSS_PER_WATER, 0.01055)
MEDIUM = Tyre("Medium", "#FFD100", 1.000, SLICK_GRIP_LOSS_PER_WATER, 0.00763)
HARD = Tyre("Hard", "#F0F0F0", 0.953, SLICK_GRIP_LOSS_PER_WATER, 0.00619)
INTERMEDIATE = Tyre("Intermediate", "#43B02A", 0.780, 0.139, 0.00763)
WET = Tyre("Wet", "#0067AD", 0.636, 0.0574, 0.00763)
TYRES = (SOFT, MEDIUM, HARD, INTERMEDIATE, WET)
TYRES_BY_NAME = {t.name: t for t in TYRES}


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
    tyre: Tyre = MEDIUM,
    weather: Weather = WEATHER[0],
    step_m: float = 2.0,
    racing_line: RacingLine | None = None,
    change_at: float = CHANGE_AT_DURABILITY,
    change_s: float = TYRE_CHANGE_S,
) -> TyreStint:
    """Drive on new ``tyre``s from a standing start until durability reaches ``change_at``, then stop.

    ``track`` is the dry track: the weather acts through the tyre's grip.
    """
    if not 0 < change_at < 1:
        raise ValueError(f"change_at must be in (0, 1), got {change_at!r}")
    if not (np.isfinite(change_s) and change_s >= 0):
        raise ValueError(f"change_s must be finite and >= 0, got {change_s!r}")

    def lap(mu: float, **kwargs) -> LapResult:
        return simulate_lap(replace(car, tire_friction=mu), track, step_m, racing_line=racing_line, **kwargs)

    flying: dict[float, LapResult] = {}  # same grip -> same lap
    durability, out = 1.0, []
    for number in range(1, MAX_STINT_LAPS + 1):
        mu = round(car.tire_friction * tyre.grip(weather) * grip_factor(durability), 6)
        if mu not in flying:
            flying[mu] = lap(mu)
        end = max(0.0, durability - tyre.wear_per_g_km * tyre_work_g_km(flying[mu]))
        first, last = number == 1, end <= change_at or number == MAX_STINT_LAPS
        driven = lap(mu, standing_start=first, stop_at_finish=last) if first or last else flying[mu]
        out.append(StintLap(number, durability, end, driven))
        if last:
            break
        durability = end
    return TyreStint(tuple(out), change_s)
