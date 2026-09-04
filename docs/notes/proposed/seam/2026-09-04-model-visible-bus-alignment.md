# Agent Note: Model-Visible 走 ADR-0183 统一 event bus — plugin 化 producer + fold 重建

Status: proposed

实施进度(与 ADR-0185 §状态同步,2026-09-04):PR-0~PR-3 已合并;PR-3.1 webserver handlers + doctor fold 进行中(`feat/adr-0185-pr-3.1-handlers`);PR-4 删旁路 + Note 迁 `implemented/` 未合并(另 agent)。本 Note 仍留 `proposed/` — Status 与路径对齐,PR-4 合并后再翻 `implemented`。

## Problem

当前 `lca.infrastructure.observability.loop_cursor` 下的 model_visible 实现走**旁路文件** + **digest 留痕**两条路径,违反 ADR-0183 "统一 event bus 单 SSOT" 的精神,且与 deepseek-harness 的"model-visible ⟺ logged" 设计原则方向不一致。三个具体缺陷:

1. **绕开统一总线**:`StdModelVisibleCapture` 把 6 件套(`<run_dir>/model_visible/step_<NN>/{system,tools,messages,manifest,inherited}.json`)写到旁路文件,spine 上的 `llm.request.header` EP 只带 `sha256:<hex>` digest + relpath,不带原文。业务上和 ADR-0183 I-FW-SSOT-1 `<run_id>.spine.jsonl` 唯一 SSOT 共存两条真值链。
2. **journal 不自含**:viewer / `lca-ops explain <run_id>` / `journal replay --diff-only` / webserver trajectory 必须反查文件系统 + digest 校验才能重建模型所见输入;dsh 的 `foldRequestHeader` 一遍纯函数就能重建,LCA 做不到。
3. **assistant 输出不可重建**:`docs/notes/implemented/seam/2026-09-03-model-visible-incomplete-projection.md` 已记录此 BUG — `capture` 在 LLM 调用**之前**跑(`model_visible_llm_adapter.py:_run_capture`),assistant 回复、tool_calls、finish_reason、usage 全部不在 messages 序列里;tools.json 22 条全空 `{}`(`_to_jsonable` repr 回退到空);system 模板被错塞到 `messages[0].role=user`(上游 reasoner bug,capture 没探测)。

深 seek 对齐参考:deepseek-harness `packages/core/agent-loop/src/agent.ts:498-517` 在 agent-loop 调 LLM **之前**主动 emit `request/header` 事件,payload **带原文**(`config` + `system` + `tools`),用 `foldRequestHeader(events, from?)` 离线 fold 重建 + `headerEquals(a, b)` 字节级 fold 优化避免 journal 爆炸。`AGENTS.md:111` 明文写:**"Model-visible ⟺ logged: anything that reaches a model request must be reconstructable from the session log; a new model-visible input requires a session event."**

## Proposal

新增**独立 `@plugin` producer** `lca.plugins.events.publishers.model_visible`,作为 `spine.llm.request.header` + `spine.llm.request.header.assistant` 两类 spine event 的**唯一授权生产者**,严格走 ADR-0183 统一 event bus。payload **带 system/tools 原文**对齐 dsh;由 `ModelVisibleHook` 在 LLM adapter 边界 pre/post 拦截;内部用 `headerEquals` fold 优化;**删 6 件套旁路文件**,viewer 从 `<run_id>.spine.jsonl` fold 重建。

### 新增 producer plugin

`lca/plugins/events/publishers/model_visible/publisher.py` 一个 `@plugin(...)` 装饰器,跟 15 个 `spine_reflector_*` 同形态、同声明范式。`requires=["event.bus", "llm.adapter", "cursor"]`,`provides=["event.bus.publisher.model_visible"]`,`event_publishes=("spine.llm.request.header", "spine.llm.request.header.assistant")`,`effects=(EffectClass.NONE,)`(只走 spine,不写旁路文件)。`setup_model_visible_publisher(ctx, config)` 在 Profile 启动时把 `ModelVisibleHook` 挂到 LLM adapter 装饰器链。

### 新增 hook(非 plugin)

`lca/plugins/events/hooks/model_visible/hook.py` 实现 ADR-0183 §3.2 的 `PreDispatchHook` + `PostDispatchHook` Protocol 两个(只实现用到的,其他不实现):

- **`before_publish(payload, producer, ctx)`**:从 ContextVar `CurrentReasonerPrompt` 拿渲染好的 system prompt + sections 元数据,从 LLM adapter kwargs 拿 `tools` / `messages` / `manifest`,从 cursor snapshot 拿 `step_id` / `incarnation`。用 `headerEquals(prev, current)` 判等:首次发 reason=`initial`;变化发 reason=`change`;同 header 开新 series 发 reason=`series`(供 retry / fail-over 场景);完全相同不发。状态在 hook instance 上 per-cursor 维护,ContextVar 隔离多 run。
- **`after_dispatch(payload, ref, results)`**:从 `results` 收集 assistant content / tool_calls / finish_reason / usage,发 `SpineLlmRequestHeaderAssistantPayload`,`header_digest` 字段关联回最近一条 `spine.llm.request.header`。**顺手修复** Note `2026-09-03-model-visible-incomplete-projection.md` 的 3 个 BUG。

### 新增 payload 类(走 ADR-0183 §3.7 类型化)

`lca_kernel/events/payloads/model_visible.py` 两个 dataclass 继承 `EventPayload`,每个字段标 `FieldType`,由 `EventRegistry` 在装载期校验:

```python
@dataclass(frozen=True)
class SpineLlmRequestHeaderPayload(EventPayload):
    category: Category = Category("spine.llm.request.header")
    step_id: str                              # STR
    incarnation: int                          # INT
    config: AssistantRequestConfig            # JSON
    system: str                               # STR (← 原文,system prompt 全文)
    tools: tuple[ToolSchema, ...]             # JSON (← 原文,tool schema 列表)
    messages: tuple[MessageDict, ...]         # JSON (← 原文,发给 LLM 的消息序列)
    manifest: ContextManifest                 # JSON
    reason: Literal["initial", "resume", "change", "series"]   # STR
    previous_header_digest: str | None        # STR (sha256:...,用于 fold 校验)

@dataclass(frozen=True)
class SpineLlmRequestHeaderAssistantPayload(EventPayload):
    category: Category = Category("spine.llm.request.header.assistant")
    step_id: str
    incarnation: int
    assistant_content: str                    # STR
    tool_calls: tuple[ToolCallDict, ...]      # JSON
    finish_reason: str                        # STR
    usage: UsageDict                          # JSON
    header_digest: str                        # STR (关联回 request/header)
```

yaml 注册:`lca_kernel/events/config/observability/spine.yaml` 新增 2 个 category,带 `payload_class` + `fields:` + `FieldType`(对齐 ADR-0183 §3.7)。

### 新增 fold 模块(对齐 dsh `packages/core/session/src/request-header.ts`)

`lca_kernel/events/fold.py` 1:1 翻译 dsh 的 `canonicalHeader` / `headerEquals` / `foldRequestHeader`:

- `canonicalHeader(header: EpochHeader) -> EpochHeader`:空 system / 空 tools 字段归一为 absent
- `headerEquals(a: EpochHeader, b: EpochHeader) -> bool`:字节级判等(走 `JSON.stringify` 比对 tool schemas,tools 顺序敏感)
- `foldRequestHeader(events: Iterable[SpineEventRecord], from_: EpochHeader | None = None, step_id: str | None = None) -> EpochHeader | None`:扫一遍事件流,fold 出"指定 step_id 在最后一个生效 header 时的状态"

这把"什么时候该 fold 什么"和"如何 fold"两件事**拆成两个 Protocol**:

- `FoldProvider` Protocol:`fold(events, *, step_id, from_) -> EpochHeader | None`
- `FoldPolicy` Protocol:`should_fold(prev, current, *, reason) -> bool`(决策:发 / 不发 / 发哪种 reason)

`ModelVisiblePublisher` 内部默认实现都用 fold 同一份真值,**禁止** fold 模块走 I/O(纯函数,可单测)。

### 删旁路文件

7 个文件整体删除,旧 viewer 反查路径改为 fold:

| 删 | delete-when |
|---|---|
| `loop_cursor/model_visible_capture.py`(`StdModelVisibleCapture`) | `rg "StdModelVisibleCapture" lca/ = 0` |
| `loop_cursor/reasoner_prompt_capture.py`(`StdReasonerPromptCapture`) | `rg "StdReasonerPromptCapture" lca/ = 0` |
| `contracts/observability/model_visible_capture.py`(Protocol) | `rg "ModelVisibleCapture" lca/ = 0` |
| `loop_cursor/model_visible_binding.py` + `model_visible_capture.py`(ContextVar) | `rg "CurrentReasonerPrompt" lca/ = 0` |
| `adapters/model_visible_llm_adapter.py`(装饰器) | `rg "ModelVisibleLLMAdapter" lca/ = 0` |
| `loop_cursor/_capture_io.py` | 由 EventBus `_to_jsonable` 统一处理 |
| `<run_dir>/model_visible/` 目录约定(docs / viewer / tests) | `rg "model_visible/" lca/ lca_kernel/ profiles/ = 0` |

**废 ADR-0169 D7 I-MV1** "每次真实 LLM 请求,必须存在可解析的 `ModelVisibleArtifact` 与 `llm.request.header` EP",由新不变量 **I-MV-2** 接管:"每次 LLM 请求,`foldRequestHeader(<run_id>.spine.jsonl, step_id)` 可重建 effective header;缺失则 fail-fast(等价 dsh `requestHeader()` 行为)"。

### PR 切分(6 PR,全部独立可 revert)

PR-0 spike 验证 fold 模块与 dsh 字节级一致,作为后续 PR 的语义锚点。

```
PR-0 spike:fold 模块 1:1 翻译 dsh request-header.ts + 5 种场景单测   [已合并]
  └─→ PR-1 (EventPayload 类型化 + yaml 注册 2 个 category)          [已合并]
        └─→ PR-2 (ModelVisiblePublisher + Hook;双轨共存)            [已合并]
              └─→ PR-3 (core viewer / CLI / replay 迁 fold;双轨)     [已合并]
                    ├─→ PR-3.1 (webserver handlers + doctor fold)    [进行中]
                    └─→ PR-4 (删旁路文件 + 废 ADR + 收尾)            [未合并 / 另 agent]
```

### 现有可复用资产(本提案零新开平行机制)

| 资产 | 复用方式 |
|---|---|
| 15 个 `spine_reflector_*` 模板(`lca/plugins/events/publishers/spine_reflector_*/plugin.py`) | 复用 `@plugin` 装饰器范式 + setup 函数形态 |
| ADR-0183 §3.3 Pipeline YAML(`profiles/event-pipeline/web-standard.yaml`) | PR-4 `consumer_rules:` 增 prefix `spine.llm.request.header.*` 把 model-visible 加入默认订阅 |
| `EventBus.publish(payload, *, producer=...)`(`lca_kernel/events/bus.py`) | Producer 直接调,满足 I-FW-BUS-1 |
| `EventPayload` 基类 + `FieldType`(`lca_kernel/events/payloads.py`) | 两个新 payload 继承 |
| dsh `canonicalHeader` + `headerEquals` + `foldRequestHeader`(`deepseek-harness/packages/core/session/src/request-header.ts`) | 1:1 翻译成 Python(语义保持一致;走 `lca_kernel/events/fold.py`) |
| `EventRegistry` yaml 装载(`lca_kernel/events/registry.py`) | PR-1 新增 2 个 category,yaml 自动装载 |
| `consumer_rules:` 前缀规则(`lca_kernel/events/config_parser.py`) | 路由 `spine.llm.request.header.*` 给 viewer / exporter |
| `@plugin` Manifest(`lca/harness/plugin_api.py`) | 跟 15 个 reflector 同形 |
| `SpineReader.events(run_id)`(`lca_kernel/events/reader.py`) | viewer 直接读 + fold,不再走 reader 的"反查 model_visible/" 路径 |

## Wire contract

### 字段语义(对齐 dsh,自含可重建)

`SpineLlmRequestHeaderPayload`:

| 字段 | 类型 | 语义 |
|---|---|---|
| `step_id` | str | 由 cursor.snapshot 派生;fold 的 key |
| `incarnation` | int | 同 step 多次 retry 计数 |
| `config` | AssistantRequestConfig | provider/model/sampling |
| `system` | str | **完整 system prompt 文本**(Brain 渲染后,Reasoner 注入到 ContextVar 的 `CurrentReasonerPrompt.system_prompt_text`) |
| `tools` | tuple[ToolSchema] | **完整 tool schema 列表**(OpenAI 兼容 dict 形式) |
| `messages` | tuple[MessageDict] | **发给 LLM 的消息序列**(role: system/user/tool 多角色) |
| `manifest` | ContextManifest | 上下文 manifest(附件 / 客观 / 记忆种类清单) |
| `reason` | Literal["initial", "resume", "change", "series"] | 为什么本 step 在此发 header(对应 dsh `reason` 语义) |
| `previous_header_digest` | str \| None | sha256(上一 header 的 canonical 形式),用于 fold 校验;`None` 表示本 step 是初始 |

`SpineLlmRequestHeaderAssistantPayload`:

| 字段 | 类型 | 语义 |
|---|---|---|
| `step_id` | str | 与关联的 `request/header` 同 |
| `incarnation` | int | 与关联的 `request/header` 同 |
| `assistant_content` | str | LLM 文本回复 |
| `tool_calls` | tuple[ToolCallDict] | LLM 发出的 tool 调用(参数完整) |
| `finish_reason` | str | `stop` / `tool_calls` / `length` / `content_filter` |
| `usage` | UsageDict | token 计数(prompt / completion / total) |
| `header_digest` | str | sha256(关联回最近一条 `request/header` 的 canonical header) |

### 字节布局(走 ADR-0183 §3.5 `SpineEventRecord.to_dict()` SSOT)

plugin 不可改 `to_dict()` 字节布局;`SpineSink.append(record)` 落 `<run_id>.spine.jsonl`。本提案不破坏此约束。

### Fold 优化行为契约(由 `FoldPolicy` Protocol 钉死)

| 上一状态 | 当前 header | reason | 写盘? |
|---|---|---|---|
| None | 任意 | `initial` | ✅ 写 |
| 上 header | `headerEquals(prev, current) == True` | (不发) | ❌ 不写 |
| 上 header | `headerEquals(prev, current) == False`,system 字段变 | `change` | ✅ 写 |
| 上 header | `headerEquals(prev, current) == False`,tools 字段变 | `change` | ✅ 写 |
| 上 header | `headerEquals(prev, current) == True`,但开新 series | `series` | ✅ 写(fold 不依赖 reason 即可重建) |
| 任意 | 任意 | `resume`(checkpoint 恢复) | ✅ 写 |

注:`resume` 由 `cursor.snapshot` 的 `inherited_from_step` 字段触发,语义与 dsh 一致。

## Alternatives considered

### Why not 把 model-visible 当作"派生 sink"挂 Pipeline YAML,producer 继续走旁路文件?

事实是 ADR-0183 §3.4 `SinkBackend` Protocol 是落盘后端协议(`append` / `flush` / `close`),不是事件生产者。model-visible 的语义是"LLM 边界真实捕获"(ADR-0169 D7 原文),需要拦截 pre/post LLM 调用两个时间点,Pure 落盘 sink 不能表达 pre/post 时序。SinkBackend 适合做"原文二次落盘",不适合做"LLM 边界拦截"。**producer + hook 协议是 ADR-0183 §3.1/3.2 已有的 seam,直接复用最干净**。

### Why not 不写 dsh 风格 fold,让 `SpineLlmRequestHeaderPayload` 每次 LLM 调用都无条件发(原文)?

事实是 100 step run 每次都带 system 原文 + 完整 tools 列表 + 完整 messages 序列,journal 体积膨胀 5-10x;且 `foldRequestHeader` 不再是纯函数(因为"无 fold 等价"语义丢失,viewer 必须扫所有事件)。dsh 用 `headerEquals` fold 是用一次内存计算的代价换 journal 体积可控;LCA 在 100+ step run 的实际负载下,journal 体积已经是可观测指标(ADR-0183 §1.7 痛点 5 提到 1614 行 yaml / 100 处 `subscribers:`)。**fold 优化是不可让步的设计**。

### Why not 不删 `<run_dir>/model_visible/` 旁路文件,作为"SinkBackend 派生后端"继续保留?

事实是 dsh 没有旁路文件,session log 自含;LCA 留旁路文件会让"viewer 优先读文件还是 spine"出现两套真值,违反 ADR-0183 I-FW-SSOT-1 `<run_id>.spine.jsonl` 唯一 SSOT;且旧 `<run_dir>/model_visible/` 的 `_to_jsonable` repr 回退 bug 不会消失(只是从 capture 路径挪到 sink 路径)。**唯一干净做法是把真值搬到 spine,旧旁路文件删干净**。

### Why not 让 `ModelVisibleHook` 直接是 `@plugin` 而不是 publisher 内嵌?

事实是 ADR-0183 §3.2 hook 通过 Pipeline YAML 装载,`@plugin` 是另一种声明形态;同时挂两者会导致"hook 装载但 producer 没装"或反之的孤儿态。`@plugin` + 内部挂 hook 是 15 个 reflector 的既有范式(`spine_reflector_*` 都同时挂 publisher manifest + setup 时挂 cursor 反射),沿用最稳。**hook 作为 producer 内嵌的 setup 行为,不是平行声明**。

### Why not 走 dsh 的"agent-loop 在调 LLM 前主动 emit"路径,不挂 hook?

事实是 dsh 的 emit 点在 `agent.ts:508`(`this.session.append('request/header', { header, reason: ... })`);LCA 调 LLM 的入口在 `lca/infrastructure/observability/adapters/model_visible_llm_adapter.py:_run_capture` 或更上游的 Brain / Reasoner,**没有单一"调 LLM 前"的语义点**。Brain / Reasoner 不持有完整 tools 列表(messages 在更下游),cursor.record_request_header 不持有原文(digest 路径)。**挂 hook 是 LCA 唯一能在"调 LLM 边界"拦截到完整 tools + messages + system + manifest 的点**。

### Why not PR-0 spike 用纯 Python 测试,不做 1:1 dsh TS 测试 case 翻译?

事实是 dsh `request-header.ts` 的 `canonicalHeader` / `headerEquals` 都有详细单测覆盖(空 system/空 tools 归一化、tools 顺序敏感、config 字段逐个比对等);1:1 翻译确保"未来 LCA fold 行为变化时,能立即发现跟 dsh 漂移",这是对齐参考点的核心价值。**纯 Python 单元测试覆盖不到"跟 dsh 语义一致"这件事**。

## Acceptance criteria

- `uv run pytest tests/ tests/integration tests/architecture tests/plugins/events -q` 全过(0 失败、0 xfail 退化)
- `uv run lca-ops validate-events web-standard` exit 0;`spine.llm.request.header` + `.assistant` 在 `lca-ops inspect-pipeline web-standard` 输出可见
- 端到端 fixture:`uv run lca-ops runs create --user-text "ping"` 产生的 `<run_id>.spine.jsonl` 含 ≥1 条 `spine.llm.request.header` 事件(reason=initial)+ ≥1 条 `spine.llm.request.header.assistant` 事件;`foldRequestHeader(spine.jsonl, step_id=...)` 重建的 header 与 LLM adapter 实际发的字节级相等
- `rg "StdModelVisibleCapture\|StdReasonerPromptCapture\|ModelVisibleCapture\|ModelVisibleLLMAdapter\|CurrentReasonerPrompt\|model_visible/" lca/ lca_kernel/ profiles/ tests/` = 0(白名单:`docs/adr/0*.md` 历史归档 + `tests/architecture/test_*.py` 负向断言)
- `lca-ops explain <run_id>` 与 webserver trajectory viewer 渲染模型可见输入完整(系统提示全文 + 工具 schema + 消息序列 + assistant 回复 + tool_calls),不再反查文件系统
- `tests/lca_kernel/events/test_fold.py` 覆盖 5 种 fold 场景:首次发、同 header 不发、system 变化发、tools 变化发、开新 series 发;`tests/lca_kernel/events/test_fold_dsh_parity.py` 1:1 翻译 dsh `request-header.test.ts` 的 fixture(空 system / 空 tools / tools 顺序 / config 字段差异)
- 5 条 I-MV 不变量全部由架构测试守护(`tests/architecture/test_event_bus_invariants.py` 扩展):
  - I-MV-1: `ModelVisiblePublisher` 是 `spine.llm.request.header.{,assistant}` 唯一授权 producer(yaml 白名单)
  - I-MV-2: `foldRequestHeader(<run_id>.spine.jsonl, step_id)` 可重建 effective header;缺失则 fail-fast
  - I-MV-3: 禁止读 `<run_dir>/model_visible/` / 写 `loop_cursor/model_visible_*.py`
  - I-MV-4: 禁 Brain / Reasoner / Body / Agent publish model-visible EP
  - I-MV-5: fold 用 `headerEquals` 字节级判等 + `canonicalHeader` 归一化

## Risks

| 风险 | 缓解 |
|---|---|
| **journal 体积膨胀**(原文每次 change 都塞) | `headerEquals` fold 优化(PR-0 fold 模块 + PR-2 publisher 内部状态);实测:100 step run 期望 ~10-20 个完整 header 事件,不是 100 |
| **viewer 改造面大**(`lca-ops` + webserver handler) | PR-3 只迁 core viewer/CLI;PR-3.1 迁 handlers/doctor;integration 测试夹具断言 fold 输出 |
| **PR-4 删旁路文件影响旧 viewer / 旧 run** | 旧 run 的 `<run_dir>/model_visible/` 文件保留但不再被读;viewer 走 fold 后报错信息明确("该 run 是旧格式,无法 fold");迁移窗口 14 天 |
| **`ModelVisibleHook` per-instance 状态 + ContextVar 隔离** | 与现有 `CurrentReasonerPrompt` ContextVar 同样实现,基于 ADR-0169 D5 已验证的 ContextVar 模式 |
| **assistant payload 与现有 `body.tool.execute.*` / `spine.tool.*` 重复** | `SpineLlmRequestHeaderAssistantPayload` 只承担"模型可见上下文"语义,**不**承担 tool 执行证据;后者仍走 `spine.tool.*` EP。架构测试断言两类事件字段不重叠 |
| **`foldRequestHeader` 的 Python 实现跟 dsh TS 版语义漂移** | PR-0 spike 1:1 翻译 dsh 的测试 case;任何字段级差异都要 PR body 显式说明 |
| **与 ADR-0169 / 0175 / 0176 废止影响历史追溯** | 旧 ADR 全文保留(`Superseded by` 注脚),不被 git rm;`_capture_io` 等历史文件进 `docs/notes/archive/` |
| **PR-0 落地的 fold 模块在没 producer 之前是个孤儿** | PR-0 的 fold 模块自带单测 + `lca-ops fold-test web-standard` CLI 验证(可用现成 spine.jsonl fixture 测试) |

## Migration plan

PR 落地顺序与现状:

1. **PR-0 spike**【已合并 `1eefe053`】:`lca_kernel/events/fold.py` + fold / dsh-parity 单测。纯加法。
2. **PR-1 类型化 + yaml 注册**【已合并 `b0723d55`】:`SpineLlmRequestHeaderPayload` + `SpineLlmRequestHeaderAssistantPayload` + `spine.yaml` 2 category。纯加法。
3. **PR-2 Publisher + Hook**【已合并 `a334098e`】:`ModelVisiblePublisher` + `ModelVisibleHook` + bundle 一行。双轨共存。
4. **PR-3 core viewer / CLI / replay**【已合并 `6ce3bc0e`】:`fold_source` + `StandardCursor` fold 优先 + journal CLI。双轨共存。webserver handlers 不在本 PR。
5. **PR-3.1 handlers + doctor fold**【进行中】:webserver `handlers/runs/{trace,explain,doctor,...}` 切 spine fold;doctor step_check 用 fold 计数。
6. **PR-4 删旁路 + 废 ADR**【未合并;另 agent】:删 sidecar 文件 + 旧 ADR Superseded 注脚 + 本 Note 迁 `implemented/seam/` + ADR 状态翻 `Accepted(落地完成)`。终态 `rg` 旧路径 = 0。

## Related

- `lca/infrastructure/observability/loop_cursor/model_visible_capture.py` — 即将删除
- `lca/infrastructure/observability/loop_cursor/reasoner_prompt_capture.py` — 即将删除
- `lca/contracts/observability/model_visible_capture.py` — 即将删除
- `lca/infrastructure/observability/adapters/model_visible_llm_adapter.py` — 即将替换
- `lca_kernel/events/bus.py` — 复用 EventBus.publish
- `lca_kernel/events/payloads.py` — 复用 EventPayload 基类
- `lca_kernel/events/registry.py` — yaml 装载新增 2 个 category
- `lca/plugins/events/publishers/spine_reflector_*/plugin.py` — 复用 @plugin 装饰器范式
- `deepseek-harness/packages/core/agent-loop/src/agent.ts:498-517` — 对齐参考
- `deepseek-harness/packages/core/session/src/request-header.ts` — 1:1 翻译源
- ADR-0183 §3.1 / §3.2 / §3.5 / §3.7 / I-FW-BUS-1 — 复用 seam
- ADR-0169 D7 I-MV1 — 即将废止
- ADR-0175 D3 — 即将废止
- ADR-0176 D4 — 即将废止
- Note `2026-09-03-model-visible-incomplete-projection.md` — 顺手修复
- Note `2026-09-04-plugin-universe-single-entry.md` PR-4 — 不冲突,本提案走其路径
