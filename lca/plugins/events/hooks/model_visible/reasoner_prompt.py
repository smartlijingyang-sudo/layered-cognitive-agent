"""ADR-0175 D3:ReasonerPrompt ContextVar 注入 — ModelVisibleHook 配套。

ADR-0185 PR-4 收口:该 ContextVar 随 hook 一起迁到
``lca.plugins.events.hooks.model_visible`` 命名空间,所有权与占用点同位。
职责:
- Reasoner 渲染完成后绑定,让 :class:`ModelVisibleHook` 在 LLM 调用时通过
  :func:`get_current_reasoner_prompt` 拿到当前 step 的真 system prompt。
- ContextVar 隔离多 run;reset token 由 caller 在 close 时释放。
- prompt 缺席时 hook 透明降级,不挡业务(ADR-0169 L10 + D5)。
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

from lca.contracts.models.cognition.prompt_assembly import PromptTrace
from lca.contracts.models.core.perception import ContextManifest


@dataclass(frozen=True)
class CurrentReasonerPrompt:
    """Reasoner 注入到 ContextVar 的最小真值集合。

    ``system_prompt_text`` 为空时,hook 走降级分支。

    所有权:Reasoner 在 prompt 渲染完成时绑定
    (:meth:`PromptReasoner._bind_reasoner_prompt`),LLM 边界
    (:class:`ModelVisibleHook`)只读 —— 把 ``system_prompt_text`` 写进
    ``SpineLlmRequestHeaderPayload.system``,不修改本对象。

    ``prompt_trace`` / ``context_manifest`` 默认 None,保留既有 4 标量
    构造;绑定时携带完整 :class:`PromptTrace`(section trace + skill ids)
    与本 turn 的 :class:`ContextManifest`,使 spine event 可重建
    skill / prompt 装配(ADR-0167 D3/D4)。
    """

    step_id: str
    template_id: str
    selector_decision_path: str
    system_prompt_text: str
    prompt_trace: PromptTrace | None = None
    context_manifest: ContextManifest | None = None


_current_reasoner_prompt: ContextVar[CurrentReasonerPrompt | None] = ContextVar(
    "lca_reasoner_prompt_current", default=None
)


def get_current_reasoner_prompt() -> CurrentReasonerPrompt | None:
    """Return the active Reasoner prompt, or ``None`` when not bound."""
    return _current_reasoner_prompt.get()


def bind_current_reasoner_prompt(prompt: CurrentReasonerPrompt) -> Token[Any]:
    """Bind a Reasoner prompt; return reset token for the caller to release."""
    return _current_reasoner_prompt.set(prompt)


def reset_current_reasoner_prompt(token: Token[Any]) -> None:
    """Release a previously bound token."""
    _current_reasoner_prompt.reset(token)


def install_reasoner_prompt(prompt: CurrentReasonerPrompt) -> Token[Any]:
    """Thin re-export for composition roots (matches ``install_*`` style)."""
    return bind_current_reasoner_prompt(prompt)


def reset_reasoner_prompt(token: Token[Any]) -> None:
    """Thin re-export."""
    reset_current_reasoner_prompt(token)


__all__ = [
    "CurrentReasonerPrompt",
    "bind_current_reasoner_prompt",
    "get_current_reasoner_prompt",
    "install_reasoner_prompt",
    "reset_current_reasoner_prompt",
    "reset_reasoner_prompt",
]
