"""Text-to-image. The protocol is tiny so a fake can stand in for the GPU in tests."""

from __future__ import annotations

import base64
from typing import Protocol

from ..config import DEFAULT_NEGATIVE, Settings
from ..errors import TransportError
from .http import JsonHttp


class ImageClient(Protocol):
    def generate(self, prompt: str, width: int, height: int, seed: int, negative: str | None = None) -> bytes:
        """One PNG for the prompt. Raises TransportError when the server cannot be reached."""
        ...


class OpenAIImageClient:
    """An OpenAI-compatible `/v1/images/generations` server (vLLM-Omni serving Z-Image)."""

    def __init__(self, http: JsonHttp, model: str, steps: int, negative: str = DEFAULT_NEGATIVE) -> None:
        self._http, self._model, self._steps, self._negative = http, model, steps, negative

    def generate(self, prompt: str, width: int, height: int, seed: int, negative: str | None = None) -> bytes:
        body = {
            "model": self._model, "prompt": prompt, "negative_prompt": self._negative if negative is None else negative,
            "size": f"{width}x{height}", "n": 1,
            "num_inference_steps": self._steps, "guidance_scale": 0.0, "seed": seed, "response_format": "b64_json",
        }
        data = self._http.post("/v1/images/generations", body)
        try:
            return base64.b64decode(data["data"][0]["b64_json"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise TransportError(f"{self._http!r}: unexpected image response") from exc


class ImagePool:
    """Several servers behind one name: job number i goes to server i mod n, so a volume's pictures spread over every GPU."""

    def __init__(self, clients: list[ImageClient]) -> None:
        if not clients:
            raise ValueError("an image pool needs at least one client")
        self._clients = clients

    def __len__(self) -> int:
        return len(self._clients)

    def for_job(self, index: int) -> ImageClient:
        return self._clients[index % len(self._clients)]

    @classmethod
    def from_settings(cls, s: Settings) -> ImagePool:
        def one(url: str) -> OpenAIImageClient:
            return OpenAIImageClient(JsonHttp(url, s.api_key, s.http_timeout, s.http_retries), s.image_model, s.image_steps, s.negative_prompt)

        return cls([one(u) for u in s.image_urls])
