"""Anthropic Claude provider."""

import httpx
from .base import BaseAIProvider, AIResponse, VisionResult


class AnthropicProvider(BaseAIProvider):
    name = "anthropic"

    def __init__(self, api_key: str = "", model: str = "claude-3-5-sonnet-20241022", base_url: str = "", **kwargs):
        super().__init__(api_key, model, base_url, **kwargs)
        self._base_url = base_url or "https://api.anthropic.com"

    def is_available(self) -> bool:
        return bool(self.api_key)

    def chat_completion(self, messages: list, temperature: float = 0.7, max_tokens: int = 2048) -> AIResponse:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        # Convert OpenAI-style messages to Anthropic format
        system_msg = ""
        anthropic_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg += msg["content"] + "\n"
            else:
                anthropic_messages.append({"role": msg["role"], "content": msg["content"]})

        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": anthropic_messages,
        }
        if system_msg:
            payload["system"] = system_msg.strip()

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(f"{self._base_url}/v1/messages", json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                text = data["content"][0]["text"]
                usage = data.get("usage", {})
                return AIResponse(
                    text=text,
                    tokens_input=usage.get("input_tokens", 0),
                    tokens_output=usage.get("output_tokens", 0),
                    model=self.model,
                )
        except Exception as e:
            return AIResponse(text=f"[AI Error: {str(e)}]", model=self.model)

    def vision_completion(self, image_url: str, prompt: str, temperature: float = 0.5) -> VisionResult:
        # Anthropic supports vision via image content blocks
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        import base64 as b64
        try:
            # Fetch image and encode
            with httpx.Client(timeout=30) as client:
                img_resp = client.get(image_url)
                img_data = b64.b64encode(img_resp.content).decode()
                media_type = img_resp.headers.get("content-type", "image/jpeg")

                messages = [{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_data}},
                        {"type": "text", "text": prompt},
                    ],
                }]
                payload = {"model": self.model, "max_tokens": 1024, "temperature": temperature, "messages": messages}
                resp = client.post(f"{self._base_url}/v1/messages", json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                text = data["content"][0]["text"]
                return VisionResult(description=text, confidence=0.8)
        except Exception as e:
            return VisionResult(description=f"[Vision Error: {str(e)}]", confidence=0.0)
