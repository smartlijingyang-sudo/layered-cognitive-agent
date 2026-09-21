# Refactor Search, MCP Subsystem, and Freshness Heuristics Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Clean up hardcoded search provider chains, temporal regex heuristics, layer boundary violations, and MCP lifecycle leaks introduced in `ee0b547c7`.

**Architecture:** 
1. Eliminate the `lca/nodes/concept/tool_fork/dispatch.py` reverse import to `lca.application.api.default_context`.
2. Introduce a `SearchProvider` Protocol and `SearchProviderRegistry` in `lca/infrastructure/search/providers/` to replace the hardcoded `if provider == ...` ladder in `service.py`.
3. Replace the static `\b(202[4-9]|203[0-9])\b` regex and static prompt years with a dynamic year evaluator and sanitized prompt guidance.
4. Enhance `MCPManager` / `StdioMCPTransport` teardown to ensure child subprocesses are cleanly collected without leaving closed event-loop errors.

**Tech Stack:** Python 3.11, Pydantic v2, Pytest, Structlog, Asyncio.

---

### Task 1: Clean layer boundary in `tool_fork/dispatch.py`

**Files:**
- Modify: `lca/nodes/concept/tool_fork/dispatch.py:218-232`
- Test: `tests/concept/test_tool_fork_dispatch.py`
- Does NOT own: `lca/application/`, `lca/session/`, `lca/runtime/`
- Invariants to test:
  - `dispatch.py` does not contain `lca.application` in its imports or AST.
  - When `input.port_values.get("tools")` is omitted, fallback uses `ToolsService()` without raising or swallowing exceptions.

**Step 1: Write failing test / lint check**
Add a test in `tests/concept/test_tool_fork_dispatch.py`:
```python
def test_tool_fork_dispatch_no_application_layer_imports():
    import inspect
    from lca.nodes.concept.tool_fork import dispatch
    src = inspect.getsource(dispatch)
    assert "lca.application" not in src
```

**Step 2: Run test to verify it fails**
Run: `.venv/bin/pytest tests/concept/test_tool_fork_dispatch.py::test_tool_fork_dispatch_no_application_layer_imports -v`

**Step 3: Remove reverse import**
In `lca/nodes/concept/tool_fork/dispatch.py`:
```python
        tools_service = input.port_values.get("tools")
        if tools_service is None:
            from lca.infrastructure.capability.tools.tools import ToolsService

            tools_service = ToolsService()
```

**Step 4: Run test to verify it passes**
Run: `.venv/bin/pytest tests/concept/test_tool_fork_dispatch.py -v`

---

### Task 2: Implement `SearchProvider` Protocol and Registry

**Files:**
- Create: `lca/infrastructure/search/providers/protocol.py`
- Create: `lca/infrastructure/search/providers/registry.py`
- Modify: `lca/infrastructure/search/providers/__init__.py`
- Modify: `lca/infrastructure/search/providers/exa.py`
- Modify: `lca/infrastructure/search/providers/searxng.py`
- Modify: `lca/infrastructure/search/providers/tavily.py`
- Test: `tests/unit/infrastructure/search/test_search_providers.py`
- Does NOT own: `lca/nodes/`, `lca/session/`, `lca/contracts/`
- Invariants to test:
  - All providers implement `SearchProvider` protocol.
  - Providers self-register into `default_search_registry`.
  - Provider lookup by ID returns the correct adapter.

**Step 1: Define `SearchProvider` Protocol and Registry**
Create `lca/infrastructure/search/providers/protocol.py` with `SearchProvider` protocol.
Create `lca/infrastructure/search/providers/registry.py` with `SearchProviderRegistry`.

**Step 2: Wrap Exa, SearXNG, and Tavily as registered providers**
Update `exa.py`, `searxng.py`, and `tavily.py` with provider classes conforming to `SearchProvider`.

**Step 3: Run search provider unit tests**
Run: `.venv/bin/pytest tests/unit/infrastructure/search/test_search_providers.py -v`

---

### Task 3: Refactor `service.py` to use Registry (Remove `if-elif` ladder)

**Files:**
- Modify: `lca/infrastructure/search/service/service.py:14-80`
- Test: `tests/unit/infrastructure/search/test_search_providers.py`
- Does NOT own: `lca/nodes/`, `lca/session/`
- Invariants to test:
  - `any_search_provider_available()` checks registry without hardcoded provider conditionals.
  - `web_search()` dispatches through registry dynamically.
  - Fallback chaining and attempt marking remain intact.

**Step 1: Refactor `service.py`**
Replace hardcoded `if provider == PROVIDER_...` blocks in `any_search_provider_available` and `web_search` with registry lookups.

**Step 2: Run tests to verify compatibility**
Run: `.venv/bin/pytest tests/unit/infrastructure/search/ tests/scenario/search/ -v`

---

### Task 4: Dynamic Temporal Year Matching & Prompt Sanitization

**Files:**
- Modify: `lca/infrastructure/search/constants/constants.py`
- Modify: `lca/infrastructure/search/router/router.py`
- Test: `tests/scenario/search/test_search_skill_policy.py`
- Does NOT own: `lca/application/`, `lca/session/`
- Invariants to test:
  - `is_search_intent` matches query with current/future years dynamically without regex decade constants.
  - `search_routing_hint` uses dynamic current year rather than hardcoded "2026".
  - Prompt does not hardcode vendor-specific environment variable names.

**Step 1: Refactor temporal regex & year evaluation**
Replace static `\b(202[4-9]|203[0-9])\b` with dynamic validation in `router.py`.

**Step 2: Sanitize `search_routing_hint`**
Interpolate dynamic year into `search_routing_hint`.

**Step 3: Run tests to verify**
Run: `.venv/bin/pytest tests/scenario/search/ tests/scenario/web/ -v`

---

### Task 5: Clean MCP Lifecycle & Event Loop Teardown

**Files:**
- Modify: `lca/infrastructure/mcp/transports/stdio.py`
- Modify: `lca/infrastructure/mcp/tool_set.py`
- Test: `tests/unit/infrastructure/mcp/test_mcp_subsystem.py`
- Test: `tests/unit/infrastructure/mcp/test_agent_mcp_injection.py`
- Does NOT own: `lca/nodes/`, `lca/session/`
- Invariants to test:
  - `reset_ambient_mcp_manager()` closes transport gracefully.
  - Pytest runs without unraisable subprocess transport warnings.

**Step 1: Fix `close()` in `stdio.py` and `reset_ambient_mcp_manager()`**
Ensure stdout/stderr pipes are closed and subprocesses awaited synchronously or asynchronously.

**Step 2: Run MCP test suite**
Run: `.venv/bin/pytest tests/unit/infrastructure/mcp/ -v`
Ensure no `RuntimeError: Event loop is closed` warnings appear.

---

### Task 6: Full Regression & Pre-push Verification

**Files:**
- Does NOT own: Any other components
- Invariants to test:
  - All unit & scenario tests pass.
  - `ruff check lca/` passes.
  - Architecture contracts pass.

**Step 1: Run full verification commands**
Run:
- `.venv/bin/pytest tests/unit/infrastructure/search/ tests/unit/infrastructure/mcp/ tests/scenario/search/ tests/concept/test_tool_fork_dispatch.py -v`
- `ruff check lca/nodes/ lca/infrastructure/search/ lca/infrastructure/mcp/`
