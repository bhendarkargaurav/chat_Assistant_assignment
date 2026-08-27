from backend.app.config import get_settings
from backend.app.exceptions import ConfigurationError
from backend.app.services.llm.anthropic_provider import AnthropicProvider
from backend.app.services.llm.base import LLMProvider
from backend.app.services.llm.ollama import OllamaProvider
from backend.app.services.llm.openai_provider import OpenAIProvider


def get_llm_provider() -> LLMProvider:
    provider = get_settings().llm_provider
    if provider == "ollama":
        return OllamaProvider()
    if provider == "openai":
        return OpenAIProvider()
    if provider == "anthropic":
        return AnthropicProvider()
    raise ConfigurationError(f"Unsupported LLM provider: {provider}")
