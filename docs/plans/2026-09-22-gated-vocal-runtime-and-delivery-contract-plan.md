# 门控声带运行时与投递契约实施计划 (Gated Vocal Runtime & Delivery Contract Implementation Plan)

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 基于 ADR-0248 E1/E2 证据与设计规范，落地门控声带运行时（Gated Vocal Runtime）、`send_message` 唯一声道工具、Widget 停等状态机与 Settle 交付硬闸，并通过策略模式实现对既有直出流程的 100% 隔离与零破坏。

**Architecture:** 采用策略模式（`VocalStrategy`）解耦经典直通模式（`DirectVoiceStrategy`）与门控声带模式（`GatedVoiceStrategy`）；门控模式下将 LLM 普通文本截流为私有 `scratchpad`，对外仅通过强类型 `SendMessageTool` 发射正式气泡；引入轮次声带状态机（`TurnVocalState`）管控 Reply-First、Widget 挂起与 Settle 交付核验。

**Tech Stack:** Python 3.11+, Pydantic V2 (`frozen=True`, `extra="forbid"`), Pytest, LCA Contracts & Infrastructure Layer.

---

### Task 1: 契约模型与不可变载荷 (Contracts & DTOs)

**Files:**
- Create: `lca/contracts/models/vocal/models.py`
- Create: `lca/contracts/models/vocal/__init__.py`
- Test: `tests/contracts/vocal/test_vocal_models.py`
- Does NOT own: 业务逻辑实现、网络 I/O、全局状态（AP-01）
- Invariants to test: 模型不可变（`frozen=True`）、字段互斥语义合法性校验（Widget 必须有 1–6 个 options，Text 必须有 content，Secret 必须有 secret_key，禁止未知额外字段）（AP-02）

**Step 1: Write the failing test**

```python
# tests/contracts/vocal/test_vocal_models.py
import pytest
from pydantic import ValidationError
from lca.contracts.models.vocal.models import (
    VocalMode,
    VocalMessageType,
    WidgetOption,
    SendMessagePayload,
    DeliveryReceipt,
)


def test_vocal_mode_and_message_type_enums():
    assert VocalMode.DIRECT == "direct"
    assert VocalMode.GATED == "gated"
    assert VocalMessageType.TEXT == "text"
    assert VocalMessageType.WIDGET == "widget"


def test_send_message_payload_text_validation():
    payload = SendMessagePayload(type=VocalMessageType.TEXT, content="Hello User")
    assert payload.content == "Hello User"

    with pytest.raises(ValidationError):
        SendMessagePayload(type=VocalMessageType.TEXT, content=None)


def test_send_message_payload_widget_validation():
    opt = WidgetOption(id="opt1", label="Option 1", variant="primary")
    payload = SendMessagePayload(type=VocalMessageType.WIDGET, options=[opt])
    assert len(payload.options) == 1

    # Empty options should fail
    with pytest.raises(ValidationError):
        SendMessagePayload(type=VocalMessageType.WIDGET, options=[])

    # > 6 options should fail
    lots_opts = [WidgetOption(id=f"o{i}", label=f"L{i}") for i in range(7)]
    with pytest.raises(ValidationError):
        SendMessagePayload(type=VocalMessageType.WIDGET, options=lots_opts)


def test_models_are_frozen():
    opt = WidgetOption(id="opt1", label="Option 1")
    with pytest.raises(ValidationError):
        opt.label = "Changed"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/contracts/vocal/test_vocal_models.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# lca/contracts/models/vocal/models.py
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class VocalMode(StrEnum):
    DIRECT = "direct"
    GATED = "gated"


class VocalMessageType(StrEnum):
    TEXT = "text"
    ATTACHMENT = "attachment"
    WIDGET = "widget"
    SECRET_REQUEST = "secret_request"


class WidgetOption(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(..., description="选项唯一标识")
    label: str = Field(..., description="选项按钮展示文字")
    description: str | None = Field(default=None, description="选项详细说明")
    variant: Literal["default", "primary", "danger"] = Field(
        default="default", description="按钮视觉样式"
    )


class SendMessagePayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: VocalMessageType = Field(default=VocalMessageType.TEXT, description="投递类型")
    content: str | None = Field(default=None, description="正式文本气泡内容")
    options: list[WidgetOption] | None = Field(
        default=None, description="交互选项列表（1-6项，widget必填）"
    )
    secret_key: str | None = Field(
        default=None, description="凭证标识键名（secret_request必填）"
    )
    reply_to_id: str | None = Field(default=None, description="关联的上下文消息ID")

    @model_validator(mode="after")
    def validate_payload_semantics(self) -> "SendMessagePayload":
        if self.type == VocalMessageType.TEXT and not self.content:
            raise ValueError("type='text' 时 content 字段不能为空")
        if self.type == VocalMessageType.WIDGET:
            if not self.options or len(self.options) < 1 or len(self.options) > 6:
                raise ValueError("type='widget' 时 options 必须包含 1 到 6 个选项")
        if self.type == VocalMessageType.SECRET_REQUEST and not self.secret_key:
            raise ValueError("type='secret_request' 时 secret_key 字段不能为空")
        return self


class DeliveryReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    message_id: str
    delivered_at_ms: int
    vocal_type: VocalMessageType
    is_terminal_for_turn: bool = False
    requires_user_action: bool = False
```

```python
# lca/contracts/models/vocal/__init__.py
from lca.contracts.models.vocal.models import (
    DeliveryReceipt,
    SendMessagePayload,
    VocalMessageType,
    VocalMode,
    WidgetOption,
)

__all__ = (
    "DeliveryReceipt",
    "SendMessagePayload",
    "VocalMessageType",
    "VocalMode",
    "WidgetOption",
)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/contracts/vocal/test_vocal_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/contracts/models/vocal/ tests/contracts/vocal/
git commit -m "feat(contracts): add vocal mode and message payload models"
```

---

### Task 2: 端口契约与策略接口 (Protocols & Strategy Interface)

**Files:**
- Create: `lca/contracts/protocols/vocal/protocol.py`
- Create: `lca/contracts/protocols/vocal/__init__.py`
- Test: `tests/contracts/vocal/test_vocal_protocol.py`
- Does NOT own: 任何基础设施实现（AP-01）
- Invariants to test: `VocalGateProtocol` 与 `VocalStrategy` 协议签名健全性（AP-02）

**Step 1: Write the failing test**

```python
# tests/contracts/vocal/test_vocal_protocol.py
from typing import runtime_checkable
from lca.contracts.protocols.vocal.protocol import VocalGateProtocol, VocalStrategy


def test_protocols_runtime_checkable():
    assert hasattr(VocalGateProtocol, "deliver")
    assert hasattr(VocalGateProtocol, "handle_text_chunk")
    assert hasattr(VocalStrategy, "mode")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/contracts/vocal/test_vocal_protocol.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# lca/contracts/protocols/vocal/protocol.py
from typing import Protocol, runtime_checkable
from lca.contracts.models.vocal.models import DeliveryReceipt, SendMessagePayload, VocalMode


@runtime_checkable
class VocalGateProtocol(Protocol):
    def handle_text_chunk(self, chunk: str) -> None:
        """处理模型常规输出 Token / 文本。"""
        ...

    def deliver(self, payload: SendMessagePayload) -> DeliveryReceipt:
        """正式向对外可见声带投递消息。"""
        ...

    def is_awaiting_widget(self) -> bool:
        """当前轮次是否正等待 Widget 用户选择。"""
        ...


@runtime_checkable
class VocalStrategy(Protocol):
    @property
    def mode(self) -> VocalMode:
        ...

    def create_gate(self, operation_id: str, wake_source: str = "user_input") -> VocalGateProtocol:
        ...
```

```python
# lca/contracts/protocols/vocal/__init__.py
from lca.contracts.protocols.vocal.protocol import VocalGateProtocol, VocalStrategy

__all__ = ("VocalGateProtocol", "VocalStrategy")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/contracts/vocal/test_vocal_protocol.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/contracts/protocols/vocal/ tests/contracts/vocal/
git commit -m "feat(contracts): define vocal gate and strategy protocols"
```

---

### Task 3: 经典直通策略与门控声带拦截器 (DirectVoiceStrategy & GatedVocalGate)

**Files:**
- Create: `lca/infrastructure/vocal/exceptions.py`
- Create: `lca/infrastructure/vocal/gate.py`
- Create: `lca/infrastructure/vocal/strategy.py`
- Create: `lca/infrastructure/vocal/__init__.py`
- Test: `tests/infrastructure/vocal/test_vocal_gate_isolation.py`
- Does NOT own: 修改原有 agent_stream_event 数据链路（AP-01）
- Invariants to test:
  - `INV-VOCAL-01`: Gated 模式下纯文本截流至 `scratchpad`，对外可见气泡数为 0；
  - `INV-VOCAL-02`: Direct 模式下普通文本直接发射对外，100% 保持既有行为（AP-02）。

**Step 1: Write the failing test**

```python
# tests/infrastructure/vocal/test_vocal_gate_isolation.py
from lca.contracts.models.vocal.models import SendMessagePayload, VocalMessageType, VocalMode
from lca.infrastructure.vocal.strategy import DirectVoiceStrategy, GatedVoiceStrategy


def test_direct_voice_strategy_emits_text_directly():
    strategy = DirectVoiceStrategy()
    assert strategy.mode == VocalMode.DIRECT
    gate = strategy.create_gate("op_1")

    gate.handle_text_chunk("Hello World")
    visible = gate.get_visible_outputs()
    assert len(visible) == 1
    assert visible[0]["content"] == "Hello World"
    assert gate.get_scratchpad() == ""


def test_gated_voice_strategy_mutes_text_into_scratchpad():
    strategy = GatedVoiceStrategy()
    assert strategy.mode == VocalMode.GATED
    gate = strategy.create_gate("op_2")

    gate.handle_text_chunk("Thinking about solution...")
    assert len(gate.get_visible_outputs()) == 0  # 严禁对外直接吐泡泡！
    assert "Thinking about solution..." in gate.get_scratchpad()

    # 只有通过 deliver 才能对外产生可见消息
    payload = SendMessagePayload(type=VocalMessageType.TEXT, content="Official Answer")
    receipt = gate.deliver(payload)
    assert receipt.vocal_type == VocalMessageType.TEXT
    visible = gate.get_visible_outputs()
    assert len(visible) == 1
    assert visible[0]["content"] == "Official Answer"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/infrastructure/vocal/test_vocal_gate_isolation.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# lca/infrastructure/vocal/exceptions.py
class VocalGateError(Exception):
    """声带硬闸基础异常。"""


class VocalGateAlreadyBlockedError(VocalGateError):
    """已挂起等待 Widget，同轮次严禁二次发声异常。"""


class UndeliveredTurnError(VocalGateError):
    """轮次收敛时未向用户交付实质性结果异常。"""
```

```python
# lca/infrastructure/vocal/gate.py
import time
import uuid
from typing import Any
from lca.contracts.models.vocal.models import (
    DeliveryReceipt,
    SendMessagePayload,
    VocalMessageType,
    VocalMode,
)
from lca.contracts.protocols.vocal.protocol import VocalGateProtocol
from lca.infrastructure.vocal.exceptions import VocalGateAlreadyBlockedError


class DirectVocalGate(VocalGateProtocol):
    def __init__(self, operation_id: str) -> None:
        self.operation_id = operation_id
        self._visible: list[dict[str, Any]] = []

    def handle_text_chunk(self, chunk: str) -> None:
        self._visible.append({"type": "text", "content": chunk})

    def deliver(self, payload: SendMessagePayload) -> DeliveryReceipt:
        self._visible.append({"type": payload.type.value, "content": payload.content})
        return DeliveryReceipt(
            message_id=str(uuid.uuid4()),
            delivered_at_ms=int(time.time() * 1000),
            vocal_type=payload.type,
            is_terminal_for_turn=False,
        )

    def is_awaiting_widget(self) -> bool:
        return False

    def get_visible_outputs(self) -> list[dict[str, Any]]:
        return list(self._visible)

    def get_scratchpad(self) -> str:
        return ""


class GatedVocalGate(VocalGateProtocol):
    def __init__(self, operation_id: str, wake_source: str = "user_input") -> None:
        self.operation_id = operation_id
        self.wake_source = wake_source
        self._scratchpad: list[str] = []
        self._visible: list[dict[str, Any]] = []
        self._awaiting_widget: bool = False
        self.has_acked: bool = False
        self.delivered_count: int = 0

    def handle_text_chunk(self, chunk: str) -> None:
        # INV-VOCAL-01: 纯文本内省截流
        self._scratchpad.append(chunk)

    def deliver(self, payload: SendMessagePayload) -> DeliveryReceipt:
        if self._awaiting_widget:
            raise VocalGateAlreadyBlockedError("当前轮次已发送 Widget 停等中，禁止同轮次二次发送消息。")

        msg_id = str(uuid.uuid4())
        now_ms = int(time.time() * 1000)
        is_terminal = False

        if payload.type == VocalMessageType.WIDGET:
            self._awaiting_widget = True
            is_terminal = True
            self._visible.append({
                "type": "widget",
                "message_id": msg_id,
                "content": payload.content,
                "options": [opt.model_dump() for opt in (payload.options or [])],
            })
        else:
            self._visible.append({
                "type": payload.type.value,
                "message_id": msg_id,
                "content": payload.content,
            })

        self.delivered_count += 1
        self.has_acked = True

        return DeliveryReceipt(
            message_id=msg_id,
            delivered_at_ms=now_ms,
            vocal_type=payload.type,
            is_terminal_for_turn=is_terminal,
            requires_user_action=is_terminal,
        )

    def is_awaiting_widget(self) -> bool:
        return self._awaiting_widget

    def get_visible_outputs(self) -> list[dict[str, Any]]:
        return list(self._visible)

    def get_scratchpad(self) -> str:
        return "".join(self._scratchpad)
```

```python
# lca/infrastructure/vocal/strategy.py
from lca.contracts.models.vocal.models import VocalMode
from lca.contracts.protocols.vocal.protocol import VocalGateProtocol, VocalStrategy
from lca.infrastructure.vocal.gate import DirectVocalGate, GatedVocalGate


class DirectVoiceStrategy(VocalStrategy):
    @property
    def mode(self) -> VocalMode:
        return VocalMode.DIRECT

    def create_gate(self, operation_id: str, wake_source: str = "user_input") -> VocalGateProtocol:
        return DirectVocalGate(operation_id)


class GatedVoiceStrategy(VocalStrategy):
    @property
    def mode(self) -> VocalMode:
        return VocalMode.GATED

    def create_gate(self, operation_id: str, wake_source: str = "user_input") -> VocalGateProtocol:
        return GatedVocalGate(operation_id, wake_source=wake_source)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/infrastructure/vocal/test_vocal_gate_isolation.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/vocal/ tests/infrastructure/vocal/
git commit -m "feat(infrastructure): implement direct and gated vocal gates"
```

---

### Task 4: SendMessage 原语工具与 Widget 停等状态机 (SendMessageTool & TurnVocalState)

**Files:**
- Create: `lca/infrastructure/vocal/tool.py`
- Test: `tests/infrastructure/vocal/test_send_message_tool.py`
- Does NOT own: 改变非声带通用工具逻辑（AP-01）
- Invariants to test:
  - `INV-VOCAL-03`: Widget 投递后返回 `is_terminal_for_turn=True`，同轮次二次发送直接抛 `VocalGateAlreadyBlockedError`（AP-02）。

**Step 1: Write the failing test**

```python
# tests/infrastructure/vocal/test_send_message_tool.py
import pytest
from lca.contracts.models.vocal.models import SendMessagePayload, VocalMessageType, WidgetOption
from lca.infrastructure.vocal.exceptions import VocalGateAlreadyBlockedError
from lca.infrastructure.vocal.gate import GatedVocalGate
from lca.infrastructure.vocal.tool import SendMessageTool


def test_send_message_tool_text_delivery():
    gate = GatedVocalGate("op_1")
    tool = SendMessageTool(gate)

    res = tool.execute(type="text", content="Hello via tool")
    assert res["status"] == "delivered"
    assert res["vocal_type"] == "text"
    assert res["is_terminal_for_turn"] is False
    assert len(gate.get_visible_outputs()) == 1


def test_send_message_tool_widget_blocks_further_sends():
    gate = GatedVocalGate("op_2")
    tool = SendMessageTool(gate)

    options = [{"id": "y", "label": "Yes"}, {"id": "n", "label": "No"}]
    res = tool.execute(type="widget", content="Are you sure?", options=options)
    assert res["is_terminal_for_turn"] is True
    assert gate.is_awaiting_widget() is True

    # INV-VOCAL-03: 二次发送必阻断
    with pytest.raises(VocalGateAlreadyBlockedError):
        tool.execute(type="text", content="Should be blocked")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/infrastructure/vocal/test_send_message_tool.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# lca/infrastructure/vocal/tool.py
from typing import Any
from lca.contracts.models.vocal.models import SendMessagePayload, VocalMessageType, WidgetOption
from lca.contracts.protocols.vocal.protocol import VocalGateProtocol


class SendMessageTool:
    name: str = "send_message"
    description: str = (
        "向用户对外唯一声道发射正式消息。在门控模式下，大模型普通内省文本用户不可见，"
        "必须调用此工具交付气泡或选项卡。支持类型：text（普通气泡）、widget（选项卡停等）、secret_request（敏感凭证输入）。"
    )

    def __init__(self, gate: VocalGateProtocol) -> None:
        self._gate = gate

    def execute(
        self,
        type: str = "text",
        content: str | None = None,
        options: list[dict[str, Any]] | None = None,
        secret_key: str | None = None,
        reply_to_id: str | None = None,
    ) -> dict[str, Any]:
        parsed_options = [WidgetOption(**opt) for opt in options] if options else None
        payload = SendMessagePayload(
            type=VocalMessageType(type),
            content=content,
            options=parsed_options,
            secret_key=secret_key,
            reply_to_id=reply_to_id,
        )
        receipt = self._gate.deliver(payload)
        return {
            "status": "delivered",
            "message_id": receipt.message_id,
            "vocal_type": receipt.vocal_type.value,
            "is_terminal_for_turn": receipt.is_terminal_for_turn,
            "requires_user_action": receipt.requires_user_action,
        }
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/infrastructure/vocal/test_send_message_tool.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/vocal/tool.py tests/infrastructure/vocal/test_send_message_tool.py
git commit -m "feat(infrastructure): implement send_message tool with widget hold"
```

---

### Task 5: Settle 交付核验硬闸与例程沉默门禁 (SettleGuard)

**Files:**
- Create: `lca/infrastructure/vocal/settle_guard.py`
- Test: `tests/infrastructure/vocal/test_vocal_settle_guard.py`
- Does NOT own: 篡改 Session 事实持久化日志（AP-01）
- Invariants to test:
  - `INV-VOCAL-04`: 人类发起的轮次未交付时必拦截抛出 `UndeliveredTurnError`；
  - `INV-VOCAL-06`: 唤醒源为 `routine` 时允许 0 交付收敛，保持沉默（AP-02）。

**Step 1: Write the failing test**

```python
# tests/infrastructure/vocal/test_vocal_settle_guard.py
import pytest
from lca.contracts.models.vocal.models import SendMessagePayload, VocalMessageType
from lca.infrastructure.vocal.exceptions import UndeliveredTurnError
from lca.infrastructure.vocal.gate import GatedVocalGate
from lca.infrastructure.vocal.settle_guard import VocalSettleGuard


def test_settle_guard_blocks_zero_delivery_for_user_input():
    gate = GatedVocalGate("op_1", wake_source="user_input")
    guard = VocalSettleGuard(gate)

    # 只有普通内省文本，没有调用 send_message
    gate.handle_text_chunk("Done some work internally.")
    with pytest.raises(UndeliveredTurnError):
        guard.validate_turn_settle()


def test_settle_guard_passes_when_message_delivered():
    gate = GatedVocalGate("op_2", wake_source="user_input")
    guard = VocalSettleGuard(gate)

    gate.deliver(SendMessagePayload(type=VocalMessageType.TEXT, content="Final answer delivered"))
    assert guard.validate_turn_settle() is True


def test_settle_guard_allows_silence_for_routine():
    # INV-VOCAL-06: 例程唤醒下无变化允许沉默收敛
    gate = GatedVocalGate("op_3", wake_source="routine")
    guard = VocalSettleGuard(gate)

    gate.handle_text_chunk("No changes detected in routine check.")
    assert guard.validate_turn_settle() is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/infrastructure/vocal/test_vocal_settle_guard.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# lca/infrastructure/vocal/settle_guard.py
from lca.contracts.protocols.vocal.protocol import VocalGateProtocol
from lca.infrastructure.vocal.exceptions import UndeliveredTurnError
from lca.infrastructure.vocal.gate import GatedVocalGate


class VocalSettleGuard:
    def __init__(self, gate: VocalGateProtocol) -> None:
        self._gate = gate

    def validate_turn_settle(self) -> bool:
        if not isinstance(self._gate, GatedVocalGate):
            return True

        # INV-VOCAL-06: 允许例程沉默
        if self._gate.wake_source == "routine":
            return True

        # INV-VOCAL-04: 用户发起轮次必须有交付
        if self._gate.delivered_count == 0:
            raise UndeliveredTurnError(
                f"轮次收敛失败：唤醒源为 '{self._gate.wake_source}'，"
                f"但本轮未通过 send_message 向用户交付任何实质性结果（Ack≠Delivery 不变量违背）。"
            )
        return True
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/infrastructure/vocal/test_vocal_settle_guard.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/vocal/settle_guard.py tests/infrastructure/vocal/test_vocal_settle_guard.py
git commit -m "feat(infrastructure): implement vocal settle guard with routine silence support"
```

---

### Task 6: 策略工厂与全链路场景集成验证 (VocalStrategyFactory & E2E Scenario)

**Files:**
- Create: `lca/application/vocal/factory.py`
- Create: `lca/application/vocal/__init__.py`
- Create: `tests/scenario/vocal/test_gated_conversation_e2e.py`
- Does NOT own: 任何破坏旧有测试或全局配置的行为（AP-01）
- Invariants to test: 完整真实端到端模拟（用户提问 -> 承接 Ack 气泡 -> 工具调用 -> 交付 气泡 -> 结算），以及经典模式默认行为完全一致（AP-02）。

**Step 1: Write the failing test**

```python
# tests/scenario/vocal/test_gated_conversation_e2e.py
from lca.application.vocal.factory import VocalStrategyFactory
from lca.contracts.models.vocal.models import VocalMode
from lca.infrastructure.vocal.gate import GatedVocalGate
from lca.infrastructure.vocal.settle_guard import VocalSettleGuard
from lca.infrastructure.vocal.tool import SendMessageTool


def test_full_gated_conversation_flow_ack_then_deliver():
    factory = VocalStrategyFactory()
    strategy = factory.resolve_strategy(vocal_mode="gated")
    assert strategy.mode == VocalMode.GATED

    gate = strategy.create_gate(operation_id="run_e2e_1", wake_source="user_input")
    assert isinstance(gate, GatedVocalGate)
    tool = SendMessageTool(gate)
    guard = VocalSettleGuard(gate)

    # 1. 思考过程（被截流进 scratchpad）
    gate.handle_text_chunk("Let me read the system logs first...")
    assert len(gate.get_visible_outputs()) == 0

    # 2. Reply-first 承接气泡
    tool.execute(type="text", content="正在为你排查系统日志，请稍候...")
    assert len(gate.get_visible_outputs()) == 1
    assert gate.has_acked is True

    # 3. 模拟耗时工具排查完毕后的正式交付
    gate.handle_text_chunk("Log analysis finished, found root cause in connection pool.")
    tool.execute(type="text", content="排查完成，根因为连接池耗尽，已自动扩容。")
    assert len(gate.get_visible_outputs()) == 2

    # 4. Settle 结算收敛成功
    assert guard.validate_turn_settle() is True


def test_default_is_direct_strategy():
    factory = VocalStrategyFactory()
    # 默认零配置走经典直连模式，确保原有体验零回归
    strategy = factory.resolve_strategy(vocal_mode=None)
    assert strategy.mode == VocalMode.DIRECT
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/scenario/vocal/test_gated_conversation_e2e.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# lca/application/vocal/factory.py
from lca.contracts.models.vocal.models import VocalMode
from lca.contracts.protocols.vocal.protocol import VocalStrategy
from lca.infrastructure.vocal.strategy import DirectVoiceStrategy, GatedVoiceStrategy


class VocalStrategyFactory:
    def __init__(self) -> None:
        self._direct = DirectVoiceStrategy()
        self._gated = GatedVoiceStrategy()

    def resolve_strategy(self, vocal_mode: str | VocalMode | None = None) -> VocalStrategy:
        if vocal_mode is None:
            return self._direct
        normalized = str(vocal_mode).lower().strip()
        if normalized == VocalMode.GATED.value:
            return self._gated
        return self._direct
```

```python
# lca/application/vocal/__init__.py
from lca.application.vocal.factory import VocalStrategyFactory

__all__ = ("VocalStrategyFactory",)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/scenario/vocal/test_gated_conversation_e2e.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/application/vocal/ tests/scenario/vocal/
git commit -m "feat(application): implement vocal strategy factory with e2e scenario tests"
```

---

### Task 7: 全量回归、代码门禁与架构守卫验证 (Regression & Hygiene)

**Files:**
- Test: 全量新增与关联单元测试
- Does NOT own: 任何破坏性变更（AP-01）
- Invariants to test: 门禁与代码风格全部通过

**Step 1: Run pytest across all vocal tests**
Run: `pytest tests/contracts/vocal/ tests/infrastructure/vocal/ tests/scenario/vocal/ -v`
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
git commit -m "docs(plans): record gated vocal runtime tasks in task.md"
```
