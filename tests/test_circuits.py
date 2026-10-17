import unittest

from racelab.geometry import build_geometry
from racelab.track import BAHRAIN, CIRCUITS, ENVIRONMENTS, Segment, Track


class CircuitTest(unittest.TestCase):
    def test_every_circuit_has_its_own_environment(self):
        self.assertEqual(sorted(t.environment for t in CIRCUITS), sorted(ENVIRONMENTS))

    def test_bahrain_closes_and_matches_the_real_length(self):
        g = build_geometry(BAHRAIN)
        self.assertLess(g.closure_error_m, 0.1)
        self.assertLess(g.heading_closure_error_rad, 1e-9)
        self.assertAlmostEqual(BAHRAIN.total_length_m / 1000, 5.412, delta=0.01)

    def test_unknown_environment_rejected(self):
        with self.assertRaises(ValueError):
            Track("moon", (Segment(100),), environment="lunar")


if __name__ == "__main__":
    unittest.main()
