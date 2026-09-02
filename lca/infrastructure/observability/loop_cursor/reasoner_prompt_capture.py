"""ADR-0175 D1 + D3:StdReasonerPromptCapture —— brain prompt 真值落盘默认实现。

职责:
- 一次性写 ``<run_dir>/model_visible/step_<NN>/{system_prompt.json,
  system_prompt_sections.json}``(system prompt 全文 + 每段结构化 trace)。
- 返回 ``ReasonerPromptArtifact``(system_prompt_digest + 2 个 relpath)。
- 不持 cursor 引用;Capture **只读** ``PromptTrace`` 写入磁盘。

设计要点:
- 与 :class:`StdModelVisibleCapture` 同样以 ``sha256:<hex>`` 派生 digest,
  与 step_tree_accumulator 兼容格式。
- 序列化策略:``_to_jsonable`` 优先 to_dict / model_dump / vars / repr。
- 失败抛 ``OSError``(不静默),由 caller 决定是否降级
  (Reasoner._render_prompt 在 try/except 中吞掉,符合 ADR-0169 L10)。
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path, PurePosixPath
from typing import Any

from lca.contracts.models.cognition.prompt_assembly import PromptTrace
from lca.contracts.observability.reasoner_prompt_capture import (
    ReasonerPromptArtifact,
    ReasonerPromptCapture,
)

_log = logging.getLogger(__name__)

_DIGEST_PREFIX = "sha256:"


def _to_jsonable(value: Any) -> Any:
    """Serialize arbitrary objects to JSON-compatible structures.

    Priority:
    1. Already JSON-compatible primitives / containers -> as-is.
    2. ``dataclasses`` instance (incl. frozen + slots) -> ``dataclasses.asdict``.
    3. ``to_dict`` / ``model_dump`` / ``dict()`` -> call.
    4. ``__dict__`` -> take it.
    5. ``repr(value)`` as final fallback.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    import dataclasses as _dc

    if _dc.is_dataclass(value) and not isinstance(value, type):
        try:
            return _to_jsonable(_dc.asdict(value))
        except Exception as exc:
            _log.debug("reasoner_prompt asdict failed: %s", exc)
    for proto_name in ("to_dict", "model_dump", "dict"):
        proto = getattr(value, proto_name, None)
        if callable(proto):
            try:
                return _to_jsonable(proto())
            except Exception as exc:
                _log.debug("reasoner_prompt %s() failed: %s", proto_name, exc)
    if hasattr(value, "__dict__"):
        try:
            return _to_jsonable(vars(value))
        except Exception as exc:
            _log.debug("reasoner_prompt vars() failed: %s", exc)
    return repr(value)


def _sha256_digest(payload: Any) -> str:
    """sha256:<hex> digest matching model_visible_capture format."""
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return _DIGEST_PREFIX + hashlib.sha256(encoded).hexdigest()


def _relative_posix(run_dir: Path, target: Path) -> str:
    """Compute POSIX-style relpath; fallback to filename on cross-device errors."""
    try:
        rel = target.relative_to(run_dir)
    except ValueError:
        return target.name
    return PurePosixPath(rel.as_posix()).as_posix()


def _write_json(path: Path, payload: Any) -> str:
    """Write JSON to ``path`` (mkdir parents); return sha256 digest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    jsonable = _to_jsonable(payload)
    serialized = json.dumps(
        jsonable,
        ensure_ascii=False,
        indent=2,
        default=str,
        sort_keys=False,
    )
    path.write_text(serialized, encoding="utf-8")
    return _sha256_digest(jsonable)


class StdReasonerPromptCapture(ReasonerPromptCapture):
    """Default ReasonerPromptCapture impl.

    写入位置::

        <run_dir>/model_visible/step_<NN>/system_prompt.json
        <run_dir>/model_visible/step_<NN>/system_prompt_sections.json
    """

    def __init__(self, *, run_dir: Path) -> None:
        self._run_dir = Path(run_dir)

    @property
    def run_dir(self) -> Path:
        return self._run_dir

    def capture(
        self,
        *,
        step_id: str,
        trace: PromptTrace,
    ) -> ReasonerPromptArtifact:
        step_dir = self._run_dir / "model_visible" / step_id

        system_path = step_dir / "system_prompt.json"
        sections_path = step_dir / "system_prompt_sections.json"

        system_payload = {
            "step_id": step_id,
            "body": trace.system_prompt_text,
            "template_id": trace.template_id,
            "variant": trace.variant,
            "selector_decision_path": trace.selector_decision_path,
            "total_chars": trace.total_chars,
        }
        system_digest = _write_json(system_path, system_payload)

        sections_payload = {
            "step_id": step_id,
            "template_id": trace.template_id,
            "variant": trace.variant,
            "selector_decision_path": trace.selector_decision_path,
            "activated_skill_ids": list(trace.activated_skill_ids),
            "tools_count": trace.tools_count,
            "available_skills_count": trace.available_skills_count,
            "total_chars": trace.total_chars,
            "sections": [_to_jsonable(s) for s in trace.sections],
        }
        _write_json(sections_path, sections_payload)

        return ReasonerPromptArtifact(
            step_id=step_id,
            system_prompt_path=_relative_posix(self._run_dir, system_path),
            system_prompt_sections_path=_relative_posix(self._run_dir, sections_path),
            system_prompt_digest=system_digest,
        )


__all__ = ["StdReasonerPromptCapture"]
