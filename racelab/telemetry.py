"""Telemetry channels derived from a simulated lap. SI units unless named.

Every channel follows from the engine's own output, not a separate model:

- throttle: drive force the lap needs, ``m * a + F_drag``, as a share of the
  drive force available at that speed, grip and curvature (100% = at the
  engine/traction/friction-circle limit);
- brake: braking force the lap needs, ``-(m * a + F_drag)``, as a share of the
  braking limit there. Drag helps slow the car, so brake effort is below 100% at speed;
- steering: kinematic road-wheel angle ``atan(wheelbase * curvature)`` of the driven path;
- gear: the gear the engine model uses at that speed (0 = no gearbox).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from racelab.car import Car
from racelab.geometry import TrackGeometry
from racelab.physics import aero_drag_force, braking_deceleration, drive_force, selected_gear
from racelab.simulation import LapResult
from racelab.track import Track


@dataclass(frozen=True)
class Telemetry:
    """One sample per simulation point, from the start line."""

    lap_time_s: float
    length_m: float
    distance_m: np.ndarray
    time_s: np.ndarray
    speed_mps: np.ndarray
    throttle_pct: np.ndarray
    brake_pct: np.ndarray
    steering_deg: np.ndarray
    """Positive steers left."""
    gear: np.ndarray
    x_m: np.ndarray
    y_m: np.ndarray


def build_telemetry(lap: LapResult, car: Car, track: Track, geometry: TrackGeometry) -> Telemetry:
    """``lap`` must be ``car`` on ``track`` (weather applied); geometry places the samples."""
    if not (lap.track_name == track.name == geometry.track_name):
        raise ValueError("lap, track and geometry must describe the same circuit")
    s, v, a, k = lap.distance_m, lap.speed_mps, lap.acceleration_mps2, np.abs(lap.curvature_per_m)

    drag = np.array([aero_drag_force(car, vi) for vi in v])
    needed = car.mass_kg * a + drag
    available = np.array([drive_force(car, vi, g, ki) for vi, g, ki in zip(v, lap.step_grip, k)])
    brake_limit = car.mass_kg * np.array([braking_deceleration(car, g, vi, ki) for vi, g, ki in zip(v, lap.step_grip, k)])
    # The solver keeps |needed| within these limits; clip only absorbs float noise.
    push, slow = np.maximum(needed, 0), np.maximum(-needed, 0)
    throttle = np.clip(np.divide(push, available, out=np.zeros_like(push), where=available > 0), 0, 1) * 100
    brake = np.clip(np.divide(slow, brake_limit, out=np.zeros_like(slow), where=brake_limit > 0), 0, 1) * 100

    steering = np.degrees(np.arctan(car.wheelbase_m * lap.curvature_per_m))
    gear = np.array([selected_gear(car, vi) for vi in v])

    dt = 2 * lap.step_length_m / (v + np.roll(v, -1))
    time = np.concatenate(([0.0], np.cumsum(dt)[:-1]))
    cx, cy, ch = geometry.pose_at(s)
    n = lap.lateral_offset_m
    return Telemetry(
        float(np.sum(dt)), lap.total_distance_m, s, time, v, throttle, brake, steering, gear,
        cx - n * np.sin(ch), cy + n * np.cos(ch),
    )


def lap_summary(t: Telemetry) -> dict[str, float]:
    """Time-weighted shares of the lap and headline figures."""
    dt = np.diff(np.append(t.time_s, t.lap_time_s))
    share = lambda mask: float(np.sum(dt[mask]) / t.lap_time_s * 100)
    return {
        "lap_time_s": t.lap_time_s,
        "top_speed_kmh": float(t.speed_mps.max() * 3.6),
        "min_speed_kmh": float(t.speed_mps.min() * 3.6),
        "avg_speed_kmh": t.length_m / t.lap_time_s * 3.6,
        "full_throttle_pct": share(t.throttle_pct >= 99.5),
        "braking_pct": share(t.brake_pct > 0.5),
        "max_steering_deg": float(np.abs(t.steering_deg).max()),
    }
