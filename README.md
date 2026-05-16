
# AirPass

AirPass is a multi-factor, air-gapped physical access control node. It upgrades traditional (and easily cloned) RFID systems by integrating a secondary, edge-based computer vision layer requiring active gesture and facial verification to trigger a physical unlock.

---

## 🏗 Architecture & Security Model

The system utilizes a **split-brain architecture** to enforce a strict security boundary between the decision engine and the physical actuator.

* **The Brain (Raspberry Pi 5):** Acts as the master state machine. It manages the `whitelist.txt` policy, runs the MediaPipe/OpenCV vision models, and validates authentication logic.
* **The Muscle (Arduino Uno):** Acts purely as a sensor and actuator. It reads raw RFID scans and toggles the physical lock (servo/LEDs/buzzer) **only** when explicitly commanded by the Pi. It cannot self-authorize.
* **Fail-Secure Bridge:** The two communicate via a USB Serial (UART) bridge. If the camera fails, the serial connection drops, or a gesture times out, the Pi instantly resets the state machine and the Arduino remains mechanically locked.

---

## ⚙️ Authentication Workflow

By default, the system enforces a strict, multi-stage pipeline:

1. **RFID Trigger:** User presents a tag to the Arduino. The UID is sent to the Pi and validated against the hot-reloaded `whitelist.txt`.
2. **Biometric Lock (Optional):** Pi requires a stable facial match against a reference image (`face_password.jpg`).
3. **Visual Challenge:** A 5-second countdown initiates.
4. **Dynamic Gesture:** User must perform a configured sequence (e.g., `Fist -> Peace -> Open`) before the timeout.
5. **Actuation:** Pi transmits the `UNLOCK` payload. Arduino actuates the lock, waits the hold duration, and automatically secures it via a `LOCK` command. Pi logs the round-trip latency to `unlock_latency.csv`.

---

## 🚀 Quick Start & Deployment

### 1. Hardware Setup

Flash `arduino/arduino.ino` to your Arduino Uno. Connect it via USB to the Raspberry Pi 5. Ensure your webcam is mounted and connected.

### 2. Software Installation

```bash
git clone https://github.com/YOUR_USERNAME/AirPass_Project.git
cd AirPass_Project
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies (requires aarch64 environment for MediaPipe)
pip install --upgrade pip
pip install -r requirements.txt

```

### 3. Access Management

Add valid normalized UIDs (no colons, uppercase) to the whitelist. The system hot-reloads this file on every scan.

```bash
echo "B842DF12" >> whitelist.txt

```

### 4. Running the Node

AirPass is managed entirely via environment variables.

**Standard Interactive Execution (GUI Enabled):**

```bash
SHOW_GUI=1 AIRPASS_REQUIRE_RFID=1 AIRPASS_GESTURE_SEQUENCE="Fist->Peace->Open" python3 main.py

```

**Production Daemon (Headless via systemd):**

```bash
sudo cp systemd/airpass.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now airpass.service

```

---

## 🎛 Configuration Variables

Modify these environment variables at runtime to adjust the security strictness.

| Variable | Default | Description |
| --- | --- | --- |
| `ARDUINO_PORT` | `/dev/ttyACM0` | Serial port for the Arduino bridge. |
| `AIRPASS_REQUIRE_RFID` | `0` | Set `1` to require an RFID scan before the vision challenge. |
| `AIRPASS_REQUIRE_FACE_ID` | `0` | Set `1` to require strict facial password matching. |
| `AIRPASS_GESTURE_SEQUENCE` | `Fist->Peace->Open` | The sequence required to trigger an unlock. |
| `AIRPASS_WHITELIST_FILE` | `./whitelist.txt` | Path to the active RFID policy list. |
| `SHOW_GUI` | `1` | Set `0` for headless operation (saves CPU overhead). |
| `AIRPASS_UNLOCK_HOLD_SECONDS` | `1.5` | Duration the actuator remains open before auto-locking. |
