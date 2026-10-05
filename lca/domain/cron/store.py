"""CronJob file store (ADR-0268 §5, §6).

存储只有这一个写入者。路径是 assistant home 下的
``cron/<job_id>.json``，定义用原子替换写入；run 记录追加在
``cron/<job_id>/runs/``。``cron.remove`` 只删除定义文件，
不删除已结束的 run 记录。
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from lca.contracts.models.cron.models import (
    CronJob,
    CronRun,
    CronRunConflictError,
    CronRunOutcome,
    TargetReceipt,
)

__all__ = ["CronStore", "MultiAssistantCronStore"]


def _atomic_write_text(path: Path, payload: str) -> None:
    """经临时文件原子替换写入文本；失败时清理临时文件后原样上抛。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


class CronStore:
    """基于 assistant home 的 CronJob 定义与 run 记录存储。"""

    def __init__(self, assistants_root: Path) -> None:
        self._root = Path(assistants_root)

    def _cron_dir(self) -> Path:
        return self._root / "cron"

    def _job_file(self, job_id: str) -> Path:
        return self._cron_dir() / f"{job_id}.json"

    def _runs_dir(self, job_id: str) -> Path:
        return self._cron_dir() / job_id / "runs"

    def save_job(self, job: CronJob) -> None:
        """原子替换写入定义文件。"""
        _atomic_write_text(self._job_file(job.id), job.model_dump_json(indent=2))

    def get_job(self, job_id: str) -> CronJob | None:
        path = self._job_file(job_id)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return CronJob.model_validate(data)

    def list_jobs(self) -> list[CronJob]:
        """列出该 assistant home 下的全部任务定义。"""
        cron_dir = self._cron_dir()
        if not cron_dir.is_dir():
            return []
        jobs: list[CronJob] = []
        for path in sorted(cron_dir.glob("*.json")):
            if not path.is_file():
                continue
            try:
                jobs.append(CronJob.model_validate(json.loads(path.read_text(encoding="utf-8"))))
            except ValueError:
                # 单条坏文件不使整个列表失败；cron.view 仍能读到详情并暴露错误。
                continue
        return jobs

    def delete_job(self, job_id: str) -> bool:
        """删除定义文件，保留 run 记录目录。"""
        path = self._job_file(job_id)
        if not path.is_file():
            return False
        path.unlink()
        return True

    def append_run(
        self,
        job_id: str,
        *,
        outcome: CronRunOutcome,
        finished_at: datetime | None = None,
        receipts: tuple[TargetReceipt, ...] = (),
        run_id: str | None = None,
    ) -> str:
        """追加一条 run 记录（只追加，不覆盖），返回实际写入的 ``run_id``。

        ``run_id`` 缺省时生成 ``<job_id>-<uuid4hex>``；正式 cron worker
        显式传入，保持与 handoff 上下文里的 ``run_id`` 一致。
        """
        rid = run_id or f"{job_id}-{uuid.uuid4().hex}"
        run = CronRun(
            run_id=rid,
            outcome=outcome,
            receipts=receipts,
            finished_at=finished_at,
        )
        _atomic_write_text(
            self._runs_dir(job_id) / f"{rid}.json",
            run.model_dump_json(indent=2),
        )
        return rid

    def get_run(self, job_id: str, run_id: str) -> CronRun | None:
        path = self._runs_dir(job_id) / f"{run_id}.json"
        if not path.is_file():
            return None
        return CronRun.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def record_handoff_runs(
        self, job_id: str, run_id: str, handoff_run_ids: tuple[str, ...]
    ) -> CronRun | None:
        """起 handoff run 之前落下它们的 run id（ADR-0268 §6.1）。

        写在起 run 之前是幂等的承载点：先起 run 再落身份，进程在两步之间死掉
        会让恢复读到的记录看起来没派过，于是再派一次，用户收到两条同样的提醒。
        同一组 id 重写是无操作，不同的一组抛 :class:`CronRunConflictError`。
        记录不存在返回 ``None``。
        """
        return self._complete_run_field(job_id, run_id, "handoff_run_ids", handoff_run_ids)

    def close_run_receipts(
        self, job_id: str, run_id: str, receipts: tuple[TargetReceipt, ...]
    ) -> CronRun | None:
        """handoff 轮结束时补写 ``receipts``（ADR-0268 §6.1）。

        同一组回执重复关闭是无操作。不同的一组抛
        :class:`CronRunConflictError`，一次到点有两个投递决定是矛盾，不是更新。
        记录不存在返回 ``None``。
        """
        return self._complete_run_field(job_id, run_id, "receipts", receipts)

    def _complete_run_field(
        self, job_id: str, run_id: str, field: str, value: tuple[Any, ...]
    ) -> CronRun | None:
        run = self.get_run(job_id, run_id)
        if run is None:
            return None
        incoming = tuple(value)
        existing = getattr(run, field)
        if existing:
            if existing == incoming:
                return run
            raise CronRunConflictError(
                f"cron run {run_id} already closed {field} with a different value"
            )
        updated = run.model_copy(update={field: incoming})
        _atomic_write_text(
            self._runs_dir(job_id) / f"{run_id}.json",
            updated.model_dump_json(indent=2),
        )
        return updated

    def list_runs(self, job_id: str) -> list[CronRun]:
        """按 run_id 字典序返回 run 记录（调用方负责时间语义）。"""
        return self.get_run_records(job_id)

    def get_run_records(self, job_id: str) -> list[CronRun]:
        """按 run_id 字典序返回该任务的 run 记录（与 ``list_runs`` 同序）。"""
        runs_dir = self._runs_dir(job_id)
        if not runs_dir.is_dir():
            return []
        runs: list[CronRun] = []
        for path in sorted(runs_dir.glob("*.json")):
            if not path.is_file():
                continue
            try:
                runs.append(CronRun.model_validate(json.loads(path.read_text(encoding="utf-8"))))
            except ValueError:
                continue
        return runs


class MultiAssistantCronStore:
    """跨全部助理 home 的 CronStore 聚合代理（用于后台 CronDaemonService 统一调度）。"""

    def __init__(self, assistants_dir: Path | None = None) -> None:
        if assistants_dir is None:
            from lca.infrastructure.path.locator import get_lca_home

            self._dir = get_lca_home() / "assistants"
        else:
            self._dir = Path(assistants_dir)

    def _stores(self) -> dict[str, CronStore]:
        if not self._dir.is_dir():
            return {}
        stores: dict[str, CronStore] = {}
        for p in self._dir.iterdir():
            if p.is_dir() and (p / "cron").is_dir():
                stores[p.name] = CronStore(p)
        return stores

    def list_jobs(self) -> list[CronJob]:
        all_jobs: list[CronJob] = []
        for s in self._stores().values():
            all_jobs.extend(s.list_jobs())
        return all_jobs

    def get_job(self, job_id: str) -> CronJob | None:
        for s in self._stores().values():
            j = s.get_job(job_id)
            if j is not None:
                return j
        return None

    def append_run(
        self,
        job_id: str,
        *,
        outcome: CronRunOutcome,
        finished_at: datetime | None = None,
        receipts: tuple[TargetReceipt, ...] = (),
        run_id: str | None = None,
    ) -> str:
        for s in self._stores().values():
            if s.get_job(job_id) is not None:
                return s.append_run(
                    job_id,
                    outcome=outcome,
                    finished_at=finished_at,
                    receipts=receipts,
                    run_id=run_id,
                )
        return f"{job_id}-{uuid.uuid4().hex}"

    def record_handoff_runs(
        self, job_id: str, run_id: str, handoff_run_ids: tuple[str, ...]
    ) -> CronRun | None:
        for s in self._stores().values():
            if s.get_job(job_id) is not None:
                return s.record_handoff_runs(job_id, run_id, handoff_run_ids)
        return None

    def close_run_receipts(
        self, job_id: str, run_id: str, receipts: tuple[TargetReceipt, ...]
    ) -> CronRun | None:
        for s in self._stores().values():
            if s.get_job(job_id) is not None:
                return s.close_run_receipts(job_id, run_id, receipts)
        return None

    def list_runs(self, job_id: str) -> list[CronRun]:
        for s in self._stores().values():
            runs = s.list_runs(job_id)
            if runs:
                return runs
        return []
