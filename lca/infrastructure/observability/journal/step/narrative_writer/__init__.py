"""StepNarrativeWriter —— JournalDocument → narrative.md 投影(ADR-0164 Phase 4)。

包内拆分:
    sections.py   5 原语子节渲染器(context/thinking/tool_call/tool_result/reflect/spans)
    fold.py       ADR-0185 fold 章节渲染器 + FoldProvider seam
    writer.py     StepNarrativeWriter 编排 + summary 表
公共入口保持 ``from ...step.narrative_writer import StepNarrativeWriter`` 不变。
"""

from lca.infrastructure.observability.journal.step.narrative_writer.fold import (
    FoldProvider,
)
from lca.infrastructure.observability.journal.step.narrative_writer.writer import (
    StepNarrativeWriter,
)

__all__ = ["FoldProvider", "StepNarrativeWriter"]
