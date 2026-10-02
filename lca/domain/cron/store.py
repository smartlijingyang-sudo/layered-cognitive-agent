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
from pathlib import Path

from lca.contracts.models.cron.models import CronJob, CronRun

__all__ = ["CronStore"]


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

    def append_run(self, job_id: str, run: CronRun) -> None:
        """追加一条 run 记录（只追加，不覆盖）。"""
        _atomic_write_text(
            self._runs_dir(job_id) / f"{run.run_id}.json",
            run.model_dump_json(indent=2),
        )

    def get_run(self, job_id: str, run_id: str) -> CronRun | None:
        path = self._runs_dir(job_id) / f"{run_id}.json"
        if not path.is_file():
            return None
        return CronRun.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def list_runs(self, job_id: str) -> list[CronRun]:
        """按 run_id 字典序返回 run 记录（调用方负责时间语义）。"""
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
