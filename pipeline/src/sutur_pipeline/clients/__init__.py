"""Clients for the model servers. Tasks depend on the small protocols here, never on a concrete server."""

from .http import JsonHttp
from .image import ImageClient, ImagePool, OpenAIImageClient
from .llm import ChatClient, OpenAIChatClient
from .tts import OpenAISpeechClient, TtsClient
from .vision import OpenAIVisionClient, VisionClient

__all__ = [
    "ChatClient", "ImageClient", "ImagePool", "JsonHttp", "OpenAIChatClient", "OpenAIImageClient",
    "OpenAISpeechClient", "OpenAIVisionClient", "TtsClient", "VisionClient",
]
