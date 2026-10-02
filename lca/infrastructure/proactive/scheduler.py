# -*- coding: utf-8 -*-
"""ProactiveScheduler：主动消息调度器（对齐 ADR-0263 §9）。

职责：tick 驱动 → 文件锁互斥 → 到期任务 → 裁决 → 投递 →
失败重试（3 次，退避 1/5/15min）→ 死信（保留 7 天）。

- 锁：``lock_dir/proactive.lock``，JSON ``{"owner": ..., "mtime_ms": ...}``，
  每次 tick 成功刷新 mtime（心跳）；stale 阈值
  ``min(2 × interval, 90min)``，超限则收割（ADR-0263 §9①②）。
- 状态：``state_dir/state.json`` 记录每个 job 的 ``last_run_ms`` /
  ``attempts`` / ``next_retry_ms``；``state_dir/dead_letter/`` 存死信，
  超 7 天的在 tick 时清理。
- tick 是同步纯驱动：不自己起线程/进程，由 carrier 生命周期调用
  （ADR-0263 §9④：tick 落 carrier 内）。
"""

from __future__ import annotations

import json
import logging
import os
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from lca.cognition.proactive.worthiness import decide
from lca.contracts.models.proactive.message import ProactiveMessage
from lca.contracts.models.proactive.policy import ProactivePolicy
from lca.contracts.models.proactive.schedule import ProactiveJob, TickReport
from lca.contracts.models.proactive.worthiness import (
    ProactiveRequest,
    VerdictKind,
)
from lca.infrastructure.proactive.deliverer import ProactiveDeliverer

_log = logging.getLogger(__name__)

# ADR-0263 §9②：stale 绝对上限 90 分钟。
STALE_ABSOLUTE_CAP_S = 90 * 60
# ADR-0263 §9③：重试退避 1min / 5min / 15min。
RETRY_BACKOFF_S: tuple[int, ...] = (60, 300, 900)
MAX_ATTEMPTS = 3
# ADR-0263 §9③：死信保留 7 天。
DEAD_LETTER_TTL_S = 7 * 24 * 3600

JobSource = Callable[[], list[ProactiveJob]]


class ProactiveScheduler:
    """文件锁互斥的主动消息 tick 调度器。"""

    def __init__(
        self,
        *,
        lock_dir: str | Path,
        state_dir: str | Path,
        job_source: JobSource,
        deliverer: ProactiveDeliverer,
        default_interval_s: int = 3600,
        policy: ProactivePolicy | None = None,
    ) -> None:
        self._lock_dir = Path(lock_dir)
        self._state_dir = Path(state_dir)
        self._job_source = job_source
        self._deliverer = deliverer
        self._default_interval_s = default_interval_s
        # 全局政策由 gate 统一执行（唯一卡点），scheduler 只透传不自查
        self._policy = policy if policy is not None else ProactivePolicy()

    # ---- 对外入口：carrier 每 tick 调用一次 ----

    def tick(self, now_ms: int | None = None) -> TickReport:
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        if not self._acquire_lock(now_ms):
            return TickReport(tick_at_ms=now_ms, lock_acquired=False)

        # 锁由 tick 自管理：正常结束释放，崩溃残留靠 mtime 心跳 + stale 收割。
        try:
            return self._tick_locked(now_ms)
        finally:
            self.release_lock()

    def _tick_locked(self, now_ms: int) -> TickReport:
        self._prune_dead_letters(now_ms)
        state = self._load_state()
        report = TickReport(tick_at_ms=now_ms, lock_acquired=True)
        due = delivered = silent = rejected = failed = dead = 0

        for job in self._job_source():
            if not job.enabled:
                continue
            js = state.get(job.id)
            if js is None:
                # 新任务从未运行过：首次 tick 立即触发（interval 是"触发间隔"
                # 语义，不是"启动延迟"）。
                js = {}
                is_due = True
            else:
                next_retry_ms = js.get("next_retry_ms")
                last_run_ms = js.get("last_run_ms", 0)
                if next_retry_ms is not None and now_ms < next_retry_ms:
                    continue
                is_due = not (
                    next_retry_ms is None
                    and now_ms - last_run_ms < job.interval_seconds * 1000
                )
            if not is_due:
                continue
            last_run_ms = js.get("last_run_ms", 0)
            due += 1
            outcome = self._run_job(job, js, now_ms)
            if outcome == "delivered":
                delivered += 1
                state[job.id] = {"last_run_ms": now_ms, "attempts": 0}
            elif outcome == "silent":
                silent += 1
                state[job.id] = {"last_run_ms": now_ms, "attempts": 0}
            elif outcome == "rejected":
                rejected += 1
                state[job.id] = {"last_run_ms": now_ms, "attempts": 0}
            elif outcome == "dead":
                dead += 1
                state.pop(job.id, None)
            else:
                failed += 1
                attempts = js.get("attempts", 0) + 1
                if attempts >= MAX_ATTEMPTS:
                    self._write_dead_letter(job, js, now_ms, reason="重试 3 次均失败")
                    state.pop(job.id, None)
                    dead += 1
                else:
                    backoff_s = RETRY_BACKOFF_S[attempts - 1]
                    state[job.id] = {
                        "last_run_ms": last_run_ms,
                        "attempts": attempts,
                        "next_retry_ms": now_ms + backoff_s * 1000,
                        "last_error": js.get("last_error", ""),
                    }

        self._save_state(state)
        return TickReport(
            tick_at_ms=now_ms,
            lock_acquired=True,
            jobs_due=due,
            delivered=delivered,
            silent=silent,
            rejected=rejected,
            failed=failed,
            dead_lettered=dead,
        )

    # ---- 单 job 执行：构造请求 → 裁决 → 投递 ----

    def _run_job(self, job: ProactiveJob, js: dict, now_ms: int) -> str:
        message = ProactiveMessage(
            id=f"{job.id}-{now_ms}",
            content=job.content,
            source=job.source,
        )
        # 调用方声明（ADR-0264 §4①）：cron 任务按配置声明期望裁决，
        # gate 只做 downgrade-only 交叉校验，不多花模型调用。
        declared = (
            VerdictKind.DELIVER_CHAT
            if (job.worth_interrupting or job.requested)
            else VerdictKind.DELIVER_QUIET
        )
        # requested 的 trigger 上下文背书：cron 的"请求记录"就是任务定义本身，
        # scheduler 只背书 job:<id> 形式的引用；对不上的按 unrequested 处理。
        known_refs = (f"job:{job.id}",) if job.request_ref else ()
        request = ProactiveRequest(
            message=message,
            target=job.target,
            requested=job.requested,
            declared=declared,
            request_ref=job.request_ref,
            known_request_refs=known_refs,
            worth_interrupting=job.worth_interrupting,
        )
        verdict = decide(
            request,
            policy=self._policy,
            now=datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc),
        )
        if verdict.kind == VerdictKind.REJECTED:
            _log.warning(
                "proactive.rejected job_id=%s reason=%s", job.id, verdict.reason
            )
            return "rejected"
        if verdict.kind == VerdictKind.SILENT:
            return "silent"
        try:
            self._deliverer.deliver(
                message,
                job.target,
                annotate_unretrieved=verdict.annotate_unretrieved,
            )
        except Exception as exc:  # noqa: BLE001 — 失败转重试/死信，不炸 tick
            js["last_error"] = str(exc)
            _log.warning("proactive.deliver_failed job_id=%s", job.id, exc_info=True)
            return "failed"
        return "delivered"

    # ---- 文件锁（ADR-0263 §9①②） ----

    @property
    def _lock_file(self) -> Path:
        return self._lock_dir / "proactive.lock"

    def _acquire_lock(self, now_ms: int) -> bool:
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        owner = f"{socket.gethostname()}:{os.getpid()}"
        try:
            with open(self._lock_file, "x", encoding="utf-8") as f:
                json.dump({"owner": owner, "mtime_ms": now_ms}, f)
            return True
        except FileExistsError:
            pass
        try:
            with open(self._lock_file, encoding="utf-8") as f:
                lock = json.load(f)
        except (OSError, ValueError):
            lock = {}
        mtime_ms = int(lock.get("mtime_ms", 0) or 0)
        stale_after_s = min(
            self._default_interval_s * 2.0,
            STALE_ABSOLUTE_CAP_S,
        )
        if now_ms - mtime_ms > stale_after_s * 1000:
            _log.warning(
                "proactive.lock_stale_reaped owner=%s age_s=%d",
                lock.get("owner"),
                (now_ms - mtime_ms) // 1000,
            )
            try:
                self._lock_file.unlink()
            except OSError:
                return False
            return self._acquire_lock(now_ms)
        return False

    def release_lock(self) -> None:
        try:
            self._lock_file.unlink()
        except OSError:
            pass

    # ---- 状态与死信 ----

    @property
    def _state_file(self) -> Path:
        return self._state_dir / "state.json"

    @property
    def _dead_letter_dir(self) -> Path:
        return self._state_dir / "dead_letter"

    def _load_state(self) -> dict:
        try:
            with open(self._state_file, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_state(self, state: dict) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._state_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
        os.replace(tmp, self._state_file)

    def _write_dead_letter(self, job: ProactiveJob, js: dict, now_ms: int, reason: str) -> None:
        self._dead_letter_dir.mkdir(parents=True, exist_ok=True)
        path = self._dead_letter_dir / f"{job.id}-{now_ms}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "job_id": job.id,
                    "dead_at_ms": now_ms,
                    "reason": reason,
                    "last_error": js.get("last_error", ""),
                    "content": job.content,
                },
                f,
                ensure_ascii=False,
            )
        _log.warning("proactive.dead_lettered job_id=%s reason=%s", job.id, reason)

    def _prune_dead_letters(self, now_ms: int) -> None:
        if not self._dead_letter_dir.is_dir():
            return
        cutoff = now_ms - DEAD_LETTER_TTL_S * 1000
        for path in self._dead_letter_dir.glob("*.json"):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if int(data.get("dead_at_ms", 0)) < cutoff:
                    path.unlink()
            except (OSError, ValueError):
                continue


__all__ = [
    "DEAD_LETTER_TTL_S",
    "MAX_ATTEMPTS",
    "RETRY_BACKOFF_S",
    "STALE_ABSOLUTE_CAP_S",
    "ProactiveScheduler",
]
