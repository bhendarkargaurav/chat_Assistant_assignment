import logging

import anthropic

from backend.app.config import get_settings
from backend.app.exceptions import ConfigurationError, ExternalServiceError
from backend.app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.anthropic_api_key:
            raise ConfigurationError(
                "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic"
            )
        self.client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        try:
            response = self.client.messages.create(
                model=self.settings.anthropic_model,
                max_tokens=self.settings.anthropic_max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            parts = [block.text for block in response.content if block.type == "text"]
            return "".join(parts)
        except Exception as exc:
            logger.exception("Anthropic request failed")
            raise ExternalServiceError(f"Anthropic request failed: {exc}") from exc

    def health_check(self) -> bool:
        return bool(self.settings.anthropic_api_key)
