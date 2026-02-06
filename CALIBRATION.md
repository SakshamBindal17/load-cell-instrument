# Load cell recalibration plan

This document outlines how to add **recalibration** to the firmware so a known weight reads correctly.

---

## Current behaviour

- **Zero:** At startup the firmware averages 50 raw HX711 readings with **no load** and stores the result in `zero_offset`. Each reading is then `zeroed = raw - zero_offset`.
- **Scale factor:** A constant `COUNTS_PER_GRAM` converts zeroed counts to grams:  
  `grams = (-zeroed) / COUNTS_PER_GRAM`.  
  The minus sign matches the load cell’s sign convention.
- **Result:** If the real scale factor or zero drifts, a known weight (e.g. 1144 g) may read low or high. Recalibration corrects this.

---

## Goal

After recalibration, placing a **known weight** on the plate should make the firmware report that value (on average). This is done by updating:

- **`COUNTS_PER_GRAM`** (scale factor), and/or  
- **`zero_offset`** (zero point),

so that **displayed_grams = known_weight** when that weight is on the plate.

---

## Single-point calibration (math)

Zero is already captured at startup (no load → `zero_offset`). One known weight is enough to correct the scale factor.

1. **No load (already in setup):** Average raw → `zero_offset`.
2. **Known weight on plate (e.g. 1144 g):** Take N raw readings, average → `raw_known`.  
   Zeroed counts: `zeroed_known = raw_known - zero_offset`.  
   We want: `grams_displayed = (-zeroed_known) / COUNTS_PER_GRAM = known_weight_g`.  
   So: **`COUNTS_PER_GRAM = (-zeroed_known) / known_weight_g`**.

In firmware this can be triggered once in a “calibration mode” (e.g. serial command or button when the known weight is on), then optionally store the new `COUNTS_PER_GRAM` in EEPROM so it survives reboot.

---

## Implementation options

| Item | Description |
|------|-------------|
| **Trigger** | Serial command (e.g. `CAL,1144`) or physical button when known weight is on. |
| **Measurement** | Average N raw HX711 readings while weight is on. |
| **Formula** | `COUNTS_PER_GRAM = (-(raw_avg - zero_offset)) / known_weight_g`. |
| **Optional** | Save to EEPROM and load in `setup()` so calibration persists. |
| **Safety** | Sanity checks: `COUNTS_PER_GRAM` in a sensible range (e.g. 10–500), known weight &gt; 0 and &lt; max (e.g. 50 kg). |

---

## Procedure (after implementation)

1. **Zero:** Remove all load; boot device (or trigger “zero” in cal mode if added).
2. **Scale factor:** Put known weight on plate; trigger calibration (serial or button). Firmware computes and uses (and optionally stores) the new `COUNTS_PER_GRAM`.
3. **Check:** Remove weight → reading ~0 g; put known weight back → reading close to known value.

Once you choose how to trigger calibration (serial, button, or both) and whether to use EEPROM, the firmware changes can be implemented accordingly.
