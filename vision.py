from typing import List, Optional, Tuple

import cv2
import numpy as np

try:
	import mediapipe as mp
except Exception:
	mp = None


class VisionProcessor:
	"""Runs face and hand processing plus gesture debounce tracking."""

	def __init__(self, gesture_hold_frames: int = 8):
		self.mediapipe_enabled = mp is not None
		self.gesture_enabled = True
		self.gesture_backend = "mediapipe" if self.mediapipe_enabled else "opencv"

		self.mp_hands = None
		self.mp_face = None
		self.mp_draw = None
		self.hands = None
		self.face = None

		self.haar_face = cv2.CascadeClassifier(
			cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
		)
		self._kernel = np.ones((5, 5), np.uint8)

		if self.mediapipe_enabled:
			self.mp_hands = mp.solutions.hands
			self.mp_face = mp.solutions.face_detection
			self.mp_draw = mp.solutions.drawing_utils

			self.hands = self.mp_hands.Hands(
				static_image_mode=False,
				max_num_hands=1,
				min_detection_confidence=0.7,
				min_tracking_confidence=0.7,
				model_complexity=0,
			)
			self.face = self.mp_face.FaceDetection(min_detection_confidence=0.7)
		else:
			print("[Vision] MediaPipe unavailable. Running OpenCV fallback for face + gestures.")

		self.current_gesture: Optional[str] = None
		self.gesture_frame_count = 0
		self.required_frames = max(7, min(10, int(gesture_hold_frames)))
		self.sequence_stack: List[str] = []

	def process_frame(self, frame) -> Tuple[bool, Optional[str], any]:
		annotated = frame.copy()

		if self.mediapipe_enabled and self.face is not None and self.hands is not None:
			rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
			face_results = self.face.process(rgb_frame)
			hand_results = self.hands.process(rgb_frame)

			face_detected = bool(face_results.detections)
			gesture_locked = self._detect_gesture(hand_results)
			self._draw_annotations(annotated, face_results, hand_results, face_detected, gesture_locked)
			return face_detected, gesture_locked, annotated

		gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
		faces = self.haar_face.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
		for (x, y, w, h) in faces:
			cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 0), 2)

		face_detected = len(faces) > 0
		gesture_locked = self._detect_gesture_opencv(frame)
		self._draw_fallback_annotations(annotated, face_detected, gesture_locked)
		return face_detected, gesture_locked, annotated

	def _draw_annotations(self, frame, face_results, hand_results, face_detected: bool, gesture_locked: Optional[str]) -> None:
		if face_results.detections:
			for detection in face_results.detections:
				self.mp_draw.draw_detection(frame, detection)

		if hand_results.multi_hand_landmarks:
			for hand_landmarks in hand_results.multi_hand_landmarks:
				self.mp_draw.draw_landmarks(
					frame,
					hand_landmarks,
					self.mp_hands.HAND_CONNECTIONS,
				)

		cv2.putText(
			frame,
			f"Face: {'YES' if face_detected else 'NO'}",
			(10, 25),
			cv2.FONT_HERSHEY_SIMPLEX,
			0.7,
			(0, 255, 0) if face_detected else (0, 0, 255),
			2,
			cv2.LINE_AA,
		)
		cv2.putText(
			frame,
			f"Debounce: {self.current_gesture or '-'} ({self.gesture_frame_count}/{self.required_frames})",
			(10, 52),
			cv2.FONT_HERSHEY_SIMPLEX,
			0.6,
			(255, 255, 0),
			2,
			cv2.LINE_AA,
		)
		cv2.putText(
			frame,
			f"Locked: {gesture_locked or '-'}",
			(10, 79),
			cv2.FONT_HERSHEY_SIMPLEX,
			0.6,
			(255, 200, 0),
			2,
			cv2.LINE_AA,
		)
		cv2.putText(
			frame,
			f"Sequence: {' > '.join(self.sequence_stack) if self.sequence_stack else '-'}",
			(10, 106),
			cv2.FONT_HERSHEY_SIMPLEX,
			0.6,
			(255, 255, 255),
			2,
			cv2.LINE_AA,
		)

	def _draw_fallback_annotations(self, frame, face_detected: bool, gesture_locked: Optional[str]) -> None:
		cv2.putText(
			frame,
			f"Face: {'YES' if face_detected else 'NO'}",
			(10, 25),
			cv2.FONT_HERSHEY_SIMPLEX,
			0.7,
			(0, 255, 0) if face_detected else (0, 0, 255),
			2,
			cv2.LINE_AA,
		)
		cv2.putText(
			frame,
			f"Backend: {self.gesture_backend} | Debounce: {self.current_gesture or '-'} ({self.gesture_frame_count}/{self.required_frames})",
			(10, 52),
			cv2.FONT_HERSHEY_SIMPLEX,
			0.6,
			(0, 200, 255),
			2,
			cv2.LINE_AA,
		)
		cv2.putText(
			frame,
			f"Locked: {gesture_locked or '-'}",
			(10, 79),
			cv2.FONT_HERSHEY_SIMPLEX,
			0.6,
			(255, 200, 0),
			2,
			cv2.LINE_AA,
		)
		cv2.putText(
			frame,
			f"Sequence: {' > '.join(self.sequence_stack) if self.sequence_stack else '-'}",
			(10, 106),
			cv2.FONT_HERSHEY_SIMPLEX,
			0.6,
			(255, 255, 255),
			2,
			cv2.LINE_AA,
		)

	def _detect_gesture(self, hand_results) -> Optional[str]:
		if not hand_results.multi_hand_landmarks:
			self.current_gesture = None
			self.gesture_frame_count = 0
			return None

		for hand_landmarks in hand_results.multi_hand_landmarks:
			raw_gesture = self._classify_hand_shape(hand_landmarks.landmark)
			return self._apply_debounce(raw_gesture)

		return None

	def _detect_gesture_opencv(self, frame) -> Optional[str]:
		ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
		lower = np.array([0, 133, 77], dtype=np.uint8)
		upper = np.array([255, 173, 127], dtype=np.uint8)
		mask = cv2.inRange(ycrcb, lower, upper)

		mask = cv2.GaussianBlur(mask, (7, 7), 0)
		mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel, iterations=1)
		mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self._kernel, iterations=2)

		contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
		if not contours:
			self.current_gesture = None
			self.gesture_frame_count = 0
			return None

		largest = max(contours, key=cv2.contourArea)
		if cv2.contourArea(largest) < 5000:
			self.current_gesture = None
			self.gesture_frame_count = 0
			return None

		raw_gesture = self._classify_contour_shape(largest)
		return self._apply_debounce(raw_gesture)

	def _classify_contour_shape(self, contour) -> str:
		area = cv2.contourArea(contour)
		if area <= 0:
			return "Unknown"

		hull_points = cv2.convexHull(contour)
		hull_area = cv2.contourArea(hull_points)
		solidity = area / hull_area if hull_area > 0 else 0.0

		hull_idx = cv2.convexHull(contour, returnPoints=False)
		if hull_idx is None or len(hull_idx) < 4:
			return "Unknown"

		defects = cv2.convexityDefects(contour, hull_idx)
		defect_count = 0

		if defects is not None:
			for i in range(defects.shape[0]):
				s, e, f, d = defects[i, 0]
				start = contour[s][0]
				end = contour[e][0]
				far = contour[f][0]

				a = np.linalg.norm(end - start)
				b = np.linalg.norm(far - start)
				c = np.linalg.norm(end - far)
				if b == 0 or c == 0:
					continue

				cos_angle = (b * b + c * c - a * a) / (2 * b * c)
				cos_angle = float(np.clip(cos_angle, -1.0, 1.0))
				angle = np.degrees(np.arccos(cos_angle))

				if angle < 90 and d > 12000:
					defect_count += 1

		fingers = defect_count + 1 if defect_count > 0 else 1

		if solidity > 0.90 and fingers <= 1:
			return "Fist"
		if fingers == 2:
			return "Peace"
		if fingers >= 4:
			return "Open"
		return "Unknown"

	def _apply_debounce(self, raw_gesture: str) -> Optional[str]:
		if raw_gesture == "Unknown":
			self.current_gesture = raw_gesture
			self.gesture_frame_count = 0
			return None

		if raw_gesture == self.current_gesture:
			self.gesture_frame_count += 1
			if self.gesture_frame_count == self.required_frames:
				self._update_sequence(raw_gesture)
				return raw_gesture
		else:
			self.current_gesture = raw_gesture
			self.gesture_frame_count = 1

		return None

	def _classify_hand_shape(self, landmarks) -> str:
		index_open = landmarks[8].y < landmarks[6].y
		middle_open = landmarks[12].y < landmarks[10].y
		ring_open = landmarks[16].y < landmarks[14].y
		pinky_open = landmarks[20].y < landmarks[18].y

		if not index_open and not middle_open and not ring_open and not pinky_open:
			return "Fist"
		if index_open and middle_open and not ring_open and not pinky_open:
			return "Peace"
		if index_open and middle_open and ring_open and pinky_open:
			return "Open"
		return "Unknown"

	def _update_sequence(self, confirmed_gesture: str) -> None:
		if not self.sequence_stack or self.sequence_stack[-1] != confirmed_gesture:
			self.sequence_stack.append(confirmed_gesture)

	def clear_sequence(self) -> None:
		self.sequence_stack.clear()

	def close(self) -> None:
		if self.hands is not None:
			self.hands.close()
		if self.face is not None:
			self.face.close()

