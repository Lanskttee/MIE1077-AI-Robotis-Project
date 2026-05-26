"""Facial-emotion perception.

Two implementations:

* ``DeepFaceEmotionDetector`` — opens the webcam with OpenCV and runs DeepFace
  on each frame on demand. DeepFace is imported lazily because TensorFlow takes
  several seconds to load on first use.
* ``MockEmotionDetector`` — returns whatever emotion has been ``inject``-ed.
  The Pygame UI binds digit keys 1..6 to inject emotions, so the rest of the
  pipeline can be demonstrated without a webcam.

Both implementations conform to the same ``EmotionDetector`` protocol so the
agent code does not care which is active.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from ..config import EMOTIONS


@dataclass
class EmotionReading:
    label: str
    confidence: float
    raw: dict[str, float]    # full per-class probabilities (sums to ~1)


class EmotionDetector(Protocol):
    def poll(self) -> Optional[EmotionReading]: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...


# ---------------------------------------------------------------------------
# Mock detector
# ---------------------------------------------------------------------------


class MockEmotionDetector:
    """Returns whatever emotion the UI/test injects.

    The UI calls ``inject('happy')`` when the user presses '1', etc. The poll
    returns ``None`` until something has been injected, then returns the last
    injection forever (so behavior is stable across the agent's loop).
    """

    def __init__(self) -> None:
        self._latest: Optional[EmotionReading] = None
        self._running = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def inject(self, label: str, confidence: float = 0.95) -> None:
        if label not in EMOTIONS:
            raise ValueError(f"unknown emotion {label!r}")
        raw = {e: (1.0 - confidence) / (len(EMOTIONS) - 1) for e in EMOTIONS}
        raw[label] = confidence
        self._latest = EmotionReading(label=label, confidence=confidence, raw=raw)

    def poll(self) -> Optional[EmotionReading]:
        if not self._running:
            return None
        return self._latest


# ---------------------------------------------------------------------------
# DeepFace detector
# ---------------------------------------------------------------------------


# DeepFace emits emotions with slightly different labels than ours; map them.
_DEEPFACE_TO_OURS = {
    "happy":    "happy",
    "sad":      "sad",
    "angry":    "angry",
    "fear":     "surprised",
    "surprise": "surprised",
    "neutral":  "neutral",
    "disgust":  "angry",
    # DeepFace has no "tired" — we synthesize it below from heuristics
}


class DeepFaceEmotionDetector:
    """Webcam + DeepFace emotion classification.

    Only imports ``cv2`` / ``deepface`` when ``start()`` is called, so the rest
    of the project keeps working in environments where they are not installed.
    """

    def __init__(self, camera_index: int = 0, sample_every_n_frames: int = 6) -> None:
        self.camera_index = camera_index
        self.sample_every = sample_every_n_frames
        self._cap = None
        self._frame_count = 0
        self._latest: Optional[EmotionReading] = None
        self._running = False

    def start(self) -> None:
        try:
            import cv2  # noqa: F401  (imported for side effect / early failure)
            from deepface import DeepFace  # noqa: F401
        except Exception as exc:
            raise RuntimeError(
                "DeepFace/OpenCV unavailable. Install via `pip install -r requirements.txt`, "
                "or set HOMEMATE_USE_MOCK_EMOTION=1."
            ) from exc

        import cv2
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open webcam at index {self.camera_index}")
        self._cap = cap
        self._running = True

    def stop(self) -> None:
        self._running = False
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def poll(self) -> Optional[EmotionReading]:
        if not self._running or self._cap is None:
            return None
        import cv2

        ok, frame = self._cap.read()
        if not ok:
            return self._latest

        self._frame_count += 1
        if self._frame_count % self.sample_every != 0:
            return self._latest

        try:
            from deepface import DeepFace
            res = DeepFace.analyze(
                frame,
                actions=["emotion"],
                enforce_detection=False,
                silent=True,
            )
            if isinstance(res, list):
                res = res[0]
            probs_raw = res.get("emotion", {})    # str -> 0..100 (DeepFace) or 0..1
            # normalize to 0..1
            total = sum(probs_raw.values()) or 1.0
            probs = {k: float(v) / total for k, v in probs_raw.items()}
            # remap to our emotion vocabulary
            mapped: dict[str, float] = {e: 0.0 for e in EMOTIONS}
            for src, val in probs.items():
                tgt = _DEEPFACE_TO_OURS.get(src.lower())
                if tgt is not None:
                    mapped[tgt] += val
            # crude 'tired' heuristic: high neutral + high sad + low happy
            mapped["tired"] = min(1.0, 0.5 * mapped["neutral"] + 0.5 * mapped["sad"]) * \
                              max(0.0, 1.0 - mapped["happy"])
            # renormalize
            tot = sum(mapped.values()) or 1.0
            mapped = {k: v / tot for k, v in mapped.items()}
            label = max(mapped, key=mapped.get)
            self._latest = EmotionReading(label=label, confidence=mapped[label], raw=mapped)
        except Exception:
            # transient DeepFace error — keep previous reading
            pass
        return self._latest


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_detector(use_mock: bool) -> EmotionDetector:
    return MockEmotionDetector() if use_mock else DeepFaceEmotionDetector()
