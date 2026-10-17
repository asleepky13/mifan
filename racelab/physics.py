"""Point-mass vehicle physics. SI units: m, s, kg, N, W.

Assumptions and limitations:
- The car is a point mass: no weight transfer, suspension, tire load
  sensitivity, slip angles or tire temperature.
- No aerodynamic downforce: grip does not grow with speed.
- Engine model is a flat power curve, ``F = P * efficiency / v``, capped by a
  fixed maximum tractive force and the friction limit. No gears, torque
  curve, shift time or rev limit.
- No friction circle: full braking/acceleration and full cornering grip are
  never combined. Corners are taken at their limit speed, straights use the
  full longitudinal grip.
- No rolling resistance, gradient or wind. Drag is ignored while braking
  (slightly conservative braking distances).
"""

from __future__ import annotations

import math

from racelab.car import Car

AIR_DENSITY_KG_M3 = 1.225
GRAVITY_MPS2 = 9.81

# P / v diverges as v -> 0. Below this speed the power limit is evaluated at
# this speed instead; the tractive-force and friction caps bound the result
# either way, so the drive force is always finite.
POWER_LIMIT_MIN_SPEED_MPS = 0.5


def _check_speed(speed_mps: float) -> None:
    if not (math.isfinite(speed_mps) and speed_mps >= 0):
        raise ValueError(f"speed must be finite and >= 0, got {speed_mps!r}")


def effective_grip(car: Car, grip_multiplier: float = 1.0) -> float:
    """Tire friction coefficient times the surface grip multiplier."""
    return car.tire_friction * grip_multiplier


def aero_drag_force(car: Car, speed_mps: float) -> float:
    """``F_drag = 0.5 * rho * Cd * A * v^2`` in N."""
    _check_speed(speed_mps)
    return 0.5 * AIR_DENSITY_KG_M3 * car.drag_coefficient * car.frontal_area_m2 * speed_mps**2


def drive_force(car: Car, speed_mps: float, grip_multiplier: float = 1.0) -> float:
    """Forward force at the contact patch in N.

    ``min(F_max, mu_eff * m * g, P * efficiency / max(v, POWER_LIMIT_MIN_SPEED_MPS))``.
    """
    _check_speed(speed_mps)
    power_limited = car.power_w * car.drivetrain_efficiency / max(speed_mps, POWER_LIMIT_MIN_SPEED_MPS)
    friction_limited = effective_grip(car, grip_multiplier) * car.mass_kg * GRAVITY_MPS2
    return min(car.max_tractive_force_n, friction_limited, power_limited)


def net_acceleration(car: Car, speed_mps: float, grip_multiplier: float = 1.0) -> float:
    """Full-throttle longitudinal acceleration ``(F_drive - F_drag) / m`` in m/s^2."""
    return (drive_force(car, speed_mps, grip_multiplier) - aero_drag_force(car, speed_mps)) / car.mass_kg


def braking_deceleration(car: Car, grip_multiplier: float = 1.0) -> float:
    """Maximum deceleration magnitude ``min(a_configured, mu_eff * g)`` in m/s^2."""
    return min(car.max_braking_decel_mps2, effective_grip(car, grip_multiplier) * GRAVITY_MPS2)


def cornering_speed(radius_m: float | None, mu_effective: float) -> float:
    """Steady-state corner limit ``sqrt(mu_eff * g * r)`` in m/s; ``inf`` for a straight (``None``)."""
    if not (math.isfinite(mu_effective) and mu_effective > 0):
        raise ValueError(f"mu_effective must be positive and finite, got {mu_effective!r}")
    if radius_m is None:
        return math.inf
    if not (math.isfinite(radius_m) and radius_m > 0):
        raise ValueError(f"radius_m must be positive and finite or None, got {radius_m!r}")
    return math.sqrt(mu_effective * GRAVITY_MPS2 * radius_m)


def top_speed_bound(car: Car) -> float:
    """Speed (m/s) above which drag exceeds any possible drive force.

    Drive force is at most ``min(F_max, P * eff / v)``, so at the smaller of the
    power-limited and force-limited terminal speeds the car cannot accelerate.
    """
    k = 0.5 * AIR_DENSITY_KG_M3 * car.drag_coefficient * car.frontal_area_m2
    power_terminal = (car.power_w * car.drivetrain_efficiency / k) ** (1 / 3)
    force_terminal = math.sqrt(car.max_tractive_force_n / k)
    return min(power_terminal, force_terminal)
