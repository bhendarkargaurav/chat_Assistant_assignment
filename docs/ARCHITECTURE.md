# Architecture

Backend for the Lenny Growth Assistant: a small agent that answers questions, writes
Ship 30 for 30 essays and produces markdown / HTML artifacts, always grounded in ingested
podcast transcripts.

## Request flow

```
POST /sessions/{id}/chat
        │
        ▼
  ChatService ──► AgentService (orchestrator)
                      │
                      ├─ load session + last N turns (conversation awareness)
                      ├─ persist the user message (before anything can fail)
                      ├─ TaskRouter ──► Intent
                      │      rules ──(low confidence, hybrid mode)──► LLM classifier
                      ├─ Skill.run(SkillContext)
                      │      ├─ RAGService.retrieve  → pgvector cosine search
                      │      └─ LLMProvider.generate → retried, bounded
                      ├─ persist the assistant message
                      └─ persist ArtifactDrafts (failures degrade to warnings)
                      ▼
                 ChatResponse: answer + sources + routing + artifacts + warnings + metadata
```

## Components

| Layer | Module | Responsibility |
|-------|--------|----------------|
| Routing | `backend/app/agent/router.py` | Map a message to one of four `Intent`s |
| Orchestration | `backend/app/agent/orchestrator.py` | History, persistence staging, skill execution, metrics |
| Skills | `backend/app/skills/` | `grounded_qa`, `ship30_essay`, `markdown_artifact`, `html_artifact` |
| Retrieval | `backend/app/services/rag.py` | Embed query, cosine search, `SourceCitation`s |
| Artifacts | `backend/app/services/artifacts.py` | Persist / read / delete, revalidate HTML |
| Safety | `backend/app/services/sanitize.py` | Bleach + tinycss2 allowlists, fail-closed assertions |
| Resilience | `backend/app/services/resilience.py` | `retry_call` with exponential backoff + jitter |
| Observability | `backend/app/observability/` | Request ids, counters, latency percentiles, middleware |

Skills are pure: they receive a `SkillContext` (message, history, RAG handle, LLM handle,
settings, router params) and return a `SkillResult` (answer, sources, artifact drafts,
metadata, warnings). All persistence lives in the orchestrator, which keeps skills trivially
testable and makes failure handling uniform.

## Routing

`TaskRouter` scores the message against weighted regex rules per intent and derives a
confidence from the top score and its margin over the runner-up. Output format beats content
style, so "write an essay as a web page" routes to `artifact_html`.

- `ROUTER_MODE=rules` — deterministic only (used in tests, and safe when the LLM is down).
- `ROUTER_MODE=hybrid` (default) — rules first; if confidence < `ROUTER_CONFIDENCE_THRESHOLD`
  the LLM classifier is asked for JSON `{intent, confidence, rationale}`.
- `ROUTER_MODE=llm` — always ask the classifier.

Any classifier failure (timeout, non-JSON, unknown intent) logs, increments
`router_llm_failures_total` and falls back to the rule decision — routing never fails a turn.
Callers can bypass routing entirely with `{"intent": "..."}` on the chat request or by using
`POST /sessions/{id}/artifacts`.

## Skills

**`grounded_qa`** — retrieves `RAG_TOP_K` chunks, prompts the model to answer only from the
excerpts plus conversation history, requires inline `[Source: title (#chunk)]` citations, and
to say plainly when the transcripts don't cover the question.

**`ship30_essay`** — retrieves `RAG_ESSAY_TOP_K` chunks and writes an atomic essay (hook →
framing → three `##` body sections → "How to apply this" → closing takeaway). The result is
word-counted; if it falls outside `ESSAY_TARGET_WORDS ± ESSAY_WORD_TOLERANCE` (default
1,100–1,400) the skill runs up to `ESSAY_MAX_EXPANSIONS` correction passes, then warns rather
than looping. A `## Sources` section is appended and the essay is stored as a markdown artifact.

**`markdown_artifact` / `html_artifact`** — build briefs, playbooks, checklists, one-pagers or
standalone styled pages. Both feed the recent conversation and the last assistant message into
the prompt so "turn *that* into a landing page" works. Markdown gets an appended sources
section; HTML gets a `<footer class="sources">` and is rebuilt inside a controlled document
shell after sanitization.

## Data model

```
sessions ──< messages
    │            │
    └──< artifacts >─ message_id (SET NULL)
```

`artifacts`: `id`, `session_id`, `message_id`, `kind` (`markdown` | `html`), `title`,
`content`, `skill`, `word_count`, `sources_json`, `metadata_json`, timestamps. Sources are
stored with the artifact so attribution survives independently of the chat transcript.

Schema is created with `Base.metadata.create_all` at startup (adequate for this assignment;
a real deployment would use Alembic migrations).

## Failure handling

| Failure | Behaviour |
|---------|-----------|
| LLM error / timeout | `retry_call` retries `LLM_MAX_ATTEMPTS` times with backoff + jitter, then `LLMError` → HTTP 502 |
| Empty LLM output | Treated as a failure (`LLMError`), never persisted |
| Retrieval / embedding outage | Skill degrades: empty sources, `retrieval_unavailable` warning, prompt tells the model to admit missing grounding |
| No matching chunks | `no_matching_sources` warning; the answer says the transcripts don't cover it |
| Database write error | Rollback + `PersistenceError` → HTTP 503 |
| Artifact persistence error | Answer is still returned with an `artifact_not_persisted` warning — an expensive generation is never thrown away |
| Unsafe generated HTML | `ArtifactError` → HTTP 422; nothing unsafe is stored |
| Oversized artifact | Rejected against `ARTIFACT_MAX_BYTES` |

The user message is committed *before* the skill runs, so an LLM outage cannot lose input.

## Security

Generated HTML passes through `sanitize_html_document`: dangerous elements (`script`,
`iframe`, `object`, `embed`, `form`, `svg`, `math`, `link`, `meta`, `base`) are removed with
their contents, attributes are allowlisted (no `on*` handlers), and URLs are restricted to
`http`, `https` and `mailto` — `data:` and `javascript:` are rejected. `<style>` blocks are
parsed with tinycss2 and stripped of `@import`, `url()`, `expression()`, `behavior` and
`-moz-binding`. `assert_safe_html` re-checks content on write and on read, and
`/artifacts/{id}/raw` adds a restrictive CSP plus `nosniff`, `X-Frame-Options: DENY` and
`Referrer-Policy: no-referrer`.

## Observability

`RequestContextMiddleware` assigns/propagates `X-Request-ID`, times every request and labels
metrics with the route *template* (never raw ids). Every log line carries the request id;
`LOG_FORMAT=json` switches to structured JSON. `GET /metrics` exposes in-process counters
(`agent_turns_total`, `router_decisions_total`, `llm_calls_total`, `llm_failures_total`,
`retrieval_failures_total`, `artifacts_created_total`, `app_errors_total`, …) and latency
summaries (count / avg / p50 / p95 / max) for HTTP requests and skill runs. Counters are
process-local — a real deployment would export them to Prometheus.

## Testing

`pytest -q` runs 75 tests against a real pgvector database with the LLM and embedding calls
faked by a deterministic provider:

- `test_router.py` — rule coverage, format-over-style precedence, LLM fallback paths
- `test_sanitize.py` — XSS vectors, CSS hardening, fail-closed assertions
- `test_agent_flow.py` — Q&A, essay (+ length correction), markdown/HTML artifacts, conversation awareness
- `test_artifacts_api.py` — list/filter/paginate/get/raw/delete, forced kinds, 404s
- `test_resilience.py` — retry semantics, LLM outage, retrieval degradation, artifact persistence failure
- `test_observability.py` — request ids, metric counters, `/skills`
- Part 1 suites (`test_chat`, `test_sessions`, `test_ingestion`, `test_chunking`, `test_health`) unchanged

## Known gaps / next steps

- No Alembic migrations (`create_all` at startup).
- Metrics are in-process only; no Prometheus exporter or tracing.
- Artifacts are immutable — no revisions or update endpoint yet.
- No auth/rate limiting; the API assumes a trusted caller.
- Essay length correction is bounded to one pass, so a badly behaved model can still land
  outside the target band (surfaced as a warning).
