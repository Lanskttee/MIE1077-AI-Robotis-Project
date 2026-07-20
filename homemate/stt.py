"""Speech-to-text engine using OpenAI Whisper API.

Usage:
    engine = STTEngine()
    if engine.available:
        engine.start()           # begin mic recording
        text = engine.stop_and_transcribe()  # blocks ~1-2s, returns string
"""
from __future__ import annotations

import io
import os
import threading


class STTEngine:
    def __init__(self, api_key: str | None = None, samplerate: int = 16000) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._sr = samplerate
        self._recording = False
        self._frames: list = []
        self._stream = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import sounddevice  # noqa: F401
            import soundfile    # noqa: F401
            return True
        except ImportError:
            return False

    def start(self) -> None:
        """Begin recording from default mic."""
        import sounddevice as sd
        with self._lock:
            self._frames = []
            self._recording = True
        self._stream = sd.InputStream(
            samplerate=self._sr, channels=1, dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, indata, frames, time, status) -> None:
        with self._lock:
            if self._recording:
                self._frames.append(indata.copy())

    def stop_and_transcribe(self) -> str:
        """Stop recording, send to Whisper API, return transcribed text."""
        import numpy as np
        import soundfile as sf
        from openai import OpenAI

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._lock:
            self._recording = False
            frames = list(self._frames)

        if not frames:
            return ""

        audio = np.concatenate(frames, axis=0)
        buf = io.BytesIO()
        sf.write(buf, audio, self._sr, format="wav")
        buf.seek(0)

        client = OpenAI(api_key=self._api_key)
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=("audio.wav", buf, "audio/wav"),
        )
        return result.text.strip()
