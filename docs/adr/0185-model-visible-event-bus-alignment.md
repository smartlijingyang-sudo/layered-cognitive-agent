# ADR-0185 — Model-Visible 走 ADR-0183 统一 event bus:plugin 化 producer + fold 重建

## 状态

Accepted — 落地中(2026-09-04)。

**实施状态**:
| PR | 范围 | 状态 | 基线 |
|---|---|---|---|
| PR-0 | fold 模块 1:1 翻译 dsh | 已合并 | `1eefe053` / merge `6e1c61d2` |
| PR-1 | EventPayload 类型化 + yaml 注册 | 已合并 | `b0723d55` / merge `36ad90a2` |
| PR-2 | `ModelVisiblePublisher` + Hook(双轨) | 已合并 | `a334098e` / merge `5d5c63e9` |
| PR-3 | core viewer / CLI / replay 迁 fold(双轨) | 已合并 | `6ce3bc0e` / merge `7841acc6` |
| PR-3.1 | webserver handlers + doctor fold | 进行中 | branch `feat/adr-0185-pr-3.1-handlers` |
| PR-4 | 删旁路文件 + 废旧 ADR + Note 迁 implemented | 未合并 | 另 agent 负责;勿在本分支宣称完成 |

PR-3 只迁 core viewer(`fold_source` / `StandardCursor` / `lca-ops journal*` / 架构与集成测试)。webserver handlers 与 doctor fold 落 PR-3.1。PR-4 删除 sidecar 与状态翻转为 Accepted(落地完成)由独立 worktree 执行。

**Supersedes / 吸收**: ADR-0169 D7 I-MV1(`StdModelVisibleCapture` 5 件套 SSOT)、ADR-0175 D3(`StdReasonerPromptCapture` 单独 capture)、ADR-0176 D4(`system.json` 合并到 `messages.json`)。

**不破坏**: ADR-0183 I-FW-BUS-1/2/3、I-FW-SSOT-1/2、I-FW-BUS-4(本 ADR 是其延伸)。

**对齐参考**: deepseek-harness `request/header` event 形态(`packages/core/agent-loop/src/agent.ts:498-517`)+ `foldRequestHeader` fold 优化(`packages/core/session/src/request-header.ts`)。deepseek-harness `AGENTS.md:111`:**"Model-visible ⟺ logged: anything that reaches a model request must be reconstructable from the session log; a new model-visible input requires a session event."**

**本文档配套 Note**: [`docs/notes/proposed/seam/2026-09-04-model-visible-bus-alignment.md`](../notes/proposed/seam/2026-09-04-model-visible-bus-alignment.md)(PR-4 合并后迁 `implemented/seam/`)。

## 0. 决策摘要

把"模型所见"从**旁路文件 6 件套 + digest 留痕**升级为**走 ADR-0183 统一 event bus 的 producer**,payload **带 system/tools 原文**(对齐 dsh),fold 优化由 `ModelVisiblePublisher` 内部用 dsh 风格 `headerEquals` + `canonicalHeader` + `foldRequestHeader` 实现,viewer 直接从 `<run_id>.spine.jsonl` fold 重建。

新增独立 `@plugin` `lca.plugins.events.publishers.model_visible`,作为 `spine.llm.request.header` + `spine.llm.request.header.assistant` 两类 spine event 的**唯一授权生产者**,严格走 ADR-0183 统一 event bus(满足 I-FW-BUS-1)。

**代价**:废 3 个现行 ADR、删 7 个旧文件、改 viewer / `lca-ops` / webserver handler 的"反查 model_visible/" 路径。

**收益**:journal 自含、顺手修复 Note `2026-09-03-model-visible-incomplete-projection.md` 的 3 个已知 BUG、不破坏 ADR-0183 I-FW-* 不变量、跟 deepseek-harness 设计原则对齐。

## 1. 背景与现状(事实)

### 1.1 当前 model_visible 落盘链路(实测)

```
Brain._render_prompt
  └─ PromptAssembler.render(...) → PromptTrace(sections/skills/tools_count)
  └─ bind_current_reasoner_prompt(CurrentReasonerPrompt(...))       # ContextVar

LLM adapter.complete(prompt, **kwargs)
  └─ ModelVisibleLLMAdapter._run_capture(prompt=prompt, kwargs=kwargs)
       ├─ cursor.snapshot → step_id / incarnation / inherited_from_step
       ├─ _derive_capture_inputs(kwargs)
       │    ├─ tools    ← kwargs 里被当前 agent 装配出来的 ToolSchema 列表
       │    ├─ messages ← kwargs 里本次实际发给模型的消息序列 + system 段
       │    └─ manifest ← kwargs 里 ContextManifest
       │
       ├─ StdReasonerPromptCapture.capture(trace)         ─→ system_prompt.json
       │                                                    ─→ system_prompt_sections.json
       │
       ├─ StdModelVisibleCapture.capture(...)             ─→ tools.json
       │                                                    ─→ messages.json
       │                                                    ─→ manifest.json
       │                                                    ─→ inherited.json (可选)
       │
       └─ cursor.record_request_header(artifact) → spine EP: llm.request.header
            └─ caller_payload = { 4 digest + 4 relpath },不带原文

<run_dir>/model_visible/step_<NN>/{system,tools,messages,manifest,inherited}.json  ← 旁路文件
<run_dir>/<run_id>.spine.jsonl                                                       ← EP 只带 digest + relpath
```

### 1.2 三处已知缺陷(实测)

| # | 问题 | 根因 |
|---|---|---|
| 1 | assistant 回复没投影(messages 里永远是 user) | `capture` 在 LLM 调用**之前**跑(`model_visible_llm_adapter.py:285`),assistant 输出不在 messages 里 |
| 2 | tools.json 22 个全空 `{}` | `_to_jsonable`(`loop_cursor/_capture_io.py:33`)对 ToolSchema 实例走 5 段回退,落到 `repr()` 字符串回退时被进一步 dict 序列化又走一次,碰到非 JSON 类型回退 `{}` |
| 3 | system 模板被错塞到 `messages[0].role=user` | 上游 reasoner bug,capture 没探测,debug agent 误判"system 注入失败" |

证据:`traces/runs/run_365ad8d3c2c0/model_visible/step-001/`。完整记录见 Note `2026-09-03-model-visible-incomplete-projection.md`。

### 1.3 当前 model_visible 实现文件清单(实测)

| 文件 | 行数 | 角色 |
|---|---:|---|
| `lca/infrastructure/observability/loop_cursor/model_visible_capture.py` | 174 | `StdModelVisibleCapture` 默认实现(写 tools/messages/manifest/inherited) |
| `lca/infrastructure/observability/loop_cursor/reasoner_prompt_capture.py` | 111 | `StdReasonerPromptCapture` 默认实现(写 system_prompt + system_prompt_sections) |
| `lca/contracts/observability/model_visible_capture.py` | 100 | `ModelVisibleCapture` Protocol + `ModelVisibleArtifact` dataclass |
| `lca/infrastructure/observability/loop_cursor/model_visible_binding.py` | — | `ModelVisibleCapture` ContextVar 注入 |
| `lca/infrastructure/observability/loop_cursor/_capture_io.py` | — | `_write_json` / `_to_jsonable` / `sha256_digest` / `relative_posix` 公共 IO |
| `lca/infrastructure/observability/adapters/model_visible_llm_adapter.py` | 313 | `ModelVisibleLLMAdapter` 装饰器(`_run_capture` 在 LLM 调用前调两个 capture) |

合计 6 个文件 + 1 个目录约定 `<run_dir>/model_visible/`,承担"模型所见" 全部职责。

### 1.4 ADR-0183 seam 可复用性(实测)

| ADR-0183 seam | 在哪 | 本 ADR 复用方式 |
|---|---|---|
| §3.1 `EventBus.publish(payload, *, producer=...)` | `lca_kernel/events/bus.py` | Producer 直接调,满足 I-FW-BUS-1 |
| §3.2 `PreDispatchHook` / `PostDispatchHook` Protocol | `lca_kernel/events/hooks.py` | `ModelVisibleHook` 实现这两个,拦截 LLM adapter 边界 |
| §3.4 `SinkBackend` Protocol | `lca_kernel/events/sinks/__init__.py` | 不复用 — 本 ADR 让 spine.jsonl 取代旁路文件真值 |
| §3.5 `SpineEventRecord.to_dict()` SSOT | `lca/infrastructure/observability/spine/event_record.py` | 字段定死,plugin 不可改;本 ADR 不变 |
| §3.7 `EventPayload` 基类 + `FieldType` | `lca_kernel/events/payloads.py` | 两个新 payload 继承它 |
| §3.7 yaml `fields:` schema 校验 | `lca_kernel/events/registry.py` | PR-1 新增 2 个 category |
| §3.3 `consumer_rules:` 前缀路由 | `lca_kernel/events/config_parser.py` | PR-4 把 `spine.llm.request.header.*` 加入默认订阅 |
| I-FW-BUS-1 producer 唯一入口 | `tests/architecture/test_event_bus_invariants.py` | 本 ADR 满足 — 不破坏 |
| I-FW-SSOT-1 `<run_id>.spine.jsonl` 唯一 SSOT | 同上 | 本 ADR **强化** — 删旁路文件 |

**结论**:0 个新开平行机制,完全走 ADR-0183 已落地 seam。

### 1.5 deepseek-harness 对齐参考(实测)

| LCA 当前 | dsh 等价 | dsh 文件 |
|---|---|---|
| (无 fold 概念,每次 LLM 都写新 6 件套) | `foldRequestHeader(events, from?)` | `deepseek-harness/packages/core/session/src/request-header.ts:67-71` |
| (无归一化,空 system/空 tools 都写) | `canonicalHeader(header)` | 同上 `:17-32` |
| (无字节级判等,每步都写) | `headerEquals(a, b)` + `sameSchema(a, b)` | 同上 `:36-53` |
| `cursor.record_request_header(artifact)` 在 adapter 边界 emit | `session.append('request/header', { header, reason })` 在 agent-loop 调 LLM **之前** emit | `deepseek-harness/packages/core/agent-loop/src/agent.ts:498-517` |
| EP payload `{ 4 digest + 4 relpath }`(不带原文) | EP payload `{ header: { config, system, tools } }`(**带原文**) | `deepseek-harness/packages/core/session/src/types.ts:329-` `SpineLlmRequestHeaderPayload` 类似字段 |
| (无 assistant event,旁路文件丢了) | `request/header.assistant` 不在 dsh,但 semantic inspect 在 `ui-conversation/contract/request-inspection.ts:54-87` 把 event.data.header 重建 prompt | dsh 通过 session log fold + view 层投影 |

## 2. 第一性原理(机制,不是补丁)

### 2.1 真正发生的只有两件事

- **生产**:在某次 LLM 调用边界,把"模型即将看见的输入"和"模型实际产生的输出"作为事实记下来
- **消费**:debug agent / viewer / offline replay / 对账工具要在**任意时刻**从 run 的事实链重建"那次 LLM 调用看见 / 说了什么"

### 2.2 最干净的形态

```
                    ┌───────────────────────────────┐
                    │ ModelVisiblePublisher         │ ← 新 @plugin,跟 15 个 spine_reflector 同形
                    │ (lca/plugins/events/...)      │   requires/provides/event_publishes 完整声明
                    └───────────────────────────────┘
                              │ setup 时挂到 LLM adapter 装饰器链
                              ▼
                    ┌───────────────────────────────┐
                    │ ModelVisibleHook              │ ← 实现 PreDispatchHook + PostDispatchHook
                    │ (PreDispatchHook)             │   pre: 拿 system/tools/messages/manifest
                    │ (PostDispatchHook)            │   post: 拿 assistant_content/tool_calls/usage
                    └───────────────────────────────┘
                              │ headerEquals(prev, current) fold 优化
                              ▼
                    ┌───────────────────────────────┐
                    │ EventBus.publish(payload, *)  │ ← 满足 I-FW-BUS-1
                    │ payload=SpineLlmRequestHeaderPayload   │   payload 走 EventPayload 子类 + FieldType
                    │ producer=ModelVisiblePublisher        │   trace_id 由 ADR-0183 §3.9 contextvars 注入
                    └───────────────────────────────┘
                              │
                              ▼
                    ┌───────────────────────────────┐
                    │ SpineSink.append(record)      │ ← I-FW-SSOT-1 唯一 SSOT
                    │ <run_id>.spine.jsonl          │   字节布局 = SpineEventRecord.to_dict()
                    └───────────────────────────────┘
                              │
                              ▼ 离线 fold(纯函数,可单测)
                    ┌───────────────────────────────┐
                    │ foldRequestHeader(events, *)  │ ← 1:1 翻译 dsh request-header.ts
                    │ (lca_kernel/events/fold.py)   │   viewer / explain / replay 调它
                    └───────────────────────────────┘
```

**真值拥有者**:`<run_id>.spine.jsonl` + `foldRequestHeader`(SSOT)
**投影方**:viewer / explain / replay / debug-run(可换实现,但 journal 是单 SSOT)
**副作用**:无 — Producer 只走 spine,不再写旁路文件

### 2.3 用户诉求的机制对应

| 诉求 | 机制形态 |
|---|---|
| 模型所见 = session log | **payload 带原文的 spine event** + fold 重建 |
| journal 自含 | 单一落盘链 `<run_id>.spine.jsonl`,删旁路文件 |
| 体积可控 | `headerEquals` 字节级 fold + `canonicalHeader` 归一化 |
| assistant 输出可重建 | `PostDispatchHook` 在 stream yield 完后 emit |
| tools 不空 `{}` | `ToolSchema.to_openai_dict()` 显式序列化,不走 `_to_jsonable` 回退 |
| system 不被错塞 user | `SpineLlmRequestHeaderPayload.system` 字段独立,`messages` 字段不做 system 探测 |
| 走统一总线 | ADR-0183 I-FW-BUS-1 producer 唯一入口 |
| 走统一 SSOT | ADR-0183 I-FW-SSOT-1 单一落盘链 |

## 3. 设计

### 3.1 新 plugin 形态(对齐 15 个 `spine_reflector_*`)

```python
# lca/plugins/events/publishers/model_visible/publisher.py

@plugin(
    id="lca.plugins.events.publishers.model_visible",
    provides=["event.bus.publisher.model_visible"],
    requires=["event.bus", "llm.adapter", "cursor"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects=(EffectClass.NONE,),  # 只走 spine,无旁路文件
    event_publishes=(
        "spine.llm.request.header",
        "spine.llm.request.header.assistant",
    ),
    event_subscribes=(),
    test_suite="tests/plugins/events/publishers/model_visible/test_publisher.py",
    description="Emit model-visible prompt + assistant output as EventBus events.",
)
async def setup_model_visible_publisher(ctx: PluginContext, config: Config) -> None:
    hook = ModelVisibleHook(
        bus=ctx.event_bus,
        cursor_provider=get_current_cursor,
        prompt_ctx_getter=get_current_reasoner_prompt,
    )
    # 挂到 LLM adapter 装饰器链;profile 可关闭
    if config.get("enabled", True):
        ctx.llm_adapter.decorator_chain.append(hook)
```

### 3.2 新 hook(非 plugin,挂在 publisher 内)

```python
# lca/plugins/events/hooks/model_visible/hook.py

class ModelVisibleHook:
    """pre/post LLM 边界拦截;内部维护 per-cursor fold 状态。

    不持有 cursor 引用,所有状态从 cursor.snapshot 取(评审 S1 处方)。
    Per-instance 状态隔离多 run:状态 dict 键 = (run_id, step_id)。
    """

    def __init__(
        self,
        *,
        bus: EventBus,
        cursor_provider: Callable[[], Cursor | None],
        prompt_ctx_getter: Callable[[], CurrentReasonerPrompt | None],
    ) -> None:
        self._bus = bus
        self._cursor_provider = cursor_provider
        self._prompt_ctx_getter = prompt_ctx_getter
        self._last_headers: dict[tuple[str, str], EpochHeader] = {}

    def before_publish(self, payload, producer, ctx) -> None:
        """PreDispatchHook — 拦截 LLM adapter 调用前。

        拿 system (ContextVar) + tools/messages/manifest (kwargs)。
        headerEquals 判等;变化或首次才发。
        """
        cursor = self._cursor_provider()
        prompt = self._prompt_ctx_getter()
        if cursor is None or prompt is None:
            return  # 透明降级,跟旧 ModelVisibleLLMAdapter._run_capture 一致

        step_id = step_id_for(cursor.snapshot.step_index + 1)
        incarnation = cursor.snapshot.incarnation
        run_id = cursor.snapshot.run_id

        # canonical 归一化(空 system / 空 tools 字段 absent)
        current = canonicalHeader(EpochHeader(
            config=payload.get("config"),  # AssistantRequestConfig from kwargs
            system=prompt.system_prompt_text,
            tools=payload.get("tools", []),
            adapter_defaults=payload.get("adapter_defaults"),
        ))

        key = (run_id, step_id)
        previous = self._last_headers.get(key)
        previous_digest = sha256_digest(previous) if previous else None

        if previous is None:
            reason: ReasonType = "initial"
        elif cursor.snapshot.inherited_from_step is not None:
            reason = "resume"
        elif headerEquals(previous, current):
            return  # fold 优化:同 header 不发
        else:
            reason = "change"

        self._bus.publish(
            SpineLlmRequestHeaderPayload(
                step_id=step_id,
                incarnation=incarnation,
                config=current.config,
                system=current.system or "",
                tools=tuple(current.tools or ()),
                messages=tuple(payload.get("messages", ())),
                manifest=payload.get("manifest"),
                reason=reason,
                previous_header_digest=previous_digest,
            ),
            producer=ModelVisiblePublisher,
        )
        self._last_headers[key] = current

    def after_dispatch(self, payload, ref, results) -> None:
        """PostDispatchHook — 拦截 LLM adapter 调用后。

        顺手修复 Note 2026-09-03-model-visible-incomplete-projection 的 3 BUG:
        1. assistant 输出 (content / tool_calls / finish_reason / usage)
        2. tools 不空 (走 ToolSchema.to_openai_dict())
        3. system 字段独立,不混进 messages
        """
        cursor = self._cursor_provider()
        if cursor is None:
            return

        step_id = step_id_for(cursor.snapshot.step_index + 1)
        incarnation = cursor.snapshot.incarnation
        key = (cursor.snapshot.run_id, step_id)
        previous = self._last_headers.get(key)

        assistant_payload = results[-1].assistant_payload  # 由 LLM adapter 包装
        self._bus.publish(
            SpineLlmRequestHeaderAssistantPayload(
                step_id=step_id,
                incarnation=incarnation,
                assistant_content=assistant_payload.content,
                tool_calls=tuple(assistant_payload.tool_calls),
                finish_reason=assistant_payload.finish_reason,
                usage=assistant_payload.usage,
                header_digest=sha256_digest(previous) if previous else "",
            ),
            producer=ModelVisiblePublisher,
        )
```

### 3.3 新 payload 类(ADR-0183 §3.7 类型化)

```python
# lca_kernel/events/payloads/model_visible.py

from typing import Literal
from dataclasses import dataclass
from lca_kernel.events.payloads import EventPayload
from lca_kernel.events.category import Category

ReasonType = Literal["initial", "resume", "change", "series"]


@dataclass(frozen=True)
class SpineLlmRequestHeaderPayload(EventPayload):
    """LLM 调用边界真实 prompt 投影 — payload 带原文(对齐 dsh)。"""

    category: Category = Category("spine.llm.request.header")

    step_id: str                                    # FieldType.STR
    incarnation: int                                # FieldType.INT
    config: "AssistantRequestConfig"                # FieldType.JSON
    system: str                                     # FieldType.STR (原文)
    tools: tuple["ToolSchema", ...]                 # FieldType.JSON (原文)
    messages: tuple["MessageDict", ...]             # FieldType.JSON (原文)
    manifest: "ContextManifest | None"              # FieldType.JSON | null
    reason: ReasonType                              # FieldType.STR
    previous_header_digest: str | None              # FieldType.STR | null (sha256:...)


@dataclass(frozen=True)
class SpineLlmRequestHeaderAssistantPayload(EventPayload):
    """LLM 实际产出 — 修复 assistant 没投影 BUG。"""

    category: Category = Category("spine.llm.request.header.assistant")

    step_id: str                                    # FieldType.STR
    incarnation: int                                # FieldType.INT
    assistant_content: str                          # FieldType.STR
    tool_calls: tuple["ToolCallDict", ...]          # FieldType.JSON
    finish_reason: str                              # FieldType.STR
    usage: "UsageDict"                              # FieldType.JSON
    header_digest: str                              # FieldType.STR (关联回 request/header)
```

yaml 注册(`lca_kernel/events/config/observability/spine.yaml` 新增):

```yaml
- category: spine.llm.request.header
  plane: observability
  payload_class: lca_kernel.events.payloads.model_visible.SpineLlmRequestHeaderPayload
  fields:
    step_id: str
    incarnation: int
    config: json
    system: str
    tools: json
    messages: json
    manifest: json
    null
    reason: str
    previous_header_digest: str
    null

- category: spine.llm.request.header.assistant
  plane: observability
  payload_class: lca_kernel.events.payloads.model_visible.SpineLlmRequestHeaderAssistantPayload
  fields:
    step_id: str
    incarnation: int
    assistant_content: str
    tool_calls: json
    finish_reason: str
    usage: json
    header_digest: str
```

### 3.4 新 fold 模块(对齐 dsh `packages/core/session/src/request-header.ts`)

```python
# lca_kernel/events/fold.py

from dataclasses import dataclass, field, replace
from typing import Iterable
from lca.infrastructure.observability.spine.event_record import SpineEventRecord


@dataclass(frozen=True)
class EpochHeader:
    """单次 LLM 调用的有效 header(对齐 dsh EpochHeader)。"""
    config: "AssistantRequestConfig | None" = None
    adapter_defaults: "AdapterDefaults | None" = None
    system: str | None = None
    tools: tuple["ToolSchema", ...] = field(default_factory=tuple)


def canonicalHeader(header: EpochHeader) -> EpochHeader:
    """空 system / 空 tools 字段归一为 absent(对齐 dsh canonicalHeader)。"""
    return EpochHeader(
        config=header.config,
        adapter_defaults=header.adapter_defaults,
        system=header.system if header.system else None,
        tools=header.tools if header.tools else (),
    )


def headerEquals(a: EpochHeader, b: EpochHeader) -> bool:
    """字节级判等(对齐 dsh headerEquals)。Tool schemas 顺序敏感。"""
    if a.config != b.config:
        return False
    if a.adapter_defaults != b.adapter_defaults:
        return False
    if a.system != b.system:
        return False
    if len(a.tools) != len(b.tools):
        return False
    return all(_sameSchema(at, bt) for at, bt in zip(a.tools, b.tools))


def _sameSchema(a: "ToolSchema", b: "ToolSchema") -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def foldRequestHeader(
    events: Iterable[SpineEventRecord],
    *,
    step_id: str | None = None,
    from_: EpochHeader | None = None,
) -> EpochHeader | None:
    """离线 fold — 扫一遍事件流,返回指定 step_id 最后的生效 header。

    对齐 dsh foldRequestHeader(events, from):
    - events 可前缀(增量 fold)或全量
    - from_ 续接上次 fold 结果(避免每次全量扫)
    - step_id=None 时 fold 整个流最后一条;否则 fold 该 step_id 最后一条
    """
    state = from_
    for event in events:
        if event.category == "spine.llm.request.header":
            payload = SpineLlmRequestHeaderPayload.from_event(event)
            if step_id is not None and payload.step_id != step_id:
                continue
            state = canonicalHeader(EpochHeader(
                config=payload.config,
                system=payload.system,
                tools=payload.tools,
            ))
    return state
```

### 3.5 Fold 优化契约(`FoldPolicy` Protocol 钉死)

| 上一状态 | 当前 header | reason | 写盘? |
|---|---|---|---|
| None | 任意 | `initial` | ✅ |
| 上 header | `headerEquals(prev, current) == True` | (不发) | ❌ |
| 上 header | `headerEquals(prev, current) == False`,system 变 | `change` | ✅ |
| 上 header | `headerEquals(prev, current) == False`,tools 变 | `change` | ✅ |
| 上 header | `headerEquals(prev, current) == True`,开新 series(retry) | `series` | ✅ |
| `cursor.snapshot.inherited_from_step != None` | 任意 | `resume` | ✅ |

注:journal 体积由 fold 保证可控 — 100 step run 期望 ~10-20 个完整 header,不是 100。`foldRequestHeader` 不依赖 reason 即可重建 effective header。

### 3.6 旁路文件:删

| 删 | delete-when |
|---|---|
| `loop_cursor/model_visible_capture.py`(`StdModelVisibleCapture`) | `rg "StdModelVisibleCapture" lca/ = 0` |
| `loop_cursor/reasoner_prompt_capture.py`(`StdReasonerPromptCapture`) | `rg "StdReasonerPromptCapture" lca/ = 0` |
| `contracts/observability/model_visible_capture.py`(Protocol) | `rg "ModelVisibleCapture" lca/ = 0` |
| `loop_cursor/model_visible_binding.py` + `model_visible_capture.py`(ContextVar) | `rg "CurrentReasonerPrompt" lca/ = 0` |
| `adapters/model_visible_llm_adapter.py`(装饰器) | `rg "ModelVisibleLLMAdapter" lca/ = 0` |
| `loop_cursor/_capture_io.py` | 由 EventBus `_to_jsonable` 统一 |
| `<run_dir>/model_visible/` 目录约定(docs / viewer / tests) | `rg "model_visible/" lca/ lca_kernel/ profiles/ = 0` |

**废 ADR-0169 D7 I-MV1** "每次真实 LLM 请求,必须存在可解析的 `ModelVisibleArtifact` 与 `llm.request.header` EP",由新不变量 **I-MV-2** 接管:"每次 LLM 请求,`foldRequestHeader(<run_id>.spine.jsonl, step_id)` 可重建 effective header;缺失则 fail-fast(等价 dsh `requestHeader()` 行为)"。

### 3.7 Consumer 端约定(viewer / explain / replay)

`lca-ops explain <run_id>` / webserver trajectory viewer / `journal replay --diff-only` 改造清单:

| 调用方 | 改前 | 改后 |
|---|---|---|
| `lca-ops explain` | 反查 `<run_dir>/model_visible/step-001/messages.json` | 读 `<run_id>.spine.jsonl` 过滤 `spine.llm.request.header` + `spine.llm.request.header.assistant` → `foldRequestHeader(events, step_id=...)` |
| webserver trajectory viewer | 同上 | 同上 |
| `journal replay --diff-only` | 反查 `model_visible/` 比对 | 走 fold 后比对 |
| integration tests fixture | 期望 `model_visible/step-001/*.json` 存在 | 期望 `spine.jsonl` 含 2 类 model-visible 事件 + fold 可重建 |

## 4. 不变量(5 条,全部由架构测试守护)

| ID | 内容 | 测试位置 |
|---|---|---|
| **I-MV-1**(新增) | `ModelVisiblePublisher` 是 `spine.llm.request.header` + `spine.llm.request.header.assistant` 唯一授权 producer(走 ADR-0183 yaml 白名单) | `tests/architecture/test_event_bus_invariants.py::test_i_mv_1` — `rg "publish.*spine\.llm\.request\.header" lca/` 仅命中 `model_visible/publisher.py` |
| **I-MV-2**(新增,替代 ADR-0169 I-MV1) | 每次真实 LLM 请求,`foldRequestHeader(<run_id>.spine.jsonl, step_id)` 可重建 effective header;缺失则 fail-fast | `tests/architecture/test_model_visible_fold.py` |
| **I-MV-3**(新增) | 禁止任何代码读 `<run_dir>/model_visible/` 或写 `lca/infrastructure/observability/loop_cursor/model_visible_*.py` | `rg "model_visible/step_\|model_visible_capture\|reasoner_prompt_capture" lca/ lca_kernel/ = 0`(白名单:`archive/`) |
| **I-MV-4**(新增) | `ModelVisibleHook` 是 LLM adapter 边界唯一允许的 model-visible 拦截点;不允许 Brain / Reasoner / Body 自己拼 header publish | `rg "publish.*spine\.llm\.request\.header" lca/cognition/ lca/runtime/ lca/body/ lca/agent/ = 0` |
| **I-MV-5**(沿用 dsh 风格) | fold 用 `headerEquals` 字节级判等;`canonicalHeader` 归一化空 system / 空 tools 字段 | `tests/lca_kernel/events/test_fold.py` |

**不破坏 ADR-0183 不变量**:仍走 I-FW-BUS-1(producer 唯一入口)、I-FW-SSOT-1(spine.jsonl 唯一 SSOT)、I-FW-BUS-2(consumer 唯一入口)、I-FW-BUS-3(plugin 不可改 EventBus 内部 / SpineSink 字节布局)、I-FW-BUS-4(业务不订阅 `event.bus.dispatch.*`)。

## 5. PR 切分(6 PR,全部独立可 revert)

依赖图:

```
PR-0 spike (fold 模块 1:1 翻译 dsh)                         [已合并]
  └─→ PR-1 (EventPayload 类型化 + yaml 注册)                [已合并]
        └─→ PR-2 (Publisher plugin + Hook 实现)             [已合并]
              └─→ PR-3 (core viewer / CLI / replay 迁 fold)  [已合并]
                    ├─→ PR-3.1 (webserver handlers + doctor fold)  [进行中]
                    └─→ PR-4 (删旁路文件 + 废 ADR + 收尾)          [未合并 / 另 agent]
```

### PR-0 spike — fold 模块 1:1 翻译 dsh

| 项 | 内容 |
|---|---|
| **目标** | 把 dsh `request-header.ts` 1:1 翻译成 Python `lca_kernel/events/fold.py`,验证 foldRequestHeader 与 dsh 字节级一致 |
| **新增** | `lca_kernel/events/fold.py`(`EpochHeader` dataclass + `canonicalHeader` + `headerEquals` + `foldRequestHeader`) |
| **新增** | `lca_kernel/events/types.py`(若需要 `AssistantRequestConfig` / `ToolSchema` 等纯类型) |
| **新增** | `tests/lca_kernel/events/test_fold.py`(5 种 fold 场景) |
| **新增** | `tests/lca_kernel/events/test_fold_dsh_parity.py`(1:1 翻译 dsh `request-header.test.ts` 的 fixture) |
| **修改** | 无 |
| **架构测试** | 无(纯加法) |
| **验收** | `uv run pytest tests/lca_kernel/events/test_fold.py tests/lca_kernel/events/test_fold_dsh_parity.py -q` 全过;`lca-ops fold-test web-standard` CLI(若实现)可用现成 spine.jsonl fixture 验证 |
| **delete-when** | 无(本 PR 是后续 PR 的语义锚点;不通过不开 PR-1) |

### PR-1 — EventPayload 类型化 + yaml 注册

| 项 | 内容 |
|---|---|
| **目标** | 新增 `SpineLlmRequestHeaderPayload` + `SpineLlmRequestHeaderAssistantPayload`,在 `spine.yaml` 注册 2 个 category |
| **新增** | `lca_kernel/events/payloads/model_visible.py`(2 个 dataclass) |
| **新增** | `lca_kernel/events/config/observability/spine.yaml` 新增 2 个 category block(带 `payload_class` + `fields:` + `FieldType`) |
| **新增** | `tests/lca_kernel/events/test_model_visible_payload_typing.py` |
| **修改** | 无 |
| **架构测试** | 新增 `test_model_visible_payload_typed` — `rg "publish.*spine\.llm\.request\.header" lca_kernel/events/payloads/` ≥ 1 |
| **验收** | `uv run lca-ops validate-events web-standard` exit 0;`tests/lca_kernel/events/` 全过 |
| **delete-when** | 无(纯加法) |

### PR-2 — Publisher plugin + Hook 实现(双轨共存)

| 项 | 内容 |
|---|---|
| **目标** | 新增 `ModelVisiblePublisher` plugin + `ModelVisibleHook`,**双轨共存**,旧 `ModelVisibleLLMAdapter` 仍存在 |
| **新增** | `lca/plugins/events/publishers/model_visible/publisher.py`(@plugin 装饰器 + setup) |
| **新增** | `lca/plugins/events/hooks/model_visible/hook.py`(PreDispatchHook + PostDispatchHook 实现) |
| **新增** | `bundles/event-bus-components.yaml` 增一行 `lca.plugins.events.publishers.model_visible`(本 PR 暂不挂 profile,先 standalone 验证) |
| **新增** | `tests/plugins/events/publishers/model_visible/test_publisher.py`(mock bus + mock LLM adapter,断言 fold 优化 + assistant payload) |
| **修改** | 无(完全加法) |
| **架构测试** | 新增 `test_i_mv_1` — producer 唯一授权 |
| **验收** | `uv run pytest tests/plugins/events/publishers/model_visible/ -q` 全过;`rg "publish.*spine\.llm\.request\.header" lca/` 仅命中 `model_visible/publisher.py` |
| **delete-when** | 无(双轨共存到 PR-4) |

### PR-3 — core viewer / CLI / replay 迁 fold(双轨共存)【已合并 `6ce3bc0e`】

| 项 | 内容 |
|---|---|
| **目标** | core viewer 读路径切到 `foldRequestHeader`;**双轨共存**,旧 capture / sidecar 仍可运行 |
| **新增** | `lca/infrastructure/observability/replay/fold_source.py`(`fold_model_visible` → `FoldedModelVisible`) |
| **修改** | `StandardCursor.at()` 优先 fold;`lca-ops journal trajectory / replay / verify-model-visible / step --model-visible` 走 fold,无 spine 时回退 sidecar |
| **修改** | `waterfall` / `narrative_writer` 的 model-visible 链接优先 `<run_id>.spine.jsonl` |
| **新增** | `tests/architecture/test_model_visible_fold.py` + `tests/integration/test_model_visible_e2e.py` |
| **范围外** | webserver handlers / doctor fold → PR-3.1;composer `instrument_llm` 仍挂旧 `ModelVisibleLLMAdapter`(delete-when: PR-4) |
| **架构测试** | I-MV-2 fold 可重建 |
| **验收** | spine.jsonl 含两类 model-visible 事件;fold header 字节级等于 publisher payload;assistant 可重建 |
| **delete-when** | 无(双轨共存到 PR-4) |

### PR-3.1 — webserver handlers + doctor fold【进行中】

| 项 | 内容 |
|---|---|
| **目标** | 把 webserver run handlers(trace / explain / doctor 等)从反查 `<run_dir>/model_visible/` 切到 spine fold;`doctor` step_check 用 fold 计数/校验 |
| **修改** | `lca/plugins/transport/webserver/handlers/runs/{trace,explain,doctor,...}.py` |
| **依赖** | PR-3 的 `fold_source` / `StandardCursor` |
| **验收** | doctor H-xref / model-visible hop 在默认 `<run_id>.spine.jsonl` 布局下非全零;handler 渲染 system + tools + messages + assistant |
| **delete-when** | 无(双轨共存到 PR-4) |

### PR-4 — 删旁路文件 + 废 ADR + 收尾【未合并;另 agent 负责】

| 项 | 内容 |
|---|---|
| **删除** | `lca/infrastructure/observability/loop_cursor/model_visible_capture.py`(整个) |
| **删除** | `lca/infrastructure/observability/loop_cursor/reasoner_prompt_capture.py`(整个) |
| **删除** | `lca/contracts/observability/model_visible_capture.py`(整个 Protocol) |
| **删除** | `lca/infrastructure/observability/loop_cursor/model_visible_binding.py` + `model_visible_capture.py`(ContextVar 注入) |
| **删除** | `lca/infrastructure/observability/adapters/model_visible_llm_adapter.py`(整个装饰器) |
| **删除** | `lca/infrastructure/observability/loop_cursor/_capture_io.py`(整个,由 EventBus 统一处理) |
| **删除** | `<run_dir>/model_visible/` 目录约定(docs 说明改写) |
| **修改** | `docs/architecture.md` + `docs/specs/*`:删除"model_visible 6 件套"段落;新增"`foldRequestHeader` 从 spine.jsonl 重建"段落 |
| **修改** | `docs/adr/0169-loop-cursor-control.md` 第 D7 节标题加 `(Superseded by ADR-0185,保留全文作历史)`,正文保留 |
| **修改** | `docs/adr/0175-prompt-trace-into-model-visible.md` 整篇加 `(Superseded by ADR-0185,保留全文作历史)`,正文保留 |
| **修改** | `docs/adr/0176-step-tree-deriver-closure-and-model-visible-dedup.md` 第 D4 节加 `(Superseded by ADR-0185 §3.6)`,正文保留 |
| **新增** | `docs/adr/0185-model-visible-event-bus-alignment.md`(本 ADR,从 Proposed 升 Accepted) |
| **新增** | `docs/notes/proposed/seam/2026-09-04-model-visible-bus-alignment.md` 移至 `implemented/seam/`,Status 改 `implemented`,`## Proposal` 改写为 `## Decision` |
| **新增** | `tests/architecture/test_event_bus_invariants.py` 扩展 5 条 I-MV 测试 |
| **修改** | `docs/adr/README.md` 第 130 行索引加 `[0185](0185-...)` 一行 |
| **架构测试** | 新增 `test_i_mv_3`(禁读 model_visible 目录)+ `test_i_mv_4`(禁 Brain/Reasoner publish model-visible)+ `test_i_mv_5`(fold 字节级判等);旧 ADR-0169 I-MV1 测试删 |
| **验收** | `rg "StdModelVisibleCapture\|StdReasonerPromptCapture\|ModelVisibleCapture\|ModelVisibleLLMAdapter\|CurrentReasonerPrompt\|model_visible/" lca/ lca_kernel/ profiles/ tests/` = 0(白名单:`docs/adr/0*.md` 历史归档 + `tests/architecture/test_*.py` 负向断言);`uv run pytest tests/ -q` 全过;`uv run lca-ops runs create --user-text "ping"` 端到端通过;viewer 渲染模型可见输入完整 |
| **delete-when** | N/A(终态) |

## 6. 与现有 ADR / Note 的关系

| 既有 | 处置 |
|---|---|
| **ADR-0169 D7 I-MV1** "model_visible 5 件套 SSOT" | **Superseded**(本 ADR §3.6);新 I-MV-2 接管 |
| **ADR-0175 D3** "ReasonerPrompt 单独 capture" | **Superseded**(由 `ModelVisiblePublisher` 内部处理 system prompt);字段合并进 `SpineLlmRequestHeaderPayload.system` |
| **ADR-0176 D4** "system.json 合并到 messages.json" | **Superseded**(整个 `model_visible/` 目录删除) |
| **ADR-0183** "事件总线框架 + 单 SSOT" | **延伸**(本 ADR 严格走其 §3.1/3.2/3.5/3.7 seam;不破坏 I-FW-* 不变量;强化 I-FW-SSOT-1 删旁路) |
| **ADR-0181** "spine as publishers/subscribers" | **延伸**(model-visible publisher 走同一 publisher 范式) |
| **ADR-0184** "事件生命周期受管理投递" | **不冲突**(本 ADR 是 producer 形态;ADR-0184 是投递保障;两者互补) |
| **Note `2026-09-03-model-visible-incomplete-projection.md`**(assistant 没投影 + tools 空 + system 错塞 user) | **顺手修复**(本 ADR §3.2 `PostDispatchHook` 拿 assistant;§3.3 payload 走 `ToolSchema.to_openai_dict()` 显式序列化;§3.3 `system` 字段独立,`messages` 不做 system 探测) |
| **Note `2026-09-04-plugin-universe-single-entry.md`**(proposed)PR-4 | **不冲突**(本 ADR 的 `ModelVisiblePublisher` 走 PR-4 的"事件组件补 `@plugin`"路径,自然落到该 PR 范围内) |
| **Note `2026-09-04-event-bus-publisher-authorization.md`** | **延伸**(model-visible 是 17 个授权 publisher 之一,直接对接) |
| **deepseek-harness `request/header`** | **对齐**(字段名 + fold 语义 + reason 取值;实现细节独立;fold 模块 1:1 翻译 `request-header.ts`) |

## 7. 风险与回滚

| 风险 | 缓解 |
|---|---|
| **journal 体积膨胀**(原文每次 change 都塞) | `headerEquals` fold 优化(PR-0 fold 模块 + PR-2 publisher 内部状态);实测:100 step run 期望 ~10-20 个完整 header 事件,不是 100 |
| **viewer 改造面大**(`lca-ops` + webserver handler) | PR-3 只迁 core viewer/CLI;PR-3.1 迁 handlers/doctor;integration 测试夹具断言 fold 输出 |
| **PR-4 删旁路文件影响旧 viewer / 旧 run** | 旧 run 的 `<run_dir>/model_visible/` 文件保留但不再被读;viewer 走 fold 后报错信息明确("该 run 是旧格式,无法 fold");迁移窗口 14 天 |
| **`ModelVisibleHook` per-instance 状态 + ContextVar 隔离** | 与现有 `CurrentReasonerPrompt` ContextVar 同样实现,基于 ADR-0169 D5 已验证的 ContextVar 模式 |
| **assistant payload 与现有 `body.tool.execute.*` / `spine.tool.*` 重复** | `SpineLlmRequestHeaderAssistantPayload` 只承担"模型可见上下文"语义,**不**承担 tool 执行证据;后者仍走 `spine.tool.*` EP。架构测试断言两类事件字段不重叠 |
| **`foldRequestHeader` 的 Python 实现跟 dsh TS 版语义漂移** | PR-0 1:1 翻译 dsh 测试 case;任何字段级差异都要 PR body 显式说明 |
| **与 ADR-0169 / 0175 / 0176 废止影响历史追溯** | 旧 ADR 全文保留(`Superseded by` 注脚),不被 git rm;`_capture_io` 等历史文件进 `docs/notes/archive/` |
| **PR-0 落地的 fold 模块在没 producer 之前是个孤儿** | PR-0 的 fold 模块自带单测 + CLI `lca-ops fold-test` 验证(可用现成 spine.jsonl fixture 测试) |

**回滚**:6 个 PR 各自独立 revert。PR-0 / PR-1 / PR-2 只动加法,回滚成本最低;PR-3 动 core viewer/CLI,回滚后旧路径恢复;PR-3.1 动 webserver handlers/doctor;PR-4 动 producer 端 + 删旧文件,回滚后旧 capture 路径恢复(双轨期保证)。

## 8. 试点判定(每个 PR 合并前必答)

### 8.1 PR-0 合并前

1. **fold 模块与 dsh 字节级一致**:`tests/lca_kernel/events/test_fold_dsh_parity.py` 1:1 翻译 dsh 6 种 fixture,全过
2. **fold 模块无 I/O**:`rg "open(\|Path(\|read\|write" lca_kernel/events/fold.py = 0`
3. **类型化 fold**:`mypy lca_kernel/events/fold.py --strict` exit 0

### 8.2 PR-1 合并前

4. **类型化字段不破坏现有 payload**:跑 `tests/lca_kernel/events/` + EventBus 集成测试,所有原发出去的 payload 通过 schema 校验
5. **yaml 装载**:`lca-ops validate-events web-standard` exit 0;`lca-ops inspect-pipeline web-standard` 可见 2 个新 category

### 8.3 PR-2 合并前

6. **fold 优化生效**:连续两次同 header,`bus.publish` 只被调一次(首次)
7. **assistant payload 由 post hook 发**:mock LLM adapter 返回 assistant content 后,`bus.publish` 被调 2 次(request/header + request/header.assistant)
8. **I-FW-BUS-1 不破坏**:reducer / cursor / runtime_loop 仍无直写 spine / 直调 sink

### 8.4 PR-3 合并前

9. **端到端事件计数一致**:`uv run lca-ops runs create --user-text "ping"` 产生的 spine.jsonl 含 2 类 model-visible 事件
10. **core viewer 渲染完整**:`lca-ops explain` / journal trajectory / verify-model-visible 显示 system 全文 + tools + messages + assistant
11. **旧 capture 路径仍可运行**(双轨):`StdModelVisibleCapture.capture(...)` 单独调用不报错;生产代码不再调用(composer `instrument_llm` 例外,delete-when PR-4)

### 8.4.1 PR-3.1 合并前

11a. **handlers 走 fold**:webserver trace / explain / doctor 不再硬编码反查 `<run_dir>/model_visible/`
11b. **doctor 非全零**:默认 `<run_id>.spine.jsonl` 布局下 H-xref / model-visible hop 计数可用

### 8.5 PR-4 合并前

12. **5 条 I-MV 不变量全部由架构测试守护**:`tests/architecture/test_event_bus_invariants.py` 全过
13. **旧 ADR Superseded 注脚**:docs/adr/0169 / 0175 / 0176 头部加注脚,正文保留
14. **PR-4 后端到端不回归**:`uv run lca-ops runs create --user-text "ping"` 端到端通过;viewer 渲染完整

## 9. 落地工具(commands)

```sh
# PR-0: fold 模块测试
uv run pytest tests/lca_kernel/events/test_fold.py tests/lca_kernel/events/test_fold_dsh_parity.py -q

# PR-1: EventPayload 类型化 + yaml 注册
uv run lca-ops validate-events web-standard
uv run lca-ops inspect-pipeline web-standard

# PR-2: Publisher 测试
uv run pytest tests/plugins/events/publishers/model_visible/ -q

# PR-3: 端到端(core viewer)
uv run lca-ops runs create --user-text "ping"
uv run pytest tests/integration/test_model_visible_e2e.py tests/architecture/test_model_visible_fold.py tests/plugins/events -q

# PR-3.1: handlers / doctor
uv run pytest tests/plugins/transport/webserver -q

# PR-4: 收尾 + 架构测试
uv run pytest tests/ tests/integration tests/architecture tests/plugins/events -q
rg "StdModelVisibleCapture|StdReasonerPromptCapture|ModelVisibleCapture|ModelVisibleLLMAdapter|CurrentReasonerPrompt|model_visible/" lca/ lca_kernel/ profiles/ tests/

# 架构测试(每个 PR 都要)
uv run pytest tests/architecture/test_event_bus_invariants.py -v
```
