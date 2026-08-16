"""楼层规划图测试——从 YAML 到档口列表的完整解析。

美食广场有多层楼，每层的档口安排写在 YAML 文件里：
- Bundle（楼层规划图）：insert 列出本层的档口
- Profile（总体蓝图）：指定用哪些楼层，还可以 patch 微调
- ProfileLoader（总规划师）：读取蓝图、加载模块、输出可执行的档口列表

本模块测试从 YAML 解析到最终招商的完整链路。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from lca.layer0_infra.plugin.include import (
    ProfileError,
    ProfileLoader,
    compose_bundles,
    expand_profile,
)
from lca.layer0_infra.plugin.loader import Loader

# ── Helpers ──────────────────────────────────────────────────


def _write_yaml(path: Path, data: Any) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False))


# ════════════════════════════════════════════════════════════
# 1. Bundle insert —— 楼层规划图的基本单元
# ════════════════════════════════════════════════════════════


class TestBundleInsert:
    """楼层规划图（bundle）的 insert 指令：列出本层要开的档口。"""

    def test_yields_entries_with_correct_id(self, tmp_path: Path) -> None:
        """一个 bundle 可以插入多个档口，按顺序排列。"""
        bundle = tmp_path / "core.yaml"
        _write_yaml(
            bundle,
            {
                "insert": [
                    {"id": "llm", "name": "lca.layer0_infra.plugin._test_plugins.llm"},
                    {"id": "reasoner", "name": "lca.layer0_infra.plugin._test_plugins.reasoner"},
                ],
            },
        )
        entries = compose_bundles([bundle])
        assert [e.id for e in entries] == ["llm", "reasoner"]

    def test_source_tracked(self, tmp_path: Path) -> None:
        """每个档口都记录了来源——知道它来自哪张规划图。"""
        bundle = tmp_path / "core.yaml"
        _write_yaml(
            bundle,
            {
                "insert": [{"id": "llm", "name": "some.module"}],
            },
        )
        entries = compose_bundles([bundle])
        assert entries[0].source == str(bundle)


# ════════════════════════════════════════════════════════════
# 2. Profile expand —— 总体蓝图展开
# ════════════════════════════════════════════════════════════


class TestProfileExpand:
    """总体蓝图（profile）展开：组合多个楼层，支持 patch 微调。

    profile.yaml 指定要用哪些 bundle（楼层），还可以用 patch 做调整：
    - 替换档口配置（浅替换，整行覆盖）
    - 插入新档口
    - 禁用某个档口
    """

    def test_lists_bundles_in_order(self, tmp_path: Path) -> None:
        """多个楼层按顺序组合：先 core 再 extra，档口按此顺序排列。"""
        b1 = tmp_path / "01-core.yaml"
        b2 = tmp_path / "02-extra.yaml"
        _write_yaml(b1, {"insert": [{"id": "a", "name": "mod.a"}]})
        _write_yaml(b2, {"insert": [{"id": "b", "name": "mod.b"}]})

        profile = tmp_path / "profile.yaml"
        _write_yaml(profile, {"bundles": [str(b1), str(b2)]})

        entries = expand_profile(profile)
        assert [e.id for e in entries] == ["a", "b"]

    def test_patch_replaces_config_shallow(self, tmp_path: Path) -> None:
        """patch 可以替换某个档口的配置（浅替换，整行覆盖）。"""
        bundle = tmp_path / "core.yaml"
        _write_yaml(
            bundle,
            {
                "insert": [
                    {"id": "llm", "name": "mod.llm", "config": {"model": "gpt-3", "temp": 0.7}},
                ],
            },
        )
        profile = tmp_path / "profile.yaml"
        _write_yaml(
            profile,
            {
                "bundles": [str(bundle)],
                "patch": [
                    {"id": "llm", "config": {"model": "claude-3"}},
                ],
            },
        )
        entries = expand_profile(profile)
        assert entries[0].config == {"model": "claude-3"}

    def test_patch_adds_entry_via_insert(self, tmp_path: Path) -> None:
        """patch 也可以插入新档口——追加到已有列表末尾。"""
        bundle = tmp_path / "core.yaml"
        _write_yaml(bundle, {"insert": [{"id": "a", "name": "mod.a"}]})
        profile = tmp_path / "profile.yaml"
        _write_yaml(
            profile,
            {
                "bundles": [str(bundle)],
                "patch": [
                    {"insert": [{"id": "b", "name": "mod.b"}]},
                ],
            },
        )
        entries = expand_profile(profile)
        assert [e.id for e in entries] == ["a", "b"]

    def test_patch_disables_entry(self, tmp_path: Path) -> None:
        """patch 可以禁用某个档口——标记 disabled=True，招商时跳过。"""
        bundle = tmp_path / "core.yaml"
        _write_yaml(
            bundle,
            {
                "insert": [
                    {"id": "a", "name": "mod.a"},
                    {"id": "b", "name": "mod.b"},
                ],
            },
        )
        profile = tmp_path / "profile.yaml"
        _write_yaml(
            profile,
            {
                "bundles": [str(bundle)],
                "patch": [{"id": "b", "disabled": True}],
            },
        )
        entries = expand_profile(profile)
        b_entry = next(e for e in entries if e.id == "b")
        assert b_entry.disabled is True


# ════════════════════════════════════════════════════════════
# 3. ProfileLoader —— 总规划师
# ════════════════════════════════════════════════════════════


class TestProfileLoader:
    """总规划师（ProfileLoader）：读取蓝图 → 加载模块 → 输出可执行的档口列表。

    比 expand_profile 更进一步：不仅解析 YAML，还要 import 真正的 Python 模块。
    """

    def test_load_profile_resolves_modules(self, tmp_path: Path) -> None:
        """总规划师能从蓝图加载真正的 Python 模块。"""
        bundle = tmp_path / "core.yaml"
        _write_yaml(
            bundle,
            {
                "insert": [
                    {"id": "llm", "name": "lca.layer0_infra.plugin._test_plugins.llm"},
                ],
            },
        )
        profile = tmp_path / "profile.yaml"
        _write_yaml(profile, {"bundles": [str(bundle)]})

        loader = ProfileLoader()
        entries = loader.load_profile(profile)
        assert len(entries) == 1
        assert entries[0].module is not None
        assert entries[0].module.name == "llm"

    def test_missing_module_raises_profile_error(self, tmp_path: Path) -> None:
        """蓝图里写了一个不存在的模块 → 总规划师报错 ProfileError。"""
        bundle = tmp_path / "core.yaml"
        _write_yaml(
            bundle,
            {
                "insert": [{"id": "ghost", "name": "lca.nonexistent.module"}],
            },
        )
        profile = tmp_path / "profile.yaml"
        _write_yaml(profile, {"bundles": [str(bundle)]})

        loader = ProfileLoader()
        with pytest.raises(ProfileError, match="cannot import"):
            loader.load_profile(profile)

    def test_dump_profile_lists_ids_with_source(self, tmp_path: Path) -> None:
        """dump_profile 返回蓝图摘要：每个档口的 ID 和来源文件。"""
        bundle = tmp_path / "core.yaml"
        _write_yaml(
            bundle,
            {
                "insert": [
                    {"id": "llm", "name": "lca.layer0_infra.plugin._test_plugins.llm"},
                ],
            },
        )
        profile = tmp_path / "profile.yaml"
        _write_yaml(profile, {"bundles": [str(bundle)]})

        loader = ProfileLoader()
        dump = loader.dump_profile(profile)
        assert len(dump) == 1
        assert dump[0]["id"] == "llm"
        assert dump[0]["source"] == str(bundle)


# ════════════════════════════════════════════════════════════
# 4. 端到端 —— 从 YAML 到开业
# ════════════════════════════════════════════════════════════


class TestEndToEnd:
    """端到端测试：从 YAML 蓝图到招商开业的完整流程。"""

    @pytest.mark.asyncio
    async def test_yaml_to_entries_to_active_tree(self, tmp_path: Path) -> None:
        """YAML → 档口列表 → 招商开业 → 所有档口 ACTIVE，设备就绪。"""
        bundle = tmp_path / "core.yaml"
        _write_yaml(
            bundle,
            {
                "insert": [
                    {"id": "llm", "name": "lca.layer0_infra.plugin._test_plugins.llm"},
                    {"id": "reasoner", "name": "lca.layer0_infra.plugin._test_plugins.reasoner"},
                ],
            },
        )
        profile = tmp_path / "profile.yaml"
        _write_yaml(profile, {"bundles": [str(bundle)]})

        pl = ProfileLoader()
        entries = pl.load_profile(profile)
        tree = await Loader().load(entries)

        from lca.layer0_infra.plugin.kernel import PluginState

        assert tree.host.handles["llm"].state is PluginState.ACTIVE
        assert tree.host.handles["reasoner"].state is PluginState.ACTIVE
        # llm provides "llm", reasoner provides "reasoner"
        assert tree.host.get_service("llm") is not None
        assert tree.host.get_service("reasoner") is not None


# ════════════════════════════════════════════════════════════
# 5. 边界情况 —— 各种异常输入
# ════════════════════════════════════════════════════════════


class TestEdgeCases:
    """边界情况：文件不存在、YAML 格式错误、字段缺失等异常输入。"""

    def test_missing_file_raises_profile_error(self, tmp_path: Path) -> None:
        """规划图文件不存在 → ProfileError: not found。"""
        with pytest.raises(ProfileError, match="not found"):
            expand_profile(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml_raises_profile_error(self, tmp_path: Path) -> None:
        """YAML 格式损坏 → ProfileError: YAML invalid。"""
        bad = tmp_path / "bad.yaml"
        bad.write_text("{{invalid:: yaml\n  - [\n")
        with pytest.raises(ProfileError, match="YAML invalid"):
            expand_profile(bad)

    def test_bundle_not_a_mapping_raises(self, tmp_path: Path) -> None:
        """bundle 文件内容不是字典（是列表）→ ProfileError: not a mapping。"""
        bad = tmp_path / "list.yaml"
        _write_yaml(bad, [{"id": "a"}])
        with pytest.raises(ProfileError, match="not a mapping"):
            compose_bundles([bad])

    def test_insert_row_missing_id_raises(self, tmp_path: Path) -> None:
        """insert 里的档口缺少 id 字段 → ProfileError: missing 'id'。"""
        bad = tmp_path / "noid.yaml"
        _write_yaml(bad, {"insert": [{"name": "mod.a"}]})
        with pytest.raises(ProfileError, match="missing 'id'"):
            compose_bundles([bad])

    def test_patch_row_not_mapping_raises(self, tmp_path: Path) -> None:
        """patch 里的条目不是字典 → ProfileError: not a mapping。"""
        bundle = tmp_path / "core.yaml"
        _write_yaml(bundle, {"insert": [{"id": "a", "name": "mod.a"}]})
        profile = tmp_path / "profile.yaml"
        _write_yaml(
            profile,
            {
                "bundles": [str(bundle)],
                "patch": ["not-a-mapping"],
            },
        )
        with pytest.raises(ProfileError, match="not a mapping"):
            expand_profile(profile)

    def test_patch_entry_not_found_logs_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """patch 想修改一个不存在的档口 → 不报错，只记录 warning。"""
        bundle = tmp_path / "core.yaml"
        _write_yaml(bundle, {"insert": [{"id": "a", "name": "mod.a"}]})
        profile = tmp_path / "profile.yaml"
        _write_yaml(
            profile,
            {
                "bundles": [str(bundle)],
                "patch": [{"id": "nonexistent", "config": {"x": 1}}],
            },
        )
        # Should not raise — just log a warning
        entries = expand_profile(profile)
        assert len(entries) == 1
        assert entries[0].id == "a"
