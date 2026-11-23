import math
from datetime import datetime, timedelta

import httpx
from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Digits, Footer, Header, Input, Label, Select, Static

BASE_URL = "https://api.aladhan.com/v1"
GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"

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
    return results[0]["latitude"], results[0]["longitude"]


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


def qibla_rose(deg: float) -> str:
    """Große Kompassrose mit Pfeil in Qibla-Richtung und gelber Gradangabe."""
    arrow = ROSE_ARROWS[round(deg / 45) % 8]
    return (
        "[b #ff5555]N[/]\n"
        "[#8be9fd]NW[/]       [#8be9fd]NO[/]\n"
        f"[#8be9fd]W[/]       [b #50fa7b]{arrow}[/]       [#8be9fd]O[/]\n"
        "[#8be9fd]SW[/]       [#8be9fd]SO[/]\n"
        "[#8be9fd]S[/]\n"
        "\n"
        f"[b #f1fa8c]🕋 {deg:.1f}° {compass_name(deg)}[/]"
    )


def qibla_line(deg: float) -> str:
    """Einzeilige Qibla-Anzeige: Richtung, Pfeil und Gradzahl."""
    arrow = ROSE_ARROWS[round(deg / 45) % 8]
    name = compass_name(deg)
    colored_name = "".join(
        f"[b #ff5555]{c}[/]" if c == "N" else f"[#8be9fd]{c}[/]"
        for c in name
    )
    return f"{colored_name}  [b #50fa7b]{arrow}[/]  [b #f1fa8c]🕋 {deg:.1f}°[/]"


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
        width: 68;
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
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("c", "change_city", "Change Location"),
        ("r", "refresh_times", "Refresh"),
    ]

    def __init__(self, city: str = "Zurich", country: str = "Switzerland", method: int = 3):
        super().__init__()
        self.city = city
        self.country = country
        self.method = method  # 3 = Muslim World League, 13 = Diyanet
        self.method_name: str = ""
        self.prayer_times: dict[str, datetime] = {}
        self.hijri_date: str = ""
        self.qibla: float | None = None
        self.coords_cache: dict[tuple[str, str], tuple[float, float]] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="main-box"):
            yield Static("Loading prayer times...", id="location-info")
            yield Static("", id="method-info")
            yield Static("", id="qibla-rose")
            yield Static("", id="next-prayer-label")
            yield Digits("00:00:00", id="countdown")
            yield DataTable(id="times-table", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self.theme = "dracula"
        table = self.query_one(DataTable)
        table.add_columns("Prayer", "Time", "Status")
        self.fetch_prayer_times()
        self.set_interval(1.0, self.update_countdown)

    def action_refresh_times(self) -> None:
        self.fetch_prayer_times()

    def action_change_city(self) -> None:
        def handle_city_result(result: tuple[str, str, int] | None) -> None:
            if result:
                self.city, self.country, self.method = result
                self.fetch_prayer_times()

        self.push_screen(CityModal(self.city, self.country, self.method), handle_city_result)

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
            keys = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]
            self.prayer_times.clear()

            for key in keys:
                hour, minute = map(int, timings[key][:5].split(":"))
                self.prayer_times[key] = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            self.query_one("#location-info", Static).update(
                f"📍 {self.city}, {self.country}  |  🌙 {self.hijri_date}"
            )
            self.query_one("#method-info", Static).update(
                f"📐 Method: {self.method_name} (#{self.method})"
            )
            self.update_qibla_for_city()
            self.update_countdown()

        except Exception as e:
            self.query_one("#location-info", Static).update(f"[b #ff5555]Error loading times:[/] {e}")

    def update_qibla(self) -> None:
        if self.qibla is None:
            self.query_one("#qibla-rose", Static).update("")
            return
        self.query_one("#qibla-rose", Static).update(qibla_line(self.qibla))

    def update_countdown(self) -> None:
        if not self.prayer_times:
            return

        now = datetime.now()
        next_prayer = None
        next_time = None

        for name, p_time in self.prayer_times.items():
            if p_time > now:
                next_prayer = name
                next_time = p_time
                break

        # After Isha -> next prayer is Fajr tomorrow
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

    def update_table(self, now: datetime, next_prayer: str) -> None:
        table = self.query_one(DataTable)
        table.clear()
        for name, p_time in self.prayer_times.items():
            time_str = p_time.strftime("%H:%M")
            if p_time < now:
                status = "[#ffd700]✓ Passed[/]"
            elif name == next_prayer:
                status = "[#50fa7b]⏳ Next[/]"
            else:
                status = "[#50fa7b]• Upcoming[/]"
            table.add_row(name, time_str, status)


def main() -> None:
    app = Salah(city="Zurich", country="Switzerland", method=3)
    app.run()


if __name__ == "__main__":
    main()
