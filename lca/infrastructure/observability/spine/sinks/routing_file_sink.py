# COMPAT(delete-when: PR-9, tracking: ADR-0181)
# 旧 EventSpine sink；PR-8 shim 走 events/sinks/spine_* 包装；本模块保留
# 至 PR-9 旧 spine 全退役（rg "lca.plugins.observability.spine.sinks" lca/ = 0 触发）。

"""Run-routing FileSink — boot vs per-run spine.jsonl (ADR-0165.1 layout + PR-27)。

Boot / no-run events → ``boot_path`` (default ``.lca/spine/boot-spine.jsonl``)。
Events with a real ``run_id`` → ``<runs_root>/<run_id>/<resolved_file_name>``。

ADR-0169 PR-27:``file_name`` 默认 ``$run_id.spine.jsonl`` 模板,在
:meth:`_sink_for` 实例化时按当前 ``run_id`` 解析为
``<run_id>.spine.jsonl``。PR-4 收口:不再支持旧单文件 layout 字面
显式传入(boot 命名空间也迁到 ``boot-spine.jsonl``)。
"""

from __future__ import annotations

import threading
from pathlib import Path

from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.sinks.naming import (
    DEFAULT_SPINE_TEMPLATE,
    resolve_filename,
)
from lca.infrastructure.observability.spine.sinks.tracing_file_sink import (
    TracingFileSink,
)

_BOOT_RUN_IDS = frozenset({"", "boot", "default-run"})


class RunRoutingFileSink:
    """Demux EventRecords to boot file or per-run spine 文件。"""

    def __init__(
        self,
        *,
        boot_path: Path,
        runs_root: Path,
        file_name: str = DEFAULT_SPINE_TEMPLATE,
        spine_filename: bool = False,
    ) -> None:
        self._boot_path = Path(boot_path)
        self._runs_root = Path(runs_root)
        self._file_name = file_name
        self._spine_filename = spine_filename
        self._boot_path.parent.mkdir(parents=True, exist_ok=True)
        self._runs_root.mkdir(parents=True, exist_ok=True)
        # 异常必落盘保证 (ADR-2026-09-03 + TracingFileSink):任何 IOError
        # 退化到 FALLBACK.log / structlog,绝不抛。这是观测层最严的
        # 不变量 —— 否则 webserver 入口异常会让 caller 整条 request 崩。
        self._boot = TracingFileSink(
            self._boot_path.parent,
            run_id="boot",
            file_name=self._boot_path.name,
        )
        self._runs: dict[str, TracingFileSink] = {}
        self._lock = threading.Lock()
        self._closed = False

    @property
    def boot_path(self) -> Path:
        return self._boot.path

    @property
    def runs_root(self) -> Path:
        return self._runs_root

    def path_for(self, run_id: str) -> Path:
        """Return the per-run 文件路径(可能尚未落盘)。"""
        if self._is_boot_run_id(run_id):
            return self._boot.path
        resolved = self._resolve_file_name(run_id)
        return self._runs_root / run_id / resolved

    def write(self, record: EventRecord) -> None:
        if self._closed:
            raise RuntimeError("RunRoutingFileSink already closed")
        run_id = str(record.run_id or "")
        if self._is_boot_run_id(run_id):
            self._boot.write(record)
            return
        sink = self._sink_for(run_id)
        sink.write(record)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with self._lock:
            sinks = list(self._runs.values())
            self._runs.clear()
        self._boot.close()
        for sink in sinks:
            sink.close()

    def _resolve_file_name(self, run_id: str) -> str:
        """把 ``file_name`` 模板按 ``run_id`` 解析为实际文件名。

        ``$run_id`` 占位符或 ``spine_filename=True`` 时统一解析为
        ``<run_id>.spine.jsonl``;其他字面量原样返回。
        """
        if self._spine_filename or self._file_name == DEFAULT_SPINE_TEMPLATE:
            from lca.infrastructure.observability.spine.sinks.naming import (
                spine_filename_for_run,
            )

            return spine_filename_for_run(run_id)
        return resolve_filename(self._file_name, run_id)

    def _sink_for(self, run_id: str) -> TracingFileSink:
        with self._lock:
            existing = self._runs.get(run_id)
            if existing is not None:
                return existing
            run_dir = self._runs_root / run_id
            sink = TracingFileSink(
                run_dir,
                run_id=run_id,
                file_name=self._file_name,
                spine_filename=self._spine_filename,
            )
            self._runs[run_id] = sink
            return sink

    @staticmethod
    def _is_boot_run_id(run_id: str) -> bool:
        return run_id in _BOOT_RUN_IDS


__all__ = ["RunRoutingFileSink"]
