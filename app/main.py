"""
Main window and application entry point for the Load Cell Instrument.

Builds the UI (port selection, display, history, Power/Mode/Tare), runs serial
I/O in a background thread, and keeps display and history in sync via Qt signals.
"""
from __future__ import annotations

import csv
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, QTimer, Qt
from PySide6.QtGui import QFont, QPalette, QColor, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QPlainTextEdit,
    QComboBox,
)
import serial.tools.list_ports

from .history_buffer import HistoryBuffer
from .serial_reader import SerialReader
from .ui_state import AppMode, UIState


class MainWindow(QMainWindow):
    """
    Main application window: display, port selection, controls, and history.

    Layout: port bar → large numeric display → status/notification → history (PAUSE only) → Power / Mode / Tare.
    """

    def __init__(self, serial_port: Optional[str] = None) -> None:
        super().__init__()
        self.setWindowTitle("Load Cell Instrument")

        # Central state: last reading, tare offset, mode (LIVE/PAUSE), unit (g/kg/N)
        self._ui_state = UIState()
        # Ring buffer of formatted lines for history panel and CSV export
        self._history = HistoryBuffer(capacity=6000)

        # Serial is read in a worker thread; we only connect/disconnect and handle signals here
        self._serial_port = serial_port
        self._serial_thread: Optional[QThread] = None
        self._serial_worker: Optional[SerialReader] = None
        self._connected: bool = False

        # All widgets are created in _build_ui; we keep references for updates and events
        self._display_label: QLabel
        self._status_label: QLabel
        self._notification_label: QLabel
        self._history_view: QPlainTextEdit
        self._power_button: QPushButton
        self._mode_button: QPushButton
        self._tare_button: QPushButton
        self._port_combo: QComboBox
        self._refresh_ports_button: QPushButton
        self._connect_button: QPushButton
        self._history_section: QWidget
        self._export_csv_button: QPushButton

        # Timer drives display updates at ~25 Hz so UI stays responsive even if serial is slow
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(40)
        self._update_timer.timeout.connect(self._refresh_display)

        # Notifications (e.g. "System is taring") auto-hide after a few seconds
        self._notification_timer = QTimer(self)
        self._notification_timer.setSingleShot(True)
        self._notification_timer.timeout.connect(self._clear_notification)

        self._build_ui()
        self._apply_initial_mode()

    # ---------------------------------------------------------------------------
    # UI construction: layout and styling only; no business logic here
    # ---------------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)
        central.setLayout(main_layout)

        # ---- Serial connection bar: dropdown of available ports, Refresh, Connect/Disconnect ----
        port_bar = QHBoxLayout()
        port_bar.setSpacing(8)

        port_label = QLabel("Port:", self)
        port_label.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self._port_combo = QComboBox(self)
        self._port_combo.setEditable(False)

        self._refresh_ports_button = QPushButton("Refresh", self)
        self._connect_button = QPushButton("Connect", self)

        # Reusable dark-theme style for smaller buttons (port bar, Export CSV)
        small_button_style = """
        QPushButton {
            background-color: #222222;
            color: #FFFFFF;
            border-radius: 4px;
            padding: 4px 10px;
        }
        QPushButton:hover {
            background-color: #333333;
        }
        QPushButton:pressed {
            background-color: #444444;
        }
        """
        self._refresh_ports_button.setStyleSheet(small_button_style)
        self._connect_button.setStyleSheet(small_button_style)

        port_bar.addWidget(port_label)
        port_bar.addWidget(self._port_combo, stretch=1)
        port_bar.addWidget(self._refresh_ports_button)
        port_bar.addWidget(self._connect_button)

        main_layout.addLayout(port_bar)

        # ---- Main readout: large numeric value; shows "--.-- g" until first reading ----
        self._display_label = QLabel("--.-- g", self)
        self._display_label.setAlignment(Qt.AlignCenter)

        display_font = QFont("Consolas", 48, QFont.Bold)
        self._display_label.setFont(display_font)

        # Instrument-style dark background; teal accent for high contrast
        palette = self._display_label.palette()
        palette.setColor(QPalette.Window, QColor("#111111"))
        palette.setColor(QPalette.WindowText, QColor("#00FFC8"))
        self._display_label.setAutoFillBackground(True)
        self._display_label.setPalette(palette)

        main_layout.addWidget(self._display_label, stretch=5)

        # ---- Status line below readout: connection info or "NO DATA" on serial error ----
        self._status_label = QLabel("", self)
        status_font = QFont("Consolas", 10)
        self._status_label.setFont(status_font)
        self._status_label.setStyleSheet("color: #888888;")
        self._status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self._status_label)

        # ---- Notification strip: short-lived messages (power on, tare, export saved) ----
        self._notification_label = QLabel("", self)
        self._notification_label.setFont(QFont("Consolas", 11, QFont.Bold))
        self._notification_label.setStyleSheet(
            "color: #00FFC8; background-color: #1a2a2a; "
            "border-radius: 4px; padding: 6px 12px;"
        )
        self._notification_label.setAlignment(Qt.AlignCenter)
        self._notification_label.setVisible(False)
        main_layout.addWidget(self._notification_label)

        # ---- History section: shown only in PAUSE; contains Export CSV and scrollable log ----
        self._history_section = QWidget(self)
        history_section_layout = QVBoxLayout(self._history_section)
        history_section_layout.setContentsMargins(0, 0, 0, 0)
        history_section_layout.setSpacing(8)

        export_row = QHBoxLayout()
        self._export_csv_button = QPushButton("Export CSV", self)
        self._export_csv_button.setStyleSheet(small_button_style)
        self._export_csv_button.clicked.connect(self._on_export_csv)
        export_row.addWidget(self._export_csv_button)
        export_row.addStretch()
        history_section_layout.addLayout(export_row)

        self._history_view = QPlainTextEdit(self)
        self._history_view.setReadOnly(True)
        self._history_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        history_font = QFont("Consolas", 10)
        self._history_view.setFont(history_font)
        history_section_layout.addWidget(self._history_view, stretch=1)

        self._history_section.hide()
        main_layout.addWidget(self._history_section, stretch=3)

        # ---- Control buttons: Power (LIVE/PAUSE), Mode (cycle g → kg → N), Tare (zero) ----
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(20)

        self._power_button = QPushButton("Power ON", self)
        self._mode_button = QPushButton("Mode (g)", self)
        self._tare_button = QPushButton("Tare", self)

        # Same dark-theme style for the three main control buttons
        button_style = """
        QPushButton {
            background-color: #222222;
            color: #FFFFFF;
            border-radius: 6px;
            padding: 8px 16px;
        }
        QPushButton:hover {
            background-color: #333333;
        }
        QPushButton:pressed {
            background-color: #444444;
        }
        """
        for btn in (self._power_button, self._mode_button, self._tare_button):
            btn.setStyleSheet(button_style)

        controls_layout.addWidget(self._power_button)
        controls_layout.addWidget(self._mode_button)
        controls_layout.addWidget(self._tare_button)

        main_layout.addLayout(controls_layout, stretch=2)

        self._refresh_ports_button.clicked.connect(self._on_refresh_ports_clicked)
        self._connect_button.clicked.connect(self._on_connect_clicked)
        self._power_button.clicked.connect(self._on_power_clicked)
        self._mode_button.clicked.connect(self._on_mode_clicked)
        self._tare_button.clicked.connect(self._on_tare_clicked)

        # Fill port dropdown with current system ports (user picks one and clicks Connect)
        self._populate_serial_ports()

    def _populate_serial_ports(self) -> None:
        """Refresh the port dropdown from the system; preserve selection if still present."""
        current = self._port_combo.currentText()
        self._port_combo.blockSignals(True)
        self._port_combo.clear()

        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            self._port_combo.addItem(p.device)

        if current:
            idx = self._port_combo.findText(current)
            if idx >= 0:
                self._port_combo.setCurrentIndex(idx)

        self._port_combo.blockSignals(False)

    # ---------------------------------------------------------------------------
    # Serial worker: start/stop the background thread that reads from the MCU
    # ---------------------------------------------------------------------------

    def _start_serial_worker(self) -> None:
        """Start the serial reader in a background thread; no-op if already running."""
        if self._serial_thread is not None:
            return

        if not self._serial_port:
            self._status_label.setText("No port selected")
            return

        self._serial_thread = QThread(self)
        self._serial_worker = SerialReader(port=self._serial_port)
        self._serial_worker.moveToThread(self._serial_thread)

        # Worker runs in its thread; we only react to signals (new value, error, stopped)
        self._serial_thread.started.connect(self._serial_worker.run)
        self._serial_worker.new_value.connect(self._handle_new_value)
        self._serial_worker.error.connect(self._handle_serial_error)
        self._serial_worker.stopped.connect(self._on_worker_stopped)

        self._serial_thread.start()

    def _stop_serial_worker(self) -> None:
        """Request stop, wait for thread exit, then clear references."""
        if self._serial_worker is None or self._serial_thread is None:
            return
        self._serial_worker.stop()
        self._serial_thread.quit()
        self._serial_thread.wait()
        self._serial_worker = None
        self._serial_thread = None

    # ---------------------------------------------------------------------------
    # User actions: port list refresh, Connect/Disconnect
    # ---------------------------------------------------------------------------

    def _on_refresh_ports_clicked(self) -> None:
        self._populate_serial_ports()

    def _on_connect_clicked(self) -> None:
        if not self._connected:
            port = self._port_combo.currentText()
            if not port:
                self._status_label.setText("No port selected")
                return
            self._serial_port = port
            self._connected = True
            self._connect_button.setText("Disconnect")
            self._status_label.setText(f"Connected: {port}")

            if self._ui_state.mode is AppMode.LIVE:
                self._start_serial_worker()
                if not self._update_timer.isActive():
                    self._update_timer.start()
        else:
            self._connected = False
            self._connect_button.setText("Connect")
            self._status_label.setText("Disconnected")
            self._stop_serial_worker()

    # ---------------------------------------------------------------------------
    # Event handlers: Power, Mode, Tare; and callbacks for serial (new value, error, stopped)
    # ---------------------------------------------------------------------------

    def _on_power_clicked(self) -> None:
        """Toggle LIVE (streaming) vs PAUSE (frozen display, history visible)."""
        if self._ui_state.mode is AppMode.LIVE:
            self._ui_state.set_mode(AppMode.PAUSE)
            self._power_button.setText("Power OFF")
            self._stop_serial_worker()
            self._update_timer.stop()
            self._show_history_panel()
            self._refresh_history_view()
        else:
            self._ui_state.set_mode(AppMode.LIVE)
            self._power_button.setText("Power ON")
            self._hide_history_panel()
            self._show_notification("System is power on")
            self._start_serial_worker()
            self._update_timer.start()

    def _on_mode_clicked(self) -> None:
        """Cycle display unit: g → kg → N → g. Affects display and new history only."""
        self._ui_state.cycle_unit()
        unit_label = self._ui_state.unit.label
        self._mode_button.setText(f"Mode ({unit_label})")

    def _on_tare_clicked(self) -> None:
        """Set current reading as zero; log a TARE marker in history."""
        self._ui_state.apply_tare()
        self._history.add_tare_marker()
        self._show_notification("System is taring")
        if self._ui_state.mode is AppMode.PAUSE:
            self._refresh_history_view()

    def _handle_new_value(self, grams: float) -> None:
        """Update display state and optionally append to history (LIVE only)."""
        self._ui_state.apply_new_reading(grams)
        self._status_label.setText("")

        if self._ui_state.mode is AppMode.LIVE:
            self._history.add_value(grams, self._ui_state.unit)

    def _handle_serial_error(self, message: str) -> None:
        """On serial error: show NO DATA; do not crash."""
        self._ui_state.has_serial_error = True
        self._status_label.setText("NO DATA")

    def _on_worker_stopped(self) -> None:
        """Serial thread exited; show NO DATA if we are still in LIVE mode."""
        if self._ui_state.mode is AppMode.LIVE:
            self._status_label.setText("NO DATA")

    # ---------------------------------------------------------------------------
    # UI helpers: initial state, panel visibility, notifications, display/history refresh, CSV export
    # ---------------------------------------------------------------------------

    def _apply_initial_mode(self) -> None:
        """Start in PAUSE; user selects port and connects before going LIVE."""
        self._ui_state.set_mode(AppMode.PAUSE)
        self._power_button.setText("Power OFF")
        self._hide_history_panel()
        self._update_timer.start()

    def _show_history_panel(self) -> None:
        self._history_section.show()

    def _hide_history_panel(self) -> None:
        self._history_section.hide()

    def _show_notification(self, message: str, duration_ms: int = 3000) -> None:
        """Show message in the notification strip; auto-hide after duration_ms."""
        self._notification_timer.stop()
        self._notification_label.setText(message)
        self._notification_label.setVisible(True)
        self._notification_timer.start(duration_ms)

    def _clear_notification(self) -> None:
        self._notification_label.setText("")
        self._notification_label.setVisible(False)
        self._notification_timer.stop()

    def _refresh_display(self) -> None:
        """Update the main numeric label from current UI state (timer-driven)."""
        self._display_label.setText(self._ui_state.get_display_text())

    def _refresh_history_view(self) -> None:
        """Reload history text; newest at top, cursor at top."""
        lines = self._history.to_list()
        text = "\n".join(reversed(lines))
        self._history_view.setPlainText(text)
        cursor = self._history_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self._history_view.setTextCursor(cursor)

    def _on_export_csv(self) -> None:
        """Export history to results/<date>_<first_ts>_to_<last_ts>.csv (timestamp, value, unit)."""
        entries = self._history.to_list()
        if not entries:
            self._show_notification("No history to export")
            return

        # Parse each history line into (timestamp, value, unit); TARE lines get a placeholder
        rows: list[tuple[str, str, str]] = []
        timestamps: list[str] = []
        for line in entries:
            if "\t" in line:
                value_part, ts = line.split("\t", 1)
                ts = ts.strip()
                timestamps.append(ts)
                parts = value_part.rsplit(maxsplit=1)
                if len(parts) == 2:
                    value_str, unit = parts
                    rows.append((ts, value_str, unit))
                else:
                    rows.append((ts, value_part, ""))
            else:
                rows.append(("", "TARE APPLIED", ""))

        # Filename includes date and first/last timestamp for easy identification
        date_str = date.today().isoformat()
        if timestamps:
            first_ts = timestamps[0].replace(":", "-").replace(".", "-")
            last_ts = timestamps[-1].replace(":", "-").replace(".", "-")
            filename = f"{date_str}_{first_ts}_to_{last_ts}.csv"
        else:
            fallback = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"load_cell_export_{fallback}.csv"

        results_dir = Path.cwd() / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        filepath = results_dir / filename

        try:
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "value", "unit"])
                for row in rows:
                    writer.writerow(row)
        except OSError as e:
            self._show_notification(f"Export failed: {e}")
            return

        self._show_notification(f"Saved to results/{filename}")

    # ---------------------------------------------------------------------------
    # Qt lifecycle: clean shutdown (stop timer and serial worker)
    # ---------------------------------------------------------------------------

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Stop timer and serial worker before closing."""
        self._update_timer.stop()
        self._stop_serial_worker()
        super().closeEvent(event)


def main() -> None:
    """Create application, main window, and run the event loop."""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.setMinimumSize(400, 300)
    window.resize(600, 400)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

