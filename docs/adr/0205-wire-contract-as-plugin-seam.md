# ADR-0205 — WireContract 元机制（已撤回）

> **SUPERSEDED 2026-09-08**：本 ADR 提出的"WireContract 元机制"已并入宪法 [ADR-0195 §1.4 信息血统闭合 (C13)](0195-platform-architecture-convergence.md) + §1.5 同型 DAG 视图 + [ADR-0066 §三](0066-declarative-atomic-control-plugins.md) ControlSlot IO Contract 范式。**不再单独存在**。原 §0 / §1 / §5 列出的 5 处 wire shape 收口（model / tool / fact / skill / model provider）不再作为本 ADR 的应用域，按各自 bug 现场走单点修复 ADR（如 [ADR-0204](0204-surface-render-slot-plan-strategy.md)）。
>
> **保留理由**：历史文件不删除，便于追溯 run_20951da435a6 的修复路径。原"WireContract / WireRegistry / wire.contract.provides"命名空间**禁止新增**，所有 typed Contract 沿用 ADR-0110 `capability.contract.provides` slot。
>
> **后续动作**：单点修复见 [ADR-0204 重写版](0204-surface-render-slot-plan-strategy.md)。宪法层级见 [ADR-0195 §1.4 / §1.5](0195-platform-architecture-convergence.md)。

## 状态

**Deprecated — Superseded by ADR-0195 §1.4 + ADR-0204 (2026-09-08)**。

**触发**: run_20951da435a6 (assistant 消息失踪 + readFile 重复循环) 暴露 LCA 多处同源结构性脆弱（5 处文件各自维护 OpenAI message 形状、字段名漂移、if/elif 散落、silent drop）。

**关联**:
- **延伸并统摄** [ADR-0204](0204-surface-render-slot-plan-strategy.md) (升级版) — surface render 是 WireContract 第 1 个应用域
- **延伸** [ADR-0193](0193-session-projection-fabric-model-visible.md) — ModelVisibleUnit.wire_view 是 WireContract 在 projection 层落地
- **衔接** [ADR-0194](0194-cognitive-loop-architecture-convergence.md) / [ADR-0195](0195-platform-architecture-convergence.md) — 五平面 + 三时态的元机制
- **延伸** [ADR-0066](0066-declarative-atomic-control-plugins.md) — ControlSlot 范式推广为 WireContract slot
- **衔接** [ADR-0183](0183-event-bus-framework-ssot.md) / [ADR-0186](0186-session-as-event-ssot.md) — 事件 SSOT
- **借鉴** [ADR-0110](0110-plugin-contract-unification-and-naming-convergence.md) — PluginContract 统一化

---

## 0. 决策摘要

LCA 当前任何「内部状态 ↔ 外部协议」(LLM wire / HTTP / DB / tool envelope / event payload / skill descriptor) 翻译都**没有强类型契约 + 显式 dispatch + 静态拓扑**。每加一个 seam 类型,代码任意处都能再发明一次形状 — 这是 run_20951da435a6 反复出现的根因,不是单点 bug。

**终态一句话**: **WireContract 是 LCA 唯一的「内部状态 ↔ 外部协议」翻译机制**。所有 wire 形状必是 Pydantic frozen Contract;所有 dispatch 必走 WireRegistry;所有 plugin 贡献必在 Manifest `wire.contract.provides` 显式声明;所有失败必 fail-loud 不静默。

```text
                            PluginContract.capabilities
                            .wire.contract.provides
                                       │
                                       ▼ (Manifest 静态声明)
┌──────────────────────────────────────────────────────────────────────┐
│ contracts/wire/                       (G0 不可插件化)              │
│   ├── contract.py    WireContract Protocol (extract/validate/transport_keys)
│   ├── registry.py    WireRegistry (dispatch, fail-loud on miss)
│   ├── violations.py  WireContractViolation + violation.v1 spine event
│   ├── transport.py   WireTransport Protocol (message → wire chunk)
│   └── exceptions.py  WireContractRegistryMiss (fail-loud)          │
└─────────────────────────────┬────────────────────────────────────┘
                              │ Compile-time resolve (DAG + closure)
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ contracts/wire/contracts/  (G1 默认契约集, 可由 plugin 覆盖)       │
│   ├── model_openai.py   OpenAI 家族 (gpt-4/o1/o3)                   │
│   ├── model_anthropic.py Anthropic 家族 (claude-3/3.5)              │
│   ├── model_google.py   Gemini 家族                                  │
│   ├── model_deepseek.py DeepSeek 家族                                │
│   ├── tool_envelope.py  ToolInvocationEnvelope                      │
│   ├── fact_shape.py     FactPayload                                  │
│   └── skill_descriptor.py SkillManifest                              │
└─────────────────────────────┬────────────────────────────────────┘
                              │ Runtime dispatch via WireRegistry
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 消费方 (零分支, 全部经 WireRegistry)                                │
│   ModelVisibleUnit.wire_view(event) → WireContract                   │
│   ToolRegistry.invoke(name, args)   → ToolContract                    │
│   FactGateway.append(fact)         → FactContract                    │
│   SkillRegistry.load(uri)          → SkillContract                   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 1. 第一性原理:5 类 wire 翻译共享同一结构

LCA 当前涉及「内部状态 ↔ 外部协议」翻译的所有 seam,均可拆为同一结构:

| seam | 内部 | 外部协议 | 当前实现 | 脆弱性 |
|---|---|---|---|---|
| **Model render** | Session fold | OpenAI/Anthropic/Gemini message | 5 个文件散落 if/elif | **run_20951da435a6 现场** |
| **Tool invocation** | ToolEnvelope | wire JSON / MCP / A2A | `tool_name → handler` 字符串字典 | 新工具静默 drop |
| **Information projection** | Fact / State / Decision | API response / DB row / OTel | 各自 Pydantic 与 dict 混用 | 字段漂移 |
| **Skill descriptor** | SkillManifest | wire manifest / role registry | 多个 YAML loader,缺 schema | skill 加载静默失败 |
| **Model provider** | LLMCall | provider-specific request | 多家 SDK 各自实现 | provider 切换成本高 |

**结构同源**: `InternalState → WireShape → ExternalProtocol`。
**根因同源**: 5 个 seam 都没有把 `WireShape` 收敛为 Pydantic frozen Contract,也没有把 `dispatch` 收敛为 Manifest-driven Registry。

**因此**:**WireContract 是这 5 个 seam 的统一元机制**。surface render 是 P0 第 1 个应用域。

---

## 2. WireContract 四要素

每个 WireContract 实例必满足 4 要素,缺一即 fail-loud:

| 要素 | 形态 | 责任 |
|---|---|---|
| **Shape** | Pydantic frozen model (`extra="forbid"`) | 字段集合 + 类型 + 嵌套契约 |
| **Extract** | `extract(event_data: Mapping) -> Contract \| None` | 从事件数据构造 Contract 实例,失败返 None |
| **Validate** | `validate(instance) -> Result[Contract, Violation]` | 校验字段合法性 (Pydantic 自动) |
| **Transport** | `transport_keys: tuple[str, ...]` | 声明该 Contract 支持哪些 wire transport (SSE chunk / OpenAI wire / DB row) |

**反例 (当前形态)**:
```python
# 5 处各自维护 message 形状,字段名不一致
payload = {"role": "assistant", "content": str(content), "tool_calls": tool_calls}  # hook.py
msg = data.get("message") or data.get("content")  # messages.py
```

**正例 (WireContract 后)**:
```python
# 1 处定义,5 处共用
class OpenAIAssistantMessage(WireContractBase):
    role: Literal["assistant"] = "assistant"
    content: str = ""
    tool_calls: list[OpenAIToolCall] | None = None
    refusal: str | None = None
    # extra="forbid" 自动

# 全栈只能:
msg = OpenAIAssistantMessage.construct(content=c, tool_calls=tc)  # 写端
msg = registry.get("openai.assistant").extract(event_data)        # 读端
chunk = registry.get_transport("sse.chunk").render(msg)           # transport
```

---

## 3. WireRegistry 派发机制

```python
class WireContractViolation(Exception):
    """WireContract 违反 — 必须 fail-loud 写 spine event, 不静默返 None"""

class WireContractRegistryMiss(KeyError):
    """Registry miss — plugin 未声明该 contract, fail-loud"""

class WireRegistry:
    """WireContract 唯一派发表。Profile-scoped, 不允许 process global。"""

    def __init__(self):
        self._contracts: dict[str, WireContract] = {}
        self._transports: dict[str, WireTransport] = {}
        self._overrides: dict[str, list[str]] = {}  # contract_key → [plugin_id, ...]

    def register(self, key: str, contract: WireContract) -> None:
        if key in self._contracts:
            raise ValueError(f"contract {key} already registered")
        self._contracts[key] = contract

    def register_override(self, base_key: str, override_key: str, plugin_id: str) -> None:
        if base_key not in self._contracts:
            raise WireContractRegistryMiss(base_key)
        self._overrides.setdefault(base_key, []).append(plugin_id)
        self._contracts[override_key] = self._contracts[base_key].derive(plugin_id)

    def get(self, key: str) -> WireContract:
        if key not in self._contracts:
            raise WireContractRegistryMiss(key)
        return self._contracts[key]

    def get_transport(self, key: str) -> WireTransport:
        if key not in self._transports:
            raise WireContractRegistryMiss(f"transport:{key}")
        return self._transports[key]

    def validate_dag(self) -> None:
        """Resolve-time 校验: overrides 形成 DAG, 无环"""
        # 拓扑排序 + 检测环
        ...
```

**关键约束**:
- **不允许 process global** — 每个 Profile 装配自己的 Registry 实例,经 Boot 注入
- **不允许 fallback** — miss 抛 `WireContractRegistryMiss`,由 Boot fail-fast
- **不允许动态覆盖** — overrides 必在 Manifest 声明, Resolve 拓扑校验

---

## 4. Manifest 声明与 PluginContract 集成

`PluginContract.capabilities` 增加新 slot:

```yaml
# plugins/model/anthropic_claude/plugin.yaml
id: model.contract.anthropic_claude
$module: lca.plugins.model.anthropic_claude
capabilities:
  provides:
    - wire.contract.anthropic_assistant:    # contract_key
        base: openai.assistant              # 继承自哪个 base
        extra_fields:                        # 严格 extra="allow" 白名单
          cache_control: { type: "ephemeral" }
        transport_keys: [sse.chunk, anthropic.wire]
        activation:
          when: model.family == "claude"
  requires:
    - wire.contract.openai_assistant        # 必须先有 base
  effects: []
  failure_mode: degrade
  authority: [wire.contract.read]
```

**Resolve 校验 (静态)**:

| 检查 | 实现 |
|---|---|
| `base` contract 已注册 | `WireRegistry.contains(base)` |
| `extra_fields` 类型与 base 不冲突 | Pydantic schema diff |
| `transport_keys` 在 WireTransportRegistry | fail-loud |
| `overrides` 形成 DAG 无环 | Resolve-time 拓扑排序 |
| `activation` 引用事实注册 | `FactDescriptorRegistry.contains(path)` |
| Plugin 间不重复覆盖同一 key | Registry.assert_unique_override |

---

## 5. 4 个应用域(同元机制, 各 P-Round 实施)

### 5.1 Model Render (P0, 随 ADR-0204 升级版同步)

```python
# contracts/wire/contracts/model_openai.py
class OpenAIUserMessage(WireContractBase):
    role: Literal["user"] = "user"
    content: str | list[OpenAIUserContent]

class OpenAIAssistantMessage(WireContractBase):
    role: Literal["assistant"] = "assistant"
    content: str | None = ""
    tool_calls: list[OpenAIToolCall] | None = None
    refusal: str | None = None

class OpenAIToolMessage(WireContractBase):
    role: Literal["tool"] = "tool"
    content: str
    tool_call_id: str

class OpenAIToolCall(WireContractBase):
    id: str
    type: Literal["function"] = "function"
    function: OpenAIFunction

# 写端
msg = OpenAIAssistantMessage.construct(content=content, tool_calls=tool_calls)
payload = SpineLlmRequestHeaderAssistantPayload(message=msg.model_dump())

# 读端 (零分支)
def derive_event_message(event):
    return unit.wire_view(event)  # WireRegistry.get(...).extract(event_data)
```

### 5.2 Tool Invocation (P1, 后续 Round)

```python
# contracts/wire/contracts/tool_envelope.py
class ToolInvocationEnvelope(WireContractBase):
    name: str
    arguments: dict[str, Any]
    tool_call_id: str
    invocation_at: datetime

class ToolResultEnvelope(WireContractBase):
    tool_call_id: str
    content: str | dict
    is_error: bool = False

# 写端
envelope = ToolInvocationEnvelope.construct(name=tc.name, arguments=tc.args, tool_call_id=tc.id)
result = ToolResultEnvelope.construct(tool_call_id=envelope.tool_call_id, content=output)

# 消费方 (零分支, 替换现有 handlers_provider.py 字符串字典)
def invoke_tool(envelope: ToolInvocationEnvelope) -> ToolResultEnvelope:
    handler = ToolRegistry.get(envelope.name)  # WireContractRegistryMiss on unknown
    return handler(envelope)
```

### 5.3 Information Projection (P1, 后续 Round)

```python
# contracts/wire/contracts/fact_shape.py
class FactPayload(WireContractBase):
    category: str
    producer: str
    data: dict[str, Any]  # 仍允许任意 data, 但 producer/category/timestamp 强类型
    timestamp: datetime

# FactGateway.append 必经
def append_fact(fact: FactPayload) -> None:
    fact.validate()  # Pydantic 自动
    session.append(fact)  # Session.append 仍是 G0 唯一入口
```

### 5.4 Skill Descriptor (P1, 后续 Round)

```python
# contracts/wire/contracts/skill_descriptor.py
class SkillManifest(WireContractBase):
    id: str
    version: str
    entrypoints: list[SkillEntrypoint]
    capabilities_provides: list[str]
    capabilities_requires: list[str]
    effects: list[Effect]

class SkillEntrypoint(WireContractBase):
    name: str
    handler: str
    input_contract: str  # WireContract key
    output_contract: str

# SkillRegistry.load 必经
def load_skill(uri: str) -> SkillManifest:
    raw = read_yaml(uri)
    manifest = SkillManifest.model_validate(raw)  # Pydantic 自动校验
    return manifest
```

---

## 6. 5 层 fail-loud 守护

任何 WireContract 违反必在 5 层之一 fail-loud,**任一独立触发即暴露**:

| 层 | 触发条件 | 表现 |
|---|---|---|
| **L1 Pydantic** | 字段类型错、unknown extra、必填缺失 | `ValidationError` 抛错 |
| **L2 Manifest** | plugin 缺 `provides` 声明 | `UndeclaredInteractionError`(已存在,扩展 slot) |
| **L3 Resolve** | overrides 形成环、base 缺失 | `WireContractResolveError` |
| **L4 Registry** | runtime miss contract / transport | `WireContractRegistryMiss` |
| **L5 测试** | 任何 if/elif 重新出现 | `tests/architecture/test_no_wire_ifelse.py` fail-loud |

**架构测试 (L5)** 守护列表:

```python
# tests/architecture/test_wire_contract_invariants.py

def test_no_dict_payload_in_write_path():
    """写端不允许 dict 字面量构造 wire shape, 必走 WireContract.construct()"""
    # grep: 'data\[.message.\]\s*=' 或 '\.get\(".message"\)'
    for path in tracked_python_files():
        content = read_file(path)
        assert "data[\"message\"]" not in content, f"{path}: dict 访问消息字段"
        assert ".get(\"message\")" not in content, f"{path}: dict.get 访问消息字段"

def test_no_if_elif_in_dispatch():
    """dispatch 入口不允许 if/elif 链"""
    # 在指定文件中 (event_translator, lifecycle_emit, messages)
    for path in dispatch_files():
        content = read_file(path)
        # 允许: registry.get(key)
        # 不允许: if event_type == "...", elif event_type == "..."
        assert "if event_type ==" not in content, f"{path}: 散落 dispatch"
        assert "elif event_type" not in content, f"{path}: 散落 dispatch"

def test_wire_contract_registry_complete():
    """每个 contract 都有 transport, 每个 transport 都被引用"""
    # registry.graph 检查

def test_wire_contract_dag():
    """overrides 形成 DAG, 无环"""
    # 拓扑排序 + 检测

def test_manifest_provides_complete():
    """每个 plugin 提供 wire.contract 都通过 Manifest.provides 声明"""
    # 静态扫描所有 plugin 文件
```

---

## 7. 不变量 (架构测试守护, fail-loud)

| ID | 内容 | 测试 |
|---|---|---|
| **WC-1** | wire shape 必是 Pydantic frozen `extra="forbid"`, 不允许 dict | `test_no_dict_payload_in_write_path` |
| **WC-2** | 每个 wire contract 在 Registry 唯一 key, 反之亦然 | `test_wire_contract_registry_complete` |
| **WC-3** | overrides 形成 DAG 无环 | `test_wire_contract_dag` |
| **WC-4** | plugin `provides` 必在 Manifest 声明, 无声明 = `UndeclaredInteractionError` | `test_manifest_provides_complete` |
| **WC-5** | dispatch 入口是 `WireRegistry.get()`, 不允许 if/elif 散落 | `test_no_if_elif_in_dispatch` |
| **WC-6** | Registry miss 抛 `WireContractRegistryMiss`, 不静默 None | `test_registry_miss_fail_loud` |
| **WC-7** | WireContract 违反必写 `wire.contract.violation.v1` spine 事件 | `test_violation_event_written` |
| **WC-8** | WireRegistry 是 profile-scoped, 不允许 process global | `test_registry_not_global` |

---

## 8. 与现有 ADR / Note 关系

| 既有 | 处置 |
|---|---|
| [ADR-0204](0204-surface-render-slot-plan-strategy.md) (升级版) | **第 1 应用域** — surface render 用 WireContract 实现 |
| [ADR-0193](0193-session-projection-fabric-model-visible.md) ModelVisibleUnit | **延伸** — 增加 `wire_view()` 第 4 步 |
| [ADR-0194](0194-cognitive-loop-architecture-convergence.md) / [ADR-0195](0195-platform-architecture-convergence.md) | **衔接** — 五平面中 Mechanism 平面扩展为 WireContract |
| [ADR-0066](0066-declarative-atomic-control-plugins.md) ControlSlot | **借鉴** — `wire.contract` 是 ControlSlot 新成员 |
| [ADR-0110](0110-plugin-contract-unification-and-naming-convergence.md) | **衔接** — PluginContract.capabilities 增加 wire.contract slot |
| [ADR-0061](0061-plugin-manifest-resolve-boot.md) | **衔接** — Resolve 校验扩展为 WireContract DAG |
| [ADR-0183](0183-event-bus-framework-ssot.md) / [ADR-0186](0186-session-as-event-ssot.md) | **衔接** — WireContract violation 走 Session.append |

---

## 9. 实施序列

| PR | 标题 | 主要结果 | delete-when / 验收 |
|---|---|---|---|
| **PR-1** | WireContract 骨架 (G0 contracts/wire/) | `WireContract` Protocol + `WireRegistry` + `WireContractRegistryMiss` + `WireContractViolation` + 5 个 fail-loud 测试 | 无 (纯加法) |
| **PR-2** | WireContract Pydantic 集 (P0 model_openai) | OpenAI 家族 4 个 Contract (`UserMessage` / `AssistantMessage` / `ToolMessage` / `ToolCall`) | schema 单测 |
| **PR-3** | ModelVisibleUnit.wire_view (P0) | ModelVisibleUnit 第 4 步 wire_view,委托 Registry | parity test ≡ 旧 if/else |
| **PR-4** | 写端 Self-Closing (P0) | `capture_post_llm` 用 `OpenAIAssistantMessage.construct()` 强类型 | MV-SHAPE-1 测试 |
| **PR-5** | 双路径合并 (P0) | `complete_model` 不再写 surface, 只写 catalog `assistant.responded.v1` | MV-UNICITY-1 |
| **PR-6** | 读端零分支 (P0) | `derive_event_message` → `unit.wire_view(event)`, 删 30 行 if/elif | MV-PARITY-1 |
| **PR-7** | Transport 收口 (P0) | `_spine_xxx` 5 个硬编码 → WireTransport table | MV-TRANSPORT-1 |
| **PR-8** | Manifest plugin 声明 (P0) | `@plugin wire.contract.claude_cache` 样例 + Resolve DAG 校验 | WC-3, WC-4 |
| **PR-9** | 删 if/elif + dict 访问 (P0) | grep 全清, `data["message"]` / `.get("message")` / `if event_type ==` 全部消失 | WC-1, WC-5 |
| **PR-10** | Tool Invocation WireContract (P1) | `ToolInvocationEnvelope` + `ToolResultEnvelope` + 替换 handlers_provider 字符串字典 | registry miss fail-loud |
| **PR-11** | Fact Shape WireContract (P1) | `FactPayload` + FactGateway.append 强类型 | schema 校验 |
| **PR-12** | Skill Descriptor WireContract (P1) | `SkillManifest` + `SkillEntrypoint` + 替换 YAML loader | skill load fail-loud |

**P0 (PR-1~9)** 同 PR 闭环(零中间态)。**P1 (PR-10~12)** 各自独立 PR。

---

## 10. delete-when 清单(无中间态)

| 删除 | delete-when |
|---|---|
| `assistant_content` / `tool_calls` 平铺字段 in `SpineLlmRequestHeaderAssistantPayload` | PR-4 同 PR 删除 |
| `complete_model` 双写 surface 分支 | PR-5 同 PR 删除 |
| `_spine_xxx` 各自硬编码 5 处 (event_translator.py) | PR-7 同 PR 删除 |
| `derive_event_message` if/elif 3 分支 (messages.py) | PR-6 同 PR 删除 |
| `_SPINE_HANDLERS` dict (event_translator.py) | PR-7 同 PR 删除 |
| `lca_kernel/events/render/` 若新建 | 不再创建, 内容直接进 `contracts/wire/contracts/model_openai.py` |
| 任何 `data["message"]` / `.get("message")` / `.get("tool_calls")` | PR-9 grep 全清 |

---

## 11. 风险与缓解

| 风险 | 缓解 |
|---|---|
| **Pydantic 校验失败阻塞生产路径** | `model_validate` 用 `ValidationError` 捕获并 fail-loud 写 `wire.contract.violation.v1` spine event, 不阻塞 conversation |
| **plugin override 链导致 wire shape 不可预测** | Manifest overrides 必填 `base` + `contract_key`, Resolve 检查 `overrides` 形成 DAG, 无环; 静态 lint-imports 扩展为 wire-contract 拓扑 |
| **ModelVisibleUnit 扩展破坏现有 I-MV-PROJ-*** | `wire_view` 是 view 的扩展, view 仍返回 `model_visible_messages`; wire_view 独立调用; 两条路径可共存 |
| **现有 consumer 不接受强类型返回** | `model_dump()` 出口统一 dict, consumer 不需要改 |
| **WireContract 抽象过重** | Protocol + Registry + Manifest 三件套是 LCA 现有范式 (ADR-0066/0075/0197/0110), 无新原语 |
| **P1 推广到 tool/fact/skill 改动面广** | 每个 P1 独立 PR, 各自 delete-when + 架构测试; 不一次性迁移 |

---

## 12. 效果预期

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
- ✅ 5 类 seam (model/tool/fact/skill/...) 同一元机制, 推广到 P1 仅是新增 Contract
- ✅ plugin 扩展走 Manifest `wire.contract.provides`, Resolve 拓扑校验
- ✅ 零中间态: 旧 if/elif / dict.get / 平铺字段, 同 PR 全删

---

## 13. 长期推广路径

| 优先级 | 域 | 复用 WireContract 模式 | 预计 PR |
|---|---|---|---|
| **P0** | Model render | `OpenAI*Message` (4 个) + WireRegistry | 9 PR (PR-1~9) |
| **P1** | Tool invocation | `ToolInvocationEnvelope` + `ToolResultEnvelope` | PR-10 |
| **P1** | Information (fact) | `FactPayload` | PR-11 |
| **P1** | Skill descriptor | `SkillManifest` + `SkillEntrypoint` | PR-12 |
| P2 | Model provider 多家族 | `Anthropic*` / `Gemini*` / `DeepSeek*` Contract + plugin override | 2 PR |
| P2 | HTTP wire / DB row | `WireTransport` 新增 transport | 1 PR |
| P2 | A2A / MCP envelope | `A2AEnvelope` / `MCPEnvelope` | 2 PR |

**核心原则**: 每次推广 = 1 个新 Pydantic Contract + 1 个 Manifest slot + 1 个 fail-loud 测试。**不再写 if/elif, 不再发明字段名, 不再 silent drop。**
