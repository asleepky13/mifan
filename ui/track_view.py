"""Builds the self-contained HTML canvas view of a run on one set of tyres.
Rendering only: all positions come from ``racelab.geometry`` and ``racelab.playback``."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from racelab.geometry import Camera, TrackGeometry
from racelab.playback import LapPlayback
from racelab.tires import TyreStint
from racelab.track import ENVIRONMENTS, WEATHER, Weather

VIEW_W, VIEW_H = 1000, 640
CURB_WIDTH_M = 1.2
RUNOFF_WIDTH_M = 14.0
GRAVEL_BELOW_RADIUS_M = 150.0  # slower corners get gravel, faster ones tarmac run-off
ARMCO_OFFSET_M = 5.0  # guardrail distance beyond the track edge where there is no run-off
TREE_CLEARANCE_M = 6.0  # beyond the outermost barrier
SCENERY_PAD_M = 220.0
FOLLOW_SCALE_PX_PER_M = 16.0
# Tree clusters per km², trees per cluster, cluster spread (m) and crown radius (m) for each environment.
TREES = {
    "parkland": (25, (4, 15), 22, (3, 7)),
    "forest": (80, (10, 28), 30, (4, 8)),
    "harbour": (12, (2, 6), 10, (2.5, 4)),
    "desert": (10, (1, 4), 14, (2.5, 3.5)),  # palms
}
# Harbour (Monaco): the sea lies outside the seafront stretch, this far from the centerline.
QUAY_M = 30.0
POOL_QUAY_M = 70.0  # a wider quay where the swimming pool sits
# Landmarks, as fractions along the seafront stretch (laid out for Monaco's).
TUNNEL_SPAN = (0.10, 0.36)
HARBOUR_FROM = 0.55
POOL_SPAN = (0.80, 0.89)
_TEMPLATE = Path(__file__).with_name("track_view.html")


def _xy(x: np.ndarray, y: np.ndarray) -> dict:
    return {"x": np.round(x, 2).tolist(), "y": np.round(y, 2).tolist()}


def _corner_runs(geometry: TrackGeometry) -> list[np.ndarray]:
    in_corner = geometry.curvature_per_m != 0
    edges = np.flatnonzero(np.diff(np.concatenate(([False], in_corner, [False])).astype(int)))
    return [np.arange(a, b + 1) % len(in_corner) for a, b in zip(edges[::2], edges[1::2])]


def distance_to_track(geometry: TrackGeometry, x: np.ndarray, y: np.ndarray, skip: slice = slice(0, 0)) -> np.ndarray:
    """Distance from each point to the nearest centerline sample (samples in ``skip`` ignored)."""
    keep = np.ones(len(geometry.x_m), bool)
    keep[skip] = False
    cx, cy = geometry.x_m[keep], geometry.y_m[keep]
    return np.array([np.min(np.hypot(cx - px, cy - py)) for px, py in zip(x, y)])


def _nearest_sample(geometry: TrackGeometry, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.array([np.argmin(np.hypot(geometry.x_m - px, geometry.y_m - py)) for px, py in zip(x, y)], int)


def inside_polygon(px: np.ndarray, py: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """True for points (x, y) inside the closed polygon (px, py), by even-odd ray casting."""
    ax, ay = np.asarray(px, float)[None], np.asarray(py, float)[None]
    bx, by = np.roll(ax, -1, axis=1), np.roll(ay, -1, axis=1)
    qx, qy = np.asarray(x, float)[:, None], np.asarray(y, float)[:, None]
    with np.errstate(divide="ignore", invalid="ignore"):
        crosses = ((ay > qy) != (by > qy)) & (qx < ax + (bx - ax) * (qy - ay) / (by - ay))
    return crosses.sum(axis=1) % 2 == 1


def inside_loop(geometry: TrackGeometry, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """True for points enclosed by the centerline."""
    return inside_polygon(geometry.x_m, geometry.y_m, x, y)


def _runoff(geometry: TrackGeometry, gravel_traps: bool = True, street: bool = False) -> tuple[list[dict], list[dict]]:
    """Run-off areas outside corners, and guardrail runs along every stretch without run-off.

    On a street circuit only slow corners get a (tarmac) escape road; elsewhere the barriers are the walls.
    """
    half, n = geometry.width_m / 2, len(geometry.x_m)
    covered = {1: np.zeros(n, bool), -1: np.zeros(n, bool)}
    out = []
    for run in _corner_runs(geometry):
        k = geometry.curvature_per_m[run]
        k = k[k != 0]  # runs include the first point after the corner
        slow = bool(np.abs(k).max() > 1 / GRAVEL_BELOW_RADIUS_M)
        if street and not slow:
            continue
        span = np.arange(run[0] - 3, run[-1] + 16) % n  # cars run wide on exit
        for side in sorted(set((-np.sign(k)).astype(int).tolist())):  # outside of the turn; chicanes get both
            mid = geometry.offset(side * (half + CURB_WIDTH_M + RUNOFF_WIDTH_M / 2))
            wall = geometry.offset(side * (half + CURB_WIDTH_M + RUNOFF_WIDTH_M + 0.6))
            out.append({
                "gravel": gravel_traps and slow,
                "mid": _xy(mid[0][span], mid[1][span]),
                "wall": _xy(wall[0][span], wall[1][span]),
            })
            covered[side][span] = True
    armco = []
    for side, mask in covered.items():
        x, y = geometry.offset(side * (half + ARMCO_OFFSET_M))
        free = ~mask
        edges = np.flatnonzero(np.diff(np.concatenate(([False], free, [False])).astype(int)))
        armco += [_xy(x[a:b], y[a:b]) for a, b in zip(edges[::2], edges[1::2]) if b - a > 1]
    return out, armco


def _buildings(geometry: TrackGeometry, first_straight_m: float) -> list[dict]:
    """Grandstand and pit garages beside the start straight, each on a side that is clear of other track."""
    half = geometry.width_m / 2
    start_idx = slice(0, int(first_straight_m / geometry.step_m) + 1)
    out = []
    for kind, s0, s1, near, far in (("grandstand", 0.12, 0.45, half + 8, half + 26), ("pits", 0.5, 0.9, half + 8, half + 24)):
        a, b = s0 * first_straight_m, s1 * first_straight_m
        xs, ys, h = geometry.pose_at(np.array([a, b, b, a]))
        for side in (1, -1):
            lat = side * np.array([near, near, far, far])
            qx, qy = xs - lat * np.sin(h[0]), ys + lat * np.cos(h[0])
            if distance_to_track(geometry, qx, qy, skip=start_idx).min() > half + 6:
                out.append({"kind": kind, **_xy(qx, qy)})
                break
    return out


def _bbox(geometry: TrackGeometry) -> tuple[np.ndarray, np.ndarray]:
    lo = np.array([geometry.x_m.min(), geometry.y_m.min()]) - SCENERY_PAD_M
    hi = np.array([geometry.x_m.max(), geometry.y_m.max()]) + SCENERY_PAD_M
    return lo, hi


def _trees(geometry: TrackGeometry, seed: int, environment: str = "parkland") -> dict:
    per_km2, per_cluster, spread, radius = TREES[environment]
    rng = np.random.default_rng(seed)
    lo, hi = _bbox(geometry)
    clusters = rng.uniform(lo, hi, size=(int(np.prod(hi - lo) * per_km2 / 1e6) + 10, 2))
    pts = np.concatenate([c + rng.normal(0, spread, size=(rng.integers(*per_cluster), 2)) for c in clusters])
    clearance = geometry.width_m / 2 + CURB_WIDTH_M + RUNOFF_WIDTH_M + TREE_CLEARANCE_M
    pts = pts[distance_to_track(geometry, pts[:, 0], pts[:, 1]) > clearance]
    return {**_xy(pts[:, 0], pts[:, 1]), "r": np.round(rng.uniform(*radius, len(pts)), 1).tolist()}


def _seaward(geometry: TrackGeometry, s: np.ndarray, offset: np.ndarray, window_m: float = 40.0):
    """Points ``offset`` m out to sea from a smoothed centerline at distances ``s``, and the seaward normals.

    The sea is outside the loop: left of a clockwise lap, right of an anticlockwise one.
    Smoothing over +-``window_m`` irons out chicanes, so the coast does not follow every kink.
    """
    k = np.linspace(-window_m, window_m, 9)

    def smooth(at: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        x, y, _ = geometry.pose_at((at[:, None] + k[None]).ravel() % geometry.length_m)
        return x.reshape(len(at), -1).mean(axis=1), y.reshape(len(at), -1).mean(axis=1)

    s = np.asarray(s, float)
    mx, my = smooth(s)
    (ax, ay), (bx, by) = smooth(s - 2.0), smooth(s + 2.0)
    tx, ty = bx - ax, by - ay
    norm = np.hypot(tx, ty)
    side = 1.0 if geometry.total_turn_rad < 0 else -1.0
    nx, ny = -ty / norm * side, tx / norm * side
    return mx + nx * offset, my + ny * offset, nx, ny


def _ray_to_box(x: float, y: float, dx: float, dy: float, lo: np.ndarray, hi: np.ndarray) -> tuple[float, float]:
    t = min((b - p) / d for p, d, lo_, hi_ in ((x, dx, lo[0], hi[0]), (y, dy, lo[1], hi[1])) if d for b in (lo_, hi_) if (b - p) / d > 0)
    return x + t * dx, y + t * dy


def _box_position(x: float, y: float, lo: np.ndarray, hi: np.ndarray) -> float:
    """Where a point on the box edge sits going anticlockwise from the lower-left corner (0-4)."""
    w, h = hi - lo
    edges = (abs(y - lo[1]), abs(x - hi[0]), abs(y - hi[1]), abs(x - lo[0]))
    e = int(np.argmin(edges))
    return e + ((x - lo[0]) / w, (y - lo[1]) / h, (hi[0] - x) / w, (hi[1] - y) / h)[e]


def _sea(geometry: TrackGeometry, seafront_m: tuple[float, float]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Sea polygon (x, y), the quay line along it, and the seafront distances the quay was built at."""
    a, b = seafront_m
    s = np.arange(a, b, 4.0)
    f = (s - a) / (b - a)
    # Smooth cosine ramps (over 4% of the stretch) up to the wide quay at the pool.
    ramp = lambda u: 0.5 - 0.5 * np.cos(np.pi * np.clip(u, 0, 1))
    wide = ramp((f - POOL_SPAN[0] + 0.06) / 0.04) * ramp((POOL_SPAN[1] + 0.06 - f) / 0.04)
    qx, qy, nx, ny = _seaward(geometry, s, QUAY_M + (POOL_QUAY_M - QUAY_M) * wide)
    lo, hi = _bbox(geometry)
    lo, hi = lo - 800, hi + 800  # well past the edge of any view
    start = _ray_to_box(qx[0], qy[0], nx[0], ny[0], lo, hi)
    end = _ray_to_box(qx[-1], qy[-1], nx[-1], ny[-1], lo, hi)
    corners = [(lo[0], lo[1]), (hi[0], lo[1]), (hi[0], hi[1]), (lo[0], hi[1])]
    pe, ps = _box_position(*end, lo, hi), _box_position(*start, lo, hi)
    best = None
    for direction in (1, -1):  # round the box either way from the end of the quay back to its start
        steps = ((ps - pe) * direction) % 4
        between = [c for k, c in enumerate(corners) if 0 < ((k - pe) * direction) % 4 < steps]
        between.sort(key=lambda c: ((corners.index(c) - pe) * direction) % 4)
        px = np.concatenate((qx, [end[0]], [c[0] for c in between], [start[0]]))
        py = np.concatenate((qy, [end[1]], [c[1] for c in between], [start[1]]))
        wet_track = inside_polygon(px, py, geometry.x_m, geometry.y_m).sum()
        if best is None or wet_track < best[0]:
            best = (wet_track, px, py)
    return np.vstack(best[1:]), np.vstack((qx, qy)), s


def _harbour(geometry: TrackGeometry, seed: int, seafront_m: tuple[float, float]) -> dict:
    """Sea, quay, piers with moored yachts, yachts at anchor, the pool, the tunnel roof and city blocks."""
    rng = np.random.default_rng(seed + 1)
    half = geometry.width_m / 2
    sea, quay, s = _sea(geometry, seafront_m)
    a, b = seafront_m
    in_sea = lambda x, y: inside_polygon(sea[0], sea[1], np.atleast_1d(x), np.atleast_1d(y))

    # Parallel piers out of the harbour quay, yachts moored stern-to on both sides.
    harbour = s >= a + HARBOUR_FROM * (b - a)
    hx, hy, nx, ny = _seaward(geometry, s[harbour], np.full(harbour.sum(), QUAY_M))
    d = np.array([nx.mean(), ny.mean()])
    d /= np.hypot(*d)
    perp = np.array([-d[1], d[0]])
    piers, moored = [], []
    for i in range(8, len(hx) - 5, 18):  # every 72 m of quay
        o = np.array([hx[i], hy[i]])
        reach = 0.0
        for t in np.arange(4.0, 124.0, 4.0):
            q = o + d * t
            if not in_sea(*q)[0] or distance_to_track(geometry, [q[0]], [q[1]])[0] < QUAY_M - 4:
                break
            reach = t
        if reach < 30:
            continue
        piers.append(_xy(np.array([o[0], o[0] + d[0] * reach]), np.array([o[1], o[1] + d[1] * reach])))
        for t in np.arange(10.0, reach - 4, 8.5):
            for side in (1, -1):
                length = rng.uniform(12, 28)
                c = o + d * t + perp * side * (2.0 + length / 2)
                if in_sea(*c)[0]:
                    moored.append((c[0], c[1], length, np.arctan2(side * perp[1], side * perp[0])))
    # The harbour wall: a breakwater around the marina, open at the mouth.
    wall_s = s[harbour][(s[harbour] > a + (HARBOUR_FROM + 0.06) * (b - a)) & (s[harbour] < a + 0.97 * (b - a))]
    wx, wy, _, _ = _seaward(geometry, wall_s, np.full(len(wall_s), QUAY_M + 150.0), window_m=120.0)
    breakwater = _xy(wx, wy)
    # Big yachts along the quay before the harbour, then a few at anchor out at sea.
    for i in np.flatnonzero(~harbour)[20::16]:
        qx_, qy_, nx_, ny_ = _seaward(geometry, s[i:i + 1], np.array([QUAY_M + 9.0]))
        length = rng.uniform(32, 52)
        if in_sea(qx_[0], qy_[0])[0]:
            moored.append((qx_[0], qy_[0], length, np.arctan2(nx_[0], -ny_[0])))
    lo, hi = _bbox(geometry)
    far = rng.uniform(lo, hi, size=(400, 2))
    far = far[in_sea(far[:, 0], far[:, 1])]
    coast_d = np.array([np.min(np.hypot(quay[0] - x, quay[1] - y)) for x, y in far])
    wall_d = np.array([np.min(np.hypot(wx - x, wy - y)) for x, y in far])
    for x, y in far[(coast_d > 220) & (wall_d > 40)][:14]:
        moored.append((x, y, rng.uniform(24, 60), rng.uniform(0, np.pi)))
    yachts = np.array(moored) if moored else np.zeros((0, 4))

    # The swimming pool on the wide quay, and the hotel roof over the tunnel.
    p0, p1 = a + POOL_SPAN[0] * (b - a), a + POOL_SPAN[1] * (b - a)
    inner = _seaward(geometry, np.array([p0, p1]), np.full(2, 26.0))
    outer = _seaward(geometry, np.array([p0, p1]), np.full(2, 54.0))
    pool = _xy(np.array([inner[0][0], inner[0][1], outer[0][1], outer[0][0]]),
               np.array([inner[1][0], inner[1][1], outer[1][1], outer[1][0]]))
    t0, t1 = (int((a + f * (b - a)) / geometry.step_m) for f in TUNNEL_SPAN)
    tunnel = _xy(geometry.x_m[t0:t1], geometry.y_m[t0:t1])

    # City blocks squared up to the nearest street, kept clear of the track, the sea, the pool and each other.
    pts = rng.uniform(lo, hi, size=(int(np.prod(hi - lo) / 1_200), 2))
    size = rng.uniform(12, 34, size=(len(pts), 2))
    diag = np.hypot(size[:, 0], size[:, 1])
    dist = distance_to_track(geometry, pts[:, 0], pts[:, 1])
    pool_c = np.array([np.mean(pool["x"]), np.mean(pool["y"])])
    ok = (dist > half + RUNOFF_WIDTH_M + 4 + diag / 2) & ~in_sea(pts[:, 0], pts[:, 1])
    ok &= np.hypot(pts[:, 0] - pool_c[0], pts[:, 1] - pool_c[1]) > 45 + diag / 2
    ok &= distance_to_quay(quay, pts) > diag / 2 + 4
    chosen: list[int] = []
    for i in np.flatnonzero(ok):
        if all(np.hypot(*(pts[i] - pts[j])) > 0.42 * (diag[i] + diag[j]) + 2 for j in chosen):
            chosen.append(i)
    chosen = np.array(chosen, int)
    heading = geometry.heading_rad[_nearest_sample(geometry, pts[chosen, 0], pts[chosen, 1])] if len(chosen) else np.zeros(0)
    blocks = {**_xy(pts[chosen, 0], pts[chosen, 1]), "w": np.round(size[chosen, 0], 1).tolist(),
              "h": np.round(size[chosen, 1], 1).tolist(), "a": np.round(heading, 3).tolist()}
    return {
        "sea": _xy(*sea), "quay": _xy(*quay), "piers": piers, "breakwater": breakwater,
        "yachts": {**_xy(yachts[:, 0], yachts[:, 1]), "l": np.round(yachts[:, 2], 1).tolist(), "a": np.round(yachts[:, 3], 3).tolist()},
        "pool": pool, "tunnel": tunnel, "blocks": blocks,
    }


def distance_to_quay(quay: np.ndarray, pts: np.ndarray) -> np.ndarray:
    return np.array([np.min(np.hypot(quay[0] - x, quay[1] - y)) for x, y in pts])


def scene(
    geometry: TrackGeometry,
    stint: TyreStint,
    car: dict | None = None,
    weather: Weather = WEATHER[0],
    first_straight_m: float = 300.0,
    environment: str = "parkland",
    seafront_m: tuple[float, float] | None = None,
) -> dict:
    """Everything the canvas needs, in world metres, plus the overview camera.

    The view plays ``stint`` on a loop: its laps, then the tyre change at the line.
    Every lap drives the same path, so positions are sent once and each lap adds its times and speeds.

    ``car`` is ``{"body", "wheels", "engine", "color"}``: part keys and #RRGGBB.
    ``environment`` (one of ``ENVIRONMENTS``) picks the ground, trees and surroundings; a harbour
    puts the sea outside the ``seafront_m`` stretch.
    """
    if environment not in ENVIRONMENTS:
        raise ValueError(f"environment must be one of {ENVIRONMENTS}, got {environment!r}")
    car = {"body": "kart", "wheels": "standard", "engine": "standard", "color": "#F2F2F2", **(car or {})}
    playbacks = [LapPlayback.from_lap(l.result, geometry) for l in stint.laps]
    half = geometry.width_m / 2
    left, right = geometry.offset(half), geometry.offset(-half)
    camera = Camera.fit(np.concatenate((left[0], right[0])), np.concatenate((left[1], right[1])), VIEW_W, VIEW_H, 24)
    # Sakhir-style tarmac run-off in the desert; tarmac escape roads only at slow corners in the city.
    runoff, armco = _runoff(geometry, gravel_traps=environment not in ("desert", "harbour"), street=environment == "harbour")
    seed = sum(map(ord, geometry.track_name))
    harbour = _harbour(geometry, seed, seafront_m) if environment == "harbour" and seafront_m else {}
    trees = _trees(geometry, seed, environment)
    if harbour:  # no trees in the sea or on a roof
        tx, ty = np.array(trees["x"]), np.array(trees["y"])
        keep = ~inside_polygon(harbour["sea"]["x"], harbour["sea"]["y"], tx, ty)
        B = harbour["blocks"]
        for bx, by, bw, bh in zip(B["x"], B["y"], B["w"], B["h"]):
            keep &= np.hypot(tx - bx, ty - by) > np.hypot(bw, bh) / 2 + 2
        trees = {k: np.array(v)[keep].tolist() for k, v in trees.items()}
    curb_offset = half + CURB_WIDTH_M / 2
    curbs = []
    for run in _corner_runs(geometry):
        for side in (curb_offset, -curb_offset):
            x, y = geometry.offset(side)
            curbs.append(_xy(x[run], y[run]))
    return {
        "view": {"w": VIEW_W, "h": VIEW_H},
        "camera": {"scale": camera.scale_px_per_m, "ox": camera.offset_x_px, "oy": camera.offset_y_px},
        "follow_scale": FOLLOW_SCALE_PX_PER_M,
        "bounds": [float(geometry.x_m.min() - SCENERY_PAD_M), float(geometry.y_m.min() - SCENERY_PAD_M),
                   float(geometry.x_m.max() + SCENERY_PAD_M), float(geometry.y_m.max() + SCENERY_PAD_M)],
        "track": {
            "name": geometry.track_name,
            "width": geometry.width_m,
            "center": _xy(geometry.x_m, geometry.y_m),
            "left": _xy(*left),
            "right": _xy(*right),
            "curbs": curbs,
            "curb_width": CURB_WIDTH_M,
            "runoff": runoff,
            "armco": armco,
            "runoff_width": RUNOFF_WIDTH_M,
            "start": {"x": float(geometry.x_m[0]), "y": float(geometry.y_m[0]), "h": float(geometry.heading_rad[0])},
        },
        "environment": environment,
        "scenery": {
            "buildings": _buildings(geometry, first_straight_m),
            "trees": trees,
            "harbour": harbour,
        },
        "weather": {"name": weather.name, "rain": weather.rain_intensity},
        "car": car,
        "change_s": stint.change_s,
        "frames": {
            "x": np.round(playbacks[0].x_m, 3).tolist(),
            "y": np.round(playbacks[0].y_m, 3).tolist(),
            "h": np.round(playbacks[0].heading_rad, 5).tolist(),
        },
        "laps": [
            {"time": pb.lap_time_s, "d0": round(l.durability_start, 4), "d1": round(l.durability_end, 4),
             "t": np.round(pb.time_s, 4).tolist(), "v": np.round(pb.speed_mps, 3).tolist()}
            for pb, l in zip(playbacks, stint.laps)
        ],
    }


def track_view_html(*args, **kwargs) -> str:
    """``scene(...)`` embedded in the canvas page; same arguments as ``scene``."""
    payload = json.dumps(scene(*args, **kwargs)).replace("</", "<\\/")
    return _TEMPLATE.read_text(encoding="utf-8").replace("__SCENE__", payload)
