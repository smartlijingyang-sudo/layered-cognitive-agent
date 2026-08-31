"""DeltaHandler Provider plugin — Tier-2 (ADR-0074 + ADR-0070).

提供 ``DeltaHandlerRegistry`` 的默认实现，把 ``RunDelta`` 折叠到 ``AgentState``。
每个 handler 负责一种 Reducer 操作（``step`` / ``perception`` / ``turn`` / 等），
通过 ``reducer.apply_*`` 完成 state mutation（宪法 C4：Reducer 唯一写）。

``RegistryDeltaReducer`` 只调度本 provider 注册的操作。本 provider 覆盖
全部 11 个 Reducer 操作，并由 boot 阶段校验无遗漏，避免静默丢弃 delta。

**关键修正**：``RunDelta`` 无 ``payload`` / ``value`` 属性——数据存储在
``delta.metadata`` 中。每个 handler 从 metadata 提取对应字段并调用
``reducer.apply_*``。

ADR-0074：把所有 Reducer 操作的可插拔 handler 注册到 registry，runtime 启动时
校验 11 个操作全部覆盖，不再允许静默丢弃。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.activation import ActivatedSkill
from lca.contracts.models.core.decision import Turn
from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.core.stop import StopDecision
from lca.contracts.protocols.act.command_envelope import RunDelta
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.state.delta_handler import DeltaHandler, DeltaHandlerRegistry
from lca.contracts.protocols.state.reducer import Reducer
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.providers.act.delta_handler_registry import (
    DefaultDeltaHandlerRegistry,
    InMemoryDeltaHandlerRegistry,
    register_default_delta_handlers,
)


class Config(BaseModel):
    """Delta handler provider 配置（当前无字段，预留扩展）。"""

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Handler 实现
# ---------------------------------------------------------------------------


class StepDeltaHandler(DeltaHandler):
    """处理 ``step`` delta：调用 ``reducer.apply_step_advanced``。

    ADR-0074：从 ``delta.metadata["step"]`` 提取 step 值（int），更新
    state.step 与 state.budget.used_steps。
    """

    def apply(self, state: AgentState, delta: RunDelta, reducer: Reducer) -> AgentState:
        step: int = delta.metadata.get("step", state.step)
        return reducer.apply_step_advanced(state, step)


class PerceptionDeltaHandler(DeltaHandler):
    """处理 ``perception`` delta：调用 ``reducer.apply_perception``。

    ADR-0074：从 ``delta.metadata["manifest"]`` 提取 ContextManifest，折叠
    到 state（C3 唯一事实源）。
    """

    def apply(self, state: AgentState, delta: RunDelta, reducer: Reducer) -> AgentState:
        manifest: ContextManifest = delta.metadata["manifest"]
        return reducer.apply_perception(state, manifest)


class TurnDeltaHandler(DeltaHandler):
    """处理 ``turn`` delta：调用 ``reducer.apply_turn``。

    ADR-0074：从 ``delta.metadata`` 提取 Turn。优先读取 ``metadata["turn"]``
    （预构造的 Turn 对象）；否则从 ``decision`` / ``observation`` / ``reflection``
    组件构造 Turn（兼容 common.py 的标准 phase executor 输出）。
    """

    def apply(self, state: AgentState, delta: RunDelta, reducer: Reducer) -> AgentState:
        turn: Turn = _extract_turn(delta.metadata)
        return reducer.apply_turn(state, turn)


def _extract_turn(metadata: dict[str, Any]) -> Turn:
    """从 metadata 提取 Turn：优先 ``metadata["turn"]``，否则从组件构造。

    common.py 的 StandardPhaseExecutor 将 decision / observation / reflection
    分别放入 metadata，而非预构造 Turn 对象。本函数兼容两种格式。
    """
    if "turn" in metadata:
        return metadata["turn"]
    # 从组件构造 Turn（兼容 common.py 的标准输出）
    return Turn(
        decision=metadata["decision"],
        observation=metadata["observation"],
        reflection=metadata.get("reflection"),
    )


class SkillRouteDeltaHandler(DeltaHandler):
    """处理 ``skill_route`` delta：调用 ``reducer.apply_skill_route``。

    ADR-0074：从 ``delta.metadata["active_template"]``
    提取 SkillRouter.route() 返回的 prompt 模板名，折叠到 state。
    """

    def apply(self, state: AgentState, delta: RunDelta, reducer: Reducer) -> AgentState:
        active_template: str | None = delta.metadata.get("active_template")
        return reducer.apply_skill_route(state, active_template)


class ActivationDeltaHandler(DeltaHandler):
    """处理 ``activation`` delta：调用 ``reducer.apply_activation``。

    ADR-0074：从 ``delta.metadata["activated"]``
    提取 tuple[ActivatedSkill, ...]，同步 state.activated_skills。
    """

    def apply(self, state: AgentState, delta: RunDelta, reducer: Reducer) -> AgentState:
        activated: tuple[ActivatedSkill, ...] = delta.metadata.get("activated", ())
        return reducer.apply_activation(state, activated)


class MemoryDeltaHandler(DeltaHandler):
    """处理 ``memory`` delta：调用 ``reducer.apply_memory``。

    ADR-0074：从 ``delta.metadata["writes"]`` 提取 MemoryWriteSet，折叠到
    state。common.py 的 memory delta 不带 writes 字段，此时传 ``None``。
    """

    def apply(self, state: AgentState, delta: RunDelta, reducer: Reducer) -> AgentState:
        writes: object = delta.metadata.get("writes")
        return reducer.apply_memory(state, writes)


class StopDeltaHandler(DeltaHandler):
    """处理 ``stop`` delta：调用 ``reducer.apply_stop``。

    ADR-0074：从 ``delta.metadata["stop"]`` 提取 StopDecision，折叠到
    state.final_output / state.status。
    """

    def apply(self, state: AgentState, delta: RunDelta, reducer: Reducer) -> AgentState:
        stop: StopDecision = delta.metadata["stop"]
        return reducer.apply_stop(state, stop)


class ErrorDeltaHandler(DeltaHandler):
    """处理 ``error`` delta：调用 ``reducer.apply_error``。

    ADR-0074：从 ``delta.metadata["error"]``
    提取 BaseException，标记 FAILED 并写入 state.last_error。
    """

    def apply(self, state: AgentState, delta: RunDelta, reducer: Reducer) -> AgentState:
        error: BaseException = delta.metadata["error"]
        return reducer.apply_error(state, error)


class ResumeDeltaHandler(DeltaHandler):
    """处理 ``resume`` delta：调用 ``reducer.apply_resume``。

    ADR-0074：从 ``delta.metadata`` 提取
    ``input_value`` 和 ``turn``（两者均可选），恢复已加载状态并可选地折叠
    人工输入对应的 Turn。
    """

    def apply(self, state: AgentState, delta: RunDelta, reducer: Reducer) -> AgentState:
        input_value: object | None = delta.metadata.get("input_value")
        turn: Turn | None = None
        if "turn" in delta.metadata:
            turn = delta.metadata["turn"]
        elif "decision" in delta.metadata:
            turn = _extract_turn(delta.metadata)
        return reducer.apply_resume(state, input_value, turn)


class ArtifactClosureDeltaHandler(DeltaHandler):
    """处理 ``artifact_closure`` delta：调用 ``reducer.apply_artifact_closure``。

    ADR-0074：从 ``delta.metadata["closure"]``
    提取闭合文本（str），折叠交付物闭合文本并标记完成。
    """

    def apply(self, state: AgentState, delta: RunDelta, reducer: Reducer) -> AgentState:
        closure: str = delta.metadata.get("closure", "")
        return reducer.apply_artifact_closure(state, closure)


class PausedDeltaHandler(DeltaHandler):
    """处理 ``paused`` delta：调用 ``reducer.apply_paused``。

    ADR-0074：从 ``delta.metadata["snapshot_ref"]``
    提取 snapshot 引用，标记 INPUT_REQUIRED（HIL 等待审批）。
    """

    def apply(self, state: AgentState, delta: RunDelta, reducer: Reducer) -> AgentState:
        snapshot_ref: object = delta.metadata.get("snapshot_ref")
        return reducer.apply_paused(state, snapshot_ref)


# ---------------------------------------------------------------------------
# Plugin setup
# ---------------------------------------------------------------------------


@plugin(
    id="lca-delta-handler-provider",
    requires=["delta_handler_registry"],
    implements=[DeltaHandlerRegistry],
    layer="L2",
    effects="none",
    description=(
        "Register default DeltaHandler implementations for all 11 Reducer operations. "
        "Boot-time validation ensures no operation is silently dropped (ADR-0074)."
    ),
    test_suite="tests/test_plugin_alignment.py::test_tier2_plugin_shape",
    kind=PluginKind.PROVIDER,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-delta-handler-provider.checked", "lca-delta-handler-provider.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """注册 11 个默认 DeltaHandler 到 registry。

    ADR-0074：注册全部 11 个 Reducer 操作，并由 boot 阶段校验无遗漏。
    """
    registry: DeltaHandlerRegistry = ctx.require("delta_handler_registry")

    register_default_delta_handlers(registry)


__all__ = [
    "ActivationDeltaHandler",
    "ArtifactClosureDeltaHandler",
    "Config",
    "DefaultDeltaHandlerRegistry",
    "ErrorDeltaHandler",
    "InMemoryDeltaHandlerRegistry",
    "MemoryDeltaHandler",
    "PausedDeltaHandler",
    "PerceptionDeltaHandler",
    "ResumeDeltaHandler",
    "SkillRouteDeltaHandler",
    "StepDeltaHandler",
    "StopDeltaHandler",
    "TurnDeltaHandler",
    "register_default_delta_handlers",
    "setup",
]
