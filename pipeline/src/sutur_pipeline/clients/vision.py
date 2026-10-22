"""Vision-language model: look at a picture and answer a question."""

from __future__ import annotations

import base64
from typing import Protocol

from ..config import Settings
from ..errors import TransportError
from .http import JsonHttp


class VisionClient(Protocol):
    def ask(self, image_jpeg: bytes, question: str, max_tokens: int = 80) -> str:
        """The model's answer as text. Raises TransportError when the server cannot be reached."""
        ...


class OpenAIVisionClient:
    """An OpenAI-compatible `/v1/chat/completions` server with a vision model (Qwen2.5-VL on vLLM)."""

    def __init__(self, http: JsonHttp, model: str) -> None:
        self._http, self._model = http, model

    def ask(self, image_jpeg: bytes, question: str, max_tokens: int = 80) -> str:
        uri = "data:image/jpeg;base64," + base64.b64encode(image_jpeg).decode()
        body = {
            "model": self._model, "max_tokens": max_tokens, "temperature": 0,
            "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": uri}}, {"type": "text", "text": question}]}],
        }
        data = self._http.post("/v1/chat/completions", body)
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise TransportError(f"{self._http!r}: unexpected chat response") from exc

    @classmethod
    def from_settings(cls, s: Settings) -> OpenAIVisionClient:
        return cls(JsonHttp(s.vision_url, s.api_key, 300.0, s.http_retries), s.vision_model)
