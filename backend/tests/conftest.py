import os
from collections.abc import Callable, Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import get_settings
from backend.app.db.models import Base
from backend.app.db.session import get_db, reset_engine
from backend.app.main import create_app
from backend.app.observability.metrics import METRICS
from backend.app.services import chat as chat_module
from backend.app.services import ingestion as ingestion_module
from backend.app.services import rag as rag_module

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://lenny:lenny@localhost:5432/lenny_assistant",
)

QA_ANSWER = "Growth loops are self-reinforcing cycles [Source: Growth Loops (#0)]."

MARKDOWN_ARTIFACT = """# Growth Loops Playbook

## Why it matters
Loops compound where funnels leak [Source: Growth Loops (#0)].

## Steps
1. Map the loop.
2. Instrument each step.
"""

HTML_ARTIFACT = """<!DOCTYPE html>
<html><head><title>Growth Loops</title>
<style>body { font-family: system-ui; color: #111; } .card { padding: 24px; }</style>
</head>
<body><header><h1>Growth Loops</h1></header>
<main><section class="card"><p>Loops compound. Source: Growth Loops (#0)</p></section></main>
</body></html>
"""


def _essay(words: int) -> str:
    body = " ".join(["growth"] * max(0, words - 12))
    return (
        "# Growth Loops Beat Funnels\n\n"
        "Hook sentence about loops [Source: Growth Loops (#0)].\n\n"
        f"## The claim\n\n{body}\n"
    )


class FakeLLMProvider:
    """Deterministic provider that answers based on the calling skill's prompt."""

    def __init__(self) -> None:
        self.provider_name = "ollama"
        self.calls: list[tuple[str, str]] = []
        self.responses: dict[str, str | Callable[[str, str], str]] = {}
        self.failure: Exception | None = None
        self.essay_words = [1250]

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if self.failure is not None:
            raise self.failure

        for marker, response in self.responses.items():
            if marker in system_prompt or marker in user_prompt:
                return response(system_prompt, user_prompt) if callable(response) else response

        if "You classify user requests" in system_prompt:
            return '{"intent": "qa", "confidence": 0.8, "rationale": "Looks like a question."}'
        if "Ship 30 for 30 writing coach" in system_prompt:
            index = min(
                len([c for c in self.calls if "Ship 30 for 30 writing coach" in c[0]]) - 1,
                len(self.essay_words) - 1,
            )
            return _essay(self.essay_words[index])
        if "standalone, self-contained HTML pages" in system_prompt:
            return HTML_ARTIFACT
        if "polished markdown documents" in system_prompt:
            return MARKDOWN_ARTIFACT
        return QA_ANSWER

    def health_check(self) -> bool:
        return True


def _database_available() -> bool:
    try:
        engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(
    not _database_available(),
    reason="PostgreSQL test database not available",
)


@pytest.fixture(scope="session")
def db_engine():
    if not _database_available():
        pytest.skip("PostgreSQL test database not available")

    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    get_settings.cache_clear()
    reset_engine()

    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture
def db_session(db_engine) -> Generator[Session, None, None]:
    connection = db_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def mock_embedding_service():
    service = MagicMock()
    service.embed_text.return_value = [0.01] * get_settings().embedding_dimension
    service.embed_texts.side_effect = lambda texts: [
        [0.01] * get_settings().embedding_dimension for _ in texts
    ]
    service.health_check.return_value = True
    return service


@pytest.fixture
def mock_llm_provider() -> FakeLLMProvider:
    return FakeLLMProvider()


@pytest.fixture(autouse=True)
def reset_metrics():
    METRICS.reset()
    yield


@pytest.fixture
def client(
    db_session, mock_embedding_service, mock_llm_provider
) -> Generator[TestClient, None, None]:
    app = create_app()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    original_get_llm = chat_module.get_llm_provider
    original_embedding_cls = ingestion_module.EmbeddingService
    original_rag_embedding_cls = rag_module.EmbeddingService

    chat_module.get_llm_provider = lambda: mock_llm_provider
    ingestion_module.EmbeddingService = lambda: mock_embedding_service
    rag_module.EmbeddingService = lambda: mock_embedding_service

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    chat_module.get_llm_provider = original_get_llm
    ingestion_module.EmbeddingService = original_embedding_cls
    rag_module.EmbeddingService = original_rag_embedding_cls


@pytest.fixture
def ingested_client(client) -> TestClient:
    """A client with one transcript already ingested."""
    client.post(
        "/documents/ingest",
        json={
            "title": "Growth Loops",
            "source": "growth.txt",
            "content": (
                "Growth loops are self-reinforcing cycles where output becomes input. "
                "Referral loops and content loops are common in product-led growth."
            ),
        },
    )
    return client


@pytest.fixture
def session_id(ingested_client) -> str:
    return ingested_client.post("/sessions", json={"title": "Chat"}).json()["id"]


@pytest.fixture
def session_id_without_documents(client) -> str:
    return client.post("/sessions", json={"title": "Empty"}).json()["id"]
