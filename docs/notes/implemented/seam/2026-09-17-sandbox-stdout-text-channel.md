# Agent Note: Sandbox stdout is a text channel

Status: implemented

## Problem

`executeCode` on `run_e5077cf26ecd` never ran the user's Python. Mount verify printed a JSON control document, then a leftover PDF from `/mnt/data/outputs` as a base64 block on the same stdout. The host parsed the last line, got `<parse error>`, and returned `预期挂载缺失`. The 103k dump went into the next tool observation. The following think prompt jumped to 157k tokens. The model then spent 184s writing a reportlab script that still could not execute. The chat showed almost no tool cards while that call streamed arguments.

Stdout was carrying two jobs: program text and file bytes. Those jobs collide when a previous run left files in `outputs/`, when the pipe truncates, and when the model reads the tool result.

## Decision

`RunBoundSandboxRuntime` keeps three guest executions distinct:

- Probe (`_execute_probe`): mount verify and inspect. `harvest_artifacts=False`. Host parses the first JSON object that has a `missing` key (`parse_mount_verify_stdout`).
- User `execute`: always `harvest_artifacts=False`. `stdout` / `stderr` are the program's text.
- Harvest (`_HARVEST_STUB` + `GUEST_ARTIFACT_SCANNER`): after a successful ready, `scan_output_files` fingerprints whatever already sits in `outputs/` (`_baseline_outputs`). Later `harvest_output_delta` publishes only new or changed files into `SandboxResult.generated_files`.

`generated_files` remains the file SSOT (ADR-0046). The scanner still exists for the harvest stub. It is not appended to user code or to JSON probes.

## Alternatives considered

### Why not only set `harvest_artifacts=False` on mount verify?

That stops the parse error on the probe. The next `executeCode` still prints leftover PDF bytes onto user stdout. Truncation, 100k tool results, and context poisoning remain.

### Why not wipe `outputs/` at `ensure_ready`?

A persistent worker may hold files the user still wants. Fingerprinting at ready treats them as not this run's deliverables. A later write with a new hash still publishes.

### Why not keep last-line JSON parse and raise the stdout cap?

Last-line parse assumes stdout is a single control document. A file bus on the same pipe makes that assumption false. A larger cap still ships binary through the model context.

## Consequences

`executeCode` can pass mount verify when `outputs/` already contains a PDF. Tool observations no longer carry leftover file bytes as stdout. New files written in this run still harvest. Probe and harvest each cost one extra Python exec per ready / execute.

## Verification

- `tests/scenario/sandbox_1/test_mount_verify_stdout.py`
- `tests/scenario/sandbox_1/test_sandbox_runtime.py` (`TestOutputChannelSplit`, harvest flag)
