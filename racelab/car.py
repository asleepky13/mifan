"""Car configuration model. All quantities are SI units."""

from __future__ import annotations

import math
from dataclasses import dataclass

# Racing slicks peak around 1.7-1.9; anything above this is not a tire.
MAX_TIRE_FRICTION = 3.0
DRIVEN_AXLES = ("all", "rear", "front")


def _positive(name: str, value: object) -> None:
    if not (isinstance(value, (int, float)) and math.isfinite(value) and value > 0):
        raise ValueError(f"{name} must be a positive finite number, got {value!r}")


@dataclass(frozen=True)
class Gearbox:
    """Fixed gear set with instant shifts; the car always uses the gear giving most force."""

    ratios: tuple[float, ...]
    """Overall ratio per gear (gear x final drive), first gear first, strictly decreasing."""
    redline_rpm: float = 8000.0
    peak_power_rpm: float = 7000.0
    launch_rpm: float = 3500.0
    """Below this engine speed the clutch slips and the engine is held here."""
    wheel_radius_m: float = 0.33

    def __post_init__(self) -> None:
        if not self.ratios or any(not (isinstance(r, (int, float)) and math.isfinite(r) and r > 0) for r in self.ratios):
            raise ValueError(f"ratios must be positive finite numbers, got {self.ratios!r}")
        if any(a <= b for a, b in zip(self.ratios, self.ratios[1:])):
            raise ValueError("ratios must strictly decrease from first gear to top gear")
        for field in ("redline_rpm", "peak_power_rpm", "launch_rpm", "wheel_radius_m"):
            _positive(field, getattr(self, field))
        if not self.launch_rpm < self.peak_power_rpm <= self.redline_rpm:
            raise ValueError("need launch_rpm < peak_power_rpm <= redline_rpm")


@dataclass(frozen=True)
class Car:
    """A point-mass car with optional downforce, gearbox and axle load transfer.

    The defaults (no downforce, no gearbox, grip on all wheels) reproduce the
    original flat-power point-mass model exactly. Build variants with
    ``dataclasses.replace(car, field=value)``; the copy is validated the same way.
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
    downforce_coefficient_m2: float = 0.0
    """Lift coefficient times area, C_L * A (m^2); 0 = no downforce."""
    driven_axle: str = "all"
    """'all' (traction from every wheel), 'rear' or 'front' (traction from one axle, with load transfer)."""
    rear_weight_fraction: float = 0.5
    cg_height_m: float = 0.5
    wheelbase_m: float = 2.6
    gearbox: Gearbox | None = None
    """None = flat power curve, P * efficiency / v."""

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
            "cg_height_m",
            "wheelbase_m",
        ):
            _positive(field, getattr(self, field))
        if self.drivetrain_efficiency > 1:
            raise ValueError(f"drivetrain_efficiency must be <= 1, got {self.drivetrain_efficiency!r}")
        if self.tire_friction > MAX_TIRE_FRICTION:
            raise ValueError(f"tire_friction must be <= {MAX_TIRE_FRICTION}, got {self.tire_friction!r}")
        if not (isinstance(self.downforce_coefficient_m2, (int, float)) and math.isfinite(self.downforce_coefficient_m2)
                and self.downforce_coefficient_m2 >= 0):
            raise ValueError(f"downforce_coefficient_m2 must be finite and >= 0, got {self.downforce_coefficient_m2!r}")
        if self.driven_axle not in DRIVEN_AXLES:
            raise ValueError(f"driven_axle must be one of {DRIVEN_AXLES}, got {self.driven_axle!r}")
        if not 0 < self.rear_weight_fraction < 1:
            raise ValueError(f"rear_weight_fraction must be in (0, 1), got {self.rear_weight_fraction!r}")
