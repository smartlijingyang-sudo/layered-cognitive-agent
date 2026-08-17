"""Live ctx + 三角色 seam：Definition 拥有键，Provider 挂载，Consumer 只依赖 Definition。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from lca.contracts.mechanisms.capability import REQUIRED_SEAM_KEYS, MissingCapabilityError, SeamKey
from lca.layer0_infra.capability.hub import CapabilityHub
from lca.layer0_infra.capability.llm import LlmService
from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
from lca.layer0_infra.plugin.include._profile import ProfileLoader
from lca.layer0_infra.plugin.loader import Loader
from lca.layer4_app.capability_boot import boot_capabilities


def test_hub_mount_and_require() -> None:
    ctx = CapabilityHub()
    svc = LlmService()
    ctx.mount(SeamKey.LLM.value, svc)
    assert ctx.require(SeamKey.LLM.value) is svc
    assert ctx.llm is svc
    with pytest.raises(MissingCapabilityError):
        ctx.require("nope")


def test_llm_service_dispatches_to_active_provider() -> None:
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


def test_every_required_seam_loaded_by_profile() -> None:
    """base-spine profile mounts every required seam key (plugin-system check)."""

    async def _load() -> None:
        path = Path("profiles/web-standard.yaml")
        entries = ProfileLoader().load_profile(path)
        tree = await Loader(check_seam_completeness=True).load(entries)
        for key in REQUIRED_SEAM_KEYS:
            svc = tree.host.get_service(key.value)
            assert svc is not None, f"Seam {key.value!r} not mounted by base-spine profile"

    asyncio.run(_load())
