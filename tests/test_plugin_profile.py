"""Profile 组合测试 —— YAML 展开 + bundle 叠加 + patch 替换 + dump。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lca.layer0_infra.plugin.include import (
    ProfileError,
    ProfileLoader,
    compose_bundles,
    expand_profile,
)
from lca.layer0_infra.plugin.loader import Loader


@pytest.fixture
def profile_dir(tmp_path: Path) -> Path:
    """创建最小可用的 profile 目录。"""
    bundles = tmp_path / "bundles"
    profiles = tmp_path / "profiles"
    bundles.mkdir()
    profiles.mkdir()
    return tmp_path


def _write_yaml(path: Path, data: object) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False))


class TestBundleInsert:
    def test_bundle_insert_yields_entries(self, profile_dir: Path) -> None:
        bundle = profile_dir / "bundles" / "lca_base.yaml"
        _write_yaml(
            bundle,
            {
                "insert": [
                    {"id": "llm", "name": "lca.layer0_infra.plugin._test_plugins.llm"},
                ]
            },
        )
        entries = compose_bundles([bundle])
        assert [e.id for e in entries] == ["llm"]
        assert entries[0].source == str(bundle)


class TestProfileExpand:
    def test_profile_lists_bundles(self, profile_dir: Path) -> None:
        base = profile_dir / "bundles" / "lca_base.yaml"
        cog = profile_dir / "bundles" / "lca_cognitive.yaml"
        _write_yaml(
            base,
            {"insert": [{"id": "llm", "name": "fake.llm"}]},
        )
        _write_yaml(
            cog,
            {"insert": [{"id": "reasoner", "name": "fake.reasoner"}]},
        )
        prof = profile_dir / "profiles" / "test.yaml"
        _write_yaml(
            prof,
            {
                "bundles": [str(base), str(cog)],
            },
        )
        entries = expand_profile(prof)
        assert [e.id for e in entries] == ["llm", "reasoner"]

    def test_profile_patch_replaces_config(self, profile_dir: Path) -> None:
        base = profile_dir / "bundles" / "lca_base.yaml"
        _write_yaml(
            base,
            {"insert": [{"id": "compaction", "name": "fake.compaction", "config": {"x": 1}}]},
        )
        prof = profile_dir / "profiles" / "test.yaml"
        _write_yaml(
            prof,
            {
                "bundles": [str(base)],
                "patch": [{"id": "compaction", "config": {"x": 99, "y": 2}}],
            },
        )
        entries = expand_profile(prof)
        compaction = next(e for e in entries if e.id == "compaction")
        # patch 整行替换 config（不深合并）
        assert compaction.config == {"x": 99, "y": 2}

    def test_profile_patch_adds_entry(self, profile_dir: Path) -> None:
        base = profile_dir / "bundles" / "lca_base.yaml"
        _write_yaml(base, {"insert": [{"id": "llm", "name": "fake.llm"}]})
        prof = profile_dir / "profiles" / "test.yaml"
        _write_yaml(
            prof,
            {
                "bundles": [str(base)],
                "patch": [{"insert": [{"id": "extra", "name": "fake.extra"}]}],
            },
        )
        entries = expand_profile(prof)
        assert [e.id for e in entries] == ["llm", "extra"]

    def test_profile_patch_disables_entry(self, profile_dir: Path) -> None:
        base = profile_dir / "bundles" / "lca_base.yaml"
        _write_yaml(
            base,
            {"insert": [{"id": "llm", "name": "fake.llm"}, {"id": "mock", "name": "fake.mock"}]},
        )
        prof = profile_dir / "profiles" / "test.yaml"
        _write_yaml(
            prof,
            {
                "bundles": [str(base)],
                "patch": [{"id": "mock", "disabled": True}],
            },
        )
        entries = expand_profile(prof)
        assert [e.id for e in entries] == ["llm", "mock"]
        assert next(e for e in entries if e.id == "mock").disabled is True


class TestProfileLoader:
    def test_load_profile_resolves_modules(self, profile_dir: Path, monkeypatch) -> None:
        """ProfileLoader 解析 name 为模块，返回 PluginEntry。"""

        base = profile_dir / "bundles" / "lca_base.yaml"
        _write_yaml(
            base,
            {"insert": [{"id": "llm", "name": "lca.layer0_infra.plugin._test_plugins.llm"}]},
        )
        prof = profile_dir / "profiles" / "test.yaml"
        _write_yaml(prof, {"bundles": [str(base)]})
        entries = ProfileLoader().load_profile(prof)
        assert len(entries) == 1
        assert entries[0].module.name == "llm"

    def test_load_profile_missing_name_raises(self, profile_dir: Path) -> None:
        base = profile_dir / "bundles" / "lca_base.yaml"
        _write_yaml(base, {"insert": [{"id": "llm", "name": "no.such.module"}]})
        prof = profile_dir / "profiles" / "test.yaml"
        _write_yaml(prof, {"bundles": [str(base)]})
        with pytest.raises(ProfileError):
            ProfileLoader().load_profile(prof)

    def test_dump_profile_lists_ids(self, profile_dir: Path) -> None:
        base = profile_dir / "bundles" / "lca_base.yaml"
        _write_yaml(
            base,
            {
                "insert": [
                    {"id": "llm", "name": "fake.llm"},
                    {"id": "tools", "name": "fake.tools"},
                ]
            },
        )
        prof = profile_dir / "profiles" / "test.yaml"
        _write_yaml(prof, {"bundles": [str(base)]})
        dump = ProfileLoader().dump_profile(prof)
        assert [row["id"] for row in dump] == ["llm", "tools"]
        assert all("source" in row for row in dump)


class TestEndToEnd:
    @pytest.mark.asyncio
    async def test_full_pipeline_profile_to_loaded_tree(self, profile_dir: Path) -> None:
        base = profile_dir / "bundles" / "lca_base.yaml"
        _write_yaml(
            base,
            {
                "insert": [
                    {"id": "llm", "name": "lca.layer0_infra.plugin._test_plugins.llm"},
                    {
                        "id": "reasoner",
                        "name": "lca.layer0_infra.plugin._test_plugins.reasoner",
                    },
                ]
            },
        )
        prof = profile_dir / "profiles" / "test.yaml"
        _write_yaml(prof, {"bundles": [str(base)]})
        entries = ProfileLoader().load_profile(prof)
        tree = await Loader().load(entries)
        assert tree.host.get_service("llm") is not None
        assert tree.host.get_service("reasoner") is not None
        tree.dispose()
