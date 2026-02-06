# Load Cell Instrument

Desktop UI for real-time thrust/weight display from an HX711 load cell over USB serial (Arduino Mega 2560, ESP32, etc.). Designed as an instrument-style display: large readout, live/pause, tare, unit switch (g / kg / N), and exportable history (CSV).

**Prerequisites:** Python 3.10 or newer (3.9 works; 3.10+ recommended), and a board with HX711 connected and firmware flashed (see below).

---

## Quick start

### 1. Clone and enter the project

```bash
git clone <repository-url> Load_Cell_UI
cd Load_Cell_UI
```

(If you don’t use Git, unpack the project and `cd` into its folder.)

### 2. Python environment (venv)

Create and activate a virtual environment so dependencies stay local.

**Create venv (once):**

```bash
python -m venv .venv
```

**Activate:**

- **Windows (PowerShell):** `.\.venv\Scripts\Activate.ps1`
- **Windows (cmd):** `.\.venv\Scripts\activate.bat`
- **Linux/macOS:** `source .venv/bin/activate`

**Install dependencies (once, with venv active):**

```bash
pip install -r requirements.txt
```

This installs PySide6 (Qt UI) and pyserial.

### 3. Run the app

With the MCU connected over USB and venv active:

```bash
python -m app.main
```

Select the serial port in the UI, click **Connect**, then use **Power ON** for live streaming. Use **Tare** to zero the display; **Mode** to switch g / kg / N. In **Power OFF** (PAUSE), the history panel appears and you can **Export CSV** (see below).

### 4. Flashing the firmware (only when needed)

Firmware lives in `Load_Cell/Load_Cell.ino`. Flash the board **only when you change that file** (e.g. calibration, pin numbers, or deadband).

1. Open `Load_Cell/Load_Cell.ino` in the Arduino IDE (or PlatformIO).
2. Install the **HX711** library if required.
3. Select your board and port, then upload.

After power-up, the MCU takes a few seconds to establish zero (no load). Then it streams `time_ms\tTHRUST_g` lines. The UI expects one numeric value per line (the last token is used as grams).

---

## History and CSV export

- **History** is recorded only while **LIVE** (Power ON). It is not visible until you switch to **PAUSE** (Power OFF), when the history panel appears below the display.
- **Export CSV** is available in that history section: click **Export CSV** to save the current log to disk.
- **Where files are saved:** in a `results/` folder inside the project directory (created automatically if it does not exist).
- **Filename:** `results/<date>_<first_timestamp>_to_<last_timestamp>.csv` (e.g. `2025-02-06_17-39-00_to_17-45-30.csv`). If there are no data lines, a fallback name like `load_cell_export_2025-02-06_17-45-00.csv` is used.
- **CSV contents:** three columns — `timestamp`, `value`, `unit`. Each row is one reading (e.g. `17:39:10.137`, `24.02`, `g`). When you pressed **Tare**, a row with `TARE APPLIED` in the value column is included so you can see when zero was reset.
- **Capacity:** The in-memory history holds the last 6000 entries; older ones are dropped. Export saves whatever is currently in that buffer.

---

## Project layout

| Path | Description |
|------|-------------|
| `app/main.py` | Entry point; main window, port selection, controls, history. |
| `app/serial_reader.py` | Serial reader worker (QThread); parses lines, emits grams. |
| `app/history_buffer.py` | Ring buffer of history lines for display and CSV export. |
| `app/ui_state.py` | Display state: last reading, tare, mode, unit, formatting. |
| `Load_Cell/Load_Cell.ino` | MCU firmware: HX711 read, zero, deadband, serial output. |
| `requirements.txt` | Python dependencies (PySide6, pyserial). |

---

## Behaviour summary

- **LIVE (Power ON):** Serial worker runs; display updates in real time; history is recorded in the background but the history panel is hidden.
- **PAUSE (Power OFF):** Serial reading stops; display freezes at the last value; history panel becomes visible and scrollable; **Export CSV** is available.
- **Tare:** Sets the current reading as zero (display shows 0). A TARE marker is added to the history and appears in exported CSV.
- **Mode:** Cycles display unit g → kg → N → g. Affects the main readout and new history entries only; existing log lines keep their unit.
- **Units:** Internal value is always grams; conversion to kg or N is for display and export only.
- **History:** Ring buffer of 6000 entries (oldest dropped when full). Only recorded while LIVE; export from PAUSE (see **History and CSV export** above).
- **Serial failure / disconnect:** UI shows “NO DATA” under the display and keeps the last value; it does not crash. Reconnect and click Connect again when the device is back.

For a detailed recalibration plan (known weight, scale factor, EEPROM), see [CALIBRATION.md](CALIBRATION.md).
