# ADR-0100 Agent Run Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chat is an Agent Run: `POST /runs` (command) + `GET /runs/{id}/live` (four UI events). LobeHub paints that canvas. `/v1/chat/completions` is housekeeping only.

**Architecture:** Loop stays in Gateway. Journal stays the fact log. The live SSE is a one-way projection to `reasoning | text | tool | done`. LobeHub gets one protocol patch that leaves AgentRuntime.

**Tech Stack:** Python 3 / Starlette / pytest; LobeHub patches under `deploy/lobehub/patches/`.

**Spec:** `docs/adr/0100-chat-command-is-agent-run.md` (binding). Protocol SSOT: `docs/specs/run-live.md`.

## Global Constraints

- Conventional Commits; one theme per commit; no `--no-verify`; no secrets.
- Do not restore ADR-0098 three-channel SSE (`deltas` / `projection.*` / `terminal`).
- Do not emit OpenAI `chat.completion.chunk`, `data: [DONE]`, or `delta.tool_calls` on `/runs/{id}/live`.
- Do not emit decision JSON or `StepTextDelta` channel=`decision` on the live wire.
- `solo` / `team` / `auto` / `cordis-creator` are modes, not upstream model ids.
- `lca_agent_driver` must stay ~200 lines of TS. If it grows, shrink the protocol, don't add a state machine.
- Do not patch `StreamingHandler`, `ClientLLMTransport`, `GeneralChatAgent`, or `Reasoning.tsx`.
- Do not merge the uncommitted ADR-0099 empty-completion encoder WIP.
- Tests: `uv run ruff check --fix <paths> && uv run ruff format <paths> && uv run pytest --no-cov <related-tests> -q`.
- Public Python APIs stay fully typed. No bare `except Exception`. No `print`.
- Gateway is Carrier: HTTP adapters do not import layer4_app.

---

### Task 1: Run UI encoder (four events)

**Files:**
- Create: `lca/plugins/providers/run_ui_encoder/__init__.py`
- Create: `lca/plugins/providers/run_ui_encoder/_encoder.py`
- Create: `tests/plugins/test_run_ui_encoder.py`

**Interfaces:**
- Consumes: journal dataclasses in `lca.contracts.models.observability.journal` (`ReasoningDelta`, `StepTextDelta`, `ToolStarted`, `ToolInvoked`, `ToolDenied`, `DecisionMade`, `AgentRunFinished`, `TeamRunFinished`).
- Produces: `RunUiEncoder.encode(stream) -> AsyncIterator[bytes]` yielding SSE frames.

SSE frame shape (verbatim):

```
id: {seq}
event: {reasoning|text|tool|done}
data: {json}

```

(`id` is the journal `seq` of the source stamped event, integer.)

Data shapes:
- `reasoning`: `{"text": "<delta>"}`
- `text`: `{"text": "<delta>"}`
- `tool`: `{"name": "<tool>", "phase": "started|done|denied", "detail": "<string>"}`
- `done`: `{"status": "completed|failed|canceled|awaiting_human"}` and optional `"error"` string.

Mapping:
- `ReasoningDelta.text_delta` → `reasoning` (skip empty).
- `StepTextDelta` only if `channel == "answer"` → `text` (skip empty / skip `decision`).
- `ToolStarted` → `tool` phase=`started`; `detail` is a short arguments preview (JSON object of known fields, same idea as current OpenAI encoder `_extract_arguments`, keep it small).
- `ToolInvoked` → `tool` phase=`done`; `detail` is `output_text` (truncated is fine) or `"ok"` / error string if `ok is False`.
- `ToolDenied` → `tool` phase=`denied`; `detail` is `reason`.
- `DecisionMade.response_text` → `text` **only if no visible text/reasoning/tool has been emitted yet**.
- `AgentRunFinished` / `TeamRunFinished` → if no visible text yet, emit `text` from `output_text`; if still none and `error`, include `error` on `done`. Then always emit `done`. Map `status` from the event: `completed` / `failed` / `canceled`; if status is `waiting_input` or `awaiting_human` or similar, use `awaiting_human`. Then stop.
- Ignore every other event type.
- After `done`, the generator ends. Do **not** emit `data: [DONE]`.
- Do not emit keepalive here (LiveTail already heartbeats at HTTP layer).

`encode` accepts an async iterator of objects that have `event_type` (or class name) and the dataclass fields. `seq` comes from `getattr(item, "seq", 0)` so stamped events work. If the item has `.event` (StampedEvent), encode the inner event but use the outer `seq`.

- [ ] **Step 1: Write failing tests** in `tests/plugins/test_run_ui_encoder.py` covering: answer text; decision channel dropped; reasoning; tool started/done/denied; finished `output_text` fills empty stream; answer deltas not duplicated by finished; `done` status; no `[DONE]` / no `chat.completion`.

- [ ] **Step 2: Run tests, expect fail** (`ModuleNotFoundError` or import error).

```
uv run pytest --no-cov tests/plugins/test_run_ui_encoder.py -q
```

- [ ] **Step 3: Implement `RunUiEncoder`.** Do not add a Cordis `@plugin` unless an existing encoder in this folder already has one — follow `openai_stream_encoder` (plain importable class). Do not modify `openai_stream_encoder`.

- [ ] **Step 4: Run tests, expect pass.** Then ruff check/format the new files.

- [ ] **Step 5: Commit**

```
git add lca/plugins/providers/run_ui_encoder tests/plugins/test_run_ui_encoder.py
git commit -m "feat(run-ui): encode journal events as four live SSE types"
```

---

### Task 2: `GET /runs/{id}/live` + keep `POST /runs` as 202

**Files:**
- Modify: `gateway/runs/port.py` — add `stream_run_live(self, run_id: str, after: int = 0) -> AsyncIterator[bytes]`
- Modify: `gateway/runs/registry_queries.py` — implement it using `RunUiEncoder` + `session.tail.subscribe(after_seq=after)`
- Modify: `gateway/runs/legacy_adapter.py` — delegate
- Modify: `gateway/runs/query_endpoints.py` — `stream_run_live` HTTP handler
- Modify: `gateway/routes.py` — `Route("/runs/{run_id}/live", stream_run_live, methods=["GET", "OPTIONS"])`
- Create: `tests/test_run_live_ui_sse.py`

**Interfaces:**
- Consumes: `RunUiEncoder` from Task 1; existing `LiveTail.subscribe`; existing `POST /runs` 202 body already includes `live_url`.
- Produces: `GET /runs/{id}/live?after=N` → `text/event-stream` of Task 1 frames. Missing run → 404 JSON `{error: "run not found"}`. CORS + `Cache-Control: no-cache` + `Connection: keep-alive` + `X-Accel-Buffering: no` like other SSE endpoints.

Query param `after` is int, default 0 (same meaning as `subscribe(after_seq=)`). Ignore `Last-Event-ID` for this route (ADR: no reconnect state machine). Pass inner **stamped** events into the encoder so `id:` is journal seq.

Do **not** change `POST /runs` status (already 202 + `live_url`). Do **not** stream from POST. Do **not** restore three-channel event names.

Leave `stream_chat_completion` in place this task (Task 3 removes the OpenAI chat agent path).

HTTP test style: follow `tests/plugins/test_agent_chat_completion_sse.py` (in-memory `RunRegistry` + `LiveTail` + `RegistryRunAdapter`) **and** a Starlette `TestClient` hitting `/runs/{id}/live` via a minimal app or `create_scripted_app` if that helper exists (`tests/test_openai_chat_stream_production.py`).

Must assert:
- `event: text` / `reasoning` / `tool` / `done` appear as SSE `event:` fields
- `data: [DONE]` is absent
- `chat.completion` is absent
- `?after=` skips earlier seqs
- unknown run_id → 404

- [ ] **Step 1: Write failing tests** (`GET /runs/{id}/live` 404 because route missing).

- [ ] **Step 2: Run** `uv run pytest --no-cov tests/test_run_live_ui_sse.py -q` — expect fail.

- [ ] **Step 3: Implement route + port method.**

- [ ] **Step 4: Tests pass. Ruff. Also run `tests/test_gateway_route_catalog.py` (route stays under `/runs` prefix).**

- [ ] **Step 5: Commit** `feat(gateway): serve four-event UI stream on GET /runs/{id}/live`

---

### Task 3: Stop using `/v1/chat/completions` as the Agent start

**Files:**
- Modify: `gateway/openai_endpoints.py` — delete `_agent_chat_completion_stream` and the `model in LCA_UI_MODELS and stream` branch. `chat_completions` is housekeeping only (`chat_completions_from_body`).
- Modify/delete tests that require Agent OpenAI SSE from `/v1/chat/completions`:
  - `tests/test_openai_chat_stream_production.py`
  - `tests/plugins/test_agent_chat_completion_sse.py` (OpenAI wire on `stream_chat_completion`)
  - any assertion that `cordis-creator` + `stream=true` on `/v1/chat/completions` starts a run
- Keep housekeeping tests in `tests/test_openai_compat_gateway.py` (models list, non-stream completions, embeddings).
- `stream_chat_completion` on RunPort may remain unused after this task; do not delete it unless nothing imports it. Prefer leaving it over a broad rename.

Non-stream `/v1/chat/completions` with mode ids must still `resolve_upstream_model` (already true).

- [ ] **Step 1: Write a failing test** that `POST /v1/chat/completions` with `model=solo, stream=true` does **not** call `create_and_dispatch` (spy the run port). Expect current code to fail this test.

- [ ] **Step 2: Run that test, see fail.**

- [ ] **Step 3: Remove the agent branch. Update/remove obsolete OpenAI-agent stream tests so they don't assert the old wire. Point any still-useful LiveTail tests at `stream_run_live` instead of rewriting them as OpenAI chunks.**

- [ ] **Step 4: `uv run pytest --no-cov tests/test_openai_compat_gateway.py tests/test_openai_chat_stream_production.py tests/plugins/test_agent_chat_completion_sse.py tests/test_run_live_ui_sse.py -q` plus ruff on touched files.**

- [ ] **Step 5: Commit** `fix(gateway): keep /v1/chat/completions as housekeeping, not Agent start`

---

### Task 4: LobeHub protocol patch `lca_agent_driver`

**Files:**
- Create: `deploy/lobehub/patches/runtime/lca_agent_driver.py`
- Create: `deploy/lobehub/patches/runtime/LcaAgentDriver.ts` (source copied into the UI by apply)
- Delete: `deploy/lobehub/patches/runtime/drop_lca_chat_hijack.py`
- Delete: `deploy/lobehub/patches/provider/openai_guard.py`
- Modify: `deploy/lobehub/engine.py` comments that name `drop_lca_chat_hijack` / `lca_run_driver` if they would lie
- Test: `tests/test_lobehub_patches.py` or nearest existing patch tests — add apply/idempotency for the new patch; stop expecting `openai_guard` / `drop_lca_chat_hijack`

**Behavior of the TS driver (must stay under ~200 lines):**

1. Patch `src/store/chat/slices/agentRun/actions/transports/client/streamingExecutor.ts` immediately before `const modelRuntimeConfig = {` with marker `/* LCA: every chat is a Run */`. If that marker is present and the virtual-model list includes `cordis-creator`, skip. Insert an early path: for a user chat (not title-only housekeeping), `await runLcaAgentTurn(...)` and `return` — do not construct `GeneralChatAgent`.
2. `runLcaAgentTurn`:
   - `POST /lca-api/runs` with `{ messages, mode: model, model, agent }` (mode from selected catalog id).
   - Read `202` JSON `{ run_id, live_url }`.
   - `GET live_url` (`/lca-api` prefix already rewritten) as `text/event-stream`.
   - Parse `event:` + `data:` frames. Accumulate `text` / `reasoning`. On each `text` or `reasoning`, call existing store `optimisticUpdateMessageContent` (and the existing reasoning updater if one is used by this executor — search; do not patch Reasoning.tsx).
   - `tool` frames append a short markdown line into content (`**name** detail`).
   - `done` with `failed` writes `error` into the message and finishes. `awaiting_human` finishes this GET (do not hang). `completed` finishes.
   - AbortController from the operation: abort the GET and `POST /lca-api/runs/{id}/cancel`.
3. `disableTools` / do not call `call_tool`.
4. Sub-agent / group orchestration paths that are not the main user send may keep upstream behavior if the hijack point is the main `executeClientAgent` — prefer hijacking all `executeClientAgent` chat sends that use LCA catalog ids (`solo|team|auto|cordis-creator`) so they cannot fall into `/webapi/chat/openai`.

Do not reintroduce LcaRunDriver reconnect loops, three-channel parsers, or evidence refs.

- [ ] **Step 1: Add a patch unit test** that `apply` injects the marker and writes `LcaAgentDriver.ts` (follow existing tests for `drop_lca_chat_hijack` / `openai_guard` if present under `tests/`).

- [ ] **Step 2: Run test, expect fail.**

- [ ] **Step 3: Implement patch + TS. Delete the two obsolete patch modules. Grep the repo for `drop_lca_chat_hijack` and `openai_guard` and update references so apply/discover does not break.**

- [ ] **Step 4: Run patch tests + `python3 deploy/lobehub/patch_lobehub.py list` in the worktree if lobehub-ui exists. Ruff on Python.**

- [ ] **Step 5: Commit** `feat(lobehub): drive chat from POST /runs + GET /live`

---

## Task dependency

1 → 2 → 3 → 4. Do not start 2 without a green Task 1 encoder. Task 4 can theoretically start after 2, but keep serial to avoid UI hitting a Gateway that still serves OpenAI chunks on the wrong path.

## Out of scope

- Browser click-through (needs running stack; note in the Task 4 report if not run).
- Deleting `openai_stream_encoder` entirely.
- `/v1/sessions` convergence (ADR-0073).
- Last-Event-ID resume.
