# AirPass Project (Raspberry Pi Brain + Arduino Muscle)

This project follows the split-brain architecture:

- Raspberry Pi 5: vision + authentication state machine
- Arduino Uno: servo/buzzer/LED/SSD1306 OLED actuation
- Communication bridge: UART serial (USB)

## v1 Workflow (Current Default)

1. Face detection (stable face required)
2. 5-second countdown
3. Gesture sequence check: `Fist -> Peace -> Open`
4. If valid: unlock command to Arduino (`UNLOCK`), then lock after hold time (`LOCK`)

## v1.1 Workflow (RFID First)

Enable RFID-gated flow:

1. RFID check
2. Face detection
3. 5-second countdown
4. Gesture sequence
5. Unlock on success

## Raspberry Pi Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

Run:

```bash
python3 main.py
```

## Important Environment Variables

- `ARDUINO_PORT` default: `/dev/ttyACM0`
- `AIRPASS_REQUIRE_RFID` default: `0`
  - `1` to require RFID before face/gesture
- `AIRPASS_ALLOWED_TAGS` default: empty
  - comma-separated UIDs, example: `A1B2C3D4,11223344`
- `AIRPASS_SKIP_ARDUINO` default: `0`
  - set `1` for vision-only testing
- `AIRPASS_SKIP_GESTURE` default: `0`
  - set `1` to test face -> unlock directly
- `AIRPASS_FACE_TIMEOUT` default: `5.0`
- `AIRPASS_FACE_STABLE_SECONDS` default: `0.8`
- `AIRPASS_COUNTDOWN_SECONDS` default: `5.0`
- `AIRPASS_REQUIRE_FACE_DURING_COUNTDOWN` default: `0`
  - set `1` for strict mode (reset if face is lost during countdown)
- `AIRPASS_GESTURE_TIMEOUT` default: `5.0`
- `AIRPASS_ALLOW_ARDUINO_BYPASS_ON_FAIL` default: `1`
- `AIRPASS_GESTURE_HOLD_FRAMES` default: `8`
  - constrained to `7..10` to smooth jitter and reject single-frame false positives
- `AIRPASS_LATENCY_CSV` default: `unlock_latency.csv`
  - logs UNLOCK send -> Arduino `ACK:UNLOCK` roundtrip in milliseconds
- `SHOW_GUI` default: `1`
  - set `0` to run headless and skip the OpenCV preview window

## Raspberry Pi 5 Gesture Backend

Pi 5 on 64-bit aarch64 should use the official `mediapipe` wheel, not `mediapipe-rpi4`.

Rebuild the venv after updating dependencies:

```bash
cd ~/AirPass_Project
rm -rf .venv311
python3.11 -m venv .venv311
source .venv311/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python -c "import mediapipe as mp; print(mp.__version__)"
```

If that import works, the app should switch from OpenCV fallback to MediaPipe hands and show the gesture landmarks/overlay.

## Arduino Sketch

Use:

- `arduino/airpass_uno.ino`

Hardware this sketch drives:

- SG90 servo (lock)
- Buzzer
- Green/Red LEDs
- SSD1306 OLED (I2C, address `0x3C`)

Arduino library dependencies:

- `Adafruit GFX Library`
- `Adafruit SSD1306`

### Default Pin Mapping (edit in sketch as needed)

- Servo: D9
- Buzzer: D6
- Green LED: D3
- Red LED: D4

## Serial Command Protocol (Pi -> Arduino)

- `RFID_OK`, `RFID_DENY`
- `FACE_OK`, `FACE_TIMEOUT`, `FACE_LOST`
- `COUNTDOWN:N`
- `GESTURE_START`
- `GESTURE_OK:<name>`, `GESTURE_FAIL:<name>`, `GESTURE_TIMEOUT`, `GESTURE_SEQUENCE_OK`
- `UNLOCK`, `LOCK`

## Robustness Notes

- Camera reconnect loop handles unplug/replug events with 1-second retry.
- Authentication state machine resets on timeouts/wrong gestures.
- Face must be stable for a short window before advancing.
- Pi serial listener writes latency samples to CSV for engineering analysis.
