# 🔹 Load Cell → HX711 Connections

| Wire Color | Load Cell Signal       | Connect To (HX711) | Description                               |
|------------|------------------------|--------------------|-------------------------------------------|
| 🔴 Red     | E+ (Excitation +)      | E+                 | Positive supply to Wheatstone bridge      |
| ⚫ Black   | E− (Excitation −)      | E−                 | Ground reference for bridge               |
| 🟢 Green   | A+ (Signal +)          | A+                 | Positive differential output              |
| ⚪ White   | A− (Signal −)          | A−                 | Negative differential output              |


# 🔹 HX711 → Arduino Mega 2560 Connections

| HX711 Pin | Wire Type | Connect To (Arduino Mega) | Purpose                          |
|-----------|-----------|---------------------------|----------------------------------|
| VCC    | Power     | 5V                        | Power supply to HX711            |
| GND    | Ground    | GND                       | Common ground reference           |
| DT     | Digital   | 36 (or check the .ino file)       | Data output from HX711           |
| SCK    | Digital   | 38 (or check the .ino file)       | Clock input from Arduino         |