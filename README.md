# 🧮 Beeran's Calculator Suite

> *Why juggle a dozen different tools when everything you need can live beautifully in one place?*

A polished, fully self-contained Windows desktop calculator suite — **48 calculators across 8 categories**, built with Python and CustomTkinter. No ads. No subscriptions. No internet required.

---

## ✨ Features

- **48 calculators** spanning everyday, professional, and technical use cases
- **Beautiful UI** — clean navy sidebar, white cards, consistent design system throughout
- **Fully offline** — all calculations run locally; no data ever leaves your machine
- **Portable** — copy the folder to any Windows machine and run
- **Customizable** — built-in Settings panel for theme, font size, startup defaults, and hiding unused calculators
- **Fast** — lazy loading and background prebuild mean the app opens in under a second

---

## 📐 Calculator Categories

### 🔢 Basic Calculator

Standard calculator with full keyboard support, 8-slot memory, and a 20-entry history panel.

### 🔬 Scientific & Graphing

Scientific calculator with DEG/RAD mode, trig/log/power functions, 8-slot memory, and a multi-expression function grapher with pan and zoom.

### 🏗️ Construction (17 calculators)

|     |     |     |
| --- | --- | --- |
| Area | Batten Spacing | Concrete Volume |
| Corner Angle | Crown Molding | Decking |
| Diagonal | Frame Spacing | Lumber |
| Miter Joint | Overlapping Boards | Parquet Floor |
| Ramp | Roofing | Slope |
| Stairs | Volume |     |

Every construction calculator includes a **live diagram** that redraws dynamically as you enter values.

### 🔄 Conversion (3 calculators)

- **Currency Converter** — 30 currencies with live flag display; fetches real-time rates from a free API; supports typing any currency code manually
- **Time & Date** — date arithmetic, calendar popups, age calculation
- **Unit Converter** — length, weight, temperature, volume, area, speed, and more

### ⚡ Electronics (3 calculators)

- **Ohm's Law** — interactive V/I/R/P circle diagram
- **Series / Parallel Resistors** — up to 10 resistors, full result breakdown
- **Voltage Divider** — with load resistance support

### 💹 Finance (11 calculators)

|     |     |     |
| --- | --- | --- |
| Amortization Schedule | Bill Splitter | Compound Interest |
| Credit Card Payoff | Depreciation | Loan Calculator |
| MACRS Rate | MACRS Full | Mortgage |
| ROI | Savings Goal |     |

### 🌐 IT Networking (6 calculators)

- Binary ↔ Hex Converter
- IP Address Converter
- IPv6 Calculator
- Subnet / CIDR Calculator
- Subnet Cheat Sheet
- Supernet Calculator

### 🏥 Medical (6 calculators)

- BMI Calculator (Imperial & Metric)
- Body Surface Area (Mosteller formula)
- Drug Dosage Calculator
- IV Drip Rate Calculator
- Opioid Conversion (MME)
- Pharmacy Dilution Calculator

> ⚠️ Medical calculators are for reference only. Always verify with a licensed healthcare professional.

---

## 🚀 Getting Started

### Option 1 — Download and Run (Windows)

1. Download the latest release from the [Releases](../../releases) page
2. Unzip `BeeransCalculatorSuite.zip`
3. Run `BeeransCalculatorSuite.exe` inside the unzipped folder

> The entire folder must stay intact — the exe depends on files in the same directory.

### Option 2 — Run from Source

**Requirements:** Python 3.10+, Windows

```bash
# Clone the repository
git clone https://github.com/yourusername/BeeransCalculatorSuite.git
cd BeeransCalculatorSuite

# Install dependencies
pip install customtkinter numpy-financial python-dateutil

# Run
python calculator_suite.py
```

---

## 🔨 Building the Executable

```bash
# Install PyInstaller
pip install pyinstaller

# Build (produces dist\BeeransCalculatorSuite\ folder)
pyinstaller --clean calculator_suite.spec
```

The build output lives in `dist\BeeransCalculatorSuite\`. Zip that folder to distribute.

---

## ⚙️ Settings

Click the **⚙ Settings** button at the bottom of the sidebar to access:

| Setting | Options |
| --- | --- |
| **Theme** | Light / Dark / System |
| **Font Size** | Smaller / Default / Larger (±2pt, all fonts scale together) |
| **Default Tab** | Choose which calculator opens at launch |
| **Default Sub-tab** | Choose which sub-calculator opens within a tab |
| **Visible Calculators** | Hide any main tab or individual sub-calculator |

Settings are saved automatically to a hidden file beside the exe and persist across launches.

---

## 🛠️ Tech Stack

| Component | Technology |
| --- | --- |
| Language | Python 3.10+ |
| UI Framework | [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) |
| Financial math | [numpy-financial](https://numpy.org/numpy-financial/) |
| Date arithmetic | [python-dateutil](https://dateutil.readthedocs.io/) |
| Packaging | [PyInstaller](https://pyinstaller.org/) (onedir mode) |
| Live exchange rates | [Fawaz Ahmed Currency API](https://github.com/fawazahmed0/exchange-api) |

---

## 💬 Suggestions & Feedback

Have an idea for a new calculator or a feature that would make your day easier?

Open the app → click **ℹ️ About** in the sidebar → fill in the suggestion form and hit **Submit**.
It opens your email client with everything pre-filled — one click to send.

Or open a [GitHub Issue](../../issues) directly.

---

## 👤 Credits

**Created by Beeran Rampersad**
Built with the creative and technical assistance of [Claude AI](https://claude.ai) (Anthropic).

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

```
MIT License

Copyright (c) 2026 Beeran Rampersad

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

<p align="center">
  Made with ❤️ by Beeran Rampersad  ·  Built with Claude AI
</p>
