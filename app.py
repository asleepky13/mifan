"""RaceLab V2 — local web UI. Run with: streamlit run app.py"""

from __future__ import annotations

import streamlit as st

from racelab import CIRCUITS, WEATHER, simulate_lap
from racelab.config import BodyPackage
from racelab.geometry import build_geometry, build_racing_line
from racelab.parts import CATEGORIES, DEFAULT_PARTS, PARTS_BY_CATEGORY, apply_parts
from racelab.telemetry import build_telemetry
from racelab.tires import CHANGE_AT_DURABILITY, GRIP_LOSS_WHEN_WORN, TYRE_CHANGE_S, tyre_stint
from racelab.summary import (
    DRIVETRAIN_EFFICIENCY,
    MAX_TRACTIVE_FORCE_N,
    car_from_setup,
    corner_average_speed_mps,
    time_to_speed,
)
from ui.telemetry_view import telemetry_html
from ui.track_view import track_view_html

# key: (label, unit, min, max, default, step, format)
SLIDERS = {
    "mass_kg": ("Mass", "kg", 800, 1800, 1200, 10, "%d"),
    "power_hp": ("Engine power", "hp", 100, 1000, 400, 10, "%d"),
    "drag_coefficient": ("Drag coefficient Cd", "", 0.20, 0.60, 0.32, 0.01, "%.2f"),
    "frontal_area_m2": ("Frontal area", "m²", 1.5, 3.5, 2.2, 0.05, "%.2f"),
    "tire_friction": ("Tire grip μ", "", 0.8, 2.0, 1.2, 0.05, "%.2f"),
    "max_braking_decel_mps2": ("Max braking", "m/s²", 5.0, 15.0, 10.0, 0.5, "%.1f"),
}
DEFAULTS = {key: spec[4] for key, spec in SLIDERS.items()}
PART_DEFAULTS = {f"part_{c}": DEFAULT_PARTS[c] for c in CATEGORIES}
TRACKS = {t.name: t for t in CIRCUITS}
WEATHERS = {w.name: w for w in WEATHER}
KMH = 3.6

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400&family=Source+Serif+4:wght@400;600&family=JetBrains+Mono:wght@400;500&display=swap');
:root { --fg:#000; --bg:#fff; --muted:#F5F5F5; --muted-fg:#525252; --line:#E5E5E5;
        --display:'Playfair Display',Georgia,serif; --body:'Source Serif 4',Georgia,serif; --mono:'JetBrains Mono',monospace; }
* { border-radius:0 !important; box-shadow:none !important; }
[data-testid="stAppViewContainer"] { background-color:var(--bg);
  background-image:repeating-linear-gradient(0deg, transparent 0 1px, rgba(0,0,0,.015) 1px 2px); background-size:100% 4px; }
[data-testid="stHeader"] { background:transparent; }
[data-testid="stSidebar"] { background:var(--muted); border-right:1px solid var(--fg); }
[data-testid="stSidebar"] label p { font-family:var(--mono); font-size:.78rem; letter-spacing:.05em; }
.block-container { max-width:72rem; }
.stButton button { width:100%; background:var(--fg); color:var(--bg); border:2px solid var(--fg); font-family:var(--mono);
  text-transform:uppercase; letter-spacing:.1em; font-size:.8rem; padding:.9rem 1rem; transition:none; }
.stButton button:hover, .stButton button:active { background:var(--bg); color:var(--fg); border-color:var(--fg); }
.stButton button:focus-visible { outline:3px solid var(--fg); outline-offset:3px; }
.rl-kicker { font-family:var(--mono); font-size:.75rem; letter-spacing:.1em; text-transform:uppercase; color:var(--muted-fg); }
h1.rl-hero { font-family:var(--display) !important; font-weight:900 !important; font-size:clamp(3.5rem, 12vw, 9rem) !important;
  line-height:.9 !important; letter-spacing:-.05em; margin:.5rem 0 0 !important; padding:0 !important; }
.rl-hero em { font-weight:400; }
.rl-rule { display:flex; align-items:center; gap:1rem; margin:1.5rem 0 2rem; }
.rl-rule::before { content:""; flex:1; border-top:4px solid var(--fg); }
.rl-rule span { width:14px; height:14px; border:2px solid var(--fg); }
h2.rl-h2 { font-family:var(--display) !important; font-size:2.5rem !important; letter-spacing:-.025em; line-height:1 !important;
  border-top:4px solid var(--fg); margin:3rem 0 1rem !important; padding:1.25rem 0 0 !important; }
.rl-stats { display:grid; grid-template-columns:repeat(auto-fit, minmax(10.5rem, 1fr)); background:var(--fg); color:var(--bg);
  background-image:repeating-linear-gradient(90deg, transparent 0 1px, rgba(255,255,255,.03) 1px 2px); background-size:4px 100%; }
.rl-stat { padding:1.5rem 1.25rem; border-right:1px solid #333; border-bottom:1px solid #333; }
.rl-stat .rl-kicker { color:#BDBDBD; }
.rl-value { font-family:var(--display); font-size:2.75rem; line-height:1; margin:.75rem 0 .5rem; letter-spacing:-.025em; }
.rl-unit { font-family:var(--mono); font-size:.8rem; margin-left:.35rem; letter-spacing:.05em; }
.rl-base { font-family:var(--mono); font-size:.72rem; color:#BDBDBD; }
.rl-table { width:100%; border-collapse:collapse; font-family:var(--body); }
.rl-table th { font-family:var(--mono); font-size:.72rem; letter-spacing:.1em; text-transform:uppercase; text-align:left;
  border-bottom:2px solid var(--fg); padding:.6rem .5rem; }
.rl-table td { border-bottom:1px solid var(--line); padding:.6rem .5rem; font-size:1.05rem; }
.rl-table td.num { font-family:var(--mono); font-size:.9rem; }
.rl-changed { background:var(--fg); color:var(--bg); padding:.1rem .4rem; }
.rl-note { font-family:var(--body); font-style:italic; color:var(--muted-fg); font-size:.95rem; margin-top:1rem; }
.rl-notice { border:4px solid var(--fg); padding:1rem 1.25rem; font-family:var(--body); margin:1rem 0; }
</style>
"""


@st.cache_data(max_entries=256, show_spinner=False)
def run(setup: tuple[tuple[str, float], ...], parts: tuple[str, ...], track_name: str, weather_name: str):
    """The car, its flying lap on new tyres along the racing line, and its run on one set of tyres."""
    car = apply_parts(car_from_setup(**dict(setup)), [PARTS_BY_CATEGORY[c][k] for c, k in zip(CATEGORIES, parts)])
    track = TRACKS[track_name].in_weather(WEATHERS[weather_name])
    lap = simulate_lap(car, track, step_m=2.0, racing_line=racing_line(track_name))
    stint = tyre_stint(car, track, step_m=2.0, racing_line=racing_line(track_name))
    return car, lap, time_to_speed(car), corner_average_speed_mps(lap), stint


@st.cache_data(show_spinner=False)
def geometry(track_name: str):
    return build_geometry(TRACKS[track_name], step_m=2.0)


@st.cache_data(show_spinner=False)
def racing_line(track_name: str):
    return build_racing_line(geometry(track_name))


def notice(text: str) -> None:
    st.markdown(f'<div class="rl-notice">{text}</div>', unsafe_allow_html=True)


def fmt(value: float | None, digits: int) -> str:
    return "—" if value is None else f"{value:,.{digits}f}"


def stat(label: str, unit: str, current: float | None, baseline: float | None, digits: int) -> str:
    delta = "" if current is None or baseline is None else f" · Δ {current - baseline:+,.{digits}f}"
    return (
        f'<div class="rl-stat"><div class="rl-kicker">{label}</div>'
        f'<div class="rl-value">{fmt(current, digits)}<span class="rl-unit">{unit}</span></div>'
        f'<div class="rl-base">Baseline {fmt(baseline, digits)} {unit}{delta}</div></div>'
    )


def reset() -> None:
    st.session_state.update(DEFAULTS)
    st.session_state.update(PART_DEFAULTS)


st.set_page_config(page_title="RaceLab", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
for key, value in {**DEFAULTS, **PART_DEFAULTS}.items():
    st.session_state.setdefault(key, value)

with st.sidebar:
    st.markdown('<div class="rl-kicker">Car setup</div>', unsafe_allow_html=True)
    track_name = st.selectbox("Circuit", list(TRACKS))
    weather_name = st.selectbox("Weather", list(WEATHERS))
    st.markdown('<div class="rl-kicker">Garage</div>', unsafe_allow_html=True)
    for category in CATEGORIES:
        options = PARTS_BY_CATEGORY[category]
        chosen = st.selectbox(category.title(), list(options), format_func=lambda k, o=options: o[k].name, key=f"part_{category}")
        st.caption(options[chosen].describe())
    st.markdown('<div class="rl-kicker">Tuning</div>', unsafe_allow_html=True)
    for key, (label, unit, lo, hi, _, step, number_format) in SLIDERS.items():
        st.slider(f"{label} ({unit})" if unit else label, lo, hi, step=step, format=number_format, key=key)
    st.button("Reset to default →", on_click=reset)
    body_color = st.color_picker("Body color", BodyPackage().color_hex)

setup = {key: st.session_state[key] for key in SLIDERS}
parts = tuple(st.session_state[f"part_{c}"] for c in CATEGORIES)
try:
    car, lap, zero_to_100, corner, stint = run(tuple(setup.items()), parts, track_name, weather_name)
    base_car, base_lap, base_zero_to_100, base_corner, base_stint = run(
        tuple(DEFAULTS.items()), tuple(DEFAULT_PARTS.values()), track_name, weather_name)
except (ValueError, ArithmeticError) as exc:
    notice(f"<strong>Simulation failed for this setup.</strong> {exc}")
    st.stop()

st.markdown(
    f'<div class="rl-kicker">RaceLab V2 · {track_name} · {lap.total_distance_m / 1000:.2f} km · {weather_name}</div>'
    '<h1 class="rl-hero">Race<em>Lab</em></h1><div class="rl-rule"><span></span></div>',
    unsafe_allow_html=True,
)
if not (lap.converged and lap.constraints_satisfied):
    notice("The speed profile did not fully converge or breaks a limit; treat these numbers with caution.")

st.markdown(
    '<div class="rl-stats">'
    + stat("Lap time", "s", lap.lap_time_s, base_lap.lap_time_s, 2)
    + stat("Top speed", "km/h", lap.max_speed_mps * KMH, base_lap.max_speed_mps * KMH, 0)
    + stat("Average speed", "km/h", lap.average_speed_mps * KMH, base_lap.average_speed_mps * KMH, 1)
    + stat("Cornering · avg corner speed", "km/h", corner and corner * KMH, base_corner and base_corner * KMH, 1)
    + stat("Acceleration · 0–100 km/h", "s", zero_to_100, base_zero_to_100, 2)
    + stat("Tyre life · laps per set", "laps", len(stint.laps), len(base_stint.laps), 0)
    + "</div>",
    unsafe_allow_html=True,
)

st.markdown('<h2 class="rl-h2">On track</h2>', unsafe_allow_html=True)
track_geometry = geometry(track_name)
# Trusted HTML: built here from engine output, no user-supplied markup.
car_look = {**dict(zip(CATEGORIES, parts)), "color": BodyPackage(color_hex=body_color).color_hex}
st.iframe(
    track_view_html(
        track_geometry, stint, car_look, WEATHERS[weather_name],
        first_straight_m=TRACKS[track_name].segments[0].length_m, environment=TRACKS[track_name].environment,
    ),
    height=860,
)
st.markdown(
    "<p class='rl-note'>Circuits are simplified layouts inspired by the real tracks: corner order and lap length "
    "follow the originals, exact shapes do not. Weather scales track grip (Dry 100%, Damp 85%, Wet 70%, Heavy rain 55%); "
    "these factors are illustrative. The car drives a minimum-curvature racing line: wide on corner entry, inside at the "
    "apex, back to the middle on long straights. It is a point mass on that line, so there is no slip or yaw. "
    f"Tyres lose durability with every lap, and grip with it (up to {GRIP_LOSS_WHEN_WORN:.0%} on a worn set). At "
    f"{CHANGE_AT_DURABILITY:.0%} durability the car stops at the line for {TYRE_CHANGE_S:.0f} s to change tyres, then "
    "starts again on a new set. Wear rates are illustrative, not calibrated. In the overview the car is drawn "
    "larger than scale so it stays visible. Garage parts change mass, power, drag, grip, braking and traction "
    "(effects listed under each part), so they change the lap; their values are game-style balance, not measured data.</p>",
    unsafe_allow_html=True,
)

st.markdown('<h2 class="rl-h2">Telemetry</h2>', unsafe_allow_html=True)
track_in_weather = TRACKS[track_name].in_weather(WEATHERS[weather_name])
st.iframe(
    telemetry_html(
        build_telemetry(lap, car, track_in_weather, track_geometry),
        build_telemetry(base_lap, base_car, track_in_weather, track_geometry),
    ),
    height="content",
)
st.markdown(
    "<p class='rl-note'>Throttle and brake are the drive and braking force the simulated lap needs, as a share of what "
    "the car can deliver at that speed and grip. Steering is the kinematic road-wheel angle for the track curvature "
    "(2.6 m wheelbase). There is no gear channel: the engine has no gearbox. Delta below zero means the current setup is ahead.</p>",
    unsafe_allow_html=True,
)

st.markdown('<h2 class="rl-h2">Setup</h2>', unsafe_allow_html=True)
rows = "".join(
    f"<tr><td>{label}</td><td class='num'><span class='{'rl-changed' if setup[key] != DEFAULTS[key] else ''}'>"
    f"{number_format % setup[key]}</span></td><td class='num'>{number_format % DEFAULTS[key]}</td><td class='num'>{unit}</td></tr>"
    for key, (label, unit, _, _, _, _, number_format) in SLIDERS.items()
) + "".join(
    f"<tr><td>{c.title()}</td><td class='num'><span class='{'rl-changed' if k != DEFAULT_PARTS[c] else ''}'>"
    f"{PARTS_BY_CATEGORY[c][k].name}</span></td><td class='num'>{PARTS_BY_CATEGORY[c][DEFAULT_PARTS[c]].name}</td><td class='num'></td></tr>"
    for c, k in zip(CATEGORIES, parts)
)
st.markdown(
    f"<table class='rl-table'><tr><th>Parameter</th><th>Current</th><th>Default</th><th>Unit</th></tr>{rows}</table>"
    f"<p class='rl-note'>Highlighted values differ from the default. Fixed for every setup: drivetrain efficiency "
    f"{DRIVETRAIN_EFFICIENCY:.0%}, maximum tractive force {MAX_TRACTIVE_FORCE_N:,.0f} N. Results come from the RaceLab "
    f"point-mass engine: no downforce, gears, weight transfer or combined braking-and-cornering grip.</p>",
    unsafe_allow_html=True,
)
