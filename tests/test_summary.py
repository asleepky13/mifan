import unittest

import numpy as np

from racelab.simulation import simulate_lap
from racelab.summary import HP_TO_W, car_from_setup, corner_average_speed_mps, time_to_speed
from racelab.track import TECHNICAL_CIRCUIT, Segment, Track

DEFAULT_SETUP = dict(
    mass_kg=1200, power_hp=400, drag_coefficient=0.32, frontal_area_m2=2.2, tire_friction=1.2, max_braking_decel_mps2=10
)


class SummaryTest(unittest.TestCase):
    def test_car_from_setup_converts_horsepower(self):
        car = car_from_setup(**DEFAULT_SETUP)
        self.assertAlmostEqual(car.power_w, 400 * HP_TO_W)
        self.assertEqual(car.mass_kg, 1200.0)

    def test_slider_extremes_are_valid_cars(self):
        for mass, hp, cd, area, mu, brake in ((800, 1000, 0.20, 1.5, 2.0, 15), (1800, 100, 0.60, 3.5, 0.8, 5)):
            lap = simulate_lap(car_from_setup(mass, hp, cd, area, mu, brake), TECHNICAL_CIRCUIT)
            self.assertTrue(lap.converged and lap.constraints_satisfied)

    def test_time_to_speed_is_plausible_and_improves_with_power(self):
        base = time_to_speed(car_from_setup(**DEFAULT_SETUP))
        more = time_to_speed(car_from_setup(**{**DEFAULT_SETUP, "power_hp": 800}))
        self.assertTrue(1.5 < more < base < 10, (base, more))

    def test_time_to_speed_none_when_unreachable(self):
        car = car_from_setup(**{**DEFAULT_SETUP, "power_hp": 100})
        self.assertIsNone(time_to_speed(car, target_mps=150.0))

    def test_corner_average_within_corner_limits(self):
        lap = simulate_lap(car_from_setup(**DEFAULT_SETUP), TECHNICAL_CIRCUIT)
        corner = corner_average_speed_mps(lap)
        limits = lap.corner_speed_limit_mps[np.isfinite(lap.corner_speed_limit_mps)]
        self.assertTrue(0 < corner <= limits.max())
        self.assertLess(corner, lap.max_speed_mps)

    def test_corner_average_none_without_corners(self):
        lap = simulate_lap(car_from_setup(**DEFAULT_SETUP), Track("straight", (Segment(2000),)))
        self.assertIsNone(corner_average_speed_mps(lap))


if __name__ == "__main__":
    unittest.main()
