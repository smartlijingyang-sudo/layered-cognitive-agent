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

import logging
from pathlib import Path

from lca.contracts.models.cognition.prompt_assembly import PromptTrace
from lca.contracts.observability.reasoner_prompt_capture import (
    ReasonerPromptArtifact,
    ReasonerPromptCapture,
)
from lca.infrastructure.observability.loop_cursor._capture_io import (
    relative_posix as _relative_posix,
)
from lca.infrastructure.observability.loop_cursor._capture_io import (
    sha256_digest as _sha256_digest,
)
from lca.infrastructure.observability.loop_cursor._capture_io import (
    to_jsonable as _to_jsonable,
)
from lca.infrastructure.observability.loop_cursor._capture_io import (
    write_json as _write_json,
)

_log = logging.getLogger(__name__)


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
            "sections": [
                {
                    **_to_jsonable(s),
                    # ADR-0176 D3 §4:content_digest = sha256(text),仅当 text 非空时写
                    **(
                        {"content_digest": _sha256_digest(s.text)}
                        if s.text
                        else {}
                    ),
                }
                for s in trace.sections
            ],
        }
        _write_json(sections_path, sections_payload)

        return ReasonerPromptArtifact(
            step_id=step_id,
            system_prompt_path=_relative_posix(self._run_dir, system_path),
            system_prompt_sections_path=_relative_posix(self._run_dir, sections_path),
            system_prompt_digest=system_digest,
        )


__all__ = ["StdReasonerPromptCapture"]
