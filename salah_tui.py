import json
import math
import os
import platform
import shutil
import subprocess
import tempfile
import threading
import wave
from datetime import datetime, timedelta
from fractions import Fraction
from pathlib import Path

import httpx
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Digits, Footer, Header, Input, Label, Select, Static

BASE_URL = "https://api.aladhan.com/v1"
GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
CONFIG_PATH = Path.home() / ".salah_tui.json"

KAABA_LAT = 21.4225
KAABA_LON = 39.8262

METHODS: dict[int, str] = {
    3: "Muslim World League (3)",
    13: "Diyanet İşleri Başkanlığı, Turkey (13)",
    2: "Islamic Society of North America - ISNA (2)",
    4: "Umm Al-Qura University, Makkah (4)",
    5: "Egyptian General Authority of Survey (5)",
    1: "University of Islamic Sciences, Karachi (1)",
    12: "Union Organization Islamic de France (12)",
    15: "Moonsighting Committee Worldwide (15)",
}

COMPASS_NAMES = ["N", "NO", "O", "SO", "S", "SW", "W", "NW"]
ROSE_ARROWS = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]
PRAYER_KEYS = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]

ALARM_MODES = ["off", "at_time", "before_23m"]
ALARM_LABELS = {
    "off": "[#6272a4]🔕 Alarm: Off[/]",
    "at_time": "[#50fa7b]🔔 Alarm: At Prayer Time[/]",
    "before_23m": "[#f1fa8c]⏰ Alarm: 23m Before + At Time[/]",
}


def play_synth_chime(kind: str = "prayer") -> None:
    """Synthetisiert einen warmen, knisterfreien Klangschalen-Adhan-Akkord."""

    def _worker() -> None:
        sample_rate = 44100
        pad = int(sample_rate * 0.15)  # 150ms Stille-Vorlauf gegen Audio-Klicks

        if kind == "pre":
            # Variante E: Tiefer Oktav-Klangteppich (23m Voraberinnerung)
            total_dur = 6.1
            notes = [
                (146.83, 0.0, 5.8),
                (293.66, 0.5, 4.8),
                (311.13, 1.3, 3.8),
                (369.99, 2.1, 3.9),
                (440.00, 3.0, 3.0),
            ]
        else:
            # Variante D: Sanfter Hijaz-Ruf & Ausklang (Gebetszeit)
            total_dur = 6.6
            notes = [
                (220.00, 0.0, 5.5),
                (233.08, 0.7, 2.2),
                (277.18, 1.5, 2.4),
                (293.66, 2.4, 3.8),
                (329.63, 3.3, 3.2),
            ]

        buf = [0.0] * (pad + int(sample_rate * total_dur))
        for freq, start, dur in notes:
            start_idx = pad + int(start * sample_rate)
            n_samples = int(sample_rate * dur)
            for i in range(n_samples):
                idx = start_idx + i
                if idx >= len(buf):
                    break
                t = i / sample_rate
                # Weiche Cosinus-S-Kurve für knisterfreies Ein- und Ausblenden
                fade_in = 0.5 * (1.0 - math.cos(math.pi * min(1.0, t / 0.35)))
                fade_out = 0.5 * (1.0 - math.cos(math.pi * min(1.0, (dur - t) / 0.45)))
                env = fade_in * fade_out * math.exp(-0.6 * t)

                val = (
                    0.60 * math.sin(2 * math.pi * freq * t)
                    + 0.35 * math.sin(2 * math.pi * (freq * 1.003) * t)
                    + 0.20 * math.sin(2 * math.pi * (freq * 2.0) * t)
                )
                buf[idx] += val * env

        peak = max((abs(x) for x in buf), default=1.0) or 1.0
        frames = bytearray()
        for x in buf:
            sample = int(max(-1.0, min(1.0, (x / peak) * 0.90)) * 32767)
            frames.extend(sample.to_bytes(2, byteorder="little", signed=True))

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                tmp_path = f.name
            with wave.open(tmp_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(bytes(frames))

            sys_name = platform.system()
            if sys_name == "Darwin" and shutil.which("afplay"):
                subprocess.run(["afplay", tmp_path], check=False)
            elif sys_name == "Linux":
                for player in ("paplay", "pw-play", "aplay"):
                    if shutil.which(player):
                        subprocess.run([player, tmp_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                        break
            elif sys_name == "Windows":
                import winsound
                winsound.PlaySound(tmp_path, winsound.SND_FILENAME)
        except Exception:
            pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    threading.Thread(target=_worker, daemon=True).start()


def send_system_notification(title: str, message: str) -> None:
    """Sendet eine native Desktop-Benachrichtigung ohne externe Pakete."""
    try:
        sys_name = platform.system()
        if sys_name == "Linux" and shutil.which("notify-send"):
            subprocess.Popen(["notify-send", "-a", "Salah TUI", title, message], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys_name == "Darwin" and shutil.which("osascript"):
            script = f'display notification "{message}" with title "{title}"'
            subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def geocode(city: str, country: str) -> tuple[float, float] | None:
    """Koordinaten einer Stadt über Open-Meteo holen. Bevorzugt das passende Land."""
    response = httpx.get(
        GEO_URL,
        params={"name": city, "count": 10, "language": "en", "format": "json"},
        timeout=10.0,
    )
    response.raise_for_status()
    results = response.json().get("results") or []
    if not results:
        return None

    country_l = country.lower()
    for res in results:
        if res.get("country", "").lower() == country_l or res.get("country_code", "").lower() == country_l:
            return res["latitude"], res["longitude"]
    return results["latitude"], results["longitude"]


def qibla_direction(lat: float, lon: float) -> float:
    """Azimut zur Kaaba in Grad (0 = Nord, im Uhrzeigersinn)."""
    phi1 = math.radians(lat)
    phi2 = math.radians(KAABA_LAT)
    dlon = math.radians(KAABA_LON - lon)
    x = math.sin(dlon)
    y = math.cos(phi1) * math.tan(phi2) - math.sin(phi1) * math.cos(dlon)
    return math.degrees(math.atan2(x, y)) % 360


def compass_name(deg: float) -> str:
    return COMPASS_NAMES[round(deg / 45) % 8]


def qibla_line(deg: float) -> str:
    """Einzeilige Qibla-Anzeige: Richtung, Pfeil und Gradzahl."""
    arrow = ROSE_ARROWS[round(deg / 45) % 8]
    name = compass_name(deg)
    colored_name = "".join(
        f"[b #ff5555]{c}[/]" if c == "N" else f"[#8be9fd]{c}[/]"
        for c in name
    )
    return f"{colored_name}  [b #50fa7b]{arrow}[/]  [b #f1fa8c]🕋 {deg:.1f}°[/]"


def sun_arc(
    prayer_times: dict[str, datetime],
    now: datetime,
    selected_prayer: str | None = None,
) -> str:
    """Rendert den 24h-Sonnenverlauf als Unicode-Braille-Kurve im Dracula-Theme."""
    if not prayer_times:
        return ""

    W, H = 56, 5
    HORIZON = 3
    px_w, px_h = W * 2, H * 4
    hy = HORIZON * 4 + 2

    def to_min(dt: datetime) -> float:
        return dt.hour * 60 + dt.minute + dt.second / 60.0

    sr = to_min(prayer_times["Sunrise"])
    mg = to_min(prayer_times["Maghrib"])
    cur = to_min(now)
    day_len = max(1.0, mg - sr)
    night_len = max(1.0, 1440.0 - day_len)

    def y_at(minute: float) -> float:
        if sr <= minute <= mg:
            t = (minute - sr) / day_len
            return hy - math.sin(t * math.pi) * (hy - 1)
        dt = (minute - mg) if minute > mg else (minute + 1440.0 - mg)
        t = dt / night_len
        return hy + math.sin(t * math.pi) * (px_h - 1 - hy)

    bits = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))
    grid = [list(bytes(W)) for _ in range(H)]

    for px in range(px_w):
        py = max(0, min(px_h - 1, round(y_at((px / px_w) * 1440.0))))
        grid[py // 4][px // 2] |= bits[py % 4][px % 2]

    sun_col = max(0, min(W - 1, round((cur / 1440.0) * (W - 1))))
    sun_row = max(0, min(H - 1, round(y_at(cur)) // 4))
    is_day = sr <= cur <= mg

    markers = {
        max(0, min(W - 1, round((to_min(prayer_times[k]) / 1440.0) * (W - 1)))): k
        for k in PRAYER_KEYS
    }

    lines: list[str] = []
    for r in range(H):
        row_chars: list[str] = []
        for c in range(W):
            if r == sun_row and c == sun_col:
                row_chars.append("[b #f1fa8c]☀[/]" if is_day else "[b #bd93f9]☾[/]")
            elif r == HORIZON and c in markers:
                p_name = markers[c]
                if p_name == selected_prayer:
                    row_chars.append("[b #ff79c6]◈[/]")
                else:
                    color = "#f1fa8c" if p_name in ("Sunrise", "Maghrib") else "#50fa7b"
                    row_chars.append(f"[b {color}]◆[/]")
            elif grid[r][c]:
                ch = chr(0x2800 + grid[r][c])
                color = "#f1fa8c" if r < HORIZON else "#6272a4"
                row_chars.append(f"[{color}]{ch}[/]")
            elif r == HORIZON:
                row_chars.append("[#44475a]─[/]")
            else:
                row_chars.append(" ")
        lines.append("".join(row_chars))

    sr_s = prayer_times["Sunrise"].strftime("%H:%M")
    dh_s = prayer_times["Dhuhr"].strftime("%H:%M")
    mg_s = prayer_times["Maghrib"].strftime("%H:%M")
    footer = f"[#6272a4]00:00[/]     [#f1fa8c]🌅 {sr_s}[/]     [#50fa7b]☀ {dh_s}[/]     [#ff79c6]🌇 {mg_s}[/]     [#6272a4]23:59[/]"
    lines.append(footer)
    return "\n".join(lines)


class CityModal(ModalScreen[tuple[str, str, int] | None]):
    """Modal dialog to change city, country, and calculation method."""

    CSS = """
    CityModal {
        align: center middle;
    }

    #dialog {
        width: 56;
        height: auto;
        border: heavy #bd93f9;
        background: #282a36;
        padding: 1 2;
    }

    #dialog Label {
        margin-top: 1;
        color: #8be9fd;
    }

    #buttons {
        margin-top: 2;
        align: right middle;
        height: auto;
    }

    Button {
        margin-left: 1;
    }
    """

    def __init__(self, current_city: str, current_country: str, current_method: int):
        super().__init__()
        self.current_city = current_city
        self.current_country = current_country
        self.current_method = current_method

    def compose(self) -> ComposeResult:
        options = [(label, code) for code, label in METHODS.items()]
        if self.current_method not in METHODS:
            options.insert(0, (f"Custom Method ({self.current_method})", self.current_method))

        with Vertical(id="dialog"):
            yield Static("[b #ff79c6]Change Location & Method[/]")
            yield Label("City:")
            yield Input(value=self.current_city, id="city-input", placeholder="e.g. Zurich")
            yield Label("Country:")
            yield Input(value=self.current_country, id="country-input", placeholder="e.g. Switzerland")
            yield Label("Calculation Method:")
            yield Select(options, value=self.current_method, allow_blank=False, id="method-select")
            with Horizontal(id="buttons"):
                yield Button("Cancel", variant="default", id="cancel")
                yield Button("Save", variant="primary", id="save")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            city = self.query_one("#city-input", Input).value.strip()
            country = self.query_one("#country-input", Input).value.strip()
            method_val = self.query_one("#method-select", Select).value
            if city and country and isinstance(method_val, int):
                self.dismiss((city, country, method_val))
        else:
            self.dismiss(None)


class Salah(App):
    """TUI for Islamic prayer times in Dracula theme."""

    TITLE = "☪ ✦ S A L A H ✦ ☪"

    CSS = """
    Header {
        color: #f1fa8c;
        text-style: bold;
    }

    Screen {
        align: center middle;
    }

    #main-box {
        width: 72;
        height: auto;
        border: heavy #bd93f9;
        padding: 1 2;
    }

    #location-info {
        text-align: center;
        color: #8be9fd;
        text-style: bold;
    }

    #method-info {
        text-align: center;
        color: #bd93f9;
        margin-bottom: 1;
    }

    #qibla-rose {
        text-align: center;
    }

    #alarm-info {
        text-align: center;
        margin-bottom: 1;
    }

    #next-prayer-label {
        text-align: center;
        color: #f8f8f2;
    }

    #countdown {
        text-align: center;
        color: #ff79c6;
        margin: 1 0;
    }

    DataTable {
        height: auto;
        margin-top: 1;
        background: transparent;
    }

    DataTable > .datatable--header {
        background: transparent;
        color: #8be9fd;
        text-style: bold;
    }

    DataTable > .datatable--odd-row,
    DataTable > .datatable--even-row {
        background: transparent;
    }

    DataTable > .datatable--cursor {
        background: #44475a;
        color: #f8f8f2;
        text-style: bold;
    }

    #sun-arc {
        text-align: center;
        margin-top: 1;
        height: auto;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("c", "change_city", "Location"),
        ("n", "cycle_alarm", "Alarm"),
        ("s", "save_config", "Save"),
        ("r", "refresh_times", "Refresh"),
    ]

    def __init__(self, city: str = "Zurich", country: str = "Switzerland", method: int = 3):
        super().__init__()
        alarm_mode = "off"
        if CONFIG_PATH.exists():
            try:
                saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                city = saved.get("city", city)
                country = saved.get("country", country)
                method = saved.get("method", method)
                if saved.get("alarm_mode") in ALARM_MODES:
                    alarm_mode = saved["alarm_mode"]
            except Exception:
                pass
        self.city = city
        self.country = country
        self.method = method
        self.alarm_mode: str = alarm_mode
        self.method_name: str = ""
        self.prayer_times: dict[str, datetime] = {}
        self.hijri_date: str = ""
        self.qibla: float | None = None
        self.coords_cache: dict[tuple[str, str], tuple[float, float]] = {}
        self.selected_prayer: str = "Fajr"
        self._last_sun_state: tuple[int, str] | None = None
        self._user_scrolled: bool = False
        self._last_next_prayer: str | None = None
        self._programmatic_move: bool = False
        self._triggered_alarms: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="main-box"):
            yield Static("Loading prayer times...", id="location-info")
            yield Static("", id="method-info")
            yield Static("", id="qibla-rose")
            yield Static(ALARM_LABELS[self.alarm_mode], id="alarm-info")
            yield Static("", id="next-prayer-label")
            yield Digits("00:00:00", id="countdown")
            yield DataTable(id="times-table", cursor_type="row")
            yield Static("", id="sun-arc")
        yield Footer()

    def on_mount(self) -> None:
        self.theme = "dracula"
        table = self.query_one(DataTable)
        table.add_columns("Prayer", "Time", "Status", "Span", "Ratio", "Share")
        table.focus()
        self.fetch_prayer_times()
        self.set_interval(1.0, self.update_countdown)

    def action_refresh_times(self) -> None:
        self._last_sun_state = None
        self.fetch_prayer_times()

    def action_cycle_alarm(self) -> None:
        idx = (ALARM_MODES.index(self.alarm_mode) + 1) % len(ALARM_MODES)
        self.alarm_mode = ALARM_MODES[idx]
        self.query_one("#alarm-info", Static).update(ALARM_LABELS[self.alarm_mode])
        if self.alarm_mode == "at_time":
            play_synth_chime("prayer")
            self.notify("Reminder set: At prayer time", title="Alarm Mode")
        elif self.alarm_mode == "before_23m":
            play_synth_chime("pre")
            self.notify("Reminder set: 23 min before + at prayer time", title="Alarm Mode")
        else:
            self.notify("Prayer reminders turned off", title="Alarm Mode")

    def action_save_config(self) -> None:
        data = {
            "city": self.city,
            "country": self.country,
            "method": self.method,
            "alarm_mode": self.alarm_mode,
        }
        CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.notify(
            f"Saved: {self.city}, {self.country} (Method #{self.method}, Alarm: {self.alarm_mode})",
            title="Settings Saved",
        )

    def action_change_city(self) -> None:
        def handle_city_result(result: tuple[str, str, int] | None) -> None:
            if result:
                self.city, self.country, self.method = result
                self._last_sun_state = None
                self._triggered_alarms.clear()
                self.fetch_prayer_times()

        self.push_screen(CityModal(self.city, self.country, self.method), handle_city_result)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if self._programmatic_move:
            return
        self._user_scrolled = True
        if 0 <= event.cursor_row < len(PRAYER_KEYS):
            self.selected_prayer = PRAYER_KEYS[event.cursor_row]
            self._last_sun_state = None
            if self.prayer_times:
                self.query_one("#sun-arc", Static).update(
                    sun_arc(self.prayer_times, datetime.now(), self.selected_prayer)
                )

    def get_coords(self) -> tuple[float, float] | None:
        """Koordinaten der aktuellen Stadt, mit Cache pro Stadt und Land."""
        key = (self.city.lower(), self.country.lower())
        if key not in self.coords_cache:
            coords = geocode(self.city, self.country)
            if coords is None:
                return None
            self.coords_cache[key] = coords
        return self.coords_cache[key]

    def update_qibla_for_city(self) -> None:
        try:
            coords = self.get_coords()
            self.qibla = qibla_direction(*coords) if coords else None
        except Exception:
            self.qibla = None
        self.update_qibla()

    def fetch_prayer_times(self) -> None:
        today_str = datetime.now().strftime("%d-%m-%Y")
        url = f"{BASE_URL}/timingsByCity/{today_str}"
        params = {
            "city": self.city,
            "country": self.country,
            "method": self.method,
        }
        headers = {
            "User-Agent": "NamazTUI/1.0",
            "Accept": "application/json",
        }
        try:
            response = httpx.get(
                url,
                params=params,
                headers=headers,
                follow_redirects=True,
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()
            data = payload["data"]
            timings = data["timings"]
            hijri = data["date"]["hijri"]
            self.hijri_date = f"{hijri['day']}. {hijri['month']['en']} {hijri['year']} AH"
            self.method_name = data.get("meta", {}).get("method", {}).get("name", f"Method {self.method}")

            now = datetime.now()
            self.prayer_times.clear()

            for key in PRAYER_KEYS:
                hour, minute = map(int, timings[key][:5].split(":"))
                self.prayer_times[key] = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            self.query_one("#location-info", Static).update(
                f"📍 {self.city}, {self.country}  |  🌙 {self.hijri_date}"
            )
            self.query_one("#method-info", Static).update(
                f"📐 Method: {self.method_name} (#{self.method})"
            )
            self.update_qibla_for_city()
            self._last_sun_state = None
            self.update_countdown()

        except Exception as e:
            self.query_one("#location-info", Static).update(f"[b #ff5555]Error loading times:[/] {e}")

    def update_qibla(self) -> None:
        if self.qibla is None:
            self.query_one("#qibla-rose", Static).update("")
            return
        self.query_one("#qibla-rose", Static).update(qibla_line(self.qibla))

    def check_alarms(self, now: datetime) -> None:
        """Prüft jede Sekunde, ob ein Gebets-Alarm oder die 23-Minuten-Vorab-Erinnerung fällig ist."""
        if self.alarm_mode == "off" or not self.prayer_times:
            return

        date_tag = now.strftime("%Y-%m-%d")
        for name, p_time in self.prayer_times.items():
            # 1) Exakt zur Gebetszeit (im 5-Sekunden-Fenster auslösen)
            diff_now = (now - p_time).total_seconds()
            key_at = f"{date_tag}:{name}:at"
            if 0 <= diff_now < 5 and key_at not in self._triggered_alarms:
                self._triggered_alarms.add(key_at)
                play_synth_chime("prayer")
                send_system_notification(f"Salah: {name}", f"It is now time for {name} ({p_time.strftime('%H:%M')}).")
                self.notify(f"It is now time for {name} ({p_time.strftime('%H:%M')})", title=f"🔔 {name}")

            # 2) 23 Minuten vor Gebetszeit
            if self.alarm_mode == "before_23m":
                pre_time = p_time - timedelta(minutes=23)
                diff_pre = (now - pre_time).total_seconds()
                key_pre = f"{date_tag}:{name}:pre23"
                if 0 <= diff_pre < 5 and key_pre not in self._triggered_alarms:
                    self._triggered_alarms.add(key_pre)
                    play_synth_chime("pre")
                    send_system_notification(f"Upcoming: {name} in 23m", f"{name} begins at {p_time.strftime('%H:%M')}.")
                    self.notify(f"{name} begins in 23 minutes ({p_time.strftime('%H:%M')})", title=f"⏰ {name} Soon")

    def update_countdown(self) -> None:
        if not self.prayer_times:
            return

        now = datetime.now()
        self.check_alarms(now)

        next_prayer = None
        next_time = None

        for name, p_time in self.prayer_times.items():
            if p_time > now:
                next_prayer = name
                next_time = p_time
                break

        if next_prayer is None:
            next_prayer = "Fajr (Tomorrow)"
            next_time = self.prayer_times["Fajr"] + timedelta(days=1)

        diff = next_time - now
        hours, remainder = divmod(int(diff.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        self.query_one("#next-prayer-label", Static).update(
            f"Next Prayer: [b #50fa7b]{next_prayer}[/]"
        )
        self.query_one("#countdown", Digits).update(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        self.update_table(now, next_prayer)

        sun_state = (now.minute, self.selected_prayer)
        if self._last_sun_state != sun_state:
            self._last_sun_state = sun_state
            self.query_one("#sun-arc", Static).update(
                sun_arc(self.prayer_times, now, self.selected_prayer)
            )

    def update_table(self, now: datetime, next_prayer: str) -> None:
        table = self.query_one(DataTable)
        saved_row = table.cursor_row
        table.clear()

        def span_mins(start: datetime, end: datetime) -> int:
            mins = int((end - start).total_seconds() // 60)
            return mins + 1440 if mins < 0 else mins

        def fmt_span(mins: int) -> str:
            h, m = divmod(mins, 60)
            return f"{h}h {m:02d}m"

        pt = self.prayer_times
        durations = {
            "Fajr": span_mins(pt["Fajr"], pt["Sunrise"]),
            "Sunrise": span_mins(pt["Sunrise"], pt["Maghrib"]),
            "Dhuhr": span_mins(pt["Dhuhr"], pt["Maghrib"]),
            "Asr": span_mins(pt["Asr"], pt["Maghrib"]),
            "Maghrib": span_mins(pt["Maghrib"], pt["Isha"]),
            "Isha": span_mins(pt["Isha"], pt["Fajr"]),
        }

        common_den = next(
            (d for d in (8, 12, 16, 24) if all(abs((m / 1440) - round((m / 1440) * d) / d) <= 0.025 for m in durations.values())),
            24,
        )

        icons = {
            "Fajr": ("#8be9fd", "↗"),
            "Sunrise": ("#f1fa8c", "☀"),
            "Dhuhr": ("#ffd700", "◐"),
            "Asr": ("#ffb86c", "↘"),
            "Maghrib": ("#ff79c6", "↘"),
            "Isha": ("#bd93f9", "☾"),
        }

        name_colors = {
            "Fajr": "#bd93f9",
            "Sunrise": "#f1fa8c",
            "Dhuhr": "#ffd700",
            "Asr": "#ffd700",
            "Maghrib": "#ff79c6",
            "Isha": "#bd93f9",
        }

        for name, p_time in pt.items():
            time_str = p_time.strftime("%H:%M")
            styled_name = f"[{name_colors.get(name, '#f8f8f2')}]{name}[/]"

            if p_time < now:
                status = "[#ffd700]✓ Passed[/]"
            elif name == next_prayer:
                status = "[#50fa7b]⏳ Next[/]"
            else:
                status = "[#50fa7b]• Upcoming[/]"

            mins = durations[name]
            color, arrow = icons[name]
            span_str = f"[{color}]{arrow} {fmt_span(mins)}[/]"
            num = round((mins / 1440) * common_den)
            ratio_str = f"[#8be9fd]{num}/{common_den}[/]"
            share_str = f"[#6272a4]{(mins / 1440) * 100:4.1f}%[/]"

            table.add_row(styled_name, time_str, status, span_str, ratio_str, share_str)

        target_name = "Fajr" if next_prayer.startswith("Fajr") else next_prayer
        if self._last_next_prayer != target_name:
            self._last_next_prayer = target_name
            self._user_scrolled = False

        if not self._user_scrolled and target_name in PRAYER_KEYS:
            target_row = PRAYER_KEYS.index(target_name)
        else:
            target_row = saved_row

        if 0 <= target_row < table.row_count:
            self._programmatic_move = True
            table.move_cursor(row=target_row, animate=False)
            self._programmatic_move = False
            self.selected_prayer = PRAYER_KEYS[target_row]


def main() -> None:
    app = Salah(city="Zurich", country="Switzerland", method=3)
    app.run()


if __name__ == "__main__":
    main()
# aladhan
