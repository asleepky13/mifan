import math
import unittest

from racelab.physics import (
    GRAVITY_MPS2,
    aero_drag_force,
    braking_deceleration,
    cornering_speed,
    drive_force,
    net_acceleration,
    top_speed_bound,
)
from racelab.track import Segment, Track
from tests import sports_car


class DragTest(unittest.TestCase):
    def test_zero_at_rest_and_quadruples_with_double_speed(self):
        car = sports_car()
        self.assertEqual(aero_drag_force(car, 0.0), 0.0)
        self.assertAlmostEqual(aero_drag_force(car, 60.0) / aero_drag_force(car, 30.0), 4.0, places=12)

    def test_rejects_negative_speed(self):
        with self.assertRaises(ValueError):
            aero_drag_force(sports_car(), -1.0)


class DriveForceTest(unittest.TestCase):
    def test_traction_cap_at_low_speed(self):
        car = sports_car()
        self.assertEqual(drive_force(car, 0.0), car.max_tractive_force_n)
        self.assertEqual(drive_force(car, 5.0), car.max_tractive_force_n)

    def test_power_limit_at_high_speed(self):
        car = sports_car()
        v = 60.0
        self.assertAlmostEqual(drive_force(car, v), car.power_w * car.drivetrain_efficiency / v)
        self.assertLess(drive_force(car, v), car.max_tractive_force_n)

    def test_friction_limit_on_low_grip(self):
        car = sports_car(max_tractive_force_n=50_000.0)
        friction = car.tire_friction * 0.5 * car.mass_kg * GRAVITY_MPS2
        self.assertAlmostEqual(drive_force(car, 1.0, grip_multiplier=0.5), friction)

    def test_finite_at_zero_speed_even_without_traction_cap(self):
        car = sports_car(max_tractive_force_n=1e12, tire_friction=3.0)
        self.assertTrue(math.isfinite(drive_force(car, 0.0)))

    def test_net_acceleration_is_zero_or_negative_at_top_speed_bound(self):
        car = sports_car()
        self.assertLessEqual(net_acceleration(car, top_speed_bound(car)), 1e-9)
        self.assertGreater(net_acceleration(car, 10.0), 0.0)


class CorneringTest(unittest.TestCase):
    def test_tighter_corner_and_lower_grip_are_slower(self):
        self.assertLess(cornering_speed(20.0, 1.0), cornering_speed(80.0, 1.0))
        self.assertLess(cornering_speed(50.0, 0.7), cornering_speed(50.0, 1.1))
        # v scales with sqrt(r).
        self.assertAlmostEqual(cornering_speed(100.0, 1.0) / cornering_speed(25.0, 1.0), 2.0)

    def test_straight_is_unlimited(self):
        self.assertEqual(cornering_speed(None, 1.0), math.inf)


class BrakingTest(unittest.TestCase):
    def test_configured_limit_when_grip_is_ample(self):
        car = sports_car(max_braking_decel_mps2=8.0, tire_friction=1.5)
        self.assertEqual(braking_deceleration(car), 8.0)

    def test_friction_limit_when_grip_is_low(self):
        car = sports_car(max_braking_decel_mps2=15.0)
        self.assertAlmostEqual(braking_deceleration(car, 0.5), car.tire_friction * 0.5 * GRAVITY_MPS2)


class ValidationTest(unittest.TestCase):
    def test_invalid_car_parameters_rejected(self):
        for bad in (
            {"mass_kg": 0.0},
            {"power_w": -1.0},
            {"drag_coefficient": math.nan},
            {"frontal_area_m2": math.inf},
            {"tire_friction": 3.5},
            {"max_braking_decel_mps2": 0.0},
            {"max_tractive_force_n": -5.0},
            {"drivetrain_efficiency": 1.2},
            {"mass_kg": "heavy"},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                sports_car(**bad)

    def test_invalid_track_rejected(self):
        for kwargs in ({"length_m": 0.0}, {"length_m": 10.0, "radius_m": -3.0}, {"length_m": 10.0, "grip_multiplier": 0.0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Segment(**kwargs)
        with self.assertRaises(ValueError):
            Track("empty", ())


if __name__ == "__main__":
    unittest.main()
