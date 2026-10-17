import math
import unittest

import numpy as np

from racelab.physics import braking_deceleration, cornering_speed
from racelab.geometry import build_geometry, build_racing_line
from racelab.parts import PARTS_BY_CATEGORY, apply_parts
from racelab.simulation import simulate_lap
from racelab.summary import car_from_setup
from racelab.track import CIRCUITS, HIGH_SPEED_CIRCUIT, TECHNICAL_CIRCUIT, WEATHER, Segment, Track, Weather
from tests import sports_car

TRACKS = CIRCUITS


class LapTest(unittest.TestCase):
    def test_lap_is_finite_converged_and_constrained(self):
        car = sports_car()
        for track in TRACKS:
            with self.subTest(track=track.name):
                r = simulate_lap(car, track)
                self.assertTrue(math.isfinite(r.lap_time_s) and r.lap_time_s > 0)
                self.assertTrue(r.converged)
                self.assertTrue(r.constraints_satisfied)
                self.assertTrue(np.all(r.speed_mps > 0))
                self.assertTrue(np.all(r.speed_mps <= r.corner_speed_limit_mps + 1e-6))
                self.assertAlmostEqual(r.total_distance_m, track.total_length_m)
                self.assertAlmostEqual(r.average_speed_mps * r.lap_time_s, track.total_length_m)
                self.assertLessEqual(r.average_speed_mps, r.max_speed_mps)
                self.assertTrue(np.all(r.acceleration_mps2 >= -braking_deceleration(car) - 1e-6))
                self.assertEqual(len(r.distance_m), len(r.speed_mps))

    def test_tracks_differ_in_character(self):
        car = sports_car()
        tech = simulate_lap(car, TECHNICAL_CIRCUIT)
        fast = simulate_lap(car, HIGH_SPEED_CIRCUIT)
        self.assertGreater(fast.average_speed_mps, tech.average_speed_mps)
        self.assertGreater(fast.max_speed_mps, tech.max_speed_mps)

    def test_higher_power_is_faster(self):
        base = simulate_lap(sports_car(), HIGH_SPEED_CIRCUIT).lap_time_s
        more = simulate_lap(sports_car(power_w=400e3), HIGH_SPEED_CIRCUIT).lap_time_s
        self.assertLess(more, base)

    def test_resolution_consistency(self):
        car = sports_car()
        for track in TRACKS:
            fine, t1, t2, t5 = (simulate_lap(car, track, ds).lap_time_s for ds in (0.5, 1.0, 2.0, 5.0))
            with self.subTest(track=track.name, times=(fine, t1, t2, t5)):
                # Converges as the step shrinks; corner windows make coarse steps slightly slower.
                self.assertLess(abs(t1 - fine) / fine, 0.005)
                self.assertLess(abs(t2 - fine) / fine, 0.01)  # the app's step
                self.assertLess(abs(t5 - fine) / fine, 0.02)

    def test_braking_starts_before_corner(self):
        # Long straight into a tight hairpin; the car must already be at the
        # hairpin limit when the hairpin begins.
        track = Track("probe", (Segment(1000), Segment(30, 15), Segment(500)))
        car = sports_car()
        r = simulate_lap(car, track, 1.0)
        apex = cornering_speed(15, car.tire_friction)
        at_entry = r.speed_mps[int(1000 / r.step_m)]
        self.assertLessEqual(at_entry, apex + 1e-6)
        before = r.distance_m < 1000
        self.assertTrue(np.any(r.acceleration_mps2[before] < -1.0), "no braking before the hairpin")

    def test_braking_wraps_across_finish_line(self):
        # The only corner sits at the very start of the lap, so braking for it
        # must happen at the end of the previous lap.
        track = Track("wrap", (Segment(20, 15), Segment(1500)))
        car = sports_car()
        r = simulate_lap(car, track, 1.0)
        apex = cornering_speed(15, car.tire_friction)
        self.assertLessEqual(r.speed_mps[0], apex + 1e-6)
        self.assertLess(r.acceleration_mps2[-1], -1.0)
        self.assertLess(r.speed_mps[-1], r.speed_mps[len(r.speed_mps) // 2])
        self.assertTrue(r.converged and r.constraints_satisfied)

    def test_all_straight_loop_runs_at_terminal_speed(self):
        r = simulate_lap(sports_car(), Track("oval-ish", (Segment(3000),)))
        self.assertTrue(r.converged)
        self.assertLess(np.ptp(r.speed_mps), 1e-6)

    def test_short_corner_not_skipped_at_coarse_resolution(self):
        track = Track("kink", (Segment(500), Segment(1.0, 10), Segment(500)))
        car = sports_car()
        r = simulate_lap(car, track, 10.0)
        self.assertLessEqual(r.speed_mps.min(), cornering_speed(10, car.tire_friction) + 1e-6)

    def test_weather_scales_grip_and_wetter_is_slower(self):
        car = sports_car()
        for track in CIRCUITS:
            times = [simulate_lap(car, track.in_weather(w)).lap_time_s for w in WEATHER]
            with self.subTest(track=track.name, times=times):
                self.assertEqual(times, sorted(times))
                self.assertLess(times[0], times[-1])
        wet = TECHNICAL_CIRCUIT.in_weather(Weather("Test", 0.5))
        self.assertEqual([s.grip_multiplier for s in wet.segments], [s.grip_multiplier * 0.5 for s in TECHNICAL_CIRCUIT.segments])
        self.assertEqual(wet.name, TECHNICAL_CIRCUIT.name)

    def test_invalid_weather_rejected(self):
        for kwargs in ({"grip_multiplier": 0.0}, {"grip_multiplier": 1.0, "rain_intensity": 1.5}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Weather("bad", **kwargs)

    def test_full_model_on_the_racing_line(self):
        # The app's car: gearbox, rear drive with load transfer, a downforce wing, friction circle.
        car = apply_parts(car_from_setup(1200, 400, 0.32, 2.2, 1.2, 10), [PARTS_BY_CATEGORY["wing"]["high"]])
        for track in TRACKS:
            line = build_racing_line(build_geometry(track))
            center = simulate_lap(car, track)
            racing = simulate_lap(car, track, racing_line=line)
            with self.subTest(track=track.name):
                self.assertTrue(racing.converged and racing.constraints_satisfied)
                self.assertLess(racing.lap_time_s, center.lap_time_s)  # using the width is faster
                self.assertAlmostEqual(racing.path_length_m, line.step_length_m.sum())
                self.assertTrue(np.allclose(racing.lateral_offset_m, line.offset_m))

    def test_downforce_pays_in_corners_costs_on_straights(self):
        base = car_from_setup(1200, 400, 0.32, 2.2, 1.2, 10)
        winged = apply_parts(base, [PARTS_BY_CATEGORY["wing"]["high"]])
        a, b = simulate_lap(base, TECHNICAL_CIRCUIT), simulate_lap(winged, TECHNICAL_CIRCUIT)
        self.assertLess(b.lap_time_s, a.lap_time_s)                      # Monaco is all corners
        self.assertGreater(np.median(b.speed_mps[np.isfinite(b.corner_speed_limit_mps)]),
                           np.median(a.speed_mps[np.isfinite(a.corner_speed_limit_mps)]))

    def test_rejects_line_from_another_track(self):
        line = build_racing_line(build_geometry(HIGH_SPEED_CIRCUIT))
        with self.assertRaises(ValueError):
            simulate_lap(sports_car(), TECHNICAL_CIRCUIT, racing_line=line)

    def test_rejects_bad_step(self):
        for step in (0.0, -1.0, math.nan, 1e9):
            with self.subTest(step=step), self.assertRaises(ValueError):
                simulate_lap(sports_car(), TECHNICAL_CIRCUIT, step)


if __name__ == "__main__":
    unittest.main()
