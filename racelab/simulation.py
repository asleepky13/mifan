"""Quasi-steady-state lap simulation on a closed circuit.

Algorithm:
1. Split the loop into ``n`` equal centerline steps of ``ds <= step_m``. Point
   ``i`` sits at ``s = i * ds``. On the centerline it covers
   ``[s - ds/2, s + ds/2)`` and takes the lowest corner limit and grip of every
   segment that window touches, so no corner is missed at coarse resolution
   (slightly conservative). With a racing line, each point's corner limit
   comes from the line's own curvature, ``sqrt(mu g / |k|)``, and each step's
   length is the distance driven along the line.
2. Start from ``min(corner limit, top_speed_bound)`` at every point.
3. Repeat, with wrap-around across the start/finish line:
   forward pass  ``v[i+1] = min(v[i+1], sqrt(v[i]^2 + 2 * a_drive(v[i]) * ds[i]))``
   backward pass ``v[i]   = min(v[i],   sqrt(v[i+1]^2 + 2 * a_brake * ds[i]))``
   Speeds only ever decrease and are bounded below by zero, so the loop
   converges; it stops once a full forward+backward sweep changes no speed by
   more than ``tolerance_mps``.
4. Optionally the lap starts from a standstill (one forward pass from 0) and/or
   ends stopped at the line (one backward pass from 0): the laps either side
   of a tyre change.
5. Lap time is ``sum(2 * ds[i] / (v[i] + v[i+1]))``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from racelab.car import Car
from racelab.geometry import RacingLine
from racelab.physics import braking_deceleration, cornering_speed, effective_grip, net_acceleration, top_speed_bound
from racelab.track import Track

# Absolute slack (m/s, m/s^2) when re-checking constraints on the final profile.
CONSTRAINT_TOLERANCE = 1e-6


@dataclass(frozen=True)
class LapResult:
    """One simulated lap. Arrays have one entry per discretisation point."""

    car_name: str
    track_name: str
    lap_time_s: float
    total_distance_m: float
    step_m: float
    distance_m: np.ndarray
    """Distance from the start line of each point (m)."""
    speed_mps: np.ndarray
    """Speed at each point (m/s)."""
    acceleration_mps2: np.ndarray
    """Mean longitudinal acceleration from point i to point i+1 (m/s^2); the last entry crosses the finish line."""
    corner_speed_limit_mps: np.ndarray
    """Cornering speed limit at each point (m/s); ``inf`` on straights."""
    max_speed_mps: float
    average_speed_mps: float
    converged: bool
    iterations: int
    constraints_satisfied: bool
    """True if the profile respects the corner, drive and braking limits at every step."""
    step_length_m: np.ndarray
    """Distance driven from point i to point i+1 (m); ``step_m`` everywhere on the centerline."""
    curvature_per_m: np.ndarray
    """Signed curvature of the driven path at each point (1/m), + turning left."""
    lateral_offset_m: np.ndarray
    """Driven path's offset from the centerline, + to the left (m); zero on the centerline."""
    finish_speed_mps: float
    """Speed crossing the finish line: ``speed_mps[0]`` on a flying lap, 0 when stopping at the line."""


def _discretize(car: Car, track: Track, n: int, ds: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per point: lowest corner limit and grip over its window, and the curvature of the segment it sits in."""
    limit = np.full(n, np.inf)
    grip = np.full(n, np.inf)
    kappa = np.zeros(n)
    s = np.arange(n) * ds
    start = 0.0
    for segment in track.segments:
        end = start + segment.length_m
        # Points whose window [i*ds - ds/2, i*ds + ds/2) overlaps [start, end).
        idx = np.arange(math.floor(start / ds - 0.5) + 1, math.ceil(end / ds + 0.5)) % n
        corner = cornering_speed(segment.radius_m, effective_grip(car, segment.grip_multiplier))
        limit[idx] = np.minimum(limit[idx], corner)
        grip[idx] = np.minimum(grip[idx], segment.grip_multiplier)
        kappa[(s >= start) & (s < end)] = 0.0 if segment.is_straight else segment.direction / segment.radius_m
        start = end
    return limit, grip, kappa


def simulate_lap(
    car: Car,
    track: Track,
    step_m: float = 2.0,
    max_iterations: int = 50,
    tolerance_mps: float = 1e-9,
    racing_line: RacingLine | None = None,
    standing_start: bool = False,
    stop_at_finish: bool = False,
) -> LapResult:
    """Simulate one lap; by default a flying lap (the car is already at speed at the start line).

    ``racing_line`` (from ``build_racing_line`` on this track at the same step) makes the car
    drive that path instead of the centerline. ``standing_start`` starts from 0 at the line;
    ``stop_at_finish`` brakes to a stop at the line.
    """
    length = track.total_length_m
    if not (math.isfinite(step_m) and 0 < step_m <= length / 2):
        raise ValueError(f"step_m must be in (0, {length / 2}], got {step_m!r}")
    if max_iterations < 1:
        raise ValueError(f"max_iterations must be >= 1, got {max_iterations!r}")

    n = math.ceil(length / step_m)
    ds = length / n
    limit, grip, kappa = _discretize(car, track, n, ds)
    step_len = np.full(n, ds)
    offset = np.zeros(n)
    if racing_line is not None:
        if racing_line.track_name != track.name or len(racing_line.offset_m) != n:
            raise ValueError("racing_line must be built from this track's geometry at the same step")
        kappa, step_len, offset = racing_line.curvature_per_m, racing_line.step_length_m, racing_line.offset_m
        limit = np.array([cornering_speed(1 / abs(k) if k else None, effective_grip(car, g)) for k, g in zip(kappa, grip)])
    # Each step i -> i+1 uses the lower grip of its two end points.
    step_grip = np.minimum(grip, np.roll(grip, -1)).tolist()
    brake = [braking_deceleration(car, g) for g in step_grip]
    dsl = step_len.tolist()

    v = np.minimum(limit, top_speed_bound(car)).tolist()
    converged = False
    iterations = 0
    for iterations in range(1, max_iterations + 1):
        previous = list(v)
        for i in range(n):
            j = (i + 1) % n
            reachable = math.sqrt(v[i] ** 2 + 2 * net_acceleration(car, v[i], step_grip[i]) * dsl[i])
            if reachable < v[j]:
                v[j] = reachable
        for i in range(n - 1, -1, -1):
            j = (i + 1) % n
            reachable = math.sqrt(v[j] ** 2 + 2 * brake[i] * dsl[i])
            if reachable < v[i]:
                v[i] = reachable
        if max(p - c for p, c in zip(previous, v)) <= tolerance_mps:
            converged = True
            break

    if standing_start:  # accelerate away from 0 until the flying profile takes over
        v[0] = 0.0
        for i in range(n - 1):
            reachable = math.sqrt(v[i] ** 2 + 2 * net_acceleration(car, v[i], step_grip[i]) * dsl[i])
            if reachable >= v[i + 1]:
                break
            v[i + 1] = reachable
    finish = v[0]
    if stop_at_finish:  # brake to 0 at the line, walking back until the flying profile is slower
        finish, after = 0.0, 0.0
        for i in range(n - 1, 0, -1):
            reachable = math.sqrt(after**2 + 2 * brake[i] * dsl[i])
            if reachable >= v[i]:
                break
            v[i] = after = reachable

    speed = np.array(v)
    speed_next = np.append(speed[1:], finish)
    pair_sum = speed + speed_next
    if not np.all(np.isfinite(pair_sum) & (pair_sum > 0)):
        raise ArithmeticError("speed profile contains zero or non-finite speeds; lap time is undefined")
    lap_time = float(np.sum(2 * step_len / pair_sum))
    acceleration = (speed_next**2 - speed**2) / (2 * step_len)

    drive_limit = np.array([net_acceleration(car, s, g) for s, g in zip(v, step_grip)])
    constraints_satisfied = bool(
        np.all(speed <= limit + CONSTRAINT_TOLERANCE)
        and np.all(acceleration <= drive_limit + CONSTRAINT_TOLERANCE)
        and np.all(acceleration >= -np.array(brake) - CONSTRAINT_TOLERANCE)
    )

    return LapResult(
        car_name=car.name,
        track_name=track.name,
        lap_time_s=lap_time,
        total_distance_m=length,
        step_m=ds,
        distance_m=np.arange(n) * ds,
        speed_mps=speed,
        acceleration_mps2=acceleration,
        corner_speed_limit_mps=limit,
        max_speed_mps=float(speed.max()),
        average_speed_mps=length / lap_time,
        converged=converged,
        iterations=iterations,
        constraints_satisfied=constraints_satisfied,
        step_length_m=step_len,
        curvature_per_m=np.asarray(kappa, float),
        lateral_offset_m=np.asarray(offset, float),
        finish_speed_mps=float(finish),
    )
