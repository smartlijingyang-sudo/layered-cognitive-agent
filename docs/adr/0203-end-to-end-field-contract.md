# ADR-0203 — 端到端字段契约：effect_kind + digest 统一

## 状态

**Proposed** (2026-09-08). Refs: report_stateful_once_tools.md, report_digest_inconsistency.md, ADR-0185 P5 (args_digest deprecation), contracts/observability/cursor/loop_cursor_payloads.py:63-73 (delete-when marker).

## 0. 决策摘要

两套相邻的合约漂移在本 ADR 一次性闭环:

1. **`effect_kind` 枚举缺失** — `Tool.is_idempotent: bool` 是二元近似,把"只读"和"stateful-once"(例如 `activate_skill` 声称 idempotent=True 但每次都 re-emit `SkillActivated`)混为一谈;Session 事件缺分类字段,prompt assembler 无法对 stateful-once 去重。
2. **digest 计算散乱** — 40+ 处 sha256 散点,5 种长度(12/16/24/32/64 hex)、5 种前缀(`"sha256:"` / `"evt_"` / `"tool:"` / `<namespace>:` / 无前缀),3 处不同算法(`hashlib.sha256` / canonical JSON / hash-bytes),Step 工具调用记录 0.3 ms 内同一 invocation_id 出现 3 种 digest。

本 ADR 引入:

- `effect_kind: Literal["ephemeral", "persistent", "stateful_once"]` 作为 `Tool` Protocol + `ToolApi` 的闭集字段;
- `SkillActivated` payload 增加 `effect_kind: Literal["stateful_once"]` 分类(扩展现有事件词表,不开平行事件);
- 单一 digest 助手 `canonical_digest(payload, *, length: int = 16, prefix: str = "sha256:") -> str`,放 `lca/contracts/observability/canonical_digest.py`;
- 删除 `ToolCallRecord.args_digest` 字段(沿用 ADR-0185 §2.5 P5 的 deprecation marker)。

**第一性原理:** 端到端字段契约是 emitter 与 receiver 的唯一共面;契约变更必须 **ADR + consumer + migration** 一并闭环(AGENTS.md §5)。`args_digest` 字段与 `effect_kind` 分类是同一谱系的两个现象:reproducer 与 consumer 对"什么叫一个 tool 调用"和"怎么算一次工具效应"必须共用一套闭集表达。

## 1. 第一性原理

### 1.1 契约单面原则

LCA 把 emitter 与 receiver 通过 frozen dataclass(`contracts/`)和解耦;任一字段语义若两边理解不同,该字段就退化为字符串散点。新增字段必须:

- 闭集(Literal / Enum)而非字符串;
- emitter 唯一(`Session.append` / 单一 emit 函数);
- receiver 接受同字段、同语义读取。

**违反该原则的后果:**

- `effect_kind` 缺位 → `activate_skill.is_idempotent=True` 误导 receiver 信任可重入 → PromptAssembler 把已激活的 skill 重复写入 `<activated_skills>` 段;(`report_stateful_once_tools.md` §2)
- digest 散点 → 同一 invocation_id 出现不同 digest → `step.tool_call.record` 事件无法做幂等去重;(`report_digest_inconsistency.md` "What the trace actually shows")

### 1.2 AGENTS §5 闭环要求

`AGENTS.md §5` 显式列出契约变更必须同 PR 闭环:

| 改了什么 | 必须同 PR 改 |
|---|---|
| Protocol / 公共签名 | 全部实现 + 测试 + 必要时 mypy |
| 枚举 / close-set / EP 名 | whitelist、catalog、emit 方、消费方、文档 |
| Schema / Journal 字段 | consumer + migration 说明 + 测试 |

本 ADR 把 Protocol(`Tool`)、Schema(`ToolApi`)、Journal 字段(`ToolCallRecord`、`SkillActivated`)三类契约一次变更,consumer 迁移 + 测试 + 文档同 PR 闭环。

## 2. 受影响的契约

### 2.1 Effect kind taxonomy

**新闭集字段:**

```python
# lca/contracts/protocols/runtime/infra/infra.py  Tool Protocol
class Tool(Protocol):
    name: ClassVar[str]
    description: ClassVar[str]
    parameters: ClassVar[dict[str, Any]]
    is_idempotent: ClassVar[bool]
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]]  # NEW
    default_timeout_s: ClassVar[int]
    ...

# lca/contracts/models/core/execution/tool.py  ToolApi
@dataclass(frozen=True)
class ToolApi:
    name: str
    description: str
    parameters: dict[str, Any]
    is_idempotent: bool = False
    effect_kind: Literal["ephemeral", "persistent", "stateful_once"] = "ephemeral"  # NEW
    default_timeout_ms: int = 30_000
```

**语义(AGENTS §2.2 分类对齐):**

| 取值 | 语义 | 对应分类 |
|---|---|---|
| `"ephemeral"` | 调用本身无持久副作用(read-only / 进程内) | 状态不变 |
| `"persistent"` | 调用每次都留下不可恢复的副作用(写文件 / 执行命令) | 投影不可逆 |
| `"stateful_once"` | 同一 run + 同一 target 只生效一次,后续调用应短路或返回原 receipt | 回执(stateful-once) |

**`is_idempotent` 不退场:** 它继续代表"调用可重试到一致状态"的传输层语义;`effect_kind` 是观察/汇编层的"语义分类"。两者正交。

### 2.2 Digest 统一

**单一助手(`lca/contracts/observability/canonical_digest.py`):**

```python
def canonical_digest(
    payload: Any,
    *,
    length: int = 16,
    prefix: str = "sha256:",
    ensure_ascii: bool = False,
) -> str:
    """Canonical sha256 digest with caller-controlled length and prefix.

    Normalization: json.dumps(payload, sort_keys=True, ensure_ascii=…, default=str).
    Output: ``f"{prefix}{sha256(...).hexdigest()[:length]}"``.

    Length + prefix are parameters (not hard-coded) because callers use
    different on-the-wire shapes (16-hex trace id, 24-hex session evt id,
    full 64-hex for file content). The helper is the single SSOT for the
    canonical JSON normalization + sha256 hex form; sites that need raw
    bytes or streaming hash keep their local helper (file content / HMAC).
    """
```

**为什么不强制统一长度:** 12 / 16 / 24 / 32 / 64 各有调用上下文(trace id / step id / session evt id / plan digest / file content);强制统一会破坏现有 on-the-wire 字段长度契约(`tool_call_id`、`session_evt_*`)。助手暴露 `length` + `prefix` 是 parameter,不替代调用方约定。

### 2.3 ToolCallRecord 收口

**删除字段(`lca/contracts/observability/cursor/loop_cursor_payloads.py:77-87`):**

```python
@dataclass(frozen=True)
class ToolCallRecord:
    tool_name: str
    call_seq: int
    # 删除 args_digest: str = ""   (沿 ADR-0185 §2.5 P5 deprecation marker)
    # 删除 args_payload_path: str | None = None
    arguments: dict[str, Any] | None = None
    arguments_summary: str = ""
    invocation_id: str = ""
```

**为什么同 PR 删:** PR-1 已把业务路径迁到 `lca.loop.commit.tool_journal.record_step_tool_call`(走 `FactGateway.publish_ep` → `Session.append`,单轨;`report_record_step_tool_call_wrapper.py` 已在 PR-1 锁定);`args_digest` 字段当前只剩:

- `lca/cognition/body/executor/cursor_record.py:105,137` — legacy adapter,本身在 delete-when 注释里(`delete-when: cursor second-track fully retired per ADR-0185 P5`);
- `lca/infrastructure/observability/loop_cursor/std/std.py:355` — payload copy,**改为不拷贝**;
- `lca/infrastructure/observability/loop_cursor/coordinator/adapter.py:198,209` — 注释 + 空字符串赋值,**改为不赋值**;
- `lca/infrastructure/observability/spine/derivers/step/tree_accumulator.py:517` — fold 注释,**改注释**;
- 6 个测试文件:`test_loop_cursor_wiring.py`、`test_observation_ssot_regression.py`、`test_step_tree_accumulator.py`(2 处)、`test_invariants.py`(3 处)、`test_halt_resume.py`、`test_cursor_record.py`(3 处)、`test_coordinator_adapter.py`(1 处断言 + 注释)、`test_payloads.py`、`test_std_loop_cursor.py`。**全部更新**。

`args_payload_path` 同理删除(它原本就是与 `args_digest` 配对的 sidecar 指针;`arguments` / `arguments_summary` 已承担该职能)。

## 3. 每个契约的 schema 形态 + 迁移步骤

### 3.1 Effect kind

| 文件 | 字段 | 旧值 / 缺位 | 新值 |
|---|---|---|---|
| `lca/contracts/protocols/runtime/infra/infra.py` | `Tool.effect_kind: ClassVar[Literal[...]]` | 缺 | 新增(默认 `ephemeral`) |
| `lca/contracts/models/core/execution/tool.py` | `ToolApi.effect_kind: Literal[...]` | 缺 | 新增(默认 `"ephemeral"`) |
| `lca/contracts/harness/memory/events.py` | `SkillActivated.effect_kind: Literal["stateful_once"]` | 缺 | 新增(默认 `"stateful_once"`) |
| `lca/infrastructure/observability/meta_event_emit.py:130` `emit_skill_activated` | 新增 `effect_kind="stateful_once"` 透传 | — | 加参数并传给 `SkillActivated` |

**注意:** `SkillActivated` 是 **现有事件**,仅扩展 payload;AGENTS §0 显式禁止"新增平行事件词表"。

### 3.2 Digest 助手

| 步骤 | 文件 | 操作 |
|---|---|---|
| 1 | `lca/contracts/observability/canonical_digest.py` | 新建,实现 `canonical_digest(payload, *, length, prefix, ensure_ascii)` |
| 2 | 17 个迁移站点(见 §3.3) | 替换 inline digest 为 `canonical_digest(payload, length=…, prefix=…)` |
| 3 | `tests/contracts/test_canonical_digest.py` | 5 个单元测试,覆盖基本 / 长度 / 前缀 / 默认值 / 类型 |

### 3.3 Digest 迁移站点(按 task 枚举顺序)

| # | 文件:行 | 旧值 | 新值 |
|---|---|---|---|
| 1 | `lca_kernel/events/session/session.py` | (无 digest) | — (本 ADR 不动;task 列举的扫描未命中;若后续发现新站点按同样模式迁移) |
| 2 | `lca/contracts/runtime/plan_proposal.py:165` | `hashlib.sha256(canonical.encode("utf-8")).hexdigest()` | `canonical_digest(canonical, length=64, prefix="")` |
| 3 | `lca/harness/plan.py:39` | `hashlib.sha256(...).hexdigest()[:32]` | `canonical_digest(value, length=32)` |
| 4 | `lca/harness/plan.py:55` | `hashlib.sha256(...).hexdigest()[:16]` | `canonical_digest(payload, length=16)` |
| 5 | `lca/cognition/brain/prompt/surface.py:46` | `hashlib.sha256(payload).hexdigest()[:16]` | `canonical_digest(payload, length=16)` |
| 6 | `lca/cognition/brain/pipeline/context_manifest.py:29` | `hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]` | `canonical_digest(payload, length=16)` |
| 7 | `lca/cognition/memory/semantic/compaction.py:174` | `sha256("\0".join(source_ids).encode("utf-8")).hexdigest()[:16]` | `canonical_digest("\0".join(source_ids), length=16)` |
| 8 | `lca/harness/diagnostics/normalizer/normalizer.py:14` | `hashlib.sha256(repr(value).encode("utf-8")).hexdigest()[:16]` | `canonical_digest(repr(value), length=16)` |
| 9 | `lca/plugins/learning/review_service.py:262` | `sha256(event_key.encode("utf-8")).hexdigest()[:16]` | `canonical_digest(event_key, length=16)` |
| 10 | `lca/plugins/skill/auto_acquire.py:63` | `sha256(f"{task_ref}\0…".encode()).hexdigest()[:16]` | `canonical_digest(f"{task_ref}\0…", length=16)` |
| 11 | `lca/plugins/transport/webserver/handlers/runs/session/builder/builder.py:93` | `hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]` | `canonical_digest(payload, length=16)` |
| 12 | `lca/plugins/transport/webserver/handlers/runs/session/index/index.py:42` | `hashlib.sha256(payload).hexdigest()[:24]` | `canonical_digest(payload, length=24)` |
| 13 | `lca/infrastructure/observability/journal/engine/journal_io.py:82` | `"evt_" + hashlib.sha256(material).hexdigest()[:24]` | `canonical_digest(material, length=24, prefix="evt_")` |
| 14 | `lca/contracts/harness/journal/artifact.py:135` | `hashlib.sha256(content_bytes).hexdigest()[:16]` | `canonical_digest(content_bytes, length=16)` |
| 15 | `lca/contracts/protocols/perceive/capability_plan.py:135` | `hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]` | `canonical_digest(blob, length=16)` |
| 16 | `lca/contracts/protocols/state/scope_plan.py:131` | `hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]` | `canonical_digest(blob, length=16)` |
| 17 | `lca/infrastructure/computer/machine/exec.py:56` | `hashlib.sha256(f"{code}:{time.monotonic()}".encode()).hexdigest()[:12]` | `canonical_digest(f"{code}:{time.monotonic()}", length=12)` |
| 18 | `lca/harness/declarative/compile/instrument/wrap.py:196` | `hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:16]` + `"sha256:"` 前缀 | `canonical_digest(rendered, length=16)` |

**注:** `lca_kernel/events/session/session.py` 是 task 列举的第 1 项,但读后发现该文件无 digest 实现,跳过。

**保留(非本 ADR 范围):** `meta_event_emit.tool_registry_digest`、`_home_layout.py:122` 的 `sha256_digest(path)` (file-bytes streaming)、`hashlib.new(self.algorithm)` 动态算法(evidence store)、HMAC(`auth.py`)— 这些不是 canonical-JSON-of-payload 形态,助手签名不适用。

### 3.4 ToolCallRecord 字段删除迁移

| # | 文件 | 旧 | 新 |
|---|---|---|---|
| 1 | `lca/contracts/observability/cursor/loop_cursor_payloads.py:77-87` | 包含 `args_digest`、`args_payload_path` | 删除两字段,保留 `tool_name / call_seq / arguments / arguments_summary / invocation_id` |
| 2 | `lca/cognition/body/executor/cursor_record.py:105,137` | `args_digest: str = ""` 参数 + `args_digest=args_digest, args_payload_path=None,` 构造 | 删除参数与字段;保留 `tool_name / call_seq / arguments / arguments_summary / invocation_id` |
| 3 | `lca/infrastructure/observability/loop_cursor/std/std.py:355` | `"args_digest": payload.args_digest, "args_payload_path": payload.args_payload_path,` | 整行删除 |
| 4 | `lca/infrastructure/observability/loop_cursor/coordinator/adapter.py:198,209` | 注释引用 + `args_digest="", args_payload_path=None,` | 删除字段,删注释中"args_digest"提及 |
| 5 | `lca/infrastructure/observability/spine/derivers/step/tree_accumulator.py:517` | 注释 | 改注释(删除"args_digest"提及) |
| 6 | 9 个测试文件(见 §2.3) | 构造 `ToolCallRecord(...args_digest=…)` 或断言 `payload["args_digest"] == ...` | 移除 `args_digest` kwarg / 字段访问 |

`tests/contracts/test_record_step_tool_call_wrapper.py` 已有断言 `"args_digest" not in payload`(行 65),与本 ADR 方向一致;其它测试需要从构造调用中移除 `args_digest` kwarg。

## 4. delete-when

```text
inline digest sites outside canonical_digest.py:
  delete_when:
    rg "hashlib\.sha256|hashlib\.new" lca/ lca_kernel/ | grep -v canonical_digest
    == 0
    (排除 streaming-HMAC / dynamic-algorithm / file-bytes 站点;保留项在 §3.3 注)

effect_kind field on Tool + ToolApi:
  delete_when:
    rg "effect_kind" lca/contracts/models/core/execution/tool.py returns the field
    and every tool implementation declares it (or falls through default "ephemeral")

args_digest removed from ToolCallRecord:
  delete_when:
    "args_digest" not in ToolCallRecord.__dataclass_fields__
    (verified by `rg "args_digest" lca/contracts/observability/cursor/` == 0)

SkillActivated carries effect_kind discriminator:
  delete_when:
    SkillActivated.effect_kind field exists in
    lca/contracts/harness/memory/events.py and emit_skill_activated passes
    effect_kind="stateful_once"
```

## 5. 验证

### 5.1 架构测试

- `tests/contracts/test_canonical_digest.py` — 5 个测试,覆盖基本 / 长度 / 前缀 / 默认值 / 类型。
- `tests/contracts/test_record_step_tool_call_wrapper.py` — PR-1 锁定测试,断言 `"args_digest" not in payload`(已存在,行 65)。
- `tests/observability/loop_cursor/test_payloads.py::test_tool_call_record_call_seq_required` — 移除 `args_digest` kwarg 后仍通过(只剩 `tool_name / call_seq`)。

### 5.2 命令门禁

```bash
# 1. 助手 SSOT
rg "hashlib\.sha256|hashlib\.new" lca/ lca_kernel/ | grep -v canonical_digest
# 期望:除 §3.3 注保留项外,无输出

# 2. effect_kind 落地
rg "effect_kind" lca/contracts/models/core/execution/tool.py
# 期望:返回 ToolApi.effect_kind 字段

# 3. args_digest 移除
rg "args_digest" lca/contracts/observability/cursor/loop_cursor_payloads.py
# 期望:无输出

# 4. 测试 + lint
pytest tests/contracts/test_canonical_digest.py \
       tests/contracts/test_record_step_tool_call_wrapper.py -q
ruff check lca/contracts/observability/canonical_digest.py \
           lca/contracts/protocols/runtime/infra/infra.py \
           lca/contracts/models/core/execution/tool.py \
           lca/contracts/observability/cursor/loop_cursor_payloads.py \
           lca/contracts/harness/memory/events.py
git diff --check
```

## 6. 不变量

| ID | 内容 |
|---|---|
| **E1** | `effect_kind` 是闭集 `Literal["ephemeral", "persistent", "stateful_once"]`,不接受自由字符串 |
| **E2** | `is_idempotent` 保留,与 `effect_kind` 正交 |
| **E3** | `SkillActivated` 扩展 `effect_kind` 不开新事件词表 |
| **D1** | digest 助手是 canonical JSON + sha256 hex 形态的**唯一** SSOT |
| **D2** | 助手暴露 `length` + `prefix` 参数,不强制统一长度 |
| **D3** | streaming-HMAC / dynamic-algorithm / file-bytes 站点不强制走助手 |
| **A1** | `args_digest` / `args_payload_path` 从 `ToolCallRecord` 删除,所有读者同 PR 迁移 |
| **A2** | 业务路径 `record_step_tool_call` / `record_step_tool_result` 不受影响(已 PR-1 锁定) |

## 7. 关联

- [0193 Session Projection Fabric](0193-session-projection-fabric-model-visible.md) — projection 边界
- [0194 认知 Loop 收敛](0194-cognitive-loop-architecture-convergence.md) — cognition / runtime / agent 分层
- [0195 全栈架构收敛](0195-platform-architecture-convergence.md) — 四段链 + SSOT 矩阵
- [0185 Model-Visible Event Bus](0185-model-visible-event-bus-alignment.md) — §2.5 P5 `args_digest` deprecation 源
- [0101 Tool Facts & Evidence Only](0101-tool-facts-and-evidence-only.md) — Tool 事件回归事实

## 8. 配套 Note

[`docs/notes/implemented/seam/2026-09-08-end-to-end-field-contract.md`](../notes/implemented/seam/2026-09-08-end-to-end-field-contract.md) — 审计 + 迁移记录
