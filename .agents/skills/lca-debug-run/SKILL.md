---
name: lca-debug-run
description: Use when the user says "latest run", "刚才那个 run", "分析一下这次", "为啥这次失败", "看看发生了什么" — runs the LCA AGENTS.md §6 "最新一次 run 全面分析" 5-step flow (jq .run_id, lca-ops debug-run, sidecar traceback, explain, journal trace), distinguishes routine debrief from real bug investigation. Trigger phrases: "latest run", "刚才那个 run", "debug-run", "lca-debug", "分析这次 run".
---

# Reading an LCA Run

A run debrief is **not** a bug investigation. The 5-step flow in [AGENTS.md §6 最新一次 run 全面分析](../../../AGENTS.md) is the routine path; trigger it on the trigger phrases and stop where the evidence stops. This skill is guidance, not a script. **Link, do not restate** the AGENTS.md section — if a step changes, the AGENTS.md section is the source of truth.

## When to use this skill

Use when the user says any of: "最新一次 run", "刚才那个 run", "上次", "最近", "看看刚才发生了什么", "分析一下这次", "为啥这次失败", "这次出错了", "理解一下过程", "DSH 风格轨迹", "模型都做了啥", "调了啥工具", "给我个像 journal 那样的树视图". Don't ask for a run_id and don't `ls traces/runs` — the pointer file is SSOT.

Do **not** use when the user is asking about static code, an ADR, a Profile topology, or a long-running trend across runs. Those go to [`lca-code-review`](../lca-code-review/SKILL.md), [`lca-write-note`](../lca-write-note/SKILL.md), or `audit-*` scripts.

## The 5-step flow

The five steps are mechanical; the value is reading the output, not running the commands. Each step produces evidence the next step consumes; do not skip steps to "save time".

1. **Resolve `run_id` from the pointer file.** `jq -r .run_id traces/latest.json` is the SSOT. Never `ls -t traces/runs`, never `find` — the pointer file is the run the system considers latest, even when file mtimes disagree.
2. **Run the 8-section `debug-run` summary.** `./scripts/lca-ops debug-run "$LATEST"` covers kernel status, journal summary, profile / bundle, and observed symptoms. Note [3/8] (kernel.log) is often empty and [5/8] does not include full traceback; do not conclude "no failure" from a clean [5/8].
3. **Read the spine event stream (table view, optional tree view).** `./scripts/lca-ops journal logs -r "$LATEST" -v` is the control-point table; `./scripts/lca-ops journal trace "$LATEST"` is the human-readable tree (default `--human` with payload text + Δms + reducer/token folding). Use the tree to reconstruct what the model saw.
4. **Read the sidecar JSON.** Large events > 4 KB offload to sidecars via `FileSink._ATOMIC_THRESHOLD` — `events.jsonl` only stores a pointer, the full event lives in `traces/runs/<run_id>/<sha256>.json`. The full traceback lives here, not in the ledger. `jq` out `exception_class`, `exception_message`, `source_location`, and `traceback_text`.
5. **Project failure cause (when the run failed).** `./scripts/lca-ops explain "$LATEST"` projects the failure reason; `./scripts/lca-ops journal steps "$LATEST"` and `./scripts/lca-ops journal narrative "$LATEST"` reconstruct the causal chain (early-failing runs may not have a journal.json — that is normal).

Step 3.5 (sidecar traceback) is mandatory for any failure trigger phrase; step 4 (`explain`) is only meaningful for failed runs.

## Routine debrief vs real bug investigation

The line is whether the run's evidence points at a real defect that needs code, a config, or a profile change. Use this split before recommending action.

- **Routine debrief** — the run completed (or failed in an expected way per its Profile's recovery semantics); the user wants to understand the flow, what the model did, or what the outcome was. Answer with the 5-step output, optionally DSH-style trajectory (`./scripts/lca-ops journal trajectory "$LATEST"`), and stop. No `git blame`, no `grep`, no file editing.
- **Real bug investigation** — at least one of:
  - the sidecar traceback names an LCA module under `lca/cognition/`, `lca/contracts/`, `lca_kernel/`, `lca/plugins/transport/`, or `lca/infrastructure/env/` and the call site is reachable from the run's actual entry path;
  - `explain` points at a Reducer violation (C4), a capability grant outside parent (C5), or a closed-set extension that lacks an ADR (C1);
  - the Profile / bundle selected for the run does not match the resolved capability (`why-plugin <id>` shows a missing provides);
  - the same failure reproduces across 2+ runs against `traces/runs/` and the diff narrows to a single commit range.

Trigger the bug investigation by opening a follow-up branch and following [`lca-code-review`](../lca-code-review/SKILL.md)'s hot-spot discipline: trace both sides of the changed interface, check Reducer discipline, check Provider registration, check the Journal catalog. The bug investigation is *not* part of this skill; this skill's job is to decide whether to escalate, and if so, to hand off a complete evidence packet (run_id, sidecar traceback excerpt, failing step, profile / bundle id).

## Common false positives

These look like bugs, are not, and the routine flow handles them:

- **"kernel.log empty"** — most runs do not write kernel.log; do not conclude "no failure" from a clean kernel.log. Always read step 3.5 sidecar.
- **"journal.json missing"** — early-failing runs (Kernel boot error, env whitelist failure) may not produce a Journal. Verify with `traces/runs/$LATEST/manifest.json` instead.
- **"Profile mismatch"** — a Plugin not in the resolved Profile is by design when the Profile's `provides → requires` DAG excludes it. Verify with `./scripts/lca-ops why-plugin <id>` and the Profile's `requires` list before claiming a regression.
- **"events.jsonl truncated"** — large events offload; do not trust `wc -l events.jsonl` as completeness signal. The sidecar tree is the completeness signal.

## Reporting

End the debrief with:

- the run_id;
- the outcome (completed / failed / awaiting approval / stopped);
- the failing step (if failed) with sidecar path and traceback excerpt;
- one sentence on what the user-visible behavior was (success or failure symptom);
- whether the run is closed (routine debrief) or escalated (bug investigation, with the evidence packet).

Do not editorialize on the architecture in a routine debrief; the user asked for the run's evidence, not a critique.