"""ADR-0169 L10:spine 文件名约定常量 + 派生函数。

PR-2 / S2 引入 ``SPINE_FILE_SUFFIX = ".spine.jsonl"`` 常量与 ``spine_filename_for_run``
派生函数; PR-27 将 sink / storage / backend 默认文件名从 ``events.jsonl``
迁移到 ``$run_id.spine.jsonl`` 模板(实例化时通过 :func:`resolve_filename`
替换 ``$run_id`` 占位符)。

旧文件名 ``events.jsonl`` 仍可显式传入(向后兼容)。所有 reader 对
``<run_id>.spine.jsonl`` 与 ``events.jsonl`` 都接受; 当两个文件同时存在时,
优先读取 spine 命名(写入侧已默认 spine 命名)。
"""

from __future__ import annotations

# COMPAT(delete-when: spine_filename 默认稳定 ≥ 14 天, tracking: ADR-0169-task-PR-27)
SPINE_FILE_SUFFIX = ".spine.jsonl"

# 旧文件名(向后兼容;Reader 仍接受 events.jsonl)
LEGACY_FILE_NAME = "events.jsonl"

# PR-27 默认模板:实例化时按 run_id 替换 $run_id 占位符
DEFAULT_SPINE_TEMPLATE = "$run_id.spine.jsonl"

# 旧默认名(向后兼容;若显式传入 events.jsonl,继续生效)
LEGACY_DEFAULT_NAME = "events.jsonl"

# 占位符集合(目前只有 $run_id;未来可扩 $trace_id 等)
_PLACEHOLDER_RUN_ID = "$run_id"


def spine_filename_for_run(run_id: str) -> str:
    """派生 per-run spine 文件名(ADR-0169 L10)。

    >>> spine_filename_for_run("run_abc")
    'run_abc.spine.jsonl'
    """
    return f"{run_id}{SPINE_FILE_SUFFIX}"


def resolve_filename(template: str, run_id: str) -> str:
    """解析文件名模板中的 ``$run_id`` 占位符(ADR-0169 PR-27)。

    非模板字面量(如 ``events.jsonl`` / ``boot-events.jsonl``)原样返回。
    模板字符串以 ``$run_id`` 开头 / 含 ``$run_id`` 占位符时,替换为实际 run_id。

    >>> resolve_filename("$run_id.spine.jsonl", "run_abc")
    'run_abc.spine.jsonl'
    >>> resolve_filename("events.jsonl", "run_abc")
    'events.jsonl'
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
    "LEGACY_DEFAULT_NAME",
    "LEGACY_FILE_NAME",
    "SPINE_FILE_SUFFIX",
    "resolve_filename",
    "spine_filename_for_run",
]
