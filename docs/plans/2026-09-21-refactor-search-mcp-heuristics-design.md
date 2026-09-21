# Architecture Design: Refactor Search, MCP Subsystem, and Freshness Heuristics

**Date**: 2026-09-21  
**Status**: Approved  
**Topic**: Refactor hardcoded search provider chains, temporal year heuristics, layer boundary violations, and MCP lifecycle leaks introduced in commit `ee0b547c7`.

---

## 1. Context & Motivation

Commit `ee0b547c7` introduced MCP integration, multi-provider search (Exa, SearXNG, Tavily), and Grok-style freshness heuristics. However, it also introduced several code smells and architectural violations:
1. **Layer Boundary Violation**: `lca/nodes/concept/tool_fork/dispatch.py` (runtime/cognition plane) imported `from lca.application.api.default_context import holder` with an empty `try...except` block, violating `contracts → infrastructure → cognition → runtime → agent` layering and anti-swallowing rules.
2. **Hardcoded Search Providers**: `lca/infrastructure/search/service/service.py` used an `if-elif` ladder branching on `PROVIDER_EXA`, `PROVIDER_SEARXNG`, `PROVIDER_TAVILY`, breaking the Open-Closed Principle (OCP) and Seam/Provider extensibility.
3. **Hardcoded Heuristics and Magic Numbers**:
   - `TEMPORAL_YEAR_REGEX = r"\b(202[4-9]|203[0-9])\b"` statically hardcoded years `2024..2039`.
   - `search_routing_hint()` statically interpolated the year `"2026"` into prompts.
4. **Subprocess Lifecycle & Async Leaks**:
   - `Agent.__init__` used `ThreadPoolExecutor` and `asyncio.run` inside a synchronous constructor.
   - MCP transports left uncollected subprocess file descriptors on loop teardown, triggering `RuntimeError: Event loop is closed in BaseSubprocessTransport.__del__`.
5. **Flat Settings Model**: All provider-specific options were flatly dumped into `SearchSettings`.

---

## 2. Scope & Boundaries

### 2.1 Owns (In Scope)
- `lca/nodes/concept/tool_fork/dispatch.py`: Remove reverse import of `application.api.default_context`.
- `lca/infrastructure/search/providers/`: Define `SearchProvider` Protocol and `SearchProviderRegistry`.
- `lca/infrastructure/search/service/service.py`: Refactor to delegate to `SearchProviderRegistry` without provider `if` ladders.
- `lca/infrastructure/search/constants/constants.py` & `router/router.py`: Make year detection dynamic based on current UTC time and cutoff year; sanitize prompts.
- `lca/infrastructure/mcp/`: Ensure clean graceful shutdown and process lifecycle termination.
- Unit and scenario tests verifying these behaviors.

### 2.2 Does NOT Own (Out of Scope, AP-01)
- `lca/session/` (EventSession, Journal, Catalog)
- `lca/runtime/` (Execution Loop, Result Projection)
- `lca/infrastructure/memory/` (AssistantMemory, dedupe, etc.)
- Non-search/non-mcp node executors or graph bundles

---

## 3. Detailed Architecture & Design

### 3.1 Architecture Boundary Fix in `tool_fork/dispatch.py`
Remove:
```python
try:
    from lca.application.api.default_context import holder
    if holder.ctx is not None:
        tools_service = holder.ctx.require("tools")
except Exception:
    pass
```
Replace with clean layer-local fallback:
```python
tools_service = input.port_values.get("tools")
if tools_service is None:
    from lca.infrastructure.capability.tools.tools import ToolsService
    tools_service = ToolsService()
```

### 3.2 Search Provider Protocol & Registry
Define `SearchProvider` protocol in `lca/infrastructure/search/providers/protocol.py`:
```python
class SearchProvider(Protocol):
    @property
    def id(self) -> str: ...
    def is_available(self, settings: SearchSettings | None = None) -> bool: ...
    async def search(
        self,
        query: str,
        *,
        topic: str | None = None,
        time_range: str | None = None,
        settings: SearchSettings | None = None,
    ) -> SearchResponse: ...
```
Register built-in providers (`ExaSearchProvider`, `SearXNGSearchProvider`, `TavilySearchProvider`) into `SearchProviderRegistry`.
`service.py` queries `SearchProviderRegistry` in `any_search_provider_available()` and `web_search()`.

### 3.3 Dynamic Temporal Anchoring
In `constants.py` / `router.py`:
- Replace `\b(202[4-9]|203[0-9])\b` with dynamic validation:
  Extract 4-digit years `r"\b(20\d{2})\b"`, checking `2024 <= year <= current_year + 5`.
- In `search_routing_hint()`:
  Interpolate dynamic current year: `curr_year = datetime.datetime.now(datetime.timezone.utc).year`.
  Use generic provider guidance rather than hardcoded environment variable names.

### 3.4 MCP Process Lifecycle & Subprocess Cleanup
In `lca/infrastructure/mcp/transports/stdio.py` & `tool_set.py`:
- Ensure `close()` synchronously or asynchronously waits for process termination and closes stdout/stderr pipes properly.
- Ensure `reset_ambient_mcp_manager()` reliably closes the manager.

---

## 4. Invariants in Tests (AP-02)

1. Zero reverse imports from `lca/nodes/` to `lca/application/`.
2. Existing 16+ tests across `test_search_providers.py`, `test_agent_mcp_injection.py`, `test_mcp_subsystem.py`, and `test_search_skill_policy.py` continue to pass.
3. No `RuntimeError: Event loop is closed` in subprocess transport `__del__`.
4. Dynamic year matches future years relative to `datetime.now()` without hardcoded decade slices.
