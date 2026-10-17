"""Builds the self-contained HTML canvas view of a lap. Rendering only: all
positions come from ``racelab.geometry`` and ``racelab.playback``."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from racelab.geometry import Camera, TrackGeometry
from racelab.playback import LapPlayback
from racelab.track import WEATHER, Weather

VIEW_W, VIEW_H = 1000, 640
CURB_WIDTH_M = 1.2
RUNOFF_WIDTH_M = 14.0
GRAVEL_BELOW_RADIUS_M = 150.0  # slower corners get gravel, faster ones tarmac run-off
ARMCO_OFFSET_M = 5.0  # guardrail distance beyond the track edge where there is no run-off
TREE_CLEARANCE_M = 6.0  # beyond the outermost barrier
SCENERY_PAD_M = 220.0
FOLLOW_SCALE_PX_PER_M = 16.0
_TEMPLATE = Path(__file__).with_name("track_view.html")


def _xy(x: np.ndarray, y: np.ndarray) -> dict:
    return {"x": np.round(x, 2).tolist(), "y": np.round(y, 2).tolist()}


def _corner_runs(geometry: TrackGeometry) -> list[np.ndarray]:
    in_corner = geometry.curvature_per_m != 0
    edges = np.flatnonzero(np.diff(np.concatenate(([False], in_corner, [False])).astype(int)))
    return [np.arange(a, b + 1) % len(in_corner) for a, b in zip(edges[::2], edges[1::2])]


def distance_to_track(geometry: TrackGeometry, x: np.ndarray, y: np.ndarray, skip: slice = slice(0, 0)) -> np.ndarray:
    """Distance from each point to the nearest centerline sample (samples in ``skip`` ignored)."""
    keep = np.ones(len(geometry.x_m), bool)
    keep[skip] = False
    cx, cy = geometry.x_m[keep], geometry.y_m[keep]
    return np.array([np.min(np.hypot(cx - px, cy - py)) for px, py in zip(x, y)])


def _runoff(geometry: TrackGeometry) -> tuple[list[dict], list[dict]]:
    """Run-off areas outside corners, and guardrail runs along every stretch without run-off."""
    half, n = geometry.width_m / 2, len(geometry.x_m)
    covered = {1: np.zeros(n, bool), -1: np.zeros(n, bool)}
    out = []
    for run in _corner_runs(geometry):
        k = geometry.curvature_per_m[run]
        k = k[k != 0]  # runs include the first point after the corner
        span = np.arange(run[0] - 3, run[-1] + 16) % n  # cars run wide on exit
        for side in sorted(set((-np.sign(k)).astype(int).tolist())):  # outside of the turn; chicanes get both
            mid = geometry.offset(side * (half + CURB_WIDTH_M + RUNOFF_WIDTH_M / 2))
            wall = geometry.offset(side * (half + CURB_WIDTH_M + RUNOFF_WIDTH_M + 0.6))
            out.append({
                "gravel": bool(np.abs(k).max() > 1 / GRAVEL_BELOW_RADIUS_M),
                "mid": _xy(mid[0][span], mid[1][span]),
                "wall": _xy(wall[0][span], wall[1][span]),
            })
            covered[side][span] = True
    armco = []
    for side, mask in covered.items():
        x, y = geometry.offset(side * (half + ARMCO_OFFSET_M))
        free = ~mask
        edges = np.flatnonzero(np.diff(np.concatenate(([False], free, [False])).astype(int)))
        armco += [_xy(x[a:b], y[a:b]) for a, b in zip(edges[::2], edges[1::2]) if b - a > 1]
    return out, armco


def _buildings(geometry: TrackGeometry, first_straight_m: float) -> list[dict]:
    """Grandstand and pit garages beside the start straight, each on a side that is clear of other track."""
    half = geometry.width_m / 2
    start_idx = slice(0, int(first_straight_m / geometry.step_m) + 1)
    out = []
    for kind, s0, s1, near, far in (("grandstand", 0.12, 0.45, half + 8, half + 26), ("pits", 0.5, 0.9, half + 8, half + 24)):
        a, b = s0 * first_straight_m, s1 * first_straight_m
        xs, ys, h = geometry.pose_at(np.array([a, b, b, a]))
        for side in (1, -1):
            lat = side * np.array([near, near, far, far])
            qx, qy = xs - lat * np.sin(h[0]), ys + lat * np.cos(h[0])
            if distance_to_track(geometry, qx, qy, skip=start_idx).min() > half + 6:
                out.append({"kind": kind, **_xy(qx, qy)})
                break
    return out


def _trees(geometry: TrackGeometry, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    lo = np.array([geometry.x_m.min(), geometry.y_m.min()]) - SCENERY_PAD_M
    hi = np.array([geometry.x_m.max(), geometry.y_m.max()]) + SCENERY_PAD_M
    clusters = rng.uniform(lo, hi, size=(int(np.prod(hi - lo) / 40_000) + 10, 2))
    pts = np.concatenate([c + rng.normal(0, 22, size=(rng.integers(4, 15), 2)) for c in clusters])
    clearance = geometry.width_m / 2 + CURB_WIDTH_M + RUNOFF_WIDTH_M + TREE_CLEARANCE_M
    pts = pts[distance_to_track(geometry, pts[:, 0], pts[:, 1]) > clearance]
    return {**_xy(pts[:, 0], pts[:, 1]), "r": np.round(rng.uniform(3, 7, len(pts)), 1).tolist()}


def scene(
    geometry: TrackGeometry,
    playback: LapPlayback,
    car: dict | None = None,
    weather: Weather = WEATHER[0],
    first_straight_m: float = 300.0,
) -> dict:
    """Everything the canvas needs, in world metres, plus the overview camera.

    ``car`` is ``{"body", "wheels", "engine", "color"}``: part keys and #RRGGBB.
    """
    car = {"body": "kart", "wheels": "standard", "engine": "standard", "color": "#F2F2F2", **(car or {})}
    half = geometry.width_m / 2
    left, right = geometry.offset(half), geometry.offset(-half)
    camera = Camera.fit(np.concatenate((left[0], right[0])), np.concatenate((left[1], right[1])), VIEW_W, VIEW_H, 24)
    runoff, armco = _runoff(geometry)
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
        "bounds": [float(geometry.x_m.min() - SCENERY_PAD_M), float(geometry.y_m.min() - SCENERY_PAD_M),
                   float(geometry.x_m.max() + SCENERY_PAD_M), float(geometry.y_m.max() + SCENERY_PAD_M)],
        "track": {
            "name": geometry.track_name,
            "width": geometry.width_m,
            "center": _xy(geometry.x_m, geometry.y_m),
            "left": _xy(*left),
            "right": _xy(*right),
            "curbs": curbs,
            "curb_width": CURB_WIDTH_M,
            "runoff": runoff,
            "armco": armco,
            "runoff_width": RUNOFF_WIDTH_M,
            "start": {"x": float(geometry.x_m[0]), "y": float(geometry.y_m[0]), "h": float(geometry.heading_rad[0])},
        },
        "scenery": {
            "buildings": _buildings(geometry, first_straight_m),
            "trees": _trees(geometry, seed=sum(map(ord, geometry.track_name))),
        },
        "weather": {"name": weather.name, "rain": weather.rain_intensity},
        "car": car,
        "lap_time": playback.lap_time_s,
        "frames": {
            "t": np.round(playback.time_s, 4).tolist(),
            "x": np.round(playback.x_m, 3).tolist(),
            "y": np.round(playback.y_m, 3).tolist(),
            "h": np.round(playback.heading_rad, 5).tolist(),
            "v": np.round(playback.speed_mps, 3).tolist(),
        },
    }


def track_view_html(*args, **kwargs) -> str:
    """``scene(...)`` embedded in the canvas page; same arguments as ``scene``."""
    payload = json.dumps(scene(*args, **kwargs)).replace("</", "<\\/")
    return _TEMPLATE.read_text(encoding="utf-8").replace("__SCENE__", payload)
