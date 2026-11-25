# 🕌 Salah

A sleek terminal user interface (TUI) for Islamic prayer times mapping the sun path across the horizon built with [Textual](https://textualize.io) and styled in the **Dracula** theme.

![Salah TUI Screenshot](screenshot.png)

## ✨ Features

- **24-Hour Solar Arc & Symmetries:** Unicode Braille curve mapping the sun/moon path across the horizon with interactive prayer markers, interval spans, ratios, and percentage shares.
- **Synthesized Reminders:** Configurable audio/desktop notifications supporting on-time chimes and 23-minute advance alerts (`n`).
- **Live Countdown & Status:** Real-time countdown with color-coded prayer status indicators (`✓ Passed`, `⏳ Next`, `• Upcoming`).
- **Qibla Direction:** Single-line compass bearing, directional arrow, and exact angle to the Kaaba.
- **Hijri Date & Method Indicator:** Displays active Hijri dates and calculation methods via the [AlAdhan API](https://aladhan.com).
- **Settings & Persistence:** Interactive modal to switch locations/methods (`c`) and save preferences locally to `~/.salah_tui.json` (`s`).

## ☀️ Solar Arc & Daylight Symmetries

Salah renders a live 24-hour astronomical arc below the prayer table using Unicode Braille sub-pixels, featuring daylight curves from Sunrise to Maghrib, night arcs spanning Isha and Fajr, and interactive markers (`◆` for fixed prayers, `◈` for the selected row). It also includes symmetry columns (`Span`, `Ratio`, `Share`) comparing twilight intervals and daylight proportions.

## 📦 Installation

Install globally in an isolated environment using [pipx](https://pypa.io):

```bash
pipx install salah-tui
```

## 🚀 Usage

Launch the application from anywhere in your terminal:

```bash
salah
```

### Keyboard Shortcuts

| Key | Action |
| :--- | :--- |
| `↑` / `↓` | Scroll through prayers and highlight their position on the solar arc |
| `c` | Change city, country, and calculation method |
| `n` | Cycle reminder mode (`Off` → `At Prayer Time` → `23m Before + At Time`) |
| `s` | Save location, calculation method, and reminder mode to `~/.salah_tui.json` |
| `r` | Refresh prayer times |
| `q` | Quit the application |

## 🕋 Qibla Direction

The Qibla is the direction from your location to the Kaaba in Makkah, displayed between the calculation method and reminder status with a directional arrow and bearing in degrees.

### How It Is Calculated

- **Coordinates:** Geocoded via [Open-Meteo Geocoding API](https://open-meteo.com/en/docs/geocoding-api) and cached per session.
- **Bearing:** Initial great-circle bearing to the Kaaba (21.4225° N, 39.8262° E) computed locally via spherical trigonometry.
- **Independence:** Calculated independently of the chosen prayer time calculation method.

### ⚠️ Notes and Limitations

- **City-level accuracy:** Computed from city centers; minor deviations may occur for larger or distant areas.
- **True north:** Based on geographic (true) north rather than magnetic north.
- **Ambiguous names:** Double-check matched locations if common city names overlap; verify coordinates via [AlAdhan Qibla endpoint](https://aladhan.com/qibla-api).
- **Internet required:** Initial lookups require connectivity; subsequent lookups rely on session caching.
- **Field verification:** Theoretical calculations should be cross-referenced with local authorities for formal prayer times.

## ⚙️ Supported Calculation Methods

- **3** – Muslim World League *(default)*
- **13** – Diyanet İşleri Başkanlığı, Turkey
- **2** – Islamic Society of North America (ISNA)
- **4** – Umm Al-Qura University, Makkah
- **5** – Egyptian General Authority of Survey
- **1** – University of Islamic Sciences, Karachi
- **12** – Union Organization Islamic de France
- **15** – Moonsighting Committee Worldwide

## 📄 License

**GNU General Public License v3.0** (GNU GPLv3) **🄯 All Lights returned** [postsonde](https://github.com/postsonde)

---

## ☪ Islamic Terminal Suite (Dracula Theme)

Part of a collection of minimalist Islamic terminal apps styled in the Dracula dark theme:

<p align="center">
  <img src="islamic-tui-suite.gif" alt="Islamic Terminal Suite Demo" width="85%" />
</p>

| App | Command | Description |
| :--- | :--- | :--- |
| **[salah-tui](https://github.com/postsonde/salah-tui.git)** | `salah` | Islamic prayer times mapping the sun path on the horizon, Hijri date & calculation methods |
| **[hijri-tui](https://github.com/postsonde/hijri-tui.git)** | `hijri` | Native Hijri calendar with lunar phases, Sunnah fasting & holy days |
| **[quran-tui](https://github.com/postsonde/quran-tui.git)** | `quran` | Study the Holy Quran with 100+ translations, side-by-side view & bookmarks |
| **[asma-tui](https://github.com/postsonde/asma-tui.git)** | `asma` | Learn the 99 Names of Allah with flashcards, streak quiz & directory |

