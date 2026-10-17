"""Headline numbers for the UI, derived from the existing engine (no new physics)."""

from __future__ import annotations

import numpy as np

from racelab.car import Car
from racelab.physics import net_acceleration
from racelab.simulation import LapResult

HP_TO_W = 745.7  # mechanical horsepower
# The UI does not expose these; every setup uses the same drivetrain.
DRIVETRAIN_EFFICIENCY = 0.88
MAX_TRACTIVE_FORCE_N = 12_000.0


def car_from_setup(
    mass_kg: float,
    power_hp: float,
    drag_coefficient: float,
    frontal_area_m2: float,
    tire_friction: float,
    max_braking_decel_mps2: float,
    name: str = "Current",
) -> Car:
    """Build a validated ``Car`` from UI units (power in hp)."""
    return Car(
        name=name,
        mass_kg=float(mass_kg),
        power_w=float(power_hp) * HP_TO_W,
        drag_coefficient=float(drag_coefficient),
        frontal_area_m2=float(frontal_area_m2),
        tire_friction=float(tire_friction),
        max_braking_decel_mps2=float(max_braking_decel_mps2),
        max_tractive_force_n=MAX_TRACTIVE_FORCE_N,
        drivetrain_efficiency=DRIVETRAIN_EFFICIENCY,
    )


def time_to_speed(car: Car, target_mps: float = 100 / 3.6, dv_mps: float = 0.05) -> float | None:
    """Standing-start time (s) to ``target_mps`` at full throttle, ``dt = dv / a(v)``.

    ``None`` if drag stops the car short of the target speed.
    """
    n = int(np.ceil(target_mps / dv_mps))
    dv = target_mps / n
    a = np.array([net_acceleration(car, (k + 0.5) * dv) for k in range(n)])
    if np.any(a <= 0):
        return None
    return float(np.sum(dv / a))


def corner_average_speed_mps(lap: LapResult) -> float | None:
    """Mean speed (m/s) over the points that sit in a corner; ``None`` if the track has none."""
    in_corner = np.isfinite(lap.corner_speed_limit_mps)
    return float(lap.speed_mps[in_corner].mean()) if in_corner.any() else None
