"""Ollama provider for local LLM inference."""

import httpx
from .base import BaseAIProvider, AIResponse, VisionResult


class OllamaProvider(BaseAIProvider):
    name = "ollama"

    def __init__(self, api_key: str = "", model: str = "llama3", base_url: str = "", **kwargs):
        super().__init__(api_key, model, base_url, **kwargs)
        self._base_url = base_url or "http://localhost:11434"

    def is_available(self) -> bool:
        return True  # Local, no API key needed

    def chat_completion(self, messages: list, temperature: float = 0.7, max_tokens: int = 2048) -> AIResponse:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(f"{self._base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return AIResponse(
                    text=data.get("message", {}).get("content", ""),
                    tokens_input=data.get("prompt_eval_count", 0),
                    tokens_output=data.get("eval_count", 0),
                    model=self.model,
                )
        except Exception as e:
            return AIResponse(text=f"[Ollama Error: {str(e)}]", model=self.model)

    def vision_completion(self, image_url: str, prompt: str, temperature: float = 0.5) -> VisionResult:
        # Ollama supports vision models like llava
        payload = {
            "model": self.model if "llava" in self.model or "vision" in self.model else "llava",
            "messages": [{"role": "user", "content": f"{prompt}\nImage: {image_url}"}],
            "stream": False,
            "options": {"temperature": temperature},
        }
        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(f"{self._base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return VisionResult(
                    description=data.get("message", {}).get("content", ""),
                    confidence=0.7,
                )
        except Exception as e:
            return VisionResult(description=f"[Ollama Vision Error: {str(e)}]", confidence=0.0)
