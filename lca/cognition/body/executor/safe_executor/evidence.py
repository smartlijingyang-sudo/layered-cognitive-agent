"""Evidence staging for SafeExecutor — observation → journal-field extractors.

These pure helpers turn raw ``Observation`` payloads into the typed fields of
``step.tool_result.record`` (stdout_head / stdout_chars_total / stderr /
files_created / delta_summary). They perform no journal I/O and no side
effects; the executor feeds their results into ``record_step_tool_result``.
"""

from __future__ import annotations

import time
from typing import Any

_PERF_COUNTER_SCALE = 1000


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * _PERF_COUNTER_SCALE)


# Single SSOT for body-layer stdout-shaped keys. Kept in sync with the
# convergence layer's ``_STDOUT_KEYS`` in
# ``lca/cognition/convergence/payload.py``. Any new stdout-shaped payload
# key must be added to both lists. delete-when: pipeline_safe_executor is
# folded into safe_executor (single owner of the contract).
_STDOUT_KEYS = ("output", "stdout", "content", "text")

# Body-layer SSOT for harvested-file keys and entry shape, kept in sync with
# the convergence layer's ``_FILE_KEYS`` / ``_file_names`` for the same reason
# and under the same delete-when as ``_STDOUT_KEYS`` above.
_FILE_KEYS = ("files_created", "files")


def _file_names(value: Any) -> tuple[str, ...]:
    """Normalize harvested file entries to names.

    The sandbox harvest carries A2A file metadata dicts (``name`` / ``url`` /
    ``mimeType``; see ``infrastructure/tools/sandbox/observation.py``), while
    writeFile-shaped producers carry plain name strings. Stringifying a dict
    entry would surface its repr as a filename.

    Listing-shaped tools (``listFiles`` / ``searchFiles``) also carry a
    ``files`` key whose entries have ``isDirectory``. Those are directory
    listings, not files created by this call, so entries with an
    ``isDirectory`` key are skipped (see tests/cognition/body/
    test_listfiles_not_files_created.py).
    """
    if not isinstance(value, (list, tuple)):
        return ()
    names: list[str] = []
    for item in value:
        if isinstance(item, dict) and "isDirectory" in item:
            continue
        name = str(item.get("name") or "") if isinstance(item, dict) else str(item or "")
        if name:
            names.append(name)
    return tuple(names)


def _extract_stdout_head(observation: Any, *, limit: int = 2000) -> str:
    """从 Observation.payload 抽 stdout-like 文本;空 observation 返回空串。"""
    payload = getattr(observation, "payload", None)
    if not isinstance(payload, dict):
        return ""
    for key in _STDOUT_KEYS:
        value = payload.get(key)
        if isinstance(value, str):
            return value[:limit]
    return ""


def _extract_stdout_chars_total(observation: Any) -> int:
    """真实 stdout 字符数,优先取 ``output`` / ``stdout`` / ``content`` / ``text`` 第一个非空 str。

    Returns 0 when observation 无 stdout-like 文本;用于填入
    ``step.tool_result.record.stdout_chars_total``,让 critic / LLM context
    看到真实产出长度(避免被 ``stdout_head`` 摘要误判为空)。
    """
    payload = getattr(observation, "payload", None)
    if not isinstance(payload, dict):
        return 0
    for key in _STDOUT_KEYS:
        value = payload.get(key)
        if isinstance(value, str):
            return len(value)
    return 0


def _extract_stderr(observation: Any, *, limit: int = 2000) -> str:
    """从 Observation.payload 抽 stderr;空 observation 返回空串。"""
    payload = getattr(observation, "payload", None)
    if not isinstance(payload, dict):
        return ""
    value = payload.get("stderr")
    if isinstance(value, str):
        return value[:limit]
    return ""


def _extract_files_created(observation: Any) -> tuple[str, ...]:
    """从 Observation 抽产出文件名;失败兜底空 tuple。

    ``extra`` 先于 ``payload``:sandbox harvest 两处写同一份 file_parts
    (``infrastructure/tools/sandbox/exec_observation.py``)。
    """
    for container in (getattr(observation, "extra", None), getattr(observation, "payload", None)):
        if not isinstance(container, dict):
            continue
        for key in _FILE_KEYS:
            names = _file_names(container.get(key))
            if names:
                return names
    return ()


def _delta_summary_from_obs(observation: Any, *, limit: int = 200) -> str:
    """从 Observation 生成 step.tool_result.delta_summary(< 200 字符人话)。"""
    if not getattr(observation, "success", True):
        err = getattr(observation, "error", None) or "unknown"
        return f"❌ {type(err).__name__}: {err}"[:limit]
    files = _extract_files_created(observation)
    if files:
        names = ", ".join(files[:3])
        return f"✅ 写出 {len(files)} 个文件: {names}"[:limit]
    stdout = _extract_stdout_head(observation, limit=80)
    if stdout:
        return f"✅ stdout[:80] = {stdout.replace(chr(10), '⏎')}"[:limit]
    return "✅ ok"
