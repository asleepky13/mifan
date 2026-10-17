import unittest

from racelab.parts import CATEGORIES, DEFAULT_PARTS, PARTS, PARTS_BY_CATEGORY, Part, apply_parts
from racelab.simulation import simulate_lap
from racelab.summary import car_from_setup
from racelab.track import CIRCUITS

BASE = car_from_setup(1200, 400, 0.32, 2.2, 1.2, 10)


class PartsTest(unittest.TestCase):
    def test_default_parts_leave_car_unchanged(self):
        defaults = [PARTS_BY_CATEGORY[c][DEFAULT_PARTS[c]] for c in CATEGORIES]
        self.assertEqual(apply_parts(BASE, defaults), BASE)

    def test_every_part_changes_the_lap(self):
        for track in CIRCUITS:
            base = simulate_lap(BASE, track)
            for part in PARTS:
                if part.key == DEFAULT_PARTS[part.category]:
                    continue
                lap = simulate_lap(apply_parts(BASE, [part]), track)
                with self.subTest(track=track.name, part=part.name):
                    self.assertTrue(lap.converged and lap.constraints_satisfied)
                    self.assertGreater(abs(lap.lap_time_s - base.lap_time_s), 0.01)
                    self.assertFalse((lap.speed_mps == base.speed_mps).all())

    def test_effects_stack_and_are_physical(self):
        car = apply_parts(BASE, [PARTS_BY_CATEGORY["engine"]["turbo"], PARTS_BY_CATEGORY["wheels"]["slick"]])
        self.assertAlmostEqual(car.power_w, BASE.power_w * 1.25)
        self.assertAlmostEqual(car.mass_kg, BASE.mass_kg + 50)
        self.assertAlmostEqual(car.tire_friction, BASE.tire_friction * 1.12)
        turbo = simulate_lap(apply_parts(BASE, [PARTS_BY_CATEGORY["engine"]["turbo"]]), CIRCUITS[0])
        self.assertGreater(turbo.max_speed_mps, simulate_lap(BASE, CIRCUITS[0]).max_speed_mps)

    def test_rejects_bad_parts(self):
        with self.assertRaises(ValueError):
            Part("x", "X", "spoiler")
        turbo, light = PARTS_BY_CATEGORY["engine"]["turbo"], PARTS_BY_CATEGORY["engine"]["light"]
        with self.assertRaises(ValueError):
            apply_parts(BASE, [turbo, light])

    def test_describe_lists_effects(self):
        self.assertEqual(PARTS_BY_CATEGORY["engine"]["turbo"].describe(), "+40 kg · power ×1.25")
        self.assertEqual(PARTS_BY_CATEGORY["body"]["kart"].describe(), "baseline")


if __name__ == "__main__":
    unittest.main()
