"""Builds the self-contained HTML canvas view of a lap. Rendering only: all
positions come from ``racelab.geometry`` and ``racelab.playback``."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from racelab.config import BodyPackage
from racelab.geometry import Camera, TrackGeometry
from racelab.playback import LapPlayback
from racelab.track import WEATHER, Weather

VIEW_W, VIEW_H = 1000, 640
CURB_WIDTH_M = 1.2
FOLLOW_SCALE_PX_PER_M = 9.0
_TEMPLATE = Path(__file__).with_name("track_view.html")


def _xy(x: np.ndarray, y: np.ndarray) -> dict:
    return {"x": np.round(x, 2).tolist(), "y": np.round(y, 2).tolist()}


def _corner_runs(geometry: TrackGeometry) -> list[np.ndarray]:
    in_corner = geometry.curvature_per_m != 0
    edges = np.flatnonzero(np.diff(np.concatenate(([False], in_corner, [False])).astype(int)))
    return [np.arange(a, b + 1) % len(in_corner) for a, b in zip(edges[::2], edges[1::2])]


def scene(geometry: TrackGeometry, playback: LapPlayback, body: BodyPackage, weather: Weather = WEATHER[0]) -> dict:
    """Everything the canvas needs, in world metres, plus the overview camera."""
    half = geometry.width_m / 2
    left, right = geometry.offset(half), geometry.offset(-half)
    camera = Camera.fit(np.concatenate((left[0], right[0])), np.concatenate((left[1], right[1])), VIEW_W, VIEW_H, 24)
    curb_offset = half + CURB_WIDTH_M / 2
    curbs = []
    for run in _corner_runs(geometry):
        for side in (curb_offset, -curb_offset):
            x, y = geometry.offset(side)
            curbs.append(_xy(x[run], y[run]))
    return {
        "view": {"w": VIEW_W, "h": VIEW_H},
        "camera": {"scale": camera.scale_px_per_m, "ox": camera.offset_x_px, "oy": camera.offset_y_px},
        "follow_scale": FOLLOW_SCALE_PX_PER_M,
        "track": {
            "name": geometry.track_name,
            "width": geometry.width_m,
            "center": _xy(geometry.x_m, geometry.y_m),
            "left": _xy(*left),
            "right": _xy(*right),
            "curbs": curbs,
            "curb_width": CURB_WIDTH_M,
            "start": {"x": float(geometry.x_m[0]), "y": float(geometry.y_m[0]), "h": float(geometry.heading_rad[0])},
        },
        "weather": {"name": weather.name, "rain": weather.rain_intensity},
        "body": {"color": body.color_hex, "length": body.length_m, "width": body.width_m},
        "lap_time": playback.lap_time_s,
        "frames": {
            "t": np.round(playback.time_s, 4).tolist(),
            "x": np.round(playback.x_m, 3).tolist(),
            "y": np.round(playback.y_m, 3).tolist(),
            "h": np.round(playback.heading_rad, 5).tolist(),
            "v": np.round(playback.speed_mps, 3).tolist(),
        },
    }


def track_view_html(
    geometry: TrackGeometry, playback: LapPlayback, body: BodyPackage, weather: Weather = WEATHER[0]
) -> str:
    payload = json.dumps(scene(geometry, playback, body, weather)).replace("</", "<\\/")
    return _TEMPLATE.read_text(encoding="utf-8").replace("__SCENE__", payload)
