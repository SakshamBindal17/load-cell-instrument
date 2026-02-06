"""
Serial reader worker: reads thrust/weight from the MCU over USB serial.

Designed to run in a QThread. Opens the port, reads lines (e.g. "time_ms\tTHRUST_g"),
parses the numeric value (grams), and emits Qt signals. Never touches UI widgets.
"""
from __future__ import annotations

import threading
from typing import Optional

from PySide6.QtCore import QObject, Signal
import serial
import serial.tools.list_ports


class SerialReader(QObject):
    """
    Reads thrust/weight values from the MCU over serial; runs in a QThread.

    Opens the given port, reads lines (e.g. "time_ms\tTHRUST_g"), parses the
    numeric value, and emits new_value(grams). Emits error(str) and stopped()
    on failure or shutdown. Must not access UI widgets.
    """

    # Qt signals: main window connects to these (thread-safe)
    new_value = Signal(float)   # each parsed reading in grams
    error = Signal(str)         # serial open/read error message
    stopped = Signal()          # worker has finished (success or failure)

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 115200,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._port = port or self._auto_detect_port()
        self._baudrate = baudrate
        self._serial: Optional[serial.Serial] = None
        self._stop_event = threading.Event()  # set by main window to request exit

    @staticmethod
    def _auto_detect_port() -> Optional[str]:
        """Return first available serial port, or None. Override by passing port= explicitly."""
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            return None
        return ports[0].device

    def stop(self) -> None:
        """Request the run loop to exit on its next iteration (thread-safe)."""
        self._stop_event.set()

    def run(self) -> None:
        """
        Main worker loop: open port, read lines, emit new_value(grams).
        Connect this to QThread.started. Runs until stop() is called or an error occurs.
        """
        try:
            if not self._port:
                self.error.emit("No serial port available")
                self.stopped.emit()
                return

            try:
                self._serial = serial.Serial(
                    self._port,
                    self._baudrate,
                    timeout=0.1,  # short timeout so we can check _stop_event often
                )
            except serial.SerialException as e:
                self.error.emit(f"Serial open error: {e}")
                self.stopped.emit()
                return

            while not self._stop_event.is_set():
                try:
                    line_bytes = self._serial.readline()
                except serial.SerialException as e:
                    self.error.emit(f"Serial read error: {e}")
                    break

                if not line_bytes:
                    continue

                try:
                    line = line_bytes.decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue
                    # Firmware sends "time_ms\tTHRUST_g" or "1300\t152.3"; last token is grams
                    parts = line.replace("\t", " ").split()
                    if not parts:
                        continue
                    value_str = parts[-1]
                    value = float(value_str)
                except ValueError:
                    # Skip header line or malformed data
                    continue

                self.new_value.emit(value)

        finally:
            # Always close port and signal that we are done
            if self._serial is not None and self._serial.is_open:
                try:
                    self._serial.close()
                except Exception:
                    pass
            self.stopped.emit()

