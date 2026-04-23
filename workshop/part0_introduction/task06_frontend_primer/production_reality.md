# Production Reality — Lesson 0.6 Frontend Primer

> The patterns in this lesson (SSE reconciliation, per-concern stores, localStorage persistence) are almost identical in every production chat app. Here's what actually breaks, and what senior engineers do about it.

## What breaks at scale

### 1. SSE reconnection semantics

**The failure mode:** a user's laptop lid closes mid-response. The SSE connection drops. When the lid opens, `EventSource` auto-reconnects — but to a *new* generation. The first half of the response is on-screen; the second half starts from token 0 in a fresh stream. Duplicates or abandonments follow.

Browsers' `EventSource` *does* support `Last-Event-ID` — if the server stamps `id:` on each event, the reconnect handshake sends the last seen ID, and the server can resume. But our baseline doesn't emit `id:` fields, so resumption silently becomes restart.

**What senior engineers do:**
- Emit `id: <token-offset>` on every SSE frame at the Gateway.
- On the server, buffer the last N tokens of each in-flight response keyed by `(session_id, generation_id)`; on `Last-Event-ID` reconnect, replay from that offset.
- Expire the buffer after 30–60 seconds — if the user is gone that long, they can resend.
- If resume is hard to implement, at minimum detect the disconnect on the client and show an explicit "Connection lost — retry" UI instead of silently losing tokens.

### 2. Zustand store bloat

**The failure mode:** somewhere around week 3 of a new app, someone decides the chat store is "the obvious place" for in-flight uploads, or draft messages per session, or the currently-viewed attachment. Six months later, opening the app means deserializing a 40KB JSON blob from localStorage into a single store, and every minor state change triggers a re-render diff against that whole tree.

**What senior engineers do:**
- Split stores by *change rate* and *subscriber set*. Hot state (messages, streaming tokens) goes in a store with many subscribers. Cold state (settings) goes in its own store that most components never touch.
- Never persist chat transcripts. Backend is the source of truth; localStorage is for preferences and UI flags.
- Periodically grep for store fields no one reads. Dead state is a re-render tax with no payoff.

### 3. localStorage quota exhaustion

**The failure mode:** `localStorage` has a ~5MB quota per origin. Serialize a large object, exceed the quota, and the browser throws `QuotaExceededError`. Naive code doesn't catch it — subsequent writes silently fail, settings stop persisting, users complain "my dark mode doesn't stick."

The baseline is safe because we only persist small key–value records. But the *pattern* breaks the moment someone adds "recent searches" or "draft messages" to a persisted store.

**What senior engineers do:**
- Wrap every `persist` store with a quota-check that logs to Sentry on `QuotaExceededError`.
- Cap persisted fields: e.g., `readHistory` keeps only the last 200 entries, oldest evicted.
- For anything that might grow unbounded, use `IndexedDB` via a library like `idb-keyval` — 50MB+ quota, async API.
- Audit persisted size on every release. A one-line `console.log(new Blob([JSON.stringify(state)]).size)` in a dev-only path catches regressions early.

### 4. Bundle size — the markdown renderer problem

**The failure mode:** the lesson-viewer uses a full markdown renderer (`react-markdown` + remark/rehype plugins) plus `highlight.js` for code. Together, those are ~300KB gzipped. On the first load of a marketing page that doesn't need them, that's 300KB of JavaScript the browser downloads and parses before anything renders.

**What senior engineers do:**
- **Route-level code splitting.** `const ContentViewer = lazy(() => import('./content-viewer'))`. The chunk loads only when a lesson is opened.
- Pick lighter parsers if the content is constrained. For pure-CommonMark, `markdown-it` is smaller and faster.
- Use `highlight.js` with a custom subset of languages, not the full grammar pack.
- Track bundle size in CI with `size-limit` or `bundlesize` — alert on any PR that adds > 5KB gzipped.

### 5. React re-render storms during streaming

**The failure mode:** a 1500-token response triggers 1500 re-renders of the message bubble. On a fast desktop, imperceptible. On a low-end phone or a Chromebook, the UI stutters; typing into the input becomes laggy.

**What senior engineers do:**
- Subscribe each bubble to *its own* message slice (the baseline already does this).
- **Batch token flushes.** Group 5–10 tokens per `appendToMessage` call. Users can't perceive < 16ms of delay; the re-render savings are 5–10x.
- For extreme cases: drop to a `ref`-based path for the streaming message. Append tokens directly to `innerText`; flip back to React state on `done` so subsequent re-renders use the normal path.
- Use the React Profiler early. A 2-minute recording during a long stream makes the hotspot obvious.

## What fails in production

### The SSE that never closes

Your gateway holds an SSE connection open. The model stalls for 60 seconds, then crashes. The gateway never sends `done` and never sends `error`. The browser sits there with a spinner forever, because `EventSource.onerror` only fires on transport-level failures, not on application-level silence.

**Mitigation:**
- **Heartbeat.** Emit a comment-event (`: ping\n\n`) every 15 seconds. The client resets an idle timer on every receive; if no receive for 30 seconds, it closes the connection and shows a "Connection lost" UI.
- **Server-side timeout.** The gateway enforces an absolute max of (e.g.) 120 seconds per stream. On timeout, emit `event: error\ndata: timeout\n\n`, then close.

### The optimistic update that fails to reconcile

`persistUserMessage` POSTs the user's message to the DB. The POST fails (network, 500, rate limit). The local state already shows the message. Now the user sees a message that isn't really saved; if they refresh, it's gone.

**Mitigation:**
- Tag optimistic messages with `status: 'pending'`. Render them with a subtle indicator (faded, small spinner).
- On POST success, update to `status: 'saved'`. On failure, update to `status: 'failed'` and show a retry button.
- Never silently swap state. The user has to see that something went wrong, with an action to fix it.

### Accessibility failure during streaming

Screen readers have no concept of "streaming text appearing over time." Three bad states are common:
- Reader ignores the region entirely (no updates announced).
- Reader re-announces the full text on every token (unusable).
- Reader announces partial tokens (gibberish).

**Mitigation:**
- `aria-live="polite"` on the message region — announces updates at natural pauses.
- On `done`, update a visually-hidden status element to "Response complete." The reader announces it once.
- Do *not* use `aria-live="assertive"` — it interrupts whatever the user is doing. `polite` is correct for chat.

## Senior engineer patterns

### Pattern 1 — "Local is fast, server is truth"

The baseline chat flow is the canonical expression of this pattern:
- Act locally first. Fast, feels instant.
- Reconcile with the server asynchronously. On success, confirm. On failure, surface.
- Never assume the two are in sync without an explicit confirmation step.

This applies far beyond chat — it's how Notion, Linear, and every modern collaborative app feel snappy on a spotty connection.

### Pattern 2 — Per-concern stores (or: the cohesion rule)

One store per *concern*, not per *page*. Settings don't belong in the chat store even if the chat view reads them. When you feel the urge to add a field, check: does any *other* concern also read or write this? If yes, it's cross-cutting and probably belongs in its own store.

### Pattern 3 — The "suspicion boundary"

During streaming, you cannot trust the server to tell you the truth about your message's final form — the DB row doesn't exist yet. During post-stream, you cannot trust local state — the tempId might not match the real id. Draw the boundary explicitly with `status: 'streaming' | 'persisted' | 'failed'` on every message. Every render branches on that field.

### Pattern 4 — Keep persistence dumb

Zustand's `persist` middleware should serialize exactly what it says it serializes. No magic "reset to defaults if shape changed" logic in user-land; use `migrate` in the middleware config. No encryption in localStorage (the threat model is wrong — anyone with the device has the key). Keep it boring, audit it once, forget about it.

## Monitoring needed

| Signal | Why | Tool |
|---|---|---|
| **SSE stream abandonment rate** | Tab closes / disconnects during stream | Log `stream_abandoned` event with partial token count |
| **Time-to-first-token (TTFT)** | User-perceived latency of streaming | RUM, `performance.mark` on send, on first token |
| **Time-to-done** | Total stream duration | RUM, measured on `done` event |
| **Reconciliation failures** | `persistAssistantMessage` errors | Sentry + log with session id |
| **localStorage errors** | `QuotaExceededError` and friends | Sentry wrapping all `persist` operations |
| **Re-render count per chat view** | Detect streaming storms | React Profiler in prod-sampled builds |
| **Bundle size per route** | Regression detector for code-split | `size-limit` in CI |

## Common mistakes

1. **Putting chat transcripts in `persist` stores.** Works for a week, blows quota after that, fails silently.
2. **Assuming `EventSource.onerror` means "the stream failed."** It means the *transport* failed. Application-level silence looks identical to a healthy idle.
3. **Mutating a message object in place.** Zustand's shallow-equal diff skips the update; the bubble never re-renders.
4. **Not debouncing `persist` writes.** Every token write hits localStorage; synchronous writes block the main thread at ~1KB/ms.
5. **Using React Context for hot state.** Context subscribers don't select — every consumer re-renders on every change. Fine for theme, catastrophic for streaming.
6. **Letting the SSE connection leak.** If the component unmounts mid-stream, you must call `EventSource.close()` in the cleanup function. Otherwise the browser keeps downloading tokens into the void.
7. **Swallowing `QuotaExceededError`.** You'll never know persistence has stopped working until a user emails support.

## Interview-style questions

1. **Why use Zustand over Redux for this app?**
   *Less boilerplate, no reducers/actions ceremony, `persist` middleware out of the box. Redux pays off once you need middleware chains, time-travel debugging, or strict action logs. For a six-store app, Zustand is the right fit.*

2. **What happens if the user closes the tab mid-stream?**
   *`EventSource.close()` fires in the cleanup, the browser tears down the connection, the gateway sees the disconnect and cancels the upstream model call. If the partial response should be saved, the gateway needs to persist what it has before returning — otherwise those tokens are lost.*

3. **Why isn't the chat state persisted to localStorage?**
   *Size (chat history grows unbounded, localStorage is ~5MB total), performance (writing on every token stalls the main thread), and correctness (Postgres is the source of truth — syncing two sources is a duplicate-bug factory).*

4. **Describe a race between `appendToMessage` and `persistAssistantMessage`.**
   *If `done` arrives before the final token's `appendToMessage` call settles, the persisted message is missing the last token. Mitigation: queue `appendToMessage` calls and await them before persisting, or flush the tail buffer synchronously on `done`.*

5. **How would you implement SSE resume after a drop?**
   *Emit `id: <offset>` on every frame (offset in tokens or bytes). On reconnect, the browser sends `Last-Event-ID` in the headers. Server keyes into a per-session ring buffer, replays from that offset, then continues the live stream. Buffer expires after ~60s.*

6. **A user says "my dark mode preference doesn't stick." What's your debugging path?**
   *DevTools → Application → Local Storage → look for `prodigon-settings`. Absent → quota exceeded or key changed. Present but stale → check the `persist` middleware's serialize/deserialize. Check for `QuotaExceededError` in the console. If theme is in memory but not localStorage, the write is failing silently.*

## Further reading

- [MDN: Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events) — the protocol
- [Zustand — Patterns and anti-patterns](https://zustand.docs.pmnd.rs/guides/tutorial-tic-tac-toe) — author-endorsed idioms
- [web.dev: Prefer `IndexedDB` over `localStorage`](https://web.dev/articles/indexeddb-best-practices) — when `persist` isn't enough
- [React Profiler docs](https://react.dev/reference/react/Profiler) — catching re-render storms
- [Accessible live regions](https://www.w3.org/WAI/ARIA/apg/patterns/alert/) — `aria-live` semantics done right
- `../task04_request_flows/README.md` — the backend side of SSE
- `frontend/src/stores/chat-store.ts` — the reconciliation actions, with comments
