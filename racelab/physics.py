"""Point-mass vehicle physics with downforce, gears, axle load transfer and a
friction circle. SI units: m, s, kg, N, W.

Models (each reduces to the original flat point-mass model when switched off):
- Downforce ``0.5 * rho * C_L * A * v^2`` adds to the normal load, so grip grows with speed.
- Gearbox: the car uses the gear giving most force; engine power follows
  ``P(rpm) = P_max * x * (2 - x)`` with ``x = rpm / peak_rpm``; instant shifts;
  no force above the top-gear redline.
- Longitudinal load transfer ``dN = m * a * h / wheelbase`` moves load onto the
  rear under acceleration; a single driven axle's traction limit includes it.
- Friction circle: grip used for cornering is not available for braking or
  accelerating, ``F_long <= mu * N * sqrt(1 - (F_lat / (mu * N))^2)``.

Still not modelled: suspension, tyre load sensitivity, slip angles, tyre
temperature, shift time, rolling resistance, gradient and wind. Drag is
ignored while braking (slightly conservative) and in the load-transfer term.
"""

from __future__ import annotations

import math

from racelab.car import Car

AIR_DENSITY_KG_M3 = 1.225
GRAVITY_MPS2 = 9.81
RPM_PER_RAD_S = 60 / (2 * math.pi)

# P / v diverges as v -> 0. Below this speed the flat power limit is evaluated at
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


def downforce(car: Car, speed_mps: float) -> float:
    """``F_down = 0.5 * rho * C_L * A * v^2`` in N."""
    _check_speed(speed_mps)
    return 0.5 * AIR_DENSITY_KG_M3 * car.downforce_coefficient_m2 * speed_mps**2


def normal_load(car: Car, speed_mps: float) -> float:
    """Total tyre load ``m * g + F_down`` in N."""
    return car.mass_kg * GRAVITY_MPS2 + downforce(car, speed_mps)


def grip_left_for_longitudinal(car: Car, speed_mps: float, curvature_per_m: float, grip_multiplier: float = 1.0) -> float:
    """Friction circle: share (0-1) of total grip still free for braking or accelerating.

    Cornering on curvature ``k`` needs lateral force ``m * v^2 * |k|``; with total grip
    ``mu * N``, the longitudinal share left is ``sqrt(1 - (F_lat / (mu * N))^2)``.
    """
    used = car.mass_kg * speed_mps**2 * abs(curvature_per_m) / (effective_grip(car, grip_multiplier) * normal_load(car, speed_mps))
    return math.sqrt(max(0.0, 1.0 - used * used))


def traction_limit(car: Car, speed_mps: float, grip_multiplier: float = 1.0) -> float:
    """Most forward force the driven tyres can transmit in a straight line (N).

    One driven axle with static load share ``f`` gains (rear) or loses (front)
    ``F * h / L`` of load when the car accelerates with force ``F``. Solving
    ``F = mu * (f * N +/- F * h / L)`` for F gives the closed forms below.
    """
    mu, n = effective_grip(car, grip_multiplier), normal_load(car, speed_mps)
    if car.driven_axle == "all":
        return mu * n
    transfer = mu * car.cg_height_m / car.wheelbase_m
    if car.driven_axle == "rear":
        limit = mu * n * car.rear_weight_fraction / (1 - transfer) if transfer < 1 else math.inf
    else:
        limit = mu * n * (1 - car.rear_weight_fraction) / (1 + transfer)
    return min(limit, mu * n)


def engine_force(car: Car, speed_mps: float) -> tuple[int, float]:
    """``(gear, force_N)`` the engine delivers at the wheels; gear 0 = no gearbox.

    Without a gearbox: flat power, ``P * efficiency / max(v, 0.5 m/s)``. With one,
    the gear giving most force below redline; ``(0, 0.0)`` above top-gear redline.
    """
    _check_speed(speed_mps)
    gb = car.gearbox
    if gb is None:
        return 0, car.power_w * car.drivetrain_efficiency / max(speed_mps, POWER_LIMIT_MIN_SPEED_MPS)
    best = (0, 0.0)
    for gear, ratio in enumerate(gb.ratios, start=1):
        rpm = speed_mps / gb.wheel_radius_m * ratio * RPM_PER_RAD_S
        if rpm > gb.redline_rpm:
            continue
        rpm = max(rpm, gb.launch_rpm)  # clutch slip below launch speed
        x = rpm / gb.peak_power_rpm
        torque = car.power_w * max(0.0, x * (2 - x)) / (rpm / RPM_PER_RAD_S)
        force = torque * ratio * car.drivetrain_efficiency / gb.wheel_radius_m
        if force > best[1]:
            best = (gear, force)
    return best


def selected_gear(car: Car, speed_mps: float) -> int:
    """Gear in use at full throttle (0 = no gearbox, or above top-gear redline)."""
    return engine_force(car, speed_mps)[0]


def drive_force(car: Car, speed_mps: float, grip_multiplier: float = 1.0, curvature_per_m: float = 0.0) -> float:
    """Forward force at the contact patch in N: ``min(F_max, engine, traction * friction-circle share)``."""
    return min(
        car.max_tractive_force_n,
        engine_force(car, speed_mps)[1],
        traction_limit(car, speed_mps, grip_multiplier) * grip_left_for_longitudinal(car, speed_mps, curvature_per_m, grip_multiplier),
    )


def net_acceleration(car: Car, speed_mps: float, grip_multiplier: float = 1.0, curvature_per_m: float = 0.0) -> float:
    """Full-throttle longitudinal acceleration ``(F_drive - F_drag) / m`` in m/s^2."""
    return (drive_force(car, speed_mps, grip_multiplier, curvature_per_m) - aero_drag_force(car, speed_mps)) / car.mass_kg


def braking_deceleration(car: Car, grip_multiplier: float = 1.0, speed_mps: float = 0.0, curvature_per_m: float = 0.0) -> float:
    """Maximum deceleration magnitude in m/s^2: ``min(a_configured, mu * N / m * friction-circle share)``.

    With ideal brake balance all four tyres brake, so load transfer does not limit it.
    """
    friction = effective_grip(car, grip_multiplier) * normal_load(car, speed_mps) / car.mass_kg
    return min(car.max_braking_decel_mps2, friction * grip_left_for_longitudinal(car, speed_mps, curvature_per_m, grip_multiplier))


def cornering_speed(radius_m: float | None, mu_effective: float) -> float:
    """Steady-state corner limit without downforce, ``sqrt(mu_eff * g * r)`` in m/s; ``inf`` for a straight."""
    if not (math.isfinite(mu_effective) and mu_effective > 0):
        raise ValueError(f"mu_effective must be positive and finite, got {mu_effective!r}")
    if radius_m is None:
        return math.inf
    if not (math.isfinite(radius_m) and radius_m > 0):
        raise ValueError(f"radius_m must be positive and finite or None, got {radius_m!r}")
    return math.sqrt(mu_effective * GRAVITY_MPS2 * radius_m)


def corner_speed_limit(car: Car, curvature_per_m: float, grip_multiplier: float = 1.0) -> float:
    """Corner limit with downforce (m/s): solves ``m v^2 |k| = mu (m g + k_L v^2)``.

    ``v = sqrt(mu m g / (m |k| - mu k_L))`` with ``k_L = 0.5 rho C_L A``; ``inf`` on a
    straight or when downforce grows faster than the cornering demand.
    """
    mu, k = effective_grip(car, grip_multiplier), abs(curvature_per_m)
    denominator = car.mass_kg * k - mu * 0.5 * AIR_DENSITY_KG_M3 * car.downforce_coefficient_m2
    if k == 0 or denominator <= 0:
        return math.inf
    return math.sqrt(mu * car.mass_kg * GRAVITY_MPS2 / denominator)


def top_speed_bound(car: Car) -> float:
    """Speed (m/s) above which drag exceeds any possible drive force.

    Drive force is at most ``min(F_max, P * eff / v)`` (a gearbox only lowers it),
    so at the smaller of the power-limited and force-limited terminal speeds the
    car cannot accelerate.
    """
    k = 0.5 * AIR_DENSITY_KG_M3 * car.drag_coefficient * car.frontal_area_m2
    power_terminal = (car.power_w * car.drivetrain_efficiency / k) ** (1 / 3)
    force_terminal = math.sqrt(car.max_tractive_force_n / k)
    return min(power_terminal, force_terminal)
