"""Place a simulated lap on the track: vehicle state (position, heading, speed) over time.

The engine is a point mass on the centerline, so the car follows the
centerline exactly; there is no racing line, slip or yaw dynamics. Every lap
is the same flying lap.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from racelab.geometry import TrackGeometry
from racelab.simulation import LapResult


@dataclass(frozen=True)
class VehicleState:
    time_s: float
    lap: int
    """1-based lap number."""
    lap_time_s: float
    """Time elapsed in the current lap."""
    distance_m: float
    """Distance from the start line in the current lap."""
    x_m: float
    y_m: float
    heading_rad: float
    speed_mps: float


@dataclass(frozen=True)
class LapPlayback:
    """Simulation samples with their timestamps; index 0 and the last index are the start line."""

    lap_time_s: float
    time_s: np.ndarray
    distance_m: np.ndarray
    speed_mps: np.ndarray
    x_m: np.ndarray
    y_m: np.ndarray
    heading_rad: np.ndarray

    @classmethod
    def from_lap(cls, lap: LapResult, geometry: TrackGeometry) -> LapPlayback:
        if lap.track_name != geometry.track_name or abs(lap.total_distance_m - geometry.length_m) > 1e-6:
            raise ValueError(f"lap on {lap.track_name!r} does not match geometry of {geometry.track_name!r}")
        speed = np.append(lap.speed_mps, lap.speed_mps[0])
        distance = np.append(lap.distance_m, lap.total_distance_m)
        time = np.concatenate(([0.0], np.cumsum(2 * np.diff(distance) / (speed[:-1] + speed[1:]))))
        x, y, heading = geometry.pose_at(distance)
        # pose_at wraps the closing sample back to the start; keep heading continuous instead.
        heading[-1] = heading[0] + geometry.total_turn_rad
        return cls(float(time[-1]), time, distance, speed, x, y, heading)

    def state_at(self, time_s: float) -> VehicleState:
        """State ``time_s`` seconds after crossing the start line; later laps repeat the first."""
        if not np.isfinite(time_s) or time_s < 0:
            raise ValueError(f"time_s must be finite and >= 0, got {time_s!r}")
        completed, t = divmod(time_s, self.lap_time_s)
        interp = lambda values: float(np.interp(t, self.time_s, values))
        return VehicleState(
            time_s=float(time_s),
            lap=int(completed) + 1,
            lap_time_s=float(t),
            distance_m=interp(self.distance_m),
            x_m=interp(self.x_m),
            y_m=interp(self.y_m),
            heading_rad=interp(self.heading_rad),
            speed_mps=interp(self.speed_mps),
        )
