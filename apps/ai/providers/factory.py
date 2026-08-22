"""AI Provider factory — returns the appropriate provider based on config."""

from django.conf import settings
from .base import BaseAIProvider
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider
from .ollama_provider import OllamaProvider
from .mock_provider import MockAIProvider


PROVIDER_REGISTRY = {
    "openai": OpenAIProvider,
    "openrouter": OpenAIProvider,  # OpenRouter uses OpenAI-compatible API
    "anthropic": AnthropicProvider,
    "ollama": OllamaProvider,
    "google": OpenAIProvider,  # Gemini can use OpenAI-compatible endpoint
    "custom": OpenAIProvider,
    "mock": MockAIProvider,
}


def get_provider(provider_name: str = None, api_key: str = "", model: str = "",
                 base_url: str = "", **kwargs) -> BaseAIProvider:
    """Get an AI provider instance by name."""
    name = provider_name or settings.AI_PROVIDER or "mock"
    provider_class = PROVIDER_REGISTRY.get(name, MockAIProvider)

    # Apply defaults from settings
    if not api_key:
        api_key = settings.AI_API_KEY or getattr(settings, "OPENAI_API_KEY", "")
    if not model:
        model = settings.AI_MODEL
    if not base_url:
        base_url = settings.AI_BASE_URL

    # Provider-specific defaults
    if name == "openrouter":
        api_key = api_key or getattr(settings, "OPENROUTER_API_KEY", "")
        base_url = base_url or getattr(settings, "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    elif name == "ollama":
        base_url = base_url or getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
    elif name == "anthropic":
        api_key = api_key or getattr(settings, "ANTHROPIC_API_KEY", "")

    return provider_class(api_key=api_key, model=model, base_url=base_url, **kwargs)
