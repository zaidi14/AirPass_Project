
# AirPass — Edge-Based Multi-Factor Physical Access Control System

**A split-brain edge security system combining RFID, biometric verification, and real-time gesture authentication for physical access control.**

---

## 1. SYSTEM SUMMARY

AirPass is an **edge-computed physical access control system** designed to eliminate single-factor RFID-based vulnerabilities through a multi-stage authentication pipeline.

The system enforces access decisions using a **Raspberry Pi-based policy engine** and a physically isolated **Arduino actuator layer**, ensuring that no single hardware component can independently grant access.

It is designed for:
- Secure physical environments
- Anti-cloning access control
- Edge AI authentication pipelines
- Fail-secure infrastructure design

---

## 2. SYSTEM ARCHITECTURE

### High-Level Flow

```text
RFID Reader → Raspberry Pi Policy Engine → Vision AI Challenge → Decision State Machine → Arduino Actuator

### Architecture Model

```text
        ┌──────────────────────────────┐
        │   Raspberry Pi (Brain)       │
        │  - State Machine             │
        │  - Vision AI (MediaPipe)     │
        │  - Policy Enforcement         │
        └─────────────┬────────────────┘
                      │ Serial (UART)
                      ▼
        ┌──────────────────────────────┐
        │   Arduino (Actuator Layer)   │
        │  - Servo Lock                │
        │  - RFID Reader Interface     │
        │  - Hardware Execution        │
        └──────────────────────────────┘
```

### Data Flow

```text
RFID UID
   ↓
Pi Policy Validation (whitelist.txt)
   ↓
Optional Face Authentication
   ↓
Timed Gesture Challenge (MediaPipe)
   ↓
Decision Engine (State Machine)
   ↓
UNLOCK / RESET Command to Arduino
   ↓
Physical Actuation + Telemetry Logging
```

---

## 3. THREAT & FAILURE MODEL

### Threat Model

AirPass assumes adversaries may attempt:

* RFID cloning or replay attacks
* Unauthorized physical proximity attacks
* Credential leakage (tag theft)
* Passive observation of entry patterns

### Failure Model

The system is explicitly designed to fail-safe under:

* Camera failure
* Serial communication loss
* Gesture timeout
* Sensor inconsistency
* Policy file corruption

### Security Principle

> The Arduino is never trusted to make decisions — only to execute them.

---

## 4. CORE ENGINEERING DESIGN

### 4.1 State Machine (Core System Logic)

```text
IDLE
  ↓ RFID detected
RFID_VALIDATION
  ↓ authorized
FACE_AUTH (optional)
  ↓ success
COUNTDOWN
  ↓ active challenge
GESTURE_VERIFICATION
  ↓ success
UNLOCK
  ↓ timeout
RESET (fail-safe)
```

---

### 4.2 Authentication Model

AirPass implements **multi-factor layered authentication**:

| Factor           | Type       | Purpose               |
| ---------------- | ---------- | --------------------- |
| RFID             | Possession | Identity trigger      |
| Face Recognition | Biometric  | Identity verification |
| Gesture Sequence | Behavioral | Intent verification   |

---

### 4.3 Trust Boundary Design

```text
TRUSTED ZONE:
- Raspberry Pi (decision authority)
- Vision AI pipeline

UNTRUSTED ZONE:
- Arduino microcontroller
- RFID reader input
- Physical actuator layer
```

---

## 5. OBSERVABILITY & TELEMETRY

The system logs:

* Unlock decision latency (ms)
* RFID validation events
* Gesture success/failure sequences
* Serial command acknowledgements

### Example Event Stream

```text
RFID_UID: B842DF12 → VALID
FACE_MATCH: TRUE
GESTURE: Fist → Peace → Open → SUCCESS
UNLOCK_LATENCY: 183ms
ACK:UNLOCK received
```

### Engineering Insight

This system treats authentication as a **measurable event pipeline**, not a binary decision.

---

## 6. DEPLOYMENT

### Requirements

* Raspberry Pi 5 (64-bit OS required)
* Arduino Uno
* Webcam
* Python 3.11+

---

### Setup

```bash
git clone https://github.com/YOUR_USERNAME/AirPass_Project.git
cd AirPass_Project

python3.11 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

---

### Run

```bash
SHOW_GUI=1 AIRPASS_REQUIRE_RFID=1 python3 main.py
```

---

### Production Mode

```bash
sudo systemctl enable --now airpass.service
```

---

## 7. DESIGN TRADEOFFS & LIMITATIONS

### Tradeoffs

* Increased security complexity vs usability
* Higher latency due to multi-factor pipeline
* Dependence on camera-based inference reliability

### Known Limitations

* Gesture recognition sensitive to lighting conditions
* Face authentication requires stable framing
* RFID still acts as initial trigger (not standalone secure)

### Future Improvements

* Replace gesture model with transformer-based pose estimation
* Add encrypted secure enclave for identity storage
* Introduce anomaly detection on access patterns
* Multi-node distributed authentication network

---

## 8. SYSTEM DESIGN PRINCIPLE

> Security is enforced through layered intent validation, not single-point identity verification.

AirPass is built on the principle that:

* possession is not identity
* biometrics are not sufficient
* intent must be actively demonstrated

---

## 9. REPOSITORY STRUCTURE

```text
secure-edge-authentication-system/
├── arduino/
├── src/
│   ├── main.py
│   ├── vision.py
│   ├── face_auth.py
│   ├── rfid_reader.py
│   └── arduino_comms.py
├── whitelist.txt
├── face_password.jpeg
└── requirements.txt
```

