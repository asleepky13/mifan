"""Quasi-steady-state lap simulation on a closed circuit.

Algorithm:
1. Split the loop into ``n`` equal steps of ``ds <= step_m``. Point ``i`` sits
   at ``s = i * ds`` and covers ``[s - ds/2, s + ds/2)``; it takes the lowest
   corner limit and grip of every segment that window touches, so no corner
   is missed at coarse resolution (slightly conservative).
2. Start from ``min(corner limit, top_speed_bound)`` at every point.
3. Repeat, with wrap-around across the start/finish line:
   forward pass  ``v[i+1] = min(v[i+1], sqrt(v[i]^2 + 2 * a_drive(v[i]) * ds))``
   backward pass ``v[i]   = min(v[i],   sqrt(v[i+1]^2 + 2 * a_brake * ds))``
   Speeds only ever decrease and are bounded below by zero, so the loop
   converges; it stops once a full forward+backward sweep changes no speed by
   more than ``tolerance_mps``.
4. Lap time is ``sum(2 * ds / (v[i] + v[i+1]))``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from racelab.car import Car
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


def _discretize(car: Car, track: Track, n: int, ds: float) -> tuple[np.ndarray, np.ndarray]:
    limit = np.full(n, np.inf)
    grip = np.full(n, np.inf)
    start = 0.0
    for segment in track.segments:
        end = start + segment.length_m
        # Points whose window [i*ds - ds/2, i*ds + ds/2) overlaps [start, end).
        idx = np.arange(math.floor(start / ds - 0.5) + 1, math.ceil(end / ds + 0.5)) % n
        corner = cornering_speed(segment.radius_m, effective_grip(car, segment.grip_multiplier))
        limit[idx] = np.minimum(limit[idx], corner)
        grip[idx] = np.minimum(grip[idx], segment.grip_multiplier)
        start = end
    return limit, grip


def simulate_lap(
    car: Car,
    track: Track,
    step_m: float = 2.0,
    max_iterations: int = 50,
    tolerance_mps: float = 1e-9,
) -> LapResult:
    """Simulate one flying lap (the car is already at speed at the start line)."""
    length = track.total_length_m
    if not (math.isfinite(step_m) and 0 < step_m <= length / 2):
        raise ValueError(f"step_m must be in (0, {length / 2}], got {step_m!r}")
    if max_iterations < 1:
        raise ValueError(f"max_iterations must be >= 1, got {max_iterations!r}")

    n = math.ceil(length / step_m)
    ds = length / n
    limit, grip = _discretize(car, track, n, ds)
    # Each step i -> i+1 uses the lower grip of its two end points.
    step_grip = np.minimum(grip, np.roll(grip, -1)).tolist()
    brake = [braking_deceleration(car, g) for g in step_grip]

    v = np.minimum(limit, top_speed_bound(car)).tolist()
    converged = False
    iterations = 0
    for iterations in range(1, max_iterations + 1):
        previous = list(v)
        for i in range(n):
            j = (i + 1) % n
            reachable = math.sqrt(v[i] ** 2 + 2 * net_acceleration(car, v[i], step_grip[i]) * ds)
            if reachable < v[j]:
                v[j] = reachable
        for i in range(n - 1, -1, -1):
            j = (i + 1) % n
            reachable = math.sqrt(v[j] ** 2 + 2 * brake[i] * ds)
            if reachable < v[i]:
                v[i] = reachable
        if max(p - c for p, c in zip(previous, v)) <= tolerance_mps:
            converged = True
            break

    speed = np.array(v)
    speed_next = np.roll(speed, -1)
    pair_sum = speed + speed_next
    if not np.all(np.isfinite(pair_sum) & (pair_sum > 0)):
        raise ArithmeticError("speed profile contains zero or non-finite speeds; lap time is undefined")
    lap_time = float(np.sum(2 * ds / pair_sum))
    acceleration = (speed_next**2 - speed**2) / (2 * ds)

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
    )
