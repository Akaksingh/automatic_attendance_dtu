"""Lazy InsightFace embedding service for single-person enrollment photos."""
from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np

from ..config import settings

_app = None
_lock = threading.Lock()


@dataclass
class DetectedFace:
    embedding: np.ndarray
    det_score: float


def _get_app():
    global _app
    if _app is None:
        with _lock:
            if _app is None:
                try:
                    from insightface.app import FaceAnalysis
                except ImportError as exc:
                    raise RuntimeError("InsightFace is not installed on the API image") from exc
                app = FaceAnalysis(name=settings.face_model_pack, providers=[settings.face_provider])
                app.prepare(ctx_id=0, det_size=(640, 640))
                _app = app
    return _app


def detect_faces(image_bytes: bytes) -> list[DetectedFace]:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is not installed on the API image") from exc
    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Uploaded file is not a valid image")
    detected = [face for face in _get_app().get(image) if float(face.det_score) >= settings.face_detection_score_min]
    faces: list[DetectedFace] = []
    for face in detected:
        embedding = np.asarray(face.embedding, dtype=np.float32)
        norm = np.linalg.norm(embedding)
        if norm:
            faces.append(DetectedFace(embedding=embedding / norm, det_score=float(face.det_score)))
    return faces


def embed_single_face(image_bytes: bytes) -> np.ndarray:
    faces = detect_faces(image_bytes)
    if not faces:
        raise ValueError("No face detected in profile photo")
    if len(faces) > 1:
        raise ValueError("Profile photo must contain exactly one face")
    embedding = np.asarray(faces[0].embedding, dtype=np.float32)
    norm = np.linalg.norm(embedding)
    if norm == 0:
        raise ValueError("Could not create a face embedding")
    return embedding / norm


def cosine_similarity(first: np.ndarray, second: np.ndarray) -> float:
    return float(np.dot(first, second))
