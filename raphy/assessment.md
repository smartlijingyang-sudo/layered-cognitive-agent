# Raphy Assessment — Round 13 (2026-10-09 01:07, branch raphy/arch-20261009-0107)

Fresh session. Scope via YAGNI: last ~40 commits' hot spots are **skills package
lifecycle** (f6c6a1e84 filesystem-effect declare, 71515dace global-store isolation,
997705416 global_link re-link, ed52b2ff0 YAML block scalar, 0c32cc411 skill-creator
guide, df03d0cf1 write-guard proposal), **CLI doctor chain** (RA-039 landed Round 10;
doctor CLI + stack_heal + debug-trace), and **profile resolve-boot + kernel boot
diagnostics** (911a6ac73/6e6e90d3c resolve-boot pins, 62d776740 list_connections seam,
54ad5f2d9 structlog-only boot diagnostics). Read: runtime-findings-20261007.md
(outranks static findings), CONTEXT.md, raphy/progress.txt `## Codebase Patterns`,
skills/improve-codebase-architecture/SKILL.md. 禁区 respected: preamble.py
(user in-flight), gate_chain_strategy.py, ralph Round 2 territory (incl.
infrastructure/tools/assistant/, lca/cognition/memory/), sandbox (Round 12 RA-048/049/050),
effect dispatch (RA-033/042/043), act subgraph typed ports (RA-041).

Three friction-walk zones were delegated to fresh-session subagents (full end-to-end
reads, 5 questions mandatory each); runtime verification to a fourth. This file
synthesizes their reports with self-grilling per candidate.

## Friction walk

### Area A — CLI doctor / DoctorFacade / stack_heal / debug-trace (32 files read)

1. *Bouncing between modules for one concept?* YES — "diagnose a profile" crosses
   ~12 modules + 1 process boundary (profile.py CLI -> facade.py -> 6 pass files ->
   contracts/diagnostics/doctor.py -> PluginContract -> PlanResolutionService ->
   resolve.py + plan_compile.py -> subprocess scripts/check_plugin_shape.py, whose
   kinds plugin_shape.py re-models with 3 tables). Doctor-layer depth is thin;
   depth concentrates in resolve/compile. Plus 4 mutually-unaware "diagnosis"
   surfaces: `doctor profile` (facade), `runs debug` (spine-direct), `debug trace`
   (journal via TraceInspector), `stack_heal` (service bring-up in steps.py).
2. *Shallow modules?* `_has_compile_errors` = verbatim restatement of
   `DoctorReport.has_errors()` (RA-065 folds it); `_optional_resolve_contracts` /
   `_optional_resolve_phase_graph` 10-of-11 lines identical (twins); `debug_seam.py`
   63 lines provide with zero CLI consumers (RA-061); `SinglePluginDoctor`
   247 lines, tested, zero consumers (RA-067).
3. *Pure functions hiding call-site bugs?* YES — activation_ref 4-link chain
   (RA-052: each link correct, nobody moves finding.plan_ref into
   report.activation_ref; stub test masked it); `except (ValueError, TypeError)`
   in compile_dry_run (RA-072: impl bug misdiagnosed as "profile invalid").
4. *Leaky seams?* YES — PluginShapeDoctor audits ambient cwd while pretending
   run(profile_path) is input-relevant (RA-060); plugin_shape.py second-models
   script kinds against its own docstring's "not a third rule engine" (RA-073);
   facade's `except Exception: return None` conflates "no data" with "chain
   structurally dead" (folded into RA-051).
5. *Untested / untestable?* pass 3-6 production path zero-tested (helpers always
   patched — RA-051); activation_ref e2e zero (RA-052); `lca-ops doctor` mounting
   zero — tests build fresh typer apps, never the real root app (RA-053); trust
   pass real-kind flow zero (map default {}); debug registry seam zero consumers.

### Area B — skills lifecycle (32 files read end-to-end + commits f6c6a1e84/71515dace/997705416/0c32cc411/df03d0cf1)

1. *Bouncing?* YES — "install/activate a skill" holds ~15 modules: create_skill_tool ->
   skill_overlay Protocol -> overlay.py (669) -> importing/gating/receipts ->
   disk/store.py -> frontmatter (TWO parsers) -> _home_layout -> catalog handlers
   (884) -> operational_skills Protocol -> factory/bundled/settings/activation.
   Plus 14 `__init__.py` "Auto-created by split_oversized_directories" shells whose
   own README still lists pre-split flat filenames (doc rot as sprawl evidence).
2. *Shallow?* `quarantine.py` 109 lines, zero production callers, only tests
   import it (RA-062); frontmatter double scan (RA-075); rglob trio
   importing/overlay/bundled (RA-080); exec/bootstrap + format/routing thin —
   dropped as weakest (benefit ~2 jump points, speculative gain).
3. *Call-site bugs?* YES, three textbook cases incl. one past incident:
   resolve_skill_store() "resolves by writing" (71515dace incident: a unit test
   rewrote production ~/.lca/skills — RA-058); safe_rel_path normalize-vs-reject
   split across store/gate call sites (RA-076); importer byte-surgery inserting
   `references: []` to dodge the contract's fail-loud (RA-077);
   DiskSkillPackageStore.__init__ mkdir + settings lru_cache making construction
   timing the hazard (RA-078).
4. *Leaky seams?* YES — three call sites `getattr(store, "root", None)` punching
   through the SkillPackageStore Protocol (RA-059); "activate" as two unaware
   semantics — overlay gates on _ACTIVATABLE_STATES but never injects content,
   SkillActivateTool injects content but checks neither retired nor
   artifact_state — the write-guard proposal's run_755719d1a9d5 exploit lands
   exactly here (RA-055).
5. *Untested?* writeFile drift undetectable by any interface (RA-057; proposal
   exists since this morning df03d0cf1); digest field two conventions
   (full-text vs body hash) across three writers (RA-056); overlay EP emission
   only ever walks the log-degradation branch in unit tests (RA-079).

### Area C — profile resolve-boot / connected_services / kernel boot diagnostics (28 files)

1. *Bouncing?* YES — "parse profile -> boot kernel" spans ~30 modules / 3
   packages (lca.harness.profile.* / lca_kernel.boot.* / lca_kernel.plan.*),
   with ≥7 pure re-export / zero-caller shadow modules from the half-done
   ADR-0115 migration (RA-074). Real depth concentrates in resolve.py,
   plan_compile.py, boot.py's _boot_context four-step.
2. *Shallow?* external_filter.py (dead second filter, divergent heuristic —
   RA-063); boot_compile.py + products wrapper (dead second compile entry,
   options fork — RA-064); lca_kernel/boot/closure.py (K4, zero callers —
   RA-074); BootEntry 44-line module (RA-068).
3. *Call-site bugs?* YES — _emit_boot_events reads `.path` while real
   dataclasses expose `.profile_path`: production boot always emits
   profile_path='' and the test's _FakeResolved(path='<test>') masks it
   (RA-054, textbook fake-shape divergence); pip trust classification: the only
   production caller never passes entry_point_group_by_module, so case-5
   "assume bundled" silently grants trust (RA-066, safety-relevant).
4. *Leaky seams?* YES — products.py writes scope.__dict__ directly while
   observability uses ctx.provide on the same object (RA-069; ADR-0195 P4-K03
   may be deliberate — check first); K6 fail-loud falls back to stdlib logging
   breaking the structlog-only contract (RA-070); ConnectorVault
   suppress(Exception) -> [] makes the agent lie about connection state
   (RA-071).
5. *Untested?* _emit_boot_events never ran against real shapes (RA-054);
   attach_profile_boot_products' re-interpret-rejection branch unpinned; K4
   catalog zero integration coverage (never executed); ConnectorVault corrupt
   file path untested (RA-071). Good counterexample: test_profile_boot_inspection_seam.py
   is a real full boot — read-side coverage is solid; the rot is write-side.

## Runtime verification (mandatory, actually run; baseline ed3f496aa, LLM_API_KEY=dummy)

All six probes PASS, no new P0/P1:
(a) basic run COMPLETED; (b) one-shot tool call COMPLETED **with marker file
really written by the tool** (llm_calls=2); (c) two sequential runs on one agent
COMPLETED x2; (d) RA-023 infinite mock (max_steps=3) -> failed Result, no leak
(tool executed 4x then terminated — fix healthy); (e1) RA-046 run(None) ->
TypeError at entry; (e2) RA-047 NativeToolCall(arguments=str) -> TypeError at
construction, dict still accepted. Related suites green (5 + 9 passed).
Two false positives eliminated by bisection: scripted adapters must implement
stream() (think.llm.invoke walks adapter.stream, Protocol default yields empty
COMPLETED without calling complete()); probe tools must be non-privileged —
bash is in _STANDARD_SHELL_TOOLS privilege list so ADR-0292 §10 grant-absence
fail-closed fires with the EXACT RA-033 regression message ("Agent 运行结束但未
产生任何输出") — a trap for the next verifier; probe now uses a self-built
non-privileged tool through the RA-042 path. Probe script kept at
~/workspace/raphy-probe-r13.py for reuse. Round 12 baseline 0ab9d67cd showed
identical probe behavior.

## Duplication scan (secondary, after friction walk)

Mechanical duplication found: the rglob trio (RA-080) and facade helper twins
(RA-065). Not storied on duplication alone — RA-080's drift (safe_rel_path vs
as_posix) and RA-065's resolve-fork are the friction; both are friction-walk
findings. Quota satisfied trivially: zero pure-duplication stories in the final
list.

## Self-grilling (per candidate)

- **RA-051 (dead pass 3-6 inputs)**. Constraints: I-HPC-7 read-only rule —
  changing getattr-None to explicit contract must not add live fallback writes;
  ADR-0199 §5.1 shapes pass inputs. Dependencies: facade.py + 4 pass modules +
  doctor/profile.py CLI + tests patching helpers. Shape: either plan producers
  grow plugin_contracts/phase_graph_plan projections (deepens plan seam) or
  facade drops dead orchestration and docstring tells the truth (deletes
  illusion). Test survival: all current tests patch the helpers — they'd keep
  passing either way; the new pin on the REAL seam is the only honest one.
  Deletion test verdict: **concentrates** — the getattr-None swallows "contract
  missing" into "no data"; explicitizing forces one true story.
- **RA-052 (activation_ref chain)**. Constraints: DoctorReport frozen contract;
  --json schema stability. Dependencies: compile_dry_run -> facade -> CLI
  --json/_print_human. Shape: single producer fix in run() success branch
  passing activation_ref into from_findings; or delete the dead pipe.
  Test survival: stub test at test_facade.py:270 pins facade behavior only;
  new e2e pin with the real pass. Deletion test: **concentrates** — the
  move (finding.plan_ref -> report.activation_ref) belongs in exactly one place.
- **RA-053 (doctor CLI unmounted)**. Constraints: lca-ops entry semantics.
  Dependencies: cli/cli.py registry, commands/doctor/profile.py register().
  Shape: one register() call in the root app; or explicit retired marking.
  Test survival: existing tests keep passing; the NEW real-root-app pin is the
  finding. Deletion test: **concentrates** — "reachable" is one registration.
- **RA-054 (boot profile_path)**. Constraints: boot event schema. Dependencies:
  _emit_boot_events, both dataclasses, the fake-based test. Shape: read
  .profile_path; test fake rebuilt from the real type. Test survival: the fake
  test is the bug's accomplice — replace, don't preserve. Deletion test: **moves
  nothing** (pure fix), earns existence by restoring attribution.
- **RA-055 (activate gate)**. Constraints: ADR-0214 gate semantics; tool vs
  overlay wording must agree. Dependencies: SkillActivateTool,
  skill_overlay Protocol, _ACTIVATABLE_STATES in overlay. Shape: shared
  predicate extracted once; tool calls it before injection. Test survival:
  existing tool tests don't pin the gap — add retired/unverified pins.
  Deletion test: **concentrates** — one predicate, two callers.
- **RA-056 (digest conventions)**. Constraints: existing Homes carry both
  values — migration needed. Dependencies: three writers, _receipt_from_disk,
  future guard (RA-057). Shape: single skill_index_digest() seam. Test survival:
  receipt tests asserting 'same source' are currently fiction — rewrite.
  Deletion test: **concentrates** — one function, one truth.
- **RA-057 (write guard)**. Constraints: proposal df03d0cf1 already specifies
  refuse-writes-not-reads; legit install/edit paths must keep working.
  Dependencies: is_standing_write_path seam, disk store, RA-056 ideally first.
  Shape: extend guard to {home}/skills/. Test survival: run_755719d1a9d5 replay
  as the pin. Deletion test: n/a (lands a designed guard).
- **RA-058 (resolve/write split)**. Constraints: boot ordering must not change.
  Dependencies: factory, skills_provider setup, overlay's defensive comment.
  Shape: pure resolve + explicit materialize step. Test survival: boot tests pin
  ordering. Deletion test: **concentrates** — "read" and "write" become
  auditable call sites.
- **RA-059 (getattr root)**. Constraints: Protocol honesty; three materialize
  paths must share semantics. Dependencies: operational_skills Protocol, three
  call sites, DiskSkillPackageStore. Shape: declared capability or
  materialize_link seam. Test survival: TypeError-based tests become
  construction-time errors. Deletion test: **concentrates**.
- **RA-060 (cwd leak)**. Constraints: C8 determinism claim; single profile_path
  input. Dependencies: plugin_shape doctor, CLI. Shape: derive repo root from
  profile_path (or explicit repo_root param). Test survival: shape tests use
  stubbed scripts — add the cwd!=repo pin. Deletion test: **concentrates**.
- **RA-061 (debug_seam)**. Constraints: PR-9 may want it; check before
  archiving. Dependencies: debug_seam plugin, debug_trace_provider, lca-ops.
  Shape: land (real debug command) or archive + declare `runs debug` canonical.
  Deletion test: **concentrates** — a seam with no consumers is decoration.
- **RA-062 (quarantine)**. Constraints: ADR-0067 gates remain the real story.
  Shape: delete module + test references. Test survival: the two importing test
  files must be rehomed/deleted — they vouch for dead code. Deletion test:
  trivially **concentrates** (zero production callers).
- **RA-063/RA-064 (dead filters/compile entry)**. Same shape as RA-062: delete;
  note the future growth point (plugin_origin / boot.py single entry) in the
  commit body. Deletion test: **concentrates**.
- **RA-065 (facade resolve x4)**. Constraints: K1+K2 idempotent — sharing one
  result is safe. Dependencies: facade, PlanResolutionService, 4 passes.
  Shape: one resolve + two projections; twins merged; _has_compile_errors
  dropped for report.has_errors(). Test survival: add the call-count pin —
  the test that exposes the embarrassment. Deletion test: **concentrates**.
- **RA-066 (pip trust)**. Constraints: I-HPC-11 default-deny; ADR-0199 §3.4.
  Dependencies: resolve.py call site, discovery phase, plugin_origin case 5.
  Shape: thread discovery map in, or fail-closed on absence. Test survival:
  existing tests pin the fiction — add production-shaped (no-map) pin.
  Deletion test: n/a (safety fix; exploitability speculative, the bug is real).
- **RA-067 (SinglePluginDoctor)**. Constraints: needs product call (wire or
  retire). Deletion test: **concentrates** either way (wired = earns existence;
  retired = removes the gray zone).
- **RA-068 (BootEntry)**. Constraints: none. Shape: inline into _boot_context.
  Deletion test: **concentrates** (interface == implementation verbatim).
- **RA-069 (__dict__ mount)**. Constraints: ADR-0195 P4-K03 may be deliberate —
  READ IT FIRST. Shape: explicit cordis capability or uniform ctx.provide.
  Deletion test: verdict pending ADR read; leak is factual either way.
- **RA-070 (stdlib logging)**. Constraints: structlog availability at K6.
  Shape: structlog.get_logger in fail-loud fallback, or documented dual-channel.
  Deletion test: **concentrates** — one diagnostic channel.
- **RA-071 (vault suppress)**. Constraints: INV classification of corruption.
  Shape: structured warning + fail-loud or degraded marker. Deletion test:
  **concentrates** — honesty about connection state is the module's job.
- **RA-072 (broad except)**. Constraints: ProfileResolveError extends
  ValueError — narrow by explicit tuple, not by base class. Shape: catch the
  named domain types; unexpected -> DoctorCompileError. Deletion test:
  **concentrates** — the except is the module's error model.
- **RA-073 (kind tables)**. Constraints: script stays the single rule source.
  Shape: script emits machine contract; doctor passes through (or shared
  import). Deletion test: **concentrates** — one modeling of kinds.
- **RA-074 (ADR-0115 shadows)**. Constraints: NEEDS an architecture decision
  first — either finish or abandon honestly. Deletion test: all dead parts
  pass individually; the decision is the deliverable.
- **RA-075 (frontmatter)**. Constraints: fail-loud on missing references stays.
  Shape: one parser -> full dict. Deletion test: **concentrates** — one schema,
  one parser.
- **RA-076 (safe_rel_path)**. Constraints: traversal safety must not weaken in
  either direction. Shape: one predicate used by both paths. Deletion test:
  **concentrates** — the policy becomes auditable in one place.
- **RA-077 (importer)**. Constraints: both install paths must share documented
  semantics. Shape: fail-loud or explicit recorded parameter. Deletion test:
  **concentrates** — byte surgery is not a policy.
- **RA-078 (store mkdir/lru)**. Constraints: boot ordering unchanged.
  Shape: lazy mkdir; lifecycle-scoped settings. Deletion test: **concentrates**
  — construction timing stops being load-bearing.
- **RA-079 (EP fake)**. Constraints: event_emitter already injectable.
  Shape: fake emitter + assertions in unit tests. Deletion test: **concentrates**
  — the production branch finally gets pinned.
- **RA-080 (rglob trio)**. Constraints: RA-076's policy covers the seam after
  convergence. Shape: one walk seam in disk/store.py. Deletion test:
  **concentrates** — traversal detail in one place.

## Candidate table

| ID | Files | Problem | Solution | Benefits (locality/leverage) | Strength |
|---|---|---|---|---|---|
| RA-051 | harness/diagnostics/doctor/facade.py, contracts/protocols/state/plan.py, lca_kernel/plan/plan_compile.py | 4 passes' inputs always None (slots dataclass lacks the attrs); getattr-None swallows "contract missing" as "no data" | Real projections on the plan, or delete dead orchestration + honest docstring | Ends tested-green/production-half-dead; `--ci` stops being false safety | Strong |
| RA-052 | doctor/compile_dry_run.py, facade.py, cli/commands/doctor/profile.py | activation_ref 4-link chain: producer never emits, consumers assume; stub test masked it | Move finding.plan_ref into report.activation_ref at the source | --json activation_ref becomes real; tests match production | Strong |
| RA-053 | cli/cli/cli.py, cli/commands/doctor/profile.py | register() never mounted in root app; `lca-ops doctor` doesn't exist | Mount, or declare retired | The tested CLI becomes reachable; assembly seam gets a real pin | Strong |
| RA-054 | lca_kernel/boot/boot.py, tests/lca_kernel/test_boot_events_emitted.py | _emit_boot_events reads .path; real field is .profile_path; fake masked it | Read .profile_path; rebuild fake from real type | Boot logs attributable; closes the fake-shape class of tests | Strong |
| RA-055 | infrastructure/tools/skills/activate/tool.py, contracts/protocols/assistant/skill_overlay.py | activate has two unaware semantics; tool injects content with no retired/verified check | Shared activatable predicate, tool calls it | The tamper exploit's injection surface closes | Strong |
| RA-056 | plugins/assistant/skill/overlay/overlay.py, plugins/domain/assistant/catalog/handlers.py | Same digest field, two conventions (full-text vs body hash), three writers | One skill_index_digest() seam | Prerequisite for the write guard; receipts tell the truth | Strong |
| RA-057 | disk/store.py, _home_layout.py, is_standing_write_path seam | writeFile tampering of verified packages undetectable (run_755719d1a9d5) | Land the proposed guard on {home}/skills/ | `verified` becomes true again | Strong |
| RA-058 | infrastructure/skills/factory/factory.py, plugins/memory/providers/skills_provider.py | resolve_skill_store() "resolves by writing" (71515dace root cause) | Pure resolve + explicit materialize step | Read/write call sites auditable; next mis-call can't silently rewrite prod | Strong |
| RA-059 | operational_skills.py Protocol, overlay.py, catalog/handlers.py | getattr(store,"root",None) x3 punches through the Protocol | First-class capability / materialize_link seam | Impl swap fails at type-check, not runtime TypeError | Strong |
| RA-060 | harness/diagnostics/doctor/plugin_shape.py | Audits ambient cwd, discards profile_path; breaks C8 | Derive repo root from profile_path | Doctor output actually about the diagnosed profile | Strong |
| RA-061 | plugins/observability/cli/debug_seam.py, debug_trace_provider.py | 63-line provide with zero CLI consumers; two debug concepts | Land a real debug command or archive | One debug story; no decorative seam | Strong |
| RA-062 | infrastructure/skills/quarantine.py | Zero production callers; tests vouch for dead code | Delete | Removes the phantom isolation story | Strong |
| RA-063 | harness/profile/resolve/external_filter.py | Dead second filter, divergent heuristic | Delete | Removes the misuse lure | Strong |
| RA-064 | harness/composition/boot_compile.py, profile/boot/products.py wrapper | Dead second compile entry with forked options | Delete (or route production through it) | One true compile entry | Strong |
| RA-065 | harness/diagnostics/doctor/facade.py, contracts/diagnostics/doctor.py | 4 full resolves per doctor call; twin helpers; _has_compile_errors restates has_errors() | Resolve once + merge twins + drop the restatement | -3/4 K1+K2 cost; no compile fork; call-count pin | Strong |
| RA-066 | harness/profile/resolve/resolve.py, plugin_origin.py | Pip trust falls back to "assume bundled" on the production path (map never passed) | Thread discovery in, or fail-closed | ADR-0199 trust model holds in production | Strong bug / Worth exploring exploitability |
| RA-067 | doctor/single_plugin.py, doctor/__init__.py | 247 lines, tested, zero consumers, no "unwired" record | Wire `doctor plugin <path>` or mark retired | Coverage stops vouching for unreachable code | Worth exploring |
| RA-068 | harness/profile/boot/projection.py, lca_kernel/boot/boot.py | 44-line module, interface == implementation | Inline into _boot_context | One fewer concept | Worth exploring |
| RA-069 | harness/profile/boot/products.py | Seam mounts via Context.__dict__ backdoor | Explicit cordis capability or uniform ctx.provide | Seam stops depending on framework private layout | Worth exploring |
| RA-070 | lca_kernel/boot/lifecycle.py, lifespan.py | Fail-loud uses stdlib logging, breaking structlog-only | structlog in fallback or documented dual-channel | One diagnostic channel for on-call | Worth exploring |
| RA-071 | infrastructure/connectors/core/vault.py | suppress(Exception) -> [] lies about connection state | Structured warning + fail-loud/degraded marker | Corruption surfaces early | Worth exploring |
| RA-072 | doctor/compile_dry_run.py | except (ValueError, TypeError) misdiagnoses impl bugs as "profile invalid" | Narrow to named domain errors; unexpected -> DoctorCompileError | Doctor stops blaming the user's YAML for its own bugs | Worth exploring |
| RA-073 | doctor/plugin_shape.py, scripts/check_plugin_shape.py | Three kind tables second-model script semantics vs own docstring | Machine contract from the script; doctor passes through | No human sync point; new kinds can't silently degrade | Worth exploring |
| RA-074 | lca_kernel/boot/closure.py, profile/boot/runtime_closure.py, lca_kernel/plan/{resolve,declarations,source}.py | ADR-0115 inverted migration: deprecation warnings name nonexistent modules; K4 chain never executes | Architecture decision: finish or abandon honestly | Policy either enforced or gone — no middle state | Worth exploring |
| RA-075 | infrastructure/skills/frontmatter/frontmatter.py, disk/store.py | Two syntax-inconsistent parsers scan the same text | One parser -> full dict | `references` fix-class patches stop recurring | Worth exploring |
| RA-076 | disk/store.py, plugins/assistant/skill/overlay/gating.py | safe_rel_path: store normalizes, gate rejects — same input, opposite policies | One predicate for both paths | Traversal policy auditable in one place | Worth exploring |
| RA-077 | infrastructure/skills/http/importer.py | Byte-surgery inserts `references: []` to dodge fail-loud | Fail loud, or explicit recorded parameter | Both install paths share semantics; pulled bytes stay intact | Worth exploring |
| RA-078 | disk/store.py, infrastructure/skills/settings/settings.py | __init__ mkdir + lru_cache make timing load-bearing | Lazy mkdir; lifecycle-scoped settings | Construction stops being an implicit correctness precondition | Worth exploring |
| RA-079 | plugins/assistant/skill/overlay/overlay.py | Unit tests only ever walk the log-degradation EP branch | Inject fake emitter, assert EP descriptors | Production EP branch finally pinned | Worth exploring |
| RA-080 | overlay/importing.py, overlay.py, bundled/bundled.py | Three rglob implementations with drifting traversal details | One walk seam in disk/store.py | Traversal safety converges | Worth exploring |

## Top recommendation

**Start with RA-051.** The doctor is the codebase's flagship "trust me, I'll check
your profile" tool, and in production it runs 2 of its 6 documented passes — the
other four are structurally dead behind a getattr that can never succeed, while
the test suite patches the seam and stays green. That "tested green, half-dead
in production" shape is exactly the class of rot that bit RA-033 (tools silently
never executing). RA-051's fix (real projections, or honest deletion) forces the
one true story about what doctor does — and it shares a file with RA-065, so the
two optimize naturally together. RA-053 (the CLI isn't even mounted) and RA-066
(trust classification) are the runners-up on the "production differs from
promise" axis.

Diversity quota: satisfied — all 30 stories come from the friction walk
(shallow modules, leaky seams, no-locality call-site bugs, testability gaps);
zero pure-duplication stories.
