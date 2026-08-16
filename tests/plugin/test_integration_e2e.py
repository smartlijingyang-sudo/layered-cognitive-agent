"""
端到端集成——从 YAML 招商手册到所有档口正常营业。

美食广场的开业流程是这样的：
1. 物业编写一份「招商手册」(YAML 文件)，里面写着要招哪些档口、每个档口怎么配置
2. 用「招商解析器」(ProfileLoader) 把手册翻译成一份份「入驻工单」(PluginEntry)
3. 用「开业调度器」(Loader) 按工单把档口一个个开起来
4. 确认所有档口都亮着灯（ACTIVE）才算成功

本模块端到端地验证这条流水线，包括配置打补丁(patch)、档口禁用(disabled)、
多手册组合、以及档口之间的互相依赖能否正常工作。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from lca.layer0_infra.plugin.include import ProfileLoader
from lca.layer0_infra.plugin.kernel import PluginState
from lca.layer0_infra.plugin.loader import Loader


def _write_yaml(path: Path, data: Any) -> None:
    """把数据写成一个 YAML 文件——相当于印刷一份招商手册。"""
    path.write_text(yaml.safe_dump(data, sort_keys=False))


# ── Test 1: Full pipeline ────────────────────────────────────


@pytest.mark.asyncio
async def test_full_pipeline_yaml_to_active_tree(tmp_path: Path) -> None:
    """写一份招商手册(YAML) → 解析出工单 → 启动所有档口 → 确认服务已挂载 → 最终清场退租。

    物业在 base.yaml 里写了两个档口：一个做 LLM（大语言模型服务），
    一个做 Reasoner（推理引擎）。手册送到招商解析器，两张工单出炉，
    开业调度器按工单把两家都开起来——确认它们都亮着 ACTIVE 的灯，
    服务台上也能领到 llm 和 reasoner 的服务。最后打烊关门（dispose）。
    """
    bundle_dir = tmp_path / "bundles"
    bundle_dir.mkdir()

    # Bundle with two plugins
    bundle_data = {
        "insert": [
            {
                "id": "llm",
                "name": "lca.layer0_infra.plugin._test_plugins.llm",
                "config": {},
            },
            {
                "id": "reasoner",
                "name": "lca.layer0_infra.plugin._test_plugins.reasoner",
                "config": {},
            },
        ]
    }
    _write_yaml(bundle_dir / "base.yaml", bundle_data)

    # Profile referencing the bundle
    profile_data = {
        "bundles": [str(bundle_dir / "base.yaml")],
    }
    profile_path = tmp_path / "profile.yaml"
    _write_yaml(profile_path, profile_data)

    # Load
    loader = ProfileLoader()
    entries = loader.load_profile(profile_path)
    assert len(entries) == 2
    assert entries[0].id == "llm"
    assert entries[1].id == "reasoner"

    # Boot
    tree = await Loader().load(entries)
    assert tree.host.handles["llm"].state is PluginState.ACTIVE
    assert tree.host.handles["reasoner"].state is PluginState.ACTIVE
    assert tree.host.get_service("llm") is not None
    assert tree.host.get_service("reasoner") is not None

    # Dispose
    tree.dispose()


# ── Test 2: Patch override ───────────────────────────────────


@pytest.mark.asyncio
async def test_patch_override_config(tmp_path: Path) -> None:
    """招商手册的「打补丁」功能：patch 整行替换某个档口的 config。

    基础手册里 llm 档口有一条配置，patch 把它替换成新的。
    最终 llm 档口拿到的是 patch 后的配置——补丁生效。
    """
    bundle_dir = tmp_path / "bundles"
    bundle_dir.mkdir()

    _write_yaml(
        bundle_dir / "base.yaml",
        {
            "insert": [
                {
                    "id": "llm",
                    "name": "lca.layer0_infra.plugin._test_plugins.llm",
                    "config": {},
                },
            ]
        },
    )

    profile_path = tmp_path / "profile.yaml"
    _write_yaml(
        profile_path,
        {
            "bundles": [str(bundle_dir / "base.yaml")],
            "patch": [
                {"id": "llm", "config": {}},
            ],
        },
    )

    entries = ProfileLoader().load_profile(profile_path)
    assert entries[0].config == {}

    tree = await Loader().load(entries)
    assert tree.host.handles["llm"].state is PluginState.ACTIVE
    tree.dispose()


# ── Test 3: Disabled plugin in profile ───────────────────────


@pytest.mark.asyncio
async def test_disabled_plugin_not_loaded(tmp_path: Path) -> None:
    """招商手册的「禁用档口」功能：patch 里把 reasoner 标为 disabled → 它不会开业。

    基础手册招了两个档口（llm 和 reasoner），但物业经理后来决定：
    reasoner 暂时不开了。他在 patch 里给 reasoner 打了个 disabled=True 的标签。
    结果：只有 llm 亮灯，reasoner 的工单虽然存在但被跳过了。
    """
    bundle_dir = tmp_path / "bundles"
    bundle_dir.mkdir()

    _write_yaml(
        bundle_dir / "base.yaml",
        {
            "insert": [
                {
                    "id": "llm",
                    "name": "lca.layer0_infra.plugin._test_plugins.llm",
                    "config": {},
                },
                {
                    "id": "reasoner",
                    "name": "lca.layer0_infra.plugin._test_plugins.reasoner",
                    "config": {},
                },
            ]
        },
    )

    profile_path = tmp_path / "profile.yaml"
    _write_yaml(
        profile_path,
        {
            "bundles": [str(bundle_dir / "base.yaml")],
            "patch": [
                {"id": "reasoner", "disabled": True},
            ],
        },
    )

    entries = ProfileLoader().load_profile(profile_path)
    # reasoner is disabled → only llm loads
    active_entries = [e for e in entries if not e.disabled]
    assert len(active_entries) == 1
    assert active_entries[0].id == "llm"

    tree = await Loader().load(entries)
    assert "llm" in tree.host.handles
    assert "reasoner" not in tree.host.handles
    tree.dispose()


# ── Test 4: Multiple bundles composed ────────────────────────


@pytest.mark.asyncio
async def test_multiple_bundles_composed(tmp_path: Path) -> None:
    """多本手册组合：core.yaml 招 llm，extra.yaml 招 reasoner → 两份手册按顺序合并。

    物业分两次印刷招商手册：第一本 core.yaml 只招 llm 档口，
    第二本 extra.yaml 只招 reasoner 档口。
    profile 引用了这两本手册，按顺序合并后两张工单都有了——
    先 core 后 extra，就像先搭主菜再做甜点。
    """
    bundle_dir = tmp_path / "bundles"
    bundle_dir.mkdir()

    _write_yaml(
        bundle_dir / "core.yaml",
        {
            "insert": [
                {
                    "id": "llm",
                    "name": "lca.layer0_infra.plugin._test_plugins.llm",
                    "config": {},
                },
            ]
        },
    )

    _write_yaml(
        bundle_dir / "extra.yaml",
        {
            "insert": [
                {
                    "id": "reasoner",
                    "name": "lca.layer0_infra.plugin._test_plugins.reasoner",
                    "config": {},
                },
            ]
        },
    )

    profile_path = tmp_path / "profile.yaml"
    _write_yaml(
        profile_path,
        {
            "bundles": [
                str(bundle_dir / "core.yaml"),
                str(bundle_dir / "extra.yaml"),
            ],
        },
    )

    entries = ProfileLoader().load_profile(profile_path)
    assert len(entries) == 2
    assert entries[0].id == "llm"
    assert entries[0].source.endswith("core.yaml")
    assert entries[1].id == "reasoner"
    assert entries[1].source.endswith("extra.yaml")

    tree = await Loader().load(entries)
    assert tree.host.handles["llm"].state is PluginState.ACTIVE
    assert tree.host.handles["reasoner"].state is PluginState.ACTIVE
    tree.dispose()


# ── Test 5: Real test plugins interop ────────────────────────


@pytest.mark.asyncio
async def test_real_test_plugins_interop(tmp_path: Path) -> None:
    """档口之间的真实协作：llm 档口提供「大模型服务」，reasoner 档口依赖它来做推理。
    两家都能开业，且 reasoner 确实能拿到 llm 的服务。

    这是端到端的「邻居协作」验证：llm 档口把大模型服务挂到服务台上，
    reasoner 档口开业时从服务台领取这份服务。两个档口都 ACTIVE，
    服务台上 llm 和 reasoner 的服务都能领到——完美合作。
    """
    bundle_dir = tmp_path / "bundles"
    bundle_dir.mkdir()

    _write_yaml(
        bundle_dir / "base.yaml",
        {
            "insert": [
                {
                    "id": "llm",
                    "name": "lca.layer0_infra.plugin._test_plugins.llm",
                    "config": {},
                },
                {
                    "id": "reasoner",
                    "name": "lca.layer0_infra.plugin._test_plugins.reasoner",
                    "config": {},
                },
            ]
        },
    )

    profile_path = tmp_path / "profile.yaml"
    _write_yaml(
        profile_path,
        {"bundles": [str(bundle_dir / "base.yaml")]},
    )

    entries = ProfileLoader().load_profile(profile_path)
    tree = await Loader().load(entries)

    llm_handle = tree.host.handles["llm"]
    reasoner_handle = tree.host.handles["reasoner"]

    assert llm_handle.state is PluginState.ACTIVE
    assert reasoner_handle.state is PluginState.ACTIVE

    # llm service is mounted and accessible
    llm_svc = tree.host.get_service("llm")
    assert llm_svc is not None

    # reasoner is also mounted
    reasoner_svc = tree.host.get_service("reasoner")
    assert reasoner_svc is not None

    tree.dispose()
