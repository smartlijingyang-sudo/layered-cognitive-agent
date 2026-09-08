# Agent Note: End-to-End Field Contract — effect_kind + digest 统一

Status: implemented

## Problem

两套相邻的合约漂移在仓库内共存:

1. **`effect_kind` 缺位** (`report_stateful_once_tools.md`)：`Tool.is_idempotent: bool` 是二元近似,`activate_skill` 声称 `is_idempotent=True` 但每次都 re-emit `SkillActivated`,prompt assembler 拿不到分类字段判断是否去重。`SkillActivated` payload 无 effect_kind,Session 流过滤只能靠 `event.type=="skill.activated.v1"` 这一字符串。

2. **digest 散乱** (`report_digest_inconsistency.md`)：40+ 处 sha256 计算散点,5 种长度(12/16/24/32/64 hex)、5 种前缀形态(`"sha256:"` / `"evt_"` / `"tool:"` / `<namespace>:` / 无前缀)、3 种算法(`hashlib.sha256` / canonical JSON / hash-bytes)。`step.tool_call.record` 同一 invocation_id 在 0.3 ms 内出现 3 种 digest(`"tool:activate_skill"` vs `"skill_id='anthropics-skills-pdf'"` vs `sha256:<hex>`),无法做幂等去重。

## Decision

按 [ADR-0203](../../adr/0203-end-to-end-field-contract.md) 一次闭环两条平行漂移:

### Effect kind 闭集

- `Tool` Protocol(`lca/contracts/protocols/runtime/infra/infra.py`)新增 `effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]]`,默认 `ephemeral`
- `ToolApi`(`lca/contracts/models/core/execution/tool.py`)新增 `effect_kind: Literal[...] = "ephemeral"`
- `SkillActivated` payload(`lca/contracts/harness/memory/events.py`)新增 `effect_kind: Literal["stateful_once"] = "stateful_once"`,不开新事件词表(沿用现有 `skill.activated.v1`)
- `is_idempotent` 保留,与 `effect_kind` 正交

### Digest 助手 SSOT

- `lca/contracts/observability/canonical_digest.py`(由 `fc3bd63f` 在 PR-C 中已落地)提供:
  - `canonical_digest(payload, *, length: int = 16, prefix: str = "sha256:", ensure_ascii: bool = False) -> str`
  - `sha256_payload_digest(payload) -> str`(历史兼容别名,64-hex 全长度)
  - `DIGEST_PREFIX` / `DEFAULT_DIGEST_PREFIX` 常量
- 17 个迁移站点按 task 枚举顺序逐一替换 inline digest 为 `canonical_digest(...)`
- `length` + `prefix` 保持各站点原约定(不强制统一长度,避免破坏 on-the-wire 字段长度契约)
- 保留 streaming-HMAC / dynamic-algorithm / file-bytes 站点(算法形态不同,不在 canonical-JSON-of-payload 形态内)

### ToolCallRecord 字段删除

- 删除 `ToolCallRecord.args_digest` / `ToolCallRecord.args_payload_path`(沿 ADR-0185 §2.5 P5 deprecation marker)
- 9 个 reader 同 PR 迁移:生产代码 4 个文件 + 测试 9 个文件
- 业务路径 `record_step_tool_call` / `record_step_tool_result` 不动(PR-1 已锁定,`tests/contracts/test_record_step_tool_call_wrapper.py:65` 已断言 `"args_digest" not in payload`)

## 迁移站点(实现状态)

### Digest 站点(17 个 inline → `canonical_digest`)

| # | 文件 | 长度 | 前缀 |
|---|---|---|---|
| 1 | `lca/contracts/runtime/plan_proposal.py` | 64 | `""` |
| 2 | `lca/harness/plan.py` (plan digest) | 32 | `"sha256:"` (默认) |
| 3 | `lca/harness/plan.py` (run digest) | 16 | `"sha256:"` (默认) |
| 4 | `lca/cognition/brain/prompt/surface.py` | 16 | `"sha256:"` (默认) |
| 5 | `lca/cognition/brain/pipeline/context_manifest.py` | 16 | `"sha256:"` (默认) |
| 6 | `lca/cognition/memory/semantic/compaction.py` | 16 | `"sha256:"` (默认) |
| 7 | `lca/harness/diagnostics/normalizer/normalizer.py` | 16 | `"sha256:"` (默认) |
| 8 | `lca/plugins/learning/review_service.py` | 16 | `"sha256:"` (默认) |
| 9 | `lca/plugins/skill/auto_acquire.py` | 16 | `"sha256:"` (默认) |
| 10 | `lca/plugins/transport/webserver/handlers/runs/session/builder/builder.py` | 16 | `"sha256:"` (默认) |
| 11 | `lca/plugins/transport/webserver/handlers/runs/session/index/index.py` | 24 | `"sha256:"` (默认) |
| 12 | `lca/infrastructure/observability/journal/engine/journal_io.py` | 24 | `"evt_"` |
| 13 | `lca/contracts/harness/journal/artifact.py` | 16 | `"sha256:"` (默认) |
| 14 | `lca/contracts/protocols/perceive/capability_plan.py` | 16 | `"sha256:"` (默认) |
| 15 | `lca/contracts/protocols/state/scope_plan.py` | 16 | `"sha256:"` (默认) |
| 16 | `lca/infrastructure/computer/machine/exec.py` | 12 | `"sha256:"` (默认) |
| 17 | `lca/harness/declarative/compile/instrument/wrap.py` | 16 | `"sha256:"` (默认) |

**未迁移(算法形态不符):** `_home_layout.py`(file-bytes streaming)、`evidence/store.py`(dynamic algorithm via `hashlib.new(self.algorithm)`)、`device_hub/auth/auth.py`(HMAC)、`meta_event_emit.tool_registry_digest`(已使用 `sha256`,但调用方式与助手签名不同,且与本 ADR 不在同迁移批次)。

### ToolCallRecord 字段迁移

| 文件 | 操作 |
|---|---|
| `lca/contracts/observability/cursor/loop_cursor_payloads.py` | 删 `args_digest` / `args_payload_path` |
| `lca/cognition/body/executor/cursor_record.py` | 删 kwarg 与字段构造 |
| `lca/infrastructure/observability/loop_cursor/std/std.py` | 删 payload copy 行 |
| `lca/infrastructure/observability/loop_cursor/coordinator/adapter.py` | 删字段赋值与注释引用 |
| `lca/infrastructure/observability/spine/derivers/step/tree_accumulator.py` | 删注释引用 |
| `tests/integration/test_loop_cursor_wiring.py` | 删 kwarg |
| `tests/observability/test_observation_ssot_regression.py` | 删 payload 字段 |
| `tests/observability/spine/derivers/test_step_tree_accumulator.py` | 删 payload 字段(2 处) |
| `tests/observability/loop_cursor/test_invariants.py` | 删 kwarg(3 处) |
| `tests/observability/loop_cursor/test_halt_resume.py` | 删 kwarg |
| `tests/cognition/body/test_cursor_record.py` | 删 kwarg(3 处) |
| `tests/observability/loop_cursor/test_coordinator_adapter.py` | 删断言与 `sha256_digest` 期望 |
| `tests/observability/loop_cursor/test_payloads.py` | 删 kwarg |
| `tests/observability/loop_cursor/test_std_loop_cursor.py` | 删 kwarg |

## Alternatives considered

### Why not a single fixed digest length?

强制 16-hex / 64-hex 会破坏 on-wire 字段长度契约(`session_evt_*` / `tool_call_id` 现有约定)。助手暴露 `length` + `prefix` 参数,站点按调用上下文传值,统一的是 *算法 + canonical 归一*,而不是 *长度*。

### Why not put `effect_kind` on `Tool` Protocol only?

`ToolApi`(manifest 形态)是工具声明,也是 tool registry 唯一注册形态(per `lca/cognition/body/tools/tool_registry.py`)。缺 `ToolApi.effect_kind` 会导致 manifest 解析层与 runtime Protocol 层分类不一致——receiver 走 manifest 路径会再次拿不到分类。

### Why not a new `FactActivated` event class for stateful-once activation?

`AGENTS.md §0` 显式禁止"新增平行事件词表"。`SkillActivated` 已经是 session-catalog 上的 activation receipt,扩展 `effect_kind` 字段即可分类,无需开新事件。

### Why delete `args_payload_path` along with `args_digest`?

两者本就是 sidecar 配对字段;`arguments` / `arguments_summary` 已承担"payload 内容"与"人话摘要"职责,sidecar 引用在 PR-1(commit `ccc78fbb`)锁定的业务路径上无引用。

## Consequences

- `canonical_digest` 成为 canonical-JSON-of-payload → sha256 hex 的唯一 SSOT;后续若发现新增站点,应直接 import 助手而非 inline。
- `SkillActivated` 携带 `effect_kind="stateful_once"`,prompt assembler 可基于该字段做去重折叠(后续 PR-E 收口 `ActivatedSkillsSection`)。
- `Tool` 实现层需在 PR 范围外补 `effect_kind` 默认值声明(本次 PR 不强制所有 Tool 改,但 Protocol 上有 ClassVar 默认 `"ephemeral"`)。
- `ToolCallRecord` 字段删除后,旧 cursor-internal caller(`CoordinatorAdapter`)的 `record_tool_call` 路径不再携带 `args_digest`;新协议字段 `arguments` / `arguments_summary` 是 SSOT。
- `args_digest` 旧字段的 wire 形态(出现在历史 spine `step.tool_call.record` 事件 payload 中)仍存在历史 trace,旧 trace 不重写(AGENTS §1 "可删的兼容"原则)。

## Testing

- `tests/contracts/test_canonical_digest.py` — 5 个单元测试:
  1. `test_canonical_digest_basic` — 同输入同输出,默认参数
  2. `test_canonical_digest_length_parameter` — 不同长度返回不同前缀 + 截断长度
  3. `test_canonical_digest_prefix_parameter` — 空前缀 / 自定义前缀
  4. `test_canonical_digest_canonicalization` — dict 顺序无关(用 `sort_keys=True`)
  5. `test_canonical_digest_type_errors` — 不可序列化类型抛 `TypeError`
- `tests/contracts/test_record_step_tool_call_wrapper.py` — 既有 PR-1 锁定测试,断言 `"args_digest" not in payload`(行 65,本 ADR 增强保持)
- `pytest tests/contracts/test_canonical_digest.py tests/contracts/test_record_step_tool_call_wrapper.py -q` 全通过

## 关联

- [ADR-0203 端到端字段契约](../../adr/0203-end-to-end-field-contract.md) — 本 note 的根 ADR
- [ADR-0185 §2.5 P5 args_digest deprecation 源](../../adr/0185-model-visible-event-bus-alignment.md)
- [report_stateful_once_tools.md](../../../report_stateful_once_tools.md) — effect_kind 调研
- [report_digest_inconsistency.md](../../../report_digest_inconsistency.md) — digest 调研
