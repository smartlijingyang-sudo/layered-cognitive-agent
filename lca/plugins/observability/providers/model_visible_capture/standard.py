"""ModelVisibleCapture standard provider (PR-7 / ADR-0169 D7 + D8).

把 :class:`StdModelVisibleCapture`(默认 LLM 边界 5 件套捕获)
注册为 ``observability.model_visible['standard']``。
profile 装配阶段 :class:`~lca_kernel.observability.ObservabilityRuntime.from_profile`
从 ``profile.runs_root`` 或入参 ``run_dir`` 取路径后构造。
"""

from __future__ import annotations

from typing import Any

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


def _make_model_visible_capture(run_dir: Any, **_: Any) -> Any:
    """Build a :class:`StdModelVisibleCapture` rooted at ``run_dir``."""
    from pathlib import Path

    from lca.infrastructure.observability.loop_cursor.model_visible_capture import (
        StdModelVisibleCapture,
    )

    return StdModelVisibleCapture(run_dir=Path(run_dir))


@plugin(
    id="observability.model_visible.standard",
    requires=["observability.model_visible"],
    layer="L1",
    effects="filesystem",
    description="Register StdModelVisibleCapture factory as observability.model_visible['standard'].",
    test_suite="tests/plugins/observability/test_seam_replacement.py::test_model_visible_standard_provider_registers",
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
                "observability.model_visible.standard.checked",
                "observability.model_visible.standard.served",
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
    """Register the standard factory; ``from_profile`` passes ``run_dir`` per call."""
    from lca.infrastructure.observability import NamedRegistry

    del config
    registry: NamedRegistry = ctx.require("observability.model_visible")
    registry.register("standard", _make_model_visible_capture)
    registry.register("default", _make_model_visible_capture)