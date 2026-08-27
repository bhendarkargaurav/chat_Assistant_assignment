import logging

import httpx

from backend.app.config import get_settings
from backend.app.exceptions import ExternalServiceError
from backend.app.observability.metrics import METRICS
from backend.app.services.resilience import retry_call

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def embed_text(self, text: str) -> list[float]:
        try:
            embedding = retry_call(
                "embeddings.embed_text",
                lambda: self._request_embedding(text),
                attempts=self.settings.embedding_max_attempts,
                retry_on=(httpx.HTTPError, KeyError, ValueError),
            )
        except Exception as exc:
            METRICS.increment("embedding_failures_total")
            logger.exception("Embedding request failed")
            raise ExternalServiceError(f"Embedding request failed: {exc}") from exc

        if len(embedding) != self.settings.embedding_dimension:
            # A mismatch means pgvector inserts will fail, so surface it as an
            # external service problem rather than letting the DB reject it.
            METRICS.increment("embedding_dimension_mismatch_total")
            raise ExternalServiceError(
                f"Embedding dimension mismatch: expected "
                f"{self.settings.embedding_dimension}, got {len(embedding)}"
            )
        METRICS.increment("embedding_calls_total")
        return embedding

    def _request_embedding(self, text: str) -> list[float]:
        url = f"{self.settings.ollama_base_url.rstrip('/')}/api/embeddings"
        payload = {
            "model": self.settings.ollama_embedding_model,
            "prompt": text,
        }
        with httpx.Client(timeout=self.settings.embedding_timeout_seconds) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            return response.json()["embedding"]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]

    def health_check(self) -> bool:
        """Cheap liveness probe — no retries, so /ready stays fast when Ollama is down."""
        url = f"{self.settings.ollama_base_url.rstrip('/')}/api/tags"
        try:
            with httpx.Client(timeout=5.0) as client:
                return client.get(url).status_code == 200
        except httpx.HTTPError:
            return False
