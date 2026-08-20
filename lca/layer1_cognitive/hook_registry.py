"""CordisHookRegistry —— 生命周期钩子的 cordis events namespace 投影。

每个 ``HookEvent`` 映射到 cordis ``events.serial(f"hook/{event.value}", ...)``；
外部调用 ``await hooks.trigger(event, state, **kwargs)`` 转发到 cordis events。
相位 span 在 trigger 边界统一发射（观察者模式），属性从 hook kwargs 提取后
经 ambient 策略脱敏/截断（写入期强制）。

设计：DSH 把生命周期钩子作为 cordis events 暴露（``agent/pre-step`` 、
``tools/pre-execute`` 等都是 ``ctx.on`` 的 listener）。LCA 把 ``HookEvent``
枚举映射成 ``hook/<event>`` 命名空间，单一 dispatch 后端——cordis events。
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from lca.contracts.atoms.enums import HookEvent
from lca.contracts.atoms.telemetry import ATTR_STEP, HOOK_TO_PHASE_SPAN, SpanName
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.observability.diagnostic import DiagnosticCategory
from lca.contracts.protocols import HookRegistry
from lca.layer0_infra.observability import detached_span, observe, set_actor


def _span_name_for_hook(event_name: str) -> str:
    if event_name in HOOK_TO_PHASE_SPAN:
        return HOOK_TO_PHASE_SPAN[event_name]
    if event_name == HookEvent.ON_ERROR:
        return SpanName.ERROR.value
    return f"hook.{event_name}"


def _extract_span_attributes(event_name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    """从 hook kwargs 提取属性（原值；脱敏/截断由属性策略在写入期强制）。"""
    attrs: dict[str, Any] = {"event": event_name}

    state = kwargs.get("state")
    if state is not None:
        if getattr(state, "agent_role", ""):
            attrs["agent_role"] = state.agent_role
        if getattr(state, "from_role", ""):
            attrs["from_role"] = state.from_role
        if getattr(state, "task", ""):
            attrs["task_preview"] = str(state.task)

    decision = kwargs.get("decision")
    if decision is not None:
        attrs["action_type"] = getattr(decision, "action_type", str(decision))
        confidence = getattr(decision, "confidence", None)
        if confidence is not None:
            attrs["confidence"] = confidence
        if getattr(decision, "response_text", ""):
            attrs["response_preview"] = str(decision.response_text)
        if getattr(decision, "tool_name", ""):
            attrs["tool_name"] = decision.tool_name
        delegations = getattr(decision, "delegations", None) or []
        if delegations:
            first = delegations[0]
            target = getattr(first, "target_role", None) or getattr(first, "target_agent_id", None)
            if target:
                attrs["delegate_target"] = target
            if len(delegations) > 1:
                attrs["delegate_count"] = len(delegations)

    error = kwargs.get("error")
    if error is not None:
        attrs["error_type"] = type(error).__name__
        attrs["error_message"] = str(error)

    observation = kwargs.get("observation")
    if observation is not None:
        attrs["observation_success"] = getattr(observation, "success", None)

    reflection = kwargs.get("reflection")
    if reflection is not None:
        attrs["reflection_preview"] = str(reflection)

    return attrs


class CordisHookRegistry(HookRegistry):
    """Lifecycle hooks as a typed projection of cordis events.

    Each ``HookEvent`` value maps to ``hook/<event>`` in the cordis events
    namespace; ``trigger`` dispatches through ``ctx.events.serial`` (last-
    listener-wins — standard for lifecycle hooks: each returns its own
    continuation, the framework ignores the return value when no listener
    transforms it). Phase spans fire at the trigger boundary.
    """

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx

    def register(self, event_name: str, hook: Callable) -> None:
        """Register a hook for *event_name* via cordis events."""
        self._ctx.events.on(_hook_event_name(event_name), hook)

    async def trigger(self, event_name: str, state: AgentState, **kwargs: Any) -> Any:
        # Ambient actor: nested llm/tool/memory span auto-tags, runtime body zero telemetry.
        set_actor(state.agent_role, state.step)
        attrs = _extract_span_attributes(event_name, kwargs)
        attrs[ATTR_STEP] = state.step
        # cordis events.serial / parallel / waterfall only accept positional
        # payloads; we fold state + kwargs into a single envelope so the
        # listener signature stays uniform across all 5 dispatch modes.
        envelope = {"event_name": event_name, "state": state, **kwargs}
        observe(
            DiagnosticCategory.HOOK,
            "hook.trigger",
            plugin="hook_registry.simple",
            attributes={
                "hook_event": event_name,
                "listener_namespace": _hook_event_name(event_name),
                "state_step": state.step,
            },
        )
        with detached_span(_span_name_for_hook(event_name), **attrs):
            return await self._ctx.events.serial(_hook_event_name(event_name), envelope)


def _hook_event_name(event_name: str) -> str:
    """Namespace hook events so they cannot collide with plugin events."""
    if event_name.startswith("hook/"):
        return event_name
    return f"hook/{event_name}"



def cordis_hook_registry(ctx: Any) -> CordisHookRegistry:
    """Return a :class:`CordisHookRegistry` wrapping *ctx*."""
    return CordisHookRegistry(ctx)


# ── Back-compat shim ─────────────────────────────────────────────
#
# Test files / legacy callers that imported ``SimpleHookRegistry``
# pre-cordis-migration still resolve through this alias. The class is
# functionally identical to ``CordisHookRegistry``; the alias exists only
# so existing imports keep working without churn.


class SimpleHookRegistry(CordisHookRegistry):
    """Back-compat alias for :class:`CordisHookRegistry`."""

    def __init__(self, ctx: Any | None = None) -> None:
        if ctx is None:
            # Standalone mode — handlers live on instance attributes (no
            # private dict dispatch table — that's reserved for cordis
            # events). Use the same name-shape as cordis (a list of Hook
            # records keyed by event) so the legacy registry stays a
            # direct projection of the cordis event model.
            from collections import defaultdict

            self._legacy_hooks: Any = defaultdict(list)
            self._legacy_signatures: dict[Callable, str] = {}

            def _register(name: str, hook: Callable) -> None:
                self._legacy_hooks[name].append(hook)
                # Inspect once: detect legacy (event_name, state, **kw)
                # vs cordis envelope (envelope) signatures.
                try:
                    params = list(inspect.signature(hook).parameters)
                except (TypeError, ValueError):
                    params = []
                self._legacy_signatures[hook] = (
                    "legacy" if len(params) >= 2 else "envelope"
                )

            async def _trigger(name: str, state: Any, **kwargs: Any) -> Any:
                envelope = {"event_name": name, "state": state, **kwargs}
                for hook in list(self._legacy_hooks.get(name, [])):
                    sig = self._legacy_signatures.get(hook, "envelope")
                    if sig == "legacy":
                        await hook(name, state, **kwargs)
                    else:
                        await hook(envelope)
                return None

            self.register = _register  # type: ignore[method-assign]
            self.trigger = _trigger  # type: ignore[method-assign]
        else:
            super().__init__(ctx)


__all__ = [
    "CordisHookRegistry",
    "SimpleHookRegistry",
    "cordis_hook_registry",
]
