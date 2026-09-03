---
name: lca-pre-push-checks
description: Use before pushing, force-pushing, marking a PR ready, or claiming checks pass on an LCA branch, and after a cascade rebase has rewritten upstream bases. Selects the smallest local evidence that covers the outgoing or just-rebased diff, including the relevant scripts/ verify_*.py + check_*.py + ruff + mypy + pytest, without reflexively running the full 40-script gate. Trigger phrases: "before push", "跑哪些检查", "validation matrix", "pre-merge".
---

# LCA Pre-Push Checks

Run this skill once before any LCA push or after any cascade rebase. The standing validation matrix in [AGENTS.md §6](../../../../AGENTS.md) owns the *which scripts exist* inventory; this skill owns the *which to run for this diff* selection and the order in which to run them. CI owns the exhaustive run and the platform matrix; the local hook only narrows what to execute.

## Inspect the outgoing change

1. Confirm the checkout and branch.

```sh
git status --short --branch
git rev-parse --show-toplevel
```

2. Verify the live PR base or stack parent, fetch that ref, and inspect the complete scope against it.

```sh
# Find the merge base against origin/main (or whatever the PR base is).
git fetch origin
BASE=$(git merge-base HEAD origin/main)
git diff --stat "$BASE"..HEAD
git diff --name-only "$BASE"..HEAD
```

The diff is the inventory. The full set of touched paths decides which checks below apply; nothing else does.

## Select relevant evidence

There is no universal local baseline beyond what `git diff --check` catches on commit. Every behavior change needs the narrowest available test or purpose-built check that would fail for its regression; add broader checks only for surfaces the diff actually reaches.

### The standard LCA check matrix (mirror AGENTS.md §6)

When the outgoing change touches one of the listed scopes, run the matching subset. **Always** start with the cheapest (`ruff --fix`, `git diff --check`) and only escalate when the scope requires it.

| Scope | Minimum check set |
|---|---|
| Only docs / roles / comments | `git diff --check`; `python scripts/verify_md_links.py` |
| Single module implementation | `uv run ruff check --fix <changed-path>` + `uv run ruff format <changed-path>` + relevant pytest |
| Imports / module moves | Above + `uv run lint-imports` |
| Routes + run entry + LobeHub patch | Above + `pytest tests/lca_plugins/transport/ tests/lobehub/` |
| Delete a shared symbol | Relevant pytest + `uv run vulture lca --min-confidence 80` |
| `lca_kernel/` / `lca/plugins/transport/` / `lca/infrastructure/env/` | `python scripts/check_kernel_boundary.py` + `uv run lint-imports` (for `kernel-domain-isolation` & `transport-isolation` contracts) + the 87 / 24 / 19 kernel / transport / env test inventories |
| Contracts / Protocol / enum / registry / Journal / Profile | Full validation: ruff + format + lint-imports + mypy + pytest + vulture + relevant `scripts/check_*.py` |

### Documentation and prose

For docs, Agent Notes, catalogs, or doc-linked comments, run the read-only slop + structure + link gate before commit:

```sh
python scripts/verify_md_links.py        # link rot
python scripts/verify_doc_budgets.py    # size budgets (per scripts/doc_budgets.json)
python scripts/check_doc_layering.py     # docs/design vs docs/specs vs docs/notes layering
python scripts/check_notes_tree.py       # docs/notes/ class + lifecycle + Status closure
python scripts/verify_doc_slop.py        # CoT-leakage / change-narration probe (see lca-trim-cot-leakage)
```

`docs/notes/` 子树的两个检查(`check_notes_tree.py` / `verify_doc_slop.py`)有 agent 优先的 wrapper:`lca-ops notes-check`(结构 / `Status:` ↔ 路径 / class 闭集 / archived freeze)和 `lca-ops notes-slop`(CoT 泄漏机械扫)。本节里其它三个(`verify_md_links.py` / `verify_doc_budgets.py` / `check_doc_layering.py`)暂无独立 wrapper,继续走裸脚本。

Do not pre-generate `.zh.md` sidecars — LCA does not enforce them; add one only when a paired doc already exists.

### Imports / module movement / boundary changes

Per AGENTS.md §6, any change to `contracts/`, Protocol, public signature, enum, `pyproject.toml`, import boundary, or multiple running layers escalates the check set:

```sh
uv run ruff check --fix . && uv run ruff format .
uv run lint-imports
uv run mypy lca
uv run pytest
uv run vulture lca --min-confidence 80
```

### Targeted contract / Protocol / enum / wire / Schema / Journal / Profile

These are the high-blast-radius changes. Beyond the imports matrix above, also run:

```sh
python scripts/check_protocol_impl.py        # every Protocol has a matching impl
python scripts/check_plugin_typing.py        # plugin setup signatures typed
python scripts/check_no_any.py               # ban `Any` in contracts
python scripts/check_no_bare_strings.py      # close-set enum discipline
python scripts/check_assembly_purity.py      # composition-root purity
python scripts/check_no_flat_runs.py         # no flatten-and-pipe shortcuts
python scripts/check_command_envelope_required.py
python scripts/check_kernel_boundary.py
python scripts/check_protocol_schema_version.py
```

### Resource-owning / async / flaky test additions

When the diff adds or changes a fixture, async test, subprocess harness, port-bound test, or shared-host test, apply [lca-ci-test-reliability](../lca-ci-test-reliability/SKILL.md) before picking commands — that skill decides whether quiescent-teardown, concurrent-process, or restoration evidence is needed; this skill still owns the command list and execution order.

### Real-LLM evidence

`real_llm` tests are off by default. Run them only when credentials are present and the user explicitly requests real-LLM coverage:

```sh
uv run pytest -m real_llm -v
```

Report the exact command and observed result. A "looks fine" claim without a recorded run is not a pass.

## Full local rehearsal

Run the complete local approximation only when the user explicitly requests it, while diagnosing a CI failure, or when the change spans the repository so broadly that no narrower set is credible. The full set is the union of the standard matrix above plus the `scripts/check_*.py` corpus relevant to the diff. Do not recreate or bypass the existing 40+ verify / check scripts in `scripts/` — link to them and run them.

## Protect history-rewriting pushes

Rebase is allowed for standalone PR branches and stacked branches (see [lca-archive-notes](../lca-archive-notes/SKILL.md) for note-handling on rewrites). Before a standalone history rewrite:

1. Fetch the current remote branch and record its exact OID.
2. Publish with `--force-with-lease=<branch>:<observed-oid>` so a concurrent update aborts the push.
3. Raw `--force` is never allowed.

After any rewritten push, fetch the live heads again and re-audit mergeability, CI, and unresolved threads. Commit hashes and inline-comment anchors from before the rewrite are not current evidence.

## Handle failures

If a relevant check fails before an ordinary push, stop and fix or explain the blocker. Do not push and hope CI differs.

If a failure looks environment-specific, prove it:

1. Record the exact command, failing test, and platform-specific mismatch.
2. Confirm the relevant non-platform evidence (run the same check on another platform if available).
3. Prefer fixing cross-platform nondeterminism when the check is required.
4. Bypass a local gate only when the user explicitly asks or agrees, and report exactly what failed and why CI is expected to differ.

## Push procedure

1. Run the selected relevant checks once.
2. Commit normally and inspect any files changed by the pre-commit fixer before continuing.
3. Push normally, or use the exact lease for an authorized rewritten branch.
4. Verify the remote ref matches local `HEAD`:

```sh
git rev-parse HEAD origin/$(git branch --show-current)
```

For GitHub PRs, inspect remote CI after the push:

```sh
gh pr checks
```

Report pending checks as pending. Inspect failures before attributing them to the branch or the environment.

## What this skill explicitly does not own

- **Adding or removing verify / check scripts** in `scripts/`. The standing matrix in AGENTS.md §6 is the script inventory. New scripts belong in their own PR with their own check policy.
- **Defining the standard matrix** — see AGENTS.md §6 for the full list and the per-scope minimum. This skill only selects.
- **Bypassing `git diff --check`** — a whitespace / CRLF / trailing-newline fail is always a fix-it-first, not a CI-different claim.