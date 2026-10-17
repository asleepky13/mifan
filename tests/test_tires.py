import unittest

from racelab.car import Car
from racelab.geometry import build_geometry, build_racing_line
from racelab.simulation import simulate_lap
from racelab.tires import CHANGE_AT_DURABILITY, TYRE_CHANGE_S, grip_factor, tyre_stint, tyre_work_g_km
from racelab.track import CIRCUITS, MONACO, MONZA

CAR = Car("App", 1200, 400 * 745.7, 0.32, 2.2, 1.2, 10, 12000, 0.88)


class TyreTest(unittest.TestCase):
    def test_grip_falls_as_durability_falls(self):
        self.assertEqual(grip_factor(1.0), 1.0)
        self.assertAlmostEqual(grip_factor(0.0), 0.85)
        self.assertGreater(grip_factor(0.7), grip_factor(0.4))
        with self.assertRaises(ValueError):
            grip_factor(1.2)

    def test_tyre_work_is_positive_and_highest_per_km_at_monaco(self):
        per_km = {}
        for track in CIRCUITS:
            work = tyre_work_g_km(simulate_lap(CAR, track))
            self.assertGreater(work, 0)
            per_km[track.name] = work / track.total_length_m
        self.assertEqual(max(per_km, key=per_km.get), MONACO.name)

    def test_invalid_settings_rejected(self):
        for kwargs in ({"change_at": 0}, {"change_at": 1}, {"change_s": -1.0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                tyre_stint(CAR, MONZA, **kwargs)


class StintTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stint = tyre_stint(CAR, MONZA, racing_line=build_racing_line(build_geometry(MONZA)))

    def test_tyres_are_changed_when_durability_is_low(self):
        laps = self.stint.laps
        self.assertGreater(len(laps), 2)
        self.assertLessEqual(laps[-1].durability_end, CHANGE_AT_DURABILITY)
        for lap, nxt in zip(laps, laps[1:]):
            self.assertGreater(lap.durability_end, CHANGE_AT_DURABILITY)
            self.assertEqual(nxt.durability_start, lap.durability_end)
            self.assertLess(lap.durability_end, lap.durability_start)
        self.assertEqual(laps[0].durability_start, 1.0)
        self.assertEqual(self.stint.change_s, TYRE_CHANGE_S)

    def test_first_lap_starts_and_last_lap_ends_at_a_standstill(self):
        first, last = self.stint.laps[0].result, self.stint.laps[-1].result
        self.assertEqual(first.speed_mps[0], 0.0)
        self.assertEqual(last.finish_speed_mps, 0.0)
        self.assertGreater(min(l.result.speed_mps[0] for l in self.stint.laps[1:]), 30)  # flying laps in between
        total = sum(l.result.lap_time_s for l in self.stint.laps)
        self.assertAlmostEqual(self.stint.cycle_time_s, total + TYRE_CHANGE_S)

    def test_flying_laps_get_slower_as_tyres_wear(self):
        times = [l.result.lap_time_s for l in self.stint.laps[1:-1]]
        self.assertEqual(times, sorted(times))
        self.assertGreater(times[-1], times[0])


if __name__ == "__main__":
    unittest.main()
