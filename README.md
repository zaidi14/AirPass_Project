# AirPass_Project

Concise Pi-driven door/gesture auth node integrating RC522 RFID, camera face+gesture, and an Arduino actuator.

## Key changes (what we changed)
- Pi is now the master state machine (`main.py`): it receives `RFID_UID:<HEX>` messages from the Arduino, validates the UID against a runtime `whitelist.txt`, performs face-password verification (optional), runs the gesture sequence, then issues `UNLOCK`/`LOCK` commands to the Arduino.
- Arduino now only reports RFID scans as `RFID_UID:<HEX>` and performs actuations on Pi commands. Pi logs latency when Arduino ACKs `UNLOCK`.
- Whitelist moved out of code: `main.py` loads `whitelist.txt` (path configurable with `AIRPASS_WHITELIST_FILE`) and reloads it at each decision so edits take effect immediately. `AIRPASS_ALLOWED_TAGS` remains as a fallback for compatibility.

## How the workflow works (step-by-step)
1. A tag is presented to the RC522 on the Arduino.
2. Arduino prints `RFID_UID:<HEX>` to serial.
3. Pi reads the UID, reloads `whitelist.txt`, and accepts or denies.
4. If accepted, Pi runs face verification (if enabled). On face pass, Pi announces a short countdown.
5. Pi runs the configured gesture sequence. On success Pi sends `UNLOCK` to Arduino.
6. Arduino actuates (servo/LED/buzzer/LCD) and replies `ACK:UNLOCK`; Pi records unlock ACK latency.

## Files of interest
- `main.py` — master state machine; loads `whitelist.txt` and orchestrates face/gesture/unlock.
- `whitelist.txt` — one UID per line (created for you with captured UIDs).
- `arduino_comms.py` / `arduino/arduino.ino` — serial protocol and Arduino behavior (reports `RFID_UID:`; handles `UNLOCK`, `LOCK`, etc.).
- `vision.py`, `face_auth.py` — camera, gesture and face-password components.

## Whitelist usage
- Default file: `whitelist.txt` in the project root. Change path with `AIRPASS_WHITELIST_FILE` env var.
- Format: plain text, one UID per line. UIDs are normalized by removing `:` or `-` and converting to uppercase.

Add a UID (example):
```bash
cd ~/AirPass_Project
echo B842DF12 >> whitelist.txt
echo 63D5CD50 >> whitelist.txt
```

Remove a UID (example):
```bash
# edit with your preferred editor, or:
grep -v "B842DF12" whitelist.txt > whitelist.tmp && mv whitelist.tmp whitelist.txt
```

## Run on Pi (manual)
1. Install dependencies (once):
```bash
cd ~/AirPass_Project
python3 -m pip install -r requirements.txt
```
2. Run the node:
```bash
cd ~/AirPass_Project
python3 main.py
```
Notes:
- `whitelist.txt` in the project root is used by default. To override:
```bash
AIRPASS_WHITELIST_FILE=/path/to/my_whitelist.txt python3 main.py
```
- To skip RFID during quick tests: `AIRPASS_REQUIRE_RFID=0 python3 main.py`.

## Systemd service (recommended for autostart)
Create `/etc/systemd/system/airpass.service` (edit `User` and paths):

```ini
[Unit]
Description=AirPass Node
After=network.target

[Service]
User=oppenheimer
WorkingDirectory=/home/oppenheimer/AirPass_Project
ExecStart=/usr/bin/python3 /home/oppenheimer/AirPass_Project/main.py
Environment=AIRPASS_WHITELIST_FILE=/home/oppenheimer/AirPass_Project/whitelist.txt
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now airpass.service
sudo journalctl -u airpass.service -f
```

## Quick troubleshooting
- If a tag isn't recognized, ensure it's normalized in `whitelist.txt` (remove `:` separators).
- Confirm Arduino serial port (default `/dev/ttyACM0`) and that the board prints `RFID_UID:` on scan.
- For face/gesture issues, check the camera (`DISPLAY` for GUI) and MediaPipe availability; set `AIRPASS_SKIP_GESTURE=1` to test face-only flows.

---
This README documents the current Pi-first workflow and the exact commands to run the node on the Pi. If you want, I can add a small helper script to append detected UIDs automatically when you press a key.
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

SSH run command used for Pi + Arduino testing:

```bash
SHOW_GUI=1 AIRPASS_REQUIRE_RFID=0 ARDUINO_PORT=/dev/ttyUSB0 AIRPASS_REQUIRE_FACE_DURING_COUNTDOWN=0 python3 main.py
```

Face-password + custom gesture example:

```bash
AIRPASS_REQUIRE_FACE_ID=1 AIRPASS_FACE_REF_IMAGE=face_password.jpg AIRPASS_FACE_ID_THRESHOLD=0.62 AIRPASS_GESTURE_SEQUENCE="Fist->Peace->Open" SHOW_GUI=1 AIRPASS_REQUIRE_RFID=0 ARDUINO_PORT=/dev/ttyUSB0 python3 main.py
```

## Important Environment Variables

- `ARDUINO_PORT` default: `/dev/ttyACM0`
- `AIRPASS_REQUIRE_RFID` default: `0`
  - `1` to require RFID before face/gesture
- `AIRPASS_REQUIRE_FACE_ID` default: `0`
  - `1` to require face-password verification (reference face match) before gesture stage
- `AIRPASS_FACE_REF_IMAGE` default: `face_password.jpg`
  - path to the reference image used for face-password verification
- `AIRPASS_FACE_ID_THRESHOLD` default: `0.60`
  - cosine threshold for face-password match (raise for stricter verification)
- `AIRPASS_ALLOWED_TAGS` default: empty
  - comma-separated UIDs, example: `A1B2C3D4,11223344`
- `AIRPASS_SKIP_ARDUINO` default: `0`
  - set `1` for vision-only testing
- `AIRPASS_SKIP_GESTURE` default: `0`
  - set `1` to test face -> unlock directly
- `AIRPASS_FACE_TIMEOUT` default: `5.0`
- `AIRPASS_FACE_STABLE_SECONDS` default: `0.4`
- `AIRPASS_COUNTDOWN_SECONDS` default: `2.0`
- `AIRPASS_REQUIRE_FACE_DURING_COUNTDOWN` default: `0`
  - set `1` for strict mode (reset if face is lost during countdown)
- `AIRPASS_GESTURE_TIMEOUT` default: `8.0`
  - timeout window resets after each accepted step in the sequence
- `AIRPASS_GESTURE_SEQUENCE` default: `Fist->Peace->Open`
  - supported gestures are `Fist`, `Peace`, and `Open`
  - example: `AIRPASS_GESTURE_SEQUENCE="Fist->Open"`
- `AIRPASS_ALLOW_ARDUINO_BYPASS_ON_FAIL` default: `1`
- `AIRPASS_GESTURE_HOLD_FRAMES` default: `7`
  - constrained to `7..10` to smooth jitter and reject single-frame false positives
- `AIRPASS_LATENCY_CSV` default: `unlock_latency.csv`
  - logs UNLOCK send -> Arduino `ACK:UNLOCK` roundtrip in milliseconds
- `SHOW_GUI` default: `1`
  - set `0` to run headless and skip the OpenCV preview window
- `AIRPASS_UNLOCK_HOLD_SECONDS` default: `1.5`
  - how long latch stays open before `LOCK` is sent
- `AIRPASS_CAMERA_WIDTH` default: `640`
- `AIRPASS_CAMERA_HEIGHT` default: `480`
- `AIRPASS_CAMERA_FPS` default: `24`

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

If `mediapipe==0.10.18` is already present on the Pi package index, that is the intended aarch64 wheel for this project.

## Arduino Sketch

Use:

- `arduino/arduino.ino`

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



export DISPLAY=:0
export XAUTHORITY=/home/oppenheimer/.Xauthority
export AIRPASS_WHITELIST_FILE=/home/oppenheimer/AirPass_Project/whitelist.txt
export AIRPASS_REQUIRE_RFID=1
export AIRPASS_REQUIRE_FACE_ID=0
export AIRPASS_SKIP_GESTURE=0
export AIRPASS_FULLSCREEN=1
export SHOW_GUI=1

python main.py