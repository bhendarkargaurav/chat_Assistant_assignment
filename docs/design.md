# Design Document  
## The Lenny Growth Assistant — UI/UX Principles & Interaction Design

**Version:** 1.0  
**Date:** 2026-08-27

> **Note on scope:** The frontend is not implemented in this submission; the backend APIs are complete and the artifact raw-serve endpoint is production-ready. This document describes the intended UI/UX so a frontend engineer can build directly from it without a discovery phase.

---

## 1. Design Principles

### 1.1 Grounded confidence, not generic chatbot energy
Every response either cites a source or explicitly says the corpus does not support the claim. The UI must make citations visually distinct — not buried — so users immediately trust or question each answer. An uncited claim should look different from a cited one.

### 1.2 Artifacts are first-class objects, not chat bubbles
Markdown essays and HTML pages are not long text responses. They open in a side panel (the Artifact Viewer), leaving the conversation thread clean. The panel is closable; the artifact is always retrievable from the session history.

### 1.3 Skills are transparent, not magic
Users can see which skill handled their request (`skill: grounded_qa`, `ship30_essay`, etc.) and the router confidence. Power users can force an intent. This builds trust and helps users iterate their prompts.

### 1.4 Degraded states are visible, not silent
If retrieval found no matching sources, the UI shows a yellow "No transcript matches found — answer may be ungrounded" banner. If a word-count target was missed, a badge shows the actual count. Warnings from the API surface as non-blocking UI notices.

### 1.5 Local-first, then cloud
The default experience runs entirely on the evaluator's machine. The provider toggle (Ollama / OpenAI / Anthropic) is visible in the interface — not buried in settings — so switching is a deliberate, visible action.

---

## 2. Information Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Header: "Lenny Growth Assistant"    [Provider badge: Ollama]│
├───────────────────────┬─────────────────────────────────────┤
│  Sidebar              │  Main Panel                         │
│  ─────────────────    │  ─────────────────────────────────  │
│  [+ New Chat]         │  Chat Thread  │  Artifact Viewer    │
│                       │               │  (slides in when    │
│  Recent Sessions      │               │   artifact exists)  │
│  · Growth loops Q&A   │               │                     │
│  · Ship 30 essay      │               │                     │
│  · Landing page gen   │               │                     │
│                       │  [Message input + Send]             │
└───────────────────────┴─────────────────────────────────────┘
```

### 2.1 Sidebar
- **New Chat** button always visible at top.
- Session list shows title (auto-set from first message, truncated to 80 chars) and relative timestamp ("2 hours ago").
- Active session highlighted. Sessions load on click without a full page refresh.
- On mobile: sidebar collapses to a hamburger menu.

### 2.2 Chat Thread
- User messages right-aligned, assistant messages left-aligned.
- Each assistant message shows:
  - The answer text (markdown rendered, not raw)
  - A collapsible **Sources** drawer listing each citation with document title, chunk index, relevance score, and a 300-char excerpt
  - A small metadata pill: `grounded_qa · ollama · 4.2 s`
- Warnings (e.g. "no_matching_sources", "word_count_off_target") shown as amber inline notices directly under the message.

### 2.3 Artifact Viewer Panel
The right-side panel renders the artifact inline — no new tab, no raw code dump.

| Artifact kind | Rendering |
|--------------|-----------|
| `markdown` | Rendered HTML via a markdown parser (e.g. `marked` + `DOMPurify`) |
| `html` | Sandboxed `<iframe>` with `sandbox="allow-same-origin"` only. The `src` points to `GET /artifacts/{id}/raw` which returns the pre-sanitized HTML with a strict CSP. |

Panel controls:
- **Copy** — copies raw content to clipboard
- **Download** — saves as `.md` or `.html`
- **Close** — collapses the panel
- **Open in new tab** — for the HTML artifact, opens `/artifacts/{id}/raw` directly

### 2.4 Provider Badge
A small pill in the header shows the active LLM provider name (e.g. `Ollama llama3.2`). Clicking it opens a settings drawer with a `LLM_PROVIDER` selector and links to `.env` documentation. In the MVP this is read-only display; the toggle requires a server restart.

---

## 3. Key Interaction States

### 3.1 Normal Q&A Turn
```
User types → hits Enter → message appears in thread →
  loading indicator (three dots) appears in assistant bubble →
  answer streams in (or appears at once for non-streaming) →
  Sources drawer collapses by default, expands on click →
  Routing pill shows intent + confidence
```

### 3.2 Artifact Generated
```
Answer arrives with artifacts: [{id, title, kind}] →
  Artifact Viewer panel slides in from the right →
  Panel header: "📄 Growth Loops Playbook  ·  markdown" →
  Content rendered immediately →
  Chat thread shows short confirmation: "Generated the markdown artifact 'Growth Loops Playbook' grounded in 5 excerpts."
```

### 3.3 No Matching Sources
```
Answer arrives with warnings: ["no_matching_sources"] →
  Amber banner below answer:
  "⚠ No transcript excerpts matched this query. The answer below is not grounded in Lenny's podcast."
  Answer still displayed — user can see it but is warned
```

### 3.4 LLM Unavailable (Ollama down)
```
POST /sessions/{id}/chat → 502/503 response →
  Error state in assistant bubble:
  "The language model is unavailable right now. Check that Ollama is running (ollama serve) and try again."
  Retry button offered
```

### 3.5 Long Generation (Ship 30 Essay)
```
User requests essay →
  Loading indicator shows:
  "Writing your Ship 30 essay — this takes 20–60 seconds with a local model…"
  Progress label updates every 5 s
  On arrival: Artifact Viewer opens with the full essay
```

### 3.6 Empty Session / First Visit
```
Centre-screen welcome state:
  "Ask anything about product and growth, grounded in Lenny's podcast transcripts."
  Three suggested prompts:
  · "What are growth loops and how do I find mine?"
  · "Write a Ship 30 essay about retention in B2B SaaS"
  · "Create a landing page for a product-led growth strategy"
```

---

## 4. Responsive Behaviour

| Breakpoint | Layout |
|-----------|--------|
| ≥ 1280 px (desktop) | Three-column: sidebar (240 px) + chat thread (flex) + artifact panel (480 px) |
| 768–1279 px (tablet) | Sidebar collapses to icon rail; artifact panel overlays chat at 80 % width |
| < 768 px (mobile) | Single column; artifact panel is full-screen modal; sidebar is bottom sheet |

The chat input is always pinned to the bottom of the viewport. The artifact panel is never shown at a width that makes the chat thread unusable (minimum chat width: 320 px).

---

## 5. Accessibility Considerations

- All interactive elements are keyboard-navigable (Tab order: sidebar → message input → send button → sources drawer → artifact controls).
- The artifact viewer `<iframe>` has a descriptive `title` attribute: `title="Rendered artifact: {artifact title}"`.
- Loading indicators use `aria-live="polite"` so screen readers announce when the response arrives.
- Color is never the sole indicator of state: warnings use both amber color and a `⚠` icon; citations use both a distinct color and a `[Source: …]` text prefix.
- Minimum contrast ratio: 4.5:1 for body text (WCAG AA). The suggested palette uses `#111827` text on `#F9FAFB` background.
- The markdown renderer must strip any `<script>` or event handler attributes before injecting into the DOM (DOMPurify on the client side, in addition to server-side sanitization).

> Full WCAG compliance validation requires manual testing with assistive technologies (NVDA, VoiceOver) and expert accessibility review.

---

## 6. Design Decisions and Rationale

### Why a side panel instead of a modal for artifacts?
A modal interrupts conversation flow and requires a deliberate close action. A side panel keeps both contexts visible simultaneously — the user can read the essay while referencing the conversation that produced it. This mirrors how Claude Artifacts and Notion AI behave.

### Why render the HTML artifact in a sandboxed iframe pointing at `/raw` rather than injecting it inline?
Injecting server-generated HTML directly into the React DOM creates an XSS surface even after sanitization. An `<iframe sandbox="allow-same-origin">` gives the artifact its own browsing context, so any sanitizer regression cannot reach the parent page. The `allow-same-origin` is needed only for copy/download access to the iframe content; scripts are blocked by the absence of `allow-scripts`.

### Why show routing metadata (intent, confidence, method) to the user?
Product and growth practitioners are sophisticated users. Exposing routing decisions helps them understand why a response was an essay rather than a direct answer, and lets them add "write a Ship 30 essay about…" to their mental model. It also makes debugging far easier during the demo.

### Why auto-collapse the Sources drawer?
Source attribution is important for trust, but most users will not read every excerpt. The default-collapsed state keeps the chat thread readable while making grounding verifiable on demand. Users who care most about citations can expand every time; others see a clean chat experience.

### Why show a loading message specific to the essay skill?
Essay generation with a local model can take 30–90 seconds. A generic spinner with no explanation leads users to think the app is broken. A skill-aware loading label ("Writing your Ship 30 essay…") sets accurate expectations and reduces perceived latency.
