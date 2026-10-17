"""Builds the telemetry dashboard (stacked channel charts, speed map, lap summary).
Rendering only: every value comes from ``racelab.telemetry``."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from racelab.telemetry import Telemetry, lap_summary

_TEMPLATE = Path(__file__).with_name("telemetry.html")


def _channels(t: Telemetry) -> dict:
    r = lambda a, d: np.round(a, d).tolist()
    return {"speed": r(t.speed_mps * 3.6, 1), "throttle": r(t.throttle_pct, 1), "brake": r(t.brake_pct, 1), "steer": r(t.steering_deg, 2)}


def telemetry_payload(current: Telemetry, baseline: Telemetry) -> dict:
    """Both laps must be on the same circuit and distance grid."""
    if current.distance_m.shape != baseline.distance_m.shape or not np.allclose(current.distance_m, baseline.distance_m):
        raise ValueError("current and baseline laps must share a distance grid")
    return {
        "length": current.length_m,
        "distance": np.round(current.distance_m, 1).tolist(),
        "time": {"current": np.round(current.time_s, 3).tolist(), "baseline": np.round(baseline.time_s, 3).tolist()},
        "series": {"current": _channels(current), "baseline": _channels(baseline)},
        "delta": np.round(current.time_s - baseline.time_s, 3).tolist(),
        "map": {"x": np.round(current.x_m, 1).tolist(), "y": np.round(current.y_m, 1).tolist()},
        "summary": {"current": lap_summary(current), "baseline": lap_summary(baseline)},
    }


def telemetry_html(current: Telemetry, baseline: Telemetry) -> str:
    payload = json.dumps(telemetry_payload(current, baseline)).replace("</", "<\\/")
    return _TEMPLATE.read_text(encoding="utf-8").replace("__TELEMETRY__", payload)
