"""Host runtime YAML SSOT — config load, user resolution, default template."""

from __future__ import annotations

from pathlib import Path

from lca.layer0_infra.host_runtime.config import DEFAULT_YAML, HostRuntimeConfig, UserConfig


def test_default_yaml_loads() -> None:
    config = HostRuntimeConfig.model_validate(__import__("yaml").safe_load(DEFAULT_YAML))
    assert config.paths.cli_dir == "/opt/lca"
    assert config.paths.venv_dir == "/opt/lca/venv"
    assert config.find_user("sandbox-user") is not None
    user = config.find_user("sandbox-user")
    assert user is not None
    assert user.home == "/home/sandbox-user"
    assert user.outputs_dir == "/home/sandbox-user/outputs"
    assert user.state_dir == "/home/sandbox-user/.lca"


def test_user_home_defaults_from_name() -> None:
    user = UserConfig(name="dev-alice")
    assert user.home == "/home/dev-alice"
    assert user.outputs_dir.endswith("/outputs")


def test_round_trip_yaml(tmp_path: Path) -> None:
    src = tmp_path / "lca-host.yaml"
    src.write_text(DEFAULT_YAML, encoding="utf-8")
    loaded = HostRuntimeConfig.from_yaml(src)
    out = tmp_path / "out.yaml"
    loaded.to_yaml(out)
    again = HostRuntimeConfig.from_yaml(out)
    assert again.find_user("sandbox-user") is not None
    assert again.tools.python_min_version == "3.10"
    assert again.venv.check_imports[0] == "pandas"


def test_find_user_none_when_absent() -> None:
    config = HostRuntimeConfig()
    assert config.find_user("missing") is None
    config.users.append(UserConfig(name="dev-bob"))
    found = config.find_user("dev-bob")
    assert found is not None
    assert found.home == "/home/dev-bob"
