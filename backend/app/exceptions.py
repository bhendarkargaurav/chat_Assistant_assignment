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
