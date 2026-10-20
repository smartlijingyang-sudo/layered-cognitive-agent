# Raphy Assessment — 2026-10-20 night (23:45 round)

Branch: `raphy/arch-20261020-2345` (from main `17d3eeea2`).
Scope rule: YAGNI over the last ~40 commits. Hot spots since the 07:45 assess
(`6840111a4` merge of raphy/arch-20261020-0745):
- **Canonical filesystem & storage** (15 commits: dc63652d1 plan → c8af8c9e9
  FileRecord schema + visibility/readability helpers → c8d82192e store
  relocation to workspace/user + SQLite index registry → 636cf2734
  FilesystemPromptSection + CONSTITUTION.md invariants → 48f3f643b delivery
  gate → aa61e0d21 recoverable TrashManager + index sync → 7b109097b e2e
  10 invariants + cross-turn continuity → 3fdb46d65 SANDBOX_MOUNT_ROOT
  literal replacement). This is the round's friction-walk area.
- **Per-assistant namespace approval override** (0bb3878f1): profile_runtime
  namespace_approval merged in new_defer_session; pause captures effective
  policy into RunSession; resume bundle round-trips it.
- Minor: a514de47e (resume paused_at stamp), 6e47c0974/f11071fa9 (ingest/
  lobehub fixes — ingest is ralph Round 2 territory, untouched).

Read CONTEXT.md (domain glossary) first. runtime-findings-20261007.md read:
its P0 (non-converging run raising instead of returning Result) is pinned by
the RA-023 regression test per the 07:45 round — not re-raised.

禁区 respected: ralph Round 2 领地 (ingest/DecisionGates/ContextFiles shims) /
lca-1000 迁移 / `gate_chain_strategy.py` / `computer/guest/preamble.py`
untouched. No ADR re-litigation (ADR-0292 §10 fail-closed noted as a
constraint on RA-174; ADR-0244 / canonical filesystem SSOT alignment
respected — candidates deepen the new filesystem modules, they don't
re-litigate the design).

## Phase 1 — Explore

Read end-to-end (not grep):
- `lca/infrastructure/file/store.py` (LocalFileStore, FileStore Protocol, _is_previewable) — full read.
- `lca/infrastructure/file/trash.py` (TrashManager) — full read.
- `lca/infrastructure/file/registry.py` (FileIndexRegistry) — full read.
- `lca/contracts/models/core/workspace/file_record.py` (FileRecord, derive_visibility, classify_readability, to_sandbox_uri) — full read.
- `lca/runtime/delivery/delivery_gate.py` (verify_delivery_attachments) — full read.
- `lca/plugins/prompts/sections/filesystem.py` (FilesystemPromptSection) — full read.
- `lca/infrastructure/runtime_plane/access/approval_engine.py` (NamespaceApprovalStrategy.evaluate, :224) — read.
- `lca/infrastructure/tool_defer/policy.py` (DEFAULT_NAMESPACE_APPROVAL, DeferPolicy) — read.
- `0bb3878f1` diff hunks: spec.py, recovery.py, session/session.py, terminal/lifecycle.py, session.py — read.

### Area A: canonical filesystem / storage (the hot spot)

- Q1 (bounce): the "file product" concept spans store.py (placement +
  mirror + registry write in put()), registry.py (SQLite index),
  file_record.py (contracts: visibility/readability derivation), trash.py
  (path-addressed delete), delivery_gate.py (text-link verification). The
  bounce is layered (contracts → infrastructure → runtime), not sprawl.
  No candidate from Q1 alone.
- Q2 (shallow): `_safe_filename`, `file_part_from_stored`,
  `persist_generated_files` are thin adapters over the store interface;
  deletion test moves them inline — concentrates nothing. Not stories.
- Q3 (pure functions / locality): **`LocalFileStore.put()` hardcodes
  `origin="upload"` while its own module docstring says the store is
  "shared by gateway upload and write_file tool".** Real put() callers:
  write_file tool (`lca/infrastructure/tools/write_file/__init__.py:81`),
  gateway ingest (`handlers/runs/ingest/service.py:209`), sandbox
  observation harvest (`tools/sandbox/observation.py:30`), computer exec
  (`computer/runtime/exec.py:382`). Every agent-generated file is
  mislabeled "upload" in the index — the registry advertises "Provenance
  tracking" but the provenance answer is decided (wrongly) inside the
  store, far from the call site that knows it. → candidate RA-175 (Strong).
- Q4 (leaky seams): **the FileStore Protocol has no delete seam; deletion
  bypasses the interface.** TrashManager takes a raw rel_path + its own
  workspace_root, writes its own `{trash_id}.meta.json + .blob` sidecars,
  and flags the registry directly. Two visible consequences: (a) after
  `trash_file("user/x")`, `store.list()/get()/read_bytes()` keep serving
  the file from the `{attachment_id}/` mirror — trash state and the read
  path disagree through the interface; (b) the id→(meta.json + blob)
  sidecar pattern is hand-rolled twice (store's `{attachment_id}/` dirs,
  trash's flat sidecar files) — two = real seam, un-owned. → candidate
  RA-176 (Worth exploring; TrashManager has zero production callers —
  tests only — so the story pins the seam, it doesn't wire tools).
- Q4 (checked, not a candidate): store.py's `_is_previewable` vs
  contracts' `classify_readability` — both derive "how can this file be
  consumed" from (name, mime), but they answer different questions
  (UI direct-render vs agent conversion tier; PDF is previewable=True but
  CONVERTED). Deliberate separation, different consumers (file parts for
  UI vs prompt section + registry scan). Documented, not written.
- Q4 (checked, not a candidate): the store's `/files/{attachment_id}`
  URLs vs `sandbox://workspace/user/x` narrative links are two addressing
  schemes, but they are complementary by design (id-addressed URLs survive
  the timestamp renames on user/ collision; the gate verifies the
  path-addressed narrative links). Not a twin.
- Q5 (testability): delivery gate and TrashManager have zero production
  callers (tests only) — honest "not yet wired" state, not an
  architecture finding. The e2e invariant suite (8 tests) is green.

### Area B: per-assistant namespace approval override (0bb3878f1)

- The merge seam is single: `new_defer_session(namespace_approval=...)`
  (session.py:377) merges the per-assistant override into
  `DeferPolicy.namespace_approval`. Pause captures the effective policy
  (`_capture_namespace_approval`, twin of `_capture_loaded_namespaces` —
  2-line helpers, hygiene, not a story); the bundle round-trips it via
  the RA-173 `_BUNDLE_FIELDS` inventory; resume re-applies it at
  lifecycle.py:99. One seam, both directions. No twin-derivation drift
  (unlike the pre-RA-171 pending_tools_calling case).
- **`NamespaceApprovalStrategy.evaluate()` (approval_engine.py:224)
  hand-writes the global default `{"shell": "require_approval"}` as its
  no-defer-session fallback, while `DEFAULT_NAMESPACE_APPROVAL` in
  tool_defer/policy.py is the SSOT consumed by DeferPolicy's
  default_factory.** The override feature just made the engine fallback
  the one path that bypasses the override-aware seam. Two derivations of
  one policy = real seam; the exact RA-167 shape (re-source the copy to
  the SSOT). → candidate RA-174 (Strong).
- `validate_bundle`'s inline malformed-format checks (loaded_namespaces +
  namespace_approval, recovery.py:264) mirror each other structurally, but
  they predate RA-173's inventory and guard format (not presence) — the
  inventory's extract/read/required triple doesn't express format
  validation. Folding them in would need a fourth inventory member;
  judged Speculative, not written this round.

### Area C: prompt section + delivery gate

- FilesystemPromptSection renders attachments from FileRecord (readability
  tier, size) — single consumer of the tier vocabulary. No candidate.
- The gate's two regexes extract only `sandbox://workspace/` links; the
  `/files/{id}` served URLs are not gate-verified — complementary
  mechanisms (see Area A Q4 note), not a finding.

### Runtime verification (mandatory)

- This round (mock LLM, MockLLMAdapter, branch tip == main tip):
  `agent.run("smoke")` x2 on one Agent → RUN1: completed | RUN2: completed.
  (a) and (c) pass. (b) tool-call flow: covered by the 01:45 round's
  scripted-LLM verification (referenced by the 07:45 round); no new
  crash/hang/silent-failure in the core flows.
- Area-specific: `tests/e2e/test_canonical_filesystem_invariants.py`
  8/8 green (the assessed area is healthy at runtime).

### Duplication scan (secondary)

- Remaining `/mnt/data` references are sandbox mount-namespace docstrings
  (guest-internal), not host-side literals — 3fdb46d65's
  SANDBOX_MOUNT_ROOT replacement is complete. No mechanical duplication
  found; the twin id→meta+blob sidecar pattern is recorded inside RA-176.

## Phase 2 — Self-grilling (per candidate)

### RA-174 (Strong)
- Constraints: ADR-0292 §10 fail-closed must not change behavior; the
  explicit `approval_mapping` constructor override keeps precedence;
  copy the dict (module-level mutable default must not be shared).
- Dependencies: `NamespaceApprovalStrategy.evaluate()` — only the
  fallback branch changes. `tool_defer.policy` imports only contracts
  (no import cycle; the engine already lazily imports tool_defer
  submodules).
- Shape of deepened module: the fallback reads
  `dict(DEFAULT_NAMESPACE_APPROVAL)`; policy.py remains the single owner
  of the default.
- Test survival: `tests/scenario/test_namespace_approval.py:37` pins the
  SSOT value; `test_namespace_approval_strategy.py` pins fail-closed
  behavior. New test asserts the engine's no-session fallback equals
  `dict(DEFAULT_NAMESPACE_APPROVAL)` (importing the SSOT, not a second
  literal).
- Deletion test verdict: concentrates — the inline literal owns nothing.

### RA-175 (Strong)
- Constraints: backward compat — `origin` keyword defaults to "upload";
  FileRecord.origin Literal is closed
  (upload/agent_created/browser_download/artifact_build), no new values.
- Dependencies: 5 put() call sites (write_file, ingest service, sandbox
  observation, computer exec, capability provider passthrough). The
  e2e test builds FileRecords directly — no test pins the hardcode.
- Shape: `put(..., origin: str = "upload")` on the FileStore Protocol;
  LocalFileStore passes it into the FileRecord; callers pass provenance.
- Test survival: e2e invariant suite stays green; new test pins per-site
  origin.
- Deletion test verdict: concentrates — the store stops pretending to
  know caller provenance.

### RA-176 (Worth exploring)
- Constraints: TrashManager has zero production callers (tests only) —
  the story pins the seam; wiring tools is a separate product decision.
  The `/files/{attachment_id}` URL is the stable deliverable address
  (survives user/ timestamp renames); delete must decide explicitly
  whether the mirror blob survives for recoverability while reads go dark.
- Dependencies: FileStore Protocol, LocalFileStore, TrashManager,
  FileIndexRegistry (trashed_at), the two sidecar writers.
- Shape: `delete(attachment_id)` (soft-delete) on the protocol;
  LocalFileStore owns move + sidecar (via one shared helper) + registry
  flag; list()/read_bytes()/get() honor trash state.
- Test survival: `test_trash_manager.py` + e2e invariants re-sourced to
  the new seam.
- Deletion test verdict: concentrates — the move+sidecar+flag ritual is
  currently split across TrashManager, the registry, and the store's
  unaware reads.

## Phase 3 — Present and record

| # | Files | Problem | Solution | Benefits (locality + leverage) | Strength |
|---|-------|---------|----------|-------------------------------|----------|
| RA-174 | approval_engine.py:224, tool_defer/policy.py:46 | The global fail-closed default is hand-derived twice: SSOT `DEFAULT_NAMESPACE_APPROVAL` vs the engine's inline `{"shell": "require_approval"}` no-session fallback — the one path that now bypasses the override-aware seam | Re-source the fallback to `dict(DEFAULT_NAMESPACE_APPROVAL)` | Locality: the default lives in one module. Leverage: future policy changes can't silently leave the engine's fallback fail-open/fail-closed | Strong |
| RA-175 | file/store.py (Protocol + LocalFileStore.put), 5 put() call sites | put() hardcodes `origin="upload"` although the store is shared by gateway upload AND the write_file tool — every agent-generated file is mislabeled in the index | Add `origin` keyword to put() (default "upload"); each caller passes its provenance | Locality: provenance decided where it's known. Leverage: the registry's provenance queries become truthful | Strong |
| RA-176 | file/store.py (Protocol), file/trash.py | The protocol has no delete seam; TrashManager bypasses it (raw paths, own sidecars); trashed files stay readable via store.list()/read_bytes() | Add `delete(attachment_id)` to the protocol; converge the twin sidecar pattern; reads honor trash state | Locality: "what happens to a deleted file" owned in one module. Leverage: future tool wiring goes through the interface | Worth exploring |

Top recommendation: do RA-174 first — it is the smallest change with the
sharpest safety edge (the fail-closed default is the one invariant the
whole approval story rests on), it follows the already-proven RA-167
re-source pattern, and its blast radius is two lines plus a test.

Diversity quota: all three stories come from the friction walk
(Q3/Q4/Q5) — none is duplication-only.

Stories written: RA-174, RA-175, RA-176 (passes: false).
Assessment complete: 3 stories written, top is RA-174.
