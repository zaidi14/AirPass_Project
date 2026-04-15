import os
import threading
import time
import math
import csv
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import cv2

from arduino_comms import ArduinoComms
from rfid_reader import RFIDReader
from vision import VisionProcessor

GESTURE_SEQUENCE = ["Fist", "Peace", "Open"]
FACE_TIMEOUT_SECONDS = 5.0
FACE_STABLE_SECONDS = 0.8
COUNTDOWN_SECONDS = 5.0
GESTURE_TIMEOUT_SECONDS = 5.0
UNLOCK_HOLD_SECONDS = 5.0
CAMERA_RETRY_SECONDS = 1.0
DEFAULT_GESTURE_HOLD_FRAMES = 8
SHOW_GUI = int(os.environ.get("SHOW_GUI", 1))


class SharedState:
	def __init__(self):
		self._lock = threading.Lock()
		self.face_detected = False
		self.camera_online = False
		self.gesture_events = deque(maxlen=30)

	def update_vision(self, face_detected: bool, gesture_locked: Optional[str], camera_online: bool) -> None:
		with self._lock:
			self.face_detected = face_detected
			self.camera_online = camera_online
			if gesture_locked:
				self.gesture_events.append(gesture_locked)

	def set_camera_offline(self) -> None:
		with self._lock:
			self.camera_online = False
			self.face_detected = False

	def has_face(self) -> bool:
		with self._lock:
			return self.face_detected

	def is_camera_online(self) -> bool:
		with self._lock:
			return self.camera_online

	def pop_gesture_event(self) -> Optional[str]:
		with self._lock:
			if not self.gesture_events:
				return None
			return self.gesture_events.popleft()

	def clear_gesture_events(self) -> None:
		with self._lock:
			self.gesture_events.clear()

	def push_gesture_event(self, gesture: str) -> None:
		with self._lock:
			self.gesture_events.append(gesture)


def camera_worker(shared: SharedState, stop_event: threading.Event, camera_index: int = 0) -> None:
	gesture_hold_frames = int(os.getenv("AIRPASS_GESTURE_HOLD_FRAMES", str(DEFAULT_GESTURE_HOLD_FRAMES)))
	try:
		processor = VisionProcessor(gesture_hold_frames=gesture_hold_frames)
	except Exception as exc:
		print(f"[Vision] Failed to initialize processor: {exc}")
		stop_event.set()
		return
	capture = None
	skip_gesture = os.getenv("AIRPASS_SKIP_GESTURE", "0").strip().lower() in {"1", "true", "yes", "on"}
	preferred_backend = cv2.CAP_V4L2 if hasattr(cv2, "CAP_V4L2") else 0

	def open_capture(index: int):
		if preferred_backend:
			return cv2.VideoCapture(index, preferred_backend)
		return cv2.VideoCapture(index)

	if not skip_gesture and not processor.gesture_enabled:
		print("[Vision] Gesture testing requested but MediaPipe gesture backend is unavailable.")
		print("[Vision] Set AIRPASS_SKIP_GESTURE=1 for face-only mode, or install a compatible MediaPipe build.")
		stop_event.set()
		processor.close()
		return

	try:
		while not stop_event.is_set():
			try:
				if capture is None:
					capture = open_capture(camera_index)
					capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
					capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
					capture.set(cv2.CAP_PROP_FPS, 30)
					capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
					capture.set(cv2.CAP_PROP_CONVERT_RGB, 1)

					if not capture.isOpened():
						print("[Camera] Capture unavailable. Retrying in 1 second...")
						shared.set_camera_offline()
						capture.release()
						capture = None
						time.sleep(CAMERA_RETRY_SECONDS)
						continue

				ok, frame = capture.read()
				if not ok:
					print("[Camera] Frame read failed. Camera may be unplugged. Retrying in 1 second...")
					shared.set_camera_offline()
					capture.release()
					capture = None
					time.sleep(CAMERA_RETRY_SECONDS)
					continue

				face_detected, gesture_locked, rendered = processor.process_frame(frame)
				shared.update_vision(face_detected, gesture_locked, camera_online=True)

				if SHOW_GUI == 1:
					cv2.imshow("AirPass Security Node", rendered)
					key = cv2.waitKey(1) & 0xFF
					if key == ord("1"):
						shared.push_gesture_event("Fist")
						print("[Debug] Injected gesture: Fist")
					elif key == ord("2"):
						shared.push_gesture_event("Peace")
						print("[Debug] Injected gesture: Peace")
					elif key == ord("3"):
						shared.push_gesture_event("Open")
						print("[Debug] Injected gesture: Open")
					if key in (ord("q"), 27):
						stop_event.set()

			except Exception as exc:
				print(f"[Camera] Exception in capture loop: {exc}. Retrying in 1 second...")
				shared.set_camera_offline()
				if capture is not None:
					capture.release()
					capture = None
				time.sleep(CAMERA_RETRY_SECONDS)

	finally:
		if capture is not None:
			capture.release()
		processor.close()


def _safe_wait(stop_event: threading.Event, seconds: float) -> bool:
	"""Returns False if stop requested during wait, True otherwise."""
	return not stop_event.wait(seconds)


def _init_latency_csv(csv_path: Path) -> None:
	if csv_path.exists():
		return

	with csv_path.open("w", newline="", encoding="utf-8") as handle:
		writer = csv.writer(handle)
		writer.writerow(["timestamp_utc", "event", "latency_ms"])


def _append_latency(csv_path: Path, event: str, latency_ms: float) -> None:
	with csv_path.open("a", newline="", encoding="utf-8") as handle:
		writer = csv.writer(handle)
		timestamp = datetime.now(timezone.utc).isoformat()
		writer.writerow([timestamp, event, f"{latency_ms:.3f}"])


def serial_listener_worker(
	arduino: ArduinoComms,
	stop_event: threading.Event,
	pending_unlock_times: deque,
	pending_lock: threading.Lock,
	latency_csv_path: Path,
) -> None:
	while not stop_event.is_set():
		line = arduino.read_line()
		if not line:
			continue

		if line.startswith("ACK:"):
			ack_command = line[4:].strip()
			if ack_command == "UNLOCK":
				with pending_lock:
					if pending_unlock_times:
						sent_time = pending_unlock_times.popleft()
					else:
						sent_time = None

				if sent_time is not None:
					latency_ms = (time.monotonic() - sent_time) * 1000.0
					_append_latency(latency_csv_path, "UNLOCK_ACK", latency_ms)
					print(f"[Latency] UNLOCK ACK roundtrip: {latency_ms:.2f} ms")


def state_machine_worker(shared: SharedState, stop_event: threading.Event) -> None:
	require_rfid = os.getenv("AIRPASS_REQUIRE_RFID", "0").strip().lower() in {"1", "true", "yes", "on"}
	skip_arduino = os.getenv("AIRPASS_SKIP_ARDUINO", "0").strip().lower() in {"1", "true", "yes", "on"}
	skip_gesture = os.getenv("AIRPASS_SKIP_GESTURE", "0").strip().lower() in {"1", "true", "yes", "on"}
	require_face_during_countdown = os.getenv("AIRPASS_REQUIRE_FACE_DURING_COUNTDOWN", "0").strip().lower() in {
		"1",
		"true",
		"yes",
		"on",
	}
	face_timeout = float(os.getenv("AIRPASS_FACE_TIMEOUT", str(FACE_TIMEOUT_SECONDS)))
	face_stable_seconds = float(os.getenv("AIRPASS_FACE_STABLE_SECONDS", str(FACE_STABLE_SECONDS)))
	countdown_seconds = float(os.getenv("AIRPASS_COUNTDOWN_SECONDS", str(COUNTDOWN_SECONDS)))
	gesture_timeout = float(os.getenv("AIRPASS_GESTURE_TIMEOUT", str(GESTURE_TIMEOUT_SECONDS)))
	allow_arduino_bypass_on_fail = os.getenv("AIRPASS_ALLOW_ARDUINO_BYPASS_ON_FAIL", "1").strip().lower() in {
		"1",
		"true",
		"yes",
		"on",
	}
	allowed_tags = {
		token.strip().upper() for token in os.getenv("AIRPASS_ALLOWED_TAGS", "").split(",") if token.strip()
	}
	latency_csv_path = Path(os.getenv("AIRPASS_LATENCY_CSV", "unlock_latency.csv"))

	rfid = None
	try:
		if require_rfid:
			rfid = RFIDReader(valid_tags=allowed_tags)
	except Exception as exc:
		print(f"[RFID] Initialization failed: {exc}")
		stop_event.set()
		return

	if not require_rfid:
		print("[RFID] Optional mode. Starting at Face check (State 1).")
	if skip_gesture:
		print("[Gesture] Bypass mode enabled. Face success will proceed directly to unlock.")
	if skip_arduino:
		print("[Arduino] Bypass mode enabled. Commands will be logged only.")
	print(
		f"[Auth] Timeouts: face={face_timeout:.1f}s, countdown={countdown_seconds:.1f}s, gesture={gesture_timeout:.1f}s"
	)

	arduino = None
	if not skip_arduino:
		arduino_port = os.getenv("ARDUINO_PORT", "/dev/ttyACM0")
		arduino = ArduinoComms(port=arduino_port)
		connected = arduino.connect(retries=10, retry_delay=2.0)
		if not connected:
			if allow_arduino_bypass_on_fail:
				print("[Arduino] Falling back to bypass mode due to connection failure.")
				skip_arduino = True
			else:
				stop_event.set()
				return

	pending_unlock_times = deque()
	pending_lock = threading.Lock()
	listener_thread = None
	if arduino is not None and not skip_arduino:
		_init_latency_csv(latency_csv_path)
		listener_thread = threading.Thread(
			target=serial_listener_worker,
			args=(arduino, stop_event, pending_unlock_times, pending_lock, latency_csv_path),
			name="SerialListenerThread",
			daemon=True,
		)
		listener_thread.start()

	def send_arduino(command: str) -> bool:
		if skip_arduino:
			print(f"[Arduino:Bypass] {command}")
			return True
		if arduino is not None:
			ok = arduino.send_command(command)
			if ok and command == "UNLOCK":
				with pending_lock:
					pending_unlock_times.append(time.monotonic())
			return ok
		return False

	idle_state = 1 if not require_rfid else 0
	state = idle_state
	state_started_at = time.monotonic()
	gesture_progress = []
	face_seen_since = None
	last_countdown_announced = None
	face_lost_since = None

	def reset_to_idle(reason: str) -> None:
		nonlocal state, state_started_at, gesture_progress, face_seen_since, last_countdown_announced, face_lost_since
		print(f"[Auth] Reset -> State {idle_state} ({reason})")
		shared.clear_gesture_events()
		gesture_progress = []
		face_seen_since = None
		last_countdown_announced = None
		face_lost_since = None
		state = idle_state
		state_started_at = time.monotonic()

	try:
		while not stop_event.is_set():
			now = time.monotonic()

			if state == 0:
				if rfid is None:
					reset_to_idle("rfid unavailable")
					time.sleep(0.03)
					continue

				uid = rfid.read_tag()
				if uid:
					if rfid.is_valid_tag(uid):
						print(f"[Auth] Valid RFID detected: {uid}")
						send_arduino("RFID_OK")
						state = 1
						state_started_at = now
						face_seen_since = None
					else:
						print(f"[Auth] Invalid RFID detected: {uid}")
						send_arduino("RFID_DENY")

			elif state == 1:
				if not shared.is_camera_online():
					face_seen_since = None
					state_started_at = now
					time.sleep(0.03)
					continue

				if shared.has_face():
					if face_seen_since is None:
						face_seen_since = now
					elif now - face_seen_since >= face_stable_seconds:
						print("[Auth] Face detected within timeout")
						send_arduino("FACE_OK")
						shared.clear_gesture_events()
						gesture_progress = []
						last_countdown_announced = None
						state = 4 if skip_gesture else 2
						state_started_at = now
				else:
					face_seen_since = None

				if now - state_started_at > face_timeout:
					send_arduino("FACE_TIMEOUT")
					reset_to_idle("face timeout")

			elif state == 2:
				if require_face_during_countdown:
					if not shared.has_face():
						if face_lost_since is None:
							face_lost_since = now
						elif now - face_lost_since >= 0.8:
							send_arduino("FACE_LOST")
							reset_to_idle("face lost during countdown")
							continue
					else:
						face_lost_since = None

				remaining = max(0, math.ceil((state_started_at + countdown_seconds) - now))
				if remaining != last_countdown_announced:
					last_countdown_announced = remaining
					send_arduino(f"COUNTDOWN:{remaining}")
					print(f"[Auth] Countdown: {remaining}s")

				if now - state_started_at >= countdown_seconds:
					send_arduino("GESTURE_START")
					state = 3
					state_started_at = now

			elif state == 3:
				gesture = shared.pop_gesture_event()
				if gesture:
					expected = GESTURE_SEQUENCE[len(gesture_progress)]
					if gesture == expected:
						gesture_progress.append(gesture)
						print(f"[Auth] Gesture accepted: {gesture} ({len(gesture_progress)}/{len(GESTURE_SEQUENCE)})")
						send_arduino(f"GESTURE_OK:{gesture}")

						if len(gesture_progress) == len(GESTURE_SEQUENCE):
							print("[Auth] Gesture sequence complete")
							send_arduino("GESTURE_SEQUENCE_OK")
							state = 4
							state_started_at = now
					else:
						send_arduino(f"GESTURE_FAIL:{gesture}")
						reset_to_idle("wrong gesture")

				if now - state_started_at > gesture_timeout:
					send_arduino("GESTURE_TIMEOUT")
					reset_to_idle("gesture timeout")

			elif state == 4:
				print("[Auth] UNLOCK sequence started")
				send_arduino("UNLOCK")

				if not _safe_wait(stop_event, UNLOCK_HOLD_SECONDS):
					break

				send_arduino("LOCK")
				print("[Auth] LOCK sent, returning to idle")
				reset_to_idle("unlock cycle complete")

			time.sleep(0.03)

	finally:
		if listener_thread is not None:
			listener_thread.join(timeout=2.0)
		if arduino is not None:
			arduino.close()


def main() -> None:
	stop_event = threading.Event()
	shared = SharedState()

	camera_thread = threading.Thread(
		target=camera_worker,
		args=(shared, stop_event, 0),
		name="CameraThread",
		daemon=True,
	)
	security_thread = threading.Thread(
		target=state_machine_worker,
		args=(shared, stop_event),
		name="StateMachineThread",
		daemon=True,
	)

	camera_thread.start()
	security_thread.start()

	try:
		while not stop_event.is_set():
			time.sleep(0.25)
			if not camera_thread.is_alive() or not security_thread.is_alive():
				stop_event.set()
	except KeyboardInterrupt:
		stop_event.set()
	finally:
		camera_thread.join(timeout=3.0)
		security_thread.join(timeout=3.0)
		cv2.destroyAllWindows()
		print("[System] AirPass node stopped")


if __name__ == "__main__":
	main()

