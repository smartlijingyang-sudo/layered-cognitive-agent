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
> **Path convention.** All commands in this SOP are written as
> `./scripts/lca-ops ...`. From anywhere else invoke it as
> `<repo>/scripts/lca-ops ...`. The bare `lca-ops` on `$PATH` is the same
> script; both work.
>
> **SSOT rule.** Commands listed here are kept in sync with the CLI by
> `scripts/check_run_debug_sync.py`. That script asks
> `./scripts/lca-ops --help` (the real registry) what commands exist
> and diffs against every `lca-ops ...` path this SOP mentions. Run it
> in CI; if it fails, this document is lying and you must fix it before
> proceeding. See §Maintenance for details.

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
./scripts/lca-ops status --json
```

**OUTPUT.** JSON with five services: `kernel_serve`, `infra`, `lobehub`, `daemon`, `onlyboxes`. Anything `unhealthy`/`missing`/`not running` → service problem, not run problem.

**NEXT.** If any service is down: `./scripts/lca-ops heal --json`, then re-check. Once `kernel_serve: healthy`, advance to Step 1.

**FAIL.** `./scripts/lca-ops` itself fails → check `which lca-ops`, run with `bash -x ./scripts/lca-ops status --json` to see where it dies.

---

### Step 1 — One-shot 8-section diagnostic

**WHY.** `debug-run` is the canonical "tell me about this run" entry point (ADR-0122). It collects manifest, journal summary, error_ref, stack frames, and a suggested action in one shot.

**DO.**

```sh
# Human-readable (default)
./scripts/lca-ops debug-run "$LATEST"

# You (agent)
./scripts/lca-ops debug-run "$LATEST" --json
```

**OUTPUT.** 8 sections. Important nuances:

- `[1/8] manifest` shows `status` (failed/passed) and `broken_hop` (e.g. `H3` = the 3rd hop in the phase graph). Also `manifest.plan_ref` if present (16-hex stable ID; see `§按 plan 复现` below).
- `[2/8] journal` shows spine event count and `missing_seqs` (gaps in seq numbers).
- `[3/8] kernel.log` is a tail of `traces/runs/<id>/kernel.log`. **Most runs do not have this file** — its absence is *not* evidence of failure loss. (See sidecar step below.)
- `[4/8] phase.cursor` — last completed phase.
- `[5/8] error_ref` — a *typed label* like `node=think.main error_kind=internal attempts=1[1:permanent:ValueError]`. **It is not the traceback.**
- `[6/8] stack frames` — top 8 frames only.
- `[7/8] suggested_action` — human hint.
- `[8/8] plan_ref + replay commands` — `plan_ref` (16-hex from manifest) + multi-line **copy-paste-runnable** commands:
  - `lca-ops journal replay <run_id> --step K --diff-only` (model-visible 重放)
  - `grep -rl <plan_ref> traces/runs/*/manifest.json` (反查同 plan 所有 run)

**NEXT.** If `status=passed` → done; the user is wrong about the failure. If `status=failed`, advance to Step 2.

**FAIL.** `debug-run` errors → Step 0 service problem is real; resolve first.

---

### Step 2 — Read the full spine event flow

**WHY.** Step 1 gives you a label. You need the *evidence* — what the LLM actually saw, what tool calls fired, where the chain broke. There are two views; pick by use case.

**DO.**

```sh
# Default human view (tree indent + payload text + Δms + auto-collapse
# token/reducer noise). Pass this to the user when they ask "走了一遍啥逻辑".
# No run_id = latest run (traces/latest.json pointer, mtime fallback).
./scripts/lca-ops journal trace
./scripts/lca-ops journal trace "$LATEST"   # explicit, equivalent here

# Compact table — control points + channel + outcome. Fast to scan.
./scripts/lca-ops journal logs -r "$LATEST"

# Expand payloads (and surface sidecar traceback when -v finds an
# offloaded event)
./scripts/lca-ops journal logs -r "$LATEST" -v

# You (agent). Pipe to jq, don't try to parse the human tree.
./scripts/lca-ops journal trace "$LATEST" --json
```

**OUTPUT.**

- `journal trace` (default `--human`): a tree with ▸/↳ markers, Δms relative to run start, and folded payload text. Auto-collapses `llm.stream.token`, `runtime.reducer.apply`, paired `transport.route.{enter,exit}`.
- `journal logs` (default): one line per event, columns `time / channel / execution_point / outcome`.
- Both read `traces/runs/<id>/events.jsonl` (spine SSOT, ADR-0167).

**NEXT.** Look at the failure. Find the first event with `outcome=failure` (or the `broken_hop` from Step 1). Note its `seq` number and `execution_point`. Advance to Step 3 to find the exception itself — Step 2 alone won't give you a traceback because exceptions over 4 KB are offloaded.

**FAIL.** `journal.jsonl events=0` but `events.jsonl events=N>0` → the run was early-fail, the step-tree never materialized. That's expected for early failures. Don't run `journal steps` (it'll say `journal.json not found`); go straight to sidecar. If the ledger itself is empty or a whole EP family is missing (e.g. no `brain.think.*` rows), check the bus delivery counters with `./scripts/lca-ops events-delivery --json` — per-category `published / persisted / delivered / dropped`, where `dropped > 0` means sent-but-neither-persisted-nor-dispatched (ADR-0184 D2; counters are EventBus in-process memory of the invoking process).

---

### Step 3 — Read the traceback from `<run_id>.exceptions.jsonl` (preferred) or sidecar

**WHY.** Since ADR-2026-09-03 traceback-ssot-hook, every `exception.caught` event is double-written:
- **Dedicated index**: `<run_id>.exceptions.jsonl` — one JSON line per exception, full payload. **Preferred** for grep.
- **Spine ledger**: `<run_id>.spine.jsonl` — main event log, exception rows are placeholder `{execution_point, offloaded}` if > 4 KiB.
- **Offloaded sidecar**: `<sha8>-<SafeClass>.json` (e.g. `1a2b3c4d-AttributeError.json`) — readable name, holds the full encoded event for offloaded exceptions.

`debug-run [5/8] error_ref` only carries the label, not the traceback. If you skip this step, you're guessing.

**DO.**

```sh
# Preferred: dedicated exceptions index (every exception EP, full payload).
./scripts/lca-ops journal exceptions "$LATEST"

# Or grep by class:
./scripts/lca-ops journal exceptions "$LATEST" --grep AttributeError

# Or agent-friendly JSON:
./scripts/lca-ops journal exceptions "$LATEST" --json | jq '.records[0].payload'

# Manual jq on the index file:
jq -r 'select(.payload.exception_class=="AttributeError") | .payload.traceback_text' \
  traces/runs/"$LATEST"/"$LATEST".exceptions.jsonl

# Sidecars (readable names) — only for offloaded exceptions > 4 KiB.
ls traces/runs/"$LATEST" | grep -E '^[0-9a-f]{8}-[A-Za-z]+\.json$'

# Pick a sidecar and dump its traceback.
SIDECAR=$(ls traces/runs/"$LATEST"/[0-9a-f]*-*.json 2>/dev/null | head -1)
[ -n "$SIDECAR" ] && jq -r '
  "exception_class:   \(.payload.exception_class // "-")",
  "exception_message: \(.payload.exception_message // "-")",
  "source_location:   \(.payload.source_location // "-")",
  "---traceback---",
  (.payload.traceback_text // "(no traceback_text)")
' "$SIDECAR"

# Last-resort: FALLBACK.log fires only when main ledger AND exceptions index both failed.
# Its presence indicates a serious I/O problem (disk full / perms / FS gone).
[ -f traces/runs/"$LATEST"/FALLBACK.log ] && cat traces/runs/"$LATEST"/FALLBACK.log
```

**OUTPUT.** The exact `ValueError` / `RuntimeError` / etc., the file:line where it raised, and the full Python traceback.

**NEXT.** You now have the exception class + message + source. Advance to Step 4.

**FAIL.** No exceptions file and no sidecar → the failure was a control-point failure (outcome=failure, no Python traceback). Read the event payload from `<run_id>.spine.jsonl` directly: `jq -r 'select(.seq==N) | .payload' traces/runs/"$LATEST"/"$LATEST".spine.jsonl`.

---

### Step 4 — Fail-path projection

**WHY.** Step 3 gives you *what* threw. Step 4 gives you *why the system decided to stop* — the causal chain from leaf cause up to the StopDecision.

**DO.**

```sh
./scripts/lca-ops explain "$LATEST"           # human
./scripts/lca-ops explain "$LATEST" --json    # you (agent)
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
| Tool bypassed Body (sandbox/transport direct import) | audit with `./scripts/lca-ops audit-direct-commands` |
| Hook re-introduced where forbidden | `./scripts/lca-ops audit-hook-attach` |
| Side effect without reducer first | Body / SafeExecutor |
| Profile topology missing a provides/requires | `./scripts/lca-ops inspect-tree <profile>` then `./scripts/lca-ops why-plugin <id>` |

If you find the failure root cause is *not* a single missing line (e.g. protocol mismatch, missing ADR) → escalate to Step 6 (diff against a passing run).

**FAIL.** Code is unclear → Step 6.

---

### Step 6 — Diff against a passing run (optional, for non-obvious bugs)

**WHY.** When the traceback is "obvious" but the *reason* isn't (the code path always ran before; why did it fail now?), the fastest disambiguation is a passing run from yesterday.

```sh
./scripts/lca-ops diff-runs <failing_id> <passing_id>
./scripts/lca-ops diff-context <failing_id> --step N
```

For narrower comparisons, `optimize <run_id>` ranks candidates by latency/token/retries; `cost <run_id>` shows the LLM spend.

**NEXT.** If diff reveals a profile/prompt/bundle change → that change is the regression. If diff is empty → random non-determinism (LLM, network); not a code fix.

---

### Step 6.5 — Acknowledge the live-kernel invariant (READ BEFORE Step 7)

**WHY.** LCA 的 kernel 是常驻 Python 进程(`uv run lca_kernel serve`,
PID/port 用 `./scripts/lca-ops status` 查)。所有 spine deriver、LLM adapter、
facade、命令 handler 都是 kernel 进程内 import 的对象 —— **修改 `lca/` /
`lca_kernel/` 任何文件不重启,对线上 run 不生效**。`pytest` 跑的是隔离逻辑,
绕开 kernel,不等于"线上生效"。

**何时一定要 kernel-restart:**

- 修改 `lca/` 内任何 `.py`(除纯 `tests/` + CLI 单文件测试)。
- 修改 `lca_kernel/` 内任何 `.py`。
- 修改 Profile / Bundle / Plugin / Manifest 配置。
- 修改 spine 的 deriver / sink / sundry reflective plugins —— 这些是
  runtime-loaded,改了不重启不会重新 import。

**何时不需要 kernel-restart:**

- 改 docs / Agent Notes / tests:`pytest` 验证即可。
- 改 CLI 单文件测试:`pytest tests/cli/...` 已能验证。
- 改 Profile YAML:`kernel-restart` 还是会重新加载它。

**DO.**

```sh
# Step 6.5 在 Step 7 之前的状态核查
./scripts/lca-ops status --json | jq '.services[] | select(.name=="kernel_serve") | .pid'
# 记下 PID;kernel-restart 后 PID 会变,PID 不变 ⇒ 老进程仍在跑。
```

**FAIL.** PID 不变 ⇒ restart 没生效。运行 `lca-ops logs` 看 boot 摘要,
确认 `<pid>` 与新 spawn 一致。

---

### Step 7 — Verify the fix on the live system (do not skip)

**WHY.** Debugging is read-only. *Verifying* the fix requires a new run. Don't tell the user "fixed" until you've reproduced.

**DO.**

```sh
# If you changed code:
./scripts/lca-ops kernel-restart --json

# Then re-trigger the run via the same path the user used.
# (Run via API / scenario file / curl — whatever the user's flow is.)

# Then re-enter this SOP at Step 1 with the new run_id.
LATEST2=$(jq -r .run_id traces/latest.json)
./scripts/lca-ops debug-run "$LATEST2" --json
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
# Tree with payloads + Δms (default --human).
# No run_id = latest run; pass $LATEST to be explicit.
./scripts/lca-ops journal trace
./scripts/lca-ops journal trace "$LATEST"

# narrative.md story
./scripts/lca-ops journal narrative "$LATEST"

# DSH-style HTML trajectory
./scripts/lca-ops journal trajectory "$LATEST"        # → traces/runs/<id>/journal.trajectory.html
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

- ❌ `lca-ops replay <run_id>` — that is not a top-level command. Use `./scripts/lca-ops journal replay <run_id> --step N` (`--step` is required). There is no `--no-llm` flag because journal replay only dumps messages + actions and never calls the LLM — that mode is already the default.
- ❌ `/v1/chat/completions` to "trigger a run" — it's a LobeHub UI proxy (ADR-0099) that streams OpenAI-compatible chunks **without** registering a run_id or writing `traces/runs/<id>/`. If you want a debuggable run, use `lca-ops runs create` (CLI) or `POST /runs` (HTTP).
- ❌ `lca-ops diagnose phase-error` — alias removed.
- ❌ `LCA_DEBUG=1` — env var does not exist (replaced by fail-loud).
- ❌ `cat traces/lca_journal.jsonl` — dead path; the journal SSOT is `traces/runs/<id>/events.jsonl`.
- ❌ `cat traces/runs/<id>/kernel.log` and concluding "no kernel log = bug": see Step 1 — most runs don't write one.
- ❌ Patching source + restart as the *first* move. ADR-0122 says one command should locate any bug; if it doesn't, that's a missing ADR, not a missing grep.

## How to trigger a run (canonical entry point)

The LCA carrier has exactly **one** run-creation seam: `POST /runs`
(`handlers/runs/api/command_endpoints.create_run`). It allocates the
`run_id`, registers the session, and starts the agent loop. Everything
else in `traces/runs/<id>/` (manifest, profile_snapshot, spine.jsonl,
sidecars) is downstream of that one call.

```sh
# CLI (preferred for coding agents):
lca-ops runs create --user-text "请把昨日的 csv 按 region 汇总"

# HTTP (for shell scripts / external integrations):
# 等价于浏览器 LobeHub 会发的请求 —— 走 Next rewrite `/lca-api/runs` → gateway `/runs`。
curl -X POST "${LCA_FRONTEND_URL:-http://127.0.0.1:3010}/lca-api/runs" \
  -H "Authorization: Bearer ${LCA_TOKEN:-lca-local}" \
  -H 'Content-Type: application/json' \
  -d '{
    "messages": [{"role": "user", "content": "..."}],
    "mode": "solo",
    "agent": {"id": "agt_aVxY6ag9MbMc", "name": "..."},
    "profile": "web-standard"
  }'
# → {"run_id": "...", "trace_id": "...", "live_url": "/runs/<id>/live"}
```

After dispatch, immediately query the terminal state with
`lca-ops debug-run <run_id>` (8 sections, including the new
`plan_ref` + runnable replay commands in `[8/8]`) or stream
`lca-ops journal trace <run_id>` for the human-readable tree view.

> **Why this is not `/v1/chat/completions`:** that endpoint exists for
> the LobeHub Next.js UI (ADR-0099). It accepts OpenAI-shaped payloads
> and returns OpenAI-shaped chunks, but **does not** write any
> `traces/runs/<id>/` artifact. Hitting it as if it were "the run API"
> silently produces zero debug evidence — the most common
> "I asked the kernel to do X and got nothing" failure. If you need a
> run you can debug-run, you must go through `POST /runs`.

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
| `kernel.log` | `record_run_failure` (terminal failure fallback) | **mostly absent** — written only when the run's finishing path itself failed; a single best-effort line, not an internals log |

---

## Maintenance (must be respected when editing CLI or this doc)

- **This SOP must not lie.** Run `uv run python scripts/check_run_debug_sync.py` after any change to either the CLI or this document. CI should wire this script; if not, wire it.
- **One-directional sync.** New CLI commands are *not* a failure — they appear in `./scripts/lca-ops --help` and agents discover them. SOP references to commands that no longer exist *are* a failure.
- **Sync mechanism.** The script invokes `./scripts/lca-ops --help` (and `<group> --help` for groups) to read the live command registry, parses the `Commands:` block, and diffs against every `` `lca-ops …` `` backtick path this SOP contains. The path prefix `./scripts/` is optional in the SOP — both `` `./scripts/lca-ops debug-run` `` and `` `lca-ops debug-run` `` are matched. CI cost: ~30 s.
- **When you add a command** here, also update `AGENTS.md` §6 if it's a high-frequency command. Don't duplicate the matrix in both files.
- **When you remove/rename a CLI command**, search this SOP for the old name; the sync check will tell you which lines to fix.
- **Sidecar rules and I10 threshold** live in `lca/infrastructure/observability/spine/sinks/file_sink.py:_ATOMIC_THRESHOLD` — if that constant moves or the threshold changes, update Step 3 here.
- **Do not hand-write the command matrix.** If you find yourself listing commands and their arguments here, push back: that's SSOT duplication and the sync check will go stale.