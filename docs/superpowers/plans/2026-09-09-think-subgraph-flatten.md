# Think Subgraph Flatten Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the temporary `phase.think.subgraph_host` + `_shared.py` glue with five flat L2 phase plugins (`phase.think.{shortcut,route,reason,classify,gate}`) plus a thin `phase.think.orchestrator`, matching the shape of `agent_lab/graphs/configs/act.yaml`.

**Architecture:** Each step plugin reads its dependency directly from `PhaseContext.capabilities` (typed contract, C13). The `SubgraphPhaseRunner` owns the cross-node `ThinkSubgraphCarry` plumbing. The orchestrator plugin is just a `SubgraphPhaseRunner.run_terminal_subgraph` wrapper.

**Tech Stack:** Python 3.12, Pydantic v2, Cordis plugin system, `lca.harness.plugin_api` `@plugin` decorator, `lca.harness.graph.execute.subgraph_phase_runner`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-09-think-subgraph-flatten-design.md`

## Global Constraints

- All new plugins use `@plugin(...)` with `layer="L2"`, `kind=PluginKind.PRIMITIVE`, `effects="none"`, `state_mutation="forbidden"`.
- All new plugins provide exactly one capability key, named `phase.think.<step>`.
- No shim, no alias, no re-export of `_shared` symbols.
- Each step plugin file ≤ 60 lines.
- Each task ends with a passing `pytest` invocation and a conventional-commit message.
- No direct import of `lca.plugins.loop.phase.think.subgraph._shared` in any new code (verified by grep).
- Five new `phase_think_<step>.checked/served` evidence descriptors must be added to the EP whitelist alongside the plugin.

---

## Task 1: Land the design spec and move `ThinkSubgraphCarry` into contracts

**Files:**
- Create: `lca/contracts/models/core/execution/think_carry.py`
- Modify: `lca/contracts/models/core/execution/__init__.py` (re-export)

### Step 1.1: Create the carry contract

Create `lca/contracts/models/core/execution/think_carry.py`:

```python
"""Typed cross-node state for the think phase graph."""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.state.state import AgentState

CARRY_KEY = "think.subgraph.carry"


@dataclass(slots=True)
class ThinkSubgraphCarry:
    """Working state passed between think subgraph nodes.

    Owned by ``SubgraphPhaseRunner._drive_linear_subgraph``. Step plugins
    must not import or mutate this type.
    """

    state: AgentState
    response: LLMResponse | None = None
    decision: Decision | None = None


__all__ = ["CARRY_KEY", "ThinkSubgraphCarry"]
```

### Step 1.2: Re-export from the execution package

Edit `lca/contracts/models/core/execution/__init__.py`. Find the `__all__` list and the import block; add:

```python
from lca.contracts.models.core.execution.think_carry import CARRY_KEY, ThinkSubgraphCarry
```

And append `"CARRY_KEY", "ThinkSubgraphCarry"` to `__all__`.

### Step 1.3: Run a sanity import

Run: `uv run python -c "from lca.contracts.models.core.execution import ThinkSubgraphCarry, CARRY_KEY; print(ThinkSubgraphCarry, CARRY_KEY)"`
Expected: prints the class and the key string with exit code 0.

### Step 1.4: Commit

```bash
git add lca/contracts/models/core/execution/think_carry.py lca/contracts/models/core/execution/__init__.py
git commit -m "feat(contracts): move ThinkSubgraphCarry into typed contract layer"
```

---

## Task 2: Implement the five flat L2 phase plugins with unit tests

Each sub-task introduces one plugin and one test file. The order matters only because of TDD cadence — any order is acceptable as long as all five land before Task 3.

### Sub-task 2.1: `phase.think.shortcut`

**Files:**
- Create: `lca/plugins/think/shortcut/plugin.py`
- Create: `lca/plugins/think/shortcut/__init__.py` (empty)
- Create: `tests/think/__init__.py` (empty)
- Create: `tests/think/test_shortcut_phase_plugin.py`

**Interfaces:**
- Consumes: `PhaseContext.capabilities["phase.think.shortcut"]` is a `SupportsShortcut`.
- Produces: capability key `phase.think.shortcut`; `PhaseResult(result_kind="decision", payload=Decision)` on hit, `PhaseResult(result_kind="think_stage", payload=ThinkSubgraphCarry)` on miss.

#### Step 2.1.1: Write the failing test

Create `tests/think/test_shortcut_phase_plugin.py`:

```python
"""Tests for phase.think.shortcut plugin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.core.execution.think_carry import ThinkSubgraphCarry
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseContext,
    PhaseInput,
)
from lca.plugins.think.shortcut.plugin import ThinkShortcutExecutor


@dataclass
class _NoopShortcut:
    async def try_shortcut(self, state: AgentState):  # type: ignore[no-untyped-def]
        return None


@dataclass
class _HitShortcut:
    decision_id = "dec_hit"

    async def try_shortcut(self, state: AgentState):  # type: ignore[no-untyped-def]
        return _FakeDecision(self.decision_id)


@dataclass
class _FakeDecision:
    decision_id: str


def _ctx(caps: dict[str, Any]) -> PhaseContext:
    return PhaseContext(  # type: ignore[call-arg]
        plan_ref="p",
        node_ref="think.shortcut",
        state=AgentState(trace_id="t", task="x"),
        journal=None,  # type: ignore[arg-type]
        budget=None,  # type: ignore[arg-type]
        artifacts={},
        capabilities=caps,  # type: ignore[arg-type]
        decision=None,
        observation=None,
        reflection=None,
        checkpoint_reason=None,
    )


@pytest.mark.asyncio
async def test_shortcut_hit_returns_decision_result() -> None:
    executor = ThinkShortcutExecutor()
    result = await executor.execute(
        _ctx({"phase.think.shortcut": _HitShortcut()}),
        PhaseInput(artifact=None),
    )
    assert result.result_kind == "decision"


@pytest.mark.asyncio
async def test_shortcut_miss_returns_stage_result() -> None:
    executor = ThinkShortcutExecutor()
    result = await executor.execute(
        _ctx({"phase.think.shortcut": _NoopShortcut()}),
        PhaseInput(artifact=None),
    )
    assert result.result_kind == "think_stage"
    assert isinstance(result.payload, ThinkSubgraphCarry)


@pytest.mark.asyncio
async def test_shortcut_missing_capability_returns_stage() -> None:
    executor = ThinkShortcutExecutor()
    result = await executor.execute(_ctx({}), PhaseInput(artifact=None))
    assert result.result_kind == "think_stage"
```

Note: adjust imports to match the project's `PhaseContext` constructor signature exactly. The plan implementer must `read_file` `lca/contracts/protocols/declarative/declarative_1/declarative_execution.py` first and align the `_ctx` factory.

#### Step 2.1.2: Run the test to verify it fails

Run: `uv run pytest tests/think/test_shortcut_phase_plugin.py -q`
Expected: import or attribute error (plugin module not yet created).

#### Step 2.1.3: Implement the plugin

Create `lca/plugins/think/shortcut/__init__.py` (empty).

Create `lca/plugins/think/shortcut/plugin.py`:

```python
"""phase.think.shortcut — try a deterministic shortcut before reason."""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.execution.think_carry import ThinkSubgraphCarry
from lca.contracts.protocols import SupportsShortcut
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.loop.phase._shared.common import StandardPhaseConfig

STAGE_KIND = "think_stage"


def _carry(context: PhaseContext) -> ThinkSubgraphCarry:
    existing = context.artifacts.get("think.subgraph.carry")
    if isinstance(existing, ThinkSubgraphCarry):
        return existing
    return ThinkSubgraphCarry(state=context.state)


@dataclass(frozen=True, slots=True)
class ThinkShortcutExecutor:
    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        cap = context.capabilities.get("phase.think.shortcut")
        if cap is None:
            return PhaseResult(result_kind=STAGE_KIND, payload=_carry(context))
        assert isinstance(cap, SupportsShortcut), (
            "phase.think.shortcut must implement SupportsShortcut"
        )
        decision = await cap.try_shortcut(context.state)
        if decision is None:
            return PhaseResult(result_kind=STAGE_KIND, payload=_carry(context))
        return PhaseResult(result_kind="decision", payload=decision)


@plugin(
    id="phase.think.shortcut",
    Config=StandardPhaseConfig,
    provides=("phase.think.shortcut",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/think/test_shortcut_phase_plugin.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_think_shortcut.checked",
                "phase_think_shortcut.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    del config
    ctx.provide("phase.think.shortcut", ThinkShortcutExecutor())


def create_executor() -> ThinkShortcutExecutor:
    return ThinkShortcutExecutor()


__all__ = ["ThinkShortcutExecutor", "create_executor", "setup"]
```

The implementer must verify `CARRY_KEY` is imported from the contract module (not redefined). Replace `"think.subgraph.carry"` in `_carry` with `CARRY_KEY` from the contracts module:

```python
from lca.contracts.models.core.execution.think_carry import CARRY_KEY, ThinkSubgraphCarry
...
existing = context.artifacts.get(CARRY_KEY)
```

#### Step 2.1.4: Run the test to verify it passes

Run: `uv run pytest tests/think/test_shortcut_phase_plugin.py -q`
Expected: 3 passed.

#### Step 2.1.5: Add the new EP descriptors to the whitelist

Find the EP whitelist (search for `phase_think_subgraph_shortcut` to locate the file, then replace those descriptors with the new `phase_think_shortcut.checked/served`). Same pattern will apply to each subsequent step plugin in Tasks 2.2–2.5.

Run: `uv run pytest tests/think/test_shortcut_phase_plugin.py -q` again to confirm nothing else broke.

#### Step 2.1.6: Commit

```bash
git add lca/plugins/think/shortcut/ tests/think/test_shortcut_phase_plugin.py \
        lca/contracts/protocols/atoms/atoms.py  # or whichever whitelist file
git commit -m "feat(think): introduce phase.think.shortcut flat plugin"
```

### Sub-task 2.2: `phase.think.route`

**Files:**
- Create: `lca/plugins/think/route/plugin.py`
- Create: `lca/plugins/think/route/__init__.py`
- Create: `tests/think/test_route_phase_plugin.py`

**Interfaces:**
- Consumes: `phase.think.route` (a `SkillRouter`) and `phase.think.reducer` (a `Reducer`).
- Produces: capability `phase.think.route`; always `PhaseResult(result_kind="think_stage", payload=ThinkSubgraphCarry)`.

#### Step 2.2.1: Write the failing test

Create `tests/think/test_route_phase_plugin.py`:

```python
"""Tests for phase.think.route plugin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.core.execution.think_carry import ThinkSubgraphCarry
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseContext,
    PhaseInput,
)
from lca.plugins.think.route.plugin import ThinkRouteExecutor


@dataclass
class _Router:
    template = "react_prompt"

    async def route(self, state: AgentState) -> str:  # type: ignore[no-untyped-def]
        return self.template


@dataclass
class _Reducer:
    def apply_skill_route(self, state: AgentState, template: str) -> AgentState:  # type: ignore[no-untyped-def]
        return state


def _ctx(caps: dict[str, Any]) -> PhaseContext:
    return PhaseContext(  # type: ignore[call-arg]
        plan_ref="p",
        node_ref="think.route",
        state=AgentState(trace_id="t", task="x"),
        journal=None,  # type: ignore[arg-type]
        budget=None,  # type: ignore[arg-type]
        artifacts={},
        capabilities=caps,  # type: ignore[arg-type]
        decision=None,
        observation=None,
        reflection=None,
        checkpoint_reason=None,
    )


@pytest.mark.asyncio
async def test_route_returns_stage_with_reducer_state() -> None:
    executor = ThinkRouteExecutor()
    result = await executor.execute(
        _ctx({"phase.think.route": _Router(), "phase.think.reducer": _Reducer()}),
        PhaseInput(artifact=None),
    )
    assert result.result_kind == "think_stage"
    assert isinstance(result.payload, ThinkSubgraphCarry)


@pytest.mark.asyncio
async def test_route_without_router_passes_through() -> None:
    executor = ThinkRouteExecutor()
    result = await executor.execute(
        _ctx({"phase.think.reducer": _Reducer()}),
        PhaseInput(artifact=None),
    )
    assert result.result_kind == "think_stage"


@pytest.mark.asyncio
async def test_route_without_reducer_raises_when_router_present() -> None:
    executor = ThinkRouteExecutor()
    with pytest.raises(RuntimeError):
        await executor.execute(
            _ctx({"phase.think.route": _Router()}),
            PhaseInput(artifact=None),
        )
```

#### Step 2.2.2: Run the test, verify it fails

Run: `uv run pytest tests/think/test_route_phase_plugin.py -q`
Expected: import failure (plugin not created).

#### Step 2.2.3: Implement the plugin

Create `lca/plugins/think/route/__init__.py` (empty).

Create `lca/plugins/think/route/plugin.py`:

```python
"""phase.think.route — SkillRouter picks active template; Reducer folds state."""

from __future__ import annotations

from dataclasses import dataclass, replace

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.execution.think_carry import CARRY_KEY, ThinkSubgraphCarry
from lca.contracts.protocols import SkillRouter
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.state.reducer import Reducer
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.loop.phase._shared.common import StandardPhaseConfig


def _carry(context: PhaseContext) -> ThinkSubgraphCarry:
    existing = context.artifacts.get(CARRY_KEY)
    if isinstance(existing, ThinkSubgraphCarry):
        return existing
    return ThinkSubgraphCarry(state=context.state)


@dataclass(frozen=True, slots=True)
class ThinkRouteExecutor:
    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        carry = _carry(context)
        router = context.capabilities.get("phase.think.route")
        if router is None:
            return PhaseResult(result_kind="think_stage", payload=carry)
        assert isinstance(router, SkillRouter)
        reducer = context.capabilities.get("phase.think.reducer")
        if reducer is None:
            raise RuntimeError(
                "phase.think.route requires phase.think.reducer when a SkillRouter is configured"
            )
        assert isinstance(reducer, Reducer)
        template = await router.route(carry.state)
        routed = reducer.apply_skill_route(carry.state, template)
        return PhaseResult(
            result_kind="think_stage",
            payload=replace(carry, state=routed),
        )


@plugin(
    id="phase.think.route",
    Config=StandardPhaseConfig,
    provides=("phase.think.route",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/think/test_route_phase_plugin.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_think_route.checked",
                "phase_think_route.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    del config
    ctx.provide("phase.think.route", ThinkRouteExecutor())


def create_executor() -> ThinkRouteExecutor:
    return ThinkRouteExecutor()


__all__ = ["ThinkRouteExecutor", "create_executor", "setup"]
```

#### Step 2.2.4: Run the test, verify it passes

Run: `uv run pytest tests/think/test_route_phase_plugin.py -q`
Expected: 3 passed.

#### Step 2.2.5: Add the new EP descriptors to the whitelist

Replace `phase_think_subgraph_route` entries with `phase_think_route.checked/served`.

#### Step 2.2.6: Commit

```bash
git add lca/plugins/think/route/ tests/think/test_route_phase_plugin.py \
        lca/contracts/.../atoms.py
git commit -m "feat(think): introduce phase.think.route flat plugin"
```

### Sub-task 2.3: `phase.think.reason`

**Files:**
- Create: `lca/plugins/think/reason/plugin.py`
- Create: `lca/plugins/think/reason/__init__.py`
- Create: `tests/think/test_reason_phase_plugin.py`

**Interfaces:**
- Consumes: `phase.think.reason` (a `Reasoner`).
- Produces: `phase.think.reason`; `PhaseResult(result_kind="think_stage", payload=ThinkSubgraphCarry)` with `response` populated.

#### Step 2.3.1: Write the failing test

Create `tests/think/test_reason_phase_plugin.py`:

```python
"""Tests for phase.think.reason plugin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.think_carry import ThinkSubgraphCarry
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseContext,
    PhaseInput,
)
from lca.plugins.think.reason.plugin import ThinkReasonExecutor


@dataclass
class _Reasoner:
    response = LLMResponse(text="hi", tool_calls=())

    async def generate_thoughts(self, state: AgentState) -> LLMResponse:  # type: ignore[no-untyped-def]
        return self.response


def _ctx(caps: dict[str, Any]) -> PhaseContext:
    return PhaseContext(  # type: ignore[call-arg]
        plan_ref="p",
        node_ref="think.reason",
        state=AgentState(trace_id="t", task="x"),
        journal=None,  # type: ignore[arg-type]
        budget=None,  # type: ignore[arg-type]
        artifacts={},
        capabilities=caps,  # type: ignore[arg-type]
        decision=None,
        observation=None,
        reflection=None,
        checkpoint_reason=None,
    )


@pytest.mark.asyncio
async def test_reason_attaches_response_to_carry() -> None:
    executor = ThinkReasonExecutor()
    result = await executor.execute(
        _ctx({"phase.think.reason": _Reasoner()}),
        PhaseInput(artifact=None),
    )
    assert result.result_kind == "think_stage"
    carry = result.payload
    assert isinstance(carry, ThinkSubgraphCarry)
    assert carry.response is _Reasoner.response


@pytest.mark.asyncio
async def test_reason_missing_capability_falls_back() -> None:
    executor = ThinkReasonExecutor()
    result = await executor.execute(_ctx({}), PhaseInput(artifact=None))
    assert result.result_kind == "think_stage"
    assert result.payload.response is None
```

#### Step 2.3.2: Run the test, verify it fails

Run: `uv run pytest tests/think/test_reason_phase_plugin.py -q`

#### Step 2.3.3: Implement the plugin

Create `lca/plugins/think/reason/__init__.py` (empty).

Create `lca/plugins/think/reason/plugin.py`:

```python
"""phase.think.reason — call the LLM via Reasoner, emitting spine facts."""

from __future__ import annotations

from dataclasses import dataclass, replace

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.execution.think_carry import CARRY_KEY, ThinkSubgraphCarry
from lca.contracts.protocols import Reasoner
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.loop.emit.cognitive.reasoner import run_reasoner_with_spine_facts
from lca.plugins.loop.phase._shared.common import StandardPhaseConfig


def _carry(context: PhaseContext) -> ThinkSubgraphCarry:
    existing = context.artifacts.get(CARRY_KEY)
    if isinstance(existing, ThinkSubgraphCarry):
        return existing
    return ThinkSubgraphCarry(state=context.state)


@dataclass(frozen=True, slots=True)
class ThinkReasonExecutor:
    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        carry = _carry(context)
        reasoner = context.capabilities.get("phase.think.reason")
        if reasoner is None:
            return PhaseResult(result_kind="think_stage", payload=carry)
        assert isinstance(reasoner, Reasoner)
        response = await run_reasoner_with_spine_facts(reasoner, carry.state)
        return PhaseResult(
            result_kind="think_stage",
            payload=replace(carry, response=response),
        )


@plugin(
    id="phase.think.reason",
    Config=StandardPhaseConfig,
    provides=("phase.think.reason",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/think/test_reason_phase_plugin.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_think_reason.checked",
                "phase_think_reason.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    del config
    ctx.provide("phase.think.reason", ThinkReasonExecutor())


def create_executor() -> ThinkReasonExecutor:
    return ThinkReasonExecutor()


__all__ = ["ThinkReasonExecutor", "create_executor", "setup"]
```

#### Step 2.3.4: Run the test, verify it passes

Run: `uv run pytest tests/think/test_reason_phase_plugin.py -q`
Expected: 2 passed.

#### Step 2.3.5: Add the new EP descriptors to the whitelist

Replace `phase_think_subgraph_reason` with `phase_think_reason.checked/served`.

#### Step 2.3.6: Commit

```bash
git add lca/plugins/think/reason/ tests/think/test_reason_phase_plugin.py \
        lca/contracts/.../atoms.py
git commit -m "feat(think): introduce phase.think.reason flat plugin"
```

### Sub-task 2.4: `phase.think.classify`

**Files:**
- Create: `lca/plugins/think/classify/plugin.py`
- Create: `lca/plugins/think/classify/__init__.py`
- Create: `tests/think/test_classify_phase_plugin.py`

**Interfaces:**
- Consumes: `phase.think.classify` (a `DecisionClassifier`).
- Produces: `phase.think.classify`; `PhaseResult(result_kind="think_stage", payload=ThinkSubgraphCarry)` with `decision` populated.

#### Step 2.4.1: Write the failing test

Create `tests/think/test_classify_phase_plugin.py`:

```python
"""Tests for phase.think.classify plugin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.execution.think_carry import ThinkSubgraphCarry
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseContext,
    PhaseInput,
)
from lca.plugins.think.classify.plugin import ThinkClassifyExecutor


@dataclass
class _Classifier:
    out = Decision(decision_id="dec_x")  # type: ignore[call-arg]

    def classify(self, response: LLMResponse) -> Decision:  # type: ignore[no-untyped-def]
        return self.out


def _ctx(caps: dict[str, Any], response: LLMResponse | None = None) -> PhaseContext:
    carry = ThinkSubgraphCarry(
        state=AgentState(trace_id="t", task="x"),
        response=response,
    )
    return PhaseContext(  # type: ignore[call-arg]
        plan_ref="p",
        node_ref="think.classify",
        state=carry.state,
        journal=None,  # type: ignore[arg-type]
        budget=None,  # type: ignore[arg-type]
        artifacts={CARRY_KEY: carry} if response is not None else {},
        capabilities=caps,  # type: ignore[arg-type]
        decision=None,
        observation=None,
        reflection=None,
        checkpoint_reason=None,
    )


@pytest.mark.asyncio
async def test_classify_attaches_decision() -> None:
    from lca.contracts.models.core.execution.think_carry import CARRY_KEY

    executor = ThinkClassifyExecutor()
    response = LLMResponse(text="hi", tool_calls=())
    result = await executor.execute(
        _ctx({"phase.think.classify": _Classifier()}, response=response),
        PhaseInput(artifact=None),
    )
    assert result.result_kind == "think_stage"
    assert result.payload.decision is _Classifier.out


@pytest.mark.asyncio
async def test_classify_without_response_falls_back() -> None:
    executor = ThinkClassifyExecutor()
    result = await executor.execute(
        _ctx({"phase.think.classify": _Classifier()}, response=None),
        PhaseInput(artifact=None),
    )
    assert result.result_kind == "think_stage"
    assert result.payload.decision is None
```

#### Step 2.4.2: Run the test, verify it fails

Run: `uv run pytest tests/think/test_classify_phase_plugin.py -q`

#### Step 2.4.3: Implement the plugin

Create `lca/plugins/think/classify/__init__.py` (empty).

Create `lca/plugins/think/classify/plugin.py`:

```python
"""phase.think.classify — convert LLMResponse to Decision via DecisionClassifier."""

from __future__ import annotations

from dataclasses import dataclass, replace

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.execution.think_carry import CARRY_KEY, ThinkSubgraphCarry
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.gate.decision_classifier import DecisionClassifier
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.loop.phase._shared.common import StandardPhaseConfig


def _carry(context: PhaseContext) -> ThinkSubgraphCarry:
    existing = context.artifacts.get(CARRY_KEY)
    if isinstance(existing, ThinkSubgraphCarry):
        return existing
    return ThinkSubgraphCarry(state=context.state)


@dataclass(frozen=True, slots=True)
class ThinkClassifyExecutor:
    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        carry = _carry(context)
        if carry.response is None:
            return PhaseResult(result_kind="think_stage", payload=carry)
        classifier = context.capabilities.get("phase.think.classify")
        if classifier is None:
            return PhaseResult(result_kind="think_stage", payload=carry)
        assert isinstance(classifier, DecisionClassifier)
        decision = classifier.classify(carry.response)
        return PhaseResult(
            result_kind="think_stage",
            payload=replace(carry, decision=decision),
        )


@plugin(
    id="phase.think.classify",
    Config=StandardPhaseConfig,
    provides=("phase.think.classify",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/think/test_classify_phase_plugin.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_think_classify.checked",
                "phase_think_classify.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    del config
    ctx.provide("phase.think.classify", ThinkClassifyExecutor())


def create_executor() -> ThinkClassifyExecutor:
    return ThinkClassifyExecutor()


__all__ = ["ThinkClassifyExecutor", "create_executor", "setup"]
```

#### Step 2.4.4: Run the test, verify it passes

Run: `uv run pytest tests/think/test_classify_phase_plugin.py -q`
Expected: 2 passed.

#### Step 2.4.5: Add the new EP descriptors to the whitelist

Replace `phase_think_subgraph_classify` with `phase_think_classify.checked/served`.

#### Step 2.4.6: Commit

```bash
git add lca/plugins/think/classify/ tests/think/test_classify_phase_plugin.py \
        lca/contracts/.../atoms.py
git commit -m "feat(think): introduce phase.think.classify flat plugin"
```

### Sub-task 2.5: `phase.think.gate`

**Files:**
- Create: `lca/plugins/think/gate/plugin.py`
- Create: `lca/plugins/think/gate/__init__.py`
- Create: `tests/think/test_gate_phase_plugin.py`

**Interfaces:**
- Consumes: `phase.think.gate` (a `DecisionGate`); `phase.think.agent_gates` (a `DecisionGate` or `None`).
- Produces: `phase.think.gate`; `PhaseResult(result_kind="decision", payload=Decision)` after enforce.

#### Step 2.5.1: Write the failing test

Create `tests/think/test_gate_phase_plugin.py`:

```python
"""Tests for phase.think.gate plugin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.execution.think_carry import CARRY_KEY, ThinkSubgraphCarry
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseContext,
    PhaseInput,
)
from lca.plugins.think.gate.plugin import ThinkGateExecutor


@dataclass
class _Gate:
    out = Decision(decision_id="dec_g")  # type: ignore[call-arg]

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:  # type: ignore[no-untyped-def]
        return self.out


def _ctx(caps: dict[str, Any], decision: Decision | None = None) -> PhaseContext:
    carry = ThinkSubgraphCarry(
        state=AgentState(trace_id="t", task="x"),
        decision=decision,
    )
    artifacts = {}
    if decision is not None:
        artifacts[CARRY_KEY] = carry
    return PhaseContext(  # type: ignore[call-arg]
        plan_ref="p",
        node_ref="think.gate",
        state=carry.state,
        journal=None,  # type: ignore[arg-type]
        budget=None,  # type: ignore[arg-type]
        artifacts=artifacts,
        capabilities=caps,  # type: ignore[arg-type]
        decision=None,
        observation=None,
        reflection=None,
        checkpoint_reason=None,
    )


@pytest.mark.asyncio
async def test_gate_returns_decision_after_enforce() -> None:
    executor = ThinkGateExecutor()
    decision_in = Decision(decision_id="dec_in")  # type: ignore[call-arg]
    result = await executor.execute(
        _ctx({"phase.think.gate": _Gate()}, decision=decision_in),
        PhaseInput(artifact=None),
    )
    assert result.result_kind == "decision"
    assert result.payload is _Gate.out


@pytest.mark.asyncio
async def test_gate_without_decision_falls_back() -> None:
    executor = ThinkGateExecutor()
    result = await executor.execute(
        _ctx({"phase.think.gate": _Gate()}),
        PhaseInput(artifact=None),
    )
    assert result.result_kind == "decision"
```

#### Step 2.5.2: Run the test, verify it fails

Run: `uv run pytest tests/think/test_gate_phase_plugin.py -q`

#### Step 2.5.3: Implement the plugin

Create `lca/plugins/think/gate/__init__.py` (empty).

Create `lca/plugins/think/gate/plugin.py`:

```python
"""phase.think.gate — enforce Decision via DecisionGate and agent gates."""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.execution.think_carry import CARRY_KEY, ThinkSubgraphCarry
from lca.contracts.protocols import DecisionGate
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.loop.phase._shared.common import StandardPhaseConfig


def _carry(context: PhaseContext) -> ThinkSubgraphCarry:
    existing = context.artifacts.get(CARRY_KEY)
    if isinstance(existing, ThinkSubgraphCarry):
        return existing
    return ThinkSubgraphCarry(state=context.state)


@dataclass(frozen=True, slots=True)
class ThinkGateExecutor:
    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        carry = _carry(context)
        if carry.decision is None:
            return PhaseResult(result_kind="decision", payload=input.artifact)
        gate = context.capabilities.get("phase.think.gate")
        decision = carry.decision
        if isinstance(gate, DecisionGate):
            decision = await gate.enforce(carry.state, decision)
        agent_gates = context.capabilities.get("phase.think.agent_gates")
        if isinstance(agent_gates, DecisionGate):
            decision = await agent_gates.enforce(carry.state, decision)
        return PhaseResult(result_kind="decision", payload=decision)


@plugin(
    id="phase.think.gate",
    Config=StandardPhaseConfig,
    provides=("phase.think.gate",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/think/test_gate_phase_plugin.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_think_gate.checked",
                "phase_think_gate.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    del config
    ctx.provide("phase.think.gate", ThinkGateExecutor())


def create_executor() -> ThinkGateExecutor:
    return ThinkGateExecutor()


__all__ = ["ThinkGateExecutor", "create_executor", "setup"]
```

#### Step 2.5.4: Run the test, verify it passes

Run: `uv run pytest tests/think/test_gate_phase_plugin.py -q`
Expected: 2 passed.

#### Step 2.5.5: Add the new EP descriptors to the whitelist

Replace `phase_think_subgraph_gate` with `phase_think_gate.checked/served`.

#### Step 2.5.6: Commit

```bash
git add lca/plugins/think/gate/ tests/think/test_gate_phase_plugin.py \
        lca/contracts/.../atoms.py
git commit -m "feat(think): introduce phase.think.gate flat plugin"
```

---

## Task 3: Move carry into the runner, add orchestrator + bundles + profile switch

**Files:**
- Modify: `lca/harness/graph/execute/subgraph_phase_runner.py`
- Create: `lca/plugins/loop/phase/think/orchestrator/plugin.py`
- Create: `lca/plugins/loop/phase/think/orchestrator/__init__.py`
- Create: `bundles/think-orchestrator.yaml`
- Create: `bundles/think-orchestrator-graph.yaml`
- Create: `profiles/fixtures/think-orchestrator-compile.yaml`
- Modify: `profiles/web-standard.yaml`
- Modify: `profiles/think-subgraph-dev.yaml`
- Create: `tests/think/test_orchestrator_graph.py`

### Step 3.1: Move carry handling into the runner

Read `lca/harness/graph/execute/subgraph_phase_runner.py`. Replace the
imports and the `_drive_linear_subgraph` body so the runner owns the carry:

```python
# Replace the existing import block at the top:
from lca.contracts.models.core.execution.think_carry import CARRY_KEY, ThinkSubgraphCarry
# Remove any import of the old _shared module (e.g.
#   from lca.plugins.loop.phase.think.subgraph._shared import CARRY_KEY, ThinkSubgraphCarry)
```

Then replace the inner loop body in `_drive_linear_subgraph`:

```python
# Replace the body inside `_drive_linear_subgraph` that currently does:
#   carry = ThinkSubgraphCarry(state=context.state)
#   artifacts[CARRY_KEY] = carry
# with:
existing = artifacts.get(CARRY_KEY)
carry = existing if isinstance(existing, ThinkSubgraphCarry) else ThinkSubgraphCarry(state=context.state)
artifacts[CARRY_KEY] = carry

# And replace the block that currently does:
#   if isinstance(result.payload, ThinkSubgraphCarry):
#       carry = result.payload
#       artifacts[CARRY_KEY] = carry
# with:
if isinstance(result.payload, ThinkSubgraphCarry):
    carry = result.payload
    artifacts[CARRY_KEY] = carry
```

(The intent is that the runner owns the carry lifecycle; the existing code
already does this; the change is to update the import path from
`lca.plugins.loop.phase.think.subgraph._shared` to
`lca.contracts.models.core.execution.think_carry`.)

Run: `uv run python -c "from lca.harness.graph.execute.subgraph_phase_runner import SubgraphPhaseRunner"`
Expected: import succeeds.

### Step 3.2: Create the orchestrator plugin

Create `lca/plugins/loop/phase/think/orchestrator/__init__.py` (empty).

Create `lca/plugins/loop/phase/think/orchestrator/plugin.py`:

```python
"""phase.think.orchestrator — drives the think 5-step phase graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.graph.execute.subgraph_phase_runner import (
    SUBGRAPH_PHASE_RUNNER_CAPABILITY,
    SubgraphPhaseRunner,
    default_subgraph_phase_runner,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class SubgraphOrchestratorConfig(BaseModel):
    """Configuration for the think orchestrator."""

    model_config = {"extra": "forbid"}

    plan_ref: str = Field(default="bundles/think-orchestrator.yaml")
    entry_node: str = Field(default="think.shortcut")


def _runner_for(context: PhaseContext) -> SubgraphPhaseRunner:
    runner = context.capabilities.get(SUBGRAPH_PHASE_RUNNER_CAPABILITY)
    if isinstance(runner, SubgraphPhaseRunner):
        return runner
    return default_subgraph_phase_runner()


@dataclass(frozen=True, slots=True)
class ThinkOrchestratorExecutor:
    plan_ref: str
    entry_node: str

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        runner = _runner_for(context)
        return await runner.run_terminal_subgraph(
            plan_ref=self.plan_ref,
            entry_node=self.entry_node,
            context=context,
            input=input,
        )


@plugin(
    id="phase.think.orchestrator",
    Config=SubgraphOrchestratorConfig,
    provides=("phase.think.orchestrator",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/think/test_orchestrator_graph.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_think_orchestrator.checked",
                "phase_think_orchestrator.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", SUBGRAPH_PHASE_RUNNER_CAPABILITY),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: SubgraphOrchestratorConfig) -> None:
    ctx.provide(
        "phase.think.orchestrator",
        ThinkOrchestratorExecutor(
            plan_ref=config.plan_ref,
            entry_node=config.entry_node,
        ),
    )


def create_executor(
    *,
    plan_ref: str = "bundles/think-orchestrator.yaml",
    entry_node: str = "think.shortcut",
) -> ThinkOrchestratorExecutor:
    return ThinkOrchestratorExecutor(plan_ref=plan_ref, entry_node=entry_node)


__all__ = [
    "SubgraphOrchestratorConfig",
    "ThinkOrchestratorExecutor",
    "create_executor",
    "setup",
]
```

(The implementer must verify imports against the existing
`phase.think.subgraph_host/plugin.py` and replace its symbol names.)

### Step 3.3: Create the new bundles

Create `bundles/think-orchestrator.yaml`:

```yaml
# Think orchestrator — entry plan for the 5-step think phase graph.
# Loaded by phase.think.orchestrator via SubgraphPhaseRunner.
entries: []
```

Create `bundles/think-orchestrator-graph.yaml`:

```yaml
# Think 5-step phase graph topology + edges.
# Loaded via profiles/fixtures/think-orchestrator-compile.yaml.
entries:
  - id: phase.topology.standard
    $name: phase_topology_think_orchestrator
    $module: lca.plugins.loop.graph.topology.standard.plugin
    config:
      nodes:
        - id: think.shortcut
          phase: think
          binding: phase.think.shortcut
          max_visits: 4
          entry: true
        - id: think.route
          phase: think
          binding: phase.think.route
          max_visits: 4
        - id: think.reason
          phase: think
          binding: phase.think.reason
          max_visits: 4
        - id: think.classify
          phase: think
          binding: phase.think.classify
          max_visits: 4
        - id: think.gate
          phase: think
          binding: phase.think.gate
          max_visits: 4

  - id: phase.edge.standard
    $name: phase_edge_think_orchestrator
    $module: lca.plugins.loop.graph.edges.standard.plugin
    config:
      edges:
        - source: think.shortcut
          target: think.route
          when: result.result_kind != "decision"
        - source: think.route
          target: think.reason
          when: true
        - source: think.reason
          target: think.classify
          when: true
        - source: think.classify
          target: think.gate
          when: true
```

Create `profiles/fixtures/think-orchestrator-compile.yaml`:

```yaml
# Compile fixture for ``bundles/think-orchestrator.yaml``.
# Mirrors profiles/fixtures/think-subgraph-compile.yaml.
bundles:
  - bundles/think-orchestrator-graph.yaml
```

### Step 3.4: Switch profile bindings

Edit `profiles/web-standard.yaml`. Find the `think.main` binding
(`phase.think.subgraph_host`) and replace it with:

```yaml
        - id: think.main
          phase: think
          binding: phase.think.orchestrator
          max_visits: 8
```

Also update the comment block at the top of the profile to reflect the
new binding (`subgraph_host` → `orchestrator`).

Edit `profiles/think-subgraph-dev.yaml` with the same swap.

### Step 3.5: Write the end-to-end orchestrator test

Create `tests/think/test_orchestrator_graph.py`:

```python
"""End-to-end: phase.think.orchestrator drives the 5-step think graph."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseInput,
)
from lca.harness.graph.execute.subgraph_phase_runner import default_subgraph_phase_runner
from lca.harness.plugin_api import build_default_context  # if available
from lca.plugins.loop.phase.think.orchestrator.plugin import ThinkOrchestratorExecutor


@pytest.mark.asyncio
async def test_orchestrator_resolves_plan() -> None:
    resolver = default_subgraph_phase_runner().resolver
    plan = resolver.resolve("bundles/think-orchestrator.yaml")
    assert plan is not None
    graph = plan.phase_graph
    assert graph is not None
    node_ids = [n.id for n in graph.nodes]
    assert node_ids == ["think.shortcut", "think.route", "think.reason", "think.classify", "think.gate"]
    assert graph.entry_node == "think.shortcut"


@pytest.mark.asyncio
async def test_orchestrator_compile_fixture_profile(tmp_path: Path) -> None:
    # Smoke test that the compile-fixture profile loads without errors.
    from lca.application.api.default_context import build_default_context
    ctx = build_default_context(profile="profiles/fixtures/think-orchestrator-compile.yaml")
    assert ctx is not None
```

(The implementer must align the helper imports — `build_default_context`
is illustrative; use whatever the project exposes for fixture-profile boot
testing. Search the existing `test_think_subgraph_compile.py`-style tests
for the project's accepted pattern and mirror it.)

### Step 3.6: Run the orchestrator test

Run: `uv run pytest tests/think/test_orchestrator_graph.py -q`
Expected: passes (resolver resolves plan; fixture profile boots).

### Step 3.7: Validate the compile-fixture profile

Run: `uv run python -m lca_kernel serve --profile profiles/fixtures/think-orchestrator-compile.yaml --validate`
Expected: exit code 0; topology compiles.

### Step 3.8: Validate the production profile

Run: `uv run python -m lca_kernel serve --profile profiles/web-standard.yaml --validate`
Expected: exit code 0.

Run: `./scripts/lca-ops why-plugin phase.think.orchestrator --profile profiles/web-standard.yaml`
Expected: `plugin: phase.think.orchestrator` line.

### Step 3.9: Commit

```bash
git add lca/harness/graph/execute/subgraph_phase_runner.py \
        lca/plugins/loop/phase/think/orchestrator/ \
        bundles/think-orchestrator.yaml \
        bundles/think-orchestrator-graph.yaml \
        profiles/fixtures/think-orchestrator-compile.yaml \
        profiles/web-standard.yaml \
        profiles/think-subgraph-dev.yaml \
        tests/think/test_orchestrator_graph.py
git commit -m "feat(think): move carry into runner, add orchestrator + bundles + profile switch"
```

---

## Task 4: Delete the temporary files and verify final state

**Files:**
- Delete: `lca/plugins/loop/phase/think/subgraph/_shared.py`
- Delete: `lca/plugins/loop/phase/think/subgraph_host/plugin.py`
- Delete: `lca/plugins/loop/phase/think/subgraph_host/__init__.py`
- Delete: `bundles/think-subgraph-host.yaml`
- Delete: `bundles/think-subgraph.yaml`
- Delete: `bundles/think-subgraph-graph.yaml`
- Delete: `bundles/think-subgraph-steps.yaml`
- Delete: `profiles/fixtures/think-subgraph-compile.yaml`
- Delete: `tests/cognition/test_think_subgraph_parity.py`
- Delete (entire subtree): `lca/plugins/loop/phase/think/subgraph/` (after
  moving tests to `tests/think/`)

### Step 4.1: Delete the temporary files

```bash
git rm lca/plugins/loop/phase/think/subgraph/_shared.py \
       lca/plugins/loop/phase/think/subgraph_host/plugin.py \
       lca/plugins/loop/phase/think/subgraph_host/__init__.py \
       bundles/think-subgraph-host.yaml \
       bundles/think-subgraph.yaml \
       bundles/think-subgraph-graph.yaml \
       bundles/think-subgraph-steps.yaml \
       profiles/fixtures/think-subgraph-compile.yaml \
       tests/cognition/test_think_subgraph_parity.py
# If the only contents of the subgraph/ subtree have been removed, drop it too:
git rm -r lca/plugins/loop/phase/think/subgraph/ 2>/dev/null || true
git rm -r lca/plugins/loop/phase/think/subgraph_host/ 2>/dev/null || true
```

### Step 4.2: Grep for residual references

Run:
```bash
grep -rn "phase.think.subgraph" lca/ profiles/ bundles/ tests/ 2>/dev/null
grep -rn "ThinkSubgraphCarry\|run_shortcut_step\|run_route_step\|run_reason_step\|run_classify_step\|run_gate_step\|collaborators_from_brain" lca/ tests/ 2>/dev/null
```

Expected: empty output.

If any reference remains, fix it inline before continuing.

### Step 4.3: Run the full think test suite

Run: `uv run pytest tests/think/ -q`
Expected: all five plugin tests + orchestrator test pass.

### Step 4.4: Run lint and type-check

Run:
```bash
uv run ruff check lca/ tests/
uv run mypy lca/
```

Expected: both exit 0. If any prior-baseline failures surface, document
them in the PR description and do not block on them.

### Step 4.5: Boot the kernel end-to-end

Run:
```bash
uv run python -m lca_kernel serve --profile profiles/web-standard.yaml --validate
./scripts/lca-ops kernel-restart
./scripts/lca-ops status --json
```

Expected: kernel boots, status returns running.

### Step 4.6: Commit the deletions

```bash
git commit -m "chore(think): remove temporary _shared.py and subgraph_host container"
```

---

## Self-Review

### 1. Spec coverage

| Spec section | Task |
|---|---|
| §3.1 carry α | Task 1, Task 3.1 |
| §3.2 shortcut independent capability | Task 2.1, Task 2.5 |
| §3.3 orchestrator | Task 3.2 |
| §3.4 bundle shape | Task 3.3 |
| §4 delete list | Task 4.1 |
| §4 create list | Tasks 1.1, 2.1–2.5, 3.2, 3.3 |
| §5 capability key map | Tasks 2.1–2.5, 3.2 |
| §6 C11 EP whitelist | Task 2.1.5, 2.2.5, 2.3.5, 2.4.5, 2.5.5 |
| §7 verification | Tasks 3.6–3.8, 4.2–4.5 |

### 2. Placeholder scan

- No "TBD" / "TODO" / "implement later" tokens.
- All test bodies contain real assertions.
- All step plugin bodies contain real logic, not placeholders.

### 3. Type consistency

- `ThinkSubgraphCarry` defined in `lca/contracts/models/core/execution/think_carry.py`; consumed by every step plugin and by the runner via the same import path.
- `CARRY_KEY` is the single string `"think.subgraph.carry"`; used by both the runner and each `_carry(context)` helper.
- `PhaseResult.result_kind` values: `"decision"` for terminal (shortcut hit, gate), `"think_stage"` for intermediate (shortcut miss, route, reason, classify). The runner's exit condition is `result.result_kind == "decision"`, matching `bundles/think-orchestrator-graph.yaml` edges.
- `phase.think.<step>` capability keys match across the five `@plugin(provides=...)` decorators and the `context.capabilities.get(...)` reads inside the executors.
