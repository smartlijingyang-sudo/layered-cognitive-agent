# Raphy Assessment — 2026-10-21 night (05:45 round)

Branch: `raphy/arch-20261021-0545` (from main `37cd74ab2`).
Scope rule: YAGNI over the last ~40 commits. Hot spots since the 23:45 assess
(`dd82cde2c` assess of RA-174/175/176, merged as `4e85b3f97`):
- **Resume-bundle machinery** (0bb3878f1 per-assistant namespace approval
  override + a514de47e `paused_at` stamp): the write/read contract around
  `resume_bundle.json` is the round's friction-walk area — it was touched
  but not re-walked since the override feature landed.
- **File store delete seam, post-RA-176**: TrashManager now delegates to
  `FileStore.delete`; checked whether the read side honors trash state
  uniformly through the interface.
- **Preset repository** (`37cd74ab2` refactor of `_build_default_bundle_manifest`
  in fs_repository.py; RA-162 landed the dual importlib exec convergence):
  creator/preset pipeline file, freshly touched — third friction-walk area.

Read CONTEXT.md (domain glossary) first. 禁区 respected: ralph Round 2 领地
(ingest/DecisionGates/ContextFiles shims) / lca-1000 迁移 /
`gate_chain_strategy.py` / `computer/guest/preamble.py` untouched. No ADR
re-litigation: the per-assistant override design
(`docs/20-namespace-approval-per-assistant-override.md`, ADR-0292 §10
fail-closed) is deepened, not re-litigated — RA-177 fixes the recovery path
the override feature missed; the fail-closed default stays the default.

## Phase 1 — Explore

Read end-to-end (not grep):
- `lca/plugins/transport/webserver/carrier/runs/recovery.py`
  (resume-bundle inventory, write_resume_bundle/validate_bundle/
  _restore_from_bundle) — full read.
- `lca/plugins/transport/webserver/handlers/runs/terminal/lifecycle.py`
  (RunTerminalCoordinator pause paths) — full read.
- `lca/plugins/session/runtime/resume/point.py` (resume point
  serialize/deserialize, paused_at round-trip) — full read.
- `lca/runtime/projection/result_projection.py` (TerminalResultProjection,
  a514de47e `paused_at` stamp) — full read.
- `lca/infrastructure/tool_defer/session.py` (ToolDeferSession,
  new_defer_session override merge) — full read.
- `lca/infrastructure/file/store.py` (post-RA-176: delete seam, `_is_trashed`)
  — full read.
- `lca/infrastructure/file/trash.py` (post-RA-176 adapter) — full read.
- `lca/infrastructure/preset/fs_repository.py` (FileSystemPresetRepository)
  — full read.
- `lca/infrastructure/runtime_plane/access/approval_engine.py` (RA-174
  landing: uses `namespace_of_tool`, fallback re-sourced) — read.

### Area A: resume-bundle write/read contract (the hot spot)

- Q1 (bounce): write side (lifecycle.py pause → write_resume_bundle →
  `_BUNDLE_FIELDS` inventory) and read side (load_resume_bundle →
  validate_bundle → `_restore_from_bundle`) are anchored on the RA-173
  inventory — one list, walked both ways. The bounce is disciplined, not
  sprawl.
- Q2 (shallow): `_bundle_str`, `_agent_id_of`, `_agent_name_of` are thin
  helpers; deletion test moves them inline — concentrates nothing.
  Not stories.
- Q3 (pure functions / locality): **`apply_driver_outcome` and
  `apply_resume_outcome` (terminal/lifecycle.py:189,203) repeat the same
  pause-time fact capture verbatim**: `session.loaded_namespaces =
  _capture_loaded_namespaces()` + `session.namespace_approval =
  _capture_namespace_approval()`. The two pause paths must freeze the same
  defer facts; adding a third fact to one path and missing the other is a
  divergence bug waiting to happen — "two = real". → candidate RA-178.
- Q4 (leaky seams): **the bundle inventory extracts `namespace_approval`
  on the write side (recovery.py:141-146) but `_restore_from_bundle`
  never applies it to the rebuilt RunSession** — `session.loaded_namespaces
  = restored["loaded_namespaces"]` is there; the sibling line for
  `namespace_approval` is missing. The consumer exists and is real:
  `carrier/runs/lifecycle/lifecycle.py:99` passes
  `getattr(session, "namespace_approval", None)` into
  `new_defer_session(namespace_approval=...)` on the resume rebind, and
  `_capture_namespace_approval`'s own docstring warns that dropping it
  re-gates a run that paused under e.g. `shell=allow` with the global
  default `shell=require_approval`. On the in-process path the paused
  session keeps the field; on the kernel-restart recovery path it is
  silently lost. The bundle carries a field its own read side never
  consumes — write/read divergence at the load seam. → candidate RA-177
  (Strong).
- Q4 (checked, not a candidate): `paused_at` round-trip (RA-159/a514de47e)
  is complete: result_projection stamps `paused_at=utc_now()` on the
  WAITING_INPUT snapshot; `resume_point_from_state_snapshot` reads the
  explicit field (not created_at); deserialize/rebuild
  (`resume_point_to_state_snapshot`) restores it onto the StateSnapshot.
  No divergence.
- Q5 (testability): `test_run_restart_recovery.py` (17) pins restore
  behavior, but no test exercises the recovery path with a per-assistant
  `namespace_approval` override in the bundle — the gap is exactly where
  RA-177's regression test goes. The failure mode (silent re-gate) is
  only observable end-to-end on kernel restart, so the interface needs a
  unit-level pin at `_restore_from_bundle`.

### Area B: file store delete seam, post-RA-176

- **`LocalFileStore.exists()` does not honor trash state.**
  get()/read_bytes()/list() all go through `_is_trashed` and go dark after
  delete; `exists()` checks only the `{attachment_id}/meta.json` sidecar —
  which RA-176 deliberately keeps for recoverability. Net: `exists(id)` is
  True while `get(id)` is None. Its two production consumers both treat
  `exists()` as interface-level validity and get *better* with the fix:
  ingest `try_resolve_local_file` (service.py:248-250) resolves
  `/files/{id}` and LobeHub-ID references, and sandbox `runtime_tools`
  `validate` (runtime_tools.py:119,122) gates `attachment_ids` — today a
  trashed attachment passes both checks while downstream reads fail.
  No test pins `exists()` on a trashed file
  (test_file_store_and_write_tool.py:31 pins it on a live file only).
  → candidate RA-179 (Worth exploring).
- The `if False:` conditional import of FileIndexRegistry (store.py:35-36)
  is dead — a circular-import guard left behind. Deletion test: it
  concentrates nothing. Speculative-grade hygiene; recorded, not written
  (merge into RA-179's diff only if the implementer judges it churn-free).
- TrashManager is now a clean path-addressed adapter (delegates to the
  seam, restore + TTL purge owned locally). No candidate.
- The two `from datetime import datetime, timezone` re-imports inside
  `put()` (module already imports them) are hygiene, not stories.

### Area C: preset repository

- **`FileSystemPresetRepository._load_from_dir` carries two twin plugin-load
  loops (~25 lines each)**: the `plugins/` subdir branch and the legacy
  flat-dir branch differ only in the glob source (`plugins_dir/*.py` vs
  `preset_dir/*.py`) and the name filter (flat branch skips `__*`/`test_*`).
  The per-file body (read code, merge `meta.get("plugins")` descriptors,
  build AuthoredPlugin) is identical — "two = real". One parameterized
  seam `_load_plugins_from(source_dir, *, skip_dunders: bool)` concentrates
  it. → candidate RA-180 (Worth exploring; duplication class, secondary).
- `save()`/`find_by_id`/`list_presets`/`delete()`/`_resolve_dir` are one
  coherent seam over the three-scope topology; the scope-resolution shape
  (PRIVATE vs SHARED vs PLATFORM) is genuinely different per branch —
  not a twin.
- `validate_preset_id` is a deep module (single invariant, enforced at
  every entry); deletion test passes.
- approval_engine.py: already consumes `namespace_of_tool` and the RA-174
  SSOT fallback — the seam is honored; no candidate.

### Runtime verification (mandatory)

- Agent smoke (branch tip == main tip, MockLLMAdapter, LLM_API_KEY=dummy):
  `agent.run("smoke")` x2 on one Agent → RUN1: completed | RUN2: completed.
  (a) and (c) pass. (b) tool-call flow: covered by the 01:45 round's
  scripted-LLM verification; no new crash/hang/silent-failure in core flows.
- Area-specific: `tests/plugins/transport/webserver/test_run_restart_recovery.py`
  17/17 green (recovery path healthy at runtime — RA-177 is a silent-gap
  finding, not a crash).
- `tests/e2e/test_canonical_filesystem_invariants.py` +
  `tests/infrastructure/file/test_trash_manager.py`: 12/12 green.

### Duplication scan (secondary)

- The `_load_from_dir` twin plugin loops are recorded inside RA-180.
- Remaining mechanical duplication: none found worth writing up
  (the `_tool_to_spec` docstring self-declares its deliberate twin with
  `think.history.assemble` — "one adapter = hypothetical seam"; the
  `_is_previewable` vs `classify_readability` split was ruled deliberate
  separation by the 23:45 round).

## Phase 2 — Self-grilling (per candidate)

### RA-177 (Strong)
- Constraints: `bind_resume_capabilities` rebind semantics must not change
  for runs that paused under the global default; ADR-0292 §10 fail-closed
  keeps `shell=require_approval` as the no-override fallback; the
  `validate_bundle` format checks (str→str dict) stay the gate;
  `RunSession.namespace_approval` is `Mapping[str, str] | None = None`;
  old bundles (pre-override) read `{}` via the inventory default and must
  keep resolving to the global default.
- Dependencies: `_restore_from_bundle` ← `RunSessionBuilder.build` ←
  `restore_waiting_run`; consumer `carrier/runs/lifecycle/lifecycle.py:99`
  `getattr(session, "namespace_approval", None)` → `new_defer_session`;
  RA-174's `DEFAULT_NAMESPACE_APPROVAL` SSOT remains the default owner.
- Shape of the deepened module: in `_restore_from_bundle`, next to the
  existing `session.loaded_namespaces = restored["loaded_namespaces"]`,
  add `session.namespace_approval = restored["namespace_approval"] or None`
  (None = legacy/empty keeps the "no override" semantics; `{}` and None are
  equivalent downstream in `new_defer_session`'s merge).
- Test survival: the 17 recovery tests pin restore behavior; new test pins
  a bundle carrying `{"shell": "allow"}` (with a defer session whose
  effective policy had the per-assistant override) rebuilding a session
  whose namespace_approval survives into a `new_defer_session`-equivalent
  rebind (`policy.namespace_approval["shell"] == "allow"`), plus an
  old-bundle regression asserting the global default is kept.
- Deletion test verdict: concentrates — the inventory owns the field;
  the read side currently walks every inventoried field except one,
  which is drift by omission.

### RA-178 (Worth exploring)
- Constraints: `apply_driver_outcome`/`apply_resume_outcome` signatures and
  the `apply_driver`/`apply_resume` aliases stay; the two `_capture_*`
  helpers keep their fail-soft contracts (empty set / None with no bound
  session).
- Dependencies: terminal/lifecycle.py internal only; RunSession fields.
- Shape: `_capture_defer_pause_facts(session) -> None` sets both
  `session.loaded_namespaces` and `session.namespace_approval`; both
  apply_* call it. The pairing of pause-time facts is owned in one place.
- Test survival: existing terminal lifecycle tests; new test pins both
  pause paths capturing identical fact sets.
- Deletion test verdict: concentrates — the two-fact pairing lives in one
  seam instead of two call sites; a third future fact cannot land on one
  path and be forgotten on the other.

### RA-179 (Worth exploring)
- Constraints: `delete()` soft-delete semantics unchanged (mirror
  meta.json+blob kept for recoverability; reads go dark); the registry
  remains the trash-state owner; `exists()` signature unchanged. Both
  consumers (`try_resolve_local_file`, `runtime_tools.validate`) treat
  `exists()` as validity — the fix makes them fail-closed on trashed
  files; no test pins the old behavior.
- Dependencies: FileStore Protocol, LocalFileStore, FileStoreService
  forward, the two consumers above.
- Shape: `exists()` consults `_is_trashed` first — the same gate
  get()/read_bytes()/list() already honor; the whole read surface agrees.
- Test survival: filesystem e2e invariants + trash tests +
  `test_file_store_and_write_tool.py` (pins exists() on live files) stay
  green; new test pins `exists(id) is False` after `delete(id)` while the
  mirror blob remains on disk.
- Deletion test verdict: concentrates — "is this file visible through the
  interface" becomes one question answered once, not per-method.

### RA-180 (Worth exploring)
- Constraints: `save()` writes the `plugins/` layout; `_load_from_dir`
  must keep reading both layouts (subdir + legacy flat); the
  `meta.get("plugins")` descriptor merge and the AuthoredPlugin shape are
  unchanged; discovery (`list_presets`) semantics unchanged.
- Dependencies: FileSystemPresetRepository internal; preset tests
  (`tests/domain/preset/test_preset_repository.py`,
  `tests/infrastructure/preset/test_plugin_loading.py`,
  `tests/infrastructure/preset/test_preset_discovery.py`) pin both layouts.
- Shape: `_load_plugins_from(source_dir, *, skip_name_filters: bool)` —
  the identical per-file body (read code, merge descriptors, build
  AuthoredPlugin) lives behind the seam; the two call sites differ only in
  glob source + dunder/test skip.
- Test survival: both-layout fixture tests stay green; new test pins a
  legacy flat-dir preset loading through the same seam.
- Deletion test verdict: concentrates — ~25 lines of identical
  per-file ritual owned once ("two = real").

### Not written (Speculative / hygiene)
- `store.py:35-36` dead `if False:` conditional import of
  FileIndexRegistry — deletion concentrates nothing; folded into RA-179's
  diff only if churn-free, otherwise a drive-by.
- The two function-level `from datetime import datetime, timezone`
  re-imports inside `LocalFileStore.put()` (module already imports them) —
  hygiene, not a story.

## Phase 3 — Present and record

| # | Files | Problem | Solution | Benefits (locality + leverage) | Strength |
|---|-------|---------|----------|-------------------------------|----------|
| RA-177 | recovery.py (`_restore_from_bundle`), terminal/lifecycle.py:99 consumer | The resume-bundle inventory extracts `namespace_approval` on the write side but `_restore_from_bundle` never applies it to the rebuilt RunSession — the read side walks every inventoried field except one; the kernel-restart recovery path silently drops the per-assistant approval override and the resume rebind falls back to the global default (`shell=require_approval`) even when the run paused under `shell=allow` | Apply the inventoried field on restore (`session.namespace_approval = restored["namespace_approval"] or None`), next to the loaded_namespaces line; add a bundle-round-trip regression test | Locality: the bundle inventory stays the single owner of pause facts — the read side walks it fully. Leverage: the override feature's safety contract (no silent re-gate) holds on the recovery path too | Strong |
| RA-178 | terminal/lifecycle.py | `apply_driver_outcome` and `apply_resume_outcome` repeat the same two pause-time capture lines verbatim; a third future fact can land on one pause path and be forgotten on the other | Converge the twin call sites into `_capture_defer_pause_facts(session)`; both apply_* call it | Locality: the pause-fact pairing owned in one seam. Leverage: future facts are added once | Worth exploring |
| RA-179 | file/store.py (+ ingest/service.py, sandbox/runtime_tools.py consumers) | Post-RA-176, `get()`/`read_bytes()`/`list()` honor trash state but `exists()` does not — the interface disagrees with itself (`exists(id)` True while `get(id)` is None); both consumers treat `exists()` as validity and pass trashed attachments through today | Gate `exists()` on the same `_is_trashed` check the other reads honor; verify the two consumers' tests | Locality: "is this file visible" answered once. Leverage: `try_resolve_local_file` and attachment validation go fail-closed on trashed files | Worth exploring |
| RA-180 | preset/fs_repository.py | `_load_from_dir` carries two twin ~25-line plugin-load loops (plugins/ subdir vs legacy flat dir) differing only in glob source and the dunder/test skip filter | Converge into `_load_plugins_from(source_dir, *, skip_name_filters: bool)` | Locality: the per-file load ritual owned once. Leverage: "two = real" — the next layout variant reuses the seam | Worth exploring |

Top recommendation: do RA-177 first — it is a real behavioral divergence
with a safety edge (a paused-under-`shell=allow` run silently re-gated to
`require_approval` on kernel-restart recovery), it follows the proven
RA-167/RA-174 re-source pattern family, and the fix is one line plus a
regression test that the interface currently cannot pin. Then RA-179
(the delete seam's read surface must agree with itself), RA-178 (cheap
twin convergence that guards a future third fact), RA-180 last (mechanical
twin, duplication-class).

Diversity quota: all four stories come from the friction walk
(Q3/Q4/Q5); RA-180 is duplication-class but is one of four, not the only
class.

Stories written: RA-177, RA-178, RA-179, RA-180 (passes: false).
Assessment complete: 4 stories written, top is RA-177.
