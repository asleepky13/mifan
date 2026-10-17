"""Kart-style parts. Each part modifies real engine inputs, so it changes the
simulated speed profile (and therefore lap time and on-track movement).

Effects multiply (``*_scale``) or add (``mass_delta_kg``) on top of the base
setup. The numbers are game-style balance choices, not measured data.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from racelab.car import Car

CATEGORIES = ("body", "wheels", "engine")


@dataclass(frozen=True)
class Part:
    key: str
    """Stable id; the renderer draws the part from it."""
    name: str
    category: str
    mass_delta_kg: float = 0.0
    power_scale: float = 1.0
    drag_scale: float = 1.0
    area_scale: float = 1.0
    grip_scale: float = 1.0
    braking_scale: float = 1.0
    traction_scale: float = 1.0

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f"category must be one of {CATEGORIES}, got {self.category!r}")

    def describe(self) -> str:
        """Short effect summary for the UI, e.g. ``"+60 kg · drag ×0.85"``."""
        bits = [f"{self.mass_delta_kg:+.0f} kg"] if self.mass_delta_kg else []
        for label, value in (
            ("power", self.power_scale), ("drag", self.drag_scale), ("frontal area", self.area_scale),
            ("grip", self.grip_scale), ("brakes", self.braking_scale), ("traction", self.traction_scale),
        ):
            if value != 1.0:
                bits.append(f"{label} ×{value:g}")
        return " · ".join(bits) or "baseline"


PARTS = (
    Part("kart", "Standard Kart", "body"),
    Part("comet", "Comet Coupe", "body", mass_delta_kg=60, drag_scale=0.85, area_scale=0.95),
    Part("bulldog", "Bulldog Truck", "body", mass_delta_kg=250, drag_scale=1.25, area_scale=1.3, traction_scale=1.15),
    Part("feather", "Feather Frame", "body", mass_delta_kg=-150, drag_scale=1.15, area_scale=0.85),
    Part("standard", "Standard Wheels", "wheels"),
    Part("slick", "Slicks", "wheels", mass_delta_kg=10, grip_scale=1.12, braking_scale=1.05),
    Part("monster", "Monster Wheels", "wheels", mass_delta_kg=60, grip_scale=0.92, area_scale=1.08, braking_scale=0.95),
    Part("roller", "Rollers", "wheels", mass_delta_kg=-20, grip_scale=0.95, area_scale=0.97),
    Part("standard", "Standard Engine", "engine"),
    Part("turbo", "Turbo", "engine", mass_delta_kg=40, power_scale=1.25),
    Part("electric", "Electric", "engine", mass_delta_kg=80, power_scale=0.9, traction_scale=1.3),
    Part("light", "Lightweight", "engine", mass_delta_kg=-50, power_scale=0.85),
)
PARTS_BY_CATEGORY = {c: {p.key: p for p in PARTS if p.category == c} for c in CATEGORIES}
DEFAULT_PARTS = {c: next(iter(PARTS_BY_CATEGORY[c])) for c in CATEGORIES}


def apply_parts(car: Car, parts: Iterable[Part]) -> Car:
    """``car`` with every part's effect applied; the result is validated like any ``Car``."""
    parts = list(parts)
    if sorted(p.category for p in parts) != sorted(set(p.category for p in parts)):
        raise ValueError("at most one part per category")
    fields = dict(
        mass_kg=car.mass_kg, power_w=car.power_w, drag_coefficient=car.drag_coefficient,
        frontal_area_m2=car.frontal_area_m2, tire_friction=car.tire_friction,
        max_braking_decel_mps2=car.max_braking_decel_mps2, max_tractive_force_n=car.max_tractive_force_n,
    )
    for p in parts:
        fields["mass_kg"] += p.mass_delta_kg
        fields["power_w"] *= p.power_scale
        fields["drag_coefficient"] *= p.drag_scale
        fields["frontal_area_m2"] *= p.area_scale
        fields["tire_friction"] *= p.grip_scale
        fields["max_braking_decel_mps2"] *= p.braking_scale
        fields["max_tractive_force_n"] *= p.traction_scale
    return replace(car, **fields)
