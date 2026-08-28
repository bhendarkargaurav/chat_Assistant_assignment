# Lenny Growth Assistant — Backend

Production-minded FastAPI backend for an agentic assistant over Lenny Rachitsky podcast
transcripts: grounded Q&A, Ship 30 for 30 essays and markdown / HTML artifacts, all built
on RAG over PostgreSQL + pgvector with switchable LLM providers (Ollama / OpenAI / Anthropic).

## Architecture

```
                    User
                     ↓
                   Agent  (router + orchestrator)
                     ↓
          ┌──────────┼──────────┐
          ↓          ↓          ↓
         Q&A      Ship 30    Artifact
          ↓          ↓          ↓
         RAG        RAG      Context
          ↓          ↓          ↓
       Answer      Essay    HTML/MD
                     ↓
                  Sources
```

Every turn: the **router** picks an intent (rules first, LLM classifier only when the rules
are unsure), the matching **skill** retrieves transcript chunks and calls the LLM, and the
**orchestrator** persists the messages plus any generated artifact. Sources travel with the
answer and are embedded in the artifact itself.

Deeper design notes, failure semantics and data model: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Features

- **Agent routing** across four intents: `qa`, `ship30_essay`, `artifact_markdown`, `artifact_html`
- **Grounded Q&A** with inline `[Source: title (#chunk)]` citations and explicit "not in the transcripts" answers
- **Ship 30 for 30 skill** producing ~1,250-word atomic essays with bounded length correction
- **Markdown and HTML/CSS artifacts**, conversation-aware ("turn *that* into a landing page")
- **Artifact persistence + APIs**, including hardened raw serving
- **HTML sanitization** (bleach + tinycss2 allowlists) at generation, storage and serve time
- **Resilience**: retries with backoff, degraded retrieval, DB rollback, artifact failures that don't lose content
- **Observability**: request ids, structured (optionally JSON) logs, `/metrics` counters and latency percentiles
- **Session-based chat**, transcript ingestion, chunking, pgvector cosine search (Part 1, unchanged)

## Project Structure

```
backend/
  app/
    agent/          # Intents, task router, orchestrator
    skills/         # Q&A, Ship 30 essay, markdown/HTML artifact skills
    api/routes/     # HTTP endpoints
    db/             # SQLAlchemy models + session
    observability/  # Request context, metrics, middleware
    schemas/        # Pydantic request/response models
    services/       # RAG, chat, ingestion, artifacts, sanitization, resilience, LLM
  tests/            # Unit + integration tests
data/transcripts/   # Sample Lenny-style transcript files
docs/ARCHITECTURE.md
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
source .venv/bin/activate     # .venv\Scripts\activate on Windows
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

### 6. Talk to the agent

```bash
# Create a session
SESSION=$(curl -s -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" -d '{"title": "Growth questions"}' | jq -r .id)

# Grounded Q&A
curl -X POST http://localhost:8000/sessions/$SESSION/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What are growth loops?"}'

# Ship 30 for 30 essay (~1,250 words, persisted as a markdown artifact)
curl -X POST http://localhost:8000/sessions/$SESSION/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Write a Ship 30 for 30 essay about growth loops"}'

# HTML artifact from the conversation so far
curl -X POST http://localhost:8000/sessions/$SESSION/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Turn that into an HTML landing page"}'

# Render the generated page
curl http://localhost:8000/artifacts/ARTIFACT_ID/raw
```

Add `"intent": "artifact_html"` to a chat request (or use `POST /sessions/{id}/artifacts`)
to bypass routing and force a skill.

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
| GET | `/metrics` | In-process counters and latency percentiles |
| GET | `/skills` | Routable agent capabilities |
| POST | `/sessions` | Create chat session |
| GET | `/sessions` | List sessions |
| GET | `/sessions/{id}` | Get session with messages |
| POST | `/sessions/{id}/chat` | Agent turn (routed to Q&A / essay / artifact) |
| GET | `/sessions/{id}/artifacts` | List artifacts for a session |
| POST | `/sessions/{id}/artifacts` | Generate an artifact of an explicit kind |
| GET | `/artifacts` | List artifacts (`session_id`, `kind`, `limit`, `offset`) |
| GET | `/artifacts/{id}` | Artifact with content, sources and metadata |
| GET | `/artifacts/{id}/raw` | Raw content with hardened headers (`text/html` or `text/markdown`) |
| DELETE | `/artifacts/{id}` | Delete an artifact |
| POST | `/documents/ingest` | Ingest a transcript |
| POST | `/documents/ingest-directory` | Ingest bundled sample transcripts |

Interactive docs: http://localhost:8000/docs

### Chat response shape

```jsonc
{
  "session_id": "…",
  "answer": "Growth loops are … [Source: Growth Loops (#0)]",
  "sources": [{"document_title": "Growth Loops", "chunk_index": 0, "score": 0.82, "excerpt": "…"}],
  "provider": "ollama",
  "skill": "grounded_qa",
  "routing": {"intent": "qa", "confidence": 0.9, "method": "rules", "rationale": "…"},
  "artifacts": [],          // summaries; fetch /artifacts/{id} for content
  "warnings": [],           // e.g. "retrieval_unavailable: …", "word_count_off_target: …"
  "metadata": {}            // skill-specific: word_count, within_target, duration_ms, …
}
```

## Security Model

- All LLM-generated HTML/CSS is sanitized with a **bleach allowlist** (no scripts, iframes,
  objects, forms, event handlers, `javascript:`/`data:` URLs) and a **tinycss2** CSS pass
  (no `@import`, `url()`, `expression()`, `behavior`, `-moz-binding`).
- Sanitization is re-asserted on write **and** on read, so a bad row cannot be served.
- `/artifacts/{id}/raw` sends `Content-Security-Policy: default-src 'none'`, `nosniff`,
  `X-Frame-Options: DENY` and `Referrer-Policy: no-referrer`.
- Artifacts are size-bounded (`ARTIFACT_MAX_BYTES`); secrets are never logged.

## LLM Provider Switching

```env
LLM_PROVIDER=ollama    # default — uses local Ollama
LLM_PROVIDER=openai    # requires OPENAI_API_KEY
LLM_PROVIDER=anthropic # requires ANTHROPIC_API_KEY
```

Embeddings always use Ollama (`nomic-embed-text`) for consistent vector dimensions.

## Development

Requires PostgreSQL running (e.g. `docker compose up db -d`):

```bash
pytest -q            # tests (LLM + embeddings are mocked; pgvector is real)
ruff check .         # lint
mypy backend/app --ignore-missing-imports   # type check
```

## Environment Variables

See `.env.example` for the full list. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://lenny:lenny@localhost:5432/lenny_assistant` | PostgreSQL connection string |
| `LLM_PROVIDER` | `ollama` | `ollama`, `openai`, or `anthropic` |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` / `OLLAMA_EMBEDDING_MODEL` | — | Local model config |
| `RAG_TOP_K` / `RAG_ESSAY_TOP_K` | `5` / `8` | Chunks retrieved for answers / essays |
| `ROUTER_MODE` | `hybrid` | `hybrid`, `rules`, or `llm` |
| `ROUTER_CONFIDENCE_THRESHOLD` | `0.45` | Below this, hybrid mode asks the LLM classifier |
| `CONVERSATION_HISTORY_LIMIT` | `10` | Turns fed to skills for conversation awareness |
| `ESSAY_TARGET_WORDS` / `ESSAY_WORD_TOLERANCE` | `1250` / `0.12` | Essay length target and accepted band |
| `ESSAY_MAX_EXPANSIONS` | `1` | Bounded length-correction passes |
| `ARTIFACT_MAX_BYTES` | `1000000` | Maximum stored artifact size |
| `LLM_MAX_ATTEMPTS` / `LLM_TIMEOUT_SECONDS` | `3` / `180` | LLM retry budget and timeout |
| `EMBEDDING_MAX_ATTEMPTS` / `EMBEDDING_TIMEOUT_SECONDS` | `3` / `60` | Embedding retry budget and timeout |
| `RETRY_BASE_DELAY_SECONDS` | `0.5` | Backoff base for retries |
| `ANTHROPIC_MAX_TOKENS` | `4096` | Max tokens for Anthropic responses (headroom for essays) |
| `LOG_FORMAT` | `text` | `text` or `json` structured logs |

## Manual Test Plan

A quick checklist for verifying the key flows without running automated tests.

**Prerequisites:** API running, transcripts ingested, `SESSION` variable set (see Quick Start).

| # | Step | Expected |
|---|------|----------|
| 1 | `GET /health` | `{"status": "ok"}` |
| 2 | `GET /ready` | `db: true`, `embeddings: true` (ollama must be running) |
| 3 | `POST /sessions` with a title | 201 with a UUID `id` |
| 4 | `POST /sessions/{id}/chat` — `"What are growth loops?"` | Answer contains `[Source: …]` citation; `routing.intent` is `qa` |
| 5 | Follow-up: `"Tell me more about the referral loop"` | Answer references prior context; same `session_id` |
| 6 | `"Write a Ship 30 essay about retention"` | `routing.intent` is `ship30_essay`; `artifacts` array non-empty; `metadata.word_count` between 1100–1400 |
| 7 | `GET /artifacts/{id}` from step 6 | Full markdown content with `## Sources` section |
| 8 | `"Turn that into an HTML landing page"` | `routing.intent` is `artifact_html`; new artifact with `kind: html` |
| 9 | `GET /artifacts/{id}/raw` for the HTML artifact in a browser | Page renders; DevTools Network shows `Content-Security-Policy: default-src 'none'` header |
| 10 | `GET /metrics` | `agent_turns_total` counter reflects the turns taken |
| 11 | Stop Ollama; `GET /ready` | `ollama: false`, `embeddings: false`; API still responds (does not crash) |
| 12 | Switch `LLM_PROVIDER=openai` in `.env`, restart; repeat step 4 | `provider` in response is `openai` |
| 13 | `GET /sessions?limit=2&offset=0` | Returns at most 2 sessions |
| 14 | `DELETE /artifacts/{id}` | 204; subsequent `GET /artifacts/{id}` returns 404 |

---

## Project Documents

| Document | Path | Purpose |
|----------|------|---------|
| PRD | `PRD.md` | User, problem, assumptions, scope, acceptance criteria |
| Architecture | `docs/ARCHITECTURE.md` | Data model, request flow, failure semantics, security |
| Design | `docs/design.md` | UI/UX principles, IA, interaction states, accessibility |
| Agent transcripts | `docs/agent_transcripts/` | Coding session logs with issues found and corrections made |

---

## Scope

Backend only — Part 1 (RAG chat) plus Part 2 (agent routing, Ship 30 essays, artifacts).
The frontend is intentionally not implemented. See `docs/design.md` for the full
UI/UX specification that a frontend team can build from directly.
