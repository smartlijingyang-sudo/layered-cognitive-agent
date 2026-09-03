"""LoopCursorFactory null provider (PR-7 / ADR-0169 D8 + L13).

把 :class:`InMemoryLoopCursor`(纯内存 cursor,ADR-0169 L13 测试替身)
注册为 ``observability.loop_cursor['null']``。profile 把
``observability.loop_cursor.implementation`` 设为 ``null`` 时,
:class:`~lca_kernel.observability.ObservabilityRuntime.from_profile`
走此 provider —— 派生 cursor 不写 spine(纯状态机测试 / 离线分析场景)。

仓库不暴露独立 ``NullLoopCursor`` 符号(ADR-0169 L13);本 provider
是 ``InMemoryLoopCursor`` 在 seam registry 上的命名别名。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

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
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _null_factory() -> type:
    """Return the in-memory cursor factory class.

    The factory's :meth:`from_profile` builds an :class:`InMemoryLoopCursor`
    using ``spine=None`` so the cursor never writes to a spine. This is the
    ADR-0169 L13 "no spine writes" pattern.
    """
    from lca.infrastructure.observability.loop_cursor.in_memory import InMemoryLoopCursor
    from lca.infrastructure.observability.loop_cursor.state import _CursorState
    from lca.contracts.observability.incarnation import Incarnation

    class _NullLoopCursorFactory:
        """In-memory only LoopCursorFactory(ADR-0169 L13)."""

        @staticmethod
        def from_profile(
            *,
            profile: object,
            run_id: str,
            trace_id: str,
            spine: object = None,
        ) -> tuple:
            _ = spine
            plan_ref = getattr(profile, "plan_ref", "default")
            incarnation = Incarnation(
                run_id=run_id,
                plan_ref=str(plan_ref),
                incarnation_seq=1,
            )
            cursor = InMemoryLoopCursor(
                run_id=run_id,
                trace_id=trace_id,
                incarnation=incarnation,
                spine=None,
            )
            _ = _CursorState  # import marker for static checkers
            return cursor, incarnation

    return _NullLoopCursorFactory


@plugin(
    id="observability.loop_cursor.null",
    requires=["observability.loop_cursor"],
    layer="L1",
    effects="none",
    description="Register InMemoryLoopCursor factory as observability.loop_cursor['null'] (ADR-0169 L13).",
    test_suite="tests/plugins/observability/test_seam_replacement.py::test_loop_cursor_null_provider_registers",
    kind=PluginKind.PROVIDER,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "observability.loop_cursor.null.checked",
                "observability.loop_cursor.null.served",
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
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register the in-memory-only factory into the loop_cursor registry."""
    from lca.infrastructure.observability import NamedRegistry

    del config
    registry: NamedRegistry = ctx.require("observability.loop_cursor")
    registry.register("null", _null_factory())