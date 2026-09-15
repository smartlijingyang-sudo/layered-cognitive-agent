# 01 — Industry Concern → LCA Seam Mapping

> Goal: absorb **essence** of DeepSeek Harness, Hermes, OpenAI Agents SDK, LangGraph, Anthropic tool_use, ReAct / Plan-Execute, and coding-agent patterns into LCA’s closed six-phase graph + Gate⊂Think + Body→SafeExecutor→Sandbox.  
> **Do not** mint node ids from foreign product names. Prefer existing ports (`Decision`, `RoutingDecision`, `CommandEnvelope`, `EffectReceipt`, `Reflection`, spine EP) or ADR-0228-shaped seams (`plan.*`, `intervene.*`, `delegate.*`).

Legend for **LCA landing**:
- **Node** — first-class graph node / subgraph
- **Gate** — Gate⊂Think slot (advisory→hard rewrite)
- **Body/SE** — SafeExecutor / ToolGuard around execute
- **Edge** — typed Predicate on outer/subgraph edges
- **Port** — typed DTO on registry / boundary
- **Plugin** — capability bundle (guard-stack, CCP, spine), not a phase
- **Kernel** — PlanInterpreter / resume / checkpointer behavior

---

## 1. Master matrix

| # | Industry concern (essence) | Typical source family | Proposed LCA landing | Phase / plane | Existing today? | Proposed action |
|---|---|---|---|---|---|---|
| 1 | Inbox / claim work unit before step | DSH | **Plugin** continuous-control-plane + optional **Port** `claimed_work` into perceive | Control | CCP lease plugin exists; not a graph port | Keep CCP as plugin; add perceive `claim.admit` only if multi-worker |
| 2 | Pre-step waterfall (policy before model) | DSH | **Nodes** under think: budget.check → compact.maybe → history.assemble | Think / control | Partial (history.assemble); no budget/compact nodes | **Add** `think.budget.check`, `think.context.compact` before history |
| 3 | Session SSOT vs live control split | DSH | **Port** Session/journal SSOT; live cancel latch via **Kernel** + spine | Observation vs control | Fold/session path + DSH-GAP audit residues | Keep journal SSOT; **forbid** second live SSOT; cancel as control port |
| 4 | Tools: pre → guards → around-execute → post → finalize → result | DSH / Hermes | **Act chain**: validate → authorize → (approve?) → envelope → dispatch(Body/SE) → observe(+post-normalize) | Act | validate/authorize/envelope/dispatch/observe | **Add** `act.approve.gate` (HITL) + `act.result.normalize`; keep guards on SE |
| 5 | Concurrency barriers (join before next model) | DSH / LangGraph Send | **Node** `act.fanout` + `act.join` around dispatch; barrier before act→think | Act | Body ToolBatchExecutor has batch; not graph-visible | **Add** graph fanout/join ports; join emits single `receipt` |
| 6 | Approval ask (dangerous ops) | Hermes / OpenAI | **Node** `intervene.interrupt` + **Port** `Command` (ADR-0228); edge before envelope | Intervene / Think | `ask_user` action_type only | **Add** intervene subgraph; retire ask_user-as-HITL |
| 7 | Cancel + wake latch | DSH | **Kernel** cancel latch + **Port** `control.cancel`; wake resumes from checkpoint | Control | Partial runtime cancel | Expose as control port; **no** new phase |
| 8 | Compaction / request-error recovery | DSH / Hermes | **Node** `think.context.compact`; **Edge** reflect→think on compact/request_error; Gate on parse fail | Think / Reflect | Memory compaction module exists off-graph | **Add** compact node; wire recovery reasons into `routing.next_hint` |
| 9 | Think → Act → Observe loop | Hermes / ReAct | Outer edges think↔act + act→reflect | Outer | Present on `phase_main` | **Keep**; document as ReAct spine |
| 10 | Prompt assemble | Hermes / Anthropic | Think: plan → render (+ concept prompt.render sections) | Think | `think.reason.plan/render` + concept.prompt.render | **Merge** duplicate render paths into one concept graph |
| 11 | Provider failover | Hermes | **Primitive** `llm.invoke` policy (retry/failover), not a phase node | Primitive | llm.dispatch single call | **Add** failover config on primitive; optional `llm.failover` wrap node |
| 12 | Pre/post tool hooks | Hermes | **Body/SE** hooks + optional act ports `pre_hook_receipt` / `post_hook_receipt` | Act | Guards around SE | Prefer SE hooks; graph only if profile needs visibility |
| 13 | Dangerous approval | Hermes | Same as #6 + authorize dangerous deny | Act / Intervene | authorize local deny | Soft deny → interrupt; hard deny → Gate rewrite |
| 14 | Tool-loop: exact fail / same-tool fail / no-progress / per-turn caps / warn-then-halt | Hermes / OpenAI max_turns | **Gate** slots (repeat, loop-breaker, progress) + **Edge** budgets on outer loop | Think / Graph | guard-stack LoopGuardPolicy + gate order | **Keep** gates; surface caps as RoutingDecision reasons; no kitchen-sink nodes |
| 15 | Compression | Hermes / coding agents | Same as #8 `think.context.compact` | Think | Off-graph compaction.py | Promote to node before history.assemble |
| 16 | Token / cost / step budgets | Hermes / OpenAI | **Node** `think.budget.check` + act.authorize budgets | Think / Act | authorize has budgets | Unify budget SSOT port `BudgetLedger` |
| 17 | Memory flush | Hermes | **Remember** admit+write; flush-before-compact via edge remember→think.compact only if needed | Remember | remember write/fold | **Merge** fold into write; add flush policy on admit |
| 18 | Subagent isolation | Hermes / OpenAI handoff | **Subgraph** `delegate.compose/await/fold` (ADR-0228); capability monotonicity | Delegate | Team/delegation exists off this outer | Land ADR-0228 delegate; nest history via ports |
| 19 | Model → tools → handoff → final | OpenAI Agents | Outer: think → act | delegate | terminal; handoff = delegate or respond | Outer | Partial | Map handoff→`delegate.*` or `decision.action_type` closed set |
| 20 | max_turns | OpenAI | Outer loop budget (declarative edges / LoopGuard); ADR-0225: no per-node max_visits | Graph | Legacy max_iterations on stop→perceive | Keep loop budget on **edges**, not node visits |
| 21 | Input / output / tool guardrails | OpenAI | Input: perceive validate; Output: Gate + delivery; Tool: act.validate + SE | Perceive / Think / Act | Partial | Add `perceive.input.guard` only if needed; else Gate |
| 22 | Approval interruptions + resumable RunState | OpenAI / LangGraph | `intervene.interrupt/resume` + journal checkpoint / thread_id | Intervene / Kernel | Planned ADR-0228 | **Add**; resume from spine projection |
| 23 | Nest handoff history | OpenAI | Delegate fold merges child transcript into Session SSOT | Delegate / Remember | Partial team | Delegate.fold → history.assemble sees nested rows |
| 24 | Interrupt before side-effects | LangGraph | intervene **before** `act.envelope` / dispatch | Act | Missing | Edge: authorize → intervene? → envelope |
| 25 | Checkpointer / thread_id resume | LangGraph | Kernel + spine journal as checkpointer; run_id/thread as locator | Kernel | Session/journal | Do **not** add parallel checkpointer product |
| 26 | Approve / edit / reject / respond | LangGraph HITL | `Command` kinds on intervene.resume → feed think | Intervene | ask_user only | Command closed set |
| 27 | Send-per-tool parallel interrupt IDs | LangGraph | `act.fanout` emits per-call interrupt ids; join collects | Act | Missing at graph | Add only if HITL-per-tool required |
| 28 | Truncated tool JSON reject | Coding agents / Anthropic | **Node** `think.decision.repair` or Gate after parse; reject incomplete tool_calls | Think | tool_wire_block in Body | Prefer **think-side repair/reject** before act; Body keeps fail-loud |
| 29 | Schema / name repair | Coding agents | Same repair node (rename snake→camel is SE; schema fix is think) | Think / SE | SE name normalize | Split: name at SE; schema repair at think |
| 30 | Parallel fanout + join | Coding agents | `act.fanout` / `act.join` | Act | Body batch | Elevate to graph for observability |
| 31 | FS write-intent | Coding agents | act.authorize or dedicated `act.intent.fs` before envelope | Act | Partial permissions | Prefer authorize policy; node only if intent must be journaled |
| 32 | Observation normalize | ReAct / Hermes | `act.observe` + reflect `observation.build` | Act / Reflect | Both exist (dual) | **Merge** observation normalize to one concept; reflect consumes |
| 33 | Reflect / replan triggers | Plan-Execute | reflect.score → `Reflection.replan_requested` → **plan.revise** or reflect→think | Reflect / Plan | admit_recovery only | Add plan.revise (ADR-0228); recovery edge on outer |
| 34 | Stall / max-visits stop | Hermes / OpenAI | Gate progress + outer loop budget; ADR-0225 drop max_visits | Think / Graph | Loop policy | **Keep** ADR-0225; stall→RoutingDecision.should_stop |
| 35 | Idempotent resume | LangGraph / DSH | Effect gateway idempotency + interrupt resume from journal | Act / Kernel | Envelope idempotency cache | Keep; document as resume invariant |
| 36 | Control vs observation plane split | Cross-cutting | Control: RoutingDecision / Command / cancel; Observation: spine EP / RunFact | Cross | Spine + CCP | **Invariant** in acceptance: no control via naked EP |
| 37 | Telemetry timeline | Cross | loop_cursor spine derivers (narrative/graph/live_tail) | Observation | spine_default | Keep out of phase nodes |
| 38 | Anthropic tool_use stop_reason / parallel tools | Anthropic | decision.parse maps stop_reason→action_type; fanout for multi tool_use | Think / Act | parse exists | Extend parse mapping; fanout for N tools |
| 39 | Classic Plan-Execute | Classic | plan.compose at turn start; execute via act; revise on reflect | Plan | Planned ADR-0228 | Land as cross-phase subgraph, **not** 7th phase |
| 40 | Exact-fail / same-args fingerprint | Hermes / DSH | Gate `repeat` with args fingerprint (already ADR-0197) | Think | Implemented | **Keep** |

---

## 2. Mapping by LCA closed phase

### Perceive
| Absorb | Seam |
|---|---|
| Inbox/claim (multi-worker) | CCP plugin; optional `perceive.claim.admit` |
| Input guardrails | Fold into observe/fold or light `perceive.input.guard` |
| Sensor fanout | concept perceive sensor.run (lineage B) — converge into production perceive |

### Think (includes Gate)
| Absorb | Seam |
|---|---|
| Pre-step waterfall | budget.check → compact → history → llm → parse → repair? → gate |
| Prompt assemble | reason.plan/render (single concept path) |
| Provider failover | primitive llm policy |
| Guardrails / stall / repeat | Gate chain + loop.policy |
| Truncation / schema repair | `think.decision.repair` before gate |
| Compaction | `think.context.compact` |
| Shortcut | keep `think.shortcut` |

### Act (Body→SE→Sandbox only)
| Absorb | Seam |
|---|---|
| Validate / authorize / envelope / dispatch / observe | **Keep** five-step core |
| Approval before side-effect | intervene before envelope |
| Parallel tools | fanout/join around dispatch |
| Timeout / spill / dangerous | ToolGuard + authorize |
| Result normalize | strengthen `act.observe` |
| FS write-intent | authorize / intent policy |

### Reflect
| Absorb | Seam |
|---|---|
| Score / critique | keep score (+ concept critique merge) |
| Recovery / replan admit | admit_recovery + plan.revise trigger |
| No-progress semantic | feed Gate facts via Reflection ports |

### Remember
| Absorb | Seam |
|---|---|
| Admit + write | keep; merge fold |
| Memory flush before compact | policy on admit / edge ordering |

### Terminal / Stop
| Absorb | Seam |
|---|---|
| Final respond / force stop | `terminal.commit` + Gate delivery/terminal |
| max_turns exhausted | RoutingDecision.should_stop from budget |

### Cross-phase (not new phases)
| Absorb | Seam |
|---|---|
| HITL interrupt/resume | `intervene.*` |
| Plan compose/revise | `plan.*` |
| Subagent handoff | `delegate.*` |
| Telemetry | spine bundles |
| Continuous work lease | CCP plugin |

---

## 3. What must **not** become phase nodes

| Temptation | Why not |
|---|---|
| “DeepSeekInboxNode” / “HermesGuardrailNode” | Foreign product names; violate N9 closed action domains |
| Seventh phase `approve` / `compact` / `delegate` | Breaks perceive→think→act→reflect→remember→stop closed set |
| Second runtime / parallel GraphRuntime | LCA constraint: single PlanInterpreter |
| Checkpointer product alongside journal | Dual SSOT; journal is the checkpointer |
| Per-node max_visits | ADR-0225 rejected; use edge/loop budgets + Gate |
| Dumping all Hermes caps as separate nodes | Caps are Gate/policy; nodes would kitchen-sink |

---

## 4. Priority bands for planning (feeds 02)

| Band | Concerns | Rationale |
|---|---|---|
| **P0 — structural** | Dual lineage converge; recovery edge on outer; HITL interrupt; observation normalize single path | Correctness / one SSOT |
| **P1 — loop quality** | budget+compact; decision repair; act fanout/join; approve-before-envelope | Agent reliability |
| **P2 — scale-out** | plan/revise; delegate; CCP claim port; provider failover | Multi-step / multi-agent |
| **P3 — polish** | FS intent node (if needed); pre/post hook ports; telemetry-only refinements | Optional visibility |

---

## 5. First-principles placement rules (used for 02)

1. **World side-effects only under Act → Envelope → EffectGateway → Body → SafeExecutor → Sandbox.**
2. **Decision rewrite only under Gate⊂Think** (advisory≠rewrite; hard rewrite monotonic).
3. **Pause/resume is control (`Command`), recorded as observation (spine), resumed from journal.**
4. **Budgets and stalls are policies + Gate + outer edges — not new phases.**
5. **Visibility plane (ForkedTools) ≠ execution plane (ToolRegistry/SE).**
6. **Prefer merging duplicate concept paths over adding synonym nodes.**
