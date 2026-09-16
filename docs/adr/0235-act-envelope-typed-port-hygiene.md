# ADR-0235 — `act.envelope` C13 卫生 — `state` / `decision` 反抽到 typed port

**Status:** Accepted — 2026-09-16. PR-5 of `2026-09-16-act-subgraph-tightening`.

> **一句话**: 把 `act.envelope` 节点 `metadata={"state": ..., "decision": ...}` 偷渡的 typed 数据反抽回 typed port(`act.envelope` 的 `declared_inputs` 增加 `state`;`effect.execute` 节点的 `declared_inputs` 扩展到 `[envelope, decision, state]`;`EffectDispatcher.execute` Protocol 签名增加 `*, state=None, decision=None` typed keyword-only 参数)。`metadata` 仅保留 op-relative 字段(`effect_class` / `operation`),把 envelope 单据恢复为「effect gateway 单据」(C2 双平面)。同步删除 `_existing_effect_receipt` / `_validated_effect_class` 内对 `envelope.metadata` 的 state / decision 偷读;`PipelineSafeExecutor` 把 `plan_ref` / `scope_ref` 收口为构造时注入 typed provider,不再读 observability scope。

**Refines / Fixes:**
- ADR-0195 §1.4 C13 — typed Contract 跨边界 = fail-loud,无 Contract 跨边界 = fail。`metadata: dict[str, Any]` 是 typed-port 反例。
- 「act 业务不知道图存在」边界(2026-09-16 user 评审第二轮)— `PipelineSafeExecutor` 当前调 `get_current_plan_ref()` / `get_current_run_scope()`(observability scope seam)偷图状态;`envelope.py` 通过 `context.runtime.state` 偷图 state。
- 「图不知道 act 业务」边界 — 维持:`EffectDispatcher` Protocol 仍只接收 typed `envelope + policy`(+ new keyword-only `state` / `decision`),不 import `Action` / `ActionRegistry` / `Tool` 内部字段。
- envelope 单据污染 — C2 双平面违反:cognition 内部数据(state / decision)进入 effect gateway 单据。

## Problem

`act.envelope` 节点(`lca/nodes/act/envelope/envelope.py`)当前实现:

```python
envelope = mint_envelope(
    plan_ref=plan_ref,
    scope_ref=node_ref,
    decision=decision,
    provider="effect.body",
    grant=CapabilityGrant(capability="body.act", scope="run", effect_class="tools"),
    idempotency_key=f"{plan_ref}:{node_ref}:{decision.decision_id}",
    metadata={
        "effect_class": "tools",
        "operation": "body.act",
        "state": context.runtime.state,    # 偷图 runtime state
        "decision": decision,                # typed Decision 经 metadata 偷渡
    },
)
```

三重违反:

1. **C13 typed-port 反例**: `metadata: dict[str, Any]` 不带 schema;`state: AgentState` / `decision: Decision` 应走 typed port 或 typed DTO 字段,不应进 `metadata`。
2. **「act 业务不知道图存在」边界违反**: `context.runtime.state` 是图 kernel 偷 state;`act.envelope` 应通过 typed port(`state` declared input)接收。
3. **envelope 单据污染**: envelope 是 effect gateway 单据(act 业务 → effect gateway 单据),不应承载 cognition 内部 state / decision(违反 C2 双平面:cognition 内部数据进入 effect gateway 单据)。

辅助问题:`PipelineSafeExecutor.execute`(`lca/cognition/body/executor/pipeline_safe_executor.py`)内 `_legacy_envelope` helper 调 `get_current_plan_ref()` / `get_current_run_scope()`(observability scope seam)偷 plan_ref / scope_ref。这是图边界渗透到 act 业务。

`lca/harness/declarative/execute/dispatch.py` 内 `_existing_effect_receipt` / `_validated_effect_class` 当前从 `envelope.metadata.get("approved", ...)` 读 approval 标志(typed-port 反例;approval 应走 typed 参数或 envelope 字段)。

## Decision

### 1. `act.envelope` declared_inputs / declared_outputs 扩展

| 当前 | 目标 |
|---|---|
| `declared_inputs = ("decision",)` | `declared_inputs = ("decision", "state")` |
| `declared_outputs = ("envelope",)` | `declared_outputs = ("envelope", "decision", "state")` (透传) |

`node_execute` 改为读 `input.port_values["decision"]` + `input.port_values["state"]`;不再读 `context.runtime.state`;metadata 仅保留 `effect_class` / `operation` typed 字段。

### 2. `act.dispatch` declared_inputs 扩展

`bundles/act/act_subgraph.yaml` 在 `act.dispatch` 上 `inputs` 增加 `state`,`outputs` 增加 `state`(透传)。`verdict_refs` 已由 PR-2 加入,本 PR 顺序在 PR-2 之后。

### 3. `effect.execute` declared_inputs 扩展

`bundles/concept/effect/effect_execute.yaml` `effect.execute` 的 `inputs: [envelope, verdict_refs]` 扩展到 `[envelope, verdict_refs, decision, state]`。

`lca/nodes/concept/effect/execute.py` `_dispatch` 在调 `gateway.execute(envelope, policy)` 时通过 typed kwargs 把 `decision` / `state` 透传:

```python
output = await gateway.execute(envelope, policy, decision=decision, state=state)
```

### 4. `EffectDispatcher.execute` Protocol 签名扩展

`lca/contracts/protocols/declarative/declarative_1/declarative_execution.py` Protocol 签名从:

```python
class EffectDispatcher(Protocol):
    async def execute(self, envelope: CommandEnvelope, policy: EffectPolicyPlan) -> object: ...
```

扩展为:

```python
class EffectDispatcher(Protocol):
    async def execute(
        self,
        envelope: CommandEnvelope,
        policy: EffectPolicyPlan,
        *,
        state: AgentState | None = None,
        decision: Decision | None = None,
    ) -> object: ...
```

keyword-only typed 参数;`state` / `decision` 不参与 protocol 结构化签名(consumer 仍可读 `envelope`),但 typed-kwargs 路径是 explicit typed Contract,符合 C13。

### 5. `EffectDispatcherFactory` Protocol 签名扩展

`lca/contracts/protocols/runtime/runtime/composition.py:148-157` `EffectDispatcherFactory.create` 同步扩展:

```python
class EffectDispatcherFactory(Protocol):
    def create(
        self,
        *,
        capabilities: EffectCapabilities,
        effect_handler_registry: EffectHandlerRegistry,
        idempotency_store: IdempotencyStore,
        state: AgentState | None = None,    # typed-injected for dispatcher construction
        decision: Decision | None = None,
    ) -> EffectDispatcher: ...
```

`state` / `decision` 通过 typed kwargs 注入 factory,允许 dispatcher 构造时缓存 typed 字段;不需要时传 `None`。**typed-injection 不破坏单例性**(dispatcher 仍可在 per-call `execute` 时接受 fresh state / decision)。

### 6. `RegistryEffectDispatcher.execute` 实现同步扩展

`lca/harness/declarative/execute/dispatch.py` `RegistryEffectDispatcher.execute` 签名从:

```python
async def execute(self, envelope: CommandEnvelope, policy: EffectPolicyPlan) -> object:
```

扩展为:

```python
async def execute(
    self,
    envelope: CommandEnvelope,
    policy: EffectPolicyPlan,
    *,
    state: AgentState | None = None,
    decision: Decision | None = None,
) -> object:
    # state / decision 通过 typed keyword-only 参数;不从 envelope.metadata 偷
    ...
```

`_existing_effect_receipt` / `_validated_effect_class` 内所有 `envelope.metadata.get("state", ...)` / `envelope.metadata.get("decision", ...)` 偷读路径删除;若需要 state / decision,从 typed 参数取。

`_require_effect_approval` 当前从 `metadata.get("approved", False)` 读;本 PR 同步修:

```python
def _require_effect_approval(
    effect_class: str,
    decision: Decision | None,
    policy: EffectPolicyPlan,
) -> None:
    """Enforce approval policy before selecting a world operation handler."""
    if effect_class not in policy.approval_required:
        return
    approved = bool(decision and getattr(decision, "needs_approval", False) is False)
    # Approval signal lives on Decision.needs_approval (PR-5 §7a typed-field);
    # rejection = decision carries needs_approval=True and no approve command seen.
    ...
```

### 7. `PipelineSafeExecutor` 不再读图(`act 业务不知道图存在`边界守护)

`lca/cognition/body/executor/pipeline_safe_executor.py` `PipelineSafeExecutor.__init__` 增加 `plan_ref_provider` / `scope_ref_provider` typed kwargs:

```python
def __init__(
    self,
    permission_manifest: ToolPermissionManifest,
    *,
    plan_ref_provider: Callable[[], str | None] | None = None,
    scope_ref_provider: Callable[[], str] | None = None,
):
    self._plan_ref_provider = plan_ref_provider
    self._scope_ref_provider = scope_ref_provider
    ...
```

`_legacy_envelope` 改为从 `self._plan_ref_provider()` / `self._scope_ref_provider()` 取,而不是从 observability scope 偷。生产路径由图 kernel 在构造 `PipelineSafeExecutor` 时注入「读 contextvar」adapter;测试路径直接注入 literal provider。

### 8. `act.observe.commit_fact` 改用 typed kernel capability 注入(R-3 follow-through)

PR-3 把 `act.observe.commit_fact` 拆出独立节点,但该节点内部仍 `getattr(runtime, "journal", None)` 静默 skip。PR-5 同步修:

```python
@dataclass(frozen=True, slots=True)
class ActObserveCommitFactExecutor:
    semantic_name: str = "act.observe.commit_fact"
    region: str = "act"
    declared_inputs: tuple[PortName, ...] = ("receipt",)
    declared_outputs: tuple[PortName, ...] = ("receipt",)

    def __init__(self, *, journal_capability: JournalCapability | None = None):
        self._journal = journal_capability

    async def node_execute(self, context, input) -> NodeOutput:
        # No more getattr(runtime, "journal", None) silent skip.
        if self._journal is None:
            raise RuntimeError(
                "act.observe.commit_fact: 'journal' capability missing — "
                "kernel must inject typed JournalCapability at construction."
            )
        receipt = input.port_values.get("receipt")
        ...
```

`journal_capability` 由 kernel 在装配时通过 typed kwargs 注入(fail-loud);测试可在 setup 时传 mock `JournalCapability`。

### 9. `act.approve.gate` 删 `_resolve_port` 偷图 + `Decision.needs_approval` typed 字段(L-2 / G-9 follow-through)

`lca/nodes/intervene/approve_gate.py:78-87` `_resolve_port` 函数删除(用 `getattr(context.runtime, name, None)` 偷图 runtime)。

`Decision`(`lca/contracts/models/core/execution/decision.py`)加 typed `needs_approval: bool = False` 字段(替代 `extra["needs_approval"]`)。`act.authorize` 当前 emit `approval_required = bool(decision.extra.get("needs_approval", False))`(PR-1)改为 `bool(decision.needs_approval)`。

## Alternatives Considered

- **(a) 维持 metadata** — 拒绝:违反 C13 typed-port + 「act 业务不知道图存在」边界 + envelope 单据污染(C2 双平面)三重。
- **(b) 把 state / decision 直接进 envelope 字段** — 拒绝:envelope 是 effect gateway 单据(act 业务 → effect gateway 单据);cognition 内部 state / decision 进入 envelope 等于 cognition 状态污染 effect gateway 单据(违反 C2 双平面)。
- **(c) typed port 透传** — **接受**:符合 C13 + 「act 业务不知道图存在」边界 + typed-port kernel native。
- **(d) `Decision.needs_approval` 用 Pydantic 字段而非 dataclass** — 拒绝:Decision 当前是 frozen dataclass;Pydantic 字段增加迁移面;按 dataclass 字段加 `needs_approval: bool = False` 最小侵入。

## Consequences

### 正面

- `act.envelope.metadata` 仅保留 `effect_class` / `operation` typed 字段;state / decision 通过 typed port 透传。
- `RegistryEffectDispatcher.execute` 不再从 metadata 偷 state / decision;签名明确 typed kwargs。
- `_existing_effect_receipt` / `_validated_effect_receipt` 不依赖 metadata 偷读(本 PR 不删这两个 helper 的 envelope-shape check;只删 metadata 偷 state / decision / approved 的路径)。
- `PipelineSafeExecutor` 把 `plan_ref` / `scope_ref` 收口为构造时注入 typed provider,不再读 observability scope;**「act 业务不感知图」verification** 通过。
- `EffectDispatcher.execute` Protocol 签名扩展为 typed keyword-only `state` / `decision`;consumer (`effect.execute`) 同步更新调用点。
- `act.observe.commit_fact` 不再 `getattr(runtime, "journal", None)` 静默 skip;journal capability 由 kernel typed-injection(R-3 follow-through)。
- `act.approve.gate` 不再 `getattr(context.runtime, ...)` 偷图;`Decision.needs_approval` typed 字段替代 `extra["needs_approval"]`(L-2 / G-9 follow-through)。

### 同步改造(本 PR 范围)

- `lca/contracts/protocols/declarative/declarative_1/declarative_execution.py` `EffectDispatcher` Protocol 签名扩展
- `lca/contracts/protocols/runtime/runtime/composition.py` `EffectDispatcherFactory` 签名扩展
- `lca/harness/declarative/execute/dispatch.py` `RegistryEffectDispatcher.execute` 实现扩展 + `EffectDispatcherFactory` 同位置实现同步
- `lca/nodes/act/envelope/envelope.py` `declared_inputs` / `declared_outputs` / `node_execute` 改造
- `lca/cognition/body/executor/pipeline_safe_executor.py` `__init__` 增加 `plan_ref_provider` / `scope_ref_provider` typed kwargs;`_legacy_envelope` 改读 typed providers
- `lca/nodes/act/observe/commit_fact.py` `__init__` 增加 `journal_capability` typed kwarg;`node_execute` 不再 `getattr(runtime, ...)`
- `lca/nodes/intervene/approve_gate.py` 删 `_resolve_port`;`Decision.needs_approval` typed 字段
- `lca/contracts/models/core/execution/decision.py` `Decision.needs_approval: bool = False` typed 字段
- `lca/nodes/act/authorize/authorize.py` emit `approval_required = bool(decision.needs_approval)`
- `bundles/act/act_subgraph.yaml` `act.envelope` 节点 inputs / outputs
- `bundles/concept/effect/effect_execute.yaml` `effect.execute` 节点 inputs
- `lca/nodes/concept/effect/execute.py` `_dispatch` 把 `decision` / `state` 通过 typed kwargs 传 `gateway.execute(...)`

### architecture test 守护

- `scripts/check_command_envelope_required.py` 仍通过(stack trace 仍含 `mint_envelope`,由 `PipelineSafeExecutor._legacy_envelope` 调 `mint_envelope` 守护)
- 新测试 `tests/act/test_envelope_typed_port_hygiene.py`:metadata 不再含 state / decision
- 新测试 `tests/contracts/test_decision_needs_approval_typed.py`:Decision 有 typed `needs_approval` 字段
- 新测试 `tests/intervene/test_approve_gate_no_runtime_grab.py`:`act.approve.gate` 只读 typed ports

### verification commands

- `grep -rn "lca.framework.graph\|from lca.framework" lca/cognition/ lca/plugins/cognitive/body/` 期望 0 matches
- `grep -rn "_existing_effect_receipt\|_validated_effect_class" lca/` 期望 0 matches(本 PR 删除 helpers)
- `grep -rn "context.runtime.state\|context.runtime.plan_ref\|NodeContext\|NodeInput\|NodeOutput" lca/cognition/body/` 期望 0 matches(act 业务不直接操作 NodeContext / port_values,只通过 SafeExecutor / Body 接口)
- `grep -rn "metadata=.state\|metadata={\"state" lca/nodes/act/ lca/harness/declarative/` 期望 0 matches
- `grep -rn "metadata=.decision\|metadata={\"decision" lca/nodes/act/ lca/harness/declarative/` 期望 0 matches

## Verification

- `ruff check` + `ruff format` 0 introduced violations
- `pytest tests/act tests/intervene tests/contracts/observability tests/integration/test_no_dual_sink.py tests/lca_kernel/plan/test_phase_main_outer_lift.py tests/effect -q` 全绿
- `pytest tests/contracts/test_decision_needs_approval_typed.py tests/intervene/test_approve_gate_no_runtime_grab.py tests/act/test_envelope_typed_port_hygiene.py -q` 全绿
- `./scripts/lca-ops plan tree profiles/web-standard.yaml` → "✓ all layers inflated and validated"
- `./scripts/lca-ops audit-state-writers` → "No state mutations detected"
- `python -c "from lca.cognition.body.executor.pipeline_safe_executor import PipelineSafeExecutor; import inspect; assert 'mint_envelope' in inspect.getsource(PipelineSafeExecutor.execute); print('OK')"` 仍打印 OK
- `python scripts/check_command_envelope_required.py` → "OK: all execute() methods include mint_envelope call"

## delete-when

N/A — typed-port extension 是新契约,旧 metadata 偷读路径同一 PR 删除,无遗留。