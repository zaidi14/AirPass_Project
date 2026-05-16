# AirPass: Multi-Factor Air-Gapped Physical Access Control

**An Edge-Powered IoT Solution for Zero-Touch Gesture & Biometric Security**

---

## Project Overview

AirPass is a **real-time, edge-powered physical access control node**. It upgrades traditional (and easily cloned) RFID systems by integrating a secondary, edge-based computer vision layer. By requiring active gesture sequences and facial verification to trigger a physical unlock, AirPass provides a highly configurable, multi-factor smart-lock system.

### Key Features

* ✅ **Multi-Factor Authentication** combining RFID, facial recognition, and dynamic hand gestures.
* ✅ **Split-Brain Architecture** ensuring physical actuators (Arduino) cannot self-authorize without the policy engine (Raspberry Pi).
* ✅ **Edge AI Processing** using MediaPipe and OpenCV on aarch64 for local, low-latency inference.
* ✅ **Fail-Secure State Machine** that instantly resets and remains mechanically locked on camera failure, serial drop, or timeout.
* ✅ **Hot-Reloadable Policy** via a runtime `whitelist.txt`—no system reboots required to grant or revoke access.
* ✅ **Telemetry Logging** capturing end-to-end unlock latency for engineering analysis.

---

## Problem Statement & Motivation

**Physical Security Challenge:** Traditional access systems rely on single-factor authentication (RFID cards or keys). These are susceptible to theft, cloning (e.g., using a Flipper Zero), or loss.

* A cloned card grants immediate, unquestioned access.
* Standard biometric systems are expensive, proprietary, and often require physical touch.

**Our Solution:** Deploy a multi-layered, split-brain IoT node. RFID acts merely as an *initiation trigger*. True authorization requires the physical presence of the authorized user (Facial ID) and active intent (Gesture Sequence challenge), completely neutralizing stolen or cloned RFID tags.

---

## System Architecture

### Hardware Stack

| Component | Specification | Purpose |
| --- | --- | --- |
| **Raspberry Pi 5** | 8GB RAM, 32GB SD Card | The "Brain": Master state machine, runs Vision AI (MediaPipe), manages policies. |
| **Arduino Uno R3** | ATmega328P Microcontroller | The "Muscle": Hardware actuator and sensor interface. |
| **USB Webcam** | Standard physical webcam (640x480) | Captures real-time frames for Face & Gesture detection. |
| **RFID Reader** | RC522 Module | Reads RFID Keyfobs and Cards (Factor 1). |
| **Servo Motor** | SG90 / Standard Micro Servo | Actuates the physical deadbolt/latch. |

### Software Stack

| Layer | Technology | Role |
| --- | --- | --- |
| **Edge AI** | MediaPipe Hands, OpenCV | Hand landmark detection and facial reference matching. |
| **Control Logic** | Python 3.11 | State machine orchestration, whitelist validation. |
| **Connectivity** | `pyserial` (UART over USB) | Fail-secure bridge protocol between Pi and Arduino. |
| **Embedded** | C++ (Arduino) | Actuator control, raw sensor polling. |
| **OS Level** | `systemd` | Daemonization, auto-start, and fault recovery. |

### Data Flow

```text
[RFID Scanned] → UID detected by RC522 
                    ↓
[UART Serial]  → "RFID_UID:<HEX>" sent to Pi
                    ↓
[Policy Check] → Pi validates UID against whitelist.txt
                    ↓
[Vision AI]    → YES: Activate Camera → Require Facial Match (Optional)
                 NO: Reset to IDLE
                    ↓
[Challenge]    → Initiate 5-second countdown → Prompt for Gesture Sequence
                    ↓
[Inference]    → MediaPipe verifies (e.g., Fist → Peace → Open)
                    ↓
[Actuation]    → SUCCESS: Pi sends "UNLOCK" via Serial
                    ↓
[Hardware]     → Arduino rotates Servo → Delays → Auto-locks → replies "ACK:UNLOCK"

```

### State Machine (Raspberry Pi Master)

```text
IDLE
 ↓ (RFID Scanned)
RFID_CHECK → Validates against runtime whitelist
 ↓ (Authorized)
FACE_AUTH → Requires stable face match (Configurable)
 ↓ (Matched)
COUNTDOWN → 5-second visual/audio prep window
 ↓ (Complete)
GESTURE_CHALLENGE → Monitors MediaPipe stream for sequence execution
 ↓ (Sequence correct before timeout)
UNLOCK → Transmit command to Arduino, log latency, wait
 ↓ (Hold time expires)
RESET → Return to IDLE

```

---

## Hardware Setup

### Components List

| Item | Qty | Role |
| --- | --- | --- |
| Raspberry Pi 5 (8GB) | 1 | Master compute node |
| 32GB MicroSD Card | 1 | Pi OS and application storage |
| Arduino Uno R3 | 1 | Hardware controller |
| Physical Webcam | 1 | Vision input |
| RC522 RFID Reader | 1 | Tag scanner |
| RFID Keyfob / Card | 1+ | User credentials |
| Servo Motor | 1 | Lock actuator |
| Breadboard | 1 | Prototyping base |
| Jumper Cables (M/M, M/F) | Set | Component wiring |
| USB Cables | 2 | Pi Power & Arduino-to-Pi Serial Bridge |

### Wiring Summary (Arduino)

* **RC522 (SPI):** SDA(10), SCK(13), MOSI(11), MISO(12), RST(9)
* **Servo Motor:** PWM Pin 6
* *(Optional status LEDs and Buzzers can be mapped directly in `arduino/arduino.ino`)*

---

## Software Installation & Deployment

### Prerequisites

* Raspberry Pi running a 64-bit OS (aarch64 required for MediaPipe).
* Arduino IDE for flashing the Uno.
* Python 3.11+.

### Step 1: Flash Arduino Firmware

1. Open `arduino/arduino.ino` in the Arduino IDE.
2. Select **Board:** Arduino Uno.
3. Select the correct COM port.
4. Click **Upload**.

### Step 2: Raspberry Pi Environment Setup

Connect the Arduino to the Pi via USB, plug in the webcam, and run the following on the Pi:

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/AirPass_Project.git
cd AirPass_Project

# Create and activate virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies 
pip install --upgrade pip
pip install -r requirements.txt

```

### Step 3: Run as a Systemd Service (Production)

To ensure AirPass starts automatically on boot and recovers from crashes:

```bash
sudo cp systemd/airpass.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now airpass.service

```

---

## Usage & Operation

### Access Management (Whitelist)

The system hot-reloads `whitelist.txt` on every scan. UIDs must be normalized (uppercase, no colons).

```bash
# Add an allowed user (takes effect immediately)
echo "B842DF12" >> whitelist.txt

# Remove a user
grep -v "B842DF12" whitelist.txt > whitelist.tmp && mv whitelist.tmp whitelist.txt

```

### Running the Node Manually

AirPass is fully managed via environment variables.

**Interactive Execution (GUI Enabled, perfect for testing):**

```bash
SHOW_GUI=1 AIRPASS_REQUIRE_RFID=1 AIRPASS_GESTURE_SEQUENCE="Fist->Peace->Open" python3 main.py

```

**High-Security Mode (Headless, Face-ID + Gesture + RFID):**

```bash
SHOW_GUI=0 AIRPASS_REQUIRE_RFID=1 AIRPASS_REQUIRE_FACE_ID=1 AIRPASS_GESTURE_SEQUENCE="Fist->Peace->Open" python3 main.py

```

### Configuration Variables

| Variable | Default | Description |
| --- | --- | --- |
| `ARDUINO_PORT` | `/dev/ttyACM0` | Serial port for the Arduino bridge. |
| `AIRPASS_REQUIRE_RFID` | `0` | Set `1` to require an RFID scan before the vision challenge. |
| `AIRPASS_REQUIRE_FACE_ID` | `0` | Set `1` to require strict facial password matching against `face_password.jpg`. |
| `AIRPASS_GESTURE_SEQUENCE` | `Fist->Peace->Open` | The sequence required to trigger an unlock. |
| `AIRPASS_WHITELIST_FILE` | `./whitelist.txt` | Path to the active RFID policy list. |
| `SHOW_GUI` | `1` | Set `0` for headless operation (saves CPU overhead). |
| `AIRPASS_UNLOCK_HOLD_SECONDS` | `1.5` | Duration the actuator remains open before auto-locking. |

---

## Security Model & Edge AI Integration

### 1. Split-Brain Trust Boundary

The Arduino is intentionally treated as an **untrusted actuator**. It cannot make unlock decisions. It only reports environmental data (`RFID_UID`) and executes explicit `UNLOCK` commands. The Raspberry Pi retains absolute authority over the state machine.

### 2. RFID Replay Mitigation

Standard RFID authentication is vulnerable to replay attacks and tag cloning. AirPass mitigates this by using RFID strictly as Factor 1. True authorization requires secondary biometric verification and a dynamic, time-sensitive gesture challenge (Factor 2). A stolen tag without the owner's face and gesture knowledge is useless.

### 3. Fail-Secure Design

The system defaults to a mechanically locked state. In the event of:

* Camera failure / disconnection
* Serial bridge failure
* Gesture challenge timeout
The authentication loop immediately resets, no `UNLOCK` payload is transmitted, and the physical area remains secured.

---

## Repository Structure

```text
secure-edge-authentication-system/
├── arduino/
│   ├── arduino.ino                 # C++ firmware for the Arduino Uno
│   └── Hardware_Tests/
│       ├── I2C _SCANNER            # Arduino I2C scanner test
│       ├── LED                     # LED test script
│       ├── RFID                    # RFID hardware test
│       └── SERVO                   # Servo motor test
├── src/
│   ├── arduino_comms.py            # Serial protocol bridge
│   ├── face_auth.py                # Facial verification handlers
│   ├── main.py                     # Core state machine orchestration
│   ├── rfid_reader.py              # RFID reader integration
│   └── vision.py                   # MediaPipe/OpenCV gesture detection logic
├── face_password.jpeg              # Reference image for facial verification
├── requirements.txt                # Python dependencies
├── whitelist.txt                   # Active RFID policy file
└── README.md                       # Project documentation
```

---

## Video Demo
* [AirPass Live Hardware Demonstration](https://www.google.com/search?q=%23) *(Video link coming soon)*
