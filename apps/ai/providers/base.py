"""AI Provider abstraction layer.

All providers implement the same interface so the rest of the system
is provider-agnostic. Supported providers:
- OpenAI / OpenAI-compatible APIs
- Anthropic
- Google Gemini
- OpenRouter
- Ollama (local)
- Mock (for development without API keys)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AIResponse:
    text: str
    tokens_input: int = 0
    tokens_output: int = 0
    model: str = ""
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)


@dataclass
class VisionResult:
    description: str
    detected_products: list = field(default_factory=list)
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)


class BaseAIProvider(ABC):
    """Abstract base for all AI providers."""

    name: str = "base"

    def __init__(self, api_key: str = "", model: str = "", base_url: str = "", **kwargs):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.options = kwargs

    @abstractmethod
    def chat_completion(self, messages: list, temperature: float = 0.7, max_tokens: int = 2048) -> AIResponse:
        """Generate a chat completion from a list of messages."""
        ...

    @abstractmethod
    def vision_completion(self, image_url: str, prompt: str, temperature: float = 0.5) -> VisionResult:
        """Analyze an image and return a description / product candidates."""
        ...

    def is_available(self) -> bool:
        """Check if the provider is properly configured."""
        return True
