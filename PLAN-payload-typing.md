# PLAN: L2/L3 类型化 payload（note 4 — payload schema typing）

Status: plan（未动手）
承接: [docs/notes/proposed/contract/2026-09-03-4-contract-payload-schema-typing.md](docs/notes/proposed/contract/2026-09-03-4-contract-payload-schema-typing.md) / [ADR-0178](docs/adr/0178-observation-control-state-convergence.md) / 根 note [2026-09-03-observation-convergence-root.md](docs/notes/proposed/seam/2026-09-03-observation-convergence-root.md)

探索日期 2026-09-04。本计划基于当前 worktree 代码事实，note 文本与现状有偏差（§5 路径修正表）。

## 0. 总闸 4 问

1. **问题是什么？** —— spine 事件的 caller payload 无类型约束：101 个已登记 category 中 98 个走 `SpineEventPayload` 壳 + `payload: dict[str, Any]`，yaml `fields:` 声明无人 enforce，字段缺失/漂移只在消费端（deriver 重投影、fold 重建）才暴露。
2. **最干净的机制边界在哪？** —— 真值 = 每 category 一个 typed payload class（pydantic，构造即校验）；`lca_kernel/events/config/**/*.yaml` 是登记与鉴权 SSOT；`EventBus._validate_schema` 是运行时校验唯一 seam；`build_record` 是落盘序列化唯一 seam。
3. **现有 seam 能否表达？** —— 能。ADR-0185 model_visible 已示范完整形态（typed class + yaml `payload_class` 直指 + fields 一致性测试）。`EventBus._validate_schema` 注释明写 "详细 spec.fields 校验推迟到 PR-3"；`build_record` 对非壳 payload 的序列化是缺口。无需新平行机制。
4. **删除条件？** —— 见 §4 PR-0 COMPAT 与 §6 delete-when 汇总。

## 1. 现状盘点（代码事实，非 note 转述）

### 1.1 两套注册表并存

| 注册表 | 位置 | 管什么 |
|---|---|---|
| EventBus 鉴权矩阵（spine EP SSOT） | `lca_kernel/events/registry.py` + `lca_kernel/events/config/observability/spine.yaml`（ADR-0180/0181/0183） | 101 个 category 的 `payload_class`（装载期必填、解析为 class）+ `fields: dict[str,str]`（**只装载不 enforce**）+ publishers/subscribers 鉴权 |
| Journal 描述符注册表 | `lca/contracts/observability/event_descriptor_registry.py`（Protocol）+ `lca/infrastructure/observability/events/event_descriptor_registry.py`（ADR-0063/0065） | Journal 事件 `EventDescriptor`，`payload_class: type[JournalEvent] \| None` 已存在（可选） |

note 4 正文假设的 "在 `event_descriptor_registry.py` 加 `payload_class`" 对 spine EP 不成立——spine 侧 SSOT 已是 `lca_kernel/events/registry.py` + yaml，且 `payload_class` 已是必填。**真正的缺口在 caller payload 的 dict 与 yaml `fields:` 无人校验。**

### 1.2 已类型化（L2 完成）

| EP / category | payload class | 形态 |
|---|---|---|
| `spine.llm.request.header` | `SpineLlmRequestHeaderPayload` | pydantic `extra="forbid", frozen=True`；ADR-0185 §3.3 |
| `spine.llm.request.header.assistant` | `SpineLlmRequestHeaderAssistantPayload` | 同上 |
| `spine.team.delegation.cache_hit` | `TeamDelegationCacheHit`（`lca/contracts/event.py` 试点） | pydantic |
| 机制自观察 `event.bus.dispatch.*` | `MechanismDispatchEventPayload`（`lca_kernel/events/payloads.py`） | pydantic + 闭集 validator |
| cursor `record_*`（走旧 spine 路径，未进 EventBus） | `ThinkingRecord` / `ToolCallRecord` / `ToolResultRecord` / `RequestHeader` / `ToolSchema`（`lca/contracts/observability/loop_cursor_payloads.py`） | frozen dataclass |
| `exception.caught` 的归一化载体 | `ExceptionRecord`（`lca/contracts/observability/exception_capture.py`，11 字段含 `traceback_text` / `call_frames` / `err_kind`） | frozen dataclass + `asdict()`（含 legacy alias `exc_type` / `reason`） |

### 1.3 仍裸 dict（98 category）

- 全部走壳：`SpineEventPayload.payload: dict[str, Any]`（`lca_kernel/events/payloads_spine.py`）。
- 15 个 publisher plugin（`lca/plugins/events/publishers/spine_reflector_*/plugin.py` + `spine_loop_cursor` + `spine_writable_matrix`）内 ≥ 79 个 `emit_*` helper 手填 `payload={...}`。
- yaml 每 category 的 `fields:` 与 caller 实际填的键**无运行时校验**；唯一校验是 `EventBus._validate_schema` 的 `isinstance(payload, spec.payload_class)`（`lca_kernel/events/bus.py`）。
- 已知漂移实例：
  - `spine.exception.caught` yaml `fields:` = `{boundary, exc_type, message, trace_id}` 4 键，而主路径（`runtime_loop.py` / `lca_kernel/lifecycle.py` → `exc_to_record` → `exception_emit.emit_exception_caught(record)`）实际落 `record.asdict()` 13 键——**yaml 声明与真实 payload 漂移**。
  - `phase.think.fold` 历史 `objective=model` 误传（`scripts/audit_ssot_field_drift.py` 背景所述）。

### 1.4 结构性缺口（本计划必须先解决）

1. **落盘序列化缺口**：`lca_kernel/events/spine_runtime.build_record()` 取 `getattr(payload, "payload", {})`——非壳 typed payload（无 `.payload` 属性）落盘会变成空 dict，**spine.jsonl 静默丢全部字段**。现无任何测试覆盖 "typed payload 过 sink 后字段完整"。任何 EP 迁 typed class 前，此缺口必须先补，否则迁移本身制造数据丢失。
2. **`fields:` 无 L3 enforce**：`_validate_schema` 的 fields 校验是显式留给 "PR-3" 的 seam（bus.py 注释）。
3. **`step.*.record` 5 个 EP**（`step.thinking.record` / `step.tool_call.record` / `step.tool_result.record` / `step.reflect.record` / `step.span.record`）在 `SPINE_EXECUTION_POINTS` 闭集内，但**未登记 `_SPINE_EP_TO_CATEGORY` 映射、无 yaml category 行**——仍走旧 `spine.append` 路径（cursor）。typed 化前需先走 ADR-0181 迁移流程登记，不能跳过。
4. **`exception.caught` 双路径**：SSOT emitter（`lca/infrastructure/observability/spine/exception_emit.py`）走旧 `resolve_active_spine().append`，不走 EventBus；`spine_reflector_runtime/plugin.py` 的 4-str 版 `emit_exception_caught(boundary, exc_type, message, trace_id)` 已无生产调用方（仅测试引用），属 note 3 遗留删除项。

### 1.5 note 4 现状认知偏差（不影响结论）

- note 说 "`exception.caught` 4 键裸 dict 缺 traceback_text"：主路径已修复（`runtime_loop.py` / `lifecycle.py` 均走 `exc_to_record`）。残留问题 = §1.4-1 漂移 + 4-str 函数未删 + EventBus 侧无该 EP 的 typed 校验。
- note 说 `EnvelopeEmitter.emit_exception_caught` 收 4 str：现状已收 `ExceptionRecord`（`lca/contracts/protocols/runtime/envelope_emitter.py`）。

## 2. EP 优先级

高风险（字段缺失=证据丢失/重投影失败，用户反馈直接命中）：

| 优先级 | EP 组 | category 数 | 风险事实 |
|---|---|---|---|
| P0-1 | `exception.caught` / `exception.finally` / `lifecycle.finally` | 3 | traceback 丢失史；yaml 字段漂移；4-str 平行入口残留 |
| P0-2 | `phase.*.fold`（13 EP，含 `perceive.phase.fold`） | 13 | step-tree deriver 真值；双 publisher（reflector.phase + loop_cursor）；objective 漂移史 |
| P0-3 | `llm.call.start/end` / `llm.stream.token/stall` | 4 | `llm.request.header(.assistant)` 已 typed，同族字段语义须一致；`stream.token` 高频 |
| P0-4 | `body.tool.execute.start/end` / `body.tool.retry` / `sandbox.enter/exit` | 5 | note 点名的 deriver 重投影依赖；与 `step.tool_call.record` 字段链同源 |
| P1 | `runtime.*`（9）/ `transport.*`+`kernel.*`+`agent*`（14） | 23 | 量大字段浅，机械迁移 |
| P2 | cognition（16）/ writable（7）/ phase_graph（4）/ team+perception+control+boot（27，cache_hit 已完成） | 54 | 低风险收尾 |

## 3. 机制设计（跨 PR 的稳定形态）

- **typed payload 唯一形态**：pydantic v2，`ConfigDict(extra="forbid", frozen=True)`，`category: Category = Category.SPINE_*` 默认值；字段与 yaml `fields:` 一一对应（`json` 型字段对应复合结构）。直接复制 `SpineLlmRequestHeaderPayload` 形态，不新建基类。
- **放置位置**：`lca_kernel/events/payloads_spine.py` 追加（壳与同源；文件超 1500 行时按 EP 组拆 `payloads_spine_<group>.py`）。不采用 note 正文的 `lca/contracts/observability/event_payload_schema.py`——spine payload SSOT 已在 kernel 元层，contracts 只放跨层契约（`ExceptionRecord` / cursor dataclass 留原地）。
- **L3 校验 = 构造期 + bus 期两段**：
  - 构造期：pydantic 构造即校验（缺字段抛 `ValidationError`）——这是主校验，零额外成本；
  - bus 期：`_validate_schema` 增加 `spec.fields` ⊆ payload 序列化键 检查（对壳类 = 检查 `payload.payload` 键集；对 typed 类 = 检查 `model_fields`）。失败抛 `PayloadSchemaError`（已存在）。
  - **不做** 每 emit 一次 `model_validate(dict)` round-trip（note 估算 0.5–1ms/次的性能风险即来自此）；`_FAST_PATH_EPS` 白名单因此不需要，`stream.token` 等高频 EP 只付构造校验成本。
- **`ExceptionRecord` 不重复定义**：`SpineExceptionCaughtPayload` 只有一个构造入口 `from_record(ExceptionRecord)`，字段 = `asdict()` 的 SSOT 键集（新键，不带 `exc_type` / `reason` legacy alias——alias 留在 asdict 给旧 reader，payload class 不登记）。满足 note "契约层单一真值，不双写"。
- **序列化单写**：`build_record` 对非壳 `EventPayload` 走 `payload.model_dump(mode="json")`（壳类保持 `dict(payload.payload)`）。这是 §1.4-1 缺口的唯一修复点。

## 4. PR 切分

每 PR 独立可回滚；契约改动同 PR 闭环（AGENTS.md §1 表）。

### PR-0 地基：序列化 seam + L3 fields 校验 + 回归锁

- `lca_kernel/events/spine_runtime.py::build_record`：非壳 payload → `model_dump(mode="json")`；壳类行为不变。
- `lca_kernel/events/bus.py::_validate_schema`：实装 `spec.fields` 校验（接上注释里预留的 "PR-3" seam）。
- yaml：修正 `spine.exception.caught` / `spine.exception.finally` `fields:` 对齐 `ExceptionRecord.asdict()` SSOT 键（漂移修复先行，避免 PR-1 校验落地即红）。
- 测试（新文件 `tests/lca_kernel/events/test_typed_payload_persistence.py`）：typed payload → `EventBus.publish` → 装载的 `SpineSink` → `SpineReader` 读回，断言字段完整；缺字段构造抛错；`fields:` 不匹配 → `PayloadSchemaError`。
- COMPAT：壳类 `SpineEventPayload.payload: dict` 保留——`# COMPAT(delete-when: 全 category payload_class ≠ SpineEventPayload 且 rg "payload: dict\[str, Any\]" lca_kernel/events = 壳类定义 1 处, tracking: ADR-0178-note-4)`。
- 验证：`uv run pytest tests/lca_kernel/events tests/observability -q` + `scripts/check_events_catalog_consistency.py`。

### PR-1 exception 组（P0-1）

- `SpineExceptionCaughtPayload.from_record(ExceptionRecord)` + `SpineExceptionFinallyPayload` + `SpineLifecycleFinallyPayload`。
- `exception_emit.emit_exception_caught` 切到构造 `SpineExceptionCaughtPayload` 后走 EventBus（`producer` = runtime reflector marker 或新 marker——同 PR 决定并在 yaml `publishers:` 登记）；旧 `resolve_active_spine().append` 路径删除（同 PR，无双写）。
- 删 `spine_reflector_runtime/plugin.py` 的 4-str `emit_exception_caught`（无生产调用方；测试同步改）——闭环 note 3 PR-2 残留，避免两个 note 各删一半。
- 测试：回归锁 "抛异常 → spine.jsonl `exception.caught` 记录含 `traceback_text` / `call_frames` / `err_kind`"。
- 依赖：PR-0。

### PR-2 phase.*.fold 组（P0-2）

- 13 个 `PhaseFold*Payload`（可共享基座：`step` / `run_id` 公共 + 组特有字段 `decision_path` / `verdict` / `lessons` / `tool_name` / `invocation_id` / `outcome` / `reason`）。
- `spine_reflector_phase/plugin.py` 13 个 `emit_*` 与 `spine_loop_cursor` 的 fold 发送点同迁移（双 publisher 共用 class，yaml `fields:` 同步）。
- 注意：`phase.*.fold` 是 `audit_ssot_field_drift.py` 守护对象，迁移后跑一次该脚本确认零漂移。
- 依赖：PR-0。

### PR-3 llm.call / llm.stream 组（P0-3）

- `SpineLlmCallStartPayload` / `SpineLlmCallEndPayload` / `SpineLlmStreamTokenPayload` / `SpineLlmStreamStallPayload`（`spine_reflector_body_llm/plugin.py`）。
- 字段语义对齐已 typed 的 `request.header` 族（`model` 命名一致性）。
- `stream.token` 高频：确认只付构造校验（§3 机制已保证），不加白名单分支。
- 依赖：PR-0。

### PR-4 body.tool 组 + 门禁（P0-4 收尾）

- `body.tool.execute.start/end` / `body.tool.retry` / `body.sandbox.enter/exit` 5 个 typed payload（`spine_reflector_body_llm/plugin.py`）。
- CI 门禁：新脚本或扩展 `scripts/check_events_catalog_consistency.py`——**每 category 的 yaml `fields:` 键集 == payload_class 字段集**（壳类豁免到 COMPAT 删除日）；`payload_class is SpineEventPayload` 的 category 清单作为渐进迁移台账打印。
- `step.*.record` 5 EP 的 typed 化**不在本 PR**：需先按 ADR-0181 流程登记 category（新 ADR 或扩展），作为 backlog 独立提案。
- 依赖：PR-0~3 合入后门禁只对已迁移组严格，未迁移组列入台账。

### Backlog（P1/P2，机械迁移，按组一 PR）

- B1 `runtime.*`（9）+ B2 `transport/kernel/agent*`（14）+ B3 cognition（16）+ B4 writable/phase_graph（11）+ B5 team/perception/control/boot（27）。
- 全部合入后：删壳类 `payload` 字段（COMPAT 删除条件 §4 PR-0），note 4 升 `implemented/`，根 note 汇总。

## 5. note 4 过时路径修正表（只记录，不改 note 正文）

| note 原文 | 现状 |
|---|---|
| `lca/contracts/observability/event_descriptor_registry.py` 加 `payload_class` | spine EP SSOT = `lca_kernel/events/registry.py` + `config/observability/spine.yaml`（`payload_class` 已必填）；journal 侧 `EventDescriptor.payload_class` 已存在 |
| 新建 `lca/contracts/observability/event_payload_schema.py` | payload 放 `lca_kernel/events/payloads_spine*.py`（§3 理由） |
| `scripts/check_observation_ssot.py` 加规则 | 该脚本不存在；现门禁 = `scripts/check_events_catalog_consistency.py` / `check_no_silent_swallow.py` / `audit_ssot_field_drift.py` |
| `tests/contracts/observability/test_event_payload_schema.py` | 目录不存在；测试放 `tests/lca_kernel/events/`（模板 = `test_model_visible_payload_typing.py`） |
| `emit_exception_caught` 4-str Protocol / 3 处平行入口 | Protocol 已收 `ExceptionRecord`；主路径已走 `exc_to_record`；残留 = reflector 4-str 函数（PR-1 删） |
| `lca/plugins/observability/spine/reflectors/runtime.py` | 已迁 `lca/plugins/events/publishers/spine_reflector_runtime/plugin.py`（ADR-0181） |

## 6. Delete-when 汇总

| compat | 条件 |
|---|---|
| `SpineEventPayload.payload: dict` 壳接收 | 全 category `payload_class` ≠ 壳，且 `rg "SpineEventPayload\(" lca/plugins = 0`（tracking: ADR-0178-note-4） |
| `ExceptionRecord.asdict()` legacy alias `exc_type` / `reason` | 全 reader 迁完新键且 `rg` 非文档命中 = 0（根 note 已定，tracking: ADR-0178-note-4） |
| `build_record` 壳类分支 | 与壳删除同条件（tracking: ADR-0178-note-4） |

## 7. 风险

- **`exception_emit` 切 EventBus 是热路径改动**（所有异常落盘）：PR-1 必须带 "无 EventBus / spine 未装配" 的降级语义保持（现状 `spine is None → None`，切后需等价透明降级，对齐 ADR-0169 L10）。
- **双 publisher 组（phase.fold / writable.*）**：两个 producer 共用一个 typed class，yaml `publishers:` 双行保留；鉴权矩阵不变。
- **yaml `fields:` 批量改**：PR-1 只改 exception 3 行；其余随各迁移 PR 同改，禁止一次性批量改 101 行（review 不可审）。
- **`Category` 枚举闭集**：本计划不新增 category（`step.*.record` 登记是独立提案），不触 C1 闭集。
