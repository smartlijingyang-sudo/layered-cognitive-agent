"""Resume memory capture（ADR-0246 PR-8）。

run 从 ``askUserQuestion`` 暂停恢复时，人工回答本身也是用户陈述。本模块在
恢复路径上补跑记忆蒸馏（与 ``phase.reflect.memory.extract`` 同一提示词与
快速路径门），把该轮身份/偏好写入记忆系统，避免「说了但没记」。
"""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import ReflectionVerdict
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Reflection
from lca.contracts.protocols.session.resume.input import ResumeInput
from lca.nodes.reflect.memory_extract.memory_extract import (
    _EXTRACT_PROMPT,
    _may_contain_self_reference,
    _parse_candidates,
)

__all__ = ["capture_resume_memory"]


async def capture_resume_memory(
    memory: object,
    adapter: object,
    resume_input: ResumeInput,
    state: object,
) -> bool:
    """从恢复的人工回答蒸馏记忆候选并写入；返回是否发生写入。

    快速路径：回答不含自我指涉、无 adapter、或蒸馏失败时返回 False（不阻塞
    恢复主流程）。写入走 ``memory.update``（C10 效果窄门），候选带
    ``dedupe_key`` 幂等，重复恢复不产生重复活跃记忆。
    """
    turn = getattr(resume_input, "turn", None)
    if turn is None:
        return False
    observation = getattr(turn, "observation", None)
    payload = getattr(observation, "payload", None)
    if not isinstance(payload, str) or not payload.strip():
        return False
    text = payload.strip()
    if not _may_contain_self_reference(text):
        return False
    if adapter is None or not hasattr(adapter, "complete"):
        return False
    try:
        response = await adapter.complete(_EXTRACT_PROMPT.replace("{task}", text))  # type: ignore[union-attr]
        candidates = _parse_candidates(getattr(response, "text", "") or "")
    except Exception:
        # 蒸馏失败不阻塞恢复（fail-soft）。
        return False
    if not candidates:
        return False
    if memory is None or not hasattr(memory, "update"):
        return False
    reflection = Reflection(
        reflection_id=new_id("refl"),
        verdict=ReflectionVerdict.ON_TRACK,
        extra={"memory_candidates": candidates},
    )
    try:
        await memory.update(
            state,
            observation,
            reflection,
        )
        return True
    except Exception:
        # 写入失败不阻塞恢复（fail-soft）。
        return False
