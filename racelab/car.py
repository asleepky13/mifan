"""Car configuration model. All quantities are SI units."""

from __future__ import annotations

import math
from dataclasses import dataclass

# Racing slicks peak around 1.7-1.9; anything above this is not a tire.
MAX_TIRE_FRICTION = 3.0


@dataclass(frozen=True)
class Car:
    """A point-mass car.

    Build variants with ``dataclasses.replace(car, field=value)``; the copy is
    validated the same way.
    """

    name: str
    mass_kg: float
    power_w: float
    drag_coefficient: float
    frontal_area_m2: float
    tire_friction: float
    max_braking_decel_mps2: float
    max_tractive_force_n: float
    drivetrain_efficiency: float

    def __post_init__(self) -> None:
        for field in (
            "mass_kg",
            "power_w",
            "drag_coefficient",
            "frontal_area_m2",
            "tire_friction",
            "max_braking_decel_mps2",
            "max_tractive_force_n",
            "drivetrain_efficiency",
        ):
            value = getattr(self, field)
            if not (isinstance(value, (int, float)) and math.isfinite(value) and value > 0):
                raise ValueError(f"{field} must be a positive finite number, got {value!r}")
        if self.drivetrain_efficiency > 1:
            raise ValueError(f"drivetrain_efficiency must be <= 1, got {self.drivetrain_efficiency!r}")
        if self.tire_friction > MAX_TIRE_FRICTION:
            raise ValueError(f"tire_friction must be <= {MAX_TIRE_FRICTION}, got {self.tire_friction!r}")
