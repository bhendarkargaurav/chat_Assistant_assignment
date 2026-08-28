import logging

from openai import OpenAI

from backend.app.config import get_settings
from backend.app.exceptions import ConfigurationError, ExternalServiceError
from backend.app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.openai_api_key:
            raise ConfigurationError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        self.client = OpenAI(api_key=self.settings.openai_api_key)

    @property
    def provider_name(self) -> str:
        return "openai"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                timeout=self.settings.llm_timeout_seconds,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            logger.exception("OpenAI request failed")
            raise ExternalServiceError(f"OpenAI request failed: {exc}") from exc

    def health_check(self) -> bool:
        return bool(self.settings.openai_api_key)
