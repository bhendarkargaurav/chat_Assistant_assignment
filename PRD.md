# Product Requirements Document  
## The Lenny Growth Assistant

**Version:** 1.0  
**Date:** 2026-08-27  
**Author:** Forward Deployed Engineer Candidate

---

## 1. Forward Deployment Brief

### 1.1 User and Problem

**Primary user:** Product managers, growth leads, and founders at early-to-mid-stage B2B/B2C companies who follow Lenny Rachitsky's work on product and growth strategy.

**Job to be done:** These practitioners need to quickly extract actionable frameworks from Lenny's large and growing podcast transcript library — without manually skimming hours of content — and turn those insights into polished, shareable work products (essays, briefs, landing pages) that they can use in team meetings, investor decks, or personal publishing.

**Pain removed:**
- Search across hundreds of hours of podcast content currently requires manual effort or basic keyword tools with no semantic understanding.
- Translating an insight into a formatted deliverable (Ship 30 essay, product brief, HTML page) requires context-switching to a separate writing tool, losing the grounding in source material.
- Re-querying an LLM without a structured knowledge base produces hallucinated "Lenny said…" claims that erode trust.

### 1.2 Success Metrics

| Metric | Definition | Target |
|--------|-----------|--------|
| **Grounding rate** | % of chat answers that include at least one `[Source: …]` citation from the transcript corpus | ≥ 90 % |
| **Essay length compliance** | % of Ship 30 essays delivered within ±12 % of the 1,250-word target | ≥ 85 % |
| **P95 response latency (Ollama)** | End-to-end latency for a grounded Q&A turn on a local machine | ≤ 30 s |
| **Artifact sanitization coverage** | % of HTML artifacts that pass `assert_safe_html()` with zero unsafe markers found | 100 % |
| **Setup success** | A new evaluator can clone and reach `/ready` in under 15 minutes following the README | Pass / Fail |

### 1.3 Assumptions

1. **Transcript corpus is representative.** The two bundled sample transcripts are treated as a stand-in for a larger corpus. In production, all publicly available Lenny podcast transcripts would be ingested.
2. **Ollama runs on the evaluator's host machine.** The Docker Compose setup expects Ollama at `host.docker.internal:11434`. The evaluator must run `ollama pull llama3.2` and `ollama pull nomic-embed-text` before starting the stack.
3. **No authentication is required for this demo.** All endpoints are unauthenticated. A production deployment would layer API-key or OAuth2 authentication on top.
4. **Embeddings always use Ollama `nomic-embed-text`.** Using a consistent local embedding model avoids re-embedding the entire corpus when switching between cloud and local chat providers.
5. **The frontend is out of scope for this submission.** The artifact viewer and chat UI are described in the design document and the raw-serve endpoint is implemented, but the browser-side React app is not built. The evaluator uses `curl` + a browser pointing at `/artifacts/{id}/raw` to verify rendering.
6. **PostgreSQL with pgvector is the only supported vector store.** This avoids an additional infrastructure dependency (Pinecone, Weaviate, etc.) and keeps the schema entirely in one database.
7. **A 1,250-word target with ±12 % tolerance is "close enough."** LLM output length is non-deterministic; the bounded retry loop is a reasonable engineering trade-off between quality and latency.

### 1.4 Scope Choices

**Included:**
- Full FastAPI backend with agent routing, RAG, three LLM providers, session/message persistence, artifact generation, HTML sanitization, observability, and Docker Compose.
- Four agent skills: grounded Q&A, Ship 30 for 30 essay, markdown artifact, HTML/CSS artifact.
- Conversation-aware artifact generation ("turn that into a landing page").
- Inline source citations and an automatic `## Sources` section in every artifact.
- Structured JSON logs, in-process metrics counters and latency percentiles, request IDs.
- Comprehensive test suite (~75 tests) with a real pgvector DB, mocked LLM/embeddings.

**Intentionally excluded:**
- **Frontend / UI.** Building a polished React chat interface with an integrated artifact viewer would double the scope. The backend APIs are complete and documented so a frontend team can build on them independently.
- **Alembic migrations.** `create_all` is used at startup. A production handoff would introduce Alembic, but it adds complexity that obscures the core architecture for an evaluator.
- **Authentication and rate limiting.** Out of scope for a local demo; documented as a known gap.
- **Streaming responses.** All LLM calls are blocking for simplicity; streaming would improve perceived latency but requires SSE/WebSocket plumbing on both sides.
- **Automatic transcript refresh / crawling.** Transcripts are ingested manually; scheduled crawling of the Lenny RSS feed is a production concern.

### 1.5 Risks and Trade-offs

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| **Hallucination** | Medium | High | All skills instruct the model to cite sources and admit uncertainty; inline `[Source: …]` format makes unsupported claims visible |
| **Latency (Ollama)** | High | Medium | Local models are slow; `llama3.2` is chosen as a balance between quality and speed on consumer hardware. `LLM_TIMEOUT_SECONDS=180` gives headroom for essay generation |
| **Cost (cloud LLMs)** | Low | Low | Cloud providers are opt-in; Ollama is the default. A 1,250-word essay with `gpt-4o-mini` costs roughly $0.01 |
| **Local model quality** | Medium | Medium | `llama3.2` produces coherent essays but citation adherence is weaker than Claude/GPT-4. Evaluated and documented |
| **Unsafe artifact rendering** | Low | High | Multi-pass sanitization (bleach + tinycss2), CSP header on raw serve, and double-check on write+read. `assert_safe_html` fails closed |
| **Data leakage** | Low | Medium | No user data leaves the machine with Ollama. Cloud provider terms apply when `LLM_PROVIDER=openai/anthropic` |
| **DB connection failure** | Low | High | Startup swallows DB init errors so `/health` stays live; `/ready` reports unready; all DB operations have rollback on `SQLAlchemyError` |
| **Corpus size** | High | Medium | Only two transcripts are bundled. RAG quality degrades with a thin corpus; retrieval falls back to "no matching sources" warning gracefully |

---

## 2. User Flows

### 2.1 Core Q&A Flow
```
User opens session → types question → agent routes to qa skill →
RAG retrieves relevant chunks → LLM answers with inline citations →
answer returned with sources array → user sees grounded response
```

### 2.2 Ship 30 Essay Flow
```
User: "Write a Ship 30 essay about growth loops"
→ Router matches ship30_essay intent (rule: \bship\s*-?\s*30\b, confidence 0.8)
→ Ship30Skill retrieves top-8 chunks for "growth loops"
→ LLM generates ~1,250-word atomic essay with hook / body / takeaway
→ Length correction loop runs if outside ±12% band
→ ## Sources section appended
→ Essay persisted as MARKDOWN artifact
→ Answer + artifact summary returned to user
```

### 2.3 Artifact Generation Flow
```
User: "Turn that into an HTML landing page"
→ Router matches artifact_html intent
→ HtmlArtifactSkill loads last assistant message as "previous" context
→ LLM generates self-contained HTML + CSS
→ sanitize_html_document() strips scripts / iframes / event handlers / dangerous CSS
→ assert_safe_html() fail-closed check
→ Artifact persisted to DB with sources_json
→ User fetches GET /artifacts/{id}/raw to render in browser
```

### 2.4 Switching LLM Providers
```
Edit .env: LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY=sk-...
Restart uvicorn / docker compose up
All subsequent chat turns use Claude; embeddings stay on Ollama
GET /ready confirms provider health
```

---

## 3. Acceptance Criteria

| # | Criterion |
|---|-----------|
| AC-1 | `POST /sessions/{id}/chat` with a question returns an answer containing at least one `[Source: …]` citation when matching transcript chunks exist |
| AC-2 | A Ship 30 essay request produces a markdown artifact with word count between 1,100 and 1,400 words |
| AC-3 | An HTML artifact request produces content that passes `assert_safe_html()` — no `<script>`, `<iframe>`, `onerror`, `javascript:` constructs |
| AC-4 | `GET /artifacts/{id}/raw` for an HTML artifact returns `Content-Security-Policy: default-src 'none'` in the response headers |
| AC-5 | Switching `LLM_PROVIDER` in `.env` and restarting routes all chat turns through the new provider without any code changes |
| AC-6 | When Ollama is unavailable, `GET /ready` returns HTTP 200 with `ollama: false`; the API does not crash |
| AC-7 | A follow-up message in the same session ("Tell me more about that") produces an answer that references the prior turn |
| AC-8 | `docker compose up --build` starts a fully functional stack (DB + API) in one command |
| AC-9 | `pytest -q` passes with a running PostgreSQL instance |
| AC-10 | `GET /metrics` returns counters including `agent_turns_total` after at least one chat turn |

---

## 4. Implementation Plan (Completed)

| Phase | Deliverable | Status |
|-------|------------|--------|
| 1 | FastAPI skeleton, DB models, session CRUD, `/health`, `/ready` | Done |
| 2 | Ingestion service, chunking, pgvector embeddings, RAG retrieval | Done |
| 3 | Agent router (hybrid rules + LLM classifier), orchestrator | Done |
| 4 | Q&A skill, Ship 30 skill, Markdown artifact skill, HTML artifact skill | Done |
| 5 | HTML sanitization (bleach + tinycss2), raw serve with CSP | Done |
| 6 | Observability (structured logs, request IDs, in-process metrics) | Done |
| 7 | Resilience (retries, degraded retrieval, DB rollback, graceful degradation) | Done |
| 8 | Docker Compose, Dockerfile, `.env.example`, HNSW vector index | Done |
| 9 | Tests (~75 across 12 files), linting, type-checking | Done |
| 10 | PRD, Architecture doc, Design doc, README, agent transcripts | Done |
