# Lenny Growth Assistant — Part 1 Backend

Production-minded FastAPI backend for grounded Q&A over Lenny Rachitsky podcast transcripts using RAG, PostgreSQL + pgvector, and switchable LLM providers (Ollama / OpenAI / Anthropic).

## Architecture

```
Question → FastAPI → Session → RAG → Lenny transcripts → Ollama/Cloud LLM → Grounded answer + sources → PostgreSQL
```

## Features

- **Session-based chat** with persistent message history
- **Transcript ingestion** with chunking and Ollama embeddings
- **Vector search** via pgvector cosine similarity
- **Grounded answers** with source citations
- **Switchable LLM provider** via `LLM_PROVIDER` env var
- **Health/readiness** endpoints
- **Structured logging** and consistent error responses
- **Docker Compose** for PostgreSQL + API

## Project Structure

```
backend/
  app/
    api/routes/     # HTTP endpoints
    db/             # SQLAlchemy models + session
    schemas/        # Pydantic request/response models
    services/       # Business logic (RAG, chat, ingestion, LLM)
data/transcripts/   # Sample Lenny-style transcript files
```

## Prerequisites

- Python 3.12+
- Docker & Docker Compose
- [Ollama](https://ollama.com/) running locally with models:
  - `ollama pull llama3.2`
  - `ollama pull nomic-embed-text`

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env if needed (API keys for cloud providers)
```

### 2. Start PostgreSQL

```bash
docker compose up db -d
```

### 3. Install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 4. Run the API locally

```bash
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Ingest sample transcripts

```bash
curl -X POST http://localhost:8000/documents/ingest-directory
```

### 6. Chat

```bash
# Create a session
curl -X POST http://localhost:8000/sessions -H "Content-Type: application/json" -d "{\"title\": \"Growth questions\"}"

# Ask a question (replace SESSION_ID)
curl -X POST http://localhost:8000/sessions/SESSION_ID/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"What are growth loops?\"}"
```

## Docker (full stack)

```bash
docker compose up --build
```

The API container expects Ollama on the host at `http://host.docker.internal:11434`.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| GET | `/ready` | Readiness (DB, LLM, embeddings) |
| POST | `/sessions` | Create chat session |
| GET | `/sessions` | List sessions |
| GET | `/sessions/{id}` | Get session with messages |
| POST | `/sessions/{id}/chat` | Ask a grounded question |
| POST | `/documents/ingest` | Ingest a transcript |
| POST | `/documents/ingest-directory` | Ingest bundled sample transcripts |

Interactive docs: http://localhost:8000/docs

## LLM Provider Switching

Set in `.env`:

```env
LLM_PROVIDER=ollama    # default — uses local Ollama
LLM_PROVIDER=openai    # requires OPENAI_API_KEY
LLM_PROVIDER=anthropic # requires ANTHROPIC_API_KEY
```

Embeddings always use Ollama (`nomic-embed-text`) for consistent vector dimensions.

## Running Tests

Requires PostgreSQL running (e.g. `docker compose up db -d`):

```bash
pytest -v
```

Tests mock Ollama LLM and embedding calls; PostgreSQL with pgvector is required for DB integration tests.

## Environment Variables

See `.env.example` for the full list. Key variables:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `LLM_PROVIDER` | `ollama`, `openai`, or `anthropic` |
| `OLLAMA_BASE_URL` | Ollama API base URL |
| `OLLAMA_MODEL` | Chat model name |
| `OLLAMA_EMBEDDING_MODEL` | Embedding model name |
| `OPENAI_API_KEY` | OpenAI API key (when using openai) |
| `ANTHROPIC_API_KEY` | Anthropic API key (when using anthropic) |
| `RAG_TOP_K` | Number of chunks to retrieve |

## Part 1 Scope

This implements Part 1 only: backend RAG chat over Lenny transcripts. Frontend, Ship 30 skill, and artifact generation are out of scope.
