# Hermes ↔ LCA Semantic Reference

> **Status:** Living — owned by ADR-0200 Phase 0.
> **Authority:** [ADR-0200 §3 Keep / Transform / Reject](../adr/0200-hermes-product-capabilities-absorption.md) + Appendix A.
> **Gate:** No new behavior until [ADR-0187](../adr/0187-assistant-agent.md) P0→P2 lands and 0200.1+ opens.
> **Rule:** Every row in this table has an LCA anchor ADR and an action (Keep / Transform / Reject). Rows without anchors are forbidden.

## 0. Reading guide

This table is the single reference for "where does Hermes concept X land in LCA?".
When in doubt: the LCA ADR anchor wins. If a Hermes concept is not in this
table, treat it as **Reject** until a new row is added here AND cited in
ADR-0200.

The action vocabulary is locked to [ADR-0200 §3](../adr/0200-hermes-product-capabilities-absorption.md#3-决策keep--transform--reject):

- **Keep** — semantics preserved; lands in an existing LCA seam.
- **Transform** — shape changed; semantics preserved or strengthened; no 1:1 directory copy.
- **Reject** — do **NOT** introduce into LCA; any code PR landing the rejected shape fails review.

## 1. Concept mapping (full table)

| Hermes concept | LCA seam | ADR anchor | Action | Notes |
|---|---|---|---|---|
| `AIAgent` / `run_agent` facade | `RuntimeFacade` (assembly graph) | [0199](../adr/0199-hermes-inspired-cognitive-plugin-convergence.md) | Transform | No single facade class; port-style assembly |
| `conversation_loop` / `turn_*` | thin Loop SM × Spine | [0169](../adr/0169-loop-cursor-control.md), [0194](../adr/0194-cognitive-loop-architecture-convergence.md) | Transform | No 1:1 directory copy |
| `background_review` (fork) | review-fork Worker / Experiment session → Artifact | [0067](../adr/0067-spacetime-runtime-and-governed-creation.md), [0187](../adr/0187-assistant-agent.md), 0200.1 (future) | Keep | Read-only main Spine; default experiment |
| `skill_manage` | SkillAcquirer + 0067 Gate | [0048](../adr/0048-operational-skill-library.md), [0067](../adr/0067-spacetime-runtime-and-governed-creation.md) | Transform | Acquirer mandatory; no ungated write |
| `Curator` | Curator Provider (active/stale/archived) | [0187](../adr/0187-assistant-agent.md), 0200.2 (future) | Keep | Pluggable policy; default opt-in |
| `ContextEngine` (assembly/compression slot) | `ProjectionHost` / ContextAssembly Provider | [0169](../adr/0169-loop-cursor-control.md), 0200.3 (future) | Keep | Projection only; lossy summary never writes to Spine |
| `MEMORY.md` / `USER.md` | 0187 Home files | [0187](../adr/0187-assistant-agent.md) | Keep | File SSOT for assistant state |
| `MemoryProvider` (plugin) | MemoryProvider slot (Home bypass) | [0187](../adr/0187-assistant-agent.md), 0200.4 (future) | Keep | Bypass augmentation, not replacement |
| `toolsets` / `check_fn` | Capability grouping + runtime predicate Provider | [0199](../adr/0199-hermes-inspired-cognitive-plugin-convergence.md), 0200.5 (future) | Keep | Predicate = capability visibility gate |
| `cron` × skills | 0093 Routine trigger | [0093](../adr/0093-continuous-control-plane.md), 0200.6 (future) | Keep | Single control plane |
| `no_agent` (cron path) | 0093 Routine with `execution_mode=no_agent` | [0093](../adr/0093-continuous-control-plane.md), 0200.6 (future) | Keep | Light path; no LLM or fixed-script step |
| `write_approval` (default off) | 0067 Gate + default `approval=on` | [0067](../adr/0067-spacetime-runtime-and-governed-creation.md), [0200](../adr/0200-hermes-product-capabilities-absorption.md) | Transform | LCA default is stricter than Hermes |
| `plugins` (tools / hooks / ...) | Manifest / Def / Prov / Cons | [0190](../adr/adr-0190-extreme-plugin-organization.md) (local 0189), [0110](../adr/0110-plugin-contract-unification-and-naming-convergence.md), [0199](../adr/0199-hermes-inspired-cognitive-plugin-convergence.md) | Transform | Per-package Declaration; no global register |
| `platform gateway` (multi-channel) | Edge adapters (NOT kernel) | [0115](../adr/0115-kernel-transport-boundary.md), [0119](../adr/0119-webserver-as-plugin.md) | Reject (kernel-bound) | Stay in transport layer |
| `import-time registry.register` | Compile-time Manifest projection | [0110](../adr/0110-plugin-contract-unification-and-naming-convergence.md), [0199](../adr/0199-hermes-inspired-cognitive-plugin-convergence.md) | Reject | Runtime registration forbidden by [0200 §3.3](../adr/0200-hermes-product-capabilities-absorption.md) item 12 |
| `compressor` (lossy summary as history) | ContextEngine projection (lossy) | [0169](../adr/0169-loop-cursor-control.md), 0200.3 (future) | Reject-as-sole-SSOT | Projection only; Spine is truth |
| `agent-loop` special-case tool interception | Capability dispatch (uniform) | [0199](../adr/0199-hermes-inspired-cognitive-plugin-convergence.md), [0068](../adr/0068-compiled-plugin-kernel-and-unified-run-plan.md) | Reject | Breaks unified dispatch ([0200 §3.3](../adr/0200-hermes-product-capabilities-absorption.md) item 10) |
| `inspector` / Plugin Doctor (Hermes parallel script) | `lca.harness.diagnostics.doctor` (compile dry-run) | [0199 §5](../adr/0199-hermes-inspired-cognitive-plugin-convergence.md), P2 | Transform | Read-only; one pipeline |
| `Footprint Ladder` (capability tiering) | Edge-first; core-tool-last; 0190 expansion red-line | [0190](../adr/adr-0190-extreme-plugin-organization.md) | Keep | Encoding gate |
| `Prompt stability` (system frozen mid-session) | Projection / prompt assembly invariant | [0169](../adr/0169-loop-cursor-control.md) | Keep | `pre_llm_call` injects; doesn't rewrite |
| `Skills progressive disclosure` (list→view→refs) | 0048 + 0187 D11 | [0048](../adr/0048-operational-skill-library.md), [0187](../adr/0187-assistant-agent.md) | Keep | Already designed; productization follows 0187 P0 |
| `delegate_task` (subagent isolation) | Worker / sub-session + fail-closed tool inheritance | [0199](../adr/0199-hermes-inspired-cognitive-plugin-convergence.md), [0067](../adr/0067-spacetime-runtime-and-governed-creation.md) | Keep | Fresh child context; leaf-side tools blocked by policy |
| `Hooks` vs `Middleware` (observe+inject vs rewrite) | Extension bus | [0180](../adr/0180-event-mechanism-as-kernel-plugin.md), [0183](../adr/0183-event-bus-framework-ssot.md) | Keep | Hooks observe; middleware explicitly rewrites |
| `HERMES_HOME` / profile isolation | 0187 AssistantHome | [0187](../adr/0187-assistant-agent.md) | Keep | One assistant = one state root |
| `Curator never auto-deletes` (archive+ledger) | 0200.2 default opt-in (consolidate) | 0200.2 (future) | Keep + Transform | Hermes default = false → LCA default = opt-in |
| `Sync-primary loop` (ThreadPool parallelism) | LCA async / declarative phase | [0194](../adr/0194-cognitive-loop-architecture-convergence.md), [0075](../adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md) | Reject | Conflicting concurrency model ([0200 §3.3](../adr/0200-hermes-product-capabilities-absorption.md) item 9) |
| `Hard-cap MEMORY` (2.2k/1.4k char) | Configurable tier (NOT sole store) | [0187](../adr/0187-assistant-agent.md), 0200.4 (future) | Reject-as-sole-store | Always-on + on-demand recall tier ([0200 §3.3](../adr/0200-hermes-product-capabilities-absorption.md) item 11) |
| `Process-global registry` (no dispose) | Manifest / assembly lifecycle | [0110](../adr/0110-plugin-contract-unification-and-naming-convergence.md), [0190](../adr/adr-0190-extreme-plugin-organization.md), [0199](../adr/0199-hermes-inspired-cognitive-plugin-convergence.md) | Transform | Assembly owns disposal |
| `Guard ladder` / `tool·loop guards` | `GateService` / `ToolGuard` / `LoopGuard` / `Convergence` | [0197](../adr/0197-guard-stack-hermes-dsh-convergence.md), [0069](../adr/0069-agent-primitive-system-and-declarative-grammar.md) | Keep | Already Accepted in 0197; no parallel guard stack ([0200 §3.3](../adr/0200-hermes-product-capabilities-absorption.md) item 7) |
| Second CognitiveRuntime / `HermesRuntime` | kernel closed set | [0194](../adr/0194-cognitive-loop-architecture-convergence.md), [0199](../adr/0199-hermes-inspired-cognitive-plugin-convergence.md) | Reject | Forbidden by [0200 §3.3](../adr/0200-hermes-product-capabilities-absorption.md) item 1 |
| Off-line GEPA / "do it now" | `0187.2` extension point only | [0187](../adr/0187-assistant-agent.md), 0187.2 (future) | Reject | Deferred per [0200 §3.3](../adr/0200-hermes-product-capabilities-absorption.md) item 8 |

## 2. Action glossary (locks ADR-0200 §3)

| Action | Meaning | Forbidden follow-up |
|---|---|---|
| **Keep** | Semantics preserved; lands in existing LCA seam | New directory / new loop / new gateway |
| **Transform** | Shape changed; semantics preserved or strengthened | 1:1 directory copy of Hermes tree |
| **Reject** | Do NOT introduce into LCA | Code PR landing the rejected shape |

The 12-item Reject list in [ADR-0200 §3.3](../adr/0200-hermes-product-capabilities-absorption.md#33-reject明确不迁) is authoritative. Rows marked **Reject** in §1 must cite a §3.3 item or a §3.2 Transform reason. Rows marked **Keep + Transform** mark where the LCA default diverges from the Hermes default (semantics preserved, default policy strengthened).

## 3. Update protocol

When proposing a new row:

1. Open a PR editing this file.
2. The PR body must cite the LCA ADR anchor (e.g. "0199 §3.4") and the [ADR-0200 §3](../adr/0200-hermes-product-capabilities-absorption.md#3-决策keep--transform--reject) sub-clause that justifies the action.
3. The action (Keep / Transform / Reject) must align with ADR-0200 §3.1–3.3.
4. The CI gate `tests/architecture/test_0200_semantic_reference.py` (added in 0200 Phase 0 follow-up) will assert: every row has an anchor + an action from §2; no row contradicts ADR-0200 §3.3 Reject list; rows whose LCA seam lands in the kernel closed set (Spine / Loop SM / ScopeKernel / CommandEnvelope / Manifest schema) fail unless explicitly justified.
5. Hot edits that bypass this protocol fail review even when the prose reads well.

## 4. Cross-references

- [ADR-0200 §3 Keep / Transform / Reject](../adr/0200-hermes-product-capabilities-absorption.md#3-决策keep--transform--reject)
- [ADR-0200 §7 Phase 0 exit criteria](../adr/0200-hermes-product-capabilities-absorption.md#phase-0--对齐与冻结文档门禁0-行为变化)
- [ADR-0200 Appendix A](../adr/0200-hermes-product-capabilities-absorption.md#附录-a--hermes--lca-语义对照速查)
- [ADR-0199 RuntimeFacade / Doctor / PluginOrigin](../adr/0199-hermes-inspired-cognitive-plugin-convergence.md)
- [ADR-0190 Extreme plugin organization](../adr/adr-0190-extreme-plugin-organization.md) (local 0189; cited as "0189" by ADR-0200 §2.1)
- [ADR-0197 Guard Stack (Hermes + DSH convergence)](../adr/0197-guard-stack-hermes-dsh-convergence.md)
- [ADR-0194 Cognitive loop convergence](../adr/0194-cognitive-loop-architecture-convergence.md)
- [ADR-0187 AssistantAgent](../adr/0187-assistant-agent.md)
- [ADR-0183 Event bus framework SSOT](../adr/0183-event-bus-framework-ssot.md)
- [ADR-0180 Event mechanism as kernel plugin](../adr/0180-event-mechanism-as-kernel-plugin.md)
- [ADR-0169 Loop / Projection convergence](../adr/0169-loop-cursor-control.md)
- [ADR-0167 Spine SSOT](../adr/0167-spine-ssot-and-step-materialization.md)
- [ADR-0119 Webserver fully plugin-ized](../adr/0119-webserver-as-plugin.md)
- [ADR-0115 Kernel / Transport boundary](../adr/0115-kernel-transport-boundary.md)
- [ADR-0110 Plugin contract unification](../adr/0110-plugin-contract-unification-and-naming-convergence.md)
- [ADR-0093 Continuous control plane (Routines / Jobs)](../adr/0093-continuous-control-plane.md)
- [ADR-0075 Declarative phase graph & minimal trusted kernel](../adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md)
- [ADR-0069 Agent primitive system & declarative grammar](../adr/0069-agent-primitive-system-and-declarative-grammar.md)
- [ADR-0068 Compiled plugin kernel & unified run plan](../adr/0068-compiled-plugin-kernel-and-unified-run-plan.md)
- [ADR-0067 Spacetime runtime & governed creation](../adr/0067-spacetime-runtime-and-governed-creation.md)
- [ADR-0048 Operational skill library](../adr/0048-operational-skill-library.md)
