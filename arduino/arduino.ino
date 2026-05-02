#include <Servo.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <SPI.h>
#include <MFRC522.h>

// ------------------------
// Hardware Pin Mapping
// ------------------------
const int SERVO_PIN = 9;
const int BUZZER_PIN = 6;
const int LED_GREEN_PIN = 3;
const int LED_RED_PIN = 4;
const int RC522_SS_PIN = 10;
const int RC522_RST_PIN = 2;

// Servo angles for your latch geometry
const int LOCK_ANGLE = 10;
const int UNLOCK_ANGLE = 95;
// RFID setup
MFRC522 mfrc522(RC522_SS_PIN, RC522_RST_PIN);
unsigned long lastRfidCheck = 0;
unsigned long rfidCheckInterval = 500;  // Check every 500ms to avoid spam

// LCD setup (16x2 with I2C backpack at 0x27)
// If your LCD doesn't work, try 0x3F instead of 0x27
LiquidCrystal_I2C lcd(0x27, 16, 2);

Servo lockServo;

String lastGesture = "-";
bool rfidVerified = false;

void setStatusLeds(bool greenOn, bool redOn) {
  digitalWrite(LED_GREEN_PIN, greenOn ? HIGH : LOW);
  digitalWrite(LED_RED_PIN, redOn ? HIGH : LOW);
}

void showTwoLine(const String &line1, const String &line2) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(line1.substring(0, 16));  // Max 16 chars per line
  lcd.setCursor(0, 1);
  lcd.print(line2.substring(0, 16));
}

void shortBeep(int freq, int ms) {
  tone(BUZZER_PIN, freq, ms);
}

void accessGrantedPattern() {
  shortBeep(1800, 120);
  delay(140);
  shortBeep(2200, 120);
}

void denyPattern() {
  shortBeep(350, 220);
  delay(240);
  shortBeep(300, 260);
}

void setLockedUi() {
  lockServo.write(LOCK_ANGLE);
  setStatusLeds(false, true);
  showTwoLine("SYSTEM LOCKED", "Waiting auth...");
}

// Convert RFID UID bytes to hex string
String getUidString(MFRC522::Uid *uid) {
  String uidStr = "";
  for (byte i = 0; i < uid->size; i++) {
    if (uid->uidByte[i] < 0x10) {
      uidStr += "0";
    }
    uidStr += String(uid->uidByte[i], HEX);
  }
  uidStr.toUpperCase();
  return uidStr;
}

// Check for RFID card presence and validate
void checkRfid() {
  unsigned long now = millis();
  if (now - lastRfidCheck < rfidCheckInterval) {
    return;  // Skip if checking too frequently
  }
  lastRfidCheck = now;

  // Look for new cards
  if (!mfrc522.PICC_IsNewCardPresent()) {
    return;
  }

  // Select one of the cards
  if (!mfrc522.PICC_ReadCardSerial()) {
    return;
  }

  // Get UID and log it
  String cardUID = getUidString(&mfrc522.uid);
  // Report UID to host (Pi). Do not autonomously accept/deny or change LEDs/display.
  Serial.print("RFID_UID:");
  Serial.println(cardUID);
  showTwoLine("RFID DETECTED", cardUID);

  // Halt PICC and stop crypto — host (Pi) will decide next actions.
  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();
}

void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) {
    return;
  }

  // Send ACK immediately so Pi-side roundtrip reflects link latency,
  // not buzzer/servo/display action time.
  Serial.print("ACK:");
  Serial.println(cmd);

  if (cmd == "RFID_OK") {
    showTwoLine("RFID OK", "Proceed to face");
    setStatusLeds(false, true);
  } else if (cmd == "FACE_ID_OK") {
    showTwoLine("FACE PASSWORD", "Verified");
  } else if (cmd == "RFID_DENY") {
    showTwoLine("RFID DENIED", "Try again");
    denyPattern();
    setLockedUi();
  } else if (cmd == "FACE_OK") {
    showTwoLine("FACE VERIFIED", "Hold still...");
  } else if (cmd == "FACE_TIMEOUT") {
    showTwoLine("FACE TIMEOUT", "Restart flow");
    setLockedUi();
  } else if (cmd == "FACE_LOST") {
    showTwoLine("FACE LOST", "Restart flow");
    setLockedUi();
  } else if (cmd.startsWith("COUNTDOWN:")) {
    String value = cmd.substring(String("COUNTDOWN:").length());
    showTwoLine("Gesture in", value + " sec");
  } else if (cmd == "GESTURE_START") {
    lastGesture = "-";
    showTwoLine("Do Gesture Seq", "Fist->Peace->Open");
  } else if (cmd.startsWith("GESTURE_PATTERN:")) {
    String pattern = cmd.substring(String("GESTURE_PATTERN:").length());
    showTwoLine("Gesture Pattern", pattern.substring(0, min((int)pattern.length(), 16)));
  } else if (cmd.startsWith("GESTURE_OK:")) {
    lastGesture = cmd.substring(String("GESTURE_OK:").length());
    showTwoLine("Gesture OK", lastGesture);
    shortBeep(1200, 80);
  } else if (cmd == "GESTURE_SEQUENCE_OK") {
    showTwoLine("Gesture Passed", "Unlocking...");
  } else if (cmd.startsWith("GESTURE_FAIL:")) {
    String wrong = cmd.substring(String("GESTURE_FAIL:").length());
    showTwoLine("Gesture FAIL", wrong);
    denyPattern();
    setLockedUi();
  } else if (cmd == "GESTURE_TIMEOUT") {
    showTwoLine("Gesture Timeout", "Restart flow");
    setLockedUi();
  } else if (cmd == "UNLOCK") {
    lockServo.write(UNLOCK_ANGLE);
    setStatusLeds(true, false);
    showTwoLine("ACCESS GRANTED", "Door unlocked");
    accessGrantedPattern();
  } else if (cmd == "LOCK") {
    setLockedUi();
  } else {
    showTwoLine("Unknown cmd", cmd.substring(0, min((int)cmd.length(), 16)));
  }
}

void setup() {
  Serial.begin(115200);
  Serial.println("AIRPASS:BOOT");

  // Initialize SPI for RC522
  SPI.begin();
  mfrc522.PCD_Init(RC522_SS_PIN, RC522_RST_PIN);
  Serial.println("AIRPASS:RC522_INIT_DONE");

  // Initialize LCD
  lcd.init();
  lcd.backlight();

  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_GREEN_PIN, OUTPUT);
  pinMode(LED_RED_PIN, OUTPUT);

  lockServo.attach(SERVO_PIN);

  setLockedUi();
  showTwoLine("AirPass UNO", "Serial ready");
  delay(1200);
  setLockedUi();
  Serial.println("AIRPASS:READY");
}

void loop() {
  static unsigned long lastIdleUi = 0;

  // Check for RFID card
  checkRfid();

  if (millis() - lastIdleUi > 2000) {
    lastIdleUi = millis();
    Serial.println("AIRPASS:WAITING_RFID");
  }

  // Handle serial commands from Pi
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    handleCommand(cmd);
  }
}
