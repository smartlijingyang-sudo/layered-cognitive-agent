# LCA Architecture

A top-level map of how LCA shapes the agent runtime. Read this before changing anything under `lca/`, `lca_kernel/`, or `bundles/`. For navigation, see [documentation-map.md](documentation-map.md); for Cordis (the underlying runtime), see [vendor/cordis/pyproject.toml](../../vendor/cordis/pyproject.toml).

The declarative graph is the spine: every run is a graph, every graph is a typed contract, every typed contract is foldable back into a state.

## One-sentence summary

**Kernel compiles and boots; the graph interprets; the loop transacts; the session appends facts; cognition stays pure; plugins fill seams; transport only carries; observability only folds and exports.**

```text
                 ┌────────────────────────────────────────────┐
                 │  Profile / Bundle / Patch  (config SSOT)   │
                 └───────────────────┬────────────────────────┘
                                     ▼
   ┌───────────────────────────────────────────────────────────────────┐
   │  G0  lca_kernel/        — K1 Profile · K2 Plan compile · Boot     │
   │      events/            — yaml config SSOT · EnvelopeBus · fold   │
   └───────────────────────────┬───────────────────────────────────────┘
                               ▼  CompiledRunPlan
   ┌───────────────────────────────────────────────────────────────────┐
   │  G0  lca/framework/graph/  — MTK core (interpreter · traversal · │
   │                              lifter · plan_sdk · strategies ·    │
   │                              port_registry · predicate_evaluator │
   │                              · observation · recorder · adapter)  │
   └───────────────────────────┬───────────────────────────────────────┘
                               ▼
            cognition/  (zero I/O)         session/  (append-only SSOT)
                                  │
                                  ▼  *.spine.jsonl
                       Deriver plugins (pure fold)
                                  ▼
                       Exporter plugins (OTel / UI / SSE)
                                  ▲
              transport/  (trigger + wire, reads fold only)
```

Fact flow follows the four-stage chain from [ADR-0195 §2.3](../adr/0195-platform-architecture-convergence.md): `Producer → FactGateway.append → Session.append → *.spine.jsonl → Deriver → Exporter`. `journal.write` on loop / tool / LLM hot paths is retired ([architecture-overview.md](../observability/architecture-overview.md)); `FactGateway` is the single seam.

## The graph — the spine of LCA

A graph describes the run. Three nested layers describe any graph:

| Layer | Form | Lives in | Owned by |
|---|---|---|---|
| **Type contract** | `Plan` · `NodeIO` · `Binding` · `Port` · `Strategy` (Pydantic frozen, `extra="forbid"`) | `lca/contracts/protocols/graph/` | `lca/framework/graph/` |
| **Composition** | `BundleGraphSpec v2`: `nodes[]` + `edges[]` (factory→plugin_id resolution, region-tag, `sub_spec_ref`, `emit_on_enter`/`emit_on_exit`) | `bundles/**/*.yaml` | author / profile |
| **Runtime** | `PlanInterpreter` + `NodeGraphDriver` + strategy registry | `lca/framework/graph/` | framework |

### Five invariants of the graph

| ID | Invariant | Owned by |
|---|---|---|
| **G1** | One graph = one responsibility; phases and graphs are distinct layers | [ADR-0219 N7](../adr/0219-phase-graph-unification.md) |
| **G2** | Port names are the `Literal` closed-set in `contracts/.../ports.py`; typos fail at compile time | [ADR-0219 N4](../adr/0219-phase-graph-unification.md) |
| **G3** | Cross-graph transport uses the boundary typed DTOs in `contracts/models/cognition/boundary.py` (no bare dict) | [ADR-0220 N8](../adr/0220-three-tier-graph-and-boundary-typing.md) (Proposed) |
| **G4** | Node ids follow `<domain>.<object>.<detail>`; first segment comes from the closed verb set (`tool.*` / `prompt.*` / `decision.*` / `gate.*` / `effect.*` / `context.*` / `skill.*` / `memory.*` / `state.*` / `observe.*` / `spine.*` / `capability.*` / `llm.*` / `shortcut.*` / `perceive.*` / `reflect.*` / `stop.*`); forbidden words include `process` / `handle` / `manage` / `do_*` / `*_impl` / `*_helper` | [ADR-0220 N9](../adr/0220-three-tier-graph-and-boundary-typing.md) |
| **G5** | Termination signals are `Decision(action_type=respond)`, `act.observe.should_terminate`, and `AgentState.budget`. Per-node visit ceilings do not exist. | [ADR-0225](../adr/0225-drop-max-visits-graph-invariant.md) |

### Three-tier graph schema (ADR-0220, Proposed)

Once [ADR-0220](../adr/0220-three-tier-graph-and-boundary-typing.md) lands, every `bundles/` graph belongs to one of three layers:

| Tier | Prefix | Purpose | Example |
|---|---|---|---|
| **L1 primitive** | `primitive.*` | runtime primitives; smallest reusable transformation | `primitive.llm_call.yaml` · `primitive.typed_transform.yaml` |
| **L2 concept** | `concept.*` | reusable domain concepts; one concept = one capability | `concept.role_snapshot.yaml` · `concept.tool_fork.yaml` |
| **L3 agent** | `agent.*` | profile-specific orchestration; nested sub-graphs | `agent/reasoning_turn.yaml` · `agent/action_turn.yaml` |

A node in L3 nests L2 concepts through `sub_spec_ref`; an L2 concept nests L1 primitives the same way. Cross-tier boundaries flow boundary DTOs only (no shared state, no `getattr` against `AgentState`).

### BundleGraphSpec v2 — what a bundle looks like

A v2 bundle is a pure graph description ([ADR-0217](../adr/0217-bundle-graph-schema-v2.md), [nested-bundle-graph-spec.md](2026-09-10-nested-bundle-graph-spec.md)):

```yaml
# bundles/agent/reasoning_turn.yaml  (L3 example, L1/L2 omitted for brevity)
id: agent.reasoning.turn
region: agent
purpose: Render and dispatch a single reasoning turn.
nodes:
  - id: think.context.compose
    region: concept
    factory: concept.context.compose     # → resolved to a plugin by FactoryResolver
    purpose: Compose conversation context from the session log.
    inputs:  [session_log]
    outputs: [context]
  - id: think.history.assemble
    region: concept
    factory: concept.history.assemble
    purpose: Drop orphan function calls and assemble model history.
    inputs:  [context]
    outputs: [history]
    config:
      emit_on_enter:  [spine.history.assemble.start]
      emit_on_exit:   [spine.history.assemble.end]
  - id: think.llm.dispatch
    region: concept
    factory: concept.llm.dispatch
    purpose: Dispatch the prepared history to the model adapter.
    inputs:  [history]
    outputs: [stream]
  - id: think.decision.parse
    region: concept
    factory: concept.decision.parse
    purpose: Parse the model stream into a typed Decision boundary DTO.
    inputs:  [stream]
    outputs: [decision]
edges:
  - { from: think.context.compose,   to: think.history.assemble, kind: data,   when: null }
  - { from: think.history.assemble,  to: think.llm.dispatch,    kind: data,   when: null }
  - { from: think.llm.dispatch,      to: think.decision.parse,  kind: data,   when: null }
```

Four kernel-side guarantees make this safe to write:

| Guarantee | Where enforced |
|---|---|
| `factory` resolves to a registered plugin by id → region+phase → fail-loud | `FactoryResolver` in `lca/contracts/protocols/.../factory.py` |
| `sub_spec_ref` recurses with a depth limit (`MAX_SUBGRAPH_DEPTH`, default 8) and a cycle detector (PG-007) | `lca/framework/graph/strategies/subgraph_strategy.py` |
| `emit_on_enter` / `emit_on_exit` only emit names in the `EXECUTION_POINTS` whitelist | `lca/framework/graph/ep_table.py` |
| All invariants above run at boot before the kernel serves traffic | `lca_kernel/boot/plan_validation/` ([03dc0def0](https://github.com/smartlijingyang-sudo/layered-cognitive-agent/commit/03dc0def0)) |

### Interpreter × driver × strategies

The MTK separates frame, motion, and policy. The frame is the interpreter; the motion is the driver; the policy is a strategy registry.

```text
PlanInterpreter.run(plan, run_state)
   │
   ▼ for each PlanNode selected by traversal
   ▼
PlanTraversal.visit(node, run_state)         # chooses next edge via PredicateEvaluator
   │
   ▼
NodeGraphDriver.run_node(node, port_registry) # applies subgraph_strategy if sub_spec_ref
   │
   ▼
NodeExecutorStrategy.invoke(executor, port_values) → NodeOutput
   │
   ▼
NodeOutputProjector  →  PhaseResult
   │
   ▼
PlanInterpreter.record_result(phase_result)  # typed, not str-keyed
```

The interpreter never knows a business phase name; the driver never runs outer fold logic; the executor never sees an execution point ([ADR-0219 N1, N5](../adr/0219-phase-graph-unification.md)).

Strategies live under `lca/framework/graph/strategies/` and are registered by `StrategyRegistry`. The shipped set covers the loop's hot paths:

| Strategy | Purpose |
|---|---|
| `node_executor_strategy.py` | adapt a `NodeExecutor` to the interpreter frame |
| `subgraph_strategy.py` | recurse into `sub_spec_ref`, enforce depth + cycle |
| `gate_chain_strategy.py` | typed routing decisions (decision port → gate.port) |
| `transform_strategy.py` | typed transforms between port types |
| `parallel_strategy.py` | fork / join over a sub-graph |
| `observe_strategy.py` | projection-friendly observation turns |
| `terminate_strategy.py` | terminal predicates and budget checks |
| `agent_consult_strategy.py` / `agent_fanout_strategy.py` | team-coordination primitives (L3-only) |

### Ports, predicates, and the typed boundary

Ports, predicates, and the boundary DTOs together close the C13 information-bloodline invariant ([AGENTS.md §3](../AGENTS.md)).

| Surface | Form | Module |
|---|---|---|
| Port literal closed-set | `Literal[...]` union in `contracts/protocols/declarative/declarative_1/ports.py` | contracts |
| Port registry | `PortRegistry` typed by `TypedDict` / Pydantic over the literal | `lca/framework/graph/port_registry.py` |
| Port reader | reads a typed value off a port | `lca/framework/graph/port_reader.py` |
| Predicate evaluator | pure `Predicate → bool`; declarative graphs reuse it for edge `when` clauses | `lca/framework/graph/predicate_evaluator.py` |
| Boundary DTOs | frozen Pydantic models in `contracts/models/cognition/boundary.py` (`BindingsView` · `ForkedTools` · `RoleSnapshot` · `ReasonerContext` · `TemplateSelection` · `ReasonerTurnRender` · `Decision` · `EffectReceipt` · `Reflection` · `MemoryReceipt` · `StopPayload`) | contracts |

Once [ADR-0220](../adr/0220-three-tier-graph-and-boundary-typing.md) lands, boundary DTOs are the only legal carrier across tier boundaries; bare `dict` is rejected at the package contract gate.

### Plan SDK

Build plans from Python without editing YAML by hand:

- `Plan SDK` at `lca/framework/graph/plan_sdk.py` exposes a typed builder.
- `PlanReader`, `PredicateEvaluator`, `PortRegistry` together form the read side ([read PR-D3](https://github.com/smartlijingyang-sudo/layered-cognitive-agent/commit/8dc7891ab)).
- `PlanLiftError` carries `plan_id` to make runtime plan failures actionable ([read PR](https://github.com/smartlijingyang-sudo/layered-cognitive-agent/commit/447e41b20)).

The `atomic cutover to typed port graph (D4)` commit ([cc17d8f81](https://github.com/smartlijingyang-sudo/layered-cognitive-agent/commit/cc17d8f81)) makes port-name typos a compile-time error; production bundle YAMLs can no longer silently route to a missing port.

## Six-step cognition (closed set)

`perceive → think → act → reflect → remember → stop` is a closed set. Changing it requires an ADR. Gate is the deterministic tail of Think (`DecisionGate`, **not** a graph node). The graph turns this into a typed topology, not a Hook chain.

| Step | Plane | Owns | Forbidden |
|---|---|---|---|
| perceive | cognitive | sensors, context composition | writing state directly |
| think | cognitive | reasoner, gate, decision | emitting journal events |
| act | world | body, SafeExecutor, tool dispatch | bypassing `CommandEnvelope` |
| reflect | cognitive | critique, progress | writing state directly |
| remember | cognitive | memory propose/commit | writing state directly |
| stop | loop | terminal outcome, budget | recording new state |

World-side effects (`act` and the executable part of `remember`) flow through the only execution gate: `cognition → Body → SafeExecutor → Sandbox`. Anything bypassing `CommandEnvelope` raises `CapabilityGrantExceededError`.

## Six kinds of objects

Every field, object, event, or side effect belongs to exactly one class. Mis-classification breaks C4 and C13.

| Class | Owner | Write boundary |
|---|---|---|
| **Fact** (Journal · SessionEvent · Event) | Session | `Session.append` only |
| **State** (`AgentState`) | Reducer / named projection | components replace, never mutate |
| **Decision** | cognition | a candidate, not a grant |
| **Verdict** | Gate / Policy / Approval | authorizes control-plane action |
| **Effect Receipt** | Body / execution boundary | immutable append |
| **Projection** (Trace · Metrics · View) | fold / deriver | derivable, never writes back |

A single object never serves as both fact source and projection.

## Capability, control, observation

**Capability** is monotonic along three axes. `grant(child) ⊆ grant(parent)` must hold across capability, scope, and effects; the only side-effect exit is `CommandEnvelope` (frozen, not bypassable).

**Control plane** — Command · Approval · Policy · CapabilityGrant — changes system behavior. **Observation plane** — Session · Journal · Trace · Metrics · Projection — records or derives. The observation plane never triggers control-plane side effects; the control plane always leaves a traceable fact. Diagnostic commands are read-only by default.

## Five layers, one direction

```text
contracts → infrastructure → cognition → runtime → agent
                              ↓
                     application  (composition root)
```

- `contracts/` holds protocols, DTOs, enums, and closed sets. No behavior, no I/O, no `os.environ`.
- `infrastructure/` is adapters and persistence ports.
- `cognition/` is Brain · Body · Memory · Gate. Pure algorithms.
- `runtime/` is `CognitiveRuntime` and its bindings.
- `agent/` is `AgentUnit` and team scheduling.
- `application/` is the composition root. It is the only layer allowed to know concrete implementations.
- `harness/` depends only on `contracts`. It carries Session · Profile · Boot · declarative phase.
- `loop/` and `session/` depend on `contracts` + `harness`. `session/` is the append-only SSOT.
- `plugins/` fill seams via Cordis context injection. Plugin↔plugin direct import is forbidden.

`lint-imports` and `pyproject.toml` package-contract checks guard the direction. See [platform-directory-architecture.md](platform-directory-architecture.md) for per-directory responsibilities and migration state.

## Plugin extension path

```text
Protocol → Seam → Provider / Adapter → Registry → Plugin → Profile / Bundle
```

A plugin is a single `.py` file with `@plugin(...)` as its only entry. Its `effects` are declared in the Manifest; `setup()` may only call `provide` / `require` / `register` / `emit` declared in the Manifest — any undeclared call raises `UndeclaredInteractionError`. Plugins only communicate through capability keys. Credentials enter only through `Profile.from_env`; plugins never read `os.environ`.

`bundles/*.yaml:plugins:` lists plugin short ids, never paths. `./scripts/lca-ops audit-plugin-shape` enforces the shape.

## Kernel (G0) responsibilities

`lca_kernel/` compiles, boots, and owns the G0 event mechanism. It does not import transport, Starlette, run-fact appends, or anything from `lca/application/`.

| Module | Owns |
|---|---|
| `source.py` · `resolve.py` | K1 Profile resolution |
| `plan.py` | K2 Plan compilation |
| `boot.py` · `closure.py` | K3–K4 Boot and closure |
| `observability.py` | K5 Observability registry assembly |
| `lifecycle.py` · `env.py` · `hmr.py` | K6–K8 lifecycle, env whitelist, HMR watcher |
| `events/config/` | category / producer **yaml** SSOT |
| `events/bus.py` · `events/fold.py` · `events/payloads*.py` | EnvelopeBus, fold primitives |

Boot-time graph validation runs every plan-level invariant before the kernel serves traffic. Process-lifecycle env whitelists are three-layered: `BOOTSTRAP_NAMES` (override existing), `BOOTSTRAP_PREFIXES` (new), `BOOTSTRAP_FORBIDDEN` (forbidden); `LCA_PROFILE` must come from argv.

## What ships today vs what is in flight

| Status | Subject | Source of truth |
|---|---|---|
| Shipped | BundleGraphSpec v2 schema + factory→plugin resolution | [ADR-0217](../adr/0217-bundle-graph-schema-v2.md) |
| Shipped | NodeGraphDriver for v2 sub-graphs; old declarative path untouched | [ADR-0218](../adr/0218-bundle-graph-v2-subgraph-driver.md) |
| Shipped | `max_visits` removed across bundle yaml, plan traversal, boot checks, test fixtures | [ADR-0225](../adr/0225-drop-max-visits-graph-invariant.md) |
| Shipped | Boot-time validation of every plan-level graph invariant | `feat(boot): validate every plan-level graph invariant at startup` ([03dc0def0](https://github.com/smartlijingyang-sudo/layered-cognitive-agent/commit/03dc0def0)) |
| Shipped | Atomic cutover to typed port graph | `feat(graph): atomic cutover to typed port graph (D4)` ([cc17d8f81](https://github.com/smartlijingyang-sudo/layered-cognitive-agent/commit/cc17d8f81)) |
| Shipped | Kernel boot migrated into Starlette lifespan (no eager `_load_harness_profile`) | `fix(gateway): move boot into Starlette lifespan` ([274d8cced](https://github.com/smartlijingyang-sudo/layered-cognitive-agent/commit/274d8cced)) |
| Shipped | LobeHub gateway emits LCA-flavored shared event handler | `feat(lobehub-gateway): emit LCA-flavored shared event handler` ([6edc69eab](https://github.com/smartlijingyang-sudo/layered-cognitive-agent/commit/6edc69eab)) |
| Shipped | Reasoning-shortcut trigger 3 re-keyed to `consecutive_repeat_max`, decoupled from projection | `fix(loop): re-key trigger 3 to consecutive_repeat_max` ([aeae90c13](https://github.com/smartlijingyang-sudo/layered-cognitive-agent/commit/aeae90c13)) |
| Shipped | v1 reasoner/sandbox retired (`PromptReasoner` SRP, GraphAssembler reachability removed, sandbox fork fail-loud) | [ADR-0222](../adr/0222-retire-v1-reasoner-sandbox.md) |
| In flight (main) | typed `PortRegistry`, typed phase result, `think.gate` writes back `decision` slot | [ADR-0219](../adr/0219-phase-graph-unification.md) (Proposed) |
| In flight (main) | three-tier graph schema, 11 boundary DTOs, `PromptReasoner` slimmed to `render_turn` + `complete_turn`, `AgentState._xxx_ref` removed | [ADR-0220](../adr/0220-three-tier-graph-and-boundary-typing.md) (Proposed) |
| Branched (not in main) | session write-path collapse + persist-before-execute + orphan-drop via `RunSessionWriter` | [ADR-0226 (planned)](../adr/README.md) on `pr2/session-write-path` |
| Reference only | `agent_lab` / `lca/plugins/lab/` info-graph prototype — deleted from the tree; design preserved for review | [2026-09-14-agent-lab-info-graph-reference.md](../design/2026-09-14-agent-lab-info-graph-reference.md) |

The "in flight (main)" rows are Proposed ADRs; their acceptance gates are listed at the top of each ADR. Status changes only when the corresponding note moves to `implemented/`.

## Reference paths

| Need | Authority |
|---|---|
| Standing rules and quick-command entry | [AGENTS.md](../../AGENTS.md) |
| Six-class terminology (Fact / State / Decision / Verdict / Effect / Projection) | [lca-structured-cognition-guide.md](lca-structured-cognition-guide.md) |
| Phase graph + act→tool path walkthrough | [guides/phase-graph-and-act-tool-path.md](../guides/phase-graph-and-act-tool-path.md) |
| Per-directory responsibilities and migration | [platform-directory-architecture.md](platform-directory-architecture.md) |
| Spine / journal / trace / observability | [architecture-overview.md](../observability/architecture-overview.md) · [harness-spine-spec.md](harness-spine-spec.md) |
| Full-stack convergence decisions | [ADR-0194](../adr/0194-cognitive-loop-architecture-convergence.md) · [ADR-0195](../adr/0195-platform-architecture-convergence.md) |
| Kernel / transport boundary | [ADR-0115](../adr/0115-kernel-transport-boundary.md) · [ADR-0116](../adr/0116-boot-event-observability-convergence.md) · [ADR-0117](../adr/0117-process-lifecycle-env-whitelist.md) |
| Hermes-inspired plugin convergence | [ADR-0199](../adr/0199-hermes-inspired-cognitive-plugin-convergence.md) |
| `agent_lab` info-graph reference (read-only) | [2026-09-14-agent-lab-info-graph-reference.md](../design/2026-09-14-agent-lab-info-graph-reference.md) |
| Index of all decisions | [adr/README.md](../adr/README.md) |
| Debug runbook | [debug/README.md](../debug/README.md) |