import logging

import httpx

from backend.app.config import get_settings
from backend.app.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def embed_text(self, text: str) -> list[float]:
        url = f"{self.settings.ollama_base_url.rstrip('/')}/api/embeddings"
        payload = {
            "model": self.settings.ollama_embedding_model,
            "prompt": text,
        }
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                embedding = data["embedding"]
                if len(embedding) != self.settings.embedding_dimension:
                    logger.warning(
                        "Embedding dimension mismatch: expected %s got %s",
                        self.settings.embedding_dimension,
                        len(embedding),
                    )
                return embedding
        except httpx.HTTPError as exc:
            logger.exception("Embedding request failed")
            raise ExternalServiceError(f"Embedding request failed: {exc}") from exc

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]

    def health_check(self) -> bool:
        try:
            self.embed_text("health check")
            return True
        except ExternalServiceError:
            return False
