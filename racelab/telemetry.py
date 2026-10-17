"""Telemetry channels derived from a simulated lap. SI units unless named.

Every channel follows from the engine's own output, not a separate model:

- throttle: drive force the lap needs, ``m * a + F_drag``, as a share of the
  drive force available at that speed and grip (100% = at the engine/traction limit);
- brake: braking force the lap needs, ``-(m * a + F_drag)``, as a share of the
  braking limit. Drag helps slow the car, so brake effort is below 100% at speed;
- steering: kinematic road-wheel angle ``atan(wheelbase * curvature)``. The
  centerline is lines and arcs, so steering steps at corner entry and exit;
- no gear channel: the engine has no gearbox.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from racelab.car import Car
from racelab.geometry import TrackGeometry
from racelab.physics import aero_drag_force, braking_deceleration, drive_force
from racelab.simulation import LapResult
from racelab.track import Track

WHEELBASE_M = 2.6


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
    x_m: np.ndarray
    y_m: np.ndarray


def build_telemetry(lap: LapResult, car: Car, track: Track, geometry: TrackGeometry) -> Telemetry:
    """``track`` must be the one the lap was simulated on (weather applied) so grip matches."""
    if not (lap.track_name == track.name == geometry.track_name):
        raise ValueError("lap, track and geometry must describe the same circuit")
    s, v, a = lap.distance_m, lap.speed_mps, lap.acceleration_mps2
    ends = np.cumsum([seg.length_m for seg in track.segments])
    grip = np.array([seg.grip_multiplier for seg in track.segments])[np.minimum(np.searchsorted(ends, s, side="right"), len(ends) - 1)]

    drag = np.array([aero_drag_force(car, vi) for vi in v])
    needed = car.mass_kg * a + drag
    available = np.array([drive_force(car, vi, g) for vi, g in zip(v, grip)])
    brake_limit = car.mass_kg * np.array([braking_deceleration(car, g) for g in grip])
    # The solver keeps |needed| within these limits; clip only absorbs float noise.
    throttle = np.clip(np.where(needed > 0, needed / available, 0.0), 0, 1) * 100
    brake = np.clip(np.where(needed < 0, -needed / brake_limit, 0.0), 0, 1) * 100

    k = geometry.curvature_per_m[np.round(s / geometry.step_m).astype(int) % len(geometry.curvature_per_m)]
    steering = np.degrees(np.arctan(WHEELBASE_M * k))

    v_next = np.roll(v, -1)
    dt = 2 * lap.step_m / (v + v_next)
    time = np.concatenate(([0.0], np.cumsum(dt)[:-1]))
    x, y, _ = geometry.pose_at(s)
    return Telemetry(float(np.sum(dt)), lap.total_distance_m, s, time, v, throttle, brake, steering, x, y)


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
