"""OpenAI / OpenAI-compatible API provider.

Works with OpenAI, OpenRouter, Ollama (OpenAI-compatible mode), and any
custom OpenAI-compatible endpoint by setting base_url.
"""

import httpx
from .base import BaseAIProvider, AIResponse, VisionResult


class OpenAIProvider(BaseAIProvider):
    name = "openai"

    def __init__(self, api_key: str = "", model: str = "gpt-4o-mini", base_url: str = "", **kwargs):
        super().__init__(api_key, model, base_url, **kwargs)
        self._base_url = base_url or "https://api.openai.com/v1"

    def is_available(self) -> bool:
        return bool(self.api_key)

    def chat_completion(self, messages: list, temperature: float = 0.7, max_tokens: int = 2048) -> AIResponse:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(f"{self._base_url}/chat/completions", json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                choice = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                return AIResponse(
                    text=choice,
                    tokens_input=usage.get("prompt_tokens", 0),
                    tokens_output=usage.get("completion_tokens", 0),
                    model=data.get("model", self.model),
                )
        except Exception as e:
            return AIResponse(text=f"[AI Error: {str(e)}]", model=self.model)

    def vision_completion(self, image_url: str, prompt: str, temperature: float = 0.5) -> VisionResult:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ]
        payload = {"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": 1024}
        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(f"{self._base_url}/chat/completions", json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                return VisionResult(description=text, confidence=0.8)
        except Exception as e:
            return VisionResult(description=f"[Vision Error: {str(e)}]", confidence=0.0)
