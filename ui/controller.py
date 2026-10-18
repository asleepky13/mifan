"""Arduino controller: a 16x2 I2C LCD, a joystick with push button and a knob, over USB serial.

The Arduino only reads its inputs and draws the text it is sent; all state lives here.

Protocol (newline-terminated ASCII, 115200 baud):
- Arduino -> PC, every 20 ms: ``<knob>,<joy_x>,<joy_y>,<button>`` with readings 0-1023
  and button 0 while pressed (``INPUT_PULLUP``).
- PC -> Arduino: ``L|<line 1>|<line 2>``, 16 characters each. Bytes 1-5 are the bar
  glyphs (1 to 5 lit columns) the sketch registers with ``createChar``.

Controls:
- Button: switch between RACE (live speed, lap and tyres on the LCD) and TUNE.
- TUNE: joystick up/down picks a setting. The knob sets it across that slider's range,
  but only after it has been turned, so picking a setting never makes its value jump.
  Joystick left/right nudges it by one slider step.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Sequence

ADC_MAX = 1023
JOY_LOW, JOY_HIGH = 300, 700  # outside this band the stick counts as pushed
KNOB_PICKUP = 24  # counts the knob must move before it takes over a setting
HUD_TIMEOUT_S = 2.0  # live readout from the track view counts as stale after this
LCD_WIDTH = 16


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    """Short LCD name (fits with the counter on one line)."""
    unit: str
    lo: float
    hi: float
    step: float

    def snap(self, value: float) -> float:
        """Nearest slider position, clamped to the range, as int for integer sliders."""
        steps = round((min(max(value, self.lo), self.hi) - self.lo) / self.step)
        v = round(min(self.lo + steps * self.step, self.hi), 6)
        return int(v) if all(float(x).is_integer() for x in (self.lo, self.hi, self.step)) else v

    def text(self, value: float) -> str:
        decimals = max(0, len(f"{self.step:g}".partition(".")[2]))
        return f"{value:.{decimals}f} {self.unit}".strip()


def parse_inputs(line: str) -> tuple[int, int, int, int] | None:
    """``"512,510,505,1"`` -> (knob, joy_x, joy_y, button); ``None`` for anything else."""
    parts = line.strip().split(",")
    if len(parts) != 4:
        return None
    try:
        knob, jx, jy, button = (int(p) for p in parts)
    except ValueError:
        return None
    if not all(0 <= v <= ADC_MAX for v in (knob, jx, jy)) or button not in (0, 1):
        return None
    return knob, jx, jy, button


def bar(fraction: float, cells: int) -> str:
    """A ``cells``-wide bar using the sketch's glyphs 1-5 (lit columns per cell)."""
    lit = round(min(max(fraction, 0.0), 1.0) * cells * 5)
    full, part = divmod(lit, 5)
    return (chr(5) * full + (chr(part) if part else "")).ljust(cells)


def fit(text: str) -> str:
    return text[:LCD_WIDTH].ljust(LCD_WIDTH)


class Controller:
    """Turns raw input frames into setting changes, and app state into LCD lines. Thread-safe."""

    def __init__(self, settings: Sequence[Setting]):
        self.settings = tuple(settings)
        self._lock = threading.Lock()
        self.mode = "RACE"
        self.index = 0
        self.values = {s.key: s.lo for s in self.settings}
        self._pending: dict[str, float] = {}
        self._button = 1
        self._stick_y = self._stick_x = 0  # -1 / 0 / +1, for edge detection
        self._anchor: int | None = None
        self._armed = False
        self._hud: dict | None = None
        self._hud_at = 0.0
        self._summary: tuple[float, str, int] | None = None

    @property
    def setting(self) -> Setting:
        return self.settings[self.index]

    def _select(self, knob: int) -> None:
        self._anchor, self._armed = knob, False

    def _set(self, setting: Setting, value: float) -> None:
        value = setting.snap(value)
        if value != self.values[setting.key]:
            self.values[setting.key] = value
            self._pending[setting.key] = value

    def feed(self, line: str) -> bool:
        """Apply one input frame from the Arduino; False if the line is not one."""
        frame = parse_inputs(line)
        if frame is None:
            return False
        knob, jx, jy, button = frame
        stick = lambda v: -1 if v < JOY_LOW else 1 if v > JOY_HIGH else 0
        with self._lock:
            if self._button == 1 and button == 0:  # press
                self.mode = "TUNE" if self.mode == "RACE" else "RACE"
                self._select(knob)
            self._button = button
            y, x = stick(jy), stick(jx)
            if self.mode == "TUNE":
                if y and not self._stick_y:
                    self.index = (self.index + y) % len(self.settings)
                    self._select(knob)
                if x and not self._stick_x:
                    self._set(self.setting, self.values[self.setting.key] + x * self.setting.step)
                if self._anchor is not None and abs(knob - self._anchor) > KNOB_PICKUP:
                    self._armed = True
                if self._armed:
                    s = self.setting
                    self._set(s, s.lo + knob / ADC_MAX * (s.hi - s.lo))
            self._stick_y, self._stick_x = y, x
        return True

    def sync(self, values: dict[str, float]) -> None:
        """Current app values (sliders moved in the browser, Reset); unsent changes win."""
        with self._lock:
            for key, value in values.items():
                if key in self.values and key not in self._pending:
                    self.values[key] = value

    def has_changes(self) -> bool:
        with self._lock:
            return bool(self._pending)

    def take_changes(self) -> dict[str, float]:
        with self._lock:
            changes, self._pending = self._pending, {}
            return changes

    def set_hud(self, hud: dict, now: float | None = None) -> None:
        """Live readout posted by the track view: speed (km/h), lap, tyres (0-1), tyre, status."""
        with self._lock:
            self._hud, self._hud_at = hud, time.monotonic() if now is None else now

    def set_summary(self, lap_time_s: float, tyre: str, laps_per_set: int) -> None:
        with self._lock:
            self._summary = (lap_time_s, tyre, laps_per_set)

    def lcd(self, now: float | None = None) -> tuple[str, str]:
        now = time.monotonic() if now is None else now
        with self._lock:
            if self.mode == "TUNE":
                s, value = self.setting, self.values[self.setting.key]
                counter = f"{self.index + 1}/{len(self.settings)}"
                head = f">{s.label}"
                return (fit(head + counter.rjust(LCD_WIDTH - len(head))),
                        fit(s.text(value).ljust(9) + bar((value - s.lo) / (s.hi - s.lo), 7)))
            hud = self._hud if self._hud and now - self._hud_at <= HUD_TIMEOUT_S else None
            if hud:
                tyres = float(hud.get("tyres", 0))
                top = "TYRE CHANGE" if str(hud.get("status", "")).startswith("Tyre change") else f"{int(hud.get('speed', 0)):>3}km/h"
                return (fit(f"{top:<10}L{int(hud.get('lap', 1))}"),
                        fit(f"{str(hud.get('tyre', 'Tyre'))[:4]} {round(tyres * 100):>3}% " + bar(tyres, 6)))
            if self._summary:
                lap_time, tyre, laps = self._summary
                return fit(f"LAP {lap_time:.2f}s"), fit(f"{tyre} {laps} laps")
            return fit("RaceLab"), fit("Press START")


class ArduinoLink:
    """Background thread: reads input frames into a ``Controller`` and keeps the LCD up to date.

    Reconnects every 2 s while the port is missing or fails. ``opener(port, baud)`` returns
    an object with ``readline()``, ``write(bytes)`` and ``close()`` (pyserial by default).
    """

    def __init__(self, port: str, controller: Controller, baud: int = 115200,
                 opener: Callable | None = None, lcd_period_s: float = 0.1):
        self.port, self.controller, self.baud = port, controller, baud
        self._opener = opener or _open_serial
        self._lcd_period = lcd_period_s
        self.status = "Connecting…"
        self.frames = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"arduino-{port}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                link = self._opener(self.port, self.baud)
            except Exception as exc:  # missing port, permission, unplugged
                self.status = f"Not connected: {exc}"
                self._stop.wait(2.0)
                continue
            self.status = "Connected"
            sent, sent_at = None, 0.0
            try:
                while not self._stop.is_set():
                    line = link.readline()
                    if line and self.controller.feed(line.decode("ascii", "ignore")):
                        self.frames += 1
                    now = time.monotonic()
                    lines = self.controller.lcd(now)
                    # Rate-limited on change, and resent every second in case the board reset.
                    if (lines != sent and now - sent_at >= self._lcd_period) or now - sent_at > 1.0:
                        link.write(("L|" + "|".join(lines) + "\n").encode("latin-1"))
                        sent, sent_at = lines, now
            except Exception as exc:
                self.status = f"Disconnected: {exc}"
            finally:
                try:
                    link.close()
                except Exception:
                    pass
            self._stop.wait(2.0)


def _open_serial(port: str, baud: int):
    import serial  # pyserial; imported here so the app runs without it

    return serial.Serial(port, baud, timeout=0.05)


class HudServer:
    """Local HTTP endpoint the track view posts its live readout to: ``POST /hud`` with JSON."""

    def __init__(self, controller: Controller, host: str = "127.0.0.1", port: int = 8765):
        ctrl = controller

        class Handler(BaseHTTPRequestHandler):
            def _cors(self) -> None:
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")

            def do_OPTIONS(self) -> None:  # noqa: N802 (http.server naming)
                self.send_response(204)
                self._cors()
                self.end_headers()

            def do_POST(self) -> None:  # noqa: N802
                try:
                    body = self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 4096))
                    hud = json.loads(body)
                    if self.path != "/hud" or not isinstance(hud, dict):
                        raise ValueError
                except ValueError:
                    self.send_response(400)
                else:
                    ctrl.set_hud(hud)
                    self.send_response(204)
                self._cors()
                self.end_headers()

            def log_message(self, *args) -> None:  # keep the console quiet
                pass

        self._server = ThreadingHTTPServer((host, port), Handler)
        self.url = f"http://{host}:{self._server.server_address[1]}/hud"
        threading.Thread(target=self._server.serve_forever, name="hud-server", daemon=True).start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
