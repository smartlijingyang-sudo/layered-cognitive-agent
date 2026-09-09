"""Task class routing — goal predicate for prompt and convergence (ADR-0196)."""

from __future__ import annotations

import re

from lca.cognition.convergence.constants import TASK_CLASS_MANIFEST_KIND
from lca.contracts.models.core.perceive.projection import current_manifest_from_state
from lca.contracts.models.core.policy.convergence import TaskClass
from lca.contracts.models.core.state.state import AgentState

_VALID_TASK_CLASSES = frozenset(
    {"informative_text", "visual_artifact", "code_demo", "mixed", "unknown"},
)

_GRAPHPLAN = re.compile(r"图计划|graph\s*plan", re.I)
_VISUAL = re.compile(
    r"画|图表|可视化|chart|plot|matplotlib|diagram|流程图|饼图|png|jpg",
    re.I,
)
_INFORMATIVE = re.compile(
    r"笑话|joke|解释|说明|介绍|故事|段子|文字|说说|讲一|这是什么|是什么|what is this|what's this",
    re.I,
)
_CODE = re.compile(
    r"用\s*python|写代码|写个脚本|execute|run code|python写",
    re.I,
)
_SYNTHESIS = re.compile(
    r"分析|analyze|解读|summarize|总结|综述|评估|evaluate|review|报告",
    re.I,
)


def classify_task(task: str) -> TaskClass:
    text = (task or "").strip()
    if not text:
        return "unknown"
    informative = bool(_INFORMATIVE.search(text))
    graphplan = bool(_GRAPHPLAN.search(text))
    visual = bool(_VISUAL.search(text)) and not graphplan
    code = bool(_CODE.search(text))
    if informative and not visual:
        return "informative_text"
    if visual and not informative:
        return "visual_artifact"
    if code and visual:
        return "mixed"
    if code:
        return "code_demo"
    if informative:
        return "informative_text"
    if visual:
        return "visual_artifact"
    return "unknown"


def _hint_from_manifest(state: AgentState) -> TaskClass | None:
    manifest = current_manifest_from_state(state)
    if manifest is None:
        return None
    for item in manifest.items:
        if item.kind != TASK_CLASS_MANIFEST_KIND:
            continue
        if isinstance(item.payload, str) and item.payload in _VALID_TASK_CLASSES:
            return item.payload  # type: ignore[return-value]
    return None


def task_requires_synthesis(task: str) -> bool:
    """True when the user goal needs model synthesis, not raw tool stdout."""
    return bool(_SYNTHESIS.search((task or "").strip()))


def resolve_task_class(state: AgentState) -> TaskClass:
    """Perceive sensor hint overrides regex heuristic."""
    hinted = _hint_from_manifest(state)
    if hinted is not None:
        return hinted
    return classify_task(state.task or "")


__all__ = ["classify_task", "resolve_task_class", "task_requires_synthesis"]
