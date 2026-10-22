"""Settings, read from the environment only. Keys and addresses are never read from files, so none can be committed by accident."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .errors import ConfigError

# What the manga must never contain. Exactly the list the old tools sent (the ship words were added for a book where the model drew galleons):
# keeping it identical keeps the pictures identical for a given prompt and seed; override with DRAW_NEGATIVE.
DEFAULT_NEGATIVE = (
    "tall ship, square-rigged ship, galleon, pirate ship, three masts, speech bubble, text balloon, signboard with writing, microphone, modern object, "
    "glasses, wristwatch, mobile phone, camera, electric lamp, neon, plastic, mirror reflection, blurry, low quality, deformed face, extra people, "
    "color, watermark, signature, text, letters, numbers"
)


def _urls(raw: str) -> tuple[str, ...]:
    return tuple(u.strip().rstrip("/") for u in raw.split(",") if u.strip())


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    try:
        value = int(env.get(name, default))
    except ValueError as exc:
        raise ConfigError(f"{name} must be a whole number, got {env.get(name)!r}") from exc
    if value < 1:
        raise ConfigError(f"{name} must be at least 1")
    return value


def _float(env: Mapping[str, str], name: str, default: float) -> float:
    try:
        value = float(env.get(name, default))
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {env.get(name)!r}") from exc
    if not 0.25 <= value <= 4:
        raise ConfigError(f"{name} must be between 0.25 and 4")
    return value


@dataclass(frozen=True)
class Settings:
    """Everything an task may need to know about the machine it runs on."""

    image_urls: tuple[str, ...] = ("http://localhost:8000",)   # one entry per model server; jobs are dealt round-robin
    image_model: str = "Tongyi-MAI/Z-Image-Turbo"
    image_steps: int = 9
    negative_prompt: str = DEFAULT_NEGATIVE
    vision_url: str = "http://localhost:8200"
    vision_model: str = "Qwen/Qwen2.5-VL-7B-Instruct"
    llm_url: str = "http://localhost:8100"
    llm_model: str = "Qwen/Qwen2.5-7B-Instruct"
    llm_threads: int = 24
    site_url: str = "https://sutur.ink"
    scan_threads: int = 12
    tts_url: str = "http://localhost:8300"
    tts_model: str = "tts"
    tts_voice: str = "default"
    tts_speed: float = 1.0
    tts_threads: int = 4
    api_key: str = field(default="", repr=False)   # never printed
    draw_threads_per_server: int = 4
    vision_threads: int = 16
    http_timeout: float = 1800.0
    http_retries: int = 3
    scan_rounds: int = 3

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Settings:
        """Read every setting from the environment.

        GPU_URLS (comma separated) or GPU_URL; DRAW_STEPS, DRAW_NEGATIVE, DRAW_THREADS; VL_URL, VL_MODEL, VL_THREADS, SCAN_ROUNDS, SCAN_THREADS;
        LLM_URL, LLM_MODEL, LLM_THREADS; SITE_URL; TTS_URL, TTS_MODEL, TTS_VOICE, TTS_SPEED, TTS_THREADS;
        UNSLOTH_API_KEY (sent as a bearer token to every server).
        """
        urls = _urls(env.get("GPU_URLS", "")) or _urls(env.get("GPU_URL", "")) or cls.image_urls
        return cls(
            image_urls=urls,
            image_model=env.get("DRAW_MODEL_ID", cls.image_model),
            image_steps=_int(env, "DRAW_STEPS", cls.image_steps),
            negative_prompt=env.get("DRAW_NEGATIVE", DEFAULT_NEGATIVE),
            vision_url=env.get("VL_URL", cls.vision_url).rstrip("/"),
            vision_model=env.get("VL_MODEL", cls.vision_model),
            llm_url=env.get("LLM_URL", cls.llm_url).rstrip("/"),
            llm_model=env.get("LLM_MODEL", cls.llm_model),
            llm_threads=_int(env, "LLM_THREADS", cls.llm_threads),
            site_url=env.get("SITE_URL", cls.site_url).rstrip("/"),
            scan_threads=_int(env, "SCAN_THREADS", cls.scan_threads),
            tts_url=env.get("TTS_URL", cls.tts_url).rstrip("/"),
            tts_model=env.get("TTS_MODEL", cls.tts_model),
            tts_voice=env.get("TTS_VOICE", cls.tts_voice),
            tts_speed=_float(env, "TTS_SPEED", cls.tts_speed),
            tts_threads=_int(env, "TTS_THREADS", cls.tts_threads),
            api_key=env.get("UNSLOTH_API_KEY", ""),
            draw_threads_per_server=_int(env, "DRAW_THREADS", cls.draw_threads_per_server),
            vision_threads=_int(env, "VL_THREADS", cls.vision_threads),
            scan_rounds=_int(env, "SCAN_ROUNDS", cls.scan_rounds),
        )
