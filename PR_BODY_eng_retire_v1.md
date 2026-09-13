# eng/retire-v1-reasoner-sandbox

## Summary

- **P0** Retire graph v1 leftovers: `GraphAssembler` package export / README /
  CLI mentions / tests now fail-loud. Production entry remains
  `DeclarativeExecution` → `PlanInterpreter` (no second Runtime).
- **P1** `PromptReasoner` SRP: Cordis compose injects `llm` + template ports
  only. Role / tools arrive as boundary DTOs (`RoleSnapshot` / `ForkedTools`).
- **P2** Sandbox tools fail-loud on Profile → Bindings → ForkedTools when
  `runCommand` / `executeCode` would otherwise silently vanish.
- **P3** Fail-matrix contract tests + this walkthrough.

## Walkthrough — one tool-using run

1. **Profile** (`profiles/web-standard.yaml`) lists bundles including
   `bundles/think.yaml` + `bundles/base.yaml` (tools / sandbox seams +
   `phase.think.reasoner.compose`).
2. **CompiledRunPlan** — kernel plan compile lifts bundle graph specs
   (ADR-0217 `BundleGraphSpec`); no v0 `phase_graph` / GraphAssembler.
3. **PlanInterpreter** drives the outer phase graph six semantics
   (perceive → think → act → reflect → remember → stop) via
   `bundles/phase_main_outer.yaml` + phase subgraphs.
4. **Think / reason** — `think.reason` enters `bundles/think_reason.yaml`:
   - `think.reason.fork_tools` → `concept.tool.fork` → `ForkedTools`
   - `think.reason.plan` / `render` consume `reasoner` + `reasoner.role_profile`
   - `think.reason.complete` requires `forked_tools` (no boot empty fallback)
5. **broken_hop=None** — fork fail-loud raises before LLM call when sandbox
   bindings omit `runCommand`/`executeCode`; interpreter does not soft-skip.
6. **Tool EPs journaled** — successful fork + LLM path keeps existing spine /
   journal EP emissions on reasoner enter/exit (`reasoner_reason_start/end`)
   and tool schema publish from `ToolsService.materialize`.

### DoD#4 evidence (real run, not prose)

- Test: `tests/cognition/reasoner/test_tool_using_run_evidence.py::test_tool_using_path_fork_reasoner_sandbox_journal_broken_hop_none`
- Asserts: fork → `ForkedTools` with `runCommand`/`executeCode`; mock LLM tool
  call via `PromptReasoner.complete_turn`; sandbox execute commits
  `ToolStartedCommitted` / `ToolInvokedCommitted` + `phase.tool.call.start/end`;
  doctor `broken_hop is None`.

## Test plan

- [ ] `uv run pytest tests/harness/declarative/compile/test_subgraph_ref_validation.py tests/harness/declarative/compile/test_assembler_wraps_instrument.py tests/harness/declarative/compile/test_layer3_check.py -q` (no `LLM_API_KEY` required — compile conftest overrides K3 boot)
- [ ] `uv run pytest tests/cognition/reasoner/test_prompt_reasoner_fail_matrix.py tests/cognition/reasoner/test_tool_using_run_evidence.py tests/plugins/concept/test_tool_fork_fail_loud.py tests/concept/test_prompt_render.py tests/architecture/test_reasoner_role_profile_capability.py -q`
- [ ] `uv run pytest tests/architecture/test_handler_substitutability.py::test_declarative_execution_uses_registry_dispatch tests/runtime/test_declarative_execution_journal.py -q`

## Hard-ban checklist

- [x] No `GraphRuntime` / second Runtime
- [x] No in-graph `new PromptReasoner` / RoleProfile / tools assembly
- [x] No v1 dual path without delete-when
- [x] No `complete_turn` silent boot empty-tools fallback
- [x] No god assembly in graph nodes

## Follow-up (does not block this PR)

- **`FU-retire-v1-planinterpreter-tool-hop`** — Add a contract test where `PlanInterpreter` drives `think.reason` through real `ForkedTools` / sandbox EP (mock LLM OK). Existing `tests/integration/cutover/test_tool_call_e2e.py` only proves wiring + stub Observation and does **not** count.

