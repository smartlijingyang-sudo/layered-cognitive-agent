"""Bridge existing HookRegistry calls onto MiddlewareRegistry seams."""

from __future__ import annotations

from typing import Any

from lca.contracts.harness.middleware import MiddlewareRegistration
from lca.contracts.mechanisms import HookRegistry

HOOK_SEAMS: tuple[tuple[str, str], ...] = (
    ("agent.before_perceive", "pre_perceive"),
    ("agent.after_perceive", "post_perceive"),
    ("agent.before_think", "pre_think"),
    ("agent.after_think", "post_think"),
    ("agent.before_act", "pre_act"),
    ("agent.after_act", "post_act"),
    ("agent.before_reflect", "pre_reflect"),
    ("agent.after_reflect", "post_reflect"),
)

_MW_BAG = "_middleware_bag"


def middleware_bag(state: Any) -> dict[str, Any]:
    extra = getattr(state, "extra", None)
    if extra is None:
        return {}
    bag = extra.get(_MW_BAG)
    if not isinstance(bag, dict):
        bag = {}
        extra[_MW_BAG] = bag
    return bag


def install_hook_bridge(registry: Any, hooks: HookRegistry) -> None:
    """Register hook-triggering middleware so the loop only calls ``registry.run``."""

    for seam_key, hook_name in HOOK_SEAMS:

        async def _mw(
            phase: str,
            state: Any,
            context: Any,
            *,
            _hook: str = hook_name,
            _hooks: HookRegistry = hooks,
        ) -> Any:
            bag = middleware_bag(state)
            kwargs: dict[str, Any] = {}
            for key in ("decision", "observation", "reflection", "error"):
                if key in bag:
                    kwargs[key] = bag[key]
            await _hooks.trigger(_hook, state, **kwargs)
            return state

        registry.register(
            MiddlewareRegistration(
                seam_key=seam_key,
                priority=80,
                plugin_id="lca.runtime.hook_bridge",
            ),
            _mw,
        )
