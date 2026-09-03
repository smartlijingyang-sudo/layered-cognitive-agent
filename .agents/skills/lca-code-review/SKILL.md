---
name: lca-code-review
description: Use when reviewing an LCA pull request — orients the reviewer to LCA standing rules (五层单向依赖, cognitive closed set, contracts/Protocol changes, journal catalog additions, profile topology changes) and the review-specific checks that code alone can't show; PRs touching new decisions should add an Agent Note under docs/notes/. Trigger phrases: "review this PR", "lca-code-review", "审查 LCA PR", "看下这个 diff", "review 一下".
---

# Reviewing an LCA PR

**This skill is guidance, not a checklist.** Re-establish base and head on the PR (do not trust the title), read the diff, then read enough surrounding code to understand the design. A short review with one substantiated blocker is better than a list of nits; prioritize correctness, lifecycle, security, and broken required behavior over style. Note: 老 ADR (`docs/adr/`) 一律不动; if the change would have touched an ADR, route through [AGENTS.md §1](../../../AGENTS.md) instead.

## Sources of truth

- [AGENTS.md](../../../AGENTS.md) — root standing rules: 总闸 4 问, 契约改动闭环, 兼容路径模板, 卫生清单.
- [AGENTS.md §3 五层单向依赖 + 不变量 C1–C7](../../../AGENTS.md#3-架构不变量) — dependency direction, cognitive closed set, Reducer discipline.
- [AGENTS.md §5 编码规范](../../../AGENTS.md#5-team领域语言与编码规范) — Protocol, enum, registry, Journal, comments.
- [AGENTS.md §6 验证矩阵](../../../AGENTS.md#6-命令与验证) — `lint-imports`, `check_protocol_impl.py`, `check_no_any.py`, `check_assembly_purity.py`, `check_no_flat_runs.py`, `check_kernel_boundary.py`, `verify_md_links.py`, `verify_doc_budgets.py`.
- [docs/notes/README.md](../../../docs/notes/README.md) and the active lifecycle [AGENTS.md](../../../docs/notes/proposed/AGENTS.md) — new decisions go here unless they change other ADRs' boundaries.
- [docs/debug/run-debug-guide.md](../../../docs/debug/run-debug-guide.md) — run-time debugging methodology (linked, not restated).

## Blocking requirements

1. **New prose receives semantic review.** Required coverage per [AGENTS.md §5 编码规范](../../../AGENTS.md): 类型、失败语义、时序、所有权、外部后果 must be present in JSDoc / docstring / module comment where the contract is non-obvious; "narrate what the code does" comments are deletion candidates.
2. **Docs match the code.** Config, defaults, errors, wire fields, events, and public behavior update the owning README and JSDoc in the same diff. Comments state non-obvious contracts; flag implementation narration, test walkthroughs, and duplicated rationale for deletion or a link to their one home.
3. **Five-layer dependency direction is monotonic.** `contracts → infrastructure → cognition → runtime → agent`; `application` is the composition root, never imported from below. Webserver transport binds to Protocols, not to specific Brain/Body/Loop. Enforced by `lint-imports` and `pyproject.toml`; review for accidental reversals (a `runtime` module importing from `agent`, an `infrastructure` module importing a concrete Plugin from `plugins/`).
4. **Protocol / enum / wire changes are closed-set.** New values enter via the closed enum or Protocol extension — never via a parallel string / int / dict field. Whitelist changes (catalog, emit, consume, docs) ride along in the same PR per [AGENTS.md 契约改动闭环](../../../AGENTS.md). Cross-check: a new `ActionType` value appears in every consumer, every Journal emission site, every doc reference.
5. **Reducer discipline (C4).** Sensor, Gate, Body never mutate `AgentState` in place; they emit Delta/Event and `reducer.apply_*` applies it. Reject any "convenience" write that bypasses the Reducer; ask for the COMPAT block if the bypass is intentional, with a deletion date.
6. **Plugin manifest is complete.** New Plugins declare `id`, `provides`, `requires`, `layer`, `kind`, `effects`, `test_suite` per [AGENTS.md §3 插件与扩展](../../../AGENTS.md). Profile DAG respects `provides → requires`; a Plugin whose `requires` are not declared in any Profile in the same PR is a finding.
7. **Env whitelist honored (K7).** Plugin code does not read `os.environ`; all credential / path input goes through Profile `{from_env: …}` and the LLM Resolver per [AGENTS.md §3 K7 BOOTSTRAP_NAMES](../../../AGENTS.md).
8. **No unbounded TODOs.** Per [AGENTS.md §1 卫生清单](../../../AGENTS.md), every `TODO` / `FIXME` carries a deletion date or a `COMPAT(delete-when: <condition>, tracking: <ADR | issue>)` block. Bare markers are blockers.
9. **New decision needs an Agent Note.** PRs that introduce a new `contract` / `primitive` / `seam` / `profile` / `runbook` decision add a Note under `docs/notes/{lifecycle}/{class}/`. Skip only when the change is purely an implementation detail, a temporary fix, or a same-contract implementation swap. Use [`lca-write-note`](../lca-write-note/SKILL.md) when the PR is large enough to need it; the note lives in the same PR as the code change.

## Hot spots

These are the diff ranges that deserve a longer second look. Each hot spot ties back to a standing rule and a mechanical check that the PR description should cite.

- **`contracts/` Protocol changes** — every implementation, every enum consumer, every wire serializer, every doc reference, every Journal emission. Verify with `uv run python scripts/check_protocol_impl.py`. Required fields stay `runtime-checked`; no `Any` (`check_no_any.py`); no bare strings replacing enum tokens.
- **Journal catalog additions** — new event names enter the closed catalog; `cordis` event derivation matches (`check_cordis_event_derivation.py`); `docs/observability/` updated; emitted by the exact phase that owns the event (Reducer single-writer per [`audit-state-writers`](../../../AGENTS.md#6-命令与验证)).
- **Profile topology changes** — `provides → requires` DAG still resolves; new Plugins appear in the Profile's `provides` set; `audit-plugin-capability` (`why-plugin <id>`) shows the new Plugin as expected; no new capability granted outside the Profile (capability grant ⊆ parent per C5).
- **`lca-kernel/`, `lca/plugins/transport/`, `lca/infrastructure/env/`** — require `scripts/check_kernel_boundary.py` plus importlinter `kernel-domain-isolation` and `transport-isolation` per [AGENTS.md §6 验证矩阵](../../../AGENTS.md). PR-7 kernel domain isolation rules forbid top-level `lca_kernel` outside the whitelist; confirm the diff respects the `ignore_imports` list.
- **Closed-set extension (C1, C2)** — adding a new phase, a new event word, a new schema, or a new Plugin kind requires an ADR per [AGENTS.md §3 C1 闭集](../../../AGENTS.md). Default-deny: the reviewer challenges each proposal to either prove the ADR exists in the same PR or prove the change is intra-set (not an extension).

## Manual checks

- **Intent and interface contracts** — trace both sides of every changed interface. Confirm the implementation matches the PR and any [Agent Note](../../../docs/notes/README.md); disagreement with an Agent Note is a design discussion, not a veto.
- **Lifecycle and concurrency** — for async setup, callbacks, processes, or teardown, check races before publication, cancellation during awaits, independent error reporting, callback containment, ownership before reentry, complete detach cleanup, quiescent disposal.
- **Capability and consumer fit** — flag generic-service API expansion whose only caller is one internal consumer; require a private capability closure handed to that consumer instead.
- **Scope, ownership, and necessity** — map each abstraction, state machine, option, defensive copy, and compatibility path to its current contract, production consumer, and owning Plugin. Challenge unrelated features and speculative generality.
- **Configuration and public choices** — require current-consumer evidence or prior art for each default, public operation set, format, or imported external concept.
- **Borrowed and derived state** — determine whether each retained value is borrowed or owned, then trace notifications and every cache, prompt, UI echo, replay, and query view to the documented success point.
- **Bounds cover the final operation** — probe tiny and exact limits, oversized single chunks, multibyte text for byte limits.
- **Real entry path** — tests exercise the shipped Loader, kernel bin, worker, webserver route, or subprocess where relevant; hand-mounted plugins do not catch Loader regressions.
- **Test strength** — assertions fail on the intended regression and verify external state, logs, events, or disposal rather than restating the implementation.
- **Implemented Agent Notes match shipped reality** — when a PR promotes a `proposed/` note, the rewrite to `implemented/` lands in the same diff; paths, names, and mechanisms match the implementation.

## Reporting findings

State the defect, location, impact, and evidence. Place a localized defect inline on the tightest relevant diff range; use a PR-level comment for cross-cutting architecture, scope, or review-wide synthesis. Separate blockers from suggestions; omit issues already enforced by a green gate. When receiving review, verify each claim and fix or rebut it on technical grounds without performative agreement.

## Commands / 调用方式

PR 动到 `docs/notes/`(新增、promote、archive 任何一组三元组)时,用 `lca-ops notes-check`(内部调 `scripts/check_notes_tree.py`)确认 `Status:` ↔ 路径、`class` 闭集、archived 冻结规则都成立;这是 agent 优先入口,CI / 手动调试才直接调裸脚本。