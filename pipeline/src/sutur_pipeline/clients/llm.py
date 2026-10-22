"""Text LLM (Qwen2.5-7B on vLLM) for the planning tasks: cast, cover scene, one drawing prompt per panel."""

from __future__ import annotations

from typing import Protocol

from ..config import Settings
from ..errors import TransportError
from .http import JsonHttp


class ChatClient(Protocol):
    def chat(self, system: str, user: str, max_tokens: int = 300, temperature: float = 0.4) -> str:
        """The model's answer, stripped. Raises TransportError when the server cannot be reached."""
        ...


class OpenAIChatClient:
    def __init__(self, http: JsonHttp, model: str) -> None:
        self._http, self._model = http, model

    def chat(self, system: str, user: str, max_tokens: int = 300, temperature: float = 0.4) -> str:
        body = {"model": self._model, "max_tokens": max_tokens, "temperature": temperature,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        data = self._http.post("/v1/chat/completions", body)
        try:
            return str(data["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise TransportError(f"{self._http!r}: unexpected chat response") from exc

    @classmethod
    def from_settings(cls, s: Settings) -> OpenAIChatClient:
        return cls(JsonHttp(s.llm_url, s.api_key, 300.0, s.http_retries), s.llm_model)
