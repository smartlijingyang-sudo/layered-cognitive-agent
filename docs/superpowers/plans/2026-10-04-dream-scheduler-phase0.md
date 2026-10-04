# Dream Scheduler (Phase 0 Condition 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `run_dream` a real periodic scheduler so the offline memory track runs without a human typing a CLI command, which is the blocking precondition for moving LLM memory distillation offline.

**Architecture:** A dedicated plugin-hosted background loop following the already-running `AvatarCostumeScheduler` pattern (`lca/plugins/avatar/plugin.py:302-312`). Each tick sweeps every assistant home, takes a per-assistant `RoutineFileLock`, and calls the synchronous `run_dream` off the event loop via `asyncio.to_thread`. Evidence is a file artifact under `{home}/dreams/`, not a new execution point.

**Tech Stack:** Python 3.12, asyncio, pydantic v2 (frozen config models), Cordis `@plugin` harness, pytest.

**Spec:** `docs/adr/0287-semantic-memory-single-online-writer.md` §D5 Phase 0, with `docs/notes/proposed/seam/2026-10-04-semantic-memory-single-online-writer.md` §交付门禁 as the argument母体. This plan implements **Phase 0 condition 1 only**. Condition 2 (the online residual-capture path) is blocked on ADR-0287 Open question 5 and is a separate plan.

---

## Why the carrier is a plugin loop and not cron or routines

ADR-0287 §4 Phase 0 names two carriers: "`{home}/routines/` 或 0268 CronJob 有 `run_dream` 条目". Neither can work. This section is the evidence, and it is the reason this plan exists in this shape. **ADR-0287 §4 Phase 0 must be amended to name the plugin loop before Task 4 lands.**

| Blocker | Evidence | Consequence |
|---|---|---|
| B1 no execution kind can call a Python function | `CronJob.execution` is a closed union `AgentExecution \| SpaceActionExecution` (`lca/contracts/models/cron/models.py:152`, `extra="forbid"` at `:144`); `CronWorkerRunner.execute_job` (`lca/infrastructure/cron/worker_runner.py:98-200`) delivers only a chat card or an avatar artifact | Adding a kind is a closed-set contract change, ADR-first under AGENTS.md §1 row 3 |
| B2 periodic schedules never fire | `next_run` decides `due` by exact `datetime` equality including microseconds (`lca/domain/cron/next_run.py:81-86` interval, `:90-94` hourly, `:101-106` daily, `:112-118` weekly). The daemon samples an unaligned `datetime.now(UTC)` (`lca/infrastructure/cron/daemon.py:44`, `:106`) after `asyncio.sleep` (`:123`). Measured: an `every_seconds=5` job fired 0 times across 30 real-clock seconds at 1s ticks while a `oneshot` in the same store fired once. All 7 production jobs under `/home/lichao/.lca/assistants/*/cron/` are `oneshot` | A minutes-level cadence is unreachable on this scheduler. Fixing it changes an ADR-specified pure function (ADR-0268 §232-233), so it needs an ADR-0268 amendment. File separately |
| B3 no system-level registration and no cadence config surface | No boot seed (`lca_kernel/boot/lifespan.py:69-100` starts the daemon, never writes a job), no creation-time seed, zero `cron\|routine\|dream` hits across all 14 `profiles/*.yaml`. `{home}/routines/*.yaml` is only counted (`lca/plugins/domain/assistant/catalog/manifest.py:82`), never parsed. `RoutineSpec` has no callable field (`lca/contracts/models/routine/models.py:8-43`) | The cadence upper bound ADR-0287 §4 requires "写在调度配置里" has nowhere to live today. Task 4 creates it |
| B6 blocking I/O in an async seam | `run_dream` is synchronous (`lca/infrastructure/memory/dream.py:217`) | Must go through `asyncio.to_thread` or it stalls the kernel serving `:8765` |

The cron daemon itself is real and running: `lca_kernel/boot/lifespan.py:69-100` constructs `CronDaemonService` with `MultiAssistantCronStore`, installed at `lca/plugins/transport/webserver/server/server.py:158`, and `/home/lichao/.lca/locks/cron.lock` cycles every ~15.3s owned by the live kernel PID. The daemon is healthy; the schedule predicate and the execution union are what block us.

Routines are not a carrier either, and ADR-0263 now says so itself. It was accepted 2026-10-05 with the caveat "**Accepted≠Implemented，C1–C5 实施另行排期**". `RoutineSpec` requires a non-empty `prompt: str` and has no callable field (`lca/contracts/models/routine/models.py`), so hosting dream there means spending an LLM turn per assistant per interval to do deterministic file work. `RoutineTickDriver` still has zero callers outside `lca/application/routine/`.

The plugin loop needs neither contract change. It is not constrained by the `CronJob` union and never routes through `next_run`.

## Global Constraints

Every task's deliverable implicitly satisfies these. Values are copied from the spec and the code they cite.

| Constraint | Value | Source |
|---|---|---|
| Lock primitive | Reuse `RoutineFileLock(lock_dir, routine_id, stale_after_s=None, routine_interval_s=None)`. Do not write a third lock implementation | `lca/application/routine/locks.py:58-69`; ADR-0278 §3 待拍板① records routine and cron already duplicate lock semantics |
| Lock granularity | One lock per assistant home, not one global lock, so a slow home does not block the sweep | `lca/application/routine/locks.py:87` `acquire()` is atomic `O_CREAT\|O_EXCL`, returns `False` without queueing |
| Event-loop discipline | `run_dream` runs via `asyncio.to_thread`. Never call it inline in the tick | B6 above |
| Determinism (C8) | Time enters through an injected `Callable[[], int]` clock. No `time.time()` inside the scheduler | AGENTS.md §3 C8 |
| No new execution point (C11) | Phase 0 evidence is a file artifact. A new EP needs whitelist + SpineHandler + test + ADR | AGENTS.md §3 C11 |
| Plugin shape | One `.py` per plugin, `@plugin(...)` is the only entry, `effects` declared, `setup()` calls only Manifest-declared provide/require/register/emit | AGENTS.md §5 Plugin 硬约束 |
| Cadence in config | The interval upper bound lives in the plugin `Config` and is set in a profile YAML, not in prose | ADR-0287 §4 Phase 0 |
| `run_dream` signature | `run_dream(home: Path, *, now_ms: int, backfill: _Backfill \| None, render: _Render \| None = None) -> DreamReport` where `_Backfill = Callable[[str, list[MemoryRecord]], object]` and `_Render = Callable[[Sequence[MemoryRecord]], str]` | `lca/infrastructure/memory/dream.py:50-51`, `:217-223` |
| Callback construction | Build `ProfileBackfillService(catalog)` from a resolved catalog capability and use `render_user_profile` as render. Do not replicate the CLI's private import of `_AssistantCatalogImpl` | `lca/infrastructure/cli/commands/ops/memory.py:28-50` |
| Validation gate | `./scripts/lca-ops audit-plugin-shape` after any plugin or bundle change | AGENTS.md §5 |
| Baseline gate protocol | `lint-imports` and `check_package_contracts.py` have pre-existing failures. Report 本次引入 vs 既有失败 separately; only exit-0 commands may be called 通过 | AGENTS.md §6 |

## File Structure

| File | Responsibility |
|---|---|
| `lca/application/memory/dream_scheduler.py` (create) | The sweep loop: interval bookkeeping, home fan-out, per-home lock, off-loop `run_dream`, evidence write. No plugin imports, no Cordis dependency |
| `lca/plugins/memory/dream_scheduler/plugin.py` (create) | The `@plugin` entry: config parse, catalog resolution, callback construction, `asyncio.create_task`, LIFO dispose |
| `bundles/assistant-runtime.yaml` (modify) | Declare the plugin id so the profile that binds assistant homes loads it |
| `profiles/web-assistant.yaml` (modify) | Set `tick_seconds`, putting the cadence upper bound in configuration |
| `tests/application/memory/test_dream_scheduler.py` (create) | Loop, fan-out, lock, collision, evidence, change detection |
| `tests/plugins/test_dream_scheduler_plugin_shape.py` (create) | Plugin shape and dispose registration |
| `tests/scenario/memory/test_dream_scheduler_live_sweep.py` (create) | End-to-end Phase 0 evidence against real homes |

`dream_scheduler.py` lives in `lca/application/memory/` because it needs `RoutineFileLock` from `lca/application/routine/locks`, and `pyproject.toml:82-92` contract 2 forbids `lca.infrastructure` from importing `lca.application`. `application` is the composition root, so it may import its own layer and downward into `lca.infrastructure.memory.dream`. The package needs an `__init__.py`: without one grimp treats the directory as a namespace package and skips it, which would leave the module outside layering enforcement entirely. The plugin file is the only place that touches the harness.

---

### Task 1: The sweep loop with an injected clock

**Files:**
- Create: `lca/application/memory/dream_scheduler.py`
- Test: `tests/application/memory/test_dream_scheduler.py`

**Interfaces:**
- Consumes: `run_dream` from `lca.infrastructure.memory.dream`; `RoutineFileLock` from `lca.application.routine.locks`.
- Produces: `DreamScheduler(homes: Callable[[], Sequence[Path]], *, lock_dir: Path, tick_seconds: int, now_ms: Callable[[], int], run_dream_fn: DreamFn, evidence_writer: EvidenceWriter)` with `async def run_forever() -> None`, `def stop() -> None`, and `async def sweep_once() -> tuple[DreamReport | None, ...]`. `DreamFn = Callable[..., DreamReport]`. Later tasks rely on `sweep_once` being separately awaitable so tests never sleep.

- [ ] **Step 1: Write the failing test**

```python
# tests/application/memory/test_dream_scheduler.py
from pathlib import Path

import pytest

from lca.application.memory.dream_scheduler import DreamScheduler


@pytest.fixture
def clock() -> list[int]:
    return [1_791_121_000_000]


def _scheduler(tmp_path: Path, homes: list[Path], clock: list[int], calls: list[Path]):
    def fake_run_dream(home, *, now_ms, backfill, render):
        calls.append(home)
        return None

    return DreamScheduler(
        homes=lambda: homes,
        lock_dir=tmp_path / "locks",
        tick_seconds=300,
        now_ms=lambda: clock[0],
        run_dream_fn=fake_run_dream,
        evidence_writer=lambda home, report, now_ms: None,
    )


async def test_sweep_once_visits_every_home(tmp_path: Path, clock: list[int]) -> None:
    homes = [tmp_path / "a", tmp_path / "b"]
    calls: list[Path] = []
    scheduler = _scheduler(tmp_path, homes, clock, calls)

    await scheduler.sweep_once()

    assert calls == homes


async def test_interval_skips_a_sweep_that_is_not_due_yet(
    tmp_path: Path, clock: list[int]
) -> None:
    calls: list[Path] = []
    scheduler = _scheduler(tmp_path, [tmp_path / "a"], clock, calls)

    await scheduler.sweep_once()
    await scheduler.sweep_once()

    assert calls == [tmp_path / "a"], "second sweep is inside the 300s interval"

    clock[0] += 300_000
    await scheduler.sweep_once()

    assert calls == [tmp_path / "a", tmp_path / "a"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/application/memory/test_dream_scheduler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lca.application.memory.dream_scheduler'`

- [ ] **Step 3: Write minimal implementation**

```python
# lca/application/memory/dream_scheduler.py
"""Periodic sweep that runs the offline memory consolidation per assistant home.

The loop keeps its own interval bookkeeping. It does not route through
``next_run``: that function decides ``due`` by exact ``datetime`` equality
including microseconds, which a discrete tick sampling a continuous clock never
satisfies, so every periodic schedule kind is unreachable there.

``run_dream`` is synchronous and does file I/O, so the sweep dispatches it off
the event loop. The kernel process serves HTTP on the same loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from lca.application.routine.locks import RoutineFileLock
from lca.infrastructure.memory.dream import DreamReport, run_dream

logger = logging.getLogger(__name__)

_Backfill = Callable[[str, list], object]
_Render = Callable[[Sequence], str]
DreamFn = Callable[..., DreamReport]
EvidenceWriter = Callable[[Path, DreamReport | None, int], object]

_ROUTINE_ID = "memory_dream"


class DreamScheduler:
    """Sweep every assistant home once per ``tick_seconds``."""

    def __init__(
        self,
        homes: Callable[[], Sequence[Path]],
        *,
        lock_dir: Path,
        tick_seconds: int,
        now_ms: Callable[[], int],
        run_dream_fn: DreamFn = run_dream,
        evidence_writer: EvidenceWriter | None = None,
        callbacks: Callable[[Path], tuple[_Render | None, _Backfill | None]] | None = None,
    ) -> None:
        self._homes = homes
        self._lock_dir = Path(lock_dir)
        self._tick_seconds = tick_seconds
        self._now_ms = now_ms
        self._run_dream = run_dream_fn
        self._evidence_writer = evidence_writer
        self._callbacks = callbacks
        self._stop = asyncio.Event()
        self._next_due_ms: int | None = None

    def stop(self) -> None:
        """Signal the loop to exit at its next check. Idempotent."""
        self._stop.set()

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                await self.sweep_once()
            except Exception:
                logger.exception("dream sweep failed")
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=float(self._tick_seconds)
                )
            except TimeoutError:
                continue

    async def sweep_once(self) -> tuple[DreamReport | None, ...]:
        """Run one pass over every home. Returns one report per home, None when skipped."""
        now = self._now_ms()
        if self._next_due_ms is not None and now < self._next_due_ms:
            return ()
        self._next_due_ms = now + self._tick_seconds * 1000
        reports: list[DreamReport | None] = []
        for home in self._homes():
            reports.append(await self._run_home(Path(home), now))
        return tuple(reports)

    async def _run_home(self, home: Path, now_ms: int) -> DreamReport | None:
        lock = RoutineFileLock(
            self._lock_dir,
            f"{_ROUTINE_ID}:{home.name}",
            routine_interval_s=float(self._tick_seconds),
        )
        if not lock.acquire():
            logger.info("dream skipped, home locked: %s", home.name)
            return None
        try:
            render, backfill = (
                self._callbacks(home) if self._callbacks is not None else (None, None)
            )
            report = await asyncio.to_thread(
                self._run_dream,
                home,
                now_ms=now_ms,
                backfill=backfill,
                render=render,
            )
        finally:
            lock.release()
        if self._evidence_writer is not None:
            self._evidence_writer(home, report, now_ms)
        return report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/application/memory/test_dream_scheduler.py -v`
Expected: PASS, 2 tests

- [ ] **Step 5: Commit**

```bash
git add lca/application/memory/dream_scheduler.py tests/application/memory/test_dream_scheduler.py
git commit -m "feat(memory): add the dream sweep loop with an injected clock"
```

---

### Task 2: Lock contention and write collision

**Superseding ruling (R16, R17).** The `_run_home` body specified below is replaced, not merely extended. Task 1's review found that `RoutineFileLock.acquire()` returns `False` whenever the lock file exists, stale or not (`lca/application/routine/locks.py:93-95`), and that nothing calls `reclaim_stale()`. After a `kill -9`, an OOM, or a `kernel-restart` escalating to SIGKILL mid-dream, the lock file survives with the dead pid in its owner string, so a restarted kernel cannot release it and that assistant home never dreams again until a human deletes the file. The failure is permanent and logged only at INFO. The review also found that `asyncio.to_thread` does not make executor threads interruptible, so a `CancelledError` at the await runs the `finally`, releases the lock, and leaves `run_dream` executing unlocked.

The replacement structure hands one synchronous function to `asyncio.to_thread` that performs, in order: `reclaim_stale()` and log a WARNING carrying `previous_owner` and `held_ms` when it returns non-`None`; `acquire()`; `run_dream`; the evidence write; `release()`, logging when it returns `False`. This binds the lock's lifetime to the work rather than to the await, puts every file operation including `mkdir` and `os.open` off the event loop, and places the evidence write inside the mutual exclusion guarding the run that produced it. It resolves the reclaim gap, the discarded `release()` result, the cancellation window, and the evidence placement in one change.

`sweep_once` also gains per-home containment around the whole `_run_home` call. Today one home raising aborts the rest of the sweep, so a single corrupt home silently starves every home after it in catalog order. A failing home yields `None` and logs; the sweep continues.

The three tests below stay as the required behaviour, and gain a fourth asserting that a stale lock from a dead pid is reclaimed rather than skipped, and a fifth asserting that one home raising does not prevent the next home from being visited.

A minutes-level timer makes collision with a live user turn routine rather than theoretical. Both the online memory tools and `run_dream` rewrite `{home}/memory/semantic.json` with a non-atomic `write_text` (`lca/infrastructure/memory/assistant_memory.py:215`), and the only guard is `StaleSnapshotOperationError` at `:213`, which aborts rather than waits. `run_dream` does not catch it, so a collision today leaves a half-promoted pass with no receipt.

**Files:**
- Modify: `lca/application/memory/dream_scheduler.py` (`_run_home`)
- Test: `tests/application/memory/test_dream_scheduler.py`

**Interfaces:**
- Consumes: `DreamScheduler._run_home` from Task 1; `StaleSnapshotOperationError` from `lca.infrastructure.memory.contextfiles.domain.edit`.
- Produces: `_run_home` returns `None` and logs when the lock is held or when the write collides. Task 5's live test asserts a held lock leaves the home's artifacts untouched.

- [ ] **Step 1: Write the failing test**

```python
# appended to tests/application/memory/test_dream_scheduler.py
from lca.application.routine.locks import RoutineFileLock
from lca.infrastructure.memory.contextfiles.domain.edit import StaleSnapshotOperationError


async def test_a_held_lock_skips_the_home(tmp_path: Path, clock: list[int]) -> None:
    home = tmp_path / "a"
    calls: list[Path] = []
    scheduler = _scheduler(tmp_path, [home], clock, calls)
    holder = RoutineFileLock(tmp_path / "locks", f"memory_dream:{home.name}")
    assert holder.acquire() is True

    await scheduler.sweep_once()

    assert calls == []
    holder.release()


async def test_a_write_collision_is_contained_not_raised(
    tmp_path: Path, clock: list[int]
) -> None:
    def colliding(home, *, now_ms, backfill, render):
        raise StaleSnapshotOperationError("semantic.json changed during edit")

    scheduler = DreamScheduler(
        homes=lambda: [tmp_path / "a"],
        lock_dir=tmp_path / "locks",
        tick_seconds=300,
        now_ms=lambda: clock[0],
        run_dream_fn=colliding,
    )

    reports = await scheduler.sweep_once()

    assert reports == (None,)


async def test_the_lock_is_released_after_a_collision(tmp_path: Path, clock: list[int]) -> None:
    def colliding(home, *, now_ms, backfill, render):
        raise StaleSnapshotOperationError("semantic.json changed during edit")

    scheduler = DreamScheduler(
        homes=lambda: [tmp_path / "a"],
        lock_dir=tmp_path / "locks",
        tick_seconds=300,
        now_ms=lambda: clock[0],
        run_dream_fn=colliding,
    )
    await scheduler.sweep_once()

    after = RoutineFileLock(tmp_path / "locks", f"memory_dream:a")
    assert after.acquire() is True, "a collided pass must not strand its lock"
    after.release()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/application/memory/test_dream_scheduler.py -v -k "collision or held_lock"`
Expected: `test_a_held_lock_skips_the_home` PASSES (Task 1 already locks), `test_a_write_collision_is_contained_not_raised` FAILS with `StaleSnapshotOperationError` propagating out of `sweep_once`

- [ ] **Step 3: Contain the collision in `_run_home`**

Replace the `try:` / `finally:` body of `_run_home` in `lca/application/memory/dream_scheduler.py` with:

```python
        try:
            render, backfill = (
                self._callbacks(home) if self._callbacks is not None else (None, None)
            )
            report = await asyncio.to_thread(
                self._run_dream,
                home,
                now_ms=now_ms,
                backfill=backfill,
                render=render,
            )
        except StaleSnapshotOperationError:
            # An online memory tool rewrote semantic.json mid-pass. The next
            # sweep re-reads from disk, so abandoning this pass loses nothing.
            logger.warning("dream pass abandoned, semantic.json moved: %s", home.name)
            return None
        except OSError:
            logger.exception("dream pass failed on I/O: %s", home.name)
            return None
        finally:
            lock.release()
```

Add to the imports at the top of the module:

```python
from lca.infrastructure.memory.contextfiles.domain.edit import StaleSnapshotOperationError
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/application/memory/test_dream_scheduler.py -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
git add lca/application/memory/dream_scheduler.py tests/application/memory/test_dream_scheduler.py
git commit -m "fix(memory): contain dream write collisions instead of stranding the pass"
```

---

### Task 3: File-based run evidence and change detection

ADR-0287 §4 Phase 0 requires "真实触发证据". A new execution point would need a whitelist entry, a SpineHandler, a test, and an ADR (C11), so the evidence is a file. `run_dream` emits nothing today, and its `backfill` reaches `revise_profile`, whose `assistant.profile.revised` EP is already dropped without an emitter.

Change detection matters because every pass unconditionally rewrites `ALIGNMENT_SYNTHESIS.md` (`dream.py:266`), the people and groups indexes (`:265`), and the FTS index (`:269`). At a 5-minute cadence across 528 homes that is roughly 150k file rewrites per day for passes that promote nothing.

**Files:**
- Modify: `lca/application/memory/dream_scheduler.py`
- Test: `tests/application/memory/test_dream_scheduler.py`

**Interfaces:**
- Consumes: `DreamReport` from `lca.infrastructure.memory.dream` (fields `promoted: tuple[str, ...]`, `upserted: int`, `trail_facts: int`, `synthesis_written: bool`, `index_documents: int`).
- Produces: `write_dream_evidence(home: Path, report: DreamReport | None, now_ms: int) -> Path | None`, writing `{home}/dreams/last_run.json`. Returns `None` when the report shows no change and a previous evidence file already exists. Task 4 passes this as `evidence_writer`.

- [ ] **Step 1: Write the failing test**

```python
# appended to tests/application/memory/test_dream_scheduler.py
import json

from lca.infrastructure.memory.dream import DreamReport
from lca.application.memory.dream_scheduler import write_dream_evidence


def _report(**overrides) -> DreamReport:
    base = {
        "promoted": (),
        "upserted": 0,
        "preimage": None,
        "user_md_written": False,
        "trail_facts": 0,
        "people_indexed": 0,
        "groups_indexed": 0,
        "synthesis_written": False,
        "synthesis_path": "",
        "synthesis_assertions": 0,
        "index_documents": 0,
    }
    base.update(overrides)
    return DreamReport(**base)


def test_evidence_records_a_promoting_pass(tmp_path: Path) -> None:
    report = _report(promoted=("preference:verbosity",), upserted=1)

    path = write_dream_evidence(tmp_path, report, 1_791_121_000_000)

    assert path == tmp_path / "dreams" / "last_run.json"
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["upserted"] == 1
    assert written["promoted"] == ["preference:verbosity"]
    assert written["now_ms"] == 1_791_121_000_000


def test_a_no_change_pass_does_not_rewrite_existing_evidence(tmp_path: Path) -> None:
    first = write_dream_evidence(tmp_path, _report(upserted=1), 1_000)
    stamp = first.stat().st_mtime_ns

    second = write_dream_evidence(tmp_path, _report(), 2_000)

    assert second is None
    assert first.stat().st_mtime_ns == stamp
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/application/memory/test_dream_scheduler.py -v -k evidence`
Expected: FAIL with `ImportError: cannot import name 'write_dream_evidence'`

- [ ] **Step 3: Write the implementation**

Append to `lca/application/memory/dream_scheduler.py`:

```python
_EVIDENCE_RELATIVE = ("dreams", "last_run.json")


def _changed(report: DreamReport) -> bool:
    """True when this pass moved a fact or rebuilt a derived artifact."""
    return bool(
        report.upserted
        or report.promoted
        or report.user_md_written
        or report.synthesis_written
        or report.trail_facts
    )


def write_dream_evidence(home: Path, report: DreamReport | None, now_ms: int) -> Path | None:
    """Record the pass under ``{home}/dreams/last_run.json``.

    A pass that changed nothing leaves the previous evidence in place, so the
    file's mtime stays a truthful "last time memory moved" marker and a
    minutes-level cadence does not churn it.
    """
    path = Path(home).joinpath(*_EVIDENCE_RELATIVE)
    if report is None or (not _changed(report) and path.is_file()):
        return None
    payload = {
        "now_ms": now_ms,
        "upserted": report.upserted,
        "promoted": list(report.promoted),
        "user_md_written": report.user_md_written,
        "synthesis_written": report.synthesis_written,
        "trail_facts": report.trail_facts,
        "index_documents": report.index_documents,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return path
```

Add `import json` to the module imports.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/application/memory/test_dream_scheduler.py -v`
Expected: PASS, 7 tests

- [ ] **Step 5: Commit**

```bash
git add lca/application/memory/dream_scheduler.py tests/application/memory/test_dream_scheduler.py
git commit -m "feat(memory): record dream run evidence as a file artifact"
```

---

### Task 4: Plugin wiring with the cadence in configuration

**Files:**
- Create: `lca/plugins/memory/dream_scheduler/plugin.py`
- Modify: `bundles/assistant-runtime.yaml`
- Modify: `profiles/web-assistant.yaml`
- Test: `tests/plugins/test_dream_scheduler_plugin_shape.py`

**Interfaces:**
- Consumes: `DreamScheduler`, `write_dream_evidence` from Task 1-3; `ProfileBackfillService` and `render_user_profile` from `lca.plugins.assistant.profile.profile`; the assistant catalog capability.
- Produces: plugin id `lca-memory-dream-scheduler` providing nothing and requiring the catalog. `Config(tick_seconds: int = 300, enabled: bool = True)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/test_dream_scheduler_plugin_shape.py
from pathlib import Path

import yaml

from lca.plugins.memory.dream_scheduler.plugin import Config


def test_config_defaults_put_the_cadence_in_one_place() -> None:
    config = Config()

    assert config.tick_seconds == 300
    assert config.enabled is True
    assert config.assistants_root is None


def test_config_rejects_unknown_keys() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Config.model_validate({"tick_seconds": 60, "surprise": 1})


def test_the_bundle_declares_the_plugin() -> None:
    bundle = yaml.safe_load(
        Path("bundles/assistant-runtime.yaml").read_text(encoding="utf-8")
    )
    ids = {entry["id"] for entry in bundle["plugins"]}

    assert "lca-memory-dream-scheduler" in ids


def test_the_running_profile_sets_the_cadence() -> None:
    profile = yaml.safe_load(Path("profiles/web-assistant.yaml").read_text(encoding="utf-8"))
    patches = {
        entry["id"]: entry.get("config", {})
        for entry in profile.get("plugins", [])
        if isinstance(entry, dict) and "id" in entry
    }

    assert patches["lca-memory-dream-scheduler"]["tick_seconds"] <= 300
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/plugins/test_dream_scheduler_plugin_shape.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lca.plugins.memory.dream_scheduler'`

- [ ] **Step 3: Write the plugin**

```python
# lca/plugins/memory/dream_scheduler/plugin.py
"""Periodic offline memory consolidation (ADR-0287 Phase 0).

The loop is plugin-hosted rather than cron-hosted because ``CronJob.execution``
is a closed union that can only deliver a chat card or an avatar artifact, and
``next_run`` decides ``due`` by exact datetime equality that a discrete tick
never satisfies. Neither is changeable without an ADR.

Shape follows ``lca/plugins/avatar/plugin.py``, which already runs a background
scheduler in the same process under the same profile.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from lca.contracts.capabilities import ASSISTANT_CATALOG
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.application.memory.dream_scheduler import DreamScheduler, write_dream_evidence
from lca.plugins.assistant.profile.profile import ProfileBackfillService, render_user_profile

logger = logging.getLogger(__name__)

_scheduler_tasks: set[asyncio.Task] = set()


class Config(BaseModel):
    """Cadence and root live here so the upper bound is configuration, not prose."""

    model_config = ConfigDict(extra="forbid")

    assistants_root: str | None = None
    tick_seconds: int = 300
    enabled: bool = True


def _config_from(config: object) -> Config:
    if isinstance(config, Config):
        return config
    if isinstance(config, dict):
        return Config.model_validate(config)
    return Config()


def _resolve_base_dir(config: Config) -> Path:
    return Path(config.assistants_root or "~/.lca/assistants").expanduser()


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _homes(catalog: Any, base_dir: Path) -> Sequence[Path]:
    """Every assistant home with a memory directory, in catalog order."""
    homes: list[Path] = []
    for summary in catalog.list():
        home = getattr(summary, "home_path", None)
        if not isinstance(home, Path):
            continue
        if not home.is_absolute():
            home = base_dir / home
        if (home / "memory").is_dir():
            homes.append(home)
    return homes


@plugin(
    id="lca-memory-dream-scheduler",
    Config=Config,
    provides=(),
    requires=(ASSISTANT_CATALOG.key,),
    layer="L3",
    kind=PluginKind.SERVICE,
    effects="filesystem",
    test_suite="tests/plugins/test_dream_scheduler_plugin_shape.py",
)
async def setup(ctx: PluginContext, config: object) -> None:
    parsed = _config_from(config)
    if not parsed.enabled:
        return
    catalog = ctx.require(ASSISTANT_CATALOG.key)
    base_dir = _resolve_base_dir(parsed)
    lock_dir = base_dir.parent / "locks"
    service = ProfileBackfillService(catalog)

    def callbacks(home: Path):
        del home

        def backfill(assistant_id: str, records: list[MemoryRecord]) -> object:
            return service.backfill_from_records(assistant_id, records)

        return render_user_profile, backfill

    scheduler = DreamScheduler(
        homes=lambda: _homes(catalog, base_dir),
        lock_dir=lock_dir,
        tick_seconds=parsed.tick_seconds,
        now_ms=_now_ms,
        evidence_writer=write_dream_evidence,
        callbacks=callbacks,
    )
    task = asyncio.create_task(scheduler.run_forever())
    _scheduler_tasks.add(task)
    task.add_done_callback(_scheduler_tasks.discard)
    inner: Any = ctx._runtime()  # type: ignore[attr-defined]
    inner.effect(scheduler.stop, label="memory:dream-scheduler")


__all__ = ["Config", "setup"]
```

`lock_dir` resolves to `~/.lca/locks`, the directory the running cron daemon already uses (`/home/lichao/.lca/locks/cron.lock`). Per-assistant lock names are `memory_dream:<home name>`, so they cannot collide with `cron.lock`.

`ProfileBackfillService` is constructed once per plugin setup rather than once per home. The CLI builds it per invocation and imports the private `_AssistantCatalogImpl` to do so (`lca/infrastructure/cli/commands/ops/memory.py:41-46`); the plugin holds the real catalog capability and does not need that.

- [ ] **Step 4: Declare it in the bundle and the profile**

Append to the `plugins:` list in `bundles/assistant-runtime.yaml`, matching the existing entry shape at lines 74-76:

```yaml
  - id: lca-memory-dream-scheduler
```

Append to the plugin patch list in `profiles/web-assistant.yaml`, next to the existing `phase.reflect.memory.extract` entry at lines 97-99:

```yaml
  # Phase 0 门禁：dream 周期上界写进配置（ADR-0287 §4）。
  - id: lca-memory-dream-scheduler
    config:
      tick_seconds: 300
```

- [ ] **Step 5: Run tests and the plugin shape gate**

Run: `uv run pytest tests/plugins/test_dream_scheduler_plugin_shape.py -v && ./scripts/lca-ops audit-plugin-shape && uv run python scripts/check_plan_lift.py`
Expected: PASS, 4 tests; audit exits 0 for the new plugin id; `check_plan_lift.py` exits 0. The lift check is mandatory because this task edits a bundle: it runs the same two calls `boot_check` uses (`resolve_profile_with_deployment_env` then `validate_profile_plans`), and skipping it before a bundle change has taken the shared kernel down.

- [ ] **Step 6: Verify the profile still resolves**

Run: `uv run python -c "from lca.application.preset.resolve import resolve_profile; p=resolve_profile('profiles/web-assistant.yaml'); print('lca-memory-dream-scheduler' in {x.id for x in p.plugins})"`
Expected: `True`. If the resolve entry point has a different name in this tree, use `./scripts/lca-ops plan tree profiles/web-assistant.yaml` and confirm the id appears.

- [ ] **Step 7: Commit**

```bash
git add lca/plugins/memory/dream_scheduler/plugin.py bundles/assistant-runtime.yaml profiles/web-assistant.yaml tests/plugins/test_dream_scheduler_plugin_shape.py
git commit -m "feat(memory): schedule the dream pass from a plugin-hosted loop"
```

---

### Task 5: End-to-end Phase 0 evidence

**Files:**
- Test: `tests/scenario/memory/test_dream_scheduler_live_sweep.py`

**Interfaces:**
- Consumes: everything from Tasks 1-4.
- Produces: the observable state ADR-0287 §4 Phase 0 asks for, asserted in one place.

- [ ] **Step 1: Write the failing test**

```python
# tests/scenario/memory/test_dream_scheduler_live_sweep.py
import json
from pathlib import Path

import pytest

from lca.contracts.atoms.enums.enums import MemoryCategory
from lca.contracts.models.memory.episode import EpisodeFact, ResidualClass
from lca.application.memory.dream_scheduler import DreamScheduler, write_dream_evidence
from lca.infrastructure.memory.episode_buffer import EpisodeBuffer


def _identity_fact(trace_id: str) -> EpisodeFact:
    return EpisodeFact(
        fact_id=f"ep_{trace_id}",
        dedupe_key="identity:role",
        category=MemoryCategory.IDENTITY,
        content="用户身份：架构师",
        residual=ResidualClass.instruction,
        explicit_user_authority=True,
        source_trace_id=trace_id,
        observed_at_ms=1_791_121_000_000,
    )


async def test_a_sweep_promotes_a_captured_episode_and_leaves_evidence(
    tmp_path: Path,
) -> None:
    home = tmp_path / "asst_test"
    (home / "memory").mkdir(parents=True)
    EpisodeBuffer(home).append(_identity_fact("trace_a"))
    clock = [1_791_121_000_000]
    scheduler = DreamScheduler(
        homes=lambda: [home],
        lock_dir=tmp_path / "locks",
        tick_seconds=300,
        now_ms=lambda: clock[0],
        evidence_writer=write_dream_evidence,
    )

    await scheduler.sweep_once()

    semantic = json.loads((home / "memory" / "semantic.json").read_text(encoding="utf-8"))
    assert [row["content"] for row in semantic if not row["deleted"]] == ["用户身份：架构师"]
    assert semantic[0]["metadata"]["source"] == "dream"

    evidence = json.loads((home / "dreams" / "last_run.json").read_text(encoding="utf-8"))
    assert evidence["upserted"] == 1
    assert evidence["promoted"] == ["identity:role"]


async def test_a_second_sweep_promotes_nothing_and_keeps_the_evidence_stable(
    tmp_path: Path,
) -> None:
    home = tmp_path / "asst_test"
    (home / "memory").mkdir(parents=True)
    EpisodeBuffer(home).append(_identity_fact("trace_a"))
    clock = [1_791_121_000_000]
    scheduler = DreamScheduler(
        homes=lambda: [home],
        lock_dir=tmp_path / "locks",
        tick_seconds=300,
        now_ms=lambda: clock[0],
        evidence_writer=write_dream_evidence,
    )
    await scheduler.sweep_once()
    stamp = (home / "dreams" / "last_run.json").stat().st_mtime_ns
    rows = len(json.loads((home / "memory" / "semantic.json").read_text(encoding="utf-8")))

    clock[0] += 300_000
    await scheduler.sweep_once()

    after = json.loads((home / "memory" / "semantic.json").read_text(encoding="utf-8"))
    assert len(after) == rows, "a repeated sweep must not add a second row for one fact"
    assert (home / "dreams" / "last_run.json").stat().st_mtime_ns == stamp
```

- [ ] **Step 2: Run test to verify it fails, then passes**

Run: `uv run pytest tests/scenario/memory/test_dream_scheduler_live_sweep.py -v`
Expected: FAIL first if `ResidualClass` is imported from the wrong module. It lives in `lca.contracts.models.memory.episode` (`episode.py:17-20`). After fixing the import, PASS, 2 tests. The second test is the regression lock on the 17/89 duplicate-dimension defect: it proves the dream path is idempotent on a fact already active, via `_already_active` at `dream.py:242`.

- [ ] **Step 3: Confirm the real kernel picks it up**

Run: `./scripts/lca-ops kernel-restart && sleep 320 && cat /home/lichao/.lca/assistants/asst_ce7fecd65188/dreams/last_run.json`
Expected: a JSON document with a `now_ms` inside the last 6 minutes. This is the "真实触发证据" ADR-0287 §4 Phase 0 requires. If the file is absent, check `./scripts/lca-ops status --json` and the kernel log for `dream sweep failed`.

- [ ] **Step 4: Commit**

```bash
git add tests/scenario/memory/test_dream_scheduler_live_sweep.py
git commit -m "test(memory): pin end-to-end dream sweep promotion and idempotency"
```

---

## Out of scope, and why

**Phase 0 condition 2 (the online residual-capture path).** Blocked on ADR-0287 Open question 5. Research found the note's premise for this condition is wrong in a way that changes its content:

- `phase.perceive.observe` already calls `record_task_episode(runtime, state)` on every turn with no flag check (`lca/nodes/perceive/observe/observe.py:62-67`, added in `913a967ae`). The real gate is `episode_home(runtime)` resolving, not `governor_enabled`. ADR-0287 F4 and the note both state the flag is the gate. Both need correcting.
- The evidence assistant ran `profiles/web-assistant.yaml` with `governor_enabled: true` (the live kernel command line confirms the profile) and still wrote zero episodes, because `govern()` is a three-template closed matcher. It returns `None` for `别那么啰嗦` and `还是简洁一点好`; the verbosity rule requires `("记住" in text or "以后" in text)` conjunction (`lca/cognition/memory/govern.py:55`).
- When the verbosity rule does match it hardcodes `explicit_user_authority=False` (`govern.py:58-63`), so it can never take the first-occurrence branch of `_lifecycle` (`lca/contracts/models/memory/episode.py:74-82`) and needs `recurrence >= 2` across distinct traces.
- The trail path is the only one giving first-occurrence preference promotion, because `_trail_episode` sets `authority=True` when `is_preference_statement` matches (`dream.py:137-158`) and that regex is far broader: `偏好|以后|不要|必须|记住|严禁|回复要|请记` (`lca/infrastructure/memory/contextfiles/domain/trail.py:17`). It has no writer.
- Live corruption: `_ROLE` and `_NAME` use greedy `(.+)` and `_clean_capture` truncates at 40 characters (`govern.py:18-19`, `:25-29`). A production home contains `用户身份：老李,做架构设计,偏好 Python,回复请简短。写进你的长期记忆。` An explicit preference was swallowed into an identity fact, promoted with `authority=True`, and is never revisited. This is independent of Phase 0 and worth its own fix.

**The `next_run` microsecond-equality defect (B2).** Platform-wide and user-facing: no periodic cron job can fire in LCA today, so any user asking for a daily reminder gets a job that silently never runs. It needs an ADR-0268 amendment because ADR-0268 §232-233 specifies the equality semantics verbatim, and every existing cron test injects a boundary-exact synthetic clock (`tests/infrastructure/cron/test_daemon_self_healing.py:66,111,118,153,160,200,234,273`; `tests/scenario/test_cron_full_lifecycle_invariants.py:175,197,236,277,322,344,387,458,464,471`), so new tests must land before the semantics change. File separately; do not smuggle into Phase 0.

**ADR-0287 §4 amendment.** Phase 0's carrier line names `{home}/routines/` and 0268 CronJob. Neither can dispatch to `run_dream`. Amend to name the plugin-hosted loop before Task 4 lands.

## Self-review notes

Spec coverage: ADR-0287 §4 Phase 0 has three clauses. Cadence in configuration is Task 4. Real trigger evidence is Task 3 plus Task 5 Step 3. The capture-path clause is explicitly out of scope with the reason recorded. D5's ordering (Phase 0 before Phase 1) is preserved because nothing here moves `phase.reflect.memory.extract`.

Type consistency: `DreamScheduler`'s constructor keyword names (`homes`, `lock_dir`, `tick_seconds`, `now_ms`, `run_dream_fn`, `evidence_writer`, `callbacks`) are identical in Tasks 1, 2, 3, and 5. `write_dream_evidence(home, report, now_ms)` matches the `EvidenceWriter` alias in Task 1. `sweep_once` returns `tuple[DreamReport | None, ...]` in Task 1 and is asserted as `(None,)` in Task 2.

Two things an executor must verify rather than trust. The `PluginContext` accessor names (`ctx.require`, `ctx._runtime()`, `inner.effect`) and the `assistants_root` config pattern are copied from `lca/plugins/avatar/plugin.py:91-92,300-312`; confirm `PluginKind.SERVICE` and `layer="L3"` against that file, since the avatar plugin declares its own values there. And `ResidualClass` is exported from `lca.contracts.models.memory.episode` (`episode.py:17-20`), not from `lca/cognition/memory/govern.py`.
