# 唤醒多门控矩阵与子代理禁声运行时实施计划 (Wake Matrix & Subagent Mute Runtime Plan)

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 基于 ADR-0248 E1/E2/E4 证据，落地 Wake 唤醒分类多门控矩阵（Wake Matrix）、可沉默 Routine 门禁、Reply-First 中间件、Subagent 物理禁声过滤器以及后台复苏（Revival）父进程统一交付协调器。

**Architecture:** 
1. **唤醒分类表 (Wake Matrix)**：将唤醒源严格归类为 `USER_INPUT`、`FIRST_RUN`、`INBOUND`、`ROUTINE`、`PEER_AGENT`、`REVIVAL` 六大闭集，由 `WakeClassifier` 生成强类型不可变 `WakeContext`（包含 `is_silence_allowed`, `requires_reply_first`, `channel_target` 等约束）；
2. **声带与门禁联动**：`GatedVocalGate` 接入 `WakeContext`，`VocalSettleGuard` 依据 `is_silence_allowed` 精准放行无变化的 Routine 例程；
3. **Reply-First 中间件**：在 `requires_reply_first=True` 且尚未 Ack 时动态注入承接引导，消除假死；
4. **子代理禁声 (Subagent Mute)**：在子代理运行时剥离 `send_message` 工具，实现重活无声道；
5. **后台复苏 (Revival)**：子代理执行完毕后产生 `REVIVAL` 唤醒源唤醒父协调者，由父协调者统一开口向用户交付。

**Tech Stack:** Python 3.11+, Pydantic V2 (`frozen=True`, `extra="forbid"`), Pytest, LCA Contracts & Infrastructure Layer.

---

### Task 1: Wake 契约与分类器 (WakeSource, WakeContext, WakeClassifier)

**Files:**
- Create: `lca/contracts/models/vocal/wake.py`
- Modify: `lca/contracts/models/vocal/__init__.py`
- Create: `lca/infrastructure/vocal/wake.py`
- Test: `tests/contracts/vocal/test_wake_models.py`
- Test: `tests/infrastructure/vocal/test_wake_classifier.py`
- Does NOT own: 业务消息持久化（AP-01）
- Invariants to test: `WakeSource` 闭集、`WakeContext` 不可变、`WakeClassifier` 映射规则（Routine 允许沉默、User/FirstRun/Inbound 必须回复、Inbound 必须带 channel_target）（AP-02）

**Step 1: Write the failing tests**

```python
# tests/contracts/vocal/test_wake_models.py
import pytest
from pydantic import ValidationError
from lca.contracts.models.vocal.wake import WakeContext, WakeSource


def test_wake_source_enum_values():
    assert WakeSource.USER_INPUT == "user_input"
    assert WakeSource.FIRST_RUN == "first_run"
    assert WakeSource.INBOUND == "inbound"
    assert WakeSource.ROUTINE == "routine"
    assert WakeSource.PEER_AGENT == "peer_agent"
    assert WakeSource.REVIVAL == "revival"


def test_wake_context_frozen():
    ctx = WakeContext(
        source=WakeSource.USER_INPUT,
        is_silence_allowed=False,
        requires_reply_first=True,
    )
    with pytest.raises(ValidationError):
        ctx.is_silence_allowed = True  # type: ignore
```

```python
# tests/infrastructure/vocal/test_wake_classifier.py
from lca.contracts.models.vocal.wake import WakeSource
from lca.infrastructure.vocal.wake import WakeClassifier


def test_classify_user_input():
    classifier = WakeClassifier()
    ctx = classifier.classify("user_input")
    assert ctx.source == WakeSource.USER_INPUT
    assert ctx.is_silence_allowed is False
    assert ctx.requires_reply_first is True


def test_classify_routine():
    classifier = WakeClassifier()
    ctx = classifier.classify("routine")
    assert ctx.source == WakeSource.ROUTINE
    assert ctx.is_silence_allowed is True
    assert ctx.requires_reply_first is False


def test_classify_inbound_with_channel():
    classifier = WakeClassifier()
    ctx = classifier.classify("inbound", channel_target="wechat:user_123")
    assert ctx.source == WakeSource.INBOUND
    assert ctx.is_silence_allowed is False
    assert ctx.channel_target == "wechat:user_123"


def test_classify_revival():
    classifier = WakeClassifier()
    ctx = classifier.classify("revival", subagent_id="sub_worker_1")
    assert ctx.source == WakeSource.REVIVAL
    assert ctx.is_silence_allowed is True
    assert ctx.subagent_id == "sub_worker_1"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/contracts/vocal/test_wake_models.py tests/infrastructure/vocal/test_wake_classifier.py -v --no-cov`
Expected: FAIL

**Step 3: Write minimal implementation**

`lca/contracts/models/vocal/wake.py`:
```python
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field


class WakeSource(StrEnum):
    USER_INPUT = "user_input"
    FIRST_RUN = "first_run"
    INBOUND = "inbound"
    ROUTINE = "routine"
    PEER_AGENT = "peer_agent"
    REVIVAL = "revival"


class WakeContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: WakeSource = Field(..., description="唤醒源")
    is_silence_allowed: bool = Field(default=False, description="是否允许无变化时完全沉默收敛")
    requires_reply_first: bool = Field(default=False, description="是否要求首个动作为承接回复")
    channel_target: str | None = Field(default=None, description="入站渠道标识")
    subagent_id: str | None = Field(default=None, description="复苏事件关联的子代理ID")
    priority: bool = Field(default=False, description="是否为高优先级打断唤醒")
```

`lca/infrastructure/vocal/wake.py`:
```python
from lca.contracts.models.vocal.wake import WakeContext, WakeSource


class WakeClassifier:
    """根据入站线索与唤醒门分类生成强类型 WakeContext。"""

    def classify(
        self,
        source: str | WakeSource,
        channel_target: str | None = None,
        subagent_id: str | None = None,
        priority: bool = False,
    ) -> WakeContext:
        src = WakeSource(source) if isinstance(source, str) else source

        if src == WakeSource.ROUTINE:
            return WakeContext(
                source=src,
                is_silence_allowed=True,
                requires_reply_first=False,
                priority=priority,
            )
        elif src == WakeSource.USER_INPUT:
            return WakeContext(
                source=src,
                is_silence_allowed=False,
                requires_reply_first=True,
                priority=priority,
            )
        elif src == WakeSource.FIRST_RUN:
            return WakeContext(
                source=src,
                is_silence_allowed=False,
                requires_reply_first=True,
                priority=priority,
            )
        elif src == WakeSource.INBOUND:
            return WakeContext(
                source=src,
                is_silence_allowed=False,
                requires_reply_first=True,
                channel_target=channel_target,
                priority=priority,
            )
        elif src == WakeSource.REVIVAL:
            return WakeContext(
                source=src,
                is_silence_allowed=True,
                requires_reply_first=False,
                subagent_id=subagent_id,
                priority=priority,
            )
        else:  # PEER_AGENT
            return WakeContext(
                source=src,
                is_silence_allowed=False,
                requires_reply_first=False,
                priority=priority,
            )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/contracts/vocal/test_wake_models.py tests/infrastructure/vocal/test_wake_classifier.py -v --no-cov`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/contracts/models/vocal/ lca/infrastructure/vocal/wake.py tests/contracts/vocal/ tests/infrastructure/vocal/
git commit -m "feat(vocal): implement wake source contracts and classifier"
```

---

### Task 2: 声带硬闸与结算门禁接入 WakeContext (GatedVocalGate & VocalSettleGuard)

**Files:**
- Modify: `lca/infrastructure/vocal/gate.py`
- Modify: `lca/infrastructure/vocal/settle_guard.py`
- Test: `tests/infrastructure/vocal/test_vocal_wake_integration.py`
- Does NOT own: 改变 Direct 模式行为（AP-01）
- Invariants to test:
  - `GatedVocalGate` 接收并保存 `WakeContext`；
  - `VocalSettleGuard` 严格依据 `wake.is_silence_allowed` 决定是否放行 0 交付轮次（AP-02）。

**Step 1: Write the failing test**

```python
# tests/infrastructure/vocal/test_vocal_wake_integration.py
import pytest
from lca.contracts.models.vocal.models import SendMessagePayload, VocalMessageType
from lca.contracts.models.vocal.wake import WakeContext, WakeSource
from lca.infrastructure.vocal.exceptions import UndeliveredTurnError
from lca.infrastructure.vocal.gate import GatedVocalGate
from lca.infrastructure.vocal.settle_guard import VocalSettleGuard


def test_gated_gate_with_wake_context_user_input():
    wake = WakeContext(source=WakeSource.USER_INPUT, is_silence_allowed=False, requires_reply_first=True)
    gate = GatedVocalGate("op_user", wake_context=wake)
    assert gate.wake_context.source == WakeSource.USER_INPUT

    guard = VocalSettleGuard(gate)
    gate.handle_text_chunk("Internal scratchpad text")
    with pytest.raises(UndeliveredTurnError):
        guard.validate_turn_settle()


def test_gated_gate_with_wake_context_routine_silence():
    wake = WakeContext(source=WakeSource.ROUTINE, is_silence_allowed=True, requires_reply_first=False)
    gate = GatedVocalGate("op_routine", wake_context=wake)
    guard = VocalSettleGuard(gate)

    gate.handle_text_chunk("Routine executed, no delta.")
    # is_silence_allowed=True，允许合法沉默
    assert guard.validate_turn_settle() is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/infrastructure/vocal/test_vocal_wake_integration.py -v --no-cov`
Expected: FAIL

**Step 3: Write minimal implementation**

在 `GatedVocalGate.__init__` 支持接收 `wake_context: WakeContext | None = None`，若传 `wake_source: str` 则自愈包装为 `WakeContext`；
在 `VocalSettleGuard.validate_turn_settle` 中依据 `self._gate.wake_context.is_silence_allowed` 执行断言判定。

**Step 4: Run test to verify it passes**

Run: `pytest tests/infrastructure/vocal/test_vocal_wake_integration.py -v --no-cov`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/vocal/gate.py lca/infrastructure/vocal/settle_guard.py tests/infrastructure/vocal/test_vocal_wake_integration.py
git commit -m "feat(vocal): integrate wake context into gated gate and settle guard"
```

---

### Task 3: Reply-First 提示词与门禁中间件 (ReplyFirstMiddleware)

**Files:**
- Create: `lca/infrastructure/vocal/middleware.py`
- Test: `tests/infrastructure/vocal/test_reply_first_middleware.py`
- Does NOT own: 篡改模型核心温度或采样参数（AP-01）
- Invariants to test:
  - 当 `wake.requires_reply_first == True` 且 `gate.has_acked == False` 时，注入承接引导语句；
  - 一旦 `gate.has_acked == True`，不再注入引导语句；
  - 当 `requires_reply_first == False`（如例程），绝对不注入（AP-02）。

**Step 1: Write the failing test**

```python
# tests/infrastructure/vocal/test_reply_first_middleware.py
from lca.contracts.models.vocal.models import SendMessagePayload, VocalMessageType
from lca.contracts.models.vocal.wake import WakeContext, WakeSource
from lca.infrastructure.vocal.gate import GatedVocalGate
from lca.infrastructure.vocal.middleware import ReplyFirstMiddleware


def test_middleware_injects_reminder_before_ack():
    wake = WakeContext(source=WakeSource.USER_INPUT, requires_reply_first=True)
    gate = GatedVocalGate("op_1", wake_context=wake)
    middleware = ReplyFirstMiddleware()

    prompt = middleware.augment_prompt("Original Prompt", gate)
    assert "[Reply-First 契约]" in prompt
    assert "send_message" in prompt


def test_middleware_stops_injecting_after_ack():
    wake = WakeContext(source=WakeSource.USER_INPUT, requires_reply_first=True)
    gate = GatedVocalGate("op_2", wake_context=wake)
    middleware = ReplyFirstMiddleware()

    gate.deliver(SendMessagePayload(type=VocalMessageType.TEXT, content="正在为你排查..."))
    assert gate.has_acked is True

    prompt = middleware.augment_prompt("Original Prompt", gate)
    assert "[Reply-First 契约]" not in prompt
    assert prompt == "Original Prompt"


def test_middleware_no_injection_for_routine():
    wake = WakeContext(source=WakeSource.ROUTINE, requires_reply_first=False)
    gate = GatedVocalGate("op_3", wake_context=wake)
    middleware = ReplyFirstMiddleware()

    prompt = middleware.augment_prompt("Routine Prompt", gate)
    assert "[Reply-First 契约]" not in prompt
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/infrastructure/vocal/test_reply_first_middleware.py -v --no-cov`
Expected: FAIL

**Step 3: Write minimal implementation**

`lca/infrastructure/vocal/middleware.py`:
```python
from lca.infrastructure.vocal.gate import GatedVocalGate


class ReplyFirstMiddleware:
    """Reply-First 承接提醒中间件：在用户在场且尚未 Ack 时提醒模型先发声。"""

    REMINDER_TEXT: str = (
        "\n\n[Reply-First 契约]: 用户正在等待。"
        "在调用任何复杂外部工具或执行耗时排查前，请务必先通过 send_message(type='text') "
        "发送一句简明承接语（如‘正在为你排查...’），防止用户端产生假死感。"
    )

    def augment_prompt(self, base_prompt: str, gate: GatedVocalGate) -> str:
        if not gate.wake_context.requires_reply_first:
            return base_prompt
        if gate.has_acked:
            return base_prompt
        return f"{base_prompt}{self.REMINDER_TEXT}"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/infrastructure/vocal/test_reply_first_middleware.py -v --no-cov`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/vocal/middleware.py tests/infrastructure/vocal/test_reply_first_middleware.py
git commit -m "feat(vocal): implement reply-first prompt middleware"
```

---

### Task 4: Subagent 物理禁声过滤器 (SubagentVocalMuteFilter)

**Files:**
- Create: `lca/infrastructure/vocal/tool_filter.py`
- Test: `tests/infrastructure/vocal/test_subagent_vocal_mute.py`
- Does NOT own: 改变非声带通用工具（AP-01）
- Invariants to test:
  - 当 `origin == "subagent"` 或 `is_subagent == True` 时，工具集中严禁包含 `send_message`；
  - 当 `origin == "user"` 或协调者主进程时，保留 `send_message`（AP-02）。

**Step 1: Write the failing test**

```python
# tests/infrastructure/vocal/test_subagent_vocal_mute.py
from lca.infrastructure.vocal.tool_filter import VocalToolFilter


def test_filter_removes_send_message_for_subagent():
    tool_filter = VocalToolFilter()
    all_tools = ["read_file", "run_command", "send_message", "web_search"]

    subagent_tools = tool_filter.filter_tools_for_runtime(all_tools, origin="subagent")
    assert "send_message" not in subagent_tools
    assert "read_file" in subagent_tools
    assert len(subagent_tools) == 3


def test_filter_retains_send_message_for_coordinator():
    tool_filter = VocalToolFilter()
    all_tools = ["read_file", "run_command", "send_message", "web_search"]

    parent_tools = tool_filter.filter_tools_for_runtime(all_tools, origin="user")
    assert "send_message" in parent_tools
    assert len(parent_tools) == 4
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/infrastructure/vocal/test_subagent_vocal_mute.py -v --no-cov`
Expected: FAIL

**Step 3: Write minimal implementation**

`lca/infrastructure/vocal/tool_filter.py`:
```python
from collections.abc import Sequence


class VocalToolFilter:
    """声带工具过滤器：依据执行者身份（协调者 vs 子代理）实施声带物理隔离。"""

    VOCAL_TOOL_NAME: str = "send_message"

    def filter_tools_for_runtime(
        self, tools: Sequence[str], origin: str | None = None
    ) -> list[str]:
        # Subagent 物理禁声（ADR-0248 §5.3: 子代理无声带，只汇报父进程）
        if origin == "subagent":
            return [t for t in tools if t != self.VOCAL_TOOL_NAME]
        return list(tools)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/infrastructure/vocal/test_subagent_vocal_mute.py -v --no-cov`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/vocal/tool_filter.py tests/infrastructure/vocal/test_subagent_vocal_mute.py
git commit -m "feat(vocal): implement subagent vocal mute tool filter"
```

---

### Task 5: 后台复苏（Revival）与父进程统一交付协调器 (RevivalCoordinator)

**Files:**
- Create: `lca/application/vocal/revival.py`
- Modify: `lca/application/vocal/__init__.py`
- Test: `tests/application/vocal/test_revival_coordinator.py`
- Does NOT own: 篡改底层 subagent 线程模型（AP-01）
- Invariants to test:
  - 子代理完成时生成 `WakeSource.REVIVAL` 触发事件；
  - 协调者由 Revival 唤醒，调用自身的 `send_message` 正式对外交付，子代理全程 0 声带泄露（AP-02）。

**Step 1: Write the failing test**

```python
# tests/application/vocal/test_revival_coordinator.py
from lca.application.vocal.revival import RevivalCoordinator
from lca.contracts.models.vocal.wake import WakeSource
from lca.infrastructure.vocal.strategy import GatedVoiceStrategy


def test_revival_coordinator_handles_subagent_completion():
    strategy = GatedVoiceStrategy()
    # 1. 父进程拥有声带
    parent_gate = strategy.create_gate("parent_op")
    revival_coord = RevivalCoordinator(parent_gate)

    # 2. 模拟子代理完成并上报
    subagent_result = {
        "subagent_id": "sub_parser_42",
        "status": "completed",
        "summary": "已成功分析 100 个文件，发现 2 处潜在内存泄漏。",
    }

    wake_ctx, delivery_receipt = revival_coord.handle_subagent_completion(subagent_result)

    # 3. 验证唤醒源为 REVIVAL
    assert wake_ctx.source == WakeSource.REVIVAL
    assert wake_ctx.subagent_id == "sub_parser_42"

    # 4. 验证由父进程统一发声交付
    assert delivery_receipt.vocal_type == "text"
    visible = parent_gate.get_visible_outputs()
    assert len(visible) == 1
    assert "已成功分析 100 个文件" in visible[0]["content"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/application/vocal/test_revival_coordinator.py -v --no-cov`
Expected: FAIL

**Step 3: Write minimal implementation**

`lca/application/vocal/revival.py`:
```python
from typing import Any
from lca.contracts.models.vocal.models import DeliveryReceipt, SendMessagePayload, VocalMessageType
from lca.contracts.models.vocal.wake import WakeContext, WakeSource
from lca.contracts.protocols.vocal.protocol import VocalGateProtocol


class RevivalCoordinator:
    """后台子代理完成复苏协调器：接收子代理上报并唤醒父进程统一开口交付。"""

    def __init__(self, parent_gate: VocalGateProtocol) -> None:
        self._parent_gate = parent_gate

    def handle_subagent_completion(
        self, subagent_outcome: dict[str, Any]
    ) -> tuple[WakeContext, DeliveryReceipt]:
        sub_id = str(subagent_outcome.get("subagent_id", "unknown_subagent"))
        summary = str(subagent_outcome.get("summary", "子代理任务已完成。"))

        wake_ctx = WakeContext(
            source=WakeSource.REVIVAL,
            is_silence_allowed=True,
            subagent_id=sub_id,
        )

        delivery_payload = SendMessagePayload(
            type=VocalMessageType.TEXT,
            content=f"[子代理汇报] {summary}",
        )
        receipt = self._parent_gate.deliver(delivery_payload)
        return wake_ctx, receipt
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/application/vocal/test_revival_coordinator.py -v --no-cov`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/application/vocal/ tests/application/vocal/
git commit -m "feat(application): implement revival coordinator for unified parent delivery"
```

---

### Task 6: 全链路多门控集成场景测试 (E2E Wake Matrix & Revival Integration)

**Files:**
- Create: `tests/scenario/vocal/test_wake_matrix_and_revival_e2e.py`
- Test: 覆盖 Routine 自动检查沉默、Inbound 渠道定向回复、Subagent 派发并复苏父进程交付完整链路
- Invariants to test: 全链路多门控行为与 ADR-0248 100% 对齐（AP-02）

**Step 1: Write the failing test**

```python
# tests/scenario/vocal/test_wake_matrix_and_revival_e2e.py
from lca.application.vocal.factory import VocalStrategyFactory
from lca.application.vocal.revival import RevivalCoordinator
from lca.contracts.models.vocal.models import SendMessagePayload, VocalMessageType
from lca.contracts.models.vocal.wake import WakeSource
from lca.infrastructure.vocal.settle_guard import VocalSettleGuard
from lca.infrastructure.vocal.tool import SendMessageTool
from lca.infrastructure.vocal.tool_filter import VocalToolFilter
from lca.infrastructure.vocal.wake import WakeClassifier


def test_e2e_routine_silent_execution_flow():
    classifier = WakeClassifier()
    wake = classifier.classify(WakeSource.ROUTINE)

    factory = VocalStrategyFactory()
    strategy = factory.resolve_strategy("gated")
    gate = strategy.create_gate("run_routine_1", wake_source=wake.source)
    guard = VocalSettleGuard(gate)

    gate.handle_text_chunk("Routine health-check: all systems normal, no action required.")
    assert len(gate.get_visible_outputs()) == 0
    assert guard.validate_turn_settle() is True


def test_e2e_subagent_mute_and_revival_flow():
    # 1. 协调者拥有完整工具集
    tool_filter = VocalToolFilter()
    coord_tools = tool_filter.filter_tools_for_runtime(["run_command", "send_message"], origin="user")
    assert "send_message" in coord_tools

    # 2. 子代理被物理禁声
    sub_tools = tool_filter.filter_tools_for_runtime(coord_tools, origin="subagent")
    assert "send_message" not in sub_tools

    # 3. 父进程建立门控
    factory = VocalStrategyFactory()
    parent_gate = factory.resolve_strategy("gated").create_gate("parent_run")

    # 4. 子代理静默执行产出
    subagent_outcome = {
        "subagent_id": "sub_audit_99",
        "status": "completed",
        "summary": "发现并修复 3 处配置漂移。",
    }

    # 5. 后台复苏唤醒父协调者交付
    revival_coord = RevivalCoordinator(parent_gate)
    wake, receipt = revival_coord.handle_subagent_completion(subagent_outcome)
    assert wake.source == WakeSource.REVIVAL
    assert len(parent_gate.get_visible_outputs()) == 1
    assert "发现并修复 3 处配置漂移" in parent_gate.get_visible_outputs()[0]["content"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/scenario/vocal/test_wake_matrix_and_revival_e2e.py -v --no-cov`
Expected: FAIL

**Step 3: Verify implementations align and pass**

**Step 4: Run test to verify it passes**

Run: `pytest tests/scenario/vocal/test_wake_matrix_and_revival_e2e.py -v --no-cov`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/scenario/vocal/test_wake_matrix_and_revival_e2e.py
git commit -m "test(scenario): add e2e scenario tests for wake matrix and subagent revival"
```

---

### Task 7: 全量单测回归、代码门禁与 task.md 同步 (Regression & Hygiene)

**Files:**
- Run: 全量测试套件
- Run: Ruff check & format
- Run: git diff --check
- Update: `docs/plans/task.md`

**Step 1: Run pytest across all vocal tests**
Run: `pytest tests/contracts/vocal/ tests/infrastructure/vocal/ tests/application/vocal/ tests/scenario/vocal/ -v --no-cov`
Expected: ALL PASS

**Step 2: Run ruff check and format**
Run: `ruff check lca/ tests/ && ruff format --check lca/ tests/`
Expected: Clean with 0 errors

**Step 3: Verify git diff check**
Run: `git diff --check`
Expected: Clean with exit code 0

**Step 4: Update task.md**
Update `<project-root>/docs/plans/task.md` with the 7 tasks.

**Step 5: Commit and sync**
```bash
git add docs/plans/task.md
git commit -m "docs(plans): update task.md with wake matrix and revival tasks"
```
