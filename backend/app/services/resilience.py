import logging
import random
import time
from collections.abc import Callable

from backend.app.config import get_settings

logger = logging.getLogger(__name__)



def retry_call[T](
    operation: str,
    func: Callable[[], T],
    *,
    attempts: int | None = None,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    base_delay: float | None = None,
) -> T:
    """Run ``func`` with bounded exponential backoff and jitter.

    Re-raises the last exception once the attempt budget is exhausted so callers
    keep control over how the failure is surfaced.
    """
    settings = get_settings()
    max_attempts = max(1, attempts if attempts is not None else settings.llm_max_attempts)
    delay = base_delay if base_delay is not None else settings.retry_base_delay_seconds

    last_error: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except retry_on as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            sleep_for = delay * (2 ** (attempt - 1)) * (0.5 + random.random() / 2)
            logger.warning(
                "%s failed (attempt %s/%s), retrying in %.2fs: %s",
                operation,
                attempt,
                max_attempts,
                sleep_for,
                exc,
            )
            time.sleep(sleep_for)

    logger.error("%s failed after %s attempts", operation, max_attempts)
    if last_error is None:
        raise RuntimeError(f"{operation} exhausted its retry budget without an error")
    raise last_error
