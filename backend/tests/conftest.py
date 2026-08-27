import os
from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import get_settings
from backend.app.db.models import Base
from backend.app.db.session import get_db, reset_engine
from backend.app.main import create_app

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://lenny:lenny@localhost:5432/lenny_assistant",
)


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
def mock_llm_provider():
    provider = MagicMock()
    provider.provider_name = "ollama"
    provider.generate.return_value = (
        "Growth loops are self-reinforcing cycles [Source: Growth Loops (#0)]."
    )
    provider.health_check.return_value = True
    return provider


@pytest.fixture
def client(db_session, mock_embedding_service, mock_llm_provider) -> Generator[TestClient, None, None]:
    app = create_app()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    from backend.app.services import chat as chat_module
    from backend.app.services import ingestion as ingestion_module
    from backend.app.services import rag as rag_module

    original_get_llm = chat_module.get_llm_provider
    original_embedding_cls = ingestion_module.EmbeddingService
    original_rag_embedding_cls = rag_module.EmbeddingService

    chat_module.get_llm_provider = lambda: mock_llm_provider
    ingestion_module.EmbeddingService = lambda: mock_embedding_service
    rag_module.EmbeddingService = lambda: mock_embedding_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    chat_module.get_llm_provider = original_get_llm
    ingestion_module.EmbeddingService = original_embedding_cls
    rag_module.EmbeddingService = original_rag_embedding_cls
