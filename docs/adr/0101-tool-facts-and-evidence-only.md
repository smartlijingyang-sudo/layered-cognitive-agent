# ADR-0101: Tool 事件回归事实 —— arguments/output 经 Evidence 平面，journal 不再携带渲染字段

## 状态

**Proposed — 2026-08-29。** 取代 ADR-0065 §四 中"typed UI state"段对 tool 事件的设计（保留其余全部内容）。本文是该方向的**根因裁决 + 一刀切方案**，不再"补 key"。

> **核心决策：journal 的 tool 事件只携带事实（tool_name、invocation_id、ok/error、latency_ms、attempt、files）。调用参数和调用结果是事实，但它们**走 EvidenceStore 平面**——journal 上只有一个 `arguments_ref` / `output_ref` 指针。渲染（terminal 块 / code 块 / tree / 文件树）由 LobeHub renderer registry 按 `tool_name` 派发，与 journal 无关。前端零改动即可拿到全部参数。**

---

## 0. 阅读顺序

1. §1 现象 —— 看清单Files 为什么丢参数
2. §2 第一性原理 —— 三个平面分清职责
3. §3 根因 —— 为什么打补丁无效
4. §4 一次性删除清单
5. §5 新的最小模型
6. §6 插件化路径
7. §7 与既有 ADR 的关系
8. §8 实施序列
9. §9 验收规约

---

## 1. 现象（2026-08-29 run_860f61bf4b53 实测）

一次"给当前目录写个有趣的解读"任务。Agent 调用 listFiles 7 次，writeFile 1 次，runCommand 1 次，exportFile 1 次。

实际落到 journal 上的 tool 事件 `data` 字段（**全部 16 个事件**）：

| 事件类型 | 数量 | data 中实际出现的字段 |
|---|---|---|
| `ToolCallStreaming` | 117 | `tool_name`, `tool_call_id` |
| `ToolStarted` | 7 | `tool_name`, `invocation_id`（偶尔 `command`, `description`） |
| `ToolInvoked` | 7 | `tool_name`, `ok`, `latency_ms`, `attempt`, `invocation_id`, `files`（+ `error`/`output_text` 失败时） |

listFiles 传了 `{"directoryPath": "/home/lichao/layered-cognitive-agent"}`。**journal 找不到 directoryPath**。前端拿不到。命令展示为空。

## 2. 第一性原理：三个平面，三个主语

```
┌────────────────────────────────────────────────────────────────┐
│ 事实账本（journal）                                              │
│   主语 = "发生了什么"                                            │
│   关心: tool_name / invocation_id / ok / latency / files        │
│   不关心: 参数长什么样、结果怎么画                                │
├────────────────────────────────────────────────────────────────┤
│ 证据平面（EvidenceStore）                                        │
│   主语 = "真实数据"                                              │
│   关心: arguments 原文 / output 原文 / stdout / stderr / files   │
│   不关心: 谁来画                                                │
├────────────────────────────────────────────────────────────────┤
│ 渲染平面（LobeHub renderer registry）                            │
│   主语 = "怎么画"                                                │
│   关心: terminal / code / tree / file / json                    │
│   不关心: 数据从哪儿来（只要有 ref）                             │
└────────────────────────────────────────────────────────────────┘
```

**判定**：参数和结果是"真实数据"，归证据平面；不是"事实"也不是"渲染"。它们当前被错放在事实账本里，被错用 view-only 标签剥离，被错用 6-key 白名单裁剪，被错用 dict 逃逸口塞回。三套错位互相纠缠，每次有人补一个 key 就漏三个。

## 3. 根因：双轨 schema + view-only 错分类

现状是两次演化的尸体：

```
演化 1（2026-08-21 之前）：
  ToolStarted.plugin_state: dict  ← 自由 dict 逃逸口，承载了所有参数
  后果：dict 没有 schema, 无法审计, 无法 typed UI

演化 2（ADR-0065 §四）：
  ToolStarted.code / command / language / skill_id / description / execution_env
  副作用：ToolStarted.arguments_preview / result_preview / plugin_state / output_truncated
          全部打成 "view-only"，从 disk 剥离
  后果：listFiles 的 directoryPath 不在 6 个 key 里 → 静默丢失
```

**根因不是"白名单漏了哪个 key"，而是试图用一个 6 字段 union 表达所有工具的全部参数签名**——类型上做不到。每次补一个 key（例如 `path`），下一个工具（例如 `grepContent` 的 `pattern`）仍然不在白名单。补丁路径是死路。

更深一层：**`arguments_preview` / `plugin_state` 被标 view-only 是分类错误**。它们不是"渲染细节"，它们是"参数原文"——事实。"view-only" 应该只描述"是否被截断"这种 UI 元数据，不是参数本身。

## 4. 一次性删除清单

按"从外向内"顺序。每条都对应一类垃圾机制，删完不留尾巴。

### 4.1 journal_io：view-only 概念整个消失

**文件**：`lca/layer0_infra/observability/journal/journal_io.py`

- ❌ 删 `_is_view_only_field()`
- ❌ 删 `_strip_view_only_data()`
- ❌ 删 `stamped_to_record` 里的 `_strip_view_only_data` 调用
- ❌ 删 dataclass 字段标记为 view-only 的代码注释

**判据**：journal 不再有"对前端暴露 vs 不暴露"的概念。这是 SSE / LobeHub 的事。

### 4.2 sse_frames：SSE 不再脱敏

**文件**：`lca/layer0_infra/observability/journal/sse_frames.py`

- ❌ 删 `_LIVE_REDACT_KEYS` 常量
- ❌ 删 `stamped_to_sse_frame` 的 `redact` 参数及对应分支
- ❌ 删 `iter_live_sse` 的 `redact` 参数及对应传播
- ❌ 删 `live_tail.py` 的 `redact` 配置项

**判据**：journal fact 就是 SSE fact。"对浏览器隐藏某些事实"不是 journal 概念，是 renderer 概念（renderer 可以不读某个 ref，但 SSE 仍把 ref 发出去）。

### 4.3 tool 事件 dataclass：事实字段收敛到 3 项 + 2 个 ref

**文件**：`lca/contracts/models/observability/journal.py`

```python
@dataclass(frozen=True)
class ToolCallStreaming(JournalEvent):
    tool_name: str
    tool_call_id: str
    arguments_ref: EvidenceRef | None = None   # 流式累积引用(完整 JSON 已落到 EvidenceStore)

@dataclass(frozen=True)
class ToolStarted(JournalEvent):
    tool_name: str
    invocation_id: str
    arguments_ref: EvidenceRef                 # 必填,除非走 inline 路径(下文 §5.3)
    idempotency_key: str = ""

@dataclass(frozen=True)
class ToolInvoked(JournalEvent):
    tool_name: str
    invocation_id: str
    ok: bool
    latency_ms: int
    attempt: int
    error: str = ""
    files: tuple[dict[str, Any], ...] = ()
    idempotency_key: str = ""
    arguments_ref: EvidenceRef | None          # 与 ToolStarted 同 ref,便于 join
    output_ref: EvidenceRef | None             # ok 时指向结果,失败时为空
    output_truncated: bool = False             # 仅这一个保留为 view-only
```

**删掉的字段**（每个都是一类垃圾）：

| 字段 | 类型 | 为什么删 |
|---|---|---|
| `arguments_preview` | view-only str | 是参数原文的截图,事实归证据平面 |
| `result_preview` | view-only str | 同上 |
| `output_text` | view-only str | 同上 |
| `plugin_state` | view-only dict | 自由 dict 逃逸口 |
| `code` / `language` / `command` / `skill_id` / `skill_inputs` / `description` / `execution_env` | 6 个 typed 字段 | 白名单 union,类型上做不到 |
| `state_ref` | EvidenceRef | 改名 `arguments_ref` 语义更准 |

### 4.4 tool_journal_emit：单一职责

**文件**：`lca/layer1_cognitive/body/tool_journal_emit.py`

- ❌ 删 `_typed_started_state()`（6-key 白名单提取函数）
- ❌ 删 `prepare_state_evidence` 内的 `should_inline` 分支（统一走 evidence 路径，见 §5.3）
- ✅ `emit_tool_started` 只做 3 件事：
  1. `arguments = dict(args)` → `EvidenceStore.prepare(...)` → 拿 `ref`
  2. emit `ToolStarted(tool_name, invocation_id, arguments_ref=ref, ...)`
  3. 同 ref 暴露给后续 ToolInvoked
- ✅ `emit_tool_invoked` 只做 3 件事：
  1. `output = dict(obs.payload)` → `EvidenceStore.prepare(...)` → 拿 `ref`
  2. emit `ToolInvoked(..., output_ref=ref, output_truncated=...)`
  3. 失败时 `output_ref = None`，`error` 字段承载错误字符串

**判据**：tool 事件的事实就两样——"用什么调的"和"调出来啥"。一切渲染细节不属于这里。

### 4.5 整文件删除

- ❌ 删 `lca/layer1_cognitive/body/tool_ui_state.py`（整文件）
- ❌ 删 `lca/layer1_cognitive/body/tool_ui_builders.py`（整文件）

包含的所有机制（每个都是把渲染职责塞进 body 层）：

- `_STARTED_BUILDERS` / `_INVOKED_BUILDERS` 两个大字典
- `_started_execute_code` / `_started_run_command_sandbox` / `_started_run_command_machine` / `_started_activate_skill` / `_started_web_search` / `_started_default`
- `_invoked_activate_skill` / `_invoked_default` / `_invoked_from_payload_state`
- `_WIRE_OVERLAY_KEYS` / `_WIRE_NOISE_KEYS`
- `_ARGS_PREVIEW_BUDGET` / `_STRING_FIELD_BUDGET`
- `register_started_builder` / `register_invoked_builder` / `build_started_plugin_state` / `build_invoked_plugin_state`
- `compact_args_preview` / `wire_arguments_json`

**判据**：这个模块存在的全部理由是"把参数塑造成 LobeHub 想要的形状"。LobeHub 形状由 LobeHub 自己定义。body 层无权也无能知道——这是反向依赖，违反 AGENTS.md §3 "下层不得反向 import" 精神。

### 4.6 fact_stream_projector：CLI 调试视图不再读 preview

**文件**：`lca/layer0_infra/observability/journal/fact_stream_projector.py`

- ❌ 删 `_render_tool_started` / `_render_tool_invoked` / `_render_tool_streaming` 中所有 `event.arguments_preview` / `event.result_preview` / `event.plugin_state` 读取
- ✅ 渲染逻辑只看 `tool_name + invocation_id + ok/error/latency_ms`

**判据**：projector 是 CLI 调试视图。事实够了。看完整参数是 UX 关心，不是 debug 关心；要就给 ref 让 ops 工具单独查。

## 5. 新的最小模型

### 5.1 三平面定型

```
事实账本:    ToolStarted(tool_name, invocation_id, arguments_ref, idempotency_key)
            ToolInvoked(tool_name, invocation_id, ok, error, latency_ms, attempt,
                        files, arguments_ref, output_ref, idempotency_key,
                        output_truncated=False)
            ToolCallStreaming(tool_name, tool_call_id, arguments_ref)
            ToolDenied(tool_name, reason)

证据平面:    EvidenceStore 现有契约 (ADR-0065 §四 保留)
            每条 tool 事件携带 0~2 个 EvidenceRef
            ref 内容: arguments (dict[str, Any]) / output (dict[str, Any])

渲染平面:    LobeHub renderer registry (deploy/lobehub/patches/runtime/renderers/)
            registry: Record<toolName, ToolRenderer>
            默认: JsonRenderer 兜底任何未注册的 tool
            工具插件自带: TerminalRenderer / CodeRenderer / TreeRenderer / FileRenderer
```

### 5.2 Tool Plugin Manifest 自描述参数

每个 Tool Provider 插件在 manifest 声明参数 schema（与现有 `effects / test_suite` 同级）：

```yaml
# lca/plugins/providers/tools/local_listFiles/manifest.yaml
id: lca-tool-local-listFiles
provides: tools.local_listFiles
parameters:
  directoryPath:
    type: string
    required: true
    ui_hint: path
  recursive:
    type: boolean
    required: false
    default: false
```

`ui_hint` 是 renderer 的事（terminal / code / tree / path / number / boolean），不进 journal。

### 5.3 inline 还是走 Evidence：按 access policy 决策

继承 ADR-0065 §四 的 `EvidencePolicy`：

- `public + small + < 2KB`：inline（`arguments_ref = None`，直接放 `arguments: dict` 字段在 ToolStarted 上 — **新增的事实字段**，与 `arguments_ref` 二选一）
- 其他：强制 `arguments_ref`，inline 不允许

### 5.4 ToolStarted 新增 `arguments: Mapping[str, object]` 字段（inline 路径）

```python
@dataclass(frozen=True)
class ToolStarted(JournalEvent):
    tool_name: str
    invocation_id: str
    arguments: Mapping[str, object] = field(default_factory=dict)  # inline 路径,与 arguments_ref 二选一
    arguments_ref: EvidenceRef | None = None                          # 非 inline 路径
    idempotency_key: str = ""
```

`arguments` 与 `arguments_ref` 互斥（一个非空时另一个为空），由 `EvidencePolicy.should_inline()` 决策。

**这是全文唯一新增的事实字段**，且自带 ADR-0065 的 typed mapping 约束（键值都是 `object`，由 Tool Plugin manifest 在 schema 层约束；journal 不另立白名单）。

## 6. 插件化路径（AGENTS.md §3 一致性）

```
Tool Protocol
   ↑
Tool Provider Plugin (lca/plugins/providers/tools/<name>/)
   ├─ 参数 schema（manifest.yaml）
   ├─ 执行实现（executor.py）
   └─ idempotency_key 声明
       ↑
EvidencePolicy Plugin（已有 ADR-0065 §四）
   ├─ decide(evidence_ref, policy) → inline | ref
   └─ 策略可由 profile 替换
       ↑
Renderer Registry（前端 deploy/lobehub/patches/runtime/renderers/index.ts）
   ├─ registry[tool_name] → Renderer
   ├─ Renderer.render(arguments: object) → JSX
   └─ 新工具只需在 registry 加一条
```

每层只负责一件事：

| 层 | 唯一职责 |
|---|---|
| Tool Plugin | 描述"我能做什么、参数是什么" |
| Journal | 记录"什么时候被调用、结果如何、参数 ref 在哪" |
| Evidence | 存"参数和结果的真实数据" |
| Renderer | 决定"怎么把数据画成 UI" |

没有任何一层跨到另一层的职责。

## 7. 与既有 ADR 的关系

| 既有 ADR | 关系 | 处理 |
|---|---|---|
| **ADR-0037 Journal-as-Truth** | 强化 | journal 回归纯事实账本 |
| **ADR-0055 Run Fact Store** | 强化 | tool 事实进入事实流 |
| **ADR-0061 Plugin Manifest** | 强化 | Tool Plugin Manifest 新增 parameters 字段 |
| **ADR-0063 Run Trace SSOT** | 不动 | |
| **ADR-0065 Recoverable Evidence Ledger** | **§四 superseded** | 删 "typed UI state"段；保留 EvidenceStore / 三平面 / 治理约束 / 替代方案表 |
| **ADR-0066~0069 / 0074 / 0084 / 0085** | 强化 | 插件一切；Renderer registry 是渲染职责的 plugin 化 |
| **ADR-0096 Journal Protocol Layer** | 兼容 | envelope schema_version + consumer contract 不变；本 ADR 仅删 data 中字段 |
| **ADR-0100 Chat Command = Agent Run** | 兼容 | UI 事件名不受影响 |

### ADR-0065 §四"故意丢弃"段更新

| 否决项 | 否决依据（更新后） |
|---|---|
| `result_preview` / `*_preview` / `plugin_state` 字典逃逸口 | §4.3：本 ADR 一次性从 journal dataclass 删除 |
| Lobehub `lcaJournal.ts` 的 `JSON.parse(result_preview)` | §4.2：本 ADR 删除 SSE redact，渲染改走 renderer registry |
| `typed UI state` 6-key 白名单 | §4.3：本 ADR 删 `code / command / language / skill_id / description / execution_env` |

## 8. 实施序列（4 PR · Phase 1 优先）

按风险递增排序，每步独立可合：

| PR | 标题 | 依赖 | 改动范围 | 验证命令 |
|---|---|---|---|---|
| **PR-1** | 删 `_LIVE_REDACT_KEYS` 与 SSE redact | 无 | sse_frames.py / live_tail.py / iter_live_sse 调用方 | `uv run pytest tests/test_sse_redact_retired.py -q` |
| **PR-2** | ToolStarted/ToolInvoked 新增 `arguments` / `arguments_ref` / `output_ref` 字段；删 typed 6-key + preview + plugin_state；emit 走新路径 | PR-1 | journal.py / tool_journal_emit.py / fact_stream_projector.py / sse_frames.py（仍走 envelope v2） | `uv run pytest tests/test_tool_event_facts.py -q` |
| **PR-3** | 删 `tool_ui_state.py` + `tool_ui_builders.py` 整文件 | PR-2 | 删除 + 修所有 import | `uv run vulture lca --min-confidence 80` + `uv run pytest -q` |
| **PR-4** | Tool Plugin Manifest 加 `parameters` 字段；LobeHub renderer registry **deferred to YAGNI trigger**（见 §8 phase 2） | PR-3 | plugins/providers/tools/*/manifest.yaml + `lca/contracts/models/core/tool.py` 增加 `ParameterSpec`/`ToolManifest.parameters` | `uv run pytest tests/test_tool_plugin_manifest.py -q` |

### 8.1 阶段化执行（避免一次性大爆炸）

**Phase 1 (MVA, 4 PR, 1 周)**：PR-1 + PR-2 + PR-3 + PR-4

完成后状态：
- 117 个 ToolCallStreaming 事件每个都有 `arguments_ref`（流式累积由 `push_tool_call_stream` 改为累积到本地后 prepare evidence）
- 7 个 ToolStarted 每个都有 `arguments_ref`（listFiles 的 `{"directoryPath": "..."}` 进 evidence）
- 7 个 ToolInvoked 每个都有 `arguments_ref` + `output_ref`（结果进 evidence）
- journal.jsonl 中再也找不到 `arguments_preview` / `plugin_state` / `code` / `command` / `language` / `skill_id` / `description` / `execution_env` 字段
- LobeHub renderer registry 上线，新工具只需在 registry 加一条
- 前端零改动（`lcaJournal.ts:buildToolState` 第 1 步 state_ref-first 已经在等 `arguments_ref`，第 2 步 typed field fallback 自然降级为空）

**Phase 2 (按需启动)**：仅在出现以下任一触发条件时启动：
- (a) 第 2 个 tool schema 注册场景出现，证明 `parameters` 字段需要更复杂校验
- (b) inline/ref 决策策略出现第二个独立需求
- (c) 出现需要在 journal 序列层面 join arguments_ref + output_ref 的查询场景

## 9. 验收规约

### V-Journal

- **V1**：ToolStarted/ToolInvoked/ToolCallStreaming dataclass 不再有 `code / language / command / skill_id / skill_inputs / description / execution_env / arguments_preview / result_preview / output_text / plugin_state / state_ref` 字段
  - 命令：`uv run pytest tests/test_tool_event_facts.py::test_no_typed_or_preview_fields -q`
- **V2**：ToolStarted.data 中 `arguments` 与 `arguments_ref` 二选一（非空互斥）
  - 命令：`uv run pytest tests/test_tool_event_facts.py::test_arguments_xor_ref -q`
- **V3**：journal_io 不再有 `_strip_view_only_data` 调用
  - 命令：`uv run grep -r "_strip_view_only_data\|_is_view_only_field" lca/layer0_infra/observability/journal/` → 空
- **V4**：所有 tool 事件落盘后 `arguments` 或 `arguments_ref` 至少一个非空
  - 命令：`uv run pytest tests/test_tool_event_facts.py::test_arguments_always_set -q`

### V-SSE

- **V5**：`_LIVE_REDACT_KEYS` 不存在
  - 命令：`uv run grep -r "_LIVE_REDACT_KEYS" lca/` → 空
- **V6**：`stamped_to_sse_frame` 不再有 `redact` 参数
  - 命令：`uv run grep -n "def stamped_to_sse_frame" lca/layer0_infra/observability/journal/sse_frames.py` → 单一签名
- **V7**：SSE 帧中的 tool 事件 `data` 包含 `arguments_ref` 或 `arguments`
  - 命令：`uv run pytest tests/test_sse_redact_retired.py::test_tool_event_includes_arguments -q`

### V-Codebase

- **V8**：`tool_ui_state.py` 与 `tool_ui_builders.py` 文件不存在
  - 命令：`test ! -f lca/layer1_cognitive/body/tool_ui_state.py && test ! -f lca/layer1_cognitive/body/tool_ui_builders.py`
- **V9**：vulture 报告 tool 相关 dead code 为 0
  - 命令：`uv run vulture lca --min-confidence 80`
- **V10**：`lcaJournal.ts` 改动 ≤ 1 处（仅 `state_ref` 字段名兼容兼容期可保留为 `arguments_ref` 别名）
  - 命令：`git diff deploy/lobehub/patches/runtime/lcaJournal.ts | wc -l` ≤ 10

### V-Plugin

- **V11**：每个 Tool Provider 插件 manifest 含 `parameters` 字段
  - 命令：`uv run pytest tests/test_tool_plugin_manifest.py::test_all_tools_have_parameters -q`
- **V12**：~~LobeHub renderer registry 含默认 JsonRenderer 兜底~~ — **Deferred**: PR-4 originally shipped a renderer registry patch, but the commit landed with 0 consumers writing `renderArgs()`. Per YAGNI (`大道至简` + 第一性原理), the entire `deploy/lobehub/patches/runtime/renderers/` tree was removed in `a72899a3`. Re-introducing requires (a) a concrete consumer needing per-tool rendering, (b) an ADR noting what that consumer is, then (c) the patch system. Until then V12 is non-blocking.
  - 命令：`pnpm run test:lobehub-renderer::test_json_fallback` — **removed**

## §5.3 / §5.4 follow-up: `should_inline` 已启用

`EvidencePolicy.should_inline()` 在 `tool_journal_emit.prepare_state_evidence` 中生效(commit `10e4671f`)。小 + public payload(默认 < 64 KiB)直接 inline,不走 evidence round-trip。V2 / V4 XOR 语义不变,新增 `test_inline_path_activated_by_should_inline_true` 验证 prepare 不被调用。`ToolStarted.arguments` 字段不再永远是 `{}`。无前端改动。

### V-Doc

- **V13**：ADR-0065 §四中关于 typed UI state 的 6-key 白名单段标记为 Superseded by ADR-0101
- **V14**：新增 `docs/specs/tool-renderer-registry.md` 描述 renderer registry 契约

## 10. 风险与回滚

| 风险 | 概率 | 影响 | 回滚 |
|---|---|---|---|
| 现有 replay 工具依赖 `arguments_preview` 字段 | 中 | 中 | replay 工具改读 `arguments` 或 fetch `arguments_ref`（不破坏 ledger 完整性） |
| Tool Plugin manifest `parameters` 校验失败导致 plugin 无法 boot | 低 | 中 | boot 期 fail-fast 是对的；profile 修复即可 |
| renderer registry 漏注册新工具导致 UI 异常 | 低 | 低 | 默认 JsonRenderer 兜底；事件正常，渲染 fallback |
| ADR-0065 §四 引用本 ADR 时链接断裂 | 极低 | 极低 | ADR 互引，git grep 一次补齐 |

## 11. 元数据

- 作者：LCA 架构
- 日期：2026-08-29
- 状态：**Proposed**
- Supersedes：ADR-0065 §四"typed UI state"段（其余保留）
- 关联 ADR：0037 / 0055 / 0061 / 0063 / 0065 / 0066~0069 / 0074 / 0084 / 0085 / 0096 / 0100
- 关联宪法条款：C3（Journal 事实可追溯）/ C4（Reducer 边界）/ C6（最小化原则）
- 关联 spec：新建 `docs/specs/tool-renderer-registry.md`
- 关联 ADR 程序：本 ADR 落地后，任何 Tool 事件 dataclass 新增字段必须新开 ADR 并修订 §4.3 的"删掉的字段"表
- 关联 plan：`docs/plans/adr-0101-implementation-tracker.md`（待 PR-1 启动时创建）

## 12. 给后续维护者的一句话

**journal 是事实账本，不是 LobeHub 字段映射器。**

任何想给 `ToolStarted` 加 `xxx_field`（除 `arguments`/`arguments_ref`/`output_ref` 之外）的 PR，回答是：

1. 这是 renderer 的事 → 去 renderer registry 加
2. 这是 evidence 的事 → 加 EvidenceRef 字段并走 EvidenceStore
3. 这是事实账本该有的事 → 先开 ADR 解释为什么 facts 里需要它

`plugin_state` / `*_preview` / typed 6-key 白名单 三种模式已死；新增不允许，存量已删。