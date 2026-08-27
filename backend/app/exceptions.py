class AppError(Exception):
    """Base application error."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=404)


class ValidationAppError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422)


class ExternalServiceError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=502)


class ConfigurationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=500)


class LLMError(ExternalServiceError):
    """Raised when the configured LLM provider cannot produce a completion."""


class RetrievalError(AppError):
    """Raised when retrieval fails in a way that cannot be degraded around."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=503)


class PersistenceError(AppError):
    """Raised when the database rejects or loses a write."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=503)


class ArtifactError(AppError):
    """Raised when artifact generation or sanitization fails."""

    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message, status_code=status_code)
