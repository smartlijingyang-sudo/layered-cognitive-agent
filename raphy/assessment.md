# Raphy Assessment — 2026-10-21 night (08:53 round)

Branch: `raphy/arch-20261021-0853` (from main `eab08cb4c`).

Scope rule: YAGNI over the last ~40 commits. Since the 05:45 assess
(`6364afe40` → merged as `eab08cb4c` with RA-177~180), the only changes are
the four RA implementations plus two cosmetic refactors (0983f038e
mcp_transport `+=` loop, c1352772a runtime_binding_validator extras_section).
The 05:45 round already friction-walked resume-bundle, the file-store delete
seam, and the preset repository, so this round picks fresh hot areas adjacent
to the landed work:

- **RunTerminalCoordinator post-RA-178** (the pause-fact capture seam landed cleanly)
- **File store read surface post-RA-176/179** (trash-state uniformity just fixed)
- **mcp_transport.py** (freshly refactored tool-result accumulation — the adjacent adapter seam)
- **runtime_binding_validator.py** (`MissingBindingError` extras refactor)

Read CONTEXT.md (domain glossary) first. 禁区 respected: ralph Round 2
(ingest/DecisionGates/ContextFiles shims), lca-1000 migration,
`gate_chain_strategy.py`, `computer/guest/preamble.py` untouched. No ADR
re-litigation. No `raphy/hidden_files/runtime-findings-*` files exist (checked).

## Phase 1 — Explore

Read end-to-end (not grep):

- `lca/plugins/transport/webserver/handlers/runs/terminal/lifecycle.py` (294 lines) — full read
- `lca/infrastructure/file/store.py` (422 lines) — full read
- `lca/contracts/models/core/workspace/file_record.py` (110 lines) — full read
- `lca/infrastructure/transport/mcp_transport.py` (147 lines) — full read
- `lca/harness/profile/validate/runtime_binding_validator.py` — full read
- `lca/infrastructure/file/registry.py` (backfill section) — read
- `lca/plugins/transport/webserver/bootstrap/bootstrap.py` (artifact-closure section) — read

### Area A: RunTerminalCoordinator post-RA-178

- Q1 (bounce): the outcome-translation seam holds — `apply_driver_outcome` /
  `apply_resume_outcome` both delegate pause-fact capture to
  `_capture_defer_pause_facts` (RA-178). No sprawl.
- Q2 (shallow): `resolve_live_terminal_hint_dto` (5 lines) is thin but a
  one-use DTO adapter at a real seam; deletion test fails it. Not a story.
  `_capture_loaded_namespaces` / `_capture_namespace_approval` share the
  identical lazy-import ritual
  (`from lca.infrastructure.tool_defer.session import current_defer_session`);
  "two = real" but the seam is ~3 lines each — recorded, not written (below).
- Q3 (pure functions / locality): the RA-178 convergence is complete; both
  pause paths call the seam. No third fact pending.
- Q4 (leaky seams): terminalize()'s finally choreography (registry clear,
  conversation-log append, materializer, projection persist, export disposal,
  session close) is intentionally best-effort per INV-ARCH-01/02 — not friction.
- Q5 (testability): `test_run_terminal_coordinator.py` pins both pause paths
  through the seam (RA-178 regression). Adequate.

### Area B: file store read surface post-RA-179

- Q1 (bounce): put()/get()/read_bytes()/exists()/list()/delete() are one
  coherent interface over the sidecar layout; the trash-state rule is now
  uniform (RA-179). No sprawl.
- Q2/Q4 (shallow + leaky): **two divergent "readability" vocabularies own
  the same question.** `_is_previewable` (store.py, private, UI-preview rule)
  vs `classify_readability` (contracts, ReadabilityTier). The same
  (filename, mime) input gets different answers: a `.py` file with unknown
  mime is NATIVE per contracts but *not* previewable (`.py` is absent from
  the preview extension set and the mime matches neither `image/` nor
  `text/`). And the interface is missing the seam entirely:
  bootstrap.py:148 imports the *private* `_is_previewable` across the seam
  to build the artifact-closure "previewable" flag — "the interface is the
  test surface": callers reaching past it prove the interface is wrong.
  → candidate RA-181.
- Q4 (checked, not a candidate): `put()` writes two physical copies
  (`workspace/user/{final_name}` + `{attachment_id}/blob` mirror) while
  reads pin to the mirror. Checked for an out-of-band writer of the live
  copy: sandbox harvest goes through `persist_generated_files` →
  `store.put()`; the write_file tool goes through the store; adapter.py:295's
  direct `write_bytes` targets sandbox session dirs, not `workspace/user`.
  No divergence consumer exists; `delete()` keeping the mirror is deliberate
  recoverability. Not a story — documented so future rounds don't re-suggest.
- Q5 (testability): `read_text_preview` has NO production caller — only a
  test pins its None case. A speculative interface riding the same
  readability tables; noted as context for RA-181, not its own story.
- Duplication (secondary): the dead `if False: pass` guard (RA-179 replaced
  the import with `pass` but left the guard) and two redundant function-level
  `from datetime import datetime` re-imports in `put()` are hygiene —
  recorded, not written.

### Area C: mcp_transport.py + runtime_binding_validator.py

- **MCPTransport leaks the outer HTTP client session.** `_get_mcp_session`
  manually enters the `streamablehttp_client` context manager
  (`await streamablehttp_client(url).__aenter__()`) but caches only the inner
  `ClientSession`; `close()` exits only the ClientSession — the outer cm's
  `__aexit__` is never invoked, leaking one HTTP client per server URL. The
  adapter owns acquisition but not the full lifetime it created.
  → candidate RA-182.
- `send_task`'s text join drops non-text (image/binary) MCP result content
  silently — recorded as Speculative; no evidence of production MCP binary
  results; the FileStore is the natural sink if it ever matters. Not written.
- runtime_binding_validator.py: `validate()` and `allows_test_defaults()`
  both build the projection via `reuse_or_build` — normal shared-seam use,
  not a twin. The extras_section list-comprehension refactor (c1352772a) is
  local and clean. No candidate.

### Runtime verification (mandatory)

- Clean worktree at main tip, MockLLMAdapter, LLM_API_KEY=<redacted>:
  `agent.run("smoke")` x2 on one Agent → RUN1: completed | RUN2: completed.
  (a) and (c) pass.
- (b) tool-call flow: `tests/scenario/browser/test_browser_preview_and_takeover_e2e.py`
  → 1 passed in 1.76s.
- No crash/hang/silent-failure in core flows.

### Duplication scan (secondary, not primary)

- store.py: dead `if False: pass` + two redundant datetime re-imports (hygiene).
- lifecycle.py: `apply_driver`/`apply_resume` method aliases and
  `RunTerminalizer`/`RunOutcomeApplier` class aliases — backward-compat
  surface, not a story.
- mcp_transport: the two Observation constructions in `send_task` differ
  (success vs error) — not twins.
- No duplication candidate written this round (quota satisfied by friction findings).

## Phase 2 — Self-grilling

### RA-181: Converge the twin readability vocabularies onto one contracts seam

- **Constraints**: `StoredFile.previewable` is a public DTO field
  (gateway/tests consume it); the artifact-closure payload's "previewable"
  flag is UI-consumed. `FileRecord.readability` (ReadabilityTier) is
  registry state. Wire shapes must not change — only rule ownership moves.
- **Dependencies**: `_is_previewable` callers: `put()`
  (StoredFile.previewable), bootstrap.py:148,172 (artifact closure).
  `classify_readability` callers: `put()` (FileRecord.readability),
  registry.py:175 (backfill). `read_text_preview` callers: none in
  production (test only).
- **Shape of the deepened module**: contracts owns the rules once — extend
  the readability seam to answer per-audience (tier + `ui_preview: bool`),
  with `read_text_preview`'s HTML/XML exclusion deriving from the same
  tables. Delete `_is_previewable`; re-source bootstrap onto the public
  seam; the interface stops being bypassed.
- **Test survival**: `tests/contracts/test_file_record_contract.py` pins
  `classify_readability` (4 asserts — the reconciliation must keep them
  green or re-source them with the implementer's verdict);
  `tests/scenario/file/test_file_store_and_write_tool.py:70` pins a
  `read_text_preview` None case; tests pinning `previewable` behavior must
  be grepped before touching.
- **Deletion test verdict**: concentrates. Deleting `_is_previewable` and
  unifying the extension/mime tables in contracts removes a real divergence
  class (a new mime/extension currently needs up to two updates) and kills
  the cross-seam private import. → **Worth exploring** (the two tables
  genuinely encode different audiences — UI preview vs readability tier —
  so the reconciliation shape needs a real design decision, not mechanical
  merging).

### RA-182: Own the full MCP session lifetime in MCPTransport

- **Constraints**: the MCP SDK is an optional dependency; the no-SDK path
  (NotImplementedError) and the broad-catch → failed-Observation behavior
  must stay. `send_task`'s synchronous-completion contract stays.
- **Dependencies**: `_get_mcp_session` (acquire, per server URL), `close()`
  (release). No other module touches `_sessions`.
- **Shape of the deepened module**: keep the entered context-manager
  handles (or an AsyncExitStack) per server URL alongside the
  ClientSession; `close()` exits inner then outer, clearing state even on
  partial failure. Acquisition and release owned by the same seam.
- **Test survival**: `tests/scenario/external/test_external_transports.py`
  pins protocol conformance, config resolution, and the no-SDK error — none
  pins `close()` today. The new test pins `close()` with a fake
  streamablehttp cm asserting both `__aexit__`s ran.
- **Deletion test verdict**: concentrates (lifetime ownership moves from
  scattered `__aenter__`/`__aexit__` asymmetry into one acquire/release
  seam). → **Worth exploring** (needs the SDK's cm protocol pinned in the test).

## Phase 3 — Candidate table

| Files | Problem | Solution | Benefits (locality + leverage) | Strength |
|---|---|---|---|---|
| `lca/contracts/models/core/workspace/file_record.py`, `lca/infrastructure/file/store.py` (`_is_previewable`), `lca/plugins/transport/webserver/bootstrap/bootstrap.py` | Two divergent readability vocabularies answer the same (filename, mime) question: `_is_previewable` (UI preview) vs `classify_readability` (ReadabilityTier) disagree — e.g. `.py` with unknown mime is NATIVE but not previewable. The FileStore Protocol exposes no previewability seam, so bootstrap.py imports the *private* `_is_previewable` across the seam. | Own the rules once in contracts — per-audience readability seam (tier + ui_preview); delete `_is_previewable`; re-source bootstrap onto the public seam; `read_text_preview`'s exclusion rules derive from the same tables. | Locality: "what can be shown/read of this file" answered once; the interface stops being bypassed. Leverage: RA-175 converged the origin vocabulary; readability is the same shape — a new mime/extension lands in one table, not two. | Worth exploring |
| `lca/infrastructure/transport/mcp_transport.py` (`_get_mcp_session`, `close`) | `_get_mcp_session` manually enters the `streamablehttp_client` context manager but caches only the inner ClientSession; `close()` exits only the ClientSession — the outer HTTP client's `__aexit__` never runs, leaking one HTTP client per server URL. | Keep the entered cm handles (or an AsyncExitStack) per server URL; `close()` exits inner then outer. | Locality: session lifetime owned by one seam (acquire + release together). Leverage: no slow socket/connection leak for long-lived transports; a pinned `close()` test proves it. | Worth exploring |

**Top recommendation**: do RA-181 first. It is the round's only friction-walk
finding with a demonstrated behavioral divergence (NATIVE-but-not-previewable)
plus a cross-seam private import proving the interface is missing the seam —
the RA-175 origin-vocabulary convergence is the direct precedent, and the
deletion verdict is clean. RA-182 is a real lifetime bug at the adapter seam
but narrower and SDK-protocol-dependent.

**Diversity quota**: satisfied. Both stories come from the friction walk
(shallow-module / leaky-seam findings); neither is duplication-class.

## Not written (recorded for future rounds)

- Twin lazy imports in `_capture_loaded_namespaces` / `_capture_namespace_approval`
  (lifecycle.py) — identical ~3-line `current_defer_session` ritual; "two =
  real" but the seam is too small for its own story; fold into the next
  lifecycle touch if any.
- store.py `if False: pass` dead guard + two redundant function-level
  `from datetime import datetime` re-imports in `put()` (left by RA-179) — hygiene.
- `trash_dir_for` mkdir side effect inside a "locate" helper — hygiene.
- mcp `send_task` silently drops non-text result content (text-only join) —
  Speculative; no production evidence of MCP binary results; FileStore is the
  natural sink if it ever matters.
- put() mirror/live dual-copy read pinning — checked: no out-of-band writer
  of the live copy exists (sandbox harvest and write_file go through the
  store; adapter.py:295 writes sandbox session dirs); `delete()` keeping the
  mirror is deliberate recoverability. Do not re-suggest.
