"""A small JSON-over-HTTP client with retries. Standard library only."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from ..errors import TransportError

_RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


class JsonHttp:
    """POST JSON, get JSON back. Retries timeouts, connection errors and 5xx/429 with exponential backoff; 4xx fails at once."""

    def __init__(self, base_url: str, api_key: str = "", timeout: float = 600.0, retries: int = 3, backoff: float = 1.5) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.timeout, self.retries, self.backoff = timeout, retries, backoff

    def __repr__(self) -> str:   # the key is never shown
        return f"JsonHttp({self.base_url!r})"

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return json.loads(self.post_bytes(path, body))  # type: ignore[no-any-return]

    def post_bytes(self, path: str, body: dict[str, Any]) -> bytes:
        """POST JSON, get the raw answer (audio, images). Same retries as `post`."""
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = urllib.request.Request(self.base_url + path, json.dumps(body).encode(), headers, method="POST")
        last: Exception | None = None
        attempts = 0
        for attempt in range(self.retries):
            attempts += 1
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                    return resp.read()   # type: ignore[no-any-return]
            except urllib.error.HTTPError as exc:
                last = exc
                exc.close()
                if exc.code not in _RETRY_STATUS:
                    break
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                last = exc
            if attempt + 1 < self.retries:
                time.sleep(self.backoff**attempt)
        raise TransportError(f"POST {self.base_url}{path} failed after {attempts} {"try" if attempts == 1 else "tries"}: {last}")
