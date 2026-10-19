# Raphy Assessment — 2026-10-19 07:45 round (`raphy/arch-20261019-0745`)

Basis: main tip `f81e60679` (clean worktree; RA-147~153 merges landed in
previous rounds). 3 hot areas read end-to-end; runtime verification run in
the main worktree with `LLM_API_KEY=<redacted> (a) basic run → COMPLETED,
(b) `tests/scenario/browser/test_browser_preview_and_takeover_e2e.py`
1 passed, (c) two sequential runs → completed/completed. No crash/hang.

## Phase 1 — Explore

### Hot-spot scan (`git log --oneline -45`)

Last 45 commits are dominated by one lane: the Muse **browser 13-tool
suite** (agy + raphy RA-146~153: fabricated-result convergence, fail-closed
fixes, driver has_page gate, lazy-import boilerplate extraction). Also:
iter-tests/iter-quality hygiene, docs/plans for the stochastic brain
(targets `~/tools/x-operator`, a different repo — not a hotspot here).

Hot areas chosen for the friction walk (browser tooling is the natural
continuation — RA-146~153 converged the *tools* but the *subagent's*
fallback dispatch and the *driver's* internals were never walked):

(A) `lca/infrastructure/tools/browser/` — tools.py (1069L, read fully),
    task_store.py (176L), executor.py (106L), driver_tool.py (34L)
(B) `lca/infrastructure/browser/cdp_driver.py` (514L, read fully)
(C) `lca/infrastructure/browser/subagent.py` (225L, read fully) +
    `arbitration.py` (87L, read fully)

### Organic friction walk

#### Area A — `tools/browser/` (tools.py / task_store.py / executor.py / driver_tool.py)

1. **Bouncing between small modules?** Mild. Understanding one tool call
   crosses tool class → task_store/driver → contracts BrowserActionResult.
   The 17 classes are spec-mandated interfaces (Muse Browser Spec), so the
   per-class thinness is not sprawl — the *schema* is the interface.
2. **Shallow modules?** `BrowserNavigateTool(BrowserOpenTool)` is a pure
   alias subclass — but its interface (the spec tool name) is the value;
   deletion test passes (it earns existence via spec compatibility).
   The two fail-closed placeholder tools (spawn_task, deep_research) each
   re-implement the same warn + fail-closed Observation ritual → two = real
   (→ RA-157).
3. **Pure functions hiding call-site bugs?** No. `_normalize_url`,
   `browser_preview_widget_tag`, `_args_for`, `_result_from_observation`
   are genuine locality helpers; no call-site bug found.
4. **Leaky seams?** YES — real finding. `BrowserSteerTaskTool.execute`
   (tools.py:476-482) mutates `task.status` / `task.payment_approved`
   directly on the record; `BrowserTransferTaskTool.execute` (tools.py:~680)
   mutates `task.status` directly. Meanwhile `BrowserTaskStore.update_task`
   offers an update seam with **zero callers** (verified by grep across
   `lca/` and `tests/`; RA-152 round independently confirmed zero calls).
   The store's own mutation seam is dead while its sibling tools reach
   past it into record fields → RA-156.
5. **Testability?** The interface is the test surface: 26 tests pass
   (contracts/browser + infrastructure/browser + tools/browser), each tool
   exercised via `execute()` through the interface.
6. **Verdict**: two stories (RA-156, RA-157).

#### Area B — `infrastructure/browser/cdp_driver.py`

1. **Bouncing?** No — single module owns sessions/pages/CDP/screencast.
2. **Shallow?** `choose_chromium_proxy(env_server, *, mihomo_open)` is
   the good case: a genuine pure function taking the probe result as a
   parameter — fully testable (`test_chrome_proxy_prefers_mihomo_*`).
   `_mihomo_proxy_open` / `_chromium_proxy` are thin environment probes
   with a real decision; they earn their names.
3. **Leaky seams?** Two `BrowserSessionSummary` update-rebuilds
   (cdp_driver.py:215 in `_init_cdp_for_session`, :325 in `navigate`)
   hand-copy all 8 contract fields verbatim, differing only in the 2-3
   changed fields — and they have *already drifted*: :215 hardcodes
   `has_active_stream=True` while :325 copies `summary.has_active_stream`.
   `BrowserSessionSummary` is a frozen pydantic BaseModel, so
   `model_copy(update=...)` is the contract's own evolve seam — the driver
   hand-rolls what the contract gives for free → RA-155.
4. **`has_page` side effect?** EXAMINED AND CLEARED. `has_page()` does
   mutate (`_pages.pop` / `_cdp_sessions.pop` on closed pages), but
   `tests/infrastructure/browser/test_browser_reopen_snapshot.py:77`
   (`test_has_page_drops_a_closed_playwright_page`) *pins the reaping
   through the interface*: `assert driver.has_page("brw_dead") is False`
   + `assert "brw_dead" not in driver._pages`. Deletion test: removing the
   reaping turns this test red — the reaping concentrates behavior, it
   earns its place. The interface is the test surface and the surface
   pins the design. No story.
5. **Verdict**: one story (RA-155).

#### Area C — `infrastructure/browser/subagent.py` + `arbitration.py`

1. **Bouncing?** YES — the finding. `BrowserSubagent.execute_action`
   dispatches over `BrowserActionType` in three layers (RA-146 design):
   injected executor → `_execute_via_driver` → fail-closed. But layer 2,
   `_execute_via_driver` (subagent.py:120-225), is a ~100-line if-chain
   re-implementing dispatch over the *same* `BrowserActionType` space that
   `executor.py::_ACTION_TOOL_NAMES` already owns. The two tables diverge:
   executor covers 4 types (NAVIGATE/CLICK/SCREENSHOT/CLOSE);
   `_execute_via_driver` covers 6 (adds TYPE, EXTRACT_TEXT). A new action
   type now requires edits in two modules; TYPE/EXTRACT_TEXT silently skip
   the shared execution seam RA-146 built.
2. **Shallow?** `arbitration.py` (87L) is deep: 5-method state machine
   (IDLE/AGENT_RUNNING/HUMAN_TAKEOVER/CLOSED) with `evaluate_input`
   gating — small interface, real semantics. Deletion test passes.
   `_execute_via_driver`'s six branches are shallow *relative to the seam
   they shadow*: each branch is "try driver.X, wrap in result" — the same
   shape the tools already wrap.
3. **Leaky seams?** The `_execute_via_driver` branches call
   `self.driver.navigate/click/type_text/take_screenshot/extract_text/
   close_session` directly, bypassing the tool wrappers that
   `build_browser_action_executor` would use for the same actions —
   so NAVIGATE via subagent-driver path and NAVIGATE via tool path can
   diverge in result shaping (e.g. screenshot artifact-id generation
   happens in both places independently).
4. **Testability?** `test_browser_lifecycle_scenarios.py:296`
   (`BrowserSubagent(driver=driver)`) pins the driver-direct path;
   `test_browser_subagent_purity.py` pins the tools path. Both must stay
   green through convergence.
5. **Verdict**: one story (RA-154, top).

### Runtime verification

- (a) basic run → COMPLETED; (c) two sequential runs → completed /
  completed (mock LLM, main worktree, `LLM_API_KEY=<redacted>
- (b) `tests/scenario/browser/test_browser_preview_and_takeover_e2e.py`
  → 1 passed; browser tool + subagent + executor suites → 26 passed.
- No crash / hang / silent failure observed. No P0 runtime candidate.

### Duplication scan (secondary, after the walk)

- `_ACTION_TOOL_NAMES` (executor.py:26) vs `_execute_via_driver`
  (subagent.py:120): already captured as RA-154 — not mechanical dup,
  diverging seams.
- Two fail-closed "not implemented" rituals (spawn_task, deep_research)
  → RA-157 (vocabulary-sanctioned two = real).
- Two 8-field `BrowserSessionSummary` rebuilds → RA-155.
- `update_task` dead seam (0 callers) vs two direct-mutation sites →
  RA-156.
- No other mechanical duplication found in the walked areas worth a
  story (launch-kwargs dict appears twice in `_init_cdp_for_session`
  but the two sites configure genuinely different scenarios —
  first-launch vs relaunch; one adapter = hypothetical).

## Phase 2 — Self-grilling

### RA-154 — Converge `_execute_via_driver`'s dispatch table onto the shared executor seam

- **Constraints**: RA-146's three-layer order stays (explicit executor →
  driver-direct → fail-closed). `driver=None` + no executor → fail-closed
  behavior stays. Subagent lock + arbitration interplay untouched.
  BrowserActionType enum (contracts) untouched.
- **Dependencies**: `subagent.py` → would import
  `build_browser_action_executor` from `lca.infrastructure.tools.browser.
  executor`; executor → `build_browser_tools` (tools.py). No cycle:
  tools.py never imports subagent. Callers pinning paths:
  `test_browser_lifecycle_scenarios.py:296` (driver-direct),
  `test_browser_subagent_purity.py` (tools),
  `test_browser_action_executor.py` (executor map).
- **Shape of the deepened module**: `_ACTION_TOOL_NAMES` extended to
  TYPE + EXTRACT_TEXT, backed by driver methods (either minimal Tool
  adapters in driver_tool.py's 同类家园 or direct adapters in
  executor.py — implementer's call); `_execute_via_driver` becomes a
  one-liner delegating to `build_browser_action_executor(driver=self.
  driver)`. One dispatch table for "BrowserAction → how it executes".
- **Test survival**: the three test files above stay green; new test:
  driver-only subagent dispatches TYPE/EXTRACT_TEXT and the results come
  back through the executor path (not the private if-chain).
- **Deletion test verdict**: deleting `_execute_via_driver`'s branches
  concentrates dispatch into the map — CONCENTRATES. Strong.

### RA-155 — Replace manual 8-field summary rebuilds with `model_copy(update=...)`

- **Constraints**: `BrowserSessionSummary` is a frozen contract model —
  do not touch the contract; `model_copy` is its built-in evolve seam.
  navigate()'s "keep old title on goto failure" (RA-153) semantics stay.
- **Dependencies**: only cdp_driver.py internals; tests in
  `test_browser_reopen_snapshot.py` pin title/url after reopen.
- **Shape**: `self._sessions[sid] = old.model_copy(update={"url": url,
  "title": title or "Page"})` at both sites; the :215
  `has_active_stream=True` hardcode becomes explicit (or stays as an
  update key — implementer's call, but the drift must be resolved, not
  hidden).
- **Test survival**: reopen-snapshot tests green; ruff clean.
- **Deletion test verdict**: concentrates the copy ritual into the
  contract's own seam — CONCENTRATES. Worth exploring (mechanical, but
  drift is already demonstrated).

### RA-156 — Delete the dead `BrowserTaskStore.update_task` seam

- **Constraints**: steer/transfer tools' direct field writes are the
  actual mutation seam; do not change their behavior. `add_timeline_step`
  stays the timestamp bump path.
- **Dependencies**: zero callers of `update_task` (grep over `lca/` +
  `tests/`; RA-152 round independently confirmed). No test pins it
  (checked: no `update_task` in tests/).
- **Shape**: delete `update_task` from `BrowserTaskStore`; the single
  mutation path becomes direct record-field writes followed by
  `add_timeline_step` (the pattern steer/transfer already use).
  Alternative rejected: routing through `update_task` — its `hasattr`
  silent-skip is weaker than direct assignment (typos vanish silently).
- **Test survival**: no test references it; full browser suites stay green.
- **Deletion test verdict**: deletes a false affordance — JUST MOVES
  nothing, REMOVES dead code (RA-137 precedent). Worth exploring.

### RA-157 — Extract the two fail-closed "not implemented" tool rituals into a shared base

- **Constraints**: the honesty contract (warn log + success=False +
  "尚未实现" error, never a fabricated running receipt) is the behavior
  to preserve, per RA-147/RA-149. Spec tool names/descriptions stay.
- **Dependencies**: both tools live in tools.py; driver_tool.py is the
  RA-151-established 同类家园 for shared tool bases.
- **Shape**: `_UnimplementedTool(Tool)` in driver_tool.py holding the
  ritual; subclasses declare the log tag + error message.
  (Mirror of RA-151's `_DriverInjectedTool` convergence.)
- **Test survival**: existing fail-closed tests for spawn_task /
  deep_research (if any pin the messages, update to the shared source);
  ruff clean.
- **Deletion test verdict**: deleting the base moves ~6 lines × 2 back —
  but the ritual is a *contract*, and centralizing means the next
  "not implemented" tool inherits it — CONCENTRATES the honesty ritual.
  Worth exploring (vocabulary-sanctioned two = real; RA-151 precedent).

## Phase 3 — Candidate table

| # | Files | Problem | Solution | Benefits (locality + leverage) | Strength |
|---|-------|---------|----------|-------------------------------|----------|
| RA-154 | `infrastructure/browser/subagent.py` (120-225), `infrastructure/tools/browser/executor.py` (26) | Two dispatch tables over `BrowserActionType`: executor map covers 4 types, `_execute_via_driver` covers 6 (adds TYPE/EXTRACT_TEXT) — same concept, diverging coverage; new types need two edits | Extend `_ACTION_TOOL_NAMES` to TYPE/EXTRACT_TEXT (driver-backed); `_execute_via_driver` delegates to `build_browser_action_executor(driver=...)` | Locality: one dispatch table. Leverage: new action types = one map entry. Tests: driver path + tools path converge, one place to pin result shaping | **Strong** |
| RA-155 | `infrastructure/browser/cdp_driver.py` (215, 325) | Two hand-copied 8-field `BrowserSessionSummary` rebuilds; already drifted (`:215` hardcodes `has_active_stream=True`, `:325` copies it); contract field additions need two edits | `old.model_copy(update={...})` via the frozen contract's own evolve seam | Locality: copy ritual in one expression. Leverage: future contract fields flow through automatically | Worth exploring |
| RA-156 | `infrastructure/tools/browser/task_store.py` (`update_task`), `tools.py` (steer/transfer) | `update_task` is a dead seam (0 callers, 0 tests); the real mutation seam is direct record-field writes in two tools — a false affordance | Delete `update_task`; keep direct writes + `add_timeline_step` as the single path | Locality: one mutation path. `hasattr` silent-skip removed (typos no longer vanish) | Worth exploring |
| RA-157 | `infrastructure/tools/browser/tools.py` (spawn_task, deep_research), `driver_tool.py` | Two = real: identical warn + fail-closed Observation ritual in the two "not implemented" placeholder tools | `_UnimplementedTool(Tool)` base in driver_tool.py (RA-151 precedent) | Locality: honesty ritual in one place. Leverage: the next placeholder tool inherits the contract | Worth exploring |

**Top recommendation**: RA-154 first. It is the only candidate that
finishes a convergence RA-146 started: the "shared execution seam" only
became shared in name while the subagent's fallback kept a private,
diverging dispatch table. Two tables over one enum is the textbook leaky
seam — and the fix deletes ~100 lines while making TYPE/EXTRACT_TEXT
honest citizens of the shared seam. The other three are Worth exploring
in any order (RA-155's drift is already demonstrated, so it edges out
RA-156/157).

**Diversity quota**: satisfied — RA-154 (leaky seam / diverging dispatch,
friction walk), RA-155 (copy-ritual drift, friction walk), RA-156 (dead
seam, friction walk) are all friction-walk findings; only RA-157 is a
duplication-class story.
