"""Live ctx + 三角色 seam：Definition 拥有键，Provider 挂载，Consumer 只依赖 Definition。"""

from __future__ import annotations

import pytest

from lca.contracts.mechanisms.capability import REQUIRED_SEAM_KEYS, MissingCapabilityError, SeamKey
from lca.contracts.mechanisms.seam import SeamRole, get_global_seam_registry
from lca.layer0_infra.capability.hub import CapabilityHub
from lca.layer0_infra.capability.llm import LlmService
from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
from lca.layer4_app.capability_boot import boot_capabilities, register_seam_catalog


def test_hub_mount_and_require() -> None:
    ctx = CapabilityHub()
    svc = LlmService()
    ctx.mount(SeamKey.LLM.value, svc)
    assert ctx.require(SeamKey.LLM.value) is svc
    assert ctx.llm is svc
    with pytest.raises(MissingCapabilityError):
        ctx.require("nope")


def test_llm_service_dispatches_to_active_provider() -> None:
    import asyncio

    svc = LlmService()
    svc.register("mock", MockLLMAdapter(), activate=True)

    async def _run() -> str:
        return (await svc.complete("say hi")).text

    text = asyncio.run(_run())
    assert isinstance(text, str)


def test_boot_mounts_every_required_key() -> None:
    ctx = boot_capabilities()
    for key in REQUIRED_SEAM_KEYS:
        assert ctx.get(key.value) is not None, key


def test_every_required_seam_has_three_roles() -> None:
    register_seam_catalog()
    registry = get_global_seam_registry()
    for key in REQUIRED_SEAM_KEYS:
        roles = registry.get_roles(key.value)
        assert SeamRole.DEFINITION in roles, key
        assert SeamRole.PROVIDER in roles, key
        assert SeamRole.CONSUMER in roles, key
        assert registry.is_complete(key.value), key
