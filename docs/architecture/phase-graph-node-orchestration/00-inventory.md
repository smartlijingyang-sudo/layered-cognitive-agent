# 00 — LCA Phase-Graph Inventory (from live YAML)

> Source: `gh api` reads of `smartlijingyang-sudo/layered-cognitive-agent` @ HEAD (no clone).  
> Primary production outer plan: `bundles/outer/phase_main.yaml` (wired by `profiles/web-standard.yaml`).  
> Parallel three-tier lineage: `bundles/agent/*` → `bundles/concept/*` → `bundles/primitive/*` (ADR-0220).  
> Inventory date: 2026-09-15 (Asia/Shanghai).

---

## 0. Dual lineage (must read first)

| Lineage | Entry | Status in profiles | Notes |
|---|---|---|---|
| **A. Six-phase outer (ADR-0221 cutover)** | `bundles/outer/phase_main.yaml` (`id: phase.main.outer`) | **Production** — `web-standard` lists it | Nested `bundles/{perceive,think,act,reflect,remember}/*_subgraph.yaml` |
| **B. Three-tier agent (ADR-0220)** | `bundles/agent/run_phase.yaml` (`id: agent.run.phase`) | Spec / coexisting; not the web-standard outer entry | Cleaner Layer 3→2→1; richer perceive/reason prep |
| **C. Legacy declarative edges** | `bundles/declarative-phase-graph.yaml` + `declarative-recovery.yaml` | `web-standard-recovery` still pulls both; headers say delete-when region-tag path lands | Parallel edge SSOT vs outer YAML edges |

**Clarity verdict:** Outer six-phase topology is clear; **two act stacks and two think stacks** (phase subgraph vs agent/concept) dilute “one true graph.” Recovery still straddles lineage C.

---

## 1. Outer plan — `phase.main.outer`

**File:** `bundles/outer/phase_main.yaml`  
**Purpose:** Six-phase outer plan (perceive → think → act → reflect → remember → terminal.commit).

### 1.1 Nodes

| Node id | Region | Kind | Nested plan | Entry | Declared inputs | Declared outputs | Responsibility |
|---|---|---|---|---|---|---|---|
| `perceive.main` | `phase:perceive` | `sub_spec_ref` (entry) | `bundles/perceive/perceive_subgraph.yaml` | `phase.perceive.observe` | `[]` | `in_assembled_manifest`, `observation`, `routing` | Pull + fold observation/manifest |
| `think.main` | `phase:think` | `sub_spec_ref` | `bundles/think/think_subgraph.yaml` | `think.shortcut` | `in_assembled_manifest` | `decision` | Shortcut / reason / LLM / parse / Gate⊂Think |
| `act.main` | `phase:act` | `sub_spec_ref` | `bundles/act/act_subgraph.yaml` | `act.validate` | `decision` | `decision`, `should_terminate` | Validate→authorize→envelope→dispatch→observe |
| `reflect.main` | `phase:reflect` | `sub_spec_ref` | `bundles/reflect/reflect_subgraph.yaml` | `phase.reflect.score` | (registry: `observation`) | `reflection`, `routing` | Score + recovery admit |
| `remember.main` | `phase:remember` | `sub_spec_ref` | `bundles/remember/remember_subgraph.yaml` | `phase.remember.write` | `decision`, `observation`, `reflection` | `memory_receipt` | Memory write + fold |
| `terminal.commit` | `phase:terminal` | `binding: terminate` | — | — | `decision`, `reflection` | `terminal_outcome` | Close loop / emit terminal |

### 1.2 Edges (control)

| From | To | Predicate |
|---|---|---|
| `perceive.main` | `think.main` | always |
| `think.main` | `act.main` | `decision.action_type == use_tool` |
| `think.main` | `terminal.commit` | `action_type == respond` ∧ `response_text ≠ ""` |
| `act.main` | `think.main` | `decision.action_type == use_tool` (re-ask model) |
| `act.main` | `terminal.commit` | `should_terminate == true` |
| `act.main` | `reflect.main` | always (after act path continues) |
| `reflect.main` | `remember.main` | always |
| `remember.main` | `terminal.commit` | always |

**Granularity / clarity notes**

- Closed set honored: no seventh phase; terminal is binding, not a phase.
- Tool re-ask loop is outer edge `act→think`, not nested act loop — good first principle.
- Edge set on outer does **not** include error→stop / recovery→think (those live in lineage C or reflect routing only).
- Guide still mentions `stop.main`; outer YAML uses `terminal.commit` — naming drift.

---

## 2. Perceive subgraph

**File:** `bundles/perceive/perceive_subgraph.yaml` (`id: perceive.subgraph`)

| Node | Factory | In | Out | Duty |
|---|---|---|---|---|
| `phase.perceive.observe` | `phase.perceive.observe` | — | `manifest`, `routing` | PerceiveHub → raw manifest |
| `phase.perceive.fold` | `phase.perceive.fold` | `manifest` | `in_assembled_manifest`, `observation` | Project closed observation + think input |

**Edges:** observe → fold (terminal).

**Assessment:** Clear 2-step; coarse vs concept perceive (4 nodes: collect→sensor→fold→compose). Missing explicit inbox/claim, sensor parallel fanout at graph level.

---

## 3. Think subgraph (+ reason inner)

**File:** `bundles/think/think_subgraph.yaml` (`id: think.subgraph`)

| Node | Factory / ref | In | Out | Duty |
|---|---|---|---|---|
| `think.shortcut` | `think.shortcut` | `in_assembled_manifest` | `decision` | Deterministic short-circuit |
| `think.route.decide` | `think.route.decide` | `decision` | `routing` | Emit `RoutingDecision.next_node` |
| `think.route` | `think.route` | — | — | Continue to full reason path |
| `think.reason` | `sub_spec_ref` → `think_reason.yaml` | `in_assembled_manifest` | `response` | Fork tools + plan + render |
| `think.history.assemble` | ref → `concept/history_assemble.yaml` | `response`, `state` | `model_visible_request` | Orphan-drop ModelVisibleRequest |
| `think.llm.dispatch` | ref → `concept/llm_dispatch.yaml` | `state`, `writer`, `model_visible_request` | `llm_response`, `usage` | Persist-before-execute LLM |
| `think.decision.parse` | ref → `concept/decision_parse.yaml` | `state`, `llm_response` | `decision` | LLMResponse → Decision |
| `think.gate` | ref → `concept/decision_enforce.yaml` | `decision` | `decision`, `routing` | Gate⊂Think enforce + reject stamp |

**Inner `think.reason` (`bundles/think_reason.yaml`)**

| Node | Duty |
|---|---|
| `think.reason.fork_tools` → `concept/tool_fork.yaml` | Materialize `ForkedTools` (visibility plane, not execute) |
| `think.reason.plan` | Turn plan |
| `think.reason.render` | Prompt render; emit `prompt_assembler_end` / `reasoner_meta` |

**Gate inner (`concept/decision_enforce.yaml`)**

| Node | Duty |
|---|---|
| `gate.chain.run` | Gate chain rewrite → `enforced_decision` |
| `gate.chain.reject` | Stamp rejection provenance + `routing` |

**Assessment:** Think is the densest, generally well-factored (shortcut → route → reason → history → llm → parse → gate). Gaps: no explicit compact/budget before history; no provider-failover node; no schema/name repair after parse; `think.route` is thin vs `route.decide`; agent.reasoning.turn has richer prep (role/context/template) not mirrored here.

---

## 4. Act subgraph

**File:** `bundles/act/act_subgraph.yaml` (`id: act.subgraph`, region: `concept`)

| Node | Factory | In | Out | Duty |
|---|---|---|---|---|
| `act.validate` | `act.validate` | `decision` | `decision` | Shape: action_type closed set; tool_calls / delegations |
| `act.authorize` | `act.authorize` | `decision` | `decision` | Budget, call_id uniqueness, dangerous tool local deny |
| `act.envelope` | `act.envelope` | `decision` | `envelope` | Mint `CommandEnvelope` (`operation=body.act`) |
| `act.dispatch` | ref → `concept/effect/effect_execute.yaml` | `envelope` | `receipt` | Effect gateway only side-effect entry |
| `act.observe` | `act.observe` | `receipt` | `receipt`, `should_terminate` | Normalize receipt; RunFact; EP end |

**Effect leaf:** `effect.execute` — `CommandEnvelope` → `EffectReceipt` via `RegistryEffectDispatcher` → Body → SafeExecutor → Sandbox.

**Assessment:** Excellent Body→SafeExecutor→Sandbox discipline. Missing at graph: pre-tool hooks / post-tool hooks as ports; parallel fanout+join; truncated JSON reject as explicit node; HITL approval before envelope; FS write-intent gate as first-class step (today inside authorize/SafeExecutor).

**Parallel lineage B act:** `concept.action.turn` = resolve → capability.grant → effect.execute (no validate/authorize/envelope/observe names) — **semantic overlap, different node vocabulary**.

---

## 5. Reflect / Remember / Terminal

### Reflect — `bundles/reflect/reflect_subgraph.yaml`

| Node | Duty |
|---|---|
| `phase.reflect.score` | Observation → Reflection |
| `phase.reflect.admit_recovery` | Set `routing.next_hint` for recovery |

### Remember — `bundles/remember/remember_subgraph.yaml`

| Node | Duty |
|---|---|
| `phase.remember.write` | Mint memory envelope + dispatch |
| `phase.remember.fold` | Forward `memory_receipt` |

### Also on disk (legacy/compat)

| File | Notes |
|---|---|
| `bundles/reflect-subgraph.yaml` | Older sibling naming; not outer entry |

**Assessment:** Reflect recovery admit is clear but **outer `phase_main` has no reflect→think edge**; recovery depends on lineage C plugin. Remember fold is thin (possible merge). No explicit memory-flush-before-compact, no replan trigger port beyond reflection fields.

---

## 6. Lineage B — Agent / Concept / Primitive (ADR-0220)

### 6.1 Layer 3 — `bundles/agent/`

| Bundle id | Nodes (refs) | Boundary out |
|---|---|---|
| `agent.run.phase` | `perceive.turn` → `reason.turn` → `act.turn` → `reflect.turn` → `remember.turn` → `terminal.commit` | `terminal_outcome` |
| `agent.perceive.turn` | `perceive.manifest.compose` → concept.perceive.turn | `manifest` |
| `agent.reasoning.turn` | prepare.{tools,role,context,template} → render.prompt → llm.call → classify → gate | `decision` |
| `agent.reasoning.shortcut` | `shortcut.try` | Decision \| None |
| `agent.action.turn` | `act.effect.execute` → concept.action.turn | `receipt` |
| `agent.reflection.turn` | `reflect.critique.run` | `reflection` |
| `agent.memory.turn` | `memory.write.dispatch` | `memory_receipt` |

**Note:** `agent.run.phase` edges are linear (no think↔act re-ask); termination post-retirement uses `decision.action_type` + Body errors + `terminal.commit`. Different control shape than outer `phase_main`.

### 6.2 Layer 2 — `bundles/concept/` (node counts)

| Concept graph | Nodes | Purpose |
|---|---|---|
| `concept.perceive.turn` | input.collect → sensor.run → observation.fold → manifest.compose | 4-step perceive |
| `concept.tool.fork` | `tool.fork.dispatch` | ForkedTools |
| `concept.role.snapshot` | role.normalize → role.compose | RoleSnapshot |
| `concept.context.compose` | lines.collect → skills.merge | ReasonerContext |
| `concept.template.select` | enumerate → score → pick | TemplateSelection |
| `concept.prompt.render` | sections.assemble → fill → trace.compile | ReasonerTurnRender |
| `concept.history.assemble` | `history.derive` | ModelVisibleRequest |
| `concept.llm.dispatch` | `llm.call` | LLMResponse + usage |
| `concept.decision.parse` | `decision.parse` | Decision |
| `concept.decision.classify` | parse.response → compose.action | Decision (alt parse path) |
| `concept.decision.shortcut_try` | `shortcut.try` | shortcut |
| `concept.decision.enforce` | gate.chain.run → reject | enforced Decision |
| `concept.action.turn` | action.resolve → capability.grant → effect.execute | Decision→Receipt |
| `concept.effect.execute` | `effect.execute` | Envelope→Receipt |
| `concept.reflection.critique` | observation.build → critique.run | Reflection |
| `concept.memory.write` | admit.policy → write.dispatch | MemoryReceipt |

### 6.3 Layer 1 — `bundles/primitive/`

| Primitive | Nodes |
|---|---|
| `primitive.llm.call` | `llm.invoke` |
| `primitive.capability.fork` | `capability.fork.dispatch` |
| `primitive.spine.emit` | event.compose → event.dispatch |
| `primitive.typed.transform` | `dto.map.apply` |

---

## 7. Guard stack / control plane / recovery / spine (not phase nodes, but seams)

### 7.1 `bundles/guard-stack.yaml` (ADR-0197)

| Entry id | Role | Plane |
|---|---|---|
| `loop.policy.default` | repeat_warn / break_failures / break_stalled / progress_* | think / graph |
| `tool.guards.service` | ToolGuardService wrap | act / SafeExecutor |
| `guard.tool-timeout` | Cooperative timeout synthetic result | act |
| `guard.tool-result-spill` | Spill large results (`max_inline_bytes: 50000`) | act |

Gate order (docs): `10 repeat → 20 loop-breaker → 30 progress → 35 delivery → 40 terminal → 50 artifact`.

### 7.2 `bundles/continuous-control-plane.yaml`

Lease DB factory (`database_path`, `lease_seconds`, `retry_delay_seconds`) — **inbox/claim analog lives here as plugin, not graph node**.

### 7.3 `bundles/declarative-phase-graph.yaml`

Resilient execution policies per phase + **legacy edge table** (perceive/think/act/reflect/remember/stop with error→stop and stop→perceive loop `max_iterations: 8`). Marked backward-compat / delete-when.

### 7.4 `bundles/declarative-recovery.yaml`

`reflect.main → think.main` when `routing.next_hint == admit_recovery`, `maxIterations: 1`.

### 7.5 Loop cursor spines

| Bundle | Role |
|---|---|
| `loop_cursor.spine_default.yaml` | Production EventSpine composition (core, emit_pipeline, source reflector, classifiers, derivers, sinks, writable matrix) |
| `loop_cursor.spine_minimal.yaml` | Minimal subset |
| `loop_cursor.spine_debug.yaml` | Debug reflectors / wraps |

Provides: `loop_cursor_factory`, `projection_host`, `persistence`, `model_visible`, `close_barrier`.

---

## 8. Clarity / completeness / granularity scorecard (as-is)

| Dimension | Perceive | Think | Act | Reflect | Remember | Outer |
|---|---|---|---|---|---|---|
| Responsibilities clear? | Yes (2-step) | Mostly yes | Yes (5-step) | Yes | Thin | Yes |
| Comprehensive vs industry loops? | Low | Medium | Medium-High | Medium | Low | Medium |
| Granularity | Coarse vs concept | Fine; some thin nodes | Fine | Coarse | Too coarse (fold) | Right |
| Dual-path risk | High (2 perceive stacks) | High (think vs agent.reasoning) | High (act vs concept.action) | Medium | Medium | High (A vs B vs C) |

**Top inventory smells**

1. **Two production-shaped graphs** (outer six-phase vs agent.run.phase) with overlapping duties, different edge semantics.
2. **Recovery edges not in outer YAML** — profile/plugin lineage C.
3. **Guide vs YAML naming** (`stop.main` vs `terminal.commit`; `phase_main_outer` vs `outer/phase_main.yaml`).
4. **Guard / compact / HITL / delegate / plan** mostly plugin or planned (ADR-0228), not yet first-class outer seams.
5. **Control plane (continuous-control) vs observation plane (spine)** correctly split as bundles, but not visible as phase-graph ports.

---

## 9. File index used for this inventory

```
bundles/outer/phase_main.yaml
bundles/perceive/perceive_subgraph.yaml
bundles/think/think_subgraph.yaml
bundles/think_reason.yaml
bundles/act/act_subgraph.yaml
bundles/reflect/reflect_subgraph.yaml
bundles/remember/remember_subgraph.yaml
bundles/agent/{run_phase,perceive_turn,reasoning_turn,reasoning_shortcut,action_turn,reflection_turn,memory_turn}.yaml
bundles/concept/{perceive_turn,tool_fork,role_snapshot,context_compose,template_select,prompt_render,
  history_assemble,llm_dispatch,decision_*,action_turn,effect/effect_execute,reflection_critique,memory_write}.yaml
bundles/primitive/{llm_call,capability_fork,spine_emit,typed_transform}.yaml
bundles/{guard-stack,continuous-control-plane,declarative-phase-graph,declarative-recovery,
  loop_cursor.spine_{default,minimal,debug},reflect-subgraph}.yaml
docs/guides/phase-graph-and-act-tool-path.md
docs/adr/{0197,0093,0219,0220,0225,0227,0228}*
profiles/web-standard.yaml, profiles/web-standard-recovery.yaml
```
