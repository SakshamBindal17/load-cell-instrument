/*
 * Load Cell Instrument – firmware for HX711 load cell (Arduino/ESP32).
 *
 * Behaviour:
 *   - At startup: average 50 samples with no load → zero_offset.
 *   - Each loop: read raw, zeroed = raw - zero_offset.
 *   - If |zeroed| < ZERO_DEADBAND: send 0 g (suppresses noise at zero).
 *   - Else: send thrust_g = (-zeroed) / COUNTS_PER_GRAM (instantaneous, no averaging).
 *
 * Serial output: one line per reading, "time_ms\tTHRUST_g" (e.g. "1300\t152.3").
 * The desktop UI reads the last token as grams.
 *
 * Hardware: HX711 DOUT → pin HX_DOUT, SCK → pin HX_SCK. Adjust for your board.
 */
#include "HX711.h"

/* HX711 data and clock pins (typical for ESP32; change for Arduino/other). */
#define HX_DOUT 36
#define HX_SCK  38

/* Scale factor: raw ADC counts per gram. Calibrate with a known weight (see CALIBRATION.md). */
#define COUNTS_PER_GRAM 64.5

/* Deadband: readings with |zeroed| below this are sent as 0 g to avoid flicker at no load.
 * 300 counts ≈ 4.6 g at 64.5 counts/g. Increase if zero still jumps. */
#define ZERO_DEADBAND   300

HX711 scale;
long zero_offset = 0;   /* Set in setup(); subtracted from every raw reading. */

void setup() {
  Serial.begin(115200);
  delay(500);

  scale.begin(HX_DOUT, HX_SCK);

  /* Capture zero with no load: average 50 samples so startup zero is stable. */
  long sum = 0;
  for (int i = 0; i < 50; i++) {
    while (!scale.is_ready());
    sum += scale.read();
  }
  zero_offset = sum / 50;

  /* Header line so the UI can ignore the first line if needed. */
  Serial.println("time_ms\tTHRUST_g");
}

void loop() {
  if (!scale.is_ready()) return;

  long raw = scale.read();
  long zeroed = raw - zero_offset;
  unsigned long t = millis();

  /* Deadband: near-zero readings are sent as 0 g for a stable idle display. */
  if (abs(zeroed) < ZERO_DEADBAND) {
    Serial.print(t);
    Serial.print("\t");
    Serial.println(0);
    return;
  }

  /* Instantaneous grams (no moving average), so step changes (e.g. 0→2 kg) show immediately. */
  float thrust_g = (-zeroed) / COUNTS_PER_GRAM;
  Serial.print(t);
  Serial.print("\t");
  Serial.println(thrust_g);
} 