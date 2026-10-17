import math
import unittest

import numpy as np

from racelab.analysis import SENSITIVITY_PARAMETERS, compare_cars, sensitivity_analysis
from racelab.track import TECHNICAL_CIRCUIT
from tests import sports_car


class CompareTest(unittest.TestCase):
    def test_compare_keeps_order_and_gaps(self):
        cars = [sports_car(name="slow", power_w=120e3), sports_car(name="fast", power_w=400e3)]
        entries = compare_cars(cars, TECHNICAL_CIRCUIT)
        self.assertEqual([e.car.name for e in entries], ["slow", "fast"])
        self.assertEqual(entries[1].gap_to_fastest_s, 0.0)
        self.assertGreater(entries[0].gap_to_fastest_s, 0.0)

    def test_compare_rejects_empty(self):
        with self.assertRaises(ValueError):
            compare_cars([], TECHNICAL_CIRCUIT)


class SensitivityTest(unittest.TestCase):
    def test_all_parameters_include_baseline_and_are_valid(self):
        car = sports_car()
        out = sensitivity_analysis(car, TECHNICAL_CIRCUIT, scales=(0.8, 1.2))
        self.assertEqual(set(out), set(SENSITIVITY_PARAMETERS))
        for name, s in out.items():
            with self.subTest(parameter=name):
                self.assertIn(1.0, s.scales)
                base = s.lap_times_s[list(s.scales).index(1.0)]
                self.assertEqual(base, s.baseline_lap_time_s)
                self.assertTrue(np.all(s.valid))
                self.assertTrue(np.all(np.isfinite(s.lap_times_s) & (s.lap_times_s > 0)))
                self.assertEqual(len(s.values), len(s.scales))

    def test_directions_are_physical(self):
        out = sensitivity_analysis(sports_car(), TECHNICAL_CIRCUIT, scales=(0.8, 1.2))
        lower, higher = 0, -1
        # More mass, drag or frontal area: slower. More power, grip or brakes: not slower.
        for name in ("mass", "drag_coefficient", "frontal_area"):
            self.assertGreater(out[name].lap_times_s[higher], out[name].lap_times_s[lower], name)
        for name in ("power", "grip", "braking"):
            self.assertLessEqual(out[name].lap_times_s[higher], out[name].lap_times_s[lower], name)

    def test_invalid_variant_reported_not_hidden(self):
        car = sports_car(tire_friction=2.8)  # 120% exceeds the friction ceiling
        s = sensitivity_analysis(car, TECHNICAL_CIRCUIT, parameters=["grip"], scales=(0.9, 1.2))["grip"]
        invalid = list(s.scales).index(1.2)
        self.assertFalse(s.valid[invalid])
        self.assertTrue(math.isnan(s.lap_times_s[invalid]))
        self.assertIn("tire_friction", s.errors[invalid])
        self.assertIsNone(s.results[invalid])
        self.assertTrue(s.valid[list(s.scales).index(1.0)])

    def test_rejects_unknown_parameter_and_bad_scale(self):
        with self.assertRaises(ValueError):
            sensitivity_analysis(sports_car(), TECHNICAL_CIRCUIT, parameters=["colour"])
        with self.assertRaises(ValueError):
            sensitivity_analysis(sports_car(), TECHNICAL_CIRCUIT, scales=(-0.5,))


if __name__ == "__main__":
    unittest.main()
