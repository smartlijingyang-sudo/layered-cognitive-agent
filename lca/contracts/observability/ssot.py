"""观测面 SSOT 注册表 —— 一次性收口文件名 / 路径 / 状态集 / 序列化(PR-1)。

背景:docs/notes/proposed/seam/2026-09-03-observation-ssot-registry.md L1。
设计原则:SSOT 集中在一个模块,5 段 frozen / pure 数据 + helper,任何"文件名 /
路径 / 状态集 / 序列化策略"的判定必须走本模块;scripts/check_observation_ssot.py
作为 CI 守门。

段 1:spine file SSOT —— 替代 RunLocator.events_path 的 fs 内联,提升到 contracts。
段 2:Run terminal status SSOT —— 替代 30+ 处裸字符串。
段 3:ExecutionOutcome enum —— 替代 5 处 Literal 字面。
段 4:to_jsonable 单一来源 —— 合并 _capture_io + journal/step/projector 两份。
段 5:provider_schema —— 工具 schema 序列化最高优先级,给 model_visible 用。
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Mapping
from enum import Enum
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

_log = logging.getLogger(__name__)


# ─── 段 1:spine file SSOT ────────────────────────────────────────────────


SPINE_FILE_SUFFIX: Final[str] = ".spine.jsonl"
"""spine 文件后缀(ADR-0169 L10)。"""

LEGACY_EVENTS_NAME: Final[str] = "events.jsonl"
"""legacy 文件名(向后兼容;reader 仍接受)。"""

EXCEPTIONS_FILE_TEMPLATE: Final[str] = "{run_id}.exceptions.jsonl"
"""per-run exceptions 文件模板(由 file_sink 拼接,reader 一律走 run_locator.exceptions_path)。"""


def spine_filename_for_run(run_id: str) -> str:
    """派生 per-run spine 文件名。

    >>> spine_filename_for_run("run_abc")
    'run_abc.spine.jsonl'
    """
    return f"{run_id}{SPINE_FILE_SUFFIX}"


def exceptions_filename_for_run(run_id: str) -> str:
    """派生 per-run exceptions 文件名。

    >>> exceptions_filename_for_run("run_abc")
    'run_abc.exceptions.jsonl'
    """
    return EXCEPTIONS_FILE_TEMPLATE.format(run_id=run_id)


def find_spine_file(run_dir: Path, run_id: str) -> Path:
    """spine SSOT 的路径解析 —— spine 命名优先,legacy 兜底。

    行为契约(同 ``FilesystemRunLocator.events_path`` 的 fs 内联实现,但提升
    到 contracts 让所有 reader/writer 走同一入口):
    1. ``<run_dir>/<run_id>.spine.jsonl`` 存在 → 返回该路径。
    2. 否则 ``<run_dir>/events.jsonl`` 存在 → 返回 legacy 路径。
    3. 都不存在 → 返回 spine 命名路径(由 caller 决定是否 raise)。

    Args:
        run_dir: run 的物理目录。
        run_id: run 标识(用于派生 spine 文件名)。

    Returns:
        spine 文件的 Path(可能不存在)。
    """
    spine_path = run_dir / spine_filename_for_run(run_id)
    if spine_path.exists():
        return spine_path
    legacy_path = run_dir / LEGACY_EVENTS_NAME
    if legacy_path.exists():
        return legacy_path
    return spine_path


# ─── 段 2:Run terminal status SSOT ──────────────────────────────────────


class RunLifecycleStatus(str, Enum):
    """Run 生命周期的可观察状态(SSOT,上提自 plugins/transport/.../session/session.py:53)。

    与 ExecutionOutcome 的语义边界(不要合并):
    - RunLifecycleStatus:run 整体 lifecycle 的宏观状态(对外可观察)。
    - ExecutionOutcome:step / phase / declarative 单次执行的微观 outcome。
    """

    PENDING = "pending"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


TERMINAL_RUN_STATUSES: Final[frozenset[RunLifecycleStatus]] = frozenset(
    {
        RunLifecycleStatus.PAUSED,
        RunLifecycleStatus.COMPLETED,
        RunLifecycleStatus.FAILED,
        RunLifecycleStatus.CANCELED,
    }
)
"""终态集 —— run 不会再推进,不代表成功。"""

SUCCESS_RUN_STATUSES: Final[frozenset[RunLifecycleStatus]] = frozenset(
    {RunLifecycleStatus.COMPLETED}
)
"""成功终态集 —— run 完整成功。"""

FAILURE_RUN_STATUSES: Final[frozenset[RunLifecycleStatus]] = frozenset(
    {RunLifecycleStatus.FAILED, RunLifecycleStatus.CANCELED}
)
"""失败终态集 —— run 失败或被取消。"""


def is_terminal_run_status(status: str | RunLifecycleStatus) -> bool:
    """是否终态 —— 状态机不会再处理它。"""
    return RunLifecycleStatus(status) in TERMINAL_RUN_STATUSES


def is_success_run_status(status: str | RunLifecycleStatus) -> bool:
    """是否完整成功终态 —— 仅 COMPLETED。"""
    return RunLifecycleStatus(status) in SUCCESS_RUN_STATUSES


def is_failure_run_status(status: str | RunLifecycleStatus) -> bool:
    """是否失败终态 —— FAILED 或 CANCELED。"""
    return RunLifecycleStatus(status) in FAILURE_RUN_STATUSES


# ─── 段 3:ExecutionOutcome enum(替代 5 处 Literal 字面) ─────────────────


class ExecutionOutcome(str, Enum):
    """step / phase / declarative 单次执行的 outcome(SSOT)。

    替代以下 Literal 字面字段:
    - ``lca/contracts/models/observability/journal_doc.py:34/181``
    - ``lca/contracts/protocols/declarative/declarative_execution.py:71``
    - ``lca/harness/declarative/compile/phase_governance.py:290``
    - ``lca/runtime/result_finalizer.py`` 内 Literal 字段
    """

    COMPLETED = "completed"
    PAUSED = "paused"
    FAILED = "failed"
    EFFECT_UNCERTAIN = "effect_uncertain"
    IN_PROGRESS = "in_progress"
    STOPPED = "stopped"


TERMINAL_EXECUTION_OUTCOMES: Final[frozenset[ExecutionOutcome]] = frozenset(
    {
        ExecutionOutcome.COMPLETED,
        ExecutionOutcome.PAUSED,
        ExecutionOutcome.FAILED,
        ExecutionOutcome.EFFECT_UNCERTAIN,
        ExecutionOutcome.STOPPED,
    }
)
"""execution 终态集(微观 outcome 不再推进)。"""


def is_terminal_outcome(outcome: str | ExecutionOutcome) -> bool:
    """execution outcome 是否终态。"""
    return ExecutionOutcome(outcome) in TERMINAL_EXECUTION_OUTCOMES


# ─── 段 4:to_jsonable 单一来源 ───────────────────────────────────────────


def provider_schema(tool: Any) -> dict[str, Any] | None:
    """工具实例的 provider-level schema(OpenAI / Anthropic / 自定义)返回 dict 或 None。

    优先级(详见 :func:`to_jsonable` 的 to_jsonable 链):
    1. ``tool.__provider_schema__()`` 方法
    2. ``tool.openai_schema()`` 方法
    3. ``tool.anthropic_schema()`` 方法
    4. ``tool.tool_schema()`` 方法
    返回 dict 或 None。
    """
    for method_name in ("__provider_schema__", "openai_schema", "anthropic_schema", "tool_schema"):
        method = getattr(tool, method_name, None)
        if callable(method):
            try:
                result = method()
            except Exception:  # pragma: no cover — provider schema 是 best-effort
                return None
            if isinstance(result, Mapping):
                return dict(result)
    return None


def to_jsonable(value: Any) -> Any:
    """任意对象 → JSON 兼容结构。SSOT —— 替代 _capture_io.to_jsonable + journal/step/projector.to_jsonable 两份。

    优先级:
    0. provider_schema(给 model_visible tools 用,优先于 dataclass 派生)
    1. 已是 JSON primitives / containers → 原样
    2. dataclass 实例 → dataclasses.asdict
    3. to_dict / model_dump / dict() → 调用
    4. __dict__ → 取
    5. repr(value) → 最终兜底(返回字符串,json 可序列化)
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    # 优先级 0:provider_schema(给 model_visible 工具实例用)
    schema = provider_schema(value)
    if schema is not None:
        return schema
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        try:
            return to_jsonable(dataclasses.asdict(value))
        except Exception as exc:
            _log.debug("to_jsonable asdict failed: %s", exc)
    for proto_name in ("to_dict", "model_dump", "dict"):
        proto = getattr(value, proto_name, None)
        if callable(proto):
            try:
                return to_jsonable(proto())
            except Exception as exc:
                _log.debug("to_jsonable %s() failed: %s", proto_name, exc)
    if hasattr(value, "__dict__"):
        try:
            return to_jsonable(vars(value))
        except Exception as exc:
            _log.debug("to_jsonable vars() failed: %s", exc)
    return repr(value)


# ─── 段 5:RunLocator Protocol 扩展(补 3 个方法) ─────────────────────────


@runtime_checkable
class RunLocatorExtended(Protocol):
    """RunLocator 扩展契约 —— 新增 3 个方法供 reader/writer 走 SSOT。

    注意:这不是替换 RunLocator(向后兼容);RunLocator 的现有 8 方法不动,
    本 Protocol 仅声明 3 个新方法供 capability_check 与迁移期使用。
    迁移完成后,RunLocator 直接合并本 Protocol。
    """

    def kernel_log_path(self, run_id: str) -> Path:
        """返回 ``<run_dir>/kernel.log`` 路径(kernel 内部日志,ADR-0122)。"""

    def exceptions_path(self, run_id: str) -> Path:
        """返回 ``<run_dir>/<run_id>.exceptions.jsonl`` 路径。"""

    def profile_snapshot_path(self, run_id: str) -> Path:
        """返回 ``<run_dir>/profile_snapshot.json`` 路径(Profile 快照)。"""


__all__ = [
    "EXCEPTIONS_FILE_TEMPLATE",
    "FAILURE_RUN_STATUSES",
    "LEGACY_EVENTS_NAME",
    # 段 1
    "SPINE_FILE_SUFFIX",
    "SUCCESS_RUN_STATUSES",
    "TERMINAL_EXECUTION_OUTCOMES",
    "TERMINAL_RUN_STATUSES",
    # 段 3
    "ExecutionOutcome",
    # 段 2
    "RunLifecycleStatus",
    # 段 5
    "RunLocatorExtended",
    "exceptions_filename_for_run",
    "find_spine_file",
    "is_failure_run_status",
    "is_success_run_status",
    "is_terminal_outcome",
    "is_terminal_run_status",
    # 段 4
    "provider_schema",
    "spine_filename_for_run",
    "to_jsonable",
]
