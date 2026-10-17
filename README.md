# RaceLab — Phase 1: Physics Engine

The physics engine for RaceLab, a 2D top-down racing simulator. It simulates a point-mass car around a closed circuit, gives a lap time and a physically constrained speed profile, compares cars and runs one-parameter sensitivity studies. There is no UI in this phase.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate   # Python 3.11+
pip install -r requirements.txt
python -m unittest discover -v
```

## Usage

```python
from racelab import Car, TECHNICAL_CIRCUIT, HIGH_SPEED_CIRCUIT, simulate_lap, compare_cars, sensitivity_analysis

car = Car(
    name="Sports",
    mass_kg=1300, power_w=250e3, drag_coefficient=0.32, frontal_area_m2=2.0,
    tire_friction=1.1, max_braking_decel_mps2=10.0, max_tractive_force_n=9000,
    drivetrain_efficiency=0.88,
)

lap = simulate_lap(car, TECHNICAL_CIRCUIT, step_m=1.0)
print(f"{lap.lap_time_s:.2f} s, top {lap.max_speed_mps * 3.6:.0f} km/h, converged={lap.converged}")

from dataclasses import replace
for entry in compare_cars([car, replace(car, name="Light", mass_kg=1100)], HIGH_SPEED_CIRCUIT):
    print(entry.car.name, round(entry.result.lap_time_s, 2), f"+{entry.gap_to_fastest_s:.2f}")

for name, s in sensitivity_analysis(car, TECHNICAL_CIRCUIT).items():
    print(name, dict(zip(s.scales.tolist(), s.lap_times_s.round(2).tolist())))
```

## Modules

| Module | Contents |
|---|---|
| `racelab/car.py` | `Car` dataclass with validation. Build variants with `dataclasses.replace`. |
| `racelab/track.py` | `Segment` (`radius_m=None` is a straight), `Track` (a closed loop), and the fictional circuits `TECHNICAL_CIRCUIT` (1.58 km, radii 18–60 m) and `HIGH_SPEED_CIRCUIT` (5.14 km, radii 90–400 m). |
| `racelab/physics.py` | Drag, drive force, net acceleration, braking, cornering speed and a top-speed bound. |
| `racelab/simulation.py` | `simulate_lap` → `LapResult`. |
| `racelab/analysis.py` | `compare_cars` → `ComparisonEntry` list; `sensitivity_analysis` → a `SensitivityResult` per parameter. |

## Equations (SI units)

| Quantity | Formula |
|---|---|
| Drag | `F_drag = 0.5 · ρ · Cd · A · v²`, with ρ = 1.225 kg/m³ |
| Drive force | `F_drive = min(F_max, μ_eff · m · g, P · η / max(v, 0.5 m/s))` |
| Net acceleration | `a = (F_drive − F_drag) / m` |
| Braking | `a_brake = min(a_configured, μ_eff · g)` |
| Cornering speed | `v_max = √(μ_eff · g · r)`, with g = 9.81 m/s² |
| Effective grip | `μ_eff = tire_friction × surface grip_multiplier` |
| Speed step | `v_next² = v² + 2 · a · ds` |
| Step time | `dt = 2 · ds / (v_i + v_{i+1})` |

**Low-speed safeguard.** `P/v` diverges as `v → 0`, so below 0.5 m/s the power limit is evaluated at 0.5 m/s. The force is also capped by `F_max` and the friction limit, so it is always finite and there is never a division by zero.

## Simulation algorithm

1. The loop is split into `n = ceil(L / step_m)` equal steps. Each point covers ±ds/2 and takes the lowest corner limit and grip of every segment that window touches, so short corners are never skipped at coarse resolution.
2. Every point starts at `min(corner limit, top-speed bound)`.
3. Forward (acceleration) and backward (braking) passes repeat, with indices wrapping across the start/finish line, until a full sweep changes no speed by more than `tolerance_mps`. Speeds only decrease and are bounded below, so the passes converge, usually in 2 iterations. This is how braking begins before corners, including corners just after the finish line.
4. The final profile is checked against the corner, drive and braking limits (`constraints_satisfied`).
5. Lap time sums `dt`. A zero or non-finite speed raises `ArithmeticError` instead of being patched over.

`LapResult` fields: `lap_time_s`, `total_distance_m`, `step_m`, `distance_m`, `speed_mps`, `acceleration_mps2` (from point i to i+1), `corner_speed_limit_mps` (`inf` on straights), `max_speed_mps`, `average_speed_mps`, `converged`, `iterations`, `constraints_satisfied`.

## Sensitivity analysis

Parameters: `mass`, `power`, `drag_coefficient`, `frontal_area`, `grip` (tire friction) and `braking`. Each one is scaled by `scales` (default 0.8–1.2), and the 1.0 baseline is always included. A scale that gives an invalid car (for example tire friction above 3.0) is reported with `valid=False`, `lap_times_s=nan` and the validation message in `errors`. It is never silently dropped.

## Assumptions and limitations

- The car is a point mass: no weight transfer, suspension, tire load sensitivity, slip angles or tire temperature.
- No aerodynamic downforce, so grip does not increase with speed.
- The engine is a flat power curve with a fixed tractive-force cap: no gears, torque curve, shift time or rev limit.
- No friction circle: full cornering grip is never combined with full braking or acceleration. Corners are driven at their limit speed.
- No rolling resistance, gradient or wind. Drag is ignored under braking, which makes braking distances slightly conservative.
- Flying lap: the car crosses the start line at the speed it carries from the previous lap.
- Explicit Euler in `v²`. Lap times change by less than 1% between 0.5 m and 5 m steps on the bundled circuits.
- The bundled tracks are lists of segments. Their geometric closure is not checked.
