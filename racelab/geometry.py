"""Track centerline geometry and the world-to-screen camera. Metres and radians.

The centerline is built exactly from the segment list: straights are lines,
corners are circular arcs of their radius turning by ``length / radius``. The
lap starts at the origin heading along +x; +y is to the left of the start.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from racelab.track import Track


@dataclass(frozen=True)
class TrackGeometry:
    """Centerline sampled every ``step_m``. Arrays share one index; the loop closes back to index 0."""

    track_name: str
    length_m: float
    width_m: float
    step_m: float
    distance_m: np.ndarray
    x_m: np.ndarray
    y_m: np.ndarray
    heading_rad: np.ndarray
    """Unwrapped tangent direction, counter-clockwise from +x."""
    curvature_per_m: np.ndarray
    """Signed curvature, +1/r in a left corner, -1/r in a right corner, 0 on straights."""
    total_turn_rad: float
    """Net heading change over one lap: +2*pi for a counter-clockwise loop."""
    closure_error_m: float
    """Gap between where the centerline ends and where it started."""

    @property
    def heading_closure_error_rad(self) -> float:
        """Net turning minus the nearest whole number of full turns."""
        turns = self.total_turn_rad / (2 * math.pi)
        return abs(turns - round(turns)) * 2 * math.pi

    def pose_at(self, distance_m: float | np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Interpolated ``(x, y, heading)`` at any distance; wraps around the lap."""
        s = np.mod(distance_m, self.length_m)
        xs = np.append(self.distance_m, self.length_m)
        x = np.interp(s, xs, np.append(self.x_m, self.x_m[0]))
        y = np.interp(s, xs, np.append(self.y_m, self.y_m[0]))
        heading = np.interp(s, xs, np.append(self.heading_rad, self.heading_rad[0] + self.total_turn_rad))
        return x, y, heading

    def offset(self, lateral_m: float) -> tuple[np.ndarray, np.ndarray]:
        """Points ``lateral_m`` to the left (negative: right) of the centerline."""
        return (
            self.x_m - lateral_m * np.sin(self.heading_rad),
            self.y_m + lateral_m * np.cos(self.heading_rad),
        )


def build_geometry(track: Track, step_m: float = 2.0) -> TrackGeometry:
    length = track.total_length_m
    if not (math.isfinite(step_m) and 0 < step_m <= length / 2):
        raise ValueError(f"step_m must be in (0, {length / 2}], got {step_m!r}")
    n = math.ceil(length / step_m)
    ds = length / n
    s = np.arange(n) * ds
    x, y, h, k = (np.empty(n) for _ in range(4))

    x0 = y0 = h0 = start = 0.0
    for segment in track.segments:
        end = start + segment.length_m
        mask = (s >= start) & (s < end)
        u = s[mask] - start
        if segment.is_straight:
            curv = 0.0
            x[mask] = x0 + u * math.cos(h0)
            y[mask] = y0 + u * math.sin(h0)
        else:
            curv = segment.direction / segment.radius_m
            x[mask] = x0 + (np.sin(h0 + curv * u) - math.sin(h0)) / curv
            y[mask] = y0 - (np.cos(h0 + curv * u) - math.cos(h0)) / curv
        h[mask] = h0 + curv * u
        k[mask] = curv
        # Exact end pose of the segment becomes the next segment's start.
        L = segment.length_m
        if curv == 0.0:
            x0, y0 = x0 + L * math.cos(h0), y0 + L * math.sin(h0)
        else:
            x0, y0 = x0 + (math.sin(h0 + curv * L) - math.sin(h0)) / curv, y0 - (math.cos(h0 + curv * L) - math.cos(h0)) / curv
        h0 += curv * L
        start = end

    return TrackGeometry(
        track_name=track.name,
        length_m=length,
        width_m=track.width_m,
        step_m=ds,
        distance_m=s,
        x_m=x,
        y_m=y,
        heading_rad=h,
        curvature_per_m=k,
        total_turn_rad=h0,
        closure_error_m=math.hypot(x0, y0),
    )


@dataclass(frozen=True)
class Camera:
    """Uniform-scale map from world metres to screen pixels; screen y points down."""

    scale_px_per_m: float
    offset_x_px: float
    offset_y_px: float

    @classmethod
    def fit(
        cls, x_m: np.ndarray, y_m: np.ndarray, width_px: float, height_px: float, margin_px: float = 0.0
    ) -> Camera:
        """Centre the points in the viewport at the largest scale that keeps ``margin_px`` free on every side."""
        span_x = float(np.max(x_m) - np.min(x_m))
        span_y = float(np.max(y_m) - np.min(y_m))
        usable_w, usable_h = width_px - 2 * margin_px, height_px - 2 * margin_px
        if usable_w <= 0 or usable_h <= 0:
            raise ValueError("margin leaves no drawable area")
        scale = min(usable_w / span_x if span_x else math.inf, usable_h / span_y if span_y else math.inf)
        if not math.isfinite(scale):
            raise ValueError("cannot fit a single point")
        cx, cy = (np.max(x_m) + np.min(x_m)) / 2, (np.max(y_m) + np.min(y_m)) / 2
        return cls(scale, width_px / 2 - scale * float(cx), height_px / 2 + scale * float(cy))

    @classmethod
    def centered_on(cls, x_m: float, y_m: float, scale_px_per_m: float, width_px: float, height_px: float) -> Camera:
        """Chase view: world point ``(x_m, y_m)`` at the viewport centre."""
        return cls(scale_px_per_m, width_px / 2 - scale_px_per_m * x_m, height_px / 2 + scale_px_per_m * y_m)

    def to_screen(self, x_m, y_m):
        return self.offset_x_px + self.scale_px_per_m * np.asarray(x_m), self.offset_y_px - self.scale_px_per_m * np.asarray(y_m)

    def to_world(self, x_px, y_px):
        return (np.asarray(x_px) - self.offset_x_px) / self.scale_px_per_m, (self.offset_y_px - np.asarray(y_px)) / self.scale_px_per_m
