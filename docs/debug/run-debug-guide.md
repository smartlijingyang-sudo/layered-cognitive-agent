# Run debug SOP (coding-agent workflow)

> **This document is for the coding agent**, not for humans. When a user
> asks "why did this run fail?", "show me the latest run", "what just
> happened", or supplies a `run_id`, follow the 8-step procedure below.
> Each step tells you **why / how / output / what next / fail mode**.
>
> Humans get readable views via the journal viewers the SOP names —
> `journal trace --human`, `journal narrative`, `journal trajectory` —
> not from this document.
>
> **SSOT rule.** Commands listed here are kept in sync with the CLI by
> `scripts/check_run_debug_sync.py`. That script asks `lca-ops --help`
> (the real registry) what commands exist and diffs against every
> `lca-ops ...` path this SOP mentions. Run it in CI; if it fails, this
> document is lying and you must fix it before proceeding. See
> §Maintenance for details.

---

## When to enter this SOP

Trigger phrases (run this immediately, do not ask for clarification):

| User says | Enter SOP? |
|---|---|
| "最新一次 run" / "刚才那个" / "上次" / "最近一次" / "看看刚才发生了什么" | yes |
| "为啥这次失败" / "这次出错了" / "分析一下这次" | yes |
| "理解一下过程" / "走了一遍啥逻辑" / "DSH 风格轨迹" / "给我个 HTML" | yes |
| supplies a `run_<id>` directly | yes |
| "刚才服务挂了" / "kernel 不响应" | no — go to AGENTS.md §6 service matrix |

**Hard rule for run_id**: always read it from the atomic pointer, never ls/find/mtime:

```sh
LATEST=$(jq -r .run_id traces/latest.json)
```

---

## The 8-step procedure

Each step has five labels you should expect to find in your own output:

- **WHY** — what this step rules in / out
- **DO** — exact command(s), JSON flag for you, human flag for the user
- **OUTPUT** — what you'll see (success and failure)
- **NEXT** — when to advance
- **FAIL** — what to do if this command itself misbehaves

### Step 0 — Confirm the failure surface

**WHY.** Distinguish "service layer is broken" from "this run failed". The rest of the SOP assumes `kernel_serve` is up.

**DO.**

```sh
lca-ops status --json
```

**OUTPUT.** JSON with five services: `kernel_serve`, `infra`, `lobehub`, `daemon`, `onlyboxes`. Anything `unhealthy`/`missing`/`not running` → service problem, not run problem.

**NEXT.** If any service is down: `lca-ops heal --json`, then re-check. Once `kernel_serve: healthy`, advance to Step 1.

**FAIL.** `lca-ops` itself fails → check `which lca-ops`, run with `bash -x ./scripts/lca-ops status --json` to see where it dies.

---

### Step 1 — One-shot 8-section diagnostic

**WHY.** `debug-run` is the canonical "tell me about this run" entry point (ADR-0122). It collects manifest, journal summary, error_ref, stack frames, and a suggested action in one shot.

**DO.**

```sh
# Human-readable (default)
lca-ops debug-run "$LATEST"

# You (agent)
lca-ops debug-run "$LATEST" --json
```

**OUTPUT.** 8 sections. Important nuances:

- `[1/8] manifest` shows `status` (failed/passed) and `broken_hop` (e.g. `H3` = the 3rd hop in the phase graph).
- `[2/8] journal` shows spine event count and `missing_seqs` (gaps in seq numbers).
- `[3/8] kernel.log` is a tail of `traces/runs/<id>/kernel.log`. **Most runs do not have this file** — its absence is *not* evidence of failure loss. (See sidecar step below.)
- `[4/8] phase.cursor` — last completed phase.
- `[5/8] error_ref` — a *typed label* like `node=think.main error_kind=internal attempts=1[1:permanent:ValueError]`. **It is not the traceback.**
- `[6/8] stack frames` — top 8 frames only.
- `[7/8] suggested_action` — human hint.
- `[8/8] replay command` — copy-paste replay for the user.

**NEXT.** If `status=passed` → done; the user is wrong about the failure. If `status=failed`, advance to Step 2.

**FAIL.** `debug-run` errors → Step 0 service problem is real; resolve first.

---

### Step 2 — Read the full spine event flow

**WHY.** Step 1 gives you a label. You need the *evidence* — what the LLM actually saw, what tool calls fired, where the chain broke. There are two views; pick by use case.

**DO.**

```sh
# Default human view (tree indent + payload text + Δms + auto-collapse
# token/reducer noise). Pass this to the user when they ask "走了一遍啥逻辑".
lca-ops journal trace "$LATEST"

# Compact table — control points + channel + outcome. Fast to scan.
lca-ops journal logs -r "$LATEST"

# Expand payloads (and surface sidecar traceback when --v finds an
# offloaded event)
lca-ops journal logs -r "$LATEST" -v

# You (agent). Pipe to jq, don't try to parse the human tree.
lca-ops journal trace "$LATEST" --json
```

**OUTPUT.**

- `journal trace` (default `--human`): a tree with ▸/↳ markers, Δms relative to run start, and folded payload text. Auto-collapses `llm.stream.token`, `runtime.reducer.apply`, paired `transport.route.{enter,exit}`.
- `journal logs` (default): one line per event, columns `time / channel / execution_point / outcome`.
- Both read `traces/runs/<id>/events.jsonl` (spine SSOT, ADR-0167).

**NEXT.** Look at the failure. Find the first event with `outcome=failure` (or the `broken_hop` from Step 1). Note its `seq` number and `execution_point`. Advance to Step 3 to find the exception itself — Step 2 alone won't give you a traceback because exceptions over 4 KB are offloaded.

**FAIL.** `journal.jsonl events=0` but `events.jsonl events=N>0` → the run was early-fail, the step-tree never materialized. That's expected for early failures. Don't run `journal steps` (it'll say `journal.json not found`); go straight to sidecar.

---

### Step 3 — Read the sidecar for the full traceback (most-skipped step)

**WHY.** Spine events > 4 KB are offloaded to `<sha256>.json` sidecar files by `FileSink._ATOMIC_THRESHOLD` (I10). Any event containing a full Python traceback is *always* over 4 KB, so its traceback is in the sidecar, **not** in `events.jsonl`. `debug-run [5/8] error_ref` only carries the label, not the traceback. If you skip this step, you're guessing.

**DO.**

```sh
# List sidecars in the run directory.
ls traces/runs/"$LATEST" | grep -vE '^(events\.jsonl|manifest\.json|profile_snapshot\.json|\..*\.swp)$'

# Pick the first sidecar (usually exactly one), pull the traceback.
SIDECAR=$(ls traces/runs/"$LATEST"/*.json 2>/dev/null \
  | grep -vE 'events\.jsonl|manifest\.json|profile_snapshot\.json' | head -1)
[ -n "$SIDECAR" ] && jq -r '
  "exception_class:   \(.payload.exception_class // "-")",
  "exception_message: \(.payload.exception_message // "-")",
  "source_location:   \(.payload.source_location // "-")",
  "---traceback---",
  (.payload.traceback_text // "(no traceback_text)")
' "$SIDECAR"
```

**OUTPUT.** The exact `ValueError` / `RuntimeError` / etc., the file:line where it raised, and the full Python traceback.

**NEXT.** You now have the exception class + message + source. Advance to Step 4.

**FAIL.** No sidecar files at all → the failure was a control-point failure (outcome=failure, no Python traceback). Read the event payload from `events.jsonl` directly: `jq -r 'select(.seq==N) | .payload' traces/runs/"$LATEST"/events.jsonl`.

---

### Step 4 — Fail-path projection

**WHY.** Step 3 gives you *what* threw. Step 4 gives you *why the system decided to stop* — the causal chain from leaf cause up to the StopDecision.

**DO.**

```sh
lca-ops explain "$LATEST"           # human
lca-ops explain "$LATEST" --json    # you (agent)
```

**OUTPUT.** A `FailureExplanation` projection: leaf event, causal ancestors (parent_seq chain), `StopDecision.failure` record, suggested attribution.

**NEXT.** If the traceback points at a code path and `explain` shows the calling phase → Step 5 (read code).

**FAIL.** `explain` itself crashes (this happens for some early-fail runs — there is one known `AttributeError: 'int' object has no attribute 'get'` path in `minimal-repro`; if it dies, you have the sidecar traceback anyway, proceed to Step 5).

---

### Step 5 — Locate the failure in code

**WHY.** Now you read the actual code path. The traceback told you `path/to/file.py:line`. Find that line. Read the surrounding 30 lines and the docstring.

**DO.**

```sh
# Read the file:line from the traceback.
# Use rg / read_file / your tool of choice.
```

**NEXT.** You now classify the failure into one of:

| Pattern | Likely fix surface |
|---|---|
| New execution_point not in `EXECUTION_POINTS` whitelist | observability whitelist constant (e.g. `event_record.py`) |
| Missing capability/dependency in plugin Manifest | `lca/plugins/<plugin>/manifest.py` |
| Reducer wrote state outside `apply_*` | `lca/cognition/<area>/reducer.py` |
| Tool bypassed Body (sandbox/transport direct import) | audit with `lca-ops audit-direct-commands` |
| Hook re-introduced where forbidden | `lca-ops audit-hook-attach` |
| Side effect without reducer first | Body / SafeExecutor |
| Profile topology missing a provides/requires | `lca-ops inspect-tree <profile>` then `lca-ops why-plugin <id>` |

If you find the failure root cause is *not* a single missing line (e.g. protocol mismatch, missing ADR) → escalate to Step 6 (diff against a passing run).

**FAIL.** Code is unclear → Step 6.

---

### Step 6 — Diff against a passing run (optional, for non-obvious bugs)

**WHY.** When the traceback is "obvious" but the *reason* isn't (the code path always ran before; why did it fail now?), the fastest disambiguation is a passing run from yesterday.

```sh
lca-ops diff-runs <failing_id> <passing_id>
lca-ops diff-context <failing_id> --step N
```

For narrower comparisons, `optimize <run_id>` ranks candidates by latency/token/retries; `cost <run_id>` shows the LLM spend.

**NEXT.** If diff reveals a profile/prompt/bundle change → that change is the regression. If diff is empty → random non-determinism (LLM, network); not a code fix.

---

### Step 7 — Verify the fix on the live system (do not skip)

**WHY.** Debugging is read-only. *Verifying* the fix requires a new run. Don't tell the user "fixed" until you've reproduced.

**DO.**

```sh
# If you changed code:
lca-ops kernel-restart --json

# Then re-trigger the run via the same path the user used.
# (Run via API / scenario file / curl — whatever the user's flow is.)

# Then re-enter this SOP at Step 1 with the new run_id.
LATEST2=$(jq -r .run_id traces/latest.json)
lca-ops debug-run "$LATEST2" --json
```

**OUTPUT.** `status=passed`, no exception class matching the prior bug.

**NEXT.** If passed, report. If still failing with same exception class → the surface is wrong, go back to Step 3 with the new run's sidecar.

**FAIL.** `kernel-restart` itself fails → Step 0.

---

### Step 8 — Report to the user

**WHY.** A coding agent that says "I fixed it" without reporting the *evidence trail* is not finished. The user wants the human-readable view.

**DO.** Produce a report with this exact three-part structure:

1. **Facts** — what `debug-run` / sidecar / `explain` actually printed.
   Quote the exception class, message, and the exact `file:line`.
   Do not paraphrase.
2. **Inferred** — your classification of the bug (which row of the
   Step-5 table it matches) and the causal chain in 2–3 sentences.
3. **Fix** — which file(s) you intend to change and why, and the
   verification result (Step 7). If you did not run Step 7, say so
   explicitly — do not claim a fix is done until you have.

Then offer the user the human-readable view(s):

```sh
# Tree with payloads + Δms (default --human)
lca-ops journal trace "$LATEST"

# narrative.md story
lca-ops journal narrative "$LATEST"

# DSH-style HTML trajectory
lca-ops journal trajectory "$LATEST"        # → traces/runs/<id>/journal.trajectory.html
```

Pick whichever the user actually asked for. Never hand the user raw `jq` output as a "human view".

---

## Bug-report writing rules

When you (the agent) write the bug summary for the user:

- **Lead with the evidence**, not the diagnosis. Show the sidecar traceback first.
- **Cite paths and seqs**, never vague references like "look at the journal".
- **Distinguish what you verified from what you inferred.** "Sidecar says X" is verified; "I think this caused Y" is inferred.
- **Never claim fixed without Step 7.** If you only changed code and ran no run, the report says "code changed; verification pending".
- **One bug per report.** If the traceback shows two unrelated exceptions, file them separately.

---

## Don'ts (also enforced by sync check)

- ❌ `lca-ops replay <run_id>` — that is not a top-level command. Use `lca-ops journal replay <run_id> --step N` (`--step` is required).
- ❌ `lca-ops diagnose phase-error` — alias removed.
- ❌ `LCA_DEBUG=1` — env var does not exist (replaced by fail-loud).
- ❌ `cat traces/lca_journal.jsonl` — dead path; the journal SSOT is `traces/runs/<id>/events.jsonl`.
- ❌ `cat traces/runs/<id>/kernel.log` and concluding "no kernel log = bug": see Step 1 — most runs don't write one.
- ❌ Patching source + restart as the *first* move. ADR-0122 says one command should locate any bug; if it doesn't, that's a missing ADR, not a missing grep.

---

## Files in `traces/runs/<run_id>/` (what may or may not exist)

| File | | When present |
|---|---|---|
| `events.jsonl` | spine SSOT (ADR-0167) | every run |
| `manifest.json` | `ManifestMaterializer` | every run |
| `profile_snapshot.json` | profile snapshot | every run |
| `journal.json` | step-tree (`lca.journal/3.1`) | only if run reached step tree (early-fail runs lack it) |
| `journal.narrative.md` | `StepNarrativeWriter` | same as `journal.json` |
| `<sha256>.json` | I10 size-offload sidecar (≥ 4 KB event) | only if any event exceeded `_ATOMIC_THRESHOLD` (typical for exception-bearing events) |
| `kernel.log` | `KernelLogProjection` | **mostly absent** — only when kernel flushes explicitly |

---

## Maintenance (must be respected when editing CLI or this doc)

- **This SOP must not lie.** Run `uv run python scripts/check_run_debug_sync.py` after any change to either the CLI or this document. CI should wire this script; if not, wire it.
- **One-directional sync.** New CLI commands are *not* a failure — they appear in `lca-ops --help` and agents discover them. SOP references to commands that no longer exist *are* a failure.
- **Sync mechanism.** The script invokes `./scripts/lca-ops --help` (and `<group> --help` for groups) to read the live command registry, parses the `Commands:` block, and diffs against every `\`lca-ops ...\`` backtick path this SOP contains. CI cost: ~30 s.
- **When you add a command** here, also update `AGENTS.md` §6 if it's a high-frequency command. Don't duplicate the matrix in both files.
- **When you remove/rename a CLI command**, search this SOP for the old name; the sync check will tell you which lines to fix.
- **Sidecar rules and I10 threshold** live in `lca/infrastructure/observability/spine/sinks/file_sink.py:_ATOMIC_THRESHOLD` — if that constant moves or the threshold changes, update Step 3 here.
- **Do not hand-write the command matrix.** If you find yourself listing commands and their arguments here, push back: that's SSOT duplication and the sync check will go stale.