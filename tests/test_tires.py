import unittest

from racelab.car import Car
from racelab.geometry import build_geometry
from racelab.simulation import simulate_lap
from racelab.tires import (
    COMPOUNDS_BY_NAME,
    PIT_THRESHOLD,
    Compound,
    grip_factor,
    simulate_race,
    tyre_work_g_km,
)
from racelab.track import CIRCUITS, MONACO, MONZA

CAR = Car("App", 1200, 400 * 745.7, 0.32, 2.2, 1.2, 10, 12000, 0.88)
SOFT, MEDIUM, HARD = (COMPOUNDS_BY_NAME[n] for n in ("Soft", "Medium", "Hard"))


class TyreTest(unittest.TestCase):
    def test_grip_falls_with_wear(self):
        self.assertEqual(grip_factor(0.0), 1.0)
        self.assertAlmostEqual(grip_factor(1.0), 0.85)
        self.assertGreater(grip_factor(0.3), grip_factor(0.6))
        with self.assertRaises(ValueError):
            grip_factor(1.2)

    def test_tyre_work_is_positive_and_highest_per_km_at_monaco(self):
        per_km = {}
        for track in CIRCUITS:
            work = tyre_work_g_km(simulate_lap(CAR, track), build_geometry(track))
            self.assertGreater(work, 0)
            per_km[track.name] = work / track.total_length_m
        self.assertEqual(max(per_km, key=per_km.get), MONACO.name)

    def test_invalid_compound_and_race_rejected(self):
        with self.assertRaises(ValueError):
            Compound("Glass", 1.0, 0.0)
        g = build_geometry(MONZA)
        for kwargs in ({"laps": 0}, {"laps": 5, "pit_threshold": 0}, {"laps": 5, "pit_loss_s": -1.0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                simulate_race(CAR, MONZA, g, start=MEDIUM, pit_to=MEDIUM, **kwargs)


class RaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.geometry = build_geometry(MONZA)

    def race(self, laps, start, pit_to=MEDIUM):
        return simulate_race(CAR, MONZA, self.geometry, laps, start, pit_to)

    def test_pits_when_tyres_are_low_and_leaves_on_fresh_tyres(self):
        result = self.race(20, SOFT, HARD)
        self.assertGreaterEqual(result.pit_stops, 1)
        for lap, nxt in zip(result.laps, result.laps[1:]):
            if lap.pit_after:
                self.assertGreaterEqual(lap.wear_end, PIT_THRESHOLD)
                self.assertEqual((nxt.wear_start, nxt.compound), (0.0, "Hard"))
            else:
                self.assertLess(lap.wear_end, PIT_THRESHOLD)
                self.assertEqual(nxt.wear_start, lap.wear_end)
        self.assertFalse(result.laps[-1].pit_after)  # never pit after the flag
        self.assertAlmostEqual(result.total_time_s, sum(l.lap_time_s for l in result.laps) + 22.0 * result.pit_stops)

    def test_laps_get_slower_as_tyres_wear(self):
        stint = [l for l in self.race(6, MEDIUM).laps]
        times = [l.lap_time_s for l in stint]
        self.assertEqual(times, sorted(times))
        self.assertGreater(times[-1], times[0])

    def test_compounds_trade_pace_for_life(self):
        soft, hard = self.race(1, SOFT).laps[0], self.race(1, HARD).laps[0]
        self.assertLess(soft.lap_time_s, hard.lap_time_s)  # softer is faster when new
        self.assertGreater(soft.wear_end, hard.wear_end)   # but wears faster
        first_stop = lambda r: next(l.lap for l in r.laps if l.pit_after)
        self.assertLess(first_stop(self.race(25, SOFT)), first_stop(self.race(25, HARD)))

    def test_short_race_needs_no_stop(self):
        self.assertEqual(self.race(3, HARD).pit_stops, 0)


if __name__ == "__main__":
    unittest.main()
