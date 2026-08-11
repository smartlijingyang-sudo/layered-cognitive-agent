# ADR-0053: Unified Search Plane (LobeHub Server Parity)

## Status

Accepted — 2026-08-10

## Context

LCA gateway runs in **Mode A** (closed-loop): LobeHub UI sends **one** chat/completions
request per user turn; LCA executes the full agent loop internally; tool UI is
projected via ``lca.events`` only (never ``delta.tool_calls``).

Gaps observed in production runs (e.g. 「今天有什么新闻」):

1. LobeHub `lobe-web-browsing____search` stripped from prompt, no LCA equivalent.
2. Tavily operational skill assumes `tvly` CLI + login inside sandbox — fails on clean Onlyboxes.
3. `TAVILY_API_KEY` in LobeHub KEY_VAULTS never reaches LCA sandbox.
4. Qwen `LLM_ENABLE_SEARCH` exists but agent routed to broken skill CLI path.
5. `run_command` timeout unit bug (60 interpreted as 60ms → 1s).
6. `activate_skill` UI content truncated to 500 chars raw JSON.
7. **Mode A tool loop misalignment**: emitting ``delta.tool_calls`` triggered LobeHub's native ``call_tool → call_llm`` loop, causing duplicate LCA runs per user turn (fixed: ``lca.events`` lifecycle only).

## Decision

Introduce a **Unified Search Plane** in `lca/layer0_infra/search/`:

| Component | Role |
|-----------|------|
| `WebSearchTool` (`web_search`) | LobeHub wire `lobe-web-browsing____search` |
| `providers/tavily.py` | REST API (no CLI) when `TAVILY_API_KEY` set |
| `router.py` | Search-intent detection + Qwen native fallback kwargs |
| `scope.py` | Run-scoped state (web_search failed → prefer LLM search) |
| `credentials/sandbox_env.py` | Inject `TAVILY_API_KEY` into Onlyboxes preamble |

**Routing policy:**

1. Real-time / news queries → **`web_search`** when Tavily API configured.
2. Tavily unavailable or tool failed → **`enable_search` on LLM** (Qwen native).
3. Never install `tvly` CLI via curl when API key present (prompt + activate_skill hint).

**UI projection (Mode A closed-loop):**

- Tool lifecycle via ``lca.events`` only: ``tool_started`` → ``tool_result`` / ``tool_state``
- **Never** ``delta.tool_calls`` — prevents LobeHub ``GeneralChatAgent`` client tool loop
- LobeHub ``callLlmFinalizer`` sets ``hasToolsCalling=false`` when ``lcaClosedLoop``
- ``activate_skill`` / ``web_search`` content: extract ``{text}`` from payload, 32k cap

**Timeout fix:**

- `run_command.timeout` ≤ 300 → seconds; > 300 → milliseconds (LobeHub compatible).

## Consequences

- Add `TAVILY_API_KEY` to LCA `.env` for Tavily tool path.
- Keep `LLM_ENABLE_SEARCH=true` for fallback when Tavily absent or fails.
- LobeHub `searchMode=off` remains OK — search owned by LCA backend.
- Future providers: register in `SearchSettings.providers` + provider module.

## Alternatives Considered

- **Re-enable LobeHub server tool execution** — breaks Mode A closed-loop.
- **Only LLM search** — loses Tavily citations/UI state when key available.
- **Patch tvly into Onlyboxes image** — fragile; API path is simpler.
