# MCP Integration & Assistant Tool Strategy Pipeline Refactoring Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Refactor commit `7ded653eb` to eliminate hardcoded factory couplings, restore C5 grant enforcement for MCP tools via a unified identifier pipeline, and replace non-deterministic network-dependent tests with fast, offline unit tests.

**Architecture:** 
1. Table-driven factory registration in `lca-tools-provider` backed by explicit configuration SSOT in `bundles/base.yaml`.
2. Unified tool identifier extraction (`_tool_matching_names`) and a 3-stage filter pipeline (Deny $\rightarrow$ Grant $\rightarrow$ Allow) in `filter_tools_by_assistant`.
3. Deterministic in-memory Mock testing for MCP tools in the agent dialogue loop adhering to C8 (Determinism).

**Tech Stack:** Python 3.11, Pydantic, Pytest, LCA Plugin & Harness Seams.

---

### Task 1: Configuration SSOT & Table-driven Factory Registration

**Files:**
- Modify: `bundles/base.yaml:368-370`
- Modify: `lca/plugins/act/tools/provider.py:25-28, 81-87`
- Create: `tests/unit/plugins/act/tools/test_provider.py`
- Does NOT own: `lca/infrastructure/tools/assistant/filter.py`, `tests/unit/infrastructure/mcp/test_aws_mcp_dialogue.py` (AP-01)
- Invariants to test: OCP & SSOT: `setup()` strictly registers only what is specified in `config.factories`; no sneaky piggybacking of `mcp` inside `g2a`. (AP-02)

**Step 1: Write the failing test**

Create `tests/unit/plugins/act/tools/test_provider.py`:
```python
from unittest.mock import MagicMock
import pytest
from lca.plugins.act.tools.provider import Config, setup, _g2a_factory, _mcp_factory

@pytest.mark.asyncio
async def test_tools_provider_registers_only_configured_factories():
    # When factories only contains g2a
    ctx = MagicMock()
    tools_seam = MagicMock()
    ctx.require.return_value = tools_seam

    await setup(ctx, Config(factories=["g2a"]))
    assert tools_seam.register_factory.call_count == 1
    tools_seam.register_factory.assert_called_once_with("g2a", _g2a_factory)

@pytest.mark.asyncio
async def test_tools_provider_registers_both_when_configured():
    ctx = MagicMock()
    tools_seam = MagicMock()
    ctx.require.return_value = tools_seam

    await setup(ctx, Config(factories=["g2a", "mcp"]))
    assert tools_seam.register_factory.call_count == 2
    tools_seam.register_factory.assert_any_call("g2a", _g2a_factory)
    tools_seam.register_factory.assert_any_call("mcp", _mcp_factory)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/plugins/act/tools/test_provider.py -v`
Expected: FAIL because `setup()` currently registers `mcp` inside `if "g2a" in config.factories`.

**Step 3: Write minimal implementation**

In `lca/plugins/act/tools/provider.py`:
```python
class Config(BaseModel):
    model_config = {"extra": "forbid"}
    factories: list[str] = Field(default_factory=lambda: ["g2a", "mcp"])

_TOOL_FACTORIES = {
    "g2a": _g2a_factory,
    "mcp": _mcp_factory,
}

async def setup(ctx: PluginContext, config: Config) -> None:
    tools_seam = ctx.require("tools")
    for name in config.factories:
        factory = _TOOL_FACTORIES.get(name)
        if factory is not None:
            tools_seam.register_factory(name, factory)
```

In `bundles/base.yaml`:
```yaml
- id: lca-tools-provider
  name: lca_providers_tools
  $module: lca.plugins.act.tools.provider
  config:
    factories:
    - g2a
    - mcp
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/plugins/act/tools/test_provider.py -v`
Expected: PASS (2 passed).

**Step 5: Commit**

```bash
git add bundles/base.yaml lca/plugins/act/tools/provider.py tests/unit/plugins/act/tools/test_provider.py
git commit -m "refactor(tools-provider): decouple tool factories with table-driven registration and SSOT configuration"
```

---

### Task 2: Strategy Pipeline for Tool Filtering & C5 Grant Enforcement

**Files:**
- Modify: `lca/infrastructure/tools/assistant/filter.py:57-90`
- Modify: `tests/plugins/assistant/test_filter_tools.py`
- Does NOT own: `lca/plugins/act/tools/provider.py`, `lca/infrastructure/mcp/` (AP-01)
- Invariants to test: C5: MCP tools with `required_grant` must be evaluated against `grants.yaml`; Deny priority: any matching key in `deny` drops the tool immediately. (AP-02)

**Step 1: Write the failing tests**

In `tests/plugins/assistant/test_filter_tools.py`, add tests asserting C5 grant enforcement for MCP tools:
```python
    def test_mcp_tool_with_required_grant_denied_without_grant(self, home: Path) -> None:
        _write_tools(home, allow=["mcp"], deny=[])
        # grants.yaml is empty by default in this fixture
        mcp_tool = _tool("mcp__aws-mcp__aws_privileged", required_grant="aws.admin")
        result = filter_tools_by_assistant([mcp_tool], home)
        assert result == ()

    def test_mcp_tool_with_required_grant_allowed_with_grant(self, home: Path) -> None:
        _write_tools(home, allow=["mcp"], deny=[])
        _write_grants(home, grants=["aws.admin"])
        mcp_tool = _tool("mcp__aws-mcp__aws_privileged", required_grant="aws.admin")
        result = filter_tools_by_assistant([mcp_tool], home)
        assert [t.name for t in result] == ["mcp__aws-mcp__aws_privileged"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/plugins/assistant/test_filter_tools.py -k "test_mcp_tool_with_required_grant" -v`
Expected: FAIL because `filter.py` currently early-continues on `mcp__` before checking `required_grant`.

**Step 3: Implement clean identifier extractor and unified funnel pipeline**

In `lca/infrastructure/tools/assistant/filter.py`:
```python
def _tool_matching_names(tool: Tool) -> frozenset[str]:
    """Extract all valid matching identifier keys for a tool."""
    name = tool.name
    keys: set[str] = {name}
    if name.startswith("local_"):
        keys.add(name[6:])
    elif name.startswith("mcp__"):
        parts = name.split("__", 2)
        keys.add("mcp")
        if len(parts) > 1 and parts[1]:
            keys.add(parts[1])
        if len(parts) > 2 and parts[2]:
            keys.add(parts[2])
    return frozenset(keys)

def filter_tools_by_assistant(
    tools: Iterable[Tool],
    home_path: str | Path,
) -> _ToolSet:
    home = Path(home_path)
    policy = _load_tools_policy(home)
    if policy is None:
        return ()
    allow, deny = policy
    grants = _load_grants(home)

    kept: list[Tool] = []
    for tool in tools:
        keys = _tool_matching_names(tool)
        if bool(keys & deny):
            continue
        required_grant = _required_grant(tool)
        if required_grant and required_grant not in grants:
            continue
        if not allow or bool(keys & allow):
            kept.append(tool)
    return tuple(kept)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/plugins/assistant/test_filter_tools.py -v`
Expected: PASS (all 24 passed).

**Step 5: Commit**

```bash
git add lca/infrastructure/tools/assistant/filter.py tests/plugins/assistant/test_filter_tools.py
git commit -m "fix(assistant): enforce C5 grants on MCP tools and unify policy matching pipeline"
```

---

### Task 3: Deterministic Offline Unit Testing for AWS MCP Dialogue Loop

**Files:**
- Modify: `tests/unit/infrastructure/mcp/test_aws_mcp_dialogue.py`
- Does NOT own: Production code in `lca/`, live cloud resources, `~/.aws/` (AP-01)
- Invariants to test: C8: Determinism: No network access, no live process spawning, execution time < 2s, 100% reproducible. (AP-02)

**Step 1: Inspect current failures**

Run: `uv run pytest tests/unit/infrastructure/mcp/test_aws_mcp_dialogue.py -v`
Expected: 2 FAILED (networking/uvx/aws credentials error taking > 50 seconds).

**Step 2: Rewrite test with deterministic Stub MCP tool and isolated manager fixture**

In `tests/unit/infrastructure/mcp/test_aws_mcp_dialogue.py`:
- Use `monkeypatch` to stub `build_ambient_mcp_tools` and `build_ambient_mcp_tools_async` with a lightweight, in-memory `Tool` stub named `mcp__aws-mcp__aws___list_regions`.
- Mock execution returns real-shaped data `{"regions": ["ap-northeast-1", "us-east-1", "eu-west-1"]}`.
- Test 1 (`test_aws_mcp_tools_injected`): Verifies Agent discovers and injects the tool.
- Test 2 (`test_agent_dialogue_calls_aws_mcp_tool`): Verifies `ScriptedLLMAdapter` triggers the tool and receives output in dialogue loop.

**Step 3: Run test to verify it passes deterministically**

Run: `uv run pytest tests/unit/infrastructure/mcp/test_aws_mcp_dialogue.py -v`
Expected: PASS (2 passed in < 2 seconds).

**Step 4: Commit**

```bash
git add tests/unit/infrastructure/mcp/test_aws_mcp_dialogue.py
git commit -m "test(mcp): replace non-deterministic external AWS calls with isolated stub tests"
```

---

### Task 4: Full Regression & Gate Verification

**Files:**
- Modify: `docs/plans/task.md`
- Does NOT own: Out of scope files (AP-01)

**Step 1: Run comprehensive tests**

```bash
uv run pytest tests/unit/plugins/act/tools/test_provider.py tests/plugins/assistant/test_filter_tools.py tests/unit/infrastructure/mcp/test_aws_mcp_dialogue.py -v
```
Expected: All tests pass cleanly.

**Step 2: Run linter and formatting checks**

```bash
uv run ruff check lca/plugins/act/tools/provider.py lca/infrastructure/tools/assistant/filter.py tests/unit/plugins/act/tools/test_provider.py tests/plugins/assistant/test_filter_tools.py tests/unit/infrastructure/mcp/test_aws_mcp_dialogue.py
git diff --check
```
Expected: 0 errors, clean git diff.

**Step 3: Commit and update tracker**

```bash
git add docs/plans/task.md
git commit -m "docs(plans): complete MCP integration refactoring"
```
