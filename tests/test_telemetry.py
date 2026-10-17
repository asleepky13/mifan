import json
import math
import unittest

import numpy as np

from racelab.geometry import build_geometry
from racelab.simulation import simulate_lap
from racelab.summary import car_from_setup
from racelab.telemetry import build_telemetry, lap_summary
from racelab.track import CIRCUITS, WEATHER, Segment, Track
from tests import sports_car
from ui.telemetry_view import telemetry_html, telemetry_payload


def telemetry_for(car, track):
    return build_telemetry(simulate_lap(car, track), car, track, build_geometry(track))


class TelemetryTest(unittest.TestCase):
    def test_channels_are_bounded_and_exclusive(self):
        car = sports_car()
        for track in CIRCUITS:
            t = telemetry_for(car, track.in_weather(WEATHER[2]))
            with self.subTest(track=track.name):
                for ch in (t.throttle_pct, t.brake_pct):
                    self.assertTrue(np.all((ch >= 0) & (ch <= 100)))
                self.assertFalse(np.any((t.throttle_pct > 1) & (t.brake_pct > 1)), "throttle and brake overlap")
                self.assertGreater(t.throttle_pct.max(), 99.5)  # full throttle on the straights
                self.assertGreater(t.brake_pct.max(), 50)       # hard braking into corners
                self.assertTrue(np.all(np.diff(t.time_s) > 0))

    def test_braking_happens_where_the_car_slows(self):
        t = telemetry_for(sports_car(), CIRCUITS[0])
        slowing = np.diff(np.append(t.speed_mps, t.speed_mps[0])) < -0.5
        self.assertTrue(np.all(t.brake_pct[slowing] > 0))
        self.assertTrue(np.all(t.brake_pct[~slowing & (np.diff(np.append(t.speed_mps, t.speed_mps[0])) > 0)] == 0))

    def test_steering_is_kinematic_and_signed(self):
        r = 40.0
        for direction in (1, -1):
            track = Track("ring", (Segment(2 * math.pi * r, r, direction=direction),))
            t = telemetry_for(sports_car(), track)
            with self.subTest(direction=direction):
                self.assertTrue(np.allclose(t.steering_deg, direction * math.degrees(math.atan(sports_car().wheelbase_m / r))))
                # Constant speed around a ring: no braking, part throttle to hold speed against drag.
                self.assertTrue(np.all(t.brake_pct == 0))
                self.assertTrue(np.all((t.throttle_pct > 0) & (t.throttle_pct < 100)))

    def test_gear_channel_follows_speed(self):
        car = car_from_setup(1200, 400, 0.32, 2.2, 1.2, 10)
        t = telemetry_for(car, CIRCUITS[0])
        self.assertEqual(set(np.unique(t.gear)) - set(range(1, 7)), set())
        order = np.argsort(t.speed_mps)
        self.assertTrue(np.all(np.diff(t.gear[order]) >= 0))  # faster never means a lower gear
        self.assertGreaterEqual(t.gear.max() - t.gear.min(), 3)
        self.assertTrue(np.all(telemetry_for(sports_car(), CIRCUITS[0]).gear == 0))  # no gearbox, no gears

    def test_summary_is_consistent(self):
        t = telemetry_for(sports_car(), CIRCUITS[1])
        s = lap_summary(t)
        self.assertAlmostEqual(s["avg_speed_kmh"], t.length_m / t.lap_time_s * 3.6)
        self.assertLessEqual(s["full_throttle_pct"] + s["braking_pct"], 100.0)
        self.assertGreater(s["top_speed_kmh"], s["avg_speed_kmh"])
        self.assertAlmostEqual(t.lap_time_s, simulate_lap(sports_car(), CIRCUITS[1]).lap_time_s, places=6)

    def test_rejects_mismatched_inputs(self):
        lap = simulate_lap(sports_car(), CIRCUITS[0])
        with self.assertRaises(ValueError):
            build_telemetry(lap, sports_car(), CIRCUITS[1], build_geometry(CIRCUITS[1]))
        with self.assertRaises(ValueError):
            telemetry_payload(telemetry_for(sports_car(), CIRCUITS[0]), telemetry_for(sports_car(), CIRCUITS[1]))


class DashboardTest(unittest.TestCase):
    def test_payload_delta_and_html(self):
        track = CIRCUITS[2]
        base = telemetry_for(sports_car(), track)
        fast = telemetry_for(sports_car(power_w=400e3), track)
        data = telemetry_payload(fast, base)
        self.assertEqual(data["delta"][0], 0.0)
        self.assertLess(data["delta"][-1], 0)  # more power: ahead by the end of the lap
        self.assertEqual(len(data["series"]["current"]["speed"]), len(data["distance"]))
        self.assertTrue(np.allclose(telemetry_payload(base, base)["delta"], 0))
        html = telemetry_html(fast, base)
        payload = html.split("const D = ", 1)[1].split(";\n", 1)[0]
        self.assertEqual(json.loads(payload)["summary"]["baseline"]["lap_time_s"], base.lap_time_s)


if __name__ == "__main__":
    unittest.main()
