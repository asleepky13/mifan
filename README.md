# RaceLab — Phase 1: Physics Engine

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

**Circuits and weather.** The sidebar picks Monza, Monaco, Spa or Bahrain and a weather preset. Weather sets how much standing water there is, and the tyres decide how much grip that costs (see *Tyres*). The track view darkens the asphalt and draws rain.

**Environments.** Each circuit has its own surroundings in the track view, set by `Track.environment`:
- Monza (parkland): mown grass and tree clusters.
- Spa (forest): dense, dark Ardennes woodland.
- Monaco (harbour): city blocks squared to the streets, and the sea beside the circuit along the tunnel, chicane, Tabac and the pool. The sea has a stone quay, a marina with piers and yachts moored stern-to, a breakwater, and big yachts at anchor. The swimming pool sits on the quay, and the hotel roof covers the tunnel (see-through in Follow mode). There are escape roads only at slow corners. The Monaco layout has 19 corners, from Sainte Devote to Anthony Noghes, and its seafront stretch is `Track.seafront_m`.
- Bahrain (desert): sand, sparse palms and tarmac run-off instead of gravel.

**Racing line.** The car drives a minimum-curvature line across the track width: wide on corner entry, inside at the apex, back towards the middle on long straights. `build_racing_line` minimises the summed squared second difference of the path, with each point kept 1.5 m inside the track edges, and solves it as a bounded quadratic programme with an active set. The lap is simulated on that line. Each point's corner limit is `√(μ g / |κ|)` from the line's own curvature, and each step is the distance driven along the line. The physics are the same point mass as before.

**Tyres.** The sidebar's *Tyres* picker switches between Pirelli's F1 range in its sidewall colours:
- Soft (red);
- Medium (yellow, the default);
- Hard (white);
- Intermediate (green);
- Wet (blue).

A caption under the picker gives the tyre's grip in the current weather, and suggests a better tyre when the conditions call for one. The wheels in the track view carry the tyre's colour, and so does the HUD's durability bar.

Pirelli does not publish grip or wear coefficients, so each tyre is fitted to the figures that are published. Every number below is reproduced by a test (`PirelliCalibrationTest`). Pace and the wet crossovers use the mean lap-time ratio over the four circuits with the default car on the racing line.

| Target | Source | Result in RaceLab |
|---|---|---|
| About 0.8–1 s a lap between compounds on a ~90 s lap | Mario Isola (Pirelli), 2025 Bahrain test | Soft −1%, Hard +1% lap time against Medium (dry grip ×1.050 / ×0.953) |
| Slicks give way to Intermediates at 110–112% of the dry lap time | Pirelli, "When it's time to change from slick to wet tyres" | Water level 1 = slicks at 111%, where Intermediates match them |
| Intermediates give way to Wets at about 118% of the dry lap time | Mario Isola (Pirelli) | Wets match Intermediates when Intermediates lap at 118% |
| Intermediates on a dry track cost 5–6 s a lap | Pirelli | Intermediates 6% slower when dry (grip ×0.780) |
| Full wets are 6–7 s a lap slower than Intermediates | F1 press coverage | Wets 7% slower than Intermediates when dry (grip ×0.636) |
| Monza 2025 pit windows (53 laps): Medium first stint to laps 22–28, Hard first stint to 28–34, Soft final stint from 32–38 | Pirelli's 2025 Italian GP strategy preview | Window midpoints, Soft 18 / Medium 25 / Hard 31 laps per set at Monza |

The weather presets sit around those crossovers:

| Preset | Water | Slick grip | Tyre with the most grip |
|---|---|---|---|
| Damp | 0.5 | 84% | slicks |
| Wet | 1.5 | 51% | Intermediates |
| Heavy rain | 2.5 | 18% | Wets |

Limitations:
- No wear figures exist for the wet tyres, so they use the Medium's wear rate.
- The RaceLab car is not an F1 car. The figures set the tyres' relative pace and life; absolute lap times are the RaceLab car's.
- There is no tyre temperature, no drying line and no fuel load.

**Tyre durability.** New tyres start at 100% durability. Each lap uses some up, and grip falls with it. At 20% the car stops on the start/finish line for 2 s while the crew changes the tyres, then starts again on a new set of the same tyres. The track view plays a whole set on a loop:
- a standing start;
- flying laps that get slower as grip goes;
- an in-lap that brakes to a stop at the line;
- the tyre change.

The stats band shows how many laps a set lasts. The model (`racelab/tires.py`):
- Grip = `μ_car × tyre dry grip × (1 − tyre water loss × water) × (1 − 0.15 × (1 − durability))`. Each lap is simulated with the grip at its start.
- Tyre work per lap = `Σ (|a_long| + v²·|κ|) · ds / g`, in g·km, along the path driven. Durability used per lap = the tyre's wear rate × tyre work, so tight circuits and fast cars use tyres up faster.
- Wear is counted on the flying version of each lap. The standing start and the stop only change the speed profile.

**Telemetry.** Stacked charts by distance: vehicle speed, throttle, brake, steering and delta time against the baseline (default setup), each comparing the current setup (blue) with the baseline (orange). A crosshair follows the pointer across every chart and the speed-coloured track map, with both laps' values at the cursor; the arrow keys move it too. A lap summary table lists the headline numbers for both laps. How the channels are derived:
- Throttle is the drive force the lap needs (mass × acceleration + drag) as a share of what the engine and tyres can deliver at that speed.
- Brake is the braking force needed as a share of the braking limit.
- Steering is the kinematic road-wheel angle, `atan(wheelbase × curvature)`, so it steps at corner entry.
- There is no gear chart: the engine has no gearbox.

**Garage.** Pick a body (Standard Kart, Comet Coupe, Bulldog Truck, Feather Frame), wheels (Standard, Slicks, Monster, Rollers) and an engine (Standard, Turbo, Electric, Lightweight). Each part's effect is listed under its picker. Parts feed the engine, so lap time, top speed, cornering and the car's motion on track all change; the track view draws the chosen parts. Reset to default also resets the parts.

**On track (V2).** A top-down view of the circuit with asphalt, curbs and the chequered start/finish line. Around it: gravel traps outside slow corners, tarmac run-off outside fast ones, tyre walls, guardrails, trees, a grandstand and pit garages, all placed from the track geometry. The car moves at the simulated speed. The view has Start, Pause and Reset controls, a sim-speed selector (0.25×–8×), an Overview or Follow-car camera, and a readout of speed, lap, lap time, last lap and status. The body colour comes from the sidebar picker.

How it fits together:
- `racelab/geometry.py` builds the centerline from the segment list, and the racing line from the centerline.
- `racelab/playback.py` puts the simulated speed profile on the racing line, giving the car's position, heading and time.
- `ui/track_view.py` packs that into JSON for `ui/track_view.html`. That page is a plain `<canvas>` with no libraries. It only interpolates between precomputed states and draws them.

The view runs inside the existing Streamlit app instead of a separate Pygame window. Animation happens in the browser, so it is smooth with no Streamlit reruns and no extra dependency. The cost is that changing a slider reloads the view and resets playback.

**V2 limitations:**
- The car is a point mass on the racing line: no slip, yaw or overtaking lines. Every lap of a set drives the same line.
- In the overview the car is drawn larger than scale so it stays visible. In Follow mode it is true to scale.
- Weather only changes grip: no aquaplaning, drying line, wet-weather tyres or temperature effects.

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
| `racelab/track.py` | `Segment` (`radius_m=None` is a straight; `direction` +1 is a left corner, −1 a right corner), `Track` (a closed loop with `width_m`; `in_weather(w)` scales every segment's grip). Circuits in `CIRCUITS`: `MONZA` (5.79 km), `MONACO` (3.34 km), `SPA` (7.00 km) and `BAHRAIN` (5.41 km), simplified layouts inspired by the real F1 tracks, with their real corner order, turn directions and lap length; exact shapes and elevation are not reproduced. Each track has an `environment` (one of `ENVIRONMENTS`: parkland, harbour, forest, desert) that the track view uses for scenery. `TECHNICAL_CIRCUIT` (Monaco) and `HIGH_SPEED_CIRCUIT` (Monza) remain as aliases. `WEATHER`: Dry, Damp, Wet and Heavy rain, with water levels 0, 0.5, 1.5 and 2.5. `grip_multiplier` is the grip left on slicks (100%, 84%, 51%, 18%). |
| `racelab/geometry.py` | `build_geometry` → `TrackGeometry` (centerline x/y, heading, signed curvature, `pose_at`, `offset`, closure error); `build_racing_line` → `RacingLine` (lateral offset, x/y, path curvature, step lengths); `Camera` (fit-to-view and chase camera, world to screen and back). |
| `racelab/playback.py` | `LapPlayback.from_lap(lap, geometry)`; `state_at(t)` → `VehicleState` (lap, lap time, distance, x, y, heading, speed). |
| `racelab/config.py` | Future-facing configuration: `TireCompound`, `AeroPackage`, `BodyPackage`, `VehicleConfig.to_car()`. Fields listed in `NOT_MODELED` (tire temperature and wear, downforce) are stored but have **no effect** yet. Tyre wear is modelled separately in `racelab/tires.py`. |
| `racelab/parts.py` | Kart-style `PARTS` in three categories (body, wheels, engine). `apply_parts(car, parts)` adds mass and scales power, drag, frontal area, grip, braking and traction, so each part changes the simulated lap. The values are game-style balance, not measured data. |
| `racelab/tires.py` | `Tyre` (name, sidewall colour, dry grip, water grip loss, wear rate; `grip(weather)`), `TYRES` (`SOFT`, `MEDIUM`, `HARD`, `INTERMEDIATE`, `WET`), `grip_factor(durability)`, `tyre_work_g_km(lap)`, `tyre_stint(car, track, tyre, weather, racing_line=...)` → `TyreStint` (per-lap `StintLap`s with durability and the driven `LapResult`, `change_s`, `cycle_time_s`). |
| `racelab/telemetry.py` | `build_telemetry(lap, car, track, geometry)` → `Telemetry`: speed, throttle %, brake %, kinematic steering angle, time and position per sample, derived from the lap; `lap_summary` → lap time, speeds, full-throttle and braking share, max steering. |
| `ui/telemetry_view.py`, `ui/telemetry.html` | The telemetry dashboard. Rendering only, no physics. |
| `ui/track_view.py`, `ui/track_view.html` | Renders the canvas view. Rendering only, no physics. |
| `racelab/physics.py` | Drag, drive force, net acceleration, braking, cornering speed and a top-speed bound. |
| `racelab/simulation.py` | `simulate_lap(car, track, racing_line=None, standing_start=False, stop_at_finish=False)` → `LapResult`. |
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

`LapResult` fields: `lap_time_s`, `total_distance_m`, `step_m`, `distance_m`, `speed_mps`, `acceleration_mps2` (from point i to i+1), `corner_speed_limit_mps` (`inf` on straights), `max_speed_mps`, `average_speed_mps`, `converged`, `iterations`, `constraints_satisfied`, `step_length_m` and `curvature_per_m` (of the path driven), `lateral_offset_m` (zero on the centerline), `finish_speed_mps`.

## Sensitivity analysis

Parameters: `mass`, `power`, `drag_coefficient`, `frontal_area`, `grip` (tire friction) and `braking`. Each one is scaled by `scales` (default 0.8–1.2), and the 1.0 baseline is always included. A scale that gives an invalid car (for example tire friction above 3.0) is reported with `valid=False`, `lap_times_s=nan` and the validation message in `errors`. It is never silently dropped.

## Assumptions and limitations

- The car is a point mass: no weight transfer, suspension, tire load sensitivity, slip angles or tire temperature. Tyre wear is modelled in `racelab/tires.py`, with grip held constant within each lap.
- No aerodynamic downforce, so grip does not increase with speed.
- The engine is a flat power curve with a fixed tractive-force cap: no gears, torque curve, shift time or rev limit.
- No friction circle: full cornering grip is never combined with full braking or acceleration. Corners are driven at their limit speed.
- No rolling resistance, gradient or wind. Drag is ignored under braking, which makes braking distances slightly conservative.
- Flying lap by default: the car crosses the start line at the speed it carries from the previous lap. A standing start is one forward pass from 0, and a stop at the line is one backward pass to 0.
- Explicit Euler in `v²`. Lap times change by less than 1% between 0.5 m and 5 m steps on the bundled circuits.
- Track geometry is lines and constant-radius arcs, with no transition curves and no elevation. All bundled circuits close to within 0.1 m and are checked by tests.
