# port-apply playbook

Use `scripts/port_apply.py` to bring a single cluster's main-end-state
onto this branch as one commit, with source-commit attribution in the
body.

## Per-cluster workflow

```bash
# 1. Sanity: check what the cluster's patch looks like (no apply)
python scripts/port_endstate.py --cluster <id>      # confirm path list
git diff bae32d8c27ee2b59312303fbfa68d4738c2f316f..origin/main -- <paths> | wc -l

# 2. Apply + commit (default mode)
python scripts/port_apply.py --cluster <id>
#   - applies via `git apply`
#   - stages <paths>
#   - runs no gates itself; that's the controller's job
#   - emits commit body:
#       port(cluster-<id>): apply end-state delta
#       Source: commits <first>..<last> from origin/main.
#       Lane: <A|B|C>.
#       Lock impact: <none | soft:<path> — wire-shape preserved by X>.
#       Test plan: <paths or "no coverage">.

# 3. Manual gates (run by controller)
uv run ruff check --fix <paths>
uv run ruff format <paths>
uv run lint-imports
uv run pytest --no-cov tests/test_<matching>.py
python scripts/check_locked_surface.py --base HEAD

# 4. If anything fails:
git checkout -- <paths>
git log --oneline -1   # ensure no orphan commit
```

## DAG order

Per ADR-0103 §3:

1. Contracts (C1–C6)
2. ADR + spec + design (C7–C8)
3. Harness (C9–C14)
4. Layer 0 (C15–C21)
5. Layer 1 (C22–C27)
6. Layer 2 (C28–C29)
7. Layer 3 (C30)
8. Layer 4 (C31)
9. Plugins (C32–C35)
10. Profiles / Bundles / Scripts (C41–C43)
11. Tests (C44–C47)
12. Gateway last (C36–C40) — soft-lock; commit body MUST mention
    `wire-shape preserved`.

## Conflict resolution

If `git apply --check` fails:

1. `git diff <base>..<head> -- <paths>` — identify the conflict.
2. Check whether the conflict is on the lock surface (hard or soft).
   If yes, stop and escalate.
3. If the conflict is in non-locked code, split the cluster into
   sub-clusters: e.g., `C16a` (render_contract) and `C16b`
   (project_tool_state). Add the sub-cluster split to
   `docs/port/main-port-plan.md` and re-run.