---
name: lca-debug-run
description: Use when the user says "latest run", "刚才那个 run", "分析一下这次", "为啥这次失败", "看看发生了什么", "最新一次 run", "DSH 风格轨迹", "traceback 呢" — runs the 5-step run-debrief flow (latest-run resolve → debug-run → journal trace → sidecar/exceptions index → explain), hands off to `lca-code-review` when the evidence points at a real defect, and links `docs/debug/run-debug-guide.md` for the canonical command matrix (CI-locked by `scripts/check_run_debug_sync.py`). Trigger phrases: "latest run", "刚才那个 run", "debug-run", "lca-debug", "分析这次 run", "traceback".
---

# Reading an LCA Run

A run debrief is **not** a bug investigation. The 5-step flow is the routine path; trigger it on the trigger phrases, stop where the evidence stops, and hand off a complete evidence packet (run_id, sidecar traceback excerpt, failing step, profile / bundle id) when the run points at a real defect. This skill is guidance, not a script.

**SSOT layout, do not duplicate:**

- The canonical command SOP — including `WHY / DO / OUTPUT / NEXT / FAIL` per step, sidecar/exceptions paths, bug-report writing rules, `POST /runs` triggering rules, and the CI sync gate — lives in [`docs/debug/run-debug-guide.md`](../../../docs/debug/run-debug-guide.md). That file is locked by [`scripts/check_run_debug_sync.py`](../../../scripts/check_run_debug_sync.py): every `` `lca-ops …` `` backtick path inside it must exist in `lca-ops --help`, or CI fails. The skill links it; it does not restate it.
- This skill owns four things the SOP does not: the trigger-phrase table, the run_id resolution rule, the 5-step flow at a glance (so the agent knows the path before opening the SOP), and the bug-vs-debrief decision + escalation handoff.
- AGENTS.md §6 owns the command-matrix pointers and the "改单 run 调试" reference; the human-readable index of every `lca-ops` subcommand lives in [docs/debug/README.md](../../../docs/debug/README.md) (kept narrow, not duplicated here).

If a command in the SOP changes, fix the SOP first (CI will catch you). If a trigger phrase changes or the bug-vs-debrief split shifts, fix this skill.

## When to use this skill

Enter the flow on any of these — do not ask for clarification, do not `ls traces/runs`, do not grep for the run_id:

- **Direct run reference:** the user supplies a `run_<id>` or says `latest` / `last` / `刚才那个` / `最近一次` / `上一个` / `看看刚才发生了什么`.
- **Failure trigger:** "为啥这次失败" / "这次出错了" / "traceback 呢" / "分析一下这次" / "分析这个失败".
- **Process trigger:** "理解一下过程" / "走了一遍啥逻辑" / "看看这次发生了什么".
- **Output-format trigger:** "DSH 风格轨迹" / "给我个 HTML" / "给我个像 journal 那样的树视图" / "人读 trace".
- **Tool-call trigger:** "模型都做了啥" / "调了啥工具" (route to `lca-ops trace <id> --focus llm|tools|delegation`).

Do **not** enter the flow for: static code questions, ADR review, Profile topology, long-running trend across runs, or "kernel 不响应 / 服务挂了" (the latter is the AGENTS.md §6 service matrix, not a run problem).

## The 5-step flow at a glance

The full per-step `WHY / DO / OUTPUT / NEXT / FAIL` lives in `docs/debug/run-debug-guide.md` (Step 0–8). This is the agent's checklist so a step is never skipped "to save time". Each step consumes the previous step's evidence; do not skip ahead.

1. **Resolve `run_id` from the newest-mtime run dir.** `LATEST=$(ls -1t traces/runs | head -1)` — no pointer file exists; the directory mtime under `traces/runs/` is the sole signal (same rule as `find_latest_run_id()`; CLI journal subcommands also accept an empty run_id and resolve this themselves).
2. **8-section diagnostic.** `./scripts/lca-ops debug-run "$LATEST"` — manifest, journal summary, kernel.log tail, phase.cursor, error_ref, top stack frames, suggested_action, plan_ref + replay commands. [3/8] kernel.log is usually empty and [5/8] error_ref is a *label*, not a traceback. A clean [3/8] does not mean "no failure".
3. **Spine event flow.** `./scripts/lca-ops journal logs -r "$LATEST" -v` (control-point table) and `./scripts/lca-ops journal trace "$LATEST"` (default `--human` tree with payload text + Δms + folded reducer/token noise). Reconstructs what the model saw.
4. **Traceback.** Step 1.5 in user-facing vocabulary, but step 3 of the SOP: `./scripts/lca-ops journal exceptions "$LATEST"` reads the dedicated `<run_id>.exceptions.jsonl` index (every `exception.caught` EP, full payload, guaranteed durable per ADR-2026-09-03). Offloaded sidecars live at `traces/runs/<id>/<sha8>-<SafeClass>.json`. Last-resort `FALLBACK.log` only fires when both ledgers fail to write. Mandatory for any failure trigger phrase.
5. **Failure projection.** `./scripts/lca-ops explain "$LATEST"` projects the causal chain from leaf event up to StopDecision. Only meaningful for failed runs. `./scripts/lca-ops journal steps "$LATEST"` and `./scripts/lca-ops journal narrative "$LATEST>` reconstruct the step tree (early-fail runs may not have `journal.json` — that is normal; verify with `traces/runs/$LATEST/manifest.json`).

Trigger phrase → step coverage:

| User says | Required steps |
|---|---|
| "最新一次 run" / "刚才那个" / "上次" / "最近一次" | 1–5 + step 4 |
| "分析一下这次" / "看看发生了什么" | 1, 3, 4 |
| "为啥这次失败" / "这次出错了" / "traceback 呢" | 1, 2, 4, 5 |
| "理解一下过程" / "走了一遍啥逻辑" | 1, 3, 5 |
| "DSH 风格轨迹" / "给我个 HTML" | 1, 3 + `./scripts/lca-ops journal trajectory "$LATEST"` |
| "模型都做了啥" / "调了啥工具" | 1, 3 + `./scripts/lca-ops trace "$LATEST" --focus llm\|tools\|delegation` |
| "给我个像 journal 那样的树视图" / "人读 trace" | 1, 3 (`journal trace --human`) |
| "所有 traceback 一刀命中" / "grep 异常类" | 1, 4 (`journal exceptions --grep <Class>`) |

`/v1/chat/completions` is **not** a run trigger (LobeHub proxy, ADR-0099; never writes `traces/runs/<id>/`). The only run-creation seam is `POST /runs` / `./scripts/lca-ops runs create`. Whole story: `docs/debug/run-debug-guide.md §How to trigger a run`.

## Routine debrief vs real bug investigation

The line is whether the run's evidence points at a real defect that needs code, config, or a Profile change. Decide before recommending any action.

- **Routine debrief** — the run completed, or failed in an expected way per its Profile's recovery semantics; the user wants to understand the flow, what the model did, or what the outcome was. Answer with the 5-step output, optionally DSH-style trajectory, and stop. No `git blame`, no `grep`, no file editing, no `audit-*` scripts.
- **Real bug investigation** — at least one of:
  - the traceback names an LCA module under `lca/cognition/`, `lca/contracts/`, `lca_kernel/`, `lca/plugins/transport/`, or `lca/infrastructure/env/` and the call site is reachable from the run's actual entry path;
  - `explain` points at a Reducer violation (C4), a capability grant outside parent (C5), or a closed-set extension that lacks an ADR (C1);
  - the Profile / bundle selected for the run does not match the resolved capability (`./scripts/lca-ops why-plugin <id>` shows a missing `provides`);
  - the same failure reproduces across 2+ runs against `traces/runs/` and `git diff <a>..<b> --stat` narrows to a single commit range.

On escalation: open a follow-up branch and follow [`lca-code-review`](../lca-code-review/SKILL.md)'s hot-spot discipline — trace both sides of the changed interface, check Reducer discipline, check Provider registration, check the Journal catalog. Hand off a complete evidence packet: run_id, sidecar traceback excerpt, failing step, profile / bundle id, the seq number of the first `outcome=failure` event. The bug investigation itself is *not* this skill; this skill's job is to decide whether to escalate.

## Common false positives

These look like bugs, are not, and the routine flow handles them without escalation:

- **"kernel.log empty"** — most runs do not write `kernel.log`; absence is not evidence of failure loss. Always read step 4 sidecar/exceptions index.
- **"journal.json missing"** — early-failing runs (Kernel boot error, env whitelist failure) may not produce a Journal. Verify with `traces/runs/$LATEST/manifest.json`.
- **"Profile mismatch"** — a Plugin not in the resolved Profile is by design when the Profile's `provides → requires` DAG excludes it. Verify with `./scripts/lca-ops why-plugin <id>` before claiming a regression.
- **"events.jsonl truncated"** — large events offload to sidecars; `wc -l events.jsonl` is not a completeness signal. The exceptions index (`<run_id>.exceptions.jsonl`) is the completeness signal.
- **"debug-run says error_ref=internal"** — `error_ref` is a typed label (`node=think.main error_kind=internal attempts=1[1:permanent:ValueError]`), not a traceback. Step 4 is mandatory; do not stop at step 2.

## Reporting

End the debrief with:

- the run_id;
- the outcome (completed / failed / awaiting approval / stopped);
- the failing step (if failed) with sidecar path and traceback excerpt;
- one sentence on what the user-visible behavior was (success or failure symptom);
- whether the run is closed (routine debrief) or escalated (bug investigation, with the evidence packet).

Do not editorialize on the architecture in a routine debrief; the user asked for the run's evidence, not a critique. Bug-report writing rules (lead with evidence, cite paths and seqs, separate verified from inferred, one bug per report, never claim fixed without re-running step 7): `docs/debug/run-debug-guide.md §Bug-report writing rules`.

## Don'ts (also enforced by the CI sync gate)

- ❌ `lca-ops replay <run_id>` — that is not a top-level command. Use `./scripts/lca-ops journal replay <run_id> --step N` (`--step` is required). There is no `--no-llm` flag because journal replay only dumps messages + actions and never calls the LLM — that mode is already the default.
- ❌ `/v1/chat/completions` to "trigger a run" — LobeHub UI proxy (ADR-0099); streams OpenAI-shaped chunks without registering a run_id or writing `traces/runs/<id>/`. Use `lca-ops runs create` or `POST /runs`.
- ❌ `lca-ops diagnose phase-error` — alias removed. Real aliases are `model-not-seen` / `loop-stuck` / `memory-poisoned` / `approval-rejected` (hyphenated).
- ❌ `LCA_DEBUG=1` — env var does not exist (replaced by fail-loud; see `docs/debug/README.md`).
- ❌ `cat traces/lca_journal.jsonl` — dead path. The journal SSOT is `traces/runs/<id>/events.jsonl`.
- ❌ `cat traces/runs/<id>/kernel.log` and concluding "no kernel log = bug" — most runs do not write one; step 4 is the completeness signal.
- ❌ Patching source + restart as the first move. ADR-0122 expects `lca-ops debug-run <run_id>` to locate the bug in one command; if it does not, that is a missing ADR-anchored hook, not a missing `grep`.
