# Agent Note: 子 note 4 — payload schema 类型化与运行时校验(L2 类型化 + L3 校验)

Status: proposed

> 根 note 与元决策:[observation-convergence-root.md](../seam/2026-09-03-observation-convergence-root.md) / [ADR-0178](../../../adr/0178-observation-control-state-convergence.md)。本 note 收 L2 类型化 + L3 运行时校验。

## Problem

`lca/contracts/observability/event_descriptor_registry.py` 40 行**只是 EP 名表**,无 payload schema 约束:

```python
# 现状:每个 EP 自填 payload,Registry 不约束
_event_descriptor_registry: dict[str, EventDescriptor] = {
    "exception.caught": EventDescriptor(...),  # 无 payload schema
    "step.tool_call.record": EventDescriptor(...),
    ...
}
```

后果(用户 2026-09-03 反馈的"payload schema 缺失"):

- 几十处 `payload={...}` 裸 dict,每个 emitter 自填 schema
- `exception.caught` 4 键裸 dict 缺 `traceback_text` → < 4 KiB → 不 offload → **traceback 永久丢失**
- `step.tool_call.record` payload 缺 `arguments` / `output` → deriver 重投影失败
- 新加 EP 时**容易忘记填必填字段**——Registry 不检查,运行时才发现

DSH(`~/deepseek-harness/packages/core/session/src/types.ts:366-420`)对照:`SessionEventMap` 是 TS 字面 union map,**每个 EP 都有 payload 类型约束**,`session.append<T>(type: T, data: SessionEventMap[T])` 编译期拒绝非法 payload。LCA 没有 TS,需要 Python 路径。

## Proposal

### 第一阶段:L2 类型化 dataclass

`lca/contracts/observability/event_payload_schema.py` 新建,定义每个 EP 的 payload 类型:

```python
@dataclass(frozen=True, slots=True)
class ExceptionCaughtPayload:
    boundary: str
    exception_class: str              # 必填,替代 exc_type
    exception_message: str             # 必填,替代 message
    traceback_text: str                # 必填,新增
    call_frames: tuple[CallFrame, ...] # 必填,新增
    err_kind: ErrKind                  # 必填,新增
    trace_id: str                      # 必填

@dataclass(frozen=True, slots=True)
class StepToolCallRecordPayload:
    step_id: str
    tool_name: str
    arguments: Mapping[str, Any]       # 必填
    output: str                        # 必填
    outcome: ExecutionOutcome          # 必填
    duration_ms: int                   # 必填

# 其他 EP payload 类型同样定义(估算 20-30 个 EP)
```

约束:每个 EP 在 `event_descriptor_registry.py` 加 `payload_class: type` 字段(指向 dataclass)。

### 第二阶段:L3 运行时校验

引入 `EventPayloadModel`(pydantic v2 或自建):

```python
# 选 pydantic v2:生态好,BaseModel.parse_obj / model_validate
# 选自建 dataclass + __post_init__:零依赖,但需重写验证器
```

倾向 **pydantic v2**——LCA 已用 pydantic(根 note §L2 表"`to_jsonable` 合并"用了 `model_dump`),无需新增依赖。

`emit_*` 入口加校验:`payload = PayloadModel.model_validate(payload)`——任何字段缺失 / 类型错误直接抛 `EventPayloadValidationError`。

### 第三阶段:L4 Protocol 签名收紧

承接 note 3,`EnvelopeEmitter` Protocol 收类型化 record:

```python
# 之前
def emit_exception_caught(boundary: str, exc_type: str, message: str, trace_id: str | None) -> EventRecord | None

# 之后
def emit_exception_caught(record: ExceptionRecord) -> EventRecord | None
```

`ExceptionRecord` 已在 `lca/contracts/observability/exception_capture.py:117` 定义,扩展其字段对齐 `ExceptionCaughtPayload`。

### 第四阶段:EP 注册收口

`event_descriptor_registry.py` 升级为 schema registry:

```python
_event_descriptor_registry: dict[str, EventDescriptor] = {
    "exception.caught": EventDescriptor(
        payload_class=ExceptionCaughtPayload,
        channel="error",
        fsync_protocol=FsyncProtocol.PER_WRITE,  # 承接 note 2
    ),
    ...
}
```

新加 EP 必须填 `payload_class`——`scripts/check_observation_ssot.py` 加规则:`registry 中每个 EP 必含 payload_class`。

## Decision criteria

- `lca/contracts/observability/event_payload_schema.py` 新建,定义 ≥ 20 个 EP payload dataclass
- `event_descriptor_registry.py` 每个 EP 含 `payload_class`
- `emit_*` 入口加 `model_validate(payload)`,缺字段抛 `EventPayloadValidationError`
- `EnvelopeEmitter` Protocol 收类型化 record(承接 note 3)
- 现有 `ExceptionRecord` 扩展对齐 `ExceptionCaughtPayload`

## Alternatives considered

### Why not 自建 dataclass + `__post_init__` 不依赖 pydantic?

pydantic v2 自带 `model_dump` / `model_validate` / `model_dump_json`,LCA 已有依赖(pydantic 在 `pyproject.toml`)。自建 dataclass + 验证器**重复造轮子**。

### Why not 全部 EP 一次性 payload 类型化?

LCA spine emit 路径有 ~30-50 个 EP,一次性改 ≥ 30 个 dataclass 跨多个 PR,**违反 AGENTS.md §1 "1-3 PR 列表"**。本 note 分阶段:第一阶段优先 `exception.caught` / `step.tool_call.record` / `phase.*.fold` / `llm.call.*` / `body.tool.execute.*` 5 类 hot path(覆盖 ~70% 用户反馈的"字段缺失"场景),其余 EP 按需迁移。

### Why not 用 Protocol + Generic 不引入 dataclass?

```python
T = TypeVar("T", bound=BaseModel)
def emit_exception_caught(payload: ExceptionCaughtPayload) -> EventRecord: ...
```

Generic 不能约束 payload shape,**只能约束 caller 传对类型**,不能约束"传对字段"。pydantic 校验是必要的。

### Why not 跳过 L3 校验,只做 L2 类型化?

L2 类型化只对**用 dataclass 类型注解的 caller**有效——`dict` 仍可绕过(动态 Python)。L3 运行时校验是 L2 漏的兜底。**4 级收敛缺一不可**(根 note §1)。

## Acceptance criteria

- `lca/contracts/observability/event_payload_schema.py` 新建,定义 ≥ 5 类 hot path EP 的 payload dataclass
- `event_descriptor_registry.py` 每个 EP 含 `payload_class` 字段
- `tests/contracts/observability/test_event_payload_schema.py` 新建:每个 payload dataclass 至少 3 case(必填 / 选填 / 校验失败)
- `tests/observability/spine/test_emit_validation.py` 新建:`emit_exception_caught({})` 必须抛 `EventPayloadValidationError`
- `scripts/check_observation_ssot.py` 加规则:`registry 中 payload_class 缺失 = fail`
- 现有 `ExceptionRecord` 字段对齐 `ExceptionCaughtPayload`(向后兼容:`exc_type` / `reason` legacy alias 通过 `asdict()` 同时给两套键,承接根 note §"asdict legacy alias"已定的策略)

## Risks

- **pydantic v2 性能**:每个 emit `model_validate` ~0.5-1ms,spine 高频路径(LLM streaming chunks)需白名单豁免。豁免条件:`payload_class is None` 或 EP 在 `_FAST_PATH_EPS` 列表里
- **`ExceptionRecord` 与 `ExceptionCaughtPayload` 字段同步**:两套定义并存 = 双写风险。本 note 强制:**`ExceptionCaughtPayload` 是契约层,**`ExceptionRecord` 是 infrastructure 层(继承 / 持有),不重复定义
- **20-30 EP payload dataclass 一次写不完**:本 note 第一阶段只覆盖 5 类 hot path,剩余 EP 在后续 PR 增量补——`registry` 加 schema 是**渐进式**而非一次性

## Delete-when

- **`registry` EP 无 `payload_class` 兼容**:若有,`# COMPAT(delete-when: 全 EP 含 payload_class 且 lint 命中 = 0, tracking: ADR-0178-note-4)`
- **`model_validate` 跳过白名单**:若有,`# COMPAT(delete-when: 高频 EP 都有轻量 schema 且性能回归 < 5%, tracking: ADR-0178-note-4)`
- **`ExceptionRecord` legacy alias(`exc_type` / `reason`)**:根 note 已定,`# COMPAT(delete-when: 全 reader 迁完且 rg 命中 = 0, tracking: ADR-0178-note-4)`

## Related

- [observation-convergence-root.md](../seam/2026-09-03-observation-convergence-root.md) — 根 note
- [ADR-0178](../../../adr/0178-observation-control-state-convergence.md) — 元决策
- [`docs/notes/implemented/seam/2026-09-03-model-visible-incomplete-projection.md`](../../implemented/seam/2026-09-03-model-visible-incomplete-projection.md) — model_visible 投影缺三件事(本 note 覆盖 `_to_jsonable` 5 段回退)
- `lca/contracts/observability/exception_capture.py` — `ExceptionRecord` / `exc_to_record` SSOT
- `lca/contracts/observability/event_descriptor_registry.py` — 升级为 schema registry
- `~/deepseek-harness/packages/core/session/src/types.ts` — `SessionEventMap` 参考
