import re
import unittest

from streamlit.testing.v1 import AppTest


def lap_time(at: AppTest) -> str:
    stats = next(m.value for m in at.markdown if m.value.startswith('<div class="rl-stats">'))
    return re.search(r'class="rl-value">([^<]+)<', stats).group(1)


class AppTestCase(unittest.TestCase):
    def test_slider_updates_results_and_reset_restores_default(self):
        at = AppTest.from_file("../app.py", default_timeout=30).run()
        self.assertFalse(at.exception)
        default = lap_time(at)

        at.slider(key="power_hp").set_value(800).run()
        self.assertNotEqual(lap_time(at), default)
        self.assertLess(float(lap_time(at)), float(default))

        at.button[0].click().run()
        self.assertEqual(at.slider(key="power_hp").value, 400)
        self.assertEqual(lap_time(at), default)

    def test_garage_part_changes_lap_and_reset_restores_it(self):
        at = AppTest.from_file("../app.py", default_timeout=30).run()
        default = lap_time(at)
        at.selectbox(key="part_engine").set_value("turbo").run()
        self.assertFalse(at.exception)
        self.assertNotEqual(lap_time(at), default)
        at.button[0].click().run()
        self.assertEqual(at.selectbox(key="part_engine").value, "standard")
        self.assertEqual(lap_time(at), default)

    def test_race_strategy_pits_and_reset_restores_it(self):
        at = AppTest.from_file("../app.py", default_timeout=60).run()
        race = lambda: next(m.value for m in at.markdown if "Pit stops" in m.value)
        self.assertIn("After lap", race())  # 20 laps on Mediums needs a stop
        default = lap_time(at)
        at.selectbox(key="start_compound").set_value("Soft").run()
        self.assertFalse(at.exception)
        self.assertLess(float(lap_time(at)), float(default))  # more grip on fresh softs
        at.slider(key="race_laps").set_value(3).run()
        self.assertIn("No stop needed", race())
        at.button[0].click().run()
        self.assertEqual((at.selectbox(key="start_compound").value, at.slider(key="race_laps").value), ("Medium", 20))
        self.assertEqual(lap_time(at), default)

    def test_every_slider_extreme_renders(self):
        at = AppTest.from_file("../app.py", default_timeout=30).run()
        for slider in at.slider:
            original = slider.value
            for value in (slider.min, slider.max):
                slider.set_value(value).run()
                with self.subTest(slider=slider.key, value=value):
                    self.assertFalse(at.exception)
                    self.assertTrue(any(m.value.startswith('<div class="rl-stats">') for m in at.markdown))
            slider.set_value(original).run()


if __name__ == "__main__":
    unittest.main()
