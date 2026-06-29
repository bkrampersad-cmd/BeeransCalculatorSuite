# 🧮 Beeran's Calculator Suite

> *Why juggle a dozen different tools when everything you need can live beautifully in one place?*

A free, fully offline calculator suite available as both a **Progressive Web App** and a **Windows desktop app** — **55 calculators across 8 categories**, no ads, no subscriptions, no account required.

**🌐 [beeranscalculatorsuite.com](https://beeranscalculatorsuite.com)**

---

## ✨ Features

- **Free forever** — no ads, no subscriptions, no sign-in
- **Fully offline** — works without internet after first load (PWA) or out of the box (desktop)
- **Installable PWA** — add to your home screen on any device; opens like a native app
- **Beautiful UI** — clean navy sidebar, white cards, consistent design throughout
- **Mobile-friendly** — responsive layout on all screen sizes
- **Privacy-first** — all calculations run locally; nothing is sent anywhere
- **Fast** — lazy loading and background prebuild mean the app opens in under a second

---

## 📐 Calculator Categories

### 🔢 Basic Calculator
Standard calculator with full keyboard support, 8-slot memory, and a 20-entry history panel.

### 🔬 Scientific & Graphing
Full scientific calculator with DEG/RAD mode — sin, cos, tan, log, ln, √, x², xʸ, n!, π, e, and more. Includes a multi-expression function grapher with pan and zoom.

### 🏗️ Construction (17 calculators)
Area · Batten Spacing · Concrete Volume · Corner Angle · Crown Molding · Diagonal · Frame Spacing · Lumber · Master Calc · Miter Joint · Overlapping Boards · **Parquet and Decking** · Ramp · Roofing · Slope · Stairs · Volume

> Every construction calculator includes a **live diagram** that redraws dynamically as you enter values. Parquet and Decking supports across / along / 45° diagonal board directions with animated stagger patterns.

### 🔄 Conversion (3 calculators)
- **Currency Converter** — 30 currencies with live flag display and real-time exchange rates
- **Time & Date** — date arithmetic, calendar popups, age calculation
- **Unit Converter** — length, weight, temperature, volume, area, speed, and more

### ⚡ Electronics (3 calculators)
- **Ohm's Law** — interactive V/I/R/P circle diagram
- **Series / Parallel Resistors** — up to 10 resistors with full result breakdown
- **Voltage Divider** — with load resistance support

### 💹 Finance (11 calculators)
Amortization Schedule · Bill Splitter · Compound Interest · Credit Card Payoff · Depreciation · Loan Calculator · MACRS Rate · MACRS Full · Mortgage · ROI · Savings Goal

### 🌐 IT Networking (6 calculators)
Binary ↔ Hex · IP Address Converter · IPv6 Calculator · Subnet / CIDR · Subnet Cheat Sheet · Supernet

### 🏥 Medical (13 calculators)
BMI Calculator · Body Surface Area · Drug Dosage · IV Drip Rate · Opioid Conversion · Pharmacy Dilution · Creatinine Clearance · QTc Calculator *(cardiology)* · Carboplatin Dose *(oncology)* · Ideal Body Weight · eGFR (CKD-EPI) · Anion Gap · Mean Arterial Pressure *(cardiology)*

> ⚠️ Medical calculators are for clinical reference only. Always verify results with a licensed healthcare professional.

---

## 📱 PWA — Install as an App

Beeran's Calculator Suite is a **Progressive Web App** — install it from your browser with no App Store required.

### Android (Chrome)
1. Open Chrome and go to **[beeranscalculatorsuite.com](https://beeranscalculatorsuite.com)**
2. Tap the **⋮ menu** → **"Add to Home screen"**
3. Tap **"Add"** — the icon appears on your home screen

### iOS (Safari)
1. Open Safari and go to **[beeranscalculatorsuite.com](https://beeranscalculatorsuite.com)**
2. Tap the **Share button** (box with arrow) at the bottom
3. Tap **"Add to Home Screen"** → **"Add"**

> PWA installation on iOS requires Safari. Chrome on iOS does not support "Add to Home Screen" for PWAs.

### Windows / Mac (Chrome or Edge)
1. Go to **[beeranscalculatorsuite.com](https://beeranscalculatorsuite.com)**
2. Click the **⊕ install icon** in the address bar
3. Click **"Install"** — the app opens in its own window

### Keeping It Updated
The PWA updates automatically in the background. To force a refresh:
- **Android / Desktop:** `Ctrl+Shift+R` (or `Cmd+Shift+R` on Mac), or clear site data in browser settings
- **iOS:** Delete the app from your home screen and re-add it from Safari

---

## 🖥️ Desktop App (Windows)

### Download and Run
1. Download the latest release from the [Releases](../../releases) page
2. Unzip `BeeransCalculatorSuite.zip`
3. Run `BeeransCalculatorSuite.exe` inside the unzipped folder

> The entire folder must stay intact — the exe depends on files in the same directory.

### Run from Source
**Requirements:** Python 3.10+, Windows

```bash
git clone https://github.com/yourusername/BeeransCalculatorSuite.git
cd BeeransCalculatorSuite

pip install customtkinter numpy-financial python-dateutil

python calculator_suite.py
```

### Build the Executable

```bash
pip install pyinstaller
pyinstaller --clean calculator_suite.spec
```

The build output lives in `dist\BeeransCalculatorSuite\`. Zip that folder to distribute.

### Desktop Settings

Click **⚙ Settings** in the sidebar to access:

| Setting | Options |
|---|---|
| **Font Size** | Scales all fonts proportionally |
| **Default Tab** | Which calculator opens at launch |
| **Default Sub-tab** | Which sub-calculator opens within a tab |
| **Visible Calculators** | Hide any main tab or individual sub-calculator |

Settings persist automatically across launches.

---

## 🛠️ Tech Stack

| Component | Technology |
|---|---|
| Desktop language | Python 3.10+ |
| Desktop UI | [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) |
| Financial math | [numpy-financial](https://numpy.org/numpy-financial/) |
| Date arithmetic | [python-dateutil](https://dateutil.readthedocs.io/) |
| Desktop packaging | [PyInstaller](https://pyinstaller.org/) (onedir mode) |
| PWA | Vanilla HTML / CSS / JavaScript (single file, no frameworks) |
| Live exchange rates | [Fawaz Ahmed Currency API](https://github.com/fawazahmed0/exchange-api) |

---

## 💬 Suggestions & Feedback

Open the app → tap **ℹ️ About** in the sidebar → fill in the suggestion form and hit **Submit**.

Or open a [GitHub Issue](../../issues) directly.

---

## 👤 Credits

**Created by Beeran Rampersad**
Built with the creative and technical assistance of [Claude AI](https://claude.ai) (Anthropic).

---

## 📄 License

MIT License — free to use, modify, and distribute.

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

<p align="center">Made with ❤️ by Beeran Rampersad &nbsp;·&nbsp; Built with Claude AI</p>
