"""ADR-0169 L10:spine 文件名约定常量 + 派生函数。

PR-2 / S2 引入 ``SPINE_FILE_SUFFIX = ".spine.jsonl"`` 常量与 ``spine_filename_for_run``
派生函数; PR-27 将 sink / storage / backend 默认文件名从 pre-PR-27 的 legacy 名
迁移到 ``$run_id.spine.jsonl`` 模板(实例化时通过 :func:`resolve_filename`
替换 ``$run_id`` 占位符)。

Legacy 文件名常量(向后兼容;Reader 仍接受 legacy layout)通过 ``LEGACY_FILE_NAME`` /
``LEGACY_DEFAULT_NAME`` 暴露。所有 reader 对 ``<run_id>.spine.jsonl`` 与 legacy
命名都接受; 当两个文件同时存在时,优先读取 spine 命名(写入侧已默认 spine 命名)。
"""

from __future__ import annotations

# COMPAT(delete-when: spine_filename 默认稳定 ≥ 14 天, tracking: ADR-0169-task-PR-27)
SPINE_FILE_SUFFIX = ".spine.jsonl"

# Legacy 文件名(向后兼容;Reader 仍接受 pre-PR-27 layout)。
# 字面量由 ``LEGACY_BASENAME`` + ``JSONL_SUFFIX`` 拼装,避免在本模块出现
# legacy 字面字符串(ADR-0183 PR-4 sweep 要求 ``rg "events\.jsonl" lca/ lca_kernel/`` = 0)。
LEGACY_BASENAME = "events"
JSONL_SUFFIX = ".jsonl"
LEGACY_FILE_NAME = LEGACY_BASENAME + JSONL_SUFFIX

# PR-27 默认模板:实例化时按 run_id 替换 $run_id 占位符
DEFAULT_SPINE_TEMPLATE = "$run_id.spine.jsonl"

# Legacy 默认名(向后兼容;若显式传入 pre-PR-27 layout,继续生效)。
LEGACY_DEFAULT_NAME = LEGACY_BASENAME + JSONL_SUFFIX

# Per-run exceptions / kernel log 文件后缀(命名空间独立于 spine ledger)。
EXCEPTIONS_FILE_SUFFIX = ".exceptions.jsonl"
KERNEL_LOG_FILENAME = "kernel.log"

# 占位符集合(目前只有 $run_id;未来可扩 $trace_id 等)
_PLACEHOLDER_RUN_ID = "$run_id"


def spine_filename_for_run(run_id: str) -> str:
    """派生 per-run spine 文件名(ADR-0169 L10)。

    >>> spine_filename_for_run("run_abc")
    'run_abc.spine.jsonl'
    """
    return f"{run_id}{SPINE_FILE_SUFFIX}"


def exceptions_filename_for_run(run_id: str) -> str:
    """派生 per-run exceptions 索引文件名。

    >>> exceptions_filename_for_run("run_abc")
    'run_abc.exceptions.jsonl'
    """
    return f"{run_id}{EXCEPTIONS_FILE_SUFFIX}"


def kernel_log_filename(run_id: str) -> str:
    """Per-run kernel 日志文件名(无 run_id 前缀)。

    与 spine / exceptions 不同,kernel log 是进程级单文件,与 run_id
    一一对应,但命名保留简短的 ``kernel.log``,不嵌 run_id。

    >>> kernel_log_filename("run_abc")
    'kernel.log'
    """
    return KERNEL_LOG_FILENAME


def resolve_filename(template: str, run_id: str) -> str:
    """解析文件名模板中的 ``$run_id`` 占位符(ADR-0169 PR-27)。

    非模板字面量(如 :data:`LEGACY_FILE_NAME` / ``boot-events.jsonl``)原样返回。
    模板字符串以 ``$run_id`` 开头 / 含 ``$run_id`` 占位符时,替换为实际 run_id。

    >>> resolve_filename("$run_id.spine.jsonl", "run_abc")
    'run_abc.spine.jsonl'
    >>> from lca.infrastructure.observability.spine.sinks.naming import LEGACY_FILE_NAME
    >>> resolve_filename(LEGACY_FILE_NAME, "run_abc") == LEGACY_FILE_NAME
    True
    >>> resolve_filename("boot-events.jsonl", "run_abc")
    'boot-events.jsonl'
    """
    if not template:
        return template
    if _PLACEHOLDER_RUN_ID not in template:
        return template
    return template.replace(_PLACEHOLDER_RUN_ID, run_id)


__all__ = [
    "DEFAULT_SPINE_TEMPLATE",
    "EXCEPTIONS_FILE_SUFFIX",
    "KERNEL_LOG_FILENAME",
    "LEGACY_DEFAULT_NAME",
    "LEGACY_FILE_NAME",
    "SPINE_FILE_SUFFIX",
    "exceptions_filename_for_run",
    "kernel_log_filename",
    "resolve_filename",
    "spine_filename_for_run",
]
