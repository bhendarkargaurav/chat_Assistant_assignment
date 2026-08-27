import logging

import httpx

from backend.app.config import get_settings
from backend.app.exceptions import ExternalServiceError
from backend.app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def provider_name(self) -> str:
        return "ollama"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.settings.ollama_base_url.rstrip('/')}/api/chat"
        payload = {
            "model": self.settings.ollama_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        }
        try:
            with httpx.Client(timeout=self.settings.llm_timeout_seconds) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data["message"]["content"]
        except httpx.HTTPError as exc:
            logger.exception("Ollama request failed")
            raise ExternalServiceError(f"Ollama request failed: {exc}") from exc

    def health_check(self) -> bool:
        url = f"{self.settings.ollama_base_url.rstrip('/')}/api/tags"
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(url)
                return response.status_code == 200
        except httpx.HTTPError:
            return False
