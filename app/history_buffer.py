"""
History buffer: fixed-size ring buffer of formatted log lines.

Stores each reading as "<value> <unit>\\t<timestamp>" or TARE markers.
When full, oldest entries are dropped. Used by the main window for the
history panel (PAUSE mode) and CSV export.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Deque, List

from .ui_state import Unit, format_value


class HistoryBuffer:
    """
    Ring buffer of formatted history lines (value + unit + timestamp, or TARE marker).

    When full, oldest entries are dropped. Used for on-screen log and CSV export.
    """

    def __init__(self, capacity: int = 6000) -> None:
        self._capacity = capacity
        # deque(maxlen=N) automatically drops oldest when appending at capacity
        self._entries: Deque[str] = deque(maxlen=capacity)

    @property
    def capacity(self) -> int:
        return self._capacity

    def add_value(self, grams: float, unit: Unit) -> None:
        """Append one data line: "<value> <unit>\\t<HH:MM:SS.mmm>" (local time)."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        value_text = format_value(grams, unit)
        line = f"{value_text}\t{timestamp}"
        self._entries.append(line)

    def add_tare_marker(self) -> None:
        """Append a TARE marker so the log/CSV shows when zero was reset."""
        self._entries.append("--- TARE APPLIED ---")

    def clear(self) -> None:
        """Remove all entries (rarely needed; mainly for testing)."""
        self._entries.clear()

    def to_text(self) -> str:
        """All entries as one string, oldest first, newline-separated."""
        return "\n".join(self._entries)

    def to_list(self) -> List[str]:
        """All entries as a list, oldest first (used by history view and CSV export)."""
        return list(self._entries)

