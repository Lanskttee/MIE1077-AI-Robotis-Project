"""Text-to-speech engine.

Prefers OpenAI ``tts-1`` when ``OPENAI_API_KEY`` is set; otherwise falls back to
platform speech (macOS ``say``, Windows SAPI via ``powershell``, or silent).
Playback uses pygame when available so Windows works without ``afplay``.
All calls are fire-and-forget daemon threads so they never block the UI.
"""
from __future__ import annotations

import os
import platform
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
                print(f"[TTS] OpenAI failed ({e}), falling back to system TTS")
        self._say_system(text)

    @staticmethod
    def _say_system(text: str) -> None:
        system = platform.system()
        if system == "Darwin":
            subprocess.run(["say", "-r", "160", text], check=False)
            return
        if system == "Windows":
            # Escape single quotes for PowerShell single-quoted string.
            safe = text.replace("'", "''")
            subprocess.run(
                [
                    "powershell", "-NoProfile", "-Command",
                    f"Add-Type -AssemblyName System.Speech; "
                    f"(New-Object System.Speech.Synthesis.SpeechSynthesizer)"
                    f".Speak('{safe}')",
                ],
                check=False,
            )
            return
        # Linux / other: best-effort espeak if present.
        subprocess.run(["espeak", text], check=False)

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
            if not self._play_file(fname):
                raise RuntimeError("no audio playback backend available")
        finally:
            try:
                os.unlink(fname)
            except OSError:
                pass

    @staticmethod
    def _play_file(path: str) -> bool:
        """Play an audio file; return True if something actually played."""
        system = platform.system()
        if system == "Darwin":
            return subprocess.run(["afplay", path], check=False).returncode == 0
        # Cross-platform: pygame mixer (already a project dependency).
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            sound = pygame.mixer.Sound(path)
            channel = sound.play()
            if channel is None:
                return False
            while channel.get_busy():
                pygame.time.wait(50)
            return True
        except Exception as e:
            print(f"[TTS] pygame playback failed: {e}")
            return False
