"""Profile 输入适配层的独立契约测试。"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from lca.harness.profile.runtime_closure import FallbackPolicy
from lca.harness.profile.source import load_profile_source


def _write_profile_fixture(tmp_path: Path, *, profile_body: str) -> Path:
    bundle = tmp_path / "bundle.yaml"
    bundle.write_text(
        "entries:\n"
        "  - id: test.plugin\n"
        "    $module: package.not_imported\n"
        "    config:\n"
        "      nested:\n"
        "        base: retained\n"
    )
    profile = tmp_path / "profile.yaml"
    profile.write_text(profile_body)
    return profile


def test_load_profile_source_adapts_yaml_without_importing_plugin_modules(tmp_path: Path) -> None:
    profile = _write_profile_fixture(
        tmp_path,
        profile_body=(
            "bundles:\n"
            "  - bundle.yaml\n"
            "patch:\n"
            "  - id: test.plugin\n"
            "    config:\n"
            "      nested:\n"
            "        patched:\n"
            "          from_env: PATCHED_VALUE\n"
            "      api_token:\n"
            "        from_env: API_TOKEN\n"
            "fallback_policy:\n"
            "  optional_capability: off\n"
        ),
    )

    source = load_profile_source(
        profile,
        env={"PATCHED_VALUE": "applied", "API_TOKEN": "secret-value"},
    )

    assert source.bundles == ("bundle.yaml",)
    assert source.entries[0]["$module"] == "package.not_imported"
    assert source.entries[0]["config"] == {
        "nested": {"base": "retained", "patched": "applied"},
        "api_token": SecretStr("secret-value"),
    }
    assert source.entries[0]["_config_sources"] == {
        "nested": f"{profile}#patch.test.plugin.nested.patched",
        "api_token": f"{profile}#patch.test.plugin.api_token",
    }
    assert source.entries[0]["_env_refs"] == [
        ("test.plugin", "nested.patched", False),
        ("test.plugin", "api_token", False),
    ]
    assert source.sources["test.plugin"].endswith("bundle.yaml+patch")
    assert source.fallback_policy == {"optional_capability": FallbackPolicy.OFF.value}
    with pytest.raises(TypeError):
        source.sources["test.plugin"] = "mutated"  # type: ignore[index]


def test_load_profile_source_skips_environment_expansion_for_disabled_plugins(
    tmp_path: Path,
) -> None:
    profile = _write_profile_fixture(
        tmp_path,
        profile_body=(
            "bundles:\n"
            "  - bundle.yaml\n"
            "patch:\n"
            "  - id: test.plugin\n"
            "    disabled: true\n"
            "    config:\n"
            "      api_key:\n"
            "        from_env: REQUIRED_KEY\n"
            "        required: true\n"
        ),
    )

    source = load_profile_source(profile, env={})

    assert source.entries[0]["disabled"] is True
    assert source.entries[0]["config"]["api_key"] == {
        "from_env": "REQUIRED_KEY",
        "required": True,
    }
    assert "_env_refs" not in source.entries[0]
