"""observation.lifecycle.plan_compile —— plan 编译产物的观察者(Observer 函数)。

设计模式: 装饰器 + 模块级 observer callable。
- @plugin(...) 是唯一入口,声明 provides/requires/effects。
- setup() 把模块级 ``observe_plan_compile`` 函数注册成 capability,
  外部 caller 通过 ``ctx.use("observation.plan_compile").on_plan_compiled(...)``
  调用,函数内部构造 PlanBlueprint + PlanCompileComplete 两个 fact 并走
  Session.append 单轨 emit。
- 不引入 class wrapper、不引入 _shared module、不引入 base mixin。

模块 M4(lifecycle): 对应 contract lca/contracts/observability/observation/m4_lifecycle/
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from lca.contracts.observability.observation import (
    PlanBlueprint,
    PlanCompileComplete,
)
from lca.contracts.observability.observation.m1_blueprint import (
    PlanEdgeSpec,
    PlanNodeSpec,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.loop.fact_gateway import append_surface_bound

_EV_PLAN_BLUEPRINT = "observation.plan_blueprint"
_EV_PLAN_COMPILE_OK = "observation.plan_compile.complete"
_OBSERVER_ACTOR = "observation"


class PlanCompileObserver(Protocol):
    """Observer 协议 —— caller 看到的最小 surface。"""

    def on_plan_compiled(
        self,
        *,
        run_id: str,
        plan_ref: str,
        profile_path: str,
        plan_version: str,
        revision: str,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        actions_authorized: list[str] | None = None,
        capabilities_granted: list[str] | None = None,
        effect_policy: dict[str, Any] | None = None,
    ) -> None: ...


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def observe_plan_compile(
    *,
    run_id: str,
    plan_ref: str,
    profile_path: str,
    plan_version: str,
    revision: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    actions_authorized: list[str] | None = None,
    capabilities_granted: list[str] | None = None,
    effect_policy: dict[str, Any] | None = None,
) -> None:
    """Observer 函数 —— caller 直接 import 调用,不绕 class wrapper。"""
    now = _now_iso()
    node_specs = tuple(
        PlanNodeSpec(
            id=n["id"],
            phase=n["phase"],
            binding=n.get("binding"),
            sub_spec_ref=n.get("sub_spec_ref"),
            max_visits=n.get("max_visits", 8),
            entry=n.get("entry", False),
            terminal=n.get("terminal", False),
            preconditions=tuple(n.get("preconditions", ())),
            terminal_predicates=tuple(n.get("terminal_predicates", ())),
        )
        for n in nodes
    )
    edge_specs = tuple(
        PlanEdgeSpec(
            **{"from": e["from"], "to": e["to"]},
            when=e.get("when", "true"),
            priority=e.get("priority", 0),
        )
        for e in edges
    )
    blueprint = PlanBlueprint(
        plan_ref=plan_ref,
        profile_path=profile_path,
        plan_version=plan_version,
        revision=revision,
        nodes=node_specs,
        edges=edge_specs,
        actions_authorized=tuple(actions_authorized or ()),
        capabilities_granted=tuple(capabilities_granted or ()),
        effect_policy=effect_policy or {},
        compiled_at=now,
    )
    append_surface_bound(
        _EV_PLAN_BLUEPRINT,
        blueprint.model_dump(mode="json"),
        actor=_OBSERVER_ACTOR,
        surface_op="append",
        visibility="model",
    )
    compile_ok = PlanCompileComplete(
        run_id=run_id,
        plan_ref=plan_ref,
        profile_path=profile_path,
        compiled_at=now,
    )
    append_surface_bound(
        _EV_PLAN_COMPILE_OK,
        compile_ok.model_dump(mode="json"),
        actor=_OBSERVER_ACTOR,
        surface_op="append",
        visibility="model",
    )


@plugin(
    id="observation.lifecycle.plan_compile",
    provides=("observation.plan_compile",),
    requires=(),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "Plan compile observer —— 接收 CompiledRunPlan 走 Session.append "
        "emit PlanBlueprint + PlanCompileComplete。"
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """把 ``observe_plan_compile`` 函数注册成 capability,无 class wrapper。"""
    del config
    observer: Callable[..., None] = observe_plan_compile
    ctx.provide("observation.plan_compile", observer)


__all__ = ["observe_plan_compile", "setup"]
