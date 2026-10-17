"""Quasi-steady-state lap simulation on a closed circuit.

Algorithm:
1. Split the loop into ``n`` equal centerline steps of ``ds <= step_m``. Point
   ``i`` sits at ``s = i * ds``. On the centerline it covers
   ``[s - ds/2, s + ds/2)`` and takes the highest curvature and lowest grip of
   every segment that window touches, so no corner is missed at coarse
   resolution (slightly conservative). With a racing line, curvature and step
   length come from the line instead; grip still comes from the segments.
2. Each point's corner limit solves ``m v^2 |k| = mu (m g + downforce(v))``.
   Every point starts at ``min(corner limit, top_speed_bound)``.
3. Repeat, with wrap-around across the start/finish line:
   forward pass  ``v[i+1] = min(v[i+1], sqrt(v[i]^2 + 2 * a_drive(v[i], k[i]) * ds[i]))``
   backward pass ``v[i]   = the largest v <= v[i] with v^2 <= v[i+1]^2 + 2 * a_brake(v, k[i]) * ds[i]``
   Both limits include the friction circle: grip used to corner is not
   available to brake or accelerate. Braking capacity falls as v rises (more
   lateral demand), so the backward step is solved exactly by bisection.
   Speeds only ever decrease and are bounded below by zero, so the loop
   converges; it stops once a full sweep changes no speed by more than
   ``tolerance_mps``.
4. Lap time is ``sum(2 * ds[i] / (v[i] + v[i+1]))``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from racelab.car import Car
from racelab.geometry import RacingLine
from racelab.physics import braking_deceleration, corner_speed_limit, net_acceleration, top_speed_bound
from racelab.track import Track

# Absolute slack (m/s, m/s^2) when re-checking constraints on the final profile.
CONSTRAINT_TOLERANCE = 1e-6
_BISECTION_STEPS = 40


@dataclass(frozen=True)
class LapResult:
    """One simulated lap. Arrays have one entry per discretisation point."""

    car_name: str
    track_name: str
    lap_time_s: float
    total_distance_m: float
    """Official (centerline) lap length (m)."""
    step_m: float
    """Centerline spacing between points (m)."""
    distance_m: np.ndarray
    """Centerline distance from the start line of each point (m)."""
    speed_mps: np.ndarray
    """Speed at each point (m/s)."""
    acceleration_mps2: np.ndarray
    """Mean longitudinal acceleration from point i to point i+1 (m/s^2); the last entry crosses the finish line."""
    corner_speed_limit_mps: np.ndarray
    """Cornering speed limit at each point (m/s); ``inf`` on straights."""
    max_speed_mps: float
    average_speed_mps: float
    """Official lap length / lap time (m/s)."""
    converged: bool
    iterations: int
    constraints_satisfied: bool
    """True if the profile respects the corner, drive and braking limits at every step."""
    step_length_m: np.ndarray
    """Distance actually driven from point i to point i+1 (m); equals ``step_m`` on the centerline."""
    curvature_per_m: np.ndarray
    """Signed curvature of the driven path at each point (1/m)."""
    lateral_offset_m: np.ndarray
    """Driven path's offset from the centerline, + to the left (m); zero on the centerline."""
    step_grip: np.ndarray
    """Surface grip multiplier used for the step from point i to i+1."""

    @property
    def path_length_m(self) -> float:
        return float(np.sum(self.step_length_m))


def _discretize(track: Track, n: int, ds: float) -> tuple[np.ndarray, np.ndarray]:
    """Per point: signed curvature with the largest magnitude, and lowest grip, over its window."""
    kappa = np.zeros(n)
    grip = np.full(n, np.inf)
    start = 0.0
    for segment in track.segments:
        end = start + segment.length_m
        # Points whose window [i*ds - ds/2, i*ds + ds/2) overlaps [start, end).
        idx = np.arange(math.floor(start / ds - 0.5) + 1, math.ceil(end / ds + 0.5)) % n
        k = 0.0 if segment.is_straight else segment.direction / segment.radius_m
        kappa[idx] = np.where(abs(k) > np.abs(kappa[idx]), k, kappa[idx])
        grip[idx] = np.minimum(grip[idx], segment.grip_multiplier)
        start = end
    return kappa, grip


def simulate_lap(
    car: Car,
    track: Track,
    step_m: float = 2.0,
    max_iterations: int = 300,
    tolerance_mps: float = 1e-9,
    racing_line: RacingLine | None = None,
) -> LapResult:
    """Simulate one flying lap (the car is already at speed at the start line).

    ``racing_line`` (from ``build_racing_line`` on the same track and step) makes the
    car drive that path; without it the car drives the centerline.
    """
    length = track.total_length_m
    if not (math.isfinite(step_m) and 0 < step_m <= length / 2):
        raise ValueError(f"step_m must be in (0, {length / 2}], got {step_m!r}")
    if max_iterations < 1:
        raise ValueError(f"max_iterations must be >= 1, got {max_iterations!r}")

    n = math.ceil(length / step_m)
    ds = length / n
    kappa, grip = _discretize(track, n, ds)
    step_len = np.full(n, ds)
    offset = np.zeros(n)
    if racing_line is not None:
        if racing_line.track_name != track.name or len(racing_line.offset_m) != n:
            raise ValueError("racing_line must be built from this track's geometry at the same step")
        kappa, step_len, offset = racing_line.curvature_per_m, racing_line.step_length_m, racing_line.offset_m
    limit = np.array([corner_speed_limit(car, k, g) for k, g in zip(kappa, grip)])
    # Each step i -> i+1 uses the lower grip of its two end points and the curvature at its start.
    step_grip = np.minimum(grip, np.roll(grip, -1)).tolist()
    k_abs, dsl = np.abs(kappa).tolist(), step_len.tolist()

    def brake(i: int, v: float) -> float:
        return braking_deceleration(car, step_grip[i], v, k_abs[i])

    v = np.minimum(limit, top_speed_bound(car)).tolist()
    converged = False
    iterations = 0
    for iterations in range(1, max_iterations + 1):
        previous = list(v)
        for i in range(n):
            j = (i + 1) % n
            reachable = math.sqrt(max(0.0, v[i] ** 2 + 2 * net_acceleration(car, v[i], step_grip[i], k_abs[i]) * dsl[i]))
            if reachable < v[j]:
                v[j] = reachable
        for i in range(n - 1, -1, -1):
            j = (i + 1) % n
            if v[i] ** 2 <= v[j] ** 2 + 2 * brake(i, v[i]) * dsl[i]:
                continue
            # h(u) = u^2 - v_j^2 - 2 a_brake(u) ds rises with u; h(v_j) <= 0 < h(v_i).
            lo, hi = v[j], v[i]
            for _ in range(_BISECTION_STEPS):
                mid = (lo + hi) / 2
                if mid**2 <= v[j] ** 2 + 2 * brake(i, mid) * dsl[i]:
                    lo = mid
                else:
                    hi = mid
            v[i] = lo
        if max(p - c for p, c in zip(previous, v)) <= tolerance_mps:
            converged = True
            break

    speed = np.array(v)
    speed_next = np.roll(speed, -1)
    pair_sum = speed + speed_next
    if not np.all(np.isfinite(pair_sum) & (pair_sum > 0)):
        raise ArithmeticError("speed profile contains zero or non-finite speeds; lap time is undefined")
    lap_time = float(np.sum(2 * step_len / pair_sum))
    acceleration = (speed_next**2 - speed**2) / (2 * step_len)

    drive_limit = np.array([net_acceleration(car, s, g, k) for s, g, k in zip(v, step_grip, k_abs)])
    brake_limit = np.array([brake(i, s) for i, s in enumerate(v)])
    constraints_satisfied = bool(
        np.all(speed <= limit + CONSTRAINT_TOLERANCE)
        and np.all(acceleration <= drive_limit + CONSTRAINT_TOLERANCE)
        and np.all(acceleration >= -brake_limit - CONSTRAINT_TOLERANCE)
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
        step_grip=np.array(step_grip),
    )
