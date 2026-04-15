import threading
import time
from typing import Optional

import serial
from serial import SerialException


class ArduinoComms:
	"""Handles thread-safe serial communication with the Arduino controller."""

	def __init__(self, port: str = "/dev/ttyACM0", baud_rate: int = 115200, timeout: float = 1.0):
		self.port = port
		self.baud_rate = baud_rate
		self.timeout = timeout
		self._serial: Optional[serial.Serial] = None
		self._lock = threading.Lock()

	def connect(self, retries: int = 5, retry_delay: float = 2.0) -> bool:
		for attempt in range(1, retries + 1):
			try:
				self._serial = serial.Serial(self.port, self.baud_rate, timeout=self.timeout)
				time.sleep(2.0)
				print(f"[Arduino] Connected on {self.port} @ {self.baud_rate} baud")
				return True
			except SerialException as exc:
				print(f"[Arduino] Connect attempt {attempt}/{retries} failed: {exc}")
				time.sleep(retry_delay)

		print("[Arduino] Unable to establish serial connection.")
		return False

	def is_connected(self) -> bool:
		return self._serial is not None and self._serial.is_open

	def send_command(self, command: str) -> bool:
		with self._lock:
			if not self.is_connected():
				print(f"[Arduino] Not connected. Dropping command: {command}")
				return False

			try:
				payload = f"{command}\n".encode("utf-8")
				self._serial.write(payload)
				self._serial.flush()
				print(f"[Arduino] -> {command}")
				return True
			except (SerialException, OSError) as exc:
				print(f"[Arduino] Send failed for '{command}': {exc}")
				self.close()
				return False

	def read_line(self) -> Optional[str]:
		with self._lock:
			if not self.is_connected():
				return None

			try:
				line = self._serial.readline().decode("utf-8", errors="ignore").strip()
				return line if line else None
			except (SerialException, OSError) as exc:
				print(f"[Arduino] Read failed: {exc}")
				self.close()
				return None

	def close(self) -> None:
		with self._lock:
			if self._serial is not None:
				try:
					if self._serial.is_open:
						self._serial.close()
						print("[Arduino] Serial port closed")
				finally:
					self._serial = None

