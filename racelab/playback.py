"""Place a simulated lap on the track: vehicle state (position, heading, speed) over time.

The car follows the path the lap was simulated on: the centerline, or a
racing line across the track width. It is a point mass on that path, so there
is no slip or yaw. Every lap is the same flying lap.
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
        # Same step-time formula as the lap time, over the distance actually driven.
        time = np.concatenate(([0.0], np.cumsum(2 * lap.step_length_m / (speed[:-1] + speed[1:]))))
        cx, cy, ch = geometry.pose_at(lap.distance_m)
        n = lap.lateral_offset_m
        x, y = cx - n * np.sin(ch), cy + n * np.cos(ch)
        if np.any(n):
            # Heading along the driven path: direction of the chord through each sample's neighbours.
            ch = np.unwrap(np.arctan2(np.roll(y, -1) - np.roll(y, 1), np.roll(x, -1) - np.roll(x, 1)))
        # Close the loop at the start sample, keeping heading continuous (no 2*pi jump).
        x, y = np.append(x, x[0]), np.append(y, y[0])
        heading = np.append(ch, ch[0] + geometry.total_turn_rad)
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
