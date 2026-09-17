"""``deployment_env`` 必须与 ``lca_kernel serve`` 的 env 分层同语义。

回归:profile 里 ``{from_env: X, required: true}`` 的值只存在于 ``.env`` 时,
lca-ops 的 resolve 检查看不到它,报 ``profile.resolve_failed``,而按同一份
``.env`` 启动的 kernel 实际健康 —— 检查与被检查对象不同源。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import lca.harness.profile.resolve.resolve as resolve_mod
from lca.infrastructure.cli.services.kernel.deployment_env import (
    deployment_env,
    resolve_profile_with_deployment_env,
)

if TYPE_CHECKING:
    import pytest


def test_allowed_prefix_key_from_dotenv_is_merged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text("COMPOSIO_API_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.delenv("COMPOSIO_API_KEY", raising=False)

    assert deployment_env(tmp_path)["COMPOSIO_API_KEY"] == "from-dotenv"


def test_forbidden_key_never_reaches_the_check_env(tmp_path: Path) -> None:
    """``LCA_PROFILE`` 只能来自 argv;检查面不得比 kernel 宽松。"""
    (tmp_path / ".env").write_text("LCA_PROFILE=web-assistant\n", encoding="utf-8")

    assert "LCA_PROFILE" not in deployment_env(tmp_path)


def test_ambient_env_stays_visible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LCA_DEPLOYMENT_ENV_PROBE", "ambient")

    assert deployment_env(tmp_path)["LCA_DEPLOYMENT_ENV_PROBE"] == "ambient"


def test_resolve_receives_the_deployment_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text("COMPOSIO_API_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.delenv("COMPOSIO_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    captured: dict[str, Any] = {}

    def _stub_resolve(profile: Path | str, *, env: Any = None) -> str:
        captured["profile"] = profile
        captured["env"] = env
        return "RESOLVED"

    monkeypatch.setattr(resolve_mod, "resolve_profile", _stub_resolve)

    assert resolve_profile_with_deployment_env(Path("p.yaml")) == "RESOLVED"
    assert captured["profile"] == Path("p.yaml")
    assert captured["env"]["COMPOSIO_API_KEY"] == "from-dotenv"
