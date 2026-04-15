import os
import threading
import time
from collections import deque
from typing import Optional

import cv2

from arduino_comms import ArduinoComms
from rfid_reader import RFIDReader
from vision import VisionProcessor

GESTURE_SEQUENCE = ["Fist", "Peace", "Open"]
FACE_TIMEOUT_SECONDS = 5.0
GESTURE_TIMEOUT_SECONDS = 5.0
UNLOCK_HOLD_SECONDS = 5.0
CAMERA_RETRY_SECONDS = 2.0


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
	processor = VisionProcessor()
	capture = None
	skip_gesture = os.getenv("AIRPASS_SKIP_GESTURE", "0").strip().lower() in {"1", "true", "yes", "on"}

	if not skip_gesture and not processor.gesture_enabled:
		print("[Vision] Gesture testing requested but MediaPipe gesture backend is unavailable.")
		print("[Vision] Set AIRPASS_SKIP_GESTURE=1 for face-only mode, or install a compatible MediaPipe build.")
		stop_event.set()
		processor.close()
		return

	try:
		while not stop_event.is_set():
			try:
				if capture is None or not capture.isOpened():
					capture = cv2.VideoCapture(camera_index)
					capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
					capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
					capture.set(cv2.CAP_PROP_FPS, 30)

					if not capture.isOpened():
						print("[Camera] Capture unavailable. Retrying in 2 seconds...")
						shared.set_camera_offline()
						time.sleep(CAMERA_RETRY_SECONDS)
						continue

				ok, frame = capture.read()
				if not ok:
					print("[Camera] Frame read failed. Camera may be unplugged. Reconnecting...")
					shared.set_camera_offline()
					capture.release()
					capture = None
					time.sleep(CAMERA_RETRY_SECONDS)
					continue

				face_detected, gesture_locked, rendered = processor.process_frame(frame)
				shared.update_vision(face_detected, gesture_locked, camera_online=True)

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
				print(f"[Camera] Exception in capture loop: {exc}. Retrying in 2 seconds...")
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


def state_machine_worker(shared: SharedState, stop_event: threading.Event) -> None:
	skip_rfid = os.getenv("AIRPASS_SKIP_RFID", "1").strip().lower() in {"1", "true", "yes", "on"}
	skip_arduino = os.getenv("AIRPASS_SKIP_ARDUINO", "1").strip().lower() in {"1", "true", "yes", "on"}
	skip_gesture = os.getenv("AIRPASS_SKIP_GESTURE", "0").strip().lower() in {"1", "true", "yes", "on"}
	face_timeout = float(os.getenv("AIRPASS_FACE_TIMEOUT", str(FACE_TIMEOUT_SECONDS)))
	gesture_timeout = float(os.getenv("AIRPASS_GESTURE_TIMEOUT", str(GESTURE_TIMEOUT_SECONDS)))
	allowed_tags = {
		token.strip().upper() for token in os.getenv("AIRPASS_ALLOWED_TAGS", "").split(",") if token.strip()
	}

	rfid = None
	try:
		if not skip_rfid:
			rfid = RFIDReader(valid_tags=allowed_tags)
	except Exception as exc:
		if skip_rfid:
			print(f"[RFID] Initialization failed but bypass is enabled: {exc}")
		else:
			print(f"[RFID] Initialization failed: {exc}")
			stop_event.set()
			return

	if skip_rfid:
		print("[RFID] Bypass mode enabled. Starting at Face check (State 1).")
	if skip_gesture:
		print("[Gesture] Bypass mode enabled. Face success will proceed directly to unlock.")
	if skip_arduino:
		print("[Arduino] Bypass mode enabled. Commands will be logged only.")
	print(f"[Auth] Timeouts: face={face_timeout:.1f}s, gesture={gesture_timeout:.1f}s")

	arduino = None
	if not skip_arduino:
		arduino_port = os.getenv("ARDUINO_PORT", "/dev/ttyACM0")
		arduino = ArduinoComms(port=arduino_port)
		arduino.connect(retries=10, retry_delay=2.0)

	def send_arduino(command: str) -> None:
		if skip_arduino:
			print(f"[Arduino:Bypass] {command}")
			return
		if arduino is not None:
			arduino.send_command(command)

	idle_state = 1 if skip_rfid else 0
	state = idle_state
	state_started_at = time.monotonic()
	gesture_progress = []

	def reset_to_idle(reason: str) -> None:
		nonlocal state, state_started_at, gesture_progress
		print(f"[Auth] Reset -> State {idle_state} ({reason})")
		shared.clear_gesture_events()
		gesture_progress = []
		state = idle_state
		state_started_at = time.monotonic()

	try:
		while not stop_event.is_set():
			now = time.monotonic()

			if state == 0:
				if rfid is None:
					reset_to_idle("rfid bypass")
					time.sleep(0.03)
					continue

				uid = rfid.read_tag()
				if uid:
					if rfid.is_valid_tag(uid):
						print(f"[Auth] Valid RFID detected: {uid}")
						send_arduino("RFID_OK")
						state = 1
						state_started_at = now
					else:
						print(f"[Auth] Invalid RFID detected: {uid}")
						send_arduino("RFID_DENY")

			elif state == 1:
				if shared.has_face():
					print("[Auth] Face detected within timeout")
					send_arduino("FACE_OK")
					shared.clear_gesture_events()
					gesture_progress = []
					state = 3 if skip_gesture else 2
					state_started_at = now
				elif now - state_started_at > face_timeout:
					send_arduino("FACE_TIMEOUT")
					reset_to_idle("face timeout")

			elif state == 2:
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
							state = 3
							state_started_at = now
					else:
						send_arduino(f"GESTURE_FAIL:{gesture}")
						reset_to_idle("wrong gesture")

				if now - state_started_at > gesture_timeout:
					send_arduino("GESTURE_TIMEOUT")
					reset_to_idle("gesture timeout")

			elif state == 3:
				print("[Auth] UNLOCK sequence started")
				send_arduino("UNLOCK")

				if not _safe_wait(stop_event, UNLOCK_HOLD_SECONDS):
					break

				send_arduino("LOCK")
				print("[Auth] LOCK sent, returning to idle")
				reset_to_idle("unlock cycle complete")

			time.sleep(0.03)

	finally:
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

