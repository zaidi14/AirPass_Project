from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np


class FaceAuthenticator:
	"""Simple face-password verifier against a stored reference image."""

	def __init__(self, reference_image_path: str, threshold: float = 0.60):
		self.threshold = threshold
		self._cascade = self._load_cascade()
		self._reference_embedding = self._load_reference_embedding(reference_image_path)

	def _load_cascade(self) -> cv2.CascadeClassifier:
		candidate_paths = []
		if hasattr(cv2, "data") and hasattr(cv2.data, "haarcascades"):
			candidate_paths.append(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
		candidate_paths.extend(
			[
				Path("/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"),
				Path("/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml"),
				Path("/usr/local/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"),
				Path("/usr/local/share/opencv/haarcascades/haarcascade_frontalface_default.xml"),
			]
		)

		for candidate_path in candidate_paths:
			if candidate_path.exists():
				classifier = cv2.CascadeClassifier(str(candidate_path))
				if not classifier.empty():
					return classifier

		raise RuntimeError("No Haar cascade found for face-password verification.")

	def _extract_largest_face(self, frame) -> Optional[np.ndarray]:
		gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
		faces = self._cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
		if len(faces) == 0:
			return None

		x, y, w, h = max(faces, key=lambda box: box[2] * box[3])
		return gray[y : y + h, x : x + w]

	def _to_embedding(self, face_gray: np.ndarray) -> np.ndarray:
		resized = cv2.resize(face_gray, (96, 96), interpolation=cv2.INTER_AREA)
		equalized = cv2.equalizeHist(resized)
		vector = equalized.astype(np.float32).reshape(-1)
		norm = float(np.linalg.norm(vector))
		if norm <= 1e-6:
			return vector
		return vector / norm

	def _load_reference_embedding(self, reference_image_path: str) -> np.ndarray:
		path = Path(reference_image_path)
		if not path.exists():
			raise RuntimeError(f"Face reference image not found: {path}")

		image = cv2.imread(str(path))
		if image is None:
			raise RuntimeError(f"Failed to load face reference image: {path}")

		face = self._extract_largest_face(image)
		if face is None:
			raise RuntimeError(f"No face found in reference image: {path}")

		return self._to_embedding(face)

	def verify(self, frame) -> Tuple[bool, float]:
		face = self._extract_largest_face(frame)
		if face is None:
			return False, 0.0

		candidate = self._to_embedding(face)
		score = float(np.dot(self._reference_embedding, candidate))
		return score >= self.threshold, score
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np


class FaceAuthenticator:
	"""Simple face-password verifier against a stored reference image."""

	def __init__(self, reference_image_path: str, threshold: float = 0.60):
		self.threshold = threshold
		self._cascade = self._load_cascade()
		self._reference_embedding = self._load_reference_embedding(reference_image_path)

	def _load_cascade(self) -> cv2.CascadeClassifier:
		candidate_paths = []
		if hasattr(cv2, "data") and hasattr(cv2.data, "haarcascades"):
			candidate_paths.append(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
		candidate_paths.extend(
			[
				Path("/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"),
				Path("/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml"),
				Path("/usr/local/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"),
				Path("/usr/local/share/opencv/haarcascades/haarcascade_frontalface_default.xml"),
			]
		)

		for candidate_path in candidate_paths:
			if candidate_path.exists():
				classifier = cv2.CascadeClassifier(str(candidate_path))
				if not classifier.empty():
					return classifier

		raise RuntimeError("No Haar cascade found for face-password verification.")

	def _extract_largest_face(self, frame) -> Optional[np.ndarray]:
		gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
		faces = self._cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
		if len(faces) == 0:
			return None

		x, y, w, h = max(faces, key=lambda box: box[2] * box[3])
		return gray[y : y + h, x : x + w]

	def _to_embedding(self, face_gray: np.ndarray) -> np.ndarray:
		resized = cv2.resize(face_gray, (96, 96), interpolation=cv2.INTER_AREA)
		equalized = cv2.equalizeHist(resized)
		vector = equalized.astype(np.float32).reshape(-1)
		norm = float(np.linalg.norm(vector))
		if norm <= 1e-6:
			return vector
		return vector / norm

	def _load_reference_embedding(self, reference_image_path: str) -> np.ndarray:
		path = Path(reference_image_path)
		if not path.exists():
			raise RuntimeError(f"Face reference image not found: {path}")

		image = cv2.imread(str(path))
		if image is None:
			raise RuntimeError(f"Failed to load face reference image: {path}")

		face = self._extract_largest_face(image)
		if face is None:
			raise RuntimeError(f"No face found in reference image: {path}")

		return self._to_embedding(face)

	def verify(self, frame) -> Tuple[bool, float]:
		face = self._extract_largest_face(frame)
		if face is None:
			return False, 0.0

		candidate = self._to_embedding(face)
		score = float(np.dot(self._reference_embedding, candidate))
		return score >= self.threshold, score
