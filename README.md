# 🕌 Salah

A sleek terminal user interface (TUI) for Islamic prayer times built with [Textual](https://textualize.io) and styled in the **Dracula** theme.

![Salah TUI Screenshot](screenshot.png)

## ✨ Features

- **Live Countdown** to the next upcoming prayer
- **Color-Coded Status** (`Gold` for passed prayers, `Green` for next & upcoming prayers)
- **Hijri & Gregorian Date** display
- **Interactive Settings Modal** to switch city, country, and calculation method on the fly
- **Calculation Method Indicator** showing the active method fetched from the [AlAdhan API](https://aladhan.com)

## 📦 Installation

Install globally in an isolated environment using [pipx](https://pypa.io):

```bash
git clone <your-repo-url>
cd <your-repo-folder>
pipx install .
```

## 🚀 Usage

Launch the application from anywhere in your terminal:

```bash
salah
```

### Keyboard Shortcuts

| Key | Action |
| :--- | :--- |
| `c` | Change city, country, and calculation method |
| `r` | Refresh prayer times |
| `q` | Quit the application |

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

GNU General Public License (GPLv3)
