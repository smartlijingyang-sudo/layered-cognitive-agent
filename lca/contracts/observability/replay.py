"""零 token 确定性回放（ADR-0167 D10）。

设计原则：永不调 LLM、永不跑 tool。重建「当时模型看到了什么 + 当时采取了什么动作」。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class StepContextAt:
    """step_index 处的「模型所见 + 所做」快照。"""

    step_index: int
    step_id: str
    request_header: dict[str, Any] | None
    messages: tuple[Any, ...]  # 真送入 LLM 的 messages（ground truth）
    tool_schemas: tuple[Any, ...]
    context_manifest: dict[str, Any] | None  # skill_catalog / workspace_instructions
    actions: tuple[Any, ...]  # tool_call + tool_result 事实记录
    source: str  # "live" | "replayed"
    inferred: bool  # True 表示 messages 由 journal 推导
    digest_verified: bool  # request_header.digest vs 文件 sha256


@runtime_checkable
class ReplayCursor(Protocol):
    """零 token 回放 Protocol。"""

    def at(self, *, run_id: str, step_index: int) -> StepContextAt: ...
    def with_override(
        self,
        *,
        run_id: str,
        step_index: int,
        tool_args_overrides: dict[str, Any],
    ) -> StepContextAt: ...  # 仅算 diff，绝不私自执行工具


@dataclass(frozen=True)
class CursorDiff:
    """两次 run 同 step 的对比（fork-diff 基础）。"""

    run_id_a: str
    run_id_b: str
    step_index: int
    prompt_hash_a: str = ""
    prompt_hash_b: str = ""
    messages_a: tuple[Any, ...] = ()
    messages_b: tuple[Any, ...] = ()
    actions_a: tuple[Any, ...] = ()
    actions_b: tuple[Any, ...] = ()


@dataclass(frozen=True)
class ModelVisibleRecord:
    """``traces/runs/<id>/model_visible/step_N/`` 的目录索引。"""

    run_id: str
    step_id: str
    header_path: str | None = None
    system_prompt_path: str | None = None
    tool_schemas_path: str | None = None
    context_manifest_path: str | None = None
    messages_path: str | None = None
    digest_verified: bool = False


__all__ = [
    "CursorDiff",
    "ModelVisibleRecord",
    "ReplayCursor",
    "StepContextAt",
]
