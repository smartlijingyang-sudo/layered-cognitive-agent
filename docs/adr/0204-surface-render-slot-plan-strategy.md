# ADR-0204 — SurfaceRender WireContract：模型可见消息的强类型契约落地

## 状态

**Accepted** (2026-09-08)。P0 实施进行中。

**触发**: run_20951da435a6 — 模型陷入 readFile 重复 3 次循环, ToolLoopBreakerGate 强制收口, 任务失败。debug 定位: assistant 消息从 conversation history 中消失。

**关联 ADR**:
- **核心落地** [ADR-0205](0205-wire-contract-as-plugin-seam.md) — WireContract 元机制 (本 ADR 是其 P0 第 1 应用域)
- **延伸** [ADR-0185](0185-model-visible-event-bus-alignment.md) (model-visible 走 ADR-0183 统一 bus)
- **补全** [ADR-0201](0201-tool-result-prompt-closure.md) (tool_result 写面闭环)
- **衔接** [ADR-0193](0193-session-projection-fabric-model-visible.md) — ModelVisibleUnit.wire_view() 第 4 步
- **借鉴** [ADR-0066](0066-declarative-atomic-control-plugins.md) (Slot 范式)
- **借鉴** [ADR-0075](0075-declarative-phase-graph-and-minimal-trusted-kernel.md) (Plan 范式)
- **借鉴** [ADR-0197](0197-guard-stack-hermes-dsh-convergence.md) (Strategy 范式)

**配套 Note**: [`docs/notes/proposed/seam/2026-09-08-surface-render-slot-plan-strategy.md`](../notes/proposed/seam/2026-09-08-surface-render-slot-plan-strategy.md) (debug 证据链)。

---

## 0. 决策摘要

模型可见的对话历史是 agent run 的唯一真值视图, 必须能从事实链忠实重建。但当前 `derive_event_message` 用 if/elif 硬编码 3 种 surface 类型, 写路径同样散落在 5 个文件, 字段名不一致, `assistant_content=""` 时整条事件消失。**bug 根因是整个 model-visible 渲染层缺一套「内部状态 ↔ 外部协议」的强类型契约 + 显式 dispatch + 静态拓扑机制**。

**终态一句话**: 把 surface render 收敛为 WireContract 第 1 个应用域 — 写端用 `OpenAIAssistantMessage.construct(...)` 强类型构造, 读端走 `ModelVisibleUnit.wire_view(event)` 零分支, transport 走 `WireTransport` 派发, plugin 通过 Manifest `wire.contract.provides` 扩展。

```text
                        surface_render.yaml (YAML → WireRegistry)
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│ contracts/wire/contracts/model_openai.py                            │
│   OpenAIUserMessage / OpenAIAssistantMessage / OpenAIToolMessage    │
│   (Pydantic frozen, extra="forbid")                                 │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼ WireRegistry.get()
┌─────────────────────────────────────────────────────────────────────┐
│ WireContract Protocol (extract / validate / transport_keys)         │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   写端 (Self-Closing)    读端 (零分支)        Transport
   OpenAIAssistantMessage unit.wire_view()     WireTransport
   .construct(content,    → registry.get()     .render(msg)
   tool_calls)              .extract(event)    → chunk
```

---

## 1. 第一性原理

### 1.1 真正发生的事

一个 agent run 中, 模型与系统的对话链路只有两种状态转换:

```
LLM 请求 (prompt 视图)  ─→  LLM 响应 (assistant content + tool_calls)
       ▲                              │
       │                              ▼
       └────  tool 结果 (tool_call_id + content)  ←─────┘
```

**模型可见的对话历史** 是这条链路的唯一真值视图, 必须满足:

1. **完整性**: 每次 LLM 调用所看到的全部消息都能从事实链重建
2. **顺序性**: 严格按 OpenAI 协议 `user → assistant(tool_calls) → tool(result) → assistant → ...` 顺序
3. **闭合性**: assistant 消息必须包含 tool_calls (若有), tool 消息必须用对应 tool_call_id 关联

### 1.2 当前架构的 5 个断裂点 (来自 run_20951da435a6 实证)

| # | 断裂点 | 文件:行 | 现象 |
|---|---|---|---|
| ① | 写端 payload 形状 | `hook.py:354-368` | 产 `{assistant_content, tool_calls}` 平铺, 无 `message` 字段 |
| ② | 双写路径竞争 | `lifecycle_emit.py:159-177` + `hook.py:354` | `_emit_lifecycle_post → complete_model` 在 `if text:` 守卫下跳过 tool_call-only 响应 |
| ③ | Fold 识别 | `fold.py:467` | `SURFACE_ASSISTANT_TYPE = "spine.llm.request.header.assistant"` 正确匹配 — 无问题 |
| ④ | 读端投影 | `messages.py:32-66` | `derive_event_message` 读 `data["message"]` 或 `data["content"]`, 找不到 `assistant_content`, 返回 None |
| ⑤ | Transport 翻译 | `event_translator.py:299-311` | `_spine_llm_header_assistant` 在 `assistant_content=""` 时 return None, 完全忽略 `tool_calls` |

### 1.3 同源根因 (ADR-0205 §1 同步诊断)

5 个断裂点同源: **wire shape 散落 5 文件 + dispatch 散落 5 处 + silent drop + 字段名自创**。

修复 = 让 surface render 走 WireContract 元机制。

---

## 2. 设计原则:WiredFact 收口 view

`ModelVisibleUnit` 当前有 `init / apply / view` 3 步。本 ADR 增加**第 4 步 `wire_view`**:

```python
class ModelVisibleUnit(ProjectionUnit):
    def init(self) -> None: ...
    def apply(self, event) -> None: ...
    def view(self) -> list[dict]: ...                  # 现有 model_visible_messages
    def wire_view(self, event) -> OpenAIMessage | None: ...  # 新增, 强类型 wire
```

`wire_view` 内部委托 `WireRegistry.get(contract_key).extract(event_data)`。

**关键约束**:
- `view` 仍是 dict 返回, 兼容现有 consumer
- `wire_view` 强类型返回, 新 consumer 走 wire contract
- 两条路径可独立调用, 不破坏 `I-MV-PROJ-*` 不变量

---

## 3. 架构设计

### 3.1 WireContract 骨架 (Pydantic frozen)

新增 `lca_kernel/contracts/wire/contracts/model_openai.py`:

```python
from typing import Literal, Any
from pydantic import BaseModel, ConfigDict


class WireContractBase(BaseModel):
    """所有 WireContract 的基类 — frozen + extra=forbid, 字段漂移 fail-loud"""
    model_config = ConfigDict(frozen=True, extra="forbid")


class OpenAIFunction(WireContractBase):
    name: str
    arguments: str  # JSON 序列化字符串


class OpenAIToolCall(WireContractBase):
    id: str
    type: Literal["function"] = "function"
    function: OpenAIFunction


class OpenAIUserMessage(WireContractBase):
    role: Literal["user"] = "user"
    content: str | list[dict[str, Any]]


class OpenAIAssistantMessage(WireContractBase):
    role: Literal["assistant"] = "assistant"
    content: str | None = ""
    tool_calls: list[OpenAIToolCall] | None = None
    refusal: str | None = None


class OpenAIToolMessage(WireContractBase):
    role: Literal["tool"] = "tool"
    content: str
    tool_call_id: str
```

### 3.2 WireContract Protocol + Registry

新增 `lca_kernel/contracts/wire/contract.py` 和 `registry.py`:

```python
from abc import ABC, abstractmethod
from typing import Any, Mapping, Type


class WireContract(ABC):
    """Wire shape 契约基类 — Pydantic frozen subclass"""

    @abstractmethod
    def extract(self, event_data: Mapping[str, Any]) -> WireContractBase | None:
        """从事件数据构造 Contract 实例, 字段缺失或类型错 → None + 写 violation"""
        ...

    @abstractmethod
    def transport_keys(self) -> tuple[str, ...]:
        """声明支持的 transport (sse.chunk / openai.wire / db.row)"""
        ...


class OpenAIAssistantContract(WireContract):
    def extract(self, event_data: Mapping[str, Any]) -> OpenAIAssistantMessage | None:
        msg = event_data.get("message")
        if not isinstance(msg, Mapping):
            return None
        try:
            return OpenAIAssistantMessage.model_validate(msg)
        except ValidationError as e:
            write_violation_event("openai.assistant", e)
            return None

    def transport_keys(self) -> tuple[str, ...]:
        return ("sse.chunk", "openai.wire")


class WireRegistry:
    """Profile-scoped contract registry. 不允许 process global."""

    def __init__(self):
        self._contracts: dict[str, WireContract] = {}
        self._transports: dict[str, WireTransport] = {}

    def register(self, key: str, contract: WireContract) -> None:
        if key in self._contracts:
            raise ValueError(f"contract {key} already registered")
        self._contracts[key] = contract

    def get(self, key: str) -> WireContract:
        if key not in self._contracts:
            raise WireContractRegistryMiss(key)
        return self._contracts[key]

    def get_transport(self, key: str) -> WireTransport:
        if key not in self._transports:
            raise WireContractRegistryMiss(f"transport:{key}")
        return self._transports[key]


class WireContractRegistryMiss(KeyError):
    """Registry miss — plugin 未声明, fail-loud"""


def write_violation_event(contract_key: str, exc: ValidationError) -> None:
    """写 wire.contract.violation.v1 spine 事件, 不阻塞 conversation"""
    session.append(FactPayload(
        category="wire.contract.violation.v1",
        producer="contracts.wire",
        data={"contract_key": contract_key, "errors": exc.errors()},
        timestamp=now(),
    ))
```

### 3.3 写端集成:`capture_post_llm` Self-Closing Message

`lca/plugins/events/hooks/model_visible/hook.py:354-368` 改造:

```python
from lca_kernel.contracts.wire.contracts.model_openai import OpenAIAssistantMessage, OpenAIToolCall


def _build_assistant_message(content: str, tool_calls: tuple) -> OpenAIAssistantMessage:
    """强类型构造 OpenAI assistant message — 写端自闭合"""
    return OpenAIAssistantMessage.construct(
        content=content or "",
        tool_calls=[
            OpenAIToolCall.construct(
                id=getattr(tc, "call_id", "") or tc.get("id", ""),
                function=OpenAIFunction.construct(
                    name=getattr(tc, "tool_name", "") or tc.get("name", ""),
                    arguments=json.dumps(
                        getattr(tc, "arguments", {}) or tc.get("arguments", {}),
                        ensure_ascii=False,
                    ),
                ),
            ) for tc in tool_calls
        ] or None,
    )


# 在 capture_post_llm 中
message = _build_assistant_message(assistant_content, tool_calls)
payload_obj = SpineLlmRequestHeaderAssistantPayload(
    message=message.model_dump(),  # 唯一 SSOT
    header_digest=digest,
)
```

**关键:删除平铺字段 `assistant_content` / `tool_calls`** (同 PR, 零中间态)。

### 3.4 双路径合并 (Phase 5)

`lca/infrastructure/session/emit/lifecycle_emit.py:159-177` 改造:

- **保留** `capture_post_llm` 作为唯一 surface 写入路径
- **改写** `complete_model` 不再写 surface, 只写 catalog (`assistant.responded.v1`)
- **测试** 架构不变量 MV-UNICITY-1: assistant surface 事件唯一来源 = `capture_post_llm`

### 3.5 读端零分支

`lca/plugins/session/runtime/messages/messages.py:32-66` 改造:

```python
def derive_event_message(event):
    """读端零分支 — 全部经 WireRegistry"""
    unit = ModelVisibleUnitRegistry.resolve(event.session)
    msg = unit.wire_view(event)  # OpenAIMessage | None
    return msg.model_dump() if msg else None
```

**删除 30 行 if/elif 分支** (同 PR)。

### 3.6 Transport 收口 (Phase 7)

`lca/application/runtime/coordinator/event_translator.py:299-311` 改造:

```python
_TRANSPORT_TABLE: dict[str, Callable[[WireContractBase], dict | None]] = {
    "openai.user": _transport_user_message,
    "openai.assistant": _transport_assistant_message,
    "openai.tool": _transport_tool_message,
}


def _spine_llm_header_assistant(e):
    unit = ModelVisibleUnitRegistry.resolve(e.session)
    msg = unit.wire_view(e)
    if msg is None:
        return None
    transport = WireTransportRegistry.get("sse.chunk")
    return transport.render(msg)
```

**删除所有 `_spine_xxx` 各自硬编码** (同 PR)。

---

## 4. Manifest plugin 声明 (Phase 8)

样例 `lca/plugins/model/anthropic_claude/plugin.yaml`:

```yaml
id: model.contract.anthropic_claude
$module: lca.plugins.model.anthropic_claude
capabilities:
  provides:
    - wire.contract.anthropic_assistant:
        base: openai.assistant
        extra_fields:
          cache_control: { type: "ephemeral" }
        transport_keys: [sse.chunk, anthropic.wire]
        activation:
          when: model.family == "claude"
  requires:
    - wire.contract.openai_assistant
  effects: []
  failure_mode: degrade
  authority: [wire.contract.read]
```

**Resolve 校验**:
- `base: openai.assistant` 已注册
- `extra_fields.cache_control` 与 base schema 不冲突 (Pydantic diff)
- `overrides` 形成 DAG 无环
- `transport_keys` 在 WireTransportRegistry

---

## 5. 不变量 (架构测试守护, fail-loud)

| ID | 内容 | 测试 |
|---|---|---|
| **MV-SLOT-1** | 每个 surface type 在 yaml 唯一 | `test_surface_render_ssot_unique_type` |
| **MV-SLOT-2** | 每个 OpenAI*Message Contract 都注册到 Registry | `test_wire_contract_registry_complete` |
| **MV-SHAPE-1** | 写端 assistant event 必含 `message` 字段且 `role=assistant` | `test_assistant_message_shape` |
| **MV-ROUNDTRIP-1** | `unit.wire_view(event)` 对每个 surface event 返回非 None (除非真正空) | `test_wire_view_roundtrip` |
| **MV-TRANSPORT-1** | WireTransport table 覆盖所有 surface slot, 无静默 drop | `test_transport_slot_dispatch` |
| **MV-PARITY-1** | 新 wire 路径对所有测试 fixture 输出 ≡ 旧 if/else 路径 | `test_parity_old_vs_new` |
| **MV-UNICITY-1** | assistant surface 事件唯一来源 = `capture_post_llm` | `test_assistant_surface_unicity` |
| **MV-DICT-1** | 写端不允许 dict 字面量构造 message, 必走 `OpenAI*Message.construct()` | `test_no_dict_payload` |
| **MV-IFELIF-1** | dispatch 入口不允许 if/elif 散落 | `test_no_if_elif_in_dispatch` |
| **WC-3** | plugin overrides 形成 DAG 无环 | `test_wire_contract_dag` |
| **WC-4** | plugin `provides` 必在 Manifest 声明, 无声明 = `UndeclaredInteractionError` | `test_manifest_provides_complete` |

---

## 6. 验证矩阵

```bash
# 阶段 1-9 (P0)
uv run pytest tests/contracts/wire/test_wire_contract_registry.py -v
uv run pytest tests/contracts/wire/test_openai_message_contract.py -v
uv run pytest tests/lca_kernel/events/test_wire_view.py -v
uv run pytest tests/plugins/events/hooks/model_visible/test_assistant_message_shape.py -v
uv run pytest tests/integration/test_assistant_surface_unicity.py -v
uv run pytest tests/lca_kernel/events/test_parity_old_vs_new.py -v
uv run pytest tests/coordinator/test_transport_slot_dispatch.py -v
uv run pytest tests/plugins/model/test_anthropic_claude_plugin.py -v
uv run pytest tests/architecture/test_no_wire_ifelse.py -v
uv run pytest tests/architecture/test_wire_contract_invariants.py -v

# 端到端
LATEST=$(./scripts/lca-ops runs create --user-text "分析这个文件" | jq -r .run_id)
./scripts/lca-ops journal logs -r "$LATEST" -v | grep "role=assistant"
# 预期: 看到 assistant(tool_calls) 消息, 不再陷入重复 readFile
```

---

## 7. delete-when 清单 (零中间态)

| 删除 | delete-when |
|---|---|
| `assistant_content` / `tool_calls` 平铺字段 in `SpineLlmRequestHeaderAssistantPayload` | **同 PR** (PR-4) |
| `complete_model` 双写 surface 分支 in `lifecycle_emit.py:159-177` | **同 PR** (PR-5) |
| `_spine_xxx` 各自硬编码 5 处 in `event_translator.py` | **同 PR** (PR-7) |
| `derive_event_message` if/elif 3 分支 in `messages.py:32-66` | **同 PR** (PR-6) |
| `_SPINE_HANDLERS` dict | **同 PR** (PR-7) |
| 任何 `data["message"]` / `.get("message")` / `if event_type ==` | **同 PR** (PR-9 grep 全清) |
| 任何 `lca_kernel/events/render/` 目录 (若创建) | 不创建 |

---

## 8. 与现有 ADR / Note 关系

| 既有 | 处置 |
|---|---|
| [ADR-0205](0205-wire-contract-as-plugin-seam.md) | **第 1 应用域** — 本 ADR 是其 P0 落地 |
| [ADR-0193](0193-session-projection-fabric-model-visible.md) ModelVisibleUnit | **延伸** — 增加 `wire_view()` 第 4 步 |
| [ADR-0185](0185-model-visible-event-bus-alignment.md) | **延伸** — model-visible 走 ADR-0183 bus |
| [ADR-0201](0201-tool-result-prompt-closure.md) | **补全** — tool_result 走 OpenAIToolMessage Contract |
| [ADR-0066](0066-declarative-atomic-control-plugins.md) ControlSlot | **借鉴** — wire.contract slot 是 ControlSlot 新成员 |
| [ADR-0110](0110-plugin-contract-unification-and-naming-convergence.md) | **衔接** — PluginContract.capabilities 扩展 |
| [ADR-0061](0061-plugin-manifest-resolve-boot.md) | **衔接** — Resolve 校验 WireContract DAG |

---

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| **Pydantic 校验失败阻塞生产路径** | `model_validate` 用 `ValidationError` 捕获并写 `wire.contract.violation.v1` spine event, 不阻塞 conversation |
| **plugin override 链导致 wire shape 不可预测** | Manifest overrides 必填 `base` + `contract_key`, Resolve 检查 `overrides` 形成 DAG, 无环 |
| **ModelVisibleUnit 扩展破坏现有 I-MV-PROJ-*** | `wire_view` 是 view 的扩展, view 仍返回 `model_visible_messages`; wire_view 独立调用 |
| **现有 consumer 不接受强类型返回** | `model_dump()` 出口统一 dict, consumer 不需要改 |
| **WireContract 抽象过重** | Protocol + Registry + Manifest 三件套是 LCA 现有范式 (ADR-0066/0075/0197/0110), 无新原语 |
| **架构改动面大** | 9 PR 阶段切分, 每阶段独立可回滚; PR-1~2 纯加法零回归 |

---

## 10. 效果预期

### 修复前 (本次 debug 现场)

```text
LLM call 1: [user_sys, user_query] → model: "readFile(path)"
LLM call 2: [user_sys, user_query, tool_result_1] → model: "readFile(path)" ← 重复!
LLM call 3: [user_sys, user_query, tool_result_1] → model: "readFile(path)" ← 重复!
→ ToolLoopBreakerGate 强制收口 → 任务失败
```

### 修复后

```text
LLM call 1: [user_sys, user_query] → model: "readFile(path)"
LLM call 2: [user_sys, user_query, assistant(tool_calls), tool_result_1] → model: "分析内容..."
→ 任务正常完成
```

### 机制层面

- ✅ 任何新 wire shape 改 Pydantic 一处, 全栈联动
- ✅ 字段名/形状定义有 SSOT, 写端和读端不再各自维护
- ✅ 架构测试 fail-loud, 错配立即暴露而非静默丢消息
- ✅ 模式可推广到 action / reducer / phase / transport / tool / fact / skill
- ✅ 不重造已有原语 (ControlSlot / PhaseBinding / LoopGuardPolicy / PluginContract), 复用其范式
- ✅ 严格遵循"一处声明, 全栈联动"的扩展性原则
- ✅ **零中间态**: 旧 if/elif / 平铺字段 / 双写路径, 同 PR 全删
