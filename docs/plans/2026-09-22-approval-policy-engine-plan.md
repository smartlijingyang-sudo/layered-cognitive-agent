# Approval Policy Engine and Graph Node-ization Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Refactor the approval classification system by decoupling cognition from permission evaluation, implementing the Strategy and Chain of Responsibility patterns (`ApprovalPolicyEngine`), and elevating permission checks into declarative graph nodes (`act.authorize` / `act.approve.gate`) with rich `ApprovalRequirement` contracts.

**Architecture:**
1. Pure cognition: `think.decision.parse` emits clean `Decision` candidate intents with zero infrastructure or ambient plane dependencies.
2. Control plane: `act.authorize` explicitly consumes `decision` and `plane`, evaluating rules via an extensible `ApprovalPolicyEngine` (Chain of Responsibility: HITL -> Machine -> DefaultAllow).
3. Graph routing: `act.approve.gate` consumes typed `ApprovalRequirement` to route to `act.envelope` or `intervene.interrupt` with full audit context, eliminating Boolean Blindness.

**Tech Stack:** Python 3.11, dataclasses, Protocols, Cordis declarative graph nodes, pytest.

---

### Task 1: Contracts Layer — Domain Models & Strategy Protocol

**Files:**
- Create: `lca/contracts/models/core/execution/approval.py`
- Create: `lca/contracts/protocols/execution/approval_strategy.py`
- Test: `tests/contracts/test_approval_models.py`
- Does NOT own: `lca/infrastructure/`, `lca/nodes/`, `deploy/` (AP-01)
- Invariants to test: `ApprovalRequirement` is frozen dataclass, Enum closed sets, default values (AP-02)

**Step 1: Write the failing test**

```python
# tests/contracts/test_approval_models.py
from lca.contracts.models.core.execution.approval import (
    ApprovalReasonKind,
    ApprovalRequirement,
    RiskLevel,
)

def test_approval_requirement_defaults_to_none():
    req = ApprovalRequirement()
    assert req.required is False
    assert req.reason_kind == ApprovalReasonKind.NONE
    assert req.risk_level == RiskLevel.LOW
    assert req.summary == ""
    assert req.target_resource is None
    assert req.details == {}

def test_approval_requirement_frozen():
    req = ApprovalRequirement(required=True, reason_kind=ApprovalReasonKind.HUMAN_INTERACTION)
    try:
        req.required = False
        assert False, "Should have raised FrozenInstanceError"
    except Exception:
        pass
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/contracts/test_approval_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lca.contracts.models.core.execution.approval'`

**Step 3: Write minimal implementation**

```python
# lca/contracts/models/core/execution/approval.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ApprovalReasonKind(str, Enum):
    NONE = "none"
    HUMAN_INTERACTION = "human_interaction"
    SENSITIVE_RESOURCE = "sensitive_resource"
    UNAUTHORIZED_PATH = "unauthorized_path"
    ELEVATED_COMMAND = "elevated_command"
    POLICY_RULE = "policy_rule"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ApprovalRequirement:
    required: bool = False
    reason_kind: ApprovalReasonKind = ApprovalReasonKind.NONE
    risk_level: RiskLevel = RiskLevel.LOW
    summary: str = ""
    target_resource: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
```

```python
# lca/contracts/protocols/execution/approval_strategy.py
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from lca.contracts.models.core.execution.approval import ApprovalRequirement
from lca.contracts.models.core.execution.decision import ToolCall
from lca.contracts.models.core.state.plane import PlaneRef


class ApprovalStrategy(Protocol):
    @property
    def strategy_name(self) -> str: ...

    def evaluate(
        self,
        tool_calls: Sequence[ToolCall],
        plane: PlaneRef | None = None,
    ) -> ApprovalRequirement | None: ...
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/contracts/test_approval_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/contracts/models/core/execution/approval.py lca/contracts/protocols/execution/approval_strategy.py tests/contracts/test_approval_models.py
git commit -m "feat(contracts): add ApprovalRequirement contract and ApprovalStrategy protocol"
```

---

### Task 2: Infrastructure Layer — Strategy Engine & Standard Strategies

**Files:**
- Create: `lca/infrastructure/runtime_plane/access/policy/approval_engine.py`
- Test: `tests/infrastructure/runtime_plane/access/test_approval_engine.py`
- Does NOT own: `lca/nodes/`, `deploy/`, `contracts/models/core/event/` (AP-01)
- Invariants to test: Chain order, HITL strategy detects askUserQuestion, Machine strategy detects sensitive paths, DefaultAllow fallback (AP-02)

**Step 1: Write the failing test**

```python
# tests/infrastructure/runtime_plane/access/test_approval_engine.py
from lca.contracts.models.core.execution.approval import ApprovalReasonKind, RiskLevel
from lca.contracts.models.core.execution.decision import ToolCall
from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef
from lca.infrastructure.runtime_plane.access.policy.approval_engine import (
    ApprovalPolicyEngine,
    DefaultAllowStrategy,
    HITLInteractionStrategy,
    MachineAccessStrategy,
    build_default_approval_engine,
)


def test_hitl_strategy_detects_ask_user():
    strategy = HITLInteractionStrategy()
    calls = [ToolCall(tool_call_id="c1", tool_name="askUserQuestion", arguments={"questions": []})]
    req = strategy.evaluate(calls, plane=None)
    assert req is not None
    assert req.required is True
    assert req.reason_kind == ApprovalReasonKind.HUMAN_INTERACTION
    assert req.risk_level == RiskLevel.LOW


def test_machine_strategy_detects_sensitive_ssh():
    strategy = MachineAccessStrategy()
    plane = PlaneRef(plane_id="p1", kind=PlaneKind.MACHINE, endpoint=None, metadata={})
    calls = [ToolCall(tool_call_id="c2", tool_name="local_readFile", arguments={"path": "/home/user/.ssh/id_rsa"})]
    req = strategy.evaluate(calls, plane=plane)
    assert req is not None
    assert req.required is True
    assert req.reason_kind == ApprovalReasonKind.SENSITIVE_RESOURCE
    assert req.risk_level == RiskLevel.HIGH


def test_engine_fallback_to_allow_when_clean():
    engine = build_default_approval_engine()
    calls = [ToolCall(tool_call_id="c3", tool_name="random_tool", arguments={})]
    req = engine.evaluate(calls, plane=None)
    assert req.required is False
    assert req.reason_kind == ApprovalReasonKind.NONE
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/infrastructure/runtime_plane/access/test_approval_engine.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

Implement `HITLInteractionStrategy`, `MachineAccessStrategy`, `DefaultAllowStrategy`, and `ApprovalPolicyEngine` with `build_default_approval_engine()`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/infrastructure/runtime_plane/access/test_approval_engine.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/runtime_plane/access/policy/approval_engine.py tests/infrastructure/runtime_plane/access/test_approval_engine.py
git commit -m "feat(runtime_plane): add ApprovalPolicyEngine and standard strategies"
```

---

### Task 3: Infrastructure Compat Seam — Refactor `decision_needs_approval`

**Files:**
- Modify: `lca/infrastructure/runtime_plane/access/classify.py`
- Test: `tests/contracts/test_decision_needs_approval_typed.py`
- Does NOT own: `lca/nodes/think/`, `lca/nodes/act/` (AP-01)
- Invariants to test: Backwards compatibility of `decision_needs_approval` across existing tests (AP-02)

**Step 1: Run existing test baseline**

Run: `pytest tests/contracts/test_decision_needs_approval_typed.py -v`
Expected: PASS

**Step 2: Refactor `decision_needs_approval` to delegate to `build_default_approval_engine()`**

Delegate `decision_needs_approval(tool_calls)` to `build_default_approval_engine().evaluate(tool_calls, plane=current_primary()).required`.

**Step 3: Run existing tests to verify zero regression**

Run: `pytest tests/contracts/test_decision_needs_approval_typed.py tests/scenario/plane/test_plane_bindings.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add lca/infrastructure/runtime_plane/access/classify.py
git commit -m "refactor(runtime_plane): delegate decision_needs_approval to ApprovalPolicyEngine"
```

---

### Task 4: Cognition Purity — Cleanse `think.decision.parse` Cross-Layer Import

**Files:**
- Modify: `lca/nodes/think/decision/parse.py`
- Test: `tests/nodes/think/test_decision_parse_purity.py`
- Does NOT own: `lca/nodes/act/`, `deploy/` (AP-01)
- Invariants to test: AST verification that `think.decision.parse` does NOT import `infrastructure.runtime_plane` (AP-02)

**Step 1: Write AST purity verification test**

```python
# tests/nodes/think/test_decision_parse_purity.py
import ast
from pathlib import Path

def test_think_decision_parse_has_no_runtime_plane_imports():
    file_path = Path("lca/nodes/think/decision/parse.py")
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    imported_modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)
    for mod in imported_modules:
        assert not mod.startswith("lca.infrastructure.runtime_plane"), f"Forbidden import found: {mod}"
```

**Step 2: Modify `think.decision.parse` to remove `decision_needs_approval` import**

Set `needs_approval=False` by default in pure cognitive parsing.

**Step 3: Run test to verify purity**

Run: `pytest tests/nodes/think/test_decision_parse_purity.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add lca/nodes/think/decision/parse.py tests/nodes/think/test_decision_parse_purity.py
git commit -m "refactor(think): decouple decision.parse from runtime plane access"
```

---

### Task 5: Control Plane Node-ization — `act.authorize` & `act.approve.gate`

**Files:**
- Modify: `lca/nodes/act/authorize/authorize.py`
- Modify: `lca/nodes/intervene/approve_gate.py`
- Test: `tests/intervene/test_approve_gate_rich_requirement.py`
- Does NOT own: `lca/nodes/think/`, `lca/transport/` (AP-01)
- Invariants to test: `act.authorize` evaluates `ApprovalRequirement`, `act.approve.gate` routes by `ApprovalRequirement.required` (AP-02)

**Step 1: Write the failing test**

```python
# tests/intervene/test_approve_gate_rich_requirement.py
import pytest
from lca.contracts.models.core.execution.approval import (
    ApprovalReasonKind,
    ApprovalRequirement,
    RiskLevel,
)
from lca.contracts.models.core.execution.decision import ActionType, Decision, ToolCall
from lca.contracts.protocols.declarative.declarative_1.node_executor import NodeInput
from lca.nodes.intervene.approve_gate import ApproveGateExecutor

@pytest.mark.asyncio
async def test_approve_gate_routes_to_interrupt_with_rich_requirement():
    executor = ApproveGateExecutor()
    dec = Decision(decision_id="d1", action_type="use_tool", rationale="", confidence=1.0)
    req = ApprovalRequirement(
        required=True,
        reason_kind=ApprovalReasonKind.SENSITIVE_RESOURCE,
        risk_level=RiskLevel.HIGH,
        summary="Accessing SSH key",
    )
    result = await executor.execute(NodeInput(port_values={"decision": dec, "approval_requirement": req, "command": None}), None)
    routing = result.port_values["approval_routing"]
    assert routing.action_type == ActionType.ASK_HUMAN
    assert routing.next_node == "intervene.interrupt"
    assert result.port_values["approval_requirement"] == req
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/intervene/test_approve_gate_rich_requirement.py -v`
Expected: FAIL

**Step 3: Update `act.authorize` and `act.approve.gate` implementations**

1. In `act.authorize`: evaluate `ApprovalRequirement` using `build_default_approval_engine()`. Pass `approval_requirement` port.
2. In `act.approve.gate`: check `approval_requirement.required` (fallback to `decision.needs_approval` for backwards compatibility).

**Step 4: Run test to verify it passes**

Run: `pytest tests/intervene/test_approve_gate_rich_requirement.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/nodes/act/authorize/authorize.py lca/nodes/intervene/approve_gate.py tests/intervene/test_approve_gate_rich_requirement.py
git commit -m "feat(act): evaluate and route with structured ApprovalRequirement"
```

---

### Task 6: Full Regression & Pre-Push Verification

**Files:**
- Does NOT own: any source code files (verification only)
- Invariants to test: Full regression suite green, lint clean, git diff clean (AP-02)

**Step 1: Run comprehensive regression test suite**

Run:
```bash
pytest tests/contracts/test_decision_needs_approval_typed.py tests/intervene/ tests/nodes/think/test_decision_parse_purity.py tests/infrastructure/runtime_plane/access/ -v
```
Expected: PASS (100% green)

**Step 2: Run code quality checks**

Run:
```bash
ruff check --fix
git diff --check
wc -l AGENTS.md
```
Expected: 0 errors, exit 0, line count <= 220.

**Step 3: Update `docs/plans/task.md` and commit**

```bash
git add docs/plans/task.md
git commit -m "chore: complete approval policy engine implementation and verification"
```
