import math
import unittest

import numpy as np

from racelab.car import Gearbox
from racelab.physics import (
    AIR_DENSITY_KG_M3,
    GRAVITY_MPS2,
    corner_speed_limit,
    downforce,
    engine_force,
    grip_left_for_longitudinal,
    selected_gear,
    traction_limit,
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


GEARBOX = Gearbox(ratios=(11.05, 8.70, 6.85, 5.39, 4.24, 3.33))


class DownforceTest(unittest.TestCase):
    def test_downforce_grows_with_v_squared_and_adds_corner_speed(self):
        car = sports_car(downforce_coefficient_m2=2.0)
        self.assertAlmostEqual(downforce(car, 60.0) / downforce(car, 30.0), 4.0)
        self.assertAlmostEqual(downforce(car, 50.0), 0.5 * AIR_DENSITY_KG_M3 * 2.0 * 2500)
        for r in (20.0, 100.0, 300.0):
            plain = cornering_speed(r, sports_car().tire_friction)
            self.assertAlmostEqual(corner_speed_limit(sports_car(), 1 / r), plain)  # no wing = old formula
            winged = corner_speed_limit(car, 1 / r)
            self.assertGreater(winged, plain)
            # At the limit, lateral force equals mu times the downforce-boosted load.
            self.assertAlmostEqual(car.mass_kg * winged**2 / r, car.tire_friction * (car.mass_kg * GRAVITY_MPS2 + downforce(car, winged)), places=4)

    def test_enough_downforce_removes_the_grip_limit(self):
        self.assertEqual(corner_speed_limit(sports_car(downforce_coefficient_m2=50.0), 1 / 400), math.inf)


class FrictionCircleTest(unittest.TestCase):
    def test_cornering_uses_up_longitudinal_grip(self):
        car = sports_car(max_braking_decel_mps2=20.0, max_tractive_force_n=1e6)
        r = 50.0
        v_lim = cornering_speed(r, car.tire_friction)
        self.assertEqual(grip_left_for_longitudinal(car, v_lim, 0.0), 1.0)
        self.assertAlmostEqual(grip_left_for_longitudinal(car, v_lim, 1 / r), 0.0, places=6)
        half = v_lim / math.sqrt(2)  # half the lateral grip used -> sqrt(1 - 0.5^2) left
        self.assertAlmostEqual(grip_left_for_longitudinal(car, half, 1 / r), math.sqrt(0.75))
        self.assertAlmostEqual(braking_deceleration(car, 1.0, half, 1 / r), car.tire_friction * GRAVITY_MPS2 * math.sqrt(0.75))
        self.assertLess(drive_force(car, half, 1.0, 1 / r), drive_force(car, half))


class LoadTransferTest(unittest.TestCase):
    def test_driven_axle_traction(self):
        kw = dict(rear_weight_fraction=0.55, cg_height_m=0.45, wheelbase_m=2.6, max_tractive_force_n=1e6)
        mu_n = sports_car().tire_friction * sports_car().mass_kg * GRAVITY_MPS2
        transfer = sports_car().tire_friction * 0.45 / 2.6
        rear = traction_limit(sports_car(driven_axle="rear", **kw), 10.0)
        front = traction_limit(sports_car(driven_axle="front", **kw), 10.0)
        self.assertAlmostEqual(rear, mu_n * 0.55 / (1 - transfer))
        self.assertAlmostEqual(front, mu_n * 0.45 / (1 + transfer))
        self.assertGreater(rear, mu_n * 0.55)   # load moves onto the rear under power
        self.assertLess(front, mu_n * 0.45)     # and off the front
        self.assertAlmostEqual(traction_limit(sports_car(**kw), 10.0), mu_n)  # all-wheel: the whole car


class GearboxTest(unittest.TestCase):
    def test_gears_shift_up_and_never_beat_engine_power(self):
        car = sports_car(gearbox=GEARBOX, max_tractive_force_n=1e6)
        gears = [selected_gear(car, v) for v in np.arange(1.0, 83.0, 1.0)]
        self.assertEqual(gears[0], 1)
        self.assertEqual(gears[-1], 6)
        self.assertTrue(all(b >= a for a, b in zip(gears, gears[1:])))
        for v in (5.0, 20.0, 45.0, 80.0):
            _, force = engine_force(car, v)
            self.assertLessEqual(force * v, car.power_w * car.drivetrain_efficiency + 1e-6)
        self.assertGreater(engine_force(car, 0.0)[1], 0)  # clutch slip: finite force from rest

    def test_no_drive_above_top_gear_redline(self):
        car = sports_car(gearbox=GEARBOX)
        redline_speed = GEARBOX.redline_rpm / 60 * 2 * math.pi * GEARBOX.wheel_radius_m / GEARBOX.ratios[-1]
        self.assertGreater(drive_force(car, redline_speed - 0.5), 0)
        self.assertEqual(drive_force(car, redline_speed + 0.5), 0)

    def test_invalid_gearbox_rejected(self):
        for kwargs in ({"ratios": ()}, {"ratios": (3.0, 4.0)}, {"ratios": (5.0, 3.0), "launch_rpm": 7500}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Gearbox(**kwargs)
        with self.assertRaises(ValueError):
            sports_car(driven_axle="middle")


if __name__ == "__main__":
    unittest.main()
