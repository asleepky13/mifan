import unittest
from dataclasses import replace

from racelab.car import Car
from racelab.geometry import build_geometry, build_racing_line
from racelab.simulation import simulate_lap
from racelab.tires import (
    CHANGE_AT_DURABILITY,
    HARD,
    INTERMEDIATE,
    MEDIUM,
    SOFT,
    TYRE_CHANGE_S,
    TYRES,
    Tyre,
    grip_factor,
    tyre_stint,
    tyre_work_g_km,
)
from racelab.track import CIRCUITS, MONACO, MONZA, SLICK_GRIP_LOSS_PER_WATER, WEATHER, Weather

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


class PirelliCalibrationTest(unittest.TestCase):
    """The tyres reproduce the published figures they were fitted to (module docstring)."""

    @classmethod
    def setUpClass(cls):
        cls.lines = {t.name: build_racing_line(build_geometry(t)) for t in CIRCUITS}

    def mean_ratio(self, factor: float) -> float:
        lap = lambda t, f: simulate_lap(replace(CAR, tire_friction=CAR.tire_friction * f), t, racing_line=self.lines[t.name]).lap_time_s
        return sum(lap(t, factor) / lap(t, 1.0) for t in CIRCUITS) / len(CIRCUITS)

    def test_about_one_percent_of_lap_time_between_compounds(self):
        self.assertAlmostEqual(self.mean_ratio(SOFT.dry_grip), 0.99, delta=0.001)
        self.assertAlmostEqual(self.mean_ratio(HARD.dry_grip), 1.01, delta=0.001)

    def test_wet_weather_crossovers(self):
        crossover = Weather("crossover", 1 - SLICK_GRIP_LOSS_PER_WATER)  # water 1
        self.assertAlmostEqual(self.mean_ratio(MEDIUM.grip(crossover)), 1.11, delta=0.002)       # slicks at 110-112%
        self.assertAlmostEqual(INTERMEDIATE.grip(crossover), MEDIUM.grip(crossover), places=3)   # ... where inters match them
        self.assertAlmostEqual(self.mean_ratio(INTERMEDIATE.grip(WEATHER[0])), 1.06, delta=0.002)  # inters cost 5-6 s when dry
        best = {w.name: max(TYRES, key=lambda t: t.grip(w)).name for w in WEATHER}
        self.assertEqual(best, {"Dry": "Soft", "Damp": "Soft", "Wet": "Intermediate", "Heavy rain": "Wet"})

    def test_monza_stint_lengths_match_pirelli_pit_windows(self):
        laps = {t.name: len(tyre_stint(CAR, MONZA, t, racing_line=self.lines[MONZA.name]).laps) for t in (SOFT, MEDIUM, HARD)}
        self.assertEqual(laps, {"Soft": 18, "Medium": 25, "Hard": 31})

    def test_sidewall_colours(self):
        self.assertEqual([t.color_hex for t in TYRES], ["#DA291C", "#FFD100", "#F0F0F0", "#43B02A", "#0067AD"])
        with self.assertRaises(ValueError):
            Tyre("Glass", "#000000", 1.0, 1.2, 0.01)


if __name__ == "__main__":
    unittest.main()
