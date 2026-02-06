"""
UI state and unit handling: mode (LIVE/PAUSE), unit (g/kg/N), last reading, tare.

All internal values are in grams; conversion and formatting happen here.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class AppMode(Enum):
    """LIVE = streaming from serial; PAUSE = frozen display, history panel visible."""

    LIVE = auto()
    PAUSE = auto()


class Unit(Enum):
    """Display units: grams, kilograms, or newtons (force = m×g with g=9.81)."""

    GRAM = "g"
    KILOGRAM = "kg"
    NEWTON = "N"

    @property
    def label(self) -> str:
        return self.value


def convert_from_grams(grams: float, unit: Unit) -> float:
    """Convert mass in grams to the selected unit (g, kg, or N using g=9.81 m/s²)."""
    if unit is Unit.GRAM:
        return grams
    if unit is Unit.KILOGRAM:
        return grams / 1000.0
    if unit is Unit.NEWTON:
        return (grams / 1000.0) * 9.81
    return grams


def format_value(grams: float, unit: Unit) -> str:
    """Format grams as "<value> <unit>" with sensible decimal places (e.g. 2 for g, 3 for kg/N)."""
    value_in_unit = convert_from_grams(grams, unit)
    if unit is Unit.GRAM:
        return f"{value_in_unit:.2f} {unit.label}"
    if unit is Unit.KILOGRAM:
        return f"{value_in_unit:.3f} {unit.label}"
    if unit is Unit.NEWTON:
        return f"{value_in_unit:.3f} {unit.label}"
    return f"{value_in_unit:.2f} {unit.label}"


def cycle_unit(current: Unit) -> Unit:
    """Return next unit in order: g → kg → N → g (used by Mode button)."""
    order = [Unit.GRAM, Unit.KILOGRAM, Unit.NEWTON]
    idx = order.index(current)
    return order[(idx + 1) % len(order)]


@dataclass
class UIState:
    """
    Central UI state: last raw reading (grams), tare offset, mode, and unit.

    Display value = (last_raw_grams - tare_offset_grams) converted to current unit.
    Tare sets tare_offset_grams = last_raw_grams so the display shows zero.
    """

    mode: AppMode = AppMode.LIVE
    unit: Unit = Unit.GRAM
    last_raw_grams: float | None = None   # latest value from MCU (grams)
    tare_offset_grams: float = 0.0        # subtracted for display; set by Tare button
    has_data: bool = False
    has_serial_error: bool = False

    def apply_new_reading(self, grams: float) -> None:
        """Update state with a new reading from the serial worker."""
        self.last_raw_grams = grams
        self.has_data = True
        self.has_serial_error = False

    def get_display_grams(self) -> float | None:
        """Value to show (raw minus tare); None if no reading yet."""
        if self.last_raw_grams is None:
            return None
        return self.last_raw_grams - self.tare_offset_grams

    def get_display_text(self) -> str:
        """Formatted string for the main readout (e.g. \"--.-- g\" or \"123.45 kg\")."""
        value_grams = self.get_display_grams()
        if value_grams is None:
            return f"--.-- {self.unit.label}"
        return format_value(value_grams, self.unit)

    def toggle_mode(self) -> None:
        self.mode = AppMode.PAUSE if self.mode is AppMode.LIVE else AppMode.LIVE

    def set_mode(self, mode: AppMode) -> None:
        self.mode = mode

    def cycle_unit(self) -> None:
        """Advance to next unit (g → kg → N → g)."""
        self.unit = cycle_unit(self.unit)

    def apply_tare(self) -> None:
        """Set tare offset to current raw reading so the display reads zero."""
        if self.last_raw_grams is not None:
            self.tare_offset_grams = self.last_raw_grams

