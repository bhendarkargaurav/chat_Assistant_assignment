import uuid
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(request_id: str | None = None) -> str:
    value = request_id or uuid.uuid4().hex[:16]
    request_id_var.set(value)
    return value


def get_request_id() -> str:
    return request_id_var.get()
