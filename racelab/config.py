"""Configuration structures for vehicle subsystems.

Only some fields feed the current point-mass engine; the rest are stored for
future models and have NO effect on results yet. Each field says which.
Track surface grip and curvature already live on ``Segment.grip_multiplier``,
``Segment.radius_m``/``direction`` and ``TrackGeometry.curvature_per_m``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from racelab.car import Car

NOT_MODELED = (
    "TireCompound.temperature_c",
    "TireCompound.optimal_temperature_c",
    "TireCompound.wear_fraction",
)


def _check_positive(**values: float) -> None:
    for name, value in values.items():
        if not (math.isfinite(value) and value > 0):
            raise ValueError(f"{name} must be positive and finite, got {value!r}")


@dataclass(frozen=True)
class TireCompound:
    name: str = "medium"
    grip_coefficient: float = 1.2
    """Used: becomes ``Car.tire_friction``."""
    temperature_c: float = 80.0
    """Stored only: no thermal model yet."""
    optimal_temperature_c: float = 90.0
    """Stored only."""
    wear_fraction: float = 0.0
    """Stored only: 0 is new, 1 is fully worn."""

    def __post_init__(self) -> None:
        _check_positive(grip_coefficient=self.grip_coefficient)
        if not 0 <= self.wear_fraction <= 1:
            raise ValueError(f"wear_fraction must be in [0, 1], got {self.wear_fraction!r}")


@dataclass(frozen=True)
class AeroPackage:
    name: str = "standard"
    drag_coefficient: float = 0.32
    """Used."""
    frontal_area_m2: float = 2.2
    """Used."""
    downforce_coefficient_m2: float = 0.0
    """Used: lift coefficient times area (C_L * A)."""

    def __post_init__(self) -> None:
        _check_positive(drag_coefficient=self.drag_coefficient, frontal_area_m2=self.frontal_area_m2)
        if not (math.isfinite(self.downforce_coefficient_m2) and self.downforce_coefficient_m2 >= 0):
            raise ValueError(f"downforce_coefficient_m2 must be >= 0, got {self.downforce_coefficient_m2!r}")


@dataclass(frozen=True)
class BodyPackage:
    """Appearance and footprint; used by the renderer only."""

    name: str = "coupe"
    color_hex: str = "#F2F2F2"
    length_m: float = 4.6
    width_m: float = 1.9

    def __post_init__(self) -> None:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", self.color_hex):
            raise ValueError(f"color_hex must look like #RRGGBB, got {self.color_hex!r}")
        _check_positive(length_m=self.length_m, width_m=self.width_m)


@dataclass(frozen=True)
class VehicleConfig:
    mass_kg: float = 1200.0
    power_w: float = 300e3
    max_braking_decel_mps2: float = 10.0
    max_tractive_force_n: float = 12_000.0
    drivetrain_efficiency: float = 0.88
    tires: TireCompound = field(default_factory=TireCompound)
    aero: AeroPackage = field(default_factory=AeroPackage)
    body: BodyPackage = field(default_factory=BodyPackage)

    def to_car(self, name: str = "Car") -> Car:
        """The engine's ``Car``. Fields listed in ``NOT_MODELED`` are dropped here."""
        return Car(
            name=name,
            mass_kg=self.mass_kg,
            power_w=self.power_w,
            drag_coefficient=self.aero.drag_coefficient,
            frontal_area_m2=self.aero.frontal_area_m2,
            tire_friction=self.tires.grip_coefficient,
            max_braking_decel_mps2=self.max_braking_decel_mps2,
            max_tractive_force_n=self.max_tractive_force_n,
            drivetrain_efficiency=self.drivetrain_efficiency,
            downforce_coefficient_m2=self.aero.downforce_coefficient_m2,
        )
