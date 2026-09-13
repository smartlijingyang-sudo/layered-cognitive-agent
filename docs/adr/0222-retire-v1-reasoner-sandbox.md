# ADR-0222 — Retire graph v1 leftovers; PromptReasoner SRP; sandbox fork fail-loud

- Status: Accepted
- Date: 2026-09-13
- Branch: `eng/retire-v1-reasoner-sandbox`
- Supersedes leftovers of: ADR-0221 P3 (GraphAssembler delete), ADR-0220 §6 N10

## Context

Production already drives `PlanInterpreter` (`lca/loop/driver.py`) on tip
`7b0ab03`. Leftover v1 surfaces remained: `GraphAssembler` package exports /
README / tests, and `phase.think.reasoner.compose` still assembled
`PromptReasoner` with `RoleProfile` + boot tools list, enabling a silent
`complete_turn` fallback to empty tools when `concept.tool.fork` failed.

## Decision

1. **P0** — `lca.harness.declarative` no longer exports `GraphAssembler` /
   `ExecutablePlan` / `MappingRestrictedScope`. Import raises `AttributeError`
   (fail-loud). delete-when ≤ this PR.
2. **P1** — `PromptReasoner` constructor = injected ports only
   (`llm`, `selector`, `template_provider`). No `role_profile` / `_tools` /
   `bind_boot_capabilities`. `complete_turn(..., tools=)` is required
   (`ForkedTools` or `Sequence[Tool]`). Compose Cordis provider wires ports
   only; `RoleSnapshot` / `ForkedTools` arrive as turn DTOs.
3. **P2** — `Profile → BindingsView → ToolsService.fork_for_run → ForkedTools`
   must surface `runCommand` / `executeCode` when sandbox is declared; missing
   → `RuntimeError`. SANDBOX plane with `sandbox=None` fails in
   `_tools_for_ref` instead of returning `[]`.
4. **P3** — Contract tests cover the fail matrix; PR body documents one
   tool-using walkthrough.

## Hard bans preserved

- No second `GraphRuntime`
- No in-graph `new PromptReasoner` / RoleProfile / tools assembly
- No `complete_turn` silent boot empty-tools fallback
- No v1 dual path without delete-when

## Consequences

- Legacy scenario tests that still call deleted `generate_thoughts` /
  `templates=` remain separately broken (pre-existing ADR-0220 debt).
- `think.reason` inner graph now forks tools via `concept.tool.fork`
  sub_spec and requires `forked_tools` on complete.
