"""Text-to-speech. The protocol is tiny so any server (or a fake) can stand behind it."""

from __future__ import annotations

from typing import Protocol

from ..config import Settings
from ..errors import TransportError
from .http import JsonHttp


class TtsClient(Protocol):
    def speak(self, text: str, voice: str, speed: float = 1.0) -> bytes:
        """The spoken text as mp3 bytes. Raises TransportError when the server cannot be reached."""
        ...


class OpenAISpeechClient:
    """An OpenAI-compatible `/v1/audio/speech` server (many open TTS servers expose this endpoint)."""

    def __init__(self, http: JsonHttp, model: str) -> None:
        self._http, self._model = http, model

    def speak(self, text: str, voice: str, speed: float = 1.0) -> bytes:
        body = {"model": self._model, "input": text, "voice": voice, "speed": speed, "response_format": "mp3"}
        audio = self._http.post_bytes("/v1/audio/speech", body)
        if not audio.startswith((b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")):
            raise TransportError(f"{self._http!r}: the answer is not an mp3 ({audio[:12]!r})")
        return audio

    @classmethod
    def from_settings(cls, s: Settings) -> OpenAISpeechClient:
        return cls(JsonHttp(s.tts_url, s.api_key, 600.0, s.http_retries), s.tts_model)
