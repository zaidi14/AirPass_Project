#include <Servo.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ------------------------
// Hardware Pin Mapping
// ------------------------
const int SERVO_PIN = 9;
const int BUZZER_PIN = 6;
const int LED_GREEN_PIN = 3;
const int LED_RED_PIN = 4;

// Servo angles for your latch geometry
const int LOCK_ANGLE = 10;
const int UNLOCK_ANGLE = 95;
const int OLED_WIDTH = 128;
const int OLED_HEIGHT = 64;
const int OLED_RESET = -1;

Servo lockServo;
Adafruit_SSD1306 oled(OLED_WIDTH, OLED_HEIGHT, &Wire, OLED_RESET);

String lastGesture = "-";

void setStatusLeds(bool greenOn, bool redOn) {
  digitalWrite(LED_GREEN_PIN, greenOn ? HIGH : LOW);
  digitalWrite(LED_RED_PIN, redOn ? HIGH : LOW);
}

void showTwoLine(const String &line1, const String &line2) {
  oled.clearDisplay();
  oled.setTextSize(1);
  oled.setTextColor(SSD1306_WHITE);
  oled.setCursor(0, 8);
  oled.println(line1);
  oled.setCursor(0, 30);
  oled.println(line2);
  oled.display();
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

void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) {
    return;
  }

  if (cmd == "RFID_OK") {
    showTwoLine("RFID OK", "Proceed to face");
    setStatusLeds(false, true);
  } else if (cmd == "RFID_DENY") {
    showTwoLine("RFID DENIED", "Try again");
    denyPattern();
    setLockedUi();
  } else if (cmd == "FACE_OK") {
    showTwoLine("FACE VERIFIED", "Hold still...");
  } else if (cmd == "FACE_TIMEOUT") {
    showTwoLine("FACE TIMEOUT", "Restart flow");
    denyPattern();
    setLockedUi();
  } else if (cmd == "FACE_LOST") {
    showTwoLine("FACE LOST", "Restart flow");
    denyPattern();
    setLockedUi();
  } else if (cmd.startsWith("COUNTDOWN:")) {
    String value = cmd.substring(String("COUNTDOWN:").length());
    showTwoLine("Gesture in", value + " sec");
  } else if (cmd == "GESTURE_START") {
    lastGesture = "-";
    showTwoLine("Do Gesture Seq", "Fist->Peace->Open");
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
    denyPattern();
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

  Serial.print("ACK:");
  Serial.println(cmd);
}

void setup() {
  Serial.begin(115200);

  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_GREEN_PIN, OUTPUT);
  pinMode(LED_RED_PIN, OUTPUT);

  lockServo.attach(SERVO_PIN);

  if (!oled.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("OLED_INIT_FAIL");
    while (true) {
      delay(100);
    }
  }

  setLockedUi();
  showTwoLine("AirPass UNO", "Serial ready");
  delay(1200);
  setLockedUi();
}

void loop() {
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    handleCommand(cmd);
  }
}
