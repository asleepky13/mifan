# RaceLab

The physics engine for RaceLab, a 2D top-down racing simulator. It simulates a point-mass car around a closed circuit, gives a lap time and a physically constrained speed profile, compares cars and runs one-parameter sensitivity studies. There is no UI in this phase.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate   # Python 3.11+
pip install -r requirements.txt
python -m unittest discover -v
```

## Web UI

```bash
pip install -r requirements.txt
streamlit run app.py
```

A browser tab opens at http://localhost:8501. The sidebar holds the circuit and car sliders. The main area shows lap time, top speed, average speed, average corner speed and 0–100 km/h time against the default setup, plus a speed-versus-distance chart and the setup table. Every number comes from the engine below. `racelab/summary.py` converts horsepower to watts and computes 0–100 km/h by integrating `dt = dv / a(v)` with the engine's `net_acceleration`. Drivetrain efficiency (88%) and maximum tractive force (12 kN) are fixed in the UI.

**Circuits and weather.** The sidebar picks Monza, Monaco or Spa and a weather preset. Weather scales track grip, so cornering speeds and braking distances drop in the wet; the track view darkens the asphalt and draws rain. The grip factors are illustrative, not calibrated.

**Telemetry.** Stacked charts by distance: vehicle speed, throttle, brake, steering and delta time against the baseline (default setup), each comparing the current setup (blue) with the baseline (orange). A crosshair follows the pointer across every chart and the speed-coloured track map, with both laps' values at the cursor; the arrow keys move it too. A lap summary table lists the headline numbers for both laps. How the channels are derived:
- Throttle is the drive force the lap needs (mass × acceleration + drag) as a share of what the engine and tyres can deliver at that speed.
- Brake is the braking force needed as a share of the braking limit.
- Throttle and brake both account for the friction circle: grip used to corner is not available to accelerate or brake.
- Steering is the kinematic road-wheel angle, `atan(wheelbase × curvature)`, along the racing line.
- Gear is the gear the six-speed gearbox model uses at that speed.

**Garage.** Pick a body (Standard Kart, Comet Coupe, Bulldog Truck, Feather Frame), wheels (Standard, Slicks, Monster, Rollers), an engine (Standard, Turbo, Electric, Lightweight) and a wing (None, Low-Drag, High-Downforce). Each part's effect is listed under its picker. Parts feed the engine, so lap time, top speed, cornering and the car's motion on track all change; the track view draws the chosen parts. Reset to default also resets the parts.

**Racing line.** The car does not drive down the middle. It drives a minimum-curvature line: wide on corner entry, at the inside edge at the apex, wide on exit, and back to the middle on long straights. The faint dashed line in the track view shows it. The lap is simulated on that line, so the extra speed is real (Monza: 124.2 s on the centerline, 109.6 s on the line with the default car).

**On track (V2).** A top-down view of the circuit with asphalt, curbs and the chequered start/finish line. Around it: gravel traps outside slow corners, tarmac run-off outside fast ones, tyre walls, guardrails, trees, a grandstand and pit garages, all placed from the track geometry. The car moves at the simulated speed. The view has Start, Pause and Reset controls, a sim-speed selector (0.25×–8×), an Overview or Follow-car camera, and a readout of speed, lap, lap time, last lap and status. The body colour comes from the sidebar picker.

How it fits together:
- `racelab/geometry.py` builds the centerline from the segment list.
- `racelab/geometry.py` also builds the racing line (below), and the lap is simulated on it.
- `racelab/playback.py` puts the simulated speed profile on that line, giving the car's position, heading and time.
- `ui/track_view.py` packs that into JSON for `ui/track_view.html`. That page is a plain `<canvas>` with no libraries. It only interpolates between precomputed states and draws them.

The view runs inside the existing Streamlit app instead of a separate Pygame window. Animation happens in the browser, so it is smooth with no Streamlit reruns and no extra dependency. The cost is that changing a slider reloads the view and resets playback.

**V2 limitations:**
- The car follows a minimum-curvature racing line, not a minimum-time one, and as a point mass it has no slip or yaw.
- Every lap is the same flying lap.
- In the overview the car is drawn larger than scale so it stays visible. In Follow mode it is true to scale.
- Weather only changes grip: no aquaplaning, drying line, tire choice or temperature effects.

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
| `racelab/car.py` | `Car` dataclass with validation, including downforce (C_L·A), driven axle, weight distribution, centre-of-gravity height, wheelbase and an optional `Gearbox`. Defaults reproduce the plain point-mass model. Build variants with `dataclasses.replace`. |
| `racelab/track.py` | `Segment` (`radius_m=None` is a straight; `direction` +1 is a left corner, −1 a right corner), `Track` (a closed loop with `width_m`; `in_weather(w)` scales every segment's grip). Circuits in `CIRCUITS`: `MONZA` (5.79 km), `MONACO` (3.34 km) and `SPA` (7.00 km), simplified layouts inspired by the real F1 tracks, with their real corner order, turn directions and lap length; exact shapes and elevation are not reproduced. `TECHNICAL_CIRCUIT` (Monaco) and `HIGH_SPEED_CIRCUIT` (Monza) remain as aliases. `WEATHER`: Dry, Damp, Wet and Heavy rain, scaling grip to 100%, 85%, 70% and 55%. |
| `racelab/geometry.py` | `build_geometry` → `TrackGeometry` (centerline x/y, heading, signed curvature, `pose_at`, `offset`, closure error); `build_racing_line` → `RacingLine` (lateral offset, path x/y, path curvature, step lengths); `Camera` (fit-to-view and chase camera, world to screen and back). |
| `racelab/playback.py` | `LapPlayback.from_lap(lap, geometry)`; `state_at(t)` → `VehicleState` (lap, lap time, distance, x, y, heading, speed). |
| `racelab/config.py` | Future-facing configuration: `TireCompound`, `AeroPackage`, `BodyPackage`, `VehicleConfig.to_car()`. Fields listed in `NOT_MODELED` (tire temperature and wear) are stored but have **no effect** yet; downforce is modelled. |
| `racelab/parts.py` | Kart-style `PARTS` in four categories (body, wheels, engine, wing). `apply_parts(car, parts)` adds mass and downforce and scales power, drag, frontal area, grip, braking and traction, so each part changes the simulated lap. The values are game-style balance, not measured data. |
| `racelab/telemetry.py` | `build_telemetry(lap, car, track, geometry)` → `Telemetry`: speed, throttle %, brake %, kinematic steering angle, gear, time and position per sample, derived from the lap; `lap_summary` → lap time, speeds, full-throttle and braking share, max steering. |
| `ui/telemetry_view.py`, `ui/telemetry.html` | The telemetry dashboard. Rendering only, no physics. |
| `ui/track_view.py`, `ui/track_view.html` | Renders the canvas view. Rendering only, no physics. |
| `racelab/physics.py` | Drag, downforce, normal load, friction circle, driven-axle traction with load transfer, gearbox engine force, drive force, net acceleration, braking, corner speed limits and a top-speed bound. |
| `racelab/simulation.py` | `simulate_lap(car, track, racing_line=...)` → `LapResult`. |
| `racelab/analysis.py` | `compare_cars` → `ComparisonEntry` list; `sensitivity_analysis` → a `SensitivityResult` per parameter. |

## Equations (SI units)

| Quantity | Formula |
|---|---|
| Drag | `F_drag = 0.5 · ρ · Cd · A · v²`, with ρ = 1.225 kg/m³ |
| Downforce | `F_down = 0.5 · ρ · C_L·A · v²`; tyre load `N = m·g + F_down` |
| Friction circle | share left for braking/accelerating `c = √(1 − (m·v²·|κ| / (μ_eff·N))²)` |
| Traction, rear drive | `F ≤ μ_eff · N · f_rear / (1 − μ_eff · h / L)` (load moves onto the rear under power); all-wheel `μ_eff · N` |
| Engine with gears | per gear: `rpm = v / r_wheel · ratio · 60/2π`; `P(rpm) = P_max · x(2 − x)`, `x = rpm / rpm_peak`; `F = P/ω_engine · ratio · η / r_wheel`; best gear below redline, clutch slip below launch rpm |
| Engine, no gearbox | `P · η / max(v, 0.5 m/s)` |
| Drive force | `F_drive = min(F_max, engine, traction · c)` |
| Net acceleration | `a = (F_drive − F_drag) / m` |
| Braking | `a_brake = min(a_configured, μ_eff · N / m · c)` |
| Cornering speed | `m·v²·κ = μ_eff · (m·g + 0.5ρ·C_L·A·v²)` → `v_max = √(μ_eff·m·g / (m·κ − μ_eff·0.5ρ·C_L·A))`; without downforce `√(μ_eff · g · r)`, g = 9.81 m/s² |
| Effective grip | `μ_eff = tire_friction × surface grip_multiplier` |
| Speed step | `v_next² = v² + 2 · a · ds` |
| Step time | `dt = 2 · ds / (v_i + v_{i+1})`, with ds the distance driven on the line |
| Racing line | minimise `Σ w_i·|p_{i−1} − 2p_i + p_{i+1}|² + ε·Σ n_i²` with `p_i = c_i + n_i·normal_i`, `|n_i| ≤ width/2 − 1.5 m` |

**Low-speed safeguard.** `P/v` diverges as `v → 0`, so below 0.5 m/s the power limit is evaluated at 0.5 m/s. The force is also capped by `F_max` and the friction limit, so it is always finite and there is never a division by zero.

## Simulation algorithm

1. The loop is split into `n = ceil(L / step_m)` equal centerline steps. On the centerline each point covers ±ds/2 and takes the highest curvature and lowest grip of every segment that window touches, so short corners are never skipped at coarse resolution. With a racing line, each point takes the line's curvature and step length instead.
2. Every point starts at `min(corner limit, top-speed bound)`; the corner limit includes downforce.
3. Forward (acceleration) and backward (braking) passes repeat, with indices wrapping across the start/finish line, until a full sweep changes no speed by more than `tolerance_mps`. Both limits use the friction circle at that point's curvature. Braking capacity falls as speed rises (more lateral demand), so each backward step is solved exactly by bisection. Speeds only decrease and are bounded below, so the passes converge, usually in 2–25 iterations (up to about 110 near the limit in long fast corners). This is how braking begins before corners, including corners just after the finish line.
4. The final profile is checked against the corner, drive and braking limits (`constraints_satisfied`).
5. Lap time sums `dt`. A zero or non-finite speed raises `ArithmeticError` instead of being patched over.

`LapResult` fields: `lap_time_s`, `total_distance_m`, `step_m`, `distance_m`, `speed_mps`, `acceleration_mps2` (from point i to i+1), `corner_speed_limit_mps` (`inf` on straights), `max_speed_mps`, `average_speed_mps`, `converged`, `iterations`, `constraints_satisfied`, `step_length_m`, `curvature_per_m`, `lateral_offset_m`, `step_grip`, `path_length_m`.

## Sensitivity analysis

Parameters: `mass`, `power`, `drag_coefficient`, `frontal_area`, `grip` (tire friction) and `braking`. Each one is scaled by `scales` (default 0.8–1.2), and the 1.0 baseline is always included. A scale that gives an invalid car (for example tire friction above 3.0) is reported with `valid=False`, `lap_times_s=nan` and the validation message in `errors`. It is never silently dropped.

## Assumptions and limitations

- The car is a point mass on its path: no suspension, tyre load sensitivity, slip angles or tyre temperature. Load transfer is longitudinal only and only affects driven-axle traction; braking assumes ideal brake balance.
- Downforce has no aero balance, ride-height or yaw effects; it adds to total tyre load.
- The gearbox shifts instantly; the power curve is a single parabola peaking at 7,000 rpm.
- The racing line minimises curvature, not lap time; the car drives a geometric line, not an optimised one.
- No rolling resistance, gradient or wind. Drag is ignored under braking and in the load-transfer term.
- Flying lap: the car crosses the start line at the speed it carries from the previous lap.
- Explicit Euler in `v²`. Lap times converge as the step shrinks: within 0.5% of the 0.5 m result at 1 m, 1% at the app's 2 m, and 2% at 5 m (tested).
- Track geometry is lines and constant-radius arcs, with no transition curves and no elevation. All bundled circuits close to within 0.1 m and are checked by tests.
