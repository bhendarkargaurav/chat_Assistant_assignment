from backend.app.config import get_settings
from backend.app.services.chunking import chunk_text


def test_chunk_text_splits_long_content():
    settings = get_settings()
    text = "word " * (settings.chunk_size + 100)
    chunks = chunk_text(text)
    assert len(chunks) >= 2
    assert all(len(chunk) <= settings.chunk_size + 50 for chunk in chunks)


def test_chunk_text_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_text_short():
    text = "Short transcript excerpt about growth loops."
    assert chunk_text(text) == [text]
