import math
import unittest

import numpy as np

from racelab.geometry import build_geometry, build_racing_line
from racelab.playback import LapPlayback
from racelab.simulation import simulate_lap
from racelab.track import CIRCUITS, HIGH_SPEED_CIRCUIT, TECHNICAL_CIRCUIT, Segment, Track
from tests import sports_car


class RacingLineTest(unittest.TestCase):
    def test_line_stays_on_track_and_uses_the_width_in_corners(self):
        for track in CIRCUITS:
            g = build_geometry(track)
            line = build_racing_line(g)
            room = track.width_m / 2 - 1.5
            with self.subTest(track=track.name):
                self.assertTrue(np.all(np.abs(line.offset_m) <= room + 1e-9))
                self.assertGreater(np.abs(line.offset_m).max(), 0.95 * room)  # reaches an edge somewhere
                # Less total squared curvature than the centerline: corners are straightened.
                self.assertLess(np.sum(line.curvature_per_m**2 * line.step_length_m), np.sum(g.curvature_per_m**2 * g.step_m))
                gaps = np.hypot(np.diff(line.x_m), np.diff(line.y_m))
                self.assertTrue(np.all(gaps < 2 * g.step_m))  # continuous, no jumps

    def test_long_straight_returns_to_the_middle(self):
        g = build_geometry(HIGH_SPEED_CIRCUIT)  # Monza: 1.2 km main straight first
        line = build_racing_line(g)
        middle = (g.distance_m > 450) & (g.distance_m < 750)
        self.assertLess(np.abs(line.offset_m[middle]).max(), 1.0)

    def test_corner_entry_is_on_the_outside(self):
        # A lone left-hand hairpin between long straights: approach on the right (outside), apex on the left.
        track = Track("hairpin", (Segment(600), Segment(math.pi * 20, 20), Segment(600), Segment(math.pi * 20, 20)), width_m=14)
        g = build_geometry(track, 2.0)
        line = build_racing_line(g)
        apex = np.argmin(np.abs(g.distance_m - (600 + math.pi * 10)))
        entry = np.argmin(np.abs(g.distance_m - 590))
        self.assertGreater(line.offset_m[apex], 4)   # inside of a left turn = left = positive
        self.assertLess(line.offset_m[entry], -2)    # outside before the turn

    def test_rejects_track_too_narrow(self):
        with self.assertRaises(ValueError):
            build_racing_line(build_geometry(Track("lane", (Segment(500, 80),), width_m=2.5)))


class LapOnLineTest(unittest.TestCase):
    def test_using_the_width_is_faster_and_still_legal(self):
        for track in CIRCUITS:
            line = build_racing_line(build_geometry(track))
            center, racing = simulate_lap(sports_car(), track), simulate_lap(sports_car(), track, racing_line=line)
            with self.subTest(track=track.name):
                self.assertTrue(racing.converged and racing.constraints_satisfied)
                self.assertLess(racing.lap_time_s, center.lap_time_s)
                self.assertTrue(np.allclose(racing.lateral_offset_m, line.offset_m))
                self.assertTrue(np.allclose(racing.step_length_m, line.step_length_m))

    def test_car_follows_the_racing_line(self):
        g = build_geometry(HIGH_SPEED_CIRCUIT)
        line = build_racing_line(g)
        pb = LapPlayback.from_lap(simulate_lap(sports_car(), HIGH_SPEED_CIRCUIT, racing_line=line), g)
        self.assertTrue(np.allclose(pb.x_m[:-1], line.x_m) and np.allclose(pb.y_m[:-1], line.y_m))
        self.assertLess(np.max(np.abs(np.diff(pb.heading_rad))), 0.2)
        self.assertAlmostEqual(pb.heading_rad[-1] - pb.heading_rad[0], g.total_turn_rad, places=6)

    def test_rejects_line_from_another_track(self):
        line = build_racing_line(build_geometry(HIGH_SPEED_CIRCUIT))
        with self.assertRaises(ValueError):
            simulate_lap(sports_car(), TECHNICAL_CIRCUIT, racing_line=line)

    def test_standing_start_and_stop_at_the_line(self):
        track = HIGH_SPEED_CIRCUIT
        flying = simulate_lap(sports_car(), track)
        lap = simulate_lap(sports_car(), track, standing_start=True, stop_at_finish=True)
        self.assertEqual((lap.speed_mps[0], lap.finish_speed_mps), (0.0, 0.0))
        self.assertEqual(flying.finish_speed_mps, flying.speed_mps[0])
        self.assertTrue(lap.constraints_satisfied)
        self.assertTrue(np.all(lap.speed_mps <= flying.speed_mps + 1e-12))
        self.assertGreater(lap.lap_time_s, flying.lap_time_s + 2)  # launching and stopping cost time
        # Mid-lap the car is back on the flying profile.
        mid = len(lap.speed_mps) // 2
        self.assertEqual(lap.speed_mps[mid], flying.speed_mps[mid])
        pb = LapPlayback.from_lap(lap, build_geometry(track))
        self.assertEqual((pb.speed_mps[0], pb.speed_mps[-1]), (0.0, 0.0))
        self.assertAlmostEqual(pb.lap_time_s, lap.lap_time_s, places=9)


if __name__ == "__main__":
    unittest.main()
