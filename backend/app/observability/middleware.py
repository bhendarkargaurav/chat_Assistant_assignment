import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from backend.app.observability.context import set_request_id
from backend.app.observability.metrics import METRICS

logger = logging.getLogger("backend.request")

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, times the request and records metrics."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = set_request_id(request.headers.get(REQUEST_ID_HEADER))
        route = request.url.path
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            # Label with the route template, not the raw path, so ids stay out
            # of metric keys.
            template = _route_template(request, route)
            METRICS.increment(
                "http_requests_total",
                method=request.method,
                path=template,
                status=str(status_code),
            )
            METRICS.observe(
                "http_request", elapsed_ms, method=request.method, path=template
            )
            logger.info(
                "%s %s -> %s in %.1fms",
                request.method,
                route,
                status_code,
                elapsed_ms,
                extra={
                    "http_method": request.method,
                    "http_path": route,
                    "http_status": status_code,
                    "duration_ms": round(elapsed_ms, 2),
                },
            )


def _route_template(request: Request, fallback: str) -> str:
    route = request.scope.get("route")
    if isinstance(route, Route):
        return route.path_format
    return fallback
