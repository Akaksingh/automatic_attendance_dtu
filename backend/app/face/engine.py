"""InsightFace wrapper: detect faces in an image and produce ArcFace embeddings.

The model pack (buffalo_l) bundles RetinaFace for detection and an ArcFace model
for 512-dim recognition embeddings. Weights download once on first use and are
cached on the `model_cache` volume, so nothing leaves the college server after
initial setup.

The model is loaded lazily and reused per process — loading is expensive, so we
never do it inside a request. In production, matching happens in the Celery
worker (see app/worker.py), not in the API process.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

import cv2
import numpy as np

from ..config import settings

_app = None
_lock = threading.Lock()


def _get_app():
    """Lazily construct the InsightFace FaceAnalysis app (thread-safe singleton)."""
    global _app
    if _app is None:
        with _lock:
            if _app is None:
                from insightface.app import FaceAnalysis

                app = FaceAnalysis(
                    name=settings.face_model_pack,
                    providers=[settings.face_provider],
                )
                # det_size trades speed vs small-face recall; 640 handles group photos.
                app.prepare(ctx_id=0, det_size=(640, 640))
                _app = app
    return _app


@dataclass
class DetectedFace:
    embedding: np.ndarray          # L2-normalized, shape (512,)
    det_score: float               # detector confidence
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2


def _decode(image_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image")
    return img


def _normalize(vec: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(vec)
    return vec / n if n > 0 else vec


def detect_faces(image_bytes: bytes) -> list[DetectedFace]:
    """Detect every usable face in an image and return normalized embeddings."""
    img = _decode(image_bytes)
    faces = _get_app().get(img)
    out: list[DetectedFace] = []
    for f in faces:
        if float(f.det_score) < settings.face_det_score_min:
            continue
        emb = _normalize(np.asarray(f.embedding, dtype=np.float32))
        x1, y1, x2, y2 = (int(v) for v in f.bbox)
        out.append(DetectedFace(embedding=emb, det_score=float(f.det_score), bbox=(x1, y1, x2, y2)))
    return out


def embed_single_face(image_bytes: bytes) -> np.ndarray:
    """For enrollment: expect exactly one clear face, return its embedding.

    Raises ValueError if zero or multiple faces are found, so enrollment photos
    are unambiguous (one student per enrollment image).
    """
    faces = detect_faces(image_bytes)
    if not faces:
        raise ValueError("No face detected in enrollment photo")
    if len(faces) > 1:
        raise ValueError(f"Expected one face, found {len(faces)}")
    return faces[0].embedding


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity of two already-normalized vectors."""
    return float(np.dot(a, b))
