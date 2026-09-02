"""ADR-0175 D1:ReasonerPromptCapture —— brain prompt 真值落盘接缝。

职责:
- 在 ``SectionManifestPromptAssembler.render`` 完成后被调用,
  把 ``PromptTrace`` 一次性写到 ``<run_dir>/model_visible/step_<NN>/
  {system_prompt.json, system_prompt_sections.json}``。
- 返回 ``ReasonerPromptArtifact``(digest + relpath bundle)给 Reasoner,
  Reasoner 再把 ``system_prompt_digest`` 塞进
  ``ContextVar get_current_reasoner_prompt()``,供同 run 后续
  ``ModelVisibleLLMAdapter._derive_capture_inputs`` 取用,让 5 件套的
  ``system.json`` 写入真 prompt(不再用占位字符串)。
- cursor 不知道 ReasonerPromptCapture 存在(协议边界不夹带,
  与 ADR-0169 D7 "Capture 不持 cursor 引用" 一致)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from lca.contracts.models.cognition.prompt_assembly import PromptTrace


@dataclass(frozen=True)
class ReasonerPromptArtifact:
    """Capture 写盘产物的不可变描述。

    字段:
    - step_id 由调用方传入(来自 cursor.snapshot.step_id);Capture 不派生。
    - system_prompt_path / system_prompt_sections_path 是相对
      ``run_dir`` 的 POSIX 风格 relpath;解析时由 ``run_dir / path`` 还原。
    - system_prompt_digest 是 ``sha256:<hex>`` 形式,与现有
      ``ModelVisibleArtifact.digest`` 格式一致。
    """

    step_id: str
    system_prompt_path: str
    system_prompt_sections_path: str
    system_prompt_digest: str


class ReasonerPromptCapture(Protocol):
    """Brain prompt 真值落盘接缝(ADR-0175 D1)。"""

    def capture(
        self,
        *,
        step_id: str,
        trace: PromptTrace,
    ) -> ReasonerPromptArtifact:
        """写 system_prompt.json + system_prompt_sections.json,返回 digest + relpath。

        参数:
            step_id  : 由 cursor.snapshot 派生(Reasoner 已持有)。
            trace    : SectionManifestPromptAssembler.render 返回的结构化 trace。

        返回:
            ``ReasonerPromptArtifact``:2 个文件路径 + system prompt digest。
        """
        ...


__all__ = ["ReasonerPromptArtifact", "ReasonerPromptCapture"]
