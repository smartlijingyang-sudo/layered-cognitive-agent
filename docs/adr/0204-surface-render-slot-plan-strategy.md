# ADR-0204 — SurfaceRender：模型可见消息的 typed Contract 收口

> **2026-09-08 重写**：将原"WireContract 元机制"提法并入宪法 [ADR-0195 §1.4 信息血统闭合 (C13)](0195-platform-architecture-convergence.md) + §1.5 同型 DAG 视图。本 ADR 现为单点修复 ADR，所有 wire.* / WireRegistry / WireTransport 命名空间已删除，typed Contract 沿用 ADR-0066 §三 ControlSlot IO Contract 范式 + ADR-0110 `capability.contract.provides` slot。原 §1.5 / §1.3 同源根因诊断、ADR-0205 撤回处置见历史 commit。

## 状态

**Accepted — Rewritten 2026-09-08**。P0 实施中。

**触发**：run_20951da435a6 — 模型陷入 readFile 重复 3 次循环，ToolLoopBreakerGate 强制收口，任务失败。debug 定位：assistant 消息从 conversation history 中消失。

**关联 ADR**：
- **核心落地** [ADR-0195 §1.4 / §1.5](0195-platform-architecture-convergence.md) — 信息血统闭合 (C13) + 同型 DAG 视图
- **延伸** [ADR-0066 §三](0066-declarative-atomic-control-plugins.md) — ControlSlot IO Contract 范式（Pydantic frozen，`extra="forbid"`）
- **延伸** [ADR-0110](0110-plugin-contract-unification-and-naming-convergence.md) — `capability.contract.provides` slot（沿用，不新开 key）
- **延伸** [ADR-0185](0185-model-visible-event-bus-alignment.md)（model-visible 走 ADR-0183 统一 bus）
- **补全** [ADR-0201](0201-tool-result-prompt-closure.md)（tool_result 写面闭环）
- **衔接** [ADR-0193](0193-session-projection-fabric-model-visible.md) — `ModelVisibleUnit.view()` 输出闭合校验
- **衔接** [ADR-0194](0194-cognitive-loop-architecture-convergence.md) / [ADR-0195](0195-platform-architecture-convergence.md) — 五平面 + 三时态

**配套 Note**：[`docs/notes/proposed/seam/2026-09-08-surface-render-slot-plan-strategy.md`](../notes/proposed/seam/2026-09-08-surface-render-slot-plan-strategy.md)（debug 证据链）。

---

## 0. 决策摘要

模型可见的对话历史是 agent run 的 V4 观察流投影，必须能从 V5 事实链忠实重建。run_20951da435a6 暴露 5 处断裂：写端 payload 形状散落 5 文件、双写路径在守卫下吞没 tool_call-only 响应、读端 if/elif 散落 3 分支、字段名漂移、transport 翻译时闭合不完整。

**根因**：违反 [ADR-0195 §1.2](0195-platform-architecture-convergence.md) 中"Model-visible = fold 投影，无写"的不变量。Surface render 在 transport 翻译阶段做了本该由 Reducer / fold 完成的闭合（`_spine_xxx` 在 `assistant_content=""` 时 return None，吞没 tool_calls），且跨边界传递未走 typed Contract（C13 D3 转换链断裂）。

**终态一句话**：把 surface render 收敛为 ControlSlot IO Contract 范式（C13 应用域）— 写端用 `OpenAIAssistantMessage.construct(...)` 强类型构造，读端走 `ModelVisibleUnit.view()` 经 typed Contract 闭合校验（V2 → V4 → V5 全程可追溯），plugin 通过 Manifest `capability.contract.provides` 扩展（沿用 ADR-0110）。

```text
                    surface_render.yaml (YAML → typed Contract 词表)
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│ contracts/slot_io/contracts/model_openai.py                         │
│   OpenAIUserMessage / OpenAIAssistantMessage / OpenAIToolMessage    │
│   (Pydantic frozen, extra="forbid")                                 │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼ SlotIORegistry.get() (沿用 ADR-0110 capability contract resolve)
┌─────────────────────────────────────────────────────────────────────┐
│ ControlSlot IO Contract (沿用 ADR-0066 §三 Pydantic frozen 范式)     │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   写端 (Self-Closing)    读端 (零分支)        Transport
   OpenAIAssistantMessage unit.view() 闭合校验  WireTransport
   .construct(content,    V5 fold projection    .render(msg)
   tool_calls)            → typed Contract       → chunk
```

---

## 1. 第一性原理

### 1.1 V2 模型决策轨迹在 V4 / V5 中的闭合要求

一个 agent run 中，模型与系统的对话链路只有两种状态转换：

```text
LLM 请求 (prompt 视图)  ─→  LLM 响应 (assistant content + tool_calls)
       ▲                              │
       │                              ▼
       └────  tool 结果 (tool_call_id + content)  ←─────┘
```

**模型可见的对话历史（V4 观察流投影）** 是这条链路的唯一真值视图，必须满足：

1. **完整性**：每次 LLM 调用所看到的全部消息都能从 V5 事实链重建
2. **顺序性**：严格按 OpenAI 协议 `user → assistant(tool_calls) → tool(result) → assistant → ...` 顺序
3. **闭合性**：assistant 消息必须包含 tool_calls（若有），tool 消息必须用对应 tool_call_id 关联

任一 V2 runtime step（每次 `act` + tool result）的 assistant(message, tool_calls) 与 tool(role="tool", tool_call_id) 必须**全部进入 V5 事实链 + V4 fold projection**，经同一套 typed Contract 收口（C13 D3 转换链完整）。

### 1.2 5 处断裂点（run_20951da435a6 实证）

| # | 断裂点 | 文件:行 | 违反的不变量 |
|---|---|---|---|
| ① | 写端 payload 形状 | `hook.py:354-368` | C13 D1 定义点散落 5 文件 |
| ② | 双写路径 + `if text:` 守卫 | `lifecycle_emit.py:159-177` + `hook.py:354` | C13 D3 V2 step 未进入 V5 |
| ③ | Fold 识别 | `fold.py:467` | 无问题（保留） |
| ④ | 读端投影 if/elif | `messages.py:32-66` | C13 D3 转换链散落 |
| ⑤ | Transport 翻译闭合 | `event_translator.py:299-311` | ADR-0195 §1.2 "Model-visible 无写" |

**修复 = 让 surface render 走 ControlSlot IO Contract 范式（C13）**。

---

## 2. 设计原则：V4 fold projection 收口 view

`ModelVisibleUnit` 当前有 `init / apply / view` 3 步。本 ADR 强化 `view()` 的闭合校验职责：

```python
class ModelVisibleUnit(ProjectionUnit):
    def init(self) -> None: ...
    def apply(self, event) -> None: ...
    def view(self) -> list[dict]:
        """返回 model_visible_messages; 经 typed Contract 闭合校验 (C13)"""
        # 内部按 IO Contract 词表 (OpenAI*Message) 闭合:
        # - assistant(content="") 必含 tool_calls (C13 D3 V2 step 完整)
        # - tool(role="tool") 必有对应 tool_call_id (C13 D3 因果闭合)
        # - 字段名 / 形状由 Pydantic frozen 强制 (C13 D1)
```

**关键约束**：
- `view()` 仍是 dict 返回，兼容现有 consumer
- 闭合校验在 fold 投影阶段统一执行，transport 翻译阶段只读取 `view()` 结果，不再自己拼字段
- 不引入独立的 wire_view / wire_contract 路径

---

## 3. 架构设计

### 3.1 typed Contract 集（Pydantic frozen）

新增 `lca_kernel/contracts/slot_io/contracts/model_openai.py`：

```python
from typing import Literal, Any
from pydantic import BaseModel, ConfigDict


class SlotIOContractBase(BaseModel):
    """ControlSlot IO Contract 基类 — frozen + extra=forbid (C13)"""
    model_config = ConfigDict(frozen=True, extra="forbid")


class OpenAIFunction(SlotIOContractBase):
    name: str
    arguments: str  # JSON 序列化字符串


class OpenAIToolCall(SlotIOContractBase):
    id: str
    type: Literal["function"] = "function"
    function: OpenAIFunction


class OpenAIUserMessage(SlotIOContractBase):
    role: Literal["user"] = "user"
    content: str | list[dict[str, Any]]


class OpenAIAssistantMessage(SlotIOContractBase):
    role: Literal["assistant"] = "assistant"
    content: str | None = ""
    tool_calls: list[OpenAIToolCall] | None = None
    refusal: str | None = None


class OpenAIToolMessage(SlotIOContractBase):
    role: Literal["tool"] = "tool"
    content: str
    tool_call_id: str
```

### 3.2 SlotIO 解析（沿用 ADR-0110 capability contract resolve）

`SlotIORegistry` 不单独存在；typed Contract 通过 ADR-0110 `PluginContract.capability.contract.provides` slot 注册，由 MTK PlanCompiler 编译期 resolve（详见 [ADR-0195 §1.4 守护 (c)](0195-platform-architecture-convergence.md)）。

```python
# 在 plugin manifest 中
# lca/plugins/model/anthropic_claude/plugin.yaml
id: model.contract.anthropic_claude
$module: lca.plugins.model.anthropic_claude
capabilities:
  provides:
    - capability.contract.anthropic_assistant:
        base: openai.assistant
        extra_fields:
          cache_control: { type: "ephemeral" }
        activation:
          when: model.family == "claude"
  requires:
    - capability.contract.openai_assistant
```

**Resolve 校验**：
- `base` Contract 已注册
- `extra_fields` 与 base schema 不冲突（Pydantic diff）
- overrides 形成 DAG 无环
- `UndeclaredInteractionError` 沿用 ADR-0110 / ADR-0066，不新开

### 3.3 写端集成：`capture_post_llm` Self-Closing Message

`lca/plugins/events/hooks/model_visible/hook.py:354-368` 改造：

```python
from lca_kernel.contracts.slot_io.contracts.model_openai import OpenAIAssistantMessage, OpenAIToolCall


def _build_assistant_message(content: str, tool_calls: tuple) -> OpenAIAssistantMessage:
    """强类型构造 OpenAI assistant message — C13 D1 定义点"""
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

**关键：删除平铺字段 `assistant_content` / `tool_calls`**（同 PR，零中间态）。

### 3.4 双路径合并（V2 step → V5 完整闭合）

`lca/infrastructure/session/emit/lifecycle_emit.py:159-177` 改造：

- **保留** `capture_post_llm` 作为唯一 surface 写入路径
- **改写** `complete_model` 不再写 surface，只写 catalog（`assistant.responded.v1`）
- **测试** 架构不变量 MV-UNICITY-1：assistant surface 事件唯一来源 = `capture_post_llm`

### 3.5 读端零分支（V5 fold projection 经 typed Contract 闭合）

`lca/plugins/session/runtime/messages/messages.py:32-66` 改造：

```python
def derive_event_message(event):
    """读端零分支 — 经 ModelVisibleUnit.view() 闭合校验 (C13)"""
    unit = ModelVisibleUnitRegistry.resolve(event.session)
    messages = unit.view()  # V5 fold projection + typed Contract 闭合校验
    return messages[-1] if messages else None
```

**删除 30 行 if/elif 分支**（同 PR）。

### 3.6 Transport 收口（V4 观察流只读 fold）

`lca/application/runtime/coordinator/event_translator.py:299-311` 改造：`_spine_xxx` 各自硬编码 5 处全部删除，改为从 `unit.view()` 读取闭合后的 messages，统一经 `WireTransport.render(msg)` 派发。

**关键**：`_spine_llm_header_assistant` 不再自己拼字段、不再 return None；闭合由 `view()` 完成，transport 只做 wire 编码。

---

## 4. Manifest plugin 声明（沿用 ADR-0110）

```yaml
# lca/plugins/model/anthropic_claude/plugin.yaml
id: model.contract.anthropic_claude
$module: lca.plugins.model.anthropic_claude
capabilities:
  provides:
    - capability.contract.anthropic_assistant:
        base: openai.assistant
        extra_fields:
          cache_control: { type: "ephemeral" }
        activation:
          when: model.family == "claude"
  requires:
    - capability.contract.openai_assistant
  effects: []
  failure_mode: degrade
  authority: [capability.contract.read]
```

**Resolve 校验**（沿用 ADR-0110 + ADR-0066）：
- `base: openai.assistant` 已注册
- `extra_fields.cache_control` 与 base schema 不冲突（Pydantic diff）
- overrides 形成 DAG 无环
- 未声明调用触发 `UndeclaredInteractionError`（沿用）

---

## 5. 不变量（架构测试守护，fail-loud）

| ID | 内容 | 测试 |
|---|---|---|
| **MV-SLOT-1** | 每个 surface type 在 yaml 唯一 | `test_surface_render_ssot_unique_type` |
| **MV-SLOT-2** | 每个 OpenAI\*Message Contract 都注册到 capability registry | `test_slot_io_registry_complete` |
| **MV-SHAPE-1** | 写端 assistant event 必含 `message` 字段且 `role=assistant` | `test_assistant_message_shape` |
| **MV-ROUNDTRIP-1** | `unit.view()` 对每个 surface event 返回非 None（除非真正空） | `test_view_roundtrip` |
| **MV-TRANSPORT-1** | WireTransport 派发表覆盖所有 surface slot，无静默 drop | `test_transport_slot_dispatch` |
| **MV-PARITY-1** | 新 typed Contract 路径对所有测试 fixture 输出 ≡ 旧 if/else 路径 | `test_parity_old_vs_new` |
| **MV-UNICITY-1** | assistant surface 事件唯一来源 = `capture_post_llm` | `test_assistant_surface_unicity` |
| **MV-DICT-1** | 写端不允许 dict 字面量构造 message，必走 `OpenAI\*Message.construct()` | `test_no_dict_payload` |
| **MV-IFELIF-1** | dispatch 入口不允许 if/elif 散落 | `test_no_if_elif_in_dispatch` |
| **C13-DAG-1** | capability.contract overrides 形成 DAG 无环 | `test_capability_contract_dag` |
| **C13-MANIFEST-1** | plugin `provides` 必在 Manifest 声明，无声明 = `UndeclaredInteractionError` | `test_manifest_provides_complete` |
| **C13-PROV-1** | V2 runtime step 的 assistant(tool_calls) 必进入 V5 事实链 + V4 fold projection | `test_v2_step_closed_in_history` |
| **C13-PROV-2** | assistant(content="") 必含 tool_calls；tool 消息必含对应 tool_call_id | `test_assistant_tool_closure` |

---

## 6. 验证矩阵

```bash
# 阶段 1-9 (P0)
uv run pytest tests/contracts/slot_io/test_slot_io_registry.py -v
uv run pytest tests/contracts/slot_io/test_openai_message_contract.py -v
uv run pytest tests/lca_kernel/events/test_view_closure.py -v
uv run pytest tests/plugins/events/hooks/model_visible/test_assistant_message_shape.py -v
uv run pytest tests/integration/test_assistant_surface_unicity.py -v
uv run pytest tests/lca_kernel/events/test_parity_old_vs_new.py -v
uv run pytest tests/coordinator/test_transport_slot_dispatch.py -v
uv run pytest tests/plugins/model/test_anthropic_claude_plugin.py -v
uv run pytest tests/architecture/test_no_slot_io_ifelse.py -v
uv run pytest tests/architecture/test_c13_provenance_closed.py -v

# 端到端
LATEST=$(./scripts/lca-ops runs create --user-text "分析这个文件" | jq -r .run_id)
./scripts/lca-ops journal logs -r "$LATEST" -v | grep "role=assistant"
# 预期: 看到 assistant(tool_calls) 消息, 不再陷入重复 readFile
```

---

## 7. delete-when 清单（零中间态）

| 删除 | delete-when |
|---|---|
| `assistant_content` / `tool_calls` 平铺字段 in `SpineLlmRequestHeaderAssistantPayload` | **同 PR**（PR-4） |
| `complete_model` 双写 surface 分支 in `lifecycle_emit.py:159-177` | **同 PR**（PR-5） |
| `_spine_xxx` 各自硬编码 5 处 in `event_translator.py` | **同 PR**（PR-7） |
| `derive_event_message` if/elif 3 分支 in `messages.py:32-66` | **同 PR**（PR-6） |
| `_SPINE_HANDLERS` dict | **同 PR**（PR-7） |
| 任何 `data["message"]` / `.get("message")` / `if event_type ==` | **同 PR**（PR-9 grep 全清） |
| 任何 `lca_kernel/events/render/` 目录（若创建） | 不创建 |
| `WireContract` / `WireRegistry` / `WireTransport` 类与 `wire.contract.*` 命名空间 | **同 PR**（PR-1 即不存在） |

---

## 8. 与现有 ADR / Note 关系

| 既有 | 处置 |
|---|---|
| [ADR-0195 §1.4](0195-platform-architecture-convergence.md) (C13) / [§1.5](0195-platform-architecture-convergence.md) | **核心落地** — surface render 是 C13 + V2/V4/V5 治理的应用域 |
| [ADR-0205](0205-wire-contract-as-plugin-seam.md) | **撤回** — 并入 ADR-0195 §1.4 / §1.5，不单独存在 |
| [ADR-0066 §三](0066-declarative-atomic-control-plugins.md) | **延伸** — typed Contract 沿用 ControlSlot IO Contract 范式 |
| [ADR-0110](0110-plugin-contract-unification-and-naming-convergence.md) | **衔接** — `capability.contract.provides` slot 沿用 |
| [ADR-0193](0193-session-projection-fabric-model-visible.md) `ModelVisibleUnit` | **延伸** — `view()` 强化闭合校验职责 |
| [ADR-0185](0185-model-visible-event-bus-alignment.md) | **延伸** — model-visible 走 ADR-0183 bus |
| [ADR-0201](0201-tool-result-prompt-closure.md) | **补全** — tool_result 走 OpenAIToolMessage Contract |
| [ADR-0061](0061-plugin-manifest-resolve-boot.md) | **衔接** — Resolve 校验 capability contract DAG |

---

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| Pydantic 校验失败阻塞生产路径 | `model_validate` 用 `ValidationError` 捕获并 fail-loud 写 `slot.io.contract.violation.v1` spine event，不阻塞 conversation（沿用现有 violation 词表，不新开） |
| plugin override 链导致 typed shape 不可预测 | Manifest overrides 必填 `base` + `contract_key`，Resolve 检查 overrides 形成 DAG 无环；静态 lint-imports 扩展为 capability-contract 拓扑 |
| `ModelVisibleUnit.view()` 强化破坏现有 `I-MV-PROJ-*` | view 仍返回 `model_visible_messages`，闭合校验作为内部步骤；consumer 接口不变 |
| 现有 consumer 不接受强类型返回 | `model_dump()` 出口统一 dict，consumer 不需要改 |
| typed Contract 抽象过重 | Pydantic frozen + Manifest provides slot 是 LCA 现有范式（ADR-0066/0110/0195），无新原语 |
| 架构改动面大 | 9 PR 阶段切分，每阶段独立可回滚；PR-1~2 纯加法零回归 |

---

## 10. 效果预期

### 修复前（本次 debug 现场）

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

- ✅ 任何新 typed shape 改 Pydantic 一处，全栈联动
- ✅ 字段名 / 形状定义有 SSOT，写端和读端不再各自维护
- ✅ 架构测试 fail-loud，错配立即暴露而非静默丢消息
- ✅ V2 / V3 / V4 / V5 视图共享同一套 typed Contract 词表（C13）
- ✅ plugin 扩展走 Manifest `capability.contract.provides`，Resolve 拓扑校验
- ✅ **零中间态**：旧 if/elif / 平铺字段 / 双写路径，同 PR 全删

---

## 11. 实施序列

| PR | 标题 | 主要结果 | delete-when / 验收 |
|---|---|---|---|
| **PR-1** | C13 + §1.4/§1.5 宪法入位（已在本重写 ADR 中完成） | AGENTS.md C13 行 + ADR-0195 §1.4/§1.5 + ADR-0066 §三补丁 | 纯文档 |
| **PR-2** | ADR-0205 撤回 banner + ADR-0204 重写（已在本重写 ADR 中完成） | 0205 retired banner + 0204 重写 | 纯文档 |
| **PR-3** | typed Contract 骨架（G0 contracts/slot_io/） | `SlotIOContractBase` + 4 个 OpenAI*Message Contract（Pydantic frozen, `extra="forbid"`） | schema 单测 |
| **PR-4** | Manifest `capability.contract.provides` 样例 + Resolve DAG 校验 | `@plugin model.contract.anthropic_claude` 样例 + `test_capability_contract_dag` | C13-DAG-1, C13-MANIFEST-1 |
| **PR-5** | 写端 Self-Closing（PR-5 即 §3.3） | `capture_post_llm` 用 `OpenAIAssistantMessage.construct()` 强类型 | MV-SHAPE-1 |
| **PR-6** | 双路径合并（PR-6 即 §3.4） | `complete_model` 不再写 surface，只写 catalog | MV-UNICITY-1 |
| **PR-7** | 读端零分支（PR-7 即 §3.5） | `derive_event_message` → `unit.view()`，删 30 行 if/elif | MV-IFELIF-1 |
| **PR-8** | Transport 收口（PR-8 即 §3.6） | `_spine_xxx` 5 个硬编码 → `unit.view() + WireTransport.render()` | MV-TRANSPORT-1 |
| **PR-9** | grep 全清 + C13 架构测试 | `data["message"]` / `.get("message")` / `if event_type ==` 全部消失 | MV-DICT-1, C13-PROV-1, C13-PROV-2 |

**P0（PR-1~9）** 同 PR 闭环（零中间态）。**P1 推广（tool/fact/skill）** 不在本 ADR 范围；按 C6 最小化，未来同类问题出现时再走 ADR 立项，不预设。
