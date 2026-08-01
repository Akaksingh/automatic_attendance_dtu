"""Lazy InsightFace embedding service for single-person enrollment photos."""
from __future__ import annotations

import threading
from dataclasses import dataclass

import cv2
import numpy as np

from ..config import settings

_app = None
_lock = threading.Lock()


@dataclass
class DetectedFace:
    embedding: np.ndarray
    det_score: float
    bbox: tuple[int, int, int, int]


def _get_app():
    global _app
    if _app is None:
        with _lock:
            if _app is None:
                try:
                    from insightface.app import FaceAnalysis
                except ImportError as exc:
                    raise RuntimeError("InsightFace/ONNX Runtime is not installed in the worker environment") from exc
                app = FaceAnalysis(name=settings.face_model_pack, providers=[settings.face_provider])
                app.prepare(ctx_id=0, det_size=(640, 640))
                _app = app
    return _app


def detect_faces(image_bytes: bytes) -> list[DetectedFace]:
    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode image")
    detected = _get_app().get(image)
    faces: list[DetectedFace] = []
    for face in detected:
        if float(face.det_score) < settings.face_detection_score_min:
            continue
        embedding = np.asarray(face.embedding, dtype=np.float32)
        norm = np.linalg.norm(embedding)
        if norm:
            x1, y1, x2, y2 = (int(value) for value in face.bbox)
            faces.append(DetectedFace(embedding=embedding / norm, det_score=float(face.det_score), bbox=(x1, y1, x2, y2)))
    return faces


def embed_single_face(image_bytes: bytes) -> np.ndarray:
    faces = detect_faces(image_bytes)
    if not faces:
        raise ValueError("No face detected in enrollment photo")
    if len(faces) > 1:
        raise ValueError("Profile photo must contain exactly one face")
    embedding = np.asarray(faces[0].embedding, dtype=np.float32)
    norm = np.linalg.norm(embedding)
    if norm == 0:
        raise ValueError("Could not create a face embedding")
    return embedding / norm


def cosine_similarity(first: np.ndarray, second: np.ndarray) -> float:
    return float(np.dot(first, second))
