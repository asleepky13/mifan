import json
import time
import unittest
import urllib.request

from ui.controller import (
    KNOB_PICKUP,
    ArduinoLink,
    Controller,
    HudServer,
    Setting,
    bar,
    parse_inputs,
)

SETTINGS = [Setting("mass_kg", "Mass", "kg", 800, 1800, 10), Setting("tire_friction", "Tyre grip", "", 0.8, 2.0, 0.05)]
MID = 512


def frame(knob=MID, jx=MID, jy=MID, button=1) -> str:
    return f"{knob},{jx},{jy},{button}"


def tuning() -> Controller:
    c = Controller(SETTINGS)
    c.sync({"mass_kg": 1200, "tire_friction": 1.2})
    c.feed(frame())
    c.feed(frame(button=0))  # press: RACE -> TUNE
    c.feed(frame())
    return c


class ProtocolTest(unittest.TestCase):
    def test_parse_inputs(self):
        self.assertEqual(parse_inputs("512,0,1023,1\r\n"), (512, 0, 1023, 1))
        for bad in ("", "1,2,3", "1,2,3,4,5", "a,2,3,1", "1024,2,3,1", "1,2,3,2", "L|text|text"):
            with self.subTest(bad=bad):
                self.assertIsNone(parse_inputs(bad))

    def test_bar_uses_partial_glyphs(self):
        self.assertEqual(bar(1.0, 3), chr(5) * 3)
        self.assertEqual(bar(0.0, 3), "   ")
        self.assertEqual(bar(0.5, 2), chr(5) + " ")
        self.assertEqual(bar(7 / 15, 3), chr(5) + chr(2) + " ")  # 7 of 15 columns lit

    def test_setting_snaps_to_slider_positions(self):
        mass, grip = SETTINGS
        self.assertEqual(mass.snap(1234.0), 1230)
        self.assertIsInstance(mass.snap(1234.0), int)
        self.assertEqual(mass.snap(5000), 1800)
        self.assertEqual(grip.snap(1.2312), 1.25)
        self.assertEqual((mass.text(1200), grip.text(1.25)), ("1200 kg", "1.25"))


class ControllerTest(unittest.TestCase):
    def test_button_press_toggles_mode_once_per_press(self):
        c = Controller(SETTINGS)
        c.feed(frame())
        for _ in range(5):
            c.feed(frame(button=0))  # held down
        self.assertEqual(c.mode, "TUNE")
        c.feed(frame(button=1))
        c.feed(frame(button=0))
        self.assertEqual(c.mode, "RACE")

    def test_joystick_picks_settings_with_wrap_around(self):
        c = tuning()
        c.feed(frame(jy=900))
        c.feed(frame(jy=900))  # still pushed: one step only
        self.assertEqual(c.setting.key, "tire_friction")
        c.feed(frame())
        c.feed(frame(jy=900))
        self.assertEqual(c.setting.key, "mass_kg")  # wrapped
        c.feed(frame())
        c.feed(frame(jy=100))
        self.assertEqual(c.setting.key, "tire_friction")

    def test_knob_takes_over_only_after_it_is_turned(self):
        c = tuning()
        c.feed(frame(knob=MID + KNOB_PICKUP - 1))  # jitter: ignored
        self.assertEqual(c.take_changes(), {})
        c.feed(frame(knob=1023))
        self.assertEqual(c.take_changes(), {"mass_kg": 1800})
        c.feed(frame(knob=0))
        self.assertEqual(c.take_changes(), {"mass_kg": 800})
        c.feed(frame(knob=0))
        self.assertEqual(c.take_changes(), {})  # unchanged: nothing to send

    def test_switching_setting_needs_a_new_turn(self):
        c = tuning()
        c.feed(frame(knob=1023))
        c.take_changes()
        c.feed(frame(knob=1023, jy=900))  # pick grip with the knob at full
        c.feed(frame(knob=1023))
        self.assertEqual(c.take_changes(), {})  # grip did not jump to 2.0
        c.feed(frame(knob=400))
        self.assertEqual(c.take_changes(), {"tire_friction": 0.8 + round(400 / 1023 * 1.2 / 0.05) * 0.05})

    def test_joystick_x_nudges_one_step_and_clamps(self):
        c = tuning()
        c.feed(frame(jx=900))
        c.feed(frame(jx=900))  # held: one step
        c.feed(frame())
        c.feed(frame(jx=100))
        c.feed(frame())
        c.feed(frame(jx=100))
        self.assertEqual(c.take_changes(), {"mass_kg": 1190})
        c.sync({"mass_kg": 800})
        c.feed(frame())
        c.feed(frame(jx=100))
        self.assertEqual(c.take_changes(), {})  # already at the minimum

    def test_race_mode_ignores_tuning_inputs(self):
        c = Controller(SETTINGS)
        c.sync({"mass_kg": 1200, "tire_friction": 1.2})
        for f in (frame(knob=0), frame(knob=1023, jx=900, jy=900)):
            c.feed(f)
        self.assertEqual((c.mode, c.index, c.take_changes()), ("RACE", 0, {}))

    def test_sync_keeps_unsent_changes(self):
        c = tuning()
        c.feed(frame(knob=1023))
        c.sync({"mass_kg": 1200})
        self.assertTrue(c.has_changes())
        self.assertEqual(c.take_changes(), {"mass_kg": 1800})
        c.sync({"mass_kg": 1500})  # moved in the browser
        self.assertEqual(c.values["mass_kg"], 1500)

    def test_lcd_lines(self):
        c = tuning()
        top, bottom = c.lcd()
        self.assertEqual(top, ">Mass" + " " * 8 + "1/2")
        self.assertTrue(bottom.startswith("1200 kg"))
        self.assertEqual(len(bottom), 16)

        r = Controller(SETTINGS)
        self.assertEqual(r.lcd(), ("RaceLab".ljust(16), "Press START".ljust(16)))
        r.set_summary(106.931, "Medium", 25)
        self.assertEqual(r.lcd(), ("LAP 106.93s".ljust(16), "Medium 25 laps".ljust(16)))
        r.set_hud({"speed": 245, "lap": 3, "tyres": 0.78, "tyre": "Soft", "status": "Running"}, now=100.0)
        top, bottom = r.lcd(now=101.0)
        self.assertEqual(top, "245km/h   L3".ljust(16))
        self.assertTrue(bottom.startswith("Soft  78% "))
        r.set_hud({"speed": 0, "lap": 25, "tyres": 0.15, "tyre": "Medium", "status": "Tyre change 1.2 s"}, now=100.0)
        self.assertTrue(r.lcd(now=101.0)[0].startswith("TYRE CHANGE"))
        self.assertEqual(r.lcd(now=103.0)[0], "LAP 106.93s".ljust(16))  # stale readout: summary again


class FakeSerial:
    def __init__(self, lines):
        self.lines, self.written, self.closed = list(lines), [], False

    def readline(self):
        time.sleep(0.005)
        return (self.lines.pop(0) + "\n").encode() if self.lines else b""

    def write(self, data):
        self.written.append(data)

    def close(self):
        self.closed = True


class LinkTest(unittest.TestCase):
    def wait_for(self, condition, timeout=2.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end and not condition():
            time.sleep(0.01)
        self.assertTrue(condition())

    def test_link_feeds_inputs_and_draws_the_lcd(self):
        c = Controller(SETTINGS)
        c.sync({"mass_kg": 1200, "tire_friction": 1.2})
        fake = FakeSerial([frame(), frame(button=0), frame(), "garbage", frame(knob=1023)])
        link = ArduinoLink("fake", c, opener=lambda port, baud: fake, lcd_period_s=0.0)
        try:
            self.wait_for(lambda: c.has_changes())
            self.assertEqual(c.take_changes(), {"mass_kg": 1800})
            self.assertEqual(link.frames, 4)
            self.assertEqual(link.status, "Connected")
            self.wait_for(lambda: any(w.startswith(b"L|>Mass") for w in fake.written))
            self.assertTrue(all(len(w.decode("latin-1").rstrip("\n").split("|")[1]) == 16 for w in fake.written))
        finally:
            link.stop()

    def test_missing_port_reports_and_retries(self):
        def opener(port, baud):
            raise OSError("no such port")
        link = ArduinoLink("/dev/nothing", Controller(SETTINGS), opener=opener)
        try:
            self.wait_for(lambda: link.status.startswith("Not connected: no such port"))
        finally:
            link.stop()


class HudServerTest(unittest.TestCase):
    def test_track_view_readout_reaches_the_controller(self):
        c = Controller(SETTINGS)
        server = HudServer(c, port=0)
        try:
            body = json.dumps({"speed": 199, "lap": 2, "tyres": 0.5, "tyre": "Hard", "status": "Running"}).encode()
            with urllib.request.urlopen(urllib.request.Request(server.url, data=body, method="POST")) as r:
                self.assertEqual(r.status, 204)
                self.assertEqual(r.headers["Access-Control-Allow-Origin"], "*")
            self.assertTrue(c.lcd()[0].startswith("199km/h"))
            bad = urllib.request.Request(server.url, data=b"not json", method="POST")
            with self.assertRaises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(bad)
            self.assertEqual(err.exception.code, 400)
        finally:
            server.close()


if __name__ == "__main__":
    unittest.main()
