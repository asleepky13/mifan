"""Car comparison and one-at-a-time parameter sensitivity."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Iterable, Sequence

import numpy as np

from racelab.car import Car
from racelab.simulation import LapResult, simulate_lap
from racelab.track import Track

# Sensitivity parameter name -> Car field it scales.
SENSITIVITY_PARAMETERS = {
    "mass": "mass_kg",
    "power": "power_w",
    "drag_coefficient": "drag_coefficient",
    "frontal_area": "frontal_area_m2",
    "grip": "tire_friction",
    "braking": "max_braking_decel_mps2",
}
DEFAULT_SCALES = (0.8, 0.9, 1.0, 1.1, 1.2)


@dataclass(frozen=True)
class ComparisonEntry:
    car: Car
    result: LapResult
    gap_to_fastest_s: float


def compare_cars(cars: Sequence[Car], track: Track, step_m: float = 2.0) -> list[ComparisonEntry]:
    """Simulate every car on ``track``; entries keep the input order."""
    if not cars:
        raise ValueError("compare_cars needs at least one car")
    results = [simulate_lap(car, track, step_m) for car in cars]
    fastest = min(r.lap_time_s for r in results)
    return [ComparisonEntry(car, r, r.lap_time_s - fastest) for car, r in zip(cars, results)]


@dataclass(frozen=True)
class SensitivityResult:
    """Lap time against one scaled parameter. Arrays are aligned with ``scales``.

    A scale that makes the car invalid has ``valid=False``, ``lap_times_s=nan``,
    ``results=None`` and the validation message in ``errors``.
    """

    parameter: str
    car_field: str
    scales: np.ndarray
    values: np.ndarray
    lap_times_s: np.ndarray
    valid: np.ndarray
    errors: tuple[str, ...]
    results: tuple[LapResult | None, ...]
    baseline_lap_time_s: float


def sensitivity_analysis(
    car: Car,
    track: Track,
    parameters: Iterable[str] = tuple(SENSITIVITY_PARAMETERS),
    scales: Iterable[float] = DEFAULT_SCALES,
    step_m: float = 2.0,
) -> dict[str, SensitivityResult]:
    """Scale one parameter at a time around ``car``. The 1.0 baseline is always included."""
    scales = sorted(set(scales) | {1.0})
    if not all(math.isfinite(s) and s > 0 for s in scales):
        raise ValueError(f"scales must be positive and finite, got {scales!r}")
    parameters = list(parameters)
    unknown = [p for p in parameters if p not in SENSITIVITY_PARAMETERS]
    if unknown:
        raise ValueError(f"unknown parameters {unknown}; choose from {list(SENSITIVITY_PARAMETERS)}")

    baseline = simulate_lap(car, track, step_m)
    out: dict[str, SensitivityResult] = {}
    for parameter in parameters:
        field = SENSITIVITY_PARAMETERS[parameter]
        base_value = getattr(car, field)
        results: list[LapResult | None] = []
        errors: list[str] = []
        for scale in scales:
            if scale == 1.0:
                results.append(baseline)
                errors.append("")
                continue
            try:
                variant = replace(car, **{field: base_value * scale})
            except ValueError as exc:
                results.append(None)
                errors.append(str(exc))
                continue
            results.append(simulate_lap(variant, track, step_m))
            errors.append("")
        out[parameter] = SensitivityResult(
            parameter=parameter,
            car_field=field,
            scales=np.array(scales),
            values=np.array(scales) * base_value,
            lap_times_s=np.array([r.lap_time_s if r else np.nan for r in results]),
            valid=np.array([r is not None for r in results]),
            errors=tuple(errors),
            results=tuple(results),
            baseline_lap_time_s=baseline.lap_time_s,
        )
    return out
