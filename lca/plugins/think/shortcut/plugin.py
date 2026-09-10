"""phase.think.shortcut — try a deterministic shortcut before reason.

ADR-0217 §3.3:本 plugin 实现 NodeExecutor 协议(think 子图专用),同时保留
@plugin(...) 装饰器注册(Cordis 容器兼容)。两种注册互不替代:
- @plugin(...) 走 Cordis 容器 / capability 体系(老机制,本 ADR 不动)
- FactoryRegistry.register(本 plugin 的 setup() 里调)走新 NodeExecutor 解析
  (think 子图专用,新机制)
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.plugins.think.step_plugin_spec import step_plugin_spec
from lca.contracts.models.core.execution.think_carry import CARRY_KEY, ThinkSubgraphCarry
from lca.contracts.protocols import SupportsShortcut
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
)
from lca.contracts.protocols.declarative.declarative_1.factory_resolver import (
    get_default_registry,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeExecutor,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.loop.phase._shared.common import StandardPhaseConfig

# 双注册共用常量
_SEMANTIC_NAME = "think.shortcut"
_REGION = "phase:think"

STAGE_KIND = "think_stage"

SPEC = step_plugin_spec(
    plugin_id="phase.think.shortcut",
    module="lca.plugins.think.shortcut.plugin",
    test_suite="tests/think/test_shortcut_phase_plugin.py",
)


def _carry(context: PhaseContext) -> ThinkSubgraphCarry:
    """老 caller 兼容:从 context.artifacts 取/新建 ThinkSubgraphCarry。

    新 caller(think 子图)通过 NodeContext 走,不依赖此 helper。
    """
    existing = context.artifacts.get(CARRY_KEY)
    if isinstance(existing, ThinkSubgraphCarry):
        return existing
    return ThinkSubgraphCarry(state=context.state)


@dataclass(frozen=True, slots=True)
class ThinkShortcutExecutor:
    """think 节点实现。

    同一实例同时实现两个协议:
    - 老 ``PhaseExecutor``(向后兼容 Cordis 调用方):保留 ``execute(ctx, inp)`` 签名
    - 新 ``NodeExecutor``:通过 ``node_execute`` 方法暴露,框架按
      ``FactoryRegistry.resolve("think.shortcut", "phase:think")`` 命中

    为什么分两个方法、不直接同名:PhaseExecutor 的 ctx/inp 与 NodeExecutor 的
    ctx/inp 是不同类型,签名一致但语义不同;保留两个方法名让维护者一眼分清。
    """

    semantic_name: str = _SEMANTIC_NAME

    # --- 老 PhaseExecutor(perceive/think/act/reflect/remember/stop 共享) ---
    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        # 老 PhaseExecutor 路径(保留 carry 语义,兼容 tests + 老 caller)
        carry = _carry(context)
        cap = context.capabilities.get("phase.think.shortcut")
        if cap is None:
            return PhaseResult(result_kind=STAGE_KIND, payload=carry)
        assert isinstance(cap, SupportsShortcut), (  # noqa: S101
            "phase.think.shortcut must implement SupportsShortcut"
        )
        decision = await cap.try_shortcut(context.state)
        if decision is None:
            return PhaseResult(result_kind=STAGE_KIND, payload=carry)
        return PhaseResult(result_kind="decision", payload=decision)

    # --- 新 NodeExecutor(think 子图专用) ---
    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """think 子图节点入口。

        inputs 端口声明(yaml):
          - in_assembled_manifest: 装载过的 manifest,plugin 自己从
            ``context.runtime["state"]`` 取,不在 port_values 里塞

        outputs 端口声明(yaml):
          - decision: 若 shortcut 命中,返回 Decision;否则不写(由边 when 走下一节点)
        """
        runtime = context.runtime
        state = runtime.get("state") if isinstance(runtime, dict) else None
        cap = runtime.get("supports_shortcut") if isinstance(runtime, dict) else None

        if cap is None or state is None:
            # 节点拿不到必备上下文 → 让 interpreter 走 when 路由,不报错
            return NodeOutput(port_values={})

        assert isinstance(cap, SupportsShortcut), (  # noqa: S101
            "think.shortcut runtime['supports_shortcut'] must implement SupportsShortcut"
        )
        decision = await cap.try_shortcut(state)
        if decision is None:
            return NodeOutput(port_values={})
        return NodeOutput(port_values={"decision": decision}, next_hint="shortcut_taken")


@plugin(
    id="phase.think.shortcut",
    Config=StandardPhaseConfig,
    provides=("phase.think.shortcut",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/think/test_shortcut_phase_plugin.py",
    spec=SPEC,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_think_shortcut.checked",
                "phase_think_shortcut.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    """Cordis 注册 + FactoryRegistry 注册双轨。

    双注册互不替代:
    - ctx.provide 把 PhaseExecutor 形式塞进 Cordis(老 caller 拿这个)
    - FactoryRegistry.register 把 NodeExecutor 形式塞进程级注册表(新 caller 拿这个)
    """
    del config
    executor = ThinkShortcutExecutor()
    ctx.provide("phase.think.shortcut", executor)
    get_default_registry().register(
        executor,
        semantic_name=_SEMANTIC_NAME,
        region=_REGION,
    )


def create_executor() -> ThinkShortcutExecutor:
    return ThinkShortcutExecutor()


__all__ = ["ThinkShortcutExecutor", "create_executor", "setup"]
