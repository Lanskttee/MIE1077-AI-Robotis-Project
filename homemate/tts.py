"""Text-to-speech engine.

Uses macOS ``say`` by default (free, zero deps).
If OPENAI_API_KEY is set, uses OpenAI tts-1 (nova voice) instead.
All calls are fire-and-forget daemon threads so they never block the UI.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import threading


class TTSEngine:
    def __init__(
        self,
        api_key: str | None = None,
        voice: str = "nova",
        model: str = "tts-1",
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._voice = voice
        self._model = model
        self._use_openai = bool(self._api_key)

    def speak(self, text: str) -> None:
        """Fire-and-forget: starts TTS in a daemon thread and returns immediately."""
        if not text:
            return
        t = threading.Thread(target=self._speak_sync, args=(text,), daemon=True)
        t.start()

    def _speak_sync(self, text: str) -> None:
        if self._use_openai:
            try:
                self._say_openai(text)
                return
            except Exception as e:
                print(f"[TTS] OpenAI failed ({e}), falling back to say")
        self._say_macos(text)

    @staticmethod
    def _say_macos(text: str) -> None:
        subprocess.run(["say", "-r", "160", text], check=False)

    def _say_openai(self, text: str) -> None:
        from openai import OpenAI  # lazy import
        client = OpenAI(api_key=self._api_key)
        response = client.audio.speech.create(
            model=self._model,
            voice=self._voice,
            input=text,
        )
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(response.content)
            fname = f.name
        try:
            subprocess.run(["afplay", fname], check=False)
        finally:
            try:
                os.unlink(fname)
            except OSError:
                pass
