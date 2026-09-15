# ADR-0228: plan / intervene / delegate subgraphs + `@graph_node` retirement

## Status

Accepted. Supersedes ADR-0227 (typed-boundary `@graph_node` decorator).

## Context

The session-write-path cutover (PR1 + PR2 + PR3, commits `19dfbc4cf` .. `30e12d45f`) landed six-phase subgraph bundles under `bundles/{perceive,think,act,reflect,remember,stop}/*_subgraph.yaml` plus an outer `bundles/outer/phase_main.yaml`. PR3 (this branch) introduced a typed-boundary `@graph_node` decorator at `lca/nodes/_decorator.py` per ADR-0227, intending to generalise the hand-written `@plugin(...)` pattern that the 3 PR3 think nodes followed.

Three observations from the cutover force this ADR:

**1. `@graph_node` produces the wrong artifact for the kernel.** The decorator wraps an async function into a `@plugin(...)` carrier whose `setup` callback lives at `<carrier>.setup.setup`. The bundle resolver loads modules by `$module:` import path and reads the module-level `setup(ctx, config=None)` callable. `@graph_node`-decorated modules do not publish a top-level `setup` (the cordis carrier is the module itself, with `setup` as a nested attribute), so the kernel's bundle lookup silently skipped every `@graph_node`-decorated module. The runtime never saw the node and every backend run failed at H6 with `NodeExecutor lookup miss`. This was caught by `daee237b6 refactor(nodes): rewrite 3 think nodes with @plugin(...) instead of @graph_node`, which converted the three PR3 nodes back to the hand-written pattern. The decorator has remained in `lca/nodes/_decorator.py` with zero callers.

**2. PR-3.7 scope (plan / intervene / delegate) cannot land without three architectural decisions.** The investigation report surfaced three subgraphs the user wants next, each of which changes a layer boundary, a SSOT, or the capability model — all triggers for AGENTS.md §1 ("先提交 ADR/Note 草案"):

- **`plan.compose` / `plan.revise` subgraph.** A first-class `TaskList` store with re-ranking and replan semantics. Today plan lives implicitly inside `Decision.action_type` (`use_tool` / `respond` / `ask_user`). Without an explicit store, multi-hop BabyAGI / AutoGPT-style planning has nowhere to write. The store is the new SSOT for "what is the agent trying to do" between turns.
- **`intervene.interrupt` / `intervene.resume` subgraph.** A typed pause primitive with `Command(resume=…)` port. Today HITL borrows `decision.action_type == "ask_user"` and the implicit loop driver re-ask path. Without an explicit interrupt primitive, LangGraph-style time-travel, AutoGen handoff-to-user, and Hermes `_interrupt_requested` are all grafted onto the same path — which is what makes today's HITL untyped and untestable.
- **`delegate.compose` / `delegate.await` / `delegate.fold` subgraph.** A typed fan-out to sub-agents with `DelegationRequest` / `DelegationReceipt` ports. Today `AGENT_FANOUT` and `AGENT_CONSULT` strategies are registered (`lca/framework/graph/strategies/agent_consult_strategy.py`, `agent_fanout_strategy.py`) but no typed subgraph uses them. Without typed ports, multi-agent composition has no contract surface.

**3. The user-stated scope continues to grow.** Across the session, the user has added: "节点逻辑写在 lca/nodes 下", "节点单一职责 / 可替换 / 一切图化 / 一切插件化", "图节点干掉了 不用了". The cumulative demand is a single architecture where every new capability is a typed node in a subgraph, where the kernel learns nothing new, where the only forward pattern is hand-written `@plugin(...)` carriers. `@graph_node` was an attempt to abstract that pattern; it failed at the cordis seam. Rather than fix the decorator, retire it: the hand-written pattern is the single canonical shape, and ADRs should not pin a tool that no caller uses.

This ADR retires ADR-0227 and establishes the architectural foundation for PR-3.7. It does **not** implement PR-3.7 — code lands only after this ADR is Accepted.

## Decision

### Decision 1 — Retire `@graph_node`

ADR-0227 is Superseded. `lca/nodes/_decorator.py` is deleted in the same PR that lands this ADR. Any docstring reference to `@graph_node` is rewritten to point at the hand-written `@plugin(...)` carrier pattern (the canonical shape, see Decision 2). The three PR3 think nodes (`history/assemble.py`, `dispatch/llm.py`, `decision/parse.py`) keep their `@plugin(...)` shape from `daee237b6` and are not touched again.

### Decision 2 — Canonical node shape (replaces ADR-0227 §Decision §1)

Every node in `lca/nodes/<region>/<sub-group>/<node>.py` is a hand-written `@dataclass(frozen=True, slots=True)` + `@plugin(...)` carrier, mirroring `lca/nodes/think/route/{shortcut,route,decide}.py`. The shape:

```python
@dataclass(frozen=True, slots=True)
class XExecutor:
    semantic_name: str = "<region>.<sub-group>.<node>"
    region: str = "<region>"
    declared_inputs: tuple[PortName, ...] = (...)
    declared_outputs: tuple[PortName, ...] = (...)

    async def node_execute(self, context: NodeContext, input: NodeInput) -> NodeOutput: ...

@plugin(
    id="phase.<region>.<sub-group>.<node>",
    provides=("<region>::<sub-group>.<node>",),
    requires=("...",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="...",
    contract=PluginContract(...),
    ownership=OwnershipDeclaration(...),
)
async def setup(ctx: PluginContext, config=None) -> None:
    ctx.provide("<region>::<sub-group>.<node>", XExecutor())
```

Two carve-outs from the canonical shape (matches the patterns already in `lca/nodes/`):

- **Multi-node sub-groups** (e.g. `lca/nodes/think/reason/{plan,render}.py`): each `<node>.py` carries its own executor + setup; the sub-group `__init__.py` re-exports both. The kernel does not need a sub-group shell.
- **`loop/` outer-loop executors** (`lca/nodes/loop/{agent,aggregator,topology,registry}/plugin.py`): these are `NodeType.AGENT` executors, not six-phase primitives, and live alongside `think/` etc. as siblings per `lca/nodes/README.md` rule 3.

### Decision 3 — Plan store: new `TaskList` typed SSOT

Add a `TaskList` Pydantic model to `lca/contracts/models/cognition/task.py` (or wherever the structured-cognition models live — verify before writing). Shape:

```python
class TaskEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    task_id: TaskId           # stable across revisions
    objective: str
    status: Literal["pending", "in_progress", "blocked", "completed", "skipped"]
    depends_on: tuple[TaskId, ...] = ()
    revision: int = 0         # monotonic; mutations bump it
    created_at_turn: int
    completed_at_turn: int | None = None

class TaskList(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    entries: tuple[TaskEntry, ...] = ()
    revision: int = 0
```

The store is owned by `AgentState` (one field, frozen-replaced via reducer). `plan.compose` reads `state.task_list` and emits a new `TaskList` typed port. `plan.revise` reads `state.task_list` plus `Reflection.replan_requested` and emits a revised list. The graph does not loop on plan: the runtime kernel reads `TaskList.entries` for the next turn and treats them as ready-to-execute. No `RoutingDecision.next_node == "plan.compose"` short-circuit; plan is always entered at the start of each turn via the outer `phase_main.yaml` topology.

This decision satisfies AGENTS.md §1 by treating plan as an owned state field (reducer writes, plan nodes read), not a side channel. The four-eyes problem (Brain producing plan, Body executing, both writing the same list) is prevented by the reducer-single-write rule.

### Decision 4 — Interrupt primitive: new `Command` typed port

Add a `Command` Pydantic model to `lca/contracts/protocols/graph/command.py`:

```python
class Command(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["resume", "approve", "reject", "redirect"]
    payload: dict[str, Any] | None = None
    issued_by: str            # "user" | "policy" | "system"
    issued_at_seq: int        # spine sequence number at issue time
```

The `intervene.interrupt` node reads a `decision` port and emits a `Command(kind="approve"|"reject")` plus a `RoutingDecision.should_terminate=True`. The kernel sees `should_terminate` and pauses, persisting the `Command` to the spine. On resume, `intervene.resume` reads the persisted `Command` from the kernel-wide port registry (the spine re-projects it as a typed port after recovery) and re-feeds it into `think` as a typed input. No more "ask_user" path through `decision.action_type`.

This decision satisfies AGENTS.md §3 C7 (control/observation separation): `Command` is a control-plane artifact (changes which node executes next), but every emission lands in the journal as a `SessionEvent` first (observation), and the kernel reads from the journal projection, not from a parallel channel.

### Decision 5 — Delegation graph: new typed sub-edges

The existing `AGENT_FANOUT` and `AGENT_CONSULT` strategies remain; they get a typed-port contract. New typed ports in `lca/contracts/protocols/graph/delegation.py`:

```python
class DelegationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    delegate_to: str          # semantic_name of the target agent (or "*")
    payload: dict[str, Any]
    timeout_ms: int
    idempotency_key: str | None = None

class DelegationReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    delegate_from: str
    status: Literal["ok", "error", "timeout", "cancelled"]
    payload: dict[str, Any] | None = None
    error: str | None = None
```

`delegate.compose` reads a `Decision` port and emits a tuple of `DelegationRequest`. The runtime kernel runs them via the existing `AGENT_FANOUT` strategy. `delegate.await` blocks until the kernel signals all children returned; emits a tuple of `DelegationReceipt`. `delegate.fold` reads the receipts and emits a typed `FoldedDelegationResult` plus an updated `Decision`.

This decision satisfies AGENTS.md §3 C5 (capability monotonicity): `delegate.compose` requires a `delegate` capability grant on the parent, the sub-agent's grant is a strict subset of the parent's, and the kernel rejects otherwise. `idempotency_key` on `DelegationRequest` makes retry safe (C9 idempotency).

### Decision 6 — Subgraph placement

The three new subgraphs land at:

- `lca/nodes/plan/{compose,revise}/<node>.py` (region=`plan`, NOT a six-phase region — this is a new seam that lives in the contract `plan` namespace)
- `lca/nodes/intervene/{interrupt,resume}/<node>.py` (region=`intervene`, same caveat)
- `lca/nodes/delegate/{compose,await,fold}/<node>.py` (region=`delegate`, same caveat)

`plan`, `intervene`, and `delegate` are **not** added to the six-phase closed set. They are cross-phase subgraphs invoked from the outer `phase_main.yaml` topology (similar to how `loop/` sits beside `think/`). AGENTS.md §3 C1 closed-set integrity is preserved: the six-phase set stays `{perceive, think, act, remember, reflect, stop}`. Adding a new region directory does not add a phase.

### Decision 7 — PR sequencing

PR-3.7 lands in three sub-PRs, each gated by this ADR:

| Sub-PR | Scope | Pre-conditions |
|---|---|---|
| PR-3.7.a | Retire `@graph_node` (delete `lca/nodes/_decorator.py`); rewrite docstring references; bump ADR-0227 → Superseded | This ADR Accepted |
| PR-3.7.b | `plan.compose` + `plan.revise` subgraphs + `TaskList` contract + `AgentState.task_list` reducer field | PR-3.7.a merged |
| PR-3.7.c | `intervene.interrupt` + `intervene.resume` + `Command` port; `delegate.compose` + `delegate.await` + `delegate.fold` + `DelegationRequest`/`DelegationReceipt` ports | PR-3.7.b merged; sub-agent capability monotonicity check landed in kernel (separate ADR if not already) |

Each sub-PR writes tests that pin the typed-port contract (parallel to the 5 `tests/think/test_route_decide_phase_plugin.py` tests for PR-3.6). Each sub-PR updates `bundles/outer/phase_main.yaml` to invoke the new subgraphs.

## Consequences

- `@graph_node` decorator code is deleted; no caller is broken (zero callers existed). Docstring references in `lca/nodes/think/{history/assemble,dispatch/llm,decision/parse}.py` are rewritten to point at the hand-written pattern.
- Plan becomes a first-class state field with a typed contract. Brain can read it; Body cannot write it. Multi-hop planning becomes possible without parallel state channels.
- HITL becomes a typed pause primitive. Resume is reproducible from journal alone. Time-travel debugging becomes possible.
- Multi-agent composition gets typed ports. Capability monotonicity is enforced at the kernel boundary, not the implementation boundary. Sub-agent retry is safe via `idempotency_key`.
- Three new region directories (`plan/`, `intervene/`, `delegate/`) appear alongside the six phases. README must be updated to explain the distinction (region vs phase).
- The outer `phase_main.yaml` becomes longer as it grows to invoke the three new subgraphs. The kernel does not change.

## Alternatives considered

- **Fix `@graph_node` to produce a module-level `setup`.** Rejected: this requires either (a) runtime inspection of the carrier to expose `setup.setup` as `setup`, or (b) runtime changes to the bundle resolver to look up `setup.setup` when `setup` is itself a carrier. Both are inward-facing changes that hide the cordis seam behind a wrapper. The hand-written pattern is already simpler, more inspectable, and used by every existing node. There is no caller to migrate.
- **Plan store as an in-memory `dict` on `Brain`, not on `AgentState`.** Rejected: violates AGENTS.md §3 C4 (reducer single write). Plan can be queried by Body or Reflection; if it lives on Brain, those queries are untyped and bypass the reducer.
- **`Command` as an `enum` plus `dict` payload, not a Pydantic model.** Rejected: typed boundary contract is the point. `dict[str, Any]` is `extra="forbid"`-able in the wrapper, but the keys are unchecked. A Pydantic model gives shape; an enum-plus-dict is just a runtime check.
- **Single ADR for all three subgraphs.** Rejected: the three concerns touch different layer boundaries. Plan store changes `AgentState` shape; interrupt changes the kernel's pause/resume contract; delegation changes capability monotonicity at the kernel boundary. Splitting the implementation PRs also lets each one land and stabilize independently.
- **Three separate ADRs (one per subgraph).** Rejected: the architectural decision is "we have a typed-node pattern, three new subgraphs need it"; splitting forces three reviews of the same preamble. One ADR with sub-PR sequencing is the minimal bureaucratic surface.

## Cross-references

- AGENTS.md §3 C1 (cognitive closed set): preserved (six phases unchanged).
- AGENTS.md §3 C4 (reducer single write): satisfied by Decision 3 (plan lives on `AgentState`).
- AGENTS.md §3 C5 (capability monotonic): satisfied by Decision 5 (delegation grant subset-of-parent).
- AGENTS.md §3 C7 (control/observation separation): satisfied by Decision 4 (`Command` is journal-first).
- AGENTS.md §3 C9 (idempotency): satisfied by Decision 5 (`idempotency_key` on `DelegationRequest`).
- AGENTS.md §3 C11 (event closed set): satisfied — no new EP names; `Command.resume` lands as a typed port, not a new spine EP.
- ADR-0227 (typed-boundary `@graph_node` decorator): Superseded by this ADR.
- ADR-0191 / 0194 / 0196 (session and journal convergence): compatible — plan store and Command both land in journal.
- ADR-0230 (stop-decision-retirement): compatible — `Command(resume)` is the typed replacement for the legacy stop-decision pause path.

## Lifecycle

- **Proposed** when this file is committed.
- **Accepted** after review by the user.
- **Implemented** as PR-3.7.a + PR-3.7.b + PR-3.7.c, each gated by `Status: Accepted`.
