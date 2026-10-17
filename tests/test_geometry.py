import json
import math
import unittest

import numpy as np

from racelab.config import NOT_MODELED, AeroPackage, BodyPackage, TireCompound, VehicleConfig
from racelab.geometry import Camera, build_geometry
from racelab.playback import LapPlayback
from racelab.simulation import simulate_lap
from racelab.track import HIGH_SPEED_CIRCUIT, TECHNICAL_CIRCUIT, Segment, Track
from tests import sports_car
from ui.track_view import scene, track_view_html

TRACKS = (TECHNICAL_CIRCUIT, HIGH_SPEED_CIRCUIT)


class GeometryTest(unittest.TestCase):
    def test_bundled_tracks_close_as_loops(self):
        for track in TRACKS:
            g = build_geometry(track)
            with self.subTest(track=track.name):
                self.assertLess(g.closure_error_m, 0.1)
                self.assertLess(g.heading_closure_error_rad, 1e-9)
                self.assertAlmostEqual(abs(g.total_turn_rad), 2 * math.pi)
                # Consecutive centerline points are one step apart (no jumps).
                gaps = np.hypot(np.diff(g.x_m), np.diff(g.y_m))
                self.assertTrue(np.all(gaps <= g.step_m + 1e-9))
                self.assertGreater(gaps.min(), 0.9 * g.step_m)

    def test_circle_is_exact(self):
        for direction in (1, -1):
            r = 50.0
            g = build_geometry(Track("circle", (Segment(2 * math.pi * r, r, direction=direction),)), 1.0)
            with self.subTest(direction=direction):
                self.assertLess(g.closure_error_m, 1e-9)
                self.assertTrue(np.allclose(np.hypot(g.x_m, g.y_m - direction * r), r))
                self.assertTrue(np.allclose(g.curvature_per_m, direction / r))
                self.assertAlmostEqual(g.total_turn_rad, direction * 2 * math.pi)

    def test_open_layout_reports_gap(self):
        g = build_geometry(Track("line", (Segment(100),)), 1.0)
        self.assertAlmostEqual(g.closure_error_m, 100.0)

    def test_pose_at_wraps_and_starts_at_origin(self):
        g = build_geometry(TECHNICAL_CIRCUIT)
        x0, y0, h0 = g.pose_at(0.0)
        self.assertEqual((float(x0), float(y0), float(h0)), (0.0, 0.0, 0.0))
        for s in (13.7, 500.0):
            a, b = g.pose_at(s), g.pose_at(s + g.length_m)
            self.assertTrue(np.allclose(a[:2], b[:2]))

    def test_offset_left_is_positive_y_on_first_straight(self):
        g = build_geometry(TECHNICAL_CIRCUIT)
        lx, ly = g.offset(5.0)
        self.assertAlmostEqual(lx[1], g.x_m[1])
        self.assertAlmostEqual(ly[1], g.y_m[1] + 5.0)

    def test_invalid_track_fields(self):
        with self.assertRaises(ValueError):
            Segment(10, 5, direction=0)
        with self.assertRaises(ValueError):
            Track("t", (Segment(10),), width_m=0)
        with self.assertRaises(ValueError):
            build_geometry(TECHNICAL_CIRCUIT, step_m=0)


class CameraTest(unittest.TestCase):
    def test_fit_keeps_points_inside_margins_with_uniform_scale(self):
        x, y = np.array([-100.0, 300.0]), np.array([50.0, 150.0])
        cam = Camera.fit(x, y, 1000, 640, margin_px=20)
        sx, sy = cam.to_screen(x, y)
        self.assertTrue(np.all((sx >= 20 - 1e-9) & (sx <= 980 + 1e-9)))
        self.assertTrue(np.all((sy >= 20 - 1e-9) & (sy <= 620 + 1e-9)))
        self.assertAlmostEqual(sx.max() - sx.min(), 960)  # width is the limiting span
        self.assertAlmostEqual((sx.min() + sx.max()) / 2, 500)
        self.assertAlmostEqual((sy.min() + sy.max()) / 2, 320)

    def test_y_axis_flips_and_round_trips(self):
        cam = Camera(2.0, 10.0, 500.0)
        _, low = cam.to_screen(0.0, 0.0)
        _, high = cam.to_screen(0.0, 100.0)
        self.assertLess(high, low)
        wx, wy = cam.to_world(*cam.to_screen(np.array([3.5, -7.0]), np.array([12.0, 40.0])))
        self.assertTrue(np.allclose(wx, [3.5, -7.0]) and np.allclose(wy, [12.0, 40.0]))

    def test_centered_on_puts_point_mid_screen(self):
        cam = Camera.centered_on(123.0, -45.0, 9.0, 1000, 640)
        sx, sy = cam.to_screen(123.0, -45.0)
        self.assertAlmostEqual(float(sx), 500)
        self.assertAlmostEqual(float(sy), 320)

    def test_fit_rejects_degenerate_input(self):
        with self.assertRaises(ValueError):
            Camera.fit(np.array([1.0]), np.array([1.0]), 100, 100)
        with self.assertRaises(ValueError):
            Camera.fit(np.array([0.0, 1.0]), np.array([0.0, 1.0]), 100, 100, margin_px=60)


class PlaybackTest(unittest.TestCase):
    def test_playback_matches_simulation(self):
        for track in TRACKS:
            lap = simulate_lap(sports_car(), track)
            pb = LapPlayback.from_lap(lap, build_geometry(track))
            with self.subTest(track=track.name):
                self.assertAlmostEqual(pb.lap_time_s, lap.lap_time_s, places=9)
                self.assertTrue(np.all(np.diff(pb.time_s) > 0))
                start, again = pb.state_at(0.0), pb.state_at(pb.lap_time_s)
                self.assertEqual((start.lap, again.lap), (1, 2))
                self.assertAlmostEqual(again.x_m, start.x_m, places=6)
                self.assertAlmostEqual(again.speed_mps, start.speed_mps, places=6)
                mid = pb.state_at(pb.time_s[100])
                self.assertAlmostEqual(mid.speed_mps, lap.speed_mps[100])
                self.assertAlmostEqual(mid.distance_m, lap.distance_m[100])
                # Heading stays continuous across the finish line.
                self.assertLess(np.max(np.abs(np.diff(pb.heading_rad))), 0.2)

    def test_rejects_mismatched_track_and_bad_time(self):
        lap = simulate_lap(sports_car(), TECHNICAL_CIRCUIT)
        with self.assertRaises(ValueError):
            LapPlayback.from_lap(lap, build_geometry(HIGH_SPEED_CIRCUIT))
        with self.assertRaises(ValueError):
            LapPlayback.from_lap(lap, build_geometry(TECHNICAL_CIRCUIT)).state_at(-1.0)


class ConfigTest(unittest.TestCase):
    def test_to_car_uses_modeled_fields_only(self):
        base = VehicleConfig(tires=TireCompound(grip_coefficient=1.4), aero=AeroPackage(drag_coefficient=0.3))
        car = base.to_car()
        self.assertEqual((car.tire_friction, car.drag_coefficient), (1.4, 0.3))
        stored_only = VehicleConfig(
            tires=TireCompound(grip_coefficient=1.4, temperature_c=40, wear_fraction=0.8),
            aero=AeroPackage(drag_coefficient=0.3, downforce_coefficient_m2=3.0),
        )
        self.assertEqual(stored_only.to_car(), car)
        self.assertEqual(len(NOT_MODELED), 4)

    def test_invalid_config_rejected(self):
        for build in (
            lambda: TireCompound(wear_fraction=1.5),
            lambda: AeroPackage(downforce_coefficient_m2=-1),
            lambda: BodyPackage(color_hex="red"),
            lambda: BodyPackage(length_m=0),
        ):
            with self.assertRaises(ValueError):
                build()


class SceneTest(unittest.TestCase):
    def test_scene_payload_is_complete_and_safe(self):
        track = TECHNICAL_CIRCUIT
        geometry = build_geometry(track)
        pb = LapPlayback.from_lap(simulate_lap(sports_car(), track), geometry)
        data = scene(geometry, pb, BodyPackage(color_hex="#123456"))
        corners = sum(not s.is_straight for s in track.segments)
        self.assertEqual(len(data["track"]["curbs"]), 2 * corners)
        self.assertEqual(len(data["frames"]["t"]), len(pb.time_s))
        self.assertEqual(data["body"]["color"], "#123456")
        html = track_view_html(geometry, pb, BodyPackage())
        self.assertNotIn("__SCENE__", html)
        payload = html.split("const S = ", 1)[1].split(";\n", 1)[0]
        self.assertEqual(json.loads(payload)["track"]["name"], track.name)


if __name__ == "__main__":
    unittest.main()
